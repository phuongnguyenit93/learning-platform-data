# Không trả entity chứa toàn bộ dữ liệu nghiệp vụ làm principal theo thói quen

**Module:** Spring Security – authentication. **Nhóm kiến thức:** Hợp đồng người dùng.

## 1. Vấn đề: principal là danh tính dùng cho bảo mật, không phải toàn bộ hồ sơ nghiệp vụ

Trong Spring Security, **`principal`** là đối tượng đại diện cho chủ thể đã gửi yêu cầu xác thực hoặc đang được hệ thống nhận diện. Sau khi xác thực, `Authentication.getPrincipal()` thường được truy cập từ `SecurityContext`, từ controller qua `@AuthenticationPrincipal` hoặc từ mã phân quyền và audit.

Điều rất dễ làm khi bắt đầu với Spring Boot + Spring Data JPA là:

1. Có sẵn entity `Account` hoặc `UserEntity` chứa id, username, password hash, email, địa chỉ, số điện thoại, vai trò, quan hệ đơn hàng, tổ chức, lịch sử giao dịch.
2. Viết `UserDetailsService.loadUserByUsername(...)` và cho chính entity này triển khai `UserDetails`.
3. Trả nguyên entity ra khỏi `UserDetailsService`, để provider đưa nó vào `Authentication.principal`.
4. Mỗi request lại lấy `SecurityContextHolder.getContext().getAuthentication().getPrincipal()` và xem entity đó như “người dùng hiện tại”, thậm chí trả thẳng từ API.

Cách này **có thể chạy** trong ứng dụng nhỏ, nhưng tạo sự gắn kết ngoài ý muốn giữa dữ liệu nghiệp vụ, persistence và security. Nó có thể làm rò rỉ dữ liệu, kéo theo proxy/lazy loading, gây vấn đề session serialization và khiến thông tin quyền hoặc trạng thái tài khoản bị cũ.

**Nguyên tắc khuyến nghị:** Giữ principal là một biểu diễn **nhỏ, rõ trách nhiệm và xuất phát từ nguồn đã kiểm chứng**; chỉ giữ những trường thật sự cần để nhận diện/authorize. Khi một use case cần thông tin nghiệp vụ, tải chúng qua repository/service có kiểm soát quyền và transaction phù hợp.

Đây là quyết định thiết kế, **không phải luật rằng mọi entity làm principal đều bị Spring Security cấm**. Mục tiêu là tránh biến entity đầy đủ thành principal theo thói quen mà không phân tích dữ liệu, vòng đời và ranh giới tin cậy.

## 2. Bốn khái niệm thường bị trộn

| Thành phần | Mục đích | Dữ liệu thường có | Vòng đời điển hình |
| --- | --- | --- | --- |
| **JPA entity** (`AccountEntity`) | Lưu/biến đổi trạng thái miền nghiệp vụ | ID, PII, password hash, trạng thái, quan hệ JPA, audit | Persistence context và transaction; có thể managed/detached |
| **`UserDetails`** | Cung cấp dữ liệu mà username/password provider cần để kiểm tra đăng nhập | username, **password hash tạm phục vụ xác minh**, authorities, cờ trạng thái | Load khi xác thực/cache tùy cấu hình; có thể trở thành principal |
| **`Authentication`** | Mô tả request xác thực hoặc kết quả đã được tin cậy | principal, credentials, authorities, details, `isAuthenticated()` | Tồn tại trong security context của request; có thể lưu trong session |
| **Principal tối thiểu** (`AppPrincipal`, `SafePrincipal`) | Mang danh tính đã xác minh qua lớp web/security | userId ổn định, username hiển thị, tenantId đã xác minh nếu cần | Request/session/token mapping; không chứa toàn bộ entity graph |

Một `UserDetails` không bắt buộc là JPA entity. Nó có thể là `org.springframework.security.core.userdetails.User` sẵn có hoặc một adapter `UserDetails` do ứng dụng tự định nghĩa.

Tương tự, principal sau xác thực **không phải luôn `UserDetails`**: cơ chế JWT, OAuth2/OIDC, SAML, X.509 hoặc một authentication provider tùy biến có thể trả đối tượng khác. Đừng ép mọi principal thành `UserEntity` hoặc giả định mọi cơ chế đều có mật khẩu.

### Luồng danh tính đúng trách nhiệm

~~~text
                  CSDL / domain repository
                    |
                    v
             AccountEntity (đầy đủ)
              id, email, phone,
              password hash, roles,
              order history, ...
                    |
                    | ánh xạ có chủ đích
                    v
           UserDetailsService
                    |
                    v
       UserDetails (dữ liệu auth cần thiết)
              username, hash,
              authorities, flags
                    |
                    v
        DaoAuthenticationProvider
           + PasswordEncoder
                    |
                    v
      Authentication đã xác thực
           |
           +--> principal tối thiểu
           |    hoặc UserDetails chuyên cho auth
           |
           +--> authorities đã kiểm tra
                    |
                    v
              SecurityContext
                    |
            Controller / service
                    |
           dùng userId, tenantId
                    |
                    v
      Truy vấn entity/DTO theo use case
       + kiểm tra quyền trên dữ liệu mới
~~~

Mô hình này tách **“ai đang gửi request?”** khỏi **“hồ sơ, địa chỉ, đơn hàng hay trạng thái hiện tại của người đó là gì?”**.

## 3. Vì sao entity đầy đủ làm principal gây rủi ro?

### 3.1. Mở rộng phạm vi tồn tại của dữ liệu nhạy cảm

Một entity có thể chứa password hash, email cá nhân, số điện thoại, ngày sinh, địa chỉ thanh toán, ghi chú nội bộ, flags chống gian lận hoặc danh sách quyền. Nếu đưa cả entity vào principal, những dữ liệu đó có thể đi theo:

- `SecurityContext` nằm trong memory của request hoặc HTTP session;
- session store phân tán và các bản sao session;
- bộ nhớ cache và quá trình serialize/deserialize;
- câu lệnh log `authentication.getPrincipal()` hoặc `toString()` được sinh tự động;
- debug snapshot, traces, exception reporting hoặc object mapping;
- controller vô tình trả `principal` trong JSON.

**Không cần lộ raw password mới có sự cố.** Password hash cũng là dữ liệu nhạy cảm: nếu bị lấy, kẻ tấn công có thể thử đoán offline. PII và thông tin vận hành nội bộ lại có rủi ro riêng. Principal chứa càng ít dữ liệu, tác động khi bị log hoặc lưu ở nơi không mong đợi càng nhỏ.

`@JsonIgnore` trên vài field của entity không đủ làm ranh giới bảo mật: nó chỉ ảnh hưởng một số cơ chế JSON serialization, không tự che dữ liệu khỏi `toString`, reflection, binary serialization, custom serializer hoặc object graph khác.

**Điều nên làm:** Chọn rõ những trường được phép xuất hiện trong principal, audit định kỳ và tuyệt đối không trả thẳng `Authentication`/entity từ endpoint chỉ để “lấy user hiện tại”.

### 3.2. JPA entity mang theo proxy, quan hệ và lazy loading

Ví dụ entity có:

~~~java
@OneToMany(mappedBy = "account", fetch = FetchType.LAZY)
private List<OrderEntity> orders;
~~~

Sau khi login, một controller hoặc logger gọi `principal.getOrders()` trong request khác. Entity có thể đã tách khỏi `EntityManager` và association chưa được load: có nguy cơ `LazyInitializationException`. Nếu persistence context vẫn mở, truy vấn bất ngờ có thể chạy ở nơi không mong muốn, gây N+1 và tải quá nhiều dữ liệu.

Các quan hệ hai chiều như `account.orders -> order.account -> account...` còn dễ gây vòng lặp khi JSON serialization nếu thiếu cấu hình. Đổi sang `FetchType.EAGER` để “sửa lỗi principal” thường kéo theo overfetch và không giải quyết ranh giới kiến trúc.

**Điều nên làm:** Ánh xạ các trường xác thực cần thiết thành projection/`UserDetails` **khi truy vấn còn trong transaction thích hợp**. Khi cần orders, gọi service nghiệp vụ để truy vấn chúng với chính sách phân quyền. Principal không cần sở hữu entity graph.

### 3.3. Principal có vòng đời khác transaction

Entity được quản lý trong persistence context và chuyển sang detached khi context kết thúc. Nhưng `Authentication` có thể tồn tại lâu hơn một transaction, đặc biệt khi Spring Security lưu `SecurityContext` trong HTTP session.

Nếu giữ entity trong principal rồi sửa trường của nó ở request khác, bạn khó xác định đó là thay đổi được quản lý/persist, thay đổi trên bản detached hay thay đổi tình cờ trên object dùng chung. Không nên dùng principal như một đơn vị update dữ liệu.

**Điều nên làm:** Principal chỉ chứa định danh ổn định; service nhận định danh đó, tải entity mới trong transaction, kiểm tra tenant/quyền/trạng thái rồi mới cập nhật.

### 3.4. Serialization và hệ thống phân tán

Khi session được lưu trong Redis/database hoặc đồng bộ giữa các node, serializer có thể cần biểu diễn `SecurityContext`, `Authentication` và principal. JPA entity với Hibernate proxy, lazy collection, các loại object không tương thích serializer hoặc liên kết đến object không `Serializable` có thể làm việc lưu/khôi phục session thất bại hay chậm.

Không phải mọi kiến trúc dùng Java serialization, và không phải cứ entity là luôn không serialize được. Vấn đề là **principal trở thành đối tượng trao đổi giữa các tầng/nút** mà entity graph vốn không được thiết kế để phục vụ.

Một `record`/class principal nhỏ, có kiểu dữ liệu rõ ràng và chính sách serialization được kiểm thử, thường dễ tiến hóa hơn. Nếu session lưu qua phiên bản ứng dụng, cân nhắc versioning/migration của principal.

### 3.5. Thay đổi tài khoản không tự cập nhật principal đã phát hành

Người dùng đăng nhập lúc 9 giờ với `ROLE_ADMIN`. Lúc 10 giờ admin khác thu hồi vai trò đó. Nếu `Authentication` cũ trong session vẫn chứa authority đã cấp lúc 9 giờ, việc sửa entity trong DB **không mặc nhiên** sửa danh sách quyền đang lưu trong context.

Tương tự, khóa user, thay username, chuyển tenant hoặc đổi mật khẩu không nhất thiết vô hiệu một session cũ hay một JWT đã ký.

Giữ entity trực tiếp trong principal cũng không bảo đảm “luôn đọc dữ liệu mới”; ngược lại, thường tạo một **snapshot khó quản lý**.

**Điều nên làm:** Có chiến lược refresh/revoke/timeout session, khóa phiên, phát hành token ngắn hạn hoặc kiểm tra trạng thái mới tại điểm nhạy cảm. Mức cập nhật tùy rủi ro của thao tác.

### 3.6. Equality, hashCode và trạng thái mutable

Entity dùng `equals()/hashCode()` dựa trên business key có thể thay đổi, Hibernate proxy hoặc ID chưa được gán khi persist. Nếu entity đó lại làm principal trong map/set/session registry, thay đổi trạng thái sau login dễ tạo bug khó tái hiện.

Còn nếu domain entity trở thành user identity ở khắp ứng dụng, một lần refactor schema, rename field hoặc thay quan hệ có thể ảnh hưởng luôn authentication, session và test bảo mật.

**Điều nên làm:** Dùng ID ổn định làm khóa định danh; tránh đưa mutable business state vào cách so sánh identity hoặc cache key. Nhận dạng không nên phụ thuộc vào địa chỉ, số điện thoại, tên hiển thị hoặc số đơn hàng.

### 3.7. Dễ biến phân quyền thành đọc nhầm dữ liệu trong entity

Nếu controller xem `principal.getRole()` rồi tin ngay, hệ thống có thể dùng thông tin không được cập nhật hoặc không đúng tenant. Đặc biệt với multi-tenant, một `role=ADMIN` không có tenant scope rất dễ bị diễn giải như admin của mọi tenant.

Phân quyền thực tế cần tách rõ:

- **Danh tính đã xác minh:** userId, cách xác thực, tenant được chọn và đã kiểm chứng.
- **Authorities của Authentication:** quyền cao cấp mà Spring Security dùng tại thời điểm kiểm tra.
- **Quyền trên tài nguyên cụ thể:** record thuộc tenant nào, người dùng được thao tác bản ghi đó không, chính sách có vừa thay đổi không.

Principal tối thiểu giảm nhầm lẫn giữa **thuộc tính nghiệp vụ** và **quyết định bảo mật**.

## 4. Chọn những trường nào cho principal?

Không có một cấu trúc bắt buộc cho mọi hệ thống, nhưng có thể bắt đầu từ:

~~~java
// Chỉ là hợp đồng danh tính, không chứa dữ liệu persistence.
public record AppPrincipal(
        long userId,
        String username,
        String tenantId
) implements java.io.Serializable {}
~~~

Đây là **đoạn khai báo minh họa**: các trường phải là dữ liệu đã được xác minh từ nguồn tin cậy; nếu hệ thống không multi-tenant, bỏ `tenantId`. Trong hệ thống có tenant, chỉ đưa tenantId đã được kiểm tra quyền membership, không sao chép vô điều kiện giá trị client gửi.

Đánh giá từng loại dữ liệu:

| Trường | Có nên ở principal? | Cân nhắc |
| --- | --- | --- |
| `userId` ổn định | Thường nên | Khóa identity đáng tin để service truy vấn dữ liệu mới |
| `username` | Có thể | Hữu ích cho hiển thị/audit; có thể đổi, đừng làm khóa duy nhất nếu hệ thống hỗ trợ đổi tên |
| `tenantId` | Có điều kiện | Phải xác minh user thực sự thuộc tenant, tránh client tự khai |
| Authorities/roles | Trong `Authentication.getAuthorities()` | Không nhúng lặp thành nhiều danh sách lệch nhau; cần lifecycle khi quyền đổi |
| Email tên hiển thị | Chỉ khi thật cần | Có thể là PII hoặc hay thay đổi; ưu tiên DTO truy vấn cho UI |
| Password hash | Chỉ ở `UserDetails` tạm dùng **trước** kiểm tra password | Không đưa vào principal/session dài hạn sau login |
| Raw password, refresh token, API secret | Không | Đây là credential; không để trong principal |
| Địa chỉ, SĐT, lịch sử mua hàng | Không theo mặc định | Load tại service khi use case được authorize |
| JPA `@OneToMany` / `@ManyToOne` | Tránh | Không gắn entity graph/proxy vào context |
| `EntityManager`, service, repository | Không | Là dependency, không phải identity |
| Cờ khóa tài khoản | Cần cho kiểm tra login; trong principal sau login tùy chính sách | Trạng thái có thể đổi, nên thiết kế revalidation hoặc thu hồi |

**Nguyên tắc tối thiểu không đồng nghĩa chỉ giữ một `String username`.** Nếu nghiệp vụ cần một ID bất biến, một tenant đã xác minh hay thông tin authentication strength để authorize, thêm đúng phần đó với lý do rõ ràng. Hạn chế phần vô ích và dữ liệu nhạy cảm.

## 5. Vì sao UserDetails vẫn có password hash nhưng principal lâu dài nên không?

Đây là điểm quan trọng để tránh một “giải pháp” sai: nếu xóa password hash **trước khi** `DaoAuthenticationProvider` kiểm tra, cơ chế username/password có thể không xác thực được.

Luồng chuẩn với `DaoAuthenticationProvider`:

1. `UsernamePasswordAuthenticationFilter` hoặc bộ lọc tương ứng tạo `UsernamePasswordAuthenticationToken` chưa xác thực, chứa username và raw password do client gửi qua HTTPS.
2. `ProviderManager` chuyển request tới `DaoAuthenticationProvider`.
3. Provider gọi `UserDetailsService.loadUserByUsername(username)`. Dữ liệu trả về phải chứa password hash có thể kiểm tra bằng `PasswordEncoder`, authorities và trạng thái tài khoản.
4. Provider kiểm tra raw password với hash, kiểm tra account locked/disabled/expired và tạo `Authentication` đã xác thực, thường với `UserDetails` làm principal.
5. `ProviderManager` mặc định gọi `eraseCredentials()` trên kết quả nếu hỗ trợ `CredentialsContainer`. `org.springframework.security.core.userdetails.User` hỗ trợ giao diện này và có thể xóa password của chính nó sau xác thực.

**Đích cần tối ưu là password hash chỉ hiện diện ở nơi thật cần để kiểm chứng**, không phải loại bỏ nó khỏi cơ chế kiểm chứng.

Một cách đơn giản là để `UserDetailsService` ánh xạ bản ghi/đối tượng entity sang `org.springframework.security.core.userdetails.User` mới cho mỗi lần tải:

~~~java
// MÃ MINH HỌA BÊN TRONG UserDetailsService; "account" là dữ liệu
// đã được repository tìm theo username trong transaction phù hợp.
return User.withUsername(account.getUsername())
        .password(account.getPasswordHash())
        .authorities("ROLE_READER")
        .disabled(!account.isEnabled())
        .accountLocked(account.isLocked())
        .build();
~~~

`User` chỉ giữ các trường đăng nhập cần thiết; nó **không phải entity** và không mang quan hệ JPA. Sau xác thực, password trong object này có thể được xóa mà **không làm thay đổi entity đang quản lý trong JPA**.

**Cảnh báo cache:** Nếu `UserDetailsService` trả một object `UserDetails` đang được cache dùng chung, khi `ProviderManager` xóa credentials trên principal, object cache đó có thể bị xóa password hash. Lần đăng nhập sau có thể thất bại. Nên dùng bản sao riêng cho kết quả, tách cache khỏi bản principal dùng trong `Authentication`, hoặc thiết kế provider/cache theo tài liệu; đừng mặc định việc xóa credential không ảnh hưởng tham chiếu chung.

Nếu cần `userId` trong principal và dùng `DaoAuthenticationProvider` mặc định, có thể viết **custom `UserDetails` nhỏ** bao gồm userId, username, password hash tạm và các cờ/authorities; nó vẫn không phải entity đầy đủ. Sau đó cần cơ chế xóa credential phù hợp, đặc biệt nếu áp dụng caching. Một lựa chọn khác là tạo principal session tối thiểu ở thành phần đáng tin **sau khi đã xác thực thành công**.

## 6. Thiết kế ba lớp: AccountEntity → AuthDetails → SafePrincipal

Hãy chia dữ liệu theo ý nghĩa:

~~~text
ACCOUNT ENTITY (domain/persistence)
  id, username, passwordHash, enabled,
  email, phone, address, orders, internalNotes,
  relationships, auditing, tenant mappings
                   |
                   | lấy/ánh xạ phần cần cho login
                   v
AUTH DETAILS (input cho DaoAuthenticationProvider)
  username, passwordHash, account flags,
  GrantedAuthority
                   |
                   | kiểm tra password + account status
                   v
TRUSTED Authentication
  principal an toàn, authorities, auth details
                   |
                   v
SECURITY CONTEXT / SESSION (nếu dùng)
  userId, username, thông tin auth tối thiểu
                   |
                   v
SERVICE NGHIỆP VỤ
  nhận userId -> lấy entity/DTO mới
  -> áp dụng object-level authorization
~~~

Không nên lưu `AccountEntity` vào `HttpSession` hay context để “lần sau khỏi query DB”. Hệ thống có thể **cache dữ liệu domain ở service/repository** theo quy tắc riêng, hoặc chọn TTL/eviction phù hợp mà không biến toàn bộ entity graph thành principal.

### Ranh giới áp dụng

- **Persistence:** repository tìm entity/projection; quyết định fetch tối thiểu và transaction.
- **Identity mapping:** chuyển bản ghi thành một object xác thực rõ ràng, không mang entity graph.
- **Authentication:** provider xác minh credential với `PasswordEncoder`, đánh giá trạng thái tài khoản và trả `Authentication`.
- **Session/context:** lưu danh tính tối thiểu do server tin cậy; bảo vệ cookie/session theo chính sách.
- **Application service:** dùng userId/tenantId để kiểm tra quyền với tài nguyên, tải thông tin mới khi cần.
- **API response:** tạo response DTO riêng; không dùng `Authentication.getPrincipal()` làm DTO mặc định.

## 7. Demo Java 17 chạy được: đối chiếu entity đầy đủ và principal an toàn

Demo dùng Spring Security Core **6.5.11** để minh họa một tình huống rõ ràng:

1. Một bản ghi tài khoản đầy đủ có password hash, email cá nhân, địa chỉ và ghi chú nội bộ.
2. `UserDetailsService` chỉ ánh xạ các trường cần thiết sang `UserDetails` chuyên cho xác thực.
3. `DaoAuthenticationProvider` kiểm tra password bằng BCrypt rồi tạo authenticated result.
4. Từ kết quả **đã kiểm chứng**, mã tin cậy tạo một `SafePrincipal` chỉ có `userId` và `username`, giữ nguyên authorities đã được provider cấp.
5. Demo chứng minh principal mới **không phải entity**, không chứa password, vẫn trả đúng `getName()` và roles.

**Lưu ý:** Bản ghi `AccountRow` là **record giả lập dữ liệu persistence**, không phải JPA entity thực, để demo có thể chạy mà không cần database hoặc Hibernate. Trong ứng dụng có JPA, nó tương ứng với dữ liệu repository lấy từ entity/projection. Việc dựng một token authenticated **chỉ được thực hiện bên trong mã server đáng tin sau khi xác thực**, không phải API cho client tự tạo đăng nhập.

### 7.1. Cấu trúc dự án

~~~text
principal-boundary-demo/
├── build.gradle
└── src/main/java/demo/PrincipalBoundaryDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.PrincipalBoundaryDemo'
}
~~~

**File `src/main/java/demo/PrincipalBoundaryDemo.java`:**

~~~java
package demo;

import java.io.Serial;
import java.io.Serializable;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.AuthenticatedPrincipal;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PrincipalBoundaryDemo {

    // Giả lập dữ liệu nghiệp vụ trong kho lưu trữ, KHÔNG phải JPA entity thật.
    record AccountRow(
            long id,
            String username,
            String passwordHash,
            String personalEmail,
            String billingAddress,
            String internalNote
    ) {}

    // Danh tính nhỏ, ổn định; không có password hay entity graph.
    record SafePrincipal(long userId, String username)
            implements AuthenticatedPrincipal, Serializable {

        @Serial
        private static final long serialVersionUID = 1L;

        @Override
        public String getName() {
            return username;
        }
    }

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        AccountRow account = new AccountRow(
                42L,
                "linh",
                encoder.encode("demo-password-only"),
                "private@example.test",
                "Private billing address",
                "Internal compliance note"
        );

        // Mỗi lần gọi tạo một UserDetails mới; không trả AccountRow.
        UserDetailsService detailsService = username -> {
            if (!account.username().equals(username)) {
                throw new UsernameNotFoundException("Unknown user");
            }
            return User.withUsername(account.username())
                    .password(account.passwordHash())
                    .roles("READER")
                    .build();
        };

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(detailsService);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager = new ProviderManager(provider);

        // Client request: chưa đáng tin.
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "linh", "demo-password-only"
                );

        Authentication verified = manager.authenticate(request);
        UserDetails temporary = (UserDetails) verified.getPrincipal();

        System.out.println("verified.authenticated=" + verified.isAuthenticated());
        System.out.println("verified.name=" + verified.getName());
        System.out.println("verified.principalIsEntity="
                + (verified.getPrincipal() == account));
        System.out.println("verified.passwordErased="
                + (temporary.getPassword() == null));

        // Ở demo chỉ có một account và ID chắc chắn thuộc username đã xác minh.
        // Ứng dụng thật phải lấy userId đã xác minh và xét tenant chính xác.
        SafePrincipal safePrincipal =
                new SafePrincipal(account.id(), verified.getName());

        // Chỉ dùng authenticated factory sau khi manager xác thực thành công.
        Authentication safeResult =
                UsernamePasswordAuthenticationToken.authenticated(
                        safePrincipal, null, verified.getAuthorities()
                );

        boolean reader = safeResult.getAuthorities().stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority()));

        System.out.println("safe.type="
                + safeResult.getPrincipal().getClass().getSimpleName());
        System.out.println("safe.name=" + safeResult.getName());
        System.out.println("safe.id=" + safePrincipal.userId());
        System.out.println("safe.reader=" + reader);
        System.out.println("safe.credentialsAbsent="
                + (safeResult.getCredentials() == null));
        System.out.println("safe.principalIsEntity="
                + (safeResult.getPrincipal() == account));
    }
}
~~~

### 7.2. Chạy demo và đầu ra

Ở thư mục `principal-boundary-demo`, với JDK 17+ và Gradle tương thích:

~~~bash
gradle -q run
~~~

Hoặc nếu dự án đã có Gradle Wrapper, dùng `./gradlew -q run`; trên Windows có thể dùng `gradlew.bat -q run`. Lần chạy đầu cần tải dependencies từ Maven Central.

**stdout do các câu lệnh `System.out.println` tạo ra**, không tính log riêng của Gradle/library nếu môi trường cấu hình thêm:

~~~text
verified.authenticated=true
verified.name=linh
verified.principalIsEntity=false
verified.passwordErased=true
safe.type=SafePrincipal
safe.name=linh
safe.id=42
safe.reader=true
safe.credentialsAbsent=true
safe.principalIsEntity=false
~~~

### 7.3. Giải thích kết quả

- `verified.authenticated=true`: password đã được `DaoAuthenticationProvider` kiểm tra dựa vào hash mà `UserDetailsService` trả về.
- `verified.principalIsEntity=false`: principal là `UserDetails` do service **tạo mới**, không phải bản ghi nghiệp vụ `AccountRow`.
- `verified.passwordErased=true`: `ProviderManager` theo mặc định gọi cơ chế xóa credential; `User` có hỗ trợ `CredentialsContainer`. Việc xóa này **không** xóa password hash khỏi `AccountRow` trong demo.
- `safe.type=SafePrincipal` và `safe.id=42`: principal biểu diễn danh tính đã xác minh bằng ID ổn định; không có email, địa chỉ hay internal note.
- `safe.name=linh`: `SafePrincipal` triển khai `AuthenticatedPrincipal.getName()` để `Authentication.getName()` trả username dễ dự đoán; nếu chỉ dùng record thường với `toString()`, kết quả getName có thể không như mong muốn.
- `safe.reader=true`: authorities đi từ kết quả xác thực đã được tin cậy, không được lấy từ body client.
- `safe.credentialsAbsent=true` và `safe.principalIsEntity=false`: token trình bày identity không giữ password và không giữ entity graph.

**Quan trọng về tính tích hợp:** Demo chỉ xây và in kết quả của các `Authentication` object. Nó **không** tạo website, session hay tự đưa `safeResult` vào `SecurityContextHolder`. Trong ứng dụng thực, muốn principal mới xuất hiện trong context/session, phải tích hợp phép chiếu này vào provider/filter xử lý authentication thành công, bảo toàn đầy đủ cơ chế session, CSRF, success/failure handlers và trust boundary. Đừng sao chép thao tác `authenticated(...)` vào controller nhận dữ liệu chưa được xác minh.

### 7.4. Quyết định thiết kế trong demo

Có hai phương án đều phù hợp:

- Dùng trực tiếp **`UserDetails` nhỏ** làm principal sau xác thực, miễn nó không mang nguyên entity hoặc credential không cần thiết và chính sách xóa credential/caching đã đúng.
- Dùng **`SafePrincipal`** được tạo bởi thành phần tin cậy sau bước credential check, chỉ giữ identity lâu dài. Khi đó phần nhập vào provider vẫn có thể là `UserDetails` chứa password hash tạm phục vụ login.

Phương án hai hữu ích khi thiết kế session principal chung cho nhiều cơ chế xác thực (password, OIDC, passkey) nhưng cần cẩn trọng ánh xạ authorities, userId và tenantId dựa trên danh tính đã được kiểm chứng.

## 8. Tích hợp với JPA trong Spring Boot

### 8.1. Phép chiếu auth dữ liệu ngay từ repository

Trong ứng dụng thực, `AccountEntity` có thể rất lớn. Để login không phải load cả orders, addresses hoặc các quan hệ, nên thiết kế query lấy dữ liệu xác thực cần thiết.

Ví dụ **mã minh họa chưa độc lập biên dịch** vì `AccountRepository`, `AccountAuthRow` và entity/domain chưa được khai báo đầy đủ trong đoạn này:

~~~java
@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    public DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) {
        AccountAuthRow row = accounts.findAuthDataByUsername(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Account unavailable"));

        return User.withUsername(row.username())
                .password(row.passwordHash())
                .authorities(row.authorities().toArray(String[]::new))
                .disabled(!row.enabled())
                .accountLocked(row.locked())
                .build();
    }
}
~~~

`AccountAuthRow` chỉ nên chứa các trường xác thực cần thiết: username, passwordHash, trạng thái và authorities. Repository có thể tạo DTO/projection; nếu query roles riêng, cần giải quyết join hoặc batch một cách có chủ đích. Trong hệ thống multi-tenant, khóa tìm kiếm phải đảm bảo username được ràng buộc với tenant đã xác minh.

Không trả `AccountEntity` từ method trên chỉ vì entity đã `implements UserDetails`. Nếu entity được load cho quá trình mapping, **hãy trả một đối tượng mới**; khi transaction đóng, principal không còn nắm reference tới managed entity/lazy collection.

Lưu ý: `User.withUsername(...).password(...)` ở đây nhận **hash đã lưu**. Code không encode lại password hash khi load; provider dùng `PasswordEncoder.matches(rawPassword, storedHash)`. Chỉ encode khi tạo/đổi mật khẩu, theo chính sách lưu trữ.

### 8.2. Service nghiệp vụ lấy userId từ principal rồi truy vấn lại

Với principal an toàn đã được cấu hình trong authentication success path, controller có thể nhận identity và chuyển xuống service:

~~~java
// Mã minh họa trong Spring MVC đã có security config và service.
@GetMapping("/me")
public ProfileResponse myProfile(
        @AuthenticationPrincipal SafePrincipal principal) {
    return profileService.loadVisibleProfile(principal.userId());
}
~~~

Đây **không** phải chương trình standalone; `ProfileResponse`, `profileService` và các annotation/dependencies thuộc dự án Spring Boot cụ thể. Trong ứng dụng thật, service còn phải kiểm tra tài khoản/tenant hợp lệ và chỉ trả response DTO đã chọn field cho client.

Từ đó:

~~~text
@AuthenticationPrincipal SafePrincipal(userId=42)
        |
        v
ProfileService.loadVisibleProfile(42)
        |
        v
AccountRepository / ProfileRepository
        |
        +--> query dữ liệu mới
        +--> kiểm tra trạng thái account/tenant
        +--> enforce object-level authorization
        |
        v
ProfileResponse DTO (chỉ trường được phép trả)
~~~

Chọn cách truy vấn và cache theo use case. Có thể dùng `@Transactional(readOnly = true)` trong application service ở ranh giới truy vấn phù hợp, thay vì kỳ vọng JPA entity từ lúc login sẽ vẫn attached trên mọi request.

### 8.3. Không trả principal trực tiếp về HTTP

Sai lầm thường gặp:

~~~java
// KHÔNG NÊN DÙNG làm endpoint trả user info.
@GetMapping("/me")
public Object me(Authentication authentication) {
    return authentication.getPrincipal();
}
~~~

Nếu principal từng là JPA entity, đây có thể vô tình biến toàn bộ entity thành response JSON, hoặc kích hoạt lazy-loading/serialization error. Ngay cả principal tối thiểu cũng nên được xem là chi tiết nội bộ của security và chỉ **chuyển trường phù hợp** sang DTO công khai theo contract API.

Tương tự, log `authentication.getPrincipal().toString()` một cách vô điều kiện có thể rò thông tin; chỉ ghi identity ID/username tối thiểu theo chính sách logging và bảo vệ dữ liệu.

## 9. Principal và các cơ chế xác thực khác

Không phải mọi Authentication trong Spring Security được tạo bởi DAO username/password:

| Cơ chế | Principal thường là gì? | Thiết kế tránh entity |
| --- | --- | --- |
| Form login + DAO | `UserDetails`, thường là `User` hoặc custom UserDetails | Ánh xạ tối thiểu từ repository, kiểm soát hash/credential erasure |
| HTTP session | `Authentication` đã xác thực được lưu/khôi phục | Session lưu identity tối thiểu; tránh entity/proxy và dữ liệu nhạy cảm |
| JWT Resource Server | `Jwt`/principal liên quan JWT theo configuration | Xác minh chữ ký, issuer, audience; ánh xạ subject sang userId nếu cần, tải domain data riêng |
| OAuth2/OIDC login | `OAuth2User`/`OidcUser` | Ánh xạ subject theo issuer và account linking; đừng lưu toàn bộ account entity vào principal |
| mTLS/X.509 | Danh tính certificate sau xác minh TLS | Ánh xạ certificate identity sang internal user/serviceId; authorize theo quyền thực tế |
| Passkey/WebAuthn | Identity được xác nhận sau challenge/assertion | Gắn userId từ credential registry đáng tin rồi tạo context/session an toàn |

Đối với OIDC, **`sub` kết hợp `iss`** là định danh bên phát hành; không nên tự đồng nhất `sub` với ID nội bộ của mọi hệ thống. Với JWT, **decode claims không phải validate token**; resource server phải xác minh token trước khi trust subject hay authorities.

Đối với multi-tenant, một claim `tenantId` hoặc tham số URL chỉ có giá trị sau khi hệ thống kiểm tra user có quyền truy cập tenant đó. Khi tenant switching, xác định rõ identity/context nào phải phát hành lại hay reload.

## 10. Khi dữ liệu nghiệp vụ hoặc quyền thay đổi giữa các request

Principal tối thiểu tạo ranh giới sạch hơn nhưng **không tự giải quyết việc refresh quyền**. Hệ thống vẫn cần chính sách vòng đời danh tính.

| Thay đổi | Điều có thể xảy ra nếu chỉ dựa vào context cũ | Cách xử lý thường cần |
| --- | --- | --- |
| Admin thu hồi role | Authorities trong session/JWT vẫn là snapshot trước đó | Session invalidation, token revocation/TTL, authority reload tại điểm nhạy cảm |
| Account bị khóa | Session cũ có thể tiếp tục hoạt động tùy cấu hình | Chặn request ở policy phù hợp, thu hồi session hoặc revalidation |
| User đổi username | `authentication.getName()` có thể còn tên cũ | Dùng userId ổn định cho identity/DB, cập nhật tên hiển thị theo lifecycle |
| Email/địa chỉ đổi | Thông tin trong principal cũ có thể stale | Load profile mới tại service khi cần, không giữ PII không thiết yếu trong session |
| Tenant membership bị thu hồi | Context/claim cũ có thể cho phép nhầm tenant | Kiểm tra membership/authorization và có cơ chế refresh/revoke |
| Password đổi | Token/session đã phát hành có thể vẫn hợp lệ | Chính sách logout thiết bị, revoke refresh token, yêu cầu login lại |

Độ thường xuyên kiểm tra lại phụ thuộc rủi ro. Một ứng dụng nội bộ có session ngắn và role hiếm đổi khác với dịch vụ tài chính yêu cầu thu hồi quyền gần tức thời. Điều cốt lõi là **phải biết mình đang dùng snapshot nào, hết hạn lúc nào và sự kiện nào làm nó mất hiệu lực**.

## 11. Tình huống lỗi thực tế và hướng sửa

### Tình huống A: Controller gặp LazyInitializationException

**Hiện tượng:** Sau khi login thành công, request mới gọi `((AccountEntity) principal).getOrders()` rồi lỗi lazy loading.

**Nguyên nhân:** Entity được giữ từ lần xác thực đã tách khỏi persistence context, association chưa được khởi tạo. Việc thay `LAZY` bằng `EAGER` dễ kéo theo truy vấn lớn.

**Sửa:** Principal chỉ giữ userId. Controller gọi `orderService.findVisibleOrders(userId)`; service mở transaction/query đúng use case và authorize từng đối tượng cần thiết.

### Tình huống B: API /me rò field nội bộ

**Hiện tượng:** `return authentication.getPrincipal()` vô tình xuất JSON gồm phone, address, passwordHash hoặc internalFlags.

**Nguyên nhân:** Entity/full object bị dùng làm security principal và HTTP DTO cùng lúc.

**Sửa:** Định nghĩa response DTO chỉ có field được API công khai; đổi principal sang identity tối thiểu; kiểm thử JSON response để bảo đảm không có dữ liệu nhạy cảm.

### Tình huống C: Session Redis không serialize được

**Hiện tượng:** Login thành công ở request đầu nhưng session persistence lỗi khi ghi/khôi phục principal chứa proxy hoặc collection.

**Nguyên nhân:** Principal mang object graph JPA với kiểu không tương thích serializer/phiên bản schema.

**Sửa:** Dùng principal nhỏ/serialize được theo cơ chế session đã chọn, bỏ graph/proxy; xác minh khả năng round-trip serialization trong integration test.

### Tình huống D: User bị thu hồi role nhưng quyền vẫn còn

**Hiện tượng:** DBA đổi role trong bảng `users`/`authorities`, session hiện tại vẫn được phép thao tác theo role cũ.

**Nguyên nhân:** `Authentication.getAuthorities()` là dữ liệu tại thời điểm xác thực/lần refresh gần nhất.

**Sửa:** Chọn chính sách thu hồi context/token và kiểm tra quyền nhạy cảm trên dữ liệu cập nhật. Đừng kỳ vọng giữ JPA entity trong principal sẽ tự refresh authorities.

### Tình huống E: Cùng ID người dùng, sai tenant

**Hiện tượng:** API nhận `tenantId` từ query và lấy `userId` trong principal rồi truy cập record tenant khác.

**Nguyên nhân:** Identity nội bộ được dùng mà thiếu kiểm tra tenant membership và quyền object-level.

**Sửa:** Dùng tenant context đã được xác minh, enforce ở service/repository, không cho client tự quyết quyền thuộc tenant nào.

### Tình huống F: Xóa credentials làm cache user bị hỏng

**Hiện tượng:** Login đầu thành công; lần tiếp theo provider lấy `UserDetails` cache nhưng password đã `null`.

**Nguyên nhân:** Cache và `Authentication.principal` cùng tham chiếu một object `CredentialsContainer`; `ProviderManager` xóa credentials sau thành công.

**Sửa:** Dùng copy tách biệt cho principal/result, điều chỉnh cache/provider đúng hợp đồng. Không tùy tiện tắt `eraseCredentialsAfterAuthentication` chỉ để tránh lỗi.

## 12. Các lỗi thiết kế cần nhận diện khi review code

| Dấu hiệu trong code | Câu hỏi cần đặt | Hướng cải thiện |
| --- | --- | --- |
| `class UserEntity implements UserDetails` | Entity có chứa PII, relations, secrets, mutable state không? | Tạo `UserDetails` adapter riêng |
| `return userRepository.findByUsername(...)` trong `loadUserByUsername` | Service đang trả entity thẳng, hay đã map projection? | Trả object chuyên cho authentication |
| `Authentication.getPrincipal()` bị cast sang `AccountEntity` | Service có thể sử dụng ID/typed principal thay vì entity không? | Refactor principal nhỏ; query domain data ở service |
| `@AuthenticationPrincipal AccountEntity user` trong controller | Có kéo JPA entity qua request/transaction không? | Chỉ inject userId hoặc principal tối thiểu |
| `return principal` ở API | Object có field nội bộ/secret/lazy graph không? | Response DTO có allowlist field |
| `log.info("{}", principal)` | `toString` có chứa hash/PII không? | Chỉ log định danh tối thiểu, không log secrets |
| `principal.getOrders()`/`getPayments()` | Có tạo query ngoài transaction hoặc overfetch không? | Dùng repository/service nghiệp vụ |
| `roles` nằm cả trong entity, principal, token, session | Khi role đổi nguồn nào là truth? | Thiết kế refresh/revocation và mapping rõ ràng |
| Đưa `@Entity` vào distributed session | Serializer, proxy, schema/versioning đã được kiểm thử? | Nhỏ hóa principal, kiểm thử round-trip |
| Lấy userId từ body và tạo authenticated token | ID đó đã được provider xác minh chưa? | Chỉ tạo trusted principal sau authentication |
| `AuthUserDetails` chứa mọi field domain | Có thực sự là adapter tối thiểu không? | Chỉ giữ auth fields/ID cần thiết |
| Mutable username được dùng làm định danh bất biến | Có hỗ trợ đổi tên, case-insensitive, tenant không? | Dùng ID nội bộ ổn định và scope chính xác |

Một entity nhỏ, bất biến, không có dữ liệu nhạy cảm không thiết yếu và được kiểm thử có thể hoạt động như principal trong hệ thống hạn chế. Nhưng khi có JPA graph, PII, session hoặc nhiều cơ chế auth, **phép chiếu riêng là mặc định an toàn, dễ bảo trì hơn**.

## 13. Checklist trước khi đưa principal vào production

1. **Nguồn đáng tin:** userId, username, tenantId và authorities đều xuất phát từ AuthenticationManager/IdP đã được xác thực hoặc dữ liệu server đã kiểm chứng.
2. **Không giữ secret dài hạn:** raw password, password hash không còn cần, refresh token, API keys và dữ liệu nội bộ không nằm trong session principal.
3. **Không mang graph JPA:** principal không có `EntityManager`, Hibernate proxy, lazy collections hoặc entity references lớn.
4. **Có định danh ổn định:** phân biệt userId, username hiển thị và tenant scope; không dựa trên email hay displayName để lookup quyền.
5. **Có chính sách authorities:** quyền được lấy từ nguồn đáng tin, xác định khi nào refresh/revoke sau khi role hoặc account status thay đổi.
6. **Không dùng principal làm response:** API có DTO riêng, allowlist trường; log không ghi secrets hoặc toàn object.
7. **Transaction đúng ranh giới:** `UserDetailsService` map trong thời gian dữ liệu còn truy cập được; use case khác tải domain data mới trong service.
8. **Session/caching an toàn:** xác minh serialization round-trip, expiration, credential erasure, session replication và cache invalidation.
9. **Kiểm tra tenant và object-level authorization:** có userId chưa đồng nghĩa được phép xem mọi dữ liệu của user hoặc tenant khác.
10. **Có test xác thực và rò dữ liệu:** login thành công/thất bại, principal type, credentials erased, không có PII, thay đổi quyền, restart session nếu có.
11. **Không tạo trusted token từ input:** chỉ provider/thành phần đáng tin sau khi xác minh credential mới được tạo authenticated result.
12. **Có kế hoạch chuyển đổi:** nếu hệ thống đang dùng entity principal, thay dần controller/`@AuthenticationPrincipal` và session serialization, không đổi type giữa chừng mà quên session cũ.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `UserDetailsService` vẫn phải cung cấp password hash cho `DaoAuthenticationProvider` nếu principal nên tối thiểu?  
**Trả lời:** Vì provider cần so khớp raw password với hash đã lưu **trong bước xác thực**. Đó là dữ liệu tạm phục vụ auth; sau đó nên xóa credential khỏi kết quả, tránh giữ hash trong principal dài hạn.

**Câu 2.** Chuyển `AccountEntity` thành `UserDetails` nhỏ có tự động ngăn mọi lỗ hổng không?  
**Trả lời:** Không. Vẫn phải xác thực credential, cấp authorities đáng tin, bảo vệ session, authorize tài nguyên và quản lý trạng thái khi quyền thay đổi.

**Câu 3.** Vì sao không nên dùng `@JsonIgnore` như cách duy nhất để bảo vệ entity principal?  
**Trả lời:** Vì JSON annotation không bảo vệ mọi đường log, session serialization, cache, object graph và các serializer khác.

**Câu 4.** Một controller muốn địa chỉ giao hàng của người dùng hiện tại. Có nên thêm toàn bộ address list vào principal?  
**Trả lời:** Thường không. Controller nhận userId, service truy vấn địa chỉ được phép xem và trả response DTO đúng field.

**Câu 5.** Entity có `@OneToMany(fetch = LAZY)`. Nếu giữ entity trong session rồi load collection ở request sau, có thể xảy ra gì?  
**Trả lời:** Entity có thể detached khiến `LazyInitializationException`, hoặc phát sinh query bất ngờ/N+1 nếu persistence context vẫn mở.

**Câu 6.** `ProviderManager` xóa password khỏi `UserDetails` dùng chung với cache. Hậu quả?  
**Trả lời:** Lần xác thực tiếp theo có thể không tìm được password hash đúng. Cần tách object cache và object result hoặc thiết kế cơ chế credential erasure/caching hợp lý.

**Câu 7.** Client gửi JSON có `userId=42, roles=["ADMIN"]`. Server được tạo `UsernamePasswordAuthenticationToken.authenticated(...)` ngay không?  
**Trả lời:** Không. Danh tính và authorities phải được xác minh từ provider và nguồn tin cậy. Factory authenticated không tự xác minh input.

**Câu 8.** Một session vẫn chứa role cũ sau khi DB thu hồi quyền; việc principal nhỏ có làm role tự cập nhật không?  
**Trả lời:** Không. Cần session/token lifecycle, refresh/revocation hoặc kiểm tra quyền mới ở điểm nhạy cảm.

## 15. Tài liệu chuẩn

- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContext`, `ProviderManager` và credential erasure.
- [Spring Security 6.5 – UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html): hợp đồng trả `UserDetails` cho username/password provider.
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): đường đi của `UserDetails` vào principal sau xác thực.
- [Spring Security 6.5 – UserDetails](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html): vòng đời dữ liệu identity và quản lý credentials.
- [Spring Security 6.5 – User API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html): `UserDetails` có sẵn, `CredentialsContainer` và xóa password.
- [Spring Security 6.5 – MVC Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html): `@AuthenticationPrincipal`.
- [Spring Security 6.5 – Authentication API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html): principal, credentials, authorities và `getName()`.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): giới hạn dữ liệu session và kiểm soát vòng đời.

**Ghi nhớ:** Dùng entity để **lưu và xử lý nghiệp vụ**; dùng `UserDetails`/provider để **xác minh**; dùng principal tối thiểu để **định danh trong security context**; dùng service để **lấy dữ liệu nghiệp vụ mới và phân quyền đúng tài nguyên**. Đừng cho một entity đầy đủ gánh cả bốn trách nhiệm chỉ vì việc cast principal sang entity đang tiện.
