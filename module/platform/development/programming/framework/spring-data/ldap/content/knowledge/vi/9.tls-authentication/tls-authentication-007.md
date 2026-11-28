# Tìm DN người dùng rồi bind để kiểm tra thông tin đăng nhập

Khi một ứng dụng **Spring Data LDAP** nhận tên đăng nhập và mật khẩu, tên mà người dùng gõ vào biểu mẫu thường **không phải Distinguished Name (DN)** dùng để xác thực trên LDAP server. Ví dụ, người dùng nhập `u1001`, trong khi entry thực tế nằm tại `uid=u1001,ou=people,dc=example,dc=org`. Ứng dụng cần **tìm đúng DN** theo một LDAP filter được kiểm soát, sau đó **thực hiện bind bằng DN đó và mật khẩu người dùng cung cấp**. Cách làm này thường được gọi là **search-then-bind** hay *bind authentication với user search*.

Bài thuộc chương **TLS và xác thực** này giải thích quy trình đó trong hệ sinh thái **SPRING_DATA_LDAP**: mô hình DN/RDN, `objectClass` và schema; `LdapTemplate.authenticate(...)`; trường hợp cần tự tìm DN rồi gọi `ContextSource.getContext(...)`; tích hợp **Spring Security LDAP**; chống LDAP injection và anonymous/unauthenticated bind; cấu hình LDAPS/StartTLS, phân quyền, quản lý kết nối, xử lý lỗi và kiểm thử với directory.

> **Nguyên tắc quan trọng nhất:** bước **search** dùng một danh tính dịch vụ có quyền tìm DN, nhưng bước kiểm tra mật khẩu phải **bind bằng danh tính của chính người dùng được tìm thấy**. Tìm thấy entry **không đồng nghĩa** mật khẩu đã đúng; service account bind thành công **không đồng nghĩa** người dùng đăng nhập thành công.

## 1. Tình huống: tên đăng nhập không nhất thiết là DN

Một cây thư mục có thể tổ chức như sau:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=u1001     → An Nguyen
│   ├── uid=u1002     → Binh Tran
│   └── uid=u1003     → Chi Le
├── ou=groups
│   ├── cn=developers
│   └── cn=reviewers
└── ou=service-accounts
    └── cn=svc-login-search
```

Một LDAP entry:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
mail: an.nguyen@example.org
```

Người dùng gửi yêu cầu đăng nhập chứa `username=u1001` và một mật khẩu bí mật. Ứng dụng có thể tìm entry bằng điều kiện tương đương:

```ldap
(&(objectClass=inetOrgPerson)(uid=u1001))
```

Nếu kết quả tìm kiếm đúng **một** entry và DN của nó là `uid=u1001,ou=people,dc=example,dc=org`, ứng dụng dùng **DN vừa tìm được** cùng mật khẩu để bind. LDAP server mới là bên xác minh mật khẩu và chính sách của tài khoản.

### Phân biệt các định danh

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Tên đăng nhập người dùng nhập | `u1001` | Giá trị tìm kiếm theo quy tắc của ứng dụng |
| LDAP attribute | `uid: u1001` | Thuộc tính dùng trong filter; không tự xác định OU |
| RDN | `uid=u1001` | Thành phần tên tương đối với parent |
| DN đầy đủ | `uid=u1001,ou=people,dc=example,dc=org` | Danh tính thường dùng để SIMPLE bind |
| Context base | `dc=example,dc=org` | Gốc tương đối của nhiều API Spring LDAP |
| Search base | `ou=people` | Phạm vi tìm người dùng bên dưới context base |
| Service account | `cn=svc-login-search,ou=service-accounts,...` | Danh tính dùng để **tìm DN**, không đại diện cho người dùng đăng nhập |

DN có thể thay đổi khi user được đổi RDN hoặc chuyển OU. Vì vậy không nên lưu công thức `"uid=" + username + ",ou=people,..."` như một giả định bất biến nếu directory thực tế cho phép move/rename.

## 2. Hai bước độc lập: tìm DN rồi bind

Luồng thành công:

```text
HTTP login request                         LDAP directory
(username, password)                              |
       |                                           |
       |-- [1] Search bằng svc-login-search ------>|
       |    base=ou=people                         |
       |    filter=(&(objectClass=...)(uid=...))    |
       |<-- [2] Đúng một entry + DN ---------------|
       |                                           |
       |-- [3] Mở context mới, SIMPLE bind -------->|
       |    principal = DN của người dùng           |
       |    credential = mật khẩu vừa nhập          |
       |<-- [4] Bind thành công --------------------|
       |                                           |
       |-- [5] Tạo authentication của ứng dụng      |
       |        nếu các chính sách khác cũng đạt    |
       |        (account, MFA, authorization...)     |
```

Dòng thời gian đúng phải thỏa:

1. **Đầu vào được kiểm tra:** username có định dạng phù hợp, mật khẩu **không rỗng**, không nhận raw LDAP filter/base DN từ client.
2. **Tìm bằng một filter an toàn:** service account tìm trong OU/naming context được duyệt.
3. **Không có hơn một kết quả:** không thử từng DN ngẫu nhiên rồi chấp nhận người đầu tiên có password khớp.
4. **Kênh LDAP đã được bảo vệ:** dùng LDAPS hoặc StartTLS với xác minh chứng chỉ **trước** khi gửi password.
5. **Bind bằng chính user DN:** LDAP server áp dụng cơ chế xác thực và chính sách tài khoản.
6. **Chỉ sau bind thành công** mới thiết lập trạng thái đã đăng nhập tại ứng dụng.
7. **Quyền sử dụng ứng dụng được xác định riêng:** có thể còn phải kiểm tra tài khoản hoạt động, nhóm, role, MFA và chính sách phiên.

Nếu bước search không thấy entry, trả nhiều DN, bị từ chối ACL hoặc lỗi TLS, không được tự chuyển sang bind bằng tài khoản dịch vụ hay bỏ qua bước xác minh mật khẩu.

## 3. Bind khác search, khác compare password và khác authorization

Trong LDAP, **SIMPLE bind** gửi một principal và credential cho server để yêu cầu tạo một kết nối/context xác thực với danh tính đó. Điều này khác các thao tác:

| Thao tác | Câu hỏi được trả lời | Có chứng minh mật khẩu người dùng đúng không? |
|---|---|---|
| LDAP search | Entry nào khớp filter và nằm trong scope? | **Không** |
| LDAP lookup | DN được chỉ định có trả một entry không? | **Không** |
| LDAP compare | Giá trị attribute có khớp phép compare trên server không? | **Không**, trừ khi một thiết kế xác thực riêng có contract rõ |
| SIMPLE bind bằng user DN | Server có chấp nhận principal + password này không? | **Có**, theo chính sách xác thực của server |
| Search group sau bind | User thuộc nhóm nào trong phạm vi được phép? | Không; đây là **authorization** |
| Cấp session/JWT | Ứng dụng duy trì trạng thái đã đăng nhập | Chỉ nên làm **sau** khi xác thực hợp lệ |

**Không đọc thuộc tính `userPassword` rồi tự so sánh chuỗi hoặc hash**: nhiều directory không cho đọc thuộc tính này, dùng cơ chế lưu trữ/chính sách khác nhau hoặc kiểm soát password theo cách server-specific. Spring Security LDAP cũng ưu tiên **bind authentication** vì không cần đọc mật khẩu từ LDAP entry.

Một bind thành công chỉ xác nhận directory chấp nhận credential cho principal đó. Nó **không tự cấp role quản trị ứng dụng**, không xác minh MFA và không nói rằng user được phép thực hiện mọi LDAP write operation.

## 4. Search base, scope và tên thuộc tính phải được xác định rõ

Giả sử `LdapContextSource` có:

```text
LDAP URL:       ldaps://ldap.example.org:636
Context base:   dc=example,dc=org
User search:    ou=people
Search scope:   SUBTREE
Username attr:  uid
Object class:   inetOrgPerson
```

Khi ấy search base trong `LdapQueryBuilder` là `ou=people` **tương đối với context base**. DN đầy đủ mà server trả về là `uid=u1001,ou=people,dc=example,dc=org`. Không tự gắn `dc=example,dc=org` hai lần.

**ONELEVEL hay SUBTREE?**

- `ONELEVEL`: chỉ tìm các user nằm ngay dưới `ou=people`.
- `SUBTREE`: tìm cả các OU con, phù hợp nếu nhân viên được chia nhiều nhánh.
- Chọn scope theo **cấu trúc đã được duyệt**, không tự nâng lên toàn domain khi không tìm thấy user.

Với SUBTREE, hai entry ở hai OU con có thể có cùng `uid`. **Tính duy nhất của login là yêu cầu bảo mật** và phải được kiểm tra ở phạm vi xác thực, không suy từ một thuộc tính có vẻ là ID.

### Active Directory không giống mọi LDAP server khác

Trên Active Directory, người dùng thường có RDN `CN=...`; tên đăng nhập có thể dựa vào `sAMAccountName` hoặc `userPrincipalName`, và định dạng có thể phụ thuộc domain/forest. Không dùng filter `(uid={username})` nếu schema AD không cấp/tổ chức login theo `uid`.

Khi tìm xuyên domain, phải xác định **domain controller, naming context, tính duy nhất theo domain và cơ chế referral**. Một login ngắn có thể trùng giữa các domain. Không coi search tại Global Catalog là phép xác thực đầy đủ nếu chưa kiểm chứng quyền, thuộc tính và domain bind trong hệ thống đó.

## 5. Cấu hình Spring Boot với tài khoản tìm kiếm có quyền tối thiểu

Ví dụ cấu hình `application.yml` cho ứng dụng sử dụng Spring LDAP:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-login-search,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_SEARCH_BIND_PASSWORD}
```

Các thuộc tính `spring.ldap.*` là cấu hình thường gặp của Spring Boot; cơ chế auto-configuration thực tế cần được đối chiếu theo phiên bản. Nếu tự khai báo `LdapContextSource`, cần bảo đảm `LdapTemplate` thực sự dùng đúng context source.

**Tài khoản `svc-login-search` chỉ dùng để tìm DN**, nên cấp:

- Search/read các thuộc tính tối thiểu cần để xác định đúng user, ví dụ `uid` và DN trong `ou=people`.
- Quyền phù hợp với filter `objectClass=inetOrgPerson` trên nhánh được duyệt.
- Không cấp quyền modify/delete, không cho đọc `userPassword` hoặc các bí mật khác.
- Không dùng tài khoản quản trị directory chỉ để tìm người đăng nhập.

Bảo vệ secret bằng môi trường quản lý secrets phù hợp; không commit mật khẩu thật, không xuất nó ra log, stack trace tùy tiện hoặc endpoint chẩn đoán.

### Yêu cầu TLS

- Với `ldaps://`, TLS bắt đầu ngay khi kết nối. Client phải xác minh **chuỗi CA, hostname/SAN và thời hạn chứng chỉ**.
- Với `ldap://` + **StartTLS**, phải cấu hình `DirContextAuthenticationStrategy` phù hợp để nâng cấp và xác minh TLS **trước khi thực hiện SIMPLE bind**.
- Không chỉ đổi URL `ldaps://` thành `ldap://` rồi coi đó là StartTLS.
- Nếu TLS handshake bị từ chối, **fail closed**; không retry SIMPLE bind qua kết nối không mã hóa.

**HTTPS của API không thay thế TLS giữa ứng dụng và LDAP server.** Có thể có kênh HTTPS an toàn từ trình duyệt tới server ứng dụng nhưng kênh LDAP phía sau vẫn bị lộ nếu chưa bảo vệ.

## 6. Cách gọn nhất: `LdapTemplate.authenticate(LdapQuery, String)`

Spring LDAP có API giúp thực hiện đúng mô hình **tìm DN → bind bằng mật khẩu user**:

```java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class LdapLoginVerifier {

    private final LdapTemplate ldapTemplate;

    public LdapLoginVerifier(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Thành công: method kết thúc bình thường.
    // Thất bại: exception để tầng xác thực xử lý.
    public void verifyCredentials(
            String username, String password) {

        if (username == null || username.isBlank()
                || username.length() > 128
                || password == null || password.isEmpty()) {
            throw new IllegalArgumentException(
                    "Missing or invalid credentials");
        }

        LdapQuery userQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .timeLimit(3000)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(username);

        ldapTemplate.authenticate(userQuery, password);
    }
}
```

**Điểm rất dễ sai về chữ ký method:**

- Trong các bản Spring LDAP hiện hành, `ldapTemplate.authenticate(LdapQuery, String)` có kiểu trả về **`void`** và **ném exception khi gặp lỗi**, không phải một hàm trả `boolean`.
- Các overload **cũ** dạng `authenticate(String base, String filter, String password)` hoặc `authenticate(Name base, String filter, String password)` trả `boolean`; trong API hiện hành chúng được đánh dấu **deprecated** và được thay bằng dạng `LdapQuery`.
- Không viết `boolean success = ldapTemplate.authenticate(userQuery, password);` nếu dùng overload `LdapQuery`: đó là sai kiểu.
- Phải để tầng xác thực phân biệt **không tìm thấy user**, **tìm nhiều DN**, **bind không được chấp nhận** và **lỗi hạ tầng**, thay vì catch mọi exception rồi trả `true` hoặc tự fallback.

Theo contract `LdapTemplate`, method sẽ search entry rồi dùng DN đã tìm cùng password để thực hiện bind qua `ContextSource`. **Filter của bước search phải dẫn tới một user duy nhất**; thư viện có xử lý trường hợp kết quả không đúng một entry, nhưng ứng dụng vẫn phải thiết kế scope và uniqueness đúng ngay từ đầu.

### Vì sao dùng `LdapQueryBuilder`?

`query().where("uid").is(username)` coi username là **giá trị của điều kiện equality**, không phải một chuỗi LDAP filter mà client được tự cung cấp. Khi username chứa dấu `*` hoặc ngoặc, filter builder sẽ escape giá trị phù hợp; nó không được diễn giải thành thêm toán tử.

Cần kết hợp **validation tên đăng nhập** với builder; không dựa vào escaping để cấp quyền tìm kiếm ngoài OU được phép.

## 7. Cách tường minh: search lấy DN rồi `ContextSource.getContext`

Đôi khi ứng dụng cần **tách từng bước** để kiểm tra điều kiện uniqueness, kiểm toán, sử dụng mapping DN riêng hoặc xử lý policy trước khi bind. Khi đó có thể:

1. Dùng `LdapTemplate.search(...)` để tìm DN bằng service account.
2. Xác nhận danh sách chứa **đúng một** DN.
3. Dùng `ContextSource.getContext(fullUserDn, password)` để tạo **context mới với danh tính user**.
4. **Đóng context** ngay sau khi kiểm tra; không giữ kết nối user trong pool service-account.

Ví dụ Java minh họa:

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.ldap.support.LdapUtils;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class ExplicitSearchThenBind {

    private final LdapTemplate searchTemplate;
    private final ContextSource contextSource;

    public ExplicitSearchThenBind(
            LdapTemplate searchTemplate,
            ContextSource contextSource) {
        this.searchTemplate = searchTemplate;
        this.contextSource = contextSource;
    }

    public void verify(String login, String password)
            throws NamingException {

        if (login == null || login.isBlank()
                || login.length() > 128
                || password == null || password.isEmpty()) {
            throw new IllegalArgumentException(
                    "Missing or invalid credentials");
        }

        LdapQuery query = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .timeLimit(3000)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(login);

        ContextMapper<String> fullDnMapper = context -> {
            DirContextOperations entry =
                    (DirContextOperations) context;
            return entry.getNameInNamespace();
        };

        List<String> matchedDns =
                searchTemplate.search(query, fullDnMapper);

        if (matchedDns.size() != 1) {
            // Tầng bảo mật phải phân loại 0 và >1 kết quả
            // nhưng không tiết lộ trạng thái user tới bên ngoài.
            throw new IllegalStateException(
                    "User DN lookup is not uniquely resolved");
        }

        DirContext userContext = null;
        try {
            userContext = contextSource.getContext(
                    matchedDns.get(0), password);
            // Trả về bình thường = server đã chấp nhận user bind.
        } finally {
            LdapUtils.closeContext(userContext);
        }
    }
}
```

**Các điểm phải hiểu đúng:**

- `DirContextOperations.getDn()` trong Spring LDAP thường trả DN **tương đối** với base path. `getNameInNamespace()` cung cấp tên theo namespace để có thể dùng làm **full user DN** cho bind, theo contract của context/adapter trong phiên bản hiện hành.
- `ContextSource.getContext(principal, credentials)` tạo context bằng credential người dùng đưa vào; nó **không được đồng nhất** với `getReadOnlyContext()` của service account.
- Theo API Spring LDAP, `getContext(principal, credentials)` **không dùng native Java LDAP pooling** ngay cả nếu context source có cấu hình native pool, để những thay đổi mật khẩu được phản ánh nhanh hơn.
- Nếu bind lỗi, `getContext(...)` có thể ném `NamingException`; logic bảo mật phải phân loại và báo lỗi phù hợp.
- `LdapUtils.closeContext(...)` đóng JNDI context trong `finally`, kể cả khi công việc sau bind xảy ra lỗi. Không trả user context vào pool kết nối của tài khoản dịch vụ.
- Ví dụ này **không quản lý HTTP security session**, MFA hoặc phân quyền ứng dụng. Chúng là trách nhiệm của lớp xác thực bên ngoài.

**Tránh sao chép code thủ công nếu không cần.** `LdapTemplate.authenticate(...)` hoặc cơ chế LDAP bind của Spring Security đã triển khai nhiều chi tiết; chỉ tự viết hai bước khi có một yêu cầu rõ và đã có kiểm thử lỗi/uniqueness, lifecycle và policy.

## 8. Vì sao “tìm đúng một DN” là một yêu cầu an ninh?

Giả sử directory có:

```text
uid=alex,ou=employees,ou=people,dc=example,dc=org
uid=alex,ou=contractors,ou=people,dc=example,dc=org
```

Search SUBTREE theo `(uid=alex)` sẽ trả **hai DN**. Nếu chương trình lấy phần tử đầu tiên và bind:

- LDAP không bảo đảm thứ tự search result nếu không dùng sorting phù hợp.
- Có thể xác thực nhầm principal.
- Điều kiện về tenant/OU có thể bị vượt qua.
- Có thể dẫn tới lỗ hổng nếu username được coi là định danh duy nhất trong hệ thống.

**Không giải quyết bằng cách đặt `countLimit(1)` rồi giả định đã có duy nhất một user.** Giới hạn 1 có thể che khuất các entry trùng. Khi cần chứng minh uniqueness, phải kiểm tra đúng số lượng trong scope **và xử lý trường hợp size/time limit, referral hoặc partial result**; một kết quả bị cắt không phải bằng chứng chỉ có một entry.

Các chiến lược:

| Tình huống | Hướng xử lý |
|---|---|
| `uid` duy nhất trong OU theo ràng buộc được thực thi | Search đúng OU đó và giám sát vi phạm |
| `uid` trùng giữa hai tenant | Chọn tenant từ thông tin đã xác thực/chính sách tin cậy rồi search trong base phù hợp |
| Login dạng email | Chỉ dùng khi hệ thống có quy tắc uniqueness và matching rule đúng |
| AD login bằng `sAMAccountName` | Gắn với domain/scope và kiểm chứng trường tương ứng |
| Không có DN nào | Xác thực thất bại, không dựng DN đoán để “thử vận may” |
| Nhiều DN khớp | Từ chối, cảnh báo sai lệch dữ liệu/cấu hình; không chọn ngẫu nhiên |
| Search bị timeout/ACL/referral | Trả lỗi hệ thống thích hợp; **không coi danh sách rỗng là kết quả đầy đủ** |

DN không phải username. Nếu user bị move sang OU khác, DN thay đổi nhưng username có thể giữ nguyên; **search-then-bind** giúp tránh công thức DN cứng, miễn scope đã được thiết kế đúng.

## 9. LDAP injection ở bước tìm DN

Một đầu vào cố tình gây nhầm cú pháp:

```text
u1001*)(|(uid=*))
```

Nếu nối filter thủ công:

```java
// Không an toàn: username có thể phá cú pháp LDAP filter.
String filter = "(&(objectClass=inetOrgPerson)(uid="
        + username + "))";
```

Có thể khiến server diễn giải thêm nhóm điều kiện hoặc nhận filter sai cú pháp.

Dùng filter builder:

```java
import org.springframework.ldap.filter.EqualsFilter;

String safe =
        new EqualsFilter("uid", username).encode();
```

Cách này giữ username là **giá trị dữ liệu**, escape ký tự đặc biệt theo filter LDAP. Với `LdapQueryBuilder`, `where("uid").is(username)` cũng đảm nhiệm mục tiêu này.

| Dữ liệu | Quy tắc |
|---|---|
| Username chứa `*` | Dấu sao phải là ký tự literal trong equality, không thành wildcard |
| Username chứa `(`/`)` | Escape để không tạo nhóm filter mới |
| Username chứa `\` | Escape backslash theo cú pháp filter |
| Username chứa ký tự Unicode | Kiểm thử quy tắc charset/matching rule của server |
| Username quá dài | Từ chối theo giới hạn nghiệp vụ |
| Client gửi `attributeName` hoặc `baseDn` | Không nhận làm chỉ thị để mở rộng tìm kiếm |

**DN escaping khác LDAP filter escaping:** khi phải dựng DN theo các RDN đã duyệt, dùng `LdapNameBuilder`; khi tìm một thuộc tính, dùng `EqualsFilter` hoặc `LdapQueryBuilder`. Không ghép raw DN do client cung cấp rồi đem bind.

**Không cho client thay đổi search base hoặc field được tìm**. Một payload chứa `ou=service-accounts` dưới dạng DN phải không thể khiến API tra cứu tài khoản dịch vụ.

## 10. Mật khẩu rỗng: nguy cơ anonymous/unauthenticated bind

Đây là một trong những bẫy quan trọng nhất của LDAP bind authentication.

Một số LDAP server cho phép **unauthenticated bind** với **DN không rỗng và mật khẩu rỗng**. Kết nối có thể được chấp nhận nhưng **không xác thực danh tính người dùng như ứng dụng mong muốn**. Nếu ứng dụng nhầm “bind không báo lỗi” thành “đăng nhập đúng”, một request chỉ có username có thể được chấp nhận sai.

Vì vậy:

- **Từ chối mật khẩu `null` hoặc chuỗi rỗng** trước mọi LDAP bind.
- Không trim mật khẩu; khoảng trắng có thể là một phần của mật khẩu thực. Nếu policy cấm mật khẩu chỉ gồm khoảng trắng, xác định ở lớp chính sách riêng, không tự sửa password người dùng nhập.
- Không tự thay mật khẩu rỗng bằng secret của service account.
- Không thử anonymous bind để “kiểm tra có user” rồi coi là xác thực.
- Kiểm thử trực tiếp một LDAP server có policy unauthenticated bind để chứng minh ứng dụng vẫn từ chối.
- Dùng Spring Security LDAP bind authentication khi phù hợp; provider Spring Security có cơ chế từ chối empty password theo contract.

**Tìm thấy user mà password rỗng phải thất bại**, kể cả khi directory cho phép search công khai.

## 11. Phân loại lỗi mà không tiết lộ trạng thái tài khoản

Các lỗi khác nhau có hành vi vận hành khác nhau:

| Giai đoạn | Lỗi ví dụ | Ý nghĩa | Hướng xử lý |
|---|---|---|---|
| Validation | Username/password thiếu | Request không hợp lệ | Từ chối trước khi kết nối LDAP |
| Search | Không có entry | Login không được tìm thấy trong scope | Không bind và trả thông báo chung |
| Search | Có hơn một DN | Phạm vi/uniqueness không hợp lệ | Từ chối, ghi cảnh báo bảo mật |
| Search | Permission denied | Account lookup không có ACL | Lỗi hệ thống/quyền, không phải password sai |
| Search | Referral/timeout/size-limit | Không chứng minh đã tìm đủ | Fail closed, không chọn kết quả bất kỳ |
| Bind | Invalid credentials | Server không chấp nhận password | Từ chối đăng nhập, không thử lại nhiều lần tự động |
| Bind | User khóa/hết hạn/bắt đổi mật khẩu | Chính sách directory riêng | Thông báo bên ngoài theo chính sách chống enumeration |
| TLS | Chứng chỉ sai hoặc handshake lỗi | Kênh không an toàn/không kết nối được | Không fallback cleartext |
| Sau bind | Không đủ role/chính sách MFA | Bind đúng nhưng chưa đủ quyền dùng app | Từ chối hoặc yêu cầu bước bổ sung |

**Thông báo cho người dùng cuối** thường nên trung tính, ví dụ: “Tên đăng nhập hoặc mật khẩu không hợp lệ”. Đừng phân biệt công khai “tài khoản chưa tồn tại” với “mật khẩu sai” theo cách giúp kẻ tấn công liệt kê tài khoản.

**Đối với người vận hành**, vẫn cần phân biệt mã lỗi transport/TLS, lookup, ACL, bind và directory availability để điều tra. Cần che dữ liệu cá nhân, credential và nội dung filter nhạy cảm khỏi log.

### Thận trọng với cách catch exception

`LdapTemplate.authenticate(LdapQuery, String)` ném exception theo contract khi thất bại. Nếu API công khai cần kết quả boolean, tầng adapter có thể ánh xạ **chỉ các loại lỗi credential đã xác minh** thành `false`. **Không catch tất cả `Exception` rồi trả `false`**, vì sẽ che lỗi LDAP server hỏng hoặc TLS không hợp lệ thành “mật khẩu sai”, gây khó khăn vận hành và cơ chế phòng thủ.

Tương tự, **không catch exception rồi trả `true` chỉ vì search thấy entry**. Bind phải được server chấp nhận, không phải kết quả tìm DN.

## 12. Spring Security LDAP: lựa chọn phù hợp cho đăng nhập HTTP

Nếu mục tiêu là xác thực người dùng cho một ứng dụng web, **Spring Security LDAP** thường là lớp đúng để thực hiện login flow, thay vì viết controller gọi thẳng `LdapTemplate.authenticate` rồi tự tạo token/session.

Spring Security cung cấp cơ chế **Bind Authentication**. Ví dụ cấu hình Java theo API Spring Security phù hợp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;

@Configuration
public class LdapSecurityConfiguration {

    @Bean
    AuthenticationManager authenticationManager(
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

`{0}` là placeholder mà Spring Security điền bằng username qua cơ chế filter của nó; **không** tự thay `{0}` bằng cách nối string từ HTTP request. Cấu hình phải được đối chiếu với **Spring Security version thực tế**. Bên cạnh bean `AuthenticationManager`, ứng dụng cần cấu hình `SecurityFilterChain` và chính sách login/session phù hợp.

### Search filter hay DN pattern?

| Cách tìm principal | Khi nào hợp lý | Lưu ý |
|---|---|---|
| **User search** qua `userSearchBase`/`userSearchFilter` | Người dùng nằm nhiều OU, DN không thể dự đoán | Cần lookup account, scope và uniqueness |
| **User DN pattern** | DN tuân theo một cấu trúc cố định, được server đảm bảo | Có thể đơn giản hơn, nhưng dễ sai khi move/rename |
| Username/UPN đặc thù AD | AD có contract đăng nhập riêng | Phải kiểm tra domain, login attribute và policy |
| Custom authenticator | Có yêu cầu đặc biệt đã phê duyệt | Chi phí bảo trì, cần kiểm thử kỹ TLS/ACL/lifecycle |

**Spring Security và Spring Data LDAP không phải cùng một tầng:** Spring Security cung cấp **authentication + authorization integration**, còn Spring Data LDAP cung cấp repository/ODM để truy cập và ánh xạ entry. Chúng có thể dùng chung LDAP infrastructure nhưng không nên trộn responsibility.

## 13. Bind thành công chưa có nghĩa đã được cấp quyền ứng dụng

Sau khi xác minh password bằng user bind, ứng dụng có thể cần quyết định user có được xem tài liệu, sửa thuộc tính hoặc truy cập endpoint quản trị không. Đây là **authorization**, không phải một phần tự động của SIMPLE bind.

Ví dụ: user `u1001` bind thành công nhưng chỉ thuộc `developers`; thao tác quản trị nhóm chỉ được phép cho người có role/nhóm đã duyệt. Các nguồn quyền có thể gồm:

- LDAP group membership (`member`/`uniqueMember` hoặc attribute server-specific).
- Backlink `memberOf` trên server có hỗ trợ, với giới hạn direct/nested/primary group.
- Role mapping từ nhóm LDAP sang quyền ứng dụng.
- Chính sách nội bộ, tài khoản bị vô hiệu hóa, MFA, tenant và phân quyền đối tượng.

Không để phần mapping quyền:

- Dựa vào một DN group hard-code sai naming context.
- Tự tìm nhóm ngoài scope được phê duyệt.
- Tự gán quyền quản trị khi search group bị timeout hoặc ACL che.
- Coi kết quả group thiếu do size-limit như đầy đủ.
- Tin cache membership quá cũ khi dùng để cấp quyền nhạy cảm.

**LDAP bind và LDAP search membership là hai nghiệp vụ riêng**, có thể dùng tài khoản/context khác và có độ trễ riêng. Khi quyền đòi hỏi thông tin rất mới, phải chọn cơ chế đánh giá/cache phù hợp.

## 14. Bảo mật toàn tuyến từ trình duyệt đến directory

Luồng đăng nhập có nhiều boundary:

```text
Browser / client
    │ HTTPS + CSRF/session/rate limiting
    ▼
Spring Security / login endpoint
    │ Validation + correlation ID + secret hygiene
    ▼
Search LDAP với service account
    │ LDAPS / StartTLS đã xác minh chứng chỉ
    ▼
DN user đã xác định duy nhất
    │ Bind với username DN + password trên TLS
    ▼
LDAP server account policy
    │
    ▼
Authorization + MFA/session theo app policy
```

Các yêu cầu tối thiểu:

1. **HTTPS cho API** và **TLS cho LDAP**; xác minh CA và hostname ở cả hai kênh.
2. **Service account tra cứu quyền hẹp**, không dùng admin.
3. **Không log password** ở HTTP request, LDAP debugging, tracing, audit hoặc error handler.
4. **Không lưu trữ mật khẩu của người dùng LDAP** trong database ứng dụng hoặc job queue chỉ để rebind về sau.
5. **Không dùng native JNDI pooling tùy tiện cho kết nối xác thực từng user**; `ContextSource.getContext(principal, credentials)` được thiết kế không tái sử dụng native pool cho bind có credential riêng.
6. **Rate limit và chống brute force** trên login; phân biệt sai mật khẩu với lỗi hạ tầng để tránh retry vô hạn.
7. **Bảo vệ chống username enumeration** bằng thông báo lỗi công khai nhất quán, không để thời gian phản hồi khác biệt quá rõ khi có thể tránh.
8. **Không dùng trust-all TLS**, hostname verifier bỏ qua lỗi hoặc fallback cleartext.
9. **Đóng context sau bind**; không vô tình trả user context cho request của người dùng khác.
10. **Quản lý session/JWT/MFA phù hợp chính sách**, không coi kết quả `ldapTemplate.authenticate` là session.

Ở quy trình sử dụng StartTLS, cần bảo đảm bước search và bước bind đều dùng **kết nối đã được nâng cấp, kiểm tra chứng chỉ**; không chỉ bảo vệ service search rồi gửi password của user qua một kết nối khác chưa có TLS.

## 15. Vì sao không dùng `LdapRepository.findByUid` để kiểm tra mật khẩu?

Có thể có entity ODM:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
        base = "ou=people",
        objectClasses = {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        })
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }
}
```

Repository:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);
}
```

`repository.findByUid("u1001")` chỉ thực hiện **search/ánh xạ ODM**. Nó **không** xác minh password của người dùng được tìm thấy. Tương tự:

- `repository.findById(Name dn)` xác định entry theo DN.
- `ldapTemplate.findByDn(...)` đọc entry và chuyển thành entity.
- `ldapTemplate.lookup(...)` đọc attribute tại DN.
- `ldapTemplate.authenticate(...)` mới là API phục vụ search-then-bind theo credential.

**Không lấy password từ entity hoặc ánh xạ `userPassword` vào DTO**, rồi tự đối chiếu với chuỗi user gửi. Directory server mới nên là nơi xác thực mật khẩu và áp chính sách tài khoản.

## 16. Hiệu năng và an toàn vận hành của search-then-bind

Một login theo search-then-bind thường có tối thiểu hai pha:

1. **Search để xác định DN**, dùng service account.
2. **Bind user**, thường cần một context/kết nối xác thực riêng.

Vì vậy một request đăng nhập không nhất thiết chỉ tạo **một LDAP operation**. Có thể phát sinh thêm search để đọc thuộc tính hoặc group/role, kiểm tra status, referral hoặc retry.

Theo dõi:

| Metric | Điều cần quan sát |
|---|---|
| Search DN p50/p95/p99 | Truy vấn có được index trên `uid`/`sAMAccountName` không? |
| Bind p50/p95/p99 | Kết nối TLS, bind latency, server account policy |
| Số LDAP operations/login | Search + bind + group lookup + retry |
| LDAP pool borrow wait | Truy vấn search service có bị nghẽn không? |
| Invalid credentials rate | Dấu hiệu brute force, nhưng không log password |
| Duplicate/no-match rate | Chất lượng username uniqueness/scope |
| TLS/ACL errors | Lỗi hạ tầng và quyền, không phải sai password |
| Login throttle/lockout | Ảnh hưởng chính sách tài khoản của server |
| Failover | Bind lại đúng endpoint đã bảo vệ, không bỏ qua TLS |

### Có nên cache DN?

Có thể cache ánh xạ `(source, tenant, username) → DN` để giảm search, nhưng cần quản lý:

- User có thể **rename/move** nên DN cache trở nên stale.
- Một UID có thể trùng ở phạm vi khác; cache key phải có **scope/tenant**.
- Một cache stale không được khiến hệ thống chuyển sang principal khác hoặc bỏ qua uniqueness.
- Cần TTL, invalidation khi provisioning/rename và fallback lookup có kiểm soát nếu DN không còn hợp lệ.
- **Không cache password** hoặc chia sẻ user-bound context giữa các request.

Không cache kết quả “mật khẩu đúng” để bỏ qua bind cho lần đăng nhập khác. Các hệ thống muốn tránh bind lặp thường quản lý **session/token sau xác thực**, có chính sách expiration/revocation riêng; đó không phải là cache mật khẩu LDAP.

## 17. Kiểm chứng độc lập bằng công cụ LDAP

Trước khi kết luận một đoạn Java sai, có thể thử **trong môi trường test được cấp phép** bằng công cụ LDAP độc lập.

**Bước 1 – Search DN với tài khoản lookup:**

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D 'cn=svc-login-search,ou=service-accounts,dc=example,dc=org' -W \
  -b 'ou=people,dc=example,dc=org' -s sub \
  '(&(objectClass=inetOrgPerson)(uid=u1001))' dn uid cn
```

Kỳ vọng: đúng **một** entry trong phạm vi đã duyệt. Nếu trả nhiều hơn, cần sửa uniqueness/scope thay vì lấy dòng đầu tiên.

**Bước 2 – Bind bằng DN người dùng đã tìm:**

```bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D 'uid=u1001,ou=people,dc=example,dc=org' -W
```

`-W` yêu cầu password tương tác, phù hợp hơn việc đưa mật khẩu vào command-line argument. Kết quả của `ldapwhoami` có thể thể hiện authorization identity do server chấp nhận.

Nếu server chạy StartTLS thay vì LDAPS, với OpenLDAP CLI có thể dùng `-H ldap://...:389 -ZZ` để **bắt buộc** thương lượng TLS thành công. CA/truststore của client LDAP phải được cấu hình đúng; không tắt kiểm tra chứng chỉ chỉ để lệnh chạy được.

**Cần hiểu:** `ldapsearch` thành công không chứng minh `ldapwhoami` bằng user DN sẽ thành công. Ngược lại, user bind thành công không có nghĩa service account có quyền đọc `memberOf` hoặc mọi thuộc tính nhân sự.

## 18. Kiểm thử unit và integration với directory

Unit test giúp xác minh validation và cách dựng filter, nhưng **mock `LdapTemplate` không chứng minh LDAP server có thực sự xác thực mật khẩu đúng**. Cần integration test với directory test hỗ trợ LDAPS/StartTLS, schema và policy gần môi trường sản xuất.

| Ca kiểm thử | Đầu vào/thiết lập | Kết quả kỳ vọng |
|---|---|---|
| Username + password đúng | `u1001`, mật khẩu test chính xác | Search đúng DN, user bind thành công |
| Password sai | `u1001`, password khác | Không xác thực |
| Password rỗng | `u1001`, `""` | **Bị từ chối trước LDAP bind** |
| Username rỗng | `""`, password bất kỳ | Bị từ chối trước search |
| Username không tồn tại | `unknown` | Không bind, lỗi công khai trung tính |
| Hai DN cùng `uid` | Entry ở hai OU con | Từ chối do ambiguity, không lấy entry đầu |
| Username injection | `u1001*)(|(uid=*))` | Không mở rộng filter, không đăng nhập sai |
| User đổi OU | DN được rename/move trong phạm vi | Search tìm DN hiện tại, bind đúng principal |
| User bị move ra scope | DN không còn dưới OU cho phép | Không mở rộng search ngoài phạm vi |
| Service account thiếu ACL | Không được search `uid` | Lỗi lookup/authorization rõ ở logs, không coi là password sai |
| Account bị khóa/hết hạn | Directory policy từ chối bind | Xác thực thất bại theo policy |
| Chứng chỉ server sai | TLS hostname/CA không hợp lệ | Fail closed, không gửi password cleartext |
| StartTLS không hỗ trợ | Endpoint từ chối nâng cấp | Không fallback SIMPLE bind thường |
| Group/role không đủ | User bind đúng nhưng thiếu role | Đăng nhập/quyền app được xử lý theo chính sách |
| Directory timeout | Service/search/bind bị gián đoạn | Lỗi hạ tầng, không tạo session |
| Concurrent login | Nhiều user cùng đăng nhập | Không trộn DN, password hoặc JNDI context |
| Password thay đổi | Đổi password trên directory | Bind cũ không được xác thực lại bằng password đã thu hồi |
| Referral/cross-domain | Entry nằm ở naming context khác | Chỉ xử lý theo policy server/tenant đã kiểm chứng |

### Unit test cho escaping

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class LoginFilterTest {

    @Test
    void usernameSpecialCharsAreEscaped() {
        String input = "u1001*)(|(uid=*))";

        String filter =
                new EqualsFilter("uid", input).encode();

        assertTrue(filter.contains("\\2a"));
        assertTrue(filter.contains("\\29"));
        assertTrue(filter.contains("\\28"));
        assertFalse(filter.contains(")(|(uid=*))"));
    }
}
```

Bài unit test này kiểm tra cách **escape giá trị filter**. Nó không thay thế kiểm thử **bind**. Khi test tích hợp, tạo ít nhất hai user ở hai OU với username trùng nhau để phát hiện việc chọn DN sai.

### Xác minh không có password leakage

- Bật log/tracing theo chính sách test, xác minh **không log password, secret hoặc thuộc tính credential**.
- Giả lập TLS failure và xác nhận ứng dụng **không thử gửi password sang `ldap://` cleartext**.
- Nếu dùng HTTP session/JWT, xác minh thất bại trước bind không tạo trạng thái đã đăng nhập.
- Kiểm thử khóa tài khoản/rate limiting với dữ liệu test, không khóa tài khoản người dùng thật khi benchmark.

## 19. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm/sai | Giải pháp |
|---|---|---|
| Chỉ `findByUid` rồi cho đăng nhập | Search thấy entry không chứng minh password đúng | Bind bằng user DN và credential |
| Dùng DN của service account cho bước bind user | Xác thực nhầm danh tính | User DN lấy từ search phải được dùng |
| Dựng DN bằng `"uid=" + username` | Sai khi move/rename và có nguy cơ DN injection | Search DN hoặc xây RDN với `LdapNameBuilder` nếu pattern thật sự cố định |
| Nối raw LDAP filter | LDAP injection | `LdapQueryBuilder`/`EqualsFilter` |
| Lấy entry đầu tiên khi trùng login | Xác thực sai principal | Yêu cầu đúng một DN |
| Đặt search size limit = 1 để “đảm bảo unique” | Che duplicate | Kiểm tra đầy đủ số kết quả |
| Chấp nhận password rỗng | Có thể bị server xử lý thành unauthenticated bind | Reject trước bind |
| Dùng `ldap://` không StartTLS | Có thể lộ password SIMPLE bind | LDAPS/StartTLS có xác minh cert |
| Bỏ qua TLS exception rồi retry cleartext | Downgrade nguy hiểm | Fail closed |
| Cache user context vào shared pool | Rò quyền giữa các user | Đóng context, không pool tùy tiện credential người dùng |
| Coi bind thành công là có role admin | Authentication khác authorization | Kiểm tra group/role/policy riêng |
| Catch mọi exception trả “password sai” | Che TLS/ACL/outage, khó vận hành | Phân loại nội bộ, trả lỗi công khai phù hợp |
| Dùng `boolean ok = authenticate(query, password)` | Sai chữ ký overload hiện hành | Dạng `LdapQuery` trả `void`, ném exception |
| Đọc `userPassword` rồi so hash | Không di động, sai cơ chế LDAP auth | Để directory kiểm tra bằng bind |
| Thử nhiều user DN khi query mơ hồ | Rủi ro login nhầm người | Thất bại nếu không duy nhất |

## 20. Bài tập thực hành

Một hệ thống có Spring Boot + Spring Data LDAP dùng `LdapContextSource` base `dc=example,dc=org`, user search base `ou=people` và một service account chỉ có quyền search user.

Directory chứa:

```text
uid=u1001,ou=employees,ou=people,dc=example,dc=org
uid=u1001,ou=contractors,ou=people,dc=example,dc=org
uid=u1002,ou=employees,ou=people,dc=example,dc=org
```

Hãy trả lời:

1. Nếu user nhập `u1002`, filter tìm DN nào là phù hợp? Search scope cần là ONELEVEL hay SUBTREE?
2. Nếu nhập `u1001`, vì sao không được lấy kết quả search đầu tiên rồi bind?
3. Vì sao password rỗng phải bị từ chối trước khi gọi LDAP?
4. Tại sao `ldapTemplate.authenticate(LdapQuery, String)` không thể gán trực tiếp cho một biến `boolean`?
5. Nếu username chứa `*)(|(uid=*))`, cần làm gì để nó chỉ là dữ liệu?
6. Tại sao service account search và user account bind là hai danh tính khác nhau?
7. Khi nào DN pattern có thể dùng thay search, và rủi ro khi user chuyển OU là gì?
8. Với LDAP server có StartTLS, vì sao không thể chỉ đổi URL từ `ldaps://` sang `ldap://`?
9. Sau bind thành công, có được cho user sửa mọi nhóm LDAP không? Vì sao?
10. Nếu một kết quả search bị cắt bởi limit, có được coi là chỉ tìm được một DN không?
11. Khi LDAP server không hoạt động, lỗi API nên được phân loại thế nào để không ngụy trang thành “password sai”?
12. Hãy đề xuất tối thiểu sáu integration tests bao gồm password sai, duplicate DN, injection, TLS, ACL và concurrency.

**Đáp án gợi ý:** với `u1002` dùng equality filter trên `uid` + `objectClass` trong scope đã duyệt, thường cần SUBTREE để nhìn OU con. `u1001` trùng login nên phải từ chối hoặc có quy tắc tenant/scope bổ sung đáng tin. Password rỗng bị chặn để tránh unauthenticated bind. `LdapTemplate.authenticate(LdapQuery, String)` là phương thức `void` ném exception. LDAP filter builder escape giá trị; TLS phải được thương lượng trước bind. Bind chỉ xác thực danh tính, role/authorization là bước riêng.

## 21. Checklist triển khai và tổng kết

Trước khi đưa search-then-bind vào ứng dụng:

- [ ] Đã định nghĩa rõ **username attribute**, **search base/scope** và **tính duy nhất của login**.
- [ ] Đã phân biệt DN, RDN, `uid`, `@Id Name` và các thuộc tính ODM.
- [ ] Tài khoản service search chỉ có quyền tối thiểu, không thể đọc/write bí mật ngoài nhu cầu.
- [ ] Filter tìm user có object class/attribute cố định và **escape giá trị theo RFC 4515**.
- [ ] Search phải trả **đúng một entry**; lỗi duplicate, referral, paging/limit được xử lý fail closed.
- [ ] Password `null`/rỗng bị từ chối **trước** bind; không trim password hoặc log secret.
- [ ] Bind dùng **DN của người dùng** và credential chính người đó, không dùng service account.
- [ ] LDAP kết nối qua **LDAPS/StartTLS có xác minh chứng chỉ**, không downgrade.
- [ ] Khi dùng API `LdapTemplate.authenticate(LdapQuery, String)`, đã hiểu **trả `void`/ném exception**.
- [ ] Nếu tự dùng `ContextSource.getContext(...)`, context được đóng và không dùng native pool cho user-specific bind.
- [ ] Với HTTP login, đã cân nhắc **Spring Security LDAP BindAuthenticator** và authentication manager.
- [ ] Authentication, authorization, group membership, MFA và session được tách rõ.
- [ ] Có rate limiting, log không chứa password, theo dõi latency search/bind và mã lỗi.
- [ ] Đã có integration test cho đúng/sai password, empty password, duplicate DN, injection, TLS, ACL, lỗi hạ tầng và rename/move.

### Tài liệu kỹ thuật tham khảo

- [Spring LDAP API – LdapOperations.authenticate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapOperations.html).
- [Spring LDAP API – LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html).
- [Spring LDAP API – ContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/ContextSource.html).
- [Spring Security – LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html).
- [RFC 4511 – LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4513 – LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513).
- [RFC 4515 – LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515).

**Kết luận:** quy trình **tìm DN người dùng rồi bind** giải quyết khoảng cách giữa tên đăng nhập nghiệp vụ và DN thực trong directory. Trong Spring Data LDAP, hãy dùng `LdapTemplate.authenticate(LdapQuery, String)` khi phù hợp hoặc tách search và `ContextSource.getContext(...)` nếu có yêu cầu kiểm soát riêng; với đăng nhập HTTP, ưu tiên tích hợp **Spring Security LDAP**. Chỉ xác thực khi tìm thấy đúng một DN và server chấp nhận bind trên kết nối TLS đáng tin, đồng thời từ chối mật khẩu rỗng, filter không an toàn, kết quả mơ hồ và mọi cơ chế hạ cấp.
