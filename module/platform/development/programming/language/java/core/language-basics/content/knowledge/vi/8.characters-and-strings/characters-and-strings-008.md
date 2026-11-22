# Phân biệt chuỗi rỗng, chuỗi trắng và `null` trong Java 17+

Khi nhận tên người dùng, ghi chú hay dữ liệu từ biểu mẫu, ba trường hợp thường bị lẫn với nhau là **`null`**, **chuỗi rỗng `""`** và **chuỗi chỉ chứa khoảng trắng**. Chúng có ý nghĩa khác nhau, và lựa chọn giữa `isEmpty()`, `isBlank()`, `trim()`, `strip()` quyết định chương trình xử lý đúng hay sai.

- **`null`**: biến tham chiếu `String` không trỏ tới đối tượng nào.
- **Chuỗi rỗng `""`**: có đối tượng `String`, nhưng độ dài bằng **0**.
- **Chuỗi trắng (*blank string*)**: có thể rỗng hoặc chỉ chứa các ký tự được Java xem là **whitespace** theo `Character.isWhitespace`. Ví dụ `"   "`, `"\t"` và `"\n"`. Chuỗi trắng **không nhất thiết có độ dài 0**.

## 1. Bảng so sánh chính xác

Giả sử biến `s` chứa giá trị ở cột đầu:

| Giá trị `s` | `s == null` | `s.isEmpty()` | `s.isBlank()` | Vì sao |
| --- | --- | --- | --- | --- |
| `null` | `true` | **Ném `NullPointerException`** | **Ném `NullPointerException`** | Không có đối tượng String |
| `""` | `false` | `true` | `true` | Rỗng cũng được coi là blank |
| `" "` | `false` | `false` | `true` | Có một space |
| `" \t\n"` | `false` | `false` | `true` | Chỉ gồm space, tab, xuống dòng |
| `"\u2003"` (EM SPACE) | `false` | `false` | `true` | EM SPACE được `Character.isWhitespace` nhận diện |
| `"\u00A0"` (NBSP) | `false` | `false` | `false` | Non-breaking space **không** được `Character.isWhitespace` xem là whitespace |
| `"Java"` | `false` | `false` | `false` | Chứa chữ |
| `" Java "` | `false` | `false` | `false` | Có chữ dù hai bên có space |

**Điểm then chốt:** `isBlank()` bao hàm cả chuỗi rỗng; còn `isEmpty()` chỉ kiểm tra `length() == 0`. Cả hai đều là phương thức instance, vì thế **không thể gọi trực tiếp trên `null`**.

## 2. Chương trình Java 17+ chạy được

Lưu tệp UTF-8 tên **`EmptyBlankNullDemo.java`**:

~~~java
public class EmptyBlankNullDemo {
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

    public static void main(String[] args) {
        String[] labels = {
                "null", "empty", "spaces", "mixed",
                "emSpace", "nbsp", "word", "padded"
        };

        String[] values = {
                null, "", "   ", " \t\n",
                "\u2003", "\u00A0", "Java", " Java "
        };

        for (int i = 0; i < values.length; i++) {
            String value = values[i];
            String size = value == null
                    ? "N/A"
                    : Integer.toString(value.length());

            System.out.println(labels[i]
                    + "=" + classify(value)
                    + ",length=" + size);
        }

        String padded = "  Java  ";
        System.out.println("trimAscii=" + padded.trim());
        System.out.println("stripAscii=" + padded.strip());

        String unicodePadded = "\u2003Java\u2003";
        System.out.println("trimUnicodeLength="
                + unicodePadded.trim().length());
        System.out.println("stripUnicodeLength="
                + unicodePadded.strip().length());

        String maybeNull = null;
        System.out.println("safeMissing="
                + (maybeNull == null || maybeNull.isBlank()));

        String onlySpace = "   ";
        String normalized = onlySpace.isBlank()
                ? "(missing)"
                : onlySpace.strip();
        System.out.println("normalized=" + normalized);
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa tệp, dùng **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 EmptyBlankNullDemo.java
java EmptyBlankNullDemo
~~~

**Expected output chính xác của chương trình:**

~~~text
null=NULL,length=N/A
empty=EMPTY,length=0
spaces=BLANK,length=3
mixed=BLANK,length=3
emSpace=BLANK,length=1
nbsp=TEXT,length=1
word=TEXT,length=4
padded=TEXT,length=6
trimAscii=Java
stripAscii=Java
trimUnicodeLength=6
stripUnicodeLength=4
safeMissing=true
normalized=(missing)
~~~

**Giải thích:** hàm `classify` phải kiểm tra `null` **trước** khi gọi phương thức. Với giá trị không null, nó phân biệt chuỗi rỗng với chuỗi có whitespace. `String.isBlank()` ra đời từ Java 11, nên có sẵn trong Java 17. `"\u2003"` là một EM SPACE: `strip()` bỏ được nhưng `trim()` không bỏ. `"\u00A0"` là NBSP, nên `isBlank()` trả false.

Mã kiểm tra kết quả bằng nhãn thay vì in trực tiếp chuỗi chứa tab hoặc dấu cách, giúp bạn nhìn thấy sự khác biệt rõ ràng trên terminal.

## 3. Chọn kiểm tra nào theo yêu cầu nghiệp vụ?

### A. Muốn kiểm tra “không có đối tượng”

~~~java
String input = null;

if (input == null) {
    System.out.println("Chua duoc cung cap");
}
~~~

`null` thường có nghĩa **không được cung cấp**, **chưa có** hoặc một trạng thái đặc biệt do thiết kế API quy định. Đừng tự mặc định `null` và `""` là một nếu API cần phân biệt “chưa trả lời” với “đã trả lời rỗng”.

### B. Muốn kiểm tra “đúng 0 đơn vị mã”

~~~java
String input = " ";

System.out.println(input.isEmpty()); // false
System.out.println(input.length());  // 1
~~~

`isEmpty()` phù hợp khi **một space cũng là dữ liệu hợp lệ**, chẳng hạn nội dung biên tập văn bản hoặc mật khẩu mà yêu cầu là không rỗng về độ dài. `isEmpty()` không loại khoảng trắng.

### C. Muốn kiểm tra “không có nội dung hữu ích ngoài whitespace”

~~~java
String input = " \t";

if (input != null && !input.isBlank()) {
    System.out.println("Co noi dung");
} else {
    System.out.println("Thieu noi dung");
}
~~~

Đây thường là lựa chọn phù hợp cho **tên hiển thị**, **ghi chú** hay **mô tả** mà chỉ nhập dấu cách/tab/xuống dòng thì bị xem là thiếu nội dung. Tuy nhiên, phạm vi whitespace của `isBlank()` không bao trùm **mọi** ký tự mà mắt người cảm nhận là khoảng trắng (ví dụ NBSP).

### D. Gộp `null` và blank thành cùng trạng thái

~~~java
static boolean isMissing(String s) {
    return s == null || s.isBlank();
}
~~~

Toán tử `||` có **short-circuit**: nếu `s == null` là true, vế `s.isBlank()` sẽ không chạy nên tránh `NullPointerException`. Đừng đổi thứ tự hai điều kiện.

## 4. `trim()` khác `strip()` như thế nào?

Cả hai tạo kết quả **chuỗi đã lược bớt ký tự ở hai đầu**, không thay đổi đối tượng `String` ban đầu.

| Phương thức | Quy tắc | Tình huống |
| --- | --- | --- |
| `trim()` | Loại các ký tự đầu/cuối có giá trị mã `<= U+0020` | Cách xử lý cũ, có giới hạn với Unicode |
| `strip()` | Loại whitespace đầu/cuối theo `Character.isWhitespace` | Thường phù hợp hơn với một số khoảng trắng Unicode |
| `stripLeading()` | Chỉ loại whitespace **đầu chuỗi** | Giữ phần cuối |
| `stripTrailing()` | Chỉ loại whitespace **cuối chuỗi** | Giữ phần đầu |

`strip()`, `stripLeading()`, `stripTrailing()` có từ Java 11. Ví dụ:

~~~java
String raw = "  Java  ";
String clean = raw.strip();

System.out.println(raw.length());   // 8
System.out.println(clean.length()); // 4
~~~

`raw` không đổi. Nếu muốn lưu kết quả vào biến đang dùng, viết `raw = raw.strip();` (khi biến không `final`).

**Lưu ý Unicode:** `strip()`/`isBlank()` dựa trên `Character.isWhitespace`, vì vậy một số khoảng trắng *non-breaking* như U+00A0 vẫn được giữ. Nếu ứng dụng muốn coi các ký tự đó là trống, bạn phải xác định rõ tập ký tự cần xử lý và bổ sung quy tắc phù hợp, thay vì cho rằng mọi khoảng trống nhìn thấy đều được `isBlank()` nhận diện.

## 5. Sai lầm phổ biến

| Cách viết / nhận định | Vấn đề | Cách sửa |
| --- | --- | --- |
| `text.isEmpty()` khi `text == null` | `NullPointerException` | Kiểm tra `null` trước |
| `"".equals(text)` và `text == null` là như nhau | Sai: một bên so nội dung với chuỗi rỗng, một bên so với null | Chọn theo nghĩa dữ liệu |
| `text.isEmpty()` coi `"   "` là rỗng | Sai: độ dài khác 0 | Dùng `isBlank()` nếu cần |
| `text.isBlank()` chỉ đúng khi độ dài lớn hơn 0 | Sai: `"".isBlank()` cũng true | Nếu muốn ba trạng thái riêng, kiểm tra `isEmpty()` trước `isBlank()` |
| `text.trim();` tự thay đổi `text` | Sai: `String` bất biến | Gán lại `text = text.trim();` |
| `strip()` xóa mọi whitespace Unicode | Sai, không gồm một số dấu cách non-breaking | Xác định chính sách whitespace của ứng dụng |
| `text == ""` để kiểm tra rỗng | `==` so sánh tham chiếu | Dùng `text.isEmpty()` sau khi kiểm tra null |
| `isBlank()` luôn có trong Java 8 | Sai: từ Java 11 | Java 17+ dùng được |

### So sánh null-safe nhưng đúng ý nghĩa

~~~java
String text = null;
System.out.println("".equals(text)); // false
System.out.println(text == null);     // true
~~~

`"".equals(text)` không ném lỗi vì đối tượng nhận lời gọi là literal `""` chắc chắn không null, nhưng câu này chỉ kiểm tra nội dung **chuỗi rỗng**, không thay thế phép kiểm tra `null`.

`java.util.Objects.toString(text, "")` có thể chuyển null thành chuỗi rỗng theo chủ đích; tuy nhiên việc chuẩn hóa như vậy sẽ **mất thông tin phân biệt** hai trạng thái. Chỉ làm khi yêu cầu sản phẩm thực sự muốn gộp chúng.

## 6. Quy trình xử lý đầu vào gọn và an toàn

Nếu quy định nghiệp vụ là “bỏ whitespace ở hai đầu, và bỏ qua giá trị rỗng hoặc blank”, có thể viết:

~~~java
static String normalizeName(String input) {
    if (input == null || input.isBlank()) {
        return null;
    }

    String cleaned = input.strip();
    return cleaned.isEmpty() ? null : cleaned;
}
~~~

Đây chỉ là **ví dụ chính sách**: trả `null` để đánh dấu “không có tên”. Trong hệ thống thật, bạn cũng có thể chọn trả `""`, `Optional<String>` hoặc báo lỗi validation, tùy hợp đồng API. Không tự động `strip()` dữ liệu mà whitespace đầu/cuối có ý nghĩa, chẳng hạn nội dung code hoặc dữ liệu cần giữ nguyên định dạng.

Chú ý: hàm trên xem NBSP đơn lẻ là nội dung (`isBlank() == false`, `strip()` cũng giữ lại). Nếu đây không phải hành vi mong muốn, cần thiết kế quy tắc làm sạch rõ ràng thay vì dùng mặc định.

## 7. Bài tập tự kiểm tra

1. **Phân loại:** `null`, `""`, `" \t"`, `"x"` tương ứng thuộc nhóm nào?  
   *Đáp án:* null, empty, blank, text.
2. **Dự đoán:** `"".isEmpty()`, `"".isBlank()` và `" ".isEmpty()` lần lượt là gì?  
   *Đáp án:* `true`, `true`, `false`.
3. **An toàn:** Vì sao `s == null || s.isBlank()` không ném lỗi khi `s == null`?  
   *Đáp án:* `||` dừng sớm nếu vế trái true.
4. **Unicode:** Vì sao `"\u2003".isBlank()` là true nhưng `"\u00A0".isBlank()` là false?  
   *Đáp án:* `Character.isWhitespace` xem EM SPACE là whitespace nhưng không xem NBSP là whitespace.
5. **Đổi dữ liệu:** Với `String s = "  A  "; s.strip();`, sau hai câu lệnh, `s.length()` là bao nhiêu?  
   *Đáp án:* 5, vì kết quả `strip()` không được gán lại.

## Ghi nhớ

- `null`: không có đối tượng; kiểm tra bằng `== null`.
- `""`: chuỗi rỗng có `length() == 0`; `isEmpty() == true`.
- Chuỗi blank: rỗng **hoặc** chỉ chứa whitespace theo `Character.isWhitespace`; `isBlank() == true`.
- `isBlank()` khác `isEmpty()`, và **không** tự xử lý `null`.
- `trim()`/`strip()` trả kết quả mới hoặc kết quả tương đương, **không sửa `String` cũ**.
- Với Unicode non-breaking space, cần quy định nghiệp vụ rõ ràng thay vì mặc định mọi khoảng trắng sẽ được `strip()` xóa.

**Kết luận:** Trước khi kiểm tra đầu vào, hãy quyết định **“thiếu dữ liệu” nghĩa là `null`, rỗng, blank, hay tổ hợp nào?** Rồi áp dụng `== null`, `isEmpty()` và `isBlank()` đúng theo ngữ nghĩa đó. Đây là cách tránh lỗi `NullPointerException` và tránh loại bỏ nhầm thông tin.
