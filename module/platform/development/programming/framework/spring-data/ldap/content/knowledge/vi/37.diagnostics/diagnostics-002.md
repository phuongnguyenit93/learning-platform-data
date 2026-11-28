# Kết nối thành công nhưng tìm kiếm không thấy dữ liệu

Trong ứng dụng **Spring Data LDAP**, có một sự cố dễ gây nhầm lẫn: cấu hình LDAP không báo lỗi, tài khoản dịch vụ **bind thành công**, nhưng phương thức **LdapRepository.findBy...(...)** trả về kết quả rỗng hoặc **LdapTemplate.search(...)** nhận danh sách không có phần tử. Đây là vấn đề chẩn đoán ở ranh giới giữa **kết nối**, **cấu trúc thư mục LDAP**, **phạm vi tìm kiếm**, **filter**, **quyền đọc** và **ánh xạ entry sang đối tượng Java**.

Mục tiêu của bài học thuộc chương **Chẩn đoán** là xác định chính xác nguyên nhân thay vì thử thay đổi mật khẩu hoặc dependency ngẫu nhiên. Người học sẽ thiết lập một chuỗi kiểm tra có thể lặp lại, so sánh **ldapsearch** với **LdapTemplate** và **Spring Data LDAP Repository**, phân biệt kết quả rỗng với ngoại lệ, và bảo vệ thông tin xác thực trong lúc điều tra.

## 1. Bind thành công thực sự chứng minh điều gì?

Trước khi tìm nguyên nhân, cần tách hai thao tác:

1. **Bind:** LDAP server chấp nhận danh tính và phương thức xác thực của client, ví dụ DN **uid=reader,ou=services,dc=example,dc=org** cùng mật khẩu đúng.
2. **Search:** LDAP server xử lý yêu cầu với **base DN**, **scope**, **filter**, thuộc tính muốn trả về và **quyền truy cập (ACL)** của danh tính đã bind.

Một tài khoản có thể đăng nhập hợp lệ nhưng bị giới hạn chỉ được tìm kiếm một nhánh; nó cũng có thể được phép tìm **uid** nhưng không được đọc **mail**. Vì vậy:

> **Bind thành công không đồng nghĩa tìm kiếm sẽ thấy entry hoặc đọc được mọi thuộc tính.**

Ở tầng Spring, việc bean **LdapTemplate** được khởi tạo hoặc repository được inject vào service còn yếu hơn một lần bind thành công: nó chỉ cho thấy các thành phần Java đã được cấu hình. Một số kết nối thực tế chỉ được mở khi bắt đầu thao tác LDAP đầu tiên. Muốn khẳng định bind và search hoạt động, cần thực thi yêu cầu thật qua directory.

### Đầu vào bắt buộc của một lần tìm kiếm

| Thành phần | Ví dụ | Nếu sai thì sao? |
| --- | --- | --- |
| **LDAP endpoint** | ldaps://ldap.example.org:636 | Có thể truy cập nhầm directory/môi trường |
| **Bind identity** | uid=reader,ou=services,dc=example,dc=org | Tài khoản có thể không thấy nhánh cần tìm |
| **Base DN** | ou=people,dc=example,dc=org | Search nhầm cây hoặc báo **noSuchObject** |
| **Scope** | SUBTREE | OBJECT/ONELEVEL có thể bỏ sót entry ở cấp sâu |
| **Filter** | (uid=linh) | Giá trị/thuộc tính/objectClass sai sẽ cho kết quả rỗng |
| **Requested attributes** | uid,cn,mail | Entry có thể được tìm thấy nhưng không có các thuộc tính được phép đọc |
| **Schema và dữ liệu** | inetOrgPerson có uid=linh | Entry có thể tồn tại nhưng không khớp điều kiện |
| **ACL và giới hạn server** | reader có quyền search/read | Có thể bị che entry hoặc kết quả bị giới hạn |

**DN** (Distinguished Name) định vị entry trong cây; **objectClass** cùng schema xác định nhóm thuộc tính được phép/bắt buộc; **LDAP filter** quyết định entry nào thỏa điều kiện. Trong hệ thống **Spring Data LDAP**, các khái niệm đó vẫn tồn tại dù mã Java chỉ gọi một phương thức repository.

## 2. Phân biệt ba dạng lỗi quan sát được

Đừng gộp mọi biểu hiện vào nhãn “không tìm thấy”:

| Hiện tượng | Ý nghĩa khả dĩ | Cách xác minh |
| --- | --- | --- |
| **LDAP Search trả success với 0 entry** | Filter không khớp, scope/base sai vùng có dữ liệu, ACL che entry hoặc nhầm môi trường | Lặp lại truy vấn bằng ldapsearch cùng bind DN |
| **No such object (LDAP result code 32)** | Base DN hoặc DN được tìm không tồn tại theo góc nhìn server; server có thể che thông tin tùy ACL | Kiểm tra DN cha/Root DSE và query với base rộng hơn |
| **Entry có trong ldapsearch nhưng repository trả rỗng/khác kỳ vọng** | Khác base, filter do mapping, objectClass, repository scan hoặc logic Java | So sánh LdapTemplate với repository trên cùng ContextSource |
| **Có entry nhưng thiếu một attribute** | Không yêu cầu attribute, ACL chặn đọc, schema/entry không có hoặc mapping không tương ứng | Yêu cầu chính xác attribute bằng ldapsearch; xem mapper |
| **SizeLimitExceeded/TimeLimitExceeded hoặc referral** | Kết quả có thể chưa đầy đủ vì giới hạn server hoặc phân vùng | Đọc LDAP result/exception, kiểm tra search controls/referral |
| **AuthenticationException/CommunicationException** | Vấn đề bind/kết nối thật sự, khác tình huống kết quả rỗng | Kiểm tra mật khẩu, TLS, DNS, endpoint |

Trong Java, API có thể ném các exception từ JNDI và Spring LDAP thay vì trả danh sách rỗng. Khi chẩn đoán, luôn lưu lại **mã LDAP gốc, tên exception, base, scope và filter** (đã che dữ liệu nhạy cảm). Không chuyển mọi ngoại lệ thành **Collections.emptyList()**: làm như vậy sẽ khiến sai cấu hình, lỗi mạng và lỗi quyền trông giống “người dùng không tồn tại”.

## 3. Dựng một cây LDAP nhất quán để đối chiếu

Giả sử ứng dụng tìm người dùng **linh** trong cây:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=linh
└── ou=services
    └── uid=reader
~~~

Entry đích ở dạng LDIF:

~~~ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
~~~

Các lớp **inetOrgPerson → organizationalPerson → person** phải được server hỗ trợ. **person** yêu cầu thuộc tính **cn** và **sn**; trong dữ liệu mẫu, **uid** là RDN và **uid=linh** là điều kiện filter. Ở directory khác, người dùng có thể được đặt dưới nhánh **ou=users**, **cn=Users** hoặc cây tổ chức phức tạp hơn; không có quy tắc chung rằng tài khoản nào cũng nằm dưới **ou=people**.

Ví dụ cấu hình Java theo Spring Boot:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    username: "uid=reader,ou=services,dc=example,dc=org"
    password: "${LDAP_BIND_PASSWORD}"
~~~

Ở đây:

- **urls** trỏ đến LDAP endpoint; nếu có nhiều directory hoặc môi trường, cần xác nhận đúng host và suffix.
- **base** đặt gốc tương đối cho thao tác **LdapTemplate** và mapping repository của ứng dụng.
- **username** là **bind DN**; không nhất thiết trùng với DN của entry cần tìm.
- **password** đọc từ biến môi trường; không lưu mật khẩu rõ trong source code hay lệnh shell.

**Lưu ý:** URL **ldaps://** cần xác minh chứng chỉ và truststore JVM. Nếu kết nối TLS thất bại, thông thường client nhận lỗi thay vì một search thành công nhưng không có entry. Không tắt kiểm tra TLS để “sửa” một kết quả rỗng.

## 4. Phương pháp khoanh vùng: đi từ server vào Java

Luồng chẩn đoán gọn nhất:

~~~mermaid
flowchart TD
    A["Ứng dụng bind OK nhưng search rỗng"] --> B["ldapsearch cùng endpoint, bind DN, base, scope, filter"]
    B --> C{"ldapsearch có entry?"}
    C -->|Không| D["Kiểm tra DN, scope, filter, ACL, dữ liệu, referral/limits"]
    C -->|Có| E["Chạy LdapTemplate với cùng base/filter"]
    E --> F{"LdapTemplate có kết quả?"}
    F -->|Không| G["Đối chiếu ContextSource base, URL, search scope, filter và config"]
    F -->|Có| H["So sánh repository mapping, objectClass, @Entry và method query"]
    H --> I["Kiểm chứng bằng integration test"]
    D --> I
    G --> I
~~~

Một nguyên tắc cần giữ xuyên suốt: **chỉ thay một biến mỗi lần**. Nếu đồng thời đổi user bind, filter, base DN và code repository, rất khó biết thay đổi nào đã khắc phục sự cố.

### 4.1. Thiết lập biến thử nghiệm

Các lệnh bên dưới dùng Bash và bộ công cụ OpenLDAP client:

~~~bash
export LDAP_URI='ldaps://ldap.example.org:636'
export BASE_DN='dc=example,dc=org'
export PEOPLE_DN='ou=people,dc=example,dc=org'
export PERSON_DN='uid=linh,ou=people,dc=example,dc=org'
export BIND_DN='uid=reader,ou=services,dc=example,dc=org'
~~~

Nếu certificate được ký bởi CA nội bộ, cấu hình CA file tin cậy cho OpenLDAP client, ví dụ:

~~~bash
export LDAPTLS_CACERT='/path/to/trusted-ca.crt'
~~~

**ldapsearch** dùng trust configuration của OpenLDAP client; ứng dụng Java dùng cấu hình TLS của JVM hoặc Spring. Việc lệnh shell chạy thành công chưa chứng minh Java có cùng truststore, nhưng nó giúp cô lập các vấn đề liên quan đến dữ liệu và ACL.

### 4.2. Kiểm tra directory và base DN

Truy vấn **Root DSE** (base DN rỗng) để xem server công bố những naming context nào:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -b "" -s base "(objectClass=*)" namingContexts
~~~

Server có thể trả về:

~~~ldif
dn:
namingContexts: dc=example,dc=org
~~~

Đầu ra thực phụ thuộc server, quyền đọc và chính sách công bố Root DSE. Nếu server trả namingContexts khác hoặc không hiển thị thuộc tính này, không tự kết luận entry đã mất. Hãy xác nhận suffix từ cấu hình directory đang dùng.

Kiểm tra entry tại **ou=people**:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$PEOPLE_DN" -s base \
  "(objectClass=*)" dn ou objectClass
~~~

Nếu lệnh này thất bại với **No such object (32)**, hãy kiểm tra base DN đang nhập, DN cha và cấu hình suffix. Nếu trả success nhưng không thấy entry, ACL có thể che nó; cần so sánh với danh tính quản trị trong một môi trường lab được cấp quyền phù hợp.

### 4.3. Kiểm tra chính entry trước khi thử filter phức tạp

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$PERSON_DN" -s base \
  "(objectClass=*)" dn uid cn sn mail objectClass
~~~

Nếu thấy entry và các thuộc tính, chúng ta đã xác nhận **DN, bind identity, dữ liệu và quyền đọc cơ bản** với chính endpoint thử nghiệm. Nếu không, một filter theo uid hay objectClass càng khó có kết quả. Trong LDAP, không phải thuộc tính nào cũng được trả về cho mọi danh tính; ACL có thể giới hạn riêng quyền đọc và quyền search.

### 4.4. Tăng dần phạm vi tìm kiếm

Tìm một entry dưới nhánh people, trước hết chỉ lọc bằng uid:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$PEOPLE_DN" -s sub \
  "(uid=linh)" dn uid cn mail objectClass
~~~

Sau đó đối chiếu với filter có objectClass:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$PEOPLE_DN" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=linh))" dn uid cn
~~~

Nếu truy vấn **(uid=linh)** có dữ liệu nhưng filter kết hợp không có, hãy xem objectClass của entry và giá trị thực trên server. Không phải mọi tài khoản LDAP đều sử dụng **inetOrgPerson**, đặc biệt khi tích hợp những loại directory khác nhau.

## 5. Sai base DN và nhầm DN tương đối với DN đầy đủ

**Base DN** là nguyên nhân rất hay gặp khi dùng Spring LDAP. Hãy phân biệt hai lớp cấu hình:

~~~text
Server DIT:
dc=example,dc=org
└── ou=people
    └── uid=linh

spring.ldap.base = dc=example,dc=org

Base tương đối trong LdapTemplate = ou=people
Base đầy đủ trên server           = ou=people,dc=example,dc=org
~~~

Khi **ContextSource** đã đặt base **dc=example,dc=org**, code nên dùng **ou=people** làm base tìm kiếm tương đối. Nếu code lại truyền **ou=people,dc=example,dc=org** vào một API đòi DN tương đối, base có thể bị ghép thành:

~~~text
ou=people,dc=example,dc=org,dc=example,dc=org
~~~

DN đó sai vị trí. Triệu chứng có thể là **NameNotFoundException / noSuchObject**, hoặc không có kết quả nếu đường dẫn vô tình tồn tại nhưng không chứa dữ liệu cần tìm.

| Vị trí cấu hình | Ví dụ | Diễn giải |
| --- | --- | --- |
| **spring.ldap.base** | dc=example,dc=org | Gốc của ContextSource |
| **@Entry(base = ...)** | ou=people | Nhánh tương đối cho entity |
| **query().base(...)** | ou=people | Nhánh tương đối trong LdapTemplate |
| **ldapsearch -b** | ou=people,dc=example,dc=org | DN đầy đủ gửi cho LDAP server |

Trong hệ thống dùng nhiều domain hoặc OU, không nên đoán base DN từ email, tên hiển thị hoặc định dạng đăng nhập. Hãy kiểm tra DN đầy đủ của entry đã biết bằng công cụ LDAP và thống nhất nó với cấu hình ContextSource.

### Sai lầm khi dùng relative DN trong repository

Entity minh họa:

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

    // Constructors, getters, setters được lược bỏ.
}
~~~

Với **@Entry(base = "ou=people")** và base **dc=example,dc=org**, repository truy cập khu vực người dùng bên dưới **ou=people,dc=example,dc=org**. Nếu entry thực ở **ou=staff**, phương thức repository có thể không thấy nó dù LDAP bind vẫn hợp lệ.

Để kiểm tra nhanh, dùng ldapsearch với **-b** lần lượt tại DN được ánh xạ và DN thật đã biết; thay đổi **@Entry** chỉ sau khi xác nhận directory structure.

## 6. Sai search scope: OBJECT, ONELEVEL, SUBTREE

LDAP cho phép giới hạn cấp độ duyệt:

| Scope | Nghĩa | Khi base là ou=people |
| --- | --- | --- |
| **OBJECT** | Chỉ chính entry tại base DN | Chỉ ou=people, không tìm uid=linh bên dưới |
| **ONELEVEL** | Chỉ entry con trực tiếp, không gồm base | Tìm uid=linh nếu nó nằm ngay dưới ou=people |
| **SUBTREE** | Base và mọi entry con ở các cấp | Tìm cả entry con sâu hơn, nếu ACL cho phép |

Ví dụ directory có:

~~~text
ou=people,dc=example,dc=org
├── uid=linh
└── ou=engineering
    └── uid=an
~~~

Từ **ou=people**:

- Scope **ONELEVEL** có thể thấy **uid=linh**, nhưng bỏ sót **uid=an** nằm sâu dưới **ou=engineering**.
- Scope **OBJECT** không tìm thấy cả hai entry người dùng.
- Scope **SUBTREE** bao gồm cả hai nếu filter và ACL cho phép.

Các lệnh đối chiếu:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" -D "$BIND_DN" -W \
  -b "$PEOPLE_DN" -s one "(uid=an)" dn

ldapsearch -LLL -x -H "$LDAP_URI" -D "$BIND_DN" -W \
  -b "$PEOPLE_DN" -s sub "(uid=an)" dn
~~~

Nếu hai kết quả khác nhau, việc chọn **scope** có thể giải thích sự cố. Trong mã Spring LDAP, có thể chỉ định rõ phạm vi thay vì phụ thuộc giả định về giá trị mặc định của từng API.

## 7. Filter không khớp: kiểm tra từ đơn giản đến phức tạp

LDAP filter tuân theo cú pháp riêng, không phải SQL WHERE. Ví dụ:

~~~text
(uid=linh)
(&(objectClass=inetOrgPerson)(uid=linh))
(|(uid=linh)(uid=an))
(&(objectClass=inetOrgPerson)(mail=linh@example.org))
~~~

Các trường hợp dễ làm kết quả rỗng:

- **Sai attribute:** thư mục thực dùng **sAMAccountName** hoặc thuộc tính đăng nhập riêng, nhưng code tìm **uid**.
- **Sai giá trị:** ứng dụng gửi email **linh@example.org** vào filter **uid**, trong khi uid thực tế chỉ là **linh**.
- **Sai objectClass:** filter yêu cầu **inetOrgPerson** trong khi entry có objectClass khác.
- **Điều kiện AND quá chặt:** chỉ một nhánh không khớp cũng làm cả filter không khớp.
- **Dữ liệu có khoảng trắng/ký tự đặc biệt:** giá trị thực khác kỳ vọng, hoặc code tự nối chuỗi làm filter sai.
- **Quy tắc matching khác tưởng tượng:** việc so sánh theo matching rule của LDAP schema, không giống mọi phép so sánh chuỗi Java hay SQL.
- **Thuộc tính không được phép search:** ACL có thể chặn một thuộc tính được dùng trong filter mà không báo cho client thấy “bạn thiếu quyền” dưới dạng dễ phân biệt.

Đối với directory lớn, hạn chế filter thật sự cần thiết, trả về những thuộc tính cần đọc và kiểm tra index server khi gặp chậm/timeout. Tuy nhiên, việc thiếu index thường dẫn đến vấn đề hiệu năng/giới hạn hơn là khiến một truy vấn đầy đủ tự nhiên trả rỗng.

### 7.1. Không nối trực tiếp giá trị người dùng vào LDAP filter

Ví dụ không an toàn:

~~~java
// Tránh sử dụng: giá trị uid có thể điều khiển cú pháp filter.
String filter = "(uid=" + userInput + ")";
~~~

Với JNDI, có thể dùng overload có tham số:

~~~java
context.search(
    "ou=people,dc=example,dc=org",
    "(uid={0})",
    new Object[]{userInput},
    controls
);
~~~

**filterArgs** được JNDI LDAP provider xử lý theo quy tắc escape giá trị filter. Với Spring LDAP, nên dùng **LdapQueryBuilder** để tránh tự tạo chuỗi filter:

~~~java
query().base("ou=people").where("uid").is(uid)
~~~

Đừng lấy escaping của **LDAP filter** để xử lý **DN**: DN và filter dùng hai quy tắc khác nhau. Khi dựng DN từ input, dùng **LdapName** và **Rdn** hoặc công cụ name builder phù hợp.

## 8. ACL: có quyền bind nhưng không có quyền search/read

Một LDAP server có thể bảo vệ danh sách nhân sự hoặc thuộc tính nhạy cảm bằng **Access Control List (ACL)**. Ví dụ, tài khoản dịch vụ **reader** được bind thành công nhưng bị chặn khi tìm dưới **ou=people**. Tùy server và cách cấu hình ACL, client có thể nhận:

- Search thành công nhưng không có entry phù hợp.
- Search thấy entry nhưng thiếu **cn**, **mail** hoặc thuộc tính khác.
- Lỗi quyền truy cập hoặc **noSuchObject** nếu server che thông tin về nhánh.

Trong OpenLDAP, quyền **search** (dùng một attribute trong filter), **read** (nhận giá trị), **compare**, **auth**, **write** là những quyền khác nhau. Một chính sách cho phép **auth** với **userPassword** không đồng nghĩa cho phép đọc danh sách người dùng.

### 8.1. So sánh cùng truy vấn dưới hai danh tính

Trước hết dùng đúng tài khoản của ứng dụng:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$PEOPLE_DN" -s sub "(uid=linh)" \
  dn uid cn mail
~~~

Trong **môi trường lab có quyền hợp lệ**, có thể chạy cùng câu lệnh với một tài khoản quản trị dữ liệu:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "cn=admin,dc=example,dc=org" -W \
  -b "$PEOPLE_DN" -s sub "(uid=linh)" \
  dn uid cn mail
~~~

Nếu quản trị viên thấy entry còn **reader** không thấy, vấn đề nhiều khả năng nằm ở **ACL hoặc chính sách phân quyền theo danh tính**. Cần xác định quyền tìm/đọc trên nhánh, entry và attribute cụ thể; nếu không có quyền tự xem ACL, chuyển thông tin chẩn đoán cho quản trị directory. Không đổi ứng dụng sang tài khoản quản trị như một cách sửa nhanh.

Các truy vấn phải dùng **cùng endpoint, base, scope, filter và requested attributes**. Nếu thay endpoint hoặc filter khi đổi tài khoản, việc so sánh không còn cô lập đúng yếu tố quyền.

### 8.2. ACL đối với một số attribute

Ví dụ tài khoản **reader** tìm được DN nhưng không thấy **mail**. Có thể do:

1. Entry không có thuộc tính **mail**.
2. Truy vấn không yêu cầu thuộc tính **mail**.
3. Quyền **read** trên **mail** bị chặn.
4. Mapper/serialization trong Java không đưa giá trị ra kết quả.

Đừng mặc định **SearchResult** có đầy đủ attributes; server chỉ trả những attribute được yêu cầu và được phép đọc, tuân theo giới hạn của LDAP server.

## 9. Truy vấn LdapTemplate trước khi kiểm tra repository

Khi ldapsearch đã tìm thấy entry bằng tài khoản ứng dụng, bước tiếp theo là chạy **LdapTemplate** với filter và base càng giống lệnh CLI càng tốt.

Ví dụ:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PersonDiagnostics {
    private final LdapTemplate ldapTemplate;

    public PersonDiagnostics(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNamesByUid(String uid) {
        return ldapTemplate.search(
            query()
                .base("ou=people")
                .where("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                attrs.get("cn").get().toString()
        );
    }
}
~~~

Mã giả định **ContextSource** đã cấu hình base **dc=example,dc=org** và entry trả về có thuộc tính **cn** được phép đọc. Nếu nghi ngờ bị ACL ẩn **cn**, trong bước chẩn đoán đầu nên dùng mapper linh hoạt hơn để xác nhận **entry được tìm thấy** trước khi cố lấy giá trị một attribute:

~~~java
import java.util.List;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class DnDiagnostics {
    private final LdapTemplate ldapTemplate;

    public DnDiagnostics(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findRelativeDns(String uid) {
        return ldapTemplate.search(
            query().base("ou=people").where("uid").is(uid),
            (ContextMapper<String>) context ->
                ((DirContextOperations) context).getDn().toString()
        );
    }
}
~~~

Ở cách thứ hai, kết quả trả về DN theo cách biểu diễn của context; trong trường hợp ContextSource có base, nó thường là **DN tương đối**, không nhất thiết là DN đầy đủ như ldapsearch trả về. Giá trị này đủ giúp nhận diện entry và định vị nhánh khi chẩn đoán.

**Nếu ldapsearch có entry nhưng LdapTemplate không có**, kiểm tra lần lượt: endpoint Java thực dùng, thông tin bind, **spring.ldap.base**, base tương đối trong query, scope, filter và profile/application properties đang được nạp. Phần lớn sự cố nằm ở **hai truy vấn thực ra không tương đương**.

### 9.1. Đối chiếu scope rõ ràng

Khi nghi ngờ scope, có thể chỉ định trong query:

~~~java
import org.springframework.ldap.query.SearchScope;

ldapTemplate.search(
    query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("uid").is(uid),
    (AttributesMapper<String>) attrs ->
        attrs.get("cn").get().toString()
);
~~~

Đây là phần mã minh họa đặt bên trong method có biến **uid** và **ldapTemplate** tương ứng. Chọn **SUBTREE** chỉ khi ứng dụng có nhu cầu tìm xuyên nhiều cấp OU; với directory lớn, cần giới hạn base và điều kiện filter hợp lý.

## 10. Khi LdapTemplate tìm được nhưng repository không trả dữ liệu

Sau khi chứng minh **LdapTemplate.search(...)** tìm được entry, hãy kiểm tra tầng ánh xạ của **Spring Data LDAP**:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    Optional<Person> findByUid(String uid);
}
~~~

Lời gọi:

~~~java
Optional<Person> person = personRepository.findByUid("linh");
~~~

Những nguyên nhân thường gặp ở tầng này:

| Điểm kiểm tra | Ví dụ sai | Cách xử lý |
| --- | --- | --- |
| **@Entry(base=...)** | Đặt **ou=users** trong khi entry nằm dưới **ou=people** | Dùng base đúng với DN thực |
| **@Entry(objectClasses=...)** | Đòi **inetOrgPerson** khi entry chỉ có class khác | Đối chiếu objectClass server với domain mapping |
| **@Attribute(name=...)** | Field Java tên login nhưng attribute LDAP là uid; annotation không khớp | Ánh xạ **@Attribute(name = "uid")** đúng |
| **@Id** | Sử dụng ID số của JPA hoặc import sai annotation | Dùng **javax.naming.Name** và **org.springframework.ldap.odm.annotations.Id** |
| **Tên method dẫn xuất** | findByUsername nhưng Java entity không có property username | Dùng tên property đúng hoặc truy vấn được khai báo phù hợp |
| **Repository scan** | Interface không được Spring phát hiện | Đặt trong package được scan hoặc cấu hình **@EnableLdapRepositories** |
| **Dữ liệu thiếu bắt buộc** | Entry không có cn/sn hoặc ACL ẩn thuộc tính cần mapping | Kiểm tra LDIF/schema, thuộc tính trả về và mapper |

**Phân biệt:** repository không được scan thường gây lỗi **không có bean** lúc khởi động, trong khi repository có bean nhưng **findByUid** rỗng thường gắn với điều kiện tìm kiếm hoặc ánh xạ.

Một truy vấn repository có thể dựa trên **@Entry** và những ràng buộc **objectClass**, không hoàn toàn giống filter **(uid=linh)** được nhập thủ công. Khi so sánh, cần đối chiếu filter thực của hai API hoặc giản lược từng điều kiện có kiểm soát.

### 10.1. Entity không tự di chuyển entry

Việc gắn **@Entry(base = "ou=people")** không khiến Spring tạo hay chuyển toàn bộ tài khoản dưới nhánh people. Nó chỉ định vị trí/schema áp dụng cho mapping. Nếu dữ liệu LDAP thực vẫn ở nhánh khác, tìm kiếm có thể không thấy; muốn thay đổi vị trí trong directory cần thao tác DN/rename đúng quyền và đúng schema.

## 11. Các tình huống đặc biệt từ LDAP server

### 11.1. Trỏ nhầm môi trường hoặc naming context

Tên máy chủ **ldap.example.org** có thể trỏ đến một directory khác với môi trường chứa dữ liệu, hoặc hệ thống có nhiều suffix. Nếu bind DN tồn tại ở nhiều môi trường, xác thực vẫn có thể thành công trong khi **ou=people** chưa có dữ liệu mẫu.

Đối chiếu DNS, host, cổng, Root DSE, base DN và một entry mẫu được biết chắc trong **đúng môi trường**. Không dựa vào việc “đăng nhập được” để nhận diện môi trường.

### 11.2. Referral và nhiều nhánh/directory

Một số LDAP server chia cây dữ liệu qua **referral**. Search bắt đầu từ một suffix có thể chỉ ra server khác chứa dữ liệu. Tùy cấu hình JNDI/Spring LDAP, referral có thể gây ngoại lệ, bị bỏ qua hoặc được theo sau. Trước khi bật tự theo referral, cần hiểu endpoint đích và việc chuyển tiếp thông tin xác thực để tránh dùng credentials không phù hợp.

Nếu không tìm thấy người dùng dưới suffix A nhưng người dùng tồn tại ở suffix B, hãy kiểm tra **naming context và chính sách truy vấn xuyên directory**, không mặc định rằng scope SUBTREE có thể vượt qua mọi referral.

### 11.3. Size limit, time limit và phân trang

Search có thể bị giới hạn số kết quả hoặc thời gian ở phía server hay client. Một truy vấn rất rộng như **(objectClass=*)** có thể bị cắt trước khi trả đến entry đang tìm, hoặc ném **SizeLimitExceededException**. Khi cần phân trang, phải dùng cơ chế paging được server hỗ trợ và kiểm tra hết các trang.

Để tìm một người dùng, hãy chọn base hẹp và filter đặc hiệu; không quét toàn directory rồi lọc một danh sách đã bị cắt trong Java. **Kết quả của một trang đầu không chứng minh entry không tồn tại trong các trang còn lại.**

### 11.4. Operational attributes và nhóm

Không phải mọi attribute đều được trả về khi yêu cầu mặc định. Một số là **operational attributes** và cần yêu cầu tường minh. Ngoài ra, trong OpenLDAP, thuộc tính **memberOf** không tự có trên người dùng chỉ vì một entry **groupOfNames** chứa DN của họ; điều đó có thể phụ thuộc overlay hoặc cách server quản lý nhóm.

Nếu filter **(memberOf=cn=developers,ou=groups,dc=example,dc=org)** trả rỗng, trước hết kiểm tra server thực có cung cấp memberOf và giá trị đúng hay không. Có thể truy vấn trực tiếp nhóm theo **member=DN** nếu schema và ACL cho phép.

### 11.5. Replication và dữ liệu chưa đồng bộ

Trong hệ thống nhiều LDAP server, dữ liệu mới có thể đã được ghi trên node A nhưng chưa xuất hiện trên node B. Hãy ghi nhận host cụ thể mà từng client truy cập, topology replication và chính sách nhất quán; đừng khẳng định directory “không có dữ liệu” khi đang so sánh hai node ở thời điểm chưa đồng bộ.

## 12. Logging và quan sát hiệu quả, an toàn

Trong môi trường phát triển, có thể tăng mức log một cách giới hạn:

~~~yaml
logging:
  level:
    org.springframework.ldap: DEBUG
    org.springframework.data.ldap: DEBUG
~~~

Không phải mọi phiên bản Spring đều log đầy đủ LDAP filter hoặc DN ở cùng mức. Dùng log để nhận biết luồng lời gọi/exception và bổ sung log ứng dụng chứa **endpoint đã rút gọn, base, scope, loại filter, request ID và thời gian thực hiện**. Nếu cần log giá trị filter trong môi trường test, hãy che uid/email/dữ liệu cá nhân và bật trong thời gian ngắn.

Đặc biệt tránh:

- In **spring.ldap.password** hoặc giá trị **Context.SECURITY_CREDENTIALS** ra log.
- Bật trace JNDI hoặc network dump trong production làm lộ tên người dùng/thuộc tính.
- Ghi nguyên dữ liệu LDIF thực của tổ chức vào tài liệu hoặc issue chia sẻ.
- Đánh đồng **0 kết quả** với **user not found** nếu thư viện trả về lỗi khác, hoặc ACL đang che entry.

Một báo cáo chẩn đoán hữu ích nên ghi:

| Trường | Ví dụ |
| --- | --- |
| Môi trường/endpoint | staging LDAP, cổng LDAPS 636 |
| Bind identity | DN dịch vụ đã che thông tin nhạy cảm |
| Base/scope | ou=people,dc=example,dc=org / SUBTREE |
| Filter | uid bằng giá trị mẫu, objectClass=inetOrgPerson |
| Requested attributes | uid,cn,mail |
| Kết quả CLI | success, 1 entry hoặc 0 entry / mã lỗi |
| Kết quả LdapTemplate | số lượng entry, loại exception nếu có |
| Kết quả repository | Optional có/không, class mapping |
| Đối chiếu ACL | cùng query với reader và admin trong lab |

Khi thu thập thông tin, chỉ ghi giá trị cần thiết để tái hiện và bảo đảm không chứa mật khẩu, token hoặc thông tin người dùng nhạy cảm.

## 13. Checklist chẩn đoán theo triệu chứng

| Triệu chứng | Kiểm tra trước | Bước tiếp theo |
| --- | --- | --- |
| **Bind OK, ldapsearch 0 kết quả** | Base DN, scope, filter và DN thực | Kiểm tra objectClass, ACL, suffix, môi trường |
| **ldapsearch báo noSuchObject (32)** | Entry tại base DN có tồn tại không | Xác minh suffix và các OU cha |
| **Admin thấy, reader không thấy** | ACL search/read cho reader | Liên hệ quản trị directory, không dùng admin làm bind app |
| **(uid=linh) có kết quả, filter AND không có** | Các nhánh của filter, objectClass | Kiểm tra schema/attribute và giá trị thật |
| **ldapsearch có, LdapTemplate không có** | ContextSource base, URL, profile, bind DN, query scope | So sánh filter và DN thực gửi |
| **LdapTemplate có, repository rỗng** | @Entry, @Attribute, objectClasses, derived method | So sánh mapping với dữ liệu LDIF |
| **Entry có nhưng cn/mail thiếu** | Requested attrs, ACL và dữ liệu entry | Điều chỉnh mapper hoặc quyền theo chính sách |
| **Chỉ sai ở một node LDAP** | Replication/caching/topology | So sánh endpoint và thời gian đồng bộ |
| **Chậm/đôi khi không đủ kết quả** | Server time/size limit, paging, filter | Thu hẹp base, tối ưu filter và xét paging |
| **Đúng lúc dev nhưng sai production** | Base, profile, suffix, schema, ACL, bind identity | Dùng test cùng cách truy vấn, không chép secrets |

### Quy trình chẩn đoán ngắn gọn

1. **Chứng minh có một entry** bằng DN đầy đủ và tài khoản đọc phù hợp trên đúng server.
2. **Chạy ldapsearch cùng bind DN của ứng dụng**, so sánh lần lượt base, scope, filter.
3. **Dùng LdapTemplate** với cùng các điều kiện; đừng để base ContextSource bị ghép hai lần.
4. **Dùng repository** và đối chiếu **@Entry / @Attribute / objectClass / derived query**.
5. **Kiểm tra ACL, paging/referral và replication** nếu những truy vấn đã tương đương mà kết quả vẫn khác.
6. **Viết integration test** với dữ liệu LDIF xác định trước để giữ lại bằng chứng về nguyên nhân và ngăn lỗi tái xuất hiện.

## 14. Thực hành kiểm thử với directory

Một bài kiểm thử đáng tin cậy cần directory thực hoặc nhúng với cây dữ liệu xác định. Ví dụ:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
~~~

Import vào directory lab phù hợp (hoặc cấu hình test embedded LDAP nạp LDIF), sau đó kiểm tra:

1. **Positive case:** filter **(uid=linh)** dưới **ou=people** với SUBTREE phải trả một entry.
2. **Negative case:** filter **(uid=khong-ton-tai)** trả 0 entry, không phải lỗi kết nối.
3. **Scope case:** OBJECT tại **ou=people** không tìm ra uid=linh; ONELEVEL/SUBTREE tìm ra nếu nằm ngay dưới OU.
4. **Base case:** truy vấn nhánh **ou=groups** không trả người dùng Linh.
5. **ACL case:** reader thiếu quyền search không được thấy entry dù user bind được; tài khoản quản trị lab thấy.
6. **Mapping case:** **LdapTemplate** và **PersonRepository.findByUid("linh")** trả kết quả nhất quán trên cùng ContextSource.
7. **Escaping case:** dữ liệu uid chứa ký tự đặc biệt được xử lý bằng query builder hoặc filter arguments; không cho phép chuỗi đầu vào thay đổi cấu trúc filter.
8. **TLS case:** endpoint và certificate phải phù hợp với JVM; mật khẩu không được xuất hiện trong log test.

Nếu dùng server nhúng khác OpenLDAP (ví dụ UnboundID), nhớ rằng **ACL, schema tùy biến và referral** có thể khác server thật. Các trường hợp kiểm tra ACL và tính tương thích directory cần chạy thêm trên chính loại LDAP server dự kiến triển khai.

### Bài tập phân tích

Ứng dụng cấu hình:

~~~yaml
spring:
  ldap:
    base: "dc=example,dc=org"
~~~

Code:

~~~java
query().base("ou=people,dc=example,dc=org")
    .where("uid").is("linh");
~~~

Trong khi lệnh:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=linh)" dn
~~~

trả entry đúng.

**Hãy xác định nguyên nhân hợp lý nhất:** lệnh ldapsearch nhận **full DN**, còn LdapTemplate query nhận base **tương đối với ContextSource**. Code Java có nguy cơ tạo DN bị lặp suffix; sửa thành **query().base("ou=people")** và xác minh lại. Sau đó so sánh ACL/filter nếu vẫn không ra kết quả.

## 15. Câu hỏi ôn tập và ghi nhớ

1. Vì sao bind thành công nhưng tìm kiếm vẫn có thể trả danh sách rỗng?
2. Phân biệt base DN đầy đủ trong ldapsearch với base DN tương đối trong LdapTemplate như thế nào?
3. Khi nào **ONELEVEL** cho ít kết quả hơn **SUBTREE**? **OBJECT** khác cả hai ở đâu?
4. Cách phân biệt “entry không tồn tại” với “ACL che entry” trong môi trường lab?
5. Tại sao một filter **(&(objectClass=inetOrgPerson)(uid=linh))** có thể trả rỗng dù **(uid=linh)** có kết quả?
6. Nếu **ldapsearch** và **LdapTemplate** giống nhau nhưng repository trả rỗng, cần xem lại annotation và derived method nào?
7. Vì sao không được nối trực tiếp uid từ HTTP request vào LDAP filter?
8. Làm thế nào lập integration test để phân biệt lỗi kết nối, lỗi tìm kiếm và lỗi ánh xạ?

**Ghi nhớ:** Kết nối LDAP là điều kiện cần, nhưng **không bảo đảm tìm kiếm có dữ liệu**. Hãy bắt đầu bằng một entry và DN đã biết, dùng cùng endpoint và bind identity để so sánh **ldapsearch → LdapTemplate → Spring Data LDAP Repository**. Lần lượt xác minh **base DN, scope, filter, objectClass/schema, ACL, requested attributes, mapping, size/time limits và replication**. Đây là phương pháp chẩn đoán có bằng chứng, an toàn và có thể chuyển thành kiểm thử hồi quy.

## Tài liệu đối chiếu

- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/) — repository và ánh xạ entry LDAP.
- [Spring LDAP — Reference](https://docs.spring.io/spring-ldap/reference/) — LdapTemplate, LDAP query và ContextSource.
- [Spring LDAP — Query Builder](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html) — xây filter bằng API thay vì nối chuỗi thủ công.
- [RFC 4511 — LDAPv3](https://www.rfc-editor.org/rfc/rfc4511.html) — SearchRequest, SearchResult, scope và LDAP result code.
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html) — cú pháp và escaping của LDAP filter.
- [OpenLDAP Administrator's Guide](https://www.openldap.org/doc/admin26/) — DIT, schema, ACL, tìm kiếm và chẩn đoán OpenLDAP.
