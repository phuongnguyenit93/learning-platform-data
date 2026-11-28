# Root DSE và thông tin khả năng của máy chủ LDAP

Khi ứng dụng **Spring Data LDAP** kết nối đến một directory, việc biết DN người dùng hoặc schema của `inetOrgPerson` chưa đủ để quyết định mọi thao tác có thể thực hiện. Directory có thể hỗ trợ phân trang LDAP, một request control để ghi có điều kiện, thao tác StartTLS hoặc những cơ chế xác thực SASL khác nhau. Thông tin để **khám phá khả năng mà máy chủ công bố** nằm ở một đối tượng đặc biệt gọi là **Root DSE** (*Root Directory-Specific Entry*).

Root DSE không phải “người dùng root”, cũng không phải OU cao nhất của một tổ chức. Nó là một **điểm truy vấn thông tin của chính LDAP server**, mang DN rỗng và những thuộc tính vận hành mô tả naming context, phiên bản giao thức, control và extension mà server nhận biết. Bài học hướng dẫn đọc Root DSE bằng lệnh `ldapsearch` và Spring LDAP `LdapTemplate`, diễn giải kết quả, rồi dùng nó như một bước kiểm tra khả năng trước khi thiết kế repository, filter, CRUD và kiểm thử tích hợp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Root DSE là gì, tại sao DN của nó là chuỗi rỗng và tại sao nó **không nằm trong dữ liệu nghiệp vụ** của directory.
- Phân biệt **Root DSE**, **naming context/suffix**, **entry gốc của một cây dữ liệu** và **subschema entry**.
- Tìm Root DSE bằng search với `base=""`, `scope=baseObject` và filter `(objectClass=*)`.
- Hiểu các thuộc tính `namingContexts`, `supportedControl`, `supportedExtension`, `supportedFeatures`, `supportedLDAPVersion`, `supportedSASLMechanisms`, `altServer` và `subschemaSubentry`.
- Xác định cách kiểm tra khả năng phân trang, StartTLS và Assertion Control bằng OID, đồng thời hiểu giới hạn của việc “server có công bố” một tính năng.
- Thiết lập một `LdapContextSource` có base rỗng để truy vấn Root DSE mà không nhầm với base DN thông thường của Spring Data LDAP.
- Viết kiểm thử tích hợp và xử lý tình huống LDAP server không công bố một thuộc tính hoặc trả kết quả khác nhau theo phiên/kết nối.

## 2. Root DSE nằm ở đâu trong mô hình LDAP?

Giả sử directory phục vụ hai miền dữ liệu:

```text
                    Root DSE
                 DN = "" (rỗng)
                  /          \
                 /            \
   dc=example,dc=org       dc=partner,dc=org
   (naming context A)      (naming context B)
          |                       |
       ou=people               ou=users
          |                       |
      uid=alice                 uid=bob
```

Sơ đồ giúp hình dung các nhánh, nhưng cần hiểu chính xác: **Root DSE không phải entry cha thông thường của các naming context trong DIT**. Theo RFC 4512, nó là một DSA-specific entry ở gốc mô hình thông tin, **nằm ngoài mọi naming context và subtree**.

| Khái niệm | DN ví dụ | Chức năng |
| --- | --- | --- |
| **Root DSE** | `""` | Mô tả các khả năng và thông tin của server LDAP. |
| **Naming context / suffix** | `dc=example,dc=org` | Gốc một vùng dữ liệu mà server cung cấp. |
| **Entry nghiệp vụ** | `uid=alice,ou=people,dc=example,dc=org` | Dữ liệu người dùng, nhóm hoặc tài nguyên được ứng dụng thao tác. |
| **Subschema entry** | DN server công bố, chẳng hạn `cn=Subschema` | Chứa định nghĩa `objectClasses` và `attributeTypes` cho vùng dữ liệu có liên quan. |

Trong Spring Boot, `spring.ldap.base=dc=example,dc=org` là **base DN của ứng dụng**, không phải Root DSE. Một repository `@Entry(base="ou=people")` tiếp tục giới hạn nhánh đối tượng Java tương ứng; nó không tự truy vấn hay ánh xạ Root DSE.

### 2.1. DN rỗng không có nghĩa tìm toàn bộ cây

Hai câu yêu cầu rất khác nhau:

```text
base = "" ; scope = baseObject ; filter = (objectClass=*)
→ Yêu cầu thông tin Root DSE.

base = "dc=example,dc=org" ; scope = subtree ; filter = (objectClass=inetOrgPerson)
→ Tìm entry người dùng trong một naming context.
```

Đặc biệt, **Root DSE không được trả như một entry trong phép tìm subtree bắt đầu từ gốc**. Muốn lấy Root DSE phải truy vấn **base object**, không dùng `SUBTREE` rồi hy vọng thấy nó trong danh sách entry nghiệp vụ.

## 3. Thuộc tính thường gặp của Root DSE

RFC 4512 quy định một số thuộc tính phục vụ discovery. Đây là **operational attributes**: chúng thường **không xuất hiện trong kết quả search mặc định nếu client không yêu cầu đích danh**.

| Thuộc tính | Giá trị chứa gì? | Dùng để làm gì? |
| --- | --- | --- |
| `namingContexts` | Một hoặc nhiều DN của naming context mà server công bố. | Khám phá các vùng dữ liệu phục vụ. |
| `supportedLDAPVersion` | Các phiên bản giao thức LDAP server nhận biết, ví dụ `3`. | Kiểm tra khả năng sử dụng LDAPv3. |
| `supportedControl` | Danh sách **OID** của LDAP request control được nhận biết. | Xác định khả năng như paged results, assertion. |
| `supportedExtension` | OID của các LDAP extended operation được nhận biết. | Kiểm tra khả năng StartTLS hoặc extension khác. |
| `supportedFeatures` | OID của các LDAP feature được công bố. | Khám phá tính năng giao thức theo RFC/vendor. |
| `supportedSASLMechanisms` | Tên cơ chế SASL như `GSSAPI` hoặc `EXTERNAL` khi phù hợp. | Lựa chọn chiến lược SASL tương thích. |
| `altServer` | URI các server LDAP thay thế, nếu được công bố. | Thông tin tham khảo khi server ưu tiên không sẵn sàng. |
| `subschemaSubentry` | DN của subschema entry liên quan tới **Root DSE**. | Bước đầu tìm hiểu schema; không đồng nghĩa với schema của mọi entry. |

**Không có nghĩa mọi thuộc tính đều phải hiện diện.** Số lượng và giá trị có thể thay đổi theo sản phẩm LDAP, cấu hình server, quyền đọc, trạng thái kết nối, thậm chí trạng thái xác thực của phiên hiện tại.

### 3.1. `namingContexts` không phải Root DSE

Ví dụ:

```ldif
dn:
namingContexts: dc=example,dc=org
namingContexts: dc=partner,dc=org
supportedLDAPVersion: 3
```

Dòng `dn:` không có ký tự sau dấu hai chấm biểu diễn **DN rỗng** của Root DSE. Hai dòng `namingContexts` chỉ công bố hai suffix; chúng **không** cho biết ứng dụng được quyền đọc cả hai, không chứng minh suffix có cùng schema hay bảo đảm cùng chính sách dữ liệu.

Không tự chọn “naming context đầu tiên” để làm `spring.ldap.base` trong ứng dụng nếu nghiệp vụ đã xác định nhánh người dùng. Một server có thể công bố nhiều naming context với mục đích rất khác nhau.

### 3.2. `supportedControl` và `supportedExtension` không giống nhau

Một **request control** bổ sung yêu cầu cho một LDAP operation, ví dụ thêm tiền điều kiện vào `Modify` hoặc xin phân trang cho `Search`. **Extended operation** là một loại thao tác LDAP riêng, chẳng hạn StartTLS.

```text
SearchRequest + Paged Results Control   → vẫn là Search.
ModifyRequest + Assertion Control       → vẫn là Modify.
StartTLS ExtendedRequest                → extended operation riêng.
```

Vì vậy cần kiểm tra đúng thuộc tính: OID phân trang/Assertion Control thuộc `supportedControl`, còn OID StartTLS thuộc `supportedExtension`.

## 4. Các OID khả năng hữu ích trong ứng dụng

OID là chuỗi định danh của tính năng giao thức. Client nên dùng hằng số hoặc bảng định nghĩa ổn định thay vì dựa vào thứ tự danh sách từ server.

| Khả năng | OID | Tìm trong Root DSE |
| --- | --- | --- |
| **Simple Paged Results Control** (RFC 2696) | `1.2.840.113556.1.4.319` | `supportedControl` |
| **Assertion Control** (RFC 4528) | `1.3.6.1.1.12` | `supportedControl` |
| **Server-Side Sort Request Control** (RFC 2891) | `1.2.840.113556.1.4.473` | `supportedControl` |
| **StartTLS** (RFC 4511) | `1.3.6.1.4.1.1466.20037` | `supportedExtension` |

Ví dụ Root DSE của một server **giả định**:

```ldif
dn:
namingContexts: dc=example,dc=org
supportedLDAPVersion: 3
supportedControl: 1.2.840.113556.1.4.319
supportedControl: 1.3.6.1.1.12
supportedExtension: 1.3.6.1.4.1.1466.20037
supportedSASLMechanisms: GSSAPI
```

Từ ví dụ đó có thể suy ra: server **công bố** khả năng sử dụng Paged Results Control và Assertion Control, đồng thời nhận biết StartTLS. **Không thể suy ra** user đã có quyền dùng mọi thao tác, schema phù hợp, cookie phân trang sẽ luôn hoạt động, hay TLS handshake sẽ thành công.

### 4.1. Vì sao không dùng `supportedSASLMechanisms` để kiểm tra simple bind?

`supportedSASLMechanisms` liệt kê **cơ chế SASL** mà server công bố; simple bind dùng DN/mật khẩu **không phải** một cơ chế SASL có tên `SIMPLE` phải xuất hiện trong danh sách đó. Nếu cần simple bind, ứng dụng phải dùng kênh TLS đã xác minh máy chủ và xử lý xác thực theo chính sách server. Nếu cần SASL GSSAPI/EXTERNAL, phải thiết kế kết nối và cơ chế xác thực phù hợp; sự hiện diện của tên trong Root DSE **chưa** có nghĩa client đã cấu hình credential đúng.

### 4.2. Khả năng “được công bố” khác với “thực thi thành công”

Nên phân biệt ba câu hỏi:

1. **Discovery:** Server có công bố OID trong Root DSE không?
2. **Protocol support:** Client có gửi đúng BER/control/extended request tương ứng không?
3. **Authorization và thực thi:** Thao tác đó có được phép và có hoạt động trên entry/scope cụ thể không?

Đối với **Assertion Control**, việc thấy `1.3.6.1.1.12` hữu ích để phát hiện tương thích, nhưng kiểm thử ghi có điều kiện vẫn phải gửi **control critical** đúng chuẩn và xác minh lỗi xung đột khi điều kiện sai. Không được bỏ qua control khi server không hỗ trợ và tiếp tục ghi vô điều kiện.

## 5. Truy vấn Root DSE bằng `ldapsearch`

Với một LDAP endpoint test/production đã bật **LDAPS** và chứng chỉ được xác minh, ví dụ:

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -b "" -s base "(objectClass=*)" \
  namingContexts supportedLDAPVersion supportedControl \
  supportedExtension supportedFeatures supportedSASLMechanisms \
  altServer subschemaSubentry
```

Giải thích:

- `-b ""`: search base là **chuỗi DN rỗng** (Root DSE).
- `-s base`: chỉ xét **base object**, không tìm con hay subtree.
- `"(objectClass=*)"`: filter dùng trong thủ tục truy vấn Root DSE theo RFC 4512.
- Các tên thuộc tính cuối lệnh: yêu cầu server trả **đúng các operational attributes** cần xem.
- `-x`: dùng simple authentication; khi không có `-D`/`-W`, lệnh thường thử kết nối anonymous tùy cấu hình LDAP CLI/server.
- `-LLL`: hiển thị kết quả LDIF gọn hơn.

Nếu server không cho anonymous đọc Root DSE, có thể dùng tài khoản **chỉ đọc và có quyền phù hợp** trên kênh TLS:

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=services,dc=example,dc=org" -W \
  -b "" -s base "(objectClass=*)" \
  namingContexts supportedControl supportedExtension supportedLDAPVersion
```

`-W` yêu cầu nhập mật khẩu tương tác. Không đưa mật khẩu vào URL, file script được commit hoặc tham số command line `-w` theo dạng rõ. Trong môi trường yêu cầu StartTLS, phải **nâng cấp TLS và xác minh chứng chỉ trước khi gửi password** (ví dụ OpenLDAP CLI có tùy chọn `-ZZ` yêu cầu StartTLS bắt buộc).

### 5.1. Tại sao `ldapsearch -b "" -s sub` không thay thế được?

Root DSE là một đối tượng đặc biệt. Theo RFC 4512, **nó không thuộc tập kết quả của subtree search bắt đầu tại gốc**. Hãy sử dụng chính xác `-s base` khi muốn đọc thuộc tính Root DSE.

### 5.2. Vì sao lệnh chỉ yêu cầu `*` có thể không hiện thông tin?

`namingContexts`, `supportedControl` và các trường khả năng là **operational attributes**. Trong LDAP, `*` thông thường yêu cầu các thuộc tính người dùng; các thuộc tính vận hành cần được **yêu cầu theo tên**. Một số client/server hỗ trợ selector `+` để lấy operational attributes (RFC 3673), nhưng không nên mặc định mọi directory hỗ trợ và trả toàn bộ metadata.

Nếu output chỉ có `dn:` hoặc rất ít thông tin, hãy kiểm tra **danh sách thuộc tính được yêu cầu, ACL và phiên kết nối** trước khi kết luận server không có khả năng nào.

## 6. Root DSE và Spring Data LDAP: điểm dễ sai về base DN

Giả sử Spring Boot cấu hình:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Khi đó `LdapTemplate` thông thường sử dụng `ContextSource` với **base `dc=example,dc=org`**. Code sau **không nhất thiết truy vấn Root DSE**:

```java
// Dễ nhầm: base("") ở đây tương đối với base của ContextSource.
ldapTemplate.search("", "(objectClass=*)", controls, mapper);
```

Trong cấu hình này, `base("")` thường được hiểu là **chính context base**, tức `dc=example,dc=org`. Đó là một entry dữ liệu, không phải DN rỗng ở mức LDAP server.

Để đọc Root DSE, cách rõ ràng là tạo một **ContextSource riêng có base rỗng** và dùng một `LdapTemplate` dành cho việc khám phá server. Các lời gọi repository ODM thông thường vẫn nên dùng context có base nghiệp vụ.

### 6.1. Cấu hình một Root DSE ContextSource riêng

Ví dụ hai bean **riêng** dành cho việc đọc thông tin server. Nếu ứng dụng đã có bean `ContextSource` chính, phải kiểm tra cách Spring Boot chọn bean chính vì việc tự khai báo một `ContextSource` có thể ảnh hưởng auto-configuration; đặt tên/`@Qualifier` rõ ràng và có thể dùng `@Primary` có chủ đích với context phục vụ repository.

```java
package com.example.directory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class RootDseConfiguration {
    @Bean("rootDseContextSource")
    public LdapContextSource rootDseContextSource(
            @Value("${app.ldap.root-url}") String url,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);       // Ví dụ ldaps://ldap.example.org:636
        source.setBase("");       // Bắt buộc: không gắn suffix nghiệp vụ.
        source.setUserDn(bindDn); // DN đầy đủ của service account.
        source.setPassword(password);
        return source;
    }

    @Bean("rootDseLdapTemplate")
    public LdapTemplate rootDseLdapTemplate(
            @Qualifier("rootDseContextSource") LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

Ở đây `app.ldap.*` là **các property ví dụ do ứng dụng tự định nghĩa**, không phải tên property mặc định của Spring Boot. Cần cấu hình chúng bằng secret/config management. Kênh LDAPS vẫn phải được JVM xác minh CA và hostname. Bean `rootDseLdapTemplate` chỉ phục vụ discovery; không thay thế `LdapTemplate` cho CRUD hoặc repository đang có.

### 6.2. Lớp dữ liệu trả về

Một snapshot nhỏ ghi lại khả năng thực sự được **công bố**:

```java
package com.example.directory;

import java.util.Set;

public record RootDseSnapshot(
        Set<String> namingContexts,
        Set<String> supportedControls,
        Set<String> supportedExtensions,
        Set<String> supportedLdapVersions,
        Set<String> supportedSaslMechanisms,
        String subschemaDn
) {
    public boolean announcesPagedResults() {
        return supportedControls.contains("1.2.840.113556.1.4.319");
    }

    public boolean announcesAssertionControl() {
        return supportedControls.contains("1.3.6.1.1.12");
    }

    public boolean announcesStartTls() {
        return supportedExtensions.contains("1.3.6.1.4.1.1466.20037");
    }
}
```

Những phương thức `announces...` cố ý dùng từ **announces** (*công bố*), thay vì `canDefinitelyUse...`. Điều này tránh suy diễn quyền/hiệu lực của thao tác chỉ từ dữ liệu Root DSE.

### 6.3. Dùng `LdapTemplate` với `OBJECT_SCOPE`

`RootDseReader` chỉ yêu cầu những attribute thực sự cần và xử lý trường thiếu:

```java
package com.example.directory;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class RootDseReader {
    private final LdapTemplate template;

    public RootDseReader(
            @Qualifier("rootDseLdapTemplate") LdapTemplate template) {
        this.template = template;
    }

    public RootDseSnapshot read() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.OBJECT_SCOPE);
        controls.setReturningAttributes(new String[] {
                "namingContexts",
                "supportedControl",
                "supportedExtension",
                "supportedLDAPVersion",
                "supportedSASLMechanisms",
                "subschemaSubentry"
        });

        List<RootDseSnapshot> rows = template.search(
                "", "(objectClass=*)", controls,
                (AttributesMapper<RootDseSnapshot>) attrs ->
                        new RootDseSnapshot(
                                values(attrs, "namingContexts"),
                                values(attrs, "supportedControl"),
                                values(attrs, "supportedExtension"),
                                values(attrs, "supportedLDAPVersion"),
                                values(attrs, "supportedSASLMechanisms"),
                                first(attrs, "subschemaSubentry")));

        if (rows.size() != 1) {
            throw new IllegalStateException(
                    "Root DSE không trả đúng một entry; kiểm tra base và ACL");
        }
        return rows.get(0);
    }

    private static Set<String> values(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        if (attr == null) {
            return Set.of();
        }
        Set<String> values = new LinkedHashSet<>();
        NamingEnumeration<?> all = attr.getAll();
        try {
            while (all.hasMore()) {
                values.add(String.valueOf(all.next()));
            }
        } finally {
            all.close();
        }
        return Set.copyOf(values);
    }

    private static String first(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        return attr == null || attr.size() == 0
                ? null : String.valueOf(attr.get());
    }
}
```

Các lớp code là những tệp Java **minh họa tách biệt** (`RootDseConfiguration.java`, `RootDseSnapshot.java` và `RootDseReader.java`). Không đặt nhiều kiểu `public` vào cùng một tệp Java. Import không sử dụng trong ví dụ thực tế nên được IDE loại bỏ khi tích hợp.

Tại sao dùng `SearchControls.OBJECT_SCOPE`?

- Root DSE chỉ được truy vấn ở **base object**; không cần `ONELEVEL`/`SUBTREE`.
- `setReturningAttributes(...)` yêu cầu các operational attribute **theo tên**.
- Filter `(objectClass=*)` là **literal cố định** được RFC 4512 nêu cho truy vấn Root DSE. Không dùng `where("objectClass").is("*")` để dựng nó: API equality sẽ escape dấu sao như dữ liệu literal, không còn là presence filter.
- `values(...)` đọc được các thuộc tính **đa giá trị** như `supportedControl`; chỉ lấy `attr.get()` một lần sẽ bỏ sót OID.
- Trường vắng mặt trở thành tập rỗng/`null`; điều đó có nghĩa **không quan sát được qua truy vấn này**, không chắc chắn là server hoàn toàn không hỗ trợ.

## 7. Ứng dụng Root DSE trong quyết định kỹ thuật

Đọc Root DSE có ích khi khởi động hoặc chẩn đoán, nhưng quyết định cuối cùng phải kết hợp **hợp đồng API, quyền và kiểm thử thực tế**.

### 7.1. Phân trang LDAP

Một endpoint cần duyệt nhiều người dùng có thể kiểm tra:

```java
RootDseSnapshot caps = rootDseReader.read();
if (!caps.announcesPagedResults()) {
    // Ghi nhận thiếu khả năng công bố; dùng thiết kế khác hoặc báo không hỗ trợ.
}
```

`Simple Paged Results Control` có OID `1.2.840.113556.1.4.319`, nhưng việc có OID **không tự kích hoạt paging**. Client còn phải gửi control đúng chuẩn, quản lý cookie và xử lý giới hạn server. Spring Data LDAP repository cũng không nên bị xem là có paging giống Spring Data JPA chỉ vì server công bố OID.

### 7.2. Ghi có điều kiện với Assertion Control

Khi nghiệp vụ yêu cầu cập nhật entry **chỉ nếu phiên bản chưa đổi**, có thể kiểm tra trước server có công bố `1.3.6.1.1.12` (RFC 4528). Sau đó, thao tác `Modify` cần được gửi **kèm request control critical** và assertion filter phù hợp, để server kiểm tra điều kiện **nguyên tử cùng thao tác ghi**.

Nếu server không hỗ trợ control bắt buộc hoặc kết quả thử nghiệm không xác nhận được cơ chế bảo vệ, ứng dụng phải **dừng tính năng ghi có điều kiện**, không bỏ control rồi ghi vô điều kiện. Root DSE chỉ là bước discovery, không thay thế kiểm thử cạnh tranh hai writer.

### 7.3. StartTLS và xác thực

OID `1.3.6.1.4.1.1466.20037` trong `supportedExtension` cho biết server nhận biết **StartTLS Extended Operation**. Điều này **không bảo đảm** TLS handshake thành công trên endpoint/kết nối hiện tại: vẫn phải xác minh certificate, trust chain và hostname.

Nếu ứng dụng dùng LDAP simple bind, mật khẩu chỉ được gửi **sau khi TLS đã thiết lập và xác minh**. Với `ldaps://`, TLS bắt đầu ngay từ kết nối; với `ldap://` và StartTLS, phải nâng cấp bắt buộc **trước bind**. Không dùng việc Root DSE công bố StartTLS để cho phép fallback xuống plaintext.

### 7.4. Lựa chọn naming context và schema

`namingContexts` cho biết các suffix được server công bố. Nếu ứng dụng quản lý `ou=people,dc=example,dc=org`, cần xác nhận suffix `dc=example,dc=org` phù hợp với directory mục tiêu, rồi cấu hình `spring.ldap.base` theo nghiệp vụ.

`subschemaSubentry` trong Root DSE, **nếu có**, chỉ ra subschema entry cho **Root DSE**; RFC 4512 cảnh báo **không giả định** schema đó cũng điều khiển các entry dữ liệu khác. Muốn tìm schema thật sự áp dụng cho Alice, cần dùng quy trình subschema discovery theo đúng entry/naming context và quyền đọc; sau đó đọc định nghĩa `objectClasses`/`attributeTypes` ở entry schema tương ứng.

## 8. Root DSE có thể khác nhau giữa các server và giữa các phiên

Root DSE là dữ liệu **đặc thù từng server** (*DSA-specific*). Trong hệ thống có load balancer, replica, nhiều directory provider hoặc nhiều cổng dịch vụ, hai connection có thể nhìn thấy tập khả năng khác nhau.

Ví dụ:

```text
ldap-1.example.org → supportedControl có Paged Results + Assertion
ldap-2.example.org → supportedControl chỉ có Paged Results
```

Nếu client truy vấn Root DSE trên server 1 rồi request update đến server 2, không thể mặc nhiên cho rằng Assertion Control hoạt động như trên server 1. Hãy:

1. Kiểm tra khả năng trên **endpoint/cụm máy chủ thực tế mà ứng dụng sẽ sử dụng**.
2. Giữ **criticality** đúng với tính năng cần thiết; không biến discovery thành lý do bỏ qua kiểm tra.
3. Thiết kế connection routing/pool phù hợp nếu một operation yêu cầu khả năng có trên một nhóm server.
4. Kiểm thử failover và tình huống một replica/server thay đổi phiên bản.
5. Cân nhắc thời gian hiệu lực của cache khả năng; không giả định dữ liệu Root DSE bất biến suốt vòng đời ứng dụng.

Theo RFC 4512, một số thông tin còn phụ thuộc **session**. Ví dụ cơ chế SASL `EXTERNAL` có thể chỉ được công bố sau khi client đã thiết lập danh tính ở tầng dưới như TLS client certificate. Vì vậy, **không nhìn thấy một cơ chế** trong một lần search không nhất thiết chứng minh nó không tồn tại trong mọi hoàn cảnh.

## 9. Bảo mật khi khám phá khả năng của server

Root DSE thường được dùng để chẩn đoán, nhưng nó **không phải endpoint cấu hình dành cho mọi người dùng ứng dụng**.

- **Dùng kết nối bảo mật** khi truy vấn cùng credential dịch vụ, ưu tiên LDAPS hoặc StartTLS bắt buộc và xác minh certificate.
- **Tối thiểu hóa quyền:** tài khoản chỉ cần đọc các thuộc tính phù hợp; không sử dụng quyền quản trị directory để thực hiện mỗi lần discovery nếu không cần.
- **Hạn chế dữ liệu lộ ra ngoài:** không đưa nguyên Root DSE, danh sách server thay thế, naming contexts nội bộ hay thông tin vendor/config nhạy cảm vào REST response công khai.
- **Không dùng Root DSE để cấp quyền:** một naming context được công bố không đồng nghĩa caller được đọc tất cả DN trong đó. Quyền vẫn do ACL và authorization của ứng dụng quyết định.
- **Chặn lỗi thông minh:** khi thiếu quyền đọc Root DSE, có thể ghi chẩn đoán ở log kỹ thuật an toàn hoặc cấu hình cố định theo hạ tầng; không “tự phát hiện bằng cách thử mọi LDAP DN”.
- **Không tin dữ liệu server mù quáng:** hostname/URI từ `altServer` là dữ liệu do server công bố, không tự trở thành endpoint tin cậy để client gửi mật khẩu. Chỉ kết nối tới endpoint đã được chính sách DNS/TLS/allowlist cho phép.

Root DSE được thiết kế để **cung cấp thông tin**, không phải một bảng cấu hình mà ứng dụng CRUD tùy ý sửa. Mọi thao tác quản trị đặc biệt với Root DSE/schema phải thuộc quy trình quản trị directory được kiểm soát, không nằm trong service truy vấn người dùng.

## 10. Kiểm thử tích hợp cho Root DSE

Unit test trên `RootDseSnapshot` có thể kiểm tra ánh xạ OID, nhưng chỉ **integration test trên LDAP server** mới xác nhận Root DSE được trả về đúng ở base rỗng và với ACL/kết nối thật.

Một test có thể dùng directory test cấu hình biết trước: suffix `dc=example,dc=org`, LDAPv3, TLS hợp lệ và cho phép tài khoản test đọc Root DSE.

```java
package com.example.directory;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class RootDseReaderIT {
    @Autowired RootDseReader reader;

    @Test
    void discoversNamingContextAndLdapVersion() {
        RootDseSnapshot root = reader.read();

        // Kỳ vọng này chỉ dành cho directory fixture công bố các giá trị.
        assertTrue(root.namingContexts().contains("dc=example,dc=org"));
        assertTrue(root.supportedLdapVersions().contains("3"));
    }
}
```

Giả định của test phải được ghi rõ: nếu directory test/provider không công bố `namingContexts` hoặc `supportedLDAPVersion` cho tài khoản hiện tại, không nên kết luận phần mềm đọc Root DSE sai chỉ vì một thuộc tính bị giới hạn quyền. Trước tiên hãy xác minh output bằng `ldapsearch` **cùng endpoint và cùng tài khoản**.

### 10.1. Những trường hợp nên kiểm thử thêm

| Trường hợp | Mục đích |
| --- | --- |
| `base=""` và scope `OBJECT_SCOPE` | Khẳng định đang truy vấn Root DSE, không phải entry suffix. |
| `ContextSource` có base nghiệp vụ | Phát hiện sai sót khi dùng lại `LdapTemplate` của repository. |
| `supportedControl` có nhiều OID | Bảo đảm đọc **tất cả giá trị** của thuộc tính đa giá trị. |
| Thuộc tính không được công bố | Mapper xử lý `null`/tập rỗng, không `NullPointerException`. |
| Anonymous và authenticated session | Xác nhận khác biệt do ACL/session nếu có. |
| Endpoint không hỗ trợ một control | Tính năng bắt buộc phải fail closed, không fallback bỏ control. |
| LDAPS certificate sai | Connection thất bại trước thao tác có credential. |
| Hai replica với khả năng khác nhau | Kiểm tra logic cache/routing, không dùng metadata của server A để suy ra server B. |

Không chạy thao tác ghi thử với control trên directory production. Có thể kiểm tra Root DSE ở production theo quyền được cấp, còn integration test ghi/xóa nên chạy trên directory riêng.

## 11. Lỗi thường gặp và hướng chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `base("")` trả entry `dc=example,...` | `ContextSource` đang có `spring.ldap.base` không rỗng. | Tạo context riêng `base=""` cho Root DSE hoặc dùng JNDI gắn trực tiếp server root. |
| Tìm subtree từ `""` không có Root DSE | Root DSE không thuộc subtree theo RFC 4512. | Search scope `OBJECT_SCOPE`/`-s base`. |
| Output chỉ có `dn:` | Không yêu cầu đúng operational attributes hoặc ACL giới hạn. | Liệt kê tên `namingContexts`, `supportedControl`,... rõ ràng. |
| `supportedControl` chỉ đọc được một OID | Mapper dùng `Attribute.get()` thay vì `getAll()`. | Đọc toàn bộ thuộc tính đa giá trị. |
| Không thấy `subschemaSubentry` | Server không công bố hoặc ACL/session khác; cũng có thể không có. | Dùng subschema discovery phù hợp với entry thật, không phỏng đoán DN schema. |
| Root DSE có OID paging nhưng code paging lỗi | Có OID chưa phải gửi đúng control/cookie/size và quyền. | Kiểm tra request và response control, giới hạn server, xử lý lỗi. |
| Root DSE có StartTLS nhưng handshake fail | CA/hostname/truststore không hợp lệ. | Cấu hình TLS đúng; không fallback plaintext. |
| Không thấy `EXTERNAL` trong SASL list | Tùy session, chưa có TLS client identity hoặc ACL. | Kiểm tra session phù hợp và chính sách xác thực. |
| Server sau load balancer có kết quả khác nhau | Request đi tới các backend có tính năng/cấu hình khác nhau. | Kiểm tra từng endpoint, cache và routing. |
| Gọi Root DSE trên LDAP CLI thành công nhưng Java thất bại | JVM và CLI dùng truststore/cách bind khác nhau. | So sánh URL, CA, hostname, credential và base thật. |

## 12. Bài tập thực hành

**Bài 1.** Server công bố `namingContexts: dc=example,dc=org`. Root DSE có DN là `dc=example,dc=org` hay không?

**Đáp án:** Không. DN Root DSE là chuỗi rỗng `""`; `dc=example,dc=org` là **DN của một naming context** được server công bố.

**Bài 2.** Vì sao lệnh `ldapsearch -b "" -s sub "(objectClass=*)"` không thích hợp khi mục tiêu là Root DSE?

**Đáp án:** Root DSE không nằm trong kết quả subtree search ở gốc. Phải dùng `-s base` và yêu cầu thuộc tính vận hành theo tên.

**Bài 3.** Bạn cần biết server có công bố Paged Results Control. Cần tìm thuộc tính và OID nào?

**Đáp án:** `supportedControl` chứa OID `1.2.840.113556.1.4.319`. Sự hiện diện giúp discovery nhưng phải kiểm tra việc gửi control và phản hồi thực tế khi phân trang.

**Bài 4.** StartTLS OID thuộc `supportedExtension` hay `supportedControl`?

**Đáp án:** `supportedExtension`, với OID `1.3.6.1.4.1.1466.20037`. StartTLS là extended operation, không phải request control của Search.

**Bài 5.** `spring.ldap.base=dc=example,dc=org` và code dùng `ldapTemplate.search("",...)`. Nó có chắc đọc Root DSE không?

**Đáp án:** Không. Với context đã gắn suffix, base rỗng tương đối thường trỏ tới chính `dc=example,dc=org`. Hãy dùng một `ContextSource` riêng `base=""` để truy vấn Root DSE.

**Bài 6.** Root DSE có OID Assertion Control. Bạn có thể bỏ qua control trong request ghi nếu server báo lỗi không hỗ trợ trên một replica khác?

**Đáp án:** Không. Ghi có điều kiện bắt buộc phải fail closed; request cần Assertion Control **critical** và test đúng endpoint. Nếu server đích không hỗ trợ, không retry thành ghi vô điều kiện.

**Bài 7.** Vì sao chỉ dựa vào `subschemaSubentry` của Root DSE để kết luận schema áp dụng cho toàn bộ user entries là không đúng?

**Đáp án:** RFC 4512 nêu `subschemaSubentry` ở Root DSE (nếu có) chỉ dẫn tới subschema liên quan Root DSE; không được giả định cùng schema được áp dụng cho mọi entry dữ liệu. Cần discovery schema của entry/naming context thực tế.

## 13. Ghi nhớ

- **Root DSE** có **DN rỗng `""`**, nằm ngoài các naming context và không thuộc kết quả tìm kiếm subtree.
- Truy vấn Root DSE bằng **base object search**, filter `(objectClass=*)` và **yêu cầu rõ tên operational attributes**.
- `namingContexts` công bố các vùng dữ liệu; `supportedControl`, `supportedExtension`, `supportedFeatures`, `supportedSASLMechanisms` và `supportedLDAPVersion` mô tả khả năng server.
- OID Paged Results và Assertion thuộc **`supportedControl`**; StartTLS thuộc **`supportedExtension`**.
- Root DSE khác suffix `dc=example,...`; `LdapTemplate` có `ContextSource` base nghiệp vụ cần **context riêng base rỗng** nếu muốn đọc Root DSE.
- Dữ liệu discovery chịu ảnh hưởng của **server, session, quyền và replica**. Có OID không đồng nghĩa thao tác thành công; phải kiểm thử thực tế và fail closed khi tính năng bắt buộc không được hỗ trợ.
- Bảo vệ kết nối LDAP bằng TLS, không làm lộ metadata hạ tầng và không dùng Root DSE thay cho authorization hoặc schema validation.

## Tài liệu tham khảo

- [RFC 4512 — LDAP: Directory Information Models, mục 5.1](https://www.rfc-editor.org/rfc/rfc4512.html#section-5.1): định nghĩa Root DSE, DN rỗng, truy vấn base object và thuộc tính operational.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): Search, request controls và extended operation.
- [RFC 2696 — LDAP Simple Paged Results Control](https://www.rfc-editor.org/rfc/rfc2696.html): OID phân trang và cách vận hành.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528.html): OID và nguyên tắc ghi có điều kiện.
- [Spring LDAP — `LdapTemplate` API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): các overload `search` với `SearchControls`.
