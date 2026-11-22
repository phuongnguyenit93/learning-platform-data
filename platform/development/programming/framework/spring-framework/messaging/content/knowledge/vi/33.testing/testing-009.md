# Kiểm thử RSocketRequester và RSocketMessageHandler

RSocket là giao thức messaging hai chiều, đa luồng, chạy trên TCP, WebSocket hoặc transport tương thích khác. Khi kiểm thử ứng dụng Spring, cần xác nhận cả hai phía của hợp đồng: client tạo đúng request với route, data, metadata và interaction model; responder nhận đúng request, gọi đúng handler, encode kết quả và trả về tín hiệu reactive phù hợp.

Spring cung cấp hai thành phần trung tâm:

- RSocketRequester là API fluent để gửi request, truyền data/metadata và đọc kết quả thành Mono hoặc Flux. Nó che giấu phần lớn thao tác tạo Payload và encode/decode.
- RSocketMessageHandler ánh xạ request RSocket vào các method @MessageMapping và @ConnectMapping, đồng thời quản lý chuyển đổi payload, route và metadata.

Bài học tập trung vào kiểm thử thực tế hai thành phần này bằng JUnit 5, Reactor Test và RSocket LocalTransport. Ví dụ dùng Spring Framework 7.0.8, RSocket Java 1.1.5 và Java 17. Nếu dự án dùng Spring Boot, nên ưu tiên các phiên bản dependency do Spring Boot BOM quản lý.

## 1. Xác định ranh giới cần kiểm thử

Một bài test chỉ gọi trực tiếp method Java của controller không xác nhận được RSocket route, metadata, serialization hoặc protocol interaction. Ngược lại, một test end-to-end qua TCP/WebSocket thường chậm hơn và khó cô lập lỗi. Hãy chọn mức kiểm thử theo điều cần chứng minh:

| Mức kiểm thử | Cách làm | Điều được xác nhận |
|---|---|---|
| Unit test business logic | Gọi service hoặc method nghiệp vụ trực tiếp | Quy tắc nghiệp vụ, validation, nhánh lỗi |
| Handler mapping test | Khởi tạo RSocketMessageHandler với handler cụ thể | Phát hiện mapping, route, method signature, loại tương tác |
| Local transport integration test | Nối RSocketRequester và RSocketMessageHandler qua LocalTransport | Encode/decode, route metadata, request/response/stream và vòng đời kết nối |
| Transport integration test | Chạy TCP hoặc WebSocket thực tế | Cấu hình network, TLS/proxy nếu có, frame/connection behavior |
| Application context test | Khởi tạo Spring context hoặc Spring Boot test | Bean discovery, @Controller scanning, auto-configuration, cấu hình codec |

LocalTransport chạy trong cùng tiến trình, không mở socket TCP và không kiểm tra Netty/TLS/WebSocket. Nó vẫn đưa request qua RSocket protocol và Spring requester/responder stack, vì vậy rất hữu ích để kiểm tra tương tác giữa hai thành phần với chi phí thấp. Dành một số ít test riêng cho TCP hoặc WebSocket để xác nhận cấu hình transport thật.

## 2. RSocketRequester cần được kiểm tra điều gì?

RSocketRequester tạo request bằng route, data, metadata và phương thức lấy kết quả. Các điểm cần xác nhận gồm:

- Route được gửi đúng và khớp với @MessageMapping ở responder.
- Data được encode theo data MIME type và decode thành đúng kiểu response.
- Metadata được gửi theo MIME type đã đăng ký và được MetadataExtractor chuyển thành header đúng.
- Interaction model phù hợp với số lượng input/output.
- Kết quả hoàn tất, lỗi, timeout hoặc bị cancel được quan sát đúng.
- Connection được dispose khi test hoặc component sở hữu requester kết thúc.

Các cách gọi phổ biến:

~~~java
Mono<Reply> response = requester.route("orders.find")
        .data(orderId)
        .retrieveMono(Reply.class);

Flux<Update> updates = requester.route("orders.watch")
        .data(orderId)
        .retrieveFlux(Update.class);

Mono<Void> sent = requester.route("orders.audit")
        .data(event)
        .send();
~~~

retrieveMono() phù hợp với Request-Response; retrieveFlux() phù hợp với Request-Stream hoặc output nhiều phần tử. send() dùng cho Fire-and-Forget. Hoàn tất send() chỉ cho biết request đã được gửi theo hợp đồng requester; nó không chứng minh handler đã xử lý xong hoặc side effect nghiệp vụ đã commit.

RSocket có bốn interaction model chính:

| Interaction | Input | Output | API thường dùng |
|---|---|---|---|
| Request-Response | Một message | Tối đa một response | retrieveMono() |
| Request-Stream | Một message | Nhiều response | retrieveFlux() |
| Fire-and-Forget | Một message | Không có response | send() |
| Request-Channel | Một stream | Một stream response | data(Publisher) và retrieveFlux() |

Khi test, đừng chỉ kiểm tra giá trị đầu tiên. Với stream, xác nhận thứ tự, số phần tử, terminal signal và cancellation/backpressure nếu đó là yêu cầu của ứng dụng.

## 3. RSocketMessageHandler cần được kiểm tra điều gì?

RSocketMessageHandler là adapter từ RSocket request sang method handler. Nó hỗ trợ @MessageMapping cho từng request và @ConnectMapping cho connection setup hoặc metadata push. Nó xác định interaction type dựa trên cardinality của input và output method:

- Một payload đầu vào và một giá trị trả về (ví dụ Mono<T>) tạo Request-Response.
- Một payload đầu vào và nhiều giá trị trả về (Flux<T>) tạo Request-Stream.
- Một payload đầu vào và void/Mono<Void> có thể tạo Fire-and-Forget.
- Stream đầu vào được xử lý như Request-Channel.

Các kiểm tra quan trọng:

1. Route hợp lệ gọi đúng method.
2. Route không tồn tại trả lỗi phù hợp.
3. Payload đầu vào được decode đúng kiểu và không bị nhầm với metadata.
4. @DestinationVariable, @Header và @Headers nhận đúng giá trị đã extract.
5. Mono/Flux trả về được encode đúng và giữ đúng thứ tự.
6. Exception đồng bộ và reactive error được truyền thành error signal phù hợp.
7. @ConnectMapping xử lý setup data/metadata trước khi request trên connection bắt đầu.
8. Handler không phát side effect ngoài ý muốn khi publisher chưa được subscribe hoặc đã bị cancel.

Khi chạy trong Spring ApplicationContext, RSocketMessageHandler phát hiện các bean @Controller có @MessageMapping/@ConnectMapping. Khi tạo handler bằng code trong test, có thể đăng ký danh sách handler trực tiếp bằng setHandlers(). Cách đăng ký thủ công giúp test một handler cô lập; nó không kiểm tra component scanning hoặc auto-configuration của ứng dụng.

## 4. Tạo LocalTransport test

LocalTransport cung cấp một server/client transport trong bộ nhớ. Tạo tên transport duy nhất cho mỗi test để tránh xung đột khi chạy song song. RSocketServer.bind() khởi động responder; RSocketRequester.builder().transport() tạo requester kết nối tới cùng tên.

Test nên dùng cùng một RSocketStrategies ở hai phía nếu muốn loại trừ sai khác codec khỏi mục tiêu test. Trong production, có thể có strategies khác nhau; khi đó cần thêm test để xác nhận cấu hình MIME type và codec giữa hai phía tương thích.

### 4.1. Maven dependencies

Ví dụ POM tối thiểu để chạy test bên dưới với Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>rsocket-test</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.version>7.0.8</spring.version>
    <rsocket.version>1.1.5</rsocket.version>
    <junit.version>5.12.2</junit.version>
    <reactor.version>3.8.7</reactor.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-messaging</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-core</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-transport-local</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>${reactor.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.3</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Trong ứng dụng Spring Boot, nên dùng dependency management của Boot và các starter tương ứng thay vì cố định thủ công mọi phiên bản. Các dependency chính cho test độc lập là spring-messaging, spring-context, rsocket-core, rsocket-transport-local, reactor-test và JUnit Jupiter.

### 4.2. Test hoàn chỉnh cho Request-Response và Request-Stream

Lưu thành src/test/java/example/RSocketRoundTripTest.java:

~~~java
package example;

import java.time.Duration;
import java.util.List;

import io.rsocket.core.RSocketServer;
import io.rsocket.transport.local.LocalClientTransport;
import io.rsocket.transport.local.LocalServerTransport;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class RSocketRoundTripTest {

    public static class EchoHandler {

        @MessageMapping("echo")
        public Mono<String> echo(@Payload String value) {
            return Mono.just("reply:" + value);
        }

        @MessageMapping("stream")
        public Flux<String> stream(@Payload String prefix) {
            return Flux.just(prefix + "-1", prefix + "-2");
        }
    }

    @Test
    void requesterDispatchesThroughAnnotatedMessageHandler() {
        String transportName = "row382-test";
        RSocketStrategies strategies = RSocketStrategies.create();

        RSocketMessageHandler messageHandler = new RSocketMessageHandler();
        messageHandler.setRSocketStrategies(strategies);
        messageHandler.setHandlers(List.of(new EchoHandler()));
        messageHandler.afterPropertiesSet();

        Disposable server = RSocketServer.create(messageHandler.responder())
                .bind(LocalServerTransport.create(transportName))
                .block(Duration.ofSeconds(5));
        assertNotNull(server);

        RSocketRequester requester = RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .transport(LocalClientTransport.create(transportName));

        try {
            StepVerifier.create(requester.route("echo")
                            .data("hello")
                            .retrieveMono(String.class))
                    .expectNext("reply:hello")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            StepVerifier.create(requester.route("stream")
                            .data("item")
                            .retrieveFlux(String.class))
                    .expectNext("item-1", "item-2")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        }
        finally {
            requester.dispose();
            server.dispose();
        }
    }
}
~~~

Test khởi tạo RSocketMessageHandler, đăng ký hai route, gắn responder vào RSocketServer và tạo requester bằng LocalClientTransport. Sau đó StepVerifier gửi request thật qua protocol và xác nhận:

- Route echo nhận chuỗi hello và trả reply:hello.
- Route stream nhận item và trả hai phần tử item-1, item-2 theo đúng thứ tự.
- Cả hai publisher hoàn tất bình thường.
- Client requester và server đều được dispose trong finally kể cả khi assertion thất bại.

Chạy test:

~~~bash
mvn test
~~~

Kết quả Surefire mong đợi:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
~~~

Đây là integration test trong bộ nhớ, không cần port cố định hoặc server chạy bên ngoài.

## 5. Dùng StepVerifier đúng cách

StepVerifier mô tả các tín hiệu Reactive Streams theo thứ tự và bắt đầu kiểm tra khi gọi verify(). Mẫu cơ bản:

~~~java
StepVerifier.create(publisher)
        .expectNext(expected)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
~~~

Các assertion thường dùng:

- expectNext(value): phần tử kế tiếp phải bằng giá trị mong đợi.
- assertNext(consumer): kiểm tra nhiều field của phần tử.
- expectNextCount(n): xác nhận số phần tử.
- expectError(type): xác nhận publisher kết thúc bằng lỗi đúng kiểu.
- thenCancel(): gửi cancellation từ subscriber.
- thenRequest(n): yêu cầu thêm n phần tử để kiểm tra backpressure.
- verify(Duration): giới hạn thời gian test chờ terminal signal.

Luôn đặt timeout hữu hạn cho verify trong test mạng hoặc test bất đồng bộ để tránh build bị treo. verify() không có timeout mặc định có thể chờ vô hạn.

Với publisher có delay, retry/backoff hoặc timeout dùng scheduler của Reactor, StepVerifier.withVirtualTime() giúp kiểm tra thời gian mà không phải chờ thật. Tạo publisher bên trong Supplier được truyền cho withVirtualTime để virtual scheduler được cài trước khi operator được khởi tạo. Virtual time không mô phỏng độ trễ mạng TCP/WebSocket; vẫn cần timeout thực tế cho transport integration test.

## 6. Kiểm tra metadata và serialization

RSocket có hai loại MIME type: data và metadata. Route thường được encode vào routing metadata; metadata ứng dụng có thể được encode trong composite metadata. Khi test metadata, cần xác nhận cả hai phía dùng đúng cấu hình.

Ví dụ client gửi token metadata:

~~~java
MimeType bearerMimeType =
        MimeType.valueOf("message/x.rsocket.authentication.bearer.v0");

Mono<Account> account = requester.route("accounts.current")
        .metadata(token, bearerMimeType)
        .retrieveMono(Account.class);
~~~

Ở responder, metadata cần được đăng ký với MetadataExtractor hoặc strategy tương ứng trước khi lấy bằng @Header/@Headers. Một method có thể nhận payload và metadata riêng:

~~~java
@MessageMapping("accounts.current")
public Mono<Account> current(
        @Payload AccountQuery query,
        @Header("authorization") String authorization) {
    return accountService.find(query, authorization);
}
~~~

Tên header thực tế phụ thuộc MetadataExtractor và MIME type mà ứng dụng đăng ký; không giả định token tự động trở thành header authorization chỉ vì client gọi metadata(). Test nên gửi metadata thật qua requester và xác nhận giá trị ở handler hoặc service mock.

Với object payload, đăng ký Encoder/Decoder tương thích ở cả client và responder, ví dụ Jackson CBOR hoặc JSON codec. Test một object có field lồng nhau, null/optional field, enum, ngày giờ và collection nếu các kiểu đó xuất hiện trong hợp đồng. Test String hoặc byte[] mặc định không đủ để xác nhận cấu hình codec JSON/CBOR.

## 7. Kiểm thử các nhánh lỗi

Một bộ test tốt cần bao phủ cả lỗi trước khi gửi và lỗi phát sinh trong handler:

| Tình huống | Cách tạo | Điều cần xác nhận |
|---|---|---|
| Route không tồn tại | Gọi route không có mapping | Error signal và nội dung lỗi có thể chẩn đoán |
| Payload sai định dạng | Gửi payload không decode được | Không gọi business handler; lỗi decode được truyền ra |
| Metadata thiếu | Bỏ metadata bắt buộc | Handler từ chối đúng chính sách |
| Business exception | Handler trả Mono.error() | Client nhận error signal; exception mapping nhất quán |
| Handler trả rỗng | Handler trả Mono.empty() | Request-Response hoàn tất không có giá trị theo hợp đồng |
| Stream lỗi giữa chừng | Flux phát vài giá trị rồi error | Giá trị trước lỗi và terminal error đúng |
| Client hủy stream | thenCancel() hoặc dispose subscription | Producer nhận cancellation và giải phóng tài nguyên |
| Connection đóng | Dispose requester hoặc server | Publisher đang chạy kết thúc theo chính sách connection |
| Request quá chậm | Delay lớn hơn timeout của client | Timeout được quan sát; không nhầm với server đã rollback |

Không assert chính xác thông điệp exception nội bộ của framework nếu đó không phải hợp đồng ứng dụng. Ưu tiên assert loại lỗi, mã lỗi hoặc error payload do ứng dụng kiểm soát.

## 8. Kiểm thử Request-Channel và Fire-and-Forget

Request-Channel có stream ở cả input và output. Dùng Flux làm data producer và retrieveFlux để đọc response. Test cần xác nhận backpressure, thứ tự và cancellation. Nếu producer là vô hạn, test phải giới hạn số phần tử hoặc cancel rõ ràng để không giữ connection vô thời hạn.

Fire-and-Forget không có response payload. send() hoàn tất sau khi requester gửi request theo protocol. Nếu cần xác nhận business handler đã xử lý, hãy dùng một tín hiệu kiểm thử độc lập, chẳng hạn CountDownLatch, Sinks.One, test probe hoặc một query xác nhận trạng thái. Không dùng việc send().block() hoàn tất làm bằng chứng handler đã ghi dữ liệu.

Ví dụ xác nhận side effect bằng probe:

~~~java
Sinks.One<String> handled = Sinks.one();

@MessageMapping("audit")
public Mono<Void> audit(@Payload AuditEvent event) {
    return auditService.store(event)
            .doOnSuccess(ignored -> handled.tryEmitValue(event.id()))
            .then();
}
~~~

Trong test, gửi bằng send(), sau đó xác nhận handled.asMono() phát đúng ID. Trong code thật, probe chỉ là dependency của test; không thêm test hook vào production API nếu không cần thiết.

## 9. Kiểm thử @ConnectMapping và connection lifecycle

@ConnectMapping xử lý SETUP frame khi connection được thiết lập và có thể đọc setup data hoặc metadata. Một lỗi setup có thể ngăn connection được chấp nhận. Test nên bao gồm:

- Client gửi setup data hợp lệ và server ghi nhận đúng.
- Setup metadata thiếu hoặc sai định dạng khiến connection bị từ chối theo chính sách.
- @ConnectMapping trả Mono<Void> hoàn tất và connection có thể gửi request tiếp.
- Connection bị đóng thì resource gắn với session được cleanup.
- Nếu server chủ động gửi request ngược về client, client responder phải được đăng ký trên requester builder và test cần xác nhận đúng route ở phía client.

Không gửi request đồng bộ ngay trong lúc xử lý SETUP nếu nó phụ thuộc vào việc SETUP hoàn tất; các request khởi chạy từ @ConnectMapping cần được tách khỏi quá trình xử lý setup theo đúng vòng đời connection.

## 10. Khi nào cần test TCP/WebSocket thật?

LocalTransport xác nhận requester, responder, route và codec qua protocol stack trong bộ nhớ. Nó không xác nhận các thành phần chỉ xuất hiện ở transport thật. Bổ sung test TCP/WebSocket khi ứng dụng phụ thuộc vào:

- Port binding, bind address và cấu hình server lifecycle.
- TLS, chứng thư, xác thực hoặc proxy.
- WebSocket path, HTTP upgrade, load balancer và ingress.
- Frame size, fragmentation, keepalive và connection timeout.
- Network disconnect, reconnect, session resumption hoặc transport-level backpressure.

Trong test TCP, dùng port 0 nếu transport hỗ trợ bind port động và lấy địa chỉ thực tế từ channel đã bind. Nếu dùng port cố định, tránh chạy nhiều test song song trên cùng port. Đóng server và requester sau mỗi test để không rò rỉ socket hoặc thread. Với WebSocket, dùng một URI test riêng và đóng client/server tương tự.

## 11. Lỗi kiểm thử thường gặp

| Lỗi | Vì sao test không đáng tin | Cách sửa |
|---|---|---|
| Mock RSocketRequester và verify route() được gọi | Không test encoding, metadata hoặc protocol | Có ít nhất một LocalTransport round-trip test |
| Chỉ gọi trực tiếp method @MessageMapping | Không test route mapping và argument resolution | Gửi request qua RSocketRequester |
| Chỉ test String codec | Không phát hiện lỗi JSON/CBOR và custom type | Test payload object thực tế |
| Dùng verify() không giới hạn thời gian | Build có thể treo vô hạn khi stream không kết thúc | Dùng verify(Duration) |
| Dùng Thread.sleep() để đợi response | Test chậm và dễ flaky | Dùng StepVerifier, latch/probe có timeout |
| Không dispose requester/server | Rò rỉ connection, event loop hoặc thread | Cleanup trong finally/@AfterEach |
| Dùng chung LocalTransport name khi chạy song song | Test có thể kết nối nhầm server | Tạo tên duy nhất cho mỗi test |
| Cho rằng send() xác nhận handler xử lý xong | Fire-and-Forget không có response nghiệp vụ | Dùng probe hoặc truy vấn trạng thái độc lập |
| Chỉ kiểm tra status code/exception message nội bộ | Test phụ thuộc chi tiết implementation | Assert hợp đồng lỗi do ứng dụng công bố |

## 12. Checklist trước khi merge

- Có unit test cho business logic độc lập với RSocket.
- Có LocalTransport test nối RSocketRequester tới RSocketMessageHandler thật.
- Đã test Request-Response và Request-Stream; các interaction khác được test nếu ứng dụng sử dụng.
- Route, payload, metadata và MIME type được xác nhận từ đầu đến cuối.
- Codec object thực tế được test, không chỉ String/byte[].
- Lỗi route, decode, metadata, handler và cancellation có assertion.
- StepVerifier có terminal expectation và timeout hữu hạn.
- @ConnectMapping được test nếu ứng dụng dùng setup data/metadata.
- Fire-and-Forget được xác nhận bằng probe nếu cần chứng minh business side effect.
- Requester và server được dispose sau test.
- Có ít nhất một transport integration test nếu production dùng TCP/WebSocket với cấu hình riêng.
- Test có thể chạy song song mà không chia sẻ port hoặc transport name.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework API — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Spring Framework API — RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)
- [RSocket Java — RSocketServer](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
