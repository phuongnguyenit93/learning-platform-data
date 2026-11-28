# Search theo base và bộ lọc với LdapTemplate

Một thư mục LDAP của doanh nghiệp có thể chứa hàng chục nghìn entry: nhân viên, nhà thầu, nhóm, thiết bị và đơn vị tổ chức. Khi ứng dụng Java cần tìm một nhân viên theo `uid` hoặc liệt kê người dùng trong một bộ phận, câu hỏi quan trọng không chỉ là **lọc theo thuộc tính nào** mà còn là **bắt đầu tìm ở nhánh nào và đi sâu bao nhiêu cấp**.

Trong Spring LDAP, `LdapTemplate.search(...)` giải quyết thao tác đó bằng cách kết hợp **search base**, **search scope**, **LDAP filter** và **mapper**. Module `SPRING_DATA_LDAP` sử dụng Spring Data LDAP cho repository và ánh xạ entry thành Java object, nhưng cũng cần `LdapTemplate` khi muốn kiểm soát trực tiếp một truy vấn LDAP. Bài thuộc chương **LdapTemplate** và tập trung vào chủ đề **Search theo base và bộ lọc**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Đọc cây LDAP, phân biệt **DN của entry**, **base DN của kết nối** và **search base của từng truy vấn**.
- Hiểu phạm vi tìm kiếm `OBJECT`, `ONELEVEL`, `SUBTREE` và xác định tập entry tương ứng.
- Viết LDAP filter bằng equality, presence, substring, AND, OR, NOT.
- Dùng `LdapQueryBuilder` xây query có base, scope, thuộc tính cần trả về, giới hạn và filter.
- Gọi `LdapTemplate.search(query, mapper)` để chuyển dữ liệu directory thành Java DTO.
- Tránh LDAP injection khi giá trị tìm kiếm đến từ người dùng, đồng thời phân biệt escaping của filter và DN.
- Kiểm thử đúng base/scope/filter trên một LDAP directory có fixture xác định.

## 2. Tư duy: search = base + scope + filter

Trong LDAP, entry được lưu thành một cây, mỗi entry có **Distinguished Name (DN)**. Ví dụ:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   └── ou=contractors
│       └── uid=hoa
└── ou=groups
    └── cn=developers
```

DN đầy đủ của Lan:

```text
uid=lan,ou=people,dc=example,dc=org
```

DN đầy đủ của Hoa:

```text
uid=hoa,ou=contractors,ou=people,dc=example,dc=org
```

Một LDAP search được mô tả bằng các thành phần chính:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| **Base DN** | `ou=people,dc=example,dc=org` | Vị trí bắt đầu tìm trong cây. |
| **Search scope** | `ONELEVEL` | Xác định có tìm ở base, con trực tiếp hay cả cây con. |
| **LDAP filter** | `(&(objectClass=inetOrgPerson)(sn=Nguyen))` | Điều kiện entry phải thỏa. |
| **Attributes to return** | `uid`, `cn`, `mail` | Chọn thuộc tính mà client cần đọc. |
| **Count/time limits** | 100 entry, 3000 ms | Giới hạn công việc của search ở phía client/server tùy quy định. |

Có thể xem logic cơ bản là:

```text
Tập entry được xét = các entry nằm trong search base + scope
Kết quả             = những entry trong tập xét khớp LDAP filter
Dữ liệu nhận về      = các thuộc tính mà client yêu cầu và được quyền đọc
```

Search base và filter đảm nhận hai việc khác nhau. Filter `(uid=lan)` không giúp tìm Lan nếu search base chỉ nằm dưới `ou=groups`. Ngược lại, base rộng `dc=example,dc=org` với filter chỉ `(objectClass=*)` có thể gây truy vấn quá lớn và trả nhiều dữ liệu không cần thiết.

## 3. Một tập dữ liệu LDAP để thực hành

Các entry dưới đây mô tả cây ví dụ trong định dạng LDIF:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Minh Tran
sn: Tran
mail: minh@example.org

dn: ou=contractors,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: contractors

dn: uid=hoa,ou=contractors,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: hoa
cn: Hoa Nguyen
sn: Nguyen
mail: hoa@partner.example.org

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
```

Entry `inetOrgPerson` trong ví dụ có các object class kế thừa và hai thuộc tính bắt buộc của `person` là `cn`, `sn`. Schema thật có thể khác, đặc biệt khi làm việc với Active Directory hoặc schema mở rộng.

Với fixture trên, truy vấn “tìm tất cả `inetOrgPerson` có `sn=Nguyen` trong subtree `ou=people`” phải trả **Lan và Hoa**, vì Hoa nằm dưới nhánh `ou=contractors`, vẫn thuộc cây con của `ou=people`. Nếu chọn `ONELEVEL` từ `ou=people` thì chỉ Lan được trả về.

## 4. Base DN: vị trí thật và vị trí tương đối

### 4.1. DN của entry khác search base

Ba giá trị liên quan nhưng không đồng nhất:

- **Entry DN:** `uid=lan,ou=people,dc=example,dc=org`, định danh duy nhất entry trong cây.
- **Connection base DN:** ví dụ `dc=example,dc=org`, cấu hình gốc cho `ContextSource`.
- **Search base:** ví dụ `ou=people`, vị trí truy vấn tính **tương đối với connection base** khi sử dụng Spring LDAP với `ContextSource` đã đặt base.

Nếu ứng dụng Spring Boot dùng:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-directory,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

thì ví dụ:

```java
query().base("ou=people")
       .where("uid").is("lan");
```

tìm trong nhánh vật lý `ou=people,dc=example,dc=org`. Chỉ viết `base("ou=people")` khi `ContextSource` đã được cấu hình base `dc=example,dc=org`.

Nếu kết nối **không cấu hình base**, search base cần phù hợp với naming context của directory, ví dụ `ou=people,dc=example,dc=org`. Không tự động lặp `dc=example,dc=org` vào query khi `ContextSource` đã có base, vì có thể tạo DN sai.

### 4.2. Base rỗng không phải luôn là root toàn bộ directory

Trong `LdapQueryBuilder`, giá trị base mặc định là DN rỗng. Nếu `ContextSource` có base `dc=example,dc=org`, base rỗng thường trỏ tới **chính nhánh cấu hình đó**. Nó không mặc nhiên cho phép truy vấn mọi naming context trên directory.

Trong Active Directory hoặc directory có nhiều naming context, lựa chọn base đúng còn phụ thuộc root DSE, domain partition, quyền truy cập và topology. Cần dựa trên cấu hình server thật.

### 4.3. Nếu base không tồn tại?

Truy vấn dưới `ou=unknown,dc=example,dc=org` có thể nhận lỗi `noSuchObject`/`NameNotFoundException` hoặc được ứng dụng xử lý theo cấu hình Spring LDAP liên quan. Không nên giả định **mọi** search sai base đều trả danh sách rỗng. Hãy kiểm thử hành vi trong môi trường mục tiêu và ghi log để phân biệt lỗi cấu hình với việc filter không có kết quả.

## 5. Search scope quyết định độ sâu

Spring LDAP cung cấp enum `org.springframework.ldap.query.SearchScope` gồm:

| Scope | Tập entry được xét khi base = `ou=people` | Dùng khi nào |
|---|---|---|
| `OBJECT` | Chỉ entry `ou=people` | Kiểm tra một entry tại base theo filter. |
| `ONELEVEL` | Các entry **con trực tiếp**: Lan, Minh, nhánh `ou=contractors` | Liệt kê entry ngay dưới một OU, không tìm sâu hơn. |
| `SUBTREE` | Base, Lan, Minh, `ou=contractors` và Hoa | Tìm trong toàn bộ cây con. |

Sơ đồ:

```text
ou=people                    <-- OBJECT: chỉ entry này
├── uid=lan                  <-- ONELEVEL thấy
├── uid=minh                 <-- ONELEVEL thấy
└── ou=contractors           <-- ONELEVEL thấy
    └── uid=hoa              <-- SUBTREE thấy, ONELEVEL không thấy
```

Ví dụ Java:

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery directChildren = query()
    .base("ou=people")
    .searchScope(SearchScope.ONELEVEL)
    .where("objectClass").is("inetOrgPerson");

LdapQuery allDescendants = query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .where("objectClass").is("inetOrgPerson");
```

Trên dữ liệu ví dụ, `directChildren` tìm Lan và Minh; `allDescendants` tìm Lan, Minh và Hoa. Bản thân entry `ou=people` không có `objectClass=inetOrgPerson` nên không khớp filter dù `SUBTREE` có xét base.

`LdapQueryBuilder` và `LdapTemplate` sử dụng `SUBTREE` làm phạm vi mặc định trong những cấu hình phổ biến; nên **đặt rõ scope** nếu nghiệp vụ đòi hỏi tìm đúng một cấp hoặc giới hạn vùng tìm kiếm. Tìm toàn bộ subtree từ root quá rộng có thể tốn tài nguyên.

## 6. LDAP filter: biểu thức điều kiện trên entry

Filter LDAP theo RFC 4515 dùng cú pháp ngoặc. Những mẫu phổ biến:

| Filter | Ý nghĩa |
|---|---|
| `(uid=lan)` | Thuộc tính `uid` có giá trị bằng `lan`. |
| `(mail=*)` | Entry **có** thuộc tính `mail` (presence). |
| `(!(mail=*))` | Entry **không có** thuộc tính `mail`. |
| `(cn=Lan*)` | Giá trị `cn` bắt đầu bằng `Lan`. |
| `(mail=*@example.org)` | Giá trị `mail` kết thúc bằng `@example.org`. |
| `(&(objectClass=inetOrgPerson)(sn=Nguyen))` | Đồng thời thuộc lớp `inetOrgPerson` và có `sn=Nguyen`. |
| `(|(uid=lan)(uid=minh))` | Có `uid=lan` **hoặc** `uid=minh`. |
| `(!(sn=Nguyen))` | Phủ định điều kiện `sn=Nguyen`; vẫn cần để ý matching rule và thuộc tính bị thiếu. |

Dấu `&` là AND, `|` là OR, `!` là NOT. Dấu `*` có thể là ký tự đại diện hoặc phần của presence filter. Giá trị của một LDAP attribute có thể **đa trị**; một điều kiện equality có thể khớp nếu một trong các giá trị hợp lệ thỏa điều kiện.

### 6.1. Filter và schema gắn chặt nhau

Filter `(sn=Nguyen)` tìm thuộc tính LDAP `sn`, **không tìm property Java tên `surname`**. Nếu entity được ánh xạ như:

```java
@Attribute(name = "sn")
private String surname;
```

thì repository có thể khai báo `findBySurname("Nguyen")`, nhưng khi viết `LdapTemplate` filter trực tiếp, cần dùng tên LDAP attribute là `sn`.

`objectClass` giúp giới hạn loại entry, nhưng không mặc định mọi hệ LDAP dùng `inetOrgPerson`. Ví dụ Active Directory thường có schema khác. Matching rule của từng thuộc tính quyết định cách so sánh có phân biệt hoa thường, chuẩn hóa khoảng trắng và các đặc tính khác; đừng suy diễn theo quy tắc SQL.

## 7. Cấu hình LdapTemplate để tìm kiếm

Trong dự án Spring Boot dùng Spring Data LDAP, dependency Maven thường là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
```

`LdapTemplate` thuộc **Spring LDAP**, nằm bên dưới cơ chế repository của Spring Data LDAP. Với cấu hình Spring Boot phù hợp, `LdapTemplate` có thể được inject để chạy search. Nếu dự án tự khai báo `ContextSource`, có thể khởi tạo bean như sau:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class DirectoryLdapConfiguration {
    @Bean
    LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Đoạn mã chỉ minh họa phương án cấu hình thủ công. Nếu Spring Boot đã cung cấp bean `LdapTemplate`, không cần khai báo thêm trùng lặp.

Trong môi trường thực tế, nên dùng LDAPS hoặc StartTLS, xác minh certificate chain/hostname, quản lý bind password bằng secret manager và cấp quyền đọc tối thiểu. Các thuộc tính `spring.ldap.*` và cách cấu hình bean cụ thể phụ thuộc phiên bản Boot và hệ thống kết nối.

## 8. Truy vấn đầu tiên: search theo base và uid

Cách dùng `LdapTemplate.search` gọn và an toàn là xây `LdapQuery` trước, rồi truyền mapper.

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PersonSearchService {

    private final LdapTemplate ldapTemplate;

    public PersonSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> namesByUid(String uid) {
        LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.ONELEVEL)
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(uid);

        return ldapTemplate.search(
            ldapQuery,
            (AttributesMapper<String>) attrs ->
                attrs.get("cn").get().toString()
        );
    }
}
```

Trong đoạn mã:

1. `base("ou=people")` giới hạn vị trí bắt đầu, tương đối với base của `ContextSource`.
2. `ONELEVEL` chỉ tìm entry con trực tiếp của `ou=people`.
3. Filter kết hợp `(objectClass=inetOrgPerson)` và `(uid=<giá trị>)`.
4. `AttributesMapper<String>` đọc thuộc tính `cn` của entry khớp để tạo dữ liệu trả về.
5. `search(...)` trả **`List<String>`**: danh sách rỗng nếu không có kết quả, danh sách nhiều phần tử nếu có nhiều entry phù hợp.

Khi gọi `namesByUid("lan")` với fixture đã nêu, kết quả là `["Lan Nguyen"]`. Gọi `namesByUid("hoa")` trả danh sách rỗng vì Hoa nằm sâu hơn một cấp; thay `ONELEVEL` bằng `SUBTREE` sẽ bao gồm Hoa.

**Lưu ý:** ví dụ giả định các entry `inetOrgPerson` khớp đều có `cn`, điều thường đúng với schema `person`. Với directory khác hoặc dữ liệu đặc biệt, mapper cần xử lý trường hợp thuộc tính bị ẩn do quyền truy cập.

## 9. Kết hợp base, scope, filter và attributes trong một query

Một yêu cầu thực tế thường cần nhiều hơn một thuộc tính: trả mã nhân viên, tên và email của người có họ `Nguyen`.

Sử dụng DTO Java 17+:

```java
public record PersonSummary(
    String uid,
    String fullName,
    String email
) {}
```

Xây query:

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PersonDirectorySearch {

    private final LdapTemplate template;

    public PersonDirectorySearch(LdapTemplate template) {
        this.template = template;
    }

    public List<PersonSummary> bySurname(String surname) {
        LdapQuery q = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid", "cn", "mail")
            .countLimit(100)
            .timeLimit(3000)
            .where("objectClass").is("inetOrgPerson")
            .and("sn").is(surname);

        return template.search(
            q,
            (AttributesMapper<PersonSummary>) attrs ->
                new PersonSummary(
                    text(attrs, "uid"),
                    text(attrs, "cn"),
                    text(attrs, "mail")
                )
        );
    }

    private static String text(Attributes attrs, String name)
            throws NamingException {
        Attribute value = attrs.get(name);
        return value == null ? null : value.get().toString();
    }
}
```

Các điểm cần hiểu:

- `attributes("uid", "cn", "mail")` yêu cầu server trả đúng các thuộc tính cần hiển thị. Filter vẫn được đánh giá trên `sn` và `objectClass` dù chúng không nằm trong danh sách thuộc tính trả về.
- `countLimit(100)` giới hạn số entry nhận trong phạm vi của `SearchControls`; directory cũng có thể áp đặt giới hạn thấp hơn.
- `timeLimit(3000)` chỉ thời gian search tính theo mili giây ở cơ chế này; **không đồng nghĩa** với timeout TCP khi mở kết nối.
- `text(attrs, ...)` trả `null` khi server không trả thuộc tính, có thể vì không tồn tại, ACL hoặc chính sách server. Thiết kế DTO/API phải xử lý giá trị thiếu rõ ràng.
- `SUBTREE` cùng filter `(sn=Nguyen)` trả Lan và Hoa từ fixture, không trả Minh vì `sn=Tran`.

Nếu ứng dụng dùng Java cũ hơn phiên bản hỗ trợ `record`, có thể thay `PersonSummary` bằng class DTO thường. Không cần mapping `@Entry` khi chỉ dùng `AttributesMapper` để lấy một số thuộc tính.

## 10. Tạo bộ lọc AND, OR và presence

### 10.1. AND theo nhiều thuộc tính

Muốn tìm người có `sn=Nguyen` và `uid=lan`, dùng:

```java
LdapQuery bySurnameAndUid = query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .where("objectClass").is("inetOrgPerson")
    .and("sn").is("Nguyen")
    .and("uid").is("lan");
```

Điều kiện tương đương về ý nghĩa:

```text
(&(objectClass=inetOrgPerson)(sn=Nguyen)(uid=lan))
```

### 10.2. OR giữa hai lựa chọn

Muốn tìm người có `uid=lan` hoặc `uid=minh`:

```java
LdapQuery selectedPeople = query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .where("uid").is("lan")
    .or("uid").is("minh");
```

Filter tương đương:

```text
(|(uid=lan)(uid=minh))
```

Nếu cần cấu trúc nhóm phức tạp như `(A OR B) AND (C OR D)`, đừng dựa vào cách đọc tên phương thức repository dài hoặc thứ tự suy diễn. Có thể xây một filter có cấu trúc bằng API filter Spring LDAP hoặc dùng định dạng filter với tham số đã mã hóa, rồi kiểm thử các trường hợp biên.

### 10.3. Tìm các entry có một thuộc tính

Để tìm entry có `mail`:

```java
LdapQuery withMail = query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .where("mail").isPresent();
```

Đây là presence filter `(mail=*)`, **không phải** điều kiện `mail` bằng chuỗi `"*"`. Với truy vấn không có `mail`, có thể dùng filter tường minh `(!(mail=*))` khi phù hợp:

```java
LdapQuery withoutMail = query()
    .base("ou=people")
    .filter("(!(mail=*))");
```

Trong dữ liệu thực tế, sự thiếu vắng một thuộc tính có thể do server không lưu hoặc quyền hạn khiến client không đọc được; cần xem ACL và schema để giải thích kết quả chính xác.

## 11. Search bằng filter string: khi nào dùng và rủi ro

`LdapTemplate` cũng có overload nhận base và filter dạng chuỗi:

```java
List<String> names = ldapTemplate.search(
    "ou=people",
    "(&(objectClass=inetOrgPerson)(uid=lan))",
    (AttributesMapper<String>) attrs ->
        attrs.get("cn").get().toString()
);
```

Cách này hợp lý với **filter hoàn toàn cố định**. Nhưng không nên lấy đầu vào người dùng rồi ghép trực tiếp vào cú pháp:

```java
// KHÔNG AN TOÀN: userInput có thể chứa ký tự cú pháp LDAP.
String unsafe = "(uid=" + userInput + ")";
```

Các ký tự như `*`, `(`, `, `)`, dấu gạch chéo ngược và byte null có vai trò đặc biệt trong LDAP filter (RFC 4515). Ghép trực tiếp có thể khiến input thay đổi ý nghĩa tìm kiếm hoặc gây **LDAP injection**.

Ví dụ: một giá trị literal `"lan*"` cần được xử lý như dữ liệu khi truy vấn equality. Nếu nối chuỗi sai, `(uid=lan*)` có nghĩa “mọi uid bắt đầu bằng lan”, thay vì tìm chính xác `uid` có dấu `*`.

### 11.1. Cách an toàn với query builder

```java
LdapQuery safe = query()
    .base("ou=people")
    .where("uid").is(userInput);
```

Builder dựng filter từ attribute cố định và xử lý việc encode giá trị phù hợp, không yêu cầu người học tự thêm dấu ngoặc hay ký tự escape.

### 11.2. Filter định dạng có tham số

Khi cần cấu trúc filter tường minh, `LdapQueryBuilder.filter(String, Object...)` nhận chuỗi mẫu theo định dạng tham số và escape các giá trị tham số:

```java
LdapQuery safeFilter = query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .filter("(&(objectClass=inetOrgPerson)(uid={0}))", userInput);
```

`{0}` được thay bằng giá trị đã encode theo quy tắc LDAP filter của API. **Chỉ truyền dữ liệu** qua tham số; đừng để người dùng kiểm soát tên attribute, dấu ngoặc logic, phần filter thô hoặc base tùy ý.

Cũng có thể xây filter dạng object với `AndFilter`, `EqualsFilter` và API liên quan của Spring LDAP. Những cấu trúc này phù hợp khi có nhiều điều kiện tùy chọn; cần thiết kế phép nhóm rõ ràng và tránh đưa chuỗi input chưa mã hóa vào pattern.

### 11.3. Search substring một cách chủ đích

LDAP filter `(mail=*@example.org)` là truy vấn suffix với wildcard đứng trước. Điều này khác với truy vấn equality `(mail=\2a@example.org)` có ký tự `*` là một phần giá trị.

Nếu cần tìm theo hậu tố do người dùng cung cấp, giữ wildcard cố định trong **cú pháp tin cậy**, còn phần hậu tố đưa vào tham số:

```java
LdapQuery byDomain = query()
    .base("ou=people")
    .filter(
        "(&(objectClass=inetOrgPerson)(mail=*{0}))",
        "@example.org"
    );
```

Trong ví dụ `*@example.org` là logic tìm email thuộc domain được chỉ định. Với input tùy ý từ API, nên giới hạn domain cho phép, kiểm tra độ dài và phân quyền truy cập. Truy vấn có wildcard đầu chuỗi có thể khó tận dụng index; hãy đánh giá hiệu năng trước khi sử dụng trên directory lớn.

### 11.4. Escape filter khác escape DN

Filter dùng cú pháp RFC 4515; DN dùng cú pháp và quy tắc RFC 4514. Khi cần tạo DN từ giá trị dynamic, sử dụng API như `LdapNameBuilder`, không thay bằng hàm encode filter:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name entryDn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", userInput)
    .build();
```

Đây là ví dụ xây DN trong cùng hệ quy chiếu phù hợp, không phải phương án cho phép người dùng chọn tùy ý OU. Đối với search, nên giữ base trong allowlist hoặc từ cấu hình ứng dụng, còn input không đáng tin chỉ là giá trị điều kiện.

## 12. Search theo Name, SearchControls và ContextMapper

`LdapQueryBuilder` bao phủ phần lớn nhu cầu thông dụng. Để hiểu API nền, có thể dùng overload `search(base, filter, searchScope, attrs, mapper)`:

```java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;

List<String> names = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    SearchControls.ONELEVEL_SCOPE,
    new String[] {"cn"},
    (AttributesMapper<String>) attrs ->
        attrs.get("cn").get().toString()
);
```

Cách này dùng trực tiếp `SearchControls.ONELEVEL_SCOPE` của JNDI. `LdapQueryBuilder` dễ đọc hơn khi có nhiều tùy chọn và cần filter từ giá trị động. Với trường hợp muốn truy cập DN hoặc thông tin context của entry, cân nhắc `ContextMapper<T>` thay cho `AttributesMapper<T>`.

| Mapper | Dữ liệu đầu vào | Phù hợp cho |
|---|---|---|
| `AttributesMapper<T>` | `javax.naming.directory.Attributes` của entry | Đọc một số thuộc tính thành DTO nhẹ. |
| `ContextMapper<T>` | Context/adapter của entry tìm được | Cần thông tin context, DN hoặc mapping phức tạp hơn. |
| Spring LDAP ODM (`find(query, Entity.class)`) | Entity có `@Entry`, `@Attribute`, `@Id` | Ánh xạ đầy đủ đối tượng miền từ LDAP. |

**Quan trọng:** `AttributesMapper` không được cung cấp DN entry như một thuộc tính thông thường. Nếu cần định danh entry, dùng `ContextMapper` hoặc ODM và hiểu DN do context trả có thể tương đối với base đã cấu hình.

Với Spring Data LDAP, repository như:

```java
public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    List<PersonEntry> findBySurname(String surname);
}
```

phù hợp khi query cố định và entity đã được mapping tốt. `LdapTemplate` phù hợp khi cần thay search base/scope, chọn thuộc tính, tạo filter động hoặc xử lý riêng kết quả directory.

## 13. Hiệu năng: tối ưu base trước khi tối ưu mapper

Một truy vấn có filter hẹp nhưng base quá rộng vẫn có thể buộc LDAP server xét nhiều entry. Các lựa chọn cải thiện:

1. **Chọn base gần dữ liệu cần tìm:** `ou=people` thay vì toàn bộ `dc=example,dc=org` nếu chỉ tìm nhân viên.
2. **Chọn scope đủ hẹp:** `ONELEVEL` nếu người dùng phải nằm ngay dưới một OU; `SUBTREE` khi thật sự phải đi qua các nhánh con.
3. **Filter theo thuộc tính phù hợp:** ưu tiên giá trị cụ thể như `uid`; kiểm tra index/matching rule trên server.
4. **Giới hạn attributes trả về:** chỉ yêu cầu `uid`, `cn`, `mail` nếu API không cần toàn bộ profile.
5. **Giới hạn count/time:** `countLimit`, `timeLimit` là hàng rào bổ sung, không thay thế thiết kế filter/base.
6. **Làm việc với paging khi danh sách lớn:** nhiều server có giới hạn số kết quả riêng; cần LDAP paging control và API tương thích nếu muốn quét lượng dữ liệu lớn. Không tự giả định mọi query hỗ trợ `Pageable` như Spring Data JPA.
7. **Không làm search toàn cây để xác thực:** xác thực credential cần luồng phù hợp với Spring Security LDAP, quyền bind và chính sách bảo mật.

Lưu ý thực tế: `countLimit` có thể khiến kết quả **bị cắt**, không có nghĩa directory chỉ có đúng chừng đó entry. Do vậy, không kết luận “không có người tiếp theo” khi truy vấn đang bị server/client giới hạn.

## 14. Bảo mật kết nối và quyền đọc

Dù filter an toàn, kết nối LDAP vẫn cần được bảo vệ:

- Dùng **LDAPS hoặc StartTLS** theo chính sách directory và xác minh certificate chain/hostname hợp lệ.
- Quản lý mật khẩu bind bằng secret manager hoặc biến môi trường; không để secret trong mã nguồn.
- Cấp cho account tìm kiếm quyền tối thiểu, tránh truy vấn các nhánh và thuộc tính nhạy cảm ngoài nhu cầu.
- Kiểm soát ai được gọi endpoint search, đặc biệt truy vấn theo tên hoặc email có thể tiết lộ danh bạ.
- Không in toàn bộ entry, password hash, nhóm nhạy cảm hoặc filter chứa dữ liệu cá nhân vào log.
- Giới hạn kích thước input và lưu lượng tìm kiếm để tránh làm directory quá tải.

**Tìm thấy LDAP entry không phải là xác thực người dùng**. `LdapTemplate.search` đọc dữ liệu theo danh tính đang bind; việc kiểm tra mật khẩu, xây dựng phiên và quyền ứng dụng là luồng bảo mật riêng.

## 15. Kiểm thử base/scope/filter với directory thật

Mock `LdapTemplate` giúp kiểm tra cách service sử dụng dữ liệu trả về, nhưng **không chứng minh** base, scope, filter hoặc matching rule hoạt động đúng. Cần kiểm thử tích hợp trên directory riêng đã nạp fixture ở mục 3.

Ví dụ khung JUnit 5/Spring Boot:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("ldap-test")
class PersonSearchIntegrationTest {

    @Autowired
    private PersonSearchService service;

    @Test
    void oneLevelDoesNotReachNestedContractor() {
        assertThat(service.namesByUid("lan"))
            .containsExactly("Lan Nguyen");

        assertThat(service.namesByUid("hoa"))
            .isEmpty();
    }
}
```

Ở đây, `ldap-test` phải trỏ tới directory thử nghiệm và fixture; `PersonSearchService` phải được khai báo như Spring bean hoặc cung cấp bằng cấu hình test. Các tình huống cần mở rộng:

| Tình huống | Kỳ vọng |
|---|---|
| Base `ou=people`, scope `ONELEVEL`, filter `(uid=lan)` | Có Lan. |
| Cùng base/scope, filter `(uid=hoa)` | Không có Hoa vì nằm sâu hơn một cấp. |
| Base `ou=people`, scope `SUBTREE`, filter `(uid=hoa)` | Có Hoa. |
| Base `ou=groups`, scope `SUBTREE`, filter `(uid=lan)` | Không có Lan. |
| `(sn=Nguyen)` với `SUBTREE` | Có Lan và Hoa, không có Minh. |
| Filter `(mail=*)` trong `SUBTREE` | Chỉ các entry có thuộc tính `mail` phù hợp. |
| Tìm equality với input `lan*` | Không bị hiểu thành wildcard tìm tất cả UID bắt đầu `lan`. |
| Dùng account chỉ được đọc một nhánh | Kết quả và lỗi theo ACL server, không suy ra toàn directory. |
| Search base không tồn tại | Xác nhận hành vi exception/empty theo cấu hình thực tế. |

Nên có fixture riêng biệt, dữ liệu xác định, quyền account test rõ ràng và cleanup. Với các phép thử write/CRUD, đừng mặc định có transaction rollback kiểu JPA. Kết quả integration test còn phụ thuộc schema và server implementation: môi trường OpenLDAP, directory nhúng và Active Directory có thể khác nhau.

### 15.1. Kiểm thử điều kiện bảo mật

Một tập input nên thử với `where("uid").is(input)` hoặc `filter(..., input)`:

- `lan`: trả đúng Lan.
- `lan*`: không được mở rộng thành `(uid=lan*)` khi đang dùng equality.
- Giá trị chứa `(` hoặc `)`: không được chèn được cấu trúc filter.
- Giá trị chứa dấu `\`: không được thay đổi cú pháp filter do thiếu escape.
- Chuỗi rất dài hoặc sai định dạng nghiệp vụ: được xử lý theo rule validation và giới hạn của API.

Với test hạ tầng, thử sai certificate hoặc mất kết nối chỉ trong directory thử nghiệm. Không dùng credential/entry production để kiểm tra phản ứng lỗi hoặc để tìm dữ liệu nhạy cảm.

## 16. Khắc phục lỗi khi search không như mong đợi

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Có Lan nhưng không có Hoa | `ONELEVEL` không đi vào `ou=contractors` | Kiểm tra scope và cây DN; đổi `SUBTREE` nếu nghiệp vụ yêu cầu. |
| Không thấy ai dù có data | Search base sai hoặc filter dùng sai attribute | Đối chiếu `ContextSource` base và query base, tên `sn`/`uid`. |
| Lỗi `NameNotFound` khi search | Base không tồn tại hoặc DN ghép sai | Kiểm tra connection base, RDN và đường dẫn dưới directory. |
| `AttributesMapper` lỗi khi đọc `mail` | Entry thiếu `mail` hoặc ACL ẩn thuộc tính | Kiểm tra `attrs.get("mail")` trước khi gọi `get()`. |
| Input có `*` trả nhiều người bất thường | Ghép filter bằng chuỗi chưa escape | Dùng query builder/binding an toàn và kiểm thử injection. |
| Filter OR/AND trả sai tập | Logic nhóm điều kiện sai | Viết lại nhóm ngoặc rõ ràng, test tập dữ liệu có trường hợp phân biệt. |
| Truy vấn chậm trên cây lớn | Base quá rộng, `SUBTREE` sâu, wildcard ở đầu | Thu hẹp base/scope, xem index và loại filter. |
| Trả thiếu entry trong danh bạ lớn | Count/time limit hoặc size limit của server | Kiểm tra LDAP result/limit; dùng paging control nếu cần. |
| Search thất bại hoàn toàn | Lỗi TCP/TLS/bind/ACL | Phân tích exception chain; đừng chuyển lỗi thành danh sách rỗng. |

Tìm kiếm trống không phải lúc nào cũng là “người dùng không tồn tại”: có thể bạn đang tìm sai nhánh hoặc tài khoản bind không thấy dữ liệu theo ACL. Một bài kiểm thử integration đủ fixture giúp phân biệt nhiều nguyên nhân này.

## 17. Bài tập thực hành

### Bài 1 — Chọn đúng scope

Với cây ở mục 2, hãy dự đoán kết quả của ba truy vấn có cùng filter `(objectClass=inetOrgPerson)`, base `ou=people` nhưng scope lần lượt là `OBJECT`, `ONELEVEL`, `SUBTREE`. Giải thích vì sao entry `ou=people` không tự xuất hiện trong kết quả dù `SUBTREE` xét nó.

### Bài 2 — Viết filter

Viết filter cho các yêu cầu:

1. Người có `sn=Nguyen` và `mail` tồn tại.
2. Người có `uid=lan` hoặc `uid=minh`.
3. Người thuộc `inetOrgPerson` với email kết thúc bằng `@example.org`.
4. Các entry không có thuộc tính `mail`.

Nêu filter nào có wildcard, filter nào là presence và cách áp dụng điều kiện object class.

### Bài 3 — Từ YAML sang search base

Ứng dụng dùng `spring.ldap.base: dc=example,dc=org`. Bạn muốn tìm người trong `ou=contractors,ou=people`. Hãy chỉ ra `base(...)` cần truyền khi dùng `LdapQueryBuilder`, và điều gì xảy ra nếu viết lặp `dc=example,dc=org` trong base đó.

### Bài 4 — Viết Java service

Viết service dùng `LdapTemplate.search` với query builder để trả `uid`, `cn`, `mail` của người họ `Tran`, chỉ xét entry con trực tiếp dưới `ou=people`, giới hạn 50 kết quả. Mapper phải xử lý khi `mail` không có.

### Bài 5 — An toàn filter

Phân tích rủi ro của `"(uid=" + userInput + ")"` khi input là `"lan*"` hoặc chứa dấu ngoặc. Chuyển sang `query().where("uid").is(userInput)` và đưa ra các integration test chứng minh nó giữ đúng phép tìm equality.

## 18. Kết luận và tài liệu tham khảo

Khi tìm kiếm qua `LdapTemplate`, hãy xác định **bắt đầu ở đâu (base)**, **đi sâu tới đâu (scope)**, **entry phải thỏa điều kiện gì (filter)** và **cần trả thuộc tính nào (attributes)**. Base thường được hiểu tương đối với `ContextSource`; `ONELEVEL` khác `SUBTREE` một cách quan trọng; filter phải sử dụng tên thuộc tính LDAP và encode giá trị input an toàn. `LdapQueryBuilder` giúp biểu đạt các phần này rõ ràng, còn `LdapTemplate.search` kết hợp chúng với mapper để tạo danh sách Java object.

Đối với ứng dụng Spring Data LDAP, repository phù hợp với các truy vấn entity cố định, trong khi `LdapTemplate` phù hợp khi cần tự chọn base/scope, filter động và thuộc tính trả về. Hãy kiểm thử với directory thật để xác nhận DN, schema, quyền, kết quả truy vấn và hiệu năng.

Nguồn tham khảo chính thức:

- [Spring LDAP – Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html)
- [Spring LDAP – Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring LDAP – `LdapQueryBuilder` API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html)
- [Spring LDAP – `LdapTemplate` API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP – `SearchScope` API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/SearchScope.html)
- [RFC 4515 – LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4511 – LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511)
