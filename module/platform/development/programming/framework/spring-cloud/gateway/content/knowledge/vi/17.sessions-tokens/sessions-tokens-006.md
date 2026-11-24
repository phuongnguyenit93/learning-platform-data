# SaveSession và thời điểm lưu phiên trước khi chuyển tiếp trong Spring Cloud Gateway

Khi API Gateway sử dụng **phiên đăng nhập (session)**, một request có thể cập nhật dữ liệu phiên rồi lập tức chuyển tiếp đến microservice khác. Nếu trạng thái phiên được lưu vào kho dữ liệu theo cách trì hoãn, downstream có thể xử lý request **trước khi phiên mới nhất được lưu xong**. Trong **SPRING_CLOUD_GATEWAY**, `SaveSession` là một **GatewayFilter Factory** được thiết kế để giải quyết đúng vấn đề thứ tự này: **yêu cầu lưu `WebSession` trước khi tiếp tục chuyển tiếp request xuống backend**.

Bài học thuộc chương **Phiên đăng nhập và token**, trình bày ý nghĩa của `WebSession.save()`, vị trí của `SaveSession` trong reactive filter chain, những điều kiện để một backend có thể đọc phiên, mối liên hệ với Spring Security/Spring Session, cách cấu hình, kiểm thử thứ tự ghi–đọc và các giới hạn về bảo mật. Các chức năng route predicate, biến đổi path/header, service discovery, giới hạn lưu lượng, circuit breaker, retry, TLS và observability vẫn cần chính sách riêng; `SaveSession` không tự thay thế chúng.

> **Phạm vi phiên bản:** Cấu hình chính theo **Spring Cloud Gateway Server WebFlux** với namespace `spring.cloud.gateway.routes` thường gặp ở Gateway 4.x. `SaveSession` làm việc với phiên reactive của **Spring WebFlux**, không phải Servlet `HttpSession`. Gateway Server MVC và các dòng Spring Cloud Gateway mới có thể có API/namespace khác. Hãy đối chiếu tài liệu đúng release train, starter và web stack trước khi triển khai.

## 1. Hiểu ba khái niệm: session, session ID và token

Trước khi sử dụng `SaveSession`, cần tách ba thứ dễ bị gọi chung là “phiên đăng nhập”:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **`WebSession`** | Đối tượng phiên reactive ở phía server, mang ID, thuộc tính, trạng thái khởi tạo và thời hạn không hoạt động | `session.getAttributes().put("workflow", "ready")` |
| **Session ID** | Mã tham chiếu để client/server tìm cùng một phiên; thường được truyền bằng cookie theo cấu hình resolver | `Cookie: SESSION=opaque-id` |
| **Access token** | Credential để một API xác thực/ủy quyền, ví dụ Bearer JWT hoặc opaque OAuth2 token | `Authorization: Bearer eyJ...` |

Với session-based authentication, Gateway có thể khôi phục trạng thái người dùng từ **session ID** do browser gửi. Với JWT resource server stateless, Gateway có thể xác thực request từ Bearer token **mà không cần WebSession**. Đây là hai mô hình khác nhau; có thể tích hợp trong cùng một hệ thống nhưng không nên giả định chúng là một.

**`SaveSession` không tạo JWT, không cấp quyền, không refresh access token và không biến session thành credential để backend tin tưởng.** Nó chỉ làm việc với cơ chế lưu phiên reactive mà ứng dụng Gateway đang sử dụng.

### Một WebSession có thể chứa gì?

Một phiên WebFlux có thể lưu những thuộc tính ứng dụng như trạng thái workflow, dữ liệu hỗ trợ luồng OAuth2 login, một số thông tin security hoặc định danh được quản lý bởi framework. Tuy nhiên:

- Không coi bất cứ thuộc tính tùy ý nào là danh tính đã được xác thực.
- Không lưu password, access token thô hoặc dữ liệu nhạy cảm một cách tùy tiện vào session.
- Nếu dùng kho phiên phân tán, cân nhắc khả năng serialize, dung lượng, TTL và quyền truy cập.
- Không để backend sử dụng một thuộc tính như `role=admin` do client có thể tự khai.

## 2. SaveSession giải quyết chính xác vấn đề nào?

Tài liệu Spring Cloud Gateway mô tả mục đích của **SaveSession GatewayFilter Factory** là buộc thao tác `WebSession.save()` xảy ra **trước khi forwarding call được thực hiện**. Điều này đặc biệt hữu ích nếu dùng **Spring Session với kho lưu trữ hoạt động theo cách trì hoãn (lazy data store)** và muốn bảo đảm trạng thái phiên đã được lưu trước khi gọi downstream.

Giả sử trên cùng một request:

1. Một thành phần WebFlux/Spring Security cập nhật thuộc tính phiên thành `stage=approved`.
2. Gateway chọn một route có URI `lb://orders-service`.
3. Downstream đọc cùng phiên từ kho phân tán để quyết định xử lý tiếp.

Nếu Gateway chỉ trông đợi cơ chế tự lưu phiên ở **cuối response**, có thể xảy ra thứ tự:

~~~text
Gateway sửa session
    ↓
Gateway forward request
    ↓
Downstream đọc kho session: vẫn thấy dữ liệu cũ
    ↓
Gateway hoàn thành response và lưu session
~~~

Khi route có `SaveSession`, thứ tự mong muốn là:

~~~text
Gateway sửa session
    ↓
SaveSession yêu cầu WebSession.save()
    ↓
Chờ thao tác save hoàn thành
    ↓
Gateway mới tiếp tục filter chain để forward
    ↓
Downstream đọc kho session: có cơ hội thấy trạng thái mới
~~~

**Điều kiện quan trọng:** Downstream phải **có khả năng tra cứu đúng cùng một phiên** qua session ID và kho lưu trữ chung thì việc lưu sớm mới giúp nó đọc được trạng thái ấy. `SaveSession` tự nó **không truyền đối tượng `WebSession` qua HTTP**, không tự gắn session ID mới vào request downstream và không thiết lập cơ chế chia sẻ phiên giữa các ứng dụng.

## 3. Vị trí trong reactive Gateway filter chain

Ở Spring Cloud Gateway Server WebFlux, Spring Security `WebFilter` và những `WebFilter` của ứng dụng có thể xử lý request **trước khi Gateway chọn route**. Khi đã chọn route, `FilteringWebHandler` sắp xếp `GlobalFilter` và `GatewayFilter` để xử lý.

`SaveSession` là **GatewayFilter**, không phải `WebFilter` của toàn ứng dụng. Do đó nó chỉ tham gia những request đã chọn được route có filter này (hoặc được áp dụng filter mặc định phù hợp).

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as WebFlux / Security WebFilters
    participant G as Gateway route filter chain
    participant R as WebSession repository
    participant D as Downstream
    C->>W: HTTP request + session cookie (nếu có)
    W->>W: Khôi phục / cập nhật WebSession
    W->>G: Route đã match
    G->>G: SaveSession lấy WebSession
    G->>R: WebSession.save()
    R-->>G: Save hoàn thành (Mono<Void>)
    G->>D: Forward request qua routing filter
    D-->>G: HTTP response
    G-->>C: Trả response cho client
~~~

Sơ đồ thể hiện **điều kiện thứ tự mà SaveSession hướng tới**. Trên thực tế, Spring Session có thể dùng Redis hoặc một repository reactive khác; bản thân Gateway không biết/downstream không tự chia sẻ dữ liệu ứng dụng chỉ vì có cùng `serviceId`.

### Pseudocode để nhớ semantics

Ở mức ý tưởng, filter tương đương một phép ghép reactive như sau:

~~~java
return exchange.getSession()
    .flatMap(WebSession::save)
    .then(chain.filter(exchange));
~~~

Đây là **pseudocode giải thích thứ tự**, không phải đoạn cần tự sao chép vào source nếu đã dùng factory built-in. Ý nghĩa là:

- `exchange.getSession()` lấy phiên reactive gắn với exchange.
- `WebSession.save()` trả về một `Mono<Void>` mô tả thao tác lưu.
- `then(chain.filter(exchange))` chỉ cho phần còn lại của chain chạy khi publisher lưu phiên **hoàn thành thành công**.

Nếu thao tác save phát sinh lỗi, `SaveSession` không bảo đảm request vẫn được forward; lỗi có thể đi vào pipeline xử lý lỗi của Gateway. **Không gọi `block()`** để đợi phiên trong Netty event loop; sử dụng composition reactive như ví dụ.

### “Lưu trước khi forward” không phải “lưu trước khi response commit”

Đây là hai mốc khác nhau:

| Mốc thời gian | Việc đang diễn ra | Vai trò |
|---|---|---|
| **Pre-forward** | Gateway chuẩn bị gửi request xuống backend | `SaveSession` lưu phiên **trước bước này** |
| **Routing/downstream** | Gateway kết nối, chuyển request và đợi response | Backend chỉ đọc session nếu có cơ chế chia sẻ |
| **Response commit** | WebFlux gửi status/headers/cookies về client | Là thời điểm của response lifecycle, **không đồng nghĩa `SaveSession`** |

`SaveSession` **không phải** `ServerHttpResponse.beforeCommit`, không buộc response commit sớm, không tự đặt mã status và không gửi `Set-Cookie` ngay cho downstream. Thao tác lưu kho phiên và gửi cookie session đến browser là hai việc khác nhau, do những thành phần khác nhau của WebFlux/Spring Session đảm nhiệm.

## 4. Cấu hình SaveSession trên một route

Giả sử Gateway expose `/api/orders/**` và backend có service ID `orders-service`. Trên route này cần bảo đảm state phiên đã được lưu trước khi call downstream.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-with-session
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - SaveSession
            - StripPrefix=1
~~~

Giải thích:

1. `Path=/api/orders/**` quyết định route có được chọn hay không.
2. `SaveSession` yêu cầu lưu `WebSession` trước khi phần chain phía sau thực hiện forwarding.
3. `StripPrefix=1` biến `/api/orders/42` thành `/orders/42`, độc lập với nội dung session.
4. `lb://orders-service` dùng cơ chế load balancing/discovery phù hợp để chọn instance backend.

**`SaveSession` không có tham số cấu hình bắt buộc.** Dạng shortcut chính là tên filter:

~~~yaml
filters:
  - SaveSession
~~~

Dạng khai báo rõ factory cũng có thể viết:

~~~yaml
filters:
  - name: SaveSession
~~~

Không tự thêm `args.name`, `args.value` hoặc một tên session cookie vào factory này theo thói quen từ những filter khác. Những chính sách cookie/SessionRepository thuộc tầng Spring WebFlux/Spring Session, không phải tham số của `SaveSession`.

### Lựa chọn các route thật sự cần lưu sớm

Không phải mọi route đều cần `SaveSession`. Ví dụ:

- API stateful mà downstream cần đọc ngay trạng thái phiên đã được Gateway cập nhật: **có thể cần**.
- API stateless Bearer JWT, downstream tự validate token: thường **không có lý do dùng SaveSession**.
- API chỉ đọc dữ liệu công khai, không dùng session: thường **không cần**.
- Luồng đăng nhập được Spring Security tự xử lý và trả redirect trước khi chọn Gateway route: **route SaveSession có thể không chạy**.

Dùng filter đúng nơi giảm thao tác lưu kho không cần thiết và tránh làm tăng latency/tải lên Redis hoặc một session repository khác.

## 5. Dùng default-filters cho nhiều route có session

Nếu nhiều route cùng cần đảm bảo pre-forward save, ở những phiên bản Gateway Server WebFlux hỗ trợ `default-filters` có thể khai báo:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - SaveSession
      routes:
        - id: orders
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
        - id: profile
          uri: lb://profile-service
          predicates:
            - Path=/api/profile/**
~~~

Các route được áp dụng default filter sẽ có hành vi lưu phiên trước khi tiếp tục chain, theo thứ tự filter thực tế.

**Cân nhắc trước khi áp dụng toàn cục:**

- Một lần `WebSession.save()` có thể thực hiện I/O hoặc thao tác với kho phiên; nếu gắn vào mọi route, cần đánh giá overhead và lỗi kho dữ liệu.
- Request không match bất kỳ route nào có thể **không đi qua GatewayFilter** này.
- HTTP 401/403 bị Spring Security chặn trước Gateway route có thể **không thực thi SaveSession**.
- Nếu default filter và route filter cùng khai báo `SaveSession`, cần tránh lặp thao tác lưu phiên mà không có mục đích.
- Thay `default-filters` không đồng nghĩa thay `discovery.locator.filters` của các route tự sinh; kiểm tra Route runtime để xác nhận filter có mặt trên các tuyến thực sự.

Một số ứng dụng tốt hơn nên bật `SaveSession` **chỉ ở những routes stateful** thay vì toàn bộ traffic, đặc biệt khi có nhiều API không dùng cookie/session.

## 6. Thứ tự filter và lúc thuộc tính session thay đổi

Lợi ích của `SaveSession` phụ thuộc việc **dữ liệu cần lưu đã được ghi vào WebSession trước khi SaveSession thực thi**.

Ví dụ về một luồng hợp lệ:

~~~text
WebFilter / security component cập nhật session.stage = "ready"
    ↓
Gateway chọn Route
    ↓
SaveSession gọi WebSession.save()
    ↓
Gateway routing đến backend
    ↓
Backend đọc stage = "ready" từ cùng shared session repository
~~~

Nhưng nếu một filter phía **sau `SaveSession`** mới cập nhật session:

~~~text
SaveSession lưu state cũ
    ↓
Filter phía sau ghi session.stage = "ready"
    ↓
Routing đến backend
    ↓
Backend có thể vẫn đọc state cũ từ repository
~~~

Lúc kết thúc HTTP exchange, cơ chế quản lý session có thể lưu lại thay đổi, nhưng **không thể dựa vào nó để bảo đảm state đã cập nhật trước downstream call**.

### Pre-filter khác post-filter

Trong Gateway WebFlux, code trước `chain.filter(exchange)` được coi là thao tác **pre**; logic được ghép sau completion của chain là **post** theo thứ tự reactive. Nếu bạn cập nhật session **ở post-filter**, cập nhật ấy thường quá muộn cho mục tiêu “backend thấy state mới trong cùng request”.

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    return chain.filter(exchange)
        .then(exchange.getSession().doOnNext(session ->
            session.getAttributes().put("stage", "ready")).then());
}
~~~

Đoạn trên là **phản ví dụ về thứ tự**, không phải gợi ý production. Nó ghi thuộc tính **sau khi chain phía sau đã hoàn thành**, nên không có cách nào để `SaveSession` nằm trước đó giúp downstream thấy giá trị `ready` trong lần forward vừa xảy ra.

Muốn session state ảnh hưởng đến downstream, hãy thực hiện thay đổi **trước bước SaveSession**, hoặc tổ chức filter rõ ràng để save sau khi hoàn tất cập nhật và trước bước forward. Đừng dựa vào thứ tự dòng YAML nếu có `GlobalFilter`, `Ordered`, filter lồng nhau hoặc điều kiện error/retry; kiểm tra thực tế thứ tự ở runtime.

## 7. Session được tạo và lưu như thế nào?

Trong WebFlux, `WebSession` cung cấp những thao tác quan trọng:

~~~java
WebSession session = ...;

session.start();                              // Chủ động bắt đầu session nếu cần
session.getAttributes().put("stage", "ready"); // Ghi thuộc tính
Mono<Void> result = session.save();           // Publisher lưu session
~~~

Đoạn mã trên chỉ minh họa API của một `WebSession` đã có, **không phải code synchronous hoàn chỉnh trong reactive handler**. Trong ứng dụng WebFlux, đối tượng được lấy từ `exchange.getSession()` hoặc cơ chế injection của framework, sau đó cần composition reactive.

Các trạng thái cần phân biệt:

| Trạng thái | Ý nghĩa | `SaveSession` có làm gì thêm? |
|---|---|---|
| Session đã tồn tại và có state cần lưu | Đối tượng phiên có thể ghi vào repository | Yêu cầu lưu trước khi forward |
| Session mới được khởi tạo và bắt đầu hợp lệ | Có thể phát sinh session ID và thuộc tính | Gọi save, tùy session manager/repository |
| Session chưa `start()` và không có dữ liệu cần lưu | Có thể chưa cần tạo persisted session | **Không giả định SaveSession tự tạo session đăng nhập** |
| Session đã invalidated | Không còn phiên hợp lệ theo lifecycle | Không thể dùng SaveSession để “khôi phục” đăng nhập |
| Session hết hạn ở repository | Client vẫn có cookie cũ nhưng session không còn | Cần xác thực/khởi tạo lại theo policy |

`WebSession` được khôi phục/lưu bởi `WebSessionManager` và cơ chế repository tùy cấu hình. Khi tích hợp **Spring Session**, có thể dùng một kho phiên phân tán như Redis. Việc ghi nhận thuộc tính vào WebSession **không đồng nghĩa dữ liệu đã bền vững trong kho** tại đúng thời điểm một microservice khác hỏi đọc.

### Spring Session và kho phiên trì hoãn

Spring Session hỗ trợ thay thế cơ chế quản lý phiên mặc định bằng một repository có khả năng chia sẻ giữa instance nếu cấu hình phù hợp. Các chi tiết cần biết:

- Các Gateway instance phải dùng **cùng backend lưu phiên và namespace/serialization tương thích** nếu muốn truy cập chung.
- Phiên có TTL; cấu hình timeout và eviction ảnh hưởng hành vi đăng nhập.
- Lỗi Redis/repository không phải lỗi HTTP routing thông thường; lưu sớm có thể khiến request thất bại **trước khi gọi downstream**.
- Kho phiên “lazy” có thể hoãn một phần thao tác ghi tới thời điểm cuối exchange; `SaveSession` là điểm ép lưu trong pipeline.
- Không nên coi mọi implementation `WebSession.save()` đều có semantics giống transaction database hoặc distributed lock. Nó bảo đảm publisher `save` hoàn thành theo hợp đồng của repository, không tự bảo đảm backend khác dùng nhất quán mô hình cache/replica và đọc ngay dữ liệu mới.

Với yêu cầu đọc-sau-ghi nghiêm ngặt, kiểm tra **consistency của session repository** và đường đọc của downstream, không chỉ kiểm tra rằng `SaveSession` có mặt trong YAML.

## 8. Khi nào backend thật sự đọc được phiên của Gateway?

Đây là chỗ nhiều hướng dẫn bỏ sót. HTTP request truyền **headers, path, query và body**; đối tượng Java `WebSession` trong Gateway **không được serialize tự động thành một object gửi sang backend**.

Để downstream tự đọc cùng session, cần thỏa mãn một mô hình chia sẻ đã được thiết kế:

1. **Cùng cách xác định session ID**, thường từ cookie `SESSION` hoặc một tên cookie được cấu hình riêng.
2. **Session ID đó thực sự hiện diện trong request đến backend**, hoặc backend có một cơ chế nhận định danh đã được tin cậy khác.
3. **Cùng kho phiên**, namespace, key prefix và serializer phù hợp, nếu backend trực tiếp đọc WebSession/Spring Session.
4. **Quyền truy cập và ranh giới bảo mật** giữa Gateway, backend và session store được thiết kế đúng.
5. **Thời điểm lưu/đọc phù hợp** với consistency của kho.

Nếu backend chỉ xác thực Bearer JWT hoặc nhận danh tính đã được xác minh qua cơ chế token exchange, nó **không cần đọc chung WebSession**. Trong kiến trúc ấy, `SaveSession` có thể không liên quan đến cách backend nhận danh tính.

### Trường hợp session mới ở request đầu tiên

Một tình huống rất quan trọng:

- Client gửi request đầu tiên **chưa có cookie session**.
- Gateway tạo/bắt đầu session và `SaveSession` lưu phiên trước forwarding.
- Nhưng request chuyển tiếp có thể **vẫn không chứa session ID mới**, vì cookie `Set-Cookie` dành cho browser được phát ra trong **response**, không phải tự động quay ngược thành `Cookie` trên request downstream.

Do đó backend **chưa chắc đọc được session vừa tạo ở ngay request đầu tiên**, dù save thành công.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant G as Gateway
    participant ST as Shared session store
    participant D as Downstream
    B->>G: Request 1, chưa có Cookie
    G->>ST: Tạo/cập nhật rồi SaveSession.save()
    ST-->>G: Save thành công
    G->>D: Forward Request 1 (có thể chưa có session cookie mới)
    D-->>G: Response 1
    G-->>B: Response 1 + Set-Cookie của session
    B->>G: Request 2 + Cookie: SESSION=<id>
    G->>ST: Cập nhật rồi SaveSession.save()
    ST-->>G: Save xong
    G->>D: Forward Request 2, cookie hiện hữu có thể được chuyển tiếp
    D->>ST: Tra cứu session theo ID nếu cùng repository
    ST-->>D: Trạng thái mới
    D-->>B: Response 2 qua Gateway
~~~

**Không tự gắn session ID vào header downstream một cách tùy tiện để chữa vấn đề này.** Nếu thiết kế cần xác thực ngay ở lần gọi đầu, hãy dùng cơ chế token propagation/ủy quyền nội bộ phù hợp hoặc một hợp đồng danh tính được bảo vệ bằng TLS/mTLS, filter loại header giả mạo và backend validation.

## 9. Ví dụ Java: ghi thuộc tính trước khi Gateway filter chạy

Ví dụ sau **chỉ phục vụ lab**, minh họa một `WebFilter` cập nhật thuộc tính session trước khi route `/lab/session/**` được chọn. Đừng dùng cơ chế ghi session cho mọi request công khai như một cách tạo đăng nhập.

~~~java
package example.gateway.lab;

import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class LabSessionMarkerFilter implements WebFilter, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String path = exchange.getRequest().getPath()
            .pathWithinApplication().value();

        if (!path.startsWith("/lab/session/")) {
            return chain.filter(exchange);
        }

        return exchange.getSession().flatMap(session -> {
            // Lab: tạo phiên, sau đó thay đổi state trước route filters.
            session.start();
            Integer oldCount = session.getAttribute("labCounter");
            session.getAttributes().put("labCounter",
                oldCount == null ? 1 : oldCount + 1);

            return chain.filter(exchange);
        });
    }
}
~~~

Sau đó khai báo route lab:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: lab-shared-session
          uri: http://localhost:9090
          predicates:
            - Path=/lab/session/**
          filters:
            - SaveSession
            - StripPrefix=2
~~~

Nếu gọi `/lab/session/check`, filter path sẽ chuyển tiếp `/check` đến backend. `LabSessionMarkerFilter` chạy ở tầng `WebFilter` và cập nhật session **trước** khi Gateway route filter `SaveSession` được thực thi.

**Giới hạn của ví dụ:**

- `@Component` và `Ordered.HIGHEST_PRECEDENCE` được dùng để minh họa chủ đích chạy sớm; trong ứng dụng có Spring Security phải kiểm tra thứ tự và chính sách bảo vệ lab endpoint.
- `session.start()` tạo/khởi động session cho request lab, không thực hiện authentication; phải hạn chế endpoint để tránh tạo vô số session do khách lạ.
- Tăng `labCounter` là một thao tác read–modify–write đơn giản, **không an toàn như bộ đếm phân tán khi nhiều request song song dùng cùng session**.
- Backend sẽ chỉ đọc được `labCounter` theo WebSession khi **cùng repository + session ID** như phân tích ở phần 8.
- Không lưu access token, thông tin định danh thật hoặc bí mật người dùng để làm bài test.

### Backend lab có thể xác minh điều gì?

Nếu backend cũng sử dụng Spring WebFlux + Spring Session với repository chung và cookie ID tương thích, một endpoint có thể đọc giá trị `labCounter` từ `WebSession` của **chính request backend**. Nếu backend chỉ là server echo đơn giản và không tích hợp Spring Session, nó có thể ghi lại `Cookie`/path nhưng **không thể tự chứng minh dữ liệu đã nằm trong Redis**.

Có thể dùng một backend test sở hữu quyền truy cập session repository hoặc một công cụ quan sát kho phiên trong môi trường kín để so sánh trạng thái ngay lúc downstream nhận request. Không in session ID/token hoặc nội dung session nhạy cảm trong log production.

## 10. Kiểm thử thực tế: xác nhận save trước forwarding

### Chuẩn bị

- Gateway Server WebFlux trên `localhost:8080` với route `lab-shared-session` như phần 9.
- Backend lab `localhost:9090` có endpoint `GET /check`; nếu muốn đọc state, phải tích hợp session repository chung.
- Session repository thật hoặc giả lập có thể quan sát việc lưu; với Spring Session Redis, đảm bảo cả hai ứng dụng dùng thông số tương thích.
- Security policy và giới hạn truy cập phù hợp cho `/lab/session/**` trong môi trường thử nghiệm.

### Bước 1 — Request tạo session và nhận cookie

~~~bash
curl -i -c session-cookies.txt \
  "http://localhost:8080/lab/session/check"
~~~

`-c` yêu cầu cURL lưu cookie do server trả về trong tệp **ở môi trường lab của người chạy lệnh**. Đọc response để xác định tên cookie thực tế, thường có thể là `SESSION` với cấu hình Spring Session phù hợp; **không mặc định luôn là `JSESSIONID` hoặc `SESSION`**.

Ở request đầu, Gateway có thể tạo session và gửi `Set-Cookie` về browser/client. Backend **chưa chắc nhận session ID mới trong cùng request**, nên nếu endpoint trả `missing` trong bước này, chưa thể kết luận `SaveSession` hỏng.

### Bước 2 — Gửi lại cookie đã nhận

~~~bash
curl -i -b session-cookies.txt -c session-cookies.txt \
  "http://localhost:8080/lab/session/check"
~~~

`-b` gửi cookie đã lưu. `LabSessionMarkerFilter` tăng `labCounter` ở Gateway; `SaveSession` yêu cầu lưu trước khi forward. Nếu backend đọc được cùng session từ repository, nó có thể nhìn thấy **giá trị vừa cập nhật ở lượt 2**, không phải giá trị của lượt trước.

Trong môi trường thử nghiệm, nên đối chiếu đồng thời:

| Quan sát | Điều cần kiểm chứng |
|---|---|
| Cookie client gửi | Đúng session ID do Gateway phát ở response trước |
| Session tại Gateway | `labCounter` đã tăng trước bước `SaveSession` |
| Kho phiên | Có dữ liệu cập nhật khi thao tác save hoàn thành |
| Request downstream | Backend nhận request đúng path `/check` và cookie thích hợp |
| Backend session | Đọc đúng cùng session và giá trị mới, nếu có cấu hình chia sẻ |
| Response client | Được xử lý bình thường, không rò rỉ ID/thuộc tính nhạy cảm |

### Bước 3 — Thử bỏ SaveSession trong lab

Chỉ trong môi trường kiểm soát, bỏ `SaveSession` khỏi route, giữ các thành phần khác như cũ, rồi thực hiện lại bài test. Nếu session repository/manager ghi dữ liệu tự động ở một thời điểm muộn hơn, backend **có thể thấy giá trị trước đó** trong request đang chuyển tiếp. Nhưng cũng có thể **vẫn thấy giá trị mới** nếu implementation đã lưu sớm; đó không nhất thiết là lỗi thử nghiệm.

**Không khẳng định “không có SaveSession thì luôn sai”.** Mục tiêu là chứng minh bảo đảm về thứ tự khi cần, và đo hành vi của **repository/phiên bản thực tế**.

### Bước 4 — Kiểm tra kho phiên lỗi

Trong lab, mô phỏng repository phản hồi lỗi hoặc không khả dụng. Khi `save()` lỗi, route có thể thất bại **trước khi gọi downstream**, với HTTP status do cơ chế error handling quyết định. Kiểm tra timeout, connection pool, fallback vận hành và tỷ lệ lỗi, không mặc định SaveSession sẽ bỏ qua lỗi để phục vụ tiếp request.

### Bước 5 — Kiểm tra concurrency

Cho hai request cùng session ID đến đồng thời rồi cập nhật một thuộc tính. `SaveSession` giúp lưu trước từng lần forwarding nhưng **không biến cập nhật session thành transaction có khóa phân tán**. Với `labCounter`, giá trị có thể bị lost update nếu repository không cung cấp cơ chế đồng bộ phù hợp. Nếu nghiệp vụ cần tính chính xác cao, sử dụng storage có atomic operation/transaction/optimistic locking phù hợp thay vì dùng WebSession làm bộ đếm giao dịch.

## 11. SaveSession và Spring Security/OAuth2

### Với đăng nhập bằng session cookie

Spring Security WebFlux có thể dùng `WebSession` cho các luồng đăng nhập và state liên quan (chẳng hạn OAuth2 login). Sau khi người dùng đã đăng nhập, những route Gateway khác có thể cần state hiện thời được lưu trước khi gọi backend.

Tuy vậy:

- Một bước `oauth2Login` có thể trả **redirect** ngay trong security filter chain, không chọn Gateway route; do đó `SaveSession` của một route downstream **không nhất thiết chạy trên response đăng nhập**.
- Có session không đồng nghĩa backend sẽ tự biết principal; phải thiết kế **identity propagation** phù hợp.
- Backend cần kiểm tra authorization theo token/danh tính đáng tin cậy; session attribute từ ứng dụng khác không phải mặc định được tin.
- Logout cần xử lý invalidation/revocation/cookie đúng cơ chế của security và repository. `SaveSession` không phải filter logout.

### Với OAuth2 TokenRelay

`TokenRelay` của Spring Cloud Gateway liên quan việc đưa access token hợp lệ của một OAuth2 client/authorized client xuống backend khi đã tích hợp đúng Spring Security/OAuth2 client. Nó **không đồng nghĩa** với `SaveSession`:

| `SaveSession` | `TokenRelay` |
|---|---|
| Thao tác với `WebSession.save()` | Thao tác với cơ chế chuyển tiếp access token |
| Nhằm lưu trạng thái phiên trước forwarding | Nhằm đưa credential thích hợp vào request downstream |
| Không tự tạo `Authorization` header | Có thể liên quan `Authorization: Bearer ...` theo cơ chế được hỗ trợ |
| Có ích trong luồng stateful/shared session | Có ích khi downstream dùng OAuth2 token |
| Không tự xác thực người dùng | Cần authentication/authorized client thích hợp |

Một Gateway dùng **JWT Resource Server stateless** có thể hoàn toàn không cần `SaveSession` để thực hiện authentication. Ngược lại, một Gateway dùng OAuth2 login có WebSession có thể cần quan tâm thứ tự lưu state, nhưng vẫn phải quyết định chính sách TokenRelay và audience của token.

### Chú ý session fixation và cookie policy

Ứng dụng dùng session phải xử lý session fixation sau đăng nhập theo cơ chế Spring Security phù hợp, session timeout, cookie `HttpOnly`, `Secure`, `SameSite` và domain/path, cũng như CSRF cho những flow dựa vào cookie. Không dùng `SaveSession` như một lý do tắt CSRF hoặc chấp nhận mọi `Origin` trong CORS.

## 12. Liên hệ với hệ thống nhiều Gateway instance và nhiều backend

Nếu Gateway chạy hai instance A/B sau load balancer:

~~~mermaid
flowchart LR
    C["Browser + session cookie"] --> LB["Ingress / load balancer"]
    LB --> GA["Gateway A"]
    LB --> GB["Gateway B"]
    GA --> STORE["Shared session repository"]
    GB --> STORE
    GA --> BACK["Downstream microservice"]
    GB --> BACK
    BACK -.->|"Nếu có hợp đồng đọc session"| STORE
~~~

Các điều kiện vận hành quan trọng:

- **Không phụ thuộc vào sticky session** nếu kiến trúc kỳ vọng bất kỳ Gateway instance nào cũng đọc được phiên từ repository chung.
- Các instance Gateway phải có cùng chính sách cookie resolver, namespace session, clock, TTL và serialization phù hợp.
- Nếu downstream đọc cùng repository, việc cấp quyền truy cập kho phiên cần giới hạn tối thiểu; không nên cho mọi service đọc toàn bộ session của mọi user.
- `SaveSession` không đồng bộ đồng hồ, không giải quyết eventual consistency/caching của repository và không phòng tránh xung đột cập nhật cùng session.
- Một instance backend unhealthy, discovery sai hoặc `lb://` không resolve được có thể gây lỗi dù session save thành công.

Đối với những hệ thống có yêu cầu bảo mật cao, **truyền token với audience và scope phù hợp** hoặc một danh tính nội bộ được xác thực thường rõ ràng hơn việc cho mọi backend cùng đọc session store. Việc lựa chọn kiến trúc phụ thuộc threat model và nhu cầu tương thích của ứng dụng.

## 13. Hiệu năng, lỗi và khả năng quan sát

`SaveSession` nằm trên **đường xử lý request** trước forwarding. Nếu session repository truy cập mạng, thời gian chờ save được cộng vào latency của request.

| Rủi ro | Tác động | Cách kiểm soát |
|---|---|---|
| Redis/repository có độ trễ cao | Tăng thời gian trước khi downstream được gọi | Theo dõi latency của thao tác save và timeout |
| Repository ngừng hoạt động | Request có thể lỗi trước routing | Giám sát availability, connection pool, circuit/timeout phù hợp ở tầng lưu trữ |
| Bật `SaveSession` cho mọi route stateless | Tải thêm và chi phí không cần thiết | Chỉ dùng nơi thực sự cần thứ tự lưu |
| Session chứa payload lớn | Tốn I/O/serialization và gây tăng bộ nhớ | Giữ session gọn, không lưu dữ liệu lớn/PII tùy tiện |
| Nhiều request cùng một session | Race/lost update | Dùng storage có primitive đồng bộ thích hợp |
| TTL hết hạn khi request đang xử lý | Backend không tìm được session dù client có cookie | Rà soát timeout và semantics expiration |
| Sai cookie hoặc namespace giữa services | Backend không truy xuất đúng state | Kiểm tra resolver, store, serializer, domain/path |
| Retry/fallback | Có thể phát sinh nhiều lần forward sau một lần lưu, tùy order | Thiết kế idempotency, timeout, kiểm tra filter order |

**Phân biệt nhóm metrics:** time-to-route, thời gian save session, thời gian chọn instance `lb://`, downstream latency, error rate của repository và tỉ lệ 401/403/429/5xx. Đừng quy mọi response 503 cho load balancer khi trước routing có một thao tác lưu phiên bị timeout.

### Logging an toàn

Có thể ghi **route ID**, tên service, trạng thái đã có session, thời lượng save và kết quả lỗi ở mức log phù hợp. Không log:

- Raw session ID hoặc cookie value.
- Bearer access/refresh token.
- Thuộc tính phiên chứa danh tính cá nhân, địa chỉ, email hay dữ liệu bảo mật.
- Nội dung cache/session repository đầy đủ.

Nếu cần correlation ID, dùng mã không nhạy cảm được tạo/kiểm tra theo chính sách observability; không biến session ID thành trace ID công khai.

## 14. Troubleshooting: khi SaveSession dường như không hoạt động

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xác minh |
|---|---|---|
| Không thấy session trong repository | Chưa start session, không có state cần lưu, sai repository hoặc route không chạy | Kiểm tra WebSession lifecycle, cấu hình Spring Session và route/filter |
| Backend vẫn đọc state cũ | Cập nhật thuộc tính xảy ra sau SaveSession, repository cache/consistency hoặc không cùng session | Kiểm tra thứ tự pre-filters và cùng ID/store |
| Backend không thấy session trên request đầu | Client chưa có cookie; Set-Cookie mới chỉ gửi trong response | Test request thứ hai dùng cookie đã phát |
| Gateway có session, backend không có | Backend không tích hợp shared repository/cookie resolver khác | Kiểm tra cookie, namespace, serializer, trust boundary |
| Gateway trả 5xx trước khi gọi backend | `save()` lỗi/timeout hoặc filter khác chặn sớm | Quan sát log publisher save, downstream call count |
| Response thiếu `Set-Cookie` | Chưa có persisted session, cookie policy, session resolver hoặc lỗi response | Kiểm tra start/lifecycle và response headers |
| SaveSession không chạy trên trang login | Security handler trả redirect/401 trước Gateway route | Kiểm tra WebFilter/security handler và route matching |
| TokenRelay không chuyển Bearer | Chưa có OAuth2 client/authorized client hoặc cấu hình relay sai | Kiểm tra TokenRelay riêng; SaveSession không tạo token |
| Chỉ lỗi ở vài Gateway nodes | Cấu hình phiên/Redis khác hoặc route không đồng nhất | So sánh từng instance, store namespace, versions, clocks |
| Có lỗi 404 sau SaveSession | Route path/rewrite hoặc downstream endpoint sai | Kiểm tra route predicate, StripPrefix, backend path |
| Auth 401/403 dù session đã lưu | Chưa authenticated, scope/role thiếu, cookie không được gửi | Kiểm tra Spring Security policy, không coi save là login |
| Tải Redis tăng mạnh sau deploy | Đã áp dụng `default-filters: SaveSession` quá rộng | Đo save calls/latency và thu hẹp phạm vi |

### Quy trình khoanh vùng năm câu hỏi

1. **Request có chọn đúng Gateway route** gắn `SaveSession` hay bị security/rate limiter xử lý sớm?
2. **Session có được start/cập nhật** trước lúc filter này chạy không?
3. **`WebSession.save()` có hoàn thành thành công** trước khi downstream call bắt đầu không?
4. **Backend nhận session ID nào** và có đọc đúng store/namespace/serializer không?
5. **Response cuối do ai tạo**: backend, fallback, error handler, Spring Security hay web server?

Có thể sử dụng một backend echo để quan sát path, header `Cookie` và thời điểm nhận request; nhưng **echo cookie một mình không xác nhận session đã được lưu**. Muốn chứng minh read-after-write cần phép đo repository/backend phù hợp.

## 15. Checklist trước khi đưa vào production

- [ ] Tôi biết `SaveSession` là **GatewayFilter Factory**, không phải `WebFilter` bao phủ mọi HTTP request.
- [ ] Tôi hiểu filter gọi `WebSession.save()` **trước khi chain tiếp tục forwarding**.
- [ ] Tôi phân biệt WebSession, session ID/cookie và Bearer token/JWT.
- [ ] Tôi không dùng `SaveSession` để cấp quyền, đăng nhập hoặc tự gắn token xuống backend.
- [ ] Tôi biết các thuộc tính cần lưu phải được cập nhật **trước SaveSession**.
- [ ] Tôi đã chọn đúng route có session; không mặc định bật filter trên toàn bộ API stateless.
- [ ] Tôi biết dạng cấu hình `- SaveSession` không yêu cầu tham số.
- [ ] Tôi đã kiểm tra Spring Session/repository, TTL, consistency, namespace và serialization khi dùng shared sessions.
- [ ] Tôi hiểu request đầu tạo phiên có thể **chưa có cookie session mới ở phía backend**.
- [ ] Tôi đã kiểm thử lưu trước forward trên **request có session ID hiện hữu**.
- [ ] Tôi có test trường hợp repository lỗi/timeout và concurrency.
- [ ] Tôi đã xác định mô hình security: session cookie, OAuth2 login, JWT Resource Server, TokenRelay hoặc token exchange.
- [ ] Tôi vẫn xử lý session fixation, logout, CSRF, SameSite, Secure, HttpOnly và TLS theo threat model.
- [ ] Tôi đã rà soát `lb://`, path rewrite, rate limiter, retry/circuit breaker và fallback độc lập với phiên.
- [ ] Tôi đo được latency/error của session save mà không log session ID, cookie, token hoặc dữ liệu riêng tư.
- [ ] Tôi đã kiểm tra hành vi trong cụm Gateway nhiều instance và đường truyền đến backend.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tìm **SaveSession GatewayFilter Factory** ở đúng mục **Server WebFlux** và phiên bản Gateway đang dùng.
- [Spring Framework — WebSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html) — `start()`, `getAttributes()`, `save()` và vòng đời phiên reactive.
- [Spring Framework — WebSessionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/WebSessionManager.html) — quản lý và lưu phiên theo request/response.
- [Spring Session Reference](https://docs.spring.io/spring-session/reference/) — repository, phiên phân tán, Spring Session Redis và những lưu ý khi chia sẻ session.
- [Spring Security Reactive Reference](https://docs.spring.io/spring-security/reference/reactive/index.html) — `SecurityWebFilterChain`, OAuth2 login, JWT resource server và security trong WebFlux.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/) — ý nghĩa của `Mono<Void>`, `flatMap`, `then` và cách compose thao tác bất đồng bộ.

**Ghi nhớ:** `SaveSession` bảo đảm **lệnh lưu `WebSession` được thực thi và hoàn thành trước khi Gateway tiếp tục chuyển tiếp request** theo pipeline reactive. Nó hữu ích khi trạng thái phiên được lưu trì hoãn nhưng backend cần đọc ngay. Tuy nhiên, muốn backend thấy phiên mới nhất, vẫn phải **cập nhật session trước filter, lưu trữ đúng repository và chuyển session ID theo một hợp đồng tin cậy**; đây không phải cơ chế phát token hay thay thế bảo mật ở downstream.
