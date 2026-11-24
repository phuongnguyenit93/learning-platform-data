# Project Reactor

## `publishOn`, `subscribeOn` và các bộ lập lịch của Reactor

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Project Reactor cung cấp các bộ lập lịch (Scheduler) và hai toán tử quan trọng là `publishOn` và `subscribeOn` để điều khiển nơi một phần pipeline được thực thi.

Một Publisher mô tả cách phát dữ liệu, còn Scheduler quyết định công việc liên quan đến subscription hoặc xử lý tín hiệu được chạy trên thread nào. `subscribeOn` điều khiển nơi subscription đi vào nguồn; `publishOn` tạo ranh giới chuyển việc xử lý các tín hiệu downstream sang một Scheduler. Hai toán tử có vai trò khác nhau. Hiểu đúng vị trí của chúng giúp ta cô lập lời gọi blocking, chuyển phép tính CPU sang worker phù hợp và tránh chặn event loop của client reactive.

Scheduler không làm cho một API blocking trở thành non-blocking và cũng không tự chia một chuỗi xử lý thành nhiều phép tính song song. Nó chỉ điều phối việc thực thi. Muốn tăng concurrency, cần kết hợp với toán tử phù hợp như `flatMap` hoặc `ParallelFlux`, đồng thời giới hạn số tác vụ theo năng lực tài nguyên.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của Scheduler trong quá trình subscribe và xử lý tín hiệu.
- Phân biệt chính xác hành vi của `subscribeOn` và `publishOn`.
- Chọn `parallel`, `boundedElastic`, `single` hoặc Scheduler tùy chỉnh theo loại công việc.
- Bọc API blocking bằng nguồn deferred và chuyển nó sang Scheduler phù hợp.
- Đặt nhiều ranh giới `publishOn` trong một pipeline mà vẫn kiểm soát được luồng thực thi.
- Hiểu prefetch, hàng đợi, demand và tác động của scheduler boundary đến backpressure.
- Quản lý vòng đời Scheduler và tránh tạo quá nhiều thread.
- Kiểm thử việc chuyển thread bằng Reactor Test.

## 1. Scheduler điều phối việc thực thi

Trong Reactor, Scheduler là một abstraction dùng để lập lịch tác vụ trên một hoặc nhiều worker. Một worker thường gắn với thread hoặc cơ chế thực thi do Scheduler quản lý. Các toán tử có thể dùng Scheduler để quyết định nơi đăng ký nguồn, phát tín hiệu theo thời gian hoặc xử lý tín hiệu downstream.

Một pipeline có thể được hình dung như sau:

~~~mermaid
flowchart LR
    A[Publisher nguồn] --> B[subscribeOn]
    B --> C[Đọc hoặc tạo dữ liệu]
    C --> D[publishOn]
    D --> E[Xử lý downstream]
    E --> F[Subscriber]
~~~

Sơ đồ chỉ thể hiện các ranh giới điều phối chính. Nguồn bất đồng bộ như WebClient có thể phát tín hiệu trên event loop do client quản lý; một toán tử thời gian có thể dùng Scheduler riêng; các bước downstream có thể được chuyển qua một hoặc nhiều Scheduler bằng `publishOn`.

Không có yêu cầu rằng mỗi Publisher phải có một thread riêng. Một Scheduler có thể dùng chung nhiều worker cho nhiều subscription. Điều quan trọng là chọn đúng mô hình thực thi và giới hạn lượng công việc được đưa vào từng nhóm worker.

### Thread không phải là trạng thái của dữ liệu

Không nên thiết kế nghiệp vụ dựa trên giả định rằng một phần tử luôn được xử lý trên cùng thread. Sau khi pipeline đi qua ranh giới bất đồng bộ, tín hiệu có thể được xử lý trên worker khác. Dữ liệu cần truyền qua giá trị của Publisher hoặc Reactor Context; không nên dựa vào một biến `ThreadLocal` tự tạo để giữ trạng thái request.

Reactor Context gắn dữ liệu với subscription và có thể được đọc trong pipeline dù tín hiệu đi qua nhiều Scheduler. Nếu ứng dụng dùng thư viện dựa trên ThreadLocal như MDC, cần cơ chế tích hợp hoặc context propagation tương thích thay vì giả định ThreadLocal tự chuyển theo tín hiệu.

## 2. Các Scheduler thường dùng

Reactor cung cấp một số Scheduler dùng chung qua lớp `Schedulers`:

| Scheduler | Đặc điểm | Công việc phù hợp |
|---|---|---|
| `Schedulers.immediate()` | Thực thi tác vụ ngay trên thread hiện tại | Trường hợp đặc biệt cần giữ thực thi đồng bộ |
| `Schedulers.single()` | Dùng một worker chia sẻ cho các tác vụ | Công việc nhẹ cần tuần tự trên một thread dùng chung |
| `Schedulers.parallel()` | Pool worker dùng chung, parallelism thường dựa trên số CPU khả dụng | Tính toán CPU-bound không blocking |
| `Schedulers.boundedElastic()` | Pool dành cho tác vụ blocking, có giới hạn thread và hàng đợi | JDBC đồng bộ, API legacy blocking, thao tác chờ I/O |
| `Schedulers.fromExecutorService(...)` | Adapter từ ExecutorService có sẵn | Tích hợp với executor do ứng dụng quản lý |

### parallel cho công việc CPU-bound

`Schedulers.parallel()` phù hợp với phép tính không blocking như mã hóa, biến đổi dữ liệu, tính điểm hoặc xử lý ảnh. Pool này có số worker hữu hạn để tận dụng CPU mà không tạo thread không giới hạn.

~~~java
Mono<Score> score =
    Mono.fromSupplier(() -> calculateScore(input))
        .subscribeOn(Schedulers.parallel());
~~~

Nguồn được tạo khi subscribe và phép tính được thực hiện trên Scheduler parallel. Nếu phép tính chạy lâu, nó vẫn chiếm worker CPU trong thời gian đó; hãy tối ưu thuật toán và giới hạn số tác vụ đồng thời.

### boundedElastic cho API blocking

`Schedulers.boundedElastic()` dành cho công việc có thể giữ thread trong lúc chờ, chẳng hạn gọi JDBC đồng bộ hoặc một thư viện HTTP blocking:

~~~java
Mono<Customer> customer =
    Mono.fromCallable(() -> legacyDao.loadCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` trì hoãn lời gọi cho tới khi nguồn được thực thi. `subscribeOn` chuyển việc subscribe vào nguồn và thực thi callable sang bounded elastic. Nếu dùng `Mono.just(legacyDao.loadCustomer(customerId))`, lời gọi DAO đã chạy trước khi Mono được tạo nên Scheduler không thể chuyển nó đi.

Bounded elastic có giới hạn tài nguyên. Khi nhiều tác vụ blocking cùng chờ, worker và hàng đợi có thể đầy. Cần giới hạn concurrency ở upstream, cấu hình pool phù hợp với connection pool và đặt timeout. Không dùng bounded elastic như một nơi chứa vô hạn mọi công việc.

### single cho công việc cần một worker

`Schedulers.single()` cung cấp Scheduler dùng chung với một worker. Nó có thể hữu ích cho công việc nhẹ cần thực thi tuần tự trên một thread. Một tác vụ chậm hoặc blocking sẽ làm các tác vụ khác dùng cùng Scheduler phải chờ, vì vậy không dùng nó cho I/O blocking.

Nếu cần một worker riêng có vòng đời do thành phần sở hữu, có thể tạo bằng `Schedulers.newSingle("name")` và dispose khi thành phần kết thúc.

### immediate cho thực thi ngay

`Schedulers.immediate()` thực thi tác vụ ngay trên thread gọi. Nó không tạo thread mới và không phải lựa chọn để cô lập blocking. Dùng nó chỉ khi chủ đích là giữ việc thực thi trên thread hiện tại hoặc khi API yêu cầu một Scheduler nhưng không cần chuyển luồng.

## 3. subscribeOn điều khiển subscription tới nguồn

`subscribeOn(scheduler)` điều khiển nơi quá trình subscribe vào nguồn upstream được thực hiện. Với nguồn đồng bộ hoặc nguồn deferred, điều này cũng quyết định thread thực thi phần tạo dữ liệu của nguồn.

~~~java
Mono<Customer> customer =
    Mono.fromCallable(() -> legacyDao.loadCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Khi Subscriber đăng ký:

1. Reactor lên lịch quá trình subscribe vào nguồn trên bounded elastic.
2. Callable được thực thi trên worker tương ứng.
3. Kết quả hoặc lỗi được phát vào pipeline.
4. Các toán tử downstream tiếp tục nhận tín hiệu theo thread mà nguồn hoặc các ranh giới Scheduler tiếp theo quy định.

`subscribeOn` hữu ích để cô lập nguồn đồng bộ hoặc lời gọi blocking. Nó không có nghĩa là mọi đoạn mã trong phương thức Java chứa pipeline đều chạy trên Scheduler đó. Các biểu thức được Java đánh giá trước khi Publisher được tạo vẫn chạy ngay trong lúc lắp ráp.

### Phân biệt assembly time và subscription time

Đoạn mã sau không chuyển lời gọi blocking sang bounded elastic:

~~~java
Mono<Customer> wrong =
    Mono.just(legacyDao.loadCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Java đánh giá đối số của `Mono.just` trước khi gọi `just`. Nếu `loadCustomer` blocking, thread đang lắp ráp pipeline bị chặn ngay tại đó.

Dùng nguồn trì hoãn:

~~~java
Mono<Customer> correct =
    Mono.fromCallable(() -> legacyDao.loadCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Hoặc dùng `defer` khi cần tạo Publisher mới cho từng subscription:

~~~java
Mono<Customer> customer =
    Mono.defer(() -> customerRepository.findById(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Ví dụ `defer` minh họa thời điểm gọi supplier; chỉ dùng bounded elastic nếu phần tạo/subscribe nguồn thực sự thực hiện công việc blocking. Nếu repository là reactive non-blocking, thường không cần chuyển nó sang bounded elastic.

### subscribeOn đặt ở đâu?

Thông thường, đặt `subscribeOn` gần nguồn giúp người đọc thấy rõ Scheduler dành cho nguồn:

~~~java
Mono<Data> data =
    Mono.fromCallable(() -> legacyClient.fetch(key))
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::transform);
~~~

`subscribeOn` tác động theo hướng subscription đi ngược về nguồn, nên đặt nó sau một số toán tử trong chuỗi vẫn có thể ảnh hưởng tới subscription nguồn. Tuy nhiên, nhiều `subscribeOn` lồng nhau thường làm pipeline khó hiểu; trong đa số trường hợp, một `subscribeOn` ở ranh giới nguồn là đủ.

Nếu nguồn tự quản lý Scheduler, ví dụ một toán tử phát theo thời gian có overload nhận Scheduler, hãy đọc hợp đồng của nguồn đó. `subscribeOn` không nhất thiết ghi đè mọi quyết định lập lịch nội bộ của một Publisher bất đồng bộ.

## 4. publishOn chuyển xử lý downstream

`publishOn(scheduler)` tạo một ranh giới thực thi trong chuỗi tín hiệu. Các toán tử downstream nằm sau nó được thực thi trên worker được chọn, cho tới ranh giới `publishOn` tiếp theo.

~~~java
Flux<Integer> values =
    Flux.range(1, 5)
        .map(this::lightTransform)
        .publishOn(Schedulers.parallel())
        .map(this::cpuHeavyTransform)
        .filter(this::isAccepted);
~~~

Trong ví dụ:

- Nguồn và `lightTransform` chạy theo thread thực thi upstream.
- `publishOn` chuyển việc phát tín hiệu downstream sang Scheduler parallel.
- `cpuHeavyTransform` và `isAccepted` được gọi trên worker downstream đó.

Một `publishOn` không chia từng phần tử thành nhiều phép tính song song. Một subscription qua một ranh giới `publishOn` thường xử lý tín hiệu tuần tự trên worker đã chọn. Nếu cần nhiều phần tử được xử lý đồng thời, phải dùng toán tử concurrency hoặc mô hình parallel phù hợp.

### Nhiều publishOn tạo nhiều ranh giới

Có thể chuyển thread nhiều lần khi loại công việc thay đổi:

~~~java
Mono<Report> report =
    Mono.fromCallable(() -> legacyDao.loadRows(reportId))
        .subscribeOn(Schedulers.boundedElastic())
        .publishOn(Schedulers.parallel())
        .map(this::calculateReport)
        .publishOn(Schedulers.boundedElastic())
        .map(this::writeLegacySummary);
~~~

Nguồn đọc dữ liệu blocking chạy trên bounded elastic; phép tính báo cáo chạy trên parallel; bước ghi bằng API blocking được chuyển lại bounded elastic. Mỗi ranh giới có chi phí lập lịch và hàng đợi, vì vậy chỉ thêm khi có lý do rõ ràng.

Nếu bước ghi trả về Publisher reactive non-blocking, hãy ghép trực tiếp Publisher đó thay vì chuyển sang bounded elastic chỉ vì nó là thao tác ghi.

## 5. So sánh subscribeOn và publishOn

| Tiêu chí | `subscribeOn` | `publishOn` |
|---|---|---|
| Điều khiển chính | Nơi subscribe vào nguồn upstream | Nơi xử lý tín hiệu downstream từ ranh giới |
| Hướng tác động | Subscription đi ngược về nguồn | Tín hiệu đi xuôi tới Subscriber |
| Vị trí thường đặt | Gần nguồn | Trước nhóm toán tử cần chuyển Scheduler |
| Số lượng thường cần | Thường một ở ranh giới nguồn | Có thể nhiều khi pipeline đổi loại công việc |
| Có tự tạo parallelism? | Không | Không |
| Trường hợp điển hình | Chạy nguồn blocking trên bounded elastic | Chuyển phép tính downstream sang parallel |

Ví dụ kết hợp:

~~~java
Mono<InvoiceView> invoice =
    Mono.fromCallable(() -> legacyDao.loadInvoice(invoiceId))
        .subscribeOn(Schedulers.boundedElastic())
        .publishOn(Schedulers.parallel())
        .map(this::calculateTax)
        .map(this::toView);
~~~

Nguồn JDBC chạy trên bounded elastic. Sau khi dữ liệu được phát, `publishOn` chuyển các bước tính thuế và tạo view sang parallel. Nếu `toView` chỉ là phép biến đổi nhẹ, việc đặt chung sau một ranh giới là hợp lý; không cần thêm Scheduler cho từng `map`.

Một cách nhớ hữu ích:

- Dùng `subscribeOn` để chọn nơi nguồn bắt đầu làm việc.
- Dùng `publishOn` để chọn nơi các bước phía sau nhận và xử lý tín hiệu.

## 6. I/O non-blocking và event loop

Một client reactive như WebClient thường thực hiện I/O non-blocking. Trong lúc chờ server, event loop có thể phục vụ các kết nối khác; không cần chuyển mỗi request sang bounded elastic.

~~~java
Mono<Customer> customer =
    webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class);
~~~

Nếu thêm một lời gọi blocking vào `map`, ta có thể chặn event loop:

~~~java
Mono<CustomerView> wrong =
    customer
        .map(value -> legacyDao.loadExtra(value.id()))
        .map(this::toView);
~~~

Hãy bọc riêng phần blocking:

~~~java
Mono<CustomerView> view =
    customer.flatMap(value ->
        Mono.fromCallable(() -> legacyDao.loadExtra(value.id()))
            .subscribeOn(Schedulers.boundedElastic())
            .map(extra -> toView(value, extra))
    );
~~~

Nguồn WebClient tiếp tục dùng cơ chế non-blocking của client. Chỉ lời gọi DAO được cô lập trên bounded elastic. Nếu có thể thay API blocking bằng driver reactive, đó thường là lựa chọn tốt hơn; bounded elastic là ranh giới tương thích hữu ích cho thư viện cũ.

Không gọi `block()`, `Thread.sleep()` hoặc `Future.get()` trên event loop hay Scheduler dành cho CPU. Một số thread Reactor được đánh dấu non-blocking và các thao tác chặn như `block()` có thể bị phát hiện, ném lỗi để ngăn việc chặn worker quan trọng.

## 7. Scheduler không đồng nghĩa với parallelism

Scheduler cung cấp nơi thực thi, còn toán tử quyết định cách các phần tử được xử lý. `publishOn(Schedulers.parallel())` chuyển một chuỗi downstream sang worker CPU; nó không tự chia luồng thành nhiều nhánh.

Nếu các phép tính độc lập và cần chạy đồng thời, có thể dùng `flatMap` với concurrency giới hạn:

~~~java
Flux<Score> scores =
    records.flatMap(
        record -> Mono.fromCallable(() -> calculateScore(record))
            .subscribeOn(Schedulers.parallel()),
        4
    );
~~~

Tối đa bốn Publisher con được hoạt động đồng thời. Kết quả có thể phát theo thứ tự hoàn tất, không đảm bảo theo thứ tự nguồn. Nếu cần giữ thứ tự đầu vào, cân nhắc `flatMapSequential`; nếu công việc phải chạy lần lượt, dùng `concatMap`.

Với phép tính CPU thuần, Reactor còn cung cấp `ParallelFlux`:

~~~java
Flux<Score> scores =
    records
        .parallel()
        .runOn(Schedulers.parallel())
        .map(this::calculateScore)
        .sequential();
~~~

`parallel()` chia dữ liệu thành các rail; `runOn` chỉ định Scheduler để xử lý rail; `sequential()` hợp nhất kết quả thành Flux. Việc hợp nhất không nên được xem là bảo đảm thứ tự ban đầu. Chỉ dùng mô hình này khi phép tính độc lập và có thể xử lý song song.

Concurrency cao không đồng nghĩa với throughput cao. Giới hạn số Publisher con theo CPU, connection pool, quota của dịch vụ và dung lượng hàng đợi.

## 8. Backpressure tại ranh giới publishOn

`publishOn` phải chuyển tín hiệu từ upstream sang worker downstream. Để làm việc đó, nó dùng hàng đợi nội bộ và prefetch để yêu cầu trước một lượng phần tử từ upstream. Vì vậy, một ranh giới `publishOn` có ảnh hưởng đến demand và bộ nhớ.

Ví dụ có thể điều chỉnh prefetch:

~~~java
Flux<Result> results =
    source.publishOn(Schedulers.parallel(), 32)
        .map(this::transform);
~~~

Tham số 32 là lượng phần tử được prefetch ở ranh giới này, không phải số thread và cũng không phải số phần tử được xử lý song song. Khi downstream tiêu thụ, demand được điều phối để tiếp tục yêu cầu dữ liệu từ upstream.

Cần cân nhắc:

- Prefetch lớn có thể giữ nhiều phần tử trong hàng đợi và tăng bộ nhớ.
- Prefetch nhỏ giảm lượng dữ liệu chờ nhưng có thể tăng số lần yêu cầu và làm giảm hiệu quả trong một số nguồn.
- Một pipeline có nhiều ranh giới publishOn có thể có nhiều hàng đợi.
- Nếu upstream là nguồn callback không hỗ trợ backpressure, adapter nguồn vẫn cần chính sách buffer/drop/latest/error phù hợp.
- Nếu downstream chậm, việc chuyển Scheduler không tự làm nguồn phát chậm lại ngoài cơ chế demand mà nguồn hỗ trợ.

Không nên tăng prefetch chỉ để che độ trễ xử lý. Hãy đo throughput, latency, queue depth và heap dưới tải đại diện.

## 9. Scheduler dùng chung và Scheduler riêng

Các Scheduler lấy từ `Schedulers.parallel()`, `Schedulers.boundedElastic()` và `Schedulers.single()` là các Scheduler dùng chung do Reactor quản lý. Thông thường, ứng dụng không dispose chúng sau mỗi request hoặc subscription.

Nếu một thành phần cần giới hạn tài nguyên riêng, có thể tạo Scheduler tùy chỉnh:

~~~java
Scheduler legacyScheduler =
    Schedulers.newBoundedElastic(
        12,
        300,
        "legacy-database"
    );
~~~

Ví dụ tạo Scheduler với tối đa 12 thread và giới hạn số tác vụ được xếp hàng theo hợp đồng của API. Các giá trị chỉ minh họa; cần chọn theo connection pool, thời gian chờ và tải thực tế.

Dùng Scheduler này cho các lời gọi blocking thuộc thành phần:

~~~java
Mono<Customer> customer =
    Mono.fromCallable(() -> legacyDao.loadCustomer(customerId))
        .subscribeOn(legacyScheduler);
~~~

Scheduler tùy chỉnh cần có chủ sở hữu vòng đời. Nếu tạo ở cấp service hoặc ứng dụng, hãy dispose khi thành phần đó shutdown:

~~~java
@PreDestroy
void shutdown() {
    legacyScheduler.dispose();
}
~~~

Không tạo Scheduler mới trong mỗi lần gọi service. Điều đó có thể làm số thread và hàng đợi tăng liên tục, đồng thời khiến tài nguyên khó được giải phóng.

### Chọn giới hạn cho Scheduler blocking

Khi đặt thread cap, hãy đối chiếu với giới hạn connection của database và khả năng xử lý của dịch vụ. Nếu có 12 worker nhưng connection pool chỉ có 4 kết nối, nhiều worker sẽ chờ lấy connection. Nếu tăng worker quá cao, database có thể bị quá tải. Concurrency ở `flatMap`, thread cap, connection pool và timeout cần được thiết kế cùng nhau.

## 10. Scheduler cho toán tử thời gian

Các toán tử như `delayElements`, `interval` và `timeout` cần bộ định thời. Một số overload dùng Scheduler mặc định; một số cho phép truyền Scheduler tường minh.

~~~java
Flux<Long> ticks =
    Flux.interval(
        Duration.ofSeconds(1),
        Schedulers.parallel()
    );
~~~

Ví dụ tạo tick mỗi giây trên Scheduler được chỉ định. Với pipeline có yêu cầu thời gian rõ ràng, dùng overload nhận Scheduler giúp xác định nơi bộ định thời phát tín hiệu.

`publishOn` không thay thế Scheduler của nguồn thời gian. Nếu `Flux.interval` được tạo với Scheduler riêng, nó tiếp tục dùng Scheduler đó để lên lịch tick; `publishOn` có thể chuyển các bước downstream sau tick sang một worker khác.

Trong kiểm thử, dùng `StepVerifier.withVirtualTime` để kiểm tra toán tử thời gian mà không phải chờ thời gian thực. Tạo Publisher bên trong supplier của `withVirtualTime` để Scheduler ảo có thể được cài trước khi pipeline được lắp ráp.

## 11. Scheduler và Reactor Context

Scheduler thay đổi thread thực thi nhưng không làm mất Reactor Context của subscription. Nếu cần mang correlation ID hoặc thông tin request qua các bước bất đồng bộ, hãy dùng Context:

~~~java
Mono<String> response =
    remoteClient.fetch()
        .publishOn(Schedulers.parallel())
        .flatMap(value ->
            Mono.deferContextual(context -> {
                String requestId = context.get("requestId");
                return Mono.just(requestId + ":" + value);
            })
        )
        .contextWrite(context -> context.put("requestId", requestId));
~~~

Context thuộc về subscription, không thuộc về thread. Vì vậy, nó phù hợp hơn ThreadLocal tự quản lý khi pipeline đổi Scheduler. Với MDC hoặc thư viện yêu cầu ThreadLocal, cần tích hợp context propagation đúng phiên bản Reactor và framework.

Không ghi dữ liệu nhạy cảm vào Context hoặc log chỉ vì nó có sẵn. Chỉ mang metadata cần thiết như correlation ID, trace ID hoặc tenant key theo chính sách bảo mật của ứng dụng.

## 12. Xử lý lỗi và cancellation qua Scheduler boundary

`publishOn` và `subscribeOn` không thay đổi ý nghĩa của tín hiệu lỗi. Nếu upstream phát `onError`, lỗi tiếp tục đi xuống pipeline và có thể được xử lý bằng `onErrorResume`, `onErrorMap` hoặc `doOnError`.

~~~java
Mono<Result> result =
    Mono.fromCallable(() -> legacyClient.call())
        .subscribeOn(Schedulers.boundedElastic())
        .publishOn(Schedulers.parallel())
        .map(this::transform)
        .onErrorResume(DependencyUnavailableException.class,
            error -> cache.findResult());
~~~

Lỗi từ lời gọi blocking hoặc phép biến đổi downstream đều có thể đi qua chuỗi xử lý lỗi. Đặt recovery tại nơi có đủ ngữ cảnh để quyết định fallback; không dùng hook toàn cục để thay thế xử lý lỗi nghiệp vụ.

Cancellation cũng truyền qua pipeline khi Subscriber hủy. Một ranh giới Scheduler có thể có công việc đang chờ trong hàng đợi; khi hủy, Reactor cố gắng dừng hoặc loại bỏ công việc không còn cần thiết theo hợp đồng của nguồn và Scheduler.

Tuy nhiên, cancellation không bảo đảm dừng một API blocking đang chạy. Thư viện phải hỗ trợ interrupt hoặc cơ chế hủy tương ứng. Nếu lời gọi từ xa đã thực hiện tác dụng phụ, cancellation không tự rollback. Với lệnh ghi, cần idempotency và đối soát trạng thái.

## 13. Kiểm thử nơi thực thi

Có thể dùng Scheduler riêng có tên để xác nhận một bước downstream được chuyển sang worker mong muốn. Test nên kiểm tra thuộc tính cần thiết thay vì phụ thuộc tên thread mặc định của Reactor.

~~~java
@Test
void publishOnMovesDownstreamWorkToScheduler() {
    Scheduler scheduler = Schedulers.newSingle("test-worker");
    AtomicReference<String> threadName = new AtomicReference<>();

    try {
        Mono<String> result =
            Mono.just("reactor")
                .publishOn(scheduler)
                .doOnNext(value ->
                    threadName.set(Thread.currentThread().getName())
                );

        StepVerifier.create(result)
            .expectNext("reactor")
            .verifyComplete();

        assertThat(threadName.get()).startsWith("test-worker");
    } finally {
        scheduler.dispose();
    }
}
~~~

Scheduler được tạo trong test phải được dispose ngay cả khi assertion thất bại. Điều này tránh để worker tồn tại và ảnh hưởng test khác.

Có thể kiểm thử `subscribeOn` với nguồn deferred:

~~~java
@Test
void subscribeOnRunsCallableOnChosenScheduler() {
    Scheduler scheduler = Schedulers.newSingle("source-worker");
    AtomicReference<String> threadName = new AtomicReference<>();

    try {
        Mono<String> result =
            Mono.fromCallable(() -> {
                threadName.set(Thread.currentThread().getName());
                return "loaded";
            })
            .subscribeOn(scheduler);

        StepVerifier.create(result)
            .expectNext("loaded")
            .verifyComplete();

        assertThat(threadName.get()).startsWith("source-worker");
    } finally {
        scheduler.dispose();
    }
}
~~~

Các kiểm thử hữu ích khác:

- Xác minh lời gọi blocking chỉ chạy khi có subscription.
- Xác minh `Mono.just(methodCall())` thực hiện lời gọi trong assembly, còn `fromCallable` trì hoãn nó.
- Xác minh các bước trước và sau `publishOn` chạy ở ranh giới thread dự kiến.
- Xác minh cancellation được truyền tới nguồn.
- Kiểm thử backpressure và prefetch với nguồn có thể quan sát demand.
- Dùng virtual time để kiểm thử `delayElements`, `interval` hoặc `timeout`.
- Kiểm tra Scheduler tùy chỉnh được dispose khi thành phần shutdown.

## 14. Những nhầm lẫn thường gặp

- **`subscribeOn` và `publishOn` giống nhau:** subscribeOn điều khiển subscription tới nguồn; publishOn chuyển việc xử lý tín hiệu downstream từ vị trí của nó.
- **Đặt publishOn ở cuối làm nguồn chạy trên Scheduler đó:** publishOn tác động các bước downstream; dùng subscribeOn để điều khiển subscription vào nguồn.
- **`Mono.just(methodCall())` được chuyển thread:** lời gọi Java đã xảy ra trước khi Mono được tạo; dùng `fromCallable` hoặc `defer`.
- **Một publishOn làm mọi phần tử chạy song song:** một ranh giới publishOn không tự chia chuỗi thành nhiều phép tính đồng thời.
- **boundedElastic phù hợp với mọi I/O:** I/O non-blocking như WebClient thường nên giữ trên cơ chế event loop của client; boundedElastic dành cho lời gọi blocking.
- **parallel phù hợp với JDBC:** JDBC blocking giữ worker CPU trong lúc chờ; dùng boundedElastic hoặc driver reactive.
- **Scheduler có thread là đủ để kiểm soát tải:** vẫn cần giới hạn concurrency, pool, prefetch và hàng đợi.
- **Mỗi request nên tạo Scheduler riêng:** Scheduler cần được tái sử dụng và quản lý theo vòng đời thành phần.
- **Cancellation luôn dừng tác vụ blocking:** thư viện ngoài phải hỗ trợ hủy; tác dụng phụ đã commit không tự rollback.
- **ThreadLocal tự đi theo pipeline:** thread có thể thay đổi; dùng Reactor Context hoặc cơ chế context propagation phù hợp.

## 15. Bài tập vận dụng

Một pipeline tạo báo cáo gồm ba bước:

1. Đọc dữ liệu bằng JDBC đồng bộ.
2. Tính tổng hợp và phân loại dữ liệu trên tập bản ghi lớn.
3. Gọi WebClient để gửi kết quả tới dịch vụ báo cáo.

Hãy thiết kế pipeline và giải thích:

1. Vì sao bước JDBC cần được bọc bằng `Mono.fromCallable` và `subscribeOn(Schedulers.boundedElastic())`?
2. Đặt `publishOn(Schedulers.parallel())` ở đâu để phép tính tổng hợp không chạy trên worker blocking?
3. Bước WebClient có cần chuyển sang bounded elastic không? Vì sao?
4. Nếu cần xử lý nhiều báo cáo đồng thời, giới hạn concurrency theo những tài nguyên nào?
5. Nếu bước JDBC timeout, cancellation có bảo đảm driver dừng truy vấn ngay không?
6. Nếu tạo Scheduler tùy chỉnh cho JDBC, thành phần nào sở hữu và dispose Scheduler đó?
7. Viết một kiểm thử xác nhận phép tính chạy trên Scheduler CPU và một kiểm thử xác nhận nguồn JDBC chỉ chạy khi có subscription.

**Gợi ý:** bọc JDBC trong `fromCallable` và đặt `subscribeOn(boundedElastic)`; chuyển bước tổng hợp bằng `publishOn(parallel)`; giữ WebClient trên cơ chế non-blocking của client. Giới hạn số báo cáo đồng thời theo connection pool, CPU và năng lực dịch vụ đích. Đo queue, thread, connection và latency dưới tải trước khi điều chỉnh.

## Kết luận

`subscribeOn` điều khiển nơi subscription đi vào nguồn, còn `publishOn` chuyển việc xử lý các tín hiệu downstream sang Scheduler được chọn. Dùng `parallel` cho phép tính CPU không blocking, `boundedElastic` để cô lập API blocking, và giữ I/O non-blocking trên cơ chế event loop của client reactive. Scheduler không tự tạo parallelism hay bảo đảm giới hạn tải; cần phối hợp concurrency, prefetch, connection pool và timeout. Hãy tạo nguồn blocking theo cách lazy, đặt ranh giới Scheduler tại nơi loại công việc thay đổi, quản lý Scheduler tùy chỉnh theo vòng đời ứng dụng và kiểm thử bằng `StepVerifier`. Nhờ đó, pipeline Reactor có thể kết hợp nhiều loại công việc mà vẫn kiểm soát được thread, demand và cancellation.
