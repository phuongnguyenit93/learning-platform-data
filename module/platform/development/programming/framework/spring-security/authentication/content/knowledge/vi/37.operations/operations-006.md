# Bộ nhớ đệm danh tính và thời gian có hiệu lực của thay đổi quyền, trạng thái

## 1. Mục tiêu: thay đổi trong database chưa chắc đã đổi quyền đang được sử dụng

Trong một hệ thống Spring Security, người dùng Alice có thể đã đăng nhập từ 09:00 với quyền `ADMIN`. Lúc 09:10, quản trị viên bỏ quyền `ADMIN` hoặc chuyển Alice sang trạng thái `DISABLED`. Database có thể cập nhật ngay, nhưng:

- `UserDetails` đang được cache có thể vẫn chứa authorities cũ.
- `Authentication` bên trong `SecurityContext` của HTTP session thường là **snapshot** tạo khi đăng nhập; nó không tự tải lại role ở mỗi request.
- JWT access token đã phát hành có thể còn claim `roles=["ADMIN"]` cho tới hết hạn, nếu resource server chỉ kiểm tra chữ ký và hạn sử dụng.
- Redis/local cache, API gateway, microservices và các request đang xử lý có thể nhìn thấy phiên bản dữ liệu khác nhau.
- Một job đã đưa vào queue hoặc một giao dịch đã được phê duyệt trước khi hạ quyền có thể vẫn tiếp tục nếu không có kiểm soát riêng ở nơi thực thi.

**Bài toán vận hành không chỉ là “cache có TTL bao lâu?”, mà là “quyền hoặc trạng thái mới bắt đầu được thực thi ở đâu, khi nào, với độ trễ tối đa nào và có thể chứng minh bằng test/metrics không?”.**

Ví dụ yêu cầu nghiệp vụ:
- Thêm role `REPORT_VIEWER`: có thể chấp nhận hiệu lực trong vòng một phút.
- Bỏ role `ADMIN`: cần hiệu lực gần như tức thời ở API quản trị.
- Khóa tài khoản do compromise: mọi session, token và đường xác thực cần bị ngăn trong thời gian rất ngắn theo SLA an ninh.
- Đổi password: login mới phải dùng hash mới; các phiên hiện có được giữ hay thu hồi phụ thuộc policy.

Sau bài này bạn sẽ hiểu rõ các lớp cache, bản chất tính nhất quán, mô hình TTL/invalidation/version, cách triển khai với Spring Security 6.x/Java 17, cách đo độ trễ thu hồi và viết test chống **stale authorization**.

## 2. Bốn khái niệm cần phân biệt

| Khái niệm | Trả lời câu hỏi | Nơi dữ liệu thường nằm |
|---|---|---|
| **Identity** | Request này đại diện ai? | Principal, `Authentication.getName()`, JWT `sub` |
| **Authentication state** | Principal đã xác thực bằng cách nào, khi nào? | `SecurityContext`, session, bearer token, IdP |
| **Authorization state** | User hiện được phép thực hiện hành động nào? | Role/scope, policy engine, database, cache |
| **Account state** | User hiện `ACTIVE`, `LOCKED`, `DISABLED` hay đã xóa? | Account table, IdP, account-state cache |

Đăng nhập thành công lúc 09:00 không đảm bảo account còn active lúc 09:30. Tương tự, một role ghi trong `Authentication.getAuthorities()` không nhất thiết là role hiện tại ở nguồn dữ liệu quyền.

Phải tách **thời điểm danh tính được xác thực** khỏi **thời điểm chính sách phân quyền được đánh giá**.

### 2.1. Source of truth và snapshot

Giả định database là nguồn dữ liệu quyền hiện hành:

~~~text
DATABASE (source of truth)
  user_id=42
  status=ACTIVE
  roles=[USER, ADMIN]
  authorization_version=17

LOGIN LÚC 09:00:
  SecurityContext/Authentication snapshot:
  principal=user42, authorities=[ROLE_USER, ROLE_ADMIN]

THAY ĐỔI LÚC 09:10:
  database: status=ACTIVE, roles=[USER], version=18

REQUEST LÚC 09:11:
  Session snapshot có thể vẫn là [ROLE_USER, ROLE_ADMIN]
  ⇒ Nếu chỉ gọi hasRole("ADMIN") trên Authentication cũ,
     role bị thu hồi vẫn có thể cho qua.
~~~

Bằng chứng đã login có giá trị để xác định **ai đang gửi request**, nhưng với hành động nhạy cảm cần kết hợp trạng thái quyền **đủ mới**.

### 2.2. Invalidation khác expiry

- **Expiry/TTL:** chấp nhận cache cho đến hạn rồi mới tải lại. Có khoảng staleness được dự đoán nếu không bị gia hạn tùy tiện.
- **Invalidation:** chủ động xóa/đánh dấu cache cũ sau khi dữ liệu thay đổi.
- **Version check:** so sánh phiên bản quyền/session với phiên bản hiện tại; không cần tìm từng bản ghi cache để xóa nếu kiểm tra đúng chỗ.
- **Revocation:** thu hồi session/token hoặc đánh dấu principal/credential không còn được sử dụng.
- **Authorization at point of use:** kiểm tra quyền trực tiếp tại nơi thực hiện hành động, thay vì chỉ dựa vào quyết định lúc user login.

Không đồng nhất năm thao tác trên. Ví dụ xóa Redis cache `user:42` **không tự xóa HTTP session đã đăng nhập**.

## 3. Những lớp dữ liệu có thể cũ trong hệ thống Spring Security

### 3.1. UserDetails cache

Trong luồng username/password, `DaoAuthenticationProvider` sử dụng `UserDetailsService`. Spring Security có:
- `CachingUserDetailsService` kết hợp `UserCache`;
- `@Cacheable` của Spring Framework trên `loadUserByUsername`;
- `UserCache` được cấu hình trong provider/service nếu ứng dụng chọn dùng.

Cache có thể giữ `username`, password hash, `enabled`/account flags và `GrantedAuthority`, tùy `UserDetails` implementation.

**Điểm quan trọng:** `CachingUserDetailsService` mặc định sử dụng `NullUserCache` nếu bạn không cung cấp cache thích hợp. Spring Security không có nghĩa tự bật Redis UserDetails cache chỉ vì ứng dụng có Redis.

### 3.2. SecurityContext trong session

Với form login/session, sau xác thực thành công, `Authentication` thường được lưu trong `SecurityContext` qua `SecurityContextRepository`. Những request tiếp theo lấy lại context đó, không nhất thiết gọi `UserDetailsService` nữa.

~~~text
POST /login:
  UserDetailsService → kiểm tra password → Authentication(role snapshot)
                                       |
                                       v
                                   HttpSession

GET /api/admin sau 20 phút:
  HttpSession → SecurityContext → Authentication cũ
                                       |
                                       v
                             hasRole("ADMIN") trên snapshot
~~~

Vì vậy **evict UserDetails cache chỉ làm ảnh hưởng các lần tải UserDetails sau**, không tự động đổi authorities của Authentication đã nằm trong session.

Spring Security 6 dùng mô hình **explicit saving** cho `SecurityContextRepository` trong nhiều cấu hình. Nếu tự thay Authentication/clear context, phải hiểu cách save/invalidate tương ứng, không giả định chỉ `SecurityContextHolder.clearContext()` ở một request là đã thu hồi mọi session.

### 3.3. JWT access token

JWT đã ký có thể chứa `sub`, `scope`, `roles`, `iat`, `exp` và các claim khác. Sau khi phát hành, nội dung JWT **không tự thay đổi** khi DB giảm role.

Resource server thông thường kiểm tra chữ ký, `iss`, `exp`, `nbf`, audience nếu được cấu hình và map claims thành authorities. Nếu không có tra cứu trạng thái/quyền hiện hành, token ký hợp lệ với `ROLE_ADMIN` cũ vẫn có thể được chấp nhận đến `exp`.

**Kiểm tra JWT signature không đồng nghĩa kiểm tra quyền hiện thời.** JWT còn hạn cũng không nói account đang active hoặc refresh token chưa bị thu hồi.

### 3.4. Opaque token và introspection cache

Một OAuth2 resource server dùng opaque token có thể gọi Authorization Server introspection để xác nhận `active` và scopes. Nhưng nếu introspection result được **cache** trong resource server hoặc gateway, một `active=true` cũ có thể tiếp tục tồn tại trong TTL cache đó.

Không mặc định opaque token luôn revocable tức thời: tính tức thời phụ thuộc cách Authorization Server cập nhật trạng thái, introspection cache, mạng và những đường kiểm tra thực tế.

### 3.5. Phân quyền nghiệp vụ cache riêng

Ngoài Spring Security, ứng dụng có thể cache:
- danh sách nhóm, team, phòng ban, tenant;
- quyền đọc một project, order hoặc report;
- object-level permission/ACL;
- feature flags, subscription/contract state;
- entitlement từ dịch vụ bên ngoài.

Role `MANAGER` có thể vẫn đúng nhưng user không còn thuộc `tenant-A`. Chỉ xóa `UserDetails` cache không nhất thiết làm mới **object ownership** hoặc ACL ở service khác.

## 4. Ma trận hiệu lực của thay đổi theo từng lớp

| Thay đổi | Lớp có thể cũ | Điều cần làm |
|---|---|---|
| Đổi display name | Profile/UI cache | TTL, invalidate profile cache, có thể eventual |
| Thêm role báo cáo | UserDetails, session, entitlement cache, JWT | Refresh context/token hoặc live authorization theo SLA |
| Bỏ role admin | Session/JWT, cache quyền | Revalidate ở endpoint nhạy cảm, revoke hoặc version check |
| Disable user | UserDetails/session/token và downstream services | Chặn login mới **và** request/session/token đang dùng |
| Lock account do nhiều mật khẩu sai | Authentication/login state, session tùy policy | Thực thi login lockout, xem policy có thu hồi session không |
| Đổi password | Password hash cache, session, refresh tokens | Evict hash cache; thu hồi sessions/tokens nếu policy yêu cầu |
| Đổi tenant | Principal, role mapping, object ACL, session | Thực thi tenant hiện hành và account binding |
| Xóa user | Mọi cache/session/token | Deny access, revoke và dọn dữ liệu theo lifecycle |
| Thu hồi refresh token | Authorization Server token store | Ngăn refresh mới; xem access token cũ còn hạn thế nào |
| Logout | Session/client/token | Invalidate session và token theo kiến trúc, không chỉ xóa cookie phía client |

Tính chính xác không chỉ đến từ một flag `enabled=false`: nếu một API bỏ qua status check vì tin session cũ, account đã khóa vẫn có thể dùng tài nguyên.

## 5. “Thời gian có hiệu lực” nghĩa chính xác là gì?

Hãy định nghĩa các mốc:

~~~text
T0: quản trị viên nhấn "Bỏ quyền ADMIN"
T1: database transaction commit và trả thành công
T2: event invalidation được phát hành
T3: các cache/replica nhận event hoặc hết TTL
T4: request mới của Alice tới một endpoint kiểm tra quyền
T5: endpoint từ chối theo policy mới
~~~

Có nhiều loại độ trễ:
- **Database commit latency:** từ T0 đến T1.
- **Propagation latency:** từ T1 đến lúc các cache/instance cập nhật.
- **Enforcement latency:** từ T1 đến request/operation đầu tiên thực sự bị từ chối.
- **Outstanding-work latency:** giao dịch hoặc job đã được phép trước T1 có thể chưa kết thúc.

Đo `T5 - T1` bằng thử nghiệm request có kiểm soát, không chỉ đo event được publish lúc T2. Với một tài khoản không phát sinh request, không có T4/T5 để quan sát; có thể dùng synthetic probe hoặc state inspection theo yêu cầu SLA.

### 5.1. TTL cho giới hạn staleness gần đúng, không phải bảo đảm mọi đường

Nếu local cache TTL cố định 60 giây từ lúc ghi, dữ liệu cũ có thể tồn tại tới khoảng 60 giây **trong lớp cache đó**, chưa tính:
- cache khác phía gateway hoặc downstream;
- request đang xử lý;
- client/session giữ snapshot khác;
- JWT còn hiệu lực 15 phút;
- stale-while-revalidate hoặc tự gia hạn TTL;
- lỗi invalidation hoặc event queue bị chậm.

Không thể kết luận “thay quyền hiệu lực tối đa 60 giây” chỉ vì Redis key có TTL 60 giây. Phải xem **đường thực thi quyền lâu nhất**.

### 5.2. Ví dụ timeline vận hành

~~~text
JWT issued:       09:00, expires 09:15, contains ADMIN
Session created:  09:01, TTL 8h, contains ADMIN
User cache:       TTL 60s
DB role removed:  09:03

Nếu /api/admin chỉ tin JWT roles:
  token cũ có thể còn được dùng tới 09:15.

Nếu /web/admin chỉ tin session Authentication:
  snapshot có thể còn tới khi session hết hạn/đăng nhập lại.

Nếu /admin luôn check current DB role:
  request SAU COMMIT sẽ bị từ chối theo snapshot DB mới
  (trừ request đã qua chốt kiểm tra trước commit).

Nếu /admin dùng cache quyền TTL 60s:
  có thể bị chậm tới khi cache được invalidate/hết TTL,
  chưa tính lớp khác.
~~~

**SLA minh họa**, không phải chuẩn bắt buộc:
- Thêm quyền không nhạy cảm: eventual consistency trong 60 giây.
- Bỏ quyền admin: từ chối request mới trong 5 giây.
- Disable account do compromise: từ chối request mới tại mọi replica gần như ngay sau commit, với cơ chế dự phòng khi store bị lỗi.

Nếu product đưa ra SLA 5 giây, một JWT 15 phút không kiểm tra trạng thái hiện thời **không đáp ứng SLA đó**.

## 6. Mô hình nhất quán: eventual hay strong?

### 6.1. Eventual consistency

Cache cũ sẽ hội tụ về trạng thái mới sau TTL/event, nhưng trong cửa sổ đó request có thể dùng quyền cũ.

Phù hợp khi:
- thay đổi dữ liệu hiển thị hoặc entitlement ít rủi ro;
- chấp nhận độ trễ đã công bố;
- có monitoring để phát hiện propagation bị kẹt;
- không có hành động nhạy cảm trong cửa sổ staleness.

### 6.2. Strong / read-current authorization

Endpoint nhạy cảm đọc nguồn dữ liệu có tính nhất quán phù hợp và kiểm tra tại thời điểm sử dụng. Có thể thêm:
- row lock/optimistic version ở thao tác ghi;
- conditional update đảm bảo quyền chưa bị thu hồi trong transaction;
- denylist/epoch check trước side effect;
- transaction-specific approval đối với thao tác tài chính.

Không tuyên bố “read DB mỗi request là tuyệt đối tức thời”: request đã kiểm tra trước khi role bị thu hồi vẫn có thể thực hiện tiếp. Nếu cần ngăn **commit sau khi quyền bị rút**, cần kiểm tra trong transaction hoặc protocol phù hợp với operation.

### 6.3. Hybrid theo rủi ro

Một thiết kế thực tế:
- Cache profile/role cho trang ít nhạy cảm với TTL ngắn.
- Request quản trị dùng **live account status + live authorization version/role**.
- Session/JWT chỉ cung cấp identity, policy server quyết định quyền hiện tại.
- Khi disable hoặc revoke, phát sự kiện invalidation và thu hồi session/token để giảm các đường dùng dữ liệu cũ.
- Nếu state store không sẵn sàng ở action đặc biệt nhạy cảm, **fail closed** thay vì tự sử dụng authority cũ.

Đổi lại, live check tăng latency/DB load. Dùng batch queries, read model được đồng bộ và circuit breaker theo risk, nhưng không mở bypass khi stale.

## 7. Spring Security: UserDetails cache hoạt động ra sao?

Spring Security 6.5 tài liệu hóa `CachingUserDetailsService`, `UserCache` và `@Cacheable`. Ví dụ ở mức cấu hình:

~~~java
@Bean
CachingUserDetailsService cachedUsers(
        UserDetailsService delegate,
        UserCache userCache) {

    CachingUserDetailsService service =
            new CachingUserDetailsService(delegate);
    service.setUserCache(userCache);
    return service;
}
~~~

Đây là **mảnh cấu hình**, không phải file Java độc lập. Cần import `org.springframework.security.authentication.CachingUserDetailsService`, `org.springframework.security.core.userdetails.UserDetailsService`, `org.springframework.security.core.userdetails.UserCache`, `@Bean`; phải xác định rõ bean nào làm delegate để tránh vòng lặp dependency.

Một lựa chọn khác:

~~~java
@Override
@Cacheable(cacheNames = "userDetails", key = "#username")
public UserDetails loadUserByUsername(String username) {
    return accountRepository.loadAsUserDetails(username);
}
~~~

Đây là minh họa cách sử dụng annotation; trong ứng dụng thực cần `@EnableCaching` và `CacheManager` được cấu hình. Với cache key, username phải canonicalize nhất quán với lookup. Khi multi-tenant, dùng `tenantId + userId` hoặc key có namespace phù hợp, tránh role của user tenant khác.

### 7.1. Vấn đề credential erasure

Tài liệu Spring Security chỉ ra khi cache `UserDetails` phục vụ xác minh password, một số cấu hình cần chú ý `eraseCredentialsAfterAuthentication` để tránh object cache bị mất password hash cần thiết cho login sau.

**Đánh đổi:** giữ password hash trong cache lâu hơn làm tăng dữ liệu bí mật cần bảo vệ. Không tắt credential erasure toàn cục chỉ vì muốn cache role/profile. Ưu tiên:
- tách **identity/authorization projection** không chứa password hash khỏi password verification data;
- chỉ cache những trường cần thiết;
- giữ TTL ngắn, kiểm soát quyền truy cập cache;
- test sau một lần authentication để xác nhận cache không hỏng dữ liệu;
- cân nhắc không cache password hash nếu chưa có yêu cầu hiệu năng rõ.

### 7.2. UserCache và session là hai thứ khác nhau

~~~text
UserDetails cache --(trong lần login/lookup)--> Authentication
                                              |
                                              v
                                       Session/SecurityContext

UserDetails cache evict(user42)
        |
        +--> login/lookup SAU ĐÓ có thể đọc user mới
        |
        └--> KHÔNG tự làm mới Authentication đã nằm trong session
~~~

Muốn hạ quyền có hiệu lực ở session đã tồn tại, cần chính sách:
- invalidate session đang mở;
- buộc reauthentication/refresh context;
- hoặc **live-check authorization** ở mỗi protected action;
- có thể kết hợp version/epoch để chặn session cũ.

Không chỉ gọi `@CacheEvict` rồi coi mọi request đang đăng nhập đã nhận quyền mới.

## 8. Phân biệt “disable login” và “disable current access”

Trong Spring Security, `UserDetails.isEnabled()`, `isAccountNonLocked()`, `isAccountNonExpired()` được authentication provider xem xét khi thực hiện **authentication**.

Ví dụ:
1. Alice đã login lúc 09:00; session đã có `Authentication`.
2. Quản trị viên đặt `enabled=false` lúc 09:10.
3. `UserDetailsService` cho login mới trả `disabled=true` (hoặc `isEnabled() == false`), nên login mới có thể bị từ chối.
4. **Session cũ vẫn có Authentication** và có thể vào endpoint không kiểm tra trạng thái account hiện hành.

Muốn vô hiệu hóa session cũ có một số cách:
- Tìm và invalidate các sessions của subject qua session registry/distributed session store.
- Kiểm tra `active`/authorization epoch trong request, từ chối khi bị khóa.
- Revoke access token/refresh token, phối hợp các resource servers.
- Trong hành động rất nhạy cảm, kiểm tra trạng thái account ngay trong transaction nghiệp vụ.

**Không tự động đồng nhất tài khoản bị khóa do sai password với compromise revoke:** sản phẩm có thể muốn người dùng đang có session hợp lệ tiếp tục tác vụ giới hạn trong khi lockout chỉ ngăn password guessing. Cần định nghĩa policy rõ theo từng trạng thái `LOCKED`, `DISABLED`, `SUSPENDED`, `DELETED`.

## 9. SessionRegistry và Spring Session: quản lý nhiều phiên

Spring Security có `SessionRegistry` để theo dõi sessions, `SessionInformation.expireNow()` để đánh dấu expired trong ngữ cảnh quản lý phiên phù hợp, và các cơ chế concurrent session control.

Lưu ý:
- `SessionRegistryImpl` thông thường hoạt động trong bộ nhớ của ứng dụng; nó không tự biết session ở replica khác.
- `SessionInformation.expireNow()` đánh dấu session và `ConcurrentSessionFilter`/infrastructure liên quan xử lý ở request tiếp theo; **không nhất thiết hủy ngay một job đang chạy**.
- `HttpSession.invalidate()` áp dụng cho session đang có; tìm tất cả session của một user trên nhiều node đòi session store/registry nhất quán.
- Với Spring Session + Redis, có thể dùng các cơ chế session repository/registry tương ứng, nhưng cần triển khai theo phiên bản thư viện và test trên cluster; không giả định mọi bean `SessionRegistry` tự động được bật.
- Custom principal dùng làm khóa registry cần `equals/hashCode` nhất quán; thay class principal hoặc username có thể khiến enumerate sessions không đầy đủ.

**Một cơ chế “log out all devices” nên được kiểm thử xuyên nhiều replicas**, bao gồm session trong browser cũ, cookie remember-me, refresh token và WebSocket connections. Chỉ xóa local cache JVM không đáp ứng yêu cầu này.

## 10. JWT: token còn hạn không đồng nghĩa quyền chưa thay đổi

### 10.1. Luồng mặc định

~~~text
T0: Authorization Server phát JWT:
    sub=alice, scope=["orders.read","orders.write"],
    exp=T0+15 phút, authorizationVersion=3

T1: DB bỏ quyền orders.write và tăng version=4

T2: Client gửi JWT cũ tới resource server

Nếu resource server chỉ verify signature/exp/iss:
    JWT vẫn có scope "orders.write" và có thể được chấp nhận.

Nếu resource server tra current version=4:
    authzVersion trong JWT là 3 => reject/step-up/reissue.
~~~

Spring Security Resource Server mặc định xác minh JWT và map scopes theo cấu hình, **không tự tra DB mỗi request để biết role vừa đổi**. Muốn version validation phải thêm kiểm tra riêng.

### 10.2. Các lựa chọn chiến lược

| Chiến lược | Ưu điểm | Giới hạn |
|---|---|---|
| Access token TTL ngắn | Giới hạn cửa sổ staleness của claims | Không thu hồi ngay nếu chưa hết hạn |
| Introspection mỗi request | Có thể phản ánh active/revocation gần hiện thời | Thêm network dependency; introspection cache có độ trễ |
| Token `jti` denylist | Thu hồi token cụ thể trước expiry | Cần store lookup/sync và TTL denylist |
| Subject `tokenVersion` / epoch | Thu hồi hàng loạt tokens của account | Request phải so version hiện hành, không chỉ tin claim |
| `authorizationVersion` | Phát hiện quyền thay đổi | Cần chính sách refresh token và giải quyết lag |
| Recalculate server-side permissions | Không tin role claim cũ | DB/cache load và consistency |
| Revoke refresh tokens | Không cho cấp access token mới | Access token đã phát có thể còn tồn tại |
| Sender-constrained token | Giảm rủi ro token bị sao chép | Không tự giải quyết thay đổi role/status |

**Không ghi đè `exp` trên server bằng tưởng tượng:** JWT đã ký không thể “sửa payload cũ trong chỗ đang cầm”. Cần vô hiệu hóa theo chính sách hoặc cấp token mới sau khi user tiếp tục đủ điều kiện.

### 10.3. Quy tắc an toàn về token version

Có thể lưu `token_version` và `authorization_version` trong DB:
- `token_version`: tăng khi cần revoke toàn bộ session/token của user.
- `authorization_version`: tăng khi role/group/entitlement thay đổi.
- Access token mang hai giá trị như signed claims.
- Resource server kiểm tra signed token **và** đọc phiên bản hiện tại từ nguồn đáng tin.

**Nếu chỉ nhúng version vào JWT nhưng không kiểm tra với current version, hoàn toàn không có tác dụng thu hồi.**

Cache phiên bản hiện tại cũng có thể stale. Với endpoint cần hiệu lực dưới vài giây, current-version cache phải được thiết kế đáp ứng SLA, hoặc read nguồn strongly consistent.

## 11. Redis/local cache: cache-aside và invalidation

### 11.1. Cache-aside

~~~text
GET authz:user42:
  local/Redis hit → return snapshot
             miss → SELECT DB → store snapshot with TTL

UPDATE roles user42:
  BEGIN
     UPDATE account_roles...
     UPDATE user.authz_version = authz_version + 1
  COMMIT
  publish invalidate(user42, newVersion)
~~~

Cache-aside phổ biến vì giảm DB load. Nhưng việc `UPDATE DB` rồi `cache.evict` không phải phép toán nguyên tử xuyên hai hệ thống.

### 11.2. Hai tình huống race

**Race A — stale read trước invalidate:**

~~~text
Reader: SELECT old roles từ DB trước commit
Writer: COMMIT new roles
Writer: EVICT cache
Reader: PUT old roles vào cache SAU EVICT

Kết quả: cache cũ lại xuất hiện cho tới TTL tiếp theo.
~~~

**Race B — event đến sai thứ tự:**

~~~text
Version 10 → 11 (grant)
Version 11 → 12 (revoke)

Event version 12 được nhận trước event version 11.
Nếu handler ghi đè snapshot bằng "event mới nhất vừa nhận",
cache có thể quay về version 11 dù DB đang ở 12.
~~~

### 11.3. Giảm rủi ro race

- **Versioned key:** lưu `authz:{userId}:{version}`, đọc version hiện tại rồi chỉ dùng snapshot đúng version. Đảm bảo current-version lookup có SLA.
- **Monotonic version:** event handler chỉ nhận phiên bản lớn hơn hiện có; không ghi đè dữ liệu mới bằng phiên bản thấp.
- **Transactional outbox:** ghi DB thay đổi và một outbox event cùng transaction; publisher phát event sau commit và retry an toàn.
- **TTL hữu hạn:** kể cả event bị mất, cache sẽ hội tụ; nhưng TTL phải phù hợp SLA và chỉ cho lớp có rủi ro chấp nhận được.
- **Invalidate across nodes:** pub/sub hoặc queue có retry; cache local phải nhận event, không chỉ Redis shared cache.
- **Fail-closed critical path:** nếu không kiểm tra được current role/status, không cho thao tác nhạy cảm dựa trên dữ liệu cũ.
- **Thận trọng với negative caching:** một account vừa được tạo/kích hoạt có thể bị cache là “không tồn tại/disabled” quá lâu.

**Không giả định Redis Pub/Sub mang tính durable message delivery.** Nếu consumer offline, message có thể bị mất. Cần TTL, reconciliation, outbox hoặc stream có chính sách retry theo nhu cầu.

## 12. Chọn cache key đúng định danh

Một cache key chỉ có username như `user:alice` có thể sai trong hệ thống multi-tenant hoặc khi user đổi email:

~~~text
tenant-A / alice → ROLE_ADMIN
tenant-B / alice → ROLE_VIEWER

SAI: cache key = "alice"
ĐÚNG: cache key = "tenant-A:user-42:authz-v7"
      cache key = "tenant-B:user-99:authz-v3"
~~~

Khuyến nghị:
- Dùng **immutable user ID**, tenant ID và version/policy namespace.
- Không dùng email làm khóa duy nhất nếu email có thể đổi.
- Khi đổi username/email, invalidate aliases và mapping caches.
- Không lấy tenant từ `X-Tenant-Id` do client tự gửi để tạo quyền; tenant trong cache key phải được xác minh với principal/session.
- Key Redis không nên chứa email/PII nếu không cần; log key/correlation ID an toàn.
- Với role theo resource, cache key có thể cần `resourceId`, `action`, `policyVersion` và owner version.

Nếu dùng chung cache với nhiều môi trường (dev/staging/prod), luôn có namespace theo môi trường; không cho cache quyền của staging rơi vào production.

## 13. Ví dụ Java 17 độc lập: snapshot cũ và version guard

Đoạn này chạy bằng JDK 17, không phụ thuộc Spring. Nó mô phỏng một session có role ADMIN từ lần login, sau đó database giảm quyền. Chúng ta đối chiếu logic **chỉ tin session roles** với logic **kiểm tra version/current account**.

File `AuthorizationVersionDemo.java`:

~~~java
import java.util.Set;

public final class AuthorizationVersionDemo {
    record Account(long version, boolean active, Set<String> roles) {
        Account {
            roles = Set.copyOf(roles);
        }
    }

    record SessionSnapshot(long authzVersion, Set<String> roles) {
        SessionSnapshot {
            roles = Set.copyOf(roles);
        }
    }

    static boolean cachedOnlyAllowsAdmin(SessionSnapshot session) {
        return session.roles().contains("ADMIN");
    }

    static boolean currentAllowsAdmin(
            SessionSnapshot session, Account liveAccount) {
        return liveAccount.active()
                && session.authzVersion() == liveAccount.version()
                && liveAccount.roles().contains("ADMIN");
    }

    public static void main(String[] args) {
        Account first = new Account(
                7, true, Set.of("USER", "ADMIN"));
        SessionSnapshot session = new SessionSnapshot(
                first.version(), first.roles());

        System.out.println("initial=" + currentAllowsAdmin(
                session, first));

        Account demoted = new Account(
                8, true, Set.of("USER"));

        System.out.println("stale-session-alone="
                + cachedOnlyAllowsAdmin(session));
        System.out.println("version-guard-after-demotion="
                + currentAllowsAdmin(session, demoted));

        SessionSnapshot fresh = new SessionSnapshot(
                demoted.version(), demoted.roles());
        System.out.println("fresh-session-after-demotion="
                + currentAllowsAdmin(fresh, demoted));

        Account disabled = new Account(
                9, false, Set.of("USER"));
        System.out.println("after-disable="
                + currentAllowsAdmin(fresh, disabled));
    }
}
~~~

Chạy:

~~~bash
javac AuthorizationVersionDemo.java
java AuthorizationVersionDemo
~~~

**Stdout chính xác:**

~~~text
initial=true
stale-session-alone=true
version-guard-after-demotion=false
fresh-session-after-demotion=false
after-disable=false
~~~

Điểm học tập:
- `stale-session-alone=true` cho thấy nguy cơ nếu quyết định quyền **chỉ dựa vào cached role**.
- Version tăng khiến snapshot cũ bị từ chối. Nhưng điều đó chỉ có ý nghĩa vì `currentAllowsAdmin` thực sự nhận **current account version**.
- Sau khi login lại và nhận snapshot mới, Alice không còn ADMIN.
- Disable account chặn thao tác ngay cả khi session có dữ liệu lịch sử.
- Demo **không mô phỏng cache phân tán hoặc thực thi request thật**; phần sau cho ví dụ Spring Boot.

## 14. Spring Boot 3.x / Spring Security 6.x: kiểm tra quyền hiện hành mỗi request

Demo sau chạy với Java 17, Spring Boot 3.5.x và Spring Security 6.5.x. Nó dùng **form login** và một in-memory account store chỉ để test. Khi Alice đăng nhập, Spring tạo session và Authentication chứa roles tại thời điểm login. Sau đó test “hạ quyền” ở store và gửi lại request **với đúng session cũ**.

Endpoint `/admin` sử dụng `AuthorizationManager` tùy chỉnh đọc account hiện hành thay vì chỉ `hasRole("ADMIN")` trên session cũ. Endpoint `/me` cũng kiểm tra account còn enabled.

**Giới hạn:** in-memory store không đồng bộ nhiều replica, test không sử dụng Redis/PostgreSQL, không revoke session thật, không có persistence hoặc cross-service authorization. Điểm minh họa là **đường kiểm tra quyền thực thi ở request**, không phải một hệ quản trị tài khoản production.

### 14.1. Cấu trúc project

~~~text
fresh-authorization-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/freshauthz/
    │   ├── FreshAuthorizationApplication.java
    │   ├── AccountSnapshot.java
    │   ├── InMemoryIdentityStore.java
    │   ├── LiveAuthorization.java
    │   ├── SecurityConfiguration.java
    │   └── AccountController.java
    └── test/java/com/example/freshauthz/
        └── AuthorizationChangeTest.java
~~~

### 14.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>fresh-authorization-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Boot BOM sẽ quản lý phiên bản tương thích của Spring Security. Test dùng `formLogin()` postprocessor của `spring-security-test`; không cần khởi chạy browser thật.

### 14.3. `FreshAuthorizationApplication.java`

~~~java
package com.example.freshauthz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FreshAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(FreshAuthorizationApplication.class, args);
    }
}
~~~

### 14.4. `AccountSnapshot.java`

~~~java
package com.example.freshauthz;

import java.util.Set;

public record AccountSnapshot(
        String username,
        String encodedPassword,
        Set<String> roles,
        boolean enabled,
        long authorizationVersion) {

    public AccountSnapshot {
        roles = Set.copyOf(roles);
    }
}
~~~

Record là immutable snapshot: mỗi thay đổi tạo object mới có version lớn hơn. Dùng `Set.copyOf` tránh một thread khác sửa roles trong cùng object.

### 14.5. `InMemoryIdentityStore.java`

~~~java
package com.example.freshauthz;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public final class InMemoryIdentityStore {

    private final PasswordEncoder encoder;
    private final ConcurrentMap<String, AccountSnapshot> accounts =
            new ConcurrentHashMap<>();

    public InMemoryIdentityStore(PasswordEncoder encoder) {
        this.encoder = encoder;
        reset();
    }

    public AccountSnapshot find(String username) {
        return accounts.get(username);
    }

    public void reset() {
        accounts.clear();
        accounts.put("alice", new AccountSnapshot(
                "alice",
                encoder.encode("local-only-demo-password"),
                Set.of("USER", "ADMIN"),
                true,
                1L));
    }

    public void demote(String username) {
        accounts.computeIfPresent(username, (id, old) ->
                new AccountSnapshot(
                        old.username(),
                        old.encodedPassword(),
                        Set.of("USER"),
                        old.enabled(),
                        old.authorizationVersion() + 1L));
    }

    public void disable(String username) {
        accounts.computeIfPresent(username, (id, old) ->
                new AccountSnapshot(
                        old.username(),
                        old.encodedPassword(),
                        old.roles(),
                        false,
                        old.authorizationVersion() + 1L));
    }
}
~~~

Store được tạo với một password giả **chỉ dùng trong test local**; không phải account/credential production. `ConcurrentHashMap.computeIfPresent` bảo vệ một key trong **một JVM**, không thay DB transaction hay Redis atomic operation xuyên các instance.

### 14.6. `LiveAuthorization.java`

~~~java
package com.example.freshauthz;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public final class LiveAuthorization {

    private final InMemoryIdentityStore accounts;

    public LiveAuthorization(InMemoryIdentityStore accounts) {
        this.accounts = accounts;
    }

    public AuthorizationDecision check(
            Authentication authentication, String requiredRole) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        AccountSnapshot current = accounts.find(authentication.getName());

        boolean granted = current != null
                && current.enabled()
                && (requiredRole == null
                    || current.roles().contains(requiredRole));

        return new AuthorizationDecision(granted);
    }
}
~~~

Điểm mấu chốt: `roles` và `enabled` ở đây lấy từ **current account snapshot trong store**, **không** lấy từ `authentication.getAuthorities()` cũ trong session. Nếu store là DB hoặc read model nhất quán, rule sẽ phản ánh thay đổi theo độ tươi của store đó.

Nếu store bị unavailable, đoạn code production phải có xử lý lỗi và **deny cho hành động nhạy cảm**; tuyệt đối không fallback tự động sang role cũ. Test này không đánh giá SLAs, transaction consistency hoặc caching.

### 14.7. `SecurityConfiguration.java`

~~~java
package com.example.freshauthz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(InMemoryIdentityStore accounts) {
        return username -> {
            AccountSnapshot current = accounts.find(username);
            if (current == null) {
                throw new UsernameNotFoundException("Invalid credentials");
            }

            return User.withUsername(current.username())
                    .password(current.encodedPassword())
                    .roles(current.roles().toArray(String[]::new))
                    .disabled(!current.enabled())
                    .build();
        };
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            LiveAuthorization current) throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .requestMatchers(HttpMethod.GET, "/admin")
                            .access((authentication, context) ->
                                current.check(authentication.get(), "ADMIN"))
                        .requestMatchers(HttpMethod.GET, "/me")
                            .access((authentication, context) ->
                                current.check(authentication.get(), null))
                        .anyRequest().denyAll())
                .formLogin(form -> form.permitAll())
                .build();
    }
}
~~~

- `UserDetailsService` dùng current account để xác thực login mới; disabled user không thể đăng nhập bằng password sau khi disable.
- `AuthorizationManager` ở `/admin` dùng current store mỗi request, không chỉ kiểm tra role đã chụp ở login.
- `/me` từ chối user đã disabled, dù session trước đó còn Authentication.
- `anyRequest().denyAll()` không mở thêm endpoint bên ngoài demo.
- `formLogin(form -> form.permitAll())` tạo và cho phép truy cập trang/processing login theo Spring Security.
- **CSRF vẫn bật**. Login form/test postprocessor phải mang CSRF token phù hợp.
- Trong production, kiểm tra status/quyền phải bao phủ **mọi protected endpoint, method security, WebSocket, queue worker, gRPC, batch jobs**, không chỉ hai routes mẫu.

### 14.8. `AccountController.java`

~~~java
package com.example.freshauthz;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    private final InMemoryIdentityStore accounts;

    public AccountController(InMemoryIdentityStore accounts) {
        this.accounts = accounts;
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        AccountSnapshot current = accounts.find(authentication.getName());
        return Map.of(
                "username", current.username(),
                "enabled", current.enabled(),
                "authorizationVersion", current.authorizationVersion());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("result", "admin-access-granted");
    }
}
~~~

Controller không cung cấp endpoint công khai để tự thay quyền; test sẽ gọi trực tiếp store. Việc phân quyền đặt **trước controller**. Production vẫn cần object-level authorization tại service/domain cho từng resource.

### 14.9. JUnit test: session cũ bị hạ quyền và disable

File `src/test/java/com/example/freshauthz/AuthorizationChangeTest.java`:

~~~java
package com.example.freshauthz;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationChangeTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    InMemoryIdentityStore accounts;

    @BeforeEach
    void reset() {
        accounts.reset();
    }

    private MockHttpSession loginAlice() throws Exception {
        MvcResult result = mvc.perform(
                formLogin()
                    .user("alice")
                    .password("local-only-demo-password"))
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        HttpSession session = result.getRequest().getSession(false);
        return (MockHttpSession) session;
    }

    @Test
    void removingRoleAppliesToAlreadyLoggedInSession()
            throws Exception {

        MockHttpSession session = loginAlice();

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isOk());

        accounts.demote("alice");  // DB-like role change.

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.authorizationVersion").value(2));
    }

    @Test
    void disabledUserCannotKeepAccessThroughOldSession()
            throws Exception {

        MockHttpSession session = loginAlice();

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk());

        accounts.disable("alice");

        mvc.perform(get("/me").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void disabledUserCannotPerformNewPasswordLogin()
            throws Exception {

        accounts.disable("alice");

        mvc.perform(formLogin()
                .user("alice")
                .password("local-only-demo-password"))
            .andExpect(unauthenticated());
    }

    @Test
    void authorizedUserInitiallyHasAdminAccess()
            throws Exception {

        MockHttpSession session = loginAlice();

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value(
                    "admin-access-granted"));
    }
}
~~~

Chạy:

~~~bash
mvn clean test
~~~

**Kỳ vọng:** 4 test methods PASS nếu project/dependencies và cấu hình Spring Boot/Security tương thích. Không có stdout cố định cho Maven vì phụ thuộc vào môi trường và phiên bản Maven Surefire.

**Ý nghĩa của hai bài test chính:**
- Session của Alice được tạo **trước** khi hạ role. Việc `/admin` chuyển từ 200 sang 403 với cùng session chứng tỏ endpoint không chỉ nhìn vào authority snapshot cũ.
- Khi user bị disabled, `/me` từ chối cùng session cũ; login mới cũng bị từ chối nhờ UserDetails trạng thái hiện hành.

**Điểm chưa được giải quyết bởi demo:** session cookie cũ chưa bị xóa tại nguồn, và các request đã bắt đầu trước lúc thay role có thể vẫn hoàn thành. Nếu ứng dụng có endpoint khác chỉ dùng `hasRole` trên session snapshot, endpoint đó vẫn có thể stale. Production cần policy thống nhất và cơ chế revoke/session-version tùy SLA.

## 15. Dùng authorizationVersion / security epoch trong production

Đọc DB roles ở mỗi request có thể tốn tài nguyên. Một biến thể dùng **phiên bản monotonic**:

~~~sql
CREATE TABLE app_accounts (
    user_id                BIGINT PRIMARY KEY,
    enabled                BOOLEAN NOT NULL,
    authorization_version BIGINT NOT NULL DEFAULT 1,
    token_version         BIGINT NOT NULL DEFAULT 1,
    updated_at            TIMESTAMPTZ NOT NULL
                          DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE account_roles (
    user_id BIGINT NOT NULL REFERENCES app_accounts(user_id),
    role    VARCHAR(120) NOT NULL,
    PRIMARY KEY (user_id, role)
);
~~~

Khi thay role:

~~~sql
BEGIN;

DELETE FROM account_roles
 WHERE user_id = 42 AND role = 'ADMIN';

UPDATE app_accounts
   SET authorization_version = authorization_version + 1,
       updated_at = CURRENT_TIMESTAMP
 WHERE user_id = 42;

COMMIT;
~~~

Việc update roles và version phải **cùng một transaction**, để không xuất hiện DB role đã đổi nhưng version vẫn cũ hoặc ngược lại.

Khi user login, Authentication/session có thể mang snapshot `authorizationVersion=17`; ở mỗi request:
1. Đọc `currentAuthorizationVersion` từ nguồn đáng tin.
2. Nếu current > snapshot, **từ chối** hoặc refresh principal/authorities theo chính sách.
3. Nếu user disabled, từ chối bất kể version.
4. Nếu current == snapshot, chỉ chấp nhận theo policy có authority snapshot tương ứng.
5. Khi role grant/revoke, tăng version atomically.
6. Khi cần thu hồi toàn bộ tokens, tăng `tokenVersion` riêng.

**Không lưu quyền vào một biến `static` chung cho tất cả users**, và không dùng timestamp đơn thuần làm version nếu đồng hồ/độ phân giải có thể trùng. Một integer increment atomically trong DB dễ so sánh hơn.

### 15.1. Tại sao version guard thường fail closed?

Nếu session cũ ở version 17 và database đã ở 18, có hai cách:
- **Reject + reauthenticate/refresh:** đơn giản và an toàn, nhưng UX có thể bị gián đoạn.
- **Reload current authorities và xây lại SecurityContext:** mượt hơn, nhưng phải bảo đảm subject/tenant/session binding và lưu context chính xác. Một revalidation chỉ refresh role có thể không đủ khi account đã disabled hoặc credential bị thu hồi.

Với thay đổi giảm quyền hoặc compromise, mặc định nên deny cho sensitive endpoints cho tới khi refresh/reissue được chứng minh an toàn.

### 15.2. Version check có còn cần cache?

Có thể cache `currentVersion` trong Redis/local cache. Tuy nhiên phiên bản cũng có thể stale, nên hiệu lực thực tế vẫn bị giới hạn bởi:
- TTL/eviction của version cache;
- thời gian propagation;
- khả năng đọc consistent database;
- policy khi store không truy cập được.

Đối với quyền nhạy cảm, có thể luôn đọc version từ DB hoặc dùng kho trạng thái có latency và consistency được cam kết. Một token chứa `version=18` không thể tự chứng minh DB chưa lên 19.

## 16. Các bẫy khi cập nhật SecurityContext trực tiếp

Một số triển khai cố “đổi authorities của user đang login” bằng cách tạo `Authentication` mới:

~~~java
Authentication updated = UsernamePasswordAuthenticationToken.authenticated(
        existingPrincipal,
        null,
        refreshedAuthorities);
~~~

Đoạn trên là **minh họa API**, không phải phương án trọn vẹn.

Cần hiểu:
- `SecurityContextHolder` thường gắn với **request/thread hiện tại**, không tự truy cập context mọi browser/session.
- Spring Security 6 yêu cầu lưu context vào `SecurityContextRepository` trong nhiều trường hợp nếu muốn thay đổi tồn tại sau request.
- Không tự tạo `authenticated(...) = true` từ dữ liệu chưa xác minh hoặc tin roles client tự gửi.
- Principal có thể chứa account/tenant attributes cũ, không chỉ authorities; refresh phải đồng bộ trạng thái.
- Nếu nhiều session đang tồn tại, cập nhật context của một request **không cập nhật các session còn lại**.
- Dùng cache/multi-instance đồng thời, có thể có race ghi lại context phiên bản cũ sau khi đã refresh phiên bản mới.

Nếu chỉ cần hạ quyền khẩn cấp, **invalidate/revoke session và kiểm tra current version tại request boundary** thường dễ reasoning hơn việc sửa tất cả session objects.

## 17. Rollout trên nhiều instance và event-driven invalidation

Một kiến trúc đề xuất:

~~~text
Admin Service
    |
    | update roles/status + version
    v
Primary DB + Outbox (transaction)
    |
    | committed event, userId, version
    v
Event Publisher → Queue/Stream
    |
    +--> API Instance A: invalidate local role cache
    +--> API Instance B: invalidate local role cache
    +--> API Instance C: invalidate local role cache
    +--> Resource Server: revoke/refresh policy cache
    +--> Session/IdP Service: invalidate sessions/tokens
    |
    v
Monitoring: consumer lag, event loss/replay, enforcement probe
~~~

**Outbox event phải mang version và identity rõ ràng**, không chỉ “evict all caches” hoặc email string. Consumers cần idempotent và chịu được message trùng/lệch thứ tự; version thấp không được overwrite version cao.

Để giảm propagation delay:
- dùng change-data-capture/outbox thay vì gửi một event ngoài transaction rồi hy vọng cả hai thành công;
- đo consumer lag p95/p99;
- retry và dead-letter queue cho lỗi kéo dài;
- reconciliation job quét current DB version nếu event từng bị mất;
- tránh cache local không có TTL hoặc không có listener;
- bảo vệ event bus khỏi message giả khiến attacker yêu cầu grant/revoke trái phép.

**Không nên phát event “grant role” như một authority đáng tin** cho resource server chỉ từ một thông điệp không kiểm tra provenance; consumers nên xác minh version và state từ nguồn policy đáng tin.

## 18. Đo lường và đặt SLA hiệu lực quyền

Một bảng minh họa vận hành:

| Change type | Proposed SLA | Enforcement path | Cách đo |
|---|---|---|---|
| Thay display name | 60 giây | Profile cache TTL | UI/data freshness probe |
| Thêm quyền báo cáo | 60 giây | Event invalidation + TTL | Read API theo role mới |
| Thu hồi `ADMIN` | 5 giây | Current role/version read | Request cùng session trên từng replica |
| Disable compromised account | 5 giây hoặc theo risk policy | Revoke + current status/version | Old session, old JWT và refresh token tests |
| Password reset | Ngay với login mới; session theo policy | UserDetails cache evict, session/token revoke | Login password cũ và các session đã mở |
| Tenant membership removal | 5 giây ở API tenant-sensitive | Tenant scope live check | Truy cập resource cũ qua mọi đường |

Các con số ở trên là **SLA mẫu để thảo luận**, không phải bảo đảm của Spring Security, Redis, JWT hay chuẩn quốc tế. Phải đo:
- `authz_change_committed_at`, `authz_change_version`;
- `cache_invalidation_received_at` theo instance;
- `decision_account_version` và policy version của request;
- số request **được allow sau khi revoke commit**;
- thời gian từ commit đến deny hiệu lực;
- tỷ lệ lỗi store, fallback và authentication failures;
- staleness p50/p95/p99/max có kiểm tra;
- sự khác biệt giữa replica và network partitions.

Không log JWT, raw session cookies, password, email đầy đủ hoặc token ID có thể tái sử dụng. Dùng correlation IDs, stable pseudonymized account ID và metadata tối thiểu.

## 19. Thử nghiệm phân tán: cùng session, nhiều replica, cũ và mới

### 19.1. Kịch bản 1 — hạ quyền role

1. Login `alice` có `ADMIN`; ghi lại session và JWT được phát hành trong môi trường test.
2. Confirm `GET /admin` trả 200.
3. Gọi admin mutation để revoke `ADMIN`; chờ DB commit version tăng.
4. Gửi request `/admin` bằng **session/JWT cũ** vào từng replica (không dùng session mới).
5. Đo từ commit tới 403/401 theo policy.
6. Không cho fallback/caching ở gateway làm request cũ tiếp tục 200 ngoài SLA.
7. Bật delay/mất message invalidation để xem TTL/version check có chặn được không.

### 19.2. Kịch bản 2 — disable user

1. Login và tạo nhiều sessions/truy cập nhiều resource servers.
2. Disable user, commit transaction và tăng security epoch.
3. Kiểm tra login mới bị từ chối.
4. Kiểm tra tất cả sessions trước đó bị invalidate **hoặc** mọi protected route deny.
5. Kiểm tra bearer access token cũ và refresh token theo chính sách; không chỉ cookie form login.
6. Kiểm tra WebSocket/API job đã mở có bị ngắt hoặc reauthorize khi dùng tiếp.

### 19.3. Kịch bản 3 — stale cache reinsert

1. Thread A bắt đầu SELECT role version 4 rồi tạm dừng trước cache PUT.
2. Thread B commit version 5 và evict cache.
3. Cho A cache PUT version 4.
4. Bảo đảm request nhạy cảm **không** dùng version 4 khi DB đã ở 5.
5. Dùng monotonic/versioned writes hoặc current-version guard để test pass.

### 19.4. Kịch bản 4 — event out of order

1. Phát version 12 và 13, giao chúng cho consumer theo thứ tự 13 rồi 12.
2. Cache phải giữ version 13 hoặc fetch lại DB, không quay về 12.
3. Dùng retry và duplicate delivery; việc áp dụng 13 hai lần phải idempotent.
4. Simulate consumer offline; kiểm tra reconciliation/TTL.

### 19.5. Kịch bản 5 — cache backend outage

1. Vô hiệu Redis/read model trong test.
2. Thao tác nhạy cảm phải **fail closed** hoặc dùng current DB read có kiểm soát.
3. Thao tác không nhạy cảm có thể degrade gracefully theo SLA.
4. Không để một exception handler chung chuyển “không biết quyền” thành `permitAll`.

### 19.6. Kịch bản 6 — giao dịch đang chạy

1. Alice bắt đầu `POST /admin/transfer`, vượt kiểm tra quyền đầu request.
2. Role ADMIN bị rút trước khi giao dịch commit.
3. Nếu policy yêu cầu chặn commit sau revoke, service phải kiểm tra current role/version **trong cùng transaction** trước write.
4. Nếu operation sử dụng external payment/job queue, phải thiết kế approval/transaction state và kiểm tra ở consumer.

**Một request được chấp nhận trước revoke không thể tự “quay ngược thời gian”.** Cần quyết định nghiệp vụ về in-flight operations chứ không hứa zero-latency/instant cancellation vô điều kiện.

## 20. Ma trận test tổng hợp

| Test | Điều cần xác nhận |
|---|---|
| UserDetails cache hit | Không gọi DB lặp lại ngoài chính sách |
| Cache miss | Đọc và populate đúng user/tenant |
| Cache entry expired | Load phiên bản mới |
| Cache invalidation sau role update | Entry cũ không được dùng nếu policy đòi current |
| Role revoke khi session còn sống | Endpoint admin deny theo SLA |
| Role grant khi session cũ | Có chính sách refresh/relogin rõ, không lạm cấp |
| Account disabled khi session còn sống | Các request protected bị deny |
| Account disabled trước login | Password login mới bị chặn |
| Password changed | Cache hash cũ bị evict, password mới dùng được |
| JWT còn hạn chứa role cũ | Deny nếu vượt authorizationVersion/current-role policy |
| Refresh token revoked | Không cấp access token mới |
| Opaque introspection cache stale | Tôn trọng TTL/SLA, có revoke path |
| SessionRegistry chỉ local | Cross-replica test phát hiện không bao phủ toàn cluster |
| Cache event mất | TTL/reconciliation khôi phục |
| Event nhận sai thứ tự | Không downgrade version |
| Cache-aside stale reinsert | Không nhận version cũ cho critical action |
| Multi-tenant same username | Cache không trộn quyền |
| User đổi username/email | Identity alias/cache invalidation đúng |
| Role update đồng thời | Version monotonic, không lost update |
| Event producer lỗi sau DB commit | Outbox retry, không mất invalidation |
| Redis unavailable | Critical path fail closed |
| Old cookie sau logout/revoke | Không còn quyền hoạt động |
| Method security `@PreAuthorize` | Không bypass live policy qua route khác |
| Resource/object-level entitlement | Check đúng resource, không chỉ role chung |
| Queue worker sau role revoke | Revalidate ở điểm thực thi nếu nghiệp vụ yêu cầu |
| Change rights p99 | Đạt SLA ở tất cả replicas và token types |

**Đừng chỉ test “cache đã xóa” bằng assert Redis key không tồn tại.** Acceptance criteria phải là **request/operation không còn thực hiện được quyền bị thu hồi** trong thời gian đã cam kết.

## 21. Lỗi vận hành thường gặp

1. **Xóa UserDetails cache rồi tuyên bố session cũ đã cập nhật.** Session có snapshot riêng.
2. **Đặt JWT TTL dài và nhúng roles nhưng hứa revoke tức thì.** Claims không tự đổi.
3. **Chỉ revoke refresh token.** Access token cũ có thể còn hạn.
4. **Chỉ xóa cache trên một node.** Các replica khác vẫn có dữ liệu cũ.
5. **Không định nghĩa SLA.** Không thể chứng minh vận hành đúng hay sai.
6. **Đặt TTL trên Redis nhưng session TTL lâu hơn.** Lớp giữ quyền lâu nhất vẫn có thể chi phối.
7. **Cache key theo username toàn cục trong multi-tenant.** Dẫn đến nhầm quyền.
8. **Tin `X-User-Role` header client gửi.** Bypass trust boundary.
9. **Dùng event version thấp ghi đè version cao.** Event ordering gây rollback quyền.
10. **Publish invalidation trước DB commit.** Consumer có thể đọc state cũ rồi cache lại.
11. **Chỉ update DB, bỏ qua outbox/Redis.** Event có thể mất.
12. **Không xử lý race của cache-aside PUT sau EVICT.** Stale data tái xuất hiện.
13. **Cache negative account lookup quá lâu.** User được kích hoạt vẫn bị từ chối.
14. **Tắt credential erasure toàn cục chỉ để cache role.** Tăng rủi ro lộ password hash.
15. **Coi `enabled=false` tự dừng mọi session.** Chỉ authentication lúc login có thể dùng flag đó.
16. **Không kiểm tra permission sau queue enqueue.** Job chạy bằng quyền đã thu hồi.
17. **Chỉ kiểm tra `hasRole` ở controller, quên method/service authorization.** Một API khác có thể bypass.
18. **Bỏ trạng thái tenant/ownership.** Role còn đúng nhưng quyền trên object đã đổi.
19. **Không invalidate session khi account compromise.** Old bearer session tiếp tục được dùng.
20. **Bỏ qua store outage/fail-open.** Khi Redis/DB lỗi, hệ thống có thể cho phép bằng quyền cũ.
21. **Dùng timestamp client làm version.** Có thể bị giả hoặc xung đột giờ.
22. **Log cookies/JWT để đo propagation.** Tự tạo rò rỉ bearer credentials.
23. **Không đo các request đang xử lý trước commit.** Đưa ra cam kết “ngay lập tức” không có căn cứ.
24. **Chỉ test một replica/one token type.** Không chứng minh chính sách toàn hệ thống.

## 22. Checklist thiết kế và vận hành production

- [ ] Xác định nguồn sự thật cho identity, roles, tenant, permissions và account status.
- [ ] Phân loại mức độ rủi ro của mỗi thay đổi: grant, revoke, disable, compromise, password reset.
- [ ] Có SLA hiệu lực cụ thể; đo từ database commit tới enforcement.
- [ ] Inventory đầy đủ các lớp snapshot/cache: UserDetails, Authentication/session, JWT, introspection, gateway, ACL, downstream.
- [ ] Dùng key theo immutable user ID + tenant/context + version, tránh trộn quyền.
- [ ] Caches có TTL, maximum size, eviction và policy khi miss/outage.
- [ ] Không tự động cho phép critical request khi không lấy được current state.
- [ ] Có current account status/role hoặc authorization version check ở endpoints nhạy cảm.
- [ ] Session/tokens cũ được revoke/refresh theo đúng policy.
- [ ] JWT signature/expiry validation không bị hiểu nhầm là quyền mới nhất.
- [ ] Token claims versions được so với current version, không chỉ được nhúng cho đẹp.
- [ ] Mọi thay đổi quyền tăng monotonic version trong cùng DB transaction.
- [ ] Invalidation được publish sau commit, qua outbox/retry khi cần.
- [ ] Consumers chịu được event duplicate/out-of-order, không ghi đè version mới bằng cũ.
- [ ] Cửa sổ race cache-aside stale reinsert được test.
- [ ] Có chiến lược cho các request đang xử lý và queued jobs.
- [ ] Account disabled được chặn ở login mới và các sessions/tokens cũ.
- [ ] UserDetails/password-hash cache cân nhắc credential erasure và quyền truy cập.
- [ ] Method security, HTTP filter và object-level checks có chính sách nhất quán.
- [ ] Test xuyên nhiều replicas, session stores, resource servers, cache outage và partition.
- [ ] Metrics: event lag, cache age/version, access allowed after revoke, enforcement latency p95/p99.
- [ ] Logs không có raw JWT, session cookie, password, refresh token hay dữ liệu cá nhân không cần thiết.
- [ ] Quy trình incident response có thể revoke user nhanh và kiểm chứng đã có hiệu lực.
- [ ] Kiến trúc bảo đảm rollout reader/writer/event consumer và rollback được đánh giá.

## 23. Ghi nhớ

**Một thay đổi quyền thành công trong database không tự làm mới mọi Authentication đang tồn tại.** UserDetails cache, HTTP session, JWT access token, introspection result và ACL cache là các lớp độc lập với thời gian tồn tại khác nhau.

Quy tắc thực hành:
1. **Identity xác định ai**, authorization state hiện hành xác định **được làm gì**.
2. **TTL giới hạn một lớp cache**, không tự bảo đảm SLA của cả hệ thống.
3. **Evict UserDetails không evict SecurityContext**; session phải được refresh/revoke hoặc bảo vệ bằng live authorization.
4. **JWT signature còn hợp lệ không có nghĩa role chưa bị rút**.
5. **Version/epoch chỉ hữu ích khi được so với nguồn hiện hành** và cập nhật nguyên tử.
6. **Critical action phải fail closed khi không thể kiểm tra quyền** theo SLA.
7. **Test bằng session/token cũ trên mọi replica sau revoke**, không chỉ nhìn Redis key/DB row.

Mục tiêu vận hành là biến câu “quyền đã bị thu hồi” thành một **đảm bảo có thể kiểm chứng**: request nào phải bị từ chối, bắt đầu từ khi nào, tại mọi thành phần nào và trong điều kiện lỗi nào.

## 24. Tài liệu tham khảo

1. [Spring Security 6.5 — Caching UserDetails](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/caching.html): `CachingUserDetailsService`, `UserCache`, `@Cacheable` và credential erasure.
2. [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextRepository`, explicit saving và session concurrency.
3. [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): validation JWT `iss/exp/nbf`, authorities và custom validators.
4. [Spring Security 6.5 — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection và active-token verification.
5. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationManager` và quyền theo HTTP request.
6. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@PreAuthorize` và authorization ở service boundary.
7. [Spring Security 6.5 — UserDetails / Account Flags](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/core/userdetails/UserDetails.html): account enabled/locked/expired semantics.
8. [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CacheEvict`, cache key và cách bật caching.
9. [Spring Session — Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): phân tán HTTP session giữa nhiều application nodes.
10. [Spring Framework — Transactional Outbox: nguyên lý transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): cơ chế transaction để phối hợp dữ liệu và sự kiện nghiệp vụ.
11. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifetime, invalidation và hijacking defenses.
12. [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): kiểm tra quyền tại từng request/action, deny-by-default và least privilege.
