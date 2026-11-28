# Cập nhật thất bại do objectClass, schema hoặc ACL

Trong **Spring Data LDAP**, việc đọc được một entry không có nghĩa ứng dụng có thể cập nhật mọi thuộc tính của entry đó. Một lệnh **LdapRepository.save(...)**, **LdapTemplate.modifyAttributes(...)** hoặc **DirContext.modifyAttributes(...)** có thể thất bại vì **objectClass** không cho phép thuộc tính, **schema** yêu cầu một giá trị khác, hoặc tài khoản **bind** không có quyền ghi theo **ACL (Access Control List)**. Ba nguyên nhân này có thể cùng xuất hiện trong một hệ thống nhưng phải được chẩn đoán và sửa theo những cách khác nhau.

Bài học thuộc chương **Chẩn đoán** của module **SPRING_DATA_LDAP**, nơi entry LDAP được tổ chức phân cấp theo **Distinguished Name (DN)**, ánh xạ sang Java object và truy cập thông qua **repository/LdapTemplate**. Nội dung hướng dẫn đọc **LDAP result code**, xác minh **objectClass, MUST/MAY, syntax, số lượng giá trị, quyền ACL**, tái hiện lỗi bằng **LDIF/ldapmodify**, đối chiếu với Java exception, thiết kế update an toàn và viết **integration test** với directory phù hợp.

> **Nguyên tắc chẩn đoán:** Bắt đầu từ **mã lỗi LDAP trả về cho đúng thao tác Modify**, không đoán nguyên nhân chỉ từ tên method `save` hoặc từ việc một câu `search` trước đó đã thành công. Đừng sửa schema, thêm quyền admin hoặc tắt kiểm tra validation chỉ để che thông báo lỗi.

## 1. Đường đi của một lệnh cập nhật trong Spring Data LDAP

Một service có thể gọi repository hoặc trực tiếp dùng `LdapTemplate`; hai đường thường đều gửi thao tác qua **Spring LDAP ContextSource** và **JNDI LDAP provider** tới server:

~~~mermaid
flowchart TD
    A["HTTP/Job: thay đổi entry"] --> B["Service: validate và authorize"]
    B --> C["Spring Data LDAP Repository.save"]
    B --> D["LdapTemplate.modifyAttributes"]
    C --> E["Spring LDAP / ODM"]
    D --> E
    E --> F["ContextSource -> JNDI"]
    F --> G["LDAP ModifyRequest tới DN"]
    G --> H{"Directory server kiểm tra"}
    H --> I["DN và sự tồn tại entry"]
    H --> J["Schema: objectClass, MUST/MAY, syntax"]
    H --> K["ACL: bind identity, thuộc tính, thao tác"]
    I --> L{"LDAPResult"}
    J --> L
    K --> L
    L -->|0| M["Update thành công"]
    L -->|65/17/21/19/69| N["Lỗi schema/objectClass"]
    L -->|50 hoặc lỗi riêng server| O["Không đủ quyền/chính sách"]
    L -->|32/34/49/...| P["Lỗi khác cần phân loại"]
~~~

Các lớp có ý nghĩa riêng:

| Tầng | Vai trò | Điều cần xác nhận |
| --- | --- | --- |
| **Java entity ODM** | Định nghĩa field và mapping LDAP qua **@Entry, @Id, @Attribute** | Field có ánh xạ sai không? @Entry có đủ objectClasses không? |
| **Repository** | Chọn DN, tạo/cập nhật entry theo mapping | Đây là create hay update? DN hiện tại có đúng không? |
| **LdapTemplate** | Gửi thao tác LDAP và dịch exception JNDI | ModificationItem thực tế là ADD, REPLACE hay REMOVE? |
| **ContextSource** | Kết nối tới host/suffix với tài khoản bind | Đúng server, đúng base DN, đúng quyền, đúng TLS chưa? |
| **LDAP server** | Áp dụng schema, ACL, chính sách và các rule dữ liệu | Result code, diagnostic message và server log cho biết gì? |

**Một tìm kiếm trả được entry** chỉ chứng minh server trả dữ liệu phù hợp với danh tính và yêu cầu search đó. Nó không bảo đảm danh tính ấy có **write permission** trên các attribute muốn sửa.

## 2. Đọc mã lỗi LDAP trước khi quyết định sửa gì

LDAPResult có **resultCode** và có thể kèm **diagnosticMessage** hoặc **matchedDN**. Chuỗi chữ trong exception của Spring/JNDI phụ thuộc provider và bản dịch ngoại lệ; mã LDAP gần với nguyên nhân giao thức hơn.

| LDAP code | Tên chuẩn | Khi gặp lúc ghi | Việc nên kiểm tra |
| ---: | --- | --- | --- |
| **0** | success | Server chấp nhận thao tác | Đọc lại nếu nghiệp vụ cần xác minh kết quả |
| **16** | noSuchAttribute | REMOVE attribute/value vốn không tồn tại | Dữ liệu cũ, race condition, thao tác REMOVE |
| **17** | undefinedAttributeType | Tên attribute không được schema nhận diện | Sai chính tả attribute, schema chưa nạp |
| **18** | inappropriateMatching | Dùng matching rule không phù hợp | Filter/compare/control và định nghĩa attribute |
| **19** | constraintViolation | Giá trị vi phạm ràng buộc dữ liệu, như SINGLE-VALUE | Số lượng giá trị, constraint tùy server |
| **20** | attributeOrValueExists | ADD attribute/value đã tồn tại | Trùng giá trị, idempotency |
| **21** | invalidAttributeSyntax | Giá trị không đúng syntax của attribute | Kiểu dữ liệu, format, encoding |
| **32** | noSuchObject | DN đích không tồn tại hoặc bị che | Base DN, rename, delete, ACL |
| **34** | invalidDNSyntax | DN không đúng cú pháp | Escape RDN/DN, parser |
| **49** | invalidCredentials | Bind không thành công | Bind DN, secret, trạng thái tài khoản |
| **50** | insufficientAccessRights | Không được phép Modify/Add/Delete | ACL với đúng bind identity, DN và attribute |
| **53** | unwillingToPerform | Server từ chối thực hiện vì chính sách/giới hạn khác | Diagnostic message và tài liệu server |
| **64** | namingViolation | Entry name vi phạm naming restrictions | RDN, naming rule, schema |
| **65** | objectClassViolation | Entry sau thay đổi không phù hợp các objectClass | MUST/MAY, structural chain, nội dung entry |
| **67** | notAllowedOnRDN | Cố xóa/thay giá trị đang thuộc RDN | DN và thao tác ModifyDN/rename |
| **69** | objectClassModsProhibited | Thay đổi objectClass bị cấm | Structural objectClass và chính sách server |

**65 không đồng nghĩa mọi lỗi schema.** Ví dụ **17** xảy ra khi tên attribute chưa được khai báo; **21** là sai syntax; **19** có thể liên quan thuộc tính đơn trị bị gán nhiều giá trị; **69** liên quan chính thao tác thay đổi objectClass bị cấm. Server cũng có thể trả **53** hoặc thông báo vendor-specific cho những quy tắc tương tự. Hãy ghi lại **kết quả thực** trên server đang dùng.

### 2.1. Khi Java chỉ có một exception chung

Một số message rút gọn như:

~~~text
org.springframework.ldap.SchemaViolationException:
  [LDAP: error code 65 - object class violation]
~~~

thường cho biết server trả lỗi về objectClass; nhưng không thể từ tên class Java suy ra đầy đủ **attribute nào** hoặc **rule MUST/MAY nào** bị vi phạm. Nhiều loại schema error được dịch qua những subclass khác nhau của Spring LDAP; cần xem **cause chain** và **LDAP diagnostic** được phép ghi log.

**Không trả nguyên diagnostic message** cho người dùng cuối nếu nó chứa DN, cấu trúc OU hoặc dữ liệu nội bộ. API công khai nên dùng thông báo an toàn, còn log có kiểm soát giữ request ID, mã LDAP và nguyên nhân gốc.

## 3. objectClass, schema, MUST/MAY và structural chain

Một LDAP entry không phải tài liệu JSON tự do. Mỗi entry có **objectClass**; các định nghĩa schema xác định **thuộc tính bắt buộc (MUST)**, **thuộc tính cho phép (MAY)**, kiểu dữ liệu, cách so khớp và ràng buộc số giá trị.

Ví dụ một người dùng theo chuỗi kế thừa objectClass:

~~~text
top (ABSTRACT)
  └── person (STRUCTURAL)
        └── organizationalPerson (STRUCTURAL)
              └── inetOrgPerson (STRUCTURAL)
~~~

Những điều quan trọng:

- Một entry **inetOrgPerson** thuộc chuỗi kế thừa **person → organizationalPerson → inetOrgPerson**. Các objectClass được liệt kê có thể nằm trong **một structural superclass chain hợp lệ**, không phải ba loại structural độc lập.
- **person** có các thuộc tính MUST **cn** và **sn**. Một entry inetOrgPerson phải đáp ứng các yêu cầu kế thừa đó.
- Thuộc tính **mail** thường được phép bởi inetOrgPerson; **description** thường được cho phép qua lớp cha. Có được phép ghi giá trị nào còn phụ thuộc syntax/ACL.
- Một attribute chỉ được ghi hợp lệ nếu được schema của entry cho phép, qua **MUST/MAY**, các lớp phụ trợ phù hợp hoặc **DIT content rule**.
- Một entry không thể vừa là **inetOrgPerson** vừa thêm structural class độc lập như **groupOfNames** chỉ để có attribute **member**. Việc thay đổi cấu trúc entry phải tuân theo quy tắc structural chain.
- **AUXILIARY objectClass** có thể mở rộng attribute được phép, nhưng việc gắn nó cũng bị chi phối bởi schema/DIT content rule và chính sách server. Không phải lớp phụ trợ bất kỳ đều được phép gắn vào mọi entry.

### 3.1. MUST và MAY không nói hết về quyền

| Câu hỏi | Ai quyết định? |
| --- | --- |
| Attribute **sn** có bắt buộc cho person không? | Schema/objectClass **MUST** |
| Attribute **mail** có được phép tồn tại trên inetOrgPerson không? | Schema/objectClass **MAY**, content rule |
| Giá trị attribute có đúng cú pháp không? | Attribute syntax, matching và server constraints |
| User reader có quyền thay mail không? | ACL/chính sách bảo mật phía server |
| Application có được phép sửa email người này không? | Authorization ở tầng nghiệp vụ |

**Một attribute hợp lệ về schema vẫn có thể bị từ chối bởi ACL.** Ngược lại, ngay cả tài khoản admin trong lab cũng không nên mặc định có thể tạo entry trái schema — quyền quản trị không thay thế định nghĩa dữ liệu hợp lệ.

## 4. Chuẩn bị dữ liệu LDIF để tái hiện

Trong directory lab, giả sử suffix **dc=lab,dc=example** và nhánh **ou=people** đã tồn tại. Entry người dùng mẫu:

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
description: Demo record
~~~

Nếu tạo entry từ đầu, **tạo cha trước, con sau** và kiểm tra root/OU không trùng. Ví dụ khai báo OU riêng:

~~~ldif
dn: ou=people,dc=lab,dc=example
objectClass: top
objectClass: organizationalUnit
ou: people
~~~

Không import lại OU nếu đã tồn tại, vì server có thể trả **entryAlreadyExists (68)**. Suffix và bind DN quản trị cần được provision hợp lệ ngoài các lệnh minh họa.

Khi kiểm thử ACL, chuẩn bị **hai tài khoản riêng**:

| Danh tính | Quyền minh họa |
| --- | --- |
| **uid=reader,ou=services,...** | Search/read dưới ou=people, **không được Modify** |
| **uid=writer,ou=services,...** | Search/read và Modify một số attribute được duyệt trong lab |

Tài khoản trên chỉ tồn tại nếu bạn đã tạo và cấp ACL tương ứng; bài học **không mặc định server tự sinh chúng**. Không sử dụng rootDN để chạy toàn bộ ví dụ và vô tình bỏ qua bước kiểm thử ACL.

### 4.1. Thiết lập biến dùng cho ldapsearch/ldapmodify

Ví dụ với OpenLDAP command-line client trong shell Bash:

~~~bash
export LDAP_URI='ldaps://ldap.lab.example:636'
export BASE_DN='dc=lab,dc=example'
export PERSON_DN='uid=linh,ou=people,dc=lab,dc=example'
export READER_DN='uid=reader,ou=services,dc=lab,dc=example'
export WRITER_DN='uid=writer,ou=services,dc=lab,dc=example'
~~~

Dùng **-W** để nhập mật khẩu tương tác và **LDAPS/StartTLS** với certificate validation. Không dùng **-w matkhau** trong shell history hoặc tắt xác minh chứng chỉ chỉ vì câu lệnh chưa kết nối được.

## 5. Tái hiện objectClassViolation (65): xóa thuộc tính bắt buộc

Đây là ví dụ dễ kiểm chứng vì **sn** thuộc nhóm MUST của objectClass **person** và được kế thừa bởi **inetOrgPerson**.

Chuẩn bị file **remove-sn.ldif**:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
delete: sn
~~~

Chạy trong **directory lab** bằng writer có quyền sửa:

~~~bash
ldapmodify -x -H "$LDAP_URI" \
  -D "$WRITER_DN" -W \
  -f remove-sn.ldif
~~~

Kết quả điển hình nếu writer có quyền và server thực thi schema:

~~~text
ldap_modify: Object class violation (65)
additional info: ... missing required attribute sn ...
~~~

Diagnostic message ở dòng thứ hai chỉ là ví dụ, không phải chuỗi chắc chắn của mọi OpenLDAP/AD phiên bản. **Nếu reader thử cùng lệnh và nhận 50**, đó là điều hợp lý: **ACL có thể từ chối trước khi trả lỗi schema**. Để cô lập lỗi 65, dùng một writer được phép thử thao tác trong lab và xác nhận entry sau khi bị từ chối vẫn có **sn**.

### 5.1. Vì sao không sửa bằng cách xóa objectClass person?

**inetOrgPerson** kế thừa **organizationalPerson** và **person**, vì vậy xóa chuỗi objectClass cha một cách tùy tiện không làm biến mất ràng buộc MUST một cách hợp lệ. Server có thể tự duy trì/kiểm tra danh sách class hoặc từ chối thay đổi structural class với code **69**. Cách đúng là **không xóa sn cuối cùng**, hoặc nếu nghiệp vụ yêu cầu một loại object khác, thực hiện provisioning/migration theo schema và khả năng directory server.

### 5.2. Khôi phục một thuộc tính bắt buộc

Nếu entry bị thiếu dữ liệu trong một môi trường đã bị nhập sai bởi cơ chế khác, có thể dùng **REPLACE sn** để đặt giá trị hợp lệ khi được quyền:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
replace: sn
sn: Nguyen
~~~

Không biến `sn` thành một chuỗi ngẫu nhiên chỉ để qua schema; cần dùng dữ liệu nghiệp vụ đúng và tôn trọng chính sách về danh tính.

## 6. Tái hiện thuộc tính không được objectClass cho phép

Giả sử ứng dụng muốn thêm thuộc tính **member** (thường dùng cho nhóm) trực tiếp vào một entry **inetOrgPerson**:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
add: member
member: uid=an,ou=people,dc=lab,dc=example
~~~

Nếu schema có khai báo **member** nhưng objectClass của entry không cho phép attribute đó, server thường trả:

~~~text
ldap_modify: Object class violation (65)
additional info: attribute 'member' not allowed
~~~

**Không gắn groupOfNames vào person để né lỗi**, vì đây là những structural class không cùng chain. Thay vào đó:

1. Nếu muốn thêm **thành viên nhóm**, hãy cập nhật entry **groupOfNames** ở **ou=groups** với thuộc tính **member**.
2. Nếu muốn lưu **mối quan hệ nghiệp vụ về người**, chọn attribute hợp lệ đã có hoặc mở rộng schema theo quy trình quản trị, với auxiliary class phù hợp khi server hỗ trợ.
3. Nếu mapping Java vô tình gửi attribute không nằm trong schema, **sửa mapping/DTO/update request**, đừng mở rộng schema chỉ để chứa mọi field Java.

### 6.1. Ví dụ entry nhóm đúng ngữ nghĩa

~~~ldif
dn: cn=developers,ou=groups,dc=lab,dc=example
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=lab,dc=example
~~~

Đối với `groupOfNames`, **cn** và **member** thường là MUST. Vì vậy nếu xóa thành viên cuối cùng mà không thay bằng giá trị hợp lệ, có thể lại gặp **objectClassViolation (65)**. Nếu yêu cầu nhóm rỗng, cần chọn đúng loại group/schema của directory chứ không phá MUST của groupOfNames.

## 7. Schema không hợp lệ: code 17, 19 và 21

Những lỗi schema dưới đây khác với một attribute được định nghĩa nhưng **không nằm trong MAY/MUST** của objectClass.

### 7.1. undefinedAttributeType (17): tên attribute không tồn tại

Ví dụ sai chính tả tên thuộc tính:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
add: mailll
mailll: linh.work@lab.example
~~~

Nếu server không có schema cho **mailll**, nó có thể trả **undefinedAttributeType (17)**. Giải pháp là sửa thành **mail**, không cấp thêm quyền ghi và không tự đăng ký schema cho một typo.

### 7.2. constraintViolation (19): vi phạm SINGLE-VALUE/ràng buộc

Một số attribute được định nghĩa là **SINGLE-VALUE**. Nếu cố thêm giá trị thứ hai hoặc REPLACE bằng nhiều giá trị, server có thể trả **constraintViolation (19)**.

Ví dụ mang tính tổng quát:

~~~text
AttributeType x-demo-single-value (SINGLE-VALUE)
Giá trị hiện tại: alpha
Yêu cầu: ADD thêm beta
Kỳ vọng điển hình: constraintViolation (19)
~~~

Tên **x-demo-single-value** chỉ mang tính minh họa, không phải attribute chuẩn có sẵn ở mọi directory. Trong lab thật, chọn một attribute đơn trị **đã được schema cho phép** trên entry và người dùng có quyền ghi, rồi xác minh trên server đang dùng. Nếu một value giống hệt đã tồn tại, server có thể trả **attributeOrValueExists (20)** thay vì code 19.

### 7.3. invalidAttributeSyntax (21): giá trị không đúng cú pháp

Ví dụ một attribute theo schema có kiểu **Generalized Time** hoặc **Integer** yêu cầu chuỗi phù hợp syntax. Truyền dữ liệu sai kiểu/cú pháp có thể làm server trả **invalidAttributeSyntax (21)**.

~~~text
Attribute được khai báo có syntax Generalized Time:
  20261126123000Z       -> ví dụ biểu diễn thời gian hợp lệ
  ngay-mai              -> không phải Generalized Time

Attribute có syntax Integer:
  120                   -> ví dụ kiểu số hợp lệ
  one hundred twenty    -> không hợp lệ
~~~

**Không giả định attribute tên timestamp nào cũng cho phép ghi trực tiếp.** Các operational attribute như **createTimestamp/modifyTimestamp** thường do server quản lý và có thể bị từ chối vì thuộc tính không cho user sửa, ngay cả khi string trông đúng syntax.

### 7.4. Phân biệt schema với kiểu Java

Một field Java kiểu **String** không biến mọi giá trị thành hợp lệ ở LDAP. Ngược lại, một số attribute nhị phân như **objectGUID** của Active Directory phải được xử lý dưới dạng **byte[]** và không thể đặt từ chuỗi tùy tiện. Khi gặp lỗi, kiểm tra **schema attributeTypes**, **ODM converter**, số lượng giá trị và encoding, không chỉ nhìn kiểu dữ liệu trong entity.

## 8. objectClassModsProhibited (69): đừng đổi structural class như thuộc tính thường

Theo mô hình LDAP (RFC 4512), structural object class của một entry được xác định qua một superclass chain và **không được thay đổi** như việc sửa mail/description. Vì vậy một yêu cầu biến entry **inetOrgPerson** trực tiếp thành **groupOfNames** qua LDAP Modify có thể bị từ chối với **objectClassModsProhibited (69)** hoặc lỗi schema liên quan.

Ví dụ minh họa một ý định không nên thực hiện:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
replace: objectClass
objectClass: top
objectClass: groupOfNames
~~~

Đây là **ví dụ phản diện**, không chạy lên dữ liệu production. Nó còn thiếu MUST của groupOfNames và vi phạm ngữ nghĩa chuyển loại structural entry. Cách đúng là **tạo entry nhóm riêng** theo DN, objectClass, MUST và quyền phù hợp; không mutate person thành group.

**Thêm auxiliary class hợp lệ** là thao tác khác với đổi structural class. Việc gắn auxiliary class phụ thuộc **DIT content rule/schema** và chính sách của server; phải tìm hiểu khả năng thực tế và cập nhật hợp lệ từng bước.

## 9. ACL: đọc được không đồng nghĩa được phép cập nhật

**Access Control List (ACL)** quyết định quyền trên LDAP entry và attribute, theo danh tính đã **bind**. Một tài khoản service có thể được phép **search/read** người dùng dưới **ou=people**, nhưng bị từ chối mọi thao tác Modify.

~~~mermaid
sequenceDiagram
    participant App as Spring / reader bind
    participant LDAP as LDAP server
    App->>LDAP: Bind as uid=reader,...
    LDAP-->>App: Bind success
    App->>LDAP: Search (uid=linh)
    LDAP-->>App: Entry cn,mail
    App->>LDAP: Modify REPLACE mail=...
    LDAP-->>App: insufficientAccessRights (50)
    Note over App,LDAP: Search thành công không chứng minh quyền Modify
~~~

### 9.1. Kiểm tra cùng bind DN với hai thao tác khác nhau

Đọc entry bằng reader:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "$PERSON_DN" -s base \
  '(objectClass=*)' dn objectClass uid cn sn mail
~~~

File **change-mail.ldif** để sửa một attribute **được schema cho phép**:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
replace: mail
mail: linh.new@lab.example
~~~

Thử bằng reader:

~~~bash
ldapmodify -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -f change-mail.ldif
~~~

Nếu lab cấp reader quyền read/search nhưng không cấp write, kết quả điển hình:

~~~text
ldap_modify: Insufficient access (50)
~~~

Sau đó, chỉ trong lab và khi được phép, thử **cùng file, cùng endpoint** bằng writer:

~~~bash
ldapmodify -x -H "$LDAP_URI" \
  -D "$WRITER_DN" -W \
  -f change-mail.ldif
~~~

Nếu writer có quyền Modify mail và dữ liệu hợp lệ, request có thể thành công. So sánh này giúp xác định vấn đề nằm ở **danh tính/ACL**, thay vì liên tục đổi schema hoặc thêm objectClass.

### 9.2. ACL còn có thể che entry hoặc attribute

Với một số server/chính sách, thiếu quyền **search/read** khiến client **không nhìn thấy entry** hoặc không nhìn thấy attribute, thay vì luôn nhận mã 50. Vì vậy:

- **Search trả rỗng** không chứng minh entry không tồn tại.
- **Search trả entry thiếu mail** không chứng minh mail chưa từng có.
- **Modify trả 50** cho biết quyền không đủ đối với thao tác, nhưng một số sản phẩm LDAP có thể dùng thông báo/chính sách đặc thù khác.
- **Bind thành công** chỉ xác nhận việc xác thực; không cấp quyền Modify mặc định.

Để phân tích, so sánh **cùng host, base DN, filter, scope, attribute list** giữa reader và một tài khoản được phép kiểm tra trong lab. Không đưa credential admin vào ứng dụng production để làm lỗi biến mất.

### 9.3. OpenLDAP ACL và Active Directory không giống nhau

Trong OpenLDAP, ACL thường được triển khai theo quy tắc **access to ... by ...** và mức quyền như **read/write**, với thứ tự rule và phạm vi attribute có ý nghĩa quan trọng. Directory có thể đặt ACL cho subtree **ou=people**, cho một số attribute, hoặc cho danh tính cụ thể.

Trong **Active Directory Domain Services**, quyền có thể liên quan **security descriptor**, inheritance và các quyền mở rộng cho loại object/attribute. Một object tồn tại trong AD cũng có một số thuộc tính **system-managed/systemOnly**, có thể bị từ chối bởi server dù một tài khoản có quyền sửa nhiều attribute khác. Không sao chép nguyên mẫu OpenLDAP ACL sang AD và kỳ vọng hiệu lực giống nhau.

Điều quan trọng là hỏi: **Ai đang bind? Ghi vào DN nào? Sửa attribute nào? Server nào quyết định quyền đó?**

## 10. Xem schema thật trước khi đổi objectClass

Đừng suy schema chỉ từ tên thuộc tính Java hoặc một sơ đồ công ty. Cùng tên objectClass có thể hoạt động trong những directory khác nhau với **schema extension**, **DIT content rule**, policy và quyền đọc schema khác nhau.

### 10.1. Tìm subschemaSubentry của entry đang lỗi

Trên LDAP server hỗ trợ cơ chế subschema LDAPv3, query chính entry để lấy **operational attribute subschemaSubentry**:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "$PERSON_DN" -s base \
  '(objectClass=*)' dn objectClass subschemaSubentry
~~~

Ví dụ một server có thể trả:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
subschemaSubentry: cn=Subschema
~~~

**cn=Subschema chỉ là ví dụ**; không hardcode DN này cho mọi server. Nếu thuộc tính **subschemaSubentry** không được trả, kiểm tra server hỗ trợ/ACL và đường truy cập schema được quản trị cung cấp. Một số server AD đặt schema trong một naming context riêng.

Giả sử result thực cung cấp **cn=Subschema**, có thể đọc:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b 'cn=Subschema' -s base \
  '(objectClass=*)' objectClasses attributeTypes
~~~

Kết quả schema có thể rất lớn. Không dump toàn bộ vào log ứng dụng; chọn các definition liên quan **inetOrgPerson**, **person**, **mail**, **sn**, **member** hoặc attribute đang bị từ chối.

### 10.2. Cách đọc một objectClass definition

Ví dụ **minh họa cấu trúc schema**, không phải chuỗi nguyên văn của một LDAP server:

~~~text
objectClasses: (
  OID-cua-lop
  NAME 'person'
  SUP top
  STRUCTURAL
  MUST ( cn $ sn )
  MAY ( userPassword $ telephoneNumber $ description $ seeAlso )
)
~~~

| Thành phần | Cần hiểu |
| --- | --- |
| **NAME / OID** | Tên và định danh chuẩn của class |
| **SUP** | Class cha; các ràng buộc được kế thừa |
| **STRUCTURAL** | Class mô tả loại entry, nằm trong structural superclass chain |
| **AUXILIARY** | Class bổ sung một số attribute, chịu content rule |
| **MUST** | Attribute bắt buộc phải hiện diện |
| **MAY** | Attribute được phép nhưng không buộc có |
| **attributeTypes** | Cú pháp, matching, số giá trị và các đặc tính khác của attribute |

Một attribute có thể được định nghĩa trên server nhưng **không có trong tập MUST/MAY hợp lệ của entry**. Khi đó chỉ thấy tên trong **attributeTypes** là chưa đủ để kết luận được phép cập nhật.

### 10.3. Active Directory có schema và quyền riêng

Với AD DS, có thể lấy **schemaNamingContext** từ Root DSE:

~~~bash
ldapsearch -LLL -x -H 'ldaps://dc1.corp.example.com:636' \
  -D 'CN=LDAP Reader,OU=Service Accounts,DC=corp,DC=example,DC=com' -W \
  -b '' -s base '(objectClass=*)' schemaNamingContext defaultNamingContext
~~~

Đây chỉ là **cách tìm thông tin naming context**, không phải lời hứa reader có quyền xem toàn bộ schema hay thay đổi ACL. Trong AD, một số attribute như **objectGUID**, **whenCreated** hoặc attribute do hệ thống quản lý có thể không cho client sửa trực tiếp; server có thể trả lỗi **53**, **50** hoặc code liên quan tùy thao tác/policy.

## 11. Spring Data LDAP: @Entry và ánh xạ field có thể tạo lỗi

Spring Data LDAP sử dụng **Spring LDAP ODM**. Entity được khai báo bằng **@Entry** để mô tả các objectClass phù hợp, **@Id** để ánh xạ **DN**, **@Attribute** cho tên attribute, và **@Transient** để bỏ qua field không persist.

Ví dụ ánh xạ phù hợp với người dùng inetOrgPerson:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

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

    @Transient
    private String displayLabelForUi;

    // Constructor không tham số, getter/setter được lược bỏ.
}
~~~

Với cấu hình Spring Boot:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.lab.example:636"
    base: "dc=lab,dc=example"
    username: "uid=reader,ou=services,dc=lab,dc=example"
    password: "${LDAP_BIND_PASSWORD}"
~~~

**@Entry(base = "ou=people")** là DN tương đối với **spring.ldap.base**. **@Id Name dn** đại diện cho DN của entry; nó **không phải** khóa số tự tăng của JPA. **@Transient** rất quan trọng nếu một field chỉ dùng để hiển thị hoặc tính toán, không phải attribute LDAP.

### 11.1. Sai tên attribute dù entity Java biên dịch được

Ví dụ lỗi mapping:

~~~java
// Sai: server schema có 'mail', không có 'mailll'.
@Attribute(name = "mailll")
private String email;
~~~

Khi ODM cố ghi thuộc tính **mailll**, server có thể trả **undefinedAttributeType (17)**. Biên dịch Java thành công không xác minh schema LDAP. Sửa annotation thành **mail** là cách đúng; không cần cấp thêm quyền hay đăng ký một attribute mới chỉ vì typo.

### 11.2. Thiếu objectClass trong mapping

Một entry thật có:

~~~text
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
~~~

Nhưng Java class chỉ khai báo:

~~~java
@Entry(objectClasses = {"top", "person"}, base = "ou=people")
~~~

Điều này không chỉ ảnh hưởng ghi: theo quy tắc matching ODM, tập class khai báo ảnh hưởng việc entity được nhận diện/ánh xạ. Khi tạo entry mới, ODM sử dụng những objectClasses được khai báo và có thể **không tạo đúng loại inetOrgPerson** mà ứng dụng cần. Vì vậy phải mô tả các objectClasses phù hợp với attribute được mapping và loại entry thực. Đừng đặt class name theo suy luận nếu schema thực tế khác.

### 11.3. Repository.save không bỏ qua schema hay ACL

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

Lời gọi:

~~~java
DirectoryPerson person =
    personRepository.findByUid("linh").orElseThrow();
person.setEmail("linh.new@lab.example");
personRepository.save(person);
~~~

Giả định entity có setter tương ứng và repository đã cấu hình. Truy vấn có thể thành công với reader, nhưng **save** vẫn có thể bị **insufficientAccessRights (50)** nếu cùng ContextSource dùng tài khoản chỉ đọc. Cũng có thể lỗi schema nếu mapping gửi thêm attribute không hợp lệ hoặc một field bắt buộc bị thay thành null/xóa.

Không bao giờ mặc định **save()** “ghi đè cả entry một cách an toàn” hoặc tự kiểm soát lost update. Khi muốn thay một attribute cụ thể, dùng **LdapTemplate.modifyAttributes** với delta hợp lệ giúp xác định thao tác gửi tới server rõ ràng hơn.

## 12. LdapTemplate: cô lập một ModificationItem đang gây lỗi

**LdapTemplate.modifyAttributes(Name/String, ModificationItem[])** gửi danh sách thay đổi cho một DN; chỉ định **ADD_ATTRIBUTE**, **REPLACE_ATTRIBUTE** hoặc **REMOVE_ATTRIBUTE** để kiểm soát chính xác việc sửa.

Ví dụ cập nhật đúng một thuộc tính **mail** vốn được schema cho phép:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public final class PersonMailWriter {
    private final LdapTemplate ldapTemplate;

    public PersonMailWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void changeMail(String newMail) {
        ModificationItem replace = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", newMail)
        );

        // ContextSource base = dc=lab,dc=example.
        ldapTemplate.modifyAttributes(
            "uid=linh,ou=people",
            new ModificationItem[]{replace}
        );
    }
}
~~~

Điều kiện để thành công: **newMail** phù hợp định dạng/chính sách được server cho phép, entry tồn tại, bind identity có quyền ghi mail và directory không áp thêm ràng buộc cấm khác. Trước khi gọi, service cần **authorize người gọi**, kiểm tra input theo nghiệp vụ và giới hạn thay đổi được phép.

### 12.1. Đọc, thay giá trị rồi gửi diff qua DirContextOperations

Một cách khác:

~~~java
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

public final class PersonDescriptionUpdater {
    private final LdapTemplate ldapTemplate;

    public PersonDescriptionUpdater(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void changeDescription(String newDescription) {
        DirContextOperations context =
            ldapTemplate.lookupContext("uid=linh,ou=people");
        context.setAttributeValue("description", newDescription);
        ldapTemplate.modifyAttributes(context);
    }
}
~~~

Ví dụ giả định LDAP account có quyền đọc **description** và ghi vào entry. **lookupContext** tạo đối tượng có trạng thái thuộc tính ban đầu để Spring LDAP tính **ModificationItem**. Đừng vô tình thêm một field chỉ dùng trong UI vào ODM, hoặc thay nhiều thuộc tính không liên quan khi chỉ muốn đổi description.

### 12.2. Một LDAP Modify phải hợp lệ sau khi áp dụng toàn bộ changes

Theo LDAPv3, **một ModifyRequest trên một entry** phải được server xử lý nguyên tử: tất cả modification trong request thành công, hoặc không modification nào được áp dụng.

Ví dụ:

~~~java
ModificationItem[] modifications = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "linh.new@lab.example")
    ),
    new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("sn")
    )
};
ldapTemplate.modifyAttributes(
    "uid=linh,ou=people",
    modifications
);
~~~

Đây là **đoạn mã lỗi cố ý** bên trong method đã có `ldapTemplate` và import **BasicAttribute/DirContext/ModificationItem**. Dù mail hợp lệ, xóa **sn** cuối cùng có thể làm toàn bộ ModifyRequest bị từ chối với **65**. **Không được giả định mail đã được thay chỉ vì modification đầu tiên trong mảng hợp lệ**.

Ngược lại, nếu ứng dụng gửi **hai ModifyRequest riêng**, thao tác đầu có thể thành công còn thao tác sau thất bại; đó không phải cùng một transaction.

### 12.3. Tránh REPLACE toàn bộ giá trị đa trị khi chỉ muốn đổi một phần

Nếu chỉ muốn thêm một DN vào **groupOfNames.member**:

~~~java
ModificationItem addOne = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute(
        "member",
        "uid=an,ou=people,dc=lab,dc=example"
    )
);
ldapTemplate.modifyAttributes(
    "cn=developers,ou=groups",
    new ModificationItem[]{addOne}
);
~~~

Đây là delta ADD, giúp tránh đọc snapshot cũ rồi REPLACE cả tập member khi nhiều writer đồng thời. Nó vẫn chịu **schema/ACL** và có thể trả **20** nếu member đã tồn tại.

## 13. JNDI và Spring LDAP dịch lỗi như thế nào?

Ở tầng Java JNDI, các lệnh **DirContext.modifyAttributes(...)** có thể ném **javax.naming.NamingException** và những subclass. **LdapTemplate** thường chuyển các exception này sang họ **runtime exception org.springframework.ldap**, nhưng phần cause và mã LDAP vẫn là đầu mối chẩn đoán quan trọng.

| Lỗi JNDI thường gặp | Exception Spring LDAP tương ứng thường gặp | Ghi chú |
| --- | --- | --- |
| **javax.naming.directory.SchemaViolationException** | **org.springframework.ldap.SchemaViolationException** | Thường liên quan code 65 hoặc schema restriction |
| **javax.naming.NoPermissionException** | **org.springframework.ldap.NoPermissionException** | Lỗi quyền, thường code 50 |
| **javax.naming.NameNotFoundException** | **org.springframework.ldap.NameNotFoundException** | DN/base không tồn tại hoặc bị che |
| **javax.naming.AuthenticationException** | **org.springframework.ldap.AuthenticationException** | Bind credentials |
| **javax.naming.directory.InvalidAttributeIdentifierException** | **org.springframework.ldap.InvalidAttributeIdentifierException** | Tên attribute không hợp lệ/không nhận diện |
| **javax.naming.directory.InvalidAttributeValueException** | **org.springframework.ldap.InvalidAttributeValueException** | Giá trị thuộc tính không hợp lệ |
| **javax.naming.directory.AttributeInUseException** | **org.springframework.ldap.AttributeInUseException** | Attribute/value đã được dùng trong thao tác ADD |
| **javax.naming.CommunicationException** | **org.springframework.ldap.CommunicationException** | Lỗi mạng, TLS, timeout hoặc kết nối |

**Không coi bảng là ánh xạ result code 1–1 bắt buộc cho mọi JNDI provider/server**. Ví dụ server có thể dùng code 53 cho chính sách vendor-specific, và exception translation có thể đưa lỗi vào loại tổng quát hơn. Nếu cần phân loại chính xác, phải xem **diagnostic message/cause chain** hoặc result code từ client SDK cấp thấp, đồng thời kiểm chứng trên directory mục tiêu.

### 13.1. Bắt riêng hai nhóm schema và ACL

~~~java
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.SchemaViolationException;
import org.springframework.ldap.core.LdapTemplate;

public final class SafeMailUpdateService {
    private final LdapTemplate ldapTemplate;

    public SafeMailUpdateService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void changeMail(String newMail) {
        try {
            // Tạo ModificationItem mail như ở phần 12.
            var change = new javax.naming.directory.ModificationItem(
                javax.naming.directory.DirContext.REPLACE_ATTRIBUTE,
                new javax.naming.directory.BasicAttribute("mail", newMail)
            );
            ldapTemplate.modifyAttributes(
                "uid=linh,ou=people",
                new javax.naming.directory.ModificationItem[]{change}
            );
        } catch (SchemaViolationException ex) {
            throw new DirectoryDataRejectedException(
                "LDAP rejected update against the directory schema", ex);
        } catch (NoPermissionException ex) {
            throw new DirectoryWriteForbiddenException(
                "LDAP writer lacks permission for the target entry", ex);
        }
    }

    public static final class DirectoryDataRejectedException
            extends RuntimeException {
        public DirectoryDataRejectedException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class DirectoryWriteForbiddenException
            extends RuntimeException {
        public DirectoryWriteForbiddenException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Hai exception domain trên chỉ minh họa **phân loại lỗi**. Nếu server trả **invalidAttributeSyntax (21)** qua một subclass khác, service cần xử lý thêm. Đừng bắt mọi **Exception** rồi trả **false** hoặc danh sách rỗng, vì như vậy che sự cố schema/ACL thành kết quả nghiệp vụ không có dữ liệu.

### 13.2. Các thông tin log cần và không nên ghi

| Nên ghi trong log nội bộ có kiểm soát | Không nên ghi |
| --- | --- |
| Request/trace ID, tên thao tác (MODIFY/ADD/DELETE) | Password, token, SECURITY_CREDENTIALS |
| Endpoint logic và environment đã được duyệt | Dữ liệu người dùng không cần thiết |
| DN mục tiêu sau khi đã che nếu nhạy cảm | Toàn bộ entry hoặc attribute bí mật |
| Tên attribute đang sửa, loại delta ADD/REPLACE/REMOVE | Raw LDIF chứa mật khẩu hoặc định danh nhạy cảm |
| LDAP result code, exception class, cause phù hợp | Trả raw stack trace/DN nội bộ cho HTTP client |
| Latency và số lần retry | Dump toàn bộ JNDI environment |

Với Spring Boot, có thể nâng log theo phạm vi hẹp trong lab:

~~~yaml
logging:
  level:
    org.springframework.ldap: DEBUG
    org.springframework.data.ldap: DEBUG
~~~

Điều này **không bảo đảm mọi phiên bản log chi tiết LDAP ModifyRequest**; một số thao tác không in attribute/value vì lý do riêng. Không bật debug/trace có nguy cơ rò dữ liệu nhạy cảm trên production hoặc ghi lại packet TLS đã giải mã chỉ để xem mã lỗi.

## 14. Quy trình chẩn đoán từng bước, tránh sửa nhầm

~~~mermaid
flowchart TD
    A["Update từ repository/LdapTemplate thất bại"] --> B["Lấy LDAP result code, operation, DN, bind identity"]
    B --> C{"Code 65/17/19/21/69?"}
    C -->|Có| D["Đọc entry hiện tại + objectClass + subschema"]
    D --> E["Kiểm tra MUST/MAY, syntax, SINGLE-VALUE, structural class"]
    C -->|Không| F{"Code 50 hoặc nghi ACL?"}
    F -->|Có| G["Chạy cùng Modify bằng service bind và writer được duyệt"]
    G --> H["Đối chiếu ACL trên DN/attribute/operation"]
    F -->|Không| I["Kiểm tra code 32/34/49/53, endpoint và cause"]
    E --> J["Sửa mapping/giá trị/provisioning đúng cách"]
    H --> K["Điều chỉnh quyền tối thiểu nếu được phê duyệt"]
    I --> L["Khắc phục nguyên nhân riêng của code"]
    J --> M["Integration test + xác minh readback"]
    K --> M
    L --> M
~~~

**Quy trình khuyến nghị:**

1. **Xác định thao tác thất bại:** repository `save`, `update`, `bind`, `rebind`, hay `modifyAttributes`? Có đang tạo entry mới thay vì sửa entry cũ không?
2. **Xác minh endpoint và bind DN:** đúng môi trường, server node, suffix và TLS. Kiểm tra loại tài khoản (reader/writer) thực tế được ContextSource dùng.
3. **Ghi mã LDAP và loại exception:** phân biệt **65**, **17**, **21**, **19**, **50**, **69** với **32**, **34**, **49**.
4. **Xác minh DN cuối cùng:** ContextSource base có thể được nối vào DN tương đối trong LdapTemplate; đừng truyền full DN rồi lặp suffix.
5. **Đọc entry hiện tại:** yêu cầu **dn, objectClass** và các attribute liên quan với đúng bind identity; kiểm tra entry có thể được nhìn thấy không.
6. **Đọc schema:** xem **subschemaSubentry**, định nghĩa objectClass, inherited MUST/MAY, attributeTypes, SINGLE-VALUE và syntax.
7. **Cô lập ModificationItem:** thử một thay đổi hợp lệ tại một thời điểm trong lab để biết lỗi đến từ attr nào; không làm thí nghiệm trên dữ liệu thật.
8. **So sánh ACL:** với cùng DN và cùng thao tác mail hợp lệ, reader bị từ chối nhưng writer hợp lệ thành công thì xem chính sách quyền.
9. **Sửa đúng nguyên nhân:** typo mapping, giá trị sai syntax, thiếu MUST, structural chain, ACL hoặc endpoint. Không ưu tiên tăng quyền vô hạn.
10. **Viết regression test** với directory phù hợp; xác minh cả lỗi bị từ chối lẫn cập nhật hợp lệ.

### 14.1. Tách lỗi schema và lỗi quyền qua một phép thử kiểm soát

Nếu **remove-sn.ldif** trả code 50 với reader, điều đó **không chứng minh sn không phải MUST**. Để thấy lỗi 65, thử cùng request bằng writer có quyền trong lab. Ngược lại, nếu **change-mail.ldif** trả 50 với reader và thành công với writer, đó là bằng chứng hướng về ACL hơn là schema.

**Đừng thay đồng thời file LDIF, tài khoản bind, endpoint và phiên bản server** khi so sánh, vì lúc đó không biết yếu tố nào đã làm kết quả thay đổi.

## 15. Bảng tình huống: từ triệu chứng đến phương án sửa

| Tình huống | Triệu chứng thường thấy | Hướng khắc phục |
| --- | --- | --- |
| Mapper ghi **mailll** thay vì mail | 17, invalid attribute identifier | Sửa `@Attribute(name="mail")` |
| Xóa giá trị **sn** cuối cùng của inetOrgPerson | 65 | Giữ sn hợp lệ, không xóa MUST |
| Ghi **member** vào entry inetOrgPerson | 65 | Ghi vào groupOfNames hoặc dùng schema phù hợp |
| Thêm **groupOfNames** lên structural class person | 65/69 hoặc lỗi khác theo server | Không đổi structural chain tùy tiện; tạo entry đúng loại |
| Gán nhiều giá trị cho attribute SINGLE-VALUE | 19 | Chọn đúng một giá trị hoặc điều chỉnh nghiệp vụ/schema theo quy trình |
| Giá trị integer/time sai syntax | 21 | Validate kiểu/format và converter |
| ADD giá trị hiện đã có | 20 | Xử lý idempotency hoặc dùng chính sách duplicate hợp lý |
| REMOVE giá trị đã mất | 16 | Đọc lại, xử lý race/điều kiện trạng thái |
| Reader search OK nhưng Modify fail | 50 | Xin đúng write permission cho attribute, không tự tăng quyền admin |
| Thay **objectGUID/modifyTimestamp** trong AD | Có thể 53/50 hoặc code policy khác | Không ghi system-managed attribute |
| **NameNotFoundException** khi đổi DN | 32 | Kiểm tra base tương đối, move/rename/ACL |
| LDAP trả success nhưng app đọc không thấy dữ liệu mới | Có thể đọc replica cũ, nhầm endpoint hoặc attribute bị ACL ẩn | Kiểm tra đường đọc/ghi và replication |
| Một request Modify chứa thay đổi hợp lệ và sai schema | Toàn Modify bị từ chối | Sửa modification sai; không giả định phần đầu đã commit |

## 16. Kiểm thử tích hợp schema và ACL

**Mock repository hoặc DirContext** có thể xác minh branch Java nhưng không tái hiện đầy đủ **MUST/MAY, schema, result code 65, ACL hoặc replication**. Hãy dùng directory nhúng nếu phù hợp cho unit/integration nhẹ, và kiểm thử bổ sung với **OpenLDAP hoặc AD DS thật trong lab** khi cần đặc tính riêng của server.

### 16.1. Ma trận kiểm thử cần có

| Case | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Ghi mail hợp lệ bằng writer | REPLACE mail | Success |
| Ghi mail bằng reader chỉ có quyền đọc | REPLACE mail | 50 hoặc biểu hiện phân quyền tương ứng |
| Xóa sn cuối cùng bằng writer | REMOVE sn | 65 khi schema được thực thi |
| Thêm member vào person | ADD member | 65 nếu member không được phép bởi schema entry |
| Dùng tên attribute không có schema | ADD mailll | 17 |
| Vi phạm syntax | Ghi giá trị sai format vào attr được phép | 21 hoặc policy code phù hợp |
| Thêm một giá trị duplicate | ADD member/email đã có | 20 tùy schema/matching |
| Cố đổi structural objectClass | REPLACE objectClass | 69/65 hoặc code server-specific |
| Sai DN | Modify không tìm thấy entry | 32, không phải lỗi schema |
| Dữ liệu chỉ đọc vì replication/policy | Modify qua read-only endpoint | Kết quả phụ thuộc topology/server |
| Một request có hai ModificationItem | Sửa mail hợp lệ + xóa sn | Không áp dụng một phần |
| Sau sửa mapping | Dùng đúng mail/sn/objectClass | Update thành công, readback khớp |

### 16.2. Mẫu JUnit cho lỗi vi phạm MUST

Mã minh họa dưới đây giả định **Spring Boot test** đã khởi tạo một LDAP directory lab hỗ trợ schema person/inetOrgPerson, bean **LdapTemplate**, và bind identity có quyền Modify. Lệnh cố ý xóa **sn**, sau đó kiểm tra server từ chối:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.SchemaViolationException;
import org.springframework.ldap.core.LdapTemplate;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class SchemaValidationIntegrationTest {
    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void removingRequiredSurnameIsRejected() {
        ModificationItem remove = new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("sn")
        );

        assertThrows(SchemaViolationException.class, () ->
            ldapTemplate.modifyAttributes(
                "uid=linh,ou=people",
                new ModificationItem[]{remove}
            )
        );
    }
}
~~~

Nếu test trả **NoPermissionException** thay vì SchemaViolationException, trước tiên xác minh **test writer có quyền ghi**. Nếu directory nhúng không áp dụng schema đủ nghiêm ngặt, test có thể không kiểm chứng được mã 65 như OpenLDAP. Đừng thay assertion thành “mọi exception đều PASS”, vì như vậy có thể che một lỗi không liên quan.

### 16.3. Kiểm thử phân quyền độc lập

Không tái sử dụng writer làm reader trong cùng test rồi kết luận ACL đã hoạt động. Nên cấu hình hai **ContextSource** hoặc hai **LdapTemplate** riêng biệt, dùng đúng bind DN và secret đã cấp. Dưới đây là ý tưởng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.ldap.NoPermissionException;

import static org.junit.jupiter.api.Assertions.assertThrows;

// Trong test có bean ldapTemplateReader đã bind bằng reader thật.
@Test
void readOnlyAccountCannotChangeMail() {
    assertThrows(NoPermissionException.class, () ->
        ldapTemplateReader.modifyAttributes(
            "uid=linh,ou=people",
            new javax.naming.directory.ModificationItem[]{
                new javax.naming.directory.ModificationItem(
                    javax.naming.directory.DirContext.REPLACE_ATTRIBUTE,
                    new javax.naming.directory.BasicAttribute(
                        "mail", "blocked@lab.example")
                )
            }
        )
    );
}
~~~

Đoạn trên là **phần thân/khung test cần field ldapTemplateReader được inject** và môi trường ACL riêng; không phải file Java độc lập có thể biên dịch nguyên xi. Kết quả kỳ vọng **NoPermissionException** phù hợp khi OpenLDAP lab thật trả code 50 và Spring LDAP dịch như dự kiến; với server khác, kiểm tra result code và chính sách trước khi chốt assertion.

### 16.4. Đảm bảo test không để lại dữ liệu sai

- Chạy trên **directory lab**, không cố ý xóa sn/đổi objectClass trên production.
- Tạo fixture theo **thứ tự DN cha trước con**, dọn dữ liệu sau test nếu server giữ state.
- Dùng **một endpoint rõ ràng** trong test schema/ACL để tránh chênh lệch replica.
- Đặt timeout, bật TLS và kiểm tra certificate đúng môi trường.
- Sau khi server từ chối Modify, đọc lại entry để xác minh các attribute cũ còn nguyên.
- Với multi-writer, kiểm thử riêng nguy cơ **lost update**; schema/ACL không thay thế optimistic concurrency.

## 17. Sự khác nhau giữa OpenLDAP và Active Directory khi chẩn đoán

Nguyên tắc LDAPv3 tương đối thống nhất, nhưng **schema, ACL và một số policy** khác đáng kể giữa các server:

| Khía cạnh | OpenLDAP | Active Directory DS |
| --- | --- | --- |
| **Schema** | objectClasses/attributeTypes trong subschema và cấu hình quản trị | Schema naming context, classSchema/attributeSchema |
| **Quyền** | ACL theo `access to` / `olcAccess`, mức read/write/entry/children | Security descriptors, inherited ACE, quyền trên object/attribute |
| **Operational attributes** | Ví dụ entryUUID, createTimestamp, modifyTimestamp | objectGUID, whenCreated, uSNChanged và thuộc tính system-managed |
| **Cách báo lỗi** | Thường hiện RFC resultCode và diagnostic từ slapd | Có thể kèm mã phụ/diagnostic đặc thù Microsoft |
| **Thay đổi objectClass** | Structural chain theo LDAP schema; có thể bị code 69 | System/schema policy riêng, không hỗ trợ mọi kiểu thay đổi structural class |
| **Replication** | Tùy OpenLDAP topology và sync provider | Nhiều domain controller, replication và quyền theo domain |

Đừng đưa một LDIF thử **inetOrgPerson** từ OpenLDAP sang AD rồi mặc định cấu trúc OU, bind DN, ACL và objectClass match hoàn toàn. Với AD, cần xác định **defaultNamingContext**, các class/attribute thực được hỗ trợ và quyền của tài khoản dịch vụ. Một lỗi policy của AD có thể trông giống schema violation nhưng được trả bằng **unwillingToPerform (53)**, nên cần đọc diagnostic thay vì chỉ dựa vào một bảng mapping đơn giản.

## 18. Các cách sửa sai phổ biến cần tránh

1. **Đổi sang tài khoản admin để qua lỗi 50:** làm mất nguyên tắc least privilege, che lỗi ACL. Chỉ dùng quyền cao trong lab để chẩn đoán khi được ủy quyền.
2. **Tắt schema checking:** có thể đưa directory vào trạng thái không hợp lệ và gây lỗi cho mọi LDAP client khác.
3. **Thêm tất cả objectClass lên entity:** không đảm bảo hợp lệ; có thể tạo structural chain sai hoặc khai báo lớp không hỗ trợ.
4. **Thêm một auxiliary class bất kỳ:** DIT content rule có thể không cho phép, và schema extension cần quy trình quản trị.
5. **Đặt giá trị giả vào sn/cn:** có thể qua MUST nhưng vi phạm chất lượng dữ liệu danh tính.
6. **Thay schema chỉ vì sai tên attribute Java:** trước tiên kiểm tra typo và mapping.
7. **REPLACE toàn bộ attributes khi chỉ muốn sửa mail:** tăng rủi ro mất dữ liệu đồng thời hoặc vô tình xóa MUST.
8. **Cho mọi lỗi trả danh sách rỗng:** schema violation và ACL denied không phải kết quả search không tìm thấy.
9. **Retry vô hạn khi code 65/50:** đây thường là lỗi ổn định, không tự hết nếu cứ gửi lại cùng request.
10. **Giả định read timeout nghĩa là Modify chưa thành công:** server có thể đã áp dụng update nhưng response không đến client.

### 18.1. Cần làm gì khi request Modify timeout?

Sau khi gửi Modify, một lần mất kết nối có thể xảy ra **sau khi server đã ghi** nhưng trước khi client nhận response. Vì vậy không tự gửi lại một lệnh **ADD/REPLACE/DELETE** mà chưa xác minh trạng thái ở server, đặc biệt nếu nhiều writer có thể sửa cùng entry.

Hãy đọc lại từ một nguồn đáng tin cậy, xác định dữ liệu hiện tại và áp dụng chính sách idempotency/conditional update phù hợp. Nếu ứng dụng cần bảo vệ giá trị cũ, có thể dùng **LDAP Assertion Control** trên server hỗ trợ; nó là cơ chế khác với schema validation và ACL.

## 19. Bài thực hành và câu hỏi ôn tập

### 19.1. Bài thực hành theo thứ tự

1. Tạo suffix và **ou=people**, nhập entry inetOrgPerson Linh đúng MUST cn/sn, dùng LDAP server lab.
2. Tạo reader/writer với ACL phân biệt quyền đọc và ghi.
3. Dùng **ldapsearch** xác nhận entry tồn tại và ghi lại objectClass/attribute list.
4. Gửi **remove-sn.ldif** bằng writer. Ghi lại resultCode và trạng thái entry sau khi bị từ chối.
5. Gửi LDIF thêm **member** vào person. Kiểm tra lỗi objectClass khi schema có member nhưng entry không cho phép.
6. Gửi LDIF thêm **mailll** không được khai báo. Phân biệt code 17 với code 65.
7. Gửi **change-mail.ldif** bằng reader rồi writer; đối chiếu code 50 và success.
8. Truy vấn **subschemaSubentry**, tìm definition person/inetOrgPerson, attributeTypes liên quan.
9. Sửa entity `@Entry/@Attribute` đúng với directory; viết một phương thức update qua LdapTemplate.
10. Viết integration test cho code 65, code 50 và trường hợp mail hợp lệ. Đọc lại dữ liệu sau mỗi case.
11. Kiểm thử một case DN sai trả 32 để không nhầm schema violation với NameNotFoundException.
12. Ghi bảng kết quả theo **request → bind identity → code → nguyên nhân → cách sửa**.

### 19.2. Câu hỏi ôn tập

1. **objectClass** khác **attributeType** và **ACL** ở đâu?
2. Vì sao một entry inetOrgPerson thường phải có **cn** và **sn**?
3. Nếu thêm **member** vào person rồi nhận code 65, có nên thêm **groupOfNames** vào objectClass không? Vì sao?
4. **undefinedAttributeType (17)** khác **objectClassViolation (65)** như thế nào?
5. Khi nào nhận **constraintViolation (19)** hoặc **invalidAttributeSyntax (21)**?
6. Vì sao **ldapsearch** thành công không chứng minh tài khoản bind có quyền Modify?
7. Vì sao lệnh xóa sn có thể trả 50 với reader nhưng 65 với writer?
8. Ý nghĩa của **subschemaSubentry** và thuộc tính **objectClasses/attributeTypes** là gì?
9. **@Entry**, **@Attribute**, **@Id**, **@Transient** trong Spring LDAP ODM phục vụ mục đích gì?
10. Khi một LDAP ModifyRequest có hai ModificationItem, một cái hợp lệ và một cái vi phạm schema, server có thể commit một nửa không?
11. Nên bắt lỗi schema/ACL như thế nào để không lộ DN hoặc secret ra HTTP response?
12. Vì sao sau read timeout của Modify không được kết luận update chắc chắn chưa xảy ra?

## 20. Tổng kết

**Cập nhật LDAP thất bại** không phải luôn do lập trình viên gọi sai `save`. **objectClass** quyết định kiểu entry và tập attribute **MUST/MAY**; **schema** còn định nghĩa syntax, số lượng giá trị và những ràng buộc bổ sung; **ACL** quyết định danh tính nào được đọc hoặc ghi trên entry/attribute. Trước khi sửa, hãy lấy **LDAP result code thực** và phân biệt những nhóm chủ yếu:

- **65 / 69**: cấu trúc hoặc thay đổi objectClass không hợp lệ.
- **17 / 19 / 21**: attribute không được định nghĩa, vi phạm constraint hoặc syntax.
- **50**: thiếu quyền ghi; không giải quyết bằng cách tăng timeout, thay đổi objectClass hoặc tùy tiện dùng admin.
- **32 / 34 / 49**: vấn đề DN hoặc authentication, cần điều tra riêng.

Với Spring Data LDAP, **repository và ODM không vượt qua quy tắc directory server**. Hãy kiểm tra mapping, dùng **LdapTemplate.modifyAttributes** để cô lập delta khi cần, đối chiếu lệnh **ldapmodify** trên đúng endpoint/bind DN, đọc schema thực và kiểm thử bằng directory có ACL phù hợp. Giữ **TLS**, bảo vệ secret và xây dựng quy trình sửa lỗi có thể kiểm chứng thay vì che các result code.

## Tài liệu tham khảo

- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): ModifyRequest, LDAPResult và các result code 17/19/21/50/65/69.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): structural/auxiliary object classes, MUST/MAY, attribute descriptions và subschema.
- [RFC 4517 — LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517.html): syntax và matching rule của LDAP attribute.
- [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519.html): ví dụ class person/organizationalPerson và attribute cơ bản.
- [RFC 2798 — inetOrgPerson](https://www.rfc-editor.org/rfc/rfc2798.html): person extension thường dùng cho người dùng directory.
- [OpenLDAP Administrator's Guide — Schema](https://www.openldap.org/doc/admin25/schema.html): định nghĩa schema và MUST/MAY.
- [OpenLDAP Administrator's Guide — Access Control](https://openldap.org/doc/admin25/access-control.html): rule `access to`, quyền read/write, entry/children và thứ tự ACL.
- [OpenLDAP Administrator's Guide — Result Codes](https://openldap.org/doc/admin25/appendix-ldap-result-codes.html): ý nghĩa những mã lỗi thường gặp.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute`, `@Transient` và mapping.
- [Spring Data LDAP — Repository Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): repository và DN kiểu javax.naming.Name.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `lookupContext`, `modifyAttributes`, ODM update.
- [Spring LDAP — Exception Package](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/package-summary.html): Spring LDAP runtime exception được dịch từ JNDI.
- [Oracle JNDI — DirContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/DirContext.html): Modify attributes và Search.
