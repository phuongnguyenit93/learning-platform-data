# Nguồn không thể giảm tốc và giới hạn của áp lực ngược

Backpressure cho phép consumer thông báo lượng dữ liệu mà nó sẵn sàng nhận, từ đó giúp publisher điều tiết tốc độ phát. Cơ chế này hoạt động tốt khi nguồn dữ liệu có khả năng hợp tác: nó có thể chờ demand, tạm dừng đọc, giảm tốc hoặc chỉ lấy thêm dữ liệu khi subscriber yêu cầu. Nhưng nhiều nguồn bên ngoài không có khả năng đó. Cảm biến, callback từ thư viện, sự kiện giao diện, datagram UDP hoặc thiết bị gửi dữ liệu theo nhịp riêng vẫn có thể phát phần tử dù consumer đang bận.

Trong trường hợp nguồn không thể giảm tốc, demand của Reactive Streams không làm cho dữ liệu ngừng xuất hiện ở bên ngoài. Adapter phải quyết định sẽ giữ dữ liệu trong bộ nhớ, bỏ một phần tử, giữ giá trị mới nhất, lấy mẫu, báo lỗi quá tải hay ghi dữ liệu vào một hệ thống lưu trữ có khả năng tiếp nhận. Mỗi lựa chọn có ý nghĩa khác nhau đối với nghiệp vụ. Không có một chính sách backpressure nào vừa bảo đảm giữ mọi phần tử, dùng bộ nhớ hữu hạn, vừa chấp nhận nguồn phát nhanh hơn consumer vô thời hạn.

## 1. Backpressure chỉ điều tiết được nguồn có thể hợp tác

Trong hợp đồng Reactive Streams, subscriber gửi demand qua `Subscription.request(n)`. Publisher có thể dùng demand để quyết định khi nào lấy hoặc phát thêm phần tử. Ví dụ, một publisher đọc file theo từng khối có thể chỉ đọc khối tiếp theo sau khi downstream yêu cầu; một driver database reactive có thể lấy thêm hàng khi cần; một message broker có thể giảm số message đang được giao hoặc tạm dừng consumer.

Những nguồn này có thể điều chỉnh hành vi dựa trên nhu cầu của downstream. Khi consumer chậm, demand giảm hoặc tạm thời bằng không, nguồn có thể chờ mà không tạo thêm dữ liệu trong bộ nhớ của adapter.

Ngược lại, một nguồn push không có giao thức demand có thể gọi callback bất cứ lúc nào:

```java
sensor.addListener(reading -> process(reading));
```

Thiết bị cảm biến quyết định lúc nào phát `reading`. Consumer không thể gọi `request(1)` trên API này nếu API không cung cấp phương thức tương ứng. Việc bọc callback vào `Flux` giúp tích hợp với Reactor, nhưng không tự bổ sung khả năng điều khiển tốc độ cho cảm biến.

Có thể chia nguồn thành ba nhóm để chọn chiến lược:

| Loại nguồn | Khả năng điều tiết | Ví dụ | Hướng xử lý |
| --- | --- | --- | --- |
| Pull hoặc demand-aware | Có thể chờ và chỉ đọc khi có nhu cầu | Đọc file theo khối, driver reactive, API có credit | Truyền demand về nguồn và giới hạn số phần tử yêu cầu |
| Push có thể tạm dừng | Có thể pause/resume hoặc giảm tốc ở một mức nào đó | Một số message consumer, socket reader, SDK có flow control | Nối demand với pause/resume, prefetch hoặc credit của nguồn |
| Push không thể giảm tốc | Tiếp tục phát theo nhịp bên ngoài | Cảm biến, callback không có flow control, UDP telemetry | Chọn buffer hữu hạn, drop/latest, sampling, báo lỗi hoặc lưu bền |

Khả năng thực tế phụ thuộc API và giao thức của nguồn. Một message broker có thể hỗ trợ prefetch hoặc acknowledgement nhưng vẫn có giới hạn về tốc độ producer; một socket có thể chịu ảnh hưởng của TCP flow control nhưng callback trong ứng dụng vẫn có thể đẩy dữ liệu nhanh hơn phần xử lý. Cần xác định ranh giới nào thật sự có thể điều tiết.

## 2. Khi tốc độ đến lớn hơn tốc độ xử lý

Gọi:

- \(\lambda\): tốc độ dữ liệu đến, tính bằng phần tử mỗi giây.
- \(\mu\): tốc độ consumer xử lý, tính bằng phần tử mỗi giây.
- \(B\): số phần tử tối đa có thể giữ trong buffer.

Nếu trung bình \(\lambda < \mu\), consumer có khả năng xử lý nhanh hơn tốc độ đến trong dài hạn. Buffer vẫn cần thiết để hấp thụ burst ngắn, nhưng có cơ hội trở về mức thấp sau khi burst kết thúc.

Nếu \(\lambda > \mu\) liên tục, hàng đợi tăng xấp xỉ theo tốc độ chênh lệch:

\[
\text{Tốc độ tăng hàng đợi} \approx \lambda - \mu
\]

Nếu buffer ban đầu gần rỗng và tốc độ không đổi, thời gian gần đúng để đầy là:

\[
T_{\text{đầy}} \approx \frac{B}{\lambda - \mu}
\]

Ví dụ, nguồn gửi 8.000 sự kiện/giây, consumer xử lý 5.000 sự kiện/giây và buffer có sức chứa 60.000 phần tử. Chênh lệch là 3.000 phần tử/giây, nên buffer có thể đầy sau khoảng 20 giây nếu tải giữ nguyên và chưa tính chi phí xử lý khác.

| Thời gian | Phần tử đang chờ |
| ---: | ---: |
| 0 giây | 0 |
| 5 giây | 15.000 |
| 10 giây | 30.000 |
| 15 giây | 45.000 |
| 20 giây | 60.000 |

Đây là mô hình đơn giản với tốc độ đến và xử lý không đổi. Hệ thống thật có burst, độ trễ, nhiều consumer, giới hạn bộ nhớ và chi phí serialize. Tuy nhiên, kết luận cốt lõi vẫn đúng: nếu dữ liệu đến nhanh hơn khả năng xử lý trong thời gian dài và nguồn không thể giảm tốc, buffer hữu hạn cuối cùng sẽ đầy. Tăng buffer chỉ kéo dài thời gian trước khi quá tải; nó không giải quyết chênh lệch tốc độ lâu dài.

## 3. Những lựa chọn khi nguồn không thể giảm tốc

Khi nguồn không hỗ trợ demand, adapter cần một chính sách rõ ràng tại ranh giới nhận dữ liệu. Các lựa chọn phổ biến gồm:

| Chiến lược | Hành vi khi consumer chậm | Phù hợp khi | Đánh đổi |
| --- | --- | --- | --- |
| Buffer không giới hạn | Giữ mọi phần tử đang chờ | Chỉ nguồn hữu hạn, kích thước đã được kiểm soát | Có thể làm cạn heap nếu nguồn lớn hoặc liên tục |
| Buffer có giới hạn | Giữ phần tử đến khi đầy; khi vượt giới hạn thì báo lỗi hoặc áp dụng overflow policy | Cần giữ dữ liệu trong burst có giới hạn | Khi đầy phải có quyết định rõ: fail, drop hoặc xử lý khác |
| Drop | Bỏ phần tử mới đến khi downstream chưa sẵn sàng | Sự kiện có thể mất mà không làm sai trạng thái | Mất dữ liệu; cần metric và quy tắc nghiệp vụ cho phép |
| Latest | Chỉ giữ giá trị mới nhất đang chờ | Dữ liệu biểu diễn trạng thái hiện tại | Bỏ các trạng thái trung gian |
| Sampling/throttling | Chỉ lấy một phần dữ liệu theo thời gian hoặc điều kiện | Telemetry, biểu đồ hoặc giám sát xu hướng | Có thể bỏ đỉnh ngắn hoặc sự kiện thoáng qua |
| Gộp/batch | Kết hợp nhiều phần tử thành một đơn vị xử lý | Có thể cộng dồn, đếm hoặc gom theo khóa | Cần định nghĩa phép gộp có bảo toàn ý nghĩa không |
| Lưu bền và xử lý sau | Đưa dữ liệu vào log/broker/storage rồi tiêu thụ theo tốc độ phù hợp | Cần giữ sự kiện và chấp nhận độ trễ | Thêm hạ tầng, retention, offset và vận hành |
| Báo quá tải | Từ chối hoặc kết thúc luồng khi vượt khả năng | Không thể tiếp tục với dữ liệu thiếu hoặc trễ | Cần cơ chế phục hồi, retry hoặc cảnh báo ở cấp hệ thống |

Không có chiến lược nào đúng cho mọi loại dữ liệu. Với số đo nhiệt độ, giữ giá trị mới nhất có thể phù hợp. Với giao dịch tài chính, bỏ một sự kiện thanh toán thường không thể chấp nhận. Với telemetry dùng cho biểu đồ xu hướng, sampling có thể đủ; với hệ thống phát hiện mọi lần vượt ngưỡng, sampling thưa có thể bỏ lỡ sự kiện quan trọng.

## 4. Buffer có giới hạn: hấp thụ burst nhưng phải định nghĩa overflow

Buffer hữu ích khi nguồn có burst ngắn và consumer có thể bắt kịp sau đó. Tuy nhiên, buffer phải có giới hạn dựa trên ngân sách bộ nhớ và thời gian chờ tối đa mà nghiệp vụ chấp nhận.

Trong Reactor, `onBackpressureBuffer(maxSize)` có thể đặt giới hạn số phần tử được giữ khi downstream chưa yêu cầu đủ. Khi vượt giới hạn, pipeline kết thúc bằng lỗi overflow. Ví dụ:

```java
Flux<SensorReading> readings = sensorEvents()
    .onBackpressureBuffer(10_000);
```

Đoạn mã đặt sức chứa tối đa 10.000 phần tử trong buffer của toán tử. Đây là cách hấp thụ burst; nó không làm chậm cảm biến. Khi buffer đầy, lỗi overflow báo rằng hệ thống không thể tiếp tục giữ toàn bộ dữ liệu theo cấu hình này.

Buffer nên được tính theo kích thước phần tử và ngân sách bộ nhớ, không chỉ theo số lượng. Nếu mỗi phần tử giữ một payload lớn hoặc tham chiếu đến object graph, 10.000 phần tử có thể chiếm nhiều heap hơn dự kiến. Cũng cần tính cả queue của client, scheduler, broker, serialization và các tầng khác; một buffer giới hạn riêng lẻ không đồng nghĩa tổng bộ nhớ toàn hệ thống đã được giới hạn.

Không nên dùng buffer vô hạn để che giấu consumer chậm. Khi nguồn liên tục và \(\lambda > \mu\), bộ nhớ sẽ tăng theo thời gian cho đến khi process gặp sự cố hoặc bị hệ điều hành giới hạn. Nếu cần giữ toàn bộ sự kiện, hãy chuyển chúng vào một hệ thống lưu bền có dung lượng và retention được quản lý.

## 5. Drop: bỏ phần tử mới khi consumer không có demand

Nếu nghiệp vụ cho phép bỏ dữ liệu đến trong lúc downstream chưa sẵn sàng, `onBackpressureDrop` có thể loại bỏ phần tử đó. Có thể truyền callback để đếm hoặc ghi nhận phần tử bị bỏ:

```java
Flux<SensorReading> readings = sensorEvents()
    .onBackpressureDrop(dropped ->
        metrics.increment("sensor.reading.dropped"));
```

Toán tử không làm nguồn giảm tốc; nó nhận dữ liệu từ upstream và bỏ những phần tử không thể chuyển tiếp theo demand hiện tại. Callback drop giúp quan sát số lượng bị bỏ. Trong ứng dụng, nên tránh ghi log từng phần tử bị drop nếu tốc độ rất cao; metric tổng hợp thường ít gây áp lực bổ sung hơn.

Drop phù hợp khi dữ liệu là mẫu độc lập và mất một số mẫu không làm sai kết quả tổng thể. Nó không phù hợp nếu mỗi phần tử biểu diễn một lệnh, giao dịch hoặc chuyển trạng thái bắt buộc. Nếu bỏ dữ liệu, cần nói rõ điều đó trong hợp đồng của hệ thống và đo tỷ lệ mất.

## 6. Latest: giữ giá trị gần nhất thay cho hàng đợi lịch sử

Với dữ liệu trạng thái, consumer đôi khi chỉ cần giá trị mới nhất. `onBackpressureLatest()` giữ phần tử gần nhất đang chờ và thay thế giá trị cũ nếu có giá trị mới đến trước khi downstream sẵn sàng:

```java
Flux<Temperature> currentTemperature = sensorEvents()
    .onBackpressureLatest();
```

Giả sử consumer đang bận và nguồn lần lượt phát `21.0`, `21.2`, `21.4`, `21.7`. Khi consumer sẵn sàng nhận lại, nó có thể nhận giá trị mới nhất đang chờ là `21.7`; các giá trị trung gian đã bị thay thế. Điều này phù hợp với màn hình hiển thị nhiệt độ hiện tại, vị trí mới nhất hoặc trạng thái pin mới nhất.

Latest không phù hợp với dữ liệu mà từng chuyển đổi đều quan trọng. Nếu một thiết bị chuyển từ “bình thường” sang “quá nhiệt” rồi trở lại “bình thường” trong lúc consumer bận, chỉ giữ giá trị mới nhất có thể khiến consumer bỏ lỡ trạng thái quá nhiệt. Hãy chọn chính sách dựa trên ý nghĩa dữ liệu, không chỉ dựa trên hiệu năng.

## 7. Sampling và gộp dữ liệu

Sampling giảm lượng dữ liệu bằng cách lấy mẫu theo chu kỳ hoặc điều kiện. Ví dụ, dashboard có thể chỉ cần một điểm dữ liệu mỗi 200 mili giây:

```java
Flux<SensorReading> chartReadings = sensorEvents()
    .sample(Duration.ofMillis(200));
```

`sample` giảm tần suất giá trị downstream nhận được, nhưng nó không làm nguồn vật lý ngừng phát. Nếu callback vẫn đến rất nhanh, nguồn và đoạn adapter trước toán tử vẫn phải tiếp nhận các callback đó. Vì vậy, sampling ở downstream không tự giải quyết mọi áp lực tại ranh giới nguồn; cần cân nhắc nơi đặt sampling và khả năng xử lý callback đầu vào.

Một lựa chọn khác là gộp nhiều phần tử thành một kết quả. Ví dụ, thay vì lưu từng số đo, hệ thống có thể tính min, max, sum và count theo cửa sổ thời gian. Cách này giữ được thông tin tổng hợp nhưng làm mất chuỗi chi tiết ban đầu. Phép gộp cần được xác định theo yêu cầu phân tích và khả năng tái dựng dữ liệu.

Với dữ liệu sự kiện có thể cộng dồn, batching có thể giảm overhead gọi downstream hoặc ghi database. Nhưng batch lớn làm tăng độ trễ và bộ nhớ; batch nhỏ tăng số lần I/O. Cần đo cả throughput lẫn latency để chọn kích thước phù hợp.

## 8. Báo lỗi khi vượt khả năng tiếp nhận

Nếu dữ liệu bị mất không thể chấp nhận và cũng không có nơi lưu bền, kết thúc pipeline bằng lỗi có thể an toàn hơn việc âm thầm bỏ phần tử. `onBackpressureError()` chuyển tình trạng thiếu demand thành lỗi thay vì tiếp tục giữ dữ liệu:

```java
Flux<PaymentEvent> payments = paymentCallbacks()
    .onBackpressureError()
    .doOnError(error -> alertOperations("Payment stream overloaded", error));
```

Ví dụ minh họa một chính sách fail-fast. Khi consumer không thể tiếp nhận phần tử theo demand, pipeline phát lỗi overflow; ứng dụng cần có cơ chế giám sát và phục hồi. Lỗi overflow không tự động làm cho nguồn bên ngoài ngừng gửi callback. Adapter phải gỡ listener hoặc chuyển trạng thái nguồn nếu có thể, nếu không callback vẫn có thể tiếp tục xuất hiện.

Với giao dịch quan trọng, fail-fast chỉ là một phần của thiết kế. Cần biết sự kiện nào đã được nhận, sự kiện nào chưa được xử lý, có thể phát lại từ offset nào và thao tác có idempotent hay không. Nếu không có nguồn bền vững để phát lại, kết thúc pipeline có thể làm mất các sự kiện đã đến nhưng chưa được xử lý.

## 9. Bọc callback không thể điều tiết thành Flux

Nhiều thư viện Java chỉ cung cấp listener hoặc callback push. Có thể dùng `Flux.create` để chuyển callback thành `Flux` và gắn cleanup với cancellation. Khi nguồn không thể giảm tốc, chọn overflow strategy phù hợp:

```java
Flux<SensorReading> readings = Flux.create(sink -> {
    Disposable registration = sensor.addListener(sink::next);
    sink.onDispose(registration);
}, FluxSink.OverflowStrategy.LATEST);
```

Ví dụ giả định `sensor.addListener` đăng ký listener và trả về `Disposable` để gỡ listener. `sink.onDispose` bảo đảm registration được giải phóng khi luồng kết thúc hoặc bị hủy. `LATEST` giữ giá trị mới nhất khi downstream chưa thể nhận thêm; các giá trị cũ đang chờ có thể bị thay thế.

Các overflow strategy thường gặp của `Flux.create`:

| Strategy | Hành vi |
| --- | --- |
| `BUFFER` | Giữ các phần tử đến trong buffer; nếu không có giới hạn phù hợp, bộ nhớ có thể tăng không giới hạn |
| `DROP` | Bỏ phần tử mới đến khi downstream không có demand để nhận |
| `LATEST` | Giữ giá trị mới nhất đang chờ và thay thế giá trị cũ |
| `ERROR` | Báo lỗi khi không thể phát phần tử do thiếu demand |
| `IGNORE` | Bỏ qua demand; có thể gây quá tải hoặc lỗi ở downstream nếu consumer không theo kịp |

Không chọn `BUFFER` chỉ vì muốn “không mất dữ liệu”; cần tính dung lượng và xử lý overflow. Không chọn `IGNORE` như một cách tắt backpressure, vì nó chuyển rủi ro sang queue và consumer downstream. `DROP`, `LATEST` và `ERROR` đều làm mất hoặc kết thúc luồng trong một số tình huống, nên phải phù hợp với semantics nghiệp vụ.

Nếu API nguồn có thể pause/resume hoặc request theo số lượng, nên nối demand với API đó thay vì dùng chính sách drop. Nếu nguồn hỗ trợ hủy listener, luôn gắn thao tác deregister vào lifecycle của sink. Nếu callback có thể được gọi đồng thời từ nhiều thread, cần dùng API adapter hỗ trợ phát đa luồng đúng cách và kiểm tra các lỗi phát; không giả định mọi listener source đều tuần tự hóa callback.

## 10. Khi nguồn hỗ trợ pause, resume hoặc credit

Một số nguồn không hỗ trợ Reactive Streams trực tiếp nhưng vẫn có cơ chế điều tiết riêng. Ví dụ, message consumer có thể tạm dừng partition, socket reader có thể dừng đọc thêm, hoặc API có thể nhận số credit cần cấp. Trong trường hợp này, adapter có thể chuyển demand downstream thành lệnh điều khiển nguồn.

Mô hình tổng quát:

```mermaid
flowchart TD
    A[Subscriber yêu cầu request(n)] --> B[Adapter nhận demand]
    B --> C{Nguồn có flow control?}
    C -->|Có| D[Chuyển demand thành credit / resume]
    D --> E[Nguồn phát trong giới hạn]
    E --> F[Adapter chuyển phần tử]
    C -->|Không| G[Áp dụng buffer / drop / latest / error]
    G --> F
    F --> H[Consumer xử lý]
```

Khi demand cạn, adapter có thể pause nguồn; khi demand tăng trở lại, adapter resume hoặc cấp thêm credit. Cần xử lý race khi pause/resume được gọi liên tiếp, giới hạn số phần tử đang bay (in-flight), và đảm bảo cancellation đóng nguồn hoặc gỡ listener.

Với message broker, acknowledgement thường liên quan đến việc xác nhận xử lý và cho phép broker giao thêm message. Không nên ack trước khi công việc cần thiết hoàn tất nếu muốn bảo đảm xử lý. Ngược lại, chỉ giữ message chưa ack mà không giới hạn số lượng có thể làm tăng lượng in-flight và gây mất cân bằng. Prefetch, concurrency và ack strategy phải được cấu hình cùng nhau.

## 11. Lưu bền khi không được phép mất dữ liệu

Nếu nguồn không thể giảm tốc và mọi sự kiện đều phải được giữ, bộ nhớ trong process thường không phải nơi phù hợp để hấp thụ chênh lệch lâu dài. Có thể cần một tầng lưu bền như message broker, append-only log hoặc queue có retention. Producer ghi sự kiện vào tầng này; consumer đọc theo tốc độ xử lý và xác nhận offset sau khi hoàn tất.

Kiến trúc này tách tốc độ tiếp nhận khỏi tốc độ xử lý, nhưng không tạo dung lượng vô hạn. Broker cũng có giới hạn disk, retention, quota, partition và tốc độ ghi. Nếu producer liên tục nhanh hơn tổng consumer, backlog vẫn tăng và cuối cùng chạm giới hạn. Khi đó cần tăng năng lực consumer, giảm tải đầu vào, mở rộng partition nếu semantics cho phép, hoặc áp dụng chính sách từ chối/điều tiết ở producer.

Đối với dữ liệu quan trọng, cần thêm:

- Mã sự kiện hoặc idempotency key để xử lý trùng an toàn.
- Offset/checkpoint để tiếp tục từ vị trí đã xử lý.
- Chính sách retry và dead-letter cho sự kiện không xử lý được.
- Giới hạn số message in-flight và kích thước batch.
- Metric backlog age, queue depth, throughput producer/consumer và tỷ lệ retry.
- Quy trình phục hồi khi broker đầy, consumer dừng hoặc dữ liệu vượt retention.

Lưu bền là cách bảo vệ dữ liệu và hấp thụ burst, không phải phép thuật làm cho hệ thống xử lý nhanh hơn. Nếu tốc độ đến trung bình vượt khả năng xử lý trong dài hạn, backlog vẫn cần được giải quyết bằng năng lực, điều tiết hoặc chính sách nghiệp vụ.

## 12. Đặt giới hạn concurrency không thay thế backpressure ở nguồn

Một cách xử lý thường gặp là dùng `flatMap` với concurrency giới hạn:

```java
Flux<Result> results = incomingEvents()
    .flatMap(this::processAsync, 32);
```

Tham số `32` giới hạn số publisher con được subscribe đồng thời theo semantics của `flatMap`. Điều này giúp giới hạn số tác vụ xử lý đồng thời, nhưng không bảo đảm một nguồn push không thể điều tiết sẽ ngừng tạo callback. Dữ liệu vẫn có thể được giữ ở adapter hoặc hàng đợi trước vị trí `flatMap` nếu nguồn tiếp tục phát.

Tương tự, `limitRate` có thể điều chỉnh cách Reactor yêu cầu dữ liệu từ upstream theo từng đợt. Nó hữu ích khi upstream tôn trọng demand. Nếu upstream là một callback source không có flow control, giới hạn demand ở downstream không thể ép thiết bị hoặc thư viện ngừng phát; adapter vẫn phải chọn cách giữ hoặc bỏ dữ liệu.

Giới hạn concurrency, giới hạn demand, giới hạn buffer và điều tiết nguồn là các lớp kiểm soát khác nhau. Hệ thống cần cấu hình chúng đồng bộ để không dồn backlog vào một tầng khuất.

## 13. Đo lường và cảnh báo quá tải

Một pipeline có thể chưa lỗi nhưng đã tiến gần đến giới hạn. Hãy quan sát cả tốc độ đến, tốc độ xử lý và lượng dữ liệu đang chờ. Các metric hữu ích gồm:

| Metric | Ý nghĩa |
| --- | --- |
| Arrival rate | Số phần tử nguồn phát mỗi giây |
| Processing rate | Số phần tử consumer hoàn tất mỗi giây |
| Queue depth / buffer occupancy | Số phần tử đang chờ và tỷ lệ sử dụng dung lượng |
| Oldest item age | Thời gian phần tử cũ nhất đã nằm trong hàng đợi |
| Drop count / drop rate | Số lượng và tỷ lệ phần tử bị loại bỏ |
| Overflow count | Số lần buffer chạm giới hạn hoặc pipeline báo lỗi quá tải |
| In-flight count | Số tác vụ đã giao nhưng chưa hoàn tất/ack |
| Consumer latency | Thời gian từ lúc nhận đến lúc xử lý xong |

Nếu arrival rate liên tục cao hơn processing rate, backlog age và queue depth sẽ tăng. Cảnh báo nên dựa trên xu hướng và ngân sách thời gian, không chỉ đợi buffer đầy. Nếu dữ liệu có thời hạn hữu ích, một backlog thấp nhưng quá cũ cũng có thể vi phạm yêu cầu nghiệp vụ.

Metric drop cần được phân biệt theo loại dữ liệu và lý do. Một dashboard có thể chấp nhận drop mẫu khi quá tải; một luồng lệnh không được phép mất dữ liệu cần báo động nghiêm trọng và chuyển sang lưu bền hoặc từ chối nguồn.

## 14. Kiểm thử chính sách khi consumer chậm

Kiểm thử nên chủ động tạo chênh lệch giữa tốc độ phát và tốc độ yêu cầu. Dùng `StepVerifier` với initial demand bằng 0 để giữ subscriber chưa nhận phần tử, sau đó phát dữ liệu qua nguồn test và kiểm tra chính sách đã chọn. Với `TestPublisher`, cần chọn chế độ test phù hợp để mô phỏng nguồn push có thể phát bất kể demand; test đó cố ý kiểm tra adapter/overflow policy khi upstream không tuân demand.

Ví dụ kiểm thử latest theo ý tưởng:

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux().onBackpressureLatest(), 0)
    .then(() -> source.next(1, 2, 3))
    .thenRequest(1)
    .expectNext(3)
    .thenCancel()
    .verify();
```

Ví dụ minh họa downstream chưa yêu cầu phần tử nào trong khi toán tử backpressure vẫn nhận dữ liệu từ nguồn và giữ giá trị mới nhất. `TestPublisher` ở đây đóng vai nguồn kiểm thử có thể phát dữ liệu theo kịch bản; adapter thực tế của callback source cần được kiểm thử riêng để xác minh cách nó nhận callback và áp dụng overflow strategy. Không dùng một nguồn test cố ý vi phạm demand để kết luận publisher Reactive Streams tuân thủ giao thức.

Các trường hợp nên kiểm tra:

1. Burst ngắn vượt tốc độ xử lý nhưng vẫn nằm trong buffer.
2. Buffer đạt đúng giới hạn và phần tử tiếp theo gây overflow.
3. Drop/latest giữ đúng phần tử theo semantics mong muốn.
4. Consumer yêu cầu dữ liệu trở lại sau thời gian không có demand.
5. Cancellation gỡ listener hoặc dừng nguồn khi API hỗ trợ.
6. Nguồn phát đồng thời từ nhiều thread.
7. Lỗi overflow được quan sát và kích hoạt cảnh báo/phục hồi.
8. Backlog bền vững tăng khi producer nhanh hơn consumer trong thời gian dài.

Không dùng `Thread.sleep` để tạo timing không ổn định. Dùng test publisher, virtual time hoặc đồng bộ hóa rõ ràng để điều khiển demand và thời điểm phát.

## 15. Quy trình chọn chính sách cho một nguồn không thể giảm tốc

Trước khi nối nguồn vào Reactor, hãy trả lời:

| Câu hỏi | Tác động đến thiết kế |
| --- | --- |
| Nguồn có thể pause, resume hoặc nhận credit không? | Nếu có, nối demand với flow control; nếu không, chọn overflow policy |
| Có được phép mất phần tử không? | Chọn drop/latest/sample chỉ khi nghiệp vụ cho phép |
| Mất phần tử nào ít gây hại nhất? | Chọn drop incoming, latest hoặc sampling theo semantics |
| Có cần giữ toàn bộ sự kiện qua restart? | Dùng broker/log/store bền vững thay cho buffer RAM |
| Burst lớn nhất và kéo dài bao lâu? | Tính buffer theo tốc độ đến, tốc độ xử lý và ngân sách bộ nhớ |
| Tốc độ trung bình có vượt năng lực consumer không? | Tăng capacity, giảm tải, mở rộng consumer hoặc thay đổi hợp đồng nguồn |
| Khi quá tải cần hành động gì? | Báo lỗi, cảnh báo, pause nguồn, chuyển lưu bền hoặc từ chối dữ liệu |
| Ai giải phóng listener và tài nguyên? | Gắn cleanup với cancellation và terminal signal |

Hãy thử với tải đại diện và burst xấu nhất, không chỉ tốc độ trung bình. Xác định giới hạn heap, thời gian chờ, tỷ lệ mất dữ liệu chấp nhận được và cách phục hồi khi overflow. Nếu không thể đưa ra một chính sách rõ ràng, pipeline chưa có hợp đồng quá tải đủ an toàn.

## 16. Những nhầm lẫn thường gặp

- **Cho rằng `request(n)` luôn làm nguồn bên ngoài giảm tốc:** chỉ nguồn hoặc adapter hỗ trợ demand/flow control mới có thể điều tiết thực sự.
- **Bọc callback vào `Flux` rồi nghĩ đã có backpressure end-to-end:** adapter vẫn cần buffer, drop, latest, error hoặc nối demand với API nguồn.
- **Dùng buffer vô hạn để tránh mất dữ liệu:** nếu tốc độ đến vượt tốc độ xử lý lâu dài, heap sẽ tăng đến giới hạn.
- **Tăng buffer để giải quyết quá tải kéo dài:** tăng buffer chỉ trì hoãn thời điểm đầy và làm tăng độ trễ.
- **Nhầm buffer backpressure với replay:** buffer phục vụ phần tử đang chờ consumer hiện tại; replay phục vụ subscriber đến muộn.
- **Dùng drop/latest cho sự kiện giao dịch:** có thể làm mất chuyển trạng thái bắt buộc hoặc khiến dữ liệu nghiệp vụ không nhất quán.
- **Dùng sampling cho cảnh báo mà không phân tích đỉnh ngắn:** có thể bỏ qua một lần vượt ngưỡng thoáng qua.
- **Cho rằng giới hạn concurrency tự giới hạn nguồn push:** nó giới hạn tác vụ xử lý đồng thời, không tự dừng callback source.
- **Dùng `IGNORE` để bỏ qua demand:** có thể chuyển quá tải xuống queue hoặc consumer và làm lỗi khó truy vết hơn.
- **Cho rằng broker có dung lượng vô hạn:** backlog vẫn tăng nếu producer liên tục vượt tổng năng lực consumer.
- **Không đo arrival rate, processing rate và queue age:** hệ thống có thể quá tải âm thầm trước khi xuất hiện lỗi rõ ràng.

## 17. Ghi nhớ khi tích hợp nguồn push

Backpressure là cơ chế quan trọng để điều tiết luồng dữ liệu, nhưng chỉ có thể giảm tốc nguồn khi nguồn tham gia flow control. Với cảm biến, callback hoặc giao thức push không thể tạm dừng, adapter phải quyết định dữ liệu nào được giữ, bỏ, gộp, lấy mẫu, lưu bền hoặc từ chối. Buffer hữu hạn hấp thụ burst; drop và latest phù hợp với một số dữ liệu trạng thái; sampling và aggregation giảm tải khi nghiệp vụ cho phép; broker/log bền vững bảo vệ sự kiện cần xử lý đầy đủ.

Hãy thiết kế chính sách trước khi nguồn bắt đầu phát, giới hạn bộ nhớ ở mọi tầng, gắn cleanup với cancellation, và quan sát tốc độ đến cùng tốc độ xử lý. Khi tốc độ đến vượt năng lực tiêu thụ trong thời gian dài, hệ thống phải tăng năng lực, giảm tải, lưu backlog có giới hạn hoặc từ chối dữ liệu theo một hợp đồng rõ ràng. Không có toán tử Reactor nào có thể tạo ra khả năng giảm tốc mà nguồn vật lý hoặc API bên ngoài không cung cấp.
