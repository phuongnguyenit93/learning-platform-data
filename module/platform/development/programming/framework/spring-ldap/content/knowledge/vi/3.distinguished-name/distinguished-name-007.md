# DN tương đối so với base context trong Spring LDAP

Trong LDAP, mỗi **entry** có một **Distinguished Name (DN)** xác định vị trí của nó trong cây thư mục. Khi làm việc với Spring LDAP, một điểm dễ gây nhầm lẫn là: DN đầy đủ nhìn thấy trong thư mục và **DN truyền vào `LdapTemplate`** có thể khác nhau, vì `ContextSource` đã được cấu hình một **base context**. Hiểu đúng mối quan hệ này giúp tránh tìm kiếm sai nhánh, nhân đôi hậu tố DN và thao tác nhầm entry.

Sau bài học, bạn có thể:

- Phân biệt **DN đầy đủ**, **DN tương đối**, **Relative Distinguished Name (RDN)** và **base context**.
- Từ một DN đầy đủ và một base context, suy ra phần DN cần truyền vào các thao tác Spring LDAP.
- Hiểu sự khác nhau giữa `ContextSource.base` và **search base** của từng truy vấn.
- Xây dựng DN tương đối bằng `LdapNameBuilder`, tránh ghép chuỗi DN thủ công từ dữ liệu nhập.
- Chẩn đoán các lỗi thường gặp khi `lookup` hoặc `search` không tìm thấy entry do chọn sai base.

## 1. DN trong cây thư mục: tên được viết từ lá về gốc

Giả sử tổ chức lưu tài khoản và nhóm trong cấu trúc:

```text
dc=org
└── dc=example
    ├── ou=people
    │   ├── uid=lan
    │   └── uid=minh
    └── ou=groups
        └── cn=developers
```

DN đầy đủ của entry người dùng `lan` là:

```text
uid=lan,ou=people,dc=example,dc=org
```

Một DN gồm các **Relative Distinguished Name (RDN)**, phân cách bằng dấu phẩy. Cách hiển thị LDAP thông dụng viết RDN cụ thể nhất trước, rồi đến các RDN cha:

| Thành phần | Vai trò |
| --- | --- |
| `uid=lan` | RDN của entry người dùng trong ví dụ |
| `ou=people` | Nhánh chứa người dùng |
| `dc=example,dc=org` | Hậu tố miền trong cây thư mục ví dụ |
| `uid=lan,ou=people,dc=example,dc=org` | DN đầy đủ dùng để xác định entry trong cây |

**RDN không đồng nghĩa với DN tương đối.** RDN `uid=lan` chỉ là một thành phần tên; DN tương đối có thể bao gồm **một hoặc nhiều RDN**, tùy base context mà ứng dụng chọn. Trong những trường hợp đặc biệt, một RDN có thể gồm nhiều cặp thuộc tính-giá trị, chẳng hạn `cn=Lan+uid=lan`; vì vậy không nên cố phân tích DN bằng cách tự tách dấu phẩy hoặc dấu cộng.

## 2. Base context là gì?

**Base context**, hay base DN trong cấu hình `ContextSource` của Spring LDAP, là vị trí mà ứng dụng dùng làm **gốc tương đối cho các thao tác LDAP**.

Ví dụ ứng dụng cấu hình:

```text
base context = dc=example,dc=org
```

Khi gọi `LdapTemplate.lookup` với:

```text
uid=lan,ou=people
```

Spring LDAP thực hiện thao tác đối với entry có DN đầy đủ:

```text
uid=lan,ou=people,dc=example,dc=org
```

Có thể hình dung:

```text
DN tương đối:  uid=lan,ou=people
Base context:   dc=example,dc=org
                ─────────────────────────────────────
DN đầy đủ:      uid=lan,ou=people,dc=example,dc=org
```

Đây là **mô hình ghép tên để hiểu địa chỉ**, không phải khuyến nghị nối các chuỗi từ người dùng thành DN. Với giá trị động, hãy dùng API dành cho LDAP Name để xử lý escaping và cấu trúc RDN đúng cách.

Base context là một lựa chọn cấu hình của **client**. Nó không làm thay đổi DN đang lưu trên máy chủ, cũng không nhất thiết trùng với root hay suffix của toàn bộ directory server. Một ứng dụng có thể chọn `dc=example,dc=org`; ứng dụng khác chỉ được cấu hình tại nhánh `ou=people,dc=example,dc=org`.

### Cùng một entry, nhiều cách viết DN tương đối

| Base context trong ứng dụng | DN đầy đủ của entry | DN tương đối đưa cho `LdapTemplate` |
| --- | --- | --- |
| `dc=example,dc=org` | `uid=lan,ou=people,dc=example,dc=org` | `uid=lan,ou=people` |
| `ou=people,dc=example,dc=org` | `uid=lan,ou=people,dc=example,dc=org` | `uid=lan` |
| Không cấu hình base (base rỗng) | `uid=lan,ou=people,dc=example,dc=org` | `uid=lan,ou=people,dc=example,dc=org` |

Vì vậy, **không có một chuỗi “DN tương đối của người dùng Lan” đúng cho mọi ứng dụng**. Chuỗi đó chỉ có nghĩa khi biết đang lấy tương đối với base nào.

## 3. Cấu hình base context trong Spring LDAP

Trong ứng dụng Spring Boot có tích hợp Spring LDAP, có thể cấu hình bằng `application.yml`:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=service-account,ou=system,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Các giá trị URL, người dùng dịch vụ và DN trong ví dụ là giả định; khi triển khai cần thay bằng thông tin thật, cung cấp biến môi trường `LDAP_BIND_PASSWORD` và cấu hình chứng chỉ tin cậy cho TLS phù hợp với hạ tầng.

- `spring.ldap.urls` chỉ địa chỉ LDAP server. Ví dụ dùng LDAPS; môi trường dùng StartTLS có cách cấu hình kết nối riêng.
- `spring.ldap.base` là **base context cho các thao tác với entry**.
- `spring.ldap.username` là **DN dùng để bind (xác thực)** tới server; trong ví dụ nó được cung cấp ở dạng đầy đủ. Không hiểu nhầm đây là DN tương đối cần truyền vào `LdapTemplate.lookup`.
- `spring.ldap.password` nên nhận từ nguồn bí mật, không ghi mật khẩu thật vào repository.

Nếu tạo `LdapContextSource` bằng Java thay vì Boot properties, ý nghĩa của `setBase("dc=example,dc=org")` cũng tương tự: các DN truyền vào những phương thức thao tác của `LdapTemplate` được hiểu tương đối với base context đã thiết lập.

**Lưu ý bảo mật:** base context là cơ chế định vị và thu hẹp phạm vi thao tác của ứng dụng, **không phải ranh giới phân quyền**. Server vẫn phải thực thi ACL cho tài khoản bind; ứng dụng nên dùng kết nối có TLS và chỉ cấp quyền cần thiết.

## 4. Tra cứu entry theo DN tương đối với `LdapTemplate.lookup`

Giả sử `LdapTemplate` đã được cấu hình với base `dc=example,dc=org`. Ta muốn đọc `cn` từ entry `uid=lan,ou=people,dc=example,dc=org`.

```java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

public class UserDirectory {
    private final LdapTemplate ldapTemplate;

    public UserDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String readCommonName() {
        return ldapTemplate.lookup(
            "uid=lan,ou=people",
            (ContextMapper<String>) context -> {
                DirContextOperations entry = (DirContextOperations) context;
                return entry.getStringAttribute("cn");
            }
        );
    }
}
```

Ở đây, `lookup` nhận **DN tương đối** `uid=lan,ou=people`, trong khi entry thật trên server có DN đầy đủ gồm cả `dc=example,dc=org`. Phương thức `lookup` dùng khi **đã biết tên entry** cần đọc; nó khác với `search`, vốn dùng search base và bộ lọc để tìm các entry.

Một lỗi điển hình là truyền cả DN đầy đủ vào cùng `LdapTemplate`:

```java
// Sai nếu ContextSource đã đặt base = "dc=example,dc=org"
ldapTemplate.lookup(
    "uid=lan,ou=people,dc=example,dc=org",
    (ContextMapper<String>) context ->
        ((DirContextOperations) context).getStringAttribute("cn")
);
```

Khi đó phần hậu tố `dc=example,dc=org` có thể bị áp dụng **hai lần**, khiến tên được tra cứu sai và thường dẫn đến lỗi không tìm thấy entry. Cách xử lý là thống nhất một quy ước: **DN truyền vào `LdapTemplate` phải tương đối với base context đã cấu hình**.

## 5. Xây dựng DN tương đối an toàn với `LdapNameBuilder`

Khi `uid` đến từ tham số của hàm, tránh viết:

```java
String relativeDn = "uid=" + uid + ",ou=people"; // Không nên
```

Giá trị thuộc tính trong DN có thể chứa dấu phẩy, dấu cộng, ký tự đặc biệt, dấu cách ở vị trí nhạy cảm... và cần được escape theo quy tắc DN. Nối chuỗi trực tiếp dễ tạo tên sai, thậm chí cho phép dữ liệu đầu vào thay đổi cách diễn giải các RDN.

Spring LDAP có `LdapNameBuilder` để tạo tên theo cấu trúc:

```java
import javax.naming.Name;

import org.springframework.ldap.support.LdapNameBuilder;

public Name relativeUserDn(String uid) {
    return LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", uid)
        .build();
}
```

Với `uid = "lan"`, DN được biểu diễn là `uid=lan,ou=people`. Thứ tự gọi `add` trong ví dụ bắt đầu từ RDN của nhánh cha `ou=people`, rồi thêm RDN con `uid=lan`. Với giá trị như `"lan,qa"`, builder sẽ biểu diễn dấu phẩy như một phần của **giá trị uid**, thay vì một dấu phân cách RDN mới.

Có thể dùng trực tiếp tên đó khi tra cứu:

```java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

Name userDn = relativeUserDn(uid);

String commonName = ldapTemplate.lookup(
    userDn,
    (ContextMapper<String>) context ->
        ((DirContextOperations) context).getStringAttribute("cn")
);
```

Lưu ý hai loại escaping khác nhau:

- **DN escaping** dùng khi xây dựng tên entry, theo quy tắc DN (RFC 4514); dùng `LdapNameBuilder` hoặc API `LdapName`.
- **LDAP filter escaping** dùng khi đưa giá trị vào điều kiện tìm kiếm; dùng `LdapQueryBuilder` hoặc bộ dựng filter tương ứng.

Không dùng hàm escape dành cho filter để tạo DN, và ngược lại.

## 6. Phân biệt base context với search base

Một ứng dụng thường có **hai mức base**:

1. **Base context** đặt một lần ở `ContextSource`, chẳng hạn `dc=example,dc=org`.
2. **Search base** cho một lần gọi `search`, chẳng hạn `ou=people`, được tính **tương đối với base context**.

Ví dụ:

```text
ContextSource base: dc=example,dc=org
Search base:        ou=people
Vị trí tìm thật:    ou=people,dc=example,dc=org
Filter:             (uid=lan)
Entry tìm thấy:     uid=lan,ou=people,dc=example,dc=org
```

Viết truy vấn bằng Spring LDAP:

```java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

List<String> foundUids = ldapTemplate.search(
    query()
        .base("ou=people")
        .where("uid").is("lan"),
    (AttributesMapper<String>) attributes ->
        (String) attributes.get("uid").get()
);
```

Trong ví dụ, `base("ou=people")` không phải **DN đầy đủ** của vùng dữ liệu; đây là đường dẫn con dưới base context đã cấu hình. Filter `(uid=lan)` kiểm tra giá trị thuộc tính của các entry trong phạm vi tìm kiếm.

So sánh:

| Thao tác | Đầu vào liên quan DN | Cách hiểu |
| --- | --- | --- |
| `lookup("uid=lan,ou=people", mapper)` | DN tương đối của **một entry** | Tra cứu đúng entry dưới base context |
| `search(query().base("ou=people").where("uid").is("lan"), mapper)` | Search base + filter | Tìm những entry khớp filter trong phạm vi `ou=people` dưới base context |
| `search(query().base("ou=groups")..., mapper)` | Search base khác | Tìm trong nhánh nhóm, vẫn dưới cùng base context |

Search base quyết định **bắt đầu tìm ở đâu**, còn filter quyết định **entry nào thỏa điều kiện**. Search scope (base object, một cấp hay toàn bộ cây con) tiếp tục quy định độ sâu tìm kiếm; không nhầm khái niệm này với base context.

## 7. Khi dùng ldapsearch, DN thường được đưa ở dạng đầy đủ

Để so sánh với công cụ dòng lệnh kết nối trực tiếp tới server, xem ví dụ (các DN và hostname đều là giả định):

```bash
ldapsearch -H ldaps://ldap.example.org:636 \
  -D "cn=service-account,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  "(uid=lan)" dn cn
```

Với `ldapsearch`, tham số `-b` trong ví dụ là **search base đầy đủ** gửi tới server. Trong ứng dụng Spring LDAP đã cấu hình `base: dc=example,dc=org`, search base tương ứng chỉ là `ou=people`. Hai cách viết cùng hướng tới một vị trí trong cây thư mục vì **điểm xuất phát của client khác nhau**.

Khi kiểm tra bằng công cụ ngoài ứng dụng, hãy so sánh DN đầy đủ trong kết quả `dn: ...` với base context và search base thực tế mà ứng dụng sử dụng. Đừng lấy nguyên chuỗi `dn: ...` của `ldapsearch` rồi mặc nhiên truyền lại cho `LdapTemplate` khi base đã được cấu hình.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng hoặc sai lầm | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `lookup` báo không tìm thấy entry dù tra `ldapsearch` thấy | Truyền DN đầy đủ trong khi `ContextSource` đã có base, dẫn tới hậu tố bị lặp | Xác định base và chỉ truyền phần DN nằm dưới base |
| `lookup("uid=lan")` không thấy entry | Base được đặt ở `dc=example,dc=org`; thiếu `ou=people` | Dùng `uid=lan,ou=people` hoặc thay đổi base nếu phù hợp |
| `search` trả về rỗng | Search base `ou=groups` trong khi người dùng ở `ou=people`, hoặc filter không khớp | Kiểm tra search base, search scope và filter |
| Tên có dấu phẩy hay dấu cộng gây lỗi hoặc trỏ sai entry | Nối chuỗi DN thủ công, không escape giá trị RDN | Xây DN bằng `LdapNameBuilder` |
| Ứng dụng chạy tốt ở môi trường A nhưng lỗi tại B | Hai môi trường dùng base context khác nhau, nhưng code dùng DN cố định | Kiểm tra base theo môi trường; tính DN tương đối phù hợp |
| Dữ liệu tìm thấy nhưng cập nhật bị từ chối | Không đủ quyền, schema/ràng buộc entry hoặc phân quyền ACL của server | Kiểm tra tài khoản bind, ACL, schema và quyền sửa |

Một quy trình chẩn đoán ngắn:

1. Xác định **DN đầy đủ** của entry mục tiêu trên server, ví dụ `uid=lan,ou=people,dc=example,dc=org`.
2. Đọc **base context** của `ContextSource`, ví dụ `dc=example,dc=org`.
3. Xác định **DN tương đối** bằng cách bỏ hậu tố base theo cấu trúc RDN, ví dụ `uid=lan,ou=people`; không dùng thao tác cắt chuỗi tùy tiện cho tên phức tạp.
4. Với `search`, kiểm tra thêm **search base**, **filter** và **scope**. Với `lookup`, kiểm tra chính xác DN tương đối của entry.
5. Nếu vẫn lỗi, xác minh entry tồn tại, kết nối/TLS, quyền truy cập, referral và ràng buộc của directory server.

Một DN được viết đúng vẫn có thể không truy cập được do ACL; ngược lại, một server truy cập thành công không chứng minh code đã chọn đúng entry. Khi thực hiện ghi dữ liệu, hãy xác minh tên mục tiêu trước khi thao tác.

## 9. Bài tập áp dụng

Giả sử trên server có ba entry:

```text
uid=lan,ou=people,dc=example,dc=org
uid=minh,ou=people,dc=example,dc=org
cn=developers,ou=groups,dc=example,dc=org
```

Ứng dụng cấu hình base context là `dc=example,dc=org`.

**Câu hỏi:**

1. Để `lookup` entry của `minh`, bạn truyền DN nào?
2. Muốn tìm nhóm `developers` bằng filter `(cn=developers)`, search base tương đối nên là gì?
3. Nếu đổi base context thành `ou=people,dc=example,dc=org`, DN tương đối của `lan` là gì? Với base này, có thể tìm nhóm `developers` bằng search base `ou=groups` không?
4. Một `uid` có giá trị thực là `lan,qa`. Vì sao `"uid=" + uid + ",ou=people"` có thể cho DN sai?
5. Trong ứng dụng, `lookup("uid=lan,ou=people,dc=example,dc=org")` không tìm thấy dù công cụ bên ngoài vẫn tìm được. Bạn kiểm tra gì trước tiên?

**Đáp án tham khảo:**

1. `uid=minh,ou=people`, vì hậu tố `dc=example,dc=org` đã được cung cấp bởi `ContextSource`.
2. `ou=groups`. Search base kết hợp với base context xác định nhánh `ou=groups,dc=example,dc=org`.
3. DN tương đối là `uid=lan`. Nhánh `ou=groups,dc=example,dc=org` nằm **ngoài** base context hiện tại; không thể định vị nó bằng một search base con như `ou=groups`. Muốn thao tác nhánh đó, cần chọn base phù hợp hoặc một `ContextSource` khác theo thiết kế ứng dụng.
4. Dấu phẩy trong value cần được escape để không bị hiểu nhầm thành dấu phân cách RDN; `LdapNameBuilder` xử lý điều này.
5. Kiểm tra `ContextSource.base`. Nếu base đã là `dc=example,dc=org`, hãy gọi `lookup("uid=lan,ou=people", ...)`; sau đó kiểm tra DN, ACL và kết nối khi cần.

## 10. Tổng kết

DN đầy đủ chỉ ra vị trí của entry trong cây LDAP. **DN tương đối** là phần đường dẫn tính từ một **base context cụ thể**; phần này có thể gồm nhiều RDN, khác với khái niệm **một RDN** đơn lẻ.

Với Spring LDAP, `ContextSource` xác lập base cho các thao tác; `LdapTemplate.lookup` dùng DN tương đối của entry; `LdapTemplate.search` nhận search base tương đối và filter. Hãy xây DN động bằng `LdapNameBuilder`, dùng builder riêng cho filter, đồng thời bảo vệ kết nối bằng TLS và kiểm soát quyền truy cập ở LDAP server.

Tài liệu tham khảo:

- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cấu trúc và cách escape DN.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): DN, thao tác tìm kiếm và search scope.
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate`, query builder và xây dựng DN.
