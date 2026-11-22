# Content-Type, nhịp giữ kết nối và bộ đệm tại proxy trong kết nối dài Spring Boot

**Ngữ cảnh:** Spring Boot → web-runtime → Kết nối dài. Bài học tập trung vào ba biến số quyết định một HTTP stream có thực sự đến người dùng theo thời gian thực hay không: **Content-Type/định dạng dữ liệu**, **heartbeat (nhịp gửi dữ liệu giữ kết nối/phát hiện mất client)** và **buffering ở ứng dụng, servlet container, proxy, CDN và client**. Trọng tâm là **Server-Sent Events (SSE)**, đồng thời so sánh streaming NDJSON, HTTP long polling và WebSocket. Có ví dụ **Java 17 + Spring Boot 3.5.16 + Spring MVC + Maven** chạy được, cấu hình Nginx, kiểm tra bằng `curl -N`, cách tính timeout, phát hiện lỗi production và lưu ý WebFlux.

> Một kết nối TCP mở suốt nhiều phút **không bảo đảm** client nhận từng sự kiện ngay khi server phát. Một lệnh `write` ở Java, một response status `200` và header `Transfer-Encoding: chunked` cũng **không chứng minh** đường truyền không bị buffer ở proxy/client. Phải đo các mốc **event generated → server flush → proxy read → client receive** trên đường đi thật.

## 1. Kết nối dài là gì và các tầng liên quan?

Một request HTTP thường có vòng đời ngắn: client gửi request, server tính kết quả, trả response và hoàn tất. Với kết nối dài, response **còn mở** trong khi server gửi từng phần dữ liệu ở những thời điểm khác nhau. Ví dụ: tiến độ báo cáo, thông báo, sự kiện dashboard, log tail, kết quả AI được stream, giao diện monitoring, feed dữ liệu.

~~~text
Client (browser/curl)
    │ GET /events, Accept: text/event-stream
    │
    ▼
CDN / Load Balancer / Ingress
    │  Có idle timeout, HTTP version, buffering policy
    ▼
Reverse Proxy (Nginx)
    │  Có proxy_buffering, proxy_read_timeout, gzip/proxy_cache
    ▼
Spring Boot (Servlet MVC hoặc WebFlux)
    │  Response Content-Type + từng event/frame + flush
    │
    ├─ T+0s   event: ready  ─────► proxy ─────► client
    ├─ T+10s  : heartbeat   ─────► proxy ─────► client
    ├─ T+20s  : heartbeat   ─────► proxy ─────► client
    └─ T+30s  data: update  ─────► proxy ─────► client

Nếu proxy gom/chờ buffer lớn:
    T+0s,10s,20s,30s các bytes đến proxy nhưng client chưa thấy.
    Client chỉ thấy một đợt sau khi đủ buffer hoặc response kết thúc.
~~~

Phải phân biệt **một kết nối lâu**, **một HTTP response lâu**, **đổi kết nối khi reconnect**, và **giữ TCP socket cho các HTTP requests kế tiếp**. HTTP keep-alive của HTTP/1.1 không phải heartbeat trong body của SSE.

### 1.1. Các kỹ thuật được dùng

| Kỹ thuật | Giao thức/Media type thường dùng | Đặc điểm | Nhịp giữ kết nối |
| --- | --- | --- | --- |
| **SSE (EventSource)** | HTTP GET + `text/event-stream` | Một chiều server → browser, auto-reconnect của EventSource | **Comment-only SSE frame** hoặc sự kiện ứng dụng |
| **NDJSON / JSON Lines stream** | `application/x-ndjson` | Mỗi dòng là JSON hoàn chỉnh, client tự parse dòng | Một bản ghi no-op/heartbeat theo contract ứng dụng |
| **HTTP response streaming tùy ý** | `text/plain`, `application/octet-stream`... | Byte stream, không có chuẩn event frame chung | Bytes no-op riêng của protocol |
| **Long polling** | Thường `application/json` | Một request chờ dữ liệu rồi trả **một response kết thúc**; client gửi request khác | Timeout và reissue request, không nhất thiết gửi frame trong response |
| **WebSocket** | HTTP Upgrade hoặc HTTP/2 CONNECT và WebSocket frames | Hai chiều, không phải SSE Content-Type | WebSocket **Ping/Pong control frames** |
| **gRPC streaming** | HTTP/2, `application/grpc` | Message framing/flow control riêng, không phải EventSource | HTTP/2/gRPC keepalive theo client/server policy |

Các media types **không thay thế lẫn nhau**. Browser `EventSource` hiểu `text/event-stream` và các field `data`, `event`, `id`, `retry`. Nó không tự parse một stream `application/json` hay `application/x-ndjson` thành SSE events. Dùng `fetch` + streaming reader khi muốn tự parse NDJSON.

## 2. Content-Type đúng không chỉ là một header trang trí

### 2.1. SSE phải có `text/event-stream`

Với SSE, server thường trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream;charset=UTF-8
Cache-Control: no-cache, no-transform
X-Accel-Buffering: no

event: ready
id: 1
retry: 3000
data: connected

: heartbeat

event: progress
id: 2
data: {"percent":42}

~~~

Header ví dụ mang tính minh họa: `Transfer-Encoding`, `Connection`, `Date` và thứ tự các trường có thể khác theo HTTP version, web server và proxy. **Định dạng body SSE** có ý nghĩa chính:
- mỗi dòng `data: ...` bổ sung dữ liệu của event;
- `event: progress` định tên sự kiện để browser đăng ký `addEventListener("progress", ...)`;
- `id: 2` cung cấp event ID; khi tự reconnect, EventSource có thể gửi `Last-Event-ID`;
- `retry: 3000` hướng dẫn browser dùng khoảng reconnect 3.000 ms (một số browser có chính sách riêng);
- **dòng trống** kết thúc khung event và làm parser dispatch dữ liệu;
- dòng bắt đầu bằng **`:`** là **SSE comment**; client EventSource **bỏ qua** trong callback JavaScript nhưng bytes vẫn đi qua mạng.

Một SSE stream truyền nhiều event liên tiếp, **không** gói toàn bộ sự kiện vào một JSON array rồi đợi đóng dấu `]` mới gửi.

### 2.2. Heartbeat frame SSE đúng cú pháp

Một nhịp comment đơn giản:

~~~text
: heartbeat

~~~

Tức chuỗi byte UTF-8 thể hiện là `": heartbeat\n\n"`. Cặp newline tách comment thành một block riêng; comment không tạo `message` event trong JavaScript. Có thể gửi `":\n\n"` nếu không cần mô tả. Nếu dùng Windows CRLF, format theo SSE specification vẫn hợp lệ.

**Không gửi đơn độc một ký tự dấu cách**, một JSON `{}` hay chuỗi `"ping"` rồi mong EventSource bỏ qua. Nếu gửi `data: ping\n\n`, browser sẽ nhận **một sự kiện dữ liệu thật**, có thể kích hoạt handler. Với Heartbeat **comment-only**, EventSource không gọi `onmessage`/`addEventListener`; nếu ứng dụng muốn kiểm tra sống từ JavaScript, hãy dùng event tên `heartbeat` và chấp nhận nó là một event thực.

### 2.3. Content negotiation và charset

Thường endpoint Spring MVC:

~~~java
@GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    return new SseEmitter();
}
~~~

Đây là **mảnh minh họa không có cơ chế gửi/cleanup**, không phải endpoint hoàn chỉnh. `produces` khai báo media type Spring dùng để chọn handler và serialize response; trả `SseEmitter` kích hoạt SSE writer. Browser EventSource thường gửi header `Accept: text/event-stream`, nhưng **client gửi Accept chưa đủ**: server cũng phải trả đúng Content-Type và framing.

SSE tiêu chuẩn là **UTF-8**. Không gửi stream UTF-16 hoặc bytes không hợp lệ rồi tự gọi là text/event-stream. Khi dữ liệu JSON trong `data: ...`, serialize JSON đúng cách trước khi đặt vào event (Spring `SseEmitter.event().data(object)` dùng converter nếu configured); nếu sử dụng raw strings, tránh tự nối JSON từ input chưa escape.

**Tránh dựa vào MIME sniffing.** Browser có thể áp những chính sách khác nhau cho `text/plain`, `application/json` và `text/event-stream`; việc đoán MIME không giúp streaming đúng. Với `X-Content-Type-Options: nosniff`, response cần Content-Type thực sự chính xác.

### 2.4. NDJSON khác SSE

NDJSON thường có `Content-Type: application/x-ndjson`, mỗi dòng là **một JSON object/value hoàn chỉnh**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"seq":1,"type":"tick"}
{"seq":2,"type":"tick"}
{"seq":3,"type":"tick"}
~~~

Mỗi dòng kết thúc bằng `\n`. Client đọc bytes đến khi gặp newline mới parse một JSON record. Nó **không có** trường `event:`/`id:`/`retry:` của SSE và không có browser EventSource auto-reconnect sẵn. Nếu muốn gửi heartbeat NDJSON, phải định nghĩa record có thể bỏ qua, ví dụ `{"type":"heartbeat"}\n`, và client/parser phải biết không đưa nó vào nghiệp vụ. Không chèn `": ping\n\n"` kiểu SSE vào NDJSON vì đó **không phải JSON hợp lệ**.

### 2.5. Vì sao `application/json` dễ tạo ảo giác “không stream”?

Nếu server muốn gửi một object JSON hoặc một array tổng quát, các serializer, output wrappers và clients có thể buffer nội dung đến khi có kết quả hợp lệ hoặc response kết thúc. Một response `application/json` **có thể** được stream bằng một số API/framework, nhưng **Content-Type JSON một mình không đưa ra contract message-by-message**. Khi cần client parse từng bản ghi theo thời gian, dùng NDJSON; khi browser cần subscribe server events và reconnect, dùng SSE; khi cần hai chiều, cân nhắc WebSocket.

## 3. Heartbeat phục vụ việc gì?

Heartbeat là **dữ liệu rất nhỏ** được gửi định kỳ ngay cả khi không có sự kiện nghiệp vụ. Nó phục vụ hai mục tiêu liên quan nhưng không giống nhau:

1. Giúp các thành phần mạng có idle timeout thấy còn dữ liệu truyền qua và không đóng kết nối chỉ vì quá lâu im lặng.
2. Giúp ứng dụng **phát hiện mất client sớm hơn**: trong Servlet, thông thường không có callback cho remote disconnect ngay khi client rút mạng; lần ghi sau có thể gây `IOException`.

**Heartbeat không bảo đảm** kết nối không bao giờ bị ngắt. Proxy có thể buffer toàn bộ heartbeat, một LB có giới hạn thời gian tuyệt đối, tab browser có thể bị background throttling, client mất mạng, scheduler bị nghẽn, hoặc server restart. SSE client phải có **reconnect/resume strategy**.

### 3.1. Tính nhịp từ các timeout thực sự

Giả sử một tuyến có:

| Thành phần | Timeout minh họa | Ý nghĩa |
| --- | --- | --- |
| Spring MVC `SseEmitter` | 300 giây | **Tổng** lifetime async request của emitter nếu khai báo 300.000 ms |
| Nginx `proxy_read_timeout` | 75 giây | Im lặng **giữa hai lần đọc từ upstream**, không phải 75 giây tổng response |
| Một load balancer | 45 giây | **Giả định cấu hình** idle timeout trên hop đó, không phải default chung |
| Heartbeat của ứng dụng | 10 giây | Một khung comment nhỏ sau mỗi nhịp scheduler |

10 giây nhỏ hơn 45 và 75, tạo biên độ cho jitter, GC pause, network delay. Nhưng sau **300 giây**, `SseEmitter(300_000L)` vẫn có thể timeout theo async lifetime dù heartbeat cứ 10 giây, và EventSource sẽ cần reconnect. **Heartbeat không tự reset một “absolute request lifetime”**. Nếu cần stream nhiều giờ, thiết kế timeout theo hợp đồng, kết nối lại định kỳ và retry, không chỉ nâng ngẫu nhiên mọi giá trị thành vô hạn.

Nguyên tắc thực hành:
- đặt `heartbeat_interval` **thấp hơn idle timeout nhỏ nhất** giữa các hop, có dự phòng cho pause/jitter;
- đừng gửi heartbeat mỗi vài mili giây vì nhiều clients gây overhead CPU/network/syscalls;
- phải đo **bytes thực sự tới hop**: gửi ở server nhưng proxy đang buffer thì LB ở phía client vẫn có thể timeout;
- phân biệt read timeout của upstream, write timeout về downstream và total request deadline;
- kiểm tra heartbeat khi app không có nghiệp vụ, lúc server tải cao và khi client bị đóng bất ngờ.

### 3.2. Đừng nhầm ba kiểu “keep-alive”

| Cơ chế | Tầng | Có tạo SSE bytes trong response? |
| --- | --- | --- |
| HTTP/1.1 persistent connection / `Connection: keep-alive` | Tái dùng TCP connection cho nhiều HTTP requests | **Không** |
| TCP keepalive probes | Kernel TCP phát probe trên socket trong điều kiện nhất định | **Không**; proxy/LB application idle timer có thể không tính |
| SSE `: heartbeat\n\n` | HTTP **response body** | **Có**, nếu từng tầng flush/forward đúng |
| WebSocket Ping/Pong | Frames của WebSocket protocol | **Không phải** SSE bytes, chỉ dùng khi đã upgrade |
| HTTP/2 PING frame | Connection-level HTTP/2 control frame | Không thay thế SSE message/ứng dụng theo mọi LB policy |

Không giải quyết lỗi SSE im lặng chỉ bằng `Connection: keep-alive`. Đây còn là header **hop-by-hop**, không gửi qua HTTP/2 theo cách HTTP/1.1. HTTP/2 có thể multiplex nhiều streams trên một connection và vẫn bị các timeout/policies khác.

### 3.3. Heartbeat và detection

Một Servlet stream bị client ngắt không nhất thiết phát hiện ngay trong controller. Spring Framework khuyến nghị **gửi đều đặn** một dữ liệu (comment-only SSE hoặc no-op stream item) để lần ghi tiếp theo có thể báo I/O failure. Khi `SseEmitter.send(...)` ném `IOException`, trong Spring MVC container thường sẽ thông báo async error cho Spring; theo tài liệu, **đừng tự `completeWithError` cho chính IOException này** như cách xử lý bắt buộc, vì container tự làm điều đó. Hãy dọn subscriber và để container/Spring hoàn tất error lifecycle.

`onCompletion`, `onTimeout` và `onError` của emitter hữu ích để giải phóng connection/subscriber, task, database listener và queue. Với nhiều node, termination/deployment restart là tình huống bình thường; dùng auto-reconnect phía client.

## 4. Buffering ở đâu và vì sao có thể chặn mọi nhịp?

### 4.1. Các bộ đệm độc lập

~~~text
Spring code (send/flush)
  │
  ▼
Spring HTTP message converter / SseEmitter writer
  │
  ▼
Servlet response / container output buffer
  │
  ▼
OS TCP buffers
  │
  ▼
Nginx proxy_buffering / gzip / proxy_cache
  │
  ▼
Ingress, LB, CDN, WAF, CDN transforms
  │
  ▼
Browser network buffering / EventSource parser
  │
  ▼
JavaScript event listener
~~~

Có thể server gọi `send` đúng 10 giây một lần nhưng browser chỉ nhận khi Nginx đủ một buffer hoặc server đóng response. Có thể client nhận byte trên network đúng lúc nhưng `EventSource` chưa gọi callback vì **không có dòng trống kết thúc event**. Có thể browser nhận comment heartbeat nhưng JavaScript **không thấy callback vì comment bị bỏ qua theo thiết kế**.

Bởi vậy cần kiểm tra **cả HTTP headers, timing byte nhận, nội dung framing và client parser**, không chỉ log `send() completed`.

### 4.2. Nginx `proxy_buffering`

Nginx reverse proxy thông thường có thể buffer response upstream. Directive:

~~~nginx
proxy_buffering off;
~~~

làm proxy chuyển bytes đến client đồng bộ khi nhận, thay vì đọc trước và gom nhiều vào internal buffers/temp file. Theo tài liệu Nginx, `proxy_buffering` **mặc định on** trong cấu hình thông thường; quyết định cuối có thể bị override ở `http`/`server`/`location` hoặc bằng `X-Accel-Buffering` nếu không bị ignore.

**Chỉ tắt buffering ở route cần streaming**, ví dụ `/events` hoặc `/ndjson`, thay vì tắt trên tất cả pages/cacheable assets để tránh mất hiệu quả proxy.

### 4.3. `X-Accel-Buffering: no` là response header, không phải request header

Spring Boot có thể gửi:

~~~http
X-Accel-Buffering: no
~~~

cho endpoint streaming. Nginx có thể **tôn trọng** header này và tắt buffering chỉ cho response đó, nếu cấu hình không `proxy_ignore_headers X-Accel-Buffering`. Đây là cơ chế **của Nginx**, không phải HTTP standard mà mọi CDN/LB đều bắt buộc hiểu.

Nginx theo mặc định **không nhất thiết truyền header `X-Accel-*` đến browser**, dù bản thân nó đã áp dụng hành vi. Vì vậy việc không thấy `X-Accel-Buffering` trong browser DevTools **không chứng minh** Nginx đã bỏ qua header. Khi cần chắc chắn, cấu hình tường minh `proxy_buffering off` trên route và đo dòng dữ liệu qua endpoint public.

**Không** nhầm `X-Accel-Buffering: no` với `proxy_request_buffering off`: thứ sau kiểm soát **request body từ client đến upstream**, không giải quyết response SSE bị gom.

### 4.4. Gzip/compression và cache

Compression có thể thêm buffer trước khi phát bytes nhỏ; proxy/CDN có thể biến đổi response hoặc kết thúc stream. Với SSE:
- Ưu tiên giữ streaming response không bị proxy buffer/transform.
- `Cache-Control: no-cache, no-transform` giúp báo không được biến đổi và phải revalidate cache, nhưng **không ép mọi proxy bỏ buffering**.
- `no-cache` **không đồng nghĩa** `no-store`. Với dữ liệu riêng tư, cân nhắc `Cache-Control: private, no-store, no-transform` và tắt `proxy_cache` ở route.
- Kiểm tra các middleware có compression, content transformation hoặc output wrapping ở JVM và reverse proxy. Nếu cần, **tắt gzip riêng ở streaming route**.
- Không đặt `Content-Length` bằng kích thước dự đoán nếu stream chưa biết tổng dài; nhiều response HTTP/1.1 có thể dùng chunked transfer encoding tự động. HTTP/2 **không dùng** `Transfer-Encoding: chunked`, nhưng semantics SSE/heartbeat vẫn giữ nguyên.

`Transfer-Encoding: chunked` là **framing của HTTP/1.1**, không tự làm client parse SSE events; và gzip content encoding không tự đồng nghĩa streaming sẽ bị buffer nhưng có thể tác động flush/timing. Phải quan sát bytes thực tế.

## 5. Proxy timeouts: đọc đúng chiều và đúng ý nghĩa

| Tham số/cơ chế | Đường tác động | Ý nghĩa điển hình | Có phải tổng lifetime SSE? |
| --- | --- | --- | --- |
| **Nginx `proxy_read_timeout`** | Nginx đọc từ upstream Spring | Khoảng tối đa **giữa hai read operations**, upstream không gửi gì sẽ bị đóng | **Không** |
| Nginx `proxy_connect_timeout` | Nginx kết nối tới upstream | Thời gian mở kết nối tới backend | Không |
| Nginx `proxy_send_timeout` | Nginx gửi request tới upstream | Thời gian giữa các hoạt động **gửi request** | Không |
| Nginx `send_timeout` | Nginx gửi response tới downstream client | Timeout giữa các lần ghi/tiến độ gửi đến client | Không phải tổng |
| Spring MVC `SseEmitter(timeoutMillis)` | Servlet async request | Async lifecycle timeout riêng của emitter | **Có thể là giới hạn vòng đời** |
| Spring Boot `spring.mvc.async.request-timeout` | MVC async | Default async request timeout nếu không override theo emitter | Có thể giới hạn |
| Tomcat HTTP keep-alive timeout | Socket không có request giữa những requests | Khác lifetime của **response đang được stream** | Không tương đương |
| Load balancer/CDN idle timeout | Hop mạng nhất định | Có thể tính dữ liệu/idle theo hướng và tầng khác | Tùy nhà cung cấp |
| Client `curl --max-time` | Toàn bộ invocation curl | Hard deadline do client đặt dù stream đang có heartbeat | **Có** |

Ví dụ Nginx `proxy_read_timeout 75s` không nghĩa mọi stream bị cắt sau 75 giây: nếu upstream gửi bytes theo nhịp 10 giây, timeout inter-read có thể liên tục được gia hạn. Nhưng nếu Spring side bị mắc kẹt 80 giây (scheduler block, stop-the-world pause, downstream backpressure...), proxy có thể cắt. **Tăng proxy_read_timeout** là một phần, không thay thiết kế heartbeat đáng tin.

Nếu vẫn bị ngắt cố định đúng 60/120/300 giây, hãy tìm **absolute timeout ở app/proxy/LB**, không chỉ thay heartbeat interval. Với `new SseEmitter(300_000L)`, chính emitter có vòng đời 5 phút; heartbeat không biến nó thành kết nối vô hạn.

## 6. Project Spring Boot chạy được: SSE heartbeat và NDJSON từng dòng

Ví dụ dùng Java 17+, Maven, Spring MVC, Spring Boot **3.5.16**. Mục tiêu:
- `GET /events` trả `text/event-stream`, phát event ban đầu và comment heartbeat mỗi 10 giây, có cleanup callbacks;
- `GET /ndjson` trả `application/x-ndjson`, viết 3 JSON records cách nhau khoảng 1 giây, flush từng dòng;
- cấu hình một MVC async executor để tránh phụ thuộc executor development không phù hợp cho blocking writes khi tải lớn;
- chứng minh sự khác biệt bằng `curl -N` và qua Nginx.

**Đây là lab có kiểm soát, không phải implementation fan-out production tới hàng chục nghìn clients.** `@Scheduled` tuần tự và `SseEmitter.send` blocking có thể bị nghẽn bởi slow clients; cần kiến trúc queue, bounds, backpressure, authorization và resource management khi mở rộng.

### 6.1. Cấu trúc thư mục

~~~text
stream-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/streamdemo/
    │   ├── StreamDemoApplication.java
    │   ├── StreamController.java
    │   └── MvcAsyncConfig.java
    └── resources/application.properties
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>stream-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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

### 6.3. `src/main/java/com/example/streamdemo/StreamDemoApplication.java`

~~~java
package com.example.streamdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
public class StreamDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamDemoApplication.class, args);
    }
}
~~~

`@EnableScheduling` bật phương thức `@Scheduled` trong controller. Project này không có database, Redis, WebSocket hay Spring Security để tập trung vào HTTP stream/heartbeat/buffering.

### 6.4. `src/main/java/com/example/streamdemo/StreamController.java`

~~~java
package com.example.streamdemo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class StreamController {
    private final Set<SseEmitter> clients = ConcurrentHashMap.newKeySet();
    private final AtomicLong nextId = new AtomicLong();

    @GetMapping(path = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<SseEmitter> events() throws IOException {
        // 5 phút: vòng đời tối đa của emitter trong lab.
        SseEmitter emitter = new SseEmitter(300_000L);

        clients.add(emitter);
        emitter.onCompletion(() -> clients.remove(emitter));
        emitter.onTimeout(() -> clients.remove(emitter));
        emitter.onError(error -> clients.remove(emitter));

        // SseEmitter hỗ trợ send trước khi MVC hoàn tất việc return handler.
        emitter.send(SseEmitter.event()
                .name("ready")
                .id(Long.toString(nextId.incrementAndGet()))
                .reconnectTime(3000L)
                .data("connected"));

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .header(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(emitter);
    }

    @Scheduled(fixedDelay = 10_000L)
    public void heartbeat() {
        for (SseEmitter emitter : clients) {
            try {
                // Comment SSE: browser EventSource bỏ qua callback dữ liệu.
                emitter.send(SseEmitter.event().comment("heartbeat"));
            } catch (IOException | IllegalStateException ex) {
                // Cleanup; khi IOException, container/Spring xử lý async error.
                clients.remove(emitter);
            }
        }
    }

    @GetMapping(path = "/ndjson", produces = "application/x-ndjson")
    public ResponseEntity<StreamingResponseBody> ndjson() {
        StreamingResponseBody body = out -> {
            for (int i = 1; i <= 3; i++) {
                String line = "{\"seq\":" + i + ",\"type\":\"tick\"}\n";
                out.write(line.getBytes(StandardCharsets.UTF_8));
                out.flush();

                if (i < 3) {
                    try {
                        Thread.sleep(1000L);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw new IOException("Interrupted while streaming",
                                interrupted);
                    }
                }
            }
        };

        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("application/x-ndjson"))
                .header(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(body);
    }
}
~~~

**Cơ chế của code:**
- `Set<SseEmitter>` quản lý các subscribers đang còn kết nối trong **một JVM process**. Concurrent set phù hợp khi controller, scheduler và callbacks chạy khác threads.
- `AtomicLong` chỉ cấp event IDs trong process. Khi restart hoặc chạy nhiều replicas, IDs có thể lặp, **không phải durable resume IDs**.
- `onCompletion`, `onTimeout`, `onError` xóa subscriber để không giữ objects mãi.
- `SseEmitter(300_000L)` đặt timeout của async response; sau 5 phút stream có thể đóng. EventSource sẽ kết nối lại nếu client còn sử dụng và server policy cho phép.
- `@Scheduled(fixedDelay=10_000L)` gửi comment đến các clients theo một scheduler; với app nhiều clients/scheduler chậm, các heartbeat thực tế **không phải đồng hồ chính xác 10.000 ms**.
- Với `IOException` khi gửi vào client đã ngắt, Spring MVC docs khuyến nghị để Servlet container/Spring làm async error dispatch. Code xóa subscriber nhưng **không** gọi lại `emitter.completeWithError(ex)` do lỗi IOException đó.
- NDJSON có 3 records, từng record là JSON hoàn chỉnh cộng `\n`. `out.flush()` đẩy nội dung từ output stream mà Java đang nắm; **không cam kết** mọi proxy trên tuyến sẽ đẩy bytes tới client ngay.
- `Thread.sleep(1000L)` chỉ làm demo cho ta quan sát các dòng, **không phải thiết kế cho production**. Với hàng nghìn stream, tránh giữ nhiều blocking threads vô thời hạn.

### 6.5. `src/main/java/com/example/streamdemo/MvcAsyncConfig.java`

~~~java
package com.example.streamdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcAsyncConfig {

    @Bean
    ThreadPoolTaskExecutor mvcStreamExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mvc-stream-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(64);
        executor.initialize();
        return executor;
    }

    @Bean
    WebMvcConfigurer mvcAsyncConfigurer(
            ThreadPoolTaskExecutor mvcStreamExecutor) {
        return new WebMvcConfigurer() {
            @Override
            public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
                configurer.setTaskExecutor(mvcStreamExecutor);
            }
        };
    }
}
~~~

Spring Framework lưu ý executor mặc định cho MVC asynchronous blocking writes **không phù hợp production khi tải cao**. Ví dụ trên cấu hình thread pool bounded hơn, nhưng số liệu 4/16/64 chỉ là **giá trị minh họa**; production cần load test để chọn queue/pool và xử lý rejection. `SseEmitter` broadcasts ở `@Scheduled` vẫn có thể block scheduler khi client đọc chậm; cấu hình MVC async executor **không tự sửa nhược điểm này**.

### 6.6. `src/main/resources/application.properties`

~~~properties
server.port=8080
spring.application.name=stream-demo

# Default timeout cho MVC async không khai báo riêng.
# SseEmitter(300_000L) vẫn có timeout riêng 5 phút.
spring.mvc.async.request-timeout=6m
~~~

`spring.mvc.async.request-timeout` là thuộc tính **MVC asynchronous request lifetime**, không phải Nginx idle timeout hay TCP keepalive. Trong ví dụ, `SseEmitter` có constructor timeout riêng. Không thêm cấu hình HTTP thread/connection timeout không liên quan rồi kỳ vọng heartbeat hoạt động.

### 6.7. Chạy từ project root

Cần Java 17+ và Maven:

~~~bash
java -version
mvn spring-boot:run
~~~

Sau khi Spring Boot mở cổng 8080, dùng terminal khác.

#### Test SSE với `curl -N`

~~~bash
curl -i -N http://localhost:8080/events
~~~

`-N`/`--no-buffer` tắt output buffering của **curl**. Đầu ra gồm headers (do `-i`) và SSE body. Ngay đầu stream thường có các field dạng:

~~~text
id:1
event:ready
retry:3000
data:connected

:heartbeat

:heartbeat

~~~

**Không cố định thứ tự các dòng `id`/`event`/`retry`/`data` nếu dùng builder; thứ tự/spacing có thể được Spring formatter sắp theo lần gọi.** Các ví dụ hiển thị là **hình dạng khung SSE**, không phải stdout chính xác từng byte. Sau lần gửi initial event, các comments xuất hiện theo nhịp khoảng 10 giây (scheduler có jitter). `curl -N` **hiển thị comment** bởi nó in raw bytes; JavaScript `EventSource` **không** có message callback cho comment.

Giới hạn phiên client để test:

~~~bash
curl -i -N --max-time 27 http://localhost:8080/events
~~~

Lệnh có thể kết thúc với curl exit code **28** do chính `--max-time` sau khoảng 27 giây: **đây không phải lỗi 5xx của server**. Nếu stream không nhận heartbeat trong suốt 27 giây, cần kiểm tra scheduling, proxy và output flushing.

#### Test NDJSON

~~~bash
curl -i -N http://localhost:8080/ndjson
~~~

Sau headers, body lần lượt là:

~~~text
{"seq":1,"type":"tick"}
{"seq":2,"type":"tick"}
{"seq":3,"type":"tick"}
~~~

Mỗi dòng cách nhau khoảng 1 giây trong project thử nghiệm. `Content-Type` là `application/x-ndjson`; một browser `EventSource` sẽ không hiểu đây là SSE. Endpoint trả sau ~2 giây, trong khi SSE vẫn mở đến timeout/ngắt kết nối.

#### So sánh client có/không buffering

~~~bash
# In response body với curl no-buffer để thấy từng khung nhận được.
curl -N -sS http://localhost:8080/events

# Kiểm tra header và thông tin kết nối (không gọi -k để bỏ TLS ngoài lab).
curl -v -N http://localhost:8080/events
~~~

Nếu dùng PowerShell mà `curl` là alias của `Invoke-WebRequest`, có thể gọi `curl.exe`. Trên Windows stdout/console và line endings có thể hiển thị khác; nội dung body SSE vẫn theo framing protocol.

### 6.8. Test EventSource trên browser

Một HTML/JavaScript minh họa cùng origin:

~~~html
<script>
  const stream = new EventSource("/events");

  stream.addEventListener("ready", event => {
    console.log("SSE ready:", event.data, event.lastEventId);
  });

  stream.onerror = () => {
    console.warn("SSE may reconnect automatically");
  };

  // Khi không còn cần stream, giải phóng connection:
  window.addEventListener("beforeunload", () => stream.close());
</script>
~~~

Trong browser, sự kiện có `event: ready` **không** đi vào `onmessage` mặc định; đăng ký `addEventListener("ready", ...)` như trên. Các `: heartbeat` **không tạo callback**, nên chỉ thấy log một lần lúc kết nối rồi có thể reconnect sau timeout — điều đó **không có nghĩa server không gửi heartbeat**. Xem Network tab hoặc dùng curl nếu cần xác nhận.

Vì project chưa có file HTML tĩnh, đoạn script là **minh họa** chèn vào một trang cùng origin hoặc thử trong browser DevTools console tại `http://localhost:8080`. Nếu mở từ trang khác origin, phải xét CORS/SameSite/cookies và xác thực; không dùng mã này làm bảo đảm sẽ chạy không cần cấu hình.

## 7. Nginx cho SSE/NDJSON: cấu hình kiểm tra được

Giả định Nginx trước Spring Boot với backend `127.0.0.1:8080`, và website public thực tế dùng `https://app.example.test` với TLS đã cấu hình ở proxy. Đây là **mảnh server block** minh họa, không phải toàn bộ cấu hình certificate, DNS, HSTS hay security.

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location = /events {
        proxy_pass http://127.0.0.1:8080;

        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Quan trọng: stream từng phần thay vì gom response.
        proxy_buffering off;
        proxy_cache off;
        gzip off;

        # Phải lớn hơn chu kỳ heartbeat + jitter.
        proxy_read_timeout 75s;

        # Theo dõi client chậm trong lúc gửi response.
        send_timeout 75s;
    }

    location = /ndjson {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;
        proxy_cache off;
        gzip off;
        proxy_read_timeout 75s;
        send_timeout 75s;
    }
}
~~~

**Cách đọc cấu hình:**
- `proxy_buffering off` ngăn Nginx đọc gom response trước khi forward, giúp từng phần dữ liệu đi qua sớm.
- `proxy_read_timeout 75s` là timeout khi Nginx chờ **bytes tiếp theo từ Spring**; 10 giây heartbeat của ví dụ nhỏ hơn 75 giây.
- `proxy_cache off` không để cache endpoint realtime như một response tĩnh.
- `gzip off` trong route giúp giảm một tầng có thể tạo buffer/transform; không cần tắt gzip cho toàn website.
- `proxy_http_version 1.1` được set **explicit** để không phụ thuộc Nginx version/default (default upstream version có thay đổi qua các phiên bản). `Connection ""` bỏ header hop-by-hop không mong muốn khi proxying request tới upstream.
- `send_timeout` liên quan đến **Nginx ghi response ra phía client**, không thay thế `proxy_read_timeout`.
- Dù public client dùng HTTP/2 với Nginx, Nginx có thể dùng HTTP/1.1 khi nói chuyện với Spring Boot; hai hop độc lập. HTTP/2 **không** dùng HTTP/1.1 chunked transfer coding.
- `proxy_pass` không có path suffix trong ví dụ nên chuyển đúng path `/events` và `/ndjson`. Với proxy có context path rewrite, phải kiểm tra upstream URL thực.

Nếu backend đã gửi `X-Accel-Buffering: no` như code lab, Nginx có thể dùng header đó để tắt buffering cho response, nhưng cấu hình `proxy_buffering off` tại route làm chính sách rõ ràng. **Không phải tất cả CDN, API gateways hay service mesh hiểu `X-Accel-Buffering`**; cần thêm policy tương đương ở các hop đó.

### 7.1. Kiểm tra Nginx syntax và reload

Trong môi trường sở hữu Nginx:

~~~bash
nginx -t
# Sau khi syntax OK, reload bằng service manager phù hợp.
sudo nginx -s reload
~~~

Chỉ reload sau khi chắc chắn đang trỏ đúng server block/certificate và không làm gián đoạn hạ tầng khác. Trong Docker/Kubernetes, thay bằng quy trình rollout chính thức. Quan trọng: test endpoint **qua URL public của proxy** sau reload; test trực tiếp `localhost:8080` không chứng minh Nginx/CDN đã ngừng buffer.

### 7.2. Quan sát stream qua proxy

~~~bash
curl -i -N https://app.example.test/events
curl -i -N https://app.example.test/ndjson
~~~

Domain là ví dụ không có DNS/certificate thật. Ở hệ thống của bạn, thay bằng domain public/ingress thật. So kết quả trực tiếp backend và qua proxy:
- status 200 và `Content-Type` có đúng?
- initial event có đến client ngay?
- comment heartbeat có xuất hiện theo nhịp 10 giây không?
- có đợt nhiều events dồn lại sau 30–60 giây không?
- khi im lặng quá hạn, Nginx/LB trả 504/502 hay đóng kết nối?
- nếu client đóng, server có dọn subscriber không?

**Một header `X-Accel-Buffering` không hiện trong response cuối không đủ để kết luận proxy đã buffer**: Nginx có thể tiêu thụ/ẩn header đó. Dùng timing bytes ở client và proxy logs.

## 8. Cấu hình phản ví dụ và vì sao nó gây lỗi

### 8.1. Giữ nguyên buffering ở Nginx

~~~nginx
location /events {
    proxy_pass http://127.0.0.1:8080;
    proxy_buffering on;
}
~~~

Với response SSE gồm nhiều frames nhỏ, Nginx có thể gom trước khi gửi downstream. Browser không thấy `ready` hoặc progress cho đến khi buffer đủ hoặc stream kết thúc; proxy có thể vẫn đọc upstream đều đặn, khiến `proxy_read_timeout` không bị kích hoạt nhưng **client thấy không có dữ liệu**.

Không phải mọi cấu hình `proxy_buffering on` luôn delay giống nhau (kích thước buffer, flush, X-Accel-Buffering, transport khác nhau). Kết luận phải dựa trên test thực.

### 8.2. Tưởng `Connection: keep-alive` là heartbeat

~~~http
Connection: keep-alive
~~~

Header này **không phải event body** và không reset mọi idle timer. HTTP/2 còn không dùng `Connection` header. Với SSE, gửi actual SSE comment/data frame định kỳ và đảm bảo các hop forward chúng. Đừng tự set những header hop-by-hop này trong Spring response khi container/proxy sẽ quản lý connection.

### 8.3. Chỉ gọi Java `send` nhưng không có event separator

Sai:

~~~text
data: step 1
data: step 2
~~~

Nếu thiếu **dòng trống**, browser có thể chưa dispatch event. Đúng:

~~~text
data: step 1

data: step 2

~~~

Hai events được phân tách bằng blank line, không phải chỉ mỗi dòng mới. Khi sử dụng Spring `SseEmitter.event()`/WebFlux `ServerSentEvent`, formatter thường xử lý framing chính xác hơn tự nối String.

### 8.4. Dùng `application/json` cho một live EventSource

Nếu server trả `Content-Type: application/json` và body là JSON object/array, browser EventSource có thể từ chối như response không phải event stream. Nếu muốn SSE, set `text/event-stream` và đúng framing. Nếu muốn JSON Lines, dùng client `fetch` + Stream reader và NDJSON parser.

### 8.5. Tắt response cache nhưng quên proxy buffering

~~~http
Cache-Control: no-cache
~~~

Header này không ra lệnh cho Nginx bỏ `proxy_buffering`. Caching và buffering là **hai khái niệm khác nhau**:
- **Caching** giữ một response để có thể phục vụ những request sau.
- **Buffering** gom dữ liệu của **request đang diễn ra** trước khi forward.

`proxy_cache off` và `proxy_buffering off` phục vụ mục đích khác nhau. Cần xét cả compression và downstream.

### 8.6. Tăng mọi timeout thành vô hạn

Điều này che sự cố, tạo kết nối mồ côi, giữ file descriptors/heap và cản trở cleanup. Tốt hơn:
- xác định điểm/ngưỡng timeout theo hop;
- đặt heartbeat có biên độ;
- khai báo timeout hữu hạn/renew semantics rõ;
- có reconnect/backoff, giới hạn số clients và dọn tài nguyên;
- có metrics để phân biệt disconnect hợp lệ với lỗi hạ tầng.

## 9. Reconnect và Last-Event-ID: heartbeat không thay message durability

Browser EventSource tự reconnect khi một SSE connection bị đóng trong điều kiện phù hợp. Server có thể gửi `id: 123` và `retry: 3000`; khi reconnect, browser có thể gửi:

~~~http
GET /events HTTP/1.1
Accept: text/event-stream
Last-Event-ID: 123
~~~

**Nhưng việc EventSource gửi Last-Event-ID không có nghĩa Spring Boot tự phát lại các event bị mất**. Ứng dụng phải giữ một log/queue có IDs ổn định, xác định quyền truy cập stream, và replay các events sau ID client gửi, nếu muốn không mất dữ liệu.

Trong project lab, ID là `AtomicLong` trong JVM, reset sau restart và không đồng bộ giữa replicas. Vì thế endpoint **chỉ minh họa event stream + heartbeat**, **không** cam kết exactly-once delivery, durable resume, replay hay consistency của multi-instance.

Thiết kế production có thể:
1. Gắn ID tăng có thứ tự theo một stream/topic và lưu events vào Kafka/Redis Streams/database với retention.
2. Xác thực client và kiểm tra client có quyền subscribe topic/event IDs được yêu cầu.
3. Khi request mang `Last-Event-ID`, đọc các events sau ID đó nếu còn trong retention.
4. Nếu ID quá cũ hoặc không tồn tại, trả snapshot/điểm bắt đầu mới theo hợp đồng ứng dụng; không im lặng giả vờ đã replay.
5. Với event processing có side effects, client phải xử lý trùng lặp/idempotency; SSE + reconnect không tự bảo đảm exactly-once.

Heartbeat `: heartbeat` không cần event ID vì nó không phải dữ liệu nghiệp vụ. Nếu server gửi heartbeat như **named event**, quyết định có gắn id hay không phải theo replay policy (tránh heartbeat làm vượt qua IDs nghiệp vụ chưa được nhận).

## 10. WebFlux: ServerSentEvent và reactive backpressure

Spring WebFlux hỗ trợ SSE bằng `Flux<ServerSentEvent<T>>` hoặc `Flux<T>` với `produces = MediaType.TEXT_EVENT_STREAM_VALUE`. Không dùng Servlet `SseEmitter` trực tiếp trong ứng dụng Reactor Netty. Một mảnh endpoint **minh họa riêng** (không nằm trong project MVC mục 6; cần `spring-boot-starter-webflux`, Reactor imports và `@RestController`):

~~~java
@GetMapping(path = "/reactive/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    Flux<ServerSentEvent<String>> data =
        Flux.interval(Duration.ofSeconds(5))
            .map(n -> ServerSentEvent.<String>builder()
                .id(Long.toString(n))
                .event("tick")
                .data("tick-" + n)
                .build());

    Flux<ServerSentEvent<String>> heartbeat =
        Flux.interval(Duration.ofSeconds(10))
            .map(n -> ServerSentEvent.<String>builder()
                .comment("heartbeat")
                .build());

    return Flux.merge(data, heartbeat);
}
~~~

- `ServerSentEvent.builder().comment(...)` tạo comment-only frame tương ứng SSE.
- `Flux.interval` tạo events theo timer và `Flux.merge` hợp nhất luồng dữ liệu và heartbeat; **không phải hệ thống event storage/replay**.
- Spring WebFlux dùng non-blocking HTTP I/O nhưng **không đồng nghĩa không có buffering ở Nginx/CDN**. Bảo đảm `text/event-stream` và cấu hình proxy vẫn cần.
- Reactive `Flux` cũng phải giải quyết client chậm, subscriber count, backpressure, cancellation và memory bounds. Một `Flux.interval` không tự bảo đảm chỉ phát khi client có khả năng nhận.
- Reactor Netty có timeout/keepalive settings riêng; không dùng `spring.mvc.async.request-timeout` để cấu hình WebFlux như Servlet MVC.

**Tình huống có cả hai starters:** Nếu project chứa cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thông thường ưu tiên MVC/Servlet application type. Có WebClient/Flux trong project không chứng minh HTTP server đang chạy WebFlux; cần kiểm tra application type/embedded runtime thật.

### 10.1. NDJSON trong WebFlux

Với endpoint tạo `Flux<MyRecord>` và `produces = "application/x-ndjson"`, framework có thể ghi từng object dưới dạng JSON lines theo codecs hỗ trợ. Đây là mô hình khác với trả một `Mono<List<MyRecord>>` thành `application/json` thông thường. Khi dùng `Flux<DataBuffer>` thủ công, nhớ release pooled buffers theo API để tránh memory leaks; nếu chỉ cần JSON records, ưu tiên codecs thay vì tự xử lý buffer.

## 11. Trường hợp WebSocket/long polling: không copy heartbeat SSE

### 11.1. WebSocket

Khi HTTP upgrade thành WebSocket (hoặc negotiate qua cơ chế HTTP/2 hỗ trợ), dữ liệu không còn là `text/event-stream`; nó đi dưới dạng **WebSocket frames**. Giữ kết nối bằng Ping/Pong control frames hoặc heartbeat ở protocol ứng dụng theo implementation; **không** gửi `": heartbeat\n\n"` để client hiểu là WebSocket Ping.

WebSocket có thể dùng cho chat hai chiều hoặc tương tác latency thấp. SSE phù hợp khi chủ yếu server → browser, tận dụng HTTP GET, dễ debug qua curl và EventSource tự reconnect. Hai loại đều cần resource controls, security, idle timeouts và proxy/ingress configuration riêng.

Nginx proxy WebSocket cần xử lý Upgrade/Connection headers theo tài liệu Nginx, **không copy** cấu hình `proxy_set_header Connection ""` của SSE làm hướng dẫn WebSocket mà quên handshake. Ngược lại, SSE **không cần Upgrade** và không cần response 101 Switching Protocols.

### 11.2. Long polling

Long polling giữ một request cho tới khi có event hoặc timeout, rồi trả **một response hoàn chỉnh** (thường JSON) và client mở request mới. Nó không bắt buộc gửi comment/heartbeat trong body. Nếu một load balancer có absolute idle cutoff, có thể chọn poll timeout **nhỏ hơn** cutoff và reissue request, thay vì giữ một SSE stream mở mãi.

Với long polling, đừng phát heartbeat SSE comment vào response `application/json` đang chờ; JSON sẽ bị hỏng. Có thể trả response `204 No Content`/empty success theo contract khi hết hạn chờ và để client poll lại.

## 12. Tác động của HTTP/1.1 và HTTP/2

HTTP/1.1 streaming response có thể dùng **chunked transfer encoding** khi length chưa biết, nhưng `Transfer-Encoding: chunked` **không** thuộc SSE protocol và không đảm bảo mỗi chunk khớp một SSE event. HTTP/2 chia dữ liệu thành **DATA frames** trên stream và multiplex nhiều streams trong một TCP connection; nó **không** dùng HTTP/1.1 chunked coding.

SSE browser kết nối qua HTTP/1.1 có thể bị giới hạn số lượng kết nối đồng thời trên cùng origin bởi browser; với HTTP/2 số lượng concurrent streams phụ thuộc SETTINGS của client/server/proxy. Không dựa vào một con số mặc định trong thiết kế: đo bằng browser/cấu hình thực tế, đặc biệt khi có nhiều tabs và dashboards.

Một reverse proxy có thể nói **HTTP/2 với browser** nhưng **HTTP/1.1 với Spring Boot**; đó là hai hop khác nhau. Cấu hình proxy upstream đúng không buộc client side phải dùng cùng protocol. Vấn đề cốt lõi vẫn là stream framing và unbuffered forwarding, không phải chỉ bật HTTP/2.

## 13. Bảo mật và giới hạn tài nguyên của kết nối dài

### 13.1. Authentication và authorization cho stream

Một kết nối SSE là **HTTP GET** lâu dài. Nó vẫn cần authentication, authorization, tenant/topic isolation và rate limiting:
- Không cho anonymous subscribe vào events riêng tư chỉ vì endpoint dùng GET.
- Browser native `EventSource` không có API tiêu chuẩn để tùy ý thêm custom `Authorization` request header; với same-origin thường dùng cookie/session, hoặc thiết kế ticket ngắn hạn một lần theo chính sách. **Không đặt JWT/secret dài hạn trong query string** vì dễ lộ qua URL logs, referer và history.
- Nếu cross-origin và dùng cookies, cần cấu hình CORS với allowed origins cụ thể, credentials và `SameSite`/`Secure` đúng; kiểm tra Origin/CSRF threat model. CORS **không thay authorization**.
- Không gửi dữ liệu của user A sang stream của user B; subscriber registry cần gắn user/tenant/topic sau khi authorize.
- Không log raw event body chứa PII/secrets; giới hạn retentions và truy cập logs.
- Đảm bảo GET stream không thực hiện tác vụ state-changing nguy hiểm chỉ để mở kết nối.

### 13.2. Giới hạn số clients và backpressure

Mỗi kết nối dài dùng một phần tài nguyên: socket/file descriptor, buffers, memory cho subscriber state, request context, async executor capacity, proxy connection slots, công suất send/flush và downstream network. Nếu fan-out gửi tuần tự tới 10.000 subscribers, một client chậm có thể làm scheduler block quá lâu để mọi client khác nhận heartbeat.

Production cần:
- giới hạn concurrent subscribers **theo user/IP/tenant/node**;
- queue bounded và backpressure/drop policy cho slow consumers;
- phân nhóm/snapshot, broadcast asynchronous hoặc reactive design phù hợp;
- phát heartbeat độc lập hoặc có deadline rõ, tránh sender toàn cục bị một client giữ;
- cleanup chắc chắn trên complete/timeout/error/cancellation và khi app shutdown;
- quan sát số active connections, messages, bytes, send latency, queue depth, dropped events, client disconnects, proxy 499/502/504;
- scale qua load balancer và external event broker; không chỉ giữ clients trong một JVM nếu cần fan-out liên node;
- tránh memory leak khi không xóa emitter sau client ngắt.

Ví dụ `ConcurrentHashMap.newKeySet` chỉ lưu **references** đến active emitters trong JVM. Đó không phải durable subscription store. Không dùng nó để bảo đảm reconnect về cùng replica; nếu cần replay, persist state/offset ngoài app.

### 13.3. Header caching cho dữ liệu riêng tư

Với event nhạy cảm, cân nhắc:

~~~http
Cache-Control: private, no-store, no-transform
Content-Type: text/event-stream
~~~

Đây chỉ là minh họa chính sách; `private`/`no-store` điều khiển caching theo semantics HTTP, không thay quyền truy cập, TLS hoặc response buffering. Cấu hình proxy `proxy_cache off` trên route cũng phải chính xác. Kiểm soát `Vary: Origin` nếu API dùng CORS phản hồi theo Origin, tránh shared cache sai.

### 13.4. TLS, HSTS và mạng nội bộ

SSE qua HTTPS dùng cùng cơ chế TLS như request HTTP khác. Nếu proxy terminate HTTPS, backend có thể dùng HTTP nội bộ theo chính sách, nhưng phải bảo vệ hop đó trong hạ tầng. Không nhầm `X-Forwarded-Proto: https` với bằng chứng backend hop được mã hóa. Khi có CDN/ingress, kiểm tra TLS, proxy idle timeouts, header forwarding, caching và authentication ở từng hop.

## 14. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra và sửa |
| --- | --- | --- |
| `EventSource` báo MIME type không hợp lệ | Response thực `application/json`, HTML login page hoặc proxy error page | `curl -i -N` xem status/Content-Type và body thật |
| Curl thấy một event, browser không gọi `onmessage` | Event có `event: ready`, không phải default message; hoặc là comment-only | Đăng ký `addEventListener("ready")`; comment không dispatch |
| Browser không nhận event cho tới khi server đóng response | Proxy/compression/client buffer | So direct vs public URL; `proxy_buffering off`, `curl -N` |
| Server log send mỗi 10s, client thấy batch mỗi 60s | Proxy gom bytes, gzip hoặc client buffering | Test per-hop, tắt buffering route, xem X-Accel-Buffering |
| Stream đóng sau đúng 5 phút dù heartbeat đều | `SseEmitter(300_000L)` async total timeout | Điều chỉnh lifecycle và reconnect, không chỉ proxy_read_timeout |
| Nginx đóng sau khoảng 60s im lặng | `proxy_read_timeout` giữa các upstream reads | Gửi heartbeat trước ngưỡng, set timeout phù hợp |
| Client đóng stream nhưng server giữ subscriber mãi | Cleanup callbacks thiếu hoặc không phát hiện disconnect | onCompletion/onTimeout/onError; periodic writes; resource bounds |
| `curl` không hiện dữ liệu kịp thời | Curl stdout buffering | `curl -N` hoặc `--no-buffer` |
| `curl --max-time` kết thúc với code 28 | Client tự đặt toàn bộ deadline | Kiểm tra exit code và chọn timeout test phù hợp |
| Không có `X-Accel-Buffering` trong browser headers | Nginx có thể xử lý/ẩn `X-Accel-*` | Đo real timing và cấu hình `proxy_buffering` |
| 504 tại proxy | Upstream silent, timeout, app slow/stuck | So proxy_read_timeout, app logs, thread dumps và scheduler |
| 502 khi proxying | Backend ngắt, error, deploy restart, bad upstream | Kiểm tra upstream logs, TLS/hop health và status |
| CORS error nhưng curl trực tiếp được | Browser Origin/preflight/cookies policy | Network tab, allowedOrigins/credentials, SecurityFilterChain |
| NDJSON client parse lỗi | Thiếu newline hoặc chèn comment SSE/partial JSON | Mỗi dòng JSON hoàn chỉnh, framing theo NDJSON |
| Heartbeat bị xem là message nghiệp vụ | Server gửi `data: ping` thay vì `: ping` | Dùng comment-only SSE hoặc filter riêng event heartbeat |
| Reconnect rồi mất vài events | Không có replay store hoặc Last-Event-ID không được xử lý | Durable IDs, replay semantics, idempotent clients |
| Nhiều tab SSE đơ trên HTTP/1.1 | Connection limit/browser scheduling | Đo per-origin connections, cân nhắc HTTP/2 hoặc multiplex app topics |
| Client chậm khiến mọi clients mất heartbeat | Scheduler/send fan-out blocking | Bounded queues, isolate slow clients, backpressure |
| HTTP/2 bật nhưng vẫn bị buffering | Proxy buffering độc lập với HTTP version | Tắt buffering ở đúng route/hop và verify |
| Response có `Transfer-Encoding: chunked` nhưng vẫn đến trễ | Chunked là framing, không phải flush guarantee | Đo per-hop, Spring flush, proxy buffering |
| SSE 401/403 đột ngột sau redirect/login | Auth cookie/session expired hoặc chain policy | Check status/response Content-Type, session auth và EventSource onerror |

### 14.1. Runbook debug nhanh

1. Ghi **public URL**, DNS/proxy hops, HTTP versions, status, Content-Type, Cache-Control và thời gian ngắt.
2. Test **backend trực tiếp** bằng `curl -N -i http://.../events` và đo thời gian giữa các comments.
3. Test **qua proxy/CDN** bằng `curl -N -i https://.../events` cùng lúc; nếu backend nhanh và public chậm, kiểm tra buffering/transforming ở hop trung gian.
4. Kiểm tra `proxy_buffering`, `X-Accel-Buffering`, `proxy_cache`, gzip, read/send timeouts. Chú ý `proxy_ignore_headers` có thể vô hiệu hóa X-Accel header.
5. Kiểm tra chính xác SSE blank lines, `data/event/id/retry`, ký tự UTF-8 và whether client dùng EventSource hay NDJSON parser.
6. Phân biệt **absolute async timeout** của emitter với **idle timeouts** của Nginx/LB. Nhịp heartbeat phải đến được hop **trước khi** idle cutoff.
7. Xem scheduler/executor: có block/chậm? Ghi last-send/last-receive timestamps, queue depth và downstream send latency.
8. Xem cleanup callbacks khi ngắt client: còn emitter/socket nào leak không?
9. Thử production-like load, nhiều tabs, network interruptions, browser background, proxy restarts, rolling deployments và client reconnect.
10. Với yêu cầu không mất sự kiện, kiểm tra Last-Event-ID và replay durable log, không nhầm heartbeat với message delivery guarantees.

## 15. Bảng quyết định chọn phương án

| Nhu cầu | Ưu tiên | Vì sao |
| --- | --- | --- |
| Browser chỉ cần nhận notifications/progress từ server | **SSE** `text/event-stream` | EventSource + comment heartbeat + reconnect |
| Browser cần gửi liên tục và nhận liên tục cùng connection | **WebSocket** | Full duplex; Ping/Pong, không SSE framing |
| CLI/service cần đọc records JSON từng dòng | **NDJSON** `application/x-ndjson` | Dễ stream/parse incrementally, custom reconnect |
| Trả một JSON array đã tính xong | `application/json` | Không cần giữ kết nối dài |
| Backend chỉ có ít sự kiện và LB không thích long streams | Long polling | Một response hữu hạn rồi client poll lại |
| File download lớn hoặc video seek | Streaming file/HTTP Range, không SSE | Media framing byte ranges khác SSE |
| Gửi token-by-token text (AI output) | SSE hoặc HTTP streaming/NDJSON có contract rõ | Cần flush, framing, proxy unbuffered và cancellation |
| Số client rất lớn, non-blocking I/O cần thiết | Đánh giá WebFlux/event broker và gateway hỗ trợ | Backpressure/concurrency, không chỉ đổi Content-Type |

Không có kỹ thuật nào tự giải quyết mọi lỗi. Chọn theo hướng dữ liệu, semantics reconnect/replay, client capability, proxy behavior, load, authentication và cost. Chọn SSE là **lựa chọn protocol**, còn heartbeat/proxy buffering là **vận hành end-to-end**.

## 16. Bài tập và đáp án

1. Browser EventSource yêu cầu MIME type nào? Có thể cho nó `application/json` và mong nhận `message` events không?
2. Một comment heartbeat SSE hợp lệ trông như thế nào? Vì sao browser không gọi `onmessage` cho nó?
3. `data: ping` khác `: ping` ra sao?
4. Vì sao phải có **dòng trống** giữa các SSE events?
5. Nếu Spring gửi heartbeat mỗi 10 giây nhưng Nginx buffer response, load balancer ở downstream có nhất thiết thấy nhịp không?
6. `proxy_buffering off` khác `proxy_cache off` ở điều gì?
7. `X-Accel-Buffering: no` do ai gửi và ai hiểu? Có phải HTTP standard mọi CDN đều tuân thủ không?
8. `proxy_request_buffering off` có tác dụng gì và có sửa delayed SSE response không?
9. `proxy_read_timeout 75s` là 75 giây tổng response hay giữa hai upstream reads?
10. `SseEmitter(300_000L)` có tự gia hạn đến vô hạn nếu được heartbeat 10 giây không?
11. `spring.mvc.async.request-timeout` có phải Nginx idle timeout không?
12. `curl -N` giải quyết buffering ở server/proxy hay chỉ ở stdout của curl?
13. `Transfer-Encoding: chunked` có được dùng trong HTTP/2 không và có tự làm event giao đúng lúc không?
14. `Content-Type: application/x-ndjson` đòi hỏi mỗi record được phân tách thế nào?
15. Khi EventSource reconnect kèm `Last-Event-ID`, Spring Boot có tự replay dữ liệu từ database không?
16. Vì sao không dùng URL query chứa JWT dài hạn để xác thực SSE?
17. `onCompletion`/`onTimeout`/`onError` của SseEmitter hỗ trợ điều gì?
18. Vì sao fan-out heartbeat cho nhiều clients trên một scheduler blocking có thể không đúng nhịp?
19. Với WebFlux, dùng `Flux<ServerSentEvent<String>>` khác Servlet `SseEmitter` như thế nào?
20. Khi browser nhận `event: ready` nhưng handler `onmessage` im lặng, sửa client ra sao?
21. HTTPS proxy có HTTP/2 với browser nhưng HTTP/1.1 với backend có hợp lệ không?
22. Vì sao tăng tất cả timeout lên vô hạn thường là giải pháp không bền vững?

**Đáp án gợi ý:** (1) `text/event-stream`, không. (2) `: heartbeat\n\n`, comment bị ignore theo protocol. (3) data event thật vs comment no-op. (4) Dòng trống kết thúc event frame. (5) Không, bytes có thể bị giữ ở proxy. (6) Buffering của response đang diễn ra vs caching cho request sau. (7) Backend response header thường dành cho Nginx, không chuẩn cho mọi CDN. (8) Request body buffering, không sửa response. (9) Giữa hai lần đọc từ upstream. (10) Không, vẫn có async lifetime. (11) Không. (12) Chỉ stdout curl. (13) Không; không bảo đảm timing. (14) Mỗi dòng JSON hợp lệ kết thúc LF. (15) Không, cần replay store/logic. (16) Query dễ bị log/lộ. (17) Cleanup subscribers/resources. (18) Slow client block sender, scheduling jitter. (19) Reactive nonblocking pipeline vs Servlet async API, vẫn phụ thuộc proxy. (20) Dùng `addEventListener("ready", ...)`. (21) Có, các hop độc lập. (22) Leak, chi phí tài nguyên, che failure và không thay reconnect policy.

## 17. Tài liệu chuẩn và tham khảo chính thức

- WHATWG HTML Living Standard, **Server-Sent Events / Event Stream Format**: https://html.spec.whatwg.org/multipage/server-sent-events.html — `text/event-stream`, `event/data/id/retry`, comment, reconnect và Last-Event-ID.
- Spring Framework 6.2, **Spring MVC Asynchronous Requests**, mục SSE/HTTP streaming/Disconnects: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html — `SseEmitter`, `ResponseBodyEmitter`, `StreamingResponseBody`, heartbeat và async executor.
- Spring Framework 6.2, **SseEmitter javadoc**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html — `SseEventBuilder`, `comment`, `id`, `retry`.
- Spring Framework, **WebFlux annotated controller return types**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html — `Flux<ServerSentEvent>` và streaming media types.
- Spring Framework, **WebFlux Streaming**: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html — heartbeat, detection, DataBuffer.
- Spring Boot 3.5, **Common application properties**: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html — `spring.mvc.async.request-timeout`.
- Nginx official documentation, **ngx_http_proxy_module**: https://nginx.org/en/docs/http/ngx_http_proxy_module.html — `proxy_buffering`, `X-Accel-Buffering`, `proxy_read_timeout`, `proxy_cache`, `proxy_http_version`, `proxy_request_buffering`.
- Nginx official documentation, **ngx_http_core_module**: https://nginx.org/en/docs/http/ngx_http_core_module.html — `send_timeout`.
- MDN, **Using Server-Sent Events**: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events — EventSource browser API, SSE parsing và phía server.
- RFC 9110, **HTTP Semantics**: https://www.rfc-editor.org/rfc/rfc9110.html — caching/semantics/content representation; cùng HTTP caching standards cho Cache-Control.
