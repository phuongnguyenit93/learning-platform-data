# Dựng cặp ứng dụng RSocket Java để quan sát bốn mô hình tương tác

Trong bài thực hành này, bạn sẽ dựng hai tiến trình Java độc lập: một RSocket server nhận thông điệp và một RSocket client gửi yêu cầu. Hai tiến trình trao đổi dữ liệu qua TCP bằng bốn mô hình của RSocket: request-response, fire-and-forget, request-stream và request-channel. Bạn sẽ chạy kiểm thử cho handler, khởi động từng tiến trình, quan sát log và thử thay TCP bằng WebSocket.

RSocket phù hợp với giao tiếp bất đồng bộ, hai chiều và reactive. Một kết nối có thể mang nhiều luồng tương tác; mỗi route xác định thao tác mà server xử lý. Reactor cung cấp Mono cho kết quả không hoặc một phần tử và Flux cho một chuỗi phần tử, đồng thời truyền tín hiệu nhu cầu để điều tiết luồng.

## 1. Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

- Tạo project Maven gồm contract dùng chung, server và client.
- Cấu hình RSocket server lắng nghe trên TCP và tạo requester từ client.
- Cài đặt bốn handler với route riêng.
- Gửi một request-response, một fire-and-forget, một request-stream và một request-channel.
- Dùng StepVerifier kiểm tra kết quả và thứ tự phần tử ở tầng handler.
- Nhận biết sự khác nhau giữa việc gửi fire-and-forget và xác nhận nghiệp vụ.
- Quan sát vòng đời stream qua log, dừng ứng dụng và giải phóng cổng.

Mô hình triển khai:

~~~text
+--------------------------+             TCP :7000
| rsocket-client           |  ==================================>
| RSocketRequester         |  <==================================
|                          |             RSocket
|  request-response        |
|  fire-and-forget         |             +------------------------+
|  request-stream          |             | rsocket-server         |
|  request-channel         |             | @MessageMapping        |
+--------------------------+             | Mono / Flux handlers   |
                                         +------------------------+
~~~

## 2. Chuẩn bị môi trường

Sử dụng JDK 21 và Maven 3.9 trở lên. Có thể kiểm tra bằng:

~~~bash
java -version
mvn -version
~~~

Ví dụ trong bài cố định Spring Boot 3.4.2, Java 21 và phiên bản thư viện Reactor do Spring Boot quản lý. Việc ghim phiên bản giúp cả nhóm chạy cùng một cấu hình. Khi nâng Spring Boot, hãy nâng phiên bản ở POM gốc rồi chạy lại toàn bộ kiểm thử.

TCP server sử dụng cổng 7000. Hãy bảo đảm cổng này chưa bị tiến trình khác chiếm và client có thể kết nối tới localhost.

## 3. Tạo cấu trúc project

Tạo thư mục rsocket-lab với cấu trúc sau:

~~~text
rsocket-lab/
├── pom.xml
├── rsocket-contract/
│   ├── pom.xml
│   └── src/main/java/dev/rsocketlab/contract/Messages.java
├── rsocket-server/
│   ├── pom.xml
│   ├── src/main/java/dev/rsocketlab/server/ServerApplication.java
│   ├── src/main/java/dev/rsocketlab/server/GreetingController.java
│   ├── src/main/resources/application.yml
│   └── src/test/java/dev/rsocketlab/server/GreetingControllerTest.java
└── rsocket-client/
    ├── pom.xml
    ├── src/main/java/dev/rsocketlab/client/ClientApplication.java
    ├── src/main/java/dev/rsocketlab/client/RSocketDemoRunner.java
    └── src/main/resources/application.yml
~~~

Contract chứa các kiểu dữ liệu được serialize qua mạng. Server và client phụ thuộc vào contract để tránh định nghĩa hai bản DTO có thể lệch nhau.

### 3.1. POM gốc

Tạo file pom.xml ở thư mục rsocket-lab:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.rsocketlab</groupId>
    <artifactId>rsocket-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>21</java.version>
    </properties>

    <modules>
        <module>rsocket-contract</module>
        <module>rsocket-server</module>
        <module>rsocket-client</module>
    </modules>
</project>
~~~

POM gốc quản lý Spring Boot và Java cho cả ba module. Không đặt plugin đóng gói Spring Boot ở đây vì contract chỉ là thư viện JAR, không phải ứng dụng có main class.

### 3.2. Module contract

File rsocket-contract/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.rsocketlab</groupId>
        <artifactId>rsocket-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>rsocket-contract</artifactId>
</project>
~~~

File rsocket-contract/src/main/java/dev/rsocketlab/contract/Messages.java:

~~~java
package dev.rsocketlab.contract;

import java.time.Instant;

public final class Messages {

    private Messages() {
    }

    public record GreetingRequest(String name) {
    }

    public record StreamRequest(String name, int count) {
    }

    public record ChannelEvent(String name, int sequence) {
    }

    public record GreetingReply(String message, int sequence, Instant createdAt) {
    }
}
~~~

Các record là payload của bài lab:

| Kiểu dữ liệu | Dùng ở đâu | Ý nghĩa |
|---|---|---|
| GreetingRequest | Request-response, fire-and-forget | Một lời chào đơn |
| StreamRequest | Request-stream | Tên và số phần tử server cần phát |
| ChannelEvent | Request-channel | Một sự kiện đầu vào của client |
| GreetingReply | Các response có dữ liệu | Nội dung, số thứ tự và thời điểm tạo |

Ứng dụng dùng JSON để mã hóa record. Trường createdAt giúp quan sát thời điểm server tạo từng phần tử; đây không phải đồng hồ dùng để đo độ trễ mạng chính xác.

## 4. Xây dựng RSocket server

### 4.1. Khai báo dependency

File rsocket-server/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.rsocketlab</groupId>
        <artifactId>rsocket-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>rsocket-server</artifactId>

    <dependencies>
        <dependency>
            <groupId>dev.rsocketlab</groupId>
            <artifactId>rsocket-contract</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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

spring-boot-starter-rsocket cung cấp tích hợp RSocket của Spring. spring-boot-starter-json cung cấp bộ mã hóa và giải mã JSON. spring-boot-starter-test và reactor-test chỉ phục vụ kiểm thử.

### 4.2. Điểm khởi chạy

File rsocket-server/src/main/java/dev/rsocketlab/server/ServerApplication.java:

~~~java
package dev.rsocketlab.server;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServerApplication.class, args);
    }
}
~~~

### 4.3. Cấu hình transport TCP

File rsocket-server/src/main/resources/application.yml:

~~~yaml
spring:
  application:
    name: rsocket-server
  rsocket:
    server:
      transport: tcp
      port: 7000

logging:
  level:
    dev.rsocketlab: INFO
    io.rsocket: INFO
    org.springframework.messaging.rsocket: DEBUG
~~~

Server lắng nghe RSocket trực tiếp trên TCP cổng 7000. Đây là cổng RSocket, không phải HTTP endpoint. Khi client kết nối bằng TCP, nó không gửi HTTP request tới cổng này.

### 4.4. Cài đặt bốn handler

File rsocket-server/src/main/java/dev/rsocketlab/server/GreetingController.java:

~~~java
package dev.rsocketlab.server;

import dev.rsocketlab.contract.Messages.ChannelEvent;
import dev.rsocketlab.contract.Messages.GreetingReply;
import dev.rsocketlab.contract.Messages.GreetingRequest;
import dev.rsocketlab.contract.Messages.StreamRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.time.Instant;

@Controller
public class GreetingController {

    private static final Logger log =
            LoggerFactory.getLogger(GreetingController.class);

    @MessageMapping("greeting.request-response")
    public Mono<GreetingReply> requestResponse(GreetingRequest request) {
        return Mono.fromSupplier(() ->
                        reply(request.name(), 1, "request-response"))
                .doOnSuccess(reply ->
                        log.info("request-response completed for name={}",
                                request.name()))
                .doOnError(error ->
                        log.error("request-response failed", error));
    }

    @MessageMapping("greeting.fire-and-forget")
    public Mono<Void> fireAndForget(GreetingRequest request) {
        return Mono.fromRunnable(() ->
                        log.info("fire-and-forget received for name={}",
                                request.name()))
                .doOnError(error ->
                        log.error("fire-and-forget handler failed", error));
    }

    @MessageMapping("greeting.request-stream")
    public Flux<GreetingReply> requestStream(StreamRequest request) {
        if (request.count() < 1 || request.count() > 10) {
            return Flux.error(
                    new IllegalArgumentException("count must be between 1 and 10"));
        }

        return Flux.range(1, request.count())
                .delayElements(Duration.ofMillis(250))
                .map(sequence ->
                        reply(request.name(), sequence, "request-stream"))
                .doOnSubscribe(subscription ->
                        log.info("request-stream started for name={}, count={}",
                                request.name(), request.count()))
                .doOnComplete(() ->
                        log.info("request-stream completed for name={}",
                                request.name()))
                .doOnError(error ->
                        log.error("request-stream failed", error))
                .doFinally(signal ->
                        log.info("request-stream finished with signal={}", signal));
    }

    @MessageMapping("greeting.request-channel")
    public Flux<GreetingReply> requestChannel(Flux<ChannelEvent> events) {
        return events
                .concatMap(event ->
                        Mono.delay(Duration.ofMillis(100))
                                .map(ignored ->
                                        reply(event.name(), event.sequence(),
                                                "request-channel")))
                .doOnSubscribe(subscription ->
                        log.info("request-channel started"))
                .doOnComplete(() ->
                        log.info("request-channel completed"))
                .doOnError(error ->
                        log.error("request-channel failed", error))
                .doFinally(signal ->
                        log.info("request-channel finished with signal={}", signal));
    }

    private GreetingReply reply(String name, int sequence, String mode) {
        return new GreetingReply(
                "Xin chào " + name + " (" + mode + ")",
                sequence,
                Instant.now());
    }
}
~~~

Mỗi annotation MessageMapping gắn một route với một handler. Client phải gửi đúng route, kể cả dấu chấm và thứ tự từ.

| Route | Kiểu handler | Mô hình | Hành vi |
|---|---|---|---|
| greeting.request-response | Mono<GreetingReply> | Request-response | Nhận một request, trả một reply |
| greeting.fire-and-forget | Mono<Void> | Fire-and-forget | Nhận payload và xử lý log, không trả payload |
| greeting.request-stream | Flux<GreetingReply> | Request-stream | Nhận một request, phát nhiều reply |
| greeting.request-channel | Flux<GreetingReply> nhận Flux<ChannelEvent> | Request-channel | Nhận một luồng sự kiện và phát một luồng reply |

Ở request-channel, client có thể tiếp tục gửi sự kiện trong khi server đang phát kết quả. concatMap xử lý từng sự kiện theo thứ tự và chờ tác vụ của sự kiện trước hoàn tất rồi mới xử lý sự kiện tiếp theo. Cách viết này làm rõ thứ tự và tránh chạy đồng thời không giới hạn trong bài lab.

Request-stream giới hạn count từ 1 đến 10 để đầu vào thử nghiệm có phạm vi rõ ràng. delayElements làm chậm từng phần tử để bạn quan sát stream; trong ứng dụng thật, khoảng trễ thường đến từ I/O hoặc nghiệp vụ thay vì một bộ hẹn giờ giả lập.

## 5. Kiểm thử handler ở server

File rsocket-server/src/test/java/dev/rsocketlab/server/GreetingControllerTest.java:

~~~java
package dev.rsocketlab.server;

import dev.rsocketlab.contract.Messages.ChannelEvent;
import dev.rsocketlab.contract.Messages.GreetingRequest;
import dev.rsocketlab.contract.Messages.StreamRequest;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingControllerTest {

    private final GreetingController controller = new GreetingController();

    @Test
    void requestResponseReturnsOneReply() {
        StepVerifier.create(
                        controller.requestResponse(new GreetingRequest("Lan")))
                .assertNext(reply -> {
                    assertThat(reply.message()).contains("Lan");
                    assertThat(reply.sequence()).isEqualTo(1);
                    assertThat(reply.createdAt()).isNotNull();
                })
                .verifyComplete();
    }

    @Test
    void fireAndForgetHandlerCompletesWithoutAReply() {
        StepVerifier.create(
                        controller.fireAndForget(new GreetingRequest("Minh")))
                .verifyComplete();
    }

    @Test
    void requestStreamEmitsTheRequestedNumberOfReplies() {
        StepVerifier.create(
                        controller.requestStream(new StreamRequest("An", 3)))
                .assertNext(reply -> assertThat(reply.sequence()).isEqualTo(1))
                .assertNext(reply -> assertThat(reply.sequence()).isEqualTo(2))
                .assertNext(reply -> assertThat(reply.sequence()).isEqualTo(3))
                .verifyComplete();
    }

    @Test
    void requestStreamRejectsAnInvalidCount() {
        StepVerifier.create(
                        controller.requestStream(new StreamRequest("An", 0)))
                .expectError(IllegalArgumentException.class)
                .verify();
    }

    @Test
    void requestChannelReturnsOneReplyPerInputInOrder() {
        Flux<ChannelEvent> events = Flux.just(
                new ChannelEvent("Lan", 1),
                new ChannelEvent("Minh", 2),
                new ChannelEvent("An", 3));

        StepVerifier.create(controller.requestChannel(events))
                .assertNext(reply -> assertThat(reply.sequence()).isEqualTo(1))
                .assertNext(reply -> assertThat(reply.sequence()).isEqualTo(2))
                .assertNext(reply -> assertThat(reply.sequence()).isEqualTo(3))
                .verifyComplete();
    }
}
~~~

StepVerifier đăng ký vào Publisher và kiểm tra các tín hiệu theo thứ tự. Các test này kiểm tra logic reactive của handler; chúng chưa mở socket và chưa xác minh quá trình serialize payload qua mạng. Việc chạy cặp tiến trình ở phần sau là bước kiểm tra end-to-end của bài thực hành.

## 6. Xây dựng RSocket client

### 6.1. Khai báo dependency

File rsocket-client/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.rsocketlab</groupId>
        <artifactId>rsocket-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>rsocket-client</artifactId>

    <dependencies>
        <dependency>
            <groupId>dev.rsocketlab</groupId>
            <artifactId>rsocket-contract</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
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

### 6.2. Điểm khởi chạy client

File rsocket-client/src/main/java/dev/rsocketlab/client/ClientApplication.java:

~~~java
package dev.rsocketlab.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(ClientApplication.class, args);
    }
}
~~~

### 6.3. Cấu hình đích kết nối

File rsocket-client/src/main/resources/application.yml:

~~~yaml
spring:
  application:
    name: rsocket-client
  main:
    web-application-type: none

demo:
  rsocket:
    host: localhost
    port: 7000

logging:
  level:
    dev.rsocketlab: INFO
    io.rsocket: INFO
~~~

Client là ứng dụng dòng lệnh, không cần HTTP server. Host và port được đọc từ cấu hình để có thể đổi đích kết nối khi chạy ở môi trường khác.

### 6.4. Tạo requester và gọi bốn route

File rsocket-client/src/main/java/dev/rsocketlab/client/RSocketDemoRunner.java:

~~~java
package dev.rsocketlab.client;

import dev.rsocketlab.contract.Messages.ChannelEvent;
import dev.rsocketlab.contract.Messages.GreetingReply;
import dev.rsocketlab.contract.Messages.GreetingRequest;
import dev.rsocketlab.contract.Messages.StreamRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.env.Environment;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

import java.time.Duration;

@Component
public class RSocketDemoRunner implements CommandLineRunner {

    private static final Logger log =
            LoggerFactory.getLogger(RSocketDemoRunner.class);
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(10);

    private final RSocketRequester requester;

    public RSocketDemoRunner(
            RSocketRequester.Builder builder,
            Environment environment) {

        String host = environment.getProperty(
                "demo.rsocket.host", "localhost");
        int port = environment.getProperty(
                "demo.rsocket.port", Integer.class, 7000);

        this.requester = builder.tcp(host, port);
    }

    @Override
    public void run(String... args) {
        requestResponse();
        fireAndForget();
        requestStream();
        requestChannel();
    }

    private void requestResponse() {
        log.info("=== REQUEST-RESPONSE ===");

        requester.route("greeting.request-response")
                .data(new GreetingRequest("Lan"))
                .retrieveMono(GreetingReply.class)
                .doOnNext(reply -> log.info("RR reply: {}", reply))
                .block(REQUEST_TIMEOUT);
    }

    private void fireAndForget() {
        log.info("=== FIRE-AND-FORGET ===");

        requester.route("greeting.fire-and-forget")
                .data(new GreetingRequest("Minh"))
                .send()
                .block(REQUEST_TIMEOUT);

        log.info("FNF send completed locally; inspect the server log");
    }

    private void requestStream() {
        log.info("=== REQUEST-STREAM ===");

        requester.route("greeting.request-stream")
                .data(new StreamRequest("An", 5))
                .retrieveFlux(GreetingReply.class)
                .doOnNext(reply -> log.info("STREAM item: {}", reply))
                .blockLast(REQUEST_TIMEOUT);
    }

    private void requestChannel() {
        log.info("=== REQUEST-CHANNEL ===");

        Flux<ChannelEvent> outgoingEvents = Flux.range(1, 5)
                .map(sequence -> new ChannelEvent("Binh", sequence))
                .delayElements(Duration.ofMillis(150));

        requester.route("greeting.request-channel")
                .data(outgoingEvents, ChannelEvent.class)
                .retrieveFlux(GreetingReply.class)
                .doOnNext(reply -> log.info("CHANNEL item: {}", reply))
                .blockLast(REQUEST_TIMEOUT);
    }
}
~~~

Spring Boot cung cấp RSocketRequester.Builder. Builder mở kết nối TCP tới host và port đã cấu hình. Mỗi lần gọi route tạo một request spec; data đặt payload đầu vào, còn retrieveMono, retrieveFlux hoặc send xác định cách client nhận kết quả.

Điểm cần quan sát ở fire-and-forget: send() không có kiểu reply và không chờ một xác nhận nghiệp vụ từ handler server. Khi Mono<Void> hoàn tất ở client, điều đó cho biết thao tác gửi phía client đã hoàn tất theo API; nó không chứng minh công việc phía server đã hoàn thành. Trong bài lab, hãy kiểm tra log server để thấy handler đã nhận payload.

Ở request-channel, data nhận một Publisher cùng kiểu phần tử. Client phát năm ChannelEvent cách nhau 150 ms; server xử lý tuần tự và phát lại năm GreetingReply. Hai chiều dữ liệu cùng tồn tại trong một tương tác.

## 7. Build và chạy hai tiến trình

Mở terminal thứ nhất tại thư mục rsocket-lab và đóng gói toàn bộ module:

~~~bash
mvn clean verify
~~~

Lệnh này biên dịch contract, server, client và chạy test của server. Khi build thành công, hai ứng dụng có thể chạy từ executable JAR.

Khởi động server trước:

~~~bash
java -jar rsocket-server/target/rsocket-server-1.0.0-SNAPSHOT.jar
~~~

Giữ terminal server mở. Khi server đã khởi động và lắng nghe cổng 7000, mở terminal thứ hai tại thư mục rsocket-lab:

~~~bash
java -jar rsocket-client/target/rsocket-client-1.0.0-SNAPSHOT.jar
~~~

Client lần lượt gọi bốn route rồi kết thúc. Server tiếp tục chạy để nhận kết nối khác.

### 7.1. Kết quả mong đợi

Log client cần thể hiện các nhóm sau:

- REQUEST-RESPONSE: một dòng RR reply.
- FIRE-AND-FORGET: thông báo gửi hoàn tất ở phía client.
- REQUEST-STREAM: năm dòng STREAM item, sequence từ 1 đến 5.
- REQUEST-CHANNEL: năm dòng CHANNEL item, sequence từ 1 đến 5.

Log server cần có request-response completed, fire-and-forget received, request-stream started/completed và request-channel started/completed. Với fire-and-forget, log server là bằng chứng bài lab cho thấy handler đã chạy.

Thứ tự thời gian giữa log client và server có thể xen kẽ do hai tiến trình chạy độc lập. Hãy đối chiếu route và sequence thay vì yêu cầu mọi dòng log xuất hiện theo một thứ tự toàn cục cố định.

## 8. Thử transport WebSocket

TCP phù hợp cho kết nối dịch vụ Java trực tiếp. Khi cần đi qua hạ tầng HTTP hoặc reverse proxy hỗ trợ WebSocket, RSocket có thể chạy trên WebSocket. Server cần cấu hình transport và mapping path.

Tạo file rsocket-server/src/main/resources/application-ws.yml:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
      port: 8080
~~~

Khởi động server với profile ws:

~~~bash
java -jar rsocket-server/target/rsocket-server-1.0.0-SNAPSHOT.jar --spring.profiles.active=ws
~~~

Trong RSocketDemoRunner, thay dòng tạo requester TCP bằng kết nối WebSocket:

~~~java
this.requester = builder
        .websocket(java.net.URI.create("ws://localhost:8080/rsocket"))
        .block(Duration.ofSeconds(5));
~~~

Phương thức websocket trả về Mono<RSocketRequester>, vì vậy ví dụ chờ tối đa năm giây để thiết lập kết nối. Giữ nguyên các hàm gọi route; payload và handler không phụ thuộc transport. Build lại client rồi chạy như phần trước.

Khi chuyển lại TCP, khôi phục builder.tcp(host, port), dừng server WebSocket và khởi động server với cấu hình mặc định. Một server instance trong bài lab chỉ nghe một transport tại một thời điểm.

## 9. Quan sát và chẩn đoán

### 9.1. Quan sát vòng đời tương tác

Các log trong GreetingController ghi nhận lúc handler bắt đầu, hoàn tất, lỗi hoặc kết thúc do tín hiệu khác. Với stream và channel, doFinally có thể nhận các tín hiệu như ON_COMPLETE, ON_ERROR hoặc CANCEL. CANCEL thường xuất hiện khi phía nhận hủy subscription hoặc kết nối bị đóng trước khi stream hoàn tất.

Để xem log RSocket chi tiết hơn, tạm tăng mức log trong application.yml:

~~~yaml
logging:
  level:
    io.rsocket: DEBUG
    org.springframework.messaging.rsocket: TRACE
~~~

Mức TRACE có thể tạo nhiều log; chỉ bật trong lúc điều tra và đưa về INFO sau khi xong.

### 9.2. Đọc hiện tượng theo mô hình

| Hiện tượng | Nơi kiểm tra trước | Nguyên nhân thường gặp |
|---|---|---|
| Client báo connection refused | Host, port, trạng thái server | Server chưa chạy, sai cổng hoặc cổng bị chặn |
| Không tìm thấy handler | Route ở client và MessageMapping ở server | Sai route hoặc controller không được Spring scan |
| Payload không giải mã được | Dependency JSON và kiểu DTO | Thiếu codec, kiểu dữ liệu hai phía không tương thích |
| Request-response không có reply | Log handler và lỗi client | Handler lỗi, timeout hoặc route không khớp |
| Stream dừng sớm | Log doFinally và phía hủy subscription | Timeout, lỗi giữa luồng hoặc client kết thúc sớm |
| Fire-and-forget không thấy reply | Log server | FNF không có response payload theo thiết kế |
| Request-channel thiếu phần tử | Sequence ở client/server và log lỗi | Publisher đầu vào kết thúc sớm, bị cancel hoặc xử lý lỗi |

Không dùng việc client không nhận được reply để kết luận rằng fire-and-forget thất bại. Mô hình này không định nghĩa response payload. Nếu nghiệp vụ cần xác nhận đã ghi dữ liệu hoặc đã xử lý xong, hãy thiết kế một route request-response riêng, một event kết quả hoặc một cơ chế trạng thái có thể truy vấn.

### 9.3. Những điều cần đo khi đưa vào ứng dụng thật

Bài lab dùng log để dễ quan sát. Một hệ thống vận hành thực tế nên theo dõi ít nhất:

- Số kết nối đang hoạt động và số lần kết nối/ngắt kết nối.
- Số request theo route, tỷ lệ lỗi và thời gian xử lý.
- Số phần tử stream phát ra, thời gian stream sống và số lần bị cancel.
- Áp lực bộ nhớ, CPU, event loop và các thao tác blocking.
- Timeout, retry và số lần reconnect ở phía client.

Gắn route hoặc loại tương tác làm nhãn metric; tránh gắn giá trị payload như tên người dùng hoặc nội dung message vì cardinality cao và có thể chứa dữ liệu riêng tư. Không ghi toàn bộ payload vào log nếu chưa có lý do nghiệp vụ và quy tắc bảo vệ dữ liệu.

## 10. Dọn dẹp sau thực hành

1. Dừng client nếu tiến trình vẫn còn chạy bằng Ctrl+C.
2. Dừng server bằng Ctrl+C để Spring đóng context và giải phóng listener.
3. Nếu đã thử WebSocket, dừng tiến trình đang nghe cổng 8080.
4. Kiểm tra cổng 7000 hoặc 8080 đã được giải phóng trước khi chạy lại. Trên Windows có thể dùng Get-NetTCPConnection -LocalPort 7000; trên Linux/macOS có thể dùng lsof -i :7000.
5. Khi muốn xóa các sản phẩm build để làm lại từ đầu, chạy mvn clean tại thư mục gốc. Lệnh này xóa thư mục target của các module Maven.

Project không tạo cơ sở dữ liệu hoặc dữ liệu bền vững. Các thông điệp chỉ được xử lý trong bộ nhớ và ghi log.

## 11. Tiêu chí nghiệm thu

Đánh dấu hoàn thành khi tất cả điều kiện sau đều đúng:

- [ ] JDK 21 và Maven hoạt động; mvn clean verify kết thúc thành công.
- [ ] Project có đủ ba module contract, server và client; hai ứng dụng dùng chung DTO từ contract.
- [ ] Server khởi động trên TCP cổng 7000 và client kết nối được.
- [ ] Request-response trả đúng một GreetingReply.
- [ ] Fire-and-forget gửi được payload và log server xác nhận handler đã nhận; client không chờ reply nghiệp vụ.
- [ ] Request-stream phát đúng năm phần tử theo sequence 1 đến 5.
- [ ] Request-channel gửi năm sự kiện và nhận năm reply theo đúng thứ tự.
- [ ] Các test StepVerifier đều pass, bao gồm trường hợp count không hợp lệ.
- [ ] Người học giải thích được vì sao Mono<Void> ở fire-and-forget không phải xác nhận nghiệp vụ từ server.
- [ ] Có thể đổi sang WebSocket bằng cấu hình transport, mapping path và requester tương ứng.
- [ ] Đã dừng hai tiến trình và giải phóng cổng sau thực hành.

## 12. Câu hỏi tự kiểm tra

1. Vì sao request-response dùng Mono còn request-stream dùng Flux?
2. Điều gì khiến request-channel khác request-stream khi nhìn từ hướng dữ liệu client gửi lên server?
3. Khi client gọi send() cho fire-and-forget, client có thể khẳng định nghiệp vụ phía server đã ghi thành công hay chưa? Giải thích.
4. concatMap trong handler request-channel đang bảo đảm đặc tính gì? Nếu thay bằng flatMap, điều gì có thể thay đổi?
5. Khi chuyển từ TCP sang WebSocket, phần nào của ứng dụng phải đổi và phần nào có thể giữ nguyên?
6. Vì sao test StepVerifier trực tiếp handler chưa thay thế được kiểm thử end-to-end qua socket?

Hãy chạy lại bài lab sau khi chủ động đổi host/port, thay số lượng phần tử stream và hủy client giữa chừng. Quan sát log doFinally để liên hệ tín hiệu reactive với vòng đời kết nối thực tế.
