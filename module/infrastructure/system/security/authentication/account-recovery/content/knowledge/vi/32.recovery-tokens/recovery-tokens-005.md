# Recovery token parsing

## 1. Parsing là cổng cú pháp, chưa phải quyết định khôi phục

**Recovery token parsing** là quá trình lấy token từ một vị trí đã quy định trong request, kiểm tra cấu trúc và chuyển nó thành biểu diễn mà tầng kiểm chứng có thể xử lý nhất quán.

Một parser an toàn cần trả lời các câu hỏi hẹp:

- Request có đúng một token ở đúng vị trí không?
- Token có kích thước và bảng ký tự được phép không?
- Các thành phần có đúng số lượng và định dạng không?
- Việc giải mã có tạo ra đúng dữ liệu mà giao thức quy định không?
- Chuỗi nhận được có phải cách biểu diễn chuẩn được chấp nhận không?

Parser chưa trả lời token có do hệ thống phát hành, còn hạn, chưa sử dụng hoặc có quyền thay MFA hay không.

Ví dụ, một chuỗi được tạo hoàn toàn từ các ký tự hợp lệ vẫn có thể qua parser dù hệ thống chưa từng phát hành nó. Đây là hành vi bình thường của tầng cú pháp. Lỗi bảo mật xuất hiện khi chương trình dùng kết quả parse thành công để cấp quyền reset.

```text
Request chưa tin cậy
    ↓
Tách một giá trị token theo hợp đồng transport
    ↓
Kiểm tra cú pháp và biểu diễn
    ↓
Kiểm chứng bí mật hoặc chữ ký
    ↓
Kiểm tra tài khoản, mục đích, thời hạn và trạng thái
    ↓
Tiêu thụ có kiểm soát khi thực hiện hành động được phép
```

Trong module khôi phục tài khoản, ranh giới này đặc biệt quan trọng vì token có thể dẫn đến đặt lại mật khẩu, thiết lập MFA mới hoặc đăng ký passkey sau khi mất thiết bị.

## 2. Định nghĩa hợp đồng token trước khi viết parser

Không nên viết một hàm “cố đọc mọi token”. Hệ thống cần xác định định dạng phát hành và những định dạng endpoint được phép nhận.

Một hợp đồng tối thiểu nên mô tả:

| Thành phần | Điều cần xác định |
| --- | --- |
| Vị trí nhận | Query parameter, JSON body hoặc vị trí cụ thể khác |
| Tên trường | Tên chính xác, cách xử lý trường lặp và trường không biết |
| Kiểu dữ liệu | Chuỗi; không tự chuyển mảng, số hoặc object thành chuỗi |
| Phiên bản | Những phiên bản được chấp nhận và đường xử lý tương ứng |
| Độ dài | Giới hạn trước khi thực hiện thao tác tốn tài nguyên |
| Bảng ký tự | Ví dụ ASCII Base64url và dấu phân cách cụ thể |
| Padding | Có cho phép `=` hay dùng dạng không padding |
| Giải mã | Lớp nào URL-decode, lớp nào Base64url-decode |
| Dạng chuẩn | Có từ chối biểu diễn không chuẩn không |
| Đầu ra | Dữ liệu đã parse, không phải một đối tượng “đã xác thực” |

Bài học sử dụng một định dạng **minh họa**, không phải tiêu chuẩn token chung:

```text
rt1.<selector>.<secret>
```

Trong đó:

- `rt1` là phiên bản định dạng.
- `selector` là 16 byte được mã hóa Base64url không padding, dài 22 ký tự.
- `secret` là 32 byte được mã hóa Base64url không padding, dài 43 ký tự.
- Toàn bộ chuỗi chuẩn dài `4 + 22 + 1 + 43 = 70` ký tự ASCII.
- `selector` giúp tìm bản ghi; biết selector không đủ chứng minh quyền recovery.
- `secret` là dữ liệu bí mật dùng ở tầng kiểm chứng.

Các kích thước này thuộc thiết kế minh họa. Chất lượng ngẫu nhiên được bảo đảm ở bước sinh token, không được suy ra chỉ từ việc chuỗi có đúng 70 ký tự.

Nếu dịch vụ chỉ dùng một opaque token ngẫu nhiên duy nhất, parser có thể đơn giản hơn và không cần tách selector. Không thêm thành phần hoặc metadata chỉ vì một token có nhiều trường trông có vẻ an toàn hơn.

## 3. Tách giá trị token mà không tạo mơ hồ

### 3.1. Mỗi endpoint chỉ nhận token theo một hợp đồng rõ ràng

Một lỗi dễ gặp là thử lấy token lần lượt từ query, body, header rồi cookie. Nếu có nhiều giá trị khác nhau, các tầng có thể chọn khác nhau.

Ví dụ:

```text
Query: token=TOKEN_A
JSON:  {"token": "TOKEN_B"}
```

Nếu lớp giới hạn thử lại xét A nhưng lớp cấp quyền dùng B, các kiểm soát không còn bảo vệ cùng một đầu vào.

Một thiết kế rõ ràng có thể dùng:

- Endpoint mở trang recovery nhận token từ query.
- Endpoint xác nhận hành động nhận token hoặc recovery session theo hợp đồng POST riêng.
- Mỗi endpoint từ chối nguồn credential không được quy định hoặc sự hiện diện mơ hồ của nhiều nguồn.

Đây là lựa chọn kiến trúc, không phải yêu cầu mọi bước đều dùng cùng một phương thức HTTP.

### 3.2. Từ chối tham số lặp

Request sau có hai giá trị cho cùng một tên:

```text
/recovery?token=TOKEN_A&token=TOKEN_B
```

Một thư viện có thể trả giá trị đầu, thư viện khác trả giá trị cuối hoặc một danh sách. Không dựa vào việc các tầng “chắc sẽ chọn giống nhau”.

Cần giữ được thông tin số lần xuất hiện trước khi chuyển sang cấu trúc chỉ chứa một giá trị. Trong thiết kế minh họa, `token` phải xuất hiện đúng một lần, kể cả khi các giá trị lặp giống nhau.

Tên tham số sau giải mã transport cũng cần được xử lý nhất quán. Không để một cách viết percent-encoded của tên trường vượt qua kiểm tra trùng rồi trở thành cùng tên ở tầng sau.

Với JSON, cần cấu hình hoặc dùng bộ đọc có khả năng phát hiện key lặp nếu hợp đồng yêu cầu từ chối. Không mặc định mọi parser JSON đều báo lỗi cho:

```json
{"token": "TOKEN_A", "token": "TOKEN_B"}
```

### 3.3. Không ép kiểu và không lấy một phần đầu vào

Các đầu vào sau không phải chuỗi token hợp lệ theo hợp đồng:

```json
{"token": null}
{"token": 12345}
{"token": ["TOKEN_A", "TOKEN_B"]}
{"token": {"value": "TOKEN_A"}}
```

Không lấy phần tử đầu của mảng, gọi `toString()` trên object hoặc cắt chuỗi dài về 70 ký tự để thử tiếp. Đầu vào sai hợp đồng cần bị từ chối.

Giới hạn kích thước request, số tham số và độ dài trường phải được áp dụng từ lớp nhận request. Kiểm tra trong hàm parse không ngăn được mọi chi phí mà web server đã bỏ ra để đọc một request quá lớn.

## 4. Tách giải mã transport khỏi giải mã token

### 4.1. URL-decode đúng một lần tại lớp được chỉ định

Nếu framework đã giải mã query parameter, hàm parse token nhận giá trị sau bước đó. Nó không được tiếp tục gọi URL decoder để “chắc chắn”.

Ví dụ về hai lớp encoding:

```text
Dữ liệu đến:          %252E
Sau URL-decode lần 1: %2E
Sau URL-decode lần 2: .
```

Nếu một tầng nhìn thấy `%2E` còn tầng khác nhìn thấy dấu chấm, việc tách thành phần và kiểm tra cú pháp có thể khác nhau.

Trong định dạng `rt1` minh họa, ký tự `%` còn lại trong giá trị đưa vào parser không thuộc bảng ký tự được phép và bị từ chối. Parser không tìm cách giải mã tiếp.

Một dấu chấm được biểu diễn qua percent-encoding hợp lệ ở lớp URL có thể trở thành dấu chấm sau đúng một lần giải mã. Việc chấp nhận biểu diễn transport đó phải nhất quán ở các tầng; không nhầm nó với việc cho phép decode lặp đến khi đầu vào “đọc được”.

### 4.2. Base64url khác Base64 thông thường

Base64url dùng `-` và `_` thay cho `+` và `/`. Không dùng bộ giải mã MIME có hành vi bỏ qua ký tự ngoài bảng chữ cái cho một token có hợp đồng chặt.

Với một số cách giải mã form, dấu `+` có thể được hiểu là khoảng trắng. Việc chọn Base64url giúp tránh vấn đề đó trong thiết kế phù hợp, nhưng không thay thế hợp đồng transport.

Không tự sửa `+` thành `-`, `/` thành `_` hoặc xóa ký tự lạ để cứu một token lỗi. Nếu cần hỗ trợ định dạng cũ, hãy có đường parser riêng theo phiên bản được cho phép.

### 4.3. Không chuẩn hóa token như tên người

Token dạng opaque thường phân biệt hoa/thường. Không tự:

- Gọi `trim()` để chấp nhận khoảng trắng ngoài hợp đồng.
- Chuyển toàn bộ sang chữ thường.
- Chuẩn hóa Unicode hoặc thay ký tự trông giống nhau.
- Bỏ ký tự xuống dòng được chèn giữa token.
- Cắt bỏ dấu phân cách hoặc thành phần thừa.

Một mã nhập tay được thiết kế để chấp nhận dấu cách là một giao thức khác. Quy tắc của mã đó không tự áp dụng cho token opaque trong URL.

## 5. Kiểm tra biểu diễn Base64url chuẩn

**Canonical encoding** nghĩa là chọn một cách biểu diễn chuẩn cho cùng một dữ liệu nhị phân.

RFC 4648 mô tả bảng chữ cái Base64url và vấn đề các bit đệm không có ý nghĩa dữ liệu. Một decoder cho phép biểu diễn không chuẩn có thể nhận nhiều chuỗi khác nhau thành cùng một dãy byte. [RFC 4648 — Canonical Encoding và Base64url](https://www.rfc-editor.org/rfc/rfc4648.html#section-3.5)

Vì vậy, kiểm tra regex và gọi decoder chưa nhất thiết hoàn thành hợp đồng dạng chuẩn.

Một cách kiểm tra trong thiết kế này:

```text
Kiểm tra độ dài và bảng ký tự
        ↓
Giải mã bằng Base64url decoder
        ↓
Kiểm tra đúng số byte
        ↓
Mã hóa lại bằng Base64url không padding
        ↓
Yêu cầu chuỗi mã hóa lại bằng chính chuỗi đầu vào
```

Bước mã hóa lại chỉ so hai biểu diễn của cùng dữ liệu đầu vào. Nó chưa so secret được gửi với bí mật hoặc giá trị kiểm tra đã lưu.

Các thành phần của hệ thống cũng cần thống nhất biểu diễn dùng làm khóa trạng thái. Nếu kho token dùng byte đã giải mã, còn chống phát lại hoặc giới hạn thử lại dùng chuỗi nhận được, biểu diễn không chuẩn có thể tạo hành vi không nhất quán.

Một đầu ra canonical giúp giảm khác biệt đó. Tuy nhiên, khóa chống phát lại vẫn nên dựa trên định danh và trạng thái có thẩm quyền của token, thay vì trông chờ riêng vào chuỗi do người gửi cung cấp.

## 6. Ví dụ parser Java cho định dạng minh họa

Đoạn mã dưới đây nhận **giá trị chuỗi sau bước xử lý transport đã quy định**. Nó chỉ kiểm tra định dạng `rt1`, không phát hành token, không truy vấn tài khoản và không quyết định quyền recovery.

Java cung cấp decoder Base64 có thể đọc đầu vào không có padding; vì vậy, quy tắc “chỉ nhận dạng không padding” của ứng dụng cần được thực thi riêng. [Java SE 21 — Base64.Decoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.Decoder.html)

```java
import java.util.Base64;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class RecoveryTokenParser {
    private static final int TOKEN_LENGTH = 70;

    private static final Pattern STRUCTURE = Pattern.compile(
            "rt1\\.([A-Za-z0-9_-]{22})\\.([A-Za-z0-9_-]{43})"
    );

    private static final Base64.Decoder URL_DECODER =
            Base64.getUrlDecoder();

    private static final Base64.Encoder URL_ENCODER =
            Base64.getUrlEncoder().withoutPadding();

    private RecoveryTokenParser() {
    }

    public static ParsedToken parse(String token) {
        if (token == null || token.length() != TOKEN_LENGTH) {
            throw invalidToken();
        }

        Matcher matcher = STRUCTURE.matcher(token);
        if (!matcher.matches()) {
            throw invalidToken();
        }

        byte[] selector = decodeCanonical(matcher.group(1), 16);
        byte[] secret = decodeCanonical(matcher.group(2), 32);

        return new ParsedToken(selector, secret);
    }

    private static byte[] decodeCanonical(
            String encoded,
            int expectedBytes
    ) {
        final byte[] decoded;

        try {
            decoded = URL_DECODER.decode(encoded);
        } catch (IllegalArgumentException exception) {
            throw invalidToken();
        }

        if (decoded.length != expectedBytes) {
            throw invalidToken();
        }

        if (!URL_ENCODER.encodeToString(decoded).equals(encoded)) {
            throw invalidToken();
        }

        return decoded;
    }

    private static IllegalArgumentException invalidToken() {
        return new IllegalArgumentException("Invalid recovery token");
    }

    public static final class ParsedToken {
        private final byte[] selector;
        private final byte[] secret;

        private ParsedToken(byte[] selector, byte[] secret) {
            this.selector = selector;
            this.secret = secret;
        }

        public byte[] selectorBytes() {
            return selector.clone();
        }

        public byte[] secretBytes() {
            return secret.clone();
        }

        @Override
        public String toString() {
            return "ParsedToken[redacted]";
        }
    }
}
```

Các điểm cần hiểu từ ví dụ:

1. Kiểm tra độ dài trước regex và giải mã.
2. Regex chỉ nhận bảng ASCII đã quy định, đúng dấu chấm và đúng phiên bản.
3. `matches()` yêu cầu toàn bộ chuỗi khớp, không tìm một token con trong chuỗi rác.
4. Cả độ dài sau giải mã lẫn biểu diễn mã hóa lại đều được kiểm tra.
5. Thông báo ngoại lệ không chứa token hoặc thành phần bí mật.
6. Đối tượng đầu ra có tên `ParsedToken`, không mang tên ngụ ý đã xác thực.
7. Getter trả bản sao để bên gọi không sửa trực tiếp mảng nội bộ.

Phép `equals` trong kiểm tra canonical không phải phép so sánh credential với dữ liệu lưu. Tầng kiểm chứng phải dùng cách so sánh phù hợp cho giá trị bí mật hoặc giá trị kiểm tra có độ dài cố định.

`toString()` được che không làm đối tượng hết nhạy cảm. Không đưa nó qua serializer, log request body hay công cụ thu thập biến cục bộ của lỗi. Chuỗi đầu vào và các bản sao byte vẫn cần được giữ trong phạm vi cần thiết.

Đoạn mã không xử lý tham số lặp hay URL-decode: những việc đó thuộc adapter nhận request và phải hoàn tất trước khi gọi `parse`.

## 7. Những đầu vào minh họa cần được phân biệt

Bảng sau mô tả hành vi theo hợp đồng `rt1` của bài học. Các giá trị `S` và `V` ở đây là ký hiệu cho selector và secret hợp lệ, không phải token thực.

| Đầu vào hoặc tình huống | Tầng xử lý | Kết quả theo hợp đồng |
| --- | --- | --- |
| Thiếu trường token | Adapter request | Từ chối, không gọi verifier |
| Hai trường `token` | Adapter request | Từ chối vì mơ hồ |
| Giá trị là mảng hoặc object | Adapter request | Từ chối kiểu dữ liệu |
| `rt1.S.V` có đủ kích thước thật và canonical | Parser | Có thể parse thành công |
| `RT1.S.V` | Parser | Từ chối phiên bản không khớp |
| Có thêm khoảng trắng ở đầu hoặc cuối | Parser | Từ chối, không trim |
| Có `=` padding | Parser | Từ chối trong định dạng không padding này |
| Có `+`, `/` hoặc Unicode ngoài bảng | Parser | Từ chối |
| Có thành phần thứ tư sau dấu chấm | Parser | Từ chối cấu trúc |
| Còn `%` sau xử lý transport | Parser | Từ chối, không decode thêm |
| Đúng bảng ký tự nhưng mã hóa lại khác chuỗi gốc | Parser | Từ chối dạng không canonical |
| Chuỗi đúng cú pháp nhưng chưa từng được phát hành | Verifier | Không đủ điều kiện cấp quyền |
| Token đúng secret nhưng đã dùng | Tầng trạng thái và tiêu thụ | Từ chối sử dụng lại |

Một ví dụ hữu ích về ranh giới là chuỗi được tạo bằng:

```text
"rt1." + 22 ký tự "A" + "." + 43 ký tự "A"
```

Hai phần Base64url này biểu diễn các byte bằng không và có thể đáp ứng cú pháp của ví dụ. Parser không thể nhìn chuỗi rồi kết luận nó đã được sinh ngẫu nhiên hoặc được phát hành cho một tài khoản.

Tầng kiểm chứng phải từ chối nếu không có bản ghi và giá trị bí mật tương ứng hợp lệ. Không thêm quy tắc đặc biệt chỉ để nhận diện mỗi chuỗi ví dụ này rồi coi vấn đề đã được giải quyết.

## 8. Sau parsing: kiểm chứng và gắn với đúng hành động

Với mô hình selector và secret, luồng phía máy chủ có thể là:

```text
ParsedToken
    ↓
Tìm bản ghi theo selector trong đúng phạm vi dịch vụ
    ↓
Tính và kiểm tra giá trị bí mật theo scheme phát hành
    ↓
Kiểm tra accountRef, caseRef, purpose và phiên bản
    ↓
Kiểm tra hạn, thu hồi và trạng thái đã dùng
    ↓
Cập nhật có điều kiện để tiêu thụ và thực hiện hành động
```

Bản ghi có thẩm quyền xác định tài khoản và mục đích. Không lấy `userId` do trình duyệt gửi rồi áp token đã kiểm chứng của tài khoản khác vào đó.

Cách tạo giá trị kiểm tra khi phát hành và cách kiểm chứng phải dùng cùng một biểu diễn. Nếu hệ thống chọn byte đã giải mã, không có tầng khác tự đổi sang băm một chuỗi đã trim hoặc đã chuyển chữ thường.

Các thành phần có kích thước cố định giúp việc ghép byte ít mơ hồ hơn, nhưng scheme kiểm chứng vẫn cần quy định phiên bản và phạm vi sử dụng. Không tự sáng tạo phép ghép hoặc thay thuật toán trong parser.

Dù kiểm chứng secret thành công, vẫn phải từ chối nếu token:

- Dành cho đặt lại mật khẩu nhưng được dùng để bỏ MFA.
- Thuộc hồ sơ đã hủy hoặc tài khoản không còn đủ điều kiện.
- Đã hết hạn theo nguồn giờ có thẩm quyền.
- Đã bị thu hồi hoặc thay thế theo chính sách.
- Đã được tiêu thụ trong một yêu cầu khác.

Đọc được token không tạo quyền; kiểm chứng đúng secret cũng chưa thay mọi điều kiện nghiệp vụ.

## 9. Nếu token là JWT, decode payload vẫn chưa đủ

Không chọn parser bằng số dấu chấm rồi thử JWT trước, opaque token sau cho đến khi một hàm trả kết quả. Định dạng `rt1` minh họa cũng có ba thành phần, nhưng không phải JWT.

Endpoint cần biết những loại token được phép nhận. Khi dùng JWT, hãy dùng thư viện JOSE phù hợp và cấu hình kiểm chứng theo hợp đồng của ứng dụng.

Các giới hạn cần giữ:

- Header và payload đọc được trước kiểm chứng vẫn là dữ liệu chưa tin cậy.
- Thuật toán được chấp nhận phải do máy chủ quy định, không do trường `alg` tự quyết định.
- Khóa phải đến từ nguồn tin cậy; không dùng dữ liệu trong token như đường dẫn hoặc URL tùy ý để lấy khóa.
- Các claim như issuer, audience, mục đích và thời gian phải được kiểm tra theo yêu cầu của loại recovery token.
- Kiểu dữ liệu và đơn vị thời gian phải rõ ràng; không tự ép một giá trị sai kiểu cho vừa schema.
- Token của luồng đăng nhập không tự được dùng làm token recovery.

RFC 8725 nêu các biện pháp kiểm chứng thuật toán, issuer, audience và phân biệt những loại JWT có mục đích khác nhau. Những kiểm tra đó nằm sau hoặc đi cùng xử lý cấu trúc; Base64url-decode payload không thay thế chúng. [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html#section-3)

Một JWT có chữ ký đúng và còn hạn cũng không tự có tính dùng một lần. Nếu luồng yêu cầu chống phát lại, hệ thống cần trạng thái tiêu thụ hoặc cơ chế tương ứng có thẩm quyền.

Không đưa nhánh JWT vào parser opaque chỉ để tăng số định dạng được hỗ trợ khi dịch vụ không cần nó.

## 10. Lỗi parsing cần an toàn và có giới hạn tài nguyên

### 10.1. Không để lỗi trở thành nguồn lộ token

Không viết log kiểu:

```text
Invalid recovery token: <nguyên token người dùng gửi>
```

Log có thể đi qua proxy, công cụ giám sát, hệ thống hỗ trợ và kho phân tích với nhiều người được quyền xem. Token còn hạn có thể bị dùng như một bearer credential nếu bị lộ.

Có thể ghi mã lỗi nội bộ như `TOKEN_FORMAT_INVALID`, định danh request do hệ thống tạo và thông tin cần thiết đã được tối thiểu hóa. Không phản chiếu nguyên token lên HTML hoặc thông báo lỗi.

Việc debug cũng không cần cắt một phần secret để đưa vào log. Nếu cần liên kết sự kiện, ưu tiên định danh nội bộ được thiết kế cho mục đích đó.

### 10.2. Phân biệt lỗi dữ liệu với lỗi vận hành ở phía nội bộ

Token sai cấu trúc có thể bị từ chối trước khi truy vấn kho dữ liệu. Nhưng kho token không truy cập được là một lỗi vận hành, không phải lý do coi mọi token đã kiểm chứng.

Không bắt mọi exception rồi trả kết quả “hợp lệ để người dùng không bị chặn”. Ngược lại, không công khai chi tiết kho dữ liệu, khóa hoặc trạng thái tài khoản qua thông báo bên ngoài.

Thông báo chung như “Liên kết không hợp lệ hoặc không còn hiệu lực” có thể phù hợp. Không cần tiết lộ selector có tồn tại, tài khoản nào gắn với nó hoặc token đã được dùng lúc nào.

### 10.3. Không dùng parsing để làm công việc không cần thiết

Tránh giải nén, giải mã đệ quy hoặc xử lý cấu trúc lồng nhau nếu hợp đồng token không có những tính năng đó.

Giới hạn đầu vào trước các thao tác cấp phát bộ nhớ. Regex cần có cấu trúc đơn giản và giới hạn rõ; không dùng một biểu thức phức tạp để tìm mọi dạng token trong một chuỗi tùy ý.

Token chỉ là dữ liệu. Không dùng thành phần của nó làm câu SQL ghép chuỗi, đường dẫn file, tên lớp hoặc địa chỉ gọi mạng.

## 11. URL, trình duyệt và tiêu thụ token

Nếu token được gửi qua liên kết, việc parsing diễn ra trong một bối cảnh có nguy cơ lộ qua lịch sử, log và referrer.

OWASP khuyến nghị dùng HTTPS, kiểm soát URL reset từ miền tin cậy và dùng chính sách referrer phù hợp để giảm lộ token. Token reset cũng cần thời hạn và chỉ dùng một lần. [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#url-tokens)

Một thiết kế cần xác định:

1. Trang mở liên kết có tải tài nguyên từ bên thứ ba làm lộ thông tin không?
2. Query chứa token có được che ở các lớp log liên quan không?
3. Token còn nằm trong URL sau khi chuyển sang bước xử lý khác không?
4. Endpoint nhận hành động có cơ chế bảo vệ request và ràng buộc ngữ cảnh phù hợp không?
5. Việc đổi token sang recovery session có giới hạn quyền và thời gian ra sao?

Không tiêu thụ token chỉ vì một GET mở liên kết. Trình quét an toàn email hoặc chức năng xem trước có thể tự truy cập URL. Cần thiết kế điểm tiêu thụ gắn với bước xác nhận hoặc hành động rõ ràng.

Nếu đổi token sang một recovery session giới hạn, việc đổi phải được bảo vệ và có kiểm soát dùng một lần; không được trở thành cách phát nhiều session từ cùng một token.

Token hết hạn hoặc dùng rồi không được hồi sinh bằng retry. Việc thay yếu tố xác thực, xử lý session cũ và thông báo thay đổi bảo mật vẫn cần chính sách riêng sau khi đủ điều kiện thực hiện.

## 12. Giữ hợp đồng parsing thống nhất khi thay phiên bản

Trong quá trình nâng cấp, có thể tồn tại nhiều phiên bản token còn hạn. Hệ thống cần mô tả rõ phiên bản nào được phát và phiên bản nào còn được nhận.

Một router phiên bản an toàn chỉ chọn trong các parser đã được cấu hình cho endpoint. Gặp `rt9` không có nghĩa tự thử parser `rt1` sau khi bỏ tiền tố.

Khi thay thư viện hoặc quy tắc decode, cần xem sự khác nhau về:

- Padding và ký tự ngoài bảng.
- Biểu diễn canonical.
- Tham số hoặc key lặp.
- URL-decode và ép kiểu.
- Độ dài tối đa và cách báo lỗi.

Không dùng cơ chế fallback rộng để làm mọi token cũ “vẫn chạy”. Nếu cần tương thích, hãy giữ hợp đồng của phiên bản cũ rõ ràng và giới hạn vòng đời theo chính sách.

Một parser tốt làm nhỏ bề mặt đầu vào: đúng một giá trị, đúng cấu trúc, đúng bảng ký tự và một biểu diễn nhất quán. Quyền khôi phục chỉ xuất hiện sau kiểm chứng mật mã hoặc bí mật, kiểm tra ngữ cảnh và bước tiêu thụ có thẩm quyền.
