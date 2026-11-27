# Case, khoảng trắng và quy tắc so sánh DN

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **chuỗi DN hiển thị**, **DN đã được phân tích thành RDN** và **quy tắc LDAP server dùng để xác định hai DN bằng nhau**.
- Giải thích ảnh hưởng của chữ hoa/thường (*case*), khoảng trắng, ký tự escape, alias của attribute type và thứ tự RDN.
- Sử dụng `javax.naming.ldap.LdapName`, `Rdn` và `LdapNameBuilder` trong Spring LDAP để tạo và xử lý DN an toàn.
- Tránh lỗi so sánh DN bằng `String.equals`, `equalsIgnoreCase` hoặc `trim` trong truy vấn, cache, phân quyền và thao tác LDAP.

Bài thuộc chương **DN và Name** của **SPRING_LDAP**. Trong thực hành Spring LDAP, từ cấu hình `ContextSource`, `LdapTemplate`, `LdapClient`, ODM cho đến xác thực bind, bạn liên tục phải xử lý Distinguished Name (DN). Một DN sai ở một dấu cách hoặc bị diễn giải theo quy tắc so sánh không phù hợp có thể dẫn đến tìm kiếm sai entry, không bind được, hoặc xác định sai thành viên nhóm.

## 1. DN là tên có cấu trúc, không đơn thuần là chuỗi

Xét DN:

~~~text
uid=lan,ou=People,dc=example,dc=org
~~~

Chuỗi này gồm các **Relative Distinguished Name (RDN)**, phân cách bằng dấu phẩy. Mỗi RDN chứa một hoặc nhiều cặp **attribute type/value** (Attribute Value Assertion, AVA):

~~~text
uid=lan        <- RDN của entry
ou=People      <- RDN của đơn vị tổ chức
dc=example     <- RDN miền
dc=org         <- RDN miền gốc
~~~

DN biểu thị đường đi từ entry đến nhánh gốc, viết từ **RDN cụ thể nhất ở bên trái** đến **RDN gốc hơn ở bên phải**. Thứ tự RDN trong DN có ý nghĩa. Đổi vị trí `uid=lan` và `ou=People` sẽ mô tả một cấu trúc tên khác.

Một RDN có thể chứa nhiều AVA, ví dụ:

~~~text
cn=Lan Nguyen+uid=lan,ou=People,dc=example,dc=org
~~~

Trong *cùng một RDN đa giá trị*, thứ tự giữa các AVA phân cách bằng dấu `+` **không mang ý nghĩa** theo quy tắc `distinguishedNameMatch`, nếu các AVA tương ứng thực sự bằng nhau.

Khi tìm cách trả lời “hai DN có giống nhau không?”, phải làm rõ bạn đang so sánh:

1. **Hai chuỗi ký tự** (ví dụ `String.equals`): từng ký tự có giống nhau không?
2. **Hai tên được parser Java hiểu** (ví dụ `LdapName.equals`): các RDN và giá trị sau xử lý cú pháp có tương đương theo quy tắc của JNDI không?
3. **Hai DN theo server LDAP**: chúng có bằng nhau theo *schema* và matching rule của các attribute type không?

Ba kết quả **có thể khác nhau**.

## 2. Case: chữ hoa/thường ảnh hưởng đến những phần nào?

### 2.1. Tên attribute type không phân biệt hoa/thường

Các attribute type descriptor như `cn`, `ou`, `dc`, `uid` không phân biệt chữ hoa/thường ở tên type:

~~~text
cn=Lan,ou=People,dc=example,dc=org
CN=Lan,OU=People,DC=example,DC=org
~~~

Các descriptor tương ứng chỉ khác *cách viết type*. LDAP schema còn có thể khai báo **OID và tên mô tả** cho cùng một type, ví dụ `cn` là tên quen thuộc của attribute type có OID `2.5.4.3`. Máy chủ có schema biết sự tương ứng này; **parser Java thuần không nhất thiết tự tra được alias/OID theo schema của server**.

Không nên kết luận rằng hai DN khác tên type theo dạng OID/descriptors chắc chắn không trỏ đến cùng entry chỉ vì hai chuỗi khác nhau.

### 2.2. Case của **giá trị** do matching rule quyết định

Điểm khác quan trọng nằm ở bên phải dấu `=`.

Ví dụ hai DN:

~~~text
cn=Lan Nguyen,ou=People,dc=example,dc=org
cn=lan nguyen,ou=people,dc=example,dc=org
~~~

Trong một schema thông dụng, `cn` và `ou` dùng **caseIgnoreMatch** nên việc thay đổi hoa/thường như ví dụ thường **không đổi kết quả so sánh giá trị**. Tuy nhiên, không có quy tắc “mọi DN đều không phân biệt hoa/thường”. Với attribute type dùng **caseExactMatch** hoặc một matching rule khác, case của giá trị có thể là phần của danh tính.

| Thành phần | Quy tắc cần nhớ | Ví dụ |
| --- | --- | --- |
| Tên type (`CN`, `cn`) | Không phân biệt hoa/thường trong cách gọi descriptor | `CN=Lan` và `cn=Lan` |
| Giá trị của type có `caseIgnoreMatch` | Không phân biệt hoa/thường theo rule, có thể có xử lý Unicode/space riêng | `cn=Lan` so với `cn=lan` |
| Giá trị của type có `caseExactMatch` | Phân biệt hoa/thường theo rule | `customCode=AbC` so với `customCode=abc` có thể khác |
| Giá trị có matching rule khác hoặc không có equality rule phù hợp | Không tự suy diễn từ tên hay kiểu dữ liệu | Cần xem schema của server |

Chỉ tra cứu, đọc DN từ log hoặc thấy tên `cn` không đủ để khẳng định mọi giá trị đều so sánh theo `caseIgnoreMatch`. Điều quyết định là *định nghĩa attribute type và các matching rule mà server áp dụng*.

### 2.3. Case của DN string không phải case của mật khẩu

Trong Spring LDAP, bạn có thể dùng DN để xác định entry cần tìm, sau đó dùng DN này để **bind** khi xác thực. Câu hỏi “DN nào xác định người dùng?” tách biệt với câu hỏi “mật khẩu có đúng không?”. Dù server coi hai cách viết DN là tương đương, điều đó **không** có nghĩa mật khẩu trở thành không phân biệt hoa/thường. Kiểm tra mật khẩu phải do cơ chế xác thực của LDAP server thực hiện.

## 3. Khoảng trắng: đứng ở đâu mới quan trọng?

Khoảng trắng trong DN khó xử lý vì có hai khái niệm khác nhau:

- **Khoảng trắng quanh ký hiệu cú pháp** khi parser đọc một dạng chuỗi DN: có parser chấp nhận và bỏ qua khoảng trắng quanh dấu `,`, `=` và `+`.
- **Khoảng trắng thực sự thuộc giá trị** của một AVA: có thể phải escape trong chuỗi DN và việc so sánh chịu matching rule của attribute type.

### 3.1. Khoảng trắng trước hoặc sau dấu phân cách

JNDI `LdapName` của Java chấp nhận khoảng trắng ASCII quanh một số dấu ngăn cách rồi bỏ qua chúng khi so sánh tên đã parse, chẳng hạn dạng:

~~~text
cn=Lan,ou=People,dc=example,dc=org
cn = Lan , ou = People , dc = example , dc = org
~~~

Đây là **hành vi parser được Java hỗ trợ**; không nên dùng cách chèn khoảng trắng tùy ý này làm định dạng chuẩn khi trao đổi DN với những công cụ khác. RFC 4514 mô tả cú pháp chuỗi DN và **không định nghĩa một cách viết canonical duy nhất**.

Đặc biệt, không được áp dụng `replaceAll("\\s+", " ")` hoặc xóa mọi khoảng trắng trên *toàn bộ DN*. Những phép biến đổi kiểu chuỗi không biết ranh giới giữa ký tự cú pháp và giá trị.

### 3.2. Khoảng trắng là ký tự đầu/cuối trong một giá trị

Nếu tên thực tế là `" Lan "` (một dấu cách ở đầu và một dấu cách ở cuối), dạng DN theo RFC 4514 phải **escape** các dấu cách ở đầu và cuối:

~~~text
cn=\ Lan\ ,ou=People,dc=example,dc=org
~~~

Có thể dùng mã hex `\20` biểu diễn dấu cách ASCII, ví dụ:

~~~text
cn=\20Lan\20,ou=People,dc=example,dc=org
~~~

Hai ví dụ trên biểu diễn cùng dãy ký tự của giá trị `cn` sau khi giải mã escape. Ngược lại, `cn=Lan` biểu diễn dãy ký tự **không chứa** khoảng trắng đầu/cuối. Hai giá trị này có bằng nhau theo LDAP hay không vẫn do matching rule của `cn` quyết định.

**Đừng dùng `trim()` để “sửa DN”**. Nó có thể làm mất dữ liệu nếu áp dụng lên giá trị và không hiểu cách escape. Ví dụ `" Lan "` có thể là giá trị được lưu cố ý; khi loại bỏ khoảng trắng, bạn đang tạo giá trị khác trước khi server có cơ hội áp dụng quy tắc so sánh của nó.

### 3.3. Khoảng trắng liên tiếp ở giữa giá trị

Ví dụ:

~~~text
cn=Lan  Nguyen,ou=People,dc=example,dc=org
cn=Lan Nguyen,ou=People,dc=example,dc=org
~~~

Không được mặc định rằng hai DN **luôn bằng nhau** hoặc **luôn khác nhau**. Các matching rule dành cho chuỗi, chẳng hạn `caseIgnoreMatch` theo mô hình LDAP chuẩn, có bước chuẩn bị và xử lý khoảng trắng; các rule khác có thể giữ phân biệt. Phải xem schema của thuộc tính đó và cách server triển khai.

Unicode cũng cần thận trọng: dấu cách ASCII (`U+0020`), non-breaking space (`U+00A0`), dấu tab và các ký tự nhìn giống nhau không nhất thiết được xử lý y hệt nhau trong mọi rule. Các quy tắc chuẩn bị chuỗi có thể liên quan đến RFC 4518, nhưng **không** nên tự viết một hàm “normalize tất cả Unicode” rồi coi kết quả là DN chuẩn cho mọi directory.

### 3.4. Bảng phân biệt nhanh

| Dạng DN (rút gọn) | Điều thực sự thay đổi | Có thể kết luận ngay? |
| --- | --- | --- |
| `cn=Lan` và `CN=Lan` | Case của **tên attribute** | Tương đương về cách gọi type |
| `cn=Lan` và `cn=lan` | Case của **giá trị** | Cần biết equality matching rule |
| `cn=\ Lan\ ` và `cn=\20Lan\20` | Cách escape cùng hai khoảng trắng | Giá trị đã giải mã là như nhau |
| `cn=\ Lan\ ` và `cn=Lan` | Giá trị có/không có khoảng trắng đầu và cuối | Cần biết equality matching rule |
| `cn=Lan  Nguyen` và `cn=Lan Nguyen` | Số khoảng trắng giữa hai từ | Cần biết equality matching rule |
| `cn=Lan,ou=People` và `ou=People,cn=Lan` | Thứ tự **hai RDN** | Là hai DN có cấu trúc khác nhau |
| `cn=Lan+uid=l1` và `uid=l1+cn=Lan` | Thứ tự AVA **trong cùng một RDN** | Thứ tự AVA không có ý nghĩa theo DN matching |

## 4. Escape: cùng giá trị, nhiều cách viết

RFC 4514 quy định ký tự đặc biệt trong giá trị phải được escape khi viết DN dưới dạng chuỗi. Những ký tự đáng chú ý gồm:

- Dấu phẩy `,`, dấu cộng `+`, dấu ngoặc kép `"`, dấu chấm phẩy `;`, dấu ngoặc nhọn `<`/`>` và dấu gạch chéo ngược `\`.
- Dấu `#` **nếu nằm ở đầu** giá trị.
- Dấu cách **ở đầu hoặc cuối** giá trị.
- Ký tự NULL và các ký tự khác phải/được biểu diễn bằng cú pháp hex escape thích hợp.

Ví dụ giá trị `cn` là `"Nguyen, Lan"`:

~~~text
cn=Nguyen\, Lan,ou=People,dc=example,dc=org
cn=Nguyen\2C Lan,ou=People,dc=example,dc=org
~~~

Cả `\,` và `\2C` biểu diễn dấu phẩy thuộc **giá trị**, không phải dấu phẩy phân tách hai RDN. Hai cách viết có thể parse thành cùng một giá trị AVA.

Ví dụ giá trị bắt đầu bằng `#`:

~~~text
cn=\#001,ou=People,dc=example,dc=org
~~~

Dấu `#` đứng đầu không được escape trong cú pháp RFC 4514 có thể mang ý nghĩa bắt đầu một giá trị dạng mã hex, nên việc bỏ escape có thể khiến parser diễn giải khác hoặc báo lỗi.

Ví dụ giá trị có dấu gạch chéo ngược là `"A\B"`:

~~~text
cn=A\\B,ou=People,dc=example,dc=org
~~~

**Không tách DN bằng `split(",")`.** Với `cn=Nguyen\, Lan,ou=People,...`, phép tách chuỗi đơn giản sẽ cắt hỏng giá trị `cn`. Tương tự, `split("+")` không phải cách tin cậy để đọc RDN đa giá trị.

## 5. Quy tắc `distinguishedNameMatch` theo RFC 4517

LDAP dùng matching rule **`distinguishedNameMatch`** để so sánh giá trị có DN syntax trong các trường hợp phù hợp. Hai DN bằng nhau theo quy tắc này khi:

1. Chúng có **cùng số lượng RDN**.
2. Các RDN **ở cùng vị trí** tương đương.
3. Mỗi cặp RDN tương ứng có **cùng số lượng AVA**, cùng các attribute type; **thứ tự các AVA trong RDN không quan trọng**.
4. Các giá trị AVA cùng type được so sánh theo **equality matching rule của attribute type** đã được khai báo trong schema.

Vì vậy, quy tắc so sánh DN **không thể rút gọn thành** “lowercase cả chuỗi rồi so sánh”. Matching rule vận dụng thông tin schema tại từng AVA.

~~~mermaid
flowchart TD
    Start["Hai DN A và B"] --> RdnCount{"Cùng số RDN?"}
    RdnCount -->|Không| Diff["Không bằng nhau"]
    RdnCount -->|Có| AtPos{"Từng RDN cùng vị trí<br/>có tập AVA tương ứng?"}
    AtPos -->|Không| Diff
    AtPos -->|Có| Rules{"Giá trị từng AVA bằng nhau<br/>theo equality rule của attribute type?"}
    Rules -->|Có| Equal["Bằng nhau theo distinguishedNameMatch"]
    Rules -->|Không| Diff
    Rules -->|Không xác định| Undef["Kết quả có thể là Undefined"]
~~~

Với quy tắc chuẩn, một phép so sánh AVA có thể cho kết quả **Undefined** nếu không thể áp dụng matching rule phù hợp; điều này khác với việc tự động coi mọi trường hợp không so sánh được là `false`.

### Ví dụ: RDN đa giá trị

~~~text
cn=Lan+uid=l1,ou=People,dc=example,dc=org
uid=l1+cn=Lan,ou=People,dc=example,dc=org
~~~

Hai DN giữ nguyên thứ tự **các RDN**; chỉ hoán đổi thứ tự **hai AVA bên trong RDN đầu tiên**. Theo `distinguishedNameMatch`, thứ tự các AVA không phải yếu tố tạo khác biệt, miễn các type và giá trị được so khớp phù hợp.

Tuy nhiên:

~~~text
cn=Lan,uid=l1,ou=People,dc=example,dc=org
~~~

DN này có thêm một RDN riêng `uid=l1`; nó **khác về cấu trúc** với dạng đa giá trị `cn=Lan+uid=l1,ou=People,...`.

## 6. So sánh trong Java/Spring LDAP: `String` và `Name` khác nhau

### 6.1. Không dùng `String.equals` cho câu hỏi “cùng DN?”

~~~java
String a = "cn=Lan,ou=People,dc=example,dc=org";
String b = "CN=Lan,OU=People,DC=example,DC=org";

System.out.println(a.equals(b)); // false: so sánh ký tự
~~~

`String.equals` hữu ích khi bạn cần xác minh hai chuỗi được lưu **giống tuyệt đối** (ví dụ kiểm tra output của một formatter). Nhưng nó không hiểu DN, RDN, escape hay equality matching rule.

`equalsIgnoreCase` vẫn không đủ: nó không phân tích `\,`/`\2C`, không biết ranh giới RDN và cũng không đọc schema để biết type nào có rule `caseExactMatch`.

### 6.2. Dùng `LdapName` để phân tích cú pháp và so sánh theo JNDI

`javax.naming.ldap.LdapName` là implementation `javax.naming.Name` có khả năng parse DN thành RDN. Ví dụ:

~~~java
import javax.naming.ldap.LdapName;

LdapName a = new LdapName(
    "cn=Nguyen\\, Lan,ou=People,dc=example,dc=org"
);
LdapName b = new LdapName(
    "CN=nguyen\\2C lan,OU=People,DC=example,DC=org"
);

System.out.println(a.equals(b)); // true theo quy tắc JNDI LdapName
~~~

Trong Java string literal, phải viết `\\` để tạo **một** ký tự `\` thật ở chuỗi DN. Bởi vậy cú pháp nguồn Java `"\\2C"` tương ứng với escape LDAP `\2C`.

`LdapName.equals` nhận biết sự tương đương của cách escape và bỏ qua thứ tự AVA trong RDN đa giá trị. Tuy nhiên, theo Javadoc của `LdapName`, cách so sánh của Java coi **attribute type và các giá trị chuỗi/binary không phân biệt hoa/thường**. Đây là quy tắc của **JNDI class**, không phải quá trình hỏi schema của LDAP server.

**Hệ quả cần nhớ:** nếu directory có một attribute type dùng `caseExactMatch`, hai `LdapName` chỉ khác case giá trị có thể bị Java đánh giá bằng nhau trong khi LDAP server đánh giá khác nhau. Ở chiều ngược lại, alias của attribute type (`cn` so với OID `2.5.4.3`) có thể được server hiểu là một type theo schema nhưng parser Java không có thông tin để kết luận như vậy. Vì thế, `LdapName.equals` là phép so sánh cấu trúc hữu ích ở client, **không phải lời cam kết đồng nhất kết quả với `distinguishedNameMatch` trên mọi server/schema**.

### 6.3. Không thao tác dựa trên thứ tự chuỗi hiển thị

Cú pháp DN hiển thị là “lá trước, gốc sau”:

~~~text
cn=Lan,ou=People,dc=example,dc=org
~~~

Trong API `LdapName`, chỉ số thành phần ở `getRdn(0)` bắt đầu từ **RDN ít cụ thể nhất**, nên với DN trên `getRdn(0)` là `dc=org` và `getRdn(size()-1)` là `cn=Lan`.

~~~java
import javax.naming.ldap.LdapName;

LdapName dn = new LdapName(
    "cn=Lan,ou=People,dc=example,dc=org"
);

System.out.println(dn.getRdn(0));                 // dc=org
System.out.println(dn.getRdn(dn.size() - 1));     // cn=Lan
~~~

Khi làm việc với tên và các OU, hãy dùng API RDN thay cho phép xử lý chuỗi. Điều này đặc biệt quan trọng nếu một RDN có dấu phẩy được escape trong giá trị.

## 7. Tạo DN đúng bằng Spring LDAP

### 7.1. `LdapNameBuilder`: escape giá trị từ input

Spring LDAP cung cấp `LdapNameBuilder` để xây dựng DN từ các cặp type/value. Đây là lựa chọn phù hợp khi thông tin như tên người dùng hoặc tên OU đến từ dữ liệu đầu vào:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String displayName = " Nguyen, Lan ";

Name dn = LdapNameBuilder
    .newInstance("dc=example,dc=org")
    .add("ou", "People")
    .add("cn", displayName)
    .build();

System.out.println(dn);
// Ví dụ kết quả: cn=\ Nguyen\, Lan\ ,ou=People,dc=example,dc=org
~~~

Builder nhận **giá trị thô** và xử lý cú pháp escape cho RDN. Đừng tự escape trước rồi truyền cho builder như một giá trị bình thường: dấu `\` có thể bị xem là ký tự dữ liệu và escape thêm lần nữa.

### 7.2. Nếu cần escape một giá trị RDN riêng lẻ

JNDI cung cấp `Rdn.escapeValue`:

~~~java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

String commonName = "Nguyen, Lan";
String escaped = Rdn.escapeValue(commonName);

LdapName dn = new LdapName(
    "cn=" + escaped + ",ou=People,dc=example,dc=org"
);
~~~

Đoạn trên chỉ ghép **type `cn` cố định** với giá trị đã escape; trong ứng dụng nên ưu tiên builder để xử lý toàn bộ cấu trúc DN, đặc biệt khi có nhiều thành phần động.

**Không nhầm escape DN với escape LDAP filter.** DN dùng để chỉ định entry; filter dùng để tìm entry theo thuộc tính, ví dụ `(uid=lan)`. Chúng có cú pháp khác nhau. Để truyền giá trị vào filter khi dùng `LdapTemplate`, hãy dùng `EqualsFilter`/`LdapQueryBuilder` hoặc cơ chế parameter binding thích hợp. Truyền một chuỗi đã escape theo DN vào filter có thể làm truy vấn sai.

### 7.3. Base DN và DN tương đối

Giả sử `ContextSource` được cấu hình base:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
~~~

Khi gọi một số API của `LdapTemplate` hoặc `LdapClient`, DN/search base có thể được dùng **tương đối** với base đã cấu hình. Ví dụ `ou=People` là nhánh nằm trong `dc=example,dc=org`. Nếu truyền lại `ou=People,dc=example,dc=org` vào vị trí yêu cầu tên tương đối, có thể dẫn đến nhân đôi base hoặc truy vấn nhầm đường dẫn, tùy API.

Việc hai tên có **khác nhau ở tiền tố/hậu tố theo cấu hình base** là chuyện về *đường dẫn và ngữ cảnh*, không phải chuyện khác case hay khoảng trắng. Cần thống nhất trong mã liệu bạn đang lưu **full DN** hay **relative DN**.

## 8. Hệ quả trong tìm kiếm, ODM, xác thực và nhóm

### Tìm kiếm và thao tác entry

Khi truy vấn entry theo DN hoặc thực hiện modify/unbind, sử dụng đối tượng `Name` được xây dựng đúng và hiểu phạm vi `ContextSource`. Không tự chuyển DN thành chữ thường, không gộp khoảng trắng và không cắt bằng dấu phẩy.

Server có thể trả DN theo cách hiển thị khác với input; vì RFC 4514 **không chuẩn hóa một chuỗi canonical**, đừng coi khác biệt giữa hai chuỗi in ra là bằng chứng entry đã đổi danh tính.

### ODM và `@Id`

Trong Spring LDAP ODM, DN thường được biểu diễn bằng field `javax.naming.Name` có annotation `@Id`. Khi dùng Spring Data LDAP repository, tên này là thành phần nhận diện entry trong directory. Không xây khóa định danh bằng `dn.toString().toLowerCase()`: thao tác đó có thể gộp nhầm các DN mà server phân biệt hoặc tạo khóa không ổn định.

Nếu cần một định danh bền vững khi entry được rename/move, cân nhắc thuộc tính định danh riêng do directory hỗ trợ, chẳng hạn `entryUUID` ở một số LDAP server hoặc `objectGUID` trong Active Directory, với cách đọc và kiểu dữ liệu phù hợp. DN có thể **thay đổi khi đổi RDN hoặc chuyển OU**.

### Bind và Spring Security LDAP

Khi Spring Security LDAP dùng search để tìm DN của người dùng rồi bind, cần chuyển đúng DN đã được tìm thấy vào luồng xác thực. Sự tồn tại của entry hay một phép `LdapName.equals` ở client không thay thế thao tác bind kiểm tra mật khẩu. Những nơi so sánh DN của người dùng với `member` của group phải tuân theo định nghĩa nhóm và cách server thực thi matching rule, không dùng so sánh chuỗi tùy tiện để cấp quyền nhạy cảm.

### TLS, pooling và lỗi kết nối

DN bị xử lý sai có thể biểu hiện như “không tìm thấy người dùng” hoặc “bind thất bại”, nhưng cũng có thể lỗi thực tế do quyền, chứng chỉ TLS, timeout hoặc kết nối pool dùng sai danh tính. Khi chẩn đoán:

- Ghi log thông tin cấu trúc và loại thao tác cần thiết, nhưng **không log mật khẩu** và hạn chế đưa DN nhạy cảm vào log công khai.
- Phân biệt lỗi parse DN ở phía ứng dụng với `NameNotFoundException`, lỗi quyền, lỗi bind và lỗi kết nối.
- Dùng LDAPS/StartTLS với xác thực chứng chỉ đúng; DN normalization không sửa được lỗi TLS hoặc ACL.

## 9. Tình huống thực hành

**Bối cảnh:** Directory chứa một nhân viên được nhận diện bằng DN có `cn` chứa dấu phẩy:

~~~text
cn=Nguyen\, Lan,ou=People,dc=example,dc=org
~~~

Một API nhận `displayName` từ form và muốn tra cứu/cập nhật entry.

### Cách dễ sai

~~~java
String dn = "cn=" + displayName + ",ou=People,dc=example,dc=org";
// displayName = "Nguyen, Lan" => dấu phẩy bị hiểu là ranh giới RDN
~~~

Hoặc:

~~~java
String normalized = dn.toLowerCase().replaceAll("\\s+", "");
// Làm thay đổi giá trị, phá cấu trúc/escape và bỏ qua matching rule.
~~~

### Cách phù hợp

~~~java
Name personDn = LdapNameBuilder
    .newInstance("ou=People")       // Tương đối với base đã cấu hình
    .add("cn", displayName)          // Giá trị thô, builder escape
    .build();

// Ví dụ: ldapTemplate.lookup(personDn);
// Chỉ dùng nếu cấu hình ContextSource và quyền tra cứu phù hợp.
~~~

Để xác nhận hai tên *đại diện cùng entry trên server*, hãy dùng thao tác truy cập LDAP theo DN hoặc tra cứu một thuộc tính định danh tin cậy theo hệ thống. `LdapName.equals` giúp so sánh tên đã parse trong Java, nhưng không thay thế schema và dữ liệu thật của server.

### Bài tập kiểm tra

Cho các cặp DN sau (giả sử cùng base được sử dụng):

1. `cn=Lan,ou=People` và `CN=Lan,OU=People`.
2. `cn=Lan,ou=People` và `cn=lan,ou=people`.
3. `cn=Nguyen\, Lan,ou=People` và `cn=Nguyen\2C Lan,ou=People`.
4. `cn=\ Lan\ ,ou=People` và `cn=Lan,ou=People`.
5. `cn=Lan+uid=lan,ou=People` và `uid=lan+cn=Lan,ou=People`.
6. `cn=Lan,ou=People` và `ou=People,cn=Lan`.

Hãy đánh dấu câu trả lời theo ba mức: **bằng nhau theo cú pháp/type**, **phụ thuộc matching rule** hoặc **khác cấu trúc DN**. Sau đó giải thích liệu kết quả `String.equals` và `LdapName.equals` có nhất thiết giống kết quả server không.

**Gợi ý:**

- (1) Tên type khác case; đây là cách biểu diễn cùng type.
- (2) Case của giá trị phụ thuộc equality rule; `caseIgnoreMatch` thông dụng sẽ coi tương đương.
- (3) Hai biểu diễn escape của cùng dấu phẩy nên cùng giá trị đã giải mã.
- (4) Giá trị thực có khoảng trắng đầu/cuối khác nhau; so sánh phía server phụ thuộc rule.
- (5) Hoán đổi AVA trong một RDN đa giá trị không làm thay đổi DN theo `distinguishedNameMatch`.
- (6) Đổi thứ tự **RDN**, nên đây là tên có cấu trúc khác.
- `String.equals` so sánh ký tự; `LdapName.equals` phân tích cú pháp nhưng **không dùng schema của server**, vì vậy không thể suy ra kết quả máy chủ cho mọi trường hợp.

## 10. Checklist khi mã hóa DN trong ứng dụng Spring

- [ ] Dùng `LdapNameBuilder` hoặc `LdapName`/`Rdn` thay vì thao tác với DN như chuỗi tự do.
- [ ] Phân biệt full DN và relative DN theo cấu hình `ContextSource`.
- [ ] Escape giá trị theo **cú pháp DN**, và dùng công cụ khác cho **LDAP filter**.
- [ ] Không gọi `trim()`, `toLowerCase()` hoặc gộp khoảng trắng trên toàn bộ DN để xác định danh tính.
- [ ] Hiểu rằng loại attribute và equality matching rule quyết định cách so sánh **giá trị**.
- [ ] Kiểm tra RDN đa giá trị, dấu phẩy được escape và DN chứa khoảng trắng đầu/cuối.
- [ ] Không coi phép so sánh `LdapName.equals` là phép kiểm chứng danh tính duy nhất khi quyết định quyền truy cập.
- [ ] Với kiểm thử tích hợp, đưa cả trường hợp caseExactMatch hoặc schema đặc biệt, nếu directory hỗ trợ.
- [ ] Không dùng DN làm khóa bất biến nếu nghiệp vụ cho phép rename/move entry.

## 11. Tóm tắt

**Case của attribute type**, **case của giá trị**, **khoảng trắng cú pháp**, **khoảng trắng dữ liệu** và **cách escape** là năm chuyện khác nhau. LDAP server so sánh DN theo `distinguishedNameMatch`, dựa vào cấu trúc RDN/AVA và equality matching rule của các attribute type. `LdapName` trong Java cung cấp parser và so sánh tên hữu ích, nhưng nó không có toàn bộ ngữ cảnh schema của server.

Trong Spring LDAP, cách thực hành đáng tin cậy là tạo DN bằng `LdapNameBuilder`, dùng `Name` khi làm việc với `LdapTemplate`/ODM, quản lý rõ base DN và để LDAP server thực thi các quy tắc phù hợp khi tra cứu, bind hoặc thay đổi entry.

### Tài liệu tham khảo

- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [RFC 4517 — LDAP: Syntaxes and Matching Rules (mục 4.2.15: distinguishedNameMatch)](https://www.rfc-editor.org/rfc/rfc4517)
- [RFC 4518 — LDAP: Internationalized String Preparation](https://www.rfc-editor.org/rfc/rfc4518)
- [Java SE — `javax.naming.ldap.LdapName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html)
- [Java SE — `javax.naming.ldap.Rdn`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/Rdn.html)
- [Spring LDAP — Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
