# Search domain object bằng LdapQuery

Trong Spring LDAP, **Object-Directory Mapping (ODM)** ánh xạ entry của thư mục LDAP thành đối tượng Java có annotation như `@Entry`, `@Id` và `@Attribute`. Khi cần tìm các đối tượng đó theo điều kiện nghiệp vụ, ứng dụng có thể tạo `LdapQuery` bằng `LdapQueryBuilder` và truyền vào `LdapTemplate.find(...)` hoặc `LdapTemplate.findOne(...)`. Kết quả được chuyển trực tiếp thành domain object, giúp tầng nghiệp vụ làm việc với Java thay vì tự đọc `Attributes` hoặc `DirContext` ở mỗi truy vấn.

Bài học này trình bày cách **search domain object bằng `LdapQuery`**: định nghĩa entity ODM, dựng truy vấn LDAP an toàn, lựa chọn `find`/`findOne`, giới hạn base và search scope, xử lý kết quả/ngoại lệ, và kiểm soát chi phí tìm kiếm. Các ví dụ giả định `ContextSource` và `LdapTemplate` đã kết nối LDAP thành công; cấu hình xác thực, TLS, pooling và quyền truy cập cần được thực hiện trong cấu hình ứng dụng.

## 1. Luồng từ LdapQuery tới domain object

Giả sử thư mục chứa những người dùng sau, trong đó `dc=example,dc=org` là base DN của kết nối:

```text
dc=example,dc=org
└── ou=people
    ├── uid=an
    │   ├── objectClass: inetOrgPerson
    │   ├── uid: an
    │   ├── cn: An Nguyen
    │   └── sn: Nguyen
    └── ou=engineering
        └── uid=linh
            ├── objectClass: inetOrgPerson
            ├── uid: linh
            ├── cn: Linh Tran
            └── sn: Tran
```

Khi ứng dụng gọi `ldapTemplate.find(query, PersonEntry.class)`, các bước khái quát là:

```text
LdapQueryBuilder                       @Entry/@Id/@Attribute
    │                                     │
    ▼                                     ▼
LdapQuery (base, scope, filter, ...)    ODM metadata cho PersonEntry
    └─────────────────┬───────────────────┘
                      ▼
             LdapTemplate.find(...)
                      │
                      ▼
         LDAP server tìm entry phù hợp
                      │
                      ▼
            ObjectDirectoryMapper
                      │
                      ▼
                List<PersonEntry>
```

Hai điều kiện khác nhau cùng tham gia:

- **`LdapQuery`** chỉ định *tìm ở đâu và theo điều kiện nào*: base DN, scope, filter, giới hạn số lượng, thời gian.
- **`PersonEntry.class`** chỉ định *entry thuộc loại đối tượng nào và ánh xạ ra sao*. Spring LDAP dùng metadata `@Entry` để giới hạn kết quả theo loại entity, rồi ánh xạ các attribute LDAP vào trường Java.

Một `LdapQuery` không chứa logic tự ánh xạ Java; việc chuyển đổi được thực hiện bởi ODM. Ngược lại, việc khai báo `@Entry` không thay thế việc đặt base hoặc filter phù hợp cho truy vấn nghiệp vụ.

## 2. Khai báo domain object bằng ODM

Entry LDAP mẫu:

```ldif
dn: uid=linh,ou=engineering,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Tran
sn: Tran
mail: linh@example.org
```

Entity tương ứng:

```java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    },
    base = "ou=people"
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

Trong ví dụ:

- `@Entry` khai báo các `objectClass` phù hợp và `base` phục vụ tính DN của loại entity. Với tìm kiếm, hãy **đặt base trên `LdapQuery`** để chủ động chọn nhánh thư mục cần duyệt.
- `@Id` đánh dấu trường `Name` chứa distinguished name (DN) của entry. DN không phải một attribute như `uid` hoặc `mail`.
- `@Attribute(name = "...")` nối tên trường Java với tên attribute LDAP; vì `fullName` khác `cn`, annotation này là cần thiết.
- Việc ODM ánh xạ entry còn phụ thuộc dữ liệu thực tế, LDAP schema, quyền đọc attribute và quy tắc chuyển kiểu. Các trường không được trả về có thể không được điền đầy đủ.

**Lưu ý về base:** Ở đây, `ContextSource` đã có base `dc=example,dc=org`, nên truy vấn `query().base("ou=people")` tìm bên dưới `ou=people,dc=example,dc=org`. Tránh lặp cả `dc=example,dc=org` trong query nếu nó đã nằm trong base DN của `ContextSource`.

## 3. Truy vấn nhiều domain object bằng find

Tác vụ: lấy những người có họ `Nguyen` trong toàn nhánh `ou=people`.

```java
import java.util.List;

import org.springframework.ldap.core.LdapOperations;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PersonDirectory {
    private final LdapOperations ldap;

    public PersonDirectory(LdapOperations ldap) {
        this.ldap = ldap;
    }

    public List<PersonEntry> findBySurname(String surname) {
        if (surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("Surname không được rỗng");
        }

        LdapQuery q = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .countLimit(100)
            .timeLimit(5_000)
            .where("sn").is(surname);

        return ldap.find(q, PersonEntry.class);
    }
}
```

`ldap.find(q, PersonEntry.class)` trả về `List<PersonEntry>`: nếu không có entry phù hợp thì thông thường là danh sách rỗng. ODM chỉ trả những entry vừa khớp filter LDAP vừa tương ứng với metadata của `PersonEntry`. Ở phía server, filter nghiệp vụ cơ bản là `(sn=Nguyen)` (Spring LDAP có thể bổ sung điều kiện object class của entity).

Vì `SearchScope.SUBTREE` bao phủ cả thư mục con, truy vấn trên cũng xét `uid=linh,ou=engineering,ou=people,...`. Nếu dùng `SearchScope.ONELEVEL`, chỉ các entry con trực tiếp của `ou=people` được xét. Vì vậy kết quả có thể khác nhau dù filter không đổi.

### So sánh các thao tác ODM

| Phương thức | Khi dùng | Kết quả mong đợi |
| --- | --- | --- |
| `find(LdapQuery, Class<T>)` | Tìm theo filter, có thể có nhiều kết quả | `List<T>`, có thể rỗng |
| `findOne(LdapQuery, Class<T>)` | Filter phải khớp đúng một entity | `T` hoặc ném ngoại lệ nếu 0/nhiều kết quả |
| `findAll(Class<T>)` | Cần lấy mọi entry tương ứng loại ODM | `List<T>`; cần thận trọng ở thư mục lớn |
| `findByDn(Name, Class<T>)` | Đã biết DN chính xác của entry | Truy xuất trực tiếp theo DN |
| `search(LdapQuery, AttributesMapper<T>)` | Muốn tự ánh xạ các LDAP attributes | Dùng callback mapper, không yêu cầu entity ODM |

Phương thức `search(...)` cũng có thể nhận `ContextMapper<T>` nếu cần làm việc với ngữ cảnh LDAP. Nó thích hợp khi ánh xạ đơn giản hoặc cấu trúc trả về không trùng một entity cố định. Trong bài này, `find(...)` mới là lựa chọn trọng tâm vì đối tượng được quản lý bằng ODM.

## 4. Tìm đúng một domain object bằng findOne

Đôi khi tầng nghiệp vụ kỳ vọng `uid` duy nhất trong phạm vi tìm kiếm. Khi đó:

```java
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Biến ldap có kiểu LdapOperations, đã được inject ở constructor.
public PersonEntry findExactlyOneByUid(String uid) {
    if (uid == null || uid.isBlank()) {
        throw new IllegalArgumentException("UID không hợp lệ");
    }

    LdapQuery q = query()
        .base("ou=people")
        .where("uid").is(uid);

    return ldap.findOne(q, PersonEntry.class);
}
```

`findOne` phân biệt rõ 3 trường hợp:

| Số entry ODM phù hợp | Kết quả `findOne` |
| --- | --- |
| Đúng 1 | Trả về `PersonEntry` |
| Không có | Ném `EmptyResultDataAccessException` |
| Trên 1 | Ném `IncorrectResultSizeDataAccessException` |

`EmptyResultDataAccessException` là một dạng cụ thể của `IncorrectResultSizeDataAccessException`. Nếu muốn coi người dùng vắng mặt là tình huống bình thường, có thể chuyển riêng ngoại lệ này thành `Optional.empty()`, đồng thời **để nguyên lỗi nhiều kết quả** vì nó cho thấy giả định duy nhất đã bị vi phạm:

```java
import java.util.Optional;
import org.springframework.dao.EmptyResultDataAccessException;

public Optional<PersonEntry> findOptionalByUid(String uid) {
    try {
        return Optional.of(findExactlyOneByUid(uid));
    } catch (EmptyResultDataAccessException ex) {
        return Optional.empty();
    }
}
```

Không nên tự ý đặt `countLimit(1)` để ép `findOne` thành công: giới hạn một kết quả có thể che giấu việc `uid` bị trùng ở các nhánh khác nhau. Tính duy nhất phải đến từ cấu trúc directory, ràng buộc nghiệp vụ hoặc filter đủ hẹp (ví dụ tìm trong một OU xác định).

## 5. Viết filter bằng LdapQueryBuilder

`LdapQueryBuilder.query()` hỗ trợ DSL kết hợp điều kiện mà không cần nối chuỗi filter LDAP thủ công.

**Tìm người có họ Nguyen và có email:**

```java
LdapQuery q = query()
    .base("ou=people")
    .where("sn").is("Nguyen")
    .and("mail").isPresent();

List<PersonEntry> users = ldap.find(q, PersonEntry.class);
```

Điều kiện tương ứng về mặt ý nghĩa là `(&(sn=Nguyen)(mail=*))`. Metadata `@Entry` còn có thể dẫn đến phần lọc object class bổ sung.

**Tìm người có một trong hai họ:**

```java
LdapQuery q = query()
    .base("ou=people")
    .where("sn").is("Nguyen")
    .or("sn").is("Tran");

List<PersonEntry> users = ldap.find(q, PersonEntry.class);
```

**Tìm attribute có dạng tiền tố có chủ đích:**

```java
LdapQuery q = query()
    .base("ou=people")
    .where("cn").like("Linh*");
```

Các phép điều kiện thông dụng:

| DSL | Mục đích | Minh họa |
| --- | --- | --- |
| `is(value)` | Bằng giá trị đã chỉ định | `where("uid").is("linh")` |
| `isPresent()` | Attribute tồn tại | `where("mail").isPresent()` |
| `like(pattern)` | So khớp mẫu, có wildcard | `where("cn").like("An*")` |
| `not().is(value)` | Không bằng giá trị | `where("sn").not().is("Tran")` |
| `and(...)` / `or(...)` | Kết hợp nhiều điều kiện | `where("sn").is("Nguyen").and("mail").isPresent()` |

**Thứ tự xây query:** các tùy chọn `base`, `searchScope`, `countLimit`, `timeLimit`, `attributes` phải thiết lập **trước** `where(...)`. Builder chặn việc thay các tham số search sau khi bắt đầu dựng filter.

### An toàn khi nhận đầu vào bên ngoài

Khi filter phụ thuộc dữ liệu người dùng, dùng các phương thức có xử lý escaping như `where("uid").is(uidInput)`. Không nối trực tiếp nội dung nhập vào filter:

```java
// Không an toàn: userInput có thể chứa cú pháp LDAP filter.
String unsafeFilter = "(uid=" + userInput + ")";
LdapQuery unsafe = query().filter(unsafeFilter);
```

Nếu phải mô tả filter phức tạp bằng cú pháp chuỗi, dùng dạng tham số hóa:

```java
LdapQuery safe = query()
    .base("ou=people")
    .filter("(&(uid={0})(mail={1}))", userInput, mailInput);
```

Dạng `filter(String, Object...)` mã hóa các tham số filter LDAP; dạng `filter(String)` nhận nguyên chuỗi và không tự escape. Không kết hợp `filter(...)` với `where(...)` trong cùng builder. Với `like(...)`, dấu `*` có ý nghĩa wildcard; chỉ dùng mẫu mà ứng dụng kiểm soát, không để chuỗi từ người dùng vô tình mở rộng điều kiện tìm kiếm.

Tránh ghi log toàn bộ DN, filter chứa dữ liệu cá nhân, email hoặc thông tin bí mật trong môi trường sản xuất. Filter đúng cú pháp không thay thế việc sử dụng tài khoản bind với quyền đọc tối thiểu và kết nối LDAPS hoặc StartTLS được cấu hình đúng.

## 6. Điều chỉnh base, scope và giới hạn kết quả

Truy vấn LDAP trên phạm vi quá rộng có thể trả hàng nghìn entry hoặc làm server tốn nhiều thời gian. `LdapQuery` cung cấp một số giới hạn:

```java
LdapQuery q = query()
    .base("ou=engineering,ou=people")
    .searchScope(SearchScope.ONELEVEL)
    .countLimit(50)
    .timeLimit(3_000)
    .where("objectClass").is("inetOrgPerson");

List<PersonEntry> people = ldap.find(q, PersonEntry.class);
```

Trong trường hợp này, giả định `ContextSource` base `dc=example,dc=org`:

- `base("ou=engineering,ou=people")`: nhánh bắt đầu tìm kiếm.
- `SearchScope.OBJECT`: chỉ entry tại base DN.
- `SearchScope.ONELEVEL`: chỉ các entry con trực tiếp của base.
- `SearchScope.SUBTREE`: base cùng toàn bộ hậu duệ.
- `countLimit(50)`: số kết quả trả về tối đa được yêu cầu ở mức tìm kiếm; **không phải phân trang**.
- `timeLimit(3_000)`: thời gian giới hạn cho thao tác tìm kiếm theo cơ chế LDAP/JNDI, tính bằng mili giây; **không thay thế timeout kết nối**.

Nên chọn base càng hẹp càng tốt và có index LDAP cho các attribute được lọc thường xuyên, chẳng hạn `uid` hoặc `mail` (cần DBA LDAP cấu hình theo server cụ thể). Một danh sách bị cắt do `countLimit` không đủ để kết luận rằng directory chỉ có từng ấy entry. Với dữ liệu lớn, sử dụng cơ chế LDAP paged results và xử lý kiểm tra cookie/continuation theo server, không biến `countLimit` thành số trang.

**Cẩn trọng với `attributes(...)` trong ODM:** mặc định LDAP trả về các attributes phù hợp cho mapper. Nếu tự giới hạn còn `attributes("cn")`, domain object có thể thiếu `uid`, `sn`, `mail` hoặc metadata mà ODM cần. Chỉ giới hạn thuộc tính khi đã kiểm tra đầy đủ các trường/kiểu đối tượng mà ODM phải ánh xạ. Nếu mục tiêu chỉ lấy một vài giá trị, đôi khi `AttributesMapper` phù hợp hơn việc tạo entity không đầy đủ.

## 7. Đóng gói thành repository và xử lý lỗi

Trong ứng dụng thực tế, nên tập trung cách dựng query và mapping ở một lớp truy cập directory. Đoạn dưới minh họa đầy đủ hơn:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.ldap.core.LdapOperations;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PersonRepository {
    private final LdapOperations ldap;

    public PersonRepository(LdapOperations ldap) {
        this.ldap = ldap;
    }

    public Optional<PersonEntry> findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid bắt buộc");
        }

        LdapQuery q = query()
            .base("ou=people")
            .where("uid").is(uid);

        try {
            return Optional.of(ldap.findOne(q, PersonEntry.class));
        } catch (EmptyResultDataAccessException ex) {
            return Optional.empty();
        }
    }

    public List<PersonEntry> findBySurname(String surname) {
        if (surname == null || surname.isBlank()) {
            return List.of();
        }

        LdapQuery q = query()
            .base("ou=people")
            .countLimit(100)
            .where("sn").is(surname);

        return ldap.find(q, PersonEntry.class);
    }
}
```

Ví dụ này không tự tạo `LdapTemplate` trong mỗi lời gọi. Ứng dụng cấu hình một `ContextSource` và một `LdapOperations`/`LdapTemplate` thích hợp để inject; phần quản lý connection, pooling và xác thực thuộc tầng cấu hình. Tránh đổi quyền xác thực hoặc cấu hình LDAP tùy tiện ở giữa một request.

Khi gặp lỗi, cần phân biệt:

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `find` trả danh sách rỗng | Sai base/scope/filter; object class không khớp entity; entry không nằm trong nhánh | Kiểm tra DN tương đối với `ContextSource`, `@Entry(objectClasses)` và filter nghiệp vụ |
| `findOne` ném `EmptyResultDataAccessException` | Không có object phù hợp sau khi lọc | Xử lý `Optional.empty()` nếu vắng mặt là hợp lệ |
| `findOne` ném `IncorrectResultSizeDataAccessException` (>1) | Có nhiều entry trùng điều kiện | Thu hẹp search base/filter; không dùng `countLimit(1)` để che lỗi |
| Mapping thất bại | Entity thiếu `@Entry`/`@Id`, tên/kiểu attribute không khớp schema, giá trị binary hoặc multi-value | Rà soát annotation, `Name` DN và bộ chuyển kiểu ODM |
| Kết quả thiếu trường | Tự giới hạn `attributes(...)` hoặc tài khoản bind thiếu quyền đọc | Xem tập attribute được yêu cầu và ACL của directory |
| Search chậm, vượt giới hạn | Base rộng, filter thiếu index, không có giới hạn hoặc server giới hạn kết quả | Thu hẹp base/scope, thêm giới hạn hợp lý và xem chỉ số LDAP |
| Lỗi kết nối hay quyền | TLS, chứng chỉ, bind, ACL, server ngắt kết nối | Kiểm tra cấu hình `ContextSource`, kết nối và log máy chủ sau khi ẩn thông tin nhạy cảm |

Lỗi kết nối, quyền truy cập hoặc mapping cần được báo về tầng ứng dụng theo trạng thái tương ứng. Không nên bắt mọi `DataAccessException` rồi trả về danh sách rỗng, vì như vậy sẽ che giấu sự cố LDAP và có thể khiến hệ thống diễn giải sai kết quả.

## 8. Tự luyện tập

1. Với base `dc=example,dc=org` trên `ContextSource`, muốn tìm user dưới `ou=people` (kể cả OU con) cần `base` và `scope` nào? **Đáp án:** `base("ou=people")` và `SearchScope.SUBTREE`.
2. `findOne(query, PersonEntry.class)` xử lý thế nào nếu có 0 hoặc 2 entry? **Đáp án:** 0 ném `EmptyResultDataAccessException`, 2 ném `IncorrectResultSizeDataAccessException`.
3. Vì sao `ldap.find(query, PersonEntry.class)` khác `ldap.search(query, mapper)`? **Đáp án:** `find` dùng metadata ODM của class để lọc theo kiểu entity và chuyển kết quả; `search` giao việc ánh xạ cho callback được cung cấp.
4. Vì sao không viết `query().filter("(uid=" + userInput + ")")`? **Đáp án:** Input có thể chèn hoặc biến đổi cú pháp filter; nên dùng `where("uid").is(userInput)` hay filter tham số hóa.
5. Nếu `countLimit(50)` trả đúng 50 entry, có thể kết luận chỉ có 50 người không? **Đáp án:** Không; đây là giới hạn tìm kiếm, không phải tổng số chính xác hoặc cơ chế phân trang.
6. Vì sao không nên đặt `attributes("cn")` cho một entity gồm `uid`, `cn`, `sn` và `mail`? **Đáp án:** ODM có thể thiếu dữ liệu cần thiết để tạo đối tượng đầy đủ hoặc khớp object class của entity.

## Tài liệu tham khảo

- [Spring LDAP Reference — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html).
- [Spring LDAP Reference — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html).
- [Spring LDAP API — LdapOperations](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html).
- [Spring LDAP API — LdapQueryBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html).
- [Spring LDAP API — SearchScope](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/SearchScope.html).
