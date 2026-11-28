# Xử lý một kết quả, nhiều kết quả và kết quả ngoài dự kiến

Một API nội bộ tìm nhân viên theo `uid` có thể trả về đúng một người trong môi trường thử nghiệm. Nhưng khi dữ liệu thật được đồng bộ từ nhiều đơn vị, cùng một `uid` có thể xuất hiện ở hai nhánh OU, một entry có thể thiếu `mail`, hoặc truy vấn không trả kết quả vì tài khoản bind không có quyền đọc. Nếu service chỉ gọi `findFirst()` hoặc lấy phần tử đầu tiên của danh sách, ứng dụng có thể gắn nhầm hồ sơ, che giấu dữ liệu trùng và báo “không tồn tại” khi directory thực ra đang gặp lỗi.

Trong chương **Tìm kiếm** của module **SPRING_DATA_LDAP**, bài này giải thích cách xử lý **0 kết quả, đúng 1 kết quả, nhiều kết quả và kết quả ngoài dự kiến** khi tìm kiếm directory bằng Spring Data LDAP. Ta sử dụng DN, `objectClass`, schema, `LdapRepository`, `LdapTemplate`, query builder, mapper và các ngoại lệ Spring LDAP. Trọng tâm là chọn API phù hợp với số lượng kết quả mong đợi, bảo toàn thông tin khi dữ liệu bất thường và phân biệt một lần tìm kiếm rỗng hợp lệ với một truy vấn đã thất bại hoặc chỉ trả dữ liệu một phần.

**Quy tắc cốt lõi:** Nếu nghiệp vụ yêu cầu đúng một entry, hãy thực thi hợp đồng “đúng một” và để lỗi nhiều kết quả được phát hiện rõ ràng. Nếu nghiệp vụ chấp nhận nhiều entry, hãy dùng collection và xử lý toàn bộ kết quả theo quy tắc đã định. Không âm thầm chọn một entry bất kỳ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt kết quả **không có entry**, **một entry**, **nhiều entry** và **kết quả không hoàn chỉnh/lỗi**.
2. Chọn giữa `LdapTemplate.search(...)`, `searchForObject(...)`, `searchForContext(...)`, `LdapRepository.findOne(...)` và các query method trả về `Optional`/`List`.
3. Hiểu chính xác hành vi của `Optional<T>` khi không có kết quả và khi có nhiều kết quả.
4. Dùng `countLimit(2)` để phát hiện một định danh không duy nhất mà không cần tải toàn bộ danh sách trùng.
5. Xây dựng DN/base/filter/scope đúng và dùng filter builder để mã hóa giá trị an toàn.
6. Ánh xạ attribute thiếu, nhiều giá trị, dữ liệu sai schema và thuộc tính tùy chọn.
7. Xử lý lỗi LDAP, referral, timeout, ACL, replica và kết quả partial mà không giả vờ rằng search thành công.
8. Viết unit test và integration test cho mọi trường hợp cardinality, dữ liệu trùng và lỗi ngoài dự kiến.

## 2. Một lần search có thể cho những trạng thái nào?

Giả sử ứng dụng cần tìm nhân viên theo `uid=lan.nguyen` trong cây:

~~~text
dc=corp,dc=example
├── ou=employees
│   ├── uid=lan.nguyen
│   └── uid=minh.tran
├── ou=contractors
│   └── uid=lan.nguyen
└── ou=services
    └── cn=app-reader
~~~

Nếu base là `dc=corp,dc=example` và scope là `SUBTREE`, filter `(uid=lan.nguyen)` có thể trả **hai entry**. Nếu base là `ou=employees` và scope `ONELEVEL`, truy vấn có thể trả một entry. Kết quả phụ thuộc cả base DN, scope, filter, schema/matching rule, ACL và topology directory.

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **0 — NOT_FOUND** | Search kết thúc bình thường và không có entry nào khớp trong phạm vi/quyền hiện tại. | Không có `uid` tương ứng trong `ou=employees`. |
| **1 — FOUND** | Có đúng một entry phù hợp. | Một nhân viên có `uid=lan.nguyen` trong OU đã chọn. |
| **N — MULTIPLE / AMBIGUOUS** | Có từ hai entry trở lên cùng khớp. | Hai OU chứa cùng `uid`. |
| **INVALID_DATA** | Entry có tồn tại nhưng thiếu field bắt buộc, sai kiểu hoặc vi phạm quy tắc nghiệp vụ. | Thiếu `sn` bắt buộc, `uid` rỗng hoặc attribute có giá trị bất ngờ. |
| **PARTIAL** | Có một phần entry nhưng search bị referral, giới hạn server hoặc lỗi giữa chừng. | Chỉ đọc được một partition, hoặc nhận `PartialResultException`. |
| **FAILED** | Không thể hoàn tất thao tác do bind, TLS, timeout, kết nối, filter hoặc lỗi server. | `invalidCredentials`, `insufficientAccessRights`, `timeLimitExceeded`. |

Điểm quan trọng là **NOT_FOUND chỉ hợp lệ khi thao tác tìm kiếm hoàn tất bình thường**. Một exception hoặc partial result không được đổi thành danh sách rỗng để service tiếp tục nghiệp vụ như thể user không tồn tại.

### 2.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Nhận yêu cầu tìm theo UID"] --> B["Validate input + xác định base/scope"]
    B --> C["Search LDAP bằng filter an toàn"]
    C --> D{"Search kết thúc bình thường?"}
    D -- "Không" --> E["FAILED hoặc PARTIAL<br/>phân loại exception"]
    D -- "Có" --> F{"Số entry quan sát được"}
    F -- "0" --> G["NOT_FOUND"]
    F -- "1" --> H["Map + validate entry"]
    F -- ">= 2" --> I["MULTIPLE / AMBIGUOUS"]
    H --> J{"Dữ liệu hợp lệ?"}
    J -- "Có" --> K["FOUND"]
    J -- "Không" --> L["INVALID_DATA"]
~~~

Không được chuyển nhánh `E` thành `G` chỉ vì code muốn trả HTTP 404 đơn giản hơn. Cũng không được chuyển nhánh `I` thành `H` bằng cách lấy phần tử đầu tiên nếu nghiệp vụ đòi hỏi danh tính duy nhất.

## 3. Phân biệt lookup theo DN và search theo thuộc tính

Hai thao tác thường bị gọi chung là “tìm người dùng”, nhưng chúng có ý nghĩa khác nhau.

| Thao tác | API | Dùng khi | Kết quả thiếu |
| --- | --- | --- | --- |
| **Lookup** | `ldapTemplate.lookup(dn, mapper)` | Đã biết DN cụ thể, cần đọc entry tại vị trí đó. | Thường nhận ngoại lệ naming đã được Spring LDAP dịch, chẳng hạn `NameNotFoundException`. |
| **Search** | `ldapTemplate.search(query, mapper)` | Tìm theo thuộc tính/filter trong một base/scope. | Danh sách rỗng nếu search hoàn tất nhưng không có entry khớp. |
| **Repository ID lookup** | `repository.findById(dn)` | Tìm theo ID của entity; trong Spring Data LDAP ID là DN. | `Optional.empty()` nếu ID không tìm thấy. |
| **Repository query** | `repository.findByUid(uid)` hoặc `findOne(query)` | Tìm theo thuộc tính đã ánh xạ trong entity. | Phụ thuộc kiểu trả về: List hoặc Optional. |

Ví dụ:

~~~java
// Đã biết DN: đọc đúng một vị trí trong cây.
Person person = ldapTemplate.lookup(
        "uid=lan.nguyen,ou=employees",
        personMapper);

// Chỉ biết UID: tìm trong phạm vi đã chọn.
List<Person> people = ldapTemplate.search(
        LdapQueryBuilder.query()
                .base("ou=employees")
                .searchScope(SearchScope.SUBTREE)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is("lan.nguyen"),
        personMapper);
~~~

DN có thể thay đổi khi entry được rename hoặc move. Nếu hệ thống chỉ lưu DN cũ rồi lookup sau khi entry đã được chuyển OU, lookup đó không còn trỏ đến vị trí mới. Search theo stable attribute/identifier có thể tìm lại entry, nhưng phải kiểm soát tính duy nhất và ACL.

**Một kết quả lookup không phải bằng chứng rằng toàn directory chỉ có một entry cùng UID.** Nó chỉ chứng minh entry tại DN đó tồn tại và caller có thể đọc nó.

## 4. Dùng `LdapTemplate.search` khi cần xử lý 0, 1 hoặc nhiều kết quả

`LdapTemplate.search(...)` thu thập những entry mà search nhận được và trả về một `List<T>`. Vì vậy:

- `list.isEmpty()`: không nhận entry nào.
- `list.size() == 1`: nhận đúng một entry.
- `list.size() > 1`: nhận nhiều entry.

Ví dụ truy vấn theo UID:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

record PersonSummary(String uid, String commonName, String email) {}

public class PersonSearchService {

    private final LdapTemplate ldapTemplate;

    public PersonSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findAllByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=employees")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        AttributesMapper<PersonSummary> mapper = attrs ->
                new PersonSummary(
                        textOrNull(attrs, "uid"),
                        textOrNull(attrs, "cn"),
                        textOrNull(attrs, "mail"));

        return ldapTemplate.search(query, mapper);
    }
}
~~~

Trong ví dụ, `textOrNull(...)` là hàm phụ trợ được định nghĩa ở mục 8.1; trong dự án, đặt helper trong class hoặc utility mà service có thể gọi. `LdapQueryBuilder` tạo filter theo cấu trúc, giúp giá trị `uid` được escape theo quy tắc LDAP filter. Base và scope được code quyết định thay vì nhận một DN tùy ý từ HTTP client.

### 4.1. Xử lý cardinality ở tầng service

Nếu nghiệp vụ muốn phân loại rõ:

~~~java
public PersonLookupResult findUniqueByUid(String uid) {
    List<PersonSummary> matches = findAllByUid(uid);

    if (matches.isEmpty()) {
        return new PersonLookupResult.NotFound();
    }
    if (matches.size() == 1) {
        return new PersonLookupResult.Found(matches.get(0));
    }
    return new PersonLookupResult.Ambiguous(matches.size());
}
~~~

Kiểu kết quả có thể khai báo:

~~~java
public sealed interface PersonLookupResult {
    record Found(PersonSummary person) implements PersonLookupResult {}
    record NotFound() implements PersonLookupResult {}
    record Ambiguous(int observedMatches) implements PersonLookupResult {}
}
~~~

Đây là ví dụ dùng Java 17+ sealed interface. Trong dự án Java cũ hơn, có thể dùng class/enum và DTO tương ứng.

**Giới hạn của cách làm:** `search` đang tạo một list chứa tất cả kết quả nhận được. Nếu filter có thể khớp hàng nghìn entry, đừng tải toàn bộ chỉ để biết có nhiều hơn một. Với use case “có đúng một không?”, nên dùng API exact-one hoặc đặt `countLimit(2)` để dừng ở ngưỡng phát hiện trùng.

## 5. Khi nghiệp vụ yêu cầu đúng một entry

Spring LDAP có các API được thiết kế để yêu cầu **chính xác một kết quả**:

- `LdapTemplate.searchForObject(query, mapper)`.
- `LdapTemplate.searchForContext(query)`.
- `LdapRepository.findOne(query)`.

Hai API đầu ném `IncorrectResultSizeDataAccessException` nếu không có entry hoặc có nhiều hơn một entry. `LdapRepository.findOne(query)` trả `Optional<T>`: không có entry thì `Optional.empty()`, nhiều hơn một thì ném `IncorrectResultSizeDataAccessException`.

### 5.1. Ví dụ với `LdapTemplate.searchForContext`

~~~java
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public PersonSummary requireExactlyOne(String uid) {
    LdapQuery query = LdapQueryBuilder.query()
            .base("ou=employees")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid", "cn", "mail")
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(uid);

    try {
        DirContextOperations context = ldapTemplate.searchForContext(query);
        return new PersonSummary(
                context.getStringAttribute("uid"),
                context.getStringAttribute("cn"),
                context.getStringAttribute("mail"));
    } catch (IncorrectResultSizeDataAccessException ex) {
        // Không có hoặc nhiều hơn một entry.
        // Nếu cần phân biệt hai trường hợp, dùng List/countLimit(2)
        // hoặc repository.findOne(query) như các mục tiếp theo.
        throw ex;
    }
}
~~~

API này phù hợp khi hợp đồng thật sự yêu cầu đúng một entry và caller muốn mọi sai lệch cardinality trở thành lỗi rõ ràng. Nếu cần phân biệt **không tồn tại** với **trùng định danh**, dùng một trong các cách dưới đây.

### 5.2. Dùng `LdapRepository.findOne(LdapQuery)`

Khai báo repository:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {

    List<Person> findByUid(String uid);

    Optional<Person> findByEmployeeNumber(String employeeNumber);
}
~~~

`LdapRepository` dùng `Name` làm kiểu ID, tức **DN của entity**. Phương thức `findByUid` trả về nhiều kết quả; `findByEmployeeNumber` trả về `Optional` và ngụ ý truy vấn kỳ vọng tối đa một entry.

Khi có một `LdapQuery` được xây dựng rõ:

~~~java
import java.util.Optional;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=employees")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("employeeNumber").is(employeeNumber);

Optional<Person> person = personRepository.findOne(query);
~~~

Hành vi:

| Số entry phù hợp | Kết quả của `findOne(query)` |
| --- | --- |
| 0 | `Optional.empty()`. |
| 1 | `Optional.of(person)`. |
| 2 trở lên | `IncorrectResultSizeDataAccessException`. |

### 5.3. `Optional<T>` không phải cách che giấu duplicate

Trong Spring Data query method, `Optional<Person> findByEmployeeNumber(...)` có hợp đồng **tối đa một kết quả**. Nếu không tìm thấy, Optional rỗng; nếu có nhiều hơn một kết quả, Spring Data ném `IncorrectResultSizeDataAccessException`. Không nên viết:

~~~java
// KHÔNG NÊN: ép một tập nhiều kết quả thành một phần tử tùy ý.
Optional<Person> findFirstByUid(String uid);
~~~

trừ khi nghiệp vụ thực sự có quy tắc sắp xếp/chọn một entry rõ ràng. `First`/`Top` là giới hạn kết quả, **không chứng minh dữ liệu duy nhất**.

## 6. Phát hiện duplicate mà không tải toàn bộ kết quả

Giả sử `uid` phải duy nhất trong OU nhân viên. Ta cần biết:

- Không có UID.
- Có đúng một UID.
- Có từ hai UID trở lên.

Không cần tải hàng trăm entry để phân biệt ba trạng thái đó. Đặt `countLimit(2)`:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=employees")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "mail")
        .countLimit(2)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uid);

List<PersonSummary> matches = ldapTemplate.search(
        query,
        (AttributesMapper<PersonSummary>) attrs ->
                new PersonSummary(
                        textOrNull(attrs, "uid"),
                        textOrNull(attrs, "cn"),
                        textOrNull(attrs, "mail")));

if (matches.isEmpty()) {
    // Không tìm thấy trong phạm vi và quyền hiện tại.
} else if (matches.size() == 1) {
    // Có đúng một entry quan sát được nếu search hoàn tất bình thường.
} else {
    // Có ít nhất hai entry: đã đủ bằng chứng UID không duy nhất.
}
~~~

`countLimit(2)` có ý nghĩa **dừng ở mức đủ phát hiện nhiều hơn một**, không phải lấy chính xác tổng số duplicate. Nếu có 12 entry, ứng dụng có thể chỉ nhận tối đa 2. Đây là điều mong muốn khi chỉ cần phân loại cardinality.

### 6.1. Không dùng count limit để giả vờ uniqueness

Các trường hợp khác nhau:

| Cách làm | Điều chứng minh được | Rủi ro |
| --- | --- | --- |
| `countLimit(1)` rồi lấy phần tử đầu. | Có ít nhất một entry nếu search trả về. | Không thể phát hiện duplicate. |
| `countLimit(2)` và kiểm tra 0/1/2. | Có 0, 1 hoặc **ít nhất 2** entry trong kết quả quan sát. | Không biết tổng duplicate chính xác khi có từ 2. |
| Search không giới hạn và đếm toàn bộ. | Số entry nhận được trong lần search hoàn tất. | Tốn tài nguyên; server vẫn có thể giới hạn hoặc dữ liệu thay đổi. |
| Unique constraint/policy ở nguồn directory. | Có cơ chế ngăn dữ liệu trùng theo phạm vi/thuộc tính được định nghĩa. | Cách enforce phụ thuộc server, schema/overlay và quy trình provisioning. |

Nếu uniqueness là điều kiện quan trọng cho đăng nhập, phân quyền hoặc gắn danh tính, hãy enforce nó ở **quy trình tạo/cập nhật directory** và có kiểm tra reconciliation. Việc chỉ giới hạn search về 1 kết quả không sửa được dữ liệu đã trùng.

## 7. Repository query method: chọn kiểu trả về đúng hợp đồng

Spring Data LDAP hỗ trợ derived query method theo tên phương thức. Ví dụ:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=employees", objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
})
public class Person {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "employeeNumber")
    private String employeeNumber;

    @Attribute(name = "departmentCode")
    private String departmentCode;

    // Constructor khong tham so, getters va setters theo ODM.
}

public interface PersonRepository extends LdapRepository<Person> {

    // Có thể trả về 0, 1 hoặc nhiều kết quả.
    List<Person> findByDepartmentCode(String departmentCode);

    // Hợp đồng tối đa một kết quả.
    Optional<Person> findByEmployeeNumber(String employeeNumber);

    // Tối đa hai entry để kiểm tra duplicate.
    List<Person> findTop2ByUid(String uid);

    // Giới hạn kết quả theo tiêu chí sắp xếp có ý nghĩa.
    List<Person> findTop5ByDepartmentCodeOrderByUidAsc(
            String departmentCode);
}
~~~

Các điểm cần nhớ:

- `List<T>` thích hợp khi nghiệp vụ chấp nhận nhiều kết quả.
- `Optional<T>` thích hợp khi tối đa một kết quả; duplicate sẽ gây lỗi cardinality.
- `Top/First` giới hạn số kết quả trả về. Nó **không phải kiểm tra uniqueness** và không thay thế quy tắc chọn dữ liệu.
- `OrderBy` chỉ có ý nghĩa nếu store/server hỗ trợ tiêu chí sắp xếp và quy tắc matching phù hợp; cần kiểm thử trên directory thực tế.
- Các query method được phân tích theo property/entity mapping. Tên thuộc tính Java phải ánh xạ đúng LDAP attribute/schema.

### 7.1. Không dùng `findAll()` cho một câu hỏi đơn giản

Đoạn sau thường không cần thiết:

~~~java
// Tốn tài nguyên: tải toàn bộ entry rồi mới lọc ở Java.
List<Person> all = personRepository.findAll();
return all.stream()
        .filter(p -> uid.equals(p.getUid()))
        .findFirst();
~~~

Thay bằng query cụ thể:

~~~java
List<Person> matches = personRepository.findByUid(uid);
~~~

Hoặc `findOne(query)`/`Optional<Person>` khi có hợp đồng duy nhất. Search có base DN và filter cụ thể giúp directory xử lý truy vấn phù hợp hơn, giảm payload và tránh đọc những entry không cần thiết.

## 8. Một entity có thể ánh xạ không đầy đủ hoặc khác dự kiến

Một LDAP entry là tập attribute có thể đa trị, chịu schema và ACL. Không phải mọi attribute đều bắt buộc có mặt ở mọi entry.

Ví dụ:

~~~ldif
dn: uid=lan.nguyen,ou=employees,dc=corp,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan.nguyen
cn: Lan Nguyen
sn: Nguyen
mail: lan.nguyen@example.org
telephoneNumber: +84-28-5555-0100
telephoneNumber: +84-28-5555-0101
~~~

`telephoneNumber` có hai giá trị. Nếu mapper chỉ gọi `attribute.get()`, nó chỉ đọc một giá trị đầu tiên và bỏ qua phần còn lại.

### 8.1. Phân biệt attribute thiếu với giá trị rỗng

Trong JNDI, `Attributes.get("mail")` có thể trả `null` nếu attribute không tồn tại. Nếu attribute tồn tại, `Attribute` có thể có một hoặc nhiều giá trị. Đừng gọi `get()` mà không kiểm tra:

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

static String textOrNull(Attributes attrs, String name)
        throws NamingException {
    Attribute attribute = attrs.get(name);
    if (attribute == null || attribute.size() == 0) {
        return null;
    }
    Object value = attribute.get();
    return value == null ? null : value.toString();
}

static List<String> allTextValues(Attributes attrs, String name)
        throws NamingException {
    Attribute attribute = attrs.get(name);
    if (attribute == null) {
        return List.of();
    }

    List<String> values = new ArrayList<>();
    NamingEnumeration<?> enumeration = attribute.getAll();
    try {
        while (enumeration.hasMore()) {
            Object value = enumeration.next();
            values.add(value.toString());
        }
    } finally {
        enumeration.close();
    }
    return List.copyOf(values);
}
~~~

Hai helper phân biệt:

- **Không có attribute:** trả `null`/danh sách rỗng.
- **Có một giá trị:** trả một giá trị.
- **Có nhiều giá trị:** trả toàn bộ giá trị trong danh sách.
- **Lỗi đọc attribute:** ném `NamingException` để tầng trên phân loại; không âm thầm coi như attribute không tồn tại.

Nếu attribute là binary như `jpegPhoto`, `objectGUID` hoặc certificate, không gọi `toString()` rồi coi là dữ liệu text. Dùng kiểu byte[]/binary mapping và quy tắc chuyển đổi theo schema/provider.

### 8.2. Trường bắt buộc và tùy chọn

Một DTO có thể phân biệt:

~~~java
import java.util.List;

public record PersonView(
        String uid,
        String commonName,
        String surname,
        String email,
        List<String> telephoneNumbers) {
}
~~~

Mapper:

~~~java
import org.springframework.ldap.core.AttributesMapper;

AttributesMapper<PersonView> personMapper = attrs -> {
    String uid = textOrNull(attrs, "uid");
    String cn = textOrNull(attrs, "cn");
    String sn = textOrNull(attrs, "sn");
    String mail = textOrNull(attrs, "mail");
    List<String> phones = allTextValues(attrs, "telephoneNumber");

    if (uid == null || uid.isBlank()) {
        throw new IllegalStateException(
                "LDAP entry thieu uid bat buoc");
    }
    if (cn == null || cn.isBlank()) {
        throw new IllegalStateException(
                "LDAP entry thieu cn bat buoc");
    }

    return new PersonView(uid, cn, sn, mail, phones);
};
~~~

Khi dùng mapper này, projection của query phải yêu cầu đủ `uid`, `cn`, `sn`, `mail` và `telephoneNumber`. Nếu query chỉ trả `uid`/`cn`, mapper sẽ không thể đọc được các thuộc tính còn lại dù chúng có tồn tại trên entry.

Trong ví dụ, `uid` và `cn` là bắt buộc theo hợp đồng ứng dụng; `sn`, `mail` và số điện thoại có thể tùy chọn tùy nghiệp vụ/schema. Nếu `sn` bắt buộc theo objectClass mà entry thiếu, cần xem đây là **dữ liệu không hợp lệ hoặc schema violation**, không mặc định thay bằng chuỗi rỗng.

### 8.3. Trường hợp objectClass không như dự kiến

Search filter nên chỉ định `objectClass` phù hợp:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=employees")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uid);
~~~

Nếu chỉ tìm `(uid=...)`, một entry thiết bị/dịch vụ/nhóm có cùng attribute `uid` (nếu schema/provider cho phép) có thể xuất hiện. `objectClass` giúp giới hạn loại entry, nhưng mapper vẫn cần xác minh các trường cần thiết. Không suy ra kiểu Java chỉ từ tên DN.

## 9. Kết quả ngoài dự kiến: phân loại trước khi phản hồi

Một search không phải lúc nào cũng chỉ trả 0/1/N. Directory có thể trả lỗi hoặc một phần dữ liệu.

| Tình huống | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Input rỗng/sai định dạng | Validation lỗi trước khi query. | Từ chối input; không gửi filter rộng. |
| DN/base không tồn tại | Naming exception hoặc kết quả phụ thuộc overload/provider. | Kiểm tra context base và DN tương đối; không tự đổi thành user không tồn tại toàn hệ thống. |
| Không có filter match | Search hoàn tất và trả list rỗng. | Trả NOT_FOUND theo phạm vi đã tìm. |
| Nhiều entry | List có từ 2 entry hoặc exact-one API báo cardinality error. | Trả AMBIGUOUS, điều tra dữ liệu trùng. |
| Thiếu attribute | Mapper thấy `attrs.get(name) == null`. | Áp quy tắc required/optional, báo INVALID_DATA nếu cần. |
| Attribute đa trị | `Attribute.size() > 1`. | Đọc toàn bộ giá trị hoặc xác định quy tắc chọn. |
| Invalid credentials | LDAP result code 49. | Kiểm tra bind DN/secret; không coi là NOT_FOUND. |
| Insufficient access | LDAP result code 50 hoặc attribute/entry bị ẩn. | Kiểm tra ACL của bind account và quyền caller. |
| Size limit | `sizeLimitExceeded` (code 4) hoặc kết quả bị giới hạn. | PARTIAL/FAILED; paging nếu use case cần đọc hết và server hỗ trợ. |
| Time limit | `timeLimitExceeded` (code 3). | Thu hẹp query, kiểm tra server; không trả empty list như thành công. |
| Admin limit | `adminLimitExceeded` (code 11). | Tuân thủ policy, điều chỉnh truy vấn/concurrency. |
| Referral/partial result | ReferralException hoặc PartialResultException tùy provider. | Theo chính sách referral; nếu bỏ nhánh thì kết quả không đầy đủ. |
| Connection/TLS | Communication/SSL exception. | Phân loại hạ tầng; không đổi thành NOT_FOUND. |
| Mapper failure | NamingException, sai kiểu hoặc validation exception. | Ghi nhận lỗi mapping/data quality và không công bố kết quả đầy đủ. |
| Replica stale | Kết quả khác giữa endpoint. | Xem replication lag và nguồn có thẩm quyền. |

### 9.1. Lỗi LDAP không phải lúc nào cũng được ném cùng một kiểu

Spring LDAP dịch các lỗi JNDI thành exception thuộc hệ phân cấp data access của Spring. Kiểu cụ thể có thể phụ thuộc lỗi gốc và phiên bản/provider. Tầng service nên phân loại theo **root cause/LDAP result code**, không chỉ bắt một exception tổng quát rồi trả HTTP 404.

Ví dụ mapping ở tầng API:

| Trạng thái service | HTTP response gợi ý |
| --- | --- |
| NOT_FOUND | 404 nếu tài nguyên thực sự không tồn tại trong phạm vi được phép. |
| FOUND | 200. |
| AMBIGUOUS | 409 hoặc lỗi nghiệp vụ có mã riêng. |
| INVALID_DATA | 502/500 tùy nguồn lỗi và hợp đồng API; ghi log data quality. |
| PARTIAL | 503 hoặc lỗi phụ thuộc có thông tin retry phù hợp; không trả dữ liệu như full success. |
| FAILED do hạ tầng | 503/504 tùy lỗi; không tiết lộ chi tiết LDAP nội bộ cho caller. |
| ACCESS_DENIED | 403 nếu quyền caller bị từ chối; lỗi ACL của service account có thể là lỗi cấu hình phụ thuộc. |

Đây là gợi ý thiết kế, không phải bảng HTTP mapping bắt buộc. Không trả bind DN, filter raw, credential, hostname nội bộ hoặc stack trace cho client.

## 10. Đừng nhầm “không tìm thấy” với “không được phép thấy”

LDAP ACL có thể giới hạn việc search hoặc đọc attribute. Ví dụ service account chỉ được phép đọc `ou=employees`, nhưng API lại tìm ở root `dc=corp,dc=example`. Một số server có thể trả lỗi; một số tình huống có thể ẩn entry/attribute theo policy.

Vì vậy:

- List rỗng có nghĩa **không có entry được trả về** trong phạm vi và quyền hiện tại.
- Nó không chứng minh người dùng không tồn tại ở mọi naming context hoặc dưới tài khoản khác.
- Thiếu attribute có thể do entry thật sự không có, do projection, hoặc do quyền đọc; cần kiểm tra ACL/schema.
- Nếu service account có quyền rộng hơn caller HTTP, tầng ứng dụng phải kiểm tra tenant/ownership trước khi trả entry.
- Không dùng tài khoản quản trị để xác nhận user tồn tại rồi tiết lộ kết quả cho người gọi không đủ quyền.

### 10.1. Quy tắc cho endpoint tìm kiếm

Một endpoint tìm người dùng nên:

1. Xác thực caller và kiểm tra authority.
2. Xác định tenant/OU caller được phép tra cứu.
3. Validate UID/name và giới hạn độ dài input.
4. Dùng `LdapQueryBuilder`/query method có tham số; không ghép filter thô.
5. Chỉ yêu cầu attribute cần trả về.
6. Phân biệt 0/1/N và partial/error.
7. Không log toàn bộ entry, DN nhạy cảm hoặc filter có PII.

## 11. Filter an toàn và query annotation

### 11.1. Derived query method

Ví dụ:

~~~java
List<Person> findByUid(String uid);
Optional<Person> findByEmployeeNumber(String employeeNumber);
~~~

Derived query method tạo predicate dựa trên property được ánh xạ. Giá trị tham số được xử lý theo cơ chế query của Spring Data LDAP; vẫn cần test ký tự đặc biệt theo version và không cho client chọn tên attribute tùy ý.

### 11.2. Dùng `LdapQueryBuilder`

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=employees")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(userInput);
~~~

Builder phù hợp khi muốn cố định cấu trúc filter và chỉ truyền giá trị. Ví dụ input `lan*)(uid=*)` phải được coi là **giá trị literal**, không được phép mở rộng filter thành điều kiện mới.

### 11.3. Cẩn trọng với `@Query`, SpEL và property placeholders

Spring Data LDAP hỗ trợ `@Query` với named/positional parameter binding. Tham số chuỗi trong declared query được mã hóa theo RFC 2254 (tiền thân của RFC 4515) theo tài liệu Spring Data LDAP. Tuy nhiên, **SpEL expressions và property placeholders không tự động được escape**; khi sử dụng phải đảm bảo giá trị được mã hóa đúng ngữ cảnh, ví dụ bằng helper `LdapEncoder` phù hợp.

Ví dụ declared query:

~~~java
@Query("(&(objectClass=inetOrgPerson)(mail=:email))")
Optional<Person> findByMail(String email);
~~~

Không đưa một filter hoàn chỉnh do client gửi vào `@Query`, SpEL hoặc placeholder. Filter là cấu trúc điều khiển truy vấn; chỉ bind các giá trị cần thiết và kiểm tra encoding.

### 11.4. DN escaping khác filter escaping

Nếu tìm theo DN, dùng `LdapNameBuilder`/`LdapName` để tạo tên có cấu trúc. Nếu tìm theo giá trị attribute, dùng filter builder/encoder. Không lấy chuỗi DN đã escape rồi dùng như filter assertion value. Hai chuẩn khác nhau:

- DN string: RFC 4514.
- Search filter: RFC 4515.

## 12. Chọn một kết quả theo thứ tự có ý nghĩa — khi nào được?

Có nghiệp vụ thật sự muốn lấy “bản ghi ưu tiên” trong nhiều kết quả, ví dụ hồ sơ đang hoạt động thay vì hồ sơ lưu trữ. Khi đó phải định nghĩa tiêu chí lựa chọn rõ ràng:

1. Filter chỉ chọn trạng thái hợp lệ nếu schema/dữ liệu cho phép.
2. Thứ tự sắp xếp phải được server/store hỗ trợ và có khóa tie-breaker ổn định.
3. Nếu hai entry vẫn cùng ưu tiên, trả AMBIGUOUS thay vì chọn tùy ý.
4. Ghi nhận lý do lựa chọn để audit.

Ví dụ query method:

~~~java
List<Person> findTop5ByDepartmentCodeOrderByUidAsc(
        String departmentCode);
~~~

Phương thức này giới hạn kết quả và yêu cầu thứ tự theo `uid` theo khả năng của store. Nó phù hợp cho danh sách gợi ý có quy tắc sắp xếp, **không chứng minh** rằng một UID là duy nhất.

Không viết:

~~~java
Person selected = matches.get(0);
~~~

trừ khi kết quả đã được sắp xếp theo quy tắc nghiệp vụ và việc lấy đầu tiên là hành vi được đặc tả. Thứ tự kết quả LDAP không nên được coi là thứ tự ổn định nếu ứng dụng không yêu cầu/kiểm soát sort.

## 13. Kiểm thử cardinality và kết quả bất thường

Một bộ test tốt cần kiểm tra cả **hợp đồng trả về** và **directory thực tế**.

### 13.1. Unit test cho xử lý 0/1/N

Nếu service đã tách phần quyết định cardinality thành một hàm thuần:

~~~java
import java.util.List;
import java.util.Objects;

public final class Cardinality {
    private Cardinality() {}

    public enum Kind { NOT_FOUND, ONE, MULTIPLE }

    public static Kind classify(List<?> values) {
        Objects.requireNonNull(values, "values");
        if (values.isEmpty()) {
            return Kind.NOT_FOUND;
        }
        if (values.size() == 1) {
            return Kind.ONE;
        }
        return Kind.MULTIPLE;
    }
}
~~~

JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class CardinalityTest {

    @Test
    void classifiesNoMatch() {
        assertEquals(Cardinality.Kind.NOT_FOUND,
                Cardinality.classify(List.of()));
    }

    @Test
    void classifiesSingleMatch() {
        assertEquals(Cardinality.Kind.ONE,
                Cardinality.classify(List.of("lan")));
    }

    @Test
    void classifiesMultipleMatches() {
        assertEquals(Cardinality.Kind.MULTIPLE,
                Cardinality.classify(List.of("lan-a", "lan-b")));
    }
}
~~~

Hàm này chỉ phân loại một list **đã có**. Nó không xác minh LDAP search hoàn tất, ACL hoặc server size limit; nếu query ném exception, không truyền list partial vào hàm rồi gọi là NOT_FOUND.

### 13.2. Kiểm thử repository method

Giả sử repository:

~~~java
public interface PersonRepository extends LdapRepository<Person> {
    List<Person> findByUid(String uid);
    Optional<Person> findByEmployeeNumber(String employeeNumber);
}
~~~

Với fixture test có dữ liệu kiểm soát:

| Dữ liệu trong OU test | Gọi method | Kỳ vọng |
| --- | --- | --- |
| Không có UID | `findByUid("unknown")` | List rỗng. |
| Một entry UID=lan | `findByUid("lan")` | List có một phần tử. |
| Hai entry UID=lan ở hai OU | `findByUid("lan")` với base phù hợp | List có hai phần tử nếu cả hai nằm trong scope/ACL. |
| Không có employeeNumber | `findByEmployeeNumber("E-404")` | `Optional.empty()`. |
| Một employeeNumber duy nhất | `findByEmployeeNumber("E-100")` | Optional có giá trị. |
| Hai entry cùng employeeNumber | `findByEmployeeNumber("E-100")` | `IncorrectResultSizeDataAccessException`. |

Test repository phải dùng directory test hoặc test container đã được cấu hình; không giả định mock repository chứng minh được server matching rule hoặc ACL.

Ví dụ integration test với fixture đã được nạp vào **OU test riêng**:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("ldap-test")
@EnabledIfEnvironmentVariable(
        named = "LDAP_INTEGRATION_TEST", matches = "true")
class PersonRepositoryCardinalityIT {

    @Autowired
    PersonRepository repository;

    @Test
    void optionalIsEmptyWhenNoEntryMatches() {
        assertTrue(repository.findByEmployeeNumber("E-NOT-FOUND").isEmpty());
    }

    @Test
    void optionalRejectsDuplicateEmployeeNumber() {
        // Fixture test có hai entry khác DN nhưng cùng employeeNumber=E-DUP.
        assertThrows(IncorrectResultSizeDataAccessException.class,
                () -> repository.findByEmployeeNumber("E-DUP"));
    }
}
~~~

Test này cần fixture `E-DUP` tồn tại trong base/scope mà repository thực sự tìm kiếm; hai entry phải có DN khác nhau nhưng cùng employeeNumber. Không chạy với directory production và không tự xóa dữ liệu ngoài OU test. Khi test báo rỗng, hãy xác minh fixture, base DN, scope và ACL trước khi kết luận query method sai.

### 13.3. Kiểm thử `LdapTemplate.searchForObject` và `search`

| Số entry trong fixture | API | Kỳ vọng |
| --- | --- | --- |
| 0 | `search(query, mapper)` | List rỗng nếu search kết thúc bình thường. |
| 1 | `search(query, mapper)` | List một phần tử. |
| 2 | `search(query, mapper)` | List hai phần tử. |
| 0 | `searchForObject(query, mapper)` | `IncorrectResultSizeDataAccessException`. |
| 1 | `searchForObject(query, mapper)` | Trả object duy nhất. |
| 2 | `searchForObject(query, mapper)` | `IncorrectResultSizeDataAccessException`. |

### 13.4. Ma trận kiểm thử dữ liệu ngoài dự kiến

| Tình huống | Dữ liệu/thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Thiếu `mail` | Entry không có mail. | Mapper trả null nếu mail tùy chọn; nếu bắt buộc, báo INVALID_DATA. |
| Thiếu `uid` | Entry không có uid. | Không tạo Person hợp lệ; báo data quality/mapping error. |
| Nhiều `telephoneNumber` | Attribute có hai giá trị. | Mapper giữ cả hai nếu DTO hỗ trợ collection. |
| Attribute binary | `objectGUID` hoặc ảnh. | Không ép qua `toString()`; xử lý byte[]. |
| Sai objectClass | Entry là nhóm hoặc thiết bị. | Filter loại entry ngoài phạm vi; mapper xác minh schema/type. |
| UID trùng | Hai OU có cùng UID. | Cardinality MULTIPLE; không lấy phần tử đầu. |
| Case/matching rule | UID khác hoa/thường. | Ghi nhận hành vi theo matching rule/schema server. |
| Rename/move | DN cũ không còn, DN mới tồn tại. | Lookup DN cũ thất bại; search theo stable identifier có thể tìm được DN mới. |
| Base DN sai | OU test không tồn tại. | Phân loại base/name error theo API/provider, không giả định là filter không khớp. |
| ACL thiếu | Reader không có quyền search/read. | Phân biệt access error/attribute visibility với NOT_FOUND. |
| Referral | Query đi qua partition có referral. | Theo policy; partial result không được báo full success. |
| Size/time limit | Fixture/query vượt policy test. | FAILED/PARTIAL; không coi số đã nhận là total. |
| Server mất kết nối | Ngắt giữa search. | Lỗi hạ tầng; retry có giới hạn nếu phù hợp. |
| Mapper exception | Entry sai kiểu hoặc field bắt buộc thiếu. | Scan/search bị lỗi theo hợp đồng; không bỏ qua âm thầm. |

### 13.5. Test filter injection

Đầu vào thử:

~~~text
lan*)(|(uid=*))
~~~

Khi dùng `LdapQueryBuilder.where("uid").is(input)`, giá trị phải được mã hóa như assertion value, không được làm thay đổi cấu trúc filter. Kiểm thử cả những ký tự đặc biệt của RFC 4515 như `*`, `(`, `)`, `\` và NUL (nếu validation cho phép chuỗi đi tới tầng builder). Không tự escape bằng replace thủ công.

## 14. Quan sát và vận hành kết quả search

Để biết hệ thống có dữ liệu trùng hoặc lỗi bất thường, ghi các số liệu cardinality ở mức an toàn:

| Metric/log field | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `ldap.search.duration` | Thời gian search. | Theo dõi p50/p95/p99. |
| `ldap.search.result_count` | Số entry nhận được trong một search hoàn tất. | Không gọi là total nếu bị giới hạn/partial. |
| `ldap.search.outcome` | `NOT_FOUND`, `FOUND`, `MULTIPLE`, `PARTIAL`, `FAILED`. | Enum cardinality thấp. |
| `ldap.search.duplicate_detected` | Số lần phát hiện từ hai entry khớp. | Theo dõi lỗi dữ liệu. |
| `ldap.search.mapping_failures` | Lỗi mapper/schema/data quality. | Không log toàn entry. |
| `ldap.search.access_denied` | Lỗi ACL/authorization. | Phân biệt HTTP caller và LDAP bind identity. |
| `ldap.search.referral_partial` | Search bị referral/partial. | Ghi trạng thái completeness. |
| `ldap.search.limit_exceeded` | Server time/size/admin limit. | Không biến thành NOT_FOUND. |

Không gắn `uid`, email, DN hoặc filter nguyên bản làm metric label. Chúng có cardinality lớn và chứa dữ liệu cá nhân/cấu trúc directory. Nếu cần điều tra một request, dùng correlation ID và log có quyền truy cập hạn chế; che hoặc băm định danh theo chính sách tổ chức.

### 14.1. Ví dụ log kết quả an toàn

~~~json
{
  "event": "ldap_search_completed",
  "operation": "find_person_by_uid",
  "base_alias": "employees",
  "scope": "SUBTREE",
  "result_count": 2,
  "outcome": "MULTIPLE",
  "elapsed_ms": 37,
  "correlation_id": "req-83ac"
}
~~~

Đây là log giả minh họa. Không đưa toàn bộ DN/UID hoặc nội dung entry vào log mặc định. Khi kết quả nhiều, ghi outcome MULTIPLE và tạo sự kiện xử lý dữ liệu trùng; không log mọi thuộc tính của hai người chỉ để báo lỗi.

## 15. Bài tập tình huống

Một hệ thống HR dùng Spring Data LDAP để tìm nhân viên theo `employeeNumber`. Directory có base `dc=corp,dc=example`:

~~~text
dc=corp,dc=example
├── ou=employees
│   ├── uid=lan
│   │   ├── employeeNumber: E-100
│   │   └── mail: lan@example.org
│   └── uid=minh
│       └── employeeNumber: E-101
└── ou=contractors
    └── uid=lan-old
        └── employeeNumber: E-100
~~~

Service hiện tại:

~~~java
Person findEmployee(String employeeNumber) {
    return repository.findByEmployeeNumber(employeeNumber)
            .orElse(null);
}
~~~

Nhóm phát hiện một số request trả sai người vì employeeNumber `E-100` xuất hiện hai lần ở hai OU. Một số entry khác không có `mail`, và đôi khi search trả partial khi directory referral sang partition contractor.

**Yêu cầu:**

1. Vì sao `Optional<Person>` không tự giải quyết duplicate?
2. Với repository query method trả Optional, kết quả khi có hai entry sẽ như thế nào?
3. Nên chọn base DN và scope nào nếu use case chỉ tìm nhân viên chính thức? Nếu cần cả contractor thì sao?
4. Viết query trả `List<Person>` và cách phát hiện 0/1/N.
5. Khi chỉ cần biết có duplicate hay không, vì sao `countLimit(2)` phù hợp?
6. Nếu muốn yêu cầu đúng một entry và coi cả 0 lẫn nhiều là lỗi, dùng API nào của `LdapTemplate`?
7. Nếu muốn 0 kết quả là bình thường nhưng duplicate là lỗi, dùng API nào của `LdapRepository`?
8. `mail` không có trong entry: khi nào mapper trả null, khi nào báo INVALID_DATA?
9. Attribute `telephoneNumber` có nhiều giá trị: mapper nên biểu diễn thế nào?
10. Search gặp `PartialResultException` khi theo referral: có được trả empty list và kết luận employee không tồn tại không?
11. Làm sao phân biệt caller không có quyền với bind account không có quyền đọc?
12. Đề xuất cách phát hiện, sửa và ngăn duplicate employeeNumber trong quy trình provisioning.

**Gợi ý đáp án:**

- `Optional` chỉ mô tả 0 hoặc 1 kết quả; khi có nhiều, Spring Data LDAP ném `IncorrectResultSizeDataAccessException`.
- Nếu chỉ tìm nhân viên chính thức, dùng base `ou=employees`. Nếu cần contractor, mở rộng phạm vi có chủ đích và xử lý định danh trùng giữa hai OU.
- `List` cho phép phân loại 0/1/N; `countLimit(2)` đủ biết có ít nhất hai, không cần tải mọi duplicate.
- `LdapTemplate.searchForObject` yêu cầu đúng một và ném lỗi nếu 0 hoặc nhiều; `LdapRepository.findOne(query)` trả Optional rỗng khi 0 và ném khi nhiều.
- `mail` tùy chọn thì null; nếu nghiệp vụ/schema yêu cầu bắt buộc thì INVALID_DATA. Nhiều phone nên dùng List.
- Partial result không chứng minh không tồn tại; phải đánh dấu PARTIAL/FAILED và kiểm tra referral.
- Spring Security kiểm tra caller/tenant; LDAP ACL kiểm tra service bind identity.
- Cần unique constraint/overlay hoặc quy trình provisioning kiểm tra uniqueness trong phạm vi toàn bộ naming context được quản lý, kèm reconciliation theo stable ID.

## 16. Ghi nhớ

**Kết quả tìm kiếm LDAP phải được xử lý theo cardinality và trạng thái hoàn tất.** `LdapTemplate.search` trả danh sách để xử lý 0/1/N; `searchForObject`/`searchForContext` đòi đúng một và ném `IncorrectResultSizeDataAccessException` nếu 0 hoặc nhiều; `LdapRepository.findOne(query)` trả `Optional.empty()` khi 0, trả entry khi 1 và ném lỗi cardinality khi nhiều. Query method trả `List` dành cho nhiều kết quả, còn `Optional` ngụ ý tối đa một.

Không lấy phần tử đầu tiên để che giấu duplicate. Không coi lỗi ACL, referral, timeout, size limit, mapper hoặc kết quả partial là NOT_FOUND. Hãy xác định base/scope/filter/`objectClass` chính xác, map attribute thiếu/đa trị theo schema, dùng stable identifier khi cần đồng bộ và kiểm thử với directory thật. Khi hợp đồng tìm kiếm được thể hiện rõ ở kiểu trả về và trạng thái service, ứng dụng sẽ tránh được việc chọn nhầm danh tính và dễ quan sát lỗi dữ liệu hơn.

### Tài liệu tham khảo

- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html)
- [Spring Data LDAP — Defining Query Methods and Limiting Results](https://docs.spring.io/spring-data/ldap/reference/repositories/query-methods-details.html)
- [Spring Data LDAP API — LdapRepository](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapRepository.html)
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP Reference — Query Builder](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [RFC 4511 — LDAPv3 Protocol and Search Operation](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515)
