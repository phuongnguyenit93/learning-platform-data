# CSS encoding

## 1. Mục tiêu: dữ liệu giao diện không trở thành chương trình CSS

Một nền tảng học tập cho phép từng tổ chức chọn màu nhấn, cỡ chữ và nền cho trang khóa học. Các tùy chọn này có thể xuất phát từ biểu mẫu quản trị, API cấu hình hoặc dữ liệu đã lưu trong cơ sở dữ liệu. Khi chúng được đưa vào CSS, ranh giới bảo mật nằm ở chỗ: người dùng được chọn một giá trị trình bày đã cho phép, hay được thay đổi cả quy tắc trình bày của trang?

Ví dụ ghép chuỗi sau đã trao quá nhiều quyền cho trường `accentColor`:

```javascript
// Ví dụ cần tránh: biến nghiệp vụ được ghép vào mã CSS.
styleElement.textContent = `.course-card { color: ${accentColor}; }`;
```

Nếu dữ liệu là `red; display:none`, giá trị ban đầu của một thuộc tính đã trở thành hai khai báo. Tác động cụ thể phụ thuộc vị trí chèn và trình duyệt, nhưng yêu cầu “chỉ cho đổi màu chữ” đã bị vi phạm ngay cả khi không có JavaScript chạy.

Trong module yêu cầu bảo mật, CSS encoding cần được hiểu cùng một hợp đồng rõ ràng: nguồn dữ liệu nào được phép ảnh hưởng phần tử nào, ở thuộc tính nào, trong miền giá trị nào, và bằng chứng nào chứng minh giới hạn đó được giữ. Không thể đặc tả đủ bằng câu “escape CSS trước khi render”.

Sau bài học, người học cần phân biệt được chuỗi CSS, identifier, giá trị thuộc tính và URL; chọn được cách biểu diễn cho từng vị trí; đồng thời chuyển các lựa chọn đó thành yêu cầu và tiêu chí nghiệm thu.

## 2. Phân biệt encoding, validation và sanitization

Ba thao tác này giải quyết ba câu hỏi khác nhau:

| Thao tác | Câu hỏi cần trả lời | Ví dụ trong tính năng tùy chỉnh giao diện |
| --- | --- | --- |
| Validation | Giá trị này có thuộc miền nghiệp vụ cho phép không? | Cỡ chữ phải là số nguyên từ 14 đến 24 |
| Encoding hoặc serialization theo ngữ cảnh | Biểu diễn dữ liệu thế nào trong cú pháp đích? | Biểu diễn một nhãn bên trong CSS string có dấu nháy |
| Sanitization | Những thành phần nào được giữ lại trong nội dung có cấu trúc? | Một trình soạn giao diện chuyên dụng lọc cây CSS theo chính sách |

Trong ví dụ cỡ chữ, server nên nhận số hoặc chuỗi số có định dạng chặt, kiểm tra miền, rồi tự tạo đơn vị `px`. Người dùng không cần cung cấp `calc(...)`, `var(...)` hay một đoạn declaration. Đây là giảm quyền của dữ liệu bằng thiết kế, không phải tìm một encoder “mạnh hơn”.

Ngược lại, khi một chức năng thực sự cần chuỗi trong `content: "..."`, việc giới hạn độ dài không tự bảo vệ dấu nháy của CSS string. Vẫn cần encoder đúng ngữ cảnh. Nếu cho phép người dùng viết cả stylesheet, việc đó là một tính năng authoring với chính sách riêng, không còn là bài toán encoding một giá trị đơn lẻ.

## 3. Xác định vị trí trước khi chọn cơ chế bảo vệ

“Nằm trong CSS” chưa đủ để xác định hợp đồng an toàn. Cần chỉ ra chính xác vị trí dữ liệu được chèn:

| Vị trí | Ví dụ cú pháp | Quyết định thiết kế cho cổng học tập |
| --- | --- | --- |
| Giá trị màu | `color: VALUE` | Chọn palette hoặc chấp nhận định dạng màu được giới hạn rõ |
| Giá trị kích thước | `font-size: VALUE` | Số nguyên có miền; ứng dụng sinh đơn vị |
| Nội dung CSS string | `content: "VALUE"` | Ưu tiên nội dung HTML; nếu cần CSS string thì dùng encoder cho string |
| Một identifier trong selector | `#IDENTIFIER` | Dùng API tra cứu trực tiếp hoặc serialize identifier |
| Toàn bộ selector | `SELECTOR { ... }` | Người dùng thông thường không được cung cấp |
| Tên thuộc tính | `PROPERTY: value` | Tên thuộc tính cố định trong mã ứng dụng |
| Danh sách declaration | `style="DECLARATIONS"` | Không nhận từ API tùy chỉnh giao diện thông thường |
| Tài nguyên nền | `background-image: url(...)` | Nhận mã asset đã duyệt thay vì URL tùy ý |
| Custom property | `--accent: VALUE` | Xác định cả nơi sử dụng `var(--accent)` trước khi cho phép |

Một chuỗi có thể hợp lệ ở vị trí này nhưng vô nghĩa hoặc nguy hiểm ở vị trí khác. Chẳng hạn, escape identifier có thể giúp xây dựng selector cho một ID; nó không chứng minh một giá trị `background-image` đáp ứng chính sách tải tài nguyên.

OWASP khuyến nghị tránh nội suy dữ liệu không tin cậy vào mã CSS; với giao diện động, dùng CSSOM với tên thuộc tính cố định và allowlist riêng cho giá trị. API nhận giá trị không thay thế việc quyết định ứng dụng cho phép giá trị nào. [OWASP: CSS contexts](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html#output-encoding-for-css-contexts).

## 4. CSS escape thực sự biểu diễn điều gì?

CSS có escape dạng dấu gạch chéo ngược theo sau bởi 1 đến 6 chữ số hexadecimal. Một ký tự whitespace ngay sau phần hexadecimal có thể được tiêu thụ để kết thúc escape. Ví dụ bên dưới là cú pháp CSS, không phải JavaScript string:

```css
/* Hai CSS string này biểu diễn cùng nội dung: A&B. */
.one::before { content: "A\26 B"; }
.two::before { content: "A\000026B"; }
```

Không có ký tự kết thúc phù hợp, chữ số hexadecimal tiếp theo có thể bị nhập vào cùng escape. Các code point không hợp lệ như zero hoặc surrogate được xử lý theo quy tắc thay thế của CSS, nên không được giả định mọi chuỗi đầu vào đều round-trip nguyên vẹn. [CSS Syntax: consume an escaped code point](https://www.w3.org/TR/css-syntax-3/#consume-escaped-code-point).

Trong thiết kế ứng dụng, điều cần nhớ là escape bảo vệ một vị trí cú pháp cụ thể. Nó không thay đổi quyền nghiệp vụ của giá trị sau khi parser diễn giải. Một URL ngoài danh sách vẫn nằm ngoài chính sách dù đã được biểu diễn hợp lệ trong CSS; một identifier trỏ đến thành phần nhạy cảm vẫn không được phép sử dụng chỉ vì selector hợp lệ.

Không viết encoder bằng vài lệnh `replace` cho dấu nháy, chấm phẩy và dấu ngoặc. Hợp đồng còn phải xét newline, backslash, Unicode, ranh giới token và môi trường bao ngoài. Đối với tính năng chỉ cần vài màu hoặc cỡ chữ, ánh xạ sang tập giá trị cố định thường tạo ra hợp đồng dễ kiểm chứng hơn nhiều.

## 5. CSS trong HTML có nhiều tầng parser

### 5.1. Thuộc tính `style` không chỉ có CSS

Trong đoạn HTML sau, trình duyệt xử lý cú pháp thuộc tính HTML trước khi diễn giải CSS bên trong:

```html
<div style="color: VALUE">Khóa học</div>
```

Nếu bắt buộc sinh thuộc tính này trên server, giá trị phải đáp ứng chính sách của thuộc tính CSS rồi toàn bộ nội dung thuộc tính phải được biểu diễn đúng cho HTML attribute có dấu nháy. HTML entity encoding đơn độc không làm một declaration tùy ý trở thành màu hợp lệ; lớp HTML có thể giải mã entity trước khi CSS được xử lý.

Vì vậy, đặc tả nên chỉ rõ chuỗi xử lý, thay vì ghi mơ hồ “escape hai lần”:

```text
Giá trị nghiệp vụ
→ kiểm tra kiểu và miền
→ tạo giá trị CSS theo hợp đồng của thuộc tính
→ template encode cho HTML attribute nếu đi qua HTML source
```

Nếu dùng DOM API ở runtime, không áp dụng máy móc lớp HTML encoding của template vào giá trị API.

### 5.2. Dấu nháy CSS không bảo vệ thẻ `style`

```html
<!-- Mẫu ghép chuỗi cần tránh khi VALUE là dữ liệu tùy ý. -->
<style>
  .course-label::before { content: "VALUE"; }
</style>
```

Trong HTML thông thường, `style` được phân tích theo chế độ raw text. Chuỗi đóng thẻ phù hợp có thể kết thúc phần tử trước khi ý nghĩa CSS string được xét; đặt dữ liệu trong dấu nháy CSS không tự bảo vệ ranh giới HTML này. Đây là lý do phải xét parser bao ngoài khi chọn encoder hoặc đổi thiết kế. [WHATWG HTML: raw text end tag processing](https://html.spec.whatwg.org/multipage/parsing.html#rawtext-end-tag-name-state).

Đối với cổng học tập, nhãn khóa học nên được đặt trong phần tử HTML bằng API văn bản hoặc template tự encode. Không đưa nhãn vào CSS chỉ để hiển thị chữ. Tách CSS tĩnh khỏi nội dung người dùng làm giảm số ngữ cảnh phải bảo vệ và giữ nội dung trong cấu trúc tài liệu phù hợp.

## 6. Từ rủi ro tới mô hình dữ liệu có giới hạn

Giả sử đội sản phẩm đề xuất cấu hình sau:

```json
{
  "accentColor": "bất kỳ chuỗi CSS nào",
  "fontSize": "bất kỳ giá trị nào",
  "background": "URL do quản trị viên nhập",
  "extraStyle": "CSS bổ sung"
}
```

Quản trị viên tổ chức vẫn là nguồn ngoài ranh giới tin cậy của mã ứng dụng. Tài khoản có thể bị chiếm, cấu hình có thể được nhập từ hệ thống khác, và trang có thể được học viên của nhiều vai trò xem. Việc gắn nhãn “admin” cho nguồn dữ liệu không giải quyết quyền tác động của CSS lên trang người khác.

Một phương án cho cùng nhu cầu sản phẩm là:

```json
{
  "accent": "ocean",
  "fontSizePx": 16,
  "backgroundAssetId": "course-grid"
}
```

Trong phương án này, `accent` là một trong ba lựa chọn; `fontSizePx` là số nguyên 14–24; `backgroundAssetId` tham chiếu asset do ứng dụng quản lý. Không có trường nhận selector, tên property hay declaration.

Các miền giá trị trên là chính sách của ví dụ, không phải ngưỡng bảo mật dùng chung cho mọi sản phẩm. Đội sản phẩm cần chọn miền phù hợp khả năng đọc, bố cục và quyền tùy chỉnh thực tế. Giá trị bảo mật của mô hình nằm ở khả năng mô tả chính xác tập hành vi được cấp.

Đội thiết kế cũng cần xác định bề mặt tác động. Trong ví dụ này, tùy chỉnh chỉ áp dụng cho vùng giới thiệu khóa học, không áp dụng cho hộp xác nhận thanh toán, cảnh báo quyền riêng tư hay thông tin phân quyền. Cho phép đổi màu không có nghĩa cho phép làm một cảnh báo biến mất.

## 7. Ví dụ Java: nhận tùy chọn, trả về class do ứng dụng kiểm soát

Ví dụ dưới đây dùng Java 17 trở lên. Nó minh họa biên chuyển đổi dữ liệu cấu hình thành các CSS class cố định; không cần encoder CSS vì dữ liệu đầu vào không được chép thành mã CSS.

```java
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public final class CourseAppearancePolicy {
    private static final Map<String, String> ACCENT_CLASSES = Map.of(
            "ocean", "course-accent-ocean",
            "forest", "course-accent-forest",
            "plum", "course-accent-plum"
    );

    private static final Set<String> BACKGROUND_IDS = Set.of(
            "none", "course-grid", "course-dots"
    );

    // Định dạng hẹp, tối đa hai chữ số; không nhận đơn vị hay biểu thức.
    private static final Pattern FONT_SIZE = Pattern.compile("[0-9]{1,2}");

    public record Appearance(
            String accentClass,
            String fontClass,
            String backgroundClass
    ) {}

    public static Appearance parse(
            String accent,
            String fontSizePx,
            String backgroundId
    ) {
        String accentClass = accent == null
                ? null : ACCENT_CLASSES.get(accent);
        if (accentClass == null) {
            throw new IllegalArgumentException("Unsupported accent");
        }

        if (fontSizePx == null || !FONT_SIZE.matcher(fontSizePx).matches()) {
            throw new IllegalArgumentException("Invalid font size format");
        }
        int fontSize = Integer.parseInt(fontSizePx);
        if (fontSize < 14 || fontSize > 24) {
            throw new IllegalArgumentException("Font size outside policy");
        }

        if (backgroundId == null || !BACKGROUND_IDS.contains(backgroundId)) {
            throw new IllegalArgumentException("Unsupported background");
        }

        return new Appearance(
                accentClass,
                "course-font-" + fontSize,
                "course-bg-" + backgroundId
        );
    }

    private CourseAppearancePolicy() {}
}
```

Stylesheet do ứng dụng quản lý chứa các class tương ứng:

```css
.course-accent-ocean { --course-accent: #075985; }
.course-accent-forest { --course-accent: #166534; }
.course-accent-plum { --course-accent: #6b21a8; }

.course-card { border-color: var(--course-accent); }

.course-font-14 { font-size: 14px; }
.course-font-15 { font-size: 15px; }
.course-font-16 { font-size: 16px; }
.course-font-17 { font-size: 17px; }
.course-font-18 { font-size: 18px; }
.course-font-19 { font-size: 19px; }
.course-font-20 { font-size: 20px; }
.course-font-21 { font-size: 21px; }
.course-font-22 { font-size: 22px; }
.course-font-23 { font-size: 23px; }
.course-font-24 { font-size: 24px; }

.course-bg-none { background-image: none; }
.course-bg-course-grid {
  background-image: url("/assets/course-grid.svg");
}
.course-bg-course-dots {
  background-image: url("/assets/course-dots.svg");
}
```

Các đường dẫn asset là hằng của ứng dụng; ví dụ giả định chúng trỏ đến tài nguyên tĩnh đã được duyệt. Tính năng upload asset, nếu có, cần chính sách riêng và không được coi là an toàn chỉ vì nhận được một asset ID.

Đầu ra `Appearance` được đưa vào thuộc tính `class` qua template tự encode HTML hoặc qua `classList.add` ở runtime. Không tắt escaping mặc định của template để tiện ghép class. Ba class do policy trả về mới là đầu ra được phép dùng; không lấy lại ba chuỗi đầu vào để render sau khi gọi `parse`.

Ở tầng HTTP, lỗi validation nên được ánh xạ thành phản hồi từ chối cấu hình theo contract API. Không đưa toàn bộ giá trị nhận được vào thông báo lỗi hiển thị trên trang. Nếu cập nhật nhiều trường trong một lần, policy nên được kiểm tra trước khi ghi để tránh lưu cấu hình nửa hợp lệ.

## 8. Ví dụ DOM: tên thuộc tính cố định, giá trị được tái tạo

Đôi khi giao diện cần cập nhật trực tiếp mà không thay toàn bộ class. Có thể dùng một API nhỏ với hợp đồng hẹp:

```javascript
const accentColors = new Map([
  ["ocean", "#075985"],
  ["forest", "#166534"],
  ["plum", "#6b21a8"]
]);

function applyCourseAppearance(card, options) {
  const color = accentColors.get(options.accent);
  const size = options.fontSizePx;

  if (color === undefined) {
    throw new TypeError("Unsupported accent");
  }
  if (!Number.isInteger(size) || size < 14 || size > 24) {
    throw new TypeError("Invalid font size");
  }

  // Kiểm tra toàn bộ tùy chọn trước khi cập nhật DOM.
  card.style.setProperty("border-color", color);
  card.style.setProperty("font-size", `${size}px`);
}
```

Hai thuộc tính được chọn trong mã ứng dụng. Dữ liệu chỉ chọn màu trong bảng và một số nguyên có miền. Không có đối số `propertyName`, `priority` hoặc chuỗi declaration đến từ API.

Không HTML-encode `color` trước khi gọi `setProperty`; đây không phải vị trí đang được HTML parser đọc. Cũng không dùng kết quả CSS string encoding cho số `size`: đầu ra `16px` được tạo từ số hợp lệ theo ngữ pháp của thuộc tính cần dùng.

Đoạn mã này là một thành phần giao diện, không phải kiểm soát quyền ở server. Server vẫn phải kiểm tra tổ chức nào được sửa cấu hình khóa học nào; client chỉ giúp giới hạn đường dữ liệu đi vào DOM và phản hồi sớm khi nhận dữ liệu sai contract.

Tránh thay API hẹp bằng một tiện ích tổng quát như sau:

```javascript
// Không dùng cho dữ liệu cấu hình không tin cậy.
function applyAnything(element, properties) {
  for (const [name, value] of Object.entries(properties)) {
    element.style.setProperty(name, value);
  }
}
```

Vòng lặp này đã chuyển quyền chọn property cho nguồn dữ liệu. Dù mỗi lời gọi dùng CSSOM, yêu cầu “chỉ đổi màu viền và cỡ chữ” không còn được thể hiện trong mã.

## 9. Khi nào `CSS.escape()` phù hợp?

`CSS.escape()` được đặc tả để serialize một identifier. Một ứng dụng đã có ID và muốn tìm đúng phần tử bằng selector có thể viết:

```javascript
const matchingElement = document.querySelector("#" + CSS.escape(elementId));
```

Nếu chỉ cần tìm theo ID, `document.getElementById(elementId)` tránh việc dựng selector. Không áp dụng `CSS.escape()` cho toàn bộ declaration rồi xem kết quả là CSS đã được duyệt; API này không kiểm tra quyền lựa chọn phần tử hay chính sách URL. [CSSOM: CSS.escape()](https://drafts.csswg.org/cssom/#the-css.escape()-method).

Trong cổng học tập, người dùng không cần truyền ID của một phần tử tùy ý để đổi kiểu hiển thị. Đối tượng DOM nên được thành phần giao diện chọn sẵn. Nếu một API cho phép gửi cả `targetSelector` và `styleValue`, việc sửa encoder của `styleValue` vẫn để nguyên một quyền tác động lớn ở `targetSelector`.

## 10. Trường hợp thật sự cần CSS string trong Java

Một chức năng xuất stylesheet độc lập có thể cần nhãn trang trí trong CSS string. OWASP Java Encoder có `Encode.forCssString` cho dữ liệu bên trong một CSS string có dấu nháy; `forCssUrl` dành cho giá trị URL trong `url(...)`, với chính sách URL phải được kiểm tra trước. Các API này không nhận thay cho numeric value, property name hoặc toàn bộ stylesheet. [OWASP Java Encoder: hợp đồng ngữ cảnh](https://raw.githubusercontent.com/OWASP/owasp-java-encoder/main/docs/contexts.md).

Ví dụ sau giới hạn ở tài nguyên CSS độc lập, được trả bằng `Content-Type: text/css; charset=UTF-8`. Đây không phải ví dụ để chèn kết quả vào HTML source:

```java
import org.owasp.encoder.Encode;

public final class DecorativeLabelCss {
    public static String render(String label) {
        if (label == null
                || label.codePointCount(0, label.length()) > 80
                || label.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException("Invalid decorative label");
        }

        String encoded = Encode.forCssString(label);
        return ".course-label::before { content: \"" + encoded + "\"; }\n";
    }

    private DecorativeLabelCss() {}
}
```

Giới hạn 80 code point là chính sách kích thước của ví dụ; nó không thay thế encoding. Dấu nháy bao quanh string và toàn bộ selector, property, dấu ngoặc đều do ứng dụng cung cấp. Không nhận chuỗi đã encode từ client và không decode lại `encoded` trước khi ghi response.

Khi triển khai, dependency encoder phải được quản lý theo phiên bản đã duyệt của dự án. Ví dụ chỉ minh họa cách gọi API, không yêu cầu thay dependency hay cấu hình build của module học tập.

Đối với nhãn có ý nghĩa nội dung, vẫn ưu tiên HTML text. Việc chọn CSS string phải bắt đầu từ nhu cầu chức năng cụ thể; không nên dùng generated content làm nơi duy nhất chứa thông tin bắt buộc để học viên hiểu hoặc thực hiện một hành động.

## 11. URL và custom property cần chính sách theo nơi tiêu thụ

### 11.1. Asset ID là quyết định sản phẩm có thể kiểm chứng

Với nền khóa học, đội sản phẩm có thể chốt rằng chỉ các asset được phát hành cùng ứng dụng được dùng. Khi đó yêu cầu ghi rõ: client gửi mã `course-grid`, server ánh xạ sang class tương ứng, stylesheet chứa đường dẫn hằng. Dữ liệu người dùng không chứa URL.

Nếu sau này bổ sung nền từ URL, đó là thay đổi miền quyền, cần xem lại thiết kế: nguồn nào được phép tải, có cho redirect không, trường hợp URL tương đối được giải quyết theo base nào, và nội dung ngoài tổ chức có được hiển thị trên trang học viên không? URL hợp lệ về cú pháp chưa trả lời được các câu hỏi này.

Không áp dụng percent-encoding lên toàn bộ URL rồi coi như đã kiểm tra chính sách. Encoding cho URL component, encoding cho CSS và quyết định đích tài nguyên là các hợp đồng khác nhau. Với mô hình asset ID hiện tại, không cần mở thêm bề mặt URL chỉ để hỗ trợ ba kiểu nền cố định.

### 11.2. Custom property không tự giới hạn loại giá trị

Ví dụ dưới đây cho thấy cùng một biến cấu hình có thể được tiêu thụ ở nơi khác:

```css
.course-card {
  background-image: var(--course-background);
}
```

Một API cho phép đặt tùy ý `--course-background` đã ảnh hưởng đến nguồn ảnh nền, dù tên custom property có vẻ là chi tiết nội bộ. Vì vậy, inventory phải ghi cả điểm gán và các điểm dùng `var(...)`.

Trong ví dụ palette ở phần Java, biến `--course-accent` chỉ nhận hằng từ stylesheet do ứng dụng kiểm soát. Khi thay stylesheet để dùng biến đó ở vị trí mới, reviewer vẫn cần đối chiếu lại hợp đồng của tính năng. Không nên ghi yêu cầu chung rằng mọi custom property đều an toàn.

## 12. Đặc tả yêu cầu bảo mật có thể nghiệm thu

Dưới đây là bộ yêu cầu mẫu cho cấu hình giao diện khóa học. ID, phạm vi và ngưỡng là đề xuất cho tình huống trong bài:

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-CSS-01 | API tùy chỉnh chỉ nhận `accent`, `fontSizePx`, `backgroundAssetId`; không chấp nhận trường style mở rộng | Contract request và ca gửi trường ngoài schema |
| SR-CSS-02 | `accent` chỉ nhận `ocean`, `forest`, `plum`; server ánh xạ sang class cố định | Kiểm tra bảng ánh xạ và giá trị ngoài tập |
| SR-CSS-03 | `fontSizePx` chỉ nhận số nguyên 14–24; response hoặc template không sử dụng chuỗi kích thước gốc | Ca biên, sai kiểu, và kiểm tra đầu ra |
| SR-CSS-04 | Nền chỉ chọn từ asset ID đã duyệt; request không cấp URL cho CSS | Ca thử URL ở trường asset ID và quan sát tài nguyên tải |
| SR-CSS-05 | Mỗi điểm ghi CSS động có tên property cố định và miền giá trị được mô tả | Danh mục sink cùng policy chịu trách nhiệm |
| SR-CSS-06 | Nếu xuất nhãn trong CSS string, chỉ đưa nhãn qua encoder có contract cho quoted CSS string; cấu trúc rule là hằng | Kiểm tra đường sinh stylesheet và fixture string |
| SR-CSS-07 | Cấu hình sai bị từ chối trước khi lưu; trang đọc cấu hình không dùng giá trị raw làm phương án dự phòng | Ca cập nhật nhiều trường và ca dữ liệu cũ sai contract |
| SR-CSS-08 | Tùy chỉnh chỉ tác động thành phần khóa học đã định; không cho chọn selector hoặc property tùy ý | Kiểm tra contract và quan sát vùng giao diện ngoài phạm vi |

SR-CSS-01 cần hành vi rõ cho trường không biết. Nếu sản phẩm muốn bỏ qua trường lạ thay vì từ chối, phải ghi chính sách đó và vẫn chứng minh trường lạ không đi tới renderer. Không để server vô tình chấp nhận một `extraStyle` do cơ chế binding tự động.

Đối với dữ liệu cũ không hợp lệ, có thể chọn bộ cấu hình mặc định do ứng dụng sở hữu để trang vẫn đọc được. Sự lựa chọn này cần được đặc tả riêng cho đường đọc; nó không đồng nghĩa API cập nhật được phép báo thành công với dữ liệu sai. Giá trị raw bị từ chối không được trở thành CSS dự phòng.

## 13. Thiết kế tiêu chí kiểm thử cho yêu cầu

Phần này mô tả bằng chứng cần có khi triển khai sản phẩm; không khẳng định các kiểm thử đã được chạy trong bài học.

### 13.1. Kiểm tra theo miền dữ liệu

| Dữ liệu thử | Đường xử lý | Kỳ vọng của ví dụ |
| --- | --- | --- |
| `accent = ocean` | Palette | Chọn class `course-accent-ocean` |
| `accent = red;display:none` | Palette | Từ chối; không có declaration mới |
| `accent = url(...)` | Palette | Từ chối như mọi giá trị ngoài tập |
| `fontSizePx = 14`, `24` | Miền số | Chấp nhận đúng hai biên |
| `fontSizePx = 13`, `25` | Miền số | Từ chối ngoài miền |
| `fontSizePx = "16px"` | Kiểu dữ liệu/API | Từ chối; client không chọn đơn vị |
| `fontSizePx = "16;display:none"` | Kiểu dữ liệu/API | Từ chối toàn bộ, không chỉ đọc tiền tố `16` |
| `backgroundAssetId = course-grid` | Asset ID | Chọn class nền được duyệt |
| `backgroundAssetId = https://invalid.example/bg.png` | Asset ID | Từ chối; không tạo yêu cầu tải tới địa chỉ đó |
| Nhãn chứa nháy kép và backslash | CSS string exporter | Vẫn là dữ liệu trong một string, không tạo rule khác |
| Nhãn có chữ Việt và emoji | CSS string exporter | Giữ nội dung hợp lệ theo contract, không cắt đôi Unicode |
| Nhãn trên 80 code point | CSS string exporter | Từ chối theo giới hạn của ví dụ |

Đối với endpoint nhận JSON số, cần kiểm tra cả số thập phân, `null`, mảng, chuỗi và số vượt miền. Đối với adapter nhận chuỗi như ví dụ Java, kiểm tra thêm whitespace, chữ số ngoài ASCII và chuỗi quá dài. Đây là hai lớp binding khác nhau; không giả định contract của lớp này tự áp dụng cho lớp kia.

### 13.2. Kiểm tra cả hiệu ứng, không chỉ chuỗi output

Một response không chứa thẻ `script` chưa chứng minh chức năng an toàn. Cần quan sát những thuộc tính liên quan đến rủi ro đã xác định:

- Cấu hình bị từ chối không được lưu hoặc áp dụng một phần.
- Không phát sinh selector, rule hoặc property ngoài hợp đồng tính năng.
- Không có yêu cầu tài nguyên mới tới nguồn ngoài tập được duyệt.
- Cảnh báo, nút xác nhận và thông tin quyền ở ngoài vùng tùy chỉnh giữ khả năng hiển thị như thiết kế.
- Đường preview và đường hiển thị sau khi lưu dùng cùng chính sách miền giá trị.

Khi kiểm tra CSSOM, trình duyệt có thể serialize lại cách viết màu hoặc giá trị. Do đó không nên chỉ so sánh nguyên văn chuỗi style. Với ví dụ class, có thể đối chiếu class được chọn và kiểm tra kết quả hiển thị liên quan; với exporter CSS string, có thể phân tích rule rồi xác minh dữ liệu string vẫn nằm đúng vị trí.

### 13.3. Liên kết rủi ro, yêu cầu và bằng chứng

Một hồ sơ yêu cầu ngắn có thể dùng các liên kết sau:

```text
Rủi ro: cấu hình tổ chức che nội dung ngoài vùng được tùy chỉnh
→ SR-CSS-01, SR-CSS-05, SR-CSS-08
→ schema đóng + sink có property cố định + phạm vi thành phần
→ ca gửi extraStyle và selector tùy ý, quan sát vùng ngoài phạm vi

Rủi ro: nền trang tải tài nguyên do nguồn ngoài kiểm soát
→ SR-CSS-04
→ asset ID ánh xạ sang stylesheet tĩnh
→ ca gửi URL, quan sát không có request tương ứng
```

Cách liên kết này giúp reviewer trả lời “kiểm soát đang giảm rủi ro nào?” và “cần cập nhật bằng chứng nào khi sản phẩm thêm tùy chọn mới?”. Không chỉ lưu một danh sách payload đã thử mà không gắn với phạm vi bảo vệ.

## 14. Những quyết định dễ làm mất hợp đồng an toàn

**Chỉ lọc dấu chấm phẩy.** Chính sách như vậy không mô tả miền giá trị của màu, kích thước hay URL. Cần tập giá trị hoặc bộ phân tích đúng loại dữ liệu, thay vì danh sách vài ký tự cấm.

**Dùng `parseInt` rồi bỏ qua phần còn lại.** Nếu API định nghĩa số nguyên, chuỗi có thêm đơn vị hoặc declaration phải bị từ chối, không được âm thầm biến thành một tiền tố số. Việc chuẩn hóa chỉ được thực hiện theo quy tắc đã định trước.

**Cho rằng dữ liệu từ database đã đáng tin.** Lưu trữ không cấp thêm quyền cho dữ liệu. Preview, trang học viên, email và bản xuất có thể có các renderer khác nhau; mỗi nơi cần contract riêng của ngữ cảnh đầu ra.

**Mở một field để “hỗ trợ khách hàng đặc biệt”.** `extraStyle` có thể vô hiệu hóa toàn bộ giới hạn của các field còn lại. Nếu thực sự cần stylesheet do người dùng viết, tách thành tính năng có chủ sở hữu chính sách, phạm vi cô lập và quy trình xét duyệt riêng.

**Kiểm tra một giá trị rồi render giá trị khác.** Chẳng hạn, server xác minh `fontSizePx` nhưng template lại lấy `request.getParameter("fontSize")` để dựng style. Renderer phải dùng kết quả đã được policy chuyển đổi, không đọc lại nguồn raw.

**Chỉ bảo vệ đường lưu.** Nếu preview ghép raw CSS nhưng đường lưu dùng allowlist, tài khoản quản trị vẫn tiếp xúc với bề mặt không có cùng hợp đồng. Cần ghi rõ tất cả đường xem trước, phục hồi và xuất tài liệu trong inventory của tính năng.

## 15. Bài tập vận dụng

Một đội phát triển muốn thêm ba tùy chọn: khoảng cách giữa các thẻ khóa học, vị trí ảnh nền và stylesheet tùy chỉnh. Hãy thực hiện các quyết định sau trước khi chọn encoder:

1. Với khoảng cách, đề xuất kiểu số, miền và đơn vị do ứng dụng sinh; mô tả hành vi khi dữ liệu có hậu tố CSS.
2. Với vị trí ảnh nền, chọn tập lựa chọn hữu hạn nếu nghiệp vụ cho phép; xác định class hoặc property cố định được tác động.
3. Với stylesheet tùy chỉnh, xác định vì sao miền quyền khác hai trường còn lại và cần quy trình thiết kế riêng.
4. Viết một yêu cầu đo được và hai ca nghiệm thu cho từng tùy chọn được chấp nhận.
5. Chỉ ra đầu ra mà renderer được dùng sau validation, đồng thời xác định cách preview và trang đã lưu chia sẻ policy.

Một câu trả lời tốt phải cho thấy dữ liệu được cấp quyền làm gì, đi vào parser nào và bằng chứng nào giữ được ranh giới đó. CSS encoding là một phần của quyết định này; nó phát huy tác dụng khi ngữ cảnh và hợp đồng giá trị đã được xác định rõ.
