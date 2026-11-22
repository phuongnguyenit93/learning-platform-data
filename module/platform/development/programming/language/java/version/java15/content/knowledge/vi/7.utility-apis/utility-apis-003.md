# Phân biệt chuỗi rỗng, chuỗi blank và null trong Java 15+

## Mục tiêu

Khi xử lý đầu vào từ form, REST API, file cấu hình, database hoặc một đối tượng Java, ba trường hợp **`null`**, **chuỗi rỗng `""`** và **chuỗi chỉ chứa khoảng trắng (blank)** thường có ý nghĩa khác nhau. Nhầm lẫn giữa chúng có thể dẫn đến `NullPointerException`, bỏ lọt dữ liệu không hợp lệ, ghi đè giá trị quan trọng hoặc thay đổi ý nghĩa của yêu cầu cập nhật.

Sau bài này, bạn có thể:

1. Giải thích chính xác `null`, `isEmpty()`, `isBlank()` và phân biệt kết quả của chúng.
2. Kiểm tra chuỗi an toàn với `null`, phân loại giá trị theo yêu cầu nghiệp vụ.
3. Nhận diện một số ký tự Unicode **trông như dấu cách nhưng không được `String.isBlank()` coi là whitespace**.
4. Chọn giữa `isEmpty()`, `isBlank()`, `strip()` và `trim()` khi kiểm tra hoặc chuẩn hóa đầu vào.
5. Viết ví dụ Java 15+ có thể biên dịch/chạy, dự đoán stdout và tránh những lỗi thường gặp.

Các API được trình bày đều đang được hỗ trợ trong Java hiện đại: `String.isEmpty()`, `String.isBlank()`, `String.strip()` và `Character.isWhitespace()`. `isBlank()` và `strip()` có từ Java 11, nên sử dụng trực tiếp trong dự án đặt mức Java 15 hoặc mới hơn; không cần thư viện ngoài hay API preview.

## 1. Ba trạng thái khác nhau

| Giá trị Java | Ý nghĩa | `length()` | `isEmpty()` | `isBlank()` |
| --- | --- | ---: | --- | --- |
| `null` | Biến tham chiếu **không trỏ tới một đối tượng String** | Không gọi được | Không gọi được | Không gọi được |
| `""` | Có đối tượng String với **0 đơn vị mã UTF-16** | 0 | `true` | `true` |
| `"   "` (3 dấu cách) | Có String chứa 3 ký tự whitespace | 3 | `false` | `true` |
| `"\t\n"` | Có String chứa tab và LF | 2 | `false` | `true` |
| `" Java "` | Có chữ cái, dù có dấu cách ở hai đầu | 6 | `false` | `false` |
| `"Java"` | Có nội dung chữ thông thường | 4 | `false` | `false` |

**`null` không phải một String đặc biệt có độ dài 0.** Nó là giá trị của một biến tham chiếu khi chưa trỏ đến đối tượng nào. Do đó, `value.length()`, `value.isEmpty()`, `value.isBlank()` hay `value.strip()` đều ném `NullPointerException` khi `value == null`.

**Chuỗi rỗng là một giá trị String hợp lệ:** `""` có độ dài 0. Không có bất kỳ ký tự nào để kiểm tra, nên `isBlank()` trả về `true` cho chuỗi rỗng. Vì vậy tập hợp các chuỗi empty là **tập con** của các chuỗi blank:

- `isEmpty() == true` luôn suy ra `isBlank() == true` đối với một String khác `null`.
- `isBlank() == true` **không** suy ra `isEmpty() == true`; `"   "` là ví dụ phản chứng.
- `null` không có kết quả boolean từ hai phương thức trên, trừ khi bạn tự xử lý `null` trước.

Một String gọi là **blank** khi nó rỗng, hoặc **mọi code point** trong chuỗi được xác định là whitespace theo `Character.isWhitespace(int)`. Đây là quy tắc API của Java, **không đồng nghĩa** với “mọi ký tự con người nhìn thấy như khoảng trắng”.

## 2. Các phương thức cần biết

### `String.isEmpty()`: không có ký tự nào

`value.isEmpty()` tương đương với kiểm tra `value.length() == 0` cho một String **khác `null`**. Dùng phương thức này khi yêu cầu là **không có dữ liệu ký tự**:

```java
"".isEmpty();        // true
" ".isEmpty();       // false
"\n".isEmpty();      // false
"Java".isEmpty();    // false
```

Những dòng trên là **biểu thức minh họa**, không phải các câu lệnh chương trình đầy đủ để đứng độc lập trong một class. `isEmpty()` không bỏ qua dấu cách hay ký tự điều khiển.

### `String.isBlank()`: không có ký tự có nội dung theo quy tắc whitespace Java

`value.isBlank()` trả về `true` nếu String rỗng **hoặc** chỉ chứa các code point mà `Character.isWhitespace(int)` nhận diện là whitespace. Ví dụ:

```java
"".isBlank();        // true
"   ".isBlank();     // true
"\t\n".isBlank();    // true
" Java ".isBlank();  // false
```

Phương thức này thường phù hợp hơn `isEmpty()` để kiểm tra trường nhập liệu bắt buộc, vì người dùng có thể gõ toàn space hoặc tab. Tuy nhiên, nó vẫn phải được gọi **sau khi kiểm tra `null`**.

### `String.strip()`: loại whitespace ở hai đầu, không kiểm tra null

`strip()` tạo ra kết quả đã loại bỏ whitespace hai đầu theo `Character.isWhitespace`. Nó không thay đổi đối tượng String gốc vì String bất biến. Các API liên quan là `stripLeading()` và `stripTrailing()`.

```java
"  Java  ".strip().equals("Java"); // true
"  ".strip().isEmpty();           // true
"".strip().isEmpty();             // true
```

Đối với String khác `null`, `value.isBlank()` và `value.strip().isEmpty()` cho cùng kết luận về việc chuỗi chỉ có whitespace. Nếu chỉ cần điều kiện boolean, **dùng `isBlank()` trực tiếp**, không cần tạo thêm giá trị String đã strip.

### `String.trim()`: khác `strip()` ở phạm vi ký tự

`trim()` loại các ký tự ở đầu/cuối có mã UTF-16 **không vượt quá U+0020**. `strip()` dùng `Character.isWhitespace` nên xử lý được **nhiều** dấu cách Unicode mà `trim()` không loại bỏ, nhưng cũng có một số ký tự thuộc tập `trim()` mà `strip()` không xem là whitespace (chẳng hạn U+0000). Vì vậy, hai phương thức **không thay thế hoàn toàn cho nhau**.

Ví dụ: **EM SPACE U+2003** là whitespace theo `Character.isWhitespace`. Với một String chỉ chứa EM SPACE:

- `isEmpty()` là `false`.
- `isBlank()` là `true`.
- `trim().isEmpty()` là `false` vì `trim()` không loại được U+2003.
- `strip().isEmpty()` là `true`.

Với ứng dụng Java 15+ đang xây dựng mới, chọn `strip()` khi muốn xóa **whitespace theo quy tắc Java**, và dùng `isBlank()` khi chỉ cần biết có nội dung ý nghĩa hay không. Nếu giao thức dữ liệu có quy tắc riêng về ký tự được phép, bạn vẫn phải kiểm tra theo **quy tắc giao thức đó**.

## 3. Kiểm tra null an toàn và phân loại rõ bốn tình huống

Mẫu điều kiện phổ biến để biết String **có nội dung**:

```java
String value = /* lấy từ đầu vào */;
boolean hasText = value != null && !value.isBlank();
```

Đây là **đoạn minh họa**, dòng gán phải được thay bằng giá trị thật trước khi biên dịch. Toán tử `&&` được đánh giá **ngắn mạch**: nếu `value != null` là `false`, Java **không gọi** `value.isBlank()`, nên không phát sinh `NullPointerException`.

Tránh viết ngược thứ tự:

```java
// Sai nếu value có thể là null:
boolean wrong = !value.isBlank() && value != null;
```

Nếu nghiệp vụ cần phân biệt rõ cả **null**, **empty**, **blank nhưng không empty**, và **có ký tự khác whitespace**, hãy phân loại theo thứ tự:

```java
static String classify(String value) {
    if (value == null) {
        return "NULL";
    }
    if (value.isEmpty()) {
        return "EMPTY";
    }
    if (value.isBlank()) {
        return "BLANK";
    }
    return "TEXT";
}
```

Đây là một **phương thức minh họa** cần đặt trong class. Thứ tự kiểm tra rất quan trọng: do `"".isBlank()` là `true`, nếu kiểm tra `isBlank()` trước thì nhánh `EMPTY` sẽ không bao giờ đạt được.

**Không dùng `==` để so sánh nội dung String.** Ví dụ, `new String("")` có thể là một đối tượng khác literal `""`, dù cả hai đều rỗng:

```java
String text = new String("");
System.out.println(text == "");       // false: so sánh tham chiếu
System.out.println(text.isEmpty());   // true: kiểm tra nội dung
System.out.println("".equals(text));  // true: so sánh giá trị
```

`"".equals(value)` là cách so sánh rỗng **an toàn với null**: nếu `value` là `null` nó trả về `false`. Tuy nhiên, cách này không thay thế `isBlank()` khi đầu vào có thể chứa whitespace.

## 4. Ví dụ hoàn chỉnh Java 15+: sáu dạng chuỗi và Unicode khó nhìn

Tạo file **`EmptyBlankNullDemo.java`**:

```java
public class EmptyBlankNullDemo {
    private static String classify(String value) {
        if (value == null) {
            return "NULL";
        }
        if (value.isEmpty()) {
            return "EMPTY";
        }
        if (value.isBlank()) {
            return "BLANK";
        }
        return "TEXT";
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private static void inspect(String name, String value) {
        if (value == null) {
            System.out.println(name
                    + " -> NULL, length=n/a, empty=n/a, blank=n/a");
            return;
        }
        System.out.println(name + " -> " + classify(value)
                + ", length=" + value.length()
                + ", empty=" + value.isEmpty()
                + ", blank=" + value.isBlank());
    }

    public static void main(String[] args) {
        String nbsp = String.valueOf((char) 0x00A0);
        String emSpace = String.valueOf((char) 0x2003);

        inspect("null", null);
        inspect("empty", "");
        inspect("spaces", "   ");
        inspect("tab+LF", "\t\n");
        inspect("text", "Java");
        inspect("NBSP", nbsp);
        inspect("EM SPACE", emSpace);

        System.out.println("hasText(null)=" + hasText(null));
        System.out.println("hasText(spaces)=" + hasText(" \t "));
        System.out.println("hasText(text)=" + hasText(" A "));
        System.out.println("trim keeps EM SPACE="
                + emSpace.trim().equals(emSpace));
        System.out.println("strip removes EM SPACE="
                + emSpace.strip().isEmpty());
    }
}
```

Dùng JDK hiện đại có `javac` hỗ trợ `--release 15` (ví dụ JDK 21). Trong thư mục chứa file, chạy:

```bash
javac --release 15 -encoding UTF-8 -d out EmptyBlankNullDemo.java
java -cp out EmptyBlankNullDemo
```

**Stdout chính xác:**

```text
null -> NULL, length=n/a, empty=n/a, blank=n/a
empty -> EMPTY, length=0, empty=true, blank=true
spaces -> BLANK, length=3, empty=false, blank=true
tab+LF -> BLANK, length=2, empty=false, blank=true
text -> TEXT, length=4, empty=false, blank=false
NBSP -> TEXT, length=1, empty=false, blank=false
EM SPACE -> BLANK, length=1, empty=false, blank=true
hasText(null)=false
hasText(spaces)=false
hasText(text)=true
trim keeps EM SPACE=true
strip removes EM SPACE=true
```

Giải thích:

- Với `null`, `inspect` trả về trước khi gọi bất kỳ phương thức nào của `String`.
- `""` có `length = 0`, cả `isEmpty` và `isBlank` đều `true`.
- Ba space và tổ hợp tab + LF đều chứa ký tự thật, nên `isEmpty` là `false` trong khi `isBlank` là `true`.
- **NO-BREAK SPACE (NBSP, U+00A0)** vẫn có thể hiển thị như khoảng trắng, nhưng **`Character.isWhitespace` không xem ký tự đó là whitespace** theo quy tắc dùng bởi `String.isBlank()`; do đó `NBSP` là `TEXT` trong phép phân loại.
- **EM SPACE (U+2003)** được `Character.isWhitespace` nhận diện; nó là `BLANK`, được `strip()` loại bỏ nhưng `trim()` giữ nguyên.
- `hasText` không ném lỗi với `null` và trả về `true` khi chuỗi chứa ít nhất một code point **không thuộc whitespace Java**.

Ví dụ cố tình tạo NBSP/EM SPACE bằng giá trị hex `0x00A0` và `0x2003`, tránh nhúng những dấu cách Unicode khó nhìn trực tiếp vào source. Không phụ thuộc tab stop của terminal để suy luận kiểu ký tự; sử dụng `length()`, mã Unicode và kết quả boolean là đáng tin hơn.

## 5. “Blank” không đồng nghĩa với “nhìn thấy khoảng trắng”

Theo `Character.isWhitespace(int)`, không phải mọi Unicode character có tên “space” đều thỏa điều kiện. Những ví dụ thường gặp:

| Ký tự | Unicode | `Character.isWhitespace` | `String.isBlank()` cho chuỗi chỉ chứa ký tự đó |
| --- | --- | --- | --- |
| SPACE | U+0020 | `true` | `true` |
| HORIZONTAL TAB | U+0009 | `true` | `true` |
| LINE FEED | U+000A | `true` | `true` |
| EM SPACE | U+2003 | `true` | `true` |
| IDEOGRAPHIC SPACE | U+3000 | `true` | `true` |
| NO-BREAK SPACE | U+00A0 | `false` | `false` |
| NARROW NO-BREAK SPACE | U+202F | `false` | `false` |
| ZERO WIDTH SPACE | U+200B | `false` | `false` |

Một số trường nhập liệu có thể trông hoàn toàn trống nhưng vẫn được `isBlank()` phân loại là **có ký tự**. Điều này không phải bug của `isBlank()`: API tuân theo một tiêu chí Unicode cụ thể.

**`Character.isSpaceChar` khác `Character.isWhitespace`.** Ví dụ NBSP thường được `isSpaceChar` xem là dấu cách, nhưng `isWhitespace` không xem như vậy. `String.isBlank()` dùng `isWhitespace`, không dùng phép hợp tùy ý của mọi phương thức Unicode. Nếu ứng dụng cần cấm cả NBSP hoặc ký tự vô hình, hãy nêu rõ tiêu chí nhập liệu và kiểm tra thêm theo whitelist hoặc quy tắc Unicode thích hợp.

**Đừng tự tiện xóa mọi ký tự vô hình trên tất cả dữ liệu.** Trong văn bản đa ngôn ngữ, một số ký tự định dạng hoặc không ngắt có ý nghĩa; với mật khẩu, mã định danh, dữ liệu chữ ký hay dữ liệu cần giữ nguyên bytes, việc tự chuẩn hóa có thể thay đổi giá trị và gây lỗi.

## 6. Chọn API theo yêu cầu nghiệp vụ

| Cần biết/đảm bảo điều gì? | Cách kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Tham chiếu có tồn tại hay không | `value == null` / `value != null` | Phân biệt **không có String** và **có String** |
| Có đúng 0 ký tự không | `value != null && value.isEmpty()` | Cho phép `" "`, nhưng không cho phép `""` |
| Có ít nhất một ký tự khác whitespace Java không | `value != null && !value.isBlank()` | Thường phù hợp trường nhập liệu văn bản bắt buộc |
| Có đúng chuỗi rỗng, an toàn với null không | `"".equals(value)` | `true` chỉ khi String có nội dung rỗng |
| Muốn loại whitespace theo Java ở hai đầu | `value.strip()` sau khi kiểm tra null | Trả về String đã chuẩn hóa; không thay đổi đối tượng gốc |
| Chỉ muốn loại đầu hoặc cuối | `value.stripLeading()` / `value.stripTrailing()` | Giữ phần còn lại |
| Muốn phân biệt rõ null/empty/blank/text | `if (value == null) ... else if (value.isEmpty()) ...` | Không gộp các trạng thái có thể quan trọng |

### 6.1. Trường bắt buộc: từ chối null và blank

Ví dụ phương thức dùng trong class Java:

```java
static String requireNonBlank(String fieldName, String value) {
    if (value == null) {
        throw new IllegalArgumentException(fieldName + " is missing");
    }
    if (value.isBlank()) {
        throw new IllegalArgumentException(fieldName + " is blank");
    }
    return value.strip();
}
```

Phương thức này phân biệt thông báo “thiếu” với “chỉ có whitespace”. Nó **chủ động chuẩn hóa hai đầu** khi trả về; chỉ nên làm vậy nếu hợp đồng dữ liệu cho phép. Nếu hệ thống cần **giữ nguyên** nội dung người dùng (ví dụ mã bí mật hoặc dữ liệu có ý nghĩa về khoảng trắng), có thể trả về `value` thay vì `value.strip()` sau khi kiểm tra.

`IllegalArgumentException` thích hợp khi tham số vi phạm tiền điều kiện của một phương thức. Ở ranh giới HTTP hoặc giao diện người dùng, chuyển lỗi kiểm tra đầu vào thành phản hồi có cấu trúc và thông báo rõ ràng theo conventions của ứng dụng; không để nó trở thành một lỗi máy chủ mơ hồ.

### 6.2. Trường tùy chọn: định nghĩa rõ “không có giá trị”

Một số ứng dụng quyết định `null`, `""` và `"   "` đều biểu thị “không có nội dung”. Khi đó mới chuẩn hóa theo chính sách:

```java
static String normalizeOptionalText(String value) {
    if (value == null) {
        return null;
    }
    String normalized = value.strip();
    return normalized.isEmpty() ? null : normalized;
}
```

Với chính sách này: `null` → `null`, `""` → `null`, `"   "` → `null`, `" Java "` → `"Java"`. Nhưng NBSP không bị `strip()` loại bỏ, vì đó không phải whitespace theo `Character.isWhitespace`. Nếu muốn chặn NBSP, cần một quy tắc bổ sung.

**Đừng áp dụng chính sách trên nếu cần phân biệt các giá trị.** Chẳng hạn, trong API cập nhật một hồ sơ:

- **Không gửi trường** có thể nghĩa là **không thay đổi**.
- **Gửi trường bằng `null`** có thể nghĩa là **xóa giá trị**.
- **Gửi `""`** có thể nghĩa là **đặt thành chuỗi rỗng**.
- **Gửi `" "`** có thể là dữ liệu cần lưu hoặc lỗi đầu vào tùy giao thức.

Đây là **ví dụ thiết kế giao thức**, không phải quy luật tự động của Java hay tất cả framework. Cần đọc hợp đồng API trước khi gộp các trạng thái.

### 6.3. Trường bắt buộc nhưng cho phép chuỗi toàn space

Một số hệ thống quản lý format, file fixed-width, mật khẩu, hoặc chuỗi dữ liệu nhị phân được diễn tả bằng text có thể **coi space là dữ liệu hợp lệ**. Khi đó chỉ kiểm tra `value != null && !value.isEmpty()` nếu yêu cầu chính xác là “phải có ít nhất một ký tự”, không dùng `isBlank()` để từ chối space. Điều kiện hợp lệ phải bắt đầu từ ý nghĩa dữ liệu, chứ không từ một API được cho là “mạnh hơn”.

## 7. Những lỗi thường gặp

### Lỗi 1: gọi phương thức trước khi kiểm tra null

```java
String value = null;
// value.isBlank(); // Ném NullPointerException nếu bỏ chú thích

boolean ok = value != null && !value.isBlank(); // false, an toàn
```

Không dùng `try/catch (NullPointerException)` như một cách kiểm tra “có nội dung” thường ngày. Kiểm tra trực tiếp `null` rõ ràng và dễ bảo trì hơn.

### Lỗi 2: nghĩ `isEmpty()` loại mọi whitespace

`"   ".isEmpty()` là `false`. Nếu trường bắt buộc không cho phép đầu vào chỉ có dấu cách, hãy dùng `isBlank()` sau khi xử lý `null`.

### Lỗi 3: nghĩ `isBlank()` chỉ đúng với một hoặc nhiều space

`"".isBlank()` cũng là `true`. Nếu một chương trình cần thống kê riêng **empty** và **blank không empty**, phải kiểm tra `isEmpty()` **trước** `isBlank()`.

### Lỗi 4: dùng `trim().isEmpty()` thay cho `isBlank()` mà không suy xét Unicode

Với U+2003, `trim().isEmpty()` là `false` nhưng `isBlank()` là `true`. Hơn nữa, `trim()` xử lý một số ký tự điều khiển không được `isBlank()` xem là whitespace. Nếu nghiệp vụ chỉ cần phép thử “blank theo Java”, `isBlank()` biểu đạt mục đích rõ hơn.

### Lỗi 5: dùng `== ""` để so sánh String

`==` so sánh **tham chiếu**, không phải nội dung. Dùng `isEmpty()` khi khác null, `"".equals(value)` khi muốn null-safe, hoặc `Objects.equals(a, b)` nếu cần so sánh hai String có thể null.

### Lỗi 6: dùng `String.valueOf` hoặc phép nối chuỗi để “sửa” null

Chẳng hạn, `"Value: " + value` với `value == null` tạo văn bản `"Value: null"`. Đó chỉ là **cách biểu diễn thành text**, không có nghĩa biến đã trở thành giá trị hợp lệ. Hãy quyết định xử lý null theo nghiệp vụ, không dựa vào việc console in ra chữ `null`.

### Lỗi 7: chuẩn hóa đầu vào trước khi quyết định giữ hay loại dấu cách

`strip()` và các thao tác thay thế whitespace có thể làm mất thông tin. Với chuỗi thông thường, việc loại khoảng trắng hai đầu có thể phù hợp; với mật khẩu, dữ liệu định dạng, số tham chiếu hoặc payload cần round-trip thì có thể không phù hợp. Xác định hợp đồng trước khi đổi dữ liệu.

## 8. Kiểm thử nên có

Một bộ test tốt cho hàm phân loại hoặc validator thường bao gồm:

- `null`.
- `""` (chuỗi rỗng).
- Một space và nhiều space (`" "`, `"   "`).
- Các ký tự điều khiển whitespace (`"\t"`, `"\n"`, `"\r\n"`).
- Chuỗi có chữ cùng whitespace ở đầu/cuối (`" Java "`).
- Chuỗi có Unicode whitespace được nhận diện (`U+2003`, `U+3000`).
- Chuỗi trông trống nhưng `isBlank()` trả false (`U+00A0`, `U+200B`).
- Chuỗi có nhiều code point, ký tự tiếng Việt, dấu kết hợp hoặc emoji nếu hệ thống cần đếm độ dài theo quy tắc riêng.

Đối với phép thử độ dài, nhớ `String.length()` đếm **UTF-16 code units**, không phải số grapheme hay số ký tự người dùng cảm nhận. Điều này không làm sai `isEmpty()`, nhưng ảnh hưởng nếu business rule yêu cầu giới hạn số ký tự hiển thị.

Trong kiểm thử validator, xác nhận thêm kết quả có giữ nguyên dữ liệu không, có ném lỗi đúng loại/đúng thông điệp không, và có tách biệt “không gửi”, “gửi null” và “gửi chuỗi rỗng” theo hợp đồng API hay không.

## 9. Quy tắc lựa chọn nhanh

1. **Cần kiểm tra null:** dùng `value == null`.
2. **Cần kiểm tra chính xác không có ký tự:** dùng `value != null && value.isEmpty()`.
3. **Cần kiểm tra có văn bản khác whitespace Java:** dùng `value != null && !value.isBlank()`.
4. **Cần chuẩn hóa whitespace hai đầu:** dùng `strip()`, sau khi đã kiểm tra null và xác nhận được phép thay đổi nội dung.
5. **Cần lưu trạng thái phân biệt:** phân nhánh theo `null → empty → blank → text`, không chuyển mọi thứ thành `""`.
6. **Cần kiểm soát các Unicode space đặc biệt:** bổ sung quy tắc theo dữ liệu của ứng dụng; đừng giả định `isBlank()` nhận mọi ký tự trông giống khoảng trắng.

## Tài liệu chính thức

- Java SE `String`: `isEmpty()`, `isBlank()`, `strip()`, `stripLeading()`, `stripTrailing()`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html
- Java SE `Character.isWhitespace(int)` và `Character.isSpaceChar(int)`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html
- Java SE `NullPointerException`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NullPointerException.html
- Java SE `Objects.equals` và `Objects.requireNonNull`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html
- Java SE 15 `String`, đối chiếu tính sẵn có trong mức source Java 15: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html

Các kiến thức trên tiếp tục đúng với Java 15 và các bản Java hiện đại. Trong dự án mới, hãy dùng JDK/JVM còn được nhà cung cấp hỗ trợ, xác định mức `--release` theo môi trường triển khai và dùng chính sách kiểm tra dữ liệu phù hợp với ứng dụng.
