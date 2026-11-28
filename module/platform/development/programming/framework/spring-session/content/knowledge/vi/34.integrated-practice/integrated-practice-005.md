# Giới hạn số phiên, liệt kê phiên của người dùng và thu hồi theo yêu cầu

Spring Session cho phép ứng dụng lưu session trong Redis, JDBC hoặc kho dùng chung để nhiều instance cùng phục vụ một người dùng. Khi hệ thống có nhiều thiết bị hoặc nhiều trình duyệt, một tài khoản có thể đồng thời giữ nhiều phiên. Ứng dụng cần xác định giới hạn số phiên, cho người dùng xem những phiên còn hiệu lực và cho phép thu hồi một phiên hoặc tất cả phiên khác khi phát hiện thiết bị lạ.

Ba khả năng này liên quan chặt chẽ nhưng là ba nghiệp vụ riêng:

- **Giới hạn phiên:** quyết định có cho phép đăng nhập mới khi tài khoản đã đạt ngưỡng hay không, hoặc phiên cũ nào sẽ bị hết hiệu lực.
- **Liệt kê phiên:** tìm các session thuộc một principal đã xác thực, sau đó hiển thị metadata an toàn như thời điểm tạo và truy cập gần nhất.
- **Thu hồi phiên:** xóa hoặc vô hiệu hóa session ở repository để những request tiếp theo không thể tiếp tục dùng phiên đó.

Không nên lưu một danh sách session riêng trong bộ nhớ từng node. Danh sách đó sẽ lệch khi request chuyển node, pod restart hoặc một phiên bị xóa ở nơi khác. Hãy dùng repository có hỗ trợ tìm session theo principal, phối hợp với Spring Security cho giới hạn đăng nhập và áp dụng quyền truy cập chặt chẽ cho API quản lý phiên.

## 1. Kiến trúc quản lý phiên trên nhiều instance

Một hệ thống nhiều instance thường có load balancer phân phối request tới nhiều node. Cookie chứa session ID giúp request tiếp theo tìm đúng phiên trong kho dữ liệu chung.

~~~mermaid
flowchart TD
    B[Browser / Mobile client] --> LB[Load balancer]
    LB --> N1[Application node A]
    LB --> N2[Application node B]
    LB --> N3[Application node C]
    N1 --> R[Indexed SessionRepository]
    N2 --> R
    N3 --> R
    R --> S[(Redis or JDBC)]
    A[Authenticated principal] --> I[Principal index]
    I --> R
    O[Session administration API] --> R
~~~

Repository dùng chung là nguồn dữ liệu cho trạng thái phiên. Khi node A tạo session, node B có thể tìm thấy session đó nếu cùng repository, namespace, serializer và cấu hình. Tương tự, thao tác thu hồi từ node C phải làm cho lần lookup kế tiếp trên node A hoặc B không còn tìm thấy session.

Nếu chỉ giữ SessionRegistry trong RAM của từng JVM, node A có thể biết một phiên còn sống trong khi node B không biết. Điều này làm giới hạn số phiên và thao tác revoke không nhất quán. Với Spring Session, nên dùng SpringSessionBackedSessionRegistry cùng repository có hỗ trợ index principal khi tích hợp Spring Security.

## 2. Phân biệt principal, session ID và session reference

Ba giá trị sau không được dùng thay thế cho nhau:

| Giá trị | Ý nghĩa | Có thể đưa ra client? |
|---|---|---|
| Principal name | Danh tính đã xác thực dùng để nhóm các session của cùng tài khoản | Chỉ khi API được phép và giá trị đã được thiết kế để công khai |
| Session ID | Credential dạng bearer để tiếp tục phiên | Không |
| Session reference | Mã tham chiếu giả danh do ứng dụng tạo cho giao diện quản lý phiên | Có thể, nếu không thể dùng trực tiếp để xác thực |

Session ID phải được coi là bí mật. Nếu API liệt kê trả nguyên ID, người gọi có thể sao chép giá trị đó và dùng như cookie đăng nhập. Không trả session ID trong JSON, URL, log, metric hoặc thông báo hỗ trợ.

Principal dùng để tìm nhóm phiên nên ổn định. Ưu tiên subject ID bất biến từ hệ thống danh tính thay vì email hoặc username có thể đổi. Nếu tên principal không nhất quán về chữ hoa/thường hoặc tenant, hai node có thể lập chỉ mục khác nhau cho cùng người dùng.

Session reference chỉ là cách giao diện chọn một phiên để thu hồi. Nó không được chấp nhận ở middleware xác thực như một session credential.

## 3. Repository cần hỗ trợ tìm theo principal

SessionRepository cơ bản có các thao tác create, save, findById và deleteById. Để liệt kê tất cả session thuộc một principal, cần repository mở rộng FindByIndexNameSessionRepository.

API quan trọng:

~~~java
Map<String, ? extends Session> sessions =
    repository.findByIndexNameAndIndexValue(
        FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
        principalName
    );
~~~

Map trả về ánh xạ session ID tới Session. ID chỉ nên được dùng nội bộ trong service để so sánh hoặc gọi deleteById. Không serialize nguyên map ra response.

Index principal cần được cấu hình và cập nhật đúng lúc đăng nhập. Với Spring Security, Spring Session có thể lấy principal từ SecurityContext được lưu trong session. Repository/index resolver cụ thể quyết định cách giá trị này được trích xuất.

Nếu repository không hỗ trợ index principal, việc quét toàn bộ session để tìm user là không phù hợp ở production: tốn chi phí, khó mở rộng và có thể đọc nhiều dữ liệu nhạy cảm. Hãy chọn repository indexed hoặc xây dựng một index nhất quán có kiểm soát.

## 4. Redis và JDBC: bật khả năng lập chỉ mục

Với Redis, dùng repository có hỗ trợ index, chẳng hạn RedisIndexedSessionRepository được cấu hình qua annotation tương ứng trong phiên bản Spring Session đang sử dụng:

~~~java
@Configuration
@EnableRedisIndexedHttpSession
class RedisSessionConfiguration {
}
~~~

Không nhầm repository indexed với repository Redis chỉ lưu session mà không hỗ trợ tìm theo principal. Kiểm tra đúng annotation, bean và dependency version trong ứng dụng. Khi dùng Redis, index principal và session record cần cùng namespace, cùng serializer và cùng vòng đời.

Với JDBC, Spring Session cung cấp JdbcIndexedSessionRepository trong các cấu hình hỗ trợ. Bảng session có thể chứa principal name cùng các cột metadata và bảng attributes. Schema/index phải khớp phiên bản thư viện. Nếu tự sửa schema, cần kiểm tra migration script và index cho principal lookup.

Bảng so sánh:

| Tiêu chí | Redis indexed | JDBC indexed |
|---|---|---|
| Lưu session | Key/hash và cấu trúc phụ trợ | Bảng session và bảng attributes |
| Tìm theo principal | Principal index | Principal column/index |
| Hết hạn | TTL và cơ chế expiration/cleanup | Expiry time và cleanup job |
| Thu hồi | Xóa session và dữ liệu index liên quan | Xóa row session/attributes theo repository |
| Vận hành | Theo dõi memory, replication, keyspace events | Theo dõi index, transaction, pool và cleanup |
| Nhất quán | Phụ thuộc Redis topology và repository implementation | Phụ thuộc transaction/isolation và database |

Không suy luận rằng hai repository phát event hết hạn giống nhau. Khả năng tìm theo principal, cleanup và event lifecycle phụ thuộc implementation và cấu hình.

## 5. Principal index được cập nhật từ đâu?

Khi người dùng đăng nhập, Spring Security tạo Authentication và lưu SecurityContext vào session theo cấu hình. Principal index resolver có thể đọc tên principal từ SecurityContext đó để đưa session vào nhóm của người dùng.

Một số ứng dụng có thể đặt principal index tường minh:

~~~java
session.setAttribute(
    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
    canonicalPrincipal
);
~~~

Chỉ làm điều này khi API và repository implementation của phiên bản đang dùng hỗ trợ cách lập chỉ mục đó. Không tự đặt một attribute tùy ý rồi giả định mọi repository sẽ tự động tạo index.

Các yêu cầu cần bảo đảm:

- Principal được chuẩn hóa giống nhau trên mọi node.
- Chỉ dữ liệu xác thực server-side được dùng để xác định principal.
- Không lấy principal name từ request parameter để gán index.
- Session anonymous không được xếp nhầm vào một tài khoản.
- Khi đăng nhập đổi principal, index cũ phải được cập nhật hoặc session được thay mới theo security flow.
- Khi logout hoặc revoke, index liên quan phải được dọn theo semantics repository.

Nếu index không có dữ liệu, findByIndexNameAndIndexValue có thể trả map rỗng dù session record vẫn tồn tại. Khi đó, hãy kiểm tra quá trình đăng nhập, SecurityContext persistence và cấu hình indexed repository.

## 6. Định nghĩa chính sách giới hạn số phiên

Trước khi cấu hình kỹ thuật, hãy quyết định giới hạn áp dụng cho đối tượng nào:

- Mỗi tài khoản toàn hệ thống.
- Mỗi tài khoản trong một ứng dụng.
- Mỗi tài khoản theo tenant.
- Mỗi loại client, ví dụ web và mobile.
- Mỗi thiết bị hoặc mỗi trình duyệt.
- Tổng số phiên đăng nhập, không tính session anonymous.

Một chính sách mẫu:

| Chính sách | Giới hạn | Khi đạt ngưỡng |
|---|---:|---|
| Tài khoản thông thường | 3 | Từ chối đăng nhập mới |
| Tài khoản hỗ trợ | 5 | Hết hiệu lực phiên ít hoạt động nhất |
| Tài khoản đặc quyền | 2 | Yêu cầu xác nhận và audit |
| Session anonymous | Theo TTL riêng | Không tính vào số phiên xác thực |

Không chọn chính sách dựa trên số cookie ở browser. Một browser có thể có nhiều cookie, còn một session có thể được dùng trên nhiều tab. Nguồn đếm phải là session đã xác thực trong repository.

Nếu giới hạn theo tenant hoặc loại client, index principal đơn lẻ có thể chưa đủ. Có thể cần index bổ sung hoặc truy vấn theo principal kết hợp tenant/client. Không đưa giá trị tùy ý từ client vào index key.

## 7. Giới hạn phiên bằng Spring Security

Spring Security Servlet hỗ trợ concurrent session control thông qua session management và SessionRegistry. Với Spring Session, dùng SpringSessionBackedSessionRegistry để registry truy vấn repository dùng chung thay vì chỉ giữ trạng thái cục bộ.

Ví dụ bean:

~~~java
@Bean
SpringSessionBackedSessionRegistry<? extends Session> sessionRegistry(
        FindByIndexNameSessionRepository<? extends Session> repository) {
    return new SpringSessionBackedSessionRegistry<>(repository);
}
~~~

Sau đó cấu hình giới hạn:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        SpringSessionBackedSessionRegistry<? extends Session> registry)
        throws Exception {

    http.sessionManagement(session -> session
        .maximumSessions(3)
        .maxSessionsPreventsLogin(true)
        .sessionRegistry(registry)
    );

    return http.build();
}
~~~

Đây là cấu hình minh họa cho Servlet stack; cần ghép vào SecurityFilterChain hiện có và kiểm tra đúng phiên bản Spring Security/Spring Session. Không tạo một filter chain thứ hai chỉ để thêm maximumSessions nếu ứng dụng đã có cấu hình bảo mật.

Hai lựa chọn chính:

- maxSessionsPreventsLogin(true): khi đã đủ phiên, đăng nhập mới bị từ chối.
- maxSessionsPreventsLogin(false): đăng nhập mới được chấp nhận và phiên cũ nhất có thể bị đánh dấu hết hiệu lực theo chiến lược concurrent-session control.

Hãy chọn theo yêu cầu sản phẩm. Nếu từ chối đăng nhập mới, giao diện cần giải thích giới hạn và hướng dẫn người dùng thu hồi phiên cũ. Nếu hết hiệu lực phiên cũ, người dùng có thể mất dữ liệu chưa lưu trên thiết bị đó.

## 8. SpringSessionBackedSessionRegistry khác registry trong RAM thế nào?

SessionRegistry trong bộ nhớ theo dõi các phiên trong một JVM. Trong cụm nhiều node, registry của node A không tự biết session do node B tạo nếu không có cơ chế đồng bộ bổ sung.

SpringSessionBackedSessionRegistry dùng FindByIndexNameSessionRepository để tìm session theo principal. Do đó, các node cùng truy vấn kho session chung và có thể thấy cùng danh sách phiên.

Điều kiện cần:

- Repository có hỗ trợ tìm theo principal.
- Principal index được cập nhật.
- Mọi node dùng cùng namespace/schema.
- Session được lưu vào repository trước khi node khác tìm.
- Các thao tác expire/delete được phản ánh theo semantics repository.
- Phiên bản code và serializer tương thích giữa các node.

Không dùng registry backed-by-session nếu repository chỉ implement SessionRepository mà không có principal index. Hãy kiểm tra kiểu bean được inject thực tế.

## 9. Giới hạn số phiên và race khi đăng nhập đồng thời

Concurrent-session control thường kiểm tra số session hiện có rồi quyết định cho đăng nhập hoặc hết hiệu lực một phiên cũ. Trong cụm nhiều node, hai login request có thể cùng đọc số lượng trước khi session mới của request kia được lưu.

Ví dụ khi giới hạn là 1:

~~~mermaid
sequenceDiagram
    participant A as Login A / Node 1
    participant R as Shared repository
    participant B as Login B / Node 2
    A->>R: Find sessions for principal
    B->>R: Find sessions for principal
    R-->>A: 0 active sessions
    R-->>B: 0 active sessions
    A->>R: Save new session A
    B->>R: Save new session B
    Note over R: Có thể xuất hiện 2 session nếu admission không atomic
~~~

Một registry dùng chung cải thiện khả năng nhìn thấy session giữa node, nhưng bản thân việc đọc số lượng rồi ghi session không nhất thiết là một transaction atomic trên toàn cụm.

Nếu giới hạn là quy tắc cứng, cần một cơ chế admission có tính nguyên tử:

- Khóa theo principal ở kho dùng chung, có TTL và fencing token.
- Bảng slot phiên với unique constraint và transaction.
- Redis Lua script hoặc thao tác atomic phù hợp để đặt chỗ.
- Version/CAS khi cập nhật tập session.
- Serialize login theo principal ở một dịch vụ admission.

Phải định nghĩa thời điểm đặt chỗ và giải phóng slot khi login thất bại, session hết hạn hoặc logout. Distributed lock đơn giản không có fencing có thể hết hạn khi tác vụ cũ vẫn chạy. Không tuyên bố giới hạn tuyệt đối nếu chỉ dùng kiểm tra count không atomic.

## 10. Liệt kê phiên của người dùng hiện tại

Endpoint tự phục vụ nên lấy principal từ Authentication hiện tại, không nhận username tùy ý từ query parameter.

Ví dụ service:

~~~java
public record SessionSummary(
        String reference,
        Instant createdAt,
        Instant lastAccessedAt,
        Duration maxInactiveInterval,
        boolean current) {
}

@Service
class UserSessionService {

    private final FindByIndexNameSessionRepository<? extends Session> repository;
    private final SessionReferenceEncoder referenceEncoder;

    UserSessionService(
            FindByIndexNameSessionRepository<? extends Session> repository,
            SessionReferenceEncoder referenceEncoder) {
        this.repository = repository;
        this.referenceEncoder = referenceEncoder;
    }

    List<SessionSummary> listSessions(
            String principalName,
            String currentSessionId) {

        Map<String, ? extends Session> sessions =
            repository.findByIndexNameAndIndexValue(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                principalName
            );

        return sessions.entrySet().stream()
            .map(entry -> {
                Session session = entry.getValue();
                String id = entry.getKey();

                return new SessionSummary(
                    referenceEncoder.encode(id),
                    session.getCreationTime(),
                    session.getLastAccessedTime(),
                    session.getMaxInactiveInterval(),
                    id.equals(currentSessionId)
                );
            })
            .sorted(Comparator.comparing(
                SessionSummary::lastAccessedAt,
                Comparator.nullsLast(Comparator.reverseOrder())
            ))
            .toList();
    }
}
~~~

Ví dụ dùng record Java hiện đại; nếu dự án dùng Java version cũ hơn, thay record bằng DTO thông thường và điều chỉnh toList() thành collector phù hợp.

Controller có thể lấy principal và session hiện tại:

~~~java
@GetMapping("/api/me/sessions")
List<SessionSummary> mySessions(
        Authentication authentication,
        HttpServletRequest request) {

    HttpSession current = request.getSession(false);
    String currentId = current == null ? null : current.getId();

    return userSessionService.listSessions(
        authentication.getName(),
        currentId
    );
}
~~~

Đảm bảo endpoint chỉ truy cập sau xác thực. Không gọi getSession(true) chỉ để lấy current ID vì nó có thể tạo session mới khi người dùng chỉ muốn xem danh sách.

## 11. Chỉ trả metadata cần thiết

Một danh sách session hữu ích không cần chứa mọi thuộc tính trong session. Các trường thường đủ:

- Mã tham chiếu giả danh.
- Thời điểm tạo.
- Thời điểm truy cập gần nhất.
- Thời lượng idle tối đa hoặc thời điểm hết hạn ước tính.
- Đánh dấu phiên hiện tại.
- Nhãn thiết bị nếu ứng dụng đã thu thập an toàn và có lý do rõ ràng.

Không trả:

- Session ID.
- Cookie value.
- SecurityContext.
- Principal object đầy đủ.
- Access token hoặc refresh token.
- Toàn bộ session attributes.
- Redis key hoặc JDBC primary key nội bộ.

User-Agent và IP có thể giúp nhận diện thiết bị nhưng là dữ liệu riêng tư, có thể không chính xác và dễ bị giả mạo. Nếu sản phẩm cần hiển thị “Chrome trên Windows” hoặc vị trí gần đúng, hãy thu thập có chủ đích, giảm độ chi tiết và thông báo rõ cho người dùng. Không dùng IP/User-Agent làm yếu tố xác thực.

## 12. Tạo session reference không tiết lộ ID gốc

Một cách là tạo HMAC-SHA-256 từ session ID bằng secret key do ứng dụng quản lý:

~~~java
final class SessionReferenceEncoder {

    private final SecretKey key;

    SessionReferenceEncoder(SecretKey key) {
        this.key = key;
    }

    String encode(String sessionId) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            byte[] digest = mac.doFinal(
                sessionId.getBytes(StandardCharsets.UTF_8)
            );
            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (GeneralSecurityException error) {
            throw new IllegalStateException(
                "Cannot encode session reference", error
            );
        }
    }
}
~~~

HMAC tạo ra reference ổn định với cùng session ID và cùng key, nhưng không thể dùng trực tiếp làm session credential. Khi người dùng yêu cầu revoke, service liệt kê các session thuộc principal đã xác thực, tính reference cho từng ID và so sánh với reference được gửi lên.

Yêu cầu bảo vệ:

- Secret key lấy từ secret manager/KMS, không hard-code.
- Không ghi key hoặc session ID vào log.
- Dùng key version để hỗ trợ rotation.
- Reference không được chấp nhận ở endpoint xác thực.
- Có thể dùng MessageDigest.isEqual để so sánh byte array theo cách giảm rò rỉ timing.
- Không dùng reference làm metric label.
- Coi reference vẫn là dữ liệu có thể liên kết các sự kiện và giới hạn retention.

Nếu không cần reference ổn định, có thể tạo random handle lưu mapping server-side với TTL. Khi đó phải quản lý mapping, dọn mapping sau revoke và bảo vệ endpoint tương tự.

## 13. Thu hồi một phiên theo yêu cầu

Khi nhận yêu cầu revoke, service phải xác minh reference thuộc một session của principal đang thao tác. Không nhận session ID thô từ client.

Pseudocode:

~~~text
revoke(principal, sessionReference):
    sessions = repository.findByPrincipal(principal)

    target = find entry where
        constantTimeEquals(
            reference(entry.sessionId),
            sessionReference
        )

    if target not found:
        return not found

    repository.deleteById(target.sessionId)
    return revoked
~~~

Ví dụ triển khai:

~~~java
boolean revokeSession(
        String principalName,
        String requestedReference) {

    Map<String, ? extends Session> sessions =
        repository.findByIndexNameAndIndexValue(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            principalName
        );

    for (Map.Entry<String, ? extends Session> entry
            : sessions.entrySet()) {

        String reference =
            referenceEncoder.encode(entry.getKey());

        if (constantTimeEquals(reference, requestedReference)) {
            repository.deleteById(entry.getKey());
            return true;
        }
    }

    return false;
}

private boolean constantTimeEquals(String left, String right) {
    return MessageDigest.isEqual(
        left.getBytes(StandardCharsets.UTF_8),
        right.getBytes(StandardCharsets.UTF_8)
    );
}
~~~

Service chỉ xóa ID tìm được trong tập session của principal đã xác thực. Nếu reference không thuộc principal đó, trả kết quả không tìm thấy hoặc không được phép theo quy ước API; không tiết lộ session có thuộc tài khoản khác hay không.

Repository deleteById là thao tác đồng bộ trong ví dụ Servlet. Với reactive stack, dùng API reactive tương ứng và compose publisher vào request pipeline; không gọi block().

## 14. Thu hồi tất cả phiên khác

Nhiều sản phẩm cần nút “Đăng xuất khỏi các thiết bị khác”. Khi đó, giữ phiên hiện tại để người dùng tiếp tục quản lý tài khoản, đồng thời xóa mọi phiên còn lại.

~~~java
int revokeOtherSessions(
        String principalName,
        String currentSessionId) {

    Map<String, ? extends Session> sessions =
        repository.findByIndexNameAndIndexValue(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            principalName
        );

    int revoked = 0;

    for (String sessionId : sessions.keySet()) {
        if (!sessionId.equals(currentSessionId)) {
            repository.deleteById(sessionId);
            revoked++;
        }
    }

    return revoked;
}
~~~

Đây là ví dụ cơ bản. Nếu có login đồng thời trong lúc revoke, một session mới có thể được tạo sau khi danh sách đã được đọc. Nếu yêu cầu “revoke tất cả phiên khác” phải có semantics mạnh, cần phối hợp với admission control hoặc tăng phiên bản bảo mật của principal để từ chối các session được tạo trước mốc thu hồi.

Nếu muốn revoke tất cả kể cả phiên hiện tại, thao tác xóa current session sẽ khiến request tiếp theo cần xác thực lại. Response cũng cần xóa cookie đúng tên, Path và Domain. Không giả định xóa repository record tự động xóa mọi cookie của browser.

## 15. Thu hồi ngay lập tức có giới hạn gì?

Xóa session khỏi repository bảo đảm các lần lookup sau khi xóa được nhìn thấy sẽ không tải lại session đó. Tuy nhiên, một request đã tải session vào bộ nhớ và đang chạy có thể tiếp tục tới khi hoàn tất. Một số cache hoặc replication topology cũng có thể làm thời điểm quan sát xóa khác nhau.

Cần xác định mức bảo đảm:

| Mức | Ý nghĩa |
|---|---|
| Revoke cho request kế tiếp | Request mới lookup repository sẽ không thấy session |
| Revoke có propagation | Các node nhận biết thay đổi qua repository/event/cache invalidation |
| Revoke mạnh | Request đang chạy cũng phải kiểm tra trạng thái thu hồi trước thao tác nhạy cảm |

Nếu cần revoke mạnh cho thao tác chuyển tiền hoặc thay đổi bảo mật, không chỉ dựa vào session đã tải ở đầu request. Có thể cần kiểm tra session version/revocation epoch tại thời điểm commit nghiệp vụ, hoặc kiểm tra trạng thái thu hồi gần thời điểm thực hiện hành động.

Không dùng event bất đồng bộ làm bằng chứng duy nhất rằng mọi node đã dừng dùng session. Event hỗ trợ thông báo và cleanup; repository hoặc revocation state mới là nguồn kiểm tra.

## 16. Kết hợp với Spring Security concurrent-session control

Spring Security quản lý số phiên đồng thời qua maximumSessions. Khi tích hợp Spring Session, SpringSessionBackedSessionRegistry giúp registry tra cứu session từ repository dùng chung.

Một cấu hình giới hạn 2 phiên và cho phép đăng nhập mới thay thế phiên cũ:

~~~java
http.sessionManagement(session -> session
    .maximumSessions(2)
    .maxSessionsPreventsLogin(false)
    .sessionRegistry(sessionRegistry)
);
~~~

Hành vi chính xác khi session cũ bị đánh dấu expired phụ thuộc Spring Security strategy và filter xử lý concurrent session. Cần kiểm thử request tiếp theo từ session bị hết hiệu lực và đảm bảo người dùng được chuyển về xác thực lại.

Nếu muốn chặn login mới:

~~~java
http.sessionManagement(session -> session
    .maximumSessions(2)
    .maxSessionsPreventsLogin(true)
    .sessionRegistry(sessionRegistry)
);
~~~

Không nhầm hai hành vi:

- **Reject new login:** giữ các session hiện có và từ chối phiên mới.
- **Expire old session:** cho login mới nhưng làm một phiên cũ mất hiệu lực.

Giao diện cần giải thích chính sách. Nếu người dùng chọn “đăng xuất thiết bị cũ”, API revoke thủ công có thể phù hợp hơn với việc tự động chọn session cũ nhất.

## 17. Phối hợp logout, revoke và session fixation

Logout thông thường của người dùng nên:
- Xóa SecurityContext.
- Invalidate HttpSession.
- Xóa session khỏi repository.
- Hết hạn cookie session.
- Phát event lifecycle nếu repository hỗ trợ.

Khi revoke một phiên từ thiết bị khác, không thể gửi response tới browser đang ở thiết bị đó để xóa cookie ngay. Cookie vẫn nằm trong browser, nhưng ID đã bị thu hồi ở server. Khi request tiếp theo gửi cookie cũ, repository không tìm thấy session và ứng dụng yêu cầu đăng nhập lại.

Sau đăng nhập, Spring Security có thể đổi session ID để chống session fixation. Principal index phải theo dõi đúng session hiện tại sau khi ID đổi. Test cần xác nhận danh sách phiên không tạo bản ghi trùng hoặc để lại index cũ.

Không chỉ xóa cookie trên thiết bị đang gọi API quản lý phiên. Revoke phải xóa session record của thiết bị mục tiêu ở server-side repository.

## 18. Bảo vệ API quản lý phiên

Các endpoint quản lý session có thể ảnh hưởng trực tiếp tới quyền truy cập tài khoản. Cần bảo vệ như API bảo mật:

| Endpoint | Quyền |
|---|---|
| GET /api/me/sessions | Người dùng đã xác thực, chỉ xem phiên của mình |
| DELETE /api/me/sessions/{reference} | Người dùng đã xác thực, chỉ thu hồi phiên thuộc mình |
| POST /api/me/sessions/revoke-others | Người dùng đã xác thực, thu hồi tất cả phiên khác |
| GET /api/admin/users/{id}/sessions | Chỉ role quản trị phù hợp |
| DELETE /api/admin/users/{id}/sessions/{reference} | Quyền quản trị đặc biệt và audit |

Nguyên tắc:

- Lấy principal từ SecurityContext, không tin principal trong request body.
- API admin phải kiểm tra quyền trên target user/tenant.
- Dùng CSRF protection nếu xác thực bằng cookie.
- Dùng POST/DELETE cho thao tác thay đổi trạng thái, không dùng GET.
- Có rate limit cho revoke-all và thao tác admin.
- Yêu cầu re-authentication hoặc MFA cho hành động rủi ro cao.
- Không trả session ID hoặc raw repository key.
- Không tiết lộ sự tồn tại của session thuộc tài khoản khác.
- Audit actor, target principal đã giả danh, action, outcome và trace ID; không audit raw session ID.

Nếu người dùng có thể thu hồi phiên hiện tại, UI phải cảnh báo rằng request tiếp theo sẽ cần đăng nhập lại.

## 19. Xử lý index cũ và session hết hạn

Index principal có thể không phản ánh hoàn hảo dữ liệu session nếu expiration cleanup bị trễ hoặc event bị mất. Khi liệt kê phiên:

- Chỉ dựa vào repository indexed API được hỗ trợ.
- Nếu API trả session đã hết hạn theo implementation, lọc theo lastAccessedTime và maxInactiveInterval khi có đủ metadata.
- Không refresh TTL chỉ vì đang liệt kê.
- Không coi một index entry là bằng chứng session vẫn có thể xác thực.
- Ghi nhận metric cho stale entry/lookup miss mà không log ID.

Công thức ước tính hết hạn idle:

~~~text
estimatedExpiry =
    lastAccessedTime + maxInactiveInterval
~~~

Đây chỉ là ước tính dựa trên metadata và đồng hồ. TTL backend, thời điểm truy cập và cleanup job có thể làm thời gian quan sát khác nhau. Không dùng giá trị hiển thị này để cấp quyền hoặc quyết định bảo mật.

Khi revoke, repository deleteById nên xử lý cả dữ liệu phiên và index liên quan theo implementation. Nếu index được quản lý riêng, kiểm tra cleanup sau delete/expire.

## 20. Giới hạn phiên theo principal, tenant và loại client

Nếu ứng dụng multi-tenant, cùng một username có thể tồn tại ở nhiều tenant. Principal index nên chứa định danh duy nhất, ví dụ subject kết hợp tenant theo quy tắc chuẩn hóa. Không ghép chuỗi thiếu delimiter hoặc dùng giá trị client tự gửi.

Nếu muốn giới hạn riêng cho web và mobile, có thể lưu một attribute client type đã được xác minh ở server-side khi tạo session. Tuy nhiên, index principal chuẩn có thể chỉ trả tất cả session của principal; service phải lọc loại client dựa trên metadata đáng tin cậy.

Không cho client tự sửa attribute client type sau đăng nhập. Không tin User-Agent để quyết định quyền. Session metadata nên được thiết lập tại authentication success handler hoặc một điểm server-side có kiểm soát.

## 21. Kiểm thử giới hạn số phiên

Các bài kiểm thử cần bao phủ:

- Đăng nhập lần đầu tạo một session được index theo principal.
- Đăng nhập lần hai khi chưa đạt ngưỡng.
- Đăng nhập khi đã đạt ngưỡng và chính sách reject.
- Đăng nhập khi đã đạt ngưỡng và chính sách expire-old.
- Session hết hạn không còn được tính như phiên hoạt động.
- Logout làm giảm số phiên có thể tìm thấy.
- Hai login đồng thời trên hai node không vượt ngưỡng nếu chính sách yêu cầu hard limit.
- Principal của tenant A không ảnh hưởng tenant B.
- Session anonymous không bị tính vào số phiên xác thực.

Không chỉ unit test strategy. Cần integration test với SessionRepository và Spring Security filter chain để kiểm tra đăng nhập thực tế.

## 22. Kiểm thử liệt kê và thu hồi

Ma trận test cho API quản lý:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| User A liệt kê session | Chỉ thấy session của A |
| User A gửi reference của B | Không revoke được session B |
| Reference không tồn tại | Trả kết quả không tìm thấy theo API contract |
| Revoke một session khác | Lookup session đó không còn thấy |
| Revoke current session | Request tiếp theo yêu cầu xác thực lại |
| Revoke all others | Current session còn hiệu lực, các phiên khác bị xóa |
| Hai request cùng revoke một session | Thao tác lặp an toàn |
| Session đã hết hạn | Không hiển thị như phiên hoạt động |
| Repository unavailable | Trả lỗi hạ tầng, không báo danh sách rỗng giả |
| Index principal thiếu | Phát hiện lỗi cấu hình qua test |
| Session ID | Không xuất hiện trong response/log/metric |
| CSRF | Request thay đổi trạng thái thiếu token bị từ chối |

Nên dùng test fixture với session ID giả lập và kiểm tra response body không chứa marker đó.

## 23. Kiểm thử nhiều node và race condition

Dùng Redis hoặc database dùng chung để chạy hai application context hoặc hai instance test. Các tình huống:

1. Node A tạo session và đăng nhập.
2. Node B liệt kê session theo principal và thấy session đó.
3. Node B revoke session.
4. Node A nhận request tiếp theo với cookie cũ.
5. Request không còn được xác thực.
6. Node A tạo session mới nếu người dùng đăng nhập lại.
7. Kiểm tra index không giữ entry mồ côi.

Với concurrent login, đồng bộ hai request bằng barrier để chúng cùng kiểm tra số lượng trước khi lưu. Nếu hard limit là 1, test phải chứng minh cơ chế admission atomic chứ không chỉ chạy hai login tuần tự.

Với revoke-all, tạo một login mới đồng thời với thao tác revoke. Định nghĩa rõ session mới có được giữ hay cũng phải bị thu hồi. Dùng version/epoch hoặc khóa theo principal nếu cần bảo đảm.

## 24. Session revocation epoch cho yêu cầu mạnh

Một mô hình nâng cao là lưu security epoch/version cho principal. Mỗi session chứa epoch lúc được tạo. Khi người dùng chọn revoke all, ứng dụng tăng epoch hiện tại của principal. Request nhạy cảm chỉ được chấp nhận nếu epoch trong session khớp epoch hiện hành.

~~~mermaid
flowchart TD
    A[Authenticated request] --> B[Read session epoch]
    B --> C[Read principal current epoch]
    C --> D{Epochs match?}
    D -->|Yes| E[Continue authorization]
    D -->|No| F[Reject and invalidate session]
    G[Revoke all sessions] --> H[Increment principal epoch]
~~~

Cách này giúp thu hồi theo mốc phiên bản, kể cả khi xóa danh sách session không atomic. Tuy nhiên, nó yêu cầu kho epoch dùng chung, kiểm tra ở đúng điểm bảo mật và xử lý cache nhất quán. Nếu cache epoch quá lâu, revoke có thể bị trễ. Đây là thiết kế bổ sung, không phải hành vi tự động của Spring Session.

Không tăng epoch cho một thao tác revoke một session nếu nghiệp vụ chỉ muốn thu hồi một thiết bị. Với revoke all, epoch có thể đơn giản hóa việc từ chối mọi session cũ, nhưng vẫn cần cleanup dữ liệu vật lý.

## 25. Event và audit khi thu hồi

Spring Session có thể phát event tạo, xóa hoặc hết hạn tùy repository. Listener có thể dùng để:

- Cập nhật metric session lifecycle.
- Gửi thông báo tới WebSocket hoặc thiết bị khác.
- Dọn cache phụ trợ.
- Ghi audit event không chứa ID thô.
- Kích hoạt cleanup tác vụ liên quan.

Không dùng event làm nguồn duy nhất cho session list hoặc authorization. Event có thể trễ, mất hoặc lặp. Revoke cần cập nhật repository trước; event là tín hiệu phụ trợ.

Audit event nên chứa:
- Actor principal giả danh hoặc internal subject reference.
- Target principal theo chính sách dữ liệu.
- Action: revoke_one, revoke_others, revoke_all, expire.
- Outcome: success, not_found, failed.
- Timestamp, application version, node pool.
- Trace ID/request ID.

Không ghi session ID, cookie, HMAC secret hoặc toàn bộ session attributes vào audit log.

## 26. API response mẫu

Một response liệt kê có thể như sau:

~~~json
{
  "sessions": [
    {
      "reference": "c5sX...opaque...",
      "createdAt": "2026-11-26T08:10:00Z",
      "lastAccessedAt": "2026-11-26T09:12:00Z",
      "estimatedExpiresAt": "2026-11-26T09:42:00Z",
      "current": true
    },
    {
      "reference": "b8Qm...opaque...",
      "createdAt": "2026-11-25T14:30:00Z",
      "lastAccessedAt": "2026-11-26T07:55:00Z",
      "estimatedExpiresAt": "2026-11-26T08:25:00Z",
      "current": false
    }
  ],
  "maximumSessions": 3
}
~~~

Các reference là dữ liệu minh họa. API không trả raw session ID. Nếu không thể tính estimatedExpiresAt đáng tin cậy, chỉ trả lastAccessedAt và maxInactiveInterval.

Response revoke:

~~~json
{
  "revoked": true
}
~~~

Không trả thêm ID đã bị xóa. Với reference không tồn tại, chọn 404 hoặc 204 theo API contract; không tiết lộ một ID có thuộc người dùng khác hay không.

## 27. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Danh sách session luôn rỗng | Repository không indexed hoặc principal không được lập chỉ mục | Dùng indexed repository và kiểm tra SecurityContext/index resolver |
| Node A thấy phiên, node B không thấy | Dùng registry trong RAM hoặc namespace lệch | SpringSessionBackedSessionRegistry và shared repository |
| Người dùng vượt giới hạn khi login đồng thời | Kiểm tra count và save không atomic | Admission control có transaction/CAS/lock có fencing |
| Revoke thành công nhưng session còn dùng được | Xóa nhầm namespace hoặc request đã tải session trước đó | Kiểm tra repository, cache và yêu cầu revoke mạnh |
| Revoke reference của user khác | Service không giới hạn lookup theo principal | Tìm reference trong tập session của principal đã xác thực |
| API làm lộ session ID | Serialize map repository trực tiếp | Trả DTO với reference giả danh |
| Logout không xóa cookie | Sai cookie name, Path hoặc Domain | Hết hạn đúng cookie scope |
| Session đã hết hạn vẫn hiển thị | Index/cleanup trễ | Lọc metadata và xác minh repository semantics |
| Revoke-all bỏ sót login mới | Login xảy ra sau lúc list | Dùng principal epoch hoặc admission coordination |
| JDBC lookup principal chậm | Thiếu index hoặc query không phù hợp | Kiểm tra schema/index và execution plan |
| Redis memory tăng do index mồ côi | Expiration/delete cleanup không hoạt động | Kiểm tra event, TTL và index cleanup |
| User bị logout nhầm ở tenant khác | Principal key không phân biệt tenant | Dùng canonical tenant-scoped principal |

## 28. Checklist trước khi phát hành

**Repository và index**
- Repository hỗ trợ FindByIndexNameSessionRepository.
- Redis/JDBC indexed implementation được bật đúng.
- Principal index lấy từ danh tính server-side ổn định.
- Mọi node dùng cùng namespace, schema và serializer.
- Expiration/delete dọn index theo semantics đã xác minh.

**Giới hạn phiên**
- Chính sách số phiên được định nghĩa theo account/tenant/client.
- SpringSessionBackedSessionRegistry được cấu hình.
- Chọn rõ reject login mới hay expire phiên cũ.
- Kiểm thử hai login đồng thời trên nhiều node.
- Nếu hard limit, có admission control atomic.

**Liệt kê và thu hồi**
- API list lấy principal từ SecurityContext.
- Response không chứa session ID hoặc cookie.
- Session reference được tạo bằng HMAC hoặc random handle.
- Revoke chỉ tìm trong tập session của principal được phép.
- Có revoke một phiên, revoke phiên khác và revoke tất cả theo nhu cầu.
- Revoke-all xử lý login đồng thời theo semantics rõ ràng.
- CSRF, authorization, re-authentication và rate limit được áp dụng.

**Vận hành**
- Có metric số session, lookup miss, revoke outcome và repository latency.
- Không dùng session ID/user ID làm metric label.
- Audit không chứa ID thô.
- Có test Redis/JDBC thật, TTL, expiration và nhiều node.
- Có runbook khi index hỏng hoặc repository unavailable.
- Xác định rõ mức đảm bảo revoke đối với request đang chạy.

Giới hạn số phiên, liệt kê và thu hồi phải dựa trên cùng một nguồn dữ liệu phiên có thể truy vấn theo principal. Dùng indexed SessionRepository và SpringSessionBackedSessionRegistry để phối hợp với Spring Security trên nhiều instance. API tự phục vụ chỉ được liệt kê phiên của principal hiện tại, trả metadata an toàn và dùng session reference giả danh để thu hồi. Với hard limit hoặc revoke-all cần tính đúng các race khi login và request xảy ra đồng thời; một lần đọc danh sách rồi xóa không tự tạo ra transaction toàn cụm. Kiểm thử trên Redis/JDBC thật, bảo vệ API bằng authorization/CSRF phù hợp và tuyệt đối không công bố session ID như một giá trị hiển thị.

## Tài liệu tham khảo

- [Spring Session — FindByIndexNameSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html)
- [Spring Session — Redis Indexed Sessions](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Session — Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Concurrent Session Control](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html#servlet-authentication-session-management-concurrency)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)

