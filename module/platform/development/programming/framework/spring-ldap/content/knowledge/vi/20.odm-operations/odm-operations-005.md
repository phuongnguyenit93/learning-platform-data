# Delete object và kiểm tra DN trong Spring LDAP ODM

Khi ứng dụng có một đối tượng Java được ánh xạ từ LDAP, thao tác **xóa object** trông đơn giản: gọi `ldapTemplate.delete(person)`. Tuy nhiên, thao tác LDAP Delete tác động lên **entry tại một Distinguished Name (DN)**, không phải một “dòng dữ liệu có khóa chính” như trong ORM quan hệ. Một đối tượng Java có thể chứa DN cũ, DN do client gán sai hoặc DN được tính từ các trường định danh đã thay đổi. Nếu ứng dụng không kiểm tra DN và phạm vi cho phép, một lệnh xóa rất ngắn có thể xóa sai tài khoản.

Bài học thuộc chương **ODM operations** của **SPRING_LDAP**. Người học sẽ thực hiện `delete(Object)` trong Object-Directory Mapping (ODM), phân biệt với `unbind(Name)`, đọc và xác minh `@Id`, đối chiếu DN tương đối với base của `ContextSource`, xử lý entry đã bị đổi tên/di chuyển, bảo vệ thao tác xóa và thiết kế kiểm thử. Các ví dụ dùng Spring LDAP với LDAP server thử nghiệm, có kết nối an toàn và quyền truy cập thích hợp.

## 1. Xóa object bằng ODM thực chất xóa điều gì?

Giả sử thư mục có entry:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
mail: an@example.org
~~~

ODM ánh xạ entry đó thành `PersonEntry`. Khi gọi:

~~~java
ldapTemplate.delete(person);
~~~

Spring LDAP dùng **metadata ODM** để xác định DN của entry rồi yêu cầu server thực hiện **LDAP Delete**. Lệnh xóa là thao tác trên entry trong Directory Information Tree (DIT), không phải xóa riêng các trường Java, không tự xóa mọi tham chiếu nhóm và không mặc định xóa toàn bộ nhánh có con.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu xóa tài khoản"] --> B["Xác thực quyền nghiệp vụ"]
    B --> C["Xây DN từ khóa đáng tin cậy"]
    C --> D["Kiểm tra DN thuộc phạm vi cho phép"]
    D --> E["Đọc entry thực tế bằng findByDn"]
    E --> F["Đối chiếu danh tính / objectClass"]
    F --> G["LdapTemplate.delete(entity)"]
    G --> H{"LDAP Delete thành công?"}
    H -->|Có| I["Kiểm tra trạng thái, audit"]
    H -->|Không| J["Phân loại lỗi, không coi là đã xóa"]
~~~

**Điểm trọng tâm:** `delete(Object)` không tự trở thành cơ chế authorization hoặc kiểm tra mọi thuộc tính tại thời điểm xóa. Hành vi của server phụ thuộc DN, quyền và tình trạng entry khi yêu cầu đến nơi.

### So sánh các API liên quan

| API | Cần đầu vào | Ý nghĩa |
|---|---|---|
| `ldapTemplate.delete(person)` | Object có metadata `@Entry`, `@Id` và/hoặc `@DnAttribute` | Xóa entry mà ODM xác định từ object |
| `ldapTemplate.unbind(relativeDn)` | DN tương đối của entry | Xóa entry tại DN, không cần object ODM |
| `ldapTemplate.unbind(relativeDn, true)` | DN và cờ recursive | Xóa nhánh đệ quy nếu phiên bản hỗ trợ; nguy hiểm nếu DN sai |
| `ldapTemplate.findByDn(dn, PersonEntry.class)` | DN và kiểu ODM | Đọc entry để xác minh trước/sau thao tác |
| `ldapTemplate.update(person)` | Object ODM | Sửa entry; không phải delete |
| `ldapTemplate.create(person)` | Object ODM mới | Thêm entry; không phải delete |

**Không nhầm lẫn** `ldapTemplate.delete(Object)` với LDAP **Bind** dùng để xác thực. Cũng không nhầm với phương thức `unbind(Name)` của Spring LDAP: tên “unbind” trong API thao tác thư mục này là xóa entry, khác với *LDAP protocol Unbind* kết thúc một phiên LDAP.

## 2. Điều kiện để một class được dùng với delete(Object)

Theo Spring LDAP ODM, entity cần có các annotation từ `org.springframework.ldap.odm.annotations`, đặc biệt:

- `@Entry`: mô tả các object class LDAP mà domain object đại diện và có thể khai báo `base`.
- `@Id`: đánh dấu trường mang DN, kiểu `javax.naming.Name` hoặc kiểu tương thích theo hợp đồng ODM.
- `@Attribute`: ánh xạ các thuộc tính như `uid`, `cn`, `sn` vào trường Java.
- `@DnAttribute`: cho phép ODM tính DN từ các thành phần RDN khi thiết kế entity theo cách đó.
- `@Transient`: loại trừ trường chỉ phục vụ ứng dụng khỏi ánh xạ LDAP.

Ví dụ entity tài khoản:

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
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public PersonEntry() {
    }

    public Name getDn() {
        return dn;
    }

    public void setDn(Name dn) {
        this.dn = dn;
    }

    public String getUid() {
        return uid;
    }

    public void setUid(String uid) {
        this.uid = uid;
    }

    public String getCommonName() {
        return commonName;
    }

    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() {
        return surname;
    }

    public void setSurname(String surname) {
        this.surname = surname;
    }
}
~~~

Đây là object mapping dành cho entry `inetOrgPerson`. Các lớp LDAP `top`, `person`, `organizationalPerson` và `inetOrgPerson` **khác** với lớp Java `PersonEntry`. Trong LDAP, DN là tên định danh vị trí của entry; `uid` chỉ là một attribute có thể được dùng làm RDN.

Tại thời điểm xóa, **trường `dn` quan trọng hơn việc tên người dùng đang hiển thị là gì**. Nếu `dn` trỏ đến entry khác, thao tác có thể nhắm sai đối tượng.

### @Id và @DnAttribute quyết định DN ra sao?

Tài liệu API của `LdapTemplate.delete(Object)` mô tả hai đường:

1. **`@Id` đã có giá trị:** dùng DN từ trường được đánh dấu `@Id` để xác định entry.
2. **`@Id` chưa có giá trị:** ODM thử **tính DN** từ những trường `@DnAttribute` được cấu hình để tính tên.

Ví dụ mẫu dùng `@DnAttribute`:

~~~java
import org.springframework.ldap.odm.annotations.DnAttribute;

@Attribute(name = "uid")
@DnAttribute(value = "uid", index = 0)
private String uid;
~~~

Đây chỉ là **một trường trong class**; entity hoàn chỉnh vẫn cần `@Entry` và `@Id`. Với `@Entry(base="ou=people")`, metadata DN phù hợp có thể cho phép ODM tính `uid=an,ou=people` khi `@Id` chưa được gán.

Trong nghiệp vụ xóa, **không nên để các trường RDN do HTTP request tùy ý cung cấp trở thành DN xóa mà không kiểm tra**. Thực hành an toàn hơn là lấy khóa nghiệp vụ đã được xác thực, dựng DN dưới nhánh allowlist rồi đọc lại entry từ LDAP trước khi gọi `delete`.

## 3. Kiểm tra DN: relative DN, full DN và base của ContextSource

Giả sử:

~~~text
ContextSource base: dc=example,dc=org
@Entry.base:        ou=people
Entry full DN:      uid=an,ou=people,dc=example,dc=org
Relative DN:        uid=an,ou=people
RDN cuối:           uid=an
~~~

Một số điểm dễ nhầm:

| Thành phần | Vai trò | Chú ý |
|---|---|---|
| `ContextSource.base` | Base DN của kết nối Spring LDAP | Nhiều thao tác của `LdapTemplate` nhận DN tương đối với base này |
| `@Entry.base` | Base dùng trong metadata ODM, đặc biệt khi tính DN từ `@DnAttribute` | Không phải lệnh tạo container |
| `@Id Name dn` | DN của entry đang được quản lý | Nếu được gán tường minh, ODM dùng tên này |
| `uid` trong `@Attribute` | Giá trị thuộc tính | Không tự bảo đảm tính duy nhất trên toàn DIT |
| `uid=an` trong DN | Một RDN | Không thay thế đầy đủ đường dẫn parent |

Một DN đầy đủ được thêm vào `ContextSource.base` lần nữa có thể khiến ứng dụng tìm sai nhánh. Ngược lại, chỉ dùng `uid=an` khi account thực nằm dưới `ou=people` cũng có thể trỏ sai DN.

Trong ví dụ, nên dựng:

~~~java
Name personDn = LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", "an")
        .build();

// Kết quả tương ứng: uid=an,ou=people
// ContextSource sẽ làm việc trong base dc=example,dc=org.
~~~

Không dựa vào phương thức `String.replace`, `split(",")` hay ghép `uid + ",ou=people"` khi dựng DN từ input: ký tự dấu phẩy, dấu cộng, dấu bằng, khoảng trắng và các escape sequence có ý nghĩa theo RFC 4514.

### DN là tên có cấu trúc, không phải chuỗi kết thúc bằng hậu tố

Giả sử chỉ được phép xóa người dùng nằm dưới `ou=people`. Việc kiểm tra:

~~~java
if (dn.toString().endsWith("ou=people")) {
    // Chưa đủ an toàn.
}
~~~

không phải kiểm tra quan hệ DN đúng nghĩa. Cách biểu diễn text có thể khác nhau về escape, khoảng trắng hoặc phân tách RDN; bản thân quy tắc string suffix cũng không xác thực phạm vi cấp con.

**Sử dụng `LdapName`/`Name`** và so sánh thành phần RDN. Đừng xem DN như đường dẫn hệ điều hành hay URL.

## 4. Thiết kế xóa tài khoản theo DN tin cậy

Ví dụ một service chỉ được xóa **entry người dùng trực tiếp dưới `ou=people`**. Nó không nhận DN tùy ý từ client; chỉ nhận UID đã được kiểm tra bởi tầng nghiệp vụ.

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonDeletionService {
    private final LdapTemplate ldapTemplate;

    public PersonDeletionService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void deleteDirectPerson(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid is required");
        }

        Name targetDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", uid)
                .build();

        // Lấy entry thực từ server thay vì tin object do client truyền.
        PersonEntry current =
                ldapTemplate.findByDn(targetDn, PersonEntry.class);

        if (current == null || current.getDn() == null) {
            throw new IllegalStateException("Person not found");
        }

        if (!targetDn.equals(current.getDn())) {
            throw new IllegalStateException("Unexpected LDAP DN");
        }

        if (!uid.equals(current.getUid())) {
            throw new IllegalStateException("Unexpected LDAP identity");
        }

        ldapTemplate.delete(current);
    }
}
~~~

**Ý nghĩa của các bước:**

1. Tầng service đã phải **xác thực người gọi, kiểm tra quyền xóa** và bảo đảm UID thuộc nghiệp vụ.
2. `LdapNameBuilder` dựng DN dựa trên **parent cố định**, tránh việc client gửi nguyên DN của một OU khác.
3. `findByDn` đọc object theo metadata `@Entry`/`@Id`, giúp kiểm tra entry thực.
4. So sánh `targetDn` với DN đọc được để phát hiện mapping/base bất thường.
5. So sánh UID của entry với UID yêu cầu; nếu cần độ chắc chắn cao hơn, có thể đối chiếu định danh ổn định của server.
6. `delete(current)` gửi thao tác xóa entry mà `@Id` đang chỉ tới.

**Đây là mẫu minh họa, không phải một cơ chế đảm bảo xóa có điều kiện nguyên tử.** Giữa `findByDn` và `delete`, entry có thể bị xóa hoặc thay thế bởi tiến trình khác. Khi rủi ro này quan trọng, cần cơ chế đồng bộ nghiệp vụ hoặc điều kiện kiểm tra phía server (nếu hỗ trợ); chỉ đọc trước rồi xóa sau là kiểm tra *best effort*.

### Khi nào không nên dùng delete(Object)?

Nếu ứng dụng chỉ có DN chính xác mà không cần ánh xạ object, `ldapTemplate.unbind(targetDn)` thể hiện thao tác xóa entry lá trực tiếp. Ngược lại, khi đã có đối tượng ODM được lấy từ LDAP và muốn giữ mô hình CRUD theo entity, `ldapTemplate.delete(person)` phù hợp hơn.

**Không dùng `delete(Object)` như một lối tắt để bỏ kiểm tra DN.** ODM chỉ hỗ trợ ánh xạ, không thay thế logic phân quyền hoặc whitelist parent.

## 5. Kiểm tra DN bằng LdapName và ranh giới allowlist

Trong một repository có nhiều nhánh, cần bảo đảm target DN nằm **bên dưới một base được phép**, và không bao giờ là chính base đó. Với bài toán chỉ xóa **các tài khoản con trực tiếp**, còn phải giới hạn thêm đúng một cấp.

Ví dụ helper đọc `Name` và kiểm tra cấu trúc:

~~~java
import javax.naming.Name;
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;

public final class DnGuards {
    private static final LdapName ALLOWED_PARENT;

    static {
        try {
            // DN tương đối với ContextSource base dc=example,dc=org.
            ALLOWED_PARENT = new LdapName("ou=people");
        } catch (InvalidNameException impossible) {
            throw new ExceptionInInitializerError(impossible);
        }
    }

    private DnGuards() {
    }

    public static void requireDirectChild(Name rawDn) {
        if (rawDn == null) {
            throw new IllegalArgumentException("DN is required");
        }

        final LdapName dn;
        try {
            dn = new LdapName(rawDn.toString());
        } catch (InvalidNameException invalid) {
            throw new IllegalArgumentException("Invalid LDAP DN", invalid);
        }

        // LdapName dùng cấu trúc RDN (gốc đứng ở đầu danh sách RDN).
        if (!dn.startsWith(ALLOWED_PARENT)
                || dn.size() != ALLOWED_PARENT.size() + 1) {
            throw new IllegalArgumentException("DN outside allowed OU");
        }

        // Ngoài kiểm tra cấu trúc còn phải xác minh RDN là uid,
        // objectClass và danh tính của entry trong LDAP.
        if (!dn.getRdn(dn.size() - 1).getType().equalsIgnoreCase("uid")) {
            throw new IllegalArgumentException("Expected uid RDN");
        }
    }
}
~~~

**Giải thích:** Với `LdapName`, các thành phần RDN được xử lý theo quy tắc của DN, khác với việc cắt chuỗi ở dấu phẩy. `startsWith(ALLOWED_PARENT)` kiểm tra quan hệ tiền tố **theo thứ tự nội bộ RDN của `Name`**, nơi base nằm ở đầu danh sách. Điều kiện `size() == parent.size() + 1` chỉ cho phép **con trực tiếp**, không cho xóa OU gốc hoặc entry nằm ở mức cháu.

Lưu ý quan trọng về bảo mật:

- Đây là **hàng rào phạm vi** trong ứng dụng, không phải thay thế ACL trên LDAP server.
- Nếu phải cho phép nhiều OU con, hãy thiết kế rule rõ ràng và chỉ cho xóa các object class dự kiến.
- Không dùng duy nhất hậu tố chuỗi `endsWith("ou=people")` vì có thể sai ngữ nghĩa DN.
- Nếu `ContextSource` không dùng base ở ví dụ, `ALLOWED_PARENT` cũng phải được tính trong đúng hệ tọa độ DN.
- Các RDN đa trị hoặc dữ liệu đặc thù cần được ràng buộc theo schema và nghiệp vụ thực tế.

Trong code xóa tài khoản, cách **cố định parent và dựng DN bằng UID** thường đơn giản và an toàn hơn API chấp nhận chuỗi DN tùy ý. Guard DN như trên hữu ích khi có nhiều nguồn gọi hoặc dữ liệu DN lấy từ bên ngoài.

## 6. @Id đã cũ hoặc không hợp lệ: vì sao phải đề phòng?

Xét vòng đời một entity:

~~~text
T0: Đọc uid=an,ou=people               -> person.dn = oldDn
T1: Quản trị viên move sang ou=alumni    -> entry DN mới
T2: Ứng dụng gọi delete(person)          -> vẫn mang oldDn
~~~

Vấn đề ở đây:

- Entry tại DN cũ có thể **không còn tồn tại**; delete sẽ thất bại.
- Một entry **khác** có thể xuất hiện tại DN cũ sau thời điểm T1, nếu server và chính sách cho phép.
- Nếu ứng dụng giữ object ODM trong cache lâu, các attribute/định danh cũng có thể đã cũ.
- Thay đổi `uid` hoặc một trường `@DnAttribute` có thể ảnh hưởng cách tính DN khi entity không có `@Id` tường minh.

**Đừng coi DN là khóa định danh bất biến qua rename/move.** Với directory có attribute ID ổn định do server cung cấp (ví dụ `entryUUID` hoặc `objectGUID` tùy sản phẩm), có thể dùng ID này để xác minh danh tính ở bước đọc trước xóa. Tuy nhiên không có một attribute ID chung được đảm bảo cho mọi LDAP server.

### Khi @Id null, ODM có thể tính sai đích nếu dữ liệu đã đổi

Tài liệu Spring LDAP mô tả rằng `delete(Object)` thử tính DN từ `@DnAttribute` nếu không có DN được đặt trong `@Id`. Điều đó tiện cho CRUD nhưng tiềm ẩn rủi ro khi giá trị định danh đến từ request chưa xác thực.

Ví dụ entity khai báo:

~~~java
@Entry(base = "ou=people",
       objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"})
public class PersonByDnAttribute {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    @DnAttribute(value = "uid", index = 0)
    private String uid;

    @Attribute(name = "cn")
    private String cn;

    @Attribute(name = "sn")
    private String sn;
}
~~~

Nếu code tạo một instance chỉ với `uid` theo user input, để `dn == null` và gọi `delete(instance)`, ODM có thể suy ra DN từ UID và `@Entry.base`. **Không nên dùng mẫu này cho endpoint xóa công khai.** Hãy dựng target DN trong phạm vi cho phép và xác minh entry thật; hoặc yêu cầu `@Id` đến từ đối tượng vừa đọc từ LDAP.

### Kiểm tra DN trước và sau delete có bảo đảm tuyệt đối không?

Không. Hai lần lookup cho biết **trạng thái tại hai thời điểm khác nhau**, nhưng không tạo transaction giữa đọc và xóa. Nếu một đối tượng khác được tạo lại tại đúng DN trong khoảng đó, thao tác có thể tác động đến object mới. Với yêu cầu rất nghiêm ngặt, cân nhắc:

- Tuân thủ quyền LDAP hạn chế ở OU đích.
- Đánh dấu trạng thái “đang xóa”, điều phối khóa ở tầng nghiệp vụ và ngừng provisioning đồng thời.
- Kiểm tra server hỗ trợ LDAP Assertion Control (RFC 4528) hoặc cơ chế CAS/transaction riêng; chỉ dùng sau khi xác nhận API và chính sách sản phẩm.
- Audit DN, ID ổn định và mã kết quả; không tự xem “lookup trước thành công” là bảo chứng nguyên tử.

## 7. Xóa entry lá khác xóa nhánh có con

LDAP Delete thông thường chỉ thành công với **entry lá** (không có entry con). Nếu entry cha còn con, kết quả có thể là `notAllowedOnNonLeaf` (**66**).

~~~text
dc=example,dc=org
└── ou=people                    [entry cha]
    ├── uid=an                   [entry lá]
    └── ou=contractors           [entry cha]
        └── uid=binh             [entry lá]
~~~

Khi `person.dn` là `uid=an,ou=people`, `delete(person)` hướng tới một entry lá. Nhưng nếu domain object đại diện `ou=contractors,ou=people`, việc xóa trực tiếp entry đó khi vẫn còn `uid=binh` sẽ bị từ chối bởi máy chủ LDAP thông thường.

| Lệnh | Trường hợp | Nhận xét |
|---|---|---|
| `ldapTemplate.delete(person)` | Entity người dùng là lá | Dùng DN của `@Id` hoặc DN tính từ metadata ODM |
| `ldapTemplate.unbind(dn)` | Xóa entry lá theo DN | Không cần domain object |
| `ldapTemplate.unbind(dn, true)` | Muốn xóa một nhánh gồm nhiều entry | Phải kiểm soát đặc biệt chặt, có nguy cơ xóa hàng loạt |
| Gọi `delete(ouEntity)` khi OU còn con | Entry không phải lá | Không được giả định ODM tự xóa toàn bộ subtree |

**Đừng thêm tùy chọn recursive chỉ để “sửa” lỗi xóa entry không phải lá** khi mục tiêu thật sự là xóa một tài khoản. Điều đó có thể che đi việc DN trỏ nhầm vào container. Hãy coi lỗi 66 là tín hiệu cần dừng và kiểm tra đối tượng.

Khi nghiệp vụ thực sự cần xóa nhánh, nên dùng một quy trình riêng: preview số entry, xác nhận root DN, bảo vệ ngoài phạm vi, dọn từng cấp theo thứ tự con trước cha hoặc dùng tính năng server hỗ trợ, đối soát và có phương án khôi phục.

## 8. Đối chiếu objectClass khi xác minh DN

Một DN đúng cú pháp và nằm trong OU cho phép **chưa đủ** để chứng minh đó là tài khoản người dùng. LDAP entry có thể là group, organizationalUnit hoặc một loại riêng của server.

Ví dụ:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
~~~

Muốn xóa một tài khoản, ứng dụng có thể xác minh:

1. Entry được đọc bằng DN đích.
2. Tập `objectClass` phản ánh loại entry được hỗ trợ, ví dụ `inetOrgPerson`.
3. Giá trị định danh như `uid` hoặc khóa ổn định phù hợp yêu cầu nghiệp vụ.
4. Object không thuộc danh sách tài khoản hệ thống/dịch vụ bị cấm xóa.
5. DN vẫn ở OU phù hợp với chính sách.
6. Người yêu cầu có quyền xóa tài khoản đó ở tầng ứng dụng.

Metadata `@Entry.objectClasses` giúp ODM nhận diện các entry phù hợp khi ánh xạ. Tuy nhiên, **không nên giả định rằng gọi `delete(Object)` sẽ tự đọc và so khớp toàn bộ tập objectClass ở server ngay trước khi xóa**. Nếu cần ràng buộc chặt, hãy thực hiện bước lookup/verify và xem xét cơ chế xóa có điều kiện của server.

Một số server có object class mở rộng hoặc operational attributes. Khi kiểm tra, cần phân biệt các class kế thừa và auxiliary classes; không yêu cầu “tập class đúng y hệt bốn chuỗi” nếu hệ thống thực tế cho phép class bổ sung hợp lệ.

## 9. Xử lý lỗi và ý nghĩa của kết quả delete(Object)

Phương thức `ldapTemplate.delete(Object)` không trả về Boolean “đã xóa”. Nếu xảy ra lỗi LDAP hoặc mapping, Spring LDAP có thể ném exception. Tùy nhà cung cấp và phiên bản, exception Java được ánh xạ khác nhau từ kết quả LDAP.

| LDAP result code | Tên | Ý nghĩa trong delete |
|---|---|---|
| **0** | `success` | Server chấp nhận thao tác xóa |
| **32** | `noSuchObject` | Entry không còn tại DN hoặc đường dẫn không tìm thấy |
| **34** | `invalidDNSyntax` | DN không đúng cú pháp |
| **50** | `insufficientAccessRights` | Danh tính bind không đủ quyền xóa |
| **53** | `unwillingToPerform` | Server từ chối vì chính sách |
| **64** | `namingViolation` | Vấn đề quy tắc đặt tên/vị trí (nếu server áp dụng) |
| **66** | `notAllowedOnNonLeaf` | Entry còn entry con |
| **80** | `other` | Lỗi khác; cần diagnostic phù hợp |

Ngoài kết quả server, còn có lỗi **mapping** ở ứng dụng:

- Class không có metadata `@Entry`/`@Id` hợp lệ.
- Đối tượng truyền vào là `null`.
- Không có `@Id` và thiếu/không hợp lệ `@DnAttribute` để tính DN.
- DN được build sai hoặc được nhập ở hệ base không đúng.
- `findByDn` không map được attribute vì schema thực tế khác model.

Không gộp mọi lỗi thành “tài khoản không tồn tại”. Nếu thiếu quyền hoặc kết nối mất, server chưa chắc đã xóa entry.

### Xóa idempotent cần định nghĩa rõ

Một số API muốn “xóa tài khoản” có nghĩa **sau khi yêu cầu, tài khoản không còn tồn tại**, kể cả trước đó đã bị xóa. Khi đó có thể coi `noSuchObject` là kết quả chấp nhận được **chỉ nếu** đã xác thực đúng DN và bảo đảm đó là trường hợp thực sự không còn entry.

Nhưng cẩn thận:

- Một số server hạn chế quyền có thể che việc tồn tại bằng phản hồi giống “không tìm thấy”.
- Timeout không cho biết request đã thực hiện hay chưa.
- Sau rename/move, entry có thể đã đi tới DN mới thay vì bị xóa.
- Nếu nghiệp vụ cần audit từng lần xóa thành công, “đã không tồn tại” là trạng thái khác với “vừa xóa”.

**Lỗi thiếu quyền, lỗi mạng và lỗi không phải lá không được coi là thành công.**

## 10. Khi delete thành công, những gì vẫn còn tồn tại?

LDAP Delete xóa entry theo DN nhưng không mặc định xử lý dữ liệu ở các hệ thống liên quan.

Ví dụ nhóm có:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
~~~

Sau khi xóa `uid=an,ou=people`:

- Attribute `member` có thể **vẫn chứa DN đã bị xóa**.
- Cache tìm kiếm, mapping principal, session và ứng dụng khác có thể còn tham chiếu cũ.
- LDAP server có thể hỗ trợ plugin referential integrity cập nhật tham chiếu tự động, nhưng đó là tính năng phụ thuộc sản phẩm/cấu hình.
- Các hệ thống audit và lưu trữ dữ liệu có chính sách lưu giữ riêng.

Vì vậy cần xác định rõ quy trình **trước và sau xóa**: gỡ quyền nhóm nếu cần, vô hiệu hóa session, xóa hoặc cập nhật cache, ghi audit và kiểm tra điều kiện lưu trữ. Tất cả không được `@Entry` hoặc `delete(Object)` tự thực hiện.

### Soft delete không phải delete(Object)

Nếu yêu cầu nghiệp vụ là “ngừng cho đăng nhập nhưng vẫn giữ dữ liệu” thì cần thao tác modify trạng thái phù hợp server hoặc di chuyển entry sang OU lưu trữ, không phải `delete(Object)`. LDAP Delete chuẩn không có cơ chế “thùng rác” thống nhất cho mọi server. Các tính năng recycle bin của một sản phẩm phải được xem xét riêng.

## 11. Quy trình an toàn: preview → xác minh → delete → đối soát

Đối với tài khoản quan trọng, nên thiết kế một workflow tách biệt:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu xóa theo UID/ID"] --> B{"Authorization hợp lệ?"}
    B -->|Không| Z["Từ chối"]
    B -->|Có| C["Dựng target DN dưới OU allowlist"]
    C --> D["Parse/validate DN và loại entry"]
    D --> E["Lookup entry hiện hành"]
    E --> F{"DN + danh tính + chính sách đúng?"}
    F -->|Không| Z
    F -->|Có| G["Kiểm tra phụ thuộc, lưu audit, xác nhận"]
    G --> H["LdapTemplate.delete(entity)"]
    H --> I{"Thao tác thành công?"}
    I -->|Không| J["Ghi lỗi và đối chiếu trạng thái thực"]
    I -->|Có| K["Readback theo DN và cập nhật phụ thuộc"]
~~~

Các bước cụ thể:

1. **Xác định actor và quyền nghiệp vụ.** Tài khoản có quyền LDAP ghi không đồng nghĩa caller API được xóa.
2. **Chọn target theo khóa nghiệp vụ đáng tin.** Không cho client đặt tùy ý `@Id`.
3. **Dựng và kiểm tra DN** dưới một OU được phép, tránh toàn bộ root của directory và OU quản trị.
4. **Đọc object hiện hành.** Nếu cần, kiểm tra objectClass, UID, định danh ổn định và trạng thái khóa.
5. **Kiểm tra tham chiếu/retention** trước khi yêu cầu thao tác phá hủy.
6. **Thực hiện delete** qua `ldapTemplate.delete(object)` hoặc `unbind(dn)` theo thiết kế.
7. **Đối soát sau thao tác**; khi lookup không tìm thấy, vẫn cần cân nhắc ACL và replication.
8. **Ghi nhận audit có kiểm soát** mà không log mật khẩu, giá trị nhạy cảm hay credential kết nối.

Không có bước nào trong workflow trên đảm bảo tính nguyên tử giữa LDAP và database khác. Nếu cần phối hợp nhiều nguồn dữ liệu, hãy thiết kế tiến trình bù trừ hoặc trạng thái trung gian phù hợp.

## 12. Kiểm tra bằng findByDn, search và lookup khác nhau ra sao?

Các lựa chọn thông thường trong Spring LDAP:

| Phương pháp | Đặc điểm | Dùng khi |
|---|---|---|
| `findByDn(dn, PersonEntry.class)` | ODM map entry theo class tại DN | Cần object đã đọc để kiểm tra rồi `delete(Object)` |
| `lookup(dn)` hoặc mapper | Đọc attribute tại DN cụ thể | Cần xem chi tiết objectClass/attribute không nằm trong model |
| `search(query, mapper)` | Tìm theo base/filter/scope, có thể nhiều entry | Chưa biết DN, cần tìm ứng viên rồi xác minh |
| `findOne(query, PersonEntry.class)` | Tìm một object phù hợp theo query | Chỉ khi điều kiện thực sự xác định được một entry duy nhất |

Nếu user nhập UID `an`, một search trên toàn bộ directory có thể tìm **nhiều** entry với cùng UID dưới những OU khác nhau. Không chọn kết quả đầu tiên rồi xóa nếu chưa xác nhận OU và DN.

Khi đã biết DN, `findByDn` hoặc lookup trực tiếp tránh sự mơ hồ của filter. Tuy nhiên, **cả hai vẫn sử dụng quyền đọc hiện tại**, vì vậy kết quả âm tính không nhất thiết chứng minh entry vật lý không tồn tại nếu ACL ẩn dữ liệu.

### Ví dụ filter dùng để tìm ứng viên trước khi xóa

~~~java
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery q = query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uid);

List<PersonEntry> matches =
        ldapTemplate.find(q, PersonEntry.class);

if (matches.size() != 1) {
    throw new IllegalStateException(
            "Expected exactly one authorized LDAP person");
}
~~~

Sau đó **vẫn cần** kiểm tra DN của phần tử trả về nằm dưới parent được phép, đặc biệt nếu quyền xóa bị giới hạn đến một OU cụ thể. Filter được xây bằng query builder giúp escape giá trị, nhưng **escape không thay thế authorization**.

## 13. Xóa object khi có concurrent rename, delete hoặc tạo lại

Ba tình huống phổ biến:

| Sự kiện đồng thời | Nguy cơ | Xử lý phù hợp |
|---|---|---|
| Tiến trình A đọc `uid=an`, tiến trình B xóa trước | A gặp `noSuchObject` khi delete | Xử lý idempotency theo chính sách, đọc lại nếu cần |
| A đọc DN cũ, B move entry sang OU khác | A xóa DN cũ có thể thất bại | Không tự truy tìm toàn cây rồi xóa bất cứ đối tượng cùng UID nào |
| A đọc entry, B xóa và tạo entry khác cùng DN | A có thể xóa entry mới nếu chỉ dựa DN | Dùng khóa/định danh ổn định, assertion nếu server hỗ trợ hoặc điều phối nghiệp vụ |

**Tìm rồi xóa theo DN là chuỗi hai thao tác**, không phải transaction. Không có cơ chế optimistic locking đa server thống nhất chỉ nhờ `@Id`. Một số LDAP server hỗ trợ assertion control để buộc điều kiện dữ liệu ngay tại thời điểm delete; nếu yêu cầu mức an toàn đó, cần chọn API/kết nối và xác minh control thực tế.

Đối với tài khoản được quản lý bởi nhiều hệ thống, phương án an toàn có thể là **disable và chờ quy trình đối soát** trước khi xóa vĩnh viễn. Đây là quyết định nghiệp vụ tùy chính sách lưu giữ.

## 14. Kiểm thử delete(Object) và guard DN

Nên chạy trên môi trường LDAP cô lập, có schema và ACL phù hợp. Tạo dữ liệu test rõ ràng và bảo đảm cleanup không xóa ngoài nhánh test.

| Kịch bản | Dữ liệu đầu vào | Kết quả kỳ vọng |
|---|---|---|
| **Xóa entry lá hợp lệ** | PersonEntry có `@Id` đúng | Xóa thành công; DN cũ không còn |
| **@Id null, thiếu @DnAttribute** | Object ODM không tính được DN | Lỗi xác định DN, không gửi xóa bừa |
| **DN ngoài allowlist** | Entry trong `ou=admins` | Ứng dụng từ chối trước khi gọi LDAP |
| **DN trỏ đến OU gốc** | `ou=people` | Guard không cho xóa |
| **DN con nhiều cấp khi chỉ cho direct child** | `uid=an,ou=team,ou=people` | Guard từ chối do số cấp RDN |
| **Entry không tồn tại** | DN hợp lệ nhưng không có object | Xử lý `noSuchObject`/readback theo chính sách |
| **Entry không phải lá** | OrganizationalUnit có con | Lỗi `notAllowedOnNonLeaf`, không xóa cả nhánh |
| **DN tạo từ UID có ký tự đặc biệt** | Ví dụ UID chứa dấu phẩy nếu chính sách cho phép | RDN được escape đúng, không trỏ sai entry |
| **DN cũ sau move** | Object cache giữ oldDn | Không tự xóa ở vị trí khác dựa trên UID |
| **Trùng DN do delete + re-create** | Hai tiến trình cùng thao tác | Xác định rủi ro race; dùng cơ chế bảo vệ phù hợp |
| **Thiếu quyền LDAP** | Tài khoản bind không có delete | Không xem lỗi thành thành công |
| **Mất kết nối giữa lệnh** | Timeout sau khi gửi delete | Đọc lại trạng thái, không giả định chắc đã xóa hay thất bại |
| **Nhóm giữ DN cũ** | `member` trỏ tới person đã xóa | Phát hiện/cập nhật tham chiếu theo chính sách |

**Mock test** có thể xác minh rằng `ldapTemplate.delete()` chỉ được gọi sau khi guard đạt và object đã được kiểm tra. **Integration test** trên LDAP server mới kiểm tra được ACL, result code, schema và các tình huống delete thực.

### Bài tập tình huống

Giả sử hệ thống chỉ được phép xóa nhân viên trực tiếp trong:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=mai
│   └── ou=contractors
│       └── uid=binh
└── ou=admins
    └── uid=operator
~~~

**Yêu cầu:**

1. Cho biết entry nào được guard “con trực tiếp của `ou=people`” cho phép.
2. Vì sao không được kiểm tra bằng `dn.toString().endsWith("dc=example,dc=org")`?
3. Nếu `PersonEntry` có `@Id = uid=mai,ou=people`, lệnh ODM nào thực hiện xóa?
4. Nếu `@Id` trống nhưng có `@DnAttribute` cho UID, ODM làm gì?
5. Nếu entry bị move sang `ou=alumni` sau khi được đọc, xóa theo DN cũ sẽ có vấn đề nào?
6. Nếu `uid=mai` có trong `member` của nhóm, kết quả sau xóa phải được kiểm tra ra sao?

**Gợi ý đáp án:**

- `uid=mai,ou=people` là con trực tiếp nên hợp lệ theo guard. `uid=binh,ou=contractors,ou=people` không phải con trực tiếp; `uid=operator,ou=admins` nằm ngoài phạm vi.
- Hậu tố miền chỉ nói entry thuộc một vùng rất rộng; nó không chứng minh nằm trực tiếp dưới OU được phép. Ngoài ra so sánh chuỗi bỏ qua ngữ nghĩa RDN và escape.
- Gọi `ldapTemplate.delete(person)` sau khi quyền nghiệp vụ, DN và định danh được xác minh.
- Khi `@Id` chưa có, ODM **thử tính DN** từ những field `@DnAttribute` đủ metadata. Không nên dựa trên input không tin cậy để xóa.
- DN cũ có thể không còn hoặc có thể được dùng lại cho object khác; phải xác minh trạng thái/danh tính, không xóa theo phỏng đoán.
- Phải kiểm tra thành viên nhóm, plugin referential integrity (nếu có) và cập nhật các tham chiếu cần thiết.

## 15. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “`delete(Object)` tìm entry bằng mọi field của object.” | ODM xác định DN từ `@Id` hoặc `@DnAttribute`; không mặc định đối chiếu toàn bộ field. |
| “`@Id` chính là UID.” | `@Id` là DN có cấu trúc; UID là attribute và có thể làm một RDN. |
| “`@Entry.base` tự tạo parent còn thiếu.” | Base là metadata về vị trí, không thực hiện LDAP Add. |
| “Có đối tượng Java nên không cần xác minh DN.” | DN stale/sai có thể gây xóa nhầm hoặc xóa thất bại. |
| “So sánh hậu tố chuỗi DN là đủ để kiểm tra OU.” | Nên parse DN và so sánh theo RDN, thêm rule về cấp và loại entry. |
| “`delete(person)` có thể xóa toàn bộ OU nếu person chứa con.” | LDAP Delete thường chỉ xóa entry lá; OU có con trả lỗi 66. |
| “Lookup trước delete bảo đảm không xóa nhầm vì có race.” | Lookup và delete là hai thao tác, không nguyên tử nếu thiếu cơ chế riêng. |
| “Entry không thấy sau delete chắc chắn mọi nhóm đã được cập nhật.” | Tham chiếu nhóm có thể vẫn còn, tùy server/plugin. |
| “Timeout nghĩa là delete chưa chạy.” | Có thể lệnh đã được server áp dụng trước khi kết nối lỗi. |
| “`unbind(dn, true)` là bản vá cho mọi lỗi delete.” | Đó là xóa đệ quy và có rủi ro xóa hàng loạt nếu DN sai. |

## Tài liệu tham khảo

- [Spring LDAP Reference — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): metadata ODM, `@Entry`, `@Id`, `@DnAttribute` và CRUD với `LdapTemplate`.
- [Spring LDAP API — LdapOperations](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapOperations.html): hợp đồng `delete(Object)`, `findByDn(...)` và xử lý DN.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `delete(Object)`, `unbind(Name)` và `unbind(Name, boolean)`.
- [Spring LDAP API — @Entry](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/Entry.html): metadata object classes và base DN.
- [Java SE — LdapName](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html): phân tích và so sánh các thành phần RDN.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): thao tác Delete và mã kết quả LDAP.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): biểu diễn và escape DN.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528): điều kiện kiểm tra phía server nếu triển khai hỗ trợ.

## Ghi nhớ

**Xóa object trong Spring LDAP ODM là xóa entry tại một DN cụ thể.** `LdapTemplate.delete(object)` dựa vào metadata `@Entry` và DN từ `@Id`; nếu `@Id` chưa được đặt, ODM có thể tính DN từ `@DnAttribute`. Trước khi xóa, cần dựng và **kiểm tra DN theo cấu trúc RDN**, bảo đảm mục tiêu nằm trong OU được phép, xác minh đối tượng hiện hành và áp dụng authorization. Đối với entry lá, delete thông thường là phù hợp; với nhánh còn con, không tự chuyển sang xóa đệ quy. Hãy xem kết quả xóa, lỗi, trạng thái race và các tham chiếu DN như những phần của cùng một quy trình vận hành an toàn, chứ không phải công việc tự động của ODM.
