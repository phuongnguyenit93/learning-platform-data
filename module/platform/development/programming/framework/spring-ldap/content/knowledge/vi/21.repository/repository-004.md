# Find theo attribute và giới hạn truy vấn dẫn xuất trong Spring LDAP Repository

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt tìm entry theo **DN** với tìm entry theo **attribute** trong cây LDAP.
2. Khai báo entity ODM và các phương thức `findBy...` trên `LdapRepository`, hiểu chúng được dịch thành LDAP search filter như thế nào.
3. Lựa chọn các toán tử truy vấn dẫn xuất phù hợp, tránh nhầm lẫn với cú pháp SQL/JPA.
4. Nhận diện giới hạn của việc suy diễn truy vấn từ tên phương thức, nhất là filter động, phạm vi tìm kiếm, phân trang và sắp xếp.
5. Chuyển sang `@Query` hoặc `LdapQueryBuilder` khi cần kiểm soát filter, base DN, scope, số lượng kết quả và thời gian truy vấn.

> **Ngữ cảnh:** Spring LDAP cung cấp `ContextSource`, `LdapTemplate` và `LdapClient` để kết nối, xác thực và thao tác thư mục. **Spring Data LDAP** bổ sung lớp Repository để tổ chức truy vấn qua interface. Bài này tập trung vào tìm kiếm entry bằng Repository; việc bảo vệ kết nối bằng LDAPS/StartTLS, phân quyền và kiểm thử thư mục vẫn áp dụng như với các API Spring LDAP khác.

## 1. Từ DN đến tìm kiếm theo attribute

LDAP lưu dữ liệu dưới dạng các **entry** trong cây phân cấp. Mỗi entry có một **distinguished name (DN)** duy nhất trong cây và một tập attribute theo schema.

Ví dụ một entry LDIF (giả sử ứng dụng cấu hình `ContextSource` với base DN `dc=example,dc=org`):

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
givenName: Lan
mail: lan@example.org
```

- **Tìm theo DN:** biết chính xác `uid=lan,ou=people,dc=example,dc=org`, dùng `repository.findById(Name)` (ID là DN, không phải chuỗi `uid`).
- **Tìm theo attribute:** biết `uid=lan` hoặc `sn=Nguyen`, cần thực hiện **search** với filter như `(uid=lan)` hoặc `(&(sn=Nguyen)(givenName=Lan))`.
- **Search base:** DN gốc giới hạn phần cây được quét, ví dụ `ou=people`; trong ví dụ này đó là đường dẫn **tương đối** so với base DN của `ContextSource`.
- **Search scope:** `OBJECT` tìm tại chính base entry, `ONELEVEL` tìm con trực tiếp, `SUBTREE` tìm cả các mức sâu hơn.

Không đồng nhất `uid` với DN: `uid` là một attribute, có thể dùng làm thành phần RDN trong ví dụ nhưng không thay thế được đường dẫn DN đầy đủ. Kết quả truy vấn còn phụ thuộc search base, scope, ACL của tài khoản bind và quy tắc so khớp attribute trên LDAP server.

## 2. Chuẩn bị entity ODM và Repository

Spring Data LDAP Repository cần **ODM entity** với `@Entry` và `@Id` của `org.springframework.ldap.odm.annotations`. Kiểu của trường ID là `javax.naming.Name` (ví dụ một `LdapName`), không phải `Long` như nhiều repository JPA. `LdapRepository` chỉ nhận **một** generic type.

```java
package example.directory;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String cn;

    @Attribute(name = "sn")
    private String sn;

    @Attribute(name = "givenName")
    private String givenName;

    @Attribute(name = "mail")
    private String mail;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getCn() { return cn; }
    public String getSn() { return sn; }
    public String getGivenName() { return givenName; }
    public String getMail() { return mail; }
}
```

Trong thực tế, nếu tên field Java khác tên attribute LDAP, khai báo `@Attribute(name = "...")` để ánh xạ; tên dùng ở **phương thức dẫn xuất** dựa trên **thuộc tính Java** của entity, còn filter LDAP phải nhắm đúng attribute đã ánh xạ. `@Entry(objectClasses = ...)` mô tả loại entry, giúp lớp ODM chọn entry phù hợp; `base` giúp xác định nhánh directory dành cho entity.

```java
package example.directory;

import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository extends LdapRepository<DirectoryPerson> {
    List<DirectoryPerson> findByUid(String uid);

    Optional<DirectoryPerson> findByMail(String mail);

    List<DirectoryPerson> findBySnAndGivenName(String sn, String givenName);

    List<DirectoryPerson> findBySnOrGivenName(String sn, String givenName);

    List<DirectoryPerson> findByCnStartingWith(String prefix);

    List<DirectoryPerson> findByMailIsNotNull();
}
```

Để sử dụng interface này, ứng dụng cần có dependency Spring LDAP/Spring Data LDAP phù hợp phiên bản, `ContextSource` và `LdapTemplate` hoạt động, đồng thời bật quét repository bằng `@EnableLdapRepositories` (hoặc cơ chế auto-configuration tương ứng của ứng dụng). Các ví dụ giả định kết nối thử tới directory đã có entry mẫu và tài khoản bind có quyền đọc.

### Ví dụ gọi từ service

```java
package example.directory;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class DirectoryLookupService {
    private final DirectoryPersonRepository people;

    public DirectoryLookupService(DirectoryPersonRepository people) {
        this.people = people;
    }

    public List<DirectoryPerson> findNguyenNamedLan() {
        return people.findBySnAndGivenName("Nguyen", "Lan");
    }

    public List<DirectoryPerson> findNamesStartingWith(String prefix) {
        return people.findByCnStartingWith(prefix);
    }
}
```

Spring Data tạo implementation của interface lúc ứng dụng khởi chạy. Với các phương thức `findBy...`, framework **phân tích tên phương thức**, kết hợp thông tin ODM rồi sinh LDAP filter; lập trình viên không cần viết lớp implementation cho từng truy vấn đơn giản.

## 3. Cách Spring suy diễn `findBy...` thành LDAP filter

Tên phương thức có hai phần: phần đầu `find...By` nêu thao tác tìm kiếm, phần sau `By` chỉ thuộc tính và toán tử. `And` và `Or` nối các điều kiện.

| Phương thức trên `DirectoryPersonRepository` | Ý nghĩa filter LDAP (minh họa phần điều kiện) |
| --- | --- |
| `findByUid("lan")` | `(uid=lan)` |
| `findBySnAndGivenName("Nguyen", "Lan")` | `(&(sn=Nguyen)(givenName=Lan))` |
| `findBySnOrGivenName("Nguyen", "Lan")` | `(\|(sn=Nguyen)(givenName=Lan))` |
| `findByCnStartingWith("Lan")` | `(cn=Lan*)` |
| `findByMailIsNotNull()` | `(mail=*)` |

Đây là **các thành phần filter minh họa**, không nhất thiết là chuỗi cuối cùng được gửi đi: truy vấn trên ODM entity thường còn có điều kiện `objectClass` tương ứng, còn kết quả phải nằm trong search base/scope và đáp ứng schema.

Chẳng hạn, `findBySnAndGivenName("Nguyen", "Lan")` về mặt logic tương đương:

```text
(&
  (objectClass=inetOrgPerson)
  (sn=Nguyen)
  (givenName=Lan)
)
```

Filter trong giao thức LDAP viết liền thành một chuỗi, ví dụ `(&(objectClass=inetOrgPerson)(sn=Nguyen)(givenName=Lan))`. Các bộ lọc có thể bổ sung điều kiện `objectClass` khác từ ODM; ví dụ trên chỉ diễn tả ý tưởng.

### Các từ khóa thiết thực

| Từ khóa trong tên method | Tác dụng LDAP | Chú ý |
| --- | --- | --- |
| Không có hậu tố, `Is` | So khớp bằng `=` | Dựa vào matching rule của attribute trên server |
| `And`, `Or` | Bộ lọc `&`, `\|` | Nhiều điều kiện khiến tên dài và khó bảo trì |
| `StartingWith` | Substring `(attr=value*)` | Có thể tốn kém nếu attribute không được index |
| `EndingWith` | Substring `(attr=*value)` | Khó tận dụng index tùy máy chủ |
| `Containing` | Substring `(attr=*value*)` | Cần hạn chế tìm chuỗi quá ngắn |
| `IsNotNull`, `NotNull` | Presence `(attr=*)` | Kiểm tra attribute **tồn tại**, không phải SQL `NOT NULL` |
| `IsNull`, `Null` | Phủ định presence `(!(attr=*))` | Attribute vắng mặt, không có khái niệm ô SQL NULL |
| `Not` | Phủ định so khớp `(!(attr=value))` | Cẩn trọng khi dữ liệu thiếu attribute |
| `GreaterThanEqual`, `LessThanEqual` | So khớp `>=`, `<=` | Chỉ có ý nghĩa nếu schema/server hỗ trợ ordering matching rule |

Đối với so khớp có ký tự đại diện, ưu tiên `StartingWith`, `EndingWith`, `Containing` khi đúng ý định. Đừng coi `Like` là SQL `LIKE '%...%'`: LDAP dùng filter với dấu `*`, và cách diễn giải tham số phụ thuộc toán tử được Spring Data LDAP hỗ trợ. Các từ khóa có trong danh sách *Spring Data Commons* chưa chắc được LDAP triển khai; kiểm tra tài liệu **store-specific** và thử trên LDAP server mục tiêu.

### Kết quả nhiều entry và một entry

- Chọn `List<DirectoryPerson>` nếu có thể có nhiều kết quả.
- Chọn `Optional<DirectoryPerson>` nếu theo dữ liệu/schema và phạm vi tìm kiếm, điều kiện dự kiến xác định **tối đa một** entry.
- Nếu dùng phương thức mong đợi một kết quả nhưng filter khớp nhiều entry, có thể phát sinh lỗi kích thước kết quả (`IncorrectResultSizeDataAccessException`); đổi sang `List` hoặc siết chặt điều kiện, không giả định LDAP luôn tự chọn entry đầu.
- `findById(Name dn)` là phương thức kế thừa từ repository, dành cho **DN**. Ví dụ `new LdapName("uid=lan,ou=people")` có thể là DN tương đối so với cấu hình directory, nhưng không thể thay thế nó bằng `"lan"`.

## 4. Giới hạn của truy vấn dẫn xuất

Truy vấn dẫn xuất phù hợp với tìm kiếm ít điều kiện, ít thay đổi. Khi yêu cầu phức tạp hơn, tên method vừa khó đọc vừa không mô tả được tất cả đặc tính của LDAP.

**4.1. Không thể mô tả linh hoạt mọi cấu trúc filter.** Một màn hình tìm người có thể nhận `uid`, `mail`, `sn` và cho phép bỏ trống từng điều kiện. Tạo sẵn hàng loạt `findByUidAndSn...` dẫn tới bùng nổ số phương thức. Một filter có nhiều nhóm `(&(...)(|(...)(...)))`, phủ định, presence hay loại trừ entry theo tổ chức cũng dễ vượt quá khả năng diễn đạt sạch sẽ bằng tên.

**4.2. Các tham số tìm kiếm LDAP không phải đều nằm trong tên method.** Search base, scope (`OBJECT`/`ONELEVEL`/`SUBTREE`), `countLimit`, `timeLimit`, thuộc tính cần trả về và chính sách xử lý kết quả cần được điều chỉnh qua API hoặc annotation thích hợp. Không có cơ chế đặt tên `findBy...` phổ quát để diễn tả hết các tùy chọn này.

**4.3. Repository LDAP không cung cấp sorting và paging như JPA.** Dù tài liệu *chung* của Spring Data có ví dụ `Pageable`, `Sort`, `OrderBy`, tài liệu **Spring Data LDAP** nói rõ paging và sorting không được hỗ trợ cho Spring LDAP Repository. Không lấy một ví dụ `Page<...> findBy...` của Spring Data JPA áp vào LDAP mà không kiểm chứng. `countLimit` là **giới hạn số entry** của một lần search, **không phải** phân trang có thứ tự ổn định; nếu cần LDAP paged-results/sort controls, thiết kế cơ chế riêng và kiểm tra máy chủ hỗ trợ.

**4.4. Điều kiện thực thi nằm ở LDAP server.** LDAP không bảo đảm tất cả attribute hỗ trợ toán tử thứ tự hay substring theo cùng cách. Chữ hoa/thường, dấu tiếng Việt và giá trị nhiều phần tử được so khớp theo matching rules của schema, không theo `String.equals` của Java. Server cũng có giới hạn kết quả/thời gian, index và ACL riêng.

**4.5. Filter chuỗi không thay thế các thao tác khác.** Tìm membership trên `member`/`uniqueMember` (DN), diễn giải schema, xử lý referral, truy vấn nhiều nhánh hoặc join kiểu quan hệ không phải các phép join SQL của ORM. Có thể tìm theo attribute chứa DN, nhưng không vì vậy mà có quan hệ JPA tự động.

### Hai nghĩa của từ “giới hạn”

| Loại giới hạn | Câu hỏi | Cách giải quyết |
| --- | --- | --- |
| **Giới hạn khả năng suy diễn** | Tên `findBy...` có biểu diễn được filter và điều kiện động hay không? | `@Query`, `LdapQueryBuilder`, custom repository |
| **Giới hạn thực thi** | Trả tối đa bao nhiêu entry, tìm trong bao lâu và tại nhánh nào? | `@Query(countLimit = ..., timeLimit = ...)` hoặc `LdapQueryBuilder.countLimit(...).timeLimit(...)`, base/scope phù hợp |

## 5. Khi filter cố định nhưng phức tạp: `@Query`

`@Query` của Spring Data LDAP (`org.springframework.data.ldap.repository.Query`) cho phép viết filter LDAP trực tiếp, gắn tham số và đặt các ràng buộc search. Ví dụ: tìm người có `mail`, thuộc `departmentNumber` chỉ định, chỉ trong `ou=people`.

```java
package example.directory;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.ldap.query.SearchScope;

public interface DepartmentPeopleRepository
        extends LdapRepository<DirectoryPerson> {

    @Query(
        value = "(&(objectClass=inetOrgPerson)(departmentNumber=?0)(mail=*))",
        base = "ou=people",
        searchScope = SearchScope.SUBTREE,
        countLimit = 100,
        timeLimit = 3000
    )
    List<DirectoryPerson> findPeopleWithEmailInDepartment(String department);
}
```

Ở ví dụ trên:

- `?0` tham chiếu tham số đầu tiên (đánh số từ 0). Có thể dùng binding theo tên như `:department` nếu cấu hình nhận diện tên tham số phù hợp.
- `countLimit = 100` yêu cầu một search trả không quá 100 entry; **không ngụ ý** đó là 100 entry đầu theo một thứ tự xác định.
- `timeLimit = 3000` giới hạn thời gian search theo cơ chế của JNDI/LDAP, dùng để tránh truy vấn chạy quá lâu; kết quả và ngoại lệ khi chạm ngưỡng phụ thuộc server/driver.
- `base` và `searchScope` thu hẹp vùng directory cần tìm, giảm tải và giảm khả năng lấy nhầm dữ liệu từ nhánh khác.

**An toàn filter:** dùng tham số đã bind thay vì ghép trực tiếp dữ liệu người dùng vào chuỗi `@Query`. Các tham số chuỗi được mã hóa theo quy tắc escape LDAP filter. Riêng biểu thức SpEL và property placeholder trong `@Query` không mặc định escape như tham số thông thường, cần xử lý cẩn thận nếu giá trị có thể do người dùng kiểm soát.

**Lưu ý phiên bản:** tài liệu Spring Data LDAP hiện đại còn có tham số `Limit` động cho một số query method; nếu dùng đồng thời với `@Query(countLimit=...)`, tham số `Limit` có thể ghi đè giới hạn trong annotation. Khi cần khả năng chạy trên nhiều phiên bản, kiểm tra API thực tế của dependency, thay vì mặc định tất cả tính năng của Spring Data Commons đều có mặt.

## 6. Khi điều kiện thay đổi lúc chạy: `LdapQueryBuilder`

Nếu người dùng chọn bộ lọc tùy ý, hãy tạo `LdapQuery` trong code, sau đó truyền vào phương thức **`LdapRepository.findAll(LdapQuery)`** hoặc `LdapTemplate.find(LdapQuery, Entity.class)`.

```java
package example.directory;

import java.util.List;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
public class SafeDirectorySearch {
    private final DirectoryPersonRepository people;

    public SafeDirectorySearch(DirectoryPersonRepository people) {
        this.people = people;
    }

    public List<DirectoryPerson> findBySurname(String surname) {
        LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .countLimit(50)
            .timeLimit(2000)
            .where("objectClass").is("inetOrgPerson")
            .and("sn").is(surname);

        return people.findAll(query);
    }
}
```

Điểm khác biệt cốt lõi: `LdapQueryBuilder` dành riêng cho LDAP, cho phép đặt `base`, `searchScope`, `countLimit`, `timeLimit` **trước khi** gọi `where(...)` để xây filter. Bạn có thể dùng `.is(...)`, `.like(...)`, `.isPresent()`, `.not()` và kết hợp các nhóm điều kiện. Builder xử lý escape giá trị cho các điều kiện so khớp thông thường, giảm nguy cơ LDAP filter injection so với nối chuỗi thủ công.

Ví dụ dựng logic `(&(objectClass=inetOrgPerson)(|(sn=Nguyen)(sn=Tran)))`:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery q = query()
    .base("ou=people")
    .countLimit(100)
    .where("objectClass").is("inetOrgPerson")
    .and(query().where("sn").is("Nguyen").or("sn").is("Tran"));
```

Không trộn `.filter("...")` và `.where(...)` trên cùng builder. `.filter(String)` dạng chuỗi thô **không tự escape** input; nếu phải dùng filter định dạng, ưu tiên `.filter("(&(uid={0})(mail=*))", uid)` hoặc API `Filter` với tham số được mã hóa, và kiểm thử ký tự đặc biệt như `*`, `(`, `)`, `\\` và NUL. Với cấu hình search base động, cần **giới hạn các nhánh được phép tìm** thay vì nhận DN tùy ý từ client.

### So sánh để chọn API

| Trường hợp | Giải pháp ưu tiên | Lý do |
| --- | --- | --- |
| Tìm theo `uid`, `mail`, `sn` cố định | `findByUid`, `findByMail`, `findBySn` | Ngắn, rõ nghĩa, dễ dùng lại |
| Kết hợp 2–3 điều kiện `And`/`Or` đơn giản | Derived query | Không phải viết filter |
| Filter LDAP cố định với nhóm/phủ định và ràng buộc search | `@Query` | Kiểm soát rõ LDAP filter, base và ngưỡng |
| Filter tùy chọn hoặc thay đổi theo request | `LdapQueryBuilder` + `findAll(LdapQuery)` | Ghép điều kiện bằng API an toàn |
| Xử lý LDAP controls hoặc thao tác thấp hơn Repository | `LdapTemplate` / `LdapClient` | Kiểm soát chi tiết search và response |

## 7. Lỗi thường gặp và nguyên tắc vận hành

1. **Sai kiểu ID:** khai báo `LdapRepository<DirectoryPerson, Long>` là sai. Dùng `LdapRepository<DirectoryPerson>` và `@Id Name dn` từ Spring LDAP ODM.
2. **Sai mapping:** tên method `findBySurname` chỉ hợp lệ nếu entity có property Java `surname`; nếu property là `sn`, dùng `findBySn`. Nếu Java là `surname` nhưng LDAP là `sn`, ánh xạ bằng `@Attribute(name="sn")`.
3. **Sai base DN:** với `ContextSource` base `dc=example,dc=org`, query `base("ou=people")` là nhánh tương đối. Ghép thêm root DN lần nữa có thể dẫn đến tìm sai nơi.
4. **Đọc nhầm kết quả rỗng:** phân biệt không có entry phù hợp, sai search scope, schema/objectClass không khớp, tài khoản bind không đủ quyền hoặc server đã áp giới hạn. Không mặc định kết luận thư mục không có người dùng.
5. **Tải toàn bộ directory:** tránh `findAll()` trên cây lớn hoặc `Containing` với chuỗi rất ngắn. Đặt base phù hợp và giới hạn số lượng/thời gian; kiểm tra index trên `uid`, `mail`, `sn` theo nghiệp vụ.
6. **Tự nối filter từ input:** chuỗi `"(&(uid=" + input + ")(objectClass=person))"` có nguy cơ LDAP injection. Dùng binding/`LdapQueryBuilder` và chính sách allowlist cho tên attribute, base DN.
7. **Nhầm giữa giới hạn và tính đầy đủ:** một search bị `countLimit` hoặc server size limit cắt kết quả **không phải** toàn bộ kết quả khớp. Ghi nhận giới hạn này trong API/UX.
8. **Quên bảo mật kết nối:** sử dụng LDAPS hoặc StartTLS theo cấu hình hạ tầng, xác thực certificate, bind bằng tài khoản quyền tối thiểu; không đưa password hoặc thông tin định danh nhạy cảm vào log.

## 8. Bài thực hành

Giả sử thư mục `ou=people,dc=example,dc=org` có ba người:

| uid | sn | givenName | mail |
| --- | --- | --- | --- |
| `lan` | `Nguyen` | `Lan` | `lan@example.org` |
| `nam` | `Nguyen` | `Nam` | `nam@example.org` |
| `mai` | `Tran` | `Mai` | *(không có attribute `mail`)* |

**Yêu cầu:**

1. Thêm `findBySn(String sn)` và `findByMailIsNull()` vào Repository; dự đoán danh sách `uid` trả về.
2. Viết `findBySnAndGivenName` tìm entry `uid=lan`; mô tả phần filter LDAP sinh ra.
3. Tạo truy vấn cho những entry có `mail` tồn tại dưới `ou=people`, giới hạn 2 kết quả và thời gian 1 giây bằng `LdapQueryBuilder`.
4. Giải thích vì sao `countLimit(2)` không bảo đảm nhận được `lan` và `nam` theo đúng thứ tự trong bảng.
5. Thử đầu vào `"Nguyen*)(uid=*)"` tại bộ lọc họ; kiểm tra rằng cách dùng `.is(input)` không biến giá trị thành phần cấu trúc filter tùy ý.

**Gợi ý đáp án:** `findBySn("Nguyen")` tìm `lan` và `nam`; `findByMailIsNull()` tìm `mai`; `findBySnAndGivenName("Nguyen", "Lan")` diễn tả `(&(sn=Nguyen)(givenName=Lan))` cộng điều kiện chọn object class. Bài 3 dùng `.base("ou=people").countLimit(2).timeLimit(1000).where("mail").isPresent()` (kèm điều kiện `objectClass` khi cần). Bài 4: LDAP search không mặc nhiên có thứ tự ổn định; phải xem việc cắt ngưỡng là **giới hạn**, không phải cam kết thứ tự hay phân trang.

Khi kiểm thử trên thư mục thật hoặc test fixture, kiểm tra cả trường hợp **0**, **1**, **nhiều** kết quả; entry thiếu attribute; scope sai; dấu tiếng Việt; ký tự cần escape; và kết quả bị cắt bởi giới hạn server. Đối chiếu DN trả về với branch dự kiến và không khẳng định tính duy nhất chỉ dựa trên `findBy...`.

## Tài liệu tham khảo

- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html): từ khóa dẫn xuất, `@Query`, binding và escaping.
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): `@EnableLdapRepositories`, ODM, kiểu ID và giới hạn paging/sorting.
- [Spring Data LDAP — `LdapRepository` API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapRepository.html): `findAll(LdapQuery)`, `findOne(LdapQuery)`.
- [Spring Data LDAP — `@Query` API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/Query.html): base, scope, countLimit và timeLimit.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `LdapQueryBuilder`, filter, search scope và giới hạn truy vấn.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute`.
