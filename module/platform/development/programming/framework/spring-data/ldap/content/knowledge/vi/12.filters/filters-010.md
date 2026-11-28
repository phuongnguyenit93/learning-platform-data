# Escape giá trị bộ lọc và phân biệt với escape DN

## 1. Vì sao cần phân biệt hai kiểu escape?

Ứng dụng LDAP thường nhận UID, email, tên nhóm hoặc DN từ request rồi dùng dữ liệu đó để tìm kiếm directory. Nếu nối input trực tiếp vào filter hoặc DN, ký tự trong dữ liệu có thể bị hiểu thành cú pháp.

Ví dụ:

```java
String uid = request.getParameter("uid");
String filter = "(uid=" + uid + ")";
```

Nếu người dùng gửi:

```text
*)(|(objectClass=*))
```

thì filter sau khi nối chuỗi có thể trở thành:

```text
(uid=*)(|(objectClass=*)))
```

Ý định tìm một UID đã biến thành biểu thức có thêm nhánh OR. Đây là **LDAP filter injection**.

Một lỗi khác xảy ra khi dựng DN bằng nối chuỗi:

```java
String dn = "uid=" + uid + ",ou=people,dc=example,dc=org";
```

Nếu UID chứa dấu phẩy, dấu cộng hoặc backslash, chuỗi có thể bị phân tích thành nhiều RDN ngoài ý muốn.

LDAP có hai ngữ cảnh độc lập:

- **RFC 4515 — Search Filter String Representation:** escape giá trị assertion trong filter.
- **RFC 4514 — Distinguished Names:** escape giá trị AVA/RDN khi biểu diễn DN.

Không dùng một hàm escape cho cả hai. Một chuỗi DN hợp lệ vẫn cần filter escaping nếu được chèn vào filter; filter escaping cũng không tạo ra một DN hợp lệ.

Trong module **SPRING_DATA_LDAP**, Spring Data LDAP và Spring LDAP cung cấp repository, ODM, LdapQueryBuilder, LdapTemplate và công cụ dựng DN. Bài này tập trung vào ranh giới giữa dữ liệu và cú pháp khi truy vấn directory.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt assertion value trong filter với giá trị RDN trong DN.
2. Nhận diện các octet đặc biệt cần escape theo RFC 4515.
3. Dựng DN bằng LdapNameBuilder thay vì nối chuỗi.
4. Dùng LdapQueryBuilder, LdapEncoder.filterEncode hoặc JNDI parameterized search.
5. Xử lý trường hợp filter tìm theo attribute chứa DN như member.
6. Giữ attribute description, operator và cấu trúc filter dưới quyền kiểm soát của ứng dụng.
7. Viết test với dấu sao, ngoặc, backslash, NUL, Unicode và dấu phẩy trong RDN.

## 2. Cấu trúc của LDAP search filter

RFC 4515 mô tả filter dạng chuỗi. Một số ví dụ:

```text
(uid=linh)
(&(objectClass=inetOrgPerson)(uid=linh))
(|(uid=linh)(mail=linh@example.org))
(!(accountStatus=disabled))
(mail=*)
```

Một assertion cơ bản có dạng:

```text
(attributeDescription=assertionValue)
```

**Phần cần filter-escape là assertion value.** Attribute description, toán tử, dấu ngoặc và cấu trúc AND/OR/NOT là cú pháp filter. Không cho input tùy ý điều khiển những phần cấu trúc này.

### 2.1. Các octet đặc biệt theo RFC 4515

Trong assertion value, năm octet sau phải được biểu diễn bằng backslash và hai chữ số hex:

| Octet | Ký tự | Escape |
| --- | --- | --- |
| 0x00 | NUL | `\00` |
| 0x28 | `(` | `\28` |
| 0x29 | `)` | `\29` |
| 0x2a | `*` | `\2a` |
| 0x5c | `\` | `\5c` |

Ví dụ:

```text
Đầu vào:
a*)(uid=*)\admin

Assertion value đã encode:
a\2a\29\28uid=\2a\29\5cadmin

Filter:
(uid=a\2a\29\28uid=\2a\29\5cadmin)
```

Filter parser giải mã escape hex thành dữ liệu. Các dấu ngoặc, wildcard và backslash trong input không còn thay đổi cấu trúc filter.

### 2.2. Unicode và UTF-8

LDAP filter string sử dụng UTF-8. Khi phải escape octet ngoài các ký tự đặc biệt, cần tuân thủ quy tắc octet/UTF-8 của RFC 4515; không thay một Unicode code point thành một cặp hex tùy ý.

Ví dụ, chuỗi tiếng Việt `Nguyễn Văn An` có thể được truyền dưới dạng Java Unicode string cho query builder. Nếu tự viết encoder, phải chuyển chuỗi sang UTF-8 bytes trước khi áp dụng quy tắc octet. Không tự encode/decode Unicode theo từng ký tự Java char.

## 3. Escape DN theo RFC 4514

DN là tên phân cấp của entry. Ví dụ:

```text
uid=linh,ou=people,dc=example,dc=org
```

Nếu UID chứa dấu phẩy, không thể chèn trực tiếp:

```text
uid=doe, john,ou=people,dc=example,dc=org
```

Dấu phẩy bên trong giá trị RDN phải được escape:

```text
uid=doe\, john,ou=people,dc=example,dc=org
```

### 3.1. Những ký tự cần chú ý trong giá trị RDN

RFC 4514 quy định cách biểu diễn các ký tự đặc biệt. Các trường hợp thường cần escape:

- Dấu cách ở đầu hoặc cuối giá trị.
- Dấu `#` ở đầu giá trị.
- Dấu phẩy `,`, dấu cộng `+`, dấu nháy kép `"`.
- Backslash `\`, dấu nhỏ hơn `<` và lớn hơn `>`.
- Dấu chấm phẩy `;` và dấu bằng `=`.
- NUL (0x00), thường biểu diễn bằng `\00`.

Các ký tự có quy tắc theo vị trí. Không tự viết hàm replace đơn giản nếu không xử lý đúng Unicode, byte và vị trí đầu/cuối.

### 3.2. Dùng LdapNameBuilder để tạo DN

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name userDn = LdapNameBuilder
    .newInstance("ou=people,dc=example,dc=org")
    .add("uid", "doe, john")
    .build();
```

Builder tạo DN từ các thành phần RDN và xử lý biểu diễn giá trị. Không cần tự nối dấu phẩy hay đoán khi nào thêm backslash.

### 3.3. Phân tích DN đã có bằng LdapName

```java
import javax.naming.ldap.LdapName;

LdapName parsed = new LdapName(
    "uid=doe\\, john,ou=people,dc=example,dc=org"
);
```

Parse DN không đồng nghĩa tin tưởng DN đó. Ứng dụng vẫn cần kiểm tra DN có thuộc naming context/OU mà caller được phép thao tác hay không. Escape cú pháp không thay thế authorization.

## 4. Khi filter chứa một DN: cần xử lý cả hai ngữ cảnh

Giả sử group có attribute DN-valued:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=doe\, john,ou=people,dc=example,dc=org
```

Ứng dụng muốn tìm group theo member DN. Có hai bước:

1. **Dựng DN user:** escape giá trị UID trong RDN theo RFC 4514, tốt nhất bằng LdapNameBuilder.
2. **Đưa DN vào filter:** chuỗi DN đã dựng trở thành assertion value, nên phải escape theo RFC 4515 nếu tự ghép raw filter.

```text
UID input:
  doe, john
       |
       | LdapNameBuilder / RFC 4514
       v
DN:
  uid=doe\, john,ou=people,dc=example,dc=org
       |
       | LdapEncoder.filterEncode / RFC 4515
       v
Filter assertion value:
  uid=doe\5c, john,ou=people,dc=example,dc=org
```

Backslash của DN representation được filter-escape thành `\5c` khi chuỗi DN trở thành assertion value. Filter parser giải mã `\5c` thành backslash; server sau đó so sánh giá trị member theo semantics của DN.

Không escape DN string bằng RFC 4514 lần thứ hai. Bước ngoài là **filter escaping**, vì chuỗi DN lúc này nằm trong filter.

## 5. Cách 1: dùng Spring LdapQueryBuilder

Với truy vấn equality thông thường, ưu tiên query builder thay vì nối chuỗi:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

String uid = requestUid;

LdapQuery ldapQuery = query()
    .base("ou=people")
    .where("objectClass").is("inetOrgPerson")
    .and("uid").is(uid);

List<String> names = ldapTemplate.search(
    ldapQuery,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
```

Query builder giữ cấu trúc filter do ứng dụng định nghĩa và encode assertion value khi dựng filter. UID là dữ liệu; objectClass, tên attribute, operator và search base là phần cấu trúc do code kiểm soát.

### 5.1. Tránh nối input vào filter string

Không viết:

```java
String filter = "(&(objectClass=inetOrgPerson)(uid=" + uid + "))";
ldapTemplate.search(filter, mapper);
```

Input có thể chứa ký tự làm thay đổi cấu trúc filter.

### 5.2. Attribute description và operator cũng phải được kiểm soát

Không chỉ assertion value mới có thể gây injection. Nếu API cho caller truyền attribute hoặc operator tùy ý, việc ghép những phần đó vào filter cũng có thể thay đổi cú pháp.

Dùng enum/allowlist:

```java
enum SearchField {
    UID("uid"),
    MAIL("mail"),
    COMMON_NAME("cn");

    private final String attribute;

    SearchField(String attribute) {
        this.attribute = attribute;
    }

    String attribute() {
        return attribute;
    }
}
```

Nếu sản phẩm hỗ trợ advanced search, thiết kế query model có field/operator allowlist, giới hạn độ sâu và số điều kiện rồi tự dựng filter từ model. Không xem một filter string parse được là filter được phép thực thi.

## 6. Cách 2: LdapEncoder.filterEncode

Spring LDAP có `LdapEncoder.filterEncode(String)` để encode giá trị dùng trong filter:

```java
import org.springframework.ldap.support.LdapEncoder;

String rawValue = "a*)(uid=*)\\admin";
String safeValue = LdapEncoder.filterEncode(rawValue);

String filter =
    "(&(objectClass=inetOrgPerson)(uid=" + safeValue + "))";
```

Ở đây cấu trúc filter là hằng số do ứng dụng viết. Chỉ rawValue đến từ input và được filter-encode trước khi chèn.

Kết quả minh họa:

```text
raw:
a*)(uid=*)\admin

encoded:
a\2a\29\28uid=\2a\29\5cadmin
```

### 6.1. Chỉ encode một lần

```java
String once = LdapEncoder.filterEncode(rawValue);
String twice = LdapEncoder.filterEncode(once); // Sai: double encoding
```

Encode hai lần có thể biến backslash trong escape sequence đầu thành dữ liệu backslash, khiến server nhận giá trị khác input ban đầu.

Quy ước tốt:

- Giữ biến rawValue cho dữ liệu gốc.
- Encode tại ranh giới nơi giá trị được đưa vào filter.
- Không truyền chuỗi đã encode qua nhiều tầng rồi encode tiếp.
- Không lưu filter-encoded string làm dữ liệu nghiệp vụ.

### 6.2. Wildcard có chủ đích

Trong substring search, wildcard phải do **ứng dụng** thêm, không phải input tự điều khiển:

```java
String safePrefix = LdapEncoder.filterEncode(userPrefix);
String filter =
    "(&(objectClass=inetOrgPerson)(cn=" + safePrefix + "*))";
```

Dấu sao do người dùng nhập được encode thành literal `\2a`; dấu sao cuối do code thêm mới là wildcard. Với exact match, không thêm wildcard.

## 7. Cách 3: JNDI parameterized search

JNDI `DirContext.search` có overload nhận filter expression và mảng đối số:

```java
import javax.naming.NamingEnumeration;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn", "mail"});

NamingEnumeration<SearchResult> results = context.search(
    "ou=people",
    "(&(objectClass=inetOrgPerson)(uid={0}))",
    new Object[] {uid},
    controls
);

try {
    while (results.hasMore()) {
        SearchResult result = results.next();
        // Xử lý kết quả.
    }
} finally {
    results.close();
}
```

Provider thay placeholder `{0}` bằng assertion value đã encode theo quy tắc LDAP filter. Không tự thay placeholder bằng String.replace hoặc String.format; dùng overload có tham số.

### 7.1. Placeholder chỉ dành cho assertion value

Tham số hóa không có nghĩa có thể truyền tên attribute hoặc operator:

```java
// Không dùng placeholder để bind attribute description:
context.search(base, "({0}={1})",
    new Object[] {attributeName, value}, controls);
```

Filter arguments không biến attribute description thành identifier parameter giống SQL. Attribute, matching rule, operator và cấu trúc filter vẫn phải là hằng số hoặc được chọn từ allowlist.

### 7.2. JNDI với DN-valued attribute

Đầu tiên dựng DN, sau đó truyền DN string làm filter argument:

```java
Name memberDn = LdapNameBuilder.newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", "doe, john")
    .build();

NamingEnumeration<SearchResult> groups = context.search(
    "ou=groups",
    "(member={0})",
    new Object[] {memberDn.toString()},
    controls
);
```

JNDI encode chuỗi DN như assertion value của filter. DN đã được dựng bằng LdapNameBuilder; không filter-encode trước khi truyền vào API parameterized search vì có thể double-encode.

## 8. Tìm kiếm attribute chứa DN bằng Spring LDAP

Ví dụ dùng member để tìm group có chứa user:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

Name memberDn = LdapNameBuilder.newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", "doe, john")
    .build();

LdapQuery groupsContainingUser = query()
    .base("ou=groups")
    .where("objectClass").is("groupOfNames")
    .and("member").is(memberDn.toString());
```

Query builder encode giá trị memberDn theo ngữ cảnh filter. Chuỗi DN bên trong đã được dựng theo ngữ cảnh DN; đây là lý do không thể thay hai bước bằng một hàm escape chung.

Nếu dùng raw filter:

```java
String filterDn = LdapEncoder.filterEncode(memberDn.toString());
String filter = "(member=" + filterDn + ")";
```

Chỉ chọn một trong hai cách:

- Query builder/JNDI parameterized search: truyền raw DN string làm value, thư viện encode.
- Raw filter string: gọi LdapEncoder.filterEncode đúng một lần trên DN string.

Không truyền filterDn đã encode vào query builder hoặc parameterized search.

## 9. So sánh filter escaping và DN escaping

| Tiêu chí | Filter escaping — RFC 4515 | DN escaping — RFC 4514 |
| --- | --- | --- |
| Ngữ cảnh | Assertion value trong filter. | Giá trị AVA/RDN trong DN. |
| Mục tiêu | Ngăn dữ liệu trở thành cú pháp filter. | Ngăn dữ liệu trở thành dấu phân cách/cú pháp DN. |
| Ký tự điển hình | NUL, `(`, `)`, `*`, backslash. | Space đầu/cuối, `#` đầu, `,`, `+`, quote, backslash, `<`, `>`, `;`, `=`, NUL. |
| Công cụ | LdapEncoder.filterEncode, LdapQueryBuilder, JNDI filter arguments. | LdapNameBuilder, LdapName. |
| Không dùng thay thế | Không dùng để dựng RDN. | Không dùng để chèn raw value vào filter. |

**Ví dụ quan trọng:** DN `uid=doe\, john,ou=people,dc=example,dc=org` là giá trị của filter `(member=...)`. Backslash của DN phải được filter-escape thành `\5c` ở tầng ngoài. Filter parser giải mã backslash rồi directory mới xử lý DN value.

## 10. Những phần của filter không được lấy từ input tùy ý

| Thành phần | Nguồn phù hợp | Cách kiểm soát |
| --- | --- | --- |
| Assertion value như UID/email | Request hoặc nghiệp vụ | Filter encoder/query builder/JNDI args. |
| DN dùng làm value member | DN đã dựng hoặc đọc từ directory | Dựng/parse DN, rồi filter-encode ở tầng filter. |
| Attribute description như uid, mail | Code/schema | Enum/allowlist. |
| Operator =, >=, <=, ~= | Code/nghiệp vụ | Chọn từ enum/nhánh code cố định. |
| AND/OR/NOT và ngoặc | Code | Dùng query/filter builder. |
| Search base | Cấu hình/authorization policy | Giới hạn OU/naming context. |
| Search scope | Code/policy | Chọn OBJECT/ONELEVEL/SUBTREE theo use case. |

Không nhận nguyên filter string từ API công khai:

```json
{
  "filter": "(&(objectClass=*)(|(uid=*)(mail=*)))"
}
```

Nếu sản phẩm cần advanced search, thiết kế query model có field/operator allowlist, giới hạn độ sâu và số điều kiện, rồi tự dựng filter từ model. Không xem filter parse được là filter được phép thực thi.

## 11. Unit test cho encoder và DN builder

### 11.1. Test RFC 4515 filter encoding

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapEncoder;

class LdapFilterEncodingTests {

    @Test
    void escapesFilterAssertionOctets() {
        String input = "a*)(uid=*)\\admin";

        assertThat(LdapEncoder.filterEncode(input))
            .isEqualTo("a\\2a\\29\\28uid=\\2a\\29\\5cadmin");
    }

    @Test
    void preservesOrdinaryUnicodeText() {
        assertThat(LdapEncoder.filterEncode("Nguyễn Văn An"))
            .isEqualTo("Nguyễn Văn An");
    }
}
```

Test Unicode xác minh encoder không làm hỏng text thông thường. Encoding byte trên wire vẫn do provider thực hiện theo LDAP/UTF-8.

### 11.2. Test DN builder với dấu phẩy

```java
import static org.assertj.core.api.Assertions.assertThat;

import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

class LdapDnEncodingTests {

    @Test
    void buildsOneRdnWhenValueContainsComma() throws Exception {
        Name dn = LdapNameBuilder
            .newInstance("ou=people,dc=example,dc=org")
            .add("uid", "doe, john")
            .build();

        assertThat(dn).isEqualTo(
            new LdapName(
                "uid=doe\\, john,ou=people,dc=example,dc=org"
            )
        );
        assertThat(dn.size()).isEqualTo(4);
    }
}
```

Test chứng minh dấu phẩy trong UID thuộc về một RDN, không tạo thêm RDN ngoài ý muốn.

### 11.3. Test hai lớp escape

```java
@Test
void dnValueMustBeFilterEncodedWhenInsertedIntoRawFilter() {
    Name memberDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", "doe, john")
        .build();

    String filterValue =
        LdapEncoder.filterEncode(memberDn.toString());

    assertThat(filterValue).contains("\\5c");
    assertThat(filterValue).doesNotContain("\\,");
}
```

DN builder tạo chuỗi DN có escape cho RDN; filter encoder escape backslash trong chuỗi DN thành `\5c`. Khi kiểm tra DN, ưu tiên so sánh Name thay vì so sánh chuỗi format.

## 12. Integration test: truy vấn không bị filter injection

Giả sử test directory có một vài user bình thường trong `ou=people`. Ta muốn chứng minh input chứa cú pháp filter vẫn được xem là một UID duy nhất:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

@DataLdapTest
class SafeLdapSearchTests {

    @Autowired
    private LdapTemplate ldapTemplate;

    @Test
    void userInputIsTreatedAsOneUidValue() {
        String attackerInput = "*)(|(objectClass=*))";

        LdapQuery safeQuery = query()
            .base("ou=people")
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(attackerInput);

        List<String> results = ldapTemplate.search(
            safeQuery,
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("uid").get()
        );

        // Fixture không có UID bằng payload này.
        // Kết quả phải rỗng, không trả về toàn bộ people.
        assertThat(results).isEmpty();
    }
}
```

Test này cần fixture có các user bình thường. Nếu code bị thay bằng nối filter thô, payload có thể làm query trả nhiều entry hoặc gây lỗi cú pháp; query builder giữ input như một assertion value.

## 13. Integration test: raw filter có DN-valued attribute

Nếu ứng dụng cần raw filter vì cấu trúc phức tạp, hãy filter-encode DN string ở tầng ngoài:

```java
Name memberDn = LdapNameBuilder
    .newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", "doe, john")
    .build();

String safeMemberValue =
    LdapEncoder.filterEncode(memberDn.toString());

String filter =
    "(&(objectClass=groupOfNames)(member=" +
    safeMemberValue + "))";

List<String> groups = ldapTemplate.search(
    filter,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
```

Fixture nên có một group chứa đúng member DN và một group khác không chứa DN đó. Xác minh group thứ nhất được tìm thấy, group thứ hai không được tìm thấy, kể cả khi DN có dấu phẩy trong RDN.

Nếu có thể dùng LdapQueryBuilder hoặc JNDI parameterized search, ưu tiên chúng để giảm code tự ghép filter.

## 14. Substring search và wildcard có kiểm soát

Tìm prefix có thể cần wildcard:

```java
String safePrefix = LdapEncoder.filterEncode(userPrefix);
String filter =
    "(&(objectClass=inetOrgPerson)(cn=" + safePrefix + "*))";
```

Trong ví dụ, dấu sao do người dùng nhập được encode thành literal `\2a`; wildcard cuối do code thêm. Nếu muốn exact match, không thêm wildcard.

Tách rõ use case:

- Exact match: encode toàn bộ input, không thêm wildcard.
- Prefix match: encode input rồi thêm wildcard cố định ở cuối.
- Suffix match: thêm wildcard cố định ở đầu.
- Contains match: thêm wildcard cố định ở hai đầu.

Wildcard rộng có thể tạo query tốn kém. Ngoài escaping, cần giới hạn base DN, scope, time limit, size limit và rate.

## 15. DN escaping không thay thế kiểm tra quyền

DN có thể được dựng hợp lệ nhưng vẫn trỏ tới vùng caller không được phép:

```text
cn=admins,ou=groups,dc=example,dc=org
```

Nếu caller chỉ được quản lý group trong `ou=teams`, việc escape đúng DN không cấp quyền truy cập `ou=groups`.

Với thao tác theo DN:

1. Dựng DN bằng builder hoặc parse bằng LdapName.
2. Kiểm tra DN thuộc naming context/subtree được phép.
3. Xác thực caller và authorization theo nghiệp vụ.
4. Dùng LDAP bind identity có ACL phù hợp.
5. Gửi thao tác qua TLS theo policy.

Escaping không thay thế ACL hoặc authorization.

## 16. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Filter trả quá nhiều kết quả | Nối raw input làm wildcard/AND/OR thành cú pháp. | Query builder, JNDI arguments hoặc filterEncode. |
| Filter syntax error | Ngoặc, backslash hoặc NUL chưa được escape. | Escape assertion value theo RFC 4515. |
| Không tìm thấy DN có dấu phẩy | DN được nối chuỗi hoặc escape sai. | LdapNameBuilder, LdapName. |
| Tìm group theo member DN không khớp | DN đúng nhưng chưa filter-escape khi chèn raw filter. | Escape chuỗi DN theo RFC 4515 ở tầng ngoài. |
| Query không khớp sau encoder | Double-encoding hoặc dùng nhầm DN encoder. | Encode đúng một lần, đúng context. |
| Search attribute động gây lỗi | Input điều khiển attribute description/operator. | Allowlist field/operator; chỉ parameterize assertion value. |
| Prefix search không hoạt động | Wildcard bị escape hoặc bị encode. | Ứng dụng thêm wildcard cố định sau khi encode prefix. |
| UID Unicode tìm không khớp | Tự encode code point sai hoặc charset không như dự kiến. | Dùng Java Unicode string và provider UTF-8; kiểm tra server/schema. |
| DN hợp lệ nhưng thao tác bị từ chối | ACL/authorization không cho phép. | Kiểm tra quyền; escaping không cấp quyền. |
| Kết quả khác giữa server | Matching rule/schema khác nhau. | Test trên đúng directory và attribute syntax. |

## 17. Checklist bảo mật filter và DN

- [ ] Đã phân biệt RFC 4515 filter escaping và RFC 4514 DN escaping.
- [ ] Không nối input thô vào filter string.
- [ ] Assertion value được encode đúng một lần.
- [ ] Attribute description và operator lấy từ code/allowlist.
- [ ] AND/OR/NOT và search scope do ứng dụng kiểm soát.
- [ ] Dùng LdapQueryBuilder hoặc JNDI parameterized search cho query động.
- [ ] Khi filter chứa DN, dựng DN trước rồi filter-encode chuỗi DN nếu ghép raw filter.
- [ ] Không filter-encode DN trước khi truyền vào API tự encode parameter.
- [ ] Dùng LdapNameBuilder/LdapName, không nối DN từ input.
- [ ] Không dùng split dấu phẩy để phân tích DN.
- [ ] Wildcard substring do ứng dụng chủ động thêm.
- [ ] Có test với sao, ngoặc, backslash, NUL, Unicode và dấu phẩy.
- [ ] Có giới hạn base DN, scope, size/time limit và rate.
- [ ] Kiểm tra authorization/ACL độc lập với escaping.
- [ ] Không ghi raw filter, password hoặc dữ liệu nhạy cảm vào log rộng.

## 18. Bài tập vận dụng

1. Escape giá trị `*)(|(objectClass=*))` để dùng làm assertion value trong `(uid=...)`. Giải thích vì sao nó không còn thay đổi cấu trúc filter.
2. Tạo DN cho UID `doe, john` bằng LdapNameBuilder. Viết biểu diễn DN sau khi escape.
3. Tạo filter tìm `(member=<user DN>)`. Vì sao phải filter-escape DN string dù DN đã được escape theo RFC 4514?
4. Viết cùng một truy vấn equality bằng LdapQueryBuilder, LdapEncoder.filterEncode và JNDI parameterized search.
5. Một API nhận attribute, operator và value. Phần nào được parameterize/escape? Phần nào phải dùng allowlist?
6. Thiết kế prefix search sao cho dấu sao trong input là ký tự literal còn wildcard cuối do ứng dụng thêm.
7. Vì sao double-encoding `\2a` thành `\5c2a` làm thay đổi giá trị tìm kiếm?
8. Viết JUnit test cho NUL, ngoặc, backslash và Unicode.
9. Giải thích tại sao DN builder đúng không có nghĩa caller được phép thao tác entry đó.
10. Thiết kế integration test với hai group, chỉ một group chứa DN user có dấu phẩy trong RDN; xác minh filter không trả nhầm group.

## 19. Tài liệu tham khảo

- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter, assertion value và escaping octet.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cú pháp DN và escaping RDN/AVA.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, filter representation, search scope và result.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): LdapQueryBuilder, LdapQuery, LdapTemplate và search APIs.
- [Spring LDAP API — LdapEncoder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapEncoder.html): filterEncode cho assertion value.
- [Spring LDAP API — LdapNameBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapNameBuilder.html): dựng DN từ RDN components.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository query methods và ODM.
- [Oracle Java SE — DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html): JNDI search với filter expression và arguments.
- [Oracle JNDI Tutorial — LDAP Search](https://docs.oracle.com/javase/jndi/tutorial/ldap/search/search.html): search filter và parameterized search.
