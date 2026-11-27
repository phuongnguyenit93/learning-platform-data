# DirContext, InitialDirContext và giao diện JNDI

Khi ứng dụng Java cần đọc hoặc thay đổi một entry trong thư mục LDAP, nó phải gửi những thao tác như *lookup*, *search*, *create* hoặc *modify* đến máy chủ. **JNDI** (*Java Naming and Directory Interface*) là bộ API chuẩn của Java cho việc truy cập các dịch vụ đặt tên và thư mục. Trong những ứng dụng dùng **Spring LDAP**, JNDI vẫn là lớp nền quan trọng: Spring cung cấp `ContextSource`, `LdapTemplate`, `LdapClient` và các cơ chế ánh xạ để giảm phần mã lặp khi làm việc với LDAP.

Bài này tập trung vào **`DirContext`, `InitialDirContext` và các giao diện liên quan của JNDI**: chúng nằm ở đâu trong kiến trúc, cách sử dụng chúng với LDAP, trách nhiệm quản lý tài nguyên và vì sao Spring LDAP xây dựng các abstraction ở phía trên. Ví dụ sử dụng Java và dịch vụ LDAP giả định tại `ldaps://ldap.example.org:636`; mọi DN, tài khoản và mật khẩu đều chỉ để minh họa.

Sau bài học, bạn có thể:

- Phân biệt JNDI, LDAP, `Context`, `DirContext`, `LdapContext` và các lớp khởi tạo tương ứng.
- Thiết lập `InitialDirContext`, kết nối LDAP qua TLS và quản lý việc đóng context.
- Đọc thuộc tính, tìm kiếm entry bằng filter có tham số, tạo và sửa entry thông qua JNDI.
- Hiểu vai trò của `Attributes`, `Attribute`, `SearchControls`, `NamingEnumeration` và các ngoại lệ `NamingException`.
- Giải thích cách `ContextSource` và `LdapTemplate` của Spring LDAP sử dụng những khái niệm này.

## 1. JNDI là gì và liên quan thế nào đến LDAP?

**JNDI** là API của Java để tìm và thao tác trên các đối tượng trong *naming service* hoặc *directory service*. **LDAP** (*Lightweight Directory Access Protocol*) là giao thức mạng cho việc truy cập thư mục. Hai khái niệm này ở hai tầng khác nhau:

| Khía cạnh | JNDI | LDAP |
| --- | --- | --- |
| Bản chất | Giao diện lập trình Java và cơ chế tìm nhà cung cấp dịch vụ | Giao thức trao đổi với directory server |
| Phạm vi | Naming, binding, lookup; mở rộng cho directory attributes và search | Entry, DN, schema, filter, bind, search, modify, add/delete |
| Cách dùng | Các interface như `Context` và `DirContext` | LDAP server hỗ trợ các operation của giao thức |
| Quan hệ | LDAP provider triển khai JNDI và ánh xạ lời gọi Java sang giao thức LDAP | Không phụ thuộc riêng vào Java hoặc JNDI |

Luồng xử lý khái quát:

```text
Ứng dụng Java
    │
    ├── JNDI: DirContext / InitialDirContext
    │             │
    │             └── LDAP service provider của Java
    │                            │
    │                            └── LDAP server
    │
    └── Spring LDAP: LdapTemplate / LdapClient
                          │
                          └── ContextSource
                                 │
                                 └── JNDI DirContext
                                        │
                                        └── LDAP server
```

Điều quan trọng là **`DirContext` là interface**, không phải tên một kết nối cụ thể. `InitialDirContext` là lớp khởi tạo một context ban đầu và tìm nhà cung cấp dịch vụ theo cấu hình môi trường. LDAP provider chịu trách nhiệm xử lý lời gọi bằng giao thức LDAP.

Từ Java 9 trở đi, các API JNDI nằm trong module chuẩn `java.naming`; tên package vẫn là `javax.naming.*` và `javax.naming.directory.*`. Việc project dùng Jakarta EE không có nghĩa các import JNDI này tự động đổi thành `jakarta.naming.*`.

## 2. Các interface và lớp quan trọng

### Quan hệ giữa các API

```text
javax.naming.Context                       (interface)
    └── javax.naming.directory.DirContext   (interface)
            └── javax.naming.ldap.LdapContext (interface)

javax.naming.InitialContext                (class)
    └── javax.naming.directory.InitialDirContext (class)
            └── javax.naming.ldap.InitialLdapContext (class)
```

| Thành phần | Vai trò chính | Ví dụ thao tác |
| --- | --- | --- |
| `Context` | Đặt tên, tìm và quản lý binding | `lookup`, `bind`, `rebind`, `unbind`, `rename`, `list` |
| `DirContext` | Mở rộng `Context` để thao tác thuộc tính thư mục và tìm kiếm | `getAttributes`, `search`, `modifyAttributes`, `createSubcontext` |
| `LdapContext` | Mở rộng `DirContext` cho các tính năng LDAP cụ thể | `extendedOperation`, `setRequestControls`, `getResponseControls` |
| `InitialContext` | Tạo naming context ban đầu từ môi trường cấu hình | `new InitialContext(env)` |
| `InitialDirContext` | Tạo directory context ban đầu, phục vụ các operation của `DirContext` | `new InitialDirContext(env)` |
| `InitialLdapContext` | Cung cấp context ban đầu có khả năng xử lý LDAP controls/extended operations | `new InitialLdapContext(env, null)` |

Có thể nhớ ngắn gọn: **`Context` xử lý tên**, **`DirContext` thêm thuộc tính và truy vấn thư mục**, còn **`LdapContext` thêm các khả năng LDAP chuyên biệt**.

### Vì sao dùng `DirContext` thay vì chỉ `Context`?

`Context.lookup(name)` trả đối tượng gắn với một tên theo ngữ nghĩa provider. Với LDAP, ứng dụng thường muốn đọc các thuộc tính cụ thể của một entry và tìm entry theo điều kiện. Những operation này nằm trên `DirContext`:

```java
// Cách làm việc với directory:
Attributes attributes = dirContext.getAttributes("uid=an,ou=people");
NamingEnumeration<SearchResult> matches = dirContext.search(
        "ou=people", "(uid=an)", searchControls);
```

Đoạn này chỉ minh họa chữ ký API; các biến được khởi tạo đầy đủ ở các ví dụ sau. `getAttributes` đọc thuộc tính của entry; `search` trả một tập kết quả cần duyệt và đóng. Không có ý nghĩa xem `lookup` và `getAttributes` là cùng một thao tác.

### Các kiểu dữ liệu đi kèm

| Kiểu | Package | Công dụng |
| --- | --- | --- |
| `Name`, `LdapName`, `Rdn` | `javax.naming`, `javax.naming.ldap` | Biểu diễn DN/RDN, giảm sai sót do ghép chuỗi |
| `Attributes`, `Attribute` | `javax.naming.directory` | Bộ thuộc tính của entry và từng thuộc tính |
| `BasicAttributes`, `BasicAttribute` | `javax.naming.directory` | Các triển khai thuận tiện để tạo giá trị thuộc tính |
| `SearchControls` | `javax.naming.directory` | Phạm vi, giới hạn kết quả, giới hạn thời gian và thuộc tính trả về |
| `SearchResult` | `javax.naming.directory` | Một kết quả tìm kiếm, gồm tên và thuộc tính |
| `NamingEnumeration<T>` | `javax.naming` | Duyệt kết quả JNDI; cần đóng sau khi dùng |
| `ModificationItem` | `javax.naming.directory` | Mô tả thay đổi thuộc tính dạng ADD, REPLACE hoặc REMOVE |
| `NamingException` và các lớp con | `javax.naming` | Lỗi tên, kết nối, xác thực, quyền truy cập và các lỗi directory khác |

## 3. Khởi tạo `InitialDirContext` để kết nối LDAP

Constructor `new InitialDirContext(env)` nhận một tập thuộc tính môi trường kiểu `Hashtable`. Với LDAP provider thường có trên JDK, các mục quan trọng gồm:

| Khóa môi trường | Ví dụ giá trị | Ý nghĩa |
| --- | --- | --- |
| `Context.INITIAL_CONTEXT_FACTORY` | `com.sun.jndi.ldap.LdapCtxFactory` | Chọn JNDI LDAP provider; chuỗi này gắn với provider trong JDK thông dụng |
| `Context.PROVIDER_URL` | `ldaps://ldap.example.org:636/dc=example,dc=org` | Địa chỉ máy chủ và DN gốc của naming context |
| `Context.SECURITY_AUTHENTICATION` | `simple` | Phương thức xác thực; `simple` dùng bind DN và mật khẩu |
| `Context.SECURITY_PRINCIPAL` | `uid=app-reader,ou=service,dc=example,dc=org` | Định danh dùng để bind |
| `Context.SECURITY_CREDENTIALS` | Giá trị bí mật cung cấp lúc chạy | Mật khẩu hoặc credential tương ứng |
| `com.sun.jndi.ldap.connect.timeout` | `5000` | Thời gian chờ kết nối tính bằng mili giây, tùy provider |
| `com.sun.jndi.ldap.read.timeout` | `5000` | Thời gian chờ phản hồi tính bằng mili giây, tùy provider |

Các khóa bắt đầu bằng `com.sun.jndi.ldap.` là **tùy chọn riêng của LDAP provider trong JDK**, không phải hằng số JNDI chuẩn áp dụng cho mọi provider.

### Ví dụ kết nối và đọc thuộc tính

Ví dụ hoàn chỉnh sau dùng LDAPS; tài khoản bind lấy từ biến môi trường, không đặt mật khẩu trực tiếp trong source code:

```java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;

public class JndiReadExample {
    public static void main(String[] args) throws NamingException {
        String bindDn = System.getenv("LDAP_BIND_DN");
        String password = System.getenv("LDAP_BIND_PASSWORD");

        if (bindDn == null || bindDn.isBlank()
                || password == null || password.isBlank()) {
            throw new IllegalStateException(
                    "Cần cấu hình LDAP_BIND_DN và LDAP_BIND_PASSWORD");
        }

        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
                "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL,
                "ldaps://ldap.example.org:636/dc=example,dc=org");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL, bindDn);
        env.put(Context.SECURITY_CREDENTIALS, password);

        // Hai tùy chọn sau thuộc LDAP provider phổ biến của JDK.
        env.put("com.sun.jndi.ldap.connect.timeout", "5000");
        env.put("com.sun.jndi.ldap.read.timeout", "5000");

        DirContext ctx = null;
        try {
            ctx = new InitialDirContext(env);

            // Tên tương đối với base dc=example,dc=org trong PROVIDER_URL.
            String relativeDn = "uid=an,ou=people";
            Attributes attrs = ctx.getAttributes(
                    relativeDn, new String[] { "cn", "mail" });

            Attribute cn = attrs.get("cn");
            Attribute mail = attrs.get("mail");

            System.out.println("cn: "
                    + (cn == null ? "(không được trả về)" : cn.get()));
            System.out.println("mail: "
                    + (mail == null ? "(không được trả về)" : mail.get()));
        } finally {
            if (ctx != null) {
                ctx.close();
            }
        }
    }
}
```

**Giải thích các bước:**

1. `INITIAL_CONTEXT_FACTORY` giúp JNDI tìm provider phù hợp.
2. `PROVIDER_URL` dùng `ldaps://` để truy cập LDAP qua TLS ngay khi kết nối. Giá trị cuối URL ở ví dụ đặt *base DN* là `dc=example,dc=org`.
3. `SECURITY_PRINCIPAL` và `SECURITY_CREDENTIALS` được gửi khi thực hiện bind theo phương thức xác thực đã chọn.
4. `new InitialDirContext(env)` tạo context mà ứng dụng sử dụng để thao tác trên thư mục.
5. `getAttributes(name, ids)` đọc những thuộc tính được yêu cầu; thuộc tính vắng mặt hoặc không được quyền đọc có thể không xuất hiện trong kết quả.
6. `ctx.close()` giải phóng tài nguyên khi kết thúc.

**Không dùng `try (DirContext ctx = ...)`:** giao diện JNDI `DirContext` **không triển khai `AutoCloseable`**, nên cần đóng bằng `finally` hoặc tiện ích quản lý tài nguyên của framework.

Việc dùng `ldaps://` chưa tự chứng minh kết nối an toàn. Ứng dụng vẫn phải cấu hình trust store tin cậy, kiểm tra chứng chỉ và hostname của máy chủ; tuyệt đối tránh thiết lập trust manager chấp nhận mọi chứng chỉ. Không gửi mật khẩu bind qua kết nối LDAP không được bảo vệ.

### Phân biệt base DN với DN của entry

Trong ví dụ trên:

```text
PROVIDER_URL = ldaps://ldap.example.org:636/dc=example,dc=org
Base DN      = dc=example,dc=org
Tên tương đối= uid=an,ou=people
DN đầy đủ    = uid=an,ou=people,dc=example,dc=org
```

Nếu cấu hình provider URL chỉ gồm host và port, ví dụ `ldaps://ldap.example.org:636`, cách truyền tên và ngữ cảnh gốc cần được điều chỉnh. **Không tự động thêm base DN hai lần**. Đối với giá trị DN chứa dấu phẩy hay ký tự đặc biệt, nên dùng `LdapName` hoặc `Rdn` thay vì nối chuỗi từ dữ liệu bên ngoài.

## 4. Đọc và biểu diễn thuộc tính với `Attributes`

`DirContext.getAttributes(...)` trả về `Attributes`: một tập các `Attribute`. Mỗi `Attribute` có ID (chẳng hạn `cn`) và có thể có nhiều giá trị nếu schema cho phép.

```java
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

// Giả sử ctx là DirContext đã kết nối và chưa đóng.
Attributes attrs = ctx.getAttributes(
        "uid=an,ou=people", new String[] { "cn", "mail" });

NamingEnumeration<? extends Attribute> all = attrs.getAll();
try {
    while (all.hasMore()) {
        Attribute attribute = all.next();
        System.out.println("Thuộc tính: " + attribute.getID());

        NamingEnumeration<?> values = attribute.getAll();
        try {
            while (values.hasMore()) {
                Object value = values.next();
                System.out.println("  Giá trị: " + value);
            }
        } finally {
            values.close();
        }
    }
} finally {
    all.close();
}
```

Khi làm việc với dữ liệu thực tế, cần lưu ý:

- `Attribute.get()` chỉ trả về một giá trị. Với thuộc tính nhiều giá trị, hãy duyệt `getAll()`.
- Kiểu giá trị trả về có thể là `String`, `byte[]` hoặc kiểu khác tùy provider và attribute type. Không ép tất cả thành chuỗi một cách mù quáng.
- LDAP schema quyết định thuộc tính bắt buộc, thuộc tính tùy chọn, cú pháp và số lượng giá trị. `BasicAttributes` không kiểm tra schema thay cho server.
- ACL và yêu cầu trả về thuộc tính có thể ảnh hưởng đến dữ liệu người đọc thấy; không suy diễn một thuộc tính chắc chắn không tồn tại chỉ vì kết quả không chứa nó.
- Không ghi dữ liệu mật như `userPassword` hoặc mã thông báo vào log chỉ để kiểm tra `Attributes`.

## 5. Tìm kiếm với `DirContext.search(...)`

LDAP search gồm **base DN**, **scope**, **filter** và danh sách thuộc tính muốn lấy. `DirContext.search(...)` phản ánh trực tiếp mô hình này.

### Phạm vi tìm kiếm trong `SearchControls`

| Hằng số | Phạm vi | Ví dụ với base `ou=people` |
| --- | --- | --- |
| `SearchControls.OBJECT_SCOPE` | Chỉ entry base | Chính entry `ou=people` |
| `SearchControls.ONELEVEL_SCOPE` | Các entry con trực tiếp | Người dùng ngay dưới `ou=people` |
| `SearchControls.SUBTREE_SCOPE` | Entry base và mọi entry hậu duệ | `ou=people` cùng toàn bộ nhánh bên dưới |

### Ví dụ tìm người dùng theo `uid`

```java
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

public class PersonSearch {
    public static void printMatches(
            DirContext ctx, String inputUid) throws Exception {

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {
                "uid", "cn", "mail"
        });
        controls.setCountLimit(100);
        controls.setTimeLimit(5000); // mili giây; giới hạn phía client

        // {0} là chỗ giữ chỗ cho giá trị uid, do JNDI xử lý trong filter.
        String filter = "(&(objectClass=inetOrgPerson)(uid={0}))";

        NamingEnumeration<SearchResult> results = ctx.search(
                "ou=people", filter, new Object[] { inputUid }, controls);

        try {
            while (results.hasMore()) {
                SearchResult result = results.next();
                Attributes attrs = result.getAttributes();
                Attribute cn = attrs.get("cn");

                System.out.println("Tên tương đối: " + result.getName());
                System.out.println("CN: " +
                        (cn == null ? "(không có)" : cn.get()));
            }
        } finally {
            results.close();
        }
    }
}
```

Đoạn ví dụ dùng context có base `dc=example,dc=org`, nên `"ou=people"` là tên tương đối. Các ví dụ `printMatches` giả định `ctx` đã được mở bằng code kết nối ở mục 3.

**Vì sao dùng `{0}`?** `DirContext.search(name, filterExpr, filterArgs, controls)` thay tham số vào filter với escaping phù hợp. Không nên ghép `inputUid` trực tiếp vào chuỗi như `"(uid=" + inputUid + ")"`, bởi các ký tự `*`, `(`, `)`, `\` và ký tự NUL có ý nghĩa riêng trong cú pháp LDAP filter.

`NamingEnumeration` có thể nhận dữ liệu theo từng đợt và phát sinh `NamingException` khi duyệt. Do đó, hãy **đóng enumeration trong `finally`**, ngay cả khi không tìm thấy entry hoặc gặp lỗi giữa chừng.

**Phân biệt kết quả tìm kiếm:** `SearchResult.getName()` thường là tên tương đối so với search base, không nhất thiết là DN đầy đủ. Một số provider hỗ trợ `getNameInNamespace()` để trả tên đầy đủ; khi xây logic xử lý tên, cần hiểu rõ ngữ nghĩa của kết quả và base hiện tại.

## 6. Tạo, sửa và xóa entry qua `DirContext`

JNDI cung cấp operation cho entry và thuộc tính, nhưng **schema, quyền truy cập và thứ tự thao tác** vẫn do LDAP server quyết định.

### Tạo entry với `createSubcontext`

`DirContext.createSubcontext(name, attrs)` tạo entry mới với tập thuộc tính ban đầu. Ví dụ sau giả định `ou=people,dc=example,dc=org` đã tồn tại và tài khoản bind có quyền ghi.

```java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;

// Giả sử ctx là DirContext đã mở và base là dc=example,dc=org.
Attributes attrs = new BasicAttributes(true);

Attribute classes = new BasicAttribute("objectClass");
classes.add("top");
classes.add("person");
classes.add("organizationalPerson");
classes.add("inetOrgPerson");
attrs.put(classes);

attrs.put("uid", "mai.nguyen");
attrs.put("cn", "Mai Nguyen");
attrs.put("sn", "Nguyen");

DirContext created = null;
try {
    created = ctx.createSubcontext("uid=mai.nguyen,ou=people", attrs);
} finally {
    if (created != null) {
        created.close();
    }
}
```

`new BasicAttributes(true)` cấu hình tìm kiếm ID thuộc tính không phân biệt chữ hoa/chữ thường ở phía đối tượng Java. Nó **không thay đổi schema**, quyền LDAP hoặc cách server so khớp giá trị. Các `objectClass` trong ví dụ thuộc một chuỗi kế thừa hợp lệ; `person` yêu cầu `cn` và `sn`. DN của entry mới cũng phải phù hợp với thuộc tính đặt tên, ở đây là `uid`.

Có thể thao tác bằng `Name` hoặc `LdapName` thay cho chuỗi DN khi giá trị RDN có ký tự đặc biệt. Không nối trực tiếp những giá trị người dùng cung cấp vào DN.

### Sửa thuộc tính bằng `modifyAttributes`

`ModificationItem` thể hiện loại thao tác thay đổi thuộc tính:

```java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

// Giả sử ctx là DirContext có quyền ghi.
ModificationItem[] changes = {
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", "mai.new@example.org"))
};

ctx.modifyAttributes("uid=mai.nguyen,ou=people", changes);
```

Ba hằng số thường gặp:

| Hằng số | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `DirContext.ADD_ATTRIBUTE` | Thêm giá trị cho thuộc tính | Có thể thất bại nếu thuộc tính `SINGLE-VALUE` hoặc trùng giá trị |
| `DirContext.REPLACE_ATTRIBUTE` | Thay tập giá trị của thuộc tính | Cần chú ý khi có nhiều giá trị và ràng buộc schema |
| `DirContext.REMOVE_ATTRIBUTE` | Xóa giá trị hoặc xóa cả thuộc tính theo yêu cầu | Không được làm mất thuộc tính `MUST` của entry |

Với thao tác trên tên và entry:

- `ctx.rename(oldName, newName)` đổi tên hoặc di chuyển entry, tùy khả năng và quy tắc server.
- `ctx.destroySubcontext(name)` xóa subcontext/entry tương ứng; hành vi với entry có con phụ thuộc provider và server, thường phải xử lý ràng buộc không được xóa parent còn con.
- `ctx.bind(...)` và `ctx.rebind(...)` xuất phát từ giao diện `Context` và có ý nghĩa liên kết đối tượng với tên. Khi muốn tạo **LDAP entry kèm thuộc tính**, `createSubcontext(name, attrs)` diễn đạt rõ ý định hơn và tránh nhầm về cách provider chuyển một Java object thành binding.

Các thao tác thay đổi dữ liệu cần quyền truy cập thích hợp. Một DN có cú pháp đúng không đồng nghĩa máy chủ cho phép ghi.

## 7. `LdapContext` và các tính năng riêng của LDAP

`DirContext` đủ cho phần lớn thao tác đọc, tìm kiếm và cập nhật entry cơ bản. Một số cơ chế LDAP chuyên sâu hơn cần **`LdapContext`**, ví dụ server/client controls hoặc extended operations.

```java
import javax.naming.Context;
import javax.naming.ldap.InitialLdapContext;
import javax.naming.ldap.LdapContext;
import java.util.Hashtable;

Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL, "ldaps://ldap.example.org:636");
// Bổ sung cấu hình xác thực phù hợp với môi trường thực tế.

LdapContext ldapCtx = null;
try {
    ldapCtx = new InitialLdapContext(env, null);
    // Tại đây có thể gọi getRequestControls(), setRequestControls(...)
    // hoặc extendedOperation(...) khi server hỗ trợ.
} finally {
    if (ldapCtx != null) {
        ldapCtx.close();
    }
}
```

**Ví dụ về khả năng cần `LdapContext`:**

- **Paged Results Control**: truy vấn một tập lớn kết quả theo trang, khi server hỗ trợ và yêu cầu được cấu hình đúng.
- **LDAP request/response controls**: đưa yêu cầu điều khiển vào operation và đọc control trả về.
- **StartTLS**: dùng extended operation để nâng cấp một kết nối `ldap://` sang TLS **trước khi gửi thông tin xác thực hoặc dữ liệu nhạy cảm**. Quy trình cần xử lý TLS session, trust store, xác thực và vòng đời kết nối đúng thứ tự.

**LDAPS và StartTLS khác nhau:** `ldaps://` thiết lập TLS từ đầu kết nối; StartTLS bắt đầu trên kết nối LDAP thông thường rồi yêu cầu nâng cấp lên TLS. Cả hai đều cần kiểm tra chứng chỉ đúng cách. Không nên bật pooling một cách máy móc trên kết nối có trạng thái bảo mật thay đổi (như StartTLS) nếu chưa hiểu chính sách lifecycle và hạn chế của provider.

## 8. `NamingException` và vòng đời tài nguyên

### Các lỗi thường gặp

Các thao tác JNDI có thể ném `javax.naming.NamingException` hoặc các lớp con. Đây là các tình huống nên phân biệt:

| Ngoại lệ JNDI | Tình huống minh họa | Hướng chẩn đoán |
| --- | --- | --- |
| `AuthenticationException` | Bind DN hoặc credential không hợp lệ | Xác minh cơ chế bind, tài khoản và mật khẩu |
| `CommunicationException` | Không kết nối được hoặc mất kết nối với server | Kiểm tra DNS, port, TLS, timeout và mạng |
| `NameNotFoundException` | DN được tra cứu không tồn tại | Kiểm tra DN tương đối/base và vị trí entry |
| `InvalidNameException` | Tên đưa vào không đúng cú pháp DN | Tạo DN bằng `LdapName`/`Rdn` hoặc builder |
| `NoPermissionException` | Không có quyền thực hiện thao tác | Đối chiếu ACL và quyền tài khoản bind |
| `SchemaViolationException` | Entry hoặc phép sửa vi phạm schema | Kiểm tra `objectClass`, `MUST`/`MAY` và attribute type |
| `SizeLimitExceededException` | Vượt giới hạn kích thước kết quả | Thu hẹp search base/filter, dùng paging khi phù hợp |
| `TimeLimitExceededException` | Truy vấn vượt giới hạn thời gian | Kiểm tra filter, index server và timeout |

Cách dịch LDAP result code sang exception có thể khác nhau theo provider và loại lỗi. Khi chẩn đoán, cần xem **exception thực tế, nguyên nhân gốc và thông tin lỗi từ LDAP server**; đừng giả định mọi thao tác không thành công đều là `NameNotFoundException`.

### Nguyên tắc quản lý tài nguyên

1. **Đóng `DirContext`/`LdapContext`** khi không còn dùng để giải phóng tài nguyên mạng.
2. **Đóng `NamingEnumeration`** từ search, liệt kê context hoặc đọc tập giá trị sau khi duyệt.
3. Đặt các thao tác đóng vào `finally`; nếu có nhiều tài nguyên, cấu trúc `finally` để không bỏ qua tài nguyên cần đóng.
4. Dùng timeout và giới hạn kết quả phù hợp; filter và scope quá rộng có thể tăng chi phí server.
5. Tránh chia sẻ bừa bãi một đối tượng context có trạng thái thay đổi giữa nhiều luồng. Việc tạo/quản lý context và pooling nên được giao cho cơ chế phù hợp thay vì tự tái sử dụng tùy tiện.

Trong Spring LDAP, `LdapTemplate` thường phụ trách tạo/lấy context từ `ContextSource` và đóng/trả context theo vòng đời thao tác. Đây là một trong những lý do dùng template thay cho việc tự viết mã `try/finally` trong mọi service.

## 9. Từ JNDI sang Spring LDAP

Để hiểu rõ vai trò từng lớp, hãy so sánh hai cách triển khai cùng một nhu cầu: tìm người dùng có `uid` cụ thể.

| Vấn đề | JNDI trực tiếp | Spring LDAP |
| --- | --- | --- |
| Tạo context | Tự tạo `InitialDirContext` với môi trường | `ContextSource` cung cấp context theo cấu hình |
| Chạy tìm kiếm | `DirContext.search(...)` | `LdapTemplate.search(...)` hoặc API client thích hợp |
| Xây filter | Filter có tham số trong `search` | `LdapQueryBuilder` hoặc filter builder |
| Duyệt kết quả | Tự quản lý `NamingEnumeration<SearchResult>` | Mapper chuyển kết quả thành đối tượng Java |
| Đóng tài nguyên | Tự đóng context và enumeration | Template quản lý tài nguyên cho lời gọi thông thường |
| Xử lý ngoại lệ | `javax.naming.NamingException` | Spring LDAP chuyển ngoại lệ JNDI sang hệ ngoại lệ của thư viện |
| Mức kiểm soát provider | Thấp tầng, gần với JNDI/LDAP | Cấu trúc nhất quán, dễ tích hợp service và kiểm thử |

### Cấu hình `ContextSource` và `LdapTemplate`

Trong ứng dụng Spring, có thể định nghĩa hai bean sau (giá trị môi trường minh họa lấy từ cấu hình ứng dụng):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {
    @Bean
    LdapContextSource contextSource(
            @Value("ldaps://ldap.example.org:636") String url,
            @Value("dc=example,dc=org") String baseDn,
            @Value("#{systemEnvironment['LDAP_BIND_DN']}") String bindDn,
            @Value("#{systemEnvironment['LDAP_BIND_PASSWORD']}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(baseDn);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Trong Spring Boot, bạn có thể dựa vào cơ chế cấu hình tự động của Spring Boot khi có dependency LDAP phù hợp; khi đó không nhất thiết phải tự khai báo cả hai bean. Bất kể cách cấu hình nào, các giá trị bí mật phải đi qua cơ chế quản lý cấu hình an toàn, hạn chế log và kiểm tra TLS đầy đủ.

### Tìm kiếm bằng `LdapTemplate`

```java
import java.util.List;
import javax.naming.directory.Attribute;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQueryBuilder;

public class PersonDirectoryService {
    private final LdapTemplate ldapTemplate;

    public PersonDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String uid) {
        return ldapTemplate.search(
                LdapQueryBuilder.query()
                        .base("ou=people")
                        .where("uid").is(uid),
                (AttributesMapper<String>) attrs -> {
                    Attribute cn = attrs.get("cn");
                    return cn == null ? null : (String) cn.get();
                });
    }
}
```

Với base DN trong `LdapContextSource` là `dc=example,dc=org`, `.base("ou=people")` xác định nhánh tương đối. `LdapQueryBuilder` dựng filter từ giá trị `uid`, còn `AttributesMapper` chuyển thuộc tính thành giá trị ứng dụng cần. `LdapTemplate` quản lý vòng đời context và chuyển đổi ngoại lệ thông thường, giúp service tập trung vào nghiệp vụ.

Tuy nhiên, Spring LDAP **không loại bỏ** khái niệm từ JNDI: dữ liệu vẫn là entry, DN, `Attributes` và search results; server vẫn có schema, quyền truy cập, TLS và giới hạn truy vấn. `DirContextAdapter` trong Spring LDAP là adapter hỗ trợ xử lý entry/thuộc tính, **khác với interface `DirContext` của JNDI**, dù tên gọi tương tự nhau.

Đối với những operation chuyên sâu cần LDAP controls hoặc extended operations, có thể dùng API thích hợp của Spring LDAP hoặc làm việc với `LdapContext` theo cơ chế framework hỗ trợ. Không nên giả định `LdapTemplate` tự động xử lý mọi tính năng đặc thù của server.

## 10. Những sai lầm dễ gặp

**Nhầm `DirContext` với `InitialDirContext`.** Đầu tiên là interface mô tả thao tác thư mục; thứ hai là lớp tạo một context ban đầu dựa trên môi trường và provider. Trong khai báo biến, ưu tiên kiểu interface `DirContext` nếu không cần tính năng cụ thể của implementation.

**Coi JNDI là LDAP.** JNDI là API chung; LDAP là giao thức. Với LDAP provider, không phải mọi hành vi của `Context` đều tương ứng trực tiếp với một LDAP operation độc lập trên mọi server.

**Ghép chuỗi DN và filter từ input.** DN escaping và LDAP filter escaping khác nhau. Dùng `LdapName`/`Rdn` để xử lý DN; dùng filter có tham số hoặc `LdapQueryBuilder` để xử lý điều kiện tìm kiếm.

**Giả định kết quả search trả DN tuyệt đối.** `SearchResult.getName()` thường tương đối với search base; phải hiểu nguồn gốc và ngữ nghĩa tên khi dùng để truy vấn tiếp.

**Quên đóng tài nguyên.** `DirContext` không phải `AutoCloseable`; `NamingEnumeration` của JNDI cũng cần đóng sau khi dùng. Bỏ qua việc đóng khiến ứng dụng dễ tiêu tốn kết nối khi hoạt động lâu.

**Gửi bind credentials qua LDAP không có TLS.** Với simple bind, mật khẩu cần được bảo vệ trong quá trình truyền. Dùng LDAPS/StartTLS kèm xác minh chứng chỉ và chính sách bảo mật của môi trường.

**Mặc định parse tên thành công nghĩa là có quyền truy cập.** `LdapName` chỉ phân tích cú pháp; quyền, schema và sự tồn tại của entry do LDAP server quyết định.

## 11. Bài thực hành có định hướng

Giả sử dịch vụ thư mục có:

```text
Base DN: dc=example,dc=org
Nhánh người dùng: ou=people,dc=example,dc=org
Entry: uid=an,ou=people,dc=example,dc=org
Thuộc tính: uid=an, cn=An Nguyen, sn=Nguyen, mail=an@example.org
```

Hãy thực hiện lần lượt trong môi trường LDAP thử nghiệm được cấp quyền:

1. Khởi tạo `InitialDirContext` với `ldaps://`, bind DN và credential lấy từ cấu hình ngoài source. Xác nhận trust store và hostname trước khi kiểm thử.
2. Dùng `getAttributes("uid=an,ou=people", new String[]{"cn","mail"})` để đọc hai thuộc tính. Ghi nhận trường hợp một thuộc tính không xuất hiện trong kết quả.
3. Chạy `search("ou=people", "(uid={0})", new Object[]{"an"}, controls)` ở scope `ONELEVEL_SCOPE`. So sánh kết quả với scope `SUBTREE_SCOPE` khi thư mục có nhánh con.
4. Thử giá trị input `a*)(uid=*)` với overload `search` có tham số; quan sát rằng giá trị được xử lý như dữ liệu tìm kiếm, thay vì trở thành cấu trúc filter do nối chuỗi.
5. Chỉ khi có quyền trên thư mục thử nghiệm, tạo entry `uid=demo,ou=people` bằng `createSubcontext`, sửa thuộc tính `mail` bằng `modifyAttributes` và đọc lại để xác minh.
6. Đóng mọi `NamingEnumeration` và `DirContext` sau thao tác; quan sát ngoại lệ JNDI khi tra một entry không tồn tại.

### Tự kiểm tra

**Câu 1.** `DirContext` và `InitialDirContext` khác nhau ở điểm nào?

**Đáp án:** `DirContext` là interface khai báo các thao tác trên dịch vụ thư mục; `InitialDirContext` là lớp khởi tạo directory context ban đầu thông qua JNDI environment và provider.

**Câu 2.** Vì sao `Context.lookup(...)` không phải lựa chọn trực tiếp nhất nếu mục tiêu là đọc `cn`, `mail` của một LDAP entry?

**Đáp án:** `lookup` có ngữ nghĩa tìm đối tượng được bind theo tên. `DirContext.getAttributes(...)` được thiết kế để đọc thuộc tính của entry và cho phép yêu cầu đúng các attribute ID cần thiết.

**Câu 3.** Tại sao phải đóng `NamingEnumeration` dù đã có `ctx.close()`?

**Đáp án:** Enumeration có thể giữ tài nguyên hoặc trạng thái tìm kiếm riêng trong thời gian duyệt. Đóng enumeration trong `finally` giải phóng tài nguyên đúng vòng đời, kể cả khi việc duyệt bị ngắt giữa chừng.

**Câu 4.** Khi xử lý một giá trị `uid` do người dùng nhập, có nên tự ghép `"(uid=" + uid + ")"` không?

**Đáp án:** Không. Giá trị chứa ký tự có ý nghĩa trong LDAP filter có thể làm sai điều kiện truy vấn. Dùng overload `search` có `filterArgs` hoặc filter builder của Spring LDAP.

**Câu 5.** Có cần sử dụng `InitialLdapContext` cho mọi truy vấn LDAP không?

**Đáp án:** Không. `InitialDirContext` và `DirContext` đã đáp ứng nhiều thao tác cơ bản. `InitialLdapContext` / `LdapContext` hữu ích khi cần LDAP controls hoặc extended operations.

## Ghi nhớ

**JNDI cung cấp ngôn ngữ lập trình Java để làm việc với dịch vụ thư mục; LDAP provider chuyển các thao tác ấy thành giao tiếp với máy chủ LDAP.** `Context` quản lý naming, `DirContext` thêm thuộc tính và tìm kiếm, `LdapContext` thêm khả năng LDAP đặc thù; `InitialDirContext` là một điểm khởi tạo cụ thể. Trong Spring LDAP, `ContextSource` quản lý cách lấy context và `LdapTemplate` giúp giảm mã lặp khi truy vấn hay thao tác entry, nhưng việc hiểu DN, schema, filter, bảo mật TLS và tài nguyên JNDI vẫn là nền tảng để triển khai đúng.
