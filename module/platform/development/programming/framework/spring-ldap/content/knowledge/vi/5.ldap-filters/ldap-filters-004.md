# Greater-than-or-equal và less-than-or-equal filter trong LDAP

## 1. Khi nào cần lọc dữ liệu theo khoảng?

Một ứng dụng dùng **Spring LDAP** thường tìm entry theo điều kiện bằng nhau, chẳng hạn `(uid=alice)`. Tuy nhiên, nhiều bài toán cần xác định **ngưỡng dưới**, **ngưỡng trên** hoặc một **khoảng giá trị**:

- Tìm tài khoản được tạo từ một thời điểm nhất định.
- Liệt kê những entry được cập nhật trước một mốc thời gian phục vụ kiểm tra vận hành.
- Lọc một thuộc tính số có quy tắc so sánh thứ tự, nếu schema thư mục hỗ trợ.
- Kết hợp điều kiện khoảng với `objectClass`, trạng thái tài khoản hoặc một nhánh OU cụ thể.

LDAP cung cấp hai phép so sánh thứ tự trong cú pháp **search filter**:

```ldap
(attribute>=value)
(attribute<=value)
```

Trong đó `>=` là **greater-than-or-equal** (lớn hơn hoặc bằng), còn `<=` là **less-than-or-equal** (nhỏ hơn hoặc bằng). Cả hai **bao gồm** giá trị biên. Đây là toán tử của LDAP filter, không phải cú pháp của DN, Java hay SQL.

Bài học thuộc chương **Filter LDAP** và tập trung vào việc xây dựng, chạy, giải thích kết quả hai loại filter trong Spring LDAP. Để sử dụng đúng, cần hiểu schema, matching rule, DN/base, search scope, escaping và cách kiểm thử truy vấn trên dịch vụ thư mục an toàn.

## 2. Cú pháp và ý nghĩa của `>=` và `<=`

### 2.1. Tìm từ ngưỡng dưới trở lên

Ví dụ tìm các entry có thời điểm tạo không sớm hơn 00:00 UTC ngày 1/1/2026:

```ldap
(createTimestamp>=20260101000000Z)
```

`createTimestamp` là thuộc tính vận hành thường lưu thời điểm tạo entry theo dạng LDAP **Generalized Time**. Chuỗi `20260101000000Z` biểu diễn thời điểm UTC. Một entry được tạo **đúng** thời điểm này cũng thỏa điều kiện vì toán tử có dấu bằng.

### 2.2. Tìm đến ngưỡng trên

Ví dụ tìm các entry có thời điểm tạo không muộn hơn 23:59:59 UTC ngày 31/1/2026:

```ldap
(createTimestamp<=20260131235959Z)
```

Điều kiện này cũng bao gồm giá trị biên. Một số máy chủ có thể ghi thời gian với độ chính xác phân số giây; giá trị `20260131235959.5Z` nằm **sau** mốc `20260131235959Z`, nên không thuộc ví dụ khoảng trên. Khi cần ranh giới ngày thật chính xác, hãy xác định cách biểu diễn thời gian và độ chính xác mà máy chủ hỗ trợ.

### 2.3. Tạo khoảng đóng bằng AND

Để tìm các entry được tạo trong khoảng từ 00:00 UTC ngày 1/1 đến đúng 23:59:59 UTC ngày 31/1/2026:

```ldap
(&(createTimestamp>=20260101000000Z)(createTimestamp<=20260131235959Z))
```

Cấu trúc `&` là phép **AND**, buộc cả hai điều kiện cùng đúng. Đây là một **khoảng đóng** `[lower, upper]` vì cả hai đầu mút đều được tính. Với một thuộc tính thời gian đơn trị như `createTimestamp`, cách diễn giải là một giá trị phải nằm giữa hai mốc theo matching rule của máy chủ.

Nếu chỉ quan tâm những entry thuộc kiểu `inetOrgPerson`, có thể thêm điều kiện:

```ldap
(&(objectClass=inetOrgPerson)
  (createTimestamp>=20260101000000Z)
  (createTimestamp<=20260131235959Z))
```

Biểu thức trên xuống dòng để dễ đọc. Khi truyền cho các LDAP client, hãy sử dụng một chuỗi filter hợp lệ không có khoảng trắng ngoài ý muốn giữa các phần, ví dụ:

```ldap
(&(objectClass=inetOrgPerson)(createTimestamp>=20260101000000Z)(createTimestamp<=20260131235959Z))
```

### 2.4. Bảng diễn giải nhanh

| Filter | Câu hỏi mà filter trả lời | Tính biên |
| --- | --- | --- |
| `(attr>=x)` | Giá trị thuộc tính có lớn hơn hoặc bằng `x` không? | Gồm `x` |
| `(attr<=x)` | Giá trị thuộc tính có nhỏ hơn hoặc bằng `x` không? | Gồm `x` |
| `(&(attr>=a)(attr<=b))` | Hai điều kiện biên cùng đúng không? | Gồm `a` và `b` nếu so sánh phù hợp |
| `(|(attr<=a)(attr>=b))` | Thuộc tính có thỏa ngưỡng thấp **hoặc** ngưỡng cao không? | Gồm `a` và `b` |
| `(attr=*)` | Entry có ít nhất một giá trị của thuộc tính không? | Kiểm tra hiện diện, không so sánh thứ tự |

Ở bảng trên, `attr`, `x`, `a`, `b` là ký hiệu minh họa. Trong truy vấn thật, phải thay bằng tên thuộc tính và giá trị hợp lệ theo schema.

## 3. Điều kiện tiên quyết: attribute phải có ordering matching rule

Điểm dễ nhầm nhất là nghĩ rằng LDAP tự so sánh mọi thuộc tính theo số hoặc theo thứ tự từ điển. **Không phải thuộc tính nào cũng hỗ trợ so sánh thứ tự.**

LDAP schema có thể định nghĩa các matching rule như:

- **Equality matching rule**: xử lý điều kiện bằng nhau, ví dụ `(uid=alice)`.
- **Ordering matching rule**: xử lý điều kiện `>=` và `<=`.
- **Substring matching rule**: xử lý các điều kiện tìm một phần chuỗi bằng `*`, nếu thuộc tính hỗ trợ.

Một attribute type có thể hỗ trợ equality nhưng không khai báo ordering. Khi đó, yêu cầu `(someAttribute>=x)` có thể không trả về kết quả như kỳ vọng, hoặc máy chủ có thể trả lỗi về phép so khớp không phù hợp, chẳng hạn LDAP result code **18 (`inappropriateMatching`)**. Hành vi chi tiết phụ thuộc schema và triển khai máy chủ.

### 3.1. So sánh số khác so sánh chuỗi

Giả sử có một thuộc tính **tự định nghĩa** tên `appScore` theo cú pháp số nguyên, với ordering matching rule dành cho số nguyên. Khi đó:

```ldap
(appScore>=10)
```

được hiểu theo **thứ tự số**, nếu server thực sự hỗ trợ thuộc tính và matching rule đã khai báo. Giá trị `12` lớn hơn `10`, còn `9` không thỏa.

Ngược lại, một thuộc tính chuỗi với phép so sánh thứ tự kiểu chữ không có nghĩa tuân theo thứ tự số. Ví dụ, trong một số cách so sánh chuỗi, `"100"` có thể đứng trước `"20"`. **Không đổi kiểu dữ liệu hoặc dùng filter trực tiếp trên một thuộc tính chuỗi để giả lập so sánh số**, trừ khi schema và quy tắc chuẩn hóa của thư mục đã được xác nhận.

`appScore` trong bài là thuộc tính giả định phục vụ giải thích, **không phải thuộc tính mặc định** của `inetOrgPerson`. Muốn dùng thực tế, quản trị viên phải có định nghĩa attribute type, ordering matching rule và object class cho phép thuộc tính đó; ứng dụng không tự tạo schema bằng `LdapTemplate`.

### 3.2. Thời gian cần định dạng và múi giờ phù hợp

Với thuộc tính kiểu Generalized Time và matching rule phù hợp, máy chủ có thể so sánh thứ tự thời điểm. Hãy chuẩn hóa đầu vào về UTC khi tạo filter, ví dụ `20260101000000Z`, thay vì tự so sánh chuỗi ngày theo định dạng hiển thị `01/01/2026`.

Khi xử lý ngày trên Java:

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

DateTimeFormatter ldapUtcTime = DateTimeFormatter
        .ofPattern("uuuuMMddHHmmss'Z'")
        .withZone(ZoneOffset.UTC);

String threshold = ldapUtcTime.format(
        Instant.parse("2026-01-01T00:00:00Z"));
// threshold = "20260101000000Z"
```

Formatter trên dùng độ chính xác **giây** và biểu diễn UTC. Nếu hệ thống nghiệp vụ cần mili-giây, phải thống nhất cách làm tròn và biên truy vấn với định dạng mà LDAP server hỗ trợ. Không trộn timezone địa phương vào chuỗi có hậu tố `Z`.

## 4. Thực hành truy vấn với `ldapsearch`

Giả sử máy chủ LDAP thử nghiệm có nhánh `ou=people,dc=example,dc=org` và các entry người dùng có thuộc tính `createTimestamp` có thể truy vấn. Một cách kiểm tra điều kiện ngưỡng dưới:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(createTimestamp>=20260101000000Z)" \
  dn cn createTimestamp
```

Để truy vấn một khoảng đóng:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(createTimestamp>=20260101000000Z)(createTimestamp<=20260131235959Z))" \
  dn cn createTimestamp
```

Các tham số cần chú ý:

| Tham số | Vai trò |
| --- | --- |
| `-H "ldaps://..."` | Kết nối LDAP qua TLS (cần cấu hình tin cậy chứng chỉ đúng) |
| `-D ... -W` | Dùng bind DN đã được cấp quyền và nhập mật khẩu theo lời nhắc |
| `-b ...` | DN gốc của thao tác tìm kiếm |
| `-s sub` | Tìm trong subtree của base DN, gồm cả base và các entry con |
| Filter trong dấu ngoặc kép | Điều kiện máy chủ sẽ đánh giá trên từng entry trong phạm vi truy vấn |
| `dn cn createTimestamp` | Chỉ yêu cầu một số thuộc tính để trả về; `createTimestamp` thường là operational attribute |

Nếu không thấy kết quả, kiểm tra lần lượt **base DN**, **search scope**, quyền đọc, sự hiện diện của thuộc tính, cấu hình schema và mốc thời gian. Đừng kết luận toán tử `>=` bị sai khi entry cần tìm nằm ở nhánh khác hoặc không được tài khoản bind nhìn thấy. Các máy chủ LDAP có thể không công bố `createTimestamp`, không cho phép lọc theo đó hoặc áp dụng quy tắc truy cập khác nhau.

## 5. Xây dựng filter trong Spring LDAP

### 5.1. Cấu hình `ContextSource` và `LdapTemplate`

Spring LDAP dùng `ContextSource` để quản lý truy cập LDAP và `LdapTemplate` để thực hiện tìm kiếm, đọc hoặc sửa entry. Ví dụ tối giản dùng cấu hình bên ngoài:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class LdapConfiguration {

    @Bean
    LdapContextSource contextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

```yaml
# application.yml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
```

Đây là kết nối ví dụ. Với `base = dc=example,dc=org`, lời gọi tìm kiếm có base tương đối `ou=people` sẽ truy vấn dưới `ou=people,dc=example,dc=org`. Base DN và filter có vai trò độc lập: **base xác định phạm vi gốc**, filter xác định **điều kiện chọn entry** trong phạm vi đó.

### 5.2. Dùng `GreaterThanOrEqualsFilter` và `LessThanOrEqualsFilter`

Spring LDAP có các đối tượng filter giúp xây cú pháp thay vì nối chuỗi thủ công. Với bài toán tìm tài khoản tạo trong một khoảng thời gian, có thể kết hợp chúng bằng `AndFilter`:

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.GreaterThanOrEqualsFilter;
import org.springframework.ldap.filter.LessThanOrEqualsFilter;
import org.springframework.stereotype.Repository;

@Repository
class DirectorySearchRepository {
    private static final DateTimeFormatter LDAP_UTC =
            DateTimeFormatter.ofPattern("uuuuMMddHHmmss'Z'")
                    .withZone(ZoneOffset.UTC);

    private final LdapTemplate ldapTemplate;

    DirectorySearchRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    List<String> findNamesCreatedBetween(
            Instant fromInclusive, Instant toInclusive) {
        if (fromInclusive.isAfter(toInclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }

        String from = LDAP_UTC.format(fromInclusive);
        String to = LDAP_UTC.format(toInclusive);

        AndFilter filter = new AndFilter();
        filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        filter.and(new GreaterThanOrEqualsFilter("createTimestamp", from));
        filter.and(new LessThanOrEqualsFilter("createTimestamp", to));

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"cn", "createTimestamp"});

        return ldapTemplate.search(
                "ou=people",
                filter.encode(),
                controls,
                (AttributesMapper<String>) attrs -> {
                    Attribute cn = attrs.get("cn");
                    return cn == null ? "" : String.valueOf(cn.get());
                }
        );
    }
}
```

Giải thích luồng xử lý:

1. `Instant` biểu diễn mốc thời gian độc lập múi giờ; formatter biến mốc đó thành Generalized Time UTC với độ chính xác giây.
2. `GreaterThanOrEqualsFilter` và `LessThanOrEqualsFilter` diễn đạt hai biên; `AndFilter` yêu cầu chúng cùng đúng và đồng thời giới hạn object class.
3. `filter.encode()` tạo chuỗi LDAP filter phù hợp. Việc truyền giá trị vào các lớp filter giúp tránh nối trực tiếp dữ liệu người dùng vào cú pháp LDAP.
4. `SearchControls` giới hạn scope và yêu cầu cụ thể thuộc tính cần trả về. `createTimestamp` thường không được trả về khi chỉ yêu cầu các thuộc tính thông thường.
5. `LdapTemplate.search(...)` thực hiện tìm kiếm và ánh xạ mỗi entry thành tên `cn`; ứng dụng nên quy định cách xử lý rõ ràng khi một thuộc tính tùy chọn vắng mặt.

Trong ví dụ này, thời gian được làm tròn về giây khi định dạng. Vì vậy, nếu nhận `Instant` chứa phần nano-giây thì việc định dạng có thể thay đổi ý nghĩa của biên. Đối với dữ liệu thực, hãy yêu cầu các mốc ở độ chính xác giây hoặc chuẩn hóa một cách tường minh theo yêu cầu nghiệp vụ trước khi gọi repository.

Các lớp `Filter` giúp xây **phần biểu thức** an toàn hơn, nhưng không tự xác minh attribute type có ordering matching rule, người dùng được phép tìm trên attribute đó hay query có được tối ưu bằng index hay không.

### 5.3. Nếu chỉ cần một ngưỡng

Bạn không bắt buộc phải có đủ hai điều kiện. Để lọc entry đã tạo kể từ một thời điểm, dùng riêng:

```java
String filter = new GreaterThanOrEqualsFilter(
        "createTimestamp", "20260101000000Z").encode();
// (createTimestamp>=20260101000000Z)
```

Hoặc để lọc đến một mốc xác định:

```java
String filter = new LessThanOrEqualsFilter(
        "createTimestamp", "20260131235959Z").encode();
// (createTimestamp<=20260131235959Z)
```

Nếu người học dùng `LdapClient` với phiên bản Spring LDAP có hỗ trợ API fluent, có thể kết hợp cùng `Filter`/builder tương ứng theo API của phiên bản đó. ODM ánh xạ entry sang lớp Java nhưng không đổi ngữ nghĩa matching rule của điều kiện tìm kiếm. Dù chọn `LdapTemplate`, `LdapClient` hay ODM, server LDAP vẫn là nơi đánh giá filter.

## 6. Những điểm dễ hiểu sai khi dùng phép so sánh thứ tự

### 6.1. LDAP không có toán tử chuẩn `>` và `<` trong cú pháp filter

Hai dạng so sánh thứ tự chuẩn là `>=` và `<=`. Không dùng trực tiếp:

```text
(appScore>10)   # Không phải cú pháp greater-than filter chuẩn
(appScore<20)   # Không phải cú pháp less-than filter chuẩn
```

Nếu bài toán cần **lớn hơn hẳn** một mốc đối với thuộc tính đơn trị, đôi khi có thể biểu đạt bằng `>=` cùng phủ định điều kiện bằng nhau:

```ldap
(&(appScore>=10)(!(appScore=10)))
```

Tuy nhiên, cách viết này chỉ phù hợp khi các matching rule và mô hình thuộc tính cho phép suy luận đó. Với thuộc tính **đa trị**, kết quả có thể khác ý định “tồn tại một giá trị lớn hơn 10”. Vì thế, nếu schema có thuộc tính đa trị, phải xem xét kỹ ngữ nghĩa trước khi tự chuyển đổi điều kiện so sánh nghiêm ngặt.

### 6.2. Điều kiện trên thuộc tính đa trị có thể khớp **hai giá trị khác nhau**

Giả sử thuộc tính giả định `appScore` được phép chứa nhiều giá trị, có **hai giá trị** `10` và `90`. Filter:

```ldap
(&(appScore>=50)(appScore<=70))
```

có thể khớp entry dù **không có giá trị nào** nằm trong đoạn `[50,70]`: `90` thỏa `>=50`, còn `10` thỏa `<=70`. Mỗi thành phần filter được đánh giá độc lập theo quy tắc so khớp của LDAP. Phép AND không tự ràng buộc hai phép so sánh phải áp dụng lên **cùng một giá trị** của thuộc tính đa trị.

Khi cần một khoảng trên một giá trị duy nhất, nên dùng thuộc tính có ràng buộc đơn trị (`SINGLE-VALUE`) hoặc thiết kế lại truy vấn/dữ liệu để thể hiện chính xác nhu cầu. `createTimestamp` thuộc nhóm thuộc tính vận hành thường đơn trị nên phù hợp hơn với cách minh họa khoảng thời gian.

### 6.3. Giá trị thiếu, quyền đọc và kết quả không khớp

Một entry không có thuộc tính cần so sánh thường không khớp filter yêu cầu thuộc tính đó. Nhưng với thuộc tính vận hành như `createTimestamp`, việc thuộc tính có được công bố, cho phép lọc hoặc hiển thị cho tài khoản bind hay không phụ thuộc máy chủ. Nếu truy vấn trả danh sách rỗng, hãy phân biệt:

- Đúng là không có entry nào thỏa điều kiện.
- Base DN/scope không bao phủ nơi entry đang tồn tại.
- Không có quyền truy cập hoặc máy chủ hạn chế tìm kiếm trên thuộc tính.
- Thuộc tính chưa được schema hỗ trợ so sánh thứ tự.
- Mốc thời gian được chuyển đổi sai múi giờ hoặc độ chính xác.

Khi LDAP server không thể đánh giá matching rule, nó có thể báo lỗi hoặc coi phép thử không khớp tùy ngữ nghĩa và cách triển khai. Chỉ nhìn số lượng kết quả là chưa đủ để kết luận nguyên nhân.

### 6.4. `>=` và `<=` không tự xác định thứ tự theo kiểu dữ liệu Java

Ví dụ, Java có thể so sánh `BigDecimal`, `Instant` hoặc `String`, nhưng LDAP server áp dụng **matching rule của attribute type**. Truy vấn `(appScore>=100)` không thành phép so sánh số chỉ vì ứng dụng dùng `Integer` hoặc `BigDecimal` khi tạo filter. Điều kiện đúng là schema của server phải hỗ trợ so sánh số thích hợp.

## 7. Escaping và bảo vệ truy vấn LDAP

Với filter nhận giá trị bên ngoài, không nối chuỗi kiểu:

```java
// Tránh xây LDAP filter từ dữ liệu không tin cậy như sau:
String unsafe = "(createTimestamp>=" + userInput + ")";
```

Theo cú pháp LDAP filter, những ký tự trong **giá trị** cần mã hóa đặc biệt bao gồm:

| Ký tự gốc | Mã hóa trong filter value |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| NUL | `\00` |

Đây là escaping cho **LDAP filter**, không phải escaping DN/RDN. Khi có sẵn `GreaterThanOrEqualsFilter`, `LessThanOrEqualsFilter` hoặc bộ dựng filter an toàn, hãy truyền **giá trị thô** vào builder; đừng tự escape hai lần. Đặc biệt, nếu ứng dụng nhận tên thuộc tính từ phía client, phải giới hạn tên đó trong một **danh sách được cho phép**: escaping giá trị không làm một tên thuộc tính tùy ý trở thành được phép truy vấn.

Ví dụ xây filter với giá trị lạ trong một thuộc tính có ordering rule phù hợp:

```java
String encoded = new GreaterThanOrEqualsFilter(
        "customOrderedAttr", "a*b").encode();
// Dấu * bên trong giá trị sẽ được mã hóa như một ký tự dữ liệu.
```

Đừng tự tạo filter bằng toán tử `>=` và nối `userInput`; cả các truy vấn không chứa wildcard chủ động cũng có thể bị phá cú pháp nếu đầu vào có dấu ngoặc hoặc dấu gạch chéo ngược. Ngoài tránh injection, hãy giới hạn độ dài đầu vào, khoảng truy vấn và thuộc tính có thể tìm để giảm nguy cơ truy vấn quá rộng hoặc tốn tài nguyên.

## 8. Search scope, hiệu năng và xử lý lỗi

### 8.1. Base DN và scope vẫn quyết định phần dữ liệu được xét

Filter không thể tìm ra entry nằm ngoài base DN đã chọn. Giả sử `ContextSource` có base `dc=example,dc=org` và bạn gọi `search("ou=people", ...)`, thì chỉ những entry trong vùng tìm kiếm bắt đầu tại `ou=people,dc=example,dc=org` mới được kiểm tra.

| Scope | Phạm vi tính từ `ou=people` | Khi nào nên dùng |
| --- | --- | --- |
| `OBJECT_SCOPE` / base | Chỉ entry `ou=people` | Kiểm tra thuộc tính của chính entry OU |
| `ONELEVEL_SCOPE` | Các entry con trực tiếp | Khi người dùng được lưu trực tiếp bên dưới OU |
| `SUBTREE_SCOPE` | Entry OU và mọi hậu duệ | Khi có nhiều OU con hoặc cần tìm nhiều cấp |

Hãy chọn base hẹp nhất vẫn bao quát dữ liệu mục tiêu. Truy vấn subtree với ngưỡng rất rộng có thể trả về nhiều entry; một filter hợp lệ về cú pháp vẫn có thể gây tải lớn nếu thuộc tính không có index phù hợp.

### 8.2. Đặt giới hạn thay vì đọc không kiểm soát

Có thể dùng `SearchControls` để giới hạn số lượng entry và thời gian chờ từ phía client:

```java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setCountLimit(500L);
controls.setTimeLimit(5000); // mili-giây
controls.setReturningAttributes(new String[] {"cn", "createTimestamp"});
```

Các giới hạn client không thay thế quy định và giới hạn phía server. Với thư mục lớn, hãy xem xét LDAP paging nếu server hỗ trợ và thuộc tính được lập chỉ mục phù hợp. Cơ chế pooling có thể giảm chi phí mở context trong một số môi trường, nhưng không thay thế tối ưu base, filter và index; khi bật pooling cần đánh giá tương tác với bind danh tính người dùng và TLS/StartTLS.

### 8.3. Phân biệt lỗi filter với lỗi kết nối và phân quyền

| Hiện tượng | Nguyên nhân có thể gặp | Hướng kiểm tra |
| --- | --- | --- |
| Truy vấn trả rỗng | Không có entry phù hợp, sai base/scope, thiếu quyền nhìn thấy entry hoặc matching rule không đánh giá được | Thử filter bằng nhau/hiện diện ở nhánh đúng và xem schema/ACL |
| LDAP result code **18** | `inappropriateMatching`: phép so khớp không phù hợp với thuộc tính | Kiểm tra thuộc tính có ordering matching rule hay không |
| LDAP result code **87** | `filterError`: bộ lọc không hợp lệ hoặc không phân tích được | Kiểm tra dấu ngoặc, toán tử và escaping |
| LDAP result code **50** | `insufficientAccessRights`: thiếu quyền | Xác nhận tài khoản bind/ACL, tránh tự tăng quyền |
| Timeout hoặc vượt giới hạn kết quả | Truy vấn quá rộng, index yếu hoặc giới hạn của server | Thu hẹp base/khoảng, dùng paging và giới hạn phù hợp |
| Lỗi TLS/bind/kết nối | Chứng chỉ không hợp lệ, mật khẩu sai, máy chủ không khả dụng | Kiểm tra truststore, tên máy chủ, cấu hình kết nối và log an toàn |

Một số máy chủ trả mã chẩn đoán khác hoặc không tiết lộ nguyên nhân chi tiết vì chính sách an toàn. Đừng biến mọi lỗi LDAP thành “không có bản ghi”, vì điều đó khiến ứng dụng che giấu sự cố vận hành. Cũng không trả nguyên diagnostic message có DN nội bộ hoặc dữ liệu nhạy cảm ra API công khai.

## 9. Kiểm thử filter theo các biên

Với thuộc tính `appScore` **giả định** đã được quản trị viên định nghĩa là số nguyên đơn trị và có ordering matching rule, xét bộ dữ liệu thử nghiệm:

| UID | `appScore` | `(appScore>=50)` | `(appScore<=70)` | Trong khoảng `[50,70]` |
| --- | ---: | :---: | :---: | :---: |
| `u40` | 40 | Không | Có | Không |
| `u50` | 50 | Có | Có | Có |
| `u60` | 60 | Có | Có | Có |
| `u70` | 70 | Có | Có | Có |
| `u80` | 80 | Có | Không | Không |

Với dữ liệu đơn trị và matching rule đúng, filter khoảng:

```ldap
(&(appScore>=50)(appScore<=70))
```

phải chọn `u50`, `u60`, `u70`. Những ca tại **đúng hai đầu biên** (`50`, `70`) đặc biệt quan trọng vì giúp phát hiện nhầm lẫn giữa `>` với `>=` hoặc `<` với `<=`.

### Các ca kiểm thử nên có

1. **Ngưỡng dưới:** xác nhận giá trị thấp hơn, bằng và cao hơn ngưỡng có kết quả tương ứng.
2. **Ngưỡng trên:** kiểm tra tương tự với mốc trên.
3. **Khoảng đóng:** xác nhận cả hai biên được bao gồm và entry ngoài khoảng bị loại.
4. **Biên ngược:** khi `lower > upper`, tầng ứng dụng phải phát hiện và phản hồi rõ ràng trước khi gửi truy vấn.
5. **Thuộc tính thiếu/không cho phép:** dùng entry không có `appScore` hoặc tài khoản thiếu quyền để quan sát hành vi server.
6. **Không hỗ trợ ordering:** kiểm thử có kiểm soát với một attribute chỉ hỗ trợ equality để nhận diện hành vi của LDAP server đang sử dụng.
7. **Đa trị:** nếu schema cho phép nhiều giá trị, kiểm tra riêng tình huống có các giá trị ở hai phía khoảng nhưng không giá trị nào nằm trong khoảng.
8. **Escaping:** thử giá trị có `*`, `(`, `)`, `\` trên một thuộc tính thử nghiệm tương ứng để chắc chắn builder không làm hỏng filter.
9. **Thời gian:** so sánh tại đúng mốc, trước/sau mốc một giây và các mốc có phần giây nếu server hỗ trợ; xác nhận đầu vào UTC.
10. **Đường truyền:** chạy qua LDAPS với truststore đúng và tài khoản chỉ có quyền đọc trong nhánh thử nghiệm.

Để test có thể chạy lặp lại, hãy dùng directory dành riêng cho phát triển, dữ liệu giả, schema đã xác nhận và thao tác dọn dẹp an toàn. Một bộ test chỉ kiểm tra `filter.encode()` chưa đủ chứng minh máy chủ thực sự có ordering matching rule phù hợp; cần ít nhất một bài kiểm thử tích hợp trên LDAP server mục tiêu hoặc môi trường tương đương.

## 10. Bài thực hành có hướng dẫn

Giả sử có một thư mục LDAP thử nghiệm chứa người dùng trong `ou=people,dc=example,dc=org` và máy chủ hỗ trợ lọc theo `createTimestamp`:

1. Đọc một số entry và trường `createTimestamp` bằng `ldapsearch` trên kết nối LDAPS; ghi nhận định dạng thời gian, múi giờ và độ chính xác.
2. Chọn mốc UTC `20260101000000Z`. Chạy filter `(createTimestamp>=20260101000000Z)` và đối chiếu kết quả với thời gian của từng entry.
3. Thêm ngưỡng trên `(createTimestamp<=20260131235959Z)` bằng AND; xác định chính xác ý nghĩa hai biên.
4. Tạo bộ lọc tương đương bằng `AndFilter`, `GreaterThanOrEqualsFilter` và `LessThanOrEqualsFilter` trong Spring LDAP. In chuỗi `encode()` của filter **không chứa dữ liệu nhạy cảm** để đối chiếu cú pháp, rồi chạy `LdapTemplate.search(...)`.
5. Giảm phạm vi base từ `dc=example,dc=org` xuống `ou=people,dc=example,dc=org`, so sánh sự khác nhau về tập entry được xét.
6. Thử một mốc ngoài dữ liệu, một khoảng có hai biên bằng nhau và một khoảng đảo ngược. Ghi nhận khi nào trả danh sách rỗng, khi nào validation từ chối đầu vào.
7. Kiểm tra schema của một thuộc tính dùng equality nhưng chưa chắc có ordering; giải thích vì sao cú pháp `(attr>=value)` hợp lệ chưa đảm bảo phép so sánh có ý nghĩa.

**Câu hỏi tự kiểm tra:**

- `(modifyTimestamp>=20260101000000Z)` có bao gồm entry được sửa đúng 00:00 UTC ngày 1/1/2026 không?
- Vì sao `(&(appScore>=50)(appScore<=70))` có thể gây bất ngờ với thuộc tính đa trị?
- Điều gì xảy ra nếu `appScore` được định nghĩa như một chuỗi không có ordering matching rule?
- Tại sao nên dùng các đối tượng `Filter` của Spring LDAP thay cho nối chuỗi từ đầu vào người dùng?
- Khi một truy vấn khoảng trả rỗng, làm thế nào phân biệt không có dữ liệu với sai base DN hoặc thiếu quyền đọc?

## 11. Ghi nhớ

LDAP có hai phép so sánh thứ tự cơ bản trong search filter: **`>=`** và **`<=`**, đều bao gồm giá trị bằng ngưỡng. Kết hợp chúng bằng AND để tạo khoảng, nhưng cần kiểm tra ngữ nghĩa **thuộc tính đa trị** và cách biểu diễn các mốc thời gian. Giá trị có được so sánh đúng hay không phụ thuộc vào **schema và ordering matching rule** của máy chủ, không phụ thuộc kiểu dữ liệu Java. Trong Spring LDAP, các lớp `GreaterThanOrEqualsFilter`, `LessThanOrEqualsFilter` và `AndFilter` giúp xây filter dễ đọc và xử lý escaping cho giá trị, còn `LdapTemplate` thực thi truy vấn trong phạm vi base DN và scope đã chọn. Hãy kết hợp kiểm soát đầu vào, TLS, quyền tối thiểu, giới hạn truy vấn và kiểm thử trên LDAP directory thực tế để lọc dữ liệu an toàn và chính xác.
