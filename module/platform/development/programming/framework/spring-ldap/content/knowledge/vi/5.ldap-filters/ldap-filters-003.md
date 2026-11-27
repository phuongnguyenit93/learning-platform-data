# AND, OR và NOT filter trong LDAP

LDAP cho phép tìm kiếm các entry trong một nhánh thư mục bằng **search filter**. Một điều kiện đơn giản như `(uid=lan)` kiểm tra một thuộc tính; trong ứng dụng thực tế, ta thường cần kết hợp nhiều điều kiện: chỉ lấy tài khoản thuộc một lớp đối tượng nhất định, thuộc một trong vài nhóm phòng ban và loại trừ một tập tài khoản. LDAP cung cấp ba toán tử logic chính cho mục đích này: **AND** (`&`), **OR** (`|`) và **NOT** (`!`).

Trong Spring LDAP, bạn có thể gửi filter qua `LdapTemplate`/`LdapClient` hoặc dùng các lớp dựng filter để xử lý giá trị đầu vào an toàn. Bài học thuộc chương **Filter LDAP** này tập trung vào cú pháp, ý nghĩa, cách lồng điều kiện và những lỗi thường gặp khi đưa bộ lọc vào ứng dụng Spring.

Sau bài học, bạn có thể:

- Đọc và viết đúng cú pháp prefix của AND, OR, NOT trong LDAP filter.
- Xác định entry nào khớp một filter lồng nhau và tránh nhầm với cú pháp SQL/Java.
- Hiểu sự khác biệt giữa `(!(mail=*))` và `(!(mail=foo@example.org))`.
- Dùng filter builder trong Spring LDAP để kết hợp điều kiện, escape giá trị và tránh LDAP filter injection.
- Phân biệt phần việc của **filter**, **search base**, **search scope** và quyền truy cập.

## 1. Bối cảnh: tìm entry trong một nhánh LDAP

Giả sử directory có nhánh `ou=people,dc=example,dc=org` và các entry:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
ou: Engineering
mail: lan@example.org

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Minh Tran
sn: Tran
ou: QA
mail: minh@example.org

dn: uid=guest,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: guest
cn: Guest Account
sn: Account
ou: Engineering
```

Để tìm Lan bằng một điều kiện bằng nhau, ta viết:

```ldap
(uid=lan)
```

Bộ lọc trên là một **assertion**: entry có ít nhất một giá trị `uid` thỏa quy tắc so khớp bằng nhau của loại thuộc tính đó hay không. Nếu chỉ cần entry có attribute `mail`, dùng filter hiện diện:

```ldap
(mail=*)
```

Các toán tử logic sẽ **kết hợp những filter con** như trên. Chúng không thay thế quy tắc so sánh giá trị của từng attribute.

## 2. Cú pháp prefix của AND, OR và NOT

Theo định dạng biểu diễn chuỗi LDAP filter (RFC 4515), mỗi filter nằm trong cặp ngoặc tròn. Toán tử logic nằm **ngay đầu** filter cha, sau đó là các filter con:

| Toán tử | Ký hiệu | Quy tắc |
| --- | --- | --- |
| **AND** | `&` | Khớp khi **tất cả** filter con khớp |
| **OR** | `\|` | Khớp khi **ít nhất một** filter con khớp |
| **NOT** | `!` | Đảo kết quả của **một** filter con |

Ví dụ AND:

```ldap
(&(objectClass=inetOrgPerson)(ou=Engineering))
```

Ví dụ OR:

```ldap
(|(ou=Engineering)(ou=QA))
```

Ví dụ NOT:

```ldap
(!(uid=guest))
```

Trong ví dụ AND, dấu `&` không dùng để ghép văn bản. Hai biểu thức `(objectClass=inetOrgPerson)` và `(ou=Engineering)` đều là filter con hoàn chỉnh. Tương tự, OR phải chứa các filter con có ngoặc.

**Không viết theo dạng infix của Java/SQL:**

```text
(uid=lan AND ou=Engineering)     # Không phải LDAP filter hợp lệ
(uid=lan)||(uid=minh)            # Không phải một LDAP filter hợp lệ
AND((uid=lan),(ou=Engineering))   # Không phải cú pháp LDAP
```

Với các toán tử lồng nhau, **ngoặc thể hiện chính xác cấu trúc cây**, không cần và cũng không có quy tắc ưu tiên AND trước OR như trong một số ngôn ngữ lập trình. NOT luôn áp dụng lên đúng **một filter con**, muốn phủ định nhiều điều kiện phải bọc chúng trong AND hoặc OR.

## 3. AND: mọi điều kiện đều phải khớp

Filter dưới đây chọn những entry có object class phù hợp và thuộc bộ phận Engineering:

```ldap
(&(objectClass=inetOrgPerson)(ou=Engineering))
```

Trên dữ liệu mẫu, Lan và guest có thể khớp; Minh không khớp do `ou=QA`.

Nếu thêm điều kiện hiện diện của email:

```ldap
(&(objectClass=inetOrgPerson)(ou=Engineering)(mail=*))
```

chỉ còn Lan, vì guest không có `mail` trong ví dụ. Một AND có thể có **nhiều filter con**, không giới hạn ở hai điều kiện trong cách viết minh họa.

Hãy đọc AND theo câu tiếng Việt: “Là inetOrgPerson **và** thuộc Engineering **và** có mail.”

> Cú pháp filter không quyết định máy chủ phân loại một entry như thế nào ngoài các quy tắc LDAP thực tế: object class, schema, matching rule, ACL và dữ liệu lưu trữ vẫn ảnh hưởng kết quả.

## 4. OR: chỉ cần một nhánh khớp

Giả sử cần lấy người thuộc Engineering **hoặc** QA:

```ldap
(|(ou=Engineering)(ou=QA))
```

Trên dữ liệu mẫu, cả ba entry có thể khớp vì mỗi entry có một trong hai giá trị `ou`. Trong LDAP, nếu `ou` là thuộc tính nhiều giá trị, một entry có giá trị `Engineering` **và** `QA` cũng có thể khớp OR; không cần xử lý riêng từng phần tử.

Để tìm một trong hai mã tài khoản:

```ldap
(|(uid=lan)(uid=minh))
```

Filter này chỉ khớp Lan hoặc Minh. OR cũng có thể chứa ba điều kiện trở lên:

```ldap
(|(uid=lan)(uid=minh)(uid=guest))
```

**OR không có nghĩa kết quả chỉ được khớp một nhánh.** Nếu một entry đáp ứng cả hai điều kiện, nó vẫn xuất hiện như một entry kết quả của truy vấn, không thành hai bản ghi vì khớp hai nhánh.

## 5. NOT: phủ định đúng một filter con

Để loại trừ tài khoản có `uid=guest`:

```ldap
(!(uid=guest))
```

Đây là NOT của bộ lọc bằng nhau `(uid=guest)`; trên dữ liệu mẫu, Lan và Minh khớp.

Để tìm những entry **không có** attribute `mail`, dùng NOT của phép kiểm tra hiện diện:

```ldap
(!(mail=*))
```

Trong ví dụ, guest khớp điều kiện này.

### Phủ định một giá trị khác với yêu cầu không có thuộc tính

Hai filter sau có ý nghĩa khác nhau:

```ldap
(!(mail=lan@example.org))
```

```ldap
(!(mail=*))
```

Filter thứ nhất có nghĩa “không thỏa phép so khớp `mail=lan@example.org`”. Theo đánh giá thông thường, nó có thể khớp cả entry có email khác **lẫn entry thiếu `mail`**. Filter thứ hai chỉ kiểm tra rằng attribute `mail` không hiện diện. Vì vậy, **NOT equality không tương đương với NOT presence**.

Khi muốn lấy entry **có mail nhưng mail không bằng** `lan@example.org`, hãy viết rõ hai điều kiện:

```ldap
(&(mail=*)(!(mail=lan@example.org)))
```

**Trường hợp attribute có nhiều giá trị:** nếu một entry chứa cả `lan@example.org` và `other@example.org`, filter `(!(mail=lan@example.org))` **không khớp**, bởi điều kiện equality bên trong đã khớp một value. NOT không có nghĩa “tồn tại ít nhất một value khác”; nó phủ định kết quả của filter con trên **toàn entry**.

Theo LDAP, ngoài TRUE/FALSE còn có thể có trạng thái **Undefined** đối với các điều kiện không đánh giá được (ví dụ quy tắc so khớp không được nhận biết trong một số trường hợp). NOT trên Undefined vẫn là Undefined, không tự biến thành TRUE. Vì vậy, không nên coi NOT là một cơ chế bảo đảm lấy mọi entry còn lại trong mọi hoàn cảnh và mọi cấu hình máy chủ.

## 6. Kết hợp nhiều tầng logic

Yêu cầu nghiệp vụ: “Lấy tài khoản thuộc object class `inetOrgPerson`, nằm trong Engineering **hoặc** QA, và **không phải** guest.”

Filter tương ứng:

```ldap
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=QA))(!(uid=guest)))
```

Để dễ đọc, có thể định dạng theo cây (chỉ dùng để giải thích, khi truyền đi vẫn là một chuỗi filter hợp lệ):

```text
AND
├── objectClass = inetOrgPerson
├── OR
│   ├── ou = Engineering
│   └── ou = QA
└── NOT
    └── uid = guest
```

Với ba entry mẫu, Lan và Minh đáp ứng; guest bị loại bởi NOT.

So sánh hai filter có ngoặc khác nhau:

```ldap
(&(|(ou=Engineering)(ou=QA))(mail=*))
```

Ý nghĩa: “(Engineering hoặc QA) **và** có mail”. Lan, Minh khớp; guest không khớp.

```ldap
(|(ou=Engineering)(&(ou=QA)(mail=*)))
```

Ý nghĩa: “Engineering **hoặc** (QA và có mail)”. Trong ví dụ, guest khớp vì thuộc Engineering dù không có mail.

Đây là lý do phải **mô tả nhóm điều kiện rõ ràng trước khi viết filter**, đặc biệt khi kết hợp quyền truy cập hoặc trạng thái tài khoản.

### Luật De Morgan giúp đọc filter có NOT

NOT có thể phủ định **toàn bộ** một nhóm OR hoặc AND:

```ldap
(!(|(ou=Engineering)(ou=QA)))
```

Tương đương về logic với:

```ldap
(&(!(ou=Engineering))(!(ou=QA)))
```

Tương tự:

```ldap
(!(&(mail=*)(uid=guest)))
```

Tương đương về logic với:

```ldap
(|(!(mail=*))(!(uid=guest)))
```

Với phép đánh giá ba trạng thái của LDAP, các phép biến đổi De Morgan này vẫn đúng theo quy tắc logic tương ứng; nhưng kết quả cụ thể phụ thuộc khả năng đánh giá từng điều kiện. **Đừng bỏ ngoặc** khi đổi hoặc rút gọn.

## 7. Tự xây filter an toàn với Spring LDAP

Khi giá trị được nhập từ form hoặc API, tuyệt đối tránh nối trực tiếp chuỗi đầu vào vào filter:

```java
// Không an toàn: userUid do người dùng cung cấp có thể chứa ký tự đặc biệt.
String filter = "(uid=" + userUid + ")";
```

LDAP filter dùng các ký tự có ý nghĩa cú pháp như `*`, `(`, `)` và `\`. Nếu đầu vào có chuỗi chứa ký tự đặc biệt, nối chuỗi thô có thể làm sai cấu trúc điều kiện hoặc dẫn tới **LDAP filter injection**.

Spring LDAP cung cấp các lớp filter builder:

| Lớp | Vai trò |
| --- | --- |
| `EqualsFilter` | Tạo phép so khớp bằng nhau và escape giá trị |
| `PresentFilter` | Kiểm tra sự hiện diện của attribute |
| `AndFilter` | Gom những filter con với AND |
| `OrFilter` | Gom những filter con với OR |
| `NotFilter` | Phủ định một filter con |

Ví dụ dùng `LdapTemplate` và các lớp trong `org.springframework.ldap.filter`:

```java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.NotFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.filter.PresentFilter;

public final class PeopleDirectory {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUsersInEitherDepartment(
            String departmentA, String departmentB) {

        OrFilter departments = new OrFilter();
        departments.or(new EqualsFilter("ou", departmentA));
        departments.or(new EqualsFilter("ou", departmentB));

        AndFilter filter = new AndFilter();
        filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        filter.and(departments);
        filter.and(new NotFilter(new EqualsFilter("uid", "guest")));
        filter.and(new PresentFilter("uid"));

        // ContextSource có base = dc=example,dc=org.
        // Search base chỉ là ou=people, tương đối với ContextSource base.
        return ldapTemplate.search(
            "ou=people",
            filter.encode(),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("uid").get()
        );
    }
}
```

Với `departmentA = "Engineering"` và `departmentB = "QA"`, builder tạo logic tương đương:

```ldap
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=QA))(!(uid=guest))(uid=*))
```

Giải thích:

1. `OrFilter` gom hai phép so khớp bộ phận thành một nhánh OR.
2. `AndFilter` gắn thêm yêu cầu object class, phủ định guest và sự hiện diện `uid`.
3. `EqualsFilter` xử lý escape **giá trị** như `departmentA` và `departmentB` trước khi mã hóa filter. Đây là điểm quan trọng khi dữ liệu đến từ bên ngoài.
4. `filter.encode()` tạo chuỗi filter chuẩn để truyền vào `LdapTemplate.search`.
5. Tham số `"ou=people"` là **search base tương đối** với base context đã cấu hình. Nó xác định nơi tìm, còn filter xác định entry nào khớp.

Ví dụ giả định LDAP server cho phép đọc `uid` và `ou` trong các entry phù hợp. Trong code thực tế, nên kiểm soát null/thuộc tính bị thiếu nếu không có filter hiện diện, mapping kết quả theo cấu trúc dữ liệu ứng dụng và giới hạn kích thước tìm kiếm khi cần.

### Kết hợp AND qua `LdapQueryBuilder`

Nếu chỉ cần các điều kiện liên tiếp đơn giản, Spring LDAP còn hỗ trợ query builder:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

List<String> lanEntries = ldapTemplate.search(
    query().base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("lan"),
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("uid").get()
);
```

Query builder hữu ích khi viết ngắn gọn và escape giá trị. Với bộ lọc lồng nhau phức tạp nhiều tầng AND/OR/NOT, cách dùng `AndFilter`, `OrFilter` và `NotFilter` làm **cấu trúc nhóm** rõ ràng hơn. Đừng ghép các chuỗi filter con bằng toán tử `&&`/`||` của Java.

## 8. Escape giá trị, wildcard và giới hạn của filter builder

Theo RFC 4515, khi muốn đưa các ký tự có ý nghĩa cú pháp vào **giá trị cần so khớp theo nghĩa đen**, cần biểu diễn dưới dạng escape:

| Ký tự trong giá trị | Cách biểu diễn trong filter |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| Dấu gạch chéo ngược `\` | `\5c` |
| Byte NUL | `\00` |

Ví dụ, tên tài khoản chứa dấu sao **thực sự** `lan*` cần so khớp như một giá trị literal:

```ldap
(uid=lan\2a)
```

Trong khi đó:

```ldap
(uid=lan*)
```

là điều kiện substring bắt đầu bằng `lan`, **không phải** phép so khớp bằng giá trị `lan*`. Còn `(uid=*)` chỉ kiểm tra sự hiện diện của thuộc tính.

Khi dùng `new EqualsFilter("uid", userUid)`, builder sẽ escape phần **giá trị**. Nếu cần tìm substring, hãy dùng API tạo substring filter tương ứng với nhu cầu, đừng chèn ký tự wildcard vào đầu vào dành cho equality rồi mong chúng tự mang nghĩa tìm gần đúng.

**Lưu ý bảo mật:** builder thường xử lý escaping giá trị, nhưng bạn vẫn phải **kiểm soát tên attribute và cấu trúc truy vấn**. Đừng chấp nhận tùy ý một tên trường, toán tử, search base hoặc search scope do người dùng truyền vào nếu chính sách ứng dụng không cho phép. Dùng danh sách field hợp lệ (allowlist), giới hạn truy vấn phù hợp và kiểm soát ACL phía server. Escape filter và escape DN là **hai quy tắc khác nhau**, không dùng thay thế cho nhau.

## 9. Filter không quyết định phạm vi hay quyền truy cập

Một truy vấn LDAP có ba yếu tố chính:

| Yếu tố | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Search base** | Bắt đầu tìm từ đâu? | `ou=people,dc=example,dc=org` |
| **Search scope** | Tìm ở một entry, một cấp hay toàn bộ cây con? | `SUBTREE` |
| **Search filter** | Entry nào thỏa điều kiện? | `(&(ou=Engineering)(mail=*))` |

Nếu `ContextSource` của Spring LDAP đặt base `dc=example,dc=org`, thì `LdapTemplate.search("ou=people", ...)` tìm tương đối dưới base đó. Một filter OR dù rất rộng cũng **không tự vượt qua phạm vi search base/scope**.

Mặt khác, filter **không thay thế phân quyền**. Khi tài khoản bind thiếu quyền đọc một entry hoặc attribute, kết quả có thể khác so với truy vấn bằng tài khoản quản trị. Khi sử dụng dữ liệu người dùng trong filter, kết nối phải được bảo vệ bằng TLS (LDAPS hoặc StartTLS được cấu hình chính xác), quyền bind được giới hạn và server cần áp dụng chính sách phân quyền phù hợp.

Về hiệu năng, một filter OR trên nhiều điều kiện có thể làm tăng công việc tìm kiếm, nhất là khi dùng attribute không có index. NOT và substring rộng cũng có thể khó tối ưu. Nếu truy vấn trên tập dữ liệu lớn, đo kiểm trên directory server thực tế, dùng search base đủ hẹp và tham khảo index của server; không suy ra hiệu năng chỉ từ số toán tử trong filter.

## 10. Những lỗi dễ gặp khi viết AND/OR/NOT

| Sai lầm | Cách sửa |
| --- | --- |
| Dùng `AND`/`OR` dạng chữ hoặc `&&`/`||` của Java trong filter | Dùng cú pháp prefix `&`, `\|`, `!` và bao ngoặc các filter con |
| Viết NOT với hai filter con trực tiếp | Dùng NOT phủ định một nhóm AND/OR: `(!(&(a=x)(b=y)))` |
| Nghĩ NOT một giá trị đồng nghĩa không có attribute | Phân biệt `(!(mail=foo@example.org))` với `(!(mail=*))` |
| Muốn mọi entry có email khác `foo`, kể cả khi attribute nhiều giá trị | Xác định rõ nghiệp vụ; `(!(mail=foo))` loại entry có **bất kỳ** value khớp `foo` |
| Bỏ ngoặc vì cho rằng AND được ưu tiên hơn OR | Đặt cấu trúc nhóm rõ ràng như `(&(...)(\|(...)(...)))` |
| Ghép chuỗi filter từ form tìm kiếm | Dùng `EqualsFilter`/query builder và allowlist attribute |
| Dùng `(uid=lan*)` để tìm dấu `*` literal | Escape thành `(uid=lan\2a)` hoặc dùng equality builder |
| Filter đúng nhưng không ra kết quả | Kiểm tra search base, scope, schema, dữ liệu, ACL và matching rule |

## 11. Bài thực hành tự kiểm tra

Hãy dùng ba entry Lan, Minh và guest ở đầu bài. Giả sử search base là `ou=people,dc=example,dc=org`, search scope là subtree và tài khoản có đủ quyền đọc.

**Bài 1.** Filter nào lấy cả Lan và Minh nhưng bỏ guest?

```ldap
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=QA))(!(uid=guest)))
```

**Bài 2.** Filter nào chỉ lấy các entry trong Engineering **có mail**?

```ldap
(&(ou=Engineering)(mail=*))
```

**Bài 3.** Filter nào lấy những entry **không có mail**?

```ldap
(!(mail=*))
```

**Bài 4.** Giải thích sự khác nhau giữa hai filter:

```ldap
(&(|(ou=Engineering)(ou=QA))(mail=*))
```

```ldap
(|(ou=Engineering)(&(ou=QA)(mail=*)))
```

**Bài 5.** Đầu vào `userUid` chứa literal `lan*`. Hãy tạo filter tìm đúng giá trị có dấu sao bằng Spring LDAP:

```java
String userUid = "lan*";
String filter = new EqualsFilter("uid", userUid).encode();
// filter tương đương: (uid=lan\2a)
```

**Đáp án và cách kiểm tra:**

1. Lan và Minh khớp: cả hai là `inetOrgPerson`, thuộc Engineering/QA và không có `uid=guest`.
2. Lan khớp; guest thuộc Engineering nhưng không có `mail` trong dữ liệu mẫu.
3. Guest khớp vì thiếu `mail`.
4. Filter thứ nhất yêu cầu **có mail cho cả hai bộ phận**, nên khớp Lan/Minh. Filter thứ hai cho toàn bộ Engineering đi qua nhánh OR thứ nhất, kể cả guest không có mail; vì vậy khớp cả ba.
5. `EqualsFilter` escape dấu sao như ký tự literal; bộ lọc không trở thành substring filter `(uid=lan*)`.

Thử thay dữ liệu mẫu bằng một entry có hai giá trị `mail`, trong đó một giá trị đúng `lan@example.org`. Kiểm tra lại vì sao `(!(mail=lan@example.org))` không khớp entry đó, dù entry còn một địa chỉ email khác.

## 12. Ghi nhớ và tham khảo

LDAP filter dùng cú pháp **prefix có ngoặc**: `&` cho AND, `|` cho OR, `!` cho NOT. AND yêu cầu tất cả filter con khớp, OR cần ít nhất một filter con khớp, còn NOT đảo kết quả của một filter con. Khi lồng điều kiện, **vị trí ngoặc xác định ý nghĩa**; cần chú ý sự khác nhau giữa phủ định equality và phủ định presence, nhất là với attribute nhiều giá trị.

Trong Spring LDAP, ưu tiên `AndFilter`, `OrFilter`, `NotFilter`, `EqualsFilter` hoặc query builder để tạo điều kiện rõ ràng và escape giá trị đầu vào. Luôn xem filter cùng với search base, scope, schema, ACL và cấu hình kết nối an toàn để hiểu kết quả truy vấn.

Tài liệu tham khảo:

- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter và escaping.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): biểu diễn filter ở mức giao thức, phạm vi tìm kiếm và ngữ nghĩa đánh giá.
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, filter builder và `LdapQueryBuilder`.
