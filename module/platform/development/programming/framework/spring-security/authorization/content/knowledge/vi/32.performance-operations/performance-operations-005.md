# Thu hồi quyền, vô hiệu hóa cache và hiệu lực trên nhiều instance trong Spring Security

Khi quản trị viên thu hồi vai trò, loại một thành viên khỏi tổ chức hoặc vô hiệu hóa một tài khoản, **quyền đã thu hồi phải thực sự ngừng có hiệu lực ở mọi instance ứng dụng**. Đây vừa là bài toán **authorization** vừa là bài toán **nhất quán dữ liệu và vận hành**. Chỉ sửa bảng quyền trong database có thể chưa đủ: `Authentication` trong session còn giữ authorities cũ, JWT vẫn hợp lệ, một instance khác vẫn dùng cache quyền, hoặc một request đã vượt qua bước kiểm tra trước thời điểm thu hồi.

Bài tập trung vào Spring Security ở **servlet stack**, Java 17+ và các kiến trúc nhiều instance có database, Spring Cache, Spring Session/Redis hoặc OAuth2 Resource Server. Các đoạn cấu hình Spring được ghi rõ khi là **fragment cần tích hợp vào ứng dụng**; phần mô phỏng Java 17 ở mục 6 là một chương trình hoàn chỉnh, biên dịch/chạy bằng JDK thuần.

## 1. Xác định chính xác thứ phải thu hồi

“Thu hồi quyền” có nhiều nghĩa và cần xử lý ở những lớp khác nhau:

| Thao tác | Nguồn dữ liệu/cơ chế bị ảnh hưởng | Điều kiện đạt yêu cầu |
| --- | --- | --- |
| Bỏ vai trò `ADMIN` khỏi user | Quan hệ user–role; effective permissions | Mọi quyết định yêu cầu `ADMIN` về sau phải từ chối |
| Bỏ quyền `EXPORT` trong một tenant | Quan hệ user–tenant–permission; ACL | Không export được tenant đó, dù vẫn đăng nhập |
| Đổi owner của một tài nguyên | Bảng owner/ACL của resource | Chủ cũ không còn truy cập tài nguyên sau khi quyền chuyển |
| Khóa tài khoản | Trạng thái user; phiên đăng nhập/token | Không cho phép tiếp tục thực hiện thao tác được bảo vệ |
| Đăng xuất một thiết bị | HTTP session hoặc refresh/access token của thiết bị | Credential tương ứng không còn dùng được theo chính sách |
| “Đăng xuất tất cả thiết bị” | Mọi session/refresh token có liên quan; access token còn hạn | Thiết bị khác không thể tiếp tục gọi API bằng credential cũ |
| Thu hồi một access token | Trạng thái token (`jti`/opaque token) | Token bị từ chối dù chưa tới `exp`, nếu hệ thống cam kết revoke tức thì |

**Authentication** xác định request đến từ ai, còn **authorization** quyết định chủ thể đó có được phép thực hiện hành động trên tài nguyên cụ thể hay không. Một token hợp lệ về chữ ký chưa chắc chứa quyền còn hiệu lực tại thời điểm truy cập.

Ví dụ: lúc 10:00, `alice` có quyền `REPORT_EXPORT` tại tenant `shop-1`. Hai instance A và B đều tải danh sách quyền vào bộ nhớ. Lúc 10:05, admin bỏ quyền này trong database. Nếu instance A nhận sự kiện invalidate nhưng B bỏ lỡ, hai request giống nhau có thể nhận kết quả trái ngược: A từ chối, B vẫn cho export. Đây chính là lỗi **quyền cũ còn hiệu lực qua cache**.

### Cần định nghĩa “hiệu lực” trước khi chọn giải pháp

Hãy viết một cam kết kiểm thử được, chẳng hạn:

> Sau khi transaction thu hồi được commit, mọi **quyết định authorization mới** đối với thao tác xuất dữ liệu nhạy cảm phải dựa trên phiên bản quyền mới nhất. Request đã bắt đầu trước commit phải tuân theo quy tắc nhất quán riêng của nghiệp vụ.

Các yêu cầu vận hành nên làm rõ:

- “Ngay lập tức” có nghĩa là trước **request tiếp theo**, trong tối đa một số giây hay chỉ sau khi token hết hạn?
- Có cần ngăn những request đã qua bước authorization và **đang chạy** hay không?
- Khi hệ thống lưu quyền/Redis/database tạm thời không truy cập được, trả **503** để tránh cấp quyền sai hay có cho phép dùng cache cũ với giới hạn được phê duyệt?
- Thu hồi áp dụng cho **một user, một tenant, một resource, một session, một thiết bị** hay toàn bộ tài khoản?
- Có cần theo dõi 99th percentile của độ trễ lan truyền thu hồi và số lần cấp quyền bằng dữ liệu quá cũ?

Không nên dùng từ “revoke ngay” nếu thiết kế chỉ dựa vào TTL 15 phút.

## 2. Vì sao dữ liệu quyền bị cũ?

Đường đi phổ biến của một request:

~~~mermaid
flowchart LR
    U["Client + credential"] --> LB["Load balancer"]
    LB --> A["Instance A"]
    LB --> B["Instance B"]
    A --> CA["Cache quyền A"]
    B --> CB["Cache quyền B"]
    CA --> DB["DB/nguồn quyền chuẩn"]
    CB --> DB
    AD["Admin thu hồi"] --> DB
    DB --> EV["Outbox/Event"]
    EV -. "invalidate" .-> CA
    EV -. "invalidate" .-> CB
~~~

Trong luồng này có thể xuất hiện **nhiều bản sao dữ liệu**:

1. **Database/permission store**: nguồn quyền đáng tin, có transaction và bản ghi owner/role/ACL.
2. **Authorities trên `Authentication`**: được tính lúc login hoặc lúc giải mã token; không nhất thiết tự thay đổi sau khi role trong DB bị sửa.
3. **HTTP session**: có thể chứa `SecurityContext` được tạo trước lúc thu hồi.
4. **JWT access token**: thường chứa scope/role đã được ký; Resource Server mặc định xác thực chữ ký, issuer, thời gian, nhưng không tự biết database quyền đã đổi.
5. **Cache quyền trong JVM**, ví dụ Caffeine: mỗi node có một bản riêng; `@CacheEvict` chỉ tác động lên backend cache mà node đang dùng.
6. **Distributed cache**, ví dụ Redis: nhiều instance đọc chung một key, nhưng vẫn phải chú ý replica lag, local near-cache, TTL, write ordering và khả năng invalidate.
7. **Thông điệp sự kiện**: có thể đến chậm, lặp, sai thứ tự hoặc mất nếu chỉ dùng pub/sub không bền vững.

Thay đổi trong database **không tự động** cập nhật các bản sao này. Việc chọn cách đồng bộ phải phụ thuộc mức độ nhạy cảm của quyền và độ trễ chấp nhận được.

## 3. Phân biệt session, JWT và opaque token khi thu hồi

### 3.1. Ứng dụng dùng HTTP session

Khi authentication được lưu trong HTTP session, Spring Security có thể khôi phục `SecurityContext` qua các request. Sau khi quyền đổi, authorities trong session cũ **có thể vẫn là ảnh chụp tại thời điểm login** nếu ứng dụng không có cơ chế làm mới.

**Logout mặc định của Spring Security** xử lý session hiện tại bằng `SecurityContextLogoutHandler`, thường gồm vô hiệu hóa session và xóa security context; Spring cũng thực hiện các handler khác theo cấu hình. Tuy nhiên, logout **một session** không tự suy ra “đăng xuất mọi phiên trên mọi node”.

Với nhiều instance, có thể dùng **Spring Session** để lưu HTTP sessions trong Redis (hoặc kho dùng chung phù hợp), thay vì mỗi server giữ session riêng. Khi cùng một session ID được lưu ở kho trung tâm, xóa session ở nơi này có thể khiến lần đọc session **tiếp theo** từ node khác không lấy lại được authentication cũ. Cần kiểm thử chính xác session repository, các index, cache phụ và hành vi request đang chạy.

Mẫu Java sau **là một class hoàn chỉnh khi ứng dụng có dependency Spring Session và bean `FindByIndexNameSessionRepository` phù hợp**; dùng cho thao tác “hủy mọi session đã index theo principal”:

~~~java
package com.example.security;

import java.util.List;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

public final class UserSessionRevoker<S extends Session> {
    private final FindByIndexNameSessionRepository<S> sessions;

    public UserSessionRevoker(FindByIndexNameSessionRepository<S> sessions) {
        this.sessions = sessions;
    }

    public int revokeAll(String principalName) {
        // Snapshot danh sách ID để không sửa map trong lúc duyệt.
        List<String> ids = List.copyOf(
                sessions.findByPrincipalName(principalName).keySet());
        ids.forEach(sessions::deleteById);
        return ids.size();
    }
}
~~~

Các điều kiện tiên quyết rất quan trọng:

- Repository phải hỗ trợ `FindByIndexNameSessionRepository` (chẳng hạn implementation **indexed**, không mặc định mọi Spring Session repository có index).
- Index principal phải thực sự được tạo; nếu chưa được cấu hình, `findByPrincipalName` có thể trả rỗng dù có session.
- `principalName` phải khớp định danh được index, tránh nhầm username có thể đổi với user ID bất biến; thiết kế cách ánh xạ ID nhất quán.
- Hủy session **không làm một request đã đọc SecurityContext trước đó tự dừng**; cần kiểm tra lại quyền tại thời điểm thực hiện thao tác nhạy cảm nếu đây là yêu cầu nghiệp vụ.
- Session cache local hoặc sự kiện WebSocket phải được xử lý riêng nếu chúng duy trì quyền truy cập khác với HTTP request.

Nếu yêu cầu chỉ là bỏ quyền `EXPORT` mà user vẫn được phép đọc, có thể **giữ session** nhưng phải làm mới/đối chiếu quyền đúng cách. Hủy mọi session là chiến lược đơn giản hơn để bắt người dùng đăng nhập lại, nhưng gây gián đoạn và vẫn không xử lý access token độc lập.

### 3.2. Ứng dụng dùng JWT access token tự xác thực

JWT thường có `sub`, `iat`, `exp`, `iss`, có thể có `aud` và claims scope/role. Resource Server kiểm tra token tại mỗi request, nhưng **JWT đã ký vẫn hợp lệ cho đến hạn**, trừ khi ứng dụng bổ sung kiểm tra trạng thái thu hồi/phiên bản quyền hoặc có cơ chế chặn phù hợp.

Ví dụ `alice` có JWT với `scope=["reports:export"]`, `exp` sau 45 phút. Database bỏ quyền sau khi token được phát hành 1 phút. Nếu endpoint chỉ dùng:

~~~java
// Fragment phương thức Spring; cách này kiểm claim có thể đã cũ.
@PreAuthorize("hasAuthority('SCOPE_reports:export')")
public byte[] exportReport() {
    return reportService.export();
}
~~~

thì việc đổi role ở database **không tự xóa** authority `SCOPE_reports:export` trên authentication được tạo từ token cũ. `@PreAuthorize` vẫn đang áp dụng đúng **dữ liệu đầu vào cũ**, chứ không làm mới dữ liệu quyền.

Các phương án:

- **Access token ngắn hạn + không gia hạn quyền đã thu hồi**: giới hạn khoảng thời gian token cũ có thể dùng, nhưng không đáp ứng revoke tức thì.
- **Denylist `jti` hoặc token hash** trong kho dùng chung: request kiểm token có bị revoke không; giữ trạng thái chặn ít nhất đến hết vòng đời token và chú ý clock skew, issuer/audience.
- **Version/epoch quyền**: khi quyền thay đổi, tăng `authzVersion` trong nguồn chuẩn; JWT chứa phiên bản tại lúc phát hành. Resource Server đối chiếu JWT version với bản chuẩn ở các request cần bảo vệ, từ chối khi cũ.
- **Kiểm tra quyền theo tài nguyên trực tiếp ở service**: với thông tin owner/tenant/ACL đổi nhanh, đọc chính sách từ nguồn có tính nhất quán phù hợp thay vì chỉ xem claim.
- **Opaque token + introspection**: Resource Server hỏi authorization server về trạng thái token; nếu endpoint trả `active=false` thì token bị từ chối. Nếu introspection hoặc kết quả của nó được cache, thời gian hiệu lực của thu hồi lại phụ thuộc cache đó.

**Logout ở trình duyệt hoặc xóa cookie không tự thu hồi tất cả JWT đang tồn tại.** Cần xử lý access token và refresh token theo chính sách ở authorization server; access token đã phát hành có thể vẫn được nơi khác chấp nhận đến khi hết hạn hoặc được kiểm tra thu hồi.

Không dùng một hệ thống **local denylist** trên từng JVM nếu cần tác động tức thời trên nhiều node mà không có cơ chế đồng bộ đáng tin. Không log nội dung access token; nếu cần định danh trong log, dùng định danh đã hạn chế hoặc mã hash không thể đảo ngược.

### 3.3. Opaque token và introspection

Spring Security Resource Server hỗ trợ OAuth2 opaque token introspection. Mỗi lần introspection thành công, Resource Server dựa vào kết quả từ authorization server để quyết định token còn active hay không. Ưu điểm là trạng thái có thể thay đổi ở một nơi trung tâm; đổi lại là latency, sự phụ thuộc vào dịch vụ introspection và chi phí mỗi request.

Nếu bổ sung cache kết quả introspection để giảm tải, chính cache này trở thành **cửa sổ quyền cũ**. Cần đặt TTL rõ ràng hoặc invalidate khi revoke; với quyền nhạy cảm có yêu cầu tức thì, không được coi một phản hồi `active=true` từ cache cũ là bằng chứng quyền vẫn còn.

## 4. Chiến lược vô hiệu hóa cache quyền

### 4.1. Cache local trong từng instance

Với Caffeine/in-memory cache, instance A và B có hai bộ nhớ riêng. `@CacheEvict(cacheNames="permissions", key="...")` tại A không thể trực tiếp xóa entry ở B nếu mỗi node sử dụng cache in-memory.

~~~java
// Fragment tích hợp Spring Cache: các method ở các Spring bean.
@Service
class PermissionQueries {
    @Cacheable(cacheNames = "permissions", key = "#tenantId + ':' + #userId")
    public Set<String> findEffective(String tenantId, String userId) {
        return repository.loadEffectivePermissions(tenantId, userId);
    }
}

@Service
class PermissionEviction {
    @CacheEvict(cacheNames = "permissions", key = "#tenantId + ':' + #userId")
    public void evict(String tenantId, String userId) {
        // Spring Cache interceptor xử lý việc xóa cache.
    }
}
~~~

Đây là **fragment**, còn thiếu imports, fields và các bean phụ thuộc. Điều kiện vận hành:

- `@EnableCaching` phải có trong context; cả `@Cacheable` và `@CacheEvict` phải đi qua Spring proxy. Gọi `this.evict(...)` trong cùng object theo proxy mode thông thường có thể **bỏ qua advice**.
- Key phải đại diện đầy đủ cho **tenant + user** và các chiều có thể làm thay đổi kết quả: resource, action, chính sách, version. Tránh collision khi nối chuỗi không kiểm soát hoặc thay đổi định dạng ID.
- Với local cache, cần sự kiện tới **mọi node** và đường fallback khi mất sự kiện. `@CacheEvict` không tự cung cấp cơ chế broadcast.
- `@CacheEvict` sau khi method hoàn thành thành công là mặc định; `beforeInvocation=true` khác về thời điểm. Dù vậy annotation không biến database update và cache invalidate thành một transaction phân tán nguyên tử.

### 4.2. Cache dùng chung

Redis-backed Spring Cache có thể cho nhiều instance cùng đọc/xóa một key; điều này giảm vấn đề mỗi node giữ một bản quyền riêng. Tuy nhiên vẫn cần kiểm tra:

- Có **near-cache** hay map local nào đọc trước Redis không?
- Key được xóa sau **commit** dữ liệu quyền hay trước commit?
- Redis replica đọc trễ có trả giá trị cũ sau khi primary đã xóa?
- Khi cache miss đồng thời, một request cũ có thể tải quyền **trước commit** rồi điền lại cache **sau khi xóa** hay không?
- Nếu cache hoặc event bus không sẵn sàng, hệ thống xử lý theo mô hình nhất quán nào?

Chỉ chuyển từ Caffeine sang Redis **không đủ** để cam kết quyền mới có hiệu lực ngay nếu toàn bộ chuỗi cập nhật/vô hiệu hóa chưa được chứng minh đúng.

### 4.3. TTL định kỳ

Dùng TTL có thể giới hạn thời gian quyền cũ còn tồn tại **trong điều kiện cache luôn tuân thủ TTL**, nhưng TTL không đồng bộ với commit:

- Cache có TTL 10 phút: một entry được tạo **ngay trước** khi thu hồi có thể còn hợp lệ gần 10 phút.
- TTL 30 giây: giảm cửa sổ nhưng có thể tăng query tới database, đặc biệt khi lưu quyền riêng cho nhiều user/tenant.
- TTL “sliding/expire-after-access” có thể kéo dài tuổi entry khi người dùng liên tục truy cập; không dùng để khẳng định giới hạn tuyệt đối nếu cấu hình không có expire-after-write phù hợp.

TTL là **lưới an toàn** cho event bị mất, không nhất thiết là lời giải duy nhất cho quyền bắt buộc có hiệu lực tức thời.

### 4.4. Cache theo phiên bản quyền

Thiết kế nguồn dữ liệu có `authz_version` tăng đơn điệu cho mỗi user hoặc mỗi user–tenant, đồng thời cập nhật phiên bản **cùng transaction** với thay đổi quyền.

~~~text
subject_key       authz_version   permissions
shop-1:alice      41             {REPORT_VIEW, REPORT_EXPORT}
   -> REVOKE REPORT_EXPORT + version tăng thành 42
shop-1:alice      42             {REPORT_VIEW}
~~~

Khi xây dựng cache, lưu `PermissionSnapshot(version, grants)`. Với quyết định nhạy cảm, đọc phiên bản hiện tại từ nguồn **đủ tin cậy**:

1. Đọc `currentVersion` (ưu tiên transactional/primary nếu cần tính nhất quán mạnh).
2. Nếu snapshot local có version thấp hơn hoặc khác currentVersion, tải lại quyền mới.
3. Chỉ cấp quyền dựa trên snapshot có phiên bản hiện hành.
4. Nếu không lấy được version đáng tin và hành động có rủi ro cao, từ chối/không thực thi (ví dụ trả 503 khi phụ thuộc authorization lỗi), thay vì dùng stale-allow.

**Bất biến bắt buộc:** thay đổi có thể ảnh hưởng authorization **luôn tăng phiên bản**, và snapshot quyền phải đi kèm với version tương ứng một cách nguyên tử. Nếu đọc version mới nhưng đọc permissions từ replica cũ, hệ thống có thể gắn sai version lên dữ liệu cũ. Cần đọc một snapshot nhất quán hoặc dùng cơ chế transaction phù hợp.

Version-check ở mọi request tăng chi phí tới authority store; có thể phân loại endpoint: thao tác tài chính/export/admin kiểm tra mạnh, endpoint ít rủi ro sử dụng TTL có giới hạn đã định. Đừng tuyên bố “revoke ngay” nếu version đọc từ một cache độc lập có thể cũ.

### 4.5. Event-driven invalidation, outbox và reconciliation

Luồng đáng tin hơn khi admin revoke:

~~~text
Admin request
   -> Transaction: cập nhật role/ACL + tăng authz_version + ghi outbox
   -> COMMIT
   -> Outbox dispatcher phát PermissionsChanged(subject, version)
   -> Mỗi node xóa local cache/near-cache liên quan
   -> Mọi request nhạy cảm vẫn đối chiếu version authoritative
~~~

Vì sao outbox? Nếu ghi DB thành công nhưng phát message thất bại, event có thể mất. Ghi outbox **trong cùng transaction** rồi phát lại giúp giảm khoảng trống này. Consumer phải idempotent, chịu message trùng/lặp và phiên bản đến sai thứ tự.

Sự kiện nên chứa **ID định danh + tenant + version + loại thay đổi**, không cần chứa dữ liệu nhạy cảm hoặc toàn bộ quyền. Consumer chỉ nên invalidate khi event mới hơn snapshot đã biết; nếu event cũ đến muộn, không được hồi phục quyền hoặc ghi đè version mới bằng version thấp hơn.

Trong Spring, `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` giúp callback xử lý sự kiện **sau commit trên cùng ứng dụng**, nhưng **không phải message bus bền vững** và không đảm bảo các node khác nhận được. Dùng nó làm trigger nội bộ có thể phù hợp; để chịu crash giữa commit và publish, cần outbox/replay hoặc cơ chế có tính bền vững tương đương.

Với Redis Pub/Sub, một subscriber offline có thể bỏ lỡ message. Nếu yêu cầu audit/replay, cân nhắc hàng đợi durable và thường xuyên đối chiếu `authz_version`; pub/sub có thể vẫn dùng làm tối ưu giảm trễ.

## 5. Quy trình thu hồi end-to-end và cửa sổ race

Giả sử yêu cầu gỡ quyền `REPORT_EXPORT` ở `shop-1` khỏi `alice`:

| Mốc | Thành phần | Hành vi | Rủi ro cần kiểm |
| --- | --- | --- | --- |
| T0 | A và B | Cache quyền cũ version 41 | Cả hai đang cho export |
| T1 | Admin + DB | Transaction đổi quyền, version 42, outbox; commit | Không được phát version mới trước khi dữ liệu commit |
| T2 | Dispatcher | Phát sự kiện version 42 | Message có thể chậm, trùng hoặc mất |
| T3 | A | Nhận event, invalidate cache | A từ chối request mới |
| T4 | B | Chưa nhận event, local cache version 41 | Nếu chỉ tin cache, B vẫn cho export |
| T5 | B | Kiểm currentVersion=42 tại nguồn chuẩn | B bỏ bản cũ và từ chối |
| T6 | Monitor | Ghi nhận thời gian hội tụ | Phải phát hiện node không hội tụ hoặc không nhận event |

**Đặc biệt: request đang chạy.** Một request có thể qua bước kiểm quyền ở T0.9, rồi admin commit thu hồi ở T1, sau đó request mới ghi vào DB ở T1.1. Muốn đảm bảo thao tác ghi không thể commit sau khi quyền bị thu hồi, cần chính sách giao dịch cụ thể: khóa phù hợp, optimistic locking/version conditional write, hoặc kiểm quyền trong cùng transaction với thao tác dữ liệu. Kiểm tra ở filter lúc request bắt đầu chỉ có thể bảo vệ **thời điểm đó**, không tự đảm bảo tính nguyên tử với thao tác ghi về sau.

**Thứ tự invalidation:** “xóa cache trước rồi commit DB” dễ xảy ra cache miss đọc lại dữ liệu cũ và repopulate. “commit DB rồi invalidate” cũng có khoảng trễ giữa hai bước. Outbox + version guard làm đường chủ đạo, invalidate đóng vai trò giảm latency và tải.

**Thêm quyền trở lại:** Khi admin cấp lại quyền đã thu hồi, tạo version mới (43). Event cũ version 42 đến sau event 43 không được khiến cache quay về một trạng thái lịch sử hoặc tự suy ra 42 là phiên bản hiện tại. Với mô hình lấy quyền lại từ DB theo version, chỉ bản mới nhất được phép quyết định.

## 6. Mô phỏng chạy được bằng Java 17: hai instance và sự kiện bị mất

Chương trình này **không cần Spring hay Redis**, vì mục tiêu là làm rõ một tính chất của hệ phân tán: hai instance có local cache riêng sẽ đưa ra kết quả khác nhau nếu chỉ một node nhận invalidation. `PermissionDirectory` đại diện cho nguồn quyền dùng chung; `Node` đại diện JVM A/B. Trong ứng dụng thật, nguồn chung là DB/authorization store với transaction và mức nhất quán phù hợp.

Tạo file **`RevocationDemo.java`** (tên file trùng với public class):

~~~java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class RevocationDemo {
    record Snapshot(long version, Set<String> permissions) {
        Snapshot {
            permissions = Set.copyOf(permissions);
        }
    }

    static final class PermissionDirectory {
        private final Map<String, Snapshot> current = new ConcurrentHashMap<>();

        void initialize(String subject, Set<String> grants) {
            current.put(subject, new Snapshot(1, grants));
        }

        Snapshot read(String subject) {
            // Demo: đọc snapshot nguyên tử từ nguồn dùng chung.
            return current.getOrDefault(subject, new Snapshot(0, Set.of()));
        }

        Snapshot revoke(String subject, String permission) {
            return current.compute(subject, (key, old) -> {
                if (old == null) {
                    throw new IllegalArgumentException("Unknown subject: " + key);
                }
                Set<String> next = new HashSet<>(old.permissions());
                next.remove(permission);
                // Cập nhật quyền và version như một snapshot bất biến.
                return new Snapshot(old.version() + 1, next);
            });
        }
    }

    static final class Node {
        private final String name;
        private final PermissionDirectory directory;
        private final Map<String, Snapshot> local = new ConcurrentHashMap<>();

        Node(String name, PermissionDirectory directory) {
            this.name = name;
            this.directory = directory;
        }

        boolean localOnly(String subject, String permission) {
            // CỐ Ý SAI cho quyền cần hiệu lực tức thì:
            // cache cũ không được làm mới nếu node bỏ lỡ event.
            Snapshot snapshot = local.computeIfAbsent(subject, directory::read);
            return snapshot.permissions().contains(permission);
        }

        boolean withVersionGuard(String subject, String permission) {
            Snapshot authoritative = directory.read(subject);
            Snapshot cached = local.get(subject);
            if (cached == null || cached.version() != authoritative.version()) {
                local.put(subject, authoritative);
                cached = authoritative;
            }
            return cached.permissions().contains(permission);
        }

        void onPermissionsChanged(String subject, long newVersion) {
            // Xóa bản cũ; event không chứa danh sách quyền.
            local.computeIfPresent(subject, (key, cached) ->
                cached.version() < newVersion ? null : cached);
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        PermissionDirectory source = new PermissionDirectory();
        String subject = "shop-1:alice";
        String action = "REPORT_EXPORT";
        source.initialize(subject, Set.of(action, "REPORT_VIEW"));

        Node a = new Node("A", source);
        Node b = new Node("B", source);

        System.out.println("Before: A=" + a.localOnly(subject, action)
                + ", B=" + b.localOnly(subject, action));

        Snapshot changed = source.revoke(subject, action);
        System.out.println("After revoke, no event: A=" + a.localOnly(subject, action)
                + ", B=" + b.localOnly(subject, action));

        // Mô phỏng B tạm mất kết nối event bus.
        a.onPermissionsChanged(subject, changed.version());
        System.out.println("Event delivered only to A: A=" + a.localOnly(subject, action)
                + ", B=" + b.localOnly(subject, action));

        System.out.println("With version check: A=" + a.withVersionGuard(subject, action)
                + ", B=" + b.withVersionGuard(subject, action));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RevocationDemo.java
java RevocationDemo
~~~

**Stdout chính xác**:

~~~text
Before: A=true, B=true
After revoke, no event: A=true, B=true
Event delivered only to A: A=false, B=true
With version check: A=false, B=false
~~~

Phân tích:

1. Ban đầu A và B nạp quyền version 1.
2. `source.revoke` tăng version 2, gỡ `REPORT_EXPORT`; **cả hai local cache vẫn là version 1**.
3. Chỉ A nhận event nên A xóa cache và đọc lại version 2; B tiếp tục cho phép vì dùng cache cũ.
4. `withVersionGuard` đọc version authoritative trước khi quyết định; B phát hiện version khác và nạp bản mới, do đó từ chối.

**Giới hạn của mô phỏng:** `ConcurrentHashMap` trong cùng tiến trình chỉ đại diện cho source chung, không mô phỏng crash, network partition, replica lag hay transaction DB. Đọc version rồi quyết định cũng vẫn có race nếu quyền đổi **sau** lần đọc. Muốn bảo đảm thao tác ghi không commit sai sau revoke, dùng cơ chế nhất quán ở tầng transaction. Không chép `localOnly` vào hệ thống production cho quyền nhạy cảm.

## 7. Triển khai chính sách authorization với Spring Security

### 7.1. Quyền đang có hiệu lực phải được xác minh ở đúng thời điểm

Một phương thức Spring Security có thể gọi bean policy kiểm trạng thái hiện tại:

~~~java
// Fragment minh họa, đặt trong Spring service bean.
@PreAuthorize("@exportPolicy.canExport(authentication, #tenantId)")
public byte[] export(@P("tenantId") String tenantId) {
    return reportExporter.buildReport(tenantId);
}
~~~

`@P` có kiểu `org.springframework.security.access.method.P` để tên `#tenantId` không phụ thuộc cờ compiler. Bean `exportPolicy` phải dùng đúng nguồn quyền của tenant hiện tại:

~~~java
// Fragment: policy có repository/authority-store đã inject.
public boolean canExport(Authentication auth, String tenantId) {
    if (auth == null || !auth.isAuthenticated()) {
        return false;
    }
    String subject = auth.getName();
    return permissions.existsCurrentGrant(
            tenantId, subject, "REPORT_EXPORT");
}
~~~

**Không được tự giả định** `auth.getName()` là ID user bất biến trong mọi hệ thống: với JWT, mặc định có thể là `sub`; với principal tùy chỉnh có thể là username. Chọn và kiểm thử phép ánh xạ chính xác theo hệ thống xác thực thật.

Nếu biểu thức chỉ dùng `hasAuthority("REPORT_EXPORT")` trên `Authentication` đã được tạo từ một session/JWT cũ, thì Spring Security thực thi điều kiện đó đúng nhưng **không thể biết** grant đã bị thu hồi sau khi `Authentication` được tạo. Policy cần quyền cập nhật hoặc cơ chế version/session/token invalidation tương đương.

Với tài nguyên cụ thể, kiểm tra cả **tenant, resource owner và action**, không chỉ quyền toàn cục. Ví dụ user vẫn có quyền export ở `shop-2` nhưng đã bị thu hồi ở `shop-1`.

### 7.2. Quy trình cập nhật quyền và phát sự kiện

Trong service quản trị, thay đổi grant và tăng version **cùng transaction**; outbox record cũng nằm trong transaction đó:

~~~java
// Fragment kiến trúc; các repository, entity và outbox là thành phần
// do ứng dụng cài đặt, không phải API có sẵn của Spring Security.
@Transactional
public void revokeExport(String tenantId, String userId) {
    grants.deleteGrant(tenantId, userId, "REPORT_EXPORT");
    long version = grants.incrementAuthzVersion(tenantId, userId);
    outbox.insert(new PermissionsChanged(tenantId, userId, version));
}
~~~

Dispatcher đọc outbox, phát event và đánh dấu đã xử lý **sau khi** broker xác nhận; nếu thất bại, retry. Consumer xử lý event theo ít nhất một lần (at-least-once) và idempotent. Không đẩy quyền nhạy cảm đầy đủ vào payload event.

Nếu cập nhật bị rollback, **không** phát event khẳng định quyền đã đổi. Nếu có thay đổi khác commit sau đó, version mới hơn phải thắng khi so sánh; không suy đoán trạng thái từ event đến cuối cùng.

### 7.3. Đồng bộ cache: event làm nhanh, version bảo đảm

Kiến trúc vận hành có thể phân hai đường:

- **Fast path:** sau commit, outbox/broker phát event → mọi node chủ động invalidate local/near-cache.
- **Safety path:** mọi quyết định nhạy cảm kiểm version/ACL từ nguồn đủ nhất quán; nếu event mất, request vẫn phát hiện quyền đã cũ.

Nếu chính sách cho phép trễ tối đa (ví dụ tài liệu chỉ public read), có thể dùng TTL kết hợp event thay vì source-check mỗi request, nhưng phải **ghi rõ cửa sổ** và đo nó. Với quyền admin, thanh toán hoặc export dữ liệu nhạy cảm, không lấy TTL làm cam kết thu hồi tức thì.

### 7.4. Xử lý khi kho quyền hoặc Redis lỗi

Nếu một request không đọc được quyền authoritative, lựa chọn là một **quyết định sản phẩm/bảo mật** đã được định nghĩa trước:

- Đối với hành động nguy cơ cao, dùng **fail closed**: không thực hiện hành động; có thể trả 503 khi cơ chế kiểm tra quyền bị lỗi, tránh trả dữ liệu nhạy cảm.
- Đối với một số thao tác chỉ đọc rủi ro thấp, dùng cache có tuổi tối đa được chấp nhận và cảnh báo rõ trạng thái suy giảm nếu chính sách cho phép.
- Không âm thầm thay `AuthorizationDecision.DENY` bằng `ALLOW` chỉ vì quyền store timeout.
- Phân biệt **deny hợp lệ** (403) với **dependency outage** (thường 503); monitoring và điều tra sự cố sẽ chính xác hơn.

Không nên chỉ dựa vào vòng đời cache in-memory để xác định thời gian quyền thu hồi. Khi instance restart, cache mất; nhưng khi node B đang sống, cache của nó có thể tồn tại dài hơn.

## 8. Kiểm thử khi chạy nhiều instance

Một unit test chỉ gọi `cache.evict(user)` rồi xác nhận một map rỗng chứng minh rất ít. Cần test **hành vi authorization đầu ra** với ít nhất hai instance/contexts thật, dùng các session/token và nguồn quyền phù hợp.

### Ma trận tối thiểu

| Tình huống | Hành động | Kỳ vọng |
| --- | --- | --- |
| Trước revoke | A/B có `EXPORT` hợp lệ | Cả hai cho phép |
| Sau DB commit | Revoke từ A, gọi API ở B bằng credential cũ | B từ chối theo SLA |
| Event chỉ đến A | Chặn/delay consumer của B | B vẫn từ chối nếu cần version check tức thì |
| Event trùng | Gửi cùng version nhiều lần | Kết quả ổn định, không cấp lại |
| Event sai thứ tự | Gửi version 12 sau version 13 | Không rollback trạng thái về 12 |
| Regrant | Revoke rồi cấp lại, tăng version | Chỉ version mới được cho phép |
| Session khác cùng user | Login hai browser/node khác nhau, “logout all” | Cả hai session bị thu hồi theo chính sách |
| JWT cũ | Dùng JWT `exp` còn hạn sau revoke | Bị từ chối nếu yêu cầu immediate revoke |
| Opaque token | Introspection trả `active=false` | Resource Server từ chối |
| Cache miss + commit race | Đang nạp quyền cũ khi commit xảy ra | Không ghi đè cache mới bằng quyền cũ |
| Request đang ghi | Bắt đầu trước revoke, commit sau revoke | Kết quả theo ràng buộc transaction đã chọn |
| Network partition | B không nhận event và không đọc được store | Không cấp quyền nhạy cảm từ dữ liệu không xác minh |
| Instance mới | C xuất hiện sau revoke | Không tải lại quyền cũ từ replica/cache |
| Tenant tách biệt | Revoke `shop-1`, vẫn giữ `shop-2` | Chỉ ảnh hưởng grant đúng tenant |

### Mẫu kịch bản integration test

Với Docker Compose/Testcontainers (nếu hệ thống thật dùng Postgres/Redis/broker), khởi chạy **hai application instances cùng chia sẻ DB/Redis**. Thực hiện:

~~~text
1. Gán Alice quyền EXPORT tại tenant X, version 7.
2. Đăng nhập/phát token, gửi GET/POST được bảo vệ qua instance A và B.
3. Bảo đảm cả hai cache đã được warm-up.
4. Admin tại A revoke EXPORT và commit version 8.
5. Giả lập B bỏ lỡ event, hoặc delay consumer/invalidate.
6. Gọi cùng credential cũ qua B và A; kiểm trạng thái 403 hoặc
   lỗi authorization đã định nghĩa, và xác nhận không xuất dữ liệu.
7. Đưa B nhận event trùng và event version 7 đến muộn; gọi lại.
8. Regrant quyền với version 9; kiểm rằng quyền chỉ có hiệu lực
   sau khi policy/version được cập nhật đúng.
9. Khởi động instance C mới; kiểm không có quyền cũ.
10. Thu thập thời gian từ COMMIT đến thời điểm mỗi node từ chối.
~~~

**Không dùng `@WithMockUser` như bằng chứng kiểm thử end-to-end JWT/session revocation.** Annotation này dựng sẵn authentication cho test, bỏ qua quy trình phát hành/đọc token hoặc session thực. Nó rất hữu ích để test logic policy, nhưng phải có integration test dùng credential thực trong loại cơ chế cần kiểm tra.

Nếu dùng MockMvc test `@PreAuthorize`, inject bean do Spring quản lý để lời gọi đi qua method-security proxy và bật `@EnableMethodSecurity`. Nếu test toàn bộ request, kiểm tra đúng `SecurityFilterChain` và các cơ chế CSRF/filter khác để không nhầm 403 do CSRF với 403 do đã thu hồi quyền.

### Kiểm tra điều kiện bảo toàn dữ liệu

Với các thao tác nhạy cảm, test cả trạng thái hệ thống:

~~~java
// Fragment assertion, dùng với test framework phù hợp.
assertThat(response.getStatus()).isEqualTo(403);
assertThat(exportStore.countExportsFor("shop-1", "alice"))
        .isEqualTo(0);
~~~

Đây **không** phải đoạn code độc lập: `response` và `exportStore` là fixture của integration test. Ý chính là xác nhận **không có side effect** sau khi authorization bị từ chối, kể cả khi bước kiểm tra quyền chạy ở node khác.

## 9. Giám sát, SLO và xử lý sự cố

Nên theo dõi ít nhất các chỉ số:

- **Revocation-to-enforcement latency:** thời gian từ DB commit đến khi một request mới chắc chắn bị từ chối trên từng node; đo p50/p95/p99 và cực đại theo chính sách.
- **Event delivery lag/outbox backlog:** message chưa phát, retry, dead-letter, consumer lag, số node chưa nhận version mới.
- **Age/version của permission cache:** số entry thấp hơn authoritative version, tỉ lệ hit/miss, tần suất invalidation, cache refills cũ.
- **Trạng thái JWT/session:** số session đã hủy; token cũ bị từ chối; số request 401/403/503, phân tách theo nguyên nhân.
- **Dependency latency và availability:** database permission lookup, Redis/session store, introspection endpoint, message broker.
- **Sự kiện quyền:** audit ai thực hiện revoke, đối tượng, tenant, quyền, version trước–sau, thời điểm commit và correlation ID.

Không log raw token, session ID hay nội dung permission nhạy cảm. Với user/tenant ID trong log, tuân thủ chính sách bảo vệ dữ liệu và phân quyền truy cập log.

Ví dụ một mục tiêu đo được là “100% request export **bắt đầu authorization sau commit** phải kiểm tra permission version mới nhất từ nguồn chuẩn; nếu kiểm tra thất bại thì không export”. Mục tiêu này mạnh hơn “event delivered within 1 second”: nhận event nhanh chưa chứng minh tất cả quyết định quyền sau đó dùng dữ liệu mới.

Với mô hình chỉ có TTL 60 giây và không có kiểm tra authoritative khác, **không** thể chứng nhận SLA 1 giây. Để chứng minh giới hạn, tính tất cả nguồn trễ thực tế: TTL, replica lag, event backlog, token lifetime, quá trình reload, đồng hồ và các request đang chạy. Nếu chỉ một tầng có thể giữ quyền cũ 20 phút, các tầng nhanh hơn không tự làm mất cửa sổ đó.

### Runbook khi nghi có node vẫn cấp quyền cũ

1. Xác định thời điểm commit và version quyền hiện tại trong nguồn chuẩn.
2. So sánh version cache/session/token đã được dùng cho request đáng ngờ, kiểm log với correlation ID.
3. Kiểm node, filter chain, policy/method-security path và cache provider đang xử lý request.
4. Kiểm outbox backlog, consumer lag, subscriber restart, retry và khả năng miss event.
5. Nếu nguy cơ cao, tạm dừng hành động nhạy cảm bằng biện pháp an toàn đã thiết kế trong hệ thống, đồng thời khôi phục đường xác minh authoritative.
6. Sau khắc phục, chạy lại integration test 2+ instances và xác minh SLO hội tụ; bổ sung kiểm thử phản ví dụ vừa phát hiện.

## 10. Sai sót thường gặp

**“Đã đổi bảng user_role nên quyền đã mất.”** `Authentication` hoặc JWT có thể chứa authorities được snapshot trước đó. Cần refresh/revoke token, session hoặc dùng dynamic authorization.

**“Đã chạy `@CacheEvict` là mọi instance mất cache.”** Điều này chỉ đúng với phạm vi mà `CacheManager` và backend cung cấp. Local JVM cache không tự lan sang node khác; Spring Cache abstraction không tự xây event bus.

**“Chỉ cần Redis Pub/Sub.”** Subscriber mất kết nối có thể bỏ lỡ sự kiện. Cần TTL, version read, durable bus/replay hoặc kết hợp tùy SLA; với hệ thống rủi ro cao, version/authoritative check là đường kiểm soát chính.

**“Xóa cache trước transaction commit để an toàn.”** Node khác có thể cache miss và tải quyền cũ trong transaction chưa commit, sau đó repopulate. Thiết kế cần xét ordering, transaction và version.

**“Có version nên cache luôn chính xác.”** Nếu đọc version từ replica trễ hoặc quên tăng version trên một code path cập nhật ACL, kết luận vẫn sai. Phải xác minh bất biến và đường đọc nhất quán.

**“Logout trên node A làm JWT không còn dùng được trên B.”** Logout session và JWT revocation là hai cơ chế khác nhau; access token tự xác thực vẫn có thể hợp lệ tới `exp` nếu không có chặn bổ sung.

**“Thu hồi chắc chắn chặn được request đã bắt đầu.”** Bước kiểm quyền có thể xảy ra trước commit thu hồi, còn tác dụng phụ xảy ra sau. Những thao tác có yêu cầu nghiêm ngặt cần transaction/locking/conditional update, không chỉ middleware.

**“Tắt cache hoàn toàn là đủ.”** Nếu token/session chứa authorities cũ, hoặc DB đọc từ replica trễ, vẫn có nguồn dữ liệu quyền cũ ngay cả khi không dùng Spring Cache.

## 11. Checklist nghiệm thu

- [ ] Xác định rõ thu hồi **role, tenant grant, resource ACL, session, token** hay trạng thái account.
- [ ] Viết SLA cụ thể: từ thời điểm commit tới **quyết định authorization mới** trên tất cả instance.
- [ ] Từng thay đổi quyền cập nhật snapshot và version một cách nhất quán/atomic.
- [ ] Kiểm tra cả authorities lưu trong `Authentication`, JWT, refresh token và HTTP session.
- [ ] `@CacheEvict` chạy qua Spring proxy và đúng backend; cache key bao gồm tenant/user/action/resource cần thiết.
- [ ] Có chiến lược cho multi-node local caches và message bị trễ/mất/sai thứ tự.
- [ ] Event chỉ là tối ưu; đường kiểm soát chính đáp ứng SLA kể cả khi subscriber bị offline.
- [ ] Khi cache/store không dùng được, không tự cấp quyền nhạy cảm theo snapshot chưa xác minh.
- [ ] Test hai hay nhiều instance với credential cũ trước/sau revoke.
- [ ] Test token chưa hết hạn, session ở thiết bị khác, quyền được cấp lại, node mới khởi động.
- [ ] Test **không xảy ra side effect** sau khi bị từ chối; kiểm race đối với thao tác ghi cần tính nguyên tử.
- [ ] Có audit và metrics để chứng minh thời gian hiệu lực, không chỉ xác nhận message đã gửi.

## 12. Tài liệu đối chiếu

- Spring Security — Handling Logouts: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Opaque Token: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Session — Redis with Spring Boot: https://docs.spring.io/spring-session/reference/guides/boot-redis.html
- Spring Session — `FindByIndexNameSessionRepository` API: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html
- Spring Framework — Cache annotations (`@Cacheable`, `@CacheEvict`): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html

**Kết quả cần đạt:** Sau khi admin thu hồi quyền, một request mới tới **bất kỳ** instance nào cũng thực thi chính sách hiệu lực đã cam kết; event bị mất hoặc cache cục bộ còn dữ liệu cũ không thể âm thầm cấp phép cho hành động nhạy cảm. Với session/JWT, phải nêu rõ loại credential nào bị thu hồi, khi nào hết hiệu lực và cơ chế nào bảo đảm điều đó.
