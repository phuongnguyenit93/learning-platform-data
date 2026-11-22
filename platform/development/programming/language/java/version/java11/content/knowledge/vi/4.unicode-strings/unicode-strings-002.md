# `strip()`, `stripLeading()` và `stripTrailing()` trong Java 11: xử lý khoảng trắng Unicode ở biên chuỗi

## 1. Mục tiêu bài học

Dữ liệu văn bản từ biểu mẫu, tệp tin và API thường có khoảng trắng vô tình xuất hiện ở đầu hoặc cuối: dấu cách, tab, ký tự xuống dòng và nhiều loại khoảng trắng Unicode. Từ **Java 11**, lớp `java.lang.String` có ba phương thức xử lý trường hợp này:

- `strip()`: loại bỏ khoảng trắng được Java nhận diện **ở cả đầu lẫn cuối**.
- `stripLeading()`: chỉ loại bỏ khoảng trắng **ở đầu**.
- `stripTrailing()`: chỉ loại bỏ khoảng trắng **ở cuối**.

Điểm cốt lõi của bài: ba phương thức dùng tiêu chí `Character.isWhitespace(int)`. Vì thế chúng xử lý được nhiều khoảng trắng Unicode mà `trim()` không xử lý, **nhưng không xóa mọi ký tự trông giống khoảng trắng**. Sự khác biệt vẫn cần chú ý trên JDK hiện đại, không chỉ trên Java 11.

Sau bài này, người học cần tự xác định được nên dùng phương thức nào, dự đoán kết quả trên chuỗi có khoảng trắng Unicode, kiểm thử các ngoại lệ như NBSP và tránh sửa nhầm dữ liệu có khoảng trắng mang ý nghĩa nghiệp vụ.

## 2. Cơ chế của ba phương thức

Giả sử chuỗi ban đầu là `"  Java 11 \n"`, trong đó `\n` là một ký tự xuống dòng, không phải hai ký tự `\` và `n`:

| Phương thức | Loại bỏ phần nào? | Giá trị nhận được (biểu diễn bằng Java literal) |
| --- | --- | --- |
| `s.strip()` | Khoảng trắng đầu và cuối | `"Java 11"` |
| `s.stripLeading()` | Chỉ phần đầu | `"Java 11 \n"` |
| `s.stripTrailing()` | Chỉ phần cuối | `"  Java 11"` |

Cả ba đều là phương thức **không có tham số** và trả về một `String`. Chuỗi gốc không bị thay đổi vì `String` là immutable.

```java
String original = "  Java 11  ";
String cleaned = original.strip();

System.out.println("[" + original + "]");
System.out.println("[" + cleaned + "]");
```

Đoạn mã trên nằm trong một phương thức và sẽ in:

```text
[  Java 11  ]
[Java 11]
```

Những trường hợp biên quan trọng:

- `"".strip()` trả về `""`.
- Nếu toàn bộ chuỗi chỉ gồm các code point được `Character.isWhitespace(int)` coi là khoảng trắng, kết quả của cả ba phương thức là `""`.
- Nếu phần đầu hoặc cuối không có khoảng trắng phù hợp, giá trị chuỗi không thay đổi.
- Chỉ xóa ở **biên** chuỗi: `" A  B ".strip()` là `"A  B"`, vẫn giữ nguyên hai dấu cách ở giữa.
- Gọi `strip()`, `stripLeading()` hoặc `stripTrailing()` trên tham chiếu `null` sẽ gây `NullPointerException`. Chuỗi rỗng `""` và tham chiếu `null` là hai tình huống khác nhau.
- Không dùng phép so sánh `==` để kết luận hai chuỗi có cùng nội dung; dùng `equals` khi cần so sánh giá trị.

## 3. “Khoảng trắng” trong Java 11 thực sự là gì?

### 3.1. Java xét Unicode code point

Unicode có nhiều ký tự phân cách ngoài khoảng trắng thông thường U+0020. `String.strip*` xét các **Unicode code point** từ rìa chuỗi và sử dụng `Character.isWhitespace(int)` để quyết định có bỏ đi hay không.

Điều này chính xác hơn cách hiểu “xóa dấu cách ASCII” nhưng **không đồng nghĩa** với việc xóa tất cả ký tự vô hình hoặc tất cả ký tự có chữ “space” trong tên Unicode.

| Ký tự | Mã Unicode | `Character.isWhitespace(int)` trên Java 11 | `strip()` ở biên |
| --- | --- | --- | --- |
| SPACE (dấu cách thường) | U+0020 | `true` | Xóa |
| HORIZONTAL TAB (`\t`) | U+0009 | `true` | Xóa |
| LINE FEED (`\n`) | U+000A | `true` | Xóa |
| EM SPACE | U+2003 | `true` | Xóa |
| IDEOGRAPHIC SPACE | U+3000 | `true` | Xóa |
| NO-BREAK SPACE (NBSP) | U+00A0 | `false` | **Giữ lại** |
| FIGURE SPACE | U+2007 | `false` | **Giữ lại** |
| NARROW NO-BREAK SPACE | U+202F | `false` | **Giữ lại** |
| ZERO WIDTH SPACE | U+200B | `false` | **Giữ lại** |

Ba khoảng trắng **không ngắt dòng** U+00A0, U+2007 và U+202F là ngoại lệ được mô tả rõ trong tài liệu `Character.isWhitespace`. `Character.isSpaceChar(int)` có thể trả `true` đối với chúng nhưng **đó là một hàm phân loại khác**, không phải quy tắc mà `strip()` sử dụng.

Ví dụ:

```java
System.out.println(Character.isWhitespace(0x2003)); // true
System.out.println(Character.isWhitespace(0x00A0)); // false
System.out.println(Character.isSpaceChar(0x00A0));   // true
```

Cú pháp `\u2003` hoặc `\u00A0` cho phép thể hiện ký tự Unicode trong string literal mà không phải dựa vào việc người đọc có nhìn thấy một ký tự khoảng trắng đặc biệt trên màn hình hay không.

### 3.2. Code point khác với số phần tử `char`

Trong Java, `String` lưu dữ liệu theo đơn vị mã UTF-16. Có những ký tự Unicode được biểu diễn bằng **hai đơn vị `char`** (surrogate pair), nhưng vẫn chỉ là **một Unicode code point**. API `Character.isWhitespace(int)` nhận code point; do đó nếu sau này tự viết thuật toán cắt khoảng trắng, hãy duyệt bằng `codePointAt`, `codePointBefore` và `Character.charCount` thay vì giả định mỗi ký tự chiếm đúng một `char`.

Ba phương thức `strip*` đã xử lý việc duyệt code point cho người dùng. Không cần tự xử lý UTF-16 khi chỉ cần quy tắc khoảng trắng chuẩn Java.

## 4. So sánh `strip()` và `trim()`

`trim()` vẫn là phương thức hợp lệ của Java, nhưng có quy tắc khác: nó bỏ các ký tự **ở đầu/cuối có mã UTF-16 không lớn hơn U+0020**. Còn `strip()` dựa vào `Character.isWhitespace(int)`, nên hiểu được nhiều khoảng trắng Unicode như U+2003, U+3000.

| Dữ liệu đầu vào | `strip()` | `trim()` | Vì sao? |
| --- | --- | --- | --- |
| `" \tJava\n "` | `"Java"` | `"Java"` | Các ký tự biên đều thuộc nhóm được cả hai xử lý |
| `"\u2003Java\u2003"` | `"Java"` | Giữ nguyên | EM SPACE không nằm trong khoảng mã ≤ U+0020 |
| `"\u00A0Java\u00A0"` | Giữ nguyên | Giữ nguyên | NBSP không được `isWhitespace` nhận diện và có mã > U+0020 |
| `"A  B"` | `"A  B"` | `"A  B"` | Khoảng trắng nằm **bên trong** |
| `"\u0000A\u0000"` | Giữ nguyên | `"A"` | U+0000 có mã ≤ U+0020 nhưng không phải Java whitespace |

**Cách chọn:** nếu mục tiêu là loại bỏ khoảng trắng ở biên chuỗi trong dữ liệu văn bản thông thường, `strip()` diễn đạt ý định tốt và nhận diện Unicode rộng hơn `trim()`. Nếu hợp đồng dữ liệu quy định chính xác chỉ xử lý một nhóm ký tự khác, hãy thực hiện theo hợp đồng đó và viết test; không tự suy ra rằng `strip()` là phép “dọn sạch mọi ký tự vô hình”.

Các cách cắt/biến đổi khác không tương đương: `replace(" ", "")` xóa dấu cách ở **mọi vị trí**, còn chuẩn hóa Unicode (NFC/NFKC) là một vấn đề riêng, không phải chức năng của `strip*`.

## 5. Chương trình Java 11 chạy độc lập và đầu ra chính xác

Ví dụ này dùng chuỗi có EM SPACE, dấu cách ASCII, tab và xuống dòng. Hàm `show` biến ký tự khó nhìn thấy thành nhãn `<EM_SPACE>`, `<SP>`, `<TAB>`, `<LF>`, `<NBSP>` và `<ZERO_WIDTH_SPACE>` để việc so sánh không phụ thuộc font chữ.

Tạo tệp **`StripMethodsDemo.java`**:

```java
public class StripMethodsDemo {

    public static void main(String[] args) {
        String input = "\u2003 \tJava 11\n \u2003";

        System.out.println("input:         " + show(input));
        System.out.println("strip:         " + show(input.strip()));
        System.out.println("stripLeading:  " + show(input.stripLeading()));
        System.out.println("stripTrailing: " + show(input.stripTrailing()));
        System.out.println("trim:          " + show(input.trim()));

        String nbsp = "\u00A0Java\u00A0";
        String zeroWidth = "\u200BJava\u200B";
        System.out.println("NBSP:          " + show(nbsp.strip()));
        System.out.println("ZERO WIDTH:    " + show(zeroWidth.strip()));

        System.out.println("blank EM:      " + "\u2003\t".isBlank());
        System.out.println("blank NBSP:    " + "\u00A0".isBlank());
        System.out.println("middle:        " + show(" A  B ".strip()));
    }

    private static String show(String text) {
        return "[" + text
                .replace("\u2003", "<EM_SPACE>")
                .replace("\u00A0", "<NBSP>")
                .replace("\u200B", "<ZERO_WIDTH_SPACE>")
                .replace("\t", "<TAB>")
                .replace("\n", "<LF>")
                .replace(" ", "<SP>")
                + "]";
    }
}
```

Biên dịch và chạy với **JDK 11 hoặc JDK mới hơn có hỗ trợ `--release 11`**:

```bash
javac --release 11 -encoding UTF-8 StripMethodsDemo.java
java StripMethodsDemo
```

Kết quả tiêu chuẩn:

```text
input:         [<EM_SPACE><SP><TAB>Java<SP>11<LF><SP><EM_SPACE>]
strip:         [Java<SP>11]
stripLeading:  [Java<SP>11<LF><SP><EM_SPACE>]
stripTrailing: [<EM_SPACE><SP><TAB>Java<SP>11]
trim:          [<EM_SPACE><SP><TAB>Java<SP>11<LF><SP><EM_SPACE>]
NBSP:          [<NBSP>Java<NBSP>]
ZERO WIDTH:    [<ZERO_WIDTH_SPACE>Java<ZERO_WIDTH_SPACE>]
blank EM:      true
blank NBSP:    false
middle:        [A<SP><SP>B]
```

**Giải thích từng kết quả:**

1. `input.strip()` xóa toàn bộ chuỗi ký tự hợp lệ ở **hai biên**, nhưng giữ dấu cách giữa “Java” và “11”.
2. `stripLeading()` chỉ bỏ phần `EM SPACE + SPACE + TAB` ở đầu; các ký tự `LF + SPACE + EM SPACE` cuối chuỗi vẫn còn.
3. `stripTrailing()` làm điều ngược lại: giữ nguyên ba ký tự ở đầu, cắt toàn bộ nhóm cuối.
4. `trim()` không loại bỏ ký tự nào ở ví dụ này vì cả **ký tự đầu tiên và cuối cùng đều là U+2003**, vượt phạm vi mà `trim()` xử lý. Nó không “nhảy qua” U+2003 để xóa SPACE hay TAB phía trong.
5. NBSP và ZERO WIDTH SPACE còn nguyên vì không thuộc tập `Character.isWhitespace`.
6. `isBlank()` cũng sử dụng ý niệm Java whitespace, nên chuỗi chỉ có EM SPACE/TAB là blank nhưng chuỗi chỉ có NBSP **không** blank.
7. Hai dấu cách ở giữa `A` và `B` vẫn được giữ; `strip()` không rút gọn khoảng trắng nội bộ.

Chương trình chỉ dùng `java.lang`, không cần import hay thư viện ngoài. Các dấu kiểm tra được in thành nhãn nên đầu ra dễ đối chiếu kể cả khi môi trường console không hiển thị chính xác các khoảng trắng Unicode.

## 6. Áp dụng đúng tình huống

### 6.1. Chuẩn hóa nhãn hoặc trường nhập của người dùng

Nếu hợp đồng nhập liệu cho phép người dùng gõ thừa khoảng trắng **ở hai đầu**, có thể kiểm tra null, kiểm tra blank, sau đó `strip()`:

```java
static String requireDisplayName(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Display name is required");
    }
    return raw.strip();
}
```

Đây là **phương thức minh họa**, đặt bên trong một lớp. `isBlank()` có từ Java 11 và cùng dựa trên `Character.isWhitespace`. Sau phép kiểm tra này, `raw.strip()` có ít nhất một code point không thuộc Java whitespace; phương thức **không** xóa các dấu cách ở giữa tên.

Lưu ý: nếu hệ thống coi NBSP hoặc ký tự vô hình là không hợp lệ, `isBlank()` và `strip()` **chưa đủ** để thực thi chính sách ấy; cần thêm kiểm tra được định nghĩa rõ.

### 6.2. Khi chỉ được phép sửa một bên

- `stripLeading()` phù hợp nếu yêu cầu chỉ bỏ khoảng trắng đầu dòng, còn các ký tự cuối dòng phải được giữ theo hợp đồng dữ liệu.
- `stripTrailing()` phù hợp nếu chỉ cần loại bỏ khoảng trắng ở cuối một giá trị, nhưng vẫn cần giữ thụt đầu dòng.
- `strip()` phù hợp khi cả hai biên được coi là khoảng trắng thừa.

**Ví dụ cụ thể:** với chuỗi `"  | cột 1 | cột 2 |  "`, `stripTrailing()` xóa phần dấu cách cuối nhưng vẫn giữ hai dấu cách trước dấu `|` đầu tiên. Nếu thụt đầu dòng là một phần của định dạng, lựa chọn một bên giúp bảo toàn dữ liệu có chủ đích.

### 6.3. Không tùy tiện xóa khoảng trắng trong dữ liệu nhạy cảm

Đừng tự động gọi `strip()` cho **mật khẩu, token, chữ ký số, thông điệp phải băm, chuỗi dùng đối chiếu byte chính xác** hoặc định dạng văn bản mà khoảng trắng biên có ý nghĩa. Hai chuỗi khác nhau có thể thành cùng một giá trị sau khi cắt, làm mất thông tin hoặc thay đổi dữ liệu đã ký.

Với mã định danh, khóa bản ghi, địa chỉ email hoặc thông số giao thức, hãy tuân thủ **quy tắc chuẩn hóa được hệ thống định nghĩa**; “trông như một đoạn văn bản” không có nghĩa là luôn được phép cắt khoảng trắng.

### 6.4. Không nhầm với tách dòng hoặc chuẩn hóa nội bộ

`"  A \n B  ".strip()` tạo chuỗi `"A \n B"`: ký tự xuống dòng và dấu cách **ở giữa** vẫn còn. Nếu cần tách từng dòng rồi loại bỏ khoảng trắng trên từng dòng, phải làm từng bước rõ ràng (ví dụ `lines()` kết hợp `map(String::strip)`). Việc này có thể thay đổi cấu trúc tệp nên cần kiểm thử theo định dạng dữ liệu.

```java
String source = "  A  \n  B  ";
String result = source.lines()
        .map(String::strip)
        .collect(java.util.stream.Collectors.joining("\n"));
// result là "A\nB".
```

Đây là **trích đoạn** cần nằm trong phương thức hoặc JShell. `lines()` là API Java 11; việc nối lại bằng `"\n"` có thể làm mất định dạng xuống dòng gốc và newline cuối, vì vậy không áp dụng khi cần bảo toàn byte hoặc format đầu vào.

## 7. Nếu nghiệp vụ muốn xóa cả NBSP ở hai biên?

Không nên sửa ý nghĩa `Character.isWhitespace` bằng cách tưởng rằng `strip()` đã xử lý NBSP. Trước tiên phải quyết định **đây có thực sự là yêu cầu nghiệp vụ không**. Nếu có, có thể chủ động mở rộng tập ký tự tại biên để bao gồm U+00A0, U+2007 và U+202F.

Ví dụ sau là **hai phương thức tĩnh đặt trong một lớp Java**, không phải toàn bộ chương trình có `main`:

```java
static boolean isBoundaryWhitespace(int codePoint) {
    return Character.isWhitespace(codePoint)
            || codePoint == 0x00A0
            || codePoint == 0x2007
            || codePoint == 0x202F;
}

static String stripIncludingNbsp(String input) {
    if (input == null) {
        throw new IllegalArgumentException("input is required");
    }

    int from = 0;
    int to = input.length();

    while (from < to) {
        int cp = input.codePointAt(from);
        if (!isBoundaryWhitespace(cp)) {
            break;
        }
        from += Character.charCount(cp);
    }

    while (from < to) {
        int cp = input.codePointBefore(to);
        if (!isBoundaryWhitespace(cp)) {
            break;
        }
        to -= Character.charCount(cp);
    }

    return input.substring(from, to);
}
```

Ví dụ `stripIncludingNbsp("\u00A0Java\u00A0")` cho kết quả `"Java"`, còn `stripIncludingNbsp("\u00A0")` cho `""`. Cách duyệt theo code point bảo toàn các cặp surrogate hợp lệ; hai biến `from` và `to` luôn là chỉ số UTF-16 hợp lệ của `substring`.

Chỉ đưa phương thức mở rộng này vào dự án nếu đã có chính sách dữ liệu và test phù hợp. Việc xóa NBSP có thể làm mất ý nghĩa “không được ngắt dòng” trong nội dung văn bản. `Character.isSpaceChar(int)` cũng không thể thay trực tiếp cho `Character.isWhitespace(int)` vì nó có tập quy tắc khác, đặc biệt đối với tab hoặc dấu xuống dòng.

Nếu sử dụng phương thức mở rộng, kiểm tra chuỗi rỗng sau khi cắt bằng `.isEmpty()`; kiểm tra `.isBlank()` trực tiếp trên đầu vào vẫn không coi NBSP đơn lẻ là blank.

## 8. Hiệu năng, độ an toàn và khả năng bảo trì

- **Chi phí:** ba phương thức duyệt từ biên chuỗi để tìm vị trí cần giữ; thời gian tương ứng với số ký tự cần kiểm tra và không cần regex. Đây là lựa chọn tự nhiên cho bước làm sạch dữ liệu thông thường.
- **Bất biến:** chúng trả về `String` và không sửa đối tượng ban đầu. Không suy luận về việc JVM có tái sử dụng cùng reference hay tạo object mới; hãy kiểm tra **giá trị**.
- **Tối ưu:** thường chỉ cần xử lý một lần tại ranh giới nhận dữ liệu, tránh lặp lại `strip()` ở nhiều tầng. Nếu ứng dụng thực sự gặp điểm nghẽn, đo bằng profiler/benchmark đại diện trước khi tự triển khai logic tối ưu.
- **Đồng nhất:** nên đặt chính sách chuẩn hóa ở cùng một vị trí (ví dụ lớp validation hoặc boundary adapter), dùng test cho Unicode edge case và theo dõi các thay đổi nghiệp vụ. Không để nơi dùng `trim()`, nơi dùng `strip()`, nơi tự thay NBSP mà không có lý do.
- **Tương thích:** `strip()`, `stripLeading()`, `stripTrailing()` và `isBlank()` đều được thêm từ **Java 11** và vẫn có trên các JDK được sử dụng hiện nay. Nếu ứng dụng phải chạy trên Java 8, các phương thức đó không có sẵn; cần chọn runtime hoặc giải pháp tương thích theo yêu cầu thực tế. `stripIndent()` là API xuất hiện ở Java sau 11, không sử dụng trong mã biên dịch mục tiêu Java 11.
- **Unicode có thể phát triển:** tập code point mà thư viện Java phân loại phụ thuộc đặc tả và dữ liệu Unicode được JDK sử dụng. Với những ký tự đầu vào quan trọng, hãy có test cụ thể trên các phiên bản runtime mà dự án hỗ trợ.

## 9. Lỗi thường gặp và cách khắc phục

| Hiểu nhầm / lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| “`strip()` xóa mọi khoảng trắng Unicode” | NBSP, FIGURE SPACE, NARROW NBSP, ZERO WIDTH SPACE vẫn còn | Hiểu tiêu chí `Character.isWhitespace(int)`; thêm chính sách rõ nếu cần |
| Dùng `trim()` thay `strip()` trong dữ liệu có EM SPACE | Khoảng trắng U+2003 vẫn tồn tại | Dùng `strip()` nếu mục tiêu là Java whitespace |
| Muốn giữ khoảng trắng đầu nhưng gọi `strip()` | Mất indentation quan trọng | Dùng `stripTrailing()` |
| Tưởng `stripLeading()` xóa hết whitespace | Ký tự cuối vẫn còn | Chọn `strip()` khi muốn xóa cả hai đầu |
| Tưởng `strip()` làm gọn mọi dấu cách trong chuỗi | Khoảng trắng nội bộ không đổi | Xử lý nội bộ bằng quy tắc riêng, có test |
| Gọi phương thức trên `null` | `NullPointerException` | Kiểm tra null theo hợp đồng đầu vào |
| Tự động cắt password/token/dữ liệu ký | Thay đổi dữ liệu nguyên bản | Bảo toàn input khi giao thức yêu cầu |
| Dùng `isBlank()` để phát hiện mọi chuỗi trông rỗng | NBSP không được coi là blank | Xác định tập ký tự chấp nhận và kiểm tra đúng tập |
| So sánh `stripped == original` | Dựa vào identity không đảm bảo | So sánh nội dung bằng `equals` |
| Tưởng `String.length()` là số Unicode code point | Có thể tính sai khi có ký tự bổ sung | Khi cần đếm code point, dùng `codePointCount` |

## 10. Bài luyện tập tự kiểm tra

Cho các biểu thức Java 11 sau, hãy dự đoán kết quả **trước khi chạy**:

1. `" \tHello\n ".stripLeading()` còn ký tự nào ở cuối?
2. `"\u2003Hello\u2003".trim()` và `"\u2003Hello\u2003".strip()` có giống nhau không?
3. `" A  B ".strip()` có bao nhiêu dấu cách giữa `A` và `B`?
4. `"\u00A0".strip().isEmpty()` và `"\u00A0".isBlank()` cho kết quả gì?
5. Dùng phương thức nào để bỏ khoảng trắng cuối nhưng giữ nguyên đầu dòng?

**Đáp án và lý do:**

1. Kết quả `"Hello\n "`: `stripLeading()` chỉ bỏ SPACE và TAB đầu chuỗi.
2. Không: `trim()` giữ hai U+2003, còn `strip()` trả `"Hello"`.
3. Hai dấu cách; `strip()` không tác động đến khoảng trắng nằm giữa hai chữ.
4. Cả hai là `false`, vì NBSP không thuộc `Character.isWhitespace`.
5. `stripTrailing()`.

## 11. Ghi nhớ và tài liệu chính thức

- **`strip()`** = cắt Java whitespace ở **hai đầu**.
- **`stripLeading()`** = cắt **đầu trái**.
- **`stripTrailing()`** = cắt **đầu phải**.
- **`Character.isWhitespace(int)`** quyết định code point nào được cắt; **NBSP không thuộc tập này**.
- **`trim()` vẫn hợp lệ nhưng khác quy tắc**; chọn theo contract, không chọn theo thói quen.
- Khi cần bảo toàn chính xác dữ liệu, **không tự ý cắt khoảng trắng**.

Tài liệu API chính thức, còn phù hợp cho mã Java 11 và các JDK mới hơn:

- `String` (Java SE 11), phần `strip`, `stripLeading`, `stripTrailing`, `trim`, `isBlank`, `lines`: https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html
- `Character` (Java SE 11), phần `isWhitespace(int)` và `isSpaceChar(int)`: https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Character.html
- `String` (Java SE 21), để đối chiếu sự hiện diện của API trên JDK mới: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html
