# Schema, syntax, matching rule và quy tắc hợp lệ dữ liệu trong LDAP

Một ứng dụng Spring LDAP có thể kết nối thành công, bind đúng tài khoản và tìm được nhánh DN, nhưng vẫn bị máy chủ từ chối khi thêm hoặc sửa entry. Nguyên nhân thường nằm ở **schema**: entry thiếu thuộc tính bắt buộc, mang một thuộc tính không được phép, có kiểu giá trị sai hoặc khai báo tổ hợp `objectClass` không hợp lệ. Ở chiều ngược lại, một LDAP filter có vẻ đúng về mặt ký tự vẫn cho kết quả bất ngờ vì **matching rule** quy định cách máy chủ so sánh giá trị.

Bài này thuộc phần **LDAP nền tảng** của Spring LDAP. Mục tiêu là giải thích mối quan hệ giữa **schema → attribute type và object class → syntax → matching rule → kiểm tra dữ liệu**, rồi dùng mô hình đó để thiết kế entry, phân tích lỗi và viết thao tác an toàn với `LdapTemplate`, `LdapClient` hoặc ODM. Ví dụ minh họa dùng thư mục giả định `dc=example,dc=org`; khả năng và chính sách cụ thể luôn phải đối chiếu với schema của máy chủ đang sử dụng.

## 1. Schema là gì và máy chủ dùng nó khi nào?

**LDAP schema** là tập định nghĩa và ràng buộc mô tả những loại entry và attribute mà dịch vụ thư mục hiểu. Nó giống một hợp đồng dữ liệu, nhưng không thể đồng nhất với các bảng, cột và khóa ngoại của cơ sở dữ liệu quan hệ.

Các thành phần quan trọng bao gồm:

| Thành phần schema | Điều nó mô tả | Ví dụ |
|---|---|---|
| **Attribute type** | Tên/OID, kiểu giá trị, quy tắc so khớp và các hạn chế của thuộc tính | `cn`, `sn`, `uid`, `mail`, `member` |
| **Object class** | Kiểu entry, class cha, những attribute bắt buộc/được phép dùng | `person`, `inetOrgPerson`, `groupOfNames` |
| **LDAP syntax** | Biểu diễn và hình thức hợp lệ của một giá trị | Directory String, IA5 String, Integer, DN |
| **Matching rule** | Cách xác định hai giá trị bằng nhau, có quan hệ thứ tự hoặc khớp chuỗi con | `caseIgnoreMatch`, `distinguishedNameMatch` |
| **DIT content/name/structure rules** | Ràng buộc bổ sung về nội dung entry, RDN và vị trí trong cây khi được máy chủ hỗ trợ | Chỉ cho một kiểu entry ở vị trí/cách đặt tên nhất định |

Schema được áp dụng khi tạo entry, sửa attribute, đổi object class và đôi khi khi đổi tên/di chuyển entry. Trong truy vấn, các định nghĩa của attribute và matching rule giúp máy chủ diễn giải điều kiện của filter. Ngoài schema còn có **ACL/quyền truy cập, chính sách mật khẩu, ràng buộc ứng dụng và cấu hình sản phẩm LDAP**: một entry hợp schema chưa chắc có thể được ghi.

### Mối liên hệ giữa các khái niệm

~~~mermaid
flowchart TD
    A["LDAP schema"] --> B["Attribute type"]
    A --> C["Object class"]
    B --> D["Syntax: giá trị hợp lệ"]
    B --> E["Matching rule: cách so sánh"]
    C --> F["MUST / MAY và kế thừa"]
    F --> G["Kiểm tra entry"]
    D --> G
    G --> H["Thêm/sửa entry hợp lệ"]
    E --> I["Đánh giá điều kiện filter"]
    H --> J["Dữ liệu trong DIT"]
    J --> I
~~~

**Phân biệt quan trọng:** *syntax* trả lời “giá trị này có thuộc dạng được phép không?”, còn *matching rule* trả lời “khi tìm kiếm, hai giá trị được xem là khớp theo cách nào?”. Một giá trị hợp lệ về syntax vẫn có thể sai quy tắc nghiệp vụ; ví dụ một chuỗi ASCII có thể hợp kiểu IA5 String nhưng không nhất thiết là địa chỉ email đúng.

## 2. Attribute type: nhiều thứ hơn một tên trường

Mỗi **attribute type** thường có một **OID** (Object Identifier) để định danh ổn định và có thể có tên dễ đọc. Ví dụ `cn` là tên thông dụng của thuộc tính *common name*, được định danh chuẩn bằng OID `2.5.4.3`. Các tên như `cn`, `uid` chỉ là cách tham chiếu thuận tiện; nhiều máy chủ chấp nhận cả tên và OID khi chúng được schema công bố.

Một định nghĩa attribute type có thể nêu:

- **`NAME`**: tên hoặc các tên của thuộc tính.
- **`SUP`**: loại thuộc tính cha; một số đặc tính được kế thừa.
- **`SYNTAX`**: kiểu dữ liệu LDAP của giá trị.
- **`EQUALITY`**: quy tắc so khớp bằng nhau, dùng bởi filter như `(uid=linh)`.
- **`SUBSTR`**: quy tắc so khớp chuỗi con, dùng bởi filter như `(cn=Tran*)`.
- **`ORDERING`**: quy tắc so khớp thứ tự, cần cho những phép so sánh tương ứng.
- **`SINGLE-VALUE`**: chỉ cho tối đa một giá trị trong một entry.
- Các cờ khác như `NO-USER-MODIFICATION` đối với attribute do máy chủ quản lý.

Không phải attribute nào cũng có đủ mọi thành phần trên; một định nghĩa có thể kế thừa đặc tính từ `SUP`. Dưới đây là **mô tả ý nghĩa** của một loại attribute, không phải khai báo schema hoàn chỉnh để nạp vào máy chủ:

~~~text
Attribute type: uid
Ý nghĩa:         mã định danh người dùng
Syntax:          Directory String
Equality:        caseIgnoreMatch
Substrings:      caseIgnoreSubstringsMatch
Cardinality:     theo định nghĩa schema thực tế
~~~

### Một số attribute quen thuộc

| Attribute | Vai trò thường gặp | Syntax/matching rule thường gặp trong schema chuẩn | Lưu ý |
|---|---|---|---|
| `cn` | Tên hiển thị/tên thông dụng | Directory String; `caseIgnoreMatch` cho equality | Có thể chứa Unicode; không mặc định là duy nhất |
| `sn` | Họ (*surname*) | Directory String; so khớp không phân biệt hoa/thường | Bắt buộc đối với `person` |
| `uid` | Mã người dùng | Directory String; `caseIgnoreMatch` | Không mặc định là khóa duy nhất toàn cây |
| `mail` | Địa chỉ email | IA5 String; `caseIgnoreIA5Match` trong định nghĩa phổ biến | Syntax không kiểm chứng email có tồn tại |
| `member` | DN của thành viên nhóm | Distinguished Name; `distinguishedNameMatch` | Giá trị là DN, không phải chuỗi `uid` đơn lẻ |
| `uidNumber` | ID dạng số ở schema POSIX, nếu có | Integer; `integerMatch` | Phụ thuộc schema bổ sung, không có trên mọi máy chủ |

Bảng mô tả kiểu phổ biến để học cách đọc schema, **không thay thế kết quả tra cứu schema hiện hành**. Doanh nghiệp có thể bổ sung attribute riêng, thừa kế attribute khác hoặc áp dụng chính sách chặt hơn.

## 3. Syntax: hình thức hợp lệ của giá trị

**LDAP syntax** quy định giá trị được biểu diễn ở định dạng nào. Các dạng thường gặp:

| Syntax | Dùng cho | Ví dụ hợp lý | Rủi ro dễ gặp |
|---|---|---|---|
| **Directory String** | Tên người, mô tả, thông tin văn bản | `cn: Tran Mai Linh` | Không có nghĩa được đưa mọi chuỗi vào mọi attribute |
| **IA5 String** | Chuỗi ký tự thuộc bộ IA5/ASCII | `mail: linh@example.org` | Ký tự không thuộc IA5 sẽ không phù hợp syntax |
| **Integer** | Giá trị nguyên ở dạng LDAP quy định | `uidNumber: 10042` | Gửi `10042.5` hoặc chữ cái là sai |
| **Distinguished Name** | Tham chiếu đến entry bằng DN | `member: uid=linh,ou=people,dc=example,dc=org` | `linh` không phải DN |
| **Boolean** | Cờ logic | `TRUE` hoặc `FALSE` theo cú pháp LDAP | Không mặc định chấp nhận `yes` hay `1` |
| **Generalized Time** | Thời điểm theo quy tắc LDAP | `20261127090000Z` | Phải theo định dạng và mức độ chính xác cho phép |
| **Octet String** | Dữ liệu byte | Dữ liệu nhị phân của một attribute thích hợp | Không thể suy cách hiển thị/so sánh chỉ từ text |

**Syntax không tương đương với quy tắc kiểm tra nghiệp vụ.** Ví dụ `mail: abc` có thể thỏa giới hạn ký tự IA5 ở mức syntax, nhưng chưa chắc thỏa một quy tắc email do ứng dụng hoặc máy chủ áp thêm. Ngược lại, `mail: linh@ví-dụ.org` có Unicode và không phù hợp một attribute dùng IA5 String dưới dạng giá trị viết trực tiếp như vậy; cách chuẩn hóa tên miền quốc tế và chính sách địa chỉ thư cần xử lý ở lớp thích hợp.

Giá trị cũng cần được **mã hóa/escape theo đúng ngữ cảnh**:

- DN có cách escape riêng theo cú pháp DN (RFC 4514).
- LDAP search filter có cách escape riêng theo filter (RFC 4515).
- LDIF có quy tắc biểu diễn giá trị, bao gồm mã hóa base64 khi cần; `::` trong LDIF cho biết giá trị base64, không đồng nghĩa luôn là kiểu dữ liệu nhị phân.

Không dùng cách escape filter để tự ghép DN, hoặc ngược lại.

## 4. Matching rule: điều kiện “khớp” nghĩa là gì?

Cùng một giá trị hiển thị có thể được so sánh theo các quy tắc khác nhau. Matching rule được gắn với attribute type thông qua schema hoặc được chỉ định tường minh bằng **extensible match** khi máy chủ và attribute hỗ trợ.

### 4.1 Các nhóm so khớp

| Nhóm | Filter mẫu | Diễn giải |
|---|---|---|
| **Equality** | `(uid=linh)` | So khớp bằng nhau dựa trên `EQUALITY` của `uid` |
| **Substring** | `(cn=Tran*)` | So khớp chuỗi con dựa trên `SUBSTR` của `cn` |
| **Ordering** | `(uidNumber>=1000)` | Cần quy tắc `ORDERING` cho attribute số tương ứng |
| **Presence** | `(mail=*)` | Có ít nhất một giá trị của attribute, không chứng minh giá trị “đúng nghiệp vụ” |
| **Approximate** | `(cn~=Linh)` | Cách triển khai và mức độ hỗ trợ phụ thuộc máy chủ/schema |
| **Extensible** | `(cn:caseExactMatch:=Tran Mai Linh)` | Yêu cầu rule cụ thể nếu máy chủ cho phép dùng rule này với attribute |

Với `uid` được định nghĩa dùng `caseIgnoreMatch`, `(uid=LINH)` có thể khớp entry có giá trị `uid: linh`, do so sánh không phân biệt hoa/thường. Điều đó **không có nghĩa** máy chủ cho phép hai entry trùng DN, hay tự động áp quy tắc duy nhất cho `uid` trên toàn cây. Chính sách uniqueness là yêu cầu khác.

Với `member` dùng `distinguishedNameMatch`, máy chủ so sánh theo quy tắc dành cho DN, thay vì đơn giản so từng ký tự trong chuỗi. Bởi vậy điều kiện tìm thành viên phải chứa DN đúng cú pháp, ví dụ:

~~~ldap
(&(objectClass=groupOfNames)(member=uid=linh,ou=people,dc=example,dc=org))
~~~

Trong filter text theo RFC 4515, ký tự đặc biệt như `*`, `(`, `)`, `\` và NUL trong **giá trị filter** phải được escape đúng. Thay đổi cách viết DN, Unicode và ký tự đặc biệt cần được xử lý bằng các thư viện LDAP thay vì nối chuỗi thủ công.

### 4.2 Điều gì xảy ra khi schema không khai báo matching rule?

Không thể mặc định mọi attribute đều hỗ trợ `=`, `>=`, `<=` hoặc tìm kiếm chuỗi con. Chẳng hạn việc dùng `(someAttr>=10)` không đảm bảo có ý nghĩa nếu `someAttr` không có ordering matching rule. Theo cách đánh giá filter LDAP, một phép so khớp có thể cho kết quả **UNDEFINED** khi máy chủ không có quy tắc phù hợp; máy chủ cũng có thể báo lỗi đối với yêu cầu hoặc rule không được hỗ trợ. Không tự diễn giải một kết quả tìm kiếm rỗng thành “dữ liệu không tồn tại” khi điều kiện lọc có vấn đề.

Các matching rule không thay thế việc xác thực và phân quyền. Filter trả về entry chỉ chứng minh entry được nhìn thấy và khớp điều kiện dưới quyền đọc hiện tại; nó không xác nhận người dùng đã nhập mật khẩu đúng.

## 5. Object class: ràng buộc MUST, MAY, SUP

Nếu attribute type mô tả từng “trường”, **object class** xác định một kiểu entry được dùng những trường nào. Một object class có thể định nghĩa:

- **`SUP`**: class cha, với các yêu cầu được kế thừa.
- **`MUST`**: attribute cần có ít nhất một giá trị (có thể được kế thừa).
- **`MAY`**: attribute được phép xuất hiện nhưng không bắt buộc.
- **Loại class**: `STRUCTURAL`, `AUXILIARY` hoặc `ABSTRACT`.

Chuỗi class người dùng phổ biến:

~~~text
top                            [ABSTRACT]
└── person                      [STRUCTURAL; MUST: cn, sn]
    └── organizationalPerson    [STRUCTURAL; kế thừa person]
        └── inetOrgPerson       [STRUCTURAL; kế thừa organizationalPerson]
~~~

Entry `inetOrgPerson` phải thỏa các yêu cầu kế thừa từ `person`, trong đó có `cn` và `sn`. Thuộc tính như `mail`, `givenName` hoặc `uid` có thể được cho phép theo định nghĩa class liên quan mà không mặc định là bắt buộc.

**Một entry có thể khai báo nhiều giá trị `objectClass` nhưng không được ghép tùy ý các structural class độc lập.** Thông thường entry có một chuỗi phân cấp structural class hợp lệ và có thể bổ sung auxiliary class khi schema hoặc content rule cho phép. `top` là class abstract nền tảng, thường xuất hiện cùng các class khác.

Ví dụ một entry người dùng hợp lý, giả định entry cha đã tồn tại và schema chuẩn tương ứng được bật:

~~~ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Tran Mai Linh
sn: Tran
givenName: Mai Linh
mail: linh@example.org
~~~

Phân tích:

1. **DN/RDN**: `uid=linh` là RDN, `ou=people,dc=example,dc=org` là nhánh cha; thuộc tính `uid` có giá trị tương ứng trong entry.
2. **Object class**: các class khai báo tạo chuỗi kế thừa phù hợp cho một người.
3. **MUST**: `cn` và `sn` đều có giá trị.
4. **MAY**: `uid`, `givenName` và `mail` được cho phép trong schema giả định.
5. **Syntax**: `cn`/`sn` là văn bản phù hợp; `mail` trong ví dụ là chuỗi ASCII.
6. **Kiểm soát khác**: entry cha phải tồn tại, DN không trùng, tài khoản bind đủ quyền và máy chủ phải chấp nhận cách đặt tên.

Lưu ý: `member: uid=linh,...` trong entry `groupOfNames` là thuộc tính **tham chiếu bằng DN**, không phải quan hệ cha–con của cây và không mặc định được server thực thi như khóa ngoại.

### Ba loại lỗi khác nhau khi khai báo entry

~~~ldif
# Ví dụ 1: thiếu sn nên không đạt MUST của person.
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Tran Mai Linh

# Ví dụ 2: sai cú pháp cho attribute dùng Integer trong schema POSIX.
dn: uid=binh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: posixAccount
uid: binh
cn: Nguyen Van Binh
sn: Nguyen
uidNumber: ABC
gidNumber: 100
homeDirectory: /home/binh

# Ví dụ 3: member của groupOfNames không chứa DN.
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: linh
~~~

Các đoạn trên **cố tình sai để phân tích**. Ví dụ 2 còn phụ thuộc việc máy chủ đã cài schema POSIX và các quy tắc của `posixAccount`; giá trị `uidNumber: ABC` không hợp kiểu Integer. Ví dụ 3 thiếu giá trị DN hợp lệ trong `member`. Mã lỗi cụ thể được trả về có thể khác nhau tùy server và tổ hợp lỗi.

## 6. Các bước kiểm tra hợp lệ khi thêm hoặc sửa entry

Khi nhận yêu cầu thêm entry, máy chủ có thể cần xét những điều kiện sau:

| Lớp kiểm tra | Câu hỏi | Kết quả nếu vi phạm |
|---|---|---|
| **DN và vị trí** | DN đúng cú pháp, parent tồn tại, tên chưa bị chiếm, RDN phù hợp chính sách? | Ví dụ invalid DN, no such object, entry already exists, naming violation |
| **Object class** | Có structural class hợp lệ, quan hệ kế thừa được chấp nhận? | Object class violation |
| **MUST** | Entry có đủ attribute bắt buộc theo tất cả class áp dụng? | Object class violation |
| **MAY và content rule** | Attribute có được phép xuất hiện trong kiểu entry này? | Object class violation hoặc constraint violation tùy nguyên nhân |
| **Syntax và cardinality** | Giá trị có đúng định dạng; attribute `SINGLE-VALUE` có quá một giá trị không? | Invalid attribute syntax hoặc constraint violation |
| **Giới hạn khác** | Độ dài, tính duy nhất, tên RDN, policy ứng dụng, plugin server? | Constraint/naming violation hoặc lỗi riêng |
| **ACL** | Danh tính bind có đủ quyền đọc/ghi tại DN và attribute? | Insufficient access rights |

Một số kết quả LDAP có ích khi chẩn đoán:

| Result code | Tên LDAP | Gợi ý điều tra |
|---|---|---|
| **17** | `undefinedAttributeType` | Attribute không được schema nhận diện |
| **19** | `constraintViolation` | Vi phạm ràng buộc về attribute hoặc chính sách |
| **21** | `invalidAttributeSyntax` | Giá trị không đáp ứng syntax của attribute |
| **32** | `noSuchObject` | Entry/nhánh được tham chiếu không tồn tại |
| **34** | `invalidDNSyntax` | DN không đúng cú pháp |
| **50** | `insufficientAccessRights` | Tài khoản không đủ quyền |
| **64** | `namingViolation` | DN/RDN hoặc quy tắc đặt tên bị vi phạm |
| **65** | `objectClassViolation` | Object class, MUST hoặc attribute được phép không hợp lệ |
| **68** | `entryAlreadyExists` | Entry có DN đã tồn tại |

**Không đoán chính xác nguyên nhân chỉ từ một mã lỗi.** Ví dụ `objectClassViolation` có thể do thiếu `sn`, thêm attribute không được phép hoặc kết hợp class sai; cần đối chiếu DN, giá trị gửi đi, schema và thông tin phản hồi/nhật ký máy chủ.

Với thao tác **modify**, máy chủ thường kiểm tra *trạng thái entry sau khi áp dụng phép sửa*. Nếu xóa `sn` khỏi entry `person` mà không có giá trị thay thế hợp lệ, kết quả vi phạm MUST. Một thay đổi `objectClass` cũng có thể khiến các attribute đang tồn tại trở thành không được phép.

## 7. Xem schema thực tế của LDAP server

Những ví dụ trong tài liệu là kiểu phổ biến; dựa vào bảng ghi nhớ để lập trình với môi trường production là chưa đủ. Trong LDAPv3, một entry có thể chỉ đến **subschema subentry** qua operational attribute `subschemaSubentry`. Client có thể đọc DN này rồi truy vấn các định nghĩa schema mà máy chủ cho phép công bố.

Ví dụ với công cụ `ldapsearch` trên hệ thống có hỗ trợ công cụ này:

~~~bash
# Bước 1: hỏi nơi công bố schema cho entry gốc của ứng dụng.
ldapsearch -LLL -x -H ldaps://ldap.example.org \
  -D "uid=reader,ou=service,dc=example,dc=org" -W \
  -b "dc=example,dc=org" -s base \
  "(objectClass=*)" subschemaSubentry

# Bước 2: thay <SCHEMA_DN> bằng DN được trả về ở bước 1.
ldapsearch -LLL -x -H ldaps://ldap.example.org \
  -D "uid=reader,ou=service,dc=example,dc=org" -W \
  -b "<SCHEMA_DN>" -s base \
  "(objectClass=*)" attributeTypes objectClasses \
  ldapSyntaxes matchingRules matchingRuleUse
~~~

`-W` yêu cầu nhập mật khẩu từ prompt; không đưa mật khẩu vào command line hoặc repository. Ví dụ dùng LDAPS và giả định chứng chỉ máy chủ được xác thực đúng. Đường dẫn subschema không cố định giữa OpenLDAP, Active Directory và các sản phẩm khác; người dùng cần quyền đọc thích hợp và một số loại schema có thể không được công bố đầy đủ.

Khi đọc một định nghĩa:

1. Tìm attribute `uid` (bằng tên hoặc OID) trong `attributeTypes`, xem `SYNTAX`, `EQUALITY`, `SUBSTR`, `SINGLE-VALUE` và `SUP`.
2. Tìm class `inetOrgPerson` trong `objectClasses`, xem `SUP`, `MUST`, `MAY` và loại class.
3. Theo chuỗi `SUP` đến các class/attribute cha để tính **ràng buộc hiệu lực**, vì một class có thể không ghi lại các yêu cầu kế thừa.
4. Kiểm tra `dITContentRules`, `dITStructureRules`, `nameForms` nếu sản phẩm dùng các cơ chế đó; đồng thời đọc chính sách tài khoản, password và ACL.

Các operational attribute thường không được trả về trong tập attribute thường mặc định (ví dụ chỉ yêu cầu `*`). Khi cần, yêu cầu tên cụ thể như `subschemaSubentry` hoặc dùng cú pháp hỗ trợ chọn operational attributes (như `+` trên máy chủ hỗ trợ).

## 8. Áp dụng với Spring LDAP

Giả sử ứng dụng đã có `ContextSource` và `LdapTemplate` cấu hình với base DN `dc=example,dc=org`, kết nối TLS, cơ chế bind có quyền phù hợp. Khi tạo entry, ứng dụng cần cung cấp các attribute phù hợp schema và dùng API dựng DN để xử lý escape.

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addPerson(String uid, String cn, String sn, String mail) {
        // DN tương đối với base "dc=example,dc=org" của ContextSource.
        Name relativeDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", uid)
                .build();

        Attributes attrs = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);

        // uid đồng thời được dùng trong RDN.
        attrs.put("uid", uid);
        attrs.put("cn", cn);
        attrs.put("sn", sn);

        if (mail != null && !mail.isBlank()) {
            attrs.put("mail", mail);
        }

        ldapTemplate.bind(relativeDn, null, attrs);
    }
}
~~~

Mỗi dòng trong ví dụ có liên hệ trực tiếp với schema:

- `objectClass` xác định loại entry và chuỗi kế thừa.
- `cn` và `sn` đáp ứng yêu cầu `MUST` từ `person`.
- `uid` có giá trị phù hợp với RDN, đồng thời là attribute mà filter tìm kiếm có thể dùng.
- `mail` được xem là tùy chọn; ứng dụng vẫn cần kiểm tra giá trị trước khi gửi, vì không nên dùng LDAP server làm lớp kiểm tra giao diện duy nhất.
- `LdapNameBuilder` dựng DN theo cấu trúc RDN, tránh tự nối chuỗi tên có ký tự đặc biệt.
- `ldapTemplate.bind(...)` yêu cầu máy chủ tạo entry; nó vẫn có thể thất bại do DN, schema, ACL hoặc kết nối.

Ở phía tìm kiếm, Spring LDAP dựng điều kiện trên attribute. Hãy chọn filter dựa trên matching rule đã được schema xác nhận:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public List<String> findNamesByUid(LdapTemplate ldapTemplate, String uid) {
    LdapQuery ldapQuery = query()
            .base("ou=people")
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(uid);

    return ldapTemplate.search(
            ldapQuery,
            (AttributesMapper<String>) attrs ->
                    (String) attrs.get("cn").get()
    );
}
~~~

Với schema điển hình, điều kiện equality trên `uid` tuân theo `caseIgnoreMatch`; mọi kết quả vẫn phụ thuộc search base, scope, ACL và dữ liệu hiện có. Giá trị của filter do người dùng cung cấp nên được đưa qua query/filter builder của Spring LDAP để được escape đúng theo ngữ cảnh; không tạo filter bằng nối chuỗi như `"(&(uid=" + uid + ")(objectClass=inetOrgPerson))"`.

**Đối với `LdapClient` và ODM**, các quy tắc schema không thay đổi: API fluent và annotation Java chỉ thay đổi cách xây dựng yêu cầu hoặc ánh xạ object. Dùng ODM với `@Entry`, `@Id`, `@Attribute` không tự động sửa được một entry thiếu `sn` hay cho phép một object class không hợp lệ. Bài học này tập trung vào schema; cấu hình TLS, pooling, xử lý lỗi nâng cao và kiểm thử tích hợp là các chủ đề vận hành tiếp theo trong Spring LDAP.

### Phân lớp xử lý lỗi trong ứng dụng

Khi ghi entry thất bại, nên ghi log an toàn những thông tin hỗ trợ chẩn đoán như loại thao tác, DN liên quan (khi được phép), loại exception và mã LDAP/result code nếu có. **Không log mật khẩu, giá trị nhạy cảm hay dữ liệu bind nguyên văn.** Các exception Spring LDAP có thể bọc lỗi JNDI và kết quả server; lớp service nên phân biệt nhóm lỗi nhập liệu/schema, lỗi quyền và lỗi hạ tầng để trả thông báo phù hợp. Không nên tự động retry yêu cầu thêm entry bị từ chối vì vi phạm schema: phải sửa dữ liệu hoặc cấu hình trước.

## 9. Bài tập phân tích một tình huống

Một đội phát triển quản lý entry người dùng và nhóm với nhánh đã tồn tại:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=linh
└── ou=groups
    └── cn=developers
~~~

Hệ thống đưa ra bốn yêu cầu:

1. Thêm người dùng `uid=linh` với `objectClass=inetOrgPerson`, `cn=Tran Mai Linh`, `mail=linh@example.org` nhưng không gửi `sn`.
2. Tìm người dùng với filter `(uid=LINH)` dù giá trị lưu là `linh`.
3. Ghi vào nhóm `groupOfNames` thuộc tính `member: linh`.
4. Tìm `uidNumber` lớn hơn hoặc bằng `1000` trên hệ thống chưa cài schema POSIX.

**Hướng giải:**

- **(1)** Entry không đáp ứng thuộc tính bắt buộc `sn` kế thừa từ `person`. Thêm `sn` và đảm bảo `uid`/RDN phù hợp schema và chính sách server.
- **(2)** Với `uid` dùng `caseIgnoreMatch` như schema phổ biến, `LINH` có thể khớp `linh`. Nhưng không được dựa vào so khớp này để khẳng định `uid` là duy nhất.
- **(3)** `member` thường có syntax DN, nên dùng `member: uid=linh,ou=people,dc=example,dc=org`; cần bảo đảm nhóm có đủ attribute MUST và giá trị DN hợp lệ.
- **(4)** Nếu `uidNumber` không được khai báo, filter/attribute có thể bị từ chối hoặc không thể đánh giá đúng; trước tiên cần xác minh attribute type và ordering rule trong schema đã cài. Không suy ra máy chủ sẽ so sánh “số” chỉ vì tên attribute chứa chữ `Number`.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một giá trị `mail` chỉ chứa ký tự ASCII đã chắc chắn là email hợp lệ chưa?

*Chưa.* Syntax IA5 String là kiểm tra về tập ký tự/định dạng giá trị ở lớp LDAP; định dạng email nghiệp vụ và khả năng nhận thư là các điều kiện bổ sung.

**Câu 2.** Vì sao entry có `objectClass: inetOrgPerson` vẫn cần `sn` dù bản thân định nghĩa class này có thể không liệt kê `sn`?

*Vì ràng buộc được kế thừa*: `inetOrgPerson` là hậu duệ của `person` và `person` yêu cầu `cn` cùng `sn`.

**Câu 3.** Sự khác nhau giữa `invalidAttributeSyntax` và `objectClassViolation` là gì?

*Thông thường*, lỗi đầu chỉ giá trị không đúng syntax của attribute; lỗi sau liên quan tập object class, attribute bắt buộc hoặc attribute được phép trong kiểu entry. Trường hợp cụ thể vẫn phải xem phản hồi máy chủ.

**Câu 4.** Tại sao filter `(uid=LINH)` có thể tìm thấy `uid: linh`?

*Vì matching rule*: định nghĩa chuẩn thường dùng `caseIgnoreMatch` cho equality của `uid`, không phải vì tất cả attribute LDAP đều tự động không phân biệt hoa/thường.

**Câu 5.** Một entry vượt qua kiểm tra schema có thể vẫn bị từ chối không?

*Có.* Parent DN không tồn tại, DN đã có, ACL thiếu quyền hoặc một chính sách riêng của máy chủ đều có thể khiến thao tác thất bại.

## Tài liệu để tra cứu sâu

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): thông tin mô hình entry, schema và subschema.
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): định nghĩa syntax và matching rule cốt lõi.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): attribute/object class thường gặp như `cn`, `sn`, `person`, `groupOfNames`.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515) và [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): escape và cú pháp riêng cho filter/DN.
- [RFC 4524 — COSINE LDAP/X.500 Schema](https://www.rfc-editor.org/rfc/rfc4524): một số định nghĩa attribute ứng dụng như `mail`.

**Ghi nhớ:** **schema** xác định loại dữ liệu và cấu trúc entry; **syntax** xác định dạng giá trị; **matching rule** xác định cách giá trị được so khớp trong tìm kiếm; còn **object class/MUST/MAY**, DN, ACL và chính sách server phối hợp quyết định entry có thể được tạo hoặc sửa hay không. Nắm chuỗi quan hệ này giúp viết filter chính xác, tạo entry hợp lệ và xử lý lỗi bằng Spring LDAP có căn cứ.
