# Kiểm tra hỗ trợ Servlet, WebFlux, chỉ mục và sự kiện của từng kho

Spring Session cung cấp nhiều repository để lưu trạng thái phiên vào Redis, JDBC hoặc bộ nhớ trong tiến trình. Các repository không có cùng khả năng. Một implementation có thể tích hợp với Servlet API qua `HttpSession`, implementation khác có thể cung cấp API reactive cho WebFlux; một repository hỗ trợ tìm session theo principal, trong khi repository khác chỉ đọc theo session ID; cơ chế phát sự kiện hết hạn cũng phụ thuộc vào cách datastore thông báo và cách repository dọn dữ liệu.

Khi chọn kho cho `SPRING_SESSION`, cần kiểm tra bốn năng lực riêng: **Servlet**, **WebFlux**, **index**, và **lifecycle events**. Việc một repository lưu được session không có nghĩa nó tự hỗ trợ cả hai ngăn xếp web, truy vấn principal hoặc phát đầy đủ sự kiện. Bài học này trình bày cách phân biệt các hợp đồng, cách đọc capability của từng loại repository và cách kiểm thử trước khi vận hành nhiều instance.

## 1. Bốn năng lực cần kiểm tra

| Năng lực | Câu hỏi cần trả lời | API hoặc cơ chế liên quan |
|---|---|---|
| Servlet | Ứng dụng có tiếp tục dùng `HttpSession` trong Servlet filter chain được không? | `SessionRepository<S>`, `SessionRepositoryFilter` |
| WebFlux | Ứng dụng có dùng `WebSession` với thao tác lưu bất đồng bộ, không chặn event loop không? | `ReactiveSessionRepository<S>`, `WebSessionManager` |
| Index | Có thể tìm session theo principal hoặc thuộc tính index thay vì chỉ theo session ID không? | `FindByIndexNameSessionRepository<S>`, `IndexResolver<S>` |
| Events | Repository có phát sự kiện tạo, xóa, hết hạn; sự kiện được kích hoạt và chuyển tới ứng dụng bằng cách nào? | `SessionCreatedEvent`, `SessionDeletedEvent`, `SessionExpiredEvent`, datastore notifications hoặc cleanup job |

Các năng lực này độc lập. Ví dụ, repository JDBC có thể phù hợp cho ứng dụng Servlet và hỗ trợ principal index nhưng không cung cấp API reactive native. Một Redis repository reactive có thể phù hợp với WebFlux nhưng không nên mặc định có cùng tính năng principal index như repository Redis đồng bộ. Một kho có TTL cũng không nhất thiết phát được sự kiện hết hạn tới ứng dụng.

## 2. Phân biệt Servlet và WebFlux ở cấp hợp đồng

### 2.1. Servlet: SessionRepository và HttpSession

Trong ứng dụng Spring MVC chạy trên Servlet container, Spring Session đặt `SessionRepositoryFilter` vào Servlet filter chain. Filter đọc session ID từ cookie/header resolver, tìm session trong repository, bọc request để các thành phần ứng dụng tiếp tục dùng `HttpSession`, rồi lưu thay đổi theo vòng đời request.

Hợp đồng đồng bộ cốt lõi là:

```java
public interface SessionRepository<S extends Session> {
    S createSession();
    void save(S session);
    S findById(String id);
    void deleteById(String id);
}
```

Các phương thức trả kết quả trực tiếp hoặc `void`. Servlet repository có thể gọi JDBC hoặc Redis client đồng bộ theo implementation. Ứng dụng Servlet không cần biết session được lưu ở máy chủ nào; nó tiếp tục dùng `request.getSession()`.

Ví dụ bật session JDBC trong ứng dụng Servlet:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession
public class JdbcHttpSessionConfiguration {
}
```

Ứng dụng cần `DataSource`, schema Spring Session JDBC đúng phiên bản và cấu hình Servlet filter được Spring Session/Spring Boot đăng ký. Annotation này không tạo một repository reactive cho WebFlux.

### 2.2. WebFlux: ReactiveSessionRepository và WebSession

Ứng dụng WebFlux dùng `WebSession` và `WebSessionManager`. Repository reactive biểu diễn thao tác bằng Reactor `Mono`, cho phép framework phối hợp I/O bất đồng bộ mà không phải chặn event loop để chờ kho dữ liệu.

Hợp đồng tổng quát:

```java
public interface ReactiveSessionRepository<S extends Session> {
    Mono<S> createSession();
    Mono<Void> save(S session);
    Mono<S> findById(String id);
    Mono<Void> deleteById(String id);
}
```

Ví dụ bật Redis WebSession trong ứng dụng WebFlux:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration
@EnableRedisWebSession
public class RedisWebSessionConfiguration {
}
```

Ứng dụng cần client Redis reactive và `ReactiveRedisConnectionFactory` tương thích. `@EnableRedisWebSession` tích hợp Redis với WebFlux; nó không đăng ký `SessionRepositoryFilter` cho Servlet và controller WebFlux nên thao tác qua `WebSession`.

### 2.3. Không biến I/O blocking thành reactive chỉ bằng Mono

JDBC là API blocking. Bọc một lời gọi JDBC trong `Mono.fromCallable(...)` không làm driver trở thành non-blocking. Nếu publisher chạy trên event loop, thao tác JDBC vẫn có thể chặn thread phục vụ nhiều request. Có thể cô lập lời gọi blocking trên scheduler dành cho tác vụ blocking, nhưng đó vẫn là một ranh giới blocking có giới hạn tài nguyên và cần timeout/pool phù hợp.

Nếu ứng dụng WebFlux cần session repository reactive end-to-end, chọn implementation có `ReactiveSessionRepository` và driver reactive tương ứng. Không suy ra rằng vì Redis có cả client đồng bộ và reactive nên mọi repository Redis đều dùng được cho cả Servlet lẫn WebFlux; cần xác định chính xác class repository và hợp đồng mà nó triển khai.

## 3. Index là gì và khi nào cần?

Repository cơ bản thường tìm session theo ID. Khi ứng dụng cần tìm tất cả phiên của một người dùng, cần một index phụ ánh xạ principal name sang các session ID.

Spring Session định nghĩa `FindByIndexNameSessionRepository<S>` với thao tác `findByPrincipalName(String)`. `PRINCIPAL_NAME_INDEX_NAME` là tên index tiêu chuẩn cho principal. `IndexResolver<S>` xác định các giá trị index từ session.

Ví dụ truy vấn principal:

```java
Map<String, ?> sessions =
        sessionRepository.findByPrincipalName(principalName);
```

Kết quả là map có session ID làm key và session làm value. Một người dùng có thể có nhiều session từ nhiều trình duyệt hoặc thiết bị. Ứng dụng có thể dùng index để hiển thị phiên đăng nhập, giới hạn số phiên hoặc logout các phiên khác.

Index không phải cơ chế xác thực hoặc phân quyền. Endpoint truy vấn phải lấy principal của caller từ `Authentication` đã xác minh hoặc kiểm tra quyền quản trị trước khi tra cứu người khác. Không nhận principal tùy ý từ request rồi trả danh sách session.

### 3.1. Principal index cần nguồn dữ liệu đáng tin cậy

Với tích hợp Spring Security, `PrincipalNameIndexResolver` có thể lấy tên từ `SecurityContext` được lưu trong session. Nếu ứng dụng dùng custom authentication hoặc không lưu SecurityContext vào session, cần thiết lập principal index attribute tường minh hoặc cung cấp `IndexResolver` riêng.

Principal name phải thống nhất giữa lúc ghi và lúc truy vấn. Nếu một instance ghi theo email còn instance khác truy vấn theo internal user ID, index sẽ không khớp dù cùng dùng Redis. Khi hỗ trợ nhiều tenant hoặc nhiều OIDC issuer, cần dùng định danh duy nhất trong đúng phạm vi, thường là internal user ID bất biến hoặc giá trị có namespace tenant/issuer.

## 4. Lifecycle events có ý nghĩa gì?

Spring Session có các sự kiện vòng đời phổ biến:

- `SessionCreatedEvent`: session mới được tạo/lưu theo cơ chế repository.
- `SessionDeletedEvent`: session bị xóa một cách tường minh.
- `SessionExpiredEvent`: session hết hạn theo thời hạn lưu trữ/logic.

Ứng dụng có thể lắng nghe bằng `@EventListener`:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.session.events.SessionCreatedEvent;
import org.springframework.session.events.SessionDeletedEvent;
import org.springframework.session.events.SessionExpiredEvent;

@Component
public class SessionLifecycleListener {

    @EventListener
    public void onCreated(SessionCreatedEvent event) {
        // Ghi metric hoặc audit event không nhạy cảm.
    }

    @EventListener
    public void onDeleted(SessionDeletedEvent event) {
        // Xử lý hậu kỳ khi session bị xóa tường minh.
    }

    @EventListener
    public void onExpired(SessionExpiredEvent event) {
        // Ghi nhận phiên hết hạn hoặc dọn dữ liệu phụ có thể retry.
    }
}
```

Các sự kiện này là application events trong Spring. Việc class sự kiện tồn tại không có nghĩa mọi repository đều phát đủ cả ba loại trong mọi trường hợp. Cần kiểm tra implementation, phiên bản, cách kích hoạt và khả năng nhận sự kiện khi ứng dụng restart hoặc listener tạm ngừng.

Không dùng listener hết hạn làm cơ chế duy nhất để thu hồi quyền hoặc hoàn tất nghiệp vụ quan trọng. Sự kiện có thể đến trễ, không được phát do thiếu cấu hình, hoặc bị bỏ lỡ nếu nguồn là Pub/Sub không bền vững. Quyền truy cập phải được kiểm tra trên mỗi request dựa vào session hợp lệ và nguồn dữ liệu chính.

## 5. Ma trận năng lực theo repository

Bảng dưới đây là hướng dẫn chọn loại implementation thường gặp. Tên class, annotation và chi tiết event có thể thay đổi theo phiên bản Spring Session; trước khi cấu hình, hãy kiểm tra đúng dependency đang dùng và class repository thực tế được Spring tạo.

| Repository / datastore | Servlet | WebFlux | Principal index | Lifecycle events |
|---|---|---|---|---|
| Redis indexed repository cho Servlet | Có, qua `SessionRepository` và `SessionRepositoryFilter` | Không dùng trực tiếp cho `WebSession` | Có, qua `FindByIndexNameSessionRepository` và `IndexResolver` | Có thể hỗ trợ create/delete/expire; expiration/deletion từ Redis phụ thuộc keyspace notifications và listener |
| Redis reactive repository | Không phải `HttpSession` Servlet repository | Có, qua `ReactiveSessionRepository` và `WebSessionManager` | Không giả định có cùng principal index như indexed Servlet repository; kiểm tra interface/API của phiên bản | Khả năng và cơ chế event phụ thuộc reactive implementation; kiểm thử riêng, không suy từ Servlet repository |
| JDBC indexed repository | Có, qua `SessionRepository` và Servlet filter | Không có JDBC reactive native trong repository chuẩn | Có, `JdbcIndexedSessionRepository` hỗ trợ truy vấn principal index | Create/delete và cleanup expiration có hành vi riêng; không giả định có notification theo từng khóa như Redis |
| Map/in-memory repository | Có với repository đồng bộ tương ứng | Chỉ khi chọn implementation reactive riêng nếu phiên bản cung cấp | Tùy class; không suy từ việc dùng Map | Thường chỉ có sự kiện trong phạm vi tiến trình nếu implementation phát; không có sự kiện phân tán giữa các instance |
| Custom repository | Theo interface được triển khai | Theo interface được triển khai | Chỉ có nếu implement index contract và duy trì index | Chỉ có nếu publisher và lifecycle/cleanup được triển khai đúng |

Điểm quan trọng nhất là kiểm tra **interface thực tế**:

- `SessionRepository` cho luồng Servlet đồng bộ.
- `ReactiveSessionRepository` cho luồng WebFlux reactive.
- `FindByIndexNameSessionRepository` cho truy vấn theo index principal.
- Event support phải được xác minh riêng qua tài liệu, cấu hình và integration test.

Một class có thể triển khai nhiều interface, nhưng không nên suy đoán từ tên datastore. Hai repository cùng dùng Redis vẫn có thể có API và feature khác nhau.

## 6. Redis cho Servlet: indexed repository và notifications

Với ứng dụng Servlet, Spring Session Redis cung cấp repository đồng bộ. Khi cần truy vấn session theo principal, chọn indexed repository và cấu hình tương ứng, thường thông qua annotation hỗ trợ Redis HTTP session có index theo phiên bản Spring Session.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisIndexedHttpSession;

@Configuration
@EnableRedisIndexedHttpSession
public class RedisIndexedHttpSessionConfiguration {
}
```

Ứng dụng cần `RedisConnectionFactory`, cấu hình cookie/session filter và serializer tương thích giữa các instance. Principal index được duy trì bởi repository; resolver phải có thể lấy principal từ session hoặc từ thuộc tính đã được ứng dụng ghi.

Redis dùng TTL để hết hạn khóa. Để Spring Session nhận được thông báo về expiration/deletion từ Redis, keyspace notifications cần được cấu hình đúng. Cờ `notify-keyspace-events` thường cần bao gồm các nhóm expiration và keyevent mà implementation sử dụng; tài liệu Spring Session Redis của phiên bản đang chạy sẽ chỉ rõ giá trị cần thiết, thường gặp là `Egx`.

Một số Redis managed service không cho ứng dụng chạy `CONFIG SET`. Khi đó có thể dùng `ConfigureRedisAction.NO_OP` để Spring Session không cố thay cấu hình, nhưng quản trị viên phải bật keyspace notifications ở phía dịch vụ. `NO_OP` không tự bật notification.

```java
@Bean
ConfigureRedisAction configureRedisAction() {
    return ConfigureRedisAction.NO_OP;
}
```

Nếu notifications không hoạt động, session vẫn có thể hết hạn theo TTL và không còn được đọc như phiên hợp lệ, nhưng listener có thể không nhận được sự kiện hết hạn cần thiết. Kiểm thử cả việc request không thể dùng session đã hết hạn và việc application listener có nhận event hay không.

## 7. Redis cho WebFlux: reactive repository

Với WebFlux, Spring Session Redis có repository reactive và cấu hình tích hợp `WebSession`. Ứng dụng cần `ReactiveRedisConnectionFactory` và client reactive tương ứng. Controller làm việc với `WebSession`, còn framework quản lý việc load/save thông qua `WebSessionManager`.

```java
@RestController
public class WebFluxPreferenceController {

    @PostMapping("/preferences/language")
    public Mono<String> saveLanguage(
            @RequestParam String language,
            WebSession session) {
        session.getAttributes().put("app.language", language);
        return Mono.just("saved");
    }
}
```

Không gọi `block()` trên event loop và không tự `subscribe()` trong controller/service để lưu session fire-and-forget. Hãy trả publisher cho framework để lỗi và completion được gắn với vòng đời response.

Không giả định mọi khả năng của Redis Servlet repository đều có ở reactive repository. Đặc biệt, cần kiểm tra xem implementation reactive đang dùng có hỗ trợ principal index, event publication và expiration notification ở mức nào. Nếu ứng dụng cần truy vấn session theo principal hoặc audit mọi lần expire, hãy chứng minh khả năng bằng API cụ thể và integration test; nếu thiếu, cân nhắc thiết kế index/event riêng có độ bền phù hợp.

## 8. JDBC: Servlet, principal index và cleanup

Spring Session JDBC chuẩn cung cấp `JdbcIndexedSessionRepository`, một repository đồng bộ cho Servlet. Nó lưu session và thuộc tính trong các bảng JDBC, đồng thời có khả năng tìm session theo principal name.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession
public class JdbcSessionConfiguration {
}
```

Ứng dụng cần `DataSource`, schema tương ứng với database dialect và `SessionRepositoryFilter` được đăng ký. JDBC repository chuẩn không phải một `ReactiveSessionRepository`; việc bọc JDBC call trong `Mono` không làm I/O trở thành non-blocking.

Principal index được lưu trong cấu trúc dữ liệu JDBC mà `JdbcIndexedSessionRepository` quản lý. Ứng dụng có thể dùng `FindByIndexNameSessionRepository` để tìm phiên theo principal, với điều kiện principal được resolver xác định đúng và dữ liệu index được lưu.

JDBC cleanup thường dựa vào thao tác truy vấn/xóa các session đã hết hạn theo lịch hoặc cơ chế cleanup của repository. Đây khác với Redis keyspace notification theo từng khóa. Không nên giả định mỗi hàng bị cleanup tự động tạo ra một sự kiện `SessionExpiredEvent` mà không kiểm tra phiên bản và implementation. Nếu nghiệp vụ cần sự kiện cho từng session hết hạn, hãy xác minh event contract hoặc xây dựng cơ chế audit/outbox riêng có thể phục hồi sau restart.

## 9. In-memory repository: hữu ích cho test, không chia sẻ giữa instance

Repository lưu trong bộ nhớ có thể hữu ích cho demo hoặc kiểm thử logic, nhưng mỗi instance có vùng nhớ riêng. Nếu request đầu đến instance A và request sau đến instance B, B không đọc được session được lưu trong bộ nhớ của A.

Đặc điểm cần lưu ý:

- Dữ liệu mất khi tiến trình dừng hoặc khởi động lại.
- Không chia sẻ session giữa các instance.
- Không có TTL hoặc cleanup phân tán trừ khi implementation cụ thể cung cấp.
- Principal index và event support phụ thuộc class repository; không suy ra từ API map.
- Không dùng in-memory repository làm giải pháp session cho production nhiều instance.

Nếu dùng repository map trong test, cần ghi rõ test đang kiểm tra logic ứng dụng chứ không chứng minh khả năng chia sẻ session, TTL hoặc event của Redis/JDBC.

## 10. Kiểm tra capability từ class và bean thực tế

Trước khi chọn repository, kiểm tra implementation được Spring inject. Có thể dùng IDE, debugger hoặc log cấu hình để xác định class bean. Trong một test cấu hình, có thể kiểm tra kiểu:

```java
assertThat(sessionRepository)
        .isInstanceOf(FindByIndexNameSessionRepository.class);
```

Đối với reactive, kiểm tra bean được cấu hình có implement `ReactiveSessionRepository` và ứng dụng WebFlux đang sử dụng nó qua `WebSessionManager`. Không chỉ kiểm tra có bean tên `sessionRepository`; một bean cùng tên có thể là implementation khác hoặc thuộc một context khác.

Checklist kiểm tra:

1. Xác định ứng dụng chạy Servlet hay WebFlux.
2. Xác định class repository thực tế và interface nó triển khai.
3. Kiểm tra factory/driver: `RedisConnectionFactory`, `ReactiveRedisConnectionFactory` hoặc `DataSource`.
4. Kiểm tra annotation/configuration đã tạo đúng repository, filter hoặc WebSessionManager.
5. Kiểm tra index contract và resolver nếu cần tìm theo principal.
6. Kiểm tra event publisher/listener, Redis notifications hoặc JDBC cleanup.
7. Kiểm tra phiên bản Spring Session, Spring Data và datastore client để tránh dùng API không có trong dependency.

## 11. Kiểm thử Servlet và WebFlux riêng biệt

Không nên dùng một bài test chung để kết luận cả Servlet và WebFlux được hỗ trợ. Hai ngăn xếp có vòng đời request, API session và cơ chế I/O khác nhau.

| Loại test | Servlet | WebFlux |
|---|---|---|
| API session | `HttpSession` | `WebSession` |
| Integration point | `SessionRepositoryFilter` | `WebSessionManager` |
| Repository contract | `SessionRepository` | `ReactiveSessionRepository` |
| Kiểm thử controller | MockMvc hoặc embedded Servlet container | WebTestClient |
| Kiểm tra async | Kiểm tra Servlet async nếu dùng | Kiểm tra publisher và không block event loop |
| Chia sẻ nhiều instance | Cùng repository và cookie/session ID | Cùng reactive repository và cookie/session ID |

Với Redis, test cần xác minh factory, serialization, TTL và kết nối thật. Với JDBC, test cần dùng đúng database engine/driver vì schema, SQL dialect, isolation và cleanup có thể khác nhau.

## 12. Kiểm thử principal index

Nếu ứng dụng cần quản lý phiên theo người dùng, hãy kiểm tra toàn bộ chuỗi từ xác thực đến index:

1. Tạo request đã xác thực bằng principal tin cậy.
2. Xác nhận SecurityContext hoặc principal index attribute được lưu trong session.
3. Chờ repository commit session.
4. Gọi `findByPrincipalName` bằng đúng canonical principal name.
5. Xác minh session ID xuất hiện trong kết quả.
6. Đăng xuất hoặc xóa session qua repository.
7. Truy vấn lại và xác minh session không còn được trả về như phiên hoạt động.
8. Thử nhiều session cùng principal, nhiều tenant và nhiều instance.

Kiểm thử cả trường hợp principal không có, anonymous, username thay đổi, principal sai chữ hoa/thường và resolver không thể đọc SecurityContext. Không dùng display name hoặc dữ liệu request tự khai làm principal index.

## 13. Kiểm thử lifecycle events

Một bài test event cần phân biệt việc session đã hết hạn trong repository với việc listener đã nhận được notification. Có thể kiểm tra:

| Sự kiện/tình huống | Cách mô phỏng | Điều cần xác minh |
|---|---|---|
| Tạo session | Gọi request tạo session và lưu thuộc tính | Event tạo được phát theo implementation |
| Xóa tường minh | Gọi `invalidate()` hoặc `deleteById` | Event xóa được phát nếu repository hỗ trợ |
| Expiration | Tạo session timeout ngắn rồi chờ/điều khiển thời gian | Session không còn hợp lệ; event hết hạn được phát nếu cơ chế hỗ trợ |
| Redis notifications tắt | Tắt keyspace notifications trong Redis test | Phân biệt TTL với event listener không nhận notification |
| Redis listener restart | Dừng subscriber trong lúc expire | Không giả định Pub/Sub sẽ phát lại thông báo đã mất |
| JDBC cleanup | Để session quá hạn rồi chạy cleanup | Xác minh hàng được dọn và kiểm tra event behavior của đúng phiên bản |
| Listener lỗi | Ném exception trong listener test | Không làm sai trạng thái session đã được repository lưu/xóa |
| Nhiều instance | Listener chạy ở một hoặc nhiều node | Xác định node nào nhận event, có thể nhận trùng hay bỏ lỡ không |

Không dùng listener để thực hiện side effect không idempotent mà không có cơ chế chống trùng. Nếu event đến nhiều lần, việc gửi email hoặc thu hồi tài nguyên phải có khóa idempotency. Nếu event bị mất mà nghiệp vụ cần bảo đảm xử lý, dùng outbox hoặc queue bền vững thay vì dựa vào datastore notification đơn thuần.

## 14. Hỗ trợ sự kiện khác nhau giữa Redis và JDBC

Redis và JDBC có cơ chế phát hiện hết hạn khác nhau:

**Redis:** khóa có TTL. Khi hết hạn, Redis phát keyspace notification nếu đã bật đúng cấu hình. Spring Session listener nhận notification và có thể phát `SessionExpiredEvent`. Thông báo Pub/Sub không phải hàng đợi bền vững; subscriber ngừng hoạt động có thể bỏ lỡ sự kiện. Việc notification đến cũng không phải một deadline chính xác tới từng mili giây.

**JDBC:** session có thời điểm hết hạn được lưu trong bảng. Repository có thể chạy truy vấn cleanup định kỳ để xóa hàng quá hạn. Đây là cơ chế quét dữ liệu, không giống một notification do datastore phát ra ngay khi từng hàng hết hạn. Việc có phát sự kiện cho từng session bị cleanup hay không cần kiểm tra theo phiên bản repository. Nếu yêu cầu audit bắt buộc, không nên phụ thuộc một giả định về event.

**In-memory:** hết hạn thường được phát hiện khi repository kiểm tra session hoặc dọn dữ liệu trong tiến trình. Khi tiến trình dừng, mọi trạng thái và listener đều mất. Nó không cung cấp cơ chế phân tán bền vững.

Trong mọi trường hợp, sự kiện chỉ là tín hiệu vòng đời. Request vẫn phải kiểm tra session còn hợp lệ; ứng dụng không được cấp quyền dựa trên việc listener đã chạy hay chưa.

## 15. Chọn repository theo yêu cầu ứng dụng

| Yêu cầu | Lựa chọn cần xem xét | Điều phải xác minh |
|---|---|---|
| Spring MVC/Servlet, dùng Redis chia sẻ | Redis Servlet repository | `SessionRepository`, filter, serializer, TTL và notifications |
| Spring MVC/Servlet, dùng relational database | JDBC indexed repository | `SessionRepository`, schema, principal index, cleanup job và SQL dialect |
| WebFlux cần I/O reactive | Reactive Redis repository hoặc repository reactive khác | `ReactiveSessionRepository`, reactive connection factory và WebSession integration |
| Tìm mọi session theo user | Repository implement `FindByIndexNameSessionRepository` | Principal resolver, index consistency, cleanup và authorization |
| Cần audit session hết hạn | Repository có event support đã kiểm chứng hoặc event pipeline riêng | Độ bền, delivery, retry, duplicate và khả năng phục hồi sau restart |
| Kiểm thử controller đơn giản | Mock hoặc in-memory repository | Không suy rộng kết quả thành khả năng phân tán production |
| Chạy nhiều instance | Redis/JDBC/shared store phù hợp | Mọi instance dùng cùng datastore, serializer, schema, principal naming và policy |

Không chọn Redis chỉ vì cần WebFlux nếu implementation đang dùng là đồng bộ. Không chọn JDBC cho WebFlux rồi kỳ vọng JDBC blocking tự trở thành non-blocking. Không chọn repository không index rồi kỳ vọng có thể tìm session theo principal. Không chọn TTL rồi kỳ vọng tự động nhận đầy đủ lifecycle events.

## 16. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| WebFlux chặn event loop khi truy cập session | Dùng JDBC hoặc Redis client đồng bộ trong chuỗi reactive | Kiểm tra `ReactiveSessionRepository`, driver và scheduler |
| `HttpSession` không được Spring Session quản lý | Filter chưa đăng ký hoặc đang chạy WebFlux | Kiểm tra Servlet stack và `SessionRepositoryFilter` |
| WebFlux không thấy session đã tạo | Đang dùng Servlet repository hoặc không cấu hình `WebSessionManager` | Dùng reactive repository và cấu hình WebFlux phù hợp |
| `findByPrincipalName` trả rỗng | Repository không hỗ trợ index hoặc principal resolver không có giá trị | Kiểm tra interface, resolver và SecurityContext persistence |
| Redis hết hạn nhưng không nhận event | Keyspace notifications tắt hoặc listener không chạy | Kiểm tra `notify-keyspace-events`, listener container và quyền cấu hình |
| JDBC dọn session nhưng không có event mong đợi | Cleanup query không phát event từng session hoặc version không hỗ trợ | Kiểm tra implementation; dùng audit/outbox nếu cần bảo đảm |
| Event được xử lý nhiều lần | Notification trùng hoặc nhiều listener/instance cùng nhận | Thiết kế handler idempotent và xác định phạm vi listener |
| Session index còn ID cũ | Cleanup index chậm hoặc session bị xóa ngoài repository | Đọc lại session, kiểm tra cleanup và tránh thao tác Redis trực tiếp |
| Test in-memory pass nhưng production không chia sẻ session | In-memory repository chỉ tồn tại trong một process | Integration test với datastore dùng chung và hai instance |

## 17. Quy trình xác minh trước khi đưa vào production

1. Xác định ứng dụng là Servlet hay WebFlux; không trộn `HttpSession` và `WebSession` tùy tiện.
2. Xác định repository class thực tế và interface mà nó triển khai.
3. Kiểm tra driver/factory đồng bộ hay reactive, cùng timeout và connection pool.
4. Nếu cần principal index, xác nhận repository implement `FindByIndexNameSessionRepository` và resolver lấy đúng danh tính.
5. Nếu cần events, kiểm tra sự kiện tạo/xóa/hết hạn riêng biệt và cách datastore kích hoạt chúng.
6. Với Redis, xác minh TTL, keyspace notifications và listener; với JDBC, xác minh cleanup schedule và event contract.
7. Kiểm thử session create/read/update/delete trên datastore thật.
8. Kiểm thử principal index với nhiều session và nhiều instance.
9. Kiểm thử event khi listener restart, datastore lỗi và cleanup chạy.
10. Ghi rõ giới hạn của implementation để các thành phần nghiệp vụ không dựa vào một capability chưa được bảo đảm.

Một repository chỉ phù hợp khi nó triển khai đúng hợp đồng của ngăn xếp web, cung cấp index nếu use case cần truy vấn theo principal và có cơ chế event đáp ứng mức độ bảo đảm mà nghiệp vụ yêu cầu. Kiểm tra interface và hành vi thực tế theo đúng phiên bản Spring Session giúp tránh nhầm lẫn giữa khả năng lưu session, khả năng tìm session và khả năng thông báo vòng đời khi ứng dụng chạy trên nhiều instance.
