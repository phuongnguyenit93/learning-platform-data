# Phân biệt DN có thể thay đổi với định danh ổn định như entryUUID hoặc objectGUID

Một nhân viên có DN `uid=lan,ou=people,dc=example,dc=org`. Khi tổ chức chuyển người này sang OU `engineering`, DN có thể đổi thành `uid=lan,ou=engineering,dc=example,dc=org`. Nếu hệ thống bên ngoài chỉ lưu DN cũ làm khóa tham chiếu, lần tra cứu tiếp theo có thể thất bại. Tệ hơn, sau khi entry cũ bị xóa, một entry mới có thể được tạo lại đúng DN đó; chuỗi DN vẫn giống nhau nhưng đây là một object khác.

Vì vậy cần tách hai khái niệm:

- **DN (Distinguished Name)** cho biết entry đang nằm ở đâu trong cây directory.
- **Định danh ổn định của entry** giúp nhận diện cùng một object qua việc đổi tên hoặc di chuyển, nếu directory hỗ trợ và giữ nguyên thuộc tính đó.

Trong LDAP, một lựa chọn phổ biến là operational attribute `entryUUID` được định nghĩa trong RFC 4530. Với Microsoft Active Directory, thuộc tính tương ứng thường dùng là `objectGUID`. Hai thuộc tính này không phải một chuẩn chung: `entryUUID` là thuộc tính UUID theo RFC; `objectGUID` là GUID nhị phân theo schema Active Directory. Cả hai đều khác DN về mục đích và cách truy xuất. [RFC 4530](https://www.rfc-editor.org/rfc/rfc4530) · [Microsoft: Object Names and Identities](https://learn.microsoft.com/en-us/windows/win32/ad/object-names-and-identities).

Bài thuộc chương **DN và định danh** của module `SPRING_DATA_LDAP`. Module học cách truy cập directory LDAP qua Spring Data LDAP repository và ánh xạ entry phân cấp sang Java object, bao gồm DN, `objectClass`, schema, repository, `LdapTemplate`, CRUD, filter an toàn, bảo mật kết nối và kiểm thử. Bài này tập trung vào việc chọn đúng định danh, duy trì tham chiếu khi DN thay đổi và tránh nhầm một địa chỉ trong cây với identity lâu dài của object.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao DN có thể đổi khi entry rename hoặc move.
- Phân biệt DN, RDN, `entryUUID`, `objectGUID`, `objectSid` và các thuộc tính nghiệp vụ như `uid`/email.
- Mô tả `entryUUID` theo RFC 4530: operational attribute, server-assigned, single-valued, không cho client sửa và immutable trong vòng đời entry.
- Hiểu `objectGUID` là thuộc tính binary 16 byte riêng của Active Directory, ổn định qua rename/move.
- Nhận biết vì sao xóa rồi tạo lại entry cùng DN không tạo lại identity cũ.
- Đọc `entryUUID` tường minh qua `LdapTemplate` vì operational attributes không được trả mặc định.
- Đọc `objectGUID` dưới dạng `byte[]` và chuyển đổi sang UUID đúng byte order.
- Thiết kế model lưu cả stable identifier và current DN.
- Cập nhật cache, database reference và quan hệ LDAP khi entry di chuyển.
- Xử lý khác biệt giữa LDAP server, Active Directory, replication và migration.
- Kiểm thử rename, move, delete/recreate và lỗi truy xuất identifier.
- Bảo vệ stable identifier trong log, API và dữ liệu đồng bộ.

## 2. DN là địa chỉ trong cây directory, không phải khóa bất biến

DN ghép RDN của entry với các RDN của ancestor đến naming context. Ví dụ:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

DN cho biết entry có RDN `uid=lan`, nằm trong `ou=people`, thuộc naming context `dc=example,dc=org`.

Khi entry được đổi tên hoặc di chuyển:

~~~text
Trước:
uid=lan,ou=people,dc=example,dc=org

Sau:
uid=lan,ou=engineering,dc=example,dc=org
~~~

Object có thể vẫn là cùng một người trong nghiệp vụ, nhưng DN đã thay đổi. DN cũ không còn là địa chỉ hiện tại của entry.

RFC 4530 nêu rõ DN không phải stable identifier: một object mới có thể được nhận diện bằng DN từng thuộc về object khác đã bị rename hoặc delete. Đây là lý do client có thể cần một UUID do directory server gán để phân biệt object. [RFC 4530, Background and Intended Use](https://www.rfc-editor.org/rfc/rfc4530#section-1).

### 2.1. Ba tình huống cần phân biệt

| Tình huống | DN | Identity ổn định |
|---|---|---|
| Rename hoặc move cùng object | Thay đổi | Thường giữ nguyên nếu server hỗ trợ thuộc tính identity và operation giữ nguyên object |
| Delete entry | Không còn DN hiện hành | Identity đó không còn gắn với entry đang tồn tại |
| Add entry mới dùng lại DN cũ | Có thể giống DN cũ | Là identity mới, server cấp identifier mới |

Không được suy luận rằng “DN giống nhau thì object giống nhau”. DN định danh entry hiện tại trong cây; nó có thể được tái sử dụng sau khi entry trước bị xóa.

### 2.2. Ví dụ lỗi khi dùng DN làm foreign key

Giả sử một hệ thống ứng dụng lưu:

~~~text
employee_directory_ref
----------------------
employee_id | ldap_dn
1001        | uid=lan,ou=people,dc=example,dc=org
~~~

Sau khi directory move entry sang OU `engineering`, bản ghi ứng dụng vẫn giữ DN cũ. Một tác vụ đồng bộ theo DN không tìm thấy entry.

Nếu một entry mới được tạo với DN cũ, tác vụ đồng bộ có thể gắn nhầm nhân viên 1001 với object mới. Đây là lỗi identity nghiêm trọng hơn lỗi “không tìm thấy”.

Mô hình an toàn hơn lưu stable identifier làm khóa tham chiếu, đồng thời cập nhật DN hiện tại như một thuộc tính định vị:

~~~text
employee_directory_ref
-----------------------------------------------
employee_id | directory_id | current_dn
1001        | UUID-...     | uid=lan,ou=engineering,...
~~~

`directory_id` là khóa tham chiếu bền vững trong phạm vi directory đã xác định; `current_dn` là địa chỉ cần dùng khi gọi LDAP.

## 3. entryUUID theo RFC 4530

RFC 4530 định nghĩa thuộc tính `entryUUID` để cung cấp UUID do directory server gán cho entry. Đặc điểm chính:

- Server tạo và gán UUID khi entry được thêm vào directory.
- UUID là 128 bit (16 octet).
- Server phải bảo đảm UUID được cấp là duy nhất theo không gian và thời gian, theo yêu cầu của RFC 4530.
- Giá trị được biểu diễn trong LDAP bằng chuỗi UUID ASCII dạng `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`.
- Attribute là single-valued.
- Attribute có `NO-USER-MODIFICATION`.
- Attribute có `USAGE directoryOperation`, tức là operational attribute.
- UUID của entry là immutable theo RFC 4530.
- Client có thể dùng giá trị này để phân biệt object theo DN hoặc tìm object sau khi rename.

[RFC 4530, `2.4 entryUUID](https://www.rfc-editor.org/rfc/rfc4530#section-2.4).

Ví dụ:

~~~text
dn: uid=lan,ou=people,dc=example,dc=org
uid: lan
cn: Lan Nguyen
entryUUID: 597ae2f6-16a6-1027-98f4-d28b5365dc14
~~~

Giá trị trên chỉ là ví dụ định dạng. Không tự tạo `entryUUID` hoặc cố ghi giá trị này bằng `modifyAttributes`; server quản lý operational attribute.

### 3.1. entryUUID không phải thuộc tính user thông thường

Vì `entryUUID` là operational attribute, LDAP server thường không trả nó khi client chỉ yêu cầu user attributes hoặc gọi lookup không chỉ rõ attribute.

Spring LDAP FAQ giải thích `DirContextAdapter` mặc định chỉ đọc visible attributes; operational attributes phải được yêu cầu tường minh. Có thể dùng overload của `LdapTemplate.lookup` hoặc search nhận danh sách attribute cần trả. [Spring LDAP FAQ — Operational Attributes](https://docs.spring.io/spring-ldap/reference/faq.html).

Do đó, code sau có thể không thấy `entryUUID`:

~~~java
Attributes attributes = ldapTemplate.lookupContext(dn).getAttributes();
Attribute id = attributes.get("entryUUID"); // Có thể null
~~~

Muốn đọc identity, yêu cầu rõ attribute:

~~~java
String[] requested = {"uid", "cn", "entryUUID"};
~~~

Server vẫn có thể từ chối hoặc không hỗ trợ attribute này; cần xử lý trường hợp không có kết quả.

### 3.2. entryUUID có được giữ khi rename/move không?

Theo RFC, UUID là immutable trong vòng đời entry. Khi entry được rename hoặc move mà vẫn là cùng entry trong directory, UUID tiếp tục nhận diện object đó.

Tuy nhiên, nếu entry bị xóa rồi tạo mới, server phải cấp UUID mới cho entry mới. Nếu dữ liệu được export/import sang một directory khác, không giả định server đích sẽ bảo toàn `entryUUID`; theo RFC, server gán UUID khi entry được add vào directory của nó.

Vì vậy, khi migration giữa directory server, cần một mapping/correlation ID do hệ thống migration quản lý nếu cần liên kết identity xuyên môi trường.

## 4. objectGUID trong Microsoft Active Directory

Active Directory có thuộc tính `objectGUID`, là GUID 128 bit được gán cho object khi object được tạo. Microsoft mô tả `objectGUID` là giá trị không thay đổi khi object được rename hoặc move trong directory. Đây là thuộc tính riêng của Active Directory, không phải tên khác của RFC 4530 `entryUUID`. [Microsoft: Object Names and Identities](https://learn.microsoft.com/en-us/windows/win32/ad/object-names-and-identities).

Đặc điểm:

- Là attribute đơn trị.
- Có kiểu dữ liệu nhị phân 16 byte khi đọc qua LDAP/JNDI.
- Được Active Directory tạo và quản lý; client không được sửa.
- Giữ nguyên khi object được rename/move theo semantics của AD.
- Có thể dùng để tìm object sau khi DN thay đổi.
- Không nên nhầm với `objectSid`, là security identifier có semantics bảo mật riêng.

Ví dụ entry AD có thể hiển thị trong công cụ quản trị như sau:

~~~text
dn: CN=Lan Nguyen,OU=People,DC=example,DC=com
objectGUID: <16 binary octets>
objectSid: <binary security identifier>
~~~

Không thể biểu diễn đầy đủ 16 byte `objectGUID` bằng text thường trong LDIF minh họa. Công cụ LDAP có thể render giá trị này ở dạng hex hoặc chuỗi GUID đã chuyển đổi.

### 4.1. objectGUID khác entryUUID ở đâu?

| Đặc điểm | `entryUUID` | `objectGUID` |
|---|---|---|
| Nguồn | RFC 4530 | Microsoft Active Directory |
| Phạm vi | LDAP server hỗ trợ RFC/schema attribute | Active Directory |
| Dạng LDAP | UUID ASCII string theo RFC | Binary 16 octet |
| Phân loại | Operational attribute, directoryOperation | Attribute đặc thù AD, system-managed/read-only |
| Client được sửa? | Không | Không |
| Giữ identity qua rename/move? | Immutable trong vòng đời entry theo RFC | Không đổi qua rename/move theo AD |
| Dùng ở server LDAP bất kỳ? | Chỉ khi server hỗ trợ | Không |
| Có thể dùng làm khóa tham chiếu ứng dụng? | Có, trong phạm vi directory đã xác định | Có, trong phạm vi AD/forest và policy ứng dụng |

Đừng viết một adapter tổng quát giả định mọi LDAP server đều có `entryUUID` hoặc mọi server đều có `objectGUID`. Hãy xác định capability của directory khi cấu hình kết nối.

## 5. objectGUID không phải objectSid

Trong Active Directory, ba giá trị thường bị nhầm:

- `objectGUID`: nhận diện object instance trong AD, giữ nguyên qua rename/move.
- `objectSid`: security identifier của security principal, được dùng trong Windows security và group membership.
- DN: vị trí/địa chỉ của object trong cây directory.

Một object có thể giữ `objectGUID` nhưng `objectSid` có semantics khác khi chuyển domain hoặc xử lý migration. Không thay thế SID bằng GUID trong access token, ACL hoặc kiểm tra quyền. Cũng không dùng DN thay cho SID nếu nghiệp vụ cần Windows security identity.

Microsoft mô tả SID và GUID là các giá trị khác nhau; GUID được gán cho mọi object AD, còn SID gắn với các security principal như user/group/computer. [Microsoft: Security Identifiers](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-security-identifiers).

## 6. Xóa rồi tạo lại cùng DN không khôi phục identity cũ

Giả sử ban đầu:

~~~text
DN:
uid=lan,ou=people,dc=example,dc=org

entryUUID:
11111111-2222-3333-4444-555555555555
~~~

Entry bị xóa. Sau đó, một job tạo lại entry với cùng DN:

~~~text
DN:
uid=lan,ou=people,dc=example,dc=org

entryUUID:
aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
~~~

DN giống nhau nhưng `entryUUID` khác nhau vì đây là một entry mới. Với Active Directory, `objectGUID` của object mới cũng là GUID mới.

Điều này ảnh hưởng tới:

- Cache key và cache invalidation.
- Foreign key trong database ứng dụng.
- Event consumer xử lý đồng bộ.
- Audit history.
- Authorization mapping.
- Group membership và các tham chiếu DN-valued.
- Job phục hồi sau sự cố.

Không tự động “nối lại” lịch sử của object cũ với object mới chỉ vì DN, UID hoặc email giống nhau. Nếu nghiệp vụ muốn coi object mới là cùng một người, phải có quy trình identity reconciliation riêng dựa trên nguồn dữ liệu có thẩm quyền.

## 7. Đọc entryUUID bằng Spring LDAP LdapTemplate

Ta dùng DTO chứa cả DN và stable identifier:

~~~java
import javax.naming.ldap.LdapName;
import java.util.UUID;

public record DirectoryIdentity(
    LdapName dn,
    UUID entryUuid,
    String uid,
    String commonName
) {}
~~~

Vì `entryUUID` là chuỗi UUID theo RFC 4530, có thể parse bằng `UUID.fromString`.

~~~java
import java.util.UUID;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class DirectoryIdentityReader {

    private final LdapTemplate ldapTemplate;

    public DirectoryIdentityReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public DirectoryIdentity readByDn(LdapName dn) {
        String[] requested = {"uid", "cn", "entryUUID"};

        return ldapTemplate.lookup(
            dn,
            requested,
            (AttributesMapper<DirectoryIdentity>) attributes -> {
                String uid = required(attributes, "uid");
                String cn = required(attributes, "cn");
                String uuidText = required(attributes, "entryUUID");

                return new DirectoryIdentity(
                    dn,
                    UUID.fromString(uuidText),
                    uid,
                    cn
                );
            }
        );
    }

    private static String required(
            Attributes attributes,
            String name) throws NamingException {

        Attribute attribute = attributes.get(name);
        if (attribute == null || attribute.size() == 0) {
            throw new NamingException(
                "Required directory attribute is missing: " + name
            );
        }
        return attribute.get().toString();
    }
}
~~~

Điểm cần lưu ý:

1. Overload `lookup(Name, String[], AttributesMapper)` yêu cầu các attribute được trả về một cách tường minh.
2. `entryUUID` có thể không được server hỗ trợ hoặc không được bind identity phép đọc.
3. `UUID.fromString` chỉ parse format; nó không xác minh UUID có thuộc entry đang tồn tại hay không.
4. DN truyền vào phải theo base DN convention của `ContextSource` đã cấu hình.
5. Không log password hoặc toàn bộ attribute nhạy cảm khi đọc identity.

`LdapTemplate` cung cấp các overload lookup/search nhận danh sách attribute cần trả về và mapper. [Spring LDAP LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html).

### 7.1. Tìm entry bằng entryUUID sau khi DN thay đổi

Nếu server hỗ trợ equality matching cho `entryUUID`, có thể search trong naming context bằng UUID:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public List<DirectoryIdentity> findByEntryUuid(
        LdapTemplate ldapTemplate,
        UUID entryUuid) {

    LdapQuery ldapQuery = query()
        .base("")
        .searchScope(SearchScope.SUBTREE)
        .attributes("entryUUID", "uid", "cn")
        .where("entryUUID").is(entryUuid.toString());

    return ldapTemplate.search(
        ldapQuery,
        (AttributesMapper<DirectoryIdentity>) attrs -> {
            String uuid = attrs.get("entryUUID").get().toString();
            String uid = attrs.get("uid").get().toString();
            String cn = attrs.get("cn").get().toString();

            return new DirectoryIdentity(
                null,
                UUID.fromString(uuid),
                uid,
                cn
            );
        }
    );
}
~~~

Ví dụ giả định base rỗng có nghĩa là search root phù hợp với `ContextSource` đang dùng và account có quyền tìm trong naming context đó. Trong production, ưu tiên một base hẹp hơn nếu biết các OU hợp lệ; tránh subtree search toàn directory chỉ để tìm một ID nếu server có thể định vị bằng index hoặc base phù hợp.

Kết quả có thể là rỗng nếu entry đã bị xóa, caller thiếu quyền hoặc server không hỗ trợ attribute. Nếu kết quả có nhiều hơn một entry, cần xem đó là vi phạm giả định uniqueness hoặc khác biệt triển khai; không chọn phần tử đầu tiên tùy tiện.

### 7.2. Operational attribute phải được yêu cầu tường minh

Trong search, projection `.attributes("entryUUID", "uid", "cn")` là điểm quan trọng. Nếu chỉ yêu cầu user attributes, `entryUUID` có thể không xuất hiện.

RFC 3673 định nghĩa lựa chọn `+` để yêu cầu toàn bộ operational attributes trên server hỗ trợ feature này, nhưng không cần dùng `+` cho bài toán này. Nêu rõ `entryUUID` giúp giới hạn dữ liệu trả về và tránh phụ thuộc feature hỗ trợ thêm. [RFC 3673](https://www.rfc-editor.org/rfc/rfc3673).

## 8. Đọc objectGUID dạng byte[] trong Java

Khi đọc `objectGUID` qua JNDI, giá trị thường là `byte[]` có 16 byte. Không dùng:

~~~java
UUID uuid = UUID.nameUUIDFromBytes(objectGuidBytes);
~~~

`nameUUIDFromBytes` tạo một UUID mới theo thuật toán name-based; nó không chuyển đổi GUID đang lưu trong AD.

Cũng không nên gọi `new UUID(...)` trực tiếp trên hai long được đọc tuần tự từ byte array mà chưa xử lý byte order.

### 8.1. Quy tắc byte order của GUID Windows

Microsoft GUID có cấu trúc:

- `Data1`: 4 byte, little-endian trong packet representation.
- `Data2`: 2 byte, little-endian.
- `Data3`: 2 byte, little-endian.
- `Data4`: 8 byte còn lại theo thứ tự byte của trường.

Vì Java `UUID` dùng thứ tự octet chuẩn để biểu diễn hai phần 64-bit, cần đảo thứ tự byte trong ba trường đầu trước khi tạo UUID. [Microsoft GUID packet representation](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-dtyp/001eec5a-7f8b-4293-9e21-ca349392db40).

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.UUID;

public final class ActiveDirectoryGuid {

    private ActiveDirectoryGuid() {
    }

    public static UUID fromLdapBytes(byte[] value) {
        if (value == null || value.length != 16) {
            throw new IllegalArgumentException(
                "objectGUID must contain exactly 16 bytes"
            );
        }

        byte[] uuidBytes = new byte[16];

        // Data1: reverse 4 bytes.
        uuidBytes[0] = value[3];
        uuidBytes[1] = value[2];
        uuidBytes[2] = value[1];
        uuidBytes[3] = value[0];

        // Data2: reverse 2 bytes.
        uuidBytes[4] = value[5];
        uuidBytes[5] = value[4];

        // Data3: reverse 2 bytes.
        uuidBytes[6] = value[7];
        uuidBytes[7] = value[6];

        // Data4: preserve the remaining 8 bytes.
        System.arraycopy(value, 8, uuidBytes, 8, 8);

        ByteBuffer buffer = ByteBuffer
            .wrap(uuidBytes)
            .order(ByteOrder.BIG_ENDIAN);

        long mostSignificantBits = buffer.getLong();
        long leastSignificantBits = buffer.getLong();

        return new UUID(
            mostSignificantBits,
            leastSignificantBits
        );
    }
}
~~~

### 8.2. Đọc objectGUID qua LdapTemplate

Đây là method đặt trong một service/reader Spring bean đã inject `LdapTemplate`; phần xử lý tập trung vào projection và chuyển đổi giá trị binary.

~~~java
import java.util.UUID;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.LdapTemplate;

public UUID readObjectGuid(
        LdapTemplate ldapTemplate,
        LdapName dn) {

    return ldapTemplate.lookup(
        dn,
        new String[] {"objectGUID"},
        (Attributes attributes) -> {
            try {
                Attribute attribute = attributes.get("objectGUID");
                if (attribute == null || attribute.size() != 1) {
                    throw new NamingException(
                        "objectGUID is missing or not single-valued"
                    );
                }

                Object raw = attribute.get();
                if (!(raw instanceof byte[] bytes)) {
                    throw new NamingException(
                        "Expected objectGUID to be returned as byte[]"
                    );
                }

                return ActiveDirectoryGuid.fromLdapBytes(bytes);
            } catch (NamingException ex) {
                throw ex;
            }
        }
    );
}
~~~

Ví dụ này dành cho Active Directory và giả định JNDI provider trả binary attribute dưới dạng `byte[]`, như thông thường với `objectGUID`. Không áp dụng converter này cho `entryUUID`, vốn được RFC 4530 biểu diễn dưới dạng chuỗi UUID ASCII trong LDAP.

### 8.3. Kiểm tra converter bằng known vector

Một phép chuyển đổi GUID nên có test với known vector đã biết cả byte array LDAP lẫn chuỗi GUID chuẩn. Không tự tạo expected value bằng chính converter đang kiểm thử.

Ví dụ test minh họa:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class ActiveDirectoryGuidTest {

    @Test
    void convertsWindowsGuidFieldByteOrder() {
        byte[] ldapBytes = new byte[] {
            (byte) 0x40, (byte) 0xFC, (byte) 0x29, (byte) 0x6B,
            (byte) 0x47, (byte) 0xCA,
            (byte) 0x67, (byte) 0x10,
            (byte) 0xB3, (byte) 0x1D,
            (byte) 0x00, (byte) 0xDD, (byte) 0x01,
            (byte) 0x06, (byte) 0x62, (byte) 0xDA
        };

        UUID result = ActiveDirectoryGuid.fromLdapBytes(ldapBytes);

        assertThat(result.toString())
            .isEqualTo("6b29fc40-ca47-1067-b31d-00dd010662da");
    }
}
~~~

Vector này minh họa GUID chuẩn `6B29FC40-CA47-1067-B31D-00DD010662DA`; ba trường đầu có byte order khác với chuỗi hiển thị. Trong integration test, nên lấy một `objectGUID` thật từ AD test directory và đối chiếu với công cụ quản trị có thẩm quyền.

## 9. Model ứng dụng nên giữ cả identity và location

Một DTO hoặc domain model có thể tách hai trường:

~~~java
public record DirectoryPersonReference(
    String directoryKey,
    String stableId,
    String currentDn,
    String uid
) {}
~~~

Ý nghĩa:

- `directoryKey`: định danh cấu hình của directory/forest mà ứng dụng kết nối.
- `stableId`: `entryUUID` hoặc `objectGUID` đã chuyển sang representation chuẩn.
- `currentDn`: DN hiện tại để thực hiện lookup/modify.
- `uid`: thuộc tính nghiệp vụ có thể thay đổi, không nên mặc định bất biến.

Vì UUID chỉ duy nhất theo miền mà server bảo đảm, không dùng một UUID đơn lẻ làm khóa toàn hệ thống nếu ứng dụng kết nối nhiều directory độc lập. Khóa tổng hợp `(directoryKey, stableId)` an toàn hơn.

### 9.1. Không thay @Id của Spring Data LDAP bằng UUID tùy ý

Trong Spring Data LDAP ODM, `@Id` đại diện cho DN/Name của entry để repository định vị object trong directory. Ví dụ:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;
}
~~~

`LdapRepository.findById(...)` dùng identity theo DN của mô hình ODM. Không đổi field `@Id` thành `UUID` rồi kỳ vọng repository tự tìm theo `entryUUID` hoặc `objectGUID`.

Nếu cần stable identifier:

- Giữ `@Id Name dn` cho DN theo contract ODM.
- Đọc `entryUUID`/`objectGUID` bằng query/lookup tường minh.
- Lưu stable ID trong domain model hoặc bảng mapping ứng dụng.
- Nếu repository query theo thuộc tính operational, xác minh mapping/projection và khả năng server trước khi dựa vào nó.

Đừng ép một trường DN và một stable ID vào cùng một property chỉ để thuận tiện serialize.

## 10. Duy trì mapping DN hiện tại

Một bảng mapping có thể được tổ chức như sau:

~~~sql
CREATE TABLE directory_object_ref (
    directory_key VARCHAR(100) NOT NULL,
    stable_id VARCHAR(80) NOT NULL,
    current_dn VARCHAR(2048) NOT NULL,
    object_type VARCHAR(100),
    last_verified_at TIMESTAMP,
    PRIMARY KEY (directory_key, stable_id),
    UNIQUE (directory_key, current_dn)
);
~~~

Đây là schema minh họa. Cần cân nhắc độ dài DN thực tế, collation của database, encoding, index size và việc DN equality không tương đương so sánh chuỗi database mặc định.

Khi phát hiện entry được move/rename:

1. Tìm entry bằng stable ID hoặc nhận event đáng tin cậy.
2. Đọc DN hiện tại từ directory.
3. Xác minh stable ID trên entry vừa tìm được.
4. Cập nhật `current_dn` trong mapping.
5. Invalidate cache theo cả DN cũ và mới.
6. Ghi audit event có correlation ID.

Không cập nhật mapping chỉ dựa vào một thông báo rename chưa được xác minh hoặc một DN mới do client gửi lên.

### 10.1. Cache nên key theo stable ID

Mô hình cache gợi ý:

~~~text
(directoryKey, stableId) -> PersonSnapshot
(directoryKey, currentDn) -> stableId
~~~

Stable ID là key chính để truy cập object snapshot. DN index là reverse lookup phục vụ thao tác LDAP.

Khi rename:

- Giữ nguyên key `(directoryKey, stableId)`.
- Cập nhật DN trong snapshot.
- Xóa mapping DN cũ.
- Thêm mapping DN mới.
- Cập nhật TTL/invalidation để tránh request dùng DN cũ.

Nếu chỉ key cache bằng DN, rename có thể tạo cache entry mới cho cùng object và để lại stale data ở key cũ.

## 11. Xử lý DN-valued references như member và manager

Nhiều schema LDAP lưu tham chiếu tới entry dưới dạng DN:

- `manager`
- `member`
- `uniqueMember`
- Các thuộc tính custom có DN syntax

Khi entry được rename/move, tham chiếu tới nó có thể cần cập nhật. Hành vi tự cập nhật tham chiếu phụ thuộc directory server, schema, linked attributes và cách server triển khai. Active Directory có linked attribute semantics cho một số quan hệ; không được giả định mọi LDAP server đều tự duy trì mọi thuộc tính DN-valued.

Một quy trình ứng dụng cần:

1. Xác định các attribute nào chứa DN reference.
2. Xác minh schema syntax và server behavior.
3. Kiểm thử rename/move trên directory test.
4. Đọc lại các entry tham chiếu sau operation.
5. Nếu server không tự cập nhật, chạy quy trình đồng bộ reference có kiểm soát.
6. Không thay thế DN reference bằng UUID nếu schema attribute yêu cầu DN syntax.

Stable ID giúp tìm đúng object; nó không tự thay đổi các thuộc tính LDAP có giá trị DN.

## 12. Phân biệt rename, move, delete và migration

| Sự kiện | DN hiện tại | `entryUUID` | AD `objectGUID` |
|---|---|---|---|
| Rename cùng entry | Thay đổi | Giữ nguyên theo vòng đời entry | Giữ nguyên |
| Move cùng directory/forest theo operation được server hỗ trợ | Thay đổi | Giữ nguyên theo vòng đời entry | Giữ nguyên theo AD object identity |
| Delete entry | Không còn entry hiện hành | Không còn identity của entry đang tồn tại | Object bị xóa; tombstone có thể giữ metadata theo AD lifecycle |
| Add entry mới dùng lại DN | Có thể trùng DN cũ | UUID mới | GUID mới |
| Export/import sang server khác | Có thể giữ DN hoặc được remap | Không đảm bảo giữ; server đích cấp UUID khi Add | Phụ thuộc migration/AD tooling, không giả định được giữ |
| Restore từ backup | Tùy cơ chế server | Phụ thuộc backup/restore semantics | Phụ thuộc AD restore semantics |

Bảng này nêu nguyên tắc thiết kế, không thay thế tài liệu của từng server cho backup, tombstone, recycle bin hoặc cross-domain migration. Đặc biệt, không coi delete và restore là cùng một thao tác với rename.

## 13. Tìm object theo objectGUID trong Active Directory

Với AD, có thể search theo `objectGUID`, nhưng assertion LDAP phải dùng đúng dạng binary của attribute. Chuỗi GUID hiển thị không phải lúc nào cũng là assertion value binary mà server mong đợi.

Có hai ý cần tách:

- `objectGUID` được trả về dưới dạng 16 byte binary.
- Filter equality trên binary attribute phải encode từng octet theo cú pháp LDAP filter. Với known vector ở mục 8.3, byte array LDAP bắt đầu bằng `40 FC 29 6B`; filter assertion tương ứng phải dùng từng octet, không dùng chuỗi GUID hiển thị:

~~~text
(objectGUID=\40\fc\29\6b\47\ca\67\10\b3\1d\00\dd\01\06\62\da)
~~~

Ví dụ này chỉ minh họa cú pháp RFC 4515 cho đúng byte array của known vector; hãy tạo assertion từ 16 byte thực tế của object cần tìm.

Nếu dùng thư viện LDAP/AD chuyên biệt, ưu tiên API có hỗ trợ GUID assertion và chuyển đổi byte order rõ ràng. Với Spring LDAP/JNDI thuần, cần viết encoder binary filter theo RFC 4515 và test trên AD test forest; không dùng `UUID.toString()` như byte representation.

Microsoft cũng mô tả AD LDAP provider có cách bind theo GUID trong một số API (`<GUID=...>`), nhưng đó là provider-specific binding syntax, không phải DN LDAP chuẩn áp dụng cho mọi server. [Microsoft: Using objectGUID to Bind to an Object](https://learn.microsoft.com/en-us/windows/win32/ad/using-objectguid-to-bind-to-an-object).

## 14. Migration giữa directory: cần một correlation strategy

Khi di chuyển dữ liệu từ OpenLDAP sang Active Directory hoặc giữa hai LDAP server độc lập, stable identifier phía nguồn có thể không được bảo toàn.

Một chiến lược migration nên:

1. Export stable ID nguồn và các thuộc tính nghiệp vụ được phép dùng để đối chiếu.
2. Tạo entry ở directory đích.
3. Đọc stable ID mới do directory đích cấp.
4. Lưu mapping `(sourceDirectory, sourceStableId) -> (targetDirectory, targetStableId)`.
5. Kiểm tra duplicate/ambiguous match trước khi chuyển reference.
6. Chỉ chuyển traffic sau khi đối chiếu đủ dữ liệu.
7. Giữ audit mapping để rollback migration hoặc điều tra.

Không dùng DN làm correlation key duy nhất nếu DN có thể được chuẩn hóa, đổi OU hoặc đổi naming convention trong quá trình migration.

Nếu có một employee ID do HR hoặc hệ thống chủ quản cấp, có thể dùng nó làm business identity, nhưng phải xác minh uniqueness, lifecycle và policy của hệ thống đó. `entryUUID`/`objectGUID` định danh object trong directory; employee ID định danh thực thể theo nghiệp vụ. Hai loại identity có thể cùng tồn tại.

## 15. Bảo mật và quyền đọc stable identifier

Stable identifier không phải password, token hoặc bằng chứng authorization. Biết `entryUUID` hay `objectGUID` không tự cho phép đọc hoặc sửa entry.

Dù UUID không chứa thông tin mô tả như tên hoặc email, RFC 4530 vẫn có phần security considerations. Một UUID ổn định có thể liên kết các bản ghi về cùng một object qua nhiều hệ thống, vì vậy nó vẫn là dữ liệu có thể định danh và cần kiểm soát truy cập.

Thực hành:

- Dùng service account có quyền đọc đúng operational attribute cần thiết.
- Không cấp quyền admin chỉ để lấy UUID.
- Không đưa stable ID vào URL công khai nếu không cần.
- Không dùng UUID làm bearer token.
- Không log raw DN/UUID nếu correlation ID nội bộ đã đủ.
- Giới hạn quyền đọc bảng mapping DN ↔ stable ID.
- Mã hóa backup và recovery journal nếu chứa định danh nhạy cảm.
- Không cho client tự chỉ định `directoryKey` hoặc stable ID rồi bỏ qua authorization.
- Khi dùng AD, không nhầm `objectGUID` với `objectSid` trong kiểm tra access token hoặc ACL.

## 16. Xử lý khi stable identifier không đọc được

Có nhiều nguyên nhân khiến ứng dụng không lấy được stable ID:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `entryUUID` không có trong Attributes | Không request operational attribute | Thêm `entryUUID` vào projection |
| `entryUUID` vẫn null | Server không hỗ trợ RFC 4530 hoặc ACL ẩn attribute | Kiểm tra schema/capability và bind permissions |
| `objectGUID` không có | Kết nối server không phải AD hoặc attribute không được trả | Kiểm tra directory type và projection |
| `objectGUID` không phải `byte[]` | Provider/mapping trả kiểu khác | Kiểm tra JNDI provider và inspect raw value an toàn |
| UUID parse lỗi | Giá trị chuỗi sai format hoặc có whitespace/representation khác | Validate dữ liệu; không tự cắt chuỗi tùy tiện |
| Tìm theo UUID trả nhiều entry | Directory scope/replication/schema không như giả định | Xác minh uniqueness, base, server và filter |
| Tìm theo DN cũ không thấy | Entry đã rename/move hoặc bị xóa | Tìm theo stable ID nếu có |
| DN mới trỏ object khác | DN đã được tái sử dụng | Đọc stable ID và so sánh với mapping |

Nếu stable ID chưa đọc được, không tự sinh một UUID thay thế rồi ghi nó vào field có tên `entryUUID` hoặc `objectGUID`. Có thể dùng một application ID riêng trong database, nhưng phải phân biệt rõ nguồn cấp và phạm vi uniqueness.

## 17. Kiểm thử rename/move và identity lifecycle

Một test tốt phải chứng minh cả hai phía: DN đổi và stable identifier giữ nguyên.

### 17.1. Test rename cùng entry

Pseudo-code integration test:

~~~java
@Test
void stableIdentifierSurvivesRename() {
    DirectoryPerson before = directory.readByDn(
        "uid=lan,ou=people,dc=example,dc=org"
    );

    directory.rename(
        before.dn(),
        "uid=lan,ou=engineering,dc=example,dc=org"
    );

    DirectoryPerson after = directory.readByDn(
        "uid=lan,ou=engineering,dc=example,dc=org"
    );

    assertThat(after.dn()).isNotEqualTo(before.dn());
    assertThat(after.stableId()).isEqualTo(before.stableId());
}
~~~

`DirectoryPerson` và `directory` là abstraction của test. Cần chạy trên server hỗ trợ thuộc tính identity đang kiểm thử.

### 17.2. Test delete rồi add lại cùng DN

~~~java
@Test
void recreatedEntryHasANewStableIdentifier() {
    DirectoryPerson original = directory.readByDn(personDn);

    directory.delete(personDn);
    directory.addPerson(personDn, "lan", "Lan Nguyen");

    DirectoryPerson recreated = directory.readByDn(personDn);

    assertThat(recreated.dn()).isEqualTo(original.dn());
    assertThat(recreated.stableId()).isNotEqualTo(original.stableId());
}
~~~

Test này kiểm tra trường hợp nguy hiểm: cùng DN nhưng object instance mới. Với directory có tombstone/recycle bin, cần phân biệt thao tác restore object cũ với add object mới; fixture phải bảo đảm thực sự xóa rồi tạo lại.

### 17.3. Test operational attribute được request

Tạo hai test lookup:

- Lookup chỉ yêu cầu `uid`, `cn`; xác nhận không dựa vào việc server tự trả `entryUUID`.
- Lookup yêu cầu `uid`, `cn`, `entryUUID`; xác nhận mapper đọc được khi server hỗ trợ và ACL cho phép.

Đây là test quan trọng vì operational attribute không được mặc định trả trong mọi API path.

### 17.4. Test objectGUID conversion

Ngoài unit test known vector, integration test trên AD test forest cần:

1. Đọc `objectGUID` raw byte array.
2. Chuyển đổi bằng converter.
3. Đối chiếu với GUID hiển thị trong công cụ quản trị AD.
4. Rename/move entry.
5. Đọc lại và xác nhận GUID chuẩn không đổi.

Không dùng một fixture mock tự tạo byte array làm bằng chứng converter tương thích với AD nếu chưa có known vector độc lập.


## 18. Thiết kế event đồng bộ khi DN thay đổi

Một event rename/move có thể có payload:

~~~json
{
  "directoryKey": "corp-ad",
  "stableId": "2c7a6b20-4f42-4f93-8a23-4e5c4a8f8f4b",
  "oldDn": "CN=Lan Nguyen,OU=People,DC=example,DC=com",
  "newDn": "CN=Lan Nguyen,OU=Engineering,DC=example,DC=com",
  "eventType": "ENTRY_RENAMED"
}
~~~

Đây là event contract minh họa, không phải event chuẩn LDAP tự phát ra bởi mọi server. LDAP không mặc định cung cấp một event bus đồng bộ rename cho ứng dụng. Event có thể đến từ audit log, directory change tracking, sync agent hoặc workflow của ứng dụng.

Consumer nên:

1. Dùng `directoryKey + stableId` để định danh target.
2. Lookup entry theo stable ID hoặc xác minh DN mới.
3. So sánh DN hiện tại với `newDn`.
4. Cập nhật mapping nếu cùng object.
5. Nếu DN hiện tại khác cả `oldDn` và `newDn`, kiểm tra event cũ/out-of-order hoặc có thêm lần rename.
6. Làm idempotent theo event ID/sequence.
7. Không ghi đè mapping khi event chưa xác minh.

Không tin `oldDn`/`newDn` từ message ngoài hệ thống nếu message chưa xác thực và không đối chiếu với directory.

### 18.1. Xử lý event đến trễ hoặc lặp

Giả sử entry được move hai lần:

~~~text
People -> Engineering -> Contractors
~~~

Event thứ nhất có thể đến sau event thứ hai. Nếu consumer cứ ghi `newDn` từ event mà không đọc lại directory, mapping có thể quay về DN cũ.

Cách xử lý:

- Dùng event sequence/version nếu nguồn phát cung cấp.
- Lưu event ID đã xử lý để chống lặp.
- Khi event đến trễ hoặc sequence không rõ, đọc DN hiện tại theo stable ID.
- Chỉ cập nhật mapping từ trạng thái được xác minh.
- Ghi audit record về event bị bỏ qua hoặc đã được reconcile.

Nếu không có stable ID, việc đối chiếu event chỉ bằng old DN/new DN yếu hơn và cần thêm nguồn định danh nghiệp vụ.

## 19. Troubleshooting identity mapping

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Lookup theo DN cũ thất bại | Entry đã rename/move | Tìm theo stable ID và đọc DN hiện tại |
| DN cũ vẫn lookup được nhưng identity khác | DN đã được tái sử dụng | Đọc stable ID trước khi gắn mapping |
| Không đọc được entryUUID | Không request operational attribute, ACL hoặc server không hỗ trợ | Projection tường minh, kiểm tra schema/capability và quyền |
| UUID nguồn không tìm thấy sau migration | Directory đích cấp identity mới | Dùng source-to-target mapping |
| objectGUID hiển thị khác chuỗi dự kiến | Chuyển byte order chưa đúng | Dùng converter theo GUID field layout và known vector |
| UUID cache bị stale | Rename event đến trễ hoặc invalidation thiếu | Reconcile theo stable ID, cập nhật reverse index |
| Một stable ID tìm thấy nhiều entry | Sai directory scope, replica/topology hoặc lỗi mapping | Xác minh uniqueness và endpoint; không chọn ngẫu nhiên |
| Entry có DN mới nhưng group member vẫn chứa DN cũ | Server không tự cập nhật DN-valued references hoặc sync chưa xong | Kiểm tra schema/server behavior và đồng bộ quan hệ |
| Không thể đọc objectGUID | Không kết nối AD hoặc thiếu quyền/projection | Kiểm tra endpoint, projection và ACL |
| Delete/recreate bị nhận nhầm là cùng object | Ứng dụng chỉ so DN/uid/email | So sánh stable ID và chạy identity reconciliation |

### 19.1. Kiểm tra bằng ldapsearch

Với server hỗ trợ `entryUUID`, có thể yêu cầu rõ operational attribute:

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D 'uid=svc-reader,ou=service-accounts,dc=example,dc=org' \
  -W \
  -b 'dc=example,dc=org' \
  -s sub \
  '(uid=lan)' \
  uid cn entryUUID
~~~

Với Active Directory, yêu cầu `objectGUID` cùng các thuộc tính cần thiết:

~~~bash
ldapsearch -x \
  -H ldaps://dc01.example.com:636 \
  -D 'CN=svc-reader,OU=Service Accounts,DC=example,DC=com' \
  -W \
  -b 'DC=example,DC=com' \
  -s sub \
  '(sAMAccountName=lan)' \
  distinguishedName objectGUID objectSid
~~~

Output của công cụ có thể hiển thị binary attribute ở dạng base64 hoặc hex tùy phiên bản và option. Đừng so sánh trực tiếp output text của công cụ với `UUID.toString()` trước khi xác định encoding và byte order.

Không đặt password trực tiếp trong command bằng `-w`; dùng prompt `-W` hoặc secret mechanism của môi trường. Chỉ chạy truy vấn trên directory và account được phép sử dụng.

## 20. Bài tập thực hành

### Bài 1 — Phân biệt DN và stable ID

Một entry chuyển từ `ou=people` sang `ou=engineering`. DN thay đổi. Giải thích vì sao cache key chỉ dựa trên DN có thể tạo stale entry và thiết kế key mới.

### Bài 2 — Delete/recreate

Một DN bị xóa rồi được dùng lại cho object mới. Điều gì xảy ra với `entryUUID` và `objectGUID`? Tại sao không thể gắn lịch sử object cũ cho object mới chỉ vì DN giống nhau?

### Bài 3 — Operational attribute

Viết `LdapTemplate.lookup` lấy `uid`, `cn`, `entryUUID`. Giải thích vì sao lookup không yêu cầu attribute có thể không trả `entryUUID`.

### Bài 4 — AD binary GUID

Một `objectGUID` được trả dưới dạng 16 byte. Vì sao không dùng `UUID.nameUUIDFromBytes()`? Mô tả byte order của Data1, Data2, Data3 và Data4.

### Bài 5 — Repository ID

Entity ODM có `@Id Name dn`. Vì sao không thay field này bằng UUID nếu repository cần định vị entry theo DN? Thiết kế thêm stable ID mà không phá contract repository.

### Bài 6 — Directory migration

Di chuyển entry từ directory A sang B. Vì sao không giả định `entryUUID` nguồn sẽ được giữ? Đề xuất mapping source ID và target ID.

### Bài 7 — AD objectGUID và objectSid

Một user được chuyển domain. Phân biệt mục đích của `objectGUID` và `objectSid`; vì sao không dùng GUID thay SID trong ACL/token?

### Bài 8 — DN-valued reference

Entry được rename nhưng group có thuộc tính `member` chứa DN của entry. Những khác biệt server nào cần kiểm tra? Viết integration test xác minh tham chiếu sau rename.

### Bài 9 — Cache invalidation

Thiết kế cache hai chiều stable ID ↔ current DN. Mô tả cách xử lý event rename đến trễ hoặc lặp lại.

### Bài 10 — Identity reconciliation

Một bản ghi mapping chỉ có DN cũ, không có stable ID. DN đó hiện trỏ tới object khác. Đề xuất cách xử lý an toàn và thông tin cần dùng từ hệ thống chủ quản để đối chiếu.

## 21. Checklist production

| Câu hỏi | Tiêu chí |
|---|---|
| Có đang dùng DN như khóa bất biến? | Phân biệt DN location và stable identity |
| Directory có hỗ trợ `entryUUID`? | Xác minh RFC 4530/schema và quyền đọc |
| Có dùng AD? | Dùng `objectGUID` đúng byte representation |
| Operational attribute có được request? | Projection nêu rõ attribute cần lấy |
| Stable ID có scope directory? | Khóa mapping gồm directory/forest key |
| Có phân biệt delete/recreate? | DN giống không đồng nghĩa object giống |
| Có migration mapping? | Source ID và target ID được liên kết có audit |
| Repository ODM có giữ `@Id Name`? | Không nhầm DN ID của repository với stable ID |
| Cache có xử lý rename? | Cập nhật DN cũ/mới theo stable ID |
| DN-valued attributes có được kiểm thử? | Xác minh server tự cập nhật hay ứng dụng phải xử lý |
| `objectGUID` có chuyển byte order đúng? | Unit test known vector và AD integration test |
| UUID có bị dùng làm credential? | Không |
| Logs/API có lộ identity? | Mask/limit theo policy |
| ACL cho operational attributes đúng? | Service account chỉ có quyền cần thiết |
| Có test rename/move/delete/recreate? | Kiểm tra cả DN và stable ID |
| Có reconciliation cho event lỗi/thứ tự sai? | Consumer idempotent và xác minh state từ directory |

## 22. Kết luận và tài liệu tham khảo

DN là địa chỉ của entry trong cây LDAP và có thể thay đổi khi rename hoặc move. Một DN cũ còn có thể được dùng lại sau khi entry bị xóa, vì vậy không nên dùng chuỗi DN làm identity bất biến trong database hoặc cache dài hạn.

`entryUUID` theo RFC 4530 và `objectGUID` trong Active Directory cung cấp định danh ổn định của object trong vòng đời directory tương ứng. `entryUUID` là operational attribute dạng UUID text và phải được yêu cầu tường minh. `objectGUID` là binary 16 byte và cần chuyển đổi theo byte order GUID của Windows. Hai thuộc tính không thay thế lẫn nhau, không phải bearer credential và không tự giải quyết authorization.

Trong ứng dụng Spring Data LDAP, giữ DN cho `@Id`/thao tác ODM và lưu stable ID riêng trong domain mapping. Khi rename/move, xác minh object bằng stable ID rồi cập nhật DN hiện tại, cache và các tham chiếu liên quan. Khi delete/recreate hoặc migration, cần identity reconciliation thay vì suy đoán từ DN.

Tài liệu chính thức:

- [RFC 4530 — LDAP entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530)
- [RFC 3673 — LDAPv3: All Operational Attributes](https://www.rfc-editor.org/rfc/rfc3673)
- [Microsoft — Object Names and Identities](https://learn.microsoft.com/en-us/windows/win32/ad/object-names-and-identities)
- [Microsoft — Using objectGUID to Bind to an Object](https://learn.microsoft.com/en-us/windows/win32/ad/using-objectguid-to-bind-to-an-object)
- [Microsoft — Security Identifiers](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-security-identifiers)
- [Microsoft — GUID structure](https://learn.microsoft.com/en-us/windows/win32/api/guiddef/ns-guiddef-guid)
- [Microsoft — GUID Packet Representation](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-dtyp/001eec5a-7f8b-4293-9e21-ca349392db40)
- [Spring LDAP FAQ — Operational Attributes](https://docs.spring.io/spring-ldap/reference/faq.html)
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP — Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html)
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Microsoft — MS-ADA3 objectGUID attribute](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-ada3/937eb5c6-f6b3-4652-a276-5d6bb8979658)
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/)
