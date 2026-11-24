# Ghép luồng

## `concatMap`: xử lý luồng con tuần tự và bảo toàn thứ tự

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi một phần tử đầu vào cần kích hoạt một Publisher con, ta phải quyết định các Publisher con được chạy đồng thời hay lần lượt. Reactor cung cấp `concatMap` để xử lý luồng con tuần tự và phát kết quả theo thứ tự của luồng đầu vào.

`concatMap` chỉ đăng ký Publisher con kế tiếp sau khi Publisher con hiện tại hoàn tất. Nếu Publisher con phát nhiều phần tử, tất cả phần tử của luồng con đó được phát trước khi chuyển sang phần tử đầu vào tiếp theo. Cách ghép này hữu ích khi thứ tự có ý nghĩa nghiệp vụ, chẳng hạn xử lý các thay đổi trạng thái của cùng một quy trình, ghi tuần tự vào một hệ thống đích hoặc gọi một dịch vụ chỉ cho phép một thao tác đang hoạt động.

Đổi lại, một Publisher con chậm sẽ giữ các phần tử phía sau chờ đến lượt. Vì vậy, `concatMap` là lựa chọn về thứ tự và mức đồng thời, không phải cách tăng thông lượng cho mọi pipeline.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cách `concatMap` đăng ký và chờ từng Publisher con.
- Phân biệt thứ tự đầu vào, thứ tự thực thi và thứ tự phát kết quả.
- Chọn giữa `concatMap`, `flatMap` và `flatMapSequential`.
- Dùng `concatMap` với `Mono` và `Flux` con trong các workflow bất đồng bộ.
- Hiểu vai trò của prefetch, demand, lỗi và cancellation.
- Đặt xử lý lỗi theo từng phần tử hoặc trì hoãn lỗi theo chính sách nghiệp vụ.
- Kiểm thử việc tuần tự hóa và thứ tự kết quả bằng Reactor Test.

## 1. Vấn đề khi ghép nhiều Publisher con

Giả sử một luồng đơn hàng phát ra các đơn theo thứ tự tiếp nhận. Với mỗi đơn, ứng dụng cần gọi dịch vụ để xác minh và ghi nhận kết quả:

~~~java
Flux<Order> orders = orderRepository.findPending();

Flux<Receipt> receipts =
    orders.flatMap(order ->
        fulfillmentClient.process(order)
    );
~~~

`flatMap` cho phép nhiều Publisher con hoạt động đồng thời. Nếu đơn A mất 500 ms còn đơn B mất 100 ms, kết quả của B có thể được phát trước A. Điều này thường tốt khi các công việc độc lập và thông lượng quan trọng hơn thứ tự. Nhưng nếu dịch vụ đích yêu cầu xử lý đúng trình tự, việc hoàn tất không theo thứ tự có thể tạo ra trạng thái khó dự đoán.

Có thể hình dung ba phần tử đầu vào A, B, C và thời gian xử lý khác nhau:

~~~mermaid
sequenceDiagram
    participant U as Luồng đầu vào
    participant A as Xử lý A
    participant B as Xử lý B
    participant C as Xử lý C
    participant D as Luồng kết quả
    U->>A: A
    U->>B: B
    U->>C: C
    B-->>D: B hoàn tất trước
    C-->>D: C hoàn tất tiếp
    A-->>D: A hoàn tất sau
~~~

Nếu đầu ra phải theo thứ tự A, B, C, ta cần chọn một toán tử thể hiện chính sách đó. `concatMap` xử lý A trước; chỉ khi Publisher con của A hoàn tất mới đăng ký Publisher con của B, rồi đến C.

## 2. Cách concatMap hoạt động

Cú pháp cơ bản:

~~~java
Flux<R> result =
    source.concatMap(value -> createPublisher(value));
~~~

Hàm ánh xạ nhận một phần tử từ nguồn và trả về một Publisher con. `concatMap` điều phối các Publisher con theo trình tự:

1. Nhận phần tử đầu tiên từ nguồn.
2. Gọi hàm ánh xạ để tạo Publisher con.
3. Subscribe vào Publisher con đó.
4. Chuyển các phần tử của Publisher con xuống Subscriber theo demand.
5. Chờ Publisher con hoàn tất.
6. Chỉ sau đó mới xử lý Publisher con kế tiếp.
7. Kết thúc luồng kết quả khi nguồn đầu vào hoàn tất và Publisher con cuối cùng đã hoàn tất; nếu có lỗi theo chính sách mặc định, phát `onError`.

~~~mermaid
flowchart TD
    S[Source: A, B, C] --> Q[concatMap]
    Q --> A[Subscribe inner A]
    A --> AW[Chờ inner A hoàn tất]
    AW --> B[Subscribe inner B]
    B --> BW[Chờ inner B hoàn tất]
    BW --> C[Subscribe inner C]
    C --> CW[Chờ inner C hoàn tất]
    CW --> O[Phát kết quả theo A, B, C]
~~~

Điểm quan trọng là `concatMap` chỉ có một Publisher con đang được subscribe tại một thời điểm. Điều này giữ thứ tự phát kết quả theo thứ tự phần tử nguồn mà toán tử quan sát được.

### Ví dụ với Mono con

Nếu mỗi đơn tạo ra đúng một biên nhận:

~~~java
Flux<Receipt> receipts =
    orderRepository.findPending()
        .concatMap(order ->
            fulfillmentClient.process(order)
        );
~~~

Giả sử `process(order)` trả về `Mono<Receipt>`. Publisher con của mỗi đơn chỉ phát tối đa một biên nhận hoặc hoàn tất rỗng. `concatMap` chờ Mono hiện tại kết thúc trước khi bắt đầu Mono tiếp theo.

### Ví dụ với Flux con

Nếu mỗi đơn tạo ra nhiều bản ghi kiểm tra:

~~~java
Flux<AuditRecord> auditRecords =
    orders.concatMap(order ->
        auditClient.recordsFor(order.id())
    );
~~~

Giả sử `recordsFor` trả về `Flux<AuditRecord>`. Với đầu vào A, B, C, toàn bộ bản ghi của A được phát trước bản ghi của B; toàn bộ bản ghi của B được phát trước bản ghi của C.

Đây là khác biệt đáng chú ý so với việc chỉ sắp xếp các phần tử đầu ra sau khi tất cả công việc đã chạy: `concatMap` tuần tự hóa cả việc subscribe Publisher con, chứ không chỉ sắp xếp kết quả sau cùng.

## 3. Bảo toàn thứ tự có nghĩa là gì?

`concatMap` bảo toàn thứ tự của các phần tử đầu vào theo thứ tự chúng được phát tới toán tử. Nó không tự tạo ra thứ tự nghiệp vụ nếu nguồn đầu vào vốn không có thứ tự xác định.

Ví dụ, truy vấn cơ sở dữ liệu không có `ORDER BY` không bảo đảm hàng trả về luôn theo thứ tự tạo đơn. Nếu cần xử lý theo thời gian tạo, nguồn phải cung cấp thứ tự đó:

~~~java
Flux<Order> orders =
    orderRepository.findPendingOrderByCreatedAtAsc();

Flux<Receipt> receipts =
    orders.concatMap(fulfillmentClient::process);
~~~

Nếu nguồn đầu vào đã được ghép từ nhiều luồng song song, thứ tự mà `concatMap` bảo toàn là thứ tự quan sát được sau phép ghép đó. Nó không thể khôi phục thứ tự ban đầu đã bị mất trước khi phần tử đến `concatMap`.

Cần phân biệt ba loại thứ tự:

- **Thứ tự nguồn:** thứ tự các phần tử được phát từ Publisher upstream.
- **Thứ tự bắt đầu và thực thi:** `concatMap` bắt đầu Publisher con theo thứ tự nguồn và chỉ có một Publisher con hoạt động tại một thời điểm.
- **Thứ tự kết quả:** các phần tử từ một Publisher con được phát hết trước khi kết quả của Publisher con kế tiếp được phát.

Nếu Publisher con thực hiện tác dụng phụ bên ngoài, việc subscribe tuần tự thường giúp thứ tự bắt đầu các thao tác được kiểm soát. Tuy nhiên, nó không tự bảo đảm giao dịch ở hệ thống từ xa được commit bền vững hoặc có thể rollback khi subscription bị hủy.

## 4. So sánh concatMap, flatMap và flatMapSequential

Ba toán tử đều nhận một hàm ánh xạ trả về Publisher con, nhưng chính sách thực thi khác nhau:

| Toán tử | Subscription Publisher con | Thứ tự phát kết quả | Khi phù hợp |
|---|---|---|---|
| `flatMap` | Có thể đồng thời | Có thể xen kẽ, không đảm bảo theo nguồn | Công việc độc lập, ưu tiên thông lượng |
| `flatMapSequential` | Có thể đồng thời | Theo thứ tự nguồn | Muốn chạy đồng thời nhưng cần đầu ra có thứ tự |
| `concatMap` | Lần lượt, một inner tại một thời điểm | Theo thứ tự nguồn | Tác vụ cần tuần tự hóa cả quá trình |

Ví dụ:

~~~java
Flux<Result> concurrent =
    source.flatMap(this::asyncOperation, 8);

Flux<Result> concurrentOrdered =
    source.flatMapSequential(this::asyncOperation, 8);

Flux<Result> sequential =
    source.concatMap(this::asyncOperation);
~~~

Với `flatMapSequential`, các Publisher con có thể được subscribe và xử lý đồng thời. Nếu Publisher con thứ hai hoàn tất trước Publisher con thứ nhất, kết quả thứ hai sẽ phải chờ để được phát theo đúng thứ tự. Điều này có thể làm tăng bộ đệm khi một Publisher con đầu tiên bị chậm.

Với `concatMap`, Publisher con thứ hai thậm chí chưa được subscribe cho tới khi Publisher con thứ nhất hoàn tất. Do đó, nó tuần tự hóa cả việc thực thi Publisher con, không chỉ thứ tự phát kết quả.

Nếu yêu cầu chỉ là giữ thứ tự hiển thị kết quả trong khi tận dụng I/O đồng thời, `flatMapSequential` có thể phù hợp hơn. Nếu bản thân thao tác phải chạy tuần tự, hãy chọn `concatMap`.

## 5. Ứng dụng trong workflow nghiệp vụ

### Ghi lần lượt các thay đổi trạng thái

Giả sử một aggregate đơn hàng nhận các lệnh thay đổi trạng thái. Mỗi thay đổi phải được ghi xong trước khi xử lý lệnh tiếp theo:

~~~java
Flux<OrderCommand> commands = commandSource.forOrder(orderId);

Flux<OrderState> states =
    commands.concatMap(command ->
        orderRepository.load(orderId)
            .flatMap(state -> state.apply(command))
            .flatMap(orderRepository::save)
    );
~~~

Trong ví dụ, Publisher con của mỗi command bao gồm đọc trạng thái, áp dụng lệnh và lưu trạng thái mới. `concatMap` chờ cả chuỗi đó hoàn tất rồi mới xử lý command kế tiếp. Điều này tránh hai command của cùng luồng cạnh tranh cập nhật một trạng thái nếu chúng được phát theo đúng thứ tự.

Nếu nhiều đơn hàng độc lập cần xử lý đồng thời, không nên tuần tự hóa tất cả đơn hàng toàn hệ thống một cách không cần thiết. Có thể phân nhóm theo aggregate key rồi tuần tự hóa bên trong từng nhóm, đồng thời xử lý các nhóm khác nhau song song. Cách làm đó cần giới hạn số nhóm đang hoạt động và quản lý vòng đời group cẩn thận.

### Gọi API theo thứ tự

Một API đối tác có giới hạn chỉ cho phép một request đang xử lý cho một phiên:

~~~java
Flux<ApiResponse> responses =
    requests.concatMap(request ->
        partnerClient.send(request)
            .timeout(Duration.ofSeconds(3))
    );
~~~

Request tiếp theo chỉ được gửi khi Publisher của request hiện tại hoàn tất hoặc lỗi. Timeout giúp một request không giữ lượt mãi mãi nếu dịch vụ không phản hồi. Tuy nhiên, timeout không bảo đảm phía đối tác chưa xử lý request; thao tác gửi cần idempotency key nếu retry có thể lặp.

### Xử lý file theo thứ tự

Nếu mỗi file cần đọc metadata rồi ghi vào kho lưu trữ theo thứ tự danh sách:

~~~java
Flux<StoredFile> stored =
    files.concatMap(file ->
        fileService.readMetadata(file)
            .flatMap(metadata ->
                storageClient.store(file, metadata)
            )
    );
~~~

Toàn bộ thao tác của file hiện tại phải hoàn tất trước khi bắt đầu file tiếp theo. Điều này hữu ích khi kho lưu trữ hoặc quy trình nghiệp vụ yêu cầu tuần tự, nhưng có thể giảm thông lượng nếu mỗi file có I/O lâu.

## 6. Publisher con rỗng, nhiều phần tử và không kết thúc

`concatMap` chờ Publisher con kết thúc, bất kể Publisher con phát bao nhiêu phần tử.

- Nếu inner là `Mono<T>` phát một phần tử, phần tử đó được chuyển xuống rồi inner hoàn tất.
- Nếu inner là `Mono.empty()`, không có phần tử đầu ra và toán tử chuyển sang phần tử nguồn tiếp theo.
- Nếu inner là `Flux<T>` phát nhiều phần tử, tất cả phần tử được phát theo thứ tự của inner trước khi chuyển tiếp.
- Nếu inner không bao giờ hoàn tất, các phần tử nguồn phía sau sẽ không được xử lý.

Ví dụ một Publisher con rỗng không ngăn các phần tử tiếp theo:

~~~java
Flux<String> values =
    Flux.just("A", "B", "C")
        .concatMap(value ->
            value.equals("B")
                ? Mono.empty()
                : Mono.just(value.toLowerCase())
        );
~~~

Kết quả là `a`, `c`. Với B, inner hoàn tất rỗng nên `concatMap` tiếp tục đến C.

Một nguồn không kết thúc có thể chặn toàn bộ chuỗi:

~~~java
Flux<Event> events =
    commands.concatMap(command ->
        eventBus.eventsFor(command)
    );
~~~

Nếu `eventsFor` là một luồng dài hạn không hoàn tất, command kế tiếp sẽ không bao giờ được xử lý. Khi cần tiêu thụ một phần luồng con, phải xác định rõ điều kiện kết thúc như `take(n)`, `next()`, `timeout` hoặc một điều kiện nghiệp vụ phù hợp. Không nên tùy tiện cắt luồng nếu điều đó làm mất dữ liệu cần thiết.

## 7. Lỗi trong concatMap

Theo hành vi mặc định, nếu Publisher con phát `onError`, luồng kết quả cũng kết thúc bằng lỗi. Các phần tử nguồn đang chờ không được xử lý tiếp theo chính sách fail-fast thông thường.

~~~java
Flux<Result> results =
    source.concatMap(this::process);
~~~

Nếu `process(B)` lỗi, `concatMap` phát lỗi ra downstream và hủy việc xử lý tiếp theo của pipeline. Điều này phù hợp khi một lỗi khiến cả quy trình phải dừng.

Nếu lỗi chỉ ảnh hưởng đến một phần tử và các phần tử sau vẫn cần tiếp tục, đặt recovery bên trong hàm ánh xạ:

~~~java
Flux<ProcessingResult> results =
    source.concatMap(item ->
        process(item)
            .map(ProcessingResult::success)
            .onErrorResume(error ->
                Mono.just(ProcessingResult.failure(item, error))
            )
    );
~~~

Khi đó lỗi của một inner được chuyển thành một giá trị kết quả. Inner hoàn tất bình thường sau recovery, nên `concatMap` tiếp tục với phần tử nguồn tiếp theo.

Nếu muốn trì hoãn việc phát lỗi cho tới khi xử lý các phần tử đã được xếp hàng, Reactor cung cấp các biến thể `concatMapDelayError`. Hãy chọn overload và chính sách delay phù hợp với việc lỗi được báo sau mỗi inner hay sau khi phần nguồn còn lại được xử lý. Trì hoãn lỗi có thể giúp hoàn tất nhiều công việc, nhưng không tự sửa lỗi hoặc bảo đảm mọi tác vụ nghiệp vụ đều thành công.

Không nên đặt `onErrorContinue` như một cách bỏ qua lỗi chung mà không hiểu toán tử nào hỗ trợ và phần tử nào bị bỏ. Recovery theo từng phần tử bằng `onErrorResume` bên trong mapper thường thể hiện chính sách rõ ràng hơn.

## 8. Demand, prefetch và bộ đệm

`concatMap` chỉ subscribe một Publisher con tại một thời điểm, nhưng điều đó không có nghĩa upstream luôn chỉ được yêu cầu đúng một phần tử. Reactor có thể prefetch một số phần tử nguồn và giữ chúng trong hàng đợi trong khi inner hiện tại đang chạy.

Một overload cho phép điều chỉnh prefetch:

~~~java
Flux<Result> results =
    source.concatMap(this::process, 1);
~~~

Tham số prefetch điều khiển lượng phần tử nguồn được yêu cầu trước để chờ xử lý. Nó **không** phải số Publisher con chạy đồng thời. Với `concatMap`, số inner đang được subscribe vẫn là một.

Prefetch thấp có thể giảm lượng phần tử chờ trong hàng đợi, nhưng có thể làm upstream phải chờ demand thường xuyên hơn và giảm hiệu quả khi nguồn có độ trễ. Prefetch cao có thể tăng khả năng giữ pipeline bận, nhưng dùng thêm bộ nhớ nếu inner xử lý chậm.

Cần phân biệt:

- **Concurrency của inner:** số Publisher con đang hoạt động cùng lúc; `concatMap` giữ ở mức một.
- **Prefetch của upstream:** số phần tử nguồn có thể được yêu cầu và xếp hàng trước.
- **Demand của downstream:** số phần tử kết quả mà Subscriber sẵn sàng nhận.

Backpressure phối hợp các lượng demand này theo hợp đồng Publisher–Subscriber. Tuy vậy, nếu upstream là nguồn không tuân thủ Reactive Streams hoặc có adapter buffer vô hạn, chỉ dùng `concatMap` không đủ để bảo đảm bộ nhớ toàn hệ thống luôn bị giới hạn.

## 9. Cancellation và scheduler

Khi Subscriber cuối hủy subscription, `concatMap` hủy upstream và Publisher con đang hoạt động theo cơ chế cancellation của pipeline. Các phần tử đang chờ trong hàng đợi sẽ không được xử lý tiếp. Nhưng cancellation không thể đảo ngược tác dụng phụ đã được hệ thống bên ngoài thực hiện.

Ví dụ, một request đã được gửi tới đối tác có thể vẫn được xử lý ở phía đối tác dù subscription đã bị hủy. Với thao tác ghi hoặc thanh toán, cần idempotency và cơ chế đối soát trạng thái.

`concatMap` không tự chọn scheduler. Inner có thể là Publisher bất đồng bộ và phát tín hiệu trên thread riêng. Nếu cần chuyển bước downstream sang scheduler khác, dùng `publishOn`; nếu inner bao bọc tác vụ blocking, hãy cô lập tác vụ đó:

~~~java
Flux<Result> results =
    source.concatMap(item ->
        Mono.fromCallable(() -> legacyService.process(item))
            .subscribeOn(Schedulers.boundedElastic())
    );
~~~

Ở đây, mỗi tác vụ blocking chạy trên bounded elastic scheduler. Dù các tác vụ dùng scheduler này, `concatMap` vẫn chỉ subscribe inner tiếp theo sau khi inner hiện tại hoàn tất. Scheduler thay đổi nơi thực thi, không thay đổi chính sách tuần tự.

Nếu một inner bị treo, toàn bộ phần tử phía sau phải chờ. Đặt timeout ở vị trí phù hợp nếu nghiệp vụ có giới hạn thời gian:

~~~java
Flux<Result> results =
    source.concatMap(item ->
        remoteClient.call(item)
            .timeout(Duration.ofSeconds(2))
    );
~~~

Timeout chuyển một inner quá chậm thành lỗi; sau đó luồng sẽ dừng hoặc tiếp tục tùy cách xử lý lỗi đã chọn.

## 10. Kiểm thử thứ tự và tuần tự hóa

Dùng `StepVerifier` để xác nhận kết quả được phát theo thứ tự nguồn. Ví dụ mỗi inner mất một khoảng thời gian giả lập:

~~~java
Flux<String> result =
    Flux.just("A", "B", "C")
        .concatMap(value ->
            Mono.delay(Duration.ofMillis(100))
                .map(ignored -> value)
        );

StepVerifier.withVirtualTime(() -> result)
    .expectSubscription()
    .thenAwait(Duration.ofMillis(300))
    .expectNext("A", "B", "C")
    .verifyComplete();
~~~

Vì các inner được chạy tuần tự, tổng thời gian ảo là khoảng 300 ms. Nếu thay `concatMap` bằng `flatMap`, các Mono có thể chạy đồng thời và thứ tự hoàn tất có thể khác.

Có thể kiểm tra số inner đang hoạt động để chứng minh concurrency tối đa là một:

~~~java
AtomicInteger active = new AtomicInteger();
AtomicInteger maxActive = new AtomicInteger();

Flux<Integer> result =
    Flux.range(1, 4)
        .concatMap(value ->
            Mono.defer(() -> {
                int current = active.incrementAndGet();
                maxActive.accumulateAndGet(current, Math::max);

                return Mono.delay(Duration.ofMillis(10))
                    .map(ignored -> value)
                    .doFinally(signal -> active.decrementAndGet());
            })
        );

StepVerifier.withVirtualTime(() -> result)
    .thenAwait(Duration.ofMillis(40))
    .expectNext(1, 2, 3, 4)
    .verifyComplete();

assertThat(maxActive.get()).isEqualTo(1);
~~~

`Mono.defer` đặt việc tăng bộ đếm vào thời điểm inner được subscribe. `doFinally` giảm bộ đếm khi inner hoàn tất, lỗi hoặc bị hủy. Kiểm thử xác nhận không có hai inner cùng hoạt động.

Các trường hợp nên kiểm thử thêm:

- Inner hoàn tất rỗng; phần tử nguồn kế tiếp vẫn được xử lý.
- Inner phát nhiều phần tử; nhóm kết quả của nó hoàn tất trước nhóm kế tiếp.
- Inner phát lỗi; xác minh luồng dừng hoặc recovery theo chính sách.
- Cancellation xảy ra khi inner đang chạy; xác minh inner nhận cancellation và phần tử chờ không được xử lý.
- Inner không hoàn tất; xác minh timeout hoặc chính sách hủy hoạt động.
- Prefetch thay đổi; kiểm tra mức bộ đệm và hành vi demand khi tải tăng.

## 11. Những nhầm lẫn thường gặp

- **`concatMap` chỉ sắp xếp kết quả sau khi mọi inner đã chạy:** nó subscribe inner lần lượt; inner sau chưa bắt đầu khi inner trước chưa hoàn tất.
- **Prefetch là concurrency:** prefetch điều khiển lượng phần tử upstream được yêu cầu trước; số inner hoạt động của `concatMap` vẫn là một.
- **`flatMapSequential` tương đương `concatMap`:** flatMapSequential cho inner chạy đồng thời rồi phát kết quả theo thứ tự; concatMap tuần tự hóa cả subscription inner.
- **`concatMap` tạo thứ tự nghiệp vụ từ nguồn bất kỳ:** nó chỉ giữ thứ tự phần tử được phát tới toán tử; nguồn phải xác định thứ tự đúng từ trước.
- **Inner phát một phần tử là đủ để chuyển sang inner kế tiếp:** nếu inner là Flux, concatMap chờ inner hoàn tất, không chỉ chờ phần tử đầu tiên.
- **Một inner rỗng làm dừng pipeline:** inner rỗng hoàn tất bình thường; concatMap tiếp tục phần tử nguồn tiếp theo.
- **Inner không kết thúc không ảnh hưởng phần tử sau:** inner không kết thúc giữ lượt và chặn toàn bộ phần tử phía sau.
- **Tuần tự hóa đồng nghĩa rollback an toàn:** cancellation hoặc lỗi không đảo ngược tác dụng phụ đã được hệ thống ngoài xác nhận.
- **Dùng concatMap luôn tốt hơn flatMap:** tuần tự hóa có thể làm giảm thông lượng đáng kể khi các công việc độc lập.

## 12. Bài tập vận dụng

Một hệ thống nhận các lệnh cập nhật tồn kho cho cùng một mã sản phẩm. Mỗi lệnh phải đọc số lượng hiện tại, áp dụng thay đổi và ghi kết quả mới. Nguồn phát lệnh theo thời gian tiếp nhận:

~~~java
Flux<InventoryCommand> commands =
    commandRepository.findForProduct(productId);
~~~

Hãy thiết kế pipeline và giải thích:

1. Vì sao `flatMap` có thể gây ra hai lệnh cùng đọc một trạng thái cũ rồi ghi đè kết quả của nhau?
2. Viết pipeline dùng `concatMap` để đọc, áp dụng lệnh và lưu trạng thái theo thứ tự.
3. Nếu thao tác lưu trả về `Mono<Void>`, làm sao để pipeline vẫn phát ra trạng thái mới sau khi lưu thành công?
4. Nếu một lệnh lỗi do dữ liệu không hợp lệ nhưng các lệnh tiếp theo vẫn phải xử lý, đặt `onErrorResume` ở đâu?
5. Nếu một lệnh gọi dịch vụ ngoài bị treo, cần dùng timeout như thế nào để không chặn các lệnh phía sau vô thời hạn?
6. Tham số prefetch có ý nghĩa gì trong bài toán này? Nó có làm tăng số lệnh đang được xử lý đồng thời không?
7. Nếu cần xử lý đồng thời các sản phẩm khác nhau nhưng tuần tự trong cùng một sản phẩm, có thể tổ chức luồng theo khóa sản phẩm như thế nào?

**Gợi ý:** dùng `concatMap` để ghép chuỗi đọc, cập nhật và lưu cho từng command. Nếu cần tiếp tục sau lỗi riêng của một command, chuyển lỗi thành kết quả nghiệp vụ bên trong mapper. Với nhiều sản phẩm độc lập, có thể nhóm theo `productId`, dùng `concatMap` trong từng nhóm và giới hạn số nhóm được xử lý đồng thời; cần kiểm soát số lượng group và tiêu thụ đầy đủ các nhóm.

## Kết luận

`concatMap` ghép Publisher con theo thứ tự: nó chờ inner hiện tại hoàn tất rồi mới subscribe inner tiếp theo. Nhờ đó, các phần tử đầu ra giữ thứ tự nguồn và các tác vụ bất đồng bộ được tuần tự hóa. Lựa chọn này phù hợp khi thứ tự thực thi là yêu cầu nghiệp vụ, nhưng có thể làm giảm thông lượng và khiến một inner chậm chặn các phần tử sau. Hãy phân biệt concurrency với prefetch, xử lý lỗi và timeout theo chính sách rõ ràng, đồng thời kiểm thử thứ tự, cancellation và số inner đang hoạt động để pipeline Reactor có hành vi dự đoán được.
