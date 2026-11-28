# Safe serialization

## 1. Serialization an toàn bắt đầu từ hợp đồng đầu ra

Serialization là chuyển dữ liệu có cấu trúc thành một biểu diễn có thể truyền hoặc lưu, chẳng hạn chuyển một đối tượng Java thành JSON. Trong chương Output encoding, vấn đề cần giải quyết là dữ liệu giữ nguyên vai trò dữ liệu khi đi qua ranh giới đầu ra, thay vì trở thành cú pháp hay mã ngoài ý muốn.

Ví dụ, tiêu đề khóa học có thể chứa dấu nháy, xuống dòng, ký hiệu `<` hoặc tiếng Việt. Một serializer JSON xử lý các ký tự đó theo cú pháp JSON. Nhưng nếu toàn bộ JSON lại được ghép vào một trang HTML, một parser khác xuất hiện. “Đã serialize thành JSON” không tự chứng minh “có thể đưa vào mọi vị trí trên trang”.

Trong module yêu cầu bảo mật, hợp đồng safe serialization cần trả lời đồng thời:

- Đối tượng nào và những trường nào được phép công bố cho người nhận?
- Kiểu dữ liệu, miền giá trị và ý nghĩa của từng trường được giữ như thế nào?
- Biểu diễn sẽ đi tới JSON parser, HTML parser hay một ngữ cảnh khác?
- Khi serialize thất bại hoặc dữ liệu vượt giới hạn, hệ thống hành xử ra sao?
- Bằng chứng nào xác nhận đầu ra vừa đúng cấu trúc, vừa đúng quyền và đúng nơi sử dụng?

Một thư viện serialization giải quyết một phần quan trọng của hợp đồng này. Các quyết định về phân quyền, chọn trường và đích sử dụng vẫn thuộc thiết kế ứng dụng.

Bài này tập trung vào JSON đầu ra của ứng dụng web Java và việc đưa dữ liệu tới trình duyệt. Native Java object serialization và việc khôi phục object graph từ nguồn không tin cậy là phạm vi khác; không bật cơ chế deserialization tùy ý để phục vụ những ví dụ dưới đây.

## 2. Năm thuộc tính của một đường serialization có thể kiểm chứng

| Thuộc tính | Câu hỏi | Ví dụ lỗi cần ngăn |
| --- | --- | --- |
| Đúng cú pháp | Đầu ra có thuộc định dạng đã công bố không? | Dấu nháy trong tiêu đề làm hỏng JSON ghép tay |
| Đúng ý nghĩa | Bên nhận có giữ được kiểu và giá trị quan trọng không? | ID lớn bị làm tròn khi đọc thành JavaScript Number |
| Đúng quyền công bố | Có chỉ những trường mà người nhận được xem không? | Serialize entity làm lộ token hoặc ghi chú nội bộ |
| Đúng ngữ cảnh | Biểu diễn có phù hợp parser tiếp theo không? | JSON hợp lệ kết thúc một phần tử `script` trong HTML |
| Có giới hạn và hành vi lỗi | Có giới hạn kích thước và lỗi rõ ràng không? | Response dở dang hoặc fallback bằng `toString()` |

Ví dụ hợp đồng cho thẻ khóa học có thể chỉ công bố `courseId`, `title`, `summary`, `lessonCount`, `publishedAt`. Đây là một lựa chọn về quyền dữ liệu trước khi bàn tới escape. Việc một trường riêng tư được escape chính xác không làm cho công bố trường đó trở nên hợp lệ.

Tương tự, JSON syntax không mô tả ý nghĩa của ID, múi giờ hay số đếm. Đội thiết kế phải chốt các ý nghĩa này để Java, trình duyệt và các dịch vụ khác không diễn giải cùng một payload theo cách khác nhau.

## 3. Dùng serializer cho cấu trúc, không ghép chuỗi JSON

### 3.1. Vì sao ghép tay dễ phá vỡ cấu trúc?

```java
// Ví dụ cần tránh.
String json = "{\"title\":\"" + title + "\"}";
```

Nếu `title` có dấu nháy hoặc backslash, nội dung có thể kết thúc string đang được dựng. Thêm một lệnh thay dấu nháy không giải quyết toàn bộ cú pháp chuỗi, ký tự điều khiển, null và các kiểu dữ liệu khác.

Thay vào đó, tạo một DTO có trường rõ ràng rồi đưa DTO cho serializer. Không tạo JSON từ `Map.toString()`, không ghép kết quả `toString()` của entity, và không yêu cầu client gửi sẵn một đoạn “JSON đã escape” để server chép nguyên vào response.

JSON có quy tắc riêng cho string, number, boolean, null, object và array. Media type của nó là `application/json`; JSON trao đổi giữa các hệ thống phải dùng UTF-8. Tên thành viên object nên duy nhất, vì các parser có thể xử lý tên lặp khác nhau. [RFC 8259: định dạng JSON và khả năng tương tác](https://www.rfc-editor.org/rfc/rfc8259.html).

### 3.2. Chọn dữ liệu trước khi serialize

Giả sử entity nội bộ có các trường sau:

```text
CourseEntity
  id
  title
  summary
  lessonCount
  publishedAt
  tenantId
  authorPrivateEmail
  moderationNotes
  unpublishedLessonIds
```

Trang danh sách công khai không cần biết toàn bộ entity. Một DTO nhỏ giúp reviewer thấy ngay tập dữ liệu có thể xuất hiện ở response, đồng thời giảm nguy cơ một getter mới của entity vô tình trở thành trường API.

Luồng thiết kế nên là:

```text
Xác định người nhận và đối tượng được phép xem
→ chọn các trường theo contract response
→ kiểm tra kiểu, miền và giới hạn
→ tạo DTO
→ serialize theo đích cụ thể
→ truyền hoặc render bằng cơ chế đã quy định
```

DTO không thay thế kiểm tra quyền truy cập khóa học. Nó giúp giới hạn trường sau khi ứng dụng đã xác định đúng đối tượng và quyền của người nhận.

## 4. JSON qua HTTP và JSON nằm trong HTML là hai đích khác nhau

| Đích | Parser đầu tiên liên quan | Contract đầu ra cần có |
| --- | --- | --- |
| HTTP API JSON | JSON parser của bên nhận | JSON hợp lệ, UTF-8, media type đúng và schema rõ |
| Data block `script type="application/json"` trong HTML | HTML parser trước, JSON parser sau | Cả JSON hợp lệ và không phá ranh giới phần tử HTML |
| JSON đặt trong một HTML attribute | HTML attribute parser trước | Biểu diễn thuộc tính HTML đúng, sau đó mới parse JSON |
| Nội dung được gán vào phần tử văn bản bằng DOM | DOM text API | Dùng giá trị sau parse như văn bản, không dựng HTML |
| JavaScript code được ghép từ JSON | HTML và JavaScript có thể cùng tham gia | Tránh thiết kế này nếu chỉ cần chuyển dữ liệu |

Một API JSON độc lập có thể chứa literal `<` trong string mà vẫn đúng JSON. Nhưng khi chép cùng biểu diễn vào HTML source, ứng dụng phải xét thêm ranh giới HTML. Thư viện được chọn vì đáp ứng JSON không đồng nghĩa nó mặc định bảo vệ mọi vị trí lồng trong HTML.

### 4.1. Kiểu `application/json` không xóa ranh giới đóng thẻ

Mẫu dưới đây không an toàn nếu `RAW_JSON` chỉ được tạo bằng serializer JSON thông thường:

```html
<!-- Ví dụ vị trí chèn cần có serializer dành cho đích HTML. -->
<script id="course-data" type="application/json">RAW_JSON</script>
```

Phần tử data block không thực thi nội dung như JavaScript, nhưng HTML parser vẫn xác định nơi phần tử kết thúc. Một giá trị string chứa chuỗi đóng thẻ `script` có thể làm thay đổi cây HTML nếu xuất hiện nguyên dạng trong nguồn trang. Dấu nháy JSON không ngăn được parser HTML làm việc trước. [WHATWG HTML: nội dung phần tử script](https://html.spec.whatwg.org/multipage/scripting.html#restrictions-for-contents-of-script-elements).

Một cách kiểm soát cho đúng data block này là để serializer biểu diễn mọi literal `<` trong tên trường và giá trị string thành JSON Unicode escape `\u003C`. Khi đọc bằng `JSON.parse`, giá trị dữ liệu được khôi phục; trong HTML source không còn literal `<` từ chuỗi dữ liệu để bắt đầu một thẻ. Có thể bổ sung escape `>` và `&` theo policy của ứng dụng.

Đây là hợp đồng cho JSON trong nội dung data block, không phải encoder dùng chung cho HTML attribute, CSS hay URL. Không mang helper của vị trí này đi gắn vào một vị trí khác chỉ vì đầu ra “đã escape”.

### 4.2. Không HTML-encode toàn bộ JSON trong data block

Trong data block `script`, HTML character references không được xử lý như nội dung văn bản HTML thông thường. Biến mọi dấu nháy JSON thành `&quot;` có thể làm nội dung không còn parse được như JSON mong muốn. Phải chọn cơ chế biểu diễn theo parser của vị trí chèn, thay vì dùng HTML encoding cho mọi loại dữ liệu.

Phương án ưu tiên khi phù hợp kiến trúc là để trình duyệt gọi endpoint JSON riêng. Khi đó không cần lồng JSON vào HTML source. Nếu cần dữ liệu khởi tạo trong HTML để đáp ứng yêu cầu tải trang, cần một helper có tên, contract và phạm vi sử dụng rõ ràng.

## 5. Ví dụ Java: hai writer cho hai contract

Ví dụ sau dùng Java 17 và API Jackson 2.x thuộc các package `com.fasterxml.jackson.*`. Đây là mã minh họa cho ứng dụng có dependency tương ứng; không yêu cầu thay cấu hình build của module học tập. Các phiên bản thư viện phải theo danh mục đã được dự án duyệt.

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.SerializableString;
import com.fasterxml.jackson.core.io.CharacterEscapes;
import com.fasterxml.jackson.core.io.SerializedString;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;

public final class CourseJson {
    public record CourseView(
            String courseId,
            String title,
            String summary,
            int lessonCount,
            String publishedAt
    ) {}

    private static final ObjectWriter API_WRITER =
            new ObjectMapper().writerFor(CourseView.class);

    private static final ObjectWriter HTML_DATA_WRITER = createHtmlDataWriter();

    public static String forApi(CourseView view) throws JsonProcessingException {
        return API_WRITER.writeValueAsString(view);
    }

    public static String forHtmlDataBlock(CourseView view)
            throws JsonProcessingException {
        return HTML_DATA_WRITER.writeValueAsString(view);
    }

    private static ObjectWriter createHtmlDataWriter() {
        JsonFactory factory = new JsonFactory();
        factory.setCharacterEscapes(new HtmlDataEscapes());
        ObjectMapper mapper = new ObjectMapper(factory);
        return mapper.writerFor(CourseView.class);
    }

    private static final class HtmlDataEscapes extends CharacterEscapes {
        private static final SerializableString LESS_THAN =
                new SerializedString("\\u003C");
        private static final SerializableString GREATER_THAN =
                new SerializedString("\\u003E");
        private static final SerializableString AMPERSAND =
                new SerializedString("\\u0026");

        private final int[] ascii;

        private HtmlDataEscapes() {
            ascii = CharacterEscapes.standardAsciiEscapesForJSON();
            ascii['<'] = ESCAPE_CUSTOM;
            ascii['>'] = ESCAPE_CUSTOM;
            ascii['&'] = ESCAPE_CUSTOM;
        }

        @Override
        public int[] getEscapeCodesForAscii() {
            return ascii;
        }

        @Override
        public SerializableString getEscapeSequence(int ch) {
            return switch (ch) {
                case '<' -> LESS_THAN;
                case '>' -> GREATER_THAN;
                case '&' -> AMPERSAND;
                default -> null;
            };
        }
    }

    private CourseJson() {}
}
```

`CharacterEscapes.standardAsciiEscapesForJSON()` cung cấp bản sao bảng escape JSON chuẩn để bổ sung policy. Cơ chế tùy chỉnh áp dụng cho tên trường và giá trị string; không cần viết lại thuật toán serializer. Factory được cấu hình trước khi tạo writer và không bị thay đổi theo từng request. [Jackson: CharacterEscapes](https://raw.githubusercontent.com/FasterXML/jackson-core/2.20/src/main/java/com/fasterxml/jackson/core/io/CharacterEscapes.java), [Jackson: JsonFactory](https://raw.githubusercontent.com/FasterXML/jackson-core/2.20/src/main/java/com/fasterxml/jackson/core/JsonFactory.java).

Ví dụ dữ liệu đã qua kiểm tra contract và quyền:

```java
CourseJson.CourseView view = new CourseJson.CourseView(
        "9007199254740993",
        "A < B & \"Java\"",
        "Hai dòng:\nTiếng Việt và emoji 👩‍💻",
        12,
        "2026-11-27T01:00:00Z"
);

String apiBody = CourseJson.forApi(view);
String htmlData = CourseJson.forHtmlDataBlock(view);
```

`apiBody` dành cho response JSON độc lập. `htmlData` chỉ dành cho nội dung của data block cố định mà helper đã công bố. Hai biểu diễn có thể khác byte nhưng phải khôi phục cùng giá trị trường sau parse.

DTO trong ví dụ chỉ mô tả hình dạng đầu ra. Nó không tự kiểm tra title dài bao nhiêu, `lessonCount` có âm không hoặc `publishedAt` có đúng quy tắc thời gian không. Service tạo DTO phải thực hiện các kiểm tra đó theo contract trước khi gọi writer.

Không cho dữ liệu request điều khiển `CharacterEscapes`, tên class, kiểu DTO hay lựa chọn serializer. Chọn writer theo đích do ứng dụng kiểm soát, không theo một cờ “trusted” do client gửi.

## 6. Đưa dữ liệu tới trình duyệt mà giữ đúng vai trò dữ liệu

### 6.1. Phương án endpoint JSON riêng

Response thành công của ví dụ có các đặc tính sau:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Content-Type-Options: nosniff
Cache-Control: private, no-store

{"courseId":"9007199254740993","title":"Khóa học Java","summary":"Nền tảng","lessonCount":12,"publishedAt":"2026-11-27T01:00:00Z"}
```

Policy cache ở đây giả định response dành riêng cho người đã đăng nhập; đây là lựa chọn của tình huống, không phải quy định chung cho mọi JSON API. Một danh mục thực sự công khai có thể cần policy cache khác sau khi đã xác định rõ dữ liệu nào được công bố.

`nosniff` yêu cầu kiểm tra media type cho các đích tải như script hoặc stylesheet theo Fetch; nó không xác thực schema JSON và không bảo vệ những lần ứng dụng tự đưa dữ liệu vào `innerHTML`. [Fetch Standard: X-Content-Type-Options](https://fetch.spec.whatwg.org/#x-content-type-options-header).

Mã client dùng giá trị đã parse làm văn bản:

```javascript
async function loadCourse(courseId, titleElement, summaryElement) {
  if (typeof courseId !== "string" || !/^[1-9][0-9]{0,18}$/.test(courseId)) {
    throw new TypeError("Invalid course ID");
  }

  const response = await fetch(
    `/api/courses/${encodeURIComponent(courseId)}/card`,
    { headers: { Accept: "application/json" } }
  );

  if (!response.ok) {
    throw new Error("Course data unavailable");
  }
  const mediaType = (response.headers.get("Content-Type") ?? "")
    .split(";", 1)[0].trim().toLowerCase();
  if (mediaType !== "application/json") {
    throw new TypeError("Unexpected response type");
  }

  const data = await response.json();
  if (data === null || typeof data !== "object" || Array.isArray(data)
      || typeof data.title !== "string"
      || typeof data.summary !== "string"
      || data.courseId !== courseId
      || !Number.isInteger(data.lessonCount)
      || data.lessonCount < 0 || data.lessonCount > 10000) {
    throw new TypeError("Unexpected course payload");
  }
  if ([...data.title].length > 200 || [...data.summary].length > 2000) {
    throw new TypeError("Course text exceeds contract");
  }

  titleElement.textContent = data.title;
  summaryElement.textContent = data.summary;
}
```

Miền ID, số lượng bài và độ dài trong đoạn mã là chính sách mẫu của bài học. Client kiểm tra một phần contract cần dùng để bảo vệ đường hiển thị; server vẫn chịu trách nhiệm chính về dữ liệu và quyền truy cập. Kiểm tra kích thước string sau parse không thay giới hạn response ở server hay giới hạn tài nguyên của đường nhận.

Không dùng `eval` để đọc JSON. Cũng không thay `textContent` bằng `innerHTML` để “giữ định dạng” tiêu đề. Sau bước parse, chuỗi lại là giá trị dữ liệu gốc; cách sử dụng tiếp theo vẫn phải phù hợp ngữ cảnh đích.

### 6.2. Phương án data block khởi tạo trong HTML

Nếu ứng dụng cần gửi dữ liệu ngay trong trang, một helper hẹp có thể tạo phần tử cố định bằng đầu ra đúng writer:

```java
String dataBlock = "<script id=\"course-data\" type=\"application/json\">"
        + CourseJson.forHtmlDataBlock(view)
        + "</script>";
```

Chỉ đầu ra của helper có contract này mới được chèn nguyên dạng ở vị trí tương ứng trong template. Không dùng nó làm cớ tắt auto-escaping cho dữ liệu khác, và không cho input điều khiển tên thẻ hoặc thuộc tính của data block.

Client đọc dữ liệu, không thực thi nó:

```javascript
const node = document.getElementById("course-data");
if (!(node instanceof HTMLScriptElement) || node.type !== "application/json") {
  throw new TypeError("Missing course data block");
}

const course = JSON.parse(node.textContent);
// Áp dụng validation theo schema trước khi dùng các trường.
// Khi hiển thị title/summary, dùng textContent trên phần tử văn bản.
```

Không chép `node.textContent` vào một thẻ script thực thi, không chuyển qua `eval`, và không decode escape bằng một helper riêng trước `JSON.parse`. Parser JSON thực hiện việc khôi phục escape của định dạng.

Mẫu này chỉ công bố một bản chụp dữ liệu cần cho giao diện. Các quyết định nhạy cảm như học viên có được đăng ký hay truy cập bài học vẫn phải được server kiểm tra ở request thực hiện hành động; không lấy data block client làm nguồn quyền.

## 7. Bảo toàn ý nghĩa dữ liệu giữa Java và JavaScript

### 7.1. ID lớn cần một contract không làm mất giá trị

JSON number không mang thông tin rằng số đó là Java `long`. Trình duyệt thường dùng JavaScript Number, nên số nguyên lớn có thể không giữ được chính xác. RFC 8259 nêu miền số nguyên từ `-(2^53)+1` đến `(2^53)-1` cho khả năng tương tác chính xác giữa các triển khai dùng binary64. [RFC 8259: numbers](https://www.rfc-editor.org/rfc/rfc8259.html#section-6).

Với hệ thống có ID lớn hơn miền đó, quy định ID là chuỗi thập phân xuyên suốt API và client. Không serialize ID thành number rồi ép sang string sau khi trình duyệt đã làm tròn. Trong ví dụ, `"9007199254740993"` là một identifier dạng string, không phải giá trị để tính toán.

Yêu cầu cần chỉ rõ cả schema lẫn hành vi client: ID được giữ dưới dạng string khi so sánh, tạo request và lưu state. Chỉ sửa serializer server nhưng để client gọi `Number(courseId)` vẫn làm mất hợp đồng.

### 7.2. Không để giá trị đặc biệt âm thầm đổi ý nghĩa

Trong JavaScript, `JSON.stringify` có các quy tắc như bỏ một thuộc tính object có giá trị `undefined`, biểu diễn `NaN` và vô cực thành `null`, hoặc báo lỗi với BigInt theo cơ chế mặc định nếu không có chuyển đổi tùy chỉnh. Vì vậy serializer thành công không đồng nghĩa dữ liệu nghiệp vụ vẫn đúng. [ECMAScript: JSON.stringify](https://tc39.es/ecma262/multipage/structured-data.html#sec-json.stringify).

Đối với ví dụ khóa học, `lessonCount` không thể là `null` hoặc một số phân số. Service phải tính toán và kiểm tra nó trước khi tạo DTO. Nếu một bước trung gian JavaScript sinh giá trị không hữu hạn, đó là lỗi cần xử lý theo contract, không phải một giá trị được phép chuyển âm thầm thành thiếu dữ liệu.

### 7.3. Ngày giờ, null và trường bị thiếu phải được định nghĩa

Một contract mẫu có thể chốt:

| Trường | Quy ước của ví dụ | Lý do |
| --- | --- | --- |
| `courseId` | String gồm chữ số, giữ nguyên giá trị | Tránh thay đổi ID qua kiểu số client |
| `title` | String bắt buộc, tối đa 200 code point | Kiểm soát dữ liệu hiển thị và kích thước |
| `summary` | String bắt buộc, tối đa 2000 code point; rỗng được phép | Phân biệt không có mô tả với lỗi thiếu trường |
| `lessonCount` | Integer 0–10000 | Miền của trang thẻ khóa học mẫu |
| `publishedAt` | String thời điểm chuẩn hóa theo UTC; trạng thái chưa công bố dùng endpoint khác | Tránh ngầm đoán múi giờ hoặc nhiều ý nghĩa của null |

Không nên tự chuẩn hóa Unicode trên mọi trường mà không xét nghiệp vụ. Với nội dung hiển thị, cần giữ chữ Việt và emoji theo contract; với mã định danh, cần quy tắc riêng. Serializer không phải nơi âm thầm sửa tên hoặc thay ID cho “đẹp”.

Các ngưỡng trong bảng là lựa chọn để minh họa cách đặc tả. Khi dùng trong dự án thật, phải thống nhất với giới hạn lưu trữ, giao diện và các consumer đã có, thay vì sao chép một bộ số rồi coi đó là tiêu chuẩn chung.

## 8. Chỉ serialize một lần tại đúng ranh giới

Một lỗi tích hợp phổ biến là serialize DTO thành string, sau đó đưa string đó cho tầng HTTP vốn đã tự serialize:

```text
DTO {title: "Java"}
→ serialize thành text JSON
→ framework serialize text đó như một JSON string
→ client nhận string, không nhận object mong muốn
```

Trong một framework có JSON converter, thường trả DTO để converter thực hiện một lần. Nếu chủ động ghi byte JSON, phải cấu hình response theo đường ghi raw JSON tương ứng và không để một converter khác bọc tiếp.

Tương tự, không HTML-encode title trước khi đưa vào DTO dùng cho API. Client có thể nhận chữ `&lt;` thay vì ký hiệu `<` thật. Mỗi ranh giới có cơ chế biểu diễn riêng; dữ liệu lưu trữ và DTO nghiệp vụ không nên chứa escape của một đích trình bày cố định.

Không tự động decode lặp lại cho tới khi “hết escape”. Ví dụ một người dùng có thể thực sự muốn viết sáu ký tự `\u003C` trong nội dung hướng dẫn. JSON parser phải khôi phục đúng chuỗi theo một lần parse, chứ ứng dụng không được tiếp tục biến nội dung đó thành ký tự khác ngoài contract.

## 9. Giới hạn và xử lý lỗi là một phần của yêu cầu

Safe serialization cần quy định giới hạn ở mô hình dữ liệu và luồng xuất, không chỉ dựa vào việc thư viện có ném exception hay không. Với trang thẻ khóa học mẫu, có thể chốt tối đa 100 thẻ trong một response, giới hạn độ dài từng trường và giới hạn kích thước body sau UTF-8 theo ngân sách của endpoint.

Đối với response nhỏ, ứng dụng có thể hoàn tất serialization trong bộ đệm giới hạn trước khi cam kết response thành công. Khi có lỗi, trả error contract thống nhất; không trả một nửa object rồi nối thông báo lỗi vào cuối. Đối với dữ liệu lớn cần streaming, phải thiết kế riêng định dạng, cách phát hiện dữ liệu chưa hoàn tất và hành vi client khi bị ngắt.

Không dùng các fallback như:

```java
// Ví dụ cần tránh.
try {
    return writer.writeValueAsString(value);
} catch (Exception failure) {
    return value.toString();
}
```

Fallback này làm đầu ra không còn tuân định dạng đã công bố và có thể đưa thêm chi tiết nội bộ tới người nhận. Một lỗi serialization không cấp quyền công bố representation chẩn đoán của object.

Quan sát lỗi nên ghi mã sự kiện, endpoint, correlation ID và thông tin kỹ thuật cần thiết theo policy log. Không ghi nguyên DTO chứa thông tin cá nhân hoặc bí mật vào log chỉ để xem ký tự nào làm lỗi. Đường hiển thị thông báo lỗi cũng cần dùng API hoặc template phù hợp ngữ cảnh.

## 10. Đặc tả bộ yêu cầu bảo mật cho tình huống

| ID | Yêu cầu mẫu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-SER-01 | Mỗi endpoint chỉ serialize DTO đã định nghĩa; không xuất entity hoặc object tùy ý | Schema response và đối chiếu tập trường thực tế |
| SR-SER-02 | Mọi JSON output được tạo bằng serializer của dự án; không ghép cấu trúc JSON bằng chuỗi dữ liệu | Kiểm tra các đường ghi response và fixture chứa ký tự đặc biệt |
| SR-SER-03 | API JSON dùng UTF-8, `application/json` và `nosniff` theo policy endpoint | Kiểm tra header, byte body và xử lý phía client |
| SR-SER-04 | JSON trong data block HTML dùng writer dành riêng cho đích đó; dữ liệu không sinh literal `<` trong phần JSON source | Kiểm tra source trang, DOM sau parse và JSON khôi phục |
| SR-SER-05 | Client đọc bằng JSON parser và đưa title/summary vào text sink; không eval hoặc dựng HTML từ các trường đó | Kiểm tra đường từ response đến DOM |
| SR-SER-06 | ID lớn được công bố và sử dụng như string; không qua chuyển đổi Number | Ca có ID vượt miền số nguyên chính xác của client |
| SR-SER-07 | Độ dài, miền số, số phần tử và kích thước response có giới hạn đã chốt | Ca biên và vượt giới hạn tại service/endpoint |
| SR-SER-08 | Lỗi serialization không trả representation dự phòng hoặc dữ liệu nội bộ | Ca mô phỏng writer thất bại và kiểm tra error contract |
| SR-SER-09 | Tập trường công bố không thay đổi khi entity nội bộ được thêm getter | Ca hồi quy kiểm tra allowlist trường DTO |
| SR-SER-10 | Kết quả serialize chỉ được dùng tại đích mà helper công bố | Danh mục helper, consumer và vị trí chèn template |

Các yêu cầu này cần được liên kết với mô hình đe dọa. Ví dụ SR-SER-01 và 09 xử lý nguy cơ công bố quá mức; SR-SER-04 và 05 giữ dữ liệu khỏi trở thành cấu trúc trang; SR-SER-06 giữ nguyên định danh khi đi qua các runtime; SR-SER-07 và 08 giới hạn ảnh hưởng khi dữ liệu hoặc hệ thống gặp lỗi.

Một yêu cầu chỉ ghi “dùng Jackson” không đủ để thay các yêu cầu trên. Cùng một thư viện có thể được dùng với entity quá rộng, writer sai đích hoặc cấu hình thay đổi giữa các request.

## 11. Thiết kế ca nghiệm thu theo thuộc tính cần bảo vệ

Phần này mô tả cách xác minh một triển khai sản phẩm; không khẳng định các kiểm thử đã được thực thi trong bài học.

### 11.1. Fixture nội dung và kiểu dữ liệu

| Dữ liệu | Thuộc tính được kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Tiêu đề chứa `"` và backslash | JSON syntax và round-trip | Parse được, khôi phục đúng nội dung |
| Mô tả có newline, tab | Chuỗi có ký tự điều khiển hợp lệ | Serializer tạo escape đúng và parser khôi phục đúng |
| Chữ Việt, emoji ngoài BMP | Unicode và byte UTF-8 | Không mất ký tự hoặc cắt đôi nội dung |
| Chuỗi literal `\u003C` | Không decode dư | Vẫn là chuỗi người dùng đã cung cấp sau một lần parse |
| Chuỗi chứa thẻ đóng `script` | Ranh giới data block HTML | Không sinh phần tử HTML ngoài dự kiến |
| Chuỗi có `<`, `>`, `&` | Policy writer HTML data | JSON source theo escape đã chốt, giá trị khôi phục vẫn đúng |
| ID `9007199254740993` | Bảo toàn định danh | Nhận đúng string, không làm tròn |
| `lessonCount` âm hoặc phân số ở tầng nguồn | Miền dữ liệu | Bị chặn trước khi tạo response thành công |
| Trường bắt buộc bị thiếu hoặc null | Schema | Hành vi lỗi theo contract, không tự đổi thành chuỗi `"null"` |
| Summary vượt 2000 code point | Giới hạn ví dụ | Từ chối hoặc xử lý theo policy đã định; không cắt ngầm |

Không cần dùng payload thực thi mã để chứng minh ranh giới HTML. Có thể dùng fixture chứa `</script><div id="serialization-marker">marker</div>` và xác minh không có phần tử `serialization-marker` được tạo từ dữ liệu. Chuỗi này phải xuất hiện như dữ liệu sau JSON parse, nếu phù hợp miền nội dung của trường.

### 11.2. Kiểm tra nghĩa thay vì chỉ so sánh byte

Hai JSON string có thể khác cách escape mà khôi phục cùng giá trị. Với ví dụ hai writer, tiêu chí quan trọng là DTO sau parse có cùng các trường được công bố. Không bắt buộc API writer và HTML data writer trả cùng chuỗi byte.

Ngược lại, chỉ so sánh object sau parse chưa chứng minh HTML containment. Với data block cần thêm kiểm tra document sau HTML parse: số lượng data block đúng, không sinh phần tử từ marker, không xuất hiện script mới, và client đọc được JSON từ đúng phần tử đã định.

Đối với quyền dữ liệu, fixture phải cố tình tạo entity nguồn có email riêng, ghi chú kiểm duyệt và trường nội bộ có giá trị dễ nhận diện. Response DTO không được chứa tên hoặc giá trị các trường đó. Escape hoàn hảo vẫn là FAIL nếu dữ liệu ngoài quyền được công bố.

### 11.3. Kiểm tra toàn bộ đường tích hợp

Một kiểm tra unit cho writer không nhìn thấy việc reverse proxy đổi media type, template escape thêm một lần hoặc framework bọc JSON string. Cần ca tích hợp cho endpoint và trang dùng data block, với các tiêu chí:

- Header và body thực tế tuân contract của đúng endpoint.
- Client nhận object đúng schema thay vì string bị serialize hai lần.
- Dữ liệu chỉ tới các sink đã định trong giao diện.
- Lỗi trước khi response thành công không lộ stack trace hoặc DTO nội bộ.
- Response dành riêng cho người dùng không bị chia sẻ qua cache trái policy.

Mỗi ca cần chỉ ra yêu cầu tương ứng và kết quả quan sát, thay vì chỉ ghi “payload không chạy”. Mục tiêu bao gồm cả tính toàn vẹn của dữ liệu và quyền công bố, không chỉ một biểu hiện XSS.

## 12. Những giả định dễ làm sai thiết kế

**“JSON.stringify cũng là HTML encoder.”** Nó tạo biểu diễn JSON theo ngữ nghĩa JavaScript; đầu ra chưa có hợp đồng cho mọi vị trí HTML. Phải xác định parser bao ngoài hoặc dùng endpoint JSON riêng.

**“Parse JSON xong thì nội dung đã sạch.”** Parser tạo giá trị dữ liệu. Nếu đưa một string đó vào HTML sink hoặc một ngữ cảnh thực thi, ứng dụng mở thêm ranh giới mới cần bảo vệ.

**“Ẩn nút trên UI đủ để bảo vệ field nhạy cảm.”** Nếu field đã có trong JSON response, client đã nhận nó. Quyết định loại bỏ trường phải được thực hiện trước khi serialize.

**“Base64 hoặc nén dữ liệu sẽ làm serialization an toàn.”** Các phép biến đổi đó không cấp quyền truy cập và không thay contract của đích sau giải mã. Cũng không mặc định cung cấp tính bí mật hay chống sửa đổi.

**“Tên field do client chọn chỉ là dữ liệu vô hại.”** Với endpoint projection hoặc export tùy biến, phải kiểm tra tên trường được yêu cầu theo allowlist. Không cho tên trường trở thành đường truy cập tùy ý vào object nội bộ.

**“Cùng dùng JSON thì mọi service đều hiểu như nhau.”** Cần thống nhất kiểu ID, null, thời gian, miền số và tên trường duy nhất. Một chuỗi JSON hợp lệ vẫn có thể được các runtime diễn giải khác ở lớp nghiệp vụ.

**“Serialization sửa được mọi loại injection.”** Một JSON string được đưa tiếp vào SQL, CSS, URL hoặc shell lại có contract của nơi tiêu thụ đó. Ví dụ truy vấn SQL vẫn cần parameter binding; JSON serialization không thay cơ chế đó.

## 13. Bài tập vận dụng

Một endpoint trả cấu hình khóa học đang serialize trực tiếp entity có `title`, `ownerEmail`, `previewToken`, `lessonCount` và một ID số lớn. Frontend chép JSON vào data block rồi dùng title dựng HTML thẻ khóa học.

Hãy đề xuất một thay đổi thiết kế hoàn chỉnh:

1. Chọn DTO cho học viên và chỉ rõ những trường không được công bố.
2. Quy định kiểu ID, miền `lessonCount`, độ dài title và hành vi null.
3. Chọn endpoint JSON riêng hoặc data block có writer riêng; mô tả đúng parser của đường đã chọn.
4. Chọn sink hiển thị title và chỉ ra vì sao parse JSON chưa đủ bảo vệ sink đó.
5. Viết ba yêu cầu có thể nghiệm thu, gắn mỗi yêu cầu với một rủi ro và hai ca kiểm tra.
6. Quy định hành vi khi serializer lỗi để endpoint không rơi về `toString()` hoặc response dở dang.

Kết quả cần làm rõ dữ liệu được công bố cho ai, được biểu diễn theo hợp đồng nào và được sử dụng ở đâu. Một đường safe serialization hoàn chỉnh giữ được cả cấu trúc, ý nghĩa, quyền dữ liệu và ranh giới parser từ service tới nơi hiển thị.
