# Cấu trúc bộ lọc LDAP và biểu thức so khớp thuộc tính

Trong **Spring Data LDAP**, ứng dụng Java thường cần tìm những entry thỏa điều kiện, chẳng hạn tài khoản có `uid` cụ thể, người dùng thuộc một phòng ban hoặc entry có địa chỉ email. LDAP biểu diễn các điều kiện đó bằng **search filter**: một biểu thức có cú pháp riêng, được máy chủ thư mục đánh giá dựa trên thuộc tính và schema của entry.

Bài này tập trung vào cách đọc, viết, kết hợp và sử dụng bộ lọc LDAP đúng và an toàn. Sau khi học, bạn có thể:

- Phân biệt **DN**, **search base**, **search scope** và **filter** trong một truy vấn LDAP.
- Đọc cấu trúc ngoặc lồng nhau, các toán tử `&`, `|`, `!` và những kiểu so khớp thuộc tính.
- Hiểu vai trò của `objectClass`, schema, matching rule và trường hợp thuộc tính không tồn tại.
- Tránh LDAP filter injection khi nhận giá trị từ người dùng; áp dụng filter qua `LdapTemplate` và repository của Spring Data LDAP.

## 1. Filter nằm ở đâu trong một phép tìm kiếm LDAP?

Giả sử thư mục có các entry như sau:

```text
dc=example,dc=org
└── ou=people
    ├── uid=lan,ou=people,dc=example,dc=org
    │   objectClass: inetOrgPerson
    │   uid: lan
    │   cn: Nguyen Thi Lan
    │   mail: lan@example.org
    └── uid=minh,ou=people,dc=example,dc=org
        objectClass: inetOrgPerson
        uid: minh
        cn: Tran Van Minh
```

Một phép tìm kiếm LDAP có ba thành phần cần phân biệt:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Search base** | DN gốc nơi bắt đầu tìm | `ou=people,dc=example,dc=org` |
| **Search scope** | Tìm tại chính base (`OBJECT`), con trực tiếp (`ONELEVEL`) hoặc toàn bộ cây con (`SUBTREE`) | `SUBTREE` |
| **Search filter** | Điều kiện entry phải thỏa | `(&(objectClass=inetOrgPerson)(uid=lan))` |

**DN (Distinguished Name)** là định danh vị trí của entry trong cây thư mục; `uid=lan,ou=people,dc=example,dc=org` là một DN. Trong khi đó, `(uid=lan)` là **filter** kiểm tra giá trị thuộc tính `uid`. Cả hai có thể nhắc tới `uid`, nhưng không thay thế cho nhau. Filter chỉ xét những entry thuộc phạm vi search base và search scope đã chọn; nó không tự quyết định ứng dụng tìm ở nhánh thư mục nào.

## 2. Cấu trúc cú pháp của LDAP filter

Theo cú pháp chuỗi filter của LDAP (RFC 4515), một filter đầy đủ luôn có **cặp ngoặc tròn bao ngoài**. Bên trong là biểu thức so khớp đơn hoặc một phép kết hợp các filter con:

```text
filter := '(' filter-component ')'

filter-component := item
                  | '&' filter filter ...
                  | '|' filter filter ...
                  | '!' filter

item := phép-so-khớp-thuộc-tính
```

Đây là lược đồ dễ đọc, không phải toàn bộ văn phạm RFC. Những điểm cần nhớ:

- Mỗi điều kiện đơn có dạng `(thuộcTính toánTử giáTrị)`, chẳng hạn `(uid=lan)`.
- `&` là **AND**: mọi filter con phải thỏa. `|` là **OR**: ít nhất một filter con phải thỏa. Cả hai nhận một hoặc nhiều filter con.
- `!` là **NOT** và nhận **đúng một** filter con; muốn phủ định nhóm điều kiện, đặt cả nhóm trong ngoặc, ví dụ `(!(|(uid=lan)(uid=minh)))`.
- Dấu ngoặc của từng filter con là bắt buộc. Ví dụ `(&(uid=lan)(mail=*))` hợp lệ, còn `(uid=lan AND mail=*)` không phải cú pháp filter LDAP.

Có thể xem filter như cây biểu thức:

```text
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=QA)))

AND
├── objectClass = inetOrgPerson
└── OR
    ├── ou = Engineering
    └── ou = QA
```

Filter trên chọn entry thuộc `inetOrgPerson` và có giá trị `ou` là `Engineering` hoặc `QA`, nếu những thuộc tính và giá trị này được schema của thư mục hỗ trợ.

## 3. Các phép so khớp thuộc tính

| Cú pháp | Tên phép so khớp | Ví dụ | Cách hiểu |
| --- | --- | --- | --- |
| `(attr=value)` | Equality | `(uid=lan)` | Thuộc tính có giá trị bằng `lan` theo matching rule của schema |
| `(attr=*)` | Presence | `(mail=*)` | Entry có thuộc tính `mail` |
| `(attr=prefix*)` | Substring | `(cn=Nguyen*)` | Một giá trị `cn` bắt đầu bằng `Nguyen` |
| `(attr=*part*)` | Substring | `(mail=*@example.org)` | Một giá trị `mail` kết thúc bằng `@example.org` |
| `(attr=pre*mid*end)` | Substring | `(cn=Nguyen*Van*An)` | Các đoạn xuất hiện theo đúng thứ tự |
| `(attr>=value)` | Greater or equal | `(employeeNumber>=1000)` | So khớp lớn hơn hoặc bằng theo ordering rule của thuộc tính |
| `(attr<=value)` | Less or equal | `(employeeNumber<=2000)` | So khớp nhỏ hơn hoặc bằng theo ordering rule |
| `(attr~=value)` | Approximate | `(cn~=Nguyen Van An)` | So khớp gần đúng, nếu máy chủ và schema hỗ trợ |
| `(attr:rule:=value)` | Extensible match | `(cn:caseExactMatch:=Nguyen Van An)` | Yêu cầu matching rule cụ thể, nếu máy chủ hỗ trợ |

### 3.1. So khớp bằng và sự khác biệt với so sánh chuỗi trong Java

`(cn=Nguyen Van An)` không nhất thiết tương đương `javaString.equals("Nguyen Van An")`. LDAP dựa vào **equality matching rule** được định nghĩa cho thuộc tính: tùy schema, quy tắc có thể xử lý chữ hoa/chữ thường, khoảng trắng hoặc dạng biểu diễn của giá trị. Ví dụ, `uid` thường có kiểu matching rule khác với một thuộc tính số hay thời gian.

Với thuộc tính có nhiều giá trị, equality filter thành công nếu **ít nhất một giá trị** thỏa phép so khớp. Ví dụ, entry có hai giá trị `memberOf` có thể thỏa `(memberOf=cn=dev,ou=groups,dc=example,dc=org)` khi một giá trị phù hợp. Việc biểu diễn thành viên nhóm và hỗ trợ `memberOf` phụ thuộc từng directory server, nên không mặc định thư mục nào cũng có thuộc tính này.

### 3.2. Presence và substring: dấu `*` không phải lúc nào cũng là ký tự thường

```ldap
(mail=*)               # Có thuộc tính mail
(cn=Lan*)              # Bắt đầu bằng Lan
(cn=*Lan*)             # Chứa Lan
(cn=Lan*Anh)           # Bắt đầu bằng Lan và kết thúc bằng Anh
(cn=Lan\2aAnh)         # Bằng giá trị chứa dấu * thật: Lan*Anh
```

Trong ví dụ trên, `*` không escape là ký hiệu của phép substring, còn `\2a` là cách mã hóa **dấu sao thật**. Riêng `(attr=*)` là presence filter, không có nghĩa tìm thuộc tính bằng chuỗi chỉ gồm một dấu sao.

### 3.3. So khớp thứ tự, gần đúng và mở rộng

`>=` và `<=` **không tự ép chuỗi thành số** như Java. Kết quả phụ thuộc *ordering matching rule* mà server áp dụng cho loại thuộc tính. Nếu một thuộc tính được định nghĩa là chuỗi, đừng mặc định `(attr>=10)` có nghĩa so sánh số nguyên. Một số thuộc tính hoàn toàn không hỗ trợ phép so khớp thứ tự.

`~=` biểu thị approximate match, nhưng mức hỗ trợ và cách đánh giá khác nhau giữa các directory server; có hệ thống không hỗ trợ phép này cho thuộc tính mong muốn. Extensible match có thể chỉ định matching rule bằng tên hoặc OID, ví dụ `(cn:caseExactMatch:=Nguyen Van An)`. Một dạng mở rộng còn có thể chứa `:dn:` để xét các attribute value trong DN theo quy tắc của LDAP. Chỉ sử dụng các quy tắc mà schema và server thực sự công bố.

`objectClass` cũng là một thuộc tính có thể lọc: `(objectClass=inetOrgPerson)` giúp giới hạn kiểu entry. Khi sử dụng bộ lọc này, cần đảm bảo entry được tạo theo schema tương ứng; không nên suy ra mọi entry `person` đều mang `inetOrgPerson`.

## 4. Kết hợp điều kiện bằng AND, OR và NOT

Một số tình huống thực tế:

```ldap
# Chỉ lấy người dùng có uid cụ thể
(&(objectClass=inetOrgPerson)(uid=lan))

# Người dùng thuộc một trong hai bộ phận (nếu entry có thuộc tính ou)
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=QA)))

# Người dùng có email và không mang trạng thái disabled
(&(objectClass=inetOrgPerson)(mail=*)(!(accountStatus=disabled)))

# Phủ định cả nhóm OR
(!(|(uid=lan)(uid=minh)))
```

`accountStatus` trong ví dụ là thuộc tính **giả định**: chỉ dùng nếu schema triển khai định nghĩa nó. Không được dựa vào tên thuộc tính này để suy luận rằng mọi hệ thống LDAP đều lưu trạng thái tài khoản giống nhau.

LDAP có trường hợp phép so khớp **không xác định** (*Undefined*), ví dụ thiếu matching rule phù hợp. Khi đó, đừng suy luận rằng `(!(attr=value))` luôn chọn mọi entry không có thuộc tính `attr`. Nếu muốn lọc riêng những entry không có thuộc tính, hãy biểu diễn tường minh bằng `(!(attr=*))` và kiểm tra hành vi với directory thực tế.

## 5. Giá trị filter phải được escape đúng chuẩn

**LDAP filter injection** xảy ra khi ứng dụng ghép trực tiếp dữ liệu người dùng vào chuỗi filter. Dữ liệu chứa `*`, `(` hoặc `)` có thể thay đổi cấu trúc hoặc ý nghĩa truy vấn.

Theo RFC 4515, những ký tự đặc biệt trong **giá trị** của filter phải được escape bằng dấu `\` theo sau là hai chữ số hex của byte tương ứng:

| Ký tự / byte cần biểu diễn | Dạng escape trong LDAP filter |
| --- | --- |
| Dấu sao `*` | `\2a` |
| Ngoặc mở `(` | `\28` |
| Ngoặc đóng `)` | `\29` |
| Dấu gạch chéo ngược `\` | `\5c` |
| Byte NUL (`0x00`) | `\00` |

Ví dụ, nếu người dùng nhập chính xác `lan*`, filter bình đẳng phù hợp là `(uid=lan\2a)`. Viết `(uid=lan*)` lại có nghĩa **tìm mọi uid bắt đầu bằng `lan`**. Việc escape một giá trị filter khác với việc escape thành phần của **DN**: hai loại biểu thức có quy tắc riêng, không được dùng chung tùy tiện.

```java
// KHÔNG AN TOÀN: input có thể biến đổi cú pháp filter.
String filter = "(uid=" + userInput + ")";
```

Trong Spring LDAP, nên dùng API xây dựng filter để thư viện xử lý việc mã hóa giá trị:

```java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(new EqualsFilter("uid", userInput));

String encodedFilter = filter.encode();
// Với userInput = "lan*", giá trị * được escape thành \2a.
```

Không tự cộng chuỗi để tạo điều kiện chứa input không tin cậy. Tên thuộc tính, search base và scope cũng cần được lựa chọn hoặc kiểm soát ở phía ứng dụng; escape **giá trị** không đồng nghĩa có thể cho người dùng tùy ý quyết định mọi thành phần truy vấn.

## 6. Sử dụng filter với Spring Data LDAP và LdapTemplate

### 6.1. LdapTemplate: truy vấn chủ động với LdapQueryBuilder

Spring LDAP cung cấp `LdapQueryBuilder` để tách các phần của truy vấn và mã hóa giá trị tìm kiếm an toàn. Ví dụ tìm tên hiển thị của entry có `uid` trùng chính xác với input:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class PersonSearchService {
    private final LdapTemplate ldapTemplate;

    public PersonSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query,
                (AttributesMapper<String>) attributes ->
                        (String) attributes.get("cn").get());
    }
}
```

Ở đây `base("ou=people")` được hiểu trong ngữ cảnh cấu hình LDAP của `LdapTemplate` (thường có một base DN ở mức kết nối). Hai điều kiện `.is(...)` là **equality match**, không phải pattern substring. Ví dụ giả định entry `inetOrgPerson` có thuộc tính bắt buộc `cn` theo schema; với entry loại khác, cần xử lý trường hợp thuộc tính không tồn tại trước khi gọi `.get()`.

Nếu cần giới hạn `ONELEVEL` hay `SUBTREE`, cấu hình search scope bằng API query tương ứng và kiểm tra với cấu trúc cây thực tế. Base, scope và filter cùng quyết định tập kết quả, nên filter đúng vẫn có thể trả về danh sách rỗng nếu search base sai.

### 6.2. Spring Data LDAP repository: truy vấn theo thuộc tính đã ánh xạ

Với mô hình repository, lớp entity ánh xạ thuộc tính LDAP sang field Java; phương thức truy vấn đơn giản có thể được dẫn xuất từ tên method:

```java
import java.util.List;
import javax.naming.Name;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=people", objectClasses = {"inetOrgPerson"})
class Person {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;
    // Getter/setter hoặc cơ chế truy cập tương ứng của entity.
}

interface PersonRepository extends LdapRepository<Person> {
    List<Person> findByUid(String uid);
}
```

`findByUid("lan")` thể hiện mong muốn **so khớp thuộc tính `uid`** của entity trong phạm vi ánh xạ. Việc dựng filter cụ thể do tầng Spring Data LDAP xử lý. Khi cần biểu thức Boolean lồng nhau phức tạp hoặc kiểm soát search base/scope đặc biệt, cân nhắc `LdapTemplate` thay vì ép mọi truy vấn vào tên method repository. Cần đối chiếu khả năng suy diễn query với phiên bản Spring Data LDAP đang sử dụng.

### 6.3. Trường hợp nào chọn công cụ nào?

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Tìm một entry theo `uid` hoặc thuộc tính đã ánh xạ | Repository với phương thức truy vấn theo tên field |
| Kết hợp AND/OR, presence, search base/scope linh hoạt | `LdapQueryBuilder` cùng `LdapTemplate` |
| Cần chủ động dựng cây filter và lấy chuỗi đã encode | Các lớp `EqualsFilter`, `AndFilter`, `OrFilter` trong Spring LDAP |
| Truy vấn do cấu hình nghiệp vụ quyết định | Đặt tên thuộc tính, phép toán, base và scope trong danh sách cho phép; chỉ truyền giá trị qua API an toàn |

## 7. Những lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Filter không hợp lệ | Thiếu ngoặc hoặc `!` có nhiều filter con | Kiểm tra cây biểu thức và từng cặp ngoặc |
| Tìm `uid` chính xác nhưng trả về nhiều entry | Input có `*` không escape nên trở thành substring | Dùng equality builder hoặc `EqualsFilter` |
| Filter hợp lệ nhưng không có kết quả | Sai search base, scope hoặc tên thuộc tính | Kiểm tra DN, phạm vi tìm và schema |
| `>=`, `<=`, `~=` không hoạt động như mong đợi | Server/schema không hỗ trợ matching rule tương ứng | Xác minh định nghĩa thuộc tính và khả năng của directory |
| Kết quả chữ hoa/chữ thường bất ngờ | Matching rule LDAP không giống `String.equals` | Kiểm tra equality rule của thuộc tính |
| Filter dùng `memberOf` không trả kết quả | Thuộc tính hoặc cơ chế nhóm phụ thuộc directory server | Kiểm tra cách server lưu quan hệ nhóm |

Khi thử nghiệm, hãy kiểm tra cả filter **và** search base/scope trong một directory dùng cho phát triển hoặc kiểm thử. Ghi lại input, filter đã mã hóa, DN của những entry mong đợi và kết quả thực tế. Nếu cần ghi log, tránh ghi mật khẩu hay dữ liệu nhạy cảm trong filter và thuộc tính trả về.

## 8. Tự luyện tập

**Bài 1.** Viết filter chọn entry `inetOrgPerson` có email và `uid=lan`.

```ldap
(&(objectClass=inetOrgPerson)(mail=*)(uid=lan))
```

**Bài 2.** Người dùng nhập giá trị `mai*anh` và muốn tìm `cn` **bằng chính chuỗi đó**. So sánh hai filter dưới đây:

```ldap
(cn=mai*anh)       # Substring: mai ... anh
(cn=mai\2aanh)    # Equality: dấu * là một phần của giá trị
```

**Bài 3.** Tìm entry có `objectClass=inetOrgPerson` và `ou` là `Engineering` hoặc `QA`:

```ldap
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=QA)))
```

Với mỗi ví dụ, thử đổi search base từ `ou=people` sang một nhánh khác, rồi so sánh kết quả để thấy rõ sự khác biệt giữa **điều kiện filter** và **vùng dữ liệu được tìm kiếm**.

## 9. Ghi nhớ

- Filter LDAP là biểu thức dạng `(...)`; phép kết hợp dùng `&`, `|`, `!` và các filter con có ngoặc riêng.
- Equality, presence, substring, ordering, approximate và extensible match có ý nghĩa khác nhau; hiệu lực phụ thuộc schema/matching rule.
- Dấu `*` không escape có nghĩa đặc biệt; với giá trị đến từ input, dùng các builder/filter API của Spring LDAP để tránh injection.
- Repository của Spring Data LDAP thuận tiện cho truy vấn theo thuộc tính được ánh xạ; `LdapTemplate` phù hợp khi cần điều khiển filter và phạm vi tìm kiếm chi tiết.

**Tham khảo chuẩn:** RFC 4515 (*Lightweight Directory Access Protocol (LDAP): String Representation of Search Filters*), RFC 4511 (*LDAP: The Protocol*), và tài liệu Spring LDAP / Spring Data LDAP tương ứng với phiên bản dự án.
