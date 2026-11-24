# Xây dựng API WebFlux phát dữ liệu qua Server-Sent Events

## Bối cảnh

Một dashboard cần nhận trạng thái mới từ máy chủ ngay khi có dữ liệu, chẳng hạn số liệu giám sát, tiến độ xử lý hoặc thông báo trong hệ thống. Nếu dùng HTTP polling, trình duyệt phải gửi yêu cầu lặp lại dù chưa có dữ liệu mới. Với Server-Sent Events (SSE), máy chủ giữ một kết nối HTTP và gửi các sự kiện nối tiếp về trình duyệt.

Trong bài thực hành này, bạn xây dựng một endpoint bằng Spring WebFlux. Endpoint trả về `Flux<ServerSentEvent<StreamEvent>>`, phát một sự kiện mỗi giây và cho phép trình duyệt nhận dữ liệu liên tục. Bài tập tập trung vào cách tạo luồng, định dạng sự kiện, vòng đời subscription và cách kiểm tra kết nối.

## Mục tiêu

Sau khi hoàn thành, bạn có thể:

- Giải thích được SSE truyền dữ liệu một chiều từ máy chủ đến client qua HTTP.
- Tạo endpoint WebFlux trả về `Flux<ServerSentEvent<T>>` với đúng media type `text/event-stream`.
- Gửi `id`, `event`, `retry` và `data` trong từng sự kiện.
- Quan sát việc client kết nối, nhận dữ liệu và hủy subscription khi ngắt kết nối.
- Phân biệt cơ chế tự kết nối lại của trình duyệt với khả năng phát lại sự kiện mà ứng dụng phải tự triển khai.
- Chọn chính sách xử lý tải ngược phù hợp với loại dữ liệu được phát.

## Chuẩn bị

Sử dụng Java 17 trở lên và một dự án Spring Boot 3.x có dependency WebFlux. Với Maven, thêm dependency sau vào `pom.xml` (phiên bản được quản lý bởi Spring Boot parent hoặc BOM của dự án):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Các đoạn mã dưới đây dùng package mẫu `com.example.reactive.sse`. Hãy đổi package cho phù hợp với dự án của bạn. Ví dụ sử dụng Java record để biểu diễn payload.

## Thiết kế luồng sự kiện

Endpoint `GET /api/events` sẽ phát một sự kiện mỗi giây. Mỗi sự kiện có:

| Trường SSE | Vai trò |
| --- | --- |
| `id` | Định danh sự kiện; trình duyệt có thể gửi lại giá trị cuối cùng qua header `Last-Event-ID` khi kết nối lại. |
| `event` | Tên loại sự kiện để client đăng ký listener tương ứng. |
| `retry` | Khoảng thời gian client chờ trước khi thử kết nối lại, tính bằng mili giây trên giao thức SSE. |
| `data` | Payload của sự kiện; Spring sẽ tuần tự hóa đối tượng thành dữ liệu truyền đi. |

SSE phù hợp khi client chỉ cần nhận dữ liệu từ server. Nếu client và server cần trao đổi hai chiều liên tục trong cùng kết nối, hãy cân nhắc WebSocket.

## Bước 1: Tạo payload

Tạo file `StreamEvent.java`:

```java
package com.example.reactive.sse;

import java.time.Instant;

public record StreamEvent(
        long sequence,
        Instant occurredAt,
        String message
) {
}
```

Payload giữ số thứ tự, thời điểm phát và nội dung. `sequence` cũng được dùng làm SSE event ID để client có thể nhận biết sự kiện đã đọc đến đâu.

## Bước 2: Tạo service phát sự kiện

Tạo `EventStreamService.java`:

```java
package com.example.reactive.sse;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class EventStreamService {

    private static final Logger log =
            LoggerFactory.getLogger(EventStreamService.class);

    private final AtomicLong sequence = new AtomicLong();

    public Flux<ServerSentEvent<StreamEvent>> stream() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(tick -> {
                    long id = sequence.incrementAndGet();
                    StreamEvent payload = new StreamEvent(
                            id,
                            Instant.now(),
                            "Sự kiện reactive số " + id
                    );

                    return ServerSentEvent.<StreamEvent>builder()
                            .id(Long.toString(id))
                            .event("stream-update")
                            .retry(Duration.ofSeconds(3))
                            .data(payload)
                            .build();
                })
                .doOnSubscribe(subscription ->
                        log.info("Client đã đăng ký SSE stream"))
                .doFinally(signal ->
                        log.info("SSE stream kết thúc với tín hiệu: {}", signal));
    }
}
```

`Flux.interval` tạo một Publisher phát số thứ tự theo chu kỳ. Toán tử `map` chuyển mỗi tick thành một `ServerSentEvent`. `AtomicLong` tạo ID tăng dần an toàn khi nhiều subscription cùng phát sự kiện trong một instance ứng dụng.

`doOnSubscribe` và `doFinally` chỉ quan sát vòng đời của luồng. Khi client đóng tab hoặc mất kết nối, subscription thường bị hủy và `doFinally` nhận tín hiệu `CANCEL`. Trong thực tế, hãy dùng tín hiệu này để giải phóng tài nguyên gắn với client nếu service có giữ tài nguyên riêng.

## Bước 3: Tạo WebFlux controller

Tạo `EventStreamController.java`:

```java
package com.example.reactive.sse;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/events")
public class EventStreamController {

    private final EventStreamService eventStreamService;

    public EventStreamController(EventStreamService eventStreamService) {
        this.eventStreamService = eventStreamService;
    }

    @GetMapping(produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<StreamEvent>> stream() {
        return eventStreamService.stream();
    }
}
```

Điểm quan trọng là controller trả thẳng `Flux` cho WebFlux. Không gọi `subscribe()` hoặc `block()` trong controller: framework quản lý subscription và ghi từng phần tử ra HTTP response. `MediaType.TEXT_EVENT_STREAM_VALUE` khai báo định dạng phản hồi `text/event-stream` để client xử lý như một luồng SSE.

## Bước 4: Chạy và quan sát API

Khởi động ứng dụng Spring Boot, sau đó mở terminal và chạy:

```bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/events
```

Trên Windows PowerShell, dùng `curl.exe` nếu lệnh `curl` đang được ánh xạ sang alias của PowerShell:

```powershell
curl.exe -N -H "Accept: text/event-stream" http://localhost:8080/api/events
```

Tùy thời điểm và bộ tuần tự hóa JSON, kết quả có dạng tương tự:

```text
id:1
event:stream-update
retry:3000
data:{"sequence":1,"occurredAt":"2026-01-01T10:00:00Z","message":"Sự kiện reactive số 1"}

id:2
event:stream-update
retry:3000
data:{"sequence":2,"occurredAt":"2026-01-01T10:00:01Z","message":"Sự kiện reactive số 2"}
```

Tùy chọn `-N` tắt buffering phía `curl`, giúp bạn nhìn thấy từng sự kiện ngay khi nhận được. Nhấn `Ctrl+C` để đóng kết nối và quan sát log kết thúc subscription ở server.

Bạn cũng có thể kiểm tra bằng trình duyệt trên cùng origin:

```javascript
const source = new EventSource("/api/events");

source.addEventListener("stream-update", (message) => {
  const event = JSON.parse(message.data);
  console.log(event.sequence, event.message, event.occurredAt);
});

source.onerror = (error) => {
  console.warn("SSE connection encountered an error", error);
};

// Gọi khi không còn cần nhận sự kiện:
// source.close();
```

`EventSource` tự thử kết nối lại khi kết nối bị gián đoạn. Trình duyệt gửi ID cuối cùng đã nhận trong header `Last-Event-ID` khi thực hiện lần kết nối lại phù hợp. Tuy nhiên, server trong bài này chỉ tạo tick mới; nó chưa đọc header đó và chưa lưu lịch sử. Vì vậy, ID hiện tại chỉ minh họa định danh sự kiện, chưa bảo đảm phát lại các sự kiện bị bỏ lỡ.

## Bước 5: Kiểm tra tải ngược và vòng đời

Mỗi client tạo một subscription riêng vào `Flux.interval`; service mẫu phát dữ liệu định kỳ cho từng subscription. Khi có nhiều client, số luồng và công việc phát sinh tăng theo số kết nối. Hãy quan sát log khi mở hai terminal cùng gọi endpoint, sau đó dừng từng client để thấy mỗi subscription kết thúc độc lập.

WebFlux truyền dữ liệu theo mô hình reactive và có thể điều tiết việc ghi dựa trên nhu cầu downstream. Tuy nhiên, nguồn phát có nhịp cố định vẫn cần chính sách khi client đọc chậm. Không nên thêm buffer không giới hạn vì một client chậm có thể làm bộ nhớ tăng liên tục.

Nếu dữ liệu là snapshot trạng thái và chỉ giá trị mới nhất quan trọng, có thể cân nhắc `onBackpressureLatest()`. Nếu dùng buffer hữu hạn và chấp nhận bỏ sự kiện cũ, có thể cấu hình rõ giới hạn và chính sách tràn:

```java
import reactor.core.publisher.BufferOverflowStrategy;

Flux.interval(Duration.ofSeconds(1))
        .onBackpressureBuffer(
                256,
                () -> log.warn("SSE buffer đã đầy"),
                BufferOverflowStrategy.DROP_OLDEST
        );
```

Đây chỉ là lựa chọn cho dữ liệu có thể bỏ bớt, chẳng hạn snapshot giám sát. Không dùng `DROP_OLDEST` cho thông báo kiểm toán, giao dịch hoặc sự kiện nghiệp vụ bắt buộc phải xử lý đủ. Với các trường hợp đó, cần nguồn sự kiện có lưu trữ, giới hạn tốc độ và cơ chế tiêu thụ có thể tiếp tục từ vị trí đã xác nhận.

## Xử lý lỗi và khả năng kết nối lại

Khi Publisher phát lỗi, luồng SSE hiện tại kết thúc. Có thể dùng `doOnError` để ghi log và dùng `retryWhen` khi lỗi upstream có thể phục hồi. Nếu muốn thông báo lỗi có cấu trúc cho client, hãy ánh xạ lỗi thành một SSE event có tên riêng, không gửi stack trace hoặc thông tin nội bộ trong `data`. Sau khi gửi thông báo, server có thể đóng luồng để client áp dụng chính sách kết nối lại.

Tự kết nối lại của `EventSource` chỉ khôi phục kết nối HTTP. Để phát lại dữ liệu bị bỏ lỡ, ứng dụng phải triển khai lưu trữ và truy vấn sự kiện. Một cách triển khai là đọc `Last-Event-ID` từ request, tìm các sự kiện có ID lớn hơn trong event store rồi nối tiếp luồng sự kiện mới. Trong môi trường nhiều instance, ID và lịch sử sự kiện cần được chia sẻ qua một kho lưu trữ hoặc message broker; `AtomicLong` trong bộ nhớ của một instance không đáp ứng yêu cầu đó.

## Tiêu chí hoàn thành

- [ ] Ứng dụng khởi động thành công với `spring-boot-starter-webflux`.
- [ ] `GET /api/events` trả về HTTP response có media type `text/event-stream`.
- [ ] Client nhận được sự kiện định kỳ, mỗi sự kiện có `id`, `event`, `retry` và `data`.
- [ ] Có thể mở nhiều client đồng thời và quan sát subscription riêng của từng client.
- [ ] Khi client ngắt kết nối, server quan sát được tín hiệu kết thúc hoặc hủy subscription.
- [ ] Controller không tự gọi `subscribe()` hay `block()`.
- [ ] Có giải thích rõ giới hạn của ví dụ về phát lại sự kiện và lựa chọn xử lý client đọc chậm.

## Bài mở rộng

1. Thay dữ liệu tick bằng tiến độ của một tác vụ xử lý dài. Mỗi sự kiện nên có `jobId`, `sequence`, `status` và `occurredAt`.
2. Lưu sự kiện vào cơ sở dữ liệu hoặc message broker. Đọc `Last-Event-ID` khi client kết nối lại và phát bù các sự kiện còn thiếu trước khi chuyển sang luồng mới.
3. Viết kiểm thử với `StepVerifier` cho một Publisher hữu hạn, xác minh thứ tự ID và payload. Có thể tách phần tạo sự kiện thành một phương thức nhận nguồn dữ liệu để kiểm thử mà không phải chờ một luồng vô hạn.
4. Đo số kết nối đồng thời, tốc độ phát, độ trễ và bộ nhớ khi client đọc chậm. Chọn chính sách buffer hoặc lưu trữ dựa trên yêu cầu mất dữ liệu của nghiệp vụ.

Khi hoàn thành, bạn có một API SSE chạy trên WebFlux và hiểu các quyết định cần bổ sung trước khi dùng luồng sự kiện này cho dữ liệu nghiệp vụ quan trọng.
