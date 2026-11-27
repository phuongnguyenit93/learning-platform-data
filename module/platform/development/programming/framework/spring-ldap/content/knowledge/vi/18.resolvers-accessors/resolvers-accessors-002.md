# DirContextAdapter làm nguồn property trong Spring LDAP

## 1. Vì sao cần một nguồn property từ LDAP?

Trong **Spring LDAP**, một entry LDAP là tập các **attribute** (thuộc tính thư mục) được xác định bởi một **DN** (*Distinguished Name*). Ứng dụng Java thường muốn làm việc với các property có ý nghĩa nghiệp vụ như `displayName`, `email`, `groups`, thay vì trực tiếp xử lý `Attributes` và `Attribute` của JNDI ở mọi tầng. `DirContextAdapter` giúp đọc các attribute từ entry dưới dạng những giá trị có thể ánh xạ sang property của đối tượng Java.

Ví dụ một entry trong thư mục:

```ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: an
cn: Nguyễn Văn An
sn: Nguyễn
mail: an@example.org
telephoneNumber: +84 28 1234 5678
```

Ứng dụng cần tạo ra dữ liệu tương ứng:

| Attribute LDAP | Property ứng dụng | Cách đọc từ adapter |
| --- | --- | --- |
| `uid` | `username` | `getStringAttribute("uid")` |
| `cn` | `displayName` | `getStringAttribute("cn")` |
| `mail` | `email` | `getStringAttribute("mail")` |
| `telephoneNumber` | `phone` | `getStringAttribute("telephoneNumber")` |
| `memberOf` (nếu server hỗ trợ) | `groupDns` | `getStringAttributes("memberOf")` |

Đây là cách hiểu chính xác của cụm từ **“nguồn property”** trong bài: dữ liệu attribute trên `DirContextAdapter` là đầu vào để *resolver* hoặc *accessor* chuyển thành property ở tầng ứng dụng. `DirContextAdapter` **không tự động** biến các attribute LDAP thành JavaBean property, cũng không tự đăng ký chúng vào `Environment` của Spring.

## 2. Vai trò của `DirContextAdapter` và `DirContextOperations`

`org.springframework.ldap.core.DirContextAdapter` là lớp adapter của Spring LDAP, triển khai giao diện `DirContextOperations`. Lớp này bao bọc dữ liệu entry, cung cấp thao tác thuận tiện để đọc hoặc thay đổi attribute và theo dõi những thay đổi phục vụ thao tác cập nhật thư mục.

Sơ đồ luồng đọc:

```text
LDAP server
    │ tìm kiếm / lookup entry
    ▼
LdapTemplate
    │ chuyển entry thành đối tượng context
    ▼
DirContextAdapter (DirContextOperations)
    │ getStringAttribute / getStringAttributes / getObjectAttribute
    ▼
ContextMapper / accessor / resolver
    │ quy tắc ánh xạ và kiểm tra dữ liệu
    ▼
UserProfile, DTO hoặc property ứng dụng
```

Trong mã ứng dụng, nên khai báo tham số theo **`DirContextOperations`** khi chỉ cần đọc giá trị. Dùng tên lớp **`DirContextAdapter`** khi cần chỉ rõ kiểu triển khai, tạo adapter để thử nghiệm hoặc cần chức năng đặc thù của adapter.

Những phương thức quan trọng:

| Phương thức | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| `getStringAttribute(name)` | Lấy một giá trị `String` của attribute | Với attribute nhiều giá trị, chỉ nhận một giá trị; không dùng để lấy toàn bộ nhóm |
| `getStringAttributes(name)` | Lấy mảng `String[]` | Có thể trả về `null` nếu attribute vắng mặt; không giả định thứ tự có ý nghĩa |
| `getObjectAttribute(name)` | Lấy giá trị dạng đối tượng | Dành cho dữ liệu không phù hợp với `String`, chẳng hạn dữ liệu nhị phân |
| `getObjectAttributes(name)` | Lấy các giá trị dạng đối tượng | Cần xử lý kiểu trả về theo schema và LDAP provider |
| `getDn()` | Lấy DN của entry | DN dùng để định vị entry, không tương đương một attribute thông thường |
| `setAttributeValue(name, value)` | Đặt giá trị attribute trong adapter | Chỉ sửa trạng thái adapter; muốn lưu cần thao tác cập nhật qua `LdapTemplate` |

Tên attribute thường được xử lý không phân biệt chữ hoa/chữ thường theo đặc tính LDAP, nhưng **tên property Java** (`displayName`, `email`) là do ứng dụng tự quy định. Không nên suy luận rằng `displayName` sẽ tự động tìm tới `cn` nếu chưa khai báo ánh xạ.

## 3. Ánh xạ một entry thành property của đối tượng Java

Giả sử ứng dụng Spring đã cấu hình `LdapTemplate` với `ContextSource`, base DN `dc=example,dc=org` và cơ chế bảo mật kết nối phù hợp. Ta dùng `ContextMapper` để đọc `DirContextOperations` rồi tạo đối tượng miền. Mẫu sau sử dụng Java 17 (`record`); hai kiểu `public` trong ví dụ được đặt vào hai tệp riêng (`UserProfile.java` và `UserProfileMapper.java`).

```java
import java.util.Arrays;
import java.util.List;

import org.springframework.ldap.core.DirContextOperations;

public record UserProfile(
        String username,
        String displayName,
        String email,
        List<String> groupDns) {
}

public final class UserProfileMapper {

    private UserProfileMapper() {
    }

    public static UserProfile from(DirContextOperations entry) {
        String username = entry.getStringAttribute("uid");
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("LDAP entry thiếu uid");
        }

        String[] memberOf = entry.getStringAttributes("memberOf");
        List<String> groups = memberOf == null
                ? List.of()
                : List.copyOf(Arrays.asList(memberOf));

        return new UserProfile(
                username,
                entry.getStringAttribute("cn"),
                entry.getStringAttribute("mail"),
                groups);
    }
}
```

Ở đây, `uid` được coi là bắt buộc theo **quy tắc nghiệp vụ của ví dụ**, còn `cn`, `mail`, `memberOf` có thể vắng mặt. `memberOf` là attribute thường gặp trong Active Directory và một số hệ thống khác, **không được bảo đảm tồn tại trên mọi LDAP server**. Việc tính danh sách nhóm có thể cần một truy vấn tới entry nhóm, tùy schema.

Sử dụng mapper khi tìm kiếm:

```java
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class UserDirectory {

    private final LdapTemplate ldapTemplate;

    public UserDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<UserProfile> findByUid(String uid) {
        return ldapTemplate.search(
                query().base("ou=people").where("uid").is(uid),
                (ContextMapper<UserProfile>) ctx ->
                        UserProfileMapper.from((DirContextOperations) ctx));
    }
}
```

Lệnh tìm kiếm trả về danh sách vì LDAP có thể trả về nhiều entry khớp filter. `LdapQueryBuilder` tạo filter với giá trị đầu vào được escape theo cách của Spring LDAP; tránh ghép chuỗi trực tiếp như `"(uid=" + uid + ")"`. Base `ou=people` ở ví dụ là **DN tương đối** với base đã cấu hình trong `ContextSource`.

Lợi ích của cách tổ chức này là `UserProfileMapper` không phụ thuộc vào cách tìm entry. Có thể tái sử dụng nó khi `lookup` một DN cụ thể hoặc khi tìm kiếm bằng filter khác.

## 4. Tự viết accessor để xử lý property có quy tắc riêng

Đối với các property cần chuẩn hóa, nên viết accessor rõ ràng thay vì rải `getStringAttribute(...)` trong controller, service và mapper. Ví dụ:

```java
import java.util.Locale;

import org.springframework.ldap.core.DirContextOperations;

public final class LdapPropertyAccessor {

    private final DirContextOperations entry;

    public LdapPropertyAccessor(DirContextOperations entry) {
        this.entry = entry;
    }

    public String optionalText(String attributeName) {
        String value = entry.getStringAttribute(attributeName);
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    public String normalizedEmail() {
        String mail = optionalText("mail");
        return mail == null ? null : mail.toLowerCase(Locale.ROOT);
    }
}
```

Trong hệ thống thật, chuẩn hóa email phải tuân theo chính sách dữ liệu của hệ thống; ví dụ trên minh họa cách đặt một quy tắc chuyển đổi tại một nơi. Với các attribute nhiều giá trị như `memberOf` hoặc `objectClass`, phải dùng `getStringAttributes(...)` và quy định rõ chiến lược xử lý: giữ danh sách, kiểm tra có chứa một giá trị hay chọn theo điều kiện. Không nên gọi `getStringAttribute(...)` rồi ngầm giả định chỉ có một giá trị.

Nếu cần truy cập attribute nhị phân như `jpegPhoto`, kiểm tra kiểu dữ liệu lấy qua `getObjectAttribute(...)` trước khi ép kiểu; không chuyển trực tiếp sang chuỗi bằng `toString()`:

```java
Object value = entry.getObjectAttribute("jpegPhoto");
byte[] photo = value instanceof byte[] bytes ? bytes : null;
```

## 5. Khi thực sự cần Spring `PropertySource`

Trong Spring Framework, **`PropertySource`** là cơ chế để `Environment` phân giải tên cấu hình như `directory.supportEmail`. Đây là khái niệm khác với property của `UserProfile`. Nếu muốn dùng một entry LDAP chứa **cấu hình ứng dụng** làm nguồn giá trị cho `Environment`, phải viết adapter `PropertySource` riêng và chủ động đăng ký nó.

Ví dụ giả sử một entry cấu hình có các attribute `o` và `mail`, và ứng dụng chỉ cho phép công bố hai khóa cấu hình:

```java
import java.util.Map;

import org.springframework.core.env.PropertySource;
import org.springframework.ldap.core.DirContextOperations;

public final class LdapEntryPropertySource
        extends PropertySource<DirContextOperations> {

    private static final Map<String, String> PROPERTY_TO_ATTRIBUTE = Map.of(
            "directory.organization", "o",
            "directory.supportEmail", "mail");

    public LdapEntryPropertySource(
            String name, DirContextOperations source) {
        super(name, source);
    }

    @Override
    public Object getProperty(String name) {
        String attribute = PROPERTY_TO_ATTRIBUTE.get(name);
        if (attribute == null) {
            return null;
        }
        String value = source.getStringAttribute(attribute);
        return value == null || value.isBlank() ? null : value;
    }
}
```

Sau khi đã lấy **entry cấu hình** bằng `LdapTemplate`, có thể đặt phương thức sau trong một thành phần cấu hình để đăng ký nguồn giá trị khi khởi tạo ứng dụng:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.ldap.core.DirContextOperations;

public void registerLdapConfiguration(
        ConfigurableEnvironment environment,
        DirContextOperations configurationEntry) {
    environment.getPropertySources().addLast(
            new LdapEntryPropertySource("ldapConfig", configurationEntry));
}
```

Khi đó `environment.getProperty("directory.supportEmail")` có thể trả về `mail` từ entry cấu hình. `addLast` đặt nguồn này sau các nguồn có độ ưu tiên cao hơn; cách sắp xếp phải phù hợp chính sách cấu hình. Nếu giá trị không tồn tại hoặc chưa được phép ánh xạ, `getProperty(...)` trả `null`, cho phép resolver xét nguồn khác.

**Giới hạn quan trọng:** Chỉ dùng ví dụ này với entry cấu hình có vòng đời phù hợp với ứng dụng. Không đưa dữ liệu của từng người dùng vào `Environment` dùng chung toàn ứng dụng: dữ liệu có thể bị truy cập chéo giữa các request. `DirContextAdapter` là ảnh dữ liệu entry tại thời điểm đọc; khi entry trên server thay đổi, property source không tự làm mới. Nếu cần refresh, thiết kế cơ chế tải lại và thay nguồn dữ liệu có kiểm soát.

## 6. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `getStringAttribute("mail")` trả `null` | Entry không có `mail`, không đủ quyền đọc, hoặc search chỉ yêu cầu một số attribute | Xác minh schema, ACL và danh sách attribute yêu cầu trong truy vấn |
| Danh sách nhóm bị thiếu | Dùng phương thức lấy một giá trị hoặc server không cung cấp `memberOf` | Đọc đa trị, kiểm tra schema, hoặc tìm membership từ các entry nhóm |
| `ClassCastException` khi đọc ảnh | Attribute nhị phân bị giả định là `String` | Dùng accessor dạng object và kiểm tra kiểu |
| Giá trị trên server không đổi sau `setAttributeValue(...)` | Thay đổi mới nằm trong adapter | Gọi thao tác cập nhật phù hợp của `LdapTemplate` với quyền ghi hợp lệ |
| Property trong `Environment` không được phân giải | Chưa đăng ký `PropertySource`, khóa không nằm trong whitelist hoặc nguồn bị nguồn khác che | Kiểm tra đăng ký, key ánh xạ và thứ tự `PropertySources` |
| Tên DN bị lặp base hoặc tìm sai entry | Trộn DN đầy đủ với DN tương đối trong `ContextSource` | Thống nhất quy ước base DN; tạo DN bằng `LdapNameBuilder` khi cần |

Trong bài toán thật, cần thêm các nguyên tắc sau:

- **Tôn trọng schema và dữ liệu thiếu:** Không mặc định entry nào cũng có `mail`, `telephoneNumber` hay `memberOf`; chỉ coi là bắt buộc khi đã có ràng buộc nghiệp vụ và kiểm tra rõ ràng.
- **Giữ nguyên ngữ nghĩa đa trị:** Không phụ thuộc vào thứ tự của attribute LDAP nếu schema không quy định thứ tự; chuẩn hóa hoặc sắp xếp ở tầng ứng dụng khi cần hiển thị ổn định.
- **Hạn chế dữ liệu nhạy cảm:** Không đưa `userPassword`, token hoặc attribute nội bộ vào `PropertySource`, DTO công khai hay log. Giới hạn thuộc tính được đọc theo nhu cầu và cấu hình kết nối LDAP an toàn bằng TLS/LDAPS.
- **Phân biệt lỗi kết nối với thiếu dữ liệu:** Lỗi xác thực, quyền hoặc kết nối phải được xử lý riêng; không biến tất cả lỗi thành `null` vì có thể che giấu sự cố thư mục.

## 7. Thử nhanh mapper mà không cần LDAP server

`DirContextAdapter` có thể tạo trực tiếp trong kiểm thử của mapper để xác minh quy tắc ánh xạ. Việc này kiểm tra logic đọc property, không thay thế kiểm thử tích hợp với schema và server thực tế.

```java
import org.springframework.ldap.core.DirContextAdapter;

DirContextAdapter entry = new DirContextAdapter();
entry.setAttributeValue("uid", "an");
entry.setAttributeValue("cn", "Nguyễn Văn An");
entry.setAttributeValue("mail", "an@example.org");
entry.setAttributeValues("memberOf", new String[] {
        "cn=engineering,ou=groups,dc=example,dc=org",
        "cn=staff,ou=groups,dc=example,dc=org"
});

UserProfile profile = UserProfileMapper.from(entry);

assert "an".equals(profile.username());
assert "Nguyễn Văn An".equals(profile.displayName());
assert profile.groupDns().size() == 2;
```

Trong môi trường kiểm thử tự động, nên dùng assertion của JUnit thay cho `assert` của Java vì Java assertion có thể bị tắt khi không bật `-ea`. Tối thiểu cần kiểm tra các trường hợp thiếu `uid`, không có `mail`, không có `memberOf` và attribute nhiều giá trị.

## 8. Ghi nhớ

Trong chủ đề **Resolver và accessor**, `DirContextAdapter` đóng vai trò nguồn dữ liệu entry LDAP, còn lớp mapper/accessor quyết định cách biến attribute thành property. `getStringAttribute(...)` phù hợp với giá trị đơn; `getStringAttributes(...)` dùng cho đa trị; `getObjectAttribute(...)` dành cho giá trị dạng đối tượng. Việc ánh xạ phải phản ánh schema, đặc điểm thiếu dữ liệu và yêu cầu bảo mật.

Khi cần đưa dữ liệu LDAP vào hệ thống cấu hình Spring, triển khai `PropertySource` riêng với danh sách khóa cho phép và phạm vi vòng đời phù hợp. Hai trường hợp dùng chung dữ liệu từ adapter nhưng phục vụ mục đích khác nhau: **property của đối tượng nghiệp vụ** và **property cấu hình ứng dụng**.
