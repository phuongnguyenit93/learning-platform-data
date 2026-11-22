# `Locale.ROOT` cho định danh kỹ thuật khi phù hợp trong Java

## 1. Vì sao thao tác hoa/thường cần quan tâm đến locale?

Trong Java, `String.toLowerCase()` và `String.toUpperCase()` **không có tham số** sử dụng **locale mặc định của JVM** (`Locale.getDefault()`). Quy tắc đổi hoa/thường có thể phụ thuộc ngôn ngữ: cùng một chuỗi đầu vào có thể cho kết quả khác nhau trên máy đang dùng locale tiếng Anh, tiếng Thổ Nhĩ Kỳ hoặc môi trường khác.

Điều đó là hợp lý với **văn bản hướng đến người dùng**. Tuy nhiên, đối với nhiều **định danh kỹ thuật** — như tên tùy chọn do ứng dụng tự quy định, từ khóa nội bộ, nhãn cấu hình hoặc tên trạng thái cho phép so khớp không phân biệt hoa/thường — việc kết quả phụ thuộc ngôn ngữ mặc định có thể làm hỏng tra cứu và gây khác biệt giữa môi trường phát triển, kiểm thử và triển khai.

Khi quy ước của định danh yêu cầu **quy tắc hoa/thường ổn định, không gắn với một ngôn ngữ cụ thể**, hãy cân nhắc:

```java
String normalized = input.toLowerCase(java.util.Locale.ROOT);
```

`Locale.ROOT` là locale **trung lập về ngôn ngữ và quốc gia**. Nó giúp loại bỏ sự phụ thuộc vào *locale mặc định* khi đổi hoa/thường. Nhưng nó **không có nghĩa** “định danh nào cũng phải chuyển sang chữ thường”, cũng **không tự làm Unicode trở thành ASCII**, không chuẩn hóa Unicode và không giải quyết mọi kiểu so sánh hoặc an toàn định danh.

## 2. Lỗi môi trường gây ra bởi định danh chứa chữ `I`

Cùng mã `"TITLE"`, phép `toLowerCase()` không tham số có thể tạo khóa `"title"` hoặc `"tıtle"` tùy `Locale.getDefault()`. Hai khóa **không bằng nhau theo `String.equals()`**. Với từ khóa kỹ thuật không phụ thuộc ngôn ngữ, chỉ định chính sách cố định:

```java
String raw = "TITLE";
System.out.println(raw.toLowerCase(java.util.Locale.ROOT));                 // title
System.out.println(raw.toLowerCase(java.util.Locale.forLanguageTag("tr"))); // tıtle
```

Đây là snippet trong phương thức. Bài riêng về chữ I Thổ Nhĩ Kỳ phân tích đủ `I/i/İ/ı`; ở đây điều cần rút ra là **khóa ổn định phải được chuẩn hóa bằng cùng quy tắc ở nơi ghi và nơi đọc**.

## 3. Khi nào `Locale.ROOT` phù hợp?

Đây là lựa chọn thường hữu ích khi **đồng thời** thỏa hai điều kiện: (1) hợp đồng dữ liệu cho phép hoặc yêu cầu so khớp không phân biệt hoa/thường; (2) việc đổi hoa/thường phải độc lập với ngôn ngữ của người sử dụng.

| Dữ liệu hoặc tình huống | Cách cân nhắc | Lý do |
| --- | --- | --- |
| Khóa cấu hình nội bộ do ứng dụng tự đặt và quy định không phân biệt hoa/thường | `trim/strip` nếu được phép, sau đó `toLowerCase(Locale.ROOT)` | Không bị thay đổi bởi locale mặc định |
| Tên lựa chọn hoặc từ khóa command trong DSL tự thiết kế | `Locale.ROOT` nếu quy tắc DSL cho phép Unicode case mapping, hoặc tự xử lý ASCII theo đặc tả | Phải tuân theo grammar/contract thực tế |
| Nhãn phân loại kỹ thuật như `"PENDING"`, `"RUNNING"` | Chuẩn hóa bằng `Locale.ROOT` nếu API chấp nhận các biến thể chữ hoa/thường | Tạo khóa tra cứu nhất quán trong ứng dụng |
| Dữ liệu giao thức như HTTP field name | Tuân theo chính xác quy tắc giao thức; thường chỉ có ASCII và so khớp không phân biệt hoa/thường | Có thể dùng ASCII-only comparator hoặc xử lý theo thư viện giao thức; không mặc định mọi Unicode đều hợp lệ |
| Văn bản giao diện để hiển thị bằng ngôn ngữ của người dùng | `toLowerCase(userLocale)` / `toUpperCase(userLocale)` khi thực sự cần | Quy tắc ngôn ngữ địa phương có ý nghĩa |
| Tên người, tên địa danh, nội dung do người dùng nhập | Không tự ý đổi, hoặc áp dụng chính sách ngôn ngữ/so khớp phù hợp | Chuyển case có thể làm mất thông tin hoặc sai ngôn ngữ |
| Đường dẫn, URL, tên file, khóa database, username, email | Xem đặc tả và hệ thống đích trước khi thay đổi | Các phần tử có thể phân biệt hoa/thường hoặc có quy tắc riêng |

**Quy tắc quyết định:** `Locale.ROOT` phù hợp với việc áp dụng **Unicode case mapping trung lập** cho dữ liệu mà *chính hợp đồng* cho phép chuẩn hóa theo cách đó. Nó không tạo ra quyền tự đổi bất kỳ định danh nào sang lowercase.

## 4. Phân biệt các API liên quan

| API | Cơ chế | Khi dùng |
| --- | --- | --- |
| `s.toLowerCase()` | Dùng locale mặc định của JVM | Khi thực sự muốn theo locale mặc định, dù điều này thường chưa đủ rõ cho nghiệp vụ |
| `s.toLowerCase(Locale.ROOT)` | Dùng quy tắc Unicode không theo một ngôn ngữ cụ thể | Chuẩn hóa kỹ thuật có hợp đồng cho phép |
| `s.toUpperCase(Locale.ROOT)` | Tương tự nhưng đổi sang chữ hoa | Khi hợp đồng dùng dạng hoa làm chuẩn |
| `s.toLowerCase(userLocale)` | Áp dụng quy tắc cho locale người dùng | Văn bản ngôn ngữ tự nhiên |
| `s.equals(other)` | So sánh nội dung chính xác | Khi phân biệt hoa/thường hoặc hai giá trị đã được chuẩn hóa đồng nhất |
| `s.equalsIgnoreCase(other)` | So sánh không phân biệt hoa/thường theo quy tắc của Java, không dựa vào `Locale.ROOT` | Trường hợp so sánh đơn giản phù hợp với hợp đồng |
| `Normalizer.normalize(s, Form.NFC)` | Chuẩn hóa dạng biểu diễn Unicode, **không đổi hoa/thường** | Khi cần gộp các dạng Unicode tương đương theo chuẩn NFC |
| `Collator` | So sánh/sắp xếp văn bản theo các quy tắc locale | Ngôn ngữ tự nhiên, không phải mặc định cho mã định danh kỹ thuật |

Các thao tác trên **không thay đổi chính đối tượng `String`**, vì `String` bất biến. Những phương thức chuyển đổi trả về giá trị `String`; muốn sử dụng kết quả phải gán hoặc chuyển tiếp giá trị ấy.

### `equalsIgnoreCase` không đồng nghĩa với lowercase `Locale.ROOT`

`equalsIgnoreCase` so sánh theo quy tắc riêng của `String`, không phải thao tác “đưa hai vế về lowercase bằng `Locale.ROOT` rồi dùng `equals`”. Nó cũng không thực hiện Unicode normalization hay locale-aware collation đầy đủ.

Vì vậy, **không thay thế tùy ý**:

```java
boolean same1 = left.equalsIgnoreCase(right);
boolean same2 = left.toLowerCase(Locale.ROOT)
        .equals(right.toLowerCase(Locale.ROOT));
```

Đây là hai chiến lược có thể khác nhau với một số ký tự Unicode. Trong ứng dụng có quy định chặt chẽ về so khớp định danh, hãy chọn một quy tắc có tài liệu và sử dụng thống nhất ở cả bên tạo khóa và bên tra cứu; kiểm thử với dữ liệu đa ngôn ngữ.

## 5. Kiểm thử quy tắc định danh ở đúng điểm sử dụng

Với từ khóa kỹ thuật, một ví dụ chạy được trên máy phát triển chưa chứng minh chính sách đúng. Kiểm thử đầu vào hợp lệ, ký tự ngoài grammar, khoảng trắng và hành vi khi thay locale mặc định. Những phép kiểm tra sau minh họa sự khác nhau giữa một mã **không có `I`** và một mã **có `I`**:

```java
java.util.Locale tr = java.util.Locale.forLanguageTag("tr");
System.out.println("READ".toLowerCase(tr)
        .equals("READ".toLowerCase(java.util.Locale.ROOT)));  // true
System.out.println("TITLE".toLowerCase(tr)
        .equals("TITLE".toLowerCase(java.util.Locale.ROOT))); // false
```

Nếu chỉ kiểm thử các mã như `READ`, ta **bỏ sót Turkish-I**. Hãy thêm dữ liệu thử nhắm vào ranh giới grammar. Với định danh ASCII-only, kiểm tra grammar trước khi tạo khóa và kiểm tra va chạm giữa các giá trị đầu vào được chấp nhận.

## 6. Thiết kế hàm chuẩn hóa khóa kỹ thuật

Giả sử ứng dụng của bạn có một tập **tên lựa chọn do chính bạn định nghĩa**, không phân biệt hoa/thường, cho phép khoảng trắng thừa đầu/cuối và có ký tự Unicode hợp lệ. Khi đó có thể định nghĩa một hàm chuẩn hóa thống nhất.

Đây là lớp đầy đủ có thể lưu trong `TechnicalKey.java`:

```java
import java.util.Locale;
import java.util.Objects;

public final class TechnicalKey {
    private TechnicalKey() {
    }

    /**
     * Hợp đồng của ứng dụng:
     * - Đầu vào không null;
     * - Bỏ whitespace ở hai đầu theo String.strip();
     * - Chuyển chữ thường không phụ thuộc locale mặc định.
     */
    public static String normalize(String raw) {
        Objects.requireNonNull(raw, "raw");
        return raw.strip().toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(normalize("  ADMIN  "));
        System.out.println(normalize("Title"));
        System.out.println(normalize("TITLE"));
        System.out.println(normalize(" USER_NAME "));
        System.out.println(normalize("Title").equals(normalize("TITLE")));
    }
}
```

Chạy:

```bash
javac TechnicalKey.java
java TechnicalKey
```

Kết quả:

```text
admin
title
title
user_name
true
```

Trong ứng dụng thật, nên **dùng cùng hàm `normalize`** khi lưu khóa và khi tra cứu. Nếu chỉ chuẩn hóa khi đọc mà không chuẩn hóa lúc tạo, hai bên có thể không khớp.

**Nhưng:** đây là chính sách do ví dụ đặt ra, không phải chuẩn chung cho mọi khóa. Có hệ thống cần phân biệt `" Admin"` với `"Admin"`, cần giữ chữ hoa/thường hoặc chỉ chấp nhận ASCII. Khi đó hàm trên **không phù hợp**; hãy định nghĩa hợp đồng khác thay vì tự ý cắt khoảng trắng và lowercase.

### Nếu định danh chỉ cho phép ASCII

Nhiều định danh trong giao thức hoặc DSL được quy định bằng các ký tự ASCII như `A–Z`, `a–z`, `0–9`, `_` và `-`. Với kiểu dữ liệu này, nên **kiểm tra tập ký tự hợp lệ theo grammar trước** và xử lý case theo đúng đặc tả.

```java
static String normalizeAsciiKey(String input) {
    java.util.Objects.requireNonNull(input, "input");
    if (!input.matches("[A-Za-z][A-Za-z0-9_-]*")) {
        throw new IllegalArgumentException("Invalid ASCII key");
    }
    return input.toLowerCase(java.util.Locale.ROOT);
}
```

Đây là **phương thức minh họa để đặt trong một lớp**, không phải chương trình độc lập. Sau khi đã kiểm tra toàn bộ chuỗi là ASCII, `Locale.ROOT` cho cách lowercase dự kiến cho `A–Z` mà không bị ảnh hưởng bởi locale của máy chạy. Với quy tắc ASCII phức tạp hơn, một bộ xử lý ASCII riêng hoặc thư viện giao thức cũng có thể phù hợp.

`matches` kiểm tra theo biểu thức chính quy và được gọi mỗi lần ở ví dụ cho dễ đọc; nếu xử lý dữ liệu lớn ở đường nóng, có thể biên dịch sẵn `Pattern` hoặc dùng parser tối ưu phù hợp sau khi đo.

## 7. Giới hạn của lowercase `Locale.ROOT`

`Locale.ROOT` chọn quy tắc chuyển chữ trung tính; **nó không phải** Unicode normalization, full Unicode case folding hay cơ chế chống giả mạo định danh. Chẳng hạn `"\u00E9"` và `"e\u0301"` vẫn có thể khác nhau sau lowercase; `"\u0130"` có thể tạo dãy `"i\u0307"`. Nếu hợp đồng khóa yêu cầu NFC, hãy xác định vị trí chuẩn hóa và kiểm tra lại sau biến đổi case khi cần.

```java
String key = java.text.Normalizer.normalize(
        input.toLowerCase(java.util.Locale.ROOT),
        java.text.Normalizer.Form.NFC);
```

Đây là **hợp đồng minh họa**, không phải chuẩn chung cho username hay domain. Với Unicode case folding đầy đủ, IDN hoặc danh tính, hãy dùng đặc tả và công cụ chuyên dụng; chuẩn hóa compatibility có thể gộp ký tự mà ứng dụng cần phân biệt.

## 8. Các vấn đề khi dùng khóa chuẩn hóa trong `Map`, database và API

### 8.1. Nhất quán khi tạo và khi tra cứu

`HashMap<String, ...>` dùng `String.hashCode` và `String.equals`. Hai chuỗi chỉ khác chữ hoa/thường là **hai khóa khác nhau** nếu chưa được chuẩn hóa:

```java
java.util.Map<String, Integer> permissions = new java.util.HashMap<>();
permissions.put("admin", 1);

System.out.println(permissions.get("ADMIN")); // null
System.out.println(permissions.get(
        "ADMIN".toLowerCase(java.util.Locale.ROOT))); // 1
```

Nếu nghiệp vụ quy định khóa không phân biệt hoa/thường, phải áp dụng cùng chính sách khi thêm, tìm, so sánh và kiểm tra trùng lặp. Nếu hợp đồng phân biệt hoa/thường, giữ nguyên khóa và so sánh chính xác.

### 8.2. Chuẩn hóa ở các hệ thống khác nhau

Trong database, `LOWER(...)`, collation và Unicode normalization có thể dùng những quy tắc khác Java. Java service và cơ sở dữ liệu có thể **không đồng ý** về việc hai chuỗi có tương đương hay không. Nếu danh tính, tính duy nhất hoặc kiểm tra quyền phụ thuộc vào khóa đã chuẩn hóa, hãy quy định nơi chịu trách nhiệm xác thực/chuẩn hóa, dữ liệu nào được lưu và cách kiểm chứng trên mọi tầng.

Kết quả đổi case cũng có thể phụ thuộc vào phiên bản Unicode/JDK. Với hệ thống lưu khóa bền vững qua nâng cấp runtime, cần lưu ý tính ổn định của hợp đồng chuẩn hóa và có kế hoạch kiểm thử/migration nếu áp dụng chính sách Unicode rộng.

### 8.3. Không tự ý lowercase giá trị từ chuẩn bên ngoài

URL có nhiều thành phần với quy tắc phân biệt hoa/thường khác nhau; hostname, path và query không được phép xử lý đồng loạt bằng một lệnh lowercase. Tên tệp có thể phân biệt hoa/thường tùy hệ điều hành/filesystem. Địa chỉ email cũng có nhiều quy tắc riêng giữa domain và local part. Đối với header hoặc token của giao thức, nên dùng đúng parser/comparator theo chuẩn hoặc thư viện giao thức.

`Locale.ROOT` chỉ lựa chọn **locale cho một phép biến đổi String**, không tự định nghĩa “các byte nào là hợp lệ” hoặc “mọi thành phần có được đổi case không”. **Đặc tả của dữ liệu luôn quyết định trước.**

## 9. Lỗi phổ biến

1. **Dùng `toLowerCase()` không tham số để chuẩn hóa từ khóa máy hiểu.** Kết quả phụ thuộc locale mặc định. Nếu muốn quy tắc trung lập, chỉ định `Locale.ROOT` và kiểm tra hợp đồng khóa.
2. **Dùng `Locale.ENGLISH` cho mọi định danh kỹ thuật.** Locale tiếng Anh là một ngôn ngữ cụ thể; `Locale.ROOT` biểu thị ý định trung lập tốt hơn khi quy tắc kỹ thuật cần ngôn ngữ trung lập.
3. **Tự động lowercase username, đường dẫn, URL hay tên file.** Có thể phá vỡ ngữ nghĩa phân biệt hoa/thường. Cần đọc đặc tả/hợp đồng trước khi đổi.
4. **Giả định đổi hoa/thường không đổi `length()`.** Ví dụ `U+0130` có thể trở thành hai code point sau `toLowerCase(Locale.ROOT)`; viết hoa `ß` có thể mở rộng thành `SS`.
5. **Nhầm `Locale.ROOT` với chuẩn hóa Unicode.** Nó không làm `"\u00E9"` và `"e\u0301"` tự bằng nhau. Cần `Normalizer` nếu hợp đồng cho phép coi chúng tương đương.
6. **Nhầm lowercase với full Unicode case folding.** Hai thao tác không có cùng đặc tả. Đối chiếu nhu cầu của hệ thống trước khi chọn.
7. **Chuẩn hóa ở một phía.** Lưu bằng giá trị gốc nhưng tìm bằng giá trị đã lowercase có thể không khớp. Cần áp dụng quy tắc nhất quán tại các điểm tạo và tra cứu khóa.
8. **Gọi `toLowerCase(Locale.ROOT)` trên `null`.** Điều này ném `NullPointerException`. Hãy quyết định rõ null là lỗi, vắng giá trị hay một trạng thái hợp lệ.
9. **Cho rằng lowercase đủ chống mọi giả mạo Unicode.** Nhiều chữ khác bảng chữ cái trông giống nhau (confusables); chuẩn hóa chữ hoa/thường không phải cơ chế kiểm tra chống giả mạo định danh.
10. **Dùng một kết quả chuẩn hóa làm định danh bảo mật mà không kiểm tra va chạm.** Có thể có nhiều giá trị đầu vào trở thành cùng một khóa sau biến đổi; nếu dùng cho đăng nhập/ủy quyền, phải kiểm soát tính duy nhất và kiểm thử tính tương thích với nơi lưu trữ.

## 10. Cách chọn nhanh theo mục đích

| Mục đích | Hướng xử lý |
| --- | --- |
| Hiển thị văn bản cho người dùng theo ngôn ngữ địa phương | Chọn locale người dùng rõ ràng nếu cần case conversion |
| Tạo khóa nội bộ mà hợp đồng quy định không phân biệt hoa/thường, không phụ thuộc ngôn ngữ | `toLowerCase(Locale.ROOT)` hoặc `toUpperCase(Locale.ROOT)`, chọn một chuẩn và dùng nhất quán |
| Định danh thuộc chuẩn ASCII-only | Xác thực grammar ASCII, rồi dùng quy tắc case đúng theo chuẩn; có thể dùng `Locale.ROOT` sau bước xác thực |
| So sánh chính xác nội dung `String` | `equals` hoặc `Objects.equals` nếu có thể `null` |
| Cần so sánh Unicode không phân biệt hoa/thường theo chuẩn riêng | Chọn chiến lược case folding/collation có định nghĩa rõ, không tự suy từ `Locale.ROOT` |
| Cần gộp các biểu diễn Unicode tương đương | Xác định NFC/NFKC... theo yêu cầu trước khi chuẩn hóa |
| Identifier có ý nghĩa phân biệt chữ hoa/thường | Giữ nguyên và so sánh chính xác |

## 11. Tự kiểm tra

Hãy dự đoán kết quả:

```java
java.util.Locale tr = java.util.Locale.forLanguageTag("tr");
String source = "FILE";

System.out.println(source.toLowerCase(java.util.Locale.ROOT)
        .equals("file"));
System.out.println(source.toLowerCase(tr).equals("file"));
System.out.println("  ADMIN  ".strip()
        .toLowerCase(java.util.Locale.ROOT));
```

Kết quả:

```text
true
false
admin
```

Hai dòng đầu khác nhau do chữ `I` có cách xử lý hoa/thường đặc thù trong tiếng Thổ Nhĩ Kỳ; dòng cuối sử dụng một hợp đồng tự định nghĩa vừa bỏ whitespace đầu/cuối vừa chuẩn hóa chữ thường.

**Ghi nhớ:** Với **định danh kỹ thuật có quy ước so khớp không phân biệt hoa/thường và không theo một ngôn ngữ**, `Locale.ROOT` là cách nêu rõ ý định trong Java. Với văn bản hiển thị hoặc định danh theo chuẩn riêng, **hãy tuân thủ locale, grammar, Unicode policy và quy tắc so sánh của chính bài toán**.
