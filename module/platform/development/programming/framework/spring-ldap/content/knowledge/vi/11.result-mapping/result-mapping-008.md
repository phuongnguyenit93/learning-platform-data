# Mapping binary attribute và giá trị null

Trong **Spring LDAP**, thao tác `LdapTemplate.search(...)` hoặc `lookup(...)` thường trả entry ở dạng thuộc tính LDAP/JNDI. Một số thuộc tính là văn bản, chẳng hạn `uid`, `cn`, `mail`; những thuộc tính khác có thể mang **dữ liệu nhị phân** như `jpegPhoto` hoặc chứng chỉ X.509. Đồng thời, một thuộc tính có thể **không xuất hiện trong kết quả**, kể cả khi nó có thật trên server nhưng không được yêu cầu trong projection hoặc tài khoản LDAP thiếu quyền đọc.

Khi ánh xạ sang Java domain object, hai câu hỏi tưởng nhỏ lại có ý nghĩa lớn: **“Giá trị này có phải `byte[]` không?”** và **“`null` có thật sự đồng nghĩa thuộc tính không tồn tại?”**. Nếu xử lý thiếu cẩn thận, ứng dụng có thể làm hỏng ảnh/chứng chỉ, nhầm dữ liệu thiếu với dữ liệu rỗng, che giấu lỗi quyền truy cập hoặc trả về mảng byte có thể bị mã bên ngoài thay đổi.

Bài thuộc chương **Mapping kết quả** trong module **SPRING_LDAP**, tập trung vào `AttributesMapper`, `ContextMapper`, `DirContextOperations`, ánh xạ binary attribute, chính sách giá trị thiếu/rỗng, defensive copying, lựa chọn thuộc tính khi search và kiểm thử cùng LDAP server thật. Những nguyên tắc này cũng hữu ích khi dùng `LdapClient` hoặc LDAP ODM để đọc entry qua `ContextSource` đã cấu hình TLS, pooling và danh tính bind.

## 1. Dữ liệu mẫu: văn bản, nhiều giá trị và nhị phân

Giả sử directory có nhân viên sau:

~~~ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
mail: linh.work@example.org
~~~

Bản ghi này chưa có `jpegPhoto`. Một bản ghi nhân viên khác có thể chứa ảnh JPEG dưới dạng octet, nhưng **không nên ghi dữ liệu JPEG thật thành chuỗi văn bản thông thường** trong LDIF. Với LDIF, giá trị nhị phân thường được biểu diễn bằng **base64 sau dấu `::`**:

~~~ldif
dn: uid=mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Mai Tran
sn: Tran
jpegPhoto:: /9j/4AAQSkZJRgABAQ==
~~~

Giá trị sau `::` ở ví dụ là **đoạn base64 minh họa**, không phải một ảnh JPEG hoàn chỉnh để sử dụng trong sản phẩm. Khi nhập LDIF, LDAP server lưu dữ liệu theo **kiểu/syntax của thuộc tính**, không có nghĩa client JNDI sẽ nhận được nguyên chuỗi base64 trong LDIF.

| Thuộc tính | Dữ liệu LDAP | Giá trị Java thường thấy | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `uid` | Văn bản, một hoặc nhiều giá trị tùy schema | `String` | Quy định thuộc tính bắt buộc trong DTO |
| `cn` | Văn bản | `String` | Có thể bị thiếu trong response do projection/ACL |
| `mail` | Có thể đa trị | `String[]` hoặc danh sách | Không mặc định chọn phần tử đầu |
| `jpegPhoto` | Octet nhị phân | `byte[]` khi provider cấu hình/nhận diện đúng | Không giải mã tùy tiện sang `String` |
| `userCertificate;binary` | Chứng chỉ dạng nhị phân, tùy server và cách yêu cầu attribute | `byte[]` hoặc các giá trị nhị phân | Tên có option `;binary` cần được xét cùng provider/server |
| `objectGUID` | Nhị phân đặc thù trên một số LDAP server như Active Directory | `byte[]` | Định dạng và diễn giải là đặc thù sản phẩm |

Vì schema và JNDI provider có thể khác nhau, **không khẳng định mọi binary attribute trên mọi server luôn được trả về dưới dạng `byte[]`**. Phải kiểm tra loại đối tượng thực tế, cấu hình provider và cách yêu cầu thuộc tính.

## 2. Ba trạng thái dễ nhầm: thiếu, rỗng và có dữ liệu

Hãy phân biệt:

| Trạng thái trong đối tượng mapper | Ví dụ | Ý nghĩa có thể kết luận |
| --- | --- | --- |
| **Không có trong kết quả** | `attributes.get("jpegPhoto") == null` | Response không cung cấp thuộc tính này |
| **Có giá trị nhị phân độ dài 0** | Một `byte[]` có `length == 0`, nếu nguồn/schema cho phép | Có một payload rỗng ở tầng Java; **không giống `null`** |
| **Có payload nhị phân** | `byte[]` có `length > 0` | Có dữ liệu octet cần giải thích theo loại attribute |
| **Giá trị trả về sai kiểu** | Đọc được `String` nơi mapper kỳ vọng `byte[]` | Có vấn đề mapping, provider hoặc hợp đồng schema |
| **Thao tác LDAP thất bại** | Thiếu quyền, timeout, TLS, referral | Không thể kết luận thuộc tính có/không có từ dữ liệu chưa nhận hợp lệ |

Đặc biệt, **“không có trong kết quả” không chứng minh “không tồn tại trên LDAP server”**. Có ít nhất ba nguyên nhân: entry thực sự thiếu thuộc tính, query không yêu cầu trường đó, hoặc quyền đọc của bind account không cho phép trả thuộc tính đó. Một số server còn áp chính sách riêng khi trả thuộc tính bị hạn chế.

Với kiểu `jpegPhoto`, byte array có độ dài 0 **không phải JPEG hợp lệ**; một ứng dụng hiển thị ảnh nên coi đây là dữ liệu không hợp lệ hoặc xử lý theo chính sách cụ thể. Tùy schema, server có thể không chấp nhận giá trị octet rỗng ngay từ đầu. Dù vậy, **ở tầng mapping và test**, việc phân biệt `null` với một `byte[0]` vẫn quan trọng.

### 2.1. `null` không phải “LDAP NULL”

LDAP thông thường mô hình hóa **thuộc tính có hoặc không có giá trị được trả**, chứ không sử dụng giá trị `NULL` theo cách một cột SQL có thể mang `NULL`. Trong API Java, `null` thường là dấu hiệu mapper **không lấy được giá trị** tại thời điểm đọc.

Ví dụ:

~~~java
Object raw = entry.getObjectAttribute("jpegPhoto");

if (raw == null) {
    // Không có giá trị jpegPhoto trong kết quả mà mapper nhận.
    // Chưa kết luận được lý do.
}
~~~

Nếu nghiệp vụ cần biết **lý do** không có dữ liệu, mapper một mình thường không đủ. Cần nhìn cả requested attributes của query, quyền ACL, schema và kết quả thực tế của server. Không tự đoán rằng `raw == null` là “người dùng chưa tải ảnh” rồi lưu một trạng thái vĩnh viễn như vậy.

## 3. Đọc thuộc tính từ JNDI và Spring LDAP

Spring LDAP cung cấp hai callback ánh xạ quan trọng:

- **`AttributesMapper<T>`** nhận `javax.naming.directory.Attributes`; thích hợp khi chỉ cần đọc giá trị thuộc tính.
- **`ContextMapper<T>`** nhận đối tượng context (trong cách dùng thông thường là `DirContextOperations`), từ đó đọc thuộc tính và tên entry.

Ví dụ `ContextMapper` tối giản:

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<Object> photoMapper = context -> {
    DirContextOperations entry = (DirContextOperations) context;
    return entry.getObjectAttribute("jpegPhoto");
};
~~~

Giá trị trả về là `Object` nên **phải kiểm tra kiểu** trước khi xem đó là JPEG, chứng chỉ hoặc dữ liệu binary khác. Code phía trên chỉ minh họa API; không nên trả raw `Object` tới controller.

Tương tự, với `AttributesMapper`:

~~~java
import javax.naming.directory.Attribute;
import org.springframework.ldap.core.AttributesMapper;

AttributesMapper<Object> photoMapper = attrs -> {
    Attribute photo = attrs.get("jpegPhoto");
    return photo == null ? null : photo.get();
};
~~~

`Attribute.get()` có thể ném `NamingException`. `AttributesMapper.mapFromAttributes` được thiết kế để làm việc với ngoại lệ này, còn các giá trị thường cần được chuyển thành DTO ngay trong callback.

### 3.1. Khi nào chọn mapper nào?

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Chỉ lấy `uid` và `jpegPhoto` | `AttributesMapper` đủ dùng |
| Cần DN entry cùng với ảnh | `ContextMapper` và `DirContextOperations.getDn()` |
| Cần ánh xạ trực tiếp thành thực thể ODM | Cơ chế mapping của LDAP ODM nếu phù hợp |
| Cần API fluent để query | `LdapClient` ở phiên bản hỗ trợ, nhưng quy tắc binary/null vẫn phải xử lý |
| Cần đọc theo JNDI controls đặc thù | Xem API mức thấp/callback phù hợp, không mặc định dùng cho mọi tìm kiếm |

**Không giữ `DirContextOperations` hoặc JNDI context trong DTO.** Mapper nên tạo dữ liệu Java độc lập trước khi `LdapTemplate` hoàn tất thao tác và giải phóng context.

## 4. Xây DTO không làm lộ mảng `byte[]` có thể sửa đổi

Mảng Java là **mutable**. Nếu DTO giữ nguyên tham chiếu `byte[]` và getter trả lại cùng mảng, code bên ngoài có thể thay đổi ảnh/chứng chỉ của DTO mà không đi qua validation.

Giải pháp là **defensive copy** ở cả lúc nhận vào và lúc trả ra. Ví dụ một domain object chỉ có ảnh tùy chọn:

~~~java
import java.util.Objects;
import java.util.Optional;

public final class EmployeeAvatar {
    private final String uid;
    private final byte[] jpegPhoto; // null = không có giá trị trong kết quả.

    public EmployeeAvatar(String uid, byte[] jpegPhoto) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
        this.uid = uid;
        this.jpegPhoto = jpegPhoto == null
                ? null
                : jpegPhoto.clone();
    }

    public String uid() {
        return uid;
    }

    public Optional<byte[]> jpegPhoto() {
        return jpegPhoto == null
                ? Optional.empty()
                : Optional.of(jpegPhoto.clone());
    }

    public boolean hasPhoto() {
        return jpegPhoto != null;
    }

    public int photoSize() {
        return jpegPhoto == null ? 0 : jpegPhoto.length;
    }
}
~~~

Dùng `Optional.empty()` giúp tầng gọi biết không có giá trị trong kết quả. Phương thức `hasPhoto()` còn phân biệt được `null` với mảng độ dài 0, trong khi `photoSize()` trả `0` cho cả hai nên **không thể tự dùng kích thước để kết luận trạng thái**.

Ví dụ:

~~~java
byte[] bytes = {1, 2, 3};
EmployeeAvatar avatar = new EmployeeAvatar("linh", bytes);

bytes[0] = 99; // Không thay đổi mảng bên trong avatar.

byte[] copied = avatar.jpegPhoto().orElseThrow();
copied[1] = 88; // Cũng không thay đổi mảng bên trong avatar.
~~~

Nếu dùng Java `record` có field `byte[]`, cần **tự viết defensive copy** cho constructor và accessor; record không tự biến mảng thành bất biến. `List.copyOf(...)` với một `List<byte[]>` cũng chỉ copy cấu trúc danh sách, **không copy từng mảng byte**.

### 4.1. Không trả ảnh nhị phân trong mọi response JSON

Đối với API danh bạ, thường nên tách:

- API danh sách nhân viên: chỉ trả `uid`, `cn` và metadata ảnh cho phép.
- Endpoint ảnh chuyên biệt: trả bytes đã kiểm tra kiểu/nội dung, đặt content type phù hợp, kiểm tra authorization và chính sách cache.
- API nội bộ lấy chứng chỉ: chỉ trả dữ liệu theo nhu cầu nghiệp vụ và quyền truy cập.

Gửi hàng trăm ảnh trong một JSON có thể tăng băng thông/bộ nhớ; một số serializer còn tự chuyển `byte[]` thành base64, làm payload lớn hơn. **Base64 là cách biểu diễn dữ liệu**, không phải mã hóa bảo mật, nén hoặc thay thế TLS.

## 5. Viết `ContextMapper` cho ảnh tùy chọn

Ví dụ mapper có validation rõ ràng về loại dữ liệu, độ dài và giá trị `null`:

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

public final class EmployeeAvatarMapper
        implements ContextMapper<EmployeeAvatar> {

    private static final int MAX_PHOTO_BYTES = 1_000_000;

    @Override
    public EmployeeAvatar mapFromContext(Object context) {
        DirContextOperations entry = (DirContextOperations) context;

        String uid = entry.getStringAttribute("uid");
        if (uid == null || uid.isBlank()) {
            throw new IllegalStateException(
                    "LDAP entry thiếu uid trong kết quả mapping");
        }

        Object raw = entry.getObjectAttribute("jpegPhoto");

        if (raw == null) {
            return new EmployeeAvatar(uid, null);
        }

        if (!(raw instanceof byte[] bytes)) {
            throw new IllegalStateException(
                    "jpegPhoto không có kiểu byte[] theo cấu hình hiện tại");
        }

        if (bytes.length == 0) {
            throw new IllegalStateException(
                    "jpegPhoto rỗng, không phải nội dung JPEG hợp lệ");
        }

        if (bytes.length > MAX_PHOTO_BYTES) {
            throw new IllegalStateException("jpegPhoto vượt giới hạn ứng dụng");
        }

        return new EmployeeAvatar(uid, bytes);
    }
}
~~~

**Giới hạn 1 MB chỉ là chính sách minh họa.** Nó chặn DTO chứa payload quá lớn sau khi đọc, nhưng **không ngăn LDAP server truyền payload đó qua mạng trước khi mapper kiểm tra**. Muốn giảm tải, cần kiểm soát requested attributes, quy trình tải ảnh và chính sách server; LDAP search thông thường không có phép “cắt byte[] chỉ còn 1 MB” tự động tương đương.

Các lựa chọn thiết kế:

1. `uid` bắt buộc đối với DTO ví dụ; thiếu thì báo lỗi, không tạo `EmployeeAvatar` mơ hồ.
2. `jpegPhoto` không có trong kết quả được ánh xạ thành `null` bên trong DTO và `Optional.empty()` khi đọc.
3. `byte[0]` bị từ chối vì không phải ảnh JPEG hợp lệ theo yêu cầu nghiệp vụ.
4. Kiểu không phải `byte[]` bị từ chối thay vì tự `toString()`/`getBytes()`.
5. Mảng được sao chép ở constructor, không lưu tham chiếu mutable do mapper/JNDI cấp.

**Một giới hạn quan trọng:** đoạn mapper này **không xác minh định dạng JPEG hoàn chỉnh**. Một mảng byte bất kỳ có kích thước khác 0 vẫn có thể là ảnh lỗi hoặc payload không phải JPEG. Khi nội dung ảnh được dùng hoặc phục vụ cho người dùng, cần kiểm tra định dạng bằng thư viện xử lý ảnh phù hợp, giới hạn kích thước pixel và xử lý an toàn.

### 5.1. Không tự chuyển binary thành text

Đoạn sau làm hỏng dữ liệu khi bytes không biểu diễn chuỗi văn bản đúng charset:

~~~java
// Không dùng để chuyển ảnh/chứng chỉ thành nội dung dạng text.
String wrong = new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
~~~

Tương tự, gọi `someString.getBytes()` không phục hồi được `byte[]` gốc nếu chuỗi đã bị chuyển đổi sai trước đó. Với JPEG, dùng bytes gốc; với chứng chỉ, dùng parser chứng chỉ trên bytes; với dữ liệu **thực sự là văn bản**, chỉ giải mã khi schema/hợp đồng quy định rõ charset.

## 6. Nếu thuộc tính nhị phân có nhiều giá trị thì sao?

Không phải mọi binary attribute đều đơn trị. Một thuộc tính chứng chỉ có thể có nhiều giá trị; đọc `getObjectAttribute(...)` hoặc `Attribute.get()` một lần có thể chỉ cho **một giá trị** và làm mất dữ liệu còn lại.

Khi cần tất cả giá trị, làm việc với `Attribute.getAll()` rồi copy từng `byte[]`:

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.DirContextOperations;

public final class BinaryAttributeValues {
    private BinaryAttributeValues() {}

    public static List<byte[]> readAll(
            DirContextOperations entry, String attributeName) {

        Attribute attribute = entry.getAttributes().get(attributeName);
        if (attribute == null) {
            return List.of();
        }

        List<byte[]> values = new ArrayList<>();
        try {
            NamingEnumeration<?> items = attribute.getAll();
            try {
                while (items.hasMore()) {
                    Object raw = items.next();
                    if (!(raw instanceof byte[] bytes)) {
                        throw new IllegalStateException(
                                "Sai kiểu binary attribute: " + attributeName);
                    }
                    values.add(bytes.clone());
                }
            } finally {
                items.close();
            }
        } catch (NamingException error) {
            throw new IllegalStateException(
                    "Không thể đọc các giá trị binary attribute", error);
        }

        return List.copyOf(values);
    }
}
~~~

Lưu ý:

- Truyền `attributeName` từ **allowlist do ứng dụng kiểm soát**, không cho client tùy ý yêu cầu mọi thuộc tính LDAP nhạy cảm.
- Danh sách trả về không cho phép thay đổi cấu trúc, nhưng **các phần tử `byte[]` vẫn mutable** khi getter cho phép truy cập trực tiếp. Khi đưa `List<byte[]>` vào domain object lâu dài, nên copy ở đầu vào **và** trả bản copy khi lấy ra.
- Dữ liệu có thể đa trị nhưng **thứ tự các giá trị LDAP không nên được coi là thứ tự nghiệp vụ** nếu schema không quy định.
- `NamingEnumeration` của JNDI nên được đóng trong `finally`; `LdapTemplate` quản lý context của nó nhưng không có nghĩa callback được phép bỏ qua mọi tài nguyên phụ.

### 6.1. Thuộc tính chứng chỉ và các option

Ví dụ LDAP có thể yêu cầu `userCertificate;binary` trong danh sách thuộc tính muốn nhận, tùy schema/server/provider. Không được giả định rằng yêu cầu `userCertificate` và `userCertificate;binary` luôn có hành vi giống nhau.

Với dữ liệu thực sự là một chứng chỉ X.509 DER, một bước xử lý chuyên biệt có thể dùng:

~~~java
import java.io.ByteArrayInputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public final class CertificateParser {
    private CertificateParser() {}

    public static X509Certificate parseDer(byte[] encoded) throws Exception {
        if (encoded == null || encoded.length == 0) {
            throw new IllegalArgumentException("Thiếu dữ liệu chứng chỉ");
        }
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");
        return (X509Certificate) factory.generateCertificate(
                new ByteArrayInputStream(encoded));
    }
}
~~~

`CertificateFactory` xác minh **cú pháp và khả năng parse** của chứng chỉ, **không đồng nghĩa chứng chỉ đáng tin cậy**. Nếu dùng chứng chỉ để xác thực, cần kiểm tra trust chain, hiệu lực, mục đích sử dụng, revocation theo chính sách và danh tính người dùng. Đừng coi “parse được” là “đủ quyền truy cập”.

## 7. Cấu hình JNDI binary attributes và kiểm tra kiểu runtime

JNDI LDAP provider có thể suy đoán thuộc tính nhị phân dựa trên schema/tên thuộc tính hoặc cấu hình riêng. Trong một số tình huống, cần khai báo những tên attribute mà provider nên trả ở dạng nhị phân thông qua environment property `java.naming.ldap.attributes.binary` (đặc thù JNDI LDAP provider thuộc JDK).

Ví dụ cấu hình mang tính minh họa:

~~~java
import java.util.Map;
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://directory.example.org:636");
source.setBase("dc=example,dc=org");
source.setBaseEnvironmentProperties(Map.of(
        "java.naming.ldap.attributes.binary",
        "jpegPhoto userCertificate objectGUID"
));
// Các thiết lập bind identity, secret và TLS trust còn cần cấu hình riêng.
~~~

**Không sao chép danh sách trên một cách máy móc.** Tập attribute và cách đặt tên có option `;binary` thay đổi theo directory server, schema và JNDI provider. Một số attribute đã được provider nhận diện là binary mà không cần khai báo thêm. Hãy xác minh các attribute thật sự cần, cách server trả dữ liệu và version đang dùng.

Trong ứng dụng, nên có bước kiểm tra hoặc test tích hợp để xác nhận:

~~~java
Object value = entry.getObjectAttribute("jpegPhoto");
if (value != null && !(value instanceof byte[])) {
    throw new IllegalStateException("Binary attribute không được map thành byte[]");
}
~~~

Không dùng `String.valueOf(value)` để “chữa” một binary type mismatch. Nếu server trả `String` cho một attribute vốn cần binary, nên sửa cấu hình/attribute request và kiểm thử lại, thay vì đoán encoding của chuỗi.

Khi dùng **LDAP ODM** hoặc `LdapClient`, cần kiểm tra cơ chế chuyển đổi binary của phiên bản library; framework không thể tự biết một thuộc tính tùy biến phải được xử lý như ảnh, chứng chỉ hay mã định danh nhị phân nếu schema và mapping không quy định rõ.

## 8. Truy vấn `LdapTemplate` phải yêu cầu đúng thuộc tính

Mapper chỉ có thể đọc những giá trị mà search/lookup trả về. Với `LdapContextSource` có base `dc=example,dc=org`, một query tải ảnh riêng có thể là:

~~~java
import java.util.List;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public final class EmployeeAvatarRepository {
    private final LdapTemplate template;
    private final EmployeeAvatarMapper mapper = new EmployeeAvatarMapper();

    public EmployeeAvatarRepository(LdapTemplate template) {
        this.template = template;
    }

    public List<EmployeeAvatar> findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .countLimit(10)
                .timeLimit(2000)
                .attributes("uid", "jpegPhoto")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return template.search(query, mapper);
    }
}
~~~

**Bốn điều cần hiểu:**

1. **Base DN:** `ou=people` được hiểu tương đối với base `dc=example,dc=org` của `ContextSource`. Nếu chuyển source base tới `ou=people`, phải điều chỉnh query.
2. **Filter:** `.is(uid)` diễn đạt equality với input là giá trị, không nối chuỗi chưa escape gây LDAP injection.
3. **Projection:** `attributes("uid", "jpegPhoto")` yêu cầu đủ trường cho mapper; nếu bỏ `jpegPhoto`, mapper sẽ thấy thiếu giá trị dù entry có thể chứa ảnh.
4. **Limit/timeout:** giới hạn số entry/thời gian search được client yêu cầu. Server vẫn có giới hạn riêng; kết quả bị cắt ngắn không được coi là dữ liệu đầy đủ.

**Quan trọng với dữ liệu lớn:** Query trên có thể tải ảnh cho mọi entry phù hợp. Khi xây trang danh bạ, thường nên có **hai bước**: search metadata nhỏ để liệt kê nhân viên, rồi fetch riêng ảnh của một người dùng sau khi kiểm tra quyền. Như vậy ít chuyển binary payload không cần thiết hơn.

### 8.1. `lookup` khác `search`

Nếu đã biết DN từ một quy tắc định danh đáng tin cậy, `LdapTemplate.lookup` đọc một entry cụ thể, thay vì search nhiều entry theo filter. Ví dụ:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "linh")
        .build();

EmployeeAvatar avatar = template.lookup(relativeDn, mapper);
~~~

Trong cấu hình có base, truyền **DN tương đối** phù hợp để tránh lặp suffix. Tùy overload `lookup` và version Spring LDAP, có thể chỉ định tập thuộc tính cần trả; hãy ưu tiên projection nhỏ nếu chỉ cần ảnh.

`lookup` trả kết quả có entry hoặc phát ngoại lệ; nó không tự xác thực người dùng. Nếu DN không tồn tại, phân biệt `NameNotFoundException` với thiếu quyền, sai TLS, bind failure hoặc timeout.

## 9. Chính sách giá trị null cho domain và API

Không phải ứng dụng nào cũng muốn biểu diễn “không có ảnh” bằng `null`. Có thể chọn một mô hình dễ diễn giải hơn:

| Domain/API | Cách biểu diễn | Khi phù hợp |
| --- | --- | --- |
| `Optional<byte[]>` | Không có giá trị hoặc có dữ liệu | Service đọc tùy chọn; nhớ defensive copy |
| `byte[]` có thể null | Phân biệt qua hợp đồng rõ ràng | DTO nội bộ đơn giản, nhưng phải tránh getter mutable |
| `enum` trạng thái + payload | `NOT_RETURNED`, `PRESENT`, `INVALID` | Cần phân biệt projection/chính sách với dữ liệu |
| `List<byte[]>` | Nhiều giá trị nhị phân | Thuộc tính certificate đa trị |
| DTO metadata + URL tải ảnh | Chỉ trả tham chiếu được cấp quyền | API danh bạ và hệ thống tải file riêng |

Lưu ý: **`NOT_RETURNED` không xác định được nguyên nhân** nếu mapper chỉ nhìn entry mà không biết query. Để phân biệt “không yêu cầu” với “đã yêu cầu nhưng không được trả”, tầng repository phải cung cấp metadata về projection/cách truy vấn. Và ngay cả khi đã yêu cầu, không được tự kết luận thiếu vì ACL hay vì entry không có giá trị nếu server không cung cấp thông tin đủ để phân biệt.

Ví dụ một kiểu trạng thái chuyên biệt:

~~~java
public enum PhotoMappingStatus {
    NOT_RETURNED,   // Không có giá trị trong phản hồi; nguyên nhân chưa xác định.
    PRESENT,        // Có byte[] phù hợp chính sách.
    INVALID         // Có giá trị nhưng sai kiểu/không hợp lệ.
}
~~~

Trong ví dụ `EmployeeAvatarMapper` ở mục 5, chính sách là **fail-fast đối với ảnh rỗng hoặc sai kiểu**, thay vì đưa `INVALID` xuống API. Cả hai cách đều có thể hợp lý; quan trọng là **thống nhất hợp đồng** và không che giấu dữ liệu lỗi.

### 9.1. Null, empty và giá trị mặc định

Các cách làm dễ gây nhầm lẫn:

~~~java
// Không nên tự thay mọi thuộc tính thiếu bằng dữ liệu byte rỗng.
byte[] photo = raw == null ? new byte[0] : (byte[]) raw;

// Không nên tự biến byte[] thành String để so sánh hoặc lưu DB.
String photoText = String.valueOf(raw);
~~~

Trong dòng đầu, ứng dụng đánh mất khả năng phân biệt “không có ảnh” với “có mảng rỗng”. Dòng thứ hai tạo chuỗi mô tả đối tượng như `[B@...` chứ không phải nội dung ảnh.

Nếu hệ thống thật sự muốn một **ảnh mặc định**, nên quyết định ở tầng trình bày hoặc API trả ảnh, không ghi dữ liệu giả vào domain mapper rồi khiến người dùng hiểu rằng LDAP entry có ảnh.

## 10. Kiểm thử mapper với `DirContextAdapter`

`DirContextAdapter` có thể mô phỏng `DirContextOperations` ở mức Java, giúp test logic mapping mà không gọi LDAP server.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

class EmployeeAvatarMapperTest {
    private final EmployeeAvatarMapper mapper = new EmployeeAvatarMapper();

    private DirContextAdapter entry() {
        DirContextAdapter entry = new DirContextAdapter(
                LdapNameBuilder.newInstance("uid=linh,ou=people").build());
        entry.setAttributeValue("uid", "linh");
        return entry;
    }

    @Test
    void missingPhotoBecomesEmptyOptional() {
        EmployeeAvatar avatar = mapper.mapFromContext(entry());
        assertTrue(avatar.jpegPhoto().isEmpty());
        assertFalse(avatar.hasPhoto());
    }

    @Test
    void mapsBytesAndProtectsAgainstMutation() {
        DirContextAdapter entry = entry();
        byte[] original = {1, 2, 3};
        entry.setAttributeValue("jpegPhoto", original);

        EmployeeAvatar avatar = mapper.mapFromContext(entry);
        original[0] = 99;

        assertArrayEquals(
                new byte[] {1, 2, 3},
                avatar.jpegPhoto().orElseThrow());

        byte[] clientCopy = avatar.jpegPhoto().orElseThrow();
        clientCopy[1] = 88;

        assertArrayEquals(
                new byte[] {1, 2, 3},
                avatar.jpegPhoto().orElseThrow());
    }

    @Test
    void emptyBinaryPayloadIsRejectedByPhotoPolicy() {
        DirContextAdapter entry = entry();
        entry.setAttributeValue("jpegPhoto", new byte[0]);

        assertThrows(IllegalStateException.class,
                () -> mapper.mapFromContext(entry));
    }

    @Test
    void textInsteadOfBinaryIsRejected() {
        DirContextAdapter entry = entry();
        entry.setAttributeValue("jpegPhoto", "not really an image");

        assertThrows(IllegalStateException.class,
                () -> mapper.mapFromContext(entry));
    }

    @Test
    void requiredUidMustBeAvailable() {
        DirContextAdapter entry = new DirContextAdapter(
                LdapNameBuilder.newInstance("uid=unknown,ou=people").build());

        assertThrows(IllegalStateException.class,
                () -> mapper.mapFromContext(entry));
    }
}
~~~

Mẫu này kiểm tra sự khác nhau giữa **missing**, **zero-length**, **wrong type** và **valid binary byte[]**; đồng thời xác minh DTO không để lộ mảng mutable. Các byte `{1,2,3}` chỉ là payload phục vụ **unit test mapping**, không phải dữ liệu JPEG thật. Nếu muốn kiểm thử bước xử lý ảnh, phải bổ sung fixture JPEG hợp lệ.

Đây là test **thuần Java**. Nó không chứng minh provider JNDI thực sự trả `jpegPhoto` thành `byte[]`, schema cho phép lưu ảnh, hay server áp ACL đúng. Phải bổ sung kiểm thử tích hợp.

## 11. Test tích hợp và xử lý lỗi khi đọc binary

### 11.1. Ma trận tích hợp

Chuẩn bị LDAP server thử nghiệm, tài khoản đọc với ACL tối thiểu, base `dc=example,dc=org` và entry nhân viên thử nghiệm. Không dùng ảnh người dùng thật hoặc chứng chỉ nhạy cảm để tạo dữ liệu test.

| Ca | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| A | Query có `uid` và `jpegPhoto`, entry có ảnh hợp lệ | Mapper nhận `byte[]` và tạo DTO đúng |
| B | Entry không có `jpegPhoto` | Mapper trả trạng thái thiếu theo hợp đồng |
| C | Query chỉ trả `uid`, không yêu cầu `jpegPhoto` | Mapper cũng thấy thiếu; không kết luận entry không có ảnh |
| D | Bind account không được đọc `jpegPhoto` | Kết quả bị giới hạn theo ACL; ứng dụng không bịa lý do thiếu |
| E | JNDI trả binary attribute dưới kiểu không mong đợi | Test phát hiện type mismatch, kiểm tra provider config |
| F | Binary payload lớn hơn giới hạn ứng dụng | Mapper từ chối sau khi nhận, ghi nhận metric không nhạy cảm |
| G | Thuộc tính chứng chỉ có nhiều giá trị | Mapper đọc đủ và không dựa vào thứ tự |
| H | DN/OU sai base | Lookup/search được phân loại lỗi riêng |
| I | LDAP TLS hoặc bind account thất bại | Trả lỗi hạ tầng/xác thực, không biến thành “không có ảnh” |
| J | Search bị size/time limit hoặc referral | Không coi kết quả từng phần là toàn bộ dữ liệu |
| K | Ảnh có bytes không hợp lệ | Kiểm tra ảnh chuyên biệt phát hiện payload lỗi |
| L | Mảng bytes của DTO được dùng bởi nhiều luồng | Không có rò rỉ mutation qua API domain |

Chỉ dùng **test server** để tạo/xóa fixture hoặc thay ACL. Các thao tác phá hoại kết nối/cấu hình nhằm mô phỏng lỗi không được làm trên directory production.

### 11.2. Lỗi không được gộp thành `null`

| Tình huống | Hành vi nên có |
| --- | --- |
| `jpegPhoto` không có trong kết quả thành công | Trả `Optional.empty()` hoặc trạng thái theo hợp đồng |
| `uid` bắt buộc bị thiếu | Báo lỗi mapping; điều tra projection/schema/ACL |
| Kiểu `String` thay cho `byte[]` | Báo lỗi mapping/provider, không tự chuyển charset |
| LDAP báo `NameNotFoundException` | Phân biệt DN không tồn tại với thuộc tính thiếu |
| LDAP báo thiếu quyền | Báo lỗi authorization/ACL phù hợp |
| Server không kết nối được hoặc TLS sai | Báo lỗi hạ tầng, không giả như entry thiếu ảnh |
| Search bị cắt bởi size/time limit | Ghi nhận không đầy đủ, không dùng để kết luận phủ định |
| JPEG bytes không giải mã được | Xử lý như dữ liệu ảnh không hợp lệ, không trả ảnh hỏng công khai |

Trong Spring LDAP, `LdapTemplate` thường chuyển lỗi JNDI sang nhóm ngoại lệ truy cập LDAP của Spring. Không bắt mọi `RuntimeException` rồi trả `null`, vì điều đó xóa dấu vết khác biệt giữa **dữ liệu tùy chọn** và **truy cập thất bại**.

## 12. Bảo mật và vận hành khi xử lý ảnh/chứng chỉ

Binary attribute có thể chứa dữ liệu cá nhân hoặc thông tin phục vụ bảo mật, nên quy trình đọc cần tuân thủ:

- **Quyền tối thiểu:** tài khoản dịch vụ chỉ đọc các thuộc tính/OU cần thiết. Không cấp quyền đọc chứng chỉ, ảnh hoặc thuộc tính nhạy cảm nếu chức năng không yêu cầu.
- **TLS có xác minh:** dùng LDAPS/StartTLS theo chính sách; xác minh CA và hostname. Không dùng kênh không mã hóa chỉ để debug.
- **Không log nội dung binary:** không đưa base64 ảnh, chứng chỉ, token, password hoặc toàn bộ entry vào log, exception message và metric label.
- **Giới hạn kích thước:** tránh tải media không cần thiết; tách endpoint ảnh, hạn chế số entry và giới hạn request/bộ nhớ.
- **Defensive copy:** tránh để bộ nhớ dữ liệu ảnh/chứng chỉ bị sửa ngoài ý muốn sau mapping.
- **Kiểm tra định dạng:** byte[] đúng kiểu không chứng minh ảnh JPEG an toàn hoặc chứng chỉ đáng tin.
- **Cache phù hợp:** dữ liệu ảnh có thể bị thay đổi/thu hồi; áp quy tắc cache theo quyền và quyền riêng tư.
- **Phân biệt authentication:** lookup được một binary attribute không xác thực người gọi; quyền xem ảnh thuộc quyết định riêng của ứng dụng và LDAP server.

Pooling ở `ContextSource` giúp tái sử dụng kết nối nhưng không thay việc bảo vệ **danh tính bind** và lifecycle. Mapper không giữ `DirContextOperations` hay kết nối. Khi có referral, không tự chuyển tiếp credential đến máy chủ chưa được phép chỉ để lấy dữ liệu binary còn thiếu.

## 13. Bài tập thực hành

**Tình huống:** API danh bạ nhân viên cần hiển thị tên và một biểu tượng cho biết nhân viên có ảnh hay không. Người dùng được phép mở ảnh khi xem hồ sơ, nhưng trang danh sách có hàng trăm người và không cần tải ảnh đầy đủ.

**Yêu cầu:**

1. Tạo một query metadata chỉ trả `uid`, `cn` và thuộc tính cần thiết cho màn hình danh sách. Không tải `jpegPhoto` của toàn bộ nhân viên chỉ để dựng danh sách.
2. Thiết kế API tải ảnh cho một `uid`, kiểm tra authorization trước khi đọc binary attribute.
3. Viết `EmployeeAvatarMapper` theo mục 5, giữ `null` khác với mảng rỗng và từ chối sai kiểu.
4. Thêm unit test cho `null`, `byte[0]`, `byte[]` hợp lệ và mutation sau khi tạo DTO.
5. Dùng LDAP server test có một nhân viên có ảnh và một người không có ảnh; xác minh projection và ACL.
6. Giả lập TLS hoặc bind failure, kiểm tra service trả lỗi phụ thuộc thay vì ảnh mặc định không có giải thích.
7. Nếu có certificate attribute đa trị, mở rộng mapper để đọc tất cả giá trị và kiểm tra parser trên fixture chứng chỉ thử nghiệm.

**Kết quả mong đợi:** API không đánh đồng lỗi LDAP với “không có ảnh”, tránh tải media thừa và không làm hỏng bytes do chuyển sai kiểu. Domain object được tách khỏi JNDI và an toàn trước thay đổi mảng từ bên ngoài.

## 14. Câu hỏi tự đánh giá

**Câu 1.** `getObjectAttribute("jpegPhoto") == null` có chắc entry không có ảnh trên LDAP server không?

**Đáp án:** Không. Query có thể không yêu cầu attribute, ACL không cho trả dữ liệu hoặc entry thực sự không có giá trị. Mapper chỉ biết giá trị không xuất hiện trong kết quả đang nhận.

**Câu 2.** `byte[0]` có giống `null` không?

**Đáp án:** Không. `null` biểu thị thiếu giá trị ở tầng Java; `byte[0]` là một mảng có độ dài 0. Với `jpegPhoto`, mảng 0 byte không phải ảnh hợp lệ và thường nên bị từ chối theo chính sách.

**Câu 3.** Tại sao cần `byte[].clone()` cả ở constructor và getter?

**Đáp án:** Vì `byte[]` là mutable. Clone khi nhận tránh giữ tham chiếu có thể bị sửa; clone khi trả tránh caller sửa dữ liệu bên trong domain object.

**Câu 4.** Một binary attribute đa trị có thể được map đầy đủ bằng một lần gọi `getObjectAttribute(...)` không?

**Đáp án:** Không nên giả định. Cần dùng API đọc các giá trị, chẳng hạn `Attribute.getAll()`, và xác định cách xử lý thứ tự/kiểu của mỗi giá trị.

**Câu 5.** Có thể dùng `new String(bytes, UTF_8)` để biến chứng chỉ hay JPEG thành text và lưu lại không?

**Đáp án:** Không. Binary payload không nhất thiết là văn bản UTF-8; chuyển kiểu như vậy có thể làm mất dữ liệu. Dùng parser thích hợp hoặc giữ bytes nguyên vẹn.

**Câu 6.** `CertificateFactory.generateCertificate(...)` thành công có đủ chứng minh chứng chỉ được tin cậy không?

**Đáp án:** Không. Parse chỉ xác minh nội dung đọc được theo định dạng chứng chỉ. Xác thực còn cần trust chain và các kiểm tra theo chính sách bảo mật.

**Câu 7.** Unit test trên `DirContextAdapter` có xác nhận mọi LDAP server sẽ trả `jpegPhoto` thành `byte[]` không?

**Đáp án:** Không. Unit test kiểm tra logic Java; phải kiểm thử tích hợp cùng provider, schema, projection và ACL của server thật.

**Câu 8.** Nếu mapper gặp timeout và trả `Optional.empty()` để API tiếp tục hoạt động, điều gì sai?

**Đáp án:** Ứng dụng đã che lỗi hạ tầng thành dữ liệu thiếu, khiến caller có thể tin sai rằng nhân viên không có ảnh. Timeout cần được phân loại và xử lý riêng.

**Ghi nhớ:** **Binary mapping** phải giữ nguyên octet, kiểm tra kiểu dữ liệu, sao chép `byte[]` ở ranh giới domain và xử lý thuộc tính đa trị đúng cách. **Giá trị `null`** chỉ cho biết mapper không nhận được giá trị, không đủ để khẳng định nguyên nhân. Kết hợp projection đúng, validation, TLS, ACL, xử lý lỗi phân biệt và kiểm thử LDAP thực tế để ánh xạ kết quả an toàn.
