# Directory service, entry, attribute và object class liên hệ với nhau

Trong Spring LDAP, ứng dụng thường tìm người dùng, nhóm hoặc đơn vị tổ chức thông qua một máy chủ LDAP. Để hiểu câu lệnh tìm kiếm hay thao tác thêm/sửa một đối tượng bằng `LdapTemplate`, `LdapClient` hoặc ODM, trước hết cần phân biệt bốn khái niệm: **directory service** là hệ thống cung cấp dữ liệu thư mục; **entry** là một đối tượng trong thư mục; **attribute** là những thông tin của đối tượng đó; và **object class** quy định entry được phép hoặc bắt buộc mang những attribute nào.

Bài học thuộc phần **Bức tranh tổng thể** của Spring LDAP, tập trung vào mô hình dữ liệu. Các ví dụ sử dụng cây thư mục giả định dưới miền `dc=example,dc=org` để nối khái niệm LDAP với cách đọc, tìm kiếm và ánh xạ entry trong ứng dụng Java.

## 1. Nhìn toàn cảnh: từ dịch vụ thư mục đến từng thuộc tính

**Directory service (dịch vụ thư mục)** lưu trữ và cung cấp thông tin về các đối tượng như tài khoản, nhóm, phòng ban, thiết bị hoặc dịch vụ. Nó thường phục vụ các tác vụ tra cứu, định danh và quản trị. LDAP (*Lightweight Directory Access Protocol*) là giao thức để client giao tiếp với dịch vụ thư mục: kết nối, xác thực (*bind*), tìm kiếm (*search*), đọc và thay đổi entry.

Dữ liệu thường được tổ chức thành một **Directory Information Tree (DIT)**: mỗi nút là một entry, các nút có quan hệ cha–con theo **Distinguished Name (DN)**. Ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=binh
└── ou=groups
    └── cn=developers
~~~

Trong cây này, đường dẫn đầy đủ của tài khoản An là `uid=an,ou=people,dc=example,dc=org`. Các đoạn `uid=an`, `ou=people`, `dc=example` và `dc=org` là những **Relative Distinguished Name (RDN)** ở từng cấp. DN phân biệt một entry với các entry khác trong cây; `uid=an` riêng lẻ chỉ xác định một tên tương đối trong phạm vi entry cha.

| Khái niệm | Câu hỏi mà khái niệm trả lời | Ví dụ |
|---|---|---|
| **Directory service** | Dữ liệu nằm ở đâu, client tra cứu và thay đổi qua giao thức nào? | Máy chủ LDAP phục vụ miền `dc=example,dc=org` |
| **Entry** | Đối tượng cụ thể nào đang được lưu trong cây? | Tài khoản `uid=an,ou=people,dc=example,dc=org` |
| **Attribute** | Đối tượng đó có những thông tin gì? | `cn`, `sn`, `uid`, `mail` |
| **Object class** | Entry phải có và có thể có những attribute nào theo schema? | `inetOrgPerson`, `organizationalUnit`, `groupOfNames` |

Quan hệ cốt lõi là: **directory service chứa một cây các entry; mỗi entry có DN và tập attribute; trong các attribute đó, `objectClass` khai báo các lớp schema chi phối cấu trúc của entry.**

## 2. Entry: một đối tượng có danh tính trong cây

Mỗi entry bao gồm:

- **DN**: tên phân biệt đầy đủ, xác định vị trí và tên entry trong DIT.
- **Các attribute**: tập cặp loại thuộc tính và một hoặc nhiều giá trị, chẳng hạn `cn: Nguyen Van An`.
- **`objectClass`**: attribute đặc biệt liệt kê một hoặc nhiều object class của entry, chịu sự ràng buộc của schema máy chủ.

Một cách trao đổi hoặc nạp dữ liệu LDAP phổ biến là **LDIF (LDAP Data Interchange Format)**. Ví dụ một entry người dùng:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
givenName: Van An
mail: an@example.org
~~~

Đọc ví dụ từ trên xuống: DN cho biết đây là entry có tên tương đối `uid=an` nằm dưới `ou=people`; các dòng `objectClass` cho biết entry đại diện một người theo schema; `uid`, `cn`, `sn`, `givenName` và `mail` mang dữ liệu thực tế.

> LDIF ở đây là dữ liệu minh họa, chưa phải lệnh tạo entry. Muốn nạp thành công, entry cha phải tồn tại, schema và chính sách đặt tên của máy chủ phải chấp nhận cấu trúc, đồng thời tài khoản thao tác cần đủ quyền.

**DN không đồng nghĩa với một attribute duy nhất.** DN là chuỗi các RDN từ entry đến gốc liên quan; attribute `uid` trong ví dụ chứa giá trị `an` dùng làm RDN ở cấp người dùng. Hai người có cùng `cn` vẫn có thể là hai entry khác nhau nếu DN khác nhau. Ngược lại, các entry cùng cha không thể có cùng DN.

Khi đổi tên hoặc chuyển một entry sang nhánh khác, DN của entry thay đổi và DN của các entry con có thể bị ảnh hưởng. Do đó ứng dụng không nên xem DN là khóa bất biến, cũng không nên mặc định `cn` hay `mail` luôn duy nhất.

## 3. Attribute: loại thuộc tính, giá trị và quy tắc

**Attribute type** định nghĩa tên và đặc điểm của thuộc tính, chẳng hạn `cn` (common name), `sn` (surname), `mail` (địa chỉ thư điện tử), `member` (DN của thành viên nhóm). **Attribute value** là một giá trị cụ thể gắn với loại thuộc tính đó.

~~~text
entry: uid=an,ou=people,dc=example,dc=org
  ├── uid         → "an"
  ├── cn          → "Nguyen Van An"
  ├── sn          → "Nguyen"
  ├── mail        → "an@example.org"
  └── objectClass → "top", "person",
                    "organizationalPerson", "inetOrgPerson"
~~~

Một attribute có thể có **nhiều giá trị** nếu định nghĩa schema cho phép. Ví dụ `member` trong một entry nhóm thường liệt kê nhiều DN; `objectClass` cũng thường có nhiều giá trị. Không nên thiết kế Java model với giả định mọi attribute đều chỉ có một chuỗi.

Schema có thể quy định kiểu cú pháp (*syntax*) và quy tắc so khớp (*matching rule*) của attribute. Vì vậy việc so sánh, chuẩn hóa chữ hoa/chữ thường, kiểm tra giá trị hay tìm kiếm phụ thuộc định nghĩa cụ thể trên máy chủ; không thể giả định mọi attribute được xử lý như chuỗi Java thông thường.

Ngoài các attribute dữ liệu thường được ứng dụng khai báo, một máy chủ có thể quản lý **operational attribute** như `createTimestamp`, `modifyTimestamp` hoặc định danh kỹ thuật riêng. Những attribute này có thể phải được yêu cầu riêng khi tìm kiếm và mức độ hỗ trợ khác nhau theo sản phẩm. Tương tự, `memberOf` có thể là thuộc tính tính toán theo cấu hình máy chủ; không phải mọi LDAP server đều cung cấp.

## 4. Object class: hợp đồng cấu trúc của entry

**Object class** là định nghĩa nằm trong **schema**, cho biết một kiểu đối tượng phải có attribute nào và được phép có attribute nào.

- **MUST**: các attribute bắt buộc đối với entry thuộc class đó (bao gồm yêu cầu kế thừa).
- **MAY**: các attribute được phép xuất hiện nhưng không bắt buộc.
- **SUP**: class cha mà object class kế thừa.

Chẳng hạn, lớp `person` yêu cầu `cn` và `sn`. Lớp `organizationalPerson` kế thừa `person`; `inetOrgPerson` lại kế thừa `organizationalPerson` và bổ sung nhiều attribute dành cho hồ sơ nhân sự/tài khoản như `mail`, `givenName` hoặc `uid` (tùy class và các quy tắc kế thừa). Vì vậy entry `inetOrgPerson` ở phần trên vẫn phải đáp ứng yêu cầu `cn` và `sn` của lớp tổ tiên `person`.

~~~text
top                       [abstract]
 └── person                [structural; MUST: cn, sn]
      └── organizationalPerson
           └── inetOrgPerson
~~~

LDAP schema phân loại object class theo vai trò:

| Loại | Vai trò | Cách hiểu |
|---|---|---|
| **STRUCTURAL** | Định nghĩa bản chất cấu trúc của entry | Ví dụ `person` → `organizationalPerson` → `inetOrgPerson` cùng một chuỗi kế thừa cấu trúc |
| **AUXILIARY** | Bổ sung khả năng/attribute cho entry khi schema và máy chủ cho phép | Không thay thế structural class chính |
| **ABSTRACT** | Là lớp nền để các lớp khác kế thừa | Ví dụ `top` |

Một entry thường có **một chuỗi structural object class hợp lệ**, có thể kèm auxiliary class. Việc khai báo nhiều class không có nghĩa muốn ghép tùy ý mọi structural class độc lập. Máy chủ kiểm tra schema khi thêm hoặc sửa entry; danh sách class thực tế và các ràng buộc chi tiết phụ thuộc vào schema được triển khai.

Điểm dễ nhầm: **object class không phải một entry và cũng không phải bảng trong cơ sở dữ liệu quan hệ**. Object class là khuôn mẫu/ràng buộc. Hai entry cùng class `inetOrgPerson` có thể có attribute tùy chọn khác nhau, nhưng đều phải tuân thủ yêu cầu chung của schema.

### Ba entry với ba vai trò khác nhau

Giả sử nhánh gốc `dc=example,dc=org` đã tồn tại. Có thể hình dung một tập LDIF như sau:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
description: Accounts used by applications

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
cn: Nguyen Van An
sn: Nguyen
mail: an@example.org

dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
~~~

- **`organizationalUnit`** dùng cho entry tổ chức nhánh như `ou=people`; thuộc tính `ou` là bắt buộc theo định nghĩa class này.
- **`inetOrgPerson`** thể hiện một người; trong ví dụ `cn` và `sn` bắt buộc theo lớp tổ tiên `person`.
- **`groupOfNames`** thể hiện nhóm; `cn` và `member` là các attribute bắt buộc. `member` chứa DN của thành viên, và có thể có nhiều giá trị khi nhóm có nhiều người.

Entry nhóm nằm dưới `ou=groups`, còn entry người dùng nằm dưới `ou=people`. **Quan hệ thành viên** được biểu diễn bằng giá trị `member` tham chiếu DN, không phải quan hệ cha–con trong DIT. Schema thông thường kiểm tra kiểu dữ liệu; việc tham chiếu có tồn tại, được tự cập nhật khi đổi DN hay được thực thi như khóa ngoại hay không còn phụ thuộc tính năng và cấu hình máy chủ.

## 5. DN, RDN, schema và object class phối hợp khi ghi dữ liệu

Khi ứng dụng tạo entry `uid=an,ou=people,dc=example,dc=org`, có thể hình dung máy chủ lần lượt đánh giá những câu hỏi sau:

1. **Vị trí**: `ou=people,dc=example,dc=org` có phải entry cha hợp lệ và đã tồn tại không?
2. **Tên**: DN có hợp lệ, không xung đột với entry khác và RDN `uid=an` có phù hợp chính sách đặt tên không?
3. **Cấu trúc**: tập `objectClass` có tạo thành tổ hợp class được schema chấp nhận không?
4. **Thuộc tính**: các attribute bắt buộc như `cn`, `sn` có đủ không, các attribute còn lại có được phép và có cú pháp đúng không?
5. **Quyền truy cập**: danh tính đã bind có quyền thêm entry tại vị trí đó không?

Một entry `inetOrgPerson` thiếu `sn` có thể bị từ chối vì vi phạm object class. Một entry có schema hợp lệ vẫn có thể bị từ chối nếu thiếu quyền ghi hoặc parent DN chưa tồn tại. **Schema kiểm soát tính hợp lệ của cấu trúc dữ liệu; quyền LDAP/ACL kiểm soát ai được đọc và ghi** — hai lớp kiểm soát khác nhau.

Với các thao tác sau đó, sửa `mail` là **modify attribute**; đổi `uid=an` sang `uid=an.nguyen` là **rename/move DN** theo khả năng máy chủ. Tăng hoặc giảm giá trị `member` là thay đổi nội dung entry nhóm. Trong Spring LDAP, các nghiệp vụ này được thể hiện bằng các API thao tác entry; chọn đúng API dựa trên việc đang sửa attribute hay thay đổi DN.

## 6. Tìm kiếm: đi từ DN đến tập entry thỏa điều kiện

Client LDAP tìm kiếm bằng cách xác định **search base**, **search scope**, **filter** và danh sách attribute cần lấy.

Ví dụ yêu cầu: “Tìm người có `uid=an` dưới nhánh `ou=people` và chỉ lấy tên, họ, email”.

~~~text
Search base : ou=people,dc=example,dc=org
Scope       : subtree
Filter      : (&(objectClass=inetOrgPerson)(uid=an))
Attributes  : cn, sn, mail
~~~

Filter ở đây dùng hai **attribute của entry**: `objectClass` và `uid`. Nó tìm những entry vừa có object class thích hợp vừa có uid bằng `an`. Không có việc tìm “trực tiếp trong class” như truy vấn một bảng SQL. Search base giới hạn phần cây được duyệt; filter giới hạn entry nào khớp điều kiện.

| Search scope | Phạm vi |
|---|---|
| **OBJECT / base** | Chỉ entry tại search base |
| **ONELEVEL / one** | Các entry con trực tiếp của search base |
| **SUBTREE / sub** | Search base và toàn bộ các mức con của nó |

Ví dụ khi base là `ou=people,dc=example,dc=org`, tìm `SUBTREE` có thể lấy entry `uid=an`; tìm `OBJECT` tại base chỉ xét chính entry `ou=people`. Kết quả thực tế còn chịu quyền đọc và filter của máy chủ.

### Liên hệ với Spring LDAP

Sau khi ứng dụng cấu hình `ContextSource` để kết nối, bind và xác định base DN `dc=example,dc=org`, có thể dùng `LdapTemplate` cùng `LdapQueryBuilder` để tìm kiếm. Ví dụ Java minh họa:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record DirectoryPerson(String cn, String mail) {}

public class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findByUid(String uid) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<DirectoryPerson>) attrs -> {
                    String cn = (String) attrs.get("cn").get();
                    String mail = attrs.get("mail") == null
                            ? null
                            : (String) attrs.get("mail").get();
                    return new DirectoryPerson(cn, mail);
                }
        );
    }
}
~~~

Trong ví dụ này:

- `ContextSource` (được cấu hình ở nơi khác) quản lý thông tin kết nối và cơ chế lấy LDAP context; base DN được giả định là `dc=example,dc=org`.
- `.base("ou=people")` đặt nhánh tìm kiếm **tương đối** so với base DN của `ContextSource`.
- `.where("objectClass").is("inetOrgPerson").and("uid").is(uid)` diễn đạt điều kiện trên attribute; API dựng filter giúp xử lý ký tự đặc biệt trong giá trị tốt hơn thao tác nối chuỗi filter thủ công.
- `AttributesMapper` chuyển các attribute trả về thành DTO Java. Ví dụ lấy giá trị đầu tiên của `cn`, xem `mail` là tùy chọn, và chưa xử lý trường hợp attribute nhiều giá trị.
- Nếu cần lấy cả **DN** của entry kết quả, hãy sử dụng API ánh xạ có ngữ cảnh (chẳng hạn `ContextMapper`) thay vì chỉ `AttributesMapper`.

Cùng mô hình entry/attribute/schema đó có thể được thao tác bằng `LdapClient` theo phong cách fluent, hoặc ánh xạ object qua **ODM** và các annotation như `@Entry`, `@Id`, `@Attribute`. Các API khác nhau ở cách viết Java; chúng vẫn gửi yêu cầu LDAP đến máy chủ và chịu những ràng buộc DN, schema, quyền truy cập như nhau.

**Lưu ý an toàn:** ví dụ chỉ minh họa phần truy vấn. Với hệ thống thực, dùng TLS phù hợp (LDAPS hoặc StartTLS), tài khoản bind có quyền tối thiểu, quản lý bí mật ngoài mã nguồn, giới hạn thuộc tính và phạm vi tìm kiếm. Không tự nối input người dùng vào biểu thức `(&(uid=...))` vì ký tự đặc biệt có thể làm thay đổi ý nghĩa filter; dùng builder hoặc cơ chế escape theo LDAP filter. Việc entry tồn tại và thỏa filter không đồng nghĩa người dùng đã được xác thực hay được cấp quyền ứng dụng.

## 7. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`inetOrgPerson` là một bản ghi người dùng.” | Đó là object class; `uid=an,...` mới là entry cụ thể. |
| “`cn` là DN.” | `cn` là attribute; DN là chuỗi RDN đầy đủ định danh vị trí entry. |
| “`objectClass` chỉ có một giá trị.” | Một entry thường khai báo nhiều class theo chuỗi kế thừa và có thể có auxiliary class. |
| “Cứ có class `person` thì `mail` bắt buộc.” | `person` yêu cầu `cn` và `sn`; `mail` không phải thuộc tính bắt buộc của `person`. |
| “Người dùng nằm trong nhóm vì nhóm là cha của người dùng trong cây.” | Thành viên nhóm thường được mô tả bằng `member`/DN hoặc cơ chế nhóm riêng của máy chủ. |
| “Có `memberOf` trên mọi máy chủ LDAP.” | Một số máy chủ sinh attribute này từ cơ chế nhóm; không nên mặc định luôn có. |
| “Schema hợp lệ là có thể thêm hoặc sửa entry.” | Còn phụ thuộc parent, DN, ACL, chính sách máy chủ và trạng thái kết nối. |
| “Tìm kiếm theo `uid` là xác thực người dùng.” | Search chỉ truy xuất thông tin. Xác thực còn yêu cầu quy trình bind/credential phù hợp. |

## 8. Tự kiểm tra bằng một tình huống

**Tình huống.** Đội vận hành cần lưu tài khoản `uid=linh,ou=people,dc=example,dc=org` với tên “Tran Mai Linh” và thêm vào nhóm `cn=developers,ou=groups,dc=example,dc=org`. Hãy xác định:

1. Đâu là entry và đâu là DN?
2. Entry người dùng cần class nào, những attribute nào bắt buộc?
3. Nên sửa gì trên entry nhóm để biểu diễn quan hệ thành viên?
4. Filter nào tìm riêng tài khoản Linh dưới `ou=people`?

**Gợi ý lời giải.** Entry người dùng có DN `uid=linh,ou=people,dc=example,dc=org`, có thể khai báo `top`, `person`, `organizationalPerson` và `inetOrgPerson`. Tối thiểu cần `cn` và `sn` theo chuỗi class `person`, cùng `uid: linh` để đáp ứng RDN đã chọn (nếu chính sách đặt tên cho phép). Entry nhóm `groupOfNames` thêm một giá trị `member: uid=linh,ou=people,dc=example,dc=org`. Với base `ou=people,dc=example,dc=org` và scope `subtree`, có thể dùng filter `(&(objectClass=inetOrgPerson)(uid=linh))`. Tất cả thay đổi vẫn cần thỏa schema và quyền của máy chủ.

## Ghi nhớ

Một yêu cầu Spring LDAP thường đi theo chuỗi tư duy: **chọn nhánh DN → tìm hoặc xác định entry → đọc/ghi attribute → kiểm tra object class và schema → áp dụng quyền truy cập và xử lý phản hồi LDAP**. Khi phân biệt rõ directory service (hệ thống), entry (đối tượng), attribute (dữ liệu) và object class (ràng buộc), bạn sẽ đọc LDIF, viết filter, ánh xạ kết quả bằng Spring LDAP và phân tích lỗi schema/DN dễ dàng hơn.
