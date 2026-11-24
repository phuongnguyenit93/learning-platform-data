# Đơn vị cơ sở cho thời gian, kích thước và các đại lượng nghiệp vụ

## Định danh meter và đơn vị đo

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, ứng dụng Java dùng Micrometer để đo lường bằng counter, gauge, timer, distribution summary và các nhãn có kiểm soát. Khi định danh một meter, tên và tag cho biết đang đo đối tượng hay sự kiện nào; đơn vị cho biết giá trị được biểu diễn theo thang đo nào.

Một meter có tên rõ ràng nhưng không có quy ước đơn vị nhất quán vẫn có thể tạo ra dashboard sai. Ví dụ, một instance ghi độ trễ theo mili giây trong khi instance khác ghi theo giây. Backend có thể tổng hợp các giá trị đó thành một chuỗi dữ liệu hợp lệ về mặt kỹ thuật nhưng vô nghĩa về mặt vận hành. Tương tự, cộng kích thước theo byte với kích thước theo kilobyte hoặc cộng giá trị tiền tệ của nhiều loại tiền sẽ tạo ra kết quả sai nếu không có quy tắc quy đổi.

Vì vậy, mỗi meter cần có một hợp đồng đo lường tối thiểu:

- **Đại lượng:** thời gian, kích thước, số lượng, tỷ lệ hay giá trị nghiệp vụ nào đang được quan sát.
- **Đơn vị:** giây, byte, đơn hàng, sản phẩm, đồng tiền cụ thể hoặc một đại lượng không thứ nguyên.
- **Quy ước ghi nhận:** giá trị được chuẩn hóa trước khi ghi như thế nào.
- **Phạm vi tổng hợp:** các giá trị có thể được cộng, lấy trung bình hoặc so sánh trong cùng một nhóm hay không.
- **Cách hiển thị:** dashboard và truy vấn phải diễn giải đúng đơn vị và chuyển đổi sang cách hiển thị phù hợp.

Đơn vị không phải phần trang trí của tên metric. Nó là một phần ngữ nghĩa của số đo, cần được giữ nhất quán từ mã Java qua registry đến backend, truy vấn và dashboard.

## baseUnit trong Micrometer có ý nghĩa gì?

Micrometer cho phép mô tả đơn vị cơ sở của meter bằng metadata **baseUnit**. Metadata này giúp registry và hệ thống nhận dữ liệu hiểu đại lượng mà meter biểu diễn. Với các meter có giá trị do ứng dụng cung cấp như **Counter** hoặc **DistributionSummary**, có thể khai báo đơn vị khi xây dựng meter.

Ví dụ:

~~~java
Counter completedOrders = Counter.builder("commerce.orders.completed")
    .description("So don hang da hoan tat")
    .baseUnit("orders")
    .register(registry);
~~~

Tên meter mô tả sự kiện hoàn tất đơn hàng; đơn vị **orders** cho biết số đếm tương ứng với số đơn hàng. Mỗi lần một đơn hàng hoàn tất, ứng dụng gọi **increment()**.

Cần phân biệt hai khái niệm:

1. **Metadata đơn vị:** mô tả giá trị đang có đơn vị gì. **baseUnit("bytes")** khai báo rằng số được ghi nhận biểu diễn byte.
2. **Chuyển đổi giá trị:** thực hiện phép tính để đưa giá trị về đơn vị đã thống nhất. Khai báo **baseUnit("bytes")** tự nó không biến kilobyte thành byte, cũng không đổi mili giây thành giây.

Nếu ứng dụng ghi số 12 với metadata là **bytes**, backend hiểu số đo là 12 byte. Nếu ý định ban đầu là 12 KiB thì ứng dụng phải quy đổi thành 12 × 1024 byte trước khi ghi, hoặc dùng một cơ chế scale có chủ đích. Metadata không thể tự đoán đơn vị đầu vào.

Micrometer không bắt buộc mọi meter phải khai báo base unit. Tuy nhiên, với các đại lượng có đơn vị rõ ràng, nên cung cấp metadata nhất quán. Quy ước thông dụng là dùng tên đơn vị viết thường, dạng số nhiều và ưu tiên đơn vị SI khi phù hợp, chẳng hạn **seconds**, **bytes**, **requests** hoặc **items**. Với đại lượng nghiệp vụ, chọn từ ngữ ngắn gọn nhưng không mơ hồ.

## Đơn vị thời gian: dùng Timer cho thời lượng

### Timer và đơn vị thời gian của registry

**Timer** được thiết kế để đo thời lượng của một thao tác và số lần thao tác đó được ghi nhận. Đây là lựa chọn phù hợp cho thời gian xử lý HTTP request, truy vấn cơ sở dữ liệu, gọi dịch vụ bên ngoài, xử lý message hoặc chạy một bước nghiệp vụ.

Timer nhận thời lượng thông qua **java.time.Duration** hoặc một giá trị số đi kèm **TimeUnit**. Registry quyết định đơn vị thời gian cơ sở thích hợp khi xuất dữ liệu. Ví dụ, registry Prometheus thường biểu diễn thời gian theo giây; các registry khác cũng có thể chọn đơn vị xuất riêng theo backend.

Ví dụ:

~~~java
Timer paymentTimer = Timer.builder("checkout.payment.processing")
    .description("Thoi gian xu ly thanh toan")
    .publishPercentileHistogram()
    .register(registry);

paymentTimer.record(() -> paymentService.charge(command));
~~~

Cách ghi bằng lambda giúp Timer tự đo thời gian thực thi, kể cả khi thao tác ném exception. Nếu đã có một giá trị thời lượng, có thể ghi trực tiếp:

~~~java
paymentTimer.record(Duration.ofMillis(250));
paymentTimer.record(150, TimeUnit.MILLISECONDS);
~~~

Cả hai cách đều biểu diễn cùng một đại lượng thời gian. Timer xử lý việc chuyển đổi sang đơn vị mà registry sử dụng khi xuất dữ liệu.

Khi đọc các phép đo Timer qua API, cần truyền đơn vị mong muốn cho những phương thức trả về giá trị thời gian, chẳng hạn **totalTime(TimeUnit.SECONDS)** hoặc **mean(TimeUnit.MILLISECONDS)**. Không nên so sánh các giá trị lấy từ những đơn vị khác nhau mà không chuyển chúng về cùng một thang đo.

### Không tự trộn giây, mili giây và nano giây

Một lỗi thường gặp là ghi trực tiếp số thời gian mà không xác định đơn vị:

~~~java
// Gia tri nay la 250 mili giay, khong phai 250 giay.
paymentTimer.record(250, TimeUnit.MILLISECONDS);
~~~

Nếu bỏ qua **TimeUnit** và coi số 250 là giây, độ trễ sẽ bị phóng đại 1.000 lần so với ý định. Tương tự, nhầm nano giây với mili giây có thể tạo ra sai lệch rất lớn.

Nên ưu tiên **Duration** khi dữ liệu thời lượng đã có kiểu dữ liệu này, vì đơn vị được gắn ngay trong giá trị. Khi dùng overload nhận số, luôn truyền **TimeUnit** tường minh. Không tự chuyển đổi thời lượng sang một số thực rồi ghi bằng Timer nếu không có lý do cụ thể.

Không cần đặt tên meter thành **checkout.payment.processing.milliseconds** chỉ để nhắc rằng đây là thời gian. Timer vốn đã mang ngữ nghĩa thời lượng và registry sẽ chọn đơn vị xuất. Đơn vị trong tên có thể khiến người đọc hiểu nhầm rằng mọi backend đều xuất cùng đơn vị hoặc gây trùng lặp khi quy ước đặt tên tự thêm hậu tố.

### Timer, percentile và SLO

Các ngưỡng phân phối của Timer cũng phải dùng cùng ngữ nghĩa thời gian. Ví dụ, **serviceLevelObjectives(Duration.ofMillis(100), Duration.ofMillis(300))** thể hiện ngưỡng 100 ms và 300 ms. Micrometer chuyển các giá trị Duration theo cách phù hợp với registry.

Nếu cấu hình percentile histogram, hãy kiểm tra dashboard và truy vấn hiểu đúng đơn vị thời gian backend xuất. Một biểu đồ hiển thị 0.25 giây và một biểu đồ hiển thị 250 mili giây có thể mô tả cùng độ trễ, nhưng phép so sánh hoặc ngưỡng cảnh báo phải được viết theo đúng đơn vị của dữ liệu tương ứng.

Timer phù hợp với thời lượng đã trôi qua. Nếu muốn theo dõi một đại lượng thời gian tức thời, chẳng hạn thời điểm hoặc tuổi của một trạng thái, cần chọn meter phù hợp với ngữ nghĩa đó; không dùng Counter để lưu thời gian xử lý.

## Đơn vị kích thước: chuẩn hóa về byte

### Byte là đơn vị cơ sở thực tế cho kích thước

Kích thước request, response, file, payload, bộ đệm và dữ liệu truyền qua mạng thường được biểu diễn bằng byte. Đối với các đại lượng này, nên thống nhất ghi nhận bằng **bytes** để các giá trị có thể so sánh và tổng hợp nhất quán.

**DistributionSummary** phù hợp để ghi nhận phân phối kích thước, chẳng hạn kích thước request body. Ví dụ:

~~~java
DistributionSummary requestPayloadSize = DistributionSummary
    .builder("http.request.payload.size")
    .description("Kich thuoc request payload")
    .baseUnit("bytes")
    .register(registry);

requestPayloadSize.record(requestBody.length);
~~~

Với mảng byte, **length** đã là số byte. Nếu kích thước được lấy từ thư viện khác, hãy kiểm tra API trả về byte, kilobyte hay một đơn vị khác trước khi ghi.

DistributionSummary có thể cung cấp count, tổng giá trị và thống kê phân phối. Do đó, ngoài kích thước trung bình, hệ thống còn có thể phân tích kích thước lớn, phân vị hoặc số quan sát vượt các ngưỡng đã cấu hình nếu backend hỗ trợ histogram tương ứng.

### Phân biệt kB và KiB

Hai cách ghi kích thước thường bị nhầm lẫn:

| Đơn vị | Hệ số quy đổi | Ví dụ |
|---|---:|---:|
| byte (B) | 1 | 1 B = 1 byte |
| kilobyte (kB) | 1.000 byte | 1 kB = 1.000 B |
| kibibyte (KiB) | 1.024 byte | 1 KiB = 1.024 B |
| megabyte (MB) | 1.000.000 byte | 1 MB = 1.000.000 B |
| mebibyte (MiB) | 1.048.576 byte | 1 MiB = 1.048.576 B |

Nếu một thư viện trả về 4 KiB, giá trị chuẩn hóa phải là 4.096 byte. Nếu một hệ thống trả về 4 kB theo hệ thập phân, giá trị chuẩn hóa là 4.000 byte. Chênh lệch có thể nhỏ ở dữ liệu đơn lẻ nhưng sẽ tích lũy trong báo cáo lưu lượng hoặc dung lượng.

Ví dụ chuyển đổi rõ ràng trước khi ghi:

~~~java
long payloadSizeInBytes = payloadSizeInKiB * 1024L;
requestPayloadSize.record(payloadSizeInBytes);
~~~

Cần đặt tên biến thể hiện đơn vị của dữ liệu đầu vào để tránh nhân hoặc chia nhầm hệ số. Không ghi số KiB vào meter có base unit là **bytes** rồi kỳ vọng backend tự quy đổi.

### Histogram kích thước cũng dùng byte

Nếu muốn theo dõi ngưỡng kích thước request, các ngưỡng cần dùng cùng đơn vị với giá trị ghi nhận. Ví dụ, nếu dữ liệu được ghi theo byte, các ranh giới 1 KiB, 4 KiB và 16 KiB tương ứng 1.024, 4.096 và 16.384 byte.

Khi so sánh các instance hoặc dịch vụ, cần giữ cấu hình ngưỡng thống nhất. Histogram được tổng hợp từ các bucket khác nhau có thể không cho kết quả tương đương. Ngoài ra, số lượng bucket và số chuỗi dữ liệu tăng sẽ ảnh hưởng cardinality, dung lượng lưu trữ và chi phí truy vấn.

## Đơn vị cho các đại lượng nghiệp vụ

Không phải số đo nào cũng là thời gian hoặc kích thước. Các chỉ số vận hành thường biểu diễn số lượng, tiền tệ, tỷ lệ hoặc đại lượng riêng của miền nghiệp vụ. Đơn vị phải mô tả chính xác điều mà con số đại diện.

### Số lượng sự kiện và đối tượng

Với số lần một sự kiện xảy ra, dùng **Counter**. Ví dụ, số đơn hàng hoàn tất có đơn vị **orders**; số message được xử lý có đơn vị **messages**. Mỗi sự kiện làm bộ đếm tăng:

~~~java
Counter completedOrders = Counter.builder("commerce.orders.completed")
    .description("So don hang da hoan tat")
    .baseUnit("orders")
    .register(registry);

completedOrders.increment();
~~~

Counter phù hợp với số đếm tích lũy. Nếu cần biết hiện tại có bao nhiêu đơn hàng đang chờ xử lý, đó là trạng thái tức thời và thường phù hợp với **Gauge**. Nếu muốn biết một đơn hàng có bao nhiêu sản phẩm, cần phân phối số lượng sản phẩm trên từng đơn hàng; **DistributionSummary** có thể ghi nhận đại lượng đó với đơn vị **items**.

Không nên dùng cùng một meter để biểu diễn cả số sự kiện tích lũy và số đối tượng đang tồn tại. Dù cả hai đều là số nguyên, chúng có ý nghĩa vận hành khác nhau.

Tốc độ như requests/second thường được tính từ Counter theo cửa sổ thời gian ở backend. Counter lưu tổng số request; phép truy vấn rate tạo ra số request mỗi giây. Không ghi giá trị tốc độ vào một Counter vốn được định nghĩa là tổng số sự kiện, rồi tiếp tục tính rate lần nữa.

### Tiền tệ và giá trị giao dịch

Giá trị giao dịch là một đại lượng có đơn vị tiền tệ. 100.000 VND và 100 USD không thể cộng trực tiếp hoặc so sánh như cùng một thang đo.

Có hai cách thiết kế phổ biến:

- Ghi nhận từng loại tiền bằng meter có đơn vị cố định tương ứng, chẳng hạn VND hoặc USD. Chỉ tổng hợp các giá trị cùng loại tiền.
- Nếu nghiệp vụ yêu cầu báo cáo theo một đồng tiền chuẩn, thực hiện quy đổi theo chính sách tỷ giá được xác định rõ trước khi ghi nhận. Quy tắc cần nêu rõ nguồn tỷ giá, thời điểm áp dụng và cách xử lý giao dịch điều chỉnh.

Không nên khai báo một meter có base unit là **USD** rồi ghi cả số tiền VND vào đó. Cũng không nên chỉ thêm tag currency rồi cộng tất cả giá trị thành một tổng duy nhất. Tag có thể phân tách dữ liệu để truy vấn, nhưng không tự thực hiện chuyển đổi tiền tệ.

Nếu dùng tag **currency**, tập giá trị cần được kiểm soát và dashboard phải nhóm hoặc lọc theo từng loại tiền. Với các báo cáo có yêu cầu kế toán hoặc đối soát, metrics chỉ nên đóng vai trò giám sát tổng quan; hệ thống giao dịch hoặc dữ liệu tài chính chuyên biệt vẫn là nguồn số liệu chính xác để đối soát.

### Tỷ lệ, phần trăm và đại lượng không thứ nguyên

Tỷ lệ lỗi, tỷ lệ thành công, mức sử dụng tài nguyên hoặc tỷ lệ cache hit là những đại lượng không thứ nguyên. Để tránh nhầm lẫn, nên chọn một quy ước cố định:

- Ghi tỷ lệ trong khoảng 0 đến 1, ví dụ 0,025 biểu diễn 2,5%.
- Dashboard định dạng giá trị thành phần trăm khi hiển thị.
- Nếu hệ thống chọn lưu giá trị 0 đến 100, phải ghi rõ quy ước và giữ nhất quán ở tất cả instance.

Không trộn 0,025 và 2,5 trong cùng một meter. Một backend hoặc dashboard có thể tự định dạng tỷ lệ thành phần trăm; việc ứng dụng nhân thêm 100 mà không thống nhất sẽ làm kết quả hiển thị lớn gấp 100 lần.

Đối với tỷ lệ được tính từ hai bộ đếm, thường nên giữ các số đếm gốc và tính tỷ lệ ở truy vấn. Ví dụ, tỷ lệ lỗi có thể được tính bằng số request thất bại chia cho tổng số request trong cùng cửa sổ thời gian. Cách này giúp người vận hành xem được cả tử số, mẫu số và tỷ lệ, đồng thời tránh mất thông tin khi chỉ ghi một giá trị phần trăm đã tính sẵn.

## Chọn meter và đơn vị theo ý nghĩa số đo

Bảng sau gợi ý cách kết hợp đại lượng, meter và đơn vị:

| Nhu cầu quan sát | Meter phù hợp | Đơn vị cơ sở gợi ý | Cách diễn giải |
|---|---|---|---|
| Thời gian xử lý request | Timer | Do registry chọn đơn vị thời gian, thường là seconds khi xuất Prometheus | Tổng thời gian, số lần, phân phối và phân vị |
| Kích thước payload | DistributionSummary | bytes | Phân phối kích thước và tổng byte đã ghi nhận |
| Số đơn hàng hoàn tất | Counter | orders | Tổng số sự kiện hoàn tất |
| Số message đang chờ | Gauge | messages | Trạng thái hiện tại tại thời điểm thu thập |
| Số sản phẩm trong mỗi đơn hàng | DistributionSummary | items | Phân phối số sản phẩm trên mỗi đơn hàng |
| Giá trị đơn hàng | DistributionSummary | Đơn vị tiền tệ cụ thể | Phân phối giá trị giao dịch cùng loại tiền |
| Tỷ lệ request thất bại | Giá trị tính từ Counter hoặc Gauge phù hợp | ratio | Tỷ lệ giữa số lỗi và tổng số request |

Chọn meter theo hành vi của đại lượng trước, rồi mới xác định đơn vị. Counter là số đếm tích lũy, Gauge là giá trị trạng thái, Timer là thời lượng, DistributionSummary là phân phối các giá trị số. Không nên chọn meter chỉ vì nó nhận được kiểu dữ liệu số mà bỏ qua ngữ nghĩa.

## Đặt đơn vị trong mã Micrometer

### Khai báo metadata tại nơi tạo meter

Đơn vị nên được khai báo ở nơi meter được xây dựng, để người đọc có thể hiểu ý nghĩa của phép đo ngay tại instrumentation:

~~~java
DistributionSummary responseSize = DistributionSummary
    .builder("http.response.size")
    .description("Kich thuoc response")
    .baseUnit("bytes")
    .register(registry);
~~~

Đơn vị phải khớp với giá trị truyền vào **record()**. Nếu nguồn dữ liệu dùng KiB, chuyển đổi về byte trước khi ghi hoặc xây dựng một meter riêng với đơn vị được xác định rõ. Không thay đổi ý nghĩa của cùng một meter theo từng request.

Đối với Timer, đơn vị thời gian được xử lý theo API Timer và registry. Không cần khai báo một base unit tùy ý cho Timer. Hãy ghi Duration hoặc số kèm TimeUnit, sau đó xác minh đơn vị mà backend xuất.

### Dùng scale khi thực sự cần

Một số builder của meter phân phối hỗ trợ scale để nhân giá trị trước khi ghi nhận. Đây là công cụ chuyển thang đo, nhưng phải được dùng có chủ đích và tài liệu hóa rõ ràng.

Ví dụ, nếu nguồn dữ liệu luôn trả về KiB và muốn lưu giá trị theo byte, có thể chuẩn hóa trực tiếp trước khi gọi **record()**. Cách chuyển đổi tường minh này thường dễ đọc và dễ kiểm thử. Nếu dùng scale, hãy kiểm tra API của meter và registry đang dùng, đồng thời xác nhận histogram, SLO và giá trị truy vấn đều được hiểu theo đơn vị sau scale.

Không dùng scale để che giấu việc nguồn dữ liệu không thống nhất. Nếu một phần request trả byte và phần khác trả KiB, cần chuẩn hóa từng nguồn trước khi ghi; một hệ số cố định không thể sửa dữ liệu đầu vào có đơn vị thay đổi.

### Tên meter và base unit cần bổ trợ cho nhau

Tên meter nên mô tả sự kiện hoặc đại lượng; base unit mô tả thang đo. Ví dụ **http.request.payload.size** cùng base unit **bytes** dễ hiểu hơn một tên mơ hồ như **http.request.value**. Tuy nhiên, không nên lặp đơn vị trong tên nếu naming convention của registry đã thêm hậu tố đơn vị khi xuất.

Micrometer registry có thể chuyển tên meter theo quy ước của backend. Với Prometheus, tên Timer thường được biểu diễn theo giây và có hậu tố tương ứng. Các registry khác có thể dùng metadata hoặc quy ước tên khác. Vì vậy:

- Không giả định tên metric được xuất giống hệt tên trong Java.
- Kiểm tra quy tắc chuẩn hóa tên và hậu tố đơn vị của registry.
- Xác nhận backend có giữ metadata đơn vị hay không.
- Viết truy vấn theo đơn vị và tên thực tế ở backend.
- Khi chuyển backend, kiểm tra lại dashboard và alert thay vì chỉ thay endpoint xuất dữ liệu.

## Giữ đơn vị nhất quán qua tag và các instance

Một meter thường có nhiều time series do các tag như service, environment, region hoặc outcome. Các giá trị thuộc cùng một meter cần dùng chung đơn vị. Không đưa đơn vị vào tag để một số series ghi giây và số khác ghi mili giây. Làm như vậy sẽ biến một lỗi hợp đồng đo lường thành nhiều series khó tổng hợp.

Nếu hai nguồn có đơn vị đầu vào khác nhau nhưng cùng đại lượng, hãy chuyển đổi về đơn vị chung trước khi ghi. Ví dụ, một client cung cấp thời gian theo Duration, client khác cung cấp số mili giây; cả hai phải được chuyển thành thời lượng hợp lệ trước khi ghi vào cùng Timer.

Tag cũng cần có cardinality được kiểm soát. Các giá trị như **currency**, **region** hoặc **payment_method** chỉ nên dùng khi tập giá trị hữu hạn và có ý nghĩa truy vấn. Không dùng customer ID, order ID hay giá trị định danh duy nhất làm tag chỉ để phân biệt số đo. Nếu cần tra cứu một giao dịch cụ thể, log hoặc trace phù hợp hơn.

Trong môi trường nhiều instance, cấu hình meter, đơn vị, tên và bucket phải đồng nhất. Nếu một instance ghi bytes còn instance khác ghi KiB, backend vẫn có thể nhóm chúng dưới cùng tên và tag; kết quả tổng hợp sẽ sai mà không nhất thiết phát sinh lỗi kỹ thuật.

## Kiểm thử hợp đồng đơn vị

Kiểm thử instrumentation nên xác nhận cả meter được tạo đúng lẫn giá trị ghi nhận có đúng đơn vị.

Ví dụ với DistributionSummary:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

DistributionSummary payloadSize = DistributionSummary
    .builder("http.request.payload.size")
    .baseUnit("bytes")
    .register(registry);

payloadSize.record(4096);

assertThat(registry.get("http.request.payload.size")
    .summary()
    .totalAmount()).isEqualTo(4096.0);
~~~

Kiểm thử trên xác nhận ứng dụng ghi nhận 4.096 đơn vị theo quy ước byte của meter. Nó không chứng minh exporter sẽ đặt tên hoặc hiển thị đơn vị giống nhau trên mọi backend.

Với Timer, nên kiểm tra giá trị bằng cách yêu cầu một TimeUnit cụ thể khi đọc:

~~~java
Timer timer = registry.timer("checkout.payment.processing");
timer.record(250, TimeUnit.MILLISECONDS);

assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
    .isEqualTo(250.0);
~~~

Trong kiểm thử tích hợp exporter, hãy kiểm tra payload thực tế để xác nhận tên sau NamingConvention, đơn vị xuất, metadata và cách biểu diễn histogram. Một bộ kiểm thử tốt nên có các trường hợp chuyển đổi từ đơn vị đầu vào, ví dụ 250 ms, 2 KiB, 4 kB, cũng như các đại lượng nghiệp vụ như 3 items hoặc 125.000 VND. Các trường hợp này giúp phát hiện nhầm hệ số và nhầm đơn vị trước khi dữ liệu đến dashboard.

## Checklist khi thiết kế meter mới

Trước khi đưa meter vào vận hành, hãy xác minh:

1. Đại lượng đang đo có được mô tả rõ trong tên và description không?
2. Đơn vị cơ sở đã được chọn và khai báo khi phù hợp chưa?
3. Giá trị đầu vào đang ở đơn vị nào? Có cần quy đổi trước khi ghi không?
4. Các instance và các nhánh xử lý có dùng cùng một quy ước không?
5. Histogram, percentile và SLO có dùng cùng đơn vị với giá trị đã ghi không?
6. Backend có chuyển đổi tên hoặc đơn vị khi xuất không?
7. Dashboard và alert có diễn giải đúng đơn vị không?
8. Các đại lượng có thể tổng hợp với nhau thực sự cùng đơn vị và cùng ý nghĩa không?
9. Đối với tiền tệ hoặc tỷ lệ, chính sách quy đổi và định dạng đã được xác định chưa?
10. Kiểm thử có xác nhận cả giá trị ở Micrometer lẫn dữ liệu sau khi xuất không?

## Những sai lầm thường gặp

**Khai báo baseUnit nhưng không quy đổi dữ liệu.** Metadata chỉ mô tả đơn vị. Nếu đầu vào là KiB, cần chuyển đổi sang byte trước khi ghi vào meter có base unit là bytes.

**Ghi thời lượng bằng số không có TimeUnit.** Một số 250 không thể hiện rõ là giây hay mili giây. Dùng Duration hoặc truyền TimeUnit tường minh cho Timer.

**Trộn byte, kB và KiB.** Các hệ số thập phân và nhị phân khác nhau. Chuẩn hóa về byte và đặt tên biến thể hiện đơn vị đầu vào.

**Cộng giá trị tiền tệ khác nhau.** Cần giữ từng loại tiền riêng hoặc quy đổi theo chính sách tỷ giá đã xác định.

**Lưu phần trăm không nhất quán.** Không trộn tỷ lệ 0 đến 1 với giá trị 0 đến 100 trong cùng một meter. Nên giữ ratio và định dạng phần trăm ở lớp hiển thị.

**Dùng Counter cho trạng thái hiện tại.** Counter là số đếm tích lũy; Gauge phù hợp hơn với số lượng đang chờ hoặc đang hoạt động tại thời điểm quan sát.

**Chỉ kiểm tra ở SimpleMeterRegistry.** Kiểm thử cục bộ không xác nhận naming convention, metadata hoặc đơn vị thực tế của backend. Cần kiểm tra thêm đầu ra exporter.

## Kết luận

Đơn vị cơ sở giúp số đo Micrometer giữ được ý nghĩa khi đi qua registry, backend, truy vấn và dashboard. Timer cần được ghi bằng Duration hoặc TimeUnit tường minh; kích thước nên được chuẩn hóa về byte; các đại lượng nghiệp vụ cần đơn vị riêng, rõ ràng và có thể tổng hợp đúng.

Hãy coi đơn vị là một phần của hợp đồng instrumentation. Khai báo metadata phù hợp, chuyển đổi giá trị đầu vào một cách tường minh, giữ cấu hình thống nhất giữa các instance và kiểm thử dữ liệu sau khi xuất. Khi tên, đơn vị và ý nghĩa được giữ ổn định, metrics mới có thể hỗ trợ so sánh, cảnh báo và phân tích vận hành đáng tin cậy.
