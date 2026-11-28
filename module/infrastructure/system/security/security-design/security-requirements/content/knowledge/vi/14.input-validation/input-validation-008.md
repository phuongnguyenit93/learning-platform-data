# Canonicalization

## 1. Tại sao cùng một dữ liệu lại có nhiều cách biểu diễn?

Một hệ thống chỉ cho phép người dùng tải báo cáo của chính tenant mình. Gateway kiểm tra chuỗi đường dẫn nhận được, nhưng dịch vụ tải file lại giải mã chuỗi thêm một lần trước khi mở tài nguyên. Nếu hai thành phần hiểu cùng input theo hai cách khác nhau, quyết định bảo mật ở gateway có thể không còn đúng với tài nguyên thực sự được sử dụng.

Vấn đề tương tự xuất hiện khi tên tài khoản có hai dạng Unicode nhìn giống nhau, mã dự án được so sánh không phân biệt hoa thường ở database nhưng phân biệt ở cache, hoặc dịch vụ xác minh chữ ký dùng một bản JSON khác với bản bên gửi đã ký.

**Canonicalization**, hay đưa về biểu diễn chuẩn, là quá trình chọn một cách biểu diễn nhất quán cho những giá trị mà một giao thức hoặc miền nghiệp vụ đã xác định là tương đương. Nó giúp các thành phần cùng xác thực, so sánh và sử dụng một ý nghĩa dữ liệu.

Đây không phải phép biến mọi input thành “dữ liệu an toàn”. Trước khi viết hàm chuẩn hóa, yêu cầu bảo mật phải trả lời:

- Dữ liệu thuộc kiểu nào và được giải mã theo giao thức nào?
- Những biểu diễn nào thực sự được coi là cùng một giá trị?
- Những biến đổi nào được cho phép, những trường hợp nào phải từ chối?
- Thành phần nào sở hữu việc chuẩn hóa?
- Giá trị nào được dùng để phân quyền và truy cập tài nguyên?
- Có phép biến đổi nào còn diễn ra sau quyết định bảo mật không?

Trong thiết kế yêu cầu bảo mật, canonicalization có giá trị khi nó loại bỏ sự nhập nhằng giữa **thứ đã được kiểm tra** và **thứ được sử dụng**.

## 2. Phân biệt các thao tác thường bị gọi chung là “normalize”

| Thao tác | Mục đích | Ví dụ | Điều không được suy ra |
|---|---|---|---|
| Decoding | Chuyển biểu diễn theo một giao thức sang dữ liệu tương ứng | Giải mã percent-encoding trong thành phần URI phù hợp | Mọi chuỗi chứa `%` đều cần decode |
| Parsing | Đọc dữ liệu theo cấu trúc và kiểu | Parse JSON thành object hoặc parse số theo contract | Parse thành công nghĩa là nghiệp vụ hợp lệ |
| Canonicalization | Chọn đại diện cho lớp giá trị tương đương | Mã dự án không phân biệt hoa thường được lưu chữ thường | Mọi trường đều có cùng quy tắc tương đương |
| Validation | Kiểm tra dữ liệu có đáp ứng chính sách không | Mã dự án dài 3–32 ký tự và thuộc alphabet cho phép | Input hợp lệ đồng nghĩa người gọi có quyền |
| Sanitization | Loại bỏ hoặc sửa nội dung theo chính sách riêng | Loại bỏ phần tử HTML bị cấm trong rich text | Có thể tùy ý “sửa cho đúng” một định danh |
| Output encoding | Mã hóa khi đưa dữ liệu vào ngữ cảnh đầu ra | Escape dữ liệu khi hiển thị trong HTML | Có thể thay bằng chuẩn hóa Unicode |
| Authorization | Xác định chủ thể được thao tác trên tài nguyên nào | Người dùng chỉ đọc được dự án thuộc tenant của mình | Định danh đúng cú pháp thì được truy cập |

OWASP khuyến nghị giải mã theo giao thức trước khi kiểm tra quy tắc của trường, xác thực biểu diễn thực sự được sử dụng và tránh giải mã lại ở phía sau. Kiểm tra quyền, truy vấn tham số hóa và mã hóa đầu ra vẫn là các lớp bảo vệ riêng. [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html#parse-safely-then-validate)

Việc chuẩn hóa nên là một quyết định có phạm vi: “mã dự án ASCII không phân biệt hoa thường”, thay vì “mọi input đều trim, lowercase và URL-decode”.

## 3. Định nghĩa quan hệ tương đương trước khi chọn thuật toán

Gọi `x ~ y` nếu contract của một trường coi `x` và `y` là cùng một giá trị. Hàm chuẩn hóa `C` cần phù hợp với quan hệ đó.

Hai thuộc tính quan trọng:

~~~text
Nếu x ~ y thì C(x) = C(y).

Nếu C(x) = C(y) thì việc coi x và y là một
phải được chính sách của trường cho phép.
~~~

Thuộc tính thứ nhất giúp tránh một tài nguyên có nhiều định danh không nhất quán. Thuộc tính thứ hai ngăn chuẩn hóa quá mạnh khiến hai giá trị cần phân biệt bị nhập làm một.

Ví dụ:

- Nếu mã dự án không phân biệt hoa thường, `Team-A` và `team-a` có thể dùng chung canonical key.
- Nếu tên file trên một hệ thống có phân biệt hoa thường, không được tự coi `Report.csv` và `report.csv` là một.
- Với số tiền, `10.00` và `10` có thể cùng giá trị số, nhưng số chữ số thập phân có thể vẫn mang ý nghĩa trong contract.
- Với chuỗi token bí mật, không được tự trim hay đổi hoa thường nếu giao thức không quy định.
- Với tên hiển thị của người dùng, giữ dấu và cách viết có thể là yêu cầu nghiệp vụ quan trọng, dù một khóa tìm kiếm phụ có cách xử lý khác.

Một bước chuẩn hóa thuần túy thường nên có tính lũy đẳng:

~~~text
C(C(x)) = C(x)
~~~

Tuy nhiên, toàn bộ pipeline giải mã giao thức không phải là một hàm có thể gọi lặp tùy ý. Percent-decoding hai lần có thể thay đổi ý nghĩa; tính lũy đẳng của một bước chuẩn hóa không cấp quyền giải mã lại cả input.

Canonicalization cũng có thể là hàm không xác định trên một số đầu vào: input sai mã hóa, nhập nhằng hoặc ngoài miền hợp lệ cần bị từ chối, thay vì luôn được “sửa” thành một giá trị.

## 4. Pipeline an toàn và ranh giới sở hữu

Mô hình tổng quát:

~~~mermaid
flowchart LR
    A[Bytes từ bên ngoài] --> B[Giới hạn kích thước và kiểm tra framing]
    B --> C[Decode và parse đúng giao thức]
    C --> D[Chuẩn hóa theo profile của trường]
    D --> E[Kiểm tra cú pháp và ngữ nghĩa]
    E --> F[Tra cứu và kiểm tra quyền]
    F --> G[Sử dụng cùng giá trị hoặc tài nguyên đã xác định]
~~~

Mỗi bước có thể có kiểm tra bảo vệ riêng. Ví dụ giới hạn kích thước cần có trước parser, còn điều kiện “ngày kết thúc sau ngày bắt đầu” chỉ có nghĩa sau khi đã parse ngày.

Một pipeline cụ thể có thể là:

~~~text
HTTP body có giới hạn
    -> đọc UTF-8 nghiêm ngặt
    -> parse JSON theo schema
    -> lấy projectCode là String
    -> kiểm tra alphabet đầu vào đã công bố
    -> chuẩn hóa mã sang chữ thường
    -> tạo kiểu CanonicalProjectCode
    -> tra cứu theo tenant và canonical code
    -> kiểm tra quyền trên project
    -> thao tác bằng project ID đã tìm được
~~~

Không cần cố đưa mọi loại validation vào đúng một vị trí duy nhất. Có kiểm tra hợp lệ của bytes, kiểm tra trước biến đổi và kiểm tra trên giá trị chuẩn. Điều bắt buộc là những quyết định trên dữ liệu đã biến đổi phải xem đúng biểu diễn được dùng cuối cùng.

Yêu cầu phân công trách nhiệm nên đủ cụ thể:

| Thành phần | Trách nhiệm minh họa |
|---|---|
| HTTP server hoặc ingress | Giới hạn request, áp dụng chính sách route và xử lý URI đã thống nhất |
| JSON parser | Parse JSON, xử lý lỗi encoding/cú pháp và chính sách trường trùng |
| Adapter của API | Áp dụng profile chuẩn hóa cho đúng trường |
| Domain service | Nhận kiểu đã chuẩn hóa; kiểm tra nghiệp vụ và quyền |
| Repository | Tra cứu bằng cùng khóa chuẩn, cùng tenant |
| Cache | Dùng khóa nhất quán với định danh mà repository và phân quyền sử dụng |

Nếu framework đã giải mã route parameter, domain service không được đoán rằng nó vẫn đang nhận raw URI rồi gọi decoder thêm lần nữa.

Việc “decode một lần” cần hiểu là một lần cho **mỗi lớp mã hóa do giao thức khai báo**. HTTP framing, JSON escape và một giá trị được định nghĩa riêng là Base64 có thể là các lớp khác nhau hợp lệ. Nguy hiểm là giải mã lại cùng một lớp hoặc tự phát hiện rồi decode khi contract không cho phép.

## 5. Percent-encoding và double decoding

Xét một chuỗi trong ngữ cảnh URI:

~~~text
%252e%252e%252f
    -- decode percent một lần --> %2e%2e%2f
    -- decode percent lần nữa --> ../
~~~

Nếu bộ kiểm tra chỉ nhìn biểu diễn giữa, nhưng nơi mở file nhìn biểu diễn cuối, quyết định kiểm tra có thể bị vô hiệu hóa.

Không phải mọi endpoint phải từ chối mọi ký tự `%`. Chính sách phụ thuộc kiểu trường:

- Mã dự án ASCII không có `%`: từ chối nếu giá trị sau parse chứa `%`.
- Nội dung bình luận tự do: ký tự `%` có thể hoàn toàn hợp lệ và không được decode tùy tiện.
- Một URI do người dùng nhập: parse bằng thư viện URI và quy tắc cho từng thành phần.
- Một blob được định nghĩa là opaque: giữ nguyên theo contract của blob.

Trong RFC 3986, ký tự reserved có vai trò cấu trúc. Không thể mặc định một ký tự reserved được percent-encode luôn tương đương với dạng không encode, vì việc thay đổi có thể ảnh hưởng cách diễn giải URI. [RFC 3986, mục 2.2 và 6](https://www.rfc-editor.org/rfc/rfc3986.html#section-2.2)

Ví dụ một dấu `/` thực sự có thể phân tách hai path segment, trong khi `%2F` có thể được một thành phần giữ trong segment hoặc một thành phần khác giải mã thành separator. API phải thống nhất hành vi xuyên qua ingress, router và ứng dụng; trường hợp không hỗ trợ thì từ chối sớm.

### Không dùng URLDecoder cho mọi chuỗi URL

`java.net.URLDecoder` là decoder cho `application/x-www-form-urlencoded`. Trong ngữ cảnh này, dấu `+` được chuyển thành khoảng trắng. Nó không phải bộ chuẩn hóa tổng quát cho mọi phần của URI. [Java URLDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLDecoder.html)

So sánh các trường hợp:

| Ngữ cảnh | Input | Ý nghĩa cần tuân theo |
|---|---|---|
| Form URL-encoded | `name=A+B` | Decoder form có thể cho giá trị `A B` |
| Giá trị JSON | `{"name":"A+B"}` | Dấu `+` là dữ liệu của chuỗi JSON |
| Giá trị JSON | `{"name":"%2F"}` | JSON không tự quy định percent-decoding |
| URI path | `/items/A+B` | Không dùng quy tắc form để tự biến `+` thành space |
| JSON string có escape | `"\u0061"` | JSON parser tạo ký tự `a` |
| JSON string chứa backslash literal | `"\\u0061"` | Sau parse vẫn là chuỗi ký tự backslash-u; không unescape thêm tùy ý |

Một hàm tiện ích “decode cho sạch” đặt trong mọi service thường phá hỏng những ranh giới này.

## 6. Unicode normalization: tương đương không chỉ là nhìn giống nhau

Một chữ có dấu có thể được biểu diễn bằng ký tự dựng sẵn hoặc chuỗi ký tự cơ sở kèm dấu kết hợp. Chẳng hạn:

~~~text
U+00E9             : é
U+0065 U+0301      : e + combining acute accent
~~~

Hai chuỗi có thể hiển thị giống nhau nhưng khác dãy code point và khác bytes.

Unicode định nghĩa bốn normalization form:

| Dạng | Cách xử lý khái quát |
|---|---|
| NFC | Phân rã tương đương canonical rồi kết hợp lại khi có thể |
| NFD | Phân rã tương đương canonical |
| NFKC | Phân rã compatibility rồi kết hợp lại |
| NFKD | Phân rã compatibility |

Các dạng compatibility có thể loại bỏ những khác biệt mà ứng dụng cần giữ, như một số biến thể ký tự hoặc định dạng. Vì vậy lựa chọn NFC hay NFKC phải là quyết định của profile dữ liệu. [Unicode Standard Annex #15](https://www.unicode.org/reports/tr15/)

Ví dụ Java:

~~~java
import java.text.Normalizer;

String precomposed = "\u00E9";
String combining = "e\u0301";

String first = Normalizer.normalize(precomposed, Normalizer.Form.NFC);
String second = Normalizer.normalize(combining, Normalizer.Form.NFC);

boolean sameCanonicalValue = first.equals(second); // true
~~~

`java.text.Normalizer` hỗ trợ các normalization form Unicode. Chọn một form vẫn là trách nhiệm của ứng dụng, không phải quyết định thư viện tự làm thay cho nghiệp vụ. [Java Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)

### Những việc NFC không giải quyết

- NFC không tự chuyển mọi ký tự trông giống nhau thành cùng một ký tự.
- Chữ Latin `a` và chữ Cyrillic `а` không trở thành một chỉ vì nhìn tương tự.
- NFC không phải quy tắc case folding.
- NFC không tự quyết định có nên xóa dấu tiếng Việt, ký tự zero-width hoặc ký tự điều hướng hai chiều hay không.
- NFC không ngăn SQL injection, XSS hoặc lạm dụng quyền.

Ví dụ một tên hiển thị có thể được lưu NFC và vẫn cho phép Unicode rộng. Định danh kỹ thuật dùng để phân quyền lại có thể bị giới hạn ASCII. Hai trường không phải dùng cùng chính sách chỉ vì đều có kiểu `String`.

Hệ thống cũng cần phân biệt “độ dài” theo bytes UTF-8, UTF-16 code units, Unicode code points và đơn vị hiển thị. `String.length()` trong Java không mặc định là số ký tự mà người dùng cảm nhận.

## 7. Case, khoảng trắng và những phép biến đổi làm mất thông tin

Lowercase, trim, bỏ dấu và thay separator thường xuất hiện trong cùng một hàm normalize. Chúng chỉ an toàn khi quan hệ tương đương của trường cho phép.

### Mã kỹ thuật không phân biệt hoa thường

Nếu alphabet đã giới hạn là ASCII và nghiệp vụ không phân biệt hoa thường, đưa về chữ thường là một lựa chọn rõ ràng. Với Unicode tổng quát, lowercase không đồng nghĩa với đầy đủ quy tắc so sánh không phân biệt hoa thường; còn có lựa chọn case folding và những khác biệt theo ngôn ngữ.

`Locale.ROOT` giúp tránh phụ thuộc locale mặc định khi thực hiện chuyển case theo mục đích kỹ thuật, nhưng không tự biến phép lowercase thành một profile Unicode identity hoàn chỉnh.

### Khoảng trắng

`"team-a"` và `" team-a "` chỉ được nhập làm một nếu contract cho phép loại bỏ khoảng trắng ngoài. Có thể chọn từ chối khoảng trắng cho mã dự án để lỗi client được phát hiện rõ ràng.

Đừng mặc định mọi ký tự trông như space đều được `trim` xử lý giống nhau. Cũng không nên thay mọi loại whitespace bằng một dấu space trên dữ liệu mà khoảng trắng có ý nghĩa, như nội dung ký, mật khẩu hoặc file do người dùng cung cấp.

### Những trường không được tự chuẩn hóa

Với API key, token, mã khôi phục, chuỗi đã ký hoặc mật khẩu, phải tuân theo đúng giao thức/quy trình đã công bố. Không tự lowercase hoặc xóa khoảng trắng để làm xác thực “dễ thành công hơn”. Nếu một hệ thống có quy tắc chuẩn hóa credential được thiết kế từ đầu, quy tắc đó phải nhất quán ở cả lúc tạo lẫn lúc xác minh.

Địa chỉ email cũng không nên được lowercase toàn bộ bằng một quy tắc mặc định cho mọi nhà cung cấp. Hành vi địa chỉ, định danh tài khoản và xác minh sở hữu cần được đặc tả riêng.

Nguyên tắc là: chấp nhận một phép biến đổi vì **hợp đồng dữ liệu cho phép**, không phải vì nó thuận tiện khi viết một hàm dùng chung.

## 8. Ví dụ profile cho mã dự án

Giả sử nền tảng có API quản lý dự án và tải báo cáo. Một người dùng thuộc tenant A được thao tác trên những dự án đã được cấp quyền trong tenant A.

Profile minh họa cho `projectCode`:

| Thuộc tính | Quy tắc đã chọn |
|---|---|
| Kiểu đầu vào | Chuỗi JSON |
| Alphabet đầu vào | ASCII chữ cái, chữ số, dấu gạch ngang và gạch dưới |
| Độ dài | 3–32 ký tự ASCII |
| Ký tự đầu | Chữ cái hoặc chữ số |
| Phân biệt hoa thường | Không |
| Canonical form | Chữ thường ASCII |
| Khoảng trắng ngoài | Từ chối; không trim |
| Percent-decoding | Không thực hiện trên giá trị sau JSON parse |
| Unicode compatibility mapping | Không áp dụng |
| Khóa định danh | Cặp `tenant_id` và `canonical_project_code` |
| Quy tắc xung đột | Hai mã có cùng canonical form trong cùng tenant không tạo hai project khác nhau |

Ví dụ:

| Giá trị sau JSON parse | Kết quả |
|---|---|
| `Team-A` | Chấp nhận, canonical là `team-a` |
| `team-a` | Cùng canonical identity với `Team-A` |
| `TEAM_A` | Chấp nhận, canonical là `team_a` |
| `team-a ` | Từ chối do khoảng trắng |
| `team%2Da` | Từ chối; không decode thành `team-a` |
| `Ｔｅａｍ-A` | Từ chối theo alphabet, không dùng NFKC để tự đổi thành ASCII |
| `../team-a` | Từ chối theo grammar |
| `ab` | Từ chối vì chưa đủ độ dài |

Giới hạn này là lựa chọn cho một **mã kỹ thuật**. Không nên sao chép nó sang tên hiển thị, tên người hoặc bình luận vì sẽ làm mất nhu cầu ngôn ngữ hợp lệ.

Một profile khác cho `displayName` có thể cho phép Unicode rộng, áp dụng NFC, cấm ký tự điều khiển không phù hợp và giới hạn theo code point sau chuẩn hóa. Trường này không được tự biến thành định danh dùng cho phân quyền.

### Ví dụ Java với kiểu biểu diễn chuẩn

~~~java
import java.util.Locale;
import java.util.regex.Pattern;

public record ProjectCode(String value) {
    private static final Pattern RAW =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9_-]{2,31}");

    private static final Pattern CANONICAL =
            Pattern.compile("[a-z0-9][a-z0-9_-]{2,31}");

    public ProjectCode {
        if (value == null || !CANONICAL.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "ProjectCode requires canonical ASCII form");
        }
    }

    public static ProjectCode fromRaw(String raw) {
        if (raw == null || raw.length() > 64) {
            throw new IllegalArgumentException("Invalid project code");
        }

        if (!RAW.matcher(raw).matches()) {
            throw new IllegalArgumentException("Invalid project code");
        }

        String canonical = raw.toLowerCase(Locale.ROOT);
        return new ProjectCode(canonical);
    }
}
~~~

Giới hạn 64 trước regex là chặn sớm cho đối số ở hàm này; grammar vẫn giới hạn giá trị hợp lệ tối đa 32 ký tự. Giới hạn request trước khi đọc body là một lớp riêng, không được thay bằng kiểm tra độ dài sau khi body đã được buffer toàn bộ.

Compact constructor bảo đảm cả trường hợp gọi `new ProjectCode(...)` trực tiếp cũng không tạo một đối tượng chứa biểu diễn không chuẩn. Đối tượng immutable giúp service phía sau không cần nhận lại raw string rồi tự quyết định normalize theo cách khác.

Ví dụ sử dụng theo thiết kế:

~~~java
ProjectCode code = ProjectCode.fromRaw(request.projectCode());

Project project = repository.findByTenantAndCode(
        authenticatedTenantId,
        code.value()
);

authorization.requireCanRead(currentPrincipal, project.id());

return reportService.readProjectReport(project.id());
~~~

Đây là mã minh họa luồng dữ liệu; các API repository và service biểu diễn trách nhiệm kiến trúc. Điểm quan trọng là tenant lấy từ ngữ cảnh đã xác thực, tra cứu dùng canonical code, kiểm tra quyền gắn với project đã tìm được, rồi sử dụng cùng project ID.

Không viết một luồng mà `requireCanRead` nhận `code.value()` nhưng `readProjectReport` lại nhận raw input và tra cứu lại theo quy tắc khác.

## 9. Xung đột định danh, database và cache

Canonicalization có thể làm hai input khác nhau trở thành cùng một canonical key. Với `Team-A` và `team-a`, đây là kết quả mong muốn của profile. Hệ thống vẫn phải xử lý việc hai người đồng thời tạo cùng identity.

Các yêu cầu liên quan:

1. Unique constraint được áp dụng trên khóa mà nghiệp vụ thực sự dùng, ví dụ `(tenant_id, canonical_project_code)`.
2. So sánh/collation ở database phù hợp với profile; không tự nhập thêm các giá trị mà ứng dụng muốn phân biệt.
3. Cạnh tranh tạo mới được xử lý bằng ràng buộc nguyên tử ở kho dữ liệu hoặc cơ chế tương đương.
4. Xung đột không được dẫn đến ghi đè project hiện có.
5. Cache, rate limit và audit dùng identity nhất quán với đường tra cứu nghiệp vụ.

Chỉ kiểm tra “mã này chưa tồn tại” trong ứng dụng trước khi insert là chưa đủ, vì hai request đồng thời có thể cùng vượt qua bước kiểm tra.

### Cache phải phân biệt đúng phạm vi

Ví dụ cache key tốt theo profile:

~~~text
project:<tenant-id>:<canonical-project-code>
~~~

Không dùng chỉ `project:team-a` nếu tenant A và tenant B được phép có mã giống nhau. Cũng không dùng raw code cho cache nhưng canonical code cho database rồi kỳ vọng hai lớp có hành vi thống nhất.

Chính sách normalize quá mạnh ở cache cũng nguy hiểm. Nếu database phân biệt dấu nhưng cache tự bỏ dấu, hai tài nguyên khác nhau có thể dùng chung entry.

### Lưu raw hay canonical?

Có thể lưu riêng:

- Canonical key: phục vụ identity, unique constraint và tra cứu.
- Display value: phục vụ hiển thị nếu nghiệp vụ cần giữ cách viết.
- Policy version: phục vụ kiểm soát thay đổi quy tắc ở các hệ thống cần migration.

Không nhất thiết phải lưu raw request. Raw input có thể chứa dữ liệu nhạy cảm hoặc chuỗi điều khiển; mục đích điều tra không tự tạo quyền giữ toàn bộ payload vô thời hạn.

## 10. Đường dẫn tài nguyên: lexical normalization chưa đủ

Đường dẫn là nơi canonicalization dễ bị hiểu thành một “hàm sửa path” duy nhất. Cần tách ít nhất ba vấn đề:

- Biểu diễn path trong URI.
- Quy tắc path của hệ điều hành/filesystem.
- Quyền truy cập file thực sự tại thời điểm mở.

Với một download API, thiết kế thường đơn giản hơn nếu client gửi ID báo cáo do server cấp; server ánh xạ ID sang vị trí lưu trữ thuộc quyền quản lý của mình. Không cần cho client gửi một filesystem path tùy ý khi nghiệp vụ chỉ cần chọn báo cáo.

Nếu ứng dụng thực sự nhận đường dẫn tương đối, contract cần xác định:

- Có cho `.`, `..`, path tuyệt đối, separator thay thế hoặc encoded separator không?
- Chạy trên những filesystem nào, có phân biệt hoa thường không?
- Có cho symlink/junction hoặc mount ngoài vùng dữ liệu không?
- Ai được sửa cấu trúc thư mục trong lúc ứng dụng đang xử lý?
- Cơ chế mở file có bảo đảm còn trong vùng được cấp quyền không?

Trong Java, `Path.normalize()` xử lý path theo dạng lexical mà không truy cập filesystem. Nó không thay thế việc giải quyết liên kết và kiểm soát file thực tế. `toRealPath()` có hành vi truy cập filesystem cho path tồn tại, nhưng cũng không tự giải quyết mọi cạnh tranh giữa kiểm tra và mở file. [Java Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html)

Một lỗi đơn giản là kiểm tra containment bằng tiền tố chuỗi:

~~~text
base      = /data/exports
candidate = /data/exports-private/secret.csv
~~~

`candidate` bắt đầu bằng cùng chuỗi ký tự nhưng không thuộc thư mục `/data/exports` theo cấu trúc path.

Ngay cả containment theo path segment cũng chỉ là một phần. Một symlink trong thư mục hợp lệ có thể trỏ ra ngoài; hoặc tài nguyên bị thay đổi sau kiểm tra. Tùy mô hình đe dọa, cần kết hợp quyền filesystem, hạn chế khả năng sửa symlink, sandbox hoặc API mở file tương đối với directory handle có bảo đảm phù hợp.

Không nên ghi yêu cầu “normalize rồi startsWith là đủ chống path traversal”. Yêu cầu đúng cần gắn kết quả kiểm tra với **file được mở**, trong môi trường và mô hình cạnh tranh đã xác định.

## 11. Dữ liệu có cấu trúc và sự nhập nhằng giữa parser

Canonicalization của một trường chuỗi không sửa được sự nhập nhằng ở cấp object.

Xét JSON:

~~~json
{
  "projectCode": "team-a",
  "projectCode": "team-b"
}
~~~

Nếu lớp kiểm tra chọn giá trị đầu nhưng lớp xử lý chọn giá trị cuối, việc normalize hai chuỗi không giải quyết được lỗi. Với các API bảo mật nhạy cảm, nên quy định từ chối trường trùng và xác minh parser thực thi chính sách đó.

Các trường hợp cần đặc tả thêm:

| Trường hợp | Quyết định cần có |
|---|---|
| Field trùng | Từ chối hay một hành vi duy nhất có thể chứng minh nhất quán |
| Field không biết | Từ chối hoặc bỏ qua theo schema; không để tầng sau tự hiểu thêm quyền |
| `null` và field vắng mặt | Có cùng nghĩa hay khác nhau |
| Key JSON khác hoa thường | Có phân biệt không; không tự đổi toàn bộ key nếu schema phân biệt |
| Tên key sau mapping bị trùng | Phát hiện và từ chối nếu profile có mapping |
| Số lớn hoặc số có exponent | Parse theo kiểu và phạm vi xác định |
| Ngày giờ | Chọn format, timezone/offset được chấp nhận và nghĩa của giá trị |
| URL trong object | Parse theo contract riêng, không normalize như chuỗi tự do |

Ví dụ `1`, `1.0` và `1e0` có thể cùng giá trị số sau một cách parse, nhưng không có cùng bytes. Nếu dữ liệu còn tham gia chữ ký số hoặc idempotency key, cần biết tầng nào so sánh theo giá trị, tầng nào so sánh theo biểu diễn.

Không cắt bỏ các ký tự không hiểu được rồi tiếp tục xử lý một object khác với dữ liệu người gọi đã gửi. Nếu chọn chuyển đổi, contract phải mô tả kết quả và kiểm soát xung đột phát sinh.

## 12. URL, chữ ký và dữ liệu opaque cần profile riêng

### URL

Lowercase toàn bộ URL có thể thay đổi path hoặc query có phân biệt hoa thường. Parse URL thành các thành phần trước khi áp dụng quy tắc đúng cho từng thành phần.

Nếu URL là đích request do server gọi, canonicalization mới chỉ hỗ trợ nhận diện. Nó không thay thế kiểm soát scheme, host, port, redirect, DNS và địa chỉ mạng thực sự kết nối. Một URL đã parse thành công vẫn có thể trỏ tới tài nguyên nội bộ không được phép.

Đối với hostname quốc tế, cần cơ chế xử lý tên miền phù hợp với giao thức, không chỉ gọi Unicode NFC trên toàn chuỗi URL. Cũng không được áp dụng IDNA hay loại bỏ dấu chấm cuối tùy tiện mà bỏ qua contract và các thành phần sử dụng hostname.

### Chữ ký hoặc MAC

Có hai loại contract thường gặp:

1. **Ký bytes gốc:** bên nhận xác minh chính xác dãy bytes thuộc phạm vi ký trước các phép biến đổi không được giao thức cho phép.
2. **Ký biểu diễn canonical do giao thức định nghĩa:** hai bên dùng đúng thuật toán canonicalization của giao thức trước khi ký và xác minh.

Không tự parse JSON, sắp xếp key và serialize lại rồi gọi đó là canonical JSON nếu giao thức chưa định nghĩa cách xử lý số, escaping, field trùng và mọi chi tiết liên quan.

Việc xác minh chữ ký không bỏ qua các giới hạn kích thước cần áp dụng trước. Còn việc parse dữ liệu đã ký vẫn cần parser và validation an toàn theo contract.

### Credential và dữ liệu opaque

Chuỗi opaque có thể chứa `+`, `/`, `=`, chữ hoa, chữ thường hoặc khoảng trắng có ý nghĩa theo giao thức. Chỉ decoder của đúng giao thức mới được xử lý chúng.

Ví dụ một token nằm trong JSON không có nghĩa là phải URL-decode token sau khi JSON parser đã trả chuỗi. Thêm một lần decoder có thể biến credential thành giá trị khác hoặc tạo bất nhất giữa các bên xác minh.

## 13. Bộ yêu cầu bảo mật mẫu

Các yêu cầu dưới đây dùng cho API dự án minh họa, không phải cấu hình áp dụng mặc định cho mọi hệ thống.

| ID | Yêu cầu | Bằng chứng nghiệm thu dự kiến |
|---|---|---|
| CAN-01 | Mỗi trường tham gia identity, routing hoặc quyền truy cập có profile chuẩn hóa được công bố | Có mapping trường → kiểu đầu vào → phép biến đổi → canonical form |
| CAN-02 | Adapter xác định dữ liệu đang ở lớp mã hóa nào và không decode lại cùng lớp sau validation | Theo dõi giá trị qua ingress, parser, service và sink với ca encoded kép |
| CAN-03 | Quyết định phân quyền và thao tác tài nguyên dùng cùng identity đã xác định | Trace thể hiện project ID được kiểm tra là ID được sử dụng |
| CAN-04 | `projectCode` tuân theo profile ASCII 3–32 ký tự và chữ thường canonical | Các biến thể hợp lệ cùng khóa; Unicode/space/percent ngoài grammar bị từ chối |
| CAN-05 | Trùng canonical key trong cùng tenant không tạo hoặc ghi đè hai project | Unique constraint và ca tạo đồng thời |
| CAN-06 | Cache dùng cùng phạm vi tenant và quan hệ tương đương với repository | Hai tenant không chia entry; các biến thể hợp lệ của một mã có hành vi nhất quán |
| CAN-07 | Input sai encoding hoặc cấu trúc không được âm thầm sửa theo nhiều cách ở các tầng | Ca bytes lỗi, field trùng và escape sai bị xử lý theo contract |
| CAN-08 | Hạn mức tồn tại trước parser và sau các bước có thể mở rộng biểu diễn | Ca đầu vào quá lớn bị từ chối trước khi tiêu tốn tài nguyên ngoài hạn |
| CAN-09 | Credential, payload đã ký và các trường opaque không chịu biến đổi ngoài giao thức | Các ca `+`, case và khoảng trắng giữ đúng nghĩa đã công bố |
| CAN-10 | Thay profile không tự nhập hai identity hoặc chuyển quyền giữa chúng | Migration phát hiện collision, có phương án xử lý trước rollout |

CAN-08 cần số đo cụ thể theo từng API. Ví dụ với một endpoint nhỏ, có thể chọn body tối đa 16 KiB, `displayName` tối đa 1.024 byte UTF-8 trước chuẩn hóa và tối đa 80 code point sau NFC. Các giá trị này chỉ minh họa cách đặt giới hạn; không thay thế đánh giá tài nguyên và nhu cầu thực tế.

Nếu request có nén, hạn mức bytes trên đường truyền không đủ để giới hạn kích thước sau giải nén. Parser cũng có thể cần giới hạn độ sâu và số phần tử. Không nên đợi tới bước chuẩn hóa chuỗi mới áp dụng mọi giới hạn.

## 14. Ma trận trường hợp nghiệm thu

Cần xây corpus theo **ngữ cảnh**, không chỉ một danh sách payload “nguy hiểm” dùng chung. Cùng một chuỗi có thể hợp lệ trong bình luận và không hợp lệ trong mã dự án.

| Nhóm | Ca đầu vào hoặc sự kiện | Kết quả mong đợi theo profile minh họa |
|---|---|---|
| ASCII case | `Team-A` và `team-a` | Cùng canonical project code |
| Khoảng trắng | ` team-a` | Từ chối cho mã dự án |
| Unicode canonical | Hai biểu diễn của `é` trong display name | Cùng NFC nếu profile display name chọn NFC |
| Unicode compatibility | Fullwidth trong project code | Từ chối; không tự NFKC thành ASCII |
| Confusable | Latin `a` và Cyrillic `а` | Không tự coi là một chỉ do nhìn giống |
| Percent literal trong JSON | `team%2Da` | Từ chối cho mã dự án, không percent-decode |
| Plus trong JSON | `"A+B"` ở trường văn bản cho phép | Giữ dấu cộng |
| Double encoding | `%252e%252e%252f` ở trường report ID hạn chế | Từ chối theo grammar; không decoder lần nữa |
| Cấu trúc | JSON trùng `projectCode` | Từ chối theo parser policy của API |
| Cạnh tranh | Hai request tạo `Team-A`/`team-a` trong cùng tenant | Chỉ một identity được tạo |
| Tenant | Cùng code nhưng khác tenant | Không chia cache hoặc quyền |
| Phân quyền | Code hợp lệ của project không thuộc quyền người gọi | Từ chối truy cập tài nguyên |
| Thay đổi tài nguyên | Symlink/file thay đổi giữa kiểm tra và mở | Không mở tài nguyên ngoài vùng cho phép theo mô hình triển khai |
| Giới hạn | Chuỗi rất dài trước NFC hoặc sau biến đổi | Từ chối theo hạn mức đã chọn |
| Locale | Chạy ở hai locale mặc định khác nhau | Project code ASCII có canonical form giống nhau |
| Chữ ký | Payload có cùng giá trị nhưng khác bytes | Xử lý theo contract chữ ký, không theo suy đoán của ứng dụng |

Các kịch bản nên có cả:

- **Positive cases:** biến thể hợp lệ cho cùng một giá trị vẫn hoạt động.
- **Negative cases:** biến thể ngoài contract bị từ chối.
- **Collision cases:** các giá trị bị đưa về cùng khóa được xử lý đúng.
- **Cross-component cases:** ingress, framework, service, cache và kho lưu diễn giải nhất quán.

Ma trận này mô tả bằng chứng cần có khi nghiệm thu thiết kế. Nó chưa phải báo cáo đã chạy các ca kiểm thử.

### Một kịch bản kiểm tra tính nhất quán

**Given:** người dùng được đọc project có code canonical `team-a` trong tenant A.

**When:** request dùng `Team-A` và được adapter chuyển thành `team-a`.

**Then:** repository, kiểm tra quyền, cache và thao tác cuối cùng đều gắn cùng project ID trong tenant A.

**And:** không có bước phía sau lấy raw input rồi chuyển nó thành một identity khác.

### Một kịch bản kiểm tra collision

**Given:** tenant A đã có project `team-a`.

**When:** client tạo project mới với code `TEAM-A`.

**Then:** hệ thống xử lý xung đột theo contract; không ghi đè, không chuyển owner và không gán quyền của project cũ cho một đối tượng mới.

## 15. Thay đổi profile là thay đổi identity

Giả sử hệ thống trước đây phân biệt hoa thường, sau đó muốn chuyển sang không phân biệt hoa thường. Hai project `Team-A` và `team-a` đang tồn tại có thể trở thành một canonical key.

Không nên xử lý bằng một migration đơn giản “lowercase mọi dòng” rồi bỏ qua xung đột. Hậu quả có thể gồm mất dữ liệu, nhầm owner, cache sai tài nguyên và trao quyền sai.

Một kế hoạch thay đổi cần:

1. Xác định profile cũ và mới, cùng mọi nơi đang dùng identity.
2. Tính thử canonical key mới trên tập dữ liệu được phép xử lý.
3. Liệt kê collision và đánh giá quyền/owner của các đối tượng liên quan.
4. Có cách giải quyết xung đột được nghiệp vụ phê duyệt trước khi ghi dữ liệu.
5. Đồng bộ database constraint, ứng dụng, cache và các tích hợp.
6. Kiểm soát thời gian hai phiên bản ứng dụng chạy đồng thời.
7. Chuẩn bị rollback không làm hỏng quan hệ quyền và định danh.

Các nâng cấp thư viện Unicode, parser hoặc collation của database cũng cần đánh giá khả năng thay đổi quan hệ tương đương. Không phải nâng cấp nào cũng thay identity, nhưng không nên mặc định chúng hoàn toàn vô can khi profile phụ thuộc các thành phần đó.

Nếu sử dụng policy version, phiên bản phải giúp kiểm soát hành vi thật của dữ liệu và ứng dụng, không chỉ là một trường metadata không được dùng.

## 16. Lỗi thường gặp khi đặc tả canonicalization

| Cách làm | Vì sao có vấn đề | Điều cần đặc tả lại |
|---|---|---|
| “Decode tới khi chuỗi không đổi” | Có thể biến dữ liệu literal thành cấu trúc mới | Lớp mã hóa được khai báo và chủ thể decode |
| “NFKC toàn bộ request” | Có thể nhập các giá trị cần phân biệt | Profile theo từng trường |
| “Lowercase tất cả để so sánh dễ” | Có thể đổi path, token hoặc dữ liệu ký | Quy tắc case của từng miền dữ liệu |
| “Trim là vô hại” | Có thể làm thay đổi credential hoặc che lỗi định danh | Chính sách khoảng trắng rõ ràng |
| “NFC đã chống ký tự giả mạo” | Normalization không đồng nghĩa phát hiện confusable | Kiểm soát identifier và hiển thị theo nhu cầu |
| “Chuẩn hóa trước mọi xử lý là đủ” | Parser có thể cạn tài nguyên trước khi tới bước đó | Giới hạn ở từng lớp |
| “Database sẽ xử lý so sánh” | Database và cache có thể dùng quan hệ khác nhau | Profile và collation/index nhất quán |
| “Validate một bản, dùng bản gốc” | Quyết định bảo mật không gắn với dữ liệu thực thi | Truyền giá trị chuẩn hoặc resource ID xuyên suốt |
| “normalize path là chống traversal” | Còn symlink, filesystem semantics và race | Ràng buộc tới tài nguyên thực sự được mở |
| “Input hợp lệ nên được truy cập” | Validation không xác định quyền | Authorization trên tài nguyên sau tra cứu |

Canonicalization thường làm lộ ra những quyết định nghiệp vụ trước đây chưa được viết rõ: hai tên nào được coi là một, điều gì phải được bảo toàn và hệ thống làm gì khi không thể hiểu input một cách duy nhất.

## 17. Bài tập chuyển thành yêu cầu bảo mật

Thiết kế một endpoint nhận:

~~~json
{
  "projectCode": "Team-A",
  "displayName": "Báo cáo doanh thu",
  "reportId": "rpt-7f82"
}
~~~

Hãy viết ba profile riêng thay vì một hàm normalize chung. Với mỗi trường, xác định:

1. Kiểu và mã hóa đầu vào; ai đã parse hoặc decode trước đó.
2. Quan hệ tương đương mà nghiệp vụ chấp nhận.
3. Các phép biến đổi được phép và thứ tự thực hiện.
4. Các giới hạn trước và sau biến đổi.
5. Cách xử lý input sai, nhập nhằng hoặc gây collision.
6. Giá trị dùng để tra cứu, phân quyền, cache và lưu trữ.
7. Ít nhất một positive case, một negative case và một ca đi qua nhiều thành phần.

Một yêu cầu canonicalization đủ rõ phải cho phép lần theo cùng một ý nghĩa dữ liệu từ biên nhận request tới tài nguyên cuối cùng. Khi hai thành phần có thể đưa ra hai cách hiểu khác nhau, cần sửa contract hoặc từ chối sự nhập nhằng trước khi dựa vào dữ liệu đó để quyết định bảo mật.
