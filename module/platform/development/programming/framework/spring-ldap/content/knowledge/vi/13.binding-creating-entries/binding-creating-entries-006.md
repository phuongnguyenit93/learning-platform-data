# Entry đã tồn tại và lỗi NameAlreadyBoundException trong Spring LDAP

Một thao tác tạo nhân viên trong LDAP có thể thất bại dù URL, mật khẩu của tài khoản dịch vụ, bộ `objectClass` và các thuộc tính đều hợp lệ. Ví dụ: người dùng nhấn **Tạo tài khoản** hai lần, hoặc hai tiến trình cùng cố thêm entry `uid=an,ou=people,dc=example,dc=org`. Lần đầu có thể tạo thành công; lần còn lại gặp lỗi **entry đã tồn tại**. Ở tầng JNDI, lỗi này thường được biểu diễn bằng `NameAlreadyBoundException`, tương ứng với mã phản hồi LDAP **`entryAlreadyExists (68)`**.

Bài học thuộc chương **Bind và tạo entry** của SPRING_LDAP. Ta sẽ hiểu tại sao DN không được tạo trùng, cách phát hiện và xử lý lỗi khi dùng `LdapTemplate.bind(...)`, mối quan hệ với LDAP Bind xác thực, sự khác biệt giữa kiểm tra tồn tại với bảo đảm tạo duy nhất, và cách trả kết quả rõ ràng ở API nghiệp vụ. Bài cũng đặt thao tác này trong bối cảnh `ContextSource`, schema, ACL, TLS, kiểm thử và việc chuyển sang `LdapClient` hoặc ODM.

## 1. Hai khái niệm “bind” tuyệt đối không được nhầm

Tên `bind` trong Spring LDAP/JNDI có thể khiến người mới học hiểu sai:

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| **LDAP protocol Bind** | Xác thực danh tính trên kết nối LDAP | Tài khoản `cn=app-writer,...` dùng DN và password khi lấy context |
| **`LdapTemplate.bind(...)`** | **Tạo entry** tại DN trong thư mục | Thêm `uid=an,ou=people` |
| **`LdapTemplate.rebind(...)`** | Thay binding/dữ liệu theo mô hình JNDI | Cần kiểm soát chặt khi muốn thay thế |
| **`LdapTemplate.modifyAttributes(...)`** | Sửa thuộc tính của entry hiện có | Chỉ đổi `mail` |
| **`LdapTemplate.unbind(...)`** | Xóa entry theo DN | Xóa một entry được phép |

Trong bài này, **`NameAlreadyBoundException` liên quan tới thao tác thêm một entry trùng tên**, không đồng nghĩa mật khẩu bind của tài khoản dịch vụ sai.

Nếu tài khoản `app-writer` không xác thực được, ứng dụng có thể gặp lỗi như `invalidCredentials (49)` **trước khi** thao tác tạo entry thực hiện. Nếu xác thực thành công nhưng không có quyền thêm entry, server có thể trả `insufficientAccessRights (50)`. Ba tình huống này cần xử lý khác nhau.

## 2. Vì sao một DN không được tạo hai lần?

LDAP tổ chức entry thành cây tên (*Directory Information Tree*, DIT). Giả sử:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=binh
├── ou=groups
│   └── cn=engineering
└── ou=services
    └── cn=app-writer
~~~

Entry An đã có trên server:

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

Bây giờ ứng dụng gửi một yêu cầu **Add** khác cũng nhắm vào:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

Trong cùng một vùng tên của thư mục, server **không thể có hai entry khác nhau với cùng DN**. LDAP Add không phải lệnh “ghi đè nếu đã tồn tại”. Khi DN đích đã được sử dụng, một server thực thi giao thức thông thường trả về `entryAlreadyExists (68)`.

Điều cần lưu ý:

- **DN**, không phải chỉ giá trị `uid`, là tên xác định entry. `uid=an,ou=people,...` và `uid=an,ou=contractors,ou=people,...` là **hai DN khác nhau**.
- Hai entry có cùng giá trị `uid` dưới hai OU khác nhau có thể vẫn tồn tại nếu schema, chính sách directory và ứng dụng cho phép.
- Nếu nghiệp vụ yêu cầu `uid` duy nhất trong **toàn tổ chức**, cơ chế không trùng DN **chưa đủ**. Cần thêm chính sách dữ liệu, cơ chế uniqueness của server hoặc phương án cấp phát định danh phù hợp.
- Những DN có cách viết chuỗi khác nhau vẫn có thể chỉ cùng một entry theo quy tắc so khớp tên của LDAP server; không dùng so sánh Java `String.equals` giữa hai DN để quyết định chắc chắn có trùng hay không.

### DN đầy đủ và DN tương đối

Giả sử `LdapContextSource` có:

~~~text
ContextSource base = dc=example,dc=org
~~~

Khi gọi `LdapTemplate`, ứng dụng thường dùng DN **tương đối với base**:

| DN đưa cho Spring LDAP | DN đích trên server |
| --- | --- |
| `uid=an,ou=people` | `uid=an,ou=people,dc=example,dc=org` |
| `uid=binh,ou=people` | `uid=binh,ou=people,dc=example,dc=org` |
| `ou=people` | `ou=people,dc=example,dc=org` |

Nếu truyền lại full DN khi một API đang xử lý tên tương đối, suffix có thể bị thêm hai lần. Một lỗi DN như vậy thường tạo `noSuchObject (32)` hơn là lỗi trùng entry dự định. Vì thế, trước khi phân loại lỗi, phải xác định **base hiệu lực**.

## 3. Điều gì xảy ra khi gọi `LdapTemplate.bind(...)`?

Một luồng tạo entry có thể hình dung như sau:

~~~mermaid
sequenceDiagram
    participant U as API / Service
    participant T as LdapTemplate
    participant C as ContextSource + JNDI
    participant D as LDAP server
    U->>T: bind(entry tại uid=an,ou=people)
    T->>C: Lấy context với danh tính dịch vụ
    C->>D: Kết nối/bind xác thực khi cần
    D-->>C: Xác thực được chấp nhận
    C->>D: LDAP AddRequest(DN, attributes)
    alt DN chưa tồn tại và các ràng buộc hợp lệ
        D-->>C: success (0)
        C-->>T: Hoàn tất
        T-->>U: Tạo entry thành công
    else DN đã tồn tại
        D-->>C: entryAlreadyExists (68)
        C-->>T: JNDI NamingException
        T-->>U: Spring LDAP NameAlreadyBoundException
    end
~~~

Đây là luồng **logic**. Tần suất mở kết nối, thời điểm thực hiện bind xác thực và việc tái sử dụng context phụ thuộc JNDI provider, cấu hình `ContextSource` và pooling. Nhưng ý nghĩa của Add vẫn là: server nhận DN và tập attributes, sau đó quyết định tạo hay từ chối.

Một số nhánh lỗi khác có thể xuất hiện trước hoặc thay cho `68`: DN cha chưa tồn tại, entry không hợp schema, tài khoản thiếu quyền hoặc lỗi kết nối. Đừng bắt mọi exception rồi gắn nhãn “đã tồn tại”.

## 4. `NameAlreadyBoundException` ở JNDI và Spring LDAP

Khi làm việc trực tiếp với JNDI, kiểu exception là:

~~~java
javax.naming.NameAlreadyBoundException
~~~

Nó thuộc hệ thống `javax.naming.NamingException`. Trong thao tác LDAP Add, provider JNDI có thể chuyển kết quả `entryAlreadyExists (68)` thành exception này.

Khi đi qua Spring LDAP, `LdapTemplate` thường chuyển các exception JNDI sang hệ thống exception của Spring LDAP. Trong trường hợp đang xét, kiểu thường dùng để bắt ở tầng service là:

~~~java
org.springframework.ldap.NameAlreadyBoundException
~~~

Hai class có tên ngắn giống nhau nhưng **nằm trong package khác nhau**:

| Nguồn | Class thường gặp | Ai xử lý? |
| --- | --- | --- |
| JNDI trực tiếp | `javax.naming.NameAlreadyBoundException` | Code JNDI tự bắt và đóng context |
| Spring LDAP `LdapTemplate` | `org.springframework.ldap.NameAlreadyBoundException` | Service/exception handler theo API Spring LDAP |
| Giao thức LDAP | Result code `68 — entryAlreadyExists` | LDAP server |

Cách ánh xạ cụ thể có thể phụ thuộc provider và phiên bản thư viện. Khi viết ứng dụng thực tế, kiểm tra exception thực sự được phát sinh qua đường gọi đang dùng, đặc biệt khi có lớp bọc kết nối hoặc provider tùy biến. **Không bắt nhầm exception JNDI trong service đang nhận exception Spring đã được chuyển đổi.**

### Tại sao nên bắt loại lỗi cụ thể?

Một cách xử lý sai:

~~~java
try {
    ldapTemplate.bind(entry);
} catch (Exception e) {
    return "Người dùng đã tồn tại"; // SAI: che mọi lỗi LDAP.
}
~~~

Đoạn này có thể che cả lỗi server ngừng hoạt động, sai credential, thiếu quyền, schema sai và lỗi lập trình.

Một cách tốt hơn: chỉ chuyển **lỗi trùng DN đã xác định** thành kết quả nghiệp vụ “conflict”; cho các lỗi khác tiếp tục được xử lý bởi cơ chế lỗi riêng.

## 5. Tạo entry đúng schema bằng `DirContextAdapter`

Để minh họa, tạo entry `uid=lan` dưới `ou=people` với `LdapTemplate`.

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonCreator {

    private final LdapTemplate ldapTemplate;

    public PersonCreator(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void create(String uid, String commonName, String surname) {
        if (uid == null || uid.isBlank() || uid.length() > 64) {
            throw new IllegalArgumentException("Invalid uid");
        }
        if (commonName == null || commonName.isBlank()
                || surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("cn and sn are required");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        DirContextAdapter entry = new DirContextAdapter(dn);
        entry.setAttributeValues("objectClass", new String[]{
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", uid);
        entry.setAttributeValue("cn", commonName);
        entry.setAttributeValue("sn", surname);

        ldapTemplate.bind(entry);
    }
}
~~~

Giải thích:

1. `LdapNameBuilder` bảo đảm giá trị `uid` được biểu diễn dưới dạng RDN phù hợp, thay vì nối chuỗi `"uid=" + uid + ",ou=people"` với input chưa kiểm soát.
2. `DirContextAdapter` mang DN và attributes dùng để **tạo mới** entry.
3. `objectClass` nêu cấu trúc entry. Trong chuỗi class chuẩn trên, `person` yêu cầu `cn` và `sn`; `uid` được đặt để phù hợp với RDN.
4. `ldapTemplate.bind(entry)` là thao tác tạo entry, không phải xác thực người dùng.
5. Parent `ou=people,dc=example,dc=org` phải tồn tại và account phải có quyền add.
6. Nếu DN đích đã có, yêu cầu Add không được ghi đè entry cũ.

Ví dụ này chỉ dành cho **directory lab** có schema phù hợp. Trong production, cần kiểm tra identifier theo chính sách doanh nghiệp, giới hạn request, quyền người gọi, audit và nội dung attribute trước khi ghi.

### Tạo trùng không phụ thuộc giá trị thuộc tính có giống nhau hay không

Giả sử `uid=lan,ou=people` đã tồn tại với `cn: Le Thi Lan`. Một yêu cầu mới gửi cùng DN nhưng `cn: Lan Le` vẫn là **tạo trùng DN**, không phải yêu cầu “chỉnh sửa CN”:

~~~text
Entry cũ:
dn: uid=lan,ou=people,dc=example,dc=org
cn: Le Thi Lan

Yêu cầu Add mới:
dn: uid=lan,ou=people,dc=example,dc=org
cn: Lan Le

Kết quả thường gặp: entryAlreadyExists (68)
~~~

Muốn sửa `cn` phải đi qua **quy trình cập nhật**, kiểm tra quyền và sử dụng API như `modifyAttributes(...)`, không dựa vào việc thêm trùng để ghi đè.

## 6. Chuyển lỗi trùng entry thành lỗi nghiệp vụ

Một service nên giữ hợp đồng rõ ràng: **create-only**, nghĩa là tạo được entry mới hoặc báo xung đột; không bí mật sửa dữ liệu đã có.

Ví dụ:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonProvisioningService {

    private final LdapTemplate ldapTemplate;

    public PersonProvisioningService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createPerson(String uid, String cn, String sn) {
        validate(uid, cn, sn);

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        DirContextAdapter entry = new DirContextAdapter(dn);
        entry.setAttributeValues("objectClass", new String[]{
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", uid);
        entry.setAttributeValue("cn", cn);
        entry.setAttributeValue("sn", sn);

        try {
            ldapTemplate.bind(entry);
        } catch (org.springframework.ldap.NameAlreadyBoundException ex) {
            throw new PersonAlreadyExistsException(
                    "Person identifier is already in use", ex);
        }
    }

    private static void validate(String uid, String cn, String sn) {
        if (uid == null || uid.isBlank() || uid.length() > 64) {
            throw new IllegalArgumentException("Invalid uid");
        }
        if (cn == null || cn.isBlank()
                || sn == null || sn.isBlank()) {
            throw new IllegalArgumentException("cn and sn are required");
        }
    }

    public static class PersonAlreadyExistsException
            extends RuntimeException {
        public PersonAlreadyExistsException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Điều gì đáng chú ý?

- Chỉ **`NameAlreadyBoundException`** được chuyển thành `PersonAlreadyExistsException`.
- Lỗi schema, LDAP ACL, TLS, timeout… **không** bị biến thành xung đột.
- Thông báo nghiệp vụ không chứa mật khẩu, dữ liệu nội bộ của entry hoặc nguyên văn LDAP response.
- Một lớp API có thể chuyển `PersonAlreadyExistsException` thành HTTP **409 Conflict**, nhưng không phải mọi ứng dụng LDAP đều là HTTP service; ở CLI hoặc message consumer có thể dùng kết quả phù hợp hơn.
- Ví dụ đặt exception trong service để tự chứa; trong dự án thật có thể dùng exception/domain result chung.

### HTTP 409 khác HTTP 500 hoặc 503

Nếu hệ thống có REST API tạo nhân viên, các tình huống nên được phân biệt:

| Tình huống | Phản hồi API gợi ý | Lý do |
| --- | --- | --- |
| Tạo entry mới thành công | `201 Created` | Tài nguyên mới được tạo |
| DN/identifier đã có | `409 Conflict` | Xung đột với tài nguyên tồn tại |
| Input không hợp lệ | `400 Bad Request` hoặc `422 Unprocessable Content` theo hợp đồng | Không phải lỗi trùng entry |
| Người gọi không có quyền | `403 Forbidden` hoặc chính sách che thông tin | Không được phép tạo entry |
| LDAP tạm thời không sẵn sàng | `503 Service Unavailable` theo chính sách | Không phải lỗi “đã tồn tại” |
| Lỗi không xác định ở backend | `5xx` thích hợp và theo dõi nội bộ | Không đoán là lỗi conflict |

Đây là khuyến nghị về **hợp đồng API**, không phải ánh xạ tự động của Spring LDAP. Cũng cần quyết định có được phép tiết lộ rằng một UID cụ thể đang tồn tại hay không: với endpoint nhạy cảm, thông báo có thể cần đủ chung để tránh *user enumeration*.

## 7. “Kiểm tra trước khi tạo” không loại bỏ xung đột

Một cách làm tưởng an toàn:

~~~text
Nếu chưa tìm thấy uid=an
    thì gọi bind() tạo uid=an
~~~

Điều này có thể giúp UX, nhưng **không phải bảo đảm tính duy nhất** khi có nhiều người dùng hoặc nhiều instance.

Hai request đồng thời:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant D as LDAP server
    A->>D: Search uid=an
    B->>D: Search uid=an
    D-->>A: Chưa tìm thấy
    D-->>B: Chưa tìm thấy
    A->>D: Add uid=an,ou=people
    D-->>A: success
    B->>D: Add uid=an,ou=people
    D-->>B: entryAlreadyExists (68)
~~~

Đây là lỗi *time-of-check to time-of-use* (TOCTOU). Trong khoảng giữa search và Add, một request khác có thể đã tạo entry.

**Nguyên tắc:** nếu nghiệp vụ cần *create-only*, hãy để LDAP server quyết định phép Add theo DN. Ứng dụng vẫn phải **bắt lỗi trùng** ngay cả khi đã làm pre-check. Pre-check có thể có ích để hiển thị gợi ý trước khi gửi form, nhưng không được coi là khóa đồng bộ hoặc cơ chế bảo mật.

Ngoài ra, một search trước có thể trả về 0 entry do ACL, scope hoặc replication lag, dù entry đã tồn tại tại nơi thực hiện Add. Vì vậy **search không thấy** chưa chắc đồng nghĩa **DN trống**.

## 8. DN uniqueness khác uniqueness của thuộc tính nghiệp vụ

Một ứng dụng có thể có hai OU:

~~~text
uid=an,ou=employees,dc=example,dc=org
uid=an,ou=contractors,dc=example,dc=org
~~~

Hai DN **khác nhau**, nên LDAP không mặc nhiên ngăn cả hai cùng tồn tại chỉ vì có chung `uid=an`.

Nếu nghiệp vụ dùng UID làm tên đăng nhập toàn hệ thống, cần một trong các cách tiếp cận được thiết kế rõ:

- Tất cả tài khoản cùng một vùng cấp phát DN duy nhất, với RDN dựa trên UID đã chuẩn hóa theo chính sách.
- Server hỗ trợ và được cấu hình chính sách **unique attribute** ở phạm vi thích hợp.
- Một dịch vụ cấp phát định danh tập trung có cơ chế đồng bộ/khóa và bảo vệ chống race.
- Thiết kế khóa nghiệp vụ khác, ví dụ ID nội bộ bất biến; không coi mỗi giá trị `cn` hay `mail` chắc chắn duy nhất.

Ngay cả khi có extension kiểm tra uniqueness ở server, **mã lỗi và chính sách báo lỗi có thể khác** lỗi DN trùng. Không giả định mọi vi phạm uniqueness đều trả `entryAlreadyExists (68)` hoặc đều được ánh xạ thành `NameAlreadyBoundException`.

### Không so sánh DN bằng chuỗi chưa được chuẩn hóa

Tên DN có cú pháp escape, nhiều loại RDN và các quy tắc so khớp tên của LDAP. Một giá trị ký tự đặc biệt như dấu phẩy phải được encode đúng. Dùng `LdapNameBuilder` hoặc kiểu `Name/LdapName` thay vì ghép, cắt DN bằng `split(",")`.

Dù dùng `LdapName.equals(...)` để kiểm tra một số trường hợp ở client, **server vẫn là nguồn quyết định tính trùng tên của entry thực tế** theo schema/semantics của nó.

## 9. Vì sao không nên đổi ngay từ `bind(...)` sang `rebind(...)`?

Khi gặp `NameAlreadyBoundException`, một giải pháp có vẻ đơn giản là thay:

~~~java
ldapTemplate.bind(entry);
~~~

bằng:

~~~java
ldapTemplate.rebind(entry);
~~~

Nhưng đây là **thay đổi hợp đồng nghiệp vụ**: từ “chỉ tạo nếu chưa có” sang một thao tác JNDI có ý nghĩa **thay binding tại tên**. Nó không phải cách sửa lỗi trùng DN an toàn cho mọi trường hợp.

Giả sử entry hiện có:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
mail: an@example.org
telephoneNumber: +84 28 1111
description: Managed by HR
~~~

Một request tạo trùng chỉ mang các trường `uid`, `cn`, `sn`. Nếu áp dụng `rebind` tùy tiện, tập attribute được tạo lại có thể thiếu `mail`, `telephoneNumber` hoặc `description`. Tùy provider và cơ chế thao tác, việc thay thế có thể làm mất dữ liệu do các hệ thống khác quản lý.

| Mục tiêu | API nên cân nhắc | Ý nghĩa |
| --- | --- | --- |
| Chỉ tạo entry mới, không chạm entry cũ | **`bind(...)`** | Nhận lỗi conflict khi DN đã có |
| Chỉ sửa `mail` của entry có sẵn | **`modifyAttributes(...)`** | Thay đổi thuộc tính có chọn lọc |
| Chủ động thay thế binding bằng tập dữ liệu đầy đủ | **`rebind(...)`**, sau khi xác minh semantics | Có nguy cơ tác động các attributes hiện hữu |
| Đổi RDN hoặc chuyển OU | **`rename(...)` / Modify DN** | Đổi tên/vị trí, không phải tạo trùng |
| Xóa entry đã có | **`unbind(...)`** | Xóa DN cụ thể, thường cần entry là leaf |

**Không sử dụng `rebind` như “thử tạo, nếu có thì cập nhật” chỉ để tránh phải bắt exception.** Cần quyết định rõ create, update, replace và rename; mỗi thao tác có chính sách phân quyền, audit và xử lý đồng thời riêng.

### Nếu nghiệp vụ thật sự cần upsert

“Upsert” có thể mang nhiều nghĩa:

1. Nếu chưa có entry → tạo; nếu đã có → **không làm gì**.
2. Nếu chưa có → tạo; nếu đã có → **cập nhật một vài attribute**.
3. Nếu chưa có → tạo; nếu đã có → **thay toàn bộ dữ liệu do ứng dụng sở hữu**.

Ba hợp đồng này khác nhau. Hãy xác định chính xác trước khi lập trình, đặc biệt về trường hợp entry đã tồn tại nhưng thuộc **một chủ thể khác**. Việc xử lý xung đột có thể cần đọc lại entry bằng quyền phù hợp, kiểm tra định danh bất biến rồi mới áp dụng thay đổi được phép.

Khi có nhiều writer, một chuỗi “search rồi bind hoặc modify” không mặc nhiên là transaction xuyên hai request LDAP. Để bảo đảm không ghi đè trong tình huống cạnh tranh, cần thiết kế theo các cơ chế được LDAP server hỗ trợ.

## 10. Retry khi lỗi mạng: một trạng thái rất dễ bị nhầm với trùng DN

Giả sử service gửi yêu cầu Add cho UID Lan, server đã tạo thành công nhưng đường mạng đứt trước khi client nhận được response:

~~~text
Client                          LDAP server
  | --- Add(uid=lan) ----------> |
  |                              | Tạo entry thành công
  | <---- response bị mất ------X |
  | Timeout                      |
~~~

Từ phía ứng dụng, request đầu tiên được báo **timeout** dù entry có thể đã tạo. Nếu client lập tức gửi lại cùng Add, server trả `entryAlreadyExists (68)`.

Trong trường hợp này, lỗi trùng ở lần thử lại **không tự chứng minh request ban đầu thất bại**. Đây là một *ambiguous outcome*: server có thể đã lưu dữ liệu, cũng có thể một tác nhân khác đã tạo entry trong thời gian đó.

### Quy trình phục hồi an toàn

1. Phân loại lỗi ban đầu: **đã nhận rõ result 68**, hay **timeout/connection error không chắc kết quả**?
2. Nếu kết quả không chắc chắn, khi kết nối phục hồi, **đọc lại DN đích** bằng tài khoản có quyền phù hợp.
3. Đối chiếu các thuộc tính dùng để nhận dạng bản ghi **do yêu cầu của ứng dụng tạo ra**, chẳng hạn một ID bất biến/operation ID được thiết kế từ trước, nếu schema cho phép.
4. Nếu entry hiện tại thực sự tương ứng với yêu cầu đã hoàn tất, có thể trả về trạng thái idempotent theo hợp đồng API.
5. Nếu entry cùng DN nhưng không thể xác minh là cùng yêu cầu/chủ thể, báo conflict hoặc chuyển sang quy trình hòa giải; **không ghi đè**.
6. Không retry vô hạn. Áp dụng giới hạn thử lại, backoff và quan sát lỗi kết nối.

Với hệ thống nhạy cảm, **idempotency key** có thể được quản lý ở tầng API/database của ứng dụng. Nhưng một khóa nằm riêng trong HTTP header không khiến LDAP tự hiểu yêu cầu là trùng hợp lệ; hệ thống phải thiết kế cách đối chiếu kết quả ghi.

### Có nên coi mọi `NameAlreadyBoundException` là thành công?

**Không.** Có ít nhất hai nguyên nhân rất khác nhau:

- Client đang retry đúng yêu cầu đã tạo thành công trước đó.
- Một tài khoản/entry của chủ thể khác đã chiếm DN hoặc có conflict thực sự.

Chỉ khi ứng dụng có **bằng chứng đủ mạnh** về danh tính và nội dung tài nguyên mới được chọn trả “đã xử lý” theo semantics idempotency. Không tự động đọc rồi trả dữ liệu của entry có sẵn cho người gọi chưa được cấp quyền.

## 11. Phân biệt lỗi entry đã tồn tại với những lỗi tạo entry khác

LDAP server còn áp dụng cấu trúc DIT, schema, ACL và chính sách xác thực. Một bảng chẩn đoán giúp tránh xử lý sai:

| Tình huống | Mã LDAP thường gặp | Điều nên kiểm tra |
| --- | --- | --- |
| DN đích đã có entry | **`entryAlreadyExists (68)`** | DN hiệu lực, yêu cầu tạo trùng, tình trạng race/retry |
| DN cha chưa tồn tại | `noSuchObject (32)` | Parent OU, base của `ContextSource`, DN tương đối |
| Không có quyền thêm entry | `insufficientAccessRights (50)` | ACL của tài khoản dịch vụ và nhánh đích |
| Thiếu MUST attribute / sai object class | `objectClassViolation (65)` | `cn`, `sn`, chuỗi object class, schema |
| Giá trị attribute sai cú pháp | `invalidAttributeSyntax (21)` | Syntax của attribute type, dữ liệu đầu vào |
| Vi phạm ràng buộc khác | `constraintViolation (19)` | SINGLE-VALUE, policy server, giới hạn |
| Tên DN không hợp lệ | `invalidDNSyntax (34)` | Escape RDN, cấu trúc DN, input chưa kiểm tra |
| Bind DN hoặc password kết nối không hợp lệ | `invalidCredentials (49)` | Secret, danh tính bind và cơ chế xác thực |
| Server yêu cầu bảo vệ xác thực mạnh hơn | `strongerAuthRequired (8)` | TLS/SASL và chính sách server |
| Kết nối/TLS bị lỗi | Timeout, handshake hoặc communication error | Hostname, CA, network, pooling, timeout |
| Phạm vi tên hoặc quyền khiến thông tin bị che | Có thể lỗi khác hoặc không thấy entry | Referral, ACL, chính sách server |

Đây là các kết quả **điển hình**, không phải bảo đảm mọi server sẽ chọn cùng một result khi nhiều điều kiện đồng thời không hợp lệ. Ví dụ, server có thể kiểm tra quyền trước khi bộc lộ sự tồn tại của một entry.

**Cách điều tra:** ghi nhận loại thao tác, DN đích theo chính sách bảo vệ dữ liệu, result code/loại exception, danh tính service bind và correlation ID. Không in password, credential, toàn bộ entry hoặc dữ liệu nhạy cảm vào log.

## 12. Tài khoản, TLS và quyền khi tạo entry

Một cấu hình truy cập LDAP có thể có dạng:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=app-writer,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Các giá trị minh họa được cấp theo môi trường. Password phải được cung cấp qua secret manager hoặc nguồn cấu hình bí mật được quản trị, **không lưu mật khẩu thật trong Git**.

Với thao tác tạo entry, cần xem xét đồng thời:

- **TLS:** simple bind gửi credential qua kết nối; dùng LDAPS hoặc StartTLS với chứng chỉ, tên máy và CA đã được kiểm chứng.
- **Base DN:** chọn đúng suffix, tránh lặp phần `dc=example,dc=org` khi tạo DN tương đối.
- **ACL:** cấp quyền add chỉ trong OU nghiệp vụ, không dùng tài khoản quản trị directory cho mọi endpoint.
- **Schema:** thuộc tính RDN và `objectClass` phải hợp lệ; server mới là nơi xác minh cuối cùng.
- **Đầu vào:** giới hạn UID, loại bỏ giá trị không phù hợp chính sách và xây RDN bằng builder thay vì nối chuỗi.
- **Truy cập dữ liệu cũ:** khi báo conflict, không tùy tiện trả tên, email hay DN của entry đã tồn tại cho client.
- **Auditing:** ghi operation và kết quả phù hợp, không tiết lộ password hoặc thông tin không được phép.
- **Giới hạn tài nguyên:** timeout, retry và pooling cần được kiểm tra; đặc biệt lưu ý lifecycle của kết nối đang bind bằng credential cũ sau khi rotate secret.

Một `ContextSource.base` hẹp **không thay thế ACL**: client có thể cấu hình tên trong một OU, nhưng quyền thực tế vẫn được LDAP server quyết định. Tương tự, escape DN đúng cú pháp **không tạo ra quyền nghiệp vụ** để người dùng được đăng ký một UID bất kỳ.

## 13. Kiểm thử logic “tạo mới” trước khi kết nối server

Có hai cấp độ cần kiểm tra:

1. **Unit test:** xác minh service tạo DN, gắn những thuộc tính cần thiết và gọi `LdapTemplate.bind(...)` theo hợp đồng create-only.
2. **Integration test:** xác minh LDAP server trả lỗi trùng thực sự, Spring LDAP chuyển lỗi như kỳ vọng, đồng thời không ảnh hưởng entry đã tồn tại.

### Unit test: tạo DN và attributes đúng

Ví dụ dùng Mockito và JUnit 5 với lớp `PersonProvisioningService` ở mục 6:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

class PersonProvisioningServiceTest {

    @Test
    void bindsExpectedDnAndAttributes() {
        LdapTemplate template = mock(LdapTemplate.class);
        PersonProvisioningService service =
                new PersonProvisioningService(template);

        service.createPerson("lan", "Le Thi Lan", "Le");

        ArgumentCaptor<DirContextOperations> captured =
                ArgumentCaptor.forClass(DirContextOperations.class);
        verify(template).bind(captured.capture());
        verifyNoMoreInteractions(template);

        DirContextOperations entry = captured.getValue();
        assertEquals("uid=lan,ou=people", entry.getDn().toString());
        assertEquals("lan", entry.getStringAttribute("uid"));
        assertEquals("Le Thi Lan", entry.getStringAttribute("cn"));
        assertEquals("Le", entry.getStringAttribute("sn"));
    }
}
~~~

Test này xác minh dữ liệu **được chuẩn bị để tạo** chứ không có LDAP server thật. Nó không chứng minh schema, ACL, tính duy nhất của DN hoặc cách Spring chuyển exception từ JNDI. Để kiểm tra điều đó cần integration test.

### Test input không hợp lệ không tạo entry

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.LdapTemplate;

class PersonProvisioningValidationTest {

    @Test
    void blankUidDoesNotCallLdap() {
        LdapTemplate template = mock(LdapTemplate.class);
        PersonProvisioningService service =
                new PersonProvisioningService(template);

        assertThrows(IllegalArgumentException.class,
                () -> service.createPerson(" ", "Lan", "Le"));

        verifyNoInteractions(template);
    }
}
~~~

Trong dự án thật, validation nên kiểm tra thêm format/độ dài/allowlist UID, canonicalization theo chính sách và quyền người gọi. Mục tiêu unit test là bảo đảm input không hợp lệ bị từ chối **trước** khi có request LDAP.

## 14. Integration test: tạo hai lần cùng DN

Để tái hiện lỗi trùng chính xác, dùng một LDAP server lab có schema và dữ liệu kiểm soát, ví dụ một container LDAP test. Parent `ou=people` cần tồn tại và tài khoản test phải có quyền add/delete trong OU được chỉ định.

Quy trình:

1. Tạo một UID có tiền tố thử nghiệm và phần ngẫu nhiên, tránh trùng dữ liệu có sẵn.
2. Gọi `createPerson(uid, ...)` một lần và xác minh entry được tạo.
3. Gọi **cùng phương thức, cùng UID** lần thứ hai.
4. Xác minh service báo đúng lỗi domain `PersonAlreadyExistsException` (hoặc adapter lỗi được chọn).
5. Đọc lại entry để chứng minh lần thử thứ hai **không ghi đè** `cn`, `sn`, `mail`.
6. Xóa **chỉ entry do test đã tạo**, bảo đảm cleanup có kiểm soát.
7. Thử với hai tác vụ đồng thời để kiểm tra một yêu cầu có thể thành công và yêu cầu khác gặp conflict.

Ví dụ khung JUnit (chỉ chạy trên directory lab và tài khoản có quyền đã cấp):

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.UUID;
import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

class DuplicateEntryIntegrationTest {

    private PersonProvisioningService service;
    private LdapTemplate ldapTemplate;

    @Test
    void secondAddFailsWithoutReplacingFirstEntry() {
        String uid = "lab-" + UUID.randomUUID().toString().replace("-", "");
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        boolean created = false;
        try {
            service.createPerson(uid, "First Name", "First");
            created = true;

            assertThrows(
                    PersonProvisioningService.PersonAlreadyExistsException.class,
                    () -> service.createPerson(uid, "Changed Name", "Changed"));

            // Bổ sung lookup/assertion đọc lại cn/sn của entry:
            // phải vẫn là First Name / First.
        } finally {
            if (created) {
                ldapTemplate.unbind(dn);  // Chỉ dọn entry test đã tạo.
            }
        }
    }
}
~~~

Đây là **khung minh họa**: `service` và `ldapTemplate` cần được inject từ cấu hình integration test. Nó không tự tạo server hay OU, và cleanup cần theo chính sách của môi trường test. Trong thực tế nên bổ sung đọc lại attributes trước khi cleanup để kiểm tra rõ tính không ghi đè.

### Những trường hợp bổ sung nên có

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Tạo UID chưa tồn tại | Thêm entry thành công đúng DN và schema |
| Tạo lại cùng DN, attributes khác | Conflict, không ghi đè dữ liệu cũ |
| Cùng UID dưới hai OU khác nhau | Hiểu phạm vi uniqueness; không nhầm với trùng DN |
| Parent OU không có | Phân biệt `noSuchObject` với `NameAlreadyBoundException` |
| Account không có quyền add | Phân biệt lỗi ACL với lỗi conflict |
| Password dịch vụ sai | Lỗi xác thực không bị chuyển thành “đã tồn tại” |
| Có search pre-check, hai thread đồng thời | Vẫn phải xử lý lỗi Add race |
| Mất phản hồi sau Add | Xác minh trạng thái trước khi quyết định retry |
| DN có ký tự đặc biệt | Builder escape đúng; không thể chèn thêm RDN qua UID |
| Môi trường có replica | Không coi search replica rỗng là bằng chứng tên chưa có tại writer |

**Không chạy các test tạo/xóa trên production.** Nếu mock `LdapTemplate`, chưa thể xác minh result code 68 hoặc chính sách server; integration test là cần thiết cho hành vi thực.

## 15. Bài thực hành: xử lý bốn kết quả tạo entry

Cho `ContextSource.base = dc=lab,dc=example,dc=org` và nhánh:

~~~text
ou=people,dc=lab,dc=example,dc=org
├── uid=an
└── uid=binh
~~~

Ứng dụng cần tạo các entry mới bằng `LdapTemplate.bind(...)`. Giả sử account test được cấp quyền add dưới OU, kết nối LDAPS đã được kiểm chứng.

### Nhiệm vụ

1. Người dùng gửi `uid=chi` (chưa có). Dự đoán kết quả nếu DN cha, schema và ACL đều hợp lệ.
2. Người dùng gửi `uid=an` đã có. Cho biết LDAP result code và tên exception ở JNDI/Spring LDAP thường gặp.
3. Một client gửi `uid=an` với `cn` khác dữ liệu cũ. Có nên dùng `rebind(...)` để “khắc phục” `NameAlreadyBoundException` không? Vì sao?
4. Hai instance cùng kiểm tra `uid=lan` chưa tồn tại rồi cùng gửi Add. Tại sao cả hai pre-check có thể thành công nhưng chỉ một Add thành công?
5. Một request tạo Lan báo timeout, request retry báo trùng DN. Có thể kết luận lần đầu thất bại không?
6. Có hai DN `uid=an,ou=people,...` và `uid=an,ou=contractors,...`. Cả hai có luôn bị LDAP cấm không?
7. Trong API HTTP, vì sao lỗi trùng DN cần phân biệt với lỗi không có quyền và lỗi TLS?
8. Khi mã nghiệp vụ bắt exception, cần dùng class `javax.naming.NameAlreadyBoundException` hay `org.springframework.ldap.NameAlreadyBoundException`?

### Đáp án có giải thích

| Câu | Đáp án |
| --- | --- |
| 1 | LDAP Add có thể thành công và tạo entry `uid=chi,ou=people,...` |
| 2 | Thường là result code **`68 — entryAlreadyExists`**; JNDI có `javax.naming.NameAlreadyBoundException`, Spring LDAP thường chuyển sang `org.springframework.ldap.NameAlreadyBoundException` |
| 3 | Không tự động. `rebind` mang semantics thay binding, có nguy cơ tác động các attributes cũ; cần quy trình update/replace riêng |
| 4 | Vì pre-check và Add là hai thao tác tách biệt; request kia có thể thêm entry trong khoảng giữa |
| 5 | Không. Response có thể bị mất sau khi server đã ghi; phải xác minh trạng thái và nguồn gốc entry |
| 6 | Không mặc nhiên. Hai DN khác nhau; uniqueness trên toàn tổ chức là chính sách bổ sung |
| 7 | Conflict là lỗi dữ liệu đã tồn tại; thiếu quyền liên quan ACL; lỗi TLS/network có thể là sự cố tạm thời hoặc kết quả chưa chắc chắn |
| 8 | Với JNDI thuần thường là class `javax.naming`; với service dùng `LdapTemplate` bắt kiểu exception đã được Spring LDAP chuyển đổi, kiểm tra version/provider |

### Bài tập thiết kế API

Một endpoint tạo hồ sơ nhân viên chỉ chấp nhận `uid`, `cn` và `sn`. Hãy xây dựng bảng phản hồi gồm ba trạng thái chính:

| Kết quả backend | Trạng thái nghiệp vụ | Phản hồi gợi ý |
| --- | --- | --- |
| `bind(...)` hoàn tất và server xác nhận thành công | Tạo mới | `201 Created` |
| `NameAlreadyBoundException` xác định | Trùng định danh | `409 Conflict` hoặc thông báo chung nếu cần chống enumeration |
| Timeout sau khi gửi Add, chưa rõ server đã xử lý | Kết quả chưa xác định | Không tự trả “đã tồn tại”; theo dõi trạng thái, đối chiếu trước khi retry |

**Mở rộng:** đề xuất một chiến lược idempotency có thể chứng minh “entry hiện có chính là entry của request đã tạo” mà không đọc/tiết lộ dữ liệu không được phép. Có thể dùng một khóa idempotency lưu ở tầng ứng dụng, kèm quyền và cơ chế xác nhận kết quả ghi, thay vì tự động coi mọi DN trùng là thành công.

## 16. Checklist và điểm cần ghi nhớ

- [ ] `ContextSource.base` đúng; DN đích được xây tương đối bằng `LdapNameBuilder`, không lặp suffix.
- [ ] Parent OU tồn tại, object class và các thuộc tính MUST đúng schema.
- [ ] Thao tác tạo mới dùng **`LdapTemplate.bind(...)`**, không phải LDAP Bind xác thực.
- [ ] Service xử lý **`NameAlreadyBoundException`** rõ ràng và không che các lỗi khác.
- [ ] Không coi search pre-check là khóa chống race; LDAP Add là nơi cuối cùng quyết định DN đã tồn tại hay chưa.
- [ ] Không thay mọi lời gọi `bind` bằng `rebind` để tránh lỗi trùng.
- [ ] Kiểm soát uniqueness ở đúng phạm vi nghiệp vụ: **DN** khác với **UID toàn tổ chức**.
- [ ] Khi timeout sau thao tác ghi, xác minh trạng thái trước khi retry; không suy luận quá mức từ result 68 ở lần thử tiếp.
- [ ] Tài khoản dịch vụ có ACL tối thiểu, kết nối dùng LDAPS/StartTLS với chứng chỉ hợp lệ, secret được bảo vệ.
- [ ] API không tiết lộ thông tin tài khoản có sẵn ngoài phạm vi được phép.
- [ ] Unit test việc xây DN/attributes và mapping nghiệp vụ; integration test tạo trùng trên LDAP server lab.

**Ghi nhớ cốt lõi:** `NameAlreadyBoundException` trong ngữ cảnh tạo entry là tín hiệu rằng **Add không thể tạo thêm entry tại DN đã tồn tại**. Hãy biến nó thành một kết quả nghiệp vụ có chủ đích, không coi đó là lý do để vô tình ghi đè, tăng quyền hoặc retry không kiểm soát.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Java SE 17 — JNDI NameAlreadyBoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/NameAlreadyBoundException.html)
- [RFC 4511 — Lightweight Directory Access Protocol, Add operation và result codes](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
