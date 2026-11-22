# Đơn vị đo

## Đơn vị đo trong hệ kiểu của DSL

Một ngôn ngữ chuyên miền (domain-specific language, DSL) thường làm việc với các đại lượng có đơn vị như độ dài, khối lượng, thời gian, nhiệt độ, vận tốc, diện tích, thể tích, năng lượng hoặc tiền tệ. Nếu hệ thống chỉ biểu diễn mọi giá trị bằng số nguyên hoặc số thực, nhiều phép toán vẫn chạy dù chúng không có ý nghĩa trong miền.

Ví dụ, một hệ thống tính cước vận chuyển có thể lưu khối lượng theo kilogram, khoảng cách theo kilomet và thời gian theo phút. Nếu biểu thức cộng khối lượng với khoảng cách, phép cộng số học vẫn thực hiện được khi cả hai đều là số thực. Nhưng kết quả không phải đại lượng có ý nghĩa. Một hệ kiểu hỗ trợ đơn vị đo có thể phát hiện lỗi đó trước khi chương trình được thực thi.

**Đơn vị đo (unit of measure)** là chuẩn dùng để biểu diễn độ lớn của một đại lượng. **Đại lượng (quantity)** là giá trị đi kèm đơn vị, ví dụ 5 mét, 12 giây hoặc 3 kilogram. Trong DSL, đơn vị có thể tham gia vào hệ kiểu để phân biệt đại lượng, giới hạn phép toán hợp lệ, hỗ trợ chuyển đổi và làm biểu thức gần với cách chuyên gia miền suy nghĩ.

Một DSL có thể hỗ trợ đơn vị đo ở nhiều mức:

- Cho phép ghi đơn vị trong literal rồi chuyển về đơn vị chuẩn khi phân tích.
- Gắn đơn vị với kiểu dữ liệu để kiểm tra tương thích khi biên dịch.
- Biểu diễn quantity bằng cả giá trị số và đơn vị ở thời gian chạy.
- Hỗ trợ chuyển đổi, kiểm tra thứ nguyên và quy tắc làm tròn.
- Tích hợp đơn vị vào mô hình miền, API, dữ liệu lưu trữ và giao diện hiển thị.

Mục tiêu không chỉ là cho phép viết 5 km thay vì 5000 m. Một thiết kế tốt giúp ngăn nhầm lẫn giữa các đại lượng, làm rõ quy tắc tính toán và bảo toàn ý nghĩa dữ liệu từ lúc viết DSL đến khi thực thi.

## Phân biệt đại lượng, giá trị, đơn vị và thứ nguyên

Bốn khái niệm này liên quan chặt chẽ nhưng không đồng nhất.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Đại lượng (quantity) | Thuộc tính có thể đo được của đối tượng hoặc hiện tượng | Chiều dài, khối lượng, thời gian |
| Giá trị số | Con số dùng để biểu diễn độ lớn | 5, 12.5, 300 |
| Đơn vị (unit) | Chuẩn dùng để biểu diễn đại lượng | m, km, s, kg |
| Thứ nguyên (dimension) | Bản chất của đại lượng, độc lập với đơn vị cụ thể | Chiều dài, thời gian, khối lượng |

Ví dụ, 5 kilomet và 5000 mét có giá trị số và đơn vị khác nhau nhưng cùng biểu diễn một độ dài. Cả hai có thứ nguyên chiều dài. Ngược lại, 5 kilogram và 5 kilomet có cùng giá trị số nhưng khác thứ nguyên nên không thể thay thế cho nhau.

Một quantity thường là giá trị số kết hợp với đơn vị và đôi khi cả độ chính xác hoặc độ không đảm bảo đo. Trong DSL, kiểu quantity có thể lưu hoặc suy ra những thông tin này.

### Đơn vị và thứ nguyên

Đơn vị là cách định lượng một đại lượng; thứ nguyên mô tả loại đại lượng. Một thứ nguyên có thể có nhiều đơn vị tương đương theo hệ chuyển đổi.

- Thứ nguyên chiều dài có thể dùng mét, kilomet, centimet hoặc inch.
- Thứ nguyên thời gian có thể dùng giây, phút, giờ hoặc ngày.
- Thứ nguyên khối lượng có thể dùng kilogram, gram hoặc pound.
- Thứ nguyên vận tốc có thể dùng mét trên giây hoặc kilomet trên giờ.

Hai đơn vị cùng thứ nguyên có thể chuyển đổi cho nhau nếu có quan hệ chuyển đổi được định nghĩa. Hai đơn vị khác thứ nguyên thường không thể chuyển đổi trực tiếp.

Cần tránh dùng từ “đơn vị” và “thứ nguyên” thay thế cho nhau. Một hệ kiểu chỉ kiểm tra tên đơn vị có thể bỏ sót trường hợp hai đơn vị khác nhau nhưng cùng thứ nguyên, hoặc không nhận ra hai số cùng kiểu nhưng biểu diễn những đại lượng không tương thích.

### Đại lượng vô thứ nguyên

Một số đại lượng không có thứ nguyên, chẳng hạn tỷ số, hệ số hoặc số lần lặp. Tuy nhiên, “không có thứ nguyên” không có nghĩa mọi giá trị vô thứ nguyên đều cùng ý nghĩa.

Tỷ lệ giảm giá, hệ số ma sát và góc đo bằng radian có thể được xem là vô thứ nguyên trong phân tích thứ nguyên, nhưng không nên tự động thay thế cho nhau. DSL có thể dùng các kiểu miền riêng như Percentage, Ratio, Count hoặc Angle để giữ ý nghĩa ngữ nghĩa.

## Hệ đơn vị và đơn vị cơ sở

Để kiểm tra và chuyển đổi đại lượng, DSL cần một hệ quy chiếu đơn vị. Một lựa chọn phổ biến là dựa trên Hệ đơn vị quốc tế (International System of Units, SI), nhưng DSL có thể bổ sung đơn vị miền hoặc chấp nhận hệ khác khi cần.

Các đơn vị cơ sở SI gồm:

| Đại lượng cơ sở | Đơn vị SI | Ký hiệu |
|---|---|---|
| Chiều dài | mét | m |
| Khối lượng | kilogram | kg |
| Thời gian | giây | s |
| Cường độ dòng điện | ampere | A |
| Nhiệt độ nhiệt động lực học | kelvin | K |
| Lượng chất | mole | mol |
| Cường độ sáng | candela | cd |

Từ các đơn vị cơ sở có thể tạo đơn vị dẫn xuất:

| Đại lượng | Đơn vị | Biểu diễn theo đơn vị cơ sở |
|---|---|---|
| Diện tích | mét vuông (m²) | m × m |
| Thể tích | mét khối (m³) | m × m × m |
| Vận tốc | mét trên giây (m/s) | m / s |
| Gia tốc | mét trên giây bình phương (m/s²) | m / s² |
| Lực | newton (N) | kg × m / s² |
| Năng lượng | joule (J) | kg × m² / s² |
| Công suất | watt (W) | kg × m² / s³ |
| Áp suất | pascal (Pa) | kg / (m × s²) |

Một hệ kiểu có thể mô tả thứ nguyên bằng số mũ của các thứ nguyên cơ sở. Ví dụ, vận tốc có vector thứ nguyên Length^1 × Time^-1; gia tốc có Length^1 × Time^-2; lực có Mass^1 × Length^1 × Time^-2.

### Đơn vị cơ sở và đơn vị chuẩn nội bộ

Một DSL có thể chọn đơn vị chuẩn nội bộ cho mỗi thứ nguyên. Chẳng hạn, mọi độ dài được chuẩn hóa về mét, thời gian về giây và khối lượng về kilogram. Khi đọc literal, frontend chuyển giá trị về đơn vị chuẩn hoặc lưu hệ số chuyển đổi để runtime xử lý.

Đơn vị chuẩn nội bộ không bắt buộc phải là đơn vị SI trong mọi lĩnh vực. Một hệ thống giao dịch có thể dùng đơn vị tiền tệ chuẩn theo từng giao dịch; một DSL thiết kế bản vẽ có thể lưu độ dài theo millimet; một hệ thống bản đồ có thể lưu tọa độ theo quy ước riêng. Điều quan trọng là đơn vị chuẩn và quy tắc chuyển đổi phải được công bố, nhất quán và không làm mất độ chính xác cần thiết.

## Biểu diễn đơn vị trong cú pháp DSL

DSL có thể cho phép đơn vị xuất hiện trực tiếp trong literal để biểu thức dễ đọc.

    distance = 12 km
    duration = 30 min
    mass = 4.5 kg
    speed = 80 km/h
    temperature = 25 degC

Đây là cú pháp minh họa. Ngôn ngữ cần quy định đơn vị được viết liền với số hay cách nhau bằng khoảng trắng, tên đơn vị có phân biệt chữ hoa/chữ thường không và ký hiệu nào được chấp nhận.

### Literal có đơn vị

Một literal có đơn vị gồm phần số và phần đơn vị. Lexer có thể nhận diện nó thành một token quantity literal hoặc nhận diện số và đơn vị thành các token riêng để parser kết hợp.

Grammar giản lược:

    quantityLiteral = number, unit ;
    unit = unitName | compoundUnit ;
    compoundUnit = unitName, "/", unitName ;

Nếu cho phép biểu thức đơn vị phức tạp, grammar có thể hỗ trợ phép nhân, chia và lũy thừa:

    unitExpression = unitFactor, { ( "*" | "/" ), unitFactor } ;
    unitFactor = unitName, [ "^", integer ] ;

Đây chỉ là phác thảo cú pháp. Cần định nghĩa precedence, dấu ngoặc, số mũ âm và cách phân biệt dấu chia trong đơn vị với phép chia trong biểu thức.

### Khoảng trắng và cách viết đơn vị

Một số quy ước có thể được chọn:

- 12 km: số và ký hiệu đơn vị được phân tách bằng khoảng trắng.
- 12km: số và đơn vị viết liền.
- 12 kilometer: dùng tên đơn vị đầy đủ.
- 12 kilometers: cho phép dạng số nhiều theo ngôn ngữ tự nhiên.

Trong DSL kỹ thuật, ký hiệu chuẩn thường giúp parser đơn giản và giảm nhập nhằng. Tên đơn vị đầy đủ có thể được hỗ trợ như alias nếu cần thân thiện với người dùng.

Cần phân biệt literal 12 m với biểu thức 12 * m. Nếu m là tên biến hoặc hằng số trong DSL, hai cách viết có thể mang ý nghĩa khác nhau. Grammar cần xác định đơn vị được nhận diện như hậu tố literal hay là một biểu thức riêng.

### Phân biệt chữ hoa và chữ thường

Ký hiệu đơn vị có thể phân biệt chữ hoa và chữ thường. Ví dụ, m thường biểu diễn mét, còn M có thể được dùng cho tiền tố hoặc đơn vị khác tùy hệ quy ước. s là giây; S có thể biểu diễn siemens. Vì vậy, DSL cần quyết định việc so khớp ký hiệu đơn vị có phân biệt case hay không.

Nếu DSL không phân biệt chữ hoa và chữ thường cho tên miền nói chung, đơn vị có thể là ngoại lệ được quy định riêng. Không nên tự động chuyển toàn bộ ký hiệu đơn vị về chữ thường vì có thể làm thay đổi ý nghĩa.

### Alias và tên hiển thị

Một đơn vị có thể có nhiều cách viết: m và meter, kg và kilogram, min và minute. DSL có thể cho phép alias nhưng nên quy về một định danh chuẩn trong mô hình.

Ví dụ cú pháp giả định:

    unit meter = "m"
    alias "metre" -> meter
    alias "meters" -> meter

Nếu cho phép alias do người dùng khai báo, cần tránh xung đột tên, vòng lặp alias và việc một alias trỏ đến nhiều đơn vị khác nhau.

## Kiểu quantity và hệ kiểu có đơn vị

Một kiểu số thông thường như Integer hoặc Decimal chỉ mô tả dạng lưu trữ, không mô tả đại lượng mà số đó biểu diễn. Một hệ kiểu có đơn vị cần thể hiện cả kiểu số và đơn vị hoặc thứ nguyên.

Có thể hình dung kiểu quantity như sau:

    Quantity<NumericType, Unit>

Ví dụ:

    Quantity<Decimal, Meter>
    Quantity<Decimal, Second>
    Quantity<Decimal, Kilogram>
    Quantity<Decimal, MeterPerSecond>

Kiểu Quantity<Decimal, Meter> và Quantity<Decimal, Second> không tương thích dù cùng dùng Decimal bên trong.

### Kiểm tra tương thích theo đơn vị

Một DSL có thể áp dụng các quy tắc:

- Hai quantity có cùng thứ nguyên có thể được so sánh sau khi quy đổi về cùng đơn vị.
- Hai quantity khác thứ nguyên không được so sánh trực tiếp.
- Phép cộng và trừ yêu cầu hai đại lượng cùng thứ nguyên.
- Phép nhân kết hợp thứ nguyên của hai toán hạng.
- Phép chia trừ số mũ thứ nguyên của mẫu khỏi tử.
- Phép lũy thừa với số mũ nguyên nhân các số mũ thứ nguyên theo hệ số đó.
- Một số hàm toán học chỉ nhận đại lượng vô thứ nguyên hoặc một kiểu miền cụ thể.

Ví dụ:

    3 m + 20 cm       // hợp lệ, kết quả có thứ nguyên chiều dài
    5 kg + 2 kg       // hợp lệ, kết quả có thứ nguyên khối lượng
    3 m + 2 s         // lỗi: khác thứ nguyên
    10 m / 2 s        // hợp lệ, kết quả có thứ nguyên vận tốc
    4 m * 3 m         // hợp lệ, kết quả có thứ nguyên diện tích

Kết quả cụ thể được biểu diễn theo đơn vị nào phụ thuộc quy tắc của DSL: giữ đơn vị toán hạng trái, chọn đơn vị chuẩn hoặc dùng một dạng đơn vị chuẩn hóa.

### Type checking tĩnh

Nếu đơn vị được xác định ngay từ literal và khai báo, compiler hoặc semantic analyzer có thể kiểm tra phép toán trước khi chạy.

    let distance: Length = 12 km
    let duration: Time = 30 min
    let speed: Velocity = distance / duration

    let invalid = distance + duration

Biểu thức invalid phải bị từ chối vì Length và Time khác thứ nguyên. Hệ thống có thể báo lỗi ngay tại toán tử cộng, kèm thông tin hai kiểu đang được kết hợp.

Type checking tĩnh có lợi khi quy tắc DSL ổn định và đơn vị của biến có thể suy ra. Nếu đơn vị chỉ được xác định từ dữ liệu bên ngoài hoặc cấu hình runtime, hệ thống có thể cần kiểm tra lúc chạy.

### Suy luận kiểu

Người dùng không nhất thiết phải khai báo đơn vị ở mọi biến nếu hệ thống có thể suy luận từ biểu thức.

    let distance = 12 km
    let time = 30 min
    let speed = distance / time

Hệ thống có thể suy ra distance là Length, time là Time và speed là Velocity. Suy luận kiểu giúp cú pháp gọn hơn, nhưng diagnostics cần cho biết kiểu đã suy ra và lý do khi phép toán không tương thích. Với API phức tạp, nên cho phép khai báo kiểu tường minh khi cần.

### Kiểm tra tĩnh và kiểm tra lúc chạy

Kiểm tra tĩnh phát hiện lỗi trước khi chương trình được thực thi hoặc triển khai. Kiểm tra lúc chạy xác nhận điều kiện dựa trên dữ liệu thực tế. Cả hai đều có thể cần thiết.

Ví dụ, DSL có thể kiểm tra tĩnh rằng order.total có kiểu Money và shipment.fee nhận Money. Nhưng việc khách hàng thực sự có hạng VIP hay không phụ thuộc dữ liệu tại thời điểm chạy. Thiết kế tốt phân biệt lỗi cấu trúc hoặc kiểu có thể phát hiện sớm với điều kiện nghiệp vụ chỉ biết khi có dữ liệu thực tế.

## Quy tắc toán học cho đơn vị

Đơn vị không chỉ là nhãn gắn sau con số. Khi thực hiện phép toán, hệ thống cần tính toán thứ nguyên theo các quy tắc nhất quán.

### Phép cộng và trừ

Phép cộng hoặc trừ yêu cầu các đại lượng có cùng thứ nguyên. Các đơn vị có thể khác nhau nếu chuyển đổi được.

    2 m + 30 cm = 2.3 m

Cả hai toán hạng đều là chiều dài. DSL có thể chuyển 30 cm thành 0.3 m trước khi cộng, hoặc biểu diễn kết quả theo một đơn vị được chọn.

Ngược lại:

    2 m + 3 kg

không hợp lệ vì chiều dài và khối lượng khác thứ nguyên.

### Phép nhân

Phép nhân kết hợp thứ nguyên:

    3 m * 4 m = 12 m^2
    5 kg * 2 m/s = 10 kg*m/s

Kết quả có thể là diện tích hoặc một đại lượng dẫn xuất khác. Hệ thống có thể chuẩn hóa biểu thức đơn vị để so sánh các biểu diễn tương đương.

### Phép chia

Phép chia lấy hiệu số mũ thứ nguyên:

    100 m / 20 s = 5 m/s

Nếu chia hai đại lượng cùng thứ nguyên, kết quả vô thứ nguyên:

    10 m / 2 m = 5

Tuy nhiên, kết quả vô thứ nguyên có thể cần giữ kiểu miền, ví dụ Ratio hoặc ScaleFactor, thay vì chỉ trở thành Decimal thông thường.

### Lũy thừa và căn

Nếu một đại lượng được nâng lên lũy thừa nguyên, số mũ của mỗi thứ nguyên được nhân với số mũ đó:

    (3 m)^2 = 9 m^2

Căn bậc hai có thể tạo số mũ phân số. Một DSL có thể chỉ hỗ trợ căn khi kết quả có thứ nguyên hợp lệ theo chính sách của nó. Nếu chỉ hỗ trợ lũy thừa nguyên, grammar và type checker cần giới hạn rõ.

### Hàm toán học

Các hàm như sin, cos, exp và log thường yêu cầu đối số vô thứ nguyên theo quy ước toán học. Hàm căn bậc hai, trị tuyệt đối hoặc làm tròn có quy tắc kiểu riêng.

Góc là trường hợp cần chú ý. Radian có thể được xem là vô thứ nguyên trong SI, nhưng một DSL kỹ thuật thường nên phân biệt Angle với Ratio để tránh truyền một tỷ lệ vào hàm sin khi người dùng dự kiến truyền góc. Nếu hỗ trợ độ và radian, cần chuyển đổi trước khi tính toán.

## Chuyển đổi đơn vị

Chuyển đổi đơn vị là phép biểu diễn cùng một đại lượng bằng đơn vị khác. Với các đơn vị có quan hệ tỷ lệ tuyến tính, công thức thường có dạng:

    valueInTarget = valueInSource * conversionFactor

Ví dụ:

    1 km = 1000 m
    1 h = 3600 s
    1 kg = 1000 g

Vì vậy:

    2.5 km = 2500 m
    3 h = 10800 s

### Chuyển đổi tự động và chuyển đổi tường minh

DSL có thể tự động chuyển đổi khi hai toán hạng cùng thứ nguyên:

    distance = 2 km + 300 m

Hoặc yêu cầu người dùng chuyển đổi tường minh:

    distance = 2 km + convert(300 m, km)

Tự động chuyển đổi làm biểu thức gọn hơn, nhưng có thể che giấu thay đổi độ chính xác hoặc làm người dùng khó biết đơn vị kết quả. Chuyển đổi tường minh giúp ý định rõ nhưng làm cú pháp dài hơn.

Một lựa chọn cân bằng là cho phép tự động chuyển đổi trong phép cộng, trừ và so sánh cùng thứ nguyên, nhưng yêu cầu tường minh khi gán sang kiểu có đơn vị cụ thể hoặc khi chuyển đổi có thể làm mất thông tin.

### Đơn vị chuẩn và chuẩn hóa

Một cách triển khai là chuẩn hóa tất cả quantity về đơn vị nội bộ trước khi tính toán. Ví dụ, mọi độ dài chuyển về mét và mọi thời gian về giây. Khi hiển thị, hệ thống có thể định dạng lại theo đơn vị mà người dùng chọn.

Lợi ích:

- So sánh và tính toán dễ triển khai.
- Giảm số trường hợp phải xử lý trong backend.
- Có thể lưu dữ liệu theo một quy ước thống nhất.
- Dễ kiểm tra tương thích thứ nguyên.

Hạn chế:

- Có thể phát sinh sai số khi chuyển sang số thực.
- Đơn vị chuẩn không phải lúc nào cũng thuận tiện cho người dùng.
- Một số phép chuyển đổi không thuần tuyến tính.
- Cần lưu thông tin nguồn hoặc precision nếu cần hiển thị chính xác như đầu vào.

### Chuyển đổi chính xác và sai số số học

Không phải mọi hệ số chuyển đổi đều có biểu diễn hữu hạn trong hệ cơ số 10 hoặc nhị phân. Ví dụ, phân số 1/3 không thể biểu diễn chính xác bằng một số chữ số thập phân hữu hạn. Chuyển đổi giữa một số đơn vị có thể tạo sai số làm tròn.

Với hệ thống tài chính hoặc đo lường chính xác, cần chọn kiểu số phù hợp:

- Số nguyên với đơn vị nhỏ nhất, ví dụ millisecond hoặc millimeter.
- Decimal với độ chính xác và scale xác định.
- Rational (phân số) khi cần giữ hệ số chuyển đổi chính xác.
- Floating-point khi chấp nhận sai số theo giới hạn ứng dụng.

Không nên dùng floating-point mặc định cho mọi quantity. Cần cân nhắc yêu cầu chính xác, phạm vi giá trị và hiệu năng.

## Đơn vị có độ lệch: nhiệt độ

Không phải mọi phép chuyển đổi đơn vị đều chỉ nhân với một hệ số. Nhiệt độ là ví dụ điển hình của đơn vị có độ lệch (affine unit).

Công thức chuyển Celsius sang Fahrenheit:

    F = C * 9/5 + 32

Công thức chuyển Celsius sang Kelvin:

    K = C + 273.15

Do có thành phần cộng, không thể xử lý độ C giống như mét hoặc giây trong mọi phép toán.

### Điểm nhiệt độ và khoảng nhiệt độ

Cần phân biệt nhiệt độ tại một điểm với chênh lệch nhiệt độ:

- 20 degC là một điểm nhiệt độ.
- 5 delta_degC là một khoảng chênh lệch nhiệt độ.

Phép cộng hai điểm nhiệt độ thường không có ý nghĩa vật lý như phép cộng hai độ dài. Nhưng có thể trừ hai điểm nhiệt độ để tạo ra một khoảng nhiệt độ. Có thể cộng một khoảng nhiệt độ vào một điểm để tạo điểm mới.

    25 degC - 20 degC = 5 delta_degC
    20 degC + 5 delta_degC = 25 degC

DSL có hỗ trợ nhiệt độ nên mô hình hai kiểu riêng: TemperaturePoint và TemperatureInterval, hoặc dùng một kiểu affine có quy tắc toán tử tương ứng. Nếu coi mọi nhiệt độ là quantity tuyến tính thông thường, hệ thống có thể cho phép các phép toán vô nghĩa.

### Đơn vị affine khác

Một số miền có các thang đo hoặc hệ tọa độ có độ lệch. Chẳng hạn, timestamp là điểm trên trục thời gian, còn duration là khoảng thời gian. Cộng hai timestamp không giống cộng hai duration; trừ hai timestamp tạo ra duration.

DSL xử lý thời gian nên phân biệt Instant/DateTime với Duration/Period, đồng thời xác định múi giờ và lịch nếu liên quan. Không nên xem ngày lịch và số giây là cùng một kiểu chỉ vì có thể chuyển đổi trong một số ngữ cảnh.

## Đơn vị ghép và đơn vị dẫn xuất

Một đơn vị ghép được tạo từ phép nhân hoặc chia các đơn vị khác. Ví dụ:

- m/s: vận tốc.
- m/s²: gia tốc.
- kg/m³: khối lượng riêng.
- N/m²: áp suất.
- kWh: năng lượng.
- L/min: lưu lượng thể tích.

DSL có thể cho phép viết đơn vị ghép trực tiếp hoặc cung cấp tên đơn vị đã đăng ký. Ví dụ, Pa tương đương N/m² theo SI; km/h có thể chuyển đổi sang m/s bằng hệ số thích hợp.

### Chuẩn hóa biểu thức đơn vị

Hệ thống có thể chuyển một đơn vị ghép về dạng chuẩn dựa trên đơn vị cơ sở và số mũ.

    km/h = (1000 m) / (3600 s)
         = (5/18) m/s

Một biểu thức đơn vị được chuẩn hóa có thể lưu vector thứ nguyên và hệ số scale. Hai biểu thức được xem là tương thích nếu vector thứ nguyên giống nhau; giá trị có thể chuyển đổi bằng tỷ lệ giữa các hệ số.

Cần phân biệt khả năng tương thích thứ nguyên với tương đương đơn vị. m/s và km/h có cùng thứ nguyên vận tốc nhưng hệ số scale khác nhau. kg/m³ và g/cm³ cũng cùng thứ nguyên khối lượng riêng nhưng có hệ số khác.

### Đơn vị dẫn xuất có tên

Người thiết kế có thể đăng ký đơn vị dẫn xuất có tên như newton, joule hoặc watt để biểu thức dễ đọc:

    force = 20 N
    energy = 100 J
    power = 50 W

Hệ thống cần biết định nghĩa thứ nguyên và hệ số scale của mỗi đơn vị. Tên đơn vị không nên chỉ là alias văn bản nếu cần kiểm tra và chuyển đổi.

## Tiền tố đơn vị

Hệ SI có các tiền tố biểu diễn bội số hoặc ước số của đơn vị, ví dụ kilo (k), centi (c), milli (m), micro (µ) và mega (M).

| Tiền tố | Ký hiệu | Hệ số |
|---|---|---:|
| kilo | k | 10^3 |
| hecto | h | 10^2 |
| deca | da | 10^1 |
| deci | d | 10^-1 |
| centi | c | 10^-2 |
| milli | m | 10^-3 |
| micro | µ | 10^-6 |
| nano | n | 10^-9 |
| mega | M | 10^6 |
| giga | G | 10^9 |

DSL có thể hỗ trợ tiền tố như một phần của lexer hoặc đăng ký từng ký hiệu đơn vị hoàn chỉnh. Nếu lexer tự ghép tiền tố với tên đơn vị, cần xử lý các ngoại lệ và quy tắc chuẩn hóa. Không phải đơn vị nào cũng được phép kết hợp với mọi tiền tố.

Cần chú ý chữ hoa/chữ thường: m và M không tương đương. Ký hiệu µ có thể được nhập bằng Unicode hoặc thay bằng alias ASCII như u theo quy ước của DSL.

## Các chiến lược thiết kế kiểu đơn vị

Có nhiều cách đưa đơn vị vào hệ kiểu. Mỗi cách tạo ra mức bảo đảm và chi phí triển khai khác nhau.

### Kiểu riêng cho từng đơn vị

Cách đơn giản là tạo kiểu riêng như Meter, Kilometer, Second, Minute và Kilogram.

Ưu điểm:

- Dễ hiểu và dễ kiểm tra ở phạm vi nhỏ.
- Có thể ngăn cộng trực tiếp các kiểu khác nhau.
- Mỗi kiểu có thể định nghĩa chuyển đổi rõ ràng.

Hạn chế:

- Số lượng kiểu tăng nhanh khi có nhiều đơn vị.
- Cần quy định cách cộng giữa hai kiểu cùng thứ nguyên nhưng khác đơn vị.
- Đơn vị ghép làm mô hình kiểu phức tạp hơn.
- Khó biểu diễn đơn vị do người dùng mở rộng.

Cách này phù hợp khi miền chỉ có một tập nhỏ đơn vị cố định.

### Kiểu quantity tham số hóa theo đơn vị

Một kiểu tổng quát có thể dùng tham số đơn vị:

    Quantity<Decimal, Meter>
    Quantity<Decimal, Second>
    Quantity<Decimal, MeterPerSecond>

Cách này giảm số lớp và cho phép thư viện định nghĩa các toán tử generic. Hệ kiểu có thể phân biệt Quantity<Decimal, Meter> với Quantity<Decimal, Second>.

Cần xem xét việc biểu diễn các đơn vị tương đương. Nếu Meter và Kilometer là hai tham số kiểu khác nhau, hệ thống phải có quy tắc để cộng hoặc so sánh chúng sau chuyển đổi. Có thể dùng một kiểu đại lượng theo thứ nguyên chung, hoặc một cơ chế chuyển đổi type-level.

### Kiểu quantity theo thứ nguyên

Một cách tổng quát hơn là kiểu hóa theo vector thứ nguyên:

    Quantity<Decimal, Dimension<Length=1, Time=-1>>

Khi đó, MeterPerSecond và KilometerPerHour có cùng kiểu thứ nguyên Velocity, dù đơn vị hiển thị khác nhau. Giá trị được lưu kèm hệ số scale hoặc đơn vị cụ thể.

Cách này mạnh cho hệ thống kỹ thuật có nhiều đơn vị ghép, nhưng hệ kiểu và thuật toán chuẩn hóa phức tạp hơn. Cần đảm bảo việc suy luận kiểu và hiển thị lỗi đủ dễ hiểu.

### Kiểm tra đơn vị lúc chạy

Nếu đơn vị đến từ tệp cấu hình, cơ sở dữ liệu hoặc người dùng nhập, không phải lúc nào compiler cũng biết đơn vị ở thời điểm biên dịch. Khi đó, DSL có thể dùng quantity object lưu giá trị và metadata đơn vị, rồi kiểm tra tương thích lúc chạy.

    let measurement = parseQuantity(inputText)
    let target = convert(measurement, meter)

Nếu đầu vào là 10 kg mà yêu cầu là Length, hàm parse hoặc convert phải trả lỗi có cấu trúc. Kiểm tra runtime linh hoạt hơn nhưng lỗi được phát hiện muộn hơn và cần quản lý trạng thái đơn vị chưa hợp lệ.

### Kết hợp kiểm tra tĩnh và động

Một thiết kế thực tế thường kết hợp:

- Kiểu tĩnh cho các đơn vị và thứ nguyên đã biết trong chương trình.
- Kiểm tra runtime cho dữ liệu bên ngoài hoặc đơn vị do người dùng cung cấp.
- Validation tại ranh giới hệ thống để không đưa quantity chưa xác thực vào logic miền.
- Kiểu miền riêng cho các khái niệm có cùng thứ nguyên nhưng khác ý nghĩa nghiệp vụ.

## Scalar, tỷ lệ và phần trăm

Một số phép toán liên quan đến đơn vị cần phân biệt quantity với scalar (giá trị vô thứ nguyên).

Scalar là một số không gắn với thứ nguyên vật lý. Khi nhân quantity với scalar, thứ nguyên của quantity được giữ nguyên:

    5 m * 2 = 10 m

Khi chia quantity cho scalar khác 0, thứ nguyên cũng giữ nguyên:

    10 s / 2 = 5 s

Khi chia hai quantity cùng thứ nguyên, kết quả là scalar hoặc một kiểu tỷ lệ:

    10 m / 2 m = 5

Phần trăm là trường hợp thường gây nhầm. 10% thường tương đương 0.1 dưới dạng tỷ lệ, nhưng kiểu Percentage có thể hữu ích để phân biệt với một số vô thứ nguyên bất kỳ. Ví dụ, nhân 10% với 200000 VND tạo ra 20000 VND; cộng 10% trực tiếp với 200000 VND thường không hợp lệ.

DSL cần định nghĩa rõ:

- Literal 10% được lưu dưới dạng 10 hay 0.1.
- Phép nhân và chia với Percentage.
- Cộng hai Percentage có được phép không.
- Chuyển đổi giữa Percentage và Ratio.
- Cách làm tròn khi tính tiền sau khi áp dụng tỷ lệ.

## Góc và đơn vị góc

Góc thường được biểu diễn bằng radian hoặc degree. Radian có thể được xem là vô thứ nguyên về mặt thứ nguyên vật lý, nhưng ý nghĩa miền của Angle khác với một tỷ lệ thông thường.

Một DSL có thể hỗ trợ:

    angleA = 90 deg
    angleB = 1.57079632679 rad
    result = sin(angleA)

Hệ thống cần chuyển degree sang radian trước khi gọi hàm toán học nếu hàm runtime yêu cầu radian. Nên quy định hàm sin, cos và tan nhận Angle, không nhận mọi kiểu vô thứ nguyên.

Góc cũng có thể có quy tắc chuẩn hóa theo miền, chẳng hạn khoảng 0 đến 360 độ hoặc -180 đến 180 độ. Đây là ràng buộc giá trị chứ không chỉ là thứ nguyên, và có thể cần kiểu miền hoặc validation riêng.

## Đơn vị thời gian và ngày lịch

Thời gian có nhiều biểu diễn khác nhau:

- Duration: khoảng thời gian như 30 giây hoặc 2 giờ.
- Instant: một thời điểm tuyệt đối trên dòng thời gian.
- LocalDateTime: ngày giờ địa phương chưa gắn múi giờ.
- Period: khoảng theo lịch như 1 tháng hoặc 1 năm.
- Date: ngày lịch, không nhất thiết có thời điểm trong ngày.

Không nên xem mọi giá trị thời gian là một quantity có đơn vị giây. Một tháng lịch không có số giây cố định; ngày lịch có thể dài khác nhau khi thay đổi giờ mùa hè tại một số vùng; timestamp cần quy tắc múi giờ.

Ví dụ:

    timeout = 30 s
    start = 2026-11-15T09:00:00Z
    finish = start + timeout

Duration có thể cộng vào Instant để tạo Instant mới. Trừ hai Instant tạo Duration. Nhưng cộng hai Instant không có ý nghĩa thông thường. Period một tháng cộng vào ngày lịch cần quy tắc lịch cụ thể.

Một DSL cho lịch hoặc lập lịch cần phân biệt kiểu và phép toán, đồng thời chỉ rõ timezone, calendar và chính sách khi ngày giờ địa phương không tồn tại hoặc bị lặp do thay đổi múi giờ.

## Tiền tệ: đơn vị có quy tắc nghiệp vụ riêng

Tiền tệ thường được biểu diễn như quantity có đơn vị, nhưng không nên đồng nhất hoàn toàn với đơn vị vật lý. VND, USD và EUR là các đơn vị tiền tệ có tỷ giá thay đổi theo thời điểm và nguồn dữ liệu.

Ví dụ:

    price = 100 USD
    tax = 10 USD
    total = price + tax

Cộng hai khoản tiền cùng loại tiền thường hợp lệ. Cộng USD với VND cần chuyển đổi theo tỷ giá và thời điểm cụ thể:

    totalVnd = convert(100 USD, VND, rateAt(transactionTime))

Không nên tự động chuyển đổi tiền tệ chỉ dựa trên một hệ số cố định. Cần có thông tin tỷ giá, nguồn, thời điểm hiệu lực, chiều quy đổi, phí và quy tắc làm tròn.

Một số quy tắc cần xác định:

- Mỗi currency có số chữ số thập phân và quy tắc làm tròn riêng.
- Một số đơn vị tiền tệ không dùng hai chữ số thập phân.
- Số tiền có thể dùng Decimal hoặc số nguyên theo đơn vị nhỏ nhất.
- Phép cộng và trừ cần cùng currency hoặc một bước chuyển đổi rõ ràng.
- Phép nhân tiền với tỷ lệ cần quy tắc làm tròn.
- Phép chia tiền có thể tạo phần lẻ cần phân bổ.

Có thể mô hình hóa Money<Currency> hoặc Money với currency runtime. Kiểu tham số hóa theo currency hỗ trợ kiểm tra tĩnh khi đơn vị tiền tệ đã biết; kiểu runtime linh hoạt hơn khi xử lý nhiều currency trong cùng một tập dữ liệu.

## Đơn vị do người dùng định nghĩa

Một số miền cần đơn vị riêng, chẳng hạn điểm tín dụng, đơn vị sản phẩm, pallet, thùng, lượt xử lý, token hoặc đơn vị công suất. Không phải tất cả đều là đơn vị vật lý, nhưng chúng vẫn có thể được quản lý như kiểu quantity để tránh nhầm lẫn.

DSL có thể cho phép khai báo đơn vị:

    unit pallet = 48 item
    unit box = 12 item
    unit case = 24 item

Nếu cho phép khai báo như vậy, hệ thống cần xác định:

- Đơn vị mới có cùng thứ nguyên với đơn vị nền nào?
- Hệ số chuyển đổi có cố định không?
- Có cho phép đơn vị không có quan hệ chuyển đổi không?
- Đơn vị có phạm vi module hay toàn chương trình?
- Tên và alias có duy nhất không?
- Có thể kết hợp đơn vị mới thành đơn vị ghép không?
- Đơn vị đã dùng trong dữ liệu lưu trữ có thể bị đổi định nghĩa không?

Đơn vị do người dùng định nghĩa có thể làm DSL linh hoạt hơn, nhưng thay đổi hệ số chuyển đổi có thể ảnh hưởng dữ liệu cũ. Nên quản lý phiên bản định nghĩa đơn vị và không âm thầm thay đổi ý nghĩa của quantity đã lưu.

## Lưu trữ và trao đổi dữ liệu có đơn vị

Khi quantity được lưu hoặc trao đổi giữa các hệ thống, cần bảo toàn cả giá trị và ý nghĩa đơn vị.

Một biểu diễn JSON đơn giản:

    {
      "value": 12.5,
      "unit": "km"
    }

Một dạng khác có thể lưu đơn vị chuẩn và thứ nguyên:

    {
      "value": 12500,
      "unit": "m",
      "dimension": "Length"
    }

Không nên chỉ lưu số 12.5 rồi dựa vào tên trường distance để suy ra đơn vị. Tên trường có thể không đủ rõ hoặc dữ liệu có thể được tạo bởi nhiều hệ thống với quy ước khác nhau.

Khi trao đổi dữ liệu, cần quy định:

- Đơn vị có bắt buộc phải có không?
- Tên đơn vị theo chuẩn nào?
- Có cho phép alias không?
- Giá trị được lưu theo đơn vị gốc hay đơn vị chuẩn?
- Số chữ số có nghĩa và quy tắc làm tròn là gì?
- Thứ nguyên được khai báo hay suy ra từ schema?
- Hệ thống nhận xử lý đơn vị không nhận diện thế nào?
- Phiên bản catalog đơn vị nào được áp dụng?

Với dữ liệu lớn, schema có thể xác định đơn vị ở cấp trường thay vì lặp lại ở từng bản ghi. Tuy nhiên, nếu cùng một trường có thể chứa nhiều đơn vị, mỗi giá trị cần mang metadata riêng.

## Đơn vị đo trong mô hình dữ liệu và API

Đơn vị cần được thể hiện nhất quán qua các lớp:

    DSL source
       |
       v
    Parser / AST
       |
       v
    Typed quantity model
       |
       v
    Domain service
       |
       v
    Storage / API / UI

Nếu frontend hiểu 10 km nhưng backend nhận số 10 và coi là mét, chương trình có thể sai mà không có lỗi cú pháp. Vì vậy, đơn vị phải được bảo toàn khi chuyển AST sang IR, từ IR sang đối tượng miền, khi serialize và khi gọi API.

Một API tốt nên thể hiện đơn vị trong tên kiểu hoặc hợp đồng dữ liệu, thay vì dựa vào quy ước không được ghi lại. Ví dụ, một phương thức nhận Length rõ ràng hơn phương thức nhận double nếu giá trị cần có đơn vị.

Ở ranh giới với hệ thống ngoài, adapter có thể chuyển đổi về đơn vị chuẩn mà hợp đồng API yêu cầu. Việc chuyển đổi nên được thực hiện tại một nơi xác định, có kiểm tra và có kiểm thử, thay vì rải rác trong nhiều hàm nghiệp vụ.

## Hiển thị và định dạng quantity

Đơn vị nội bộ dùng cho tính toán có thể khác đơn vị hiển thị. Một hệ thống lưu khoảng cách bằng mét có thể hiển thị kilomet khi giá trị lớn, hoặc hiển thị centimet khi giá trị nhỏ.

Ví dụ:

- 1500 m có thể hiển thị là 1.5 km.
- 0.002 m có thể hiển thị là 2 mm.
- 3600 s có thể hiển thị là 1 h.

Tự động chọn đơn vị hiển thị có thể tiện lợi nhưng cần quy tắc ổn định để người dùng so sánh dữ liệu. Với báo cáo, hợp đồng hoặc hệ thống kiểm soát, có thể cần đơn vị hiển thị cố định.

Định dạng cũng cần xác định:

- Số chữ số thập phân.
- Làm tròn half-up, half-even hoặc quy tắc khác.
- Dấu thập phân và dấu phân nhóm theo locale.
- Khoảng trắng giữa giá trị và ký hiệu đơn vị.
- Dạng số ít/số nhiều nếu hiển thị tên đầy đủ.
- Cách biểu diễn giá trị rất lớn hoặc rất nhỏ.
- Cách hiển thị giá trị không xác định hoặc thiếu dữ liệu.

Locale có thể ảnh hưởng cách hiển thị số, nhưng không nên làm thay đổi ý nghĩa của dữ liệu đã lưu. Ví dụ, dấu phẩy có thể là dấu thập phân ở một locale và dấu phân nhóm ở locale khác. DSL nên chọn cú pháp số ổn định, còn UI có thể định dạng theo locale.

## Độ chính xác, làm tròn và sai số đo

Một quantity có thể có độ chính xác số học và độ không đảm bảo đo. Hai khái niệm này khác nhau:

- **Độ chính xác số học** liên quan đến cách lưu và tính toán số, ví dụ Decimal scale hoặc floating-point precision.
- **Độ không đảm bảo đo** mô tả khoảng biến thiên hoặc sai số của phép đo thực tế.

Ví dụ, cảm biến báo 20.1 °C không có nghĩa nhiệt độ thật chính xác tuyệt đối đến 0.1 độ. Thiết bị có thể có sai số ±0.5 °C. DSL khoa học hoặc kỹ thuật có thể cần mô hình uncertainty riêng.

Một quantity mở rộng có thể chứa:

    Measurement
      value: Decimal
      unit: Celsius
      uncertainty: 0.5
      confidence: ...

Không phải DSL nào cũng cần lưu uncertainty. Với nghiệp vụ vận chuyển, độ chính xác có thể được quy định theo cân nặng và cách làm tròn; với mô phỏng hoặc khoa học, sai số đo có thể là phần quan trọng của mô hình.

Cần xác định khi chuyển đổi đơn vị thì uncertainty được chuyển đổi ra sao. Với chuyển đổi tuyến tính theo hệ số, độ không đảm bảo tuyệt đối cũng nhân với trị tuyệt đối của hệ số. Với chuyển đổi affine, phần offset ảnh hưởng giá trị điểm nhưng không ảnh hưởng độ lớn của khoảng sai số theo cùng cách.

## Đơn vị đo và dữ liệu thiếu hoặc không hợp lệ

Giá trị quantity có thể bị thiếu, không xác định hoặc không hợp lệ. Hệ kiểu nên phân biệt các trường hợp:

- Không có giá trị (None/Null).
- Có giá trị nhưng thiếu đơn vị.
- Đơn vị không được nhận diện.
- Đơn vị không tương thích với kiểu mong đợi.
- Giá trị nằm ngoài miền hợp lệ.
- Giá trị số không hữu hạn hoặc tràn phạm vi.
- Đơn vị hợp lệ nhưng không có chuyển đổi sang đơn vị đích.

Ví dụ, một cảm biến trả về 12 nhưng không kèm đơn vị. Nếu hệ thống mong đợi độ C, không nên tự đoán đó là 12 °C trừ khi hợp đồng dữ liệu quy định rõ. Một giá trị 12 m có đơn vị hợp lệ nhưng có thể vẫn vượt giới hạn chiều dài tối đa của miền.

Diagnostics nên chỉ ra lỗi xảy ra ở lớp nào: phân tích literal, resolve đơn vị, kiểm tra thứ nguyên, kiểm tra miền hay chuyển đổi runtime.

## An toàn và giới hạn khi nạp đơn vị từ nguồn ngoài

Nếu DSL cho phép plugin hoặc người dùng khai báo đơn vị, catalog đơn vị trở thành dữ liệu cần kiểm soát. Một định nghĩa sai có thể làm mọi phép tính downstream sai theo.

Các điểm cần cân nhắc:

- Không cho alias ghi đè đơn vị chuẩn nếu không có cơ chế quản lý rõ.
- Phát hiện chu trình trong định nghĩa đơn vị.
- Kiểm tra hệ số chuyển đổi hữu hạn và khác 0 khi yêu cầu.
- Giới hạn độ dài biểu thức đơn vị và số mũ.
- Xác thực đơn vị từ nguồn ngoài trước khi đưa vào type environment.
- Gắn phiên bản catalog với chương trình hoặc dữ liệu đã biên dịch.
- Không thực thi mã tùy ý chỉ để tính hệ số chuyển đổi.
- Kiểm tra quyền khi người dùng được phép thay đổi định nghĩa đơn vị.

Một catalog chuẩn và bất biến giúp kết quả có thể tái lập. Nếu đơn vị tùy chỉnh thay đổi theo tenant hoặc môi trường, cần đưa ngữ cảnh đó vào quá trình type checking và runtime.

## Kiểm thử hệ kiểu có đơn vị

Một hệ kiểu có đơn vị cần kiểm thử cả phép toán hợp lệ, lỗi thứ nguyên, chuyển đổi và các trường hợp đặc biệt.

Các nhóm trường hợp có thể bao gồm:

- Cộng hai quantity cùng thứ nguyên nhưng khác đơn vị.
- Từ chối cộng quantity khác thứ nguyên.
- So sánh sau khi chuyển đổi đơn vị.
- Nhân và chia để tạo thứ nguyên dẫn xuất.
- Lũy thừa và căn theo quy tắc đã hỗ trợ.
- Chuyển đổi Celsius/Fahrenheit/Kelvin.
- Phân biệt điểm nhiệt độ với khoảng nhiệt độ.
- Xử lý góc degree và radian.
- Chuyển đổi currency theo tỷ giá và thời điểm.
- Làm tròn và overflow.
- Đơn vị không tồn tại, alias trùng hoặc catalog sai.
- Literal thiếu đơn vị ở vị trí yêu cầu quantity.
- Dữ liệu runtime có đơn vị không tương thích.
- Tuần tự hóa và đọc lại quantity giữ nguyên ý nghĩa.

Ví dụ:

    2 m + 30 cm        -> accepted, Length
    2 m + 3 s          -> rejected, incompatible dimensions
    10 m / 2 s         -> accepted, Velocity
    20 degC - 10 degC  -> accepted, TemperatureInterval
    20 degC + 10 degC  -> rejected or domain-defined
    100 USD + 50 VND   -> rejected without exchange conversion

Kết quả cuối cùng phụ thuộc chính sách của DSL. Đặc biệt, các phép toán với nhiệt độ và tiền tệ cần ngữ nghĩa riêng, không nên suy ra chỉ từ quy tắc thứ nguyên cơ bản.

## Những lỗi thiết kế thường gặp

### Lưu số mà không lưu đơn vị

Nếu chỉ lưu 1000 mà không biết đó là mét, gram hay millisecond, dữ liệu không đủ thông tin để sử dụng an toàn. Đơn vị nên được lưu trong kiểu, schema hoặc metadata có hợp đồng rõ.

### Dùng một kiểu số cho mọi đại lượng

Dùng Decimal cho cả tiền, khoảng cách, nhiệt độ và thời gian khiến compiler không thể phát hiện nhầm lẫn. Quantity type hoặc domain type giúp phân biệt các đại lượng.

### Chỉ so khớp tên đơn vị

Hai đơn vị khác tên nhưng cùng thứ nguyên có thể chuyển đổi; hai kiểu cùng là số nhưng khác thứ nguyên không thể cộng. Cần mô hình hóa dimension và conversion, không chỉ so sánh chuỗi đơn vị.

### Chuyển đổi ngầm không kiểm soát

Tự động chuyển đổi ở mọi vị trí có thể che giấu mất độ chính xác hoặc thay đổi đơn vị kết quả. Cần quy định nơi cho phép implicit conversion và nơi cần conversion tường minh.

### Xem nhiệt độ như quantity tuyến tính

Celsius và Fahrenheit có offset. Cần phân biệt điểm nhiệt độ và khoảng nhiệt độ để tránh các phép cộng/trừ sai nghĩa.

### Coi mọi giá trị vô thứ nguyên là tương đương

Percentage, Ratio, Angle và Count có thể cùng không có thứ nguyên vật lý nhưng khác ý nghĩa miền. Có thể cần kiểu riêng để tránh thay thế tùy tiện.

### Dùng floating-point cho mọi trường hợp

Sai số nhị phân có thể làm phép so sánh hoặc tính tiền không chính xác. Cần chọn representation theo yêu cầu và có chính sách rounding.

### Không bảo toàn đơn vị qua API

Một lớp frontend hiểu quantity nhưng backend chỉ nhận số có thể làm mất ý nghĩa. Cần giữ đơn vị qua model, serialization, API và storage hoặc chuẩn hóa tại ranh giới được xác định rõ.

## Quy trình đưa đơn vị đo vào DSL

Khi thiết kế hệ kiểu có đơn vị, có thể tiến hành theo các bước:

1. **Khảo sát đại lượng trong miền:** liệt kê các quantity thực tế, đơn vị đang dùng, độ chính xác và quy tắc nghiệp vụ.
2. **Phân loại thứ nguyên:** xác định đại lượng cơ sở, dẫn xuất và vô thứ nguyên; phân biệt các kiểu miền có ý nghĩa riêng.
3. **Chọn catalog đơn vị:** xác định đơn vị chuẩn, alias, tiền tố và nguồn định nghĩa.
4. **Thiết kế cú pháp literal:** quy định cách viết số, ký hiệu đơn vị, đơn vị ghép và chuyển đổi tường minh.
5. **Thiết kế quantity type:** chọn kiểu theo đơn vị, theo thứ nguyên hoặc kiểu runtime; xác định cách suy luận kiểu.
6. **Định nghĩa phép toán:** nêu rõ cộng, trừ, nhân, chia, so sánh, lũy thừa và hàm toán học được phép.
7. **Xác định chuyển đổi:** phân biệt chuyển đổi tuyến tính, affine, conversion cần tỷ giá hoặc lịch.
8. **Chọn representation số:** integer, decimal, rational hay floating-point; quy định precision và rounding.
9. **Tích hợp dữ liệu:** bảo toàn đơn vị trong AST/IR, domain model, API và storage.
10. **Xây diagnostics và kiểm thử:** báo lỗi thứ nguyên rõ ràng, kiểm tra chuyển đổi và các trường hợp biên.
11. **Quản lý phiên bản:** kiểm soát thay đổi catalog, alias, hệ số và ngữ nghĩa đơn vị để dữ liệu cũ không bị diễn giải lại ngoài ý muốn.

Không nhất thiết triển khai toàn bộ tính năng ngay từ đầu. Một DSL nhỏ có thể bắt đầu với vài thứ nguyên phổ biến và chuyển đổi tĩnh. Khi miền mở rộng, hệ thống có thể bổ sung đơn vị ghép, affine units, custom units và uncertainty theo nhu cầu đã xác định.

## Kết luận

Đơn vị đo là một phần quan trọng của hệ kiểu trong DSL khi ngôn ngữ xử lý đại lượng vật lý, thời gian, tiền tệ hoặc các quantity chuyên miền. Việc gắn đơn vị với kiểu giúp phân biệt các đại lượng, kiểm tra phép toán theo thứ nguyên, hỗ trợ chuyển đổi và ngăn nhiều lỗi mà kiểu số thông thường không phát hiện được.

Một thiết kế vững chắc cần phân biệt giá trị, đơn vị và thứ nguyên; xác định catalog và đơn vị chuẩn; quy định cú pháp literal; hỗ trợ phép toán và chuyển đổi phù hợp; xử lý các trường hợp đặc biệt như nhiệt độ, thời gian và tiền tệ; đồng thời bảo toàn thông tin qua frontend, runtime, API và lưu trữ.

Mức độ phức tạp nên tương xứng với miền. Dù DSL chỉ hỗ trợ một vài đơn vị cố định hay một hệ đơn vị mở rộng, các quy tắc phải rõ ràng và nhất quán để mỗi quantity luôn giữ đúng ý nghĩa từ lúc được viết đến khi được sử dụng.
