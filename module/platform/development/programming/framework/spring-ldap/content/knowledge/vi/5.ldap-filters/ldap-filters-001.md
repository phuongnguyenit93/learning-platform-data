# Search filter và cú pháp biểu thức LDAP

Trong dịch vụ thư mục LDAP, **search filter** là biểu thức cho biết một entry phải thỏa điều kiện nào để được coi là phù hợp với truy vấn. Khi ứng dụng dùng **Spring LDAP** để tìm nhân viên, nhóm, email hoặc tài khoản, filter giúp giới hạn dữ liệu cần lấy; nếu dựng filter sai, ứng dụng có thể trả kết quả thiếu, truy vấn quá rộng hoặc gặp **LDAP injection**.

Bài thuộc chương **Filter LDAP** của module **SPRING_LDAP**. Sau bài học, người học có thể đọc và viết biểu thức filter theo cú pháp chuẩn, kết hợp điều kiện AND/OR/NOT, chọn phép so khớp phù hợp, escape giá trị đầu vào và thực hiện tìm kiếm bằng `LdapTemplate` cùng `LdapQueryBuilder`. Đây cũng là nền tảng để làm việc với `ContextSource`, `LdapClient`, LDAP ODM, xác thực và kiểm thử truy cập thư mục an toàn.

## 1. Filter nằm ở đâu trong một truy vấn LDAP?

Một yêu cầu tìm kiếm LDAP không chỉ gồm filter. Client cần xác định đồng thời **điểm bắt đầu**, **phạm vi duyệt**, **điều kiện khớp** và **các thuộc tính trả về**:

| Thành phần | Vai trò | Giá trị minh họa |
| --- | --- | --- |
| **Base DN** | Entry gốc của vùng muốn tìm | `ou=people,dc=example,dc=org` |
| **Search scope** | Tìm chính base, con trực tiếp hay toàn bộ cây con | `BASE`, `ONELEVEL`, `SUBTREE` |
| **Search filter** | Điều kiện quyết định entry nào khớp | `(&(objectClass=inetOrgPerson)(uid=linh))` |
| **Requested attributes** | Thuộc tính yêu cầu server trả về | `uid`, `cn`, `mail` |
| **Giới hạn truy vấn** | Giới hạn thời gian, số kết quả và chính sách tìm kiếm | Size limit, time limit; tùy client/server |

Ví dụ mong muốn: tìm người dùng có `uid=linh` trong nhánh nhân viên và chỉ lấy `cn`, `mail`.

~~~text
Base DN:    ou=people,dc=example,dc=org
Scope:      SUBTREE
Filter:     (&(objectClass=inetOrgPerson)(uid=linh))
Attributes: cn, mail
~~~

Để hình dung, đây là lệnh `ldapsearch` minh họa (giả sử môi trường đã cấu hình truststore và có tài khoản tra cứu):

~~~bash
ldapsearch -H ldaps://directory.example.org:636 \
  -x -D "cn=app-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=linh))" cn mail
~~~

`-W` yêu cầu nhập mật khẩu theo cách tương tác; tránh ghi mật khẩu trực tiếp trên dòng lệnh. `ldaps://` chỉ là địa chỉ mẫu, cần kiểm tra chứng chỉ TLS khi chạy thực tế.

**Filter không thay thế base hoặc scope.** `(uid=linh)` dưới `ou=people` và cùng filter đó dưới `ou=groups` có thể trả kết quả khác nhau. Một filter đúng cú pháp vẫn có thể không trả entry nào nếu base DN, quyền đọc, search scope hoặc schema không phù hợp.

## 2. Dữ liệu mẫu để diễn giải filter

Giả sử thư mục có hai entry nhân viên:

~~~ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
ou: Engineering
employeeType: permanent

dn: uid=mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Mai Tran
sn: Tran
ou: Support
employeeType: contractor
~~~

Bản ghi `linh` có email; bản ghi `mai` chưa có thuộc tính `mail`. Các entry cha như `dc=example,dc=org` và `ou=people,...` được giả định đã tồn tại. Đây là dữ liệu học tập, không phải LDIF hoàn chỉnh để nạp vào mọi máy chủ.

Khi đánh giá filter, LDAP sử dụng **attribute type** và **matching rule** do schema quy định. Một thuộc tính có thể có nhiều giá trị; ví dụ thuộc tính số điện thoại có thể chứa nhiều số. Đối với so khớp bằng (`=`), kết quả đúng khi **ít nhất một giá trị** của thuộc tính thỏa matching rule tương ứng.

Điều này khác phép so sánh chuỗi tùy ý trong Java: không được tự mặc định mọi thuộc tính đều phân biệt chữ hoa/thường, hỗ trợ tìm gần đúng hoặc so sánh theo số. Schema và khả năng của server mới quyết định hành vi.

## 3. Cấu trúc cơ bản của biểu thức filter

Dạng văn bản của LDAP search filter được mô tả trong **RFC 4515**. Phần đơn giản nhất là một điều kiện nằm trong dấu ngoặc đơn:

~~~text
(attribute=assertionValue)
~~~

Ví dụ:

~~~ldap
(uid=linh)
(cn=Linh Nguyen)
(mail=*)
~~~

Các thành phần quan trọng:

- **Attribute description:** tên thuộc tính do schema định nghĩa, ví dụ `uid`, `cn`, `mail`, `objectClass`.
- **Toán tử/matching syntax:** xác định kiểu điều kiện, ví dụ `=`, `>=`, `<=`, `~=`.
- **Assertion value:** giá trị được đem ra so khớp với thuộc tính; có quy tắc escape riêng.
- **Dấu ngoặc:** mỗi filter hoàn chỉnh đều được bao bởi `(` và `)`.

Biểu thức lồng nhau cũng là một filter hoàn chỉnh:

~~~text
(&(objectClass=inetOrgPerson)(uid=linh))
~~~

Không viết theo cú pháp SQL như `uid = 'linh' AND mail IS NOT NULL`; LDAP không dùng cú pháp đó. Filter dạng văn bản cũng không phải DN hay LDAP URL.

## 4. Những kiểu điều kiện quan trọng

| Kiểu | Cú pháp | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| **Equality** | `(attr=value)` | Giá trị thuộc tính khớp theo matching rule bằng | `(uid=linh)` |
| **Presence** | `(attr=*)` | Entry có thuộc tính đó | `(mail=*)` |
| **Substring** | `(attr=part*)`, `(attr=*part*)` | So khớp phần đầu/cuối/giữa theo matching rule chuỗi con | `(cn=Li*)` |
| **Greater or equal** | `(attr>=value)` | So sánh lớn hơn hoặc bằng theo ordering matching rule | `(employeeNumber>=1000)` |
| **Less or equal** | `(attr<=value)` | So sánh nhỏ hơn hoặc bằng theo ordering matching rule | `(employeeNumber<=2000)` |
| **Approximate** | `(attr~=value)` | So khớp gần đúng nếu server/schema hỗ trợ | `(cn~=Linh Nguyen)` |
| **Extensible match** | `(attr:rule:=value)` | Chọn matching rule được server hỗ trợ | `(cn:2.5.13.2:=linh nguyen)` |
| **AND** | `(&(f1)(f2))` | Các filter con cùng khớp | `(&(uid=linh)(mail=*))` |
| **OR** | `(|(f1)(f2))` | Ít nhất một filter con khớp | `(|(uid=linh)(uid=mai))` |
| **NOT** | `(!(f))` | Phủ định kết quả của một filter con | `(!(uid=linh))` |

Trong bảng, `f1` và `f2` đại diện cho các filter có đủ dấu ngoặc. Các phép so sánh thứ tự và gần đúng **không được bảo đảm hỗ trợ** cho mọi thuộc tính; việc dùng phép so sánh phải dựa vào schema/matching rule.

### 4.1. Equality và presence

~~~ldap
(uid=linh)
(mail=*)
(&(objectClass=inetOrgPerson)(mail=*))
~~~

Với dữ liệu mẫu:

- `(uid=linh)` khớp entry Linh.
- `(mail=*)` khớp Linh, không khớp Mai vì Mai không có thuộc tính `mail`.
- `(&(objectClass=inetOrgPerson)(mail=*))` chọn các entry thuộc lớp `inetOrgPerson` có `mail`.

**Presence không có nghĩa giá trị khác chuỗi rỗng theo cách kiểm tra của ứng dụng**. Nó là phép kiểm tra thuộc tính hiện diện theo semantics của LDAP. Ngoài ra, ACL có thể ảnh hưởng dữ liệu client được nhìn thấy.

### 4.2. Substring: dấu `*` là wildcard khi đặt đúng vị trí

~~~ldap
(cn=Li*)
(cn=*Nguyen)
(cn=*inh*)
(mail=*@example.org)
~~~

Bốn dòng trên minh họa **bốn filter riêng**: tên bắt đầu bằng `Li`, kết thúc bằng `Nguyen`, chứa `inh` hoặc email có hậu tố `@example.org`. Với `cn=Linh Nguyen`, cả ba ví dụ về `cn` có thể phù hợp nếu matching rule chuỗi con của thuộc tính cho phép.

`*` được hiểu là wildcard trong substring filter. Còn `(mail=*)` là dạng **presence**, không phải truy vấn tìm chuỗi `*` trong email. Để tìm dấu sao **theo nghĩa ký tự thật**, phải escape (`\2a`), ví dụ `(uid=an\2ab)` tương ứng một giá trị `uid` chứa ký tự `*`.

Tìm chuỗi con với wildcard ở đầu như `(cn=*inh*)` có thể tốn tài nguyên trên thư mục lớn tùy chỉ mục và cấu hình server. Không tự động mở rộng tìm kiếm toàn cây khi người dùng chỉ cần một OU cụ thể.

### 4.3. So sánh thứ tự, gần đúng và matching rule

~~~ldap
(employeeNumber>=1000)
(employeeNumber<=2000)
(cn~=Linh Nguyen)
(cn:2.5.13.2:=linh nguyen)
~~~

**Cần hiểu đúng tính tương thích:**

- `>=` và `<=` dùng **ordering matching rule** của thuộc tính, không đồng nghĩa Java tự ép kiểu giá trị thành số. Ngay cả thuộc tính có hình thức số, cách sắp xếp tùy schema.
- `~=` chỉ có ý nghĩa khi server hỗ trợ **approximate matching**; kết quả và cách tính “gần giống” có thể khác nhau giữa triển khai.
- `:2.5.13.2:=` minh họa **extensible matching** với OID của `caseIgnoreMatch`. Server phải hỗ trợ matching rule và việc dùng rule đó cho thuộc tính liên quan; nếu không, yêu cầu có thể không được xử lý như mong đợi.
- Cách so khớp chữ hoa/thường, Unicode, khoảng trắng hoặc chuẩn hóa ký tự thường do **matching rule**, không phải do filter mặc định.

Ví dụ `(cn:2.5.13.2:=linh nguyen)` dùng cú pháp extensible match. Với thuộc tính/chế độ thích hợp, dấu `:dn` cũng có thể xuất hiện trong phần khai báo để chỉ sự tham gia của thuộc tính từ DN vào phép matching. Đây là tính năng nâng cao, cần tài liệu schema/server trước khi dùng.

### 4.4. AND, OR, NOT và nhóm biểu thức

Toán tử logic đứng **ngay sau dấu ngoặc mở**, và mỗi nhánh con cũng phải nằm trong ngoặc:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=linh))
(|(uid=linh)(uid=mai))
(!(employeeType=contractor))
~~~

Có thể lồng các toán tử:

~~~ldap
(&(objectClass=inetOrgPerson)
  (|(ou=Engineering)(ou=Support))
  (mail=*)
  (!(employeeType=contractor)))
~~~

Dòng xuống và khoảng trắng trong mẫu nhiều dòng trên chỉ để **trình bày**; khi gửi request, hãy tạo **một filter liền mạch** không chứa khoảng trắng/chú thích bổ sung ngoài giá trị assertion:

~~~ldap
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=Support))(mail=*)(!(employeeType=contractor)))
~~~

Filter này tìm entry `inetOrgPerson` thuộc một trong hai OU nghiệp vụ, **có email** và **không có `employeeType=contractor`**. Với dữ liệu mẫu, Linh khớp còn Mai không khớp.

**Lưu ý về NOT và thuộc tính thiếu:** `(!(employeeType=contractor))` không có nghĩa chắc chắn rằng thuộc tính `employeeType` tồn tại và mang giá trị khác `contractor`. Nếu nghiệp vụ chỉ áp dụng cho entry có thuộc tính, thêm điều kiện presence:

~~~ldap
(&(employeeType=*)(!(employeeType=contractor)))
~~~

Đối với thuộc tính đa trị, phủ định một equality filter cũng cần diễn giải cẩn thận: `(!(memberOf=X))` có nghĩa **không có giá trị nào của thuộc tính được so khớp là X**; điều kiện này không đòi hỏi thuộc tính phải hiện diện. Nếu nghiệp vụ chỉ xét entry có `memberOf`, cần kết hợp thêm `(memberOf=*)`.

## 5. Escaping và LDAP injection

Đây là phần quan trọng nhất khi filter có dữ liệu do người dùng nhập. **Không ghép giá trị đầu vào trực tiếp** vào filter:

~~~java
// KHÔNG AN TOÀN: giá trị uid từ HTTP request được nối thẳng vào filter.
String filter = "(&(objectClass=inetOrgPerson)(uid=" + uid + "))";
~~~

Nếu `uid` nhận giá trị `*)(uid=*`, filter được tạo trở thành:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=*)(uid=*))
~~~

Thay vì chỉ tìm một tài khoản, truy vấn sẽ khớp **mọi entry thuộc lớp yêu cầu có thuộc tính uid**. Đây là ví dụ về **LDAP injection**, khi dữ liệu không tin cậy làm thay đổi **cấu trúc biểu thức**.

### 5.1. Các ký tự phải escape trong assertion value

Trong cú pháp chuỗi filter của RFC 4515, những ký tự sau có ý nghĩa đặc biệt và phải được biểu diễn bằng `\HH` (hai chữ số hex) nếu muốn tìm **ký tự literal**:

| Ký tự trong giá trị | Biểu diễn trong filter | Giải thích |
| --- | --- | --- |
| `*` | `\2a` | Không bị hiểu là wildcard |
| `(` | `\28` | Không mở nhóm điều kiện |
| `)` | `\29` | Không đóng nhóm điều kiện |
| `\` | `\5c` | Không khởi đầu escape tùy ý |
| NUL (byte `0x00`) | `\00` | Ký tự NUL không được viết trực tiếp |

Ví dụ:

~~~ldap
(uid=an\2ab)
(cn=Ha \28Support\29)
(description=path\5cdev)
~~~

Các ví dụ lần lượt biểu diễn `uid` chứa dấu sao literal (`an*b`), `cn` có giá trị `Ha (Support)` và `description` chứa dấu gạch chéo ngược giữa `path` và `dev`. Dạng `\HH` biểu diễn **byte UTF-8**; với dữ liệu Unicode, dùng API xử lý đúng encoding thay vì tự cắt chuỗi theo ký tự rồi đoán mã hex.

**Đừng lẫn với DN escaping.** Chẳng hạn, dấu phẩy `,` phải được escape khi là một phần của giá trị RDN trong DN (ví dụ `cn=Nguyen\, Linh,ou=people`), nhưng dấu phẩy **không có ý nghĩa ngăn cách điều kiện trong search filter**. Cú pháp DN thuộc RFC 4514, cú pháp filter thuộc RFC 4515.

### 5.2. Sử dụng API tạo filter của Spring LDAP

Spring LDAP có các lớp dựng filter như `EqualsFilter`, `AndFilter`, `OrFilter`. Chúng giúp biểu diễn cấu trúc và escape giá trị đúng cách.

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

public final class SafeEmployeeFilter {
    private SafeEmployeeFilter() {}

    public static String byUid(String uid) {
        AndFilter filter = new AndFilter();
        filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        filter.and(new EqualsFilter("uid", uid));
        return filter.encode();
    }
}
~~~

Với một `uid` như `*)(uid=*`, giá trị được mã hóa làm **giá trị literal**, không được phép biến thành điều kiện LDAP mới.

Với bộ lọc có **tên thuộc tính chọn động**, chỉ cho phép chọn từ một danh sách tên thuộc tính cố định như `uid`, `mail`, `cn`. Escaping giá trị không thay thế việc kiểm soát **attribute description**, **base DN**, **scope** hoặc matching rule do client chọn.

Nếu cần wildcard có chủ đích (ví dụ người dùng tìm tên bắt đầu bằng một tiền tố), phải phân biệt **ký tự wildcard do ứng dụng thêm vào** với **dấu `*` trong dữ liệu của người dùng**. Dùng filter builder hỗ trợ substring và quy tắc escape phù hợp; đừng nối chuỗi wildcard với input chưa được xử lý.

## 6. Tìm kiếm bằng `LdapTemplate` và `LdapQueryBuilder`

Trong Spring LDAP, `LdapContextSource` cấu hình cách tạo kết nối tới thư mục và base DN, `LdapTemplate` thực hiện thao tác với entry, còn `LdapQueryBuilder` cho phép biểu diễn điều kiện truy vấn có cấu trúc. `LdapClient` cung cấp kiểu API fluent trong các phiên bản có hỗ trợ, trong khi LDAP ODM giúp ánh xạ entry thành đối tượng; **cả ba vẫn tuân theo semantics của LDAP filter trên server**.

Ví dụ service tìm nhân viên theo `uid`:

~~~java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public class EmployeeDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findDisplayNames(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attributes -> {
                    Attribute cn = attributes.get("cn");
                    return cn == null ? null : (String) cn.get();
                });
    }
}
~~~

Ví dụ giả định `LdapContextSource` đã đặt base DN `dc=example,dc=org`, nên `ou=people` trong query là **DN tương đối**. Điều kiện `.is(uid)` dùng query API để mã hóa giá trị cần so khớp; code không ghép input vào filter raw. Trong ứng dụng thực tế cần định nghĩa DTO và xử lý trường hợp thuộc tính bị ẩn hoặc vắng mặt, kết quả không duy nhất, lỗi kết nối/ACL và giới hạn truy vấn.

**Các lưu ý cho code thực tế:**

1. Dùng API dựng DN (`LdapNameBuilder` hoặc `LdapName`) nếu base/DN có giá trị động; dựng filter và dựng DN là hai bước khác nhau.
2. Khi không cần toàn bộ cây, thu hẹp base và scope; xem xét limit và timeout phù hợp với lưu lượng.
3. Đặt tài khoản tra cứu ở quyền tối thiểu và sử dụng LDAPS hoặc StartTLS với kiểm tra chứng chỉ.
4. Không dựa vào filter để thay cho **phân quyền**. Ví dụ filter chỉ trả người dùng thuộc OU không chứng minh người đang gọi API có quyền đọc mọi hồ sơ trong OU đó.
5. Không kết luận đăng nhập thành công chỉ vì tìm thấy entry: xác thực cần một cơ chế như LDAP bind hoặc IdP, sau đó mới kiểm tra quyền nghiệp vụ.

### 6.1. Sử dụng `LdapTemplate` với Filter object

Nếu cần tự kết hợp nhiều nhóm điều kiện, có thể tạo filter rõ ràng rồi truyền `encode()` vào `LdapTemplate.search`:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

public class EmployeeLookup {
    private final LdapTemplate ldapTemplate;

    public EmployeeLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUid(String uid) {
        AndFilter filter = new AndFilter();
        filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        filter.and(new EqualsFilter("uid", uid));

        return ldapTemplate.search(
                "ou=people",
                filter.encode(),
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("uid").get());
    }
}
~~~

Ở đây `filter.encode()` tạo biểu thức có cấu trúc và escape assertion value. Ví dụ giả định server trả được thuộc tính `uid`. Đối với dữ liệu thiếu hoặc lỗi truy cập, ứng dụng cần xử lý rõ ràng thay vì trả kết quả sai lệch.

Một số ứng dụng cần tự dùng filter thô, chẳng hạn tương tác với một matching rule đặc thù của máy chủ. Khi đó, **chỉ cố định phần cấu trúc đã kiểm chứng** và mã hóa mọi giá trị không tin cậy bằng API phù hợp trước khi lắp vào biểu thức.

## 7. Quy trình tạo filter từ yêu cầu nghiệp vụ

Giả sử trang quản trị có chức năng “Tìm nhân viên đang làm việc, thuộc Engineering hoặc Support, đã có email”. Thay vì viết ngay một chuỗi filter dài, chuyển yêu cầu thành từng điều kiện:

| Yêu cầu | Điều kiện filter |
| --- | --- |
| Là nhân viên | `(objectClass=inetOrgPerson)` |
| Loại nhân viên là permanent | `(employeeType=permanent)` |
| Thuộc Engineering hoặc Support | `(|(ou=Engineering)(ou=Support))` |
| Có email | `(mail=*)` |

Ghép bằng AND:

~~~ldap
(&(objectClass=inetOrgPerson)(employeeType=permanent)(|(ou=Engineering)(ou=Support))(mail=*))
~~~

Sơ đồ xử lý:

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ"] --> B["Chọn base DN và search scope"]
    B --> C["Xác định thuộc tính theo schema"]
    C --> D["Chọn equality, presence, substring hoặc phép so khớp được hỗ trợ"]
    D --> E["Dựng filter qua API, escape input"]
    E --> F["Thực hiện search qua TLS với tài khoản ít quyền"]
    F --> G["Xử lý entry, giới hạn, partial result và lỗi"]
~~~

Giới hạn kết quả, phân trang hoặc sắp xếp (nếu server hỗ trợ control tương ứng) là những quyết định riêng với cú pháp filter. Một filter đúng vẫn có thể tốn tài nguyên nếu tìm quá rộng hay dùng substring không có chỉ mục hỗ trợ.

## 8. Những lỗi hay gặp

| Biểu hiện | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Filter bị từ chối vì sai cú pháp | Thiếu dấu ngoặc, viết AND như SQL, escape sai | Xây filter qua API và kiểm tra biểu thức cuối cùng |
| `(mail=*)` trả ít kết quả hơn dự kiến | Một số entry thiếu `mail`; ACL/schema có thể ảnh hưởng | Kiểm tra presence, dữ liệu mẫu và quyền đọc |
| `(cn=li*)` không giống tìm chuỗi Java | Matching rule, chuẩn hóa hoặc server/index khác kỳ vọng | Xem schema và kiểm thử cùng loại LDAP server |
| `(uid=abc*)` trả nhiều tài khoản ngoài ý muốn | `*` là wildcard | Dùng equality khi cần khớp chính xác; escape `*` nếu là ký tự literal |
| Truy vấn trả quá nhiều entry | Base/scope quá rộng, bỏ sót điều kiện lọc, injection | Thu hẹp vùng tìm, dùng builder, giới hạn số kết quả |
| `(!(employeeType=contractor))` vẫn khớp entry thiếu thuộc tính | Phủ định không đồng nghĩa có giá trị thay thế | Kết hợp `(employeeType=*)` khi cần |
| `>=`, `<=`, `~=` không hoạt động như dự đoán | Thuộc tính không có matching rule phù hợp hoặc server không hỗ trợ | Kiểm tra schema và chọn phép so khớp được hỗ trợ |
| Kết quả rỗng nhưng entry tồn tại | Base/scope, DN, quyền đọc, alias/referral hoặc filter sai | Tách từng yếu tố; kiểm thử filter đơn trước |
| Java nhận lỗi kết nối hoặc partial result | Vấn đề TLS, timeout, referral hoặc giới hạn server | Phân loại lỗi, không coi là “không tìm thấy” |
| Truy vấn chậm trên nhiều OU | Filter quá rộng, nhiều OR hoặc substring có wildcard đầu | Tối ưu base/scope/index theo số liệu thực tế |

Không chuyển mọi ngoại lệ thành danh sách rỗng: điều đó khiến “không tìm thấy” và “không truy cập được dữ liệu” trở nên không phân biệt. Khi debug, ghi nhận filter đã mã hóa và thông tin truy vấn ở mức phù hợp nhưng không đưa credential hoặc dữ liệu cá nhân nhạy cảm vào log.

## 9. Bài thực hành kiểm thử filter

Sử dụng một LDAP server thử nghiệm có schema và các entry mẫu như mục 2. Bạn có thể bắt đầu bằng một công cụ LDAP client hoặc `ldapsearch`, sau đó chuyển sang `LdapTemplate`. Không chạy lệnh trên máy chủ sản xuất khi chưa có quyền và giới hạn truy vấn phù hợp.

| Bài kiểm tra | Filter | Kết quả kỳ vọng với dữ liệu mẫu |
| --- | --- | --- |
| Tìm đúng Linh | `(uid=linh)` | Chỉ Linh |
| Tìm hai người | `(|(uid=linh)(uid=mai))` | Linh và Mai |
| Có email | `(mail=*)` | Linh |
| Có loại permanent | `(&(objectClass=inetOrgPerson)(employeeType=permanent))` | Linh |
| Thuộc Support | `(ou=Support)` | Mai |
| Không phải contractor và có loại nhân viên | `(&(employeeType=*)(!(employeeType=contractor)))` | Linh |
| Khớp prefix uid | `(uid=li*)` | Linh |
| UID có ký tự sao literal | `(uid=an\2ab)` | Không khớp hai entry mẫu |
| Input injection thử nghiệm | Giá trị `*)(uid=*` đưa vào `EqualsFilter` | Không biến thành filter rộng; tìm giá trị literal |

**Kịch bản kiểm thử bằng Spring LDAP:**

1. Chuẩn bị dữ liệu LDAP thử nghiệm và cấu hình `ContextSource` dùng TLS hoặc endpoint thử nghiệm được cô lập.
2. Với mỗi filter, đặt **cùng base DN và scope**, tránh thay đổi nhiều biến đồng thời.
3. Thực hiện truy vấn trực tiếp, kiểm tra DN và thuộc tính nhận được; đối chiếu các mục trên.
4. Thử giá trị chứa `*`, `(`, `)`, `\` và Unicode qua `EqualsFilter`/`LdapQueryBuilder`; bảo đảm không làm thay đổi cấu trúc filter.
5. Kiểm tra trạng thái không có kết quả, thuộc tính thiếu, tài khoản thiếu quyền, timeout và referral để phân biệt lỗi hạ tầng với “không khớp”.
6. Kiểm thử hiệu năng trên khối dữ liệu đại diện trước khi đưa substring hoặc OR filter diện rộng vào hệ thống thực tế.

**Không chỉ dùng mock để xác nhận matching rule.** Mock có thể kiểm tra application code đã truyền filter đúng, nhưng hành vi so khớp, ACL, index và hỗ trợ matching rule phải được xác minh trên một LDAP server thật thuộc loại sẽ triển khai.

## 10. Câu hỏi tự đánh giá

**Câu 1.** Khác biệt giữa `(mail=*)` và `(mail=\2a)` là gì?

**Đáp án:** `(mail=*)` hỏi thuộc tính `mail` có hiện diện không; `(mail=\2a)` yêu cầu giá trị literal `*`. Dấu `*` đã escape không còn là wildcard.

**Câu 2.** Muốn tìm tài khoản có `uid` là `linh` hoặc `mai` thì biểu thức nào đúng?

**Đáp án:** `(|(uid=linh)(uid=mai))`.

**Câu 3.** Vì sao `(!(employeeType=contractor))` không tương đương câu SQL “employeeType khác contractor và có giá trị”?

**Đáp án:** LDAP filter không mặc định bắt thuộc tính tồn tại khi phủ định. Nếu yêu cầu loại bỏ cả entry thiếu thuộc tính, phải thêm `(employeeType=*)` và xét matching rule của schema.

**Câu 4.** Có thể ghép `uid` từ HTTP request vào `"(&(objectClass=inetOrgPerson)(uid=" + uid + "))"` không?

**Đáp án:** Không. Dữ liệu chứa `*` hoặc dấu ngoặc có thể làm thay đổi cấu trúc filter và mở rộng kết quả. Dùng `EqualsFilter` hoặc `LdapQueryBuilder.where("uid").is(uid)` để mã hóa assertion value.

**Câu 5.** Một filter chính xác đã đủ để xác thực và phân quyền người dùng chưa?

**Đáp án:** Chưa. Filter chỉ giúp chọn entry trong search. Xác thực cần quy trình kiểm tra danh tính (ví dụ LDAP bind hoặc IdP), và phân quyền là quyết định riêng dựa trên chính sách của ứng dụng/hệ thống.

**Điểm cần ghi nhớ:** Hãy luôn phân tách **base DN và scope** (tìm ở đâu), **search filter** (entry nào khớp), **requested attributes** (cần đọc gì) và **quyền truy cập** (được phép nhận gì). Đối với mọi giá trị đầu vào động, dùng API dựng filter có escaping thay vì nối chuỗi LDAP thủ công.
