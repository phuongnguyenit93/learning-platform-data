# Phân biệt DN, đường dẫn tệp, URL và biểu thức tìm kiếm

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập dịch vụ thư mục LDAP qua Spring Data LDAP repository hoặc `LdapTemplate`, ánh xạ các entry có DN (*Distinguished Name*), `objectClass` và schema thành đối tượng Java. Một nhầm lẫn phổ biến khi học LDAP là coi DN, đường dẫn tệp, URL và biểu thức tìm kiếm đều là những cách ghi “đường dẫn đến người dùng”. Chúng thực ra mô tả **bốn khái niệm khác nhau**, có ngữ nghĩa, quy tắc escape và API riêng.

Ví dụ cùng nói về tài khoản Lan:

```text
DN:         uid=lan,ou=people,dc=example,dc=org
File path:  /srv/ldap/backups/people.ldif
LDAP URL:   ldaps://ldap.example.org:636/uid=lan,ou=people,dc=example,dc=org
Filter:     (uid=lan)
```

**DN** xác định vị trí của entry trong cây LDAP; **file path** chỉ đến một tài nguyên trên hệ điều hành; **LDAP URL** xác định endpoint directory và có thể mang DN hoặc thông tin truy vấn; **LDAP filter** nêu điều kiện khớp thuộc tính entry. Bài này giải thích cách chọn đúng loại và cách dùng trong Spring Data LDAP.

## 1. Bốn chuỗi, bốn mục đích

| Khái niệm | Câu hỏi được trả lời | Ví dụ | API thường dùng |
|---|---|---|---|
| **DN** | Entry **nào** trong cây thư mục? | `uid=lan,ou=people,dc=example,dc=org` | `LdapTemplate.lookup`, `@Id Name` trong ODM |
| **Đường dẫn tệp** | Tệp hoặc thư mục **nào** trên máy? | `/srv/ldap/backups/people.ldif` | `java.nio.file.Path`, `Files` |
| **LDAP URL** | Kết nối đến **server nào**, truy cập DN/truy vấn nào? | `ldaps://ldap.example.org:636/...` | Cấu hình kết nối, referral, LDAP client |
| **LDAP filter** | Entry nào **thỏa điều kiện** theo thuộc tính? | `(&(objectClass=inetOrgPerson)(uid=lan))` | `LdapTemplate.search`, repository finder |

Một DN có thể nằm **bên trong LDAP URL**; một filter cũng có thể là **thành phần của LDAP URL**. Tuy nhiên, không thể hoán đổi một chuỗi DN cho tham số filter hay dùng một file path làm DN.

## 2. DN là tên phân cấp của LDAP entry

### 2.1. DN, RDN và cây thông tin thư mục

LDAP tổ chức entry thành cây (*Directory Information Tree* — DIT):

```text
dc=org
└── dc=example
    ├── ou=people
    │   ├── uid=lan
    │   └── uid=binh
    └── ou=groups
        └── cn=developers
```

DN đầy đủ của entry Lan:

```text
uid=lan,ou=people,dc=example,dc=org
```

DN gồm các thành phần **RDN** (*Relative Distinguished Name*), từ cụ thể nhất ở bên trái đến ancestor ở bên phải. Ở đây `uid=lan` là RDN của Lan trong container `ou=people`. RDN có thể đa trị, ví dụ `cn=Lan+uid=lan`; không nên tách mọi DN bằng dấu `=` hoặc giả định chỉ có một cặp tên/giá trị trong mỗi RDN.

Một LDAP entry minh họa:

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
```

Trong LDIF, `dn:` xác định tên entry, còn `uid`, `cn`, `sn`, `mail` là các thuộc tính. `objectClass` và schema kiểm soát những thuộc tính được phép hoặc bắt buộc; chẳng hạn lớp `person` yêu cầu `cn` và `sn`. DN không mặc nhiên xuất hiện như một thuộc tính tên `dn` khi client đọc `Attributes`.

DN nói **entry ở đâu**, chưa nói client đang kết nối đến server nào hay cần tìm những entry khác theo điều kiện nào.

### 2.2. DN đầy đủ và DN tương đối với base

Khi `LdapContextSource` cấu hình:

```text
ContextSource.base = dc=example,dc=org
```

thì cùng một entry có nhiều cách biểu diễn tùy mốc:

| Mốc so sánh | DN |
|---|---|
| Đầy đủ trong LDAP namespace | `uid=lan,ou=people,dc=example,dc=org` |
| Tương đối với `dc=example,dc=org` | `uid=lan,ou=people` |
| Tương đối với `ou=people,dc=example,dc=org` | `uid=lan` |

Nhiều API `LdapTemplate` nhận **DN tương đối với base của context**. Ví dụ base `dc=example,dc=org` thì `lookup("uid=lan,ou=people")` tìm đúng entry. Nếu truyền toàn bộ DN như một tên tương đối, ứng dụng có thể ghép lặp hậu tố:

```text
uid=lan,ou=people,dc=example,dc=org,dc=example,dc=org
```

Phải quy định ở từng ranh giới API: tham số là **DN đầy đủ** hay **DN tương đối với base cụ thể nào**. DN rỗng `""` trong LDAP protocol có thể tham chiếu root DSE, nhưng `lookup("")` trong context đã cấu hình base có thể chỉ tới chính entry tại base đó; đây là hai ngữ cảnh khác nhau.

### 2.3. Escape trong DN

Theo RFC 4514, dấu phẩy phân cách RDN, dấu cộng có thể nối các cặp thuộc tính/giá trị trong một RDN đa trị. Ký tự đặc biệt bên trong **giá trị** cần được escape:

```text
Giá trị uid: lan,team
DN đúng:     uid=lan\,team,ou=people,dc=example,dc=org
DN sai:      uid=lan,team,ou=people,dc=example,dc=org
```

Không tạo DN từ dữ liệu người dùng bằng chuỗi `"uid=" + uid + ",ou=people"`. Dùng API hiểu cấu trúc tên:

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "lan,team";
Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid)
        .build();

LdapName parsed = new LdapName(relativeDn.toString());
System.out.println(parsed); // uid=lan\,team,ou=people
```

`LdapNameBuilder.add("uid", uid)` coi `uid` là **giá trị một RDN**, không phải một đoạn cú pháp mà đầu vào có thể chèn thêm RDN. `LdapName` và `Rdn` cũng hữu ích khi parse, chuẩn hóa và kiểm tra DN.

## 3. File path là tên tài nguyên trên hệ điều hành

Ví dụ:

```text
Linux:   /srv/ldap/export/users.ldif
Windows: C:\data\ldap\users.ldif
```

Đây là **đường dẫn tệp**, không phải tên người dùng trong LDAP directory. Một file `users.ldif` có thể chứa hàng trăm entry, mỗi entry có DN riêng. Thư mục `/srv/ldap/export` chỉ là nơi tệp được lưu, không phải LDAP naming context.

| Thuộc tính | LDAP DN | Đường dẫn tệp |
|---|---|---|
| Cấu trúc phân cấp | RDN, thường phân cách bằng dấu phẩy | Đoạn tên thư mục/tệp, phân cách bởi `/` hoặc `\` |
| Thành phần | `uid=lan`, `ou=people` | `export`, `users.ldif` |
| Parser Java | `LdapName`, `LdapNameBuilder` | `Path`, `Files` |
| Tài nguyên | Entry trong directory | File hoặc directory trên đĩa |
| Quy tắc truy cập | LDAP bind, ACL, schema, base DN | Quyền filesystem, hệ điều hành |

Đoạn Java dưới đây chỉ đọc một tệp LDIF:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path ldifFile = Path.of("data", "ldap", "users.ldif");
String ldifText = Files.readString(ldifFile, StandardCharsets.UTF_8);
```

`Path.of("uid=lan,ou=people,dc=example,dc=org")` tạo ra **một path** theo luật hệ điều hành. Nó không biến chuỗi đó thành LDAP DN. Ngược lại, `LdapTemplate.lookup` không mở một tệp `.ldif` trên ổ đĩa.

Không thể suy ra đường dẫn filesystem `/org/example/people/lan` từ DN `uid=lan,ou=people,dc=example,dc=org` để truy cập LDAP. Cây ASCII chỉ là cách minh họa quan hệ cha/con, không phải giao thức địa chỉ file.

## 4. LDAP URL xác định endpoint và có thể mang truy vấn

URL có scheme, host, port và các thành phần tùy theo scheme. LDAP URL được định nghĩa trong RFC 4516, khác với URL HTTP:

```text
ldaps://ldap.example.org:636/uid=lan,ou=people,dc=example,dc=org
ldap://ldap.example.org:389/ou=people,dc=example,dc=org?uid,cn?sub?%28uid%3Dlan%29
```

Định dạng tổng quát:

```text
ldap://host:port/baseDN?attributes?scope?filter?extensions
```

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Scheme | `ldap` hoặc `ldaps` | Loại kết nối; `ldaps` dùng TLS ngay khi kết nối |
| Host/port | `ldap.example.org:389` | Endpoint dịch vụ LDAP |
| DN trong phần path | `ou=people,dc=example,dc=org` | Entry hoặc base DN được tham chiếu |
| Attributes | `uid,cn` | Thuộc tính yêu cầu lấy |
| Scope | `sub` | Mức tìm kiếm `base`, `one`, `sub` |
| Filter | `%28uid%3Dlan%29` | Dạng percent-encoded của `(uid=lan)` |
| Extensions | Có thể không có | Mở rộng LDAP URL theo RFC 4516 |

Phần sau `/` trong URL là **DN theo cú pháp LDAP**, không phải thư mục vật lý trên server. Một URL có thể trỏ tới server và DN mà không có filter; cũng có thể mô tả cả một truy vấn LDAP.

### 4.1. Ba lớp escape: DN, filter và URL

Khi lồng dữ liệu vào URL, phải phân biệt rõ từng lớp:

| Đang biểu diễn... | Cơ chế escape | Ví dụ |
|---|---|---|
| Giá trị RDN trong **DN** | RFC 4514 | `uid=lan\,team,ou=people` |
| Giá trị thuộc tính trong **LDAP filter** | RFC 4515 | `(uid=lan\2ateam)` với giá trị `lan*team` |
| Thành phần trong **LDAP URL** | URI percent-encoding/RFC 4516 | `(uid=lan)` thành `%28uid%3Dlan%29` |

Ví dụ nếu `uid` là chuỗi literal `lan*team`:

```text
DN:      uid=lan*team,ou=people,dc=example,dc=org
Filter:  (uid=lan\2ateam)
URL:     ldap://ldap.example.org/ou=people,dc=example,dc=org??sub?%28uid%3Dlan%5C2ateam%29
```

Trong DN, dấu `*` ở ví dụ là ký tự thường. Trong filter, dấu `*` không được escape sẽ có thể trở thành **wildcard** của substring filter; `\2a` mới mang ý nghĩa dấu sao literal. Khi đưa filter vào LDAP URL, ký tự `\` của `\2a` được percent-encode tiếp thành `%5C`.

**Không dùng DN escaping để bảo vệ LDAP filter**, và không dùng filter escaping để tạo URI. Nếu tự tạo LDAP URL, hãy dùng parser/encoder hiểu LDAP URL; `java.net.URI` xử lý URI cơ bản nhưng không tự hiểu ngữ nghĩa LDAP DN hay filter.

### 4.2. LDAP URL trong referral

Khi LDAP server trả `referral` hoặc `SearchResultReference`, nó có thể đề nghị:

```text
ldap://ldap-b.example.org/ou=partners,dc=example,dc=org
```

Đây là **địa chỉ server và vùng tên cần tiếp tục**, không phải một LDAP entry đã được trả về. JNDI có chính sách `ignore`, `follow`, `throw` để quyết định cách xử lý referral. Mở kết nối theo URL phải kiểm tra host, port, TLS, quyền và giới hạn vòng lặp; URL được server đề nghị không mặc nhiên đáng tin.

## 5. LDAP filter là điều kiện tìm kiếm trên thuộc tính

LDAP filter có cú pháp RFC 4515, ví dụ:

```text
(uid=lan)
(objectClass=inetOrgPerson)
(&(objectClass=inetOrgPerson)(uid=lan))
(|(sn=Nguyen)(sn=Tran))
(!(mail=*))
(cn=Lan*)
```

| Filter | Ý nghĩa |
|---|---|
| `(uid=lan)` | `uid` bằng `lan` |
| `(&(objectClass=inetOrgPerson)(uid=lan))` | AND: khớp cả hai điều kiện |
| `(|(sn=Nguyen)(sn=Tran))` | OR: khớp một trong hai họ |
| `(!(mail=*))` | NOT: không có thuộc tính `mail` |
| `(cn=Lan*)` | `cn` bắt đầu bằng `Lan` |
| `(mail=*)` | Có thuộc tính `mail` |

Filter **không tự xác định** server hay vùng tên để tìm. Cần kết hợp:

```text
Server:       ldap.example.org
Context base: dc=example,dc=org
Search base:  ou=people
Scope:        ONELEVEL
Filter:       (uid=lan)
```

Sơ đồ:

```text
       ContextSource (server + base DN)
                      |
                      v
          Search base + search scope
                      |
                      v
             LDAP filter
                      |
                      v
    SearchResultEntry (DN + Attributes)
                      |
                      v
           Java DTO hoặc ODM entity
```

`(uid=lan)` có thể trả **nhiều entry**, ví dụ:

```text
uid=lan,ou=employees,dc=example,dc=org
uid=lan,ou=contractors,dc=example,dc=org
```

Chỉ DN đầy đủ mới nêu một vị trí trong namespace đang xét. Ngay cả filter đúng cũng có thể trả danh sách rỗng khi search base/scope không bao phủ entry hoặc tài khoản bind không có quyền đọc.

### 5.1. Escape filter an toàn

Theo RFC 4515, những ký tự sau cần được mã hóa khi chúng là **giá trị literal**:

| Ký tự | Dạng escape trong filter |
|---|---|
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| NUL | `\00` |

Không nối filter trực tiếp với input:

```java
// Sai: input có thể thay đổi cấu trúc/logic LDAP filter.
String rawFilter = "(uid=" + userInput + ")";
```

Sử dụng API xây filter an toàn:

```java
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery ldapQuery = query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(userInput);
```

`where(...).is(userInput)` xử lý dữ liệu người dùng như giá trị so sánh, thay vì cho phép đầu vào chèn cú pháp filter. Nếu nghiệp vụ thực sự hỗ trợ tìm kiếm theo tiền tố, cần mô tả và triển khai riêng substring search thay vì vô tình tạo wildcard.

## 6. Dùng đúng kiểu trong Spring Data LDAP

Giả sử cấu hình `application.yml`:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Ở đây `urls` là endpoint LDAP; `base` là DN dùng làm mốc; `username` là định danh bind (ví dụ bằng DN đầy đủ); mật khẩu lấy qua biến môi trường hoặc hệ thống quản lý bí mật, không ghi giá trị thật vào nguồn.

### 6.1. Khi biết DN: dùng lookup

**`PersonDirectory.java`**

```java
package com.example.ldap;

import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.InvalidAttributeValueException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String loadFullNameByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        // DN tương đối với ContextSource.base.
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        AttributesMapper<String> mapper = attrs -> {
            Attribute cn = attrs.get("cn");
            if (cn == null || cn.size() == 0) {
                throw new InvalidAttributeValueException("Thiếu cn");
            }
            return (String) cn.get();
        };

        return ldapTemplate.lookup(relativeDn, mapper);
    }
}
```

`lookup` lấy **một DN xác định**. `relativeDn` chứa `uid=lan,ou=people`, không gắn hậu tố `dc=example,dc=org` do base của context đã bao gồm phần đó.

### 6.2. Khi chỉ biết điều kiện: dùng search

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery ldapQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn")
        .countLimit(100)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(userInput);

AttributesMapper<String> mapper = attrs -> (String) attrs.get("cn").get();
List<String> names = ldapTemplate.search(ldapQuery, mapper);
```

- `base("ou=people")` là **DN tương đối** với base kết nối.
- `SearchScope.SUBTREE` bao gồm cả entry ở base và mọi cấp con.
- `where(...)` cùng `and(...)` xây dựng **filter**.
- `attributes(...)` quyết định thuộc tính được yêu cầu trả về, không phải điều kiện lọc.
- Kết quả `List<String>` có thể rỗng hoặc nhiều phần tử; không mang ý nghĩa lookup một DN.

Với Spring Data LDAP repository, `@Id` của entity ODM biểu diễn DN bằng `Name`. `findById(Name dn)` định danh entry theo DN; `findByUid(String uid)` là **finder theo thuộc tính**, có thể tìm nhiều entry theo phạm vi của repository. Không nhầm hai phương thức.

### 6.3. Khi cần đọc file LDIF

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path ldif = Path.of("data", "ldap", "users.ldif");
String content = Files.readString(ldif, StandardCharsets.UTF_8);
```

Đây chỉ là đọc một file văn bản. Nó không gửi LDAP query, không bind LDAP server và không ghi entry. Muốn nhập dữ liệu LDIF vào directory phải có công cụ hoặc logic import riêng, tôn trọng DN, schema và quyền LDAP.

## 7. Tình huống chọn đúng chuỗi và lỗi phổ biến

| Nhu cầu | Loại cần dùng | Ví dụ |
|---|---|---|
| Đọc entry cụ thể | DN | `uid=lan,ou=people` (với context base `dc=example,dc=org`) |
| Tìm người dùng theo họ | Filter + search base/scope | `(sn=Nguyen)` |
| Chọn LDAP server để kết nối | URL | `ldaps://ldap.example.org:636` |
| Chỉ đến file backup LDIF | File path | `/srv/ldap/backups/users.ldif` |
| LDAP referral sang một vùng khác | LDAP URL | `ldap://ldap-b.example.org/ou=partners,dc=example,dc=org` |
| Tìm giá trị `uid` có dấu sao thật | Filter đã escape | `(uid=lan\2ateam)` |
| Phân biệt hai `uid` giống nhau ở hai nhánh | DN đầy đủ hoặc khóa ổn định theo directory | `uid=lan,ou=employees,...` so với `uid=lan,ou=contractors,...` |

**Sai 1 — Dùng DN làm filter:**

```text
Sai:   filter = uid=lan,ou=people,dc=example,dc=org
Đúng:  filter = (uid=lan)
       base   = ou=people,dc=example,dc=org
```

Filter cần cú pháp riêng trong ngoặc và dùng trên thuộc tính. Nếu đã biết chính xác DN, dùng `lookup` sẽ rõ ý định hơn.

**Sai 2 — Dùng file path hoặc LDAP URL trong lookup:**

```text
Sai:   lookup("/org/example/people/lan")
Sai:   lookup("ldap://ldap.example.org/uid=lan,ou=people,...")
Đúng:  lookup("uid=lan,ou=people") // base kết nối: dc=example,dc=org
```

Địa chỉ kết nối được cấu hình trong `ContextSource`. Tham số `lookup` là tên entry tương đối với base của context, không nhận file path/LDAP URL.

**Sai 3 — Dùng escape của DN cho filter:**

```text
Giá trị uid: lan*team
DN:          uid=lan*team,ou=people
Filter:      (uid=lan\2ateam)
```

Filter escape khác DN escape. Nối filter từ input có thể gây LDAP filter injection hoặc sai kết quả dù DN vẫn hợp lệ.

**Sai 4 — Nhầm base DN với filesystem path:** `spring.ldap.base = dc=example,dc=org` là mốc tên logic trong directory, không phải chỗ lưu dữ liệu của server trên đĩa.

**Sai 5 — Dùng HTTP client với `ldap://`:** `ldap://` và `ldaps://` là scheme LDAP, không phải HTTP/HTTPS. Dùng JNDI, Spring LDAP hoặc LDAP client tương ứng. Với referral, xác minh server đích và bảo mật trước khi kết nối.

## 8. Kiểm thử cú pháp, escaping và truy vấn

Quy tắc dựng DN có thể kiểm thử độc lập với server. Ví dụ JUnit 5:

**`DistinguishedNameTest.java`**

```java
package com.example.ldap;

import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DistinguishedNameTest {
    @Test
    void commaInUidRemainsOneRdnValue() throws Exception {
        Name name = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "lan,team")
                .build();

        LdapName parsed = new LdapName(name.toString());
        assertEquals(2, parsed.size());
        assertEquals("uid", parsed.getRdn(parsed.size() - 1).getType());
        assertEquals("lan,team",
                parsed.getRdn(parsed.size() - 1).getValue());
    }
}
```

Kiểm thử này xác nhận giá trị có dấu phẩy là **một RDN**, không làm thêm cấp trong cây. Nó không chứng minh server có entry tương ứng. Với filter, cần kiểm tra giá trị chứa `*`, `(`, `)`, `\` được API builder escape đúng; khi kiểm thử bằng directory mẫu cần bảo đảm đầu vào không làm nới rộng điều kiện tìm kiếm.

Để kiểm thử tích hợp:

1. Khởi tạo LDAP test directory với `dc=example,dc=org`, `ou=people` và entry `uid=lan,ou=people,dc=example,dc=org`.
2. Đặt `ContextSource.base = dc=example,dc=org` rồi `lookup("uid=lan,ou=people")`; kiểm tra `cn`.
3. `search(base("ou=people"), scope ONELEVEL, filter "(uid=lan)")` phải trả cùng entry.
4. Với một `uid` có dấu phẩy hoặc dấu sao (nếu schema cho phép), thử `LdapNameBuilder`/`LdapQueryBuilder` và xác minh không phát sinh nhầm RDN hoặc wildcard.
5. Thay base kết nối thành `ou=people,dc=example,dc=org`, rồi thử `lookup("uid=lan")`; cách biểu diễn DN tương đối phải thay đổi đúng.
6. Trong topology có referral, kiểm tra LDAP URL của đích, quyền, chứng chỉ TLS và chế độ theo referral; không coi referral là kết quả tìm kiếm thông thường.

Một filter trả danh sách rỗng chưa chắc là filter sai: còn có thể do base/scope, quyền truy cập, schema hoặc entry thực sự không tồn tại.

## 9. Câu hỏi tự đánh giá

1. Trong các chuỗi `uid=lan,ou=people,dc=example,dc=org`, `/data/users.ldif`, `ldaps://ldap.example.org:636/...`, `(uid=lan)`, chuỗi nào định danh LDAP entry?
2. Vì sao `(uid=lan)` có thể trả nhiều entry nhưng một DN đầy đủ xác định một vị trí trong namespace?
3. Với `ContextSource.base = dc=example,dc=org`, cần truyền gì vào `LdapTemplate.lookup` để tìm Lan?
4. Dấu phẩy trong `uid=lan\,team` khác dấu `/` ở file path như thế nào?
5. Dấu `*` có ý nghĩa khác nhau thế nào giữa DN và filter?
6. LDAP URL còn mang thông tin gì ngoài DN? Khi gặp URL trong referral phải xác minh điều gì?
7. Khi nào dùng `Path`, `LdapNameBuilder`, và `LdapQueryBuilder`?

**Ghi nhớ:** **DN là tên entry**, **file path là đường dẫn dữ liệu trên đĩa**, **LDAP URL là địa chỉ dịch vụ có thể kèm DN/filter**, và **LDAP filter là điều kiện tìm kiếm theo thuộc tính**. Trong Spring Data LDAP, hãy chọn đúng API, thống nhất base DN, escape ở đúng lớp cú pháp và bảo vệ kết nối LDAP theo chính sách TLS/quyền truy cập.

### Tài liệu tham khảo

- IETF [RFC 4512 — Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, DN, RDN, DIT.
- IETF [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cú pháp và escape DN.
- IETF [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter và escape giá trị.
- IETF [RFC 4516 — LDAP URLs](https://www.rfc-editor.org/rfc/rfc4516): DN, attributes, scope và filter trong URL.
- Oracle Java SE: [`LdapName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html), [`Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html).
- Spring LDAP: [`LdapNameBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html), [`LdapQueryBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html), [`LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html).
