# Thuộc tính nhị phân và cách ánh xạ objectGUID theo yêu cầu ứng dụng

Một ứng dụng Spring Boot dùng Spring Data LDAP có thể đọc người dùng từ nhiều loại directory. Khi thử nghiệm với OpenLDAP, lập trình viên thường thấy các thuộc tính chuỗi như `uid`, `cn`, `mail` hoặc `entryUUID`; nhưng khi kết nối Microsoft Active Directory (AD), một thuộc tính quan trọng là **`objectGUID`** lại được trả về như **16 byte nhị phân**. Nếu ứng dụng gọi `getStringAttribute("objectGUID")` hoặc `new String(bytes)`, giá trị thu được có thể sai, không đọc được, hoặc không khớp GUID mà công cụ quản trị AD hiển thị.

Thách thức không chỉ là đổi 16 byte sang chuỗi. **`objectGUID` có cách biểu diễn byte đặc thù**, khác cách đọc tuần tự một UUID theo thứ tự mạng. Ứng dụng cần quyết định lưu nguyên `byte[]`, lưu `UUID` Java hay lưu chuỗi GUID chuẩn; đồng thời phải hiểu DN có thể đổi nhưng GUID của cùng đối tượng thường được giữ trong vòng đời AD phù hợp.

Bài **Khác biệt máy chủ** thuộc module **SPRING_DATA_LDAP** trình bày cách nhận biết thuộc tính nhị phân, đọc qua `LdapTemplate`/JNDI, chuyển `objectGUID` sang `UUID` chính xác, xây filter tìm theo GUID, sử dụng trong ánh xạ định danh với database và kiểm thử trên directory. Đây là phần bổ sung cho repository, LDAP ODM, DN/`objectClass`/schema, CRUD, filter an toàn và bảo mật kết nối.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt giá trị LDAP kiểu chuỗi, kiểu nhị phân và biểu diễn Base64 trong LDIF.
2. Giải thích `objectGUID` trong Active Directory khác `entryUUID` của các directory hỗ trợ RFC 4530 như thế nào.
3. Đọc `objectGUID` thành `byte[]` qua `LdapTemplate`/`DirContextOperations` và xử lý khi JNDI không nhận diện đúng kiểu binary.
4. Chuyển **16 byte AD GUID** sang `java.util.UUID` theo quy tắc endian hỗn hợp và chuyển ngược khi cần truy vấn.
5. Tạo LDAP filter nhị phân với giá trị octet được escape theo RFC 4515, không ghép thẳng GUID hiển thị vào `(objectGUID=...)`.
6. Thiết kế phép chiếu DTO hoặc ánh xạ ODM phù hợp, không vô tình ghi vào attribute `objectGUID` do server quản lý.
7. Kiểm thử byte order, DN/ACL/schema, truy vấn theo GUID và vòng đời rename/delete/recreate.

## 2. LDAP không chỉ có thuộc tính String

Một LDAP entry có **DN** và tập attribute theo schema. Mỗi attribute có cú pháp và quy tắc so khớp; không phải tất cả đều là chuỗi UTF-8 thông thường.

Ví dụ AD:

~~~text
DC=corp,DC=example
└── OU=People
    └── CN=Lan Nguyen
        sAMAccountName: lan
        cn: Lan Nguyen
        mail: lan@corp.example
        objectGUID: <16 byte binary do AD cấp>
~~~

| Attribute ví dụ | Kiểu dữ liệu khi ứng dụng Java thường đọc | Lưu ý |
| --- | --- | --- |
| `cn`, `mail`, `sAMAccountName` | `String` hoặc nhiều chuỗi tùy schema. | Có thể thay đổi; không dùng làm định danh entry bất biến. |
| `objectGUID` (AD) | `byte[]` gồm 16 byte. | Là GUID do AD gán cho đối tượng, cần chuyển endian đúng khi hiển thị. |
| `objectSid` (AD) | `byte[]`. | Là Security Identifier, **không phải GUID** và không dùng bộ chuyển mã `objectGUID`. |
| `thumbnailPhoto`/`jpegPhoto` | Dữ liệu ảnh nhị phân. | Kích thước có thể lớn; chỉ đọc khi cần, không ép sang String. |
| `userCertificate` | Thường là byte nhị phân theo cú pháp attribute. | Xử lý như certificate theo thư viện thích hợp, không decode như text. |
| `entryUUID` (server hỗ trợ RFC 4530) | Thường là chuỗi UUID theo cú pháp được chuẩn quy định. | Không giả định là 16 byte theo dạng `objectGUID` của AD. |

Chính **schema của server** và cấu hình client quyết định cách một attribute được biểu diễn khi đi qua JNDI. Một tên thuộc tính giống nhau không nhất thiết có cùng ngữ nghĩa trên các sản phẩm LDAP khác nhau; kiểm tra directory đang dùng trước khi code mapper.

### 2.1. Dấu `::` trong LDIF là Base64, không phải giá trị GUID dạng text

Khi xuất một thuộc tính nhị phân bằng `ldapsearch -LLL`, bạn có thể gặp dạng:

~~~ldif
dn: CN=Lan Nguyen,OU=People,DC=corp,DC=example
cn: Lan Nguyen
objectGUID:: <gia-tri-Base64-cua-16-byte>
~~~

Dòng này **chỉ mang tính minh họa**; chuỗi trong dấu ngoặc nhọn không phải LDIF có thể import. Trong LDIF, một dấu hai chấm `:` chỉ một giá trị có thể hiển thị trực tiếp; hai dấu `::` biểu thị **giá trị đã mã hóa Base64**. Base64 chỉ là cách biểu diễn 16 byte trong văn bản, không thay đổi quy tắc endian của GUID.

Quy trình đọc đúng là:

~~~text
LDAP attribute -> 16 byte gốc
    ├── Java JNDI: byte[]
    ├── LDIF export: Base64 của 16 byte
    └── GUID hiển thị: chuyển byte order rồi định dạng UUID chuẩn
~~~

Không thực hiện `Base64.getDecoder().decode(...)` trên một `byte[]` đã là dữ liệu gốc từ JNDI. Chỉ cần Base64 decode khi bạn **đang đọc biểu diễn LDIF dạng văn bản** đã xác định rõ.

## 3. `objectGUID` là gì và ổn định tới đâu?

Trong Active Directory, `objectGUID` là thuộc tính định danh đối tượng do hệ thống quản lý. Nó thường giữ nguyên khi đối tượng được **đổi tên hoặc chuyển OU** trong những thao tác di chuyển được hỗ trợ, dù DN và tên đăng nhập có thể thay đổi.

Ví dụ:

~~~text
Trước rename:
DN:         CN=Lan Nguyen,OU=People,DC=corp,DC=example
objectGUID: 00112233-4455-6677-8899-aabbccddeeff

Sau rename:
DN:         CN=Lan N.,OU=Engineering,DC=corp,DC=example
objectGUID: 00112233-4455-6677-8899-aabbccddeeff
~~~

GUID trên chỉ là dữ liệu mẫu. Trong trường hợp này, ứng dụng có thể xác định đây vẫn là cùng đối tượng nhờ GUID, không dựa vào DN đã thay đổi.

**Nhưng không có định danh nào bất biến qua mọi kiểu chuyển đổi hệ thống**:

- **Rename/move hợp lệ trong cùng môi trường AD:** `objectGUID` thường được giữ.
- **Xóa rồi tạo đối tượng mới trùng DN hoặc username:** đối tượng mới thường có `objectGUID` khác; không tự gắn vào dữ liệu người cũ.
- **Import/migration, tái tạo tài khoản ở forest khác:** GUID có thể thay; phải có quy trình mapping đáng tin cậy, không nối tự động qua email.
- **Nhiều directory:** cần namespace theo nguồn; không coi một chuỗi GUID duy nhất là ID toàn hệ thống nếu chưa kiểm soát nguồn.

Trong cơ sở dữ liệu ứng dụng, sử dụng cặp **`(provider_key, external_id)`** để liên kết tới ID nội bộ, ví dụ `(corp-ad, 00112233-4455-6677-8899-aabbccddeeff)`. DN/username/email được lưu như snapshot có thể đổi. Không cố sửa `objectGUID` bằng `LdapTemplate.modifyAttributes` hoặc repository `save`: đây là thuộc tính được AD quản lý.

## 4. Vì sao GUID dạng byte của AD khác thứ tự byte thông thường?

Một GUID có cấu trúc logic gồm các thành phần:

~~~text
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
 Data1   Data2 Data3     Data4
 4 byte  2 byte 2 byte   8 byte
~~~

Ví dụ GUID hiển thị:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

Các byte `objectGUID` AD tương ứng:

~~~text
33 22 11 00   55 44   77 66   88 99 aa bb cc dd ee ff
|  Data1    | |Data2| |Data3|  |        Data4         |
   little      little   little            theo thứ tự
   endian      endian   endian            hiển thị
~~~

Ba nhóm đầu (`Data1`, `Data2`, `Data3`) có **thứ tự byte little-endian** trong biểu diễn nhị phân AD; tám byte cuối (`Data4`) giữ thứ tự của biểu diễn GUID chuẩn. Đó là lý do nếu bạn đặt thẳng 16 byte AD vào một `ByteBuffer` **big-endian** rồi gọi hai lần `getLong()` để tạo `UUID`, chuỗi thu được **không khớp GUID mà AD hiển thị**.

### Ví dụ đối chiếu

| Biểu diễn | Giá trị |
| --- | --- |
| GUID chuẩn | `00112233-4455-6677-8899-aabbccddeeff` |
| 16 byte trả về từ AD | `33 22 11 00 55 44 77 66 88 99 aa bb cc dd ee ff` |
| Sau đảo byte 3 nhóm đầu đúng quy tắc | `00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff` |

Đừng đảo toàn bộ mảng 16 byte. Chỉ ba trường đầu được diễn giải theo little-endian; đảo tất cả sẽ làm hỏng phần `Data4`.

## 5. Bộ chuyển đổi `objectGUID` sang `UUID` trong Java

Ta tách phép chuyển đổi thành một class **thuần Java**, không phụ thuộc Spring LDAP, để kiểm thử bằng dữ liệu byte biết trước. Ví dụ dùng Java 17+.

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.UUID;

public final class AdObjectGuidCodec {

    private static final String HEX = "0123456789abcdef";

    private AdObjectGuidCodec() {}

    /**
     * 16 byte trả về từ attribute objectGUID của Active Directory
     * -> UUID Java có dạng chuỗi chuẩn.
     */
    public static UUID fromAdBytes(byte[] raw) {
        if (raw == null || raw.length != 16) {
            throw new IllegalArgumentException(
                    "objectGUID phai co chinh xac 16 byte");
        }

        ByteBuffer buffer = ByteBuffer.wrap(raw)
                .order(ByteOrder.LITTLE_ENDIAN);

        long data1 = Integer.toUnsignedLong(buffer.getInt());
        long data2 = Short.toUnsignedInt(buffer.getShort());
        long data3 = Short.toUnsignedInt(buffer.getShort());

        long mostSignificantBits =
                (data1 << 32) | (data2 << 16) | data3;

        // Tám byte còn lại giữ thứ tự big-endian/network order.
        long leastSignificantBits =
                buffer.order(ByteOrder.BIG_ENDIAN).getLong();

        return new UUID(mostSignificantBits, leastSignificantBits);
    }

    /**
     * UUID chuẩn -> đúng 16 byte dùng trong objectGUID binary filter.
     */
    public static byte[] toAdBytes(UUID guid) {
        if (guid == null) {
            throw new IllegalArgumentException("GUID khong duoc null");
        }

        long high = guid.getMostSignificantBits();
        long low = guid.getLeastSignificantBits();

        ByteBuffer buffer = ByteBuffer.allocate(16)
                .order(ByteOrder.LITTLE_ENDIAN);

        buffer.putInt((int) (high >>> 32));  // Data1
        buffer.putShort((short) (high >>> 16)); // Data2
        buffer.putShort((short) high);         // Data3
        buffer.order(ByteOrder.BIG_ENDIAN).putLong(low); // Data4

        return buffer.array();
    }

    /**
     * Biểu diễn toàn bộ 16 byte dạng \hh theo RFC 4515.
     * Chỉ dùng cho giá trị của filter objectGUID cố định.
     */
    public static String escapeAsFilterOctets(byte[] raw) {
        if (raw == null || raw.length != 16) {
            throw new IllegalArgumentException(
                    "Binary GUID phai co 16 byte");
        }

        StringBuilder value = new StringBuilder(16 * 3);
        for (byte octet : raw) {
            int unsigned = octet & 0xff;
            value.append('\\');
            value.append(HEX.charAt(unsigned >>> 4));
            value.append(HEX.charAt(unsigned & 0x0f));
        }
        return value.toString();
    }
}
~~~

Giải thích chi tiết:

1. `fromAdBytes` từ chối dữ liệu thiếu hoặc có độ dài khác 16, tránh tạo UUID sai một cách thầm lặng.
2. `ByteOrder.LITTLE_ENDIAN` áp dụng khi đọc 4 + 2 + 2 byte đầu tiên.
3. `Integer.toUnsignedLong` và `Short.toUnsignedInt` tránh ảnh hưởng dấu của kiểu Java khi ghép các trường.
4. `ByteOrder.BIG_ENDIAN` đọc tám byte cuối theo đúng thứ tự hiển thị.
5. `toAdBytes` thực hiện chiều ngược, cần thiết nếu truy vấn `objectGUID` bằng LDAP filter nhị phân.
6. `escapeAsFilterOctets` chuyển từng byte thành `\hh`. Chuỗi sinh ra từ **bytes đã chuẩn hóa**, không chứa tên attribute hay filter logic từ user.

**Không dùng** `UUID.nameUUIDFromBytes(raw)`: API này tạo UUID bằng cách băm byte, không giải mã `objectGUID`. Cũng không dùng `new String(raw, UTF_8)` hoặc `UUID.fromString(...)` trực tiếp trên nội dung nhị phân.

### 5.1. Định dạng GUID đầu vào của API

Nếu một HTTP API nhận GUID dạng chuỗi, hãy kiểm tra định dạng và dùng `UUID.fromString(...)` sau khi validation; hàm này chỉ dành cho **chuỗi GUID**, không dành cho 16 byte LDAP:

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

public final class GuidInput {
    private static final Pattern CANONICAL = Pattern.compile(
        "(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
        + "[0-9a-f]{4}-[0-9a-f]{12}");

    private GuidInput() {}

    public static UUID parse(String value) {
        if (value == null || !CANONICAL.matcher(value).matches()) {
            throw new IllegalArgumentException("GUID khong dung dinh dang");
        }
        return UUID.fromString(value);
    }
}
~~~

Kiểm tra regex giúp yêu cầu **đúng dạng 8-4-4-4-12** thay vì phụ thuộc toàn bộ vào độ chặt của parser. Khi lưu dưới dạng String, chọn một quy ước canonical duy nhất, ví dụ `uuid.toString()` chữ thường có dấu gạch nối.

## 6. Đọc `objectGUID` qua `LdapTemplate` và `DirContextOperations`

Trong Spring LDAP, `ContextMapper<T>` cho phép lấy cả **context entry và thuộc tính**. Khi cần GUID + DN, đây là lựa chọn dễ hiểu hơn `AttributesMapper` chỉ có tập attribute.

### 6.1. Kết nối Spring Boot

Ví dụ dependency Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

`application.yml` minh họa một AD LDAP endpoint:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://dc01.corp.example:636}
    base: ${LDAP_BASE_DN:DC=corp,DC=example}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
    base-environment:
      "java.naming.ldap.attributes.binary": "objectGUID"
~~~

Ví dụ bind DN kỹ thuật: `CN=svc-directory-reader,OU=Service Accounts,DC=corp,DC=example`, với mật khẩu lấy từ secret manager. Cấu hình `java.naming.ldap.attributes.binary` là thuộc tính môi trường của **LDAP JNDI provider trên JVM** để yêu cầu coi tên attribute đã liệt kê là nhị phân. Với provider đã nhận biết `objectGUID` là binary, cấu hình này có thể không cần thiết, nhưng khai báo tường minh hữu ích khi kiểm tra tính di động.

**Không phải một cấu hình chuẩn chung cho mọi LDAP client:** hành vi có thể khác ở provider hoặc phiên bản JNDI; kiểm tra thực tế đối tượng được trả về có kiểu `byte[]`. Nếu cần thêm binary attributes, xác định danh sách qua schema/provider, ví dụ `objectSid` khi chức năng thật sử dụng, nhưng không dùng chung codec GUID để xử lý SID.

Kết nối phải sử dụng LDAPS hoặc StartTLS được cấu hình đúng và xác minh CA/hostname. Không tắt kiểm tra TLS để đọc được GUID và không đặt credential trong Git.

### 6.2. DTO đọc từ directory

~~~java
import java.util.UUID;

public record AdDirectoryUser(
        UUID objectGuid,
        String relativeDn,
        String accountName,
        String displayName) {
}
~~~

`relativeDn` chỉ là **vị trí entry hiện tại** so với context base. `objectGuid` là **định danh entry** do server AD trả về. Không lưu DN vào field GUID hoặc suy GUID từ username.

### 6.3. Mapper có kiểm tra kiểu và độ dài

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

public final class AdDirectoryUserMapper
        implements ContextMapper<AdDirectoryUser> {

    @Override
    public AdDirectoryUser mapFromContext(Object source) {
        DirContextOperations entry = (DirContextOperations) source;

        Object rawValue = entry.getObjectAttribute("objectGUID");
        if (!(rawValue instanceof byte[] rawGuid)) {
            throw new IllegalStateException(
                    "objectGUID khong duoc tra ve duoi dang byte[]");
        }

        return new AdDirectoryUser(
                AdObjectGuidCodec.fromAdBytes(rawGuid),
                entry.getDn().toString(),
                entry.getStringAttribute("sAMAccountName"),
                entry.getStringAttribute("cn"));
    }
}
~~~

Mapper cố ý **fail fast** khi server không trả đúng kiểu. Nếu attribute thiếu do projection, ACL hoặc môi trường JNDI, không tạo GUID giả, không dùng DN/email làm ID fallback. Ở các trường hợp đó, việc đồng bộ hoặc trả kết quả định danh nên báo lỗi cấu hình/dữ liệu cho người vận hành.

Đối với Java record trả `UUID` và `String`, không có nguy cơ caller sửa mảng raw. Nếu ứng dụng cần giữ `byte[]` trong DTO hoặc cache, hãy **clone khi nhận và khi trả** để tránh đối tượng khác sửa nội dung mảng.

### 6.4. Truy vấn thực tế bằng `LdapTemplate.search`

~~~java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class AdDirectoryReader {
    private final LdapTemplate ldapTemplate;
    private final AdDirectoryUserMapper mapper =
            new AdDirectoryUserMapper();

    public AdDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<AdDirectoryUser> byAccountName(String accountName) {
        if (accountName == null || accountName.isBlank()
                || accountName.length() > 128) {
            throw new IllegalArgumentException(
                    "Account name khong hop le");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("OU=People")
                .attributes("objectGUID", "sAMAccountName", "cn")
                .countLimit(20)
                .where("objectClass").is("user")
                .and("sAMAccountName").is(accountName);

        return ldapTemplate.search(query, mapper);
    }
}
~~~

Ở đây, `.attributes(...)` yêu cầu tường minh `objectGUID` và các thuộc tính DTO cần. Nếu không yêu cầu GUID, server có thể không trả attribute đó cùng kết quả search. `.where(...).is(accountName)` dùng query builder để escape **giá trị filter**, không nối trực tiếp input vào cú pháp LDAP.

Đường tìm kiếm `OU=People` là ví dụ. AD thật có thể tổ chức user ở nhiều OU, CN=Users hoặc cấu trúc khác; phải điều chỉnh base/scope theo topology và ACL. `objectClass=user` là thuộc tính đặc trưng AD, **không** thể chuyển nguyên sang mọi server OpenLDAP.

Kết quả `search` có thể là 0, 1 hoặc nhiều entry tùy filter và vùng tìm. Nếu nghiệp vụ kỳ vọng một user duy nhất, không tùy tiện chọn phần tử đầu tiên; cần policy về tính duy nhất và xử lý kết quả bất thường.

## 7. Tìm entry theo GUID bằng LDAP filter nhị phân

Khi đã có một GUID chuẩn do người dùng hoặc database cung cấp, **không** viết trực tiếp:

~~~ldap
(objectGUID=00112233-4455-6677-8899-aabbccddeeff)
~~~

Giá trị `objectGUID` trong filter của AD là giá trị nhị phân; một chuỗi UUID hiển thị như trên không phải chuỗi octet nhị phân tương ứng. Cần chuyển UUID về **byte[] theo cách lưu AD** rồi escape từng byte dưới dạng `\hh` theo RFC 4515.

Với GUID mẫu `00112233-4455-6677-8899-aabbccddeeff`, filter đúng về hình thức là:

~~~ldap
(objectGUID=\33\22\11\00\55\44\77\66\88\99\aa\bb\cc\dd\ee\ff)
~~~

Mỗi `\hh` biểu diễn một octet, gồm cả byte `00`. Đây là cách thể hiện giá trị **binary assertion**, không phải filter có wildcard. Việc escape toàn bộ 16 byte làm cho giá trị không thể phá cú pháp filter.

### 7.1. Hàm tạo filter với tên thuộc tính cố định

~~~java
import java.util.UUID;

public final class AdGuidFilters {
    private AdGuidFilters() {}

    public static String objectGuidEquals(UUID guid) {
        byte[] raw = AdObjectGuidCodec.toAdBytes(guid);
        return "(objectGUID="
                + AdObjectGuidCodec.escapeAsFilterOctets(raw)
                + ")";
    }
}
~~~

Trong hàm này **`objectGUID` là tên attribute cố định do server lựa chọn**, còn tất cả byte đến từ UUID đã parse. Đây là trường hợp an toàn để dựng một filter binary theo template; không tổng quát hóa thành hàm nhận arbitrary filter string, arbitrary attribute hoặc raw DN từ HTTP client.

### 7.2. Tích hợp truy vấn theo GUID vào `LdapTemplate`

~~~java
import java.util.List;
import java.util.UUID;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public List<AdDirectoryUser> byGuid(
        LdapTemplate ldapTemplate, UUID guid) {
    LdapQuery query = LdapQueryBuilder.query()
            .base("OU=People")
            .attributes("objectGUID", "sAMAccountName", "cn")
            .countLimit(2)
            .filter(AdGuidFilters.objectGuidEquals(guid));

    return ldapTemplate.search(query, new AdDirectoryUserMapper());
}
~~~

Ví dụ đặt `OU=People` để giới hạn vùng tìm kiếm. Nếu entry có thể được di chuyển sang OU khác, một truy vấn ở OU cũ sẽ không tìm thấy entry dù GUID không đổi. Cần thiết kế base **bao phủ những OU thuộc phạm vi nghiệp vụ**, kết hợp ACL và authorization, thay vì tự động cho mọi HTTP request quét root rộng.

`countLimit(2)` cho phép phát hiện trường hợp bất thường nhiều kết quả khi ứng dụng kỳ vọng một GUID duy nhất, nhưng giới hạn này không thay thế kiểm tra lỗi/điều kiện. Với AD, `objectGUID` được thiết kế để định danh đối tượng; nếu truy vấn không trả một entry như dự kiến, kiểm tra provider, cách chuyển byte, base/scope, ACL, replication và vòng đời entry trước khi kết luận đối tượng đã bị xóa.

**Cẩn thận double escaping:** chuỗi `\33...` được tạo sẵn theo RFC 4515 là *filter assertion value đã escape*. Nếu chuyển lại nó như một **giá trị văn bản** cho một filter builder tiếp tục escape, filter có thể không còn khớp byte. Hãy chọn **một** chiến lược xây binary filter và kiểm thử biểu thức thực tế gửi đến directory.

## 8. `AttributesMapper`, `ContextMapper` và ODM có gì khác?

Bạn có thể đọc GUID qua nhiều lớp Spring LDAP, nhưng lựa chọn mapper ảnh hưởng khả năng truy cập DN và kiểm soát kiểu.

| Cơ chế | Dữ liệu mapper nhận | Điểm mạnh | Cần chú ý với `objectGUID` |
| --- | --- | --- | --- |
| `AttributesMapper<T>` | `javax.naming.directory.Attributes`. | Đơn giản nếu chỉ cần attribute. | Lấy `Attribute.get()` dưới dạng `byte[]`, không ép thành String. |
| `ContextMapper<T>` | Context adapter, thường dùng `DirContextOperations`. | Lấy cả DN và attribute, tiện cho DTO. | Gọi `getObjectAttribute("objectGUID")`, kiểm tra `instanceof byte[]`. |
| `AbstractContextMapper<T>` | `DirContextOperations` trong `doMapFromContext`. | Class mapper tái sử dụng, không ép kiểu mỗi lần. | Thực hiện codec và chính sách thiếu field như ContextMapper. |
| LDAP ODM `@Entry`/`@Attribute` | Entity qua annotation. | Tốt với các entry cần repository và CRUD. | Nếu map binary field, phải xử lý đúng kiểu và **không vô tình ghi** attribute do AD quản lý. |

### 8.1. Ví dụ `AttributesMapper` tối giản

~~~java
import java.util.UUID;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;

public final class GuidOnlyMapper implements AttributesMapper<UUID> {

    @Override
    public UUID mapFromAttributes(Attributes attributes)
            throws NamingException {
        Attribute attribute = attributes.get("objectGUID");
        if (attribute == null) {
            throw new IllegalStateException("Thieu objectGUID");
        }
        Object value = attribute.get();
        if (!(value instanceof byte[] raw)) {
            throw new IllegalStateException(
                    "objectGUID khong phai byte[]");
        }
        return AdObjectGuidCodec.fromAdBytes(raw);
    }
}
~~~

Trong `AttributesMapper` không có phương thức `getDn()`. Nếu cần cả DN, dùng `ContextMapper` hoặc `AbstractContextMapper` như ở mục 6.

### 8.2. Entity ODM và thuộc tính chỉ đọc

Một entity Spring Data LDAP cho user AD có thể khai báo:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "OU=People", objectClasses = {"top", "person",
        "organizationalPerson", "user"})
public class AdPersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "sAMAccountName")
    private String accountName;

    @Attribute(name = "cn")
    private String commonName;

    // Getter/setter, constructor và mapping khác tùy project.
}
~~~

Entity minh họa **không tự map `objectGUID` vào trường có thể ghi**. Với truy vấn DTO cần stable ID, dùng mapper `AdDirectoryUserMapper` để lấy `objectGUID` riêng. Lý do là `objectGUID` do AD quản lý, không được xem là thuộc tính ứng dụng có thể sửa bằng `save`/`modifyAttributes`.

Nếu dự án muốn ODM ánh xạ `byte[]` của `objectGUID` vào một entity dùng cho đọc, cần kiểm tra khả năng ánh xạ binary (ví dụ loại thuộc tính BINARY được thư viện hỗ trợ), cách nạp field và **cách loại trừ attribute khỏi luồng ghi** của phiên bản Spring LDAP đang dùng. Không giả định chỉ thêm `@Attribute(name = "objectGUID")` là đã an toàn cho mọi thao tác repository `save`.

### 8.3. DTO khác entity ghi

Việc tách **read DTO** với **write entity** đặc biệt có ích khi directory chứa các thuộc tính do server quản lý hoặc dữ liệu nhạy cảm. Nếu chỉ cần trả tên và GUID:

~~~java
public record DirectoryIdentityView(
        String guid,
        String displayName) {
}
~~~

Service có thể tạo từ `AdDirectoryUser`:

~~~java
DirectoryIdentityView view = new DirectoryIdentityView(
        user.objectGuid().toString(),
        user.displayName());
~~~

Không trả `byte[]` raw hoặc toàn bộ `DirContextOperations` cho HTTP client chỉ vì ứng dụng đã đọc được chúng.

## 9. Thiết kế lưu `objectGUID` trong database ứng dụng

Nếu dùng AD làm nguồn danh tính và PostgreSQL làm dữ liệu nghiệp vụ, cần liên kết ID nội bộ với GUID theo **namespace directory**:

~~~text
Active Directory:
  provider_key:  corp-ad
  objectGUID:    00112233-4455-6677-8899-aabbccddeeff
  current DN:    CN=Lan Nguyen,OU=People,DC=corp,DC=example
                         |
                         v
directory_identity_link:
  provider_key:  corp-ad
  external_id:   00112233-4455-6677-8899-aabbccddeeff
  app_user_id:   10f4c8df-4c56-45f8-9b3c-a87875e3a3a3
                         |
                         v
app_user.id:      10f4c8df-4c56-45f8-9b3c-a87875e3a3a3
                         ^
                         |
orders.owner_id / audit.actor_id / permissions.subject_id
~~~

Một schema ví dụ:

~~~sql
CREATE TABLE directory_identity_link (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_user_id        UUID NOT NULL REFERENCES app_user(id),
    provider_key       VARCHAR(100) NOT NULL,
    external_id        UUID NOT NULL,
    relative_dn        TEXT,
    account_snapshot   VARCHAR(200),
    last_seen_at       TIMESTAMPTZ,
    CONSTRAINT uq_directory_identity UNIQUE (provider_key, external_id)
);
~~~

Trong ví dụ này, `external_id` là UUID chuẩn đã chuyển đúng từ raw AD GUID; không lưu chuỗi byte trộn endian như ID khác. Nếu hệ thống cùng bảng liên kết nhiều provider với external ID không có dạng UUID, hãy dùng kiểu text/cột phân loại phù hợp thay vì bắt mọi nguồn vào `UUID`.

Quy tắc đồng bộ:

1. Mỗi entry được nhận diện qua `(provider_key, external_id)`, không qua DN hay email.
2. Khi rename/move giữ nguyên GUID, cập nhật `relative_dn`/`account_snapshot` và giữ `app_user_id`.
3. Khi xóa rồi tạo lại với GUID mới, không tự liên kết người mới với user cũ chỉ vì trùng tên đăng nhập.
4. Nếu migration sang directory khác làm GUID thay đổi, sử dụng quy trình linking có bằng chứng và audit.
5. Dùng unique constraint, transaction và upsert idempotent để xử lý chạy song song; không mặc định LDAP và database có transaction chung.

**Giới hạn:** `objectGUID` định danh đối tượng directory, không tự nói người đó được phép đăng nhập hoặc có vai trò gì. Authentication/authorization vẫn là trách nhiệm của Spring Security hoặc IdP và chính sách ứng dụng.

## 10. Lưu ý schema và khác biệt giữa server LDAP

| Vấn đề | Active Directory | Directory hỗ trợ `entryUUID` theo RFC 4530 | Hệ quả với code |
| --- | --- | --- | --- |
| Thuộc tính định danh entry | `objectGUID`. | `entryUUID` nếu server triển khai chuẩn. | Cần adapter theo provider; không hardcode một attribute cho mọi server. |
| Dạng giá trị thường gặp | Binary 16 byte. | Chuỗi UUID theo syntax RFC. | AD cần codec endian; `entryUUID` không dùng codec AD byte[] mặc định. |
| Tên đăng nhập | Thường `sAMAccountName`/`userPrincipalName`. | Có thể `uid`. | Filter tìm user tùy schema, không chỉ thay URL. |
| DN/RDN | User có thể dùng `CN=...`, OU đa dạng. | Có thể dùng `uid=...` theo tổ chức. | Không suy DN từ username khi directory không cam kết. |
| Nhóm | Có `member`, `memberOf` theo mô hình AD. | Có thể dùng `uniqueMember`, `member` hoặc schema khác. | Cấu hình group search/roles riêng. |
| Quyền server | Security descriptor/ACL của AD. | Cơ chế ACL tùy nhà cung cấp. | Kiểm thử bằng tài khoản bind thật. |
| Replication | Theo topology domain controller. | Tùy server/kiến trúc. | Dữ liệu/thuộc tính có thể chưa đồng bộ ngay giữa endpoint. |

Nếu ứng dụng dùng Spring Data LDAP cho nhiều sản phẩm directory, đặt một lớp `DirectoryIdentityAdapter` theo provider để trả về **external ID đã chuẩn hóa**, rồi dùng chung quy trình đồng bộ:

~~~java
public interface DirectoryIdentityAdapter {
    String providerKey();
    String externalIdOf(Object ldapEntry);
}
~~~

Interface này minh họa ranh giới thiết kế. Trong code thật, nên dùng kiểu `DirContextOperations`/domain type thay `Object` khi phù hợp và test riêng AD binary GUID, `entryUUID`, schema khác nhau. Đặc biệt, **không coi `objectSid` là GUID** hoặc dùng `UUID.fromString(...)` với dữ liệu SID nhị phân.

## 11. Kiểm thử bộ chuyển đổi không cần LDAP server

Bộ codec là hàm thuần Java, nên có thể unit test bằng một GUID và dãy byte đã biết.

### 11.1. JUnit 5: chiều đọc và chiều ghi

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.HexFormat;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AdObjectGuidCodecTest {

    private static final UUID GUID = UUID.fromString(
            "00112233-4455-6677-8899-aabbccddeeff");
    private static final byte[] RAW = HexFormat.of().parseHex(
            "33221100554477668899aabbccddeeff");

    @Test
    void convertsRawAdBytesToCanonicalGuid() {
        assertEquals(GUID, AdObjectGuidCodec.fromAdBytes(RAW));
    }

    @Test
    void convertsGuidBackToAdBytes() {
        assertArrayEquals(RAW, AdObjectGuidCodec.toAdBytes(GUID));
    }

    @Test
    void createsBinaryFilterAssertionValue() {
        assertEquals(
                "\\33\\22\\11\\00\\55\\44\\77\\66"
                + "\\88\\99\\aa\\bb\\cc\\dd\\ee\\ff",
                AdObjectGuidCodec.escapeAsFilterOctets(RAW));
    }

    @Test
    void rejectsInvalidLength() {
        assertThrows(IllegalArgumentException.class,
                () -> AdObjectGuidCodec.fromAdBytes(new byte[15]));
        assertThrows(IllegalArgumentException.class,
                () -> AdObjectGuidCodec.fromAdBytes(null));
    }

    @Test
    void validatesInputGuidText() {
        assertEquals(GUID, GuidInput.parse(GUID.toString()));
        assertThrows(IllegalArgumentException.class,
                () -> GuidInput.parse("00112233"));
    }
}
~~~

**Vì sao test bằng dãy byte cố định quan trọng?** Nếu chỉ kiểm tra `fromAdBytes(toAdBytes(uuid)) == uuid`, hai hàm có thể cùng sai theo một quy tắc và vẫn vượt qua test. Vector `00112233-...` ↔ `33 22 11 00 ...` giúp phát hiện lỗi đổi endian ở từng nhóm.

### 11.2. Test mapper khi attribute sai kiểu

Thêm các trường hợp:

- `objectGUID` không được trả về (không có trong projection hoặc ACL không cho đọc).
- JNDI trả `String` hoặc loại object không mong đợi thay vì `byte[]`.
- Mảng byte có 0, 15 hoặc 17 phần tử.
- GUID có byte bằng `00`, `ff` và các byte có bit cao để kiểm tra chuyển kiểu số nguyên không dấu.
- Mapper nhận đúng DN tương đối và tên đăng nhập ngay cả khi user có RDN `CN`.

Với `DirContextAdapter`, có thể tạo context giả lập và thiết lập attribute `objectGUID` nhị phân, nhưng cách tạo/kiểu trả về phải được kiểm tra theo phiên bản thư viện. Unit test mapping không thay thế kiểm thử JNDI với domain controller thật hoặc môi trường test có AD tương thích.

## 12. Kiểm thử tích hợp với directory

### 12.1. Xác minh thuộc tính do AD trả về

Trên môi trường được phép, dùng `ldapsearch` với tài khoản dịch vụ chỉ đọc:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://dc01.corp.example:636" \
  -D "CN=svc-directory-reader,OU=Service Accounts,DC=corp,DC=example" -W \
  -b "OU=People,DC=corp,DC=example" -s sub \
  "(sAMAccountName=lan)" dn objectGUID sAMAccountName cn
~~~

`-W` hỏi mật khẩu tương tác; không để mật khẩu trên command line hoặc trong log. Nếu `objectGUID` được in bằng `objectGUID:: ...`, đó là Base64 của bytes nhị phân. Có thể đối chiếu GUID chuẩn bằng công cụ quản trị AD do tổ chức cho phép. Chú ý rằng `ldapsearch` và JVM có thể dùng kho chứng chỉ TLS khác nhau.

Nếu search không trả `objectGUID`:

1. Kiểm tra entry, base/scope và filter đúng cho AD.
2. Xác nhận đã yêu cầu attribute `objectGUID` tường minh.
3. Kiểm tra quyền đọc của bind account và policy server.
4. Xác minh JNDI binary settings nếu Java nhận kiểu không đúng.
5. Không tự rơi về `sAMAccountName`/DN làm stable ID thay thế.

### 12.2. Ma trận tích hợp theo vòng đời entry

| Kịch bản | Thao tác trong môi trường test | Kỳ vọng |
| --- | --- | --- |
| Đọc GUID của user. | Search theo `sAMAccountName`, yêu cầu `objectGUID`. | Java nhận 16 byte, codec chuyển thành GUID chuẩn. |
| Tìm lại bằng GUID. | Dùng filter binary `(objectGUID=\hh...)`. | Trả đúng entry ban đầu, với base/scope phù hợp. |
| Rename CN hoặc move OU. | Đổi DN entry test hợp lệ. | GUID vẫn đại diện cùng entry; tìm theo GUID ở phạm vi mới phù hợp. |
| Xóa và tạo mới trùng username. | Dùng dữ liệu thử nghiệm được cấp quyền. | GUID mới thường khác; hệ thống không tự ghép link cũ. |
| JNDI không cấu hình binary đúng. | Kiểm tra kiểu attribute thực tế. | Cảnh báo/exception rõ, không chuyển String tùy tiện. |
| Search chỉ trả `cn`, không trả `objectGUID`. | Giới hạn attributes projection. | Mapper báo thiếu GUID, không tạo ID giả. |
| Tài khoản bind mất quyền đọc. | Thu hẹp ACL trên môi trường thử nghiệm. | Query có thể lỗi/thiếu attribute; không coi là identity mới. |
| Server thứ hai chưa đồng bộ. | Đọc cùng user qua replica khác. | Không kết luận entry bị xóa từ một kết quả rỗng hoặc cũ. |
| Tài khoản chỉ đọc thử sửa `objectGUID`. | Chỉ trên môi trường test được quản trị. | Server từ chối; ứng dụng không thiết kế luồng ghi GUID. |
| Input GUID thiếu dấu gạch hoặc sai độ dài. | Gọi API nhận GUID dạng chuỗi. | Validation từ chối, không gửi filter thô tới LDAP. |

Các test có thao tác rename/xóa/tạo entry chỉ thực hiện trên **directory test** và theo quyền cho phép. Không thử trực tiếp trên dữ liệu production hoặc tài khoản thật của người dùng.

## 13. Lỗi thường gặp và chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `ClassCastException` khi ép `objectGUID` thành `String`. | Attribute là nhị phân. | Đọc `byte[]` qua `getObjectAttribute`/JNDI và codec. |
| UUID in ra khác GUID hiển thị trong AD. | Đọc 16 byte như hai long big-endian hoặc đảo sai byte. | Kiểm tra quy tắc Data1/Data2/Data3 little-endian và Data4 big-endian. |
| `UUID.fromString(...)` báo lỗi khi đọc `objectGUID`. | Đưa binary bytes hoặc Base64 vào parser chuỗi GUID. | Chuyển raw 16 byte bằng `AdObjectGuidCodec.fromAdBytes`. |
| Filter GUID không trả entry. | Dùng chuỗi UUID trực tiếp thay vì binary filter, hoặc base sai. | Chuyển UUID → AD bytes → `\hh`; kiểm tra scope và quyền. |
| Mapper báo thiếu `objectGUID`. | Query không yêu cầu attribute, ACL không đủ, JNDI cấu hình sai. | Kiểm tra projection/bind và server schema. |
| GUID tự nhiên “thay đổi” sau khi tạo lại account. | Đây có thể là một entry mới, dù DN/email/username giống. | Dùng quy trình provisioning/linking có xác minh; không nhập nhằng hai danh tính. |
| Repository `save` cố sửa `objectGUID`. | Entity ánh xạ operational/server-managed attribute như field ghi được. | Tách read DTO và write entity; không cho app ghi GUID. |
| Lỗi TLS/bind dù code codec đúng. | Truststore JVM, certificate, account secret hoặc ACL. | Sửa kết nối/quyền trước; codec không giải quyết lỗi bind. |
| Dữ liệu từ hai server khác nhau không khớp. | Directory/forest khác hoặc replication lag. | Gắn `provider_key`, theo dõi replication và dùng nguồn có thẩm quyền. |

Ngoài ra, `objectGUID` có thể khác cấu trúc dữ liệu nhị phân khác như `objectSid`. Không cố viết một bộ chuyển đổi `byte[] -> UUID` cho mọi thuộc tính binary; hãy chọn codec dựa vào **schema và ngữ nghĩa** của attribute.

## 14. Bài tập thực hành

Một ứng dụng Spring Boot đọc người dùng từ AD với base `DC=company,DC=internal`, tài khoản dịch vụ chỉ đọc và entry:

~~~text
DN:               CN=Mai Le,OU=Employees,DC=company,DC=internal
sAMAccountName:   mai
cn:               Mai Le
objectGUID text:  00112233-4455-6677-8899-aabbccddeeff
objectGUID bytes: 33 22 11 00 55 44 77 66 88 99 aa bb cc dd ee ff
~~~

**Yêu cầu:**

1. Giải thích vì sao không dùng `getStringAttribute("objectGUID")` hoặc `new String(rawBytes)` để lấy GUID chuẩn.
2. Dùng `ByteBuffer` hoặc xử lý các nhóm byte để chuyển dữ liệu trên thành UUID đúng; nêu rõ nhóm nào little-endian.
3. Viết unit test xác minh `UUID.fromString("00112233-4455-6677-8899-aabbccddeeff")` tương ứng 16 byte đã cho.
4. Tạo filter LDAP theo GUID từ dữ liệu nhị phân; giải thích sự khác nhau với `(objectGUID=00112233-...)`.
5. Viết `LdapQueryBuilder` yêu cầu các thuộc tính `objectGUID`, `sAMAccountName` và `cn` dưới `OU=Employees`.
6. Nếu người dùng chuyển từ `OU=Employees` sang `OU=Alumni` nhưng GUID không đổi, ứng dụng nên dùng khóa nào để giữ liên kết với database và điều chỉnh search base ra sao?
7. Nếu xóa rồi tạo lại user có `sAMAccountName=mai` nhưng GUID khác, có được tự gán vào bản ghi cũ chỉ vì username/email trùng không?
8. Trình bày khác biệt giữa `objectGUID` và `entryUUID` hoặc `objectSid`; vì sao cần adapter khác nhau?
9. Nếu tài khoản bind có quyền đọc `cn` nhưng không thấy `objectGUID`, hãy chỉ ra ba hướng kiểm tra trước khi thay đổi mapping.

**Gợi ý đáp án:**

- GUID AD là 16 byte có byte order hỗn hợp; ba nhóm `4+2+2` byte đầu được diễn giải little-endian, tám byte cuối giữ thứ tự.
- Test phải xác nhận vector byte chuẩn `33221100554477668899aabbccddeeff` → `00112233-4455-6677-8899-aabbccddeeff`; không chỉ kiểm tra round-trip.
- Filter binary: `(objectGUID=\33\22\11\00\55\44\77\66\88\99\aa\bb\cc\dd\ee\ff)`.
- Query dùng `.base("OU=Employees").attributes("objectGUID","sAMAccountName","cn")` và filter theo username hoặc GUID đã được xây an toàn.
- Lưu `(provider_key, objectGUID)` làm khóa liên kết ngoài tới `app_user.id`; DN chỉ là snapshot. Nếu user chuyển OU, mở rộng đúng vùng tìm được cấp quyền hoặc tìm theo GUID qua nguồn có thẩm quyền.
- Xóa/tạo lại là vòng đời entry khác; không tự gộp vào user cũ qua username/email.
- `entryUUID` thường là UUID dạng chuỗi của RFC 4530; `objectSid` là SID binary với cấu trúc khác GUID.
- Kiểm tra projection đã yêu cầu attribute, ACL/quyền server và JNDI binary settings trước khi tạo ID fallback.

## 15. Ghi nhớ

**`objectGUID` trong Active Directory là dữ liệu nhị phân 16 byte, không phải chuỗi UUID trực tiếp.** Để hiển thị/lưu thành `java.util.UUID`, cần đọc ba trường đầu theo **little-endian** (4 + 2 + 2 byte) và tám byte cuối theo **big-endian**. Để tìm lại entry theo GUID, phải chuyển UUID thành đúng 16 byte AD rồi escape từng octet thành `\hh` trong LDAP filter.

Trong Spring Data LDAP, `LdapTemplate` và `ContextMapper`/`AttributesMapper` giúp chủ động xử lý thuộc tính nhị phân. ODM/repository phù hợp với các entry CRUD nhưng phải cẩn trọng với attribute do server quản lý như `objectGUID`. Khi liên kết dữ liệu sang database ứng dụng, kết hợp **provider key + GUID**, giữ DN và username là các thông tin có thể thay đổi. Cuối cùng, kiểm chứng bằng test vector cố định, truy vấn LDAP thực tế, ACL tối thiểu, TLS và các kịch bản rename/delete/recreate.

### Tài liệu tham khảo

- [Microsoft — objectGUID Attribute](https://learn.microsoft.com/en-us/windows/win32/adschema/a-objectguid)
- [Microsoft — Using objectGUID to Bind to an Object](https://learn.microsoft.com/en-us/windows/win32/ad/using-objectguid-to-bind-to-an-object)
- [Microsoft — GUID Structure](https://learn.microsoft.com/en-us/windows/win32/api/guiddef/ns-guiddef-guid)
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4530 — LDAP entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530)
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
