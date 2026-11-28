# Đọc dữ liệu nhị phân mà không chuyển chuỗi tùy ý

Khi làm việc với **Spring Data LDAP**, lập trình viên không chỉ ánh xạ `uid`, `cn` hoặc `mail` thành `String`. Directory có thể lưu **ảnh JPEG**, **chứng chỉ X.509**, **định danh nhị phân** và những thuộc tính có syntax không phải chuỗi. Nếu áp dụng `new String(bytes)`, `toString()` hay ép mọi giá trị LDAP thành `String`, ứng dụng dễ làm sai nội dung, mất dữ liệu hoặc tạo lỗi khó phát hiện.

Chủ đề này hướng dẫn đọc và ánh xạ dữ liệu nhị phân **đúng kiểu** qua `LdapTemplate`, `AttributesMapper`, `ContextMapper` và ODM của Spring LDAP, từ đó phục vụ những repository Spring Data LDAP. Nguyên tắc cơ bản là: **đọc nguyên vẹn `byte[]`, diễn giải bytes theo định dạng và schema đã biết, chỉ mã hóa thành văn bản ở ranh giới thật sự cần thiết**.

Sau bài học, bạn có thể:

- Phân biệt LDAP `String` và `byte[]` qua JNDI; hiểu vai trò của attribute syntax và `;binary`.
- Đọc `jpegPhoto` bằng `AttributesMapper<byte[]>` hoặc `DirContextOperations.getObjectAttribute(...)`.
- Khai báo field ODM có `@Attribute(type = Attribute.Type.BINARY)` và xử lý thuộc tính binary tùy chỉnh.
- Chọn **Base64**, **hex**, **UTF-8** hay parser chuyên biệt đúng mục đích, không chuyển chuỗi theo suy đoán.
- Xử lý các tình huống thiếu attribute, đa trị, ảnh lớn, dữ liệu không hợp lệ và rò rỉ thông tin.
- Kiểm thử vòng đọc–ghi và so sánh bytes để phát hiện mất dữ liệu.

## 1. Thực tế một LDAP entry có cả dữ liệu văn bản và nhị phân

Một entry mẫu trong cây thư mục (DIT) có thể chứa:

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
jpegPhoto:: /9j/4AAQSkZJRgABAQ...
```

Trong LDIF:

- `dn` là tên phân biệt của entry, không phải dữ liệu ảnh.
- `cn`, `uid` và `mail` thường được biểu diễn như văn bản theo schema tương ứng.
- `jpegPhoto` chứa **octets** (bytes) của ảnh, không phải câu chữ.
- Dấu **`::`** trong LDIF thể hiện giá trị ở dạng **Base64 theo cú pháp LDIF**. Nó **không phải** một phần của tên attribute và cũng không có nghĩa mọi giá trị LDIF có `::` đều là ảnh/binary về mặt nghiệp vụ.

Ví dụ `/9j/4AAQ...` chỉ là phần minh họa, **không phải ảnh JPEG đầy đủ**. Khi LDAP server trả về thông qua JNDI, ứng dụng thường nhận giá trị `jpegPhoto` dưới dạng `byte[]` — không phải chuỗi Base64 LDIF. Không cần giải mã Base64 lần nữa cho `byte[]` đã lấy trực tiếp từ JNDI.

### 1.1. Những ví dụ thường gặp

| LDAP attribute | Ý nghĩa dữ liệu | Java representation thường gặp |
| --- | --- | --- |
| `cn`, `sn`, `uid`, `mail` | Văn bản và mã định danh dạng chuỗi | `String` |
| `jpegPhoto` | Ảnh JPEG | `byte[]` |
| `thumbnailPhoto` | Ảnh thu nhỏ (phụ thuộc server/schema) | `byte[]` |
| `userCertificate;binary` | Chứng chỉ theo định dạng ASN.1/DER | `byte[]` |
| `cACertificate;binary` | Chứng chỉ CA dạng mã hóa DER | `byte[]` |
| `objectGUID` (Active Directory) | Định danh nhị phân đặc thù AD | `byte[]`, sau đó chuyển theo quy tắc GUID của AD |
| Thuộc tính `customBlob` tự định nghĩa | Octet string theo schema riêng | `byte[]` nếu JNDI được cấu hình nhận biết |

**Không có một quy tắc “thuộc tính tên gì cũng đọc bằng String”**. Tên, syntax, matching rule và lựa chọn biểu diễn của JNDI provider quyết định kiểu dữ liệu. Một số trường có cách mã hóa nhị phân riêng; không thể hiểu chúng đúng chỉ bằng cách chuyển toàn bộ bytes thành ký tự.

## 2. JNDI trả về `String` hay `byte[]` như thế nào?

Spring LDAP sử dụng **JNDI LDAP provider** để tương tác với directory. Khi truy vấn một entry, JNDI trả về đối tượng `javax.naming.directory.Attributes`; mỗi `Attribute` chứa một hoặc nhiều giá trị kiểu `Object`.

```text
LDAP server (ber/LDAP octets)
             │
             ▼
JNDI LDAP provider
             ├── thuộc tính dạng chuỗi -> String
             └── thuộc tính non-string -> byte[]
             │
             ▼
Attributes / Attribute.get()
             │
             ▼
Spring LDAP AttributesMapper / ContextMapper / ODM
```

Theo tài liệu JNDI của Oracle, provider có **danh sách nội bộ các thuộc tính non-string** thường gặp, bao gồm `jpegPhoto`, `thumbnailPhoto` và `userCertificate`; các tên attribute có option `;binary` cũng được xử lý đặc biệt. Ngoài danh sách có sẵn, ứng dụng có thể khai báo bổ sung các thuộc tính binary bằng môi trường JNDI.

Chẳng hạn, nếu biết một attribute tùy chỉnh thực sự có syntax nhị phân:

```java
import java.util.Map;
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://directory.example.org:636");
source.setBase("dc=example,dc=org");
// Cấu hình principal/password qua secret store bên ngoài ví dụ.
source.setBaseEnvironmentProperties(
        Map.of("java.naming.ldap.attributes.binary",
               "customBlob objectGUID"));
```

Giá trị của `java.naming.ldap.attributes.binary` là **danh sách tên attribute phân cách bằng khoảng trắng**, theo JNDI provider của Oracle; nó **mở rộng** danh sách binary built-in. Trong cấu hình bean thực tế, cần hoàn thiện bind credentials, TLS/truststore và lifecycle của `ContextSource` trước khi dùng.

**Lưu ý quan trọng:**

1. Chỉ thêm tên attribute mà **schema hoặc tài liệu directory xác nhận** là binary; không biến `cn`/`mail` thành binary để né vấn đề encoding.
2. Việc thêm tên vào môi trường JNDI làm thay đổi **kiểu đối tượng trả về cho việc đọc**, chứ không sửa schema hoặc dữ liệu trên server.
3. `objectGUID` là ví dụ riêng cho Active Directory, **không phải attribute chuẩn có ở mọi LDAP server**.
4. `setBaseEnvironmentProperties(...)` là cấu hình cấp `ContextSource`; cần kiểm tra mọi `LdapTemplate`/repository sử dụng đúng nguồn này.
5. Các server/JNDI provider khác có thể có danh sách mặc định và quy tắc riêng. Không suy ra kiểu dữ liệu từ tên Java field khi chưa kiểm tra giá trị thực tế.

## 3. Vì sao `new String(bytes)` và `bytes.toString()` là sai?

Ví dụ Java sau **không** đọc đúng nội dung ảnh:

```java
byte[] jpegBytes = /* bytes được trả từ LDAP */;

// SAI: hiểu byte ảnh thành ký tự theo charset mặc định hoặc do chỉ định tùy ý.
String text1 = new String(jpegBytes);
String text2 = new String(jpegBytes, java.nio.charset.StandardCharsets.UTF_8);

// SAI: toString() của mảng không hiển thị nội dung mảng.
String text3 = jpegBytes.toString();
```

| Cách viết | Vấn đề |
| --- | --- |
| `new String(bytes)` | Dùng charset mặc định hoặc cách xử lý ký tự không phù hợp; byte không mã hóa hợp lệ có thể bị thay thế |
| `new String(bytes, UTF_8)` | Chỉ có nghĩa khi **đã biết** bytes biểu diễn văn bản UTF-8 hợp lệ; ảnh và DER không phải UTF-8 |
| `bytes.toString()` | Thường cho chuỗi mô tả đối tượng kiểu `[B@...`, không phải dữ liệu |
| `Arrays.toString(bytes)` | Chỉ là biểu diễn số byte để debug, không phải định dạng ảnh hoặc chuỗi có thể xử lý nghiệp vụ |
| `(String) attribute.get()` | Có thể ném `ClassCastException` khi giá trị thực là `byte[]` |

Các luồng chuyển **bytes → String theo charset → bytes** có thể không bảo toàn dữ liệu nếu bytes ban đầu không hợp lệ với charset đó. Để bảo toàn dữ liệu nhị phân, giữ `byte[]` hoặc dùng một kiểu dữ liệu nhị phân khác (`ByteBuffer`, stream, file) theo yêu cầu của ứng dụng.

### 3.1. Khi nào chuyển chuỗi lại hợp lệ?

**Chỉ khi định dạng dữ liệu quy định đó là văn bản với một charset xác định.** Ví dụ một attribute tùy chỉnh có schema quy định chứa JSON UTF-8 nhưng được truyền dưới dạng octets: ứng dụng có thể giải mã qua `StandardCharsets.UTF_8` sau khi xác thực schema, giới hạn kích thước và xử lý lỗi giải mã.

Ngược lại, dữ liệu `jpegPhoto` phải được **giải mã như ảnh** (hoặc chuyển nguyên bytes tới trình hiển thị), còn `userCertificate;binary` phải được **phân tích theo X.509/ASN.1** nếu cần đọc chi tiết. Đổi chúng thành UTF-8 để “dễ xem” là sai lớp biểu diễn.

## 4. Đọc `jpegPhoto` bằng `AttributesMapper<byte[]>`

### 4.1. Viết một mapper kiểm tra đúng kiểu

`AttributesMapper<T>` chuyển `Attributes` của **mỗi LDAP entry** thành một giá trị Java. Với dữ liệu binary, tham số `T` có thể trực tiếp là `byte[]`:

```java
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;

public final class BinaryAttributeMapper
        implements AttributesMapper<byte[]> {

    private final String attributeName;

    public BinaryAttributeMapper(String attributeName) {
        this.attributeName = attributeName;
    }

    @Override
    public byte[] mapFromAttributes(Attributes attrs) throws NamingException {
        Attribute attr = attrs.get(attributeName);
        if (attr == null || attr.size() == 0) {
            return null;
        }

        Object raw = attr.get();
        if (!(raw instanceof byte[])) {
            throw new IllegalStateException(
                    "Expected binary LDAP attribute: " + attributeName
                    + ", actual type: " + raw.getClass().getName());
        }

        // Trả về bản sao để không chia sẻ mảng mutable với tầng JNDI.
        return ((byte[]) raw).clone();
    }
}
```

Đây là mapper cho **một giá trị** của attribute. Việc `Attribute#get()` chọn giá trị đầu tiên không mang nghĩa “giá trị chính” nếu LDAP attribute đa trị. Đối với `jpegPhoto`, một số directory/schema có thể cho phép nhiều ảnh; cách xử lý phải dựa trên nghiệp vụ.

Mapper **không tự dựng DN**. Nếu cần biết entry nào mang ảnh, hãy đọc bằng DN đã xác định hoặc dùng `ContextMapper` để lấy thông tin DN cùng bytes.

### 4.2. Dùng `LdapTemplate.lookup` khi đã biết DN

Giả sử `LdapContextSource` được cấu hình base `dc=example,dc=org`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class UserPhotoService {
    private final LdapTemplate ldapTemplate;

    public UserPhotoService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public byte[] readPhotoByUid(String uid) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return ldapTemplate.lookup(
                dn,
                new String[] {"jpegPhoto"},
                new BinaryAttributeMapper("jpegPhoto"));
    }
}
```

Ở ví dụ này:

- `dn` là **DN tương đối** so với base `dc=example,dc=org`; nếu có người dùng ở các OU khác, cần xác định đúng DN trước.
- `new String[] {"jpegPhoto"}` chỉ yêu cầu **attribute ảnh**, không tải toàn bộ `objectClass`, `mail` và các thuộc tính không cần.
- `lookup` đọc một entry theo DN, khác với `search` theo filter.
- Kết quả `null` nghĩa là mapper không nhận được thuộc tính/giá trị ảnh; nó **không đủ để khẳng định ảnh chưa tồn tại** nếu ACL hoặc quyền đọc chặn attribute.
- Nếu JNDI provider trả `String` cho một attribute được kỳ vọng là binary, mapper **báo lỗi cấu hình/kiểu dữ liệu**, không “sửa” bằng `getBytes()`.

**Tránh để đầu vào người dùng quyết định trực tiếp toàn bộ DN hoặc tên attribute.** `LdapNameBuilder` escape giá trị RDN; ứng dụng vẫn cần xác thực và phân quyền xem ảnh.

### 4.3. Đọc bằng `search` khi mới biết filter

Nếu cần tìm entry theo `mail` hoặc `uid` trong một subtree trước khi có DN, có thể kết hợp `LdapQueryBuilder` với mapper:

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .attributes("jpegPhoto")
        .countLimit(5)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(userSuppliedUid);

List<byte[]> photos = ldapTemplate.search(
        query, new BinaryAttributeMapper("jpegPhoto"));
```

`.is(userSuppliedUid)` xây **equality filter** với escape giá trị, giúp tránh ghép filter LDAP nguy hiểm. `.countLimit(5)` hạn chế số entry kết quả, **không** giới hạn số byte của một ảnh. Trong một directory lớn, truy vấn trả `jpegPhoto` cho hàng nghìn người sẽ dễ tốn bộ nhớ và băng thông; **không đưa ảnh vào search dùng để lập danh sách người dùng** nếu chỉ cần `uid`/`cn`.

## 5. Đọc nhị phân bằng `ContextMapper`

`ContextMapper<T>` thích hợp khi ngoài bytes, ứng dụng còn cần **DN** để định danh entry hoặc xử lý các giá trị trong cùng một context. Với `DirContextOperations` của Spring LDAP, phương thức **`getObjectAttribute`** đọc attribute dưới dạng `Object` và không ép kiểu chuỗi.

```java
import javax.naming.Name;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

record LocatedPhoto(String dn, byte[] imageBytes) {}

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

LocatedPhoto photo = ldapTemplate.lookup(
        dn,
        new String[] {"jpegPhoto"},
        (ContextMapper<LocatedPhoto>) context -> {
            DirContextOperations entry = (DirContextOperations) context;
            Object raw = entry.getObjectAttribute("jpegPhoto");

            if (raw == null) {
                return new LocatedPhoto(entry.getNameInNamespace(), null);
            }
            if (!(raw instanceof byte[])) {
                throw new IllegalStateException(
                        "jpegPhoto is not returned as byte[]");
            }
            return new LocatedPhoto(
                    entry.getNameInNamespace(),
                    ((byte[]) raw).clone());
        });
```

**Điểm cần nhớ:**

- `getObjectAttribute("jpegPhoto")` giữ kiểu Java thật của giá trị; khi JNDI cấu hình đúng, kết quả là `byte[]`.
- **Không** dùng `getStringAttribute("jpegPhoto")`: API này dành cho các attribute dạng `String` và có thể ném `ClassCastException`.
- `getDn()` thường trả DN **tương đối với context base**, còn `getNameInNamespace()` trả tên đầy đủ trong directory.
- Trong cấu hình mặc định, `ContextMapper` nhận một đối tượng `DirContextAdapter`/`DirContextOperations`; nếu dự án thay `DirObjectFactory`, phải kiểm tra kiểu context thực tế.
- `record` chứa `byte[]` **không tự sao chép mảng** trong constructor/getter. Nếu giữ dữ liệu lâu, cần chính sách defensive copy hoặc lớp DTO bất biến thực sự.

Khi attribute có **nhiều giá trị**, `getObjectAttribute` chỉ trả **một**. Có thể dùng `getObjectAttributes("jpegPhoto")` và duyệt `Object[]`, kiểm tra `instanceof byte[]` cho từng phần tử. Không áp dụng `getStringAttributes` cho attribute nhị phân.

## 6. Ánh xạ field binary với Spring LDAP ODM

Khi muốn lưu một entry như Java entity cho **Spring Data LDAP repository**, sử dụng annotation ODM của package `org.springframework.ldap.odm.annotations`.

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class Person {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(
        name = "jpegPhoto",
        type = Attribute.Type.BINARY
    )
    private byte[] jpegPhoto;

    public Person() {}

    // Thêm getter/setter và defensive copy cho byte[] theo thiết kế entity.
}
```

**`@Attribute(type = Attribute.Type.BINARY)`** cho ODM biết attribute cần được xử lý như **binary (`byte[]`)** thay vì chuỗi khi ánh xạ field. Nó khác với `@Id Name dn`, là tên entry. `@Entry(objectClasses=...)` còn phải phù hợp với schema của directory.

Ví dụ repository:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    List<Person> findByUid(String uid);
}
```

Không nên suy ra rằng việc gắn `@Attribute(type=BINARY)` cho field ODM sẽ tự thay đổi kiểu trả về của **mọi lời gọi JNDI/AttributesMapper riêng biệt** dùng `ContextSource` khác. Tầng ODM và cấu hình binary attribute của JNDI có **nhiệm vụ khác nhau**; với attribute không được provider nhận biết sẵn, cần kiểm tra cả hai.

### 6.1. Cẩn thận khi dùng repository để lập danh sách

Nếu mỗi entity `Person` đều có `jpegPhoto` dung lượng lớn, một lời gọi repository đọc 10.000 người dùng có thể làm tải về/ánh xạ rất nhiều bytes ngoài nhu cầu. **Đừng mặc định rằng repository sinh ra projection “nhẹ” chỉ vì API trả về tên người dùng**.

Đối với danh sách, ưu tiên truy vấn chỉ lấy `uid`, `cn`, `mail`; khi client mở chi tiết hoặc yêu cầu ảnh, mới dùng `LdapTemplate.lookup(dn, new String[]{"jpegPhoto"}, ...)` và chính sách cache hợp lệ.

## 7. `;binary` là option của LDAP attribute, không phải phép ép kiểu Java

LDAP hỗ trợ option dạng `attributeType;option`. Option **`;binary`** đặc biệt dùng cho truyền một số dạng dữ liệu mã hóa ASN.1, chẳng hạn chứng chỉ:

```text
userCertificate;binary
cACertificate;binary
```

Với certificate DER, đọc nguyên `byte[]`:

```java
import java.io.ByteArrayInputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

byte[] derBytes = /* byte[] đọc từ userCertificate;binary */;
CertificateFactory factory = CertificateFactory.getInstance("X.509");
X509Certificate certificate = (X509Certificate)
        factory.generateCertificate(new ByteArrayInputStream(derBytes));
```

Sau khi parse, ứng dụng có thể kiểm tra `subject`, `issuer`, thời hạn chứng chỉ hoặc public key theo nghiệp vụ. **Parse thành công không đồng nghĩa chứng chỉ đã đáng tin cậy**: muốn xác minh tính tin cậy phải thực hiện validation chain, chữ ký, chính sách, revocation và hostname/identity nếu ứng dụng cần.

Trong một số directory, client phải yêu cầu tên attribute **có option `;binary`** để server trả dạng được mong đợi. Tên/ID mà JNDI trả về có thể đi kèm option; hãy dùng tên đúng theo schema và server, kiểm tra `Attribute.getID()` khi cần chẩn đoán, **không in giá trị certificate** ra log.

Với dữ liệu như `objectGUID` của Active Directory, bytes mang định dạng định danh đặc thù; **không** dùng trực tiếp `new UUID(ByteBuffer.getLong(), ...)` mà chưa xét quy tắc byte order của GUID trên AD. Cần converter đã được kiểm chứng cho định dạng của chính server.

## 8. Base64, hex và UTF-8: dùng đúng ranh giới

### 8.1. Base64 dùng khi cần chuyển bytes sang văn bản có thể hoàn nguyên

Một hệ thống JSON không thể mang `byte[]` như một chuỗi ký tự gốc. Khi hợp đồng API yêu cầu ảnh ở dạng chuỗi Base64:

```java
import java.util.Base64;

byte[] imageBytes = /* đọc từ LDAP */;
String base64 = Base64.getEncoder().encodeToString(imageBytes);

// Khi bên nhận cần hoàn nguyên:
byte[] restored = Base64.getDecoder().decode(base64);
```

Base64 **là mã hóa biểu diễn (encoding), không phải mã hóa bảo mật (encryption)**. Nó không che giấu nội dung. Dung lượng biểu diễn Base64 khoảng **4/3** dung lượng bytes gốc (chưa tính JSON và overhead khác), nên không phải lựa chọn tối ưu cho mọi trường hợp truyền ảnh lớn.

Nếu API trả ảnh trực tiếp và phù hợp chính sách bảo mật, có thể sử dụng một response nhị phân với `Content-Type: image/jpeg`; khi đó **không cần Base64**. Chỉ khai báo MIME type sau khi xác minh định dạng và dữ liệu. Không đặt mọi blob là `image/jpeg` nếu server/schema chưa bảo đảm đó là JPEG hợp lệ.

### 8.2. Hex để kiểm tra metadata kỹ thuật

Hex giúp kiểm tra một vài bytes đầu hoặc đối chiếu checksum trong test:

```java
import java.util.HexFormat;

byte[] raw = new byte[] {(byte) 0xFF, (byte) 0xD8, (byte) 0xFF};
String prefix = HexFormat.of().formatHex(raw); // "ffd8ff"
```

`HexFormat` có từ Java 17; ở phiên bản Java cũ hơn, dùng thư viện hoặc utility thích hợp. Không log cả blob dưới dạng hex tại production: dữ liệu vẫn có thể bị khôi phục và log sẽ rất lớn.

### 8.3. UTF-8 chỉ cho bytes được định nghĩa là văn bản

```java
import java.nio.charset.StandardCharsets;

// CHỈ hợp lệ nếu schema/hợp đồng dữ liệu xác nhận rawUtf8 là văn bản UTF-8.
String actualText = new String(rawUtf8, StandardCharsets.UTF_8);
```

Với dữ liệu bên ngoài không chắc hợp lệ, `new String(bytes, UTF_8)` có thể thay thế byte lỗi bằng ký tự thay thế. Nếu việc bảo toàn nguyên văn là bắt buộc, dùng `CharsetDecoder` với chế độ `CodingErrorAction.REPORT` để phát hiện dữ liệu không hợp lệ thay vì âm thầm thay thế.

**Bảng quyết định:**

| Dữ liệu đầu vào | Mục tiêu | Cách phù hợp |
| --- | --- | --- |
| `byte[]` JPEG | Render ảnh | Giữ bytes và giải mã ảnh bằng thư viện ảnh |
| `byte[]` JPEG | Đưa vào trường JSON text có hợp đồng Base64 | `Base64.encodeToString` |
| `byte[]` DER certificate | Đọc trường certificate | `CertificateFactory` hoặc parser ASN.1/X.509 |
| `byte[]` custom text UTF-8 có schema rõ | Đọc văn bản | `UTF-8 decoder` có kiểm tra lỗi |
| `byte[]` objectGUID của AD | Hiển thị GUID | Converter định dạng GUID theo AD |
| `String` `cn` | Hiển thị tên | Giữ `String`, không tự ép Base64 |

## 9. Dữ liệu lớn: giới hạn kích thước, bộ nhớ và response

Một truy vấn `search` trả hàng nghìn `jpegPhoto` có thể tốn nhiều bộ nhớ dù filter nhanh. Ví dụ giả định:

- 1 ảnh: 150 KiB.
- 1.000 ảnh: khoảng 146 MiB dữ liệu ảnh gốc, chưa tính overhead kết quả, `List` và JVM.
- Nếu mã hóa Base64 để đưa tất cả vào JSON, kích thước văn bản còn tăng thêm.

Các số trên **chỉ minh họa phép nhân kích thước**, không phải benchmark cho Spring LDAP.

Nguyên tắc thiết kế:

1. **Lấy đúng attribute cần thiết:** danh sách người dùng chỉ yêu cầu `uid`/`cn`; ảnh tải bằng request riêng khi người dùng được phép xem.
2. **Giới hạn số entry:** dùng search base/scope phù hợp, filter chọn lọc và count limit theo nghiệp vụ.
3. **Kiểm tra kích thước blob:** sau khi nhận `byte[]`, từ chối dữ liệu quá lớn theo hạn mức ứng dụng. Lưu ý kiểm tra sau khi tải **không bảo vệ** khỏi chi phí truyền/tải bytes ban đầu; cần giới hạn ở directory/server, API gateway hoặc kiến trúc lưu trữ.
4. **Không nhân bản mảng không cần thiết:** defensive copy là tốt tại ranh giới sở hữu dữ liệu, nhưng sao chép nhiều lần làm tăng peak heap.
5. **Chọn loại response:** dùng binary HTTP response khi phù hợp thay vì Base64 JSON cho ảnh, nhưng vẫn cần authorization và chống cache nhạy cảm.
6. **Không giữ dữ liệu lâu hơn cần thiết:** quản lý TTL/cache theo chính sách và tránh đặt blob nhạy cảm vào log/tracing.

Ví dụ kiểm tra kích thước:

```java
private static final int MAX_PHOTO_BYTES = 2 * 1024 * 1024;

static byte[] validatePhoto(byte[] bytes) {
    if (bytes == null) {
        return null;
    }
    if (bytes.length == 0 || bytes.length > MAX_PHOTO_BYTES) {
        throw new IllegalArgumentException("Invalid photo size");
    }
    return bytes;
}
```

Ngưỡng 2 MiB ở đây là **ví dụ chính sách ứng dụng**; cần điều chỉnh theo dữ liệu và môi trường. Muốn kiểm tra ảnh JPEG hợp lệ, không chỉ dựa vào độ dài hoặc ba bytes đầu: dùng decoder/parsing library có giới hạn tài nguyên và chính sách an toàn đối với dữ liệu không tin cậy.

## 10. Bảo mật khi đọc ảnh, certificate và giá trị nhạy cảm

Không nên coi một attribute binary là vô hại chỉ vì nó không thể đọc như chữ. Một số binary attribute là định danh, chứng chỉ, khóa công khai hoặc dữ liệu xác thực; nội dung có thể nhạy cảm hoặc gây ra những yêu cầu tuân thủ riêng.

| Rủi ro | Cách giảm thiểu |
| --- | --- |
| API trả ảnh của user khác | Kiểm tra authorization theo **chủ thể/entry DN** trước khi đọc hoặc trả bytes |
| Tải binary từ LDAP không mã hóa | Dùng LDAPS/StartTLS với xác minh chứng chỉ và hostname |
| Log blob hoặc Base64 | Log loại attribute, kích thước theo nhóm hoặc mã lỗi; **không log nội dung** |
| Mã hóa Base64 bị hiểu nhầm là bảo mật | Bảo vệ transport, storage, quyền truy cập và retention riêng |
| File ảnh/certificate giả dạng | Kiểm tra định dạng thực tế trước khi render/parse |
| Blob cực lớn làm quá tải heap | Giới hạn kết quả, kích thước, request rate và tối ưu luồng tải |
| Nội dung nhị phân đi vào tracing tags | Chỉ dùng tags cardinality thấp; không thêm bytes, Base64 hoặc DN tùy tiện |
| Đọc `userPassword` như ảnh hoặc text | Tránh truy vấn/hiển thị; xử lý dữ liệu xác thực theo API và quyền chuyên biệt |

Không sử dụng `Arrays.toString(bytes)`, `Base64.encodeToString(bytes)` hoặc `HexFormat.of().formatHex(bytes)` trong logging production của dữ liệu cá nhân chỉ vì “trông dễ đọc”. Chúng đều **làm lộ nội dung** theo cách có thể khôi phục.

## 11. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `ClassCastException: String cannot be cast to byte[]` | JNDI không nhận biết custom binary attribute hoặc query chọn tên khác | Xác minh schema/provider, cấu hình `java.naming.ldap.attributes.binary` |
| `ClassCastException: byte[] cannot be cast to String` | Gọi `getStringAttribute` hoặc cast `Attribute.get()` cho dữ liệu nhị phân | Dùng `getObjectAttribute` / `byte[]` |
| Ảnh hiển thị ký tự lạ như � | Dùng `new String(bytes)` theo charset | Giữ nguyên bytes, dùng image decoder |
| Ảnh lỗi sau vòng encode/decode | Đã chuyển bytes sang String trước khi Base64 hoặc đổi charset | Base64 **trực tiếp từ bytes nguyên bản** |
| `byte[].toString()` ra `[B@...` | Đang xem mô tả mảng Java, không phải dữ liệu | Dùng parser/encoder phù hợp |
| `jpegPhoto` trả `null` | Attribute không tồn tại, chưa được yêu cầu, ACL che giấu hoặc entry sai | Kiểm tra DN, returned attributes, quyền và schema |
| Ảnh bị thay bởi ảnh khác | Attribute nhiều giá trị nhưng chỉ lấy một và dựa vào thứ tự | Đọc tất cả giá trị hoặc áp dụng quy tắc nghiệp vụ rõ ràng |
| `@Attribute(type=BINARY)` nhưng mapper riêng vẫn trả String | Annotation ODM không thay đổi mọi đường đọc JNDI | Kiểm tra tầng ODM và JNDI env riêng |
| JSON rất lớn, heap tăng | Đọc cả `jpegPhoto` cho danh sách người dùng, thêm Base64 overhead | Chia endpoint ảnh và danh sách; hạn chế result |
| Chứng chỉ parse lỗi | Bytes không phải DER/X.509 đúng định dạng | Kiểm tra name `;binary`, schema và parser |
| `objectGUID` hiển thị sai | Dùng thứ tự byte không đúng chuẩn AD | Dùng converter GUID chuyên biệt |
| Thuộc tính đọc được ở admin nhưng không đọc được ở service account | ACL/operational attribute policy khác nhau | Kiểm tra quyền và response với đúng principal |

## 12. Kiểm thử để phát hiện mất dữ liệu nhị phân

Nên kết hợp **unit test** cho mapper và **integration test** với directory thực/nhúng hỗ trợ đúng schema.

### 12.1. Unit test: bytes giữ nguyên sau ánh xạ

```java
import java.util.Arrays;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;

byte[] expected = {
    (byte) 0xFF, (byte) 0xD8, (byte) 0xFF,
    (byte) 0xE0, (byte) 0x00, (byte) 0x10
};
Attributes attrs = new BasicAttributes(true);
attrs.put("jpegPhoto", expected);

byte[] actual =
        new BinaryAttributeMapper("jpegPhoto").mapFromAttributes(attrs);

if (!Arrays.equals(expected, actual)) {
    throw new AssertionError("Binary LDAP mapping modified the bytes");
}
if (expected == actual) {
    throw new AssertionError("Expected defensive copy, got same array");
}
```

Mẫu bytes này **không phải file JPEG hợp lệ đầy đủ**; nó chỉ giúp kiểm thử **ánh xạ byte-for-byte**, không phải chức năng giải mã ảnh.

### 12.2. Unit test: xử lý thiếu và sai kiểu

```java
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;

Attributes missing = new BasicAttributes(true);
if (new BinaryAttributeMapper("jpegPhoto")
        .mapFromAttributes(missing) != null) {
    throw new AssertionError("Expected missing photo to be null");
}

Attributes wrongType = new BasicAttributes(true);
wrongType.put("jpegPhoto", "not binary");

try {
    new BinaryAttributeMapper("jpegPhoto")
            .mapFromAttributes(wrongType);
    throw new AssertionError("Expected type mismatch");
} catch (IllegalStateException expected) {
    // Cấu hình JNDI/schema sai kiểu phải được phát hiện.
}
```

Không viết mapper tự động gọi `((String) value).getBytes(...)` để cho test sai kiểu “vẫn chạy”, vì hành vi đó che giấu lỗi dữ liệu.

### 12.3. Integration test với directory

Trong directory test, thực hiện các bước:

1. **Tạo entry hợp lệ:** có DN và các thuộc tính bắt buộc theo `inetOrgPerson`; thêm `jpegPhoto` bằng bytes ảnh giả hợp lệ với schema/server.
2. **Đọc theo DN:** dùng `LdapTemplate.lookup` với returned attributes chỉ có `jpegPhoto`; xác minh `byte[]` khớp với bytes ban đầu.
3. **Đọc qua search:** tìm theo `uid` và map `jpegPhoto` bằng `AttributesMapper`, kiểm tra kết quả đúng entry.
4. **Đọc qua ContextMapper:** dùng `getObjectAttribute` và lấy DN; kiểm tra không ép kiểu thành String.
5. **Đọc qua ODM:** xác minh field `@Attribute(type=BINARY) byte[]` được ánh xạ theo schema thực tế.
6. **Thiếu ảnh/ACL:** tạo entry không có `jpegPhoto` và thử principal bị hạn chế quyền; bảo đảm code không ném NPE hoặc tiết lộ ảnh.
7. **Sai kiểu custom attribute:** thử một attribute binary tùy chỉnh chưa khai báo trong JNDI rồi thêm cấu hình `java.naming.ldap.attributes.binary`, kiểm tra kiểu object nhận được.
8. **Đa trị:** nếu schema cho phép, thêm hai giá trị nhị phân và kiểm tra code không giả định thứ tự.
9. **Dữ liệu lỗi/kích thước:** thử payload sai định dạng, rỗng, vượt ngưỡng; kiểm tra thông báo lỗi không chứa blob.
10. **So sánh vòng đọc–ghi:** nếu có quyền và yêu cầu nghiệp vụ ghi lại, dùng `Arrays.equals(original, reread)` để bảo đảm không bị biến đổi byte.

Sử dụng tài khoản test có quyền tối thiểu, LDAPS/TLS hợp lệ và dữ liệu giả; không tải hay log chứng chỉ/ảnh người thật chỉ để kiểm thử.

## 13. Tự luyện tập

**Câu 1.** Tại sao đọc `jpegPhoto` bằng `new String((byte[]) attr.get(), UTF_8)` là sai?

*Gợi ý:* JPEG là dữ liệu nhị phân, không phải văn bản UTF-8. Giải mã charset có thể làm mất bytes và không tạo ra một đối tượng ảnh.

**Câu 2.** `Attribute.get()` trả `String` cho một thuộc tính `customBlob` đã xác nhận thuộc loại binary. Nên sửa mapper bằng `getBytes()` không?

*Gợi ý:* Không. Kiểm tra cấu hình JNDI binary attribute và schema/server; không giả vờ có bytes đúng từ một String được diễn giải sai.

**Câu 3.** Một API JSON cần xuất ảnh sang web client. Khi nào Base64 phù hợp? Nó có bảo vệ nội dung không?

*Gợi ý:* Base64 phù hợp khi hợp đồng JSON cần biểu diễn bytes trong một String có thể hoàn nguyên. Nó **không phải encryption**; cần authorization và truyền tải an toàn.

**Câu 4.** Vì sao `getStringAttribute("jpegPhoto")` không phải lựa chọn đúng, còn `getObjectAttribute("jpegPhoto")` phù hợp hơn?

*Gợi ý:* Helper String giả định giá trị là `String`. Helper Object giữ được `byte[]` mà JNDI trả về.

**Câu 5.** Một repository trả 5.000 entity `Person`, mỗi entity có `jpegPhoto`. Bạn sẽ thay đổi thiết kế truy vấn như thế nào?

*Gợi ý:* Đọc danh sách chỉ với các thuộc tính cần thiết; tách truy vấn lấy ảnh theo DN, có giới hạn kích thước và quyền phù hợp.

**Câu 6.** `userCertificate;binary` trả `byte[]`. Có thể xem bytes này như chứng chỉ đáng tin cậy ngay không?

*Gợi ý:* Không. Phải parse theo X.509 và thực hiện validation trust chain/chính sách cần thiết.

**Câu 7.** Trong LDIF, `jpegPhoto:: ...` có nghĩa sau `Attribute.get()` cần `Base64.decode(...)` lần nữa không?

*Gợi ý:* Không. `::` là cú pháp biểu diễn Base64 của LDIF; JNDI thường đã trả giá trị nhị phân gốc `byte[]`.

## 14. Ghi nhớ

- **Dữ liệu nhị phân phải được xử lý như bytes**, không tự chuyển thành `String` hoặc đọc bằng `getStringAttribute`.
- **JNDI** quyết định nhiều giá trị là `String` hay `byte[]` dựa trên danh sách binary/syntax; `java.naming.ldap.attributes.binary` hỗ trợ tên binary tùy chỉnh.
- **`AttributesMapper<byte[]>`** và **`ContextMapper` với `getObjectAttribute`** giúp đọc đúng kiểu; kiểm tra null, đa trị và quyền truy cập.
- **ODM** dùng `@Attribute(type = Attribute.Type.BINARY)` cho field `byte[]`; kiểm tra riêng cấu hình JNDI khi đọc qua API khác.
- **Base64/hex là cách biểu diễn bytes**, không mã hóa bảo mật; UTF-8 chỉ dành cho dữ liệu thực sự là văn bản có charset được xác định.
- Với ảnh/chứng chỉ, cần kiểm tra định dạng, kích thước, authorization và tránh log dữ liệu nhạy cảm. **Unit test so sánh byte-for-byte** là cách trực tiếp phát hiện lỗi chuyển đổi.

**Tài liệu tham khảo:**

- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Attribute`, trường binary và type conversion.
- [Spring LDAP API — Attribute annotation](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/odm/annotations/Attribute.html): `type = Attribute.Type.BINARY`.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `lookup` với returned attributes và `AttributesMapper`/`ContextMapper`.
- [Spring LDAP API — DirContextAdapter](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextAdapter.html): `getObjectAttribute`, `getObjectAttributes`.
- [Spring LDAP API — AbstractContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): `setBaseEnvironmentProperties`.
- [Oracle JNDI LDAP Provider — Binary Attribute Handling](https://docs.oracle.com/javase/jndi/tutorial/ldap/misc/attrs.html): tên binary mặc định, `;binary` và `java.naming.ldap.attributes.binary`.
- [Oracle JNDI LDAP Provider Guidelines](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap-gl.html): các LDAP-specific environment properties.
- [RFC 2849 — LDAP Data Interchange Format](https://www.rfc-editor.org/rfc/rfc2849): biểu diễn `::` của LDIF.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): attribute syntax, schema và DIT.
