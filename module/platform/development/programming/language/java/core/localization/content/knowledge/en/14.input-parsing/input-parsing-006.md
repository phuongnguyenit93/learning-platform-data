# Thông báo lỗi theo Locale nhưng giữ mã lỗi ổn định trong Java

## Mục tiêu

Khi người dùng nhập một số, ngày tháng, số lượng hoặc dữ liệu biểu mẫu không hợp lệ, ứng dụng cần giải quyết **hai bài toán khác nhau**:

1. **Xác định loại lỗi một cách ổn định** để chương trình, API client, giám sát và kiểm thử xử lý đúng. Ví dụ: `INPUT_NUMBER_INVALID`.
2. **Giải thích lỗi bằng ngôn ngữ phù hợp** với người nhận, ví dụ: “Số lượng không phải số hợp lệ.” hoặc “Quantity must be a valid number.”

Nếu dùng câu dịch làm mã lỗi, cùng một lỗi sẽ có nhiều định danh khác nhau theo ngôn ngữ. Nếu dùng một chuỗi tiếng Anh cố định làm thông báo cho mọi người, giao diện khó dùng và bỏ qua nhu cầu localization. Thiết kế đúng là **giữ code độc lập với `Locale`, còn message được tra cứu/định dạng theo `Locale`**.

Sau bài học, bạn có thể:

- Phân biệt **error code**, **message key**, **localized message**, **field identifier**, **HTTP status** và **technical detail**.
- Thiết kế một danh sách mã lỗi ổn định cho việc phân tích đầu vào, không phụ thuộc tên người dùng hoặc ngôn ngữ.
- Dùng `ResourceBundle` với `Locale` và `MessageFormat` để trả thông điệp đa ngôn ngữ từ một kết quả validation.
- Xử lý lỗi parse theo lớp: dữ liệu thiếu, cú pháp sai, còn phần dư, ngoài phạm vi và vi phạm quy tắc nghiệp vụ.
- Xây dựng hợp đồng API và kiểm thử trong đó **code giữ nguyên** nhưng **message thay đổi** theo locale.
- Nhận diện các bẫy: dùng message để điều khiển logic, nhầm lỗi validation với lỗi server, fallback che thiếu bản dịch, làm lộ dữ liệu nhạy cảm qua log hoặc thông điệp.

Bài học thuộc phần **Phân tích đầu vào**: đầu tiên phát hiện và phân loại lỗi, sau đó mới tạo thông điệp được bản địa hóa. Không cần biến văn bản dịch thành một thành phần của thuật toán phân tích.

## 1. Một lỗi có nhiều cách diễn đạt, nhưng chỉ một định danh

Giả sử biểu mẫu yêu cầu số lượng trong khoảng từ 1 đến 100. Người dùng nhập `abc`.

Cùng một kết quả validation có thể được trình bày:

| Thành phần | Tiếng Việt | Tiếng Anh |
| --- | --- | --- |
| Mã lỗi | `INPUT_NUMBER_INVALID` | `INPUT_NUMBER_INVALID` |
| Message key | `error.number.invalid` | `error.number.invalid` |
| Thông báo | `Số lượng không phải số hợp lệ.` | `Quantity must be a valid number.` |
| Field identifier | `quantity` | `quantity` |
| HTTP status minh họa | `400` | `400` |

**Mã lỗi và field identifier là định danh để máy xử lý. Thông báo là nội dung dành cho người đọc.** Một người dùng đổi ngôn ngữ từ tiếng Việt sang tiếng Anh không làm tình trạng dữ liệu `abc` thay đổi, cũng không buộc API phát sinh một loại lỗi khác.

Sơ đồ xử lý:

```text
Raw input + quy tắc/Locale đầu vào
               |
       Parse + validate
               |
      Kết quả dạng cấu trúc
      code=INPUT_NUMBER_INVALID
      field=quantity
               |
        Tra message key
               |
      ResourceBundle + Locale
          /             \
         v               v
    vi-VN message    en-US message
         \               /
          v             v
    Response code không đổi
    Message phù hợp người đọc
```

Phần **phát hiện lỗi** không phụ thuộc vào cách dịch câu. Nếu người dịch sửa “không phải số hợp lệ” thành “vui lòng nhập số”, cùng `INPUT_NUMBER_INVALID` vẫn là cùng lỗi với cùng chính sách xử lý.

## 2. Phân biệt các khái niệm liên quan

| Khái niệm | Mục đích | Ví dụ | Có thay theo Locale? |
| --- | --- | --- | --- |
| **Error code** | Định danh công khai, ổn định cho loại lỗi | `INPUT_NUMBER_INVALID` | Không |
| **Message key** | Định danh khóa trong tệp tài nguyên | `error.number.invalid` | Không |
| **Localized message** | Giải thích cho người dùng | `Số lượng không phải số hợp lệ.` | Có |
| **Field identifier** | Chỉ trường dữ liệu lỗi | `quantity` | Không |
| **Localized field label** | Tên trường đọc được trên giao diện | `Số lượng` / `Quantity` | Có |
| **HTTP status** | Phân loại kết quả ở cấp giao thức | `400 Bad Request` | Không |
| **Context parameters** | Dữ liệu cần điền vào mẫu dịch | `min=1`, `max=100` | Giá trị ổn định; cách hiển thị có thể theo locale |
| **Technical detail / diagnostic** | Phục vụ điều tra hệ thống | parse position, exception type | Không nên là thông điệp hiển thị công khai |

Mặc dù code và key trong ví dụ có nội dung gần nhau, chúng **không nhất thiết là cùng chuỗi**:

- `INPUT_NUMBER_INVALID` có thể là định danh trong hợp đồng API.
- `error.number.invalid` có thể là tên key của `ResourceBundle`.
- Một ánh xạ từ code sang key được duy trì trong code/configuration và có thể đổi cấu trúc tài nguyên mà **không làm hỏng contract của client**.

Tương tự, `HTTP 400` không thay thế code. Nhiều lỗi như trường thiếu, số không hợp lệ, ngày sai định dạng có thể đều dùng HTTP 400 nhưng cần các code khác nhau để client hiển thị lỗi ở trường tương ứng hoặc thực hiện xử lý khác.

Đừng nhầm `Locale` với **múi giờ**, **đơn vị tiền**, hoặc **vùng thực tế của người dùng**. Locale dùng cho việc parse/format có thể khác locale mong muốn khi hiển thị thông báo, nếu ứng dụng có chính sách rõ ràng; không suy ra thông tin nhạy cảm từ Locale.

## 3. Bước đầu: phân loại lỗi trước khi dịch

Với một trường số, những trường hợp này không nên bị nhập chung nếu ứng dụng cần hành vi khác nhau:

| Điều kiện đầu vào | Error code minh họa | Ý nghĩa |
| --- | --- | --- |
| Không có giá trị hoặc chuỗi rỗng | `INPUT_NUMBER_REQUIRED` | Trường bắt buộc chưa được nhập |
| Không thể bắt đầu parse thành số | `INPUT_NUMBER_INVALID` | Cú pháp số không hợp lệ |
| Parser chỉ đọc được tiền tố `10` của `10abc` | `INPUT_NUMBER_INVALID` | Còn phần dư trái với hợp đồng trường chỉ nhận số |
| Parse được số nhưng vượt giới hạn | `INPUT_NUMBER_OUT_OF_RANGE` | Đúng kiểu số, sai miền giá trị |
| Số có nhiều chữ số thập phân hơn mức cho phép | `INPUT_NUMBER_SCALE_INVALID` | Không đáp ứng yêu cầu precision/scale nghiệp vụ |

Các code trên là **thiết kế mẫu cho ứng dụng**, không phải các hằng số mà JDK tự cung cấp. Ứng dụng có thể chọn tên khác, nhưng nên thống nhất về ý nghĩa và mức độ cụ thể.

Quy trình lý tưởng:

1. Nhận giá trị và ngữ cảnh đầu vào, bao gồm locale của trường nếu người dùng nhập số/ngày theo định dạng địa phương.
2. Phân biệt *thiếu trường* với *trường có nội dung sai* nếu nghiệp vụ cần hai phản hồi khác nhau.
3. Parse theo đúng grammar/locale và kiểm tra **toàn bộ đầu vào được tiêu thụ** nếu đây là trường chỉ chứa một giá trị.
4. Kiểm tra kiểu, miền giá trị và quy tắc nghiệp vụ; không dùng việc parse thành công như bằng chứng mọi điều kiện đều đúng.
5. Trả một kết quả có cấu trúc chứa giá trị thành công **hoặc** code lỗi cố định; chưa cần dịch.
6. Khi tạo phản hồi cho người dùng, chọn locale hiển thị, lấy mẫu thông báo, điền tham số và xuất kết quả.

Tách như vậy giúp cùng thuật toán validation được gọi từ giao diện web, ứng dụng di động, CLI và batch import. Từng kênh có thể chọn cách diễn đạt lỗi phù hợp mà không thay đổi logic cốt lõi.

## 4. Vì sao không nên dùng thông điệp làm logic?

Một cách làm dễ hỏng:

```java
if (errorMessage.equals("Số lượng không phải số hợp lệ.")) {
    highlightQuantityField();
}
```

Đây là **đoạn minh họa anti-pattern**, giả định biến `errorMessage` và phương thức `highlightQuantityField` đã tồn tại. Khi người dùng đổi ngôn ngữ, thông điệp thay thành tiếng Anh và điều kiện không còn đúng. Ngay cả ở tiếng Việt, một chỉnh sửa câu chữ hoặc dấu câu của người dịch cũng có thể phá vỡ logic.

Nên dùng:

```java
if (errorCode == ErrorCode.INPUT_NUMBER_INVALID) {
    highlightQuantityField();
}
```

Đây là đoạn minh họa trong mã ứng dụng có `ErrorCode` và hàm xử lý UI tương ứng. `ErrorCode` là kiểu/định danh máy đọc, không là câu hiển thị.

Điều tương tự áp dụng với log và giám sát: nếu thống kê bằng message, một lỗi có thể bị chia thành nhiều nhóm theo ngôn ngữ, placeholder và phiên bản dịch. Thống kê bằng code sẽ ổn định hơn.

**Không bao giờ parse chuỗi thông báo** để lấy ý nghĩa nghiệp vụ. Nội dung đã dịch không phải giao thức dữ liệu, và trật tự từ, dấu câu, định dạng số có thể thay đổi hợp lệ theo từng locale.

## 5. Dùng ResourceBundle để ánh xạ code thành thông điệp

Java cung cấp `java.util.ResourceBundle` để tìm chuỗi tài nguyên theo tên và `Locale`. Với thông điệp có tham số, dùng `java.text.MessageFormat`.

Ví dụ họ tài nguyên:

```text
messages.properties
messages_en.properties
messages_vi.properties
```

Bản gốc:

```properties
# messages.properties
field.quantity=Quantity
error.number.required={0} is required.
error.number.invalid={0} must be a valid number.
error.number.outOfRange={0} must be between {1} and {2}.
```

Bản tiếng Việt:

```properties
# messages_vi.properties
field.quantity=Số lượng
error.number.required=Vui lòng nhập {0}.
error.number.invalid={0} không phải số hợp lệ.
error.number.outOfRange={0} phải nằm trong khoảng {1} đến {2}.
```

Khi cần thông báo:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", locale);

String pattern = bundle.getString("error.number.invalid");
String fieldLabel = bundle.getString("field.quantity");

String message = new MessageFormat(pattern, locale)
        .format(new Object[] {fieldLabel});
```

Đây là **đoạn minh họa bên trong phương thức**, cần import `ResourceBundle`, `MessageFormat` và có biến `locale` kiểu `Locale`. Với tiếng Việt, kết quả là `Số lượng không phải số hợp lệ.`; tiếng Anh sẽ có thông điệp tương ứng.

**Cần tách riêng key của lỗi và label của trường**:

- Code `INPUT_NUMBER_INVALID` không chứa văn bản “Số lượng”.
- Key `field.quantity` xác định label dịch của trường.
- Pattern `error.number.invalid` có placeholder `{0}` cho label.
- Những field khác có thể dùng cùng loại lỗi nhưng với label khác, trong khi `field` kỹ thuật vẫn là định danh ổn định của trường đó.

Đừng nối câu dịch bằng `"Sai " + fieldLabel` hoặc `fieldLabel + " invalid"`: mỗi ngôn ngữ có trật tự từ và ngữ pháp khác nhau. Hãy đưa cả câu vào pattern để người dịch có quyền đảo vị trí placeholder.

### Placeholder cũng phải có hợp đồng

Với pattern `"{0} must be between {1} and {2}."`:

- `{0}`: label đã dịch của trường.
- `{1}`: giới hạn nhỏ nhất.
- `{2}`: giới hạn lớn nhất.

Người dịch được phép sắp xếp lại các tham số để đúng ngữ pháp, nhưng **không nên xóa, thêm sai index, hoặc đổi ý nghĩa của chúng**. Mỗi key nên có chú thích dành cho người dịch về vị trí sử dụng, giọng văn và ý nghĩa placeholder.

`MessageFormat` có cú pháp riêng cho dấu nháy đơn `'` và ngoặc nhọn. Một thông điệp có apostrophe hoặc pattern lồng phải được kiểm thử bằng chính `MessageFormat`; không thay thế tùy tiện bằng `String.replace("{0}", ...)`.

Lưu ý `ResourceBundle` có cơ chế fallback: nếu bản địa phương thiếu một key, có thể lấy giá trị từ parent/root bundle. Như vậy chương trình vẫn chạy nhưng người dùng có thể thấy câu tiếng Anh giữa giao diện tiếng Việt. Hãy kiểm tra độ đầy đủ bản dịch ở pipeline thay vì xem fallback thành công là đã dịch đủ.

## 6. Ví dụ hoàn chỉnh Java 17+: code cố định, câu dịch thay đổi

Ta xây dựng một parser đơn giản cho trường số lượng, chấp nhận khoảng `1..100`. Ví dụ minh họa rõ:

- Input thiếu: `INPUT_NUMBER_REQUIRED`.
- Input không phải số hoặc còn ký tự sau tiền tố số: `INPUT_NUMBER_INVALID`.
- Input đúng số nhưng ngoài khoảng: `INPUT_NUMBER_OUT_OF_RANGE`.
- Input hợp lệ: trả giá trị số, không có lỗi.
- Với cùng input sai, `Locale` tiếng Việt và tiếng Anh cho **cùng code** nhưng message khác nhau.

Ví dụ dùng `DecimalFormat#setParseBigDecimal(true)` để lấy đối tượng decimal và `ParsePosition` để kiểm tra parser tiêu thụ hết chuỗi. Nó không tuyên bố kiểm tra nghiêm ngặt mọi quy tắc dấu phân nhóm của tất cả locale; đó là kiểm tra riêng nếu sản phẩm yêu cầu.

Tạo **bốn tệp** trong cùng một thư mục, lưu `.properties` bằng UTF-8.

### Tệp 1: messages.properties

```properties
# Root bundle: fallback when a locale-specific translation is absent.
# TRANSLATORS: {0} = localized field label.
field.quantity=Quantity
error.number.required={0} is required.
error.number.invalid={0} must be a valid number.
# TRANSLATORS: {0} = field label, {1} = min, {2} = max.
error.number.outOfRange={0} must be between {1} and {2}.
```

### Tệp 2: messages_en.properties

Bản tiếng Anh được khai báo tường minh để ví dụ không dựa vào sự lựa chọn default locale của JVM khi tìm bundle:

```properties
field.quantity=Quantity
error.number.required={0} is required.
error.number.invalid={0} must be a valid number.
error.number.outOfRange={0} must be between {1} and {2}.
```

### Tệp 3: messages_vi.properties

```properties
# TRANSLATORS: {0} = nhãn trường đã được dịch.
field.quantity=Số lượng
error.number.required=Vui lòng nhập {0}.
error.number.invalid={0} không phải số hợp lệ.
# TRANSLATORS: {0} = nhãn trường, {1} = nhỏ nhất, {2} = lớn nhất.
error.number.outOfRange={0} phải nằm trong khoảng {1} đến {2}.
```

### Tệp 4: LocalizedInputErrorsDemo.java

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedInputErrorsDemo {

    private enum ErrorCode {
        INPUT_NUMBER_REQUIRED("error.number.required"),
        INPUT_NUMBER_INVALID("error.number.invalid"),
        INPUT_NUMBER_OUT_OF_RANGE("error.number.outOfRange");

        private final String messageKey;

        ErrorCode(String messageKey) {
            this.messageKey = messageKey;
        }
    }

    private record ParseResult(BigDecimal value, ErrorCode error) {}

    private static ParseResult parseQuantity(
            String raw, Locale inputLocale) {
        if (raw == null || raw.isBlank()) {
            return new ParseResult(null, ErrorCode.INPUT_NUMBER_REQUIRED);
        }

        DecimalFormat parser = (DecimalFormat)
                NumberFormat.getNumberInstance(inputLocale);
        parser.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(raw, position);

        if (!(parsed instanceof BigDecimal)
                || position.getIndex() != raw.length()) {
            return new ParseResult(null, ErrorCode.INPUT_NUMBER_INVALID);
        }

        BigDecimal quantity = (BigDecimal) parsed;
        BigDecimal min = BigDecimal.ONE;
        BigDecimal max = new BigDecimal("100");

        if (quantity.compareTo(min) < 0
                || quantity.compareTo(max) > 0) {
            return new ParseResult(
                    null, ErrorCode.INPUT_NUMBER_OUT_OF_RANGE);
        }

        return new ParseResult(quantity, null);
    }

    private static String localize(
            ErrorCode code, Locale displayLocale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", displayLocale);

        String pattern = bundle.getString(code.messageKey);
        String field = bundle.getString("field.quantity");

        return new MessageFormat(pattern, displayLocale)
                .format(new Object[] {
                    field,
                    BigDecimal.ONE,
                    new BigDecimal("100")
                });
    }

    private static void show(
            String language, Locale locale, String raw) {
        ParseResult result = parseQuantity(raw, locale);

        if (result.error() == null) {
            System.out.println(language
                    + " | OK | " + result.value().toPlainString());
        } else {
            System.out.println(language + " | "
                    + result.error().name() + " | "
                    + localize(result.error(), locale));
        }
    }

    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale en = Locale.US;

        show("VI", vi, "");
        show("EN", en, "");

        show("VI", vi, "abc");
        show("EN", en, "abc");

        show("VI", vi, "150");
        show("EN", en, "150");

        show("VI", vi, "10x");
        show("EN", en, "10x");

        show("VI", vi, "10");
        show("EN", en, "10");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên, từ thư mục chứa cả bốn tệp:

```bash
javac -encoding UTF-8 LocalizedInputErrorsDemo.java
java -cp . LocalizedInputErrorsDemo
```

Stdout:

```text
VI | INPUT_NUMBER_REQUIRED | Vui lòng nhập Số lượng.
EN | INPUT_NUMBER_REQUIRED | Quantity is required.
VI | INPUT_NUMBER_INVALID | Số lượng không phải số hợp lệ.
EN | INPUT_NUMBER_INVALID | Quantity must be a valid number.
VI | INPUT_NUMBER_OUT_OF_RANGE | Số lượng phải nằm trong khoảng 1 đến 100.
EN | INPUT_NUMBER_OUT_OF_RANGE | Quantity must be between 1 and 100.
VI | INPUT_NUMBER_INVALID | Số lượng không phải số hợp lệ.
EN | INPUT_NUMBER_INVALID | Quantity must be a valid number.
VI | OK | 10
EN | OK | 10
```

### Diễn giải kết quả

1. `""` là dữ liệu thiếu: code `INPUT_NUMBER_REQUIRED`. Với tiếng Việt, pattern yêu cầu nhập trường; với tiếng Anh, nhãn trường đứng trước câu `is required`.
2. `"abc"` không thể parse thành số: code `INPUT_NUMBER_INVALID`, không phụ thuộc locale của phản hồi.
3. `"150"` parse được thành `BigDecimal` nhưng vượt mức 100: code `INPUT_NUMBER_OUT_OF_RANGE`. `MessageFormat` điền hai giới hạn vào câu dịch; không hard-code câu tiếng Anh trong parser.
4. `"10x"` bắt đầu bằng tiền tố `10`, nhưng `ParsePosition` cho biết parser chưa đọc hết input: dùng cùng code sai cú pháp.
5. `"10"` là số hợp lệ, trả đối tượng decimal; chỉ khi hiển thị cho người dùng hoặc trao đổi theo schema khác mới chọn cách định dạng.

**Trong ví dụ, input locale và display locale tình cờ giống nhau.** Ở một hệ thống thật, có thể giữ hai biến khác nhau nếu người dùng nhập dữ liệu theo quy ước đã chọn trước đó nhưng muốn nhận thông báo bằng một ngôn ngữ khác. Điều quan trọng là xác định rõ hai hợp đồng, không tự suy chúng luôn giống nhau.

Lưu ý ví dụ dùng provider JDK thông thường mà `NumberFormat.getNumberInstance(...)` trả về `DecimalFormat`. Nếu xây thư viện yêu cầu hỗ trợ provider tùy biến, nên kiểm tra kiểu thực tế hoặc chọn một đường parse phù hợp khác thay vì cast không kiểm tra. Các chuỗi thử nghiệm ở đây không phụ thuộc dấu thập phân theo locale, nên output về code và các giá trị nguyên xác định.

## 7. Mã lỗi ổn định trong API

Nếu lỗi được trả qua HTTP/JSON, phản hồi nên tách rõ mã và văn bản hiển thị:

```json
{
  "code": "INPUT_NUMBER_INVALID",
  "message": "Số lượng không phải số hợp lệ.",
  "field": "quantity"
}
```

Cùng lỗi với locale `en-US`:

```json
{
  "code": "INPUT_NUMBER_INVALID",
  "message": "Quantity must be a valid number.",
  "field": "quantity"
}
```

Hai phản hồi có cùng `code` và `field`; chỉ `message` thay đổi. Đây là một **schema minh họa** của ứng dụng, không phải định dạng JSON bắt buộc do Java hoặc HTTP quy định.

Khách hàng API nên kiểm tra:

```java
switch (error.code()) {
    case "INPUT_NUMBER_REQUIRED" -> showRequiredState();
    case "INPUT_NUMBER_INVALID" -> highlightInvalidNumber();
    case "INPUT_NUMBER_OUT_OF_RANGE" -> showRangeHint();
    default -> showGenericError();
}
```

Đây là đoạn minh họa trong một phương thức với `error` và các hàm UI đã được định nghĩa; không phải chương trình độc lập. Không so sánh `message` để phân nhánh vì bản dịch có thể thay đổi.

### HTTP status không phải error code

Có thể chọn HTTP `400 Bad Request` cho đầu vào sai hoặc `422 Unprocessable Content` cho một số loại dữ liệu hợp lệ về cú pháp nhưng sai quy tắc nghiệp vụ, tùy hợp đồng API. Không có quy tắc bắt buộc tất cả hệ thống phải dùng cùng một mã trạng thái cho mọi loại validation. Khi đã công bố contract, cần dùng nhất quán.

Một status như 400 có thể bao gồm nhiều code. Ngược lại, một code công khai có thể được ánh xạ sang status khác trong các giao thức khác nhau (HTTP, CLI, batch), nếu tài liệu hóa rõ. Tránh gắn `"400"` vào bản dịch như một phần để client phải đọc và suy luận.

### Nhiều lỗi trong một request

Nếu một form có nhiều trường sai, một phản hồi có thể chứa danh sách:

```json
{
  "errors": [
    {
      "code": "INPUT_NUMBER_REQUIRED",
      "field": "quantity",
      "message": "Vui lòng nhập Số lượng."
    },
    {
      "code": "INPUT_DATE_INVALID",
      "field": "deliveryDate",
      "message": "Ngày giao hàng không hợp lệ."
    }
  ]
}
```

`INPUT_DATE_INVALID` trong ví dụ này là mã lỗi ứng dụng tự định nghĩa, không phải API Java. Trường `field` nên giữ định danh ổn định như `deliveryDate`, không thay bằng nhãn “Ngày giao hàng”. Nhãn dịch có thể được cung cấp riêng nếu UI cần.

Đừng suy rằng mọi lỗi đều có một field: lỗi liên trường (ví dụ ngày kết thúc trước ngày bắt đầu) có thể gắn với nhiều field hoặc với toàn form. Schema cần cho phép mô tả đúng trường hợp đó.

## 8. Chọn locale cho thông điệp lỗi

Để trả đúng ngôn ngữ, cần có **chính sách xác định Locale**:

- Ứng dụng có cài đặt ngôn ngữ người dùng: ưu tiên thiết lập đã xác thực nếu đó là quy tắc sản phẩm.
- Request HTTP có `Accept-Language`: có thể dùng làm tín hiệu thương lượng ngôn ngữ khi hợp đồng cho phép.
- Không có ngôn ngữ hợp lệ/được hỗ trợ: dùng locale fallback được sản phẩm công bố.
- API thuần máy-với-máy: có thể trả code ổn định và message ngôn ngữ mặc định, hoặc cho phép client tự hiển thị bản dịch; cần mô tả lựa chọn trong tài liệu.

`Accept-Language` có thể là danh sách ngôn ngữ kèm độ ưu tiên `q`, ví dụ `vi-VN,vi;q=0.9,en;q=0.7`. Đây **không phải** một language tag đơn lẻ: không truyền nguyên header đó vào `new Locale.Builder().setLanguageTag(...)` hoặc kỳ vọng `Locale.forLanguageTag(...)` đọc đúng danh sách. Java có `Locale.LanguageRange.parse(...)` và các phương thức `Locale.lookup(...)`/`Locale.filter(...)` để hỗ trợ lựa chọn locale từ danh sách có sẵn.

**Chỉ hỗ trợ những locale mà sản phẩm có tài nguyên phù hợp.** Một language tag đúng cú pháp không bảo đảm có bản dịch, và `ResourceBundle.getBundle(...)` có fallback riêng. Nên chọn `resolvedLocale` theo danh sách sản phẩm hỗ trợ trước, sau đó tra tài nguyên; nếu fallback xảy ra, có thể ghi nhận để giám sát độ đầy đủ bản dịch.

### Dùng cùng locale cho MessageFormat

Khi cần điền số hoặc ngày vào thông điệp:

```java
String pattern = bundle.getString("error.amount.max");
String message = new MessageFormat(pattern, displayLocale)
        .format(new Object[] {limit});
```

Đây là đoạn minh họa trong một phương thức, với `bundle`, `displayLocale` và `limit` được khai báo. Dùng `displayLocale` tường minh giúp các format element như `{0,number}` hoặc `{0,date}` được xử lý theo ngữ cảnh người đọc.

Không dùng `String.format` với default locale cho một pattern `MessageFormat`: hai API có cú pháp placeholder khác nhau (`%s` so với `{0}`), và một số cách xử lý ngôn ngữ/định dạng khác nhau.

### Cần phân biệt locale input và locale output

Một hệ thống nhập liệu có thể nhận:

- `inputLocale`: quy ước để parse chuỗi người dùng nhập, ví dụ số `1.234,50` theo tiếng Đức.
- `displayLocale`: ngôn ngữ để hiển thị thông báo, ví dụ tiếng Việt.
- `wireFormat`: schema dữ liệu gửi qua API, ví dụ decimal chuẩn `1234.50`.

Không được dùng cách viết localized message để suy `inputLocale` hoặc cách ghi số trong database. Mỗi mục đích có hợp đồng riêng.

## 9. Không biến exception thành thông điệp công khai

Một lỗi parser có thể phát sinh từ `NumberFormat.parse`, `LocalDate.parse`, `Integer.parseInt` hoặc validation nghiệp vụ. Những exception này có thể chứa thông tin kỹ thuật, chuỗi đầu vào hoặc chi tiết implementation không thích hợp để hiển thị.

Không nên làm:

```java
catch (Exception ex) {
    return ex.getMessage(); // Không phải thông điệp UX đã bản địa hóa.
}
```

Đây là anti-pattern minh họa trong một phương thức có kiểu trả về phù hợp; không phải ứng dụng đầy đủ.

Thay vào đó, phân loại lỗi **dự kiến** thành code ổn định, ghi log kỹ thuật có kiểm soát, rồi dịch code thành thông điệp thân thiện. Ví dụ:

```java
try {
    int quantity = Integer.parseInt(raw);
    // Áp dụng các kiểm tra miền giá trị tiếp theo.
} catch (NumberFormatException ex) {
    // Gán code INPUT_NUMBER_INVALID cho kết quả validation.
}
```

Đây là đoạn minh họa, giả định biến `raw` đã khai báo. Trong ứng dụng nhập số theo locale, `Integer.parseInt` chỉ phù hợp nếu grammar input được định nghĩa như vậy; không tự thay thế parser theo locale cho UI.

**Không bắt mọi `RuntimeException` rồi trả `INPUT_NUMBER_INVALID`.** Lỗi cấu hình, `NullPointerException` trong code, lỗi database và lỗi parse dữ liệu người dùng là những loại sự cố khác nhau. Nếu gom mọi lỗi nội bộ thành lỗi người dùng, việc vận hành mất tín hiệu và người dùng có thể bị yêu cầu “sửa đầu vào” dù hệ thống đang lỗi.

Đặc biệt, không gửi stack trace, tên lớp nội bộ, SQL statement hoặc thông tin nhạy cảm trong `message`. Dùng correlation ID/tracing khi cần để hỗ trợ tìm đúng log kỹ thuật.

## 10. Không ghi dữ liệu nhạy cảm vào code hoặc message

Một code nên ổn định và ít chiều thông tin:

```text
INPUT_NUMBER_INVALID
ACCOUNT_LOGIN_FAILED
DATE_OUT_OF_RANGE
```

Không tạo code động:

```text
INPUT_NUMBER_INVALID_USER_12345
INVALID_VALUE_4111111111111111
USER_PASSWORD_WRONG_AT_2026_10_28
```

Các ví dụ trên là **anti-pattern**, không phải mã lỗi được khuyến nghị. Gắn giá trị nhập hoặc danh tính người dùng vào code gây nổ số lượng code, tăng nguy cơ lộ dữ liệu cá nhân và làm khó thống kê.

Tương tự, thông báo có thể dùng placeholder nhưng chỉ điền dữ liệu người dùng nếu thực sự cần và đã được kiểm soát. Với thông tin như mật khẩu, token, số thẻ hoặc dữ liệu nhạy cảm, tốt hơn là **không phản chiếu giá trị** trong phản hồi. Thay vì “Giá trị [dữ liệu nhạy cảm] không hợp lệ”, dùng thông báo chung: “Giá trị nhập không hợp lệ.”

Một số trường hợp cũng cần chống lộ tình trạng tài khoản: ví dụ xác thực đăng nhập có thể dùng code/message chung để không xác nhận địa chỉ email nào tồn tại. Lựa chọn này là yêu cầu bảo mật, không phải vấn đề dịch câu chữ.

## 11. Quản lý vòng đời của mã lỗi

“Mã lỗi ổn định” không có nghĩa cả hệ thống mã lỗi không bao giờ được thêm hoặc thay đổi. Nó có nghĩa **mỗi code đã công bố có ý nghĩa rõ và không bị tái sử dụng tùy tiện**.

### Quy tắc thực tế

1. Chọn convention như `INPUT_*`, `AUTH_*`, `ORDER_*` hoặc cấu trúc `validation.number.invalid`; thống nhất một kiểu.
2. Viết mô tả rõ khi nào code xuất hiện và client nên làm gì.
3. Không đưa văn bản dịch, tên môi trường hoặc dữ liệu request vào code.
4. Khi sửa câu hiển thị mà ý nghĩa lỗi không đổi, **giữ code** và có thể giữ message key.
5. Khi ý nghĩa thay đổi đáng kể, cân nhắc **thêm code mới** và cập nhật client theo kế hoạch tương thích.
6. Tránh đổi chính tả code công khai chỉ để phù hợp tên class Java mới; code là hợp đồng API, không phải tên biến nội bộ.
7. Duy trì fallback cho client nhận code chưa biết (thường hiển thị thông báo lỗi chung và ghi log), không crash hoặc giả định enum phía client luôn có đủ mọi giá trị.

Ví dụ:

- `INPUT_NUMBER_INVALID` giữ nguyên khi người dịch đổi từ “không hợp lệ” sang “vui lòng nhập một số hợp lệ”.
- Nếu sản phẩm tách lỗi `INPUT_NUMBER_INVALID` thành lỗi “chứa chữ” và “dấu nhóm sai”, có thể thêm những code chuyên biệt nhưng cần tính đến client cũ. Có thể vẫn dùng code chung nếu client không cần phân biệt; không tăng số lượng code mà không có nhu cầu.
- Một code như `PAYMENT_REJECTED` không được dùng lại cho tình trạng hệ thống mất kết nối tới cổng thanh toán; hai tình huống cần cách xử lý khác nhau.

Mối quan hệ giữa **mã lỗi** và **message key** thường là ánh xạ một-một cho một câu chính, nhưng không bị bắt buộc. Một code có thể được trình bày bằng pattern khác nhau theo kênh UI (toast, email, form), miễn là không đổi hợp đồng nghiệp vụ. Nên có lớp trình bày kiểm soát sự lựa chọn đó, không cho client suy mã lỗi từ câu.

## 12. Cơ chế fallback và quản lý bản dịch

Tạo root bundle như `messages.properties` giúp `ResourceBundle` có nội dung để fallback. Tuy nhiên, root fallback là hành vi kỹ thuật, không phải bằng chứng một ngôn ngữ đã dịch đầy đủ.

Rủi ro thường gặp:

- `messages_vi.properties` thiếu key `error.number.outOfRange`; Java có thể lấy bản tiếng Anh từ `messages.properties`.
- Bản dịch thêm hoặc thiếu placeholder; `MessageFormat` có thể hiển thị `{2}` nguyên dạng nếu không có đối số hoặc output thiếu thông tin.
- Một bản dịch đổi ý nghĩa từ “không hợp lệ” thành “chưa nhập”, khiến người dùng được hướng dẫn sai loại thao tác cần sửa.
- Một số locale dùng dấu nháy đơn với ý nghĩa khác trong câu thông thường; `MessageFormat` cần quy tắc escape riêng.

Kiểm tra chất lượng nên gồm:

- So sánh key **được định nghĩa trong chính từng file** với tập key tham chiếu, không chỉ gọi `ResourceBundle.containsKey` vì fallback có thể che thiếu dịch.
- Kiểm tra pattern của mỗi locale bằng `new MessageFormat(pattern, locale)`.
- Kiểm tra số index và ý nghĩa placeholder theo hợp đồng, không bắt buộc thứ tự xuất hiện giống bản gốc.
- Kiểm tra câu ở giao diện thật: dài quá gây cắt chữ, thiếu ngữ cảnh, sai giọng văn, tên trường chưa dịch.
- Có policy khi bundle/khóa vắng mặt. Với lỗi cấu hình tài nguyên nội bộ, không giả vờ rằng người dùng đã nhập sai; nên dùng thông báo chung dự phòng có kiểm soát và theo dõi lỗi cấu hình.

Đối với Java 17+, tệp `.properties` do `PropertyResourceBundle` đọc qua byte stream có cơ chế ưu tiên UTF-8. Nên lưu các bản dịch UTF-8, kiểm thử dấu tiếng Việt và kiểm soát encoding trong pipeline build. Đừng trộn lẫn cách đọc `java.util.Properties.load(InputStream)` với hợp đồng encoding của `PropertyResourceBundle`.

## 13. Kiểm thử code ổn định và thông điệp đa ngôn ngữ

Một bộ test cho parser/validation nên tách hai nhóm.

### A. Kiểm tra phân loại lỗi (không phụ thuộc ngôn ngữ)

| Input | Kết quả mong đợi | Ý nghĩa |
| --- | --- | --- |
| `null` hoặc `""` | `INPUT_NUMBER_REQUIRED` | Thiếu giá trị |
| `"abc"` | `INPUT_NUMBER_INVALID` | Sai cú pháp số |
| `"10x"` | `INPUT_NUMBER_INVALID` | Parser chỉ đọc được tiền tố |
| `"150"` với max 100 | `INPUT_NUMBER_OUT_OF_RANGE` | Đúng kiểu, ngoài phạm vi |
| `"10"` | Thành công, không có error code | Giá trị hợp lệ |

Chạy lại bộ ca này với các locale đầu vào được hỗ trợ. Nếu cú pháp số giữa hai locale khác nhau, cung cấp input hợp lệ tương ứng; không yêu cầu cùng một chuỗi có dấu phân cách phải mang cùng giá trị trong mọi locale.

### B. Kiểm tra bản địa hóa thông điệp

Cùng kết quả `INPUT_NUMBER_INVALID`:

- Với `vi-VN`, thông điệp hiển thị bằng tiếng Việt và label trường được dịch.
- Với `en-US`, thông điệp hiển thị bằng tiếng Anh.
- **Code vẫn chính xác là `INPUT_NUMBER_INVALID`**, field vẫn là `quantity`.
- Nếu bản dịch đổi lời văn, những test xử lý nghiệp vụ không nên hỏng. Test i18n có thể kiểm tra pattern, key và placeholder độc lập hoặc kiểm tra nội dung trong test tích hợp theo chính sách sản phẩm.

Đừng viết test nghiệp vụ dùng `assertEquals("Số lượng không phải số hợp lệ.", response.getMessage())` để quyết định đã phân loại đúng lỗi. Cách đó trộn validation với copywriting; sửa câu trong resource sẽ làm test nghiệp vụ thất bại dù code đúng. Có thể có test localization riêng để bảo đảm bản dịch mong muốn được hiển thị, nhưng test đó phải có mục tiêu rõ.

### C. Kiểm tra fallback và trường hợp code chưa biết

Nếu dịch vụ trả code mới mà client cũ chưa nhận diện, client nên có xử lý mặc định an toàn. Nếu không tìm thấy message key ở một locale, chương trình không nên làm hỏng toàn bộ luồng validation. Đồng thời, sự thiếu dịch phải được ghi nhận để sửa ở pipeline.

### D. Kiểm tra dữ liệu nhạy cảm

Thử input dài hoặc chứa ký tự đặc biệt, script-like text, token giả lập. Đảm bảo không phản chiếu trực tiếp vào message nếu không cần và không làm tăng cardinality của code/metric. Kiểm tra mọi giá trị đưa vào HTML được escape theo tầng render; bản dịch đúng chưa có nghĩa output an toàn với mọi hệ thống UI.

## 14. Lỗi phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng câu tiếng Anh/tiếng Việt làm `errorCode` | Code đổi theo bản dịch và copywriting | Dùng định danh máy đọc ổn định |
| Dùng `message.equals(...)` để điều khiển UI | Đổi ngôn ngữ làm hỏng nhánh logic | Kiểm tra code và field identifier |
| Gắn giá trị người dùng vào tên code | Lộ dữ liệu, tăng số lượng mã không kiểm soát | Code từ tập định danh đã định nghĩa |
| Gửi thẳng `exception.getMessage()` cho người dùng | Có thể lộ chi tiết nội bộ, không được bản địa hóa | Ánh xạ lỗi dự kiến sang code và resource message |
| Gộp mọi exception thành `INPUT_INVALID` | Che mất bug, sự cố hệ thống và lỗi cấu hình | Phân biệt validation với lỗi nội bộ |
| Định nghĩa key chỉ dựa vào câu dịch gốc | Văn bản đổi làm ID bị sai nghĩa | Key biểu thị ý nghĩa tương đối ổn định |
| Không chú thích placeholder cho người dịch | Dịch sai tham số/giới hạn hoặc cú pháp | Ghi ý nghĩa `{0}`, `{1}` rõ ràng |
| Dùng default JVM Locale cho mọi request | Người dùng khác ngôn ngữ nhận câu không mong muốn | Xác định và truyền display locale tường minh |
| Parse nguyên `Accept-Language` như một tag | Header có danh sách và trọng số `q` | Thương lượng qua danh sách locale được hỗ trợ |
| Chỉ kiểm tra `getString(key)` không lỗi | Fallback có thể che thiếu dịch | So sánh tập key của từng locale |
| Dùng locale hiển thị để parse API số chuẩn | Cùng data có thể nhận giá trị khác nhau | Parse machine format theo schema, UI input theo input locale |
| Dùng `NumberFormat.parse(String)` là strict validator | Có thể chỉ đọc tiền tố `10` của `10x` | Kiểm tra `ParsePosition` và grammar |
| Cho phép client phân tích câu để biết giới hạn | Bản dịch và format số thay đổi | Trả dữ liệu cấu trúc nếu client cần min/max |
| Chỉ trả HTTP 400 không có mã lỗi | Client khó phân biệt loại lỗi | Trả stable error code theo contract |
| Coi message key chính là code vĩnh viễn | Tái tổ chức bundle có thể phá client | Ánh xạ code công khai sang key nội bộ |
| Thay code vì chỉnh một dấu câu | Phá tương thích không cần thiết | Giữ code khi ý nghĩa không đổi |

## 15. Bài tập thực hành

**Bài 1 — thiết kế contract.** Một trường `deliveryDate` có các lỗi “trống”, “sai cú pháp ngày” và “ngày trước hôm nay”. Hãy đề xuất ba code ổn định, ba message key và ví dụ thông điệp `vi-VN`/`en-US` tương ứng. Giải thích tại sao code không nên chứa dấu tiếng Việt hoặc chính câu dịch.

**Bài 2 — cùng lỗi, hai ngôn ngữ.** Với `INPUT_NUMBER_INVALID` và field `quantity`, viết hai file properties tạo câu tiếng Việt và tiếng Anh. Dùng `ResourceBundle`/`MessageFormat` để nhận message, nhưng giữ nguyên code trong phản hồi.

**Bài 3 — parser đọc tiền tố.** Người dùng nhập `"10kg"` trong ô chỉ chấp nhận số lượng. Vì sao `NumberFormat.parse("10kg")` có thể trả số? Hãy bổ sung `ParsePosition` để sinh code `INPUT_NUMBER_INVALID` khi còn phần dư.

**Bài 4 — fallback.** Tệp tiếng Việt thiếu `error.number.outOfRange` nhưng root bundle có key. Điều gì xảy ra khi gọi `getString`? Tại sao hoạt động của `ResourceBundle` không chứng minh bản dịch đã hoàn tất? Bạn sẽ kiểm tra thiếu dịch bằng cách nào?

**Bài 5 — API client.** Client nhận JSON có code `INPUT_NUMBER_OUT_OF_RANGE` và message tiếng Đức. Làm thế nào client vẫn xác định được field cần highlight và quy tắc xử lý mà không phân tích câu tiếng Đức?

**Bài 6 — bảo mật.** Một exception parse chứa nguyên chuỗi đầu vào có thông tin nhạy cảm. Hãy viết chính sách thông báo/lưu log thích hợp và giải thích vì sao không nên nhúng input vào error code hoặc message mặc định.

**Bài 7 — thay đổi theo phiên bản.** Nhóm dịch sửa một câu từ “không hợp lệ” thành “vui lòng nhập giá trị hợp lệ”. Bạn cần đổi code không? Nếu quy tắc nghiệp vụ mới phân biệt hai lỗi khác nhau và client cần xử lý riêng, bạn sẽ bổ sung code theo cách nào để không làm hỏng client cũ?

## 16. Ghi nhớ

**Thông báo lỗi là nội dung dành cho con người; mã lỗi là hợp đồng dành cho máy.** Hãy phân tích và xác thực đầu vào để tạo ra loại lỗi ổn định như `INPUT_NUMBER_INVALID`, rồi ánh xạ loại lỗi ấy sang message key và tạo câu hiển thị bằng `ResourceBundle` + `MessageFormat` theo `Locale` đã chọn.

Một cách tổ chức hiệu quả tách các lớp:

```text
Parse/validate -> stable error code
Stable code    -> message key + parameters
Message key    -> ResourceBundle(displayLocale)
Pattern        -> MessageFormat(displayLocale)
Response       -> stable code + localized message + stable metadata
```

Khi thay đổi ngôn ngữ, câu chữ có thể thay đổi còn code vẫn giữ nguyên. Khi thay đổi quy tắc nghiệp vụ, hãy đánh giá có cần code mới hay không thay vì tái sử dụng code cũ cho ý nghĩa khác. Và khi parse số/ngày theo locale, đừng bỏ qua kiểm tra phần dư, grammar, miền giá trị hoặc hệ thống fallback bản dịch.

**Quy tắc cốt lõi:** *Máy dựa vào code; người dùng đọc message. Cả hai phải phản ánh cùng một lỗi, nhưng không phụ thuộc vào nhau về ngôn ngữ.*

### Tài liệu API tham khảo

- [`ResourceBundle` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [`MessageFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html)
- [`NumberFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [`ParsePosition` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html)
