# Suy diễn truy vấn từ tên phương thức trong Spring Data LDAP

Trong ứng dụng quản lý danh bạ, ta thường phải tìm nhân viên theo `uid`, họ, email hoặc tổ hợp nhiều điều kiện. Nếu tự viết bộ lọc LDAP cho từng trường hợp, lớp truy cập dữ liệu có thể đầy các chuỗi như `(&(objectClass=inetOrgPerson)(sn=Nguyen)(mail=*@example.org))`. **Spring Data LDAP** cho phép biểu đạt nhiều truy vấn thông dụng bằng **tên phương thức của repository**: khai báo `findBySurnameAndEmailEndingWith(...)`, framework phân tích tên và tạo LDAP filter phù hợp.

Bài học thuộc chương **Truy vấn Repository**, tập trung vào cơ chế **suy diễn truy vấn từ tên phương thức** (*derived query methods*). Phạm vi của module `SPRING_DATA_LDAP` là truy cập dịch vụ thư mục LDAP bằng repository và ánh xạ entry phân cấp sang Java; vì vậy các ví dụ luôn gắn tên thuộc tính Java với DN, `objectClass`, schema, base DN, filter an toàn và hành vi thực tế của directory.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Đọc và viết tên phương thức dạng `findBy…`, `findBy…And…`, `findBy…Or…` với các từ khóa truy vấn LDAP được hỗ trợ.
- Hiểu sự khác biệt giữa **tên property Java** và **tên thuộc tính LDAP**, đặc biệt khi có `@Attribute`.
- Giải thích cách tên phương thức trở thành điều kiện tìm kiếm LDAP và cách `@Entry` thu hẹp loại entry.
- Chọn kiểu trả về `List<T>` hoặc `Optional<T>` dựa trên tính duy nhất của kết quả.
- Biết khi nào cần chuyển sang `@Query`, `LdapQuery` hoặc `LdapTemplate`, và xử lý bộ lọc/đầu vào một cách an toàn.
- Thiết kế kiểm thử tích hợp để xác nhận kết quả trên directory có schema và ACL thực tế.

## 2. Mô hình truy vấn LDAP phía sau repository

LDAP không truy vấn theo bảng và cột như SQL. Nó tìm **entry** trong cây thư mục dựa trên **base DN**, **phạm vi tìm kiếm** (*scope*) và **filter**.

Ví dụ, entry:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
```

Cây directory giả định:

```text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    ├── uid=minh
    └── uid=hoa
```

Muốn tìm một người có `sn=Nguyen`, về mặt logic ứng dụng cần một filter như:

```text
(&(objectClass=inetOrgPerson)(sn=Nguyen))
```

Dấu `&` là phép **AND**; `(objectClass=inetOrgPerson)` giới hạn loại entry; `(sn=Nguyen)` giới hạn giá trị thuộc tính. Muốn tìm nhân viên có họ Nguyen và email bắt đầu bằng `lan`:

```text
(&(objectClass=inetOrgPerson)(sn=Nguyen)(mail=lan*))
```

`*` ở đây là ký tự đại diện trong LDAP filter; nó khác ký tự `*` được coi là dữ liệu đầu vào người dùng. Khi suy diễn query, Spring Data LDAP tạo biểu thức tìm kiếm tương ứng từ tên phương thức và metadata của entity. Chuỗi filter thực tế có thể chứa thêm điều kiện hoặc khác cách sắp xếp nhánh, nhưng phải giữ cùng ý nghĩa.

**Cần nhớ:** `dn` định danh entry theo cây; `uid`, `sn`, `mail` là thuộc tính của entry. Truy vấn bằng một thuộc tính không giống tra cứu theo DN.

## 3. Chuẩn bị entity và repository

Để có ví dụ nhất quán, giả sử ứng dụng Spring Boot đã cấu hình kết nối LDAP với base `dc=example,dc=org`, directory có nhánh `ou=people` và schema tương thích `inetOrgPerson`.

### 3.1. Mapping của entity

```java
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

    // Constructor không tham số, getter/setter được lược bớt.
}
```

Có hai lớp tên cần phân biệt:

| Property trong Java | Thuộc tính LDAP | Định nghĩa mapping |
|---|---|---|
| `uid` | `uid` | `@Attribute(name = "uid")` |
| `fullName` | `cn` | `@Attribute(name = "cn")` |
| `surname` | `sn` | `@Attribute(name = "sn")` |
| `email` | `mail` | `@Attribute(name = "mail")` |
| `dn` | Distinguished Name | `@Id` của Spring LDAP ODM |

**Tên phương thức repository dùng tên property Java.** Do vậy `findBySurname("Nguyen")` là đúng với mapping trên, còn `findBySn("Nguyen")` không đúng nếu entity không có property tên `sn`. Tương tự, `findByEmail` sử dụng LDAP attribute `mail`, không yêu cầu một property Java tên `mail`.

Annotation `@Id` trong ví dụ là `org.springframework.ldap.odm.annotations.Id` (không phải `org.springframework.data.annotation.Id`). Với LDAP, ID của entity là `javax.naming.Name`; không nên giả định ID là `Long` như nhiều repository JPA.

### 3.2. Repository có phương thức suy diễn

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {

    List<PersonEntry> findBySurname(String surname);

    List<PersonEntry> findBySurnameAndEmail(
        String surname, String email
    );

    List<PersonEntry> findBySurnameOrEmail(
        String surname, String email
    );

    List<PersonEntry> findByEmailStartingWith(String prefix);

    List<PersonEntry> findByEmailContaining(String fragment);

    List<PersonEntry> findByEmailIsNotNull();

    List<PersonEntry> findByEmailIsNull();

    Optional<PersonEntry> findByUid(String uid);
}
```

Repository này chưa có class triển khai tự viết. Khi khởi tạo ứng dụng, Spring Data tạo proxy, xác định entity tương ứng và chuẩn bị các phương thức truy vấn. Khi được gọi, phương thức sẽ dẫn tới LDAP search. `Optional<PersonEntry>` của `findByUid` chỉ hợp lý khi dữ liệu và base tìm kiếm **bảo đảm nhiều nhất một entry** khớp `uid`; nếu không có ràng buộc đó, ưu tiên trả về `List<PersonEntry>`.

Một repository LDAP có thể kế thừa `LdapRepository<PersonEntry>` chỉ với **một** tham số kiểu. Interface này cũng cung cấp CRUD và phương thức nhận `LdapQuery`. Spring Data LDAP không tự tạo schema, nhánh LDAP hoặc quyền ghi.

## 4. Framework phân tích tên phương thức như thế nào?

Xét lời gọi:

```java
List<PersonEntry> results =
    repository.findBySurnameAndEmailStartingWith("Nguyen", "lan");
```

Để chạy được, thêm khai báo:

```java
List<PersonEntry> findBySurnameAndEmailStartingWith(
    String surname, String prefix
);
```

Tên phương thức có thể đọc thành các phần:

```text
find  By  Surname  And  Email  StartingWith
│     │      │      │     │         │
│     │      │      │     │         └─ Điều kiện tiền tố
│     │      │      │     └─────────── Property Java "email"
│     │      │      └───────────────── AND
│     │      └──────────────────────── Property Java "surname"
│     └─────────────────────────────── Bắt đầu phần điều kiện
└───────────────────────────────────── Hành động tìm kiếm
```

Diễn giải ý nghĩa:

1. `find…By` cho biết đây là phương thức truy vấn; phần sau `By` được phân tích thành điều kiện.
2. `Surname` và `Email` phải khớp các property của `PersonEntry`.
3. `And` kết hợp hai điều kiện cùng đúng.
4. `StartingWith` yêu cầu thuộc tính `email` bắt đầu bằng chuỗi truyền vào.
5. Nhờ `@Attribute`, filter dùng tên thuộc tính LDAP `sn` và `mail`, thay vì `surname` và `email`.

Với dữ liệu mẫu, kết quả tương đương với điều kiện LDAP:

```text
(&(objectClass=inetOrgPerson)(sn=Nguyen)(mail=lan*))
```

Đây là biểu diễn **ý nghĩa truy vấn**, không phải cam kết chuỗi filter sẽ chính xác từng ký tự trong mọi phiên bản Spring Data LDAP. `@Entry(base = "ou=people")` cùng base cấu hình giới hạn nơi tìm kiếm; `objectClasses` giúp giới hạn entry theo schema.

## 5. Những từ khóa quan trọng trong derived query của LDAP

Với `PersonEntry` ở trên, các phương thức minh họa:

| Tên phương thức | Ý nghĩa | Filter LDAP minh họa (đã lược điều kiện objectClass) |
|---|---|---|
| `findByUid("lan")` | `uid` bằng `lan` | `(uid=lan)` |
| `findBySurname("Nguyen")` | `sn` bằng `Nguyen` | `(sn=Nguyen)` |
| `findBySurnameNot("Nguyen")` | `sn` không bằng `Nguyen` | `(!(sn=Nguyen))` |
| `findByEmailIsNotNull()` | Entry có thuộc tính `mail` | `(mail=*)` |
| `findByEmailIsNull()` | Entry thiếu thuộc tính `mail` | `(!(mail=*))` |
| `findByEmailStartingWith("lan")` | `mail` bắt đầu bằng `lan` | `(mail=lan*)` |
| `findByEmailEndingWith("@example.org")` | `mail` kết thúc bằng chuỗi đã cho | `(mail=*@example.org)` |
| `findByEmailContaining("nguyen")` | `mail` chứa chuỗi đã cho | `(mail=*nguyen*)` |
| `findBySurnameAndEmail(…)` | Đồng thời khớp hai thuộc tính | `(&(sn=…)(mail=…))` |
| `findBySurnameOrEmail(…)` | Khớp ít nhất một thuộc tính | Phép OR trên `(sn=…)` và `(mail=…)` |

Các biến thể `IsNotNull`/`NotNull`, `IsNull`/`Null`, `Not`, `Like`/`NotLike`, `GreaterThanEqual` và `LessThanEqual` cũng được nêu trong tài liệu truy vấn riêng cho Spring Data LDAP. Tuy nhiên, cần hiểu đúng giới hạn:

- **`IsNull` không tìm giá trị Java `null` đã lưu trên server.** Nó tìm entry **không có** thuộc tính LDAP tương ứng. Presence filter `(mail=*)` xác định thuộc tính có tồn tại.
- **`StartingWith`, `EndingWith`, `Containing`** là các truy vấn dùng wildcard LDAP; hiệu năng tùy index, matching rule và server. Các truy vấn bắt đầu bằng `*` dễ tốn tài nguyên trên directory lớn.
- **`Like` khác toán tử SQL `LIKE`.** Không áp dụng giả định về ký tự `%` của SQL. Nếu yêu cầu pattern tùy biến, cần kiểm tra quy tắc wildcard và mã hóa filter trong phiên bản thư viện đang dùng.
- **`GreaterThanEqual`/`LessThanEqual`** dùng so sánh LDAP được schema và matching rule của thuộc tính hỗ trợ. Không đồng nhất với phép so sánh số hoặc thời gian của SQL.
- **Không suy ra toàn bộ từ khóa Spring Data JPA đều áp dụng cho LDAP.** Bảng từ khóa chung của Spring Data mô tả nhiều store; hãy dùng danh sách hỗ trợ của Spring Data LDAP và kiểm thử tương thích.

Ví dụ mở rộng:

```java
List<PersonEntry> findByEmailEndingWith(String domain);

List<PersonEntry> findBySurnameNot(String excludedSurname);

List<PersonEntry> findBySurnameAndEmailContaining(
    String surname, String emailFragment
);
```

Các tên này hữu ích khi yêu cầu đã rõ ràng và có ít điều kiện. Nếu tên ngày càng dài hoặc cần nhóm điều kiện phức tạp, query tường minh sẽ dễ đọc và dễ kiểm thử hơn.

## 6. Ghép điều kiện bằng And và Or

Bộ lọc LDAP hỗ trợ:

- AND: `(&(sn=Nguyen)(mail=lan@example.org))`.
- OR: `(|(sn=Nguyen)(mail=lan@example.org))`.
- NOT: `(!(sn=Nguyen))`.

Spring Data phân tích tên phương thức có `And` và `Or` để dựng điều kiện tương ứng:

```java
// Cần cả surname = "Nguyen" VÀ email = "lan@example.org"
List<PersonEntry> findBySurnameAndEmail(
    String surname, String email
);

// Chỉ cần surname = "Nguyen" HOẶC email = "lan@example.org"
List<PersonEntry> findBySurnameOrEmail(
    String surname, String email
);
```

Trong dự án thực tế, không nên dựa vào trực giác về thứ tự ưu tiên của `And` và `Or` khi trộn nhiều toán tử, ví dụ `findBySurnameAndUidOrEmail`. LDAP filter hỗ trợ nhóm bằng ngoặc, nhưng tên phương thức không phải công cụ biểu diễn mọi cấu trúc ngoặc tùy ý. Với logic như `(A OR B) AND (C OR D)`, nên viết filter rõ ràng bằng `@Query` hoặc `LdapQueryBuilder`.

**Thí dụ:** yêu cầu “người họ Nguyen hoặc Tran, đồng thời có email công ty” cần phép nhóm:

```text
(&(objectClass=inetOrgPerson)
  (|(sn=Nguyen)(sn=Tran))
  (mail=*@example.org))
```

Đây là trường hợp nên ưu tiên biểu diễn rõ cấu trúc thay vì ép thành một tên phương thức dài và khó bảo trì.

## 7. Chọn kiểu trả về và điều kiện duy nhất

Tên phương thức quyết định **điều kiện tìm kiếm**, còn kiểu trả về cho biết ứng dụng kỳ vọng **bao nhiêu entry**:

```java
List<PersonEntry> findBySurname(String surname);

Optional<PersonEntry> findByUid(String uid);
```

`findBySurname` có thể tìm thấy nhiều người cùng họ nên trả về `List<PersonEntry>`. `findByUid` trả về `Optional` cho trường hợp được thiết kế với tối đa một entry khớp. Nếu nhiều entry cùng đáp ứng truy vấn trả về đơn, lời gọi có thể phát sinh ngoại lệ về số lượng kết quả; `Optional` không biến truy vấn thành “lấy người đầu tiên” một cách an toàn.

Cần phân biệt ba trường hợp:

| Điều kiện thực tế | Với `List<PersonEntry>` | Với `Optional<PersonEntry>` |
|---|---|---|
| Không có entry khớp | Danh sách rỗng | `Optional.empty()` |
| Có một entry khớp | Danh sách một phần tử | `Optional` chứa entry |
| Có nhiều entry khớp | Danh sách nhiều phần tử | Có thể lỗi vì kỳ vọng kết quả đơn |

Ngoài ra:

- `repository.findById(name)` là thao tác CRUD tìm theo **DN**, do `@Id` quản lý. Nó khác `findByUid("lan")` là tìm theo thuộc tính `uid`.
- Không dùng `findById(String)` để thay thế truy vấn `uid`: ID của LDAP repository là `javax.naming.Name`.
- Tính duy nhất của `uid` thường chỉ được bảo đảm bởi chính sách tổ chức hoặc phạm vi cây cụ thể, không mặc nhiên bởi cú pháp LDAP.

**Giới hạn quan trọng của LDAP repository:** Đừng tự động đưa `Pageable`, `Page<T>`, `Sort` hay `OrderBy…` từ các ví dụ JPA vào repository LDAP rồi giả định sẽ được hỗ trợ. Tài liệu cấu hình LDAP repository nêu rõ paging và sorting không được hỗ trợ qua lớp repository chuẩn do đặc điểm của giao thức. Nếu cần phân trang ở server, hãy tìm hiểu các LDAP control và API thích hợp, cấu hình directory, rồi kiểm thử riêng.

## 8. Tên property, DN và schema tác động thế nào đến truy vấn?

Một derived query chỉ được xây đúng khi cả **Java mapping** lẫn **directory schema** đúng:

1. **Tên Java phải khớp:** `findByFullName(...)` trỏ tới property `fullName`, từ đó đến LDAP attribute `cn`. `findByCn(...)` không hợp lệ nếu class không khai báo property `cn`.
2. **Object class phải phù hợp:** Với `@Entry(objectClasses = …)`, query chỉ nên áp dụng cho entry thuộc loại đã ánh xạ. LDAP server có thể sử dụng schema khác, nhất là trên Active Directory.
3. **Base DN phải phù hợp:** `ou=people` và `ou=contractors` có thể có các `uid` giống nhau; thay search base sẽ thay đổi tập kết quả.
4. **Schema và matching rule quyết định cách so khớp:** Nhiều thuộc tính chuỗi có so khớp không phân biệt hoa thường, nhưng không phải mọi thuộc tính đều như nhau. Không mặc định `IgnoreCase` của các store khác tương đương LDAP matching rule.
5. **Giá trị đa trị cần hiểu đúng:** Một LDAP attribute có thể có nhiều giá trị. Điều kiện bằng nhau thường khớp nếu có giá trị thích hợp trong tập giá trị; kết quả ánh xạ Java cũng phải phù hợp kiểu dữ liệu.

Vì vậy, cùng một phương thức `findBySurname("Nguyen")` có thể cho kết quả khác nhau giữa các directory nếu dữ liệu, schema, base hoặc ACL khác nhau. Tên phương thức hợp lệ về mặt Java chưa chứng minh truy vấn có kết quả trên directory thật.

## 9. An toàn bộ lọc và dữ liệu đầu vào

Giả sử người dùng nhập mã nhân viên qua API:

```java
String suppliedUid = request.uid();
List<PersonEntry> entries = repository.findByUid(suppliedUid);
```

**Không nên** tự ghép filter thành chuỗi như sau:

```java
// Sai: input không đáng tin bị đưa thẳng vào cú pháp filter.
String unsafe = "(uid=" + suppliedUid + ")";
```

Nếu input có `*`, `(`, `)`, `\` hoặc byte đặc biệt, filter có thể bị đổi nghĩa hoặc trở nên không hợp lệ, dẫn tới **LDAP injection**. Với derived query, framework dựng điều kiện từ cấu trúc cố định và xử lý giá trị tham số theo API truy vấn; không cần tự thêm dấu ngoặc hoặc ký tự wildcard vào input.

Khi chuyển sang `@Query`, tham số bind trực tiếp cũng được mã hóa theo quy tắc LDAP filter mặc định (tài liệu Spring Data LDAP dùng RFC 2254 cho phần này). Tuy nhiên, **biểu thức SpEL** và **property placeholder** trong query không được escape tự động theo cùng cơ chế; nếu dùng chúng với dữ liệu không tin cậy phải có xử lý riêng và kiểm thử.

Những thực hành tốt cần tuân thủ:

- Cố định attribute và base DN theo nghiệp vụ; không để người dùng quyết định tùy ý cấu trúc filter hoặc điểm gốc tìm kiếm.
- Giới hạn đầu vào hợp lý theo loại trường (ví dụ độ dài mã nhân viên) và phân quyền trước khi tra cứu thông tin nhạy cảm.
- Không coi kết quả của `findByUid` là đã **xác thực** người dùng; xác thực mật khẩu thuộc luồng bảo mật riêng, thường tích hợp qua Spring Security LDAP.
- Kết nối directory bằng TLS khi giao tiếp ngoài môi trường test, xác thực chứng chỉ và dùng bind account với quyền tối thiểu.

## 10. Khi derived query không còn phù hợp

### 10.1. Dùng `@Query` để diễn đạt filter cố định rõ ràng

Khi điều kiện cần nhiều nhóm logic hoặc attribute đặc thù, có thể khai báo truy vấn tường minh:

```java
import java.util.List;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends LdapRepository<PersonEntry> {

    @Query(
        "(&(objectClass=inetOrgPerson)" +
        "(|(sn=Nguyen)(sn=Tran))" +
        "(mail=:email))"
    )
    List<PersonEntry> findSelectedPeopleByEmail(
        @Param("email") String email
    );
}
```

`:email` là một **giá trị bind**, không phải đoạn cú pháp filter do người dùng nhập. Truy vấn ví dụ chọn người có `sn=Nguyen` hoặc `sn=Tran` và email bằng giá trị truyền vào. Mã ví dụ chỉ minh họa khi nghiệp vụ thật sự cần giới hạn cố định hai họ; một bộ lọc tùy biến từ input phải thiết kế riêng để tránh ghép chuỗi không an toàn.

### 10.2. Dùng `LdapQuery` với repository khi điều kiện động

`LdapRepository<T>` có phương thức nhận trực tiếp `org.springframework.ldap.query.LdapQuery`:

```java
import java.util.List;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public List<PersonEntry> searchByUid(
        PersonRepository repository, String uid) {

    LdapQuery ldapQuery = query()
        .where("uid").is(uid);

    return repository.findAll(ldapQuery);
}
```

Cách này giúp tách **tên thuộc tính cố định** khỏi **giá trị dữ liệu**, tạo filter bằng builder và linh hoạt hơn khi điều kiện phát sinh lúc chạy. Vì `@Entry(base = "ou=people")` đã định nghĩa vị trí của entity, cần kiểm tra tương tác giữa base của entity, `ContextSource` và query khi bổ sung `query().base(...)`.

### 10.3. Dùng `LdapTemplate` khi cần kiểm soát thao tác thấp hơn

Khi cần tùy chỉnh scope, lấy một số attribute, xử lý nhóm hoặc dùng thao tác LDAP đặc thù, `LdapTemplate` của Spring LDAP thường phù hợp:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public List<String> lookupNames(LdapTemplate template, String uid) {
    return template.search(
        query().base("ou=people").where("uid").is(uid),
        (AttributesMapper<String>) attrs ->
            attrs.get("cn").get().toString()
    );
}
```

Ví dụ giả định entry tìm được có `cn`. Với directory không đồng nhất cần xử lý thuộc tính thiếu. Nên chọn mức trừu tượng đơn giản nhất diễn đạt được truy vấn mà vẫn rõ ràng về base DN, filter và quyền truy cập.

| Yêu cầu | Giải pháp nên cân nhắc |
|---|---|
| Tìm theo một hoặc vài property cố định | Derived query `findBy…` |
| Nhiều nhánh `AND`/`OR` cần nhóm rõ ràng | `@Query` |
| Ghép các điều kiện tùy chọn lúc chạy | `LdapQueryBuilder` và `LdapRepository.findAll(query)` |
| Cần scope, attributes, mapping hoặc LDAP operation tùy biến sâu | `LdapTemplate` |
| Xác thực danh tính, kiểm tra quyền đăng nhập | Spring Security LDAP và chính sách bảo mật |

## 11. Ví dụ nghiệp vụ: tra nhân viên theo họ và tên miền email

Giả sử dịch vụ danh bạ cần tìm những người có họ `Nguyen` và email thuộc `example.org`. Bắt đầu từ một repository dễ đọc:

```java
public interface PersonRepository extends LdapRepository<PersonEntry> {

    List<PersonEntry> findBySurnameAndEmailEndingWith(
        String surname, String suffix
    );
}
```

Service xử lý input và gọi phương thức:

```java
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class DirectoryService {
    private final PersonRepository people;

    public DirectoryService(PersonRepository people) {
        this.people = people;
    }

    public List<PersonEntry> peopleInDomain(
            String surname, String emailDomain) {

        String domainSuffix = "@" + emailDomain;
        return people.findBySurnameAndEmailEndingWith(
            surname, domainSuffix
        );
    }
}
```

Kết quả logic là các entry có `sn=Nguyen` **và** `mail` kết thúc bằng `@example.org`. Bởi đây là email domain lấy từ người gọi, trong hệ thống thật nên quy định tập domain được phép tra cứu và xác thực quyền API, thay vì coi mọi chuỗi là một domain đáng tin.

Trên directory có nhiều entry, truy vấn suffix `(mail=*@example.org)` có thể tốn tài nguyên do wildcard đứng đầu. Nếu nghiệp vụ cho phép, tìm theo các trường được đánh chỉ mục tốt hơn, hoặc dùng một thuộc tính phân loại do directory cung cấp để thu hẹp tập entry.

## 12. Kiểm thử tích hợp cho phương thức suy diễn

Derived query cần được kiểm thử với directory có schema và dữ liệu gần thực tế. Mock repository chỉ xác nhận service có gọi đúng method; nó **không kiểm tra** filter, mapping, scope, matching rule hoặc quyền truy cập.

Giả sử test directory chứa:

| DN tương đối dưới `ou=people` | `uid` | `sn` | `mail` |
|---|---|---|---|
| `uid=lan` | `lan` | `Nguyen` | `lan@example.org` |
| `uid=minh` | `minh` | `Nguyen` | `minh@example.org` |
| `uid=hoa` | `hoa` | `Tran` | Không có thuộc tính `mail` |

Các tình huống cần xác minh:

1. `findBySurname("Nguyen")` trả hai entry: `lan` và `minh`.
2. `findBySurnameAndEmailStartingWith("Nguyen", "lan")` trả đúng `lan`.
3. `findBySurnameOrEmail("Tran", "minh@example.org")` trả `hoa` và `minh`.
4. `findByEmailIsNull()` trả `hoa`; `findByEmailIsNotNull()` trả `lan` và `minh`.
5. `findByUid("nobody")` cho kết quả rỗng. Trường hợp nhiều entry cùng `uid` phải xác nhận xử lý đúng với kiểu trả về đơn.
6. Truy vấn `findByUid("la*n")` **không** được diễn giải dấu `*` của input thành wildcard tìm tất cả mã bắt đầu `la`; cần test cả dấu ngoặc và dấu gạch chéo ngược.
7. Tài khoản bind không đủ quyền có thể không thấy entry/attribute; xác minh hành vi ứng dụng khi directory từ chối quyền, vượt giới hạn số kết quả hoặc mất kết nối.
8. Kiểm tra các thuộc tính `@Attribute` dùng tên khác property (`surname` → `sn`, `email` → `mail`) và base DN để phát hiện cấu hình sai.

Khi triển khai test, có thể dùng LDAP server nhúng hoặc container chạy directory phù hợp. Hãy nạp fixture vào nhánh tách biệt, dọn dữ liệu sau test và không cho phép test ghi lên directory production. Các thao tác CRUD, rename DN và thay đổi schema nên có bài test riêng vì chúng không được chứng minh bởi các truy vấn chỉ đọc.

## 13. Những lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Repository không khởi tạo; báo không nhận ra property | Tên `findBySn` không trùng property `surname` | So tên method với field/getter Java và mapping `@Attribute`. |
| Query chạy nhưng không thấy người mong đợi | Base DN, `objectClass` hoặc scope sai | Đối chiếu DN thật, entry class và cấu hình `ContextSource`. |
| `Optional` gây lỗi nhiều kết quả | Tìm kiếm không bảo đảm tính duy nhất | Thu hẹp base/filter hoặc đổi sang kiểu trả về danh sách. |
| `findByEmailIsNull` có kết quả lạ | Entry thật thiếu thuộc tính `mail`, hoặc bị hạn chế đọc | Kiểm tra dữ liệu/ACL bằng quyền test tương đương. |
| Search chứa wildcard quá chậm | `Containing`, `EndingWith` làm filter ít tận dụng index | Chọn thuộc tính tìm kiếm phù hợp và giới hạn phạm vi. |
| Dùng `Pageable` hoặc `Sort` không hoạt động | Áp giả định repository quan hệ sang LDAP | Dùng API/protocol LDAP chuyên biệt khi cần phân trang, sắp xếp. |
| Search thất bại với một số input | Tự nối filter, escape sai hoặc schema matching rule không hợp | Dùng query builder/binding; test dấu `*`, `(`, `)`, `\`. |
| Tên method quá dài, khó hiểu | Nghiệp vụ có nhiều nhóm điều kiện | Viết `@Query` hoặc builder để biểu diễn logic minh bạch. |

Khi điều tra, hãy log thông tin vận hành cần thiết như loại truy vấn và thời gian thực thi, nhưng tránh ghi nguyên thông tin nhạy cảm hoặc credential vào log. Có thể kiểm tra filter tại môi trường test với dữ liệu không nhạy cảm.

## 14. Bài tập tự luyện

**Bài 1 – Đọc mapping.** Với `private String fullName` có `@Attribute(name = "cn")`, hãy viết repository method lấy tất cả entry có tên hiển thị chính xác `Lan Nguyen`. Giải thích vì sao không đặt tên `findByCn`.

**Bài 2 – Ghép điều kiện.** Viết method tìm người có `sn=Nguyen` và email bắt đầu bằng `lan`. Viết filter LDAP tương đương ở mức ý nghĩa.

**Bài 3 – Presence filter.** Giải thích khác nhau giữa `findByEmailIsNull()` và `findByEmailIsNotNull()`. Chúng có liên quan gì tới các filter `(!(mail=*))` và `(mail=*)`?

**Bài 4 – Kết quả đơn.** Khi nào nên trả `Optional<PersonEntry>` và khi nào `List<PersonEntry>`? Điều gì xảy ra nếu có hai entry có cùng `uid` trong phạm vi tìm kiếm?

**Bài 5 – An toàn.** Giải thích rủi ro của `"(uid=" + input + ")"` khi input chứa `*` hoặc ký tự ngoặc; nêu một cách làm an toàn bằng repository hoặc query builder.

**Bài 6 – Chọn công cụ.** Nếu yêu cầu tìm người có `(sn=Nguyen OR sn=Tran) AND mail thuộc example.org`, bạn chọn tên method, `@Query` hay `LdapQueryBuilder`? Giải thích lựa chọn và chỉ ra phần điều kiện cần nhóm.

## 15. Ghi nhớ và nguồn tham khảo

Suy diễn truy vấn giúp biến nhu cầu tìm kiếm directory thường gặp thành tên phương thức Java ngắn gọn. Chuỗi `findBySurnameAndEmailStartingWith` chỉ đúng khi parser nhận ra property của entity, mapping dẫn đến thuộc tính LDAP phù hợp, và base DN, schema, ACL, matching rule hỗ trợ việc tìm kiếm. Với logic phức tạp, hãy dùng `@Query`, `LdapQuery` hoặc `LdapTemplate`; đồng thời luôn kiểm tra cách escape tham số, giới hạn quyền truy cập và kết quả trên directory thật.

Tài liệu chính thức để đối chiếu khi phiên bản Spring Data LDAP thay đổi:

- [Spring Data LDAP – Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html)
- [Spring Data LDAP – Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- [Spring LDAP – Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html)
- [Spring Data LDAP – `LdapRepository<T>` API](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapRepository.html)
- [RFC 4515 – String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
