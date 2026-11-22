# Khi nào reactive phù hợp và khi nào làm tăng độ phức tạp?

**Bối cảnh:** Spring Framework – Reactive (đặc biệt là Spring WebFlux và Project Reactor). Bài này giúp lựa chọn mô hình lập trình phù hợp với tải thực tế, thay vì mặc định rằng reactive luôn nhanh hơn Spring MVC.

## 1. Hiểu đúng vấn đề mà reactive giải quyết

Trong ứng dụng web truyền thống, một request thường được xử lý theo luồng tuần tự: nhận request → gọi dịch vụ/đọc cơ sở dữ liệu → chờ kết quả → trả response. Với cách gọi I/O chặn (blocking), luồng Java đang xử lý request có thể phải đứng đợi mạng hoặc cơ sở dữ liệu. Khi có rất nhiều request đồng thời, số luồng, stack bộ nhớ và chi phí chuyển ngữ cảnh có thể tăng đáng kể.

Mô hình reactive cho phép mô tả **chuỗi xử lý bất đồng bộ, không chặn (non-blocking)**: khi một lời gọi I/O đang chờ, luồng thực thi có thể phục vụ việc khác; khi dữ liệu sẵn sàng, pipeline tiếp tục. Trong hệ sinh thái Spring:

- **Spring WebFlux** là web stack hỗ trợ lập trình reactive trên nền Reactor; thường sử dụng ít luồng xử lý I/O hơn so với cách tạo một luồng bị chặn cho mỗi request đang đợi.
- **`Mono<T>`** mô tả luồng phát ra từ 0 đến 1 giá trị (hoặc lỗi); **`Flux<T>`** phát ra từ 0 đến nhiều giá trị (hoặc lỗi).
- **Reactive Streams** định nghĩa cơ chế yêu cầu dữ liệu (demand) giữa publisher và subscriber, tạo cơ sở cho **backpressure**: bên tiêu thụ có thể thông báo khả năng tiếp nhận thay vì bị đẩy không giới hạn.
- Pipeline thường chỉ thực sự bắt đầu khi có subscriber. Trong WebFlux, framework đăng ký subscription khi xử lý response; tầng controller/service thông thường **trả về `Mono`/`Flux`**, không tự `subscribe()`.

**Điều reactive không tự tạo ra:** CPU nhanh hơn, cơ sở dữ liệu trả lời nhanh hơn, mạng ít độ trễ hơn, thứ tự xử lý luôn được đảm bảo, hay backpressure xuyên suốt mọi giao thức và thư viện. Reactive tối ưu cách sử dụng tài nguyên trong thời gian **chờ I/O**, với điều kiện những thành phần quan trọng trên đường đi thật sự hỗ trợ non-blocking.

Ví dụ: hai dịch vụ độc lập mất khoảng 120 ms và 180 ms để trả lời. Nếu gọi tuần tự và blocking, riêng phần chờ có thể gần 300 ms. Ghép hai lời gọi non-blocking bằng `Mono.zip(...)` cho phép chúng hoạt động đồng thời, nên phần chờ có thể gần thời gian lời gọi chậm hơn (cộng overhead). Lợi ích này đến từ **chạy đồng thời các I/O độc lập**, không phải từ một cơ chế làm cho bản thân dịch vụ nhanh hơn. Cách bất đồng bộ khác cũng có thể đạt lợi ích tương tự.

## 2. Những tình huống reactive thường phù hợp

### 2.1. Nhiều request đồng thời nhưng phần lớn thời gian là chờ I/O

Một API gateway, backend-for-frontend hoặc dịch vụ tổng hợp dữ liệu thường nhận nhiều request và phải gọi nhiều HTTP service khác. Khi các upstream đã có client non-blocking (chẳng hạn `WebClient`), WebFlux có thể giữ số lượng luồng chờ thấp hơn ngay cả khi nhiều request còn đang trong trạng thái in-flight.

Reactive đáng thử khi có đủ **ba điều kiện**:

1. Tải đồng thời cao hoặc có đỉnh tải dài khiến mô hình blocking tiêu tốn nhiều luồng/tài nguyên.
2. Tỷ trọng thời gian chờ network/I/O lớn hơn phần xử lý CPU.
3. Đường xử lý quan trọng có HTTP client, driver và thành phần dữ liệu hỗ trợ bất đồng bộ thật sự.

Không có ngưỡng requests/second cố định khiến reactive tự động trở thành lựa chọn tốt. Cần đo giới hạn của hệ thống đang xây dựng.

### 2.2. Truyền dữ liệu dạng luồng, có thể dài hoặc liên tục

Server-Sent Events (SSE), dòng sự kiện thời gian thực, stream kết quả truy vấn hoặc các nguồn dữ liệu liên tục hợp với kiểu `Flux<T>`. Ứng dụng có thể xử lý từng phần dữ liệu khi xuất hiện thay vì phải gom toàn bộ kết quả vào bộ nhớ trước khi gửi.

Ví dụ một endpoint thông báo giá thay đổi liên tục: một `Flux<PriceEvent>` có thể đại diện cho nguồn sự kiện; client ngắt kết nối thì subscription cần được hủy và tài nguyên liên quan cần được giải phóng. Với SSE, phải xét cách xử lý client chậm, buffering, giới hạn kết nối và đặc tính của nguồn sự kiện. **Backpressure trong Reactor không đồng nghĩa rằng mọi HTTP client, message broker hoặc nguồn bên ngoài đều tuân thủ demand.**

### 2.3. Chuỗi tích hợp đã reactive từ đầu đến cuối

Một service dùng WebFlux + `WebClient` + reactive database client (ví dụ R2DBC khi phù hợp) + reactive messaging adapter có thể truyền trạng thái bất đồng bộ xuyên các tầng mà không phải liên tục đổi sang blocking.

Khi các tầng đã dùng `Mono`/`Flux`, việc kết hợp request phụ thuộc, timeout, retry có điều kiện, hủy tác vụ và giới hạn concurrency trở nên nhất quán hơn. Tuy vậy, **reactive ở controller không đủ**: nếu lõi nghiệp vụ vẫn gọi JDBC, JPA hoặc SDK blocking trên event-loop, lợi ích chính sẽ bị triệt tiêu và nguy cơ nghẽn tăng lên.

### 2.4. Cần điều phối nhiều I/O phụ thuộc hoặc độc lập

Reactor có những toán tử như `flatMap`, `concatMap`, `zip`, `timeout` và `onErrorResume` giúp biểu diễn cách ghép bất đồng bộ. Chẳng hạn một màn hình tổng hợp cần dữ liệu profile và tồn kho từ hai upstream; nếu độc lập, gọi song song rồi ghép; nếu B phụ thuộc A, dùng `flatMap` để chờ A trước.

Đây là lợi ích về **composition và kiểm soát luồng**, bên cạnh khả năng sử dụng tài nguyên. Phải đặt giới hạn cho số tác vụ đồng thời, kết nối và hàng đợi; nếu không, ứng dụng có thể tăng lượng công việc in-flight đến mức làm nghẽn upstream.

## 3. Khi nào reactive làm tăng độ phức tạp hơn giá trị nhận được?

### 3.1. CRUD vừa và nhỏ với thư viện blocking là chủ đạo

Nếu ứng dụng chủ yếu là request ngắn, logic tuần tự, truy vấn JPA/JDBC và lưu lượng đồng thời vừa phải, Spring MVC thường rõ ràng hơn: code tuyến tính, transaction quen thuộc, breakpoint và stack trace dễ theo dõi. Chuyển controller sang `Mono` trong khi repository vẫn gọi blocking không biến hệ thống thành non-blocking.

Các ứng dụng đơn giản cần ưu tiên khả năng bảo trì và tính đúng đắn thường có lợi hơn từ **Spring MVC + JDBC/JPA** so với viết toàn bộ pipeline Reactor chỉ vì xu hướng công nghệ.

### 3.2. Công việc nặng CPU

Mã hóa lớn, nén, xử lý ảnh, tính toán phức tạp hoặc thuật toán chạy CPU lâu không tự tăng tốc vì bọc trong `Mono`. Nếu đặt phép tính nặng ngay trên event-loop, một tác vụ có thể cản trở rất nhiều request khác. Cần thiết kế giới hạn song song, nơi thực thi phù hợp (pool chuyên dụng hoặc worker riêng), và đo CPU thực tế.

Reactive phát huy thế mạnh ở **I/O waiting**. Với CPU-bound, câu hỏi chính là năng lực CPU, phân bổ tác vụ và số core, không phải số publisher.

### 3.3. Driver, SDK và thao tác nghiệp vụ còn blocking

Những dấu hiệu đáng chú ý: `Thread.sleep(...)`, `Future.get()`, `Mono.block()`, gọi JDBC/JPA đồng bộ, đọc file bằng API blocking, SDK HTTP đồng bộ hoặc thao tác đồng bộ hóa kéo dài trên request path. Nếu chạy trên luồng event-loop, chúng có thể làm giảm thông lượng và khiến latency đuôi tăng mạnh.

Một giải pháp chuyển tiếp là bao thao tác blocking trong `Mono.fromCallable(...)` và chuyển sang `Schedulers.boundedElastic()`. Cách này giúp tránh chiếm dụng event-loop nhưng **thao tác bên trong vẫn blocking**, vẫn dùng luồng và bị giới hạn bởi số connection/worker. Không coi đây là bằng chứng rằng toàn hệ thống đã non-blocking.

### 3.4. Giao dịch dữ liệu và ngữ cảnh theo luồng phức tạp

Reactive transaction của R2DBC dùng ngữ cảnh reactive, khác với mô hình đồng bộ dựa nhiều vào `ThreadLocal`. Không thể mặc định một giao dịch JPA dùng `@Transactional` sẽ bao trùm các tác vụ reactive chạy qua nhiều scheduler. Việc phối hợp nhiều kho dữ liệu, kiểm soát tính nhất quán và hủy tác vụ phải được thiết kế rõ.

Các cơ chế security context, MDC/log correlation, tracing và dữ liệu request theo luồng cũng cần kiểm tra cách truyền ngữ cảnh qua Reactor Context. Suy luận rằng mỗi request luôn gắn với một thread cố định có thể gây lỗi khó tìm.

### 3.5. Chi phí nhận thức, kiểm thử và vận hành

Code kiểu `map`/`flatMap` và quy tắc subscription, cold/hot publisher, xử lý lỗi, timeout, retry, cancellation, backpressure, scheduler đòi hỏi cả nhóm hiểu chung. Stack trace qua pipeline có thể kém trực quan; nếu không có metrics/tracing, lỗi xảy ra dưới tải thường khó chẩn đoán.

Các lỗi thiết kế hay gặp gồm: tự gọi `subscribe()` khiến framework không còn kiểm soát vòng đời tác vụ; quên `return` publisher khiến chuỗi không chạy; retry vô hạn gây bão tải; `flatMap` mở quá nhiều tác vụ; tự `block()` trong controller; xử lý lỗi thành giá trị mặc định khiến thất bại bị che giấu; tạo publisher nhưng không quản lý resource khi bị hủy.

### 3.6. Đã có lựa chọn đơn giản hơn đáp ứng yêu cầu

Với Java 21+, **virtual threads** là phương án cần đánh giá cho hệ thống imperative có nhiều lời gọi blocking: code vẫn tuyến tính nhưng chi phí chờ của luồng có thể thấp hơn platform thread. Virtual threads không làm JDBC non-blocking, không tăng năng lực connection pool và không tự xử lý backpressure; cần kiểm tra compatibility, đồng bộ hóa, giới hạn tài nguyên và workload. Với Java 17 hoặc các hệ thống đang vận hành MVC ổn định, tối ưu query, pool, cache và timeout cũng có thể đem lại kết quả tốt mà không cần đổi mô hình.

**Đừng dùng reactive để giải quyết một nút thắt chưa được xác định.** Nếu bottleneck là SQL chậm, lock tranh chấp, CPU đạt trần hoặc upstream giới hạn số kết nối, đổi kiểu controller không giải quyết nguyên nhân.

## 4. Bảng đối chiếu để chọn kiến trúc

| Bối cảnh thực tế | Hướng thường hợp lý | Lý do / điều kiện |
| --- | --- | --- |
| API CRUD, JPA/JDBC, traffic vừa, nhóm quen imperative | Spring MVC | Ít chuyển đổi, transaction và debug đơn giản |
| Hệ thống imperative có nhiều I/O blocking, dùng Java 21+ | Đo Spring MVC với virtual threads bên cạnh baseline | Giữ code tuyến tính; vẫn cần quản lý DB pool và tải |
| Gateway/BFF ghép nhiều API, concurrency cao, upstream non-blocking | Thử WebFlux + WebClient | Khả năng điều phối I/O không chặn và giảm luồng chờ |
| SSE hoặc stream dữ liệu dài, cần hủy/kiểm soát nguồn phát | WebFlux + Flux đáng cân nhắc | Mô hình publisher thích hợp cho streaming |
| WebFlux controller nhưng mọi repository đều JPA/JDBC blocking | Cân nhắc giữ MVC hoặc cô lập blocking có kiểm soát | Reactive bề mặt không loại bỏ luồng blocking |
| Xử lý ảnh/mã hóa/tính toán CPU dài | Tối ưu CPU, worker pool hoặc xử lý ngoài request path | Reactive không làm phép tính CPU nhanh hơn |
| Các service có thể đáp ứng SLA bằng stack đang dùng | Giữ stack, cải tiến điểm nghẽn đã đo | Tránh thêm chi phí migration và đào tạo |

Bảng là **gợi ý ra quyết định**, không phải quy tắc áp dụng cho mọi hệ thống. Spring MVC cũng hỗ trợ những dạng xử lý async nhất định; WebFlux chỉ là một cách tổ chức toàn bộ request pipeline. Hai stack có thể cùng tồn tại ở các service khác nhau trong cùng hệ thống.

## 5. Ví dụ: tổng hợp hai upstream trong Spring WebFlux

Giả sử endpoint `GET /overview/{id}` cần lấy sản phẩm từ catalog service và tồn kho từ warehouse service. Hai request độc lập; chúng không cần chờ tuần tự. Đoạn mã sau là **một controller hoàn chỉnh bên trong dự án Spring Boot đã có dependency `spring-boot-starter-webflux`**, dùng Java 17+, không phải một chương trình Java chạy độc lập. Cần có hai upstream tại `localhost:8081` và `localhost:8082` trả JSON theo các record được khai báo.

Tệp `src/main/java/demo/OverviewController.java`:

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class OverviewController {
    private final WebClient catalogClient;
    private final WebClient warehouseClient;

    public OverviewController(WebClient.Builder builder) {
        this.catalogClient = builder.clone()
                .baseUrl("http://localhost:8081")
                .build();
        this.warehouseClient = builder.clone()
                .baseUrl("http://localhost:8082")
                .build();
    }

    @GetMapping("/overview/{id}")
    public Mono<Overview> getOverview(@PathVariable String id) {
        Mono<Item> item = catalogClient.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class);

        Mono<Stock> stock = warehouseClient.get()
                .uri("/stocks/{id}", id)
                .retrieve()
                .bodyToMono(Stock.class);

        return Mono.zip(item, stock)
                .map(tuple -> new Overview(tuple.getT1(), tuple.getT2()))
                .timeout(Duration.ofSeconds(2))
                .onErrorMap(TimeoutException.class, error ->
                        new ResponseStatusException(
                                HttpStatus.GATEWAY_TIMEOUT,
                                "Upstream timeout",
                                error));
    }

    public record Item(String id, String name) {}
    public record Stock(String id, int available) {}
    public record Overview(Item item, Stock stock) {}
}
```

**Cách chạy trong một dự án có sẵn:** đặt class vào package được Spring Boot scan, bổ sung `spring-boot-starter-webflux` theo dependency management của dự án, chạy ứng dụng bằng `./gradlew bootRun` (hoặc `mvn spring-boot:run` nếu dự án dùng Maven), khởi chạy hai service giả lập đúng endpoint rồi gọi `curl http://localhost:8080/overview/sku-1`. Response JSON phụ thuộc dữ liệu upstream; không có stdout cố định. Nếu upstream chưa chạy, request sẽ lỗi kết nối — đây là môi trường thiếu giả lập, không phải hành vi thành công của ví dụ.

Giải thích từng điểm:

1. `WebClient` trả `Mono`, không chặn thread đang dựng pipeline khi chờ HTTP response. Cần dùng cấu hình HTTP connector/connection pool phù hợp trong hệ thống thực.
2. `Mono.zip(item, stock)` đăng ký hai nguồn độc lập khi có subscription và kết hợp hai kết quả. Độ trễ có thể gần với upstream chậm hơn, nếu cả hai đủ tài nguyên và không bị xếp hàng.
3. `timeout(2s)` áp dụng cho pipeline ghép, chấm dứt chờ kéo dài; `onErrorMap` biến riêng timeout thành HTTP 504. Với lỗi HTTP từ upstream, connection failure, response rỗng hoặc retry, sản phẩm thực tế phải xác định và triển khai chính sách lỗi riêng.
4. Không có `block()` hay `subscribe()` trong controller. WebFlux quản lý subscription, trả response và xử lý hủy khi request kết thúc.
5. Một nguồn hoàn thành **không phát giá trị** có thể khiến `zip` hoàn thành không có `Overview`; nếu nghiệp vụ yêu cầu báo 404 hoặc fallback, phải quy định rõ. Nếu một nguồn lỗi, `zip` sẽ lỗi thay vì trả dữ liệu thiếu trừ khi ta thiết kế cách phục hồi cụ thể.

Ví dụ minh họa **composition và non-blocking HTTP**. Không chứng minh rằng WebFlux luôn nhanh hơn MVC; một ứng dụng MVC dùng async fan-out hoặc virtual threads cũng phải được so sánh bằng benchmark cùng điều kiện.

### 5.1. Tránh chặn event-loop vì mã legacy

Đây là **đoạn minh họa trong service**, giả sử `legacyClient.fetch(id)` là phương thức **blocking** có sẵn; không phải class độc lập có thể biên dịch nếu chưa định nghĩa client:

```java
// Sai trên luồng event-loop: lời gọi blocking chạy ngay khi dựng Mono.
Mono<Item> wrong = Mono.just(legacyClient.fetch(id));

// Chuyển tiếp có kiểm soát: việc blocking chạy trên boundedElastic.
Mono<Item> bridge = Mono.fromCallable(() -> legacyClient.fetch(id))
        .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
```

`Mono.just(legacyClient.fetch(id))` đánh giá `fetch` trước khi tạo publisher nên vẫn blocking tại điểm gọi. `fromCallable` trì hoãn lời gọi đến lúc subscribe; `subscribeOn(boundedElastic())` bố trí chạy trên scheduler dành cho việc blocking hữu hạn. Tuy nhiên nếu có hàng nghìn lời gọi JDBC/SDK blocking, chúng vẫn cạnh tranh luồng, hàng chờ và connection pool. Cần đặt timeout, concurrency limit và cân nhắc giữ endpoint imperative nếu phần blocking là chủ đạo.

Trong pipeline WebFlux, **không gọi `.block()` để lấy giá trị rồi xử lý đồng bộ**. Chỉ dùng `block()` tại một ranh giới imperative được chủ động thiết kế, chẳng hạn một công cụ dòng lệnh hoặc mã test, sau khi hiểu rủi ro chờ.

## 6. Các phép thử nên làm trước khi quyết định đổi kiến trúc

Không lựa chọn reactive chỉ bằng số thread hoặc một benchmark chạy localhost không mô phỏng hệ thống. Thực hiện thử nghiệm nhỏ trên **một use case I/O-heavy** với cùng dữ liệu, downstream, mức tải và phần cứng:

1. **Ghi baseline:** lưu request/second đạt được ở cùng mức lỗi chấp nhận; p50/p95/p99 latency, CPU, RSS/heap, GC, số thread, active connection, thời gian queue, timeout và tỷ lệ lỗi.
2. **Xác định nút thắt:** request đang chờ upstream hay DB? Pool hết connection? SQL chậm? CPU trần? Event-loop bị block? Quan sát p99 và thời gian chờ pool, không suy luận từ throughput tổng.
3. **Xây prototype đúng công nghệ:** với WebFlux, dùng `WebClient`/driver reactive trên đường nóng; giữ cơ chế timeout, retry hữu hạn, giới hạn kết nối và concurrency, quan sát cancellation. Nếu vẫn blocking, ghi rõ phần còn lại và pool cô lập.
4. **Chạy nhiều mức concurrency:** từ tải thông thường đến tải đỉnh và vượt đỉnh; giữ cùng workload, cùng tỷ lệ payload và cùng giới hạn upstream. Quan sát throughput **kèm lỗi và độ trễ đuôi**, vì tăng throughput bằng cách chất hàng đợi không đồng nghĩa hệ thống tốt hơn.
5. **Tính chi phí duy trì:** thay đổi repository/transaction, unit/integration tests, tracing, logging context, kiến thức nhóm và quy trình debug. Nếu gain nhỏ hoặc lỗi vận hành khó kiểm soát, MVC có thể là lựa chọn đúng.

Các chỉ số giúp phát hiện ưu/nhược:

| Tín hiệu đo được | Cách hiểu thận trọng |
| --- | --- |
| Thread count giảm nhưng p99, lỗi không tốt hơn | Chưa chứng minh lợi ích ở mức người dùng |
| p99 tăng khi active connection chạm giới hạn | Có thể nghẽn pool/upstream; đổi programming model không giải quyết |
| Event-loop có đoạn blocking dài | Có khả năng SDK/JDBC/CPU work chạy sai thread |
| Heap và queue tăng liên tục khi client chậm | Cần xem buffering, demand, giới hạn bộ nhớ và cách hủy |
| WebFlux giảm RAM/threads và giữ latency/error tốt hơn ở tải cao | Tín hiệu phù hợp, cần đo lặp lại và xét chi phí bảo trì |
| Virtual threads đạt SLA với code đơn giản hơn | Có lý do mạnh để giữ mô hình imperative nếu các ràng buộc khác cho phép |

**Lưu ý về backpressure:** Reactor có demand giữa producer và subscriber tuân thủ Reactive Streams; nhưng một callback nguồn nóng, hệ thống message broker hoặc thư viện bên ngoài có thể không dừng phát vì subscriber chậm. Lúc đó phải có chiến lược buffer giới hạn, drop, reject, pause consumption hoặc scale phù hợp với nghiệp vụ, và xác định rủi ro mất dữ liệu/đúng thứ tự.

## 7. Những lỗi suy luận phổ biến cần tránh

- **“Reactive = request nào cũng nhanh hơn.”** Sai: giảm thời gian chờ chiếm luồng và hỗ trợ fan-out, không rút ngắn trực tiếp thời gian CPU, SQL hoặc mạng.
- **“Dùng `Mono` là đã non-blocking.”** Sai: nội dung trong `Mono` vẫn có thể gọi blocking; `Mono.just(blockingCall())` còn chạy blocking ngay khi tạo.
- **“Một event-loop xử lý vô hạn kết nối.”** Sai: OS, memory, connection pool, throughput upstream, buffering và CPU đều có giới hạn.
- **“Có backpressure nên không bao giờ quá tải.”** Sai: cơ chế demand chỉ hữu ích ở nơi các thành phần thực sự tuân thủ và chuyển tiếp tín hiệu.
- **“Có thể bỏ transaction và log context như cũ.”** Sai: reactive request có thể di chuyển qua nhiều luồng; transaction/context cần thiết kế tương ứng.
- **“Gọi `subscribe()` trong service cho chạy nhanh hơn.”** Thường sai trong request flow: dễ đánh mất vòng đời xử lý, propagation lỗi, cancellation và kết quả trả về; hãy trả publisher cho framework.
- **“Retry mọi lỗi là an toàn.”** Sai: retry có thể nhân tải khi upstream yếu; chỉ retry lỗi tạm thời, có giới hạn, backoff và xét idempotency.
- **“Chuyển hết sang WebFlux rồi mới kiểm tra lợi ích.”** Rủi ro cao: thay đổi đồng thời concurrency, persistence, transaction, test và vận hành. Tốt hơn là thử nghiệm một lát cắt đại diện trước.

## 8. Kết luận: quyết định dựa trên đường I/O và bằng chứng đo

Reactive thích hợp nhất khi ứng dụng có **nhiều tác vụ I/O đồng thời, nhu cầu streaming hoặc composition bất đồng bộ, và có thể duy trì non-blocking dọc đường xử lý quan trọng**. Nó cho phép sử dụng luồng hiệu quả hơn dưới một số kiểu tải, nhưng phải gắn với giới hạn concurrency, backpressure thực tế, timeout, xử lý lỗi và quan sát hệ thống.

Reactive thường **làm tăng độ phức tạp không cần thiết** khi ứng dụng CRUD nhỏ, phần lớn mã phụ thuộc JPA/JDBC blocking, CPU là nút thắt, hoặc nhóm không cần các đặc tính streaming/concurrency này. Spring MVC, tối ưu tài nguyên và — khi thích hợp — virtual threads có thể đáp ứng bài toán với mô hình đơn giản hơn.

**Câu hỏi chốt trước khi chọn WebFlux:** “Chúng ta đã chứng minh rằng chờ I/O ở mức đồng thời cao là vấn đề chính, các thành phần then chốt đều hỗ trợ non-blocking, và benchmark cho thấy lợi ích đủ lớn để trả chi phí phát triển, kiểm thử, vận hành chưa?” Nếu chưa, hãy đo và thử nghiệm thay vì đổi kiến trúc theo cảm tính.
