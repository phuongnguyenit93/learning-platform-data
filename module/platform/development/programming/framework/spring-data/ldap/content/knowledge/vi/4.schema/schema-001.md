# Vai trò của schema trong dữ liệu thư mục

> **Chương:** Schema  
> **Phạm vi:** Spring Data LDAP — truy cập dịch vụ thư mục LDAP bằng repository và ánh xạ các entry phân cấp sang đối tượng Java.

Trong một cơ sở dữ liệu quan hệ, bảng và các ràng buộc giúp ứng dụng biết dữ liệu nào có thể lưu. Với LDAP, **schema** giữ vai trò tương tự ở mức mô tả loại entry, các thuộc tính được phép dùng và quy tắc đối với giá trị. Tuy nhiên, LDAP còn tổ chức entry thành **cây thông tin thư mục** (Directory Information Tree — DIT), nên phải hiểu riêng **vị trí của entry trong cây** và **cấu trúc hợp lệ của entry**.

Khi làm việc với Spring Data LDAP, hiểu schema là điều kiện để thiết kế mô hình Java đúng, thêm/sửa entry thành công, xây dựng truy vấn phù hợp và giải thích các lỗi mà directory server trả về.

## 1. Schema là gì và giải quyết vấn đề nào?

**Schema LDAP** là tập định nghĩa mà directory server sử dụng để hiểu và kiểm tra dữ liệu thư mục, bao gồm:

- **Attribute type:** tên/mã định danh thuộc tính (ví dụ `cn`, `sn`, `uid`, `mail`), kiểu giá trị, quy tắc so khớp và các đặc tính khác.
- **Object class:** loại entry, quan hệ kế thừa, thuộc tính bắt buộc (**MUST**) và thuộc tính được phép (**MAY**).
- **Syntax và matching rule:** dạng biểu diễn hợp lệ của giá trị và cách server so sánh giá trị khi thực hiện các phép lọc/tìm kiếm.
- **Các định nghĩa schema bổ sung:** tùy directory server, có thể bao gồm các dạng name form, DIT content rule và những quy tắc khác.

Ví dụ, một entry biểu diễn nhân sự thuộc lớp `person` cần có `cn` (common name) và `sn` (surname). Nếu ứng dụng chỉ gửi `cn`, server có thể từ chối thao tác thêm entry vì vi phạm yêu cầu thuộc tính bắt buộc.

Schema mang lại ba lợi ích trực tiếp:

1. **Nhất quán dữ liệu:** entry của cùng một loại tuân theo hợp đồng thuộc tính được định nghĩa.
2. **Khả năng tương tác:** nhiều client LDAP có thể hiểu các thuộc tính và object class tiêu chuẩn theo cùng một ý nghĩa.
3. **Phát hiện sai sót sớm:** thao tác thêm hoặc sửa không phù hợp schema bị directory server kiểm tra và trả lỗi.

**Giới hạn cần nhớ:** schema không tự tạo chỉ mục tìm kiếm, không quyết định quyền truy cập, không mặc nhiên bảo đảm `uid` duy nhất toàn thư mục và không đảm bảo `mail` là một địa chỉ email đang tồn tại. Các việc đó có thể cần chính sách, tính năng hoặc cơ chế kiểm tra riêng của server/ứng dụng.

## 2. Phân biệt schema, DIT, DN và entry

Xét một cây thư mục đơn giản:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=lan
└── ou=groups
    └── cn=developers
~~~

Bản ghi người dùng có **DN** (Distinguished Name) đầy đủ là:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **DIT** | Các entry được sắp xếp ở đâu, theo quan hệ cha–con nào? | `ou=people` nằm dưới `dc=example,dc=org` |
| **DN** | Entry cụ thể được định danh bằng đường dẫn nào trong cây? | `uid=lan,ou=people,dc=example,dc=org` |
| **RDN** | Entry được đặt tên thế nào so với entry cha? | `uid=lan` |
| **Entry** | Bản ghi hiện có gồm những thuộc tính và giá trị nào? | `uid`, `cn`, `sn`, `mail`, `objectClass` |
| **Schema** | Những object class, thuộc tính và giá trị nào hợp lệ? | `inetOrgPerson` kế thừa các yêu cầu của `person` |

DN biểu thị **vị trí và tên**; schema biểu thị **hình dạng dữ liệu hợp lệ**. Một DN đúng cú pháp chưa chắc có entry tồn tại ở DN đó, và một entry có đủ thuộc tính theo schema cũng chưa chắc được phép nằm ở mọi vị trí nếu server áp dụng thêm quy tắc DIT.

Thuộc tính dùng trong RDN (chẳng hạn `uid`) cần được schema của entry cho phép và giá trị đặt tên phải nhất quán với entry. Thay đổi RDN/DN là thao tác đổi tên hoặc di chuyển entry, có ý nghĩa khác với việc cập nhật một trường thông thường.

## 3. Object class: hợp đồng của từng loại entry

Mỗi entry LDAP có thuộc tính đa giá trị `objectClass` để mô tả những lớp mà entry thuộc về. Các lớp có quan hệ kế thừa thông qua `SUP` (superior class).

Ba nhóm chính:

| Nhóm | Ý nghĩa | Ví dụ |
|---|---|---|
| **ABSTRACT** | Lớp cơ sở để các lớp khác kế thừa; không dùng độc lập làm lớp cấu trúc của entry | `top` |
| **STRUCTURAL** | Xác định loại cấu trúc chính của entry | `person`, `organizationalPerson`, `inetOrgPerson` |
| **AUXILIARY** | Bổ sung khả năng/thuộc tính cho một entry đã có lớp cấu trúc, nếu được phép | Các lớp phụ trợ do schema của server định nghĩa |

Một entry thông thường có **một chuỗi kế thừa structural object class**. Không thể tùy ý ghép hai structural class không có quan hệ kế thừa chỉ để lấy thêm các thuộc tính của cả hai.

Ví dụ quan hệ kế thừa phổ biến:

~~~text
top                           (ABSTRACT)
└── person                    (STRUCTURAL)
    └── organizationalPerson  (STRUCTURAL)
        └── inetOrgPerson     (STRUCTURAL)
~~~

Trong schema tiêu chuẩn, `person` yêu cầu ít nhất:

~~~text
objectClass: person
MUST: cn, sn
MAY: userPassword, telephoneNumber, seeAlso, description
~~~

`organizationalPerson` và `inetOrgPerson` kế thừa yêu cầu từ lớp cha, đồng thời cho phép thêm các thuộc tính phù hợp với thông tin tổ chức và người dùng Internet, chẳng hạn `uid` và `mail` trong `inetOrgPerson`.

**MUST** nghĩa là entry phải có giá trị hợp lệ cho thuộc tính đó; **MAY** nghĩa là được phép có nhưng không bắt buộc. Các thuộc tính được phép là kết quả tổng hợp từ các object class áp dụng, bao gồm lớp cha. Việc một thuộc tính được schema cho phép **không có nghĩa** người đang kết nối có quyền đọc hoặc sửa thuộc tính đó.

### Entry người dùng hợp lệ

Ví dụ LDIF (LDAP Data Interchange Format):

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
sn: Tran
mail: lan@example.org
~~~

Lý giải:

- **DN** đặt entry dưới nhánh `ou=people`, với RDN `uid=lan`.
- `objectClass` khai báo chuỗi lớp thích hợp cho một người dùng.
- `cn` và `sn` đáp ứng yêu cầu bắt buộc được kế thừa từ `person`.
- `uid` và `mail` phù hợp với mô hình người dùng `inetOrgPerson`.

Ví dụ giả định nhánh cha đã tồn tại và server đã nạp schema tương ứng. Định nghĩa object class cụ thể có thể khác giữa OpenLDAP, Active Directory và các directory server khác; luôn đối chiếu schema thực tế của server đang sử dụng.

### Entry nhóm có ràng buộc khác

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
~~~

`groupOfNames` thường yêu cầu `cn` và ít nhất một giá trị `member`. Vì vậy, một nhóm trống có thể không hợp lệ với lớp này. Nếu nghiệp vụ cho phép nhóm không thành viên, cần chọn mô hình object class phù hợp với schema/server thay vì tự bỏ qua thuộc tính bắt buộc.

Giá trị `member` có dạng DN, nhưng schema riêng của nó không mặc nhiên bảo đảm DN được tham chiếu luôn tồn tại. Tính toàn vẹn tham chiếu, nếu cần, phải được kiểm tra hoặc bật hỗ trợ thích hợp.

## 4. Attribute type, syntax và matching rule

Object class trả lời **“có thể dùng thuộc tính nào?”**; định nghĩa attribute type trả lời **“thuộc tính đó chứa dữ liệu gì và được so sánh như thế nào?”**.

Một attribute type có thể mô tả:

- **Tên và OID:** `cn` là tên dễ đọc; OID xác định định nghĩa một cách chuẩn hóa.
- **Syntax:** giá trị là chuỗi, số, DN, thời gian hay dạng dữ liệu khác theo cú pháp LDAP.
- **Equality/substring/ordering matching rule:** cách server thực hiện so khớp bằng, chuỗi con hoặc thứ tự khi loại thuộc tính đó hỗ trợ.
- **SINGLE-VALUE:** nếu được quy định, entry chỉ có tối đa một giá trị cho thuộc tính đó; nếu không, thuộc tính có thể đa giá trị tùy định nghĩa.

Ví dụ, `member` của `groupOfNames` chứa DN; `cn` thường là chuỗi tên hiển thị và có thể có nhiều giá trị. Cách so sánh chính xác phải dựa vào matching rule trong schema, chứ không nên suy từ kiểu Java `String`.

**Một vài hệ quả quan trọng:**

- Bộ lọc `(cn=tran thi lan)` có thể so khớp theo quy tắc không phân biệt hoa/thường nếu matching rule của thuộc tính và server hỗ trợ như vậy.
- Không phải mọi attribute type đều hỗ trợ mọi phép so sánh; phép tìm chuỗi con hay sắp thứ tự có thể không phù hợp với một số thuộc tính.
- Chỉ vì hai giá trị cùng được Java biểu diễn bằng `String` không có nghĩa LDAP so sánh chúng theo cùng một cách.
- Schema kiểm tra cú pháp theo định nghĩa LDAP; nó thường **không** thay thế xác thực nghiệp vụ. Chẳng hạn, `mail` được phép chứa chuỗi phù hợp syntax nhưng không đồng nghĩa email đã được xác minh.

## 5. Server kiểm tra schema ở giai đoạn nào?

Schema thường được directory server áp dụng khi xử lý thao tác **Add** hoặc **Modify** (và trong các tình huống liên quan đến đổi tên). Client gửi yêu cầu; server đối chiếu object class, thuộc tính và cú pháp trước khi chấp nhận thay đổi.

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Data LDAP"] --> B["Add / Modify entry"]
    B --> C["Directory server"]
    C --> D{"Hợp lệ theo schema và các quy tắc server?"}
    D -->|Có| E["Tiếp tục kiểm tra quyền và áp dụng thay đổi"]
    D -->|Không| F["Trả mã lỗi LDAP"]
~~~

**Tình huống 1 — thiếu thuộc tính MUST**

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
~~~

Entry thiếu `sn`, dù có `cn` và `uid`. Một server thực thi schema chặt chẽ thường từ chối tạo entry.

**Tình huống 2 — thuộc tính ngoài các object class**

Nếu entry chỉ có lớp `person` mà ứng dụng cố ghi `mail`, server có thể từ chối vì `mail` không được cho phép bởi tập object class áp dụng. Cần kiểm tra lớp phù hợp, chứ không tùy tiện thêm object class thiếu quan hệ hay tắt kiểm tra schema.

**Tình huống 3 — thuộc tính chưa được định nghĩa**

Nếu ứng dụng gửi `favoriteColor` nhưng server không có attribute type này, thao tác có thể gặp lỗi `undefinedAttributeType`. Định nghĩa một attribute type mới cần cấu hình schema của directory server, không thể giải quyết chỉ bằng cách thêm trường Java.

| Mã kết quả LDAP thường gặp | Ý nghĩa liên quan | Hướng kiểm tra |
|---|---|---|
| `objectClassViolation (65)` | Thiếu thuộc tính MUST hoặc dùng thuộc tính/lớp không phù hợp | Xem `objectClass`, kế thừa, MUST/MAY |
| `undefinedAttributeType (17)` | Attribute type không được server biết đến | Kiểm tra tên thuộc tính và schema server |
| `invalidAttributeSyntax (21)` | Giá trị không hợp lệ với syntax đã định nghĩa | Kiểm tra kiểu, biểu diễn và nội dung giá trị |
| `attributeOrValueExists (20)` | Thêm trùng thuộc tính/giá trị theo quy tắc server | Kiểm tra thao tác Modify và thuộc tính đa giá trị |
| `invalidDNSyntax (34)` | DN truyền vào sai cú pháp | Kiểm tra DN và cách escape thành phần RDN |

Mã lỗi là chỉ dẫn ban đầu; thông điệp cụ thể và cách kiểm tra phụ thuộc directory server. Lỗi từ chối thao tác cũng có thể đến từ quyền truy cập, chính sách mật khẩu, quy tắc tên hoặc ràng buộc khác mà schema không quản lý.

## 6. Liên hệ trực tiếp với Spring Data LDAP

Trong Java, một entity LDAP phản ánh entry của thư mục. **Annotation ánh xạ Java không phải nơi định nghĩa schema của server**. Khai báo entity đúng giúp client tạo và đọc thuộc tính nhất quán, nhưng server vẫn là bên quyết định entry có hợp lệ hay không.

Ví dụ entity ánh xạ người dùng:

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
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    // Constructor mặc định và getters/setters theo nhu cầu ứng dụng.
}
~~~

Ánh xạ với schema:

| Thành phần Java | Thành phần LDAP | Ý nghĩa |
|---|---|---|
| `@Entry(objectClasses = ...)` | `objectClass` | Khai báo tập lớp dùng khi ánh xạ/ghi entry |
| `@Entry(base = "ou=people")` | Nhánh cơ sở | Chọn vị trí cơ sở của entity trong DIT |
| `@Id Name dn` | Distinguished Name | Định danh entry trong cây |
| `@Attribute(name = "cn")` | `cn` | Trường Java ánh xạ tới common name |
| `@Attribute(name = "sn")` | `sn` | Trường Java ánh xạ tới surname bắt buộc |
| `@Attribute(name = "mail")` | `mail` | Thuộc tính cho phép trong lớp người dùng phù hợp |

Entity không khai báo `sn` hoặc để `sn` rỗng khi thêm entry có thể khiến `save(...)` thất bại vì schema. Cần xác thực dữ liệu đầu vào trước khi ghi, nhưng vẫn phải xử lý lỗi LDAP do server trả về. Nếu thay `objectClasses` sang lớp khác, phải kiểm tra lại toàn bộ thuộc tính mà entity đang sử dụng.

### Truy vấn repository theo thuộc tính trong schema

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);

    List<DirectoryPerson> findBySurname(String surname);
}
~~~

Ở đây, tên phương thức dẫn xuất được xây dựng theo **tên thuộc tính Java** (`uid` và `surname`); annotation `@Attribute(name = "sn")` ánh xạ trường `surname` sang thuộc tính LDAP `sn`. Repository phải được cấu hình cùng context/base DN phù hợp và server phải hỗ trợ các thuộc tính được truy vấn.

Khi cần tạo bộ lọc tường minh, `LdapTemplate` và `LdapQueryBuilder` cho phép biểu diễn điều kiện rõ ràng:

~~~java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class DirectoryPersonFinder {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonFinder(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findByUid(String uid) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.find(ldapQuery, DirectoryPerson.class);
    }
}
~~~

`uid` trong ví dụ là một thuộc tính mà schema cho phép. Hãy dùng API tạo filter của Spring LDAP để escape giá trị nhập vào; tránh tự nối chuỗi người dùng thành biểu thức LDAP như `"(uid=" + input + ")"` vì có thể tạo lỗi filter hoặc LDAP injection. Đồng thời, không giả định `uid` là duy nhất trên toàn cây nếu directory server chưa áp dụng ràng buộc riêng.

### Schema ảnh hưởng đến CRUD như thế nào?

| Thao tác | Cần hiểu từ schema | Cần hiểu thêm ngoài schema |
|---|---|---|
| **Create** | Object class, thuộc tính MUST/MAY, syntax | DN cha đã tồn tại, quyền tạo, RDN hợp lệ |
| **Read/Search** | Tên thuộc tính, matching rule, object class | Base DN, scope, ACL, giới hạn và chỉ mục tìm kiếm |
| **Update** | Thuộc tính được phép, số lượng giá trị, syntax | Quyền sửa và chính sách server |
| **Delete** | Bản thân schema thường ít quyết định thao tác xóa | Quyền xóa, entry con, quan hệ tham chiếu |
| **Rename/Move** | Thuộc tính đặt tên/RDN phù hợp với loại entry | DN đích, quyền đổi tên/di chuyển và quy tắc DIT |

**Ví dụ lỗi dễ nhầm:** `@Attribute(name = "mail")` trong Java không thể tự làm cho server chấp nhận `mail` nếu object class đang dùng không cho phép nó. Việc bổ sung annotation chỉ sửa ánh xạ ở client; hợp đồng dữ liệu vẫn nằm ở schema của server.

## 7. Cách xem schema đang thực sự được server áp dụng

Đừng suy đoán schema chỉ từ tên sản phẩm directory. Một server có thể cài thêm object class và attribute type tùy biến, hoặc áp dụng quy tắc riêng cho một nhánh.

Quy trình khảo sát cơ bản:

1. Kết nối tới đúng directory server bằng tài khoản có quyền đọc thông tin schema.
2. Đọc thuộc tính `subschemaSubentry` nếu server cung cấp để lấy DN của subschema entry.
3. Tại DN này, đọc `objectClasses` và `attributeTypes` để kiểm tra định nghĩa thực tế.
4. Tìm object class dùng trong bài toán, lần theo `SUP` để tổng hợp MUST/MAY được kế thừa.
5. Đối chiếu tên thuộc tính, syntax, matching rule với Java entity và các filter mà ứng dụng sử dụng.

Ví dụ lệnh khám phá sơ bộ (phụ thuộc quyền và cấu hình server):

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -s base -b "" subschemaSubentry
~~~

Sau khi lấy được DN subschema từ kết quả, thực hiện truy vấn base-scope trên DN đó để đọc `objectClasses` và `attributeTypes`. **Không** mặc định mọi directory đều có cùng DN schema, và tránh dùng LDAP không mã hóa trong môi trường thực tế khi truyền thông tin nhạy cảm.

Nếu đang dùng Active Directory, có thể gặp hệ thống class/attribute và cách tổ chức schema khác với các ví dụ chuẩn `inetOrgPerson`. Nếu sử dụng OpenLDAP hoặc directory nhúng trong test, các extension được nạp cũng ảnh hưởng đến khả năng chấp nhận entry.

## 8. Thiết kế và kiểm thử dựa trên schema

Một quy trình thực tế khi xây dựng tính năng “quản lý nhân viên” bằng Spring Data LDAP:

1. **Xác định loại entry:** chọn `inetOrgPerson` nếu phù hợp nghiệp vụ và được server hỗ trợ; không chọn lớp chỉ dựa vào tên gần giống đối tượng Java.
2. **Lập bảng dữ liệu:** tách `cn`/`sn` bắt buộc khỏi `mail`/`telephoneNumber` tùy chọn; kiểm tra thuộc tính nào đa giá trị.
3. **Chọn DN và base:** ví dụ `uid=<giá-trị>,ou=people,dc=example,dc=org`, kiểm tra quy tắc đặt tên và escape an toàn giá trị RDN bằng API xây dựng DN.
4. **Ánh xạ entity:** dùng `@Entry`, `@Id` và `@Attribute` theo đúng object class và attribute type đã xác minh.
5. **Kiểm tra dữ liệu trước khi ghi:** chặn trường hợp thiếu `sn`, giá trị không phù hợp syntax, hoặc thuộc tính vượt phạm vi object class.
6. **Kiểm thử với directory thật hoặc test directory có schema tương đương:** thực hiện Add, Modify, Search, Rename và kiểm tra mã lỗi thực tế của server.

Nên có các ca kiểm thử có ý nghĩa:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Thêm `inetOrgPerson` có đủ `cn`, `sn`, `uid` | Thành công nếu DN, quyền và các ràng buộc khác hợp lệ |
| Thiếu `sn` | Bị từ chối vì yêu cầu thuộc tính bắt buộc |
| Ghi một attribute type server chưa định nghĩa | Bị từ chối với lỗi liên quan thuộc tính không xác định |
| Truy vấn `uid` có ký tự đặc biệt trong đầu vào | Filter vẫn được escape và thực thi đúng |
| Đổi RDN chứa dấu phẩy, dấu bằng hoặc ký tự cần escape | DN được xây dựng hợp lệ, không tách nhầm thành phần |
| Đọc/sửa bằng tài khoản có quyền hạn chế | Hành vi tuân theo ACL, độc lập với việc thuộc tính có hợp lệ theo schema |

Một directory nhúng hoặc container LDAP rất hữu ích cho integration test, nhưng phải nạp schema phù hợp và không mặc nhiên coi hành vi của nó giống server production. Khi kiểm thử lỗi schema, hãy xác nhận server test đang **bật kiểm tra schema**.

## 9. Những nhầm lẫn thường gặp

- **“Có field Java là LDAP sẽ lưu được.”** Sai. Server phải biết attribute type đó và object class của entry phải cho phép nó.
- **“Có `uid` thì mỗi người dùng chắc chắn là duy nhất.”** Sai. RDN phải phân biệt trong cùng parent DN; tính duy nhất của `uid` trên nhiều nhánh là ràng buộc riêng.
- **“Schema cho phép `userPassword` nghĩa là mật khẩu được lưu an toàn.”** Sai. Bảo vệ credential phụ thuộc cách lưu/so khớp mật khẩu, chính sách và bảo mật vận chuyển.
- **“Thêm `@Entry` sẽ tạo object class trên server.”** Sai. Annotation mô tả cách ánh xạ entity; cài đặt hoặc thay đổi schema là công việc cấu hình directory.
- **“Thuộc tính hợp lệ thì mọi tài khoản đều đọc/ghi được.”** Sai. ACL và các chính sách truy cập được kiểm tra riêng.
- **“Có giá trị `member` thì entry thành viên chắc chắn tồn tại.”** Sai. Syntax DN không đồng nghĩa với bảo toàn tham chiếu.

## 10. Ghi nhớ và tài liệu tham chiếu

**Schema xác định cấu trúc entry hợp lệ; DIT và DN xác định vị trí entry; Spring Data LDAP ánh xạ dữ liệu và gửi thao tác; directory server kiểm tra và quyết định chấp nhận yêu cầu.**

Khi gặp lỗi Add/Modify, lần lượt xem `objectClass`, các trường MUST/MAY kế thừa, attribute syntax, DN/RDN, rồi quyền và chính sách server. Cách phân tích theo lớp này giúp tránh sửa nhầm Java mapping khi nguyên nhân thực sự nằm ở schema LDAP.

Các tiêu chuẩn nền tảng để tra cứu:

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): object class, attribute type, schema và mô hình DIT.
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): syntax và matching rule.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): ví dụ lớp `person`, `organizationalPerson`, `groupOfNames` và các thuộc tính phổ biến.
- [RFC 2798 — Definition of the inetOrgPerson LDAP Object Class](https://www.rfc-editor.org/rfc/rfc2798): lớp `inetOrgPerson`.
