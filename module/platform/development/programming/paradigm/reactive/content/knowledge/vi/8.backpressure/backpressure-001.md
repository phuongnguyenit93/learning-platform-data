# Chênh lệch tốc độ phát và xử lý dẫn đến quá tải

Trong **REACTIVE_PROGRAMMING**, ta xử lý dữ liệu được phát theo thời gian qua các luồng bất đồng bộ, hợp đồng `Publisher–Subscriber` và những kiểu dữ liệu như `Mono` và `Flux`. Một vấn đề quan trọng của hệ thống luồng là tốc độ nguồn phát dữ liệu có thể lớn hơn tốc độ consumer xử lý. Nếu không điều tiết, phần tử chưa xử lý sẽ tích tụ trong hàng đợi, làm tăng độ trễ và tiêu thụ bộ nhớ cho đến khi hệ thống quá tải.

Reactive Streams đưa ra cơ chế **backpressure** để Subscriber báo nhu cầu nhận dữ liệu, giúp các thành phần phối hợp theo khả năng xử lý. Tuy nhiên, muốn chọn đúng chiến lược, trước hết cần hiểu sự chênh lệch tốc độ hình thành như thế nào, khi nào hàng đợi tăng và vì sao chỉ thêm buffer không thể giải quyết một tình trạng quá tải kéo dài.

## 1. Producer và consumer có tốc độ khác nhau

Trong một pipeline, producer tạo hoặc đọc dữ liệu rồi phát về phía downstream. Consumer nhận dữ liệu và thực hiện công việc như xác thực, biến đổi, ghi cơ sở dữ liệu hoặc gọi dịch vụ khác.

Hai tốc độ thường được đo bằng số phần tử trong một đơn vị thời gian:

- **Tốc độ phát (arrival rate, λ):** số phần tử đến pipeline trong một giây.
- **Tốc độ xử lý (service rate, μ):** số phần tử consumer hoàn thành trong một giây.

Ví dụ, một dịch vụ nhận 50.000 sự kiện mỗi giây nhưng chỉ ghi được 5.000 sự kiện mỗi giây. Khi đó, nếu hai tốc độ duy trì ổn định và không có cơ chế giảm tải, số sự kiện tồn đọng tăng khoảng 45.000 phần tử mỗi giây.

```text
Producer: 50.000 sự kiện/giây
             |
             v
       +-------------+
       | Hàng đợi    |  <--- tồn đọng tăng 45.000 sự kiện/giây
       +-------------+
             |
             v
Consumer: 5.000 sự kiện/giây
```

Hàng đợi giúp hấp thụ chênh lệch trong một khoảng thời gian. Nó không làm consumer xử lý nhanh hơn. Nếu tốc độ phát tiếp tục cao hơn tốc độ xử lý, hàng đợi sẽ tiếp tục tăng cho đến khi đạt giới hạn hoặc chiếm hết tài nguyên có thể dùng.

## 2. Khi nào hàng đợi tăng và khi nào hệ thống ổn định?

Có thể dùng chênh lệch giữa tốc độ đến và tốc độ xử lý để ước lượng xu hướng của backlog:

\[
\text{Tốc độ tăng backlog} \approx \lambda - \mu
\]

Đây là mô hình đơn giản khi producer và consumer duy trì tốc độ tương đối ổn định, không tính đến retry, batch, drop hoặc nhiều tầng queue khác.

| Quan hệ tốc độ | Hành vi hàng đợi | Ý nghĩa |
|---|---|---|
| \(\lambda < \mu\) | Có khả năng giảm khi đang tồn đọng | Consumer có năng lực xử lý lớn hơn lượng dữ liệu đến trung bình |
| \(\lambda = \mu\) | Không có dư địa để giảm backlog | Hệ thống rất nhạy với burst và dao động |
| \(\lambda > \mu\) kéo dài | Backlog tăng liên tục | Hệ thống có nguy cơ quá tải nếu không điều tiết hoặc loại bỏ dữ liệu |

Ví dụ với \(\lambda = 50.000\) và \(\mu = 5.000\) phần tử/giây:

\[
50.000 - 5.000 = 45.000\text{ phần tử/giây}
\]

Sau 10 giây, backlog tăng xấp xỉ:

\[
45.000 \times 10 = 450.000\text{ phần tử}
\]

Nếu mỗi phần tử chiếm trung bình 2 KB trong bộ nhớ (chỉ tính phần dữ liệu ước lượng, chưa tính overhead của object và queue), riêng phần backlog này đã cần khoảng 900 MB. Kích thước thực tế có thể cao hơn do object header, tham chiếu, cấu trúc hàng đợi và dữ liệu phụ trợ.

Trong thực tế, tốc độ đến thường thay đổi theo thời gian. Một đợt tăng đột biến ngắn có thể được hấp thụ nếu sau đó consumer có năng lực dư để xử lý backlog. Nhưng nếu tải trung bình trong thời gian dài lớn hơn năng lực xử lý, queue không thể tự ổn định.

## 3. Quá tải không chỉ là hết bộ nhớ

Backlog tăng tạo ra nhiều tác động liên quan với nhau:

1. **Bộ nhớ tăng:** phần tử chờ được giữ trong queue, buffer hoặc object đang sống, làm tăng heap và áp lực garbage collection.
2. **Độ trễ tăng:** một sự kiện phải đợi lâu hơn trước khi được xử lý. Dù consumer vẫn hoạt động, kết quả có thể đến sau thời điểm nghiệp vụ còn hữu ích.
3. **Timeout và retry dây chuyền:** lời gọi downstream chờ lâu có thể timeout; retry tạo thêm công việc, khiến tải tăng hơn nữa.
4. **Cạn tài nguyên phụ trợ:** kết nối cơ sở dữ liệu, thread, socket hoặc giới hạn request đến dịch vụ ngoài có thể bị chiếm dụng bởi công việc đang chờ.
5. **Suy giảm toàn hệ thống:** một consumer chậm có thể làm các pipeline dùng chung pool, queue hoặc dependency cũng bị chậm theo.

Ví dụ, nếu mỗi sự kiện cần một kết nối đến cơ sở dữ liệu và ứng dụng tạo quá nhiều tác vụ đồng thời, hệ thống có thể cạn connection pool trước khi heap đạt giới hạn. Vì vậy, theo dõi riêng CPU là chưa đủ để kết luận pipeline còn an toàn.

## 4. Buffer hấp thụ burst nhưng không sửa được thiếu năng lực kéo dài

Buffer là vùng lưu tạm dữ liệu giữa producer và consumer. Nó hữu ích khi tốc độ phát dao động hoặc consumer tạm thời bận. Nếu có khoảng trống tải sau burst, consumer có thể xử lý phần tồn đọng.

Tuy nhiên, buffer có giới hạn dung lượng. Nếu tốc độ đến luôn lớn hơn tốc độ xử lý, dung lượng buffer chỉ quyết định thời điểm hệ thống chạm ngưỡng.

Giả sử buffer chứa tối đa 100.000 phần tử và backlog tăng 45.000 phần tử/giây. Bỏ qua backlog ban đầu, thời gian lấp đầy gần đúng là:

\[
\frac{100.000}{45.000} \approx 2{,}22\text{ giây}
\]

Khi buffer đầy, hệ thống cần một chính sách rõ ràng: làm chậm nguồn, từ chối dữ liệu, loại bỏ phần tử, giữ lại phần tử mới nhất, ghi bền vững sang nơi khác hoặc phát lỗi. Nếu không có chính sách, ứng dụng có thể tiếp tục tăng bộ nhớ bằng cách dùng queue không giới hạn.

Buffer không giới hạn thường khiến lỗi xuất hiện muộn hơn và khó dự đoán hơn. Nó cho phép backlog tăng theo tải thay vì tạo một ngưỡng kiểm soát rõ ràng. Với hệ thống có giới hạn tài nguyên, cần cân nhắc dung lượng hữu hạn và cách xử lý khi đầy.

## 5. Backpressure điều tiết bằng demand

Reactive Streams định nghĩa hợp đồng để Subscriber báo số phần tử mình sẵn sàng nhận thông qua `Subscription.request(n)`. Publisher phải tuân thủ lượng demand đã được yêu cầu và không được phát `onNext` vượt quá nhu cầu còn lại.

```text
Subscriber                         Publisher
    |                                  |
    |------ subscribe(subscriber) ---->|
    |<--------- onSubscribe -----------|
    |                                  |
    |---------- request(20) ---------->|
    |<----------- onNext(1) -----------|
    |<----------- onNext(2) -----------|
    |                ...               |
    |<---------- onNext(20) -----------|
    |                                  |
    |------ xử lý xong, request(20) -->|
    |<---------- lô tiếp theo ---------|
```

Subscriber có thể yêu cầu dữ liệu theo từng lô hoặc theo từng phần tử. Khi chưa có demand mới, Publisher không được gửi thêm phần tử cho subscription đó. Nhờ vậy, nhu cầu ở downstream có thể lan ngược qua các toán tử về upstream, tạo cơ chế phối hợp tốc độ giữa các thành phần hỗ trợ Reactive Streams.

Backpressure là giao thức điều tiết số lượng phần tử được phát, không phải bộ điều tốc theo đơn vị thời gian. `request(100)` cho phép tối đa 100 phần tử theo nhu cầu hiện tại; nó không có nghĩa chỉ được phát 100 phần tử mỗi giây. Muốn giới hạn tốc độ theo thời gian, ứng dụng cần thêm chính sách rate limiting hoặc pacing phù hợp.

Backpressure cũng không bảo đảm mọi nguồn bên ngoài đều có thể giảm tốc độ. Một callback từ thiết bị, socket hoặc API không hỗ trợ demand có thể tiếp tục tạo dữ liệu. Khi đó adapter phải quyết định buffer, drop, latest, từ chối hoặc chuyển dữ liệu sang một hệ thống lưu trữ khác.

## 6. Phân biệt backpressure với các chiến lược xử lý quá tải

Không có một chính sách phù hợp cho mọi loại dữ liệu. Cần xác định dữ liệu có bắt buộc phải xử lý đầy đủ hay không, thứ tự có quan trọng không, dữ liệu có thể phát lại từ nguồn hay không và độ trễ tối đa chấp nhận được.

| Chiến lược | Cách hoạt động | Phù hợp khi | Rủi ro hoặc đánh đổi |
|---|---|---|---|
| Backpressure | Yêu cầu upstream chỉ phát theo demand | Nguồn có thể tôn trọng demand | Không trực tiếp áp dụng được cho nguồn không điều tiết |
| Buffer hữu hạn | Giữ dữ liệu trong giới hạn định trước | Cần hấp thụ burst ngắn | Khi đầy phải có chính sách overflow |
| Drop | Bỏ phần tử khi downstream không theo kịp | Số liệu phụ, telemetry có thể mất mẫu | Mất sự kiện đã bị loại bỏ |
| Latest | Chỉ giữ phần tử mới nhất trong lúc downstream chậm | Trạng thái hiện tại quan trọng hơn lịch sử trung gian | Không phù hợp nếu cần xử lý mọi sự kiện |
| Reject hoặc fail | Từ chối hoặc báo lỗi khi vượt ngưỡng | Cần bảo vệ tài nguyên và báo ngược tình trạng quá tải | Producer phải có cách retry hoặc xử lý từ chối |
| Persist rồi xử lý sau | Đưa dữ liệu vào log/queue bền vững để consumer đọc dần | Cần giữ dữ liệu và chấp nhận độ trễ | Cần quản lý dung lượng, retention và khả năng phát lại |
| Scale consumer | Tăng năng lực xử lý song song | Công việc có thể phân chia và dependency còn dư năng lực | Có thể làm quá tải database hoặc dịch vụ downstream |

Các chiến lược có thể kết hợp. Ví dụ, một hệ thống có thể giới hạn demand, dùng buffer hữu hạn để hấp thụ dao động nhỏ và ghi dữ liệu vào broker bền vững khi cần giữ toàn bộ sự kiện.

## 7. Ví dụ backpressure và giới hạn xử lý trong Reactor

Trong Reactor, `Flux` và `Mono` triển khai hợp đồng Reactive Streams. Khi các toán tử nằm trong một pipeline hỗ trợ backpressure, demand từ Subscriber được truyền ngược qua chuỗi toán tử theo cách implementation quản lý.

### Giới hạn nhu cầu upstream với `limitRate`

`limitRate` điều chỉnh cách Reactor chia nhu cầu downstream thành các yêu cầu nhỏ hơn gửi upstream:

```java
Flux<Integer> values = Flux.range(1, 1_000_000)
    .limitRate(100);

values.subscribe(this::process);
```

Toán tử này hữu ích để kiểm soát lượng demand được yêu cầu từ upstream theo từng đợt. Nó không phải bộ giới hạn tốc độ theo giây và cũng không bảo đảm thời gian xử lý của `process` sẽ giảm. Nếu consumer xử lý chậm, pipeline vẫn cần một chính sách về thời gian, concurrency và tài nguyên phù hợp.

### Giới hạn số tác vụ bất đồng bộ đồng thời

Khi mỗi phần tử được ánh xạ thành một tác vụ bất đồng bộ, tham số concurrency của `flatMap` giúp giới hạn số inner Publisher đang được subscribe đồng thời:

```java
Flux<Result> results = Flux.fromIterable(requests)
    .flatMap(this::callRemoteService, 8);
```

Ví dụ đặt giới hạn tám tác vụ đồng thời. Đây là giới hạn concurrency của bước `flatMap`, không phải giới hạn tốc độ request mỗi giây. Nếu dịch vụ ngoài có quota theo thời gian, cần bổ sung rate limiter. Cũng cần lưu ý mỗi inner Publisher có thể có prefetch riêng, vì vậy concurrency không phải phép đo chính xác cho tổng số byte đang được giữ trong bộ nhớ.

### Chọn chính sách khi nguồn không thể điều tiết

Với một nguồn phát nóng không thể chờ demand, có thể chọn hành vi khi downstream không theo kịp. Ví dụ, nếu dữ liệu chỉ mang ý nghĩa quan sát và có thể bỏ mẫu:

```java
Flux<Metric> metrics = hotMetricSource()
    .onBackpressureDrop(metric ->
        log.warn("Drop metric because downstream is busy: {}", metric.name())
    );
```

Nếu chỉ cần trạng thái mới nhất, có thể cân nhắc:

```java
Flux<State> latestState = hotStateSource()
    .onBackpressureLatest();
```

Các toán tử trên là chính sách ở ranh giới giữa nguồn và downstream. Chúng có thể giúp bảo vệ consumer nhưng đồng nghĩa một số phần tử sẽ không được xử lý. Không nên dùng drop hoặc latest cho giao dịch, đơn hàng hay sự kiện kiểm toán nếu nghiệp vụ yêu cầu giữ đầy đủ từng phần tử.

Khi cần giữ dữ liệu, có thể dùng buffer hữu hạn và định nghĩa rõ hành vi khi buffer đầy:

```java
Flux<Event> buffered = hotEventSource()
    .onBackpressureBuffer(1_000);
```

Với cấu hình giới hạn này, khi vượt dung lượng buffer, pipeline có thể kết thúc bằng lỗi overflow theo chính sách của toán tử. Ứng dụng cần xử lý lỗi và quyết định có thể phát lại dữ liệu từ nguồn hay chuyển sang lưu trữ bền vững. Buffer hữu hạn bảo vệ bộ nhớ tốt hơn buffer không giới hạn, nhưng không loại bỏ chênh lệch năng lực xử lý.

## 8. Tính toán năng lực và đặt ngưỡng

Trước khi chọn buffer hoặc concurrency, cần đo dữ liệu thực tế. Một số phép ước lượng hữu ích:

- **Backlog tăng:** lấy tốc độ đến trừ tốc độ xử lý trong cùng đơn vị thời gian.
- **Thời gian đến ngưỡng:** lấy dung lượng queue còn trống chia cho tốc độ tăng backlog dự kiến.
- **Bộ nhớ backlog:** lấy số phần tử chờ nhân với kích thước trung bình thực tế của mỗi phần tử, sau đó cộng overhead cấu trúc dữ liệu và object.
- **Năng lực consumer:** đo throughput khi chạy với dependency thật hoặc môi trường gần thực tế, không chỉ đo tốc độ của một hàm biến đổi trong bộ nhớ.

Định luật Little mô tả quan hệ giữa số lượng phần tử trung bình trong hệ thống \(L\), tốc độ đến trung bình \(\lambda\) và thời gian lưu lại trung bình \(W\):

\[
L = \lambda W
\]

Trong điều kiện hệ thống ổn định và các đại lượng được đo trên cùng phạm vi, nếu tốc độ đến là 2.000 phần tử/giây và thời gian lưu lại trung bình là 0,5 giây, số phần tử trung bình trong hệ thống xấp xỉ 1.000. Khi độ trễ tăng, số phần tử đang nằm trong hệ thống cũng tăng nếu throughput không đổi.

Đây là quan hệ quan sát và ước lượng, không phải cách tính dung lượng buffer an toàn duy nhất. Cần đo cả phân vị độ trễ cao, burst, kích thước phần tử, retry và giới hạn dependency để đặt ngưỡng thực tế.

## 9. Theo dõi dấu hiệu quá tải

Một pipeline có thể vẫn phát dữ liệu nhưng đã ở trạng thái quá tải tiềm ẩn. Nên quan sát ít nhất:

- Tốc độ phần tử đến và tốc độ phần tử hoàn tất xử lý.
- Độ sâu queue hoặc số phần tử đang chờ ở từng ranh giới có buffer.
- Tuổi của phần tử cũ nhất đang chờ và độ trễ đầu cuối.
- Số lần drop, overflow, reject, timeout và retry.
- Heap, garbage collection, số thread hoạt động và số tác vụ đồng thời.
- Tình trạng connection pool, quota và latency của dịch vụ downstream.

Chỉ số tổng số phần tử đã nhận không cho biết pipeline có đang theo kịp hay không. Cần so sánh tốc độ đến với tốc độ hoàn tất và theo dõi backlog theo thời gian. Nếu queue liên tục tăng, tăng thêm buffer chỉ trì hoãn thời điểm chạm giới hạn.

## 10. Cách chọn giải pháp theo yêu cầu nghiệp vụ

Trước khi thay đổi pipeline, hãy trả lời các câu hỏi sau:

1. Dữ liệu đến theo burst ngắn hay có tốc độ trung bình cao hơn năng lực consumer trong thời gian dài?
2. Nguồn có hỗ trợ backpressure và có thể giảm tốc độ đọc không?
3. Có bắt buộc xử lý mọi phần tử theo đúng thứ tự không?
4. Có thể bỏ mẫu hoặc chỉ giữ trạng thái mới nhất không?
5. Buffer tối đa được phép chiếm bao nhiêu bộ nhớ và đầy thì phải làm gì?
6. Có thể scale consumer mà không làm quá tải dependency phía sau không?
7. Nếu từ chối hoặc lỗi, dữ liệu có thể được retry hay phát lại từ nguồn không?

Với sự kiện nghiệp vụ cần bảo toàn, ưu tiên điều tiết demand hoặc lưu trữ bền vững rồi xử lý dần; cần có cơ chế retry, idempotency và giám sát backlog. Với telemetry có thể mất mẫu, drop hoặc latest có thể hợp lý. Với tải tăng ngắn, buffer hữu hạn có thể hấp thụ burst nếu hệ thống có đủ năng lực xử lý phần tồn đọng sau đó.

Quá tải xuất hiện khi công việc đến nhanh hơn khả năng hoàn tất trong thời gian đủ dài. Reactive Streams cung cấp giao thức backpressure để consumer điều tiết demand; Reactor bổ sung các toán tử để giới hạn nhu cầu, concurrency và lựa chọn hành vi ở ranh giới nguồn. Khi kết hợp các cơ chế này với buffer hữu hạn, đo throughput và chính sách dữ liệu phù hợp, pipeline có thể duy trì giới hạn tài nguyên và phản ứng rõ ràng khi tải vượt năng lực.
