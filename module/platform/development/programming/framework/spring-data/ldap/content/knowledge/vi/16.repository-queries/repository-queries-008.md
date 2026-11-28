# Liên kết tham số theo vị trí và khả năng tham số có tên theo phiên bản

Trong **Spring Data LDAP**, repository method có thể tạo LDAP query từ tên method hoặc dùng filter tự định nghĩa qua `@Query`. Khi filter cần nhận surname, email hay DN do ứng dụng cung cấp, các giá trị đó phải được **liên kết với tham số method** một cách rõ ràng. Spring Data LDAP có cách liên kết **theo vị trí** và, ở các phiên bản có hỗ trợ, cách liên kết **theo tên**.

- **Theo vị trí:** `?0`, `?1`, ... tham chiếu tham số method theo chỉ số bắt đầu từ 0.
- **Theo tên:** `:surname`, `:emailAddress`, ... tham chiếu tham số theo tên.

Tài liệu Spring Data LDAP 3.5.8 và 4.1.1 công bố cả hai dạng. Không nên suy luận khả năng này chỉ từ phiên bản Spring Framework hoặc Spring Data Commons: cần kiểm tra **đúng phiên bản artifact `spring-data-ldap`** đang chạy. Bài này cũng phân biệt placeholder của `@Query` với `{0}` của `LdapQueryBuilder.filter(format, ...)`, vì chúng thuộc hai API khác nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt query method **suy diễn từ tên** và query method **khai báo filter bằng `@Query`**.
- Viết filter dùng tham số vị trí `?0`, `?1` và hiểu chỉ số bắt đầu từ 0.
- Viết filter dùng tham số có tên `:surname`, `:emailAddress` trong phiên bản hỗ trợ.
- Giải thích lợi ích của tham số có tên khi method được refactor hoặc thay đổi thứ tự tham số.
- Dùng `@Param` để ánh xạ tên tham số rõ ràng.
- Phân biệt `@Query` placeholders với `LdapQueryBuilder.filter(String, String...)` dùng `MessageFormat`.
- Hiểu cách Spring Data LDAP encode giá trị tham số để tránh LDAP filter injection.
- Biết khi nào cần `@LdapEncode`, `LdapEncoder.LikeEncoder`, SpEL hoặc property placeholder.
- Viết integration test xác nhận tham số được gắn đúng và ký tự đặc biệt được xử lý an toàn.

## 2. Ngữ cảnh: từ Java method đến LDAP filter

Giả sử ứng dụng quản lý người dùng trong naming context `dc=example,dc=org`:

```text
dc=example,dc=org
└── ou=people
    ├── uid=alice
    │   ├── sn: Nguyen
    │   ├── givenName: Alice
    │   └── mail: alice@example.org
    └── uid=bob
        ├── sn: Tran
        ├── givenName: Bob
        └── mail: bob@example.org
```

Một method có thể tìm theo hai điều kiện:

```text
surname = "Nguyen"
givenName = "Alice"

LDAP filter:
(&(objectClass=inetOrgPerson)(sn=Nguyen)(givenName=Alice))
```

Không nên ghép input vào filter bằng phép nối chuỗi. Framework cần biết **phần nào là cấu trúc filter cố định** và **phần nào là giá trị dữ liệu** để encode đúng ngữ cảnh.

## 3. Hai cách tạo query method trong repository

Spring Data LDAP hỗ trợ hai hướng chính:

1. **Derived query:** framework phân tích tên method và tạo điều kiện từ tên thuộc tính Java.
2. **Declared query:** method được gắn `@Query` để khai báo filter LDAP cụ thể.

Ví dụ derived query:

```java
public interface PersonRepository extends LdapRepository<Person> {
    List<Person> findBySurname(String surname);

    List<Person> findBySurnameAndGivenName(
            String surname, String givenName);
}
```

Framework dựa vào tên thuộc tính của entity để tạo filter tương ứng. Với method thứ hai, hai tham số lần lượt cung cấp giá trị cho `surname` và `givenName`. Người viết method không phải tự đánh số placeholder trong filter.

Dùng `@Query` khi filter cần được viết cụ thể:

```java
@Query("(&(objectClass=inetOrgPerson)(sn=?0)(givenName=?1))")
List<Person> findByNameWithCustomFilter(
        String surname, String givenName);
```

## 4. Chuẩn bị entity và repository

Giả sử entry LDAP có dạng:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
givenName: Alice
mail: alice@example.org
```

Entity ODM tương ứng:

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
public class Person {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "givenName")
    private String givenName;

    @Attribute(name = "mail")
    private String mail;

    protected Person() { }

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getSurname() { return surname; }
    public String getGivenName() { return givenName; }
    public String getMail() { return mail; }
}
```

Repository:

```java
package com.example.directory;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    List<Person> findBySurnameAndGivenName(
            String surname, String givenName);
}
```

`LdapRepository<Person>` là repository chuyên biệt của Spring Data LDAP; ID của entity ODM là DN kiểu `javax.naming.Name`. Với ứng dụng có nhiều Spring Data modules, hãy cấu hình scan repository phù hợp để repository được nhận diện là LDAP repository.

## 5. Liên kết tham số theo vị trí trong `@Query`

Tham số vị trí được viết bằng `?0`, `?1`, `?2`, ... **Chỉ số đầu tiên là 0**, không phải 1.

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;

public interface PersonRepository extends LdapRepository<Person> {

    @Query("(&(objectClass=inetOrgPerson)(sn=?0)(givenName=?1))")
    List<Person> findBySurnameAndGivenName(
            String surname,
            String givenName);
}
```

Khi gọi:

```java
List<Person> people =
        repository.findBySurnameAndGivenName("Nguyen", "Alice");
```

Framework gắn:

| Placeholder | Tham số method | Giá trị minh họa |
| --- | --- | --- |
| `?0` | Tham số thứ nhất | `Nguyen` |
| `?1` | Tham số thứ hai | `Alice` |

Filter sau khi bind về mặt logic:

```ldap
(&(objectClass=inetOrgPerson)(sn=Nguyen)(givenName=Alice))
```

### 5.1. Ưu điểm và nhược điểm

**Ưu điểm:** cú pháp ngắn, dễ dùng với query có ít tham số và dễ đối chiếu thứ tự method với placeholder.

**Nhược điểm:** query dài khiến người đọc phải đếm vị trí; đổi thứ tự tham số method có thể làm filter bind sai mà code vẫn biên dịch.

Ví dụ:

```java
// Ban đầu:
@Query("(&(sn=?0)(givenName=?1))")
List<Person> findPeople(String surname, String givenName);

// Nếu đổi thứ tự khai báo method nhưng quên đổi filter:
@Query("(&(sn=?0)(givenName=?1))")
List<Person> findPeople(String givenName, String surname);
```

Filter vẫn nhận `?0` cho `sn` và `?1` cho `givenName`, trong khi ý nghĩa tham số method đã đổi.

## 6. Liên kết tham số có tên

Ở các phiên bản Spring Data LDAP có hỗ trợ named parameter binding, tên tham số trong filter được đặt sau dấu hai chấm:

```java
@Query("(&(objectClass=inetOrgPerson)(sn=:surname)(givenName=:givenName))")
List<Person> findByName(
        String surname,
        String givenName);
```

`:surname` tham chiếu tham số tên `surname`; `:givenName` tham chiếu tham số tên `givenName`. Thứ tự khai báo tham số method không còn là yếu tố quyết định việc gắn giá trị.

Để tên tham số tường minh và ổn định, dùng annotation `@Param` của Spring Data:

```java
package com.example.directory;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends LdapRepository<Person> {

    @Query("(&(objectClass=inetOrgPerson)(sn=:surname)(givenName=:givenName))")
    List<Person> findByName(
            @Param("surname") String familyName,
            @Param("givenName") String firstName);
}
```

Tên Java trong method có thể là `familyName` và `firstName`; `@Param` khai báo rõ mapping đến tên trong filter. Điều này tránh phụ thuộc vào việc compiler có lưu tên tham số trong bytecode hay không.

### 6.1. Đổi thứ tự tham số mà không đổi ý nghĩa filter

```java
@Query("(&(objectClass=inetOrgPerson)(sn=:surname)(givenName=:givenName))")
List<Person> findByName(
        @Param("givenName") String firstName,
        @Param("surname") String familyName);
```

Method vẫn bind đúng:

| Tên trong filter | Annotation | Biến Java |
| --- | --- | --- |
| `:surname` | `@Param("surname")` | `familyName` |
| `:givenName` | `@Param("givenName")` | `firstName` |

### 6.2. Quy tắc đặt tên

- Tên sau dấu `:` phải khớp với tên được framework khám phá hoặc giá trị trong `@Param`.
- Không đặt khoảng trắng trong tên tham số.
- Không dùng tên attribute LDAP làm placeholder nếu method parameter không có mapping tương ứng.
- Không nhầm `:surname` với property placeholder hoặc cú pháp tham số của thư viện khác.

## 7. Khả năng theo phiên bản Spring Data LDAP

Không nên mặc định mọi phiên bản Spring Data LDAP đều có cùng cú pháp tham số. Hãy kiểm tra phiên bản artifact thực tế trong dependency management và tài liệu API tương ứng.

| Phiên bản/tài liệu đối chiếu | Điều tài liệu công bố | Cách sử dụng |
| --- | --- | --- |
| Spring Data LDAP 3.1.11 Reference | Phần query methods mô tả query suy diễn từ tên method; tài liệu đó không trình bày cú pháp binding của `@Query`. | Không suy đoán named binding từ tài liệu này; kiểm tra API/release đang dùng hoặc dùng derived query. |
| Spring Data LDAP 3.4.0 API | Có annotation `@Query`, nhưng Javadoc của bản này không mô tả rõ các dạng placeholder positional/named. | Không dựa vào cú pháp mới nếu chưa xác minh đúng artifact. |
| Spring Data LDAP 3.5.8 API | Nêu rõ binding theo vị trí `?0` và theo tên `:someParam`. | Có thể dùng cả hai dạng theo tài liệu API. |
| Spring Data LDAP 4.0.6/4.1.1 Reference | Nêu rõ cả named binding và positional binding; khuyến nghị named parameter để dễ đọc và ít lỗi khi refactor. | Ưu tiên named binding cho query nhiều tham số khi ứng dụng chạy phiên bản hỗ trợ. |

**Kết luận về tương thích:** tài liệu cụ thể cho cả hai dạng có ở dòng 3.5.x (API 3.5.8) và 4.x. Nếu dự án dùng bản cũ hơn, đừng lấy ví dụ mới rồi giả định nó hoạt động. Kiểm tra Javadoc của đúng version, dependency được BOM quản lý và integration test khi nâng cấp.

### 7.1. Kiểm tra version ứng dụng đang dùng

Với Gradle:

```bash
./gradlew dependencyInsight \
  --dependency spring-data-ldap \
  --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-ldap
```

Không chỉ xem version được ghi trực tiếp trong file build: Spring Boot BOM hoặc Spring Data BOM có thể quyết định version thực tế. Tránh tự nâng riêng một module Spring Data mà không kiểm tra release train tương thích.

### 7.2. Nếu phiên bản chưa xác nhận named binding

1. Dùng derived query nếu điều kiện có thể biểu đạt rõ qua tên method.
2. Kiểm tra API đúng version và viết integration test nhỏ cho `@Query`.
3. Nếu cần filter tự định nghĩa nhưng không muốn phụ thuộc named binding, dùng positional binding chỉ khi version đó xác nhận hỗ trợ.
4. Có thể chuyển truy vấn sang `LdapTemplate`/`LdapQueryBuilder`, dùng overload format có tham số đã được encode.
5. Nếu ứng dụng cần named binding và phiên bản hiện tại không hỗ trợ, lên kế hoạch nâng cấp theo release train phù hợp.

Không thay named parameter bằng cách nối chuỗi thủ công để né giới hạn version.

## 8. Phân biệt ba loại placeholder

| Ngữ cảnh | Ví dụ placeholder | Ý nghĩa |
| --- | --- | --- |
| `@Query` positional | `?0`, `?1` | Tham số method theo vị trí, chỉ số bắt đầu từ 0. |
| `@Query` named | `:surname` | Tham số method theo tên, nếu phiên bản hỗ trợ. |
| `LdapQueryBuilder.filter(format, params)` | `{0}`, `{1}` | Tham số chuỗi format theo `MessageFormat`. |
| Spring Data Value Expressions / SpEL | `?#{[0]}`, `:?#{principal.emailAddress}` | Biểu thức truy xuất đối số hoặc context runtime. |
| Property placeholder | `:?${app.ldap.stage:dev}` | Giá trị lấy từ Spring Environment/configuration. |

### 8.1. `?0` không phải `{0}`

Trong `@Query`:

```java
@Query("(sn=?0)")
List<Person> findBySurname(String surname);
```

Trong `LdapQueryBuilder.filter(String, String...)`:

```java
LdapQuery ldapQuery = query()
        .filter("(sn={0})", surname);
```

Hai cú pháp thuộc hai bộ xử lý khác nhau. Không chuyển `?0` thành `{0}` trong `@Query` hoặc ngược lại rồi mong framework tự hiểu.

### 8.2. Không nhầm named parameter với tên thuộc tính

```java
@Query("(&(objectClass=inetOrgPerson)(sn=:surname))")
List<Person> findBySurname(@Param("surname") String value);
```

- `sn` là tên **attribute LDAP**.
- `surname` là tên **tham số query**.
- `value` là tên biến Java, được ánh xạ tới `surname` bởi `@Param`.

## 9. `LdapQueryBuilder.filter(format, params)` là một API khác

Khi thao tác trực tiếp với `LdapTemplate`, Spring LDAP cung cấp overload:

```java
filter(String filterFormat, String... params)
```

Overload này dùng `MessageFormat` và **encode các tham số** khi chèn vào filter:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery ldapQuery = query()
        .base("ou=people")
        .filter(
                "(&(objectClass=inetOrgPerson)(sn={0})(givenName={1}))",
                surname,
                givenName);
```

Ở đây `{0}` nhận `surname` và `{1}` nhận `givenName`. Không dùng `String.format` hoặc nối chuỗi để tự tạo filter.

Một API khác là:

```java
LdapQuery unsafe = query()
        .filter("(sn=" + rawSurname + ")");
```

Filter hardcoded được truyền trực tiếp không tự được sửa hay encode. Nếu `rawSurname` đến từ người dùng, cách viết này có nguy cơ LDAP filter injection.

**Quy tắc:** khi dùng `LdapQueryBuilder.filter(...)`, chọn overload có `filterFormat` và `params` để giá trị được encode. Khi dùng `where("sn").is(surname)`, query builder xây điều kiện theo criteria API thay vì tự ghép raw filter.

## 10. Mã hóa tham số và LDAP filter injection

LDAP filter có cú pháp riêng. Các ký tự đặc biệt trong assertion value có thể làm thay đổi cấu trúc filter nếu không được encode đúng:

- `*` — wildcard trong substring/presence filter.
- `(` và `)` — mở/đóng biểu thức filter.
- `\` — ký tự escape.
- NUL — ký tự null.

Không viết:

```java
// KHÔNG AN TOÀN
String filter = "(uid=" + username + ")";
```

Nếu input chứa cú pháp filter, người dùng có thể làm thay đổi logic truy vấn thay vì chỉ cung cấp một giá trị `uid`.

### 10.1. Mặc định encoding của `@Query`

Tài liệu Spring Data LDAP cho biết tham số của string-based query được encode theo quy tắc LDAP filter (tài liệu mô tả theo RFC 2254). Điều này giúp ký tự đặc biệt trong giá trị tham số được xử lý như **dữ liệu**, không phải cấu trúc filter.

Nếu `surname` chứa `*`, mặc định encoding coi nó là ký tự literal. Vì thế input `"Nguyen*"` không nhất thiết có nghĩa “mọi surname bắt đầu bằng Nguyen”. Nếu nghiệp vụ muốn wildcard, cần chọn API/encoder phù hợp.

### 10.2. Dùng `@LdapEncode` khi muốn thay đổi encoder

Spring Data LDAP cung cấp `@LdapEncode` để chỉ định encoder cho **một tham số cụ thể** của repository query method.

Ví dụ giữ lại wildcard `*` cho tìm kiếm substring:

```java
import org.springframework.data.ldap.repository.LdapEncode;
import org.springframework.data.ldap.repository.LdapEncoder;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

@Query("(&(objectClass=inetOrgPerson)(cn=:pattern))")
List<Person> findByCommonNamePattern(
        @Param("pattern")
        @LdapEncode(LdapEncoder.LikeEncoder.class)
        String pattern);
```

`LdapEncoder.LikeEncoder` giữ lại dấu wildcard theo semantics của encoder trong khi escape các ký tự cần thiết. Dùng nó **chỉ khi** ứng dụng chủ ý hỗ trợ pattern search; không gắn encoder này đại trà cho mọi tham số username/email.

`@LdapEncode` áp dụng cho tham số được bind trực tiếp vào string-based query. Nó **không tự áp dụng** cho derived query hoặc tham số được đưa vào qua Value Expressions như SpEL/property placeholders.

### 10.3. DN escaping khác filter escaping

Một tham số có thể là DN:

```text
uid=alice,ou=people,dc=example,dc=org
```

Khi DN được truyền vào filter:

```java
@Query("(member=:memberDn)")
List<GroupEntry> findGroupsContaining(
        @Param("memberDn") String memberDn);
```

Framework phải encode **giá trị filter** theo ngữ cảnh LDAP filter. Điều đó không có nghĩa nó xây một DN mới hoặc xác nhận DN có tồn tại. Khi tạo DN từ RDN đầu vào, dùng `LdapNameBuilder`/`LdapName` để xử lý cú pháp DN; khi đưa DN vào filter, dùng cơ chế filter parameter binding.

Không dùng một hàm escape duy nhất cho cả DN và filter.

## 11. SpEL và Property Placeholders trong `@Query`

Spring Data LDAP còn hỗ trợ Value Expressions cho query phụ thuộc context hoặc cấu hình.

### 11.1. Truy cập tham số method bằng SpEL

Ví dụ truy cập tham số đầu tiên theo chỉ số:

```java
@Query("(&(objectClass=inetOrgPerson)(sn=?#{[0]}))")
List<Person> findBySurnameUsingExpression(String surname);
```

Ví dụ truy cập thông tin principal:

```java
@Query("(&(objectClass=inetOrgPerson)(mail=:?#{principal.emailAddress}))")
List<Person> findForCurrentPrincipal();
```

Đây là **SpEL expression**, không phải named parameter thông thường. Tài liệu Spring Data LDAP cảnh báo giá trị do SpEL cung cấp **không được tự encode theo RFC 2254**. Nếu expression trả về input có ký tự filter đặc biệt, cần encode rõ ràng, chẳng hạn qua helper `org.springframework.ldap.support.LdapEncoder` hoặc một SpEL extension phù hợp.

### 11.2. Property placeholder

Có thể đưa cấu hình môi trường vào filter:

```java
@Query("(&(objectClass=inetOrgPerson)(sn=?0)(department=:?${app.ldap.department:engineering}))")
List<Person> findBySurnameAndConfiguredDepartment(String surname);
```

`${app.ldap.department:engineering}` lấy giá trị property; nếu không có thì dùng mặc định `engineering`. Property placeholder không phải tham số method và **không tự được encode như bind parameter**. Không đưa dữ liệu người dùng trực tiếp vào property chỉ để tạo filter.

### 11.3. Chọn cơ chế phù hợp

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Truy vấn theo thuộc tính và tham số rõ ràng | Derived query hoặc `@Query` với `?0`/`:name`. |
| Filter phụ thuộc người dùng hiện tại | SpEL, đồng thời tự bảo đảm encoding giá trị. |
| Filter phụ thuộc cấu hình môi trường | Property placeholder; chỉ dùng giá trị cấu hình tin cậy và encode nếu cần. |
| Cần giữ wildcard trong tham số tìm kiếm | `@LdapEncode(LdapEncoder.LikeEncoder.class)` hoặc API `LdapQueryBuilder.like(...)`. |
| Tạo filter động bằng Java | `LdapQueryBuilder`, dùng criteria API hoặc overload format có tham số. |

## 12. Kiểu dữ liệu tham số

Theo API `@Query` của Spring Data LDAP, tham số không phải `String` được chuyển sang biểu diễn `toString()` để đưa vào filter.

| Kiểu Java | Ví dụ | Lưu ý |
| --- | --- | --- |
| `String` | `"Nguyen"` | Phù hợp với attribute string nếu schema/matching rule tương ứng. |
| `Integer`/`Long` | `42` | Chuyển thành chuỗi; cần khớp cú pháp số của attribute. |
| `UUID` | `toString()` | Chỉ dùng nếu directory lưu UUID theo cùng định dạng. |
| `Name`/DN | `LdapName.toString()` | Kiểm tra DN đầy đủ/tương đối và matching rule của attribute. |
| `LocalDate`/`Instant` | ISO date/timestamp | Phải thống nhất định dạng LDAP và timezone; không dựa vào locale mặc định. |
| Enum | `ACTIVE` | Định nghĩa rõ giá trị LDAP được lưu, tránh phụ thuộc tên enum khi refactor. |

Với kiểu phức tạp, nên chuyển thành `String` theo định dạng nghiệp vụ đã quy định trước khi gọi repository. Không dùng `toString()` mặc định của một DTO làm giá trị filter.

## 13. Ví dụ đầy đủ: positional và named binding trong cùng repository

```java
package com.example.directory;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends LdapRepository<Person> {

    // Derived query: tham số được gắn theo thuộc tính trong tên method.
    List<Person> findBySurnameAndGivenName(
            String surname, String givenName);

    // Positional: ?0 là tham số thứ nhất, ?1 là tham số thứ hai.
    @Query("(&(objectClass=inetOrgPerson)(sn=?0)(givenName=?1))")
    List<Person> searchByPosition(
            String surname, String givenName);

    // Named: tên tham số được chỉ định tường minh bằng @Param.
    @Query("(&(objectClass=inetOrgPerson)(sn=:surname)(givenName=:givenName))")
    List<Person> searchByName(
            @Param("surname") String familyName,
            @Param("givenName") String firstName);

    // Named binding: tìm theo mail.
    @Query("(&(objectClass=inetOrgPerson)(mail=:emailAddress))")
    Person findOneByEmail(
            @Param("emailAddress") String email);
}
```

Khi gọi:

```java
List<Person> positional =
        repository.searchByPosition("Nguyen", "Alice");

List<Person> named =
        repository.searchByName("Nguyen", "Alice");

Person alice =
        repository.findOneByEmail("alice@example.org");
```

Hai method đầu có thể tạo điều kiện LDAP tương đương, nhưng cách gắn tham số khác nhau. Method `findOneByEmail` chỉ phù hợp nếu email là duy nhất trong phạm vi search; nếu directory trả nhiều entry, kiểu trả về đơn có thể gây lỗi kích thước kết quả. Khi không bảo đảm duy nhất, dùng `List<Person>`.

## 14. Kiểm thử tham số binding

Một unit test chỉ kiểm tra chuỗi filter trong source không chứng minh repository proxy thực sự bind đúng giá trị. Nên có integration test trên directory test với fixture rõ ràng.

### 14.1. Fixture test

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
givenName: Alice
mail: alice@example.org

dn: uid=bob,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: bob
cn: Bob Nguyen
sn: Nguyen
givenName: Bob
mail: bob@example.org
```

Fixture phải được nạp vào **directory test** đã có `dc=example,dc=org` và `ou=people`. Không chạy test seed/ghi trên directory production.

### 14.2. Integration test JUnit 5

```java
package com.example.directory;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class PersonRepositoryQueryBindingIT {
    @Autowired PersonRepository repository;

    @Test
    void positionalAndNamedQueriesBindSameValues() {
        Set<String> positional = repository
                .searchByPosition("Nguyen", "Alice")
                .stream()
                .map(Person::getUid)
                .collect(Collectors.toSet());

        Set<String> named = repository
                .searchByName("Nguyen", "Alice")
                .stream()
                .map(Person::getUid)
                .collect(Collectors.toSet());

        assertEquals(Set.of("alice"), positional);
        assertEquals(positional, named);
    }
}
```

Test giả định profile `test` kết nối tới directory test và fixture đã nạp. Nếu dùng `@Param`, test cũng xác minh mapping giữa tên trong filter và annotation.

### 14.3. Kiểm thử thứ tự và refactor

Với positional binding:

- Kiểm tra tham số thứ nhất thực sự được dùng ở `?0`.
- Kiểm tra tham số thứ hai thực sự được dùng ở `?1`.
- Nếu đổi thứ tự method signature, phải rà soát và cập nhật query.

Với named binding:

- Đổi thứ tự tham số method nhưng giữ nguyên `@Param`.
- Xác nhận filter vẫn bind đúng giá trị.
- Cố ý viết sai tên `:surnameTypo` để xác nhận lỗi cấu hình/query được phát hiện trong khởi tạo hoặc khi thực thi.

### 14.4. Kiểm thử ký tự đặc biệt

Tạo fixture có surname chứa ký tự đặc biệt hợp lệ theo schema, chẳng hạn `O*(Brien)`. Truy vấn bằng tham số string-based:

```java
List<Person> matches =
        repository.findBySurnameAndGivenName(
                "O*(Brien)", "Casey");
```

Kết quả cần phản ánh **giá trị literal**, không diễn giải `*` hoặc dấu ngoặc trong input thành cú pháp filter. Bổ sung input thử nghiệm `*`, `(`, `)`, `\` và chuỗi có wildcard.

Nếu dùng `LdapEncoder.LikeEncoder` để giữ wildcard, test phải xác nhận đó là **hành vi pattern search được chủ ý**, không phải đường bypass encoding.

### 14.5. Kiểm thử khi nâng cấp version

1. Ghi lại version thực tế của `spring-data-ldap` và Spring Data release train.
2. Khởi tạo ApplicationContext để repository query được parse.
3. Chạy cùng fixture cho derived query, positional và named query.
4. Kiểm tra ký tự đặc biệt, SpEL và custom encoder nếu ứng dụng sử dụng.
5. So sánh kết quả thực tế với version cũ; không chỉ dựa vào việc project biên dịch thành công.

## 15. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `No parameter found for name` hoặc lỗi tương tự | Tên `:param` không khớp method parameter/`@Param`. | Kiểm tra tên và khai báo `@Param` rõ ràng. |
| Query trả kết quả rỗng dù fixture tồn tại | Dùng sai chỉ số `?0`/`?1` hoặc đổi thứ tự method mà không sửa filter. | Đối chiếu thứ tự tham số và thêm integration test. |
| Named query không chạy ở version cũ | Artifact chưa hỗ trợ cú pháp named hoặc tài liệu version không cam kết. | Kiểm tra Javadoc đúng version, dùng derived query/positional được hỗ trợ hoặc nâng cấp. |
| Dùng `{0}` trong `@Query` | Nhầm placeholder MessageFormat của `LdapQueryBuilder`. | Dùng `?0` hoặc `:name` trong `@Query` ở phiên bản hỗ trợ. |
| Dùng `?0` trong `LdapQueryBuilder.filter(format, ...)` | Nhầm cú pháp hai API. | Dùng `{0}`/`{1}` cho MessageFormat overload. |
| Filter không tìm thấy chuỗi có dấu `*` | Default encoder escape wildcard thành literal. | Dùng criteria `like` hoặc `LdapEncode(LdapEncoder.LikeEncoder.class)` khi thật sự cần wildcard. |
| Ký tự đặc biệt làm đổi nghĩa filter | Nối raw input hoặc dùng SpEL/property value không encode. | Dùng binding/encoder; kiểm tra Value Expressions riêng. |
| Tên attribute được lấy từ request | Parameter binding chỉ thay **giá trị**, không phải cách an toàn để chọn cấu trúc filter tùy ý. | Dùng allowlist attribute và query builder. |
| Tham số ngày/UUID không match | `toString()` không đúng định dạng schema/matching rule. | Chuẩn hóa thành chuỗi LDAP theo hợp đồng dữ liệu. |
| Một method trả một entity nhưng có nhiều kết quả | Điều kiện query không duy nhất. | Dùng `List` hoặc bổ sung điều kiện duy nhất theo nghiệp vụ/schema. |
| Query compile được nhưng lỗi khi tạo repository | Annotation, tên tham số, version hoặc lookup strategy không phù hợp. | Kiểm tra ApplicationContext startup và dependency thực tế. |
| Filter injection qua username | Nối chuỗi hoặc biểu thức không được encode. | Dùng parameter binding mặc định và test input đặc biệt. |

## 16. Bài tập thực hành

**Bài 1.** Trong `@Query("(sn=?0)(givenName=?1)")`, `?0` tham chiếu tham số nào?

**Đáp án:** Tham số đầu tiên trong method signature, vì positional index bắt đầu từ 0.

**Bài 2.** Một query dùng `:surname` và method có `@Param("surname") String familyName`. Framework bind giá trị nào?

**Đáp án:** Giá trị của `familyName` được gắn vào placeholder `:surname` nhờ `@Param("surname")`.

**Bài 3.** Có thể đổi thứ tự khai báo hai tham số trong method dùng named binding mà không sửa filter không?

**Đáp án:** Có, nếu tên được khám phá hoặc `@Param` vẫn ánh xạ đúng tới từng placeholder. Với positional binding, cần cập nhật thứ tự placeholder tương ứng.

**Bài 4.** `@Query("(sn={0})")` và `LdapQueryBuilder.filter("(sn={0})", surname)` có cùng cú pháp binding không?

**Đáp án:** Không nên giả định như vậy. `@Query` dùng positional `?0` (hoặc named `:name` khi được hỗ trợ). Overload `LdapQueryBuilder.filter(format, params)` dùng `MessageFormat` với `{0}`.

**Bài 5.** Vì sao `@LdapEncode(LdapEncoder.LikeEncoder.class)` không nên gắn vào mọi tham số?

**Đáp án:** Encoder này giữ lại wildcard `*` để tìm kiếm pattern. Nếu mọi input đều được giữ wildcard, ký tự do người dùng nhập có thể thay đổi semantics từ so sánh literal sang tìm kiếm mẫu.

**Bài 6.** Named binding được tài liệu Spring Data LDAP 3.5.8 và 4.1.1 công bố. Có thể tự động khẳng định nó tồn tại trong mọi bản 3.4 hoặc 3.1 không?

**Đáp án:** Không. Phải kiểm tra đúng API/reference của artifact và test tích hợp. Không suy diễn tính năng theo tên framework hoặc version của Spring Framework.

**Bài 7.** Một method dùng `:emailAddress` nhưng tham số Java được biên dịch không lưu tên và không có `@Param`. Có rủi ro gì?

**Đáp án:** Framework có thể không khám phá được tên để bind. Dùng `@Param("emailAddress")` rõ ràng hoặc cấu hình biên dịch lưu tên tham số theo yêu cầu version.

**Bài 8.** Khi dùng SpEL `?#{[0]}`, có thể mặc định rằng input đã được filter-escape giống parameter binding trực tiếp không?

**Đáp án:** Không. Tài liệu Spring Data LDAP cảnh báo giá trị SpEL/property placeholder không tự được encode theo RFC 2254. Phải bảo đảm encoding riêng.

## 17. Ghi nhớ

- **Derived query** bind tham số theo thuộc tính được suy diễn từ tên method; không cần placeholder viết tay.
- Trong `@Query`, **positional binding** dùng `?0`, `?1`, ... và chỉ số bắt đầu từ 0.
- Trong `@Query`, **named binding** dùng `:paramName` ở các phiên bản hỗ trợ; dùng `@Param` để ánh xạ tên rõ ràng.
- Tài liệu Spring Data LDAP 3.5.8 và 4.1.1 ghi rõ cả named và positional binding. Với version cũ hơn, kiểm tra API đúng artifact; không mặc định tính năng mới có mặt.
- `LdapQueryBuilder.filter(format, params)` dùng `MessageFormat` placeholders `{0}`, khác cú pháp `@Query`.
- Tham số được bind là **giá trị**, không phải tên attribute hoặc đoạn cấu trúc filter. Không nối raw input vào filter.
- String-based query parameters có encoding; `@LdapEncode` cho phép thay encoder theo từng tham số. `SpEL` và property placeholders cần xử lý encoding riêng.
- Dùng positional binding cho query ngắn; ưu tiên named binding khi query nhiều tham số hoặc có nguy cơ refactor.
- Kiểm thử cả thứ tự, tên, ký tự đặc biệt, version compatibility và kết quả trên LDAP directory test.

## Tài liệu tham khảo

- [Spring Data LDAP 4.1.1 — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html): derived query, `@Query`, named/positional binding, encoding, SpEL và property placeholders.
- [Spring Data LDAP 3.5.8 — `Query` API](https://docs.spring.io/spring-data/ldap/docs/3.5.8/api/org/springframework/data/ldap/repository/Query.html): cú pháp `?0` và `:someParam` được công bố trong Javadoc.
- [Spring Data LDAP 4.1.1 — `Query` API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/Query.html): API annotation và parameter binding.
- [Spring Data LDAP 4.1.0 — `LdapEncode` API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapEncode.html): encoder theo tham số và mặc định filter encoding.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `LdapQueryBuilder`, criteria và filter format với `MessageFormat`.
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): bật repository, `LdapRepository` và cấu hình `ContextSource`/`LdapTemplate`.
