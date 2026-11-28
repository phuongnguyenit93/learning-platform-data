# DirContext, LdapContext và các đối tượng thuộc tính

## 1. Mục tiêu và vị trí trong kiến trúc Spring Data LDAP

Khi truy cập một dịch vụ thư mục LDAP từ Java, **JNDI** (*Java Naming and Directory Interface*) là lớp API nền tảng: nó biểu diễn đường dẫn trong cây thư mục bằng tên, thao tác với entry thông qua `DirContext` và biểu diễn dữ liệu entry qua `Attributes`/`Attribute`. `LdapContext` là một dạng `DirContext` có thêm những khả năng riêng của giao thức LDAP, chẳng hạn **LDAP controls** và **extended operations**.

Trong ứng dụng **Spring Data LDAP**, developer thường tương tác với repository, entity ODM hoặc `LdapTemplate`. Hiểu các API JNDI bên dưới giúp giải thích được cách DN, `objectClass`, schema, truy vấn, CRUD, bảo mật kết nối và exception thực sự vận hành.

Sau bài học, bạn có thể:

- Phân biệt `Context`, `DirContext`, `LdapContext`, `LdapContextSource` và `DirContextOperations`.
- Đọc, tạo, sửa và tìm kiếm entry bằng các đối tượng `Attributes`, `Attribute`, `SearchResult`, `ModificationItem` và `SearchControls`.
- Giải thích trách nhiệm quản lý tài nguyên và ánh xạ dữ liệu của `LdapTemplate` so với JNDI thuần.
- Dùng API tạo DN và dựng filter đúng cách để tránh lỗi cú pháp và LDAP injection.
- Lựa chọn abstraction phù hợp khi cần thao tác repository, đọc thuộc tính, hoặc dùng khả năng đặc thù của LDAP.

## 2. Cây thư mục LDAP và khái niệm context

Một directory LDAP là không gian tên phân cấp. Mỗi entry có **distinguished name (DN)** và tập thuộc tính; các giá trị `objectClass` quyết định kiểu entry cùng các thuộc tính bắt buộc hoặc cho phép theo schema.

Ví dụ directory minh họa:

```text
dc=example,dc=org                     <- base DN
|
+-- ou=people                          <- organizational unit
|   +-- uid=alice                      <- entry người dùng
|   +-- uid=bob
|
+-- ou=groups                          <- nhánh nhóm
    +-- cn=developers

DN đầy đủ của Alice:
uid=alice,ou=people,dc=example,dc=org
```

LDAP DN và Java package là hai khái niệm khác nhau. `ou=people` là **tên tương đối trong directory**; `com.example.identity.ldap` là package chứa lớp Java. Nếu `ContextSource` của Spring LDAP đã có base DN `dc=example,dc=org`, các DN được truyền vào nhiều thao tác `LdapTemplate` thường **tương đối với base** đó; ví dụ `uid=alice,ou=people`.

Trong JNDI, **context** là một điểm nhìn vào một namespace. Nó cung cấp các thao tác tra cứu tên và điều hướng; **directory context** bổ sung khả năng truy vấn entry theo thuộc tính. Không phải mỗi đối tượng context là một entry Java có tất cả field được ánh xạ sẵn.

```text
Spring Service
   |
   +-- Spring Data LDAP Repository  ---> ODM entity (@Entry / @Attribute)
   |                                      |
   +-- LdapTemplate ----------------------+  (mức API Spring LDAP)
           |
           v
     ContextSource / LdapContextSource
           |
           v
     JNDI DirContext  --(có thể là)--> LdapContext
           |
           +-- lookup / search / bind / modify / delete
           |
           v
     LDAP provider -> LDAP/LDAPS server -> entry/attributes
```

Tên `LdapContextSource` dễ gây nhầm: đây là **lớp Spring LDAP để tạo context JNDI**, không phải interface `javax.naming.ldap.LdapContext`.

## 3. Hệ phân cấp Context → DirContext → LdapContext

Các interface quan trọng nằm trong thư viện Java SE:

```java
javax.naming.Context
    ^
    |
javax.naming.directory.DirContext
    ^
    |
javax.naming.ldap.LdapContext
```

`DirContext` **extends** `Context`; `LdapContext` **extends** `DirContext`. Vì thế, một `LdapContext` có toàn bộ thao tác của `DirContext`, nhưng một `DirContext` không nhất thiết cung cấp các API điều khiển đặc thù LDAP.

| Kiểu | Package | Vai trò chính | Một số thao tác |
| --- | --- | --- | --- |
| `Context` | `javax.naming` | Tra cứu và quản lý tên trong namespace. | `lookup`, `bind`, `rebind`, `unbind`, `list`, `close`. |
| `DirContext` | `javax.naming.directory` | Thao tác entry và các tập thuộc tính trong dịch vụ thư mục. | `getAttributes`, `modifyAttributes`, `search`, `createSubcontext`. |
| `LdapContext` | `javax.naming.ldap` | Khả năng riêng LDAPv3, đặc biệt controls/extended operations. | `setRequestControls`, `getResponseControls`, `extendedOperation`, `reconnect`. |
| `ContextSource` | `org.springframework.ldap.core` | Giao diện Spring cung cấp context JNDI cho các thao tác. | `getReadOnlyContext`, `getReadWriteContext`. |
| `LdapContextSource` | `org.springframework.ldap.core.support` | Cấu hình địa chỉ, base DN và thông tin bind để cung cấp context. | Thiết lập URL, base DN, bind credentials. |
| `DirContextOperations` | `org.springframework.ldap.core` | Giao diện Spring biểu diễn một entry và các thay đổi thuộc tính ở mức thuận tiện. | `getStringAttribute`, `setAttributeValue`, `getDn`. |

### 3.1. DirContext làm được gì?

Các thao tác `DirContext` có hai hình thức tên: chuỗi `String` hoặc `javax.naming.Name`. Dùng `Name`/`LdapName` giúp biểu diễn từng thành phần RDN chính xác và tránh việc nối thủ công các ký tự đặc biệt.

| Thao tác JNDI | Ý nghĩa | Tương ứng trong LDAP |
| --- | --- | --- |
| `getAttributes(dn)` | Đọc toàn bộ hoặc một số thuộc tính của entry. | LDAP search/read entry. |
| `search(base, filter, controls)` | Tìm các entry khớp filter trong phạm vi đã chỉ định. | LDAP Search. |
| `createSubcontext(dn, attributes)` | Tạo entry mới có bộ thuộc tính ban đầu. | LDAP Add. |
| `modifyAttributes(dn, changes)` | Thêm, thay thế hoặc xóa các giá trị thuộc tính. | LDAP Modify. |
| `destroySubcontext(dn)` | Xóa entry con (theo giới hạn của server). | LDAP Delete. |
| `rename(oldDn, newDn)` | Đổi tên RDN hoặc di chuyển entry nếu server cho phép. | LDAP Modify DN. |
| `getSchema(...)` | Truy cập schema do provider/server cung cấp. | LDAP schema-related operations. |

Một số phương thức của `Context` như `bind`/`unbind` cũng có thể dùng với LDAP provider, nhưng khi thêm entry kèm thuộc tính, `createSubcontext(dn, attributes)` diễn đạt trực tiếp ý định hơn.

### 3.2. LdapContext bổ sung gì?

`LdapContext` dùng khi ứng dụng cần tính năng LDAPv3 vượt khỏi thao tác tìm kiếm/sửa thuộc tính cơ bản:

- `setRequestControls(Control[] controls)`: gửi **request controls** kèm LDAP operation, ví dụ paged results.
- `getRequestControls()`: đọc bộ controls hiện được cài cho context.
- `getResponseControls()`: đọc **response controls** gắn với operation gần nhất, nếu server trả về.
- `extendedOperation(ExtendedRequest request)`: gửi LDAP extended operation. StartTLS là một trường hợp, nhưng phải triển khai luồng đàm phán TLS và xác thực chứng chỉ đúng.
- `newInstance(Control[] controls)`: tạo context mới cùng môi trường với bộ request controls riêng.
- `reconnect(Control[] controls)`: thiết lập lại kết nối/xác thực theo contract của provider.

Ví dụ đọc response controls trong **JNDI thuần**, khi provider thực sự cung cấp `LdapContext`:

```java
import javax.naming.directory.DirContext;
import javax.naming.ldap.Control;
import javax.naming.ldap.LdapContext;

void inspectResponseControls(DirContext context) throws Exception {
    if (context instanceof LdapContext ldapContext) {
        Control[] controls = ldapContext.getResponseControls();
        if (controls != null) {
            for (Control control : controls) {
                System.out.println("Control OID: " + control.getID());
            }
        }
    }
}
```

Không ép kiểu vô điều kiện từ `DirContext` sang `LdapContext`: contract `DirContext` không bảo đảm interface mở rộng này. Một số request/response controls phụ thuộc vào LDAP server, LDAP provider và từng operation; không có response control là tình huống hợp lệ.

> `LdapContext` trong JNDI **không tự động làm kết nối an toàn**. Bảo mật đến từ cấu hình LDAPS hoặc StartTLS đúng cách, xác minh chứng chỉ và chính sách xác thực/ủy quyền của server.

## 4. Các đối tượng biểu diễn dữ liệu entry

Một LDAP entry không giống một bản ghi SQL có các cột scalar cố định. Entry có tập thuộc tính, có thể có **nhiều giá trị cho cùng tên thuộc tính**; một số thuộc tính vận hành (*operational attributes*) chỉ được trả về khi được yêu cầu phù hợp.

### 4.1. Attributes — tập hợp các Attribute

`javax.naming.directory.Attributes` là tập chứa các `Attribute` của entry. `get(String attrID)` trả về một `Attribute` hoặc `null` nếu thuộc tính đó không có. Một implementation thông dụng là `BasicAttributes`.

```java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

Attributes person = new BasicAttributes(true); // true: tên thuộc tính không phân biệt hoa/thường

Attribute objectClasses = new BasicAttribute("objectClass");
objectClasses.add("top");
objectClasses.add("person");
objectClasses.add("organizationalPerson");
objectClasses.add("inetOrgPerson");

person.put(objectClasses);
person.put("uid", "alice");
person.put("cn", "Alice Nguyen");
person.put("sn", "Nguyen");
person.put("mail", "alice@example.org");

Attribute cn = person.get("cn");
String fullName = cn == null ? null : (String) cn.get();
```

`new BasicAttributes(true)` chọn chế độ so sánh **tên attribute** không phân biệt hoa/thường trong đối tượng Java. Nó không sửa schema LDAP, không biến giá trị attribute thành case-insensitive và không quyết định quy tắc so khớp của server.

### 4.2. Attribute — một tên, có thể nhiều giá trị

`javax.naming.directory.Attribute` mô tả một tên thuộc tính và tập giá trị. Một số phương thức:

| Phương thức | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getID()` | Lấy tên thuộc tính, ví dụ `member`. | Tên không nhất thiết viết hoa/thường như trong source. |
| `size()` | Số lượng giá trị. | Có thể bằng 0. |
| `get()` | Lấy một giá trị. | Có thể ném `NamingException` khi không có giá trị. |
| `get(int index)` | Lấy giá trị ở vị trí được chỉ định. | Đừng suy luận thứ tự LDAP có ý nghĩa nếu attribute không có thứ tự. |
| `getAll()` | Nhận `NamingEnumeration<?>` của các giá trị. | Đọc đúng kiểu và giải phóng enumeration. |
| `add(Object value)` | Thêm một giá trị vào attribute trong Java. | Chưa đồng nghĩa với việc đã ghi lên LDAP server. |
| `remove(Object value)` | Bỏ một giá trị khỏi đối tượng Java. | Phải gọi thao tác modify để lưu vào directory. |

Ví dụ thuộc tính nhiều giá trị như `member` của nhóm hoặc `telephoneNumber`:

```java
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import java.util.ArrayList;
import java.util.List;

static List<String> readValues(Attribute attribute) throws Exception {
    List<String> values = new ArrayList<>();
    if (attribute == null) {
        return values;
    }

    NamingEnumeration<?> items = attribute.getAll();
    try {
        while (items.hasMore()) {
            Object value = items.next();
            if (value instanceof String text) {
                values.add(text);
            }
        }
    } finally {
        items.close();
    }
    return values;
}
```

Trong LDAP, thuộc tính có thể mang giá trị nhị phân như `byte[]` (ví dụ ảnh hoặc chứng chỉ), hoặc kiểu khác do provider cung cấp. Vì vậy, ép mọi giá trị thành `String` sẽ không an toàn. Nếu attribute **không có thứ tự**, `get(0)` không có nghĩa là “giá trị ưu tiên”.

### 4.3. SearchResult, SearchControls và ModificationItem

Ba đối tượng thường đi cùng `DirContext`:

- `SearchResult` (`javax.naming.directory`): một kết quả tìm kiếm, chứa tên tương đối, thông tin object (nếu được trả về) và `getAttributes()` của entry.
- `SearchControls`: mô tả cách tìm: `OBJECT_SCOPE`, `ONELEVEL_SCOPE` hoặc `SUBTREE_SCOPE`; các thuộc tính cần nhận, giới hạn kết quả và thời gian tìm kiếm.
- `ModificationItem`: mô tả **một thay đổi** gồm thao tác `ADD_ATTRIBUTE`, `REPLACE_ATTRIBUTE` hoặc `REMOVE_ATTRIBUTE` và đối tượng `Attribute`.

Ví dụ lựa chọn phạm vi:

```text
searchBase = "ou=people"

OBJECT_SCOPE    -> chỉ entry ou=people
ONELEVEL_SCOPE  -> các entry con trực tiếp của ou=people
SUBTREE_SCOPE   -> ou=people và mọi entry con ở các cấp bên dưới
```

Đừng nhầm `SearchControls.SUBTREE_SCOPE` với chỉ định base DN: một giá trị là **phạm vi**, giá trị còn lại là **vị trí bắt đầu** tìm kiếm.

## 5. Ví dụ JNDI thuần: đọc, tìm, tạo và cập nhật entry

Đoạn mã dưới đây minh họa trực tiếp các đối tượng JNDI. Giả sử `DirContext context` đã được tạo, bind vào LDAP server thử nghiệm và có base DN `dc=example,dc=org`. Các đường dẫn trong ví dụ là DN tương đối với base. Trong ứng dụng thật, bạn thường dùng `LdapTemplate` để tránh phải quản lý context ở từng phương thức.

### 5.1. Đọc thuộc tính của một DN

```java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;

static String readCommonName(DirContext context) throws Exception {
    Attributes attributes = context.getAttributes(
        "uid=alice,ou=people",
        new String[] { "cn", "mail" }
    );

    Attribute cn = attributes.get("cn");
    return cn == null ? null : (String) cn.get();
}
```

Để tối ưu dữ liệu, chỉ yêu cầu các attribute thực sự cần. Khi entry không có, provider thường ném `javax.naming.NameNotFoundException`; khi chỉ một thuộc tính bị thiếu, `Attributes.get("attribute")` trả `null`.

### 5.2. Tìm kiếm với SearchControls

```java
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;
import java.util.ArrayList;
import java.util.List;

static List<String> searchCommonNames(DirContext context, String surname)
        throws Exception {
    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setReturningAttributes(new String[] { "cn" });
    controls.setCountLimit(100);
    controls.setTimeLimit(5000); // giới hạn xử lý tìm kiếm phía JNDI, đơn vị ms

    NamingEnumeration<SearchResult> matches = context.search(
        "ou=people",
        "(sn={0})",
        new Object[] { surname },
        controls
    );

    List<String> names = new ArrayList<>();
    try {
        while (matches.hasMore()) {
            SearchResult result = matches.next();
            Attributes attributes = result.getAttributes();
            if (attributes.get("cn") != null) {
                names.add((String) attributes.get("cn").get());
            }
        }
    } finally {
        matches.close();
    }
    return names;
}
```

Ở đây `"(sn={0})"` đi kèm mảng tham số để provider mã hóa giá trị trong **LDAP search filter**. Không ghép trực tiếp `"(sn=" + surname + ")"` từ dữ liệu không tin cậy. `setCountLimit(100)` là giới hạn yêu cầu phía client; giới hạn của server vẫn có thể chặt hơn. `setTimeLimit` không thay thế cho **network timeout** hoặc các cấu hình timeout kết nối.

### 5.3. Tạo entry và sửa thuộc tính

```java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

static void addPerson(DirContext context) throws Exception {
    Attributes attrs = new BasicAttributes(true);
    Attribute classes = new BasicAttribute("objectClass");
    classes.add("top");
    classes.add("person");
    classes.add("organizationalPerson");
    classes.add("inetOrgPerson");

    attrs.put(classes);
    attrs.put("uid", "carol");
    attrs.put("cn", "Carol Nguyen");
    attrs.put("sn", "Nguyen"); // bắt buộc với objectClass person
    attrs.put("mail", "carol@example.org");

    DirContext created = context.createSubcontext(
        "uid=carol,ou=people", attrs
    );
    try {
        // Entry đã được tạo. Không cần gọi save() thêm.
    } finally {
        created.close();
    }
}

static void changeMail(DirContext context) throws Exception {
    ModificationItem[] modifications = {
        new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", "carol.new@example.org")
        )
    };
    context.modifyAttributes("uid=carol,ou=people", modifications);
}
```

`DirContext.ADD_ATTRIBUTE` thêm giá trị/attribute, `REPLACE_ATTRIBUTE` thay thế và `REMOVE_ATTRIBUTE` xóa theo ngữ nghĩa LDAP Modify. Những thao tác này chịu ràng buộc từ schema, objectClass và ACL: tạo entry thiếu `cn`/`sn` hoặc sửa thuộc tính không cho phép sẽ bị server từ chối.

**Quản lý tài nguyên JNDI:** đoạn ví dụ nhận sẵn `DirContext` để dễ tập trung vào API. Nơi **tạo context** phải đóng context bằng `close()` trong `finally`; `DirContext` không được mặc định coi là tài nguyên `AutoCloseable` dùng trong `try-with-resources`. `NamingEnumeration` của thao tác search cũng nên được đóng sau khi duyệt.

## 6. Spring LDAP đóng gói các thao tác JNDI như thế nào?

Trong Spring, `ContextSource` tạo `DirContext` với URL, base DN và danh tính bind được cấu hình. `LdapTemplate` lấy context cho một operation, thực hiện thao tác JNDI, chuyển phần lớn exception JNDI thành ngoại lệ unchecked của Spring LDAP, rồi quản lý đóng/giải phóng context theo cơ chế của framework.

```text
Repository / Service
       |
       +--> LdapTemplate.search / lookup / bind / modify
                |
                +--> ContextSource.getReadOnlyContext()
                |           hoặc getReadWriteContext()
                |
                +--> JNDI DirContext
                |
                +--> AttributesMapper / ContextMapper
                |
                +--> Giải phóng context; chuyển đổi NamingException
```

`getReadOnlyContext()` và `getReadWriteContext()` mô tả **mục đích truy cập** của phía Spring. Quyền đọc/ghi thực sự do tài khoản bind và ACL của LDAP server quyết định; gọi `getReadWriteContext()` không tự nâng quyền.

### 6.1. Đọc bằng AttributesMapper

`AttributesMapper<T>` nhận `javax.naming.directory.Attributes` và biến thành đối tượng Java đơn giản. Ví dụ Spring Boot đã tự cấu hình `LdapTemplate`, với base DN là `dc=example,dc=org`:

```java
package com.example.identity;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class PeopleSearchService {

    private final LdapTemplate ldapTemplate;

    public PeopleSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> bySurname(String surname) {
        return ldapTemplate.search(
            LdapQueryBuilder.query()
                .base("ou=people")
                .where("sn").is(surname),
            (AttributesMapper<PersonSummary>) attrs -> {
                String cn = (String) attrs.get("cn").get();
                var mail = attrs.get("mail");
                String email = mail == null ? null : (String) mail.get();
                return new PersonSummary(cn, email);
            }
        );
    }

    public record PersonSummary(String commonName, String email) {}
}
```

Trong lambda, `AttributesMapper` chỉ cần đọc các thuộc tính cần thiết; entity ODM chưa bắt buộc. Ví dụ giả định entry người dùng hợp lệ có `cn` và `mail` nếu có thì là một giá trị đọc được dưới dạng chuỗi. Khi làm việc với thuộc tính nhiều giá trị hoặc nhị phân, hãy đọc bằng enumeration và xử lý đúng kiểu.

`LdapQueryBuilder` tạo điều kiện tìm kiếm và mã hóa tham số filter giúp tránh đưa input thẳng vào cú pháp truy vấn. `LdapTemplate.search(...)` trả danh sách: không có entry khớp filter thường là danh sách rỗng, không phải lỗi. Nếu base DN truy vấn không tồn tại, vẫn có thể phát sinh exception.

### 6.2. Khi cần DN và metadata: ContextMapper

`ContextMapper<T>` nhận đối tượng context của entry (Spring LDAP thường biểu diễn bằng `DirContextOperations`/`DirContextAdapter`). Nó phù hợp khi cần DN, xử lý thông tin ngữ cảnh hoặc dùng cơ chế theo dõi thay đổi thuộc tính.

So sánh:

| Tiêu chí | `AttributesMapper<T>` | `ContextMapper<T>` |
| --- | --- | --- |
| Dữ liệu đầu vào | `Attributes` của entry. | Context của entry, có thể truy cập DN và thuộc tính. |
| Trường hợp thường dùng | DTO gọn, chỉ lấy vài thuộc tính. | Cần DN và thông tin ở mức entry. |
| Độ phức tạp | Thấp, tập trung vào dữ liệu. | Linh hoạt hơn, cần hiểu cách Spring tạo context adapter. |
| Sửa entry | Không phải cơ chế chính để lưu thay đổi. | Có thể phối hợp `DirContextOperations` và `LdapTemplate.modifyAttributes`. |

Ví dụ lấy DN rồi sửa `mail` qua `DirContextOperations`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

static void updateMail(LdapTemplate template, String uid, String newMail) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid)
        .build();

    DirContextOperations entry = template.lookupContext(dn);
    entry.setAttributeValue("mail", newMail);
    template.modifyAttributes(entry);
}
```

`DirContextOperations` ở đây **không phải** `javax.naming.directory.DirContext`. Nó là abstraction Spring cho dữ liệu entry, giúp đọc thuộc tính và ghi nhận những sửa đổi so với dữ liệu đã tải; `LdapTemplate.modifyAttributes(entry)` gửi các thay đổi cần thiết về directory. Khi có thay đổi DN/RDN, phải xét thao tác rename phù hợp; không thể chỉ sửa chuỗi DN như một thuộc tính thông thường.

### 6.3. Quan hệ với Spring Data LDAP Repository và ODM

Ở tầng cao hơn, entity thường khai báo `@Entry`, `@Id` và `@Attribute`:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class LdapPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    @DnAttribute(value = "uid", index = 0)
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public LdapPerson() {}
    // Bổ sung getters/setters cho các field trong dự án thực tế.
}
```

Repository Spring Data LDAP thao tác với `LdapPerson` thay vì tự xử lý `Attributes` ở mỗi method. Tuy nhiên, ở phía dưới framework vẫn phải chuyển entry/attribute qua các API LDAP để đọc, tìm kiếm và cập nhật. Khi schema hoặc kiểu giá trị không khớp, vấn đề có thể xuất phát từ mapping ODM **hoặc** phản hồi directory; hiểu `Attribute` và `DN` giúp tìm lỗi đúng tầng.

## 7. DN, filter và schema: ba loại quy tắc khác nhau

### 7.1. DN không phải filter

Một DN có thứ tự các **relative distinguished names** (RDN) để chỉ ra đường dẫn entry; một LDAP filter biểu diễn **điều kiện tìm kiếm**:

```text
DN đầy đủ:
uid=alice,ou=people,dc=example,dc=org

DN tương đối so với dc=example,dc=org:
uid=alice,ou=people

LDAP search filter:
(&(objectClass=inetOrgPerson)(uid=alice))
```

Với đầu vào chưa tin cậy, tạo DN bằng `LdapNameBuilder`:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", userInput)
    .build();
```

Với filter, dùng `LdapQueryBuilder` hoặc JNDI parameter placeholder:

```java
// Spring LDAP:
var filterQuery = org.springframework.ldap.query.LdapQueryBuilder
    .query()
    .base("ou=people")
    .where("uid").is(userInput);

// JNDI trực tiếp: dùng "(uid={0})" và Object[] tham số.
```

**DN escaping** và **filter escaping** tuân theo quy tắc khác nhau; một chuỗi đã escape cho filter không mặc nhiên an toàn khi nhúng vào DN. Không tự cắt/gộp DN theo dấu phẩy vì giá trị RDN có thể chứa ký tự cần escape.

### 7.2. objectClass và schema quy định dữ liệu hợp lệ

`objectClass` cũng là một `Attribute` có thể có nhiều giá trị. Khi tạo entry `inetOrgPerson`, schema LDAP thường yêu cầu các thuộc tính kế thừa, chẳng hạn `cn` và `sn` của `person`. Server có thể từ chối entry thiếu trường bắt buộc, dùng attribute không được phép, hoặc gán giá trị sai cú pháp bằng lỗi schema.

Không phải mọi directory có schema giống nhau. Đặc biệt, Active Directory và OpenLDAP có thể khác nhau về class/attribute được hỗ trợ. Hãy đọc schema thực tế của server, thay vì giả định ví dụ `inetOrgPerson` áp dụng cho tất cả.

## 8. Quản lý tài nguyên, kết nối và lỗi

### 8.1. Ai chịu trách nhiệm đóng context?

Với **JNDI thuần**:

```java
import javax.naming.Context;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import java.util.Hashtable;

static void demoConnection(String bindDn, String password) throws Exception {
    Hashtable<String, Object> env = new Hashtable<>();
    env.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
    env.put(Context.PROVIDER_URL,
            "ldaps://ldap.example.org:636/dc=example,dc=org");
    env.put(Context.SECURITY_AUTHENTICATION, "simple");
    env.put(Context.SECURITY_PRINCIPAL, bindDn);
    env.put(Context.SECURITY_CREDENTIALS, password);

    // Các thuộc tính timeout dưới đây riêng cho JNDI LDAP provider của JDK.
    env.put("com.sun.jndi.ldap.connect.timeout", "3000");
    env.put("com.sun.jndi.ldap.read.timeout", "5000");

    DirContext context = new InitialDirContext(env);
    try {
        context.getAttributes("uid=alice,ou=people",
            new String[] { "cn" });
    } finally {
        context.close();
    }
}
```

Đây là ví dụ cơ chế, sử dụng endpoint và dữ liệu giả định. Không ghi mật khẩu thực trong source/log; dùng secret manager hoặc biến môi trường và cấu hình truststore/certificate validation cho LDAPS. Nếu khởi tạo `InitialDirContext` thất bại, không có context để đóng; ngoại lệ cần được xử lý ở tầng gọi.

Với **Spring LDAP**, để `LdapTemplate` lấy/giải phóng context thông qua `ContextSource`. Tránh lưu một đối tượng `DirContext` lâu dài trong field singleton hoặc chia sẻ giữa nhiều thread: nó có trạng thái phiên và không nên mặc nhiên coi là thread-safe. Thường chỉ chia sẻ các bean cấu hình/template do Spring quản lý, không chia sẻ trực tiếp context lấy từ provider.

### 8.2. Ngoại lệ thuộc tầng nào?

| Tình huống | JNDI thường phát sinh | Spring LDAP thường phát sinh | Hướng chẩn đoán |
| --- | --- | --- | --- |
| Không tồn tại DN lookup | `javax.naming.NameNotFoundException` | `org.springframework.ldap.NameNotFoundException` | DN tương đối/base DN và entry có tồn tại. |
| Trùng DN khi tạo | `javax.naming.NameAlreadyBoundException` | `org.springframework.ldap.NameAlreadyBoundException` | Entry đã tồn tại, quy tắc duy nhất. |
| Sai bind credentials | `javax.naming.AuthenticationException` | `org.springframework.ldap.AuthenticationException` | Bind DN, secret, chính sách xác thực. |
| Không đủ quyền ghi | `javax.naming.NoPermissionException` | `org.springframework.ldap.NoPermissionException` | ACL của directory. |
| Mạng/TLS có vấn đề | `javax.naming.CommunicationException` | `org.springframework.ldap.CommunicationException` | URL, cổng, timeout, truststore. |
| Sai LDAP filter | `javax.naming.directory.InvalidSearchFilterException` | `org.springframework.ldap.InvalidSearchFilterException` | Filter syntax và escaping. |
| Schema không phù hợp | `javax.naming.directory.SchemaViolationException` | `org.springframework.ldap.SchemaViolationException` | `objectClass`, thuộc tính bắt buộc, syntax. |

Các cặp trên là những ánh xạ điển hình, không bảo đảm tất cả LDAP providers đều báo cùng lớp exception cho mọi mã lỗi. `LdapTemplate` thường chuyển các checked `javax.naming.NamingException` thành runtime exception thuộc `org.springframework.ldap`; lỗi cấu hình bean hoặc mapping entity cũng có thể xuất hiện dưới lớp exception khác.

### 8.3. Bảo mật và hiệu năng

- Ưu tiên **LDAPS hoặc StartTLS**, xác minh chứng chỉ, dùng tài khoản bind theo nguyên tắc quyền tối thiểu.
- Giới hạn phạm vi search, trả về đúng các thuộc tính cần dùng, áp dụng giới hạn số kết quả và timeout hợp lý; tránh quét cả directory khi chỉ cần một OU.
- Khi tìm kiếm rất lớn, xem xét phân trang qua LDAP controls và khả năng hỗ trợ của server. Phân trang LDAP không đồng nghĩa với phân trang kiểu SQL; sử dụng server-side paging có thể cần `LdapContext`/controls hoặc tiện ích tương ứng của Spring LDAP.
- Tránh in dữ liệu nhạy cảm: bind credentials, filter thô chứa dữ liệu cá nhân, DN đầy đủ và các thuộc tính bí mật.
- Phân biệt **không có kết quả tìm kiếm** (thường trả danh sách rỗng) với **DN lookup không tồn tại** hoặc lỗi dịch vụ. Không bắt mọi exception rồi trả `null`.

## 9. Kiểm thử qua LdapTemplate và đối chiếu với JNDI

Một integration test có giá trị phải thao tác với directory thử nghiệm có cấu trúc đã biết, ví dụ `dc=example,dc=org`, `ou=people` và entry `uid=alice` với `cn=Alice Nguyen`. Sau đó xác minh rằng `LdapTemplate` đọc attribute đúng như JNDI.

```java
import static org.assertj.core.api.Assertions.assertThat;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class LdapAttributeIT {

    @Autowired
    private LdapTemplate template;

    @Test
    void readsCommonNameFromEntry() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", "alice")
            .build();

        String cn = template.lookup(dn,
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get()
        );

        assertThat(cn).isEqualTo("Alice Nguyen");
    }
}
```

Bài test phụ thuộc vào LDAP server/embedded directory đã được tạo và seed trước; chỉ khởi động Spring context không đủ chứng minh mapping hoạt động. Nên bổ sung các ca: entry không tồn tại, thiếu attribute tùy chọn, attribute nhiều giá trị, dữ liệu nhị phân, filter có ký tự đặc biệt, ghi không đủ quyền và schema từ chối.

Khi test `LdapContext`/controls, hãy dùng LDAP server hỗ trợ tính năng tương ứng; mock đơn thuần không xác minh được server trả response controls đúng định dạng.

## 10. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `LdapContextSource` là `javax.naming.ldap.LdapContext`. | `LdapContextSource` là bean Spring tạo context; `LdapContext` là interface JNDI hỗ trợ LDAP controls. |
| `Attributes` là một `Map<String, String>`. | Mỗi `Attribute` có thể nhiều giá trị và có thể chứa kiểu nhị phân. |
| Gọi `attribute.add(value)` sẽ lập tức cập nhật LDAP. | Chỉ sửa đối tượng trong Java; cần `modifyAttributes` hoặc API Spring tương ứng. |
| `get(0)` luôn là giá trị chính. | Nhiều attribute LDAP không có thứ tự giá trị có ý nghĩa. |
| `DirContextOperations` là socket/connection JNDI. | Đây là abstraction Spring cho dữ liệu entry và các thay đổi. |
| `setSearchScope(SUBTREE_SCOPE)` đặt base DN. | Đây là phạm vi tìm dưới một base DN riêng. |
| `getReadWriteContext()` tự cấp quyền ghi. | Quyền thực tế phụ thuộc tài khoản bind và ACL của server. |
| Chỉ cần Spring context khởi động là LDAP đã kết nối tốt. | Kết nối/bind có thể chỉ thực sự diễn ra ở thao tác LDAP đầu tiên. |
| Cùng một cách escape áp dụng cho cả DN và filter. | DN và LDAP filter có hai bộ quy tắc escape khác nhau. |

## 11. Bài tập ứng dụng

1. Vẽ sơ đồ quan hệ giữa `Context`, `DirContext`, `LdapContext` và `ContextSource`. Chỉ rõ lớp nào thuộc JNDI và lớp nào thuộc Spring LDAP.
2. Viết `Attributes` mô tả entry `uid=linh,ou=people` có các object class `top`, `person`, `organizationalPerson`, `inetOrgPerson`, cùng các thuộc tính `uid`, `cn`, `sn`, `mail`. Giải thích các điều kiện schema để tạo entry thành công.
3. Với thuộc tính `member` có ba DN, viết hàm đọc toàn bộ giá trị bằng `NamingEnumeration`. Nêu vì sao `get(0)` chưa chắc là lựa chọn đúng.
4. Viết tìm kiếm JNDI sử dụng `SearchControls.ONELEVEL_SCOPE` và placeholder `(uid={0})`; đối chiếu kết quả với `LdapTemplate.search(LdapQuery, AttributesMapper)`.
5. Thử cập nhật `mail` bằng `DirContext.modifyAttributes` và `LdapTemplate.modifyAttributes(DirContextOperations)` trên directory test. So sánh quản lý context, exception và code cần viết.
6. Giải thích cách chuẩn bị LDAP server thử nghiệm để xác minh một thao tác phân trang qua LDAP controls, và lý do không thể kết luận hỗ trợ phân trang chỉ từ kết quả mock.

## 12. Tài liệu tham khảo

- [Java SE — Context API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/Context.html): giao diện namespace nền tảng của JNDI.
- [Java SE — DirContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html): thuộc tính, search và modify.
- [Java SE — LdapContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapContext.html): LDAP controls và extended operations.
- [Java SE — Attributes và Attribute API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attributes.html): mô hình attribute trong JNDI.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `ContextSource`, mapping, DN và tìm kiếm.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ODM.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): tìm kiếm và thao tác directory ở mức giao thức.
- [RFC 4514 — DN String Representation](https://www.rfc-editor.org/rfc/rfc4514) và [RFC 4515 — Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515): sự khác nhau giữa biểu diễn DN và filter.
