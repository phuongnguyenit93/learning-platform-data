# Đối chiếu schema của máy chủ trước khi thiết kế lớp Java

Khi xây dựng ứng dụng bằng **Spring Data LDAP**, ta thường bắt đầu bằng một lớp Java như `Person`, `Group` hoặc `Organization` rồi dùng `@Entry`, `@Attribute` và `LdapRepository` để ánh xạ nó sang directory. Nhưng LDAP không có một mô hình bảng cố định giống cơ sở dữ liệu quan hệ. Mỗi máy chủ công bố **schema** riêng, quy định entry nào được phép tồn tại, thuộc tính nào bắt buộc, giá trị có kiểu gì, được phép có bao nhiêu giá trị và so sánh theo quy tắc nào.

Vì vậy, trước khi thiết kế entity, cần **đối chiếu schema thực tế của máy chủ**. Một field Java kiểu `String` có thể không phù hợp nếu thuộc tính LDAP là DN, dữ liệu nhị phân hoặc nhiều giá trị. Một field đơn trị có thể làm mất dữ liệu nếu schema cho phép nhiều giá trị. Một filter tưởng như đúng có thể không hoạt động như mong đợi nếu matching rule của attribute không phải kiểu so sánh mà lập trình viên giả định.

Bài học đi từ khám phá Root DSE và subschema, đọc định nghĩa `attributeType`/`objectClass`, hiểu syntax và matching rule, so sánh OpenLDAP với Active Directory, rồi ánh xạ schema sang Java bằng **Spring LDAP ODM** và Spring Data LDAP repository.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của schema trong việc kiểm soát entry LDAP.
- Khám phá naming context, thông tin máy chủ và subschema qua **Root DSE**.
- Đọc các định nghĩa `attributeTypes`, `objectClasses`, `matchingRules` và `ldapSyntaxes`.
- Phân biệt `MUST`, `MAY`, `SUP`, `STRUCTURAL`, `AUXILIARY` và `SINGLE-VALUE`.
- Đối chiếu syntax OID, equality/ordering/substring matching rule với kiểu Java.
- Phát hiện các thuộc tính nhiều giá trị, DN-valued, binary và operational trước khi viết entity.
- Hiểu khác biệt schema giữa OpenLDAP, Active Directory và các LDAP server khác.
- Dùng `@Entry`, `@Id`, `@Attribute`, `@DnAttribute`, `@Transient` để ánh xạ ODM.
- Thiết kế repository, filter và thao tác CRUD dựa trên schema thực tế.
- Viết integration test để phát hiện schema mismatch trước khi triển khai.

## 2. Schema LDAP quyết định điều gì?

Schema là tập định nghĩa mà directory dùng để kiểm tra và diễn giải dữ liệu. Có thể xem schema là **hợp đồng dữ liệu của máy chủ LDAP**.

| Thành phần | Câu hỏi nó trả lời |
| --- | --- |
| **Attribute type** | Thuộc tính tên gì, có OID nào, syntax nào, matching rule nào, có được nhiều giá trị không? |
| **Object class** | Entry thuộc loại đối tượng nào, phải có thuộc tính gì và được phép có thuộc tính gì? |
| **Syntax** | Giá trị có cấu trúc/kiểu dữ liệu nào: chuỗi, DN, số nguyên, thời gian, octet hay kiểu khác? |
| **Matching rule** | Server so sánh hai giá trị như thế nào: không phân biệt hoa thường, phân biệt hoa thường, so sánh DN, số hoặc substring? |
| **Content rule / name form** | Có ràng buộc bổ sung nào về cấu trúc entry và thuộc tính dùng để đặt tên không? |

Ví dụ một entry người dùng:

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
mail: alice@work.example.org
```

Entry trên cho ta một số thông tin:

- `dn` là danh tính phân biệt của entry trong cây directory.
- `objectClass` khai báo các lớp mà entry tuân theo.
- `cn` và `sn` là các thuộc tính bắt buộc theo lớp `person` trong schema chuẩn.
- `mail` có thể chứa nhiều giá trị nếu định nghĩa attribute type cho phép.
- `uid` là attribute có thể có nhiều giá trị theo định nghĩa chuẩn; không nên mặc định mọi directory chỉ lưu một `uid`.

Java entity chỉ nên được thiết kế sau khi xác minh các giả định này trên **máy chủ và naming context mục tiêu**.

## 3. Phân biệt schema với dữ liệu thực tế

Ba khái niệm cần tách biệt:

1. **Schema definition:** định nghĩa một attribute type hoặc object class có thể được dùng như thế nào.
2. **Entry data:** các giá trị thực tế đang lưu trong directory.
3. **Application model:** cách ứng dụng biểu diễn dữ liệu đó trong Java.

Ví dụ:

| Lớp | Ví dụ |
| --- | --- |
| Schema | `mail` là thuộc tính chuỗi, có thể có nhiều giá trị. |
| Entry | Alice hiện có hai giá trị `mail`. |
| Java | `Set<String> mailAddresses` có thể biểu diễn các giá trị hiện có. |

Schema cho phép nhiều giá trị **không có nghĩa mọi entry đều phải có nhiều giá trị**. Một entry có thể không có giá trị nào của thuộc tính `MAY`, có một giá trị hoặc nhiều giá trị tùy định nghĩa. Ngược lại, nếu Java field là `String` đơn trị nhưng directory có nhiều giá trị, mapper có thể không biểu diễn được đầy đủ dữ liệu.

Schema cũng không phải danh sách mọi giá trị đang có trong directory. Muốn biết một entry cụ thể có thuộc tính nào, cần đọc entry đó; muốn biết thuộc tính được phép và có kiểu gì, cần đọc schema.

## 4. Khám phá máy chủ qua Root DSE

**Root DSE** là entry đặc biệt ở gốc của máy chủ LDAP. Nó không thuộc một naming context thông thường và cung cấp thông tin về máy chủ, naming context, khả năng hỗ trợ và đôi khi là vị trí subschema.

Các thuộc tính thường hữu ích:

| Thuộc tính Root DSE | Ý nghĩa |
| --- | --- |
| `namingContexts` | Các naming context mà server cung cấp. |
| `subschemaSubentry` | DN của subschema entry được dùng để khám phá định nghĩa schema, nếu server công bố. |
| `supportedLDAPVersion` | Phiên bản LDAP server hỗ trợ. |
| `supportedControl` | Các control server hỗ trợ. |
| `supportedExtension` | Các extended operation server hỗ trợ. |
| `vendorName`, `vendorVersion` | Thông tin nhà cung cấp/phiên bản nếu server công bố. |
| `defaultNamingContext` | Thuộc tính thường gặp trên Active Directory, chỉ naming context mặc định của domain. |
| `schemaNamingContext` | Thuộc tính Active Directory trỏ tới naming context chứa schema objects. |
| `configurationNamingContext` | Naming context cấu hình của Active Directory. |

Không phải mọi server đều cung cấp toàn bộ các thuộc tính này. Đặc biệt, `defaultNamingContext` và `schemaNamingContext` là các thuộc tính thường thấy trong Active Directory, không phải tên thay thế portable cho `namingContexts`.

### 4.1. Đọc Root DSE bằng ldapsearch

Ví dụ dùng OpenLDAP command-line client:

```bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=directory-reader,ou=services,dc=example,dc=org" \
  -W \
  -b "" \
  -s base \
  "(objectClass=*)" \
  namingContexts subschemaSubentry supportedLDAPVersion \
  supportedControl supportedExtension vendorName vendorVersion
```

Giải thích:

- `-x` dùng simple authentication.
- `-H` chỉ endpoint LDAP; ví dụ dùng LDAPS để bảo vệ kết nối.
- `-D` là bind DN của tài khoản được phép đọc thông tin cần thiết.
- `-W` yêu cầu nhập password tương tác.
- `-b "" -s base` truy vấn chính Root DSE.
- `(objectClass=*)` chọn entry Root DSE.
- Danh sách cuối giới hạn các thuộc tính cần đọc.

Quyền đọc Root DSE và các thuộc tính operational phụ thuộc server/policy. Nếu không có quyền anonymous read, dùng một tài khoản có quyền đọc tối thiểu. Không đưa password thật vào shell history hoặc tham số dòng lệnh.

### 4.2. Đọc naming context của Active Directory

Ví dụ:

```bash
ldapsearch -x \
  -H ldaps://dc.example.org:636 \
  -D "CN=Directory Reader,OU=Services,DC=example,DC=org" \
  -W \
  -b "" \
  -s base \
  "(objectClass=*)" \
  defaultNamingContext schemaNamingContext \
  configurationNamingContext subschemaSubentry
```

Kết quả giúp xác định:

- Domain naming context chứa người dùng/nhóm.
- Schema naming context chứa các schema object của AD.
- Configuration naming context chứa cấu hình forest.
- Subschema entry mà server công bố.

Không hardcode các DN này trong code dùng chung cho mọi directory. Hãy xem chúng là cấu hình theo môi trường hoặc metadata được khám phá khi triển khai.

## 5. Tìm subschema entry và đọc định nghĩa schema

LDAP dùng **subschema subentry** để công bố các định nghĩa schema áp dụng cho một phần của cây directory. RFC 4512 định nghĩa thuộc tính `subschemaSubentry` để trỏ tới subschema entry kiểm soát một entry có thể sửa đổi.

Quy trình:

1. Đọc Root DSE để tìm `subschemaSubentry` nếu có.
2. Nếu cần xác định schema cho một entry cụ thể, đọc chính entry đó và yêu cầu thuộc tính `subschemaSubentry` một cách tường minh.
3. Dùng DN đã khám phá để truy vấn subschema entry với base scope.
4. Đọc các thuộc tính schema cần thiết như `attributeTypes`, `objectClasses`, `matchingRules`, `matchingRuleUse` và `ldapSyntaxes` nếu server công bố.

Không mặc định mọi server đều có DN `cn=Subschema` hoặc cho phép mọi client đọc mọi định nghĩa. **Dùng DN server công bố** thay vì đoán.

### 5.1. Đọc subschema của một entry

Ví dụ:

```bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=directory-reader,ou=services,dc=example,dc=org" \
  -W \
  -b "uid=alice,ou=people,dc=example,dc=org" \
  -s base \
  "(objectClass=*)" \
  subschemaSubentry objectClass uid cn sn mail
```

Nếu kết quả cho biết:

```text
subschemaSubentry: cn=Subschema
```

thì có thể đọc entry đó:

```bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=directory-reader,ou=services,dc=example,dc=org" \
  -W \
  -b "cn=Subschema" \
  -s base \
  "(objectClass=subschema)" \
  attributeTypes objectClasses matchingRules matchingRuleUse ldapSyntaxes
```

`cn=Subschema` ở đây chỉ là **ví dụ giá trị đã khám phá**, không phải DN chuẩn bắt buộc cho mọi LDAP server.

Theo RFC 4512, client đọc thuộc tính của subschema entry bằng base-object search với filter `(objectClass=subschema)`. Một số server/proxy có cách biểu diễn hoặc quyền truy cập riêng; nếu không nhận được thuộc tính mong đợi, kiểm tra tài liệu nhà cung cấp và schema naming context tương ứng.

### 5.2. Những thuộc tính schema cần đọc

| Thuộc tính trên subschema entry | Chứa gì? |
| --- | --- |
| `attributeTypes` | Định nghĩa các attribute type. |
| `objectClasses` | Định nghĩa các object class. |
| `matchingRules` | Định nghĩa matching rule. |
| `matchingRuleUse` | Cho biết matching rule có thể áp dụng cho attribute type nào. |
| `ldapSyntaxes` | Mô tả các syntax được server công bố. |
| `dITContentRules` | Ràng buộc bổ sung cho DIT content theo schema. |
| `nameForms`, `dITStructureRules` | Quy tắc về cấu trúc tên và cây directory nếu server hỗ trợ. |

Các thuộc tính schema này thường là operational attributes; khi dùng `ldapsearch` cần yêu cầu rõ tên. Không nên giả định search mặc định trả chúng như thuộc tính user thông thường.

## 6. Phân tích định nghĩa attribute type

Một attribute type definition có thể có dạng:

```text
attributeTypes: (
  2.16.840.1.113730.3.1.3
  NAME 'employeeNumber'
  DESC 'Numerical identifier assigned to an employee'
  EQUALITY caseIgnoreMatch
  SUBSTR caseIgnoreSubstringsMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15
  SINGLE-VALUE
)
```

Đây là ví dụ minh họa cấu trúc schema. Định nghĩa thực tế phải lấy từ server mục tiêu; không copy OID hoặc thuộc tính ví dụ thành schema production nếu chưa xác minh nguồn gốc.

Các thành phần quan trọng:

| Thành phần | Ý nghĩa |
| --- | --- |
| OID | Định danh số duy nhất của attribute type. |
| `NAME` | Descriptor dùng trong LDAP filter/entry, ví dụ `employeeNumber`. |
| `DESC` | Mô tả cho quản trị viên và người phát triển. |
| `SUP` | Attribute type cha mà attribute này kế thừa. |
| `EQUALITY` | Matching rule dùng để so sánh bằng. |
| `ORDERING` | Matching rule dùng cho so sánh thứ tự. |
| `SUBSTR` | Matching rule dùng cho substring filter. |
| `SYNTAX` | Syntax OID quy định dạng dữ liệu. |
| `SINGLE-VALUE` | Attribute type chỉ được chứa tối đa một giá trị trên một entry. |
| `NO-USER-MODIFICATION` | Không cho người dùng thông thường sửa giá trị. |
| `USAGE` | Phân loại cách sử dụng, ví dụ userApplications hoặc directoryOperation. |

### 6.1. OID và tên thuộc tính

Tên `employeeNumber` giúp code dễ đọc, còn OID là định danh kỹ thuật. Một attribute có thể có nhiều descriptor/alias cùng tham chiếu một OID.

Khi thiết kế Java:

- Dùng tên attribute thực tế server chấp nhận trong `@Attribute(name = "...")`.
- Không giả định alias có thể dùng ở mọi server hoặc mọi API.
- Khi kiểm tra schema giữa môi trường, so sánh OID và các thuộc tính quan trọng, không chỉ so tên hiển thị.
- Với custom attribute, tổ chức cần OID arc được cấp hợp lệ (thường dựa trên Private Enterprise Number); không tự dùng một OID tùy ý có thể xung đột với tổ chức khác.

### 6.2. `SUP` và kế thừa attribute

Một attribute type có thể kế thừa từ attribute type khác. Khi đọc schema, hãy xem cả định nghĩa cha:

```text
customEmployeeCode
    SUP employeeNumber
        SUP name
```

Các thuộc tính như syntax/matching rule có thể được kế thừa theo quy tắc schema. Không chỉ đọc dòng định nghĩa trực tiếp rồi kết luận attribute thiếu syntax hoặc equality rule.

## 7. Syntax và matching rule không phải một

**Syntax** quy định giá trị có dạng dữ liệu nào. **Matching rule** quy định server so sánh giá trị ra sao. Hai khái niệm liên quan nhưng không thể thay thế nhau.

Ví dụ:

| Syntax / ví dụ | OID | Kiểu Java thường cân nhắc | Lưu ý |
| --- | --- | --- | --- |
| Directory String | `1.3.6.1.4.1.1466.115.121.1.15` | `String` | Chuỗi Unicode; matching rule quyết định xử lý hoa thường/khoảng trắng. |
| Distinguished Name (DN) | `1.3.6.1.4.1.1466.115.121.1.12` | `Name` | Parse DN theo cấu trúc; không xử lý như chuỗi tùy ý. |
| Integer | `1.3.6.1.4.1.1466.115.121.1.27` | `Integer`/`Long` | Kiểm tra miền giá trị và converter. |
| Generalized Time | `1.3.6.1.4.1.1466.115.121.1.24` | `String` hoặc kiểu thời gian có converter | Phải xử lý timezone và độ chính xác. |
| Octet String | `1.3.6.1.4.1.1466.115.121.1.40` | `byte[]` | Dữ liệu nhị phân, không nên chuyển tùy tiện thành chuỗi. |
| JPEG | `1.3.6.1.4.1.1466.115.121.1.28` | `byte[]` | Ví dụ ảnh; kiểm tra giới hạn kích thước và quyền đọc. |

### 7.1. Matching rule ảnh hưởng truy vấn

Một attribute string có thể dùng:

- `caseIgnoreMatch`: so sánh không phân biệt hoa thường theo quy tắc chuẩn hóa.
- `caseExactMatch`: so sánh có phân biệt hoa thường.
- `caseIgnoreSubstringsMatch`: so sánh substring không phân biệt hoa thường.
- `caseExactSubstringsMatch`: so sánh substring có phân biệt hoa thường.
- `distinguishedNameMatch`: so sánh DN theo cấu trúc DN, không chỉ chuỗi văn bản.
- `integerMatch`: so sánh giá trị số nguyên theo syntax/matching rule tương ứng.

Ví dụ nếu `uid` dùng `caseIgnoreMatch`, filter:

```ldap
(uid=ALICE)
```

có thể khớp giá trị `alice` theo matching rule. Nhưng không nên viết code Java giả định mọi attribute string đều không phân biệt hoa thường. Hãy kiểm tra schema của từng attribute.

### 7.2. Matching rule ảnh hưởng cả filter và update

Matching rule được dùng trong search/compare, và có thể ảnh hưởng việc server nhận diện hai giá trị là tương đương khi thêm/xóa giá trị. Ví dụ một attribute có equality rule không phân biệt hoa thường có thể coi `Alice` và `alice` là cùng giá trị.

Do đó, Java `Set<String>` sử dụng so sánh chuỗi phân biệt hoa thường theo mặc định có thể khác semantics của LDAP server. Nếu nghiệp vụ cần đối chiếu trùng lặp chính xác, cần xác định matching rule và quy tắc chuẩn hóa ở tầng ứng dụng.

## 8. Phân tích object class

Một object class định nghĩa loại entry và tập thuộc tính được yêu cầu/cho phép. Ví dụ:

```text
objectClasses: (
  2.16.840.1.113730.3.2.2
  NAME 'inetOrgPerson'
  SUP organizationalPerson
  STRUCTURAL
  MAY ( audio $ businessCategory $ displayName $
        employeeNumber $ employeeType $ givenName $
        mail $ manager $ mobile $ uid )
)
```

Đây là cấu trúc minh họa; danh sách thuộc tính cụ thể phải đối chiếu schema server và phiên bản RFC/extension được triển khai.

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| OID | Định danh số duy nhất của object class. |
| `NAME` | Tên class, ví dụ `inetOrgPerson`. |
| `SUP` | Superclass mà class kế thừa. |
| `ABSTRACT` | Lớp trừu tượng, thường dùng làm lớp cha. |
| `STRUCTURAL` | Lớp cấu trúc xác định loại entry trong cây directory. |
| `AUXILIARY` | Lớp bổ sung thuộc tính cho entry có structural class phù hợp. |
| `MUST` | Thuộc tính bắt buộc phải hiện diện theo class. |
| `MAY` | Thuộc tính được phép nhưng không bắt buộc. |

### 8.1. `MUST` không đồng nghĩa đơn trị

Nếu một object class khai báo:

```text
MUST ( cn $ sn )
MAY ( mail $ telephoneNumber )
```

thì entry cần có `cn` và `sn`. `mail` và `telephoneNumber` được phép nhưng không bắt buộc.

**`MUST` không có nghĩa thuộc tính chỉ được có một giá trị.** Cardinality do định nghĩa attribute type quyết định. Một attribute bắt buộc vẫn có thể là đa trị nếu attribute type không có `SINGLE-VALUE`.

### 8.2. Kế thừa object class

`inetOrgPerson` kế thừa `organizationalPerson`, lớp này kế thừa `person`, và `person` kế thừa `top`. Vì vậy các thuộc tính bắt buộc có thể đến từ superclass:

```text
top (ABSTRACT)
  └── person (STRUCTURAL; MUST cn, sn)
       └── organizationalPerson (STRUCTURAL)
            └── inetOrgPerson (STRUCTURAL)
```

Khi đối chiếu schema, cần đọc toàn bộ chuỗi `SUP` để xác định **effective MUST/MAY**, không chỉ dòng class cuối.

### 8.3. Structural và auxiliary class

- **Structural class** mô tả loại entry chính, ví dụ người dùng hoặc organizational unit.
- **Auxiliary class** bổ sung các thuộc tính tùy chọn vào entry đã có structural class.
- **Abstract class** thường làm lớp cha, không được dùng độc lập để tạo một entry cụ thể.

Một entry không thể tùy tiện ghép các structural class không tương thích. Quy tắc cấu trúc và kế thừa phải được server chấp nhận. Nếu cần mở rộng một entry người dùng bằng thuộc tính riêng, một auxiliary object class thường phù hợp hơn việc tạo một structural class thứ hai không liên quan.

## 9. Ví dụ schema chuẩn và hệ quả khi thiết kế Java

### 9.1. `person` và `inetOrgPerson`

RFC 4519 định nghĩa `person` là structural class với `cn` và `sn` bắt buộc; `organizationalPerson` mở rộng thông tin tổ chức. RFC 2798 định nghĩa `inetOrgPerson` mở rộng `organizationalPerson` với nhiều thuộc tính người dùng như `givenName`, `mail`, `uid`, `employeeNumber` tùy schema.

LDIF:

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

Java ODM:

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

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "givenName")
    private String givenName;

    @Attribute(name = "mail")
    private Set<String> mailAddresses;

    protected Person() { }
}
```

`mailAddresses` là `Set<String>` vì attribute có thể nhiều giá trị; `uid` trong schema chuẩn cũng có thể nhiều giá trị, nên field `String uid` ở ví dụ chỉ phù hợp nếu **schema/profile cụ thể của tổ chức bảo đảm chỉ một uid**. Nếu directory cho phép nhiều giá trị uid, hãy ánh xạ collection hoặc áp dụng một invariant ở tầng nghiệp vụ.

### 9.2. `groupOfNames` và `groupOfUniqueNames`

Hai class nhóm thường gặp:

| Object class | Thuộc tính chính | Ý nghĩa |
| --- | --- | --- |
| `groupOfNames` | `cn`, `member` | `cn` và ít nhất một `member` là bắt buộc theo schema chuẩn. |
| `groupOfUniqueNames` | `cn`, `uniqueMember` | `cn` và ít nhất một `uniqueMember` là bắt buộc theo schema chuẩn. |

`member` chứa DN của thành viên và là thuộc tính nhiều giá trị. `uniqueMember` dùng syntax Name and Optional UID và matching rule riêng.

LDIF:

```ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=alice,ou=people,dc=example,dc=org
member: uid=bob,ou=people,dc=example,dc=org
```

Java:

```java
package com.example.directory;

import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfNames"}
)
public class DirectoryGroup {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "member")
    private Set<Name> members;

    protected DirectoryGroup() { }
}
```

`Set<Name>` thể hiện đúng bản chất member là DN nhiều giá trị. Không dùng `Set<String>` nếu ứng dụng cần thao tác/so sánh DN theo cấu trúc và Spring LDAP ODM hỗ trợ mapping `Name`.

## 10. Cardinality: đơn trị hay đa trị?

Một trong những sai lầm phổ biến là suy luận cardinality từ dữ liệu mẫu:

```ldif
uid: alice
mail: alice@example.org
```

Việc entry Alice hiện chỉ có một giá trị `uid` và một giá trị `mail` **không chứng minh** schema giới hạn mỗi thuộc tính một giá trị.

Hãy tìm `SINGLE-VALUE` trong định nghĩa attribute type:

```text
attributeTypes: (
  1.2.3.4.5
  NAME 'employeeNumber'
  EQUALITY caseIgnoreMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15
  SINGLE-VALUE
)
```

Nếu có `SINGLE-VALUE`, một entry chỉ có tối đa một giá trị thuộc tính đó. Nếu không có, attribute type có thể là đa trị; vẫn cần xem schema server cụ thể và các quy tắc bổ sung.

### 10.1. Chọn kiểu Java

| Schema LDAP | Java thường phù hợp | Lưu ý |
| --- | --- | --- |
| Directory String, single-value theo profile | `String` | Kiểm tra có thật sự `SINGLE-VALUE` hoặc invariant ứng dụng. |
| Directory String, multi-value | `Set<String>` hoặc `List<String>` | LDAP không bảo đảm thứ tự giá trị; Set thường phản ánh semantics tốt hơn. |
| DN, single-value | `Name` | Dùng `LdapName`/`Name` để xử lý cấu trúc DN. |
| DN, multi-value | `Set<Name>` | Ví dụ `member` của group. |
| Binary, single-value | `byte[]` | Có thể cần giới hạn kích thước. |
| Binary, multi-value | Collection của `byte[]` hoặc kiểu wrapper phù hợp | Xác minh mapper/provider hỗ trợ kiểu mong muốn. |
| Operational/read-only attribute | Kiểu phù hợp + readonly mapping | Không ghi ngược thuộc tính do server quản lý. |

Nếu API nghiệp vụ cần thứ tự, hãy định nghĩa thứ tự riêng ở tầng ứng dụng sau khi đọc; không dựa vào thứ tự trả về của attribute nhiều giá trị.

## 11. Operational attributes và quyền truy cập

Không phải mọi thuộc tính xuất hiện trong entry đều là thuộc tính ứng dụng có thể ghi. Một số attribute do directory tạo/quản lý:

- `createTimestamp`
- `modifyTimestamp`
- `creatorsName`
- `modifiersName`
- `entryUUID` (thường gặp ở OpenLDAP và các server khác)
- `entryCSN` (đặc thù triển khai)
- Các thuộc tính vận hành khác tùy server.

Trong schema, các thuộc tính này có thể được đánh dấu `NO-USER-MODIFICATION` và `USAGE directoryOperation`. Client có thể phải yêu cầu tường minh khi search; không nên đưa chúng vào update payload.

Spring LDAP ODM hỗ trợ `@Attribute(readonly = true)`:

```java
@Attribute(name = "createTimestamp", readonly = true)
private String createdAt;

@Attribute(name = "modifyTimestamp", readonly = true)
private String modifiedAt;
```

Định dạng Generalized Time có thể cần converter nếu Java model dùng `Instant` hoặc kiểu thời gian khác. Dùng `String` ở ví dụ để tránh giả định định dạng/độ chính xác của provider; hãy xác minh syntax và converter trước khi đổi kiểu.

**Quyền đọc và schema là hai vấn đề khác nhau:** schema cho biết thuộc tính tồn tại/được phép như thế nào; ACL quyết định tài khoản hiện tại có được đọc hoặc sửa nó hay không.

## 12. Đối chiếu schema giữa OpenLDAP và Active Directory

Không nên coi mọi LDAP server có cùng schema mặc định, cùng cách lưu schema hoặc cùng naming context.

| Chủ đề | OpenLDAP | Active Directory Domain Services |
| --- | --- | --- |
| Root DSE | Có naming contexts và thông tin server theo cấu hình. | Có các thuộc tính như `defaultNamingContext`, `schemaNamingContext`, `configurationNamingContext`. |
| Schema discovery | Thường đọc subschema entry, ví dụ DN server công bố như `cn=Subschema`. | Root DSE trỏ tới subSchema; schema cũng được biểu diễn bằng các object `classSchema` và `attributeSchema` trong schema naming context. |
| Schema deployment | Có thể dùng schema files/config database tùy cách cài đặt. | Schema được quản lý trong AD schema partition; thay đổi cần quyền và quy trình quản trị AD. |
| Attribute/class extension | Thường thêm định nghĩa qua schema configuration. | Thêm schema objects theo cơ chế AD; thuộc tính/class có các metadata AD riêng. |
| Thuộc tính đặc thù | Có thể có `entryUUID`, `entryCSN` và schema/module riêng. | Có `objectGUID`, `objectSid`, `sAMAccountName`, `userPrincipalName`, `userAccountControl` và các attribute AD-specific. |

### 12.1. OpenLDAP

OpenLDAP có thể nạp các schema phổ biến như:

```text
core
cosine
inetorgperson
nis
```

Tên file và cách nạp phụ thuộc cách triển khai:

- Với cấu hình file kiểu cũ, schema có thể được khai báo bằng các chỉ thị include.
- Với cấu hình động `cn=config`, schema được quản lý như entry trong configuration DIT.
- Việc bật schema checking và các overlay/module có thể ảnh hưởng quy tắc thực tế.

Không giả định tên file schema trên máy chủ giống nhau giữa các bản phân phối. Hãy kiểm tra subschema mà server đang công bố, không chỉ đọc một file cấu hình cục bộ mà ứng dụng không có quyền truy cập.

### 12.2. Active Directory

Active Directory có naming context riêng cho schema, thường được công bố trong `schemaNamingContext`. Schema được biểu diễn bằng các đối tượng:

- `classSchema`: định nghĩa object class.
- `attributeSchema`: định nghĩa attribute type.

Các thuộc tính AD thường gặp khi đọc schema object:

| Thuộc tính | Mục đích |
| --- | --- |
| `lDAPDisplayName` | Tên LDAP được dùng trong truy vấn. |
| `governsID` | OID của class schema. |
| `attributeID` | OID của attribute schema. |
| `subClassOf` | Class cha. |
| `attributeSyntax`, `oMSyntax` | Mô tả syntax theo mô hình AD. |
| `isSingleValued` | Cho biết attribute có single-valued hay không. |
| `mustContain`, `mayContain` | Thuộc tính bắt buộc/được phép theo class. |
| `systemMustContain`, `systemMayContain` | Thuộc tính bắt buộc/được phép ở mức hệ thống. |

Active Directory không trình bày schema object theo đúng cách mà một OpenLDAP subschema entry thường được đọc. Dù có subSchema entry và thuộc tính `attributeTypes`/`objectClasses`, schema AD còn được quản lý bằng schema objects riêng. Khi xây ứng dụng chạy trên AD, cần đối chiếu tài liệu AD schema và đúng domain/forest functional level.

### 12.3. Không dùng giả định OpenLDAP cho Active Directory

Một số khác biệt dễ gặp:

- Đăng nhập thường dùng `sAMAccountName` hoặc `userPrincipalName` thay cho `uid`.
- Password có thể được quản lý bằng `unicodePwd` và chính sách AD; không đọc/ghi nó như một chuỗi thông thường.
- Group membership thường dùng `member` và backlink `memberOf`, nhưng semantics/primary group có điểm riêng.
- `objectGUID` và `objectSid` là định danh quan trọng, không giống DN hoặc `uid`.
- Attribute có thể có quyền đọc/ghi và rule riêng theo security descriptor.

Entity dùng cho OpenLDAP không nên mặc định tương thích với AD chỉ bằng cách thay URL và base DN.

## 13. Ánh xạ schema sang Spring LDAP ODM

Spring LDAP cung cấp **Object-Directory Mapping (ODM)** với các annotation:

| Annotation | Vai trò |
| --- | --- |
| `@Entry` | Khai báo object class mà Java class đại diện và có thể chỉ định base DN. |
| `@Id` | Ánh xạ DN của entry; field phải là `Name` hoặc lớp dẫn xuất. |
| `@Attribute` | Ánh xạ field Java tới attribute LDAP; có thể khai báo tên, syntax, kiểu binary/string và readonly. |
| `@DnAttribute` | Lấy một thành phần từ DN để gán vào field String. |
| `@Transient` | Không ánh xạ field thành LDAP attribute. |

### 13.1. `@Entry` phải khớp objectClass thực tế

Ví dụ entry người dùng chứa:

```ldif
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
```

ODM entity:

```java
@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class Person {
    @Id
    private Name dn;
}
```

Theo quy tắc ODM, các object class được khai báo trong entry cần được phản ánh trong `@Entry` để entity được nhận diện phù hợp. Nếu muốn ánh xạ field thuộc `inetOrgPerson`, phải khai báo class đó và chuỗi superclass cần thiết theo entry thực tế.

Khi tạo entry bằng ODM, Spring LDAP dùng các object class được khai báo trong `@Entry`. Vì vậy không khai báo thiếu superclass hoặc class bắt buộc mà directory yêu cầu.

### 13.2. `@Attribute`: tên và syntax

Ví dụ:

```java
@Attribute(name = "mail")
private Set<String> mailAddresses;

@Attribute(
    name = "manager",
    syntax = "1.3.6.1.4.1.1466.115.121.1.12"
)
private Name managerDn;
```

`name` ánh xạ field sang đúng tên LDAP. `syntax` có thể giúp converter của Spring LDAP lựa chọn cách chuyển đổi chính xác hơn, đặc biệt khi kiểu Java phụ thuộc syntax. Không khai báo OID syntax theo suy đoán; hãy lấy từ schema.

### 13.3. Thuộc tính nhị phân

Ví dụ `jpegPhoto` có thể được ánh xạ thành `byte[]`:

```java
@Attribute(
    name = "jpegPhoto",
    type = Attribute.Type.BINARY,
    syntax = "1.3.6.1.4.1.1466.115.121.1.28"
)
private byte[] photo;
```

`Attribute.Type.BINARY` yêu cầu JNDI provider trả dữ liệu dạng `byte[]`. Nếu schema/provider coi thuộc tính là chuỗi, mapping binary có thể không đúng. Kiểm tra cả syntax lẫn cách provider trả giá trị.

### 13.4. Operational attribute chỉ đọc

```java
@Attribute(name = "createTimestamp", readonly = true)
private String createdAt;
```

`readonly = true` cho phép đọc field nhưng không persist nó trở lại directory khi cập nhật entity. Điều này hữu ích với các thuộc tính server quản lý và không cho client sửa.

### 13.5. `@DnAttribute` và `@Transient`

DN:

```text
uid=alice,ou=people,dc=example,dc=org
```

Field lấy từ thành phần RDN:

```java
@DnAttribute(value = "uid")
@Transient
private String uidFromDn;
```

`@DnAttribute` lấy giá trị `uid` từ DN. Mặc định field cũng có thể được ánh xạ như LDAP attribute; nếu chỉ muốn lấy từ DN và không muốn persist nó như một attribute riêng, dùng `@Transient`.

Nếu một field cần đồng thời đại diện cho giá trị attribute `uid` và thành phần RDN `uid`, có thể kết hợp `@Attribute` với `@DnAttribute` theo đúng mục đích. Chỉ dùng `@DnAttribute` cho field kiểu `String`; không dùng nó để ánh xạ DN đầy đủ.

## 14. Ví dụ entity hoàn chỉnh dựa trên schema

Giả sử server xác nhận:

- `inetOrgPerson` là structural class trong chuỗi kế thừa `organizationalPerson`/`person`/`top`.
- `cn`, `sn` là thuộc tính bắt buộc theo superclass.
- `mail` có thể nhiều giá trị.
- `manager` có syntax DN.
- `jpegPhoto` là dữ liệu binary và được phép đọc.
- `createTimestamp` là operational/read-only.

Entity:

```java
package com.example.directory;

import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Attribute.Type;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

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

    @DnAttribute(value = "uid")
    @Transient
    private String uidFromDn;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "givenName")
    private String givenName;

    @Attribute(name = "mail")
    private Set<String> mailAddresses;

    @Attribute(
        name = "manager",
        syntax = "1.3.6.1.4.1.1466.115.121.1.12"
    )
    private Name managerDn;

    @Attribute(
        name = "jpegPhoto",
        type = Type.BINARY,
        syntax = "1.3.6.1.4.1.1466.115.121.1.28"
    )
    private byte[] photo;

    @Attribute(name = "createTimestamp", readonly = true)
    private String createdAt;

    protected Person() { }

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getCommonName() { return commonName; }
    public String getSurname() { return surname; }
    public String getGivenName() { return givenName; }
    public Set<String> getMailAddresses() { return mailAddresses; }
    public Name getManagerDn() { return managerDn; }
    public byte[] getPhoto() { return photo; }
    public String getCreatedAt() { return createdAt; }
}
```

**Lưu ý quan trọng:** field `uid` là `String` chỉ khi môi trường có invariant một uid cho mỗi entry. Schema chuẩn có thể cho phép `uid` nhiều giá trị. Nếu không có invariant được xác nhận, đổi field thành collection và kiểm thử mapping. Entity chỉ là ví dụ cho một profile directory đã được khảo sát, không phải model dùng chung cho mọi server.

## 15. Dùng entity với repository và LdapTemplate

Repository:

```java
package com.example.directory;

import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    Optional<Person> findByUid(String uid);
    List<Person> findBySurname(String surname);
}
```

`LdapRepository` sử dụng entity ODM để tìm và thao tác entry. Khi dùng repository, schema vẫn quyết định object class và thuộc tính có hợp lệ hay không; repository không tự tạo ra một schema mới cho server.

Với `LdapTemplate`:

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<Person> findPeople() {
        return ldapTemplate.findAll(Person.class);
    }

    public Person findByDn(javax.naming.Name dn) {
        return ldapTemplate.findByDn(dn, Person.class);
    }
}
```

Các method ODM của `LdapTemplate` dựa vào annotation và converter để ánh xạ. Nếu schema thực tế khác với annotation, lỗi có thể xuất hiện khi đọc, tạo hoặc cập nhật entity. Không giả định compile thành công là mapping đã đúng.

## 16. Kiểm tra schema trước khi tạo hoặc cập nhật entry

Một query đọc thành công không chứng minh thao tác ghi sẽ thành công. Khi thêm hoặc sửa entry, server còn kiểm tra:

- Các thuộc tính `MUST` có mặt.
- Attribute type có tồn tại và được object class cho phép.
- Syntax của từng giá trị hợp lệ.
- Attribute single-value không nhận nhiều giá trị.
- Structural object class và chuỗi kế thừa tương thích.
- Naming attribute có mặt và giá trị khớp RDN của DN.
- ACL cho phép tài khoản bind thực hiện thao tác.

### 16.1. Ví dụ lỗi do thiếu MUST

Entry thiếu `sn`:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
```

Với schema chuẩn `person` yêu cầu `cn` và `sn`, server có thể từ chối entry do vi phạm object class.

### 16.2. Ví dụ lỗi do SINGLE-VALUE

Nếu `employeeNumber` được định nghĩa `SINGLE-VALUE`, request sau không hợp lệ:

```ldif
employeeNumber: E-100
employeeNumber: E-101
```

Một Java field kiểu `List<String>` không làm server chấp nhận nhiều giá trị nếu schema cấm điều đó.

### 16.3. Ví dụ lỗi do naming attribute

DN:

```text
uid=alice,ou=people,dc=example,dc=org
```

Nhưng entry chứa:

```ldif
uid: bob
```

Một số server kiểm tra naming attribute/value consistency và từ chối thao tác vì RDN yêu cầu `uid=alice` nhưng entry lại chứa `uid=bob`. Đây là một kiểm tra khác với việc chỉ có đủ MUST attribute.

## 17. Schema migration và quản lý khác biệt môi trường

Schema thay đổi là thay đổi hợp đồng dữ liệu giữa ứng dụng và directory. Cần quản lý như một migration:

1. **Đọc schema hiện tại** ở tất cả môi trường liên quan.
2. Xác định attribute/object class mới có OID, syntax, matching rule và cardinality rõ ràng.
3. Đánh giá tương thích ngược: phiên bản ứng dụng cũ có bỏ qua attribute mới được không?
4. Triển khai schema lên directory theo quy trình quản trị của nhà cung cấp.
5. Kiểm tra quyền, replication và khả năng đọc schema ở các node phục vụ ứng dụng.
6. Chạy integration test add/modify/search bằng schema mới.
7. Triển khai ứng dụng dùng field mới.
8. Chỉ bắt buộc dữ liệu mới sau khi mọi writer/consumer tương thích.

### 17.1. Không tự thay schema production từ ứng dụng

Ứng dụng Spring Data LDAP thông thường nên **tiêu thụ schema**, không tự thay đổi schema máy chủ trong luồng request. Schema thường cần quyền quản trị directory, OID hợp lệ, quy trình phê duyệt và đồng bộ giữa các replica.

Với OpenLDAP, cách triển khai schema phụ thuộc cấu hình file hoặc `cn=config`. Với AD, thay đổi schema thuộc quy trình quản trị forest/schema master. Không dùng một script schema của OpenLDAP như thể áp dụng trực tiếp cho AD.

### 17.2. Tránh drift giữa dev, test và production

Nếu test directory có schema rộng hơn production, test có thể xanh nhưng ứng dụng lỗi khi triển khai. Hãy:

- Giữ schema test tương ứng với phiên bản production dự kiến.
- Kiểm tra schema version/OID quan trọng trong pipeline integration test.
- Không dùng custom attribute chỉ tồn tại trên một môi trường mà không có migration.
- Ghi lại server vendor/version và naming context khi lưu kết quả khảo sát schema.
- Nếu có nhiều directory vendor, dùng profile/entity mapping riêng khi semantics thật sự khác nhau thay vì cố ép một entity dùng chung.

## 18. Kiểm thử schema-first

Nên có một integration test kiểm tra cả đọc và ghi với directory test có schema gần production.

### 18.1. Ma trận kiểm thử

| Tình huống | Điều cần xác minh |
| --- | --- |
| Đọc Root DSE | Lấy đúng naming context và schema entry nếu server công bố. |
| Đọc subschema | Nhận được attribute type/object class cần dùng. |
| Đọc entry người dùng | ODM map DN và thuộc tính đúng kiểu. |
| Attribute nhiều giá trị | Collection Java nhận đủ giá trị, không mất dữ liệu. |
| Attribute DN | Mapping sang `Name` hợp lệ và so sánh đúng. |
| Attribute binary | `byte[]` nhận đúng dữ liệu, không bị decode thành text. |
| Operational attribute | Có thể đọc nếu ACL cho phép và không bị ghi ngược. |
| Thiếu MUST | Server từ chối entry; ứng dụng xử lý lỗi phù hợp. |
| Unknown attribute | Server từ chối hoặc xử lý theo policy; không giả định custom attr tự tồn tại. |
| SINGLE-VALUE bị vi phạm | Server từ chối nhiều giá trị. |
| Wrong syntax | Server từ chối giá trị không phù hợp syntax. |
| Naming mismatch | Server kiểm tra DN/RDN và giá trị naming attribute. |
| Matching rule | Filter equality/substring hoạt động đúng semantics server. |
| ACL | Tài khoản test chỉ có quyền cần thiết; lỗi quyền không bị nhầm thành schema error. |

### 18.2. Ví dụ JUnit 5 kiểm tra mapping

```java
package com.example.directory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("integration-test")
class PersonSchemaMappingIT {
    @Autowired PersonRepository repository;

    @Test
    void mapsEntryAccordingToDirectorySchema() throws Exception {
        Person person = repository.findByUid("alice")
                .orElseThrow();

        assertNotNull(person.getDn());
        assertEquals("Alice Nguyen", person.getCommonName());
        assertEquals("Nguyen", person.getSurname());
        assertEquals(
                Set.of("alice@example.org", "alice@work.example.org"),
                person.getMailAddresses());
    }
}
```

Đây là ví dụ minh họa; repository cần khai báo method `findByUid` và fixture phải có các giá trị tương ứng. Nếu entity dùng `Optional<Person>` thì method signature cần đúng kiểu trả về được Spring Data LDAP hỗ trợ trong phiên bản dự án. Test phải được chạy với naming context và schema test đã chuẩn bị.

### 18.3. Kiểm thử thao tác ghi bị schema từ chối

Tạo một entry test thiếu thuộc tính bắt buộc hoặc chứa hai giá trị cho attribute single-value, gọi `ldapTemplate.create(...)`/`update(...)` và xác minh Spring LDAP chuyển lỗi directory thành exception phù hợp. Không assert một mã lỗi cụ thể nếu server/provider khác nhau mà chưa chuẩn hóa contract; có thể ghi nhận LDAP result code như `objectClassViolation (65)`, `constraintViolation (19)` hoặc `invalidAttributeSyntax (21)` tùy trường hợp.

Không chạy các test ghi lỗi này trên production. Dùng suffix/OU riêng trong directory test và dọn fixture sau test.

## 19. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `objectClassViolation (65)` | Thiếu MUST, object class không tương thích hoặc thiếu structural class hợp lệ. | Đọc `objectClasses` và chuỗi `SUP`; kiểm tra effective MUST/MAY. |
| `undefinedAttributeType (17)` | Attribute không tồn tại trong schema hoặc tên sai. | Đọc `attributeTypes`/schema object và kiểm tra descriptor/OID. |
| `invalidAttributeSyntax (21)` | Giá trị không phù hợp syntax. | Kiểm tra syntax OID và converter/format Java. |
| `constraintViolation (19)` | Vi phạm SINGLE-VALUE hoặc constraint khác. | Kiểm tra cardinality và content rule. |
| `namingViolation (64)` | RDN không nhất quán với naming attribute hoặc vi phạm quy tắc DN. | Đối chiếu DN, giá trị RDN và naming attribute. |
| ODM không map được field | Sai tên attribute, syntax, kiểu binary/string hoặc converter. | Kiểm tra `@Attribute`, `Attribute.Type`, syntax OID và converter. |
| ODM không nhận entry | `@Entry.objectClasses` không bao phủ objectClass thực tế hoặc base sai. | Đối chiếu toàn bộ objectClass của entry và base DN. |
| Field Java chỉ nhận một giá trị | Model đơn trị trong khi schema/entry đa trị. | Dùng collection phù hợp và kiểm thử đủ dữ liệu. |
| DN bị coi như String | Không dùng kiểu `Name`/converter phù hợp. | Ánh xạ DN-valued attribute thành `Name` khi thích hợp. |
| Ảnh/certificate bị lỗi dữ liệu | JNDI/provider trả binary nhưng mapping mặc định là String. | Dùng `Attribute.Type.BINARY` và kiểm tra syntax. |
| Không đọc được operational attribute | Không request tường minh hoặc thiếu ACL. | Yêu cầu attribute cụ thể và kiểm tra quyền đọc. |
| Test xanh nhưng production lỗi | Schema/version/server vendor khác nhau. | Đồng bộ schema test với production và chạy integration test trên đúng loại server. |

## 20. Bài tập thực hành

**Bài 1.** Một entry có `mail: alice@example.org` và `mail: alice@work.example.org`. Chỉ dựa vào dữ liệu này, có thể kết luận schema `mail` là multi-valued không?

**Đáp án:** Có thể xác nhận entry đang có nhiều giá trị, nhưng để kết luận hợp đồng schema cần đọc định nghĩa attribute type. Một schema có thể cho phép nhiều giá trị; entry cụ thể không đại diện cho mọi ràng buộc của server.

**Bài 2.** `person` yêu cầu `cn` và `sn`. Nếu Java class có hai field này, entry có chắc chắn hợp lệ không?

**Đáp án:** Chưa. Còn phải kiểm tra chuỗi object class, thuộc tính bắt buộc kế thừa, naming attribute, syntax, ACL và các ràng buộc server khác.

**Bài 3.** Một thuộc tính có `SINGLE-VALUE` nhưng Java field là `List<String>`. Java collection có làm directory chấp nhận nhiều giá trị không?

**Đáp án:** Không. Schema server vẫn giới hạn một giá trị; kiểu Java không thể nới ràng buộc của directory.

**Bài 4.** Tại sao không nên map `member` của `groupOfNames` thành `String`?

**Đáp án:** `member` chứa DN của thành viên và thường là multi-valued. Dùng `Set<Name>` thể hiện cấu trúc DN và nhiều thành viên rõ hơn.

**Bài 5.** `@DnAttribute(value="uid")` có thay thế `@Attribute(name="uid")` không?

**Đáp án:** Không hoàn toàn. `@DnAttribute` lấy thành phần RDN từ DN; nó không tự đồng nghĩa field là một LDAP attribute riêng. Nếu không muốn field được persist như attribute, dùng `@Transient`; nếu cần cả hai ý nghĩa, khai báo mapping phù hợp.

**Bài 6.** Một field ảnh JPEG được map thành `String` nhưng directory trả octet. Cần kiểm tra gì?

**Đáp án:** Kiểm tra syntax OID và kiểu JNDI provider trả về; dùng `byte[]` với `@Attribute(type = Attribute.Type.BINARY)` khi phù hợp.

**Bài 7.** Root DSE của AD trả `schemaNamingContext`. Có thể dùng DN đó như `cn=Subschema` của OpenLDAP không?

**Đáp án:** Không. AD biểu diễn schema bằng các `classSchema`/`attributeSchema` objects trong schema naming context và có subSchema object riêng. Cần theo cơ chế AD.

**Bài 8.** `@Entry(objectClasses={"person","top"})` có thể map entry có `inetOrgPerson` nếu entity muốn dùng field `mail` không?

**Đáp án:** Không nên giả định. ODM yêu cầu khai báo các object class liên quan có trong entry; nếu cần map thuộc tính thuộc `inetOrgPerson`, phải khai báo class đó cùng các class trong chuỗi kế thừa phù hợp.

## 21. Checklist trước khi thiết kế entity Java

- [ ] Xác định đúng vendor/version và naming context của directory.
- [ ] Đọc Root DSE và xác định `subschemaSubentry`/schema naming context nếu được công bố.
- [ ] Đọc định nghĩa attribute type và object class cần sử dụng.
- [ ] Đọc cả chuỗi `SUP` để xác định thuộc tính kế thừa.
- [ ] Xác minh `MUST`/`MAY`, structural/auxiliary và `SINGLE-VALUE`.
- [ ] Xác minh syntax OID và equality/ordering/substring matching rule.
- [ ] Phân loại attribute string, DN, binary, multi-valued và operational.
- [ ] Đối chiếu ACL đọc/ghi với tài khoản ứng dụng.
- [ ] Chọn Java type tương ứng: `String`, collection, `Name`, `byte[]` hoặc kiểu có converter.
- [ ] Khai báo `@Entry` với object class phù hợp entry thực tế.
- [ ] Dùng `@Attribute`/`@DnAttribute`/`@Transient` đúng mục đích.
- [ ] Chạy integration test trên server/schema tương đương production trước khi triển khai.

## 22. Ghi nhớ

- **Schema là hợp đồng dữ liệu của LDAP server**; hãy đọc nó trước khi thiết kế Java entity.
- Root DSE cung cấp naming context và có thể trỏ tới subschema; hãy dùng DN server công bố thay vì đoán `cn=Subschema`.
- `attributeType` quyết định syntax, matching rule và cardinality; `objectClass` quyết định MUST/MAY và cấu trúc entry.
- `MUST` không có nghĩa single-value. Chỉ `SINGLE-VALUE` mới giới hạn attribute còn tối đa một giá trị.
- Syntax và matching rule khác nhau: syntax mô tả dạng dữ liệu, matching rule mô tả semantics so sánh.
- `member` là DN-valued và multi-valued; `uid` cũng có thể multi-valued theo schema chuẩn. Đừng chọn Java scalar chỉ vì fixture hiện có một giá trị.
- Spring LDAP ODM dùng `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` và `@Transient`; mapping phải khớp objectClass, syntax và kiểu dữ liệu thật.
- OpenLDAP và Active Directory có cách quản lý schema khác nhau; không giả định schema của một vendor áp dụng cho vendor khác.
- Kiểm thử cả đọc và ghi trên directory test có schema tương đương production để phát hiện lỗi MUST, syntax, cardinality, naming và ACL.

## Tài liệu tham khảo

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): attribute type, object class, subschema subentry và mô hình schema.
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517.html): syntax OID và matching rule.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519.html): các attribute/object class phổ biến như `person`, `organizationalPerson`, `groupOfNames`, `member` và `uid`.
- [RFC 2798 — Definition of the inetOrgPerson LDAP Object Class](https://www.rfc-editor.org/rfc/rfc2798.html): schema `inetOrgPerson` và ví dụ entry.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/3.3/odm.html): annotation ODM, conversion và cách ánh xạ DN/attribute.
- [Spring LDAP API — Attribute](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/Attribute.html): `name`, `syntax`, `readonly` và binary/string type.
- [OpenLDAP Administrator's Guide — Schema](https://www.openldap.org/doc/admin26/schema.html): cách định nghĩa và quản lý schema trong OpenLDAP.
- [Microsoft Learn — Active Directory Schema](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/5859bab0-f545-4db6-80c6-9798b484b3d8): schema objects và cách mở rộng schema AD.
- [Microsoft Learn — RootDSE](https://learn.microsoft.com/en-us/windows/win32/adschema/rootdse): thuộc tính Root DSE của Active Directory.
