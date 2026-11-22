# Backpressure và điều kiện áp dụng ở các ranh giới HTTP

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Thực thi reactive

## 1. Mục tiêu bài học và vấn đề cần giải quyết

Một hệ thống HTTP reactive thường đi qua nhiều tầng: client, proxy, network socket, HTTP codec, handler, service, database hoặc dịch vụ khác. Khi một phía tạo dữ liệu nhanh hơn phía tiếp nhận xử lý, hàng đợi có thể tăng, bộ nhớ bị chiếm và độ trễ xấu đi. **Backpressure** là cơ chế để bên nhận thể hiện khả năng tiêu thụ với bên phát và hạn chế lượng dữ liệu đang bay trong hệ thống.

Sau bài này, bạn cần:

1. Hiểu **demand** trong Reactive Streams và cách **Flux/Mono** truyền tín hiệu **request(n)** ngược chiều dữ liệu.
2. Chỉ ra những **ranh giới HTTP** mà demand có thể ảnh hưởng đến tốc độ đọc/ghi, và nơi nó **không** còn là tín hiệu Reactive Streams.
3. Phân biệt **backpressure theo phần tử**, **TCP flow control theo byte**, **HTTP/2 flow control**, **buffering** và **rate limiting**.
4. Áp dụng với Spring WebFlux/Reactor Netty, WebClient, streaming request/response và các nguồn dữ liệu phù hợp.
5. Nhận biết điểm phá vỡ cơ chế: chuyển sang blocking API, gom hết dữ liệu, producer không nghe demand, proxy đệm, queue không giới hạn hoặc consumer không stream.

**Luận điểm chính:** Trả về **Flux** hoặc bật Spring WebFlux chỉ tạo điều kiện để xử lý theo demand. Nó **không tự bảo đảm backpressure đầu-cuối từ trình duyệt đến database**. Cần xem từng đoạn kết nối thực tế.

## 2. Cơ chế Reactive Streams: dữ liệu đi xuôi, demand đi ngược

Reactive Streams định nghĩa bốn vai trò cốt lõi:

- **Publisher<T>**: nguồn công bố các phần tử T.
- **Subscriber<T>**: phía nhận, tiêu thụ các phần tử.
- **Subscription**: quan hệ đăng ký, cung cấp **request(long n)** và **cancel()**.
- **Processor<T,R>**: vừa nhận vừa phát (khái niệm giao thức; trong Reactor, các operator thường thực hiện vai trò trung gian tương ứng).

Một chuỗi cơ bản:

~~~text
DỮ LIỆU:        nguồn ---- onNext(T) ----> operator ----> consumer
DEMAND:         nguồn <--- request(n) ---- operator <---- consumer
HUỶ:           nguồn <--- cancel() ------ operator <---- consumer
~~~

Trình tự điển hình: bên nhận **subscribe**, nhận **onSubscribe(subscription)**, yêu cầu **request(3)**, rồi upstream được phép gửi **tối đa ba phần tử onNext** ứng với phần demand đó. Sau khi tiêu thụ, bên nhận có thể yêu cầu thêm hoặc huỷ đăng ký. Publisher phát **onComplete** nếu hết dữ liệu, hoặc **onError** nếu lỗi; terminal signal không phải là một phần tử dữ liệu tính vào request(n).

Các điều kiện quan trọng:

- **n phải dương** khi gọi request(n); giá trị 0 hoặc âm vi phạm hợp đồng Reactive Streams và dẫn tới tín hiệu lỗi.
- Demand được tích luỹ theo số lượng phần tử đang được phép nhận, không phải số byte hay số mili giây. **request(10)** không có nghĩa "10 KB" hoặc "10 request HTTP/giây".
- **Long.MAX_VALUE** biểu thị yêu cầu không giới hạn. Những cách subscribe tiện dụng như **subscribe()** thường đưa ra unbounded demand; khi đó không thể suy ra consumer đang hạn chế tốc độ phát theo từng phần tử.
- Một số operator **đổi hình dạng demand**: **buffer(10)** nhận demand 2 buffer có thể yêu cầu 20 phần tử ở phía trước; **flatMap**, **publishOn** có prefetch; **limitRate** chia yêu cầu lớn thành các đợt nhỏ.
- **cancel()** ngừng sự quan tâm của subscriber tới nguồn, nhưng không thể "thu hồi" dữ liệu đã gửi trên mạng, đã ghi vào queue, đã được xử lý hoặc đã cam kết ở hệ thống khác.

**Backpressure khác tốc độ:** demand là quyền phát một số phần tử. Nếu subscriber yêu cầu 1.000 phần tử rồi xử lý rất chậm, source vẫn có thể đã gửi nhiều phần tử vào các buffer hợp lệ. Muốn có tải ổn định, còn cần giới hạn concurrency, bộ nhớ, timeout và năng lực downstream.

## 3. Ba lớp điều tiết dễ bị nhầm lẫn

| Lớp | Đơn vị | Cơ chế điển hình | Điều lớp đó bảo đảm / không bảo đảm |
| --- | --- | --- | --- |
| **Reactive Streams** | Số phần tử T | Subscription.request(n), cancel() | Điều tiết onNext giữa các Publisher/Subscriber tuân thủ hợp đồng; không gửi request(n) nguyên trạng qua HTTP. |
| **Transport TCP** | Byte và cửa sổ nhận/gửi | Receive window, send buffer, socket writable | Hạn chế lượng byte có thể truyền khi peer không đọc kịp; không hiểu JSON object, business event hoặc số phần tử Flux. |
| **HTTP/2** | Byte trong DATA frame ở connection/stream | WINDOW_UPDATE, flow-control window | Điều tiết body DATA theo byte giữa hai HTTP/2 peer; không thay thế Reactive Streams hay hạn mức application. |

**HTTP/1.1** không có cơ chế flow control từng stream như HTTP/2; có thể stream body qua **Transfer-Encoding: chunked** hoặc các cách đóng khung khác, nhưng khả năng truyền vẫn chịu ảnh hưởng TCP. **HTTP/2** multiplex nhiều stream trên một connection và có flow control cho DATA frame. Cả hai có thể hỗ trợ một pipeline WebFlux reactive nếu stack HTTP và nguồn/đích thích hợp.

**TLS/HTTPS** mã hoá đường truyền; TLS không chuyển request(n) thành một tín hiệu kiểm soát tốc độ mới ở tầng ứng dụng. **Rate limiting** (ví dụ tối đa 100 request/giây) khống chế lưu lượng theo thời gian, thường ở API Gateway; không tương đương backpressure cho một body streaming đang mở.

## 4. Nhận diện chính xác ranh giới HTTP

Xét hai tuyến phổ biến.

**A. Server gửi response dạng stream:**

~~~text
Database/reactive source
          |
          v   Flux<Item>
Business operators / WebFlux HTTP encoder
          |
          v   Byte buffers / HTTP DATA hoặc chunked body
HTTP server connector (ví dụ Reactor Netty)
          |
          v   Socket, TCP, TLS
Load balancer / reverse proxy (có thể buffer hoặc đổi giao thức)
          |
          v
Client HTTP decoder -> trình duyệt/app sử dụng dữ liệu

request(n) có thể truyền ngược trong pipeline reactive của mỗi tiến trình;
socket writability, TCP window và HTTP/2 window điều tiết tại ranh giới mạng.
Không tồn tại một Subscription.request(n) chung xuyên suốt các host.
~~~

**B. Server nhận request body dạng stream:**

~~~text
Client gửi request body
          |
          v
Socket / HTTP server / decoder
          |
          v   Flux<DataBuffer> hoặc Flux<Item>
Controller -> service -> storage/processor
          |
          v
Subscriber hoàn thành công việc
~~~

Khi application xử lý body từng phần và upstream connector hỗ trợ liên kết demand với việc đọc từ socket, backpressure có thể góp phần giảm đọc/giải mã tiếp. Nhưng client và các proxy vẫn có thể đã gửi hoặc đệm dữ liệu từ trước. Không thể lấy số lần gọi **request(n)** ở server rồi kết luận tương ứng một-một với số packet TCP hay số dòng JSON client vừa gửi.

**Một HTTP boundary thật sự chỉ được xem là có khả năng điều tiết hữu ích khi đồng thời thỏa các điều kiện:**

1. Phần dữ liệu có thể **được phát/nhận từng phần**, thay vì phải gom toàn bộ payload mới giải mã hoặc xử lý.
2. Connector và codec có cơ chế **nối demand với non-blocking I/O/read-write readiness**, hoặc ít nhất áp dụng queue được giới hạn, không lén tăng bộ nhớ vô hạn.
3. Publisher **tôn trọng demand**, hoặc khi source không thể chậm lại có **chính sách overflow rõ ràng** (buffer giới hạn, drop, latest hoặc error/cancel).
4. Các operator và downstream không tự phá vỡ tính từng phần bằng **collectList**, **block**, queue không giới hạn, prefetch/concurrency quá cao hoặc adapter blocking.
5. Bên ngoài tiến trình, **proxy/client** phải được kiểm tra về buffering và cách tiêu thụ; một đường HTTP có thể tách thành nhiều connection với chính sách khác nhau.

Điều kiện trên là khung đánh giá năng lực. Mỗi thư viện/adapter có chi tiết riêng; không suy từ tên "reactive" ra bảo đảm vô hạn về bộ nhớ hay an toàn quá tải.

## 5. Spring WebFlux và Reactor Netty kết nối demand với HTTP ra sao?

Trong Spring WebFlux, controller có thể trả về **Flux<T>**, **Mono<T>**, hoặc nhận **Flux<T>** từ request body. Spring có phần **HttpHandler** và adapter HTTP non-blocking. Với **spring-boot-starter-webflux**, cấu hình Spring Boot mặc định thông dụng là Reactor Netty; WebFlux cũng có adapter cho các container phù hợp khác.

Ở response, Spring dùng **HttpMessageWriter/Encoder** chuyển phần tử logic thành byte buffer. Server connector chuyển các byte đó tới socket. Demand từ downstream có thể hạn chế lượng dữ liệu mà publisher cần tạo; khi transport chậm, tầng ghi có thể điều chỉnh tốc độ tiêu thụ tùy connector, kích thước buffer và khả năng ghi.

Ở request, **HttpMessageReader/Decoder** biến luồng byte thành phần tử của **Flux<T>**. Với **application/x-ndjson**, nhiều JSON object trên các dòng riêng có thể được giải mã như các phần tử. Với một JSON array/body gom toàn bộ thành một object, ứng dụng có thể phải tiêu thụ/đệm lượng lớn trước khi có phần tử kết quả; cần phân biệt **streaming framing** với một request body được aggregate.

**Điểm cần nhớ:** Spring Framework cung cấp mô hình có backpressure, nhưng không có phép đo cố định kiểu **1 request(n) = 1 TCP read = 1 lần ghi socket**. Chunk network có thể chứa nhiều object hoặc một object trải trên nhiều chunk; TLS, codec, flush policy và Netty buffer còn thay đổi ranh giới byte.

### Phía server gửi dữ liệu

- **Flux<Item> với NDJSON**: phù hợp với danh sách sự kiện/vật thể có thể đọc dần; client cần parse theo từng dòng và không dùng API gom toàn bộ.
- **Flux<ServerSentEvent<T>> với text/event-stream (SSE)**: phù hợp với feed thông báo server-to-client; cơ chế nhận chậm, proxy buffering, mất kết nối và heartbeat vẫn cần kiểm soát. Browser EventSource không có API request(n) như Reactive Streams.
- **Flux<DataBuffer>**: phù hợp cho luồng byte/file lớn khi cần kiểm soát sát IO, nhưng đòi hỏi quản lý vòng đời buffer nếu xử lý trực tiếp.
- **Mono<T>**: một giá trị/response đơn; có thể vẫn là non-blocking, nhưng không phải ví dụ nhiều phần tử để quan sát demand theo chuỗi.

### Phía server nhận dữ liệu

- **@RequestBody Flux<Item>**: xử lý body theo nhiều record nếu codec/content type hỗ trợ. Không gọi collectList() trừ khi yêu cầu nghiệp vụ bắt buộc có đủ mọi record.
- **Flux<DataBuffer>**: xử lý upload từng buffer, ghi dần vào storage nếu storage hỗ trợ; chú ý giới hạn body, lỗi giải mã, cancellation và giải phóng buffer nếu tự thao tác.
- Với body phải đọc trọn trước khi xử lý (ví dụ chữ ký trên toàn dữ liệu, JSON object lớn), có thể không duy trì được streaming theo record. Dùng giới hạn kích thước và bộ nhớ thay vì giả định đã có backpressure hiệu quả.

## 6. Demo Spring Boot 3.x, Java 17+: một stream response và một stream request

**Điều kiện:** Tạo project Spring Boot 3.x với Java 17+ và dependency **org.springframework.boot:spring-boot-starter-webflux** (cùng Jackson do starter cung cấp). Dùng riêng WebFlux starter cho demo Reactor Netty; nếu thêm cả **spring-boot-starter-web** thì Spring Boot thường ưu tiên ứng dụng Servlet/MVC, làm thay đổi stack thực tế.

Tạo tệp **src/main/java/com/example/boundary/BoundaryDemoApplication.java**:

~~~java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class BoundaryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundaryDemoApplication.class, args);
    }

    @GetMapping(value = "/feed", produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Event> feed() {
        return Flux.range(1, 100)
                .map(i -> new Event(i, "event-" + i))
                .doOnRequest(n ->
                        System.out.println("source requested " + n))
                .limitRate(8);
    }

    @PostMapping(
            value = "/ingest",
            consumes = MediaType.APPLICATION_NDJSON_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ingest(@RequestBody Flux<Event> input) {
        return input.limitRate(8)
                .count()
                .map(count -> "received=" + count);
    }

    public record Event(int id, String label) {}
}
~~~

**Tại sao đoạn code này có ý nghĩa?**

- **Flux.range(1, 100)** là nguồn hữu hạn, tuân thủ Reactive Streams, giúp quan sát yêu cầu upstream trong môi trường ổn định; **Event** là Java record, Jackson có thể serialize/deserialize.
- **application/x-ndjson** cho phép biểu diễn từng JSON object trên một dòng, thuận lợi cho response stream và request stream. Đây là một **chuỗi object**, không phải một JSON array bao trọn nội dung.
- **limitRate(8)** chia demand truyền ngược về nguồn thành các batch nhỏ hơn, có chiến lược cấp bổ sung khi sắp tiêu thụ hết batch. Nó **không** có nghĩa 8 item/giây hay hard-cap 8 item nằm trong tất cả các buffer hệ thống.
- **doOnRequest** đặt **trước** limitRate nên quan sát demand mà operator gửi về source. Log đó thể hiện hành vi operator, **không phải packet TCP hay cửa sổ HTTP/2**.
- **count()** trong endpoint ingest đếm phần tử rồi mới trả kết quả. Đây là phép tổng hợp ra một con số, thường không cần giữ toàn bộ Event; tuy nhiên response vẫn chỉ xuất hiện khi body đầu vào hoàn tất.

Chạy ứng dụng từ project đã có Gradle wrapper và plugin Spring Boot phù hợp:

~~~bash
./gradlew bootRun
~~~

Thử tải response stream:

~~~bash
curl -sS -N -H "Accept: application/x-ndjson" http://localhost:8080/feed
~~~

Đầu ra **đầu tiên** về mặt nội dung JSON sẽ tương ứng:

~~~json
{"id":1,"label":"event-1"}
{"id":2,"label":"event-2"}
{"id":3,"label":"event-3"}
~~~

Sau đó còn các record tới id 100; thời điểm flush và cách log demand thay đổi theo server/transport. **-N** yêu cầu curl không tự đệm nội dung xuất ra terminal; nó **không** bắt server phải phát mỗi record thành một packet hoặc chứng minh rằng TCP chậm đã gây backpressure.

Thử gửi hai record vào request body:

~~~bash
printf '{"id":1,"label":"a"}\n{"id":2,"label":"b"}\n' |
  curl -sS -H "Content-Type: application/x-ndjson" \
       --data-binary @- http://localhost:8080/ingest
~~~

Output kỳ vọng của response:

~~~text
received=2
~~~

Dấu **@-** khiến curl lấy body từ standard input. Nếu đang dùng PowerShell trên Windows, thay **printf/pipe** bằng một tệp UTF-8 chứa hai dòng NDJSON rồi dùng **--data-binary @items.ndjson**; ứng dụng Java và HTTP contract không đổi.

**Giới hạn của demo:** Flux.range phát quá nhanh để mô phỏng một consumer chậm thực sự. Nó chứng minh rằng demand có thể được điều chỉnh trong Reactor, và các endpoint có thể encode/decode body dạng stream. Muốn chứng minh backpressure truyền tới transport, cần đo thêm kích thước queue, buffer, mức sử dụng bộ nhớ, socket writes, client đọc chậm và cấu hình proxy bằng một tải thử kiểm soát được.

## 7. Kiểm tra demand theo phần tử bằng reactor-test

Để kiểm tra chính xác hợp đồng Publisher, thêm dependency kiểm thử cùng phiên bản quản lý bởi Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Đây là đoạn **dependencies** cho Gradle Groovy DSL của project đã có plugins/repositories phù hợp, không phải toàn bộ tệp build.gradle.

Tạo **src/test/java/com/example/boundary/DemandTest.java**:

~~~java
package com.example.boundary;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DemandTest {

    @Test
    void honorsRequestedElementCount() {
        StepVerifier.create(Flux.range(1, 5), 0)
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests com.example.boundary.DemandTest
~~~

Bài test khởi đầu demand bằng **0**, yêu cầu 2 phần tử, xác nhận 1 và 2, sau đó mới yêu cầu ba phần tử còn lại. Test PASS nghĩa là **Publisher trong bài test** đáp ứng contract demand. Test này **không** chứng minh HTTP connector, proxy, browser hoặc database giữ một demand chung; muốn xác minh tuyến end-to-end cần đo thực tế từng ranh giới.

## 8. WebClient và ranh giới HTTP phía client

WebClient của Spring WebFlux cũng hỗ trợ xử lý non-blocking với Reactive Streams. Một đoạn bên nhận dữ liệu:

~~~java
WebClient client = WebClient.create("http://localhost:8080");

Flux<BoundaryDemoApplication.Event> events = client.get()
        .uri("/feed")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(BoundaryDemoApplication.Event.class);
~~~

Đoạn trên là **mảnh code minh họa**, cần import **org.springframework.web.reactive.function.client.WebClient** và **org.springframework.http.MediaType**, đặt trong class/method của ứng dụng WebFlux; nó không phải một chương trình Java độc lập. **bodyToFlux** cho phép downstream tiêu thụ từng item và tạo demand trong pipeline WebClient. Trái lại, **bodyToMono(List<...>)**, **collectList()** hoặc xử lý toàn bộ response trước khi dùng sẽ chủ động gom phần tử.

Một ứng dụng Spring WebFlux đóng vai trò **A gọi B** có thể giữ pipeline có demand tương đối tốt khi A không chặn event loop, B stream kết quả và cả hai sử dụng nguồn/đích tôn trọng demand. Nhưng trên network, A và B vẫn giao tiếp qua HTTP/TCP buffers, không truyền đối tượng Subscription của JVM này sang JVM kia. Nếu có API Gateway hoặc cache ở giữa, phải kiểm tra riêng khả năng streaming/buffering của nó.

Lưu ý **subscribe()** và **blockLast()** từ code bên ngoài có thể đòi lượng dữ liệu rất lớn; trong Spring WebFlux handler, đừng gọi **block()** để đợi WebClient, JDBC hoặc future trên event-loop. Hãy trả lại **Mono/Flux** để framework quản lý chuỗi bất đồng bộ, hoặc bố trí boundary rõ ràng cho tác vụ blocking.

## 9. Những operator dễ làm sai năng lực backpressure

| Thành phần | Tác dụng thực tế | Rủi ro / cách dùng |
| --- | --- | --- |
| **limitRate(32)** | Chia demand upstream thành các batch và bổ sung theo ngưỡng. | Không phải giới hạn thời gian hay toàn bộ memory; chỉ tác động tại vị trí đặt operator. |
| **flatMap(mapper, concurrency, prefetch)** | Chạy nhiều nguồn con đồng thời; concurrency/prefetch đặt giới hạn thiết kế. | Concurrency/prefetch quá lớn làm số công việc và buffer tăng; thiết lập theo tài nguyên thật. |
| **publishOn(scheduler, prefetch)** | Chuyển việc xử lý tín hiệu xuống scheduler với queue/prefetch. | Có queue tại ranh giới scheduler; demand downstream không bằng demand upstream tại mọi thời điểm. |
| **buffer(n), window(n)** | Gom hoặc chia dữ liệu thành nhóm logic. | Demand của các nhóm khác với phần tử gốc, có thể cần n phần tử cho một buffer. |
| **collectList(), sort()** | Cần đủ phần tử mới phát kết quả cuối hoặc thực hiện xử lý đầy đủ. | Có thể giữ gần như toàn bộ input trong bộ nhớ, mất lợi thế streaming của output. |
| **onBackpressureBuffer(...)** | Cấp một vùng đệm khi producer nhanh hơn consumer. | Bản không giới hạn có thể phình bộ nhớ; dùng bounded buffer và chính sách overflow rõ ràng nếu bắt buộc. |
| **onBackpressureDrop / onBackpressureLatest** | Chọn bỏ bớt phần tử khi không đủ demand. | Chỉ phù hợp dữ liệu có thể bỏ/mới nhất đủ dùng (ví dụ telemetry tức thời), không phù hợp giao dịch cần đủ mọi sự kiện. |
| **retry / repeat / cache / replay** | Phát lại hoặc lưu kết quả. | Có thể tăng lượng request/source work hoặc giữ dữ liệu; phải đặt giới hạn và xem idempotency. |
| **subscribe() trong service** | Khởi chạy một subscription độc lập. | Làm đứt chuỗi caller quản lý cancellation, lỗi và demand; thông thường return Publisher thay vì tự subscribe. |

Chú ý đặc biệt với **Flux.create**, callback API, nguồn push từ message broker hoặc client SDK bên thứ ba: không phải mọi nguồn tự nhiên đều có cơ chế pause. Nếu producer không thể dừng, bạn phải quyết định **giới hạn queue, từ chối/cancel, ghi bền vững, hoặc bỏ dữ liệu có chủ đích**. Chỉ thêm một operator reactive quanh nguồn push không biến nguồn đó thành pull-based thực sự.

## 10. Điều kiện áp dụng theo từng kiểu ranh giới

### 10.1 HTTP/1.1 và HTTP/2

**HTTP/1.1:** response có thể stream qua body chunked, TCP làm chậm sender nếu receiver không đọc đủ nhanh. Phù hợp cho NDJSON/SSE, nhưng đường truyền giữa nhiều middlebox có thể bị đệm. Không có cơ chế **request(n)** trong HTTP/1.1 protocol.

**HTTP/2:** DATA frame có flow-control window theo **stream** và **connection**. Peer cập nhật khả năng nhận byte bằng **WINDOW_UPDATE**. Đây là lợi thế vận hành cho multiplexing, nhưng số byte window không phải số Event Java đã xử lý. Một proxy kết thúc HTTP/2 ở phía client rồi chuyển HTTP/1.1 tới backend làm thành **hai đoạn độc lập**.

Bật **server.http2.enabled=true** trong Spring Boot không tự chứng minh pipeline có backpressure đầu-cuối; protocol version và demand là hai chuyện khác nhau.

### 10.2 SSE (Server-Sent Events)

SSE phù hợp luồng thông báo dài, một chiều server tới client, nhưng browser **EventSource** không phát **request(n)**. Client JavaScript có thể xử lý sự kiện chậm, trong khi thư viện/proxy/browser vẫn có buffer. Dùng heartbeat khi kết nối dài cần phát hiện mất kết nối; giới hạn người đăng ký, bộ nhớ, số sự kiện chờ và chính sách với subscriber chậm. Nếu mọi event đều quan trọng, cần cơ chế resume/replay có giới hạn và event ID, không dùng drop ngẫu nhiên.

### 10.3 WebSocket

WebSocket cho phép truyền message hai chiều trên kết nối dài; một API reactive có thể cung cấp **Flux** nhận/gửi message, nhưng giao thức WebSocket không mang trực tiếp Reactive Streams **request(n)** giữa hai phía. TCP và buffer vẫn có giới hạn; với phía phát dữ liệu nhanh cần quản lý outbound queue, downstream subscription và khả năng xử lý message của client.

### 10.4 Reverse proxy / CDN / API gateway

Proxy có thể nhận trọn response vào RAM hoặc disk trước khi gửi tiếp, **response buffering**, **request buffering**, chuyển protocol, nén/giải nén hoặc chặn những kiểu stream cụ thể. Khi proxy đệm, backend có thể thấy proxy là consumer nhanh, mặc dù browser vẫn đang đọc rất chậm. Vì vậy hãy kiểm tra cấu hình và đo tại **browser↔edge** lẫn **edge↔Spring Boot**. Thay đổi buffering cần căn cứ vào security, tài nguyên, quan sát và chi phí thực tế.

### 10.5 Database, filesystem và outbound service

Backpressure chỉ giúp "chậm lại" nếu **nguồn upstream** hỗ trợ hoặc được điều tiết tại một queue. Driver cơ sở dữ liệu reactive hỗ trợ cursor/fetch theo mức độ nhất định có thể vận hành khác hẳn JDBC blocking luôn trả một danh sách lớn. Nguồn file, object storage và message broker cũng có đặc tính đọc trước, batch và acknowledgement riêng. Dùng driver/client phù hợp, xử lý cancellation, giới hạn dữ liệu đang xử lý và bảo đảm semantics của transaction.

### 10.6 Ranh giới blocking và Servlet MVC

Một phương thức **JDBC**, **RestTemplate**, thao tác file blocking hoặc xử lý CPU nặng trên Netty event loop có thể làm chậm **mọi connection** dùng chung luồng đó. Nếu chưa đổi được thư viện, cô lập blocking work ở scheduler thích hợp như **Schedulers.boundedElastic()**, đồng thời chặn số tác vụ đồng thời và queue theo khả năng chịu tải. **boundedElastic** không làm JDBC thành reactive; nó chỉ di chuyển nơi chờ sang thread khác với ngân sách hữu hạn.

Spring MVC hỗ trợ nhiều kiểu async/streaming, nhưng cơ chế ghi Servlet và cách adapter vận hành khác WebFlux với Reactor Netty. Đừng cho rằng chỉ vì controller MVC trả kiểu Flux hoặc DeferredResult là toàn bộ đường HTTP, codec và backend đã có một hợp đồng Reactive Streams thống nhất.

## 11. Bộ nhớ, lỗi và huỷ: backpressure không thể tự thay thế bảo vệ tài nguyên

**Gom dữ liệu:** **bodyToMono(byte[])**, **collectList()**, hoặc JSON decode thành một object rất lớn đều có thể đòi bộ nhớ lớn. Spring codec hỗ trợ **maxInMemorySize** để đặt giới hạn cho những tình huống decoding/buffering tương ứng, nhưng đó không phải quota toàn bộ app; nếu bạn tự buffer hoặc queue, phải tự giới hạn.

**DataBuffer:** Với Reactor Netty, các byte buffer có thể được pool/reference-count. Khi tự thao tác **Flux<DataBuffer>**, filter, drop hoặc hủy ở nhánh tùy biến, phải theo hướng dẫn **DataBufferUtils.release** và cách sở hữu buffer để không rò rỉ direct memory. Khi sử dụng codec chuẩn để chuyển thành POJO, phần lớn việc quản lý buffer do framework thực hiện.

**Lỗi và cancellation:** Khi consumer hủy stream hoặc client disconnect, quan sát **doOnCancel**, **doFinally**, đóng cursor/file/subscription và cleanup tài nguyên phù hợp. Không dựa tuyệt đối vào việc ứng dụng nhận tín hiệu cancel tức thời: OS/proxy có thể còn buffer; các phần việc ghi side effect đã thực hiện có thể không đảo ngược được.

**Giới hạn tải:** Kết hợp connection cap, timeout, concurrent-request cap, kích thước body, giới hạn hàng đợi, batch size, retry budget, memory/CPU và độ chậm nguồn. Nếu sự kiện không được phép mất, ưu tiên queue bền vững và cơ chế acknowledgement/replay thay vì **onBackpressureDrop**.

**Khả năng quan sát:** Theo dõi p95/p99 latency, active connections/streams, pending writes, queue depth, số subscription, cancellation/error, throughput, heap/direct memory, CPU, độ trễ proxy, số phần tử đang chờ và độ trễ database. Log **doOnRequest** chỉ là bằng chứng ở một đoạn pipeline; cần ghép với metric network mới hiểu giới hạn thực.

## 12. Thiết kế test để tránh kết luận nhầm

Một kiểm thử tốt tách ít nhất ba câu hỏi:

1. **Publisher đúng contract demand không?** Dùng **StepVerifier.create(flux, 0)** rồi yêu cầu từng đợt, xác nhận không phát dữ liệu khi chưa có demand và xử lý terminal/cancel đúng. Đây là mức đơn vị (mục 7).
2. **HTTP adapter có stream dữ liệu không?** Dùng **WebTestClient** hoặc một HTTP client có thể đọc body từng phần, chọn đúng **Content-Type**, quan sát khi nào phần tử được nhận và client hủy sớm. Nếu test helper gom toàn bộ response, chính helper đó đã che mất hành vi streaming.
3. **Một client đọc chậm có làm các buffer/queue tăng vô hạn không?** Chạy tải kiểm soát qua cả proxy/ingress, giảm tốc độ client, quan sát bộ nhớ, socket, connector, queue, huỷ và throughput. Không kết luận từ một lần curl localhost vì OS/codec có thể đệm đủ lượng dữ liệu nhỏ.

Đo riêng **HTTP/1.1** và **HTTP/2**, và giữ nguyên payload, số client, mức song song, TLS/proxy, độ trễ mạng, kích thước item. Nếu nguồn là in-memory Flux.range nhỏ, nó có thể hoàn tất trước khi backpressure ở network trở thành nút thắt. Cần dataset đủ lớn nhưng **có giới hạn an toàn** và chính sách hủy rõ ràng.

## 13. Bảng chẩn đoán khi triển khai

| Triệu chứng | Giả thuyết cần kiểm tra | Hành động thực tế |
| --- | --- | --- |
| Heap tăng nhanh khi dùng Flux | collectList, cache, buffer không giới hạn, concurrency/prefetch lớn | Profile allocation và queue, chuyển sang streaming/bounded collection khi phù hợp. |
| Direct memory tăng | DataBuffer không release, outbound network queue | Kiểm tra sở hữu pooled buffers, leak detector, metric Netty và đường cancel. |
| doOnRequest luôn thấy Long.MAX_VALUE | Terminal subscriber/operator đã yêu cầu unbounded | Kiểm tra vị trí log và toán tử, dùng StepVerifier để test điều khiển demand; không đánh đồng với dữ liệu vượt bộ nhớ. |
| curl nhận response một lần ở cuối | Codec content type đang aggregate, proxy buffering hoặc client buffering | Dùng NDJSON/SSE phù hợp; kiểm tra header, flush, proxy config và client. |
| Một client chậm làm server quá tải | Nguồn push không thể pause, queue lớn, nhiều client cùng giữ stream | Giới hạn connection/queue, đặt overflow policy, timeout và resource budgets. |
| Backend hiện HTTP/1.1 dù browser hiện HTTP/2 | Proxy chuyển protocol ở hai chặng | Đo hai chặng riêng; HTTP/2 không quyết định việc hỗ trợ Reactive Streams ở service. |
| Blocking timeout khi tải tăng | JDBC hoặc gọi HTTP blocking chạy trên event-loop | Đo blocked event-loop; đổi sang non-blocking driver hoặc cô lập có giới hạn. |
| Subscriber hủy nhưng upstream vẫn làm việc | Source không hỗ trợ cancel, side effect đã khởi chạy hoặc buffer đã nạp | Kiểm tra cancellation hook, cleanup, rate/concurrency và tính huỷ được của nguồn. |
| Thêm onBackpressureBuffer làm đỡ lỗi ban đầu rồi OOM | Đệm đã chuyển áp lực thành tăng RAM | Đặt bounded buffer, chọn overflow policy rõ và sửa nguồn gây quá tải. |

## 14. Bài tập tình huống và tự kiểm tra

**Tình huống A:** API trả 500.000 record từ database dưới dạng Flux, nhưng service gọi collectList() rồi mới serialize một JSON array. Vì sao response không còn streaming hiệu quả? Vì **collectList** giữ toàn bộ record cho tới khi nguồn hoàn thành và tạo list, dễ tăng bộ nhớ; cân nhắc serialize từng record bằng NDJSON hoặc stream ở boundary phù hợp, đồng thời kiểm tra demand từ driver.

**Tình huống B:** Trình duyệt kết nối SSE qua một proxy; server log request ít và memory ổn, nhưng người dùng thấy nhiều event dồn thành đợt. Nguyên nhân khả dĩ là gì? **Proxy/client buffering hoặc flush policy**. Cần đo cả hai chặng trước khi sửa backpressure trong Flux.

**Tình huống C:** Flux xử lý file upload từng DataBuffer, sau một thời gian direct memory tăng. Nên tìm ở đâu? Kiểm tra **đường consume/drop/cancel của pooled DataBuffer**, buffer release và queue của connector; demand đúng không loại trừ leak.

**Tình huống D:** Một client chỉ xử lý 10 item/giây, server gửi 1.000 item/giây. Có phải thêm limitRate(10) là đủ? **Không.** limitRate giới hạn **số phần tử được request theo đợt**, không phải 10 item/giây. Cần consumer xử lý theo demand, giới hạn công việc đang bay, bảo vệ queue và đo ranh giới transport/proxy.

Câu hỏi cuối bài:

1. Demand **request(5)** được tính theo byte hay phần tử?
2. Vì sao **request(n)** không tự đi qua hai host bằng HTTP/2?
3. TCP flow control có nhận biết message/event nghiệp vụ không?
4. Vì sao một endpoint trả về **Flux** vẫn có thể gây OOM?
5. Khi nào được phép **drop/latest**, khi nào bắt buộc lưu bền vững?
6. Muốn xác nhận backpressure khi browser đọc chậm, bạn phải đo những đoạn nào?

**Đáp án gợi ý:** (1) phần tử; (2) Reactive Streams là hợp đồng trong pipeline, HTTP/2 chỉ có flow-control theo byte; (3) không; (4) nguồn/codec/operator/proxy/queue có thể đệm hoặc phá streaming; (5) chỉ bỏ khi nghiệp vụ cho phép mất dữ liệu, còn dữ liệu quan trọng cần lưu/ack/retry có kiểm soát; (6) publisher/operator/HTTP connector, socket/proxy và client, cùng bộ nhớ/queue.

## 15. Tài liệu tham khảo chính thống

- **Reactive Streams Specification:** https://www.reactive-streams.org/ và https://github.com/reactive-streams/reactive-streams-jvm (hợp đồng Publisher, Subscriber, request và cancel).
- **Project Reactor Reference – Backpressure:** https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html (cách request truyền upstream, unbounded demand, limitRate, prefetch).
- **Spring Framework – WebFlux Reactive Core:** https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html (non-blocking I/O, HttpHandler, adapter, codec/đệm).
- **Spring Framework – WebClient:** https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html (HTTP reactive client, body streams).
- **Spring Framework – Data Buffers and Codecs:** https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html (sở hữu và release DataBuffer).
- **RFC 9113 – HTTP/2:** https://www.rfc-editor.org/rfc/rfc9113 (frame, stream và flow control theo byte).
