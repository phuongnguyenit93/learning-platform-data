# Kết hợp điều kiện bằng And, Or và phủ định

Trong **Spring Data LDAP**, truy vấn repository thường không chỉ lọc theo một thuộc tính. Ví dụ, ứng dụng quản lý tài khoản cần tìm người có **họ Nguyễn và tên An**, người có **họ Nguyễn hoặc tên An**, hoặc người có **họ Nguyễn nhưng không dùng một địa chỉ email bị chặn**. Các điều kiện này tương ứng với ba phép logic **AND**, **OR** và **NOT** trong LDAP filter.

Bài thuộc chương **Truy vấn Repository** này giải thích cách biểu diễn các phép logic trong bộ lọc LDAP, cách viết **derived query method** trên `LdapRepository` và khi nào chuyển sang `LdapTemplate` để kiểm soát nhóm điều kiện. Người học cũng sẽ thấy vai trò của DN, `objectClass`, schema, cách escape filter, phạm vi tìm kiếm, quyền truy cập và kiểm thử với directory.

## 1. Chuẩn bị mô hình LDAP để đọc các ví dụ

Giả sử directory có base DN `dc=example,dc=org` và các entry dưới `ou=people`:

```text
dc=example,dc=org
└── ou=people
    ├── uid=u1001  → sn=Nguyen, givenName=An,   mail=an@example.org
    ├── uid=u1002  → sn=Nguyen, givenName=Binh, mail=binh@example.org
    ├── uid=u1003  → sn=Tran,   givenName=An,   mail=blocked@example.org
    ├── uid=u1004  → sn=Tran,   givenName=Chi,  mail=chi@example.org
    └── uid=u1005  → sn=Le,     givenName=An,   mail=(không có)
```

Ví dụ một entry hợp lệ theo schema `inetOrgPerson`:

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
mail: an@example.org
```

Trong đó, **DN (Distinguished Name)** định vị entry trong cây LDAP; `sn`, `givenName`, `mail` là thuộc tính có tên và quy tắc so khớp do **schema** quyết định. `objectClass` mô tả loại entry và những thuộc tính bắt buộc/được phép. Một thuộc tính có thể đa trị; việc so khớp text, phân biệt chữ hoa/thường và khoảng trắng còn tùy **matching rule** của directory.

Để tránh nhập nhằng khi diễn giải kết quả, các bảng bên dưới dùng tập dữ liệu giả định trên với cách so khớp equality thông thường, không dựa vào một cấu hình so khớp đặc biệt.

## 2. LDAP filter có cú pháp logic riêng

LDAP không dùng cú pháp SQL như `WHERE a = ? AND b = ?`. Một LDAP search filter theo RFC 4515 có thể biểu diễn:

| Ý định | LDAP filter | Ý nghĩa |
|---|---|---|
| Họ là Nguyen | `(sn=Nguyen)` | Phép so khớp bằng của thuộc tính `sn` |
| Họ Nguyen **và** tên An | `(&(sn=Nguyen)(givenName=An))` | Hai điều kiện đều đúng |
| Họ Nguyen **hoặc** tên An | `(\|(sn=Nguyen)(givenName=An))` | Ít nhất một điều kiện đúng |
| **Không** có họ Nguyen | `(!(sn=Nguyen))` | Phủ định kết quả so khớp |
| Có thuộc tính mail | `(mail=*)` | Bộ lọc hiện diện (presence) |
| Mail không phải giá trị bị chặn, và phải tồn tại | `(&(mail=*)(!(mail=blocked@example.org)))` | Kết hợp presence với NOT |

Các ký hiệu đặc biệt:

- **`&`**: AND, nằm bên trong một cặp ngoặc bao toàn bộ nhóm điều kiện.
- **`|`**: OR, cũng bao một hoặc nhiều filter con.
- **`!`**: NOT, phủ định **một filter con** (filter con có thể là cả nhóm AND/OR).
- **`(...)`**: từng bộ lọc con luôn có dấu ngoặc.

Không được bỏ dấu ngoặc rồi viết `(sn=Nguyen)&(givenName=An)`: đó không phải một LDAP filter hoàn chỉnh. Đặc biệt, dấu `|` của OR nằm **trong filter**; nó không phải toán tử nối lệnh của shell.

## 3. AND: tất cả điều kiện đều phải khớp

Yêu cầu “tìm người **vừa có họ Nguyen vừa có tên An**” tương ứng với:

```ldap
(&(sn=Nguyen)(givenName=An))
```

Với tập dữ liệu mẫu, chỉ `u1001` thỏa mãn cả hai điều kiện:

| Entry | `sn=Nguyen` | `givenName=An` | AND |
|---|---|---|---|
| u1001 | Đúng | Đúng | **Khớp** |
| u1002 | Đúng | Sai | Không khớp |
| u1003 | Sai | Đúng | Không khớp |
| u1004 | Sai | Sai | Không khớp |
| u1005 | Sai | Đúng | Không khớp |

AND có thể kết hợp nhiều điều kiện, chẳng hạn:

```ldap
(&(objectClass=inetOrgPerson)(sn=Nguyen)(givenName=An))
```

Ở đây, điều kiện về `objectClass` giúp thu hẹp kết quả về loại entry phù hợp. Schema và `@Entry` của Spring LDAP có thể cung cấp ràng buộc class trong một số lời gọi ODM; khi phân tích truy vấn thực tế, cần kiểm tra filter cuối cùng mà tầng truy cập thực hiện.

## 4. OR: chỉ cần một điều kiện khớp

Yêu cầu “tìm người **có họ Nguyen hoặc có tên An**” có filter:

```ldap
(|(sn=Nguyen)(givenName=An))
```

Với dữ liệu mẫu:

| Entry | Họ Nguyen? | Tên An? | OR |
|---|---|---|---|
| u1001 | Đúng | Đúng | **Khớp** |
| u1002 | Đúng | Sai | **Khớp** |
| u1003 | Sai | Đúng | **Khớp** |
| u1004 | Sai | Sai | Không khớp |
| u1005 | Sai | Đúng | **Khớp** |

Một entry thỏa **cả hai nhánh OR** vẫn chỉ là **một entry kết quả của cùng một LDAP search**, không phải tự động trả bản ghi trùng. Nếu ứng dụng chạy **hai truy vấn riêng** rồi tự gộp danh sách, lúc đó mới cần chủ động loại trùng theo định danh phù hợp, thường là DN hoặc định danh directory được thống nhất.

OR với nhiều điều kiện:

```ldap
(|(sn=Nguyen)(sn=Tran)(sn=Le))
```

Nên giới hạn số nhánh OR và phạm vi tìm kiếm theo nhu cầu thực tế; biểu thức OR quá rộng có thể trả nhiều entry và làm tăng tải directory.

## 5. NOT: phủ định điều kiện và lưu ý thuộc tính vắng mặt

Yêu cầu “không có họ Nguyen” có thể biểu diễn:

```ldap
(!(sn=Nguyen))
```

Với các entry `inetOrgPerson` hợp lệ trong ví dụ, `sn` là thuộc tính bắt buộc được kế thừa từ `person`, nên kết quả mong đợi là `u1003`, `u1004`, `u1005`.

Trường hợp cần thận trọng hơn là `mail`, vì nó có thể không tồn tại:

```ldap
(!(mail=blocked@example.org))
```

Đây là **phủ định phép so khớp `mail=blocked@example.org`**, không đồng nghĩa với “entry bắt buộc có email và email khác giá trị bị chặn”. Trong những trường hợp so khớp thông thường, entry **không có `mail`** cũng có thể được chọn bởi phép phủ định. Nếu nghiệp vụ yêu cầu phải có email, viết rõ cả điều kiện hiện diện:

```ldap
(&(mail=*)(!(mail=blocked@example.org)))
```

Phép phủ định trong LDAP vận hành theo kết quả đánh giá filter của directory, bao gồm những trường hợp không xác định khi schema/matching rule hoặc quyền truy cập không đáp ứng. Vì vậy, với thuộc tính tùy chọn, **kiểm thử trường hợp vắng mặt** trên LDAP server đang sử dụng thay vì suy luận máy móc theo `!=` trong Java/SQL.

Đừng viết `(mail!=blocked@example.org)` để thay cho NOT: đây không phải dạng phủ định equality chuẩn của LDAP filter.

## 6. Định nghĩa entity ODM để dùng repository

Trong Spring Data LDAP, repository làm việc với đối tượng Java thông qua ODM (**Object–Directory Mapping**) của Spring LDAP. Ví dụ entity:

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

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "givenName")
    private String givenName;

    @Attribute(name = "mail")
    private String email;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
    public String getGivenName() { return givenName; }
    public void setGivenName(String givenName) { this.givenName = givenName; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

Các điểm cần nhớ:

- `@Id` là DN có kiểu `javax.naming.Name`, khác `@Id` của JPA. DN có thể thay đổi nếu entry được đổi RDN hoặc di chuyển OU.
- `@Attribute(name = "sn")` ánh xạ property Java `surname` sang thuộc tính LDAP `sn`; tên property trong derived method là **`Surname`**, không phải `Sn` nếu entity không có property `sn`.
- `@Entry` mô tả các `objectClass` kỳ vọng và base tương đối; nó **không** tạo schema hay cấp quyền đọc/ghi.
- Repository dùng cấu hình `LdapContextSource`; base của context và base trong ODM phải được hiểu nhất quán với DN thật.

Giả định ứng dụng đã cấu hình kết nối và quét repository, ví dụ base của `LdapContextSource` là `dc=example,dc=org`. Dữ liệu mẫu phải được tạo trong directory thử nghiệm có schema và ACL phù hợp.

## 7. Kết hợp bằng And, Or, Not trong derived query method

Với Spring Data LDAP, một số truy vấn có thể được **suy diễn từ tên phương thức** mà không cần viết filter thủ công:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    // sn=Nguyen AND givenName=An
    List<DirectoryPerson> findBySurnameAndGivenName(
            String surname, String givenName);

    // sn=Nguyen OR givenName=An
    List<DirectoryPerson> findBySurnameOrGivenName(
            String surname, String givenName);

    // NOT (sn=Nguyen)
    List<DirectoryPerson> findBySurnameNot(String surname);
}
```

Phần tên sau `findBy` được phân tích theo **property của entity**: `Surname` → `surname` → `sn`, còn `GivenName` → `givenName`. `And`, `Or` và `Not` diễn tả cách kết hợp/đảo điều kiện; Spring Data LDAP chuyển chúng thành các bộ lọc LDAP tương ứng theo những từ khóa **được phiên bản sử dụng hỗ trợ**.

Ví dụ gọi:

```java
List<DirectoryPerson> exact =
        repository.findBySurnameAndGivenName("Nguyen", "An");

List<DirectoryPerson> either =
        repository.findBySurnameOrGivenName("Nguyen", "An");

List<DirectoryPerson> others =
        repository.findBySurnameNot("Nguyen");
```

Với dữ liệu giả định và phạm vi tìm kiếm `ou=people`, kết quả dự kiến là:

| Query method | UID dự kiến |
|---|---|
| `findBySurnameAndGivenName("Nguyen", "An")` | `u1001` |
| `findBySurnameOrGivenName("Nguyen", "An")` | `u1001`, `u1002`, `u1003`, `u1005` |
| `findBySurnameNot("Nguyen")` | `u1003`, `u1004`, `u1005` |

**Hai lưu ý về API:**

1. Query derivation chỉ hỗ trợ các toán tử được **Spring Data LDAP trong phiên bản đang dùng** triển khai; tập keyword có thể không trùng hoàn toàn với Spring Data JPA. Hãy xác minh query method được repository khởi tạo và chạy đúng trên directory test. Nếu một keyword hay tổ hợp không được hỗ trợ, sử dụng `LdapTemplate` với filter builder.
2. Mô tả filter trong các bảng mang tính **logic**. Filter thực sự có thể được thêm điều kiện `objectClass`/base của ODM và được escape/chuẩn hóa; không khẳng định đây là chuỗi byte chính xác mà repository gửi đi.

## 8. Thứ tự ưu tiên và nhóm điều kiện: tránh suy diễn sai

Giả sử nghiệp vụ muốn:

> Tìm người **(họ Nguyen hoặc tên An)** và **email không bị chặn**.

Biểu thức mong đợi:

```text
(A OR B) AND NOT C
A = (sn=Nguyen)
B = (givenName=An)
C = (mail=blocked@example.org)
```

LDAP filter đầy đủ:

```ldap
(&(|(sn=Nguyen)(givenName=An))(!(mail=blocked@example.org)))
```

Với tập dữ liệu mẫu, lọc OR trước được `u1001, u1002, u1003, u1005`; sau NOT email bị chặn sẽ loại `u1003` và giữ `u1001, u1002, u1005`. Nếu yêu cầu email phải tồn tại, bổ sung `(mail=*)`; khi đó `u1005` bị loại.

Không nên đọc tên phương thức `findBySurnameOrGivenNameAndEmailNot(...)` rồi mặc nhiên hiểu là `(Surname OR GivenName) AND NOT Email`. Cấu trúc parser derived query và độ ưu tiên AND/OR có thể làm bộ lọc logic khác dự kiến, ví dụ `A OR (B AND NOT C)`. Khi biểu thức có **nhiều nhóm ngoặc hoặc cả AND lẫn OR**, hãy viết nhóm rõ bằng `LdapTemplate` hoặc một cơ chế query được thư viện hỗ trợ và kiểm thử filter cuối cùng.

### Phủ định một điều kiện khác phủ định cả nhóm

Hai filter sau không tương đương:

```ldap
(&(sn=Nguyen)(!(givenName=An)))
```

Nghĩa là `sn=Nguyen AND NOT(givenName=An)`: kết quả `u1002`.

```ldap
(!(&(sn=Nguyen)(givenName=An)))
```

Nghĩa là `NOT(sn=Nguyen AND givenName=An)`: với dữ liệu mẫu, mọi người **trừ `u1001`** có thể khớp. Nhóm bị phủ định đã đổi phạm vi tác động của NOT.

Hai quy tắc De Morgan giúp tự kiểm tra:

```text
NOT (A AND B)  tương đương  (NOT A) OR (NOT B)
NOT (A OR B)   tương đương  (NOT A) AND (NOT B)
```

Lưu ý các quy tắc logic cổ điển nên được đối chiếu với ngữ nghĩa LDAP filter ở những trường hợp đánh giá không xác định; với tập thuộc tính đầy đủ và equality thông thường, chúng trực quan như ví dụ.

## 9. Dùng LdapTemplate để nhóm filter phức tạp

`LdapTemplate` phù hợp khi một truy vấn cần **nhóm ngoặc tường minh**, điều kiện hiện diện, nhiều lớp `objectClass` hoặc giới hạn search base/scope riêng. Spring LDAP cung cấp các bộ xây dựng filter như `AndFilter`, `OrFilter`, `NotFilter`, `EqualsFilter` và `PresentFilter`.

Ví dụ truy vấn **`(sn=Nguyen OR givenName=An) AND mail tồn tại AND NOT(mail=blocked@example.org)`**:

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.NotFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.filter.PresentFilter;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class DirectoryPersonSearch {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findEligible(
            String surname, String givenName, String blockedEmail) {

        OrFilter nameGroup = new OrFilter();
        nameGroup.or(new EqualsFilter("sn", surname));
        nameGroup.or(new EqualsFilter("givenName", givenName));

        AndFilter all = new AndFilter();
        all.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        all.and(nameGroup);
        all.and(new PresentFilter("mail"));
        all.and(new NotFilter(
                new EqualsFilter("mail", blockedEmail)));

        LdapQuery ldapQuery = query()
                .base("ou=people")
                .filter(all);

        return ldapTemplate.find(ldapQuery, DirectoryPerson.class);
    }
}
```

Trong ví dụ:

1. `nameGroup` dùng `OrFilter` để tạo nhóm `(|(sn=...)(givenName=...))`.
2. `all` dùng `AndFilter` bao nhóm tên, điều kiện loại entry, presence và phủ định.
3. `NotFilter` phủ định đúng filter `(mail=blockedEmail)`, không phủ định cả nhóm tên.
4. `query().base("ou=people")` bắt đầu tìm tại nhánh tương đối với base DN của `LdapContextSource`, giả định `dc=example,dc=org`.
5. `ldapTemplate.find(ldapQuery, DirectoryPerson.class)` dùng ODM để ánh xạ các entry phù hợp sang `DirectoryPerson`.

**Bộ xây dựng `EqualsFilter` xử lý escape ký tự trong giá trị theo cú pháp LDAP filter.** Không nối chuỗi `"(&(sn=" + surname + ")...)"` từ dữ liệu người dùng. Khi tên thuộc tính được đưa vào builder, hãy dùng **tên thuộc tính cố định/được whitelist** như `sn`, `givenName`, `mail`; không cho input bên ngoài tự chọn attribute hay cú pháp filter tùy ý.

Đoạn code giả định dependency Spring LDAP/Spring Data LDAP phù hợp và directory thử nghiệm có các entry/schema nêu trên. Với các bản thư viện khác nhau, kiểm tra signature API, cách áp dụng base/scope và xử lý search result trong môi trường thực tế.

## 10. Filter an toàn trước LDAP injection

LDAP filter có ký tự điều khiển riêng như dấu sao `*`, cặp ngoặc `(` `)`, dấu gạch chéo ngược `\` và NUL. Nếu lấy nguyên input rồi ghép vào filter:

```java
// SAI: dữ liệu bên ngoài có thể thay đổi cú pháp LDAP filter.
String rawFilter = "(sn=" + userInput + ")";
```

Ví dụ user nhập giá trị chứa dấu `*` hoặc `)` có thể khiến filter bị mở rộng hoặc sai cú pháp. Hãy truyền **giá trị** vào API đã biết cách escape:

```java
// Truy vấn bằng LdapQueryBuilder:
LdapQuery safeQuery = query()
        .base("ou=people")
        .where("sn").is(userInput);

// Hoặc xây filter tường minh:
EqualsFilter safeFilter = new EqualsFilter("sn", userInput);
```

Derived query method cũng nhận tham số như giá trị truy vấn; đừng biến đầu vào thành một phần của tên method hay xây raw filter động. Các toán tử AND/OR/NOT của **nghiệp vụ** phải do code quyết định. Nếu client gửi điều kiện lọc tùy chọn, parse thành cấu trúc được phép (ví dụ chỉ ba field và toán tử hợp lệ) trước khi biến thành filter.

**DN escaping khác filter escaping.** Nếu cần lookup entry theo DN, xây DN với `LdapNameBuilder`, không dùng `EqualsFilter` để ghép RDN. Ngược lại, đừng nhúng DN chưa escape vào một chuỗi filter thô.

## 11. Kết quả đúng còn phụ thuộc base, scope, schema và quyền

Ngay cả một biểu thức logic đúng cũng có thể trả kết quả rỗng hoặc không đầy đủ. Trước khi nghi ngờ AND/OR/NOT, cần kiểm tra:

| Yếu tố | Ảnh hưởng | Cách kiểm tra |
|---|---|---|
| **Base DN** | Chỉ tìm trong vùng directory đã chọn | Đối chiếu `spring.ldap.base`, `@Entry(base=...)` và DN thực |
| **Search scope** | `ONELEVEL` khác `SUBTREE`; entry ở OU con có thể bị bỏ qua | Chạy test từng scope trên cây xác định |
| **objectClass** | Chỉ những entry thuộc loại phù hợp được chọn | Kiểm tra `@Entry` và schema thực của entry |
| **Tên thuộc tính** | `surname` của Java ánh xạ sang `sn` của LDAP | Kiểm tra `@Attribute`/metadata |
| **Matching rule** | Equality và substring có ngữ nghĩa theo syntax/schema | Thử với giá trị hoa/thường, dấu và ký tự đặc biệt |
| **Thuộc tính đa trị/thiếu** | Điều kiện equality hoặc phủ định có thể khớp ngoài dự kiến | Test có/không có attribute và nhiều giá trị |
| **ACL** | Tài khoản bind có thể bị hạn chế đọc entry/attribute | Thử bằng đúng service account đang dùng |
| **Giới hạn server** | Size/time limit, paging làm kết quả bị cắt | Đối chiếu mã lỗi, số entry, paging và access log |

Không nên tự cho rằng NOT trả ra “tất cả người dùng còn lại trong hệ thống”: nó chỉ được áp dụng trên **vùng tìm kiếm hiện tại**, loại entry phù hợp và dữ liệu mà directory cho phép xét.

Ví dụ `(!(sn=Nguyen))` khi search base là `ou=people` không thể tự tìm thấy entry ở `ou=contractors` nếu nhánh này nằm ngoài phạm vi. Nếu chuyển user giữa các OU, DN thay đổi; ứng dụng phải xem lại base/scope và chính sách định danh thay vì thay đổi bộ lọc một cách ngẫu nhiên.

## 12. Hiệu năng của điều kiện kết hợp

Về mặt logic, biểu thức AND thường thu hẹp tập kết quả, còn OR có thể mở rộng tập kết quả. Nhưng thời gian thực tế phụ thuộc vào **index của thuộc tính**, search base, schema, số entry, kích thước giá trị đa trị, kế hoạch thực thi và khả năng tối ưu của LDAP server.

| Loại filter | Điều cần đo hoặc cân nhắc |
|---|---|
| AND với thuộc tính chọn lọc | Có index phù hợp cho `uid`, `sn` hay `mail` không? |
| OR nhiều nhánh | Bao nhiêu nhánh, có phải quét nhiều entry hoặc trả nhiều kết quả không? |
| NOT hoặc NOT trên vùng rộng | Kết quả có quá lớn không? Có nên thêm điều kiện dương `objectClass`/OU không? |
| Presence `(mail=*)` | Thuộc tính này xuất hiện ở bao nhiêu entry? |
| Filter đa trị | Có chi phí xử lý lớn, limit trả về hoặc hành vi server-specific không? |

Không áp đặt quy tắc “AND luôn nhanh hơn OR” cho mọi LDAP server. Hãy đo **p95/p99 độ trễ**, số LDAP search thực tế, số entry trả về, tỷ lệ lỗi và hiệu năng ở cùng dữ liệu/khối lượng tải. Khi dùng repository, một lời gọi method là một thao tác Java logic; nếu có phân trang, referral hoặc retry, số thao tác LDAP protocol có thể khác.

Để đọc dữ liệu nhạy cảm và đảm bảo hiệu năng đúng điều kiện vận hành, dùng **LDAPS/StartTLS có xác thực chứng chỉ**, bind account quyền tối thiểu, timeout hợp lý và log đã ẩn thông tin cá nhân. Không tắt TLS hoặc cho quyền quản trị LDAP để benchmark “dễ chạy”.

## 13. Kiểm thử AND, OR, NOT với directory

Đọc tên method và kiểm tra filter bằng mắt chưa đủ. Nên chạy kiểm thử tích hợp trên **LDAP directory** có schema và matching rule giống môi trường đích; có thể dùng embedded/test directory khi phù hợp. Ít nhất cần bộ dữ liệu chứa một số entry thỏa cả hai điều kiện, chỉ một điều kiện, không điều kiện nào và thiếu thuộc tính tùy chọn.

| Ca thử | Filter / phương thức | Kết quả kỳ vọng trên bộ dữ liệu mẫu |
|---|---|---|
| AND cơ bản | `(&(sn=Nguyen)(givenName=An))` | `u1001` |
| OR cơ bản | `(|(sn=Nguyen)(givenName=An))` | `u1001, u1002, u1003, u1005` |
| NOT trên `sn` bắt buộc | `(!(sn=Nguyen))` | `u1003, u1004, u1005` |
| AND NOT | `(&(sn=Nguyen)(!(givenName=An)))` | `u1002` |
| OR rồi AND NOT | `(&(|(sn=Nguyen)(givenName=An))(!(mail=blocked@example.org)))` | `u1001, u1002, u1005` trong giả định thông thường |
| Bắt buộc có mail | `(&(|(sn=Nguyen)(givenName=An))(mail=*)(!(mail=blocked@example.org)))` | `u1001, u1002` |
| Phủ định cả AND | `(!(&(sn=Nguyen)(givenName=An)))` | Mọi entry mẫu ngoại trừ `u1001` |
| Input có ký tự đặc biệt | Repository parameter hoặc `EqualsFilter` với giá trị chứa `*`, `)`, `\` | Không làm biến đổi cây cú pháp filter; không phát sinh LDAP injection |
| Khác OU/base | Di chuyển entry ra ngoài `ou=people` | Kết quả thay đổi theo phạm vi tìm kiếm đúng thiết kế |
| Hạn chế quyền | Tài khoản chỉ đọc có ACL giới hạn | Xử lý khác biệt quyền và dữ liệu đúng chính sách |

**Kiểm tra khác biệt parser:** nếu viết một derived method kết hợp cả `And`, `Or` và `Not`, hãy chạy ca thử phân biệt được `(A OR B) AND NOT C` và `A OR (B AND NOT C)`. Nếu kết quả không đúng ý đồ, đổi sang filter được nhóm tường minh bằng `LdapTemplate`. Tránh tạo kiểm thử chỉ có các entry khiến cả hai biểu thức ngẫu nhiên trả cùng danh sách.

Khi kiểm thử, không chỉ `assert` số lượng; hãy đối chiếu danh sách DN/UID cụ thể. Nếu có thể, kiểm tra filter/operation tại LDAP server để xác minh thực sự truy vấn đúng base, loại entry và toán tử. **Không dùng dữ liệu người dùng thật** trong bộ test ví dụ.

## 14. Bài tập vận dụng

Giả sử tổ chức yêu cầu tìm những tài khoản ở `ou=people` thỏa mãn:

> (Họ `Nguyen` **hoặc** tên `An`), **không có** email `blocked@example.org`, và **bắt buộc có** thuộc tính `mail`.

Hãy trả lời:

1. LDAP filter đầy đủ có dấu ngoặc nhóm như thế nào?
2. Với tập dữ liệu `u1001` đến `u1005`, những entry nào phải được trả về?
3. Vì sao `findBySurnameOrGivenNameAndEmailNot(...)` có thể diễn tả một biểu thức khác yêu cầu?
4. Khi nào nên dùng `LdapRepository` derived method, khi nào nên chọn `LdapTemplate` và `AndFilter`/`OrFilter`/`NotFilter`?
5. Điều gì xảy ra nếu ứng dụng tìm ở `ou=contractors` thay vì `ou=people`, dù filter vẫn đúng?
6. Làm thế nào để kiểm tra input có ký tự `*` hoặc `)` không thay đổi cấu trúc filter?

**Đáp án tham khảo:**

```ldap
(&(|(sn=Nguyen)(givenName=An))(mail=*)(!(mail=blocked@example.org)))
```

Kết quả dự kiến là `u1001` và `u1002`. `u1003` bị loại vì email chặn; `u1005` không có email; `u1004` không thỏa nhóm OR. Filter phải áp dụng trên đúng search base và schema. Dùng filter builder giúp biểu diễn nhóm logic tường minh và escape giá trị do người dùng nhập.

## 15. Ghi nhớ

- **AND**: `(&(A)(B))`; **OR**: `(|(A)(B))`; **NOT**: `(!(A))`. Các ví dụ `A` và `B` ở đây là **filter con**, không phải chữ cái thay thế literal gửi tới LDAP.
- Với `LdapRepository`, có thể suy diễn những truy vấn logic đơn giản từ tên method như `findBySurnameAndGivenName`, `findBySurnameOrGivenName`, `findBySurnameNot` khi phiên bản thư viện hỗ trợ.
- Khi cần `(A OR B) AND NOT C`, biểu diễn **nhóm ngoặc rõ ràng** bằng `AndFilter`, `OrFilter`, `NotFilter` trên `LdapTemplate` thay vì suy đoán ưu tiên toán tử.
- **Phủ định trên thuộc tính tùy chọn** cần chú ý entry không có thuộc tính; thêm `(mail=*)` nếu yêu cầu kết quả nhất thiết có email.
- Filter hoạt động trong phạm vi **DN/base/scope**, schema, `objectClass` và ACL của LDAP. Dùng filter builder để escape input; không ghép raw filter từ chuỗi bên ngoài.
- Kiểm thử trên directory thật hoặc directory test, có các trường hợp khớp cả hai, khớp một, không khớp, thiếu thuộc tính, input đặc biệt và lỗi quyền truy cập.

**Kết luận:** nắm vững AND, OR và phủ định giúp viết **truy vấn repository Spring Data LDAP** đúng nghiệp vụ, đồng thời biết lúc nào nên dùng `LdapTemplate` để giữ nguyên ý nghĩa của nhóm điều kiện, an toàn với đầu vào và có kết quả kiểm chứng được.
