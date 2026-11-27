# where, and, or và nhóm điều kiện trong Spring LDAP Query Builder

Khi tìm kiếm LDAP, ứng dụng thường cần kết hợp nhiều tiêu chí: “là tài khoản người dùng **và** thuộc phòng Engineering **hoặc** QA, **và** phải có email”. Nếu viết một chuỗi filter bằng cách nối các phần do người dùng nhập, rất dễ sai dấu ngoặc, thay đổi ý nghĩa AND/OR hoặc tạo lỗ hổng **LDAP filter injection**.

Trong Spring LDAP, `LdapQueryBuilder` (gói `org.springframework.ldap.query`) cung cấp fluent API để tạo `LdapQuery` gồm **search base, scope, thuộc tính trả về, giới hạn và filter**. Những phương thức `where(...)`, `and(...)`, `or(...)` và **tiêu chí lồng nhau** giúp diễn đạt logic chính xác mà không cần ghép thủ công chuỗi filter. Bài này thuộc chương **Query builder** của module **Spring LDAP**, tập trung vào cách kết hợp điều kiện và tránh các bẫy API thực tế.

Sau bài học, bạn có thể:

- Viết filter LDAP đơn bằng `where("attribute").is(value)`.
- Kết hợp điều kiện cùng cấp bằng `and("attribute")` hoặc `or("attribute")`.
- Xây nhóm `A AND (B OR C)` và `A OR (B AND C)` bằng `and(ContainerCriteria)` / `or(ContainerCriteria)`.
- Hiểu vì sao **không được trộn AND và OR dạng chuỗi cùng một cấp** trong API fluent.
- Tạo điều kiện `not()`, `isPresent()` và biết khi nào cần dùng các lớp `Filter` chuyên dụng.
- Tránh injection, xác định search base/scope, đọc kết quả bằng `LdapTemplate` hoặc `LdapClient` và kiểm thử filter.

## 1. Dữ liệu mẫu và ngữ nghĩa của LDAP filter

Giả sử một LDAP directory có base `dc=example,dc=org` và chứa những entry sau, đều nằm trực tiếp dưới `ou=people`:

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

dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Le
sn: Le
ou: QA

dn: uid=bao,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: bao
cn: Bao Pham
sn: Pham
ou: Sales
mail: bao@example.org
```

LDAP filter có cú pháp **prefix**, mỗi nhóm được bọc trong ngoặc:

```ldap
(uid=lan)
```

```ldap
(&(objectClass=inetOrgPerson)(mail=*))
```

```ldap
(|(ou=Engineering)(ou=QA))
```

| Biểu thức | Ý nghĩa |
| --- | --- |
| `(uid=lan)` | Thuộc tính `uid` khớp giá trị Lan theo matching rule của schema |
| `(mail=*)` | Có ít nhất một giá trị `mail` (presence filter) |
| **AND**: `&` | Tất cả điều kiện con phải khớp |
| **OR** | Có ít nhất một điều kiện con khớp |
| **NOT**: `!` | Phủ định kết quả của một filter con |

Cú pháp LDAP **không** dùng `uid=lan && mail!=null` hay `uid=lan OR uid=minh`. Thứ tự ngoặc quyết định logic, vì vậy builder phải thể hiện **đúng cây điều kiện** mà nghiệp vụ yêu cầu.

## 2. Khởi tạo query và dùng `where(...)`

Import thường dùng:

```java
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;
```

Một điều kiện equality:

```java
LdapQuery byUid = query()
    .base("ou=people")
    .where("uid").is("lan");
```

Logic filter thu được là:

```ldap
(uid=lan)
```

`where("uid")` chọn **tên thuộc tính**; `is("lan")` chọn **giá trị** so khớp bằng nhau. `is(value)` tạo equality filter theo quy tắc LDAP, không phải phép so sánh Java `String.equals`. Matching rule của attribute trên LDAP server quyết định cách so khớp (ví dụ có phân biệt hoa/thường không).

Lưu ý:

- `query()` tạo một `LdapQueryBuilder`.
- `base("ou=people")` chỉ định **search base**, không phải DN của một entry cần lookup.
- Nếu `ContextSource.base = "dc=example,dc=org"`, search base tương đối `ou=people` sẽ ứng với `ou=people,dc=example,dc=org` trên server.
- `where(...)` bắt đầu khai báo filter; những thiết lập như `base(...)`, `searchScope(...)`, `attributes(...)` nên được đặt **trước** `where(...)`.

Không đưa giá trị của người dùng vào **tên attribute** mà không kiểm soát. Builder escape **giá trị** so khớp, nhưng application vẫn phải quyết định field nào được phép tìm.

## 3. AND: dùng `and("attribute")`

Yêu cầu: “Entry là `inetOrgPerson` **và** có UID bằng `lan`”.

```java
LdapQuery lanPerson = query()
    .base("ou=people")
    .where("objectClass").is("inetOrgPerson")
    .and("uid").is("lan");
```

Tương đương với filter:

```ldap
(&(objectClass=inetOrgPerson)(uid=lan))
```

Khi thêm nhiều AND cùng cấp:

```java
LdapQuery withEmail = query()
    .base("ou=people")
    .where("objectClass").is("inetOrgPerson")
    .and("ou").is("Engineering")
    .and("mail").isPresent();
```

Filter:

```ldap
(&(objectClass=inetOrgPerson)(ou=Engineering)(mail=*))
```

Theo dữ liệu mẫu, truy vấn thứ hai khớp Lan; guest ở Engineering nhưng **thiếu `mail`**, nên không khớp. `isPresent()` kiểm tra sự hiện diện của attribute; nó khác với kiểm tra một giá trị email cụ thể.

Một nhóm AND có thể chứa nhiều điều kiện, nhưng chúng đều phải có cấu trúc LDAP hợp lệ. `and("mail")` trả về `ConditionCriteria` để tiếp tục bằng `is(...)`, `isPresent()`, `like(...)` hoặc phép so sánh được API hỗ trợ.

## 4. OR: dùng `or("attribute")`

Yêu cầu: “UID là Lan **hoặc** Minh”:

```java
LdapQuery eitherUser = query()
    .base("ou=people")
    .where("uid").is("lan")
    .or("uid").is("minh");
```

Filter tương đương:

```ldap
(|(uid=lan)(uid=minh))
```

Nếu muốn tìm người thuộc một trong hai bộ phận:

```java
LdapQuery eitherDepartment = query()
    .base("ou=people")
    .where("ou").is("Engineering")
    .or("ou").is("QA");
```

Filter tương đương:

```ldap
(|(ou=Engineering)(ou=QA))
```

Với dữ liệu mẫu, Lan, Minh, guest và An khớp; Bảo thuộc Sales không khớp. OR có nghĩa **ít nhất một điều kiện đúng**, không phải “chỉ đúng một trong hai”. Nếu một thuộc tính có nhiều giá trị và entry khớp nhiều nhánh, entry vẫn là **một** entry trong kết quả search, không bị nhân bản chỉ vì khớp nhiều điều kiện.

## 5. Quan trọng: không trộn `and("...")` và `or("...")` cùng cấp

Ví dụ sau trông giống Java fluent hợp lý, nhưng **không phải cách viết được hỗ trợ**:

```java
// Sai: đã dùng and(String) tại cùng container, sau đó gọi or(String).
LdapQuery invalid = query()
    .where("objectClass").is("inetOrgPerson")
    .and("ou").is("Engineering")
    .or("ou").is("QA");
```

Trong API Spring LDAP, `ContainerCriteria.or(String)` có thể ném `IllegalStateException` nếu trên cùng container đã dùng `and(String)`; chiều ngược lại cũng vậy. Lý do là biểu thức như `A AND B OR C` **không rõ cách nhóm** nếu không có ngoặc. Spring LDAP buộc người viết diễn đạt cây điều kiện một cách tường minh.

Hai cách hiểu khác nhau của biểu thức ban đầu là:

```text
A AND (B OR C)
```

và:

```text
(A AND B) OR C
```

Chúng **không tương đương**. Vì vậy, khi một query cần cả AND lẫn OR, hãy tạo một **nhóm con bằng `query().where(...)`**, rồi gắn nhóm ấy vào nhóm cha qua `and(nested)` hoặc `or(nested)`.

## 6. Nhóm điều kiện: `A AND (B OR C)`

Yêu cầu: “Lấy entry có `objectClass=inetOrgPerson` và `ou` là Engineering **hoặc** QA”.

Biểu thức logic:

```text
AND
├── objectClass = inetOrgPerson
└── OR
    ├── ou = Engineering
    └── ou = QA
```

Filter LDAP:

```ldap
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=QA)))
```

Code Query Builder:

```java
LdapQuery peopleInTwoDepartments = query()
    .base("ou=people")
    .where("objectClass").is("inetOrgPerson")
    .and(
        query().where("ou").is("Engineering")
               .or("ou").is("QA")
    );
```

Giải thích:

1. `where("objectClass").is("inetOrgPerson")` tạo điều kiện A của nhóm cha.
2. `query().where("ou")...or("ou")...` tạo một **`ContainerCriteria` lồng nhau** chứa OR của B và C.
3. `and(nested)` gắn cả nhóm OR như **một nhánh** vào AND cha.
4. `base("ou=people")` chỉ đặt ở query cha. Các thông số base/scope được chỉ định trong nested criterion **không phải cách cấu hình truy vấn tổng thể** và không được mang sang query cha.

Với bộ dữ liệu mẫu, Lan, Minh, guest và An khớp; Bảo không khớp. Nếu thêm yêu cầu “phải có email” và “không phải guest”, code trở thành:

```java
LdapQuery activeContactPeople = query()
    .base("ou=people")
    .where("objectClass").is("inetOrgPerson")
    .and(query().where("ou").is("Engineering")
                .or("ou").is("QA"))
    .and("mail").isPresent()
    .and("uid").not().is("guest");
```

Filter tương đương:

```ldap
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=QA))(mail=*)(!(uid=guest)))
```

Lan và Minh khớp; guest bị loại bởi điều kiện `mail=*` và `uid != guest`; An thiếu email; Bảo không thuộc Engineering/QA.

### Không nhầm với một nhóm OR phẳng

Code sau chỉ có OR, vì thế `objectClass` được xem là một trong các lựa chọn chứ **không phải điều kiện bắt buộc**:

```java
LdapQuery notTheSame = query()
    .base("ou=people")
    .where("objectClass").is("inetOrgPerson")
    .or("ou").is("Engineering")
    .or("ou").is("QA");
```

Đây là logic `A OR B OR C`, không tương đương với `A AND (B OR C)`. Trong dữ liệu mẫu, mọi entry đều là `inetOrgPerson` nên đều khớp; filter này quá rộng so với yêu cầu ban đầu.

## 7. Nhóm điều kiện: `A OR (B AND C)`

Yêu cầu khác: “Lấy tất cả người thuộc Engineering, **hoặc** người thuộc QA **và có email**”.

Filter:

```ldap
(|(ou=Engineering)(&(ou=QA)(mail=*)))
```

Code:

```java
LdapQuery engineeringOrQaWithMail = query()
    .base("ou=people")
    .where("ou").is("Engineering")
    .or(
        query().where("ou").is("QA")
               .and("mail").isPresent()
    );
```

Theo dữ liệu mẫu, Lan và guest khớp vì thuộc Engineering (dù guest không có email); Minh khớp vì thuộc QA và có email. An thuộc QA nhưng thiếu email nên không khớp. Bảo thuộc Sales nên không khớp.

So sánh với:

```ldap
(&(|(ou=Engineering)(ou=QA))(mail=*))
```

Biểu thức thứ hai yêu cầu **có email cho cả hai nhánh Engineering và QA**, nên chỉ trả Lan và Minh. Khi viết query để cấp quyền hoặc chọn đối tượng cập nhật, khác biệt ngoặc này đặc biệt quan trọng.

### Có thể lồng nhiều nhóm ở các cấp

Để diễn đạt `A AND (B OR C) AND (D OR E)`, hãy gắn **hai nhóm OR riêng biệt** vào cùng một nhóm AND cha, thay vì viết một chuỗi điều kiện phẳng rồi chắp thêm `.and(String)` sau `.or(String)`:

```java
LdapQuery grouped = query()
    .base("ou=people")
    .where("objectClass").is("inetOrgPerson")
    .and(query().where("ou").is("Engineering")
                .or("ou").is("QA"))
    .and(query().where("mail").isPresent()
                .or("uid").is("guest"));
```

Đây là biểu thức `objectClass=inetOrgPerson AND (ou=Engineering OR ou=QA) AND (mail tồn tại OR uid=guest)`. Nhóm OR ở cấp con được giữ nguyên khi gắn vào AND cha. Nếu không cần điều kiện `objectClass`, có thể thay nhóm cha bằng một filter composition thích hợp, xem mục 9.

## 8. `not()`, `isPresent()` và điều kiện kiểm tra giá trị

Ngoài equality, `ConditionCriteria` hỗ trợ những dạng thường dùng:

| API | Ví dụ | Filter tương đương |
| --- | --- | --- |
| `is(value)` | `where("uid").is("lan")` | `(uid=lan)` |
| `isPresent()` | `where("mail").isPresent()` | `(mail=*)` |
| `not().is(value)` | `where("uid").not().is("guest")` | `(!(uid=guest))` |
| `not().isPresent()` | `where("mail").not().isPresent()` | `(!(mail=*))` |
| `gte(value)` | `where("employeeNumber").gte("100")` | `(employeeNumber>=100)` |
| `lte(value)` | `where("employeeNumber").lte("900")` | `(employeeNumber<=900)` |

**Cảnh báo về so sánh:** `gte`/`lte` phụ thuộc ordering matching rule của attribute trên server. Không suy luận rằng giá trị chuỗi `"100"` hay `"900"` luôn được so sánh số học như kiểu `int` của Java. Chỉ dùng khi schema và matching rule thực tế phù hợp.

**NOT trên một điều kiện** khác với “không có attribute”:

```ldap
(!(mail=lan@example.org))
```

có thể khớp cả entry có email khác **và** entry thiếu `mail`. Trong khi đó:

```ldap
(!(mail=*))
```

chỉ khớp entry không hiện diện attribute `mail`. Nếu muốn “có email nhưng không bằng địa chỉ này”, hãy yêu cầu cả hai:

```java
LdapQuery emailOtherThanLan = query()
    .base("ou=people")
    .where("mail").isPresent()
    .and("mail").not().is("lan@example.org");
```

Filter tương đương:

```ldap
(&(mail=*)(!(mail=lan@example.org)))
```

Nếu `mail` có nhiều giá trị và một giá trị khớp `lan@example.org`, phủ định equality không khớp **toàn entry**; nó không có nghĩa “tồn tại một value khác”. Một số phép so khớp LDAP còn có trạng thái Undefined (khi không thể đánh giá); NOT không biến Undefined thành TRUE. Quyết định nghiệp vụ dựa trên kết quả truy vấn cần xét schema và quyền đọc thực tế.

## 9. Khi nhóm/NOT phức tạp: dùng `Filter` và `filter(...)`

Với điều kiện thông thường, lồng `query().where(...)` là cách đọc dễ dàng. Với một nhóm cần phủ định **cả OR hoặc AND**, hoặc muốn tái sử dụng một cây điều kiện riêng, có thể dùng các lớp `org.springframework.ldap.filter`:

| Lớp | Mục đích |
| --- | --- |
| `EqualsFilter` | Equality và escaping giá trị |
| `PresentFilter` | Attribute presence |
| `AndFilter` | Chứa nhiều filter con kết hợp AND |
| `OrFilter` | Chứa nhiều filter con kết hợp OR |
| `NotFilter` | Phủ định một filter con (có thể là cả nhóm) |

Ví dụ: “**không thuộc** Engineering **và cũng không thuộc** QA” được viết như phủ định cả nhóm OR:

```ldap
(!(|(ou=Engineering)(ou=QA)))
```

Code:

```java
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.NotFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

OrFilter inDepartments = new OrFilter();
inDepartments.or(new EqualsFilter("ou", "Engineering"));
inDepartments.or(new EqualsFilter("ou", "QA"));

LdapQuery outsideDepartments = query()
    .base("ou=people")
    .filter(new NotFilter(inDepartments));
```

Điểm quan trọng: **chọn một trong hai cách khai báo filter**:

- `query().where(...).and(...)...` để tạo filter bằng fluent criteria;
- `query().filter(filterObject)` hoặc `query().filter(hardcodedFilter)` để cung cấp toàn bộ filter đã có.

**Không trộn `filter(...)` với `where(...)` trong cùng `LdapQueryBuilder`.** Spring LDAP có thể ném `IllegalStateException` khi bạn cố thêm `where` sau một filter đã được chỉ định. Thông số base/scope/attributes cần được đặt trước khi filter được hoàn tất.

Một overload `filter(String hardcodedFilter)` **không kiểm tra hoặc escape input**. Nếu buộc dùng filter dạng chuỗi, chỉ dùng chuỗi cố định đã kiểm soát; với giá trị động, ưu tiên `where(...).is(...)`, `EqualsFilter` hoặc `filter(String format, Object... params)` theo đúng cú pháp `MessageFormat` và API phiên bản đang dùng.

## 10. Dùng query hoàn chỉnh với `LdapTemplate.search`

Giả sử ứng dụng Spring Boot đã cấu hình `ContextSource.base = "dc=example,dc=org"` và một `LdapTemplate` dùng context source đó. Đoạn Java 17+ sau minh họa xây query phức hợp, giới hạn phạm vi và ánh xạ kết quả:

```java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record PersonSummary(String uid, String commonName) {}

public final class PeopleDirectory {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findInDepartments(
            String departmentA, String departmentB) {

        LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid", "cn")
            .countLimit(200)
            .timeLimit(3_000)
            .where("objectClass").is("inetOrgPerson")
            .and(query().where("ou").is(departmentA)
                        .or("ou").is(departmentB))
            .and("mail").isPresent()
            .and("uid").not().is("guest");

        return ldapTemplate.search(
            ldapQuery,
            (AttributesMapper<PersonSummary>) attrs -> {
                Attribute uid = attrs.get("uid");
                Attribute cn = attrs.get("cn");
                return new PersonSummary(
                    uid == null ? null : (String) uid.get(),
                    cn == null ? null : (String) cn.get()
                );
            }
        );
    }
}
```

Lưu ý về cấu hình:

1. `base("ou=people")` là search base **tương đối** so với base của `ContextSource`. Không truyền lại cả `dc=example,dc=org` nếu base đó đã cấu hình sẵn.
2. `searchScope(SearchScope.SUBTREE)` cho phép tìm entry ở mọi cấp bên dưới people. Nếu chỉ muốn con trực tiếp, dùng `SearchScope.ONELEVEL`, và cần xác minh cấu trúc OU.
3. `attributes("uid", "cn")` chỉ yêu cầu hai attribute để mapping; `mail` vẫn có thể dùng trong filter dù không nằm trong projection trả về.
4. `countLimit(200)` và `timeLimit(3_000)` đặt giới hạn kết quả/thời gian; chúng **không** bảo đảm server chỉ có 200 entry hay truy vấn luôn hoàn thành đầy đủ.
5. `departmentA` và `departmentB` đến từ đầu vào nên được đưa vào `is(...)` để escape giá trị filter, thay vì nối chuỗi.
6. Vì `cn` có thể là multi-valued, lấy `attrs.get("cn").get()` chỉ lấy **một giá trị**; ví dụ trên cố ý đơn giản hóa. Khi cần đầy đủ hoặc một tên ưu tiên, phải dùng mapping/quy tắc nghiệp vụ phù hợp.

Với `departmentA = "Engineering"` và `departmentB = "QA"`, theo dữ liệu mẫu Lan và Minh được chọn. Trong một directory thật, quyền bind, schema/matching rules và vị trí entry có thể ảnh hưởng kết quả.

### Dùng cùng LdapQuery với LdapClient

Ở phiên bản Spring LDAP có `LdapClient`, cùng đối tượng `LdapQuery` có thể được truyền tới fluent search:

```java
import org.springframework.ldap.core.LdapClient;

List<PersonSummary> people = ldapClient.search()
    .query(ldapQuery)
    .map((AttributesMapper<PersonSummary>) attrs -> {
        Attribute uid = attrs.get("uid");
        Attribute cn = attrs.get("cn");
        return new PersonSummary(
            uid == null ? null : (String) uid.get(),
            cn == null ? null : (String) cn.get()
        );
    })
    .list();
```

Đoạn code này minh họa trong một method/class đã có biến `ldapClient` và `ldapQuery` cùng DTO. Lựa chọn `LdapTemplate` hay `LdapClient` không thay đổi ngữ nghĩa nhóm filter; cả hai cùng dựa trên `LdapQuery` do builder tạo. Cần kiểm tra phiên bản Spring LDAP thực tế để dùng API tương ứng.

## 11. Bảo mật, giới hạn và hiệu năng

**Builder giải quyết escaping của giá trị, không giải quyết tất cả vấn đề bảo mật.**

Ví dụ tránh nối filter:

```java
// Không an toàn:
String filter = "(uid=" + inputUid + ")";

// An toàn hơn cho equality filter:
LdapQuery safe = query()
    .base("ou=people")
    .where("uid").is(inputUid);
```

Nếu `inputUid = "lan*"`, chuỗi nối thô `(uid=lan*)` mang nghĩa substring; builder equality sẽ escape ký tự `*` theo RFC 4515 để nó là một phần **literal của giá trị** (ví dụ `(uid=lan\2a)`). Với nhu cầu substring có chủ đích, dùng `like(...)` và kiểm soát mẫu tìm kiếm; không đánh tráo yêu cầu equality bằng wildcard từ đầu vào không tin cậy.

Ngoài escaping:

- Chỉ cho phép tên attribute, search base và kiểu điều kiện trong **danh sách được phê duyệt**; người dùng không được tự chọn bất kỳ nhánh LDAP nào.
- Dùng kết nối **LDAPS hoặc StartTLS** có kiểm tra chứng chỉ, bind account với **quyền tối thiểu** và ACL phía server.
- Thu hẹp base/scope đúng nhu cầu trước khi chạy query trên DIT lớn. Một OR rộng có thể trả nhiều entry, và NOT/substrings có thể làm tối ưu index khó hơn.
- Chỉ trả các attribute cần dùng; chú ý attribute nhị phân và multi-valued khi mapping.
- Nếu gặp size/time limit hoặc paging chưa hoàn tất, **không coi kết quả một phần là toàn bộ dữ liệu**.
- Khi log, không ghi secret hoặc nguyên dữ liệu cá nhân nhạy cảm từ filter/kết quả.

`LdapQueryBuilder` là công cụ tạo **đúng truy vấn** và giảm lỗi cú pháp. Hiệu năng của query vẫn phụ thuộc filter, matching rule, index, DIT, network và LDAP server; không thể kết luận truy vấn “nhẹ” chỉ vì được viết qua fluent API.

## 12. Kiểm thử biểu thức và truy vấn thật

Nên có hai tầng kiểm thử:

### 12.1. Unit test biểu thức filter

Không cần khởi động LDAP server để xác nhận builder tạo đúng nhóm:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

class LdapQueryGroupingTest {
    @Test
    void groupsOrInsideAnd() {
        LdapQuery ldapQuery = query()
            .where("objectClass").is("inetOrgPerson")
            .and(query().where("ou").is("Engineering")
                        .or("ou").is("QA"));

        assertEquals(
            "(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=QA)))",
            ldapQuery.filter().encode()
        );
    }
}
```

Test này xác minh **logic và cách encode filter** theo phiên bản thư viện đang sử dụng, không chứng minh server có index hay entry thực sự tồn tại. Nếu phiên bản thay đổi định dạng nhưng giữ ngữ nghĩa, test chuỗi có thể cần được điều chỉnh; thêm integration test giúp xác nhận hành vi thực tế.

### 12.2. Integration test trên thư mục mẫu

Với LDIF ở đầu bài, kiểm tra tối thiểu:

1. **AND đơn:** `(objectClass=inetOrgPerson) AND (mail=*)` khớp Lan, Minh và Bảo.
2. **OR đơn:** `ou=Engineering OR ou=QA` khớp Lan, Minh, guest và An.
3. **AND chứa OR:** `inetOrgPerson AND (Engineering OR QA) AND mail present AND NOT guest` khớp Lan và Minh.
4. **OR chứa AND:** `Engineering OR (QA AND mail present)` khớp Lan, guest và Minh.
5. **Escaping:** giá trị chứa `*`, `(`, `)` hoặc dấu gạch chéo ngược được xử lý như dữ liệu literal trong equality.
6. **Cấu hình:** search base tương đối trỏ đúng vùng dữ liệu; scope và filter không bỏ sót OU cần thiết.
7. **Quyền:** kết quả khi bind bằng tài khoản chỉ đọc phù hợp với ACL, lỗi kết nối/TLS không bị chuyển thành “không tìm thấy”.

Một entry có attribute nhiều giá trị cần được thử riêng: điều kiện equality khớp nếu có giá trị thích hợp, còn phủ định equality không có nghĩa tồn tại một giá trị khác. Khi kết quả lớn, xác minh size limit và cách xử lý kết quả chưa đầy đủ.

## 13. Các lỗi thường gặp

| Lỗi hoặc hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `IllegalStateException` sau chuỗi `and("a")...or("b")` | Trộn AND/OR cùng cấp trong fluent criteria | Đưa OR vào nested `query().where(...).or(...)` rồi gắn bằng `and(nested)` |
| Gọi `base(...)` sau `where(...)` | Tham số tìm kiếm phải được đặt trước khi khai báo filter | Sắp thứ tự `base/searchScope/attributes/countLimit/timeLimit` trước `where` |
| Gọi `where(...)` sau `filter(...)` | Hai chiến lược dựng filter không được trộn | Chọn fluent criteria **hoặc** filter object/chuỗi |
| Query trả quá nhiều entry | OR phẳng làm điều kiện bắt buộc trở thành một lựa chọn | Thêm nhóm `A AND (B OR C)` chính xác |
| Query trả quá ít entry | Nhóm AND đặt sai, scope/base hẹp hoặc filter không khớp | Vẽ cây logic, kiểm tra DN, scope và schema |
| Query đúng nhưng không thấy người dùng ở OU con | Search scope không bao phủ OU đó | Xem `ONELEVEL` so với `SUBTREE` và base |
| Dùng `like("lan*")` khi muốn tìm literal dấu sao | `*` được hiểu là wildcard trong substring pattern | Dùng `is("lan*")` để equality và escaping |
| Nối input trực tiếp vào filter | Có nguy cơ LDAP injection | Dùng `is(value)`, filter builder hoặc format có escaping |
| NOT email cụ thể trả cả entry thiếu email | Phủ định equality khác presence | Kết hợp `mail=*` và NOT equality |
| Bị giới hạn kết quả nhưng coi là đầy đủ | Size/time limit hoặc paging | Kiểm tra trạng thái trả về và phân trang khi cần |

## 14. Bài tập áp dụng

Giả sử dữ liệu giống mục 1, `ContextSource.base = "dc=example,dc=org"` và ứng dụng cần đọc entry từ `ou=people`.

**Câu 1.** Viết builder cho `(uid=lan)`.

```java
LdapQuery q1 = query()
    .base("ou=people")
    .where("uid").is("lan");
```

**Câu 2.** Viết builder cho `(&(objectClass=inetOrgPerson)(mail=*))`.

```java
LdapQuery q2 = query()
    .base("ou=people")
    .where("objectClass").is("inetOrgPerson")
    .and("mail").isPresent();
```

**Câu 3.** Chọn entry thuộc Engineering hoặc QA nhưng không có email. Kết quả theo dữ liệu mẫu là những ai?

```java
LdapQuery q3 = query()
    .base("ou=people")
    .where("ou").is("Engineering")
    .or("ou").is("QA");
```

Đoạn trên **mới** tạo nhóm OR, chưa áp điều kiện không có email. Cần nhóm đầy đủ:

```java
LdapQuery q3Fixed = query()
    .base("ou=people")
    .where("mail").not().isPresent()
    .and(query().where("ou").is("Engineering")
                .or("ou").is("QA"));
```

Đáp án: guest và An. Lan/Minh có email; Bảo thuộc Sales.

**Câu 4.** So sánh `A AND (B OR C)` với `(A AND B) OR C`, trong đó A = `mail=*`, B = `ou=Engineering`, C = `ou=QA`. Có thể cho cùng một kết quả không?

Đáp án: không nhất thiết. `A AND (B OR C)` yêu cầu email cho cả hai bộ phận, nên Lan/Minh khớp. `(A AND B) OR C` cho toàn bộ QA đi qua ngay cả khi không có email, nên có thêm An. Phải nhóm đúng theo nghiệp vụ.

**Câu 5.** Vì sao `where("uid").is(userUid)` phù hợp hơn nối `"(uid=" + userUid + ")"`? Khi `userUid` có dấu sao, kết quả có khác không?

Đáp án: `is(userUid)` escape ký tự đặc biệt trong giá trị theo filter encoding, tránh biến dấu sao thành wildcard hoặc chèn cấu trúc LDAP filter. Nối chuỗi thô có thể thay đổi ngữ nghĩa và tạo lỗi bảo mật.

**Câu 6.** Muốn phủ định **cả nhóm** `(ou=Engineering OR ou=QA)`, API nào dễ diễn đạt nhất?

Đáp án: dùng `OrFilter` chứa hai `EqualsFilter`, sau đó `NotFilter` bọc cả nhóm và truyền qua `query().filter(filter)`. `not()` trên một `ConditionCriteria` chỉ phủ định một điều kiện cụ thể, không tự phủ định cả cây lồng nhau.

**Câu 7.** Có thể viết `query().filter(new OrFilter(...)).where("uid")...` không?

Đáp án: không; đây là hai cách chỉ định filter khác nhau trong cùng builder. Chọn một cách, và thiết lập base/scope/projection trước phần filter.

## 15. Tổng kết và tài liệu tham khảo

Trong Spring LDAP, `where(...)` khởi tạo một điều kiện filter; `and("attribute")` và `or("attribute")` nối các điều kiện **cùng cấp**. Khi nghiệp vụ yêu cầu kết hợp cả AND và OR, phải tạo **nhóm tường minh** bằng `query().where(...)` rồi đưa vào `and(nested)` hoặc `or(nested)`. API cố ý ngăn trộn hai kiểu cùng cấp để tránh biểu thức mơ hồ.

`LdapQueryBuilder` còn chứa search base, search scope, thuộc tính trả về và các giới hạn tìm kiếm. Đặt các tham số này trước `where` hoặc `filter`, ưu tiên builder để escape giá trị đầu vào, không trộn hai cơ chế dựng filter và tránh nghĩ rằng `NOT` hay `OR` tự động thay đổi search scope. Luôn kiểm thử ý nghĩa của ngoặc và hành vi trên directory có dữ liệu đại diện.

Tài liệu tham khảo chính thức:

- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `where`, `and`, `or`, nested criteria và filter API.
- [Spring LDAP — LdapQueryBuilder Javadoc](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html): base/scope/attributes/limits và thứ tự cấu hình.
- [Spring LDAP — ContainerCriteria Javadoc](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/ContainerCriteria.html): `and(String)`, `or(String)`, `and(ContainerCriteria)`, `or(ContainerCriteria)` và ràng buộc mixing.
- [Spring LDAP — ConditionCriteria Javadoc](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/ConditionCriteria.html): `is`, `isPresent`, `not`, `like`, `gte` và `lte`.
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp AND/OR/NOT, nhóm filter và escaping.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, search scope và đánh giá điều kiện.
