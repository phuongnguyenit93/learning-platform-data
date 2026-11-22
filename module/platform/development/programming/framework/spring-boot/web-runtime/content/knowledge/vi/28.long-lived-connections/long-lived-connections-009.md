# Giới hạn kích thước thông điệp, hàng đợi gửi và máy khách đọc chậm

> **Module:** Spring Boot - web-runtime · **Nhóm:** Kết nối dài. Bài tập trung vào **WebSocket, STOMP over WebSocket và SSE** trong Spring Boot: bảo vệ hệ thống khỏi payload quá lớn, hàng đợi outbound tăng vô hạn và máy khách đọc chậm (slow consumer). Với Spring MVC/STOMP, ba API cần hiểu rõ là `setMessageSizeLimit`, `setSendBufferSizeLimit` và `setSendTimeLimit`. Bài cũng phân biệt raw WebSocket, WebFlux/Reactor backpressure, executor queue và network buffers. Ví dụ sử dụng **Java 17+**, **Spring Boot 4.1.2**, Maven.

## Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt WebSocket **frame**, WebSocket **message**, STOMP **message**, payload nghiệp vụ, và biết rằng byte size không đồng nhất với độ dài chuỗi Java.
2. Giải thích **slow consumer** và vì sao dữ liệu sinh nhanh hơn tốc độ đọc làm tăng queue, latency, RAM, GC và khả năng từ chối phục vụ.
3. Cấu hình giới hạn inbound STOMP message, outbound per-session send buffer và send time; biết những giới hạn này **không phải** frame limit, task queue hay hard timeout.
4. Sử dụng `configureClientOutboundChannel` để quản lý executor tasks và hiểu trade-off core/max threads với queue capacity.
5. Chọn backpressure, coalescing, bounded buffer, drop có kiểm soát, disconnect, durable replay theo loại dữ liệu.
6. Chạy được một ứng dụng Spring MVC STOMP/WebSocket nhỏ để quan sát giới hạn và thử burst; test client chậm với network shaping thay vì dựa vào phỏng đoán.
7. Biết khác biệt raw WebSocket `ConcurrentWebSocketSessionDecorator`, WebFlux `session.receive()/send()` và SSE `SseEmitter` / `Flux<ServerSentEvent>`.
8. Lập kế hoạch metrics, load test, bảo mật, quota và khôi phục sau reconnect cho hệ thống production.

## 1. Vì sao kết nối dài cần kiểm soát bộ đệm?

WebSocket giữ một kết nối hai chiều mở trong thời gian dài. SSE giữ một HTTP response stream mở để server gửi events. Hệ thống có thể có hàng trăm nghìn events phát tới nhiều sessions, không giống REST endpoint trả một response rồi kết thúc.

~~~text
Business events / upstream hot feed
          |
          v
       Publisher
          |
          v
     Broker / fanout
        /   |   \
       /    |    \
 client A  B     C
 nhanh   chậm   ngắt mạng
          |
       bytes chờ gửi
          |
       queue tăng dần -> memory pressure -> GC / mất kết nối
~~~

Một client có thể chậm vì mạng di động yếu, TCP receive window nhỏ, trình duyệt bị treo, thiết bị sleep, proxy chậm, CPU client tốn thời gian parse JSON hoặc browser không còn đọc đều. Dù nguyên nhân nào, server phải có **giới hạn tài nguyên per-client và toàn hệ thống**.

Giả sử một session cần nhận 800 KiB/s dữ liệu mới, nhưng thực tế kết nối chỉ truyền được 100 KiB/s, backlog tăng khoảng 700 KiB/s. Nếu phần dữ liệu dư thực sự đi vào một bộ đệm 512 KiB, phép tính lý tưởng cho thời gian đầy là khoảng 512/700 = **0,73 giây**. Đây chỉ là **mô hình**: còn thread scheduling, frame overhead, OS/TCP buffers, compression, các queue khác và timeouts.

Nếu 10.000 sessions được phép có buffer 512 KiB, trần logic chỉ riêng tầng đó gần **4,9 GiB**, chưa kể heap overhead và dữ liệu ở broker/executor. Tăng mọi giới hạn để tránh disconnect thường làm nguy cơ OOM tệ hơn.

### 1.1. Bốn kết quả có thể khi producer nhanh hơn consumer

- **Chặn/giảm upstream:** nguồn hỗ trợ demand/backpressure thì giảm phát khi downstream không theo kịp.
- **Buffer:** tạm giữ dữ liệu; chỉ chấp nhận nếu **bounded** và có chính sách khi đầy.
- **Bỏ/hợp nhất:** giữ snapshot mới nhất, drop oldest/latest hoặc sampling; chỉ cho loại dữ liệu được phép mất intermediate events.
- **Ngắt kết nối:** đóng client chậm, cho reconnect và lấy snapshot/replay từ durable store.

WebSocket đơn thuần không bảo đảm delivery/ACK exactly-once. Một lời gọi `send` thành công chưa chứng minh người dùng đã xem hoặc xử lý sự kiện.

## 2. Phải phân biệt frame, STOMP message và queue

~~~text
App object (ví dụ JSON)
   |
   +-- serialize UTF-8 bytes
   |
   +-- STOMP frame: command + headers + body + NUL
   |
   +-- WebSocket message / nhiều fragments
   |
   +-- WebSocket frames
   |
   +-- TLS/TCP -> mạng -> browser
~~~

| Lớp | Ví dụ giới hạn | Đơn vị | Điều không được suy diễn |
| --- | --- | --- | --- |
| Business payload | DTO/schema, JSON size, depth | bytes/objects | Không tự bound WebSocket frame |
| STOMP inbound message | `setMessageSizeLimit` | bytes đã ghép | Không tự bound mọi HTTP request |
| WebSocket frame/message | Tomcat/Jetty/Netty settings | bytes | Không đồng nhất với STOMP aggregate |
| Spring per-session outbound | `setSendBufferSizeLimit` | bytes pending | Không phải global heap limit |
| Outbound thread pool | `clientOutboundChannel` executor queue | **tasks** | Không phải bytes per session |
| Socket/kernel | TCP send buffer/window | bytes | Không thay bằng một property STOMP |
| SSE stream | app event, HTTP response writes | bytes/event | Không dùng STOMP settings |

Một ký tự Unicode không luôn chiếm một byte. Ví dụ `"á"` thường chiếm 2 bytes UTF-8 nhưng Java `String.length()` có thể là 1; emoji có thể chiếm 4 bytes UTF-8. Thêm STOMP headers, JSON escaping và encoding overhead, nên quota ở message parser cần đo theo **bytes thật**.

### 2.1. STOMP over WebSocket có thể ghép các phần

STOMP SEND/MESSAGE không phải cùng khái niệm với WebSocket frame. Spring STOMP support có thể nhận STOMP message bị chia thành các WebSocket messages nhỏ rồi ghép để parse. Vì thế **giới hạn sau khi ghép** rất quan trọng. Một attacker gửi nhiều fragments nhỏ không được phép vượt tổng quota của message.

Giới hạn container cũng cần bật: một frame payload cực lớn có thể bị ngăn ở container trước khi tới STOMP decoder. Không được kết luận rằng `setMessageSizeLimit` kiểm soát mọi binary raw WebSocket, upload HTTP hay size sau khi dữ liệu giải nén.

## 3. Luồng STOMP trong Spring MVC

~~~text
WebSocket handshake /ws -> HTTP 101 Switching Protocols
          |
          v
       STOMP CONNECT / SEND / SUBSCRIBE
          |
          v
  StompSubProtocolHandler
          |
          v
    clientInboundChannel ---------> @MessageMapping
          |                            |
          |                            v
          +----------------------> brokerChannel
                                       |
                                       v
                                  simple broker
                                       |
                                       v
                              clientOutboundChannel
                                       |
                                       v
                            WebSocketSession send
                                       |
                                    browser
~~~

- `clientInboundChannel` xử lý messages từ clients qua executor.
- `brokerChannel` truyền messages từ application về broker.
- `clientOutboundChannel` đưa messages tới các sessions, có executor và queue độc lập.
- Simple broker lưu subscriptions trong memory, broadcast tới destinations; **không phải persistent log** để replay một cách tự động.
- Nếu dùng broker relay đến RabbitMQ/ActiveMQ, broker external có thêm flow control và durability tùy cấu hình, nhưng đoạn cuối broker→WebSocket client vẫn có slow-consumer problem.

## 4. Ba setting quan trọng của WebSocketTransportRegistration

Trong class `WebSocketMessageBrokerConfigurer`:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration r) {
    r.setMessageSizeLimit(32 * 1024);
    r.setSendBufferSizeLimit(256 * 1024);
    r.setSendTimeLimit(10_000);
    r.setTimeToFirstMessage(30_000);
}
~~~

Các giá trị trên là **ví dụ kiểm thử**, không phải preset cho mọi môi trường.

### 4.1. setMessageSizeLimit: quota inbound STOMP

`setMessageSizeLimit(32 * 1024)` là giới hạn bytes cho **incoming STOMP message được ghép** trước khi đưa vào application. Spring Framework STOMP có default thường là **64 KiB**; cần kiểm đúng phiên bản đang dùng.

- Một STOMP message có thể chứa headers/body và được phân mảnh trên nhiều WebSocket fragments.
- Message > limit có thể làm decoder báo lỗi, transport đóng session hoặc gửi STOMP ERROR tùy implementation.
- Sau WebSocket upgrade, lỗi không nhất thiết thể hiện thành HTTP 413.
- Spring có thể tự điều chỉnh tối thiểu kích thước WebSocket message để nhận các chunks STOMP, nhưng giới hạn container/framework còn độc lập.

Không thiết kế một payload đúng 32.768 byte và mong chắc chắn pass: STOMP headers/framing cũng có overhead. Phải test boundary cho encoding thực.

### 4.2. setSendBufferSizeLimit: pending bytes của một session

`setSendBufferSizeLimit(256 * 1024)` giới hạn số bytes của messages đang **phải chờ gửi** do session gửi chậm. Khi một thread đang gửi, các thread gửi tiếp không thể tùy tiện gửi đồng thời trên cùng session; Spring có thể buffer pending messages và xem xét overflow.

Khi vượt limit, Spring có thể clear state và cố đóng session. Việc đóng phụ thuộc transport/network, **không bảo đảm xảy ra ngay đúng thời điểm byte thứ 262.145 được sinh**.

Giới hạn **theo session** này không bao gồm toàn bộ:

- Tasks đang chờ trong `clientOutboundChannel` executor.
- Messages đang chờ ở custom publisher queue/sink.
- Data đang có trong broker relay.
- OS kernel send buffers, TLS buffers hoặc proxy buffering.

Nếu client có thể mở nhiều sessions, tổng memory risk vẫn tăng dù từng session được bound.

### 4.3. setSendTimeLimit: không phải hard timer cho mọi send

`setSendTimeLimit(10_000)` đặt thời hạn millisecond liên quan đến sending chậm. Theo Javadoc Spring, time limit được kiểm tra **khi có thêm attempts gửi**; nếu chỉ gửi một message rồi writer bị treo, không nhất thiết bị đóng ngay sau 10 giây khi chưa có message tiếp theo.

Do đó cần đồng thời:

- Socket/connector I/O timeout và idle timeout theo server.
- WebSocket ping/pong hoặc STOMP heartbeats.
- Monitoring age since last successful send.
- Chính sách đóng session và cleanup resources.

**Heartbeat không phải backpressure:** client còn trả heartbeat không chứng minh nó đã xử lý mọi event nghiệp vụ.

### 4.4. setTimeToFirstMessage

`setTimeToFirstMessage(30_000)` giới hạn thời gian sau khi WebSocket upgrade mà client chưa gửi STOMP frame đầu tiên. Chống giữ session rỗng lâu, không phải giới hạn băng thông hoặc message rate.

## 5. Executor queue là tầng khác với send buffer

Spring STOMP sử dụng executor cho inbound và outbound channels. Đặc biệt, `clientOutboundChannel` queue chứa **tasks chờ worker threads**, trong khi `sendBufferSizeLimit` nói về **bytes pending ở mỗi WebSocket session**.

~~~text
Simple broker
   |
   v
clientOutboundChannel executor
   +-- queue: task 1, task 2, task 3, ...
   |
   +-- worker threads
          |
          v
    one session send lock
          |
          +-- per-session pending message bytes
          |
          v
     connector/socket buffers
~~~

Một lỗi cấu hình phổ biến là đặt `corePoolSize=4` và `maxPoolSize=64` nhưng dùng executor queue gần như vô hạn. Java ThreadPoolExecutor có thể **xếp tasks vào queue** thay vì tăng threads vượt core, nên `maxPoolSize` không có hiệu quả mong muốn. Queue capacity, rejected tasks, active thread count và latency phải được đo thực.

### 5.1. Ví dụ configureClientOutboundChannel

~~~java
@Override
public void configureClientOutboundChannel(ChannelRegistration registration) {
    registration.taskExecutor()
            .corePoolSize(4)
            .maxPoolSize(8)
            .queueCapacity(200);
}
~~~

Đây là **fragment Java** trong WebSocketMessageBrokerConfigurer. `queueCapacity(200)` đếm **tasks**, không phải 200 bytes hay bảo đảm 200 messages đã được client nhận. Với queue bounded, executor có thể từ chối task khi quá tải; đừng che những lỗi này và tiếp tục báo delivered=true.

### 5.2. Vì sao tăng threads không giải quyết mọi slow client?

Nếu client có đường truyền chỉ 50 KiB/s còn bạn cố phát 500 KiB/s, thêm 100 outbound threads không tạo thêm băng thông cho client. Thậm chí việc đưa messages vào send buffer nhanh hơn có thể tăng memory/GC và đẩy bottleneck sang TCP/proxy.

Hãy xét **giảm producer rate, coalesce snapshots, bounded per-session buffer, disconnect/replay** trước khi chỉ tăng executor. Tuy nhiên nếu workload chủ yếu đợi I/O ngắn hạn và threads thật sự thiếu, tuning thread pool có thể giúp. Chọn qua đo latency/queue, không có một con số đúng cho mọi deployment.

## 6. Chính sách khi máy khách đọc chậm

| Chính sách | Ý nghĩa | Phù hợp | Không phù hợp |
| --- | --- | --- | --- |
| Backpressure upstream | Giảm phát theo downstream demand | Cold publisher, pipeline có demand | Hot broker hoàn toàn không tôn trọng demand |
| Bounded buffer | Giữ tạm một số events/bytes hữu hạn | Burst ngắn | Producer mãi nhanh hơn consumer |
| Drop oldest | Bỏ events cũ để nhường events mới | Telemetry có thể lấy snapshot | Audit/payment |
| Drop latest | Bỏ events đến khi queue đầy | Một số sampling/batching | Luồng cần trạng thái mới nhất tức thời |
| Keep latest / coalescing | Mỗi object giữ trạng thái cuối | Bảng giá, dashboard | Event transitions bắt buộc đầy đủ |
| Disconnect | Đóng slow client để bảo vệ server | Fanout realtime có reconnect | Workflow không có replay |
| Durable queue/replay | Lưu bền, client dùng cursor/ACK | Đơn hàng, thanh toán, audit | Mức nhỏ không cần persistence |
| Admission control | Từ chối publish/kết nối khi vượt quota | Bảo vệ toàn server | Không phải hệ thống có thể bỏ qua errors |

### 6.1. Coalescing có điều kiện

Ví dụ một dashboard nhận 1.000 updates/s cho cùng một sensor. Nếu browser chỉ vẽ 10 lần/s, có thể giữ **update cuối cùng trong mỗi 100 ms** hoặc chỉ một bản mới nhất per sensor. Kết quả hiển thị sẽ mới mà không cần hàng nghìn pending DOM updates.

Ngược lại, một chuỗi nghiệp vụ `order-created → paid → shipped` không được bỏ `paid` mà không có cơ chế state reconciliation và durable events. Cần phân biệt **state snapshots** và **event log**.

### 6.2. Sequence, gap và replay

~~~json
{"seq":101,"asset":"A","value":12}
{"seq":104,"asset":"A","value":14}
~~~

Client biết thiếu 102/103 nếu sequence phải liên tục. Sau reconnect, nó có thể gọi REST API lấy snapshot mới, hoặc yêu cầu replay từ `lastSeenSeq` nếu backend có durable log. WebSocket/STOMP SUBSCRIBE **không tự phát lại** toàn bộ events bị mất.

**Application ACK** khác với việc socket send được gọi. Khi tính đúng đắn nghiệp vụ quan trọng, áp dụng transaction/outbox/offset/idempotency phù hợp.

### 6.3. Fairness và quotas

Giới hạn theo nhiều chiều:

- Max active connections theo IP, user, tenant.
- Số destinations/subscriptions mỗi session.
- Inbound message bytes, messages/s, burst allowance.
- Outbound bytes/s, fanout factor, pending bytes/session và global memory.
- Tổng thời gian connection sống, idle timeouts và reconnect rate.
- Chi phí decode/serialize/compression và max JSON nesting/array length.

Một attacker có thể gửi 100.000 messages chỉ 10 bytes: `setMessageSizeLimit` không thay message rate limit. Nếu attacker tạo hàng nghìn sessions, chỉ per-session quota không đủ; cần global/user quota.

## 7. Dự án đầy đủ: Spring Boot 4.1.2 STOMP/WebSocket

Lab có:

- HTTP upgrade WebSocket tại `/ws`.
- STOMP SEND tới `/app/echo`, Spring gửi reply đến `/topic/echo`.
- Inbound STOMP max **32 KiB**.
- Per-session send buffer max **256 KiB**.
- Send time limit **10 giây**, time to first message **30 giây**.
- Outbound executor queue **200 tasks**.
- Endpoint `POST /lab/burst` gửi tối đa 200 events x 8 KiB ASCII.
- HTML browser WebSocket/STOMP client tối giản.

Đây là **lab trên localhost**, không có authentication/authorization; không mở public internet hoặc gửi dữ liệu nhạy cảm.

### 7.1. File tree

~~~text
slow-client-lab/
  pom.xml
  src/main/java/com/example/slowclient/
    SlowClientApplication.java
    WebSocketConfig.java
    EchoStompController.java
    BurstController.java
  src/main/resources/
    application.properties
    static/demo.html
~~~

### 7.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>slow-client-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
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

`spring-boot-starter-websocket` bản Boot 4.1.2 tích hợp Spring MVC WebSocket support. Không kết hợp cấu hình này với một WebFlux server rồi mong Servlet STOMP transport settings vẫn áp dụng.

### 7.3. SlowClientApplication.java

~~~java
package com.example.slowclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SlowClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(SlowClientApplication.class, args);
    }
}
~~~

### 7.4. WebSocketConfig.java

~~~java
package com.example.slowclient;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration(proxyBeanMethods = false)
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("http://localhost:8080");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {
        registration.setMessageSizeLimit(32 * 1024);
        registration.setSendBufferSizeLimit(256 * 1024);
        registration.setSendTimeLimit(10_000);
        registration.setTimeToFirstMessage(30_000);
    }

    @Override
    public void configureClientOutboundChannel(
            ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(4)
                .maxPoolSize(8)
                .queueCapacity(200);
    }
}
~~~

**Phạm vi cấu hình:**

- `/ws` là endpoint upgrade, không phải STOMP destination.
- STOMP SEND `/app/echo` được xử lý bởi method Spring; `/topic/echo` được simple broker chuyển tới subscribers.
- `setMessageSizeLimit` kiểm STOMP message đã ghép, không ảnh hưởng HTTP body size của `/lab/burst`.
- `setSendBufferSizeLimit` kiểm per-session pending bytes; `queueCapacity(200)` kiểm executor tasks.
- `setSendTimeLimit` không phải hard timeout cho mọi send.
- `setAllowedOrigins("http://localhost:8080")` là chính sách same-origin **cố định cho lab**. Origin không thay authentication; non-browser client có thể giả mạo.

### 7.5. EchoStompController.java

~~~java
package com.example.slowclient;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class EchoStompController {
    @MessageMapping("/echo")
    @SendTo("/topic/echo")
    public String echo(String message) {
        return "echo: " + message;
    }
}
~~~

Một client gửi STOMP message với destination `/app/echo` và `content-type:text/plain` được mapping đến method `echo`; return được gửi tới `/topic/echo`. Trong ứng dụng thật, không echo token, PII hoặc payload không được kiểm schema; subscriptions phải có authorization theo user/tenant.

### 7.6. BurstController.java

~~~java
package com.example.slowclient;

import org.springframework.http.ResponseEntity;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BurstController {

    private final SimpMessagingTemplate template;

    public BurstController(SimpMessagingTemplate template) {
        this.template = template;
    }

    @PostMapping("/lab/burst")
    public ResponseEntity<String> burst(
            @RequestParam(defaultValue = "10") int count,
            @RequestParam(defaultValue = "128") int bytes) {
        if (count < 1 || count > 200 || bytes < 1 || bytes > 8192) {
            return ResponseEntity.badRequest().body(
                    "count must be 1..200 and bytes must be 1..8192");
        }

        String body = "x".repeat(bytes);
        for (int i = 1; i <= count; i++) {
            template.convertAndSend("/topic/echo", i + ":" + body);
        }

        return ResponseEntity.accepted().body(
                "submitted " + count + " messages");
    }
}
~~~

Code ràng buộc đầu vào để tránh một HTTP request lab kích hoạt một vòng vô hạn. `bytes` là số chữ `x` ASCII, cộng prefix `i:` và STOMP framing còn có overhead. HTTP **202 Accepted** trong demo **không có nghĩa** mọi subscribers đã nhận bytes hoặc ACK event: nó chỉ là kết quả của vòng đưa messages vào broker không gặp lỗi đồng bộ.

Nếu exposed public, endpoint này là một điểm khuếch đại fanout và có thể gây DoS; production phải có auth, quotas, rate limit và không cho người dùng yêu cầu tùy ý số lượng/payload.

### 7.7. application.properties

~~~properties
server.port=8080

# Lab không tích hợp authentication, không expose internet.
logging.level.org.springframework.web.socket=INFO
logging.level.org.springframework.messaging=INFO
~~~

### 7.8. static/demo.html

File này dùng browser WebSocket API để gửi STOMP frames cơ bản, **không phải STOMP client hoàn chỉnh**. Nó giả định CONNECTED frame đến riêng, không triển khai robust frame parsing, heartbeat, escaping, content-length, receipts và reconnect. Production nên dùng thư viện STOMP client đã được kiểm thử.

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>WebSocket slow client lab</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; }
    button, input { padding: 0.5rem; }
    pre { border: 1px solid #aaa; height: 280px; overflow: auto; }
  </style>
</head>
<body>
  <h1>STOMP/WebSocket lab</h1>
  <button id="connect">Connect</button>
  <input id="message" maxlength="100" value="hello">
  <button id="send">SEND</button>
  <button id="close">Close</button>
  <pre id="log"></pre>
  <script>
    let socket = null;
    let subscribed = false;
    const log = (line) => {
      const panel = document.getElementById("log");
      panel.textContent += line + "\n";
      panel.scrollTop = panel.scrollHeight;
    };
    function frame(command, headers, body = "") {
      return command + "\n" + headers.join("\n")
          + "\n\n" + body + "\0";
    }
    document.getElementById("connect").onclick = () => {
      if (socket && socket.readyState === WebSocket.OPEN) return;
      subscribed = false;
      socket = new WebSocket("ws://" + location.host + "/ws");
      socket.onopen = () => {
        log("WebSocket OPEN");
        socket.send(frame("CONNECT",
          ["accept-version:1.2", "host:localhost"]));
      };
      socket.onmessage = event => {
        const raw = String(event.data);
        if (!subscribed && raw.startsWith("CONNECTED")) {
          subscribed = true;
          socket.send(frame("SUBSCRIBE",
            ["id:s-1", "destination:/topic/echo", "ack:auto"]));
          log("STOMP CONNECTED, subscribed");
        } else {
          log("RECEIVED: " + raw.slice(0, 200));
        }
      };
      socket.onerror = () => log("WebSocket ERROR");
      socket.onclose = event => {
        subscribed = false;
        log("CLOSE code=" + event.code);
      };
    };
    document.getElementById("send").onclick = () => {
      if (!socket || socket.readyState !== WebSocket.OPEN || !subscribed) {
        log("Not subscribed yet");
        return;
      }
      const body = document.getElementById("message").value;
      socket.send(frame("SEND",
        ["destination:/app/echo", "content-type:text/plain"], body));
    };
    document.getElementById("close").onclick = () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close(1000, "demo finished");
      }
    };
  </script>
</body>
</html>
~~~

`WebSocket.bufferedAmount` ở browser là số bytes **chính browser đã queue để gửi đi**, không đo trực tiếp server→browser send buffer. Dùng server metrics để quan sát client đọc chậm. Một browser tab bị pause JS cũng có thể có OS receive buffer đã nhận messages trước; không coi việc không cập nhật giao diện là bằng chứng TCP đang bị nghẽn.

### 7.9. Chạy và kiểm tra

Tại project root:

~~~bash
mvn spring-boot:run
~~~

Mở:

~~~text
http://localhost:8080/demo.html
~~~

Bấm **Connect** rồi **SEND**. Kết quả log kỳ vọng ở mức ứng dụng:

~~~text
WebSocket OPEN
STOMP CONNECTED, subscribed
RECEIVED: MESSAGE
destination:/topic/echo
...
echo: hello
~~~

Dấu `...` là các STOMP headers thực tế có thể thay đổi, **không phải output cố định**. Dùng DevTools Network → WS để xem các frames.

Phát burst nhỏ từ terminal khác:

~~~bash
curl -i -X POST \
  "http://localhost:8080/lab/burst?count=10&bytes=128"
~~~

Nếu controller đưa messages vào broker không lỗi đồng bộ, response:

~~~text
HTTP/1.1 202
...
submitted 10 messages
~~~

Status line/headers có thể khác container, nhưng body demo là chính xác. Cũng có thể thử:

~~~bash
curl -i -X POST \
  "http://localhost:8080/lab/burst?count=500&bytes=128"
~~~

Kỳ vọng HTTP **400** và body:

~~~text
count must be 1..200 and bytes must be 1..8192
~~~

HTTP 400 này đến từ **input validation của BurstController**, không phải STOMP message size limit.

### 7.10. Thử STOMP inbound vượt 32 KiB

Trong DevTools Console của trang đã mở, tạo một socket riêng:

~~~javascript
const ws = new WebSocket("ws://localhost:8080/ws");
ws.onopen = () => {
  ws.send("CONNECT\naccept-version:1.2\nhost:localhost\n\n\0");
};
ws.onmessage = event => {
  const data = String(event.data);
  if (data.startsWith("CONNECTED")) {
    const body = "x".repeat(40 * 1024);
    ws.send("SEND\ndestination:/app/echo\n"
      + "content-type:text/plain\n\n" + body + "\0");
  }
  console.log(data.slice(0, 150));
};
ws.onclose = event => console.log("CLOSED", event.code);
ws.onerror = () => console.log("ERROR");
~~~

Payload 40 KiB lớn hơn cấu hình STOMP 32 KiB. Bạn có thể thấy STOMP ERROR, decoder exception hoặc WebSocket close tùy container/version. Không có bảo đảm HTTP 413 sau upgrade; frame quá lớn có thể bị container chặn **trước** STOMP parser. Test nên xác nhận payload không được controller xử lý như message hợp lệ và không làm server cạn RAM.

### 7.11. Kiểm thử slow consumer đúng cách

Không thể tạo slow TCP reader đáng tin bằng một lệnh `Thread.sleep()` trong browser JS: browser/kernel có thể tiếp nhận dữ liệu vào buffer trong khi handler chưa chạy. Nên dùng network emulator, traffic shaping hoặc test environment có bandwidth/latency control thực sự, rồi đo bytes và queue.

1. Kết nối 1 client nhanh và 1 client có download bandwidth bị giới hạn.
2. Subscribe cùng topic; kiểm tốc độ gửi và nhận thực tế.
3. Phát các burst nhỏ rồi tăng dần trong **lab riêng**, ví dụ:
   
~~~bash
curl -i -X POST \
  "http://localhost:8080/lab/burst?count=200&bytes=8192"
~~~

4. Quan sát latency, active outbound threads, executor queue, pending bytes per session (nếu instrument), close reasons, heap và GC.
5. So sánh client nhanh có bị chậm theo không; thử disconnect/reconnect.
6. Lặp bài test với các giới hạn cao/thấp đã **ghi lại trong test config**, không thay production.

**Không hứa rằng lệnh burst sẽ luôn đóng client sau 10 giây**: nếu mạng đủ nhanh và các buffer chưa đầy, kết nối có thể tiếp tục bình thường. Ngược lại, nếu làm chậm quá mạnh thì kernel/proxy có thể đóng connection trước khi limit của Spring có cơ hội kiểm.

### 7.12. Đóng gói Maven

~~~bash
mvn package
java -jar target/slow-client-lab-0.0.1-SNAPSHOT.jar
~~~

Đây là project Spring Boot; không dùng `javac` trần để build các class Spring mà không có Maven dependency classpath.

## 8. Raw WebSocket trên Servlet: ConcurrentWebSocketSessionDecorator

Nếu dùng `TextWebSocketHandler` hoặc `BinaryWebSocketHandler` trực tiếp qua `WebSocketConfigurer`, cấu hình `configureWebSocketTransport` của **STOMP** không tự áp dụng.

Spring Servlet có `ConcurrentWebSocketSessionDecorator` để bảo đảm tại một thời điểm chỉ có một thread được dùng gửi vào cùng session; các lần send khác được xếp hàng/buffer và bị kiểm timeout/size:

~~~java
// Fragment trong lớp quản lý raw WebSocket session.
WebSocketSession safeSession =
        new ConcurrentWebSocketSessionDecorator(
                originalSession, 10_000, 256 * 1024);
~~~

**Quan trọng:** Tạo **một decorator cho mỗi session** rồi dùng cùng object trong mọi đường gửi. Nếu mỗi lần send lại bọc một decorator mới thì bạn có thể mất mục tiêu đồng bộ và các giới hạn không còn chung cho session.

Decorator này **không** thay:

- WebSocket container frame/message max.
- App-level inbound payload size/schema.
- Global heap/connection quota.
- Broker persistence.
- Socket/network timeout.

Một số phiên bản có thêm `ConcurrentWebSocketSessionDecorator.OverflowStrategy` (drop/terminate) để chọn hành vi khi buffer quá mức. Chọn strategy theo dữ liệu nghiệp vụ, và luôn đếm dropped messages.

### 8.1. Servlet container buffers

Với Jakarta WebSocket server trên servlet container có thể dùng `ServletServerContainerFactoryBean`:

~~~java
// Fragment @Bean trong Spring MVC @Configuration.
@Bean
ServletServerContainerFactoryBean createWebSocketContainer() {
    ServletServerContainerFactoryBean bean =
            new ServletServerContainerFactoryBean();
    bean.setMaxTextMessageBufferSize(64 * 1024);
    bean.setMaxBinaryMessageBufferSize(64 * 1024);
    bean.setMaxSessionIdleTimeout(60_000L);
    return bean;
}
~~~

Đoạn trên là fragment cần imports và configuration class để chạy; giá trị **container message buffer** không đồng nghĩa `setMessageSizeLimit` của STOMP. Tomcat/Jetty có defaults khác nhau; Spring có thể điều chỉnh tối thiểu kích thước transport cho STOMP chunks, nên test đường nhận thật.

## 9. WebFlux/WebSocket: backpressure, nhưng không phải phép màu

WebFlux sử dụng:

- `WebSocketSession.receive()` → `Flux<WebSocketMessage>`.
- `WebSocketSession.send(Publisher<WebSocketMessage>)` → `Mono<Void>`.
- `WebSocketHandler.handle(...)` phải trả một `Mono<Void>` phản ánh lifecycle gửi/nhận.
- Reactor có demand signals và backpressure operators, nhưng **hot sources, broker callbacks, sockets và buffers khác** vẫn cần chính sách rõ ràng.

Một handler echo minh họa:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

public final class EchoWebSocketHandler implements WebSocketHandler {
    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> outbound = session.receive()
                .map(WebSocketMessage::getPayloadAsText)
                .map(text -> "echo:" + text)
                .map(session::textMessage);

        return session.send(outbound);
    }
}
~~~

Đây là class handler nhưng **chưa có route registration và inbound size guard**, không triển khai public trực tiếp. Với WebFlux, cần giới hạn frame/message ở Reactor Netty/transport **đúng phiên bản** và giới hạn parser/application; không suy luận `spring.codec.max-in-memory-size` là hard limit chung cho mọi WebSocket message.

### 9.1. Cold vs hot publisher

- Cold publisher có thể đáp ứng demand, trì hoãn sản xuất.
- Hot source có thể tiếp tục phát dù một subscriber chậm.
- Một `Sinks.Many` hoặc `Flux.create` được dùng không đúng có thể đẩy backlog sang internal queue, gây OOM dù phía WebSocket send API dùng Publisher.

Reactor operators:

| Operator | Tác dụng | Giới hạn |
| --- | --- | --- |
| `onBackpressureLatest()` | Giữ bản mới nhất | Bỏ intermediate events |
| `onBackpressureDrop()` | Bỏ khi thiếu demand | Phải đo drops nếu cần |
| `onBackpressureBuffer(maxSize, ...)` | Buffer hữu hạn, xử lý overflow | Không dùng bản không giới hạn cho hot stream |
| `limitRate(...)` | Điều chỉnh demand upstream | Không phải giới hạn bandwidth mạng |
| `timeout(...)` | Timeout tín hiệu reactive theo operator semantics | Không phải socket hard send timeout |
| `doFinally(...)` | Cleanup khi complete/error/cancel | Không tự ngăn overload |

Fragment chỉ cho trạng thái có thể mất updates:

~~~java
// Snapshot và metrics là type/bean của ứng dụng, không phải code độc lập.
Flux<Snapshot> latest = snapshots
        .onBackpressureLatest()
        .doOnDiscard(Snapshot.class, s -> metrics.incrementDropped());
~~~

Với order/payment/audit, không dùng drop như giải pháp correctness; thay bằng log bền, cursor/replay, retry/idempotency.

### 9.2. Sinks và EmitResult

Nếu dùng Reactor Sinks để broadcast, phải xử lý `tryEmitNext` khi thiếu demand/overflow/terminal state, và cân nhắc chính sách cho **mỗi subscriber**. Không spin-retry vô hạn ngay trên Netty event loop khi emit bị từ chối.

Cần giới hạn kích thước frame ở server transport, tốc độ phát, số subscriptions và dùng connection pool quotas. Một publisher được gọi là reactive không có nghĩa application memory tự động bounded.

## 10. SSE cũng bị máy khách đọc chậm

Server-Sent Events giữ HTTP response `text/event-stream` mở, server gửi events theo dòng. Browser `EventSource` có thể reconnect; `Last-Event-ID`/event id hỗ trợ resumability nếu ứng dụng thực sự có replay.

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

id: 101
event: update
data: {"state":"working"}

id: 102
event: update
data: {"state":"done"}

~~~

Khi client chậm:

- Servlet MVC `SseEmitter` có thể bị block/error/timeout khi ghi; **không** cho phép queue producer phía trước tăng vô hạn.
- WebFlux `Flux<ServerSentEvent<?>>` có semantics reactive demand; nếu nguồn nóng hoặc proxy buffer không tôn trọng demand cần bounded policy.
- Reverse proxy/Nginx/Envoy có thể buffer data hoặc áp idle timeout, khiến events tới client thành từng burst. Cần cấu hình streaming endpoint, heartbeat, connection limits và load-test qua proxy thực.
- `Last-Event-ID` chỉ là một cơ chế client có thể báo id cuối. Server cần log/snapshot và retention policy mới có thể replay.

Servlet MVC fragment:

~~~java
// Fragment, không phải chương trình độc lập.
SseEmitter emitter = new SseEmitter(60_000L);
// Khi có event hợp lệ từ nguồn:
// emitter.send(SseEmitter.event().id("101").name("tick").data("hello"));
~~~

WebFlux fragment:

~~~java
// Fragment trong WebFlux controller, cần import Flux/ServerSentEvent/Duration.
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(i -> ServerSentEvent.<String>builder()
                    .id(Long.toString(i))
                    .event("tick")
                    .data("tick-" + i)
                    .build());
}
~~~

Không coi heartbeat SSE hoặc TCP keep-alive là bằng chứng browser đã xử lý messages. Cần event-age metrics và clean up subscribers khi disconnect.

## 11. Thứ tự, ACK, reconnect và replay

### 11.1. Accepted by broker khác delivered by client

~~~text
Produced
   -> accepted by messaging channel
   -> queued for broker
   -> queued for clientOutboundChannel
   -> write attempted
   -> bytes reached client TCP
   -> browser parsed event
   -> application processed and ACKed
~~~

Mỗi bước là một mức thành công khác nhau. `SimpMessagingTemplate.convertAndSend` hoàn thành không đảm bảo client đã ACK, vì phần lớn pipeline bất đồng bộ. Nếu nghiệp vụ cần exactly-once effect, dùng transaction/outbox, durable message log và idempotency ở business layer; WebSocket không cung cấp exactly-once tự động.

### 11.2. Publish order

Spring STOMP cho phép:

~~~java
// Fragment bên trong configureMessageBroker(...):
registry.setPreservePublishOrder(true);
~~~

Mục tiêu là bảo toàn thứ tự publication **theo một client session** khi outbound executor xử lý song song, đổi lại overhead. Không tạo thứ tự toàn cục giữa nhiều nodes hoặc đảm bảo replay sau reconnect. Với fanout, gửi `seq`/version để client nhận biết gap/out-of-order.

### 11.3. Reconnect storm

Đóng slow clients có thể cứu tài nguyên server, nhưng nếu 10.000 clients cùng reconnect ngay sẽ dồn handshake, authentication và snapshot API. Phải có exponential backoff + jitter, giới hạn retry/rate và snapshot/replay qua cursor. Đừng gửi toàn bộ history trong một WebSocket frame lớn để “bù” dữ liệu.

## 12. Quan sát và cảnh báo

Spring Framework có `WebSocketMessageBrokerStats` khi dùng `@EnableWebSocketMessageBroker`, cung cấp thống kê sessions, abnormal closes, inbound/outbound channel executor và broker/SockJS. Framework có thể log định kỳ ở INFO hoặc xuất stats qua JMX/integration. Một số metrics dưới đây cần tự instrument, không phải tất cả có sẵn tự động.

| Nhóm metric | Cần đo | Tác dụng |
| --- | --- | --- |
| Sessions | active, created, closed, abnormal closes | Rò connection, reconnect storm |
| Inbound | messages/s, bytes/s, rejected oversized | Flood/parse limits |
| Outbound | executor active threads, queued tasks, rejections | Saturation gửi |
| Per-session | pending bytes, send duration, last successful send | Phát hiện slow consumers |
| Broker | subscription count, fanout, destination hot spots | Resource pressure |
| Reliability | dropped events, sequence gaps, replay lag | Chất lượng dữ liệu |
| Runtime | heap, GC pause, CPU, network egress | Nguy cơ OOM/latency |
| Edge | proxy resets, idle timeouts, TLS/WebSocket failures | Vấn đề mạng |

**Đo tail latency:** trung bình send 5 ms có thể che nhóm clients lag 30 giây. Xem p95/p99 event delivery lag, queue wait và per-client backlog, đồng thời phân biệt 1% client rất chậm với toàn hệ thống quá tải.

Một số alert gợi ý:

- Outbound executor queue tăng liên tục và active threads sát trần.
- Tỷ lệ abnormal closes/slow-client disconnect tăng sau deploy.
- Heap tăng tương quan sessions mà không hồi phục sau disconnect.
- P99 delivery lag vượt SLA; number of dropped events tăng.
- Broker fanout/egress vượt capacity dự kiến.
- Reconnect rate tăng gây thêm tải auth/database.

Không gắn session ID, user ID hay destination trực tiếp vào hàng triệu metrics labels có high cardinality; sampling/aggregation và privacy cần được thiết kế.

## 13. Load test: không phỏng đoán server sẽ đóng client chậm

Kịch bản nên có:

1. Một client khỏe với payload 100–500 bytes, baseline latency/CPU/memory.
2. Inbound message gần và vượt 32 KiB; test STOMP fragmentation.
3. Một client chậm do network emulator có bandwidth nhỏ; một client nhanh đồng thời.
4. High fanout tới hàng nghìn clients theo giới hạn lab.
5. Burst vượt network throughput trong vài giây, nhưng không đánh vào production.
6. Kết nối sleep, mất mạng, reconnect và replay state.
7. Reverse proxy/CDN/ingress thực với WebSocket upgrade và SSE buffering.
8. Payload nén có output lớn, serialization allocations và JSON parser limits.
9. Test fairness giữa tenants/users, inbound flood và quota.
10. Đóng hết clients rồi xác nhận memory/subscription counts trở về baseline.

Acceptance criteria cần định lượng theo SLO: p99 event lag, max buffered bytes, max queue depth, max sessions, tỷ lệ disconnect chủ động, no-loss cho dữ liệu quan trọng và không làm chết các clients nhanh.

### Dự toán egress

Với `N` clients, `R` events/s/client và `S` bytes/event sau serialize:

~~~text
approx_outbound_payload_bytes_per_second = N * R * S
~~~

Ví dụ 1.000 clients × 10 events/s × 1 KiB ≈ **9,77 MiB/s** payload, chưa kể WebSocket/STOMP/TLS/TCP overhead. Nếu mỗi event được serialize cho từng client, CPU/GC cũng có thể tăng theo fanout. Tính capacity cả socket buffers, executor queues và per-session buffers; không chỉ network throughput.

## 14. Lỗi thường gặp

| Sai lầm | Vấn đề | Sửa |
| --- | --- | --- |
| Chỉ giới hạn WebSocket frame | Một STOMP message có thể ghép nhiều fragments | Thêm inbound STOMP aggregate limit |
| Chỉ có `setMessageSizeLimit` | Không bound outbound pending bytes | Bổ sung per-session send buffer/time |
| Hiểu send time limit là hard timer | Send đơn có thể không bị kiểm khi không có send tiếp | Transport idle/socket timeouts và observability |
| Xem executor queue như send buffer | Một bên đếm tasks, một bên đếm bytes | Monitor cả hai |
| Set maxPoolSize lớn, queue vô hạn | Threads không tăng như tưởng, heap tăng | Bounded queue, sizing bằng test |
| Tăng thread liên tục | Không tăng bandwidth client | Coalescing, rate control, drop/disconnect |
| Không giới hạn connections/user | Nhiều sessions lách quota | Global + per-user quotas |
| Drop audit/payment events | Dữ liệu nghiệp vụ mất | Durable log/replay/idempotency |
| Dùng `String.length()` như bytes | UTF-8 có multibyte | Giới hạn bytes serialized |
| Gán STOMP settings cho WebFlux/raw WebSocket | Sai framework/transport | Chọn đúng API và server limit |
| Tạo decorator mới mỗi lần raw send | Không chia sẻ state per session | Một wrapper per session |
| Flux hot + unbounded buffer | OOM dù dùng Reactor | Bounded buffer/overflow strategy |
| Nhầm 202 từ lab là delivered | Không có ACK browser | Track sequence và delivery |
| Thử JS sleep làm bằng chứng TCP chậm | Kernel/browser vẫn buffer bytes | Network shaping + server metrics |
| Public burst endpoint không auth | Fanout/DoS | Auth, rate limit, quota |
| Xem heartbeat là backpressure | Client có thể còn ping nhưng lag dữ liệu | Pending bytes và event lag |
| Không có reconnect backoff | Reconnect storm | Exponential backoff + jitter |
| Quên proxy SSE buffering | Events đến thành burst | Tuning đúng streaming path |
| Chỉ đo CPU | Bỏ sót network/queue/GC/tail latency | Observability đa tầng |

## 15. Checklist triển khai production

- [ ] Xác định đúng protocol: STOMP/WebSocket, raw WebSocket, WebFlux hay SSE.
- [ ] Limit inbound bytes sau khi ghép/parse; test encoding, compression, JSON depth và container frame limits.
- [ ] Có giới hạn rate messages/s, connections, subscriptions theo user/tenant.
- [ ] Outbound per-session buffer/time phù hợp bursts hợp lệ và tổng RAM capacity.
- [ ] `clientOutboundChannel` executor queue bounded, có metrics/rejection policy.
- [ ] Có giới hạn tổng memory/network/CPU và bảo vệ một slow client không gây starvation cho client khác.
- [ ] Slow-consumer overflow có hành động rõ: drop/coalesce/disconnect/replay tùy semantics.
- [ ] Critical events có durable log, sequence number, ACK/replay/idempotency.
- [ ] Có heartbeat/idle timeout phù hợp nhưng không xem chúng là backpressure.
- [ ] WebSocket/SSE endpoints có auth, authorization, allowed origins, rate limiting và không public stress API.
- [ ] Có test network shaping, high fanout, proxy buffering, disconnect và reconnect storm.
- [ ] Có dashboard active sessions, pending bytes, executor tasks, drops, event age p99, heap/GC.
- [ ] Có runbook điều chỉnh thresholds dựa trên workload thực thay vì nâng limits vô hạn.

## 16. Câu hỏi tự kiểm tra có đáp án

**1.** `setMessageSizeLimit(32 * 1024)` có giới hạn mỗi WebSocket frame đúng 32 KiB?

**Đáp án:** Không. Đây là giới hạn inbound STOMP message sau ghép, không phải frame limit của container.

**2.** `setSendBufferSizeLimit(256 * 1024)` bảo đảm ứng dụng chỉ giữ 256 KiB outbound tổng cộng?

**Đáp án:** Không. Nó áp dụng cho pending bytes của từng session tại tầng Spring STOMP, không bao gồm task queues, sockets và các sessions khác.

**3.** `setSendTimeLimit(10_000)` chắc chắn đóng một send bị treo sau đúng 10 giây?

**Đáp án:** Không. Spring có thể chỉ kiểm giới hạn này khi có attempt gửi tiếp; cần socket/idle timeouts.

**4.** Vì sao outbound queueCapacity=200 khác send buffer=256 KiB?

**Đáp án:** Executor queue đếm tasks; send buffer đếm bytes pending theo session. Hai thứ có thể bão hòa độc lập.

**5.** Có thể dùng `Thread.sleep()` trong browser onmessage để mô phỏng TCP đọc chậm chắc chắn không?

**Đáp án:** Không. Network và browser buffers có thể đã nhận data; nên dùng traffic shaping và server metrics.

**6.** `TextWebSocketHandler` raw có tự nhận cấu hình STOMP `configureWebSocketTransport` không?

**Đáp án:** Không. Dùng raw session decorator/container limits phù hợp.

**7.** WebFlux với `onBackpressureBuffer()` không giới hạn có chắc không OOM?

**Đáp án:** Không. Hot producer có thể tràn queue; dùng bounded capacity và overflow strategy.

**8.** `SimpMessagingTemplate.convertAndSend` thành công có phải mọi subscriber đã xử lý event?

**Đáp án:** Không. Nếu cần đảm bảo, xây ACK business, log bền và replay.

**9.** Có thể drop events thanh toán như chart snapshot không?

**Đáp án:** Không nên. Chart có thể dùng latest state, còn thanh toán/audit yêu cầu durability và correctness.

**10.** Một client chậm có thể ảnh hưởng các clients khác không?

**Đáp án:** Có thể qua executor threads, queues, broker, heap hoặc network egress dùng chung. Cần isolation, bounded resources và load tests.

## 17. Tài liệu chính thức

- [Spring Framework — STOMP Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html) — outbound executor, sendTimeLimit, sendBufferSizeLimit, inbound message size.
- [Spring Framework — WebSocket Transport](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/server-config.html) — frame/container settings và STOMP limits.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html) — inbound/outbound/broker channels.
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html).
- [Spring Framework — Monitoring WebSocket/STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html).
- [Spring Framework — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html).
- [Spring Framework Javadoc — WebSocketTransportRegistration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketTransportRegistration.html).
- [Spring Framework Javadoc — ConcurrentWebSocketSessionDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html).
- [Spring Framework Javadoc — SseEmitter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html).
- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/backpressure.html).
- [Spring Boot 4.1.2 managed dependencies](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html).
- [Spring Boot 4.1.2 release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455).
- [WHATWG — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html).
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html).

**Ghi nhớ:** Giới hạn kích thước inbound message, pending outbound send bytes, thời gian gửi và task queue là **các hàng rào khác nhau**. Trên Spring MVC STOMP, dùng `setMessageSizeLimit`, `setSendBufferSizeLimit`, `setSendTimeLimit` và tune `clientOutboundChannel` có đo lường. Trên raw WebSocket/WebFlux/SSE, chọn API đúng runtime. Với slow client, cần bounded resources, chính sách overflow minh bạch, quotas, sequence/replay và monitoring; **không** cố chữa bằng tăng buffers hoặc threads vô hạn.