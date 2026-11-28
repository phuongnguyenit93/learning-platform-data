# Điều kiện chuỗi con, tiền tố và hậu tố trong bộ lọc LDAP

Trong **Spring Data LDAP**, ứng dụng có thể tìm entry theo thuộc tính như `uid`, `cn`, `sn` hoặc `mail` bằng repository và `LdapTemplate`. Không phải yêu cầu nào cũng là so sánh bằng: hộp gợi ý tên có thể cần người dùng có tên **bắt đầu bằng** một cụm từ, màn hình tra cứu cần tên **chứa** một đoạn, hoặc nghiệp vụ cần tên **kết thúc bằng** một hậu tố. LDAP biểu diễn các kiểu tìm này bằng **substring assertion** trong search filter.

Bài này tập trung vào **điều kiện chuỗi con, tiền tố và hậu tố**: cú pháp LDAP, cách xây filter với Spring LDAP, phân biệt ký tự `*` làm wildcard với dấu `*` là dữ liệu thật, cách kết hợp với các điều kiện khác và những đánh đổi về hiệu năng, schema, bảo mật.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Đọc và tự viết filter tìm theo tiền tố, hậu tố, chuỗi con bằng cú pháp RFC 4515.
- Phân biệt **equality**, **presence** và **substring** để không viết nhầm điều kiện.
- Dùng `LdapQueryBuilder` với `like(...)` khi mẫu wildcard do ứng dụng kiểm soát.
- Xây filter có wildcard cố định quanh **giá trị đầu vào được escape** để không tạo LDAP injection.
- Hiểu sự khác nhau giữa điều kiện substring trên LDAP và biểu thức SQL `LIKE` hoặc regular expression.
- Giới hạn search base/scope, trả ít thuộc tính, kiểm thử kết quả đúng và đo chi phí tìm kiếm.

## 2. Dữ liệu minh họa và ý nghĩa của wildcard

Giả sử directory có các entry dưới `ou=people,dc=example,dc=com`:

```ldif
dn: uid=alice,ou=people,dc=example,dc=com
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen

dn: uid=alicia,ou=people,dc=example,dc=com
objectClass: inetOrgPerson
uid: alicia
cn: Alicia Tran
sn: Tran

dn: uid=bob,ou=people,dc=example,dc=com
objectClass: inetOrgPerson
uid: bob
cn: Bob Alice
sn: Alice

dn: uid=nguyen,ou=people,dc=example,dc=com
objectClass: inetOrgPerson
uid: nguyen
cn: Nguyen Alice
sn: Alice
```

Đây là các thuộc tính tiêu biểu cho ví dụ tìm kiếm; một entry hợp lệ trên directory thực tế phải có đủ `objectClass` và thuộc tính bắt buộc theo schema được cấu hình.

LDAP search filter dùng cú pháp dạng chuỗi như:

```ldap
(cn=Alice Nguyen)
```

Một dấu sao `*` **không được escape** trong giá trị của substring filter biểu thị vị trí có thể khớp với một chuỗi bất kỳ, kể cả chuỗi rỗng. Trong LDAP, `*` **không phải** ký hiệu lặp lại ký tự ngay trước nó như một số regular expression. Nó cũng không làm cho cả filter trở thành regex.

| Ý định | Filter LDAP | Ý nghĩa |
| --- | --- | --- |
| Bằng chính xác | `(cn=Alice Nguyen)` | So khớp theo matching rule cho equality của `cn`. |
| Có thuộc tính | `(cn=*)` | Entry có `cn`; đây là **presence filter**. |
| Bắt đầu bằng | `(cn=Ali*)` | Giá trị `cn` bắt đầu bằng `Ali`. |
| Kết thúc bằng | `(cn=*Alice)` | Giá trị `cn` kết thúc bằng `Alice`. |
| Chứa chuỗi con | `(cn=*Alice*)` | Giá trị `cn` có chuỗi `Alice` ở bất kỳ vị trí nào. |
| Nhiều đoạn theo thứ tự | `(cn=Al*Nguyen)` | Bắt đầu với `Al`, sau đó có thể có nội dung khác trước đoạn kết `Nguyen`. |

Các ví dụ giả định directory hỗ trợ phép matching substring đối với thuộc tính `cn`. Việc phân biệt chữ hoa/chữ thường, dấu tiếng Việt và các dạng Unicode tương đương do **matching rule của thuộc tính trong schema và cách directory triển khai** quyết định; không nên mặc định filter LDAP áp dụng so sánh chuỗi giống `String.contains()` của Java.

## 3. Điều kiện tiền tố: `prefix*`

**Prefix search** tìm giá trị bắt đầu với một đoạn cố định. Filter:

```ldap
(cn=Ali*)
```

với dữ liệu minh họa có thể trả về `Alice Nguyen` và `Alicia Tran`. Giá trị `Bob Alice` không khớp vì đoạn `Ali` không ở đầu.

### Khi nào nên dùng?

- Gợi ý người dùng khi gõ vài chữ đầu của tên.
- Tra cứu theo mã có tiền tố được quy ước, chẳng hạn `uid=emp*`.
- Hạn chế phạm vi tìm khi có quy tắc định danh theo nhóm.

Một câu tìm theo tiền tố thường dễ diễn đạt cho người dùng hơn so với tìm ở bất kỳ vị trí nào. Tùy server và index, nó **có thể** thuận lợi hơn truy vấn có wildcard ở đầu, nhưng cần đo trên directory thật.

### Viết với `LdapQueryBuilder`

Spring LDAP cung cấp `org.springframework.ldap.query.LdapQueryBuilder`. Khi mẫu `Ali*` là **hằng số do ứng dụng định nghĩa**, có thể dùng `like(...)`:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery prefixQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid", "cn")
        .where("cn").like("Ali*");

List<String> names = ldapTemplate.search(
        prefixQuery,
        (AttributesMapper<String>) attrs ->
                attrs.get("cn").get().toString()
);
```

Trong ví dụ, `spring.ldap.base` có thể được cấu hình thành `dc=example,dc=com`. Khi đó `base("ou=people")` là DN **tương đối với context base**. Scope `ONELEVEL` chỉ tìm những entry là con trực tiếp, và `attributes("uid", "cn")` chỉ yêu cầu dữ liệu mapper/UI cần.

**Chú ý:** `like(...)` dành cho **mẫu tìm kiếm có wildcard**. Đừng ghép trực tiếp dữ liệu request như `where("cn").like(prefixFromRequest + "*")` nếu chưa có cơ chế kiểm soát/escape phù hợp: dấu `*` hay cấu trúc khác do người dùng đưa vào có thể thay đổi ý nghĩa filter. Phần 7 minh họa cách thêm wildcard an toàn quanh dữ liệu đã được encode.

## 4. Điều kiện hậu tố: `*suffix`

**Suffix search** chọn giá trị kết thúc bằng một đoạn nhất định:

```ldap
(cn=*Alice)
```

Trong ví dụ, `Bob Alice` và `Nguyen Alice` khớp. `Alice Nguyen` không khớp vì `Alice` nằm ở đầu.

Với mẫu do ứng dụng kiểm soát:

```java
LdapQuery suffixQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .where("cn").like("*Alice");
```

Không nên nhầm hậu tố với **đuôi DN**. Filter trên so sánh **giá trị thuộc tính `cn`**, hoàn toàn khác với việc kiểm tra entry có nằm dưới nhánh DN `ou=people,dc=example,dc=com` hay không. Quan hệ cha–con của entry do search base và scope quyết định.

Suffix search có ích khi dữ liệu có quy tắc kết thúc chuỗi rõ ràng, nhưng wildcard ở đầu có thể khiến một số server/index khó tối ưu hơn. Đừng giả định mọi directory đánh index cho phép substring với hiệu quả giống nhau.

## 5. Điều kiện chứa chuỗi con: `*fragment*`

**Contains search** tìm một đoạn nằm ở bất kỳ vị trí nào trong giá trị:

```ldap
(cn=*Alice*)
```

Với dữ liệu mẫu, filter có thể khớp `Alice Nguyen`, `Bob Alice` và `Nguyen Alice`. Đây là một trường hợp **substring**, không phải phép so khớp bằng chính xác.

Ví dụ query builder với mẫu cố định:

```java
LdapQuery containsQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .where("cn").like("*Alice*");
```

Một số ứng dụng cung cấp ô “Tìm kiếm mọi vị trí” nhưng không giới hạn số ký tự hoặc kết quả. Với directory lớn, filter dạng `*fragment*` có thể cho nhiều kết quả và tạo tải. Nên quy định **độ dài tối thiểu** của chuỗi tìm, giới hạn base/scope, giới hạn số kết quả và đo thực tế. Nếu nghiệp vụ chỉ cần gợi ý khi gõ đầu tên, ưu tiên kiểu tiền tố thay vì tự chọn contains.

### Nhiều đoạn substring có thứ tự

LDAP cho phép một giá trị tìm gồm đoạn đầu, những đoạn giữa và đoạn cuối:

```ldap
(cn=Al*ce*Nguyen)
```

Đây là một **substring assertion**: bắt đầu bằng `Al`, sau đó có đoạn `ce` và kết thúc bằng `Nguyen`, theo đúng thứ tự. Các đoạn giữa có thể có các ký tự khác xen vào. Cú pháp này không phải “chứa ba từ ở vị trí bất kỳ”, cũng không có ý nghĩa sắp xếp hoặc so sánh số.

Nên cân nhắc mức độ phức tạp của kiểu tìm này: người dùng có thể khó dự đoán kết quả nếu UI không giải thích cách các đoạn được so khớp.

## 6. So sánh equality, presence và substring

Tập lệnh sau **không tương đương**:

```ldap
(uid=alice)       # Equality: uid bằng alice theo matching rule.
(uid=*)           # Presence: uid tồn tại.
(uid=ali*)        # Prefix: uid bắt đầu bằng ali.
(uid=*ice)        # Suffix: uid kết thúc bằng ice.
(uid=*lic*)       # Contains: uid chứa lic.
(uid=\2a)         # Equality: uid chứa đúng ký tự dấu sao.
```

Các dòng có chú thích chỉ để minh họa và **không phải một chuỗi filter duy nhất** gửi nguyên văn tới LDAP. Khi gọi API, mỗi filter phải là biểu thức hợp lệ, không mang chú thích `# ...` sau nó.

Điểm quan trọng: `(uid=*)` là **presence filter**, còn `(uid=\2a)` biểu diễn giá trị literal `*`. Sự khác biệt nằm ở việc dấu sao được escape hay chưa.

Trong Spring LDAP, tìm bằng chính xác nên dùng `is(...)`:

```java
LdapQuery exactUid = query()
        .base("ou=people")
        .where("uid").is(uidFromRequest);
```

API `is(...)` xử lý giá trị như dữ liệu trong equality filter; đừng đổi sang `like(...)` chỉ vì muốn tìm một chuỗi do người dùng nhập nếu không có yêu cầu wildcard.

## 7. Dữ liệu người dùng và wildcard: mã hóa đúng ngữ cảnh

### 7.1. Vấn đề khi nối trực tiếp input

Giả sử trang tra cứu tên dùng:

```java
// Không an toàn: user input có thể thay đổi mẫu filter.
String filter = "(cn=*" + searchTextFromRequest + "*)";
```

Nếu người dùng nhập `*`, filter được tạo thành `(cn=***)`, có thể mở rộng tìm kiếm ngoài dự kiến và hoạt động khác với yêu cầu “tìm ký tự dấu sao”. Đầu vào chứa `(`, `)`, `\` hoặc byte NUL còn có thể làm sai cú pháp.

**RFC 4515** quy định cách escape cho giá trị trong search filter:

| Ký tự cần tìm như dữ liệu | Biểu diễn trong filter |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| NUL (U+0000) | `\00` |

Phải **escape phần dữ liệu trước, rồi thêm wildcard có chủ đích**. Không dùng hàm escape DN/RDN để xử lý filter: DN tuân theo cú pháp khác (RFC 4514).

### 7.2. Dùng `LdapEncoder.filterEncode` cho phần literal

Spring LDAP cung cấp `org.springframework.ldap.support.LdapEncoder.filterEncode(...)` để mã hóa giá trị filter. Khi cần một API cho người dùng chọn loại khớp và nhập một **chuỗi literal**, ứng dụng có thể cố định tên thuộc tính và cấu trúc filter:

```java
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapEncoder;

public class PersonNameSearch {
    public enum MatchMode {
        EXACT, STARTS_WITH, ENDS_WITH, CONTAINS
    }

    private final LdapTemplate ldapTemplate;

    public PersonNameSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public static String cnFilter(String literal, MatchMode mode) {
        if (literal == null || literal.isBlank()) {
            throw new IllegalArgumentException("Từ khóa không được rỗng");
        }
        if (literal.length() > 80) {
            throw new IllegalArgumentException("Từ khóa quá dài");
        }
        if (mode == null) {
            throw new IllegalArgumentException("Thiếu kiểu tìm kiếm");
        }

        // Chỉ mã hóa dữ liệu. Các dấu * dưới đây do ứng dụng thêm vào.
        String encoded = LdapEncoder.filterEncode(literal);
        String assertion = switch (mode) {
            case EXACT -> encoded;
            case STARTS_WITH -> encoded + "*";
            case ENDS_WITH -> "*" + encoded;
            case CONTAINS -> "*" + encoded + "*";
        };

        // objectClass và cn là tên thuộc tính do ứng dụng cố định.
        return "(&(objectClass=inetOrgPerson)(cn=" + assertion + "))";
    }

    public List<String> searchNames(String keyword, MatchMode mode) {
        String filter = cnFilter(keyword, mode);

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"cn"});
        controls.setCountLimit(100);
        controls.setTimeLimit(2000);

        return ldapTemplate.search(
                "ou=people",
                filter,
                controls,
                (AttributesMapper<String>) attrs ->
                        attrs.get("cn").get().toString()
        );
    }
}
```

Ví dụ input `Al*ce` và mode `CONTAINS` tạo phần điều kiện `(cn=*Al\2ace*)`: dấu sao do người dùng nhập trở thành **ký tự literal cần tìm**, còn hai dấu sao ở đầu/cuối là wildcard do ứng dụng chủ động thêm. Với mode `EXACT`, input `*` tạo điều kiện `(cn=\2a)`, không biến thành presence filter.

Đoạn mã trên cố định `objectClass`, thuộc tính `cn` và base `ou=people`, nên không cho request thay đổi cấu trúc LDAP filter. Với môi trường có nhiều trường được phép tìm, tạo **allowlist** ánh xạ lựa chọn nghiệp vụ (ví dụ `displayName` → `cn`) sang tên LDAP đã biết; không nhận tên thuộc tính hoặc cả filter do client tự gửi.

`filterEncode` mã hóa **giá trị**, còn các dấu sao wildcard do code thêm sau đó được giữ nguyên như cú pháp. Đây là ngoại lệ có kiểm soát cho tình huống xây substring filter động; khi chỉ cần equality, `LdapQueryBuilder.where(...).is(...)` hoặc `EqualsFilter` là lựa chọn đơn giản hơn.

**Giới hạn ví dụ:** cách kiểm tra `literal.isBlank()` và độ dài chỉ là quy tắc ứng dụng. Dữ liệu có tiếng Việt, Unicode hoặc dấu câu vẫn phải được biểu diễn và so khớp theo matching rule của directory. Tùy yêu cầu nghiệp vụ, có thể đặt giới hạn độ dài tối thiểu cho mode `CONTAINS` để tránh truy vấn quá rộng.

## 8. Kết hợp substring với điều kiện logic

Filter LDAP hỗ trợ AND/OR/NOT:

```ldap
(&(objectClass=inetOrgPerson)(cn=Ali*))
```

Filter trên yêu cầu entry thuộc `inetOrgPerson` **và** có `cn` bắt đầu bằng `Ali`. Dùng query builder cho **mẫu tin cậy do ứng dụng định nghĩa**:

```java
LdapQuery q = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("cn").like("Ali*");
```

Ví dụ OR:

```ldap
(|(cn=Ali*)(sn=Nguyen))
```

Nó có nghĩa entry có `cn` bắt đầu bằng `Ali` **hoặc** `sn` bằng `Nguyen`, không phải cả hai. Khi kết hợp các biểu thức, tránh nhầm thứ tự group, đặc biệt nếu có AND và OR cùng lúc. Dùng cấu trúc filter builder hoặc các biểu thức rõ ràng thay vì ghép chuỗi logic tùy tiện.

Không phải mọi attribute type đều có matching rule hỗ trợ substring. Nếu directory báo lỗi hoặc không trả kết quả dự kiến cho một thuộc tính, cần kiểm tra **schema, matching rule, ACL và index**, không tự coi thuộc tính bất kỳ cũng có `contains` hoạt động tương tự `cn`.

## 9. Hiệu năng và tính đúng đắn khi tìm chuỗi con

Substring filter có thể tốn tài nguyên, nhất là khi:

- Kết quả có thể khớp rất nhiều entry (ví dụ từ khóa chỉ một ký tự).
- Bộ lọc bắt đầu bằng wildcard (`*frag*`, `*suffix`) và directory không có index phù hợp.
- Client tìm từ base quá rộng, dùng scope `SUBTREE` dù chỉ cần con trực tiếp.
- API trả mọi thuộc tính của mỗi entry hoặc không đặt giới hạn số kết quả.

Các biện pháp cải thiện:

1. **Chọn kiểu khớp từ nhu cầu:** dùng `is(...)` cho exact; `prefix*` khi người dùng nhập đầu tên; `*fragment*` chỉ khi nghiệp vụ cần.
2. **Giới hạn miền tìm:** `base("ou=people")`, `SearchScope.ONELEVEL` nếu chỉ cần con trực tiếp hoặc `SUBTREE` nếu các OU con cũng chứa người dùng hợp lệ.
3. **Chỉ trả trường cần dùng:** `attributes("uid", "cn")` trong `LdapQueryBuilder` hoặc `setReturningAttributes(...)` với `SearchControls`.
4. **Đặt giới hạn số lượng và thời gian:** phù hợp với UI; xử lý khi kết quả bị giới hạn thay vì coi danh sách là đầy đủ.
5. **Đo thực tế:** so sánh latency p50/p95, số entry trả về, kích thước phản hồi và metrics server; kiểm tra index và matching rules với quản trị directory.

Đừng khẳng định truy vấn tiền tố **luôn** nhanh hơn truy vấn chứa chuỗi con. Mức độ hỗ trợ index cho substring, tính chọn lọc của dữ liệu, cache và cách máy chủ thực thi có thể tạo kết quả khác nhau. Thay đổi scope sang `ONELEVEL` có thể “nhanh” đơn giản vì bỏ qua entry hợp lệ ở OU con; đó là sai chức năng nếu cần tìm toàn subtree.

## 10. Kiểm thử cú pháp, escaping và kết quả

Kiểm thử nên có **hai tầng**: unit test xác minh phần cấu trúc/filter được tạo ra và integration test xác minh directory trả đúng entry với schema/matching rule thật.

### 10.1. Unit test cho literal và wildcard

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class PersonNameSearchTest {
    @Test
    void addsWildcardsOnlyForSelectedMode() {
        assertEquals(
                "(&(objectClass=inetOrgPerson)(cn=Ali*))",
                PersonNameSearch.cnFilter(
                        "Ali", PersonNameSearch.MatchMode.STARTS_WITH)
        );
        assertEquals(
                "(&(objectClass=inetOrgPerson)(cn=*Alice))",
                PersonNameSearch.cnFilter(
                        "Alice", PersonNameSearch.MatchMode.ENDS_WITH)
        );
        assertEquals(
                "(&(objectClass=inetOrgPerson)(cn=*Alice*))",
                PersonNameSearch.cnFilter(
                        "Alice", PersonNameSearch.MatchMode.CONTAINS)
        );
    }

    @Test
    void treatsUserAsteriskAsLiteralCharacter() {
        assertEquals(
                "(&(objectClass=inetOrgPerson)(cn=*Al\\2ace*))",
                PersonNameSearch.cnFilter(
                        "Al*ce", PersonNameSearch.MatchMode.CONTAINS)
        );
    }
}
```

Trong Java string literal `"\\2a"` biểu diễn một dấu `\` theo sau bởi `2a` trong filter đã mã hóa. Cách biểu diễn hex có thể khác nhau về chữ hoa/chữ thường tùy encoder; test ví dụ minh họa dạng được sử dụng trong Spring LDAP thông thường.

### 10.2. Integration test với directory

Chuẩn bị các entry có `cn` lần lượt là `Alice Nguyen`, `Alicia Tran`, `Bob Alice`, `Nguyen Alice` và một entry có giá trị chứa dấu `*` nếu schema/directory cho phép. Từ cùng base/scope và tài khoản LDAP:

| Kiểu tìm | Từ khóa | Kết quả mong đợi theo dữ liệu mẫu |
| --- | --- | --- |
| `EXACT` | `Alice Nguyen` | Chỉ entry có `cn` bằng `Alice Nguyen`. |
| `STARTS_WITH` | `Ali` | `Alice Nguyen`, `Alicia Tran`. |
| `ENDS_WITH` | `Alice` | `Bob Alice`, `Nguyen Alice`. |
| `CONTAINS` | `Alice` | `Alice Nguyen`, `Bob Alice`, `Nguyen Alice`. |
| `CONTAINS` | `*` | Chỉ entry có **dấu sao thật** trong `cn`, không phải tất cả entry. |

Đối chiếu theo DN/ID của entry để tránh hiểu nhầm nếu có nhiều entry cùng `cn`; LDAP không bảo đảm thứ tự kết quả mặc định. Nếu thử nghiệm so khớp dấu tiếng Việt hoặc chữ hoa/thường, ghi rõ schema/matching rule đang sử dụng và điều chỉnh kỳ vọng theo directory thực tế.

Các trường hợp nên thử thêm: từ khóa rỗng; khoảng trắng ở đầu/cuối; ký tự `(`, `)`, `\`; Unicode; đầu vào rất dài; không có entry khớp; tìm trong OU con; tài khoản không có quyền đọc một số thuộc tính; kết quả bị giới hạn bởi server.

## 11. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `(cn=*)` để tìm dấu `*` | Biến equality thành kiểm tra tồn tại thuộc tính. | Tìm literal `*` bằng `\2a` hoặc builder mã hóa đúng. |
| Ghép raw input vào `(cn=*...*)` | Người dùng có thể thay đổi cú pháp/wildcard. | Escape giá trị trước, chỉ thêm wildcard cố định do ứng dụng quyết định. |
| Dùng `like(...)` cho mọi input như equality | Tạo tìm kiếm rộng hoặc không đúng ý người dùng. | Tách rõ mode `EXACT` và các mode substring. |
| Nhầm suffix của `cn` với hậu tố DN | Chọn sai nhánh/thực thể. | Dùng base/scope cho cây LDAP, substring filter cho giá trị thuộc tính. |
| Giả định mọi thuộc tính hỗ trợ substring | Truy vấn không khớp hoặc không được server hỗ trợ như dự kiến. | Đối chiếu schema và matching rules. |
| Xem `*` như regex `.*` hoặc dùng ký tự `?` | Viết pattern sai ý nghĩa LDAP. | Theo cú pháp RFC 4515 và substring assertion của LDAP. |
| Không giới hạn base, scope, số kết quả | Truy vấn contains có thể rất tốn tài nguyên. | Thu hẹp phạm vi, projection, size/time limit và đo thực tế. |
| So sánh kết quả theo thứ tự LDAP mặc định | Test có thể thất bại khi server đổi thứ tự. | So sánh theo tập DN hoặc định danh của entry. |

## 12. Bài tập thực hành

**Bài 1.** Hãy viết filter tìm `cn` bắt đầu bằng `Mai`, kết thúc bằng `Tran` và chứa `Anh`.

**Đáp án:** Lần lượt `(cn=Mai*)`, `(cn=*Tran)` và `(cn=*Anh*)`. Đây là ba kiểu khớp độc lập; nếu muốn đầu và cuối cùng xuất hiện trong một tên, có thể dùng `(cn=Mai*Tran)`.

**Bài 2.** Một người dùng nhập dấu `*` vào ô “Tìm giá trị uid chính xác”. Filter `(uid=*)` có đúng yêu cầu không?

**Đáp án:** Không. Nó kiểm tra `uid` tồn tại. Giá trị `*` theo nghĩa literal phải được escape thành `\2a`, dẫn tới filter `(uid=\2a)`; với Spring LDAP nên dùng `where("uid").is(input)` cho equality.

**Bài 3.** Tìm `cn` chứa `Alice` dưới `ou=people` nhưng directory còn có OU `contractors` chứa người dùng. Cần scope nào?

**Đáp án:** Chọn `SUBTREE` nếu cần cả các entry trong OU con. `ONELEVEL` sẽ không xét hậu duệ cấp sâu hơn, dù filter `(cn=*Alice*)` có đúng.

**Bài 4.** Vì sao không cho client gửi cả `(cn=*Alice*)` rồi truyền nguyên vẹn vào tham số filter?

**Đáp án:** Client khi đó kiểm soát toàn bộ cấu trúc filter, có thể thay đổi thuộc tính, điều kiện logic hoặc wildcard. API nên nhận **từ khóa literal** và **mode từ tập cho phép**; ứng dụng tự xây bộ lọc với escape và wildcard có chủ đích.

**Bài 5.** Trong cùng directory, kết quả của `(cn=*Alice*)` có bắt buộc giống `String.contains("Alice")` của Java không?

**Đáp án:** Không. LDAP áp dụng matching rule cho thuộc tính và cách server xử lý chuẩn hóa/case/Unicode. Java `String.contains` kiểm tra chuỗi theo quy tắc Java tại client; muốn so sánh phải xác định matching rule thực tế.

## 13. Ghi nhớ

- **Tiền tố:** `(cn=Ali*)`; **hậu tố:** `(cn=*Alice)`; **chứa chuỗi con:** `(cn=*Ali*)`.
- `(cn=*)` là **presence**, còn `(cn=\2a)` tìm dấu sao **literal**. Equality, substring và presence không được xem là tương đương.
- Dùng `LdapQueryBuilder.where(...).like(...)` cho **mẫu wildcard đáng tin cậy**; với giá trị request, escape literal bằng encoder filter phù hợp và thêm wildcard do code kiểm soát.
- Substring là phép khớp theo **schema/matching rule LDAP**, không phải regular expression hay SQL `LIKE` hoàn chỉnh.
- Kết hợp filter với **search base, scope, returning attributes, giới hạn kết quả và ACL** để bảo đảm chức năng, hiệu năng và quyền truy cập.
- Kiểm thử cả cú pháp mã hóa lẫn kết quả trên directory với dữ liệu thực tế trước khi đưa tính năng tìm chuỗi con vào sử dụng.
