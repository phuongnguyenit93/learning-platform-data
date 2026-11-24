# Lợi ích, chi phí và những trường hợp không phù hợp

Reactive Programming giúp mô hình hóa dữ liệu và sự kiện đến theo thời gian, đặc biệt khi một ứng dụng phải chờ nhiều nguồn I/O, xử lý luồng dữ liệu liên tục hoặc phối hợp các tác vụ bất đồng bộ. Với Java, Reactor cung cấp `Mono` và `Flux` để biểu diễn các pipeline; Reactive Streams định nghĩa hợp đồng trao đổi dữ liệu giữa `Publisher` và `Subscriber`, trong đó subscriber có thể điều tiết nhu cầu bằng backpressure.

Những khả năng này có thể giúp hệ thống sử dụng tài nguyên hiệu quả, phản hồi sớm và kiểm soát luồng dữ liệu. Tuy nhiên, reactive không tự động làm chương trình nhanh hơn, không biến một thư viện blocking thành non-blocking và cũng không loại bỏ độ phức tạp. Chọn reactive là quyết định về mô hình thực thi và cách tổ chức toàn bộ đường đi của dữ liệu. Cần cân nhắc lợi ích đối với tải thực tế, chi phí triển khai và năng lực vận hành của đội ngũ.

## 1. Reactive giải quyết vấn đề nào?

Trong mô hình đồng bộ truyền thống, một luồng thường gọi hàm, chờ kết quả rồi mới thực hiện bước tiếp theo. Khi lời gọi phải chờ mạng, cơ sở dữ liệu hoặc một dịch vụ bên ngoài, luồng thực thi có thể bị giữ lại dù CPU không làm việc. Nếu mỗi request chiếm một thread trong suốt thời gian chờ, số lượng thread và bộ nhớ dành cho chúng có thể tăng nhanh khi tải đồng thời tăng.

Mô hình bất đồng bộ cho phép đăng ký công việc và tiếp tục xử lý khi kết quả sẵn sàng. Reactive bổ sung cách biểu diễn kết quả như một luồng tín hiệu có thể kết hợp bằng toán tử, có thể hủy và có thể điều tiết nhu cầu. Trong Reactor:

- `Mono<T>` biểu diễn không hoặc một phần tử, kèm tín hiệu hoàn tất hoặc lỗi.
- `Flux<T>` biểu diễn không, một hoặc nhiều phần tử, sau đó có thể hoàn tất hoặc lỗi.
- `Publisher` phát các tín hiệu đến `Subscriber` theo hợp đồng Reactive Streams.
- `Subscription` cho phép subscriber yêu cầu một số lượng phần tử (`request(n)`) hoặc hủy đăng ký (`cancel()`).

Một pipeline `Mono` hoặc `Flux` thường chỉ mô tả công việc. Nó bắt đầu thực thi khi có subscriber đăng ký, chẳng hạn khi framework web đăng ký kết quả trả về hoặc khi chương trình gọi một thao tác kết thúc như `subscribe` hay `block`. Vì vậy, việc xây dựng pipeline và việc kích hoạt pipeline là hai việc khác nhau.

Reactive Streams quy định giao thức truyền tín hiệu và backpressure. Reactor là một thư viện triển khai các kiểu và toán tử phù hợp với giao thức đó. Spring WebFlux, WebClient và nhiều thư viện khác có thể tích hợp với Reactor, nhưng việc dùng một API trả về `Mono` hoặc `Flux` chưa đủ để bảo đảm toàn bộ ứng dụng đều non-blocking. Các thành phần ở hai đầu pipeline cũng phải hỗ trợ mô hình này hoặc được cô lập đúng cách.

## 2. Lợi ích khi áp dụng đúng

### 2.1. Sử dụng tài nguyên hiệu quả khi chờ I/O

Với I/O bất đồng bộ và non-blocking, một số lượng thread giới hạn có thể phục vụ nhiều tác vụ đang chờ mạng hoặc cơ sở dữ liệu. Thread không cần nằm chờ riêng cho từng request trong toàn bộ thời gian I/O. Điều này có thể giảm áp lực lên thread, stack memory và chi phí chuyển đổi ngữ cảnh khi ứng dụng có nhiều kết nối đồng thời.

Lợi ích rõ nhất thường xuất hiện ở hệ thống có thời gian chờ I/O lớn so với thời gian xử lý CPU, chẳng hạn API tổng hợp dữ liệu từ nhiều dịch vụ, gateway, hệ thống thông báo hoặc ứng dụng duy trì nhiều kết nối lâu dài. Kết quả phụ thuộc vào driver, client HTTP, connection pool, giới hạn tài nguyên và cấu hình scheduler. Chỉ đổi controller sang kiểu trả về `Mono` trong khi vẫn gọi JDBC blocking trên event-loop không tạo ra lợi ích này.

### 2.2. Kết hợp nhiều tác vụ bất đồng bộ một cách rõ ràng

Các toán tử Reactor thể hiện quan hệ giữa các bước trong pipeline. Có thể ánh xạ dữ liệu bằng `map`, chuyển sang publisher khác bằng `flatMap`, kết hợp các kết quả độc lập bằng `zip`, gom nhóm bằng `buffer`, hoặc xử lý từng phần tử bằng `concatMap` hay `flatMap` tùy yêu cầu về thứ tự và mức đồng thời.

Ví dụ, một API cần lấy hồ sơ người dùng và danh sách đơn hàng từ hai endpoint độc lập có thể khởi chạy hai request, sau đó ghép kết quả:

```java
Mono<User> user = webClient.get()
    .uri("/users/{id}", userId)
    .retrieve()
    .bodyToMono(User.class);

Mono<List<Order>> orders = webClient.get()
    .uri("/users/{id}/orders", userId)
    .retrieve()
    .bodyToFlux(Order.class)
    .collectList();

return Mono.zip(user, orders)
    .map(result -> new UserOverview(result.getT1(), result.getT2()))
    .timeout(Duration.ofSeconds(2))
    .onErrorMap(TimeoutException.class,
        error -> new UpstreamTimeoutException("Dịch vụ phản hồi quá chậm", error));
```

Ví dụ giả định `webClient`, `userId`, các kiểu dữ liệu và ngoại lệ đã được khai báo. `Mono.zip` phát kết quả khi cả hai nguồn phát ra giá trị; nếu một nguồn lỗi thì pipeline kết hợp cũng lỗi. `timeout` đặt giới hạn thời gian cho kết quả kết hợp, còn `onErrorMap` chuyển lỗi timeout thành lỗi miền nghiệp vụ. Cách viết này làm lộ rõ quan hệ giữa hai tác vụ, thời hạn chờ và cách chuyển lỗi.

Khi thứ tự là bắt buộc, `concatMap` thường phù hợp hơn `flatMap`, vì `flatMap` có thể xử lý các publisher con đồng thời và phát kết quả theo thứ tự hoàn tất. Toán tử cần được chọn theo ngữ nghĩa nghiệp vụ, không chỉ theo số dòng code.

### 2.3. Xử lý dữ liệu từng phần tử và phản hồi sớm

Với `Flux`, ứng dụng có thể xử lý từng phần tử khi nó đến thay vì đợi tải toàn bộ dữ liệu vào một collection. Cách này hữu ích cho nhập dữ liệu, đọc log, xử lý sự kiện, kết quả tìm kiếm lớn, luồng thông báo hoặc server-sent events. Người dùng có thể nhận kết quả đầu tiên trước khi toàn bộ nguồn hoàn tất.

Xử lý theo luồng cũng có thể giảm nhu cầu giữ toàn bộ dữ liệu trong bộ nhớ. Tuy nhiên, lợi ích này chỉ có khi pipeline không âm thầm gom tất cả phần tử vào một cấu trúc không giới hạn. Các thao tác như `collectList`, `cache` hoặc `onBackpressureBuffer` có thể làm tăng bộ nhớ đáng kể nếu nguồn lớn hoặc không có giới hạn.

### 2.4. Điều tiết tốc độ và hủy công việc

Backpressure cho phép subscriber cho publisher biết mình sẵn sàng nhận bao nhiêu phần tử. Thay vì để producer phát nhanh hơn khả năng xử lý của consumer, pipeline có thể truyền nhu cầu ngược về phía nguồn và hạn chế lượng dữ liệu đang chờ. Đây là công cụ quan trọng khi tốc độ sinh sự kiện và tốc độ xử lý không ổn định.

Ví dụ dưới đây yêu cầu từng phần tử sau khi xử lý xong. `BaseSubscriber` cho phép điều khiển demand rõ ràng:

```java
Flux.range(1, 1_000)
    .map(this::transform)
    .subscribe(new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(1);
        }

        @Override
        protected void hookOnNext(Integer value) {
            persist(value);
            request(1);
        }
    });
```

Trong ví dụ, subscriber yêu cầu một phần tử khi đăng ký và chỉ yêu cầu phần tử tiếp theo sau khi `persist` hoàn tất. Đây là minh họa cho demand; trong ứng dụng thực tế cần xử lý lỗi khi ghi, quyết định có tiếp tục yêu cầu hay hủy subscription, và tránh để thao tác blocking chạy trên event-loop.

Khả năng hủy cũng hữu ích khi client đóng kết nối, người dùng rời màn hình hoặc kết quả không còn cần thiết. Khi cancellation được truyền đến nguồn, các công việc chưa cần thiết có thể dừng và giải phóng tài nguyên. Hiệu quả thực tế tùy thuộc vào việc publisher và các adapter có hỗ trợ hủy hay không; một lời gọi bên ngoài đã được gửi đi có thể không thể thu hồi.

### 2.5. Mô tả chính sách lỗi và thời gian chờ trong cùng pipeline

Reactor cung cấp các toán tử như `timeout`, `retryWhen`, `onErrorResume`, `onErrorReturn` và `onErrorMap`. Chúng giúp thể hiện rõ chính sách khi một bước thất bại: chuyển sang nguồn dự phòng, thử lại có giới hạn, ánh xạ sang lỗi miền nghiệp vụ hoặc trả về giá trị thay thế.

Những toán tử này không làm cho lỗi biến mất. Ví dụ, retry một thao tác ghi có thể tạo bản ghi trùng nếu lần đầu đã thành công ở hệ thống đích nhưng phản hồi bị mất. Chính sách thử lại cần xét loại lỗi, số lần thử, khoảng nghỉ, timeout, idempotency và ngân sách thời gian tổng thể. Khi được thiết kế đúng, pipeline giúp nhìn thấy chính sách xử lý lỗi ở gần luồng công việc; khi thiết kế thiếu cẩn trọng, nó có thể che giấu lỗi hoặc khuếch đại tải lên dịch vụ đang gặp sự cố.

## 3. Chi phí và độ phức tạp phải chấp nhận

### 3.1. Khó theo dõi luồng điều khiển hơn

Trong mã đồng bộ, stack trace thường cho thấy chuỗi lời gọi dẫn đến kết quả. Trong pipeline bất đồng bộ, một bước có thể được đăng ký ở thread này, thực thi ở thread khác và phát tín hiệu sau một khoảng thời gian. Stack trace tại thời điểm lỗi có thể không thể hiện đầy đủ lịch sử đăng ký. Việc đọc log theo thứ tự thời gian cũng khó hơn khi nhiều request xen kẽ.

Đội ngũ cần có correlation ID, log có cấu trúc, tracing xuyên dịch vụ và cách ghi nhận ngữ cảnh phù hợp. Các thao tác debug phải hiểu được signal, subscription và ranh giới scheduler. Đây là chi phí thiết kế và vận hành lâu dài, không chỉ là chi phí học cú pháp.

### 3.2. Quản lý scheduler và ranh giới thread

Reactive không đồng nghĩa với việc mỗi toán tử chạy trên một thread riêng. Nhiều toán tử chạy trên thread đang phát tín hiệu cho đến khi pipeline gặp một ranh giới scheduler. Reactor cung cấp các scheduler thường dùng như:

| Scheduler | Mục đích thường gặp | Lưu ý |
| --- | --- | --- |
| `Schedulers.parallel()` | Công việc CPU-bound có thể chạy song song | Không dùng để chờ I/O blocking |
| `Schedulers.boundedElastic()` | Cô lập các lời gọi blocking khó loại bỏ | Có giới hạn tài nguyên; cần theo dõi tải và hàng đợi |
| `Schedulers.single()` | Công việc cần thực thi trên một luồng tuần tự | Có thể trở thành nút thắt nếu nhận quá nhiều việc |
| `Schedulers.immediate()` | Thực thi ngay trên thread hiện tại | Không tạo ranh giới chuyển thread |

`subscribeOn` ảnh hưởng đến nơi subscription bắt đầu và quá trình upstream được khởi động. `publishOn` tạo ranh giới thực thi cho các toán tử downstream kể từ vị trí đặt nó. Đặt scheduler sai có thể làm nghẽn event-loop, tăng số lần chuyển thread hoặc tạo hàng đợi lớn. Việc truyền ngữ cảnh như thông tin xác thực, tracing và transaction qua ranh giới bất đồng bộ cũng cần được kiểm tra với cơ chế context phù hợp; không nên mặc định rằng `ThreadLocal` luôn có giá trị ở mọi thread.

Nếu buộc phải gọi thư viện blocking, có thể cô lập lời gọi đó:

```java
Mono<Result> result = Mono.fromCallable(() -> legacyClient.fetch(key))
    .subscribeOn(Schedulers.boundedElastic());
```

Đoạn mã giúp lời gọi blocking không chiếm event-loop của pipeline gọi nó, nhưng bản thân `legacyClient.fetch` vẫn blocking. Khi phần lớn ứng dụng dựa vào các thư viện đồng bộ, việc bọc từng lời gọi theo cách này có thể làm tăng độ phức tạp mà không đạt được hiệu quả của một hệ thống non-blocking xuyên suốt.

### 3.3. Backpressure cần chính sách ở mọi ranh giới

Backpressure chỉ có tác dụng khi nguồn dữ liệu và các adapter tham gia đúng hợp đồng. Một nguồn callback, message broker hoặc API bên ngoài có thể không hỗ trợ demand theo Reactive Streams. Khi chuyển đổi nguồn đó thành `Flux`, ứng dụng phải chọn cách xử lý khi consumer chậm: buffer, bỏ phần tử mới, bỏ phần tử cũ, giữ phần tử mới nhất hay làm chậm nguồn nếu nguồn cho phép.

Mỗi lựa chọn có hệ quả nghiệp vụ. Buffer không giới hạn có thể làm cạn bộ nhớ; bỏ phần tử có thể làm mất sự kiện; giữ giá trị mới nhất có thể không phù hợp với luồng giao dịch; làm chậm nguồn có thể gây tăng độ trễ hoặc ảnh hưởng hệ thống upstream. Vì vậy, cần xác định giới hạn buffer, số lượng phần tử được yêu cầu trước, hành vi khi quá tải và cách quan sát số liệu. Backpressure là một giao thức điều tiết, không phải bảo đảm rằng bộ nhớ không bao giờ tăng.

### 3.4. Ngữ nghĩa lỗi và retry dễ gây sai lệch nghiệp vụ

Trong Reactor, lỗi là một tín hiệu kết thúc pipeline hiện tại. Nếu muốn tiếp tục với một giá trị thay thế hoặc một publisher khác, cần thể hiện điều đó bằng toán tử phù hợp. Đặt `onErrorResume` quá rộng có thể biến lỗi nghiêm trọng thành kết quả có vẻ hợp lệ. Retry không giới hạn có thể giữ tài nguyên quá lâu và làm tăng tải khi dịch vụ đích đang lỗi.

Các thao tác có tác dụng phụ như thanh toán, gửi email hoặc ghi dữ liệu cần được thiết kế idempotent nếu có thể bị thử lại. Cần phân biệt lỗi tạm thời với lỗi không thể phục hồi, đặt giới hạn retry và timeout tổng, đồng thời ghi log đủ thông tin để điều tra. Không nên dùng xử lý lỗi như một cách che đi vi phạm hợp đồng dữ liệu.

### 3.5. Kiểm thử và bảo trì đòi hỏi công cụ chuyên biệt

Kiểm thử pipeline cần xác minh cả giá trị, thứ tự, thời điểm phát, tín hiệu hoàn tất, lỗi và cancellation. Reactor Test cung cấp `StepVerifier` để kiểm tra các tín hiệu của `Mono` và `Flux` mà không cần dựa vào thời gian chờ tùy tiện.

```java
StepVerifier.create(service.findEvents())
    .expectNext("created", "updated")
    .verifyComplete();

StepVerifier.create(service.loadMissingItem())
    .expectError(NotFoundException.class)
    .verify();
```

Với pipeline dùng delay hoặc timer, `StepVerifier.withVirtualTime` có thể kiểm thử thời gian ảo để tránh làm bài test chậm. Các test vẫn cần được thiết kế để kiểm tra hành vi quan trọng, chẳng hạn giới hạn concurrency, thứ tự, retry và backpressure; chỉ xác minh rằng pipeline phát ra một giá trị là chưa đủ cho những luồng phức tạp.

Đội ngũ cũng cần thống nhất quy ước về tên biến publisher, nơi kết thúc subscription, cách xử lý context và cách đặt scheduler. Nếu mỗi thành viên dùng toán tử theo phong cách riêng, code review và bảo trì sẽ khó hơn đáng kể.

### 3.6. Tích hợp hệ sinh thái có thể làm mất lợi ích

Một ứng dụng chỉ non-blocking ở một vài lớp nhưng gọi JDBC, JPA hoặc thư viện blocking ở các điểm nóng vẫn phải trả chi phí chờ blocking. Khi đó, hệ thống có thể phải duy trì cả mô hình reactive lẫn imperative, cùng các adapter và quy tắc vận hành cho cả hai. Việc chuyển đổi dữ liệu, transaction, bảo mật và context giữa hai mô hình làm tăng số trường hợp cần kiểm thử.

Trước khi chọn reactive, cần kiểm tra khả năng hỗ trợ của driver cơ sở dữ liệu, client HTTP, message broker, thư viện bảo mật, tracing và các framework đang dùng. Nếu những phụ thuộc quan trọng chưa có tích hợp non-blocking đáng tin cậy, lợi ích tổng thể có thể thấp hơn chi phí chuyển đổi.

### 3.7. Có overhead và không tự tăng tốc công việc CPU-bound

Pipeline, subscription, điều phối tín hiệu, hàng đợi và chuyển thread đều có chi phí. Với tác vụ nhỏ, hữu hạn và ít đồng thời, cách viết imperative hoặc Java Stream có thể đơn giản và nhanh hơn. Reactive cũng không làm phép tính CPU nặng hoàn thành nhanh hơn chỉ vì nó được viết bằng `Flux`; muốn tận dụng nhiều lõi cần lựa chọn chiến lược song song phù hợp và đo lường overhead.

Hiệu năng phải được đánh giá bằng tải gần với thực tế: thông lượng, độ trễ p95/p99, số kết nối, mức sử dụng CPU và heap, số thread, độ dài hàng đợi, tỷ lệ timeout và hành vi khi phụ thuộc bên ngoài chậm. Một benchmark chỉ đo đường đi thành công trong điều kiện lý tưởng không phản ánh được khả năng chịu tải của hệ thống.

## 4. Những trường hợp reactive thường không phù hợp

Reactive không phải lựa chọn mặc định cho mọi ứng dụng Java. Các tình huống sau thường nên bắt đầu bằng mô hình imperative hoặc một giải pháp đơn giản hơn:

1. **CRUD đơn giản, tải vừa phải và ít I/O đồng thời.** Nếu request chủ yếu đọc hoặc ghi một vài bảng, thời gian xử lý ngắn và mô hình thread-per-request đáp ứng được tải, Spring MVC cùng JDBC/JPA thường dễ phát triển, debug và tuyển người bảo trì hơn.
2. **Phần lớn phụ thuộc đều blocking.** Nếu cơ sở dữ liệu, SDK và dịch vụ nội bộ đều dùng API đồng bộ, việc bọc chúng bằng `Mono.fromCallable` không biến hệ thống thành non-blocking. Có thể dùng một thread pool được giới hạn rõ ràng trong kiến trúc imperative để kiểm soát tải với ít khái niệm hơn.
3. **Tác vụ CPU-bound thuần túy.** Mã hóa, nén, xử lý ảnh hoặc tính toán lớn cần chiến lược phân chia công việc CPU và giới hạn song song. Reactive có thể giúp kết hợp kết quả bất đồng bộ, nhưng không tự làm phép tính nhanh hơn. Một executor hoặc parallel stream phù hợp có thể dễ hiểu hơn.
4. **Luồng công việc ngắn, tuần tự và hữu hạn.** Một quy trình vài bước phải chạy lần lượt, không có nhiều nguồn sự kiện và không cần phát kết quả từng phần thường dễ biểu diễn bằng hàm đồng bộ. Thêm publisher, scheduler và operator có thể làm luồng điều khiển khó đọc.
5. **Batch nhỏ hoặc script chạy theo lịch.** Với tập dữ liệu hữu hạn có kích thước vừa phải, vòng lặp hoặc Java Stream thường đủ rõ ràng. Chỉ nên dùng `Flux` khi có yêu cầu thực tế về streaming, giới hạn demand, nguồn dữ liệu bất đồng bộ hoặc tích hợp với một pipeline reactive hiện hữu.
6. **Đội ngũ chưa có thời gian xây dựng năng lực vận hành.** Nếu hệ thống không có logging, tracing, kỹ năng debug bất đồng bộ và quy ước kiểm thử phù hợp, chi phí xử lý sự cố có thể vượt lợi ích về tài nguyên. Có thể triển khai theo phạm vi nhỏ để tích lũy kinh nghiệm trước khi mở rộng.

Những trường hợp này không phải lệnh cấm tuyệt đối. Một ứng dụng CRUD vẫn có thể có một luồng sự kiện cần reactive; một hệ thống reactive vẫn có thể gọi một thành phần blocking đã được cô lập. Quyết định nên dựa trên đặc tính của từng luồng xử lý và khả năng của toàn bộ chuỗi phụ thuộc.

## 5. Cách chọn mô hình cho một bài toán

Trước khi đưa Reactive Programming vào một module, hãy trả lời các câu hỏi sau:

| Câu hỏi đánh giá | Dấu hiệu nghiêng về reactive | Dấu hiệu nghiêng về imperative |
| --- | --- | --- |
| Dữ liệu đến theo cách nào? | Luồng sự kiện liên tục, nhiều phần tử, cần xử lý khi dữ liệu đến | Một request tạo ra một kết quả hữu hạn |
| Thời gian chủ yếu được dùng vào đâu? | Chờ nhiều I/O đồng thời | Tính toán CPU hoặc ít thao tác I/O |
| Có cần điều tiết tốc độ? | Producer và consumer có tốc độ khác nhau; cần demand, buffer có giới hạn hoặc cancellation | Dữ liệu nhỏ, hữu hạn và không có vấn đề quá tải |
| Các phụ thuộc hỗ trợ ra sao? | Driver và client chính có API non-blocking, tích hợp Reactor tốt | Hầu hết thư viện quan trọng đều blocking |
| Có cần phát kết quả từng phần? | Có, client có thể tiêu thụ kết quả dần | Không, chỉ cần kết quả cuối cùng |
| Đội ngũ có thể vận hành không? | Có logging, tracing, kiểm thử và kinh nghiệm bất đồng bộ | Chưa có công cụ hoặc thời gian để xây dựng năng lực đó |

Một quyết định hợp lý nên bắt đầu từ yêu cầu có thể đo được, chẳng hạn số request đồng thời, tỷ lệ thời gian chờ I/O, kích thước luồng dữ liệu, giới hạn bộ nhớ hoặc độ trễ mục tiêu. Sau đó xây một lát cắt nhỏ đại diện cho đường đi thật: nhận request, gọi phụ thuộc, xử lý kết quả, xử lý lỗi và trả response. Đo cả trường hợp bình thường lẫn khi một phụ thuộc chậm hoặc lỗi.

Nếu chọn reactive, hãy giữ pipeline ở ranh giới có ý nghĩa: trả `Mono` hoặc `Flux` từ lớp service, để framework hoặc lớp điều phối phù hợp đăng ký subscription, giới hạn concurrency và buffer, đồng thời ghi nhận context. Tránh gọi `block()` giữa pipeline vì nó biến một bước thành chờ đồng bộ và có thể làm nghẽn event-loop. Cũng tránh gọi `subscribe()` tùy tiện bên trong service, vì việc tự tạo subscription có thể tách công việc khỏi lifecycle của request, làm khó quản lý lỗi và cancellation.

Nếu chọn imperative, hãy dùng thread pool và connection pool có giới hạn, đặt timeout cho lời gọi bên ngoài và đo tải. Imperative không đồng nghĩa với việc bỏ qua concurrency hoặc quản lý tài nguyên. Hai mô hình đều cần giới hạn, timeout, quan sát và chính sách lỗi rõ ràng.

## 6. Một số dấu hiệu thiết kế cần xem lại

- **Có `block()` trong một pipeline đang chạy trên event-loop:** kiểm tra xem có thể compose publisher xuyên suốt hay cần cô lập lời gọi blocking bằng scheduler phù hợp.
- **Có `subscribe()` trong lớp nghiệp vụ:** kiểm tra ai sở hữu lifecycle, lỗi và cancellation của subscription; thông thường lớp nghiệp vụ nên trả publisher để caller điều phối.
- **Dùng `flatMap` nhưng nghiệp vụ yêu cầu thứ tự:** cân nhắc `concatMap` hoặc một chiến lược giới hạn concurrency và sắp xếp kết quả phù hợp.
- **Buffer tăng liên tục khi consumer chậm:** xác định giới hạn bộ nhớ và chính sách quá tải; không dùng buffer vô hạn để che giấu chênh lệch tốc độ.
- **Retry làm phát sinh dữ liệu trùng hoặc tải tăng đột biến:** kiểm tra idempotency, loại lỗi, số lần thử, backoff và timeout tổng.
- **Pipeline chạy trên scheduler không phù hợp:** tách rõ công việc CPU-bound, I/O non-blocking và lời gọi blocking; chỉ chuyển thread khi có lý do cụ thể.
- **Log khó nối các bước của một request:** bổ sung correlation ID, tracing và cơ chế truyền context xuyên các ranh giới bất đồng bộ.

## 7. Kết luận

Reactive Programming có giá trị khi bài toán thực sự có luồng dữ liệu bất đồng bộ, nhiều I/O đồng thời, nhu cầu phát kết quả từng phần hoặc cần điều tiết producer và consumer. `Mono`, `Flux`, các toán tử kết hợp và backpressure cung cấp một cách diễn đạt thống nhất cho những luồng đó. Lợi ích về tài nguyên và khả năng chịu tải chỉ xuất hiện khi các thành phần quan trọng hỗ trợ non-blocking và pipeline được giới hạn, quan sát, kiểm thử đúng cách.

Đổi lại, nhóm phát triển phải hiểu subscription, signal, scheduler, cancellation, context, backpressure và ngữ nghĩa lỗi. Nếu công việc nhỏ, tuần tự, CPU-bound hoặc phụ thuộc chủ yếu vào thư viện blocking, mô hình imperative thường có tổng chi phí thấp hơn. Hãy chọn theo đặc tính tải và yêu cầu nghiệp vụ, thử nghiệm bằng số liệu, rồi mở rộng reactive ở những nơi nó giải quyết được vấn đề cụ thể.
