# Máy khách ngắt kết nối, hủy đăng ký và dọn tài nguyên trong kết nối dài Spring Boot

## 1. Bài toán: client đã rời đi nhưng công việc phía server vẫn tiếp tục

Một endpoint Spring Boot nhận HTTP request, chạy vài mili giây và trả JSON thường có vòng đời ngắn. Nhưng **Server-Sent Events (SSE), WebSocket, streaming download, long polling** và các subscription tới message broker có thể tồn tại hàng chục giây, hàng phút hoặc lâu hơn. Trong thời gian đó, server có thể giữ timer, task, connection, entry trong registry, callback, thread, buffer, subscription và kết nối tới hệ thống khác.

Giả sử trình duyệt mở một trang dashboard có `new EventSource("/events")`. Backend đăng ký một listener vào nguồn dữ liệu để đẩy giá trị mới. Người dùng đóng tab sau 20 giây, nhưng listener phía backend không bị hủy. Sau 1.000 lượt truy cập như vậy, có thể vẫn tồn tại 1.000 listeners và các hàng đợi chưa bao giờ được giải phóng. Triệu chứng về sau là RAM tăng, số timers/tasks tăng, heap giữ `SseEmitter`/`WebSocketSession`, kết nối downstream bị giữ, hoặc server phát sinh lỗi `Broken pipe` liên tục.

**Chủ đề bài học:** khi máy khách ngắt kết nối, làm sao nhận biết sự kiện kết thúc, **hủy đăng ký (unsubscribe/cancel)** khỏi nguồn dữ liệu và **dọn tài nguyên (cleanup)** một cách đầy đủ, đúng một lần theo nghĩa tác dụng, an toàn khi callback bị gọi nhiều lần.

Những nguyên tắc cốt lõi:

1. **Ngắt TCP/HTTP ở client không đồng nghĩa server biết ngay.** Không phải mọi framework đều nhận được tín hiệu tức thời khi socket bên kia đóng hoặc mạng mất.
2. **Dừng gửi dữ liệu không tự dừng nguồn dữ liệu.** Một listener do chính ứng dụng đăng ký, timer hay subscription được tạo thủ công có thể vẫn tồn tại dù response đã đóng.
3. **Cleanup phải chạy ở mọi đường kết thúc:** hoàn tất bình thường, timeout, lỗi I/O, client cancellation, server shutdown và error trong pipeline.
4. **Cleanup phải idempotent:** có thể nhận `onError` rồi `onCompletion`, hoặc callback timeout và task gửi cùng chạm vào một session.
5. **Ownership rõ ràng:** đóng tài nguyên do **một session/request** sở hữu; không đóng `WebClient`/connection pool dùng chung chỉ vì một client ngắt.

Phạm vi là **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**. Ví dụ ứng dụng Spring MVC và WebFlux dùng Java 21. Một số chi tiết phát hiện disconnect thuộc server, HTTP protocol, container, proxy và cách mạng thực tế, không được coi là một callback đảm bảo xảy ra ngay lập tức.

## 2. Các kiểu kết nối dài có vòng đời khác nhau

| Kiểu giao tiếp | Hướng dữ liệu | Server biết client rời đi bằng cách nào? | Điểm cleanup |
| --- | --- | --- | --- |
| SSE với Spring MVC `SseEmitter` | Chủ yếu server → browser | Lỗi trong lần ghi, async completion/error/timeout của servlet container | `onCompletion`, `onTimeout`, `onError`, hủy timer/listener |
| SSE WebFlux `Flux<ServerSentEvent<?>>` | Server → browser | Transport phát hiện disconnect và hủy subscription; hoặc pipeline kết thúc | `doFinally`, `using`, `usingWhen`, cleanup upstream |
| WebSocket | Hai chiều | Close frame, transport error/close, idle/heartbeat policy | Session callbacks hoặc reactive termination |
| HTTP streaming/raw response | Server → client | Lỗi `write`/flush, reactive cancellation | `try/finally`, `try-with-resources`, `doFinally` |
| Long polling | Client chờ một response rồi kết thúc | Timeout/complete/cancel request | Loại waiter khỏi registry, dừng timeout task |
| Subscription tới broker/DB change stream | Server ↔ upstream service | Chỉ tự đóng nếu API subscription/cancellation được tích hợp đúng | `unsubscribe`, `Disposable.dispose`, `AutoCloseable.close` |

**Không nhầm SSE với WebSocket:** `EventSource` tự quản lý reconnect theo cơ chế browser; WebSocket có protocol đóng kết nối và hai luồng gửi/nhận. **Không nhầm long polling với SSE:** long polling hoàn thành một response rồi client thường gửi request tiếp, còn SSE giữ HTTP response mở để gửi nhiều events.

Đối tượng thực sự cần dọn phụ thuộc kiến trúc. Với `Flux.interval`, việc cancel upstream thường tự dừng scheduled subscription. Với một listener Kafka, Redis Pub/Sub, JDBC polling, external socket hoặc map session do ứng dụng tự tạo, có thể cần explicit cleanup.

## 3. Vòng đời một session từ lúc đăng ký đến khi giải phóng

```text
Browser mở EventSource / WebSocket / streaming fetch
          |
          v
Server tạo sessionId + ghi nhận stream đang hoạt động
          |
          +--> đăng ký listener tới broker/nguồn events
          +--> tạo timer heartbeat hoặc scheduling task
          +--> giữ một bounded queue/buffer nếu cần
          +--> response / WebSocket vẫn mở
          |
          +----------- các đường kết thúc -------------
          | Client đóng/tab unload (có thể không nhận ngay)
          | Lỗi I/O trong send
          | Server async timeout
          | Người dùng mất quyền/token hết hạn theo policy
          | Nguồn events hoàn tất hoặc trả lỗi
          | Server shutdown/deployment
          v
CLOSE_ONCE / CANCEL_ONCE
          |
          +--> remove session khỏi registry
          +--> unsubscribe nguồn dữ liệu / dispose subscription
          +--> cancel heartbeat/timer
          +--> giải phóng buffer / file / listener riêng của session
          +--> cập nhật active gauge + audit reason
          v
Không còn tài nguyên thuộc phiên kết nối đó
```

Thiết kế tốt nên phân biệt **sự kiện kích hoạt cleanup** và **hành động cleanup thực tế**. Nhiều callback có thể tranh nhau kích hoạt, nhưng một đối tượng/session chỉ cần một lần giải phóng có hiệu lực. Dùng `AtomicBoolean.compareAndSet(false, true)` hoặc loại entry khỏi registry bằng thao tác atomic là cách thông dụng.

**Không giả định luôn nhận một event `CLIENT_DISCONNECTED` chính xác.** Với Servlet, có thể chỉ nhận lỗi ở lần ghi heartbeat sau đó; với WebFlux, `SignalType.CANCEL` cho biết downstream subscription bị cancel, nhưng nó không tự chứng minh nguyên nhân là browser đóng tab (cũng có thể do timeout operator, route cancellation hoặc application code).

## 4. Vì sao không luôn phát hiện disconnect ngay?

Kết nối từ browser tới Spring Boot có thể đi qua:

```text
Browser
  |
  v
CDN / reverse proxy / load balancer
  |
  v
Embedded Tomcat / Reactor Netty
  |
  v
Ứng dụng và nguồn dữ liệu
```

Khi browser đóng tab, TCP socket phía client có thể gửi FIN/RST; nếu mất mạng hoặc NAT silently drops traffic thì server có thể không nhận thông báo tức thời. Reverse proxy đôi khi vẫn giữ **một upstream connection riêng** dù client đã đóng. TCP half-open connection có thể tồn tại cho tới khi ghi, đọc, heartbeat, timeout hoặc tầng network phát hiện lỗi.

Tài liệu Spring Framework về **Spring MVC asynchronous requests** nêu điểm quan trọng: **Servlet API không cung cấp thông báo trực tiếp khi remote client rời đi**; với streaming, cần ghi định kỳ để phát hiện lỗi ghi sau disconnect. Với SSE, lần ghi có thể là một comment-only heartbeat mà client không cần xử lý. Đây là lý do một stream **im lặng vô hạn** có thể giữ tài nguyên lâu hơn dự kiến.

Trong WebFlux/Reactive Streams, server có cơ chế hủy subscription khi nhận biết transport đã đóng; nhưng thời điểm đó vẫn phụ thuộc **khi transport/proxy thực sự nhận ra disconnect**, không phải bộ đếm thời gian cố định trong business logic.

Vì thế có hai nhóm bảo vệ song song:

- **Phát hiện:** heartbeat, I/O errors, WebSocket close/ping-pong, async timeout, socket idle/keepalive và proxy timeout.
- **Dọn dẹp:** cleanup callback, cancellation propagation, resource ownership, registry eviction, shutdown hooks và kiểm thử rò rỉ.

Chỉ tăng timeout hoặc chỉ tạo `onCompletion` callback không đủ nếu hệ thống không có sự kiện nào giúp container thấy kết nối đã chết.

## 5. SSE: `EventSource.close()` chỉ đóng phía browser

Một client JavaScript đơn giản:

```javascript
const source = new EventSource("/events");

source.addEventListener("tick", event => {
  console.log("tick", event.data);
});

source.onerror = () => {
  console.warn("SSE interrupted; browser may reconnect");
};

// Ví dụ khi component bị tháo hoặc người dùng chủ động thoát màn hình:
function stopWatching() {
  source.close();
}
```

`EventSource.close()` yêu cầu browser đóng kết nối SSE và ngăn cơ chế reconnect của **EventSource instance ấy**. Nó **không gọi trực tiếp một method Java `unsubscribe()` ở server**. Backend chỉ dọn sau khi HTTP transport/framework biết response đã kết thúc hoặc gặp lỗi.

Nếu frontend dùng React/Vue/Angular component, phải gọi `close()` trong cleanup của component/subscription lifecycle, không tạo một `EventSource` mới mỗi lần render. Ví dụ logic React:

```jsx
import { useEffect } from "react";

export default function LivePanel() {
  useEffect(() => {
    const source = new EventSource("/events");
    const onTick = event => console.log(event.data);

    source.addEventListener("tick", onTick);

    return () => {
      source.removeEventListener("tick", onTick);
      source.close();
    };
  }, []);

  return <div>Live events</div>;
}
```

Đây là đoạn **component phía browser**, cần project React phù hợp; không phải Java code của Spring Boot. Khi dùng API được xác thực qua cookie hoặc token, cần triển khai chính sách xác thực/CORS/CSRF tương ứng; đừng nhét token bí mật vào URL rồi để nó bị log/cache.

**Không dùng `onerror` như bằng chứng stream vĩnh viễn kết thúc.** Native `EventSource` có cơ chế tự reconnect trên lỗi mạng. Client nên quyết định trường hợp nào cho phép reconnect và khi nào chủ động `close()` theo nghiệp vụ.

## 6. Spring MVC và `SseEmitter`: ba lifecycle callbacks

Spring MVC hỗ trợ trả về `SseEmitter` để stream `text/event-stream`. Các callback then chốt:

| Callback/API | Khi nào được sử dụng | Hành động nên làm |
| --- | --- | --- |
| `onCompletion(Runnable)` | Async request đã hoàn thành; có thể do thành công, timeout hoặc network error | Cleanup resources/registry theo kiểu idempotent |
| `onTimeout(Runnable)` | Servlet async timeout xảy ra | Hủy công việc và cleanup; không giả định status còn sửa được |
| `onError(Consumer<Throwable>)` | Container thông báo lỗi async request | Cleanup, log/metric phù hợp, không tạo response JSON mới |
| `send(...)` | Ghi một event ra HTTP response | Bắt `IOException` và dừng producer của phiên |
| `complete()` | Ứng dụng chủ động hoàn tất stream bình thường | Gọi trong trường hợp nghiệp vụ kết thúc có chủ đích |
| `completeWithError(error)` | Ứng dụng chủ động chuyển lỗi xử lý để framework giải quyết | Không gọi tùy tiện sau `send` bị `IOException` |
| `SseEmitter(Long timeout)` | Timeout theo **mili giây** cho async stream | Chọn theo nhu cầu, không coi timeout này là client heartbeat |

**Điểm đặc biệt sau lỗi I/O:** Spring Framework khuyến cáo khi `SseEmitter.send(...)` ném `IOException` do client đã rời đi, ứng dụng **không chịu trách nhiệm gọi** `emitter.complete()` hoặc `emitter.completeWithError()` ngay ở nhánh lỗi ấy; Servlet container sẽ kích hoạt async error notification và Spring MVC hoàn tất request. Ứng dụng vẫn phải **tự dừng công việc và unregister listener** của mình. Đây là sự khác nhau giữa **container cleanup** và **business resources cleanup**.

`onCompletion` là callback tốt cho việc hủy tài nguyên, nhưng không nên chỉ dựa vào mỗi callback mà không xét `IOException`, timeout và server shutdown. Callback có thể đến **muộn** hơn thời điểm browser đóng.

## 7. Ví dụ Spring Boot MVC hoàn chỉnh: SSE có heartbeat và cleanup idempotent

Ví dụ này dùng **Spring Boot 3.3.13, Java 21, embedded Tomcat**, Gradle Wrapper, phục vụ HTTP trên loopback để thử. Mỗi SSE session có một scheduled task, được dừng khi stream hoàn tất, timeout, lỗi hoặc shutdown. Đây là thiết kế **dễ quan sát về vòng đời**, không phải mẫu tối ưu cho hàng chục nghìn clients; hệ thống lớn nên dùng fan-out/bounded backpressure thay vì mỗi client một scheduled job.

**Cấu trúc source:**

```text
src/main/java/com/example/longconn/
  LongConnectionApplication.java
  StreamSchedulerConfig.java
  ManagedSseController.java
src/main/resources/
  application.properties
build.gradle
```

### 7.1. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 7.2. `src/main/java/com/example/longconn/LongConnectionApplication.java`

```java
package com.example.longconn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LongConnectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(LongConnectionApplication.class, args);
    }
}
```

### 7.3. `src/main/java/com/example/longconn/StreamSchedulerConfig.java`

```java
package com.example.longconn;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StreamSchedulerConfig {

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService sseScheduler() {
        return Executors.newScheduledThreadPool(2);
    }
}
```

Đây là executor **được chia sẻ và được Spring quản lý lifecycle**; ta chỉ hủy `ScheduledFuture` của **một kết nối** khi client đóng, không `shutdown()` toàn bộ executor mỗi lần client ngắt. Spring đóng executor khi application context dừng.

### 7.4. `src/main/java/com/example/longconn/ManagedSseController.java`

```java
package com.example.longconn;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.annotation.PreDestroy;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
public class ManagedSseController {

    private final ScheduledExecutorService scheduler;
    private final ConcurrentMap<UUID, StreamSession> sessions =
            new ConcurrentHashMap<>();
    private final AtomicInteger active = new AtomicInteger();

    public ManagedSseController(ScheduledExecutorService scheduler) {
        this.scheduler = scheduler;
    }

    @GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events() {
        UUID id = UUID.randomUUID();
        SseEmitter emitter = new SseEmitter(90_000L);
        StreamSession session = new StreamSession(id, emitter);
        sessions.put(id, session);
        active.incrementAndGet();

        // Có thể nhiều callback cùng đến; cleanup phải idempotent.
        emitter.onCompletion(session::close);
        emitter.onTimeout(session::close);
        emitter.onError(error -> session.close());

        ScheduledFuture<?> task = scheduler.scheduleAtFixedRate(
                () -> pushTick(session),
                0,
                10,
                TimeUnit.SECONDS);

        // Xử lý race: callback close có thể chạy trước khi gán task.
        session.setTask(task);
        return emitter;
    }

    private void pushTick(StreamSession session) {
        if (session.closed.get()) {
            return;
        }
        try {
            long tick = session.sequence.incrementAndGet();
            session.emitter.send(SseEmitter.event()
                    .name("tick")
                    .id(session.id + ":" + tick)
                    .data("beat-" + tick));
        } catch (IOException disconnected) {
            // Spring MVC/container hoàn tất async I/O error.
            // Chỉ dừng producer và dọn resources của ứng dụng.
            session.close();
        } catch (IllegalStateException alreadyClosed) {
            session.close();
        }
    }

    @GetMapping("/active-streams")
    public int activeStreams() {
        return active.get();
    }

    @PreDestroy
    public void shutdownStreams() {
        for (StreamSession session : sessions.values()) {
            session.close();
            session.emitter.complete();
        }
    }

    private final class StreamSession {
        final UUID id;
        final SseEmitter emitter;
        final AtomicLong sequence = new AtomicLong();
        final AtomicBoolean closed = new AtomicBoolean();
        final AtomicReference<ScheduledFuture<?>> task =
                new AtomicReference<>();

        StreamSession(UUID id, SseEmitter emitter) {
            this.id = id;
            this.emitter = emitter;
        }

        void setTask(ScheduledFuture<?> scheduled) {
            task.set(scheduled);
            if (closed.get()) {
                scheduled.cancel(false);
            }
        }

        void close() {
            if (closed.compareAndSet(false, true)) {
                ScheduledFuture<?> scheduled = task.get();
                if (scheduled != null) {
                    scheduled.cancel(false);
                }
                sessions.remove(id, this);
                active.decrementAndGet();
            }
        }
    }
}
```

**Giải thích những chỗ quan trọng:**

- `SseEmitter(90_000L)` đặt async timeout 90 giây (đơn vị **ms**). Đây là ví dụ quản lý phiên hữu hạn; nếu nghiệp vụ muốn SSE sống lâu hơn, phải cấu hình timeout phù hợp và cơ chế reconnect. Timeout không phải heartbeat interval.
- Mỗi stream có `UUID` riêng; `sessions` cho phép tracking và cleanup khi shutdown. Registry không lưu các session đã được `close()` nếu callbacks/heartbeat hoạt động đúng.
- `onCompletion`, `onTimeout`, `onError` đều gọi **cùng** một `close()`, được bảo vệ bằng `AtomicBoolean.compareAndSet`. `active.decrementAndGet()` chỉ chạy một lần.
- Scheduled task gửi `tick` mỗi 10 giây. Nếu client đóng, lần ghi sau có thể ném `IOException`; code hủy producer ngay. **Không gọi `completeWithError` trong nhánh IOException**, theo hướng dẫn Spring MVC.
- `cancel(false)` không ngắt cưỡng bức một lần `send` đang chạy; nó ngăn những lần chạy kế tiếp. Task/callback có thể chạm vào nhau, nên check `closed` và cleanup phải idempotent.
- `setTask()` kiểm tra `closed` sau khi gán `ScheduledFuture`, tránh race hiếm gặp khi callback gọi `close()` trước lúc `scheduleAtFixedRate` trả về.
- Executor là bean dùng chung; session chỉ sở hữu future. Shutdown hook hủy các sessions còn lại khi application context dừng.
- `/active-streams` chỉ là endpoint quan sát demo, **không public số session hoặc thông tin người dùng trên production** nếu không được bảo vệ. Production nên dùng metric gauge với quyền truy cập giới hạn.

**Giới hạn:** Ví dụ cho dễ học nên dùng một scheduling task cho mỗi client, không có authentication, quotas hoặc slow-client queue. Trong production, cần tách riêng đăng ký vào broker, policy connection limit, per-user cleanup và kiểm soát backpressure. Nếu một `send` chạy quá lâu, `ScheduledExecutorService` có thể bị chiếm threads; không dùng ví dụ này để benchmark tải cao.

### 7.5. `src/main/resources/application.properties`

```properties
server.address=127.0.0.1
server.port=8080

# Giới hạn async mặc định cho những endpoint khác; SSE riêng đã đặt 90s.
spring.mvc.async.request-timeout=90s
```

`server.address=127.0.0.1` giúp demo chỉ nghe loopback; không tự thay thế authentication/authorization khi triển khai public. `spring.mvc.async.request-timeout` thuộc Servlet MVC async request processing; nó không phải socket timeout của browser hoặc load balancer.

## 8. Chạy thử SSE và chủ động cắt kết nối

Trong project mẫu có `gradlew` và Java 21:

```bash
./gradlew bootRun
```

Terminal khác mở SSE bằng `curl`:

```bash
curl -N -i http://127.0.0.1:8080/events
```

Ví dụ các dòng SSE được stream (UUID/tick ID thực khác nhau):

```text
id: 9e5c0...:1
event: tick
data: beat-1

id: 9e5c0...:2
event: tick
data: beat-2
```

Đây là **định dạng minh họa**, không phải stdout byte-exact vì UUID ngẫu nhiên, thời điểm ticks và HTTP headers khác nhau. `curl -N` tắt output buffering phía curl, giúp người học thấy các events khi được flush.

Trong terminal thứ ba:

```bash
curl -s http://127.0.0.1:8080/active-streams
```

Với một client đang mở và không có client khác, body dự kiến là:

```text
1
```

Bấm `Ctrl+C` để dừng `curl -N`. Server **có thể chưa biết ngay**; sau một lần gửi heartbeat/tick hoặc khi container nhận network close, `onError`/`onCompletion` và `session.close()` sẽ dọn task. Khi đã được phát hiện và cleanup xong, `/active-streams` về `0`.

**Không hứa rằng nó sẽ về 0 ngay trong đúng 10 giây** ở mọi hạ tầng: proxy buffering, socket half-open, container behavior, scheduler delay và timeout có thể thay đổi thời gian phát hiện. Test với kết nối thực qua ingress/proxy của hệ thống để biết behavior thực, không chỉ localhost.

Nếu stream timeout sau 90 giây, session cũng được cleanup. Với native `EventSource`, browser có thể tự reconnect và tạo một session mới. Vì vậy tổng `active-streams` không nhất thiết bằng 0 nếu client vẫn liên tục reconnect — cần phân biệt **session cũ được xóa** với **session mới đã tạo**.

## 9. Vì sao cleanup phải idempotent và không phụ thuộc một callback?

Một lần disconnect có thể dẫn đến:

```text
send -> IOException
       |
       +--> application calls session.close()
       |
       +--> Servlet container raises async error
                  |
                  +--> onError -> close()
                  +--> onCompletion -> close()
```

Hoặc:

```text
async timeout -> onTimeout -> close()
              -> onCompletion -> close()
```

Nếu code cleanup không bảo vệ trạng thái, mỗi callback có thể `active--` nhiều lần, cố unsubscribe cùng listener hai lần, đóng connection sai thứ tự hoặc xóa nhầm session mới có cùng user key.

Với `AtomicBoolean`, nhiều callback có thể **cùng gọi** `close()` nhưng chỉ callback thắng `compareAndSet(false,true)` thực hiện side effects. `ConcurrentMap.remove(id, this)` cũng an toàn hơn `remove(id)` khi registry có thể bị cập nhật bởi phiên mới.

**Chú ý:** idempotence không đồng nghĩa cleanup luôn thành công. Nếu `unsubscribe()` hoặc `close()` ném lỗi, cần chiến lược xử lý, metric và đôi khi retry/reconciliation. Với nhiều resources cần đóng, cố gắng giải phóng **tất cả** resources dù một bước thất bại, ví dụ dùng các `try/finally` hoặc `closeQuietly` có logging được kiểm soát. Không giữ lock quá lâu hay thực hiện network I/O blocking trong container callback thread.

Ví dụ Java 17 độc lập cho nguyên tắc chỉ đóng một lần:

**`CloseOnceDemo.java`**

```java
import java.util.concurrent.atomic.AtomicBoolean;

public class CloseOnceDemo {
    static class Subscription implements AutoCloseable {
        private final AtomicBoolean closed = new AtomicBoolean();

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                System.out.println("released");
            }
        }
    }

    public static void main(String[] args) {
        try (Subscription subscription = new Subscription()) {
            System.out.println("active");
            subscription.close();
            subscription.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CloseOnceDemo.java
java CloseOnceDemo
```

**Stdout chính xác:**

```text
active
released
```

Trong `try-with-resources`, `close()` còn được gọi lúc rời block, nhưng side effect `released` chỉ in **một** lần. Đây là mô hình đơn giản hóa của việc hủy đăng ký khi session kết thúc.

## 10. `onCompletion`/`onTimeout` không phải tín hiệu “người dùng đóng tab” chính xác

Dù `onCompletion` hữu ích, nó có thể xảy ra bởi:

- Server chủ động `emitter.complete()`.
- Async request timeout.
- Exception trong xử lý response hoặc network I/O.
- Container/ứng dụng shutdown.
- Client disconnect được transport phát hiện.
- Logic business đã quyết định stream hoàn tất.

Vì vậy đừng luôn ghi log `"user closed browser"` khi `onCompletion` chạy. Ghi reason chính xác khi **biết được** (`SERVER_COMPLETE`, `TIMEOUT`, `IO_FAILURE`); nếu không, dùng `ASYNC_COMPLETE` hoặc `UNKNOWN`. Một `IOException` từ `send` có thể là disconnect, reset, proxy close hoặc vấn đề mạng khác; nó không chứng minh ý định người dùng.

Tương tự, `onTimeout` là timeout của **async request/session** trong server, không phải tín hiệu chắc chắn client đã rời đi. Ở production, metrics và logs nên phân biệt timeout, cancellation, network write error và normal completion để tránh đếm sai lỗi.

Sau khi HTTP headers/body đã được commit để streaming, server thường **không thể chuyển response đang mở thành một JSON 500 có status khác**. Với SSE, có thể phát một event ứng dụng thông báo lỗi nếu connection còn hoạt động và policy cho phép, sau đó hoàn tất. Khi socket đã lỗi, đừng tiếp tục cố ghi thông báo lỗi qua cùng socket.

## 11. `ResponseBodyEmitter`, `StreamingResponseBody` và `DeferredResult`

Ba API Spring MVC có mô hình cleanup khác nhau:

**`ResponseBodyEmitter` / `SseEmitter`:** push nhiều phần dữ liệu từ thread riêng; cần callbacks để dọn event producer/listener. SSE thêm định dạng `text/event-stream`.

**`StreamingResponseBody`:** ghi trực tiếp vào `OutputStream`, phù hợp stream file/lượng bytes lớn. Dùng **try-with-resources** cho `InputStream`/file channel:

```java
@GetMapping("/download")
public StreamingResponseBody download() {
    return output -> {
        try (InputStream input = Files.newInputStream(
                Path.of("/srv/data/public/sample.bin"))) {

            byte[] buffer = new byte[64 * 1024];
            int n;
            while ((n = input.read(buffer)) != -1) {
                output.write(buffer, 0, n);
            }
            output.flush();
        }
    };
}
```

Đây là **mẫu method tích hợp**, chưa phải source độc lập: cần import `InputStream`, `Files`, `Path`, `GetMapping`, `StreamingResponseBody`, có file thật và security phù hợp. Khi `output.write` ném `IOException` do client ngắt, try-with-resources vẫn đóng file. Không bắt lỗi rồi cố tiếp tục ghi trên output đã hỏng. Trên Servlet stack, write/flush có thể blocking; nên cấu hình `AsyncTaskExecutor` phù hợp khi dùng `StreamingResponseBody` dưới tải.

**`DeferredResult<T>`:** chờ **một** kết quả không đồng bộ, không phải SSE stream nhiều events. Khi có timeout/completion, bỏ waiter khỏi map/queue, hủy scheduled timeout và ngắt upstream task có thể hủy. Đừng giữ một `DeferredResult` đã timeout trong registry rồi cố `setResult` về sau.

Ví dụ logic cleanup:

```java
DeferredResult<String> pending = new DeferredResult<>(30_000L);
pending.onCompletion(() -> waiters.remove(requestId));
pending.onTimeout(() -> waiters.remove(requestId));
```

Đây là **mẫu tích hợp**, cần registry `waiters` và `requestId` thực tế; chọn cùng một hàm close-once nếu còn timers/listeners khác. `setResult(...)` trả `false` nếu request đã không còn chấp nhận kết quả theo contract cụ thể; không bỏ qua giá trị return khi ứng dụng cần biết result có được chấp nhận không.

## 12. WebFlux: client disconnect trở thành cancellation trong Reactive Streams

Với Spring WebFlux và Reactor Netty, controller có thể trả `Flux<ServerSentEvent<String>>`. Server subscribe vào `Flux` để gửi HTTP stream. Khi response kết thúc hoặc connection bị đóng và transport phát hiện, downstream subscription có thể phát tín hiệu **cancel** lên publisher.

```text
Browser HTTP SSE
     |
     v
Reactor Netty response writer [subscriber]
     |
     +--> cancel (khi transport/người dùng dừng theo điều kiện thực tế)
     |
     v
Flux<ServerSentEvent<?>>
     |
     +--> doFinally(CANCEL)
     +--> upstream subscription dispose / resource cleanup
     |
     v
Source (interval / listener / broker / file I/O)
```

Reactor cung cấp tín hiệu:

| `SignalType` | Ý nghĩa |
| --- | --- |
| `ON_COMPLETE` | Publisher hoàn tất bình thường |
| `ON_ERROR` | Publisher kết thúc lỗi |
| `CANCEL` | Subscriber/upstream chain bị hủy do downstream không còn yêu cầu dữ liệu |
| Các tín hiệu khác | Dành cho subscribe/request/next...; `doFinally` dùng các terminal paths |

`doFinally(signalType -> ...)` chạy khi một **subscription** kết thúc vì complete, error hoặc cancel. Nó hữu ích cho metrics và cleanup side effects; **khác** `doOnComplete` (không chạy khi cancel) và `doOnError` (không chạy khi complete/cancel).

`Flux.defer(...)` giúp tạo resource và tăng bộ đếm **riêng cho từng subscription**, tránh mở tài nguyên ngay lúc controller tạo đối tượng Flux nhưng chưa có người subscribe.

Không dùng `doOnCancel` đơn độc để dọn mọi resource nếu cũng có đường `ON_COMPLETE`/`ON_ERROR`; dùng `doFinally` hoặc resource-ownership operators phù hợp.

## 13. Ví dụ Spring Boot WebFlux hoàn chỉnh: SSE cancellation tự giải phóng

Đây là **dự án khác**, không trộn trực tiếp với Spring MVC demo mục 7. Spring Boot có thể chọn Servlet web application type nếu cùng có `spring-boot-starter-web` và `spring-boot-starter-webflux`; để minh họa WebFlux/Reactor Netty hãy dùng **chỉ WebFlux starter**.

### 13.1. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 13.2. `src/main/java/com/example/reactivestream/ReactiveStreamApplication.java`

```java
package com.example.reactivestream;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveStreamApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveStreamApplication.class, args);
    }
}
```

### 13.3. `src/main/java/com/example/reactivestream/ReactiveSseController.java`

```java
package com.example.reactivestream;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@RestController
public class ReactiveSseController {

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicLong cancelled = new AtomicLong();

    @GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.defer(() -> {
            String streamId = UUID.randomUUID().toString();
            active.incrementAndGet();

            return Flux.interval(Duration.ZERO, Duration.ofSeconds(5))
                    .map(n -> ServerSentEvent.<String>builder()
                            .event("tick")
                            .id(streamId + ":" + n)
                            .data("beat-" + n)
                            .build())
                    .doFinally(signal -> {
                        active.decrementAndGet();
                        if (signal == SignalType.CANCEL) {
                            cancelled.incrementAndGet();
                        }
                    });
        });
    }

    @GetMapping("/stream-metrics-demo")
    public Map<String, Long> metrics() {
        return Map.of(
                "active", (long) active.get(),
                "cancelled", cancelled.get());
    }
}
```

**Vì sao ví dụ này cleanup được?**

- `Flux.defer` chạy mỗi khi request **được subscribe**; mỗi request có streamId và biến active riêng theo lần subscribe.
- `Flux.interval` tạo publisher định kỳ. Khi downstream cancel, upstream subscription được hủy và task định kỳ của **subscription đó** được dispose; không cần tự quản lý một `ScheduledFuture` riêng trong controller.
- `doFinally` giảm `active` khi complete/error/cancel. `cancelled` chỉ tăng với `SignalType.CANCEL`, không gắn nhãn mọi kết thúc là browser disconnect.
- `ServerSentEvent` do Spring WebFlux serialize thành `text/event-stream`, event có `id` và `event` name rõ ràng.
- Không dùng `subscribe()` thủ công trong controller. **Framework là subscriber của HTTP response**, nên cancellation có đường truyền ngược lên upstream.

**Lưu ý:** Ví dụ không có broker listener/DB connection bên ngoài. Với các resources đó cần `using`/`usingWhen` hoặc cleanup trực tiếp. `Flux.interval` ở đây dùng shared Reactor scheduler; việc cancel task của một subscription **không được shutdown toàn bộ scheduler dùng chung**.

### 13.4. `src/main/resources/application.properties`

```properties
server.address=127.0.0.1
server.port=8080
```

Chạy:

```bash
./gradlew bootRun
curl -N http://127.0.0.1:8080/events
```

Ở terminal khác:

```bash
curl -s http://127.0.0.1:8080/stream-metrics-demo
```

Nếu một stream vẫn đang hoạt động, response JSON **có thể** tương tự:

```json
{"active":1,"cancelled":0}
```

Khi dừng `curl` và transport/server xử lý cancellation, `active` sẽ giảm và `cancelled` thường tăng. Thời điểm và count chính xác phụ thuộc kết nối và các request khác. **Không khẳng định browser bấm close thì `CANCEL` xuất hiện đồng bộ ngay lập tức**.

## 14. Kiểm thử hủy đăng ký với Reactor `StepVerifier`

Kiểm thử ở tầng publisher giúp kiểm chứng **cleanup khi downstream cancel** mà không phụ thuộc TCP và proxy. Với project WebFlux ở mục 13, dùng `reactor-test`:

**`src/test/java/com/example/reactivestream/ReactiveSseControllerTest.java`**

```java
package com.example.reactivestream;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.http.codec.ServerSentEvent;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReactiveSseControllerTest {

    @Test
    void cancellationStopsStreamAndUpdatesCounters() {
        ReactiveSseController controller = new ReactiveSseController();

        Flux<ServerSentEvent<String>> flux = controller.events();

        StepVerifier.create(flux)
                .expectNextMatches(
                        item -> "beat-0".equals(item.data()))
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        assertThat(controller.metrics().get("active")).isZero();
        assertThat(controller.metrics().get("cancelled")).isEqualTo(1L);
    }
}
```

Chạy:

```bash
./gradlew test
```

Đây là **unit test của Reactor chain**, không phải integration test đo bao lâu Servlet/Netty phát hiện một TCP disconnect. `StepVerifier` chủ động phát **cancel** vào subscription và kiểm tra `doFinally` chạy, `active` về 0. Với các pipelines bất đồng bộ phức tạp hơn, nên dùng latch/`Awaitility` để chờ cleanup thay vì giả định callback đã hoàn tất tại một thời điểm tuyệt đối.

Muốn test end-to-end, dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` và `WebTestClient`/HTTP client thật subscribe SSE, sau đó cancel/dispose client và **đợi có giới hạn** cho server metric trở về baseline. Đừng viết assertion “server phải nhận disconnect trong 10 ms”, vì phụ thuộc transport và scheduler.

## 15. Hủy một subscription không tự động hủy subscription tự tạo bằng `subscribe()`

Anti-pattern nguy hiểm trong reactive code:

```java
// Sai mô hình: ứng dụng tự subscribe một upstream vô hạn.
Disposable upstream = brokerEvents.subscribe(event -> queue.offer(event));

// Controller trả stream từ queue; khi client rời đi, upstream vẫn chạy
// nếu không có cơ chế gắn vòng đời của upstream với HTTP subscription.
return queueFlux;
```

Đây là **mẫu minh họa**, các biến `brokerEvents`, `queue`, `queueFlux` cần được định nghĩa riêng. Điểm lỗi là **subscription do chính ứng dụng sở hữu** có vòng đời tách khỏi subscription của HTTP response. Khi browser disconnect, Spring có thể cancel `queueFlux` nhưng không tự biết để gọi `upstream.dispose()`.

Cách thiết kế tốt hơn là **nối trực tiếp** reactive stream vào response:

```java
return brokerEvents
        .filter(this::isAuthorizedEvent)
        .map(this::toSse)
        .doFinally(signal -> recordTermination(signal));
```

Đây là **mẫu tích hợp**, các helper do nghiệp vụ định nghĩa. Nếu `brokerEvents` tuân thủ Reactive Streams và truyền cancellation upstream, `cancel` có thể giải phóng subscriber của broker. Nếu broker SDK đòi `unsubscribe` riêng, cần adapter giải phóng tài nguyên tương ứng.

Khi bắt buộc tạo `Disposable` bằng `subscribe()` thủ công, phải **gắn `dispose()` của nó với cleanup của đúng HTTP session**, và xử lý cả complete/error. Nên ưu tiên API xây cold publisher/managed resource cho từng subscriber hơn là tạo một global hot subscription cho từng request rồi quên giữ handle.

## 16. `using` và `usingWhen`: sở hữu tài nguyên xuyên suốt một subscription

`doFinally` phù hợp cho side effect (giảm counter, metrics, log). Khi cần một resource phải mở khi subscribe và đóng chắc chắn khi kết thúc, Reactor cung cấp:

- `Flux.using(resourceSupplier, resourceToPublisher, resourceCleanup)` cho cleanup **đồng bộ**.
- `Flux.usingWhen(resourcePublisher, resourceClosure, asyncComplete, asyncError, asyncCancel)` cho cleanup **bất đồng bộ**.

Ví dụ **pseudocode tích hợp** với API broker giả định:

```java
Flux<Event> liveEvents = Flux.using(
        () -> broker.openSubscription(topic),
        handle -> handle.events(),
        handle -> handle.close());
```

Ở đây `broker`, `Event`, `handle.events()` và `close()` là interfaces **do ứng dụng định nghĩa**, không phải API mặc định của Spring. Hợp đồng thiết kế là mỗi subscriber mở đúng một handle và `Flux.using` gọi cleanup khi complete, error hoặc cancel.

Nếu đóng subscription đòi network call bất đồng bộ:

```java
Flux<Event> liveEvents = Flux.usingWhen(
        broker.openSubscriptionAsync(topic),
        handle -> handle.events(),
        handle -> handle.closeAsync(),
        (handle, error) -> handle.closeAsync(),
        handle -> handle.closeAsync());
```

Đây cũng là pseudocode; `closeAsync()` phải trả về `Publisher` hoàn tất sau khi đã release resource. Dạng ba nhánh giúp định nghĩa cleanup cho normal completion, error và cancel. **Không tạo `Mono<Void>` cleanup rỗng rồi tưởng resource đã được đóng**.

Những lưu ý:

1. Cleanup **theo từng subscription**, không dùng một resource mutable dùng chung cho tất cả clients rồi đóng khi bất kỳ client nào cancel.
2. Cleanup phải idempotent hoặc được operator bảo đảm gọi đúng cách trong phạm vi được thiết kế; ứng dụng vẫn cần xử lý race tại các callback/lifecycle khác.
3. Với blocking cleanup (JDBC close, filesystem sync, SDK không reactive), không block Reactor event-loop. Bố trí scheduler phù hợp hoặc chuyển sang client non-blocking.
4. Khi cleanup có thể thất bại, phải xác định policy báo lỗi/metrics/retry; không giả định lỗi cleanup luôn “nuốt” an toàn.
5. `doFinally` đặt trên một hot shared publisher hoặc sau `share()` có thể chỉ phản ánh **một subscription của một tầng**; cần xem stream sharing/reference count thực tế trước khi quyết định đóng upstream globally.

## 17. WebSocket: close frame, transport error và registry cleanup

Khác SSE, WebSocket có protocol hai chiều, close handshake và cơ chế ping/pong ở transport. Với Spring Servlet WebSocket stack, `WebSocketHandler` có các lifecycle methods:

| Method | Ý nghĩa |
| --- | --- |
| `afterConnectionEstablished(session)` | Handshake xong, có WebSocket session |
| `handleMessage(session, message)` | Nhận message |
| `handleTransportError(session, exception)` | Lỗi transport/session |
| `afterConnectionClosed(session, closeStatus)` | Kết nối đóng, dọn registry/listener |
| `session.close(status)` | Server chủ động bắt đầu đóng session theo protocol |

Một skeleton MVC WebSocket minh họa **quản lý registry**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

public class TrackingWebSocketHandler extends TextWebSocketHandler {
    private final ConcurrentMap<String, WebSocketSession> sessions =
            new ConcurrentHashMap<>();

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        sessions.put(session.getId(), session);
    }

    @Override
    public void handleTransportError(
            WebSocketSession session, Throwable exception) {
        cleanup(session);
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session, CloseStatus status) {
        cleanup(session);
    }

    private void cleanup(WebSocketSession session) {
        sessions.remove(session.getId(), session);
        // Unsubscribe / cancel per-session producer ở đây nếu có.
    }
}
```

Đây là **đoạn class minh họa**, cần WebSocket configuration/handler mapping và dependencies tương ứng để có endpoint thật. `sessions.remove(key, session)` tránh xóa nhầm một entry khác khi có cập nhật đồng thời. Nếu session lỗi nhưng chưa đóng, sản phẩm cần policy đóng session và giải phóng producer; không chỉ remove map trong khi socket vẫn giữ tài nguyên.

Với WebSocket broadcast, đừng gửi đồng thời từ nhiều threads vào một `WebSocketSession` mà không bảo đảm concurrency của session implementation. Spring có `ConcurrentWebSocketSessionDecorator` để quản lý concurrent sends và giới hạn send/buffer khi dùng Servlet stack; slow clients cần bị giới hạn hoặc đóng theo chính sách.

Ping/pong và idle timeouts cần tương thích proxy/load balancer, không chỉ application-level `onclose` của browser. Một kết nối mất mạng im lặng vẫn có thể chỉ được phát hiện sau heartbeat/timeout.

## 18. WebFlux WebSocket: hợp nhất inbound và outbound lifecycles

Trong reactive WebFlux, handler thường có dạng:

```java
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> outgoing =
            Flux.interval(Duration.ofSeconds(1))
                    .map(n -> session.textMessage("tick-" + n));

    Mono<Void> sending = session.send(outgoing);
    Mono<Void> receiving = session.receive().then();

    return Mono.firstWithSignal(sending, receiving)
            .doFinally(signal -> recordSessionEnd(signal));
}
```

Đây là **mẫu tích hợp** cần `WebSocketHandler`, `WebSocketSession`, Reactor `Flux`/`Mono`, method `recordSessionEnd(...)` và `HandlerMapping` thực tế. `session.receive()` hoàn tất khi inbound stream đóng; `session.send(outgoing)` là outbound stream. Trong ví dụ có outbound vô hạn, `Mono.firstWithSignal(...)` kết thúc khi một bên hoàn tất/lỗi rồi **hủy** bên còn lại, nhờ đó sender không phát vô hạn sau khi inbound socket đóng.

Nếu chỉ viết:

```java
return session.send(outgoing);
```

trong khi source outbound vô hạn, handler có thể không quan sát được **điều kiện kết thúc inbound** theo ý định nghiệp vụ; transport có thể vẫn hủy khi socket thật bị đóng, nhưng thiết kế composition phải nói rõ “session kết thúc theo nhánh nào”.

Spring Framework WebFlux documentation mô tả `WebSocketSession.send(...)` và `receive()` như hai streams cần được **hợp thành một lifecycle thống nhất**. Nếu upstream broker subscription nằm trong `outgoing`, bảo đảm cancel của `Mono` kéo theo hủy broker source hoặc dùng `usingWhen` khi SDK đòi cleanup bất đồng bộ.

Không đóng **shared Reactor Netty event-loop** hoặc scheduler toàn ứng dụng khi một WebSocket session kết thúc. Chỉ cleanup tài nguyên thuộc session.

## 19. `WebClient` phía client: cancellation cũng phải giải phóng connection

Ngoài server-side SSE, một ứng dụng Spring Boot có thể **đóng vai HTTP client** đăng ký stream từ service khác:

```java
Disposable subscription = webClient.get()
        .uri("/events")
        .retrieve()
        .bodyToFlux(String.class)
        .subscribe(this::consumeEvent);
```

Đây là **mẫu tích hợp**: `webClient`, `consumeEvent` là thành phần do ứng dụng định nghĩa. Việc gọi `subscribe()` trực tiếp là quyết định tự quản lý lifecycle. Nếu người dùng không còn theo dõi stream, hoặc service shutdown, phải gọi:

```java
subscription.dispose();
```

Nhưng **không** coi `dispose()` là một lời bảo đảm socket đã được đóng/đưa về pool trong đúng mili giây, hoặc upstream broker ở remote server đã hủy ngay. Reactor Netty xử lý cancellation khi được truyền xuống transport; remote server cần nhận biết ngắt và thực hiện cleanup tương ứng.

Tốt hơn, ở nhiều endpoint có thể **trả nguyên Publisher** cho framework thay vì tự `subscribe()`:

```java
@GetMapping(path = "/proxy-events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> relay() {
    return webClient.get()
            .uri("/events")
            .retrieve()
            .bodyToFlux(String.class);
}
```

Đây là ví dụ code tích hợp cho Spring WebFlux, cần inject `WebClient` và cấu hình base URL. Khi client upstream chain được compose trực tiếp vào HTTP response, cancellation **có đường truyền** từ downstream tới `WebClient` exchange. Nếu giữa đường ứng dụng dùng `cache`, `share`, `publish`, `replay`, hoặc tạo hot subscription riêng thì semantics có thể đổi; phải xác định ai sở hữu upstream subscription.

**Không đóng connection pool của `WebClient` dùng chung** sau từng request. Dispose per-request subscription khác hoàn toàn shutdown Reactor Netty `ConnectionProvider`/HTTP resources chung.

## 20. `AbortController` với streaming `fetch`: client có trách nhiệm hủy

Nếu frontend dùng `fetch` streaming response thay vì native `EventSource`:

```javascript
const controller = new AbortController();

async function watchStream() {
  const response = await fetch("/stream", {
    signal: controller.signal
  });

  if (!response.ok || !response.body) {
    throw new Error("Stream unavailable");
  }

  const reader = response.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      console.log("received bytes", value.length);
    }
  } finally {
    reader.releaseLock();
  }
}

function stopWatching() {
  controller.abort();
}
```

Đây là đoạn browser JavaScript; cần gọi `watchStream()` và xử lý promise rejection trong frontend thật. `AbortController.abort()` yêu cầu hủy request/stream ở phía client. `reader.releaseLock()` trả quyền sở hữu stream reader, **không tự thay thế** `abort()` khi cần chủ động chấm dứt network request.

Nếu bỏ giữa vòng đọc mà không abort/cancel, kết nối có thể vẫn mở. Khi biết không tiếp tục đọc nữa, có thể dùng `reader.cancel()` theo API Streams và đảm bảo lỗi/cancellation được xử lý. Các framework UI cần gắn lệnh hủy vào component unmount, navigation và lifecycle của user session.

Như SSE, server có thể chỉ phát hiện sự kiện đóng sau khi transport đưa tín hiệu tới nó; không cam kết browser abort làm server callback chạy tức thời.

## 21. Hủy khi client rời đi khác với timeout và đóng chủ động ở server

| Trigger | Client/server làm gì? | Cleanup bắt buộc? |
| --- | --- | --- |
| Client gọi `EventSource.close()` | Browser đóng SSE và ngừng reconnect | Có, khi server biết stream kết thúc |
| Client `AbortController.abort()` | Hủy HTTP fetch/stream | Có |
| Client WebSocket `close(code, reason)` | Bắt đầu WebSocket close handshake | Có |
| Proxy idle timeout | Proxy đóng hoặc reset connection | Có, khi backend nhận biết |
| Spring MVC async timeout | Container gọi timeout lifecycle | Có |
| Reactor `.timeout(Duration)` | Publisher phát lỗi timeout và cancel upstream | Có |
| Nguồn dữ liệu hoàn tất | Server chủ động complete response | Có |
| Authentication bị thu hồi | Ứng dụng chủ động close/cancel theo policy | Có |
| Server shutdown/redeploy | Dừng nhận sessions mới và drain/close sessions cũ | Có |

Timeout là chính sách **liveness**; user cancellation là **thay đổi nhu cầu dữ liệu**; server shutdown là **chuyển vòng đời hệ thống**. Chúng đều phải giải phóng tài nguyên, nhưng reason code và response/close behavior có thể khác.

Đừng tự thêm một cơ chế `setTimeout(0)`/timeout “vô hạn” chỉ để tránh disconnect nếu môi trường có gateway idle timeout thấp hơn. Thay vào đó, thống nhất handshake/heartbeat/lifetime/reconnect giữa client, proxy và backend.

Với trường hợp server chủ động kết thúc SSE, có thể gửi một **event nghiệp vụ `done`** và hoàn tất stream. Client không nên dựa vào một thông báo đó nếu network đã rơi; cần logic reconnect/idempotency theo use case.

## 22. Heartbeat và proxy buffering: cấu hình sai làm cleanup chậm

SSE có thể gửi comment heartbeat theo định dạng:

```text
: heartbeat

```

Client EventSource bỏ qua dòng comment như một event ứng dụng; transport vẫn có bytes để kiểm tra liveness. Với `SseEmitter`, tạo comment event:

```java
emitter.send(SseEmitter.event().comment("heartbeat"));
```

Khi dùng NGINX hay reverse proxy, cần kiểm tra response buffering/timeout. Nếu proxy giữ bytes trong buffer thay vì flush xuống client, heartbeat có thể không đến browser đúng thời điểm; phía backend và proxy còn có kết nối riêng.

Ví dụ **khái niệm** với NGINX cho route SSE cụ thể:

```nginx
location /events {
    proxy_pass http://127.0.0.1:8080;
    proxy_buffering off;
    proxy_read_timeout 120s;
}
```

Đây không phải cấu hình production hoàn chỉnh: cần routing, TLS, auth, upstream, idle timeouts, header sanitation và kiểm tra NGINX version. `proxy_read_timeout` thường đo **khoảng im lặng giữa các lần đọc từ upstream**, không phải tổng lifetime của SSE. Đặt heartbeat **ngắn hơn idle timeout nhỏ nhất** trong đường kết nối, đồng thời tránh quá dày gây tải.

Một số triển khai dùng response header `X-Accel-Buffering: no` cho NGINX, nhưng đây là cơ chế vendor-specific, không thay thế cấu hình proxy và không được mọi CDN tuân theo.

**Heartbeat không phải keepalive bảo mật**: cần giới hạn số connections, xác thực, per-user session quota và chống abuse. Không gửi heartbeat mỗi vài mili giây cho hàng chục nghìn users.

## 23. Slow consumer và backpressure: dọn trước khi bộ nhớ tăng vô hạn

Giả sử broker phát 10.000 sự kiện/giây, nhưng một browser chỉ đọc được 100 sự kiện/giây. Nếu ứng dụng tạo một queue không giới hạn cho từng client, bộ nhớ tăng ngay cả khi socket vẫn “đang kết nối”. Trước khi mất kết nối, server có thể cạn RAM hoặc giữ quá nhiều `DataBuffer`.

Các lựa chọn tùy nghiệp vụ:

| Chiến lược | Phù hợp | Rủi ro/đánh đổi |
| --- | --- | --- |
| Bounded queue per client | Giới hạn memory với burst nhỏ | Phải định nghĩa khi queue đầy |
| Drop/latest/coalesce | Dashboard trạng thái chỉ cần giá trị mới | Có thể mất sự kiện trung gian |
| Disconnect slow consumer | Cần bảo vệ hệ thống khỏi client quá chậm | Client cần reconnect/resume |
| Batch/throttle | Nhiều updates, có thể gộp | Tăng latency và thay đổi granularity |
| Replay từ durable log + cursor | Events có ý nghĩa và cần độ tin cậy | Cần storage, offset và ordering |
| Backpressure upstream | Source reactive hỗ trợ demand | Không phải SDK/broker nào cũng tuân thủ |

Reactor `onBackpressureLatest()` là **chính sách mất dữ liệu có chủ đích**, không phù hợp cho giao dịch/đơn hàng nếu mọi event phải được nhận. Với events quan trọng, nên dùng durable event log, per-client offset, reconnect + resume và giới hạn tốc độ; không giữ tất cả events mãi trong RAM.

Nếu phải ngắt client khi quá chậm, hãy đóng đúng session và giải phóng upstream listener/queue ngay. **Không để listener tiếp tục đẩy vào một queue mà không ai đọc**.

SSE từ browser theo HTTP/1.1 còn có giới hạn connection per origin ở một số client/browser. WebSocket/HTTP2 có semantics concurrency khác. Không lấy con số pool TCP connections để suy trực tiếp số logical subscribers đang giữ.

## 24. Buffer ownership với WebFlux/Netty: cancellation có thể làm rò bộ nhớ off-heap

Trong Spring WebFlux, `DataBuffer` có thể bọc Netty `ByteBuf` dùng **reference counting**. Khi ứng dụng tự giữ, biến đổi hoặc bỏ một buffer, nó phải tôn trọng ownership: buffer giữ lại cần `retain` khi thật sự cần kéo dài vòng đời và `release` khi không dùng nữa.

Ví dụ nếu pipeline tự drop `DataBuffer` ở operator nào đó:

```java
Flux<DataBuffer> processed = source
        .filter(this::isWanted)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Đây là **mẫu tích hợp**, các biến `source`, `isWanted` cần định nghĩa, và phải biết operator nào sở hữu buffer. `doOnDiscard` giúp giải phóng **buffers đã bị loại bỏ** bởi các operators hỗ trợ discard hooks. Không nên `release` mọi buffer ngay sau khi đã đưa cho response writer nếu writer vẫn cần đọc bytes — làm vậy có thể tạo use-after-release.

Một số APIs của Spring, như `DataBufferUtils.join`, có contract quản lý release khi cancellation/error; đừng release một buffer **hai lần**. Đọc tài liệu từng API để biết ownership, đặc biệt khi dùng `DataBufferUtils.read(...)`, `response.writeWith(...)` hoặc custom codecs.

**Rò rỉ memory ngoài heap** có thể xảy ra dù Java heap không tăng nhiều. Khi nghi vấn, xem Netty leak detection, direct memory usage, pooled buffer metrics và code transformation/discard theo yêu cầu của production, không chỉ heap dump.

## 25. Resource cleanup theo ownership: đóng cái của session, giữ cái shared

| Tài nguyên | Scope điển hình | Cleanup đúng |
| --- | --- | --- |
| Entry `sessionId → emitter/session` | Một connection | Remove entry atomic/idempotent |
| Listener đăng ký broker cho một browser | Một connection | `unsubscribe()`/`close()` khi session kết thúc |
| `Disposable` từ `subscribe()` thủ công | Một subscription | `dispose()` |
| `ScheduledFuture` heartbeat | Một connection | `cancel(false)` hoặc theo interrupt policy |
| `ScheduledExecutorService` bean dùng chung | Toàn application | Shutdown lúc context dừng, **không** mỗi client |
| Shared `WebClient`/Reactor Netty resources | Toàn application | Application lifecycle quản lý |
| WebSocket session | Một socket | Close frame / lifecycle callback rồi remove |
| File `InputStream` trong streaming response | Một request | `try-with-resources` |
| JDBC connection/transaction đã mở | Một operation | Release/rollback theo transaction boundary |
| Netty `DataBuffer` ứng dụng tự giữ | Một buffer | Release theo ownership contract |
| Queue per client | Một connection | Clear/close, bounded capacity |
| Metrics counter/gauge | Toàn application | Cập nhật theo session lifecycle, tránh tag theo raw user IDs |

**Không đóng shared broker connection** khi một client unsubscribe nếu broker có nhiều subscribers trên connection ấy. Thường cần `subscription.unsubscribe()` cho một topic/subscriber, trong khi client connection dùng chung sống tới khi service shutdown. Phân biệt subscription handle với transport/client object.

Ngược lại, **không giữ `userId` làm key duy nhất** nếu một người có nhiều tabs/devices. Nếu tab A đóng và code xóa mọi listeners theo userId, tab B có thể mất dữ liệu. Dùng sessionId/subscriptionId đủ chính xác và tham chiếu tới owner theo cấu trúc registry được thiết kế.

Nếu user logout/thu hồi quyền, policy có thể yêu cầu đóng tất cả sessions của user; đây là **hành động nghiệp vụ có chủ đích**, không được nhầm với cleanup khi một tab rời đi.

## 26. SSE tự reconnect: hủy đăng ký cũ và khôi phục trạng thái mới

Native `EventSource` thường tự reconnect sau một số lỗi mạng. Điều này tạo chuỗi:

```text
session A đang mở
   -> client mất mạng
   -> server phát hiện và cleanup A (có thể trễ)
   -> browser reconnect tạo session B
   -> server đăng ký B
```

Có thời điểm **A chưa được dọn nhưng B đã được tạo**. Nếu registry chỉ có `Map<userId, SseEmitter>` và overwrite entry A bằng B, callback A chạy muộn có thể `remove(userId)` và **xóa nhầm B**. Cần dùng `sessionId` duy nhất hoặc `map.remove(userId, expectedSession)` khi phù hợp, và quản lý nhiều sessions của cùng user.

SSE có trường `id:` và browser có thể gửi `Last-Event-ID` khi reconnect. Chúng hữu ích để resume **nếu** server có durable event source và chính sách replay. Nhưng `Last-Event-ID` **không tự biến hệ thống thành exactly-once delivery**; cần xử lý duplicates, ordering và idempotent consumers.

Giới hạn số sessions trên user/tenant, dùng connection expiry và cleanup cho trường hợp half-open, tránh reconnect storm sau restart. Thêm jitter/backoff ở các lớp được phép để hàng nghìn browsers không reconnect đồng thời khi gateway khôi phục.

Nếu bảo mật yêu cầu token hết hạn khi session đang mở, không chỉ xác thực tại handshake rồi mặc nhiên cho stream vô hạn. Xác định policy reconnect/re-auth/forced-close phù hợp; tránh ghi token vào SSE event IDs hoặc URL logs.

## 27. Long polling: rút waiter khỏi hàng đợi khi client timeout/cancel

Với long polling, client gửi:

```http
GET /notifications/wait
```

Backend giữ request tối đa, ví dụ 25 giây, rồi trả event hoặc response rỗng. Nguồn events có thể là broker và server thường có `Map<userId, List<DeferredResult<...>>>`.

Nếu request timeout hoặc client rời đi mà waiter vẫn ở map:

- Event kế tiếp có thể cố ghi vào một `DeferredResult` không còn hợp lệ.
- Registry phình to theo thời gian.
- Một user reconnect có thể tạo nhiều stale waiters.
- Scheduled task timeout vẫn chạy dù waiter đã hoàn thành.

Mẫu quản lý:

```java
DeferredResult<ResponseEntity<?>> waiter =
        new DeferredResult<>(25_000L);

Runnable cleanup = () -> pendingWaiters.remove(waiterId, waiter);
waiter.onCompletion(cleanup);
waiter.onTimeout(cleanup);
waiter.onError(error -> cleanup.run());
```

Đây là **mã tích hợp minh họa**, cần imports, registry `pendingWaiters`, ID `waiterId` và logic đặt kết quả thực tế. Khi event đến, kiểm tra `setResult(...)` thành công hay không; dọn waiter sau hoàn tất. Nếu có timer riêng, cleanup còn phải cancel timer và remove broker listener.

`DeferredResult` dùng để trả một kết quả, không stream nhiều events trong cùng HTTP response. Khi client chờ lâu rồi ngắt giữa chừng, callback/container behavior cũng phụ thuộc Servlet async lifecycle; không đòi hỏi cleanup ngay đúng thời điểm ở phía browser.

## 28. WebSocket ping/pong và idle timeout

WebSocket có control frames `Ping`/`Pong` và close handshake. Chúng giúp xác nhận liveness và giải phóng connection bị treo, nhưng chỉ hiệu quả khi được cấu hình đúng với **server implementation** và đường network thực tế. Trong browser, JavaScript WebSocket API **không cho gửi ping frames trực tiếp**; browser tự xử lý protocol-level ping/pong theo implementation. Ứng dụng có thể gửi message heartbeat riêng nếu cần tín hiệu ở application layer.

Ví dụ client JavaScript:

```javascript
const socket = new WebSocket("wss://example.test/live");

socket.onmessage = event => console.log(event.data);
socket.onclose = event => console.log("closed", event.code);
socket.onerror = () => console.log("transport error");

function leavePage() {
  if (socket.readyState === WebSocket.OPEN) {
    socket.close(1000, "client leaving");
  }
}
```

Đây là ví dụ browser-side, hostname là minh họa. `onclose` được gọi cho cả close thông thường và một số tình huống lỗi. `onerror` không cung cấp lý do chi tiết đáng tin cậy cho bảo mật hoặc audit. Server vẫn phải có `afterConnectionClosed`/reactive session termination và cleanup idempotent, kể cả khi browser không gửi close frame vì mạng đứt.

Khi một proxy đóng WebSocket sau idle timeout, hãy đối chiếu ping interval, proxy/read idle timeout, server idle timeout và reconnect policy. Đừng chỉ tăng server timeout vô hạn để che việc không có liveness check.

## 29. Kiểm thử lỗi/timeout/disconnect mà không phụ thuộc may rủi

Một chiến lược kiểm thử tốt dùng **hai tầng**:

**A. Unit test cancellation và cleanup logic:** Reactor `StepVerifier.thenCancel`, `AtomicBoolean`, `CountDownLatch`, `CloseOnceDemo` kiểm tra side effects một lần. Với MVC, trích logic cleanup thành `StreamSession`/service có thể test độc lập, không cần browser thật.

**B. Integration test qua socket HTTP thật:** Start server trên random port hoặc staging endpoint; mở SSE bằng HTTP client, nhận event đầu rồi chủ động đóng response/connection; đợi **có giới hạn** cho active streams, registry size, scheduled futures và upstream listener count về baseline.

Test cases cần thiết:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Client đọc 1 event rồi đóng SSE | Subscription/producer của session cũ được hủy khi server phát hiện |
| Client đóng khi server chuẩn bị gửi | Không double cleanup, không âm counter |
| Async timeout | Timer/listener bị cancel; session rời registry |
| Broker trả error | Server phát hiện và cleanup, không giữ listener |
| Nhiều tabs cùng một user | Đóng tab A không xóa session B |
| Browser reconnect rất nhanh | Cleanup callback A không xóa entry B |
| WebSocket normal close | Registry và per-session queue được dọn |
| WebSocket transport reset | Cleanup và metric theo error path |
| Slow client | Queue bound được áp dụng, không tăng RAM vô hạn |
| Stream kết thúc bình thường | Active gauge trở về baseline |
| Redeploy/shutdown | Server ngừng nhận mới và release các subscriptions cũ |
| Proxy buffering/idle timeout | Heartbeat và close detection hoạt động qua public route |
| Shared resource ownership | Một session đóng không shutdown global executor/client pool |

**Không test bằng cách chờ `Thread.sleep(10)` rồi khẳng định server phải nhận disconnect.** Dùng latch/events, eventual assertions và timeout đủ rộng; đo liveness theo đường mạng thực tế.

Trong môi trường test, có thể dùng `curl -N` rồi `Ctrl+C` để tái hiện disconnect, nhưng automation nên dùng HTTP client mà test kiểm soát được connection disposal. Với end-to-end qua gateway, cần đo cả upstream và downstream connections; ngắt browser không nhất thiết lập tức đóng upstream connection của proxy.

## 30. Metrics và log: phân biệt kết thúc bình thường, lỗi và cancel

Một dashboard hữu ích có các nhóm số liệu:

```text
stream_active_connections{protocol="sse|websocket"}
stream_opened_total{protocol="sse|websocket"}
stream_ended_total{reason="complete|timeout|io_error|cancel|shutdown"}
stream_upstream_subscriptions{source="broker"}
stream_scheduler_tasks_active
stream_per_client_queue_bytes
stream_write_errors_total
stream_duration_seconds
```

Đây là **tên metrics gợi ý**, không khẳng định Micrometer/Actuator tự xuất chính xác các tên này. Khi triển khai, tránh dùng `sessionId`, `userId` hoặc URL động làm metric tags vì cardinality rất cao. Dùng trace/span IDs ở tracing/logs có kiểm soát; tag nên là protocol, route, outcome và một số nhóm business ổn định.

Log một session có thể ghi:

```text
stream_opened streamId=... protocol=sse
stream_cleanup streamId=... reason=io_error
stream_closed streamId=... activeAfter=...
```

Trên production, chỉ log mức cần thiết, không phát tán token, cookies, message payload nhạy cảm hoặc PII. Ghi **một cleanup event** sau khi `closeOnce` thành công thay vì log một event lỗi cho mỗi callback trùng.

Những số liệu cảnh báo leak: `stream_opened_total` tăng nhưng `stream_ended_total` không theo kịp khi load đã dừng; active connections không về baseline; broker listener count/queue size tăng sau khi tất cả clients thoát; số `ScheduledFuture` không giảm; off-heap memory tăng khi streaming bytes.

Hãy kiểm tra **số phiên đang hợp lệ** và thời gian trung bình một phiên thực, tránh báo động sai khi có khách đang cố ý mở stream cả ngày.

## 31. Bảo mật và vận hành: stream dài cần ranh giới riêng

Kết nối dài giữ tài nguyên lâu và có thể làm thay đổi cơ chế authz:

- **Authentication lúc mở kết nối:** xác thực qua cookie/token/TLS phù hợp, không tin userId do client đưa trong query để tự chọn dữ liệu.
- **Authorization liên tục:** khi quyền bị thu hồi, tài khoản khóa hoặc token hết hạn, policy có thể yêu cầu đóng stream/re-auth. Không luôn coi một handshake hợp lệ là quyền vô hạn.
- **Quotas/rate limits:** giới hạn connections đồng thời trên user/tenant/IP đã xác minh; phòng reconnect storm và abuse.
- **Browser policy:** SSE với credentials/CORS cần thiết kế đúng; WebSocket không dùng CORS preflight như fetch, nên kiểm tra `Origin` và chính sách xác thực cho handshake theo hệ thống.
- **CSRF/session:** nếu thao tác WebSocket messages có side effects, cần xác thực/ủy quyền/anti-CSRF hoặc origin policy phù hợp, không chỉ tin socket đã mở.
- **TLS/proxy:** traffic public nên qua HTTPS/WSS; termination và forwarded headers đúng trust boundary; không lộ backend socket.
- **Data privacy:** khi client ngắt, server không nên tiếp tục giữ dữ liệu cá nhân trong queue/cache per-client ngoài retention cần thiết.
- **Backpressure:** disconnected/slow clients không được dùng memory vô hạn hoặc chặn nguồn dữ liệu của clients khỏe.

Trong cluster nhiều replicas, session state thường là **local theo instance**; khi node mất, clients reconnect ở instance khác. Không thiết kế registry local như nguồn dữ liệu bền vững; dùng broker/durable log cho events cần replay.

## 32. Xử lý server shutdown và graceful termination

Khi redeploy, server nên dừng nhận kết nối mới và cho các request hiện tại có thời gian hoàn tất hoặc đóng hợp lý. **Long-lived streams có thể không tự hoàn tất trong grace period**, nên cần chính sách rõ:

1. Đánh dấu service đang draining và không nhận subscriptions mới hoặc trả tín hiệu reconnect theo nghiệp vụ.
2. Chủ động complete/close những streams còn mở khi kết thúc grace period.
3. Dispose broker listeners, future tasks và per-session buffers.
4. Chỉ sau đó shutdown shared executors, HTTP clients/broker connections.
5. Đảm bảo ingress/load balancer ngừng route requests mới tới instance đang terminate.

Spring Boot có cơ chế graceful shutdown của embedded server, nhưng không nên suy rằng nó sẽ **đợi vô hạn** mọi WebSocket/SSE stream hoặc tự cleanup một listener do code đăng ký thủ công. Hãy kiểm thử lifecycle startup/shutdown của từng server và connection type.

Với MVC sample ở mục 7, `@PreDestroy` gọi `session.close()` và `emitter.complete()` cho các sessions còn lại. Shared scheduler sẽ được đóng bởi lifecycle của bean; thiết kế production có nhiều sources nên tổ chức shutdown order rõ ràng để không gọi unsubscribe sau khi global broker client đã bị destroy.

Khi pod bị kill cưỡng bức (`SIGKILL`) hoặc node chết, không có Java shutdown hook nào được bảo đảm chạy. External broker subscriptions và leases cần có **server-side timeout/TTL** hoặc cơ chế expiry độc lập, không dựa hoàn toàn vào JVM cleanup.

## 33. Lỗi phổ biến và cách chẩn đoán đúng tầng

| Triệu chứng | Nghi vấn chính | Hướng xử lý |
| --- | --- | --- |
| Browser đóng tab nhưng active sessions không giảm ngay | Transport chưa phát hiện disconnect; không có heartbeat | Ghi định kỳ, xem proxy, timeout, container callbacks |
| `Broken pipe` xuất hiện khi gửi SSE | Client/proxy đã đóng HTTP connection | Dừng producer, cleanup; không cố ghi JSON lỗi |
| `onCompletion` gọi nhiều đường | Error/timeout/complete đều tới cleanup | `closeOnce`, atomic removal |
| Map emitters tăng liên tục | Không remove session khi hoàn tất | Cleanup registry trên mọi terminal path |
| WebFlux `doOnComplete` không chạy sau client cancel | Cancel khác normal complete | Dùng `doFinally`/`doOnCancel`, xử lý ON_ERROR |
| `Disposable` từ broker vẫn chạy | Đã `subscribe()` thủ công, không gắn lifecycle | `dispose` hoặc `using`/compose Publisher |
| WebSocket close nhưng sender vẫn chạy | Handler chưa compose receive/send hoặc leak timer | Gắn outbound cancel vào session termination |
| Một tab đóng làm các tab khác ngắt | Registry key chỉ theo userId; xóa nhầm entry | Dùng sessionId/compare-remove |
| RAM tăng với slow clients | Queue/buffer không giới hạn | Bound queue, backpressure/drop/replay policy |
| Direct memory Netty tăng | DataBuffer bị retain mà không release | Audit buffer ownership, leak detector |
| SSE đứt đều sau 60 giây | Proxy/read idle timeout hoặc async timeout | So sánh heartbeat và từng hop timeout |
| Spring trả HTTP 500 sau client rời đi | Lỗi write đã commit response | Quan sát cause/metrics, không sửa status đã gửi |
| Browser reconnect tạo nhiều phiên | Phiên cũ cleanup trễ hoặc không có max session policy | Close old sessions, ownership và TTL |
| Server shutdown treo | Streams vô hạn không kết thúc, shared resources chờ | Draining policy, close active sessions |
| Test lúc được lúc không | Assertion đòi network disconnect tức thì | Eventual assertions, latch, controlled client |
| `EventSource.close` nhưng browser tự kết nối lại | Có thể app tạo EventSource mới hoặc lifecycle component sai | Kiểm tra frontend mount/reconnect logic |
| Thời gian stream dài làm pool cạn | Một stream giữ connection/resource của downstream lâu | Isolate pools, limits, close consumers |

Một quy trình điều tra gọn:

1. Theo dõi **một sessionId** từ lúc mở đến lúc cleanup.
2. Quan sát callback/signal nào xuất hiện: IO error, timeout, complete, reactive cancel hay WebSocket close.
3. So sánh active session registry, heartbeat task, broker subscription và pending queues **trước/sau** disconnect.
4. Kiểm tra proxy buffering, idle timeouts, client reconnection và browser/network behavior.
5. Xác định có upstream subscription tự tạo bằng `subscribe()` mà không dispose không.
6. Test cả race giữa disconnect, timeout, shutdown và reconnect.

Không sửa triệu chứng bằng cách chỉ tăng heap, tăng executor pool hoặc tắt mọi timeout: leak vẫn sẽ trở lại khi tải tăng.

## 34. Câu hỏi kiểm tra và bài tập thực hành

1. Vì sao `EventSource.close()` không bảo đảm server gọi ngay `onCompletion()`?
2. Spring MVC `SseEmitter.send()` ném `IOException` do client ngắt thì application nên dọn nguồn dữ liệu thế nào? Vì sao không gọi `completeWithError()` trong nhánh này?
3. So sánh `onTimeout`, `onError`, `onCompletion`: chúng có bao giờ kích hoạt cleanup cho **cùng** session không?
4. Vì sao `AtomicBoolean.compareAndSet(false, true)` hữu ích khi nhiều callbacks cùng tới?
5. `cancel(false)` một `ScheduledFuture` khác gì `shutdown()` toàn bộ shared executor?
6. Reactive `doFinally(SignalType.CANCEL)` khác `doOnComplete` ở điểm nào?
7. Nếu `Flux.interval` được trả thẳng cho WebFlux, điều gì xảy ra với scheduled task khi downstream cancel?
8. Nếu code tự `broker.subscribe(...).subscribe()` và không lưu `Disposable`, tại sao HTTP disconnect không tự dọn upstream?
9. Khi nào cần `Flux.using` và khi nào cần `Flux.usingWhen`?
10. Reactive WebSocket vì sao phải hợp nhất `session.receive()` và `session.send()` theo một termination policy?
11. Làm sao tránh callback của session A xóa nhầm session B sau reconnect?
12. Heartbeat comment-only SSE giúp phát hiện gì, và vì sao proxy buffering có thể làm chậm tín hiệu?
13. Khi nào việc bỏ events ở `onBackpressureLatest` không được chấp nhận?
14. Vì sao một `DataBuffer` được retain cần release, và vì sao release ngay sau khi giao cho response writer có thể sai?
15. Viết test dùng `StepVerifier.thenCancel` để chứng minh số active subscriptions trở về 0; vì sao test này khác end-to-end TCP disconnect test?
16. Nếu một node bị `SIGKILL`, phần cleanup Java nào có thể không chạy, và cần cơ chế TTL/lease ở đâu?
17. Mở hai tab của một user, đóng một tab; làm sao chứng minh tab còn lại vẫn nhận dữ liệu?
18. Những metrics nào chứng minh listener/task/queue đang rò rỉ dù không còn browser kết nối?

**Bài tập 1:** Chạy ứng dụng Spring MVC, mở hai `curl -N` sessions và gọi `/active-streams`; chủ động dừng một session, quan sát về 1 sau khi server phát hiện rồi dừng session còn lại. Thử timeout và restart, kiểm tra không có task cũ bị giữ.

**Bài tập 2:** Chạy ứng dụng WebFlux và test Reactor ở mục 14. Thay `doFinally` bằng `doOnComplete`, quan sát vì sao cancellation không cập nhật counter như dự định; khôi phục `doFinally`.

**Bài tập 3:** Mô phỏng một nguồn dữ liệu có handle `AutoCloseable`, dùng `Flux.using` để sở hữu handle theo subscription. Gửi cancellation và xác minh `close()` chỉ có tác dụng một lần. Thêm một tình huống error để kiểm tra cleanup vẫn chạy.

**Bài tập 4:** Đặt proxy có buffering/idle timeout trước SSE; thay đổi heartbeat interval trong môi trường test rồi đo thời gian server nhận disconnect. **Không** thử gây cạn kết nối/DoS trên production.

## 35. Kết luận: đóng HTTP response chưa đủ nếu còn tài nguyên phụ

**Chuỗi trách nhiệm cần ghi nhớ:**

```text
Client không còn cần stream
     -> transport/framework nhận biết kết thúc (có thể trễ)
     -> cancel/timeout/error/close signal
     -> cleanup idempotent của session
     -> hủy broker listener/timer/upstream subscription
     -> remove registry/buffer, cập nhật metrics
     -> không ảnh hưởng các sessions hoặc shared resources khác
```

Với **Spring MVC `SseEmitter`**, dọn qua `onCompletion`, `onTimeout`, `onError` và nhánh `IOException` từ `send`, kết hợp heartbeat để phát hiện client đã rời đi; **đừng gọi `completeWithError` sau I/O send failure**. Với **WebFlux**, ưu tiên để cancellation truyền theo reactive chain, dùng `doFinally`, `Flux.using` hoặc `usingWhen` để giải phóng nguồn dữ liệu. Với **WebSocket**, thống nhất lifecycle inbound/outbound và xử lý close/error/idempotent registry removal.

Một stream tốt không chỉ gửi events chính xác. Nó phải **ngừng tiêu tốn tài nguyên khi không còn người nhận**, chịu được client chậm, reconnect, lỗi mạng, timeout và redeploy, đồng thời không vô tình dừng các kết nối lành mạnh khác.

### Tài liệu tham khảo

- Spring Framework 6.1 — Asynchronous Requests, phần HTTP Streaming, SSE, Disconnects và Exception Handling: https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-ann-async.html
- Spring Framework 6.1 — `SseEmitter` JavaDoc: https://docs.spring.io/spring-framework/docs/6.1.18/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html
- Spring Framework 6.1 — `ResponseBodyEmitter` JavaDoc: https://docs.spring.io/spring-framework/docs/6.1.18/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyEmitter.html
- Spring Framework — WebFlux reactive core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — WebFlux WebSocket handling: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
- Project Reactor — Reference Guide, `doFinally`, `using` và cancellation: https://projectreactor.io/docs/core/3.6.17/reference/
- Project Reactor — `Flux` API: https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Flux.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Boot 3.3 — Servlet Web Applications và reactive web applications: https://docs.spring.io/spring-boot/3.3/reference/web/index.html
- MDN — EventSource `close()`: https://developer.mozilla.org/en-US/docs/Web/API/EventSource/close
- MDN — AbortController `abort()`: https://developer.mozilla.org/en-US/docs/Web/API/AbortController/abort