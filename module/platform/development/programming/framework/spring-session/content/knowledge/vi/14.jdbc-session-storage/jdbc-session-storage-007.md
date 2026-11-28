# Chỉ mục thời điểm hết hạn, principal và tra cứu phiên

Spring Session JDBC lưu phiên trong cơ sở dữ liệu quan hệ và dùng các chỉ mục để tìm phiên theo session ID, xác định phiên đã đến hạn dọn dẹp và tra cứu các phiên của một người dùng. Ba nhu cầu này tương ứng với ba cột quan trọng trong bảng `SPRING_SESSION`: `SESSION_ID`, `EXPIRY_TIME` và `PRINCIPAL_NAME`.

`JdbcIndexedSessionRepository` triển khai cả `SessionRepository` và `FindByIndexNameSessionRepository`. Nhờ đó, ứng dụng có thể tiếp tục dùng `HttpSession` qua `SessionRepositoryFilter`, đồng thời có thể tra cứu nhiều phiên theo principal khi cần quản lý đăng nhập đồng thời, buộc đăng xuất hoặc hiển thị danh sách phiên của tài khoản. Để các truy vấn này hoạt động hiệu quả và đúng, schema phải có đúng chỉ mục, dữ liệu principal phải được ghi vào session và tác vụ dọn phiên hết hạn phải được vận hành phù hợp.

## 1. Mô hình dữ liệu và các chỉ mục mặc định

### 1.1. Hai bảng lưu session

Spring Session JDBC mặc định dùng hai bảng:

- `SPRING_SESSION`: lưu thông tin chung của mỗi phiên, bao gồm ID, thời gian, timeout và principal.
- `SPRING_SESSION_ATTRIBUTES`: lưu từng thuộc tính session dưới dạng bản ghi riêng, gắn với khóa nội bộ của phiên.

Ví dụ schema PostgreSQL theo tài liệu Spring Session:

```sql
CREATE TABLE SPRING_SESSION (
    PRIMARY_ID CHAR(36) NOT NULL,
    SESSION_ID CHAR(36) NOT NULL,
    CREATION_TIME BIGINT NOT NULL,
    LAST_ACCESS_TIME BIGINT NOT NULL,
    MAX_INACTIVE_INTERVAL INT NOT NULL,
    EXPIRY_TIME BIGINT NOT NULL,
    PRINCIPAL_NAME VARCHAR(100),
    CONSTRAINT SPRING_SESSION_PK PRIMARY KEY (PRIMARY_ID)
);

CREATE UNIQUE INDEX SPRING_SESSION_IX1 ON SPRING_SESSION (SESSION_ID);
CREATE INDEX SPRING_SESSION_IX2 ON SPRING_SESSION (EXPIRY_TIME);
CREATE INDEX SPRING_SESSION_IX3 ON SPRING_SESSION (PRINCIPAL_NAME);

CREATE TABLE SPRING_SESSION_ATTRIBUTES (
    SESSION_PRIMARY_ID CHAR(36) NOT NULL,
    ATTRIBUTE_NAME VARCHAR(200) NOT NULL,
    ATTRIBUTE_BYTES BYTEA NOT NULL,
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_PK
        PRIMARY KEY (SESSION_PRIMARY_ID, ATTRIBUTE_NAME),
    CONSTRAINT SPRING_SESSION_ATTRIBUTES_FK
        FOREIGN KEY (SESSION_PRIMARY_ID)
        REFERENCES SPRING_SESSION(PRIMARY_ID)
        ON DELETE CASCADE
);

CREATE INDEX SPRING_SESSION_ATTRIBUTES_IX1
    ON SPRING_SESSION_ATTRIBUTES (SESSION_PRIMARY_ID);
```

Kiểu dữ liệu của cột nhị phân và một số chi tiết DDL thay đổi theo hệ quản trị cơ sở dữ liệu. Spring Session đóng gói script schema cho nhiều nhà cung cấp tại `org/springframework/session/jdbc/schema-*.sql`; nên dùng script đúng database và đúng phiên bản thư viện đang triển khai. <Link url="https://docs.spring.io/spring-session/reference/configuration/jdbc.html" title="Tài liệu Spring Session JDBC" />

### 1.2. Ý nghĩa của từng khóa

| Cột hoặc chỉ mục | Vai trò | Truy vấn được hỗ trợ |
|---|---|---|
| `PRIMARY_ID` — khóa chính | Định danh nội bộ của hàng session trong cơ sở dữ liệu | Join tới bảng thuộc tính và thao tác nội bộ |
| `SESSION_ID` — unique index | ID phiên được client gửi qua cookie hoặc header | Tìm một session theo ID |
| `EXPIRY_TIME` — index | Thời điểm hết hạn được tính từ lần truy cập cuối và timeout | Tìm/xóa các phiên đã hết hạn |
| `PRINCIPAL_NAME` — index | Tên principal được liên kết với phiên | Liệt kê các session của một người dùng |
| `SESSION_PRIMARY_ID` trong bảng attributes | Liên kết thuộc tính với hàng session | Đọc/xóa thuộc tính theo phiên |
| `(SESSION_PRIMARY_ID, ATTRIBUTE_NAME)` — khóa chính bảng attributes | Mỗi tên thuộc tính chỉ có một giá trị trong một session | Tìm hoặc cập nhật một thuộc tính |

`PRIMARY_ID` và `SESSION_ID` có mục đích khác nhau. `PRIMARY_ID` là khóa nội bộ, ổn định để liên kết hai bảng. `SESSION_ID` là định danh phiên mà Spring Session trao đổi với client. Không dùng `PRIMARY_ID` làm cookie session ID và không tự sửa `SESSION_ID` trực tiếp trong database.

`SPRING_SESSION_IX1` là unique index vì hai hàng không được có cùng `SESSION_ID`. Hai chỉ mục `EXPIRY_TIME` và `PRINCIPAL_NAME` là index thường vì nhiều phiên có thể cùng hết hạn tại một thời điểm hoặc thuộc về cùng một người dùng.

## 2. Chỉ mục `EXPIRY_TIME` và vòng đời phiên

### 2.1. Tính thời điểm hết hạn

Session có hai giá trị chính để xác định thời hạn không hoạt động:

- `LAST_ACCESS_TIME`: lần truy cập cuối được ghi nhận, lưu dưới dạng epoch milliseconds.
- `MAX_INACTIVE_INTERVAL`: khoảng không hoạt động tối đa, lưu theo giây.

Spring Session tính `EXPIRY_TIME` theo thời điểm truy cập cuối cộng với khoảng không hoạt động tối đa:

\[
T_{expiry}=T_{lastAccess}+I_{maxInactive}
\]

`EXPIRY_TIME` được lưu dưới dạng epoch milliseconds. Vì vậy, `MAX_INACTIVE_INTERVAL` và `EXPIRY_TIME` không cùng đơn vị. Khi viết SQL hoặc công cụ chẩn đoán, không cộng trực tiếp số giây vào một timestamp milliseconds.

Ví dụ: nếu lần truy cập cuối là 10:00 và timeout là 30 phút, hạn logic của session là 10:30. Một request hợp lệ tiếp tục dùng session trước hạn sẽ làm mới `LAST_ACCESS_TIME`, từ đó repository tính lại `EXPIRY_TIME` khi lưu session.

Nếu `MAX_INACTIVE_INTERVAL` âm, session được cấu hình không hết hạn theo inactivity timeout. Trong implementation JDBC, `EXPIRY_TIME` của trường hợp này được đặt ở một mốc rất xa trong tương lai để không bị tác vụ dọn thông thường xóa như một session hết hạn.

### 2.2. Vì sao cần index trên `EXPIRY_TIME`?

Spring Session JDBC chạy câu lệnh dọn phiên hết hạn có dạng:

```sql
DELETE FROM SPRING_SESSION
WHERE EXPIRY_TIME < ?;
```

Điều kiện là một phép so sánh theo khoảng (`<`) trên `EXPIRY_TIME`. Index `SPRING_SESSION_IX2` giúp database tìm các hàng đến hạn mà không phải quét toàn bộ bảng trong những trường hợp query planner có thể sử dụng index. Khi xóa hàng cha, khóa ngoại `ON DELETE CASCADE` giúp xóa các thuộc tính tương ứng trong `SPRING_SESSION_ATTRIBUTES`.

Nếu thiếu index này, tác vụ dọn dẹp có thể phải quét nhiều hàng khi bảng session lớn. Hệ quả là tăng I/O, thời gian giữ lock và tải database, đặc biệt khi có nhiều instance cùng sử dụng repository.

### 2.3. Hết hạn logic và dọn dữ liệu vật lý là hai bước

Không nên đồng nhất việc session không còn hợp lệ với việc hàng database đã bị xóa:

1. Khi `EXPIRY_TIME` đã qua, session không còn hợp lệ theo inactivity timeout.
2. `JdbcIndexedSessionRepository.findById(sessionId)` đọc session và kiểm tra `isExpired()`. Nếu session đã hết hạn, repository xóa nó và trả về `null`.
3. Tác vụ cleanup định kỳ xóa những hàng có `EXPIRY_TIME` nhỏ hơn thời điểm hiện tại, kể cả các phiên không còn được request truy cập.

Vì cleanup chạy theo lịch, một hàng đã hết hạn có thể vẫn tồn tại trong database cho đến lần chạy dọn tiếp theo. Điều đó không có nghĩa request mang session ID cũ được phép sử dụng phiên: `findById` vẫn kiểm tra hết hạn logic.

### 2.4. Lịch dọn phiên mặc định

`JdbcIndexedSessionRepository` mặc định chạy cleanup mỗi phút. Có thể thay lịch bằng thuộc tính `cleanupCron` của `@EnableJdbcHttpSession`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession(cleanupCron = "0 */5 * * * *")
public class JdbcSessionConfiguration {
}
```

Ví dụ này chạy cleanup mỗi 5 phút. Nếu dùng Spring Boot, có thể cấu hình:

```yaml
spring:
  session:
    jdbc:
      cleanup-cron: "0 */5 * * * *"
```

Có thể tắt lịch mặc định bằng `Scheduled.CRON_DISABLED` nếu hệ thống có job cleanup riêng:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession(cleanupCron = Scheduled.CRON_DISABLED)
public class JdbcSessionConfiguration {
}
```

Chỉ tắt cleanup mặc định khi đã có cơ chế thay thế được giám sát. Nếu không có job thay thế, hàng hết hạn và các thuộc tính liên quan sẽ tích tụ. Tài liệu Spring Session cũng lưu ý job mặc định được thiết kế đơn giản; nếu cần batch processing phức tạp, có thể dùng một giải pháp như Spring Batch. <Link url="https://docs.spring.io/spring-session/reference/configuration/jdbc.html" title="Tùy chỉnh expired sessions cleanup" />

## 3. Chỉ mục `PRINCIPAL_NAME`

### 3.1. Principal là gì trong session?

Principal là danh tính mà ứng dụng đã xác thực, thường là username hoặc một định danh tài khoản ổn định. Một người dùng có thể có nhiều phiên cùng lúc, ví dụ đăng nhập trên laptop, điện thoại và trình duyệt khác.

Spring Session định nghĩa interface `FindByIndexNameSessionRepository<S extends Session>` để tìm các phiên theo tên chỉ mục và giá trị chỉ mục. Use case phổ biến là tra cứu mọi phiên của một principal bằng hằng số:

```java
FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME
```

`JdbcIndexedSessionRepository` triển khai interface này và lưu giá trị principal trong cột `PRINCIPAL_NAME`. Index `SPRING_SESSION_IX3` giúp truy vấn theo tên principal hiệu quả hơn khi có nhiều phiên.

### 3.2. Principal được đưa vào chỉ mục như thế nào?

Spring Session không tự biết mọi cơ chế xác thực của ứng dụng. Principal phải được suy ra từ dữ liệu có trong session. `PrincipalNameIndexResolver` mặc định có thể lấy tên principal từ:

- Thuộc tính session có tên `FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME`.
- `SecurityContext` của Spring Security được lưu trong session dưới thuộc tính `SPRING_SECURITY_CONTEXT`.

Với ứng dụng Spring Security thông thường, resolver có thể đọc principal từ `SecurityContext` được lưu trong session. Nếu dùng cơ chế xác thực tùy chỉnh, hoặc không lưu `SecurityContext` vào session, ứng dụng cần tự đặt thuộc tính principal.

Ví dụ trong Servlet controller sau khi đã xác thực:

```java
import org.springframework.security.core.Authentication;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import jakarta.servlet.http.HttpSession;

@RestController
public class LoginSessionController {

    @PostMapping("/login/session-index")
    public void addPrincipalIndex(HttpSession session, Authentication authentication) {
        session.setAttribute(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            authentication.getName()
        );
    }
}
```

Đây là ví dụ cho trường hợp ứng dụng cần ghi principal rõ ràng. Nếu Spring Security đã lưu `SecurityContext` và resolver đang đọc được principal từ đó, không cần đặt thêm cùng một thuộc tính chỉ để tạo index.

Khi chọn giá trị principal, nên dùng một định danh ổn định, nhất quán giữa các instance. Tránh dùng display name có thể thay đổi. Nếu username không phân biệt hoa thường ở tầng nghiệp vụ, hãy chuẩn hóa giá trị trước khi lưu và truy vấn; kết quả so sánh cũng chịu ảnh hưởng collation của database.

### 3.3. Dữ liệu principal được ghi vào cột nào?

Khi repository lưu hoặc cập nhật session, `IndexResolver` xác định giá trị principal. `JdbcIndexedSessionRepository` ghi giá trị đó vào cột `PRINCIPAL_NAME` của bảng session. Nhờ vậy, truy vấn principal không cần giải mã tất cả thuộc tính nhị phân trong bảng attributes để tìm username.

Nếu principal không thể được xác định, cột `PRINCIPAL_NAME` có thể là `NULL`. Khi đó, `findByPrincipalName(username)` không tìm được phiên ấy, dù session vẫn tồn tại và client vẫn có thể dùng session ID để truy cập. Vì thế, “không có kết quả trong principal lookup” không đồng nghĩa “người dùng không còn session”. Cần kiểm tra quá trình ghi principal và cấu hình resolver.

## 4. Tra cứu phiên theo principal

### 4.1. API `findByPrincipalName`

`FindByIndexNameSessionRepository` cung cấp hai phương thức:

```java
Map<String, S> findByIndexNameAndIndexValue(String indexName, String indexValue);

Map<String, S> findByPrincipalName(String principalName);
```

`findByPrincipalName` là phương thức tiện ích dùng chỉ mục `PRINCIPAL_NAME_INDEX_NAME`. Kết quả là một `Map` trong đó:

- Key là session ID.
- Value là đối tượng `Session` tương ứng.

Nếu không tìm thấy phiên, API trả về map rỗng, không phải `null`.

Ví dụ dùng repository:

```java
import java.util.Map;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class UserSessionQueryService {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public UserSessionQueryService(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public Map<String, ? extends Session> findSessions(String username) {
        return this.sessions.findByPrincipalName(username);
    }
}
```

Ví dụ giả định Spring context chỉ có một repository triển khai interface này cho Servlet session. Nếu ứng dụng có nhiều repository hoặc nhiều loại session, cần cấu hình injection rõ ràng bằng qualifier.

### 4.2. Tra cứu bằng tên index và giá trị

Có thể gọi trực tiếp phương thức tổng quát:

```java
Map<String, ? extends Session> sessions = repository.findByIndexNameAndIndexValue(
    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
    "alice"
);
```

Với `JdbcIndexedSessionRepository`, implementation mặc định hỗ trợ chỉ mục principal này. Nếu truyền một `indexName` khác, implementation JDBC trả về map rỗng. Không nên hiểu rằng interface tổng quát đồng nghĩa mọi repository đều hỗ trợ mọi loại index tùy ý.

Nếu cần tìm theo tenant, loại thiết bị hoặc một thuộc tính nghiệp vụ khác, cần thiết kế schema và câu truy vấn bổ sung hoặc xây dựng repository/query riêng. Chỉ đặt thêm một thuộc tính session không tự động tạo cột và index SQL tương ứng.

### 4.3. Tra cứu nhiều session để quản lý đăng nhập đồng thời

Một use case phổ biến là giới hạn số phiên của một tài khoản hoặc cho phép quản trị viên xem các thiết bị đang đăng nhập. Ví dụ:

```java
Map<String, ? extends Session> sessions = repository.findByPrincipalName("alice");

sessions.forEach((sessionId, session) -> {
    System.out.println("Session ID: " + sessionId);
    System.out.println("Created at: " + session.getCreationTime());
    System.out.println("Last accessed: " + session.getLastAccessedTime());
});
```

Không gửi session ID thô ra giao diện quản trị hoặc log nếu không cần thiết. Thay vào đó, tạo một mã tham chiếu an toàn và chỉ hiển thị các thông tin đã được chọn, ví dụ thời điểm đăng nhập, lần hoạt động cuối hoặc nhãn thiết bị do ứng dụng lưu riêng.

## 5. Xử lý phiên hết hạn trong kết quả principal lookup

### 5.1. Cleanup chạy định kỳ

Job cleanup mặc định chạy mỗi phút, nên giữa hai lần chạy có thể tồn tại hàng đã hết hạn trong bảng. Câu query mặc định của `findByPrincipalName` lọc theo `PRINCIPAL_NAME`; nó không tự thêm điều kiện `EXPIRY_TIME` vào truy vấn danh sách. Vì vậy, trong một khoảng thời gian trước khi cleanup chạy, kết quả principal lookup có thể chứa hàng đã đến hạn logic nhưng chưa bị xóa vật lý.

Đối với thao tác cần danh sách phiên đang hoạt động chính xác, không nên chỉ dựa vào việc hàng xuất hiện trong kết quả principal lookup. Có thể kiểm tra `Session.isExpired()` hoặc xác minh lại bằng `findById(sessionId)`. `findById` kiểm tra timeout và xóa phiên nếu phát hiện đã hết hạn.

Ví dụ lọc lại kết quả:

```java
Map<String, ? extends Session> candidates = repository.findByPrincipalName(username);

for (String sessionId : candidates.keySet()) {
    Session activeSession = repository.findById(sessionId);
    if (activeSession != null) {
        // Chỉ xử lý phiên còn hợp lệ.
    }
}
```

Việc gọi `findById` từng ID tạo thêm truy vấn database. Nếu danh sách có thể lớn, hãy cân nhắc truy vấn chuyên biệt có điều kiện expiry, job cleanup có tần suất phù hợp hoặc một dịch vụ quản lý session được thiết kế cho tải đó. Khi tùy chỉnh query, phải giữ đúng ngữ nghĩa của repository và kiểm thử trên hệ quản trị cơ sở dữ liệu thực tế.

### 5.2. JDBC không phát session lifecycle events

`JdbcIndexedSessionRepository` không hỗ trợ publish session events như `SessionDeletedEvent` hoặc `SessionExpiredEvent`. Nếu ứng dụng cần audit hoặc đồng bộ tài nguyên khi session bị hủy, không thể mặc định chờ một Spring Session event từ repository JDBC.

Có thể xây dựng cơ chế nghiệp vụ riêng khi ứng dụng chủ động đăng xuất hoặc thu hồi phiên, ví dụ ghi một bản ghi audit trong cùng luồng thao tác. Với timeout, cleanup job có thể được mở rộng hoặc thay thế bằng job riêng có ghi nhận kết quả. Cần phân biệt rõ thao tác invalidate trực tiếp, timeout logic và cleanup vật lý.

## 6. Tìm kiếm, buộc đăng xuất và giới hạn phiên

### 6.1. Buộc đăng xuất các phiên của một principal

Ứng dụng có thể tra cứu các phiên của người dùng rồi xóa từng phiên theo session ID:

```java
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class RemoteSessionRevocationService {

    private final FindByIndexNameSessionRepository<? extends Session> repository;

    public RemoteSessionRevocationService(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        this.repository = repository;
    }

    public void revokeAll(String principalName) {
        var sessions = this.repository.findByPrincipalName(principalName);
        for (String sessionId : sessions.keySet()) {
            this.repository.deleteById(sessionId);
        }
    }
}
```

Khi xóa phiên trong repository dùng chung, các instance ứng dụng sẽ không thể nạp lại phiên bằng session ID cũ. Cookie ở trình duyệt từ xa có thể vẫn còn cho đến khi hết hạn hoặc bị xóa ở client, nhưng ID cũ không còn khôi phục được session đã bị xóa.

Đây là thao tác nhạy cảm. Endpoint thực hiện remote logout cần yêu cầu quyền quản trị phù hợp, xác minh principal mục tiêu và ghi audit. Không cho phép người dùng tự truyền một username bất kỳ để xóa session của tài khoản khác.

### 6.2. Giới hạn số phiên đồng thời

Principal index có thể là đầu vào cho chính sách giới hạn phiên:

1. Người dùng đăng nhập thành công.
2. Ứng dụng tìm các phiên hiện có theo principal.
3. So sánh số phiên với giới hạn đã định.
4. Nếu vượt giới hạn, áp dụng chính sách như từ chối đăng nhập mới hoặc thu hồi phiên cũ.

Nếu nhiều request đăng nhập đồng thời, hai request có thể cùng đọc số phiên trước khi phiên mới được lưu. Chỉ dùng `findByPrincipalName` rồi đếm không tạo ra tính nguyên tử cho quy tắc giới hạn. Nếu giới hạn là yêu cầu bắt buộc, cần thêm cơ chế phối hợp ở database, ví dụ transaction/lock hoặc bảng quản lý đăng nhập có khóa theo principal, và kiểm thử cạnh tranh nhiều instance.

### 6.3. Dữ liệu principal phải nhất quán

Các instance phải dùng cùng quy tắc xác định principal. Nếu instance A lưu `alice@example.com` còn instance B truy vấn `alice`, hai giá trị sẽ không khớp dù cùng người dùng. Hãy thống nhất canonical principal name, quy tắc hoa thường và cách xử lý khi username đổi.

Nếu principal thay đổi trong session, repository phải lưu thay đổi để cập nhật cột `PRINCIPAL_NAME`. Với `FlushMode.ON_SAVE`, thay đổi thường được ghi khi session được lưu ở cuối request. Không truy vấn principal index ngay trong cùng luồng trước khi thay đổi đã được flush và kỳ vọng database đã phản ánh giá trị mới.

## 7. Tối ưu và kiểm tra kế hoạch truy vấn

### 7.1. Ba truy vấn chính và index tương ứng

| Tác vụ | Điều kiện SQL cốt lõi | Index cần có |
|---|---|---|
| Nạp session theo cookie/header ID | `SESSION_ID = ?` | Unique index `SPRING_SESSION_IX1` |
| Dọn session hết hạn | `EXPIRY_TIME < ?` | `SPRING_SESSION_IX2` |
| Liệt kê session theo principal | `PRINCIPAL_NAME = ?` | `SPRING_SESSION_IX3` |
| Join thuộc tính session | `PRIMARY_ID = SESSION_PRIMARY_ID` | PK bảng session và index/PK trên `SESSION_PRIMARY_ID` |

Khi database có nhiều dữ liệu, dùng `EXPLAIN` hoặc công cụ tương đương để xác minh query planner có sử dụng index phù hợp. Với PostgreSQL, có thể dùng `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường staging hoặc bản sao dữ liệu có quy mô tương đương production. Không chạy truy vấn phân tích nặng tùy tiện trên database production đang chịu tải.

### 7.2. Index có chi phí ghi

Mỗi index giúp tăng tốc một nhóm truy vấn nhưng làm tăng chi phí khi insert, update và delete. Spring Session cập nhật `EXPIRY_TIME` khi session được lưu và cập nhật `PRINCIPAL_NAME` khi giá trị principal thay đổi. Database phải cập nhật các index tương ứng.

Không nên thêm nhiều index dựa trên phỏng đoán. Bắt đầu với các index chuẩn của Spring Session, đo query thực tế và chỉ bổ sung index khi có workload cụ thể. Index dư thừa làm tăng dung lượng, chi phí ghi và thời gian bảo trì.

### 7.3. Kích thước và collation của `PRINCIPAL_NAME`

Schema mẫu dùng `VARCHAR(100)` cho `PRINCIPAL_NAME`. Nếu ứng dụng có principal dài hơn, cần điều chỉnh DDL và migration tương ứng trước khi lưu dữ liệu. Cũng cần hiểu collation của database: một số cấu hình so sánh chuỗi không phân biệt hoa thường, số khác phân biệt. Kết quả truy vấn principal phải phù hợp với quy tắc định danh của hệ thống.

Không dùng giá trị principal có dữ liệu nhạy cảm không cần thiết. Cột này được lưu dạng văn bản và được dùng để truy vấn; quyền truy cập database và log truy vấn cần được giới hạn tương ứng.

## 8. Tùy chỉnh bảng và câu truy vấn

### 8.1. Đổi tên bảng

Nếu ứng dụng muốn dùng tên bảng riêng, có thể cấu hình `tableName`:

```java
@Configuration
@EnableJdbcHttpSession(tableName = "APP_SESSION")
public class JdbcSessionConfiguration {
}
```

Khi đó, bảng thuộc tính mặc định có tên `APP_SESSION_ATTRIBUTES`. Schema migration phải tạo đúng cả hai bảng, các khóa ngoại và các index cần thiết. Tên bảng trong câu SQL và tên index trong script phải khớp cấu hình repository.

### 8.2. Tùy chỉnh query principal hoặc expiry

`JdbcIndexedSessionRepository` cung cấp các setter để tùy chỉnh câu SQL như `setListSessionsByPrincipalNameQuery` và `setDeleteSessionsByExpiryTimeQuery`. Có thể áp dụng qua `SessionRepositoryCustomizer<JdbcIndexedSessionRepository>` khi database cần cú pháp riêng hoặc ứng dụng có thêm điều kiện lọc.

Ví dụ minh họa thay query cleanup để chỉ xóa hàng của một tenant:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.session.config.SessionRepositoryCustomizer;
import org.springframework.session.jdbc.JdbcIndexedSessionRepository;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession
public class JdbcSessionQueryConfiguration {

    @Bean
    SessionRepositoryCustomizer<JdbcIndexedSessionRepository> sessionQueryCustomizer() {
        return repository -> repository.setDeleteSessionsByExpiryTimeQuery("""
            DELETE FROM %TABLE_NAME%
            WHERE EXPIRY_TIME < ?
              AND TENANT_ID = 'portal'
            """);
    }
}
```

Đây chỉ là ví dụ nếu schema thực tế có cột `TENANT_ID` và các query tạo/cập nhật session cũng ghi cột đó. Không thêm điều kiện theo cột chưa tồn tại hoặc chỉ thay query cleanup mà quên giữ tính nhất quán của các thao tác còn lại. Placeholder `%TABLE_NAME%` được repository thay bằng tên bảng đã cấu hình.

Khi tùy chỉnh query principal, phải giữ đúng thứ tự tham số, các cột cần hydrate session và điều kiện hết hạn nếu nghiệp vụ yêu cầu. Kiểm thử với database vendor thật, vì cú pháp và cách tối ưu index khác nhau giữa PostgreSQL, MySQL, SQL Server, Oracle và các hệ quản trị khác.

### 8.3. Index tùy chỉnh không tự xuất hiện từ `IndexResolver`

`IndexResolver` quyết định giá trị index mà repository trích xuất từ session. Tuy nhiên, schema JDBC mặc định chỉ có cột `PRINCIPAL_NAME` và query tích hợp chỉ hỗ trợ `PRINCIPAL_NAME_INDEX_NAME`. Đổi resolver không tự tạo thêm cột, index hoặc câu truy vấn cho tenant, thiết bị hay thuộc tính khác.

Nếu cần các index bổ sung, phải thiết kế bảng index riêng hoặc mở rộng schema/query một cách nhất quán. Cần xác định cách thêm, cập nhật và xóa index khi session thay đổi principal, đổi ID, hết hạn hoặc bị invalidate. Nếu không, chỉ mục phụ có thể trỏ tới session không còn tồn tại.

## 9. Kiểm thử chỉ mục và tra cứu phiên

### 9.1. Kiểm thử principal lookup

Một integration test có thể xác minh session được lưu và tìm lại theo principal:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.jdbc.JdbcIndexedSessionRepository;

@SpringBootTest
class JdbcSessionPrincipalIndexTest {

    @Autowired
    JdbcIndexedSessionRepository repository;

    @Test
    void findsSessionByPrincipalName() {
        var session = this.repository.createSession();
        session.setAttribute(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            "alice"
        );
        this.repository.save(session);

        var sessions = this.repository.findByPrincipalName("alice");

        assertThat(sessions).containsKey(session.getId());
    }
}
```

Test này cần database đã khởi tạo schema Spring Session đúng vendor. Nếu ứng dụng dùng Spring Security context thay vì đặt thuộc tính principal thủ công, nên có thêm test đi qua login flow để xác minh `SecurityContext` được lưu và resolver trích xuất đúng principal.

### 9.2. Kiểm thử session ID và expiry

Kiểm thử cần bao gồm:

1. Tạo session và xác minh `findById(sessionId)` trả về session.
2. Kiểm tra hàng tương ứng có `SESSION_ID` duy nhất và `EXPIRY_TIME` đúng đơn vị milliseconds.
3. Đặt timeout ngắn, để session hết hạn và xác minh `findById` trả `null`.
4. Chạy `cleanUpExpiredSessions()` hoặc chờ cron cleanup, rồi xác minh hàng session và attributes đã bị xóa.
5. Kiểm tra index `EXPIRY_TIME` được dùng bởi query cleanup trên database test có dữ liệu đủ lớn.

Không chỉ kiểm tra hàng bị xóa. Cần xác minh request tiếp theo mang session ID cũ không còn được xác thực. Ngược lại, không kết luận cleanup bị lỗi chỉ vì một hàng hết hạn vẫn tồn tại trong khoảng thời gian trước lần chạy cron kế tiếp.

### 9.3. Kiểm thử nhiều phiên và nhiều instance

Tạo nhiều session cho cùng một principal từ hai instance ứng dụng cùng dùng database. `findByPrincipalName` phải tìm được các session đã được lưu bởi cả hai instance. Kiểm tra thêm:

- Principal được lưu nhất quán trên mọi instance.
- Session bị xóa ở instance A không còn được `findById` tìm thấy ở instance B.
- Timeout và cleanup sử dụng cùng timezone/clock và cùng schema.
- Các instance không dùng khác table name hoặc khác phiên bản schema.
- Cleanup job không gây tải truy vấn quá mức khi nhiều instance cùng chạy.

## 10. Vận hành và xử lý sự cố

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Session lookup theo ID chậm | Thiếu unique index trên `SESSION_ID` hoặc query plan không dùng index | Kiểm tra DDL và `EXPLAIN` query theo session ID |
| Cleanup làm database tải cao | Thiếu index `EXPIRY_TIME`, bảng có nhiều hàng hết hạn hoặc cron chạy quá thường xuyên | Kiểm tra query plan, thời gian cleanup, số hàng xóa và cron |
| Hàng hết hạn còn tồn tại | Cleanup chưa tới lịch, bị tắt hoặc lỗi quyền/xung đột database | Kiểm tra `cleanupCron`, log và gọi cleanup trong môi trường test |
| Principal lookup luôn rỗng | Cột `PRINCIPAL_NAME` không được điền hoặc giá trị truy vấn không khớp | Kiểm tra resolver, `SPRING_SECURITY_CONTEXT`, attribute principal và collation |
| Principal lookup chậm | Thiếu index `PRINCIPAL_NAME` hoặc query join attributes tốn kém | Kiểm tra DDL, `EXPLAIN` và số lượng attributes/session |
| Principal lookup trả session đã hết hạn | Hàng đã đến hạn nhưng cleanup chưa xóa; query theo principal chưa lọc expiry | Kiểm tra `Session.isExpired()` hoặc xác minh lại bằng `findById` |
| Session attributes bị mồ côi | Thiếu foreign key `ON DELETE CASCADE` hoặc schema tự tạo không theo script | Kiểm tra FK và dọn dữ liệu tồn đọng bằng migration có kiểm soát |
| Lỗi sau khi đổi table name | Bảng hoặc index vẫn mang tên cũ | Đối chiếu `tableName`, tên bảng attributes, FK và toàn bộ index |
| Nhiều instance cùng chạy cleanup | Mỗi repository instance tạo lịch cleanup riêng | Theo dõi query trùng lặp; cân nhắc điều phối một job tập trung nếu tải lớn |

Với nhiều instance, mọi node cần dùng cùng schema, table name, index và cách chuẩn hóa principal. `JdbcIndexedSessionRepository` thực hiện các thao tác JDBC trong transaction; mặc định dùng propagation `REQUIRES_NEW` để tránh bị ảnh hưởng bởi transaction read-only đang tồn tại. Nếu ứng dụng có nhiều `DataSource` hoặc `TransactionManager`, cần cấu hình Spring Session JDBC dùng đúng bean tương ứng. <Link url="https://docs.spring.io/spring-session/reference/configuration/jdbc.html" title="Transaction và DataSource cho Spring Session JDBC" />

## 11. Quy trình thiết kế và kiểm chứng

Khi triển khai chỉ mục và tra cứu phiên bằng JDBC, hãy đi theo trình tự:

1. Dùng schema SQL đúng database vendor và kiểm tra các cột, khóa ngoại cùng index mặc định.
2. Xác minh unique index trên `SESSION_ID`, index trên `EXPIRY_TIME` và `PRINCIPAL_NAME`.
3. Xác minh `EXPIRY_TIME` được tính từ `LAST_ACCESS_TIME` và `MAX_INACTIVE_INTERVAL` với đúng đơn vị.
4. Xác định `IndexResolver` đang dùng và bảo đảm principal được ghi vào session.
5. Dùng `findByPrincipalName` để tra cứu phiên; hiểu rằng JDBC mặc định hỗ trợ chỉ mục principal tích hợp.
6. Kiểm tra hết hạn logic bằng `findById` và dọn dữ liệu vật lý bằng cleanup job.
7. Đo query plan bằng `EXPLAIN`, theo dõi số hàng hết hạn và thời gian cleanup.
8. Kiểm thử đăng xuất từ xa, giới hạn session đồng thời và request từ nhiều instance.
9. Nếu tùy chỉnh schema hoặc SQL, cập nhật đồng bộ mọi query tạo, cập nhật, đọc, xóa và cleanup.

Các index `SESSION_ID`, `EXPIRY_TIME` và `PRINCIPAL_NAME` phục vụ ba thao tác khác nhau: nạp một phiên, dọn phiên hết hạn và liệt kê phiên của một principal. `JdbcIndexedSessionRepository` kết hợp các index này với `FindByIndexNameSessionRepository` để hỗ trợ quản lý session trên nhiều instance. Khi schema, principal resolver và cleanup job được cấu hình nhất quán, việc tra cứu và thu hồi phiên có thể mở rộng theo dữ liệu; nếu bỏ sót index hoặc không ghi principal, API tra cứu vẫn có thể chạy nhưng hiệu năng hoặc kết quả sẽ không đáp ứng mong đợi.

## Tài liệu tham khảo

- [Spring Session JDBC — schema, indexes và cleanup](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Session API — FindByIndexNameSessionRepository](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html)
- [Spring Session API — PrincipalNameIndexResolver](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/PrincipalNameIndexResolver.html)
- [Spring Session API — JdbcIndexedSessionRepository](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/jdbc/JdbcIndexedSessionRepository.html)
- [JdbcIndexedSessionRepository source — default queries and index resolution](https://github.com/spring-projects/spring-session/blob/main/spring-session-jdbc/src/main/java/org/springframework/session/jdbc/JdbcIndexedSessionRepository.java)
