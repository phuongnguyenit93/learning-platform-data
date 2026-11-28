# Vai trò của dc, ou, cn, uid và cách tránh hiểu chúng như từ khóa cố định

## Mục tiêu bài học

Khi nhìn vào một distinguished name (DN) như **uid=an,ou=people,dc=example,dc=org**, người mới học LDAP thường nghĩ **dc**, **ou**, **cn**, **uid** là bốn từ khóa đặc biệt bắt buộc phải xuất hiện theo một thứ tự cố định. Cách hiểu đó dễ dẫn tới sai mô hình dữ liệu, ghép DN bằng chuỗi, chọn sai search base và tạo entry vi phạm schema.

Thực tế, **dc**, **ou**, **cn** và **uid** là **tên các loại thuộc tính (LDAP attribute types)** đã được định nghĩa trong schema. Chúng thường được chọn làm thành phần tên của entry vì thuận tiện cho một quy ước tổ chức directory. Quy ước thông dụng không có nghĩa mọi LDAP directory bắt buộc dùng chính các tên đó hoặc có đúng một dạng cây cố định.

Trong module **SPRING_DATA_LDAP**, hiểu bản chất của các thành phần tên giúp bạn ánh xạ entry phân cấp sang đối tượng Java, xây DN đúng bằng Spring LDAP, tìm kiếm qua repository hoặc **LdapTemplate**, thực hiện CRUD an toàn và kiểm thử trên một LDAP directory.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa thông dụng của **dc**, **ou**, **cn**, **uid** và phân biệt chúng với **objectClass**.
- Đọc đúng **attribute=value**, **RDN**, **DN**, **base DN** và **DN tương đối**.
- Hiểu tại sao tên thuộc tính được chọn để đặt tên entry không tự quyết định loại entry hoặc vị trí cha.
- Thiết kế cây LDAP nhất quán mà không mặc định **ou=people** hay **uid=...** là quy tắc của giao thức.
- Sử dụng **LdapNameBuilder**, **LdapQueryBuilder**, **LdapTemplate** và ánh xạ Spring Data LDAP một cách phù hợp.
- Phát hiện các lỗi naming, schema, tìm kiếm và bảo mật trước khi đưa dữ liệu vào môi trường thật.

## 1. Nhìn vào cây: DN là tên có cấu trúc

Ví dụ directory của một tổ chức:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=binh
└── ou=groups
    └── cn=reviewers
~~~

DN đầy đủ của người dùng An là:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

LDAP viết DN từ **entry cụ thể nhất ở bên trái** đến **các entry cha ở bên phải**:

| Thành phần trong DN | Đọc theo ngữ cảnh ví dụ | Quan hệ |
| --- | --- | --- |
| **uid=an** | Tên tương đối của entry người dùng An | Entry cần truy cập |
| **ou=people** | Tên entry cha dùng gom các hồ sơ người dùng | Cha trực tiếp |
| **dc=example** | Thành phần được chọn cho một nhánh tên miền | Một cấp cao hơn |
| **dc=org** | Thành phần tên ở cấp trên cùng trong suffix ví dụ | Cấp gốc của suffix đang dùng |

Trong ví dụ, **uid=an** là một **relative distinguished name (RDN)**; toàn bộ **uid=an,ou=people,dc=example,dc=org** là một **DN**. DN xác định **vị trí duy nhất của entry trong cây** mà directory đang quản lý. RDN chỉ xác định tên của entry **trong phạm vi entry cha**.

Đừng nhầm “tên giống DNS” với “đường dẫn mạng”: **dc=example,dc=org** chỉ là một cách biểu diễn naming context thường gặp. Nó **không tự tạo DNS record**, không xác định địa chỉ IP của LDAP server và không ngụ ý ứng dụng phải kết nối tới hostname **example.org**.

### 1.1. Tại sao gọi là các attribute type?

Một thành phần RDN có dạng **loại thuộc tính = giá trị**, ví dụ **uid=an**:

- **uid** là **attribute type** được directory schema nhận biết.
- **an** là **giá trị thuộc tính** được dùng làm thành phần tên của entry.
- Dấu bằng **=** là ký hiệu của cú pháp DN, không phải một câu lệnh gán biến của Java.

Thuộc tính được dùng trong RDN còn xuất hiện trong entry theo quy tắc đặt tên và schema tương ứng. Nhưng một entry còn có nhiều thuộc tính khác không nằm trong DN, chẳng hạn **mail**, **sn**, **description**.

RDN có thể gồm **nhiều thành phần thuộc tính** (multi-valued RDN), viết bằng dấu **+**, mặc dù các ví dụ nhập môn thường dùng một thành phần. Vì vậy ngay cả cách diễn đạt “một RDN luôn chỉ có một attribute=value” cũng không hoàn toàn chính xác.

~~~text
uid=an,ou=people,dc=example,dc=org        # RDN một thành phần
cn=An Tran+uid=an,ou=people,dc=example,dc=org  # RDN nhiều thành phần (minh họa cú pháp)
~~~

RDN nhiều thành phần chỉ hợp lệ khi schema, quy tắc đặt tên và LDAP server hỗ trợ tổ hợp đó. Không nên tự thay đổi DN người dùng thành multi-valued RDN chỉ vì giao thức cho phép cú pháp.

## 2. Vai trò thông dụng của dc, ou, cn và uid

| Attribute type | Tên đầy đủ | Thường biểu diễn | Thường thấy ở |
| --- | --- | --- | --- |
| **dc** | **domainComponent** | Một thành phần tên kiểu domain | Suffix dạng **dc=example,dc=org** |
| **ou** | **organizationalUnit** | Đơn vị tổ chức hoặc nhánh phân loại dữ liệu | **ou=people**, **ou=groups**, **ou=Engineering** |
| **cn** | **commonName** | Tên chung/để hiển thị của người, nhóm hoặc đối tượng | **cn=An Tran**, **cn=reviewers** |
| **uid** | **userId** | Mã định danh người dùng theo quy ước directory | **uid=an**, **uid=account123** |

Đây là ý nghĩa phổ biến của **attribute types** trong schema LDAP, không phải danh sách “từ khóa dành riêng” của một ngôn ngữ lập trình. Các ví dụ lựa chọn vị trí và cách đặt tên chỉ là **quy ước thiết kế**.

### 2.1. dc: thành phần tên miền

Một tổ chức có DNS domain **example.org** thường chọn directory suffix:

~~~text
dc=example,dc=org
~~~

Entry ở gốc suffix có thể dùng object class **domain**:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example
~~~

Ở đây, **dc** đóng vai trò **thuộc tính** và một giá trị **dc=example** được chọn làm RDN của entry. Suffix **dc=example,dc=org** là một DN hoàn chỉnh đối với directory đang phục vụ nhánh đó, dù có thành phần **dc=org** ở bên phải.

Không phải mọi LDAP server bắt buộc có suffix dạng **dc=...**. Một directory có thể dùng suffix kiểu **o=Example Corporation** hoặc một naming context khác nếu server/schema cho phép. Đặc biệt, ứng dụng không được tự suy suffix từ email domain mà bỏ qua cấu hình thực tế của directory.

### 2.2. ou: đơn vị tổ chức hoặc nhánh phân loại

Object class **organizationalUnit** thường được dùng để biểu diễn một đơn vị hoặc container logic. Ví dụ:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
~~~

**ou=people** ở đây là entry có RDN sử dụng thuộc tính **ou**. Bạn cũng có thể thấy **ou=Finance**, **ou=Operations** hoặc **ou=Applications** nếu tổ chức phân nhóm theo đơn vị hay chức năng.

Nhưng giao thức LDAP **không quy định phải có ou=people** mới lưu được người dùng; không có quy tắc nói mọi nhóm nhất thiết nằm dưới **ou=groups**. Đây là những lựa chọn thiết kế giúp quản trị quyền, tìm kiếm theo subtree và đồng bộ dữ liệu thuận tiện hơn.

Một entry có object class **organizationalUnit** có thể cần tuân theo các thuộc tính bắt buộc của schema; tên **ou** một mình trong DN không thay thế những quy tắc đó. Ngược lại, một thuộc tính **ou** xuất hiện trong một entry người dùng có thể mô tả phòng ban của người đó mà **không** biến entry thành một đơn vị tổ chức.

### 2.3. cn: tên chung

**cn (commonName)** thường là tên hiển thị của một người, tên nhóm hoặc một đối tượng cần được đặt tên. Ví dụ:

~~~ldif
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: reviewers
member: uid=an,ou=people,dc=example,dc=org
~~~

Ở entry nhóm, **cn** là thuộc tính tên nhóm và được chọn làm RDN. Với người dùng thuộc schema **person** hoặc **inetOrgPerson**, **cn** cũng là một thuộc tính bắt buộc qua kế thừa class **person**.

Điều này **không** có nghĩa entry người dùng bắt buộc phải đặt RDN bằng **cn**. Một người dùng có thể đặt RDN bằng **uid**, đồng thời vẫn có **cn** trong thuộc tính của entry:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org
~~~

Ngược lại, một số directory lại chọn cách đặt DN người dùng bằng **cn=An Tran,ou=people,...**, trong khi **uid=an** chỉ nằm ở thuộc tính. Đó có thể là một mô hình hợp lệ nếu schema, quy tắc đặt tên và chính sách định danh phù hợp.

### 2.4. uid: mã định danh người dùng

**uid** thường dùng cho mã người dùng: **an**, **an.tran**, **user-1042**. Trên entry **inetOrgPerson**, nó là một thuộc tính phù hợp để lưu ID đăng nhập theo quy ước ứng dụng.

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

Tuy nhiên:

- **uid không nhất thiết là khóa đăng nhập thực tế** của mọi sản phẩm LDAP.
- **uid không tự được bảo đảm duy nhất trên toàn directory** trừ khi thiết kế, quy tắc đặt tên hoặc cấu hình kiểm soát tính duy nhất có quy định.
- **uid không phải lúc nào cũng xuất hiện trong DN**; DN có thể dùng **cn** hoặc một attribute type khác.
- **uid không đồng nghĩa với RDN, DN, LDAP bind DN, UUID** hay khóa chính của cơ sở dữ liệu quan hệ.

Trong Active Directory, ứng dụng thường gặp thêm **sAMAccountName**, **userPrincipalName**, **objectGUID**. Các thuộc tính này có mục đích và quy tắc khác **uid**, vì vậy không thể giả định cách đặt tên của OpenLDAP dùng **uid** cũng áp dụng y nguyên cho mọi Active Directory deployment.

## 3. Không nhầm tên thuộc tính với loại entry (objectClass)

**objectClass** mô tả entry được phép có loại dữ liệu nào theo schema. Các attribute types như **dc**, **ou**, **cn**, **uid** là những trường dữ liệu mà objectClass cho phép hoặc yêu cầu.

| Object class | Loại đối tượng điển hình | Ví dụ thuộc tính bắt buộc |
| --- | --- | --- |
| **domain** | Entry đại diện cho domain component | **dc** |
| **organizationalUnit** | Đơn vị tổ chức | **ou** |
| **person** | Người | **cn**, **sn** |
| **organizationalPerson** | Mở rộng person trong tổ chức | Kế thừa yêu cầu từ **person** |
| **inetOrgPerson** | Hồ sơ người dùng dạng Internet | Kế thừa **cn**, **sn**; có thể dùng **uid**, **mail** theo schema |
| **groupOfNames** | Nhóm chứa các DN thành viên | **cn**, **member** |

Các object class trên thuộc **STRUCTURAL** (trừ lớp nền **top**, thuộc ABSTRACT), và không thể thay thế tùy ý cho nhau. Ví dụ, một entry groupOfNames **không trở thành người dùng** chỉ vì có một thuộc tính hoặc RDN kiểu **uid**.

**RDN không quyết định objectClass.** Để xác định liệu một entry là người, nhóm hay đơn vị tổ chức, hãy đọc **objectClass** và schema. Tên RDN chỉ mô tả cách entry được định danh trong cây.

Ví dụ:

~~~text
dn: uid=an,ou=people,dc=example,dc=org
RDN: uid=an
objectClass: inetOrgPerson
cn: An Tran
sn: Tran
~~~

Nếu bỏ **cn** hoặc **sn** khỏi entry này khi tạo mới, server có thể từ chối vì schema **person/inetOrgPerson** yêu cầu chúng, dù **uid=an** trong DN hoàn toàn hợp lệ về mặt cú pháp.

## 4. DN, RDN, base DN và DN tương đối

Một trong những nguồn lỗi phổ biến với Spring LDAP là nhầm phần DN của entry với **base DN** đã cấu hình cho ContextSource.

Giả sử ứng dụng kết nối LDAP với:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-app,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Khi đó:

| Khái niệm | Ví dụ |
| --- | --- |
| LDAP base DN của ContextSource | **dc=example,dc=org** |
| DN đầy đủ của An | **uid=an,ou=people,dc=example,dc=org** |
| DN tương đối so với base | **uid=an,ou=people** |
| DN nhánh cần tìm | **ou=people** |
| RDN của entry An | **uid=an** |
| Bind DN của tài khoản dịch vụ | **uid=svc-app,ou=service-accounts,dc=example,dc=org** |

**Bind DN** dùng để xác thực tài khoản ứng dụng; **base DN** xác định phạm vi tên mà ContextSource thường dùng khi thực hiện các lệnh LDAP. Hai cấu hình này không cùng vai trò và không bắt buộc có cùng nhánh cha.

Ví dụ, gọi **LdapTemplate.lookup** với DN tương đối:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "an")
    .build();
// relativeDn: uid=an,ou=people
~~~

LdapTemplate áp dụng ContextSource có base đã cấu hình để truy cập entry tương ứng với DN đầy đủ. Nếu đưa cả **dc=example,dc=org** vào DN tương đối rồi vẫn dùng cùng base, bạn có nguy cơ **ghép base hai lần**.

Ngược lại, giá trị DN tham chiếu trong các thuộc tính kiểu **member** của nhóm thường là **DN đầy đủ**:

~~~ldif
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: reviewers
member: uid=an,ou=people,dc=example,dc=org
~~~

Tức là **DN của entry đang thao tác** với LdapTemplate và **giá trị thuộc tính có kiểu DN** có ngữ nghĩa khác nhau. Không tự cắt phần base khỏi **member** chỉ vì ContextSource đã đặt base.

### 4.1. RDN chỉ cần duy nhất trong phạm vi cha

Có thể đồng thời tồn tại hai entry với cùng **uid=an** ở hai nhánh:

~~~text
uid=an,ou=employees,dc=example,dc=org
uid=an,ou=contractors,dc=example,dc=org
~~~

Đây là **hai DN khác nhau**. Nếu nghiệp vụ muốn **uid** duy nhất toàn tổ chức, phải thiết kế thêm cơ chế đảm bảo: quy tắc cấp phát ID, tính duy nhất trong ứng dụng, overlay/constraint của directory nếu hỗ trợ và kiểm thử cạnh tranh khi ghi.

Một DN cũng có thể thay đổi khi di chuyển entry sang nhánh khác hoặc đổi RDN. Thay đổi **uid**, **cn** hay thuộc tính được chọn làm RDN không đơn giản tương đương cập nhật một field Java; thường phải cân nhắc thao tác **rename/modDN**, quy tắc naming và những DN tham chiếu từ các nhóm/dịch vụ khác.

## 5. Cách chọn tên RDN khi thiết kế thư mục

Không có một lựa chọn đúng cho mọi hệ thống. Cần đặt câu hỏi: **entry này thuộc loại gì, ai quản lý tên của nó, tên có ổn định không, có cần dùng như khóa nghiệp vụ không, dữ liệu có di chuyển giữa các nhánh không?**

### 5.1. Người dùng: dùng cn hay uid?

Hai phương án có thể hợp lệ với entry người dùng:

~~~text
# Phương án A: RDN dựa trên mã người dùng
uid=an,ou=people,dc=example,dc=org

# Phương án B: RDN dựa trên tên hiển thị
cn=An Tran,ou=people,dc=example,dc=org
~~~

**Dùng uid làm RDN** thường thuận tiện khi uid ít thay đổi và có chính sách cấp phát rõ ràng. **Dùng cn làm RDN** có thể phù hợp khi directory chọn hiển thị tên người trong cây, nhưng tên có khả năng thay đổi, trùng nhau hoặc chứa ký tự cần escape. **Cả hai cách đều cần quản lý uniqueness của RDN trong cùng parent**.

| Tiêu chí | uid làm RDN | cn làm RDN |
| --- | --- | --- |
| Thường dùng | Mã định danh người dùng | Tên chung/hiển thị |
| Dễ bị ảnh hưởng khi đổi họ tên | Ít hơn nếu uid ổn định | Có thể phải đổi DN nếu cn trong RDN đổi |
| Nguy cơ trùng | Phụ thuộc chính sách uid | Tên người có thể trùng nhiều hơn |
| Bắt buộc theo LDAP? | Không | Không |
| Thuộc tính cn/sn trên inetOrgPerson có còn bắt buộc? | Có | Có |

Không chọn **uid** chỉ vì thấy từ **user** trong tên nó. Một hệ thống có thể sử dụng UUID/ID ổn định khác để đồng bộ danh tính, tùy schema và loại directory. Không cho phép người dùng cuối tự chọn bất kỳ RDN hoặc parent DN nào mà không có giới hạn nghiệp vụ.

### 5.2. Đơn vị và nhóm: không đồng nhất ou với “thư mục”

Một nhánh **ou=groups** có thể chứa nhóm **cn=reviewers**; một nhánh **ou=people** có thể chứa người dùng **uid=an**. Đây là quy ước hợp lý, nhưng **ou** không phải từ khóa “tạo thư mục” giống đường dẫn filesystem.

Một entry được phân loại là đơn vị tổ chức có schema và thuộc tính **organizationalUnit**, còn một entry nhóm **groupOfNames** có schema **cn/member**. Cây LDAP là cấu trúc **entry có schema**, không phải tập các folder tùy ý.

Người dùng cũng có thể nằm trực tiếp dưới một suffix hoặc một nhánh có RDN khác, miễn server cho phép và cấu trúc đáp ứng nghiệp vụ.

### 5.3. Tên trong DN phải phù hợp với quy tắc server

LDAP syntax cho phép các loại RDN khác nhau, nhưng directory thực tế còn có thể áp dụng:

- **Schema**: thuộc tính trong entry phải hợp lệ theo objectClass.
- **Name form / DIT structure rules** nếu directory triển khai.
- **ACL**: tài khoản phải có quyền tạo/move/rename dưới parent.
- **Quy tắc uniqueness** và quy trình cấp ID của tổ chức.
- **Quy tắc sản phẩm**: Active Directory, OpenLDAP và các LDAP server khác không nhất thiết chấp nhận cùng cấu trúc dữ liệu/định danh.

Đây là lý do không thể suy ra cú pháp và tính hợp lệ chỉ từ việc DN “trông giống” **uid=...** hay **cn=...**.

## 6. Định dạng DN và escaping: đừng ghép chuỗi thủ công

LDAP DN theo RFC 4514 có cú pháp riêng. Một giá trị có dấu phẩy, dấu cộng, dấu bằng, dấu gạch chéo ngược, dấu # ở đầu hoặc khoảng trắng ở vị trí đặc biệt cần xử lý đúng.

Ví dụ họ tên có dấu phẩy:

~~~text
cn=Tran\, An,ou=people,dc=example,dc=org
~~~

Trong DN, dấu phẩy **sau ký tự escape** thuộc về giá trị **cn**; các dấu phẩy còn lại phân tách các RDN. Nếu code viết:

~~~java
String dn = "cn=" + nameFromRequest + ",ou=people,dc=example,dc=org";
~~~

thì giá trị **nameFromRequest** có thể làm thay đổi cấu trúc DN, làm kết nối sai entry hoặc trở thành một đường LDAP injection.

Trong Spring LDAP, ưu tiên API cấu trúc:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String nameFromRequest = "Tran, An";

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("cn", nameFromRequest)
        .build();
// Được tạo bằng RDN và có escaping theo cú pháp DN.
~~~

Giữ riêng hai khái niệm:

1. **DN escaping** dùng khi xây DN/RDN.
2. **LDAP filter escaping** dùng khi đặt giá trị trong điều kiện tìm kiếm.

Hai cú pháp **khác nhau**. Nếu đang tìm theo cn, hãy để **LdapQueryBuilder** xử lý escaping giá trị bộ lọc, thay vì escape bằng quy tắc DN rồi đưa vào filter.

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// cn là attribute type được ứng dụng chọn cố định.
// Giá trị có thể chứa ký tự đặc biệt nhưng được query builder xử lý.
ldapTemplate.search(
        query().base("ou=people").where("cn").is(nameFromRequest),
        (org.springframework.ldap.core.AttributesMapper<String>)
                attrs -> (String) attrs.get("cn").get()
);
~~~

**Không nhận trực tiếp tên attribute/filter operator từ request**. Giá trị được escape không làm một attribute type lạ trở nên an toàn hoặc có quyền sử dụng. Ứng dụng nên dùng danh sách thuộc tính được phép truy vấn như **uid**, **cn**, **mail**, và giới hạn search base/scope theo nhu cầu.

## 7. Làm việc với dc, ou, cn, uid bằng Spring LDAP

### 7.1. Dữ liệu mẫu

Giả sử các entry dưới đây tồn tại trên một LDAP server có schema chuẩn tương ứng:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org

dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: reviewers
member: uid=an,ou=people,dc=example,dc=org
~~~

LDIF trình bày thứ tự cha trước con để dễ hiểu. Trên server thực tế, suffix **dc=example,dc=org** có thể đã được tạo hoặc quản lý qua cơ chế bootstrap; không import trùng những entry đã tồn tại.

### 7.2. Service đọc và tìm người dùng

Sử dụng Spring Boot với **spring-boot-starter-data-ldap** hoặc cấu hình Spring LDAP tương đương. Dưới đây là service dùng Java 17+ và LdapTemplate:

~~~java
package org.example.directory;

import java.util.List;
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record PersonView(String uid, String commonName, String mail) {}

@Service
public class PersonDirectoryReader {
    private static final String PEOPLE_BASE = "ou=people";

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Khi đã biết RDN uid, tạo DN tương đối an toàn.
    public PersonView lookupByUid(String uid) {
        validateUid(uid);
        Name relativeDn = LdapNameBuilder.newInstance(PEOPLE_BASE)
                .add("uid", uid).build();
        return ldapTemplate.lookup(relativeDn, PERSON_MAPPER);
    }

    // Khi chưa biết DN, tìm theo giá trị thuộc tính.
    public List<PersonView> searchByUid(String uid) {
        validateUid(uid);
        return ldapTemplate.search(
                query().base(PEOPLE_BASE)
                        .where("objectClass").is("inetOrgPerson")
                        .and("uid").is(uid),
                PERSON_MAPPER);
    }

    // Tên chung cn không bắt buộc duy nhất: trả List.
    public List<PersonView> searchByCommonName(String cn) {
        if (cn == null || cn.isBlank() || cn.length() > 256) {
            throw new IllegalArgumentException("cn không hợp lệ");
        }
        return ldapTemplate.search(
                query().base(PEOPLE_BASE)
                        .where("objectClass").is("inetOrgPerson")
                        .and("cn").is(cn),
                PERSON_MAPPER);
    }

    private static final AttributesMapper<PersonView> PERSON_MAPPER =
            attrs -> new PersonView(
                    required(attrs, "uid"),
                    required(attrs, "cn"),
                    optional(attrs, "mail"));

    private static String required(Attributes attrs, String name)
            throws NamingException {
        String value = optional(attrs, name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu thuộc tính: " + name);
        }
        return value;
    }

    private static String optional(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        Object raw = attribute.get();
        if (!(raw instanceof String value)) {
            throw new IllegalArgumentException("Sai kiểu: " + name);
        }
        return value;
    }

    private static void validateUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
    }
}
~~~

Các điểm cần nhận ra:

- **lookupByUid** giả định mô hình đặt RDN người dùng bằng **uid** trong **ou=people**. Nếu directory thực tế dùng **cn** làm RDN, lookup theo UID xây sẵn như vậy sẽ không truy cập đúng entry; hãy **search theo uid để lấy DN thật**.
- **searchByUid** tìm thuộc tính **uid** trong entry theo filter; không yêu cầu RDN phải dùng uid.
- **searchByCommonName** trả **List**, vì **cn** không phải khóa duy nhất.
- **LdapQueryBuilder** xử lý escaping giá trị filter và **LdapNameBuilder** xử lý cú pháp DN.
- **AttributesMapper** chỉ ánh xạ những thuộc tính được dùng trong model Java. Không suy kiểu entry từ tiền tố DN.

**Ghi chú kỹ thuật:** đoạn code giả định thuộc tính đang đọc có một giá trị chuỗi. LDAP attribute có thể đa giá trị hoặc kiểu nhị phân; trong ứng dụng thật nên kiểm tra số lượng/kiểu giá trị và giới hạn dữ liệu phù hợp với schema.

### 7.3. Tạo entry cần objectClass và thuộc tính hợp lệ

Khi muốn tạo entry **inetOrgPerson** bằng LdapTemplate, ngoài RDN **uid** cần đưa vào objectClass và các thuộc tính bắt buộc **cn**, **sn**:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "binh";
Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid).build();

Attributes attrs = new BasicAttributes(true);
BasicAttribute classes = new BasicAttribute("objectClass");
classes.add("top");
classes.add("person");
classes.add("organizationalPerson");
classes.add("inetOrgPerson");
attrs.put(classes);
attrs.put("uid", uid);
attrs.put("cn", "Binh Le");
attrs.put("sn", "Le");
attrs.put("mail", "binh@example.org");

ldapTemplate.bind(relativeDn, null, attrs);
~~~

Đoạn code này nằm trong service đã có biến **ldapTemplate**, và giả định nhánh **ou=people** đã tồn tại. Thao tác **bind** ở đây tạo entry; nó không tự động tạo các parent còn thiếu. Server vẫn kiểm tra schema, ACL, cú pháp các giá trị và tính hợp lệ của DN.

Nếu **uid=binh,ou=people** đã có, tạo lại cùng DN thường bị từ chối. Đừng dùng kết quả **search** làm bảo đảm tuyệt đối rằng thao tác tạo sẽ không trùng trong trường hợp đồng thời; hãy xử lý lỗi từ chính thao tác ghi.

### 7.4. Spring Data LDAP repository và annotation

Khi muốn dùng mô hình repository, có thể ánh xạ một entry với class Java cố định:

~~~java
package org.example.directory;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
        base = "ou=people",
        objectClasses = {
            "top", "person", "organizationalPerson", "inetOrgPerson"
        })
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}
    // Bổ sung getters/setters hoặc cách truy cập trường phù hợp.
}
~~~

~~~java
package org.example.directory;

import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
}
~~~

**@Entry** chỉ định object class dùng cho ánh xạ; **@Id** giữ DN; **@Attribute** kết nối trường Java với thuộc tính LDAP. Spring Data LDAP **không tạo ra dc/ou/cn/uid như các từ khóa của Java** và không tự định nghĩa schema trên directory. Nếu class Java có tên **PersonEntry** nhưng LDAP entry thiếu **sn**, server vẫn có thể từ chối thao tác lưu.

Với một directory đang đặt RDN người dùng bằng **cn** thay cho **uid**, cần thiết kế cách xác định DN tương ứng trong **@Id**, mapper hoặc quy trình đọc. Không dùng code lookup theo uid-RDN của ví dụ trên mà giả định mọi repository sẽ tự sửa DN.

## 8. Tìm kiếm: tên attribute không phải một đường dẫn cố định

LDAP filter có thể tham chiếu trực tiếp các thuộc tính mà server/schema hỗ trợ:

~~~ldap
(uid=an)
(cn=An Tran)
(&(objectClass=inetOrgPerson)(mail=an@example.org))
~~~

Từng biểu thức đặt điều kiện trên **giá trị thuộc tính**, không bắt buộc thuộc tính phải là một thành phần trong DN.

Ví dụ, người dùng sau:

~~~text
DN: cn=An Tran,ou=employees,dc=example,dc=org
uid: an
cn: An Tran
sn: Tran
~~~

có thể vẫn khớp **(uid=an)** dù DN bắt đầu bằng **cn=...**, miễn entry có thuộc tính **uid** và truy vấn bao phủ entry đó.

**Search base** quyết định cây con được tìm. Nếu chỉ tìm dưới **ou=people**, một người dùng ở **ou=employees** không nằm trong phạm vi tìm. Điều này không phụ thuộc chuyện filter dùng **cn** hay **uid**.

Các lựa chọn **object**, **one-level** và **subtree** cũng ảnh hưởng phạm vi kết quả; số kết quả tối đa, timeout, phân trang và ACL phụ thuộc server/cấu hình. Đừng suy rằng một truy vấn theo **uid** mặc nhiên trả đúng một entry trên toàn tổ chức.

### 8.1. Giá trị và tên thuộc tính có những quy tắc khác nhau

Giá trị như **an** hoặc **An Tran** có thể đến từ người dùng, nhưng tên thuộc tính như **uid**, **cn**, **mail** nên được chọn từ code/cấu hình tin cậy. Truy vấn an toàn phải:

1. Cố định hoặc allowlist attribute types được phép.
2. Escape giá trị filter qua builder.
3. Cố định/giới hạn search base và scope.
4. Giới hạn dữ liệu được trả về, thực thi kiểm tra quyền và xử lý dữ liệu đa giá trị.

Không xây filter bằng chuỗi kiểu **"(cn=" + requestValue + ")"**, cũng không cho request tùy ý chọn **attributeType**, **baseDn** và **searchScope** có khả năng đọc mọi nhánh.

## 9. Đặc điểm của từng loại LDAP directory

**dc**, **ou**, **cn**, **uid** là những tên phổ biến trong schema LDAP, nhưng quy tắc cụ thể phụ thuộc directory:

| Khía cạnh | Điểm cần kiểm tra |
| --- | --- |
| **Suffix / base DN** | Server dùng **dc=...**, **o=...** hay naming context khác? |
| **Tên RDN của người dùng** | **uid**, **cn** hay thuộc tính khác? |
| **objectClass thực tế** | **inetOrgPerson**, loại riêng của nhà cung cấp, hoặc class mở rộng? |
| **Thuộc tính định danh đăng nhập** | **uid**, **userPrincipalName**, **sAMAccountName** hoặc một quy tắc riêng? |
| **Tính duy nhất** | Chỉ duy nhất DN dưới một parent hay có constraint cho thuộc tính? |
| **Tổ chức OU** | Có nhánh **ou=people**, **ou=groups** hay cấu trúc nhiều tầng? |
| **Schema và ACL** | Attribute type nào tồn tại, MUST/MAY ra sao, tài khoản có thể đọc/ghi ở đâu? |

Ví dụ **Active Directory** thường sử dụng các thuộc tính và object class riêng. Thực hành với OpenLDAP hoặc LDAP server nhúng không có nghĩa mọi câu lệnh tạo entry sẽ chạy y nguyên trên AD DS. Mẫu DN và base phải lấy từ cấu hình directory thật, không suy luận theo tên thư mục của dự án Java.

## 10. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **No such object (32)** khi lookup | Xây sai DN hoặc ghép base hai lần; parent không tồn tại | Kiểm tra DN đầy đủ, base DN và naming context |
| Search theo **uid** không ra kết quả | uid là thuộc tính có nhưng search base không bao phủ, hoặc không có giá trị đó | Mở rộng đúng subtree, kiểm tra thuộc tính entry và filter |
| Search theo **cn** ra nhiều kết quả | cn không phải khóa duy nhất | Trả danh sách, dùng DN/ID ổn định để phân biệt |
| **Object class violation (65)** khi thêm person | Thiếu **cn/sn**, hoặc tổ hợp class/thuộc tính sai schema | Tra **MUST/MAY** của objectClass |
| **Undefined attribute type (17)** | Ứng dụng dùng tên thuộc tính không có trên schema server | Kiểm tra attributeTypes/schema thực tế |
| **Invalid DN syntax (34)** | Giá trị chứa ký tự đặc biệt nhưng DN ghép chuỗi sai | Dùng LdapNameBuilder/JNDI Rdn |
| **Entry already exists (68)** | Trùng DN dưới cùng parent | Xử lý xung đột khi ghi; không chỉ dựa vào search trước đó |
| **Insufficient access rights (50)** | Bind account không đủ quyền | Kiểm tra ACL của nhánh và thuộc tính |
| Người dùng đổi họ tên làm hỏng tham chiếu | RDN chứa cn, DN đã được rename nhưng dữ liệu tham chiếu không cập nhật | Định nghĩa quy trình rename và đồng bộ membership |
| Kết quả khác nhau giữa hai LDAP server | Schema, ACL, naming context, replication hoặc chính sách sản phẩm khác nhau | Kiểm tra từng server và giảm giả định trong mã |

Cùng một dữ liệu có nhiều vấn đề, server có thể báo lỗi ở bước kiểm tra đầu tiên. Vì vậy đọc kết quả LDAP cùng DN, base, objectClass và attributes đã gửi (không ghi mật khẩu/thuộc tính nhạy cảm vào log) sẽ giúp chẩn đoán tốt hơn việc chỉ nhìn tên exception Spring.

## 11. Thực hành kiểm thử với directory

Chuẩn bị directory thử nghiệm có suffix **dc=example,dc=org**, nhánh **ou=people**, **ou=groups** và một tài khoản thử nghiệm có quyền đọc/ghi. Tạo dữ liệu seed theo LDIF ở phần 7 bằng công cụ phù hợp; không chạy các ca tạo/xóa trên directory sản xuất.

### 11.1. Quan sát DN và attribute types

Ví dụ dùng LDAP client:

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-app,ou=service-accounts,dc=example,dc=org" -W \
  -b "dc=example,dc=org" -s sub \
  "(objectClass=inetOrgPerson)" dn objectClass uid cn sn mail
~~~

Ở đây:

- **-b** là search base, **không phải giá trị uid**.
- **objectClass** xác định loại entry được tìm.
- **uid/cn/sn/mail** là những thuộc tính yêu cầu server trả về.
- **dn** cho biết đường đi đầy đủ tới entry, giúp quan sát RDN thực sự dùng **uid** hay **cn**.

Client phải kiểm tra chứng chỉ server/hostname theo cấu hình TLS; **-W** yêu cầu nhập password tương tác. Đừng đặt mật khẩu thật trên dòng lệnh hay bỏ qua chứng chỉ chỉ để test chạy.

### 11.2. Ma trận kiểm thử

| Ca | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| **Đọc người theo DN** | Lookup **uid=an,ou=people** | Thành công nếu entry đặt RDN theo uid và base đúng |
| **Tìm bằng thuộc tính** | Search **(uid=an)** dưới **ou=people** | Trả entry có uid tương ứng, không phụ thuộc tên RDN |
| **Đổi cách đặt RDN** | Tạo entry test có RDN **cn=...** và thuộc tính **uid** (nếu server cho phép) | Search uid vẫn tìm được; lookup dựng sẵn uid-RDN có thể không tìm được |
| **Hai uid ở hai nhánh** | Tạo cùng uid ở hai parent khác nhau | Hai DN khác nhau; search rộng có thể trả hai entry |
| **Thiếu MUST** | Tạo inetOrgPerson không có sn | Directory từ chối |
| **Tên có dấu phẩy** | Tạo DN bằng LdapNameBuilder | DN đúng cú pháp, không chia nhầm RDN |
| **Sai base DN** | Truy vấn ngoài subtree được cấu hình | Không tìm ra hoặc báo noSuchObject tùy thao tác |
| **Nhóm tham chiếu người dùng** | Tạo groupOfNames với member là DN đầy đủ | Thuộc tính member chứa đúng DN, không bị cắt base |
| **UID/cn không hợp lệ theo nghiệp vụ** | Gửi dữ liệu quá dài hoặc sai định dạng | Validation từ chối trước khi ghi |
| **Thiếu quyền ghi** | Tạo entry bằng bind account read-only | LDAP từ chối ghi |
| **Ký tự filter đặc biệt** | Search với input có dấu sao, ngoặc | Builder escape giá trị, không biến thành filter mở rộng ngoài ý muốn |

Trong JUnit, nên dùng test integration với directory thật hoặc LDAP nhúng có schema phù hợp, seed/cleanup dữ liệu độc lập và assertions so sánh **DN đầy đủ**, **RDN**, **objectClass**, **uid/cn/sn**. Mock LdapTemplate không xác nhận được server thực sự chấp nhận schema, DN hoặc ACL.

## 12. Những hiểu nhầm thường gặp

**“dc, ou, cn, uid là những thư mục/từ khóa cố định của LDAP.”** Không. Chúng là **attribute types** thuộc LDAP schema; cách dùng làm RDN hay cách tổ chức cây là quy ước cần phù hợp với server và ứng dụng.

**“Entry có ou trong DN thì chắc chắn là organizationalUnit.”** Không. DN có thể chứa RDN **ou** của một entry cha; loại của entry con phải xem objectClass của chính entry con.

**“Mọi người dùng đều có DN bắt đầu bằng uid.”** Không. Người dùng có thể dùng **cn** hoặc tên phù hợp khác làm RDN. Thuộc tính **uid** có thể nằm trong entry mà không nằm trong DN.

**“cn chỉ dành cho người dùng.”** Không. **cn** cũng được dùng cho nhóm và nhiều loại entry khác.

**“uid là ID duy nhất trong mọi hệ thống LDAP.”** Không. DN định danh entry theo cây; mức duy nhất của **uid** phụ thuộc chính sách/schema và cơ chế kiểm soát của directory.

**“Đặt base DN trong Spring LDAP nghĩa là mọi giá trị member phải viết tương đối.”** Không. Tham chiếu thuộc tính kiểu DN thường chứa **DN đầy đủ**; base DN chủ yếu liên quan đến cách các thao tác tìm/lookup địa chỉ hóa entry.

**“Một entry có RDN hợp lệ thì dữ liệu bên trong sẽ hợp lệ.”** Không. LDAP server còn kiểm tra **objectClass**, các thuộc tính MUST/MAY, cú pháp, ACL và naming constraints.

## 13. Tổng kết và bài tập tự luyện

**dc**, **ou**, **cn** và **uid** đều là những **tên thuộc tính được định nghĩa trong LDAP schema**. Người quản trị directory thường chọn chúng để đặt tên cho entry qua RDN, nhưng LDAP không áp đặt một cây duy nhất như **uid → ou → dc** và không gán vai trò “folder” cố định cho từng tên. Để hiểu một entry, hãy kết hợp **DN/RDN**, **objectClass**, **thuộc tính thực tế**, **schema**, **base DN**, **ACL** và cấu hình của server.

Trong **Spring Data LDAP**, lựa chọn **DN an toàn**, tìm kiếm **theo thuộc tính thay vì đoán RDN** và ánh xạ entity theo schema giúp ứng dụng linh hoạt giữa các directory. Khi làm CRUD, tạo DN qua **LdapNameBuilder**, tạo filter qua **LdapQueryBuilder**, kết nối TLS được xác minh và kiểm thử hành vi trên directory mục tiêu.

**Bài tập:**

1. Trong DN **uid=an,ou=people,dc=example,dc=org**, đâu là RDN, parent DN và base DN nếu Spring LDAP cấu hình **base=dc=example,dc=org**?
2. Vì sao **(uid=an)** vẫn có thể tìm thấy entry có DN bắt đầu bằng **cn=An Tran**? Nêu điều kiện về search base và thuộc tính.
3. Thiết kế hai cây: một cây có người dùng dưới **ou=people**, một cây dưới **ou=employees** và đặt RDN bằng **cn**. So sánh phương thức lookupByUid với searchByUid.
4. Một tổ chức có hai người trùng **cn**. Hãy trình bày vì sao dùng **cn** để tìm kiếm phải kiểm tra nhiều kết quả, và khi nào dùng uid cũng có thể trùng.
5. Tạo một entry **inetOrgPerson** với RDN **uid** nhưng cố ý bỏ **sn**. Giải thích vì sao lỗi schema không bắt nguồn từ **uid**.
6. Tại sao phải tạo DN đầy đủ khi ghi **member** của groupOfNames, dù LdapTemplate đang dùng base DN?
7. Chỉ ra cách xử lý một tên **Tran, An** khi dùng làm RDN **cn**, và giải thích sự khác biệt giữa escaping DN và filter.
8. Kiểm tra schema của directory thực tế để xác định **dc**, **ou**, **cn**, **uid** là các attribute types nào; xác minh objectClass và naming convention của người dùng trước khi viết repository.

### Tài liệu tham khảo

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512) — entry, naming, attribute types, objectClasses và schema.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514) — DN, RDN và escaping.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515) — cú pháp bộ lọc tìm kiếm và escaping.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519) — thuộc tính và lớp phổ biến như **cn**, **uid**, **organizationalUnit**, **person**.
- [RFC 2247 — Using Domains in LDAP/X.500 Distinguished Names](https://www.rfc-editor.org/rfc/rfc2247) — quy ước mô hình hóa các domain component bằng **dc**.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) và [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — DN builders, LdapTemplate, ODM và repository.
