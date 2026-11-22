# Chính sách bộ nhớ đệm, thu hồi và tính nhất quán khi dữ liệu thay đổi

**Module:** Spring Security – authentication. **Nhóm kiến thức:** Kho tài khoản.

## 1. Bài toán: dữ liệu tài khoản thay đổi, nhưng hệ thống đang giữ bản cũ

Giả sử người dùng `an` đăng nhập lúc 09:00 với `ROLE_ADMIN`. Lúc 09:05, quản trị viên thu hồi quyền admin. Cơ sở dữ liệu đã lưu `ROLE_USER`, nhưng người dùng vẫn đang có HTTP session với `Authentication.getAuthorities()` chứa `ROLE_ADMIN`. Nếu có cache `UserDetails`, một lần xác thực mới cũng có thể đọc bản cũ. Nếu client dùng JWT còn hiệu lực, thông tin role trong token đã ký không tự thay đổi khi database cập nhật.

Vì vậy, câu hỏi **“đã cập nhật tài khoản trong DB rồi, sao quyền chưa đổi?”** thực chất có nhiều lớp:

- Bản ghi trong **kho tài khoản** (JDBC/JPA/LDAP/IdP) có đúng và đã commit chưa?
- **Cache `UserDetails`** có còn snapshot username, password hash, flags và authorities cũ không?
- **`SecurityContext` trong session** có chứa `Authentication` từ lần đăng nhập trước không?
- **Access token hoặc refresh token** đã phát hành còn hiệu lực không?
- Các **node khác**, CDN/gateway, lớp authorization và các request đang chạy có nhìn cùng một phiên bản không?

**Nguyên tắc:** Cache giúp giảm chi phí truy vấn, còn thu hồi (revocation) và tính nhất quán (consistency) là một **chính sách bảo mật xuyên nhiều lớp**. Chỉ gọi `cache.evict(username)` không thể tự thu hồi session, refresh token, JWT hay quyền đã được quyết định trong một request đang chạy.

Bài này tập trung vào **kho tài khoản phục vụ xác thực Spring Security**, cách áp dụng cache có kiểm soát, các sự kiện làm dữ liệu mất hiệu lực, cơ chế thu hồi và cách kiểm chứng độ trễ nhất quán.

## 2. Phân biệt năm lớp dữ liệu có thể bị cũ

| Lớp | Chứa gì? | Được đọc khi nào? | Cách làm mới/thu hồi |
| --- | --- | --- | --- |
| **Kho gốc** (DB/LDAP/IdP) | Username, hash, trạng thái, quyền, phiên bản thay đổi | Khi service hoặc provider truy vấn nguồn | Transaction commit, đồng bộ replica, giải quyết xung đột |
| **`UserDetails` cache** | Thông tin tải cho `UserDetailsService` / `AuthenticationProvider` | Khi đăng nhập/xác thực lại tùy cơ chế | Evict theo identity, TTL, version, invalidation event |
| **HTTP session / `SecurityContext`** | `Authentication` đã xác thực cùng authorities | Request kế tiếp sử dụng session | Logout, invalidate/expire session, refresh/re-authentication và policy request-time |
| **Access token** (JWT/opaque) | `sub`, scopes/roles, `exp`, `jti` hoặc reference ID | Mỗi request bearer theo cấu hình | JWT: hết hạn/denylist/version check; opaque: introspection/revoke ở server |
| **Cache ủy quyền/nghiệp vụ** | ACL, tenant membership, kết quả kiểm tra permission | Khi service cần authorize đối tượng | Evict theo resource/tenant/user, TTL, request-time revalidation |

**Dữ liệu authoritative (nguồn sự thật) phải được xác định rõ**: với ứng dụng có DB account nội bộ, DB có thể là authoritative cho trạng thái enabled/roles; với SSO, IdP có thể là nguồn xác thực, còn quyền domain nằm ở DB ứng dụng. Không được tự suy ra `JWT.roles` luôn là nguồn quyền mới nhất.

### Một sơ đồ vòng đời

~~~text
Admin đổi quyền / khóa tài khoản / đổi mật khẩu
                     |
                     v
             Account service
                     |
                     v
       UPDATE DB + authVersion++
                     |
                     v
              COMMIT thành công
                     |
          +----------+-----------+
          |          |           |
          v          v           v
     Cache evict   Session     Token policy
     / reload      revoke      denylist/version
          |          |           |
          +----------+-----------+
                     |
                     v
        Kiểm tra lại ở request sau
          (có thể thêm kiểm tra DB
           khi thao tác rủi ro cao)
~~~

Mỗi nhánh có thời gian lan truyền và cơ chế thất bại riêng. Nếu nghiệp vụ cần thu hồi trong vài giây, phải định nghĩa và kiểm thử **ngân sách trễ thu hồi**; TTL 15 phút không thể là lời bảo đảm “thu hồi gần tức thì”.

## 3. Cache `UserDetails` trong Spring Security vận hành ra sao?

### 3.1. `UserDetailsService` và `DaoAuthenticationProvider`

Trong luồng username/password thường gặp:

1. Filter tạo `UsernamePasswordAuthenticationToken` chưa xác thực từ username và raw password.
2. `ProviderManager` chọn `DaoAuthenticationProvider`.
3. Provider nạp `UserDetails` từ `UserDetailsService` hoặc cache nếu đã cấu hình.
4. `PasswordEncoder.matches(rawPassword, storedHash)` và các kiểm tra trạng thái account xác định thành công/thất bại.
5. Provider trả `Authentication` đã xác thực, với authorities từ nguồn được tin cậy.
6. Web filter lưu `SecurityContext` cho request/session theo cấu hình.

`AbstractUserDetailsAuthenticationProvider` cung cấp giao diện `setUserCache(UserCache)`. **Mặc định là `NullUserCache`**: không có cache người dùng thực sự trong provider thông thường. Lý do: với ứng dụng session-based, không cần truy vấn DB để xác thực lại ở **mọi request**; server thường khôi phục `SecurityContext` từ session.

Do đó, hãy đo trước khi bật cache. Không tự gắn Redis/Ehcache vào auth chỉ vì “request nào cũng cần lấy UserDetails”: với session thông thường, nhận định đó không đúng theo mặc định.

### 3.2. `UserCache` có ba thao tác cơ bản

~~~java
// Chữ ký giao diện để học; không phải class thực thi độc lập.
UserDetails getUserFromCache(String username);
void putUserInCache(UserDetails user);
void removeUserFromCache(String username);
~~~

`UserCache` không quy định bắt buộc TTL, eviction theo version, distributed invalidation hay giới hạn kích thước. Những khả năng đó do implementation và cache backend đảm nhận.

Spring Security cung cấp `NullUserCache` và `SpringCacheBasedUserCache`. Cũng có `CachingUserDetailsService`, wrapper thực hiện cache trước khi gọi `UserDetailsService` bên dưới; với Spring Framework có thể dùng `@Cacheable`. **Các vị trí cache không giống nhau**: cache do provider sử dụng và cache của wrapper/service có thể là hai lớp riêng. Khi xóa tài khoản, phải biết **đúng lớp nào** đang lưu bản sao và vô hiệu hóa chúng theo thiết kế.

### 3.3. Một chi tiết ít được chú ý: cache trúng vẫn cần kiểm tra credential

Đối với `DaoAuthenticationProvider`, **cache hit không có nghĩa bỏ qua xác thực password**. Provider vẫn có các bước kiểm tra credential/trạng thái phù hợp; nếu kiểm tra password trên bản cache thất bại, `AbstractUserDetailsAuthenticationProvider` có cơ chế tải lại dữ liệu mới để thử xác minh, tránh từ chối một password đã thay đổi chỉ vì cache chứa hash cũ.

Nhưng cơ chế tải lại này **không phải hợp đồng đồng bộ toàn bộ cache**:

- Cache có thể chứa authorities cũ ngay cả khi credential vẫn đúng.
- Cờ locked/disabled có thể bị cũ giữa các lần cập nhật nếu chỉ dựa vào cache.
- Không nên dùng sự kiện “password sai” làm chiến lược refresh role.
- Provider hoặc `UserDetailsService` tùy biến có thể có semantics khác.

Nói cách khác, **khả năng tự xử lý password mismatch không thay thế event-driven eviction, version và quyền tại thời điểm request**.

## 4. Bẫy bảo mật: xóa credentials và cache dùng chung cùng object

`ProviderManager` mặc định cố gắng gọi `eraseCredentials()` trên kết quả xác thực nếu đối tượng hỗ trợ `CredentialsContainer`. Điều này giảm thời gian lưu raw password, password hash hoặc secret trong `Authentication`/session.

Tuy nhiên, nếu `Authentication.principal` trỏ trực tiếp tới **cùng instance `UserDetails`** đang được lưu trong cache, quá trình xóa credential có thể **xóa cả password hash trong instance cache**. Những lần xác thực kế tiếp dựa vào object cache đó có thể thất bại.

~~~text
UserDetailsService --> UserDetails object U (passwordHash != null)
                           |
                +----------+-----------+
                |                      |
                v                      v
        UserCache giữ U           Authentication.principal = U
                                       |
                                       v
                          ProviderManager.eraseCredentials()
                                       |
                                       v
                              U.password = null
                                       |
                                       v
                       Cache giữ cùng U, password đã null
~~~

**Cách xử lý an toàn:**

- Ưu tiên **copy** `UserDetails` khi đưa vào/tạo kết quả authenticated để không làm thay đổi instance cache; kiểm thử rằng bản copy không chia sẻ mutable credential container với cache.
- Hoặc thiết kế cache giữ immutable projection/DTO đúng mức bảo vệ và nạp hash trong quá trình login khi cần.
- Giữ TTL ngắn và kiểm soát quyền truy cập vào cache, vì password hash vẫn là dữ liệu nhạy cảm.
- Không tắt `eraseCredentialsAfterAuthentication` chỉ để sửa lỗi cache mà bỏ qua phân tích rủi ro. Một số hướng dẫn Spring nêu khả năng tắt credential erasure khi dùng `CachingUserDetailsService`/`@Cacheable`, nhưng đây là **trade-off bảo mật** cần được hiểu và kiểm chứng; bản sao tách biệt thường là lựa chọn ít rò rỉ hơn.

Việc cache `UserDetails` khác với cache **`SecurityContext` đã xác thực**. Cái thứ hai có thể chứa `Authentication` từ request trước, và không được “sửa” chỉ bằng thao tác xóa `UserDetails` của provider.

## 5. Chính sách cache: xác định key, TTL, version, giới hạn và hành vi lỗi

### 5.1. Chọn key đúng ý nghĩa

Key có thể là username chuẩn hóa hoặc stable userId, nhưng phải thống nhất với quy tắc tìm kiếm:

~~~text
Đơn tenant:   auth:user:<canonical-username>
Đa tenant:    auth:user:<verified-tenant-id>:<canonical-username>
Theo ID:      auth:user-id:<stable-user-id>
~~~

Đây là **mẫu thiết kế**, không phải key mặc định của Spring Security. Nếu username có thể đổi, cần xóa **cả key cũ và key mới**; key theo userId giảm một số vấn đề rename nhưng `UserCache` mặc định API tra theo username nên adapter phải ánh xạ chính xác.

Không cho client tự khai một `tenantId` có quyền cao hơn rồi dùng thẳng làm cache key: tenant scope phải được xác minh. Tránh va chạm key giữa environment (dev/test/prod), loại principal, tenant và phương thức đăng nhập.

### 5.2. TTL không phải cơ chế thu hồi ngay lập tức

`TTL = 300 giây` nghĩa là entry được xem là không hợp lệ sau khoảng thời gian đó **nếu** cache thực thi TTL đúng và không kéo dài thời hạn vô hạn bởi truy cập. Nó **không** cam kết mọi request dừng sử dụng thông tin cũ trong 300 giây nếu còn session/JWT/cache khác.

Đặt TTL dựa trên dữ liệu và ngân sách rủi ro:

| Loại thông tin | Độ nhạy thay đổi | Chính sách thường cân nhắc |
| --- | --- | --- |
| Tên hiển thị, avatar | Thấp | TTL tương đối dài, refresh khi sửa profile |
| Username, account enabled/locked | Cao | Evict sau commit, version/revalidate; tránh cache dài |
| Roles/authorities | Cao | Event + version + session/token policy rõ ràng |
| Tenant membership, ACL dữ liệu nhạy cảm | Rất cao | Revalidate tại authorization hoặc cache ngắn với invalidation bảo đảm |
| Password hash dùng cho login | Rất cao | Không cache nếu chưa cần; bảo vệ credential và copy đúng |
| “User không tồn tại” | Có rủi ro | Negative cache ngắn/thận trọng, tránh làm user mới không login được |

**Negative caching:** Nếu cache kết quả “không có tài khoản”, một người vừa đăng ký có thể tiếp tục bị coi là không tồn tại. Khi createUser, phải xóa negative entry phù hợp; cũng cần tránh tạo kênh dò username hoặc gây cache poisoning.

### 5.3. Giới hạn kích thước, bảo vệ dữ liệu và eviction

Một cache auth phải có:

- Dung lượng/weight tối đa, chính sách eviction, TTL và giám sát hit/miss/evict;
- Phân quyền truy cập backend cache, TLS khi truyền mạng và bảo vệ dữ liệu khi lưu;
- Quy tắc không log password hash, raw credential, tokens hay full serialized `UserDetails`;
- Chính sách khi Redis/cache lỗi: không tự động chấp nhận dữ liệu chưa được kiểm chứng;
- Tách namespace và key version khi đổi schema/serializer;
- Cơ chế chống cache stampede khi nhiều request đồng thời cache miss;
- Kế hoạch rebuild/warmup; **không** mở quyền chỉ vì cache miss hoặc cache không truy cập được.

Cache auth là tối ưu hiệu năng có điều kiện; **nguồn quyết định** phải luôn đến từ dữ liệu/credential đã được hệ thống xác thực theo policy.

## 6. Khi account thay đổi, phải vô hiệu hóa những gì?

Các sự kiện quan trọng:

| Sự kiện | Cache `UserDetails` | Session/`Authentication` | Token | Kiểm tra ở request |
| --- | --- | --- | --- | --- |
| Tạo tài khoản mới | Evict negative cache, key username | Không có session để thu hồi chỉ do create | Chưa có token nếu chưa login | Kiểm tra email/activation nếu có |
| Đổi password | Evict hash cũ | Cân nhắc logout các session khác và reauth session hiện tại | Revoke refresh token; access token theo policy | Có thể yêu cầu step-up/passwordChangedAt |
| Reset password do nghi bị chiếm | Evict ngay | Thu hồi các session liên quan | Revoke refresh, denylist/version check cho access token còn hạn | Chính sách nghiêm ngặt hơn tự đổi thông thường |
| Khóa/disable user | Evict flags | Expire/invalidate sessions; chặn request mới | Revoke token còn hiệu lực nếu rủi ro cao | Recheck account enabled tại điểm bảo vệ |
| Thu hồi/cấp role | Evict authorities | Context cũ có thể chứa role cũ; refresh hoặc expire | Claims/scope cũ có thể chưa đổi | Authorize trên quyền mới theo chính sách |
| Đổi tenant membership | Evict theo user/tenant | Làm mới tenant context/session | Token có tenant claim cần refresh/revoke | Kiểm tra tenant + object-level rights |
| Đổi username | Evict key cũ và mới; cập nhật mapping | Session có getName cũ, dùng ID ổn định | Subject/claim cần mapping an toàn | Không để username cũ truy cập nhầm account |
| Xóa user | Evict dữ liệu/negative-cache phù hợp | Thu hồi session & remember-me | Revoke token, xóa key/credential liên quan | Deny login, truy cập tài nguyên cũ |
| Đổi email/phone | Evict nếu auth dùng làm login/MFA | Theo mức độ rủi ro và xác minh lại | Update claims/next issuance | Không tự dùng profile thay đổi làm role |

**Điều tối quan trọng:** “Evict cache sau UPDATE” giải quyết **một lớp**. Nếu kết quả `Authentication` đã nằm trong HTTP session, `UserDetailsService` có thể không được gọi lại ở request tiếp theo. Khi thu hồi vai trò, đừng giả định chỉ xóa cache là đã thu hồi quyền.

### Mô hình sự kiện có thể dùng

~~~text
AccountChanged(userId, usernameBefore, usernameAfter,
               tenantId, authVersion, reason, committedAt)
                      |
                      v
        Bản ghi DB commit thành công
                      |
                      v
             Outbox / event bus
                      |
        +-------------+----------------+
        |             |                |
        v             v                v
  Evict cached    Invalidate      Update token
  auth details    sessions        revocation state
        |             |                |
        +-------------+----------------+
                      |
                      v
         Metrics + audit + retry/DLQ
~~~

Event nên mang **identity/phiên bản tối thiểu**, không mang password hash, raw password hoặc PII không cần thiết. Consumer phải **idempotent** vì message broker có thể giao lại cùng sự kiện.

## 7. Transaction, thứ tự sự kiện và consistency window

### 7.1. Đừng evict trước khi giao dịch commit

Giả sử service gọi `cache.evict("an")` rồi DB transaction mới commit. Giữa hai bước, request khác cache miss, tải **dữ liệu cũ** từ DB rồi repopulate cache. Khi commit xong, cache lại chứa bản cũ và không còn sự kiện xóa nào khác.

~~~text
Sai thứ tự:
t0   UPDATE chưa COMMIT
t1   EVICT cache
t2   request B cache miss -> SELECT dữ liệu DB cũ -> CACHE PUT cũ
t3   COMMIT dữ liệu mới
t4   cache vẫn chứa dữ liệu cũ cho đến TTL/eviction kế tiếp
~~~

**Tốt hơn:** Ghi trạng thái mới và tăng `authVersion` trong **một transaction**, rồi phát invalidation sau commit. Dù vậy, có các cuộc đua đọc/ghi khác và sự kiện có thể thất lạc nên vẫn cần TTL/phiên bản hoặc cơ chế bảo đảm mạnh hơn ở các điểm nhạy cảm.

### 7.2. Bẫy re-population sau eviction

Ngay cả thứ tự “COMMIT rồi EVICT” cũng có race:

~~~text
t0 Request B bắt đầu load bản v1 (trước commit), đang chờ
t1 Admin COMMIT bản v2
t2 Sự kiện EVICT cache
t3 Request B hoàn thành và PUT bản v1 vào cache (stale resurrection)
~~~

Giải pháp tùy mức nhất quán cần đạt:

- **Version/generation fencing:** mỗi entry mang phiên bản, cache chỉ nhận dữ liệu với version không thấp hơn mức mới nhất đã biết;
- **Evict + TTL ngắn** nếu chấp nhận cửa sổ stale tối đa có giới hạn;
- **Đọc authoritative khi thao tác rủi ro cao** thay vì chỉ dựa vào cache;
- **Lock/serialization theo key** khi thực sự cần đồng bộ mạnh và chấp nhận chi phí;
- **Outbox + retry + idempotent consumers** để sự kiện không mất khi process chết sau commit;
- **Read-your-writes:** sau thay đổi, request cùng actor có thể đọc primary hoặc dùng version mới để tránh replica lag.

`authVersion` thường là số nguyên **tăng đơn điệu** mỗi khi chính sách xác thực/phân quyền của account thay đổi. Dùng timestamp từ nhiều máy có clock skew có thể kém tin cậy hơn một version tăng trong DB transaction.

### 7.3. Replica và distributed cache

Đọc từ read replica sau commit trên primary có thể vẫn nhận dữ liệu cũ nếu replication lag. Evict Redis đúng thời điểm **không đảm bảo** query kế tiếp đã thấy bản mới. Những thao tác như khóa tài khoản hoặc thu hồi quyền quan trọng có thể cần đọc primary/consistent read hoặc kiểm tra version đã commit trước khi chấp nhận dữ liệu.

Với cache per-node, mỗi node phải nhận invalidation. Với cache tập trung, vẫn còn stale data trong thread-local request, session hoặc các bản copy tại service khác. Quan sát `cache hit ratio` thôi không đo được độ trễ thu hồi.

### 7.4. Các mức nhất quán

| Mức | Hành vi chấp nhận | Ví dụ |
| --- | --- | --- |
| **Eventual consistency** | Cập nhật lan truyền với độ trễ hữu hạn theo thực tế vận hành | Avatar/tên hiển thị |
| **Bounded staleness** | Có ngân sách cụ thể về thời gian stale (cần đo) | Vai trò ít nhạy cảm với cache TTL ngắn |
| **Read-your-writes** | Sau khi user tự sửa, lần đọc kế tiếp của họ thấy dữ liệu mới | Đổi tên/đăng ký |
| **Security critical revalidation** | Quyết định nhạy cảm phải kiểm tra trạng thái mới/nguồn quyền phù hợp | Disable account, chuyển tiền, cấp admin, thu hồi tenant access |

Không ghi “strong consistency” chỉ vì cache eviction thành công: phải chỉ ra **tại điểm nào** quyết định được làm mới, đọc từ nguồn nào, có request đang chạy/replica lag không và xử lý mất kết nối thế nào.

## 8. `SecurityContext`/HTTP session không đồng nhất với `UserDetails` cache

Với Spring Security Servlet, sau login thành công, `SecurityContextHolder` chứa `Authentication`. `SecurityContextRepository` có thể lưu kết quả cho request kế tiếp trong HTTP session. Ở request sau, Spring khôi phục identity; không nhất thiết gọi lại `DaoAuthenticationProvider` hay `loadUserByUsername`.

Vì vậy:

~~~text
Đăng nhập -> UserDetails (có thể đọc cache) -> Authentication ROLE_ADMIN
                                              |
                                              v
                                  HttpSession/SecurityContext
                                              |
                                              v
                                  Request 2: ROLE_ADMIN
                                              |
Admin đổi DB ROLE_USER + xóa UserCache ------+  (KHÔNG tự sửa session)
~~~

Để thu hồi quyền của session đã cấp, ứng dụng có thể:

1. **Expire/invalidate session** liên quan đến user để lần truy cập sau buộc xác thực lại;
2. **Revalidate `authVersion` hoặc trạng thái account** tại mỗi request / tại endpoints rủi ro cao, rồi từ chối hoặc tạo lại authentication đúng chính sách;
3. **Refresh authorities** từ authoritative source ở một ranh giới tin cậy rõ ràng, không “đổi role” dựa trên input client;
4. Sử dụng thời hạn phiên ngắn hơn cùng quy tắc logout thiết bị khi đổi mật khẩu hoặc khóa tài khoản.

`SessionRegistry` phục vụ tính năng quản lý concurrent sessions khi được tích hợp đúng; `SessionInformation.expireNow()` đánh dấu session hết hạn để bộ lọc xử lý, **không có nghĩa đóng ngay một request đang chạy** hoặc xóa mọi session trong hệ thống phân tán. Với Spring Session, quản lý session phân tán phải dựa trên repository/index và cấu hình session tracking thực tế, không giả định SessionRegistry ở một node nhìn thấy tất cả.

**Logout** của Spring Security Servlet thông thường invalidate HTTP session và làm sạch `SecurityContextHolder`/repository. Nhưng logout một trình duyệt **không tự động** thu hồi JWT/refresh tokens đã phát hành, các session trên thiết bị khác hoặc external IdP session.

## 9. Thu hồi JWT và opaque token: không thể giải bằng cách xóa `UserCache`

### 9.1. JWT đã ký là snapshot theo thời điểm phát hành

Một JWT được xác minh chữ ký và các claim như issuer, audience, expiration vẫn có thể hợp lệ **về mặt mật mã** khi role/account trong DB đã đổi. Hệ thống resource server stateless không bắt buộc truy vấn user database để kiểm tra mỗi token. Do đó, xóa `UserDetails` cache hoặc cập nhật account **không làm thay đổi** chữ ký/claim trong JWT.

Các lựa chọn:

- **Access token TTL ngắn:** giảm cửa sổ stale; không đủ khi cần chặn ngay.
- **Denylist theo `jti`:** lưu token identifier đã thu hồi đến lúc token hết hạn, kiểm tra ở mỗi request tại gateway/resource server. Cần storage tin cậy, xử lý outage và thời gian hệ thống.
- **`authVersion`/`securityStamp` claim:** token mang version lúc phát hành; mỗi request hoặc tại điểm nhạy cảm so khớp với bản version mới nhất trong authoritative store/cache được bảo đảm. Không có tra cứu version thì claim **không tự giúp thu hồi**.
- **Opaque/reference token + introspection:** authorization server có thể đánh dấu token không còn active; resource server phải introspect và quản lý cache introspection thận trọng.
- **Rotate/revoke refresh token:** chặn cấp access token tiếp theo; refresh token bị thu hồi **không làm access JWT hiện tại tự hết hạn**.

Nếu yêu cầu “khóa tài khoản phải mất quyền trong vài giây”, chọn chiến lược thu hồi hoặc revalidation đáp ứng mục tiêu đó; chỉ dựa vào JWT TTL một giờ là không phù hợp.

### 9.2. Token version thực sự kiểm soát điều gì?

Giả sử token có:

~~~json
{
  "sub": "account-42",
  "auth_ver": 7,
  "scope": "document:read",
  "exp": 1893456000
}
~~~

Đây là JSON **minh họa**, không phải token hợp lệ/đã ký. Sau khi admin cập nhật tài khoản, DB đặt `authVersion = 8`. Resource server phải **xác minh chữ ký, thuật toán được phép, issuer/audience/exp** rồi so `auth_ver == currentAuthVersion` (theo policy). Nếu current version là 8, token version 7 bị từ chối.

Nếu version được cache 5 phút mà không có invalidation tin cậy, yêu cầu có thể vẫn thấy 7 trong 5 phút. **Version check chỉ mạnh bằng freshness của nguồn version và xử lý lỗi khi tra cứu**.

### 9.3. Opaque token không tự có consistency tuyệt đối

Opaque token thường được introspect ở authorization server, nơi có thể trả `active=false` sau thu hồi. Nhưng resource server có thể cache kết quả introspection; nếu cache TTL dài, token bị thu hồi vẫn có cửa sổ stale. Cần thống nhất ngân sách thời gian và cache policy hai phía.

## 10. Mô hình kiến trúc: chọn mức độ phức tạp theo yêu cầu

### Mức A: Một instance, session-based, yêu cầu đơn giản

- Để `NullUserCache` mặc định nếu chưa đo thấy nhu cầu cache `UserDetails`.
- Dựa vào `SecurityContextRepository` và session theo Spring Security; bảo vệ CSRF/cookie.
- Khi khóa user/thu hồi quyền, invalidate sessions liên quan hoặc revalidate ở endpoints nhạy cảm.
- Sử dụng DB chính để kiểm tra quyền quan trọng.
- Dùng audit trail cho thay đổi account và logout.

### Mức B: Nhiều instance, DB + distributed cache

- Cache `UserDetails`/auth projection với TTL, giới hạn dung lượng, đúng key tenant.
- Mỗi account có `authVersion`, tăng trong transaction với thay đổi quan trọng.
- Phát invalidation sau commit, tốt hơn dùng **transactional outbox** nếu cần delivery tin cậy.
- Các node tiêu thụ event idempotent, có giám sát propagation lag và retry/DLQ.
- Session nằm trong repository phân tán hoặc strategy rõ ràng; có cơ chế revoke trên mọi node.
- Xác định cách xử lý replica lag, network partition và mất Redis.

### Mức C: JWT stateless/API rủi ro cao

- Access token ngắn hạn, refresh token rotation và revocation.
- Tùy mức bảo mật: denylist `jti`, token version hoặc introspection.
- Resource server kiểm tra JWT/opaque theo chuẩn và freshness policy.
- Quyết định quyền với dữ liệu nhạy cảm phải đối chiếu tình trạng account/tenant mới hoặc authority service đáng tin.
- Mục tiêu “thu hồi nhanh” phải có SLO và kiểm thử end-to-end, không chỉ unit test cache.

**Không có một cấu hình chung cho mọi ứng dụng.** Bật Redis, thêm TTL rồi tuyên bố “consistent” là thiếu định nghĩa về yêu cầu bảo mật, topology và điểm ra quyết định.

## 11. Ví dụ Java 17 chạy độc lập: TTL, dữ liệu cũ, eviction và version

Ví dụ thuần Java dưới đây mô phỏng **ba kho riêng biệt**: dữ liệu tài khoản gốc, cache có TTL, và session snapshot. Mục tiêu là trực quan hóa hậu quả của việc chỉ sửa DB hoặc chỉ evict cache.

**Đây là mô hình giáo dục**, không phải implementation của `UserCache`/`SecurityContextRepository` Spring Security. Ví dụ không lưu password, không có HTTP hoặc mã hóa JWT vì trọng tâm là tính nhất quán khi account role/flags thay đổi.

### 11.1. File và lệnh chạy

Tạo file **`AuthCacheConsistencyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public final class AuthCacheConsistencyDemo {

    record Account(long id, String username, String role,
                   boolean enabled, long authVersion) {}

    record CacheEntry(Account account, long expiresAtMillis) {}

    record SessionSnapshot(long userId, String role, long authVersion) {}

    static final class AccountStore {
        private Account account = new Account(
                42L, "an", "ROLE_ADMIN", true, 1L);

        Account find(String username) {
            if (!account.username().equals(username)) {
                throw new IllegalArgumentException("Unknown account");
            }
            return account;
        }

        void changeRole(String role) {
            account = new Account(
                    account.id(), account.username(), role,
                    account.enabled(), account.authVersion() + 1);
        }

        void disable() {
            account = new Account(
                    account.id(), account.username(), account.role(),
                    false, account.authVersion() + 1);
        }
    }

    static final class AccountCache {
        private final Map<String, CacheEntry> values = new HashMap<>();
        private final long ttlMillis;

        AccountCache(long ttlMillis) {
            this.ttlMillis = ttlMillis;
        }

        Account get(AccountStore store, String username, long nowMillis) {
            CacheEntry cached = values.get(username);
            if (cached != null && nowMillis < cached.expiresAtMillis()) {
                return cached.account();
            }
            Account fresh = store.find(username);
            values.put(username,
                    new CacheEntry(fresh, nowMillis + ttlMillis));
            return fresh;
        }

        void evict(String username) {
            values.remove(username);
        }
    }

    public static void main(String[] args) {
        AccountStore db = new AccountStore();
        AccountCache cache = new AccountCache(1000L);

        // t = 0: lần đọc đầu, tạo bản cache và session role ADMIN.
        Account first = cache.get(db, "an", 0);
        SessionSnapshot oldSession = new SessionSnapshot(
                first.id(), first.role(), first.authVersion());

        System.out.println("initial.cacheRole=" + first.role());
        System.out.println("initial.sessionVersion="
                + oldSession.authVersion());

        // t = 100: DB đã đổi quyền; cache chưa hết TTL, session chưa đổi.
        db.changeRole("ROLE_USER");
        System.out.println("db.afterChangeRole=" + db.find("an").role());
        System.out.println("cache.at100.role="
                + cache.get(db, "an", 100).role());
        System.out.println("oldSession.role=" + oldSession.role());

        // t = 1100: cache hết hạn và tải role mới, session cũ vẫn stale.
        Account refreshed = cache.get(db, "an", 1100);
        System.out.println("cache.afterTTL.role=" + refreshed.role());
        System.out.println("oldSession.versionCurrent="
                + (oldSession.authVersion()
                   == db.find("an").authVersion()));

        SessionSnapshot renewed = new SessionSnapshot(
                refreshed.id(), refreshed.role(), refreshed.authVersion());

        // t = 1200: khóa user. Cache vẫn giữ "enabled=true".
        db.disable();
        System.out.println("cache.beforeEvict.enabled="
                + cache.get(db, "an", 1200).enabled());

        // Eviction làm lần đọc cache kế tiếp nhận account mới.
        cache.evict("an");
        Account latest = cache.get(db, "an", 1200);
        System.out.println("cache.afterEvict.enabled=" + latest.enabled());
        System.out.println("renewedSession.versionCurrent="
                + (renewed.authVersion()
                   == db.find("an").authVersion()));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac AuthCacheConsistencyDemo.java
java AuthCacheConsistencyDemo
~~~

**Stdout chính xác của chương trình**:

~~~text
initial.cacheRole=ROLE_ADMIN
initial.sessionVersion=1
db.afterChangeRole=ROLE_USER
cache.at100.role=ROLE_ADMIN
oldSession.role=ROLE_ADMIN
cache.afterTTL.role=ROLE_USER
oldSession.versionCurrent=false
cache.beforeEvict.enabled=true
cache.afterEvict.enabled=false
renewedSession.versionCurrent=false
~~~

### 11.2. Đọc kết quả và nối sang Spring Security

- `cache.at100.role=ROLE_ADMIN`: khi TTL chưa hết, một yêu cầu tra cache có thể thấy role đã lỗi thời dù DB là `ROLE_USER`.
- `oldSession.role=ROLE_ADMIN`: session vẫn giữ snapshot cũ; **cache đã expire cũng không tự làm mới session**.
- `oldSession.versionCurrent=false`: so sánh `authVersion` với kho gốc phát hiện snapshot không còn hợp lệ. Để áp dụng thực tế, phiên/token phải được **từ chối hoặc refresh an toàn** khi version lệch.
- `cache.beforeEvict.enabled=true`: khóa account ở DB không làm một entry cache tự đổi.
- `cache.afterEvict.enabled=false`: sau eviction, lần đọc mới có thể nhận trạng thái đã khóa; điều này không tự logout mọi phiên đang hoạt động.
- `renewedSession.versionCurrent=false`: ngay cả session tạo sau lần refresh role cũng trở nên stale khi account bị disable tiếp theo.

**Giới hạn:** Clock trong demo được truyền thủ công để giữ output deterministic; triển khai thực tế phải dùng cơ chế TTL của cache và tính đến đồng hồ/độ trễ. `HashMap` ở đây chỉ chạy đơn luồng; production nhiều thread phải dùng cache backend an toàn đồng thời. Demo không mô phỏng race stale-repopulation, transaction/replica lag, request đang chạy hay token ký số; những tình huống đó cần test tích hợp.

## 12. Áp dụng với Spring Security: các điểm nối API chính xác

### 12.1. `UserCache` chỉ quản lý UserDetails

~~~java
// MÃ MINH HỌA: các bean được cấu hình ở Spring application context.
@Bean
UserCache userCache(org.springframework.cache.CacheManager cacheManager) {
    var springCache = cacheManager.getCache("authUsers");
    if (springCache == null) {
        throw new IllegalStateException("Missing authUsers cache");
    }
    return new SpringCacheBasedUserCache(springCache);
}

@Bean
DaoAuthenticationProvider daoAuthenticationProvider(
        UserDetailsService userDetailsService,
        PasswordEncoder encoder,
        UserCache userCache) {
    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);
    provider.setPasswordEncoder(encoder);
    provider.setUserCache(userCache);
    return provider;
}
~~~

Đây là **đoạn cấu hình tích hợp Spring**, không phải chương trình standalone; cần import `UserCache`, `SpringCacheBasedUserCache`, `@Bean`, các dependency Spring Security/Cache và cấu hình `CacheManager` cùng chiến lược TTL/eviction. Mã này minh họa API provider-level cache; không giải quyết vấn đề cache credential aliasing, logout hoặc invalidation phân tán chỉ bằng hai bean.

Khi thay đổi user qua `UserDetailsManager`/service, xóa cache đã dùng:

~~~java
// Minh họa sau khi transaction cập nhật account đã commit.
userCache.removeUserFromCache(username);
~~~

Nếu còn cache `@Cacheable`/`CachingUserDetailsService` **khác**, evict thêm các cache tương ứng. Không giả định gọi một phương thức là xóa được mọi nơi lưu thông tin user.

### 12.2. Event sau commit

~~~java
// MÃ PHÁC THẢO trong ứng dụng Spring đã khai báo event/repository.
// Không phải chương trình standalone.
@Transactional
public void revokeRole(long userId) {
    Account account = repository.lockAndFind(userId);
    account.revokeAdmin();
    account.bumpAuthVersion();
    applicationEventPublisher.publishEvent(
            new AuthChanged(account.id(), account.username(),
                    account.authVersion()));
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(AuthChanged event) {
    userCache.removeUserFromCache(event.username());
    // Các bước revoke session/token khác phải được thực hiện riêng.
}
~~~

Event listener sau commit phù hợp **trong cùng process**, nhưng nếu process chết sau commit trước khi xử lý, hoặc cần gửi đến nhiều node, cơ chế đơn giản này **không bảo đảm** event đến nơi. Dùng transactional outbox + broker/retry/idempotency nếu yêu cầu mạnh; event chỉ chứa accountId/version/username cần thiết, không chứa credentials.

### 12.3. Session registry và việc thu hồi

Trong Servlet app đã cấu hình concurrent session management/session registry phù hợp, có thể sử dụng `SessionRegistry` để tìm session của một principal đã biết, rồi đánh dấu hết hạn:

~~~java
// MÃ MINH HỌA, không phải chương trình standalone.
// principal phải khớp cách SessionRegistry lưu identity.
for (SessionInformation session :
        sessionRegistry.getAllSessions(principal, false)) {
    session.expireNow();
}
~~~

**Đây không phải “kill session ngay lập tức”**: expiration thường có hiệu lực khi filter kiểm tra request tiếp theo, còn session đã mất tracking thì không tìm được. Khi dùng Spring Session/Redis, phải chọn repository/index và cấu hình integration có thể xác định tất cả session của account qua các node. Tránh lấy username không khớp với principal object/`equals` của SessionRegistry.

### 12.4. Logout và bearer token

Đối với form/session, dùng logout support của Spring Security để clear context và invalidate session đúng cách. Với token bearer, thêm cơ chế thu hồi riêng theo `jti`, token version, introspection hoặc refresh token rotation. Không suy ra `SecurityContextLogoutHandler` có thể làm JWT đã phát hành tự hết hiệu lực.

### 12.5. Phân biệt Servlet và Reactive

Các ví dụ `UserCache`/`DaoAuthenticationProvider` và `SessionRegistry` ở trên là **Spring Security Servlet**. Ứng dụng WebFlux có `ReactiveUserDetailsService`, `ReactiveAuthenticationManager` và `ServerSecurityContextRepository`; lifecycle và hook khác. Không sao chép cấu hình `HttpSecurity`/`SecurityContextHolder` sang Reactive mà không kiểm tra API và context propagation tương ứng.

## 13. Test tính nhất quán, không chỉ test giá trị trong cache

### 13.1. Ma trận test bắt buộc theo risk

| Test | Bối cảnh | Kỳ vọng |
| --- | --- | --- |
| Password đổi, cache vẫn có hash cũ | Xác thực lại bằng password mới/cũ | Theo policy: mới hợp lệ, cũ bị từ chối khi hệ thống đã quan sát cập nhật; không “cache hit => bỏ qua password” |
| Disabled user, session còn sống | Request tới endpoint bảo vệ | Bị chặn theo revoke SLO; không chỉ fail ở login lần sau |
| Thu hồi `ROLE_ADMIN` | Session và token phát hành trước thay đổi | Endpoint admin từ chối trong ngân sách thu hồi đã công bố |
| User đổi tenant membership | Cache user và ACL cache tại nhiều node | Tenant cũ không còn truy cập được; tenant mới theo policy |
| Cache miss cạnh tranh với eviction | Loader bắt đầu trước commit, kết thúc sau eviction | Không được giữ vĩnh viễn version cũ; có fencing/TTL |
| Event bị giao lại | Consumer nhận duplicate | Idempotent, không làm giảm version hoặc cấp lại quyền |
| Broker/Redis down | Logout/revoke trong lúc sự cố | Chọn rõ fail-closed, retry hoặc degrade hạn chế; không tự mở quyền |
| Replica lag | DB primary đã commit, replica chưa thấy | Revalidation nhạy cảm không cấp quyền dựa trên trạng thái cũ |
| Session ở node khác | Một node revoke, request kế tiếp qua node B | Có kết quả nhất quán trong SLO |
| JWT chưa hết hạn | Account disabled sau khi token cấp | Token bị từ chối theo cơ chế đã chọn, hoặc tuyên bố rõ cửa sổ còn hiệu lực |
| Username đổi | Cache dùng old/new key | Không để username cũ lấy nhầm account và không có stale key |
| Credential erasure + cache | Đăng nhập nhiều lần cùng user với caching | Không bị mất password hash trong cache dùng chung, không log secret |

Test nên đi qua **SecurityFilterChain thật** bằng MockMvc/WebTestClient hoặc integration test tương ứng. Một unit test `cache.evict(key)` thành công **không chứng minh** HTTP session/JWT đã mất quyền.

### 13.2. Đo độ trễ thu hồi

Ghi các mốc an toàn (không ghi secret):

~~~text
t_commit: DB commit cập nhật authVersion
t_event:  invalidation được gửi/nhận trên các node
t_evict:  cache user/ACL đã bị xóa
t_revoke: session/token revocation state đã cập nhật
t_deny:   request đầu tiên theo danh tính cũ bị từ chối
~~~

Theo dõi `t_deny - t_commit` theo p95/p99 và trường hợp xấu, phân biệt loại account change. Một hệ thống có thể đặt mục tiêu ví dụ **dưới 5 giây** cho disable account; đây chỉ là **minh họa mục tiêu cần thống nhất**, không phải cam kết của Spring Security hay một cấu hình TTL mặc định.

Cần quyết định rõ request đã **bắt đầu trước commit** có được phép hoàn tất không. Trong nhiều hệ thống, không thể hủy ngay mọi request đang chạy; thao tác cực kỳ nhạy cảm cần checkpoint authorization bổ sung gần lúc commit nghiệp vụ.

### 13.3. Hành vi khi cache hoặc revocation store mất kết nối

Nếu không kiểm tra được account enabled/authVersion ở điểm bảo mật cao, “cho qua vì Redis lỗi” có thể làm mất chính sách thu hồi. Tùy nghiệp vụ có thể:

- **Fail closed** với quyết định nhạy cảm, trả lỗi tạm thời và cảnh báo;
- **Đọc fallback từ DB primary** nếu vẫn có quyền truy cập và đủ capacity;
- Dùng trạng thái đáng tin với TTL rất ngắn nếu policy chấp nhận bounded staleness;
- Từ chối thao tác có tác động cao nhưng cho phép các API rủi ro thấp theo quy tắc được thiết kế.

Đừng hạ bậc bảo mật ngầm. Ghi lại các trạng thái degraded, alert và kiểm tra SLO.

## 14. Các lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “Đã evict UserDetails nên user bị logout” | HTTP session/`Authentication` là lớp khác | Revoke/refresh session theo policy |
| “Đã đổi password nên JWT cũ mất hiệu lực” | JWT ký số giữ claim tới `exp` nếu không revalidate/revoke | Ngắn hạn + version/denylist/introspection khi cần |
| Dùng TTL dài cho locked flag/roles | Cho phép stale quyền trong thời gian dài | Invalidation + revalidation/version + SLO |
| Cache password hash và dùng chung object với principal | `eraseCredentials()` có thể xóa hash trong cache | Copy object hoặc tách cache khỏi principal |
| Evict trước transaction commit | Loader có thể repopulate bản cũ | After-commit + event/invalidation đúng thứ tự |
| Chỉ xử lý event ở node hiện tại | Node khác vẫn có cache cũ | Distributed invalidation/repository và retry |
| Dùng timestamp địa phương làm version duy nhất | Clock skew/đụng độ timestamp làm sai thứ tự | Version tăng đơn điệu trong DB |
| Negative cache quá lâu | User mới tạo không đăng nhập được | TTL ngắn + evict khi tạo |
| Một key username cho mọi tenant | Cache collision và nhầm identity | Key có tenant đã xác minh hoặc stable ID |
| Cho rằng `@CacheEvict` tự thu hồi mọi cache | Nó chỉ ảnh hưởng đúng cache được khai báo | Inventory tất cả lớp cache/session/token |
| Dựa vào role từ token mà không có freshness policy | Vai trò đã bị thu hồi vẫn trong token | Chọn ngân sách stale và kiểm tra theo nhu cầu |
| Reuse authVersion nhưng không tăng lúc đổi quyền | Token/session cũ nhìn vẫn đúng version | Bump version theo mọi sự kiện auth-relevant |
| TTL là cam kết thời gian revocation | Session và queue/event/replica có độ trễ khác | Kiểm thử end-to-end và đo p99 |
| Bật cache để sửa hiệu năng chưa đo | Tăng rủi ro và complexity không cần thiết | Profile DB/LDAP calls trước khi bật |
| Dùng fail-open khi không đọc được revocation store | Vô hiệu cơ chế khóa tài khoản | Chính sách degraded/fail-closed rõ ràng |
| Log UserDetails hoặc token đầy đủ | Rò secret/PII và token bearer | Log identity ID, event type, version và trace ID |

## 15. Checklist đưa vào production

1. **Inventory:** ghi rõ nơi nào lưu user, `UserDetails`, `SecurityContext`, session, token, ACL và tenant membership.
2. **Source of truth:** xác định authoritative source cho password/enable/roles/tenant, ai có quyền cập nhật.
3. **Cache policy:** key chuẩn, TTL, max size, namespace, negative caching, bảo vệ credentials và cache hit/miss.
4. **Mutation policy:** tạo/đổi/xóa/khóa/reset password/đổi quyền đều có lý do, audit và invalidation tương ứng.
5. **Transaction:** cập nhật quyền và tăng authVersion atomically, phát event sau commit, cân nhắc outbox.
6. **Version fencing:** ngăn stale loader ghi đè version mới; không phụ thuộc hoàn toàn vào TTL.
7. **Session:** có quy trình revoke/reauth cho người dùng còn phiên trên các thiết bị, cả nhiều node.
8. **Token:** access TTL, revoke refresh, JWT denylist/version hoặc opaque introspection theo risk.
9. **Authorization:** ở endpoint nhạy cảm kiểm tra quyền hiện hành với freshness đủ mạnh.
10. **Outage behavior:** xác định fallback/fail-closed cho cache, DB replica, broker và token revocation store.
11. **Test:** kiểm thử concurrency, replica lag, logout, change password/roles, session ở node khác, JWT còn hạn.
12. **Observability:** đo p95/p99 của thời gian từ commit đến request bị deny; có alert khi quá mục tiêu.
13. **Privacy:** cache/session không mang dữ liệu nghiệp vụ hay credential vượt nhu cầu; log tối thiểu.
14. **Documentation:** ghi rõ thay đổi nào yêu cầu thu hồi **ngay**, thay đổi nào cho phép stale trong bao lâu, và ai chịu trách nhiệm.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Sau khi admin xóa `UserCache` của user, browser đã đăng nhập qua session có tự mất `ROLE_ADMIN` không?  
**Đáp:** Không. Authentication trong session là snapshot khác; cần revoke, refresh hoặc policy revalidation.

**Câu 2.** Vì sao Spring Security có `NullUserCache` mặc định cho provider username/password?  
**Đáp:** Trong nhiều ứng dụng Servlet session-based, không xác thực lại password ở mỗi request; cache `UserDetails` thường không cần cho luồng này.

**Câu 3.** `DaoAuthenticationProvider` thấy password trên cached UserDetails không khớp. Điều đó có đồng nghĩa hệ thống có cache invalidation tốt?  
**Đáp:** Không. Provider có thể tải lại user để thử password mới, nhưng role, locked flag và session vẫn cần chính sách freshness/thu hồi riêng.

**Câu 4.** Vì sao event `evict` chạy trước DB commit có thể làm cache chứa bản cũ?  
**Đáp:** Một request khác có thể cache miss, đọc dữ liệu chưa commit rồi put entry cũ trước khi transaction hoàn tất.

**Câu 5.** Tăng `authVersion` từ 8 lên 9 trong DB có tự thu hồi JWT có `auth_ver=8` không?  
**Đáp:** Không, resource server phải kiểm tra version đáng tin với dữ liệu đủ mới và từ chối token version cũ.

**Câu 6.** `SessionInformation.expireNow()` có đảm bảo request đang chạy bị hủy lập tức không?  
**Đáp:** Không. Nó đánh dấu expiration để cơ chế session/filter xử lý, thường ở request sau; cần hiểu session tracking/distributed configuration.

**Câu 7.** Password đổi nhưng refresh token vẫn hợp lệ thì có thể xảy ra gì?  
**Đáp:** Client có thể tiếp tục đổi refresh token lấy access token mới tùy policy; cần quyết định revoke/rotate refresh và xử lý các access token còn sống.

**Câu 8.** Vì sao phải kiểm thử end-to-end khi thu hồi quyền?  
**Đáp:** Vì cache eviction, session, JWT, replica và các node có thể tồn tại song song; test một lớp không chứng minh đã chặn request thật.

## 17. Tài liệu tham khảo

- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `ProviderManager`, việc xóa credentials và lưu ý cache.
- [Spring Security 6.5 – AbstractUserDetailsAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): `UserCache`, `NullUserCache` mặc định, xử lý password không khớp cache.
- [Spring Security – Caching UserDetails](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/servlet/authentication/passwords/caching.html): `CachingUserDetailsService`, `@Cacheable` và credential erasure.
- [Spring Security 6.5 – UserCache API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserCache.html): get/put/remove và phạm vi contract.
- [Spring Security 6.5 – Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextRepository`, session persistence và explicit save.
- [Spring Security 6.5 – Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): session invalidation, context cleanup và logout handlers.
- [Spring Security 6.5 – SessionInformation API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionInformation.html): các trạng thái phiên active/expired/destroyed.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): xác thực JWT cho resource server.
- [Spring Security – Opaque Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection và principal từ token.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): vòng đời session và kiểm soát thu hồi.

**Ghi nhớ:** **DB commit** tạo dữ liệu mới, **cache invalidation** làm lần đọc tiếp theo thấy dữ liệu mới, **session/token revocation** mới kiểm soát các danh tính đã cấp, còn **authorization freshness** quyết định khi nào thay đổi thực sự có hiệu lực ở API. Muốn tuyên bố nhất quán, phải định nghĩa cửa sổ stale, đo end-to-end và xử lý race, lỗi mạng, nhiều node cùng những request đang chạy.
