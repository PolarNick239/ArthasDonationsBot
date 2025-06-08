# Детектор донатов со стримов Папича (Arthas)

Этот бот включает в себя несколько частей:
1) Мониторинг twitch и youtube - автоматическое обнаружение что стрим был запущен/остановлен
2) С помощью легковесных алгоритмов компьютерного зрения проверять кадры на наличие доната
3) При обнаружении доната - постит его в телеграмм канал https://t.me/arthas_twitch (за время работы бот собрал коллекцию из **18 тысяч донатов!**)

# Задача алгоритма

**На вход** дается [тройка последовательных кадров](data/sample001/) из видеопотока. Иногда эти кадры не последовательные а с некоторым шагом (например с пропуском 2-3 кадров) - это позволяет алгоритму справляться с обработкой 1080p стрима даже на слабом железе вроде Raspberry Pi.

Пример:

<a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/data/sample001/frame0.jpg"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/data/sample001/frame0.jpg" alt="Previous frame" width="32%"/></a> <a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/data/sample001/frame1.jpg"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/data/sample001/frame1.jpg" alt="Current frame with a donate appeared" width="32%"/></a> <a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/data/sample001/frame2.jpg"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/data/sample001/frame2.jpg" alt="Next frame" width="32%"/></a>

**На выход** либо сообщается что на центральном из этих трех кадров нет доната, либо информация в какой части изображения обнаружен донат чтобы извлечь и запостить его в телеграм канал:

<a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/99_detected_donate.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/99_detected_donate.png" alt="Example of detected donate image" width="96%"/></a>

# Учет движения в кадре

Интуиция:

1) **Впервые** донат мог появиться только в тех пикселях где цвет отличается от предыдущего кадра. Это важно учесть чтобы не было повторных срабатываний на один и тот же донат.
2) Дополнительно мы ожидаем что пиксели доната не меняются на следующем кадре. Это не так важно, но если бы хотелось дополнительной надежности - можно было бы следующий кадр брать сильно позже (например через 5 секунд), донат в это время еще не должен был успеть исчезнуть, а вот многие другие пиксели вероятно уже изменились и будут отфильтрованы.

Реализация:

1) Строим маску пикселей которые в прошлом кадре значительно отличались.
2) Строим маску пикселей которые в следующем кадре значительно отличались.
3) Оставляем в кадре только те пиксели которые имеют шансы быть донатом - отличающиеся в прошлом кадре но при этом не отличающиеся в следующем (т.к. донат показывается продолжительное время).

Пример таких масок при появлении доната и оставшихся пикселей (которые имеют шансы быть донатом):

<a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/11_is_appeared_mask.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/11_is_appeared_mask.png" alt="11_is_appeared_mask.png" width="32%"/></a> <a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/12_is_gone_mask.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/12_is_gone_mask.png" alt="12_is_gone_mask.png" width="32%"/></a> <a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/22_frame_without_old_data_and_without_what_is_gone.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/22_frame_without_old_data_and_without_what_is_gone.png" alt="22_frame_without_old_data_and_without_what_is_gone.png" width="32%"/></a>

# Априорный учет в какой части кадра донаты

Донаты показываются только сверху - поэтому откусываем верхнюю часть изображения.

Это дополнительная надежность и защита от ложных срабатываний (например в случае когда на экране показывается цветная картинка с объектами синего и желтого цвета - в таком случае алгоритм может принять ее за донат - но если она не в зоне потенциального доната - мы защитились от такого случая).

<a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/30_header_30_image_after_crop_to_detect_letters.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/30_header_30_image_after_crop_to_detect_letters.png" alt="30_header_30_image_after_crop_to_detect_letters.png" width="32%"/></a>

# Ищем буквы синего и желтого цветов

Интуиция:

1) Донат - это заглавие (никнейм отправителя) + текст сообщения.
2) Значит мы ищем синие буквы заглавия и желтые буквы сообщения.
3) Если нашли и то и то - там скорее-всего донат.

Реализация:

1) Оставляем пиксели нужного цвета (**синего** или **желтого**) - преобразовав картинку в **HSV** (Hue + Saturation + Value) и оставив только те пиксели которые из диапазона нужного нам цвета.
2) Находим скопления пикселей нужного цвета чтобы увеличить надежность - одиночные случайные всплески будут проигнорированы. Это делается например через **СНМ** (Систему Непересекающихся Множеств) - объединяя в множества пиксели нужного цвета и оставляя в конце только те пиксели - у кого множество нужного нам размера.
3) Проецируем каждое скопление-кружочек на левую ось (см. на белый график) чтобы с дополнительной надежностью решить "где много букв", а не "одна случайная".

Пример на синих буквах:

<a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/30_header_31_pixels_with_letters_colo_by_hue_sat_val.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/30_header_31_pixels_with_letters_colo_by_hue_sat_val.png" alt="30_header_31_pixels_with_letters_colo_by_hue_sat_val.png" width="32%"/></a> <a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/30_header_32_pixels_with_letters_in_blobs.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/30_header_32_pixels_with_letters_in_blobs.png" alt="30_header_32_pixels_with_letters_in_blobs.png" width="32%"/></a> <a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/30_header_99_plot_blobs_hists.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/30_header_99_plot_blobs_hists.png" alt="30_header_99_plot_blobs_hists.png" width="32%"/></a>

Пример на желтых буквах: 

<a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/31_donate_31_pixels_with_letters_colo_by_hue_sat_val.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/31_donate_31_pixels_with_letters_colo_by_hue_sat_val.png" alt="31_donate_31_pixels_with_letters_colo_by_hue_sat_val.png" width="32%"/></a> <a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/31_donate_32_pixels_with_letters_in_blobs.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/31_donate_32_pixels_with_letters_in_blobs.png" alt="31_donate_32_pixels_with_letters_in_blobs.png" width="32%"/></a> <a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/31_donate_99_plot_blobs_hists.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/31_donate_99_plot_blobs_hists.png" alt="31_donate_99_plot_blobs_hists.png" width="32%"/></a>

# Если нашли синие и желтые буквы

Если у нас большое скопление и синих и желтых букв - в этом диапазоне графика по вертикали (по левой оси) и нужно извлечь донат:

<a href="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/99_detected_donate.png"><img src="https://raw.githubusercontent.com/PolarNick239/ArthasDonationsBot/master/debug/99_detected_donate.png" alt="Example of detected donate image" width="96%"/></a>
