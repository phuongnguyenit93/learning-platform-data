# window: chia nguồn thành các luồng con

Trong xử lý reactive, nhiều bài toán cần chia một luồng dữ liệu lớn thành các phần nhỏ để xử lý theo lô, theo khoảng thời gian hoặc theo một tín hiệu ranh giới. Ví dụ, một hệ thống nhận sự kiện đơn hàng liên tục nhưng muốn tổng hợp mỗi 100 sự kiện; một dịch vụ giám sát muốn tính số liệu theo từng phút; hoặc một pipeline log muốn gom các bản ghi cho đến khi gặp dấu phân cách. Reactor cung cấp nhóm toán tử **window** để chia một publisher thành nhiều publisher con.

Điểm quan trọng là window trả về một luồng bên ngoài chứa các luồng bên trong. Với Flux<T>, kết quả có kiểu khái niệm Flux<Flux<T>>: mỗi phần tử của luồng ngoài là một Flux<T> đại diện cho một cửa sổ. Khác với buffer, vốn thường phát một collection sau khi thu thập xong, window cho phép tiêu thụ các phần tử trong cửa sổ như một luồng riêng. Cách tổ chức lồng nhau này hữu ích nhưng đòi hỏi phải quản lý việc subscribe, thứ tự xử lý, demand và vòng đời của từng cửa sổ.

## 1. Window là gì?

Một cửa sổ (window) là một nhóm phần tử được chọn từ nguồn theo một quy tắc mở và đóng. Quy tắc có thể dựa trên số lượng phần tử, thời gian hoặc một publisher phát tín hiệu ranh giới.

Ví dụ, nguồn phát:

~~~text
1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8
~~~

Chia thành các cửa sổ có tối đa ba phần tử sẽ tạo:

~~~text
Window 1: 1 -> 2 -> 3
Window 2: 4 -> 5 -> 6
Window 3: 7 -> 8
~~~

Cửa sổ cuối có thể ít phần tử hơn kích thước tối đa vì nguồn đã hoàn tất. window không đòi hỏi mọi cửa sổ đều đầy đủ.

Trong Reactor:

~~~java
Flux<Flux<Integer>> windows = Flux.range(1, 8)
    .window(3);
~~~

windows là publisher bên ngoài. Mỗi phần tử của nó là một publisher con chứa tối đa ba số nguyên. Việc tạo biến windows chỉ lắp ráp pipeline; các cửa sổ được phát khi có subscription và dữ liệu đi qua nguồn.

## 2. Phân biệt window với buffer

window và buffer đều chia một luồng thành nhóm, nhưng kiểu kết quả và cách tiêu thụ khác nhau.

| Đặc điểm | window | buffer |
| --- | --- | --- |
| Kiểu kết quả | Flux<Flux<T>> | Flux<List<T>> hoặc collection tương ứng |
| Dữ liệu bên trong | Một publisher con | Một collection đã được thu thập |
| Thời điểm có thể xử lý | Có thể subscribe và xử lý phần tử khi cửa sổ đang mở | Thường nhận collection khi buffer đóng |
| Bộ nhớ | Có thể xử lý từng phần tử theo luồng nếu inner publisher được tiêu thụ kịp | Phải giữ các phần tử của buffer đến khi phát collection |
| Cách xử lý | Compose inner publisher bằng flatMap, concatMap hoặc toán tử khác | Xử lý collection được phát ra |

Ví dụ buffer:

~~~java
Flux<List<Integer>> batches = Flux.range(1, 8)
    .buffer(3);
~~~

Kết quả là các collection [1, 2, 3], [4, 5, 6], [7, 8].

Ví dụ window:

~~~java
Flux<List<Integer>> batches = Flux.range(1, 8)
    .window(3)
    .concatMap(window -> window.collectList());
~~~

Đoạn mã cũng tạo các list có cùng nội dung như ví dụ buffer, nhưng mỗi cửa sổ được biểu diễn trước tiên bằng một publisher con. collectList thu thập phần tử của cửa sổ đó thành một list khi cửa sổ hoàn tất.

Nếu mục tiêu chỉ là tạo một list nhỏ để ghi database theo lô, buffer có thể đơn giản hơn. Nếu cần xử lý từng phần tử trong cửa sổ, compose một luồng con, hoặc kiểm soát cách mỗi cửa sổ được tiêu thụ, window mang lại tính linh hoạt cao hơn. Dùng window(...).collectList() cũng sẽ giữ dữ liệu trong bộ nhớ như buffer; chỉ dùng window không tự bảo đảm bộ nhớ thấp.

## 3. Window theo số lượng phần tử

### Cửa sổ không chồng lấn

window(maxSize) mở cửa sổ theo từng nhóm có tối đa maxSize phần tử. Khi cửa sổ đủ số lượng, nó đóng và cửa sổ tiếp theo được tạo cho các phần tử kế tiếp.

~~~java
Flux<Flux<OrderEvent>> windows = orderEvents
    .window(100);
~~~

Mỗi cửa sổ nhận tối đa 100 OrderEvent. Đây là cách phù hợp khi muốn xử lý một số lượng sự kiện cố định trong mỗi nhóm, ví dụ kiểm tra một lô, ghi theo batch hoặc tính tổng theo nhóm.

### Chia cửa sổ có khoảng mở mới riêng

Overload window(maxSize, skip) cho phép xác định kích thước cửa sổ và khoảng cách giữa thời điểm mở các cửa sổ liên tiếp. maxSize là số phần tử tối đa trong một cửa sổ; skip là số phần tử nguồn giữa hai lần mở cửa sổ.

~~~java
Flux<Flux<Integer>> windows = Flux.range(1, 10)
    .window(5, 3);
~~~

Vì cửa sổ mới được mở sau mỗi ba phần tử trong khi mỗi cửa sổ giữ tối đa năm phần tử, các cửa sổ chồng lấn:

~~~text
Window 1: 1, 2, 3, 4, 5
Window 2:       4, 5, 6, 7, 8
Window 3:             7, 8, 9, 10
Window 4:                   10
~~~

Các phần tử ở vùng chồng lấn xuất hiện trong nhiều cửa sổ. Đây là hành vi có chủ đích của cấu hình overlap, không phải phần tử bị phát trùng do lỗi. Cần tính đến chi phí xử lý lặp nếu mỗi cửa sổ thực hiện side effect.

Nếu skip lớn hơn maxSize, sẽ có khoảng trống giữa các cửa sổ:

~~~java
Flux<Flux<Integer>> windows = Flux.range(1, 12)
    .window(2, 4);
~~~

Các cửa sổ nhận:

~~~text
Window 1: 1, 2
Gap:          3, 4
Window 2:             5, 6
Gap:                   7, 8
Window 3:                         9, 10
Gap:                                      11, 12
~~~

Những phần tử nằm trong gap không thuộc cửa sổ nào và không xuất hiện trong output của toán tử. Vì vậy, chỉ dùng cấu hình gap khi nghiệp vụ cho phép bỏ qua các phần tử đó hoặc khi một pipeline khác xử lý chúng.

| Quan hệ giữa skip và maxSize | Kết quả |
| --- | --- |
| skip == maxSize | Các cửa sổ liên tiếp, không chồng lấn và không có gap |
| skip < maxSize | Các cửa sổ chồng lấn; một phần tử có thể thuộc nhiều cửa sổ |
| skip > maxSize | Có gap; một số phần tử không thuộc cửa sổ nào |

## 4. Window theo thời gian

Với nguồn phát liên tục, số phần tử trong một cửa sổ có thể thay đổi rất nhiều. Thay vì đóng cửa sổ sau một số lượng cố định, có thể đóng theo thời gian.

window(Duration timespan) tạo các cửa sổ theo khoảng thời gian liên tiếp:

~~~java
Flux<Flux<Metric>> windows = metrics
    .window(Duration.ofSeconds(10));
~~~

Mỗi cửa sổ đại diện cho một khoảng 10 giây theo scheduler timer của Reactor. Cửa sổ đóng khi hết khoảng thời gian; cửa sổ tiếp theo được mở theo chu kỳ. Một cửa sổ có thể chứa nhiều, ít hoặc không có phần tử nếu nguồn không phát trong khoảng đó.

Thời gian của toán tử là thời gian xử lý (processing time) theo scheduler, không tự động là timestamp nghiệp vụ gắn trong từng event. Nếu sự kiện đến trễ nhưng mang timestamp thuộc một khoảng thời gian trước đó, window(Duration) vẫn phân loại theo thời điểm nó được đưa vào pipeline. Bài toán event-time với watermark và xử lý late event cần một mô hình khác hoặc một stream-processing engine hỗ trợ semantics đó.

### Cửa sổ thời gian chồng lấn hoặc có khoảng trống

Overload window(timespan, openWindowEvery) tách thời lượng mỗi cửa sổ khỏi chu kỳ mở cửa sổ mới:

~~~java
Flux<Flux<Metric>> windows = metrics
    .window(
        Duration.ofSeconds(10),
        Duration.ofSeconds(5)
    );
~~~

Mỗi cửa sổ mở cách nhau 5 giây và tồn tại trong 10 giây. Vì cửa sổ mới mở trước khi cửa sổ cũ đóng, hai cửa sổ chồng lấn trong 5 giây. Một metric đến trong vùng chồng lấn có thể được đưa vào cả hai cửa sổ đang mở.

Nếu khoảng mở mới lớn hơn thời lượng cửa sổ, sẽ có khoảng thời gian không cửa sổ nào mở; các phần tử đến trong khoảng đó không thuộc cửa sổ nào. Vì vậy:

| Cấu hình thời gian | Hành vi |
| --- | --- |
| openWindowEvery == timespan | Các cửa sổ liên tiếp, không chồng lấn |
| openWindowEvery < timespan | Cửa sổ chồng lấn; một phần tử có thể xuất hiện trong nhiều cửa sổ |
| openWindowEvery > timespan | Có gap; phần tử đến trong khoảng trống không thuộc cửa sổ |

Khi dùng cửa sổ thời gian, cần xác định múi thời gian, độ chính xác timer, scheduler và cách xử lý phần tử sát ranh giới. Với dữ liệu nghiệp vụ cần phân loại theo timestamp nguồn, không nên dùng thời điểm callback được xử lý làm timestamp thay thế.

## 5. Kết hợp giới hạn số lượng và thời gian

windowTimeout(maxSize, maxTimeSpan) đóng cửa sổ khi đạt một trong hai điều kiện: đủ số lượng phần tử hoặc hết thời gian tối đa. Cách này hữu ích khi muốn batch có kích thước không quá lớn nhưng cũng không muốn dữ liệu ít phải chờ quá lâu.

~~~java
Flux<Flux<AuditEvent>> windows = auditEvents
    .windowTimeout(200, Duration.ofSeconds(2));
~~~

Một cửa sổ đóng khi nhận đủ 200 sự kiện hoặc sau tối đa hai giây. Nếu sự kiện đến chậm, timer vẫn giúp phát cửa sổ nhỏ hơn để downstream xử lý. Nếu sự kiện đến nhanh, giới hạn số lượng đóng cửa sổ trước khi hết hai giây.

Đây là lựa chọn phổ biến cho batch I/O: giới hạn số bản ghi mỗi lần ghi và giới hạn độ trễ chờ gom đủ batch. Cần cân nhắc kích thước payload, thời gian ghi, giới hạn connection pool và concurrency của downstream. maxSize giới hạn số phần tử, không giới hạn trực tiếp số byte của batch.

## 6. Chia cửa sổ theo tín hiệu ranh giới

Không phải mọi cửa sổ đều được xác định bằng số lượng hoặc timer. Một nguồn khác có thể phát tín hiệu đánh dấu ranh giới, ví dụ sự kiện đổi phiên, dấu phân cách trong file hoặc tín hiệu bắt đầu/kết thúc một chu kỳ nghiệp vụ.

Reactor có các overload window nhận publisher ranh giới, cũng như windowWhen cho trường hợp có publisher mở cửa sổ và một publisher đóng tương ứng. Ví dụ, một publisher ranh giới phát tín hiệu mỗi khi cần kết thúc cửa sổ hiện tại và bắt đầu cửa sổ tiếp theo:

~~~java
Flux<Flux<LogEntry>> windows = logEntries
    .window(rolloverSignals);
~~~

Ví dụ giả định rolloverSignals là publisher phát tín hiệu ranh giới theo hợp đồng của nguồn. Cần kiểm tra semantics của overload cụ thể về thời điểm mở cửa sổ đầu tiên và cách xử lý khi publisher ranh giới hoàn tất hoặc lỗi. Không nên coi tín hiệu ranh giới như một phần tử dữ liệu của nguồn chính; nó điều khiển cách chia nhóm.

Với cửa sổ động, cần bảo đảm publisher mở/đóng có lifecycle phù hợp. Nếu publisher đóng không bao giờ phát, cửa sổ có thể tồn tại lâu hơn dự kiến. Nếu tín hiệu mở đến quá nhanh, số cửa sổ đang hoạt động có thể tăng và tạo áp lực tài nguyên.

## 7. Tiêu thụ các publisher con

Vì window phát một publisher con cho mỗi cửa sổ, pipeline cần tiêu thụ các publisher con đó. Có ba cách thường gặp:

### Xử lý tuần tự bằng concatMap

~~~java
Flux<BatchResult> results = events
    .window(100)
    .concatMap(window ->
        window.collectList()
            .flatMap(batchService::persist)
    );
~~~

concatMap subscribe và xử lý từng cửa sổ theo thứ tự. Cửa sổ tiếp theo được xử lý sau khi publisher xử lý cửa sổ hiện tại hoàn tất. Cách này hữu ích khi thứ tự batch phải được giữ hoặc database chỉ nên nhận một batch tại một thời điểm.

### Xử lý nhiều cửa sổ đồng thời bằng flatMap

~~~java
Flux<BatchResult> results = events
    .window(100)
    .flatMap(
        window -> window.collectList()
            .flatMap(batchService::persist),
        4
    );
~~~

Tham số concurrency giới hạn số publisher xử lý cửa sổ được subscribe đồng thời theo semantics của flatMap. Cách này có thể tăng throughput khi các batch độc lập, nhưng kết quả có thể phát theo thứ tự hoàn tất thay vì thứ tự cửa sổ. Cần bảo đảm thao tác persist an toàn khi chạy song song và connection pool có đủ tài nguyên.

### Xử lý đồng thời nhưng giữ thứ tự phát kết quả

~~~java
Flux<BatchResult> results = events
    .window(100)
    .flatMapSequential(
        window -> window.collectList()
            .flatMap(batchService::persist),
        4
    );
~~~

flatMapSequential có thể subscribe các publisher con đồng thời nhưng giữ thứ tự phát kết quả theo thứ tự nguồn. Nếu một batch phía trước chậm, kết quả của batch sau có thể phải chờ trong hàng đợi để bảo toàn thứ tự.

Chọn toán tử theo yêu cầu nghiệp vụ: concatMap cho xử lý tuần tự, flatMap cho concurrency khi thứ tự không quan trọng, và flatMapSequential khi cần concurrency nhưng vẫn giữ thứ tự downstream. Giới hạn concurrency không thay thế giới hạn buffer hoặc chính sách quá tải.

## 8. Không bỏ quên inner window

Một lỗi thiết kế thường gặp là subscribe luồng ngoài nhưng không tiêu thụ các publisher con:

~~~java
events.window(100)
    .subscribe(window -> log("Có một window mới"));
~~~

Đoạn mã chỉ quan sát việc cửa sổ được phát ra, nhưng không đăng ký để xử lý các phần tử bên trong từng cửa sổ. Với pipeline thật, hãy compose inner publisher bằng flatMap, concatMap, flatMapSequential hoặc một toán tử thích hợp khác.

Tránh gọi subscribe thủ công bên trong callback của subscribe ngoài:

~~~java
// Không nên: tự tạo subscription tách rời cho từng inner window.
events.window(100)
    .subscribe(window -> window.subscribe(this::process));
~~~

Cách viết này tạo các subscription lồng nhau mà caller khó quản lý lỗi, cancellation và thứ tự. Nếu outer subscription bị hủy, các inner subscription được tạo thủ công không nhất thiết được quản lý theo lifecycle mà bạn mong muốn. Hãy dùng toán tử flatten để Reactor điều phối quan hệ giữa outer và inner publisher.

## 9. Window và backpressure

Window tạo hai tầng publisher:

- Tầng ngoài phát các cửa sổ.
- Tầng trong phát các phần tử thuộc từng cửa sổ.

Subscriber cần demand để nhận cửa sổ từ tầng ngoài và demand cho từng inner publisher để nhận phần tử. Vì vậy, tiêu thụ window cần xem xét cả số cửa sổ đang hoạt động và số phần tử đang chờ trong mỗi cửa sổ.

Một số rủi ro cần kiểm soát:

- Inner window không được subscribe: phần tử không được tiêu thụ như mong đợi và có thể làm tăng áp lực buffer.
- Quá nhiều cửa sổ đồng thời: đặc biệt với overlap hoặc nguồn mở cửa sổ nhanh, nhiều inner publisher có thể cùng tồn tại.
- Inner consumer chậm: dữ liệu của cửa sổ có thể phải chờ trong hàng đợi; cần giới hạn concurrency và buffer.
- Gom toàn bộ cửa sổ vào collection: collectList giữ mọi phần tử của cửa sổ trong bộ nhớ đến khi inner publisher hoàn tất.
- Side effect lặp do overlap: một phần tử thuộc nhiều cửa sổ có thể được xử lý nhiều lần.
- Nguồn push không hỗ trợ demand: adapter vẫn cần buffer, drop, latest hoặc chính sách quá tải phù hợp.

Backpressure không làm cho một cửa sổ lớn trở nên miễn phí. Nếu mỗi cửa sổ có hàng triệu phần tử hoặc nhiều cửa sổ chồng lấn, số dữ liệu đang được giữ vẫn có thể rất lớn. Hãy chọn kích thước, thời gian, concurrency và cách tiêu thụ dựa trên ngân sách bộ nhớ và độ trễ.

## 10. Ví dụ: gom sự kiện đơn hàng theo batch để ghi

Giả sử một dịch vụ nhận OrderEvent liên tục. Database có thể ghi hiệu quả hơn khi nhận batch, nhưng hệ thống không muốn chờ vô hạn để gom đủ số lượng.

~~~java
Flux<WriteResult> writes = orderEvents
    .windowTimeout(100, Duration.ofSeconds(1))
    .concatMap(window ->
        window.collectList()
            .filter(batch -> !batch.isEmpty())
            .flatMap(batch -> orderEventRepository.insertBatch(batch))
    );
~~~

Pipeline chia sự kiện thành các cửa sổ tối đa 100 phần tử hoặc tối đa một giây. Khi cửa sổ đóng, collectList tạo một list; filter bỏ batch rỗng nếu có; insertBatch thực hiện thao tác ghi. concatMap giữ thứ tự batch và chỉ xử lý một batch tại một thời điểm.

Trong ứng dụng thực tế, cần quyết định:

- insertBatch có trả Mono<WriteResult> hay một publisher khác.
- Điều gì xảy ra nếu một batch ghi thất bại: retry, lưu vào dead-letter, phát lỗi hay tiếp tục với batch sau.
- Có cần idempotency key để tránh ghi trùng khi retry.
- Database giới hạn batch size, transaction duration và số kết nối ra sao.
- Có cần concurrency lớn hơn một để tăng throughput hay phải giữ thứ tự sự kiện.
- Sự kiện có cần được lưu bền trước khi đưa vào pipeline hay không.

windowTimeout giúp cân bằng kích thước batch và độ trễ chờ, nhưng không tự cung cấp durability hoặc retry semantics. Nếu nguồn là message broker, acknowledgement nên gắn với kết quả xử lý batch theo semantics của broker để tránh xác nhận dữ liệu trước khi ghi thành công.

## 11. Ví dụ: tính số liệu theo cửa sổ thời gian

Một hệ thống giám sát có thể tính số lượng request trong mỗi khoảng 30 giây:

~~~java
Flux<Long> requestCounts = requestEvents
    .window(Duration.ofSeconds(30))
    .concatMap(window -> window.count());
~~~

Mỗi inner window được đếm khi đóng và phát ra một Long. Nếu khoảng thời gian không có request, tùy semantics nguồn và window timer, có thể có cửa sổ rỗng với count bằng 0. Điều này có thể hữu ích cho biểu đồ theo thời gian, nhưng cần kiểm tra cách toán tử và nguồn tạo cửa sổ rỗng trong cấu hình thực tế.

Nếu cần cả số lượng, tổng latency và latency tối đa, có thể reduce từng cửa sổ thành một đối tượng thống kê:

~~~java
Flux<RequestStats> stats = requestEvents
    .window(Duration.ofSeconds(30))
    .flatMap(window ->
        window.reduce(
            RequestStats.empty(),
            RequestStats::add
        )
    );
~~~

reduce giữ một accumulator thay vì gom toàn bộ event thành list. Với cửa sổ lớn, cách này thường tiết kiệm bộ nhớ hơn nếu phép tổng hợp có thể thực hiện tăng dần. Cần đảm bảo hàm add không làm thay đổi một accumulator dùng chung giữa các subscription.

## 12. Kiểm thử window theo số lượng

StepVerifier có thể xác minh các nhóm được tạo bởi window:

~~~java
Flux<List<Integer>> batches = Flux.range(1, 7)
    .window(3)
    .concatMap(Flux::collectList);

StepVerifier.create(batches)
    .expectNext(List.of(1, 2, 3))
    .expectNext(List.of(4, 5, 6))
    .expectNext(List.of(7))
    .verifyComplete();
~~~

Test xác minh hai cửa sổ đầy và một cửa sổ cuối không đủ kích thước. Có thể kiểm tra overlap:

~~~java
Flux<List<Integer>> overlapping = Flux.range(1, 7)
    .window(4, 2)
    .concatMap(Flux::collectList);

StepVerifier.create(overlapping)
    .expectNext(List.of(1, 2, 3, 4))
    .expectNext(List.of(3, 4, 5, 6))
    .expectNext(List.of(5, 6, 7))
    .expectNext(List.of(7))
    .verifyComplete();
~~~

Test cho thấy các phần tử ở vùng overlap xuất hiện trong nhiều cửa sổ. Với gap, hãy xác minh các phần tử nằm giữa các cửa sổ không được phát ra trong bất kỳ list nào.

## 13. Kiểm thử window theo thời gian

Không nên dùng Thread.sleep để đợi cửa sổ thời gian đóng. Reactor Test có StepVerifier.withVirtualTime để điều khiển đồng hồ ảo và timer. Một bài test thời gian nên:

1. Tạo publisher bên trong supplier của withVirtualTime để scheduler ảo được cài trước khi pipeline được lắp ráp.
2. Dùng thenAwait hoặc then để tiến thời gian và phát tín hiệu theo kịch bản.
3. Thu thập hoặc đếm inner window để kiểm tra kết quả.
4. Xác minh complete, error hoặc cancellation đúng với lifecycle nguồn.

Ví dụ khung kiểm thử:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMillis(500))
            .take(5)
            .window(Duration.ofSeconds(2))
            .concatMap(Flux::count)
    )
    .thenAwait(Duration.ofSeconds(5))
    .expectNextCount(2)
    .verifyComplete();
~~~

Ví dụ minh họa cách đưa nguồn timer và window vào virtual time; số cửa sổ phát ra cần được xác minh theo semantics của phiên bản Reactor, thời điểm bắt đầu timer và việc cửa sổ rỗng có được phát hay không. Trong test cụ thể của dự án, nên dùng expectNext(...) với kết quả đã xác định từ cấu hình và bổ sung trường hợp event nằm sát ranh giới. Không dùng kết quả timing của một máy chạy thật làm oracle cho test thời gian.

## 14. Những lưu ý về thời gian và ranh giới

Cửa sổ theo thời gian phụ thuộc scheduler timer. Các yếu tố như tải scheduler, độ trễ callback và thời điểm subscribe có thể ảnh hưởng lúc ranh giới được xử lý. Với event có timestamp riêng, cần phân biệt:

- Processing time: thời điểm event được pipeline nhận và xử lý.
- Event time: thời điểm sự kiện thực sự xảy ra theo timestamp của nguồn.
- Arrival time: thời điểm event đến adapter hoặc ứng dụng.

window(Duration) trong Reactor chia theo timer của pipeline, thường dựa trên processing time. Nếu sự kiện đến muộn nhưng timestamp thuộc cửa sổ trước, toán tử không tự chuyển event về cửa sổ cũ. Xử lý event-time cần logic lưu giữ trạng thái, watermark, allowed lateness hoặc công cụ stream processing được thiết kế cho dữ liệu đến trễ.

Ở ranh giới chính xác giữa hai cửa sổ, event và timer có thể được xử lý cạnh nhau. Nếu nghiệp vụ yêu cầu quy tắc bao gồm/exclude timestamp cụ thể, hãy định nghĩa ranh giới rõ và kiểm thử các trường hợp sát biên bằng virtual time hoặc publisher điều khiển.

## 15. Những lỗi thường gặp

- **Nhầm window trả collection:** window trả publisher con; dùng collectList nếu thật sự cần list.
- **Không tiêu thụ inner publisher:** subscribe outer nhưng bỏ qua inner window khiến dữ liệu không được xử lý đúng.
- **Subscribe thủ công bên trong callback:** tạo subscription tách rời, khó quản lý lỗi và cancellation; dùng flatten operator.
- **Dùng overlap mà không tính xử lý trùng:** một phần tử có thể thuộc nhiều cửa sổ và gây side effect lặp.
- **Dùng gap nhưng mong mọi phần tử được giữ:** phần tử trong khoảng trống không thuộc cửa sổ nào.
- **Gom cửa sổ rất lớn thành list:** collectList giữ toàn bộ phần tử trong heap; cân nhắc reduce hoặc giới hạn kích thước.
- **Dùng window thời gian cho event-time:** timer chia theo thời điểm pipeline xử lý, không theo timestamp nghiệp vụ của event.
- **Không giới hạn concurrency:** nhiều cửa sổ được xử lý đồng thời có thể làm cạn connection pool hoặc tăng hàng đợi.
- **Giả định batch cuối luôn đầy:** khi nguồn complete hoặc error, cửa sổ cuối có thể ít phần tử hơn giới hạn.
- **Bỏ qua lỗi của inner publisher:** lỗi khi xử lý một cửa sổ có thể kết thúc pipeline ngoài; cần xác định retry/fallback theo batch.
- **Dùng buffer để thay thế window mà không xét kiểu tiêu thụ:** collection và inner publisher có semantics bộ nhớ, thời điểm phát khác nhau.
- **Dùng timer test với sleep:** test dễ flaky; dùng virtual time và kiểm soát nguồn.

## 16. Quy trình chọn cách chia cửa sổ

Trước khi dùng window, hãy trả lời các câu hỏi:

1. Cửa sổ được xác định theo số lượng, thời gian hay tín hiệu nghiệp vụ?
2. Có cần overlap để một phần tử tham gia nhiều nhóm không?
3. Có gap mà phần tử không thuộc nhóm nào không, và nghiệp vụ có chấp nhận bỏ qua chúng không?
4. Cửa sổ cuối khi nguồn complete có thể chưa đủ kích thước không?
5. Cần xử lý inner window tuần tự, song song hay song song nhưng giữ thứ tự kết quả?
6. Inner window sẽ được xử lý streaming, reduce hay collect thành collection?
7. Kích thước cửa sổ, thời gian sống, concurrency và buffer có nằm trong ngân sách tài nguyên không?
8. Nguồn có hỗ trợ backpressure hay cần overflow policy ở adapter?
9. Thời gian là processing time hay event time? Cần xử lý late event không?
10. Khi một cửa sổ lỗi hoặc bị hủy, tài nguyên và các cửa sổ còn lại được quản lý ra sao?

window chia một nguồn thành các publisher con để pipeline xử lý theo nhóm mà vẫn giữ mô hình reactive. Dùng window(maxSize) cho nhóm theo số lượng, window(maxSize, skip) khi cần overlap hoặc gap, window(Duration) cho chu kỳ thời gian, và windowTimeout khi cần giới hạn cả kích thước lẫn thời gian chờ. Hãy tiêu thụ inner publisher bằng các toán tử compose, chọn concurrency theo yêu cầu thứ tự, giới hạn bộ nhớ và kiểm thử ranh giới bằng StepVerifier. Khi phân biệt rõ window với buffer và processing time với event time, việc chia luồng trong Reactor sẽ dễ dự đoán và phù hợp hơn với yêu cầu xử lý dữ liệu thực tế.
