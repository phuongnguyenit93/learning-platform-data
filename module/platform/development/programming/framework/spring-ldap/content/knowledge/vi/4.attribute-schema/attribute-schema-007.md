# Case-insensitive attribute name và matching rule

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt tính **không phân biệt hoa/thường của tên thuộc tính LDAP** (*attribute type descriptor*) với quy tắc so sánh **giá trị thuộc tính** (*matching rule*).
- Giải thích vai trò của `EQUALITY`, `SUBSTR`, `ORDERING`, `SYNTAX` trong schema và ảnh hưởng của chúng tới LDAP filter.
- Nhận diện `caseIgnoreMatch`, `caseExactMatch`, `caseIgnoreSubstringsMatch` và các matching rule dành cho DN, số hoặc dữ liệu nhị phân.
- Tra cứu schema, viết filter an toàn, ánh xạ thuộc tính bằng `LdapTemplate`/ODM và tránh giả định sai khi dùng API Java.
- Kiểm thử trường hợp khác case, khoảng trắng, Unicode, thuộc tính nhiều giá trị và matching rule đặc thù trên LDAP server thực tế.

Bài thuộc chương **Attribute và schema** của **SPRING_LDAP**. Trong Spring LDAP, các thành phần như `ContextSource`, `LdapTemplate`, `LdapClient` hoặc Object-Directory Mapping (ODM) giúp thao tác với entry, DN, filter và thuộc tính; **chính LDAP server và schema đang áp dụng** mới quyết định cách so khớp giá trị khi truy vấn.

## 1. Cùng một entry, hai loại case khác nhau

Giả sử directory có entry:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
sn: Nguyen
mail: lan@example.org
~~~

Có hai câu hỏi tưởng giống nhau nhưng bản chất khác biệt:

1. `cn`, `CN` và `Cn` có biểu diễn **cùng loại thuộc tính** không?
2. Giá trị `Nguyen Lan` có được coi bằng `nguyen lan` khi tìm kiếm không?

**Câu 1:** Tên mô tả attribute type trong LDAP không phân biệt hoa/thường. Các cách viết `cn`, `CN`, `Cn` cùng nhận diện attribute type `cn`.

**Câu 2:** Phụ thuộc vào **equality matching rule** mà schema gán cho attribute type. Với `cn` thông dụng, quy tắc tương ứng có nguồn gốc `caseIgnoreMatch` nên hai giá trị thường được xem là tương đương; với attribute type khác có `caseExactMatch`, việc thay đổi case có thể làm kết quả khác đi.

~~~mermaid
flowchart TD
    F["Truy vấn (CN=nguyen lan)"]
    F --> T["CN: xác định attribute type<br/>Tên type không phân biệt case"]
    T --> S["LDAP server đọc schema của type"]
    S --> R{"EQUALITY matching rule?"}
    R -->|"caseIgnoreMatch"| I["So khớp giá trị không phân biệt case<br/>theo quy tắc chuẩn bị chuỗi"]
    R -->|"caseExactMatch"| E["So khớp có phân biệt case<br/>theo quy tắc chuẩn bị chuỗi"]
    R -->|"Quy tắc khác / không phù hợp"| O["Áp dụng rule phù hợp hoặc<br/>kết quả không xác định"]
~~~

Đừng nhầm **case-insensitive attribute name** với câu nói “LDAP không phân biệt chữ hoa/chữ thường”. Câu sau quá rộng và dẫn đến lỗi thiết kế.

## 2. Attribute type, tên alias, OID và attribute description

### 2.1. Tên type không phân biệt hoa/thường

Theo mô hình LDAP, mỗi **attribute type** có Object Identifier (OID) và có thể có một hoặc nhiều tên mô tả (*descriptors*). Ví dụ type `commonName` thường được gọi bằng tên `cn`, có OID `2.5.4.3`.

Trong một schema khai báo những tên đó là alias của cùng OID, các biểu diễn:

~~~text
cn
CN
2.5.4.3
~~~

có thể xác định cùng **attribute type**. Sự tương đương giữa tên alias và OID dựa vào **schema**, không phải vào phép đổi chữ thường trong ứng dụng.

Trong khi đó:

~~~text
cn
sn
uid
~~~

là các type khác nhau. Việc các tên đều có thể chứa giá trị chuỗi không khiến chúng trở thành một thuộc tính.

### 2.2. Attribute description có thể chứa option

Một **attribute description** gồm tên/OID của attribute type và có thể kèm option, ví dụ:

~~~text
cn
CN
cn;lang-vi
cn;lang-en
~~~

`cn` và `CN` chỉ khác case của type descriptor. `cn;lang-vi` và `cn;lang-en` dùng cùng type gốc nhưng có **option khác nhau** để mô tả những tập giá trị phù hợp; không được coi chúng là hai tên hoàn toàn có thể thay thế trong mọi thao tác.

Quy tắc phân tích tên type và option không phân biệt case của descriptor, nhưng **ý nghĩa của option vẫn phải được giữ**. Nếu directory hỗ trợ language tags, entry có thể lưu:

~~~ldif
cn;lang-vi: Nguyễn Lan
cn;lang-en: Lan Nguyen
~~~

Ví dụ trên chỉ minh họa attribute description có option; việc hỗ trợ và truy vấn option phụ thuộc LDAP server và schema/capability.

### 2.3. Tên thuộc tính hiển thị từ server có thể khác cách client gửi

Bạn có thể tìm kiếm với `(CN=Nguyen Lan)` và nhận về thuộc tính mang tên `cn`. Việc đổi kiểu chữ hiển thị này không chứng minh hai kết quả khác dữ liệu.

Đừng dùng tên thuộc tính nguyên văn để tạo “khóa duy nhất” trong một `Map<String, ?>` có so sánh case-sensitive, nếu dữ liệu đến từ nhiều nguồn có thể hiển thị `CN`/`cn`. Đồng thời, cũng đừng đơn giản xóa mọi phần sau dấu `;`: option có thể mang ý nghĩa.

## 3. Schema mới là nơi xác định cách so sánh giá trị

Một định nghĩa attribute type trong schema LDAP có thể chứa những thành phần sau:

| Thành phần | Ý nghĩa | Ảnh hưởng khi truy vấn |
| --- | --- | --- |
| `NAME` | Tên/alias mô tả của attribute type | Cho phép tìm type theo descriptor; case của descriptor không tạo type mới |
| `SYNTAX` | Cú pháp/kiểu giá trị được server chấp nhận | Ảnh hưởng cách giải mã, xác thực, truyền và biểu diễn giá trị |
| `EQUALITY` | Matching rule cho so sánh bằng | Điều khiển filter như `(cn=Lan)` |
| `SUBSTR` | Matching rule cho substring | Điều khiển filter như `(cn=*Lan*)` |
| `ORDERING` | Matching rule cho thứ tự | Điều khiển filter như `(attribute>=value)` hoặc `(attribute<=value)` |
| `SINGLE-VALUE` | Ràng buộc entry có tối đa một giá trị thuộc type đó | **Không** có nghĩa giá trị duy nhất trên toàn directory |
| `SUP` | Attribute type cha mà type hiện tại có thể kế thừa đặc tính | Matching rule có thể được kế thừa theo định nghĩa schema |
| `USAGE` | Loại sử dụng thuộc tính, ví dụ user application hoặc operational | Ảnh hưởng cách server quản lý/trả về thuộc tính |

Định nghĩa minh họa (OID bên dưới chỉ dùng trong ví dụ đào tạo, không phải OID để triển khai sản phẩm):

~~~text
( 1.3.6.1.4.1.55555.1.7
  NAME 'projectCode'
  DESC 'Identifier with case-sensitive comparisons'
  EQUALITY caseExactMatch
  SUBSTR caseExactSubstringsMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15
  SINGLE-VALUE )
~~~

`SYNTAX 1.3.6.1.4.1.1466.115.121.1.15` là cú pháp **Directory String**. Ví dụ quy định:

- `projectCode` có giá trị chuỗi theo Directory String syntax.
- Filter equality dùng `caseExactMatch`.
- Filter substring dùng `caseExactSubstringsMatch`.
- Mỗi entry có tối đa một giá trị `projectCode`, nhưng hai entry khác nhau vẫn có thể có cùng project code nếu không có ràng buộc uniqueness riêng.

Lưu ý: OID cho một attribute type tùy chỉnh phải được cấp trong namespace thuộc tổ chức sở hữu; không lấy OID minh họa để đưa thẳng vào hệ thống production.

### 3.1. Các nhóm matching rule phổ biến

| Matching rule | Nhóm giá trị | Đặc tính đáng chú ý |
| --- | --- | --- |
| `caseIgnoreMatch` | Chuỗi | Equality không phân biệt case theo cách chuẩn bị/so sánh chuỗi LDAP |
| `caseExactMatch` | Chuỗi | Equality có phân biệt case; vẫn có quy tắc chuẩn bị chuỗi, không đơn giản là so từng byte |
| `caseIgnoreSubstringsMatch` | Chuỗi | So khớp substring không phân biệt case |
| `caseExactSubstringsMatch` | Chuỗi | So khớp substring có phân biệt case |
| `distinguishedNameMatch` | DN | So sánh RDN/AVA với schema/matching rule của type cấu thành DN |
| `integerMatch` / `integerOrderingMatch` | Số nguyên | So sánh theo giá trị nguyên hoặc quan hệ thứ tự số |
| `booleanMatch` | Boolean | So khớp theo giá trị logic |
| `octetStringMatch` | Dãy octet | So khớp dãy byte theo quy tắc tương ứng |
| `objectIdentifierMatch` | OID và descriptor hợp lệ | So sánh định danh kiểu OID/descriptor theo schema |
| `caseIgnoreIA5Match` | Chuỗi IA5/ASCII phù hợp | Equality không phân biệt case theo quy tắc cho chuỗi IA5 |

Bảng chỉ minh họa các matching rule đã chuẩn hóa; **không có nghĩa mọi server đều hỗ trợ mọi rule hoặc mọi type đều gán đủ các rule**.

Các thuộc tính có tên giống “email”, “user” hoặc “number” cũng không chứng minh rule chúng dùng. Hãy đọc schema thực tế, kể cả khi module Spring LDAP đã có các lớp Java phù hợp để truy cập chúng.

### 3.2. `caseIgnoreMatch` không đồng nghĩa `String.toLowerCase()`

Matching rule cho chuỗi có thể bao gồm các bước chuẩn bị ký tự theo chuẩn LDAP, trong đó có xử lý Unicode, chuẩn hóa dạng ký tự và khoảng trắng. Vì thế:

~~~java
a.toLowerCase().equals(b.toLowerCase())
~~~

không thay thế được kết quả so khớp của server. Phương thức `toLowerCase()` có thể còn chịu tác động locale hoặc quy tắc chuyển chữ khác với LDAP. Dùng `Locale.ROOT` cũng không biến phép so sánh Java thành `caseIgnoreMatch`.

Tương tự, `caseExactMatch` có phân biệt case nhưng **không nhất thiết là byte-for-byte equality**. Hai chuỗi Unicode biểu diễn khác nhau đôi khi được chuẩn hóa theo rule trước khi so sánh. Với giá trị nhị phân, rule kiểu `octetStringMatch` là một trường hợp khác hoàn toàn.

## 4. Equality, substring, ordering và approximate là những phép kiểm tra khác nhau

Xét entry có `cn: Nguyen Lan`. Các filter LDAP có ý nghĩa khác nhau:

~~~ldap
(cn=Nguyen Lan)
(cn=*Lan*)
(cn>=Nguyen)
(cn~=Nguyen Lan)
(cn=*)
~~~

| Filter | Kiểu kiểm tra | Điều kiện để hoạt động đúng |
| --- | --- | --- |
| `(cn=Nguyen Lan)` | Equality | Server dùng equality matching rule của `cn` |
| `(cn=*Lan*)` | Substring | Server cần substring matching rule phù hợp cho `cn` |
| `(cn>=Nguyen)` | Ordering | Cần ordering matching rule phù hợp; không tự suy từ equality |
| `(cn~=Nguyen Lan)` | Approximate | Ngữ nghĩa/phạm vi hỗ trợ phụ thuộc server và matching rule thích hợp |
| `(cn=*)` | Presence | Kiểm tra thuộc tính có giá trị, không so giá trị theo equality rule |

Cùng một attribute type có thể định nghĩa `EQUALITY` và `SUBSTR` khác nhau. Không suy từ việc `(cn=lan)` khớp `Lan` rằng **mọi** truy vấn substring hoặc ordering đều phải có cùng cách xử lý case.

Nếu attribute type không có rule cần thiết, server có thể trả kết quả **Undefined** cho phép đối sánh. Trong phép tìm kiếm, các entry mà filter không đánh giá thành TRUE không được đưa vào tập kết quả; đây không nhất thiết là bằng chứng entry không tồn tại.

### 4.1. Equality là kết quả của server

Giả sử entry có:

~~~ldif
uid: Lan
~~~

Một client gửi:

~~~ldap
(uid=lan)
~~~

Nếu `uid` trong schema áp dụng `caseIgnoreMatch`, filter thường khớp. Nếu đây là attribute type tự định nghĩa với equality rule phân biệt case, có thể không khớp. Việc client gửi `uid` hay `UID` trong **tên type** không quyết định kết quả so sánh `Lan` với `lan`.

### 4.2. Substring phụ thuộc `SUBSTR`

Ví dụ:

~~~ldap
(cn=*LAN*)
~~~

Với `caseIgnoreSubstringsMatch`, kết quả có thể tìm được `cn: Nguyen Lan` dù khác chữ hoa/thường. Với `caseExactSubstringsMatch`, việc thay case có thể khiến không khớp.

Đừng dùng wildcard `*` tùy tiện để mô phỏng case-insensitive equality. `(cn=*LAN*)` nghĩa là **có substring**, không phải so sánh bằng với một chuỗi case-insensitive.

### 4.3. Ordering không phải thứ tự String của Java

Nếu schema cung cấp `ORDERING`, server so sánh bằng matching rule đó. Thứ tự có thể khác `String.compareTo` hoặc sắp xếp theo locale của ứng dụng.

Filter `(employeeNumber>=100)` chỉ có ý nghĩa số học nếu attribute type thực tế sử dụng syntax/rule tương ứng. Một thuộc tính lưu text dạng `"100"` và `"20"` không đương nhiên được so sánh theo số nguyên.

## 5. Filter extensible match và matching rule chỉ định rõ

LDAP filter có cú pháp *extensible match* cho phép chỉ định matching rule hoặc khai báo rằng phép so sánh áp dụng cả thành phần DN:

~~~ldap
(cn:caseExactMatch:=Nguyen Lan)
~~~

Ý tưởng của filter này là yêu cầu dùng `caseExactMatch`, thay vì mặc định theo `EQUALITY` của type. Tuy nhiên:

- Server phải **hỗ trợ** matching rule được chỉ định và cho phép dùng với type/syntax đó.
- Rule có thể được tham chiếu bằng tên hoặc OID trong phạm vi server hiểu.
- Một phép so sánh có thể trở thành Undefined nếu rule không áp dụng được hoặc không được hỗ trợ.
- Không được coi cú pháp extensible match là cách bắt server bỏ qua schema, ACL hay quy tắc chuẩn bị giá trị.

Ví dụ phổ biến khác ở mức khái niệm là yêu cầu khớp DN theo `distinguishedNameMatch` đối với thuộc tính có cú pháp DN; đây không giống cách so sánh chuỗi thường.

**Thực hành mặc định:** đối với nghiệp vụ thông thường, hãy dùng filter equality trên attribute type có schema đúng. Chỉ dùng extensible match khi thật sự cần và đã kiểm tra hỗ trợ trên directory đích.

## 6. Case của tên attribute khác cách so sánh trong Java/JNDI

### 6.1. `BasicAttributes(true)` chỉ cấu hình cách tìm thuộc tính trong bộ chứa ở client

JNDI có `javax.naming.directory.BasicAttributes` với lựa chọn bỏ qua case ở **ID thuộc tính**:

~~~java
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;

Attributes attrs = new BasicAttributes(true);
attrs.put("CN", "Nguyen Lan");

System.out.println(attrs.get("cn").get()); // Nguyen Lan
System.out.println(attrs.get("CN").get()); // Nguyen Lan
~~~

Tham số `true` làm cho bộ chứa `BasicAttributes` tìm **attribute ID** không phân biệt hoa/thường. Nó **không** thay đổi schema hoặc so sánh **giá trị** trên LDAP server. Ví dụ trên không có truy cập mạng.

Nếu dùng `BasicAttributes(false)` hoặc một `Map<String, ?>` thông thường, ứng dụng có thể thấy hành vi tra cứu key khác. Đừng suy từ hành vi collection của Java ra quy tắc equality của directory.

### 6.2. `AttributesMapper` trong `LdapTemplate`

Với một LDAP server chứa entry `uid=lan,ou=people,dc=example,dc=org`:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class DirectoryProfileService {

    private final LdapTemplate ldapTemplate;

    public DirectoryProfileService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String login) {
        EqualsFilter filter = new EqualsFilter("uid", login);

        return ldapTemplate.search(
            "ou=people",
            filter.encode(),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get()
        );
    }
}
~~~

Giả định: các entry được trả về đều có `cn`, context có base `dc=example,dc=org`, tài khoản dùng để tìm kiếm có quyền đọc và server thực sự có thuộc tính `uid` như ví dụ.

Trong đoạn mã:

- `"uid"` là **tên attribute** trong filter; việc thay bằng `"UID"` không yêu cầu đổi schema.
- `login` là **giá trị**; Java không nên tự gọi `toLowerCase()` trước khi tìm kiếm để “bắt chước LDAP”.
- `EqualsFilter` escape các ký tự đặc biệt theo cú pháp **LDAP filter**, giúp giảm nguy cơ filter injection.
- `"cn"` là attribute ID lấy từ kết quả; việc ánh xạ thành `String` không thể hiện hoặc thay đổi equality rule của server.

Nếu thuộc tính có thể vắng mặt, cần kiểm tra `attrs.get("cn") != null` trước khi đọc; cũng cần xử lý giới hạn tìm kiếm và trường hợp nhiều entry khớp.

### 6.3. Đừng lẫn escape giá trị filter với escape DN

Các ký tự có ý nghĩa trong LDAP filter gồm dấu sao `*`, ngoặc tròn, gạch chéo ngược và NUL. Ví dụ, nếu username thực chứa ký tự `*`, ghép chuỗi như:

~~~java
String filter = "(uid=" + login + ")";
~~~

có thể biến giá trị bình thường thành wildcard và thay đổi ý nghĩa truy vấn.

Dùng `EqualsFilter` hoặc `LdapQueryBuilder` với binding/escaping phù hợp. Cú pháp escape DN như `cn=Nguyen\, Lan` giải quyết một vấn đề khác: biểu diễn cấu trúc RDN/DN. Không đem escape DN thay cho escape filter.

## 7. ODM, repository và schema attribute

Khi ánh xạ entry bằng Spring LDAP ODM, annotation `@Attribute` chỉ định tên thuộc tính cần đọc/ghi:

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
    private String login;

    @Attribute(name = "cn")
    private String commonName;

    // Constructor, getters và setters phù hợp với ứng dụng.
}
~~~

Spring Data LDAP có thể đặt repository phía trên ODM, giúp gọi các phương thức truy cập entry. Nhưng `@Attribute(name = "cn")` **không** thay đổi matching rule của `cn`. Nó chỉ nói field Java lấy dữ liệu từ attribute type nào.

Nếu cần một thuộc tính tùy chỉnh có equality phân biệt case, bạn phải cấu hình **schema trên server** thích hợp. Việc đổi Java field thành `String`, thêm setter, hoặc đổi tên field không làm server chuyển `caseIgnoreMatch` sang `caseExactMatch`.

### 7.1. Không đồng nhất schema với validation trong Java

Giả sử một giá trị chỉ được phép lưu theo `Directory String` và type có `SINGLE-VALUE`. Server có thể từ chối thao tác `modify` đưa thêm giá trị thứ hai, dù đối tượng Java có thể chứa `List<String>`.

Ngược lại, một Java DTO có `@NotBlank` chỉ áp dụng các quy tắc validation ở tầng ứng dụng; nó không thay thế LDAP schema. Khi dữ liệu được ghi qua `LdapTemplate`, `LdapClient` hay repository, server vẫn áp dụng syntax, objectClass, ACL và các ràng buộc khác.

## 8. Cách đọc matching rule từ LDAP server

Khi không chắc một thuộc tính có phân biệt case hay không, cách đáng tin cậy là **đọc schema thực tế**. Trong các triển khai LDAP chuẩn, entry có thể trỏ đến subschema entry qua operational attribute `subschemaSubentry`. Đường dẫn và khả năng truy cập có thể khác nhau tùy server.

Một ví dụ minh họa với `ldapsearch`:

~~~bash
# Đọc DN của subschema entry đang áp dụng cho một entry cụ thể.
ldapsearch -LLL \
  -H ldaps://ldap.example.org:636 \
  -D "uid=directory-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s base \
  subschemaSubentry
~~~

Sau khi nhận được DN từ thuộc tính `subschemaSubentry`, có thể truy vấn subschema entry tương ứng (thay `<DN_TRA_VE>` bằng DN thực):

~~~bash
ldapsearch -LLL \
  -H ldaps://ldap.example.org:636 \
  -D "uid=directory-reader,ou=service,dc=example,dc=org" -W \
  -b "<DN_TRA_VE>" -s base \
  attributeTypes matchingRules matchingRuleUse
~~~

Các lệnh trên là hướng dẫn kiểm tra; phải dùng URI, DN và tài khoản phù hợp với directory thực tế. `-W` yêu cầu nhập mật khẩu tương tác; không đưa mật khẩu vào lịch sử shell hoặc command line. Kết nối `ldaps://` cần kiểm tra chứng chỉ TLS; không bỏ xác thực TLS để chạy được ví dụ.

Khi đọc `attributeTypes`, hãy xác định:

1. Attribute type có **OID** và những `NAME` nào?
2. Nó có `EQUALITY`, `SUBSTR`, `ORDERING` trực tiếp hay được kế thừa qua `SUP`?
3. `SYNTAX` là Directory String, DN, Integer, Boolean, octet string hay kiểu khác?
4. Server có hỗ trợ rule dùng trong extensible match và có giới hạn schema/ACL nào không?

Nếu schema không được phép đọc hoặc bị tối giản qua proxy, cần phối hợp quản trị LDAP và thiết kế một bài kiểm thử tích hợp với dữ liệu mẫu có quyền truy cập phù hợp. **Không nên mặc định rule từ tên attribute hoặc từ một bản sao schema của server khác.**

## 9. Các nhầm lẫn ảnh hưởng đến xác thực và phân quyền

| Nhầm lẫn | Tác động | Cách làm đúng |
| --- | --- | --- |
| “Tên attribute không phân biệt case nên password cũng không phân biệt case” | Sai bản chất xác thực, có thể tạo cơ chế đăng nhập không an toàn | Giao việc xác thực mật khẩu cho LDAP bind/Spring Security LDAP |
| `CN` và `cn` là hai trường khác nhau | Đọc/ghi trùng logic hoặc mapping lỗi | Hiểu chúng là descriptor cùng attribute type |
| `cn` và `uid` đều là chuỗi nên so khớp giống nhau | Kết luận sai khi filter theo loại thuộc tính khác nhau | Đọc `EQUALITY` và `SUBSTR` của từng type |
| `caseIgnoreMatch` là lowercase Java | Lỗi Unicode/space/locale, bất đồng server-client | Để server áp dụng matching rule |
| Filter equality khớp thì substring/ordering cũng khớp tương tự | Bỏ qua các rule riêng và khả năng rule không được khai báo | Kiểm tra riêng `EQUALITY`, `SUBSTR`, `ORDERING` |
| `cn;lang-vi` và `cn;lang-en` là cùng attribute description | Mất thông tin option và ngôn ngữ | Giữ chính xác option khi cần truy cập từng tập giá trị |
| `SINGLE-VALUE` ngăn hai entry có cùng email | Giả định uniqueness toàn directory không tồn tại | Cần cơ chế uniqueness/ràng buộc nghiệp vụ riêng |
| Dùng `String.equalsIgnoreCase()` để xét thành viên nhóm | Có thể so DN/entry sai schema và mở rộng quyền | Dùng DN/membership lookup do directory hỗ trợ và kiểm tra authorities trong Spring Security |
| Tự ghép filter với input | Nguy cơ LDAP filter injection | Dùng filter builder và escape theo RFC 4515 |

**Lưu ý về DN-valued attributes:** `member` trong `groupOfNames` thường có DN syntax và dùng quy tắc thích hợp cho DN. Cách so khớp loại dữ liệu này không tương đương với việc so tên hiển thị `cn` bằng `String.equalsIgnoreCase()`. Với phân quyền, ứng dụng còn phải xác định quy tắc chuyển membership thành `GrantedAuthority`.

**Lưu ý về mật khẩu:** Authentication qua LDAP bind kiểm tra thông tin đăng nhập bằng server. Đừng cố đọc `userPassword` bằng repository rồi biến thành string và so sánh hoa/thường tại Java. Ngoài rủi ro bảo mật, schema/ACL và cách lưu giá trị có thể khiến phương pháp đó sai hoàn toàn.

## 10. Kịch bản kiểm thử thực hành

Giả sử LDAP thử nghiệm có schema cho `cn` sử dụng `caseIgnoreMatch` và attribute type minh họa `projectCode` sử dụng `caseExactMatch`. Tạo các entry thử nghiệm hợp lệ theo schema thực tế, rồi kiểm tra:

| Trường hợp | Thao tác | Kỳ vọng cần xác minh |
| --- | --- | --- |
| Tên type khác case | `(cn=Nguyen Lan)` so với `(CN=Nguyen Lan)` | Kết quả khớp tương đương cho cùng attribute type |
| Giá trị khác case trên `cn` | `(cn=Nguyen Lan)` so với `(cn=nguyen lan)` | Theo `caseIgnoreMatch` của schema thử nghiệm |
| Giá trị khác case trên `projectCode` | `(projectCode=Ab7)` so với `(projectCode=ab7)` | Theo `caseExactMatch`; không mặc định khớp |
| Substring | `(cn=*LAN*)` | Theo `SUBSTR` đã khai báo, không tự suy từ `EQUALITY` |
| Filter injection | Input username chứa `*`, `(` hoặc `\` | Filter builder xử lý như giá trị literal, không đổi ý nghĩa truy vấn |
| Unicode/khoảng trắng | Giá trị có dấu, nhiều khoảng trắng, các dạng biểu diễn Unicode | Theo rule thực tế; ghi rõ dữ liệu và kết quả |
| Attribute options | `cn;lang-vi`, `cn;lang-en` | Không làm mất option và không gộp nhầm giá trị |
| Attribute nhiều giá trị | Một entry có nhiều giá trị `cn` | Server so từng giá trị theo rule, không giả định chỉ có một |
| Attribute thiếu ordering | Truy vấn `>=` trên type không có rule phù hợp | Xác minh hành vi server, không suy kết quả từ Java |
| Quyền truy cập | Cùng filter với tài khoản có ACL đọc khác nhau | Phân biệt không khớp do matching rule với hạn chế quyền/visibility |

### Ví dụ: kiểm tra filter builder trong một bài test tích hợp

~~~java
String username = "lan*";
EqualsFilter filter = new EqualsFilter("uid", username);
String encoded = filter.encode();

// Dấu '*' từ username được escape thành literal '*' trong filter LDAP.
// Kết quả phải là truy vấn equality với giá trị "lan*", không phải wildcard.
System.out.println(encoded);
~~~

Để kết luận rằng một entry được tìm thấy hay không, phải chạy `LdapTemplate.search(...)` trên LDAP test server có schema cụ thể. Đoạn Java trên chỉ chứng minh **việc tạo filter an toàn**, không kiểm tra matching rule của directory.

Trong bài kiểm thử tích hợp, nên ghi rõ schema, quyền tài khoản bind, base DN, search scope và TLS. Nếu đang dùng connection pooling, cần bảo đảm test không bị ảnh hưởng bởi context dùng sai danh tính hoặc kết nối không đúng cấu hình.

## 11. Câu hỏi tự kiểm tra

1. Vì sao `(CN=Lan)` và `(cn=Lan)` thường được hiểu là filter trên cùng một attribute type?
2. Tại sao `(projectCode=Ab7)` có thể khác `(projectCode=ab7)`, dù tên `projectCode` có thể viết thành `PROJECTCODE`?
3. Một attribute type có `EQUALITY caseIgnoreMatch` nhưng không khai báo `SUBSTR`. Có thể đảm bảo `(x=*abc*)` hoạt động không?
4. `BasicAttributes(true)` có làm LDAP server thay đổi quy tắc so sánh giá trị hay không?
5. Có thể lấy `String.toLowerCase()` làm chuẩn chung cho mọi dữ liệu LDAP không? Hãy nêu ít nhất hai lý do.
6. Khi mã hóa thao tác đăng nhập trong Spring Security LDAP, ai chịu trách nhiệm kiểm tra mật khẩu và ai quyết định người dùng được quyền truy cập endpoint?
7. Vì sao `cn;lang-vi` và `cn;lang-en` cần được xem xét riêng khi ánh xạ dữ liệu?

**Gợi ý đáp án:** (1) Tên descriptor của type không phân biệt case; (2) case của **giá trị** do `EQUALITY` quyết định; (3) không, `SUBSTR` là rule độc lập; (4) không, chỉ cấu hình một collection JNDI ở client; (5) Unicode/locale, chuẩn bị chuỗi theo matching rule, syntax khác nhau; (6) LDAP bind/server xác thực, Spring Security kiểm soát authorization theo authorities và chính sách ứng dụng; (7) option có thể mô tả các tập giá trị riêng.

## 12. Ghi nhớ

- **Attribute name (descriptor) không phân biệt hoa/thường.** `cn` và `CN` cùng gọi một type; các alias/OID được nhận diện theo schema.
- **Attribute value có so sánh phân biệt hoa/thường hay không là chuyện của matching rule.** Hãy xem `EQUALITY`, `SUBSTR` và `ORDERING` của type.
- **Không tự chuẩn hóa mọi giá trị bằng lowercase trong Java.** LDAP server có quy tắc xử lý Unicode, khoảng trắng, syntax và matching rule riêng.
- **Spring LDAP giúp viết truy vấn và ánh xạ dữ liệu**, nhưng không thay thế schema. Sử dụng `EqualsFilter` hoặc query builder để escape filter, giữ đúng attribute description và kiểm thử trên server.
- **Authentication và authorization là các bước khác nhau.** Quy tắc so sánh thuộc tính không thay thế bind xác thực mật khẩu hay kiểm soát quyền của Spring Security.

### Tài liệu tham khảo

- [RFC 4512 — LDAP: Directory Information Models (attribute type, schema, attribute description)](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517)
- [RFC 4518 — LDAP: Internationalized String Preparation](https://www.rfc-editor.org/rfc/rfc4518)
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4519 — Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519)
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Java `BasicAttributes` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/BasicAttributes.html)
