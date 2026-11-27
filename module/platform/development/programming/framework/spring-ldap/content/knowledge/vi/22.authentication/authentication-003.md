# Search user bằng filter an toàn trong Spring LDAP

Khi người dùng nhập tên đăng nhập hoặc email, ứng dụng thường phải **tìm đúng entry LDAP** của người đó trước khi kiểm tra mật khẩu bằng bind. Bước tìm kiếm tưởng chừng đơn giản này có thể gây lỗi xác thực và lộ dữ liệu nếu ứng dụng tự nối dữ liệu người dùng vào chuỗi **LDAP search filter**.

Ví dụ, ứng dụng quản lý nhân sự cho phép đăng nhập bằng `uid`. Với đầu vào `lan`, ứng dụng muốn tìm đúng entry có `uid=lan`. Nhưng nếu ghép filter bằng chuỗi và người dùng nhập `*`, điều kiện `(uid=*)` sẽ trở thành phép kiểm tra “có thuộc tính uid”, có thể trả về **rất nhiều tài khoản** thay vì một người dùng cụ thể.

Bài học này tập trung vào **xây dựng LDAP filter an toàn khi tìm người dùng trong luồng Authentication bằng Spring LDAP**, kết hợp lựa chọn search base, search scope, xử lý kết quả và mối liên hệ giữa search với user bind. Các ví dụ áp dụng cho thư mục LDAP nói chung; tên thuộc tính và schema cần điều chỉnh theo máy chủ thực tế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu cấu trúc filter LDAP và lý do nối chuỗi với đầu vào không tin cậy dẫn đến **LDAP filter injection**.
- Phân biệt **exact match**, wildcard search và cách escape ký tự theo **RFC 4515**.
- Viết truy vấn tìm người dùng bằng `LdapQueryBuilder` hoặc `EqualsFilter` của Spring LDAP.
- Giới hạn vùng tìm kiếm bằng base DN, scope, thuộc tính được trả về và quyền của tài khoản dịch vụ.
- Xử lý an toàn trường hợp **không tìm thấy**, **nhiều entry phù hợp** và **lỗi dịch vụ thư mục**.
- Hiểu vì sao tìm thấy entry chỉ là bước định danh, **chưa phải xác thực người dùng**.

## 1. LDAP search filter là gì?

Một lệnh LDAP search gồm những thành phần chính:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Base DN** | Gốc của vùng tìm kiếm | `ou=people,dc=example,dc=org` |
| **Search scope** | Những mức trong cây thư mục được duyệt | Một cấp hoặc toàn bộ cây con |
| **Filter** | Điều kiện để entry được xem là phù hợp | `(&(objectClass=inetOrgPerson)(uid=lan))` |
| **Requested attributes** | Các thuộc tính muốn đọc từ entry tìm được | `uid`, `cn` |
| **Bind identity** | Danh tính LDAP thực hiện search | Tài khoản dịch vụ được cấp quyền đọc |

Một filter LDAP theo RFC 4515 có dạng biểu thức đặt trong ngoặc:

~~~text
(uid=lan)
(mail=lan@example.org)
(&(objectClass=inetOrgPerson)(uid=lan))
(|(uid=lan)(mail=lan@example.org))
(!(accountStatus=disabled))
~~~

Các toán tử thường gặp:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| `=` | So khớp theo luật matching của schema LDAP | `(uid=lan)` |
| `*` | Wildcard trong biểu thức substring hoặc phép kiểm tra sự tồn tại | `(cn=Lan*)`, `(uid=*)` |
| `&` | AND: tất cả điều kiện con phải đúng | `(&(objectClass=person)(uid=lan))` |
| \| | OR: ít nhất một điều kiện con đúng | `(&(objectClass=person)(\|(uid=lan)(mail=lan@example.org)))` |
| `!` | NOT: phủ định điều kiện | `(!(uid=lan))` |
| `>=`, `<=` | So sánh thứ tự nếu attribute hỗ trợ matching rule phù hợp | `(employeeNumber>=1000)` |

Ở đây, **exact match** là so khớp giá trị thuộc tính theo matching rule của LDAP, không có nghĩa là so sánh từng byte hay luôn phân biệt hoa thường. Ví dụ `uid` trong một schema có thể dùng quy tắc so khớp không phân biệt hoa thường. Ứng dụng cần hiểu matching rule của thư mục thay vì tự kết luận hai tên đăng nhập khác nhau về chữ hoa/chữ thường là hai tài khoản độc lập.

## 2. Rủi ro khi ghép filter bằng chuỗi

### 2.1. Ví dụ không an toàn

Đoạn mã sau **không nên sử dụng** khi `username` nhận dữ liệu từ request:

~~~java
// KHÔNG AN TOÀN: username là đầu vào của người dùng.
String filter = "(&(objectClass=inetOrgPerson)(uid="
        + username + "))";

List<String> results = ldapTemplate.search(
        "ou=people",
        filter,
        (AttributesMapper<String>) attrs ->
                attrs.get("uid").get().toString()
);
~~~

Với `username = "lan"`, filter được tạo ra là:

~~~text
(&(objectClass=inetOrgPerson)(uid=lan))
~~~

Nhưng với `username = "*"`, filter được tạo ra là:

~~~text
(&(objectClass=inetOrgPerson)(uid=*))
~~~

Điều kiện `uid=*` nghĩa là thuộc tính `uid` **tồn tại**, không phải `uid` có nội dung là một dấu sao. Truy vấn vốn cần tìm một người dùng đã bị mở rộng thành tìm mọi entry mang `uid` và phù hợp `objectClass`. Đây là một ví dụ trực quan của việc cho phép dữ liệu đầu vào thay đổi ý nghĩa cú pháp filter.

Kẻ tấn công cũng có thể thử dấu ngoặc, dấu gạch chéo ngược và các cấu trúc logic để làm sai điều kiện search hoặc gây lỗi parser. Mức độ tác động phụ thuộc vào cách xây filter, quyền của tài khoản thực hiện search, phạm vi tìm kiếm và cách ứng dụng xử lý kết quả.

### 2.2. Hậu quả trong quy trình đăng nhập

Sự cố có thể biểu hiện dưới nhiều dạng:

- Tìm thấy tài khoản **khác với danh tính được yêu cầu** do điều kiện search bị nới rộng.
- Trả về nhiều entry, sau đó ứng dụng chọn phần tử đầu tiên mà không có tiêu chí duy nhất.
- Làm lộ danh sách tài khoản hay thuộc tính không cần thiết khi ứng dụng trả kết quả search ra API.
- Làm tăng tải lên LDAP server do filter quá rộng.
- Khiến ứng dụng xử lý sai lỗi: coi “có ít nhất một entry” là đăng nhập thành công dù **chưa kiểm tra mật khẩu bằng user bind**.

**Quy tắc:** Dữ liệu do người dùng nhập chỉ nên là **giá trị** của điều kiện tìm kiếm. Không cho đầu vào quyết định cấu trúc filter, tên attribute, toán tử, search base hoặc search scope, trừ khi các lựa chọn đó được ánh xạ qua danh sách cho phép rõ ràng ở tầng ứng dụng.

## 3. Escape LDAP filter đúng chuẩn RFC 4515

Trong giá trị của filter, một số ký tự có ý nghĩa cú pháp đặc biệt. Theo RFC 4515, phải mã hóa chúng bằng dấu `\` theo sau hai chữ số hex khi chúng được dùng như **dữ liệu literal**:

| Ký tự literal | Mã escape trong LDAP filter | Vì sao cần escape? |
|---|---|---|
| `*` | `\2a` | Tránh trở thành wildcard / điều kiện hiện diện |
| `(` | `\28` | Tránh làm thay đổi cú pháp nhóm điều kiện |
| `)` | `\29` | Tránh đóng nhóm điều kiện ngoài ý muốn |
| `\` | `\5c` | Tránh bắt đầu chuỗi escape khác |
| NUL (byte `0x00`) | `\00` | Không truyền NUL nguyên dạng trong filter |

Ví dụ người dùng có tên đăng nhập literal `lan*`:

~~~text
Đầu vào người dùng:     lan*
Filter không escape:   (uid=lan*)
Filter đã escape:      (uid=lan\2a)
~~~

Hai filter **khác nghĩa hoàn toàn**: `(uid=lan*)` là tìm giá trị bắt đầu bằng `lan`, trong khi `(uid=lan\2a)` tìm literal chứa dấu `*` theo quy tắc so khớp attribute.

> **Lưu ý về encoding:** RFC 4515 quy định biểu diễn string LDAP filter theo UTF-8 và cú pháp escape byte dạng hex. Các byte không hợp lệ của chuỗi UTF-8 cần được xử lý/escape theo chuẩn. Với ứng dụng Java thông thường, hãy sử dụng thư viện tạo filter của Spring LDAP thay vì tự viết hàm thay thế ký tự hoặc tự xử lý UTF-8.

### Escape filter khác escape DN

Giả sử đầu vào là `lan,admin`:

- Khi tìm người dùng bằng `(uid=...)`, giá trị phải được xử lý trong **ngữ cảnh filter**, nơi dấu `*` và dấu ngoặc đặc biệt.
- Khi dựng DN như `uid=<username>,ou=people,dc=example,dc=org`, giá trị RDN phải được escape theo **quy tắc DN** (RFC 4514), trong đó dấu phẩy, dấu cộng và một số ký tự ở đầu/cuối giá trị có ý nghĩa riêng.

Không lấy chuỗi đã escape cho filter rồi ghép vào DN, và cũng không dùng chuỗi escape DN để thay thế cho filter. Với Spring LDAP, dùng `LdapQueryBuilder` / `EqualsFilter` cho filter và `LdapNameBuilder` hoặc API `javax.naming.ldap.Rdn` cho DN.

## 4. Tìm user an toàn bằng `LdapQueryBuilder`

`LdapQueryBuilder` cho phép ứng dụng mô tả điều kiện search qua API thay vì tự ghép chuỗi. Phương thức `where("uid").is(username)` tạo điều kiện bằng giá trị literal và thực hiện escaping tương ứng, nên giá trị `*` do người dùng nhập không tự trở thành wildcard.

### 4.1. Cấu hình kết nối

Ví dụ ứng dụng dùng Spring Boot với Spring LDAP đã được cấu hình và máy chủ thử nghiệm có cây:

~~~text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    └── uid=minh
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=system,dc=example,dc=org
    password: ${LDAP_READER_PASSWORD}
~~~

`username` và `password` ở đây là **tài khoản dịch vụ** có quyền đọc thư mục cần thiết. Mật khẩu phải được lấy từ biến môi trường hoặc secret manager; địa chỉ LDAP là ví dụ, không phải địa chỉ máy chủ công khai để kiểm thử. Với LDAPS, backend phải tin cậy chứng chỉ TLS của LDAP server và xác thực đúng tên máy chủ.

### 4.2. Ví dụ Java có thể tái sử dụng

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
public class LdapUserDirectory {

    private final LdapTemplate ldapTemplate;

    public LdapUserDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Tìm chính xác theo uid, không tạo wildcard từ đầu vào.
    public List<String> findMatchingUids(String username) {
        if (!validUsername(username)) {
            return List.of();
        }

        return ldapTemplate.search(
                userQuery(username),
                (AttributesMapper<String>) attrs ->
                        attrs.get("uid").get().toString()
        );
    }

    // Chỉ bind mới kiểm tra mật khẩu của người dùng.
    public boolean authenticate(String username, String password) {
        if (!validUsername(username)
                || password == null || password.isEmpty()) {
            return false;
        }

        return ldapTemplate.authenticate(
                userQuery(username), password
        );
    }

    private LdapQuery userQuery(String username) {
        return LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(username);
    }

    private boolean validUsername(String username) {
        return username != null
                && !username.isBlank()
                && username.length() <= 128;
    }
}
~~~

**Điểm cần hiểu trong ví dụ:**

1. `userQuery(username)` định nghĩa **search base** `ou=people` tương đối với `spring.ldap.base`, tức tìm dưới `ou=people,dc=example,dc=org`. Không nhận base DN từ request.
2. `SearchScope.SUBTREE` cho phép tìm trong cả cây con bên dưới vùng này. Nếu tài khoản luôn nằm trực tiếp trong `ou=people`, có thể cân nhắc `SearchScope.ONELEVEL` để hạn chế phạm vi.
3. `where("objectClass").is("inetOrgPerson")` xác định loại entry cần tìm. Đây là lựa chọn minh họa; Active Directory hay schema nội bộ có thể cần attribute/`objectClass` khác.
4. `and("uid").is(username)` so khớp `uid` với **giá trị** username; các ký tự đặc biệt được xử lý ở lớp xây filter.
5. `ldapTemplate.search(...)` chỉ thực hiện tra cứu và đọc `uid` từ entry. Kết quả là danh sách, **không phải bằng chứng đã xác thực**.
6. `ldapTemplate.authenticate(...)` tìm danh tính theo truy vấn rồi dùng mật khẩu để thực hiện bind xác thực. Phải từ chối mật khẩu rỗng trước bước này; không tự đọc `userPassword` để so sánh.
7. Giới hạn `128` ký tự chỉ là **chính sách minh họa** để chặn đầu vào bất thường, không phải giới hạn do giao thức LDAP áp đặt. Ứng dụng phải xác định quy tắc độ dài và chuẩn hóa tên đăng nhập phù hợp thực tế.

Đoạn code tập trung vào cách tạo filter đúng. Khi đưa vào production, cần bảo đảm `uid` **duy nhất trong vùng search**, kiểm soát quyền truy cập, xử lý lỗi và xác định quy tắc trả về khi có nhiều entry phù hợp. Không được dựa vào thứ tự kết quả tìm kiếm để chọn một danh tính tùy ý.

### 4.3. Cách thay thế bằng `EqualsFilter` / `AndFilter`

Khi dùng API `LdapTemplate.search(base, filter, mapper)` nhận filter dạng chuỗi, vẫn có thể tạo filter an toàn bằng các đối tượng `Filter` của Spring LDAP:

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(new EqualsFilter("uid", username));

String safeFilter = filter.encode();

List<String> users = ldapTemplate.search(
        "ou=people",
        safeFilter,
        (AttributesMapper<String>) attrs ->
                attrs.get("uid").get().toString()
);
~~~

Ở đây, `EqualsFilter` nhận **giá trị thuộc tính** và mã hóa nó như một giá trị so khớp equality. `AndFilter` tạo cấu trúc AND hợp lệ mà ứng dụng không phải nối ngoặc thủ công. Trước khi chạy, hãy áp dụng cùng bước kiểm tra `username` như ở ví dụ trên.

**Không nhầm lẫn:** Nếu mục tiêu là tìm theo tiền tố, có thể dùng các phép tìm substring/wildcard được thiết kế cho chức năng tìm kiếm. Nhưng **ô đăng nhập** cần đối sánh một định danh cụ thể, vì vậy nên dùng điều kiện equality (`is` / `EqualsFilter`) thay vì điều kiện `like` với wildcard được lấy từ người dùng.

## 5. Search an toàn còn phụ thuộc vào phạm vi và dữ liệu

Escape filter chỉ giải quyết việc dữ liệu đầu vào làm đổi **cú pháp filter**. Một truy vấn vẫn có thể không an toàn về nghiệp vụ nếu tìm quá rộng hoặc xử lý kết quả sai.

### 5.1. Search base, scope và quyền truy cập

Giả sử thư mục có:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── ou=contractors
│       └── uid=ngoc
└── ou=system
    └── cn=svc-reader
~~~

Với base `ou=people,dc=example,dc=org`:

| Scope | Tìm ở đâu? | Tình huống |
|---|---|---|
| `OBJECT` / base | Chỉ tại entry base | Kiểm tra thuộc tính của một entry đã biết |
| `ONELEVEL` | Các entry con trực tiếp | Người dùng chỉ nằm ngay dưới `ou=people` |
| `SUBTREE` | Entry base và các cấp con | Người dùng nằm ở nhiều OU con |

Tên các hằng số tương ứng tùy API; trong ví dụ Spring LDAP dùng `SearchScope.SUBTREE`.

Chọn base/scope rộng hơn nhu cầu có thể khiến tìm kiếm chậm, khớp nhầm entry từ OU không liên quan hoặc đọc dữ liệu ngoài vùng dự định. Chọn quá hẹp lại khiến người dùng hợp lệ không tìm thấy. Do đó phải thống nhất phạm vi tìm kiếm với **mô hình quản lý tài khoản** và ACL của thư mục.

Tài khoản dịch vụ dùng để search chỉ nên được cấp quyền đọc **những OU và attribute thật sự cần**. Trong một API tra cứu danh tính, thường chỉ cần trả về tên định danh, DN và một số thuộc tính công khai; không nên lấy toàn bộ entry rồi trả thẳng về trình duyệt. Cơ chế chọn các attribute trả về có thể cấu hình thông qua query/search controls tùy cách gọi `LdapTemplate`.

### 5.2. Danh tính phải duy nhất

Khi tìm người dùng theo `uid` hoặc email, ứng dụng phải phân biệt ba trường hợp:

| Số entry khớp | Ý nghĩa | Cách xử lý |
|---|---|---|
| `0` | Không tìm thấy danh tính trong vùng hợp lệ | Thất bại xác thực; phản hồi bên ngoài trung tính |
| `1` | Tìm được đúng một entry ứng viên | Cho phép tiếp tục bước **user bind** |
| `>1` | Danh tính mơ hồ hoặc phạm vi search quá rộng | Từ chối, ghi nhận lỗi cấu hình/dữ liệu, không chọn entry đầu tiên |

Ví dụ, nếu một tổ chức cho phép hai OU cùng chứa `uid=lan`, truy vấn `SUBTREE` trên cả hai OU có thể trả về hai entry. Trường hợp này vẫn xảy ra khi filter đã escape **hoàn toàn đúng**. Cần áp dụng quy tắc duy nhất ở mức thư mục hoặc thiết kế thêm ngữ cảnh danh tính đáng tin cậy (ví dụ miền đăng nhập), không dựa vào `results.get(0)`.

Nếu kiểm tra số kết quả ở bước search rồi mới bind trong một request khác, cần lưu ý dữ liệu có thể thay đổi giữa hai thao tác. Cách chắc chắn hơn là đảm bảo uniqueness bằng chính sách quản lý thư mục và để luồng xác thực xử lý tình huống mơ hồ theo nguyên tắc **fail closed**.

### 5.3. Chọn attribute phù hợp với schema

| Mô hình thư mục | Thuộc tính đăng nhập thường gặp | Lưu ý |
|---|---|---|
| OpenLDAP với `inetOrgPerson` | `uid`, đôi khi `mail` | Không mặc định coi `mail` là duy nhất nếu schema không áp đặt |
| Active Directory | `sAMAccountName`, `userPrincipalName` | `sAMAccountName` có ngữ cảnh miền; nếu tìm nhiều miền cần cơ chế định danh rõ ràng |
| LDAP theo schema riêng | Mã nhân viên hoặc thuộc tính được quản trị riêng | Phải xác nhận matching rule, tính duy nhất, quyền search và khả năng đổi định danh |

**Tên attribute cố định** phải do ứng dụng lựa chọn. Nếu form cho phép tìm bằng “username hoặc email”, hãy ánh xạ lựa chọn giao diện sang tên thuộc tính trong danh sách cho phép; không trực tiếp truyền tên attribute do người dùng tự nhập vào query builder.

## 6. Kết nối bước search với LDAP bind authentication

Trong Spring LDAP, chức năng tìm user thường là **giai đoạn đầu** của luồng đăng nhập:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant App as Backend Spring
    participant LDAP as LDAP server
    User->>App: Username + mật khẩu qua HTTPS
    App->>App: Kiểm tra đầu vào / dựng filter an toàn
    App->>LDAP: Service bind và search theo uid equality
    LDAP-->>App: 0, 1 hoặc nhiều entry / lỗi LDAP
    alt Có đúng một entry hợp lệ
        App->>LDAP: User bind bằng DN + mật khẩu
        LDAP-->>App: Thành công hoặc thất bại
        App->>App: Áp dụng chính sách phân quyền/phiên đăng nhập
        App-->>User: Kết quả đăng nhập
    else Không có entry hoặc định danh mơ hồ
        App-->>User: Đăng nhập không thành công
    else Lỗi kết nối, TLS hoặc ACL
        App-->>User: Thông báo lỗi dịch vụ phù hợp
    end
~~~

Khi áp dụng `LdapTemplate.authenticate(userQuery, password)`, Spring LDAP hỗ trợ phần tìm kiếm rồi bind theo truy vấn đã cung cấp. Việc tích hợp vào `Spring Security`, cấp session/JWT, tìm nhóm và quyết định quyền truy cập là trách nhiệm của tầng bảo mật ứng dụng; chúng **không tự xảy ra** chỉ vì `search(...)` trả về một entry.

Một số quy tắc thực tế:

- **Không dùng search làm xác thực:** `findMatchingUids("lan")` trả về `lan` chỉ chứng minh có entry phù hợp với filter và quyền đọc; người đăng nhập vẫn chưa chứng minh mình sở hữu mật khẩu.
- **Không bind bằng tài khoản dịch vụ rồi xem như người dùng đã đăng nhập:** tài khoản dịch vụ chỉ hỗ trợ việc tìm kiếm.
- **Không dùng filter lấy từ client gửi nguyên vẹn:** hãy nhận các giá trị như username/email và tạo filter từ phía backend.
- **Không dùng anonymous bind hoặc mật khẩu rỗng làm bằng chứng xác thực:** kiểm soát riêng các biến thể anonymous/unauthenticated simple bind.
- **Không trao quyền ứng dụng trước khi kiểm tra nhóm/quyền:** bind xác thực danh tính; authorization là bước tiếp theo.

## 7. Phân biệt lỗi đầu vào, lỗi xác thực và lỗi hạ tầng

| Tình huống | Mức độ/nguồn lỗi | Hướng xử lý |
|---|---|---|
| `username` rỗng, quá dài hoặc không đúng chính sách | Dữ liệu request không hợp lệ | Từ chối trước khi gọi LDAP |
| Username có `*`, `(` hoặc `\` | Ký tự đầu vào cần escape | Dùng equality filter an toàn; không tự suy ra đây là nỗ lực tấn công |
| Không tìm thấy entry | Danh tính không tồn tại trong vùng search | Trả lỗi đăng nhập chung, không tiết lộ sự tồn tại của tài khoản |
| Mật khẩu sai | User bind không thành công | Trả lỗi đăng nhập chung; không ghi mật khẩu |
| Tìm thấy nhiều entry | Vi phạm tính duy nhất / lỗi cấu hình vùng search | Từ chối an toàn, cảnh báo vận hành |
| LDAP server không phản hồi | Timeout hoặc gián đoạn mạng | Giám sát lỗi dịch vụ, không coi mặc nhiên là mật khẩu sai |
| TLS/chứng chỉ không hợp lệ | Không thiết lập được kênh tin cậy | Dừng kết nối và sửa chứng chỉ/truststore |
| Tài khoản dịch vụ bị từ chối search | ACL hoặc cấu hình bind sai | Điều tra cấu hình/permission, không đổi sang tài khoản quản trị để “cho chạy” |
| Search trả quá nhiều entry | Filter/scope quá rộng hoặc cấu hình giới hạn chưa phù hợp | Giảm phạm vi, đặt giới hạn/tối ưu chỉ mục, sửa logic ứng dụng |

Ở API bên ngoài, nên tránh phản hồi “username này có tồn tại” hoặc “username không tồn tại” theo cách có thể giúp dò tài khoản. Ở log nội bộ, phân biệt **search 0 kết quả**, **bind sai thông tin**, **duplicate identity** và **server unavailable** bằng mã sự kiện và correlation ID, đồng thời tránh log mật khẩu và dữ liệu định danh nhạy cảm không cần thiết.

## 8. Kiểm thử filter an toàn

### 8.1. Bộ dữ liệu thử nghiệm

Tạo một LDAP directory dùng cho môi trường test có:

- `uid=lan,ou=people,dc=example,dc=org`: tài khoản hợp lệ.
- `uid=minh,ou=people,dc=example,dc=org`: tài khoản hợp lệ khác.
- Một entry dưới OU ngoài phạm vi search để xác minh base DN.
- Tùy kịch bản, hai entry ở các OU khác nhau có cùng `uid` để xác minh xử lý kết quả mơ hồ.

Không thử nghiệm payload injection trực tiếp lên directory thật nếu không có môi trường và dữ liệu được kiểm soát.

### 8.2. Trường hợp nên kiểm thử

| Dữ liệu / điều kiện | Hành vi kỳ vọng |
|---|---|
| `username="lan"` | Chỉ tìm entry có `uid=lan` theo matching rule cấu hình |
| `username="*"` | Dấu sao được xem là literal; không biến thành `(uid=*)` |
| `username="lan*"` | Không tạo substring search `(uid=lan*)` |
| `username="lan)(uid=*"` | Không thay đổi cấu trúc filter hoặc phá parser |
| `username` chứa dấu `\` hoặc ký tự Unicode hợp lệ | Xử lý escaping/encoding theo thư viện và schema |
| `username=null`, chuỗi rỗng, toàn khoảng trắng | Bị từ chối hoặc trả rỗng trước khi gọi LDAP |
| Tên đăng nhập đúng, mật khẩu sai | Search có thể tìm thấy entry, nhưng authentication thất bại |
| Có hai entry cùng `uid` trong phạm vi search | Không tùy tiện chọn entry đầu tiên |
| Entry nằm ngoài base DN | Không lọt vào kết quả |
| Tài khoản dịch vụ chỉ có quyền đọc OU người dùng | Search hoạt động trong vùng được cấp phép, không truy vấn vùng bị cấm |
| TLS không hợp lệ hoặc kết nối timeout | Trả lỗi hạ tầng an toàn, không hạ cấp sang kết nối không mã hóa |

Trong kiểm thử tích hợp, hãy dùng LDAP server giả lập/embedded directory hỗ trợ query và bind thật để kiểm tra hành vi end-to-end. Trong kiểm thử đơn vị, có thể kiểm tra **biểu diễn filter đã encode** của `EqualsFilter`, chẳng hạn đầu vào `lan*` phải giữ dấu sao là dữ liệu literal thay vì wildcard. So sánh hành vi và ý nghĩa filter sẽ bền vững hơn so với phụ thuộc vào cách viết chữ hoa/thường của hex escape.

### 8.3. Checklist trước khi triển khai

1. Bộ lọc được tạo bằng `LdapQueryBuilder` hoặc `Filter` có escaping; không có chỗ nối chuỗi trực tiếp với dữ liệu request.
2. Base DN, scope, loại entry và tên attribute được cấu hình cố định hoặc ánh xạ từ danh sách cho phép.
3. Thuộc tính định danh có quy tắc duy nhất rõ ràng; không đăng nhập dựa trên entry đầu tiên nếu có nhiều kết quả.
4. Tài khoản dịch vụ chỉ được cấp quyền đọc cần thiết; kết nối LDAP dùng LDAPS hoặc StartTLS đã xác minh chứng chỉ.
5. Search không bị dùng thay thế user bind; mật khẩu rỗng bị từ chối.
6. Có giới hạn truy vấn phù hợp: timeout, size limit, phân trang khi là màn hình danh sách; ưu tiên equality và chỉ mục directory cho tìm người dùng đăng nhập.
7. Response và log không tiết lộ mật khẩu, toàn bộ LDAP filter chứa dữ liệu nhạy cảm, hay khả năng tồn tại tài khoản ngoài nhu cầu.

## 9. Câu hỏi tự kiểm tra

1. Tại sao `(uid=*)` không có nghĩa là tìm tài khoản có tên là một dấu sao?
2. Vì sao `where("uid").is(username)` an toàn hơn nối `"(uid=" + username + ")"`?
3. Nếu truy vấn đã escape chuẩn nhưng trả về hai DN cùng `uid`, vấn đề nằm ở đâu?
4. Vì sao quy tắc escape DN không thể dùng thay thế cho escape filter?
5. Sau khi search tìm thấy đúng một entry, ứng dụng cần làm gì trước khi coi người dùng đã đăng nhập?
6. Nếu search trả lỗi timeout, ứng dụng có nên coi đó là mật khẩu sai không?

**Gợi ý trả lời:** (1) `*` là ký hiệu wildcard/kiểm tra tồn tại trong filter; (2) query builder đặt username làm giá trị literal và escape ký tự cú pháp; (3) tính duy nhất hoặc phạm vi dữ liệu; (4) DN và filter có hai ngữ pháp khác nhau; (5) user bind bằng mật khẩu rồi áp dụng chính sách ứng dụng; (6) không, đây là lỗi hạ tầng cần xử lý và giám sát riêng.

## Kết luận

Tìm user bằng filter an toàn là bước cơ bản của LDAP bind authentication trong Spring LDAP. Hãy tạo filter theo cấu trúc cố định bằng `LdapQueryBuilder` hoặc `EqualsFilter`, để thư viện escape các giá trị theo RFC 4515, giới hạn đúng base DN/scope và không giả định kết quả search luôn duy nhất. **Tìm đúng entry không thay thế xác thực bằng bind**; chỉ khi danh tính đã được kiểm tra bằng mật khẩu và đáp ứng chính sách phân quyền, ứng dụng mới có thể cấp quyền truy cập.
