# Quy ước method query của repository

## Mục tiêu học tập

**Spring Data LDAP** cung cấp cơ chế repository trên nền **Spring LDAP**: thay vì tự viết mọi lệnh tìm kiếm bằng `LdapTemplate.search(...)`, lập trình viên khai báo phương thức như `findByUid(...)` hoặc `findBySurnameAndEmail(...)`. Spring Data phân tích **tên phương thức** và tạo LDAP Search phù hợp với metadata ánh xạ của đối tượng.

Trong chương **Repository**, bài học này giúp bạn:

1. Phân biệt **derived query method** (truy vấn suy ra từ tên phương thức) với phương thức CRUD có sẵn và với `@Query` khai báo LDAP filter trực tiếp.
2. Hiểu cú pháp `find…By<Property><Keyword>`, cách nối điều kiện `And`/`Or` và các keyword thực sự được hỗ trợ trong Spring Data LDAP.
3. Viết entity ODM có `@Entry`, `@Id`, `@Attribute` và interface `LdapRepository<T>`; nhận ra tên property Java khác tên LDAP attribute.
4. Lựa chọn kiểu trả về phù hợp, xử lý 0/nhiều kết quả, DN, base DN, ACL và dữ liệu nhiều giá trị.
5. Biết khi nào chuyển sang `@Query`, `LdapQuery` hoặc `LdapTemplate`; đặc biệt tránh áp dụng máy móc quy ước phân trang/sắp xếp của Spring Data JPA cho LDAP.
6. Thiết kế kiểm thử để phát hiện sai filter, sai scope, thiếu quyền và rủi ro LDAP injection.

Nội dung áp dụng cho module **SPRING_LDAP** khi làm việc với DN, schema, filter, `ContextSource`, `LdapTemplate` và ODM. `LdapClient` có thể là lựa chọn khác cho truy vấn lập trình trực tiếp, nhưng **method-name query derivation** ở đây là tính năng của **Spring Data LDAP repository**, không phải một quy tắc tự động của mọi API LDAP.

## 1. Repository được tạo từ interface như thế nào?

Với Spring Data LDAP, bạn khai báo một **entity ODM** đại diện cho entry và một **interface repository**. Spring tạo proxy lúc khởi tạo application context; khi gọi phương thức truy vấn đã khai báo, proxy dựng truy vấn LDAP rồi thực hiện bằng hạ tầng Spring LDAP.

~~~mermaid
flowchart LR
    A["Service gọi findBySurname('Tran')"] --> B["Spring Data LDAP repository proxy"]
    B --> C["Phân tích method name"]
    C --> D["ODM metadata + LDAP filter"]
    D --> E["LdapTemplate / ContextSource"]
    E --> F["LDAP server (schema, ACL, search)"]
    F --> G["LDAP entries"]
    G --> H["ODM map sang Java objects"]
~~~

Một phương thức `findBy...` **không chạy SQL**, không dùng bảng và cột như JPA. Nó được chuyển thành điều kiện LDAP Search trên các attribute đã ánh xạ.

### 1.1. Entity ODM mẫu

Giả sử thư mục có base `dc=example,dc=org`, nhánh `ou=people` và entry:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org
telephoneNumber: +84 90 111 2222
~~~

Class Java:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {

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

    @Attribute(name = "telephoneNumber")
    private String[] phoneNumbers;

    public DirectoryPerson() {
        // Constructor để ODM khởi tạo entity.
    }

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getFullName() { return fullName; }
    public String getSurname() { return surname; }
    public String getEmail() { return email; }
    public String[] getPhoneNumbers() { return phoneNumbers; }
}
~~~

Các annotation quan trọng:

| Annotation | Ý nghĩa đối với repository |
| --- | --- |
| `@Entry` | Khai báo object class và base của loại entry mà entity đại diện |
| `@Id` | Trường định danh DN của entry; **kiểu `javax.naming.Name`** |
| `@Attribute(name = "cn")` | Ánh xạ Java property `fullName` đến LDAP attribute `cn` |
| `@Attribute(name = "mail")` | Ánh xạ property `email` đến LDAP attribute `mail` |
| `@Transient` (nếu dùng) | Bỏ qua field chỉ phục vụ tính toán trong Java |
| `@DnAttribute` (nếu dùng) | Liên hệ field với thành phần RDN theo quy tắc ODM |

**Chú ý:** Truy vấn dẫn xuất được viết theo **tên property của entity**, không phải tự động dùng tên attribute LDAP. Trong entity trên, cú pháp là `findByFullName(...)`, không phải `findByCn(...)`, bởi class không có property tên `cn`.

### 1.2. Interface repository đúng kiểu LDAP

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findBySurname(String surname);

    List<DirectoryPerson> findBySurnameAndEmail(
        String surname, String email
    );

    List<DirectoryPerson> findByFullNameStartingWith(String prefix);

    List<DirectoryPerson> findByFullNameContaining(String fragment);

    List<DirectoryPerson> findByEmailIsNotNull();

    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

Các phương thức không cần phần thân; Spring Data LDAP suy ra truy vấn từ tên, tham số và entity metadata. Hãy bảo đảm package repository được quét bằng `@EnableLdapRepositories` hoặc cấu hình Spring Data LDAP tương đương.

**Khác với một số ví dụ repository tổng quát:** `LdapRepository<T>` chỉ nhận **một kiểu generic**, vì ID LDAP được xác định là `Name`. Không khai báo `LdapRepository<DirectoryPerson, Long>` hoặc giả định ID là số tự tăng.

### 1.3. Cấu hình repository

Ví dụ Java configuration ở mức tối giản:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(
    basePackages = "com.example.directory.repository"
)
public class DirectoryRepositoryConfig {
}
~~~

Cần có `ContextSource` và `LdapTemplate` được cấu hình trong ứng dụng. Thông thường hạ tầng Spring Data LDAP sẽ tìm bean `ldapTemplate` để thực thi repository. Kết nối phải có base DN đúng, bind account với quyền phù hợp và LDAPS/StartTLS đã kiểm tra chứng chỉ.

Ví dụ thuộc tính kết nối chỉ để mô tả, **không** hardcode credentials:

~~~text
LDAP URL:      ldaps://ldap.example.org:636
Context base:  dc=example,dc=org
Entity base:   ou=people
Search data:   uid=lan,ou=people,dc=example,dc=org
~~~

Spring Data LDAP không cấp quyền truy vấn thay cho LDAP server và không bỏ qua schema. Quyền search/read vẫn do account bind và ACL quyết định.

## 2. Quy ước tên phương thức: subject và predicate

Cú pháp thường gặp:

~~~text
<subject>By<predicate>

findBySurname
findBySurnameAndEmail
findByFullNameStartingWith
findByEmailIsNotNull
~~~

Trong đó:

- **Subject (phần trước `By`):** diễn tả thao tác, như `find…By`, `read…By` hoặc `get…By` trong hệ quy ước Spring Data. Một số dạng như `exists…By` và `count…By` cũng thuộc quy ước chung; **khả năng hỗ trợ cụ thể phụ thuộc module và phiên bản**.
- **Predicate (phần sau `By`):** gồm các **tên property của entity**, các từ khóa so sánh và toán tử nối như `And` / `Or`.
- **Tham số:** được dùng làm giá trị so khớp khi tạo LDAP filter. Giá trị do user cung cấp phải được truyền dưới dạng tham số, không nối thủ công vào chuỗi LDAP filter.

### 2.1. Không có keyword: so khớp bằng nhau

~~~java
List<DirectoryPerson> findBySurname(String surname);
~~~

Với lời gọi:

~~~java
List<DirectoryPerson> results =
    repository.findBySurname("Tran");
~~~

Ý nghĩa filter khái niệm:

~~~ldap
(&(objectClass=inetOrgPerson)(sn=Tran))
~~~

Dòng filter là **minh họa ngữ nghĩa**, không phải cam kết byte-for-byte filter thực tế: Spring Data có thể thêm điều kiện objectClass theo entity metadata, diễn giải base và combine các objectClass khác nhau tùy phiên bản. Phần quan trọng là **`surname` được ánh xạ sang `sn`** rồi so khớp bằng nhau.

LDAP server quyết định case-sensitivity và normalization theo **EQUALITY matching rule** của attribute `sn`. Tên phương thức `findBySurname` **không bảo đảm** so khớp phân biệt chữ hoa/thường theo trực giác Java `String.equals`.

### 2.2. Kết hợp nhiều điều kiện: And và Or

~~~java
List<DirectoryPerson> findBySurnameAndEmail(
    String surname, String email
);

List<DirectoryPerson> findBySurnameOrFullName(
    String surname, String fullName
);
~~~

Với hai tham số, `And` có ý nghĩa tương đương:

~~~ldap
(&(sn=Tran)(mail=lan@example.org))
~~~

Còn `Or` có ý nghĩa tương đương:

~~~ldap
(|(sn=Tran)(cn=Lan Tran))
~~~

Các ví dụ bỏ phần objectClass để tập trung vào điều kiện. Khi kết hợp nhiều nhánh `And` và `Or` trong một tên phương thức rất dài, khả năng đọc và kiểm thử giảm nhanh; nên chuyển sang `@Query` hoặc `LdapQueryBuilder` để có filter tường minh.

**Không hiểu `And` và `Or` như phép nối chuỗi tùy ý**. Parser của Spring Data phân tích token theo tên property, thứ tự tham số và quy tắc operator. Nếu tên property không khớp entity, repository có thể báo lỗi tạo query ngay khi khởi động.

## 3. Các keyword truy vấn Spring Data LDAP thường dùng

Tài liệu riêng của **Spring Data LDAP** liệt kê các keyword tiêu biểu sau. Bảng sử dụng property của entity mẫu để tránh nhầm với tên LDAP attribute.

| Keyword | Phương thức ví dụ | Ý nghĩa LDAP |
| --- | --- | --- |
| Không có keyword | `findBySurname("Tran")` | `(sn=Tran)` |
| `Not` | `findBySurnameNot("Tran")` | `(!(sn=Tran))` |
| `IsNotNull` / `NotNull` | `findByEmailIsNotNull()` | `(mail=*)` |
| `IsNull` / `Null` | `findByEmailIsNull()` | `(!(mail=*))` |
| `StartingWith` | `findByFullNameStartingWith("Lan")` | `(cn=Lan*)` |
| `EndingWith` | `findByFullNameEndingWith("Tran")` | `(cn=*Tran)` |
| `Containing` | `findByFullNameContaining("an")` | `(cn=*an*)` |
| `Like` | `findByFullNameLike(value)` | Tìm với mẫu LDAP theo ngữ nghĩa được module hỗ trợ |
| `NotLike` / `IsNotLike` | `findByFullNameNotLike(value)` | Phủ định điều kiện dạng `Like` |
| `LessThanEqual` | `findByAgeLessThanEqual(age)` * | LDAP `<=` nếu attribute hỗ trợ ORDERING |
| `GreaterThanEqual` | `findByAgeGreaterThanEqual(age)` * | LDAP `>=` nếu attribute hỗ trợ ORDERING |

*Dòng có `Age` minh họa keyword theo tài liệu module; entity `DirectoryPerson` ở trên **chưa khai báo property `age`**, vì vậy không thể chép phương thức đó vào interface mẫu nếu chưa bổ sung attribute và schema tương ứng. LDAP cũng không mặc định có attribute `age`: cần xác minh syntax, ORDERING matching rule và phạm vi hỗ trợ trên server.

Các keyword `LessThanEqual` và `GreaterThanEqual` phải được hiểu theo ngữ nghĩa ordering của LDAP; không giống thao tác so sánh số nguyên Java khi thuộc tính là chuỗi.

**Đặc biệt:** Danh sách keyword trong **Spring Data Commons** là danh sách *tổng quát* dùng chung nhiều datastore. Đừng thấy `Between`, `Regex`, `In`, `IsEmpty`, `GreaterThan` hoặc các toán tử phức tạp trong tài liệu chung rồi mặc định Spring Data LDAP hỗ trợ chúng. Phải tra **bảng keyword cụ thể cho LDAP** và thử trên phiên bản đang dùng.

### 3.1. IsNull là “không có attribute”, không phải SQL NULL

LDAP không có khái niệm cột `NULL` giống bảng quan hệ. Ví dụ:

~~~java
List<DirectoryPerson> findByEmailIsNull();
~~~

Tương đương ý nghĩa filter:

~~~ldap
(!(mail=*))
~~~

Nghĩa là “không tồn tại giá trị thuộc tính `mail` phù hợp điều kiện presence”, **không phải** tìm một trường `mail` có literal `null`. Khi entry không thể đọc vì ACL, điều kiện tìm kiếm còn phụ thuộc mô hình đánh giá quyền và quyền search của server.

### 3.2. StartingWith, EndingWith và Containing

Với:

~~~java
repository.findByFullNameStartingWith("Lan");
repository.findByFullNameEndingWith("Tran");
repository.findByFullNameContaining("an");
~~~

Ý nghĩa lần lượt là mẫu prefix, suffix và substring đối với LDAP attribute `cn`. Khả năng tìm kiếm có nhanh hay không còn phụ thuộc index, matching rules và chính sách server. Tìm substring trên vùng dữ liệu lớn có thể tốn tài nguyên hơn so khớp chính xác.

Đừng tự ghép ký tự `*` vào đầu vào tùy ý để “lái” truy vấn nếu đã dùng `StartingWith`/`Containing`. Hãy coi đầu vào là **dữ liệu**, để Spring Data hoặc API filter của Spring LDAP xử lý escaping đúng ngữ cảnh.

### 3.3. Like và ký tự wildcard

`Like` là từ khóa có trong danh sách Spring Data LDAP, nhưng ngữ nghĩa mẫu có thể khác mong đợi từ SQL `LIKE '%x%'`. LDAP filter dùng `*` cho substring, còn escaping theo quy tắc LDAP. Cần kiểm thử rõ giá trị đầu vào, ký tự `*`, dấu ngoặc và backslash trên phiên bản module thực tế, tránh coi chuỗi `%x%` của SQL như pattern LDAP.

Nếu nghiệp vụ chỉ cần bắt đầu/kết thúc/chứa chuỗi, `StartingWith`, `EndingWith` và `Containing` thường **diễn đạt ý định rõ hơn** `Like`.

## 4. Phân biệt property Java với LDAP attribute

Khi viết repository interface, phần tên sau `By` trỏ đến **property của Java entity ODM**:

~~~java
@Attribute(name = "cn")
private String fullName;

@Attribute(name = "mail")
private String email;
~~~

Vì vậy:

~~~java
// Đúng với entity DirectoryPerson hiện tại:
List<DirectoryPerson> findByFullName(String fullName);
List<DirectoryPerson> findByEmail(String email);

// Sai nếu entity không có property tên "cn" hoặc "mail":
// List<DirectoryPerson> findByCn(String cn);
// List<DirectoryPerson> findByMail(String mail);
~~~

Spring Data phân tích tên `FullName` thành Java property `fullName`, rồi ODM mapping sang LDAP attribute `cn`. Một lỗi phổ biến là viết theo **tên attribute LDAP** trong interface nhưng class ODM lại đổi tên field để phù hợp domain model.

Các property sâu như `address.city` được nhiều module Spring Data hỗ trợ ở mức parser chung; nhưng LDAP không có cấu trúc object quan hệ giống JPA. **Không giả định** query dạng nested path hoạt động chỉ vì ví dụ JPA có `findByAddress_City(...)`. Cần xác minh mapper và loại LDAP attribute thực sự được hỗ trợ.

### 4.1. Tên method đặc biệt: findById không đồng nghĩa findByUid

`LdapRepository<DirectoryPerson>` kế thừa phương thức CRUD như:

~~~java
Optional<DirectoryPerson> findById(Name id);
boolean existsById(Name id);
void deleteById(Name id);
~~~

`id` ở đây là **DN của entry**, do field `@Id Name dn` đại diện.

~~~java
Name dn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", "lan")
    .build();

Optional<DirectoryPerson> byDn = repository.findById(dn);

// Khác hoàn toàn với search theo thuộc tính uid:
Optional<DirectoryPerson> byUid = repository.findByUid("lan");
~~~

Hai phương thức có hợp đồng khác nhau:

- `findById(Name)`: tìm theo **DN cụ thể**.
- `findByUid(String)`: tìm theo **attribute `uid`** trong base/scope của repository.

Thậm chí nếu DN đang dùng `uid=lan`, entry có thể được **move** sang OU khác; lúc đó findById với DN cũ không còn tìm đúng, trong khi một search theo `uid` ở vùng rộng hơn có thể vẫn tìm thấy.

**Không dùng `Long` hoặc `String` làm ID generic theo thói quen JPA**; tài liệu Spring Data LDAP yêu cầu `javax.naming.Name`.

## 5. Kiểu trả về và số lượng entry

Cùng một LDAP filter có thể khớp **0, 1 hoặc nhiều entry**. Kiểu trả về của method phải tương thích với kỳ vọng nghiệp vụ.

| Kiểu trả về | Khi sử dụng | Lưu ý |
| --- | --- | --- |
| `List<DirectoryPerson>` | Chấp nhận nhiều entry | Danh sách rỗng khi base hợp lệ nhưng không có kết quả |
| `Optional<DirectoryPerson>` | Kỳ vọng tối đa một entry | Nếu nhiều entry, thường phát sinh lỗi kích thước kết quả tùy module/API |
| `DirectoryPerson` | Kỳ vọng đúng hoặc tối đa một object theo hợp đồng | Cần xử lý trường hợp vắng mặt theo phiên bản/hợp đồng |
| `boolean` từ `existsById(Name)` | Kiểm tra một DN cụ thể | Không phải kiểm tra uniqueness toàn bộ `uid` |
| `Iterable<DirectoryPerson>` từ CRUD | Đọc nhiều entry | Cần chú ý tải và giới hạn server |

Ví dụ service không nên lấy phần tử đầu rồi kết luận duy nhất:

~~~java
// Có thể sai khi uid bị trùng giữa nhiều OU:
List<DirectoryPerson> all = repository.findBySurname("Tran");
if (!all.isEmpty()) {
    DirectoryPerson arbitrary = all.get(0);
}
~~~

Nếu nghiệp vụ khẳng định `uid` duy nhất, phải **định nghĩa phạm vi duy nhất**, xác minh policy/schema của LDAP server và kiểm thử trường hợp trùng trong các nhánh khác nhau. LDAP không mặc nhiên áp dụng unique constraint toàn cục cho mọi attribute.

### 5.1. Không nhầm search rỗng với base DN không tồn tại

- Search trên base hợp lệ, filter không khớp: kết quả rỗng là tình huống bình thường.
- Base DN/OU không tồn tại: server có thể trả `noSuchObject`, dẫn tới lỗi tìm tên; không nên coi đó là “không có nhân viên”.
- Tài khoản bind thiếu quyền đọc: kết quả và thông báo có thể bị hạn chế tùy ACL; không suy diễn từ danh sách rỗng rằng entry bị xóa.
- Lỗi kết nối, TLS, timeout hoặc schema: cần báo đúng nhóm lỗi, không gom tất cả thành `Optional.empty()`.

## 6. Khi method name không đủ: dùng @Query

Không nên kéo dài tên phương thức thành vài chục token để mô tả điều kiện phức tạp. **Spring Data LDAP** hỗ trợ `org.springframework.data.ldap.repository.Query` để khai báo LDAP filter trên method.

Ví dụ tìm hồ sơ theo email và họ trong nhánh người dùng:

~~~java
import java.util.List;

import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findBySurname(String surname);

    @Query(
        value = "(&(objectClass=inetOrgPerson)(mail=:email)(sn=:surname))",
        base = "ou=people"
    )
    List<DirectoryPerson> findByContact(
        @Param("email") String email,
        @Param("surname") String surname
    );
}
~~~

Ở ví dụ trên:

- `@Query.value` là **LDAP filter**, không phải SQL/JPQL.
- `:email` và `:surname` là named parameters.
- `base="ou=people"` được áp dụng theo ngữ cảnh tìm kiếm của Spring LDAP; nếu `ContextSource` có base `dc=example,dc=org`, không tự nhân đôi phần này.
- `@Query` cũng có thể cấu hình `searchScope`, `timeLimit` và `countLimit` tùy phiên bản API.

Ví dụ filter trên chỉ cần những thuộc tính có trong schema minh họa. Không thêm điều kiện theo thuộc tính không tồn tại hoặc bị ACL chặn rồi xem đó là lỗi method query.

### 6.1. Named và positional parameters

Spring Data LDAP cho phép hai kiểu binding trong `@Query`:

~~~java
// Named parameter: dễ đọc, thuận tiện refactor.
@Query("(mail=:email)")
List<DirectoryPerson> byMailNamed(@Param("email") String email);

// Positional parameter: chỉ số bắt đầu từ 0.
@Query("(mail=?0)")
List<DirectoryPerson> byMailPositional(String email);
~~~

Ưu tiên named parameter khi điều kiện dài. Với positional parameters, thay thứ tự tham số của method có thể làm filter tiếp tục chạy nhưng so khớp sai trường.

### 6.2. Parameter encoding và LDAP injection

LDAP filter có ký tự cú pháp đặc biệt như `*`, `(`, `)`, `\\` và NUL. Nếu tự nối chuỗi:

~~~java
// Không an toàn với đầu vào không tin cậy:
String filter = "(mail=" + emailFromRequest + ")";
~~~

người dùng có thể thay đổi ý nghĩa biểu thức tìm kiếm. Đối với derived query và binding thông thường của `@Query`, để framework thực hiện escaping theo cơ chế được tài liệu mô tả.

Spring Data LDAP hỗ trợ `@LdapEncode` để điều chỉnh encoding cho **tham số của custom `@Query`** trong các trường hợp đặc biệt; không áp dụng annotation đó cho derived query. Việc tùy biến encoder hoặc cho phép wildcard phải được kiểm soát theo nghiệp vụ, tránh vô tình giảm mức bảo vệ đầu vào.

**Cảnh báo riêng về SpEL trong `@Query`:** Các giá trị từ expression/placeholder không tự được escaping theo cùng cách với binding chuỗi bình thường. Nếu cần sử dụng SpEL hoặc environment property để dựng filter, phải xử lý encoding an toàn và không đánh giá expression không đáng tin cậy. Nhiều trường hợp có thể tránh SpEL bằng named parameters hoặc `LdapQueryBuilder`.

## 7. Điều gì không nên giả định từ Spring Data JPA?

Spring Data Commons dùng chung cách **đặt tên phương thức**, nhưng từng datastore chỉ hỗ trợ một tập tính năng nhất định. Với Spring Data LDAP, tài liệu cấu hình hiện hành nêu rõ **paging và sorting không được hỗ trợ ở tầng LDAP repository**.

| Mong đợi từ JPA | Thực tế cần nhớ với Spring Data LDAP |
| --- | --- |
| `JpaRepository<Entity, Long>` | LDAP dùng `LdapRepository<Entity>` và DN kiểu `Name` làm ID |
| `findById(42L)` | `findById(Name)` tìm theo DN |
| `Page<T> findByX(..., Pageable)` | Không mặc định có repository pagination theo `Pageable` |
| `findByXOrderByYAsc(...)` | Không giả định repository tạo LDAP server-side sort tương đương |
| `findTop10By...` | Từ khóa giới hạn thuộc parser chung; phải kiểm tra hỗ trợ chính xác của module/phiên bản |
| `Between`, `Regex` hoặc nested path | Không mặc định hoạt động trên LDAP chỉ vì được liệt kê ở Spring Data Commons |
| Database transaction cho nhiều bảng | LDAP có ngữ nghĩa thao tác riêng, không cung cấp transaction JPA tương đương |
| SQL `LIKE '%text%'` | LDAP dùng filter và substring matching theo syntax/matching rule |

Nếu cần **phân trang LDAP thật sự**, hãy dùng `LdapTemplate` với **Simple Paged Results Control (RFC 2696)**, `PagedResultsDirContextProcessor` hoặc API control tương thích. Nếu cần **sắp xếp trên server**, dùng **Server-Side Sorting Control (RFC 2891)** khi LDAP server hỗ trợ. Hai thao tác này cần xử lý cookie, sort response, giới hạn máy chủ và tính nhất quán của kết quả.

Không “giả lập phân trang” bằng cách tải toàn bộ dữ liệu qua `repository.findAll()` rồi chia danh sách trên client ở một directory lớn: việc đó không giảm được tải hay giới hạn từ LDAP server.

## 8. Kiến trúc service: khi nào repository, khi nào LdapTemplate?

Một ứng dụng thực tế có thể kết hợp hai lớp mà không mâu thuẫn.

~~~text
Controller
    |
    v
PersonService
    |-------------------------------|
    v                               v
Spring Data LDAP Repository     LdapTemplate
(method-name / @Query)          (LdapQuery, search,
    |                             controls, batch)
    |-------------------------------|
                    v
           ContextSource / LDAP
~~~

**Ưu tiên repository** khi cần CRUD/tra cứu theo các thuộc tính đã ánh xạ, điều kiện ngắn và không cần controls chuyên biệt.

**Ưu tiên `@Query`** khi vẫn muốn kết quả ODM nhưng LDAP filter phức tạp hoặc cần base/scope cụ thể, không muốn tên method quá dài.

**Ưu tiên `LdapTemplate` hoặc `LdapClient`** khi cần điều khiển search scope, giới hạn, paged results, sorting controls, thao tác nhiều attribute hay xử lý đặc biệt ngoài khả năng repository.

Ví dụ service sử dụng repository, giữ tầng HTTP không phụ thuộc trực tiếp filter LDAP:

~~~java
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class PeopleDirectoryService {

    private final DirectoryPersonRepository repository;

    public PeopleDirectoryService(DirectoryPersonRepository repository) {
        this.repository = repository;
    }

    public List<DirectoryPerson> searchBySurname(String surname) {
        if (surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("surname không được rỗng");
        }
        return repository.findBySurname(surname);
    }
}
~~~

Đây là ví dụ về tổ chức tầng, không khuyến khích trả nguyên ODM entity cho mọi public API. Nên map sang DTO chỉ chứa thông tin được phép công bố, không bao gồm DN/attribute nhạy cảm không cần thiết.

## 9. Lỗi thường gặp khi đặt tên method query

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Startup báo không tìm thấy property `Cn` | Method là `findByCn` nhưng entity chỉ có `fullName` | Đặt `findByFullName` hoặc sửa mapping |
| Repository bean không được tạo | Chưa `@EnableLdapRepositories` hoặc package nằm ngoài vùng scan | Kiểm tra cấu hình scan và dependency |
| Generic repository khai báo sai | Dùng `LdapRepository<Entity, Long>` theo thói quen JPA | Chuyển thành `LdapRepository<Entity>`, ID là `Name` |
| Kết quả rỗng dù có entry | Base/scope/filter/objectClass hoặc ACL không phù hợp | Kiểm tra `@Entry`, `ContextSource.base`, quyền search và filter |
| `findById("lan")` không phù hợp | ID LDAP là DN, không phải giá trị `uid` | Dùng `findById(Name)` hoặc `findByUid(String)` |
| Tìm một object nhưng có nhiều kết quả | Thuộc tính không unique trong vùng search | Sửa phạm vi và ràng buộc nghiệp vụ; dùng List nếu có thể nhiều |
| `IsNull` hiểu sai | Tưởng tìm literal SQL NULL | Kiểm tra presence filter `(!(attr=*))` |
| `Like` cho kết quả bất ngờ | Nhầm cú pháp SQL wildcard với LDAP substring | Dùng `StartingWith` / `Containing`; kiểm thử mẫu |
| Kết quả sort/page không như JPA | Repository LDAP không có pagination/sorting tương đương | Dùng LDAP controls qua `LdapTemplate` |
| Lỗi so sánh `<=`/`>=` | Attribute không có ORDERING phù hợp | Kiểm tra schema và matching rule |
| `@Query` có filter lỗi hoặc injection | Ghép input tùy ý; dùng SpEL không escaping | Dùng named parameter/builder và encoder phù hợp |
| Timeout khi dùng `Containing` | Search quá rộng, thiếu index hoặc bị server limit | Giới hạn base/scope, thêm index, phân tích filter |

**Quy tắc chẩn đoán:** Đầu tiên kiểm tra **Java property name và mapping**, tiếp đó kiểm tra **filter/schema/base DN**, sau cùng phân biệt **ACL, giới hạn server và lỗi kết nối**. Không chữa lỗi startup do tên method sai bằng cách nới ACL LDAP.

## 10. Kiểm thử derived query trên LDAP thật

Một bài kiểm thử unit chỉ mock `DirectoryPersonRepository` không chứng minh Spring Data phân tích tên phương thức đúng hoặc server đánh giá filter như mong đợi. Cần kiểm thử tích hợp với LDAP server tương thích môi trường mục tiêu.

Chuẩn bị một OU có dữ liệu thử:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Minh Le
sn: Le
mail: minh@example.org

dn: uid=binh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Binh Tran
sn: Tran
~~~

Các ca kiểm thử:

| Ca | Lời gọi | Kỳ vọng |
| --- | --- | --- |
| Equality | `findBySurname("Tran")` | Nhận Lan và Binh nếu schema/ACL cho phép |
| And | `findBySurnameAndEmail("Tran", "lan@example.org")` | Chỉ Lan |
| Or | `findBySurnameOrFullName("Le", "Lan Tran")` | Minh và Lan |
| StartingWith | `findByFullNameStartingWith("Lan")` | Tìm Lan theo prefix |
| Containing | `findByFullNameContaining("Tran")` | Tìm các entry có `cn` chứa `Tran` |
| IsNull | `findByEmailIsNull()` | Tìm Binh do không có `mail` |
| IsNotNull | `findByEmailIsNotNull()` | Tìm Lan và Minh |
| Không kết quả | `findByUid("unknown")` | `Optional.empty()` nếu không trùng |
| DN lookup | `findById(Name của uid=lan)` | Trả object Lan ở đúng DN |
| Tên Java khác LDAP | `findByFullName("Lan Tran")` | Tìm theo `cn` chứ không tìm attribute `fullName` |
| Đầu vào ký tự đặc biệt | Tham số chứa `*` hoặc dấu ngoặc | Không làm thay đổi cấu trúc filter |
| Sai cấu hình | Search base không tồn tại | Báo lỗi phù hợp, không âm thầm coi kết quả rỗng |
| Thiếu quyền | Account không được search/read entry | Giữ nguyên giới hạn ACL, không che giấu thành công |

Trong các test quan trọng, hãy xác minh **DN hoặc UID của toàn bộ entry trả về**, không chỉ đếm số lượng. Với attribute có matching rule không phân biệt chữ hoa/thường, so sánh kỳ vọng theo **ngữ nghĩa LDAP**, không áp dụng mặc định so sánh chuỗi Java.

### 10.1. Ví dụ kiểm thử tích hợp giản lược

Giả sử môi trường test đã tạo các entry ở trên và repository được inject:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DirectoryPersonRepositoryIT {

    @Autowired
    DirectoryPersonRepository repository;

    @Test
    void shouldDeriveQueryFromJavaPropertyName() {
        List<DirectoryPerson> results =
            repository.findByFullName("Lan Tran");

        assertThat(results)
            .extracting(DirectoryPerson::getUid)
            .contains("lan");
    }

    @Test
    void shouldMatchMissingAttribute() {
        List<DirectoryPerson> results =
            repository.findByEmailIsNull();

        assertThat(results)
            .extracting(DirectoryPerson::getUid)
            .contains("binh");
    }
}
~~~

Đây là minh họa để nhấn mạnh **kết quả của query derivation**. Một bài kiểm thử thực tế còn phải khởi tạo/thu hồi LDAP test data, cô lập môi trường, sử dụng tài khoản đọc đúng quyền và bảo đảm không kết nối nhầm production.

## 11. Bài tập tự thực hành

Cho entity có các property `uid`, `fullName`, `surname`, `email`, trong đó mapping LDAP là `uid`, `cn`, `sn`, `mail`:

1. Khai báo `findByFullNameEndingWith(String suffix)`; viết filter LDAP tương đương về mặt ngữ nghĩa.
2. Khai báo một method tìm người có `surname="Tran"` **và** `email` hiện diện. Giải thích vì sao `IsNotNull` không phải so sánh với literal `null`.
3. Viết hai phương thức khác nhau để đọc theo **DN** và theo **uid**. Chỉ ra kiểu tham số phù hợp.
4. Dùng `@Query` với named parameters cho điều kiện kết hợp `mail` và `sn` dưới `ou=people`.
5. Giả sử `uid` xuất hiện ở hai OU. Nếu method trả `Optional<DirectoryPerson>`, điều gì có thể xảy ra? Thiết kế lại hợp đồng.
6. Một người dùng nhập `a*)(uid=*)` làm giá trị tìm kiếm. Vì sao không được nối trực tiếp giá trị này vào LDAP filter?
7. Viết một test chứng minh `findByFullName("Lan Tran")` truy vấn theo LDAP `cn`, không phải `fullName`.
8. Nếu muốn API trả 20 entry mỗi lần và sort server-side, bạn sẽ dùng repository method name hay LDAP controls? Giải thích giới hạn.

**Tự đánh giá:** Người học hoàn thành bài khi có thể nhìn vào chữ ký `findByFullNameStartingWith("Lan")`, xác định **property Java**, **LDAP attribute**, **filter logic**, **phạm vi tìm kiếm**, **kiểu trả về** và **những điều kiện server có thể khiến kết quả khác kỳ vọng**.

## 12. Ghi nhớ

Với **Spring Data LDAP**, quy ước **method query** cho phép khai báo nhiều truy vấn chỉ bằng tên interface method: `findBySurname`, `findBySurnameAndEmail`, `findByFullNameContaining`, `findByEmailIsNull`... Parser đọc **property Java của entity ODM**, sau đó Spring LDAP tạo LDAP Search phù hợp với schema và mapping.

**Không đồng nhất LDAP repository với JPA repository.** DN kiểu `Name` là ID, keyword có phạm vi hỗ trợ riêng, filter hoạt động theo matching rule và ACL của LDAP; đặc biệt **paging/sorting không mặc nhiên được hỗ trợ ở tầng repository**. Khi method name quá phức tạp, dùng `@Query` với parameter binding an toàn; khi cần paged results, sorting controls hoặc search tùy biến sâu, chuyển sang `LdapTemplate`/`LdapClient`.

## Tài liệu tham khảo

- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html): cách suy truy vấn từ tên method, bảng keyword hỗ trợ và `@Query`.
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): `LdapRepository<T>`, DN kiểu `Name`, kích hoạt repository và giới hạn paging/sorting.
- [Spring Data LDAP — Defining Query Methods](https://docs.spring.io/spring-data/ldap/reference/repositories/query-methods-details.html): subject/predicate, keyword và tên method đặc biệt.
- [Spring Data LDAP — Repository Query Keywords](https://docs.spring.io/spring-data/ldap/reference/repositories/query-keywords-reference.html): danh sách keyword tổng quát và lưu ý kiểm tra datastore-specific.
- [Spring Data LDAP — @Query API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/Query.html): filter, base, searchScope, timeLimit, countLimit.
- [Spring LDAP — ODM](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute` và ánh xạ LDAP entry.
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cấu trúc filter và escaping các ký tự đặc biệt.
