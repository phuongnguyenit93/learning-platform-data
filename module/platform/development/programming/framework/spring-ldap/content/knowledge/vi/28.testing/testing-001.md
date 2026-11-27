# Kiểm thử mapping không cần server LDAP thật

Khi làm việc với **Spring LDAP**, một phép tìm kiếm thường có hai phần: lấy entry từ thư mục và chuyển dữ liệu của entry thành đối tượng Java. Hai phần này cần được kiểm thử riêng. Để kiểm tra logic chuyển đổi (*mapping*), ta có thể tạo các thuộc tính LDAP ngay trong bộ nhớ, gọi mapper trực tiếp và so sánh kết quả. Không cần khởi động OpenLDAP, Active Directory, embedded LDAP hay mở kết nối mạng.

Bài này tập trung vào mapping trong **Spring LDAP** với `AttributesMapper` và `ContextMapper`. Đây là một phần của quá trình làm việc với DN, schema, filter, `LdapTemplate`, `LdapClient` và ODM; các kiểm thử đơn vị ở đây giúp phát hiện lỗi chuyển đổi dữ liệu trước khi kiểm thử tích hợp về tìm kiếm, xác thực, TLS và phân quyền.

## 1. Ranh giới của phép kiểm thử

Giả sử ứng dụng tìm người dùng bằng LDAP:

```text
Ứng dụng
   │
   ▼
LdapTemplate / LdapClient ── truy vấn, filter, kết nối ──► LDAP server
   │
   ▼
AttributesMapper / ContextMapper
   │
   ▼
User hoặc DTO nghiệp vụ
```

Trong **unit test mapping**, đầu vào của mapper được tạo tại chỗ:

```text
BasicAttributes / DirContextAdapter (trong bộ nhớ)
                         │
                         ▼
              Mapper thực của ứng dụng
                         │
                         ▼
                DTO cần kiểm tra
```

Ta kiểm chứng được tên thuộc tính, kiểu dữ liệu, giá trị mặc định, thuộc tính bắt buộc, thuộc tính nhiều giá trị, dữ liệu Unicode và cách xử lý DN. Ta **chưa** kiểm chứng filter có tìm đúng entry trên server hay không, schema có cho phép thuộc tính đó không, tài khoản có quyền đọc không, hoặc TLS/pooling có hoạt động không. Những hành vi ấy cần kiểm thử tích hợp với một thư mục phù hợp.

| Cơ chế | Đầu vào có thể tạo trong bộ nhớ | Phạm vi phù hợp |
| --- | --- | --- |
| `AttributesMapper<T>` | `javax.naming.directory.BasicAttributes`, `BasicAttribute` | Chuyển các thuộc tính của một entry thành đối tượng |
| `ContextMapper<T>` | `org.springframework.ldap.core.DirContextAdapter` | Chuyển các thuộc tính kèm thông tin context/DN |
| `LdapTemplate` / `LdapClient` | Mock API truy vấn nếu kiểm thử lớp service | Kiểm tra service gọi mapper hoặc xử lý kết quả ra sao |
| ODM (`@Entry`, `@Attribute`, `@Id`, …) | Đối tượng Java và fixture riêng cho logic nghiệp vụ | Kiểm tra logic dùng entity; việc Spring LDAP thực sự đọc/ghi entity qua ODM cần kiểm thử tích hợp hoặc phép kiểm thử riêng với hạ tầng ODM |

Các ví dụ bên dưới dùng Java 17+, `spring-ldap-core` và JUnit Jupiter (JUnit 5). Mã nguồn và mã kiểm thử được đặt trong package `com.example.ldap`; dự án cần khai báo `org.springframework.ldap:spring-ldap-core` cùng `org.junit.jupiter:junit-jupiter` ở phạm vi test, theo cơ chế quản lý phiên bản hiện có.

## 2. Kiểm thử `AttributesMapper` bằng `BasicAttributes`

`AttributesMapper<T>` nhận `javax.naming.directory.Attributes`, không bắt buộc phải có `DirContext` hoặc kết nối LDAP. Đây là lựa chọn gọn nhất khi chỉ cần map dữ liệu của entry mà không cần DN.

Ví dụ một người dùng có ba thuộc tính:

| Thuộc tính LDAP | Ý nghĩa | Quy tắc mapping |
| --- | --- | --- |
| `uid` | Mã đăng nhập | Bắt buộc, là chuỗi |
| `cn` | Tên hiển thị | Bắt buộc, là chuỗi |
| `mail` | Email | Có thể vắng mặt, khi đó trả về `null` |

Tạo mapper trong `src/main/java/com/example/ldap/UserAttributesMapper.java`:

```java
package com.example.ldap;

import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;

public final class UserAttributesMapper
        implements AttributesMapper<UserAttributesMapper.User> {

    public record User(String uid, String displayName, String email) {}

    @Override
    public User mapFromAttributes(Attributes attributes) throws NamingException {
        return new User(
                readString(attributes, "uid", true),
                readString(attributes, "cn", true),
                readString(attributes, "mail", false)
        );
    }

    private static String readString(
            Attributes attributes, String name, boolean required)
            throws NamingException {

        Attribute attribute = attributes.get(name);
        if (attribute == null || attribute.size() == 0) {
            if (required) {
                throw new IllegalArgumentException(
                        "Thiếu thuộc tính LDAP bắt buộc: " + name);
            }
            return null;
        }

        Object value = attribute.get();
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException(
                    "Thuộc tính LDAP không phải chuỗi: " + name);
        }
        return text;
    }
}
```

`Attributes.get(name)` có thể trả về `null`, còn `Attribute.get()` có thể ném `NamingException`. Vì vậy mapper kiểm tra thuộc tính vắng mặt hoặc rỗng, đồng thời từ chối dữ liệu không phải chuỗi thay vì âm thầm chuyển `byte[]` thành văn bản sai. Với dữ liệu nghiệp vụ khác, hãy thống nhất quy tắc lỗi theo contract của ứng dụng (ví dụ lỗi mapping riêng).

### Unit test đầy đủ

Tạo `src/test/java/com/example/ldap/UserAttributesMapperTest.java`:

```java
package com.example.ldap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.junit.jupiter.api.Test;

class UserAttributesMapperTest {

    private final UserAttributesMapper mapper = new UserAttributesMapper();

    @Test
    void mapsAttributesIncludingUnicode() throws Exception {
        Attributes attributes = new BasicAttributes(true);
        attributes.put("UID", "u01");
        attributes.put("cn", "Nguyễn An");
        attributes.put("mail", "an@example.org");

        UserAttributesMapper.User user =
                mapper.mapFromAttributes(attributes);

        assertEquals("u01", user.uid());
        assertEquals("Nguyễn An", user.displayName());
        assertEquals("an@example.org", user.email());
    }

    @Test
    void allowsMissingOptionalEmail() throws Exception {
        Attributes attributes = new BasicAttributes(true);
        attributes.put("uid", "u02");
        attributes.put("cn", "Bình");

        UserAttributesMapper.User user =
                mapper.mapFromAttributes(attributes);

        assertEquals("u02", user.uid());
        assertNull(user.email());
    }

    @Test
    void rejectsMissingRequiredAttribute() {
        Attributes attributes = new BasicAttributes(true);
        attributes.put("uid", "u03");

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> mapper.mapFromAttributes(attributes));

        assertEquals("Thiếu thuộc tính LDAP bắt buộc: cn",
                error.getMessage());
    }

    @Test
    void rejectsBinaryValueForTextAttribute() {
        Attributes attributes = new BasicAttributes(true);
        attributes.put("uid", "u04");
        attributes.put(new BasicAttribute("cn", new byte[] {1, 2, 3}));

        assertThrows(IllegalArgumentException.class,
                () -> mapper.mapFromAttributes(attributes));
    }
}
```

`new BasicAttributes(true)` dùng chế độ **không phân biệt chữ hoa/chữ thường của tên thuộc tính**. Vì thế fixture đặt `UID` vẫn tra được bằng `uid`. Không nhầm tính chất này với quy tắc so khớp **giá trị** của attribute trên LDAP server: so khớp giá trị phụ thuộc schema và matching rule, không thể suy ra từ unit test này.

Những kiểm thử trên chạy trong JVM như unit test Java thông thường: không có `ContextSource`, credentials, cổng LDAP hoặc `@SpringBootTest`. Cũng không cần mock `AttributesMapper`, vì mapper chính là đối tượng đang được kiểm thử.

## 3. Kiểm thử `ContextMapper` bằng `DirContextAdapter`

Khi việc mapping cần tên phân biệt (DN) hoặc API của `DirContextOperations`, dùng `ContextMapper<T>`. Spring LDAP có `DirContextAdapter`, một đối tượng context có thể tạo trực tiếp, gắn thuộc tính và truyền vào mapper mà không cần mở phiên LDAP.

Ví dụ một entry có DN tương đối `uid=u01,ou=people`, tên hiển thị và thuộc tính `memberOf` nhiều giá trị. Tạo `src/main/java/com/example/ldap/MembershipContextMapper.java`:

```java
package com.example.ldap;

import java.util.Arrays;
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

public final class MembershipContextMapper
        implements ContextMapper<MembershipContextMapper.Membership> {

    public record Membership(String dn, String displayName,
                             List<String> groups) {}

    @Override
    public Membership mapFromContext(Object context) {
        if (!(context instanceof DirContextOperations entry)) {
            throw new IllegalArgumentException(
                    "Cần một DirContextOperations để mapping");
        }

        String[] memberOf = entry.getStringAttributes("memberOf");
        List<String> groups = memberOf == null
                ? List.of()
                : List.copyOf(Arrays.asList(memberOf));

        return new Membership(
                entry.getDn().toString(),
                entry.getStringAttribute("cn"),
                groups
        );
    }
}
```

Tạo `src/test/java/com/example/ldap/MembershipContextMapperTest.java`:

```java
package com.example.ldap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;

class MembershipContextMapperTest {

    private final MembershipContextMapper mapper =
            new MembershipContextMapper();

    @Test
    void mapsDnAndMultipleGroups() throws Exception {
        DirContextAdapter entry = new DirContextAdapter(
                new LdapName("uid=u01,ou=people"));
        entry.setAttributeValue("cn", "Nguyễn An");
        entry.setAttributeValues("memberOf", new String[] {
                "cn=dev,ou=groups",
                "cn=reviewers,ou=groups"
        });

        MembershipContextMapper.Membership result =
                mapper.mapFromContext(entry);

        assertEquals("uid=u01,ou=people", result.dn());
        assertEquals("Nguyễn An", result.displayName());
        assertEquals(Set.of("cn=dev,ou=groups", "cn=reviewers,ou=groups"),
                new HashSet<>(result.groups()));
    }

    @Test
    void mapsMissingGroupsToEmptyList() throws Exception {
        DirContextAdapter entry = new DirContextAdapter(
                new LdapName("uid=u02,ou=people"));
        entry.setAttributeValue("cn", "Bình");

        MembershipContextMapper.Membership result =
                mapper.mapFromContext(entry);

        assertEquals(List.of(), result.groups());
        assertTrue(result.groups().isEmpty());
    }
}
```

Ở đây **không so sánh thứ tự** của `memberOf`: các giá trị của thuộc tính LDAP nhiều giá trị thường không có thứ tự ngữ nghĩa. Nếu nghiệp vụ đòi thứ tự, phải có một quy tắc sắp xếp được xác định riêng. DN do `DirContextAdapter` giữ trong ví dụ là DN đã cấp khi khởi tạo; với kết quả tìm kiếm thực tế, cần phân biệt DN tương đối với `base` và DN đầy đủ trước khi đưa vào DTO hoặc liên kết LDAP khác. Khi cần so sánh cấu trúc DN, nên dùng `LdapName`/`Name` thay vì tự tách bằng dấu phẩy (vì giá trị RDN có thể chứa dấu phẩy đã escape).

## 4. Thiết kế fixture và ca kiểm thử có giá trị

Fixture càng nhỏ, nguyên nhân lỗi càng rõ. Một fixture tốt chỉ chứa các thuộc tính mà mapper thực sự đọc. Đồng thời phải kiểm thử cả dữ liệu hợp lệ và dữ liệu sai cấu trúc, không chỉ tình huống “đủ tất cả các trường”.

| Tình huống | Fixture | Điều cần khẳng định |
| --- | --- | --- |
| Thuộc tính chữ hoa/chữ thường | `BasicAttributes(true)` và `UID` | Mapper đọc đúng `uid` |
| Chuỗi Unicode | `cn = "Nguyễn An"` | Không lỗi dấu tiếng Việt |
| Thuộc tính tùy chọn vắng mặt | Không đặt `mail` | Trả về `null` theo contract |
| Thuộc tính bắt buộc vắng mặt | Không đặt `cn` | Ném lỗi rõ ràng |
| Thuộc tính có kiểu khác | `cn` chứa `byte[]` | Không ép kiểu sai |
| Thuộc tính nhiều giá trị | Hai giá trị `memberOf` | Không làm mất giá trị; không phụ thuộc thứ tự |
| DN có ký tự đặc biệt | Dùng `new LdapName(...)` | Xử lý DN theo cú pháp LDAP, không split thủ công |
| Thuộc tính rỗng | `new BasicAttribute("cn")` | Thực thi đúng chính sách với giá trị rỗng |

Với thuộc tính **nhiều giá trị** khi dùng `AttributesMapper`, không nên chỉ gọi `attribute.get()` rồi coi đó là toàn bộ danh sách. Hãy duyệt `attribute.getAll()` qua `NamingEnumeration<?>`, chuyển từng giá trị đúng kiểu và đóng enumeration khi xong. Với thuộc tính nhị phân như `jpegPhoto` hoặc `userCertificate`, xử lý `byte[]` theo schema/contract thay vì dùng `toString()`.

Đừng nhầm ba tình huống: attribute không tồn tại, attribute tồn tại nhưng không có giá trị, và attribute có chuỗi rỗng. Các trường hợp ấy có thể cần chính sách nghiệp vụ khác nhau. Mapper mẫu trên coi hai trường hợp đầu là thiếu; trường hợp chuỗi rỗng vẫn được giữ nguyên, để ứng dụng quyết định có chấp nhận hay không.

## 5. Khi nào cần mock, khi nào cần LDAP tích hợp?

Với bài toán **kiểm thử mapping**, gọi trực tiếp `mapFromAttributes(...)` hoặc `mapFromContext(...)` là đủ. Không cần mock máy chủ hay mock những class dữ liệu như `BasicAttributes` và `DirContextAdapter`.

Khi kiểm thử một **service** gọi `LdapTemplate.search(...)` hoặc một chuỗi thao tác `LdapClient`, có thể mock `LdapOperations`/lớp client ở ranh giới truy vấn để kiểm tra service xử lý danh sách kết quả, trường hợp không có kết quả và lỗi ứng dụng. Bài kiểm thử service đó chứng minh luồng điều khiển của service; nếu mock trả về DTO dựng sẵn thì **không** chứng minh mapper thực sự chuyển được entry.

Các phần sau nên được kiểm thử tích hợp riêng bằng LDAP test server hoặc môi trường thư mục dành cho kiểm thử:

- Filter, base DN, scope tìm kiếm và quy tắc matching do schema quyết định.
- Mapping ODM thông qua annotation (`@Entry`, `@Attribute`, `@Id`) khi framework thực hiện đọc/ghi entry, cùng các thao tác `bind`, `modify`, `unbind`.
- Xác thực, quyền truy cập, StartTLS/LDAPS, pooling, referral và xử lý lỗi từ server.
- Đặc tính thực tế của từng thư mục (ví dụ Active Directory so với OpenLDAP), bao gồm schema, thuộc tính hệ thống và kiểu giá trị.

Một bộ kiểm thử cân đối thường gồm nhiều unit test mapping nhanh, một số unit test service sử dụng mock, và các integration test tập trung vào ranh giới giao tiếp LDAP. Unit test mapping phát hiện lỗi chuyển đổi dữ liệu sớm; integration test xác minh rằng dữ liệu thực của server và cách Spring LDAP lấy dữ liệu phù hợp với các giả định trong mapper.

## 6. Tự kiểm tra kết quả học tập

Sau khi chạy các test JUnit 5 trong dự án, hãy tự trả lời:

1. Vì sao `BasicAttributes` có thể dùng để kiểm thử `AttributesMapper` mà không cần `ContextSource`?
2. Khi `mail` vắng mặt và khi `cn` vắng mặt, mapper đưa ra hai kết quả khác nhau như thế nào?
3. Vì sao nên so sánh các nhóm `memberOf` theo tập hợp thay vì theo chỉ số mảng?
4. Unit test với `DirContextAdapter` cho biết điều gì về DN, và điều gì vẫn phải xác minh khi truy vấn server thật?
5. Nếu chuyển sang ODM hoặc dùng TLS, kiểm thử nào cần bổ sung để bao phủ phần việc nằm ngoài mapping?

**Kết quả mong đợi:** người học có thể tự tạo một LDAP entry giả bằng các API trong bộ nhớ, gọi mapper thực của ứng dụng, xác nhận đầu ra cho tình huống thường gặp và tình huống lỗi, rồi xác định đúng phần nào cần kiểm thử tích hợp thay vì tự tin quá mức vào unit test.
