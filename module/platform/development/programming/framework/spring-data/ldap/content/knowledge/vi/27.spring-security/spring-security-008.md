# Xử lý tài khoản khóa, vô hiệu hóa hoặc hết hạn theo máy chủ

Trong ứng dụng **Spring Security kết hợp Spring Data LDAP**, một lần đăng nhập thất bại không phải lúc nào cũng có nghĩa người dùng nhập sai mật khẩu. Directory server có thể từ chối bind vì tài khoản đã **bị khóa**, **bị vô hiệu hóa**, **hết hạn**, hoặc mật khẩu đã **hết hạn/bắt buộc thay đổi**. Đây là các trạng thái khác nhau, có cách khôi phục và ý nghĩa bảo mật khác nhau.

Ứng dụng Java cần tôn trọng chính sách của LDAP server, phân loại lỗi đủ chính xác cho vận hành nhưng không tiết lộ trạng thái tài khoản cho người không được phép. Bài thuộc chương **Spring Security**, tập trung vào chủ đề **“Xử lý tài khoản khóa, vô hiệu hóa hoặc hết hạn theo máy chủ”**. Nội dung đặt trong phạm vi **SPRING_DATA_LDAP**: tìm DN, bind, đọc thuộc tính theo schema, dùng Spring Security LDAP, quản lý ACL/TLS, xử lý lỗi và kiểm thử trên directory.

> **Nguyên tắc:** LDAP server là nơi thực thi chính sách tài khoản và xác minh bind. Ứng dụng có thể đọc trạng thái để hỗ trợ quản trị hoặc policy bổ sung, nhưng không được coi một thuộc tính cache hay một lần search cũ là bằng chứng cuối cùng thay cho kết quả bind hiện tại.

## 1. Phân biệt các trạng thái tài khoản

| Trạng thái | Ý nghĩa | Hệ quả thường gặp |
|---|---|---|
| **Locked** – bị khóa | Server tạm thời hoặc theo policy chặn đăng nhập, thường sau nhiều lần xác thực thất bại | Bind bị từ chối cho đến khi hết thời gian khóa hoặc được mở khóa |
| **Disabled** – bị vô hiệu hóa | Tài khoản bị quản trị viên hoặc workflow provisioning tắt | Không được phép đăng nhập, kể cả mật khẩu đúng |
| **Account expired** – tài khoản hết hạn | Thời điểm hiệu lực của tài khoản đã kết thúc | Bind bị từ chối hoặc yêu cầu xử lý theo policy server |
| **Password expired** – mật khẩu hết hạn | Mật khẩu không còn hợp lệ theo tuổi thọ/policy | Có thể bị từ chối hoặc được yêu cầu đổi mật khẩu |
| **Password change required** | Server yêu cầu đổi mật khẩu ở lần đăng nhập tiếp theo | Không nên coi bind thành công một phần là phiên đăng nhập đầy đủ |
| **Password incorrect** | Credential không khớp | Từ chối xác thực; có thể tăng bộ đếm lockout |
| **Account not found** | Không tìm được entry trong phạm vi search | Không có principal để bind theo quy trình search-then-bind |

Cần tách **account state** khỏi **authentication result** và **authorization**:

- Account có thể đang active nhưng mật khẩu sai.
- Mật khẩu đúng nhưng account bị disabled hoặc expired.
- Bind có thể thành công nhưng user vẫn thiếu role để dùng một chức năng.
- Account có thể bị khóa sau một lần search status nhưng trước lần bind kế tiếp.

Một API không nên suy diễn “không bind được” thành một trạng thái duy nhất nếu directory có chính sách phong phú hơn.

## 2. Luồng xác thực và điểm kiểm tra trạng thái

```text
HTTP login request
(username, password)
       │
       ▼
Validate input
- username hợp lệ
- password không null/rỗng
       │
       ▼
Search user DN
(service account, fixed base + safe filter)
       │
       ▼
Exactly one DN?
       │
       ▼
Optional status pre-check
(server-specific attributes, if authorized)
       │
       ▼
Bind as the user
(user DN + supplied password, TLS)
       │
       ├── bind accepted
       │       │
       │       ▼
       │   account/application policy
       │   authorities, MFA, session
       │
       └── bind rejected
               │
               ▼
       classify trusted server result
       (locked / disabled / expired / bad credentials)
```

Các nguyên tắc:

1. **Search** dùng service account có quyền đọc tối thiểu để tìm DN trong base/scope cố định.
2. Nếu có kiểm tra trạng thái trước bind, nó chỉ là **pre-check** dựa trên dữ liệu có thể thay đổi; không thay thế bind.
3. **Bind** phải dùng DN của người dùng và mật khẩu người đó nhập, qua LDAPS/StartTLS đã xác minh chứng chỉ.
4. LDAP server thực thi lockout, disable, account expiry và password policy theo cấu hình của nó.
5. Sau bind thành công, ứng dụng vẫn kiểm tra role, MFA, session và policy nghiệp vụ.
6. Nếu bind bị từ chối, chỉ phân loại chi tiết khi có tín hiệu đáng tin từ server/version; nếu không, xử lý như authentication failure chung.

**Không đọc `userPassword` rồi tự so sánh hash** để bỏ qua bind. Không dùng trạng thái lấy từ replica/cache cũ để ghi đè quyết định của server ở thời điểm xác thực.

## 3. Không có một thuộc tính LDAP chuẩn chung cho mọi trạng thái

LDAP định nghĩa giao thức, schema và cách search; các thuộc tính khóa/vô hiệu hóa/hết hạn phụ thuộc **directory product, schema và policy được bật**.

| Môi trường | Thông tin có thể gặp | Lưu ý |
|---|---|---|
| Active Directory | `userAccountControl`, `accountExpires`, `lockoutTime`, `msDS-User-Account-Control-Computed` | Một số flag/attribute đặc thù AD |
| OpenLDAP với ppolicy overlay | `pwdAccountLockedTime`, `pwdReset`, `pwdChangedTime`, `pwdPolicySubentry` | Phụ thuộc overlay, policy và quyền đọc |
| Schema kiểu shadow | `shadowExpire`, `shadowInactive`, `shadowLastChange` | Phụ thuộc schema/module được triển khai |
| Directory thương mại khác | Attribute và diagnostic riêng của sản phẩm | Đọc tài liệu/version và test thực tế |

**Không giả định các attribute trên tồn tại ở mọi server.** Một entry không trả `pwdAccountLockedTime` không chứng minh account active nếu server không dùng ppolicy hoặc service account không có quyền đọc operational attribute.

## 4. Active Directory: disabled, locked và expired

Active Directory có một số attribute đặc thù hữu ích khi quản trị tài khoản.

### 4.1 Disabled qua userAccountControl

`userAccountControl` là bit field. Một số flag thường được quan tâm:

| Flag | Giá trị hex | Ý nghĩa |
|---|---:|---|
| `ACCOUNTDISABLE` | `0x0002` | Account bị vô hiệu hóa |
| `DONT_EXPIRE_PASSWORD` | `0x10000` | Password không hết hạn theo thiết lập này |

Ví dụ kiểm tra bit disabled:

```java
public final class ActiveDirectoryFlags {

    private static final int ACCOUNTDISABLE = 0x0002;

    private ActiveDirectoryFlags() {}

    public static boolean isDisabled(int userAccountControl) {
        return (userAccountControl & ACCOUNTDISABLE) != 0;
    }
}
```

Đây chỉ là cách giải mã bit. Nó không tự xác thực mật khẩu và cũng không nên là lý do duy nhất để bỏ qua bind. **Không nhầm `ACCOUNTDISABLE` với lockout hoặc account expiry.**

### 4.2 Locked qua trạng thái lockout của AD

AD có attribute `lockoutTime` và attribute tính toán `msDS-User-Account-Control-Computed`. Flag `LOCKOUT` (bit `0x0010`) trong attribute tính toán có thể phản ánh trạng thái khóa hiện tại.

`lockoutTime` là timestamp gắn với sự kiện khóa; chỉ thấy giá trị khác 0 không phải lúc nào cũng đủ để tự quyết định account còn đang bị khóa, vì thời lượng khóa và chính sách tự mở khóa ảnh hưởng trạng thái hiệu lực. Khi cần đánh giá trạng thái hiện tại, ưu tiên **kết quả bind/policy server** hoặc attribute tính toán được server hỗ trợ và đã kiểm chứng.

### 4.3 Account expiry qua accountExpires

`accountExpires` dùng giá trị Windows FILETIME (số khoảng 100 nanosecond từ mốc 1601 UTC) trong AD. Các giá trị đặc biệt thường biểu thị **không đặt ngày hết hạn** là 0 hoặc giá trị lớn nhất 64-bit. Không diễn giải nó như Unix epoch seconds.

Ví dụ chuyển FILETIME sang Java `Instant`:

```java
import java.time.Instant;
import java.util.Optional;

public final class AdAccountExpiry {

    private static final long WINDOWS_EPOCH_OFFSET_SECONDS =
            11_644_473_600L;
    private static final long TICKS_PER_SECOND = 10_000_000L;

    private AdAccountExpiry() {}

    public static Optional<Instant> parseAccountExpires(String raw) {
        if (raw == null || raw.isBlank()) {
            return Optional.empty();
        }

        long fileTime = Long.parseLong(raw);
        if (fileTime == 0 || fileTime == Long.MAX_VALUE) {
            return Optional.empty();
        }

        long seconds = fileTime / TICKS_PER_SECOND
                - WINDOWS_EPOCH_OFFSET_SECONDS;
        long remainingTicks = fileTime % TICKS_PER_SECOND;

        return Optional.of(Instant.ofEpochSecond(
                seconds, remainingTicks * 100L));
    }
}
```

Khi đánh giá hết hạn, so sánh với clock UTC đáng tin và xử lý giá trị malformed như lỗi dữ liệu. Mẫu code chỉ chuyển đổi timestamp; nó không bao quát clock skew, quyền đọc attribute hoặc mọi biến thể schema.

**Không có flag `ACCOUNT_EXPIRED` chung trong `userAccountControl` để thay cho việc đọc `accountExpires`.** Account expiry và password expiry là hai chính sách khác nhau.

## 5. OpenLDAP và Password Policy overlay

OpenLDAP có thể dùng **ppolicy overlay** để áp dụng chính sách mật khẩu và lockout. Khi overlay được bật, một số attribute thường gặp:

| Attribute | Mục đích |
|---|---|
| `pwdAccountLockedTime` | Thông tin khóa account theo password policy |
| `pwdReset` | Trạng thái yêu cầu đổi password |
| `pwdChangedTime` | Thời điểm thay đổi password |
| `pwdPolicySubentry` | Policy entry áp dụng cho user |
| `pwdFailureTime` | Lịch sử thời điểm xác thực thất bại, theo cấu hình |
| `pwdGraceUseTime` | Thông tin sử dụng grace login, nếu policy hỗ trợ |

Các thuộc tính này có thể là **operational attributes** hoặc chịu quyền đọc riêng. Client có thể phải yêu cầu rõ tên attribute trong search; service account có thể không được phép đọc chúng. Giá trị và semantics phải được đối chiếu với đúng OpenLDAP release/overlay configuration.

Một số triển khai ppolicy dùng marker đặc biệt cho trạng thái locked; **không hard-code marker hoặc cách tính expiry cho mọi LDAP server**. Cũng không tự tính password expiry chỉ từ `pwdChangedTime` nếu chưa biết policy hiệu lực, `pwdMaxAge`, grace period và quy tắc của server.

### Password Policy response control

Một số client/server có hỗ trợ **Password Policy response control** để cung cấp cảnh báo hoặc lỗi liên quan password policy, chẳng hạn password sắp hết hạn, đã hết hạn, account bị khóa hoặc yêu cầu đổi mật khẩu. Cần xác minh server có bật control, client/provider có expose response, operation nào trả control và ứng dụng có xử lý warning/error hay không.

Nếu provider không expose control, không được giả vờ rằng chỉ đọc một attribute bất kỳ đã thay thế được response policy.

## 6. Server diagnostic và mã lỗi không đồng nhất

LDAP result code `invalidCredentials` (49) thường được dùng khi credential không được chấp nhận. Một số server cung cấp thêm **diagnostic message** để phân biệt nguyên nhân. Nội dung và cấu trúc diagnostic là đặc thù sản phẩm, có thể thay đổi theo version/configuration.

### Ví dụ diagnostic thường gặp trên Active Directory

AD có thể trả result code 49 kèm chuỗi diagnostic chứa `data` code. Những giá trị thường được ghi nhận:

| AD diagnostic data | Ý nghĩa thường gặp |
|---|---|
| `52e` | Invalid credentials |
| `533` | Account disabled |
| `532` | Password expired |
| `701` | Account expired |
| `775` | Account locked |
| `773` | User must reset password |

Đây là **mã chẩn đoán đặc thù AD**, không phải LDAP result code portable. Không giả định OpenLDAP hoặc directory khác trả cùng chuỗi.

Một số lưu ý:

- Không gửi diagnostic nguyên văn về trình duyệt/mobile client.
- Không ghi password, bind DN nhạy cảm hoặc raw filter vào log để giải thích lỗi.
- Không phân tích chuỗi lỗi bằng một regex chung rồi áp dụng cho mọi server.
- Nếu cần phân loại, viết **adapter theo product/version**, test với response thực tế và có fallback `UNKNOWN`.
- Proxy, load balancer hoặc provider có thể biến đổi/ẩn diagnostic message.
- Không tự động thử lại password khi gặp lockout/expired; retry có thể làm tăng lockout hoặc vi phạm policy.

## 7. Tích hợp Spring Security LDAP

Spring Security LDAP thường dùng các thành phần:

- `BindAuthenticator`: tìm user DN theo search configuration hoặc DN pattern, sau đó bind bằng credential user.
- `LdapAuthenticationProvider`: phối hợp LDAP authenticator và authorities populator.
- `DefaultLdapAuthoritiesPopulator`: lấy authority từ group theo cấu hình.
- `UserDetailsContextMapper`: ánh xạ context/attributes thành `UserDetails` theo nhu cầu.
- `AuthenticationException` và các lớp con: biểu diễn thất bại xác thực.

Ví dụ cấu hình search-based bind:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;

@Configuration
public class LdapSecurityConfiguration {

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {

        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(contextSource);

        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter(
                "(&(objectClass=inetOrgPerson)(uid={0}))");

        return factory.createAuthenticationManager();
    }
}
```

Cấu hình trên minh họa cơ chế tìm user và bind. Nó **không tự chứng minh** rằng mọi server-specific trạng thái disabled/locked/expired đều được ánh xạ thành exception chi tiết. Hành vi exception phụ thuộc Spring Security/Spring LDAP version và cách directory trả lỗi.

### UserDetails flags không tự đọc mọi LDAP policy

`UserDetails` có các trạng thái như:

- `isAccountNonExpired()`
- `isAccountNonLocked()`
- `isCredentialsNonExpired()`
- `isEnabled()`

Đây là **mô hình trạng thái ở tầng Spring Security**. LDAP provider không thể tự suy ra mọi flag nếu mapper không đọc attribute tương ứng và server không cung cấp dữ liệu đó. Khi cần custom mapping, phải triển khai `UserDetailsContextMapper` hoặc một thành phần account policy riêng, rồi **kiểm thử cách provider sử dụng kết quả**. Không gán mặc định tất cả flag là true rồi nghĩ server đã bảo vệ đầy đủ.

### Phân biệt exception của Spring Security

| Exception | Ý nghĩa |
|---|---|
| `LockedException` | Account bị khóa |
| `DisabledException` | Account bị vô hiệu hóa |
| `AccountExpiredException` | Account hết hạn |
| `CredentialsExpiredException` | Credential/mật khẩu hết hạn |
| `BadCredentialsException` | Credential không hợp lệ hoặc lỗi xác thực chung |

Có thể dùng chúng trong adapter/service của ứng dụng **sau khi đã xác định trạng thái bằng nguồn tin cậy**. Không tự đổi mọi `AuthenticationException` thành `LockedException`; cũng không giả định `LdapAuthenticationProvider` luôn phân biệt chính xác mọi diagnostic code của AD/OpenLDAP.

## 8. Thiết kế lớp phân loại trạng thái độc lập

Để tránh gắn logic vendor-specific vào controller, tạo mô hình nội bộ:

```java
public record DirectoryAccountState(
        boolean locked,
        boolean disabled,
        boolean accountExpired,
        boolean passwordExpired,
        boolean passwordChangeRequired
) {}
```

Một policy checker có thể ánh xạ trạng thái đã được xác minh thành exception Spring Security:

```java
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;

public final class AccountStatusPolicy {

    public void check(DirectoryAccountState state) {
        // Thứ tự ưu tiên là policy của ứng dụng.
        if (state.disabled()) {
            throw new DisabledException("Account unavailable");
        }
        if (state.locked()) {
            throw new LockedException("Account unavailable");
        }
        if (state.accountExpired()) {
            throw new AccountExpiredException("Account unavailable");
        }
        if (state.passwordExpired() || state.passwordChangeRequired()) {
            throw new CredentialsExpiredException("Credentials unavailable");
        }
    }
}
```

Mẫu này cho thấy **cách biểu diễn trạng thái**, không phải một LDAP attribute mapper hoàn chỉnh. Nguồn dữ liệu của `DirectoryAccountState` cần được triển khai theo server cụ thể và chỉ dựa trên attribute/response đáng tin.

### Nơi gọi policy checker

1. **Pre-check trước bind:** đọc trạng thái account để từ chối sớm hoặc phục vụ UX/quản trị. Dữ liệu có thể stale; không thay thế bind.
2. **Sau khi bind hoặc khi xử lý kết quả bind:** áp dụng policy bổ sung mà ứng dụng cần. Nếu bind bị server từ chối, chỉ phân loại được locked/disabled/expired khi adapter hiểu response/control của server.

Trong cả hai trường hợp, **server vẫn là authority cuối cùng cho bind**. Nếu account bị khóa giữa pre-check và bind, bind phải thất bại. Đây là race condition bình thường cần xử lý an toàn.

## 9. Không biến pre-check thành nguồn quyết định duy nhất

Một anti-pattern là:

```text
Search account attributes
       │
       ├── thấy enabled=true
       │
       ▼
Tạo session ngay
```

Luồng này bỏ qua xác minh mật khẩu và có race condition. Một biến thể khác đọc trạng thái active từ replica, rồi bỏ qua bind nếu pre-check nói user active. Cả hai đều sai.

Quy trình phù hợp:

- Tìm DN đúng duy nhất trong scope đã duyệt.
- Nếu đọc được status attribute, dùng nó để **pre-check** hoặc cung cấp diagnostics cho quản trị viên.
- Xác thực credential bằng user bind trên TLS; server thực thi policy hiện tại.
- Chỉ tạo session sau khi bind và policy ứng dụng thành công.
- Nếu server báo trạng thái chi tiết, adapter phân loại theo đúng product/version; nếu không, trả failure chung.
- Không dùng cached `enabled=true` để vượt qua bind failure hoặc lockout.

**Search thành công không có nghĩa account active. Bind thành công cũng không tự đồng nghĩa người dùng được phép truy cập mọi chức năng.**

## 10. Đọc thuộc tính trạng thái qua LdapTemplate

Nếu directory cho phép service account đọc trạng thái, có thể truy vấn rõ các attribute cần thiết. Ví dụ sau minh họa **đọc metadata** từ user entry; nó không xác thực password:

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class AccountStateReader {

    public record RawAccountState(
            String userAccountControl,
            String accountExpires,
            String lockoutTime,
            String computedControl,
            String pwdAccountLockedTime,
            String pwdReset
    ) {}

    private final LdapTemplate ldapTemplate;

    public AccountStateReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public RawAccountState readByUid(String uid) {
        LdapQuery request = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .countLimit(2)
                .timeLimit(2000)
                .attributes(
                        "userAccountControl",
                        "accountExpires",
                        "lockoutTime",
                        "msDS-User-Account-Control-Computed",
                        "pwdAccountLockedTime",
                        "pwdReset")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        AttributesMapper<RawAccountState> mapper = attrs ->
                new RawAccountState(
                        value(attrs, "userAccountControl"),
                        value(attrs, "accountExpires"),
                        value(attrs, "lockoutTime"),
                        value(attrs, "msDS-User-Account-Control-Computed"),
                        value(attrs, "pwdAccountLockedTime"),
                        value(attrs, "pwdReset"));

        List<RawAccountState> results =
                ldapTemplate.search(request, mapper);
        if (results.size() != 1) {
            throw new IllegalStateException(
                    "Account status is not uniquely resolved");
        }
        return results.get(0);
    }

    private static String value(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null || attribute.size() == 0
                ? null
                : String.valueOf(attribute.get());
    }
}
```

**Đây là ví dụ minh họa cách đọc raw metadata, không phải query dùng nguyên xi cho mọi server.** Trong thực tế:

- Với AD, object class và login attribute có thể là `user`/`sAMAccountName` thay vì `inetOrgPerson`/`uid`.
- Với OpenLDAP, các attribute AD sẽ không tồn tại; chỉ yêu cầu attribute ppolicy nếu schema/overlay hỗ trợ.
- Operational attribute có thể cần yêu cầu tường minh và quyền đọc riêng.
- `countLimit(2)` giúp phát hiện có nhiều kết quả nếu nhận đủ; vẫn phải xử lý size-limit/referral/partial result, không coi response bị cắt là duy nhất.
- Nếu một attribute không được trả, không tự coi nó là false/active; cần phân biệt **absent**, **not readable**, **not supported** và **malformed**.

## 11. Chuyển trạng thái AD sang mô hình ứng dụng

Một adapter AD có thể đọc `userAccountControl` và `msDS-User-Account-Control-Computed` rồi tạo `DirectoryAccountState`. Ví dụ phần giải mã flag:

```java
public final class AdAccountStateMapper {

    private static final int ACCOUNTDISABLE = 0x0002;
    private static final int LOCKOUT = 0x0010;

    private AdAccountStateMapper() {}

    public static boolean disabled(int userAccountControl) {
        return (userAccountControl & ACCOUNTDISABLE) != 0;
    }

    public static boolean locked(int computedControl) {
        return (computedControl & LOCKOUT) != 0;
    }
}
```

Không lấy `LOCKOUT` từ một bit tự đoán trong `userAccountControl` rồi dùng làm trạng thái hiện tại; dùng attribute/contract phù hợp của AD. Account expiry cần chuyển `accountExpires` theo FILETIME như phần 4; password expiry là policy khác và cần dữ liệu/policy tương ứng.

Đối với OpenLDAP ppolicy, tạo adapter riêng đọc `pwdAccountLockedTime`, `pwdReset` và thông tin policy phù hợp. **Không dùng chung `AdAccountStateMapper` cho OpenLDAP.**

## 12. Chuyển trạng thái OpenLDAP ppolicy sang mô hình ứng dụng

Với OpenLDAP, adapter phải biết ppolicy overlay đang bật và policy nào áp dụng. Một bản ghi status có thể gồm:

```text
pwdPolicySubentry
pwdAccountLockedTime
pwdReset
pwdChangedTime
pwdFailureTime
```

Các bước:

1. Xác minh server có ppolicy overlay và policy entry áp dụng cho user.
2. Xác minh service account được phép đọc operational attributes cần thiết.
3. Đọc giá trị theo đúng syntax và semantics của version.
4. Phân biệt lock do ppolicy với account disabled theo schema/ACL riêng.
5. Xác định password expiry/grace/password reset theo policy thực, không chỉ lấy `pwdChangedTime`.
6. Kiểm thử response control hoặc bind result khi policy từ chối đăng nhập.

Nếu không có ppolicy overlay, ứng dụng không thể suy ra mọi trạng thái lock/password expiry bằng một tên attribute chung. Hãy dùng cơ chế quản trị của server hoặc bổ sung policy được thiết kế rõ ràng.

## 13. Xử lý exception: chi tiết nội bộ, thông báo công khai chung

Đối với người đăng nhập, thông báo như:

```text
Tên đăng nhập hoặc thông tin xác thực không hợp lệ.
```

thường an toàn hơn việc tiết lộ “tài khoản đang bị khóa”, “người dùng đã bị vô hiệu hóa” hoặc “mật khẩu đã hết hạn”. Các thông tin chi tiết chỉ nên xuất hiện trong audit/log bảo vệ hoặc màn hình quản trị có phân quyền. Đặc biệt, không để API trở thành công cụ **enumeration** xác định user tồn tại/disabled/locked.

Một mô hình phân loại nội bộ:

```java
public enum DirectoryAuthenticationFailure {
    BAD_CREDENTIALS,
    ACCOUNT_LOCKED,
    ACCOUNT_DISABLED,
    ACCOUNT_EXPIRED,
    PASSWORD_EXPIRED,
    PASSWORD_CHANGE_REQUIRED,
    USER_NOT_FOUND,
    AMBIGUOUS_USER,
    DIRECTORY_UNAVAILABLE,
    TLS_FAILURE,
    UNKNOWN
}
```

Adapter server-specific có thể ánh xạ diagnostic đã xác minh sang enum. Tầng HTTP chỉ cần một response chung; audit event nội bộ lưu category, source server, correlation ID và thời điểm theo chính sách log.

**Không ghi raw diagnostic chứa DN hoặc thông tin nhạy cảm vào log phổ thông.** Không lưu password trong exception message, tracing tag hay metric label.

## 14. Recovery: ai được mở khóa hoặc kích hoạt lại?

Đăng nhập không nên tự ý sửa trạng thái tài khoản. Quy trình recovery thuộc quản trị danh tính:

| Trạng thái | Hành động thường gặp | Ai thực hiện |
|---|---|---|
| Locked | Chờ hết lockout duration hoặc unlock theo quy trình | Directory admin / workflow đã duyệt |
| Disabled | Xác minh lý do, sau đó enable nếu đủ điều kiện | Account owner/admin |
| Account expired | Gia hạn hoặc tạo lại theo vòng đời nhân sự | HR/IAM/Directory admin |
| Password expired | Quy trình đổi password an toàn | Người dùng qua kênh được duyệt hoặc helpdesk |
| Must change password | Hoàn tất bước đổi password trước khi cấp phiên đầy đủ | Người dùng qua luồng password-change |
| Directory unavailable | Khôi phục dịch vụ/replica/TLS | Hạ tầng directory |

Không viết controller công khai kiểu `/unlock?uid=...`. Nếu có chức năng admin unlock/enable, cần role quản trị riêng, kiểm tra quyền ở server, audit người thực hiện/lý do/thời gian/kết quả, xác nhận workflow và bảo vệ endpoint. Không tự đặt lại password hoặc xóa lockout chỉ vì user thử đăng nhập nhiều lần.

**Tài khoản bị khóa do brute force là tín hiệu bảo mật**, không phải lỗi UX để ứng dụng tự mở khóa.

## 15. Lockout policy, retry và rate limiting

Khi mật khẩu sai liên tục, server có thể tăng bộ đếm failure và khóa account. Một ứng dụng retry tự động có thể làm tình trạng xấu hơn.

- Không retry bind với cùng password sai.
- Không fan-out thử credential trên nhiều domain/DC không có policy rõ.
- Rate limit theo IP, username đã chuẩn hóa và các yếu tố rủi ro phù hợp.
- Tránh thông báo cho kẻ tấn công biết lockout threshold hoặc trạng thái tài khoản.
- Dùng backoff cho lỗi hạ tầng; phân biệt lỗi network với invalid credentials.
- Không retry mù sau timeout bind vì kết quả server có thể đã được thực hiện nhưng response bị mất.
- Không tạo song song nhiều bind cho một username khi chưa đo tác động lockout.

Một lỗi bind do directory outage không nên bị tính như password sai ở tầng ứng dụng. Ngược lại, credential sai không nên được retry liên tục như lỗi mạng.

## 16. Replica, cache và race condition của trạng thái account

Trong topology nhiều DC/replica, trạng thái account có thể chưa đồng bộ tức thời. Ví dụ:

1. Admin disable user trên DC A.
2. Ứng dụng đọc status từ replica B trước khi replication hoàn tất.
3. B vẫn trả `enabled` theo dữ liệu cũ.
4. Bind tới DC A bị từ chối.

Điều này cho thấy **status pre-check có thể stale**. Những nguyên tắc:

- Dùng endpoint phù hợp cho authentication và để bind kiểm tra credential/policy.
- Không dùng cache trạng thái active để bỏ qua bind.
- Nếu cần read status, ghi rõ source DC, timestamp và độ mới.
- Không đồng nhất `lockoutTime` trên replica với trạng thái hiện hành nếu chưa hiểu semantics AD.
- Khi failover sang DC khác, kiểm thử consistency và behavior lockout.
- Cache kết quả “active” phải có TTL ngắn và không được dùng làm quyền cho hành động nhạy cảm.
- Khi không xác định được trạng thái vì timeout/ACL/partial result, trả `UNKNOWN` hoặc directory unavailable; không coi như active.

**Race giữa search và bind là điều có thể xảy ra.** Bind cuối cùng phải chịu trách nhiệm chấp nhận hoặc từ chối credential tại thời điểm nó được thực hiện.

## 17. Kiểm thử trạng thái tài khoản với directory phù hợp

Mock `LdapTemplate` chỉ giúp kiểm tra luồng code; nó không chứng minh AD/OpenLDAP áp dụng lockout/expiry đúng như cấu hình. Cần lab với **policy thật** và user test có thể reset trạng thái.

| Ca kiểm thử | Cách tạo trong lab | Kỳ vọng |
|---|---|---|
| Active account | User được enable, không hết hạn | Password đúng bind thành công |
| Wrong password | Dùng credential sai | Từ chối, tăng failure counter theo policy |
| Locked account | Đạt lockout threshold hoặc admin lock | Bind bị từ chối, phân loại theo server adapter nếu có |
| Disabled account | Tắt account bằng công cụ admin | Bind bị từ chối; status reader nhận đúng flag nếu được phép |
| Account expired | Đặt expiry trong quá khứ | Server từ chối theo policy |
| Password expired | Đặt password age vượt policy | Bind/policy control phản ánh đúng behavior |
| Must change password | Bật trạng thái reset/change required | Không cấp session đầy đủ trước khi hoàn tất |
| Grace login | Cấu hình ppolicy grace nếu có | Không nhầm grace warning với password bình thường |
| Attribute ACL denied | Service account không được đọc status | Trạng thái `UNKNOWN`, không suy ra active |
| Missing ppolicy | Tắt overlay trong lab OpenLDAP | Adapter không giả định ppolicy attributes tồn tại |
| AD diagnostic mapping | Thu response của AD lab theo version | Chỉ map mã đã xác minh |
| Replica lag | Disable/lock trên DC A, đọc DC B | Pre-check stale không vượt bind |
| Bind race | Khóa user giữa search và bind | Bind thất bại, không tạo session |
| TLS failure | Chứng chỉ sai CA/hostname | Fail closed, không gửi password cleartext |
| Referral/partial | Server trả kết quả từng phần | Không coi thiếu attribute là false/active |
| No user / duplicate | Không có hoặc có hai DN khớp | Không bind nhầm principal |
| Log hygiene | Chạy login success/failure | Không ghi password hoặc raw sensitive diagnostic |
| Enumeration | Thử user không tồn tại, locked, disabled | Thông báo công khai trung tính |

### Test unit cho bit ACCOUNTDISABLE

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ActiveDirectoryFlagsTest {

    @Test
    void detectsDisabledFlagWithoutTreatingOtherBitsAsDisabled() {
        assertTrue(ActiveDirectoryFlags.isDisabled(0x0002));
        assertTrue(ActiveDirectoryFlags.isDisabled(0x0202));
        assertFalse(ActiveDirectoryFlags.isDisabled(0x0200));
    }
}
```

Test unit này xác minh bitmask. Nó **không** chứng minh account bị lock/expired hoặc server sẽ từ chối bind. Cần integration test riêng cho từng trạng thái.

## 18. Chẩn đoán sự cố theo lớp

| Triệu chứng | Khả năng | Hướng điều tra |
|---|---|---|
| Tất cả user đều không đăng nhập được | Bind account/search base/TLS/server outage | Kiểm tra search service, TLS, DNS, availability |
| Chỉ một user không đăng nhập | Password sai hoặc trạng thái account | Dùng diagnostic nội bộ và công cụ quản trị được phép |
| Admin mở khóa nhưng ứng dụng vẫn báo locked | Replica/cache hoặc DC khác | Xác minh endpoint bind, replication, TTL |
| Attribute status không xuất hiện | Schema/overlay không có hoặc ACL | Kiểm tra server capability và quyền đọc |
| AD trả `data 775` | Có thể là lockout diagnostic | Chỉ adapter AD đã kiểm chứng mới phân loại |
| Spring Security chỉ trả BadCredentials | Provider gom lỗi hoặc diagnostic không được expose | Xem cause chain/version, custom classifier nếu cần |
| Password expired nhưng UI báo sai mật khẩu | Policy control/diagnostic chưa được map | Xây luồng password change theo server |
| User disabled nhưng bind vẫn thành công | Server/policy/bind route khác kỳ vọng | Xác minh DC, account flags và test policy |
| Lỗi TLS bị báo password sai | Exception bị gom quá rộng | Tách transport/TLS khỏi credential failure |
| Nhiều account bị lock sau deploy | Retry hoặc service dùng nhầm credential | Dừng retry, kiểm tra secret/rotation và rate |

Đối với sự cố diện rộng, không yêu cầu mọi user đổi mật khẩu trước khi xác định lỗi hạ tầng. Một certificate hết hạn hoặc bind service password bị rotate sai có thể khiến tất cả login fail.

## 19. Bài tập tình huống

Một ứng dụng Spring Boot dùng `LdapBindAuthenticationManagerFactory` để tìm user theo `uid` trong `ou=people`. LDAP service có hai môi trường:

- **AD:** có `userAccountControl`, `accountExpires`, `lockoutTime` và `msDS-User-Account-Control-Computed`.
- **OpenLDAP:** dùng ppolicy overlay, có `pwdAccountLockedTime` và `pwdReset` khi policy áp dụng.

Một số người dùng báo “sai mật khẩu”, nhưng quản trị viên xác nhận có user bị khóa hoặc password hết hạn.

Hãy trả lời:

1. Vì sao không thể dùng một attribute chung để nhận biết locked/disabled/expired trên cả AD và OpenLDAP?
2. Phân biệt account locked, disabled, account expired và password expired.
3. Bit `ACCOUNTDISABLE` của AD có giá trị nào? Vì sao không dùng nó để kết luận lockout?
4. Vì sao `lockoutTime` khác với một trạng thái lockout hiện hành đã được server tính toán?
5. `accountExpires` dùng epoch nào và hai giá trị đặc biệt thường gặp để biểu thị never-expire là gì?
6. OpenLDAP ppolicy có thể cung cấp những attribute/control nào? Vì sao phải xác minh overlay và ACL?
7. Vì sao bind phải được thực hiện sau search và là authority cuối cùng?
8. `UserDetails.isAccountNonLocked()` có tự đọc mọi attribute AD/OpenLDAP không?
9. Khi nào cần adapter để map diagnostic AD `data 775`/`533`/`532`/`701`/`773`?
10. Vì sao không được trả cho client biết tài khoản tồn tại nhưng đang bị khóa?
11. Một replica trả active nhưng DC xác thực trả locked; hệ thống nên tin nguồn nào?
12. Cần test những gì để chứng minh password expiry, lockout, disable, TLS và log hygiene?

**Định hướng:** status model phải có adapter riêng theo server. AD dùng bit/attribute AD; OpenLDAP dùng ppolicy khi overlay có hiệu lực. Status pre-check chỉ hỗ trợ diagnostics/policy ứng dụng; bind thực tế trên TLS vẫn là bước xác minh credential. Lỗi công khai cần trung tính; nội bộ có thể lưu category đã được xác minh.

## 20. Checklist triển khai và tổng kết

Trước khi phát hành chức năng xác thực LDAP:

- [ ] Phân biệt **locked**, **disabled**, **account expired**, **password expired** và **must change password**.
- [ ] Xác nhận product/version, schema, overlay và account policy của directory.
- [ ] Tìm DN trong base/scope cố định, filter an toàn và yêu cầu đúng một entry.
- [ ] Dùng bind bằng DN người dùng và password user nhập trên LDAPS/StartTLS đã xác minh.
- [ ] Không đọc `userPassword` để tự so sánh và không chấp nhận password rỗng.
- [ ] Xem status attribute như pre-check/diagnostic; không dùng cache stale để bỏ qua bind.
- [ ] Có adapter riêng cho AD/OpenLDAP hoặc server khác; không suy semantics từ tên attribute.
- [ ] Nếu phân tích diagnostic code, giới hạn theo product/version và test response thực.
- [ ] Không giả định Spring Security tự map mọi trạng thái server sang exception cụ thể.
- [ ] Dùng `LockedException`, `DisabledException`, `AccountExpiredException`, `CredentialsExpiredException` chỉ khi có trạng thái đã xác minh.
- [ ] Thông báo công khai trung tính; log nội bộ có kiểm soát, không ghi password/raw sensitive diagnostic.
- [ ] Có quy trình unlock/enable/reset được phân quyền và audit.
- [ ] Có rate limit, không retry bind credential sai, không để retry gây lockout.
- [ ] Kiểm thử lockout, disable, expiry, password change, ACL, replica lag, TLS và concurrent bind.
- [ ] Khi không đọc được status hoặc search/bind không hoàn tất, xử lý `UNKNOWN`/directory unavailable, không mặc định active.

### Tài liệu kỹ thuật tham khảo

- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html).
- [Spring Security — Core Authentication and Account Status Exceptions](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html).
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/).
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513).
- [Microsoft Learn — User-Account-Control Attribute](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/useraccountcontrol-manipulate-account-properties).
- [Microsoft Learn — Account Lockout Policy](https://learn.microsoft.com/en-us/windows/security/threat-protection/security-policy-settings/account-lockout-policy).
- [OpenLDAP Administrator's Guide](https://www.openldap.org/doc/admin26/overlays.html).

**Kết luận:** xử lý account bị khóa, vô hiệu hóa hoặc hết hạn trong **Spring Security LDAP** cần dựa vào policy và tín hiệu do directory server cung cấp. AD và OpenLDAP có mô hình thuộc tính khác nhau; Spring Security cũng không tự suy ra mọi trạng thái nếu thiếu mapper/adapter phù hợp. Hãy để bind trên kết nối TLS xác minh credential, dùng status reader để hỗ trợ policy/diagnostics, phân loại lỗi theo đúng server/version, bảo vệ thông báo công khai và kiểm thử trạng thái thật trong lab.
