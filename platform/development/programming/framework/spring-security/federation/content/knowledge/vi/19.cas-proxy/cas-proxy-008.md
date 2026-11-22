# StatelessTicketCache, thời hạn và giới hạn tái sử dụng kết quả xác thực proxy trong Spring Security CAS

**Bài toán:** Một CAS Proxy Ticket (**PT**) theo giao thức Central Authentication Service (**CAS**) chỉ hợp lệ cho **một lần thử kiểm chứng** tại CAS Server và được cấp cho **một service cụ thể**. Trong một ứng dụng stateless, client gọi API nhiều lần nhưng không sử dụng `HttpSession`, nên nếu gửi lại cùng PT và backend lần nào cũng hỏi CAS, các lần sau có thể nhận `INVALID_TICKET`. Spring Security cung cấp **`StatelessTicketCache`** để ghi nhớ **`CasAuthenticationToken` đã xác thực thành công** và cho phép server dùng lại kết quả đó trong một khoảng thời gian.

**Điểm quan trọng nhất:** **CAS không biến PT thành vé nhiều lần.** PT đã bị CAS consume ở lần validation đầu. Việc client tiếp tục dùng cùng chuỗi PT để gọi backend là **cơ chế tái sử dụng Authentication trong cache cục bộ của Spring Security**, không phải CAS xác minh lại mỗi lần. Điều này cải thiện hiệu năng nhưng **biến PT đã được cache thành bearer credential có thể replay tại chính ứng dụng**, đòi hỏi TTL ngắn, kiểm soát service/proxy chain/tenant, thẩm định quyền trên mỗi request và cơ chế thu hồi.

Bài thuộc **Spring Security – federation → CAS Proxy**, tập trung vào `StatelessTicketCache`, vòng đời cache, `SpringCacheBasedTicketCache` và `NullStatelessTicketCache`, giới hạn tái sử dụng, thời hạn, kiểm soát rủi ro, ví dụ Spring Security và Java 17 chạy được, kiểm thử và runbook.

## 1. Từ SSO đến CAS Proxy: vì sao cần PT?

Với web browser SSO thông thường:

1. Browser vào Portal A, được chuyển tới CAS `/login`.
2. CAS xác thực người dùng và cấp **Service Ticket (ST)** cho Portal A.
3. Portal A gọi `/serviceValidate` kiểm tra ST; sau xác thực thành công, Portal tạo local session.
4. Browser dùng session cookie của Portal cho những request tiếp theo.

Nhưng nếu Portal A cần truy cập backend Service B **thay mặt người dùng**, một cookie Portal không phải chứng cứ để B tin user; B cần credential phù hợp với B.

~~~text
Browser                   Portal A                  CAS                   API B
   |                         |                      |                     |
   |--- Login CAS ---------->|--- validate ST ----->|                     |
   |                         |<-- Assertion + PGT --|                     |
   |                         |                      |                     |
   |--- Xem dữ liệu -------->|--- /proxy(PGT,B) ---->|                     |
   |                         |<------ PT-B ----------|                     |
   |                         |--- API + PT-B ----------------------------->|
   |                         |                      |<--- /proxyValidate --|
   |                         |                      |--- authentication -->|
   |                         |<------------------ API response -----------|
~~~

**Proxy-Granting Ticket (PGT)** giúp Portal A xin **các PT riêng cho service B**. B xác minh PT-B với CAS, kiểm proxy chain và local authorization trước khi trả dữ liệu.

**Không nhầm:**

| Credential | Chức năng | Có thể dùng nhiều lần theo CAS Protocol? |
| --- | --- | --- |
| ST | User đăng nhập đúng một service | **Không**, one-time validation |
| PT | Service A đại diện user truy cập service B | **Không**, one-time validation |
| PGT | Service A xin PT cho các backend đã được phép | **Có**, trong thời hạn/policy cho phép |
| TGT | CAS SSO session của user | **Có**, để CAS cấp vé theo policy |
| TGC | CAS browser cookie để nhận diện phiên SSO | Được browser gửi lại CAS; không gửi thẳng API B |
| Cached CasAuthenticationToken | Kết quả xác thực **đã thành công tại B** | **Có thể** được B dùng lại theo cache policy |
| OAuth access token | Credential API theo OAuth2 | Cơ chế khác CAS, không tự tương đương PT |

**Mỗi PT vẫn phải được cấp cho backend service cụ thể và được kiểm chứng một lần**; PGT/PT không phải quyền quản trị chung.

## 2. Mâu thuẫn bề ngoài: PT một lần nhưng backend stateless lại nhận cùng PT nhiều lần?

Hai quy tắc đều đúng, nhưng thuộc **hai tầng khác nhau**.

**Tầng CAS Protocol:** PT được CAS Server tạo cho service B, có thời hạn ngắn và chỉ được validate **một lần**. Nếu B gọi `/proxyValidate` với PT đó lần thứ hai, CAS từ chối.

**Tầng ứng dụng Spring Security:** B đã lưu **một kết quả validation thành công** trong `StatelessTicketCache`. Khi client gửi lại chính PT đó, `CasAuthenticationProvider` có thể lấy **`CasAuthenticationToken` trong cache** và không gọi CAS nữa.

~~~text
Request 1: PT-X -> API B -> cache MISS
                          -> CAS /proxyValidate(PT-X,B)
                          -> SUCCESS, PT-X bị consume ở CAS
                          -> CasAuthenticationToken
                          -> cache.put(PT-X, auth)
                          -> xử lý request

Request 2: PT-X -> API B -> cache HIT
                          -> lấy auth đã xác thực
                          -> KHÔNG gọi CAS
                          -> xử lý request nếu còn được phép

Request 3: PT-X -> API B -> cache entry EXPIRED
                          -> thử validate CAS lại
                          -> CAS từ chối PT-X đã consume
                          -> phải xin PT MỚI
~~~

**Không đồng nhất “PT còn hợp lệ tại CAS” với “cache entry còn sống ở B”.** CAS đã invalid PT theo quy tắc one-time; ứng dụng duy trì một **kết quả xác thực độc lập** cho thời gian ngắn.

### Stateless nghĩa là gì ở đây?

Client không dựa vào một `HttpSession` giữa các request; nhưng nếu B dùng cache, **backend vẫn giữ một chút trạng thái**: map `ticket ID → Authentication`. Đây là **stateless theo giao thức client/server session**, không phải không tồn tại bất kỳ state nào.

## 3. Tại sao Spring Security có StatelessTicketCache?

Theo Javadoc Spring Security, `StatelessTicketCache` lưu kết quả xác thực cho **stateless connections**, bao gồm CAS service/proxy tickets. Khi một request dùng ticket chưa thấy, backend xác minh với CAS và tạo `CasAuthenticationToken`. Token đó được cache theo ticket string; các lần gửi lại có thể lấy token đã thành công từ cache.

Mục tiêu:

- Không cần browser session/cookie khi service gọi service.
- Tránh phải xin PT mới cho **từng** API request trong một đợt gọi ngắn.
- Giảm độ trễ CAS validation qua mạng, giảm tải CAS Server.
- Giữ được thông tin principal/authorities đã được kiểm chứng cho backend.
- Có cửa sổ sử dụng ngắn khi cần nhiều request sau một lần kiểm chứng.

**Giới hạn:** cache không có phép màu đảm bảo user vẫn active, PGT chưa bị thu hồi, group không đổi, service hiện tại chính là service đã được validation ban đầu hoặc ticket chưa bị đánh cắp. Đây là các thuộc tính cần chính sách và kiểm tra bổ sung.

## 4. Các lớp API và phương thức chính

| Lớp/interface | Vai trò |
| --- | --- |
| `org.springframework.security.cas.authentication.StatelessTicketCache` | Hợp đồng cache kết quả xác thực CAS stateless |
| `SpringCacheBasedTicketCache` | Adapter lưu `CasAuthenticationToken` vào `org.springframework.cache.Cache` |
| `NullStatelessTicketCache` | Không lưu entries; luôn miss, dùng khi không muốn cache |
| `CasAuthenticationProvider` | Quyết định lookup cache hay TicketValidator rồi tạo Authentication |
| `CasAuthenticationToken` | Authentication đã thành công, chứa credentials, principal, authorities và assertion |
| `CasServiceTicketAuthenticationToken` | Authentication request token cho CAS ticket trong các version hiện đại |
| `CasAuthenticationFilter` | Nhận `ticket` trên request và gọi AuthenticationManager |
| `ServiceProperties` | Cấu hình service URL và authenticateAllArtifacts |
| `ServiceAuthenticationDetailsSource` | Cung cấp service URL theo request khi xử lý ticket trên nhiều URL |
| `Cas20ProxyTicketValidator` | Validator gọi CAS proxy validation endpoint và kiểm proxy chain |

Các phương thức `StatelessTicketCache`:

~~~java
CasAuthenticationToken getByTicketId(String serviceTicket);
void putTicketInCache(CasAuthenticationToken token);
void removeTicketFromCache(String serviceTicket);
void removeTicketFromCache(CasAuthenticationToken token);
~~~

**Diễn giải:**

- `getByTicketId(...)`: trả token đã cache hoặc `null` nếu không có.
- `putTicketInCache(...)`: lưu token dưới khóa lấy từ `CasAuthenticationToken.getCredentials()`, tức ticket string.
- `removeTicketFromCache(String)`: loại một ticket khỏi cache, nhằm kết thúc khả năng tái sử dụng cục bộ.
- `removeTicketFromCache(token)`: loại theo credentials của token đã lưu.

Các thao tác này **không tự thu hồi TGT/PGT/PT tại CAS Server**, không phải bộ API logout toàn CAS. `removeTicketFromCache` có ý nghĩa **với cache của service**, không mặc nhiên là lệnh revoke credentials toàn federation.

## 5. NullStatelessTicketCache: lựa chọn không cache

`NullStatelessTicketCache` là implementation không có backing store:

- `getByTicketId` luôn trả `null`.
- `putTicketInCache` không làm gì.
- `removeTicketFromCache` không làm gì.
- Đây là lựa chọn mặc định của `CasAuthenticationProvider` trong các tài liệu Javadoc của Spring Security.

**Hệ quả:** nếu client tiếp tục gửi lại **cùng** PT đã dùng lần đầu, provider sẽ gọi CAS validation lần nữa và bị từ chối theo CAS one-time rule. Điều này có thể là **hành vi mong muốn** nếu an ninh yêu cầu **mỗi request có ticket mới**, không chấp nhận bearer replay tại service.

~~~java
// Mảnh cấu hình trong Spring Security CAS provider:
casAuthenticationProvider.setStatelessTicketCache(
        new NullStatelessTicketCache());
~~~

Đây là **đoạn minh họa cấu hình**; bean provider phải được wiring đầy đủ với TicketValidator, ServiceProperties, user details, AuthenticationManager/filter. Dùng đúng version dependency `spring-security-cas`.

**Khi chọn Null:** backend ít requests, latency CAS chấp nhận được, yêu cầu không dùng lại ticket cao, có nguồn PT mới cho mỗi request và không muốn giữ Authentication snapshot trong cache. Không có cache vẫn cần rate limit, TLS và validation đúng service/proxy chain.

## 6. SpringCacheBasedTicketCache: adapter, không tự quyết định TTL

`SpringCacheBasedTicketCache` nhận một **Spring Cache** qua constructor. Nó chuyển các thao tác put/get/remove của `StatelessTicketCache` thành thao tác lưu trữ.

~~~java
// Một org.springframework.cache.Cache có TTL đã được
// cấu hình qua cache provider:
Cache cache = cacheManager.getCache("casProxyAuth");
StatelessTicketCache tickets =
        new SpringCacheBasedTicketCache(cache);
~~~

Đây là snippet trong cấu hình Spring, không phải class độc lập. Đảm bảo `cache` không null. **Việc cache có timeout, eviction, distributed storage, serialization, at-rest encryption hay maximum size là quyết định của cache provider**, không phải `StatelessTicketCache` tự cung cấp tham số TTL.

**Cảnh báo:** `ConcurrentMapCache` hoặc `ConcurrentMapCacheManager` mặc định **không cung cấp TTL theo thời gian** như một expiry cache. Nếu dùng chúng trong production mà không có lớp hạn chế khác, một authentication có thể sống quá lâu. Chỉ tạo `SpringCacheBasedTicketCache` với backing `ConcurrentMapCache` **không đủ** để đảm bảo timeout.

### Cache provider thường dùng

| Provider | Gợi ý | Lưu ý |
| --- | --- | --- |
| **Caffeine** | Local in-memory TTL, max size, eviction | Mỗi node có cache riêng; phải xử lý revocation đa node |
| **Redis + Spring Cache** | Có TTL và tập trung qua nhiều nodes | Bảo vệ transport/credentials/serialization, kiểm invalidation |
| **JCache/Ehcache** | Có expiry policy theo cache | Kiểm compatibility theo Spring/Security version |
| **ConcurrentMapCache** | Thử nghiệm đơn giản | Không tự có TTL, không dùng mặc định cho auth cache production |
| **NullStatelessTicketCache** | Không cache | Gửi lại PT cũ sẽ bị CAS từ chối |

Không dựa vào một config kiểu `cacheName=casProxyAuth` mà suy ra TTL đã có. Phải xem implementation và chính sách expiry thực tế.

## 7. Cấu hình luồng stateless trong Spring Security CAS

Tài liệu Spring Security giải thích `CasAuthenticationProvider` phân biệt stateful/stateless theo authentication request; các luồng stateless dùng định danh đặc biệt **`CasServiceTicketAuthenticationToken.CAS_STATELESS_IDENTIFIER`** ở các version hiện đại, hoặc constant có tên tương tự ở `CasAuthenticationFilter` trong các tài liệu cũ.

Để nhận CAS tickets trên nhiều URL (không chỉ callback browser `/login/cas`), cấu hình cần chú ý:

1. `ServiceProperties.authenticateAllArtifacts = true`.
2. `CasAuthenticationFilter` dùng `ServiceProperties` đó.
3. `ServiceAuthenticationDetailsSource` tạo details chứa service URL đúng cho request.
4. `AuthenticationManager` đưa token tới đúng `CasAuthenticationProvider`.
5. Provider dùng **proxy-capable TicketValidator** và proxy-chain policy được phê duyệt.
6. Provider có `StatelessTicketCache` với TTL/eviction phù hợp nếu cần tái sử dụng.
7. Filter chain chỉ áp dụng cho các URL và phương thức thực sự sử dụng CAS PT.
8. Mỗi API vẫn có authorization riêng sau authentication.

~~~text
HTTP /api/orders?ticket=PT-X
            |
  CasAuthenticationFilter
    authenticateAllArtifacts=true
    identify stateless request
            |
  CasServiceTicketAuthenticationToken
      credentials=PT-X
      details=service URL
            |
  CasAuthenticationProvider
        |
        +-- cache.getByTicketId(PT-X)
        |       |
        |       +-- hit -> CasAuthenticationToken cũ
        |
        +-- miss -> Cas20ProxyTicketValidator
                  /proxyValidate(ticket=PT-X, service=...)
                  -> verify permitted proxy chain
                  -> load UserDetails/authorities
                  -> cache.put(...)
            |
  Spring SecurityContext cho request
            |
  Endpoint + method/object authorization
~~~

**Chú ý:** Nếu request đã có Authentication, filter có thể không xử lý ticket mới tùy chain và configuration. Cần test rõ nhiều filter chains, bearer/session mechanisms và thứ tự filters; không được để một authentication cũ của người dùng khác được tái sử dụng ngoài ý muốn.

## 8. Ví dụ Spring Boot 3/Spring Security 6.x: cache TTL ngắn bằng Caffeine

Ví dụ dưới đây minh họa một **phần cấu hình** dành cho ứng dụng Servlet dùng `spring-security-cas` và **Spring Cache + Caffeine**. Nó không phải một chương trình Java độc lập và không thể chạy nếu thiếu TicketValidator, CAS service registry, authentication filter, user details và security filter chain.

Mục tiêu ví dụ: cache kết quả CAS proxy authentication tối đa **2 phút tính từ lúc ghi** và giới hạn số entries. **Hai phút chỉ là lựa chọn minh họa, không phải default hoặc khuyến nghị cho mọi sản phẩm.**

Tệp `src/main/java/com/example/security/CasProxyCacheConfig.java`:

~~~java
package com.example.security;

import java.time.Duration;
import java.util.Objects;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.security.cas.authentication.SpringCacheBasedTicketCache;
import org.springframework.security.cas.authentication.StatelessTicketCache;

@Configuration
public class CasProxyCacheConfig {

    @Bean("casProxyCacheManager")
    CacheManager casProxyCacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("casProxyAuth");

        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(2)));

        return manager;
    }

    @Bean("casStatelessTicketCache")
    StatelessTicketCache casStatelessTicketCache(
            @Qualifier("casProxyCacheManager") CacheManager manager) {
        Cache cache = Objects.requireNonNull(
                manager.getCache("casProxyAuth"),
                "CAS proxy cache must be configured");

        return new SpringCacheBasedTicketCache(cache);
    }
}
~~~

Để biên dịch trong dự án Spring tương ứng, cần:

- Dependency **Spring Security CAS** và CAS Java Client tương thích.
- `spring-context-support`/Spring Cache abstraction phù hợp BOM Spring.
- **Caffeine** library (`com.github.ben-manes.caffeine:caffeine`).
- Spring Boot 3.x/Spring Security 6.x và Java 17+.
- Bean provider phải nhận đúng `@Qualifier("casStatelessTicketCache")` nếu có các cache khác.

### Vì sao expireAfterWrite chứ không phải expireAfterAccess?

`expireAfterWrite` tạo **giới hạn tuổi tuyệt đối kể từ khi ghi**. Nếu dùng `expireAfterAccess` không có maximum age bổ sung, caller gửi PT liên tục có thể kéo dài Authentication snapshot vô hạn; điều này xung đột mục tiêu giới hạn tái sử dụng.

Nếu có nhu cầu idle timeout, có thể kết hợp **absolute TTL** với giới hạn idle, nhưng phải kiểm provider hỗ trợ và test rằng **max lifetime không bị kéo dài bởi mỗi lần cache hit**.

**Caffeine maximumSize là giới hạn số entries, không phải giới hạn số lần PT được sử dụng.** Muốn “tối đa N requests” phải dùng một cơ chế đếm/atomic policy riêng.

## 9. Nối StatelessTicketCache vào CasAuthenticationProvider

Ví dụ phần bean wiring, giả định hệ thống đã có `ServiceProperties`, `TicketValidator` và `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` bảo đảm trusted CAS context:

~~~java
@Bean
CasAuthenticationProvider casProxyProvider(
        ServiceProperties serviceProperties,
        TicketValidator proxyTicketValidator,
        AuthenticationUserDetailsService<CasAssertionAuthenticationToken>
                casUsers,
        @Qualifier("casStatelessTicketCache")
        StatelessTicketCache statelessTicketCache) {

    CasAuthenticationProvider provider =
            new CasAuthenticationProvider();

    provider.setServiceProperties(serviceProperties);
    provider.setTicketValidator(proxyTicketValidator);
    provider.setAuthenticationUserDetailsService(casUsers);
    provider.setStatelessTicketCache(statelessTicketCache);
    provider.setKey("api-b-cas-provider-v1");

    return provider;
}
~~~

**Đây là mảnh code trong Spring `@Configuration`, không phải class runnable.** Imports cần tương ứng:

- `org.springframework.security.cas.authentication.CasAuthenticationProvider`
- `org.springframework.security.cas.authentication.CasAssertionAuthenticationToken`
- `org.springframework.security.cas.ServiceProperties`
- `org.springframework.security.core.userdetails.AuthenticationUserDetailsService`
- `org.apereo.cas.client.validation.TicketValidator`

Provider phải được đăng ký trong AuthenticationManager dùng bởi `CasAuthenticationFilter`. Cần SecurityFilterChain, CAS entry point nếu phục vụ browser login, URL matching, error response, cache invalidation và actual CAS infrastructure. **Không tự cho rằng chỉ tạo bean provider là CAS PT đã được hỗ trợ end-to-end.**

### TicketValidator phải kiểm proxy chain

`Cas20ProxyTicketValidator` của CAS Java Client là validator thường gặp cho proxy tickets. Nó có cơ chế **allowedProxyChains** và cờ **acceptAnyProxy** trong những phiên bản tương ứng.

**Production:** chỉ tin những proxy chain đã được duyệt. **Không copy** ví dụ `acceptAnyProxy=true` từ tutorial rồi triển khai, vì nó mở rộng đáng kể nơi có thể ủy quyền xác thực người dùng.

Cấu hình đúng phải kiểm:

- CAS Server HTTPS và TLS certificate trust.
- Ticket dành cho đúng service B.
- Proxy chain chứa đúng Portal A và không có proxy lạ.
- CAS Service Registry cho phép A proxy tới B.
- Timeout của CAS validation.
- Response XML/subject/attributes hợp lệ.
- Account/tenant authorization bên B.

## 10. ServiceProperties.authenticateAllArtifacts và URL động

Khi browser CAS login bình thường, filter xử lý `/login/cas`. Với proxy authentication tới một stateless backend, ticket có thể đi kèm request tới các URL khác, nên tài liệu Spring hướng dẫn bật:

~~~java
ServiceProperties properties = new ServiceProperties();
properties.setService("https://api.example.test/login/cas");
properties.setAuthenticateAllArtifacts(true);
~~~

**Đây là mảnh setup**, còn service URL dùng khi proxy validation có thể lấy động qua `ServiceAuthenticationDetailsSource`. Khi cấu hình:

~~~java
CasAuthenticationFilter casFilter = new CasAuthenticationFilter();
casFilter.setServiceProperties(properties);
casFilter.setAuthenticationDetailsSource(
        new ServiceAuthenticationDetailsSource(properties));
casFilter.setAuthenticationManager(authenticationManager);
~~~

**Chỉ là skeleton wiring**, chưa xác định filter-chain position, endpoint matcher, proxy validator và security context persistence. Phải đối chiếu Javadoc của version được sử dụng.

**Vấn đề bảo mật:** Nếu `ServiceAuthenticationDetailsSource` lấy service URL từ incoming HTTP request, không được tin `Host`, `X-Forwarded-Host`, scheme/path do attacker giả mạo. CAS service URL phải khớp service được đăng ký và public HTTPS origin; chỉ dùng trusted reverse proxy và host allowlist.

**Không bật authenticateAllArtifacts toàn ứng dụng** nếu chỉ một nhóm API cần CAS tickets. Giới hạn đúng filter chain/path để tránh ticket query param trên URL khác vô tình kích hoạt authentication.

## 11. Rủi ro trọng yếu: cache keyed by ticket, không mặc định keyed by service

Theo Javadoc, `SpringCacheBasedTicketCache` lưu `CasAuthenticationToken` bằng **ticket string** lấy từ `token.getCredentials()`. Không có tham số `serviceUrl`, `tenantId` hoặc `proxyChain` trong phương thức `getByTicketId(String)`.

**Hệ quả:** Nếu cùng một instance/provider/cache nhận cùng ticket trên **nhiều URL**, cache hit có thể trả Authentication đã kiểm chứng ở URL cũ mà **không gọi lại CAS** cho URL hiện tại. Tài liệu Spring Security CAS nêu rõ cached PT có thể được dùng ở URL khác sau khi backend đã xác thực một lần.

Ví dụ:

~~~text
PT-X được CAS cấp cho:
  service=https://api.example.test/payments

Request 1: /payments?ticket=PT-X
  cache MISS -> CAS validates for payments -> SUCCESS -> cache PT-X

Request 2: /admin?ticket=PT-X
  cache HIT -> authentication cũ có thể được reuse
  nếu cùng cache/provider/filter và không có kiểm soát khác

=> CAS không còn cơ hội kiểm service mismatch ở request 2.
=> API MUST kiểm authority và phạm vi endpoint riêng.
~~~

**Đừng dùng “CAS đã chỉ cấp PT cho /payments” làm bằng chứng đủ** để /admin chấp nhận cùng cached Authentication nếu backend cho phép cache hit ngoài phạm vi. Đây là trust-boundary quan trọng nhất của `StatelessTicketCache`.

### Cách kiểm soát

1. **Tách filter chain/provider/cache** theo nhóm service trust domain khi cần scope riêng.
2. Chỉ bật CAS proxy ticket processing trên **đúng API endpoints**.
3. Kiểm tra service identity và intended audience **trước khi nhận authority từ cache** qua policy phù hợp.
4. Gắn quyền vào API/method/object; cached Authentication chỉ chứng minh danh tính/những quyền đã được cấp, không cấp quyền mọi URL.
5. Với nhiều tenant/issuer/proxy chains, thiết kế namespace cache/trust context rõ; không chia cùng cache cho các realms không tương thích.
6. Nếu buộc cache key phải gồm **ticket + trusted service + trusted tenant**, cần wrapper/implementation có context tin cậy và kiểm soát đúng provider integration; **giao diện StatelessTicketCache chuẩn chỉ nhận ticket string**, nên không thể tự nói rằng sửa cấu hình Caffeine thành composite key là xong.
7. Trường hợp không thể đảm bảo scope, ưu tiên **không cache** hoặc thay cơ chế chứng thực backend.

**Tách mỗi user/tenant bằng query parameter chưa xác minh là không đủ.** Trusted context phải đến từ server-side registration, routing/authorization và policy.

## 12. Phạm vi proxy chain: ticket có thể do ai đại diện ai?

CAS Proxy Authentication cho phép một ứng dụng A gọi backend B thay user. Khi `/proxyValidate` thành công, response có thể chứa danh sách proxies trong chuỗi ủy quyền.

~~~text
User -> Portal A -> Service C -> API B
          |             |
       Proxy 1       Proxy 2

CAS /proxyValidate(PT-B) -> principal + proxy chain
~~~

Nếu B chỉ cho phép Portal A proxy trực tiếp mà nhận ticket từ Proxy X không được duyệt, B phải từ chối dù ticket và subject có vẻ hợp lệ.

**Policy cần xem:**

- Những proxy URLs nào được tin?
- Cho phép chuỗi proxy dài bao nhiêu?
- Có cho phép chuyển tiếp qua proxy trung gian không?
- Service B có cho phép ST trực tiếp hay chỉ PT qua A?
- Có yêu cầu specific authentication method/MFA/context không?
- Có user/tenant/resource restrictions theo proxy caller không?
- Có cơ chế thu hồi proxy registration không?

**Không dùng `acceptAnyProxy=true` trong production** trừ khi threat model cực kỳ đặc biệt và được phê duyệt. Cache lưu kết quả đã kiểm, nhưng **proxy authorization cũng phải được đánh giá lại khi policy thay đổi**, không coi cache entry cũ là chứng cứ proxy A còn được ủy quyền vô hạn.

## 13. Quy tắc chọn TTL: tách hai đồng hồ

Có ít nhất **hai thời hạn**:

1. **CAS PT validity trước validation:** thời gian CAS chấp nhận PT chưa tiêu thụ; CAS khuyến nghị ST/PT không xác minh quá lâu (mốc 5 phút là khuyến nghị protocol, không phải default áp dụng mọi deployment).
2. **Spring Authentication cache TTL sau validation:** khoảng thời gian B tự cho phép reuse **kết quả đã xác thực**. Nó bắt đầu khi cache ghi, không được CAS cấp sẵn.

Ví dụ minh họa:

~~~text
10:00:00 CAS cấp PT-X cho API B
10:00:12 B validate PT-X thành công
         CAS tiêu thụ PT-X
         B cache Authentication (TTL = 120 giây)
10:01:00 Client gọi PT-X lại -> cache HIT
10:02:12 Cache hết hạn tính từ 10:00:12
10:02:13 Client gọi PT-X lại -> cache MISS
         CAS không cho validate lại PT-X đã consume
         Client cần PT mới
~~~

**Không suy luận:** “PT được CAS cho tồn tại 5 phút thì cache cũng mặc định 5 phút” hoặc “CAS PT hết hạn sau 5 phút nên cache sẽ tự bị hủy”. Hai vòng đời riêng.

### Chọn TTL theo tiêu chí nào?

| Yếu tố | Tác động |
| --- | --- |
| Độ nhạy của API | Thanh toán/quản trị có thể cần TTL rất ngắn hoặc không cache |
| Tần suất request | Nhiều request trong một operation có thể hưởng lợi từ một cache ngắn |
| Khả năng thu hồi quyền | Muốn thu hồi nhanh thì cache TTL ngắn hoặc có invalidation |
| Proxy chain thay đổi | Cần invalidate nếu ủy quyền proxy bị rút |
| CAS outage policy | Cache hit không chứng minh CAS hiện còn tin principal |
| Thiết bị/mạng rủi ro | Credential PT bị đánh cắp vẫn có thể reuse trong cache window |
| Kích thước cache | Memory/DoS risk, cần maximumSize và load controls |
| Multi-node consistency | Mỗi node có TTL độc lập nếu local cache |
| Compliance/SLA | Quy định thời gian thu hồi account/roles/tokens |

**Mô hình gợi ý:** Chọn TTL từ **yêu cầu tối đa về độ trễ thu hồi**, không chỉ từ hiệu năng. Ví dụ “phải mất quyền trong 60 giây” thì cache TTL 10 phút **không đạt yêu cầu** nếu không có invalidation chủ động và kiểm soát trên mỗi request.

Không đưa con số cố định làm chuẩn chung. Cần thử canary, đo traffic và làm security review.

## 14. Giới hạn tái sử dụng: TTL khác số lần dùng

`StatelessTicketCache` interface không có phương thức đặt `maxUses`. Các cache backend thông thường cũng chỉ giữ entry theo thời gian/dung lượng, không tự đếm “được dùng mấy lần”.

Một cached Authentication có thể được dùng:

- Nhiều lần trong 30 giây.
- Liên tiếp đến sát thời điểm TTL.
- Qua nhiều endpoint cùng sử dụng cache.
- Trên nhiều threads cùng lúc.
- Từ một client khác nếu PT bị lộ, trừ khi có caller binding bổ sung.

**Muốn giới hạn N lần sử dụng**, cần thiết kế thêm:

1. Định nghĩa rõ **đếm trên request nào**: mỗi cache hit? kể cả lần validate đầu? mọi endpoint hay chỉ operation nhạy cảm?
2. Đếm **atomic** để hai threads không vượt `maxUses`.
3. Kết hợp **TTL tuyệt đối** từ thời điểm validated.
4. Ràng buộc scope: service, proxy chain, tenant và loại thao tác.
5. Khi chạm giới hạn, evict entry và yêu cầu PT mới; không tự cấp PT mới.
6. Có thể yêu cầu per-request proof (mTLS/client authentication/DPoP-like design nếu phù hợp nền tảng), vì PT là bearer string.
7. Test concurrent hit và race; nếu dùng distributed cache cần atomic Lua/CAS operation hoặc transactional primitive.
8. Có metric `reuse_count` nhưng **không log raw ticket**.

**Lưu ý:** Nếu muốn chỉ dùng ticket một lần tại backend, **không bật cache** là lựa chọn rõ ràng hơn. Khi cần caching, đó là quyết định chấp nhận có giới hạn sự tái sử dụng tại service.

## 15. Java 17 độc lập: cache có TTL tuyệt đối, scope và maxUses

Chương trình dưới đây mô phỏng **chính sách bổ sung** chứ không tái hiện toàn bộ Spring Security. Nó thể hiện: một proxy ticket đã được CAS xác minh một lần có thể được backend reuse trong cửa sổ ngắn, nhưng phải trùng service/proxy/tenant, không quá hạn và không vượt giới hạn số lượt.

Tạo file **ProxyTicketReusePolicyDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ProxyTicketReusePolicyDemo {

    record Scope(String service, String proxy, String tenant) {}

    record Cached(String user, Scope scope, long expiresAt,
                  int uses) {}

    static final class PolicyCache {
        private final Map<String, Cached> entries = new HashMap<>();
        private static final long TTL_SECONDS = 120;
        private static final int MAX_USES = 2;

        void storeValidated(String ticket, String user, Scope scope,
                            long nowSeconds) {
            // Gọi sau khi CAS đã validate PT thành công.
            // Không mô phỏng ticket validation bằng chính hàm này.
            entries.put(ticket, new Cached(
                    user, scope, nowSeconds + TTL_SECONDS, 0));
        }

        String use(String ticket, Scope expected, long nowSeconds) {
            Cached value = entries.get(ticket);
            if (value == null) {
                return "MISS";
            }
            if (nowSeconds >= value.expiresAt()) {
                entries.remove(ticket);
                return "EXPIRED";
            }
            if (!value.scope().equals(expected)) {
                return "DENY_SCOPE";
            }
            if (value.uses() >= MAX_USES) {
                entries.remove(ticket);
                return "REAUTH_REQUIRED";
            }
            entries.put(ticket, new Cached(
                    value.user(), value.scope(),
                    value.expiresAt(), value.uses() + 1));
            return "ALLOW " + value.user();
        }

        void revoke(String ticket) {
            entries.remove(ticket);
        }
    }

    public static void main(String[] args) {
        PolicyCache cache = new PolicyCache();
        Scope payments =
                new Scope("payments-api", "portal-a", "north");
        Scope admin =
                new Scope("admin-api", "portal-a", "north");

        cache.storeValidated("PT-A", "alice", payments, 100);
        System.out.println("first: "
                + cache.use("PT-A", payments, 100));
        System.out.println("wrong service: "
                + cache.use("PT-A", admin, 110));
        System.out.println("second: "
                + cache.use("PT-A", payments, 180));
        System.out.println("third: "
                + cache.use("PT-A", payments, 190));

        cache.storeValidated("PT-B", "bob", payments, 300);
        System.out.println("after TTL: "
                + cache.use("PT-B", payments, 421));

        cache.storeValidated("PT-C", "carol", payments, 500);
        cache.revoke("PT-C");
        System.out.println("after revoke: "
                + cache.use("PT-C", payments, 510));
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac ProxyTicketReusePolicyDemo.java
java ProxyTicketReusePolicyDemo
~~~

**Stdout chính xác:**

~~~text
first: ALLOW alice
wrong service: DENY_SCOPE
second: ALLOW alice
third: REAUTH_REQUIRED
after TTL: EXPIRED
after revoke: MISS
~~~

### Đọc kết quả

- Lần đầu: Authentication đã xác minh được cho payments-api.
- Dùng cùng PT tại admin-api: từ chối bởi kiểm scope; **không cộng lượt sử dụng**.
- Lần thứ hai ở đúng service: cho phép trong cửa sổ TTL.
- Lần thứ ba: chạm maxUses → yêu cầu lấy PT mới.
- PT-B được ghi lúc 300, expiry 420; lúc 421 hết hạn.
- PT-C bị revoke nên không tìm thấy.

**Lưu ý an toàn rất quan trọng:** đây là **mô phỏng đơn luồng, dùng `HashMap` và đồng hồ giả**. Trong production cần CAS protocol validation trước khi gọi store, cache backend atomic, giá trị key ngẫu nhiên mạnh, xử lý race, session/account revocation và bảo vệ network. Không dùng demo làm `StatelessTicketCache` production; giao diện Spring mặc định **chỉ get theo ticket string**, nên tích hợp kiểm scope/maxUses phải được thiết kế ở boundary phù hợp chứ không chỉ copy `PolicyCache`.

## 16. Thời hạn kết quả xác thực và độ tươi của quyền

Cache lưu **CasAuthenticationToken đã được tạo khi validation thành công**, bao gồm principal và GrantedAuthority tại thời điểm đó. Nếu thông tin thay đổi trong CAS hoặc local DB:

- Người dùng bị khóa tài khoản.
- Người dùng rời tenant.
- Group/role CAS thay đổi.
- Proxy A không còn được phép thay user truy cập API B.
- Token/phiên TGT/PGT gốc bị thu hồi.
- Chính sách MFA/assurance có yêu cầu mới.

Thì **cache hit không tự gọi CAS hoặc UserDetailsService lại để biết thay đổi**. Vì vậy phải xác định **thời điểm quyền trở nên stale**.

Các chiến lược:

| Chiến lược | Khả năng | Đánh đổi |
| --- | --- | --- |
| TTL ngắn | Giới hạn tối đa tuổi của Authentication snapshot | Tăng số lần xin PT/validate |
| Chủ động `removeTicketFromCache` | Thu hồi một PT cục bộ đã biết | Phải biết cache key và fanout mọi nodes |
| Evict toàn cache khi đổi policy | Đơn giản khi đổi version trust | Tăng login/validation traffic |
| Account/role version check mỗi request | Có thể thu hồi quyền nhanh | Thêm database/cache lookup |
| Domain authorization từ DB hiện hành | Không dựa hoàn toàn vào stale authority | Tăng latency nhưng đúng entitlement |
| mTLS/caller binding bổ sung | Giảm rủi ro PT bị đưa sang client khác | Cần identity của service caller |
| Không cache | Không reuse Authentication qua PT | Tăng áp lực cấp PT mới |

**TGT/PGT logout không mặc nhiên xóa entry trong StatelessTicketCache.** Nó là cache do backend B quản lý. CAS Server có thể đã vô hiệu hóa ticket gốc, nhưng B vẫn có cached Authentication nếu chưa hết TTL/chưa evict.

## 17. Một PT có thể bị dùng lại sau khi CAS thu hồi phiên?

**Có thể trong cửa sổ cache của service**, nếu backend B không nhận được tín hiệu hoặc chưa xóa entry và policy không kiểm account/session hiện hành.

Ví dụ:

~~~text
10:00 API B validate PT-X -> cache auth (TTL 5 phút)
10:01 CAS logout user, hủy TGT/PGT
10:02 Caller gửi lại PT-X tới API B
      cache HIT -> backend không gọi CAS
      có thể tiếp tục nhận Authentication cũ
10:05 Cache hết TTL, lần dùng lại PT-X sẽ miss
      CAS từ chối PT đã consume
~~~

**Đây là mô hình nguy cơ, không phải cam kết mọi Spring configuration có thể tiếp tục cho phép:** backend có thể có policy thu hồi khác. Điều quan trọng là **CAS logout không phải một tín hiệu cache invalidation tự động được bảo đảm**.

Đối với thao tác nhạy cảm (thanh toán, quản trị, thông tin cá nhân), cân nhắc revocation epoch hoặc entitlement check ở backend; nếu yêu cầu vô hiệu tức thì thì TTL đơn độc không đủ.

## 18. Multi-node, Redis và nhất quán TTL

Nếu API B chạy nhiều pods sau load balancer:

~~~text
            Proxy caller Portal A
                     |
                 Load Balancer
                  /          \
              API B-1      API B-2
                |             |
          local cache 1  local cache 2
                  \          /
                 CAS Server
~~~

**Với Caffeine cache cục bộ:**

1. PT-X request đầu vào B-1 → CAS validates thành công, B-1 cache kết quả.
2. PT-X request tiếp theo vào B-2 → B-2 cache miss.
3. B-2 thử validate lại PT-X với CAS → CAS từ chối vì PT đã consume.
4. Người dùng thấy lỗi ngẫu nhiên tùy request rơi node nào.

Các phương án:

- Sử dụng cache tập trung, có TTL/eviction như Redis nếu được phép và hỗ trợ serialization an toàn.
- Giữ routing ổn định trong cửa sổ TTL nếu được thiết kế/giám sát rõ, nhưng sticky routing không giải quyết failover hoàn toàn.
- Yêu cầu client xin **PT mới theo từng request/node** khi không muốn cache chia sẻ.
- Chuyển sang API authentication mechanism có audience, TTL và validation phù hợp hơn với topology.
- Khi cần thu hồi, fanout invalidate tới mọi node/cache.

**Redis caching CasAuthenticationToken cần đặc biệt cẩn trọng:** Authentication object có thể không phù hợp Java serialization mặc định qua các versions/nodes và có thể chứa thông tin cá nhân; thiết kế serializer, schema/version, encryption/access control và key namespace phù hợp. Không bật insecure Java deserialization từ dữ liệu không tin.

### TTL trong cluster

- Kiểm tra TTL ở **backend cache thật**, không chỉ config local.
- Dùng thời gian nhất quán; ưu tiên server/cache monotonic semantics khi phù hợp.
- Định nghĩa eviction khi deploy phiên bản mới/roles thay đổi.
- Kiểm tra cache shared across tenants và CAS contexts.
- Đặt key namespace đủ hẹp để tránh reuse giữa hai ứng dụng tin CAS khác nhau.
- Khi đổi CAS service URL hoặc proxy trust, evict entries cũ.

## 19. Cache key và dữ liệu nhạy cảm trong telemetry

Spring cache implementation thường lấy **ticket string nguyên bản** làm cache key. Đây là một bearer secret. Nếu gửi ticket vào metrics/logs/Redis command traces, rủi ro bị lộ tăng.

Không ghi:

- Raw `PT-...` hoặc `ST-...` vào access logs.
- Full `CasAuthenticationToken` vào logs.
- CAS Assertion chứa identity attributes/PII.
- PGT, TGT, TGC hoặc cookie values.
- Header/URL query chứa ticket trong APM traces.

Có thể ghi theo policy:

- Hash/digest đã keyed (HMAC) của ticket nếu cần correlation nội bộ, không phải raw.
- CAS trust-context identifier và service ID công khai được duyệt.
- Cache hit/miss/evict/expired counters.
- Proxy-chain policy outcome ở mức không lộ bí mật.
- Số active entries và cache latency.
- Authentication decision vs domain authorization decision.
- Correlation ID không phải ticket value.

**Lưu ý:** Hash ticket không tự biến bearer credential thành dữ liệu công khai hoàn toàn nếu ticket entropy yếu hoặc log có thể tương quan đến PII. Hãy áp retention/access control.

## 20. Vì sao không dùng same ticket cho mọi backend?

Giả sử Portal A gọi Billing B và HR C:

~~~text
Portal A -> CAS /proxy(PGT, target=Billing B) -> PT-B
Portal A -> CAS /proxy(PGT, target=HR C)      -> PT-C
~~~

**PT-B** được CAS cấp cho Billing B, không phải HR C. CAS protocol sẽ từ chối PT-B nếu HR C cố validate nó cho target của HR C.

Nếu nhiều backend **chia sẻ cùng cache** hoặc proxy auth boundary với ticket-key-only lookup, có nguy cơ một cached Authentication bị tái sử dụng ở nơi không phù hợp. Vì thế:

1. Không share `StatelessTicketCache` instance giữa các service trust boundaries khác nhau mà không có isolation rõ.
2. Không tùy tiện chuyển PT-B cho HR C.
3. Không định nghĩa cache authentication như một công cụ SSO toàn cluster.
4. Kiểm scope service/tenant trên từng request.
5. Với nhiều host/tenants, tách cache namespace hoặc chuyển sang tokens có audience rõ.

Một cache hit **không phải CAS `/proxyValidate` thành công lần thứ hai cho service mới**.

## 21. StatelessTicketCache không phải Stateless Ticket Registry của CAS Server

Hai thuật ngữ trông giống nhau nhưng thuộc **hai sản phẩm và mục tiêu khác nhau**.

| Thuật ngữ | Nằm ở đâu? | Chức năng |
| --- | --- | --- |
| **Spring Security StatelessTicketCache** | CAS Client / backend service | Cache **kết quả Authentication** sau khi CAS validation một ticket |
| **Apereo CAS Stateless Ticket Registry** | CAS Server | Cơ chế phát/kiểm chứng **tickets self-contained** theo một triển khai CAS Server |
| **CAS Proxy-Granting Ticket Storage** | Proxying CAS client | Lưu PGT để service A xin PT cho backend B |
| **Spring SecurityContext Session Repository** | Spring web application | Lưu local Authentication trong HttpSession hoặc repository khác |

**Không trộn ba nơi lưu:** PGT storage không chứa cache kết quả PT validation; Spring StatelessTicketCache không phát PT; CAS Stateless Ticket Registry không thay Spring Authentication cache.

**Cảnh báo version:** Apereo CAS **Stateless Ticket Registry** (tài liệu development) có những trade-off có thể **không bảo đảm one-time ticket** và hỗ trợ session revocation khác chuẩn registry stateful. Đó là **ngoại lệ phía CAS Server**, phải đánh giá riêng nếu thực sự bật module đó. Không suy diễn các caveats của nó là behavior mặc định của Spring `StatelessTicketCache`.

Bài này giả định **CAS Protocol với ST/PT one-time validation** như đặc tả; nếu CAS Server dùng một registry triển khai khác, cần xác minh hành vi thực tế và rủi ro riêng.

## 22. Bảo vệ proxy credentials khi truyền qua HTTP

CAS PT là bearer ticket. Khi gửi từ A tới B:

- Bắt buộc **HTTPS/TLS** và xác minh chứng thư/hostname.
- Trong server-to-server communication, ưu tiên **mTLS** hoặc service identity ở gateway khi có thể.
- Hạn chế ticket lộ trong query string; nếu CAS client hỗ trợ request parameter `ticket`, cấu hình access logs redact.
- Không cho browser/JS chưa tin tự cấp hoặc sửa `PT` để truy cập backend.
- Không đưa ticket vào Referer, analytics, tracing, error URL, frontend URLs hoặc support tickets.
- Đặt strict timeouts/rate limits và chống replay ngoài phạm vi cache.
- Không để proxy A gửi PT-B tới backend khác hoặc môi trường staging.
- Bảo vệ PGT trong A; PGT có thể xin nhiều PT, nên rủi ro lớn hơn PT đơn lẻ.
- Định nghĩa luồng rotation/revocation keys, service registry và proxy chain.

**Có cache không làm PT kém nhạy cảm.** Ngược lại, nó tạo thêm một cửa sổ mà PT bị lộ có thể được service B chấp nhận **sau lần validation đầu tiên**, dù CAS Server không cho validate lại.

## 23. Kiểm tra quyền trên request: Identity không đủ để xử lý nghiệp vụ

Giả sử B nhận cached Authentication với `ROLE_FINANCE_VIEWER`. Một request:

~~~text
GET /api/tenants/south/invoices/773
ticket=PT-X (của user thuộc north)
~~~

**Authentication có thể thành công**, nhưng **Authorization phải từ chối** vì user không thuộc tenant south.

Các phép kiểm tra:

1. Local account còn active.
2. Proxy chain/caller còn được phép.
3. Tenant của request có nằm trong memberships đã được xác minh không?
4. Authority có cho phép action tương ứng không?
5. Resource có thuộc tenant đó không?
6. Session/role version hiện hành có bị thu hồi không?
7. Operation nhạy cảm có yêu cầu auth freshness/step-up mới không?
8. Nếu cần, request caller có chứng minh được identity bằng mTLS ngoài PT không?

`@PreAuthorize("hasRole('VIEWER')")` có thể phù hợp để chặn một lớp URL, nhưng **không tự kiểm ownership/tenant của invoice**. Cần domain service checks.

**Không kéo dài life của một authorization decision** chỉ vì cache đã giữ Authentication. Quyền trên object có thể đổi nhanh hơn authentication snapshot.

## 24. Xử lý lỗi cache miss, CAS outage và lỗi validation

### Khi cache MISS

Backend có thể gọi CAS để validate ticket. Nếu PT mới thì có thể thành công; nếu **PT đã consume** mà cache entry hết hạn/evicted, CAS trả `INVALID_TICKET`. Đó là kết quả bình thường, không phải lý do tắt validation.

**Hành vi nên có:** trả 401/challenge hoặc thông báo caller xin PT mới qua PGT được phép. Không retry cùng ticket vô hạn.

### Khi CAS outage

- Cache HIT có thể vẫn trả Authentication cũ nếu chính sách cho phép.
- Cache MISS không thể xác thực ticket chưa biết; **fail closed**.
- Không dùng “CAS đang lỗi” làm điều kiện tăng TTL vô hạn hoặc accept-any-ticket.
- Với endpoints nhạy cảm có thể phải từ chối cả cache HIT nếu freshness policy hoặc revocation SLA đòi.

### Khi cache backend outage

Không mặc định fail-open. Quyết định theo architecture:

- Nếu có thể validate **PT mới** với CAS một lần thì cache write fail có thể chấp nhận request lần đầu theo policy, nhưng các request sau cần PT mới.
- Nếu ticket cũ đã consume, không thể “revalidate để phục hồi cache”.
- Nếu cache là kho shared, cần telemetry và giới hạn retries.
- Lỗi serialization/deserialization của cached Authentication phải được xử lý như auth failure, không dùng token rỗng.

### Khi service/proxy chain mismatch

Không dùng cache entry của scope cũ để vượt qua policy mới. Trả 403/401 phù hợp với phân biệt authentication vs authorization; không tiết lộ raw ticket, assertion, proxy chain secrets hoặc stack trace ra client.

## 25. Các mốc thay đổi buộc phải evict hoặc giảm TTL

| Thay đổi | Hành động được khuyến nghị |
| --- | --- |
| User bị khóa hoặc role bị rút | Evict cache liên quan hoặc xác minh account version mỗi request |
| CAS/PGT logout | Không mặc nhiên tự xóa Spring cache; chủ động invalidate nếu bắt buộc |
| Proxy chain bị thu hồi | Evict auth snapshots từng được phát cho proxy đó |
| Service registration thay đổi | Evict entries cũ/đổi cache namespace |
| Tenant bị suspend | Deny tại domain policy và invalidate cached privileges |
| CAS server/trust anchor đổi | Revalidate new tickets; đánh giá xóa cache cũ |
| URL service/host/ACS thay đổi | Không reuse cross-service; kiểm cache scope |
| Policy maxUses thay đổi | Không dùng lại cached entries không đáp ứng version mới |
| CAS backend outage dài | Xem xét force deny theo policy, không tự gia hạn cache |
| Rủi ro ticket leak | Evict ticket và chặn requests, điều tra logs |
| Deployment đổi serialization schema | Evict/migrate cache có kiểm soát |

**Khả năng triển khai:** `removeTicketFromCache(ticket)` xử lý theo key khi biết ticket. Nếu muốn revoke **theo user/tenant/proxy chain**, phải tự thiết kế **reverse index**, cache tags hoặc entitlement version check. Giao diện cache mặc định **không có `removeAllByUser`**.

## 26. Test matrix: chức năng, TTL và chống cấp quyền sai

| # | Trường hợp | Kỳ vọng |
| --- | --- | --- |
| 01 | PT mới dành cho API B, proxy chain hợp lệ | CAS validation một lần → cache auth |
| 02 | Gửi lại PT đó ngay | Cache hit, không gọi CAS lại |
| 03 | Gửi lại PT ở thời điểm sau TTL | Cache miss và CAS từ chối PT đã consume |
| 04 | Disable cache bằng NullStatelessTicketCache | Gửi lại PT không được chấp nhận |
| 05 | Cache expireAfterWrite=120s | Đọc liên tiếp không kéo dài absolute TTL |
| 06 | Cache expireAfterAccess không có max age | Phát hiện nguy cơ gia hạn quá lâu |
| 07 | PT của API B gửi tới API C | Không được vượt scope/authorization |
| 08 | PT của tenant north gửi tới south | Domain policy từ chối |
| 09 | PT qua proxy chain không được phép | Validator từ chối trước cache write |
| 10 | Role bị thu hồi sau validation | Request nhạy cảm bị từ chối theo revocation SLA |
| 11 | User logout CAS khi cached PT còn TTL | Đánh giá rõ cache hit policy, không suy luận tự revoke |
| 12 | Cache entry bị removeTicketFromCache | Không còn cache hit, cần ticket mới |
| 13 | maxUses=2 trong custom policy | Lượt vượt giới hạn bị từ chối |
| 14 | Concurrent 100 requests trên một key | Không vượt maxUses do race, nếu policy có đếm |
| 15 | PT bị đánh cắp nhưng user chưa logout | TLS/mTLS/caller binding và cache scope giảm rủi ro |
| 16 | CAS /proxyValidate endpoint timeout | Không tạo Authentication chưa xác minh |
| 17 | Cache hit khi CAS outage | Theo policy freshness, không mặc định allow mọi thao tác |
| 18 | Cache miss khi CAS outage | Fail closed |
| 19 | Cache provider không có TTL | QA phải phát hiện và không duyệt production |
| 20 | Caffeine cache local nhiều nodes | Phát hiện PT dùng ở node khác sau one-time validation |
| 21 | Shared Redis cache eviction | Mọi node không còn tái sử dụng PT bị revoke |
| 22 | Cache serialized Authentication đổi version | Không deserialize vô hạn hoặc bỏ qua policy |
| 23 | Request đã có SecurityContext khác | Không nhận nhầm identity từ PT không được xử lý |
| 24 | Host/X-Forwarded-Host giả | Không tạo service URL trái phép |
| 25 | PT của service khác nhưng cùng subject | Không chỉ dựa username để cho phép |
| 26 | PT bị replay trước lần validation thành công | CAS one-time semantics và race handling đúng |
| 27 | Ticket bị consume bởi validation sai service | CAS từ chối lần validate tiếp theo |
| 28 | UserDetails roles mapping nhận group lạ | Không tự cấp ROLE_ADMIN |
| 29 | Ticket xuất hiện trong access logs | Redaction hoạt động |
| 30 | CAS Stateless Ticket Registry được bật | Test riêng vì semantics có thể khác registry one-time |
| 31 | Tắt proxying ở CAS Service Registry | Không được tiếp tục cấp PT mới |
| 32 | Đồng thời đổi proxy chain và cache policy | Cache entries cũ bị invalidate/fail closed |

**Định nghĩa PASS:** phải quan sát cả CAS validation count, cache hit/miss, security context, endpoint authorization và kết quả request thực tế. Chỉ unit test CacheManager không chứng minh việc TicketValidator được gọi đúng một lần.

## 27. Chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Request đầu thành công, request thứ hai bị INVALID_TICKET | Cache không bật, NullStatelessTicketCache, miss sang node khác hoặc expired | Kiểm cache bean, TTL, multi-node routing |
| Request vẫn thành công sau CAS logout | Cached Authentication còn TTL | Kiểm revocation policy/eviction và domain authorization |
| PT có thể vào endpoint khác ngoài intended target | Cache keyed by ticket, mọi URL dùng chung provider | Giới hạn chain/path, service scope, authorization |
| User có quyền cũ sau khi group bị rút | Authorities snapshot cached | Entitlement version check hoặc evict |
| Cached Authentication không tự hết hạn | Backing cache thiếu TTL | Cấu hình expireAfterWrite/absolute TTL |
| Số requests nhiều hơn maxUses nhưng vẫn success | StatelessTicketCache không có built-in counter | Thêm atomic use-budget ở boundary |
| PT dùng được ở node A nhưng không ở node B | Local caches độc lập, CAS one-time | Shared cache hoặc thiết kế auth khác |
| Hệ thống bất ngờ full logout khi cache bị clear | Không có PT mới, client reuse PT đã consume | Caller phải xin PT mới từ CAS qua PGT |
| Proxy ticket validation bị từ chối | Cas20ProxyTicketValidator chưa allow đúng proxy chain | So proxy list với Service Registry |
| Dùng acceptAnyProxy=true nên mọi ticket qua proxy lạ được tin | Trust quá rộng | Dùng allowedProxyChains cụ thể |
| CAS báo INVALID_SERVICE | URL target khác khi xin PT và validate | So service URL và reverse proxy |
| URL service đổi khi qua gateway | Trusted forwarded headers thiếu cấu hình | Host allowlist, public origin |
| Cache lớn dần quá mức | Không có max entries / TTL | max size, TTL, metrics |
| Redis serialization exception | CasAuthenticationToken không tương thích serializer/schema | Versioning, custom secure serialization |
| Role_ADMIN xuất hiện từ CAS group | Group→role mapping trực tiếp | Exact allowlist, tenant scope |
| Có ticket trong logs/APM | Ghi query string nguyên văn | Mask ticket credentials và giảm log retention |
| Spring 5 sample không compile ở Spring 6/7 | API/token classes, JCache/Ehcache khác | Dùng đúng Javadoc/BOM và thử build |

**Không sửa lỗi bằng cách** tăng TTL vô hạn, bỏ qua kiểm proxy chain, cho nhận mọi service URL hoặc tắt TLS validation.

## 28. Runbook triển khai production

### Trước khi bật cache

1. Inventory các clients stateless, API service URLs, proxy chain, CAS server/version, CAS client version.
2. Xác minh CAS Service Registry chỉ cho phép service/proxy chain được phê duyệt.
3. Thử flow PT không cache: CAS issue PT cho B, B validate thành công **một lần**.
4. Xác định vì sao cần reuse cùng ticket; có thể dùng PT mới mỗi request hoặc OAuth2 token phù hợp hơn không?
5. Xác định **replay risk**, tenant boundary, sensitivity của APIs và account revocation SLA.
6. Thống nhất absolute TTL, cache max size, số lần reuse (nếu cần), cleanup behavior và owner.
7. Chọn cache backend: Caffeine local hay shared Redis, tính đến one-time PT và multi-node.
8. Tách filter chain, trust context, service URLs và cache namespaces theo policy.
9. Thiết kế cách evict khi user/group/tenant/proxy chain đổi.
10. Đặt metrics redaction và kiểm tra logging không chứa ticket.

### Khi rollout

1. Bật cache trên canary backend, giữ quyền rollback về NullStatelessTicketCache.
2. Đo `CAS validate`, `cache hit/miss`, `INVALID_TICKET`, service mismatch, p95 latency.
3. Kiểm tính đúng TTL bằng thời gian thực/lời gọi liên tục.
4. Thử PT bị đưa tới endpoint khác và tenant khác; policy phải chặn.
5. Thử logout, disable user, revoke role và proxy chain change.
6. Thử node switch, cache eviction, Redis outage, CAS outage.
7. Xác minh authorization theo object không dựa chỉ vào cached roles.
8. Giám sát replay anomaly và requests cùng PT từ nhiều caller identities.
9. Đối chiếu proxy validation trust và errors trên CAS Server.
10. Chỉ mở rộng khi security/revocation/latency tiêu chí được đáp ứng.

### Khi rollback hoặc có sự cố

1. Ngừng nhận cached Authentication không được kiểm soát (evict cache hoặc đổi cấu hình) theo change policy.
2. Nếu PT đã consume, các clients phải xin **PT mới**; không retry ticket cũ.
3. Không kéo dài cache TTL nhằm né CAS outage nếu chưa được security owner phê duyệt.
4. Kiểm tra tokens có bị lộ trong proxy logs/traces và rotate/revoke credentials liên quan.
5. Kiểm CAS server service registry, proxy chain và backend authorization.
6. Ghi incident timeline, phạm vi tickets/sessions có thể bị replay, tenant impact và kết quả mitigation.

## 29. Monitoring và cảnh báo

Những metrics sau là **đề xuất do ứng dụng triển khai**, không phải auto-instrumentation mặc định của Spring Security CAS:

| Metric | Ý nghĩa |
| --- | --- |
| `cas_proxy_cache_hit_total` | Số lần sử dụng kết quả xác thực đã cache |
| `cas_proxy_cache_miss_total` | Số lần cần validate hoặc bị miss |
| `cas_proxy_cache_evictions_total` | Entries bị evict vì TTL, manual revoke hoặc capacity |
| `cas_proxy_cache_entry_age_seconds` | Tuổi entry tại thời điểm sử dụng |
| `cas_proxy_validation_success_total` | PT validation thành công tại CAS |
| `cas_proxy_validation_failure_total` | PT validation fail theo reason |
| `cas_proxy_replay_blocked_total` | Requests bị deny do scope/maxUses/revoked state |
| `cas_proxy_chain_denied_total` | Proxy chain không được phép |
| `cas_proxy_authz_denied_total` | Authentication hợp lệ nhưng domain authorization từ chối |
| `cas_proxy_cache_size` | Số entries, giúp nhận biết memory pressure |
| `cas_proxy_revocation_delay_seconds` | Độ trễ giữa revoke và request bị từ chối |

Không đặt raw PT, principal ID, email, TGT/PGT hoặc proxy credentials trong **metric labels**. Nếu cần dấu vết, dùng correlation IDs được bảo vệ và thời gian tồn tại ngắn. Phân loại **cache hit dẫn đến 403** khác với **CAS validation failed**.

**Tình huống cần cảnh báo:** hit rate tăng bất thường từ cùng PT/caller không quen thuộc; nhiều INVALID_TICKET sau failover; cache entries không hết hạn; nhiều proxy chain không hợp lệ; hoặc user vẫn thao tác sau thời điểm revocation SLA.

## 30. Hỏi đáp thường gặp

**1. StatelessTicketCache có làm Proxy Ticket của CAS trở thành vé dùng nhiều lần tại CAS không?**  
Không. CAS vẫn one-time validation. Spring Security **tái sử dụng CasAuthenticationToken đã xác minh** tại backend sau cache hit.

**2. Vì sao gửi cùng PT lần hai vẫn được?**  
Vì backend lấy Authentication từ cache và không gọi CAS lần hai. Nếu cache miss hoặc expired, CAS sẽ từ chối PT đã consume.

**3. Thời hạn cache có tự lấy từ expiry của PT không?**  
Không mặc định. Backing Spring Cache quyết định TTL riêng, cần cấu hình rõ và thử.

**4. SpringCacheBasedTicketCache có setMaxUses không?**  
Không. Interface chuẩn cung cấp get, put, remove; cần policy/atomic counter riêng nếu muốn giới hạn lượt.

**5. NullStatelessTicketCache dùng khi nào?**  
Khi không muốn giữ cached Authentication; các request mới phải có PT chưa consume.

**6. Cache key có tự gồm service URL và tenant không?**  
Không. Javadoc chỉ ra lookup bằng **ticket ID string**. Phải thiết kế isolation/authorization riêng.

**7. Có thể dùng cùng PT qua API B và API C không?**  
CAS protocol PT gắn với một target service. Cache hit trong một backend có nhiều URLs không chứng minh nó hợp lệ với service C; cần scope checks.

**8. CAS logout có thu hồi hết cached Authentication không?**  
Không mặc nhiên. Service phải có invalidation/revocation policy.

**9. expireAfterAccess có an toàn không?**  
Nếu không có absolute TTL, hoạt động liên tục có thể kéo dài entry. Ưu tiên hard maximum age và kiểm policy.

**10. Cache có tự đồng bộ trên nhiều pods không?**  
Không. Caffeine local là riêng từng node; nếu PT đã consume ở CAS, node khác có thể validate thất bại.

**11. Cache kết quả xác thực có đồng nghĩa đã có quyền trên API không?**  
Không. Cần authorize theo route/method/tenant/resource và account status hiện hành.

**12. Dùng shared Redis có giải quyết mọi rủi ro không?**  
Không. Nó giúp shared cache nhưng tăng rủi ro serialization, data protection, key namespace, revocation và outage.

**13. Apereo CAS Stateless Ticket Registry và Spring StatelessTicketCache có giống nhau không?**  
Không. Một bên là ticket registry của CAS Server, bên kia là cache Authentication ở Spring Client; semantics khác nhau.

**14. Có nên dùng acceptAnyProxy=true để giảm lỗi?**  
Không trong production thông thường; phải giới hạn proxy chain theo service registry và trust policy.

**15. Nếu yêu cầu thu hồi gần như tức thì thì làm gì?**  
Không chỉ dựa TTL. Cần evict chủ động và kiểm trạng thái account/entitlement/role version khi xử lý request nhạy cảm; nếu không đảm bảo, không cache.

## 31. Checklist trước khi dùng thật

- [ ] Hiểu PT/ST là **one-time validation tại CAS**, cache chỉ reuse kết quả Authentication ở backend.
- [ ] Xác minh PGT/PT flow, CAS server và service registry cho phép đúng proxy caller/target.
- [ ] `CasAuthenticationProvider` dùng proxy-capable TicketValidator với **allowed proxy chains** chặt.
- [ ] Không cấu hình `acceptAnyProxy=true` cho production khi không có threat-model approval.
- [ ] `ServiceProperties.authenticateAllArtifacts` chỉ bật ở filter chain/path cần thiết.
- [ ] `ServiceAuthenticationDetailsSource` dùng service URL đáng tin, chống spoofed Host/forwarded headers.
- [ ] Hiểu `StatelessTicketCache` chỉ lookup theo ticket ID, không có scoped composite key mặc định.
- [ ] Không chia cache/provider giữa các trust contexts/tenants nếu chưa có isolation và domain checks.
- [ ] Có `expireAfterWrite` hoặc absolute TTL thực tế trên backing Cache.
- [ ] Có maximum entries và kiểm cache eviction; max size không phải max uses.
- [ ] Nếu có giới hạn số lượt, đếm atomic và test concurrent requests.
- [ ] Phân biệt CAS PT expiry và Authentication cache TTL; không tự giả định bằng nhau.
- [ ] Chọn ngưỡng TTL dựa vào sensitivity và revocation SLA, không chỉ latency.
- [ ] Cached Authentication không được thay thế account/tenant/resource authorization.
- [ ] Có cách invalidate khi user disabled, role/tenant/proxy trust thay đổi hoặc token leak.
- [ ] Test multi-node/redis/redis outage/cas outage, failover và client xin PT mới.
- [ ] Không log raw ticket/TGT/PGT/TGC hoặc serialized Authentication chứa PII.
- [ ] Test replay sau TTL, logout, wrong service, wrong tenant, wrong proxy chain và maxUses.
- [ ] Không nhầm Spring StatelessTicketCache với Apereo CAS Stateless Ticket Registry.
- [ ] Xác minh API/package của đúng Spring Security và CAS Client BOM, không copy cấu hình từ bản cũ nếu chưa kiểm.

## 32. Kết luận

**`StatelessTicketCache` giúp `CasAuthenticationProvider` phục vụ các caller stateless bằng cách ghi nhớ `CasAuthenticationToken` sau lần xác minh CAS thành công.** Khi nhận lại cùng PT, provider có thể dùng cache hit để không gọi CAS lần nữa, dù PT đã bị consume ở CAS Server. Cơ chế này có ích cho các đợt gọi API ngắn nhưng làm phát sinh **cửa sổ bearer replay tại backend**, không phải mở rộng validity của CAS Proxy Ticket.

Để sử dụng an toàn, phải **giới hạn thời gian sống tuyệt đối, số lượng entries, phạm vi service/proxy chain/tenant và quyền trên từng request**; nếu muốn giới hạn số lượt thì thêm policy atomic vì interface chuẩn không có maxUses. Đồng thời, phải thiết kế **thu hồi** vì CAS logout, quyền bị rút hoặc thay đổi proxy chain **không tự động xóa** cache của Spring. Khi không kiểm soát được rủi ro, sử dụng `NullStatelessTicketCache` với PT mới cho từng request hoặc cơ chế API authentication khác phù hợp hơn.

### Tài liệu chính thức và hướng đọc thêm

- Spring Security — CAS Authentication, phần **Proxy Ticket Authentication**, `StatelessTicketCache`, stateless flow: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security Javadoc — `StatelessTicketCache`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/StatelessTicketCache.html
- Spring Security Javadoc — `SpringCacheBasedTicketCache`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/SpringCacheBasedTicketCache.html
- Spring Security Javadoc — `NullStatelessTicketCache`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/NullStatelessTicketCache.html
- Spring Security Javadoc — `CasAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
- Spring Security Javadoc — `CasAuthenticationFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html
- Spring Security Javadoc — `ServiceProperties`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html
- Apereo CAS — CAS Protocol Specification, Sections 2.5–3.3 (ST/PT/PGT): https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- Apereo CAS — Proxy Authentication: https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html
- Apereo CAS — Stateless Ticket Registry (**khái niệm khác**, có caveats riêng): https://apereo.github.io/cas/development/ticketing/Stateless-Ticket-Registry.html
