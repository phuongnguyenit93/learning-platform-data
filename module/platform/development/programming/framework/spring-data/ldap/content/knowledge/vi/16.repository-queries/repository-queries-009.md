# Cơ chế mã hóa tham số và giới hạn của biểu thức động

Khi một repository method nhận email, tên người dùng hoặc từ khóa do người dùng nhập, giá trị đó có thể trở thành một phần của **LDAP search filter**. Nếu ghép trực tiếp chuỗi đầu vào vào filter, ký tự đặc biệt có thể thay đổi cấu trúc điều kiện, làm truy vấn trả về nhiều entry hơn dự kiến hoặc gây **LDAP injection**. Vì vậy cần hiểu rõ framework encode phần nào, biểu thức động nào tự được bảo vệ và phần nào lập trình viên phải kiểm soát.

Trong **Spring Data LDAP**, repository hỗ trợ truy vấn suy ra từ tên method và truy vấn khai báo bằng **@Query**. Với truy vấn chuỗi, tham số bind trực tiếp có cơ chế encoding; annotation **@LdapEncode** cho phép chọn encoder riêng. Tuy nhiên **SpEL** và **Property Placeholder** là Value Expressions, không tự được escape theo quy tắc LDAP filter. **Spring LDAP LdapQueryBuilder** cũng cung cấp cách xây dựng filter có encode giá trị an toàn.

Bài thuộc chương **Truy vấn Repository** của module **SPRING_DATA_LDAP**. Người học sẽ hiểu **RFC 4515**, phân biệt filter-value encoding với DN escaping, sử dụng named/positional parameter, chọn **LdapEncoder**, giới hạn wildcard, kiểm soát biểu thức động, xây dựng truy vấn bằng **LdapQueryBuilder**, bảo vệ attribute/base/scope, và kiểm thử injection cùng các trường hợp Unicode.

> **Nguyên tắc cốt lõi:** Encode **giá trị assertion** theo đúng ngữ cảnh filter. Không encode cả filter như một value, không dùng DN escaping thay cho filter escaping và không cho dữ liệu không tin cậy quyết định attribute, operator, cấu trúc AND/OR, base DN hoặc search scope.

## 1. Vì sao tham số LDAP cần được encode?

LDAP search filter có cú pháp riêng. Ví dụ:

~~~text
(&(objectClass=inetOrgPerson)(mail=linh@example.test))
~~~

Ứng dụng muốn tìm entry theo email. Nếu giá trị được nối trực tiếp vào chuỗi:

~~~java
String filter =
    "(&(objectClass=inetOrgPerson)(mail=" + email + "))";
~~~

thì một giá trị đầu vào có chứa ký tự cú pháp có thể kết thúc assertion hiện tại và chèn điều kiện khác. Ví dụ đầu vào cố ý tạo filter:

~~~text
*)(|(objectClass=*)
~~~

Khi nối chuỗi, filter có thể biến thành:

~~~text
(&(objectClass=inetOrgPerson)(mail=*)(|(objectClass=*)))
~~~

Ý nghĩa truy vấn đã thay đổi: thay vì chỉ tìm mail khớp chính xác, filter có thể chọn rất nhiều entry. Đây là **LDAP injection**. Hậu quả tùy quyền đọc của bind identity và dữ liệu server cho phép truy cập.

### 1.1. Encoding bảo vệ ranh giới cú pháp

Mục tiêu là để dữ liệu đầu vào luôn được hiểu là **một giá trị**, không trở thành toán tử hay nhánh filter mới. Ví dụ ký tự sao literal phải được biểu diễn khác với wildcard substring:

~~~text
Giá trị người dùng nhập:  linh*admin
Filter value đã escape:   linh\2aadmin

Filter:
(uid=linh\2aadmin)
~~~

Server so sánh với giá trị có dấu sao literal trong attribute. Nó không diễn giải dấu sao đó thành wildcard.

### 1.2. Encoding không phải authorization

Một filter được encode đúng vẫn có thể tìm quá rộng nếu ứng dụng chọn base DN hoặc scope không phù hợp. Encoding chỉ bảo vệ cú pháp giá trị; quyền đọc vẫn do **LDAP ACL**, bind identity và authorization của ứng dụng quyết định.

## 2. Quy tắc escaping của LDAP search filter

Biểu diễn chuỗi filter được quy định trong **RFC 4515** (tài liệu Spring Data LDAP hiện hành vẫn gọi encoding tương thích RFC 2254, phiên bản tiền nhiệm của RFC 4515). Trong assertion value, các octet đặc biệt phải được biểu diễn bằng backslash và hai chữ số hex:

| Ký tự/octet | Biểu diễn filter |
| --- | --- |
| Asterisk **\*** | **\2a** |
| Left parenthesis **(** | **\28** |
| Right parenthesis **)** | **\29** |
| Backslash **\\** | **\5c** |
| NUL **0x00** | **\00** |

Ví dụ:

~~~text
Input:
  a*(b)\c

Filter assertion value:
  a\2a\28b\29\5cc

LDAP filter:
  (uid=a\2a\28b\29\5cc)
~~~

Với ký tự Unicode cần escape, RFC 4515 yêu cầu xử lý theo **octet UTF-8** tương ứng, không tùy tiện lấy một ký tự Unicode rồi chuyển thành một mã hex đơn lẻ. Hãy dùng encoder của thư viện thay vì tự viết hàm replace nếu không có yêu cầu đặc biệt.

### 2.1. Wildcard literal và wildcard có chủ đích

Trong filter, dấu sao có thể mang hai nghĩa:

- **Literal asterisk**: một ký tự thực trong giá trị; phải encode thành **\2a**.
- **Substring wildcard**: toán tử wildcard trong filter; được giữ lại có chủ đích ở vị trí pattern.

Không thể phân biệt hai trường hợp chỉ bằng cách nhìn chuỗi input nếu API không quy định pattern contract. Ví dụ tìm chính xác chuỗi **a*b** khác với tìm mọi giá trị bắt đầu bằng **a** và kết thúc bằng **b**.

### 2.2. Không encode hai lần

Nếu giá trị đã được filter-encode rồi lại đưa qua encoder lần nữa, dấu backslash trong chuỗi escape có thể bị encode thành **\5c**. Kết quả filter sẽ tìm một chuỗi khác với mong đợi.

Chọn một tầng chịu trách nhiệm encoding: **repository parameter binding**, **LdapQueryBuilder** hoặc một helper rõ ràng cho Value Expression. Không vừa tự encode trước khi gọi repository vừa dựa vào framework encode lần nữa.

## 3. Phân biệt filter escaping và DN escaping

LDAP filter và Distinguished Name có hai ngữ pháp khác nhau:

| Ngữ cảnh | Chuẩn/tiện ích | Mục đích |
| --- | --- | --- |
| Assertion value trong search filter | RFC 4515; **LdapEncoder.filterEncode(...)** | Giữ dữ liệu bên trong filter value |
| RDN/DN | RFC 4514; **LdapEncoder.nameEncode(...)** hoặc JNDI Name API | Escape tên trong cây directory |
| LDIF attribute value | RFC 2849 | Biểu diễn dữ liệu trong file LDIF |

Ví dụ tên người dùng chứa dấu phẩy:

~~~text
RDN:
uid=linh\,nguyen

Filter tìm attribute uid có giá trị chứa dấu phẩy:
(uid=linh\2cnguyen)
~~~

Hai chuỗi escape khác nhau vì chúng thuộc hai ngữ cảnh khác nhau. Không dùng **nameEncode** để escape assertion value và không dùng **filterEncode** để tạo DN.

Khi cần tạo DN động, ưu tiên **LdapNameBuilder** hoặc JNDI **LdapName/Rdn** để cấu trúc từng RDN. Không ghép DN bằng cách nối chuỗi có input tùy ý.

Nếu assertion value của filter bản thân là một DN (ví dụ giá trị của attribute **member**), có hai lớp ngữ cảnh: trước hết tạo DN hợp lệ bằng Name API/RFC 4514; sau đó encode toàn bộ chuỗi DN như **một filter assertion value** theo RFC 4515. DN escaping bên trong không thay thế filter escaping bên ngoài.

## 4. Hai cách khai báo truy vấn trong Spring Data LDAP

Repository query method thường thuộc một trong hai nhóm:

| Nhóm | Cách định nghĩa | Khi nên dùng |
| --- | --- | --- |
| **Derived query** | Spring phân tích tên method như findByLastnameAndFirstname | Điều kiện phổ biến, có keyword được hỗ trợ |
| **Declared query** | Dùng **@Query** với filter LDAP tường minh | Cần cấu trúc filter tùy chỉnh hoặc điều kiện phức hợp |

Ví dụ derived query:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<Person> {

    List<Person> findByLastname(String lastname);

    List<Person> findByLastnameAndFirstname(
        String lastname,
        String firstname
    );
}
~~~

**LdapRepository** chỉ nhận entity type; ID mặc định là **javax.naming.Name**, vì ODM của Spring LDAP dùng DN làm định danh entry.

Tên method được parse thành các predicate trên property của entity. Ví dụ hai điều kiện có thể tạo filter tương đương:

~~~text
(&(objectclass=person)
  (lastname=Nguyen)
  (firstname=Linh))
~~~

Derived query không phải ngôn ngữ biểu thức tùy ý. Nó chỉ hỗ trợ các property/operator mà Spring Data LDAP triển khai. Khi yêu cầu không khớp keyword hoặc cần kiểm soát filter rõ hơn, dùng **@Query** hoặc **LdapQueryBuilder**.

## 5. Named và positional parameter trong @Query

Spring Data LDAP hỗ trợ hai cách gắn tham số cho filter trong **@Query**:

- **Named parameter**: tên tham số có dấu hai chấm, ví dụ **:emailAddress**.
- **Positional parameter**: chỉ số bắt đầu từ 0, ví dụ **?0**.

Ví dụ named parameter:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository
        extends LdapRepository<Person> {

    @Query("(&(objectClass=inetOrgPerson)(mail=:emailAddress))")
    Optional<Person> findByMail(
        @Param("emailAddress") String emailAddress
    );
}
~~~

Named parameter dễ đọc hơn khi method có nhiều tham số và ít rủi ro khi refactor thứ tự argument.

Ví dụ positional parameter:

~~~java
@Query("(&(objectClass=inetOrgPerson)(sn=?0)(cn=?1))")
List<Person> findBySurnameAndCommonName(
    String surname,
    String commonName
);
~~~

Ở đây **?0** là surname và **?1** là commonName. Khi thêm hoặc đổi thứ tự tham số, cần rà lại query vì vị trí không tự mô tả ý nghĩa.

### 5.1. Tham số bind trực tiếp được encode

Theo tài liệu Spring Data LDAP, tham số của **String-based query** được encode theo quy tắc RFC 2254/RFC 4515. Đây là cơ chế bảo vệ giá trị khi framework thay tham số vào filter string.

Điều đó không có nghĩa query string có thể lấy từ input. **Cấu trúc @Query phải là filter do lập trình viên viết và review**; chỉ giá trị của tham số mới được bind/encode.

### 5.2. Không tự tạo dấu ngoặc hoặc wildcard quanh tham số bằng cách nối chuỗi

Giữ filter template tĩnh và bind value. Nếu cần substring search, chọn operator/encoder được thiết kế cho wildcard thay vì nối user input vào filter hoàn chỉnh.

## 6. @LdapEncode và lựa chọn encoder

**@LdapEncode** cho phép chỉ định encoder cho một tham số query method. Nếu không chỉ định, Spring Data LDAP dùng encoder mặc định dựa trên cơ chế filter encoding tương ứng với helper **org.springframework.ldap.support.LdapEncoder.filterEncode(String)** cho tham số bind trực tiếp trong String-based query.

API **LdapEncoder** của Spring Data LDAP là strategy interface để encode filter value. Những encoder có sẵn gồm:

| Encoder | Ý nghĩa |
| --- | --- |
| **LdapEncoder.filterEncode(...)** (Spring LDAP helper) | Escape giá trị cho filter; encode dấu sao literal |
| **LdapEncoder.LikeEncoder** (Spring Data LDAP) | Escape ký tự đặc biệt nhưng giữ dấu sao để pattern LIKE |
| **LdapEncoder.NameEncoder** (Spring Data LDAP) | Dùng quy tắc name encoding; chỉ dành cho ngữ cảnh DN được thiết kế phù hợp |
| Custom encoder | Quy tắc encoding riêng, phải tự bảo đảm chống injection |

**NameEncoder** dùng quy tắc DN encoding, không phải encoder tổng quát cho mọi filter value. Với một DN được đặt bên trong assertion value, hãy bảo đảm cả DN và lớp filter bên ngoài đều được encode đúng; không chọn NameEncoder chỉ vì giá trị có vẻ giống tên.

Ví dụ giữ wildcard trong query pattern:

~~~java
import org.springframework.data.ldap.repository.LdapEncode;
import org.springframework.data.ldap.repository.LdapEncoder;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

@Query("(&(objectClass=inetOrgPerson)(cn=:pattern))")
List<Person> findByCommonNamePattern(
    @LdapEncode(LdapEncoder.LikeEncoder.class)
    @Param("pattern") String pattern
);
~~~

Nếu truyền **Linh***, encoder giữ wildcard cuối để tìm tên bắt đầu bằng Linh. Các ký tự filter đặc biệt khác vẫn phải được encode.

### 6.1. Wildcard phải là một phần của hợp đồng API

**LikeEncoder** giữ các dấu sao trong giá trị. Vì vậy không đưa chuỗi tùy ý do người dùng nhập vào mà không kiểm tra pattern. Nếu endpoint chỉ cho phép prefix search, hãy tạo pattern ở service từ một chuỗi literal đã xác thực và giới hạn ký tự wildcard theo quy tắc nghiệp vụ.

Ví dụ, API có thể nhận **prefix** và service tự tạo **prefix + "*"**; client không được tự quyết định chèn wildcard ở giữa hoặc đầu chuỗi.

### 6.2. Custom encoder phải có constructor không tham số

Tài liệu Spring Data LDAP yêu cầu implementation của **LdapEncoder** có constructor không tham số để được khởi tạo khi repository khởi tạo. Encoder phải:

- Encode đầy đủ ký tự đặc biệt theo RFC 4515.
- Chỉ giữ wildcard nếu API thực sự cho phép.
- Xử lý null theo hợp đồng framework.
- Không dựa vào mutable state hoặc ThreadLocal.
- Có unit test cho ASCII, Unicode, backslash, NUL và input tấn công.

**@LdapEncode** và strategy **LdapEncoder** có từ Spring Data LDAP **3.5**. Với phiên bản cũ hơn, kiểm tra API đang có và dùng cách xây dựng filter an toàn được hỗ trợ; không copy annotation từ ví dụ phiên bản mới vào dependency cũ.

Không viết encoder tự chế chỉ bằng cách thay **(** và **)**; như vậy vẫn có thể bỏ sót asterisk, backslash hoặc NUL.

## 7. Giới hạn encoding với derived query

Derived query được tạo từ method name và property của entity. Các keyword phổ biến gồm:

| Keyword | Ví dụ | Ý nghĩa filter |
| --- | --- | --- |
| Không có keyword | **findByFirstname(name)** | Equality |
| **StartingWith** | **findByFirstnameStartingWith(name)** | Prefix |
| **EndingWith** | **findByFirstnameEndingWith(name)** | Suffix |
| **Containing** | **findByFirstnameContaining(name)** | Substring |
| **Like** | **findByFirstnameLike(pattern)** | Pattern theo quy tắc keyword của store |
| **Not** | **findByFirstnameNot(name)** | Negation |
| **IsNull / IsNotNull** | **findByFirstnameNull() / findByFirstnameNotNull()** | Attribute absent/present theo semantics query |
| **GreaterThanEqual** | **findByAgeGreaterThanEqual(age)** | So sánh >= |
| **LessThanEqual** | **findByAgeLessThanEqual(age)** | So sánh <= |

**@LdapEncode không áp dụng cho derived query methods.** Không gắn annotation này với kỳ vọng thay encoder của mọi query được suy ra từ tên method. Nếu cần kiểm soát encoder/wildcard chính xác, chuyển sang String-based **@Query** với encoder phù hợp hoặc xây dựng query bằng **LdapQueryBuilder**.

Không suy rộng keyword từ Spring Data JPA sang LDAP. Các operator, kiểu dữ liệu và matching rule phụ thuộc store và schema LDAP. Một method tên hợp lệ ở repository khác chưa chắc được Spring Data LDAP hỗ trợ.

Theo tài liệu Spring LDAP Repositories hiện hành, repository LDAP không hỗ trợ paging và sorting theo cách của các store quan hệ do đặc thù LDAP protocol. Dùng **countLimit/timeLimit** của query để giới hạn một lần search. Với duyệt dữ liệu lớn, dùng API Spring LDAP phù hợp như paged-results control thay vì giả định Pageable của repository sẽ hoạt động.

## 8. SpEL trong @Query: biểu thức không tự escape

Spring Data LDAP cho phép dùng **SpEL Value Expressions** để lấy tham số theo index/tên hoặc gọi bean method. Ví dụ:

~~~java
@Query("(&(objectClass=inetOrgPerson)(mail=?#{[0]}))")
List<Person> findByMailUsingExpression(String mail);
~~~

Giá trị **?#{[0]}** được lấy từ SpEL. **Giá trị do SpEL cung cấp không tự được escape theo RFC 2254/RFC 4515.** Đây là khác biệt quan trọng so với tham số bind trực tiếp như **:mail** hoặc **?0**.

### 8.1. Encode tường minh bên trong expression

Nếu cần SpEL, hãy gọi helper filter encoder trước khi giá trị được đưa vào filter:

~~~java
@Query(
    "(&(objectClass=inetOrgPerson)"
    + "(mail=?#{T(org.springframework.ldap.support.LdapEncoder)"
    + ".filterEncode([0])}))"
)
List<Person> findByMailWithEncodedExpression(String mail);
~~~

Đoạn ví dụ dùng static method **LdapEncoder.filterEncode** của Spring LDAP. Kiểm tra cú pháp expression và phiên bản Spring Data LDAP trong project khi triển khai. Nếu không cần tính năng của SpEL, ưu tiên tham số bind trực tiếp để giảm số điểm phải tự quản lý.

### 8.2. SpEL có thể gọi bean method

SpEL có khả năng truy cập argument và bean method theo cấu hình Value Expressions. Điều đó hữu ích để lấy principal hoặc biến cấu hình, nhưng không biến expression thành một cơ chế parameter binding tự động an toàn. Mọi giá trị cuối cùng đi vào assertion value vẫn phải được encode đúng.

Không cho người dùng gửi nguyên chuỗi SpEL để ứng dụng đánh giá. Expression trong annotation là cấu hình do lập trình viên kiểm soát; input chỉ nên là dữ liệu thuần được đưa qua một hàm xử lý có kiểm soát.

## 9. Property Placeholder: giá trị cấu hình cũng cần kiểm tra

Property Placeholder có thể làm query thay đổi theo cấu hình môi trường:

~~~java
@Query(
    "(&(objectClass=inetOrgPerson)"
    + "(stage=:?${myapp.directory.stage:dev}))"
)
List<Person> findPeopleAtConfiguredStage();
~~~

Giá trị property được resolve từ Spring Environment. Theo tài liệu Spring Data LDAP, giá trị do Property Placeholder cung cấp **không tự được escape theo RFC 2254**.

Property trong file cấu hình có thể được xem là trusted configuration nếu chỉ người vận hành được phép sửa. Tuy nhiên vẫn phải kiểm tra định dạng/allowlist để tránh một giá trị cấu hình vô tình làm hỏng filter hoặc mở rộng truy vấn.

### 9.1. Dùng allowlist cho giá trị cấu hình có tập hữu hạn

Nếu stage chỉ có các giá trị **dev**, **test**, **prod**, hãy chuyển thành enum hoặc kiểm tra với tập hợp cho phép trước khi đưa vào truy vấn. Không dùng property placeholder để nhận dữ liệu request, tenant name hoặc nội dung do người dùng nhập.

### 9.2. Không nhầm property placeholder với parameter binding

Property placeholder được resolve từ Environment khi tạo query; nó không có cùng hợp đồng với tham số method được bind trực tiếp. Đừng dựa vào **@LdapEncode** trên method parameter để nghĩ rằng giá trị placeholder cũng đã được encode.

## 10. LdapQueryBuilder cho filter động an toàn

Khi cần thay đổi điều kiện theo request, **LdapQueryBuilder** thường phù hợp hơn việc ghép filter string. Builder cho phép cấu hình base, scope, attributes, time/count limit trước rồi mới khai báo filter.

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

LdapQuery findPersonByMail(String mail) {
    return query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "mail")
        .countLimit(100)
        .timeLimit(2000)
        .where("objectClass").is("inetOrgPerson")
        .and("mail").is(mail);
}
~~~

Builder encode các giá trị không an toàn trong filter. Nó không yêu cầu service tự escape mail trước khi gọi **is(mail)**.

### 10.1. Filter format có tham số

Nếu cần filter tường minh, dùng overload **filter(String format, Object... params)**:

~~~java
LdapQuery query = query().filter(
    "(&(objectClass=inetOrgPerson)(mail={0}))",
    mail
);
~~~

Overload này dùng **MessageFormat** cho filter template và encode các tham số. Template phải là chuỗi cố định do ứng dụng kiểm soát; chỉ giá trị được truyền trong params là dữ liệu động.

### 10.2. filter(String) không encode

Overload:

~~~java
LdapQuery query = query().filter(
    "(&(objectClass=inetOrgPerson)(mail=" + mail + "))"
);
~~~

không validate hoặc escape chuỗi filter. Spring LDAP cảnh báo không dùng overload **filter(String hardcodedFilter)** với input trực tiếp hoặc chuỗi nối từ input. Chỉ dùng khi toàn bộ filter là literal đáng tin cậy được viết sẵn và review.

Không trộn **filter(...)** với **where(...)** trên cùng builder; API yêu cầu chọn một cách khai báo filter.

## 11. Attribute name và operator không phải tham số value

Encoding tham số chỉ bảo vệ **giá trị assertion**. Nó không biến mọi phần của filter thành tham số an toàn. Ví dụ:

~~~text
(mail={value})
^    ^
|    +-- assertion value có thể được encode
+------- attribute description là cấu trúc filter
~~~

Không viết query nhận tên attribute trực tiếp từ request rồi nối vào filter:

~~~java
import org.springframework.ldap.support.LdapEncoder;

// Không an toàn: attributeName là dữ liệu không tin cậy.
String filter = "(" + attributeName + "="
    + LdapEncoder.filterEncode(value) + ")";
~~~

Filter encoding không xác thực attribute name. Nếu cần cho phép tìm theo nhiều trường, ánh xạ lựa chọn của người dùng qua **allowlist**:

~~~java
enum PersonSearchField {
    EMAIL,
    COMMON_NAME
}

String attributeFor(PersonSearchField field) {
    return switch (field) {
        case EMAIL -> "mail";
        case COMMON_NAME -> "cn";
    };
}
~~~

Service nhận enum đã parse/validate, chọn tên attribute cố định, rồi đưa value vào **LdapQueryBuilder.where(attribute).is(value)**. Không nhận tên attribute LDAP tùy ý từ client.

### 11.1. Operator cũng phải do ứng dụng quyết định

Không cho request gửi chuỗi **=**, **>=**, **~=**, **~** hoặc đoạn **AND/OR/NOT** để chèn trực tiếp vào filter. Chuyển lựa chọn operator thành enum và map sang nhánh builder đã định nghĩa. Ví dụ chỉ cho phép **EXACT**, **PREFIX** hoặc **CONTAINS**; mỗi lựa chọn có một cách tạo query riêng.

### 11.2. Không parameterize được cấu trúc filter bằng value binding

Named/positional parameters trong **@Query** dành cho giá trị, không phải tên attribute, toán tử, dấu ngoặc, search scope hoặc danh sách attribute trả về. Nếu cấu trúc cần thay đổi theo request, dùng code chọn một trong các nhánh query đã kiểm soát hoặc dùng builder để ghép các điều kiện hợp lệ.

## 12. Base DN, search scope và returning attributes cũng cần allowlist

Filter không phải phần duy nhất ảnh hưởng phạm vi dữ liệu. **base DN**, **search scope**, danh sách attribute và giới hạn kết quả quyết định directory subtree nào được tìm và dữ liệu nào được trả về.

| Thành phần | Không nên làm | Cách kiểm soát |
| --- | --- | --- |
| **base DN** | Nhận DN tùy ý từ request | Map tenant/organization ID sang DN đã provision |
| **search scope** | Cho client chọn BASE/ONELEVEL/SUBTREE không giới hạn | Chọn scope theo use case và authorization |
| **attributes** | Cho client yêu cầu mọi attribute, kể cả sensitive | Allowlist attribute trả về |
| **countLimit** | Không giới hạn khi query có thể match toàn subtree | Đặt giới hạn hợp lý |
| **timeLimit** | Cho search chạy vô thời hạn | Đặt deadline phù hợp |
| **controls** | Nhận control OID tùy ý từ client | Chỉ bật control được ứng dụng hỗ trợ |

Annotation **@Query** cũng có các thuộc tính cấu hình **base**, **searchScope**, **countLimit** và **timeLimit**. Base có thể tham gia parameter binding theo API, nhưng giá trị đó là DN chứ không phải filter assertion value: phải kiểm tra DN/tenant theo allowlist và dùng Name API/đúng DN escaping. Search scope là kiểu lựa chọn có giới hạn, không nên lấy chuỗi tùy ý từ client.

Ví dụ query builder ở mục 10 giới hạn base, scope, attributes, count và time. Những giới hạn này giúp kiểm soát tải và giảm nguy cơ vô tình trả về dữ liệu nhạy cảm, nhưng **không thay thế ACL trên LDAP server**.

### 12.1. Tenant DN không được tạo bằng nối chuỗi

Nếu hệ thống multi-tenant, map tenant key sang DN đã được lưu/validate. Không lấy chuỗi tenant từ request rồi ghép vào base DN. Khi phải tạo DN từ một giá trị RDN, dùng **LdapNameBuilder** hoặc JNDI Name API để encode theo đúng DN grammar; đồng thời vẫn kiểm tra tenant có quyền truy cập nhánh đó.

## 13. LIKE, substring search và kiểm soát wildcard

Wildcard hữu ích khi tìm kiếm theo prefix hoặc substring, nhưng có thể làm truy vấn đắt hơn và rộng hơn:

| Nhu cầu | Filter logic | Ví dụ API |
| --- | --- | --- |
| Equality | **(cn=Linh Nguyen)** | **is(value)** |
| Prefix | **(cn=Linh*)** | **StartingWith** hoặc **like** với pattern |
| Suffix | **(cn=*Nguyen)** | **EndingWith** |
| Contains | **(cn=*Linh*)** | **Containing** |
| Presence | **(cn=*)** | **isPresent() / NotNull** |

Với equality, dấu sao trong input phải được escape. Với prefix/contains, wildcard do ứng dụng chủ động thêm vào pattern. Không để user biến mọi truy vấn thành **\*value\*** nếu endpoint chỉ cần equality.

### 13.1. Prefix thường dễ kiểm soát hơn contains

Directory server có thể tối ưu matching rule/index cho equality hoặc prefix tùy cấu hình. Substring filter có wildcard ở đầu có thể làm server phải xét nhiều entry hơn nếu không có index phù hợp. Kiểm tra indexing và query performance trên directory thực tế; không giả định mọi filter đều có chi phí giống nhau.

### 13.2. Giới hạn kích thước và số kết quả

Validate độ dài đầu vào, giới hạn wildcard và đặt **countLimit/timeLimit**. Với directory lớn, cân nhắc paged results và giới hạn số trang. Một filter không bị injection vẫn có thể trở thành công cụ gây quá tải nếu nó cho phép truy vấn rộng liên tục.

## 14. Biểu thức động có giới hạn gì?

Một query method có thể thay đổi **giá trị** ở runtime, nhưng không phải mọi thành phần filter đều là expression parameter. Bảng sau tóm tắt:

| Cơ chế | Có thay giá trị động? | Encoding tự động? | Ghi chú |
| --- | --- | --- | --- |
| Derived query parameter | Có | Theo cơ chế query derivation của store | Không áp dụng custom **@LdapEncode** |
| **@Query** named/positional parameter | Có | Có, theo RFC 2254 cho String-based query | Dùng cho value trực tiếp |
| **@LdapEncode** | Chọn encoder cho parameter trực tiếp | Có, theo encoder đã chọn | Không áp dụng cho derived query hoặc Value Expressions |
| **SpEL Value Expression** | Có thể truy cập argument/bean | **Không** | Phải encode tường minh |
| **Property Placeholder** | Có thể lấy từ Environment | **Không** | Validate/allowlist hoặc encode tường minh |
| **LdapQueryBuilder.where().is(...)** | Có | Có | Phù hợp query động theo value |
| **LdapQueryBuilder.filter(format, params)** | Có | Có cho params | Template phải tĩnh và dùng MessageFormat |
| **LdapQueryBuilder.filter(String)** | Chuỗi filter tùy ý | **Không** | Chỉ dùng literal đáng tin cậy |

### 14.1. Expression không phải prepared statement

LDAP protocol truyền filter đã được tạo thành cấu trúc filter request; nó không có prepared statement giống JDBC. Spring Data LDAP bind/encode tham số ở tầng query builder để giữ đúng ranh giới filter. Không nên mô tả cơ chế này như một statement được LDAP server prepare và bind riêng ở wire protocol.

### 14.2. Biểu thức động không nên chọn quyền truy cập

Không dùng SpEL hoặc property placeholder để chọn DN gốc, attribute nhạy cảm, ACL, bind identity hoặc filter authorization từ input. Những giá trị này là cấu hình/quy tắc bảo mật; chúng phải được xác định bởi ứng dụng và policy, không bởi query string do client điều khiển.

## 15. So sánh ba cách xử lý cùng một email

Giả sử ứng dụng tìm người theo email do người dùng nhập:

### Cách A — repository @Query với named parameter

~~~java
@Query("(&(objectClass=inetOrgPerson)(mail=:mail))")
Optional<Person> findByMail(@Param("mail") String mail);
~~~

Tham số **mail** được bind trực tiếp và encode theo cơ chế String-based query. Đây thường là cách đơn giản nhất khi cấu trúc filter cố định.

### Cách B — SpEL expression

~~~java
@Query(
    "(&(objectClass=inetOrgPerson)"
    + "(mail=?#{T(org.springframework.ldap.support.LdapEncoder)"
    + ".filterEncode([0])}))"
)
Optional<Person> findByMailExpression(String mail);
~~~

Giá trị expression không tự encode. Ở đây code gọi **filterEncode** tường minh. Nếu bỏ lời gọi helper, không được giả định **@LdapEncode** sẽ tự xử lý expression.

### Cách C — LdapQueryBuilder

~~~java
LdapQuery query = query()
    .base("ou=people")
    .where("objectClass").is("inetOrgPerson")
    .and("mail").is(mail);

return ldapTemplate.search(
    query,
    new PersonAttributesMapper()
);
~~~

Builder encode value của điều kiện. Cách này hữu ích khi service cần ghép các predicate theo lựa chọn đã validate.

### 15.1. Nên chọn cách nào?

- Dùng **derived query** cho điều kiện chuẩn, đơn giản và được store hỗ trợ.
- Dùng **@Query** khi filter có cấu trúc cố định và muốn khai báo gần repository method.
- Dùng **LdapQueryBuilder** khi cần ghép predicate động trong code.
- Dùng **SpEL** khi thật sự cần truy cập Value Expression/bean, và encode giá trị expression rõ ràng.
- Dùng **filter(String)** chỉ cho filter literal tĩnh đã review.

## 16. Filter phức hợp AND/OR phải được dựng từ nhánh tin cậy

Ví dụ người dùng có thể chọn tìm theo email hoặc common name. Hãy chuyển lựa chọn thành nhánh query trong code:

~~~java
LdapQuery queryByEmail(String email) {
    return query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("mail").is(email);
}

LdapQuery queryByName(String name) {
    return query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("cn").is(name);
}
~~~

Service quyết định method nào được gọi sau khi kiểm tra enum/permission. Nếu cần OR giữa nhiều predicate, dùng khả năng kết hợp điều kiện của LdapQueryBuilder hoặc dựng một **Filter** object từ các thành phần cố định.

Không nhận nguyên chuỗi filter như **(&(objectClass=*)(|(mail=...)(cn=...)))** từ client. Client chỉ gửi dữ liệu tìm kiếm; ứng dụng quyết định cấu trúc filter.

### 16.1. LdapQueryBuilder không làm mọi chuỗi đầu vào trở nên an toàn

Builder escape **giá trị filter** khi dùng các condition API hoặc filter format có params. Nhưng tên attribute, base DN, scope, query format và control vẫn do caller cung cấp. Nếu caller lấy chúng từ input không tin cậy, cần validate/allowlist riêng.

## 17. Các lỗi encoding và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tìm không thấy chuỗi có dấu sao literal | Asterisk bị encode hoặc bị hiểu nhầm là wildcard | Chọn equality encoder và test literal |
| LIKE không trả kết quả | Default encoder escape asterisk | Dùng LikeEncoder hoặc builder pattern phù hợp |
| Kết quả quá rộng | Wildcard do client điều khiển hoặc filter nối chuỗi | Giới hạn pattern, bind value, review filter |
| Filter invalid syntax | Parenthesis/backslash/NUL không được encode | Dùng filterEncode/builder |
| Search trả về nhiều user | Filter injection hoặc base/scope quá rộng | Kiểm tra filter cuối, base, scope và ACL |
| DN chứa dấu phẩy không đúng | Dùng filterEncode cho DN | Dùng LdapNameBuilder/JNDI Name API |
| SpEL có thể làm đổi filter | Expression value không được escape | Gọi filterEncode tường minh |
| Placeholder làm hỏng filter | Property value chứa ký tự cú pháp | Validate/allowlist và encode theo ngữ cảnh |
| Query sau khi encode hai lần không match | Backslash escape bị escape lần nữa | Chỉ encode đúng một lần |
| Attribute name bị chèn | Dùng input cho tên attribute | Map enum sang allowlist |
| Filter chạy quá lâu | Contains/wildcard đầu chuỗi, base quá rộng | Giới hạn scope, time/count, kiểm tra index |

### 17.1. Đừng log toàn bộ dữ liệu nhạy cảm

Khi debug, ghi query template hoặc một phiên bản đã che assertion value. Không log email, phone, user identifier hoặc giá trị directory nhạy cảm nếu không có nhu cầu và policy phù hợp. Nếu cần điều tra injection, ghi nhận request ID, loại operation và trạng thái validation thay vì lưu nguyên input có thể chứa PII.

## 18. Kiểm thử encoding và LDAP injection

Một unit test cho encoder nên bao gồm các trường hợp:

| Input | Điều cần xác minh |
| --- | --- |
| **alice** | Giá trị bình thường không đổi không cần thiết |
| **a*b** | Asterisk literal được escape ở equality |
| **a(b)** | Hai dấu ngoặc được escape |
| **a\b** | Backslash được escape |
| Chuỗi có NUL | NUL được biểu diễn theo RFC 4515 hoặc bị từ chối đúng hợp đồng |
| Tiếng Việt/Unicode | Giá trị round-trip đúng |
| ***)(|(objectClass=*)** | Không thể thoát khỏi assertion value |
| Chuỗi rất dài | Bị giới hạn theo policy ứng dụng |
| Pattern có wildcard | Chỉ giữ wildcard được API cho phép |

### 18.1. Kiểm thử repository trực tiếp

Trong integration test với LDAP server riêng:

1. Tạo entry fixture có mail literal chứa ký tự đặc biệt nếu schema/test server cho phép.
2. Gọi repository method bằng chuỗi có **\***, ngoặc và backslash.
3. Xác nhận chỉ entry khớp chính xác được trả về.
4. Gọi method bằng payload injection mẫu.
5. Xác nhận query không trả về toàn bộ subtree hoặc entry ngoài tiêu chí.
6. Kiểm tra các phương thức SpEL/placeholder có helper encoding đúng.
7. Kiểm tra LIKE với pattern hợp lệ và pattern bị từ chối theo allowlist.

### 18.2. Test generated filter và test server

Unit test encoder giúp kiểm tra byte/chuỗi escape, nhưng integration test mới xác nhận LDAP server diễn giải filter đúng. Khi có thể, test cả:

- Chuỗi filter đã dựng ở tầng framework.
- Kết quả thực tế từ server.
- Base DN và scope.
- Search count/time limit.
- ACL của bind identity.

Không chỉ assert chuỗi filter nội bộ rồi kết luận đã chống injection; cần chứng minh payload không thay đổi phạm vi kết quả.

### 18.3. Fuzz test có kiểm soát

Có thể sinh chuỗi chứa các ký tự **\0**, **\***, **(**, **)**, **\\**, Unicode, ký tự kết hợp và chuỗi dài để kiểm tra encoder. Chạy fuzz trong test riêng, không dùng directory production hoặc tài khoản thật vì payload có thể tạo truy vấn rộng và tải lớn.

## 19. Checklist thiết kế repository query

~~~text
[ ] Query template do ứng dụng kiểm soát, không lấy nguyên filter từ request
[ ] Giá trị bind trực tiếp dùng named/positional parameter
[ ] SpEL values được filterEncode tường minh
[ ] Property placeholders được validate/allowlist và encode nếu cần
[ ] @LdapEncode chỉ dùng cho trực tiếp bound parameter của String query
[ ] LikeEncoder chỉ giữ wildcard theo hợp đồng API
[ ] Derived query dùng keyword được Spring Data LDAP hỗ trợ
[ ] Attribute name được map từ allowlist/enum
[ ] Operator AND/OR/NOT do ứng dụng dựng
[ ] Base DN và search scope được giới hạn theo authorization
[ ] Returning attributes không chứa dữ liệu nhạy cảm không cần thiết
[ ] Count/time limit phù hợp với use case
[ ] Không double-encode filter value
[ ] DN escaping và filter escaping không bị trộn
[ ] Unit test encoder và integration test LDAP injection đã chạy
[ ] ACL LDAP vẫn được cấu hình độc lập với encoding
~~~

## 20. Bài thực hành, câu hỏi ôn tập và ghi nhớ

### 20.1. Bài thực hành

Tạo **PersonRepository** cho directory lab và thực hiện:

1. Viết derived query tìm theo surname, firstname và email.
2. Viết **@Query** với named parameter và positional parameter; so sánh khả năng đọc khi refactor.
3. Tìm entry có email chứa ký tự **+**, **\*** hoặc dấu ngoặc trong dữ liệu fixture.
4. Viết một test chứng minh filter literal **\*** và substring wildcard có kết quả khác nhau.
5. Thử payload ***)(|(objectClass=*)** với code nối chuỗi trong test cô lập; quan sát filter bị thay đổi.
6. Thay code nối chuỗi bằng **@Query** direct binding và xác minh kết quả.
7. Tạo method dùng **@LdapEncode(LdapEncoder.LikeEncoder.class)** cho prefix/contains pattern; thêm validation giới hạn wildcard.
8. Tạo method dùng SpEL; trước tiên quan sát rằng expression không tự escape, sau đó thêm **LdapEncoder.filterEncode**.
9. Tạo query dùng property placeholder và xác minh giá trị config được allowlist.
10. Dựng cùng điều kiện bằng **LdapQueryBuilder.where().is(...)** và **filter(format, params)**.
11. Viết enum search field và map sang allowlist attribute; từ chối tên attribute tùy ý.
12. Giới hạn base DN, scope, attributes, countLimit và timeLimit.
13. Viết integration test cho Unicode, NUL, backslash, dấu ngoặc và payload injection.
14. Viết ghi chú ngắn nêu rõ phiên bản Spring Data LDAP đang dùng và API encoding có sẵn trong phiên bản đó.

### 20.2. Câu hỏi ôn tập

1. Vì sao nối chuỗi user input vào LDAP filter có thể gây LDAP injection?
2. RFC 4515 yêu cầu escape những octet đặc biệt nào?
3. Vì sao asterisk literal khác substring wildcard?
4. Filter escaping khác DN escaping ở điểm nào?
5. Named parameter và positional parameter trong @Query có cú pháp ra sao?
6. Tham số bind trực tiếp của String-based @Query được encode như thế nào?
7. @LdapEncode có áp dụng cho derived query không?
8. Vì sao default filter encoder có thể ảnh hưởng LIKE query?
9. LikeEncoder giữ lại ký tự nào và cần giới hạn input ra sao?
10. Vì sao SpEL và Property Placeholder không tự được escape?
11. Làm thế nào gọi filterEncode trong SpEL?
12. Khác biệt giữa filter(String) và filter(String, Object... params) của LdapQueryBuilder?
13. Vì sao không thể dùng value parameter để thay attribute name hoặc operator?
14. Base DN, search scope và returning attributes ảnh hưởng phạm vi dữ liệu thế nào?
15. Làm sao chứng minh integration test đã chặn payload LDAP injection?

### 20.3. Ghi nhớ

**LDAP filter là một ngôn ngữ có cú pháp riêng.** Dữ liệu người dùng phải được giữ trong assertion value bằng escaping theo **RFC 4515**. Spring Data LDAP hỗ trợ named/positional parameter trong **@Query**; tham số bind trực tiếp của String-based query được encode. **@LdapEncode** cho phép chọn encoder cho tham số trực tiếp, nhưng không áp dụng cho derived query hoặc Value Expressions. SpEL và Property Placeholder không tự escape, vì vậy cần encode tường minh hoặc dùng allowlist.

**LdapQueryBuilder.where().is(...)** và **filter(format, params)** giúp xây dựng filter động có encode giá trị; **filter(String)** không validate/escape. Wildcard phải được giữ lại có chủ đích; attribute name, operator, base DN, scope, returning attributes và controls phải do ứng dụng kiểm soát. Cuối cùng, filter encoding không thay thế ACL, authorization, giới hạn truy vấn và integration test trên directory thật.

## Tài liệu tham khảo

- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html): derived queries, @Query, named/positional binding, parameter encoding, @LdapEncode, SpEL và property placeholders.
- [Spring Data LDAP — LdapEncode API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapEncode.html): phạm vi parameter encoding và giới hạn Value Expressions.
- [Spring Data LDAP — LdapEncoder API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapEncoder.html): encoder strategy, LikeEncoder và NameEncoder.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): LdapQueryBuilder, filter criteria và hardcoded filters.
- [Spring LDAP — LdapQueryBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html): filter(String), filter(format, params), where, base, scope và limits.
- [Spring LDAP — LdapEncoder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapEncoder.html): filterEncode và nameEncode.
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): cú pháp filter và escaping assertion values.
- [RFC 4514 — LDAP Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html): biểu diễn và escaping DN/RDN.
- [OWASP — LDAP Injection](https://owasp.org/www-community/attacks/LDAP_Injection): rủi ro và cách phòng chống LDAP injection.
- [CodeQL — Java LDAP Injection](https://codeql.github.com/codeql-query-help/java/java-ldap-injection/): phát hiện việc ghép user input vào LDAP query và khuyến nghị dùng helper/builder.
