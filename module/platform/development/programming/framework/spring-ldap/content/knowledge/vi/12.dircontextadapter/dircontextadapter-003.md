# `getStringAttributes` và đọc giá trị đa trị với `DirContextAdapter`

Khi ứng dụng Java làm việc với LDAP qua **Spring LDAP**, một thuộc tính của entry không nhất thiết chỉ chứa một giá trị. Ví dụ, một nhóm có thể chứa nhiều thành viên trong thuộc tính `member`; một người dùng có thể có nhiều số điện thoại nếu schema cho phép. `DirContextAdapter` giúp đọc những thuộc tính đó bằng phương thức `getStringAttributes(String name)`, không cần tự duyệt `NamingEnumeration` của JNDI.

Sau bài này, bạn có thể phân biệt thuộc tính đơn trị và đa trị, đọc đủ các giá trị văn bản từ một entry bằng `LdapTemplate`, xử lý trường hợp thuộc tính vắng mặt, đồng thời tránh những giả định sai về thứ tự và kiểu dữ liệu.

## 1. Vì sao cần đọc thuộc tính đa trị?

Xét một entry LDAP mô tả nhóm `app-readers`:

```ldif
dn: cn=app-readers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app-readers
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
```

Trong ví dụ này:

- `cn` mang một giá trị: `app-readers`.
- `member` mang **hai giá trị** dưới cùng tên thuộc tính, mỗi giá trị là DN của một thành viên.
- `objectClass` cũng mang nhiều giá trị (`top`, `groupOfNames`).

Đây là cách LDAP biểu diễn một thuộc tính đa trị; không phải hai thuộc tính `member` khác nhau. Việc thuộc tính có được phép mang nhiều giá trị hay không do **schema LDAP** quyết định. Một số môi trường cũng cung cấp `memberOf` trên entry người dùng để thể hiện nhóm mà người dùng tham gia, nhưng sự hiện diện và cách cập nhật thuộc tính này phụ thuộc máy chủ.

Nếu dùng `getStringAttribute("member")`, ứng dụng chỉ nhận **một giá trị đầu tiên do adapter trả về** và có thể bỏ sót thành viên. Để đọc cả tập giá trị, sử dụng `getStringAttributes("member")`.

## 2. Các phương thức đọc thuộc tính trong `DirContextAdapter`

`DirContextAdapter` triển khai `DirContextOperations`; bạn thường nhận một instance qua `LdapTemplate.lookupContext(...)` hoặc từ `ContextMapper` khi tìm kiếm LDAP. Với các thuộc tính văn bản, hai phương thức cần phân biệt là:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `getStringAttribute("cn")` | `String` | Lấy một giá trị; nếu có nhiều giá trị thì chỉ lấy giá trị đầu, nếu thiếu hoặc không có giá trị thì nhận `null`. |
| `getStringAttributes("member")` | `String[]` | Lấy **tất cả giá trị được trả về** của thuộc tính dưới dạng chuỗi. |
| `attributeExists("member")` | `boolean` | Kiểm tra thuộc tính có hiện diện trong dữ liệu của adapter hay không, kể cả khi chưa có giá trị. |
| `getObjectAttributes("jpegPhoto")` | `Object[]` | Lấy các giá trị ở dạng đối tượng, phù hợp hơn khi dữ liệu không phải chuỗi. |
| `getAttributeSortedStringSet("member")` | `SortedSet<String>` | Lấy các chuỗi dưới dạng tập hợp đã sắp xếp, khi cần biểu diễn theo thứ tự nhất quán. |

Hợp đồng trả về của `getStringAttributes` là điểm dễ nhầm:

| Tình trạng của thuộc tính trong adapter | `getStringAttributes("member")` |
| --- | --- |
| Có hai giá trị `uid=lan,...` và `uid=minh,...` | Mảng `String[]` gồm hai phần tử. |
| Có thuộc tính, nhưng không chứa giá trị | Mảng rỗng `new String[0]` (có thể xảy ra ở mức API; server/schema có thể không cho phép trạng thái này). |
| Không có thuộc tính `member` trong dữ liệu nhận được | `null`. |

Như vậy, **`null` không đồng nghĩa với mảng rỗng**. Cũng cần nhớ rằng thuộc tính không xuất hiện trong adapter có thể do truy vấn không yêu cầu trả về thuộc tính đó, do quyền đọc hoặc do máy chủ không cung cấp; không thể chỉ dựa vào `null` để kết luận thuộc tính thực sự không tồn tại trên server.

> **Lưu ý về thứ tự:** Thuộc tính LDAP đa trị thông thường không có thứ tự mang ý nghĩa nghiệp vụ. Không dựa vào `values[0]` để xác định “thành viên chính” và không so sánh hai danh sách chỉ bằng thứ tự phần tử.

## 3. Đọc tất cả `member` bằng `LdapTemplate`

Giả sử `ContextSource` đã cấu hình base DN `dc=example,dc=org`, `LdapTemplate` đã kết nối đến máy chủ và entry nhóm trong ví dụ đang tồn tại. Mã sau đọc DN các thành viên:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class GroupReader {
    private final LdapTemplate ldapTemplate;

    public GroupReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findMemberDns(String groupCn) {
        // DN tương đối với base DN đã cấu hình.
        Name groupDn = LdapNameBuilder.newInstance()
                .add("ou", "groups")
                .add("cn", groupCn)
                .build();

        DirContextOperations entry = ldapTemplate.lookupContext(groupDn);
        String[] members = entry.getStringAttributes("member");

        if (members == null || members.length == 0) {
            return Collections.emptyList();
        }

        // Sao chép khỏi mảng trả về trước khi đưa cho tầng ứng dụng.
        return Collections.unmodifiableList(
                new ArrayList<>(Arrays.asList(members)));
    }
}
```

Gọi `findMemberDns("app-readers")` với dữ liệu LDIF ở trên sẽ nhận danh sách chứa hai DN `uid=lan,ou=people,dc=example,dc=org` và `uid=minh,ou=people,dc=example,dc=org`. **Không dựa vào thứ tự** hai phần tử đó.

Điểm chính trong ví dụ:

1. `LdapNameBuilder` xây DN từ các thành phần `ou` và `cn`, xử lý ký tự đặc biệt trong giá trị `groupCn` an toàn hơn việc nối chuỗi DN bằng tay.
2. `lookupContext` lấy một entry theo DN và trả về `DirContextOperations`, giao diện có `getStringAttributes`.
3. `getStringAttributes("member")` đọc các giá trị văn bản hiện có trong adapter.
4. Kiểm tra `null` trước khi xử lý mảng; danh sách rỗng ở tầng ứng dụng có thể dùng để biểu diễn “không có giá trị khả dụng”.

Trong một nghiệp vụ cần phân biệt “thuộc tính chưa được trả về” với “thuộc tính đã trả về nhưng rỗng”, **không nên gộp ngay cả hai thành danh sách rỗng**. Khi đó hãy lưu thêm trạng thái hiện diện của thuộc tính hoặc áp dụng chính sách xử lý lỗi rõ ràng.

### Chỉ yêu cầu các thuộc tính cần đọc

Khi entry chứa nhiều dữ liệu, có thể yêu cầu LDAP trả về riêng `cn` và `member`. Trong một phương thức của lớp `GroupReader` đã có trường `ldapTemplate` ở ví dụ trên, bạn có thể dùng overload `lookup(Name, String[], ContextMapper<T>)`:

```java
import java.util.Arrays;
import java.util.List;
import javax.naming.Name;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

Name groupDn = LdapNameBuilder.newInstance()
        .add("ou", "groups")
        .add("cn", "app-readers")
        .build();

ContextMapper<List<String>> mapper = context -> {
    DirContextOperations entry = (DirContextOperations) context;
    String[] members = entry.getStringAttributes("member");
    return members == null ? List.of() : List.copyOf(Arrays.asList(members));
};

List<String> members = ldapTemplate.lookup(
        groupDn, new String[] {"cn", "member"}, mapper);
```

`ContextMapper` nhận context của entry, còn `getStringAttributes` chuyển thuộc tính đa trị sang `String[]`. Nếu truy vấn yêu cầu duy nhất `cn`, lệnh `getStringAttributes("member")` ở mapper thường nhận `null` dù `member` có thể đang tồn tại trên máy chủ. Ví dụ dùng `List.of` và `List.copyOf` (Java 10+).

## 4. Khi nào dùng `getObjectAttributes`?

`getStringAttributes` phù hợp khi giá trị của thuộc tính là **văn bản**, chẳng hạn `cn`, `objectClass`, `member`, `telephoneNumber`. Đối với thuộc tính nhị phân như `jpegPhoto`, hãy giữ nguyên kiểu gốc (giả sử `entry` là `DirContextOperations` đã lấy được từ LDAP):

```java
Object[] photos = entry.getObjectAttributes("jpegPhoto");
if (photos != null) {
    for (Object value : photos) {
        if (value instanceof byte[]) {
            byte[] imageBytes = (byte[]) value;
            // Xử lý dữ liệu nhị phân bằng API thích hợp.
        }
    }
}
```

Không tự ép `byte[]` thành `String` để đọc ảnh hoặc chứng chỉ: kết quả có thể bị hỏng hoặc phụ thuộc bảng mã. Nếu cần đọc toàn bộ `Attributes` theo JNDI, phương thức `entry.getAttributes()` vẫn có sẵn, nhưng với dữ liệu chuỗi đa trị thì `getStringAttributes` thường ngắn gọn hơn.

## 5. Thực hành tại chỗ không cần LDAP server

Ta có thể tạo `DirContextAdapter` từ `Attributes` của JNDI để quan sát kết quả đọc. Đoạn mã sau là ví dụ Java độc lập có phương thức `main`, không phát sinh truy vấn mạng:

```java
import java.util.Arrays;
import javax.naming.ldap.LdapName;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.core.DirContextAdapter;

public class AdapterValuesDemo {
    public static void main(String[] args) throws Exception {
        BasicAttributes attrs = new BasicAttributes(true);
        BasicAttribute member = new BasicAttribute("member");
        member.add("uid=lan,ou=people,dc=example,dc=org");
        member.add("uid=minh,ou=people,dc=example,dc=org");
        attrs.put(member);
        attrs.put("cn", "app-readers");

        DirContextAdapter entry = new DirContextAdapter(
                attrs,
                new LdapName("cn=app-readers,ou=groups,dc=example,dc=org"));

        System.out.println(entry.getStringAttribute("cn"));
        System.out.println(Arrays.toString(entry.getStringAttributes("member")));
        System.out.println(entry.getStringAttributes("description") == null);
    }
}
```

Kết quả mong đợi:

- Dòng đầu là `app-readers`.
- Dòng thứ hai chứa **đủ hai DN** thành viên (thứ tự có thể khác nhau).
- Dòng cuối là `true` vì `description` không được đưa vào adapter.

Thử thay `getStringAttributes("member")` bằng `getStringAttribute("member")` và nhận xét vì sao cách đọc đơn trị không phù hợp để ánh xạ danh sách thành viên. Sau đó xóa `attrs.put(member)` và quan sát giá trị `null`.

## 6. Các tình huống cần chú ý khi dùng trong ứng dụng

| Tình huống | Nguyên nhân hoặc cách xử lý |
| --- | --- |
| Chỉ đọc được một thành viên | Kiểm tra xem có đang gọi `getStringAttribute` thay vì `getStringAttributes` hay không. |
| `getStringAttributes` trả `null` | Kiểm tra tên thuộc tính, danh sách thuộc tính được yêu cầu khi lookup/search, schema và quyền truy cập của tài khoản LDAP. |
| Danh sách giống nhau nhưng thứ tự khác | LDAP không bảo đảm thứ tự thông thường; so sánh theo ngữ nghĩa tập hợp. Nếu giá trị là DN, nên phân tích bằng `LdapName`/`Name` khi cần so sánh DN. |
| Nhầm DN với tên người dùng | `member` của `groupOfNames` thường chứa **DN**, không phải username; cần tra cứu entry người dùng nếu muốn lấy `uid` hay `cn`. |
| Đọc nhóm lớn trên Active Directory bị thiếu thành viên | AD có thể trả từng khoảng giá trị (`member;range=...`). Cần cơ chế **incremental/ranged retrieval** tương ứng, chẳng hạn tiện ích `DefaultIncrementalAttributesMapper` của Spring LDAP; một lần `getStringAttributes("member")` không thay thế cơ chế này. |
| Có dữ liệu nhị phân | Dùng `getObjectAttributes` để tránh xử lý sai kiểu dữ liệu. |

Ngoài ra, nếu không tìm thấy chính **entry** theo DN, `lookupContext` sẽ phát sinh ngoại lệ truy cập LDAP phù hợp; đó là tình huống khác với việc tìm thấy entry nhưng thiếu một thuộc tính. Với dữ liệu nhóm và quyền truy cập, cần tuân thủ ACL của directory, sử dụng kênh kết nối bảo mật theo cấu hình hệ thống và tránh ghi toàn bộ DN/thành viên nhạy cảm vào log.

## 7. Tự kiểm tra

1. Với `member` có ba DN, `getStringAttribute("member")` và `getStringAttributes("member")` khác nhau ở điểm nào?
2. Tại sao `getStringAttributes("member") == null` chưa đủ để khẳng định nhóm không có thành viên?
3. Khi ánh xạ `member` sang `List<String>`, lúc nào nên giữ lại thông tin “thuộc tính vắng mặt” thay vì chuyển mọi trường hợp thành `List.of()`?
4. Nếu nhận được `member;range=0-1499` từ Active Directory, vì sao việc đọc `member` một lần có thể chưa đủ?

**Ghi nhớ:** Đọc thuộc tính đa trị với `DirContextAdapter` bằng `getStringAttributes(name)`; xử lý `null`, chọn kiểu dữ liệu phù hợp và không dựa vào thứ tự giá trị. Trường hợp dữ liệu LDAP được trả theo từng khoảng cần cơ chế truy xuất bổ sung.

## Tài liệu tham khảo

- [Spring LDAP — Simplifying Attribute Access and Manipulation with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html)
- [Spring LDAP Javadoc — DirContextAdapter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/DirContextAdapter.html)
- [Spring LDAP Javadoc — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP — Incremental Retrieval of Multi-Valued Attributes](https://docs.spring.io/spring-ldap/reference/utilities.html)
