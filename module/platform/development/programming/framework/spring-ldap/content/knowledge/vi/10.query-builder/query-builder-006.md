# Filter tùy biến bằng hardcoded filter

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **hardcoded filter** là gì và khi nào cần dùng thay cho các điều kiện `where(...).is(...)` của `LdapQueryBuilder`.
- Phân biệt chính xác ba overload: `filter(String hardcodedFilter)`, `filter(String filterFormat, Object... params)` và `filter(Filter filter)`.
- Viết LDAP filter phức hợp bằng `&`, `|`, `!`, equality, presence và substring theo RFC 4515.
- Nhận ra rằng **`filter(String)` không kiểm tra cú pháp, không escape input**, trong khi overload có tham số và các filter builder phù hợp sẽ xử lý dữ liệu đầu vào theo quy tắc filter.
- Không trộn `filter(...)` với `where(...)`, không cấu hình search base/scope sau khi đã xác định điều kiện lọc, và không nhầm escape DN với escape LDAP filter.
- Đánh giá tác động của hardcoded filter đến quyền truy cập, chỉ mục, chi phí truy vấn, TLS, logging và kiểm thử trong **Spring LDAP**.

Bài thuộc chương **Query builder** trong module **SPRING_LDAP**. Người học đã làm quen với DN, schema, LDAP filter và tìm kiếm; ở đây, bạn sẽ biết cách truyền **một filter được định nghĩa rõ ràng** cho `LdapTemplate` hoặc `LdapClient`, đồng thời giữ đúng ranh giới giữa cú pháp do lập trình viên kiểm soát và dữ liệu đến từ người dùng.

## 1. Vì sao cần hardcoded filter?

Giả sử ứng dụng có LDAP directory chứa nhân viên:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
sn: Nguyen
mail: lan@example.org
~~~

Một truy vấn đơn giản có thể được xây từ DSL:

~~~java
LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .where("uid").is("lan");
~~~

Truy vấn trên cần một equality assertion. Nhưng một số nghiệp vụ có điều kiện lọc đã được mô tả bằng filter RFC 4515 phức hợp, chẳng hạn:

~~~ldap
(&(objectClass=inetOrgPerson)(mail=*)(!(uid=svc*)))
~~~

Ý nghĩa:

1. Entry thuộc object class `inetOrgPerson`.
2. Entry **có** thuộc tính `mail`.
3. Entry có `uid` **không** bắt đầu bằng `svc` theo substring matching rule áp dụng.

Nếu filter cố định này là một quy tắc hệ thống đã được xem xét, có thể truyền nguyên chuỗi cho query builder. Cách làm đó được gọi là **hardcoded filter**: mã lập trình hoặc cấu hình tin cậy chứa **cú pháp LDAP filter hoàn chỉnh**, thay vì xây mọi điều kiện qua `where(...)`.

**Hardcoded không nhất thiết có nghĩa “được viết trực tiếp trong Java source”.** Filter có thể được đọc từ cấu hình được quản trị kiểm soát. Điều quan trọng là **nguồn và quyền sửa filter**: một chuỗi lấy nguyên từ HTTP request, form, query parameter hoặc hệ thống bên ngoài không trở thành an toàn chỉ vì được gán vào biến có tên `hardcodedFilter`.

## 2. Phân biệt ba cách truyền filter cho LdapQueryBuilder

Spring LDAP công bố ba overload quan trọng:

| API | Cách xử lý | Dùng khi nào? | Rủi ro cần nhớ |
| --- | --- | --- | --- |
| `filter(String hardcodedFilter)` | Dùng chuỗi **nguyên trạng**, không escape/validate | Filter hoàn chỉnh, cố định và được kiểm soát | Input không tin cậy có thể tạo LDAP filter injection |
| `filter(String filterFormat, Object... params)` | Dùng mẫu `MessageFormat` và **encode tham số** theo LDAP filter | Có cú pháp filter cố định nhưng giá trị được cung cấp động | Không cho người dùng kiểm soát mẫu hoặc tên attribute |
| `filter(Filter filter)` | Dùng đối tượng `Filter` đã tạo | Muốn ghép `AndFilter`, `OrFilter`, `EqualsFilter` và phần hardcoded | Chất lượng bảo vệ phụ thuộc từng thành phần; `HardcodedFilter` vẫn raw |

Ba phương án đều tạo một `LdapQuery` có thể truyền vào `LdapTemplate.search(query, mapper)`.

~~~mermaid
flowchart TD
    Need["Cần biểu diễn LDAP filter"]
    Dynamic{"Có dữ liệu động từ người dùng?"}
    Need --> Dynamic
    Dynamic -->|"Không: điều kiện cố định, đã duyệt"| Raw["filter(String hardcodedFilter)<br/>Chuỗi được giữ nguyên"]
    Dynamic -->|"Có"| Choice{"Dạng điều kiện"}
    Choice -->|"Equality/and/or đơn giản"| Where["where(...).is(...)<br/>hoặc EqualsFilter"]
    Choice -->|"Mẫu RFC 4515 cố định"| Params["filter(String format, Object... params)<br/>Escape từng tham số"]
    Choice -->|"Lắp từ nhiều Filter"| Typed["filter(Filter)<br/>AndFilter/EqualsFilter/..."]
    Raw --> Server["LdapQuery -> LDAP server"]
    Where --> Server
    Params --> Server
    Typed --> Server
~~~

**Không có cách nào trong bảng thay thế schema, matching rule, ACL hoặc TLS của LDAP server.** Query builder hỗ trợ biểu diễn và encode truy vấn, không tự cấp quyền đọc dữ liệu.

## 3. filter(String hardcodedFilter): giữ nguyên toàn bộ cú pháp

Ví dụ một filter **không có dữ liệu đầu vào**:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn", "mail")
    .countLimit(100)
    .timeLimit(2_000)
    .filter("(&(objectClass=inetOrgPerson)(mail=*)(!(uid=svc*)))");
~~~

Các phần của query có trách nhiệm khác nhau:

- `base("ou=people")`: chỉ định nhánh bắt đầu tìm kiếm, thường **tương đối** với `ContextSource.base`.
- `searchScope(SearchScope.SUBTREE)`: xét base và mọi hậu duệ của nó.
- `attributes(...)`: yêu cầu các thuộc tính cần map.
- `countLimit(100)` và `timeLimit(2_000)`: giới hạn kết quả/thời gian, **không** bảo đảm server chỉ kiểm tra 100 entry.
- `filter(String)`: đặt filter hoàn chỉnh ở cuối chuỗi builder.

Đặc biệt, `filter(String)` **không** tự kiểm tra dấu ngoặc, tên thuộc tính, matching rule hoặc escape ký tự. Nếu chuỗi bị sai, query builder không nhất thiết phát hiện trước khi gửi request; lỗi có thể chỉ xuất hiện khi LDAP server hoặc tầng provider phân tích filter.

### 3.1. Truyền filter vào LdapTemplate

~~~java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public List<String> listCommonNames(LdapTemplate ldapTemplate) {
    LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("cn")
        .countLimit(50)
        .filter("(&(objectClass=inetOrgPerson)(mail=*))");

    return ldapTemplate.search(
        query,
        (AttributesMapper<String>) attrs -> {
            Attribute cn = attrs.get("cn");
            return cn == null ? null : (String) cn.get();
        }
    );
}
~~~

Mapper trên minh họa cách lấy attribute từ entry. Ứng dụng thực cần quyết định hành vi nếu `cn` vắng mặt/đã bị ACL che, hoặc thuộc tính có nhiều giá trị. Ví dụ không khẳng định `mail` hay `cn` luôn hiện diện trên mọi LDAP server.

### 3.2. Hardcoded filter có thể ở file cấu hình

Một filter do đội vận hành quản lý có thể là:

~~~properties
directory.people.filter=(&(objectClass=inetOrgPerson)(mail=*)(!(uid=svc*)))
~~~

Ứng dụng đọc property này và truyền vào `filter(String)` như một filter **cấu hình tin cậy**. Điều cần kiểm soát:

- Ai có quyền thay đổi cấu hình?
- Có review/cấu hình kiểm thử trước triển khai không?
- Có cấm đưa dữ liệu request trực tiếp vào property/filter không?
- Có giới hạn base/scope và thuộc tính được trả về không?
- Nếu môi trường có nhiều tenant, filter có thể bỏ qua ranh giới tenant không?

**Không để người dùng cuối gửi một “filter hoàn chỉnh” như một chuỗi rồi gọi `filter(userInput)`.** Đó là một API cho phép điều khiển truy vấn LDAP, có thể phá vỡ ràng buộc nghiệp vụ hoặc tạo điều kiện đọc quá rộng tùy ACL.

## 4. Vì sao filter(String) không an toàn cho input động?

Xét cách viết sai:

~~~java
String filter = "(uid=" + usernameFromHttpRequest + ")";

LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .filter(filter); // NGUY HIỂM: filter(String) không escape!
~~~

Nếu `usernameFromHttpRequest` là `lan*`, biểu thức cuối cùng trở thành:

~~~ldap
(uid=lan*)
~~~

Cú pháp này không còn là equality tìm literal `lan*` nữa, mà là **prefix substring** tìm các giá trị bắt đầu bằng `lan`. Các ký tự đặc biệt khác như `(`, `)` và gạch chéo ngược có thể làm thay đổi cấu trúc hoặc khiến filter không hợp lệ.

Trường hợp nghiêm trọng hơn là LDAP filter injection: attacker cố chèn các toán tử vào một chuỗi filter do ứng dụng nối thủ công. Cùng một lỗ hổng có thể khiến ứng dụng trả nhiều entry ngoài dự định hoặc sử dụng logic truy vấn sai.

### 4.1. Các ký tự phải escape trong assertion value

RFC 4515 yêu cầu biểu diễn những ký tự sau theo cú pháp escape của filter khi chúng là **dữ liệu literal**:

| Ký tự dữ liệu | Dạng escape trong filter | Nếu không escape |
| --- | --- | --- |
| `*` | `\2a` | Có thể trở thành wildcard |
| `(` | `\28` | Có thể làm hỏng cấu trúc filter |
| `)` | `\29` | Có thể làm hỏng cấu trúc filter |
| `\` | `\5c` | Có thể ảnh hưởng cách diễn giải escape |
| Byte NUL | `\00` | Không được đưa trực tiếp vào filter string |

Khi đầu vào có ký tự Unicode cần encode, quy tắc biểu diễn octet theo RFC 4515 cũng phải được tôn trọng. Không dùng cách tự viết `replace("*", "\\2a")` làm phương pháp duy nhất: rất dễ quên những ký tự còn lại hoặc escape sai khi vừa có wildcard chủ động vừa có dữ liệu literal.

Trong Java string literal, cần viết dấu backslash đúng với cú pháp Java:

~~~java
String expected = "(uid=lan\\2a)";
// Runtime string: (uid=lan\2a)
~~~

Trong thực tế, không cần tự ghép chuỗi expected để thực thi truy vấn nếu có thể sử dụng API Spring LDAP chịu trách nhiệm encode giá trị.

## 5. filter(String filterFormat, Object... params): cú pháp cố định, giá trị động

Khi format do ứng dụng kiểm soát nhưng giá trị nhận từ request, dùng overload có tham số:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public LdapQuery queryByUsername(String username) {
    return LdapQueryBuilder.query()
        .base("ou=people")
        .attributes("uid", "cn")
        .filter(
            "(&(objectClass=inetOrgPerson)(uid={0}))",
            username
        );
}
~~~

Trong ví dụ này:

1. Chuỗi format chứa **cấu trúc filter cố định**.
2. `{0}` đánh dấu nơi chèn tham số.
3. Spring LDAP sử dụng `MessageFormat` và **`LdapEncoder.filterEncode(...)`** cho giá trị tham số trước khi chèn.
4. Giá trị `lan*` được xử lý như chuỗi literal chứa dấu sao, **không** biến thành prefix wildcard.

**Tính an toàn nằm ở ranh giới “format cố định — value động”.** Overload này không thể bảo đảm an toàn nếu bạn tự ghép dữ liệu người dùng vào chuỗi format trước khi gọi.

### 5.1. Hai tham số trong filter OR

~~~java
public LdapQuery queryByUidOrMail(
        String uid, String email) {

    return LdapQueryBuilder.query()
        .base("ou=people")
        .attributes("uid", "cn", "mail")
        .countLimit(25)
        .filter(
            "(&(objectClass=inetOrgPerson)(|(uid={0})(mail={1})))",
            uid,
            email
        );
}
~~~

Đây là một filter phức hợp:

~~~ldap
(&(objectClass=inetOrgPerson)(|(uid=...)(mail=...)))
~~~

Nếu hai tham số đến từ request, chúng vẫn được encode như **giá trị**; dấu `|`, `&` và các dấu ngoặc thuộc **template tin cậy**. Filter không cho phép input động thay đổi tên attribute `uid`, `mail` hoặc cấu trúc OR.

Điều kiện OR có thể trả nhiều entry khi hai giá trị tìm kiếm thuộc hai người khác nhau. Không dùng kết quả đầu tiên làm căn cứ xác thực danh tính. Nếu yêu cầu nghiệp vụ cần duy nhất một user, phải thiết kế identifier/uniqueness phù hợp.

### 5.2. Lưu ý cú pháp MessageFormat

Overload format sử dụng `java.text.MessageFormat`. Do đó cần nhớ:

- Placeholder dạng `{0}`, `{1}` có ý nghĩa trong **format string**.
- Dấu nháy đơn và dấu ngoặc nhọn dùng trong format có quy tắc escape/quote của `MessageFormat`; không tự tạo format có những ký tự này bằng cách nối chuỗi từ input.
- Không đưa `{0}` vào dữ liệu user với kỳ vọng nó sẽ bị hiểu thành placeholder: user value là dữ liệu, không phải format.
- Không dùng format động do người dùng chọn. Nếu phải chọn các kiểu tìm kiếm khác nhau, hãy chọn từ các **template cố định được whitelist**.

Trong Spring LDAP, overload này được dùng để escape **giá trị assertion trong filter**. Nó **không** escape tên attribute tùy ý hoặc DN/search base: hai đối tượng đó có cú pháp và cơ chế kiểm soát riêng.

## 6. filter(Filter filter): ghép các thành phần có cấu trúc

Spring LDAP core có các lớp Filter như:

- `EqualsFilter` cho equality.
- `AndFilter` cho điều kiện AND.
- `OrFilter` cho điều kiện OR.
- `PresentFilter` cho presence.
- `HardcodedFilter` để chèn một phần filter **đã được tin cậy**.

Lựa chọn đối tượng `Filter` giúp xây điều kiện phức hợp mà không phải nối dấu ngoặc thủ công.

### 6.1. Ghép phần cố định và input an toàn

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.HardcodedFilter;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public LdapQuery employeesByUid(String username) {
    AndFilter filter = new AndFilter();

    // Cố định và do ứng dụng kiểm soát.
    filter.and(
        new HardcodedFilter("(objectClass=inetOrgPerson)")
    );

    // Dữ liệu động: EqualsFilter encode giá trị.
    filter.and(new EqualsFilter("uid", username));

    return LdapQueryBuilder.query()
        .base("ou=people")
        .attributes("uid", "cn")
        .filter(filter);
}
~~~

Ưu điểm:

- Phần hardcoded không cần tự đặt `&` bao quanh nhiều điều kiện.
- Input `username` đi qua `EqualsFilter`, thay vì được chèn thẳng vào chuỗi raw.
- Khi số điều kiện tăng, `AndFilter` có thể giúp giữ cấu trúc rõ ràng.

**Cảnh báo:** `HardcodedFilter` **không xác minh hay escape** nội dung truyền vào constructor. Chỉ dùng lớp này với fragment **đã được kiểm soát**, ví dụ `"(objectClass=inetOrgPerson)"`, tuyệt đối không dùng `new HardcodedFilter("(uid=" + input + ")")`.

### 6.2. Ghép AND/OR với hai giá trị động

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.filter.PresentFilter;

public LdapQuery findMatchingProfiles(
        String username, String email) {

    OrFilter identity = new OrFilter();
    identity.or(new EqualsFilter("uid", username));
    identity.or(new EqualsFilter("mail", email));

    AndFilter all = new AndFilter();
    all.and(new PresentFilter("cn"));
    all.and(identity);

    return LdapQueryBuilder.query()
        .base("ou=people")
        .attributes("uid", "cn", "mail")
        .filter(all);
}
~~~

Filter này tương đương về cấu trúc với:

~~~ldap
(&(cn=*)(|(uid=<giá_trị_đã_escape>)(mail=<giá_trị_đã_escape>)))
~~~

Các chỗ viết `<giá_trị_đã_escape>` trong ví dụ giải thích **không phải cú pháp LDAP literal để copy vào server**; lúc chạy, các lớp filter builder sẽ tạo giá trị đã encode.

Dùng `Filter` object thường phù hợp hơn hardcoded string khi ứng dụng phải hỗ trợ nhiều tổ hợp AND/OR. Ngược lại, với một filter chuẩn không có tham số, `filter(String)` có thể ngắn gọn và dễ đọc.

## 7. Không trộn filter(...) và where(...)

**Đây là ràng buộc quan trọng của `LdapQueryBuilder`.** Theo tài liệu Spring LDAP, bạn chọn **một** trong hai cách xác định filter:

1. **DSL điều kiện:** bắt đầu bằng `where("attribute")` và tiếp tục `is`, `and`, `or`…
2. **Filter hoàn chỉnh:** bắt đầu bằng một trong ba overload `filter(...)`.

Không kết hợp:

~~~java
// Cách làm sai: cố khai báo filter hai lần.
LdapQueryBuilder builder = LdapQueryBuilder.query();
builder.filter("(objectClass=inetOrgPerson)");
builder.where("uid").is("lan");
// IllegalStateException: đã xác định filter trước đó.
~~~

Với mã sử dụng fluent chain, còn có vấn đề về kiểu trả về: `filter(...)` trả `LdapQuery`, nên không nên mong gọi tiếp các phương thức cấu hình builder sau đó.

### 7.1. Phải cấu hình base, scope và limits **trước filter**

Cách đúng:

~~~java
LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn")
    .timeLimit(1_500)
    .countLimit(30)
    .filter("(&(objectClass=inetOrgPerson)(mail=*))");
~~~

Không nên đặt cấu hình như `base(...)` hoặc `countLimit(...)` **sau** `where(...)` hoặc `filter(...)`: builder yêu cầu cấu hình thuộc tính tìm kiếm trước khi bắt đầu xây filter, và các bước sau khi filter được xác định có thể bị từ chối theo contract.

### 7.2. Nếu cần điều kiện động, xây lại filter

Thay vì bắt đầu `where(...)` rồi cố nối thêm một hardcoded filter, hãy:

- Xây **toàn bộ filter bằng DSL** nếu đủ khả năng biểu diễn; hoặc
- Xây **một `AndFilter`** gồm phần raw tin cậy và các `EqualsFilter` động; hoặc
- Dùng **một mẫu `filter(format, params)`** có đầy đủ AND/OR và placeholder.

Đây là ba chiến lược thay thế nhau, **không phải ba bước bắt buộc trong cùng query**.

## 8. Hardcoded filter trong LdapTemplate và LdapClient

`LdapQuery` được tạo bởi `LdapQueryBuilder` có thể được dùng với `LdapTemplate`:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

public List<String> searchUids(
        LdapTemplate ldapTemplate, LdapQuery query) {

    return ldapTemplate.search(
        query,
        (AttributesMapper<String>) attrs ->
            (String) attrs.get("uid").get()
    );
}
~~~

Với `LdapClient` (tùy phiên bản Spring LDAP mà ứng dụng dùng), tư duy tương tự: `LdapQuery` mô tả base/scope/filter, rồi client thực thi và ánh xạ kết quả qua API fluent. Không nên sửa filter trực tiếp trong khâu mapping.

~~~java
// Minh họa ý tưởng với LdapClient có API search fluent.
List<String> uids = ldapClient.search()
    .query(query)
    .map((AttributesMapper<String>) attrs ->
        (String) attrs.get("uid").get())
    .list();
~~~

Khi triển khai thực tế, kiểm tra chính xác phiên bản Spring LDAP và overload mapping đang có; các method fluent có thể thay đổi giữa các phiên bản. Nội dung quan trọng là **query được xây riêng và cùng cơ chế an toàn**, không phải việc chuyển `LdapTemplate` sang `LdapClient` sẽ tự động sửa lỗi injection.

### 8.1. Spring Data LDAP và ODM có vai trò gì?

Repository trong Spring Data LDAP sử dụng mapping entity và phương thức truy cập khác với việc truyền raw `LdapQuery` vào template. Hardcoded filter phù hợp với những truy vấn directory chuyên biệt hoặc query phức tạp; ODM/repository phù hợp khi thao tác entry có cấu trúc nhất quán.

Một `@Attribute(name = "uid")` trong ODM không làm thay đổi syntax hay matching rule của `uid`. Mọi query vẫn chịu schema/ACL server.

## 9. Base DN, scope và filter phải hợp tác đúng

Giả sử `ContextSource` có cấu hình:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=directory-reader,ou=services,dc=example,dc=org
    # password: cung cấp qua secret manager / environment.
~~~

Khi query builder đặt `base("ou=people")`, nhiều API Spring LDAP hiểu đây là DN **tương đối** với `dc=example,dc=org`. Không gắn thêm base đầy đủ lần nữa khi API đang xử lý relative DN.

| Thành phần | Ví dụ | Lỗi dễ gặp |
| --- | --- | --- |
| `ContextSource.base` | `dc=example,dc=org` | Quên rằng base đã cấu hình |
| Query base | `ou=people` | Truyền lại `ou=people,dc=example,dc=org` vào chỗ nhận relative DN |
| Scope | `SearchScope.ONELEVEL` | Bỏ sót user nằm sâu trong OU con |
| Scope | `SearchScope.SUBTREE` | Chọn base quá cao, tìm quá rộng |
| Filter | `(&(objectClass=inetOrgPerson)(uid={0}))` | Ghép input vào raw string thay vì bind parameter |
| Attributes | `"uid", "cn"` | Mapper đọc thêm `mail` nhưng không yêu cầu mail |
| Count/time limits | `countLimit(50)`, `timeLimit(2000)` | Nghĩ giới hạn output đồng nghĩa toàn bộ tập kết quả |

### 9.1. Filter không giúp tìm entry ngoài scope

Ví dụ directory:

~~~text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    └── ou=engineering
        └── uid=minh
~~~

Nếu base là `ou=people` và scope `ONELEVEL`, filter `(uid=minh)` không thể tìm entry dưới `ou=engineering`, dù filter rất chính xác. Chọn `SUBTREE` nếu nghiệp vụ cần bao phủ OU con.

### 9.2. Hardcoded filter không bảo đảm truy vấn nhanh

Filter như:

~~~ldap
(cn=*a*)
~~~

có thể có số lượng match rất lớn hoặc chi phí cao. Query builder không tự thêm chỉ mục, không tự đặt giới hạn độ dài prefix và không biết tốc độ backend. Khi dùng hardcoded filter:

- Chọn base và scope nhỏ nhất đáp ứng yêu cầu nghiệp vụ.
- Ưu tiên equality trên identifier đáng tin cậy khi muốn tìm một người.
- Xem schema có `EQUALITY`/`SUBSTR` rule phù hợp không.
- Xác định indexing thực tế của LDAP server.
- Giới hạn số thuộc tính và kết quả; nếu cần paging, phải dùng cơ chế server/client phù hợp.
- Đo latency, lỗi giới hạn, tài nguyên server và tải đồng thời.

**Đừng khẳng định wildcard ở đầu luôn full scan**: nhiều LDAP backend hỗ trợ substring index. Ngược lại, có index cũng không bảo đảm một filter rất rộng sẽ nhanh.

## 10. Bảo mật: “filter tin cậy” nghĩa là gì?

Một filter raw nên được xem như **đoạn truy vấn có đặc quyền cấu trúc**. Nó được quyền quyết định attribute nào được hỏi, dùng AND/OR ra sao, có phủ định hay wildcard nào.

### 10.1. Phân loại nguồn filter

| Nguồn | Có nên đưa thẳng vào `filter(String)`? | Lý do |
| --- | --- | --- |
| Hằng Java do đội phát triển review | Có thể, khi cú pháp đã kiểm tra | Ứng dụng kiểm soát toàn bộ cấu trúc |
| Cấu hình version-controlled có review | Có thể, với kiểm thử và quyền sửa nghiêm ngặt | Dễ thay đổi, cần bảo vệ cấu hình |
| Bộ mẫu cố định được chọn bằng enum | Có thể, nếu mỗi mẫu là constant an toàn | Người dùng chỉ chọn mẫu, không sửa cú pháp |
| Username/email từ HTTP request | **Không** | Chứa ký tự đặc biệt, phải được encode như value |
| Text từ search box/autocomplete | **Không** | Có thể tạo wildcard hoặc cấu trúc ngoài dự định |
| LDAP filter hoàn chỉnh được gửi qua REST API | **Không mặc định** | Có thể vượt qua ràng buộc nghiệp vụ, gây injection |
| Cấu hình có thể sửa bởi tenant chưa được tin cậy | **Không mặc định** | Ranh giới tenant/ACL không thể chỉ dựa vào string |

Nếu API cần “advanced search”, nên nhận một **cấu trúc điều kiện giới hạn** (field, operator, value), whitelist thuộc tính/operation, rồi tự tạo `Filter` hoặc dùng template cố định. Không expose raw LDAP filter cho mọi client.

### 10.2. Không nhầm filter escaping với quyền truy cập

Giả sử `username` đã được encode đúng nhưng filter cố định chọn toàn bộ directory và tài khoản bind có quyền đọc quá rộng. Truy vấn vẫn có thể trả dữ liệu không phù hợp nghiệp vụ.

An toàn gồm nhiều lớp:

1. **Cấu trúc truy vấn** được ứng dụng kiểm soát.
2. **Value** được encode theo RFC 4515.
3. **DN và base** được tạo/kiểm tra theo cú pháp DN.
4. **ACL** giới hạn quyền của tài khoản `ContextSource`.
5. **Authorization** của ứng dụng quyết định ai được gọi chức năng.
6. **TLS**, giới hạn tài nguyên và logging bảo vệ vận hành.

**Không coi “không có injection” là đủ để truy vấn được quyền truy cập mọi attribute.**

### 10.3. Filter dùng cho authentication cần đặc biệt thận trọng

Nếu filter phục vụ tìm DN để bind authentication, không dùng một hardcoded filter quá rộng như `(cn=*)` rồi chọn entry đầu tiên. Filter phải xác định đúng danh tính cần kiểm tra và trả về **một entry duy nhất** theo chính sách directory.

Việc tìm thấy entry bằng search **không** chứng minh mật khẩu đúng. Spring Security LDAP nên chịu trách nhiệm chuyển kết quả bind thành `Authentication`, ánh xạ authorities và bảo vệ endpoint.

### 10.4. Không log secrets hoặc truy vấn chứa dữ liệu nhạy cảm

Không ghi mật khẩu, `userPassword`, credentials của service account hoặc toàn bộ JNDI environment vào log. Với truy vấn theo email/DN, filter có thể chứa thông tin định danh; chỉ log ở mức cần thiết và theo chính sách dữ liệu. Để quan sát hiệu năng, ưu tiên log mẫu truy vấn/loại operation, thời gian, số kết quả và mã lỗi thay vì luôn ghi nguyên giá trị.

## 11. Một số trường hợp dễ sai khi dùng hardcoded filter

### 11.1. Không dùng “SQL escaping” cho LDAP

~~~java
// Sai tư duy: giá trị được quote như SQL không đồng nghĩa an toàn LDAP.
String filter = "(uid='" + username + "')";
~~~

LDAP filter không dùng cơ chế SQL parameters hay SQL quotes. Dấu nháy đơn trong LDAP assertion value không phải biện pháp escape những dấu như `*`, `(`, `)`, `\`. Dùng overload `filter(format, params)` hoặc các lớp `Filter`.

### 11.2. Không dùng DN escaping cho filter

~~~text
DN có giá trị chứa dấu phẩy:
cn=Nguyen\, Lan,ou=people,dc=example,dc=org

LDAP filter tìm giá trị cn:
(cn=Nguyen, Lan)
~~~

DN escape giải quyết ranh giới RDN; filter escape giải quyết ký tự cú pháp trong assertion value. Khi mã hóa đầu vào filter, dùng API của Spring LDAP; không tự sửa chuỗi DN rồi bỏ vào filter mà không hiểu mục đích.

### 11.3. Không thêm wildcard để “sửa” mọi truy vấn

Một người dùng nhập `lan` và muốn tìm UID chính xác. Nếu ứng dụng biến nó thành `(uid=*lan*)`, kết quả có thể bao gồm nhiều username và tạo tập ứng viên lớn. `(uid=lan)` phù hợp hơn khi nghiệp vụ yêu cầu equality.

### 11.4. Không ghép filter của hai nguồn raw

~~~java
String filter = "(&" + configFilter + userFilter + ")";
~~~

Mẫu này khó kiểm soát khi `userFilter` đến từ request hoặc `configFilter` có cú pháp lỗi. Dùng `AndFilter` với mỗi thành phần được xác định nguồn tin cậy và encode value; hoặc một mẫu `filter(format, params)` đã kiểm soát hoàn toàn.

### 11.5. Không bỏ qua điều kiện không hỗ trợ trong schema

Một filter có thể đúng RFC 4515 nhưng không cho kết quả mong muốn nếu attribute type không hỗ trợ equality/substring matching rule phù hợp. Tên attribute LDAP không phân biệt hoa/thường, nhưng **giá trị** có case-sensitive hay không do schema và matching rule quyết định.

## 12. Mẫu ứng dụng thực tế: tìm nhân viên theo nhiều tiêu chí

Giả sử REST API cho phép tra cứu nhân viên theo **một trong hai khóa**: UID hoặc email. Hệ thống muốn giới hạn kết quả thuộc `inetOrgPerson` và chỉ đọc `uid`, `cn`, `mail`.

### 12.1. Service dùng parameterized hardcoded filter

~~~java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
public class EmployeeDirectorySearchService {

    public record EmployeeView(
        String uid,
        String commonName,
        String email
    ) {}

    private final LdapTemplate ldapTemplate;

    public EmployeeDirectorySearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<EmployeeView> search(String uid, String email) {
        if (uid == null || uid.isBlank()
                || email == null || email.isBlank()) {
            throw new IllegalArgumentException(
                "UID và email phải có giá trị"
            );
        }

        LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid", "cn", "mail")
            .countLimit(50)
            .timeLimit(2_000)
            .filter(
                "(&(objectClass=inetOrgPerson)(|(uid={0})(mail={1})))",
                uid,
                email
            );

        return ldapTemplate.search(
            query,
            (AttributesMapper<EmployeeView>) attrs ->
                new EmployeeView(
                    required(attrs, "uid"),
                    required(attrs, "cn"),
                    optional(attrs, "mail")
                )
        );
    }

    private static String required(Attributes attrs, String name)
            throws javax.naming.NamingException {
        Attribute a = attrs.get(name);
        if (a == null || a.size() == 0) {
            throw new IllegalArgumentException(
                "LDAP entry thiếu thuộc tính " + name
            );
        }
        return (String) a.get();
    }

    private static String optional(Attributes attrs, String name)
            throws javax.naming.NamingException {
        Attribute a = attrs.get(name);
        return a == null || a.size() == 0
            ? null : (String) a.get();
    }
}
~~~

Ví dụ này có các giới hạn được nêu rõ:

- Filter cấu trúc do ứng dụng quản lý; `uid` và `email` được encode như các giá trị.
- Chỉ cần thông tin hiển thị; method trả danh sách, **không tự giả định UID/email duy nhất toàn directory**.
- Code chặn tham số rỗng để tránh truy vấn không có ý nghĩa; API thực có thể thiết kế tìm bằng một trường hoặc hai trường theo hợp đồng khác.
- `SearchScope.SUBTREE` bao phủ các OU con dưới `ou=people`, miễn tài khoản dịch vụ có quyền.
- `countLimit` và `timeLimit` là hàng rào quản lý tải, không thay thế schema/index hay một SLA đã được đo.
- Các thuộc tính `uid`, `cn` và `mail` được giả định là string. Với binary/multivalued attributes, phải kiểm tra kiểu theo schema trước khi map.

### 12.2. Kịch bản filter bị tấn công

Hãy thử các giá trị trong test:

~~~text
lan
lan*
la(n)
lan\test
(uid=*)
Lan Nguyen
Nguyễn Lan
~~~

Với overload `filter(format, params)` hoặc các lớp `EqualsFilter`, những giá trị đó phải được xử lý như **dữ liệu literal** trong equality assertion, không biến thành tên attribute, wildcard hay nhánh logic mới. Kiểm tra filter được encode là một phần; để xác nhận server trả đúng entry, vẫn cần LDAP integration test.

### 12.3. Nếu cần hardcoded cấu hình và trường động khác nhau

Ví dụ một filter nền cố định:

~~~ldap
(&(objectClass=inetOrgPerson)(mail=*))
~~~

Có thể dùng `HardcodedFilter` ghép với `EqualsFilter("uid", uid)` bằng `AndFilter`. Cách này phù hợp nếu filter nền được cấu hình riêng và đã được kiểm duyệt. Chỉ dùng một query builder `filter(Filter)` để tránh trộn `filter` và `where`.

## 13. Kiểm thử và chẩn đoán

### 13.1. Unit test điều kiện query

Dùng unit test để xác minh:

1. Filter hằng được giữ nguyên, cú pháp dấu ngoặc khớp và không vô tình có input động.
2. Với `filter(format, params)`, username `lan*` tạo **literal `*` đã được escape**.
3. Các ký tự `(`, `)`, `\` và Unicode không thể tạo nhánh filter mới ngoài ý định.
4. Không được trộn `filter(...)` với `where(...)`; kỳ vọng `IllegalStateException` theo contract.
5. Cấu hình base/scope/attributes/countLimit/timeLimit được đặt trước filter.
6. Mapper xử lý attribute bắt buộc/vắng mặt và giá trị có kiểu không mong đợi.
7. Bộ lọc chọn từ enum/whitelist không cho phép client gửi raw filter.

Ví dụ minh họa kiểm tra output của query:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

LdapQuery query = LdapQueryBuilder.query()
    .filter("(uid={0})", "lan*");

String encoded = query.filter().encode();

if (!"(uid=lan\\2a)".equalsIgnoreCase(encoded)) {
    throw new AssertionError(
        "Input '*' phải là literal trong equality filter"
    );
}
~~~

Đây là kiểm tra **cú pháp filter được sinh ra** (hex có thể viết hoa/thường); nó không xác minh schema hoặc kết quả search trên LDAP server. Với test production, dùng assertion framework phù hợp và tránh phụ thuộc vào định dạng không có cam kết canonical nếu so sánh biểu diễn dài/phức tạp.

### 13.2. Integration test với LDAP server

Chuẩn bị LDAP test server (embedded hoặc môi trường cô lập) chứa entry đúng schema, với tài khoản bind có quyền phù hợp.

| Tình huống | Cần kiểm tra |
| --- | --- |
| Filter cố định hợp lệ | Truy vấn trả đúng tập entry trong base/scope |
| Filter cố định sai dấu ngoặc | Truy vấn báo lỗi phù hợp, không bị nuốt |
| Attribute chưa có trong schema | Không mặc định coi filter hợp lệ về cú pháp là khớp dữ liệu |
| Input có dấu `*` literal | Không trở thành substring |
| Input có dấu ngoặc/backslash | Không thay cấu trúc filter |
| OR hai trường | Không có hành vi chọn một entry tùy ý |
| Scope ONELEVEL vs SUBTREE | OU lồng nhau được/bị loại đúng kỳ vọng |
| Account với ACL đọc hạn chế | Filter không vượt qua ràng buộc ACL |
| Index substring/equality khác nhau | Đo chi phí và độ trễ trên directory đại diện |
| Size/time limits | Không coi tập kết quả bị giới hạn là danh sách đầy đủ |
| TLS/bind thất bại | Lỗi được phân loại, không báo “không có người dùng” |

**Không coi unit test filter đủ để kết luận ứng dụng an toàn.** Filter có thể được encode đúng nhưng query vẫn có scope quá rộng, quyền bind quá lớn hoặc nghiệp vụ cấp quyền dựa trên kết quả chưa xác thực.

### 13.3. Tình huống lỗi cần phân biệt

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `IllegalStateException` khi xây query | Trộn `filter(...)` và `where(...)` hoặc khai báo lại filter | Chọn một cách xác định filter |
| Filter không hợp lệ | Chuỗi hardcoded sai RFC 4515 | Review cú pháp, test trước khi đưa cấu hình vào production |
| Query trả nhiều người | Filter OR/substrings quá rộng | Tăng độ chọn lọc; đừng chọn entry đầu tiên nếu cần danh tính |
| Query trả rỗng | Base/scope/filter/schema/ACL hoặc dữ liệu | Kiểm tra từng yếu tố, không đoán từ một danh sách rỗng |
| `NameNotFoundException` hoặc lỗi DN | Base DN hoặc relative DN sai | Kiểm tra `ContextSource.base` và DN |
| Timeout/mất kết nối | Server quá tải, mạng, TLS, DNS hoặc pool | Phân loại lỗi vận hành, giới hạn retry có kiểm soát |
| `AuthenticationException` khi bind | Credentials hoặc chính sách server | Xử lý xác thực qua cơ chế phù hợp |
| Lỗi schema/permission | Attribute bị hạn chế, matching rule không áp dụng | Kiểm tra schema và ACL, không thay filter bằng wildcard rộng |

## 14. Câu hỏi tự kiểm tra

1. `filter(String hardcodedFilter)` làm gì với các ký tự đặc biệt bên trong chuỗi?
2. Vì sao `filter("(uid=" + userInput + ")")` không an toàn?
3. Nếu `userInput = "lan*"`, làm sao tìm **literal** `lan*` chứ không phải prefix `lan`?
4. Sự khác biệt giữa `filter("(uid={0})", userInput)` và `filter("(uid={0})")` là gì?
5. Khi nào `filter(Filter filter)` phù hợp hơn `filter(String)`?
6. `HardcodedFilter` có tự validate và escape input động không?
7. Vì sao không thể tiếp tục `where(...)` sau khi đã gọi `filter(...)` trên cùng builder?
8. Tại sao phải đặt `base(...)`, `attributes(...)`, `countLimit(...)` trước khi xác định filter?
9. Với filter `(&(objectClass=inetOrgPerson)(mail=*)(!(uid=svc*)))`, entry nào có thể khớp?
10. Cùng filter nhưng search base `ou=people` và `ou=groups` khác gì nhau?
11. Đã dùng parameterized filter an toàn thì còn cần ACL/TLS/authorization không?
12. Khi có cả username và email, vì sao filter OR có thể trả hơn một entry?
13. Tại sao `(cn=*)` là presence, còn `(cn=*Lan*)` là substring?
14. Nếu filter được giữ trong một tệp cấu hình được deploy cùng ứng dụng, ai phải có quyền chỉnh sửa tệp đó?
15. Làm sao biết một filter hiệu năng thấp do hardcoded string, do schema/index, hay do phạm vi tìm kiếm?

**Gợi ý đáp án:** (1) Giữ nguyên, không escape/validate; (2) input có thể làm thay đổi cấu trúc hoặc wildcard; (3) overload tham số hoặc `EqualsFilter`; (4) trường hợp thứ nhất encode dữ liệu và chèn vào placeholder, trường hợp thứ hai chỉ là một chuỗi raw chứa literal `{0}`; (5) cần ghép điều kiện có cấu trúc; (6) không; (7) builder chỉ nhận một cách xác định filter; (8) cấu hình tìm kiếm được thiết kế trước khi thiết lập filter; (9) inetOrgPerson có mail, uid không bắt đầu svc theo rule; (10) khác phạm vi cây; (11) có; (12) điều kiện có thể khớp hai entry riêng; (13) ký hiệu `*` đơn độc vs các fragment; (14) người quản trị/đội phát triển có quyền kiểm soát cấu hình; (15) đo thực tế, xem base/scope/schema/index/ACL và log server.

## 15. Checklist sử dụng trong dự án

- [ ] Filter hardcoded **không chứa** dữ liệu raw từ request hoặc nguồn không tin cậy.
- [ ] Nếu có giá trị động, dùng `filter(format, params)`, `where(...).is(...)` hoặc các lớp `Filter` phù hợp.
- [ ] Không dùng `HardcodedFilter` cho input không tin cậy.
- [ ] Không trộn `filter(...)` với `where(...)` trong cùng query builder.
- [ ] Đặt base, scope, returning attributes, count/time limit **trước** filter.
- [ ] Phân biệt LDAP filter escaping với DN escaping.
- [ ] Kiểm tra cấu trúc `&`/`|`/`!` và matching rule của schema.
- [ ] Kiểm tra search base tương đối với `ContextSource.base`.
- [ ] Hạn chế filter rộng, nhiều wildcard và số nhánh OR không kiểm soát.
- [ ] Dùng LDAPS/StartTLS với xác minh chứng chỉ, không ghi credentials vào log.
- [ ] Tài khoản bind có ACL tối thiểu; authorization của ứng dụng được kiểm tra riêng.
- [ ] Unit test input có ký tự đặc biệt và integration test với directory có schema thực tế.
- [ ] Đo hiệu năng thực tế trước khi quyết định thay đổi chỉ mục/pooling.
- [ ] Nếu cấu hình cho phép sửa filter, phải có quyền truy cập, review và quy trình rollback rõ ràng.

## 16. Ghi nhớ

**`LdapQueryBuilder.filter(String)` là lối thoát hữu ích khi bạn đã có một LDAP filter hoàn chỉnh, cố định và được kiểm soát.** Đổi lại, API này **không escape và không validate** chuỗi, nên tuyệt đối không chuyển thẳng input người dùng thành filter.

Khi muốn giữ cấu trúc filter nhưng truyền giá trị động, dùng **`filter(String format, Object... params)`**, vốn áp dụng `LdapEncoder.filterEncode` cho tham số; hoặc dùng **`filter(Filter)`** với `AndFilter`, `OrFilter`, `EqualsFilter` và một phần hardcoded tin cậy khi cần. `filter(...)` và `where(...)` là **hai cách thay thế nhau**, không kết hợp trên cùng query.

Trong **Spring LDAP**, một filter đúng phải đi cùng search base/scope, schema/matching rule, ACL, TLS và việc xử lý lỗi/giới hạn. Chỉ khi các lớp đó phối hợp đúng, bạn mới có một truy vấn an toàn, chính xác và có thể vận hành được.

### Tài liệu tham khảo

- [Spring LDAP — Advanced LDAP Queries: Hardcoded Filters](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring LDAP Javadoc — LdapQueryBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html)
- [Spring LDAP Javadoc — HardcodedFilter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/HardcodedFilter.html)
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517)
