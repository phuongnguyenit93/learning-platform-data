# Attribute binary và xử lý dữ liệu byte

Khi đọc một entry LDAP bằng Spring LDAP, bạn thường thấy những thuộc tính như `cn`, `mail` hay `uid` được biểu diễn bằng chuỗi. Nhưng một số thuộc tính lưu **dữ liệu byte**, ví dụ ảnh JPEG, chứng chỉ X.509 hoặc mã định danh nhị phân. Nếu coi mọi giá trị LDAP đều là `String`, ứng dụng có thể làm hỏng dữ liệu, lưu sai kiểu hoặc gặp lỗi ép kiểu khi dùng `LdapTemplate`.

Bài học thuộc chương **Attribute và schema** trong **SPRING_LDAP**. Nội dung tập trung vào ý nghĩa của thuộc tính binary trong LDAP, cách Java/JNDI biểu diễn giá trị, cách đọc và cập nhật bằng Spring LDAP, cùng các lưu ý về schema, LDIF, bảo mật và kiểm thử.

Sau bài này, bạn sẽ có thể:

- Phân biệt **thuộc tính có dữ liệu dạng byte**, **cú pháp thuộc tính trong schema** và tùy chọn truyền `;binary`.
- Hiểu khi nào JNDI trả về `byte[]` và vì sao không nên tự chuyển byte tùy ý thành `String`.
- Đọc và cập nhật ảnh `jpegPhoto` qua `LdapTemplate`, có kiểm tra kiểu dữ liệu, kích thước và quyền truy cập.
- Nhận biết cú pháp Base64 trong LDIF và chuyển đổi dữ liệu byte an toàn khi tích hợp API.
- Xử lý các lỗi thường gặp khi kết nối đến OpenLDAP hoặc Active Directory.

## 1. Thuộc tính LDAP có phải lúc nào cũng là chuỗi?

Một **entry** chứa các thuộc tính (`attributes`). Mỗi thuộc tính có **một hoặc nhiều giá trị**; **schema** quy định kiểu cú pháp (`syntax`), quy tắc so sánh (`matching rules`), phạm vi và số lượng giá trị được phép.

Ở tầng giao thức LDAP, giá trị được mang dưới dạng **chuỗi octet** (dãy byte). Tuy nhiên, **không phải mọi dãy byte đều mang nghĩa là tệp hoặc blob**. Nhiều cú pháp quy định giá trị là chuỗi ký tự, số, DN hoặc thời gian; những cú pháp khác mang dữ liệu nhị phân cần trình xử lý phù hợp.

Ví dụ:

| Thuộc tính | Dữ liệu thường gặp | Cách ứng dụng thường xử lý |
| --- | --- | --- |
| `cn` | Tên người/nhóm, ví dụ `Lan Nguyen` | Giá trị văn bản. |
| `mail` | `lan@example.org` | Giá trị văn bản. |
| `jpegPhoto` | Nội dung ảnh JPEG | `byte[]`, có thể giải mã thành ảnh. |
| `userCertificate;binary` | Chứng chỉ X.509 dạng mã hóa nhị phân (thường là DER) | `byte[]`, có thể phân tích bằng thư viện chứng chỉ. |
| `objectGUID` (Active Directory) | GUID lưu dưới dạng 16 byte | `byte[]`; quy tắc biểu diễn GUID phụ thuộc AD. |

**Điểm dễ nhầm:** `objectGUID` là thuộc tính đặc thù của Active Directory, không phải thuộc tính bắt buộc có trong mọi máy chủ LDAP. Tương tự, tên thuộc tính và khả năng ghi `jpegPhoto` phụ thuộc schema, cấu hình và quyền trên server.

### Ba lớp khác nhau của “binary”

1. **Dữ liệu thực tế:** một ảnh JPEG là byte; không thể đọc bằng `new String(bytes)` mà vẫn giữ nguyên ý nghĩa.
2. **LDAP schema:** định nghĩa attribute type, cú pháp, matching rule, khả năng đa trị và những lớp đối tượng nào được phép chứa thuộc tính.
3. **Cách mã hóa khi truyền/hiển thị:** giao thức LDAP truyền giá trị dưới dạng octet; JNDI quyết định chuyển sang kiểu Java nào, còn LDIF có thể dùng Base64 để biểu diễn dãy byte dưới dạng văn bản.

Ba lớp trên có liên quan nhưng **không đồng nhất**. Cần kiểm tra schema của thư mục và phản hồi thực tế từ provider thay vì suy đoán kiểu dữ liệu dựa duy nhất vào tên thuộc tính.

## 2. Phân biệt `;binary` với giá trị kiểu binary

Theo LDAP, một **attribute description** có thể gồm tên thuộc tính và các option, ví dụ:

```text
jpegPhoto
userCertificate;binary
```

Tùy chọn `;binary` được định nghĩa để chỉ định cách truyền giá trị theo **binary transfer option** (tham khảo [RFC 4522](https://www.rfc-editor.org/rfc/rfc4522)). Nó **không phải** một “kiểu dữ liệu Java”, cũng không có nghĩa thêm `;binary` vào bất kỳ thuộc tính văn bản nào sẽ biến thuộc tính đó thành ảnh hay chứng chỉ.

Hãy phân biệt:

- `jpegPhoto`: thuộc tính có cú pháp được thiết kế cho ảnh JPEG; khi đọc thường cần `byte[]`. Không phải cứ thấy dữ liệu byte là phải thêm hậu tố `;binary`.
- `userCertificate;binary`: cách sử dụng tùy chọn truyền binary đặc biệt quan trọng với chứng chỉ theo schema PKIX; hỗ trợ và yêu cầu cụ thể phải theo server, schema và API LDAP đang dùng.
- `objectGUID`: thuộc tính riêng của Active Directory; thường đọc ra các byte của GUID. Không thể lấy cách lưu GUID này áp dụng chung cho mọi attribute.

**Không có quy tắc “mọi giá trị byte đều phải đặt tên thuộc tính kèm `;binary`”.** Cũng không nên tự ý đổi tên attribute trong một phép ghi chỉ để khắc phục lỗi kiểu dữ liệu; cần xác nhận attribute description hợp lệ trên server.

Một DN có thể dùng `uid=lan,ou=people,dc=example,dc=org` để định vị entry, trong khi thuộc tính ảnh của entry mang tên `jpegPhoto`. **DN xác định vị trí entry**; tên thuộc tính xác định phần dữ liệu cần đọc hoặc sửa. Hai việc này độc lập.

## 3. JNDI biểu diễn byte trong Java như thế nào?

Spring LDAP sử dụng JNDI dưới lớp truy cập thư mục. Các API phổ biến:

| Kiểu/API | Mục đích |
| --- | --- |
| `javax.naming.directory.Attributes` | Tập thuộc tính của một entry. |
| `javax.naming.directory.Attribute` | Một thuộc tính và các giá trị của nó. |
| `Attribute.get()` | Lấy một giá trị (kiểu `Object`) của thuộc tính. |
| `Attribute.getAll()` | Duyệt các giá trị nếu thuộc tính đa trị. |
| `byte[]` | Biểu diễn byte thô khi provider cung cấp dữ liệu nhị phân. |

Do `Attribute.get()` trả về `Object`, ứng dụng nên **kiểm tra kiểu thực tế** trước khi ép kiểu:

```java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public static byte[] readJpegPhoto(Attributes attributes) throws Exception {
    Attribute photo = attributes.get("jpegPhoto");
    if (photo == null) {
        return null; // Entry không có ảnh.
    }

    Object value = photo.get();
    if (!(value instanceof byte[])) {
        throw new IllegalStateException(
            "jpegPhoto không được JNDI trả về dưới dạng byte[]: " +
            (value == null ? "null" : value.getClass().getName())
        );
    }

    return ((byte[]) value).clone();
}
```

Ví dụ xử lý một giá trị ảnh. Nếu thuộc tính được cấu hình **đa trị**, cần xem xét các giá trị bằng `getAll()` và áp dụng quy tắc nghiệp vụ phù hợp; không được mặc định mọi attribute chỉ chứa một giá trị.

### Vì sao đôi khi JNDI trả về `String`?

Kiểu trả về phụ thuộc LDAP provider, loại attribute và danh sách attribute được nhận diện là nhị phân. JNDI LDAP provider hỗ trợ thuộc tính môi trường:

```properties
java.naming.ldap.attributes.binary=jpegPhoto objectGUID
```

Giá trị là danh sách **tên thuộc tính phân cách bằng khoảng trắng** mà provider cần coi là nhị phân. Cấu hình này hữu ích nhất khi server trả thuộc tính đặc thù, chẳng hạn `objectGUID`, mà provider chưa tự nhận diện. Không thể thay thế việc kiểm tra schema bằng cách đánh dấu bừa tất cả các attribute là binary.

Khi tạo `LdapContextSource` thủ công, có thể bổ sung môi trường cho JNDI:

```java
import java.util.HashMap;
import java.util.Map;
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://ldap.example.org:636");
source.setBase("dc=example,dc=org");
source.setUserDn("uid=svc-reader,ou=service,dc=example,dc=org");
source.setPassword(bindPassword); // Lấy từ nguồn bí mật của ứng dụng.

Map<String, Object> env = new HashMap<>();
env.put(
    "java.naming.ldap.attributes.binary",
    "jpegPhoto objectGUID"
);
source.setBaseEnvironmentProperties(env);

// Khi quản lý bean bằng Spring, vòng đời bean sẽ gọi afterPropertiesSet().
```

Nếu ứng dụng đã dùng cấu hình tự động của Spring Boot, hãy áp dụng tùy chọn môi trường theo cơ chế cấu hình `ContextSource` thực tế của ứng dụng, tránh khai báo thêm bean khiến cấu hình kết nối hiện có bị thay thế. Việc đặt thuộc tính JNDI này chỉ điều khiển **phản ánh kiểu dữ liệu phía client**, không sửa schema của server.

## 4. Đọc thuộc tính byte bằng `LdapTemplate`

Giả sử:

- LDAP server dùng TLS tại `ldaps://ldap.example.org:636`.
- `ContextSource` có base `dc=example,dc=org`.
- Entry cần tra cứu có DN đầy đủ `uid=lan,ou=people,dc=example,dc=org`.
- Bean `ldapTemplate` đã được cấu hình và inject; tài khoản bind có quyền đọc `jpegPhoto`.

Dựng tên tương đối bằng `LdapNameBuilder`, rồi dùng `lookup`:

```java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

// Trong một service đã có field hoặc constructor-injected ldapTemplate:
Name relativeDn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", "lan")
    .build();

byte[] photo = ldapTemplate.lookup(
    relativeDn,
    (AttributesMapper<byte[]>) attrs -> {
        Attribute attribute = attrs.get("jpegPhoto");
        if (attribute == null) {
            return null;
        }

        Object raw = attribute.get();
        if (!(raw instanceof byte[])) {
            throw new IllegalStateException(
                "Giá trị jpegPhoto phải là byte[]"
            );
        }
        return ((byte[]) raw).clone();
    }
);

if (photo == null) {
    // Entry tồn tại, nhưng không có jpegPhoto.
} else {
    // Kiểm tra kích thước/định dạng trước khi sử dụng.
}
```

**Cần phân biệt ba kết quả:**

1. **Entry tồn tại và có ảnh:** trả về `byte[]` chứa dữ liệu ảnh.
2. **Entry tồn tại nhưng thiếu ảnh:** ví dụ trên trả về `null`; bạn có thể thay bằng `Optional` trong lớp service.
3. **Entry không tồn tại hoặc bị từ chối:** thao tác LDAP có thể ném ngoại lệ do Spring chuyển đổi từ lỗi LDAP/JNDI; không nên tự động diễn giải mọi ngoại lệ thành “không có ảnh”.

DN gửi đến `lookup` là **tương đối** khi `ContextSource` đã thiết lập base. Nếu tự ghép thêm `dc=example,dc=org` vào tên tương đối, ứng dụng có thể truy cập sai DN.

Ngoài `LdapTemplate`, các đường truy cập khác như `LdapClient` hoặc LDAP ODM vẫn phải tôn trọng **cùng schema và kiểu giá trị**. Nếu dùng ODM ánh xạ sang một trường `byte[]`, hãy xác minh bộ chuyển đổi và quy tắc mapping thực tế trước khi đưa vào sử dụng.

## 5. Cập nhật dữ liệu binary cho entry đã tồn tại

Có thể dùng `ModificationItem` và `BasicAttribute` của JNDI cùng `LdapTemplate.modifyAttributes` để thay thế ảnh.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.support.LdapNameBuilder;

// Trong một service đã có ldapTemplate:
byte[] jpeg = Files.readAllBytes(Path.of("avatar.jpg"));

final int maxPhotoBytes = 256 * 1024; // Giới hạn ví dụ.
if (jpeg.length == 0 || jpeg.length > maxPhotoBytes) {
    throw new IllegalArgumentException("Kích thước ảnh không hợp lệ");
}

Name relativeDn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", "lan")
    .build();

ModificationItem replacement = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute("jpegPhoto", jpeg)
);

ldapTemplate.modifyAttributes(
    relativeDn,
    new ModificationItem[] { replacement }
);
```

Trong ví dụ này:

- `Files.readAllBytes(...)` đọc **byte ảnh gốc**, không qua `String`.
- `BasicAttribute("jpegPhoto", jpeg)` đặt giá trị `byte[]` cho thuộc tính.
- `DirContext.REPLACE_ATTRIBUTE` thay nội dung thuộc tính hiện có (hoặc thêm nó nếu chưa có, tùy điều kiện cập nhật và server).
- `ldapTemplate.modifyAttributes(...)` gửi yêu cầu đến server. Server xác thực schema, giới hạn kích thước, quyền ghi và các ràng buộc khác.

Đoạn code nhằm minh họa cập nhật attribute, chưa phải pipeline upload ảnh đầy đủ. Với dữ liệu từ người dùng, cần xác minh đó thật sự là JPEG trước khi lưu, đặt giới hạn dung lượng, xử lý quota, kiểm soát quyền cập nhật entry và quản lý lỗi. Không dùng một DN do người dùng tùy ý cung cấp để cập nhật ảnh ở bất kỳ entry nào.

**Lưu ý:** Nếu attribute có thể chứa nhiều giá trị, thao tác `REPLACE_ATTRIBUTE` bằng một giá trị sẽ **thay thế tập giá trị hiện tại**. Hãy cân nhắc `ADD_ATTRIBUTE`, `REMOVE_ATTRIBUTE` hoặc quy trình cập nhật theo schema và yêu cầu nghiệp vụ. Ảnh `jpegPhoto` thường được ứng dụng dùng như một giá trị đơn, nhưng khả năng đa trị phải theo schema của server.

## 6. Byte, Base64, văn bản và LDIF: bốn khái niệm khác nhau

### Base64 là cách **biểu diễn** byte thành văn bản

Nhiều REST API, cấu hình hoặc hệ thống xuất dữ liệu cần một chuỗi có thể in ra. Base64 chuyển byte sang chuỗi ký tự ASCII; khi giải mã Base64, ta khôi phục được **đúng dãy byte ban đầu**.

```java
import java.util.Arrays;
import java.util.Base64;

byte[] original = new byte[] { 0, 1, 2, (byte) 255 };

String encoded = Base64.getEncoder().encodeToString(original);
// AAEC/w==

byte[] decoded = Base64.getDecoder().decode(encoded);
System.out.println(Arrays.equals(original, decoded)); // true
```

**Base64 không phải mã hóa bảo mật**, cũng không làm dữ liệu trở thành kiểu văn bản. Đừng đưa Base64 vào `BasicAttribute("jpegPhoto", ...)` nếu server mong dữ liệu ảnh thô; khi đó server sẽ nhận **byte của chuỗi Base64** hoặc giá trị không đúng cú pháp thay vì ảnh JPEG.

Để tránh nhầm giữa các cách truyền:

| Đầu vào | Giá trị Java | Giá trị gửi vào `jpegPhoto` |
| --- | --- | --- |
| File ảnh JPEG | `byte[]` từ `Files.readAllBytes` | Dùng trực tiếp `byte[]` sau khi kiểm tra. |
| JSON có trường ảnh Base64 | `String` Base64 | Giải mã `Base64.getDecoder().decode(...)` thành `byte[]`. |
| Chuỗi đường dẫn file | `"avatar.jpg"` | Đọc file để lấy byte; không gửi tên file. |
| Nội dung văn bản `"hello"` | `String` | Không hợp lệ để thay cho ảnh JPEG nếu schema yêu cầu ảnh. |

### LDIF dùng một hoặc hai dấu hai chấm

[LDIF theo RFC 2849](https://www.rfc-editor.org/rfc/rfc2849) mô tả dữ liệu LDAP dưới dạng văn bản:

- `attribute: value`: giá trị được viết trực tiếp theo cú pháp LDIF.
- `attribute:: base64-value`: giá trị được biểu diễn bằng **Base64** trong file LDIF.

Ví dụ, **cùng một chuỗi văn bản** có thể biểu diễn dưới hai dạng:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
description:: SGVsbG8sIExEQVAh
```

Dòng `description:: SGVsbG8sIExEQVAh` biểu diễn giá trị `description` là **`Hello, LDAP!`**. Vì vậy, dấu `::` trong LDIF chỉ nói rằng giá trị trong **file này được mã hóa Base64**, **không khẳng định** schema của `description` là binary.

Đối với ảnh JPEG, dạng LDIF dùng `jpegPhoto::` rồi đến Base64 của **byte JPEG thực**. Khi chuyển đổi file lớn, công cụ xuất LDIF có thể xuống dòng và thụt đầu dòng theo quy tắc folding của LDIF. Không nên tự ghép/loại bỏ khoảng trắng tùy tiện trong nội dung Base64.

Ví dụ tạo Base64 từ byte thực bằng Java:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;

byte[] jpegBytes = Files.readAllBytes(Path.of("avatar.jpg"));
String jpegBase64 = Base64.getEncoder().encodeToString(jpegBytes);

System.out.println("jpegPhoto:: " + jpegBase64);
// Dòng in ra minh họa giá trị; để tạo file LDIF thực tế
// còn cần dn, cấu trúc entry hoặc changetype và quy tắc gấp dòng.
```

Đừng nhầm `;binary` trong **attribute description** với `::` trong **file LDIF**: chúng thuộc hai lớp cú pháp khác nhau.

## 7. Tích hợp chứng chỉ và GUID nhị phân

### Chứng chỉ X.509

Chứng chỉ lưu trong LDAP có thể được trả về dạng byte theo attribute `userCertificate;binary`, tùy server và cơ chế truy xuất. **DER** là cách mã hóa nhị phân thông dụng của chứng chỉ; `PEM` thường là chứng chỉ DER được bọc Base64 trong phần văn bản có header/footer.

Nếu đã nhận đúng `byte[]` chứa chứng chỉ X.509, Java có thể phân tích:

```java
import java.io.ByteArrayInputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public static X509Certificate parseDerCertificate(byte[] derBytes)
        throws Exception {
    CertificateFactory factory = CertificateFactory.getInstance("X.509");
    return (X509Certificate) factory.generateCertificate(
        new ByteArrayInputStream(derBytes)
    );
}
```

**Phân tích được chứng chỉ không đồng nghĩa đã tin cậy nó.** Nếu dùng chứng chỉ để xác thực danh tính hoặc quyết định bảo mật, ứng dụng phải có chính sách trust, kiểm tra chuỗi chứng chỉ, thời hạn, mục đích sử dụng và những yêu cầu liên quan. Thuộc tính chứng chỉ trong directory cũng **khác** với việc cấu hình TLS để bảo vệ kênh kết nối LDAP.

### `objectGUID` trong Active Directory

Active Directory thường trả thuộc tính `objectGUID` dưới dạng 16 byte. Đừng dùng `new String(guidBytes)` để hiển thị GUID: đây không phải chuỗi UTF-8. Để hiển thị GUID theo định dạng quen thuộc, cần áp dụng **quy tắc thứ tự byte do Active Directory quy định** (một số nhóm byte không theo cùng thứ tự với cách in hex thẳng). Tương tự, khi tra cứu bằng filter theo `objectGUID`, phải tạo filter ở dạng byte/escape đúng quy tắc LDAP thay vì đưa chuỗi UUID hiển thị vào tùy ý.

Đây là trường hợp đặc thù; các nhà cung cấp LDAP khác có thể không có attribute này.

## 8. Bảo vệ dữ liệu byte trong ứng dụng

Binary attribute có thể tiêu thụ nhiều tài nguyên hơn các thuộc tính văn bản và có thể chứa nội dung nhạy cảm. Khi dùng Spring LDAP trong một dịch vụ, nên thực hiện các kiểm soát theo **mối nguy thực tế**:

| Rủi ro | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Dữ liệu quá lớn | Tốn RAM/độ trễ, lỗi hạn mức server. | Giới hạn byte trước khi gửi, cấu hình giới hạn API và server. |
| File giả mạo kiểu | Tệp `.jpg` nhưng chứa dữ liệu không phải JPEG. | Kiểm tra chữ ký định dạng và giải mã bằng thư viện ảnh khi cần; không tin phần mở rộng file. |
| Dữ liệu nhị phân nhạy cảm | Chứng chỉ, thông tin liên quan danh tính được log. | Không log toàn bộ byte hoặc Base64; ghi log kích thước và định danh tối thiểu. |
| Truy cập sai entry | DN được dựng từ đầu vào không được kiểm soát. | Ràng buộc nhánh cho phép, kiểm tra quyền và dựng DN/filter bằng API chuyên dụng. |
| Kênh truyền không bảo vệ | Byte hoặc thông tin đăng nhập đi qua kết nối không mã hóa. | Dùng LDAPS/StartTLS với kiểm tra chứng chỉ server và cấu hình xác thực phù hợp. |
| Thay thế sai tập giá trị | `REPLACE_ATTRIBUTE` làm mất các giá trị khác. | Kiểm tra schema và chọn thao tác sửa phù hợp. |

Với ảnh hoặc file cung cấp qua REST API, hãy cân nhắc không đưa Base64 dung lượng lớn vào JSON nếu có cách truyền tệp phù hợp hơn. Khi bắt buộc dùng Base64, áp dụng giới hạn kích thước **trước và sau giải mã**, tránh tạo bản sao byte không cần thiết và xử lý lỗi Base64 không hợp lệ.

### Xử lý ngoại lệ với ngữ cảnh chính xác

Spring LDAP chuyển nhiều lỗi JNDI/LDAP thành hệ thống ngoại lệ riêng của Spring. Một số tình huống thực tế:

- **Sai schema hoặc không được phép cập nhật `jpegPhoto`:** kiểm tra `objectClass` của entry, định nghĩa attribute và quyền ghi.
- **Không tồn tại DN:** phân biệt base của `ContextSource` với DN tương đối.
- **Đọc về `String` thay vì `byte[]`:** xem lại đặc tả attribute, binary attribute handling của JNDI và thuộc tính môi trường `java.naming.ldap.attributes.binary`.
- **Dữ liệu ảnh không mở được:** xác minh byte ban đầu có thực sự là JPEG và có bị mã hóa/giải mã Base64 sai bước hay không.
- **Server từ chối kích thước:** kiểm tra hạn mức ở máy chủ, ở ứng dụng, ở reverse proxy hoặc API gateway.

Không trả ra phản hồi HTTP toàn bộ thông điệp LDAP thô khi thông điệp có thể chứa DN nội bộ hoặc thông tin nhạy cảm. Phần lỗi công khai nên có mã lỗi nghiệp vụ rõ ràng; chi tiết kỹ thuật đưa vào log theo chính sách bảo mật.

## 9. Kiểm thử việc đọc/ghi binary

Một kiểm thử tích hợp với LDAP test server có **schema và quyền tương tự môi trường thật** giúp tránh lỗi do sự khác nhau giữa provider hoặc server. Bài kiểm thử nên xác minh:

1. **Đọc đúng byte:** lưu một mẫu JPEG nhỏ và so sánh các byte đọc lại với byte ban đầu bằng `Arrays.equals(expected, actual)`.
2. **Không có ảnh:** entry tồn tại nhưng thiếu `jpegPhoto` phải được xử lý đúng, không nhầm với lỗi entry không tồn tại.
3. **Thay thế:** cập nhật ảnh mới, đọc lại và xác nhận byte cũ đã được thay; kiểm tra tác dụng của `REPLACE_ATTRIBUTE` nếu thuộc tính có nhiều giá trị.
4. **Kiểu dữ liệu:** xác nhận provider trả `byte[]` và cấu hình binary attributes được áp dụng đúng.
5. **Quyền/giới hạn:** tài khoản chỉ có quyền đọc không được phép thay ảnh; ảnh vượt mức phải bị từ chối ở lớp ứng dụng.
6. **Chứng chỉ hoặc GUID:** nếu ứng dụng hỗ trợ, kiểm tra dữ liệu sau khi chuyển đổi sang đối tượng ứng dụng và ngược lại.

Ví dụ so sánh dữ liệu binary:

```java
import java.util.Arrays;

public static void assertSamePhoto(byte[] expected, byte[] actual) {
    if (!Arrays.equals(expected, actual)) {
        throw new AssertionError("Byte ảnh không khớp");
    }
}
```

Không dùng `expected.toString()` hoặc `expected.equals(actual)` để so sánh nội dung mảng `byte[]`: hai cách này không so sánh từng byte của mảng. Khi cần kiểm tra mã hóa Base64, hãy so sánh **byte sau khi giải mã** với dữ liệu gốc.

## 10. Tình huống thực hành và lời giải

Một dịch vụ hồ sơ nhân viên dùng Spring LDAP. Mỗi nhân viên có DN dạng `uid=<mã>,ou=people,dc=example,dc=org`. Người dùng cập nhật ảnh đại diện bằng cách tải lên file `photo.jpg`. `ContextSource` đặt base `dc=example,dc=org`.

**Câu hỏi 1.** Nên ghi gì vào `jpegPhoto`: đường dẫn `photo.jpg`, chuỗi Base64 của ảnh hay byte JPEG?

**Trả lời:** Ghi **byte JPEG thực** dưới dạng `byte[]` cho API cập nhật attribute; Base64 chỉ dùng khi giao tiếp qua lớp yêu cầu biểu diễn văn bản, chẳng hạn LDIF hoặc JSON.

**Câu hỏi 2.** Tên tương đối để `LdapTemplate` sửa ảnh của người dùng có `uid=lan` là gì?

**Trả lời:** `uid=lan,ou=people`. Hậu tố `dc=example,dc=org` đã nằm trong base của `ContextSource`; nên dựng `Name` bằng `LdapNameBuilder`.

**Câu hỏi 3.** Vì sao `description:: SGVsbG8sIExEQVAh` trong LDIF không có nghĩa `description` là thuộc tính binary?

**Trả lời:** `::` báo rằng **file LDIF** đang mã hóa giá trị bằng Base64. Schema của `description` vẫn có thể yêu cầu cú pháp văn bản; Base64 không sửa schema.

**Câu hỏi 4.** Sau `lookup`, `attrs.get("jpegPhoto").get()` trả `String` và code ép kiểu bị lỗi. Nên xử lý thế nào?

**Trả lời:** Không chuyển String tùy tiện thành byte ảnh. Kiểm tra schema của `jpegPhoto`, provider JNDI, giá trị trả về và cấu hình `java.naming.ldap.attributes.binary` nếu cần; xác minh lại với LDAP server trước khi xử lý tiếp.

**Câu hỏi 5.** Có thể kiểm tra ảnh sau khi đọc về bằng `firstBytes.toString().equals(secondBytes.toString())` không?

**Trả lời:** Không. Dùng `Arrays.equals(firstBytes, secondBytes)` để so sánh nội dung, và dùng bộ giải mã JPEG nếu cần kiểm tra ảnh hợp lệ.

## 11. Ghi nhớ

**LDAP truyền các giá trị dưới dạng octet, nhưng schema mới quyết định ý nghĩa của chúng.** Trong Spring LDAP, dữ liệu như `jpegPhoto` cần được xử lý bằng byte; `;binary` là một tùy chọn truyền có quy tắc riêng, còn `::` trong LDIF chỉ đánh dấu biểu diễn Base64 của giá trị. Khi đọc và cập nhật, hãy dùng `LdapTemplate` với `Attributes`/`ModificationItem`, xác nhận kiểu `byte[]` và giới hạn kích thước, đồng thời để schema và quyền của máy chủ quyết định thao tác có hợp lệ hay không.

Tài liệu nền để tra cứu khi cần: [RFC 4512 – LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512), [RFC 4517 – LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517), [RFC 4522 – LDAP Binary Encoding Option](https://www.rfc-editor.org/rfc/rfc4522), [RFC 4523 – LDAP Schema Definitions for X.509 Certificates](https://www.rfc-editor.org/rfc/rfc4523) và [RFC 2849 – LDIF](https://www.rfc-editor.org/rfc/rfc2849).
