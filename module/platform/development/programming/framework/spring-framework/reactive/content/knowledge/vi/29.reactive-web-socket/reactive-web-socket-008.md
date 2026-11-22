# Giới hạn hàng đợi khi phát cho nhiều phiên hoặc phía nhận chậm trong Spring WebFlux WebSocket

## 1. Bài toán: một client chậm có thể làm hỏng cả kênh broadcast

WebSocket duy trì một kết nối hai chiều để server và client trao đổi thông điệp theo thời gian thực. Trong Spring WebFlux, mỗi WebSocketSession có luồng nhận và luồng gửi reactive. Khi một thông điệp cần phát đến hàng trăm hoặc hàng nghìn phiên, tốc độ tiêu thụ của từng client có thể rất khác nhau:

- Client trên mạng nhanh đọc ngay.
- Client dùng mạng di động hoặc thiết bị yếu xử lý chậm.
- Browser chuyển sang tab nền và cập nhật giao diện chậm.
- Proxy hoặc socket bị nghẽn nên server chưa thể ghi tiếp.
- Một phiên đã ngắt kết nối nhưng pipeline dọn dẹp chưa hoàn tất.

Nếu server đẩy 1.000 thông điệp/giây mà client chỉ xử lý được 50, backlog tăng thêm khoảng 950 thông điệp/giây. Hàng đợi không giới hạn sẽ tăng bộ nhớ, tạo độ trễ lớn, gây garbage collection và cuối cùng ảnh hưởng cả những client đang nhận tốt.

Mục tiêu đúng không phải là "không bao giờ có backlog"; mục tiêu là **kiểm soát backlog, chọn chính sách rõ ràng khi đầy và cô lập phiên nhận chậm**.

Bài học này giải thích:

1. Backpressure của Reactor khác với giới hạn bộ nhớ thực tế như thế nào.
2. Vì sao một multicast sink dùng chung có thể để client chậm giữ chân client nhanh.
3. Cách tổ chức một outbound queue có giới hạn cho từng phiên.
4. Chính sách FAIL_OVERFLOW, drop, coalesce, disconnect và resume.
5. Ví dụ Spring Boot/WebFlux chạy được với Sinks.Many unicast và ArrayBlockingQueue.
6. Kiểm thử không cho một slow subscriber làm mất thông điệp của fast subscriber.
7. Cách tính ngân sách bộ nhớ, đo metrics và xử lý các hàng đợi ẩn trong transport.

## 2. Vòng đời một WebSocketSession

Spring WebFlux cung cấp WebSocketHandler:

~~~java
public interface WebSocketHandler {
    Mono<Void> handle(WebSocketSession session);
}
~~~

Một phiên có hai luồng:

| API | Ý nghĩa |
| --- | --- |
| session.receive() | Flux<WebSocketMessage> nhận từ client |
| session.send(Publisher<WebSocketMessage>) | Ghi thông điệp outbound và trả Mono<Void> |
| session.close(CloseStatus) | Đề nghị đóng phiên với close code phù hợp |
| session.getId() | Định danh phiên trong phạm vi runtime |

Ví dụ tối thiểu chỉ gửi lại các thông điệp vừa nhận:

~~~java
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> replies = session.receive()
        .map(message ->
            session.textMessage(message.getPayloadAsText())
        );

    return session.send(replies);
}
~~~

Trong trường hợp broadcast, nhiều phiên cùng nhận nội dung từ một nguồn. Điều quan trọng là **mỗi phiên có đúng một outbound publisher được đưa vào session.send(...)**, không gọi send() riêng lẻ cho từng event trong vòng lặp.

### 2.1. Luồng xử lý điển hình

~~~text
Nguồn business events
         |
         v
Kiểm tra quyền phát và kích thước payload
         |
         v
Bộ định tuyến broadcast / room
         |
         +------> Queue phiên A --> session A.send(...) --> browser A
         |
         +------> Queue phiên B --> session B.send(...) --> browser B
         |
         +------> Queue phiên C --> session C.send(...) --> browser C
                          |
                          v
                  Giới hạn backlog
                          |
                          v
                Drop / disconnect / resume
~~~

Cách này tách tốc độ nhận của từng client. Tuy nhiên, vẫn phải giới hạn tổng số phiên và lưu ý các tầng bộ đệm bên dưới hàng đợi ứng dụng.

### 2.2. Thành công khi enqueue không có nghĩa client đã nhận

Sinks.Many.tryEmitNext(...) trả OK chỉ cho biết một phần tử được sink chấp nhận tại thời điểm đó. Nó **không xác nhận byte đã được ghi tới socket, browser đã nhận hoặc ứng dụng client đã xử lý**.

Tương tự, việc phần tử rời queue ứng dụng không đồng nghĩa nó đã rời bộ đệm Netty hoặc hệ điều hành. Khi cần bảo đảm xử lý, hãy dùng ACK ở cấp ứng dụng hoặc cơ chế lưu/replay bền vững.

## 3. Backpressure: demand không tự biến thành quota bộ nhớ

Trong Reactive Streams, subscriber báo demand thông qua request(n). Một Publisher tuân thủ backpressure không phát onNext vượt demand chưa được yêu cầu.

Trong thực tế, có nhiều ranh giới không hoàn toàn đồng bộ:

- Producer ngoài Reactor như callback từ broker có thể phát nhanh hơn demand.
- Sink được gọi chủ động bằng tryEmitNext từ nhiều thread.
- Operators như publishOn, flatMap, buffer có thể có prefetch/hàng đợi riêng.
- HTTP/WebSocket writer có thể chuyển message sang buffer transport.
- Netty và kernel có outbound buffer riêng.
- Browser có buffer và thời gian xử lý JavaScript riêng.

Bởi vậy, backpressure là cơ chế điều phối tín hiệu; **một giới hạn queue hữu hạn là chính sách tài nguyên bổ sung**.

### 3.1. Những cách gây backlog không giới hạn

Tránh dùng các cấu trúc sau cho một luồng broadcast không có quota:

~~~java
Sinks.Many<String> sink =
    Sinks.many().unicast().onBackpressureBuffer();
~~~

Ở đây phiên bản không nhận Queue có thể tích lũy dữ liệu không giới hạn khi subscriber không có demand.

~~~java
Flux<String> output = source.onBackpressureBuffer();
~~~

Overload không truyền capacity cũng có nguy cơ buffer vô hạn.

~~~java
Sinks.Many<String> history =
    Sinks.many().replay().all();
~~~

Replay toàn bộ lịch sử phù hợp cho một số bài toán nhỏ/có vòng đời xác định, nhưng không phù hợp cho room chạy vô hạn nếu không có giới hạn retention.

### 3.2. Buffer hữu hạn theo số phần tử

Có thể dùng:

~~~java
Flux<String> bounded = source.onBackpressureBuffer(64);
~~~

Khi downstream thiếu demand, operator chứa tối đa 64 phần tử; phần tử vượt giới hạn gây overflow error theo semantics của overload này. Đây là giới hạn tại vị trí operator, không phải toàn bộ các buffer ở những tầng khác.

Hoặc tạo unicast sink với Queue hữu hạn:

~~~java
Sinks.Many<String> sink = Sinks.many()
    .unicast()
    .onBackpressureBuffer(
        new ArrayBlockingQueue<String>(64)
    );
~~~

Khi phần tử mới không thể được thêm vì Queue đầy, tryEmitNext có thể trả FAIL_OVERFLOW. Ứng dụng phải xử lý kết quả thay vì bỏ qua.

## 4. Vì sao một multicast sink chung có thể gây head-of-line blocking?

Reactor hỗ trợ nhiều chiến lược multicast. Chúng **không tương đương nhau** về độ trễ và quyền độc lập của subscriber.

### 4.1. multicast().onBackpressureBuffer(capacity)

~~~java
Sinks.Many<String> room = Sinks.many()
    .multicast()
    .onBackpressureBuffer(64);
~~~

Chiến lược này phát tới nhiều subscriber và tôn trọng demand theo subscriber chậm nhất. Nếu chênh lệch tốc độ nhận giữa các subscriber vượt bộ đệm cho phép, tryEmitNext có thể trả FAIL_OVERFLOW.

Điều quan trọng:

- Buffer 64 là **một vùng lưu trữ của sink chung**, không phải một queue 64 riêng cho mỗi client.
- Một client chậm có thể kìm hãm luồng phát tới các client nhanh.
- Khi tràn, dùng emitNext với error handler không phù hợp có thể dẫn tới sink bị terminal error, tác động toàn room.
- Khi chưa có subscriber, sink có cơ chế warm-up buffer theo giới hạn.
- Auto-cancel khi subscriber cuối hủy có ảnh hưởng đến khả năng tiếp tục dùng sink.

Với phòng chat nhỏ cần mọi client cùng bắt nhịp, cách này có thể phù hợp. Với broadcast lớn mà client độc lập, nó thường không phải lựa chọn tốt nhất.

### 4.2. multicast().directAllOrNothing()

~~~java
Sinks.Many<String> room = Sinks.many()
    .multicast()
    .directAllOrNothing();
~~~

Nếu **bất kỳ** subscriber nào không có demand, phần tử mới có thể bị drop cho **tất cả** subscriber; tryEmitNext báo FAIL_OVERFLOW. Subscriber chậm không bị đóng chỉ vì sự kiện này.

Chỉ chọn khi protocol chấp nhận mất event cùng lúc ở cả room. Không chọn cho chat history, lệnh điều khiển hoặc giao dịch phải đến đủ người nhận.

### 4.3. multicast().directBestEffort()

~~~java
Sinks.Many<String> room = Sinks.many()
    .multicast()
    .directBestEffort();
~~~

Nếu chỉ một số subscriber chậm, phần tử bị bỏ đối với subscriber đó, còn subscriber có demand vẫn nhận được. Khi **không subscriber nào** có demand, tryEmitNext có thể trả FAIL_OVERFLOW.

Lựa chọn này phù hợp với telemetry hoặc dashboard có thể bỏ frame cũ. Nó không cung cấp replay, queue riêng hay bảo đảm mọi event tới mọi client.

### 4.4. So sánh các cách phát

| Cách | Slow subscriber ảnh hưởng người khác? | Dữ liệu có thể mất? | Dùng cho |
| --- | --- | --- | --- |
| Shared multicast onBackpressureBuffer(64) | Có thể | Khi overflow, phải xử lý lỗi | Room nhỏ, cần phối hợp demand |
| Shared directAllOrNothing() | Có, event có thể mất cho tất cả | Có | Tín hiệu đồng bộ không cần mọi mẫu |
| Shared directBestEffort() | Hạn chế, slow client bị bỏ riêng | Có | Dashboard/telemetry best effort |
| Queue hữu hạn riêng từng phiên | Không cần làm đầy queue của phiên khác | Theo chính sách overflow | Nhiều phiên cần cô lập |
| Broker lưu event + cursor/ACK | Không nếu xử lý đúng quota | Không mất trong retention cam kết | Sự kiện cần resume/replay |

Không có một phương án đúng cho mọi ứng dụng. Hãy xác định tính quan trọng, tần suất và khả năng replay của từng loại message.

## 5. Định nghĩa chính sách khi queue đầy

Một queue hữu hạn chỉ là một nửa giải pháp. Phải quyết định hành vi khi đẩy phần tử thứ N+1.

### 5.1. Ngừng tạo dữ liệu hoặc giảm tốc upstream

Nếu producer có thể bị điều tiết, đây là cách giữ dữ liệu và tránh backlog.

- Truyền tín hiệu demand trở lại upstream.
- Giới hạn tốc độ đọc từ message broker theo tenant/room.
- Tạm ngừng phát những dữ liệu không cần thiết.
- Giảm tần suất sampling khi hệ thống quá tải.

Cách này không luôn phù hợp với một broadcast source có nhiều subscriber độc lập. Dừng toàn nguồn vì một client chậm có thể gây head-of-line blocking.

### 5.2. DROP_LATEST: bỏ phần tử mới

Khi queue đầy, giữ các event cũ đang chờ, bỏ event mới. Chỉ dùng nếu event mới không quan trọng hơn event cũ.

Ví dụ: một stream log best effort có thể chấp nhận mất một số dòng, nhưng phải hiển thị số dòng đã bị bỏ.

### 5.3. DROP_OLDEST: bỏ phần tử cũ

Khi queue đầy, bỏ event cũ nhất để giữ event mới. Phù hợp cho dashboard hiển thị trạng thái gần nhất, không phù hợp cho một chuỗi lệnh cần xử lý theo thứ tự đầy đủ.

Nếu event chứa số thứ tự, client có thể phát hiện gap rồi yêu cầu snapshot mới.

Trong Reactor, một operator per-client có thể áp dụng:

~~~java
Flux<Snapshot> latestStates = source
    .onBackpressureBuffer(
        32,
        BufferOverflowStrategy.DROP_OLDEST
    );
~~~

Điều kiện quan trọng: operator này phải nằm **trong pipeline của từng client** nếu muốn quota riêng, không đặt một lần trên nguồn chung rồi tưởng rằng đã có 32 slot cho mỗi subscriber.

### 5.4. Coalesce theo khóa

Đối với trạng thái có thể thay thế (giá cổ phiếu, vị trí con trỏ, tiến độ), có thể lưu bản mới nhất theo khóa thay vì queue từng thay đổi:

~~~text
Trước coalesce:
  price-A=10, price-A=11, price-A=12, price-B=20

Sau coalesce:
  price-A=12, price-B=20
~~~

Coalescing cần cấu trúc dữ liệu có giới hạn số khóa, thời gian lưu và kích thước payload. Không dùng Map không giới hạn để thay thế một queue không giới hạn.

### 5.5. Disconnect client chậm

Khi message phải được nhận đủ thứ tự nhưng client không theo kịp, **đóng phiên chậm** thường an toàn hơn tiếp tục giữ backlog vô hạn hoặc bỏ âm thầm.

Cách triển khai:

1. Đặt per-session queue capacity.
2. tryEmitNext báo FAIL_OVERFLOW.
3. Ghi metric slow_consumer_disconnect.
4. Gỡ phiên khỏi registry.
5. Đề nghị đóng với close code thích hợp, ví dụ **1013 (SERVICE_OVERLOAD)**.
6. Client reconnect và lấy snapshot/replay từ cursor nếu ứng dụng hỗ trợ.

Không gửi thông tin nhạy cảm trong close reason. Close frame cũng có thể không tới client khi transport đã hỏng.

### 5.6. Quota theo thời gian

Ngay cả khi queue chưa đầy, một message có thể bị chờ hàng chục giây. Có thể áp dụng:

- Max queue age.
- Max time without ACK.
- Max idle send interval.
- Max wall-clock time cho một lần gửi.
- Max backlog theo bytes.

Thời hạn cần tương thích với loại dữ liệu. Một sự kiện đã lỗi thời nên được bỏ hoặc yêu cầu resync, không nên gửi tới client nhiều phút sau đó mà không báo độ trễ.

## 6. Tính ngân sách bộ nhớ

Với queue tính theo số message:

~~~text
N = số phiên đồng thời
Q = số message chờ tối đa trên mỗi phiên
B = kích thước tối đa của một message
M_app ≈ N × Q × B
~~~

Ví dụ:

- N = 200 phiên.
- Q = 64 message/phiên.
- B = 8 KiB/message.

Giới hạn bảo thủ cho payload xấp xỉ **100 MiB** (200 × 64 × 8 KiB), chưa bao gồm metadata, object headers, bộ đệm codec, Netty, kernel socket, in-flight frames và buffer ở broker.

Đây là **ước lượng ngân sách**, không phải phép đo heap chính xác: nếu nhiều phiên cùng giữ tham chiếu tới một object String bất biến, một phần payload có thể được chia sẻ; quá trình encode ra bytes và giữ các frame riêng vẫn tốn thêm bộ nhớ.

### 6.1. Giới hạn số message chưa đủ

Nếu mỗi message có kích thước không giới hạn, 64 message có thể lớn hơn cả trăm MiB. Cần đồng thời:

- Max message bytes.
- Max queue elements.
- Max active sessions.
- Tổng ngân sách memory cho mỗi instance/tenant.
- Quota kết nối và tốc độ publish theo user/room.

Nên kiểm tra kích thước **UTF-8 bytes**, không chỉ String.length() vì số UTF-16 code units không bằng số bytes trên wire.

### 6.2. Phân tách ngân sách cho từng room và tenant

Một tenant có thể mở hàng nghìn session và chiếm phần lớn ngân sách của instance. Cần có giới hạn theo tenant/room và chính sách ưu tiên nếu một số luồng quan trọng hơn.

## 7. Ví dụ Java 17+ với outbound queue hữu hạn theo phiên

Ví dụ sau dùng **Spring Boot 4.1.2, Java 17+, Spring WebFlux và Project Reactor**. Nó triển khai một broadcast hub đơn giản:

- Mỗi client có một Sinks.Many unicast.
- Queue là ArrayBlockingQueue có 64 slot.
- Giới hạn 200 client trong một instance.
- Payload text không quá 8 KiB.
- Khi queue của một client đầy, chỉ client đó bị loại khỏi registry và được yêu cầu đóng.
- Hai client khác có thể tiếp tục nhận message.
- Không subscribe thủ công cho từng thông điệp WebSocket.
- Có test tái hiện một subscriber không yêu cầu demand.

Ví dụ dùng dữ liệu text công khai, chưa tích hợp authentication. Endpoint publish phải được bảo vệ trước khi triển khai thực tế.

Cấu trúc:

~~~text
bounded-websocket-broadcast/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/broadcast/
    │       ├── BroadcastApplication.java
    │       ├── BoundedHub.java
    │       ├── BroadcastSocketHandler.java
    │       ├── BroadcastRoutes.java
    │       └── PublishController.java
    └── test/
        └── java/com/example/broadcast/
            └── BoundedHubTest.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>bounded-websocket-broadcast</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
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

Spring Boot parent quản lý phiên bản Spring Framework, Reactor, Netty và các dependency liên quan. Starter webflux-test trong Boot 4 cung cấp các công cụ kiểm thử cho WebFlux.

### 7.2. BroadcastApplication.java

~~~java
package com.example.broadcast;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BroadcastApplication {

    public static void main(String[] args) {
        SpringApplication.run(BroadcastApplication.class, args);
    }
}
~~~

### 7.3. BoundedHub.java

Đây là phần chính của ví dụ.

~~~java
package com.example.broadcast;

import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@Component
public final class BoundedHub {

    public static final int MAX_SESSIONS = 200;
    public static final int MAX_PENDING = 64;
    public static final int MAX_TEXT_BYTES = 8192;

    private final ConcurrentMap<String, Peer> peers =
        new ConcurrentHashMap<>();

    private final AtomicInteger active = new AtomicInteger();

    public record BroadcastReport(
        int accepted,
        int disconnected,
        int activeSessions
    ) {}

    public static final class Peer {

        private final String id;

        private final Sinks.Many<String> outgoing =
            Sinks.many().unicast().onBackpressureBuffer(
                new ArrayBlockingQueue<String>(MAX_PENDING)
            );

        private final Sinks.One<CloseStatus> closeRequested =
            Sinks.one();

        private boolean stopped;

        private Peer(String id) {
            this.id = id;
        }

        public String id() {
            return id;
        }

        public Flux<String> outgoing() {
            return outgoing.asFlux();
        }

        public Mono<CloseStatus> closeRequested() {
            return closeRequested.asMono();
        }

        // Serialize only the producers of THIS peer's sink.
        private synchronized Sinks.EmitResult offer(String text) {
            if (stopped) {
                return Sinks.EmitResult.FAIL_TERMINATED;
            }

            return outgoing.tryEmitNext(text);
        }

        private synchronized void requestClose(
            CloseStatus status
        ) {
            if (!stopped) {
                stopped = true;
                closeRequested.tryEmitValue(status);
            }
        }

        private synchronized void finish() {
            stopped = true;
            outgoing.tryEmitComplete();
        }
    }

    public Peer register() {
        while (true) {
            int count = active.get();

            if (count >= MAX_SESSIONS) {
                throw new IllegalStateException(
                    "Too many WebSocket sessions"
                );
            }

            if (active.compareAndSet(count, count + 1)) {
                break;
            }
        }

        Peer peer = new Peer(UUID.randomUUID().toString());
        peers.put(peer.id(), peer);
        return peer;
    }

    public BroadcastReport broadcast(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                "A broadcast must have non-blank text"
            );
        }

        if (text.getBytes(StandardCharsets.UTF_8).length
                > MAX_TEXT_BYTES) {
            throw new IllegalArgumentException(
                "Broadcast exceeds 8 KiB"
            );
        }

        int accepted = 0;
        int disconnected = 0;

        for (Peer peer : peers.values()) {
            Sinks.EmitResult result = peer.offer(text);

            if (result == Sinks.EmitResult.OK) {
                accepted++;
                continue;
            }

            // Fail closed. An unexpected sink failure must be logged
            // and counted separately in a production application.
            if (detach(peer)) {
                disconnected++;
                peer.requestClose(
                    CloseStatus.SERVICE_OVERLOAD
                        .withReason("Outbound backlog")
                );
            }
        }

        return new BroadcastReport(
            accepted,
            disconnected,
            active.get()
        );
    }

    public int activeCount() {
        return active.get();
    }

    public void unregister(Peer peer) {
        detach(peer);
        peer.finish();
    }

    private boolean detach(Peer peer) {
        if (peers.remove(peer.id(), peer)) {
            active.decrementAndGet();
            return true;
        }

        return false;
    }
}
~~~

**Tại sao dùng ArrayBlockingQueue?**

Sinks.many().unicast().onBackpressureBuffer() không truyền Queue mặc định có thể giữ backlog không giới hạn. Khi truyền Queue hữu hạn, sink không thể thêm message vượt số slot khả dụng. Khi thiếu demand và queue đầy, tryEmitNext báo FAIL_OVERFLOW.

**Tại sao tạo sink riêng cho mỗi Peer?**

Một client chậm chỉ làm đầy queue của chính nó. Nó không chiếm queue của những client khác. Mỗi Peer cũng chỉ có một subscriber outbound tương ứng với một session.send(...).

**Tại sao dùng synchronized ở offer?**

Các producer có thể gọi broadcast từ nhiều request/threads. Reactor safe sinks phát hiện concurrent emission không được serialize và có thể trả FAIL_NON_SERIALIZED. Synchronize tại Peer giúp chỉ một producer gọi tryEmitNext trên sink của phiên đó tại một thời điểm. Đây là cách đơn giản cho demo, không phải kiến trúc fan-out tối ưu ở quy mô rất lớn.

**Tại sao dùng AtomicInteger cho MAX_SESSIONS?**

Nếu chỉ kiểm tra peers.size() rồi add, nhiều handshake đồng thời có thể cùng vượt hạn mức. Vòng compareAndSet cấp quota trước khi tạo Peer. detach chỉ giảm số phiên một lần nhờ remove theo cặp key/value.

### 7.4. BroadcastSocketHandler.java

~~~java
package com.example.broadcast;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Mono;

@Component
public final class BroadcastSocketHandler
        implements WebSocketHandler {

    private final BoundedHub hub;

    public BroadcastSocketHandler(BoundedHub hub) {
        this.hub = hub;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        final BoundedHub.Peer peer;

        try {
            peer = hub.register();
        }
        catch (IllegalStateException overloaded) {
            return session.close(
                CloseStatus.SERVICE_OVERLOAD
            );
        }

        Mono<Void> outbound = session.send(
            peer.outgoing().map(session::textMessage)
        );

        // Consume the inbound stream so completion can detect
        // that the client has disconnected.
        Mono<Void> inbound = session.receive().then();

        // When a queue overflows, close only this session.
        Mono<Void> forcedClose = peer.closeRequested()
            .flatMap(session::close);

        // Terminate when the connection closes, sending fails,
        // or this peer must be disconnected.
        return Mono.firstWithSignal(
                inbound,
                outbound,
                forcedClose
            )
            .doFinally(signal -> hub.unregister(peer));
    }
}
~~~

Một phiên có một session.send(...) duy nhất. Mono.firstWithSignal cho phép vòng đời phiên kết thúc khi inbound hoàn tất, outbound kết thúc/lỗi hoặc policy yêu cầu đóng phiên. doFinally dọn registry khi complete, error hoặc cancel.

Trong một hệ thống production, cần quan sát lỗi đóng phiên và phân biệt graceful close với transport failure. Không kỳ vọng close frame 1013 luôn tới client nếu socket đã mất kết nối.

### 7.5. BroadcastRoutes.java

~~~java
package com.example.broadcast;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration
public class BroadcastRoutes {

    @Bean
    HandlerMapping socketMapping(
        BroadcastSocketHandler handler
    ) {
        return new SimpleUrlHandlerMapping(
            Map.of("/ws/live", handler),
            -1
        );
    }
}
~~~

Trong cấu hình WebFlux của Spring Boot, WebSocketHandlerAdapter được cung cấp bởi hạ tầng WebFlux. SimpleUrlHandlerMapping nối URL /ws/live tới WebSocketHandler.

### 7.6. PublishController.java

~~~java
package com.example.broadcast;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class PublishController {

    private final BoundedHub hub;

    public PublishController(BoundedHub hub) {
        this.hub = hub;
    }

    @PostMapping(
        value = "/broadcast",
        consumes = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<BoundedHub.BroadcastReport> publish(
        @RequestBody Mono<String> text
    ) {
        return text.map(hub::broadcast)
            .onErrorMap(
                IllegalArgumentException.class,
                error -> new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid broadcast message",
                    error
                )
            );
    }
}
~~~

POST /api/broadcast nhận text rồi chuyển cho các Peer đang hoạt động. Đây là endpoint demo; **trong production phải xác thực và phân quyền người được phép publish**, giới hạn request body ở gateway/server và áp dụng rate limit.

Vòng lặp broadcast là công việc đồng bộ O(N) qua các Peer. Nó đủ để giải thích queue isolation, nhưng không nên để hàng nghìn vòng xử lý đắt đỏ chạy lâu trên Netty event-loop. Với quy mô lớn, chuyển fan-out sang dispatcher có giới hạn, chia shard theo room và đặt quota toàn hệ thống.

## 8. Kiểm thử bằng JUnit 5 và StepVerifier

Test dưới đây kiểm tra phần khó nhất mà không phụ thuộc vào timing của socket: một Peer không subscribe, nên queue của nó không được drain. Peer thứ hai subscribe với unbounded demand và nhận bình thường.

### 8.1. BoundedHubTest.java

~~~java
package com.example.broadcast;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.socket.CloseStatus;

import reactor.core.Disposable;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class BoundedHubTest {

    @Test
    void slowPeerIsRemovedButFastPeerKeepsReceiving() {
        BoundedHub hub = new BoundedHub();

        BoundedHub.Peer fast = hub.register();
        BoundedHub.Peer slow = hub.register();

        List<String> received = new ArrayList<>();

        // This subscriber requests demand and drains its sink.
        Disposable subscription =
            fast.outgoing().subscribe(received::add);

        // The slow peer intentionally has no subscriber;
        // its bounded queue cannot drain.
        for (int i = 0; i <= BoundedHub.MAX_PENDING; i++) {
            hub.broadcast("message-" + i);
        }

        assertEquals(
            BoundedHub.MAX_PENDING + 1,
            received.size()
        );
        assertEquals("message-0", received.get(0));
        assertEquals(
            "message-" + BoundedHub.MAX_PENDING,
            received.get(BoundedHub.MAX_PENDING)
        );

        // The slow peer exceeded its queue capacity.
        assertEquals(1, hub.activeCount());

        StepVerifier.create(slow.closeRequested())
            .expectNextMatches(status ->
                status.getCode()
                    == CloseStatus.SERVICE_OVERLOAD.getCode()
            )
            .verifyComplete();

        subscription.dispose();
        hub.unregister(fast);
        hub.unregister(slow);
    }

    @Test
    void rejectsOversizedMessageBeforeFanout() {
        BoundedHub hub = new BoundedHub();

        String oversized = "x".repeat(
            BoundedHub.MAX_TEXT_BYTES + 1
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> hub.broadcast(oversized)
        );
    }

    @Test
    void enforcesMaximumConnectionQuota() {
        BoundedHub hub = new BoundedHub();
        List<BoundedHub.Peer> peers = new ArrayList<>();

        for (int i = 0; i < BoundedHub.MAX_SESSIONS; i++) {
            peers.add(hub.register());
        }

        assertThrows(
            IllegalStateException.class,
            hub::register
        );

        for (BoundedHub.Peer peer : peers) {
            hub.unregister(peer);
        }

        assertEquals(0, hub.activeCount());
    }
}
~~~

**Ý nghĩa của test đầu tiên:** queue 64 slot của Peer không subscribe sẽ đầy ở lần gửi tiếp theo; Peer chậm bị loại. Peer nhanh vẫn có demand và tiếp tục nhận tất cả message trong ví dụ. Đây là test của **queue trong ứng dụng**, không phải phép chứng minh client ngoài mạng thực nhận được từng byte.

Test thứ hai xác minh giới hạn payload. Test thứ ba xác minh giới hạn số phiên.

### 8.2. Lệnh chạy

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Maven chạy unit tests trước khi ứng dụng được khởi động ở lệnh thứ hai.

### 8.3. Thử qua browser và curl

Mở developer console ở browser:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/live");

socket.onopen = () => console.log("connected");
socket.onmessage = (event) => console.log(event.data);
socket.onclose = (event) => {
    console.log("closed", event.code, event.reason);
};
~~~

Mở thêm một hoặc hai tab có cùng đoạn code, rồi publish từ terminal:

~~~bash
curl -i -X POST http://localhost:8080/api/broadcast \
  -H "Content-Type: text/plain" \
  --data-binary "Hello room"
~~~

Nếu các session còn hoạt động, từng browser nhận:

~~~text
Hello room
~~~

Response REST có cấu trúc như:

~~~json
{
  "accepted": 3,
  "disconnected": 0,
  "activeSessions": 3
}
~~~

Các con số là **minh họa** khi có đúng ba phiên đã đăng ký và chưa có queue đầy. accepted đếm số sink chấp nhận message, không phải số browser đã xác nhận xử lý.

Nếu tất cả client đều nhận nhanh, không dễ làm đầy queue chỉ bằng vài request. Unit test dùng Peer không drain giúp kích hoạt overflow một cách có kiểm soát. Muốn kiểm chứng slow network thật, cần test client bị throttle, proxy giới hạn băng thông và theo dõi cả buffer của transport.

## 9. Giới hạn của ví dụ: queue ứng dụng chưa phải end-to-end flow control

Ví dụ dùng ArrayBlockingQueue để đặt giới hạn **tại Sinks.Many của từng phiên**. Nhưng có ít nhất ba tầng khác cần quản lý:

~~~text
Application per-session queue
           |
           v
Reactor operators / writer prefetch
           |
           v
Netty outbound pending bytes
           |
           v
Kernel socket send buffer
           |
           v
Network và browser
~~~

Nếu session.send(...) yêu cầu message sớm hơn tốc độ socket thực sự ghi, queue ứng dụng có thể được drain trong khi các message vẫn đang chờ ở Netty. Khi đó tryEmitNext trả OK không có nghĩa backlog tổng thể còn nhỏ.

Vì thế **không được tuyên bố ví dụ đơn thuần đã chặn mọi memory growth của một slow receiver**. Production cần giới hạn thêm:

- Số byte đang chờ ghi trên connection.
- Write timeout hoặc send timeout theo server adapter.
- Netty Channel writability và write-buffer watermarks khi tích hợp ở tầng Netty.
- Số frame đang in-flight.
- Số frame được client ACK khi dữ liệu phải được xử lý đầy đủ.
- Max lifetime của một message trong queue hoặc transport.
- Max inbound frame/message size để ngăn payload quá lớn.

Các setting cụ thể khác nhau giữa Reactor Netty, Tomcat, Jetty và phiên bản Spring. Kiểm tra API của server adapter thực tế, không áp một giới hạn Netty sang connector khác rồi tưởng đã có tác dụng.

### 9.1. Không đồng nhất WebSocket write với browser ACK

Một message đã được ghi xuống transport không bảo đảm JavaScript onmessage đã chạy. Đối với sự kiện cần chắc chắn client xử lý, cần giao thức ứng dụng:

~~~text
Server: EVENT {sequence: 101, ...}
Client: ACK   {sequence: 101}
Server: ghi nhận lastAck = 101
~~~

Giới hạn tối đa W event chưa được ACK. Nếu pending ACK vượt W hoặc timeout, tạm dừng/đóng phiên hoặc yêu cầu client resync. Không gửi lại event một cách mù quáng nếu handler có side effect; client cần xử lý idempotent bằng sequence/event ID.

### 9.2. Khi cần bảo đảm không mất dữ liệu

Queue WebSocket trong memory không phải một event store bền vững. Khi process restart hoặc connection mất, queue biến mất.

Một hệ thống cần resume thường dùng:

- Database log hoặc message broker lưu sự kiện.
- Sequence/offset tăng dần theo room hoặc partition.
- Cursor last acknowledged ở client.
- Replay sau khi reconnect trong cửa sổ retention.
- Snapshot/resync nếu cursor đã hết hạn.
- Consumer idempotent để xử lý event trùng.

Không chuyển bài toán giao dịch tài chính hoặc lệnh điều khiển quan trọng thành chính sách DROP_OLDEST chỉ để giảm bộ nhớ.

## 10. Đảm bảo thứ tự và công bằng giữa các phiên

### 10.1. Ordering

WebSocket giữ thứ tự frame trên một connection, nhưng thứ tự business event còn phụ thuộc các producer và cách bạn đưa message vào từng queue.

Nếu nhiều thread gọi broadcast đồng thời, synchronized trên từng Peer chỉ đảm bảo các lệnh emit **không đồng thời tại cùng sink**. Nó không đảm bảo tuyệt đối toàn bộ các Peer nhìn cùng một thứ tự khi hai broadcast call xen kẽ.

Nếu thứ tự toàn room là yêu cầu, hãy:

- Đánh sequence ở ingress.
- Serialize luồng nguồn cho từng room/partition.
- Dùng một bounded dispatcher theo room.
- Fan-out theo sequence cố định.
- Kiểm tra gap ở client và hỗ trợ replay khi cần.

### 10.2. Fairness

Một room cực lớn có thể chiếm thời gian của dispatcher và làm room nhỏ bị chậm. Có thể chia shard theo room, tenant hoặc hash của session ID, giới hạn số phần tử xử lý mỗi vòng và đưa workload nặng ra khỏi event-loop.

Không tạo một thread riêng cho từng WebSocket session nếu không có lý do; hàng chục nghìn thread có chi phí bộ nhớ và scheduling lớn.

### 10.3. Backpressure toàn cục

Nếu mọi phiên đều chậm, việc chỉ loại từng phiên có thể gây reconnect storm. Hệ thống nên có thêm:

- Global publish rate limit.
- Adaptive admission control.
- Circuit breaker/bulkhead cho nguồn event.
- Giảm tần suất update hoặc coalesce theo tenant.
- Cooldown/reconnect jitter.
- Ngân sách số phiên theo instance và room.

## 11. Cleanup và quản lý vòng đời

Khi client ngắt hoặc server yêu cầu đóng:

1. Gỡ phiên khỏi registry.
2. Hủy outbound Publisher.
3. Dọn queue và các subscription.
4. Giải phóng tham chiếu tới payload.
5. Ngừng mọi timer hoặc listener gắn riêng với phiên.
6. Ghi metric close/cancel và nguyên nhân.

Trong ví dụ, Mono.firstWithSignal và doFinally xử lý dọn registry khi phiên hoàn tất hoặc bị hủy. Với triển khai có timer, broker subscription hoặc resource khác, cần dispose chúng trong cùng lifecycle.

Không chỉ xóa Map entry mà để một Flux.interval hoặc broker consumer tiếp tục phát cho phiên đã ngắt.

## 12. Thử nghiệm slow consumer thực tế

Unit test với một subscriber không request là cần thiết nhưng chưa đủ. Một kế hoạch load/integration test nên bao gồm:

| Tình huống | Quan sát cần có |
| --- | --- |
| 1 client nhanh, 1 client không đọc | Client nhanh vẫn được phục vụ; client chậm bị xử lý theo policy |
| 1.000 client nhận bình thường | Heap, CPU, queue depth và latency nằm trong budget |
| 10% client băng thông thấp | Không tạo memory growth vô hạn |
| Message lớn gần 8 KiB | Byte budget và throughput đúng |
| Một client gửi payload lớn | Inbound size limit và lỗi protocol rõ ràng |
| Client disconnect giữa lúc broadcast | Không giữ reference đến phiên đã đóng |
| Nhiều producer cùng publish | Không xuất hiện FAIL_NON_SERIALIZED ngoài dự kiến |
| Mất mạng giữa chừng | Close/cancel/cleanup và reconnect đúng |
| Server restart | Client resync/replay theo contract |
| Broker nhanh hơn WebSocket | Quota nguồn, queue và fan-out vẫn hữu hạn |

Có thể dùng Gatling, k6 với WebSocket hoặc test client tự viết để tạo tải. Test nên đo memory, pending outbound bytes và network throughput, không chỉ số request thành công.

### 12.1. Các chỉ số theo dõi

- websocket_sessions_active.
- websocket_outbound_queue_depth.
- websocket_outbound_queue_overflow_total.
- websocket_slow_consumer_disconnect_total.
- websocket_publish_accepted_total.
- websocket_publish_rejected_total.
- websocket_outbound_bytes_pending.
- websocket_event_lag_seconds.
- websocket_send_timeout_total.
- websocket_disconnect_total theo close code.
- websocket_reconnect_rate.
- websocket_replay_gap_total.

Tên metrics có thể đặt theo quy ước hệ thống; đây là gợi ý thiết kế. Với room/tenant có cardinality cao, không đưa session ID làm label metric Prometheus vì có thể gây bùng nổ số time series.

### 12.2. Cảnh báo sớm

Đặt alert khi:

- Queue depth p95 tăng trong nhiều phút.
- Tỷ lệ overflow tăng.
- Number of active sessions gần ngưỡng.
- Pending bytes của transport tiếp tục tăng.
- Client lag vượt SLA.
- GC pause hoặc heap usage tăng theo số phiên.
- Reconnect rate tăng sau khi một node quá tải.

## 13. Bảo mật WebSocket và bảo vệ tài nguyên

Giới hạn queue là một phần của bảo vệ dịch vụ trước hành vi vô ý hoặc có chủ đích.

- Xác thực tại handshake hoặc tầng HTTP phù hợp.
- Kiểm tra Origin/CORS tương ứng với chính sách WebSocket, không dựa vào CORS của REST để thay thế.
- Phân quyền room/tenant trước khi đăng ký.
- Giới hạn số kết nối theo user, tenant và IP.
- Giới hạn kích thước frame và tổng message.
- Giới hạn tốc độ publish/inbound messages.
- Không cho client phát tự do vào mọi room.
- Không ghi access token hoặc payload nhạy cảm vào log.
- Đặt thời gian idle/heartbeat phù hợp; dùng WebSocket ping/pong theo khả năng stack.
- Dọn phiên khi token hết hạn hoặc quyền bị thu hồi theo contract.
- Dùng wss:// trong production.

Endpoint POST /api/broadcast ở ví dụ chỉ dành cho môi trường cục bộ; không deploy công khai mà không có authentication/authorization/rate limit.

## 14. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Sinks.unicast().onBackpressureBuffer() không truyền Queue | Backlog có thể không giới hạn | Truyền Queue hữu hạn |
| Sinks.replay().all() cho room vô hạn | Tích lũy lịch sử trong memory | Dùng retention hữu hạn hoặc event store |
| Dùng shared multicast buffer rồi tưởng là per-client queue | Client chậm kìm client nhanh | Tách queue mỗi phiên hoặc dùng best-effort có chủ đích |
| Bỏ qua tryEmitNext result | Mất event/overflow không được phát hiện | Phân loại FAIL_OVERFLOW, FAIL_TERMINATED, FAIL_NON_SERIALIZED |
| emitNext lỗi overflow lên shared sink | Có thể làm room terminal error | Dùng tryEmitNext và policy cục bộ |
| Mỗi event gọi session.send(...).subscribe() | Nhiều luồng gửi, mất thứ tự và khó cleanup | Một outbound Flux trên mỗi session |
| Dùng queue vô hạn để tránh rớt event | Tăng memory và latency | Queue hữu hạn + replay/ACK |
| Giới hạn số event nhưng không giới hạn byte | Một event rất lớn vẫn gây OOM | Giới hạn UTF-8 payload bytes |
| Coi sink OK là đã được client xử lý | Đánh giá sai delivery guarantee | Dùng ACK nếu cần |
| Chỉ quan sát heap queue Java, bỏ qua Netty buffer | Không phát hiện backlog ở transport | Đo pending outbound bytes và send timeouts |
| Dùng DROP_OLDEST với lệnh thanh toán | Mất sự kiện quan trọng | Lưu bền vững và dùng ACK/replay |
| Không dọn Peer khi disconnect | Memory leak, phantom sessions | doFinally, remove và dispose |
| Broadcast đồng thời không serialize producer | FAIL_NON_SERIALIZED hoặc reorder | Serialize theo room/Peer |
| Publish nặng trên event-loop | Tăng latency cho mọi kết nối | Dispatcher hữu hạn, shard fan-out |
| Chỉ rate-limit inbound, bỏ qua outbound | Server vẫn OOM vì push | Quota cả hai chiều |
| Mọi client reconnect cùng lúc | Reconnect storm | Backoff và jitter |
| Không kiểm soát Origin/room | Cross-origin hoặc truy cập trái phép | Validate handshake và authorization |

## 15. Checklist áp dụng trong production

Trước khi chạy thật, xác nhận:

1. Mỗi phiên có outbound Publisher rõ ràng?
2. Queue riêng có giới hạn cứng theo message và byte?
3. Max sessions per instance, user và tenant được cấu hình?
4. Chính sách overflow có tương ứng với semantics của event?
5. Khi queue đầy, chỉ phiên chậm bị loại hay cả room chịu ảnh hưởng?
6. tryEmitNext result có được kiểm tra?
7. Producer đồng thời có được serialize theo yêu cầu ordering?
8. Có giới hạn số frame đang in-flight ở tầng transport?
9. Có send timeout, channel writability hoặc cơ chế tương đương?
10. Nếu dữ liệu quan trọng, có ACK/cursor/replay bền vững?
11. Có chính sách snapshot/resync khi mất event?
12. Có giám sát queue depth, pending bytes, lag và overflow?
13. Có dọn subscription/timer/registry trong doFinally?
14. Có load test với mạng chậm, disconnect, reconnect và payload lớn?
15. Có xác thực, phân quyền room, kiểm tra Origin và rate limit?
16. Có tránh broadcast fan-out nặng trên event-loop?
17. Có retry budget/cooldown để tránh reconnect storm?
18. Có phương án shutdown và restart không làm mất dữ liệu cần giữ?

## 16. Bài tập thực hành

**Bài 1 — Queue hữu hạn:** Tạo unicast sink với ArrayBlockingQueue(4). Phát năm phần tử trước khi có subscriber và kiểm tra lần phát tràn.

**Bài 2 — Slow vs fast:** Tạo hai Peer, chỉ subscribe cho Peer nhanh. Broadcast năm message. Xác minh Peer nhanh vẫn nhận đủ và Peer chậm bị đóng.

**Bài 3 — Multicast:** So sánh multicast().onBackpressureBuffer(4), directBestEffort() và directAllOrNothing() với một subscriber request(0) và một subscriber có demand.

**Bài 4 — Overflow policy:** Thay disconnect bằng DROP_OLDEST cho dữ liệu dashboard, kiểm tra client nhận snapshot mới nhất và phát hiện sequence gap.

**Bài 5 — Ordering:** Gọi broadcast từ hai thread. Đánh sequence ở ingress và xác minh mỗi client nhận một thứ tự nhất quán theo room.

**Bài 6 — Byte budget:** Đặt MAX_TEXT_BYTES=1024. Gửi text Unicode và kiểm tra giới hạn theo UTF-8 chứ không chỉ String.length().

**Bài 7 — Load test:** Tạo 200 phiên WebSocket, trong đó 10% đọc chậm. Đo heap, queue depth, pending bytes và tỷ lệ disconnect.

**Bài 8 — ACK protocol:** Thêm sequence, client ACK, giới hạn 16 event chưa ACK và timeout khi client không xác nhận.

**Bài 9 — Replay:** Lưu event trong broker/database. Reconnect bằng lastAck và chỉ phát lại các event còn thiếu.

**Bài 10 — Cleanup:** Chủ động đóng browser tab, kiểm tra activeCount giảm và không còn timer/subscription giữ Peer.

**Bài 11 — Multi-tenant:** Giới hạn 20 phiên mỗi tenant và 200 phiên mỗi instance. Kiểm tra quota khi nhiều handshake đồng thời.

**Bài 12 — Transport backpressure:** Dùng proxy throttle outbound bandwidth. Xác định điểm backlog rời queue ứng dụng nhưng còn nằm tại Netty, rồi bổ sung chính sách giới hạn phù hợp.

## 17. Ghi nhớ

Giới hạn queue khi WebSocket broadcast không chỉ là thêm một buffer. Một thiết kế an toàn phải chọn **phạm vi queue (mỗi phiên hay toàn room), capacity, overflow policy, resource cleanup và delivery guarantee**.

Với Spring WebFlux, kết nối mỗi phiên được phục vụ bằng một session.send(Publisher<WebSocketMessage>) và một lifecycle reactive. Khi cần cô lập client chậm, per-session **Sinks.many().unicast().onBackpressureBuffer(Queue hữu hạn)** là một điểm khởi đầu rõ ràng: theo dõi tryEmitNext, xử lý FAIL_OVERFLOW và dọn Peer khi disconnect.

Shared multicast sink có các semantics khác: onBackpressureBuffer theo demand thấp nhất, directAllOrNothing có thể bỏ cho toàn room, còn directBestEffort bỏ theo subscriber chậm. Chọn theo semantics của sản phẩm, không chỉ theo mức throughput.

Cuối cùng, **queue ứng dụng không tự giới hạn toàn bộ bộ nhớ transport**. Hãy đo byte pending, send timeout, kích thước payload, số phiên và event lag. Với dữ liệu cần đủ và đúng thứ tự, bổ sung ACK/cursor/replay; với dữ liệu thay thế được, cân nhắc drop/coalesce có kiểm soát.

## 18. Tài liệu tham khảo

- Spring Framework Reference — WebFlux WebSockets: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
- Spring Framework Reference — WebFlux Config / WebSocketService: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework API — WebSocketSession: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html
- Spring Framework API — CloseStatus: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/CloseStatus.html
- Reactor Core Reference — Sinks: https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html
- Reactor Core API — Sinks.UnicastSpec: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.UnicastSpec.html
- Reactor Core API — Sinks.MulticastSpec: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.MulticastSpec.html
- Reactor Core API — Flux.onBackpressureBuffer: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Netty Reference Guide: https://projectreactor.io/docs/netty/release/reference/http-server.html
- Spring Boot 4.1 Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/4.1/reference/web/reactive.html
