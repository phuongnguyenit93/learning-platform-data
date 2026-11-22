# `String.contains()` để kiểm tra chuỗi con trong Java

Trong Java, **`String.contains(CharSequence s)`** trả về `true` nếu chuỗi đang xét **có chứa một dãy ký tự liên tiếp đúng bằng** đối số `s`, ngược lại trả về `false`. Đây là công cụ đơn giản để kiểm tra sự xuất hiện của một **chuỗi con** (*substring*) mà không cần biết vị trí bắt đầu.

Ví dụ:

```java
String text = "Java Core - String";

System.out.println(text.contains("Core")); // true
System.out.println(text.contains("core")); // false
```

Từ khóa quan trọng là **liên tiếp** và **đúng nguyên văn**: `contains()` phân biệt chữ hoa/chữ thường, không bỏ khoảng trắng, không tự chuẩn hóa Unicode, không tách từ và **không dùng biểu thức chính quy (regex)**.

## 1. Cú pháp, tham số và giá trị trả về

Khai báo trong lớp `java.lang.String`:

```java
public boolean contains(CharSequence s)
```

- **Đối tượng nhận:** một `String` cần tìm bên trong, chẳng hạn `text`.
- **Tham số `s`:** một `CharSequence` làm chuỗi con cần tìm. Thông thường truyền một `String` như `"Java"`; đối số có thể là một triển khai `CharSequence` khác như `StringBuilder`.
- **Kết quả:** `boolean`, bằng `true` nếu tìm được dãy ký tự liên tiếp, bằng `false` nếu không.
- **Vị trí:** `contains()` **không trả về vị trí**. Nếu muốn vị trí xuất hiện đầu tiên, dùng `indexOf()`.
- **`null`:** gọi phương thức trên `null` hoặc truyền tham số `null` đều gây `NullPointerException` (chi tiết trong phần xử lý null).

Ví dụ so sánh:

| Đầu vào | Lời gọi | Kết quả | Giải thích |
| --- | --- | --- | --- |
| `"Java Core"` | `contains("Java")` | `true` | Tìm thấy ở đầu |
| `"Java Core"` | `contains("Core")` | `true` | Tìm thấy ở cuối |
| `"Java Core"` | `contains("va Co")` | `true` | Tồn tại dãy liên tiếp xuyên qua dấu cách |
| `"Java Core"` | `contains("java")` | `false` | `J` và `j` khác nhau |
| `"Java Core"` | `contains("JavaCore")` | `false` | Thiếu dấu cách so với dữ liệu gốc |
| `"Java Core"` | `contains("Python")` | `false` | Không xuất hiện |

**`contains()` không yêu cầu khớp toàn bộ chuỗi**. `"Java Core".contains("Java")` là `true` dù đối tượng có thêm `" Core"`, còn `"Java Core".equals("Java")` là `false`.

## 2. Ví dụ Java 17+ hoàn chỉnh

Lưu mã dưới tên `ContainsBasics.java`:

```java
public class ContainsBasics {
    public static void main(String[] args) {
        String text = "Java Core - String";

        System.out.println(text.contains("Core"));
        System.out.println(text.contains("core"));
        System.out.println(text.contains("Java Core"));
        System.out.println(text.contains(""));

        System.out.println("".contains(""));
        System.out.println("".contains("Java"));

        System.out.println(
                text.contains(new StringBuilder("String")));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ContainsBasics.java
java ContainsBasics
```

Kết quả:

```text
true
false
true
true
true
false
true
```

Giải thích:

1. Chuỗi `"Core"` xuất hiện liên tiếp nên trả `true`.
2. `"core"` khác `"Core"` do phân biệt chữ hoa/thường nên `false`.
3. `"Java Core"` xuất hiện ở đầu chuỗi, khớp đúng dấu cách.
4. **Chuỗi rỗng `""` được coi là chuỗi con của mọi `String`**, kể cả chuỗi rỗng; vì thế cả `text.contains("")` và `"".contains("")` đều trả `true`.
5. Chuỗi rỗng không chứa dãy ký tự `"Java"` nên `"".contains("Java")` trả `false`.
6. `StringBuilder` triển khai `CharSequence`, vì vậy `contains(new StringBuilder("String"))` hợp lệ và tìm được dãy ký tự.

Về mặt ngữ nghĩa, Java kiểm tra sự hiện diện của **một chuỗi con chính xác**. Không cần gọi `toString()` trước khi truyền một `StringBuilder`, nhưng nếu nội dung của đối tượng thay đổi trong khi một luồng khác đang sử dụng nó, cần đồng bộ phù hợp; các `CharSequence` có thể thay đổi không có bảo đảm thread-safe mặc định.

## 3. Phân biệt `contains`, `indexOf`, `startsWith`, `endsWith`, `equals` và `matches`

Các API đều xử lý chuỗi, nhưng hỏi các câu khác nhau:

| API | Mục đích | Ví dụ |
| --- | --- | --- |
| `text.contains(part)` | Có chứa đoạn nguyên văn ở **bất kỳ đâu** không? | `"file.txt".contains("le.")` → `true` |
| `text.indexOf(part)` | Đoạn nguyên văn xuất hiện **đầu tiên ở vị trí nào**? | `"banana".indexOf("ana")` → `1` |
| `text.lastIndexOf(part)` | Đoạn nguyên văn xuất hiện **cuối cùng ở vị trí nào**? | `"banana".lastIndexOf("ana")` → `3` |
| `text.startsWith(part)` | Chuỗi có **bắt đầu** bằng đoạn này không? | `"file.txt".startsWith("file")` → `true` |
| `text.endsWith(part)` | Chuỗi có **kết thúc** bằng đoạn này không? | `"file.txt".endsWith(".txt")` → `true` |
| `text.equals(other)` | Hai chuỗi có **toàn bộ nội dung** bằng nhau không? | `"java".equals("java")` → `true` |
| `text.matches(regex)` | **Toàn bộ** chuỗi có khớp biểu thức chính quy không? | `"abc123".matches(".*\\d+.*")` → `true` |

Đặc biệt, `String.contains()` không diễn giải dấu `.`, `*`, `+`, `?` hay `\d` theo ngôn ngữ regex. Khi tìm dấu chấm bằng `contains(".")`, nó tìm **ký tự dấu chấm thật**; khi tìm `contains("\\d+")`, nó tìm **ba ký tự** dấu gạch chéo ngược, `d` và `+` trong văn bản, chứ không có nghĩa “một hoặc nhiều chữ số”.

Ví dụ thực thi độc lập `ContainsCompare.java`:

```java
public class ContainsCompare {
    public static void main(String[] args) {
        String text = "Error: file missing";

        System.out.println(text.contains("Error:"));
        System.out.println(text.startsWith("Error:"));
        System.out.println(text.endsWith("Error:"));
        System.out.println(text.indexOf("file"));

        System.out.println("a.b".contains("."));
        System.out.println("abc123".contains("\\d+"));
        System.out.println("abc123".matches(".*\\d+.*"));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 ContainsCompare.java
java ContainsCompare
```

Kết quả:

```text
true
true
false
7
true
false
true
```

Ở đây `"file"` bắt đầu ở vị trí UTF-16 **7**. Khi chỉ cần một giá trị đúng/sai, `contains()` diễn đạt ý định rõ; khi cần cắt đoạn hoặc báo vị trí, `indexOf()` cung cấp chỉ số. `indexOf(part) >= 0` thường có cùng ý nghĩa về sự tồn tại của đoạn ký tự với `contains(part)` khi tham số là một `String` không null.

### `contains()` không kiểm tra ranh giới từ

`"supervisor".contains("admin")` là `false` vì không có chuỗi `"admin"`; trong khi `"superadministrator".contains("admin")` và `"superadmin".contains("admin")` đều là `true`. Phép tìm không biết đâu là **từ**, **quyền hạn** hay **mã sản phẩm**. Nếu hệ thống cần kiểm tra một vai trò bằng `"admin"`, hãy kiểm tra đúng token/giá trị đã phân tách và chuẩn hóa theo hợp đồng; không dùng `contains("admin")` để quyết định cấp quyền.

## 4. Chuỗi rỗng và giá trị `null`

Hai trường hợp cần phân biệt:

- **`""` là chuỗi rỗng hợp lệ.** Mọi chuỗi đều chứa chuỗi rỗng theo định nghĩa API.
- **`null` nghĩa là không có tham chiếu tới đối tượng `String`.** Không thể gọi phương thức instance trên `null`.

```java
String text = "hello";
System.out.println(text.contains("")); // true

String missing = null;
// missing.contains("h"); // NullPointerException
// text.contains(null);   // NullPointerException
```

Đoạn trên là mã minh họa trong thân phương thức (hai dòng có thể ném ngoại lệ đã được comment). Khi nhận dữ liệu có thể vắng mặt, chọn chính sách nghiệp vụ:

```java
public static boolean containsSafely(
        String text, String query) {
    return text != null
            && query != null
            && text.contains(query);
}
```

Đây là **phương thức minh họa để đặt trong class**. Nó trả `false` khi `text` hoặc `query` là `null`; nhưng với `query.equals("")`, nếu `text` không null, nó vẫn trả `true`. Chính sách này thích hợp khi null có nghĩa “không kiểm tra được”; ứng dụng khác có thể muốn báo lỗi đầu vào.

**Điểm dễ bỏ sót:** Nếu giao diện tìm kiếm không muốn từ khóa trống khớp mọi bản ghi, kiểm tra rõ `query.isEmpty()` hoặc `query.isBlank()` trước khi gọi `contains()`. Hai phương thức này khác nhau: `isBlank()` còn nhận các chuỗi chỉ gồm khoảng trắng theo khái niệm whitespace của Java, không có nghĩa tất cả ký tự trống Unicode đều nhất thiết được nhận diện như nhau.

## 5. Phân biệt chữ hoa/thường và tìm kiếm không phân biệt hoa/thường

`contains()` là phép so khớp **phân biệt hoa/thường**:

```java
System.out.println("Introduction to Java".contains("java"));
// false
```

Nếu bài toán tìm kiếm cơ bản muốn bỏ qua khác biệt hoa/thường, có thể đưa **cả hai chuỗi** về chữ thường bằng cùng một `Locale` rồi tìm:

Lưu `ContainsIgnoreCaseDemo.java`:

```java
import java.util.Locale;

public class ContainsIgnoreCaseDemo {
    public static void main(String[] args) {
        String text = "INTRO JAVA";
        String query = "java";

        boolean found = text.toLowerCase(Locale.ROOT)
                .contains(query.toLowerCase(Locale.ROOT));

        System.out.println(found);
        System.out.println(text.contains(query));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ContainsIgnoreCaseDemo.java
java ContainsIgnoreCaseDemo
```

Kết quả:

```text
true
false
```

`Locale.ROOT` là lựa chọn nhất quán cho nhiều tình huống so khớp **không phụ thuộc ngôn ngữ người dùng**. Tuy nhiên, biến đổi chữ hoa/thường có những quy tắc Unicode phức tạp, có thể thay đổi số code point và phụ thuộc ngôn ngữ; cách hạ chữ rồi `contains()` **không tương đương đầy đủ với Unicode case folding, tìm kiếm theo collation, phân tách từ hoặc tìm kiếm không dấu**. Với văn bản đa ngôn ngữ và yêu cầu so khớp ngôn ngữ cụ thể, cần chọn thuật toán/thư viện phù hợp và kiểm thử các trường hợp như `I/i/İ/ı` trong tiếng Thổ Nhĩ Kỳ.

Không tự động dùng cùng phép hạ chữ trong các vị trí yêu cầu **so khớp chính xác theo giao thức**, chẳng hạn khóa định danh phân biệt chữ hoa, chữ ký số hoặc token bảo mật.

## 6. Unicode: cùng cách nhìn nhưng chuỗi con vẫn có thể không khớp

`String.contains()` tìm dãy **UTF-16 code unit** khớp liên tiếp. Nó **không** thực hiện Unicode normalization, không xét grapheme cluster hay chữ có dấu tương đương về mặt hiển thị.

Ví dụ “é” có thể được biểu diễn theo hai cách:

- `"\u00E9"`: một code point dựng sẵn U+00E9.
- `"e\u0301"`: chữ `e` (U+0065) theo sau bởi dấu sắc kết hợp U+0301.

Hai cách thường trông giống nhau, nhưng chuỗi UTF-16 khác nhau. Muốn so khớp theo dạng chuẩn tương đương, có thể chủ động chuẩn hóa **cả nguồn và từ khóa** về cùng Unicode normalization form.

Ví dụ độc lập `ContainsUnicodeDemo.java`:

```java
import java.text.Normalizer;

public class ContainsUnicodeDemo {
    public static void main(String[] args) {
        String composed = "Caf\u00E9";
        String decomposed = "Cafe\u0301";

        System.out.println(composed.contains(decomposed));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println(composed.contains(normalized));

        String emojiText = "A\uD83D\uDE00B"; // A😀B
        System.out.println(
                emojiText.contains("\uD83D\uDE00"));
        System.out.println(
                emojiText.contains("\uD83D"));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 ContainsUnicodeDemo.java
java ContainsUnicodeDemo
```

Kết quả:

```text
false
true
true
true
```

Hai dòng cuối cho thấy một sự khác biệt quan trọng: chuỗi `"A😀B"` chứa cả hai code unit tạo thành emoji, nhưng cũng **chứa riêng high surrogate `\uD83D`** ở mức code unit, nên phép tìm trả `true`. Điều đó không có nghĩa high surrogate là một ký tự Unicode hoàn chỉnh. Nếu cần tìm “ký tự người dùng cảm nhận”, hãy kết hợp xử lý grapheme cluster (ví dụ `\X` trong `java.util.regex.Pattern` trên Java 9+) và các quy tắc nghiệp vụ tương ứng; `contains()` không bảo đảm ranh giới cụm ký tự.

**Không nhầm normalize với bỏ dấu:** `Normalizer.Form.NFC`/`NFD` đưa biểu diễn về dạng chuẩn, không tự biến `"é"` thành `"e"`. Chức năng tìm kiếm không dấu còn cần một chính sách riêng, đặc biệt đối với tiếng Việt.

## 7. Các tình huống áp dụng thực tế

### 7.1. Lọc danh sách theo một đoạn văn bản

Giả sử danh sách tiêu đề đã có trong bộ nhớ và người dùng nhập một từ khóa. Trong ví dụ này, tìm kiếm phân biệt hoa/thường theo `contains()`:

```java
import java.util.List;

public class FilterBySubstringDemo {
    public static void main(String[] args) {
        List<String> titles = List.of(
                "Java String",
                "Java Collection",
                "Spring Boot",
                "Modern Java");

        String query = "Java";

        List<String> selected = titles.stream()
                .filter(title -> title.contains(query))
                .toList();

        System.out.println(selected);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FilterBySubstringDemo.java
java FilterBySubstringDemo
```

Kết quả:

```text
[Java String, Java Collection, Modern Java]
```

`contains()` hợp lý với danh sách nhỏ trong bộ nhớ và khi nghiệp vụ cần một phép tìm nguyên văn. Với dữ liệu lớn, hệ thống tìm kiếm toàn văn, phân tích từ, xếp hạng kết quả hoặc truy vấn cơ sở dữ liệu, cần chọn cơ chế phù hợp (index, full-text search, collation…). Tránh lặp lại việc chuyển hoa/thường hoặc chuẩn hóa cùng nội dung hàng nghìn lần nếu có thể tính trước một lần trong pipeline.

### 7.2. Kiểm tra một đoạn thông báo đã xuất hiện

```java
String message = "WARN: connection timeout";
boolean hasTimeout = message.contains("timeout"); // true
```

Cách này thuận tiện để phát hiện đoạn văn bản trong tình huống đơn giản. Nếu cần phân tích log đúng định dạng, đếm tần suất hoặc kiểm tra mã sự kiện, nên parse trường riêng hoặc dùng định dạng log có cấu trúc; lời nhắn người dùng có thể chứa một cụm từ tương tự mà không tương ứng với cùng sự kiện.

### 7.3. Quyết định dùng công cụ nào

- Chỉ cần **có/không** một đoạn nguyên văn → `contains()`.
- Cần **vị trí bắt đầu** của đoạn → `indexOf()`, trả `-1` nếu không tìm thấy.
- Cần **lấy phần trước/sau** một dấu phân cách → `indexOf()` rồi `substring()`, nhớ kiểm tra `-1`.
- Cần **khớp tiền tố/hậu tố** → `startsWith()`/`endsWith()`.
- Cần **quy tắc regex** → `Pattern`/`Matcher` hoặc `matches()` theo yêu cầu khớp toàn bộ; không đưa regex vào `contains()`.
- Cần **khớp từ, bỏ dấu, không phân biệt locale hoặc phân đoạn Unicode** → làm rõ đặc tả tìm kiếm rồi chọn công cụ thích hợp; `contains()` không tự cung cấp các đặc tính đó.

## 8. Lỗi thường gặp

1. **Đọc `contains()` như “tìm gần đúng”:** thực ra là tìm đoạn liên tiếp chính xác, không hỗ trợ lỗi chính tả, khoảng trắng tùy ý hoặc khoảng cách chỉnh sửa.
2. **Quên phân biệt chữ hoa/thường:** `"Java".contains("java")` là `false`.
3. **Truyền regex với kỳ vọng mẫu sẽ được diễn giải:** `contains("\\d+")` tìm chuỗi nguyên văn `\d+` chứ không tìm chữ số.
4. **Dùng `contains("")` để kiểm tra có dữ liệu:** luôn `true` với chuỗi nhận không null. Muốn kiểm tra chuỗi trống dùng `isEmpty()`; muốn kiểm tra khoảng trắng có thể dùng `isBlank()`.
5. **Không xử lý null:** cả đối tượng nhận null và query null đều dẫn tới `NullPointerException`.
6. **Dùng `contains()` thay kiểm tra token:** tìm `"admin"` trong chuỗi không đồng nghĩa xác minh quyền `admin`; tìm `"cat"` trong `"catalog"` vẫn `true`.
7. **Lấy kết quả boolean làm vị trí:** `contains()` chỉ trả `boolean`; `indexOf()` mới trả index.
8. **Không chuẩn hóa Unicode khi yêu cầu tương đương chuẩn:** hai biểu diễn chữ có dấu có thể nhìn giống nhau nhưng trả `false`.
9. **Coi chuỗi con của UTF-16 là ký tự Unicode đầy đủ:** có thể tìm trúng nửa surrogate pair; `contains()` không xét ranh giới code point/grapheme.
10. **Gọi `toLowerCase()` theo default locale không kiểm soát:** kết quả có thể đổi theo môi trường; chọn locale và chính sách so khớp theo nghiệp vụ.
11. **Quá lạm dụng kiểm tra văn bản tự do cho logic nghiệp vụ:** với mã trạng thái, quyền, định danh và định dạng có cấu trúc, parse hoặc so sánh trường chính xác thường đáng tin hơn.

## 9. Câu hỏi tự kiểm tra

Với `String s = "Java Core"`, hãy dự đoán:

| Biểu thức | Kết quả | Vì sao |
| --- | --- | --- |
| `s.contains("Java")` | `true` | Tiền tố cũng là chuỗi con |
| `s.contains("a C")` | `true` | Đoạn liên tiếp trải qua dấu cách |
| `s.contains("Core")` | `true` | Hậu tố cũng là chuỗi con |
| `s.contains("core")` | `false` | Sai khác chữ hoa/thường |
| `s.contains("JavaCore")` | `false` | Thiếu dấu cách |
| `s.contains("")` | `true` | Chuỗi rỗng khớp tại mọi chuỗi |
| `s.contains("Java Core!")` | `false` | Đối số dài và khác nội dung |
| `s.indexOf("Core")` | `5` | `indexOf` trả vị trí, không phải boolean |

Tự đặt thêm câu hỏi: nếu `s` là `null` thì `s.contains("Java")` sẽ thế nào? Câu trả lời là **`NullPointerException`**, vì không có đối tượng để gọi phương thức.

**Ghi nhớ:** `contains(CharSequence)` là phép kiểm tra **có hay không một dãy ký tự liên tiếp chính xác** trong `String`. Nó trả `boolean`, **phân biệt hoa/thường**, **không dùng regex**, **không tự chuẩn hóa Unicode**, và **`contains("")` luôn đúng với chuỗi nhận không null**. Khi cần vị trí, quy tắc tìm theo từ/ngôn ngữ hoặc so khớp gần đúng, hãy dùng API/thuật toán chuyên biệt.
