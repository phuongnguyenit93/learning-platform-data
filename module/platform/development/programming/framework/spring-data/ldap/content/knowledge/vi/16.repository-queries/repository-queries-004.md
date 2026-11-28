# Các từ khóa hiện diện, so khớp chuỗi và so sánh được hỗ trợ trong Spring Data LDAP Repository

Khi sử dụng **Spring Data LDAP**, ta có thể khai báo phương thức trên interface repository thay vì tự viết mọi LDAP search filter. Spring Data đọc tên phương thức, phân tích **tên property Java** và **từ khóa truy vấn** rồi chuyển tiêu chí phù hợp thành điều kiện tìm kiếm trên directory. Cơ chế này gọi là *derived query method*.

Bài học tập trung vào ba nhóm quan trọng khi viết truy vấn repository: kiểm tra **thuộc tính hiện diện/vắng mặt**; tìm **bằng, phủ định, tiền tố, hậu tố và chuỗi con**; và so sánh **nhỏ hơn hoặc bằng/lớn hơn hoặc bằng**. Đặc biệt, **không phải mọi keyword của Spring Data Commons đều được Spring Data LDAP hỗ trợ**: LDAP có cú pháp filter, schema và matching rule riêng, khác cơ sở dữ liệu quan hệ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Viết đúng tên phương thức `findBy...` theo **property Java** được ánh xạ bằng `@Attribute`.
- Dùng `IsNull`/`IsNotNull` để kiểm tra thuộc tính LDAP không có hoặc có mặt.
- Dùng `StartingWith`, `EndingWith`, `Containing` và `Like` đúng mục đích, không nhầm với SQL `LIKE` hoặc regex.
- Hiểu các keyword so sánh `LessThanEqual`/`GreaterThanEqual` và điều kiện schema/matching rule để chúng có ý nghĩa.
- Phân biệt bảng keyword **LDAP-specific** với bảng **generic** ở phụ lục Spring Data Commons.
- Kết hợp `And`/`Or`, đánh giá độ rộng truy vấn, dùng `@Query` hoặc `LdapTemplate` khi derived method không phù hợp.
- Thiết kế test với directory thực tế để kiểm tra kết quả, escaping và các hạn chế của schema.

## 2. Ngữ cảnh: entity và repository

Giả sử directory có các entry `inetOrgPerson` dưới `ou=people,dc=example,dc=com`, ví dụ:

```ldif
dn: uid=alice,ou=people,dc=example,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.com

dn: uid=bob,ou=people,dc=example,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: bob
cn: Bob Tran
sn: Tran
```

Bob **không có thuộc tính `mail`**. Điều này giúp minh họa khác biệt giữa thuộc tính **vắng mặt** và thuộc tính có giá trị.

Spring LDAP ODM ánh xạ entry sang Java:

```java
package com.example.directory;

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
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    protected DirectoryPerson() {
        // Dành cho cơ chế ánh xạ ODM.
    }

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getCommonName() { return commonName; }
    public String getSurname() { return surname; }
    public String getEmail() { return email; }

    // Getter/setter, constructor khác tùy nghiệp vụ.
}
```

Giả sử `spring.ldap.base=dc=example,dc=com`, metadata `@Entry(base="ou=people")` đặt entry của entity dưới nhánh `ou=people` tương đối với context. Các thuộc tính `cn`, `sn`, `uid`, `mail` đều phải được schema LDAP cho phép; `objectClass` cùng các lớp cha quyết định tính hợp lệ và quyền truy cập còn phụ thuộc server.

Repository cơ sở:

```java
package com.example.directory;

import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
```

**Lưu ý:** `LdapRepository` cho ODM LDAP nhận **một** tham số kiểu entity và sử dụng `javax.naming.Name` làm ID. Không khai báo `LdapRepository<DirectoryPerson, Long>` như ví dụ chung của datastore khác.

## 3. Spring phân tích tên phương thức ra sao?

Ví dụ:

```java
List<DirectoryPerson> findByCommonNameStartingWith(String prefix);
```

Spring hiểu:

1. `find...By` cho biết đây là một phương thức truy vấn.
2. `CommonName` là property Java `commonName` của `DirectoryPerson`.
3. `StartingWith` là keyword yêu cầu tìm giá trị bắt đầu bằng một đoạn.
4. `prefix` là **tham số dữ liệu**, không phải tên thuộc tính hoặc một đoạn LDAP filter.
5. ODM ánh xạ property `commonName` thành thuộc tính LDAP `cn`.

Ý nghĩa filter có thể hình dung là `(cn=Ali*)` khi gọi với `"Ali"`. Đây là biểu thức **minh họa**: query thực thi có thể bao gồm điều kiện `objectClass`/base và các phần khác do framework gắn vào. Không nên so khớp nguyên chuỗi filter trong unit test nếu chưa cố định phiên bản và cấu hình repository.

**Quan trọng:** phương thức có tên `findByCnStartingWith` sẽ chỉ hợp lý khi entity **thật sự có property `cn`**. Với entity ở trên, tên property là `commonName`, còn `cn` là tên attribute phía LDAP. Spring Data parse tên phương thức theo **mô hình Java**, không tự dùng tên LDAP attribute làm Java property.

## 4. Bảng keyword được mô tả cho Spring Data LDAP

Tài liệu *Spring Data LDAP — Query Methods* liệt kê các nhóm keyword LDAP-specific sau. Bảng diễn đạt dưới đây dùng property `commonName`/`email` từ entity mẫu và thuộc tính ví dụ giả định cho nhóm so sánh:

| Nhóm | Từ khóa | Phương thức ví dụ | Ý nghĩa LDAP |
| --- | --- | --- | --- |
| So sánh bằng | Không thêm keyword (`Is`/`Equals` nên kiểm tra theo phiên bản) | `findByUid(String uid)` | `(uid=alice)` |
| Phủ định giá trị | `Not` | `findBySurnameNot(String sn)` | `(!(sn=Tran))` |
| Có thuộc tính | `IsNotNull`, `NotNull` | `findByEmailIsNotNull()` | `(mail=*)` |
| Không có thuộc tính | `IsNull`, `Null` | `findByEmailIsNull()` | `(!(mail=*))` |
| Mẫu chuỗi | `Like` | `findByCommonNameLike(String pattern)` | Khớp mẫu LDAP do phương thức/phiên bản tạo. |
| Phủ định mẫu | `NotLike`, `IsNotLike` | `findByCommonNameNotLike(String pattern)` | Phủ định điều kiện mẫu. |
| Tiền tố | `StartingWith` | `findByCommonNameStartingWith(String prefix)` | `(cn=Ali*)` |
| Hậu tố | `EndingWith` | `findByCommonNameEndingWith(String suffix)` | `(cn=*Nguyen)` |
| Chứa chuỗi con | `Containing` | `findByCommonNameContaining(String fragment)` | `(cn=*lice*)` |
| Nhỏ hơn/bằng | `LessThanEqual` | `findByRankCodeLessThanEqual(String value)` | `(rankCode<=...)` nếu schema hỗ trợ ordering. |
| Lớn hơn/bằng | `GreaterThanEqual` | `findByRankCodeGreaterThanEqual(String value)` | `(rankCode>=...)` nếu schema hỗ trợ ordering. |

**Lưu ý quan trọng về ví dụ so sánh:** `rankCode` chỉ là **thuộc tính mở rộng giả định** có quy tắc so khớp thứ tự; nó **không có** trong entity `DirectoryPerson` ở mục 2 và không phải thuộc tính LDAP chuẩn mặc định. Hai phương thức ở hàng cuối chỉ có thể dùng sau khi directory định nghĩa attribute type/ordering rule tương ứng và entity ánh xạ property đó. Không sao chép hai phương thức vào repository mẫu rồi kỳ vọng ứng dụng biên dịch/chạy ngay.

Tài liệu LDAP-specific cũng mô tả việc kết hợp điều kiện theo `And` và `Or`. Ngược lại, phụ lục **Repository query keywords** chung của Spring Data liệt kê rất nhiều từ như `Between`, `In`, `Regex`, `Near`, `GreaterThan`, `LessThan`. Danh sách chung đó **không phải lời cam kết** rằng LDAP hỗ trợ tất cả. Với Spring Data LDAP, cần ưu tiên tài liệu LDAP-specific và kiểm tra hành vi ở phiên bản dự án đang sử dụng.

### 4.1. Vì sao ví dụ trong bảng tài liệu đôi lúc khó đọc?

Một số hàng trong tài liệu tham khảo LDAP dùng tên placeholder như `Firstname`, còn tên phương thức minh họa không luôn khớp chính xác giữa các hàng (chẳng hạn ví dụ `EndingWith`/`Containing` ghi cùng tên `Like`). Khi áp dụng vào ứng dụng, hãy dùng **keyword** đúng nghĩa và **property thật của entity**, như `findByCommonNameEndingWith` và `findByCommonNameContaining`. Không sao chép một tên phương thức có vẻ bị nhầm trong bảng nếu trái với mục đích truy vấn.

## 5. Kiểm tra sự hiện diện: `IsNull` và `IsNotNull`

LDAP dùng **presence filter** để kiểm tra entry có thuộc tính:

```ldap
(mail=*)
```

Phủ định của presence filter thể hiện thuộc tính **không xuất hiện** trên entry:

```ldap
(!(mail=*))
```

Khai báo trên repository:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByEmailIsNotNull();
    List<DirectoryPerson> findByEmailIsNull();

    // Tên rút gọn tương đương theo danh sách keyword:
    List<DirectoryPerson> findByEmailNotNull();
    List<DirectoryPerson> findByEmailNull();
}
```

Với dữ liệu mẫu:

- `findByEmailIsNotNull()` có thể trả Alice vì Alice có `mail`.
- `findByEmailIsNull()` có thể trả Bob vì Bob không có `mail`.

**Không nhầm LDAP `IsNull` với phép so sánh một giá trị `null` được lưu trên server.** Trong mô hình LDAP, một thuộc tính thường **vắng mặt** chứ không phải có một giá trị Java `null`. Việc ánh xạ ODM đọc thiếu `mail` thành `null` ở Java là hệ quả của trạng thái entry, không phải định nghĩa filter so sánh với chuỗi chữ `"null"`.

### Presence không đồng nghĩa kiểm tra giá trị rỗng

`(mail=*)` có nghĩa thuộc tính hiện diện; nó **không** kiểm tra email có định dạng hợp lệ, có thể gửi thư hay có giá trị khác dấu cách. Việc server có cho phép giá trị chuỗi rỗng hay không còn phụ thuộc schema và provider. Nếu form yêu cầu email hợp lệ, cần validation nghiệp vụ riêng.

Tương tự, kết quả tìm kiếm còn phụ thuộc quyền đọc và chính sách directory. Không sử dụng presence filter thay thế cho quyết định có cho người gọi xem email hay không.

## 6. So sánh bằng và phủ định

So sánh chính xác theo giá trị thuộc tính:

```java
List<DirectoryPerson> findByUid(String uid);
List<DirectoryPerson> findBySurname(String surname);
List<DirectoryPerson> findBySurnameNot(String surname);
```

Ví dụ với `findByUid("alice")`, về mặt logic điều kiện là `(uid=alice)`. Với `findBySurnameNot("Tran")`, logic là `(!(sn=Tran))`.

**Phủ định** cần hiểu cẩn thận: trong LDAP, bộ lọc `(!(sn=Tran))` không nhất thiết tương đương với `(sn=*)` AND `sn != Tran` theo trực giác từ SQL. Cách LDAP kết hợp phủ định, matching rule và trường vắng mặt có thể làm tập kết quả khác kỳ vọng. Với `inetOrgPerson`, `sn` thường bắt buộc do thừa kế từ `person`, nhưng ở thuộc tính tùy chọn thì phải xác định rõ có muốn tính những entry thiếu thuộc tính hay không.

Nếu chỉ muốn các entry có `mail` và không bằng một giá trị nhất định, nên yêu cầu **cả presence và phủ định** ở mức filter thay vì chỉ dựa vào `Not`:

```ldap
(&(mail=*)(!(mail=blocked@example.com)))
```

Đoạn trên chỉ là filter minh họa; khi giá trị email đến từ request, phải để framework encode tham số, không nối trực tiếp dữ liệu ngoài vào filter dạng chuỗi.

## 7. Tìm kiếm chuỗi: `StartingWith`, `EndingWith` và `Containing`

Với property Java `commonName` ánh xạ LDAP `cn`:

```java
List<DirectoryPerson> findByCommonNameStartingWith(String prefix);
List<DirectoryPerson> findByCommonNameEndingWith(String suffix);
List<DirectoryPerson> findByCommonNameContaining(String fragment);
```

Với các giá trị ví dụ, ý nghĩa filter tương ứng:

| Lời gọi | Ý nghĩa filter | Ví dụ giá trị có thể khớp |
| --- | --- | --- |
| `findByCommonNameStartingWith("Ali")` | `(cn=Ali*)` | `Alice Nguyen`, `Alicia Tran` |
| `findByCommonNameEndingWith("Nguyen")` | `(cn=*Nguyen)` | `Alice Nguyen` |
| `findByCommonNameContaining("lic")` | `(cn=*lic*)` | `Alice Nguyen` |

Các mẫu trên thể hiện **substring search**, không phải SQL `LIKE` hoặc Java regex. Dấu `*` trong LDAP substring filter có nghĩa là đoạn ký tự bất kỳ; ký tự `%` hay `_` không có ngữ nghĩa wildcard giống SQL `LIKE`.

Kết quả **không nhất thiết** tuân theo so sánh của `String.startsWith`/`String.endsWith`/`String.contains` ở Java: LDAP dựa trên **matching rule** trong schema của thuộc tính và cách máy chủ áp dụng chuẩn hóa chữ hoa/thường, Unicode và dấu.

### 7.1. Kết hợp điều kiện bằng `And` và `Or`

Ví dụ người dùng có họ `Nguyen` và `cn` chứa `Ali`:

```java
List<DirectoryPerson> findBySurnameAndCommonNameContaining(
        String surname, String fragment);
```

Ý nghĩa filter:

```ldap
(&(sn=Nguyen)(cn=*Ali*))
```

Ví dụ khác — hoặc họ `Nguyen`, hoặc tên bắt đầu bằng `Ali`:

```java
List<DirectoryPerson> findBySurnameOrCommonNameStartingWith(
        String surname, String prefix);
```

Ý nghĩa logic:

```ldap
(|(sn=Nguyen)(cn=Ali*))
```

Khi phối hợp nhiều `And` và `Or`, hãy viết tên phương thức sao cho cấu trúc logic rõ ràng và kiểm tra query thực tế. Nếu biểu thức phức tạp, dùng `@Query` hoặc `LdapTemplate` có filter builder để chủ động đặt dấu ngoặc/nhóm điều kiện.

### 7.2. Từ khóa `Like` có gì khác?

Spring Data LDAP liệt kê `Like` (và `NotLike`/`IsNotLike`). `Like` không đồng nghĩa rằng repository sẽ xử lý mọi cú pháp pattern của SQL:

```java
List<DirectoryPerson> findByCommonNameLike(String pattern);
List<DirectoryPerson> findByCommonNameNotLike(String pattern);
```

Đọc `Like` là **truy vấn theo mẫu LDAP** có hành vi phụ thuộc cách framework chuyển đổi tham số ở phiên bản đang dùng, không phải một hàm regex hay dấu `%` của SQL. Tài liệu LDAP-specific minh họa `Like` với cú pháp gần phép so sánh bằng, trong khi `StartingWith`/`EndingWith`/`Containing` mô tả rõ vị trí wildcard. Vì vậy, **ưu tiên ba keyword rõ ý nghĩa** khi chỉ cần tiền tố, hậu tố hoặc chứa chuỗi con.

Không truyền thẳng một pattern do client tự tạo (chứa các dấu `*`/`(`/`)` tùy ý) vào `Like` rồi giả định không có rủi ro. Mỗi loại query phải có **hợp đồng input**: nếu người dùng chỉ được nhập literal, ứng dụng cần chọn API dựng filter và escape thích hợp; nếu người dùng được phép chọn chế độ tìm, client nên gửi một enum kiểu tìm thay vì nguyên LDAP filter.

### 7.3. Nhớ rằng wildcard và literal `*` là khác nhau

```text
(cn=Ali*)      tìm tiền tố Ali
(cn=*lic*)     tìm chuỗi con lic
(cn=*)         kiểm tra cn hiện diện
(cn=\2a)       tìm giá trị cn chứa đúng ký tự * (equality)
```

Giá trị `\2a` là dạng escape của ký tự `*` theo cú pháp LDAP filter (RFC 4515 và diễn giải RFC 2254 trong tài liệu Spring). Nếu ứng dụng đang xây **giá trị equality**, dấu `*` do người dùng gửi phải được coi là literal, không làm biến truy vấn thành presence filter. Các biểu thức `@Query` và SpEL có quy tắc encode riêng; xem mục 10.

## 8. So sánh thứ tự: `LessThanEqual` và `GreaterThanEqual`

LDAP hỗ trợ phép so sánh **nhỏ hơn hoặc bằng** và **lớn hơn hoặc bằng** trong filter, thường được biểu diễn như sau:

```ldap
(rankCode<=100)
(rankCode>=100)
```

Đây là **ví dụ cú pháp trên một thuộc tính giả định**; không được hiểu `rankCode` có sẵn trong schema chuẩn hoặc mọi directory hỗ trợ so sánh số. Spring Data LDAP liệt kê các keyword:

- `LessThanEqual`: yêu cầu so sánh theo quan hệ nhỏ hơn hoặc bằng.
- `GreaterThanEqual`: yêu cầu so sánh theo quan hệ lớn hơn hoặc bằng.

Ví dụ trong một hệ thống đã mở rộng schema có attribute type `rankCode` và **ordering matching rule** phù hợp:

```java
// Chỉ dùng khi DirectoryPerson đã ánh xạ field rankCode,
// objectClass/schema cho phép thuộc tính và hỗ trợ ordering rule.
List<DirectoryPerson> findByRankCodeLessThanEqual(String boundary);
List<DirectoryPerson> findByRankCodeGreaterThanEqual(String boundary);
```

Để các ví dụ này thực sự hoạt động, cần kiểm tra **đủ bốn điều kiện**:

1. Directory định nghĩa attribute type `rankCode` với syntax và **ORDERING matching rule** phù hợp; chẳng hạn thứ tự số hoặc từ điển tùy thiết kế.
2. `objectClass` có hiệu lực cho phép lưu `rankCode` trong entry.
3. Entity Java khai báo property và `@Attribute(name = "rankCode")` tương ứng.
4. Server có dữ liệu và ACL cho phép truy vấn, với giá trị tham số phù hợp cú pháp ordering rule.

Nếu không có ordering matching rule, máy chủ có thể từ chối hoặc trả kết quả không mong đợi tùy khả năng và chính sách server. **Không** suy ra so sánh số từ việc Java truyền `Integer`, và không mặc định so sánh `String` theo `String.compareTo` của JVM.

### 8.1. Vì sao không liệt kê `LessThan` và `GreaterThan` như keyword LDAP mặc định?

Bộ lọc LDAP cơ bản định nghĩa toán tử `<=` và `>=`; tài liệu keyword LDAP-specific liệt kê `LessThanEqual`/`GreaterThanEqual`, không cam kết `LessThan`/`GreaterThan` nghiêm ngặt ở đây. Mặc dù phụ lục Spring Data Commons có `LessThan`, `GreaterThan`, `Between`, điều đó không chứng minh chúng hoạt động trong Spring Data LDAP.

Nếu nghiệp vụ cần **nhỏ hơn nghiêm ngặt**, có thể phân tích kết hợp phủ định và so sánh bao hàm trên thuộc tính có ordering rule, nhưng phải rất cẩn thận với entry thiếu thuộc tính, matching rule và semantics của LDAP. Không tự tạo phương thức `findByRankCodeLessThan` chỉ vì Spring Data JPA hỗ trợ nó.

## 9. Interface repository hoàn chỉnh cho những keyword phổ biến

Sau khi đã hiểu ý nghĩa từng nhóm, có thể tổ chức các truy vấn trực tiếp trong repository:

```java
package com.example.directory;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    // Equality và phủ định:
    List<DirectoryPerson> findByUid(String uid);
    List<DirectoryPerson> findBySurnameNot(String surname);

    // Kiểm tra sự hiện diện:
    List<DirectoryPerson> findByEmailIsNotNull();
    List<DirectoryPerson> findByEmailIsNull();

    // Các kiểu substring:
    List<DirectoryPerson> findByCommonNameStartingWith(String prefix);
    List<DirectoryPerson> findByCommonNameEndingWith(String suffix);
    List<DirectoryPerson> findByCommonNameContaining(String fragment);

    // AND và OR:
    List<DirectoryPerson> findBySurnameAndCommonNameContaining(
            String surname, String fragment);
    List<DirectoryPerson> findBySurnameOrCommonNameStartingWith(
            String surname, String prefix);
}
```

Không thêm hai phương thức `rankCode` so sánh thứ tự vào interface này vì entity ví dụ **chưa có** thuộc tính tương ứng. `@Entry` xác định các object class và base của entity; phương thức repository định nghĩa các tiêu chí trên **property Java**, không cần khai báo LDAP filter dưới dạng chuỗi cho các trường hợp thông thường.

### 9.1. Gọi từ tầng service

```java
package com.example.directory;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PeopleQueryService {
    private final DirectoryPersonRepository repository;

    public PeopleQueryService(DirectoryPersonRepository repository) {
        this.repository = repository;
    }

    public List<DirectoryPerson> findByPrefix(String prefix) {
        if (prefix == null || prefix.isBlank() || prefix.length() > 60) {
            throw new IllegalArgumentException("Tiền tố không hợp lệ");
        }
        return repository.findByCommonNameStartingWith(prefix);
    }

    public List<DirectoryPerson> findWithoutEmail() {
        return repository.findByEmailIsNull();
    }

    public List<DirectoryPerson> findExactUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
        return repository.findByUid(uid);
    }
}
```

`uid` được kiểm tra theo quy tắc ASCII **minh họa** của ứng dụng; LDAP có thể hỗ trợ các giá trị khác. Validation không thay thế encoding của filter, cũng không cấp quyền đọc entry. Với tìm kiếm tiền tố trên directory lớn, có thể cần giới hạn độ dài tối thiểu và lượng kết quả theo nghiệp vụ.

## 10. Khi nào nên dùng `@Query` hoặc `LdapTemplate`?

Derived methods rất tiện cho điều kiện ngắn. Nếu muốn diễn đạt một filter có cấu trúc đặc biệt, cần trộn presence với phủ định, hoặc cần kiểm soát rõ base/scope/thuộc tính trả về, cân nhắc hai lựa chọn sau.

### 10.1. `@Query` cho filter do ứng dụng định nghĩa

Ví dụ tìm người dùng có email nhưng không phải địa chỉ được chặn:

```java
package com.example.directory;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    @Query("(&(mail=*)(!(mail=:blockedAddress)))")
    List<DirectoryPerson> findHasOtherEmail(
            @Param("blockedAddress") String blockedAddress);
}
```

**Đây là interface minh họa riêng**, không thêm một interface trùng tên vào dự án thật; hãy đưa method mới vào interface repository đang có.

Với `@Query`, tài liệu Spring Data LDAP mô tả các tham số của string query được encode theo quy tắc LDAP filter (tài liệu nêu RFC 2254). Vì thế nên dùng placeholder `:blockedAddress` hoặc `?0` thay vì nối string input vào filter. Cú pháp filter, tên attribute và toán tử đều do **code tin cậy** xác định.

**Cảnh báo quan trọng:** tài liệu còn nêu rằng giá trị được đưa vào filter bằng **SpEL expressions** hoặc **property placeholders** không được tự escape theo cơ chế đó. Đừng dùng SpEL cho input chưa kiểm tra trong một filter rồi giả định framework bảo vệ; phải encode giá trị theo đúng ngữ cảnh bằng cơ chế phù hợp, và không cung cấp cả filter/attribute name từ client.

Nếu cần custom encoding cho tham số `@Query`, Spring Data LDAP có cơ chế `@LdapEncode` nhưng chỉ áp dụng cho các **tham số** của query method tương ứng, không áp dụng tự động cho mọi derived query hoặc value expression. Chỉ tùy biến khi thực sự hiểu yêu cầu encoding và version đang dùng.

### 10.2. `LdapTemplate` khi cần điều chỉnh cách search

`LdapTemplate` của Spring LDAP giúp chọn base, scope, thuộc tính trả về và filter builder rõ ràng:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery ldapQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid", "cn")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("alice");

List<String> ids = ldapTemplate.search(
        ldapQuery,
        (AttributesMapper<String>) attrs ->
                attrs.get("uid").get().toString()
);
```

Ở đây `ldapTemplate` là bean `LdapTemplate` được inject vào class đang chứa phương thức, còn đoạn code minh họa phần thân của một thao tác tìm kiếm. `.is(...)` giúp truyền **giá trị** theo đúng cơ chế filter thay vì nối chuỗi raw. Với base `dc=example,dc=com` đã cấu hình, `base("ou=people")` là tên tương đối với `ContextSource`.

Một repository ODM tải entity Java; `LdapTemplate` còn có thể trả DTO gọn chỉ lấy `uid`/`cn`. Hãy chọn theo nhu cầu: derived query cho CRUD/domain, `LdapTemplate` cho read path cần kiểm soát chặt filter, scope và projection.

## 11. Đặc điểm quan trọng của LDAP khi so với JPA

| Nội dung | Spring Data LDAP | Không nên giả định theo JPA |
| --- | --- | --- |
| Định danh | Entry có **DN**, thường ánh xạ `@Id Name dn`. | Không mặc định dùng `Long` khóa tự tăng. |
| Property query | Tên property Java được ánh xạ tới LDAP attribute. | Không có table/column SQL theo nghĩa JPA. |
| Presence | `(mail=*)` và phủ định cho thuộc tính vắng mặt. | Không có SQL `IS NULL` trên row/column. |
| Substring | `*` là wildcard trong LDAP filter. | Không dùng trực tiếp `%`, `_` của SQL `LIKE`. |
| Ordering | Cần LDAP attribute type có ordering matching rule. | Kiểu `int`/`String` trong Java không bảo đảm phép so sánh hợp lệ trên directory. |
| Paging/sorting | Spring LDAP repository không hỗ trợ paging/sorting theo cách Spring Data JPA. | Không mặc định truyền `Pageable`/`Sort` và kỳ vọng kết quả tương đương SQL. |
| Authorization | Server dùng LDAP ACL; có thể có các hạn chế/nhánh riêng. | Không phải mọi repository query đều được phép đọc mọi entry. |

Một keyword có thể được Spring Data parser nhận diện nhưng **không có nghĩa** LDAP backend thực thi thành công với mọi attribute. Ví dụ, keyword so sánh thứ tự hợp lệ ở mức API vẫn không thể tạo semantics đúng nếu directory thiếu ordering matching rule cho thuộc tính tương ứng.

## 12. Kiểm thử với directory: những trường hợp nên có

Một unit test gọi mock repository chỉ chứng minh service chọn đúng method. Để kiểm tra *derived query* thật, cần integration test với LDAP directory dành riêng cho test, có schema và fixture ổn định.

Chuẩn bị:

```text
ou=people,dc=example,dc=com
├── uid=alice    cn="Alice Nguyen"  sn="Nguyen"  mail="alice@example.com"
├── uid=alicia   cn="Alicia Tran"   sn="Tran"    mail không có
└── uid=bob      cn="Bob Alice"     sn="Alice"   mail không có
```

Gợi ý bảng kiểm thử:

| Method | Dữ liệu đầu vào | Kết quả theo fixture |
| --- | --- | --- |
| `findByEmailIsNotNull()` | Không có tham số | Alice. |
| `findByEmailIsNull()` | Không có tham số | Alicia và Bob. |
| `findByCommonNameStartingWith(...)` | `"Ali"` | Alice và Alicia. |
| `findByCommonNameEndingWith(...)` | `"Alice"` | Bob. |
| `findByCommonNameContaining(...)` | `"lic"` | Alice, Alicia và Bob (tùy matching rule). |
| `findBySurnameNot(...)` | `"Tran"` | Alice và Bob theo dữ liệu mẫu. |
| `findBySurnameAndCommonNameContaining(...)` | `"Nguyen"`, `"Ali"` | Alice. |

**Lưu ý về kết quả contains:** `"Alice"` chứa `lic`, `"Alicia"` cũng chứa `lic`, còn `"Bob Alice"` cũng chứa `lic`. So khớp case/Unicode cần dựa vào matching rule của `cn` trên server thực tế. So sánh kết quả bằng **tập DN/uid**, không giả định thứ tự trả về ổn định.

### Ví dụ integration test (Spring Boot + JUnit 5)

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DirectoryPersonRepositoryIT {
    @Autowired DirectoryPersonRepository repository;

    @Test
    void queryByPresenceAndPrefix() {
        Set<String> withEmail = repository.findByEmailIsNotNull()
                .stream()
                .map(DirectoryPerson::getUid)
                .collect(Collectors.toSet());
        assertEquals(Set.of("alice"), withEmail);

        Set<String> withPrefix = repository
                .findByCommonNameStartingWith("Ali")
                .stream()
                .map(DirectoryPerson::getUid)
                .collect(Collectors.toSet());
        assertEquals(Set.of("alice", "alicia"), withPrefix);
    }
}
```

Test trên giả định directory test chỉ có **ba entry người dùng theo fixture** và không có data ngoài cùng phạm vi. Nếu fixture tồn tại nhiều dữ liệu khác, cần lọc theo nhánh dành riêng cho test hoặc tạo tên duy nhất cho mỗi lần chạy và dọn sau test. Không dùng directory production để ghi dữ liệu thử hoặc chạy truy vấn nặng.

### Các edge cases cần bổ sung

1. **Thuộc tính vắng mặt:** kiểm tra `IsNull`/`IsNotNull` với `mail` vắng mặt thực sự, không gửi giá trị rỗng.
2. **Dấu sao literal:** truyền đầu vào có `*` và kiểm tra có bị biến thành wildcard ngoài chủ ý không.
3. **Dấu ngoặc/backslash:** thử ký tự `(`, `)`, `\` và Unicode trong input; xác minh cách encoding của phiên bản đang dùng.
4. **Property mapping:** đổi tên property Java/`@Attribute(name=...)` và xác nhận phương thức còn hợp lệ; không đánh đồng `commonName` với `cn`.
5. **Ordering rule:** dùng directory test có thuộc tính hỗ trợ ordering, kiểm tra hai keyword `LessThanEqual` và `GreaterThanEqual` ở ranh giới bằng và lớn/nhỏ hơn; không thử trên attribute thiếu rule.
6. **ACL và phạm vi:** tài khoản chỉ được đọc đúng nhánh; kiểm tra entry ngoài base không lọt vào kết quả.
7. **Độ rộng truy vấn:** kiểm tra từ khóa ngắn/contains có thể trả quá nhiều kết quả và ứng dụng có giới hạn phù hợp.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng khắc phục |
| --- | --- | --- |
| `findByCnContaining` không ánh xạ đúng. | Entity có property `commonName`, không có `cn`. | Đặt tên theo property Java: `findByCommonNameContaining`. |
| `findByEmailIsNull` được hiểu là so với chuỗi “null”. | Nhầm presence LDAP với SQL/Java null. | Hiểu nó là `(!(mail=*))`. |
| `findByCommonNameContaining` trả nhiều kết quả. | Substring wildcard có thể so khớp rộng. | Xác định độ dài tối thiểu, phạm vi, giới hạn kết quả, index và đo thực tế. |
| Tìm `Like` bằng pattern kiểu SQL `%Ali%`. | LDAP không dùng ký hiệu wildcard `%`. | Dùng `Containing` hoặc filter LDAP đúng cú pháp. |
| Dùng `GreaterThan` rồi gặp lỗi khi khởi tạo repository. | Dựa vào keyword chung chứ không phải LDAP-specific. | Ưu tiên `GreaterThanEqual` nếu được hỗ trợ, hoặc tự thiết kế query/logic theo khả năng LDAP. |
| `GreaterThanEqual` không trả kết quả như so sánh số. | Thiếu/sai ordering rule hoặc giá trị không tuân theo syntax. | Kiểm tra schema `attributeTypes`, index và giá trị thực tế. |
| `Not` trả cả entry không có thuộc tính. | Phủ định LDAP khác suy luận trên cột SQL. | Nếu cần thuộc tính tồn tại, kết hợp presence và phủ định. |
| Query `@Query`/SpEL có nguy cơ injection. | Giá trị được chèn mà chưa encode đúng. | Dùng parameter binding chuẩn, kiểm soát SpEL/property placeholders và escape theo filter. |
| Tính năng phân trang repository không hoạt động như JPA. | Hạn chế của Spring LDAP repository. | Thiết kế query và cơ chế LDAP paging cụ thể cho nhu cầu lớn, không mặc định `Pageable`. |

## 14. Bài thực hành

**Bài 1.** Entity khai báo `@Attribute(name="cn") String commonName`. Bạn muốn tìm tên chứa `"Anh"`. Hãy khai báo method repository.

**Đáp án:** `List<DirectoryPerson> findByCommonNameContaining(String fragment)`. Dùng property `commonName`, không phải tên LDAP `cn`.

**Bài 2.** Viết hai method phân biệt người dùng **có email** và **không có email**. LDAP filter logic tương ứng là gì?

**Đáp án:** `findByEmailIsNotNull()` → `(mail=*)`; `findByEmailIsNull()` → `(!(mail=*))`. Chúng kiểm tra sự hiện diện/vắng mặt của thuộc tính.

**Bài 3.** Định nghĩa ba method tìm `commonName` bắt đầu với, kết thúc bằng và chứa một đoạn chuỗi.

**Đáp án:** `findByCommonNameStartingWith(String prefix)`, `findByCommonNameEndingWith(String suffix)` và `findByCommonNameContaining(String fragment)`. Filter minh họa tương ứng `(cn=Ali*)`, `(cn=*Nguyen)`, `(cn=*lic*)`.

**Bài 4.** Vì sao `findByRankCodeGreaterThanEqual("100")` không thể bảo đảm so sánh đúng ngay khi Java biên dịch thành công?

**Đáp án:** `rankCode` phải là attribute type có trong schema và có **ordering matching rule** phù hợp, entity phải ánh xạ đúng, entry phải chứa dữ liệu phù hợp và tài khoản có quyền tìm. Biên dịch Java không kiểm tra mọi quy tắc LDAP.

**Bài 5.** Bạn thấy `Between`, `Regex` và `GreaterThan` trong phụ lục keyword chung. Có thể mặc định dùng cho LDAP không?

**Đáp án:** Không. Phụ lục chung không bảo đảm tính hỗ trợ ở mọi datastore. Phải dựa vào tài liệu LDAP-specific, kiểm tra phiên bản và xác minh bằng integration test.

**Bài 6.** Viết một điều kiện tìm những người dùng có `mail` nhưng không bằng `blocked@example.com` mà không cho client tự quyết định cấu trúc filter.

**Đáp án:** Dùng filter cố định `(&(mail=*)(!(mail=:blockedAddress)))` với `@Query` và named parameter để framework encode **giá trị**. Hoặc dùng `LdapTemplate` với filter builder `AndFilter`, `PresentFilter` và `NotFilter`/`EqualsFilter` phù hợp với phiên bản thực tế; không nối raw input vào filter.

## 15. Ghi nhớ

- Derived query trong Spring Data LDAP xây theo **tên property Java** được `@Attribute` ánh xạ, không theo tên field LDAP nếu hai tên khác nhau.
- `IsNotNull`/`NotNull` nghĩa là **có thuộc tính**; `IsNull`/`Null` nghĩa là **vắng thuộc tính**, tương ứng với presence filter và phủ định.
- `StartingWith`, `EndingWith`, `Containing` tạo điều kiện substring theo cú pháp LDAP; `Like`/`NotLike` cần được kiểm tra semantics và pattern cụ thể.
- `LessThanEqual` và `GreaterThanEqual` chỉ có ý nghĩa phù hợp khi **schema có ordering matching rule** cho attribute được so sánh.
- Không xem danh sách keyword **Spring Data Commons** là tập keyword LDAP đầy đủ; tránh suy diễn `Between`/`Regex`/`GreaterThan` được hỗ trợ.
- Sử dụng `@Query` hoặc `LdapTemplate` cho trường hợp phức tạp, luôn kiểm soát parameter encoding, base/scope, thuộc tính, ACL và tải truy vấn.
- Kiểm tra bằng **directory thử nghiệm** trước khi đưa chức năng vào production; test với thuộc tính thiếu, các wildcard, matching rule và kết quả theo tập DN.

## Tài liệu tham khảo

- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html): bảng keyword LDAP-specific, `@Query` và parameter encoding.
- [Spring Data LDAP — Repository query keywords](https://docs.spring.io/spring-data/ldap/reference/repositories/query-keywords-reference.html): danh sách chung, có cảnh báo cần đối chiếu với từng datastore.
- [Spring LDAP — Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html): `LdapRepository`, kiểu DN của ID và giới hạn paging/sorting.
- [Spring Data LDAP — Defining Query Methods](https://docs.spring.io/spring-data/ldap/reference/repositories/query-methods-details.html): nguyên tắc phân tích tên và cấu trúc method query.
