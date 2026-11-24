# Luồng thực thi

## Công việc thiên về CPU và công việc chờ I/O

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học cách tổ chức ứng dụng quanh các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Một pipeline reactive có thể chứa nhiều loại công việc: có bước cần CPU để tính toán, có bước chủ yếu chờ mạng hoặc đĩa phản hồi. Chọn scheduler phù hợp cho từng loại giúp hệ thống sử dụng tài nguyên hiệu quả và tránh làm nghẽn những thread phục vụ các luồng khác.

**Công việc thiên về CPU (CPU-bound)** dành phần lớn thời gian thực hiện phép tính: mã hóa, nén, biến đổi ảnh, tính điểm, phân tích dữ liệu hoặc áp dụng thuật toán. **Công việc chờ I/O (I/O-bound)** dành phần lớn thời gian chờ dữ liệu từ mạng, cơ sở dữ liệu, hệ thống tệp hoặc dịch vụ khác. Hai loại công việc có đặc tính tài nguyên khác nhau nên không nên chạy chúng một cách tùy tiện trên cùng một nhóm thread.

Trong Reactor, `Schedulers.parallel()` thường phù hợp với phép tính CPU-bound không blocking; `Schedulers.boundedElastic()` phù hợp để cô lập các API blocking, đặc biệt là thư viện cũ hoặc JDBC đồng bộ. Với I/O bất đồng bộ thực sự như WebClient, thường không cần chuyển sang bounded elastic chỉ vì đó là I/O: client và event loop đã quản lý việc chờ mà không giữ một thread cho mỗi request.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt công việc CPU-bound, I/O-bound blocking và I/O-bound non-blocking.
- Chọn `Schedulers.parallel()` cho tính toán CPU và `Schedulers.boundedElastic()` cho lời gọi blocking.
- Dùng `subscribeOn` và `publishOn` đúng vị trí để điều khiển luồng thực thi.
- Ghép các bước I/O và CPU trong cùng một pipeline mà không chặn event loop.
- Giới hạn concurrency, tránh tạo quá nhiều tác vụ và hiểu tác động của hàng đợi scheduler.
- Quản lý scheduler tùy chỉnh theo vòng đời ứng dụng.
- Đo lường và kiểm thử hành vi thực thi thay vì suy đoán từ tên API.

## 1. Phân biệt CPU-bound và I/O-bound

Điểm phân biệt không nằm ở việc một hàm có trả về `Mono` hay `Flux`, mà ở nơi thời gian thực thi được tiêu thụ.

### Công việc CPU-bound

Một tác vụ CPU-bound liên tục thực hiện tính toán và cần thời gian xử lý của CPU. Ví dụ:

- Tính checksum hoặc hash trên dữ liệu lớn.
- Nén hoặc giải nén nội dung.
- Chuyển đổi ảnh, âm thanh hoặc video.
- Tính toán điểm xếp hạng trên tập dữ liệu lớn.
- Phân tích cú pháp hoặc biến đổi dữ liệu phức tạp.
- Chạy thuật toán tối ưu hóa hoặc mô hình tính toán trong bộ nhớ.

Nếu tác vụ CPU-bound chiếm một thread quá lâu, các công việc khác được xếp trên cùng scheduler phải chờ. Tạo thêm nhiều thread không làm CPU có thêm năng lực tính toán; vượt quá số lõi khả dụng thường làm tăng context switching và tranh chấp.

### Công việc I/O-bound

Một tác vụ I/O-bound thường dành nhiều thời gian chờ một tài nguyên bên ngoài:

- Chờ HTTP response từ dịch vụ khác.
- Chờ database trả kết quả.
- Chờ đọc hoặc ghi tệp.
- Chờ message broker hoặc socket.
- Chờ một API legacy gọi callback.

Cần phân biệt hai kiểu I/O:

1. **I/O blocking:** thread gọi bị giữ lại cho tới khi thao tác hoàn tất. Ví dụ JDBC đồng bộ hoặc một thư viện HTTP blocking.
2. **I/O non-blocking:** thao tác được đăng ký bất đồng bộ; thread có thể xử lý công việc khác trong lúc chờ. Ví dụ WebClient với Reactor Netty hoặc driver reactive.

Cả hai đều chờ I/O, nhưng chỉ kiểu blocking cần một thread dành riêng để chờ. Vì vậy, không nên đưa mọi thao tác mạng sang `boundedElastic()` theo thói quen.

| Đặc điểm | CPU-bound | I/O-bound blocking | I/O-bound non-blocking |
|---|---|---|---|
| Thời gian chủ yếu dùng cho | Tính toán | Chờ trong lời gọi blocking | Chờ sự kiện I/O mà không giữ thread |
| Tài nguyên dễ bão hòa | CPU, cache CPU, bộ nhớ | Thread, connection, tài nguyên I/O | Connection, event loop, giới hạn dịch vụ |
| Scheduler thường chọn | `parallel()` | `boundedElastic()` | Scheduler/event loop của client |
| Rủi ro chính | Oversubscription, CPU saturation | Cạn thread, giữ thread khi chờ | Nghẽn event loop nếu có đoạn blocking |
| Cách tăng năng lực | Tối ưu thuật toán, giới hạn song song theo CPU | Giới hạn concurrency, pool và timeout | Điều tiết demand/concurrency và connection |

Một pipeline có thể kết hợp cả ba loại. Ví dụ, ứng dụng gọi dịch vụ HTTP bất đồng bộ, sau đó giải mã và tính điểm trên CPU, rồi ghi kết quả bằng JDBC blocking. Ta cần đặt ranh giới scheduler theo từng bước thay vì chuyển cả pipeline sang một scheduler duy nhất.

## 2. Vì sao scheduler phù hợp lại quan trọng?

Scheduler quyết định nơi một phần công việc reactive được thực thi. Chọn sai scheduler có thể tạo ra các vấn đề sau:

- **Blocking trên event loop:** một lời gọi JDBC hoặc `Thread.sleep` chặn thread xử lý nhiều kết nối, làm độ trễ của nhiều request cùng tăng.
- **CPU work trên bounded elastic:** các phép tính nặng chiếm worker được thiết kế để chờ blocking I/O, làm tăng hàng đợi và tạo nhiều thread hơn mức CPU có thể sử dụng hiệu quả.
- **Blocking trên parallel:** một tác vụ chờ lâu giữ worker trong nhóm thread nhỏ dành cho tính toán, khiến các phép tính khác bị đói tài nguyên.
- **Chuyển scheduler quá nhiều:** mỗi lần chuyển có thể tạo chi phí lập lịch, hàng đợi và chuyển ngữ cảnh; không nên thêm `publishOn` ở mọi toán tử.
- **Concurrency không giới hạn:** nhiều Publisher con cùng hoạt động có thể làm cạn connection, hàng đợi hoặc CPU ngay cả khi scheduler đã chọn đúng.

Scheduler không làm cho một thuật toán chậm trở nên nhanh hơn và cũng không biến API blocking thành non-blocking. Nó giúp cô lập loại công việc vào nhóm thread phù hợp để các phần khác của hệ thống tiếp tục hoạt động.

## 3. Schedulers.parallel() cho tính toán CPU

`Schedulers.parallel()` cung cấp một scheduler dùng chung với số worker giới hạn, thường được cấu hình dựa trên số CPU khả dụng. Đây là lựa chọn mặc định phù hợp cho các bước tính toán không blocking.

Ví dụ, ứng dụng cần tính điểm cho từng bản ghi:

~~~java
Flux<Score> scores =
    records
        .publishOn(Schedulers.parallel())
        .map(this::calculateScore);
~~~

`publishOn` chuyển việc xử lý các tín hiệu downstream tiếp theo sang worker của scheduler parallel. Hàm `calculateScore` được gọi trên scheduler này, thay vì thread phát tín hiệu upstream.

Cần hiểu giới hạn của ví dụ: một toán tử `publishOn` chuyển chuỗi downstream sang một worker và các tín hiệu trên nhánh đó được xử lý tuần tự. Nó không tự chia từng phần tử thành nhiều phép tính chạy song song. Nếu chỉ cần tránh chạy phép tính trên event loop và không cần xử lý nhiều phần tử cùng lúc, cách này có thể đủ.

### Chạy nhiều phép tính độc lập trên các CPU

Nếu các phần tử có thể được tính độc lập và ta muốn tận dụng nhiều lõi, có thể dùng `ParallelFlux`:

~~~java
Flux<Score> scores =
    records
        .parallel()
        .runOn(Schedulers.parallel())
        .map(this::calculateScore)
        .sequential();
~~~

- `parallel()` chia luồng thành các rail để xử lý song song.
- `runOn(Schedulers.parallel())` phân phối các rail lên worker của scheduler.
- `map` thực hiện phép tính trên từng rail.
- `sequential()` hợp nhất kết quả trở lại thành `Flux`.

Số rail mặc định thường dựa trên parallelism của scheduler. Có thể chỉ định số rail nếu có lý do đo lường cụ thể:

~~~java
Flux<Score> scores =
    records
        .parallel(4)
        .runOn(Schedulers.parallel())
        .map(this::calculateScore)
        .sequential();
~~~

Ở đây có bốn rail. Con số này là ví dụ; hãy chọn dựa trên CPU khả dụng, chi phí mỗi phần tử và kết quả đo tải. Việc tăng số rail vượt quá năng lực CPU không đảm bảo thông lượng cao hơn.

Khi hợp nhất bằng `sequential()`, không nên mặc định rằng kết quả giữ nguyên thứ tự đầu vào. Các rail có thể hoàn tất và phát phần tử theo lịch khác nhau. Nếu thứ tự là yêu cầu nghiệp vụ, cần chọn cách ghép có bảo toàn thứ tự hoặc mang chỉ số để sắp xếp lại có kiểm soát.

### Bảo toàn thứ tự khi tính toán đồng thời

Một lựa chọn khác là tạo Publisher con cho từng phép tính rồi dùng `flatMapSequential`:

~~~java
Flux<Score> scores =
    records.flatMapSequential(
        record -> Mono.fromCallable(() -> calculateScore(record))
            .subscribeOn(Schedulers.parallel()),
        4
    );
~~~

Tối đa bốn phép tính con được đăng ký đồng thời; kết quả được phát theo thứ tự nguồn. Nếu phép tính đầu tiên chậm hơn các phép tính sau, kết quả hoàn tất sớm phải chờ trong bộ đệm để giữ thứ tự. Vì vậy, bảo toàn thứ tự có thể làm tăng bộ nhớ và độ trễ đầu ra.

Chọn cách xử lý dựa trên nhu cầu thực tế:

- Dùng `publishOn(parallel())` khi muốn chuyển một chuỗi xử lý tuần tự sang worker CPU.
- Dùng `parallel().runOn(...)` khi muốn chia luồng thành nhiều rail.
- Dùng `flatMapSequential` khi các tác vụ độc lập có thể chạy đồng thời nhưng kết quả phải theo thứ tự nguồn.

## 4. BoundedElastic cho lời gọi blocking

`Schedulers.boundedElastic()` dành cho những tác vụ có thể giữ thread trong lúc chờ, như gọi JDBC đồng bộ, thư viện HTTP blocking hoặc API tệp blocking. Scheduler này giới hạn số thread và lượng công việc được xếp hàng theo cấu hình của Reactor. Các giới hạn mặc định phụ thuộc phiên bản và cấu hình môi trường.

Để bọc một lời gọi blocking, dùng `Mono.fromCallable` hoặc `Mono.fromRunnable` rồi đặt `subscribeOn`:

~~~java
Mono<Customer> customer =
    Mono.fromCallable(() -> legacyCustomerDao.load(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` trì hoãn lời gọi tới khi có subscription. `subscribeOn` đưa quá trình subscribe nguồn và việc thực thi callable lên bounded elastic scheduler. Khi callable đang chờ database, thread của nhóm này bị giữ; event loop hoặc worker CPU vẫn có thể xử lý công việc khác.

Một ví dụ với API blocking trả về kết quả ghi:

~~~java
Mono<Void> save =
    Mono.fromRunnable(() -> legacyDao.save(entity))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Nếu API blocking có thể ném exception, Reactor chuyển exception đó thành tín hiệu `onError`. Có thể xử lý ở pipeline bằng `onErrorMap`, `onErrorResume` hoặc retry có giới hạn theo chính sách của nghiệp vụ.

### Không bọc lời gọi blocking bằng Mono.just

Đoạn mã sau không trì hoãn lời gọi:

~~~java
Mono<Customer> wrong =
    Mono.just(legacyCustomerDao.load(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Java đánh giá `legacyCustomerDao.load(customerId)` trước khi gọi `Mono.just`. Vì vậy, thao tác blocking xảy ra ngay trong lúc lắp ráp, có thể chặn thread đang tạo pipeline. `subscribeOn` được gắn sau đó không thể chuyển ngược một lời gọi đã xảy ra sang scheduler khác.

Hãy dùng:

~~~java
Mono<Customer> correct =
    Mono.fromCallable(() -> legacyCustomerDao.load(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Tính lười của nguồn và vị trí scheduler đều cần thiết: `fromCallable` trì hoãn công việc, còn `subscribeOn` chọn nơi công việc được thực thi.

### Giới hạn và timeout cho blocking I/O

Bounded elastic không phải tài nguyên vô hạn. Nếu ứng dụng nhận nhiều tác vụ blocking hơn số worker và sức chứa hàng đợi, công việc sẽ phải chờ hoặc bị từ chối khi vượt giới hạn. Hãy:

- Đặt giới hạn concurrency ở upstream bằng `flatMap(..., concurrency)`.
- Đặt timeout cho thao tác nếu thư viện hoặc tầng gọi hỗ trợ.
- Cấu hình connection pool phù hợp với số worker có thể gọi database.
- Theo dõi độ sâu hàng đợi, thời gian chờ worker và số tác vụ bị từ chối.
- Tránh tạo một scheduler mới cho mỗi request.

Ví dụ giới hạn số truy vấn blocking đang hoạt động:

~~~java
Flux<Customer> customers =
    customerIds.flatMap(
        id -> Mono.fromCallable(() -> legacyCustomerDao.load(id))
            .subscribeOn(Schedulers.boundedElastic())
            .timeout(Duration.ofSeconds(2)),
        12
    );
~~~

Tham số `12` giới hạn số Publisher con được hoạt động đồng thời trong `flatMap`. Nó không nhất thiết là số thread của bounded elastic; scheduler có thể dùng worker chung và có hàng đợi riêng. Hãy chọn concurrency cùng với giới hạn connection pool và năng lực database.

Timeout phát lỗi khi thời hạn chờ hết và gửi cancellation upstream. Thư viện blocking chỉ dừng thực sự nếu nó hỗ trợ interrupt hoặc cancellation. Không nên giả định mọi JDBC driver hay API blocking sẽ dừng ngay khi subscription bị hủy.

## 5. I/O non-blocking thường không cần boundedElastic

Một HTTP client reactive như WebClient có thể thực hiện I/O bất đồng bộ trên event loop. Trong thời gian chờ server, thread không bị giữ riêng cho request đó. Vì vậy, không cần chuyển request sang bounded elastic chỉ vì nó gọi mạng:

~~~java
Mono<Customer> customer =
    webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class);
~~~

Publisher này có thể được ghép trực tiếp với các bước reactive khác. WebClient quản lý việc đăng ký I/O và phát tín hiệu khi có dữ liệu.

Vấn đề xuất hiện nếu ta đặt một hàm blocking trong callback chạy trên event loop:

~~~java
Mono<CustomerView> wrong =
    webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class)
        .map(customer -> legacyCustomerDao.loadExtra(customer.id()))
        .map(this::toView);
~~~

Nếu `loadExtra` là JDBC blocking, nó có thể giữ event loop trong lúc chờ database. Các kết nối khác dùng cùng event loop bị ảnh hưởng.

Hãy cô lập riêng bước blocking:

~~~java
Mono<CustomerView> customerView =
    webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class)
        .flatMap(customer ->
            Mono.fromCallable(() ->
                    legacyCustomerDao.loadExtra(customer.id())
                )
                .subscribeOn(Schedulers.boundedElastic())
                .map(extra -> toView(customer, extra))
        );
~~~

HTTP request vẫn dùng I/O non-blocking. Chỉ lời gọi JDBC được chuyển sang bounded elastic. Khi nó hoàn tất, kết quả được ghép trở lại pipeline.

Nếu có thể thay thư viện blocking bằng driver reactive hoặc API non-blocking, đó thường là lựa chọn tốt hơn trong một ứng dụng reactive. Bounded elastic là ranh giới tương thích hữu ích cho những thành phần blocking chưa thể thay thế, nhưng vẫn cần giới hạn tải và theo dõi.

## 6. subscribeOn và publishOn trong pipeline hỗn hợp

Hai toán tử này đều liên quan tới scheduler nhưng có tác dụng khác nhau.

- `subscribeOn(scheduler)` điều khiển nơi quá trình subscribe vào nguồn upstream được thực hiện. Với nguồn deferred như `fromCallable`, nó quyết định thread chạy công việc nguồn.
- `publishOn(scheduler)` tạo ranh giới thực thi cho các tín hiệu downstream tiếp theo. Các toán tử sau nó chạy trên worker được chọn, cho tới khi gặp một ranh giới `publishOn` khác.

Ví dụ kết hợp I/O blocking và tính toán:

~~~java
Mono<Report> report =
    Mono.fromCallable(() -> legacyDao.loadData(reportId))
        .subscribeOn(Schedulers.boundedElastic())
        .publishOn(Schedulers.parallel())
        .map(this::calculateReport);
~~~

Trình tự:

1. Khi có subscription, `fromCallable` chạy trên bounded elastic.
2. Kết quả đọc dữ liệu được phát xuống.
3. `publishOn` chuyển các tín hiệu downstream sang scheduler parallel.
4. `calculateReport` chạy trên worker dành cho công việc CPU.

Nếu pipeline tiếp tục gọi một API blocking khác, cần cô lập bước đó thêm một lần bằng nguồn deferred và scheduler phù hợp. Đừng giả định `publishOn(parallel())` làm các toán tử blocking phía sau tự chuyển sang bounded elastic.

Một ví dụ với I/O non-blocking, tính toán CPU và ghi blocking:

~~~java
Mono<Void> workflow =
    webClient.get()
        .uri("/transactions/{id}", transactionId)
        .retrieve()
        .bodyToMono(Transaction.class)
        .publishOn(Schedulers.parallel())
        .map(this::calculateRisk)
        .flatMap(risk ->
            Mono.fromRunnable(() -> legacyAuditDao.save(risk))
                .subscribeOn(Schedulers.boundedElastic())
        );
~~~

Mỗi ranh giới được đặt ở nơi loại công việc thay đổi. HTTP client dùng cơ chế non-blocking của nó; phép tính rủi ro chuyển sang worker CPU; thao tác ghi audit blocking được cô lập trên bounded elastic.

Không nên thêm `subscribeOn` hoặc `publishOn` chỉ để "cho chắc". Mỗi ranh giới có chi phí lập lịch và có thể tạo hàng đợi. Hãy đặt chúng theo ranh giới blocking/CPU thực sự, sau đó đo lường.

## 7. Concurrency khác với parallelism

Hai khái niệm này có liên hệ nhưng không giống nhau:

- **Concurrency (đồng thời):** nhiều tác vụ đang được tiến hành trong cùng khoảng thời gian; chúng có thể luân phiên chờ I/O.
- **Parallelism (song song):** nhiều tác vụ thực sự thực thi cùng lúc trên nhiều lõi CPU.

Một pipeline có thể có concurrency cao nhưng parallelism thấp. Ví dụ, hàng trăm request HTTP non-blocking đang chờ phản hồi không cần hàng trăm thread. Ngược lại, một phép tính CPU-bound cần số worker phù hợp với lõi CPU để chạy song song hiệu quả.

Với I/O, `flatMap` concurrency cho phép nhiều request con đang hoạt động:

~~~java
Flux<Response> responses =
    requestIds.flatMap(
        id -> webClient.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(Response.class),
        64
    );
~~~

Con số 64 là giới hạn số Publisher con đồng thời, không phải số thread. Nếu tăng quá cao, dịch vụ từ xa hoặc connection pool có thể bị quá tải.

Với CPU, số tác vụ thực sự chạy song song nên gần với năng lực CPU và đặc điểm phép tính. Dùng `parallel()` hoặc concurrency hữu hạn trên scheduler parallel; tránh tạo hàng nghìn tác vụ CPU đang chờ nếu không có lợi ích đo được.

## 8. Quản lý scheduler dùng chung và scheduler tùy chỉnh

Reactor cung cấp các scheduler dùng chung như:

- `Schedulers.parallel()` cho công việc CPU-bound.
- `Schedulers.boundedElastic()` cho công việc blocking.
- `Schedulers.single()` cho công việc cần một worker tuần tự.
- `Schedulers.immediate()` để thực thi ngay trên thread hiện tại trong một số tình huống đặc biệt.

Các scheduler dùng chung được Reactor quản lý. Thông thường, không dispose chúng sau mỗi request hoặc mỗi subscription.

Nếu cần cô lập một nhóm API blocking có giới hạn riêng, có thể tạo scheduler tùy chỉnh:

~~~java
Scheduler legacyIo =
    Schedulers.newBoundedElastic(
        20,
        500,
        "legacy-io"
    );
~~~

Ví dụ tạo scheduler với tối đa 20 thread và giới hạn 500 tác vụ được xếp hàng cho mỗi backing thread theo hợp đồng API này. Các con số chỉ minh họa; cần chọn theo số kết nối, thời gian blocking và năng lực dịch vụ.

Dùng scheduler đó cho các lời gọi thuộc nhóm legacy:

~~~java
Mono<Data> data =
    Mono.fromCallable(() -> legacyClient.fetch(key))
        .subscribeOn(legacyIo);
~~~

Scheduler tùy chỉnh cần có chủ sở hữu vòng đời. Hãy dispose khi ứng dụng shutdown hoặc thành phần sở hữu scheduler dừng:

~~~java
@PreDestroy
void shutdown() {
    legacyIo.dispose();
}
~~~

Không tạo scheduler mới trong từng lần gọi phương thức:

~~~java
// Không nên: mỗi request tạo thêm một scheduler.
Mono<Data> load(String key) {
    Scheduler scheduler = Schedulers.newBoundedElastic(10, 100, "request-io");
    return Mono.fromCallable(() -> legacyClient.fetch(key))
        .subscribeOn(scheduler);
}
~~~

Cách này dễ làm tăng số thread, hàng đợi và tài nguyên không được giải phóng. Tạo scheduler ở cấp ứng dụng hoặc thành phần có vòng đời rõ ràng, tái sử dụng cho nhiều subscription và dispose khi chủ sở hữu kết thúc.

## 9. Virtual threads và bounded elastic

Ở các phiên bản Reactor hỗ trợ virtual thread và chạy trên Java 21 trở lên, bounded elastic có thể được cấu hình để sử dụng virtual thread cho từng tác vụ. Một số phiên bản dùng system property:

```text
reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true
```

Tùy chọn này phụ thuộc phiên bản Reactor và cấu hình JVM. Hãy kiểm tra tài liệu của phiên bản đang dùng trước khi bật.

Virtual thread có thể giảm chi phí giữ thread cho nhiều tác vụ blocking, nhưng không làm cho tài nguyên bên ngoài trở nên vô hạn. Database vẫn có giới hạn connection; dịch vụ HTTP vẫn có quota; CPU vẫn có số lõi hữu hạn. Vì vậy, vẫn cần giới hạn concurrency, timeout và kiểm soát hàng đợi ở những nơi phù hợp.

Không nên hiểu rằng bật virtual thread sẽ tự động biến mọi API blocking thành reactive non-blocking. Mô hình thực thi khác đi, nhưng lời gọi vẫn blocking theo cách sử dụng của nó và vẫn tiêu thụ tài nguyên trong thời gian chờ.

## 10. Các lỗi thiết kế thường gặp

### Chạy JDBC trên parallel

~~~java
Mono<Customer> customer =
    Mono.fromCallable(() -> jdbcTemplate.queryForObject(sql, mapper))
        .subscribeOn(Schedulers.parallel());
~~~

JDBC là blocking. Chạy nó trên scheduler dành cho CPU có thể giữ worker trong lúc chờ database và làm nghẽn các phép tính khác. Hãy chuyển sang bounded elastic hoặc dùng driver reactive.

### Chạy phép tính nặng trên bounded elastic

~~~java
Mono<Score> score =
    Mono.fromCallable(() -> expensiveCalculation(input))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đoạn mã vẫn có thể chạy, nhưng bounded elastic không được thiết kế để tối ưu phép tính CPU. Nhiều tác vụ tính toán có thể chiếm worker và làm hàng đợi blocking tăng. Dùng parallel cho phép tính không blocking, với concurrency phù hợp.

### Nghĩ rằng publishOn làm lời gọi nguồn chạy trên scheduler mới

~~~java
Mono<Data> data =
    Mono.just(legacyClient.fetch())
        .publishOn(Schedulers.boundedElastic());
~~~

`legacyClient.fetch()` đã chạy trước khi `Mono.just` được tạo. `publishOn` chỉ ảnh hưởng các tín hiệu downstream sau ranh giới của nó. Hãy dùng `fromCallable` kết hợp `subscribeOn`.

### Chặn thread trong pipeline reactive

Không dùng `block()`, `Thread.sleep()` hoặc chờ `Future.get()` trong event loop hoặc scheduler parallel. Nếu cần tích hợp API blocking, bọc nó trong nguồn deferred và cô lập trên bounded elastic.

### Tạo quá nhiều ranh giới scheduler

Mỗi `publishOn` có thể tạo hàng đợi và chi phí chuyển worker. Nếu pipeline đổi scheduler nhiều lần mà không có ranh giới công việc rõ ràng, độ trễ và độ phức tạp sẽ tăng. Đặt ranh giới theo loại công việc, không theo từng toán tử.

### Không giới hạn concurrency

Dù scheduler có giới hạn thread, upstream vẫn có thể tạo quá nhiều Publisher con và làm tăng hàng đợi. Giới hạn `flatMap` concurrency, connection pool và lượng dữ liệu chờ; quan sát cả các lớp hàng đợi, không chỉ số thread.

## 11. Đo lường để xác nhận lựa chọn scheduler

Không thể kết luận scheduler phù hợp chỉ bằng việc pipeline chạy thành công. Cần đo hành vi dưới tải đại diện.

| Chỉ số | Điều cần quan sát | Dấu hiệu cần điều tra |
|---|---|---|
| CPU utilization | Mức sử dụng CPU theo thời gian | CPU luôn bão hòa trong khi throughput không tăng |
| Thread count | Số thread hoạt động và chờ | Tăng liên tục hoặc vượt dự kiến |
| Scheduler queue | Số tác vụ chờ worker | Hàng đợi tăng đều, thời gian chờ dài |
| I/O pool | Connection đang dùng, chờ và timeout | Pool cạn dù CPU còn thấp |
| Latency | p50, p95, p99 | Tail latency tăng khi tải tăng |
| Throughput | Công việc hoàn tất mỗi giây | Offered load tăng nhưng completed throughput đứng yên |
| Rejection/error | Tác vụ bị từ chối, timeout, lỗi pool | Quá tải hoặc giới hạn tài nguyên bị chạm |
| GC và heap | Tần suất GC, bộ nhớ giữ bởi queue | Queue lớn gây tăng heap và pause |

Một quy trình thử nghiệm có thể làm như sau:

1. Đo baseline khi chạy với tải nhỏ và cấu hình hiện tại.
2. Tăng dần arrival rate hoặc số request đồng thời.
3. Quan sát CPU, queue, thread, connection pool và phân vị độ trễ.
4. Thay đổi một yếu tố mỗi lần, chẳng hạn concurrency hoặc giới hạn pool.
5. Chạy lại cùng kịch bản và so sánh throughput cùng p95/p99.
6. Giữ cấu hình chỉ khi nó cải thiện mục tiêu mà không làm tăng lỗi hoặc tiêu thụ tài nguyên ngoài giới hạn.

Đừng chỉ tối ưu throughput cực đại. Mức tải vận hành cần giữ được SLO, thời gian chờ và tỷ lệ lỗi trong thời gian đủ dài.

## 12. Kiểm thử pipeline có chuyển scheduler

Có thể kiểm thử logic kết quả bằng `StepVerifier`, đồng thời quan sát thread khi cần xác nhận ranh giới thực thi. Không nên dùng assertion phụ thuộc tên thread cụ thể nếu tên đó thay đổi theo phiên bản hoặc môi trường.

Ví dụ kiểm tra kết quả của một tác vụ blocking đã được bọc:

~~~java
Mono<String> result =
    Mono.fromCallable(() -> "loaded")
        .subscribeOn(Schedulers.boundedElastic())
        .publishOn(Schedulers.parallel())
        .map(String::toUpperCase);

StepVerifier.create(result)
    .expectNext("LOADED")
    .verifyComplete();
~~~

Test này xác nhận tín hiệu và kết quả của pipeline. Để xác nhận chính sách scheduler, có thể dùng hook quan sát thread hoặc một hàm test ghi nhận tên thread; nên kiểm tra thuộc tính tổng quát như thread không phải event loop, thay vì phụ thuộc vào một tên cụ thể.

Với phép tính song song, có thể kiểm thử số tác vụ đang hoạt động tối đa bằng bộ đếm nguyên tử, như cách đo concurrency trong một pipeline `flatMap`. Với blocking I/O, dùng một fake có thời gian chờ điều khiển được và xác minh cancellation/timeout theo hợp đồng của adapter.

Khi kiểm thử dùng scheduler tùy chỉnh, hãy dispose scheduler trong `finally` hoặc fixture teardown. Không để scheduler và worker sống qua nhiều test nếu chúng làm trạng thái chia sẻ ảnh hưởng kết quả.

## 13. Bài tập vận dụng

Một pipeline xử lý hóa đơn gồm ba bước:

1. Gọi WebClient lấy dữ liệu hóa đơn.
2. Dùng một thư viện cũ để đọc thêm dữ liệu từ JDBC.
3. Tính thuế và điểm rủi ro trên một tập dữ liệu lớn.

Hãy thiết kế cách điều phối:

1. Bước WebClient có cần chuyển sang bounded elastic không? Giải thích theo cơ chế I/O.
2. Bọc lời gọi JDBC bằng Publisher nào và chọn scheduler nào?
3. Đặt ranh giới `publishOn` hoặc `subscribeOn` ở đâu để phép tính CPU không chạy trên event loop?
4. Nếu cần tính nhiều hóa đơn đồng thời, chọn `parallel()`, `flatMap` hay `flatMapSequential`? Điều kiện bảo toàn thứ tự là gì?
5. Concurrency của bước JDBC nên phụ thuộc những giới hạn nào?
6. Nếu JDBC chậm, timeout và cancellation có bảo đảm truy vấn dừng ngay không?
7. Những metric nào cần theo dõi để biết scheduler đang bị nghẽn?

**Gợi ý:** giữ WebClient trên cơ chế non-blocking của client; bọc JDBC bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; chuyển phép tính CPU sang `Schedulers.parallel()`. Nếu tính nhiều hóa đơn đồng thời, giới hạn concurrency theo CPU, connection pool và yêu cầu thứ tự. Đo queue, connection, CPU và p95/p99 trước khi điều chỉnh số worker.

## Kết luận

Công việc CPU-bound cần worker phù hợp với năng lực CPU và thường dùng `Schedulers.parallel()`; công việc I/O-bound blocking cần được cô lập trên `Schedulers.boundedElastic()`; I/O non-blocking thường nên giữ trên cơ chế event loop của client reactive. Dùng `fromCallable` để trì hoãn lời gọi blocking, `subscribeOn` để chọn nơi thực thi nguồn và `publishOn` để chuyển các bước downstream. Khi kết hợp nhiều loại công việc, hãy giới hạn concurrency, quản lý scheduler theo vòng đời ứng dụng và đo hàng đợi, tài nguyên cùng độ trễ dưới tải. Lựa chọn đúng giúp pipeline `Mono`/`Flux` giữ được khả năng đáp ứng mà không làm nghẽn các thread phục vụ những luồng khác.
