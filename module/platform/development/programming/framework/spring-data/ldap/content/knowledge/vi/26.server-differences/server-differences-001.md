# OpenLDAP: schema, ACL và dữ liệu LDIF cho môi trường học

**OpenLDAP** là một máy chủ triển khai giao thức LDAP thường được dùng để học về directory và kiểm thử ứng dụng Java. Với **Spring Data LDAP**, ứng dụng có thể ánh xạ entry thành đối tượng Java và truy vấn bằng repository; tuy nhiên, kết quả thực tế vẫn chịu chi phối bởi **schema**, **quyền truy cập (ACL)**, cấu trúc **Distinguished Name (DN)** và dữ liệu đã được nạp vào LDAP server.

Bài học hướng dẫn xây dựng một directory OpenLDAP nhỏ có thể tái tạo bằng **LDIF**, hiểu vì sao schema chấp nhận hoặc từ chối entry, thiết lập ACL đọc hạn chế cho ứng dụng, và xác minh bằng công cụ dòng lệnh trước khi kết nối **LdapTemplate** hoặc **Spring Data LDAP Repository**. Ví dụ sử dụng tên miền giả định **dc=lab,dc=example** và tài khoản dịch vụ chỉ đọc; mọi mật khẩu và chứng chỉ phải được cấu hình riêng cho môi trường thực hành.

## 1. OpenLDAP khác gì so với một API truy vấn LDAP?

LDAP là giao thức trao đổi giữa client và directory server. **OpenLDAP slapd** là một triển khai LDAP server, có nhiệm vụ lưu entry, áp dụng schema, xác thực bind, kiểm tra ACL và xử lý thao tác tìm kiếm/chỉnh sửa.

~~~mermaid
flowchart TB
    A["Java service / Spring Data LDAP repository"] --> B["Spring LDAP: LdapTemplate, ContextSource"]
    B --> C["JNDI LDAP provider"]
    C --> D["OpenLDAP slapd"]
    D --> E["Schema: objectClass, attributeType, matching rule"]
    D --> F["ACL: ai được đọc / ghi / xác thực"]
    D --> G["MDB database: entry và DN"]
    H["LDIF: dữ liệu / thay đổi cấu hình"] --> D
~~~

Trong bối cảnh học tập, cần phân biệt:

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| **DIT** (Directory Information Tree) | Cấu trúc cây các entry | dc=lab,dc=example → ou=people → uid=linh |
| **Schema** | Quy định lớp đối tượng, thuộc tính và ràng buộc | inetOrgPerson cần cn và sn thông qua chuỗi kế thừa |
| **ACL** (Access Control List) | Quyết định danh tính nào được đọc/sửa nội dung nào | uid=reader được tìm người dùng nhưng không được sửa mail |
| **LDIF** (LDAP Data Interchange Format) | Định dạng văn bản mô tả entry hoặc lệnh thay đổi directory | Nạp một người dùng bằng ldapadd |
| **Backend** | Cơ chế lưu trữ dữ liệu trên máy chủ | MDB là backend phổ biến ở các triển khai slapd hiện đại |
| **JNDI / Spring LDAP / Spring Data LDAP** | API client Java để kết nối, tìm và thay đổi entry | LdapTemplate.search, LdapRepository.findByUid |

**Schema trả lời: “Entry này có hợp lệ không?” ACL trả lời: “Danh tính này được thực hiện thao tác đó không?”** Một entry có thể hoàn toàn đúng schema nhưng vẫn không đọc được vì ACL. Ngược lại, tài khoản quản trị có đủ quyền vẫn không thể lưu dữ liệu vi phạm schema, trừ những cấu hình đặc biệt không được dùng trong bài học.

## 2. Thiết kế cây thư mục dùng trong phòng thực hành

Giả sử directory phục vụ việc thử nghiệm tra cứu nhân sự và nhóm phát triển:

~~~text
dc=lab,dc=example
├── ou=people
│   ├── uid=linh
│   └── uid=an
├── ou=groups
│   └── cn=developers
└── ou=services
    └── uid=reader
~~~

Mỗi dòng trong cây tương ứng một **entry** có DN đầy đủ. Ví dụ:

- **uid=linh,ou=people,dc=lab,dc=example** là DN của người dùng Linh.
- **uid=linh** là RDN của entry đó; phần phía sau là DN của entry cha.
- **ou=people,dc=lab,dc=example** là nhánh tìm kiếm nhân sự.
- **uid=reader,ou=services,dc=lab,dc=example** là tài khoản dịch vụ dùng để bind và truy vấn bằng Spring.

Không dùng **uid** như một định danh bảo đảm duy nhất toàn bộ directory: tính duy nhất của **DN** chỉ được đảm bảo trong phạm vi cây hiện có; hai entry dưới hai OU khác nhau có thể có cùng uid nếu chính sách hệ thống cho phép. Nếu ứng dụng yêu cầu uid là duy nhất trên nhiều nhánh, phải áp dụng quy tắc kiểm tra/giới hạn riêng.

## 3. Schema OpenLDAP: objectClass và thuộc tính

Schema LDAP mô tả các **attributeType**, **objectClass** và **matching rule**. Đối với entry, ba quy tắc dễ gặp nhất là:

1. **MUST**: thuộc tính bắt buộc, kể cả những thuộc tính bắt buộc do lớp cha kế thừa.
2. **MAY**: thuộc tính được phép có nhưng không bắt buộc.
3. **Phân loại objectClass**: thường có một chuỗi lớp **STRUCTURAL** tương thích và có thể kết hợp lớp **AUXILIARY** để bổ sung khả năng; các lớp **ABSTRACT** như **top** đứng trong chuỗi kế thừa.

Một số objectClass có sẵn thường gặp trong schema mặc định:

| objectClass | Loại / mục đích | Thuộc tính cần nhớ |
| --- | --- | --- |
| **top** | Abstract, gốc của cây kế thừa | objectClass |
| **domain** | Structural, biểu diễn domain | dc |
| **dcObject** | Auxiliary, bổ sung thuộc tính domain component | dc |
| **organization** | Structural, đơn vị/tổ chức | o |
| **organizationalUnit** | Structural, nhánh tổ chức | ou |
| **person** | Structural, entry kiểu người | cn, sn |
| **organizationalPerson** | Structural, mở rộng person | Kế thừa cn, sn |
| **inetOrgPerson** | Structural, mở rộng organizationalPerson | Thường dùng uid, mail; vẫn cần cn, sn |
| **groupOfNames** | Structural, nhóm chứa DN thành viên | cn và ít nhất một giá trị member |

**Lưu ý về schema gốc:** Trong LDIF dưới đây, entry gốc dùng **organization + dcObject**, không dùng objectClass **domain** cùng **organization** như hai structural class độc lập. Việc ghép các structural class không tương thích sẽ bị từ chối.

Schema dùng cho **inetOrgPerson** thường được cấp qua bộ schema core/cosine/inetorgperson, tùy gói và cách OpenLDAP được triển khai. Hãy xác nhận chúng đã được nạp trước khi tạo dữ liệu. Với cấu hình động **cn=config**, schema có thể xuất hiện dưới **cn=schema,cn=config**.

### 3.1. Vì sao inetOrgPerson cần cn và sn?

Một entry:

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
~~~

Lớp **inetOrgPerson** kế thừa **organizationalPerson → person**. Do **person** yêu cầu **cn** và **sn**, bỏ **sn** thường dẫn đến lỗi schema **objectClassViolation** (LDAP result code 65). Ngược lại, một entry chỉ dùng **organizationalUnit** không cần có các thuộc tính nhân sự đó.

Schema còn định nghĩa cách so sánh thuộc tính (ví dụ quy tắc matching cho uid hay cn), kiểu giá trị và quy tắc nhiều giá trị. Vì thế, hành vi tìm kiếm không thể suy ra đơn thuần từ cách so sánh chuỗi trong Java.

### 3.2. objectClass không tương đương Java class

Trong Spring Data LDAP, annotation **@Entry** khai báo nhóm objectClass phù hợp với entry LDAP; **@Attribute** ánh xạ thuộc tính sang trường Java. Dù có tên giống nhau, objectClass thuộc **LDAP schema**, còn Java class thuộc **mô hình domain của ứng dụng**. Một DTO có trường mới không khiến OpenLDAP tự thêm attributeType tương ứng: muốn lưu thuộc tính ngoài schema hiện hành, phải lựa chọn thuộc tính đã được cho phép hoặc mở rộng schema đúng cách.

Trong môi trường học, ưu tiên các thuộc tính chuẩn như uid, cn, sn, mail trước khi tự định nghĩa schema. Khi cần schema tùy biến, phải cấp **OID** không xung đột, chọn syntax/matching rule đúng và áp dụng quy trình thay đổi schema riêng.

## 4. Chuẩn bị OpenLDAP để nhập dữ liệu

Ví dụ giả định đã có một **OpenLDAP slapd** chạy với các điều kiện sau:

- **Suffix/base DN:** dc=lab,dc=example.
- **Tài khoản quản trị dữ liệu:** cn=admin,dc=lab,dc=example (hoặc rootDN khác do môi trường thực tế cấu hình), có quyền ghi vào suffix.
- **Endpoint:** ldaps://ldap.lab.example:636, với chứng chỉ hợp lệ được máy client tin cậy.
- **Schema:** đã nạp các lớp **organizationalUnit**, **inetOrgPerson**, **groupOfNames**.
- **Công cụ client:** ldapadd, ldapsearch, ldapmodify, ldapwhoami, ldappasswd, ldapcompare từ bộ OpenLDAP client tools.

Mọi lệnh shell phía dưới dùng cú pháp Bash trên Linux/macOS. Nếu chạy trên PowerShell, thay cách khai báo biến môi trường và truyền tham số tương ứng.

~~~bash
export LDAP_URI='ldaps://ldap.lab.example:636'
export BASE_DN='dc=lab,dc=example'
export ADMIN_DN='cn=admin,dc=lab,dc=example'
export READER_DN='uid=reader,ou=services,dc=lab,dc=example'
~~~

Cấu hình TLS/truststore phải được thiết lập đúng trước khi bind. Có thể sử dụng **LDAPTLS_CACERT** để chỉ định CA file tin cậy cho OpenLDAP client:

~~~bash
export LDAPTLS_CACERT='/path/to/lab-ca.crt'
~~~

Không dùng tùy chọn bỏ xác minh chứng chỉ TLS trong một bài thực hành về bảo mật. Nếu lab chỉ có LDAP ở loopback, có thể bắt đầu bằng môi trường cô lập và cấu hình StartTLS/LDAPS trước khi gửi thông tin xác thực qua mạng.

**Kiểm tra LDAP server có phản hồi:** Root DSE thường có thể truy vấn mà không cần biết base DN:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -s base -b "" namingContexts supportedLDAPVersion
~~~

Các thuộc tính Root DSE thực tế tùy server/chính sách ACL. Đầu ra mong đợi có thể gồm **namingContexts: dc=lab,dc=example**; nếu không thấy, kiểm tra kết nối, quyền và cấu hình trước khi nhập dữ liệu.

## 5. Tạo bộ LDIF dữ liệu mẫu

Tạo file **lab-data.ldif** với nội dung sau. Đây là định dạng LDIF cho **ldapadd** (gồm các entry mới), không phải file sửa ACL:

~~~ldif
dn: dc=lab,dc=example
objectClass: top
objectClass: organization
objectClass: dcObject
dc: lab
o: LDAP Training Lab

dn: ou=people,dc=lab,dc=example
objectClass: top
objectClass: organizationalUnit
ou: people
description: Training users

dn: ou=groups,dc=lab,dc=example
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: ou=services,dc=lab,dc=example
objectClass: top
objectClass: organizationalUnit
ou: services

dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@lab.example
description: Java application developer

dn: uid=an,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@lab.example
description: LDAP integration tester

dn: cn=developers,ou=groups,dc=lab,dc=example
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=lab,dc=example
member: uid=an,ou=people,dc=lab,dc=example
description: Development team

dn: uid=reader,ou=services,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: reader
cn: LDAP Reader
sn: Reader
description: Read only service identity for Spring application
~~~

Các entry được sắp theo thứ tự **cha trước, con sau**. Nếu server đã tạo sẵn entry **dc=lab,dc=example**, hãy xóa riêng khối entry gốc khỏi file nhập để tránh lỗi **entryAlreadyExists**, đồng thời giữ nguyên base DN phù hợp với cấu hình server. Không chạy lặp lại toàn bộ file **ldapadd** trên directory đã nạp; nếu muốn lặp bài học từ đầu, cần khôi phục một môi trường lab riêng.

Đặc điểm đáng chú ý của bộ dữ liệu:

1. Nhánh **ou=people** chứa hai entry **inetOrgPerson** có đủ **cn** và **sn**.
2. Nhóm **groupOfNames** có các giá trị **member** là **DN đầy đủ** của người dùng, không phải uid đơn lẻ. **groupOfNames** phải có ít nhất một **member**.
3. Tài khoản dịch vụ **reader** được biểu diễn như entry thông thường và chưa có **userPassword**. Mật khẩu sẽ được đặt tương tác ở bước sau; không đặt mật khẩu rõ trong file LDIF.
4. Các giá trị mẫu chỉ gồm ASCII để có thể chép trực tiếp. Với giá trị Unicode như tên tiếng Việt có dấu, LDIF chuẩn dùng biểu diễn base64 khi giá trị không thể biểu diễn bằng SAFE-STRING theo đặc tả; công cụ xuất LDIF có thể tự biểu diễn bằng cú pháp **cn:: ...**.

### 5.1. Nhập dữ liệu

~~~bash
ldapadd -x -H "$LDAP_URI" \
  -D "$ADMIN_DN" -W \
  -f lab-data.ldif
~~~

**-x** yêu cầu xác thực đơn giản; **-D** là bind DN; **-W** yêu cầu nhập mật khẩu tương tác. **-f** chỉ định file LDIF. Lệnh phải được chạy bằng tài khoản có quyền thêm entry tại các nhánh tương ứng.

Sau đó kiểm tra:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$ADMIN_DN" -W \
  -b "$BASE_DN" -s sub \
  '(objectClass=inetOrgPerson)' dn uid cn sn mail
~~~

Kết quả kỳ vọng gồm người dùng **linh**, **an** và entry dịch vụ **reader**, vì cả ba đều sử dụng objectClass **inetOrgPerson**. Để chỉ lấy người dùng thuộc nhánh nhân sự, thay **-b** bằng **ou=people,dc=lab,dc=example**.

### 5.2. Đặt mật khẩu bind mà không lưu plaintext vào LDIF

~~~bash
ldappasswd -x -H "$LDAP_URI" \
  -D "$ADMIN_DN" -W -S \
  "$READER_DN"
~~~

**-S** yêu cầu nhập mật khẩu mới tương tác; **-W** yêu cầu mật khẩu quản trị để bind. Thao tác dùng LDAP Password Modify Extended Operation, cần được server hỗ trợ và cho phép; trên một số cấu hình, quyền đối với thao tác đổi mật khẩu còn phụ thuộc chính sách máy chủ. Nếu môi trường không hỗ trợ thao tác này, quản trị viên có thể tạo giá trị băm bằng **slappasswd** rồi cập nhật **userPassword** qua cơ chế quản trị phù hợp. Không ghi mật khẩu vào lịch sử shell bằng **-w** hoặc **-s** trong ví dụ chia sẻ.

Xác nhận bind thành công:

~~~bash
ldapwhoami -x -H "$LDAP_URI" \
  -D "$READER_DN" -W
~~~

Đầu ra thường có dạng **dn:uid=reader,ou=services,dc=lab,dc=example**. Việc bind thành công chỉ xác nhận danh tính; nó **không chứng minh** tài khoản đã được đọc entry nhân sự. Quyền đọc phụ thuộc ACL ở phần tiếp theo.

## 6. ACL của OpenLDAP: cấp quyền theo DN, thuộc tính và thao tác

**Access Control List (ACL)** trong OpenLDAP mô tả **tài nguyên nào** có thể được truy cập bởi **danh tính nào** với **mức quyền nào**. Với cấu hình động **cn=config**, ACL thường được đặt trong thuộc tính **olcAccess** của entry database tương ứng. Cách viết trong **slapd.conf** truyền thống có cùng ý tưởng nhưng hình thức khai báo khác.

Các mức thường gặp, từ thấp lên cao:

| Mức | Ý nghĩa thực dụng |
| --- | --- |
| **none** | Không có quyền. |
| **disclose** | Có thể biết một số thông tin tối thiểu về sự tồn tại/lỗi, không có quyền đọc. |
| **auth** | Đủ quyền cần thiết cho thao tác xác thực, không cho phép tự đọc mật khẩu. |
| **compare** | Cho phép thực hiện so sánh thuộc tính. |
| **search** | Cho phép dùng thuộc tính để chọn entry trong tìm kiếm. |
| **read** | Cho phép lấy giá trị thuộc tính/entry được cấp quyền. |
| **write** | Cho phép thay đổi dữ liệu thuộc phạm vi quyền. |
| **manage** | Mức quản trị cao hơn các quyền truy cập thông thường. |

Các mức quyền có thứ tự và được dùng trong các biểu thức ACL; chi tiết kiểm tra với các thuộc tính đặc biệt như **entry** và **children** còn quan trọng đối với thao tác tạo, xóa và đổi DN.

### 6.1. Quy tắc đọc-only cho ứng dụng Spring

Mục tiêu của lab:

- Tài khoản **reader** được đọc **ou=people**, **ou=groups** và metadata cần thiết, nhưng không được thấy **userPassword** hay sửa thuộc tính.
- Người dùng có thể xác thực bằng mật khẩu cá nhân và, trong ví dụ này, có thể đọc entry của chính mình.
- Danh tính chưa xác thực không được duyệt danh sách người dùng; chỉ được quyền **auth** đối với **userPassword** để thực hiện bind.
- Tài khoản quản trị **rootDN** của database được dùng riêng cho quản trị lab, không đưa vào cấu hình ứng dụng Java.

Trước khi sửa ACL, xác định đúng **database config DN** bằng quyền quản trị **cn=config**. Trên hệ thống được cấu hình với local SASL EXTERNAL:

~~~bash
ldapsearch -LLL -Y EXTERNAL -H ldapi:/// \
  -b cn=config '(olcDatabase=*)' dn olcSuffix
~~~

Ví dụ một hệ thống có thể trả **dn: olcDatabase={1}mdb,cn=config** với **olcSuffix: dc=lab,dc=example**; số thứ tự **{1}** và loại backend tùy bản cài đặt. **Không giả định tên entry này là cố định.**

Tạo file **acl-lab.ldif** bên dưới, thay DN ở dòng đầu bằng chính entry database chứa suffix của lab:

~~~ldif
dn: olcDatabase={1}mdb,cn=config
changetype: modify
replace: olcAccess
olcAccess: {0}to attrs=userPassword by self write by anonymous auth by * none
olcAccess: {1}to dn.subtree="ou=people,dc=lab,dc=example" by dn.exact="uid=reader,ou=services,dc=lab,dc=example" read by self read by * none
olcAccess: {2}to dn.subtree="ou=groups,dc=lab,dc=example" by dn.exact="uid=reader,ou=services,dc=lab,dc=example" read by * none
olcAccess: {3}to * by dn.exact="uid=reader,ou=services,dc=lab,dc=example" read by * none
~~~

**Thứ tự các dòng olcAccess là một phần của hành vi bảo mật.** Trong mỗi rule, OpenLDAP đánh giá phần **to** để xác định tài nguyên và phần **by** để xác định danh tính truy cập. Quy tắc khớp trước thường quyết định kết quả theo cách đánh giá ACL mặc định; vì vậy quy tắc bảo vệ **userPassword** cần được đặt trước quy tắc đọc rộng. Các rule cấp quyền theo **uid=reader** so sánh với **bind DN** đã xác thực, không phải giá trị **uid** do ứng dụng đưa vào filter.

Ý nghĩa cụ thể:

| Rule | Phạm vi | Hành vi |
| --- | --- | --- |
| **{0}** | userPassword của mọi entry | Chủ entry có thể thay mật khẩu của mình; anonymous chỉ có quyền dùng để xác thực; danh tính khác không được đọc mật khẩu. |
| **{1}** | Nhánh people | Reader được đọc; người dùng được đọc entry của chính mình; chủ thể khác bị từ chối. |
| **{2}** | Nhánh groups | Reader được đọc; những chủ thể khác bị từ chối. |
| **{3}** | Các entry/thuộc tính còn lại | Reader được đọc phần không bị chặn trước đó; các chủ thể khác bị từ chối. |

**Cẩn trọng với replace:** **replace: olcAccess** thay toàn bộ ACL hiện có của database được chọn. Chỉ thực hiện trên **database lab riêng** sau khi sao lưu cấu hình; không sao chép cấu hình này lên directory production hoặc database đang dùng chung. Nếu đã có ACL, cần hợp nhất các rule theo chính sách thực tế thay vì thay toàn bộ.

Áp dụng từ máy chạy slapd (hoặc môi trường có quyền quản trị **cn=config** qua local socket):

~~~bash
ldapmodify -Y EXTERNAL -H ldapi:/// \
  -f acl-lab.ldif
~~~

Một số bản đóng gói không bật **ldapi:///** hoặc không ánh xạ peer credentials sang quyền quản trị config. Khi đó phải dùng phương thức quản trị **cn=config** hợp lệ tại môi trường đó. **cn=config** là cây cấu hình; **dc=lab,dc=example** là cây dữ liệu. Tài khoản **cn=admin,dc=lab,dc=example** không mặc nhiên có quyền sửa **cn=config**.

Xem lại cấu hình sau khi áp dụng:

~~~bash
ldapsearch -LLL -Y EXTERNAL -H ldapi:/// \
  -b 'olcDatabase={1}mdb,cn=config' -s base olcAccess
~~~

Thay base DN trong lệnh trên bằng database DN đã tìm được. Nếu cấu hình bị từ chối, xem chẩn đoán của slapd, cú pháp rule, thứ tự ACL và quyền của tài khoản quản trị config.

### 6.2. Vì sao quyền read và write không phải vấn đề của repository?

Spring Data LDAP có thể cung cấp **save(...)**, **delete(...)** và phương thức truy vấn cho cùng một entity, nhưng quyền thực thi vẫn thuộc máy chủ. Với tài khoản bind **reader**, gọi **repository.save(...)** để thay đổi một entry ở **ou=people** sẽ bị server từ chối nếu ACL chỉ cấp **read**. Ứng dụng cần xử lý lỗi truy cập và không nên âm thầm dùng rootDN để “khắc phục” lỗi.

Một số thao tác đòi hỏi quyền lên entry cha, hoặc quyền trên **entry/children** ở cấp LDAP, nên mở rộng ACL cho ghi không thể đơn giản chỉ đổi **read → write** trên một thuộc tính. Hãy xây dựng và kiểm thử policy ghi riêng nếu cần thực hành CRUD.

## 7. Kiểm thử ACL bằng OpenLDAP client

Sau khi nạp dữ liệu, đặt mật khẩu và áp dụng ACL, thực hiện các kiểm tra bằng đúng **reader DN** mà ứng dụng Java sẽ sử dụng.

### 7.1. Truy vấn người dùng thành công

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "ou=people,$BASE_DN" -s sub \
  '(&(objectClass=inetOrgPerson)(uid=linh))' \
  dn uid cn sn mail
~~~

Kết quả mong đợi: một entry **uid=linh,ou=people,dc=lab,dc=example** với **uid**, **cn**, **sn** và **mail**. Với filter của dữ liệu động từ người dùng, ứng dụng Java phải dùng tham số JNDI/Spring LDAP query builder để tránh **LDAP filter injection**, không ghép chuỗi tùy ý vào dấu ngoặc của filter.

### 7.2. Xác nhận mật khẩu không bị đọc

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "uid=linh,ou=people,$BASE_DN" -s base \
  '(objectClass=*)' userPassword
~~~

Reader không được nhận giá trị **userPassword** vì rule **{0}** đã hạn chế quyền đối với thuộc tính này. Kết quả có thể hiển thị DN mà không có **userPassword**, hoặc chịu các giới hạn hiển thị khác tùy server. Việc ẩn **userPassword** là cần thiết ngay cả khi máy chủ lưu mật khẩu dưới dạng hash.

### 7.3. Xác nhận người dùng chưa xác thực không duyệt được directory

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -b "ou=people,$BASE_DN" -s sub \
  '(uid=linh)' dn cn mail
~~~

Theo ACL mẫu, truy vấn anonymous không được đọc thông tin người dùng. LDAP server có thể trả kết quả rỗng hoặc lỗi về quyền tùy cách ẩn thông tin. Đừng suy ra một entry không tồn tại chỉ từ một truy vấn bị ACL hạn chế.

### 7.4. Xác nhận reader không sửa được mail

Tạo file **change-mail.ldif**:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
changetype: modify
replace: mail
mail: changed@lab.example
~~~

Thử thao tác bằng tài khoản reader:

~~~bash
ldapmodify -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -f change-mail.ldif
~~~

Kết quả mong đợi: **Insufficient access** (thường LDAP result code **50**). Kiểm tra lại bằng ldapsearch để xác nhận **mail** không bị thay đổi. Chỉ chạy cập nhật thành công bằng tài khoản quản trị nếu cần minh họa thao tác ghi có chủ đích trong lab.

### 7.5. Kiểm tra quan hệ thành viên nhóm

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "ou=groups,$BASE_DN" \
  '(&(objectClass=groupOfNames)(cn=developers))' \
  dn cn member
~~~

Hai giá trị **member** phải là DN của **linh** và **an**. **OpenLDAP không mặc nhiên sinh thuộc tính memberOf cho entry người dùng chỉ vì groupOfNames có member**. Cơ chế backlink **memberOf** tùy việc cấu hình overlay/phần mở rộng; để kiểm tra nhóm theo dữ liệu mẫu, hãy truy vấn entry nhóm qua thuộc tính **member**.

## 8. Liên hệ trực tiếp với Spring Data LDAP

Trong bài này, OpenLDAP là **LDAP server**; Spring LDAP/Spring Data LDAP là **client API** ở ứng dụng Java. Spring có thể khởi tạo **ContextSource** và repository từ cấu hình tương tự:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.lab.example:636
    base: dc=lab,dc=example
    username: uid=reader,ou=services,dc=lab,dc=example
    password: ${LDAP_BIND_PASSWORD}
~~~

Biến môi trường **LDAP_BIND_PASSWORD** chỉ chứa mật khẩu reader, không sử dụng mật khẩu quản trị. Phải cấu hình JVM truststore để Java xác minh chứng chỉ TLS. Việc chạy được lệnh **ldapsearch** trên máy phát triển không bảo đảm JVM đã có cùng cấu hình truststore.

Ví dụ entity với các annotation LDAP ODM và repository:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
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

    @Attribute(name = "mail")
    private String mail;

    // Constructors, getters/setters được lược bỏ.
}
~~~

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    Optional<Person> findByUid(String uid);
}
~~~

Trường **dn** là định danh LDAP (phân cấp), không phải ID số tự tăng. **@Entry(base = "ou=people")** là DN tương đối so với base của **ContextSource**; không nên ghép **dc=lab,dc=example** hai lần. Tùy thiết lập dự án, cần bật repository scanning (ví dụ **@EnableLdapRepositories**) và các dependency Spring LDAP/Spring Data LDAP phù hợp.

Với **PersonRepository.findByUid("linh")**:

1. Spring Data LDAP xây dựng truy vấn theo thông tin ánh xạ và filter.
2. Spring LDAP lấy context từ **ContextSource** và giao tiếp với OpenLDAP qua JNDI.
3. OpenLDAP kiểm tra **bind identity reader**, **ACL**, **schema** và dữ liệu dưới **ou=people**.
4. Entry phù hợp được ánh xạ thành **Person**. Một số thuộc tính có thể không được trả về nếu ACL giới hạn.

Nếu muốn kiểm soát query rõ ràng hơn, dùng **LdapTemplate** và builder:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class DirectoryLookup {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        return ldapTemplate.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get()
        );
    }
}
~~~

**query().where("uid").is(uid)** giúp xây dựng filter và escape giá trị đúng ngữ cảnh. Vì base đã được cấu hình ở ContextSource, truy vấn chỉ cần **ou=people**. Nếu schema hoặc ACL làm entry không có **cn** trong kết quả, mapper cần xử lý việc thiếu thuộc tính theo yêu cầu nghiệp vụ.

### 8.1. Vì sao CRUD có thể thất bại dù entity đúng?

| Tình huống | Vấn đề ở OpenLDAP | Hành động cần kiểm tra |
| --- | --- | --- |
| **findByUid** trả rỗng | Sai base DN, scope, filter hoặc bị ACL ẩn entry | So sánh ldapsearch với cùng bind DN và base |
| **save** báo schema violation | Thiếu cn/sn, objectClass không khớp, thuộc tính không được phép | Đối chiếu entry LDIF và schema của server |
| **save/delete** báo insufficient access | Bind reader chỉ có quyền read | Tách tài khoản ghi có quyền tối thiểu hoặc giữ lab chỉ đọc |
| **save** tạo DN không mong đợi | Dùng sai RDN, base hoặc mapping **@Id** | Xem DN thực của entry và cấu hình @Entry |
| Thêm group thất bại | groupOfNames thiếu thuộc tính member | Cung cấp ít nhất một DN member |
| Truy vấn nhóm không có memberOf | Overlay memberOf chưa được bật/không áp dụng | Truy vấn thuộc tính member của groupOfNames |

Khi debug Spring LDAP, hãy ưu tiên tái hiện bằng **ldapsearch/ldapmodify dùng cùng DN và endpoint**. Việc thử lệnh với tài khoản admin thường che mất lỗi ACL mà ứng dụng thực gặp.

## 9. Phân biệt OpenLDAP với các LDAP server khác

Giao thức LDAP đưa ra các khái niệm chung, nhưng sản phẩm server có thể khác nhau về **schema mặc định**, **ACL**, **DN dùng cho tài khoản**, **thuộc tính nhóm**, **cơ chế đồng bộ** và **cách quản trị cấu hình**.

| Khía cạnh | OpenLDAP trong bài lab | Điều cần lưu ý khi dùng server khác |
| --- | --- | --- |
| Schema nhân sự | inetOrgPerson và thuộc tính theo RFC/schema đã nạp | Có thể có objectClass/attribute riêng; một số thuộc tính không tồn tại hoặc bị ràng buộc khác |
| Quyền truy cập | olcAccess tại database trong cn=config | Cú pháp và cách đặt ACL có thể hoàn toàn khác |
| Quản trị cấu hình | cn=config hoặc slapd.conf cũ | Không mặc định có cn=config giống OpenLDAP |
| Nhóm | groupOfNames, member chứa DN | Thuộc tính nhóm/backlink có thể khác; memberOf không bảo đảm có sẵn |
| Mật khẩu | userPassword; bind và Password Modify theo chính sách server | Phương thức xác thực, đổi mật khẩu, password policy có thể khác |
| Chỉ mục tìm kiếm | Có thể cấu hình **olcDbIndex** cho MDB | Kiểu chỉ mục và khả năng tối ưu filter khác nhau |

Không nên viết mã Java phụ thuộc mặc định vào **olcAccess**, **olcDbIndex** hoặc **memberOf** khi ứng dụng phải chạy trên nhiều sản phẩm directory. Hãy giữ lớp cấu hình server phù hợp từng môi trường và dựa trên các thuộc tính/filter được hệ thống triển khai thực sự hỗ trợ.

## 10. Lỗi thường gặp khi thực hành

| Kết quả/trạng thái | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| **No such object** (32) | DN cha chưa được tạo hoặc base DN không đúng | Kiểm tra suffix, nhập các entry cha trước |
| **Invalid DN syntax** (34) | Dùng DN sai cú pháp, thiếu escaping RDN | Xem lại DN và dùng API **LdapName/Rdn** khi sinh DN từ Java |
| **Invalid credentials** (49) | Sai DN bind, mật khẩu hoặc phương thức xác thực | Kiểm tra LDAP_URI, bind DN, mật khẩu; không ghi password ra log |
| **Insufficient access rights** (50) | ACL không cho search/read/write | Chạy thử với đúng bind DN và kiểm tra olcAccess |
| **Object class violation** (65) | Thiếu MUST, objectClass không hợp lệ hoặc sai chuỗi kế thừa | Kiểm tra cn/sn, group member và schema được nạp |
| **Entry already exists** (68) | Đã nhập cùng DN trước đó | Không nhập trùng; dùng ldapmodify cho cập nhật |
| **Unavailable / connect error** | LDAP service không chạy, sai DNS/port, TLS lỗi | Kiểm tra endpoint và TLS certificate trust |
| **Tìm được bằng admin nhưng không được bằng reader** | Khác quyền ACL hoặc base cho tài khoản ứng dụng | So sánh cùng query với hai bind identity |

Một vài mã lỗi là **LDAP result code**, có thể được chuyển thành exception khác nhau khi đi qua JNDI và Spring LDAP. Kết quả tìm kiếm rỗng không luôn có nghĩa entry không tồn tại: ACL có thể che entry, hoặc filter/base DN không phù hợp.

### Kiểm thử integration đáng làm

Trong một directory lab được khởi tạo lại được bằng LDIF, thực hiện ít nhất các kịch bản:

1. **Dữ liệu hợp lệ:** nhập đủ cây và kiểm tra hai nhân viên + một nhóm qua ldapsearch.
2. **Schema:** nhập một bản ghi **inetOrgPerson** thiếu **sn** vào môi trường thử nghiệm riêng và xác nhận server từ chối.
3. **ACL read:** reader đọc được **cn/mail** nhưng không đọc được **userPassword**.
4. **ACL write:** reader sửa **mail** thất bại; đọc lại thấy dữ liệu không đổi.
5. **Filter:** truy vấn **uid=linh** có kết quả; dữ liệu chứa ký tự đặc biệt không được phép thay đổi cấu trúc filter.
6. **Spring:** repository nhận đúng **Person** với DN, uid, cn, sn, mail từ bộ dữ liệu đã tạo.
7. **TLS:** JVM tin cậy certificate đúng; kết nối bị từ chối khi certificate không hợp lệ.

Nên tự động hóa việc dựng server kiểm thử, nạp LDIF trước mỗi nhóm bài kiểm tra và xóa toàn bộ lab sau khi chạy. Test mock repository chỉ kiểm tra logic Java, không thể chứng minh schema và ACL trên OpenLDAP hoạt động đúng.

## 11. Bảo mật và vận hành một lab có thể tái tạo

Ngay cả lab cũng nên duy trì vài nguyên tắc:

- **Chỉ dùng dữ liệu giả:** không sao chép thông tin người dùng thật từ directory công ty.
- **Mật khẩu riêng:** không commit mật khẩu, hash mật khẩu thật hay private key TLS trong repository chia sẻ.
- **Quyền tối thiểu:** dùng **reader** cho ứng dụng đọc; tài khoản admin chỉ dùng để khởi tạo dữ liệu và cấu hình.
- **TLS được kiểm chứng:** LDAPS hoặc StartTLS; đừng gửi simple bind credentials qua mạng không mã hóa.
- **Giới hạn truy vấn:** trong ứng dụng, đặt base DN hẹp, size/time limit và phân trang khi cần; trong server, cấu hình index phù hợp với filter phổ biến.
- **Quản lý ACL cẩn thận:** cấu hình cần được kiểm tra trên lab độc lập và có khả năng khôi phục; đặc biệt lưu ý thao tác **replace: olcAccess**.
- **Tái tạo có kiểm soát:** version hóa LDIF dữ liệu mẫu và cấu hình lab (không kèm secrets); xác định rõ suffix, schema cần bật và cách kiểm thử.

Đối với OpenLDAP MDB, có thể cân nhắc chỉ mục cho thuộc tính hay tìm như **uid** và **objectClass**. Cấu hình index, thống kê truy vấn và tối ưu hóa phải theo nhu cầu cụ thể: không nên tự thêm mọi thuộc tính vào index vì sẽ tăng chi phí lưu trữ/cập nhật.

## 12. Câu hỏi ôn tập và ghi nhớ

1. Vì sao **inetOrgPerson** không hợp lệ nếu thiếu **sn** dù lớp này không khai báo trực tiếp mọi thuộc tính bắt buộc?
2. **groupOfNames.member** chứa uid hay DN? Vì sao **memberOf** không mặc định có trên người dùng OpenLDAP?
3. Khác biệt giữa **rootDN**, **bind DN** của reader và DN của entry người dùng là gì?
4. Nếu Spring Data LDAP đọc được uid nhưng không sửa được mail, cần xem lại cấu hình Java hay ACL máy chủ?
5. Vì sao thứ tự **olcAccess** và cách phân biệt **cn=config** với dữ liệu **dc=lab,dc=example** quan trọng?
6. Khi **repository.findByUid(...)** trả về rỗng, làm thế nào xác định lỗi do DN/filter hay do thiếu quyền?
7. Vì sao test Java dùng mock repository chưa đủ để xác nhận mapping và schema LDAP?

**Ghi nhớ:** **LDIF** cung cấp dữ liệu tái tạo được; **schema** kiểm tra entry hợp lệ; **ACL** quyết định danh tính có được đọc và sửa entry hay không. Spring Data LDAP giúp Java thao tác với directory qua repository, nhưng mọi truy vấn và lệnh CRUD vẫn chịu các quy tắc của OpenLDAP. Khi thiết kế một lab tốt, cần thống nhất **suffix, DN, objectClass, dữ liệu mẫu, tài khoản bind, TLS và các kịch bản kiểm thử** để kết quả học tập có thể quan sát, kiểm chứng và tái lập.
