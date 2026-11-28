# Định danh bằng entryUUID hoặc objectGUID

Trong **Spring Data LDAP**, một entry thường được truy cập thông qua **Distinguished Name (DN)**, chẳng hạn **uid=linh,ou=people,dc=lab,dc=example**. DN vừa mô tả vị trí trong cây thư mục, vừa có thể thay đổi khi entry được đổi tên hoặc chuyển sang OU khác. Nếu ứng dụng lấy DN làm khóa bất biến trong cơ sở dữ liệu nghiệp vụ, các lần đổi DN có thể làm đứt liên kết với người dùng, nhóm hoặc tài khoản dịch vụ đã được lưu trước đó.

Nhiều directory server cung cấp một định danh ổn định hơn DN: **OpenLDAP** có thuộc tính **entryUUID**, còn **Microsoft Active Directory Domain Services (AD DS)** sử dụng **objectGUID**. Hai thuộc tính này cùng phục vụ việc nhận diện entry qua những thay đổi tên hoặc vị trí, nhưng **khác schema, kiểu dữ liệu, cách truyền trên LDAP và cách tìm kiếm**. Không thể thay thế tên thuộc tính hoặc ép kiểu Java một cách máy móc.

Bài học thuộc chương **Khác biệt máy chủ**. Người học sẽ hiểu DN, objectClass và identifier; đọc được **entryUUID** và **objectGUID**; chuyển đổi 16 byte GUID của AD thành **java.util.UUID** đúng thứ tự; tổ chức một lớp ánh xạ kết quả bằng **LdapTemplate** bên cạnh **Spring Data LDAP Repository**; và kiểm thử trên directory phù hợp, có chú ý tới ACL, TLS, replication và tính an toàn của filter.

## 1. Vì sao DN không phải khóa định danh bất biến?

Một LDAP directory có cấu trúc cây (Directory Information Tree, **DIT**):

~~~text
dc=lab,dc=example
├── ou=people
│   └── uid=linh
└── ou=teams
    └── ou=platform
~~~

DN ban đầu:

~~~text
uid=linh,ou=people,dc=lab,dc=example
~~~

Nếu quản trị viên chuyển entry sang nhánh khác, DN trở thành:

~~~text
uid=linh,ou=platform,ou=teams,dc=lab,dc=example
~~~

Nếu đổi giá trị RDN hoặc đổi tên entry, DN cũng thay đổi. Một chương trình chỉ giữ DN ban đầu có thể gặp **noSuchObject (32)** khi lookup DN cũ, mặc dù entry vẫn tồn tại dưới tên mới. Điều này tác động trực tiếp tới các chức năng **LDAP CRUD**, mapping **@Id** và những khóa ngoại do ứng dụng tự lưu.

Sự khác biệt cốt lõi:

| Thuật ngữ | Ý nghĩa | Có thể thay đổi khi rename/move? |
| --- | --- | --- |
| **DN** | Tên phân cấp, chứa RDN của entry và các entry cha | **Có** |
| **RDN** | Một thành phần tên của entry, ví dụ uid=linh | **Có** |
| **uid / cn / sAMAccountName** | Thuộc tính định danh theo nghiệp vụ/quy ước đăng nhập | Có thể đổi và không mặc nhiên duy nhất toàn directory |
| **entryUUID** | Định danh entry do server LDAP hỗ trợ RFC 4530 cấp | Thông thường **không đổi** khi chỉ đổi DN của cùng entry |
| **objectGUID** | Định danh 128-bit do AD DS gán cho object | **Không đổi** khi object được rename/move trong phạm vi được AD hỗ trợ |

**DN vẫn rất cần thiết:** LDAP Search, Add, Modify, Delete và Modify DN hoạt động dựa trên cây và DN. UUID/GUID giúp ứng dụng nhận diện *đó vẫn là cùng một entry* sau khi DN đổi; chúng không tự thay thế DN ở mọi API LDAP.

## 2. So sánh OpenLDAP entryUUID và AD objectGUID

| Đặc điểm | OpenLDAP / entryUUID | Active Directory / objectGUID |
| --- | --- | --- |
| Tên thuộc tính LDAP | **entryUUID** | **objectGUID** |
| Đặc tả | **RFC 4530**: operational attribute, OID 1.3.6.1.1.16.4 | Schema AD, attribute ID 1.2.840.113556.1.4.2 |
| Giá trị điển hình | Chuỗi UUID chuẩn: 8-4-4-4-12 ký tự hex | **16 byte nhị phân**, thường xuất qua LDIF dạng base64 |
| Số giá trị | **SINGLE-VALUE** | **Single-valued** |
| Ai gán? | Server tạo khi thêm entry | Domain controller tạo khi tạo object |
| Người dùng có sửa trực tiếp? | **NO-USER-MODIFICATION** theo RFC 4530 | **systemOnly**, không phải thuộc tính tùy ý ghi qua LDAP Modify |
| Lấy qua LDAP | Yêu cầu rõ **entryUUID** hoặc **+** nếu server hỗ trợ | Yêu cầu rõ **objectGUID** |
| Đọc bằng JNDI | Thường là **String** theo cú pháp UUID | Nên cấu hình nhận **byte[]** |
| Dùng làm khóa trong Java | **UUID.fromString(...)** sau khi kiểm tra | Chuyển từ byte AD theo đúng endian rồi tạo **UUID** |
| Filter tìm theo ID | **(entryUUID=uuid-chuỗi)** | **(objectGUID=giá-trị-binary)**, thường biểu diễn bằng các byte escape |

**Hai giá trị không tự tương đương**, dù Java cuối cùng đều có thể lưu chúng dưới dạng **UUID**. Một người được đồng bộ từ OpenLDAP sang Active Directory có thể trở thành một object mới trong AD với **objectGUID khác entryUUID** của nguồn. Ứng dụng tích hợp nhiều server cần lưu thêm **loại và phạm vi directory**.

## 3. OpenLDAP: entryUUID là operational attribute

**RFC 4530** xác định **entryUUID** là thuộc tính vận hành (**operational attribute**) có cú pháp UUID, một giá trị, do server tạo và không cho người dùng tùy ý chỉnh sửa. Giá trị đó được cấp khi entry được tạo và giữ nguyên trong đời sống của **cùng entry**, kể cả khi DN thay đổi.

Ví dụ một entry nhân viên với những thuộc tính thông thường:

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

**Không đưa entryUUID vào file LDIF để tự chỉ định** khi thêm một entry LDAP theo cách thông thường. Server sẽ gán nó. Những ví dụ ID trong bài chỉ nhằm minh họa kết quả sau khi entry tồn tại.

### 3.1. Vì sao ldapsearch mặc định có thể không hiển thị entryUUID?

LDAP phân biệt **user attributes** và **operational attributes**. Truy vấn chỉ yêu cầu các thuộc tính người dùng, chẳng hạn **uid**, **cn**, **mail**, không nhất thiết trả về **entryUUID**. Đây không phải bằng chứng rằng entry thiếu định danh.

Ví dụ thao tác bằng OpenLDAP client, dùng TLS và bind DN chỉ đọc:

~~~bash
export LDAP_URI='ldaps://ldap.lab.example:636'
export BASE_DN='dc=lab,dc=example'
export BIND_DN='uid=reader,ou=services,dc=lab,dc=example'
export PERSON_DN='uid=linh,ou=people,dc=lab,dc=example'

ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$PERSON_DN" -s base \
  '(objectClass=*)' dn uid cn entryUUID
~~~

**-W** yêu cầu nhập mật khẩu tương tác, tránh đặt password trong lịch sử lệnh. Ví dụ kết quả minh họa:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
uid: linh
cn: Linh Nguyen
entryUUID: 00112233-4455-4677-8899-aabbccddeeff
~~~

Định danh ở đây chỉ là giá trị mẫu; **không** suy ra UUID thật của người dùng từ uid hay DN. Có thể yêu cầu mọi operational attribute với dấu **+** nếu server hỗ trợ:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$PERSON_DN" -s base \
  '(objectClass=*)' '*' '+'
~~~

Dấu **\*** yêu cầu các user attributes; dấu **+** yêu cầu các operational attributes được server hỗ trợ và cho phép trả về. Trong ứng dụng thực tế, **chỉ yêu cầu entryUUID và các trường thật sự cần thiết** sẽ giảm dữ liệu mạng, tránh vô tình thu thập thông tin vận hành không liên quan.

### 3.2. Tìm entry bằng entryUUID

Khi biết UUID đã được server trả về, tìm trên một **base DN đủ rộng để bao gồm vị trí hiện tại**:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$BIND_DN" -W \
  -b "$BASE_DN" -s sub \
  '(entryUUID=00112233-4455-4677-8899-aabbccddeeff)' \
  dn uid cn entryUUID
~~~

**Quan trọng:** Nếu entry đã di chuyển khỏi **ou=people**, tìm dưới OU cũ vẫn trả rỗng dù UUID không đổi. Tìm theo UUID không làm LDAP Search bỏ qua **base DN, scope, ACL, naming context hay index**. Khi có nhiều suffix hoặc referral, ứng dụng phải thiết kế phạm vi tìm kiếm phù hợp.

## 4. Active Directory: objectGUID là giá trị nhị phân

Trong **Active Directory Domain Services**, **objectGUID** là thuộc tính do AD gán lúc tạo object. Thuộc tính có **16 byte**, chỉ chứa một giá trị và không được cập nhật tùy ý. Theo tài liệu Microsoft, nó giữ nguyên khi object được đổi tên hoặc chuyển vị trí trong các thao tác được AD hỗ trợ.

Ví dụ một user object:

~~~text
CN=Linh Nguyen,OU=Employees,DC=corp,DC=example,DC=com
~~~

Giả sử administrator đổi **CN** và chuyển sang **OU=Engineering**. DN thay đổi, nhưng **objectGUID** của cùng object không đổi. Ứng dụng lưu GUID có thể tìm lại DN hiện tại, thay vì dựa mãi vào đường dẫn cũ.

Khi đọc bằng LDAP, **objectGUID không phải một chuỗi UUID thông thường**. Công cụ **ldapsearch** có thể hiển thị dưới dạng LDIF base64:

~~~ldif
dn: CN=Linh Nguyen,OU=Employees,DC=corp,DC=example,DC=com
objectGUID:: MyIRAFVEd2aImaq7zN3u/w==
~~~

**Dấu hai chấm kép (::)** trong LDIF cho biết giá trị được mã hóa base64. Đây là ví dụ với GUID dạng hiển thị **00112233-4455-6677-8899-aabbccddeeff**; các byte nhị phân tương ứng sẽ được giải thích ngay sau đây. Không được đưa nguyên chuỗi base64 đó vào **UUID.fromString(...)**, và không giả định nội dung trả về từ JNDI có kiểu Java String.

### 4.1. Thứ tự byte GUID trong Active Directory

Đây là chi tiết dễ gây lỗi nhất khi tích hợp AD với Java: **ba trường đầu của GUID được mã hóa theo little-endian trong biểu diễn nhị phân của AD**; 8 byte cuối giữ thứ tự byte như trong dạng GUID hiển thị.

Với GUID:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

16 byte nhận từ LDAP tương ứng:

~~~text
33 22 11 00 | 55 44 | 77 66 | 88 99 aa bb cc dd ee ff
   Data1     | Data2 | Data3 |           Data4
little-endian|  LE   |  LE   |   giữ nguyên thứ tự
~~~

Nếu dùng **ByteBuffer** đọc 16 byte theo big-endian mặc định như một UUID chuẩn, kết quả sẽ khác giá trị Microsoft hiển thị. Sự khác biệt này không phải do AD gán GUID mới; đó là **lỗi giải mã dữ liệu** ở phía Java.

### 4.2. objectGUID khác objectSid và sAMAccountName

| Trường AD | Công dụng chính | Có phù hợp làm khóa entry ổn định? |
| --- | --- | --- |
| **distinguishedName** | Định vị object trong cây LDAP | Không ổn định khi rename/move |
| **sAMAccountName** | Tên tài khoản đăng nhập kiểu Windows | Có thể đổi; còn chịu quy tắc duy nhất theo domain |
| **userPrincipalName** | Tên đăng nhập kiểu UPN | Có thể đổi; không phải định danh bất biến |
| **objectSid** | Security identifier của security principal, quan trọng với ACL/authorization | Không đồng nghĩa GUID; có thể đổi theo một số thao tác chuyển domain |
| **objectGUID** | Định danh của directory object | Nên dùng để nhận diện cùng object trong phạm vi AD phù hợp |

**objectGUID không phải thông tin xác thực.** Biết GUID của một user không chứng minh client được phép đọc, sửa hoặc đăng nhập dưới danh tính user đó. LDAP server vẫn phải kiểm tra **bind identity** và ACL.

## 5. Vòng đời định danh: rename, move, delete, recreate

Tính ổn định của một ID cần được hiểu theo **vòng đời của cùng entry/object**:

| Thao tác | DN | entryUUID / objectGUID | Diễn giải |
| --- | --- | --- | --- |
| **Đổi RDN** trong cùng directory | Đổi | Giữ nguyên với cùng entry/object | Nhận diện vẫn là đối tượng cũ |
| **Chuyển OU** bằng Modify DN hợp lệ | Đổi | Giữ nguyên với cùng entry/object | Có thể tìm lại theo định danh ở vùng chứa mới |
| **Sửa cn, mail, description** | Thường không đổi, trừ khi sửa RDN | Giữ nguyên | Identifier không phải phiên bản thay đổi |
| **Đồng bộ qua replica cùng hệ thống** | Phụ thuộc topology | Dự kiến giữ định danh của cùng object khi replication hỗ trợ | Phải kiểm tra nhất quán và độ trễ |
| **Xóa hẳn rồi tạo entry mới với DN cũ** | Có thể giống hệt | **Thông thường khác** | Không được coi object mới là object cũ |
| **Export/import thành object mới ở directory khác** | Có thể giống hoặc khác | Không bảo đảm giữ nguyên | Cần mapping nguồn–đích riêng |
| **Move cross-domain/cross-forest hoặc migration** | Đổi | Phụ thuộc sản phẩm, đường di chuyển và cách tạo object | Không tự hứa GUID giữ nguyên qua mọi migration |

**Cảnh báo quan trọng:** Nếu entry được **xóa rồi tạo mới** với cùng **DN, uid, cn**, ứng dụng dùng DN làm khóa có thể nhầm đó là đối tượng cũ. Ở phía ngược lại, dùng UUID/GUID cho phép phát hiện có thể đó là một object mới; dữ liệu nghiệp vụ liên kết với object cũ cần được đối soát thay vì gán sang object mới một cách tự động.

Sự tồn tại của định danh ổn định **không cung cấp optimistic locking**. Hai request cùng đọc entry rồi ghi đè một attribute vẫn có thể gặp **lost update**. **entryUUID/objectGUID trả lời “entry nào?”**, còn cơ chế kiểm soát phiên bản/xung đột trả lời “entry này đã thay đổi kể từ lần tôi đọc chưa?”.

## 6. Chiến lược nhận diện đối tượng trong ứng dụng Java

Nếu ứng dụng chỉ cần lookup nhanh theo DN hiện tại, lưu DN có thể đủ. Nhưng nếu lưu quan hệ nghiệp vụ tồn tại lâu dài (nhân sự, quyền nội bộ, lịch sử phê duyệt), nên tách:

~~~mermaid
flowchart TD
    A["Directory A: OpenLDAP"] --> B["entryUUID + directoryId"]
    C["Directory B: Active Directory"] --> D["objectGUID + directoryId"]
    B --> E["Stable Directory Reference"]
    D --> E
    E --> F["Bảng liên kết nghiệp vụ / cache"]
    E --> G["Resolver: lookup DN hiện tại"]
    G --> H["LDAP Search theo ID trong đúng directory"]
    H --> I["DN hiện tại + các thuộc tính cần đọc"]
~~~

Đề xuất mô hình dữ liệu:

~~~java
import java.util.UUID;

public record DirectoryReference(
        String directoryId,
        IdentifierKind kind,
        UUID value) {

    public enum IdentifierKind {
        OPENLDAP_ENTRY_UUID,
        ACTIVE_DIRECTORY_OBJECT_GUID
    }
}
~~~

Ví dụ lưu trong bảng hoặc sự kiện nghiệp vụ:

~~~text
directory_id     = corp-ad-main
identifier_kind  = ACTIVE_DIRECTORY_OBJECT_GUID
identifier_value = 00112233-4455-6677-8899-aabbccddeeff
last_seen_dn     = CN=Linh Nguyen,OU=Employees,DC=corp,DC=example,DC=com
~~~

- **directoryId** là tên logic được tổ chức quản lý cho một directory/nguồn danh tính; không nên sử dụng một hostname replica ngẫu nhiên làm khóa duy nhất.
- **kind** phân biệt schema và cách giải mã.
- **value** là UUID đã chuẩn hóa. Với AD, phải chuyển đổi từ byte nhị phân trước.
- **lastSeenDn** là vị trí quan sát gần nhất, dùng như cache hoặc thông tin hiển thị, **không** thay thế định danh bền vững.

Nếu cùng một người có object trong hai directory, **không tự nối hai record chỉ vì uid/email/cn giống nhau**. Việc ánh xạ xuyên directory là bài toán identity reconciliation cần quy tắc xác minh riêng.

## 7. Spring LDAP: đọc entryUUID của OpenLDAP bằng LdapTemplate

Giả sử ứng dụng Spring Boot cấu hình:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.lab.example:636"
    base: "dc=lab,dc=example"
    username: "uid=reader,ou=services,dc=lab,dc=example"
    password: "${LDAP_BIND_PASSWORD}"
~~~

**ContextSource base** là **dc=lab,dc=example**, do đó **ou=people** trong truy vấn là base DN tương đối. Vì **entryUUID là operational attribute**, cần yêu cầu nó tường minh:

~~~java
import java.util.List;
import java.util.UUID;
import javax.naming.directory.Attribute;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class OpenLdapIdentityReader {
    private final LdapTemplate ldapTemplate;

    public OpenLdapIdentityReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record EntryIdentity(String uid, UUID entryUuid) {}

    public List<EntryIdentity> findByUid(String uid) {
        return ldapTemplate.search(
            query().base("ou=people")
                   .attributes("uid", "entryUUID")
                   .where("uid").is(uid),
            (AttributesMapper<EntryIdentity>) attrs -> {
                Attribute rawId = attrs.get("entryUUID");
                if (rawId == null || rawId.size() != 1) {
                    throw new IllegalStateException(
                        "entryUUID is not visible in LDAP result");
                }
                Object value = rawId.get();
                if (!(value instanceof String text)) {
                    throw new IllegalStateException(
                        "Unexpected OpenLDAP entryUUID value type");
                }
                return new EntryIdentity(
                    (String) attrs.get("uid").get(),
                    UUID.fromString(text)
                );
            }
        );
    }
}
~~~

**query().where("uid").is(uid)** giúp escape dữ liệu vào filter đúng ngữ cảnh, tránh LDAP filter injection. **attrs.get("entryUUID")** có thể vắng nếu ACL hạn chế hoặc server không trả operational attribute theo yêu cầu. Khi thiếu định danh cần thiết cho mapping, báo lỗi có ý nghĩa hơn là âm thầm tạo UUID mới trong Java.

Ví dụ **AttributesMapper** chỉ đọc các attribute, **không tự cung cấp DN** của entry. Nếu cần trả đồng thời DN hiện tại, có thể sử dụng **ContextMapper** để lấy **DirContextOperations.getDn()** và các attribute; DN nhận được thường là **tương đối với ContextSource base**. Không tự coi chuỗi đó là DN đầy đủ.

### 7.1. Tìm theo entryUUID bằng Spring LDAP

Sau khi có UUID hợp lệ, câu truy vấn có thể dùng **matching rule uuidMatch** của server:

~~~java
import java.util.List;
import java.util.UUID;
import org.springframework.ldap.core.AttributesMapper;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public List<String> findCurrentUidsById(UUID stableId) {
    return ldapTemplate.search(
        query().base("")
               .attributes("uid", "entryUUID")
               .where("entryUUID").is(stableId.toString()),
        (AttributesMapper<String>) attrs ->
            (String) attrs.get("uid").get()
    );
}
~~~

Đây là phần phương thức minh họa **đặt bên trong service có field ldapTemplate**. **base("")** bắt đầu từ base của ContextSource; nó phù hợp khi entry có thể đổi OU trong cùng suffix. Với directory nhiều suffix, phải tìm trong naming context được phép và có dữ liệu, không suy ra toàn mạng LDAP là một cây duy nhất.

Nếu entry đã bị xóa và tạo lại, UUID cũ không khớp object mới. Nếu tài khoản bind không có quyền tìm kiếm trên nhánh mới, câu truy vấn có thể trả rỗng dù ID vẫn tồn tại ở server.

## 8. Java: chuyển objectGUID của Active Directory sang UUID

**java.util.UUID** biểu diễn GUID chuẩn ở dạng hai phần 64-bit. Tuy nhiên, **16 byte objectGUID của AD** có thứ tự byte hỗn hợp; vì vậy **không nên chỉ gọi UUID.nameUUIDFromBytes(...)**, cũng không thể dùng **UUID.fromString(...)** trực tiếp với dữ liệu byte hoặc base64.

Một converter thuần Java, dùng được với JDK 17+:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Objects;
import java.util.UUID;

public final class ActiveDirectoryGuid {
    private ActiveDirectoryGuid() {}

    public static UUID fromLdapBytes(byte[] bytes) {
        Objects.requireNonNull(bytes, "objectGUID bytes");
        if (bytes.length != 16) {
            throw new IllegalArgumentException(
                "objectGUID must contain exactly 16 bytes");
        }

        ByteBuffer buffer = ByteBuffer.wrap(bytes)
            .order(ByteOrder.LITTLE_ENDIAN);
        long data1 = Integer.toUnsignedLong(buffer.getInt());
        long data2 = Short.toUnsignedLong(buffer.getShort());
        long data3 = Short.toUnsignedLong(buffer.getShort());

        long mostSignificant =
            (data1 << 32) | (data2 << 16) | data3;

        // Data4 dùng thứ tự byte như GUID hiển thị.
        long leastSignificant =
            ByteBuffer.wrap(bytes, 8, 8)
                      .order(ByteOrder.BIG_ENDIAN)
                      .getLong();

        return new UUID(mostSignificant, leastSignificant);
    }

    public static byte[] toLdapBytes(UUID uuid) {
        Objects.requireNonNull(uuid, "uuid");

        long high = uuid.getMostSignificantBits();
        ByteBuffer buffer = ByteBuffer.allocate(16)
            .order(ByteOrder.LITTLE_ENDIAN);
        buffer.putInt((int) (high >>> 32)); // Data1
        buffer.putShort((short) (high >>> 16)); // Data2
        buffer.putShort((short) high); // Data3
        buffer.order(ByteOrder.BIG_ENDIAN);
        buffer.putLong(uuid.getLeastSignificantBits()); // Data4

        return buffer.array();
    }
}
~~~

**Kiểm tra bằng test vector đã biết:**

~~~java
import java.util.Arrays;
import java.util.HexFormat;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

UUID expected = UUID.fromString(
    "00112233-4455-6677-8899-aabbccddeeff");

byte[] raw = HexFormat.of().parseHex(
    "33221100554477668899aabbccddeeff");

assertEquals(expected, ActiveDirectoryGuid.fromLdapBytes(raw));
assertArrayEquals(raw, ActiveDirectoryGuid.toLdapBytes(expected));
~~~

Ví dụ test này là **phần thân một phương thức @Test** và yêu cầu JUnit; không phải file Java độc lập. Phép kiểm tra hai chiều giúp phát hiện các lỗi đảo byte, cắt chuỗi UUID hoặc chuyển đổi base64 không đúng.

### 8.1. Kết quả LDIF base64 được xử lý thế nào?

Nếu **ldapsearch** trả **objectGUID::** kèm base64, bước hợp lý là:

~~~java
import java.util.Base64;
import java.util.UUID;

String ldapBase64 = "MyIRAFVEd2aImaq7zN3u/w==";
byte[] bytes = Base64.getDecoder().decode(ldapBase64);
UUID canonical = ActiveDirectoryGuid.fromLdapBytes(bytes);
// canonical: 00112233-4455-6677-8899-aabbccddeeff
~~~

Với **JNDI**, mục tiêu là nhận thẳng **byte[]** từ thuộc tính objectGUID; không cần chuyển sang base64 rồi lại giải mã trong ứng dụng. Base64 trong LDIF chỉ là cách **biểu diễn trên văn bản**.

## 9. JNDI: yêu cầu objectGUID dạng byte[] và tìm theo GUID

LDAP provider mặc định trong JDK hỗ trợ thuộc tính môi trường:

~~~text
java.naming.ldap.attributes.binary = objectGUID
~~~

Giá trị là danh sách tên thuộc tính cách nhau bởi dấu cách, ví dụ **objectGUID objectSid**, để provider trả các thuộc tính tương ứng dưới dạng **byte[]** thay vì cố chuyển sang String.

Với Spring Boot/JNDI, có thể bổ sung:

~~~yaml
spring:
  ldap:
    urls: "ldaps://dc1.corp.example.com:636"
    base: "DC=corp,DC=example,DC=com"
    username: "CN=LDAP Reader,OU=Service Accounts,DC=corp,DC=example,DC=com"
    password: "${LDAP_BIND_PASSWORD}"
    base-environment:
      "[java.naming.ldap.attributes.binary]": "objectGUID objectSid"
~~~

Chỉ dùng cấu hình khi backend tương ứng là AD và tên thuộc tính có ý nghĩa. Với Java, có thể dùng **DirContext.search(...)** và filter arguments nhị phân; JNDI LDAP provider hỗ trợ **byte[]** làm đối số filter cho thuộc tính dạng binary:

~~~java
import java.util.Hashtable;
import java.util.Objects;
import java.util.UUID;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

public final class AdGuidLookup {
    public static void main(String[] args) throws Exception {
        UUID id = UUID.fromString(
            "00112233-4455-6677-8899-aabbccddeeff");
        byte[] objectGuidBytes =
            ActiveDirectoryGuid.toLdapBytes(id);

        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL,
            "ldaps://dc1.corp.example.com:636");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL,
            "CN=LDAP Reader,OU=Service Accounts,"
                + "DC=corp,DC=example,DC=com");
        env.put(Context.SECURITY_CREDENTIALS,
            Objects.requireNonNull(
                System.getenv("LDAP_BIND_PASSWORD")));
        env.put("java.naming.ldap.attributes.binary", "objectGUID");
        env.put("com.sun.jndi.ldap.connect.timeout", "3000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(
            new String[]{"objectGUID", "distinguishedName"});

        DirContext ctx = null;
        NamingEnumeration<SearchResult> results = null;
        try {
            ctx = new InitialDirContext(env);
            results = ctx.search(
                "DC=corp,DC=example,DC=com",
                "(objectGUID={0})",
                new Object[]{objectGuidBytes},
                controls
            );

            while (results.hasMore()) {
                SearchResult result = results.next();
                Attribute attr =
                    result.getAttributes().get("objectGUID");
                if (attr == null || !(attr.get() instanceof byte[] raw)) {
                    throw new IllegalStateException(
                        "objectGUID is missing or not binary");
                }
                UUID found = ActiveDirectoryGuid.fromLdapBytes(raw);
                System.out.println(found);
                System.out.println(result.getNameInNamespace());
            }
        } finally {
            try {
                if (results != null) {
                    results.close();
                }
            } finally {
                if (ctx != null) {
                    ctx.close();
                }
            }
        }
    }
}
~~~

Điểm quan trọng của ví dụ:

1. **objectGUID={0}** dùng đối số **byte[]** đã chuyển đúng định dạng AD, không gắn trực tiếp chuỗi UUID vào filter.
2. **SearchControls.setReturningAttributes(...)** yêu cầu objectGUID rõ ràng.
3. **objectGUID được parse trước khi dùng**; một chuỗi UUID không hợp lệ không được đưa thẳng vào LDAP filter.
4. **getNameInNamespace()** trả DN hiện tại của entry theo JNDI context, giúp ứng dụng nhận biết việc đổi OU/CN.
5. **InitialDirContext** và **NamingEnumeration** được đóng để tránh giữ kết nối/tài nguyên.
6. TLS cần chứng chỉ hợp lệ được JVM tin cậy. Ví dụ chỉ chạy khi đã có endpoint, bind DN, ACL và truststore phù hợp; không đưa mật khẩu thật vào code.

Nếu truy vấn trả rỗng, kiểm tra **base DN, ACL, filter bytes và directory thực đang kết nối** trước khi kết luận GUID không tồn tại.

### 9.1. Filter octet-escaped để chẩn đoán từ ldapsearch

Trong LDAP filter, dữ liệu nhị phân có thể được biểu diễn theo **RFC 4515** bằng các octet escape **\hh** (hai ký tự hex trên mỗi byte). Với test vector trên, filter đúng là:

~~~text
(objectGUID=\33\22\11\00\55\44\77\66\88\99\aa\bb\cc\dd\ee\ff)
~~~

Ví dụ gọi OpenLDAP client tới AD DS, đặt filter trong **dấu nháy đơn** để shell không xử lý các dấu backslash:

~~~bash
ldapsearch -LLL -x -H 'ldaps://dc1.corp.example.com:636' \
  -D 'CN=LDAP Reader,OU=Service Accounts,DC=corp,DC=example,DC=com' -W \
  -b 'DC=corp,DC=example,DC=com' -s sub \
  '(objectGUID=\33\22\11\00\55\44\77\66\88\99\aa\bb\cc\dd\ee\ff)' \
  dn objectGUID
~~~

**Không đảo byte dựa trên ký tự của UUID bằng phép reverse toàn bộ chuỗi.** Chỉ ba nhóm Data1/Data2/Data3 được đảo theo quy tắc GUID nhị phân; 8 byte cuối giữ nguyên. Trong code production, ưu tiên **byte[] + filter arguments** với provider đã kiểm chứng, thay vì ghép filter từ input tùy ý.

## 10. Spring Data LDAP Repository và khóa @Id

Spring Data LDAP ánh xạ entry thành Java object qua **@Entry**, **@Attribute**, **@Id** và **LdapRepository**. Tuy nhiên, trong LDAP ODM, **@Id đại diện cho DN**, không tự đổi sang entryUUID hoặc objectGUID.

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    // Constructors và getters/setters được lược bỏ.
}
~~~

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

Các lời gọi **findById(...)**, **save(...)**, **delete(...)** của repository vẫn làm việc theo ngữ nghĩa LDAP và mapping DN. Đừng thay field **Name dn** bằng **UUID id** rồi kỳ vọng repository tự dùng entryUUID/objectGUID làm primary key như Spring Data JPA.

Chiến lược tốt hơn khi ứng dụng cần ID ổn định:

- **Repository** phục vụ CRUD và mapping entry trong cây LDAP.
- **Identity reader/resolver** đọc entryUUID hoặc objectGUID bằng API phù hợp, có thể là **LdapTemplate** hoặc JNDI.
- **Domain service** giữ cặp **directoryId + kind + UUID** và tra cứu lại DN hiện tại khi cần thay đổi entry.
- **Không tự cập nhật entryUUID/objectGUID** khi save entity: chúng là thuộc tính do directory cấp, không phải trường CRUD thông thường.

**Cảnh báo mapping:** Việc gắn **@Attribute(name = "entryUUID")** hoặc **@Attribute(name = "objectGUID")** lên entity rồi gọi **save** có thể tương tác với cơ chế đồng bộ thuộc tính của ODM theo cách không mong muốn nếu không cấu hình chỉ đọc/phạm vi cập nhật. Cách an toàn cho bài học là **đọc hai trường này qua projection/mapper riêng** và không đưa chúng vào lệnh Modify. Trong dự án thực, kiểm tra API read-only mapping được phiên bản Spring LDAP hỗ trợ trước khi sử dụng.

## 11. Mức trừu tượng nào nên dùng khi hỗ trợ nhiều LDAP server?

Một service truy vấn cả OpenLDAP và AD cần xử lý **khác biệt nhà cung cấp** tại lớp adapter, thay vì để controller hoặc domain logic biết chi tiết 16 byte little-endian:

~~~java
import java.util.Optional;
import java.util.UUID;

public interface DirectoryIdentityResolver {
    Optional<String> resolveCurrentDn(UUID stableId);
}
~~~

Hai implementation có thể khác nhau:

| Adapter | Cách tìm | Cách đọc ID |
| --- | --- | --- |
| **OpenLdapIdentityResolver** | Filter **entryUUID** trên suffix phù hợp | UUID String → UUID.fromString |
| **ActiveDirectoryIdentityResolver** | Filter **objectGUID** bằng byte[] hoặc octet-escaped | byte[16] → ActiveDirectoryGuid.fromLdapBytes |

Nếu có nhiều directory, interface thực tế nên nhận thêm **DirectoryReference** hoặc đối tượng chỉ rõ nguồn. **Optional.empty()** chỉ phù hợp khi tìm kiếm đã hoàn tất thành công mà không có entry. Lỗi TLS, invalidCredentials, referral, ACL hoặc timeout **không nên bị đổi thành Optional.empty()**.

Một khi đã resolve được DN hiện tại, có thể tiếp tục dùng **LdapTemplate.lookup(...)**, repository hoặc thao tác **Modify** trong chính context/source hợp lệ. Khi có concurrent rename/move, DN vẫn có thể đổi giữa lúc resolve và lúc sửa; service cần xử lý **noSuchObject** và chính sách retry có giới hạn thay vì tự khẳng định lookup UUID tạo ra khóa bất biến xuyên mọi bước.

## 12. Bảo mật, ACL và quyền riêng tư của identifier

Một identifier không phải password, nhưng vẫn có giá trị bảo mật và quyền riêng tư:

- **ACL:** Tài khoản ứng dụng cần quyền tìm/đọc **entryUUID** hoặc **objectGUID**. Bind thành công không chứng minh được attribute hiện diện trong SearchResult. Nếu thiếu trường, phân biệt chưa yêu cầu nó, thiếu quyền, không đúng server hoặc entry không tồn tại.
- **TLS:** Dùng **LDAPS/StartTLS** có xác minh chứng chỉ để bảo vệ thông tin bind và dữ liệu được truy vấn; không bỏ kiểm tra hostname/truststore để lấy được GUID.
- **Filter:** Với entryUUID, parse/chuẩn hóa UUID trước khi tạo query. Với objectGUID, dùng 16 byte đúng định dạng và JNDI filter arguments hoặc encoder RFC 4515 kiểm chứng được. Không ghép giá trị HTTP chưa kiểm tra vào LDAP filter.
- **Authorization:** Người biết GUID không được tự động xem hoặc sửa object. Server vẫn kiểm tra bind DN và ACL; ứng dụng phải kiểm tra thêm quyền nghiệp vụ của người gọi API.
- **Ghi log:** UUID/GUID ổn định là dữ liệu có thể dùng để liên kết hoạt động qua thời gian. Chỉ log khi cần, hạn chế phạm vi truy cập log và không đưa toàn bộ DN/thuộc tính cá nhân vào thông điệp công khai.
- **Giới hạn truy vấn:** Tìm theo GUID trên cả suffix có thể tốn tài nguyên; đặt base/scope, size/time limit và xem index hoặc phạm vi GC/replica phù hợp.
- **Secret management:** Không hardcode mật khẩu bind vào Java, YAML hoặc script chia sẻ; không in biến **LDAP_BIND_PASSWORD** ra console.

Đừng lẫn lộn **UUID/GUID dùng nhận diện object** với **SID/chính sách nhóm dùng phân quyền** ở Active Directory. Khả năng đọc được identifier không cấp thêm quyền thao tác với object.

## 13. Tình huống nhất quán, replication và tích hợp

### 13.1. Rename/move cùng directory

Ứng dụng lưu **entryUUID** hoặc **objectGUID** và cache DN cũ. Khi gặp **NameNotFoundException** ở DN cũ, có thể thử tìm lại theo identifier trên một search base thích hợp. Nếu tìm thấy, cập nhật **lastSeenDn** rồi thực hiện lại thao tác đọc. Với lệnh ghi, cần xem xét tính idempotent và biến đổi đồng thời, không retry tùy tiện.

### 13.2. Xóa và tái tạo với cùng uid

Nếu người quản trị xóa rồi tạo lại **uid=linh**, entry mới có thể giữ uid và DN cũ nhưng nhận UUID/GUID mới. Ứng dụng không nên tự chuyển mọi quan hệ lịch sử, quyền hoặc dữ liệu nhạy cảm của object cũ sang object mới chỉ vì cùng uid.

### 13.3. Replication đa máy chủ

Các replica trong cùng hệ thống directory thường được kỳ vọng tái hiện cùng object và định danh, nhưng dữ liệu có thể **chưa đồng bộ tại thời điểm đọc**. Khi search theo ID trả rỗng trên node B nhưng có kết quả ở node A, cần xác định endpoint, naming context, replication lag và cấu hình global catalog/referral. Identifier ổn định không tạo ra read-after-write consistency trên mọi replica.

### 13.4. Chuyển directory hoặc đồng bộ người dùng

Một hệ thống đồng bộ từ OpenLDAP sang AD có thể tạo user object mới trên AD. Dù hai object đại diện cho cùng người ngoài đời, chúng thường có **hai ID directory khác nhau**. Nếu có yêu cầu hợp nhất, lưu bảng ánh xạ nguồn–đích qua quy trình được phê duyệt; không giả định entryUUID = objectGUID.

## 14. Kiểm thử tích hợp trên hai loại directory

Test mock chỉ xác nhận hàm chuyển đổi và logic Java; không xác nhận schema, ACL, objectClass hay hành vi LDAP server. Cần có test riêng cho **OpenLDAP** và **AD DS**, hoặc môi trường lab có cùng đặc tính tương ứng.

| Kịch bản | Kiểm thử với OpenLDAP | Kiểm thử với AD DS |
| --- | --- | --- |
| Tạo object mới | Server tự sinh **entryUUID** | Domain controller tự sinh **objectGUID** |
| Đọc ID | Request explicit **entryUUID** | Request explicit **objectGUID**, nhận **byte[]** |
| Kiểm tra định dạng | Parse String bằng UUID.fromString | Chuyển byte[16] bằng converter |
| Rename/move | Đọc ID trước/sau Modify DN | Đọc GUID trước/sau rename/move được hỗ trợ |
| Lookup ID sau move | Search theo entryUUID từ base đủ rộng | Filter byte objectGUID từ naming context phù hợp |
| Xóa và tạo lại | ID mới khác ID cũ | GUID mới khác GUID cũ |
| ACL | Bind reader có/không có quyền đọc/search entryUUID | Reader có/không có quyền đọc objectGUID |
| Replication | Kiểm tra cùng entry trên những replica được cấu hình | Kiểm tra trên DC/GC và domain phù hợp |
| Lỗi mapping | Thuộc tính chưa requested, String không hợp lệ | Byte sai độ dài, nhầm endian, JNDI trả String |

### 14.1. Những phép thử tối thiểu

1. **Unit test converter:** dùng vector GUID **00112233-4455-6677-8899-aabbccddeeff**, kiểm tra cả từ byte sang UUID và từ UUID về byte. Với input dài 15 hoặc 17 byte phải báo lỗi.
2. **Integration test OpenLDAP:** thêm một entry giả, đọc entryUUID, đổi DN, đọc lại và xác nhận **UUID giữ nguyên**. Không tự thêm entryUUID vào LDIF.
3. **Integration test AD:** đọc objectGUID dưới dạng byte[], chuyển UUID, truy vấn lại bằng byte[] filter, so sánh DN/objectGUID.
4. **Search base:** đưa entry sang OU khác và chứng minh search theo ID dưới OU cũ có thể không thấy, nhưng tìm từ suffix phù hợp có thể thấy.
5. **ACL:** dùng tài khoản giống ứng dụng thực, không chỉ tài khoản admin.
6. **Recreate:** xóa và thêm object mới có cùng tên trong môi trường lab, xác minh định danh mới khác.
7. **Failure path:** thiếu quyền, lỗi TLS, timeout, sai filter và sai thuộc tính phải được phân biệt với “không tìm được object”.

Khi so sánh UUID, nên so sánh **đối tượng UUID/canonical form** thay vì so sánh chuỗi có dấu ngoặc, chữ hoa/chữ thường hay base64. Với objectGUID, phải kiểm tra byte-order bằng test vector cố định để tránh unit test hai hàm cùng sai nhưng vẫn round-trip thành công.

## 15. Các lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **ldapsearch không trả entryUUID** | Chưa yêu cầu operational attribute, ACL hạn chế hoặc server không hỗ trợ | Request **entryUUID** tường minh; kiểm tra Root DSE/schema và quyền |
| **objectGUID hiển thị dấu :: trong LDIF** | Giá trị là bytes được encode base64 | Decode base64 rồi chuyển endian phù hợp |
| **UUID Java khác GUID AD hiển thị** | Xử lý cả 16 byte theo cùng endian hoặc đảo byte sai | Kiểm tra Data1/Data2/Data3 bằng test vector |
| **ClassCastException: String → byte[]** | JNDI không đánh dấu objectGUID là binary | Cấu hình **java.naming.ldap.attributes.binary** |
| **UUID tìm không thấy sau khi đổi OU** | Search base quá hẹp, ACL hoặc replica chưa đồng bộ | Tìm từ suffix được phép; kiểm tra source và replication |
| **Tìm theo UUID có kết quả trên server A nhưng không trên B** | Khác directory, naming context, referral hoặc replication lag | Ghi endpoint và directoryId, kiểm tra topology |
| **Repository.findById không nhận UUID** | @Id của LDAP ODM là **DN**, không phải GUID/UUID | Giữ field Name dn; tách identity resolver |
| **Sửa entryUUID/objectGUID bị từ chối** | Server gán và quản lý thuộc tính | Không Modify; chỉ đọc qua projection |
| **DN cũ trả noSuchObject (32)** | Entry được move/rename, bị xóa hoặc bị ACL che | Tìm lại theo ID, phân biệt deleted/recreated |
| **Có UUID nhưng không được đọc thông tin** | Identifier không phải quyền truy cập | Kiểm tra ACL và authorization nghiệp vụ |

Quy trình chẩn đoán phù hợp: **xác định directory → xác minh bind → yêu cầu identifier tường minh → kiểm tra kiểu String/byte[] → chuẩn hóa UUID → kiểm tra base/filter/ACL → kiểm tra DN mới và trạng thái replica**. Đừng “sửa” lỗi nhầm byte bằng cách tạo mới một GUID tùy ý, vì việc đó sẽ làm hỏng liên kết nghiệp vụ.

## 16. Câu hỏi ôn tập và tổng kết

1. DN khác **entryUUID/objectGUID** ở đặc tính nào khi người dùng bị chuyển OU?
2. Vì sao **entryUUID** có thể không xuất hiện trong output ldapsearch khi chỉ yêu cầu **cn/mail**?
3. Hai dấu hai chấm **objectGUID::** trong LDIF có ý nghĩa gì?
4. Với GUID **00112233-4455-6677-8899-aabbccddeeff**, 16 byte của AD phải được sắp theo thứ tự nào?
5. Vì sao **UUID.fromString(...)** không thể được dùng trực tiếp với thuộc tính objectGUID nhị phân?
6. Tại sao **@Id** trong Spring Data LDAP Repository không tự động trở thành entryUUID hoặc objectGUID?
7. Có thể dùng entryUUID hoặc objectGUID làm **optimistic locking version** hay không?
8. Khi xóa rồi tạo lại entry với cùng DN, định danh ổn định giúp phát hiện điều gì?
9. Vì sao cần lưu thêm **directoryId** và **identifier kind** nếu hệ thống truy cập nhiều directory?
10. Làm thế nào kiểm chứng một ID vẫn nhận diện đúng object sau rename/move, kể cả khi có nhiều replica?

**Ghi nhớ:** **entryUUID** của OpenLDAP và **objectGUID** của Active Directory giúp nhận diện entry/object ổn định hơn **DN**, nhưng không cùng định dạng truyền dữ liệu. **entryUUID** thường đọc dưới dạng chuỗi UUID operational attribute; **objectGUID** là 16 byte theo biểu diễn GUID của Microsoft và cần chuyển đúng endian. Trong Spring Data LDAP, **@Id vẫn là DN**: dùng repository cho LDAP CRUD/mapping và tách một lớp resolver cho khóa bền vững. Luôn gắn ID với directory nguồn, yêu cầu attribute tường minh, kiểm tra ACL/TLS và thử nghiệm trên loại server thực tế.

## Tài liệu tham khảo

- [RFC 4530 — LDAP entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530.html): cú pháp UUID, SINGLE-VALUE, NO-USER-MODIFICATION và hành vi định danh entry.
- [Microsoft — objectGUID attribute schema](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adls/f5f15ec2-427e-4ebe-bb64-2493cf1d032f): OID, kiểu dữ liệu, giới hạn 16 byte và systemOnly.
- [Microsoft — Object-Guid attribute](https://learn.microsoft.com/en-us/windows/win32/adschema/a-objectguid): ID được AD gán và giữ trong đời sống của object.
- [Microsoft — Using objectGUID to Bind to an Object](https://learn.microsoft.com/en-us/windows/win32/ad/using-objectguid-to-bind-to-an-object): vì sao DN thay đổi còn GUID giữ nguyên khi rename/move.
- [Microsoft — GUID binary order in LDAP filters](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-5136): đảo byte ba nhóm đầu trước khi tạo filter.
- [Oracle — JNDI/LDAP Attributes Binary](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap-gl.html): **java.naming.ldap.attributes.binary** và kiểu giá trị JNDI.
- [Java JNDI — DirContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/DirContext.html): LDAP search với tham số filter nhị phân.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): ánh xạ kết quả và truy vấn LDAP.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, @Entry và LDAP object-directory mapping.
