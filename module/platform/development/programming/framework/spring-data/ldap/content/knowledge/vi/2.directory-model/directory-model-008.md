# LDIF và cách biểu diễn dữ liệu thư mục

**LDAP Data Interchange Format (LDIF)** là định dạng văn bản dùng để biểu diễn entry trong directory và mô tả các thay đổi cần gửi tới LDAP server. LDIF giúp quản trị viên, ứng dụng và công cụ LDAP trao đổi dữ liệu theo một cấu trúc có thể đọc, lưu trong file, review và đưa vào quy trình import/export. Trong **Spring Data LDAP**, LDIF là định dạng dữ liệu ở biên của hệ thống: repository và **LdapTemplate** làm việc với Java object, DN và LDAP operation; LDIF giúp tạo fixture, di chuyển dữ liệu, sao lưu logic hoặc tái hiện một lỗi directory.

Bài thuộc chương **Mô hình thư mục** của module **SPRING_DATA_LDAP**. Người học sẽ phân biệt **content records** với **change records**, hiểu cách biểu diễn **DN, objectClass, attribute đơn trị/đa trị, binary value, UTF-8, Base64 và line folding**, thực hiện **add/delete/modify/modrdn**, kiểm tra bằng **ldapadd/ldapmodify/ldapsearch**, ánh xạ dữ liệu LDIF sang Spring LDAP ODM và xây dựng integration test an toàn.

> **Quy tắc nền tảng:** LDIF là một **định dạng biểu diễn và trao đổi dữ liệu**. Một file LDIF không tự tạo transaction cho toàn bộ file, không mã hóa dữ liệu nhạy cảm và không vượt qua **schema, ACL, TLS hoặc chính sách** của directory server.

## 1. LDIF nằm ở đâu trong kiến trúc LDAP?

Một directory lưu entry theo cây DN. LDIF biểu diễn các entry hoặc thao tác thay đổi trên entry đó bằng những record văn bản:

~~~mermaid
flowchart TD
    A["File LDIF"] --> B{"Loại record"}
    B --> C["Content record"]
    B --> D["Change record"]
    C --> E["dn + objectClass + attributes"]
    D --> F["dn + changetype + change specification"]
    E --> G["LDAP Add / import"]
    F --> H["LDAP Add/Delete/Modify/ModifyDN"]
    G --> I[("LDAP Directory")]
    H --> I
    I --> J["LdapTemplate / ContextSource"]
    J --> K["Spring Data LDAP ODM"]
    K --> L["Java entity / Repository"]
~~~

Các vai trò:

| Thành phần | Dữ liệu/định dạng | Vai trò |
| --- | --- | --- |
| **LDAP entry** | DN, objectClass, attributes | Đơn vị dữ liệu được lưu trong directory |
| **LDIF content record** | Một entry ở dạng văn bản | Import hoặc trao đổi entry |
| **LDIF change record** | Một thao tác trên DN | Add, delete, modify hoặc modrdn |
| **ldapadd/ldapmodify** | LDIF và LDAP protocol | Gửi dữ liệu/thay đổi tới server |
| **ldapsearch** | SearchRequest và kết quả LDIF | Đọc directory và xuất kết quả |
| **Spring LDAP ODM** | Java class và annotation | Ánh xạ entry thành object |
| **LdapRepository** | Repository method | Truy vấn và thao tác entry theo mô hình Java |
| **LdapTemplate** | LDAP operation API | Tìm kiếm, bind, modify, rename, unbind |

Spring Data LDAP không yêu cầu ứng dụng phải lưu entity dưới dạng file LDIF. **Repository.save(...)** không phải một lệnh đọc file LDIF; nó làm việc với entity ODM và gửi LDAP operation thông qua ContextSource.

## 2. Cấu trúc cơ bản của một LDIF file

LDIF được chuẩn hóa trong **RFC 2849**. Một file thường gồm nhiều record, mỗi record gồm các dòng thuộc tính và được ngăn cách bởi **một dòng trống**. File có thể bắt đầu bằng dòng phiên bản:

~~~ldif
version: 1

dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@lab.example

dn: uid=an,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@lab.example
~~~

Đọc file theo thứ tự:

1. **version: 1**: khai báo phiên bản LDIF nếu file có dòng version.
2. **dn:**: chỉ ra Distinguished Name của entry.
3. **objectClass:**: xác định loại entry theo schema.
4. Những dòng tiếp theo là **attribute description** và **attribute value**.
5. Dòng trống kết thúc record hiện tại và bắt đầu record tiếp theo sau đó.

**Dòng version** nếu xuất hiện phải ở đầu file, trước các record. Một file không có version line vẫn có thể là LDIF hợp lệ tùy trường hợp; không chèn **version: 1** giữa các record.

### 2.1. Comment và dòng trống

Một dòng bắt đầu bằng **#** là comment:

~~~ldif
# Fixture cho integration test Spring Data LDAP
version: 1

# Entry người dùng
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
~~~

Comment giúp ghi chú nguồn dữ liệu, mục đích hoặc ngày tạo fixture. Không đặt secret trong comment vì LDIF thường được commit, gửi qua email, đính kèm ticket hoặc lưu trong artifact build.

### 2.2. Mỗi record là một đơn vị cú pháp

Không nối hai entry liên tiếp mà thiếu dòng trống:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen

dn: uid=an,ou=people,dc=lab,dc=example
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
~~~

Trong ví dụ rút gọn này, các objectClass cha có thể được bổ sung tùy schema server; mục đích là minh họa **ranh giới record**. Dòng trống thuộc cấu trúc file, không phải một attribute có giá trị rỗng.

## 3. DN: địa chỉ của entry trong cây thư mục

**Distinguished Name (DN)** xác định vị trí của một entry trong directory tree. DN được tạo từ một hoặc nhiều **Relative Distinguished Name (RDN)**, đi từ entry cụ thể nhất tới suffix/root:

~~~text
dc=lab,dc=example
└── ou=people
    └── uid=linh

DN đầy đủ:
uid=linh,ou=people,dc=lab,dc=example
~~~

Một dòng LDIF:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
~~~

DN không phải giá trị của attribute uid; nó là **định danh tên phân cấp** của entry. Entry có thể có attribute uid nhưng DN còn bao gồm nhánh OU và suffix.

### 3.1. Thứ tự RDN và base DN

Trong DN:

~~~text
uid=linh,ou=people,dc=lab,dc=example
  └──── RDN entry
          └──── RDN OU
                   └── suffix
~~~

Với Spring LDAP **ContextSource base = dc=lab,dc=example**, nhiều API nhận DN tương đối như **uid=linh,ou=people**. Trong LDIF, DN thường được ghi **đầy đủ** để entry tự mô tả vị trí của nó.

### 3.2. Escaping ký tự trong DN

Giá trị RDN có thể chứa dấu phẩy, dấu cộng, dấu ngoặc kép, backslash, dấu **#** ở đầu hoặc khoảng trắng ở đầu/cuối. Khi biểu diễn DN, các ký tự đặc biệt phải được escape theo **RFC 4514**.

~~~text
Giá trị uid:
  linh,an

DN có RDN chứa dấu phẩy literal:
  uid=linh\,an,ou=people,dc=lab,dc=example

Hoặc biểu diễn hex escape:
  uid=linh\2Can,ou=people,dc=lab,dc=example
~~~

Không nhầm:

- **DN escaping** theo RFC 4514 dùng để biểu diễn RDN/DN.
- **LDAP filter escaping** theo RFC 4515 dùng cho giá trị trong filter.
- **LDIF Base64** dùng để biểu diễn byte của một giá trị LDIF.

Ba cơ chế phục vụ ba ngữ cảnh khác nhau. Không lấy một hàm escape filter để tạo DN hoặc dùng Base64 thay cho DN escaping.

## 4. objectClass và attribute trong LDIF

Một entry thường có nhiều dòng **objectClass** và các attribute mô tả dữ liệu:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@lab.example
description: Backend engineer
~~~

| Dòng LDIF | Ý nghĩa |
| --- | --- |
| **dn:** | DN của entry |
| **objectClass:** | Các object class mà entry tuân theo |
| **uid:** | User identifier |
| **cn:** | Common name |
| **sn:** | Surname |
| **mail:** | Email address |
| **description:** | Thông tin mô tả tự do theo schema |

### 4.1. objectClass quyết định cấu trúc hợp lệ

Trong ví dụ, **inetOrgPerson** kế thừa **organizationalPerson**, rồi **person** và **top**. Schema xác định:

- **MUST**: attribute bắt buộc, ví dụ **cn** và **sn** từ class **person**.
- **MAY**: attribute được phép nhưng không bắt buộc, ví dụ một số attribute contact như **mail**.
- **Syntax/matching rule**: kiểu giá trị và cách server so sánh.
- **Structural/Auxiliary**: loại objectClass và quan hệ kế thừa.

Một LDIF có cú pháp văn bản đúng vẫn có thể bị server từ chối nếu **objectClass chain** không hợp lệ, thiếu MUST hoặc chứa attribute không được phép.

### 4.2. Attribute name và attribute options

Attribute description có thể là tên thuộc tính hoặc OID, đôi khi kèm option:

~~~ldif
cn: Linh Nguyen
cn;lang-en: Linh Nguyen
cn;lang-vi: Nguyễn Văn Linh
~~~

Các option như **lang-en** và **lang-vi** là ví dụ về **language tags** nếu schema/server và ứng dụng hỗ trợ. Chúng không tự động tạo ra hai thuộc tính Java độc lập. Mapping và matching phải xét đầy đủ **attribute description** cùng option.

Một số thuộc tính có option **;binary** trong những ngữ cảnh LDAP đặc thù. Cú pháp option không thay đổi quy tắc **Base64 của LDIF**; hai dấu hai chấm liền nhau vẫn biểu thị giá trị Base64 trong LDIF.

### 4.3. Attribute đơn trị và đa trị

LDAP attribute có thể chứa một hoặc nhiều giá trị theo schema. LDIF biểu diễn các giá trị bằng cách **lặp lại cùng attribute description**, không nối chúng bằng dấu phẩy:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@lab.example
mail: linh.work@lab.example
~~~

Không viết:

~~~ldif
# Sai nếu muốn biểu diễn hai giá trị mail độc lập:
mail: linh@lab.example, linh.work@lab.example
~~~

Dòng sai ở trên là **một giá trị String chứa dấu phẩy**, không phải hai attribute value. Server có thể lưu nó như một địa chỉ sai hoặc từ chối theo syntax.

**Số lượng giá trị** còn phụ thuộc schema: attribute **SINGLE-VALUE** chỉ cho phép một giá trị. Việc lặp attribute trong LDIF không làm nó trở thành đa trị nếu schema cấm.

## 5. Content records và change records

LDIF có hai kiểu record chính:

| Kiểu | Bắt đầu bằng | Dùng khi |
| --- | --- | --- |
| **Content record** | **dn:** rồi đến attribute | Mô tả một entry hoàn chỉnh |
| **Change record** | **dn:** rồi đến **changetype:** | Mô tả thao tác thay đổi trên DN |

### 5.1. Content record

~~~ldif
dn: uid=an,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@lab.example
~~~

Đây là biểu diễn một entry. Công cụ import thường gửi thao tác **Add** tương ứng; nếu DN đã tồn tại, server có thể trả **entryAlreadyExists (68)**. Content record không có dòng **changetype: add**.

### 5.2. Change record

~~~ldif
dn: uid=an,ou=people,dc=lab,dc=example
changetype: modify
replace: mail
mail: an.new@lab.example
-
~~~

Đây là một yêu cầu **Modify** trên entry đã tồn tại. **changetype: modify** quyết định cách parser hiểu các dòng tiếp theo. Dòng dấu gạch ngang kết thúc một change specification; không nhầm với dòng trống kết thúc record.

**Một file có thể chứa nhiều record**; một số record là content, số khác là change record. Tuy nhiên, hãy chọn công cụ và mode import phù hợp với kiểu dữ liệu; không dùng **ldapadd** để mong nó thực thi tất cả loại change record như **ldapmodify**.

## 6. Biểu diễn giá trị UTF-8 và Base64

LDIFv1 sử dụng biểu diễn văn bản dựa trên **UTF-8**. Các giá trị có thể được ghi trực tiếp nếu tuân theo quy tắc safe-string của LDIF; nếu không, dùng **Base64**.

### 6.1. Giá trị văn bản UTF-8

Ví dụ:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: inetOrgPerson
uid: linh
cn: Nguyễn Văn Linh
sn: Nguyễn
~~~

File phải được lưu bằng encoding phù hợp (thường là **UTF-8**). Không lưu thành UTF-16 hoặc một code page địa phương rồi hy vọng mọi LDAP client tự đoán đúng.

### 6.2. Cú pháp Base64

LDIF dùng hai dấu hai chấm liền nhau để chỉ giá trị Base64:

~~~ldif
attributeName:: BASE64_DATA
~~~

Ví dụ giá trị byte:

~~~ldif
jpegPhoto:: AAECAwQ=
~~~

Chuỗi **AAECAwQ=** minh họa các byte **00 01 02 03**; đây không phải một bức ảnh hợp lệ. Dữ liệu thực tế có thể là ảnh, chứng thư, khóa công khai hoặc binary attribute tùy schema.

### 6.3. Khi nào cần Base64?

Nên dùng Base64 khi giá trị không thể biểu diễn an toàn dưới dạng safe-string, chẳng hạn:

- Có byte **NUL**, CR hoặc LF bên trong giá trị.
- Là dữ liệu **binary** thay vì văn bản UTF-8.
- Bắt đầu bằng khoảng trắng, dấu hai chấm hoặc dấu nhỏ hơn theo quy tắc LDIF.
- Không phải chuỗi UTF-8 hợp lệ.
- Có khoảng trắng đầu/cuối mà việc lưu/đọc qua công cụ có thể làm mất hoặc gây mơ hồ.

Base64 **không phải mã hóa bảo mật**. Ai có file LDIF đều có thể giải mã giá trị. Không dùng Base64 để “bảo vệ” mật khẩu, token, private key hoặc thông tin cá nhân.

### 6.4. Đừng nhầm dấu hai chấm đơn, kép và URL value

| Cú pháp | Ý nghĩa |
| --- | --- |
| **cn: Linh Nguyen** | Giá trị văn bản trực tiếp |
| **jpegPhoto:: AAECAwQ=** | Giá trị Base64 |
| **photo:< file:///tmp/photo.jpg** | Giá trị tham chiếu URL trong LDIF |

**:<** là cơ chế URL value theo LDIF. Client có thể dereference URL tùy implementation và policy; không phải mọi tool đều hỗ trợ giống nhau. Không import LDIF không tin cậy có URL tùy ý trỏ tới file nội bộ hoặc host ngoài. Cần kiểm soát scheme, vị trí và quyền đọc file nếu dùng tính năng này.

## 7. Line folding: xuống dòng mà không làm đổi giá trị

LDIF cho phép **fold** một dòng dài thành nhiều dòng vật lý. Dòng tiếp nối bắt đầu bằng đúng một dấu cách; khi đọc, client bỏ dấu cách đầu tiên và nối phần còn lại vào dòng trước.

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
description: Backend engineer working on directory integration
~~~

Biểu diễn gấp dòng minh họa:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
description: Backend engineer working on
 directory integration
~~~

Khi parser đọc, giá trị description là:

~~~text
Backend engineer working on directory integration
~~~

**Khoảng trắng đầu dòng continuation chỉ là dấu folding**, không phải một khoảng trắng mới trong giá trị. Nếu muốn giá trị thật có khoảng trắng ở vị trí đó, phải biểu diễn/encode cẩn thận theo quy tắc LDIF.

### 7.1. Không nhầm continuation với một attribute mới

~~~ldif
description: Backend engineer
 working on LDAP
~~~

Dòng thứ hai bắt đầu bằng space nên là phần tiếp nối của description. Nếu bỏ space:

~~~ldif
description: Backend engineer
working on LDAP
~~~

thì dòng **working on LDAP** không còn là một attribute description hợp lệ; file có thể bị parser từ chối. Dùng formatter LDIF chuẩn thay vì tự wrap chuỗi tùy ý.

### 7.2. Không cắt giữa byte UTF-8

Khi fold một dòng chứa Unicode nhiều byte, không nên chia giữa một chuỗi byte UTF-8. Công cụ ghi LDIF nên fold theo ranh giới ký tự, không tạo file mà client khác giải mã thành ký tự hỏng.

## 8. Change type: add

Change record với **changetype: add** tạo một entry:

~~~ldif
dn: uid=binh,ou=people,dc=lab,dc=example
changetype: add
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Binh Le
sn: Le
mail: binh@lab.example
~~~

Một record add chứa các attribute của entry, tương tự content record nhưng có **changetype: add**. DN cha phải tồn tại trước nếu server không tự tạo cây cha.

### 8.1. Thực thi add

Với content LDIF:

~~~bash
ldapadd -x -H "$LDAP_URI" \
  -D "$WRITER_DN" -W \
  -f people.ldif
~~~

Với change record **changetype: add**, dùng công cụ chấp nhận change records như:

~~~bash
ldapmodify -x -H "$LDAP_URI" \
  -D "$WRITER_DN" -W \
  -f add-person.ldif
~~~

Tên file chỉ là ví dụ; **LDAP_URI** và **WRITER_DN** cần được định nghĩa cho lab, TLS phải được xác minh và tài khoản phải có quyền Add tại nhánh đó.

### 8.2. Các lỗi thường gặp khi add

| LDAP result | Nguyên nhân |
| ---: | --- |
| **68 entryAlreadyExists** | DN đã tồn tại |
| **32 noSuchObject** | DN cha/base không tồn tại hoặc không được thấy |
| **65 objectClassViolation** | Thiếu MUST, objectClass chain sai hoặc attribute không được phép |
| **17 undefinedAttributeType** | Attribute chưa được định nghĩa trong schema |
| **21 invalidAttributeSyntax** | Giá trị sai syntax |
| **50 insufficientAccessRights** | Bind identity không có quyền Add |
| **64 namingViolation** | DN/RDN không tuân naming rule |

Nếu add thất bại, không xóa entry cũ hoặc cấp quyền admin ngay. Trước tiên xác định **DN, schema, bind identity và result code**.

## 9. Change type: delete

Một change record xóa entry:

~~~ldif
dn: uid=binh,ou=people,dc=lab,dc=example
changetype: delete
~~~

Thực thi:

~~~bash
ldapmodify -x -H "$LDAP_URI" \
  -D "$WRITER_DN" -W \
  -f delete-person.ldif
~~~

Hoặc dùng lệnh **ldapdelete** theo cú pháp DN riêng của công cụ. **changetype: delete** trong file LDIF change record là lựa chọn hữu ích khi muốn review thao tác theo cùng định dạng.

### 9.1. Delete không phải xóa một attribute

Phân biệt:

~~~ldif
# Xóa toàn bộ entry:
dn: uid=binh,ou=people,dc=lab,dc=example
changetype: delete
~~~

~~~ldif
# Xóa attribute mail khỏi entry:
dn: uid=binh,ou=people,dc=lab,dc=example
changetype: modify
delete: mail
-
~~~

Thao tác thứ hai giữ entry và các attribute khác. Nếu **mail** không tồn tại, server có thể trả **noSuchAttribute (16)**. Nếu DN không tồn tại hoặc bị ẩn, delete entry có thể trả **noSuchObject (32)**.

### 9.2. Không xóa entry cha khi còn con

Nhiều LDAP server không cho xóa một entry có subordinate entries. Phải dọn các entry con theo quy trình phù hợp trước khi xóa OU cha. Một file LDIF delete không mặc định xóa đệ quy toàn subtree.

Xóa user còn có thể để lại DN cũ trong **member**, **manager**, **uniqueMember** hoặc attribute tham chiếu khác. Server có thể cung cấp referential integrity overlay/plugin; nếu không, ứng dụng cần quy trình cập nhật tham chiếu. Không giả định xóa entry tự động xóa mọi liên kết ở entry khác.

## 10. Change type: modify

Modify record có các change specification. Các loại cơ bản:

| Change | Ý nghĩa |
| --- | --- |
| **add** | Thêm một hoặc nhiều giá trị cho attribute |
| **delete** | Xóa toàn bộ attribute hoặc một giá trị cụ thể |
| **replace** | Thay tập giá trị hiện tại bằng tập giá trị mới |

Một change specification được kết thúc bằng dòng dấu gạch ngang. Một ModifyRequest có thể chứa nhiều change specification cho cùng DN.

### 10.1. ADD một giá trị

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
add: mail
mail: linh.work@lab.example
-
~~~

Nếu attribute đã tồn tại với giá trị khác và schema cho phép đa trị, server thêm giá trị mới. Nếu giá trị đó đã tồn tại, có thể nhận **attributeOrValueExists (20)**. Nếu attribute là SINGLE-VALUE, thêm giá trị thứ hai có thể nhận **constraintViolation (19)**.

### 10.2. DELETE toàn bộ attribute

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
delete: description
-
~~~

Không có dòng **description:** sau change spec, vì yêu cầu là xóa toàn attribute. Nếu attribute không tồn tại, server thường trả **noSuchAttribute (16)**.

### 10.3. DELETE một giá trị cụ thể

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
delete: mail
mail: linh.work@lab.example
-
~~~

Chỉ giá trị **linh.work@lab.example** được yêu cầu xóa; các giá trị mail khác được giữ lại. Nếu giá trị không tồn tại, server có thể trả code 16. Đối với attribute đa trị, cách này chính xác hơn việc đọc cả tập rồi REPLACE snapshot cũ.

### 10.4. REPLACE tập giá trị

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
replace: mail
mail: linh.primary@lab.example
mail: linh.backup@lab.example
-
~~~

REPLACE thay tập giá trị hiện tại bằng hai giá trị trong change spec. Nếu không có dòng giá trị sau **replace: mail**, semantics là xóa attribute (cần cân nhắc schema và MUST/MAY). Với dữ liệu đa trị, REPLACE dễ ghi đè cập nhật đồng thời từ client khác nếu nó được tạo từ một snapshot cũ.

### 10.5. Nhiều change specification trong một ModifyRequest

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
replace: description
description: Senior engineer
-
add: mail
mail: linh.work@lab.example
-
delete: mail
mail: linh.old@lab.example
-
~~~

Một ModifyRequest tác động lên **một entry**. LDAP server xử lý các modification của cùng request như một đơn vị nguyên tử: hoặc toàn bộ thay đổi hợp lệ được áp dụng, hoặc không thay đổi nào được áp dụng. Điều đó **không biến nhiều record trong một file LDIF thành transaction chung**.

### 10.6. increment là extension

Một số LDAP client/server hỗ trợ **Modify-Increment** theo RFC 4525, ví dụ tăng giá trị integer:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
increment: loginCount
loginCount: 1
-
~~~

Đây là **extension**, không phải mọi directory server đều hỗ trợ. Attribute phải có syntax/matching phù hợp và server phải công bố/hỗ trợ control/operation tương ứng. Không dùng **increment** như một thao tác LDIF phổ quát khi chưa kiểm tra server.
## 11. Change type: modrdn / đổi DN

Đổi RDN của entry được mô tả bằng **changetype: modrdn**:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modrdn
newrdn: uid=linh.nguyen
deleteoldrdn: 1
~~~

Ý nghĩa:

- **dn** là DN hiện tại của entry.
- **newrdn** là RDN mới, không phải full DN.
- **deleteoldrdn: 1** yêu cầu xóa giá trị RDN cũ khỏi entry khi phù hợp.
- **deleteoldrdn: 0** giữ lại giá trị cũ như một attribute value nếu server hỗ trợ và schema cho phép.

### 11.1. Move entry sang OU khác

Để đổi superior DN, có thể dùng **newsuperior**:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modrdn
newrdn: uid=linh.nguyen
deleteoldrdn: 1
newsuperior: ou=engineering,dc=lab,dc=example
~~~

DN mới dự kiến:

~~~text
uid=linh.nguyen,ou=engineering,dc=lab,dc=example
~~~

DN cha mới phải tồn tại và tài khoản bind phải có quyền rename/move tại cả vị trí nguồn và đích. Một số server có policy riêng về **cross-context move**, referral hoặc subordinate naming.

### 11.2. Rename DN không tự cập nhật mọi DN tham chiếu

Nếu entry Linh được tham chiếu trong:

~~~ldif
dn: cn=developers,ou=groups,dc=lab,dc=example
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=lab,dc=example
~~~

việc rename Linh không bảo đảm attribute **member** ở entry group tự đổi sang DN mới trên mọi directory server. Kiểm tra referential integrity behavior của server hoặc cập nhật các tham chiếu theo quy trình được kiểm soát. Không giữ cache DN cũ mà không có chiến lược refresh.

## 12. Dòng URL value và dữ liệu binary

LDIF có cú pháp:

~~~ldif
photo:< file:///var/lib/ldap-import/linh.jpg
~~~

Đây là **URL value**, trong đó file được công cụ import dereference theo khả năng implementation. Nó không giống:

~~~ldif
photo:: AAECAwQ=
~~~

Dòng thứ nhất tham chiếu một URL; dòng thứ hai mang bytes trực tiếp dưới dạng Base64. Khi dùng URL:

- Xác nhận client import hỗ trợ URL value.
- Kiểm soát scheme, đường dẫn, quyền đọc và vị trí file.
- Không cho file LDIF không tin cậy dereference **file://** hoặc URL nội bộ tùy ý.
- Kiểm tra kích thước dữ liệu, encoding và cách client gửi giá trị.

Với dữ liệu binary lớn, cân nhắc công cụ migration chuyên dụng, không nhồi toàn bộ nội dung vào một file văn bản khổng lồ nếu quy trình không cần thiết.

## 13. Export LDIF từ directory

Một lệnh **ldapsearch** có thể xuất kết quả theo LDIF:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "$PEOPLE_DN" -s sub \
  '(objectClass=inetOrgPerson)' \
  dn objectClass uid cn sn mail description \
  > people-export.ldif
~~~

Các tùy chọn:

| Tùy chọn | Ý nghĩa thường dùng trong OpenLDAP client |
| --- | --- |
| **-L** | In kết quả theo LDIFv1 |
| **-LL** | Bỏ comment |
| **-LLL** | Bỏ version line và comment |
| **-b** | Search base DN |
| **-s** | Search scope: base, one, sub |
| **-W** | Nhập mật khẩu tương tác |
| **-H** | LDAP URI |

**ldapsearch -LLL** thuận tiện khi muốn tạo file record không có comment/version line. Nếu muốn lưu cả version line theo mục đích interchange, dùng tùy chọn LDIF thích hợp của client và kiểm tra file sau export.

### 13.1. Export không mặc định là backup hoàn chỉnh

Một truy vấn ldapsearch chỉ xuất những entry/attribute mà:

- Filter và base/scope đã chọn.
- Bind identity có quyền search/read.
- Client yêu cầu và server trả về.
- Server cho phép truy cập các operational attribute được yêu cầu.

Nó có thể không bao gồm **password hash, operational attributes, replication metadata, ACL, schema configuration hoặc dữ liệu ngoài suffix**. Vì vậy **LDIF export từ ldapsearch không tương đương backup vật lý đầy đủ**. Với OpenLDAP, **slapcat** là một công cụ backup/export backend offline hoặc theo cách quản trị phù hợp; với AD DS cần cơ chế backup/restore của Microsoft.

### 13.2. Không export dữ liệu nhạy cảm tùy tiện

Một LDIF có thể chứa **mail, phone, manager DN, group membership, userPassword hoặc binary attribute**. Trước khi export:

1. Xác định mục đích và phạm vi dữ liệu cần lấy.
2. Chỉ yêu cầu attribute cần thiết trong ldapsearch.
3. Lưu file trong thư mục được kiểm soát quyền.
4. Mã hóa ổ đĩa/kênh truyền và bảo vệ artifact nếu có dữ liệu nhạy cảm.
5. Che hoặc loại secret trước khi commit fixture.
6. Xóa file export tạm theo chính sách lưu trữ.

**Base64 không phải encryption**; người nhận file có thể giải mã ngay.

## 14. Import LDIF: thứ tự, tính lặp lại và lỗi

Ví dụ import content LDIF:

~~~bash
ldapadd -x -H "$LDAP_URI" \
  -D "$WRITER_DN" -W \
  -f people-export.ldif
~~~

Với change records:

~~~bash
ldapmodify -x -H "$LDAP_URI" \
  -D "$WRITER_DN" -W \
  -f changes.ldif
~~~

Trước khi chạy trên dữ liệu quan trọng:

- Xác nhận **endpoint**, suffix, base DN và tài khoản bind.
- Kiểm tra các entry cha đã tồn tại.
- Xem file LDIF có **content records** hay **change records**.
- Xác nhận schema đích có đủ objectClass/attributeTypes.
- Xác định thứ tự add/rename/delete và quan hệ DN.
- Thử trên môi trường staging/lab với bản dữ liệu đã được làm sạch.

### 14.1. LDIF không có transaction toàn file

Giả sử file có ba record:

~~~text
Record 1: ADD uid=an     -> success
Record 2: MODIFY uid=linh -> success
Record 3: ADD uid=binh   -> failure (schema)
~~~

Sau lỗi ở record 3, hai record đầu **có thể đã được áp dụng**. Không có bảo đảm toàn bộ file tự rollback. Khi chạy lại nguyên file, record 1 có thể báo **entryAlreadyExists (68)**, record 2 có thể bị áp dụng lần nữa, còn record 3 tiếp tục thất bại.

Vì vậy:

- Chia migration thành batch nhỏ, có checkpoint.
- Ghi nhận DN và kết quả từng record.
- Thiết kế thao tác có tính idempotent nếu có thể.
- Đọc lại trạng thái directory trước khi retry.
- Chuẩn bị phương án rollback/compensation có kiểm thử.

### 14.2. Idempotency và duplicate

| Thao tác | Lần đầu | Chạy lại |
| --- | --- | --- |
| ADD entry | Có thể thành công | Có thể nhận **68 entryAlreadyExists** |
| ADD attribute value | Có thể thành công | Có thể nhận **20 attributeOrValueExists** |
| REPLACE attribute | Đặt tập giá trị mới | Có thể tiếp tục đặt cùng tập giá trị |
| DELETE attribute | Có thể thành công | Có thể nhận **16 noSuchAttribute** |
| DELETE entry | Có thể thành công | Có thể nhận **32 noSuchObject** |
| MODRDN | Đổi DN | DN cũ có thể không còn tồn tại, cần xác minh |

Không coi mọi lỗi duplicate là thành công mà không xác minh trạng thái cuối cùng. Ví dụ entry đã tồn tại có thể là một object khác cùng DN do một quy trình trước tạo ra.

### 14.3. Thứ tự import các entry

Nếu cây có:

~~~text
dc=lab,dc=example
└── ou=people
    └── uid=linh
~~~

thì tạo suffix/OU cha trước khi add entry con. Nếu một migration chuyển entry sang OU mới, đảm bảo OU mới tồn tại trước **modrdn/newsuperior**. Nếu xóa subtree, dọn các entry con theo thứ tự phù hợp trước khi xóa parent.

## 15. Kiểm tra LDIF bằng công cụ và đọc lỗi

### 15.1. Xem entry sau import

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b 'uid=linh,ou=people,dc=lab,dc=example' -s base \
  '(objectClass=*)' dn objectClass uid cn sn mail
~~~

Kết quả là một content record LDIF. So sánh **DN, objectClass và attribute values** với file mong muốn; không chỉ nhìn dòng **adding new entry** từ ldapadd.

### 15.2. Lỗi phổ biến

| Result code | Ý nghĩa | Hướng xử lý |
| ---: | --- | --- |
| **16 noSuchAttribute** | Attribute/value cần xóa không tồn tại | Đọc lại entry, xử lý race hoặc thay đổi trước đó |
| **17 undefinedAttributeType** | Attribute chưa có trong schema | Kiểm tra tên và schema |
| **19 constraintViolation** | Vi phạm constraint, ví dụ SINGLE-VALUE | Kiểm tra số giá trị và ràng buộc |
| **20 attributeOrValueExists** | Giá trị đã tồn tại | Xác minh idempotency |
| **21 invalidAttributeSyntax** | Giá trị sai syntax | Kiểm tra encoding/kiểu |
| **32 noSuchObject** | DN không tồn tại hoặc không nhìn thấy | Kiểm tra base/parent/ACL |
| **34 invalidDNSyntax** | DN sai cú pháp | Kiểm tra RDN và escaping |
| **49 invalidCredentials** | Bind sai | Kiểm tra bind DN/secret |
| **50 insufficientAccessRights** | Không đủ quyền | Kiểm tra ACL với bind identity |
| **64 namingViolation** | DN vi phạm naming rule | Kiểm tra RDN |
| **65 objectClassViolation** | Entry không hợp lệ theo objectClass/schema | Kiểm tra MUST/MAY/structural chain |
| **68 entryAlreadyExists** | DN đã tồn tại | Kiểm tra import trùng |
| **69 objectClassModsProhibited** | Thay đổi objectClass bị cấm | Không thay structural class tùy tiện |

### 15.3. Diagnostic message là gợi ý, không phải schema contract

Server có thể trả diagnostic message như:

~~~text
additional info: object class violation
~~~

hoặc thông báo cụ thể hơn về attribute. Chuỗi message phụ thuộc vendor và phiên bản; automation nên dựa vào **result code**, không parse một câu tiếng Anh cứng để quyết định migration. Khi cần điều tra sâu, xem server logs có kiểm soát và giữ nguyên request ID/operation context.

## 16. Ánh xạ LDIF sang Spring Data LDAP ODM

LDIF và entity Java có thể mô tả cùng một entry theo hai hình thức:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@lab.example
mail: linh.work@lab.example
~~~

~~~java
import java.util.Set;
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
    private Set<String> emails;

    // Constructor không tham số, getters/setters được lược bỏ.
}
~~~

| LDIF | ODM |
| --- | --- |
| **dn:** | **@Id Name dn** |
| **objectClass:** | **@Entry(objectClasses = ...)** |
| **uid:** | **@Attribute(name = "uid")** |
| **cn:** | **@Attribute(name = "cn")** |
| **sn:** | **@Attribute(name = "sn")** |
| Nhiều dòng **mail:** | **Set<String> emails** hoặc collection phù hợp |

**@Entry(base = "ou=people")** thường tương đối với base DN của ContextSource. DN trong LDIF đầy đủ; entity **@Id** lưu tên tương ứng theo API ODM. Cần kiểm thử cách tạo/đọc DN với cấu hình thực tế.

### 16.1. Attribute nhiều giá trị trong Java

Vì LDIF có hai dòng mail, Java field có thể dùng collection phù hợp:

~~~java
@Attribute(name = "mail")
private Set<String> emails;
~~~

Không ánh xạ attribute đa trị vào **String** rồi giả định framework tự nối mọi giá trị bằng dấu phẩy. Việc chuyển kiểu phải phản ánh **schema, cardinality và nghiệp vụ**.

Một số attribute có syntax DN, ví dụ **member**; có thể dùng **Set<Name>** nếu ODM converter và phiên bản Spring LDAP hỗ trợ kiểu đó. Luôn kiểm thử dữ liệu đọc/ghi trên directory mục tiêu.

### 16.2. LDIF không phải một phần của @Entry

**@Entry** khai báo objectClass và base DN cho mapping; nó không nhúng nội dung file LDIF. Không viết:

~~~java
// Không có annotation mặc định kiểu:
// @Entry(ldif = "people.ldif")
~~~

Nếu ứng dụng cần nạp LDIF, hãy thực hiện qua **quy trình import/migration** bằng công cụ LDAP hoặc một parser LDIF phù hợp, sau đó dùng Spring LDAP để đọc/kiểm chứng. Không biến việc khởi động ứng dụng web thành thao tác import lại toàn bộ file ở mỗi lần deploy.

## 17. Thực hiện CRUD tương ứng bằng LdapTemplate

Nếu dữ liệu đã được biểu diễn thành Java object/Attributes, **LdapTemplate** cung cấp các thao tác tương ứng:

| Mục đích LDIF | Spring LDAP API thường dùng |
| --- | --- |
| Content record / changetype add | **bind(...)** |
| Add entry đã tồn tại | **Không dùng bind để ghi đè tùy tiện**; kiểm tra semantics và dùng API phù hợp |
| Modify add/replace/delete attribute | **modifyAttributes(...)** |
| Delete entry | **unbind(...)** |
| Modrdn / move | **rename(...)** |
| Read/export entry | **lookup(...) / search(...)** |

Ví dụ thêm một entry qua **LdapTemplate**:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.core.LdapTemplate;

public final class PersonProvisioner {
    private final LdapTemplate ldapTemplate;

    public PersonProvisioner(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addPerson(Name relativeDn) {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("objectClass", "top");
        attrs.get("objectClass").add("person");
        attrs.get("objectClass").add("organizationalPerson");
        attrs.get("objectClass").add("inetOrgPerson");
        attrs.put("uid", "linh");
        attrs.put("cn", "Linh Nguyen");
        attrs.put("sn", "Nguyen");
        attrs.put("mail", "linh@lab.example");

        ldapTemplate.bind(relativeDn, null, attrs);
    }
}
~~~

Ví dụ giả định **relativeDn** là **uid=linh,ou=people** tương đối với ContextSource base **dc=lab,dc=example**, entry chưa tồn tại và bind identity có quyền Add. **BasicAttributes(true)** biểu diễn attribute IDs không phân biệt chữ hoa/chữ thường theo constructor được chọn. Các MUST/objectClass phải hợp lệ theo schema server.

### 17.1. Sửa một attribute

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem replaceMail = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute("mail", "linh.new@lab.example")
);
ldapTemplate.modifyAttributes(
    "uid=linh,ou=people",
    new ModificationItem[]{replaceMail}
);
~~~

Đoạn mã nằm trong service có **ldapTemplate**; nó tương ứng change record **replace: mail**. Nếu chỉ muốn thêm một địa chỉ email, dùng **ADD_ATTRIBUTE** thay vì REPLACE toàn tập.

### 17.2. Xóa entry và đổi DN

~~~java
ldapTemplate.unbind("uid=linh,ou=people");
ldapTemplate.rename(
    "uid=linh,ou=people",
    "uid=linh.nguyen,ou=people"
);
~~~

Đây là hai ví dụ độc lập, không gọi tuần tự để xóa rồi rename cùng một entry. **unbind** xóa entry; **rename** thay đổi DN. Cả hai đều cần quyền phù hợp và xử lý tham chiếu DN liên quan.

## 18. Kiểm thử LDIF và directory bằng integration test

Một unit test mock **LdapTemplate** không kiểm tra cú pháp LDIF, schema server, ACL hay result code thật. Nên có **directory fixture** và kiểm thử import/search/modify trong môi trường riêng.

### 18.1. Kịch bản test

| Ca kiểm thử | Dữ liệu/thao tác | Kỳ vọng |
| --- | --- | --- |
| Parse content record | Một entry có DN và objectClass | Tạo đúng entry |
| Multi-valued attribute | Hai dòng mail | Đọc ra hai giá trị |
| Unicode | cn có tiếng Việt | Giữ nguyên ký tự sau import/export |
| Base64 binary | Attribute chứa bytes | Đọc lại đúng byte |
| Folded line | Description có continuation | Giá trị được nối đúng |
| ADD entry duplicate | Import lại cùng DN | entryAlreadyExists (68) |
| MODIFY ADD duplicate | Thêm lại cùng value | attributeOrValueExists (20) |
| REMOVE missing value | Xóa giá trị không có | noSuchAttribute (16) |
| Missing MUST | Xóa sn cuối cùng | objectClassViolation (65) |
| Reader attempts write | Bind reader rồi Modify | insufficientAccessRights (50) nếu ACL lab cấu hình vậy |
| Modrdn | Đổi RDN/move OU | DN mới đúng, parent tồn tại |
| Multi-record failure | Record cuối sai schema | Các record trước có thể đã commit |

### 18.2. Integration test đọc entry đã import

Ví dụ JUnit 5 với Spring Boot:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class LdifDirectoryIntegrationTest {
    @Autowired
    DirectoryPersonRepository repository;

    @Test
    void readsMultiValuedMailFromImportedEntry() {
        DirectoryPerson person =
            repository.findByUid("linh").orElseThrow();

        assertEquals("Linh Nguyen", person.getCommonName());
        assertTrue(
            person.getEmails().contains("linh@lab.example")
        );
        assertTrue(
            person.getEmails().contains("linh.work@lab.example")
        );
    }
}
~~~

Đây là **mẫu integration test**. Để chạy cần repository có **findByUid**, entity có getter, directory lab đã import entry fixture với hai mail, và bean LDAP được cấu hình đúng. Test không tự import file LDIF; quá trình chuẩn bị fixture cần được thực hiện trước test hoặc trong lifecycle test có kiểm soát.

### 18.3. Xác minh import bằng CLI và Java

Quy trình thực hành:

1. Import LDIF bằng **ldapadd/ldapmodify** trong lab.
2. Dùng **ldapsearch** truy vấn DN cụ thể và các attribute cần kiểm tra.
3. Đọc entry qua **LdapRepository.findByUid(...)** hoặc **LdapTemplate.lookup(...)**.
4. So sánh DN, objectClass, giá trị đơn/đa trị và Unicode.
5. Thử Modify bằng writer và thử cùng thao tác bằng reader.
6. Kiểm tra result code, đọc lại entry sau mỗi thao tác.
7. Dọn fixture theo thứ tự child trước parent.

### 18.4. Không import file LDIF tự động mỗi lần ứng dụng start

Nếu ứng dụng gọi **ldapadd** hoặc import toàn bộ LDIF ở mọi lần khởi động:

- Các entry đã tồn tại có thể làm startup fail với code 68.
- Một record lỗi có thể khiến file chỉ được áp dụng một phần.
- Nhiều pod start cùng lúc có thể cạnh tranh Add/Modify.
- Thay đổi fixture có thể vô tình ghi đè dữ liệu người dùng.
- Secret hoặc PII trong file có thể xuất hiện trong artifact/log.

Đối với dữ liệu production, hãy dùng **migration job có kiểm soát, checkpoint, audit và phê duyệt phù hợp**; không biến LDIF bootstrap thành cơ chế đồng bộ dữ liệu vô điều kiện.

## 19. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Parser báo lỗi ở dòng sau | Thiếu dòng trống, continuation sai hoặc thiếu attribute separator | Kiểm tra record boundary và folding |
| **dn:** không parse được | DN sai cú pháp hoặc RDN chưa escape | Dùng parser DN và RFC 4514 |
| **entryAlreadyExists (68)** | Add lại DN đã tồn tại | Đọc trạng thái trước khi retry |
| **noSuchObject (32)** | Parent/base DN không tồn tại hoặc không thấy | Import parent trước, kiểm tra ACL |
| **undefinedAttributeType (17)** | Attribute chưa có trong schema | Sửa tên hoặc provision schema hợp lệ |
| **objectClassViolation (65)** | Thiếu MUST, objectClass chain sai hoặc attribute không được phép | Kiểm tra schema/MUST/MAY |
| **constraintViolation (19)** | SINGLE-VALUE hoặc constraint khác | Kiểm tra cardinality và rule |
| **invalidAttributeSyntax (21)** | Giá trị sai syntax/encoding | Validate value và Base64/UTF-8 |
| **insufficientAccessRights (50)** | Bind identity thiếu quyền | Xem ACL tại DN/attribute/operation |
| Giá trị tiếng Việt bị hỏng | File sai encoding hoặc bị fold giữa byte UTF-8 | Lưu UTF-8 và fold theo ranh giới ký tự |
| Base64 không giải mã | Dữ liệu Base64 hỏng hoặc thiếu dấu hai chấm | Kiểm tra cú pháp **attr:: value** |
| Attribute đa trị thành một chuỗi dấu phẩy | Viết nhiều value trên một dòng | Lặp lại attribute description |
| Xóa OU thất bại | Còn subordinate entry | Xóa con trước theo quy trình |
| Rename thành công nhưng group member cũ | DN reference không tự cập nhật | Kiểm tra referential integrity/cập nhật tham chiếu |
| Import file dừng giữa chừng | Record sau lỗi; file không atomic | Đọc trạng thái, resume theo checkpoint |
| Repository không đọc được entry vừa import | Sai ContextSource base, @Entry base hoặc mapping | So sánh full DN và relative DN |

### 19.1. Phân biệt lỗi file với lỗi directory

| Nhóm | Ví dụ | Công cụ kiểm tra |
| --- | --- | --- |
| **LDIF syntax** | Thiếu dòng trống, continuation không đúng | LDIF parser/client |
| **DN syntax** | Dấu phẩy trong RDN chưa escape | JNDI LdapName, ldapsearch |
| **Schema** | Thiếu sn, attribute sai syntax | Server result code, subschema |
| **ACL** | Reader không được Modify | Cùng request với bind identity trong lab |
| **Connectivity/TLS** | Không mở được LDAPS | Connect/read logs, truststore |
| **Spring mapping** | Sai @Attribute hoặc @Entry base | ODM test, LdapTemplate readback |
| **Concurrency** | REPLACE từ snapshot cũ | Hai writer integration test |

## 20. Bài thực hành tổng hợp và câu hỏi ôn tập

### 20.1. Bài thực hành

Tạo directory lab với suffix **dc=lab,dc=example**, nhánh **ou=people** và **ou=groups**. Sau đó thực hiện:

1. Viết **people.ldif** có ba content record: Linh, An và Binh; dùng đầy đủ objectClass chain cho inetOrgPerson.
2. Thêm **mail** hai giá trị cho Linh và để Binh không có mail.
3. Thêm **description** có tiếng Việt; export và xác minh UTF-8.
4. Tạo một binary attribute fixture bằng Base64 và đọc lại byte trong test.
5. Fold một dòng description dài, import và so sánh giá trị sau parse.
6. Dùng **ldapadd** import content records, sau đó dùng **ldapsearch** xác minh.
7. Viết change record **modify** để ADD một mail, REPLACE description và DELETE một giá trị mail; kiểm tra từng kết quả.
8. Viết change record **modrdn** chuyển Linh sang OU khác trong lab, kiểm tra DN mới và các member reference.
9. Tạo reader chỉ có quyền đọc và writer có quyền Modify; chạy cùng một thay đổi mail với hai tài khoản.
10. Import lại file có DN đã tồn tại, ghi nhận code 68 và thiết kế cách xử lý idempotent.
11. Ánh xạ entry sang **DirectoryPerson** với **@Entry, @Id, @Attribute** và collection cho mail.
12. Viết integration test đọc multi-valued mail, Unicode và DN.
13. Tạo một record cố ý vi phạm MUST, xác minh server từ chối và không ghi một phần ModifyRequest.
14. Viết kế hoạch migration: checkpoint, retry, rollback/compensation và bảo vệ file LDIF nhạy cảm.

### 20.2. Câu hỏi ôn tập

1. LDIF khác LDAP protocol và Java ODM như thế nào?
2. Một content record gồm những thành phần nào? Dòng trống có vai trò gì?
3. DN trong LDIF thường được biểu diễn đầy đủ ra sao so với base DN của ContextSource?
4. **objectClass**, **MUST** và **MAY** ảnh hưởng thế nào tới việc import entry?
5. Tại sao hai giá trị mail phải được biểu diễn bằng hai dòng attribute?
6. Khi nào cần dùng **Base64**? Base64 có bảo vệ secret không?
7. Một dòng continuation bắt đầu bằng space được parser xử lý thế nào?
8. Khác biệt giữa content record và change record là gì?
9. **add**, **delete**, **replace** trong modify record khác **changetype: delete** ra sao?
10. Vì sao một ModifyRequest có nhiều change specification có tính nguyên tử trong khi cả file LDIF không có transaction chung?
11. **newrdn**, **deleteoldrdn**, **newsuperior** dùng trong modrdn như thế nào?
12. Tại sao rename DN không bảo đảm mọi attribute member ở entry khác tự đổi?
13. **ldapsearch -LLL** và **ldapadd/ldapmodify** được dùng cho công việc gì?
14. Spring LDAP ODM ánh xạ dn/objectClass/attribute vào Java entity qua annotation nào?
15. Tại sao không import LDIF toàn bộ mỗi lần ứng dụng Spring Boot khởi động?

### 20.3. Ghi nhớ

LDIF biểu diễn **entry hoặc thay đổi entry** theo một định dạng văn bản có cấu trúc. **Content record** mô tả DN và attributes; **change record** bổ sung **changetype** để thực hiện add, delete, modify hoặc modrdn. Dữ liệu được viết dưới dạng UTF-8 khi an toàn, hoặc Base64 khi cần; dòng continuation bắt đầu bằng một dấu cách và được nối lại khi parse. Attribute đa trị được lặp thành nhiều dòng, không ghép bằng dấu phẩy.

Khi import, directory server vẫn áp dụng **DN hierarchy, objectClass, schema, ACL và chính sách**. Một ModifyRequest trên một entry có ngữ nghĩa nguyên tử nhưng nhiều record trong một file không tạo transaction toàn file. Hãy dùng **ldapadd/ldapmodify** để import, **ldapsearch** để xác minh, và **Spring Data LDAP ODM/LdapTemplate** để làm việc với Java object. Bảo vệ file LDIF như dữ liệu thật, không coi Base64 là encryption và không tự động import lại file trong mỗi lần deploy.

## Tài liệu tham khảo

- [RFC 2849 — The LDAP Data Interchange Format (LDIF)](https://www.rfc-editor.org/rfc/rfc2849.html): cú pháp LDIFv1, content/change records, Base64, URL values và line folding.
- [RFC 4514 — LDAP Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html): biểu diễn và escaping DN/RDN.
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): Add, Delete, Modify, ModifyDN, Search và result codes.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): objectClass, attributeTypes, DIT và schema.
- [RFC 4517 — LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517.html): syntax và matching rules của attribute.
- [RFC 4525 — LDAP Modify-Increment Extension](https://www.rfc-editor.org/rfc/rfc4525.html): extension increment cho LDAP Modify.
- [OpenLDAP — ldapadd manual](https://man7.org/linux/man-pages/man1/ldapadd.1.html): nhập LDIF content records.
- [OpenLDAP — ldapmodify manual](https://man7.org/linux/man-pages/man1/ldapmodify.1.html): thực thi change records.
- [OpenLDAP — ldapsearch manual](https://man7.org/linux/man-pages/man1/ldapsearch.1.html): tìm kiếm và xuất LDIF.
- [OpenLDAP Administrator's Guide](https://www.openldap.org/doc/admin25/): schema, ACL, import/export và vận hành directory.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): ánh xạ entry LDAP sang Java class.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): bind, lookup, modify, rename, unbind và search.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ODM.
