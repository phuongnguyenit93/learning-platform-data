# Kiểm thử resolver khi attribute thiếu hoặc sai kiểu trong Spring LDAP

Khi ứng dụng dùng Spring LDAP để đọc hồ sơ người dùng, dữ liệu trả về không phải lúc nào cũng có đủ các thuộc tính như mô hình Java mong đợi. Một entry có thể không có `description`, tài khoản bind có thể không được đọc `mail`, hoặc một thuộc tính nhị phân như `jpegPhoto` được trả về dưới dạng `byte[]` trong khi mã lại ép thành `String`. Những sai lệch này dễ dẫn đến `NullPointerException`, `ClassCastException` hoặc đối tượng nghiệp vụ thiếu thông tin nhưng vẫn được coi là hợp lệ.

Trong chương **Resolver và accessor**, *accessor* là cách truy cập giá trị LDAP, ví dụ `Attributes.get(...)` của JNDI hoặc `DirContextAdapter.getStringAttribute(...)` của Spring LDAP. *Resolver* là lớp quy tắc của **ứng dụng**: quyết định thuộc tính nào bắt buộc, thuộc tính nào tùy chọn, chấp nhận kiểu dữ liệu gì và chuyển chúng sang đối tượng Java ra sao. Spring LDAP cung cấp các API như `AttributesMapper`, `ContextMapper` và `DirContextOperations`; tên `PersonAttributeResolver` trong bài là **lớp tự xây dựng**, không phải một resolver có sẵn của Spring LDAP.

Mục tiêu của bài là xây dựng phép kiểm thử đủ chặt để phân biệt **thuộc tính thiếu**, **thuộc tính rỗng**, **sai kiểu**, **sai số lượng giá trị**, đồng thời giữ những trường hợp tùy chọn hoạt động an toàn.

## 1. Vì sao phải kiểm thử những trường hợp này?

Giả sử một tài khoản LDAP có dữ liệu:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
cn: An Nguyen
sn: Nguyen
uid: an
mail: an.work@example.org
mail: an.personal@example.org
description: Ky su phan mem
~~~

Ứng dụng muốn xây dựng một `DirectoryPerson` gồm `uid`, `cn`, `description` và tập email. Trong môi trường thực tế, những tình huống sau đều có thể gặp:

| Dữ liệu nhận được | Ví dụ | Nguy cơ nếu resolver thiếu kiểm tra |
| --- | --- | --- |
| Thiếu thuộc tính bắt buộc theo nghiệp vụ | Không có `uid` trong phản hồi | Trả đối tượng không có định danh; lỗi phát sinh ở tầng khác |
| Thiếu thuộc tính tùy chọn | Không có `description` | Gọi `get()` trên `null`, gây lỗi không cần thiết |
| Có thuộc tính nhưng không có giá trị | `new BasicAttribute("cn")` trong dữ liệu thử | Đọc phần tử đầu tiên thất bại; nhầm lẫn với giá trị rỗng |
| Sai kiểu | `cn` trả về `byte[]` thay vì `String` | `ClassCastException` hoặc dữ liệu sai sau chuyển kiểu |
| Trường đơn trị bị trả nhiều giá trị | `uid={an,an2}` | Lấy `get(0)` và vô tình chọn một giá trị không xác định |
| Trường đa trị có một giá trị sai kiểu | `mail={String,byte[]}` | Lỗi xảy ra giữa vòng lặp, dễ bỏ sót khi chỉ kiểm tra giá trị đầu |
| Thuộc tính không được yêu cầu/không có quyền đọc | Lookup chỉ yêu cầu `cn`, hoặc ACL ẩn `mail` | Kết luận nhầm rằng thuộc tính không tồn tại trong thư mục |

Một nguyên tắc quan trọng: **“không được trả về” không luôn đồng nghĩa “không tồn tại trong LDAP”**. Giá trị có thể bị loại bởi danh sách thuộc tính được yêu cầu, quyền đọc ACL, cơ chế trả thuộc tính vận hành, hoặc giới hạn của server. Unit test kiểm tra logic của resolver; integration test cần xác minh cả cấu hình truy vấn và hành vi server.

## 2. Xác định hợp đồng trước khi viết resolver

Trong ví dụ của bài, ứng dụng áp dụng quy ước:

| Thuộc tính | Kiểu mong đợi | Số giá trị | Khi thiếu | Khi sai kiểu/không hợp lệ |
| --- | --- | --- | --- | --- |
| `uid` | `String` | Chính xác 1 | Báo lỗi dữ liệu | Báo lỗi dữ liệu |
| `cn` | `String` | Chính xác 1 | Báo lỗi dữ liệu | Báo lỗi dữ liệu |
| `description` | `String` | 0 hoặc 1 | Trả `null` | Báo lỗi dữ liệu |
| `mail` | `String` | 0 hoặc nhiều | Trả tập rỗng | Báo lỗi nếu có giá trị sai kiểu/rỗng |

`uid` là **bắt buộc theo nghiệp vụ của ứng dụng mẫu**, không phải khẳng định mọi entry `inetOrgPerson` đều bắt buộc có `uid` theo schema. Tương tự, quy tắc coi `description` là đơn trị do mô hình này lựa chọn; schema LDAP thực tế có thể cho phép thuộc tính đó chứa nhiều giá trị. Phải chọn hợp đồng dựa trên **schema, yêu cầu nghiệp vụ và dữ liệu thực tế**, rồi viết test để bảo vệ hợp đồng đó.

Khi một trường tùy chọn thiếu, giá trị mặc định cần có ý nghĩa. Ví dụ tập email rỗng có thể hợp lý cho màn hình hiển thị, nhưng **không thích hợp** để kết luận người dùng chắc chắn không có email nếu tài khoản bind không được đọc thuộc tính.

## 3. Hiểu hành vi của accessor JNDI và Spring LDAP

### 3.1. Dùng `AttributesMapper` và JNDI `Attributes`

~~~java
Attributes attributes = /* dữ liệu trả về từ LDAP */;
Attribute cn = attributes.get("cn");

if (cn != null && cn.size() > 0) {
    Object raw = cn.get(0); // Có thể ném NamingException
    // Kiểm tra kiểu raw trước khi ép thành String.
}
~~~

`attributes.get("cn")` có thể trả `null`, còn `cn.get(0)` trả `Object`. Vì vậy, cách viết:

~~~java
String cn = (String) attributes.get("cn").get();
~~~

có ít nhất ba điểm dễ lỗi: thuộc tính không có, thuộc tính không có giá trị và giá trị không phải `String`. Trong JNDI, `Attribute` có thể chứa nhiều giá trị; lấy phần tử đầu tiên cũng không xác nhận trường thực sự đơn trị.

### 3.2. Dùng `ContextMapper` và `DirContextAdapter`

Spring LDAP hỗ trợ accessor tiện lợi trên `DirContextAdapter`/`DirContextOperations`:

~~~java
String one = context.getStringAttribute("cn");
String[] many = context.getStringAttributes("mail");
Object binaryOrOther = context.getObjectAttribute("jpegPhoto");
boolean hasMail = context.attributeExists("mail");
~~~

Theo API `DirContextAdapter`:

- `getStringAttribute("cn")` trả **giá trị đầu tiên** nếu có nhiều giá trị, và trả `null` nếu thuộc tính vắng hoặc không có giá trị.
- `getStringAttributes("mail")` trả `null` nếu thuộc tính không tồn tại, hoặc một mảng (có thể rỗng) nếu tồn tại.
- `getObjectAttribute(...)` trả giá trị dạng `Object`, thích hợp khi cần đọc thuộc tính nhị phân và kiểm tra kiểu.
- `attributeExists(...)` kiểm tra sự hiện diện trong **tập thuộc tính đã được nạp vào adapter**, không xác nhận được vì sao một thuộc tính vắng mặt.

Accessor giúp mã gọn hơn nhưng **không thay thế việc xác định kiểu và số lượng giá trị** nếu nghiệp vụ cần hợp đồng nghiêm ngặt. Đặc biệt, không dùng `getStringAttribute` để khẳng định một thuộc tính đa trị chỉ có một giá trị.

## 4. Viết resolver có chính sách rõ ràng

Ví dụ sau là lớp **thuần Java** nhận `javax.naming.directory.Attributes`; nó có thể được truyền trực tiếp cho Spring LDAP qua `AttributesMapper`. Lớp không truy cập server nên có thể kiểm thử nhanh với `BasicAttributes`.

~~~java
import java.util.HashSet;
import java.util.Set;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public final class PersonAttributeResolver {

    public record DirectoryPerson(
        String uid,
        String cn,
        String description,
        Set<String> mail
    ) {}

    public DirectoryPerson resolve(Attributes attributes)
            throws NamingException {
        if (attributes == null) {
            throw new IllegalArgumentException("LDAP Attributes không được null");
        }

        String uid = requiredString(attributes, "uid");
        String cn = requiredString(attributes, "cn");
        String description = optionalString(attributes, "description");
        Set<String> mail = optionalStrings(attributes, "mail");

        return new DirectoryPerson(uid, cn, description, mail);
    }

    private static String requiredString(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null) {
            throw invalid(name, "thiếu thuộc tính bắt buộc");
        }
        return singleString(attribute, name);
    }

    private static String optionalString(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null ? null : singleString(attribute, name);
    }

    private static String singleString(Attribute attribute, String name)
            throws NamingException {
        if (attribute.size() != 1) {
            throw invalid(name, "phải có chính xác một giá trị");
        }

        Object raw = attribute.get(0);
        if (!(raw instanceof String)) {
            throw invalid(name, "giá trị phải là String");
        }

        String value = (String) raw;
        if (value.isBlank()) {
            throw invalid(name, "giá trị không được rỗng");
        }
        return value;
    }

    private static Set<String> optionalStrings(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null) {
            return Set.of();
        }
        if (attribute.size() == 0) {
            throw invalid(name, "thuộc tính có mặt nhưng không chứa giá trị");
        }

        Set<String> values = new HashSet<>();
        for (int i = 0; i < attribute.size(); i++) {
            Object raw = attribute.get(i);
            if (!(raw instanceof String)) {
                throw invalid(name, "giá trị thứ " + i + " không phải String");
            }
            String value = (String) raw;
            if (value.isBlank()) {
                throw invalid(name, "giá trị thứ " + i + " bị rỗng");
            }
            values.add(value);
        }
        return Set.copyOf(values);
    }

    private static IllegalStateException invalid(String name, String reason) {
        // Báo tên thuộc tính và lý do; không ghi nội dung giá trị nhạy cảm.
        return new IllegalStateException(
            "Dữ liệu LDAP không hợp lệ ở " + name + ": " + reason
        );
    }
}
~~~

Thiết kế này có một số đặc điểm cần kiểm thử:

1. Thuộc tính **bắt buộc** không có sẽ phát sinh lỗi ngay ở ranh giới ánh xạ.
2. Thuộc tính **tùy chọn** không có được chuyển thành `null` hoặc `Set.of()` đúng như hợp đồng.
3. Thuộc tính có tên nhưng không có giá trị được phân biệt với thuộc tính hoàn toàn vắng mặt.
4. Resolver kiểm tra **từng giá trị** của thuộc tính đa trị, kể cả giá trị thứ hai hoặc thứ ba.
5. Email được biểu diễn bằng `Set` vì LDAP không bảo đảm thứ tự các giá trị trong thuộc tính đa trị. Việc so sánh test cũng dựa trên tập, không dựa vào vị trí phần tử.
6. Khi có giá trị sai kiểu, resolver phát sinh lỗi có ngữ cảnh thay vì để `ClassCastException` xuất hiện ở tầng nghiệp vụ xa hơn.

Trong hệ thống thật, có thể dùng ngoại lệ miền riêng như `InvalidDirectoryEntryException` thay cho `IllegalStateException`, gắn thông tin DN và tên nguồn LDAP (đã được xử lý bảo mật) để hỗ trợ chẩn đoán. Không đưa dữ liệu nhạy cảm vào thông điệp lỗi công khai.

## 5. Unit test với BasicAttributes, không cần LDAP server

`BasicAttributes` và `BasicAttribute` trong JNDI giúp dựng dữ liệu giả ở mức **raw LDAP attributes**. Nhờ vậy, có thể thử cả trường hợp sai kiểu mà một LDAP server có schema nghiêm ngặt thường từ chối lưu trữ.

Ví dụ JUnit 5 dưới đây kiểm thử trực tiếp `PersonAttributeResolver`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Set;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.junit.jupiter.api.Test;

class PersonAttributeResolverTest {

    private final PersonAttributeResolver resolver =
        new PersonAttributeResolver();

    private static Attributes attrs(Attribute... attributes) {
        // true: so tên thuộc tính không phân biệt chữ hoa/chữ thường.
        BasicAttributes result = new BasicAttributes(true);
        for (Attribute attribute : attributes) {
            result.put(attribute);
        }
        return result;
    }

    private static Attributes minimal() {
        return attrs(
            new BasicAttribute("uid", "an"),
            new BasicAttribute("cn", "An Nguyen")
        );
    }

    @Test
    void mapsValidSingleAndMultiValuedAttributes() throws NamingException {
        Attribute emails = new BasicAttribute("mail");
        emails.add("an.work@example.org");
        emails.add("an.personal@example.org");

        Attributes input = attrs(
            new BasicAttribute("uid", "an"),
            new BasicAttribute("cn", "An Nguyen"),
            new BasicAttribute("description", "Engineer"),
            emails
        );

        var person = resolver.resolve(input);

        assertAll(
            () -> assertEquals("an", person.uid()),
            () -> assertEquals("An Nguyen", person.cn()),
            () -> assertEquals("Engineer", person.description()),
            () -> assertEquals(
                Set.of("an.work@example.org", "an.personal@example.org"),
                person.mail()
            )
        );
    }

    @Test
    void missingOptionalAttributesUseDocumentedDefaults()
            throws NamingException {
        var person = resolver.resolve(minimal());

        assertNull(person.description());
        assertEquals(Set.of(), person.mail());
    }

    @Test
    void missingRequiredUidIsRejected() {
        Attributes input = attrs(new BasicAttribute("cn", "An Nguyen"));

        IllegalStateException error = assertThrows(
            IllegalStateException.class, () -> resolver.resolve(input)
        );
        assertTrue(error.getMessage().contains("uid"));
    }

    @Test
    void presentButEmptyCnIsRejected() {
        Attributes input = attrs(
            new BasicAttribute("uid", "an"),
            new BasicAttribute("cn") // Attribute có 0 giá trị.
        );

        assertThrows(IllegalStateException.class,
            () -> resolver.resolve(input));
    }

    @Test
    void blankCnIsNotAcceptedAsValidData() {
        Attributes input = attrs(
            new BasicAttribute("uid", "an"),
            new BasicAttribute("cn", "   ")
        );

        assertThrows(IllegalStateException.class,
            () -> resolver.resolve(input));
    }

    @Test
    void binaryDataInStringFieldIsRejected() {
        Attributes input = attrs(
            new BasicAttribute("uid", "an"),
            new BasicAttribute("cn", new byte[] {1, 2, 3})
        );

        assertThrows(IllegalStateException.class,
            () -> resolver.resolve(input));
    }

    @Test
    void multiValuedUidIsRejectedInsteadOfTakingFirst() {
        Attribute uids = new BasicAttribute("uid");
        uids.add("an");
        uids.add("an2");
        Attributes input = attrs(
            uids,
            new BasicAttribute("cn", "An Nguyen")
        );

        assertThrows(IllegalStateException.class,
            () -> resolver.resolve(input));
    }

    @Test
    void invalidSecondEmailValueIsDetected() {
        Attribute emails = new BasicAttribute("mail");
        emails.add("an.work@example.org");
        emails.add(new byte[] {0x01, 0x02});
        Attributes input = attrs(
            new BasicAttribute("uid", "an"),
            new BasicAttribute("cn", "An Nguyen"),
            emails
        );

        assertThrows(IllegalStateException.class,
            () -> resolver.resolve(input));
    }

    @Test
    void attributePresentWithoutMailValuesIsRejected() {
        Attributes input = attrs(
            new BasicAttribute("uid", "an"),
            new BasicAttribute("cn", "An Nguyen"),
            new BasicAttribute("mail")
        );

        assertThrows(IllegalStateException.class,
            () -> resolver.resolve(input));
    }

    @Test
    void ignoresCaseOfLdapAttributeIdsInTestData()
            throws NamingException {
        Attributes input = attrs(
            new BasicAttribute("UID", "an"),
            new BasicAttribute("CN", "An Nguyen")
        );

        assertEquals("an", resolver.resolve(input).uid());
    }
}
~~~

Các test trên kiểm tra **hợp đồng quan sát được**: đúng dữ liệu, áp dụng default, và từ chối dữ liệu sai. Test dùng `BasicAttributes(true)` để mô phỏng cách định danh thuộc tính LDAP không phân biệt chữ hoa/thường. Vì `BasicAttribute` là một object JNDI trong bộ nhớ, nó cho phép dựng trạng thái bất thường; điều này hữu ích để kiểm tra độ bền của mã, nhưng **không chứng minh rằng server LDAP thực tế sẽ trả đúng kiểu dữ liệu giả lập đó**.

### Ma trận test tối thiểu

| Ca | `uid` | `cn` | `mail` | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| Hợp lệ | String | String | 2 String | Map thành công |
| Thiếu tùy chọn | String | String | Không có | `mail = Set.of()` |
| Thiếu bắt buộc | Không có | String | Không có | Lỗi nêu rõ `uid` |
| Có mặt nhưng rỗng | String | Không giá trị | Không có | Lỗi `cn` |
| Chuỗi trắng | String | `"  "` | Không có | Lỗi `cn` |
| Sai kiểu bắt buộc | String | `byte[]` | Không có | Lỗi kiểu `cn` |
| Trường đơn trị có 2 giá trị | 2 String | String | Không có | Lỗi số lượng `uid` |
| Sai kiểu ở phần tử thứ hai | String | String | String + `byte[]` | Lỗi kiểu `mail` |
| `mail` có mặt nhưng rỗng | String | String | 0 giá trị | Lỗi dữ liệu theo hợp đồng |

## 6. Kiểm thử accessor DirContextAdapter độc lập

Nếu ứng dụng triển khai `ContextMapper`, hãy kiểm thử trực tiếp accessor trên `DirContextAdapter` để xác nhận các giá trị `null` trước khi áp dụng default.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import javax.naming.ldap.LdapName;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;

class DirContextAdapterAccessorTest {

    @Test
    void missingAttributeReturnsNullAndExistsFalse() throws Exception {
        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put(new BasicAttribute("cn", "An Nguyen"));

        DirContextAdapter adapter = new DirContextAdapter(
            attrs, new LdapName("uid=an,ou=people")
        );

        assertNull(adapter.getStringAttribute("description"));
        assertNull(adapter.getStringAttributes("mail"));
        assertFalse(adapter.attributeExists("mail"));
        assertEquals("An Nguyen", adapter.getStringAttribute("cn"));
    }

    @Test
    void binaryValueMustBeReadAsObject() throws Exception {
        BasicAttributes attrs = new BasicAttributes(true);
        byte[] image = new byte[] {1, 2, 3};
        attrs.put(new BasicAttribute("jpegPhoto", image));

        DirContextAdapter adapter = new DirContextAdapter(
            attrs, new LdapName("uid=an,ou=people")
        );

        Object value = adapter.getObjectAttribute("jpegPhoto");
        assertInstanceOf(byte[].class, value);
        assertArrayEquals(image, (byte[]) value);
    }
}
~~~

Để kiểm tra thêm một thuộc tính đa trị, tạo `BasicAttribute("mail")`, thêm hai email, truyền vào adapter rồi so sánh `Set.of(adapter.getStringAttributes("mail"))` với tập kỳ vọng (cần đảm bảo mảng không `null`). Không kiểm tra vị trí đầu/ cuối của email: **LDAP không bảo đảm thứ tự các giá trị đa trị**.

Nếu dùng `getStringAttribute("mail")` cho thuộc tính nhiều giá trị, chỉ có **một giá trị đầu tiên** được đọc ra. Unit test nên khiến việc dùng sai accessor đó bị phát hiện, ví dụ khẳng định mã nghiệp vụ yêu cầu đủ cả hai email.

## 7. Kết nối resolver với LdapTemplate

Sau khi unit test logic resolver đạt, tích hợp resolver với quá trình search/lookup của Spring LDAP:

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class PersonDirectoryReader {

    private final LdapTemplate ldapTemplate;
    private final PersonAttributeResolver resolver =
        new PersonAttributeResolver();

    public PersonDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonAttributeResolver.DirectoryPerson> findPeople() {
        return ldapTemplate.search(
            "ou=people",
            "(objectClass=inetOrgPerson)",
            SearchControls.SUBTREE_SCOPE,
            new String[] {"uid", "cn", "description", "mail"},
            (AttributesMapper<PersonAttributeResolver.DirectoryPerson>)
                resolver::resolve
        );
    }
}
~~~

Ví dụ giả định `ContextSource` đặt base DN `dc=example,dc=org`, nên `"ou=people"` là search base tương đối. Hãy yêu cầu đầy đủ các thuộc tính cần ánh xạ; nếu bỏ `uid` khỏi `returningAttributes`, resolver sẽ thấy `uid` thiếu **ngay cả khi server có lưu thuộc tính đó**.

Khi mapper phát hiện dữ liệu không hợp lệ, yêu cầu search có thể thất bại thay vì trả danh sách thiếu một vài người. Đây là lựa chọn có chủ ý của chế độ **strict mapping**. Nếu giao diện cần hiển thị cả entry tốt lẫn entry lỗi, cần thiết kế API riêng ghi nhận **entry nào lỗi, loại lỗi và tính đầy đủ**; không đơn giản nuốt mọi exception rồi trả `List` như thể đã thành công.

### Phân biệt lỗi mapper với lỗi LDAP

| Lỗi / tình huống | Thuộc lớp nào | Hành vi nên xác nhận |
| --- | --- | --- |
| Thiếu `uid` trong `Attributes` | Resolver/hợp đồng dữ liệu | Phát hiện lỗi trong unit test, có ngữ cảnh thuộc tính |
| `cn` là `byte[]` | Resolver/kiểu dữ liệu | Phát hiện trước khi tạo đối tượng không hợp lệ |
| Entry DN không tồn tại khi lookup | LDAP/JNDI | Xử lý `NameNotFoundException`; không giả làm thuộc tính thiếu |
| Thiếu quyền đọc `mail` | ACL và tầng LDAP | Xác nhận quyền với test tích hợp; không kết luận mail trống |
| `PartialResultException`, size/time limit | Tìm kiếm/giới hạn | Không công bố dữ liệu đã map là kết quả hoàn chỉnh |
| Lỗi TLS/kết nối | Hạ tầng | Không chuyển thành default `null`/`Set.of()` |

## 8. Kiểm thử tích hợp có ý nghĩa

Unit test dùng `BasicAttributes` chứng minh resolver xử lý dữ liệu đầu vào đúng quy tắc. Integration test cần chứng minh **ứng dụng truy xuất đúng dữ liệu LDAP thật**:

1. **Seed entry thử nghiệm** với `uid`, `cn`, `sn` hợp lệ, một entry có `description`, một entry không có `description`, một entry có nhiều `mail`.
2. **Dùng đúng cấu hình `ContextSource`** (base DN, TLS, bind identity, search scope) và gọi `PersonDirectoryReader.findPeople()`.
3. **Kiểm tra dữ liệu hợp lệ**: số lượng entry, định danh đúng, giá trị optional và tập `mail` đầy đủ; đừng so thứ tự các email.
4. **Thử hạn chế thuộc tính trả về**: bỏ `uid` khỏi `returningAttributes` trên truy vấn thử để thấy strict resolver báo thiếu.
5. **Thử quyền ACL khác nhau**: cùng một entry nhưng bind account chỉ có quyền đọc một phần; xác nhận mapper báo/ghi nhận dữ liệu thiếu thay vì kết luận thuộc tính không tồn tại.
6. **Thử dữ liệu thực tế khác nhau**: schema, attribute subtype/options, giá trị nhị phân, attribute vận hành, multi-value và định dạng được server chuẩn hóa.

**Giới hạn của unit test:** `BasicAttributes` không áp schema, ACL, referral, TLS, conversion rule hoặc quy tắc phân trang như máy chủ LDAP. Do đó không nên sử dụng test trong bộ nhớ để khẳng định `jpegPhoto` luôn là `byte[]` trên mọi provider hay thuộc tính `cn` sai kiểu có thể được ghi vào server.

Đối với Active Directory, một số thuộc tính nhiều giá trị lớn có thể được trả theo dạng **ranged retrieval**. Resolver chỉ có thể kiểm tra các giá trị **đã được trả về**. Muốn kiểm chứng toàn bộ tập, cần có logic truy xuất bổ sung, ví dụ cơ chế incremental retrieval của Spring LDAP, rồi mới áp chính sách so sánh tập giá trị.

## 9. Những sai lầm cần tránh

| Cách viết dễ sai | Vì sao có vấn đề | Cách thay thế |
| --- | --- | --- |
| `(String) attrs.get("cn").get()` | NPE khi thiếu, lỗi khi rỗng/sai kiểu | Kiểm tra `null`, `size()`, `instanceof` |
| `String.valueOf(attrs.get("cn").get())` | Có thể biến `byte[]` thành chuỗi dạng `[B@...` thay vì báo lỗi | Kiểm tra kiểu, chuyển đổi có chủ đích |
| `getStringAttribute("mail")` cho email đa trị | Chỉ nhận một giá trị; mất email khác | `getStringAttributes` hoặc duyệt `Attribute` |
| `catch (Exception e) { return null; }` | Che lỗi dữ liệu, quyền và kết nối | Phân loại lỗi, áp default chỉ với optional thật sự |
| Thiếu `mail` thì kết luận user không có email | ACL/returning attributes có thể ẩn `mail` | Xác nhận điều kiện đọc và hợp đồng nguồn |
| So sánh các email theo thứ tự trong mảng | LDAP không bảo đảm thứ tự tập giá trị | So sánh `Set` |
| Chỉ thử dữ liệu hợp lệ | Không bao phủ lỗi khi schema/provider thay đổi | Ma trận missing, empty, wrong type, cardinality |
| Ghi log toàn bộ raw `Attributes` khi test lỗi | Có thể lộ dữ liệu cá nhân hoặc thông tin nhạy cảm | Ghi tên trường, loại lỗi, DN được bảo vệ và correlation ID |

Nếu cần xử lý kiểu dữ liệu khác `String`, chẳng hạn `jpegPhoto` (`byte[]`) hoặc một thuộc tính chứa DN của thành viên nhóm, hãy viết **resolver chuyên biệt** và test đúng cấu trúc dữ liệu đó. Không ép mọi `Object` sang chuỗi rồi hy vọng dữ liệu có cùng ý nghĩa. Với ODM, `@Attribute` và Spring `ConversionService` có thể hỗ trợ chuyển đổi; các converter tùy chỉnh cũng cần được kiểm thử với giá trị thiếu, sai kiểu và lỗi chuyển đổi.

## 10. Bài tập vận dụng

Giả sử `PersonAttributeResolver` nhận bốn bộ `Attributes` độc lập:

**A.** Có `uid="an"`, `cn="An Nguyen"`, không có `description`, không có `mail`.

**B.** Có `uid="an"`, `cn` là `byte[]{1,2}`, `mail` là một `String`.

**C.** Có `uid="an"`, `cn="An Nguyen"`, `mail` gồm `"a@example.org"` và `byte[]{3}`.

**D.** Có `uid` hai giá trị `"an"`, `"an2"`, `cn="An Nguyen"`.

Hãy tự trả lời trước khi xem đáp án:

1. Bộ nào map thành công? Giá trị `description` và `mail` khi đó là gì?
2. Bộ nào bị từ chối vì **sai kiểu**? Trường nào phải được báo lỗi?
3. Bộ nào bị từ chối vì **sai số lượng giá trị**?
4. Nếu `mail` không có trong kết quả truy vấn, cần biết gì trước khi xác nhận người dùng thực sự không có email?
5. Nếu một phần tử `mail` là `byte[]`, có nên dùng `String.valueOf(...)` để bỏ qua lỗi không?

**Đáp án gợi ý:** A map thành công với `description=null` và `mail=Set.of()`. B lỗi kiểu của `cn`. C lỗi kiểu phần tử trong `mail`. D lỗi số lượng giá trị `uid`. Khi `mail` vắng mặt, cần kiểm tra danh sách thuộc tính đã yêu cầu, ACL, server và policy trả dữ liệu; không nên dùng `String.valueOf` để che lỗi kiểu.

## 11. Ghi nhớ

- Resolver là nơi biến **dữ liệu LDAP thô** thành đối tượng Java theo **quy tắc bắt buộc, tùy chọn, kiểu và số lượng giá trị**; trong bài `PersonAttributeResolver` là mã ứng dụng tự viết.
- Dùng `BasicAttributes` và `BasicAttribute` để unit test các ca **thiếu**, **rỗng**, **sai kiểu**, **đa trị** mà không cần khởi động LDAP server.
- Accessor `DirContextAdapter.getStringAttribute` tiện lợi nhưng chỉ lấy **một giá trị**; cần dùng accessor đa trị và kiểm tra kiểu khi dữ liệu không đơn giản.
- Thiếu thuộc tính trong phản hồi **không tự chứng minh** thuộc tính vắng trong directory: xét `returningAttributes`, ACL, schema, provider và nguồn truy vấn.
- Unit test bảo vệ logic ánh xạ; integration test trên LDAP thật bảo vệ **cấu hình kết nối, truy vấn, quyền, mapping và tính đầy đủ**.
- Không nuốt mọi ngoại lệ thành default, và không log dữ liệu LDAP nhạy cảm để chẩn đoán lỗi chuyển đổi.

### Tài liệu tham khảo

- [Spring LDAP — Simplifying Attribute Access and Manipulation with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html)
- [Spring LDAP — DirContextAdapter API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/DirContextAdapter.html)
- [Spring LDAP — AttributesMapper và ContextMapper](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/package-summary.html)
- [Spring LDAP — Object-Directory Mapping (ODM) và Converters](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring LDAP — Operational Attributes FAQ](https://docs.spring.io/spring-ldap/reference/faq.html)
- [Spring LDAP — Incremental Retrieval of Multi-Valued Attributes](https://docs.spring.io/spring-ldap/reference/utilities.html)
- [Java JNDI — Attributes, Attribute, BasicAttributes](https://docs.oracle.com/en/java/javase/25/docs/api/java.naming/javax/naming/directory/Attributes.html)
