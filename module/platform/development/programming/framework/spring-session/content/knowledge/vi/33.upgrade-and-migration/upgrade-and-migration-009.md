# Rolling upgrade, rollback và kiểm thử tương thích phiên trước khi triển khai

Khi triển khai phiên bản mới của một ứng dụng Spring có dùng Spring Session, nhiều instance cũ và mới có thể cùng phục vụ request trong một khoảng thời gian. Trong giai đoạn rolling upgrade, một instance cũ có thể ghi session theo định dạng cũ, instance mới đọc session đó; sau đó instance mới ghi một attribute mới và request tiếp theo lại được chuyển tới instance cũ. Nếu hai phiên bản không hiểu cùng cookie, session attributes, serializer hoặc trạng thái xác thực, người dùng có thể bị logout, mất dữ liệu tạm hoặc gặp lỗi deserialize ngay giữa đợt triển khai.

Vì vậy, tương thích phiên phải được xem là một phần của kế hoạch phát hành. Một bản build mới chạy tốt trên một node riêng chưa chứng minh nó tương thích với dữ liệu do phiên bản trước ghi. Rolling upgrade đòi hỏi kiểm tra cả chiều đọc và chiều ghi giữa các phiên bản đang cùng tồn tại. Rollback cũng phải được thiết kế trước: nếu phiên bản mới đã ghi định dạng mà phiên bản cũ không đọc được, việc đưa binary cũ trở lại có thể làm hỏng request đang mang session mới.

Trong SPRING_SESSION, Spring Session giúp session được chia sẻ giữa các instance qua Redis hoặc JDBC, nhưng không tự bảo đảm mọi phiên bản ứng dụng tương thích với nhau. Ứng dụng vẫn phải duy trì hợp đồng dữ liệu session, cookie, TTL và trạng thái xác thực. Bài học này trình bày chiến lược expand-contract, kiểm thử mixed-version, triển khai theo đợt, rollback an toàn và thời điểm có thể loại bỏ định dạng cũ.

## 1. Vì sao rolling upgrade tác động tới session?

Giả sử một cụm có bốn instance phiên bản N và đang triển khai phiên bản N+1. Load balancer chuyển request tới bất kỳ instance khỏe nào. Tất cả instance cùng đọc một Redis namespace hoặc cùng JDBC session tables.

~~~mermaid
flowchart TD
    B[Browser gửi session cookie] --> LB[Load balancer]
    LB --> O1[Instance N]
    LB --> O2[Instance N]
    LB --> N1[Instance N+1]
    LB --> N2[Instance N+1]
    O1 --> R[(Shared Spring Session store)]
    O2 --> R
    N1 --> R
    N2 --> R
~~~

Trong thời gian này, các tình huống sau đều có thể xảy ra:

- Instance N ghi session attributes theo schema cũ; N+1 phải đọc được.
- Instance N+1 ghi attribute mới; N phải đọc được nếu request kế tiếp có thể tới N.
- N và N+1 dùng cùng session ID nhưng serializer khác nhau.
- N lưu SecurityContext với class principal cũ; N+1 đã đổi package hoặc cấu trúc class.
- Một node thay cookie name hoặc cookie path; browser gửi cookie tới node khác nhưng node đó không tìm được session.
- Một node dùng namespace Redis/schema JDBC khác; session có vẻ biến mất khi request đổi node.

Đây là lý do cần phân biệt “binary tương thích” với “session data tương thích”. Hai instance có thể chạy đồng thời mà không lỗi startup, nhưng vẫn không đọc được session do phiên bản kia ghi.

## 2. Hợp đồng tương thích của session gồm những gì?

Trước khi nâng cấp, xác định những thành phần sau là hợp đồng được chia sẻ giữa các phiên bản:

| Thành phần | Điều cần giữ tương thích |
|---|---|
| Session ID | Cách đọc ID từ cookie và cách repository tra cứu ID |
| Cookie | Name, Domain, Path, Secure, HttpOnly, SameSite và encoding |
| Repository scope | Redis namespace/key prefix hoặc JDBC schema/table |
| Serializer | Java serialization, JSON hoặc serializer tùy chỉnh; type metadata và charset |
| Attribute names | Tên attribute, kiểu dữ liệu và ý nghĩa |
| Attribute schema | Field bắt buộc/tùy chọn, enum, date/time, null semantics và version |
| Authentication | Principal, authorities, SecurityContext và cách khôi phục |
| Lifecycle | TTL, max inactive interval, expiration, invalidation và session ID rotation |
| Repository behavior | Save mode, flush mode, index và transaction assumptions |

Một thay đổi chỉ ở controller có thể không ảnh hưởng session. Nhưng đổi tên attribute, kiểu dữ liệu, class principal hoặc cookie name có thể làm hỏng tương thích dù API bên ngoài không đổi.

Không coi cấu trúc key nội bộ của Spring Session Redis hoặc schema nội bộ của repository là hợp đồng tùy ý để sửa trực tiếp. Hãy dùng API/configuration được hỗ trợ ở phiên bản dự án và migration script tương ứng.

## 3. Backward compatibility và forward compatibility

Hai khái niệm này mô tả hai chiều đọc dữ liệu:

- **Backward-compatible reader:** phiên bản mới đọc được dữ liệu do phiên bản cũ ghi.
- **Forward-compatible reader:** phiên bản cũ đọc được dữ liệu do phiên bản mới ghi.

Trong rolling deployment, cả hai chiều có thể cần thiết vì old và new nodes cùng hoạt động. Nếu N+1 chỉ đọc được format mới, nó không thể phục vụ session hiện có do N tạo. Nếu N+1 ghi format mới ngay khi một node được deploy, node N còn lại có thể không đọc được session đó.

| Writer | Reader | Test cần có trong rolling window |
|---|---|---|
| N | N | Hoạt động hiện tại |
| N | N+1 | Bắt buộc: phiên bản mới phải đọc session cũ |
| N+1 | N | Bắt buộc nếu node cũ còn có thể nhận request |
| N+1 | N+1 | Hoạt động sau nâng cấp |

Nếu không thể bảo đảm N+1 writer tương thích với N reader, không bật ghi format mới trong khi còn node N. Có thể giữ format cũ cho tới khi toàn bộ node cũ đã rời cụm và rollback về N không còn nằm trong cửa sổ được hỗ trợ.

## 4. Chiến lược expand-contract cho session attributes

Expand-contract là cách thay đổi dữ liệu theo nhiều pha để các phiên bản cùng tồn tại có thời gian tương thích.

Ví dụ phiên bản N lưu:

~~~json
{
  "schemaVersion": 1,
  "displayName": "An"
}
~~~

Phiên bản N+1 muốn thêm preferredLanguage. Một thay đổi an toàn có thể là thêm field tùy chọn và đặt default khi field vắng mặt:

~~~json
{
  "schemaVersion": 1,
  "displayName": "An",
  "preferredLanguage": "vi"
}
~~~

Nhưng nếu N deserialize thành class cứng không chấp nhận field lạ, hoặc schema mới thay kiểu displayName từ String sang object, N có thể lỗi. Cần xác minh serializer và reader behavior, không chỉ nhìn JSON.

Quy trình tổng quát:

1. **Expand:** chuẩn bị reader có thể xử lý cả dữ liệu cũ và dữ liệu mở rộng; không xóa field cũ.
2. **Deploy compatibility release:** triển khai code mới nhưng tiếp tục ghi định dạng cũ hoặc dạng giao nhau mà N và N+1 đều hiểu.
3. **Drain old nodes:** chờ tất cả instance N rời khỏi traffic và background workers cũ dừng.
4. **Enable new writes:** chỉ sau khi old reader không còn được dùng, bật ghi schema mới nếu cần.
5. **Migrate gradually:** đọc cũ, chuyển đổi khi có request hoặc chạy migration batch có giới hạn.
6. **Contract:** chỉ bỏ field/reader cũ sau khi hết session cũ, hết rollback window và đã xác minh không còn consumer cũ.

Không phải mọi thay đổi đều cần dual-write. Nếu chỉ thêm một attribute tùy chọn mà phiên bản cũ bỏ qua an toàn, có thể dùng cách đơn giản hơn. Nếu thay đổi không tương thích, cần bridge release, feature flag hoặc kế hoạch kết thúc session cũ.

## 5. Ba pha triển khai khuyến nghị

~~~mermaid
flowchart LR
    A[Phase 1: Compatibility release] --> B[Phase 2: Rolling deploy]
    B --> C[Phase 3: Enable new format]
    C --> D[Phase 4: Contract after expiry window]
~~~

**Phase 1 — Compatibility release**

- Code mới đọc được session format hiện tại.
- Code mới vẫn ghi format mà phiên bản cũ hiểu.
- Giữ cookie name, namespace/schema và TTL không đổi.
- Bổ sung metrics để phát hiện deserialize errors và session misses.
- Chạy mixed-version tests trước khi triển khai.

**Phase 2 — Rolling deploy**

- Deploy từng nhóm instance hoặc canary.
- Trong lúc N và N+1 cùng chạy, cả hai vẫn đọc/ghi hợp đồng giao nhau.
- Theo dõi login failures, session read/save errors, cookie issuance và latency.
- Không bật feature thay đổi schema session chưa tương thích.

**Phase 3 — Enable new format**

- Chỉ bật sau khi tất cả old nodes và worker đã được drain.
- Giữ reader tương thích ngược trong thời gian rollback.
- Nếu cần rollback về N, phải chứng minh binary đó đọc được format mới hoặc có đường quay lại compatibility release.

**Phase 4 — Contract**

- Đợi session cũ hết TTL hoặc chủ động kết thúc theo chính sách.
- Hết thời gian rollback cần hỗ trợ.
- Bỏ code đọc format cũ, field cũ và migration logic.
- Sau cùng mới xóa cột/index cũ hoặc namespace cũ nếu có kế hoạch riêng.

## 6. Đừng bật ghi format mới quá sớm

Giả sử N chỉ đọc cartState dạng String, còn N+1 đổi sang object CartStateV2. Nếu N+1 ghi object mới ngay khi canary đầu tiên chạy, request tiếp theo có thể tới N và N không deserialize được.

Một cách an toàn là tách khả năng đọc và khả năng ghi bằng feature flag:

~~~yaml
app:
  session:
    read-v2-enabled: true
    write-v2-enabled: false
~~~

Trong giai đoạn compatibility, N+1 có thể đọc cả v1 và v2 nhưng vẫn ghi v1. Sau khi tất cả N nodes được drain và rollback policy được chấp thuận, bật write-v2-enabled.

Feature flag cần được quản lý tập trung và đồng nhất trên các instance. Nếu một node ghi v2 trong khi node khác còn ghi v1, cần có semantics rõ ràng để tránh ghi đè qua lại. Đừng dựa vào flag cục bộ thay đổi tùy ý ở từng node.

## 7. Thiết kế session attribute có version

Nếu ứng dụng tự lưu object trong session, hãy định nghĩa schema rõ ràng và có version. Ví dụ DTO có thể được chuyển đổi từ v1 sang model nội bộ hiện tại:

~~~java
public record CartStateV1(
        int itemCount,
        String currency) implements java.io.Serializable {
}

public record CartStateV2(
        int itemCount,
        String currency,
        String couponCode) implements java.io.Serializable {
}

public CartStateV2 upgrade(CartStateV1 oldState) {
    return new CartStateV2(
            oldState.itemCount(),
            oldState.currency(),
            null);
}
~~~

Code đọc session có thể nhận dạng version và chuyển đổi:

~~~java
Object value = session.getAttribute("app.cart.state");

CartStateV2 current;
if (value instanceof CartStateV2 v2) {
    current = v2;
} else if (value instanceof CartStateV1 v1) {
    current = upgrade(v1);
} else {
    current = new CartStateV2(0, "VND", null);
}
~~~

Đây là minh họa khi serializer khôi phục được các kiểu DTO tương ứng. Nếu dùng Java serialization, các kiểu được lưu phải đáp ứng contract Serializable; việc thêm interface này không tự bảo đảm mọi thay đổi class đều tương thích. Nếu dùng JSON, nên deserialize vào envelope/Map có schemaVersion rồi map sang DTO; không bật polymorphic type handling rộng mà không giới hạn type an toàn.

Giữ attribute name ổn định nếu có thể. Khi buộc phải đổi tên, có thể đọc tên mới trước rồi fallback tên cũ trong giai đoạn chuyển tiếp. Chỉ ghi tên mới sau khi old readers không còn tồn tại; sau thời gian TTL/rollback, bỏ fallback cũ.

## 8. Serializer là ranh giới tương thích quan trọng

### 8.1. Java serialization

Java native serialization gắn dữ liệu với class name, class structure và serialVersionUID. Các thay đổi class có thể gây InvalidClassException, ClassNotFoundException hoặc lỗi khôi phục object. Đổi package/class name của principal hoặc session DTO có thể làm phiên bản cũ/mới không đọc được dữ liệu đã lưu.

Ngay cả khi đặt serialVersionUID cố định, không phải mọi thay đổi cấu trúc đều an toàn. Cần kiểm thử bằng payload thực tế được tạo từ binary cũ và đọc bởi binary mới; đồng thời kiểm tra chiều ngược lại nếu rolling window yêu cầu.

Không serialize các object phụ thuộc implementation như Hibernate proxy, servlet request, service bean hoặc class nội bộ dễ thay đổi. Ưu tiên DTO nhỏ, ổn định và không chứa secret không cần thiết.

### 8.2. JSON hoặc serializer có schema

JSON có thể giảm coupling class layout, nhưng vẫn cần quản lý:

- Field thêm mới có default hoặc optional semantics.
- Field bị bỏ có được reader cũ/new chấp nhận không.
- Enum mới có khiến reader cũ lỗi không.
- Thay kiểu dữ liệu có tương thích không.
- Type metadata có an toàn và giới hạn danh sách class không.
- Null/missing field được diễn giải giống nhau không.

Không coi JSON tự động tương thích. Ví dụ reader cũ có thể reject enum value mới hoặc yêu cầu field bắt buộc đã bị bỏ.

### 8.3. Kiểm thử bằng fixture từ phiên bản cũ

Tạo fixture session từ bản build trước trong môi trường test. Kiểm thử:

1. Binary mới đọc fixture cũ.
2. Binary mới ghi session mới và binary cũ đọc được nếu cần rollback về bản cũ.
3. Hai phiên bản cùng đọc/ghi một session trong mixed-version test.
4. Session có SecurityContext, principal và authorities vẫn được khôi phục đúng.
5. Payload không hợp lệ được xử lý an toàn, không làm toàn bộ request path sập không kiểm soát.

Fixture nên là dữ liệu tổng hợp, không sao chép session của người dùng production vì payload có thể chứa thông tin cá nhân hoặc credential.

## 9. Spring Security và SecurityContext phải tương thích

Trong ứng dụng Servlet session-based, Spring Security có thể lưu SecurityContext vào HttpSession. Spring Session lưu session đó vào Redis/JDBC. Vì vậy, nâng cấp Spring Security hoặc thay principal class có thể ảnh hưởng session đã đăng nhập.

Kiểm tra các thành phần:

- Principal class và package.
- Authentication implementation.
- Granted authorities và role mapping.
- Custom user details fields.
- SecurityContext serialization.
- Session fixation protection và session ID rotation.
- Remember-me hoặc authorized client attributes nếu được lưu trong session.

Ví dụ, phiên bản N lưu com.example.auth.UserPrincipal, còn N+1 chuyển class sang com.example.identity.AccountPrincipal. Nếu payload cũ chứa class name cũ, N+1 cần class compatibility hoặc migration mapping. Ngược lại, nếu N+1 ghi class mới rồi rollback về N, N có thể không tìm thấy class.

Không dùng việc session record tồn tại làm bằng chứng user vẫn được xác thực. Test phải khôi phục Authentication, kiểm tra principal và authorities, sau đó gọi endpoint được bảo vệ. Nếu không thể giữ tương thích an toàn, có thể chủ động invalidate session và yêu cầu đăng nhập lại; phải coi đó là quyết định sản phẩm có thông báo và kế hoạch hỗ trợ.

## 10. Redis: giữ ổn định namespace và cách lưu trong rolling window

Với Spring Session Redis, các instance cùng một ứng dụng thường dùng chung Redis namespace. Trong rolling upgrade:

- Giữ redisNamespace ổn định.
- Giữ serializer tương thích giữa nodes.
- Không tự đổi key prefix hoặc cấu trúc Redis nội bộ.
- Không xóa toàn bộ namespace khi deploy.
- Không đổi TTL mặc định mà không đánh giá tác động tới session hiện tại.
- Nếu thay đổi attribute format, áp dụng expand-contract.

Ví dụ cấu hình namespace cần được giữ nhất quán giữa các instance:

~~~java
@Configuration
@EnableRedisHttpSession(
        redisNamespace = "portal:session",
        maxInactiveIntervalInSeconds = 1800)
class SessionConfiguration {
}
~~~

Annotation và thuộc tính cụ thể phụ thuộc Spring Session version. Trong môi trường dùng Spring Boot auto-configuration, không tạo cấu hình trùng lặp gây ra nhiều repository/connection factory. Điều quan trọng trong rollout là tất cả nodes của cùng session domain dùng cùng repository scope và hiểu cùng dữ liệu.

Ví dụ trên dùng Servlet stack với HttpSession. Ứng dụng WebFlux cần reactive session repository và cấu hình Redis WebSession tương ứng, chẳng hạn @EnableRedisWebSession cùng ReactiveRedisConnectionFactory ở các phiên bản hỗ trợ. Không dùng @EnableRedisHttpSession cho WebFlux hoặc trộn Servlet và reactive repository trong cùng session domain nếu chưa có thiết kế chuyển đổi rõ ràng.

Redis key layout là chi tiết implementation có thể thay đổi theo version. Không viết migration bằng cách tự rename/delete key dựa trên prefix nội bộ nếu không có contract được hỗ trợ. Nếu cần di chuyển namespace, xây migration có đọc/ghi rõ ràng, có đo đạc và có rollback plan; không coi đổi namespace là thay đổi cấu hình vô hại vì session cũ sẽ không được tìm thấy ở namespace mới.

## 11. JDBC: schema migration theo expand-contract

Spring Session JDBC dùng các bảng session và attributes theo schema được cung cấp cho phiên bản/dialect tương ứng. Nâng cấp có thể cần chạy schema migration, nhưng không nên tự ý đổi tên cột hoặc xóa index trong khi binary cũ vẫn chạy.

Một quy trình an toàn:

1. Đọc migration/schema guidance của đúng Spring Session version và database dialect.
2. Sao lưu và kiểm tra migration trên bản copy dữ liệu test.
3. **Expand:** thêm cột nullable, index mới hoặc bảng phụ mà binary cũ có thể bỏ qua.
4. Deploy code mới có thể đọc cả schema cũ và schema mở rộng.
5. Backfill theo batch nhỏ, có checkpoint và rate limit nếu cần.
6. Chờ toàn bộ old nodes và jobs dừng.
7. **Contract:** chỉ xóa cột/index/bảng cũ sau rollback window và sau khi xác minh không còn reader cũ.

Không chạy DDL destructive trong cùng thời điểm rolling deploy nếu old nodes còn cần schema cũ. DDL có thể khóa bảng hoặc làm query chậm; đo lock duration và chọn migration strategy phù hợp database.

### 11.1. Kiểm tra index và cleanup query

Session cleanup thường dựa vào thời gian hết hạn và các index của schema. Thay đổi index có thể ảnh hưởng cả performance và compatibility. Kiểm tra execution plan, write amplification và lock/build cost trước khi tạo index lớn.

Không xóa bảng SPRING_SESSION_ATTRIBUTES hoặc thay primary key chỉ vì tên cột có vẻ nội bộ. Dùng schema script/migration phù hợp phiên bản. Nếu schema migration thất bại giữa chừng, dừng rollout và xác định trạng thái DDL trước khi chạy lại; một số database tự commit DDL, một số khác có transaction semantics khác.

## 12. Cookie contract phải ổn định trong rolling upgrade

Browser gửi session ID theo cookie attributes. Nếu N phát cookie SESSION với Path / còn N+1 đổi thành PORTAL_SESSION hoặc Path /app, request tiếp theo có thể không mang ID mà node mới mong đợi.

Trong giai đoạn rolling, giữ ổn định:

- Cookie name.
- Domain và Path.
- Secure và HttpOnly.
- SameSite.
- Cách encode/decode session ID.
- Quy tắc xóa cookie khi logout.

Đổi cookie name là một migration giao thức browser, không chỉ là rename biến. Nếu phải đổi, cần chiến lược dual-read/accept old cookie, phát cookie mới, xóa cookie cũ và hỗ trợ rollback. Cơ chế này phải được thiết kế và test rõ; Spring Session không tự động biến mọi cookie name change thành migration trong suốt.

Không mở rộng cookie Domain hoặc Path quá mức chỉ để tiện rollout. Cookie domain-wide có thể gửi session credential tới nhiều subdomain hơn. Giữ phạm vi bảo mật như trước nếu không có quyết định kiến trúc riêng.

## 13. TTL và session lifecycle khi nâng cấp

Thay maxInactiveIntervalInSeconds ảnh hưởng session đang hoạt động và session mới theo semantics repository/version. Một thay đổi TTL có thể làm:

- Session hết hạn sớm hơn và người dùng bị logout.
- Session tồn tại lâu hơn, tăng memory/database footprint.
- Cleanup workload thay đổi đột ngột.
- Event expiration đến ở thời điểm khác.

Trước khi thay TTL, xác định:

1. Idle timeout mong muốn.
2. Absolute lifetime nếu ứng dụng có giới hạn riêng.
3. TTL thực tế của session đã lưu.
4. Cookie Max-Age/Expires có đồng bộ hay không.
5. Chính sách expiration và cleanup của Redis/JDBC.
6. Hành vi khi rollback về phiên bản cũ với timeout khác.

Không giả định đổi cấu hình mới lập tức sửa TTL của tất cả session cũ. Kiểm tra repository implementation và dữ liệu thật trong test. Nếu cần rút ngắn lifetime vì bảo mật, cân nhắc invalidate chủ động hoặc migration có kiểm soát thay vì trông chờ config mới áp dụng hồi tố.

## 14. Rolling deployment theo canary và từng đợt

Một kế hoạch triển khai thực tế có thể gồm:

1. Chạy compatibility test trên build mới với session fixtures cũ.
2. Deploy một canary instance N+1 vào cụm nhưng giữ write format tương thích.
3. Chuyển một tỷ lệ nhỏ traffic và quan sát lỗi deserialize, session miss, login failure và latency.
4. Xác minh request luân phiên giữa N và N+1 bằng cùng cookie.
5. Tiếp tục thay từng batch instance.
6. Drain old nodes, background workers, scheduled jobs và consumer có đọc session.
7. Chờ xác nhận không còn traffic tới N.
8. Bật tính năng ghi schema mới nếu cần.
9. Theo dõi session error rate và datastore load trong rollback window.
10. Sau khi hết rollback window và session cũ hết hạn/migrate xong, contract code/schema cũ.

~~~mermaid
sequenceDiagram
    participant LB as Load balancer
    participant N as Old nodes N
    participant N1 as New canary N+1
    participant R as Shared session store
    LB->>N: Traffic hiện tại
    N->>R: Đọc/ghi format v1
    LB->>N1: Canary traffic
    N1->>R: Đọc v1, ghi format tương thích
    Note over N,N1: Mixed-version compatibility window
    LB->>N: Drain old nodes
    N-->>LB: Không còn nhận traffic
    LB->>N1: Chuyển toàn bộ traffic sang N+1
    N1->>R: Có thể bật format v2 sau gate
~~~

Canary không chỉ là kiểm tra health endpoint. Cần có test request thật tạo session ở N rồi đọc ở N+1 và ngược lại khi policy yêu cầu. Health check có thể xanh dù session serializer đang lỗi.

## 15. Rollback: binary cũ có đọc được dữ liệu mới không?

Rollback thường được mô tả là chuyển traffic về image cũ. Với Spring Session, cần trả lời thêm: image cũ có đọc được tất cả session data mà image mới đã ghi không?

| Trạng thái trước rollback | Rủi ro | Hướng xử lý |
|---|---|---|
| N+1 chỉ ghi format v1 tương thích N | Thấp hơn | Có thể rollback về N theo kiểm thử |
| N+1 đã ghi attribute v2 nhưng N bỏ qua field an toàn | Có thể rollback được | Xác minh serializer và reader thực tế |
| N+1 ghi class/enum/type mà N không biết | Deserialize failure | Rollback về compatibility bridge hoặc invalidate/migrate session |
| N+1 đổi cookie name | Browser có thể chỉ giữ cookie mới | Cần dual-cookie migration hoặc buộc đăng nhập lại có kế hoạch |
| N+1 đổi Redis namespace | N không tìm thấy session ở namespace mới | Cần migration/dual-read hoặc quay lại namespace cũ có dữ liệu |
| N+1 thay JDBC schema destructive | N có thể query lỗi | Khôi phục schema tương thích trước khi chạy binary cũ |
| N+1 đổi TTL/rules | Session có thể hết hạn khác dự kiến | Đánh giá dữ liệu còn lại và policy rollback |

Không rollback binary trước khi xác định session data và schema có tương thích. Một lựa chọn an toàn là rollback về phiên bản bridge N+0.5 có thể đọc cả v1/v2, thay vì về N cũ hoàn toàn.

Nếu không thể duy trì backward compatibility, cần chấp nhận một trong các phương án: chuyển đổi dữ liệu ngược có kiểm chứng, giữ một compatibility service, hoặc invalidate session và yêu cầu người dùng đăng nhập lại. Đây là trade-off về trải nghiệm và bảo mật, phải được phê duyệt trước release.

## 16. Session migration khi format không tương thích

Nếu cần chuyển đổi session data, ưu tiên migration lazy hoặc batch có giới hạn:

**Lazy migration**

- Khi N+1 đọc session v1, deserialize và map sang model nội bộ v2.
- Ghi lại v2 chỉ khi toàn bộ reader còn hoạt động hiểu v2.
- Giữ khả năng đọc v1 trong thời gian TTL/rollback.
- Ghi metric số session v1/v2 được đọc/chuyển đổi.

**Batch migration**

- Xác định chính xác key/table theo API/schema được hỗ trợ.
- Chia batch nhỏ, có checkpoint và giới hạn tốc độ.
- Không đọc hoặc log payload nhạy cảm ngoài nhu cầu chuyển đổi.
- Có thể chạy lại an toàn sau interruption.
- Có metric số record thành công/thất bại và backlog.
- Chỉ xóa dữ liệu cũ sau xác minh và hết rollback window.

Spring Session không cung cấp một cơ chế dual repository/migration tổng quát tự động cho mọi custom session attributes. Nếu cần custom migration, phải thiết kế theo repository và serializer cụ thể, kiểm tra concurrency và không sửa cấu trúc nội bộ dựa trên giả định không được hỗ trợ.

## 17. Kiểm thử tương thích trước khi triển khai

Một bộ test compatibility phải sử dụng dữ liệu do các phiên bản thật tạo ra, không chỉ tạo object mới trong test code hiện tại.

### 17.1. Golden fixtures

Tạo session fixture bằng binary N:

- Session anonymous có attributes cơ bản.
- Session đã đăng nhập với principal và authorities.
- Session chứa custom DTO hoặc workflow state.
- Session có attribute optional/missing.
- Session gần hết TTL.
- Session sau login/session fixation rotation nếu có.

Sau đó dùng binary N+1 đọc fixture. Nếu rollback về N nằm trong yêu cầu, dùng N đọc fixture do N+1 ghi.

Fixture cần được tạo bằng dữ liệu tổng hợp, loại bỏ cookie/session ID production và secret. Quản lý fixture như test artifact có version, không commit credential hoặc payload người dùng.

### 17.2. Ma trận reader/writer

| Writer | Reader | Test cần xác minh |
|---|---|---|
| N | N+1 | New version đọc được session cũ |
| N+1 compatibility mode | N | Old version đọc được dữ liệu new version ghi trong rolling window |
| N+1 | N+1 | New version đọc/ghi đúng schema mới |
| N+1 format v2 | N | Chỉ được phép nếu rollback vẫn cần và old reader hỗ trợ v2 |
| N+1 | N+1 sau restart | Session tồn tại qua restart/deploy |

Kiểm thử cả round-trip: writer tạo session, reader đọc và cập nhật, writer ban đầu đọc lại. Điều này giúp phát hiện serializer hoặc attribute mutation không tương thích.

## 18. Kiểm thử với Redis và JDBC thật

### Redis integration test

- Khởi chạy Redis phiên bản tương thích môi trường production bằng Testcontainers hoặc môi trường test riêng.
- Cấu hình namespace giống production nhưng tách biệt theo test run.
- Chạy ứng dụng N và N+1 với cùng session repository.
- Tạo session ở N, gửi cookie tới N+1 và kiểm tra attributes/principal.
- Ghi session ở N+1, đọc lại ở N nếu rollback compatibility yêu cầu.
- Kiểm tra TTL, expiration, invalidate và key cleanup.
- Kiểm tra restart instance và reconnect.

Không chỉ dùng mock SessionRepository; mock không xác minh serialization, Redis commands, TTL hoặc namespace.

### JDBC integration test

- Dùng database engine/dialect gần production.
- Chạy schema migration trước binary mới theo đúng thứ tự triển khai.
- Xác minh N và N+1 cùng truy cập schema trong expand phase.
- Kiểm tra insert/update/delete session và attributes.
- Kiểm tra index/expiration cleanup và transaction boundaries.
- Kiểm tra rollback schema có còn phục vụ binary cũ không.

H2 hoặc một database khác có thể hữu ích cho unit/integration test nhanh nhưng không thay thế kiểm thử dialect/DDL/locking trên database production khi migration phụ thuộc đặc tính riêng.

## 19. Kiểm thử mixed-version và concurrency

Một test quan trọng mô phỏng hai instance:

1. Gửi request tới node N để tạo session và lấy cookie.
2. Gửi request có cookie đó tới node N+1.
3. N+1 cập nhật một attribute tương thích.
4. Gửi request tiếp theo tới N.
5. Xác minh N vẫn đọc được session và không lỗi deserialize.
6. Chạy thêm request đồng thời từ cả hai node nếu ứng dụng cho phép.
7. Kiểm tra lost update, last-write-wins hoặc version conflict theo semantics repository.

Đặc biệt kiểm thử:

- Hai node cùng đọc và cập nhật một attribute.
- Node mới ghi attribute optional, node cũ bỏ qua.
- Node cũ save snapshot sau khi node mới ghi dữ liệu.
- Session ID rotation xảy ra trong lúc request khác đang chạy.
- Logout ở một node và request đồng thời tới node còn lại.
- TTL được refresh bởi nhiều node với timeout configuration giống nhau.

Không giả định Spring Session tự cung cấp optimistic locking cho mọi repository. Nếu session attributes có thể bị ghi đồng thời, phải hiểu save mode/flush mode và repository behavior của phiên bản đang dùng.

## 20. Kiểm thử cookie và browser behavior

Session store tương thích vẫn không đủ nếu browser không gửi đúng cookie:

- Kiểm tra cookie name và value sau login.
- Kiểm tra Domain/Path giữa phiên bản cũ và mới.
- Kiểm tra Secure/HttpOnly/SameSite không bị thay đổi ngoài ý muốn.
- Kiểm tra response khi session ID rotate.
- Kiểm tra logout xóa cookie đúng name/path/domain.
- Kiểm tra browser gửi cookie tới cả old và new instances qua load balancer.
- Nếu đổi cookie, kiểm tra dual-read/expiration và rollback.

Dùng browser automation hoặc HTTP client có cookie jar cho end-to-end. Test gửi MockHttpSession trực tiếp không chứng minh browser cookie contract. Cũng không lấy session ID thật từ môi trường production làm fixture.

## 21. Kiểm thử TTL và thời gian tồn tại session qua rollout

Rolling upgrade có thể kéo dài nhiều phút hoặc giờ; session có thể được tạo trước, trong và sau deployment. Cần kiểm thử:

- Session tạo trước rollout vẫn được đọc trong rollout.
- Session mới tạo bởi N+1 vẫn được N đọc nếu mixed-version policy yêu cầu.
- Session gần hết TTL không bị gia hạn ngoài ý muốn chỉ vì migration read.
- TTL sau khi cập nhật được đặt đúng theo policy.
- Session hết hạn trong rollback window không được khôi phục chỉ vì binary cũ trở lại.
- Cleanup job không xóa session đang hoạt động do thay đổi timestamp/schema.

Thời gian chờ để contract dữ liệu cũ nên dựa trên maximum session lifetime thực tế, không chỉ idle timeout nếu hệ thống còn absolute lifetime hoặc cookie lifetime khác. Nếu có session không có TTL hoặc cleanup bị trì hoãn, phải có cách đo backlog trước khi xóa reader cũ.

## 22. Theo dõi canary và mixed-version metrics

Trong rollout, theo dõi riêng:

- Tỷ lệ session lookup miss theo application version.
- Lỗi serialization/deserialization theo version và repository.
- Session save/delete timeout.
- Authentication failure và user re-login rate.
- Cookie issuance/rotation anomalies.
- TTL/expiration rate và số session bị evict.
- Redis/JDBC latency, connection pool pressure và error rate.
- Số request theo old/new version.

Không dùng session ID hoặc principal làm metric label. Dùng application_version, repository_type, operation, outcome và environment với cardinality thấp.

Đặt rollback trigger trước release, ví dụ deserialize error vượt baseline, session miss tăng bất thường, login failure tăng, hoặc repository latency vượt SLO trong thời gian liên tục. Threshold phải dựa trên baseline thực tế; không dùng một con số cố định cho mọi hệ thống.

## 23. Rollback runbook

Khi canary hoặc rolling upgrade có vấn đề:

1. Dừng rollout để không thêm node mới.
2. Xác định lỗi nằm ở binary, serializer, cookie, schema, Redis topology hay datastore availability.
3. Kiểm tra phiên bản nào đã ghi session format mới và feature flag hiện tại.
4. Kiểm tra schema JDBC migration có thay đổi destructive không.
5. Nếu old binary vẫn đọc được dữ liệu, rollback traffic về N theo quy trình.
6. Nếu old binary không đọc được dữ liệu, rollback về compatibility bridge hoặc tắt write-v2 nếu reader cũ vẫn còn hỗ trợ dữ liệu đang lưu.
7. Nếu không có đường tương thích, cân nhắc migration ngược có kiểm chứng hoặc invalidate session theo kế hoạch được phê duyệt.
8. Xác minh cookie cũ/mới, login, logout và session lookup sau rollback.
9. Theo dõi orphan sessions, TTL cleanup, retry rate và datastore load.
10. Ghi lại phiên bản writer/reader và dữ liệu đã thay đổi để chuẩn bị lần triển khai tiếp theo.

Không xóa Redis namespace hoặc truncate JDBC session tables như thao tác rollback mặc định. Việc đó có thể logout toàn bộ người dùng và phá hủy bằng chứng điều tra.

## 24. Khi nào chấp nhận invalidate toàn bộ session?

Đôi khi thay đổi bảo mật hoặc serializer không thể giữ tương thích. Buộc người dùng đăng nhập lại có thể là lựa chọn hợp lý nếu:

- Session payload có nguy cơ không còn an toàn để tin cậy.
- Principal/authority contract thay đổi đáng kể.
- Session ID/cookie policy được thay đổi vì lý do bảo mật.
- Migration có nguy cơ deserialize sai hoặc cấp nhầm quyền.
- Không thể bảo đảm old/new readers tương thích trong thời gian cần thiết.

Nếu chọn invalidate:

- Thông báo rõ tác động đăng nhập lại.
- Chọn thời điểm ít ảnh hưởng.
- Thực hiện bằng cơ chế được hỗ trợ và có kiểm soát.
- Không xóa nhầm dữ liệu Redis/JDBC dùng chung cho ứng dụng khác.
- Đảm bảo cookie cũ không được chấp nhận sau invalidation.
- Đo tỷ lệ login thành công sau rollout và chuẩn bị hỗ trợ người dùng.

Giữ session bằng mọi giá không quan trọng hơn tính đúng đắn và an toàn của authentication.

## 25. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Người dùng bị logout trong rolling deploy | New node không đọc serializer/attribute cũ | Kiểm tra fixture từ phiên bản N và backward reader |
| Node cũ lỗi sau khi node mới ghi | N+1 ghi format mà N không hiểu | Giữ write format cũ cho tới khi drain N hoặc có forward compatibility |
| Rollback binary thành công nhưng session lỗi | Binary cũ không đọc payload mới | Rollback về bridge release hoặc migrate/invalidate session |
| Session không tìm thấy sau deploy | Namespace/schema/cookie name thay đổi | So sánh cấu hình giữa versions; không đổi repository scope ngoài kế hoạch |
| InvalidClassException sau nâng cấp | Java serialized class thay đổi | Dùng DTO/schema version hoặc compatibility class; kiểm thử old fixtures |
| JDBC application cũ không chạy sau migration | DDL xóa/đổi cột khi old nodes còn hoạt động | Dùng expand-contract và trì hoãn destructive DDL |
| Cookie không gửi tới node mới | Domain/Path/name/SameSite thay đổi | Kiểm tra browser cookie jar và response Set-Cookie |
| TTL thay đổi làm session hết hạn sớm | Cấu hình mới áp dụng cho session update hoặc cleanup khác | Kiểm thử TTL cũ/mới và lập kế hoạch migration |
| Session attributes mất sau request đồng thời | Old snapshot ghi đè update mới | Giảm shared mutable attributes; dùng version/CAS cho state quan trọng |
| Canary health xanh nhưng user vẫn logout | Health check không đi qua session serializer | Thêm mixed-version login/session tests và metrics |
| Migration batch làm datastore quá tải | Batch lớn hoặc chạy nhiều worker | Giảm batch/concurrency, rate limit và checkpoint |
| Feature flag ghi v2 chỉ bật trên vài node | Cấu hình không đồng nhất | Quản lý flag tập trung, xác minh effective config từng instance |

## 26. Quy trình triển khai trước release

Khi chuẩn bị triển khai một phiên bản Spring Session mới:

1. Ghi lại baseline: Spring Boot/Spring Session/Spring Security, Java runtime, Redis/JDBC driver, serializer, namespace/schema, cookie và TTL.
2. Liệt kê session attributes cùng class/type đang được lưu, đặc biệt principal và SecurityContext.
3. Tạo golden fixtures từ phiên bản đang chạy và kiểm thử binary mới đọc được.
4. Nếu rollback về bản cũ nằm trong yêu cầu, kiểm thử bản cũ đọc dữ liệu do bản mới ghi.
5. Thiết kế expand-contract cho attributes, serializer và JDBC schema.
6. Giữ cookie contract, repository namespace và TTL ổn định trong mixed-version window.
7. Chạy Redis/JDBC integration tests với datastore gần production.
8. Chạy mixed-version tests, concurrency tests và browser cookie tests.
9. Định nghĩa canary, rollout batch, metrics và rollback trigger.
10. Triển khai compatibility release trước khi bật format mới.
11. Drain toàn bộ old nodes/background workers trước khi contract.
12. Chờ session cũ hết hạn hoặc migrate xong và hết rollback window trước khi xóa reader/schema cũ.

## 27. Checklist quyết định go/no-go

- [ ] New version đọc được session fixtures do old version tạo.
- [ ] Old version đọc được dữ liệu new version sẽ ghi trong thời gian rollback cần hỗ trợ, hoặc write mới vẫn bị tắt.
- [ ] SecurityContext, principal và authorities tương thích.
- [ ] Cookie name/domain/path/flags giữ đúng contract.
- [ ] Redis namespace hoặc JDBC schema không đổi ngoài migration đã kiểm thử.
- [ ] Serializer và custom session attributes có version/default strategy.
- [ ] TTL, expiration và cleanup behavior được kiểm tra.
- [ ] JDBC migration theo expand-contract và old binary vẫn hoạt động trong expand phase.
- [ ] Redis changes không phụ thuộc key layout nội bộ không được hỗ trợ.
- [ ] Mixed-version test đã chạy với repository thật.
- [ ] Concurrent update, session fixation, logout và cookie rotation đã được kiểm thử.
- [ ] Canary metrics và rollback thresholds đã được xác định.
- [ ] Có compatibility bridge hoặc phương án invalidate session được phê duyệt.
- [ ] Contract/destructive migration chỉ diễn ra sau rollback window và session retention window.

Rolling upgrade an toàn đòi hỏi các phiên bản cùng tồn tại phải hiểu session data mà phiên bản kia ghi. Hãy giữ ổn định cookie và repository scope, triển khai reader tương thích trước, duy trì write format giao nhau trong mixed-version window, rồi mới bật schema mới. Với Redis, không tự sửa key layout nội bộ; với JDBC, dùng expand-contract và trì hoãn DDL destructive. Rollback phải xét dữ liệu đã được phiên bản mới ghi, không chỉ binary image. Kiểm thử bằng fixtures cũ, Redis/JDBC thật, mixed-version requests, cookie round-trip, SecurityContext, TTL và concurrent updates trước khi phát hành. Chỉ contract format cũ sau khi old nodes đã dừng, rollback window kết thúc và session cũ đã hết hạn hoặc được migrate có kiểm soát.
