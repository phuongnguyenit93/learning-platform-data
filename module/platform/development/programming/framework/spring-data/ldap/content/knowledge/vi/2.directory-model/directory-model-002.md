# Cây thông tin thư mục DIT và quan hệ cha–con

Trong **Spring Data LDAP**, đối tượng Java được ánh xạ từ các entry nằm trong một **cây thông tin thư mục**. Muốn hiểu vì sao một repository tìm thấy hoặc không tìm thấy người dùng, vì sao DN cần đầy đủ nhánh cha, hay vì sao di chuyển entry làm thay đổi định danh của nó, trước hết cần nắm cách LDAP tổ chức dữ liệu thành **DIT (Directory Information Tree)**.

Bài học này tập trung vào cấu trúc DIT và quan hệ **cha – con** giữa các entry. Những khái niệm về schema, `objectClass`, search filter, `LdapTemplate` và repository được đưa vào vừa đủ để thấy mô hình cây ảnh hưởng trực tiếp đến thao tác trong ứng dụng Java.

Sau bài học, bạn có thể:

- Nhận diện **entry**, **attribute**, **RDN**, **DN**, **naming context** và **Root DSE**.
- Chỉ ra cha, con, anh chị em và tổ tiên của một entry từ DN.
- Phân biệt quan hệ cây DIT với quan hệ phòng ban, người quản lý hoặc thành viên nhóm trong nghiệp vụ.
- Giải thích cách search base, search scope và filter quyết định tập entry được truy vấn.
- Áp dụng mô hình DIT khi ánh xạ entity, tìm kiếm và đổi tên/di chuyển entry qua Spring LDAP và Spring Data LDAP.

## 1. DIT là gì?

**Directory Information Tree (DIT)** là mô hình phân cấp logic của các **entry** trong dịch vụ thư mục LDAP. Mỗi entry chứa một tập thuộc tính, chẳng hạn `uid`, `cn`, `sn`, `mail` hoặc `objectClass`. Entry có một **tên phân biệt** duy nhất (**Distinguished Name – DN**) trong phạm vi thư mục mà server quản lý.

Một DIT minh họa:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=teams
│   ├── cn=backend
│   └── cn=qa
└── ou=services
    └── uid=inventory-app
```

Mỗi nhãn trong hình biểu diễn **RDN (Relative Distinguished Name)** của entry tương ứng. Nếu viết đầy đủ, entry `uid=lan` có DN:

```text
uid=lan,ou=people,dc=example,dc=org
```

Theo quy ước chuỗi LDAP DN, RDN của **chính entry** đứng bên trái; các RDN của tổ tiên nằm dần về bên phải. DN của cha của `uid=lan` là `ou=people,dc=example,dc=org`; DN của ông/bà là `dc=example,dc=org`.

DIT là cây **logic của các tên và entry**, không khẳng định server lưu dữ liệu dưới dạng thư mục tập tin hay có cấu trúc vật lý tương ứng trên đĩa. Nó cũng không bắt buộc phải phản ánh sơ đồ tổ chức thực tế của doanh nghiệp.

## 2. Entry, thuộc tính, RDN và DN

### 2.1. Entry và attribute

Ví dụ entry của một người có thể được biểu diễn dưới dạng LDIF (*LDAP Data Interchange Format*):

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
```

- `dn` là vị trí và định danh của entry trong DIT; dòng này thuộc biểu diễn LDIF, không phải một thuộc tính nội dung thông thường giống `cn`.
- `objectClass` mô tả các lớp schema entry tuân theo. `inetOrgPerson` kế thừa từ các lớp như `organizationalPerson` và `person`.
- `uid`, `cn`, `sn`, `mail` là các thuộc tính của entry. Một thuộc tính có thể có một hoặc nhiều giá trị tùy schema và loại thuộc tính.
- Schema quy định thuộc tính nào **bắt buộc** (MUST), thuộc tính nào **được phép** (MAY), loại giá trị và các quy tắc so khớp.

Đối với `inetOrgPerson`, `cn` và `sn` là những thuộc tính bắt buộc được kế thừa qua lớp `person`. Khi tạo entry, không chỉ có DN đúng là đủ; entry còn phải tuân thủ schema và quyền của tài khoản đang thao tác.

### 2.2. RDN là nhãn của entry dưới cha trực tiếp

Trong DN:

```text
uid=lan,ou=people,dc=example,dc=org
└─┬──┘ └───┬───┘ └─────┬──────┘
  │        │           └─ Các RDN của tổ tiên cao hơn
  │        └─ RDN của entry cha
  └─ RDN của entry hiện tại
```

RDN của người dùng là `uid=lan`. Một RDN thông thường có dạng `loạiThuộcTính=giáTrị`, nhưng LDAP cũng hỗ trợ **RDN nhiều thành phần**, ví dụ `cn=Lan+uid=lan` (các phần nối bằng `+`). Các thuộc tính dùng trong RDN phải phù hợp với quy tắc đặt tên và schema của directory.

**RDN chỉ cần phân biệt trong phạm vi cùng một cha.** Vì vậy, hai entry đều có RDN `uid=lan` vẫn có thể tồn tại ở hai nhánh khác nhau:

```text
uid=lan,ou=people,dc=example,dc=org
uid=lan,ou=contractors,dc=example,dc=org
```

Ngược lại, không thể có hai entry phân biệt với cùng DN chính xác dưới một cha; directory sẽ coi đây là trùng tên.

### 2.3. DN là đường tên phân cấp đầy đủ

Một DN được tạo bằng cách nối RDN hiện tại với chuỗi RDN của các entry cha. Mỗi cặp `tên=giáTrị` trong DN là một **RDN**, không phải một filter tìm kiếm.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| RDN | `uid=lan` | Tên tương đối của entry dưới cha |
| DN | `uid=lan,ou=people,dc=example,dc=org` | Tên phân biệt của entry trong DIT |
| DN của cha | `ou=people,dc=example,dc=org` | Entry chứa entry `uid=lan` trực tiếp |
| Attribute `uid` | `uid: lan` | Dữ liệu thuộc tính trên entry |
| Filter | `(uid=lan)` | Điều kiện tìm kiếm entry có `uid` phù hợp |

`dc` thường biểu diễn một thành phần tên miền (*domain component*), `ou` thường chỉ *organizational unit*, `cn` là *common name*, còn `uid` là *user identifier*. Đây là các kiểu thuộc tính hay gặp, **không phải các cấp cây cố định**: một cây DIT hợp lệ có thể dùng RDN thuộc loại khác theo schema và naming rule của server.

### 2.4. DN không phải chuỗi phân tách bằng dấu phẩy một cách tùy tiện

Giá trị RDN có thể chứa dấu phẩy, dấu cộng hoặc ký tự đặc biệt. Ví dụ, nếu `cn` có giá trị `Lan, QA`, DN phải escape dấu phẩy bên trong giá trị:

```text
cn=Lan\, QA,ou=people,dc=example,dc=org
```

Vì vậy, **không** dùng `dn.split(",")` để tìm các cấp của DN và không nối input tùy ý để xây DN. Java/JNDI hỗ trợ `javax.naming.ldap.LdapName`/`Rdn`; Spring LDAP cung cấp `LdapNameBuilder`. Chúng giúp biểu diễn và escape DN đúng cách. Việc escape DN tuân RFC 4514; escape giá trị **search filter** là một quy tắc khác theo RFC 4515.

## 3. Quan hệ cha – con, anh chị em và tổ tiên

Với cây:

```text
dc=example,dc=org                        (A)
├── ou=people                             (B)
│   ├── uid=lan                           (C)
│   └── uid=minh                          (D)
└── ou=teams                              (E)
    └── cn=backend                        (F)
```

Ta có các quan hệ:

| Quan hệ | Ví dụ | Cách hiểu |
| --- | --- | --- |
| **Parent (cha)** | B là cha của C | DN của B thu được khi bỏ RDN đầu của DN của C |
| **Child (con trực tiếp)** | C là con của B | DN của C có thêm đúng một RDN ở phía trái DN của B |
| **Sibling (cùng cha)** | C và D là anh chị em | Có chung DN cha B nhưng RDN khác nhau |
| **Ancestor (tổ tiên)** | A là tổ tiên của C | DN của A là hậu tố RDN hợp lệ của DN của C |
| **Descendant (hậu duệ)** | F là hậu duệ của A | Đường đi từ A tới F đi qua E |
| **Subtree (cây con)** | B cùng C, D | Gồm entry B và toàn bộ các hậu duệ của nó |

Phát biểu “DN của cha là DN của con bỏ RDN đầu” là quy tắc ở **dạng trình bày DN chuẩn**. Các API `Name` của Java có cách đánh số các component riêng; không nên suy ra thứ tự index trong `LdapName` từ thứ tự hiển thị mà chưa đọc hợp đồng API.

### 3.1. Parent entry phải tồn tại

Trong trường hợp thông thường, trước khi thêm `uid=lan,ou=people,dc=example,dc=org`, nhánh cha `ou=people,dc=example,dc=org` phải tồn tại và là phần của naming context được server phục vụ. Tạo một DN con khi cha chưa có thường gây lỗi **No Such Object**, ngay cả khi các thuộc tính của entry mới hoàn toàn hợp lệ.

Tương tự, xóa một entry cha đang có con thường bị từ chối. Muốn xóa cả nhánh cần xử lý các entry con trước hoặc dùng cơ chế subtree deletion chuyên biệt nếu directory hỗ trợ và người dùng có đủ quyền. Không nên coi thao tác xóa trên cha là tự động xóa đệ quy.

### 3.2. Naming context và Root DSE

`dc=example,dc=org` thường đóng vai trò **naming context** (suffix) mà một server quản lý. Entry này là điểm đầu của nhánh dữ liệu trong ví dụ, nhưng không đồng nhất với **Root DSE**.

**Root DSE** là một entry đặc biệt được truy cập bằng **DN rỗng** (`""`), thường dùng để công bố khả năng của LDAP server, chẳng hạn danh sách `namingContexts`, phiên bản LDAP và các control/extension được hỗ trợ. Root DSE nằm ở vị trí đặc biệt trong mô hình directory; nó không phải entry `dc=example,dc=org` và không phải dữ liệu người dùng được tạo theo `objectClass=domain`.

Một server có thể cung cấp nhiều naming context hoặc referral tới server khác. Vì vậy, không được mặc định toàn bộ dữ liệu của một tổ chức đều nằm dưới một `dc=...` duy nhất.

## 4. DIT thể hiện gì và không thể hiện gì?

Một cách tổ chức phổ biến là tách người dùng, nhóm và service account thành các nhánh `ou=people`, `ou=groups`, `ou=services` để dễ phân quyền, áp dụng chính sách hoặc giới hạn phạm vi tìm kiếm. Tuy nhiên, **quan hệ parent–child trong DIT chỉ là quan hệ vị trí tên**.

Các ngữ nghĩa nghiệp vụ khác cần được biểu diễn riêng:

- `uid=lan` nằm dưới `ou=people` **không** có nghĩa Lan báo cáo trực tiếp cho một `organizationalUnit` theo quan hệ quản lý nhân sự.
- Entry người dùng thuộc nhóm backend không nhất thiết nằm dưới entry `cn=backend`; quan hệ thành viên thường nằm trong các thuộc tính như `member` hoặc `uniqueMember` của entry nhóm, tùy schema/server.
- Quan hệ quản lý trực tiếp có thể được biểu diễn bằng thuộc tính tham chiếu DN, ví dụ `manager`, nhưng thuộc tính này độc lập với parent DN trong DIT.
- `ou=Engineering` trong một entry có thể là **giá trị thuộc tính**; nó không buộc entry phải nằm dưới một container `ou=Engineering`.

Ví dụ:

```ldif
dn: cn=backend,ou=teams,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
```

Nhóm `backend` nằm ở nhánh `ou=teams`, còn người dùng nằm trong `ou=people`. Các thuộc tính `member` tham chiếu đến DN của người dùng; chúng **không biến người dùng thành con của entry nhóm**. Với `groupOfNames`, schema thường đòi ít nhất một `member` khi tạo entry.

## 5. Schema và quy tắc đặt tên trong cây

**Schema LDAP** mô tả `attributeType`, `objectClass`, matching rule và các ràng buộc khác. Một entry có DN đúng về mặt cú pháp vẫn có thể bị directory từ chối nếu không hợp lệ theo schema.

Chẳng hạn, các entry `ou=people` và `ou=teams` có thể có:

```ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
```

Trong khi đó, entry người dùng dùng `inetOrgPerson`, và entry nhóm dùng `groupOfNames`. Mỗi loại có tập thuộc tính bắt buộc và được phép khác nhau.

Ở một số directory, các cấu trúc schema như **name forms** và **DIT structure rules**, hoặc cấu hình riêng của server, còn có thể giới hạn loại RDN hay loại entry nào được phép nằm dưới một parent cụ thể. Tài liệu ứng dụng phải phù hợp với directory đang dùng; không nên suy ra rằng mọi LDAP server đều áp dụng chính sách cây như nhau.

Một số yếu tố thiết kế DIT cần cân nhắc:

| Yếu tố | Câu hỏi thiết kế |
| --- | --- |
| RDN | Sử dụng `uid`, `cn` hay thuộc tính nào đủ ổn định, dễ đảm bảo duy nhất trong cùng cha? |
| Container | Phân nhánh theo người dùng/nhóm/dịch vụ hay theo khu vực/phòng ban? |
| Search scope | Ứng dụng thường tìm dưới một OU hay cần quét toàn subtree? |
| ACL/quyền | Tài khoản ứng dụng được đọc/ghi nhánh nào, có quyền đổi DN hoặc tạo con không? |
| Thay đổi cơ cấu | Khi chuyển phòng ban, DN của người dùng có phải thay đổi không? |
| Tham chiếu DN | Nếu DN đổi, các giá trị `member`, `manager` hoặc liên kết ngoài có được cập nhật? |

## 6. Cây DIT ảnh hưởng trực tiếp đến truy vấn LDAP

Mỗi lần search có ba phần cần phân biệt: **search base**, **search scope** và **filter**. DIT quyết định entry nào nằm trong vùng có thể tìm kiếm, còn filter quyết định entry nào trong vùng đó đáp ứng điều kiện.

Giả sử cây có thêm một nhánh con:

```text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    ├── uid=minh
    └── ou=contractors
        └── uid=mai
```

Khi search base là `ou=people,dc=example,dc=org`:

| Search scope | Entry được xét (trước khi áp filter) |
| --- | --- |
| `OBJECT` / `BASE` | Chỉ `ou=people` |
| `ONELEVEL` | Con trực tiếp: `uid=lan`, `uid=minh`, `ou=contractors` |
| `SUBTREE` | `ou=people` cùng mọi hậu duệ: Lan, Minh, Contractors, Mai |

Lưu ý: các ví dụ liệt kê theo RDN cho gọn; DN thực tế vẫn gồm toàn bộ tổ tiên tới suffix. Nếu dùng filter `(objectClass=inetOrgPerson)`, các entry kiểu container sẽ không khớp. Với `ONELEVEL`, `uid=mai` nằm sâu hai cấp **không thể được trả về** dù filter khớp hoàn toàn.

### 6.1. Tình huống truy vấn thực tế

Mục tiêu: tìm người dùng tên Lan đang nằm trực tiếp trong nhánh `ou=people`.

```text
Search base : ou=people,dc=example,dc=org
Search scope: ONELEVEL
Filter      : (&(objectClass=inetOrgPerson)(uid=lan))
```

Với cùng filter nhưng scope `SUBTREE`, nếu có một `uid=lan` nữa trong `ou=contractors`, cả hai entry có thể cùng khớp. Đó là lý do **filter `(uid=lan)` một mình không đảm bảo chỉ có một kết quả** trên toàn DIT: tính duy nhất DN được xác định trong cấu trúc cây, còn tính duy nhất của thuộc tính `uid` trên toàn doanh nghiệp phụ thuộc chính sách riêng.

### 6.2. Search bằng `LdapTemplate`

Ví dụ Spring LDAP (thường được dùng dưới Spring Data LDAP) với context base là `dc=example,dc=org`:

```java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class DirectorySearchService {
    private final LdapTemplate ldapTemplate;

    public DirectorySearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> directPeopleNames() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchControls.ONELEVEL_SCOPE)
                .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(query,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());
    }
}
```

Trong cấu hình giả định trên, `.base("ou=people")` tương đối so với context base `dc=example,dc=org`. Thay `ONELEVEL_SCOPE` bằng `SUBTREE_SCOPE` để tìm cả các entry người dùng ở các OU con. Thư viện xử lý kết nối và thực hiện search, nhưng **không tự suy đoán** phạm vi DIT mà nghiệp vụ mong muốn.

## 7. Ánh xạ DN và entry thành entity Spring Data LDAP

Trong Spring Data LDAP, một entity thường được đánh dấu `@Entry`, thuộc tính LDAP được ánh xạ bằng `@Attribute`, và trường DN được biểu diễn qua `@Id` có kiểu `javax.naming.Name`:

```java
import java.util.List;
import javax.naming.Name;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=people", objectClasses = {"inetOrgPerson"})
public class Person {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Constructor phù hợp, getter/setter hoặc cơ chế truy cập entity.
}

interface PersonRepository extends LdapRepository<Person> {
    List<Person> findByUid(String uid);
}
```

`@Entry(base = "ou=people")` khai báo nhánh cơ sở cho loại entity này trong ngữ cảnh cấu hình LDAP, còn `@Id Name dn` nhận diện entry cụ thể. Một repository theo `uid` có thể trả về nhiều entry nếu `uid` lặp lại ở các OU con và phạm vi truy vấn cho phép. Ví dụ dùng `List<Person>` để không giả định `uid` duy nhất toàn cây; cách dùng kiểu trả về đơn hoặc `Optional` cần phù hợp với tính duy nhất thực tế và khả năng phiên bản Spring Data LDAP sử dụng.

**Phân biệt hai loại mapping:**

- `@Attribute(name = "uid")` ánh xạ **giá trị thuộc tính LDAP** sang field Java.
- `@Id Name dn` ánh xạ **DN của cả entry**, bao gồm vị trí của nó trong DIT.

`uid` có thể là thuộc tính nghiệp vụ và cũng được dùng làm RDN, nhưng nó **không thay thế** DN đầy đủ. Để biểu diễn RDN rõ ràng trong các thao tác tạo/cập nhật, Spring LDAP ODM còn có `@DnAttribute`; chỉ sử dụng khi hiểu cách field đó được đồng bộ với DN và quy tắc đặt tên của entity.

### 7.1. Dựng DN bằng API thay vì nối chuỗi

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public Name personDn(String uid) {
    return LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();
}
```

Nếu `LdapContextSource` đã cấu hình base `dc=example,dc=org`, tên tương đối trả về biểu diễn entry `uid=<giá trị>,ou=people` dưới base đó. `LdapNameBuilder` xử lý việc escape giá trị RDN theo cú pháp DN, tránh lỗi khi `uid` có dấu phẩy hoặc ký tự cần mã hóa. Nếu muốn dựng một DN tuyệt đối ngoài ngữ cảnh cấu hình, hãy biểu diễn đủ các RDN tương ứng và kiểm tra yêu cầu API được gọi.

Không dùng code nối chuỗi như sau với dữ liệu người dùng:

```java
// Không nên làm: uid có thể chứa dấu phẩy, dấu cộng, dấu bằng...
String dn = "uid=" + userUid + ",ou=people,dc=example,dc=org";
```

Lưu ý: escape **DN/RDN** khác escape **filter**; để tìm `(uid=...)` an toàn hãy dùng `LdapQueryBuilder` hoặc builder filter, thay vì đưa trực tiếp chuỗi DN vào biểu thức filter.

## 8. Đổi tên và di chuyển entry làm thay đổi cấu trúc DIT

Khi đổi RDN hoặc chuyển sang một parent khác, **DN của entry thay đổi**, dù các thuộc tính nghiệp vụ vẫn có thể giữ nguyên.

Ví dụ:

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan,ou=staff,dc=example,dc=org
```

Đây là thay đổi parent. Một ví dụ đổi RDN ngay trong cùng parent:

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan.nguyen,ou=people,dc=example,dc=org
```

LDAP có thao tác **Modify DN** để đổi tên entry; việc di chuyển sang parent mới hoặc đổi RDN được hỗ trợ đến đâu phụ thuộc khả năng, cấu hình và quyền của server. Spring LDAP có các API rename tương ứng, nhưng phải kiểm tra hành vi của directory đích, nhất là di chuyển qua các naming context hoặc qua server khác.

Cần lưu ý thêm:

1. **Cha mới phải tồn tại** và tài khoản thực hiện phải có quyền sửa cây/đổi tên cần thiết.
2. **RDN mới phải duy nhất trong cha mới** và phù hợp với schema/naming rule.
3. **Hậu duệ có thể bị ảnh hưởng về tên**: nếu cả nhánh được di chuyển, DN đầy đủ của các entry bên dưới cũng thay đổi theo vị trí cây.
4. **Các tham chiếu DN** (`member`, `manager`, cấu hình ngoài ứng dụng, cache, ACL) có thể cần cập nhật. Một số server hỗ trợ duy trì tham chiếu tự động, nhưng không được mặc định có.
5. **RDN và thuộc tính** cần nhất quán theo lựa chọn thao tác/setting của server (ví dụ giữ hay bỏ giá trị RDN cũ khi rename).

Đối với ứng dụng Spring Data LDAP, DN đóng vai trò nhận diện entity. Khi DN đổi, các lần `findById`/`lookup` với tên cũ có thể không còn tìm thấy entry. Vì vậy, nên chọn RDN đủ ổn định, thiết kế kế hoạch thay đổi DN và kiểm thử các liên kết tham chiếu trước khi thay đổi cấu trúc DIT thật.

## 9. Những sai lầm thường gặp

| Nhầm lẫn | Thực tế | Cách kiểm tra |
| --- | --- | --- |
| `(uid=lan)` định danh duy nhất entry | Filter có thể khớp nhiều entry ở các nhánh khác nhau | Xác định search base/scope, kiểm tra DN đầy đủ |
| `ou=people` luôn là thuộc tính của mọi entry dưới nó | `ou=people` là RDN của container; con không tự động thừa hưởng thuộc tính đó | Xem attribute của từng entry, không suy từ tên nhánh |
| Đưa DN đúng thì có thể tạo con dù cha chưa tồn tại | Thông thường parent entry phải tồn tại và cho phép có con | Kiểm tra naming context, parent, schema, quyền |
| `ONELEVEL` tìm cả các cấp cháu | `ONELEVEL` chỉ xét entry con trực tiếp | So sánh kết quả với `SUBTREE` |
| DN là đường dẫn hệ thống tập tin | DN theo RFC 4514 có quy tắc escape và thứ tự RDN riêng | Dùng `LdapName`/`LdapNameBuilder` |
| Chuyển entry giữa OU chỉ cần sửa thuộc tính `ou` | Thay đổi vị trí cây là đổi DN, cần Modify DN hoặc cơ chế server phù hợp | Kiểm tra DN trước và sau thay đổi |
| Xóa OU sẽ tự xóa toàn bộ người dùng bên dưới | Server thường từ chối xóa entry không phải lá | Lập kế hoạch xóa hậu duệ, kiểm tra quyền |
| Cây DIT đồng nghĩa sơ đồ tổ chức công ty | Quan hệ báo cáo/quyền nhóm thường cần thuộc tính tham chiếu riêng | Kiểm tra `manager`, `member`, schema và chính sách |

## 10. Bài thực hành tự kiểm tra

Xét DIT sau:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── ou=contractors
│       └── uid=mai
└── ou=groups
    └── cn=backend
```

**Bài 1.** Viết DN đầy đủ của `uid=mai`, xác định parent, ancestor và sibling của entry này.

*Đáp án gợi ý:* DN là `uid=mai,ou=contractors,ou=people,dc=example,dc=org`. Parent là `ou=contractors,ou=people,dc=example,dc=org`; ancestor khác gồm `ou=people,dc=example,dc=org` và `dc=example,dc=org`. Trong cây được cho, `uid=mai` không có sibling được liệt kê.

**Bài 2.** Tìm các `inetOrgPerson` dưới `ou=people` bằng scope `ONELEVEL` và `SUBTREE`. Với cây có `uid=lan` và `uid=mai` là `inetOrgPerson`, kết quả khác nhau thế nào?

*Đáp án gợi ý:* `ONELEVEL` thấy `uid=lan` nhưng không thấy `uid=mai`; `SUBTREE` thấy cả hai. Container `ou=contractors` không khớp `objectClass=inetOrgPerson`.

**Bài 3.** Có hai `uid=lan` tại `ou=people` và `ou=contractors`. Chúng có vi phạm tính duy nhất của LDAP DN không?

*Đáp án gợi ý:* Không, vì hai DN đầy đủ khác nhau. Chính sách nghiệp vụ có thể vẫn yêu cầu `uid` duy nhất trên toàn hệ thống và phải kiểm tra riêng.

**Bài 4.** Nhóm `cn=backend` có thuộc tính `member` trỏ tới `uid=lan,ou=people,...`. Lan có phải con của `cn=backend` trong DIT không?

*Đáp án gợi ý:* Không. Đó là quan hệ thành viên được biểu diễn bằng tham chiếu DN; parent của Lan vẫn là `ou=people,...`.

**Bài 5.** Nếu muốn chuyển `uid=mai` lên trực tiếp dưới `ou=people`, bạn cần xem xét những gì?

*Đáp án gợi ý:* Parent mới, DN mới, RDN trùng hay không, quyền Modify DN, hỗ trợ của server và các tham chiếu DN phụ thuộc vào tên cũ.

## 11. Ghi nhớ

- **DIT** là cây logic gồm các entry; mỗi entry có thuộc tính và một **DN** định danh vị trí trong cây.
- **RDN** là tên tương đối dưới cha; **DN** là chuỗi các RDN từ entry hiện tại đến tổ tiên, thể hiện quan hệ cha – con.
- Search theo LDAP phụ thuộc **base + scope + filter**: đúng filter nhưng sai nhánh hoặc scope vẫn cho kết quả không như mong đợi.
- Schema, `objectClass` và quyền truy cập quy định entry/thuộc tính/thao tác nào hợp lệ; cấu trúc DIT không tự biểu diễn mọi quan hệ nghiệp vụ.
- Trong **Spring Data LDAP**, `@Id Name dn` biểu diễn danh tính theo cây, còn `@Attribute` biểu diễn dữ liệu. Dùng API DN của JNDI/Spring LDAP để xây tên an toàn và lưu ý hậu quả của việc đổi DN.

**Tài liệu tham khảo:**

- RFC 4512 — *LDAP: Directory Information Models* (entry, DIT, naming context, schema): https://www.rfc-editor.org/rfc/rfc4512
- RFC 4514 — *LDAP: String Representation of Distinguished Names*: https://www.rfc-editor.org/rfc/rfc4514
- RFC 4511 — *LDAP: The Protocol* (search scope, Modify DN): https://www.rfc-editor.org/rfc/rfc4511
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring Data LDAP Reference Documentation](https://docs.spring.io/spring-data/ldap/reference/)
