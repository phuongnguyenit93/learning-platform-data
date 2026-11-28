# ODM là gì và khác ORM ở những điểm nào?

Trong **Spring Data LDAP**, lập trình viên thường làm việc với một đối tượng Java như `DirectoryPerson`, nhưng dữ liệu thực tế được lưu thành **entry trong cây thư mục LDAP**. Cơ chế nối hai thế giới đó gọi là **ODM (Object–Directory Mapping)**. ODM có nét giống ORM (Object–Relational Mapping) ở chỗ giảm công việc chuyển đổi dữ liệu thủ công; tuy nhiên, mô hình lưu trữ, định danh, truy vấn và cập nhật của LDAP khác đáng kể với cơ sở dữ liệu quan hệ.

Bài thuộc chương **Ánh xạ thực thể** này giúp bạn nhận biết ODM, phân biệt đúng với ORM/JPA và hiểu vì sao Spring Data LDAP cung cấp repository cùng cơ chế ánh xạ entry phân cấp sang đối tượng Java. Các khái niệm DN, `objectClass`, schema, CRUD và truy vấn an toàn là nền tảng để sử dụng repository hoặc `LdapTemplate` đúng cách.

## 1. ODM giải quyết bài toán gì?

**LDAP (Lightweight Directory Access Protocol)** là giao thức truy cập dịch vụ thư mục. Dữ liệu được tổ chức thành một **Directory Information Tree (DIT)**, gồm những entry có vị trí phân cấp. Mỗi entry mang một **Distinguished Name (DN)** và tập thuộc tính do schema LDAP quy định. Một thuộc tính có thể có nhiều giá trị.

Ví dụ, một entry người dùng trong thư mục có thể được biểu diễn bằng LDIF:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
givenName: An
mail: an.nguyen@example.org
```

Đọc entry này cần phân biệt:

- **DN** `uid=u1001,ou=people,dc=example,dc=org` xác định vị trí và tên duy nhất của entry trong cây tại thời điểm truy cập. Các thành phần `uid=u1001`, `ou=people`, `dc=example`, `dc=org` là các **Relative Distinguished Name (RDN)** trên đường đi tới gốc. DN có thể thay đổi khi entry được đổi tên hoặc di chuyển.
- **`objectClass`** chỉ ra những loại đối tượng entry tuân theo, từ đó quyết định thuộc tính bắt buộc (**MUST**) và được phép (**MAY**) theo schema. Ở ví dụ này, `person` yêu cầu các thuộc tính như `cn` và `sn`.
- **Thuộc tính** như `cn`, `sn`, `mail` lưu giá trị của entry; không thể mặc nhiên coi mỗi thuộc tính là một cột SQL chỉ có một giá trị.

Trong Java, nếu không có ODM, bạn phải lấy `Attributes` từ kết quả tìm kiếm LDAP, đọc từng thuộc tính, xử lý giá trị thiếu/nhiều giá trị và chuyển thành đối tượng. ODM dùng metadata ánh xạ để tự thực hiện phần lớn công việc đó:

```text
Ứng dụng Java
  └── DirectoryPerson { dn, uid, commonName, surname, email }
                  ⇅ ODM: @Entry, @Id, @Attribute
Dịch vụ thư mục LDAP
  └── dc=example,dc=org
        └── ou=people
              └── uid=u1001  (entry có objectClass, cn, sn, mail, ...)
```

**ODM không biến LDAP thành SQL.** Nó ánh xạ dữ liệu từ entry sang đối tượng Java và ngược lại, trong khi thao tác phía dưới vẫn tuân theo cấu trúc DN, schema, bộ lọc tìm kiếm và quyền truy cập của LDAP.

## 2. ORM là gì và vì sao dễ nhầm với ODM?

**ORM (Object–Relational Mapping)** ánh xạ đối tượng Java với bảng, hàng và cột trong cơ sở dữ liệu quan hệ. Trong hệ sinh thái Spring, ví dụ quen thuộc là **JPA/Hibernate**: một đối tượng `Employee` thường đại diện cho một hàng của bảng `employee`, `@Id` ánh xạ khóa chính và các quan hệ có thể được biểu diễn qua `@ManyToOne`, `@OneToMany`, ...

ODM và ORM cùng đưa ra cảm giác “làm việc với object thay vì cú pháp truy cập dữ liệu ở tầng thấp”. Nhưng entry LDAP là một phần của **cây tên phân cấp**, còn hàng SQL thuộc **bảng quan hệ**; sự khác biệt này quyết định thiết kế domain và cách viết nghiệp vụ.

| Khía cạnh | ODM với Spring Data LDAP | ORM với JPA/Hibernate |
|---|---|---|
| Nguồn dữ liệu | LDAP directory, cây các entry | RDBMS, bảng/hàng/cột |
| Đơn vị ánh xạ | Entry và thuộc tính LDAP | Entity và cột/bảng |
| Định danh | DN (`javax.naming.Name` trong Spring LDAP ODM); gắn với tên và vị trí entry | Primary key; thường độc lập với vị trí lưu trữ vật lý |
| Mô tả cấu trúc | `objectClass`, schema LDAP, thuộc tính MUST/MAY | DDL, kiểu cột, ràng buộc khóa, quan hệ |
| Giá trị thuộc tính | Có thể đa trị; dữ liệu tuân theo syntax/matching rule của LDAP | Thường một giá trị/cột; quan hệ nhiều giá trị được mô hình bằng bảng phụ hoặc bảng liên kết |
| Tìm kiếm | Search base, search scope, LDAP filter như `(sn=Nguyen)` | SQL/JPQL, điều kiện, join, group by, aggregate |
| Liên kết dữ liệu | Thường qua DN hoặc thuộc tính tham chiếu, ví dụ `member`; không tự có JPA association | Foreign key, join, mapping quan hệ và cơ chế tải quan hệ |
| Cập nhật | LDAP add/modify/delete; đổi RDN hoặc chuyển nhánh là thao tác rename/move | SQL INSERT/UPDATE/DELETE; thay khóa chính có ngữ nghĩa khác |
| Giao dịch | Không mặc định có giao dịch ACID trải nhiều entry như RDBMS; tùy năng lực máy chủ/extension | Thường có transaction ACID do database cung cấp, tích hợp `@Transactional` |
| Công cụ Spring | `@Entry`, `@Attribute`, `@Id`, `LdapRepository`, `LdapTemplate` | `@Entity`, `@Column`, `@Id`, `JpaRepository`, `EntityManager` |

**Ví dụ về định danh:** hai entry `uid=u1001,ou=people,dc=example,dc=org` và `uid=u1001,ou=contractors,dc=example,dc=org` có thể cùng `uid` nhưng **DN khác nhau**. Vì vậy, không được xem `uid` là khóa chính toàn cục nếu schema và chính sách thư mục không bảo đảm tính duy nhất đó. Mặt khác, nếu chuyển người dùng từ `ou=people` sang `ou=contractors`, DN thay đổi ngay cả khi người dùng đó vẫn là cùng một thực thể nghiệp vụ.

## 3. ODM được thể hiện thế nào trong Spring Data LDAP?

Spring Data LDAP dùng cơ chế **Object–Directory Mapping của Spring LDAP** và bổ sung abstraction repository. Những annotation thường gặp nằm trong `org.springframework.ldap.odm.annotations`:

- `@Entry`: khai báo lớp Java đại diện cho entry LDAP, kèm các `objectClasses` và `base` tương đối khi cần.
- `@Id`: chỉ trường giữ DN, thường có kiểu `javax.naming.Name`. Đây **không phải** `@Id` của JPA (`jakarta.persistence.Id`).
- `@Attribute(name = "...")`: gắn field Java với tên thuộc tính LDAP, chẳng hạn field `surname` với `sn`.
- `@DnAttribute`: dùng khi một phần DN được ánh xạ từ thuộc tính, hữu ích lúc tạo DN từ các thành phần RDN. Cần hiểu rõ base và thứ tự RDN trước khi áp dụng.
- `@Transient`: đánh dấu dữ liệu thuộc đối tượng Java nhưng không được ánh xạ thành thuộc tính LDAP.

### Ví dụ: ánh xạ một LDAP entry sang Java

```java
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
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) { this.commonName = commonName; }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

Ở đây, `@Entry` nói rằng đối tượng `DirectoryPerson` biểu diễn một LDAP entry với nhóm object class đã khai báo. Field `commonName` được lưu vào `cn`, còn `surname` vào `sn`. Trường `dn` là địa chỉ của entry trong cây. **Schema của máy chủ LDAP** vẫn quyết định entry có hợp lệ hay không: annotation không cho phép ghi một thuộc tính bị schema cấm, cũng không tự khắc phục thiếu thuộc tính MUST.

Việc ánh xạ một field `String` giả định ứng dụng chỉ cần một giá trị của thuộc tính đó. Nếu directory cho phép nhiều giá trị (ví dụ một người có nhiều địa chỉ email), hãy thiết kế kiểu collection được ODM hỗ trợ, xác nhận schema/matching rule và kiểm tra cách mapper đọc/ghi các giá trị; không được âm thầm làm mất các giá trị còn lại.

### Repository tương ứng

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findBySurname(String surname);
}
```

Với cơ chế truy vấn suy ra từ tên phương thức của Spring Data LDAP, `findBySurname("Nguyen")` tìm theo thuộc tính Java `surname`, được mapper liên hệ với thuộc tính LDAP `sn`. Kết quả là danh sách các `DirectoryPerson`, không phải các hàng JPA. Repository phải được cấu hình để kết nối đúng LDAP server và quét thấy interface này.

**Lưu ý:** Các snippet minh họa cách ánh xạ và API. Để chạy thật, ứng dụng còn cần dependency Spring Data LDAP/Spring LDAP, cấu hình kết nối, tài khoản bind có quyền phù hợp, dữ liệu directory và schema tương ứng.

## 4. DN và RDN: điểm khác biệt cốt lõi với khóa chính SQL

Trong cơ sở dữ liệu quan hệ, ID như `employee_id = 1001` thường chỉ là một giá trị khóa; thay đổi phòng ban không nhất thiết làm đổi ID. Trong LDAP, DN thể hiện đường dẫn đến entry:

```text
uid=u1001,ou=people,dc=example,dc=org
└── RDN       └── nhánh cha └── các thành phần domain
```

Trong cấu hình thường gặp, `spring.ldap.base` là `dc=example,dc=org`; khi đó thao tác dựa trên `LdapContextSource` thường dùng DN **tương đối với base này**, chẳng hạn `uid=u1001,ou=people`. Đừng tự thêm `dc=example,dc=org` vào mọi DN mà không kiểm tra base của context; điều đó dễ làm lặp hậu tố hoặc định vị sai entry.

Ví dụ tạo DN tương đối để tìm đúng entry:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "u1001")
    .build();

var found = directoryPersonRepository.findById(relativeDn);
```

Đoạn trên giả định `directoryPersonRepository` đã được inject, directory có `ou=people` và tài khoản bind có quyền đọc entry. `LdapNameBuilder` giúp tạo DN theo từng RDN, an toàn và dễ đọc hơn việc tự ghép DN từ dữ liệu người dùng. Khi **tạo mới** entry, cần xác định cách ODM tạo DN (ví dụ từ `@DnAttribute` cùng `@Entry`) và cách repository nhận diện entity mới; đừng giả định cứ gán sẵn `@Id` rồi gọi `save()` là chắc chắn thực hiện LDAP add. Cần kiểm thử riêng thao tác create trên directory thật hoặc directory dùng cho test.

**Đổi DN không đơn thuần là sửa ID:** đổi `uid` trong RDN, đổi tên entry hoặc chuyển entry sang OU khác có thể cần thao tác rename/move (`LdapTemplate.rename(...)` hoặc chức năng tương ứng) và xem xét các tham chiếu DN ở entry khác. Không nên giả định `save()` sẽ tự di chuyển entry như cập nhật một field trong bảng.

## 5. Truy vấn và CRUD: cùng làm việc với object nhưng API có giới hạn khác

`LdapRepository` cung cấp thao tác repository quen thuộc và hỗ trợ query method cho các trường hợp đơn giản. Với truy vấn directory đặc thù hơn, `LdapTemplate` cho phép kiểm soát **base**, **scope**, **filter** và thuộc tính cần đọc. Đằng sau cả hai là các thao tác LDAP (search/add/modify/delete), không phải câu SQL.

Ví dụ tìm người theo `uid` bằng `LdapTemplate` và bộ xây dựng truy vấn:

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class DirectoryLookup {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findByUid(String userInput) {
        LdapQuery ldapQuery = query()
            .base("ou=people")
            .where("uid").is(userInput);

        return ldapTemplate.find(ldapQuery, DirectoryPerson.class);
    }
}
```

`userInput` đi vào API xây dựng filter để được escape đúng quy tắc LDAP. **Không** nối chuỗi kiểu `"(uid=" + userInput + ")"`, vì các ký tự đặc biệt như `*`, `(`, `)`, `\\` có thể thay đổi ý nghĩa của filter và gây LDAP injection. Việc escape filter cũng khác với escape RDN/DN; hãy dùng API dành riêng cho từng trường hợp.

Đối chiếu vòng đời dữ liệu:

| Ý định | Spring Data LDAP | ORM/JPA |
|---|---|---|
| Đọc | `findById(...)`, query method hoặc LDAP search | `findById(...)`, JPQL, SQL |
| Thêm | Tạo entry với DN, object class, các thuộc tính hợp lệ | INSERT hàng thỏa ràng buộc bảng |
| Sửa thuộc tính | LDAP modify; chịu giới hạn schema và ACL | UPDATE cột, theo transaction và mapping JPA |
| Xóa | LDAP delete; có thể bị từ chối nếu entry có con | DELETE hàng; xét foreign key/cascade |
| Đổi tên/vị trí | Rename/move DN, cần chú ý cây và tham chiếu | Thường update thuộc tính/foreign key |

**Chú ý về giao dịch:** đừng đặt giả định rằng một loạt `repository.save()` hoặc thao tác `LdapTemplate` trên các entry khác nhau sẽ rollback cùng nhau như một transaction JPA. LDAP server có thể cung cấp extension hoặc chức năng giao dịch riêng, nhưng đó không phải bảo đảm mặc định của Spring Data LDAP. Với cập nhật đồng bộ nhiều entry, cần có quy trình xử lý lỗi, retry hoặc bù trừ phù hợp.

## 6. Những tình huống ODM không thể áp dụng theo tư duy ORM

### Tình huống A: Người dùng thuộc nhiều nhóm

Trong database quan hệ, bạn có thể có `users`, `groups`, `user_group`, dùng khóa ngoại và `@ManyToMany`. Trong LDAP, nhóm có thể là entry `groupOfNames` chứa nhiều giá trị `member` là DN của thành viên. ODM có thể ánh xạ `member` thành một tập DN, nhưng **không tự cung cấp join, lazy loading hay cascade JPA** để biến chúng thành các object người dùng hoàn chỉnh. Muốn lấy thông tin từng thành viên, ứng dụng phải thực hiện lookup phù hợp, kiểm soát số lần truy vấn và xử lý DN không còn tồn tại.

### Tình huống B: Chuyển người dùng sang OU khác

Một bộ phận đổi từ `ou=people` sang `ou=alumni`. Trong ORM, việc cập nhật `department_id` có thể đủ. Trong LDAP, DN của entry thay đổi, nên thao tác rename/move và cập nhật các entry tham chiếu theo DN có thể cần thiết. Một số directory quản lý tham chiếu tự động bằng cơ chế riêng; không được coi đó là hành vi chung của mọi máy chủ LDAP.

### Tình huống C: Thêm thuộc tính mới vào entity Java

Thêm field `@Attribute(name = "employeeNumber")` không giống với chạy migration thêm cột. Schema LDAP của object class phải cho phép thuộc tính đó; tài khoản bind phải có quyền ghi. Nếu không, server có thể trả lỗi schema violation hoặc insufficient access rights, dù lớp Java biên dịch bình thường.

### Tình huống D: Tạo báo cáo nhiều bảng và thống kê

SQL/JPA thường thích hợp khi nghiệp vụ cần join phức tạp, aggregate, ràng buộc dữ liệu quan hệ và giao dịch nhiều bản ghi. LDAP mạnh ở tra cứu danh tính, người dùng, nhóm và cấu hình phân cấp, nhưng không được thiết kế để thay thế mọi khả năng truy vấn của RDBMS.

## 7. Kiểm tra thực tế khi xây dựng entity LDAP

Trước khi viết repository hay gọi `save()`, hãy xác định đầy đủ:

1. **Base DN và đường đi:** DN là tuyệt đối hay tương đối với `ContextSource`? Entry nằm ở OU nào? Đổi OU có tác động ra sao?
2. **Schema:** Những `objectClass` nào được dùng? Thuộc tính nào bắt buộc, được phép, đơn trị hay đa trị? Thuộc tính nào là RDN?
3. **Mapping:** `@Id` là `Name`; `@Attribute` trỏ đúng tên LDAP; object có constructor và các field/kiểu dữ liệu mapper hỗ trợ.
4. **Truy vấn:** Giới hạn search base và scope hợp lý; dùng filter builder/escaping thay vì ghép chuỗi; lưu ý phân trang và giới hạn kết quả của server.
5. **Bảo mật:** Dùng LDAPS hoặc StartTLS theo khả năng hạ tầng, xác thực chứng chỉ máy chủ, giữ mật khẩu bind ngoài mã nguồn, cấp quyền tối thiểu và không ghi thông tin nhạy cảm vào log.
6. **Kiểm thử tích hợp:** Chạy thử với LDAP directory có schema giống môi trường đích (có thể dùng embedded/test directory), kiểm tra đọc/ghi/xóa, đổi DN, thuộc tính đa trị, lỗi schema, lỗi quyền và filter có ký tự đặc biệt.

Một lưu ý quan trọng: **Spring Data LDAP là công cụ ánh xạ và truy cập LDAP, không phải bản thay tên của Spring Data JPA**. Repository làm API dễ học hơn, nhưng sự đúng đắn của ứng dụng vẫn phụ thuộc hiểu DN, schema, `objectClass`, cách truy vấn directory và đặc tính cập nhật của máy chủ LDAP.

## 8. Tự đối chiếu kiến thức qua một ví dụ

Giả sử ứng dụng cần lưu tài khoản nhân viên để các hệ thống khác tra cứu và xác thực; đồng thời cần lưu đơn hàng, chi tiết thanh toán và thống kê doanh thu.

- **Phần danh tính/người dùng/nhóm:** directory LDAP và ODM thường hợp lý khi tổ chức đã có hệ thống LDAP làm nguồn dữ liệu cho các mục này. Một `DirectoryPerson` ánh xạ tới entry dựa trên DN và schema.
- **Phần đơn hàng/thanh toán/báo cáo:** RDBMS và ORM phù hợp hơn với quan hệ dữ liệu, giao dịch và truy vấn tổng hợp. Một `OrderEntity` ánh xạ tới bảng và có primary key.
- **Kết nối hai phần:** có thể lưu một mã định danh ứng dụng ổn định và thực hiện lookup LDAP khi cần. Không nên mặc nhiên dùng DN như khóa ngoại bất biến, bởi rename/move có thể làm DN thay đổi.

**Ghi nhớ:** ODM ánh xạ **Java object ↔ LDAP entry**, với DN và schema; ORM ánh xạ **Java object ↔ relational row**, với primary key và mô hình quan hệ. Phân biệt này giúp chọn đúng cách thiết kế entity, repository, bộ lọc tìm kiếm và xử lý cập nhật trong Spring Data LDAP.
