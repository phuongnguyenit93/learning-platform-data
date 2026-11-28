# Phân biệt wildcard được chủ ý dùng với dữ liệu đầu vào thông thường trong Repository Query

## 1. Vấn đề: cùng dấu `*`, hai ý nghĩa hoàn toàn khác nhau

Trong **Spring Data LDAP**, repository tạo truy vấn trên LDAP directory từ tên phương thức hoặc từ `@Query`; `LdapTemplate` cũng cho phép xây dựng filter bằng `LdapQueryBuilder`. Dữ liệu directory được lưu dưới dạng entry, có **DN** (Distinguished Name), `objectClass` và các thuộc tính theo schema như `uid`, `cn`, `sn`, `mail`. Tìm kiếm theo thuộc tính phải tuân thủ cú pháp filter LDAP, chứ không phải cú pháp `LIKE` của SQL.

Hãy xét hai yêu cầu:

1. Người dùng nhập **`A*B`** như một tên hiển thị và muốn tìm **chính xác** entry có `cn` bằng ba ký tự `A`, `*`, `B`.
2. Người dùng chọn chức năng **tìm tên bắt đầu bằng `A` và kết thúc bằng `B`**, nên ứng dụng **chủ ý** tạo filter có wildcard nằm giữa.

Cả hai có thể nhìn giống nhau nếu ai đó viết filter `(cn=A*B)`, nhưng chúng **không tương đương**. Trong filter LDAP:

- `*` không escape ở vị trí thích hợp mang ý nghĩa **wildcard** của substring filter.
- `\2a` biểu diễn ký tự `*` **theo nghĩa dữ liệu thông thường** trong một assertion value.

Do đó:

~~~text
(cn=A*B)       => chuỗi bắt đầu bằng A, kết thúc bằng B
(cn=A\2aB)     => giá trị chứa dấu * thật: A*B (equality assertion)
(cn=*\2a*)     => chuỗi chứa ký tự * thật ở một vị trí nào đó
(cn=*)         => thuộc tính cn hiện diện, KHÔNG phải cn chứa ký tự *
~~~

**Mục tiêu bài học:** tách rạch ròi **cú pháp truy vấn do ứng dụng kiểm soát** khỏi **giá trị dữ liệu người dùng**, chọn đúng API của Spring Data LDAP/Spring LDAP, hiểu khi nào `Like`, `Containing` và `@LdapEncode` cho phép wildcard, và viết kiểm thử ngăn LDAP injection.

> **Quy tắc nền tảng:** Ký tự `*` chỉ được giữ làm wildcard khi **nghiệp vụ cố ý cho phép vị trí đó là cú pháp tìm kiếm**. Ký tự `*` đi vào như một phần của **giá trị chưa tin cậy** phải được mã hóa như dữ liệu, trừ khi có một chính sách riêng cho phép pattern, được thực thi rõ ràng và kiểm thử.

## 2. Ôn tập cú pháp LDAP filter theo RFC 4515

Một số dạng filter thường dùng:

| Filter | Diễn giải |
| --- | --- |
| `(uid=alice)` | Equality: giá trị `uid` khớp `alice` theo matching rule của schema |
| `(cn=Alice*)` | Substring: `cn` bắt đầu bằng `Alice` |
| `(cn=*Nguyen)` | Substring: `cn` kết thúc bằng `Nguyen` |
| `(cn=*Ali*)` | Substring: `cn` chứa `Ali` |
| `(cn=A*B)` | Substring: bắt đầu `A`, kết thúc `B` |
| `(cn=*)` | Presence: thuộc tính `cn` hiện diện |
| `(cn=\2a)` | Equality với một dấu `*` **literal** |
| `(cn=*\2a*)` | Substring chứa dấu `*` **literal** |
| `(&(objectClass=inetOrgPerson)(uid=alice))` | AND: đúng lớp người dùng và đúng `uid` |
| `(|(uid=alice)(uid=bob))` | OR: `uid` khớp Alice hoặc Bob |
| `(!(mail=*))` | Không có thuộc tính `mail` trong ngữ nghĩa filter/ACL của server |

Dấu `*` trong LDAP không phải toán tử SQL `%`; LDAP filter không có ý nghĩa SQL `?` hay `_` làm wildcard mặc định. Các phép equality/substring thực tế phụ thuộc **equality matching rule / substring matching rule** của schema. Không tự giả định so khớp luôn phân biệt hoặc luôn không phân biệt hoa/thường.

### 2.1. Các ký tự bắt buộc escape trong giá trị filter

Theo RFC 4515, khi một ký tự đặc biệt xuất hiện dưới vai trò **dữ liệu** của assertion value, phải biểu diễn bằng dấu gạch chéo ngược rồi đến **hai chữ số hex**:

| Ký tự dữ liệu | Biểu diễn trong filter | Vì sao quan trọng? |
| --- | --- | --- |
| `*` | `\2a` | Không bị hiểu thành wildcard hoặc presence |
| `(` | `\28` | Không mở một thành phần filter |
| `)` | `\29` | Không kết thúc thành phần filter |
| `\` | `\5c` | Không bị hiểu là phần mở đầu escape sequence |
| NUL (`0x00`) | `\00` | Không phá chuỗi/cú pháp filter |

Ví dụ đầu vào `A*(B)` cần được đối xử như **một giá trị**. Trong filter equality, phần giá trị được mã hóa sẽ tương tự `A\2a\28B\29`; dấu ngoặc và dấu sao không còn cấu trúc điều khiển.

Cú pháp filter LDAP khác **escape DN**. Đối với DN lấy từ input, dùng `LdapName` hoặc `LdapNameBuilder`; đối với assertion value trong filter, dùng query builder/binder/filter encoder của Spring LDAP. Không dùng một cơ chế escape DN để thay cho escape LDAP filter.

### 2.2. Wildcard là cú pháp, không phải dữ liệu

Nếu một lập trình viên chủ ý xây dựng pattern:

~~~text
(cn=Al*)
~~~

thì dấu `*` ở cuối là **cú pháp truy vấn** do ứng dụng xác định. Nhưng khi API nhận `name = "Al*"`, nghiệp vụ tìm **chính xác** `Al*`, filter đúng phải tương đương:

~~~text
(cn=Al\2a)
~~~

Một trường tìm kiếm có nhãn “Tên chứa” nên đặt hai dấu sao **ngoài** dữ liệu đã encode:

~~~text
Ứng dụng cung cấp:  (cn=* [đầu vào đã encode] *)
Người dùng nhập:    Al*
Filter kết quả:     (cn=*Al\2a*)
~~~

Hai dấu `*` ngoài cùng là wildcard được cho phép; `\2a` giữa là dấu sao do người dùng nhập và được xử lý như dữ liệu. Đó là sự phân biệt trọng tâm của toàn bài.

## 3. Mô hình dữ liệu và repository ví dụ

Giả sử `LdapContextSource` của ứng dụng có base DN `dc=example,dc=org`, còn các entry người dùng nằm dưới `ou=people`. Ví dụ dữ liệu:

~~~text
uid=alice,ou=people,dc=example,dc=org
  cn: Alice Nguyen

uid=an,ou=people,dc=example,dc=org
  cn: An Tran

uid=literal-star,ou=people,dc=example,dc=org
  cn: A*B

uid=substring-test,ou=people,dc=example,dc=org
  cn: AxxB

uid=ops,ou=people,dc=example,dc=org
  cn: Ops (Test)
~~~

Định nghĩa entity Spring LDAP ODM:

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
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) {
        this.surname = surname;
    }
}
~~~

Ở đây Java property là `commonName`, nhưng LDAP attribute là `cn` nhờ `@Attribute(name = "cn")`. Các method query dẫn xuất sẽ tham chiếu **tên property Java** (`CommonName`), không phải tùy tiện dùng tên `Cn` khi class không có property đó.

Chú ý import `@Id` từ `org.springframework.ldap.odm.annotations.Id`, không phải `jakarta.persistence.Id`. ID repository là `javax.naming.Name` biểu diễn **DN**, không phải một string UID.

## 4. Query dẫn xuất: chọn rõ equality hay substring

Spring Data LDAP hỗ trợ tạo filter từ tên phương thức repository. Một khai báo cơ bản:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {

    // Tìm giá trị thuộc tính theo equality, KHÔNG có wildcard chủ ý.
    List<PersonEntry> findByCommonName(String commonName);

    // Nghiệp vụ chọn kiểu tìm kiếm prefix.
    List<PersonEntry> findByCommonNameStartingWith(String prefix);

    // Nghiệp vụ chọn kiểu tìm kiếm suffix.
    List<PersonEntry> findByCommonNameEndingWith(String suffix);

    // Nghiệp vụ chọn kiểu tìm kiếm substring.
    List<PersonEntry> findByCommonNameContaining(String fragment);
}
~~~

Định hướng ý nghĩa:

| Phương thức | Ý đồ | Hình dạng filter |
| --- | --- | --- |
| `findByCommonName("Alice Nguyen")` | Tìm equality | `(cn=Alice Nguyen)` |
| `findByCommonNameStartingWith("Ali")` | Bắt đầu bằng | `(cn=Ali*)` |
| `findByCommonNameEndingWith("Nguyen")` | Kết thúc bằng | `(cn=*Nguyen)` |
| `findByCommonNameContaining("ice")` | Chứa đoạn ký tự | `(cn=*ice*)` |

*Hình dạng filter mang tính minh họa*: Spring Data LDAP có thể bổ sung điều kiện `objectClass`, base DN và các ràng buộc từ `@Entry`. Các keyword `StartingWith`, `EndingWith`, `Containing` được định nghĩa cho **ý định substring**, trong khi tên method không có keyword biểu đạt equality.

**Phân biệt hai tầng:** keyword `Containing` có thể quyết định wildcard nằm **trước/sau giá trị**, nhưng điều đó **không cho phép** tự động coi dấu sao *bên trong input người dùng* là wildcard. Khi yêu cầu “tìm literal `*`” mang tính bảo mật hoặc nghiệp vụ quan trọng, cần kiểm tra filter thực tế và kết quả trong **phiên bản Spring Data LDAP đang dùng**, hoặc sử dụng `@Query` với wildcard cố định và parameter binding mặc định như phần tiếp theo.

`Like` là keyword khác với `Containing`/`StartingWith`/`EndingWith`. Đừng tự suy đoán `findByCommonNameLike(...)` luôn có hành vi như SQL `LIKE '%...%'`: ý nghĩa và cách encode mẫu cần đối chiếu tài liệu/version. Với nguồn input chưa tin cậy, ưu tiên phương thức có ngữ nghĩa rõ và kiểm thử ký tự đặc biệt.

### 4.1. Giá trị là chuỗi, không phải filter

Một API controller có thể nhận:

~~~text
GET /people?name=A*B&mode=exact
~~~

Dù HTTP query có ký tự `*`, nếu `mode=exact`, service phải gọi:

~~~java
repository.findByCommonName("A*B");
~~~

với mục đích **tìm giá trị literal `A*B`**, không tự chuyển sang `Like`.

Nếu `mode=startsWith`, service có thể chọn `findByCommonNameStartingWith(...)` nhưng vẫn phải áp dụng quy tắc đầu vào và giới hạn phạm vi. **Chế độ tìm kiếm** do chức năng nghiệp vụ quy định, không được tự nhận dạng wildcard từ sự xuất hiện của `*` trong chuỗi input.

## 5. `@Query`: wildcard cố định trong filter, giá trị được bind an toàn

Với truy vấn phức tạp không dễ suy ra từ method name, Spring Data LDAP hỗ trợ `org.springframework.data.ldap.repository.Query`.

### 5.1. Cú pháp wildcard thuộc mã nguồn

Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;

public interface AdvancedPersonRepository
        extends LdapRepository<PersonEntry> {

    // Equality: mặc định encode ký tự đặc biệt của ?0.
    @Query("(&(objectClass=inetOrgPerson)(cn=?0))")
    List<PersonEntry> findExactName(String literalName);

    // "Chứa": 2 wildcard nằm trong annotation, không lấy từ user.
    @Query("(&(objectClass=inetOrgPerson)(cn=*?0*))")
    List<PersonEntry> findNameContainingLiteral(String fragment);

    // "Bắt đầu bằng": wildcard chỉ do ứng dụng đặt ở cuối.
    @Query("(&(objectClass=inetOrgPerson)(cn=?0*))")
    List<PersonEntry> findNameStartingWithLiteral(String prefix);

    // Presence: dấu * ở đây biểu đạt tồn tại thuộc tính.
    @Query("(&(objectClass=inetOrgPerson)(mail=*))")
    List<PersonEntry> findPeopleWithMail();
}
~~~

Theo tài liệu Spring Data LDAP, **tham số String được bind trực tiếp** vào truy vấn `@Query` được mã hóa mặc định (tài liệu mô tả theo RFC 2254; cú pháp filter LDAP hiện đại được chuẩn hóa trong RFC 4515). Bởi vậy, trong ví dụ:

- Gọi `findExactName("A*B")` cần có ý nghĩa **literal** `(cn=A\2aB)`.
- Gọi `findNameContainingLiteral("A*B")` cần có ý nghĩa **chứa literal** `(cn=*A\2aB*)`.
- Gọi `findNameStartingWithLiteral("A*")` cần có ý nghĩa **prefix có literal sao** `(cn=A\2a*)`.
- `findPeopleWithMail()` dùng `(mail=*)` **cố định** để kiểm tra thuộc tính có tồn tại, không có input để escape.

Cả tên attribute, `objectClass` và vị trí wildcard trong annotation đều **do lập trình viên định nghĩa**, còn `?0` biểu thị một **giá trị dữ liệu**.

`@Query` cũng hỗ trợ tham số đặt tên, ví dụ `:name` (khi cấu hình/annotation tham số đúng); chỉ mục `?0` trong ví dụ làm rõ ranh giới cú pháp và dữ liệu mà không phụ thuộc tên tham số biên dịch.

### 5.2. Đừng thay bind parameter bằng nối chuỗi

**Sai** khi dựng filter thẳng từ input:

~~~java
// KHÔNG DÙNG trong ứng dụng nhận input chưa tin cậy.
String unsafeFilter =
    "(&(objectClass=inetOrgPerson)(cn=*" + userText + "*))";
~~~

Nếu `userText="*"`, filter trở thành `(cn=***)`, có thể mở rộng phạm vi thành **rất nhiều entry** thay vì tìm tên chứa dấu sao thật. Nếu chứa dấu ngoặc hoặc cú pháp filter khác, việc nối chuỗi có thể làm hỏng cú pháp hoặc dẫn đến **LDAP injection**.

**Đúng:** dùng placeholder bind được encoder xử lý:

~~~java
@Query("(&(objectClass=inetOrgPerson)(cn=*?0*))")
List<PersonEntry> findNameContainingLiteral(String userText);
~~~

Không tự gọi một hàm escape rồi chuyển tiếp vào API đã tự encode mà không hiểu cơ chế, vì có thể gây **double escaping** và biến dấu gạch chéo thành dữ liệu literal ngoài ý muốn. Phải phân công **một nơi chịu trách nhiệm mã hóa** và kiểm thử filter tạo ra.

### 5.3. SpEL và property placeholder có ngoại lệ nguy hiểm

Tài liệu Spring Data LDAP nêu rõ: **giá trị lấy từ SpEL expressions hoặc property placeholders trong `@Query` không được tự động escape như tham số bind trực tiếp**.

~~~java
// Không nên dùng kiểu này với input chưa tin cậy:
@Query("(cn=?#{[0]})")
List<PersonEntry> unsafeSpel(String name);

// Nên dùng direct binding:
@Query("(cn=?0)")
List<PersonEntry> safeBinding(String name);
~~~

Biểu thức SpEL không phải tương đương về tính an toàn với `?0`. Nếu thực sự cần SpEL, phải đảm bảo **giá trị kết quả đã được mã hóa đúng cho LDAP filter** và kiểm thử. Tương tự, property placeholder chỉ phù hợp với cấu hình được kiểm soát và cần xem xét escaping riêng; không đưa input HTTP trực tiếp vào một filter template.

## 6. `@LdapEncode`: khi nào được phép giữ dấu `*`?

Trong các phiên bản Spring Data LDAP hỗ trợ `@LdapEncode`, một tham số `@Query` có thể chỉ định encoder riêng.

**Mặc định** là mã hóa các ký tự đặc biệt, bao gồm `*`, để dùng giá trị như dữ liệu. Nhưng `LdapEncoder.LikeEncoder` có chủ đích **giữ dấu `*` trong input** để chúng trở thành wildcard.

Ví dụ về chế độ dành cho **pattern đã được chính ứng dụng tin cậy xây dựng**:

~~~java
import java.util.List;

import org.springframework.data.ldap.repository.LdapEncode;
import org.springframework.data.ldap.repository.LdapEncoder;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;

public interface TrustedPatternRepository
        extends LdapRepository<PersonEntry> {

    @Query("(&(objectClass=inetOrgPerson)(cn=?0))")
    List<PersonEntry> findByApprovedPattern(
        @LdapEncode(LdapEncoder.LikeEncoder.class) String approvedPattern
    );
}
~~~

Ví dụ gọi:

~~~java
// Pattern nội bộ đã được duyệt: wildcard cuối có ý nghĩa prefix.
repository.findByApprovedPattern("Alice*");
~~~

Khi dùng `LikeEncoder`, ký tự `*` trong tham số được giữ lại. Đây là **quyền mở rộng ngữ nghĩa truy vấn**. Nếu nhận trực tiếp `request.getParameter("name")` rồi gọi `findByApprovedPattern`, người dùng có thể thay đổi phạm vi khớp bằng cách nhập `*` ở bất kỳ vị trí nào.

**Không dùng `LikeEncoder` như lựa chọn mặc định cho người dùng cuối.** Chỉ sử dụng nó khi một luồng nghiệp vụ có hợp đồng pattern cụ thể, giới hạn rõ các vị trí wildcard, độ dài, số lượng wildcard và quyền truy vấn.

Một chính sách pattern có thể quy định:

- Người dùng chỉ chọn một trong ba chế độ: `EXACT`, `PREFIX`, `CONTAINS`; **không được tự gửi raw LDAP filter**.
- Ở chế độ `PREFIX`, hệ thống nhận đoạn prefix như **dữ liệu literal**, sau đó tự thêm đúng một wildcard ở cuối.
- Nếu nghiệp vụ thật sự cần người dùng viết pattern, phải có parser/validator tách các đoạn literal và wildcard được phép, không cho phép tạo cấu trúc LDAP filter tự do.
- Các tên attribute được tìm phải thuộc **allowlist** do ứng dụng định nghĩa.
- Search phải có giới hạn base, scope, thời gian và số entry.

`@LdapEncode` chỉ áp dụng cho **tham số được bind trực tiếp trong truy vấn `@Query`**, không áp dụng cho derived query hoặc các value expression như SpEL/property placeholders. Đừng cho rằng chỉ cần gắn annotation này ở mọi nơi là mọi biểu thức đã được xử lý an toàn.

## 7. `LdapTemplate` và các lớp filter: `is` khác `like`

Khi cần query động hoặc tự quản lý base DN, search scope, attribute selection và count/time limit, `LdapTemplate` với `LdapQueryBuilder` cung cấp một cách tiếp cận khác.

### 7.1. Equality an toàn với `.is(...)`

~~~java
import java.util.List;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PeopleSearchService {

    private final LdapTemplate ldapTemplate;

    public PeopleSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findExactName(String literalName) {
        LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid", "cn")
            .countLimit(100)
            .timeLimit(3000)
            .where("objectClass").is("inetOrgPerson")
            .and("cn").is(literalName);

        return ldapTemplate.search(
            ldapQuery,
            attrs -> String.valueOf(attrs.get("uid").get())
        );
    }
}
~~~

Với `literalName="A*B"`, `.is(...)` xem giá trị như dữ liệu equality và áp dụng escaping phù hợp. `objectClass` và `cn` là **tên thuộc tính tĩnh** trong mã nguồn, không phải tham số tự do do người dùng chọn.

Giới hạn `countLimit` và `timeLimit` giúp kiểm soát truy vấn; server vẫn có giới hạn riêng. Một query thành công không có nghĩa ứng dụng có thể đọc toàn bộ directory hoặc vượt qua ACL.

### 7.2. `.like(...)` dành cho mẫu có wildcard được chủ ý

Spring LDAP hỗ trợ:

~~~java
LdapQuery patternQuery = query()
    .base("ou=people")
    .where("cn").like("A*B");
~~~

Theo tài liệu Spring LDAP, `.like("A*B")` cố ý tạo substring filter tương tự `(cn=A*B)`. Dấu `*` trong chuỗi cung cấp cho `.like(...)` **không bị escape theo cách của equality**. Vì vậy, `.like(userInput)` **không phải** cách triển khai an toàn cho trường tìm kiếm literal tùy ý.

API `.whitespaceWildcardsLike(...)` còn cố tình biến khoảng trắng thành wildcard khi xây dựng filter. Đây cũng là **một thay đổi ngữ nghĩa có chủ ý**, không thích hợp nếu người dùng mong so khớp nguyên văn cả dấu cách.

### 7.3. `EqualsFilter` và `LikeFilter`

Hai lớp filter minh họa rõ khác biệt:

~~~java
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.LikeFilter;

String literal = "A*B";

// Dữ liệu literal: dấu * được escape.
String exact = new EqualsFilter("cn", literal).encode();

// Pattern có chủ ý: dấu * giữ lại ý nghĩa wildcard.
String pattern = new LikeFilter("cn", "A*B").encode();
~~~

Kết quả filter có ý nghĩa:

~~~text
exact   = (cn=A\2aB)
pattern = (cn=A*B)
~~~

Theo JavaDoc Spring LDAP, `LikeFilter` cho phép chỉ định wildcard bằng cách **không escape dấu `*`**. Vì vậy, đừng dùng `LikeFilter("cn", requestValue)` nếu request được hiểu là dữ liệu bình thường. Khi cần toán tử substring, hãy chọn cách đặt wildcard do ứng dụng kiểm soát và mã hóa phần literal còn lại.

### 7.4. Dùng `filter(format, params)` khi cần wildcard tĩnh

Một cách tránh nhầm lẫn là cố định wildcard trong **filter template** còn giá trị được truyền như parameter:

~~~java
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Cú pháp {0} thuộc template của Spring LDAP, không phải raw filter user.
LdapQuery containsLiteral = query()
    .base("ou=people")
    .attributes("uid", "cn")
    .countLimit(100)
    .timeLimit(3000)
    .filter(
        "(&(objectClass=inetOrgPerson)(cn=*{0}*))",
        userFragment
    );
~~~

Theo tài liệu Spring LDAP, overload `filter(String filterFormat, String... params)` thực hiện mã hóa tham số trước khi chèn vào filter template. Với `userFragment="*"`, kết quả mong muốn là tìm **literal sao** trong `cn`, không biến đoạn input này thành wildcard. Cần kiểm thử đúng phiên bản thư viện.

**Cẩn thận overload:** `filter(String hardcodedFilter)` nhận **một chuỗi filter thô**, không thay đổi nó, và **không phù hợp** để dựng filter bằng cách nối dữ liệu người dùng. Builder cũng không cho phép tùy ý trộn nhánh `.filter(...)` với `.where(...)` trên cùng query; chọn một kiểu xây dựng filter và dùng nhất quán.

## 8. Thiết kế API phân biệt ba chế độ tìm kiếm

Thay vì để người dùng nhập filter LDAP, API có thể nhận một **mode** rõ ràng:

~~~text
GET /directory/people?mode=EXACT&q=A%2AB
GET /directory/people?mode=PREFIX&q=Ali
GET /directory/people?mode=CONTAINS&q=ice
~~~

`%2A` là cách biểu diễn dấu `*` ở **tầng URL**, không phải LDAP filter escape `\2a`. Phần xử lý HTTP sẽ decode query parameter, rồi dịch vụ Java **mới thực hiện encode LDAP filter**. Hai tầng mã hóa hoàn toàn khác nhau.

Ví dụ một service chỉ cung cấp ba chế độ, không nhận raw filter:

~~~java
import java.util.List;

public enum SearchMode {
    EXACT, PREFIX, CONTAINS
}

public class SafePersonSearch {

    private final AdvancedPersonRepository repository;

    public SafePersonSearch(AdvancedPersonRepository repository) {
        this.repository = repository;
    }

    public List<PersonEntry> search(SearchMode mode, String rawInput) {
        if (mode == null || rawInput == null) {
            throw new IllegalArgumentException("Thiếu chế độ/từ khóa");
        }

        String term = rawInput.strip();

        if (term.isBlank() || term.length() > 80) {
            throw new IllegalArgumentException("Từ khóa không hợp lệ");
        }

        return switch (mode) {
            case EXACT -> repository.findExactName(term);
            case PREFIX -> repository.findNameStartingWithLiteral(term);
            case CONTAINS -> repository.findNameContainingLiteral(term);
        };
    }
}
~~~

**Đây là giới hạn nghiệp vụ**, không phải thao tác escape: `.strip()` thay đổi dữ liệu đầu vào. Nếu hệ thống cho phép tên chứa khoảng trắng có ý nghĩa ở đầu/cuối, đừng `.strip()` một cách tự động ở chế độ `EXACT`; phải định nghĩa hợp đồng canonicalization phù hợp. Ngoài ra, giới hạn 80 ký tự là ví dụ, không thay thế chính sách thực tế.

Những điểm an toàn:

1. Enum `SearchMode` chỉ cho phép các chức năng đã thiết kế; **không nhận cả filter/attribute name** từ caller.
2. Input được truyền vào **tham số bind thông thường**, không dùng `LikeEncoder` hay SpEL chưa encode.
3. Dấu `*`, `(`, `)` người dùng nhập vẫn là **dữ liệu** trong cả ba chế độ.
4. `PREFIX` và `CONTAINS` là **ngữ nghĩa do ứng dụng chọn**, không phải tự động “nâng quyền” khi user nhập wildcard.
5. Phân quyền LDAP server, giới hạn count/time, base DN và rate limiting vẫn cần cho các search rộng.

### 8.1. Rủi ro truy vấn rộng dù escaping đã đúng

Escaping chống LDAP injection không tự ngăn một truy vấn **hợp lệ nhưng quá rộng**. Ví dụ `CONTAINS` với một ký tự như `"a"` có thể trả rất nhiều entry. Chuỗi trống trong template `(cn=*{0}*)` có thể tạo `(cn=**)`, khiến filter mang ý nghĩa gần như không ràng buộc.

Vì vậy cần:

- Từ chối input rỗng/độ dài quá ngắn ở chế độ substring nếu nghiệp vụ không cho phép.
- Giới hạn phạm vi nhánh `ou=people` thay vì `dc=example,dc=org` khi không cần toàn directory.
- Giới hạn số kết quả, timeout và số request mỗi người dùng.
- Chỉ lấy `uid`, `cn` khi danh sách không cần `jpegPhoto` hoặc thuộc tính nhạy cảm.
- Ghi nhận kết quả bị cắt/giới hạn rõ ràng; không trình bày một tập kết quả một phần như toàn bộ dữ liệu.
- Dùng Paged Results Control khi cần xử lý dữ liệu lớn và server hỗ trợ, nhưng không xem paging là biện pháp bảo mật thay cho ACL.

## 9. Ma trận ví dụ: literal input so với wildcard có chủ ý

Giả sử dữ liệu có hai entry:

~~~text
cn: A*B
cn: AxxB
~~~

| Mong muốn | Tham số đầu vào | Filter hợp lệ về ý nghĩa | Entry dự kiến khớp |
| --- | --- | --- | --- |
| Tìm tên đúng `A*B` | Literal `A*B` | `(cn=A\2aB)` | `A*B` |
| Tìm tên có dạng A ... B | Pattern được ứng dụng cho phép `A*B` | `(cn=A*B)` | `A*B`, `AxxB` |
| Tìm tên chứa dấu `*` | Literal `*` trong chế độ CONTAINS | `(cn=*\2a*)` | `A*B` |
| Tìm `cn` có tồn tại | Không có tham số | `(cn=*)` | Cả hai |
| Tìm prefix literal `A*` | Literal `A*` trong chế độ PREFIX | `(cn=A\2a*)` | `A*B` |
| Tìm prefix `A` | Literal `A` trong chế độ PREFIX | `(cn=A*)` | Cả hai |
| Tìm tên chứa dấu ngoặc | Literal `(Test)` | `(cn=*\28Test\29*)` | Tên chứa `(Test)` |
| Tìm một dấu `\` literal | Literal backslash | `(cn=*\5c*)` | Tên chứa dấu backslash |

Đây là **ngữ nghĩa filter**, không phải cam kết số lượng record chính xác trên mọi server. LDAP matching rules, normalization, ACL và các entry khác có thể ảnh hưởng kết quả thật; bảng sử dụng cây ví dụ đơn giản để làm nổi bật escaping.

## 10. Kiểm thử hồi quy để chống wildcard injection

Chỉ unit test “method đã được gọi” không chứng minh được filter LDAP đã được encode chính xác. Nên có **integration test với LDAP server nhúng hoặc container**, dữ liệu fixture và schema tương ứng.

### 10.1. Fixture kiểm thử

Ví dụ LDIF (trong môi trường test cô lập):

~~~ldif
dn: uid=literal-star,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: literal-star
cn: A*B
sn: Literal

dn: uid=substring-test,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: substring-test
cn: AxxB
sn: Substring

dn: uid=ops,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: ops
cn: Ops (Test)
sn: Test
~~~

Giả sử `dc=example,dc=org` và `ou=people` đã tồn tại. LDIF ở trên chỉ gồm **các entry con**, tránh import trùng root và OU nếu server/bootstrap đã tạo sẵn.

### 10.2. Test repository dùng đúng parameter binding

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("ldap-test")
class WildcardRepositoryIT {

    @Autowired
    AdvancedPersonRepository repository;

    @Test
    void exactNameTreatsAsteriskAsLiteral() {
        var people = repository.findExactName("A*B");

        assertThat(people)
            .extracting(PersonEntry::getUid)
            .containsExactlyInAnyOrder("literal-star");
    }

    @Test
    void containsTreatsInputAsteriskAsLiteral() {
        var people = repository.findNameContainingLiteral("*");

        assertThat(people)
            .extracting(PersonEntry::getUid)
            .containsExactlyInAnyOrder("literal-star");
    }

    @Test
    void prefixAddsOnlyIntentionalWildcard() {
        var people = repository.findNameStartingWithLiteral("A*");

        assertThat(people)
            .extracting(PersonEntry::getUid)
            .containsExactlyInAnyOrder("literal-star");
    }

    @Test
    void encodedParenthesesDoNotChangeFilterTree() {
        var people = repository.findNameContainingLiteral("(Test)");

        assertThat(people)
            .extracting(PersonEntry::getUid)
            .containsExactlyInAnyOrder("ops");
    }
}
~~~

Để test chạy được, phải cấu hình profile `ldap-test` với `ContextSource`, schema, data fixture và repository scanning. Các assert dùng `containsExactlyInAnyOrder`, vì thứ tự LDAP Search **không được đảm bảo** nếu không có cơ chế sort rõ ràng.

Nếu test trả thêm `substring-test` khi đầu vào exact là `A*B` hoặc khi tìm tên chứa literal `*`, có khả năng filter đang giữ dấu sao của user làm wildcard. Đây là dấu hiệu phải xem lại cách bind/encoder, không nên chỉ sửa assert để test xanh.

### 10.3. Các ca tấn công và input bất thường

Một bộ test tốt cần phân loại:

| Input | Chế độ | Kỳ vọng an toàn |
| --- | --- | --- |
| `*` | EXACT | Chỉ khớp giá trị đúng một dấu sao, không biến thành presence |
| `*` | CONTAINS | Tìm thuộc tính có **ký tự sao thật** |
| `A*B` | EXACT | Chỉ đúng literal `A*B`, không khớp `AxxB` |
| `A*` | PREFIX | Prefix chứa dấu sao literal, rồi mới đến wildcard của ứng dụng |
| `(` và `)` | EXACT/CONTAINS | Là nội dung ký tự, không tạo cấu trúc filter |
| Dấu `\` | EXACT | Escape `\5c`, không cho input tự tạo `\2a` |
| Chuỗi chứa NUL | EXACT | Được encode đúng hoặc bị từ chối bởi chính sách input |
| Chuỗi rỗng | CONTAINS | Bị từ chối theo quy tắc nghiệp vụ, không tạo truy vấn toàn thư mục |
| Chuỗi rất dài | Mọi mode | Bị giới hạn trước truy vấn để bảo vệ server |
| Input mô phỏng filter `*)(|(uid=*))` | EXACT | Không thay cấu trúc filter hoặc mở rộng kết quả |

Ngoài việc assert số lượng entry, với LDAP integration test nên so sánh kết quả **bằng DN/UID** và dùng dữ liệu đủ phân biệt literal/substring. Kiểm thử riêng một tên không chứa ký tự đặc biệt không phát hiện được lỗi escaping.

Nếu kiểm tra log/debug filter, không đưa dữ liệu người dùng hoặc toàn bộ danh sách DN lên nơi công khai; chỉ ghi metadata an toàn và có chính sách giữ log. Không dùng tài khoản quản trị để chạy search production.

## 11. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Hướng thay thế |
| --- | --- | --- |
| Gọi `.like(input)` cho trường tìm nguyên văn | Dấu `*` của người dùng được hiểu là wildcard | Dùng `.is(input)` hoặc bind parameter mặc định |
| Ghép `"(cn=*" + input + "*)"` | LDAP injection, filter sai hoặc mở rộng kết quả | `@Query` wildcard tĩnh + `?0`/`:name` được bind |
| Dùng `LikeFilter` cho mọi giá trị | Không escape ký tự `*` theo nghĩa dữ liệu | Dùng `EqualsFilter` cho equality |
| Dùng `@LdapEncode(LikeEncoder.class)` với input HTTP | Input `*` điều khiển phạm vi khớp | Chỉ áp dụng cho pattern đã được kiểm soát/được duyệt |
| Nghĩ `Like` là SQL `LIKE` | Sai cú pháp và mong đợi wildcard | Đọc keyword của LDAP và kiểm thử filter thực tế |
| Dùng SpEL `?#{[0]}` thay `?0` | Giá trị SpEL không tự được escape | Prefer direct bound parameters |
| Nhầm URL-encoding `%2A` với LDAP escaping `\2a` | Ký tự được giải mã ở tầng sai | Xử lý URL và LDAP filter ở hai tầng riêng |
| Tự escape trước rồi dùng binder | Double escaping, tìm không ra literal mong muốn | Một tầng encoder duy nhất và integration test |
| Cho caller chọn tên LDAP attribute tùy ý | Truy vấn thuộc tính không được dự kiến/cho phép | Allowlist thuộc tính ở code |
| Dùng `(cn=*)` để tìm literal `*` | Trả mọi entry có thuộc tính `cn` | Dùng `(cn=\2a)` hoặc `(cn=*\2a*)` |
| Dùng DN escape cho filter value | Sai ngữ nghĩa escaping | DN dùng `LdapNameBuilder`; filter dùng binder/filter encoder |
| Search `CONTAINS` quá rộng không giới hạn | Quá tải directory và có thể lộ nhiều dữ liệu | Base hẹp, ACL, count/time limits, rate limit và kiểm thử |

## 12. Quy trình triển khai một chức năng tìm kiếm an toàn

~~~mermaid
flowchart TD
    A["Nhận request q + chế độ tìm kiếm"] --> B{"Mode hợp lệ?"}
    B -->|Không| C["Từ chối request"]
    B -->|Có| D["Kiểm tra độ dài, rỗng, quyền nghiệp vụ"]
    D --> E{"EXACT / PREFIX / CONTAINS"}
    E -->|EXACT| F["Equality + bind literal"]
    E -->|PREFIX| G["Wildcard ứng dụng ở cuối + bind literal"]
    E -->|CONTAINS| H["Wildcard ứng dụng ở hai đầu + bind literal"]
    F --> I["Thực hiện query trong base/ACL/limits"]
    G --> I
    H --> I
    I --> J["Nhận và xác minh kết quả"]
    J --> K["Log metadata an toàn, không log filter nhạy cảm"]
~~~

Checklist triển khai:

1. Xác nhận **input thuộc loại literal hay pattern**; văn bản người dùng thông thường mặc định là literal.
2. Định nghĩa **mode bằng API/enum**, không suy diễn từ dấu `*` nhập vào.
3. Chọn repository query derivation hoặc `@Query` với placeholder bind trực tiếp.
4. Đặt wildcard và tên attribute trong **cú pháp tĩnh do ứng dụng kiểm soát**.
5. Tránh `.like(...)`, `LikeFilter` và `LikeEncoder` với raw user input trừ khi đã có hợp đồng pattern rõ ràng.
6. Tránh đưa input chưa encode vào SpEL, property placeholder, `filter(String)` hoặc nối chuỗi.
7. Giới hạn base DN, scope, số kết quả, timeout và quyền đọc.
8. Kiểm thử `*`, `(`, `)`, `\`, NUL, chuỗi rỗng, chuỗi dài và input giống một filter khác.
9. Kiểm chứng với directory thực/embedded có schema và matching rules tương đương.
10. Khi cần DN động, xử lý DN bằng `LdapName`/`LdapNameBuilder` riêng khỏi filter.

## 13. Câu hỏi tự kiểm tra

1. Tại sao `(cn=*)` không phải filter tìm một dấu sao literal?
2. Người dùng nhập `A*B` ở chế độ EXACT. Filter có ý nghĩa đúng phải là `(cn=A*B)` hay `(cn=A\2aB)`? Vì sao?
3. Trong `@Query("(cn=*?0*)")`, dấu sao nào thuộc cú pháp do ứng dụng quyết định, và phần nào là dữ liệu được encode?
4. `findByCommonNameContaining(...)` khác `findByCommonName(...)` ở **ý nghĩa truy vấn** như thế nào?
5. Vì sao không nên tự gọi `String.replace("*", ...)` rồi nối vào một filter LDAP?
6. `@LdapEncode(LdapEncoder.LikeEncoder.class)` giải quyết nhu cầu gì? Điều gì xảy ra nếu truyền thẳng input người dùng vào đó?
7. Vì sao SpEL value expression không tương đương về escaping với `?0` trực tiếp?
8. Hãy giải thích vì sao dấu `*` trong `@Query("(mail=*)")` được cho phép nhưng dấu `*` trong HTTP input phải coi là dữ liệu.
9. Khi người dùng nhập `\2a` như bốn ký tự thực, filter phải làm gì với dấu `\` để không biến input thành dấu sao ngoài ý muốn?
10. Dù escaping đã đúng, vì sao `CONTAINS` với `"a"` vẫn có thể gây vấn đề hiệu năng?
11. Viết một test chứng minh tìm literal `*` không trả entry `AxxB`, nhưng tìm pattern `A*B` có thể trả cả `A*B` và `AxxB`.
12. Tại sao kết quả query có thể khác nhau giữa hai directory dù filter giống nhau, khi schema định nghĩa matching rule khác?
13. DN `uid=a*b,ou=people` được tạo an toàn bằng công cụ nào, và vì sao không dùng filter escaping để xây DN?
14. Khi có nhu cầu cho phép một bộ phận quản trị nhập pattern, cần giới hạn gì ngoài việc chỉ chọn một encoder giữ dấu sao?

## 14. Kết luận

Trong Spring Data LDAP, **wildcard là cú pháp của LDAP filter**, trong khi **dữ liệu người dùng phải được mã hóa như assertion value**. Một dấu sao `*` trong source code/`@Query` có thể mang ý nghĩa substring hoặc presence được **chủ ý thiết kế**; cùng ký tự đó, khi xuất hiện trong input thông thường, phải được biểu diễn theo nghĩa literal (`\2a`).

Đối với repository, ưu tiên **phương thức tìm chính xác hoặc query có wildcard tĩnh với tham số `@Query` được bind trực tiếp**. Dùng `StartingWith`/`EndingWith`/`Containing` khi nghiệp vụ thật sự muốn substring, nhưng vẫn kiểm thử sự khác biệt giữa wildcard do ứng dụng tạo và dấu sao trong input. Với `LdapTemplate`, `.is(...)` và `EqualsFilter` dành cho dữ liệu literal, còn `.like(...)`/`LikeFilter` hoặc `LikeEncoder` chỉ dành cho mẫu có wildcard được kiểm soát.

Một hệ thống tìm kiếm tốt không chỉ chống LDAP injection: nó còn giới hạn phạm vi, tài nguyên, phân quyền và có integration test kiểm chứng ký tự đặc biệt trên directory thật. **Ranh giới giữa cú pháp và dữ liệu** chính là yếu tố giúp query đúng cả về chức năng lẫn bảo mật.

### Tài liệu tham khảo

- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515).
- [RFC 4511 — LDAPv3 Search and Controls](https://www.rfc-editor.org/rfc/rfc4511).
- [Spring Data LDAP — Query Methods và Parameter Encoding](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html).
- [Spring Data LDAP — Query Methods Details](https://docs.spring.io/spring-data/ldap/reference/repositories/query-methods-details.html).
- [Spring Data LDAP API — `@LdapEncode`](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapEncode.html).
- [Spring Data LDAP API — `LdapEncoder.LikeEncoder`](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapEncoder.LikeEncoder.html).
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html).
- [Spring LDAP API — `LikeFilter`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/filter/LikeFilter.html).
