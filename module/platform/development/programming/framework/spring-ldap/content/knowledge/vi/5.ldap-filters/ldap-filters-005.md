# Escaping giá trị người dùng trong filter LDAP

Trong LDAP, **filter** là biểu thức cho biết entry nào khớp điều kiện tìm kiếm. Các ký tự như `*`, `(`, `)` và `\` có ý nghĩa đặc biệt trong cú pháp filter. Khi một ứng dụng lấy dữ liệu từ người dùng rồi ghép trực tiếp vào filter, đầu vào có thể vô tình đổi ý nghĩa truy vấn hoặc bị lợi dụng để tìm kiếm ngoài dự kiến. **Escaping giá trị đầu vào theo cú pháp LDAP filter** là bước cần thiết để giữ nguyên nghĩa *dữ liệu* của giá trị đó.

Bài học thuộc chương **Filter LDAP** trong SPRING_LDAP. Ta sẽ đọc cú pháp escape theo RFC 4515, phân biệt escape filter với escape DN, rồi thực hành xây dựng truy vấn an toàn bằng `LdapQueryBuilder`, `LdapTemplate` và các filter builder của Spring LDAP. Các nguyên tắc tương tự cũng áp dụng khi sử dụng `LdapClient`, ODM hay những lớp truy cập LDAP khác.

## 1. Vấn đề bắt đầu từ đâu?

Giả sử ứng dụng tìm người dùng có `uid` bằng chuỗi nhập trên màn hình:

~~~text
Base DN: ou=people,dc=example,dc=org
Filter:  (&(objectClass=inetOrgPerson)(uid=an))
~~~

Filter trên nghĩa là lấy entry vừa thuộc `inetOrgPerson`, vừa có `uid` đúng bằng `an`. Cấu trúc của filter gồm các **thành phần cú pháp** và **giá trị so sánh**:

~~~text
(&(objectClass=inetOrgPerson)(uid=an))
 │ │                              └── giá trị assertion: an
 │ └── điều kiện 1: objectClass = inetOrgPerson
 └── toán tử AND, kết hợp các điều kiện
~~~

Một cách lập trình sai là nối giá trị của người dùng vào chuỗi:

~~~java
// KHÔNG AN TOÀN: inputUid đến trực tiếp từ client.
String filter = "(&(objectClass=inetOrgPerson)(uid=" + inputUid + "))";
~~~

Nếu `inputUid` bằng `*` thì đoạn mã tạo ra:

~~~text
(&(objectClass=inetOrgPerson)(uid=*))
~~~

Trong LDAP filter, `(uid=*)` là **phép kiểm tra thuộc tính uid có hiện diện**, không có nghĩa `uid` có giá trị đúng bằng dấu sao. Một yêu cầu vốn muốn tìm chính xác một UID đã bị chuyển thành truy vấn có thể khớp rất nhiều entry.

Đầu vào chứa dấu ngoặc hoặc toán tử cũng có thể phá cấu trúc filter, gây lỗi cú pháp hoặc tạo điều kiện truy vấn khác với dự định tùy cách chuỗi được ghép. Đây là một dạng **LDAP filter injection**. Không nên giả định mọi payload đều khai thác thành công: kết quả phụ thuộc filter bao quanh, parser, ACL và logic ứng dụng. Nhưng việc cho đầu vào quyết định cú pháp filter đã là lỗi thiết kế.

Mục tiêu đúng phải là: dù người dùng gửi `an`, `*` hay `an(test)`, ứng dụng vẫn chỉ tìm **giá trị bằng chính chuỗi đó** khi nghiệp vụ yêu cầu phép so sánh chính xác.

## 2. Cú pháp escape theo RFC 4515

RFC 4515 mô tả cách biểu diễn LDAP search filter dưới dạng chuỗi. Trong **giá trị assertion**, những ký tự có nghĩa đặc biệt cần được biểu diễn bằng dấu gạch chéo ngược và **hai chữ số hexadecimal cho từng octet**.

| Ký tự trong dữ liệu | Octet UTF-8/ASCII | Biểu diễn trong filter | Vì sao cần escape |
| --- | --- | --- | --- |
| Dấu sao `*` | `2A` | `\2a` | `*` có thể là wildcard hoặc phép kiểm tra tồn tại |
| Dấu ngoặc mở `(` | `28` | `\28` | Mở biểu thức filter |
| Dấu ngoặc đóng `)` | `29` | `\29` | Đóng biểu thức filter |
| Dấu gạch chéo ngược `\` | `5C` | `\5c` | Bắt đầu một chuỗi escape |
| Ký tự NUL | `00` | `\00` | NUL không được để nguyên trong chuỗi filter |

Hai chữ số hex có thể viết hoa hoặc viết thường: `\2a` và `\2A` đều biểu diễn octet `2A`. Escaping không làm thay đổi giá trị mà ứng dụng muốn tìm; nó chỉ ngăn parser LDAP đọc dữ liệu như cú pháp.

Ví dụ:

~~~text
Input người dùng         Giá trị được escape trong filter
an                       an
a*b                      a\2ab
an(qa)                   an\28qa\29
team\ops                 team\5cops
*                        \2a
~~~

Áp dụng vào filter hoàn chỉnh:

~~~text
Input:    a*b
Filter:   (uid=a\2ab)
Ý nghĩa:  uid bằng chính xác chuỗi "a*b"

Input:    *
Filter:   (uid=\2a)
Ý nghĩa:  uid bằng chính xác dấu "*"

Filter:   (uid=*)
Ý nghĩa:  thuộc tính uid tồn tại
~~~

**Cần phân biệt:** dấu `*` trong *cú pháp filter do lập trình viên chủ động viết* có thể mang ý nghĩa wildcard; dấu `*` nằm trong *giá trị so sánh do người dùng nhập* phải được coi là ký tự dữ liệu khi tìm chính xác.

### Không phải ký tự nào cũng cần escape

Dấu cách, dấu phẩy, dấu bằng hoặc dấu `|` có thể là dữ liệu bình thường ở vị trí giá trị assertion; không nên đưa ra quy tắc tùy tiện rằng cứ thấy dấu câu là phải loại bỏ. Điều bắt buộc là escape các octet có ý nghĩa đặc biệt theo RFC 4515, và bảo đảm dữ liệu nằm đúng **vị trí giá trị**, không bị dùng để xây toán tử, attribute name hay cấu trúc filter.

### Unicode và encoding octet

Chuỗi filter LDAP hiện đại dùng UTF-8. Ví dụ giá trị `Hà` có thể được truyền trực tiếp qua giao thức với encoding UTF-8 phù hợp. Khi sử dụng dạng hex escaped cho một ký tự Unicode, cần escape **từng octet UTF-8**, không lấy mã Unicode code point rồi đặt sau một dấu `\`.

Ví dụ chữ `é` có mã UTF-8 là hai octet `C3 A9`:

~~~text
Dữ liệu:          é
UTF-8 bytes:      C3 A9
Dạng escape:      \c3\a9
Không tương đương: \e9  (chỉ một byte, không phải UTF-8 hợp lệ của é)
~~~

Không nên tự mã hóa các ký tự Unicode theo kiểu `\u00e9` rồi cho rằng đó là escape filter LDAP: `\uXXXX` là cú pháp của một số ngôn ngữ lập trình, **không phải** escape octet của RFC 4515. Dùng builder/thư viện LDAP uy tín giúp tránh việc phải tự quản lý UTF-8 và escaping.

Việc chữ hoa/chữ thường hay dấu tiếng Việt có được coi tương đương khi tìm kiếm hay không do **matching rule của attribute type trên server** quyết định; escaping tự nó không thực hiện chuẩn hóa hay so khớp không phân biệt dấu.

## 3. Toán tử filter phải do ứng dụng quyết định

Một LDAP filter có cấu trúc khác nhau tùy mục tiêu:

| Filter | Ý nghĩa |
| --- | --- |
| `(uid=an)` | UID bằng `an` |
| `(uid=*)` | Có thuộc tính UID |
| `(cn=Nguyen*)` | CN bắt đầu bằng `Nguyen` |
| `(cn=*An*)` | CN chứa chuỗi `An`, nếu server hỗ trợ substring matching |
| `(&(objectClass=inetOrgPerson)(uid=an))` | Cả hai điều kiện phải khớp |
| `(|(uid=an)(uid=binh))` | Một trong hai UID khớp |
| `(!(uid=an))` | Phủ định phép so sánh UID bằng `an` |

Các ký hiệu `&`, `|`, `!` và dấu ngoặc ở trên là **cú pháp mà ứng dụng tạo ra**. Người dùng chỉ nên cung cấp giá trị để so sánh, chẳng hạn `an` hoặc `binh`.

Đặc biệt, không nên nhầm lẫn:

- **Equality:** `(uid=\2a)` so sánh với giá trị thật `*`.
- **Presence:** `(uid=*)` chỉ yêu cầu attribute tồn tại.
- **Substring:** `(cn=*An*)` tìm tên chứa `An`; hai dấu sao là wildcard **cố ý**.
- **Literal asterisk trong substring:** nếu tên cần tìm chứa dấu sao thật, phần dấu sao thuộc dữ liệu phải là `\2a`, còn wildcard do ứng dụng thêm vẫn giữ `*`.

Nếu sản phẩm có chế độ “tìm gần đúng” cho tên, hãy xây một cấu trúc substring rõ ràng, trong đó các đoạn giá trị người dùng được escape và các wildcard được tạo ra bởi logic ứng dụng. Không dùng phép so sánh chính xác rồi cho phép người dùng tự nhập `*` để mở rộng phạm vi.

## 4. Cách ưu tiên trong Spring LDAP: `LdapQueryBuilder`

Spring LDAP hỗ trợ `LdapQueryBuilder` để lập trình viên khai báo điều kiện truy vấn bằng API, thay vì nối các mảnh chuỗi cú pháp. Khi dùng phương thức so sánh `.is(...)`, **giá trị được xử lý bởi filter builder** để nó không trở thành cú pháp LDAP.

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

record DirectoryUser(String uid, String name, String email) {}

@Service
public class DirectorySearchService {
    private final LdapTemplate ldapTemplate;

    public DirectorySearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryUser> findByExactUid(String inputUid) {
        if (inputUid == null || inputUid.isBlank() || inputUid.length() > 128) {
            throw new IllegalArgumentException("Invalid uid");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(inputUid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<DirectoryUser>) attrs ->
                        new DirectoryUser(
                                (String) attrs.get("uid").get(),
                                (String) attrs.get("cn").get(),
                                attrs.get("mail") == null
                                        ? null
                                        : (String) attrs.get("mail").get()));
    }
}
~~~

Trong ví dụ, giả sử `ContextSource` đã cấu hình base DN `dc=example,dc=org`. Do đó base `ou=people` trong query là tương đối với base của `ContextSource`. Tài khoản bind được cấp quyền chỉ đọc để truy vấn vùng này.

Các điểm quan trọng:

1. `"objectClass"`, `"uid"` và `"ou=people"` là **cấu trúc/trường được lập trình viên xác định**; chỉ `inputUid` đến từ người dùng.
2. `.is(inputUid)` tạo một điều kiện equality đối với **giá trị nguyên vẹn**, không biến dấu `*` do người dùng nhập thành wildcard.
3. `AttributesMapper` chuyển entry tìm thấy thành DTO; `mail` được xử lý như thuộc tính có thể vắng mặt.
4. Kiểm tra `null`, rỗng và độ dài là **validation nghiệp vụ/giới hạn tài nguyên**, không thay thế escaping.
5. Nếu UID hợp lệ theo nghiệp vụ có thể chứa khoảng trắng ở đầu/cuối, đừng tự động `trim()` trước khi so sánh: thao tác đó có thể làm đổi giá trị cần tìm.

Giá trị `uid` trong thư mục có thể không duy nhất trên mọi OU nếu không có quy tắc hoặc ràng buộc phù hợp. Phương thức trên trả về **danh sách**; tầng nghiệp vụ phải xử lý trường hợp không có, có một hoặc nhiều kết quả.

Ví dụ dùng `LdapTemplate` nhưng ranh giới tin cậy tương tự áp dụng khi truy vấn bằng `LdapClient`: chọn API xây filter có escaping thích hợp với phiên bản Spring LDAP đang sử dụng. ODM không tự làm cho chuỗi filter được ghép thủ công trở nên an toàn.

### Không cần escape đầu vào thêm một lần trước builder

Nếu ứng dụng đã dùng `.is(inputUid)`, **không tự chuyển** `*` thành chuỗi `\2a` trước khi truyền vào. Builder có thể tiếp tục escape dấu `\` vừa thêm, dẫn tới truy vấn tìm **chuỗi ký tự gồm dấu gạch chéo và chữ số**, thay vì tìm dấu sao. Đây là lỗi *double escaping*.

Quy tắc thiết kế là mỗi giá trị được escape **một lần, tại đúng ranh giới chuyển từ dữ liệu sang cú pháp filter**, bởi cơ chế xây filter cuối cùng. Nếu cần hỗ trợ nhiều API khác nhau, thống nhất nơi chịu trách nhiệm escaping và kiểm thử hành vi của từng API.

## 5. Cách khác: các lớp `Filter` có cấu trúc

Spring LDAP còn cung cấp các lớp xây filter như `EqualsFilter` và `AndFilter`. Khi muốn tái sử dụng một đoạn filter hoặc viết một lớp tạo điều kiện độc lập với query, có thể dùng chúng:

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

public class SafeFilterFactory {
    public String exactUidFilter(String userSuppliedUid) {
        if (userSuppliedUid == null) {
            throw new IllegalArgumentException("uid is required");
        }

        AndFilter filter = new AndFilter();
        filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        filter.and(new EqualsFilter("uid", userSuppliedUid));
        return filter.encode();
    }
}
~~~

Nếu `userSuppliedUid` là `*`, ý nghĩa mong muốn của điều kiện thứ hai là `(uid=\2a)`. Dấu sao do người dùng cung cấp được hiểu là **ký tự literal**, không phải phép presence. Dạng hex có thể khác chữ hoa/chữ thường mà vẫn tương đương về nghĩa.

Ưu điểm của cách này là cấu trúc AND và equality tách khỏi input. Khi dùng `LdapTemplate.search(...)` với một filter đã encode, cần đảm bảo toàn bộ điều kiện đều được tạo từ các filter builder hoặc các thành phần cố định đáng tin cậy. Không nên nối tiếp `input` thô vào chuỗi `filter.encode()` đã có.

Trong các API đời cũ hoặc callback JNDI, nếu buộc phải tạo filter từ chuỗi, hãy dùng encoder **dành riêng cho LDAP filter assertion value** của thư viện đang dùng và giới hạn vị trí chèn đã định sẵn. Việc tự viết một danh sách `String.replace(...)` không cần thiết khi có builder phù hợp.

## 6. Filter escaping và DN escaping là hai việc khác nhau

LDAP có **hai cú pháp riêng** thường gặp:

- **DN / RDN** (theo RFC 4514): xác định tên và vị trí entry. Dấu phẩy, dấu cộng, dấu bằng, dấu gạch chéo ngược và một số trường hợp dấu cách hoặc `#` có quy tắc escape riêng.
- **Filter** (theo RFC 4515): mô tả điều kiện truy vấn. Dấu sao, dấu ngoặc, dấu gạch chéo ngược và NUL là các ký tự cần xử lý trong assertion value.

Ví dụ một nhóm có tên `Ops, East`:

~~~text
DN minh họa:
cn=Ops\, East,ou=groups,dc=example,dc=org

Filter so sánh cn:
(cn=Ops, East)
~~~

Dấu phẩy phải được escape khi nó là **nội dung của một RDN**, nhưng trong giá trị của equality filter thông thường nó không cần escape. Áp dụng nhầm quy tắc DN sang filter có thể làm truy vấn sai, và ngược lại.

Với Spring LDAP, có thể dựng DN bằng API chuyên trách:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String groupName = "Ops, East"; // Giá trị có thể đến từ client.
Name relativeDn = LdapNameBuilder.newInstance("ou=groups")
        .add("cn", groupName)
        .build();

// Tên đã được mã hóa theo quy tắc DN:
// cn=Ops\, East,ou=groups
~~~

Nếu muốn tìm một entry theo `cn`, lại dùng `LdapQueryBuilder.where("cn").is(groupName)`. Nếu muốn lọc theo thuộc tính `member` chứa một DN, trước hết cần xây DN hợp lệ, sau đó truyền **biểu diễn DN như giá trị assertion** cho filter builder để escape theo quy tắc filter.

Cần phân biệt thêm **URL encoding** (ví dụ `%2A` trong URL), **HTML escaping**, **JSON escaping** và **Java string escaping**. Không có cơ chế nào trong số đó thay thế tự động cho escaping LDAP filter. Trong Java source, để tạo literal gồm dấu gạch chéo ngược, phải viết `"\\2a"`; còn chuỗi filter chạy thực tế chứa `\2a`. Đây là vấn đề cú pháp của **ngôn ngữ Java**, khác với RFC 4515.

## 7. Các trường hợp dễ sai dù đã biết escaping

### 7.1. Cho người dùng chọn attribute name

Đầu vào không chỉ có thể nằm ở phần giá trị. Một màn hình “tìm theo trường” có thể nhận cả tên trường:

~~~java
// Nguy hiểm nếu searchField không được kiểm soát.
String filter = "(" + searchField + "=" + searchValue + ")";
~~~

Escape `searchValue` là chưa đủ nếu `searchField` vẫn có thể là cú pháp tùy ý. **Tên thuộc tính và toán tử phải lấy từ danh sách cho phép** của ứng dụng.

Ví dụ giới hạn tìm theo UID, CN hoặc email:

~~~java
import java.util.Map;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class UserFilters {
    private static final Map<String, String> ALLOWED_FIELDS = Map.of(
            "username", "uid",
            "name", "cn",
            "email", "mail");

    public LdapQuery exactMatch(String fieldKey, String userValue) {
        String attribute = ALLOWED_FIELDS.get(fieldKey);
        if (attribute == null || userValue == null) {
            throw new IllegalArgumentException("Unsupported search");
        }

        return LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and(attribute).is(userValue);
    }
}
~~~

Như vậy người dùng chỉ chọn một **khóa nghiệp vụ** được hỗ trợ, còn ứng dụng ánh xạ sang LDAP attribute đáng tin cậy.

### 7.2. Cho người dùng nhập cả biểu thức filter

API nhận chuỗi như `"(|(uid=*)(mail=*))"` rồi gắn trực tiếp vào truy vấn đang trao quá nhiều quyền cho client. Nếu thật sự cung cấp giao diện “nâng cao” cho quản trị viên, nên thiết kế cấu trúc tìm kiếm có kiểm soát gồm field, operator và value, sau đó biên dịch qua builder theo danh sách phép toán được phép. Tránh coi một chuỗi filter thô là dữ liệu tìm kiếm thông thường.

### 7.3. Dùng wildcards để “tìm gần đúng”

Một endpoint cho phép người dùng tìm tên chứa chuỗi `an` không nên đơn giản nối `"*" + term + "*"` rồi chèn vào filter text. Nếu `term` chứa `)` hoặc `*`, cấu trúc hoặc phạm vi tìm kiếm có thể thay đổi.

Cách đúng là chọn một API tạo **substring filter** phù hợp với phiên bản Spring LDAP, trong đó phần dữ liệu `term` được escape còn các dấu sao do ứng dụng chủ đích tạo ra mới là wildcard. Cần kiểm thử ít nhất hai trường hợp: người dùng nhập `An` thì tìm substring; người dùng nhập `*` thì xử lý theo chính sách nghiệp vụ thay vì mặc nhiên trở thành “trả về tất cả”. Có thể từ chối chuỗi tìm quá ngắn hoặc giới hạn kết quả để bảo vệ tài nguyên.

### 7.4. Base DN và search scope quá rộng

Escaping **không giới hạn phạm vi truy vấn**. Một filter được escape đúng nhưng chạy từ `dc=example,dc=org` với `SUBTREE_SCOPE` có thể quét nhiều OU và trả về dữ liệu ngoài nhu cầu. Hãy chọn search base, scope, size/time limit và tài khoản bind có quyền tối thiểu theo use case. Đặc biệt với hệ thống lớn, filter thiếu chọn lọc có thể gây tải cao dù không có injection.

### 7.5. Đánh đồng kiểm tra password với search filter

Không nên xác thực mật khẩu bằng cách truy vấn `(userPassword=...)`. LDAP thường xác thực người dùng qua **bind** hoặc cơ chế tích hợp an toàn của server; sử dụng `LdapTemplate.authenticate(...)` hay Spring Security tùy thiết kế. Mật khẩu không phải phần của filter tìm kiếm, không được log, và kết nối cần LDAPS/StartTLS với kiểm tra chứng chỉ phù hợp.

## 8. Kiểm thử escaping theo các tình huống có ý nghĩa

Để kiểm tra một API tìm UID **chính xác**, hãy chuẩn bị vài entry thử nghiệm trong OU được phép đọc và gửi các giá trị sau. Cột biểu diễn filter giả định dùng attribute `uid` và phép equality:

| Giá trị đầu vào | Phần filter sau khi escape | Điều cần kiểm tra |
| --- | --- | --- |
| `an` | `(uid=an)` | Tìm đúng UID `an` |
| `*` | `(uid=\2a)` | Không biến thành `(uid=*)` |
| `a*b` | `(uid=a\2ab)` | Dấu sao nằm giữa là literal |
| `an(test)` | `(uid=an\28test\29)` | Dấu ngoặc không mở/đóng biểu thức |
| `team\ops` | `(uid=team\5cops)` | Dấu gạch chéo ngược được xử lý |
| `abc` theo sau NUL | `(uid=abc\00)` | Không để NUL trực tiếp trong filter |
| `café` | Có thể giữ UTF-8 hoặc escape từng byte thích hợp | Truy vấn không làm hỏng Unicode |

Các kết quả cụ thể phụ thuộc dữ liệu thử nghiệm và schema. Một giá trị có NUL hoặc dấu câu đặc biệt có thể **được filter escape đúng** nhưng vẫn bị server từ chối theo syntax của chính thuộc tính `uid`. Hai khái niệm cần kiểm tra riêng: *filter có cú pháp an toàn* và *giá trị có hợp lệ để so sánh trên attribute đó hay không*.

### Ví dụ kiểm thử đơn vị với `EqualsFilter`

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class LdapFilterEscapingTest {

    @Test
    void literalAsteriskDoesNotBecomePresenceFilter() {
        String encoded = new EqualsFilter("uid", "*")
                .encode().toLowerCase(Locale.ROOT);
        assertEquals("(uid=\\2a)", encoded);
    }

    @Test
    void parenthesesStayInsideAssertionValue() {
        String encoded = new EqualsFilter("uid", "an(test)")
                .encode().toLowerCase(Locale.ROOT);
        assertEquals("(uid=an\\28test\\29)", encoded);
    }

    @Test
    void backslashIsEscaped() {
        String encoded = new EqualsFilter("uid", "team\\ops")
                .encode().toLowerCase(Locale.ROOT);
        assertEquals("(uid=team\\5cops)", encoded);
    }
}
~~~

Ví dụ dùng JUnit 5 và giả định phiên bản Spring LDAP có API `EqualsFilter.encode()`. Việc chuyển sang chữ thường trong test chỉ giúp biểu diễn hexadecimal nhất quán. Khi kiểm thử tích hợp, cần thử cả filter trên LDAP test server, xác nhận kết quả chỉ khớp entry được kỳ vọng và không bị mở rộng do wildcard. Đừng kiểm thử payload nguy hiểm trên thư mục sản xuất.

**Lưu ý:** test so sánh chuỗi biểu diễn chỉ kiểm tra một phần hành vi. Test tích hợp còn cần xác minh base DN, ACL, matching rule, filter syntax của server và cách ứng dụng xử lý 0/nhiều kết quả. Không giả định một server có cùng schema hoặc quy tắc so sánh với server khác.

## 9. Quy trình áp dụng trong ứng dụng thực tế

Với một endpoint tìm nhân viên theo UID, có thể dùng quy trình:

1. **Xác định nghiệp vụ:** cần exact equality hay substring; trường tìm kiếm nào được hỗ trợ; giới hạn số lượng kết quả.
2. **Giữ cấu trúc filter trong code:** operator, tên attribute và các nhánh `AND/OR/NOT` do ứng dụng xác định hoặc chọn từ allowlist.
3. **Truyền input ở vị trí giá trị:** dùng `LdapQueryBuilder`/`EqualsFilter` để thư viện escape assertion value; không nối input thô vào chuỗi filter.
4. **Giới hạn phạm vi và quyền:** query trong OU phù hợp, chọn search scope và tài khoản chỉ có quyền cần thiết; áp dụng time/size limit khi thích hợp.
5. **Mapping kết quả cẩn thận:** xử lý `MAY` attribute có thể thiếu, dữ liệu nhiều giá trị và trường hợp có nhiều entry.
6. **Kiểm thử giá trị đặc biệt:** `*`, `(`, `)`, `\`, NUL, Unicode và chuỗi dài; kiểm tra behavior với từng API/phiên bản.
7. **Giám sát và xử lý lỗi:** phân biệt lỗi filter syntax, naming, schema, ACL, kết nối TLS, timeout; không ghi log dữ liệu nhạy cảm hoặc filter có chứa mật khẩu.

Escaping chỉ giải quyết việc **bảo toàn nghĩa của giá trị trong cú pháp filter**. Nó cần đi kèm validation, phân quyền, giới hạn truy vấn và xử lý dữ liệu kết quả để hệ thống truy cập LDAP an toàn.

## 10. Bài thực hành: tìm lỗi và sửa filter

### Tình huống

Một API nhận tham số `q` và `field` để tìm nhân viên. Code cũ:

~~~java
String filter = "(&(objectClass=inetOrgPerson)("
        + field + "=" + q + "))";
List<String> entries = ldapTemplate.search(
        "ou=people",
        filter,
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get());
~~~

### Yêu cầu

1. Chỉ ra **hai vị trí đầu vào không đáng tin cậy** làm thay đổi cấu trúc filter.
2. Giải thích vì sao `q="*"` là trường hợp đặc biệt nếu yêu cầu là so sánh exact.
3. Viết lại bằng `LdapQueryBuilder`: `field` chỉ cho phép các khóa `username`, `name`; giá trị thực tế tương ứng là `uid`, `cn`.
4. Kiểm thử `q="an(test)"` và `q="*"` để bảo đảm dấu ngoặc/dấu sao không còn ý nghĩa toán tử.
5. Nêu hai biện pháp bổ sung **ngoài escaping** để giới hạn việc truy cập thư mục.

### Đáp án tham khảo

Hai vị trí nguy hiểm là `field` (attribute name) và `q` (assertion value). Giá trị `*` chưa được escape có thể chuyển `(uid=*)` thành phép kiểm tra presence.

Một phiên bản sửa lại:

~~~java
import java.util.Map;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

Map<String, String> allowlist = Map.of(
        "username", "uid",
        "name", "cn");

String attribute = allowlist.get(field);
if (attribute == null || q == null || q.isBlank() || q.length() > 128) {
    throw new IllegalArgumentException("Invalid search criteria");
}

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and(attribute).is(q);

// ldapTemplate.search(query, attributesMapper);
~~~

Trong phiên bản này, `q="an(test)"` được hiểu là một giá trị chứa dấu ngoặc thật; `q="*"` được hiểu là dấu sao thật. Tên trường và cấu trúc filter không bị lấy trực tiếp từ input. Hai biện pháp bổ sung có thể là: giới hạn base/scope theo OU được phép và dùng tài khoản bind chỉ đọc với ACL tối thiểu; ngoài ra có thể thêm giới hạn độ dài input, kích thước kết quả, thời gian truy vấn và logging an toàn.

### Câu hỏi ôn tập ngắn

| Câu hỏi | Đáp án |
| --- | --- |
| Có thể thay `\2a` bằng `%2A` trong assertion value không? | Không: đó là URL encoding, không phải escape RFC 4515 |
| Có nên tự escape giá trị trước khi gọi `.is(...)` không? | Không, tránh double escaping; để builder chịu trách nhiệm |
| `(uid=*)` có phải tìm literal `*` không? | Không, đó là presence filter |
| DN escape và filter escape có cùng quy tắc không? | Không; chúng thuộc hai cú pháp khác nhau |
| Input Unicode có luôn cần đổi thành hex escape không? | Không; có thể truyền UTF-8 hợp lệ, hoặc escape từng octet khi cần |
| Escape filter có ngăn được truy vấn subtree quá rộng không? | Không; cần giới hạn base/scope, ACL và tài nguyên riêng |

## 11. Ghi nhớ

- LDAP filter dùng cú pháp RFC 4515. Trong **assertion value**, escape `*`, `(`, `)`, `\`, NUL bằng `\2a`, `\28`, `\29`, `\5c`, `\00` tương ứng.
- **Giữ cấu trúc filter trong code; coi input người dùng là giá trị.** Với Spring LDAP, ưu tiên `LdapQueryBuilder.where(...).is(value)` hoặc các filter builder thích hợp.
- Phân biệt exact, presence và substring. Dấu sao do người dùng gửi phải là dữ liệu nếu nghiệp vụ yêu cầu exact; wildcard chỉ được tạo ra khi ứng dụng chủ đích cho phép.
- **Filter escaping, DN escaping và URL encoding khác nhau.** Áp dụng đúng cơ chế tại đúng nơi, tránh double escaping.
- Escaping đi cùng giới hạn phạm vi tìm kiếm, ACL tối thiểu, kết nối LDAP bảo mật, xử lý lỗi và kiểm thử các ký tự đặc biệt. Không dùng search filter chứa password để thay cho cơ chế LDAP bind xác thực.

### Tài liệu tham khảo

- [RFC 4515 – Lightweight Directory Access Protocol (LDAP): String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4514 – LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
