# Phân biệt độ dài bằng không với nội dung toàn khoảng trắng

Hai ô nhập liệu có thể cùng trông như chưa có nội dung nhưng chứa dữ liệu khác nhau: ô thứ nhất gửi `""`, ô thứ hai gửi `"   "`. Chuỗi đầu không có đơn vị dữ liệu nào; chuỗi sau có ba dấu cách.

Phân biệt này quyết định cách kiểm tra trường bắt buộc, xử lý tìm kiếm và lưu dữ liệu. Hãy chọn phép kiểm tra theo yêu cầu cụ thể thay vì coi “không nhìn thấy chữ” là một trạng thái duy nhất.

## 1. Rỗng, toàn khoảng trắng và null

| Giá trị | Có đối tượng String? | Độ dài | Cách hiểu |
| --- | --- | --- | --- |
| `null` | Không có đối tượng được tham chiếu | Không gọi được `length()` | Thiếu giá trị tham chiếu |
| `""` | Có | `0` | Chuỗi rỗng |
| `" "` | Có | `1` | Một dấu cách |
| `"\t\n"` | Có | `2` | Tab và xuống dòng |
| `" a "` | Có | `3` | Có chữ cùng dấu cách ở hai đầu |

Với một `String` khác `null`:

```java
value.isEmpty()
```

trả `true` đúng khi `value.length() == 0`. `String.isEmpty()` có từ Java 6 và vẫn có ý nghĩa này trong JDK hiện hành.

Trong khi đó:

```java
value.isBlank()
```

trả `true` khi chuỗi rỗng hoặc mọi điểm mã trong chuỗi đều là khoảng trắng theo `Character.isWhitespace`. `isBlank()` có từ Java 11; bài dùng JDK hiện đại để thực hành, không gán phương thức này thành API Java 6.

Xem [String.isEmpty](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#isEmpty()) và [String.isBlank](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#isBlank()).

### Quan hệ giữa hai phép kiểm tra

Với đầu vào khác `null`:

```text
isEmpty() == true  => isBlank() == true

isBlank() == true  không bảo đảm isEmpty() == true
```

`""` là trường hợp đầu; `" "` là phản ví dụ cho chiều ngược lại.

`length()` của Java đếm đơn vị mã UTF-16. Nó không phải số byte của chuỗi khi mã hóa UTF-8 và không luôn là số ký tự người dùng cảm nhận. Với câu hỏi “có bằng không không?”, điều quan trọng là chuỗi có chứa đơn vị mã nào hay chưa.

## 2. Vì sao cần phân biệt khi kiểm tra dữ liệu?

Giả sử một trường tên hiển thị bắt buộc phải chứa nội dung:

```java
if (name.isEmpty()) {
    throw new IllegalArgumentException("Name is required");
}
```

Đoạn này chỉ từ chối chuỗi có độ dài `0`. Đầu vào `"   "` vẫn qua được.

Nếu quy tắc là “từ chối rỗng và toàn khoảng trắng theo Java”, phép kiểm tra phù hợp hơn là:

```java
if (name == null || name.isBlank()) {
    throw new IllegalArgumentException("Name is required");
}
```

Các đoạn trên minh họa phần kiểm tra khi đã có biến `name`; chương trình hoàn chỉnh nằm bên dưới.

Đừng tự động gộp `null` và rỗng nếu hợp đồng dữ liệu cần phân biệt chúng. Chẳng hạn, trong một yêu cầu cập nhật, “không gửi trường” có thể có nghĩa giữ giá trị cũ, còn gửi chuỗi rỗng có thể có nghĩa xóa nội dung. Cần quyết định quy tắc trước khi viết hàm tiện ích.

## 3. “Khoảng trắng” là một tập ký tự có định nghĩa

Không phải mọi ký tự nhìn giống khoảng trống đều được Java phân loại giống nhau.

| Mẫu | Ý nghĩa |
| --- | --- |
| `" "` | SPACE, U+0020 |
| `"\t"` | Tab, U+0009 |
| `"\n"` | Xuống dòng, U+000A |
| `"\u2003"` | EM SPACE |
| `"\u00A0"` | NO-BREAK SPACE, thường gọi là NBSP |
| `"\u200B"` | ZERO WIDTH SPACE |

`isBlank()` dùng quy tắc `Character.isWhitespace`. Quy tắc này nhận EM SPACE nhưng loại trừ các dấu cách không ngắt như NBSP. ZERO WIDTH SPACE cũng không được nhận là khoảng trắng theo quy tắc đó.

Vì vậy, một chuỗi chỉ chứa NBSP hoặc ZERO WIDTH SPACE vẫn có thể trông trống nhưng `isBlank()` trả `false`. Đây là lý do cần xem điểm mã khi chẩn đoán dữ liệu sao chép từ tài liệu hoặc giao diện.

Xem [Character.isWhitespace(int)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#isWhitespace(int)).

## 4. Chương trình hoàn chỉnh: quan sát mọi trường hợp

Tạo tệp `EmptyVsBlank.java`:

```java
public class EmptyVsBlank {
    public static void main(String[] args) {
        show("empty", "");
        show("space", " ");
        show("tab-newline", "\t\n");
        show("em-space", "\u2003");
        show("nbsp", "\u00A0");
        show("zero-width", "\u200B");
        show("text", " a ");
        System.out.println("null-or-blank(null)=" + isNullOrBlank(null));
        System.out.println("null-or-blank(space)=" + isNullOrBlank(" "));
        System.out.println("broad-space(nbsp)=" + onlyBusinessSpaces("\u00A0"));
        System.out.println("broad-space(zero-width)=" + onlyBusinessSpaces("\u200B"));
    }

    private static void show(String label, String value) {
        System.out.println(label
                + ": length=" + value.length()
                + ", empty=" + value.isEmpty()
                + ", blank=" + value.isBlank()
                + ", trim-empty=" + value.trim().isEmpty()
                + ", strip-empty=" + value.strip().isEmpty());
    }

    private static boolean isNullOrBlank(String value) {
        return value == null || value.isBlank();
    }

    private static boolean onlyBusinessSpaces(String value) {
        return value.codePoints().allMatch(codePoint ->
                Character.isWhitespace(codePoint) || Character.isSpaceChar(codePoint));
    }
}
```

Chương trình dùng nhãn thay vì in trực tiếp các ký tự không nhìn thấy, nhờ vậy đầu ra không bị tab/xuống dòng làm khó đọc.

### Biên dịch và chạy

Lưu tệp UTF-8 không BOM. Mở terminal tại thư mục chứa tệp, dùng JDK 17 trở lên có `javac` và `java` trong `PATH`:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out EmptyVsBlank.java
java -cp out EmptyVsBlank
```

Stdout đã kiểm chứng trên Microsoft OpenJDK 21.0.9:

```text
empty: length=0, empty=true, blank=true, trim-empty=true, strip-empty=true
space: length=1, empty=false, blank=true, trim-empty=true, strip-empty=true
tab-newline: length=2, empty=false, blank=true, trim-empty=true, strip-empty=true
em-space: length=1, empty=false, blank=true, trim-empty=false, strip-empty=true
nbsp: length=1, empty=false, blank=false, trim-empty=false, strip-empty=false
zero-width: length=1, empty=false, blank=false, trim-empty=false, strip-empty=false
text: length=3, empty=false, blank=false, trim-empty=false, strip-empty=false
null-or-blank(null)=true
null-or-blank(space)=true
broad-space(nbsp)=true
broad-space(zero-width)=false
```

Dòng `empty` cho thấy chuỗi rỗng cũng được coi là blank. Dòng `space` cho thấy một chuỗi không rỗng vẫn có thể blank. Các dòng Unicode cho thấy không thể thay quy tắc API bằng trực giác nhìn trên màn hình.

## 5. trim, strip và phép kiểm tra blank

`trim()` và `strip()` là thao tác tạo kết quả chuỗi đã bỏ ký tự ở hai đầu. `isBlank()` là câu hỏi đúng/sai về nội dung chuỗi.

| Thao tác | Tiêu chí |
| --- | --- |
| `trim()` | Bỏ ở hai đầu các ký tự có giá trị không lớn hơn U+0020 |
| `strip()` | Bỏ khoảng trắng hai đầu theo `Character.isWhitespace` |
| `isBlank()` | Kiểm tra toàn bộ chuỗi có rỗng hoặc toàn khoảng trắng theo cùng quy tắc Java không |

`strip()` cũng có từ Java 11. `trim()` vẫn có hợp đồng riêng còn dùng được; chỉ không nên coi nó là phép loại bỏ mọi khoảng trắng Unicode.

Trong ví dụ, EM SPACE có giá trị lớn hơn U+0020 nên `trim().isEmpty()` trả `false`, nhưng `strip().isEmpty()` trả `true`.

NBSP không được `strip()` loại bỏ theo quy tắc này. Đổi `trim` thành `strip` không đồng nghĩa đã xử lý mọi ký tự trông như khoảng trống. Xem [trim](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#trim()) và [strip](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#strip()).

### Kiểm tra không phải sửa dữ liệu

Nếu chỉ cần biết có nội dung theo quy tắc Java không, viết `isBlank()` thể hiện trực tiếp mục đích. Nếu cần lưu tên đã bỏ khoảng trắng ngoài cùng, mới quyết định có dùng kết quả `strip()` hay không.

`String` là bất biến. Gọi:

```java
name.strip();
```

không tự gán lại biến `name`. Muốn dùng kết quả, cần giữ nó:

```java
String cleaned = name.strip();
```

Thao tác bỏ khoảng trắng phải là một quyết định của hợp đồng trường dữ liệu. Với văn bản cần giữ nguyên nội dung, tùy ý biến đổi có thể làm mất thông tin có ý nghĩa.

## 6. Xử lý null một cách có chủ đích

Hàm trong chương trình:

```java
return value == null || value.isBlank();
```

dùng phép OR rút gọn. Khi `value == null` đã đúng, Java không gọi `isBlank()`, nên tránh dereference `null`.

Thứ tự ngược lại:

```java
return value.isBlank() || value == null;
```

không bảo vệ được trường hợp `null`: lời gọi đầu tiên đã gây `NullPointerException`.

Tên `isNullOrBlank` làm rõ rằng hàm **cố ý** gộp hai trạng thái. Nó không thay đổi ý nghĩa của `String.isBlank()`; bản thân phương thức của `String` chỉ gọi được trên một đối tượng tồn tại.

Nếu yêu cầu là “phải có giá trị và có ít nhất một điểm mã không phải khoảng trắng Java”, có thể viết:

```java
boolean hasText = value != null && !value.isBlank();
```

Đây là điều kiện theo quy tắc blank của Java, không phải chứng nhận văn bản hợp lệ cho mọi nghiệp vụ.

## 7. Khi nghiệp vụ muốn coi NBSP là khoảng trắng

Hàm `onlyBusinessSpaces` trong chương trình mở rộng tập được chấp nhận:

```java
Character.isWhitespace(codePoint) || Character.isSpaceChar(codePoint)
```

`isSpaceChar` dựa trên các nhóm dấu phân cách Unicode, nên bổ sung NBSP vào các trường hợp của phép kiểm tra này. Xem [Character.isSpaceChar(int)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#isSpaceChar(int)).

Hàm duyệt bằng `codePoints()` để làm việc theo điểm mã. `allMatch` trả `true` với chuỗi rỗng: không có phần tử nào vi phạm điều kiện. Hàm không nhận `null`; bên gọi cần xử lý `null` riêng nếu hợp đồng cho phép.

Quan trọng hơn, đây là **quy tắc tự chọn của ví dụ**, không phải định nghĩa thay thế của `String.isBlank()`. ZERO WIDTH SPACE vẫn trả `false`, như stdout đã chỉ ra.

Nếu nghiệp vụ cần xử lý một số ký tự định dạng không nhìn thấy, hãy nêu chính xác tập ký tự và lý do. Không xóa mọi ký tự “khó nhìn thấy” một cách tự động: ký tự định dạng có thể tham gia biểu diễn văn bản có ý nghĩa. Phân loại blank và xác thực dữ liệu là hai bước liên quan nhưng không đồng nhất.

## 8. Lỗi thường gặp

| Cách viết hoặc suy luận | Vấn đề |
| --- | --- |
| `value == ""` để kiểm tra rỗng | So sánh tham chiếu, không trực tiếp kiểm tra độ dài |
| `isEmpty()` để từ chối tên toàn dấu cách | Không khớp yêu cầu về nội dung |
| Gọi `isBlank()` rồi mới kiểm tra `null` | Thứ tự bảo vệ sai |
| Coi `trim().isEmpty()` và `isBlank()` giống nhau với mọi Unicode | Khác tập ký tự |
| Thấy NBSP không blank nên kết luận API lỗi | Định nghĩa khoảng trắng của API không phải “trông như dấu cách” |
| Coi `!isBlank()` là tên hợp lệ hoàn chỉnh | Còn quy tắc nghiệp vụ khác, bao gồm tập ký tự và độ dài |
| Gọi `strip()` nhưng không dùng kết quả | Chuỗi gốc và biến tham chiếu không tự thay đổi |

## 9. Tự kiểm tra

1. Vì sao `"   ".isEmpty()` là `false` nhưng `"   ".isBlank()` là `true`?
2. Vì sao chuỗi `" a "` không blank dù có dấu cách?
3. Dòng nào trong stdout chứng minh `trim` và `strip` không xử lý cùng một tập?
4. Vì sao NBSP được hàm nghiệp vụ nhận nhưng `isBlank()` không nhận?
5. Nếu trường cập nhật cần phân biệt `null` với `""`, có nên dùng một hàm gộp cả hai ngay từ đầu không?

Chọn phép kiểm tra theo câu hỏi: **độ dài có bằng không**, **mọi điểm mã có thuộc tập khoảng trắng đã chọn**, hay **giá trị có đáp ứng quy tắc nghiệp vụ**. Ba câu hỏi gần nhau nhưng cần câu trả lời rõ ràng riêng.
