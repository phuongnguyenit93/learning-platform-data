# Ngăn LDAP injection khi xây dựng bộ lọc từ dữ liệu đầu vào

## 1. Vấn đề: một ô nhập liệu có thể thay đổi cấu trúc LDAP filter

Trong hệ thống **Spring Boot Integration**, ứng dụng có thể truy vấn LDAP/Active Directory để tìm tài khoản, nhóm, phòng ban hoặc đối chiếu thông tin người dùng trước khi gọi HTTP client, ghi cơ sở dữ liệu, cập nhật cache hay phát sự kiện qua Kafka/RabbitMQ. LDAP thường được xem là một dịch vụ dữ liệu nền, nhưng **filter tìm kiếm** cũng là một ngôn ngữ truy vấn có cú pháp và toán tử. Nếu ghép dữ liệu đầu vào trực tiếp vào chuỗi filter, người dùng có thể làm thay đổi ý nghĩa truy vấn.

Ví dụ ứng dụng hỗ trợ tìm người dùng bằng `uid`:

```java
// KHÔNG AN TOÀN: input đi thẳng vào cú pháp LDAP filter
String filter = "(&(objectClass=inetOrgPerson)(uid="
        + username + "))";
```

Khi `username = "alice"`, filter trở thành:

```text
(&(objectClass=inetOrgPerson)(uid=alice))
```

Nhưng khi người gửi nhập `username = "*"`, kết quả là:

```text
(&(objectClass=inetOrgPerson)(uid=*))
```

Trong LDAP search filter, `(uid=*)` là **presence filter** (chỉ cần attribute `uid` tồn tại), không còn là điều kiện khớp chính xác một tài khoản. Truy vấn có thể trả về nhiều người hơn dự định. Nếu ứng dụng chọn kết quả đầu tiên rồi dùng nó để quyết định quyền, hoặc trả toàn bộ kết quả chưa kiểm tra, rủi ro trở thành **mở rộng phạm vi truy cập, lộ danh bạ hoặc sai logic xác thực**.

Input tinh vi hơn có thể chứa dấu ngoặc, toán tử `&`, `|`, `!` và các biểu thức khác để cố gắng thay đổi cấu trúc filter. Không phải payload nào cũng tạo ra filter hợp lệ, và mức độ khai thác phụ thuộc cách ứng dụng xử lý kết quả cùng ACL của LDAP server; tuy nhiên **điểm yếu nằm ở việc dữ liệu được phép điều khiển cú pháp truy vấn**.

**Mục tiêu học tập:**

- Phân biệt LDAP search filter với Distinguished Name (DN) và LDAP URL.
- Hiểu cú pháp filter, ký tự đặc biệt và quy tắc escaping theo RFC 4515.
- Xây filter an toàn bằng API của Spring LDAP thay vì nối chuỗi.
- Giới hạn attribute, toán tử, base DN, search scope và khối lượng kết quả.
- Kiểm thử injection với dữ liệu độc hại, Unicode, tài khoản trùng và lỗi LDAP.
- Bảo vệ quyền truy cập và observability khi tích hợp LDAP vào Spring Boot.

## 2. LDAP search filter là một ngôn ngữ có cấu trúc

Các search filter phổ biến:

| Dạng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Equality | Attribute có giá trị khớp | `(uid=alice)` |
| Presence | Attribute tồn tại | `(mail=*)` |
| Substring | Giá trị khớp mẫu có wildcard | `(cn=Anh*)` |
| AND | Tất cả điều kiện con đúng | `(&(objectClass=person)(uid=alice))` |
| OR | Ít nhất một điều kiện con đúng | `(|(uid=alice)(mail=alice@example.org))` |
| NOT | Phủ định một điều kiện | `(!(accountStatus=disabled))` |
| Comparison | Lớn hơn/bé hơn theo matching rule | `(employeeNumber>=1000)` |
| Extensible match | Matching rule hoặc ngữ nghĩa khớp đặc biệt | Phụ thuộc directory và schema |

Filter LDAP thường được viết theo cú pháp **prefix**: operator đứng trước các biểu thức con, chẳng hạn `(&(a=x)(b=y))`. Dữ liệu dùng trong một giá trị tìm kiếm không được phép tự tạo thêm dấu ngoặc, wildcard hoặc nhánh OR/NOT.

### 2.1. Hai lớp khác nhau: cú pháp và giá trị

Ứng dụng sở hữu cấu trúc filter:

```text
(&(objectClass=inetOrgPerson)(uid=<GIÁ_TRỊ>))
```

Đầu vào chỉ được đóng vai trò **giá trị của một phép so khớp**, không được thay đổi operator, tên attribute hoặc cách nhóm điều kiện. Đây tương tự nguyên tắc parameterized query trong SQL, nhưng **API và quy tắc escape dành cho LDAP khác SQL**. Đừng dùng SQL escaping, HTML encoding hoặc JSON escaping để sửa LDAP injection.

### 2.2. Tại sao validate input vẫn chưa đủ?

Giới hạn độ dài, kiểm tra kiểu và cho phép một tập ký tự hữu hạn là lớp bảo vệ tốt, nhưng validation không thay thế việc tạo filter đúng cách. Username/email hợp lệ trong hệ thống thực tế có thể chứa nhiều ký tự hơn một regex đơn giản; các chính sách thay đổi theo nguồn danh tính.

Nên áp dụng đồng thời:

1. **Input validation** theo hợp đồng nghiệp vụ (độ dài, bắt buộc, định dạng, canonicalization).
2. **Safe filter construction** bằng builder/filter object của thư viện để escape giá trị.
3. **Allowlist** cho những phần không thể parameterize như attribute hoặc kiểu tìm kiếm.
4. **LDAP ACL và search limits** để giảm thiệt hại khi truy vấn bị lạm dụng.
5. **Authorization ở ứng dụng** đối với tài khoản/nhóm và dữ liệu được phép hiển thị.

## 3. RFC 4515: escape giá trị của LDAP search filter

RFC 4515 định nghĩa dạng chuỗi của LDAP search filter. Khi giá trị được đặt trong **assertion value** của filter, một số byte đặc biệt phải được thể hiện bằng chuỗi escape dạng dấu gạch chéo ngược và hai chữ số hex.

| Ký tự trong đầu vào | Byte / ý nghĩa cú pháp | Cách escape trong filter |
| --- | --- | --- |
| `*` | Wildcard / presence / substring | `\2a` |
| `(` | Mở biểu thức | `\28` |
| `)` | Đóng biểu thức | `\29` |
| `\` | Ký tự escape | `\5c` |
| NUL | Byte 0x00 | `\00` |

Ví dụ **giá trị cần tìm đúng là dấu sao**:

```text
Input literal:       *
Sai (presence):      (uid=*)
Đúng (literal '*'):  (uid=\2a)
```

Với tên người dùng `a(b)c*`:

```text
Input literal:      a(b)c*
Escaped value:      a\28b\29c\2a
Search filter:      (uid=a\28b\29c\2a)
```

Ở đây `\28` và `\29` **không còn là dấu ngoặc cấu trúc**, còn `\2a` **không phải wildcard**. Directory sẽ so sánh với giá trị chứa các ký tự literal tương ứng, theo matching rule của attribute.

Không nên tự viết hàm escape bằng vài lần `replace()` trong code nghiệp vụ: dễ sai thứ tự escape, bỏ sót NUL, xử lý Unicode/byte không đúng hoặc vô tình escape hai lần. Dùng thành phần đã được framework triển khai và kiểm thử. Với chuỗi UTF-8, RFC 4515 còn có quy tắc cho octet và chuỗi UTF-8 không hợp lệ; hệ thống nên dùng decoder/encoding hợp lệ ở ranh giới nhận dữ liệu.

**Lưu ý:** dấu `&`, `|` và `!` mang ý nghĩa operator ở những vị trí cú pháp nhất định. Không có nghĩa cứ xuất hiện ký tự đó trong một giá trị là phải áp dụng bộ "escape giống SQL". Để thư viện tạo **toàn bộ filter** và escape assertion value theo quy tắc LDAP.

## 4. Cách an toàn nhất: Spring LDAP LdapQueryBuilder

Đối với ứng dụng Spring Boot 3.x sử dụng Spring LDAP 3.x tương thích, Spring LDAP có DSL `LdapQueryBuilder` để khai báo filter theo cấu trúc và đưa input vào **giá trị**.

### 4.1. Dependency và cấu hình kết nối

```kotlin
// build.gradle.kts — Spring Boot quản lý version tương thích
implementation("org.springframework.boot:spring-boot-starter-data-ldap")
```

```yaml
# application.yml — minh họa; secret cấp bởi runtime/secret manager
spring:
  ldap:
    urls: "${LDAP_URLS:ldaps://ldap.example.org:636}"
    base: "dc=example,dc=org"
    username: "${LDAP_BIND_DN}"
    password: "${LDAP_BIND_PASSWORD}"
```

`spring.ldap.base` là base DN cho ngữ cảnh LDAP được cấu hình; search base bên dưới thường là DN **tương đối** với base này. Đừng đưa username, OU hoặc DN do người dùng tự nhập thẳng vào cấu hình. Production cần TLS phù hợp (LDAPS hoặc StartTLS theo khả năng directory), kiểm tra chứng chỉ và hostname, secret manager, phân quyền tài khoản bind tối thiểu và timeout/connection pool có giới hạn.

### 4.2. Dùng giá trị người dùng trong equality filter

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import javax.naming.directory.Attribute;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.stereotype.Repository;

record DirectoryPerson(String uid, String commonName, String mail) {}

@Repository
public class DirectoryPersonRepository {
    private final LdapTemplate ldap;

    public DirectoryPersonRepository(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public List<DirectoryPerson> findByUsername(String username) {
        if (username == null || username.isBlank()
                || username.length() > 64) {
            throw new IllegalArgumentException("Invalid username length");
        }

        LdapQuery safeQuery = query()
                .base("ou=people")
                .countLimit(2)
                .timeLimit(1500)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(username);

        return ldap.search(safeQuery,
                (AttributesMapper<DirectoryPerson>) attrs -> {
                    String uid = (String) attrs.get("uid").get();
                    String name = (String) attrs.get("cn").get();
                    Attribute mail = attrs.get("mail");
                    String email = mail == null
                            ? null : (String) mail.get();
                    return new DirectoryPerson(uid, name, email);
                });
    }
}
```

Điểm bảo vệ là `.and("uid").is(username)`: framework tạo equality filter và **escape giá trị username** thay vì ghép username vào cú pháp. Phần `objectClass=inetOrgPerson` và attribute `uid` là hằng do ứng dụng kiểm soát.

`countLimit(2)` giúp phát hiện trường hợp kết quả không duy nhất mà không trả cả directory; `timeLimit(1500)` là giới hạn tìm kiếm phía client/query theo API Spring LDAP, nhưng giới hạn hiệu quả thực tế còn phụ thuộc server, timeout kết nối, network và cấu hình LDAP. Chúng **không thay thế** cấu hình search size/time limit, rate limit ở server và timeout tổng thể ở phía ứng dụng.

Ví dụ mapper giả định entry có `uid` và `cn`. Với schema khác (như Active Directory dùng `sAMAccountName`, `userPrincipalName`), phải định nghĩa schema mapping riêng và kiểm tra attribute null/multi-value. Không đẩy dữ liệu directory vào response cho người dùng khi chưa phân quyền và lọc các trường được phép lộ.

### 4.3. Kiểm tra tính duy nhất, không chọn kết quả đầu tiên

```java
List<DirectoryPerson> found = directoryPersonRepository
        .findByUsername(username);

if (found.isEmpty()) {
    // Không tìm thấy tài khoản theo điều kiện tra cứu.
    throw new UserNotFoundException();
}
if (found.size() != 1) {
    // Lỗi dữ liệu/hợp đồng: uid không duy nhất trong search scope.
    throw new AmbiguousDirectoryIdentityException();
}
DirectoryPerson person = found.get(0);
```

`UserNotFoundException` và `AmbiguousDirectoryIdentityException` là các exception **minh họa do ứng dụng tự định nghĩa**. Trong luồng xác thực, đừng dùng cách "lấy người dùng đầu tiên" rồi xem kết quả tìm kiếm là chứng cứ đã xác thực. Việc tìm ra một directory entry chỉ xác định **đối tượng phù hợp với truy vấn**, chưa chứng minh người gọi biết mật khẩu, có phiên đăng nhập hợp lệ hay được cấp quyền truy cập.

## 5. Xây filter bằng Filter objects, tránh string concatenation

Spring LDAP còn có các lớp `EqualsFilter`, `AndFilter`, `OrFilter` trong package `org.springframework.ldap.filter`. Khi cần một filter động có nhiều nhánh do **ứng dụng** quyết định, hãy tạo cây filter từ các object.

```java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

String encodeSafeUserFilter(String username, String departmentCode) {
    AndFilter filter = new AndFilter();
    filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
    filter.and(new EqualsFilter("uid", username));
    filter.and(new EqualsFilter("departmentNumber", departmentCode));
    return filter.encode();
}
```

Ở đây tên attribute và toán tử do ứng dụng chọn; `username` và `departmentCode` là **assertion values** được filter object escape. Không sử dụng:

```java
// KHÔNG AN TOÀN: hai giá trị từ request được nối thẳng vào filter
String unsafeFilter = "(&(uid=" + username
        + ")(departmentNumber=" + departmentCode + "))";
```

**Không đưa chuỗi filter nguyên vẹn từ HTTP request vào API** như `query().filter(rawUserFilter)`, ngay cả khi có ý định "hỗ trợ tìm kiếm nâng cao". Một phương thức nhận raw filter được thiết kế cho trường hợp nguồn filter **đã đáng tin**; nó không tự hiểu đâu là cú pháp và đâu là input cần escape.

Nếu ứng dụng cần hỗ trợ AND/OR tùy chọn, cho client lựa chọn từ một tập operation đã được định nghĩa (ví dụ "tra cứu theo uid", "theo email", "theo nhóm") rồi backend tự tạo các nhánh filter. Không cấp quyền cho client gửi dấu ngoặc, raw filter fragment, matching rule identifier hoặc schema attribute tùy ý.

## 6. Attribute name, toán tử và base DN cũng là bề mặt tấn công

Escape **giá trị** không đủ nếu ứng dụng vẫn để người dùng kiểm soát cấu trúc khác của truy vấn. Ví dụ:

```java
// SAI: attributeName tới từ query parameter chưa được kiểm soát
String filter = "(" + attributeName + "="
        + userValue + ")";
```

Ngay cả khi `userValue` đã được escape, một attribute hoặc operator không hợp lệ có thể khiến truy vấn sai, mở rộng việc tìm kiếm hoặc sử dụng thuộc tính mà service account có quyền đọc nhưng API không được phép công bố.

### 6.1. Whitelist trường tìm kiếm

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import org.springframework.ldap.query.LdapQuery;

enum AccountSearchField {
    USERNAME, EMAIL
}

LdapQuery safeSearch(AccountSearchField field, String value) {
    String ldapAttribute = switch (field) {
        case USERNAME -> "uid";
        case EMAIL -> "mail";
    };

    return query()
            .base("ou=people")
            .countLimit(20)
            .timeLimit(1500)
            .where("objectClass").is("inetOrgPerson")
            .and(ldapAttribute).is(value);
}
```

API HTTP chỉ nên chấp nhận giá trị enum hoặc tên được map vào enum với kiểm tra rõ ràng; giá trị không thuộc danh sách cho phép phải bị từ chối. `value` cũng cần giới hạn độ dài và hợp đồng dữ liệu. Không lấy toàn bộ LDAP schema làm danh sách tìm kiếm public.

### 6.2. Không để người gọi chọn arbitrary base DN hoặc search scope

Một API nhận `baseDn`, `searchScope` hoặc `filter` tùy ý có thể vô tình cung cấp giao diện truy vấn directory tổng quát. Người dùng có thể yêu cầu tìm dưới những OU không được phép, hoặc dùng `SUBTREE` tại root directory thay vì `ONELEVEL` tại `ou=people`.

Áp dụng chính sách:

- Mapping tenant/tổ chức vào OU từ **cấu hình backend đáng tin**; không lấy raw tenant header chưa xác thực làm DN.
- Base DN và search scope cố định theo endpoint hoặc nhóm endpoint được phép.
- Chỉ trả các attribute cần thiết; không mặc định trả cả entry.
- Đặt giới hạn số bản ghi, thời gian thực thi, pagination và rate limit.
- Nếu cần phân quyền theo tổ chức/tenant, kiểm tra điều kiện server-side, không chỉ ẩn kết quả ở giao diện.
- Tránh cho client chỉ định attribute nhạy cảm như password hash, token hoặc thông tin quản trị.

Một service account có quyền đọc toàn directory làm tăng phạm vi ảnh hưởng của lỗ hổng. Ưu tiên bind account chỉ có quyền đọc OU/attribute thực sự cần và cơ chế authorization bổ sung ở ứng dụng.

## 7. Phân biệt LDAP filter escaping và DN escaping

LDAP có ít nhất **hai ngữ cảnh dễ bị nhầm**:

1. **Search filter** theo RFC 4515, ví dụ `(uid=alice)`.
2. **Distinguished Name** theo RFC 4514, ví dụ `uid=alice,ou=people,dc=example,dc=org`.

Những ký tự cần escape và cách escape của hai ngữ cảnh **khác nhau**. Chẳng hạn dấu phẩy `,` và dấu cộng `+` có vai trò trong DN, nhưng không phải đều là special character của assertion value trong LDAP filter. Ngược lại `*` có nghĩa wildcard trong filter, không phải bộ toán tử của DN.

Không áp dụng cách escape của filter để xây DN, và không lấy một DN đã được escape rồi tự nhét vào filter mà không thực hiện escaping theo filter. Dùng API có cấu trúc cho đúng từng ngữ cảnh.

### 7.1. Xây DN bằng LdapNameBuilder

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDnForUser(String userId) {
    // Giá trị RDN được mã hóa theo quy tắc DN, không phải filter.
    return LdapNameBuilder.newInstance("ou=people")
            .add("uid", userId)
            .build();
}
```

Nếu `userId` chứa dấu phẩy, dấu cộng hoặc ký tự đặc biệt của DN, builder sẽ xử lý giá trị RDN theo ngữ cảnh DN. Phần base DN trong ví dụ là hằng đã tin cậy; không để đầu vào quyết định tổ chức, OU hoặc thư mục gốc.

Để minh họa với JNDI thuần, `javax.naming.ldap.Rdn` và `LdapName` cũng hỗ trợ cấu trúc DN. Không ghép:

```java
// KHÔNG AN TOÀN: userId có thể phá vỡ cấu trúc DN.
String unsafeDn = "uid=" + userId + ",ou=people,dc=example,dc=org";
```

**Lưu ý về authentication:** Spring Security LDAP có cơ chế xác thực dựa trên bind hoặc password comparison theo cấu hình. Nếu thực hiện LDAP login, hãy dùng thành phần xác thực phù hợp và chính sách chống brute-force, không tự ghép DN/filter rồi chỉ kiểm tra "search trả về tài khoản". Query an toàn chỉ là một phần của toàn bộ hệ thống xác thực.

## 8. Tìm kiếm gần đúng và wildcard: đưa quyền quyết định cho backend

Trong chức năng autocomplete hoặc tìm tên người dùng theo tiền tố, wildcard có thể là **yêu cầu sản phẩm hợp lệ**. Nhưng khác biệt rất lớn giữa:

- Client yêu cầu `prefix = "an"`, backend có tính năng "starts with" với wildcard do backend điều khiển.
- Client gửi thẳng một chuỗi filter `(cn=an*)` hoặc tự đặt wildcard `*`, dấu ngoặc và OR.

Với tìm kiếm gần đúng, thiết kế:

1. Input của người dùng vẫn chỉ là **literal search term**, không phải filter fragment.
2. Backend chọn operator cố định (`starts_with`, `contains` hoặc `exact`) từ enum đã cho phép.
3. Dùng API/filter builder dành riêng cho **substring matching** để escape phần literal và chỉ thêm wildcard do backend quyết định. Không ghép raw input vào chuỗi `(cn=...*)`.
4. Bắt buộc độ dài tiền tố tối thiểu, giới hạn số kết quả, timeout và rate limit để chống enumerate toàn danh bạ.
5. Không dùng substring/contains search cho xác thực hoặc phân quyền tài khoản cần khớp duy nhất.

Một số API DSL của Spring LDAP có phương thức hỗ trợ tìm gần đúng/substring theo phiên bản cụ thể. Hãy kiểm tra cách phương thức đó xử lý wildcard và escaping **bằng test**; không suy rằng tất cả phương thức có tên `like` sẽ tự áp cùng chính sách với equality `is()`. Nếu phải xây filter nâng cao, chỉ tổ hợp từ các primitive đáng tin và giá trị đã được encode đúng ngữ cảnh.

## 9. Kết hợp với HTTP API: chống dữ liệu đầu vào điều khiển LDAP

Trong REST API, một endpoint tìm tài khoản có thể nhận:

```http
GET /api/directory/users?username=alice HTTP/1.1
Accept: application/json
```

Đừng cho frontend gửi `ldapFilter`, `baseDn` hoặc `attribute` tự do rồi chuyển tiếp trực tiếp. Phần HTTP chỉ cung cấp **tham số nghiệp vụ** như `username`, `email` hoặc `departmentCode`.

### 9.1. Controller mẫu tách input và filter

```java
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/directory/users")
class DirectoryController {
    private final DirectoryPersonRepository directory;

    DirectoryController(DirectoryPersonRepository directory) {
        this.directory = directory;
    }

    @GetMapping
    ResponseEntity<List<DirectoryPerson>> searchByUsername(
            @RequestParam String username) {
        // Demo: trong production phải kiểm tra quyền caller,
        // hạn chế trường trả về và rate limit phù hợp.
        List<DirectoryPerson> users = directory.findByUsername(username);
        return ResponseEntity.ok(users);
    }
}
```

Ví dụ tập trung vào dữ liệu đi qua boundary HTTP → LDAP. **Không xem đây là API public an toàn đầy đủ**: cần authentication, authorization, danh sách field response được phép, hạn chế enumerate người dùng và chống lộ thông tin cá nhân. Việc dùng filter builder không thay thế kiểm soát quyền truy cập.

Để giảm rò rỉ thông tin trong luồng đăng nhập, không trả khác biệt chi tiết "username không tồn tại" và "mật khẩu sai" nếu chính sách bảo mật yêu cầu tránh account enumeration. Thông báo cho người dùng nên được chuẩn hóa, còn log nội bộ chỉ giữ thông tin cần thiết có phân quyền.

### 9.2. Xử lý sự cố LDAP và fallback

LDAP là dependency mạng nên có thể gặp connection timeout, referral, busy server, size/time limit exceeded hoặc lỗi TLS. Một ứng dụng có thể retry có giới hạn với backoff cho lỗi tạm thời, nhưng không nên retry không giới hạn hoặc đổi sang search scope rộng hơn khi gặp lỗi.

Với bài toán **authorization**, không được tự động cho qua nếu LDAP không truy cập được, trừ khi chính sách đã định nghĩa cơ chế xác thực/phân quyền dự phòng có bảo đảm. Cache kết quả directory cần TTL, invalidation và đánh giá nguy cơ dữ liệu quyền đã lỗi thời. Nếu ứng dụng dùng Redis cache hoặc Kafka event để truyền trạng thái nhóm, cần xác định đâu là nguồn sự thật và độ trễ đồng bộ được chấp nhận.

## 10. Kiểm thử phòng LDAP injection

### 10.1. Unit test đối với filter object

Đơn vị nhỏ nhất cần chứng minh là **input trở thành literal**, không thay đổi cấu trúc filter. Ví dụ JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class LdapFilterEscapingTest {

    @Test
    void starMustBeLiteralInsteadOfPresenceFilter() {
        String encoded = new EqualsFilter("uid", "*").encode();
        assertEquals("(uid=\\2a)", encoded);
    }

    @Test
    void parenthesesMustNotChangeFilterStructure() {
        String encoded = new EqualsFilter("uid", "a(b)c").encode();
        assertEquals("(uid=a\\28b\\29c)", encoded);
    }

    @Test
    void backslashMustBeEscaped() {
        String encoded = new EqualsFilter("uid", "a\\b").encode();
        assertEquals("(uid=a\\5cb)", encoded);
    }

    @Test
    void nulMustBeEscaped() {
        String encoded = new EqualsFilter(
                "uid", "a" + String.valueOf((char) 0) + "b").encode();
        assertEquals("(uid=a\\00b)", encoded);
    }
}
```

Những test trên minh họa đúng ngữ nghĩa RFC 4515; khi chạy cần xác nhận output của phiên bản Spring LDAP đang sử dụng. Không tự viết một encoder chỉ để test encoder đó; hãy test API của thư viện và **đường truy vấn thực tế**. Một helper unit test pass không bảo đảm toàn ứng dụng không còn vị trí khác dùng string concatenation.

### 10.2. Integration test với directory thật

Dùng embedded LDAP server/test container hoặc directory test được phép truy cập, tạo dữ liệu cố định như:

```text
ou=people,dc=example,dc=org
  uid=alice  -> inetOrgPerson
  uid=bob    -> inetOrgPerson
  uid=admin  -> inetOrgPerson
```

| Dữ liệu đầu vào | Kỳ vọng |
| --- | --- |
| `alice` | Trả đúng entry alice khi caller có quyền |
| `*` | Không biến thành presence filter, không trả tất cả user |
| `a(b)c` | Được so khớp như giá trị literal nếu hợp lệ theo policy |
| `\` hoặc `a\b` | Không làm vỡ filter parser hoặc thay cấu trúc tìm kiếm |
| NUL, chuỗi quá dài, bỏ trống | Bị validate/từ chối hoặc encode an toàn theo hợp đồng |
| Chuỗi chứa nhiều dấu ngoặc và `|`/`&` | Không làm biến đổi bộ điều kiện cố định của backend |
| Unicode hợp lệ | Không bị lỗi encode/sửa ngữ nghĩa nếu schema cho phép |
| Hai entry cùng username trong phạm vi tìm | Trả lỗi ambiguous, không chọn entry đầu tiên |
| Tên attribute ngoài allowlist | Bị từ chối, không trở thành raw LDAP attribute |
| Search scope/base ngoài vùng được phép | Không được thực thi từ input HTTP |
| LDAP timeout/referral/unavailable | Không fail-open quyền, có error/timeout có kiểm soát |
| Tài khoản bind chỉ có quyền hẹp | Không đọc entry/attribute nằm ngoài quyền đã cấp |

Test nên xác minh cả **thực thể nào được truy xuất** và **không có dữ liệu ngoài phạm vi bị lộ**, không chỉ so sánh một chuỗi filter. Với active directory, kiểm tra schema thực tế (case folding, multi-valued attributes, nested groups, referrals) vì behavior có thể khác directory test đơn giản.

### 10.3. Test authorization không được thay bằng test escaping

Ngay cả filter được escape đúng, API vẫn có thể trả danh sách người dùng mà caller không được phép xem nếu thiếu authentication/authorization. Do đó cần kiểm tra phân quyền tài khoản, OU, tenant, nhóm và các field nhạy cảm; kiểm tra không có cách dùng ID/DN của người khác để lấy thông tin trái quyền. Kiểm thử bảo mật phải bao gồm cả **authorization boundary** chứ không chỉ cú pháp filter.

## 11. Logging, tracing và metrics khi gặp lỗi LDAP

Thường cần biết truy vấn mất bao lâu, bị timeout, không tìm thấy hay gặp lỗi schema. Không cần ghi nguyên filter chứa giá trị của người dùng vào log.

**Metric nhãn hữu hạn** có thể gồm:

```text
ldap_lookup_duration_seconds{
    operation="find_by_username",
    directory="corporate",
    outcome="success"
}

ldap_lookup_total{
    operation="find_by_username",
    outcome="timeout"
}
```

Tránh nhãn `username`, `email`, `uid`, `dn`, `raw_filter` hoặc `correlationId` vì vừa có cardinality cao vừa có thể chứa định danh cá nhân. Dùng structured logs/traces có phân quyền để điều tra riêng lẻ khi thật sự cần, với retention, masking và hạn chế truy cập. Nếu đầu vào có ký tự xuống dòng/điều khiển, log phải xử lý an toàn để không bị log injection.

Với tracing, có thể truyền correlation ID xuyên HTTP → LDAP operation → DB/cache/broker theo cơ chế observability được thiết kế, nhưng **không** biến raw LDAP filter thành attribute mặc định trên mọi span. Khi ghi exception, tránh lưu cùng lúc cả username, bind credentials, full DN và toàn bộ server error nếu điều đó làm lộ thông tin.

Các cảnh báo hữu ích:

- Tỷ lệ query fail/timeout/busy server tăng bất thường.
- Search time p95/p99, số query và số result vượt ngưỡng cho operation.
- Số request bị validation từ chối (không dùng raw input làm label).
- Tài khoản bind bị lock, lỗi TLS/certificate và referral loop.
- Tăng đột ngột số truy vấn wildcard/search rộng, biểu hiện enumeration hoặc cấu hình client sai.

## 12. Những kiểu "sửa" injection sai hướng

| Cách làm sai | Vì sao sai | Thay bằng |
| --- | --- | --- |
| `filter = "(uid=" + input + ")"` | Input điều khiển cú pháp | `where("uid").is(input)` hoặc `EqualsFilter` |
| Chỉ xóa dấu `*` | Vẫn còn `(`, `)`, `\`, NUL; biến đổi dữ liệu hợp lệ | RFC 4515 escaping qua thư viện |
| Dùng HTML/URL/SQL escaping | Không cùng cú pháp LDAP filter | Filter builder dành cho LDAP |
| Escaping filter rồi dùng làm DN | RFC 4515 khác RFC 4514 | `LdapNameBuilder`/`Rdn` cho DN |
| Cho client gửi raw LDAP filter để "linh hoạt" | Cấp quyền kiểm soát operator/attribute/scope | API có enum/field allowlist |
| Cho username/password đúng thì query tùy ý | Authentication không đồng nghĩa authorization | ACL hẹp, phân quyền theo endpoint |
| Bắt exception rồi tìm rộng hơn | Có thể lộ directory sau query lỗi | Fail có kiểm soát và điều tra lỗi |
| Lấy kết quả LDAP đầu tiên làm danh tính | Filter rộng/trùng entry tạo identity confusion | Bắt buộc duy nhất và xác thực thật |
| Log toàn bộ filter để debug | Lộ tên người dùng, DN, PII; tăng bề mặt log injection | Log operation, outcome, latency đã chuẩn hóa |
| Chỉ giới hạn length của input | Input ngắn như `*` vẫn có cú pháp đặc biệt | Escaping + schema/policy validation |
| Dùng service account toàn quyền cho mọi API | Một lỗi mở rộng phạm vi tra cứu | Least-privilege bind và search scope |
| Trust cache user/group vô thời hạn | Không phản ánh thu hồi quyền và thay đổi directory | TTL/invalidation, consistency policy |

## 13. Checklist triển khai trong Spring Boot Integration

- [ ] Tất cả LDAP search filters nhận input từ HTTP, file, Kafka/RabbitMQ, Redis hoặc đối tác đều dùng builder/filter object; không nối input vào raw filter.
- [ ] Phân biệt rõ **filter assertion value** (RFC 4515) và **DN/RDN value** (RFC 4514); sử dụng API escape đúng ngữ cảnh.
- [ ] Tên attribute, toán tử, base DN, search scope và matching rules được chọn từ allowlist/backend configuration.
- [ ] Input có validation theo nghiệp vụ, nhưng escaping vẫn thực hiện kể cả input được coi là hợp lệ.
- [ ] Search dùng base/scope hẹp, size/time limit, pagination/rate limit và chỉ lấy attributes cần thiết.
- [ ] Mọi thao tác tìm danh tính kiểm tra tính duy nhất; không dùng "kết quả đầu tiên" làm chứng cứ xác thực.
- [ ] LDAP bind account có quyền tối thiểu, kết nối dùng TLS với certificate validation, credentials không xuất hiện trong source/log.
- [ ] API xác thực/phân quyền bằng cơ chế phù hợp; lookup directory không thay password/token verification.
- [ ] Lỗi timeout, referral và server unavailable không tự động làm fail-open authorization.
- [ ] Đã test `*`, dấu ngoặc, backslash, NUL, Unicode, query quá rộng, attribute ngoài allowlist và lỗi schema.
- [ ] Integration test dùng LDAP server thật hoặc phù hợp, xác nhận kết quả không bị broaden khi input độc hại.
- [ ] Logs/traces và metrics không lộ raw filter, bind credentials, username/email/DN hoặc ID cá nhân ở metric labels.
- [ ] Nếu kết quả LDAP được đưa sang DB/cache/broker, vẫn áp schema, retention, quyền truy cập, idempotency và hợp đồng dữ liệu của hệ thống đích.

**Kết quả mong muốn:** Khi một ứng dụng Spring Boot truy vấn LDAP, dữ liệu bên ngoài chỉ có thể ảnh hưởng tới **giá trị cần so khớp**, không thể biến thành toán tử, attribute tùy ý hoặc thay đổi phạm vi tìm kiếm. Việc dùng Spring LDAP query/filter builders, DN builders đúng ngữ cảnh, giới hạn quyền và kiểm thử tích hợp giúp ngăn LDAP injection mà vẫn giữ được khả năng tìm kiếm, xác thực và quan sát hệ thống.
