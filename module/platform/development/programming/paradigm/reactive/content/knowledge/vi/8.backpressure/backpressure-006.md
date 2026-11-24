# Hàng đợi và ranh giới bất đồng bộ làm thay đổi nhu cầu

Backpressure cho phép Subscriber điều tiết số phần tử mà Publisher được phép phát. Tuy nhiên, trong một pipeline thực tế, request không nhất thiết được truyền nguyên vẹn từ Subscriber cuối đến tận nguồn. Các toán tử có thể tạo hàng đợi, yêu cầu trước một lượng dữ liệu (prefetch), gom nhiều phần tử thành một kết quả hoặc xử lý nhiều Publisher con đồng thời. Những hàng đợi và ranh giới bất đồng bộ này giúp các phần của pipeline hoạt động độc lập, nhưng cũng làm thay đổi cách nhu cầu được truyền và lượng dữ liệu đang nằm trong bộ nhớ.

Bài học thuộc chương **Áp lực ngược** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline Java. Hiểu hàng đợi và ranh giới bất đồng bộ giúp dự đoán chính xác hơn tải đang chờ, giới hạn bộ nhớ và hành vi điều tiết của pipeline.

Các đoạn mã minh họa API Reactor. Những tên như eventSource, log, metrics, Customer và blockingRepository đại diện cho thành phần của ứng dụng; một số import và khai báo miền được lược bỏ để tập trung vào hành vi của toán tử.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao toán tử tạo ranh giới bất đồng bộ thường cần hàng đợi giữa producer và consumer.
- Phân biệt demand ở downstream với request được prefetch ở upstream.
- Phân tích cách publishOn, flatMap và buffer làm thay đổi lượng dữ liệu được yêu cầu hoặc lưu giữ.
- Chọn kích thước prefetch và giới hạn đồng thời dựa trên năng lực xử lý và bộ nhớ.
- Chọn chính sách phù hợp khi nguồn phát không thể giảm tốc độ: buffer, drop, latest hoặc báo lỗi.
- Kiểm thử hành vi demand và hủy bằng StepVerifier, đồng thời theo dõi hàng đợi khi vận hành.

## 1. Vì sao pipeline cần hàng đợi?

Trong một chuỗi xử lý đồng bộ, phần tử thường đi lần lượt qua các toán tử. Khi một bước xử lý xong phần tử hiện tại, nó mới chuyển phần tử sang bước tiếp theo. Nếu không có ranh giới bất đồng bộ, các bước có thể phối hợp trực tiếp qua lời gọi và tín hiệu, không cần giữ một hàng đợi riêng chỉ để tách tốc độ thực thi.

Khi một bước chuyển sang scheduler khác, producer và consumer có thể chạy trên các luồng khác nhau. Producer có thể phát phần tử trong khi consumer vẫn đang xử lý phần tử trước. Một hàng đợi nằm giữa hai phía sẽ tạm giữ các phần tử chờ xử lý:

~~~text
Producer
   |
   |  phát phần tử theo demand / prefetch
   v
+--------------------+
| Hàng đợi tại ranh  |
| giới bất đồng bộ   |
+--------------------+
   |
   |  consumer lấy phần tử
   v
Consumer trên scheduler khác
~~~

Hàng đợi giúp tách thời điểm phát và thời điểm xử lý. Nếu producer tạm thời nhanh hơn consumer, phần tử được giữ lại để consumer lấy sau. Nếu consumer nhanh hơn producer, consumer có thể phải chờ phần tử tiếp theo.

Hàng đợi không làm tăng năng lực xử lý lâu dài. Nếu tốc độ đến trung bình cao hơn tốc độ tiêu thụ trong thời gian dài, số phần tử chờ sẽ tăng cho đến khi hàng đợi đầy hoặc bộ nhớ cạn. Backpressure cần phối hợp với hàng đợi để giới hạn lượng công việc đang chờ hoặc để áp dụng một chính sách khi nguồn không thể giảm tốc độ.

## 2. Demand thay đổi qua một ranh giới bất đồng bộ

Trong Reactive Streams, Subscriber cuối gửi request(n) về upstream. Với một chuỗi toán tử đồng bộ đơn giản, request có thể được truyền qua các toán tử theo cách tương đối trực tiếp. Khi có ranh giới bất đồng bộ, toán tử có thể yêu cầu trước một lượng phần tử để lấp hàng đợi của mình.

Ví dụ với Reactor:

~~~java
Flux<Integer> pipeline =
    Flux.range(1, 100)
        .map(value -> value * 10)
        .publishOn(Schedulers.parallel(), 16)
        .map(value -> expensiveCalculation(value));
~~~

publishOn chuyển việc xử lý các tín hiệu phía sau nó sang scheduler được chỉ định. Nó tạo ranh giới bất đồng bộ và dùng hàng đợi để chuyển phần tử từ phía upstream sang worker phía downstream. Tham số 16 là prefetch: lượng phần tử mà publishOn yêu cầu trước từ upstream cho hàng đợi của nó.

Giả sử Subscriber cuối ban đầu chưa yêu cầu phần tử nào. publishOn vẫn có thể gửi request ban đầu để lấp hàng đợi, theo chính sách prefetch của nó. Khi consumer xử lý và lấy phần tử khỏi hàng đợi, toán tử tiếp tục yêu cầu thêm dữ liệu theo các đợt. Vì thế, số request quan sát ở phía nguồn có thể lớn hơn demand hiện tại mà Subscriber cuối đã gửi.

Prefetch không có nghĩa Subscriber cuối đã tiêu thụ các phần tử đó. Nó chỉ cho biết toán tử đã xin phép upstream phát trước một lượng dữ liệu để giữ sẵn. Các phần tử đã được phát có thể vẫn đang nằm trong hàng đợi chờ downstream xử lý.

### publishOn và subscribeOn có vai trò khác nhau

- **publishOn** đổi scheduler dùng cho các tín hiệu phía downstream kể từ vị trí đặt toán tử. Nó tạo ranh giới chuyển dữ liệu bất đồng bộ và thường có hàng đợi cùng prefetch.
- **subscribeOn** chỉ định scheduler thực hiện quá trình subscribe và yêu cầu nguồn ở phía upstream. Nó hữu ích để điều phối nơi nguồn bắt đầu hoạt động, đặc biệt khi nguồn có thao tác khởi tạo cần chạy trên scheduler phù hợp.

Ví dụ:

~~~java
Mono<Customer> customer =
    Mono.fromCallable(() -> blockingRepository.findById(customerId))
        .subscribeOn(Schedulers.boundedElastic())
        .publishOn(Schedulers.parallel())
        .map(this::toCustomerView);
~~~

Lời gọi repository chặn được thực hiện trên boundedElastic. Sau ranh giới publishOn, bước chuyển đổi view chạy trên parallel. Việc chọn scheduler cần dựa trên loại công việc: boundedElastic phù hợp để cô lập tác vụ có khả năng chặn; parallel thường phù hợp với phép tính CPU-bound ngắn. Không nên đặt publishOn chỉ vì muốn tăng tốc; mỗi ranh giới thêm vào có thể tạo hàng đợi và chi phí chuyển lịch.

## 3. Prefetch và kích thước hàng đợi

Prefetch là lượng phần tử một toán tử yêu cầu trước để có sẵn dữ liệu khi downstream cần. Nó thường được biểu diễn bằng số phần tử, không phải số byte. Với phần tử có kích thước lớn hoặc không đồng đều, cùng một prefetch vẫn có thể tiêu thụ lượng bộ nhớ rất khác nhau.

Với publishOn, có thể chỉ định prefetch rõ ràng:

~~~java
Flux<Event> events =
    eventSource()
        .publishOn(Schedulers.parallel(), 32)
        .map(this::enrich);
~~~

Giá trị 32 cho phép publishOn yêu cầu trước tối đa một lượng phần tử theo cấu hình prefetch đó. Khi downstream tiêu thụ dữ liệu, toán tử sẽ tiếp tục yêu cầu thêm theo các đợt để duy trì mức dữ liệu sẵn sàng. Chi tiết ngưỡng bổ sung request là hành vi triển khai của toán tử; khi thiết kế ứng dụng, nên dựa vào hợp đồng và đo lường thay vì phụ thuộc vào một con số nội bộ cố định.

Prefetch lớn có thể giúp consumer ít phải chờ khi producer có thể phát nhanh, nhưng đồng thời làm tăng lượng dữ liệu có thể nằm trong hàng đợi. Prefetch nhỏ giảm lượng dữ liệu giữ sẵn nhưng có thể làm consumer thường xuyên chờ nguồn, nhất là khi độ trễ tạo phần tử cao.

### Ước lượng bộ nhớ

Một ước lượng ban đầu cho hàng đợi có thể dùng:

\[
\text{Bộ nhớ hàng đợi} \approx
\text{số phần tử đang giữ} \times
\text{kích thước trung bình mỗi phần tử}
\]

Ví dụ, nếu một ranh giới giữ khoảng 32 phần tử và mỗi phần tử chiếm trung bình 8 KB, phần payload có thể vào khoảng 256 KB cho hàng đợi đó. Đây chỉ là ước lượng: còn chi phí tham chiếu, cấu trúc hàng đợi, object graph và các hàng đợi khác trong pipeline.

Nếu pipeline có ba ranh giới bất đồng bộ, mỗi ranh giới có prefetch riêng, tổng lượng dữ liệu đang chờ có thể lớn hơn nhiều so với nhìn vào một tham số prefetch đơn lẻ. Khi phần tử chứa danh sách, mảng hoặc dữ liệu lớn, hãy đo kích thước object thực tế và cân nhắc giới hạn theo byte ở tầng ứng dụng nếu cần.

## 4. Các toán tử có thể thay đổi nhu cầu

### buffer: một yêu cầu downstream có thể cần nhiều phần tử upstream

buffer(n) gom tối đa n phần tử nguồn thành một List rồi phát List đó như một phần tử đầu ra. Đơn vị demand sau buffer là batch, còn đơn vị demand trước buffer là phần tử riêng lẻ.

~~~java
Flux<List<Integer>> batches =
    Flux.range(1, 100)
        .doOnRequest(n -> log.info("Nguồn nhận demand: {}", n))
        .buffer(10)
        .doOnRequest(n -> log.info("Demand theo batch: {}", n));
~~~

Nếu downstream yêu cầu một batch, buffer cần thu thập các phần tử để tạo batch đó. Trong trường hợp batch đầy đủ, một yêu cầu đầu ra có thể cần tối đa mười phần tử đầu vào. Nếu nguồn hoàn tất trước khi batch đầy, buffer có thể phát batch cuối chứa ít hơn mười phần tử.

Điều này cho thấy không thể so sánh trực tiếp con số request ở hai phía nếu các toán tử đã thay đổi cấu trúc dữ liệu. Hãy xác định rõ đơn vị mà mỗi tầng tiêu thụ: một Event, một List<Event>, hay một nhóm kết quả.

buffer có thể giữ dữ liệu trong bộ nhớ khi downstream chưa yêu cầu batch tiếp theo. Với buffer theo thời gian hoặc theo điều kiện khác, cần hiểu thêm lúc nào batch được phát và batch cuối được xử lý ra sao. Không nên dùng batch lớn nếu mỗi phần tử có kích thước lớn hoặc thời gian xử lý batch không ổn định.

### flatMap: nhiều Publisher con và nhiều hàng đợi

flatMap có thể đăng ký đồng thời vào nhiều Publisher con. Hai tham số quan trọng là concurrency và prefetch:

~~~java
Flux<OrderView> views =
    Flux.fromIterable(orderIds)
        .flatMap(
            id -> orderClient.findById(id),
            8,
            4
        );
~~~

Trong ví dụ này:

- 8 giới hạn số Publisher con được đăng ký đồng thời.
- 4 là prefetch cho mỗi Publisher con trong cách flatMap tiêu thụ các nguồn con.

Khi có nhiều Publisher con, mỗi nguồn có thể có dữ liệu đang chờ. Tổng lượng công việc đang hoạt động phụ thuộc vào concurrency, prefetch, tốc độ phản hồi và hàng đợi nội bộ của các toán tử liên quan. Tăng concurrency có thể tăng throughput khi các nguồn I/O độc lập, nhưng cũng tăng số kết nối và lượng công việc đang chờ. Tăng prefetch có thể giảm khoảng trống giữa các lần lấy dữ liệu, nhưng làm tăng dữ liệu được yêu cầu trước.

Nếu cần giữ thứ tự đầu ra theo thứ tự nguồn, cân nhắc concatMap hoặc flatMapSequential theo yêu cầu nghiệp vụ. Các toán tử này có chính sách kết hợp và hàng đợi khác nhau. Chọn toán tử dựa trên yêu cầu thứ tự và mức đồng thời, không chỉ dựa trên throughput.

### limitRate: chia nhỏ request lớn

limitRate giúp điều chỉnh cách request được truyền lên upstream:

~~~java
Flux<Event> events =
    eventSource()
        .limitRate(64)
        .map(this::process);
~~~

Khi downstream yêu cầu một lượng lớn dữ liệu, limitRate chia request upstream thành các đợt nhỏ hơn theo giới hạn đã cấu hình. Điều này hữu ích khi nguồn có thể đáp ứng demand lớn nhưng ứng dụng muốn tránh yêu cầu một lượng quá lớn cùng lúc.

limitRate không phải là một ranh giới scheduler và không thay thế giới hạn đồng thời của flatMap. Nó điều chỉnh cách truyền demand, trong khi publishOn điều phối thực thi qua ranh giới bất đồng bộ và flatMap điều khiển số Publisher con hoạt động đồng thời.

## 5. Khi nguồn không thể giảm tốc độ

Backpressure hoạt động hiệu quả nhất khi nguồn có thể tuân theo request. Tuy nhiên, một số nguồn nóng (hot source) hoặc API callback bên ngoài có thể phát sự kiện theo nhịp riêng, bất kể subscriber đang sẵn sàng nhận bao nhiêu phần tử.

Ví dụ: cảm biến gửi mẫu theo chu kỳ, message broker đẩy thông điệp theo tốc độ riêng hoặc callback nhận sự kiện từ thư viện không hỗ trợ Reactive Streams. Khi consumer chậm hơn producer, adapter cần có chính sách rõ ràng cho phần tử đến trong lúc không có demand.

Reactor cung cấp một số toán tử để chọn chính sách:

| Chính sách | Toán tử | Hành vi khi downstream không theo kịp |
|---|---|---|
| Giữ phần tử chờ xử lý | onBackpressureBuffer | Lưu phần tử vào hàng đợi; cần chọn giới hạn để tránh tăng bộ nhớ vô hạn |
| Bỏ phần tử mới đến | onBackpressureDrop | Bỏ phần tử đến khi không có demand |
| Giữ giá trị mới nhất | onBackpressureLatest | Giữ giá trị gần nhất để downstream nhận khi có demand trở lại |
| Báo lỗi | onBackpressureError | Kết thúc bằng lỗi khi phần tử đến mà không có demand |

Các toán tử onBackpressure* thường yêu cầu nguồn upstream không giới hạn rồi tự áp dụng chính sách ở phía sau. Điều này có nghĩa chúng không làm producer chậm lại. Chúng kiểm soát điều gì xảy ra với dữ liệu khi downstream chưa sẵn sàng.

### Buffer có giới hạn

~~~java
Flux<MarketTick> ticks =
    hotMarketFeed()
        .onBackpressureBuffer(
            500,
            dropped -> log.warn("Hàng đợi đầy, không giữ được tick {}", dropped)
        );
~~~

Ví dụ dùng hàng đợi có giới hạn 500 phần tử. Khi vượt quá giới hạn, callback overflow được gọi; toán tử báo lỗi overflow theo chính sách của overload này. Ứng dụng cần quyết định xử lý lỗi đó ở tầng phù hợp, ví dụ phát cảnh báo, ngừng tiêu thụ hoặc chuyển sang nguồn thay thế.

Không nên mặc định dùng buffer không giới hạn cho nguồn nóng. Nếu producer tiếp tục phát nhanh hơn consumer trong thời gian dài, hàng đợi sẽ tiếp tục tăng và có thể làm cạn heap. Hàng đợi hữu hạn buộc ứng dụng phải chọn hành vi khi đầy: báo lỗi, bỏ dữ liệu hoặc giảm tốc độ ở nguồn nếu nguồn có hỗ trợ.

### Drop và latest

Với dữ liệu mà mỗi sự kiện đều quan trọng, bỏ dữ liệu có thể không chấp nhận được. Nhưng với dữ liệu trạng thái liên tục như vị trí hiện tại hoặc giá trị cảm biến mới nhất, giữ lại tất cả giá trị cũ đôi khi không hữu ích:

~~~java
Flux<SensorReading> latestReadings =
    sensorFeed()
        .onBackpressureLatest();
~~~

Nếu consumer đang bận, toán tử giữ giá trị mới nhất thay cho việc tích lũy mọi giá trị đến. Khi downstream có demand trở lại, nó nhận trạng thái mới nhất còn được giữ. Các giá trị trung gian có thể bị bỏ, nên chính sách này chỉ phù hợp khi nghiệp vụ cho phép mất các mẫu cũ.

onBackpressureDrop phù hợp khi sự kiện dư thừa có thể bị bỏ và hệ thống có thể ghi nhận số lượng bị bỏ. Đừng dùng drop để che giấu một consumer chậm trong luồng giao dịch hoặc audit cần tính đầy đủ.

## 6. Hàng đợi đầy và cách chọn giới hạn

Hàng đợi đầy là dấu hiệu producer đã tạo dữ liệu nhanh hơn khả năng consumer xử lý trong một khoảng thời gian. Khi đó, hệ thống cần một quyết định có chủ đích:

1. **Giảm tốc độ upstream:** nếu nguồn hỗ trợ demand hoặc có cơ chế pause/resume, truyền backpressure hoặc tạm ngừng phát.
2. **Tăng năng lực consumer:** tối ưu xử lý, tăng concurrency có giới hạn hoặc phân bổ thêm worker khi tài nguyên phía sau cho phép.
3. **Giữ dữ liệu có giới hạn:** chọn capacity phù hợp với burst mà hệ thống cần hấp thụ và đặt chính sách overflow.
4. **Bỏ dữ liệu có chọn lọc:** chỉ dùng khi nghiệp vụ chấp nhận mất sự kiện, đồng thời đo số lượng bị bỏ.
5. **Từ chối hoặc báo lỗi:** nếu không thể bảo đảm xử lý đúng hạn, kết thúc sớm và để tầng gọi quyết định retry hoặc fallback.

Một cách ước lượng capacity là xem producer nhanh hơn consumer bao nhiêu phần tử mỗi giây và hệ thống cần hấp thụ burst trong bao lâu:

\[
\text{Capacity cần thiết} \approx
(\text{tốc độ đến} - \text{tốc độ xử lý})
\times \text{thời gian burst}
\]

Giả sử producer có thể gửi 1.000 sự kiện/giây, consumer xử lý được 700 sự kiện/giây và hệ thống cần hấp thụ burst kéo dài 2 giây. Phần chênh lệch tích lũy ước tính là 600 sự kiện. Đây là mức tham khảo ban đầu; cần cộng biên an toàn, xem kích thước phần tử, thời gian xử lý thực tế và khả năng phục hồi sau burst.

Nếu producer tiếp tục nhanh hơn consumer sau khi burst kết thúc, hàng đợi vẫn tăng. Không có capacity hữu hạn nào giải quyết được sự mất cân bằng kéo dài; cần điều chỉnh tốc độ hoặc năng lực xử lý.

## 7. Phân biệt hàng đợi, prefetch và backpressure

Ba khái niệm có liên quan nhưng trả lời các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Hàng đợi | Phần tử đã phát nhưng chưa xử lý đang được giữ ở đâu? | Queue tại publishOn hoặc buffer |
| Prefetch | Toán tử yêu cầu trước bao nhiêu phần tử để có dữ liệu sẵn? | publishOn(scheduler, 16), flatMap(..., 8, 4) |
| Backpressure | Subscriber báo khả năng tiêu thụ như thế nào? | request(n), cancel() |

Hàng đợi lưu phần tử. Prefetch quyết định lượng dữ liệu được yêu cầu trước để lấp hàng đợi hoặc phục vụ xử lý. Backpressure là cơ chế phối hợp nhu cầu giữa các thành phần. Chỉ tăng prefetch hoặc capacity mà không kiểm soát tốc độ đến và tốc độ xử lý có thể làm vấn đề bộ nhớ nghiêm trọng hơn.

Backpressure cũng không có nghĩa toàn bộ ứng dụng không thể có hàng đợi. Một pipeline có thể tuân thủ Reactive Streams ở ranh giới Publisher–Subscriber nhưng vẫn tích lũy dữ liệu trong các queue do toán tử, adapter, client hoặc hệ thống message broker quản lý. Cần quan sát cả pipeline lẫn các thành phần tích hợp.

## 8. Quan sát queue và demand trong vận hành

Để xác định một ranh giới đang gây nghẽn, hãy quan sát các chỉ số tại cả upstream và downstream:

- **Số phần tử được yêu cầu:** theo dõi request qua doOnRequest ở các vị trí trước và sau ranh giới.
- **Tốc độ phát và tốc độ xử lý:** so sánh số phần tử/giây ở hai phía của queue.
- **Độ sâu hàng đợi:** đo số phần tử đang chờ nếu thành phần cung cấp metric này.
- **Thời gian chờ:** đo thời gian một phần tử nằm trong queue trước khi được xử lý.
- **Overflow và drop:** đếm số phần tử bị bỏ hoặc số lần queue đầy.
- **Concurrency và prefetch:** ghi lại cấu hình thực tế của flatMap, publishOn và các toán tử liên quan.
- **Bộ nhớ:** theo dõi heap, allocation rate và GC pause, nhất là khi phần tử chứa object graph lớn.

Có thể đặt hook để quan sát demand và phần tử:

~~~java
Flux<Event> pipeline =
    eventSource()
        .doOnRequest(n -> metrics.recordUpstreamRequest(n))
        .doOnNext(event -> metrics.recordReceived())
        .publishOn(Schedulers.parallel(), 32)
        .doOnNext(event -> metrics.recordProcessed());
~~~

Ví dụ minh họa vị trí đo. Tên metrics đại diện cho API của ứng dụng. Hook trước publishOn đo phía nhận từ nguồn; hook sau publishOn đo phần tử đã đi qua ranh giới và tới bước xử lý phía sau. Nếu xử lý phía sau có thể lỗi, hủy hoặc bỏ phần tử ở toán tử tiếp theo, cần đặt thêm metric ở đúng điểm muốn thống kê.

Không nên chỉ đo tổng số phần tử ở cuối pipeline. Nếu số lượng đầu ra giảm, nguyên nhân có thể là filter, drop, lỗi, cancel hoặc nguồn phát ít dữ liệu. Đặt chỉ số ở các ranh giới giúp phân biệt các trường hợp này.

## 9. Kiểm thử demand và ranh giới bất đồng bộ

StepVerifier cho phép tạo subscriber có demand ban đầu xác định. Có thể dùng doOnRequest để quan sát request mà một toán tử gửi về upstream.

~~~java
AtomicLong upstreamRequested = new AtomicLong();

Flux<Integer> pipeline =
    Flux.range(1, 100)
        .doOnRequest(upstreamRequested::addAndGet)
        .publishOn(Schedulers.parallel(), 8);

StepVerifier.create(pipeline, 0)
    .thenRequest(1)
    .expectNext(1)
    .thenCancel()
    .verify();

assertTrue(upstreamRequested.get() > 0);
~~~

Subscriber cuối bắt đầu với demand bằng không. Tuy vậy, publishOn có thể prefetch từ nguồn theo cấu hình 8 phần tử để lấp hàng đợi. Kiểm thử chỉ xác nhận upstream đã nhận request; không nên dựa vào một con số nội bộ chính xác nếu phiên bản Reactor hoặc cấu trúc pipeline thay đổi.

Kiểm thử thay đổi đơn vị demand qua buffer:

~~~java
AtomicLong sourceDemand = new AtomicLong();

Flux<List<Integer>> batches =
    Flux.range(1, 20)
        .doOnRequest(sourceDemand::addAndGet)
        .buffer(4);

StepVerifier.create(batches, 0)
    .thenRequest(1)
    .expectNext(List.of(1, 2, 3, 4))
    .thenCancel()
    .verify();

assertTrue(sourceDemand.get() >= 4);
~~~

Một yêu cầu batch cần nguồn cung cấp các phần tử để tạo batch. Ví dụ xác nhận demand đã truyền lên nguồn, đồng thời kiểm tra giá trị batch được phát. Nếu thay đổi toán tử hoặc cấu hình prefetch, hãy đánh giá lại ranh giới đang đo thay vì cố định giả định về tổng request.

Với các nguồn nóng hoặc scheduler có thời gian thực thi riêng, hãy tránh kiểm thử bằng sleep. Dùng StepVerifier, TestPublisher hoặc scheduler ảo của Reactor khi phù hợp để điều khiển thời gian và tín hiệu một cách xác định.

## 10. Quy trình chọn queue và prefetch

Khi thêm một ranh giới bất đồng bộ vào pipeline, hãy lần lượt trả lời:

1. **Vì sao cần tách scheduler?** Xác định bước nào cần chạy trên luồng khác, ví dụ I/O chặn hay phép tính CPU.
2. **Phần tử có kích thước bao nhiêu?** Đánh giá heap thực tế mà một queue có thể giữ.
3. **Consumer cần bao nhiêu dữ liệu sẵn sàng?** Chọn prefetch nhỏ trước, sau đó đo thời gian chờ và throughput.
4. **Có bao nhiêu ranh giới và Publisher con?** Tính đến tổng lượng queue có thể tồn tại, concurrency và prefetch của từng nhánh.
5. **Nguồn có tuân theo request không?** Nếu có, để backpressure điều tiết. Nếu không, chọn buffer có giới hạn, drop, latest hoặc error theo nghiệp vụ.
6. **Điều gì xảy ra khi queue đầy?** Xác định cách báo lỗi, retry, từ chối hoặc bỏ dữ liệu.
7. **Đo ở đâu?** Theo dõi demand, tốc độ vào/ra, độ sâu queue, độ trễ chờ và bộ nhớ.

Không nên tăng prefetch chỉ để làm một benchmark ngắn nhanh hơn. Hãy thử cả tải ổn định, burst, consumer chậm, nguồn lỗi và tình huống hủy. Một cấu hình tốt cần giữ throughput phù hợp mà không làm độ trễ và bộ nhớ tăng mất kiểm soát.

## 11. Bài tập vận dụng

Một hệ thống nhận 2.000 sự kiện đơn hàng mỗi giây từ một nguồn nóng. Dịch vụ làm giàu dữ liệu xử lý trung bình 1.500 sự kiện mỗi giây, nhưng có thể tăng lên 2.200 sự kiện mỗi giây trong thời gian ngắn. Mỗi sự kiện sau khi làm giàu chiếm trung bình 4 KB trong bộ nhớ. Client cuối đôi khi chỉ yêu cầu dữ liệu theo từng batch 50 phần tử.

Hãy thiết kế pipeline và chính sách queue:

1. Chọn vị trí publishOn nếu bước làm giàu cần chạy trên scheduler riêng. Chọn prefetch ban đầu và giải thích tác động lên lượng dữ liệu chờ.
2. Xác định có nên dùng buffer(50) để tạo batch cho client. Giải thích vì sao một demand cho batch khác với demand cho một sự kiện.
3. Nếu dùng flatMap để gọi dịch vụ làm giàu bất đồng bộ, chọn concurrency và prefetch theo giới hạn kết nối cùng năng lực dịch vụ.
4. Vì nguồn nóng không thể giảm tốc độ, chọn giữa buffer có giới hạn, drop, latest hoặc error. Giải thích ảnh hưởng nghiệp vụ của việc bỏ sự kiện.
5. Ước lượng lượng bộ nhớ queue trong một burst và đề xuất metric để cảnh báo khi queue gần đầy.
6. Viết một kiểm thử StepVerifier bắt đầu với demand bằng không, yêu cầu một batch và xác nhận nguồn nhận request qua ranh giới buffer.

Một lời giải tốt cần làm rõ nơi dữ liệu được giữ, đơn vị demand ở từng tầng, chính sách khi queue đầy và cách hệ thống phục hồi sau burst. Không có một con số prefetch đúng cho mọi ứng dụng; hãy bắt đầu từ giới hạn tài nguyên và xác nhận bằng đo tải.

## Kết luận

Hàng đợi tách tốc độ phát và tiêu thụ ở các ranh giới bất đồng bộ. Prefetch cho phép toán tử yêu cầu trước dữ liệu để duy trì công việc, còn các toán tử như buffer và flatMap làm thay đổi đơn vị demand hoặc lượng xử lý đồng thời. Khi nguồn không thể tuân theo request, ứng dụng phải chọn chính sách rõ ràng cho dữ liệu dư thừa: giữ có giới hạn, bỏ, giữ giá trị mới nhất hoặc báo lỗi. Hiểu các ranh giới này giúp kiểm soát bộ nhớ, độ trễ và backpressure xuyên suốt pipeline Reactor.
