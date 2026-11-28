# FindByIndexNameSessionRepository và tra cứu phiên qua chỉ mục

Trong ứng dụng dùng Spring Session, dữ liệu phiên được lưu trong repository dùng chung như Redis hoặc JDBC. Khi cần liệt kê các phiên của một người dùng, cách đơn giản nhưng kém hiệu quả là tìm mọi phiên rồi đọc từng thuộc tính để so sánh tên người dùng. `FindByIndexNameSessionRepository` cung cấp một hợp đồng tra cứu theo chỉ mục để repository tìm trực tiếp những phiên có cùng giá trị chỉ mục.

Khả năng này hữu ích cho màn hình quản trị phiên, chức năng đăng xuất khỏi các thiết bị khác, giới hạn số phiên đăng nhập đồng thời và điều tra các phiên của một tài khoản. Nó cũng phù hợp với kiến trúc nhiều instance: ứng dụng có thể truy vấn kho dữ liệu phiên dùng chung thay vì chỉ nhìn thấy các phiên nằm trong bộ nhớ của một máy chủ.

## 1. Vai trò của FindByIndexNameSessionRepository

`SessionRepository` định nghĩa các thao tác cơ bản như tạo, lưu, tìm theo session ID và xóa phiên. `FindByIndexNameSessionRepository<S extends Session>` mở rộng hợp đồng đó bằng khả năng tìm một nhóm phiên theo tên chỉ mục và giá trị chỉ mục.

Hai phương thức quan trọng của interface là:

```java
public interface FindByIndexNameSessionRepository<S extends Session>
        extends SessionRepository<S> {

    String PRINCIPAL_NAME_INDEX_NAME =
            FindByIndexNameSessionRepository.class.getName() + ".PRINCIPAL_NAME";

    Map<String, S> findByIndexNameAndIndexValue(
            String indexName, String indexValue);

    default Map<String, S> findByPrincipalName(String principalName) {
        return findByIndexNameAndIndexValue(
                PRINCIPAL_NAME_INDEX_NAME, principalName);
    }
}
```

Đoạn mã trên minh họa hợp đồng API. `findByPrincipalName` là phương thức tiện ích dùng chỉ mục chuẩn `PRINCIPAL_NAME_INDEX_NAME`; còn `findByIndexNameAndIndexValue` cho phép truy vấn một chỉ mục khác nếu repository đã được cấu hình để tạo và duy trì chỉ mục đó.

Kết quả là một `Map` trong đó:

- Key là session ID.
- Value là đối tượng `Session` chứa metadata và các thuộc tính của phiên.
- Map rỗng nếu không có phiên nào khớp; API không trả về `null`.

Một người dùng đăng nhập trên trình duyệt máy tính, điện thoại và một trình duyệt khác có thể có nhiều phiên cùng principal name. Vì vậy, kết quả là một tập phiên, không phải một phiên duy nhất. `FindByIndexNameSessionRepository` chỉ có ở các repository hỗ trợ tra cứu theo chỉ mục; một bean chỉ triển khai `SessionRepository` cơ bản không cung cấp hợp đồng này.

## 2. Chỉ mục principal name

Chỉ mục được dùng phổ biến nhất là `FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME`. Giá trị của nó là tên principal gắn với phiên, thường là username hoặc một định danh ổn định của tài khoản.

Spring Session không tự biết mọi cơ chế xác thực mà ứng dụng có thể sử dụng. Vì vậy, ứng dụng phải bảo đảm principal name được đưa vào chỉ mục. `PrincipalNameIndexResolver` là bộ phân giải có sẵn: nó đọc giá trị từ thuộc tính phiên có tên `PRINCIPAL_NAME_INDEX_NAME` hoặc lấy principal từ thuộc tính Spring Security context được lưu trong phiên dưới tên `SPRING_SECURITY_CONTEXT`.

Với luồng Spring Security tiêu chuẩn, `Authentication` được lưu trong `SecurityContext`, và resolver có thể lấy tên principal từ context này. Trong một cơ chế xác thực riêng, hoặc khi ứng dụng lưu principal theo cách khác, hãy ghi chỉ mục một cách rõ ràng sau khi xác thực thành công:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.session.FindByIndexNameSessionRepository;

void recordPrincipalIndex(
        HttpServletRequest request, String canonicalPrincipalName) {
    request.getSession().setAttribute(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            canonicalPrincipalName);
}
```

`canonicalPrincipalName` phải là cùng một giá trị mà ứng dụng sẽ dùng khi truy vấn. Ví dụ, nếu username không phân biệt chữ hoa chữ thường, hãy chuẩn hóa nó nhất quán khi ghi và khi tìm. Một mã tài khoản nội bộ ổn định thường phù hợp hơn email nếu email có thể thay đổi.

Không ghi principal index trước khi xác thực thành công. Không dùng giá trị do client tự gửi mà chưa được máy chủ xác minh. Nếu session ID được thay đổi trong luồng đăng nhập để chống session fixation, hãy bảo đảm thông tin principal vẫn được lưu trên phiên sau xác thực và được repository lập chỉ mục khi lưu phiên.

## 3. Tra cứu phiên theo principal name

Ứng dụng thường inject interface `FindByIndexNameSessionRepository` thay vì phụ thuộc trực tiếp vào lớp Redis hoặc JDBC. Nhờ đó, service nghiệp vụ không cần biết cấu trúc key Redis hay câu SQL của repository.

Ví dụ dưới đây lấy metadata của các phiên thuộc một principal. Service chỉ trả về thông tin cần thiết cho phần quản trị nội bộ, không trả về toàn bộ session attributes vì chúng có thể chứa dữ liệu xác thực hoặc dữ liệu riêng tư.

```java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class PrincipalSessionService {

    private final FindByIndexNameSessionRepository<? extends Session> repository;

    public PrincipalSessionService(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        this.repository = repository;
    }

    public List<SessionSummary> findSessions(String principalName) {
        if (principalName == null || principalName.isBlank()) {
            throw new IllegalArgumentException("principalName is required");
        }

        Map<String, ? extends Session> sessions =
                repository.findByPrincipalName(principalName);

        return sessions.entrySet().stream()
                .map(entry -> {
                    Session session = entry.getValue();
                    return new SessionSummary(
                            entry.getKey(),
                            session.getCreationTime(),
                            session.getLastAccessedTime(),
                            session.getMaxInactiveInterval());
                })
                .collect(Collectors.toList());
    }

    public static class SessionSummary {
        private final String sessionId;
        private final Instant createdAt;
        private final Instant lastAccessedAt;
        private final Duration maxInactiveInterval;

        public SessionSummary(String sessionId, Instant createdAt,
                Instant lastAccessedAt, Duration maxInactiveInterval) {
            this.sessionId = sessionId;
            this.createdAt = createdAt;
            this.lastAccessedAt = lastAccessedAt;
            this.maxInactiveInterval = maxInactiveInterval;
        }

        public String getSessionId() { return sessionId; }
        public Instant getCreatedAt() { return createdAt; }
        public Instant getLastAccessedAt() { return lastAccessedAt; }
        public Duration getMaxInactiveInterval() { return maxInactiveInterval; }
    }
}
```

Trong ví dụ, `Session` cung cấp `Instant` cho thời điểm tạo và truy cập cuối, cùng `Duration` cho khoảng không hoạt động tối đa. Session ID được dùng làm khóa của kết quả; hãy cân nhắc chỉ hiển thị một phần ID hoặc một mã thay thế trong giao diện quản trị. Không đưa session ID vào URL hay log công khai.

Nếu cần gọi API chỉ mục tổng quát, có thể viết tương đương:

```java
Map<String, ? extends Session> sessions =
        repository.findByIndexNameAndIndexValue(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                principalName);
```

Phương thức `findByPrincipalName` thường dễ đọc hơn khi tra cứu tài khoản. Phương thức tổng quát hữu ích khi ứng dụng có thêm chỉ mục nghiệp vụ đã được cấu hình trong repository.

## 4. Chỉ mục tùy chỉnh

`findByIndexNameAndIndexValue` không tự động quét mọi thuộc tính của phiên. Một chỉ mục chỉ có tác dụng khi repository có thể suy ra và duy trì giá trị chỉ mục đó. Với chỉ mục principal chuẩn, Spring Session cung cấp `PrincipalNameIndexResolver`. Với một chiều tra cứu khác, ứng dụng cần cung cấp `IndexResolver` phù hợp hoặc cấu hình repository theo khả năng của backend đang dùng.

Ví dụ, một hệ thống SaaS có thể cần tìm phiên theo tenant để hỗ trợ vận hành. Có thể xác định một chỉ mục logic như `tenantId` và giá trị là mã tenant. Luồng tổng quát gồm:

1. Chọn tên chỉ mục ổn định, chẳng hạn `tenantId`.
2. Xác định cách lấy tenant đã được xác thực từ session hoặc security context.
3. Cấu hình resolver để trả về cặp tên chỉ mục và giá trị tương ứng khi repository lưu phiên.
4. Dùng `findByIndexNameAndIndexValue("tenantId", tenantId)` để truy vấn.
5. Kiểm thử việc cập nhật, xóa và hết hạn phiên để bảo đảm chỉ mục được duy trì đồng bộ.

Không nên dùng chỉ mục tùy chỉnh để lưu dữ liệu lớn hoặc dữ liệu thay đổi liên tục. Chỉ mục nên chứa giá trị nhỏ, ổn định và phục vụ một truy vấn vận hành cụ thể. Nếu cần truy vấn theo nhiều thuộc tính phức tạp, quan hệ nhiều chiều hoặc phân trang lớn, hãy cân nhắc một kho dữ liệu nghiệp vụ chuyên dụng thay vì biến session repository thành cơ sở dữ liệu truy vấn tổng quát.

## 5. Redis và JDBC hỗ trợ chỉ mục như thế nào?

Spring Session có các triển khai repository được thiết kế cho tra cứu theo chỉ mục. Với Servlet và các phiên imperative, những lớp thường gặp là `RedisIndexedSessionRepository` và `JdbcIndexedSessionRepository`.

| Backend | Repository hỗ trợ chỉ mục | Cách tổ chức tra cứu |
|---|---|---|
| Redis | `RedisIndexedSessionRepository` | Lưu dữ liệu phiên và cấu trúc chỉ mục riêng để tìm các session ID theo principal/index value |
| JDBC | `JdbcIndexedSessionRepository` | Lưu metadata phiên trong bảng Spring Session và hỗ trợ truy vấn theo principal name qua schema/chỉ mục của repository |

Với Redis, cần chọn cấu hình indexed repository. `RedisSessionRepository` cơ bản lưu phiên nhưng không cung cấp cùng khả năng tra cứu principal như `RedisIndexedSessionRepository`. Trong cấu hình Java tường minh, Spring Session cung cấp `@EnableRedisIndexedHttpSession` cho indexed Redis repository. Với JDBC, `JdbcIndexedSessionRepository` là triển khai có hỗ trợ tra cứu chỉ mục; schema phải tương ứng với phiên bản Spring Session đang dùng.

Trong Spring Boot, hãy kiểm tra dependency Spring Session, cấu hình store và repository thực tế được tạo. Đừng chỉ dựa vào việc Redis hoặc JDBC đã lưu được session để kết luận rằng truy vấn chỉ mục sẽ hoạt động. Có thể kiểm tra kiểu bean được inject hoặc viết kiểm thử tích hợp gọi trực tiếp `findByPrincipalName` sau khi tạo và lưu một phiên có principal index.

Tất cả instance của ứng dụng phải dùng cùng repository, namespace Redis hoặc schema JDBC và cùng cách phân giải principal. Nếu instance A ghi chỉ mục vào namespace này còn instance B đọc namespace khác, tra cứu có thể trả về map rỗng dù cookie phiên vẫn xuất hiện ở trình duyệt.

## 6. Quản lý phiên và đăng xuất trên các thiết bị

Một use case thường gặp là người dùng yêu cầu đăng xuất khỏi tất cả thiết bị. Sau khi lấy các phiên bằng principal name, ứng dụng có thể xóa từng phiên qua `deleteById`, phương thức được kế thừa từ `SessionRepository`.

```java
public void revokeAllSessions(String principalName) {
    Map<String, ? extends Session> sessions =
            repository.findByPrincipalName(principalName);

    sessions.keySet().forEach(repository::deleteById);
}
```

Nếu yêu cầu chỉ đăng xuất các thiết bị khác, cần lấy session ID hiện tại từ request và bỏ qua ID đó khi xóa:

```java
public void revokeOtherSessions(String principalName, String currentSessionId) {
    Map<String, ? extends Session> sessions =
            repository.findByPrincipalName(principalName);

    sessions.keySet().stream()
            .filter(sessionId -> !sessionId.equals(currentSessionId))
            .forEach(repository::deleteById);
}
```

Hai ví dụ là logic ở tầng service. Endpoint gọi chúng phải xác thực người dùng, kiểm tra người gọi có quyền quản lý đúng tài khoản và không cho phép client tùy ý truyền principal name để xóa phiên của người khác. Nếu quản trị viên được phép thực hiện thao tác này, quyền đó phải được kiểm tra ở phía máy chủ và ghi nhận bằng audit log phù hợp.

Tra cứu và xóa là hai thao tác riêng. Một request khác có thể tạo phiên mới hoặc cập nhật phiên trong lúc danh sách đang được xử lý. Hãy chấp nhận việc một ID có thể đã bị xóa trước khi `deleteById` chạy; repository được thiết kế để thao tác xóa ID không còn tồn tại không gây lỗi chỉ vì phiên đã biến mất. Với yêu cầu bảo đảm chặt chẽ hơn, cần phối hợp thao tác với chính sách xác thực, khóa hoặc cơ chế nghiệp vụ tương ứng; không giả định rằng kết quả truy vấn là một snapshot khóa cứng.

Không dùng việc xóa phiên như cách thu hồi một access token độc lập. Nếu ứng dụng phát hành token stateless, việc xóa session không tự động vô hiệu hóa token đó; cần thiết kế cơ chế thu hồi token riêng.

## 7. Kết hợp với Spring Security

Spring Security có thể dùng `SpringSessionBackedSessionRegistry` để quản lý các phiên đăng nhập thông qua `FindByIndexNameSessionRepository`. Đây là lựa chọn phù hợp khi triển khai giới hạn số phiên đồng thời, hiển thị phiên đang đăng nhập hoặc áp dụng chính sách khi một tài khoản đăng nhập trên thiết bị mới.

Registry này dựa trên principal name index để tìm phiên của người dùng. Do đó, điều kiện tiên quyết vẫn là repository hỗ trợ chỉ mục và principal name được resolver ghi nhận đúng. Khi tích hợp, cần bảo đảm tên principal mà Spring Security sử dụng nhất quán với tên principal được lập chỉ mục.

Không nên tự viết một `SessionRegistry` lưu danh sách trong bộ nhớ của từng instance khi ứng dụng chạy nhiều máy chủ. Danh sách đó sẽ không đồng nhất giữa các instance. Registry dựa trên Spring Session giúp việc tra cứu sử dụng kho phiên dùng chung.

## 8. Vòng đời chỉ mục và các tình huống vận hành

Chỉ mục cần phản ánh vòng đời phiên. Khi phiên được lưu với principal index, repository cập nhật cấu trúc tra cứu; khi principal thay đổi, phiên được cập nhật hoặc bị xóa/hết hạn, repository cần điều chỉnh chỉ mục tương ứng. Cách thực hiện cụ thể phụ thuộc backend.

Một số điểm cần kiểm tra khi vận hành:

- **Principal index bị thiếu:** `findByPrincipalName` trả về map rỗng dù phiên tồn tại. Kiểm tra thuộc tính `PRINCIPAL_NAME_INDEX_NAME`, `SPRING_SECURITY_CONTEXT` và resolver đang được dùng.
- **Principal name không khớp:** khác biệt chữ hoa/chữ thường, khoảng trắng, domain prefix hoặc cách chuẩn hóa khiến truy vấn không tìm thấy phiên. Chuẩn hóa thống nhất khi lưu và tìm.
- **Repository không hỗ trợ index:** ứng dụng đang dùng repository cơ bản thay vì indexed implementation. Kiểm tra dependency, cấu hình và kiểu bean thực tế.
- **Dữ liệu hết hạn:** thời điểm xóa dữ liệu vật lý và việc dọn dẹp chỉ mục có thể phụ thuộc TTL hoặc tác vụ cleanup của backend. Không dùng việc key/bản ghi còn tồn tại làm bằng chứng phiên vẫn hợp lệ.
- **Cập nhật đồng thời:** phiên có thể bị thay đổi hoặc xóa giữa lúc truy vấn và lúc xử lý kết quả. Thiết kế thao tác quản trị theo hướng có thể chạy lặp và xử lý ID đã biến mất.
- **Nhiều instance:** các instance phải dùng cùng repository, namespace, schema và cấu hình resolver. Kiểm thử qua load balancer hoặc luân phiên request giữa các instance.
- **Dữ liệu nhạy cảm:** principal name có thể là email hoặc tên đăng nhập. Giới hạn quyền truy vấn, không ghi toàn bộ danh sách session vào log và chỉ trả về metadata cần thiết.

## 9. Kiểm thử tra cứu theo chỉ mục

Kiểm thử đơn vị có thể mock `FindByIndexNameSessionRepository` để xác nhận service gọi đúng principal name và xử lý map kết quả. Tuy nhiên, mock không kiểm tra việc backend tạo, cập nhật và xóa chỉ mục.

Kiểm thử tích hợp nên dùng Redis hoặc cơ sở dữ liệu thử nghiệm cùng indexed repository thực tế. Một kịch bản cơ bản gồm:

1. Tạo một phiên và gắn `PRINCIPAL_NAME_INDEX_NAME` với principal đã chọn.
2. Lưu phiên qua repository.
3. Gọi `findByPrincipalName` và xác nhận map có session ID vừa tạo.
4. Tạo thêm phiên thứ hai cùng principal, xác nhận kết quả chứa cả hai ID.
5. Tra cứu một principal khác và xác nhận không nhận nhầm phiên.
6. Xóa một phiên bằng `deleteById`, tra cứu lại và xác nhận phiên đã xóa không còn trong kết quả.
7. Để phiên hết hạn theo cấu hình repository, sau đó xác nhận hành vi tra cứu và cleanup phù hợp với backend.
8. Nếu chạy nhiều instance, tạo phiên qua instance A và tra cứu qua instance B để xác nhận chỉ mục dùng chung.

Đối với luồng Spring Security, cần có thêm kiểm thử đăng nhập thật qua filter chain để xác nhận `SecurityContext` được lưu trong phiên và principal resolver trích xuất đúng tên. Một bài kiểm thử chỉ tự đặt thuộc tính principal index không chứng minh toàn bộ tích hợp Spring Security đã hoạt động.

## 10. Servlet và WebFlux dùng API khác nhau

`FindByIndexNameSessionRepository` là API imperative thường dùng với Servlet `HttpSession`. Trong ứng dụng WebFlux, Spring Session cung cấp `ReactiveFindByIndexNameSessionRepository`; các phương thức tra cứu trả về `Mono<Map<String, S>>` thay vì `Map` trực tiếp.

Không inject repository reactive vào service Servlet rồi xử lý như API đồng bộ, hoặc chặn luồng reactive chỉ để lấy kết quả. Hãy chọn đúng loại repository theo mô hình web của ứng dụng và giữ nhất quán kiểu xử lý ở tầng service.

## 11. Nguyên tắc thiết kế

- Dùng `FindByIndexNameSessionRepository` khi cần tìm nhiều phiên theo một giá trị đã được lập chỉ mục.
- Dùng `findByPrincipalName` cho tra cứu theo principal; dùng `findByIndexNameAndIndexValue` cho chỉ mục khác đã được cấu hình.
- Bảo đảm principal index được ghi nhận. Spring Session không thể tự suy ra principal từ mọi cơ chế xác thực.
- Chọn indexed repository tương ứng với backend; repository lưu session cơ bản không mặc nhiên hỗ trợ truy vấn chỉ mục.
- Dùng `deleteById` để xóa phiên qua abstraction của Spring Session, không sửa trực tiếp Redis key hoặc SQL row.
- Bảo vệ endpoint liệt kê và thu hồi phiên; session ID và principal name đều cần được xử lý thận trọng.
- Kiểm thử với Redis/JDBC repository thực tế và qua nhiều instance để xác nhận chỉ mục được duy trì đúng trong toàn bộ vòng đời phiên.
