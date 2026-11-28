# Ánh xạ Attributes sang DTO bằng AttributesMapper

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập dịch vụ thư mục LDAP bằng Spring Data LDAP/Spring LDAP để tìm kiếm và thao tác trên các entry được tổ chức theo cây DN (Distinguished Name), tuân theo `objectClass` và schema của directory. Bên cạnh mô hình entity với repository, có những chức năng chỉ cần **đọc một vài thuộc tính** và trả về DTO phục vụ API, giao diện hoặc nghiệp vụ. `AttributesMapper<T>` là công cụ phù hợp cho trường hợp đó.

Sau bài học, bạn có thể giải thích cơ chế ánh xạ một kết quả LDAP sang DTO, viết mapper có kiểm tra dữ liệu thiếu và đa trị, gọi `LdapTemplate.search(...)` với bộ lọc an toàn, cũng như kiểm thử mapper độc lập với LDAP server.

## 1. Từ LDAP entry đến DTO

Một entry ví dụ trong cây thư mục:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
telephoneNumber: +84 28 1111 2222
telephoneNumber: +84 28 3333 4444
```

- **DN** `uid=lan,ou=people,dc=example,dc=org` xác định vị trí của entry trên cây, không mặc nhiên là một thuộc tính được trả về trong `Attributes`.
- **`objectClass`/schema** xác định những loại entry hợp lệ và thuộc tính có thể hoặc phải có. Chẳng hạn `person` yêu cầu `cn` và `sn`; các thuộc tính như `mail`, `telephoneNumber` có thể vắng mặt.
- **`Attributes`** (JNDI, `javax.naming.directory.Attributes`) là tập các `Attribute` được LDAP server trả về cho *một* entry; mỗi `Attribute` có thể có không, một hoặc nhiều giá trị.
- **DTO** là cấu trúc Java do ứng dụng định nghĩa. DTO có thể chỉ giữ `uid`, `cn`, email và danh sách số điện thoại; nó không cần phản ánh toàn bộ entry.

Luồng đọc điển hình:

```text
LdapTemplate.search(LdapQuery, AttributesMapper<PersonDto>)
           |
           v
 LDAP server -- các entry khớp base / scope / filter
           |
           v
 Mỗi SearchResult -> Attributes -> mapFromAttributes(...)
           |
           v
          PersonDto  ->  List<PersonDto>
```

`AttributesMapper<T>` thuộc package `org.springframework.ldap.core`, với phương thức:

```java
T mapFromAttributes(javax.naming.directory.Attributes attributes)
        throws javax.naming.NamingException;
```

`LdapTemplate` gọi mapper **một lần cho mỗi entry** khớp truy vấn và gom các giá trị trả về thành `List<T>`. Mapper chỉ chuyển đổi dữ liệu được trả về; nó không tự thực hiện truy vấn, cập nhật LDAP hoặc lưu DTO. Khi dùng `lookup`, Spring LDAP cũng có các overload nhận `AttributesMapper` để chuyển đổi một entry.

## 2. Thiết kế DTO và quy tắc ánh xạ

Ở ví dụ này, ta chọn quy tắc rõ ràng trước khi viết code:

| Thuộc tính LDAP | Kiểu DTO | Quy tắc |
|---|---|---|
| `uid` | `String uid` | Bắt buộc đối với DTO; thiếu hoặc chuỗi rỗng thì báo lỗi |
| `cn` | `String fullName` | Bắt buộc đối với DTO; thiếu hoặc chuỗi rỗng thì báo lỗi |
| `mail` | `String email` | Tùy chọn; thiếu thì `null`; ví dụ chỉ lấy giá trị đầu tiên |
| `telephoneNumber` | `List<String> phones` | Đọc tất cả giá trị; thiếu thì danh sách rỗng |

Đây là **quy tắc của ứng dụng**, không phải tuyên bố rằng mọi server LDAP đều bắt buộc có `uid` hoặc chỉ cho phép một `mail`. Thuộc tính thực tế phụ thuộc schema, dữ liệu, quyền truy cập và cấu hình server. Nếu nghiệp vụ cần nhiều địa chỉ email, hãy ánh xạ `mail` thành danh sách thay vì lấy giá trị đầu tiên.

Với Java 17 trở lên, DTO có thể dùng `record`:

**`PersonDto.java`**

```java
package com.example.ldap;

import java.util.List;

public record PersonDto(
        String uid,
        String fullName,
        String email,
        List<String> phones) {
}
```

DTO này tách khỏi lớp LDAP entry và phù hợp để truyền dữ liệu đọc cho tầng ứng dụng. Các giá trị như ảnh `jpegPhoto` là dữ liệu nhị phân, không nên ép kiểu thành `String` theo mẫu dưới đây.

## 3. Viết AttributesMapper xử lý dữ liệu thiếu và đa trị

**`PersonAttributesMapper.java`**

```java
package com.example.ldap;

import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.InvalidAttributeValueException;
import org.springframework.ldap.core.AttributesMapper;

public final class PersonAttributesMapper implements AttributesMapper<PersonDto> {

    @Override
    public PersonDto mapFromAttributes(Attributes attrs) throws NamingException {
        return new PersonDto(
                requiredString(attrs, "uid"),
                requiredString(attrs, "cn"),
                optionalString(attrs, "mail"),
                stringValues(attrs, "telephoneNumber"));
    }

    private static String requiredString(Attributes attrs, String name)
            throws NamingException {
        String value = optionalString(attrs, name);
        if (value == null || value.isBlank()) {
            throw new InvalidAttributeValueException(
                    "Thiếu thuộc tính LDAP bắt buộc: " + name);
        }
        return value;
    }

    private static String optionalString(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        if (attr == null || attr.size() == 0) {
            return null;
        }

        Object raw = attr.get();
        if (!(raw instanceof String value)) {
            throw new InvalidAttributeValueException(
                    "Thuộc tính LDAP không phải chuỗi: " + name);
        }
        return value;
    }

    private static List<String> stringValues(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        if (attr == null) {
            return List.of();
        }

        List<String> result = new ArrayList<>();
        NamingEnumeration<?> values = attr.getAll();
        try {
            while (values.hasMore()) {
                Object raw = values.next();
                if (!(raw instanceof String value)) {
                    throw new InvalidAttributeValueException(
                            "Giá trị LDAP không phải chuỗi: " + name);
                }
                result.add(value);
            }
        } finally {
            values.close();
        }
        return List.copyOf(result);
    }
}
```

Những điểm cần hiểu trong triển khai:

1. `attrs.get("mail")` có thể trả về `null` nếu thuộc tính không tồn tại **hoặc** không nằm trong danh sách thuộc tính được yêu cầu trả về; không gọi thẳng `get()` khi chưa kiểm tra.
2. `Attribute.get()` lấy một giá trị, trong khi `Attribute.getAll()` trả về `NamingEnumeration` để duyệt các giá trị. Mapper đóng enumeration bằng `finally` kể cả khi xảy ra lỗi.
3. LDAP không bảo đảm thứ tự có ý nghĩa của các giá trị đa trị. Nếu nghiệp vụ cần thứ tự hoặc số điện thoại ưu tiên, phải có quy tắc bổ sung; không dựa vào vị trí giá trị do server trả về.
4. Kiểm tra `instanceof String` giúp phát hiện sai kiểu thay vì tạo dữ liệu DTO sai. Với giá trị nhị phân, xử lý `byte[]` theo schema và hợp đồng API riêng.
5. Mapper không giữ trạng thái giữa các lần gọi, nên có thể tái sử dụng. `NamingException` được `LdapTemplate` xử lý theo cơ chế ngoại lệ của Spring LDAP; không nên lặng lẽ bỏ qua mọi lỗi ánh xạ.

Việc coi `uid` và `cn` là bắt buộc ở đây giúp phát hiện entry thiếu dữ liệu trước khi trả DTO. Một ứng dụng cần biểu diễn dữ liệu thiếu có thể thay quy tắc bằng trường nullable hoặc kiểu khác, miễn là thực hiện nhất quán và có kiểm thử.

## 4. Dùng mapper trong LdapTemplate.search

Giả sử `ContextSource` đã kết nối đến LDAP server và cấu hình **base DN** là `dc=example,dc=org`. Khi đó, truy vấn dưới đây dùng `ou=people` làm base **tương đối** với base DN của kết nối, và tìm các entry có `objectClass=inetOrgPerson` và `uid` phù hợp.

**`PersonDirectoryReader.java`**

```java
package com.example.ldap;

import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.stereotype.Repository;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class PersonDirectoryReader {
    private final LdapTemplate ldapTemplate;
    private final PersonAttributesMapper mapper = new PersonAttributesMapper();

    public PersonDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonDto> findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        LdapQuery ldapQuery = query()
                .base("ou=people")
                .attributes("uid", "cn", "mail", "telephoneNumber")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(ldapQuery, mapper);
    }
}
```

Diễn giải phần truy vấn:

- `base("ou=people")` giới hạn nhánh tìm kiếm; base DN của ứng dụng phải được cấu hình nhất quán. Mặc định truy vấn Spring LDAP dùng phạm vi `SUBTREE` nếu không đặt `searchScope`, nhưng ứng dụng có thể thay thành `ONELEVEL` hoặc `OBJECT` tùy mục tiêu.
- `attributes("uid", "cn", "mail", "telephoneNumber")` chỉ yêu cầu các trường mapper sử dụng, giảm dữ liệu truyền và tránh lấy các trường không cần thiết. Các tham số cấu hình truy vấn (base, scope, thuộc tính, giới hạn) phải được khai báo **trước** phần `where(...)`.
- `where(...).is(...).and(...).is(uid)` xây dựng LDAP filter có mã hóa giá trị đầu vào; tránh nối chuỗi thành `"(uid=" + uid + ")"` vì có nguy cơ LDAP filter injection.
- `search(...)` trả về `List<PersonDto>`: danh sách rỗng nếu không tìm thấy; nhiều phần tử nếu nhiều entry khớp. Không giả định `uid` luôn duy nhất trên mọi nhánh thư mục. Nếu nghiệp vụ yêu cầu đúng một kết quả, phải kiểm tra số lượng và quy tắc định danh.

Nếu số kết quả lớn, hãy chủ động giới hạn phạm vi, thời gian hoặc số lượng bằng `searchScope(...)`, `timeLimit(...)`, `countLimit(...)`, và dùng cơ chế phân trang được directory hỗ trợ khi cần. Giới hạn số lượng không thay thế cho phân trang đầy đủ.

## 5. Khi nào chọn AttributesMapper, ContextMapper hoặc repository?

| Cách tiếp cận | Dữ liệu nhận khi ánh xạ | Trường hợp phù hợp |
|---|---|---|
| `AttributesMapper<T>` | Các `Attributes` của entry | Đọc thuộc tính và tạo DTO đơn giản; không cần DN hay trạng thái context |
| `ContextMapper<T>` | Đối tượng context, thường là `DirContextOperations` | Cần thêm thông tin context như DN, thao tác với biểu diễn entry |
| Spring Data LDAP repository / ODM | Entity được gắn ánh xạ với `@Entry`, `@Attribute`, `@Id`, ... | Quản lý entity theo mô hình repository và các thao tác CRUD |

Một hạn chế thường gặp là cố lấy DN qua `AttributesMapper`: **DN của `SearchResult` không tự xuất hiện trong `Attributes`**. Nếu DTO cần DN, có thể dùng `ContextMapper` và `DirContextOperations.getDn()`, đồng thời hiểu DN trả về trong ngữ cảnh base của kết nối; khi cần DN tuyệt đối phải xử lý base phù hợp. Không nên phụ thuộc vào thuộc tính riêng của một loại directory để giả định mọi server đều có trường `distinguishedName`.

`AttributesMapper` là API thuộc **Spring LDAP Core**, có thể dùng cùng dự án Spring Data LDAP. Nó không yêu cầu khai báo entity hay repository cho từng DTO đọc.

## 6. Kiểm thử mapper không cần LDAP server

JNDI cung cấp `BasicAttributes` và `BasicAttribute` để mô phỏng các thuộc tính nhận từ một entry. Ví dụ kiểm thử JUnit 5 sau kiểm tra cả trường tùy chọn thiếu, trường đa trị và lỗi trường bắt buộc:

**`PersonAttributesMapperTest.java`**

```java
package com.example.ldap;

import java.util.Set;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.InvalidAttributeValueException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PersonAttributesMapperTest {
    private final PersonAttributesMapper mapper = new PersonAttributesMapper();

    @Test
    void mapsMissingOptionalAndMultiplePhones() throws Exception {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("uid", "lan");
        attrs.put("cn", "Lan Nguyen");
        Attribute phones = new BasicAttribute("telephoneNumber");
        phones.add("+84 28 1111 2222");
        phones.add("+84 28 3333 4444");
        attrs.put(phones);

        PersonDto person = mapper.mapFromAttributes(attrs);

        assertEquals("lan", person.uid());
        assertEquals("Lan Nguyen", person.fullName());
        assertNull(person.email());
        assertEquals(
                Set.of("+84 28 1111 2222", "+84 28 3333 4444"),
                Set.copyOf(person.phones()));
    }

    @Test
    void rejectsMissingRequiredUid() {
        Attributes attrs = new BasicAttributes(true);
        attrs.put("cn", "Lan Nguyen");

        assertThrows(InvalidAttributeValueException.class,
                () -> mapper.mapFromAttributes(attrs));
    }
}
```

`new BasicAttributes(true)` làm tên thuộc tính trong dữ liệu thử nghiệm không phân biệt chữ hoa/chữ thường. Phần kiểm thử dùng `Set` để không gắn ý nghĩa vào thứ tự của thuộc tính đa trị. Có thể bổ sung bài kiểm thử cho giá trị kiểu `byte[]`, thuộc tính rỗng và một `mail` hợp lệ.

**Kiểm thử tích hợp** vẫn cần một LDAP directory (thật hoặc dành cho thử nghiệm) với schema và dữ liệu mẫu: thêm entry dưới `ou=people`, gọi `findByUid("lan")`, đối chiếu các trường DTO, rồi kiểm tra truy vấn không khớp và quyền đọc thuộc tính. Kiểm thử đơn vị chỉ xác nhận logic mapper; nó không chứng minh cấu hình kết nối, quyền LDAP hoặc filter hoạt động đúng trên server.

## 7. Lỗi thường gặp và lưu ý vận hành

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `attrs.get("cn") == null` | Entry thiếu trường, thuộc tính không được trả về, hoặc tài khoản bind thiếu quyền đọc | Kiểm tra schema, `attributes(...)` và ACL của directory |
| Ép kiểu trực tiếp gây `ClassCastException` | Giá trị không phải `String`, ví dụ thuộc tính nhị phân | Kiểm tra kiểu dữ liệu; giải mã/chuyển đổi theo schema |
| Chỉ đọc một số điện thoại | Dùng `get()` cho trường đa trị | Duyệt `getAll()` và định nghĩa cách xử lý nhiều giá trị |
| DTO thiếu DN | `AttributesMapper` chỉ nhận tập thuộc tính | Dùng `ContextMapper` khi cần DN |
| Truy vấn không có kết quả | Sai base DN, scope, filter, `objectClass` hoặc quyền truy cập | Kiểm tra từng điều kiện và thử với entry mẫu |
| Mapper báo trường bắt buộc thiếu | Dữ liệu entry không đáp ứng hợp đồng DTO | Sửa dữ liệu/schema hoặc điều chỉnh quy tắc required/optional |

Khi truy cập directory trong môi trường thực tế, cấu hình kết nối bảo mật (LDAPS hoặc StartTLS, xác thực chứng chỉ phù hợp), lưu thông tin bind trong cấu hình bí mật, cấp quyền đọc tối thiểu, và tránh ghi log nguyên giá trị thuộc tính nhạy cảm. Sử dụng truy vấn có escape đầu vào và chỉ lấy những thuộc tính thật sự cần thiết.

## 8. Tự kiểm tra kiến thức

1. Nếu `mail` không được trả về, `attrs.get("mail")` có giá trị gì và mapper xử lý ra sao?
2. Vì sao dùng `getAll()` để lấy `telephoneNumber` thay vì ép một giá trị từ `get()`?
3. Nếu DTO cần DN của entry, tại sao chỉ dùng `AttributesMapper` là chưa đủ?
4. Tại sao nên đặt `attributes(...)` trước `where(...)` và không nối trực tiếp dữ liệu người dùng vào LDAP filter?
5. Kiểm thử đơn vị với `BasicAttributes` kiểm chứng phần nào, còn điều gì phải kiểm thử với LDAP server?

**Ghi nhớ:** `AttributesMapper` cho phép kiểm soát tường minh cách chuyển từng tập thuộc tính LDAP thành DTO. Chất lượng ánh xạ phụ thuộc vào việc hiểu schema, xử lý thuộc tính thiếu/đa trị, giới hạn dữ liệu truy vấn và kiểm thử bằng các trường hợp biên.

### Tài liệu tham khảo

- Spring LDAP Javadoc: [`AttributesMapper`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/AttributesMapper.html).
- Spring LDAP Javadoc: [`LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html).
- Spring LDAP Javadoc: [`LdapQueryBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html).
- Spring LDAP Reference: [Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html).
