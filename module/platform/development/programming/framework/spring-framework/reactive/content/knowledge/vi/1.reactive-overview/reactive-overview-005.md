# Quan hệ giữa Reactive Streams, Reactor, Reactor Netty và Spring WebFlux

## 1. Bức tranh tổng thể

Bốn tên gọi này nằm ở **những tầng trách nhiệm khác nhau** trong lập trình reactive trên JVM:

| Thành phần | Bản chất | Trách nhiệm chính | Ví dụ |
| --- | --- | --- | --- |
| **Reactive Streams** | Đặc tả (specification) về xử lý luồng bất đồng bộ có điều tiết nhu cầu | Định nghĩa hợp đồng giữa nơi phát dữ liệu và nơi nhận: Publisher, Subscriber, Subscription, Processor; quy tắc tín hiệu và backpressure | Subscriber gọi Subscription.request(n) để yêu cầu tối đa n phần tử |
| **Project Reactor** | Thư viện lập trình reactive trên JVM, triển khai hợp đồng Reactive Streams | Cung cấp kiểu Mono, Flux, toán tử biến đổi/phối hợp luồng và scheduler | Flux.range(1, 3).map(n -> n * 2) |
| **Reactor Netty** | Thư viện mạng bất đồng bộ xây trên Netty và tích hợp với Reactor | Cung cấp HTTP/TCP client, HTTP server, kết nối, đọc/ghi socket, I/O event loop và API reactive | HttpServer, HttpClient; HTTP server nhúng thường dùng với WebFlux trong Spring Boot |
| **Spring WebFlux** | Framework web reactive của Spring Framework | Ánh xạ URL, xử lý request/response, route, controller, codec, validation, error handling và tích hợp các nguồn dữ liệu reactive | @RestController trả về Mono hoặc Flux; RouterFunction |

Sơ đồ quan hệ phổ biến trong ứng dụng Spring Boot WebFlux chạy bằng Reactor Netty:

~~~text
HTTP client
    |
    v
[Reactor Netty: HTTP server, TCP/socket, event loop]
    |
    v
[Spring WebFlux: routing, handler, codec, HTTP response]
    |
    v
[Ứng dụng: controller/service/repository]
    |
    v
[Project Reactor: Mono / Flux và các toán tử]
    |
    v
[Reactive Streams: hợp đồng Publisher - Subscriber - Subscription]
~~~

**Đọc sơ đồ theo trách nhiệm, không hiểu là một chuỗi thư viện bắt buộc phải gọi theo đúng thứ tự.** WebFlux sử dụng Reactor làm nền tảng API reactive và có thể chạy trên nhiều runtime web tương thích; Reactor Netty là lựa chọn server phổ biến, không phải định nghĩa của WebFlux. Reactive Streams là hợp đồng nền tảng mà Reactor thực thi, không phải HTTP server.

## 2. Reactive Streams: hợp đồng nền tảng

Reactive Streams giải quyết bài toán: một nguồn bất đồng bộ có thể phát dữ liệu nhanh hơn tốc độ bên nhận xử lý. Thay vì để nguồn phát vô hạn rồi tích đầy bộ nhớ, bên nhận có thể **báo nhu cầu (demand)**.

Bốn interface chính trong gói org.reactivestreams:

- **Publisher<T>**: nguồn cung cấp chuỗi phần tử; phương thức subscribe(Subscriber).
- **Subscriber<T>**: bên tiêu thụ, nhận các tín hiệu onSubscribe, onNext, onError, onComplete.
- **Subscription**: liên kết giữa một Publisher và một Subscriber; request(n) yêu cầu thêm tối đa n phần tử; cancel() hủy đăng ký.
- **Processor<T,R>**: vừa là Subscriber vừa là Publisher, có thể nhận và phát dữ liệu (không bắt buộc phải dùng khi xây pipeline).

Trình tự tín hiệu cơ bản:

~~~text
Publisher.subscribe(subscriber)
         |
         v
Subscriber.onSubscribe(subscription)
         |
         +-- subscription.request(n), n > 0
         |
         +-- onNext(item) tối đa theo demand được cấp
         |
         +-- onComplete() HOẶC onError(error)
         |
         +-- không còn onNext sau tín hiệu kết thúc
~~~

Các điểm cần nhớ:

1. **request(n) là số phần tử được yêu cầu**, không phải số byte và không phải lệnh gửi HTTP request mới. Demand có thể được bổ sung theo thời gian.
2. **Backpressure** là cơ chế kiểm soát tốc độ sản xuất/tiêu thụ qua tín hiệu demand. Trong pipeline có nhiều toán tử, lượng request thực tế có thể được toán tử điều chỉnh (ví dụ prefetch), nên không giả định mọi tầng đều truyền nguyên giá trị n.
3. Subscription có thể bị hủy bằng cancel(), chẳng hạn khi phía client ngắt kết nối; việc hủy cần được các tầng hỗ trợ mới có tác dụng lan truyền đầy đủ.
4. onError và onComplete là **tín hiệu kết thúc thay thế nhau** của một subscription; sau khi kết thúc không còn dữ liệu mới cho subscription đó.
5. Đặc tả nói về giao tiếp giữa các thành phần stream. Nó **không tự cung cấp** API web, socket, database, scheduler hay chính sách nghiệp vụ.

Reactive Streams đặt ra quy tắc để các thư viện tương thích phối hợp với nhau. Việc cùng dùng đặc tả không có nghĩa mọi thư viện có cùng API, toán tử hay chiến lược thực thi.

## 3. Project Reactor: API lập trình dựa trên hợp đồng đó

Reactor triển khai Reactive Streams và cung cấp hai kiểu đặc trưng:

| Kiểu | Số phần tử thành công tối đa | Tình huống thường gặp |
| --- | --- | --- |
| **Mono<T>** | 0 hoặc 1 | Lấy một bản ghi, gọi dịch vụ trả một kết quả, biểu diễn việc hoàn tất với Mono<Void> |
| **Flux<T>** | 0 đến nhiều | Danh sách kết quả, sự kiện liên tục, stream server-sent events |

Ví dụ về luồng biến đổi:

~~~java
Flux<Integer> doubled = Flux.range(1, 3)
        .map(n -> n * 2)
        .filter(n -> n >= 4);
// Khi được subscribe: phát 4, 6 rồi hoàn tất.
~~~

Đây là **đoạn minh họa**, chưa phải chương trình Java độc lập. Khai báo một pipeline thường chỉ mô tả việc sẽ xảy ra: nhiều Publisher trong Reactor là **cold**, chưa xử lý cho tới khi có subscription. Có ngoại lệ như hot publisher và nguồn đã vận hành độc lập, nên không đồng nhất toàn bộ Reactor với cơ chế lazy.

Một pipeline Reactor thường được hình dung như sau:

~~~text
Flux/Mono (Publisher) --subscribe--> Subscriber
       |                                |
       +<------- request(n) ------------+
       +--------- onNext -------------->+
       +--------- onComplete/onError --->+
~~~

Các toán tử có vai trò khác nhau:

- **map**: biến đổi một phần tử đồng bộ.
- **flatMap**: ánh xạ phần tử thành Publisher khác và phối hợp các kết quả; có thể thay đổi thứ tự khi xử lý đồng thời.
- **concatMap**: xử lý Publisher con theo thứ tự.
- **filter**, **take**, **collectList**, **zip**, **onErrorResume**: lọc, giới hạn, gom, kết hợp, phục hồi khi lỗi.
- **subscribeOn**, **publishOn**: điều chỉnh ngữ cảnh thực thi tại những vị trí nhất định; không tự làm cho lời gọi blocking trở thành non-blocking.

Ví dụ kiểm soát demand bằng Reactor, với dependency reactor-core có sẵn qua spring-boot-starter-webflux:

~~~java
package com.example.reactiverelationship;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandDemo {
    public static void main(String[] args) {
        Flux.range(1, 4).subscribe(new BaseSubscriber<Integer>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("received=" + value);
                request(1);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("completed");
            }
        });
    }
}
~~~

Kết quả chuẩn:

~~~text
received=1
received=2
received=3
received=4
completed
~~~

Ở ví dụ nguồn hữu hạn Flux.range, subscriber cấp demand từng phần tử. Việc này cho thấy hợp đồng **subscription/request/onNext**; với nguồn khác, cách điều tiết upstream phụ thuộc khả năng hỗ trợ backpressure của nguồn đó.

## 4. Reactor Netty: tầng mạng và vòng lặp I/O

Netty là framework mạng bất đồng bộ theo mô hình event loop. Reactor Netty xây API reactive cho HTTP/TCP trên Netty và kết nối vòng đời I/O với Mono/Flux. Trong ứng dụng WebFlux dùng Reactor Netty:

1. Reactor Netty nhận kết nối và HTTP request, đọc bytes trên socket qua event loop.
2. Dữ liệu request được chuyển thành dạng mà HTTP handler có thể tiêu thụ.
3. WebFlux định tuyến, giải mã body, gọi handler ứng dụng và tạo phản hồi.
4. Chuỗi phản hồi được encode; Reactor Netty ghi dữ liệu ra network qua I/O bất đồng bộ.

Reactor Netty quản lý kết nối, event loop và network I/O; **không quyết định route URL, business logic hay validation của controller**. Những trách nhiệm web này thuộc WebFlux hoặc code ứng dụng.

Điều tiết demand của Reactor có thể hỗ trợ kiểm soát dòng dữ liệu trong pipeline, nhưng **không có quy tắc một request(n) tương ứng một lần TCP read hay một packet HTTP**. Các buffer, codec, giao thức, tốc độ client và hệ thống ở xa ảnh hưởng hành vi thực tế.

Trong cấu hình Spring Boot với spring-boot-starter-webflux mà không có cấu hình server khác, Reactor Netty là server nhúng thường được tự động cấu hình. Có thể dùng các server tương thích khác, vì **WebFlux không đồng nghĩa với Reactor Netty**.

## 5. Spring WebFlux: tầng web dùng Reactor

Spring WebFlux cung cấp hai phong cách lập trình chính:

- **Annotated controllers**: dùng @RestController, @GetMapping, @RequestBody; trả Mono<T>, Flux<T> hoặc kiểu được framework hỗ trợ.
- **Functional endpoints**: dùng RouterFunction và HandlerFunction để định tuyến và xử lý request theo hàm.

Ở cả hai phong cách, Spring xử lý HTTP concerns như route, status, headers, codec, đọc body và ghi response. Reactor giúp mô tả chuỗi xử lý bất đồng bộ, trong khi HTTP server runtime thực hiện mạng.

### Luồng một HTTP request

~~~text
GET /numbers
  -> Reactor Netty nhận HTTP request
  -> WebFlux ánh xạ @GetMapping("/numbers")
  -> Controller trả Flux<Integer>
  -> WebFlux subscribe/điều phối publisher để ghi response
  -> Codec chuyển dữ liệu thành HTTP body phù hợp
  -> Reactor Netty gửi bytes đến client
~~~

Lưu ý quan trọng: controller **trả về Publisher**, framework mới điều phối subscription để xử lý response. Nếu controller tự gọi subscribe() rồi bỏ subscription đó, lỗi, hủy và vòng đời HTTP dễ bị tách khỏi framework.

### Ví dụ ứng dụng chạy được (Java 17+, Maven, Spring Boot 3.3.5)

Tạo ba tệp sau:

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactive-relationship</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/com/example/reactiverelationship/ReactiveRelationshipApplication.java**

~~~java
package com.example.reactiverelationship;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveRelationshipApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveRelationshipApplication.class, args);
    }
}
~~~

**src/main/java/com/example/reactiverelationship/RelationController.java**

~~~java
package com.example.reactiverelationship;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class RelationController {

    @GetMapping("/relation")
    public Mono<String> relation() {
        return Mono.just("WebFlux -> Reactor -> Reactor Netty");
    }

    @GetMapping("/numbers")
    public Flux<Integer> numbers() {
        return Flux.range(1, 3).map(n -> n * 2);
    }
}
~~~

Tại thư mục chứa pom.xml, chạy:

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -s http://localhost:8080/relation
curl -s http://localhost:8080/numbers
~~~

Body phản hồi (lần lượt):

~~~text
WebFlux -> Reactor -> Reactor Netty
[2,4,6]
~~~

Spring Boot đưa các dependency phù hợp vào classpath: Spring WebFlux hỗ trợ route/controller và HTTP encoding, reactor-core cung cấp Mono/Flux, Reactor Netty cung cấp server mạng mặc định. Trong ví dụ này, tên ở endpoint là cách ghi nhớ đơn giản về các tầng; **không phải mô tả rằng WebFlux không thể chạy trên server khác**.

Nếu muốn chạy riêng DemandDemo trong cùng dự án, tạo thêm tệp Java cùng tên class tại cùng package và thực thi bằng IDE hoặc compile/run với classpath dependency Maven. Ví dụ DemandDemo không đòi hỏi server HTTP.

### Vị trí của WebClient

WebFlux cũng cung cấp **WebClient** cho HTTP client reactive. Khi dùng mặc định trong cấu hình phù hợp, WebClient có thể dùng Reactor Netty HttpClient để thực hiện I/O. WebClient là **API client ở tầng Spring**; Reactor Netty HttpClient là **bộ kết nối mạng** phía dưới. Không nên nhầm WebClient là HTTP server của WebFlux.

## 6. Những nhầm lẫn thường gặp và hệ quả kỹ thuật

| Nhận định dễ nhầm | Hiểu đúng | Hệ quả khi thiết kế |
| --- | --- | --- |
| “Reactive Streams là thư viện HTTP” | Là đặc tả Publisher/Subscriber/backpressure, độc lập giao thức | Chọn WebFlux/Reactor Netty hoặc thành phần khác cho HTTP |
| “Reactor và Reactor Netty là một” | Reactor xử lý pipeline; Reactor Netty tích hợp network I/O | Có thể dùng Flux/Mono trong ứng dụng không có web server |
| “WebFlux bắt buộc chạy Reactor Netty” | WebFlux có thể chạy trên runtime web tương thích khác | Chọn runtime dựa trên môi trường và yêu cầu triển khai |
| “Tất cả publisher tự động chống tràn bộ nhớ” | Backpressure chỉ có hiệu lực theo semantics của từng nguồn và toán tử; một số nguồn có chiến lược buffer/drop/error | Xem nguồn, operator, buffering và tải thực tế |
| “Mono/Flux luôn chạy trên thread khác” | Publisher không tự đồng nghĩa multithreading hay async I/O | Hiểu scheduler và nơi chạy đoạn code |
| “WebFlux luôn nhanh hơn Spring MVC” | Lợi ích thường xuất hiện với nhiều tác vụ I/O không blocking và mức đồng thời lớn; không bảo đảm latency/throughput tốt hơn cho mọi workload | Đo tải, đo độ trễ và tính chi phí vận hành |
| “Chỉ cần trả Mono thì lời gọi blocking thành non-blocking” | JDBC, Thread.sleep(), gọi HTTP blocking vẫn chặn thread nếu được gọi trực tiếp | Ưu tiên driver/API không blocking, hoặc cô lập blocking hợp lý |
| “Controller nên tự subscribe()” | WebFlux sở hữu subscription để phối hợp response, lỗi và hủy | Trả Publisher cho framework thay vì tự subscribe() |

### Blocking trong event loop

Ví dụ sai về ý tưởng:

~~~java
@GetMapping("/bad")
public Mono<String> bad() {
    String value = legacyBlockingClient.call(); // Chặn thread xử lý request.
    return Mono.just(value);
}
~~~

Việc bao một kết quả đồng bộ vào Mono.just **không làm lời gọi ban đầu trở thành non-blocking**. Nếu chưa thay được API cũ, có thể cô lập công việc blocking lên scheduler dành riêng:

~~~java
@GetMapping("/legacy")
public Mono<String> legacy() {
    return Mono.fromCallable(() -> legacyBlockingClient.call())
            .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
}
~~~

Hai đoạn này chỉ **minh họa cấu trúc**, giả định đã có biến legacyBlockingClient và phương thức call(); không phải class Java độc lập. boundedElastic giúp tránh chặn event loop với công việc blocking có giới hạn, nhưng vẫn tiêu thụ thread và có thể nghẽn khi tải cao. Giải pháp ưu tiên lâu dài là sử dụng client/driver thật sự non-blocking nếu phù hợp.

### Backpressure không phải phép màu cho HTTP

Với nguồn có giới hạn hữu hạn như Flux.range, có thể dễ dàng điều tiết số phần tử được đẩy tới subscriber. Với nguồn sự kiện bên ngoài, websocket, message broker hoặc network peer, việc truyền tải demand ngược tới nguồn có thể cần adapter, buffer và chính sách rõ ràng. Cần phân biệt:

- **Demand của Reactive Streams**: số phần tử được subscriber yêu cầu trong pipeline.
- **Flow control giao thức**: cơ chế như TCP receive window, HTTP/2 flow control và các queue.
- **Giới hạn tài nguyên**: thread, connection pool, bộ nhớ, buffer, timeout, hàng đợi.

Chúng có thể tương tác nhưng không phải một cơ chế duy nhất. Chỉ dựa vào Mono/Flux không thay thế giới hạn tải, timeout và kiểm thử khả năng chịu tải.

## 7. Khi nào dùng và cách tự kiểm tra hiểu bài

- Dùng **Reactor** khi cần ghép các phép xử lý bất đồng bộ hoặc reactive trong ứng dụng Java, kể cả không có HTTP.
- Dùng **Reactor Netty** khi cần HTTP/TCP client/server reactive hoặc khi ứng dụng WebFlux chọn nó làm network runtime.
- Dùng **Spring WebFlux** khi muốn xây endpoint, WebClient hoặc tích hợp web reactive của Spring. Cân nhắc nếu toàn bộ đường đi I/O có thể thực hiện non-blocking.
- Dùng **Reactive Streams** như hợp đồng tư duy về tín hiệu, cancellation và demand khi đánh giá hành vi mọi tầng.

Ba câu hỏi tự kiểm tra:

1. Nếu bỏ Reactor Netty và chạy WebFlux trên server tương thích khác, Mono/Flux và contract Reactive Streams có mất không? **Không**. Chúng là các tầng khác nhau.
2. Nếu dùng Flux.range trong ứng dụng CLI không có Spring, có cần WebFlux không? **Không**. Reactor chạy độc lập với framework web.
3. Nếu controller trả Mono nhưng gọi JDBC blocking ngay trước khi tạo Mono, request có non-blocking không? **Không**. Lời gọi JDBC vẫn blocking và cần lựa chọn kiến trúc xử lý phù hợp.

**Mối quan hệ cốt lõi:** Reactive Streams đặt ra hợp đồng truyền dữ liệu theo demand; Reactor hiện thực hợp đồng và cung cấp API Mono/Flux; Reactor Netty nối API reactive với mạng bất đồng bộ; Spring WebFlux dùng Reactor để lập trình HTTP và có thể sử dụng Reactor Netty làm runtime mạng. Nhận diện đúng bốn tầng giúp chọn công nghệ, điều tra thread bị chặn và thiết kế backpressure thực tế.