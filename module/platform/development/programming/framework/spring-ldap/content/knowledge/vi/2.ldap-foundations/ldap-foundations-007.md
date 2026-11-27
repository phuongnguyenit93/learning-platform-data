# Leaf entry, container entry và các nhánh trong DIT

Trong LDAP, dữ liệu được sắp xếp thành **cây thông tin thư mục** (*Directory Information Tree*, viết tắt là **DIT**). Để dùng Spring LDAP đúng cách, người học cần phân biệt entry ở cuối nhánh, entry dùng làm nơi chứa các entry khác, và những nhánh nối các entry với nhau. Những khái niệm này quyết định cách đặt DN, chọn phạm vi tìm kiếm, tạo entry, di chuyển entry và xử lý thao tác xóa.

Bài học thuộc phần **LDAP nền tảng** của SPRING_LDAP. Ta sẽ dùng một thư mục nhân sự làm ví dụ xuyên suốt, rồi liên hệ với truy vấn an toàn bằng `LdapTemplate`, `LdapClient` và ánh xạ kết quả trong ứng dụng Java.

## 1. DIT là gì?

DIT biểu diễn các **entry** theo cấu trúc cha–con. Mỗi entry có một **Distinguished Name (DN)** để định danh vị trí của nó trong cây, cùng tập thuộc tính (*attributes*) chịu sự ràng buộc của schema.

Giả sử một tổ chức có naming context `dc=example,dc=org`:

~~~text
dc=example,dc=org
├── ou=people
│   ├── ou=engineering
│   │   ├── uid=an
│   │   └── uid=binh
│   ├── ou=sales
│   │   └── uid=chi
│   └── ou=trainees
└── ou=groups
    └── cn=developers
~~~

Trong sơ đồ, mỗi dòng biểu thị một **entry**; việc thụt dòng biểu thị quan hệ cha–con. Những ký hiệu `ou=`, `uid=` và `cn=` chỉ là **Relative Distinguished Name (RDN)** của entry tại cấp đó, chưa phải DN đầy đủ.

Ví dụ DN đầy đủ của nhân viên An là:

~~~text
uid=an,ou=engineering,ou=people,dc=example,dc=org
~~~

| Khái niệm | Trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Entry | `uid=an` | Một nút chứa các thuộc tính LDAP |
| RDN | `uid=an` | Thành phần tên phân biệt entry với các entry cùng cha |
| DN | `uid=an,ou=engineering,ou=people,dc=example,dc=org` | Tên xác định vị trí entry trong DIT |
| Parent | `ou=engineering,ou=people,dc=example,dc=org` | Entry cha trực tiếp của An |
| Sibling | `uid=binh,...` | Entry có cùng parent với An |
| Ancestor | `ou=people,...` | Entry tổ tiên nằm phía trên An |
| Descendant | `uid=an,...` khi xét từ `ou=people,...` | Entry nằm dưới một entry gốc được chọn |
| Naming context | `dc=example,dc=org` | Vùng tên mà LDAP server công bố và phục vụ |

**Lưu ý:** `dc=example,dc=org` là gốc của naming context trong ví dụ, không nhất thiết là gốc duy nhất của mọi thư mục trên server. Một LDAP server có thể phục vụ nhiều naming context khác nhau.

### Đọc DN từ phải sang trái

Trong DN, các RDN được viết từ entry cụ thể tới tổ tiên, ngăn nhau bằng dấu phẩy:

~~~text
uid=an,ou=engineering,ou=people,dc=example,dc=org
│      │              │         └─────────────── gốc ví dụ
│      │              └───────────────────────── OU people
│      └──────────────────────────────────────── OU engineering
└─────────────────────────────────────────────── entry người dùng An
~~~

Muốn tìm parent của một entry, bỏ **RDN ngoài cùng bên trái** của DN. Muốn tạo DN cho entry con, thêm RDN mới vào **bên trái** DN của parent.

Chẳng hạn, entry `uid=an,...` và `uid=binh,...` cùng nằm dưới `ou=engineering,...` dù các giá trị `uid` khác nhau. DN phải được coi là tên có cấu trúc, không nên nối chuỗi tùy tiện: dấu phẩy, dấu bằng, khoảng trắng đầu/cuối hoặc ký tự đặc biệt trong giá trị RDN cần được escape đúng quy tắc LDAP.

## 2. Leaf entry: entry ở cuối một nhánh

**Leaf entry** là entry hiện **không có entry con trực tiếp**. Trong sơ đồ trên, `uid=an`, `uid=binh`, `uid=chi` và `cn=developers` là leaf entry.

Ví dụ entry người dùng:

~~~ldif
dn: uid=an,ou=engineering,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
mail: an@example.org
~~~

Entry này mang dữ liệu của một người dùng; trong DIT minh họa, nó chưa có entry con. Các thuộc tính `cn`, `sn`, `mail` là **dữ liệu của entry**, không phải các nút con của entry.

Đặc điểm cần nhớ:

- **Leaf là trạng thái theo cấu trúc cây tại thời điểm quan sát.** Không có một objectClass LDAP chuẩn chung tên là “leaf” áp dụng cho mọi thư mục.
- Entry thường dùng làm leaf có thể là người dùng, thiết bị, nhóm, vai trò hoặc một entry ứng dụng; loại dữ liệu không tự quyết định nó có con hay không.
- Không thể kết luận chắc chắn một entry là leaf chỉ vì RDN bắt đầu bằng `uid=` hoặc `cn=`.
- Một entry chỉ được phép có con hay không còn phụ thuộc schema, quy tắc nội dung DIT của máy chủ, ACL và cách server triển khai.

Ngay cả `ou=trainees` trong ví dụ cũng **đang là leaf** vì chưa có người học nào bên dưới nó, mặc dù OU này được tạo ra để chứa entry trong tương lai.

## 3. Container entry: entry dùng để tổ chức các entry con

**Container entry** là entry đóng vai trò vị trí tổ chức, nơi các entry khác được đặt dưới nó. Trong mô hình LDAP phổ biến, các `organizationalUnit` (OU) thường được dùng làm container cho phòng ban hoặc nhóm quản trị.

Ví dụ:

~~~ldif
dn: ou=engineering,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: engineering
description: Nhan su khoi ky thuat
~~~

OU `engineering` đang chứa hai entry người dùng. DN của từng người dùng thể hiện quan hệ cha–con với OU đó; ứng dụng không cần một thuộc tính riêng trên OU để liệt kê tất cả con.

| Entry | Vai trò sử dụng | Có con trong sơ đồ? | Là leaf tại thời điểm này? |
| --- | --- | --- | --- |
| `dc=example,dc=org` | Gốc naming context | Có | Không |
| `ou=people` | Container nhân sự | Có | Không |
| `ou=engineering` | Container phòng kỹ thuật | Có | Không |
| `ou=trainees` | Container dự kiến cho học viên | Không | **Có** |
| `uid=an` | Entry người dùng | Không | **Có** |
| `cn=developers` | Entry nhóm | Không | **Có** |

Vì vậy, **container** diễn tả vai trò thiết kế hoặc khả năng tổ chức entry, còn **leaf** mô tả thực tế entry hiện không có con. Hai khái niệm không loại trừ nhau: một container đang rỗng có thể đồng thời là leaf.

Không nên đồng nhất “container” với một objectClass duy nhất:

- `organizationalUnit` là objectClass chuẩn thường được dùng để xây OU.
- `domain` với thuộc tính `dc` có thể làm phần gốc của cấu trúc tên.
- Trong **Active Directory**, `container` còn là tên một objectClass cụ thể; đó là khái niệm schema riêng cần phân biệt với chữ “container” theo nghĩa tổ chức DIT nói chung.
- Khả năng chứa loại entry nào tùy vào schema, DIT structure rules, ACL và chính sách của LDAP server. Việc có một OU không đồng nghĩa mọi loại objectClass đều có thể được tạo tùy ý bên dưới nó.

## 4. Branch: nhánh của DIT và quan hệ tổ tiên

Trong DIT, **nhánh** (*branch*) thường dùng để chỉ một phần cây xuất phát từ một entry và gồm các entry ở bên dưới nó. Khi nói “branch entry”, người ta thường muốn nói một entry có con, nằm trên một hoặc nhiều leaf. “Branch” là cách nhìn cấu trúc, không mặc nhiên là objectClass LDAP.

Ví dụ phần cây có gốc `ou=engineering,ou=people,dc=example,dc=org`:

~~~text
ou=engineering,ou=people,dc=example,dc=org
├── uid=an,ou=engineering,ou=people,dc=example,dc=org
└── uid=binh,ou=engineering,ou=people,dc=example,dc=org
~~~

Có thể mô tả:

- **Nhánh `ou=people`:** gồm chính `ou=people` và mọi OU, người dùng nằm phía dưới.
- **Nhánh `ou=engineering`:** gồm `ou=engineering` cùng hai người dùng An và Bình.
- **Đường đi từ gốc đến An:** `dc=example,dc=org` → `ou=people` → `ou=engineering` → `uid=an`.
- **Các nhánh cùng cấp:** `ou=people` và `ou=groups` là sibling, cùng parent `dc=example,dc=org`.

Phân biệt **vị trí trong cây** với **quan hệ logic** giữa các entry. Một nhóm LDAP có thể tham chiếu đến thành viên đang nằm ở nhánh khác:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=engineering,ou=people,dc=example,dc=org
~~~

Thuộc tính `member` chứa DN được tham chiếu, **không biến `uid=an` thành con của `cn=developers`**. DN của An vẫn nằm dưới nhánh `ou=people`. LDAP group membership và LDAP DIT containment là hai loại quan hệ khác nhau.

Vì DN mô tả vị trí, việc di chuyển người dùng từ `ou=engineering` sang `ou=sales` có thể làm thay đổi DN. Các tham chiếu từ nhóm, cấu hình hoặc hệ thống ngoài có thể cần cập nhật; khả năng tự xử lý tham chiếu tùy máy chủ và cơ chế tích hợp.

## 5. Search scope: tìm entry ở một điểm, một cấp hay toàn bộ nhánh

Hiểu cây DIT đặc biệt quan trọng khi truy vấn LDAP. Một phép tìm kiếm có **base DN** (điểm bắt đầu), **filter** (điều kiện) và **scope** (độ sâu tìm kiếm).

Ba phạm vi thường gặp trong JNDI và LDAP:

| Scope | Tên JNDI | Phạm vi được xét |
| --- | --- | --- |
| **Base object** | `SearchControls.OBJECT_SCOPE` | Chỉ entry tại base DN |
| **One level** | `SearchControls.ONELEVEL_SCOPE` | Chỉ các entry con trực tiếp của base; không gồm chính base |
| **Subtree** | `SearchControls.SUBTREE_SCOPE` | Base và tất cả descendant ở mọi độ sâu |

Chọn base `ou=people,dc=example,dc=org` với filter `(objectClass=*)`, giả sử mọi entry trong ví dụ đều có quyền đọc:

| Scope | Kết quả nằm trong vùng xét |
| --- | --- |
| Base object | `ou=people` |
| One level | `ou=engineering`, `ou=sales`, `ou=trainees` |
| Subtree | `ou=people`, ba OU con và ba người dùng An, Bình, Chi |

Nếu vẫn chọn base `ou=people,...` nhưng dùng filter `(objectClass=inetOrgPerson)`:

| Scope | Kết quả khớp filter |
| --- | --- |
| Base object | Không có, vì `ou=people` không phải `inetOrgPerson` |
| One level | Không có, vì ba con trực tiếp đều là OU |
| Subtree | An, Bình và Chi |

Đây là nguyên nhân phổ biến khiến ứng dụng tìm thấy dữ liệu khi truy vấn subtree nhưng nhận danh sách rỗng ở one level: entry cần tìm nằm sâu hơn một cấp, dù filter hoàn toàn đúng.

### Ví dụ thực tế bằng `LdapTemplate`

Trong ví dụ dưới đây, `ContextSource` đã được cấu hình với base `dc=example,dc=org`. Bởi vậy, `ou=people` truyền vào `LdapTemplate` là DN **tương đối với base đã cấu hình**:

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.LdapTemplate;

public class PeopleDirectory {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findDirectChildDns() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);

        return ldapTemplate.search(
                "ou=people",
                "(objectClass=*)",
                controls,
                (ContextMapper<String>) ctx -> ctx.getDn().toString());
    }

    public List<String> findPeopleInAllNestedOus() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);

        return ldapTemplate.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                controls,
                (ContextMapper<String>) ctx -> ctx.getDn().toString());
    }
}
~~~

Phương thức đầu chỉ tìm các entry con trực tiếp dưới `ou=people`. Phương thức sau tìm người dùng ở mọi OU lồng nhau dưới đó. `ContextMapper` được dùng vì ví dụ quan tâm DN; nếu chỉ cần tên hay email, có thể chuyển sang `AttributesMapper`. Giá trị DN do mapper trả về cần được hiểu theo quy ước DN tương đối của `ContextSource`/Spring LDAP khi lưu hoặc dùng lại.

Kết quả thực tế có thể ít hơn sơ đồ vì ACL, giới hạn server, alias/referral hoặc filter bổ sung. Không nên giả định số entry thực tế luôn cố định.

### Base DN khác với search base

Hai lớp base thường dễ bị nhầm:

- **Base của `ContextSource`**: ví dụ `dc=example,dc=org`, xác định gốc mà ứng dụng làm việc tương đối với nó.
- **Base của từng truy vấn**: ví dụ `ou=engineering,ou=people`, xác định nhánh cụ thể để tìm.

Nếu `ContextSource` đã dùng `dc=example,dc=org`, không nên lại đưa đầy đủ `ou=engineering,ou=people,dc=example,dc=org` vào tham số vốn được xử lý tương đối với base. Hãy kiểm tra quy ước cụ thể của API được dùng để tránh lặp phần hậu tố DN.

Khi filter chứa giá trị lấy từ người dùng, dùng `LdapQueryBuilder` hoặc API escape filter tương ứng, thay vì ghép chuỗi LDAP filter từ input. Quy tắc escape DN và escape filter **khác nhau**; không dùng một loại escape để thay thế loại kia.

## 6. Tạo entry: vì sao parent phải tồn tại?

LDAP thường yêu cầu entry cha đã tồn tại trước khi thêm entry con. Ví dụ muốn tạo:

~~~text
uid=lan,ou=trainees,ou=people,dc=example,dc=org
~~~

thì `ou=trainees,ou=people,dc=example,dc=org` phải hiện diện và tài khoản thao tác phải có quyền thêm entry tại vị trí đó. Nếu không có parent, server thường báo lỗi như `noSuchObject`; nếu không đủ quyền, server có thể trả về `insufficientAccessRights`.

Một chuỗi tạo entry điển hình:

1. Kiểm tra naming context và base DN của `ContextSource`.
2. Xác định parent OU; nếu cần thêm OU mới, phải tạo dưới parent đang tồn tại.
3. Chọn RDN cho entry mới (ví dụ `uid=lan`), tạo DN đúng cú pháp.
4. Chuẩn bị các `objectClass` và thuộc tính mà schema yêu cầu (ví dụ `cn`, `sn` cho đối tượng người dùng phù hợp).
5. Dùng `LdapTemplate.bind(...)` hoặc API tương đương được dự án chọn; xử lý lỗi schema, trùng DN và thiếu quyền.

Khi tạo DN từ dữ liệu đầu vào, nên sử dụng công cụ dựng tên có hiểu biết cú pháp DN:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "lan"; // Có thể đến từ dữ liệu đầu vào đã kiểm tra.
Name relativeDn = LdapNameBuilder.newInstance("ou=trainees,ou=people")
        .add("uid", uid)
        .build();

// Kết quả tương đối với base ContextSource:
// uid=lan,ou=trainees,ou=people
~~~

Cách này giúp xử lý ký tự đặc biệt trong giá trị RDN theo quy tắc DN, thay vì dùng `"uid=" + uid + ",ou=trainees,ou=people"`. Nó không thay thế việc kiểm tra dữ liệu, schema hoặc quyền ghi.

## 7. Xóa và di chuyển: tác động của cấu trúc leaf/branch

### Xóa một leaf

Ví dụ, nếu `uid=chi,ou=sales,...` không có con, server có thể cho xóa entry bằng `LdapTemplate.unbind(...)` khi tài khoản có quyền. Việc xóa vẫn cần tuân theo chính sách nghiệp vụ, chẳng hạn rà soát các tham chiếu nhóm.

### Xóa một container đang có con

Giả sử `ou=engineering` đang chứa An và Bình. Thao tác xóa trực tiếp `ou=engineering` thông thường **không hợp lệ** vì entry còn subordinate; server có thể trả về LDAP result code `notAllowedOnNonLeaf (66)`.

Các lựa chọn cần được đánh giá trước khi thao tác thật:

- Xóa hoặc di chuyển các entry con hợp lệ theo thứ tự từ dưới lên, rồi mới xóa OU.
- Nếu hệ thống có tiện ích xóa cây con (*subtree delete*), kiểm tra kỹ server, quyền hạn và phạm vi vì đây không phải giả định an toàn cho mọi server.
- Với dữ liệu thật, tạo bản sao lưu và kiểm tra ảnh hưởng đến các DN đang được tham chiếu trước khi thay đổi cấu trúc.

**Không có tính chất “xóa OU là tất cả con tự động biến mất” trong thao tác xóa entry LDAP thông thường.** Đây là điểm khác biệt quan trọng so với cách nhiều người hình dung từ thư mục tệp hoặc cơ sở dữ liệu có cascade delete.

### Đổi tên hoặc chuyển nhánh

Thao tác đổi RDN hoặc di chuyển entry thường được gọi là *Modify DN* trong giao thức LDAP. Ví dụ chuyển `uid=an` từ `ou=engineering` sang `ou=sales`:

~~~text
Trước:
uid=an,ou=engineering,ou=people,dc=example,dc=org

Sau:
uid=an,ou=sales,ou=people,dc=example,dc=org
~~~

Dữ liệu bên trong entry có thể vẫn giống nhau nhưng **DN đã đổi**. Nếu các entry nhóm có `member` lưu DN cũ, ứng dụng cần hiểu server có tự duy trì tham chiếu hay không. Không nên giả định mọi LDAP server tự cập nhật quan hệ tham chiếu khi di chuyển entry. Việc di chuyển một entry chứa nhiều con còn phụ thuộc hỗ trợ và ràng buộc của máy chủ.

## 8. Thiết kế các nhánh DIT cho ứng dụng thực tế

Giả sử ứng dụng quản lý nhân sự, nhóm phân quyền và tài khoản máy chủ. Một mô hình có thể là:

~~~text
dc=example,dc=org
├── ou=people
│   ├── ou=engineering
│   └── ou=sales
├── ou=groups
│   ├── cn=developers
│   └── cn=hr-readers
└── ou=services
    └── uid=app-reader
~~~

Mô hình này giúp phân vùng tìm kiếm và phân quyền theo nhánh. Tuy nhiên, lựa chọn cấu trúc OU cần dựa trên dữ liệu, chính sách tổ chức và tần suất thay đổi: đặt người dùng vào OU phòng ban khiến DN có thể thay đổi khi họ chuyển phòng. Nếu hệ thống lưu DN lâu dài ở nhiều nơi, cần thiết kế cơ chế cập nhật tham chiếu phù hợp.

| Quyết định thiết kế | Hệ quả |
| --- | --- |
| Tách `ou=people` khỏi `ou=services` | Dễ cấu hình phạm vi tìm kiếm và quyền riêng cho tài khoản ứng dụng |
| Tách nhóm sang `ou=groups` | DIT thể hiện vị trí quản lý nhóm, còn thành viên được biểu diễn bằng tham chiếu |
| Lồng nhiều OU theo phòng ban | Phân cấp rõ, nhưng truy vấn người dùng phải tính đến `SUBTREE_SCOPE` |
| Đặt tất cả người dùng trực tiếp dưới `ou=people` | Truy vấn one level đơn giản hơn, nhưng khó phản ánh tổ chức nếu cần phân nhánh |
| Đổi OU hoặc RDN của entry | Có thể thay đổi DN được lưu trong ứng dụng/nhóm |

Spring LDAP cho phép đặt các quan tâm này ở các lớp khác nhau: `ContextSource` giữ cấu hình server và base; `LdapTemplate`/`LdapClient` thực hiện truy vấn theo DN, filter và scope; `AttributesMapper`, `ContextMapper` hoặc ODM biến entry thành mô hình Java. **Mapping object không làm thay đổi cây DIT**: ánh xạ một entry sang Java object không khiến entry tự trở thành cha/con của entry khác.

Khi thử nghiệm với server thật, dùng LDAPS hoặc StartTLS có xác thực chứng chỉ, tài khoản bind được cấp quyền tối thiểu, timeout và pooling phù hợp. Một truy vấn subtree quá rộng có thể ảnh hưởng hiệu năng hoặc vượt giới hạn kết quả của server. Nên hạn chế search base, chọn filter đủ đặc hiệu, chỉ yêu cầu thuộc tính cần dùng và kiểm tra kích thước/trang kết quả theo tính năng server.

## 9. Bài thực hành nhận diện leaf, container và branch

Cho DIT ở mục 1. Hãy tự trả lời trước khi xem gợi ý:

1. Parent DN của `uid=binh,ou=engineering,ou=people,dc=example,dc=org` là gì?
2. `ou=trainees` là leaf entry, container entry hay cả hai?
3. Tìm dưới base `ou=people` với `ONELEVEL_SCOPE` và filter `(objectClass=inetOrgPerson)` sẽ trả về bao nhiêu entry?
4. Chuyển sang `SUBTREE_SCOPE` nhưng giữ nguyên filter ở câu 3 thì trả về bao nhiêu entry trong sơ đồ?
5. Tại sao `cn=developers` không phải parent của An dù có thuộc tính `member` trỏ đến An?
6. Có thể xóa `ou=engineering` ngay khi An và Bình vẫn tồn tại dưới nhánh này bằng một thao tác xóa entry thông thường hay không?

**Đáp án tham khảo:**

| Câu | Đáp án | Giải thích |
| --- | --- | --- |
| 1 | `ou=engineering,ou=people,dc=example,dc=org` | Bỏ RDN ngoài cùng bên trái `uid=binh` |
| 2 | Cả hai | Được tạo để chứa entry; hiện không có con nên đang là leaf |
| 3 | 0 | Con trực tiếp của `ou=people` đều là OU |
| 4 | 3 | An, Bình, Chi nằm sâu hơn dưới các OU con |
| 5 | Quan hệ `member` là tham chiếu | Parent được xác định bằng DN, không phải bằng thuộc tính tham chiếu |
| 6 | Thông thường không | Entry đang có subordinate; phải xử lý con hoặc dùng cơ chế xóa cây được hỗ trợ và kiểm soát |

### Tự kiểm tra với Spring LDAP

Trên một LDAP server dùng cho thử nghiệm, tạo cây dữ liệu tương đương (hoặc đọc cây có sẵn mà bạn được cấp quyền). Viết hai truy vấn với cùng base `ou=people`, cùng filter `(objectClass=inetOrgPerson)`, chỉ khác scope one level và subtree. Đối chiếu sự khác nhau của kết quả rồi đổi base thành `ou=engineering,ou=people`. Khi kết quả không đúng dự kiến, lần lượt kiểm tra DN tương đối, vị trí entry thật, scope, filter, schema và ACL; **không dùng quyền quản trị để che đi lỗi cấu hình hoặc truy vấn**.

## 10. Những điểm cần ghi nhớ

- **DIT** là cây entry LDAP được định danh bằng DN; parent–child được thể hiện qua cấu trúc DN.
- **Leaf entry** hiện không có entry con. **Container entry** là entry có vai trò chứa hoặc tổ chức entry khác; container rỗng cũng có thể là leaf.
- **Branch** là một nhánh của cây, không phải tên chung của một objectClass bắt buộc.
- Thuộc tính tham chiếu như `member` biểu diễn quan hệ logic, không thay đổi vị trí entry trong DIT.
- **Search scope** quyết định tìm ở chính base, một cấp con hay toàn bộ subtree; filter chỉ lọc trong vùng đó.
- Việc thêm, xóa, đổi RDN và di chuyển entry phụ thuộc parent, schema, ACL và đặc tính LDAP server. Trước khi thao tác, hãy xác định đúng DN, phạm vi và ảnh hưởng của thay đổi.
