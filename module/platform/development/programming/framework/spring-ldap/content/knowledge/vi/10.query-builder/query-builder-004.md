# Criteria cho equality và matching trong Spring LDAP Query Builder

Khi truy vấn thư mục LDAP từ Java, điều quan trọng không chỉ là **tìm đúng thuộc tính**, mà còn phải chọn đúng **kiểu so khớp**. Biểu thức `(uid=an)` biểu diễn phép so sánh equality; `(cn=Nguyen*)` là tìm theo tiền tố; còn `(mail=*)` kiểm tra thuộc tính có tồn tại. Các biểu thức này trông giống nhau nhưng có ý nghĩa và chi phí truy vấn khác nhau.

Trong Spring LDAP, `LdapQueryBuilder` giúp mô tả điều kiện tìm kiếm theo cấu trúc thay vì nối chuỗi filter bằng tay. Bài học thuộc chương **Query builder** của SPRING_LDAP, tập trung vào cách viết **criteria cho equality và matching**, phân biệt matching do schema quyết định với mẫu substring, kết hợp nhiều điều kiện, tránh LDAP filter injection và áp dụng với `LdapTemplate`. Các nguyên tắc này cũng có ích khi sử dụng `LdapClient` hoặc ODM, bởi LDAP server vẫn là nơi thực hiện phép so khớp thực tế.

## 1. Một LDAP query gồm những thành phần nào?

Giả sử LDAP server cung cấp cây thông tin thư mục (*DIT*):

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   └── ou=contractors
│       └── uid=chi
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=app-reader
~~~

Một entry trong nhánh người dùng có thể có dạng:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
mail: an@example.org
departmentNumber: DEV
~~~

Để tìm entry, một yêu cầu LDAP thường gồm ba yếu tố:

| Thành phần | Ví dụ | Nhiệm vụ |
| --- | --- | --- |
| **Search base** | `ou=people,dc=example,dc=org` | Xác định điểm bắt đầu tìm trong DIT |
| **Search scope** | `SUBTREE_SCOPE` | Quyết định tìm tại base, một cấp con hay toàn bộ subtree |
| **Filter/criteria** | `(&(objectClass=inetOrgPerson)(uid=an))` | Chọn những entry thỏa điều kiện |

Khi `LdapContextSource` của Spring LDAP đã cấu hình base `dc=example,dc=org`, service thường đặt **search base tương đối** là `ou=people`. Hai phần đó tương ứng với DN đầy đủ `ou=people,dc=example,dc=org` trên server.

**Criteria không thay thế base và scope.** Một điều kiện equality hoàn toàn đúng vẫn trả về danh sách rỗng nếu query bắt đầu ở OU khác hoặc chỉ tìm `ONELEVEL_SCOPE` trong khi entry nằm sâu hơn.

## 2. Equality: `attribute=value`

**Equality filter** hỏi LDAP server xem entry có giá trị của một thuộc tính khớp với giá trị được cung cấp theo **matching rule equality của attribute type** hay không.

~~~text
(uid=an)
(cn=Nguyen Van An)
(mail=an@example.org)
(objectClass=inetOrgPerson)
~~~

Cú pháp chung là `(attribute=value)`. Trong Spring LDAP, cách biểu diễn trực tiếp nhất thường là:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

String requestedUid = "an";

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("uid").is(requestedUid);
~~~

`.where("uid").is(requestedUid)` tạo **equality assertion** đối với thuộc tính `uid`. Giá trị `requestedUid` được xử lý ở vị trí **dữ liệu của filter**, không phải một đoạn cú pháp LDAP filter do người dùng điều khiển.

### Equality không nhất thiết là so sánh byte-for-byte

Đây là điểm quan trọng nhất khi hiểu chữ *matching*.

Từng attribute type trong LDAP schema có thể xác định một **equality matching rule**. Tùy attribute và server, rule này có thể so sánh chuỗi không phân biệt hoa/thường, so khớp DN theo quy tắc dành cho DN hoặc dùng cách so sánh đặc thù khác.

Ví dụ về cách suy nghĩ:

| Trường hợp | Điều có thể xảy ra | Vì sao |
| --- | --- | --- |
| Tìm `(cn=Nguyen Van An)` | Có thể khớp với giá trị tên có khác biệt hoa/thường | `cn` thường dùng quy tắc kiểu `caseIgnoreMatch` |
| Tìm `(uid=AN)` | Có thể khớp với UID `an` trên schema thông dụng | Tùy equality matching rule của `uid` |
| Tìm `(member=uid=an,ou=people,dc=example,dc=org)` | So khớp giá trị DN theo quy tắc của thuộc tính `member` | Không phải so sánh chuỗi văn bản tùy ý |
| Tìm một thuộc tính kiểu số | Cần tuân thủ syntax và matching rule của attribute | Không suy luận từ cách Java so sánh String |

**`.is("An")` không có nghĩa Spring tự thực hiện `equalsIgnoreCase(...)`.** Spring xây biểu thức filter; LDAP server quyết định so khớp dựa trên schema. Vì thế không thể khẳng định mọi trường hợp đều phân biệt hoặc không phân biệt hoa/thường, dấu tiếng Việt, khoảng trắng hay ký tự Unicode.

Nếu hệ thống có yêu cầu định danh **phải phân biệt chữ hoa/chữ thường**, cần kiểm tra schema và matching rule thực tế, thay vì chỉ dùng equality thông thường rồi giả định kết quả. Tương tự, đừng tùy tiện `toLowerCase()` dữ liệu người dùng trước khi tìm nếu việc chuẩn hóa không nằm trong hợp đồng nghiệp vụ.

## 3. `LdapQueryBuilder`: xây equality criteria an toàn

Trong ứng dụng, ta thường muốn giới hạn kết quả trong một loại object class và tìm đúng UID:

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

record PersonSummary(String uid, String commonName, String mail) {}

public class PersonSearchService {

    private final LdapTemplate ldapTemplate;

    public PersonSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findByUid(String userInput) {
        if (userInput == null
                || userInput.isBlank()
                || userInput.length() > 128) {
            throw new IllegalArgumentException("Invalid uid");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchControls.SUBTREE_SCOPE)
                .attributes("uid", "cn", "mail")
                .countLimit(50)
                .timeLimit(2000)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(userInput);

        return ldapTemplate.search(
                query,
                (AttributesMapper<PersonSummary>) attrs ->
                        new PersonSummary(
                                (String) attrs.get("uid").get(),
                                (String) attrs.get("cn").get(),
                                attrs.get("mail") == null
                                        ? null
                                        : (String) attrs.get("mail").get()));
    }
}
~~~

Giả sử `ContextSource.base=dc=example,dc=org`, query bắt đầu từ `ou=people,dc=example,dc=org`. Phép `SUBTREE_SCOPE` cho phép tìm cả entry `uid=chi` dưới OU con `ou=contractors`.

Các thành phần trong ví dụ có trách nhiệm tách bạch:

1. `.base("ou=people")`: xác định **nhánh tìm**, tương đối với base đã cấu hình.
2. `.searchScope(...)`: xác định **độ sâu**.
3. `.attributes(...)`: chỉ yêu cầu các thuộc tính cần để mapping, thay vì tải toàn bộ dữ liệu.
4. `.countLimit(...)`, `.timeLimit(...)`: giới hạn tài nguyên ở phía yêu cầu; server còn có thể áp giới hạn riêng.
5. `.where("objectClass").is(...)`: bắt đầu điều kiện equality.
6. `.and("uid").is(userInput)`: yêu cầu cả điều kiện object class lẫn UID cùng đúng.
7. `AttributesMapper`: chuyển attributes thành Java object; ở ví dụ, `mail` có thể vắng mặt.

Bộ lọc logic tương ứng, khi `userInput=an`:

~~~text
(&(objectClass=inetOrgPerson)(uid=an))
~~~

Lưu ý: `uid`, `cn` có thể có nhiều giá trị theo schema; ví dụ DTO đơn giản chỉ lấy giá trị đầu tiên để tập trung vào criteria. Với dữ liệu thực tế, cần xác định chính xác mô hình đa trị và ACL trước khi ánh xạ.

**Quan trọng:** `countLimit` không tự tạo cơ chế phân trang để tải tất cả kết quả. Nếu ứng dụng cần duyệt danh sách lớn, phải xem xét tính năng paging phù hợp với server và client. Không mở rộng search thành toàn bộ naming context khi chưa cần thiết.

## 4. Equality khác với substring matching

Trong filter LDAP, dấu `*` có ý nghĩa khác nhau tùy cách nó xuất hiện:

| Filter | Loại phép so khớp | Ý nghĩa |
| --- | --- | --- |
| `(uid=an)` | Equality | UID bằng `an` theo equality matching rule |
| `(uid=*)` | Presence | Entry có thuộc tính `uid` |
| `(cn=Nguyen*)` | Substring – prefix | CN bắt đầu bằng `Nguyen` |
| `(cn=*An)` | Substring – suffix | CN kết thúc bằng `An` |
| `(cn=*Van*)` | Substring – contains | CN có chứa `Van` |
| `(cn=Nguyen*An)` | Substring – kết hợp | CN bắt đầu bằng `Nguyen` và kết thúc bằng `An` |

Cú pháp `(cn=Nguyen*)` không phải phép equality so với giá trị chứa dấu sao. Đây là biểu thức **substring filter** sử dụng ký hiệu wildcard do ứng dụng chủ động quyết định.

### Dùng `.like(...)` cho mẫu substring được kiểm soát

Spring LDAP Query Builder cung cấp phương thức `.like(...)` để mô tả kiểu truy vấn theo pattern. Ví dụ cố định do ứng dụng định nghĩa:

~~~java
LdapQuery prefixQuery = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchControls.SUBTREE_SCOPE)
        .where("objectClass").is("inetOrgPerson")
        .and("cn").like("Nguyen*");
~~~

Trong ví dụ trên, `Nguyen*` là **pattern tin cậy được viết trong code**. Dấu sao cuối thể hiện ý định tìm theo tiền tố, khác với việc tìm chính xác chuỗi `"Nguyen*"`.

Nếu người dùng muốn tìm một tên **chứa dấu sao thật**, phải xem dấu sao đó là dữ liệu, không phải wildcard. Để tìm chính xác một chuỗi như `A*B`, ưu tiên:

~~~java
String inputName = "A*B";

LdapQuery exactQuery = LdapQueryBuilder.query()
        .base("ou=people")
        .where("cn").is(inputName);
~~~

Về nghĩa, dấu sao trong equality assertion phải được escape để không trở thành wildcard, tương ứng `(cn=A\2aB)`.

**Không chuyển mọi tìm kiếm “theo tên” thành `.like(userInput)`.** Nếu đầu vào chứa wildcard do người dùng nhập, bạn có thể vô tình trao quyền điều khiển phạm vi truy vấn. Với chức năng tìm theo tiền tố hoặc chứa chuỗi, cần có cơ chế tạo substring filter trong đó **đoạn dữ liệu được escape riêng**, còn wildcard là ký hiệu do ứng dụng sinh ra. Việc nối `"*" + input + "*"` rồi truyền thẳng vào mẫu cần được kiểm tra rất kỹ với API và phiên bản thư viện cụ thể.

### Nếu ứng dụng muốn cho phép một số pattern cố định

Một cách an toàn và dễ kiểm tra là để client chọn **khóa nghiệp vụ**, còn ứng dụng quyết định pattern LDAP:

~~~java
import java.util.Map;

Map<String, String> allowedPrefixes = Map.of(
        "nguyen", "Nguyen*",
        "tran", "Tran*");

String pattern = allowedPrefixes.get(prefixKey);
if (pattern == null) {
    throw new IllegalArgumentException("Unsupported prefix");
}

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("cn").like(pattern);
~~~

Pattern đến từ allowlist do ứng dụng kiểm soát; người dùng không gửi chuỗi filter tùy ý. Giải pháp này phù hợp với chức năng lọc theo nhóm pattern đã được định nghĩa trước, không phải công cụ tìm substring tự do.

## 5. Presence: kiểm tra thuộc tính có tồn tại

**Presence filter** có dạng `(attribute=*)`. Nó không yêu cầu giá trị cụ thể mà chỉ kiểm tra entry có ít nhất một giá trị cho thuộc tính đó theo cách LDAP server đánh giá.

Ví dụ:

~~~text
(mail=*)
(telephoneNumber=*)
(uid=*)
~~~

Trong API Query Builder, có thể biểu diễn điều kiện kiểm tra sự hiện diện:

~~~java
LdapQuery havingMail = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("mail").isPresent();
~~~

Lưu ý:

- `(mail=*)` không đồng nghĩa địa chỉ email đã đúng định dạng hoặc được xác minh.
- `mail` là thuộc tính tùy chọn trong nhiều schema người dùng, nên không thể mặc định entry nào cũng có.
- Không nhìn thấy `mail` trong một search response chưa đủ để kết luận `mail` không có trên server: ACL và danh sách thuộc tính được yêu cầu có thể hạn chế dữ liệu trả về.
- Presence với `uid` **khác** equality `(uid=\2a)`. Biểu thức thứ hai tìm một UID có giá trị là dấu sao thật, nếu giá trị đó được schema cho phép.

Presence filter hữu ích cho chức năng “liệt kê tài khoản có email” hoặc phân tích chất lượng dữ liệu; nó **không** chứng minh email có thể sử dụng để gửi thư hay đăng nhập.

## 6. AND, OR và NOT trong criteria

Khi nghiệp vụ có nhiều điều kiện, cần hiểu toán tử logic LDAP:

| Cấu trúc | Ví dụ filter | Ý nghĩa |
| --- | --- | --- |
| AND – `&` | `(&(objectClass=inetOrgPerson)(uid=an))` | Cả hai điều kiện đều đúng |
| OR – `|` | `(|(uid=an)(mail=an@example.org))` | Ít nhất một điều kiện đúng |
| NOT – `!` | `(!(uid=an))` | Điều kiện con không khớp |
| Kết hợp lồng | `(&(objectClass=inetOrgPerson)(|(uid=an)(mail=an@example.org)))` | Là người dùng và khớp UID hoặc email |

### AND bằng Query Builder

Đây là trường hợp thông dụng nhất và dễ đọc nhất:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(requestedUid);
~~~

### OR lồng trong AND bằng filter object

Khi cần biểu diễn cấu trúc lồng, Spring LDAP cũng có các lớp filter như `AndFilter`, `OrFilter` và `EqualsFilter`. Ví dụ tìm người dùng có UID **hoặc** email khớp:

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.OrFilter;

if (uid == null || email == null) {
    throw new IllegalArgumentException("Both search values are required");
}

OrFilter alternatives = new OrFilter();
alternatives.or(new EqualsFilter("uid", uid));
alternatives.or(new EqualsFilter("mail", email));

AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(alternatives);

String encoded = filter.encode();

// Dùng encoded làm filter trong một phép search dưới ou=people,
// với search scope và mapping được xác định rõ.
~~~

Các class filter tạo cấu trúc và encode giá trị, tránh ghép chuỗi như `"(|(uid=" + uid + ")(mail=" + email + "))"`. Để dùng `encoded`, cung cấp nó cho overload `LdapTemplate.search(...)` nhận filter đã mã hóa và base/scope phù hợp.

**Chú ý ưu tiên toán tử:** các filter LDAP lồng nhau theo dấu ngoặc. Một query kết hợp `AND` và `OR` phải được nhóm theo quy tắc nghiệp vụ, không dựa vào suy đoán giống thứ tự ưu tiên toán tử trong Java hoặc SQL.

### NOT cần được hiểu theo logic LDAP

`(!(mail=an@example.org))` không đồng nghĩa “mọi entry đều có mail khác giá trị đó” theo suy nghĩ của ứng dụng. Một entry **không có `mail`** cũng có thể thỏa điều kiện phủ định.

Nếu nghiệp vụ là “có email nhưng không bằng `an@example.org`”, cần thể hiện cả hai điều kiện:

~~~text
(&(mail=*)(!(mail=an@example.org)))
~~~

Do đó cần xác định rõ trường vắng mặt, trường đa trị và phép phủ định có ý nghĩa gì trong nghiệp vụ trước khi viết criteria.

## 7. Matching rule của schema quyết định kết quả cuối cùng

Trong LDAP, **matching** không chỉ là cú pháp `=` hoặc dấu sao. Attribute type có thể khai báo các quy tắc so khớp:

| Loại rule | Phép so khớp liên quan | Ví dụ cách sử dụng |
| --- | --- | --- |
| **EQUALITY** | Equality assertion | `(uid=an)` |
| **SUBSTR** | Substring assertion | `(cn=Nguyen*)` |
| **ORDERING** | So sánh theo thứ tự khi được hỗ trợ | `(someAttribute>=value)` |
| **Approximate matching** | Cú pháp `~=` nếu server hỗ trợ | `(cn~=Nguyen An)` |
| **Extensible match** | Chọn rule hoặc DN attributes tường minh | Cú pháp `attribute:matchingRule:=value` |

LDAP server mới là nơi thực hiện phép so khớp. Không phải thuộc tính nào cũng hỗ trợ đầy đủ cả equality, substring, ordering và approximate matching.

### Equality và substring không thể thay thế cho nhau

Nếu thuộc tính có equality rule nhưng không có substring rule phù hợp, search substring có thể không hoạt động như người viết tưởng tượng. Ngược lại, nếu ứng dụng cần tìm đúng một mã định danh thì dùng substring vì tiện gõ có thể khiến nhiều entry khớp.

### Approximate matching không đồng nghĩa `.like(...)`

Biểu thức LDAP `(cn~=Nguyen An)` mang ý nghĩa approximate match theo khả năng server. Cách server xác định “gần đúng” có thể khác nhau, thậm chí không được hỗ trợ cho thuộc tính đó.

`.like("Nguyen*")` là mẫu **substring**, không tự thực hiện fuzzy search, tính khoảng cách Levenshtein hoặc chuẩn hóa tiếng Việt thông minh.

### Extensible match là tính năng nâng cao

Filter như:

~~~text
(cn:caseExactMatch:=Nguyen Van An)
~~~

chỉ có ý nghĩa mong muốn khi LDAP server chấp nhận matching rule được chỉ định và rule áp dụng cho attribute tương ứng. Không nên giả định mọi server hỗ trợ mọi rule theo tên này. Khi cần exact case-sensitive hoặc so khớp đặc biệt, hãy đọc schema thực tế và kiểm thử trước khi đưa vào API.

Nếu phải xây extensible filter từ đầu vào, phần assertion value vẫn cần escaping RFC 4515; tên attribute/matching rule phải thuộc allowlist của ứng dụng, không nhận cả biểu thức thô từ người dùng.

## 8. Escaping để input không trở thành cú pháp filter

Khi người dùng nhập tên hoặc UID, họ đang cung cấp **giá trị dữ liệu**, không phải biểu thức LDAP.

Đoạn mã sau không an toàn:

~~~java
String filter = "(&(objectClass=inetOrgPerson)(uid="
        + userInput + "))"; // KHÔNG AN TOÀN
~~~

Nếu `userInput` là `*`, biểu thức thành `(uid=*)`, tức **presence**, thay vì tìm UID có giá trị dấu sao. Nếu người dùng nhập dấu ngoặc, biểu thức có thể sai cú pháp hoặc làm thay đổi cấu trúc.

Theo RFC 4515, các ký tự sau cần được escape khi chúng là **dữ liệu trong assertion value**:

| Dữ liệu | Biểu diễn escape trong LDAP filter | Vai trò cú pháp cần tránh |
| --- | --- | --- |
| `*` | `\2a` | Wildcard/presence |
| `(` | `\28` | Mở filter |
| `)` | `\29` | Đóng filter |
| `\` | `\5c` | Bắt đầu chuỗi escape |
| NUL | `\00` | Octet NUL |

Ví dụ `input="a*b"` trong equality nên tạo điều kiện tương đương `(uid=a\2ab)`: dấu sao được hiểu là **ký tự thật**. Dạng hex có thể viết hoa hoặc viết thường.

Dùng `LdapQueryBuilder.where("uid").is(userInput)` hoặc `EqualsFilter` giúp API xây filter xử lý giá trị theo ngữ cảnh. **Không tự escape sẵn rồi lại đưa vào builder** nếu builder sẽ encode tiếp: lỗi *double escaping* có thể làm truy vấn tìm sai giá trị.

### Mã hóa Unicode

LDAP filter string representation sử dụng UTF-8. Khi escape một ký tự Unicode bằng dạng hex, phải escape **từng octet UTF-8**. Ví dụ chữ `é` là hai byte UTF-8 `C3 A9`, nên nếu viết hoàn toàn bằng escape octet sẽ là `\c3\a9`, không phải `\e9`.

Tránh tự viết hàm thay chuỗi thiếu kiểm tra mã hóa, và đừng nhầm escape LDAP filter với URL encoding hoặc escape trong Java source. Trong một Java string literal, để biểu diễn chuỗi LDAP filter chứa `\2a` thì cần viết `"\\2a"`; đó là quy tắc escape **của Java**, không phải của LDAP.

### DN escaping là cơ chế riêng

Nếu ứng dụng tạo DN từ `uid` hoặc `cn`, dùng `LdapNameBuilder`. Nếu ứng dụng tạo equality filter, dùng `LdapQueryBuilder` hoặc filter builder. DN/RDN được biểu diễn theo quy tắc khác, không dùng encoder filter thay encoder DN.

## 9. Cho phép chọn trường tìm kiếm nhưng không nhận attribute tùy ý

Một API có thể hỗ trợ tìm theo username, tên hoặc email. Không nên ghép trực tiếp `field` của HTTP request vào filter hoặc cho người dùng cung cấp cả biểu thức filter.

Thay vào đó, ánh xạ **khóa nghiệp vụ** sang danh sách attribute được phép:

~~~java
import java.util.Map;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class SearchCriteriaFactory {

    private static final Map<String, String> FIELDS = Map.of(
            "username", "uid",
            "name", "cn",
            "email", "mail");

    public LdapQuery exactMatch(String fieldKey, String value) {
        String attribute = FIELDS.get(fieldKey);
        if (attribute == null
                || value == null
                || value.isBlank()
                || value.length() > 128) {
            throw new IllegalArgumentException("Invalid search criteria");
        }

        return LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and(attribute).is(value);
    }
}
~~~

Các thuộc tính được **ứng dụng quyết định**, chỉ phần giá trị là input người dùng. Ngay cả tên trường hợp cú pháp LDAP cũng không mặc nhiên được phép truy vấn: có thể có thuộc tính nội bộ hoặc nhạy cảm mà người dùng không nên tìm theo.

Nếu API hỗ trợ toán tử “bằng”, “có thuộc tính”, “bắt đầu bằng”, cần áp dụng **allowlist cho cả toán tử** và quyết định cách encode phù hợp. Không nhận các chuỗi filter như `"(|(uid=*)(mail=*))"` từ client rồi chèn trực tiếp vào query.

## 10. Những lỗi dễ mắc khi viết criteria

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Equality không trả về entry đã biết | Base/scope sai, attribute không có giá trị khớp hoặc ACL giới hạn | Kiểm tra full DN, search base, scope và giá trị thực tế |
| `uid=*` trả về quá nhiều entry | Đã đưa dấu sao người dùng vào filter thô | Dùng equality builder để dấu sao được escape |
| `like(...)` trả về danh sách lớn | Pattern có wildcard rộng hoặc input không được kiểm soát | Xác định lại nghiệp vụ, giới hạn pattern và phạm vi |
| Không khớp vì khác hoa/thường | Matching rule của attribute khác kỳ vọng | Đọc `attributeTypes` và rule trên server |
| `isPresent()` trả kết quả không như kỳ vọng | Attribute bị che hoặc query nhắm vùng không đúng | Kiểm tra ACL, filter và DIT |
| Filter có cú pháp sai | Tự ghép dấu ngoặc/toán tử/escape sai | Dùng builder, kiểm thử ký tự đặc biệt |
| OR kết hợp AND cho kết quả ngoài ý muốn | Nhóm điều kiện sai | Viết rõ cấu trúc lồng AND/OR |
| Truy vấn chậm | Subtree quá rộng, filter ít chọn lọc hoặc thuộc tính không được index | Thu hẹp base/scope; trao đổi quản trị server về index/limit |
| Kết quả bị cắt | Client/server giới hạn số kết quả hoặc thời gian | Xử lý size/time limit và paging nếu cần |
| Một filter chạy khác nhau trên hai LDAP server | Schema, matching rules hoặc cấu hình ACL khác | Kiểm tra server thực tế và integration test |

**Lỗi tìm kiếm không phải lúc nào cũng là lỗi filter.** Lỗi `noSuchObject (32)` thường liên quan base DN không có; `insufficientAccessRights (50)` liên quan quyền; `filterError (87)` liên quan biểu thức filter không hợp lệ. Nhiều trường hợp đơn giản chỉ trả về 0 entry do không có dữ liệu phù hợp.

Một số server có thể che dữ liệu hoặc trả kết quả khác để thực thi chính sách bảo mật. Đừng khắc phục truy vấn rỗng bằng cách tăng quyền tài khoản dịch vụ lên quản trị mà chưa xác định nguyên nhân.

## 11. Kiểm thử equality và matching trong phòng lab

Chuẩn bị một LDAP server kiểm thử có base `dc=example,dc=org` và các entry mẫu:

| DN tương đối | `cn` | `uid` | `mail` |
| --- | --- | --- | --- |
| `uid=an,ou=people` | Nguyen Van An | an | an@example.org |
| `uid=binh,ou=people` | Tran Van Binh | binh | *(không có)* |
| `uid=chi,ou=contractors,ou=people` | Nguyen Thi Chi | chi | chi@example.org |

Tài khoản thử nghiệm được phép đọc `uid`, `cn` và `mail`. Tập dữ liệu chỉ để minh họa; matching rule và kết quả thực tế còn tùy schema/server.

### Kịch bản truy vấn

| Bài kiểm thử | Criteria | Kết quả kỳ vọng trong DIT mẫu |
| --- | --- | --- |
| A | Equality `(uid=an)`, subtree từ `ou=people` | An |
| B | Equality `(uid=chi)`, one-level từ `ou=people` | Không có Chi, vì entry nằm sâu hơn |
| C | Equality `(uid=chi)`, subtree từ `ou=people` | Chi |
| D | Substring `(cn=Nguyen*)`, subtree | An và Chi, nếu substring rule hỗ trợ |
| E | Presence `(mail=*)`, subtree | An và Chi |
| F | `(&(objectClass=inetOrgPerson)(uid=an))` | An |
| G | `(|(uid=an)(uid=binh))` | An và Bình |
| H | `(uid=\2a)` | Chỉ entry thật sự có UID là dấu sao, nếu được phép và có dữ liệu |
| I | `(uid=*)` | Các entry có UID, khác với bài H |

Để kiểm thử an toàn của builder, gửi các giá trị: `*`, `a*b`, `an(test)`, `team\ops`, chuỗi dài, NUL và Unicode. Mục tiêu là **không làm thay đổi cấu trúc filter do input**; không nhất thiết server cho phép mọi giá trị trong một attribute type.

### Unit test equality escaping

Ví dụ với JUnit 5 và `EqualsFilter` của Spring LDAP:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class CriteriaEscapingTest {

    @Test
    void literalStarIsNotPresence() {
        String actual = new EqualsFilter("uid", "*")
                .encode()
                .toLowerCase(Locale.ROOT);

        assertEquals("(uid=\\2a)", actual);
    }

    @Test
    void parenthesesAreDataInEquality() {
        String actual = new EqualsFilter("uid", "an(test)")
                .encode()
                .toLowerCase(Locale.ROOT);

        assertEquals("(uid=an\\28test\\29)", actual);
    }

    @Test
    void backslashIsEscaped() {
        String actual = new EqualsFilter("uid", "team\\ops")
                .encode()
                .toLowerCase(Locale.ROOT);

        assertEquals("(uid=team\\5cops)", actual);
    }
}
~~~

Test chuỗi chỉ xác minh lớp encode. Integration test còn cần đối chiếu DN, scope, ACL, matching rule và số entry thực tế trên server. Không đưa payload thử nghiệm vào thư mục production hoặc thao tác với tài khoản quản trị.

## 12. Bài thực hành: từ yêu cầu nghiệp vụ đến criteria

Ứng dụng quản lý nhân viên cần hỗ trợ ba chức năng:

1. **Tìm đúng username:** người dùng nhập một UID và hệ thống chỉ tìm giá trị equality tương ứng.
2. **Lọc theo họ:** người dùng chọn một nhóm họ đã được định nghĩa trước, ví dụ `nguyen` hoặc `tran`, và ứng dụng tìm theo prefix.
3. **Tìm hồ sơ có email:** người quản trị dữ liệu muốn liệt kê entry đang có thuộc tính `mail`.

Yêu cầu: xác định cách viết bằng Query Builder và lý do lựa chọn; đảm bảo chỉ tìm dưới `ou=people`. Với UID, kiểm tra hành vi của ký tự `*`.

### Đáp án tham khảo

**Chức năng 1 — equality:**

~~~java
LdapQuery byUsername = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(userInput);
~~~

Nên validation `userInput` về null, rỗng, độ dài và quy tắc UID trước khi gọi builder. Dấu `*` do người dùng nhập phải là **dữ liệu**, không biến thành presence/wildcard.

**Chức năng 2 — prefix từ allowlist:**

~~~java
String pattern = switch (familyKey) {
    case "nguyen" -> "Nguyen*";
    case "tran" -> "Tran*";
    default -> throw new IllegalArgumentException("Unsupported family");
};

LdapQuery byPrefix = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("cn").like(pattern);
~~~

Đây là pattern do **ứng dụng xây dựng**, không phải chuỗi wildcard tùy ý từ client. Kết quả phụ thuộc `cn` và substring matching rule của server.

**Chức năng 3 — presence:**

~~~java
LdapQuery havingEmail = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("mail").isPresent();
~~~

Nếu `mail` có mặt nhưng rỗng hoặc không hợp lệ theo nghiệp vụ, presence không tự xác nhận email có thể sử dụng; cần quy tắc kiểm tra chất lượng dữ liệu riêng.

### Câu hỏi tự đánh giá

| Câu hỏi | Đáp án ngắn |
| --- | --- |
| `.is("Nguyen*")` có nghĩa tìm mọi tên bắt đầu bằng Nguyen không? | **Không.** Equality coi dấu sao là dữ liệu literal; dùng substring pattern có chủ đích |
| `.like("Nguyen*")` có tự động làm fuzzy search không? | **Không.** Đây là substring/prefix pattern |
| `(mail=*)` có tìm email chứa dấu sao không? | **Không.** Đây là presence |
| Equality có luôn so khớp String phân biệt hoa/thường không? | **Không.** Phụ thuộc equality matching rule của attribute |
| Chỉ dùng `.is(...)` là đã giới hạn dữ liệu được đọc chưa? | **Chưa.** Còn phụ thuộc base, scope, ACL, giới hạn server |
| Cần làm gì khi người dùng chọn field tìm kiếm? | Dùng **allowlist** cho attribute và toán tử |
| Khi một entry không có `mail`, `(!(mail=x))` có thể khớp không? | Có thể; NOT của equality không có nghĩa thuộc tính bắt buộc phải hiện diện |
| Có nên tự escape input rồi truyền vào `.is(...)`? | Không; tránh double escaping, để builder xử lý assertion value |

## 13. Ghi nhớ

- **Equality** trong Spring LDAP được biểu diễn trực quan bằng `.where("attribute").is(value)`. LDAP server áp dụng **equality matching rule theo schema**, không phải Java `String.equals(...)`.
- **Substring matching** dùng pattern có wildcard, chẳng hạn `.like("Nguyen*")` khi pattern được kiểm soát. Không đưa wildcard do người dùng nhập vào mẫu mà không xử lý đúng ngữ nghĩa và escaping.
- **Presence** như `(mail=*)` chỉ kiểm tra thuộc tính có giá trị; không tương đương `(mail=\2a)`, cũng không xác nhận chất lượng dữ liệu.
- **AND/OR/NOT** phải được nhóm theo logic nghiệp vụ. Trong trường hợp kết hợp phức tạp, có thể dùng các filter object `AndFilter`, `OrFilter` và `EqualsFilter` để giữ cấu trúc rõ ràng.
- **Escaping RFC 4515** bảo toàn ý nghĩa đầu vào ở vị trí assertion value. DN escaping là cơ chế khác. Dùng builder đúng loại và không double escape.
- **Base, scope, giới hạn tài nguyên và ACL** vẫn cần được cấu hình cùng với criteria. Dùng `ContextSource` kết nối TLS, tài khoản bind quyền tối thiểu, và integration test trên LDAP server lab để xác nhận matching rule thật.
- ODM hay `LdapClient` có thể cung cấp API truy cập khác, nhưng không thay đổi nghĩa các phép so khớp do schema/LDAP server quy định.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [RFC 4515 – LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4517 – LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517)
- [RFC 4512 – LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
