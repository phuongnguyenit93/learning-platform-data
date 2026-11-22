# Kiến thức nền và trình tự học Java Core String

## 1. Mục tiêu và vị trí của chủ đề

`String` là kiểu dữ liệu dùng để biểu diễn **chuỗi ký tự** trong Java. Đây là một lớp thuộc gói `java.lang`, được nhập tự động. Học `String` không chỉ là ghi nhớ các phương thức: cần hiểu sự khác nhau giữa **giá trị và tham chiếu**, tính **bất biến**, cách Java biểu diễn **Unicode**, cũng như cách xử lý văn bản an toàn và hiệu quả.

Sau bài học, người học cần có thể:

- Tạo chuỗi, đọc và biến đổi nội dung mà không nhầm lẫn về tính bất biến.
- So sánh chuỗi theo nội dung, phân biệt `==` với `equals()` và xử lý trường hợp `null`.
- Tìm kiếm, cắt, nối, tách, thay thế, định dạng và chuẩn hóa văn bản.
- Giải thích `String Pool`, `StringBuilder`, mã hóa ký tự và các lỗi Unicode thường gặp.
- Chọn API phù hợp trong tình huống thực tế và kiểm chứng bằng chương trình Java tự chạy.

**Điều kiện đầu vào:** đã học biến, kiểu nguyên thủy, toán tử, `if`, vòng lặp, phương thức, mảng và kiến thức cơ bản về lớp/đối tượng. Nền tảng ví dụ là **Java 17+**; một số API hiện đại như `strip()`, `isBlank()`, `lines()`, `repeat()` có từ Java 11. Lộ trình dưới đây đi từ căn bản đến ứng dụng rồi mới tối ưu.

## 2. Lộ trình đọc các bài trong chương

Mục tiêu của bài này là **biết học gì trước, luyện gì sau và chứng minh đã hiểu bằng cách nào**. Các bài chuyên đề giữ phần giải thích chi tiết và code thực hành; khi cần tra cứu một hành vi cụ thể, hãy quay lại đúng bài đó thay vì học thuộc toàn bộ API trong một lượt.

| Thứ tự | Bài nên đọc | Sau bài này, tự kiểm tra được gì? |
| --- | --- | --- |
| 1 | String là gì và vai trò biểu diễn văn bản trong Java | Giải thích String là đối tượng, dùng cho văn bản và không tự quyết định charset hay độ an toàn của dữ liệu. |
| 2 | Quan hệ giữa String, char[], CharSequence và đối tượng | Phân biệt upcast, copy, mutable view và phép chuyển kiểu. |
| 3 | Phân biệt nội dung chuỗi với biến tham chiếu đến chuỗi | Vẽ lại sơ đồ alias, giải thích `==`, `equals()` và string pool. |
| 4 | Chuỗi rỗng, chuỗi trắng, null và chuỗi chứa chữ null | Viết điều kiện null-safe mà không làm mất bốn trạng thái đầu vào. |
| 5 | Vì sao String là lớp final và có tính bất biến | Giải thích `final class`, `final` trên biến và immutable bằng ví dụ độc lập. |
| 6 | Các nhóm thao tác: đọc, so sánh, tìm kiếm, biến đổi và chuyển mã | Chọn `substring`, `indexOf`, `replace`, regex, Unicode và UTF-8 theo yêu cầu. |
| 7 | Chọn String, StringBuilder hoặc StringBuffer theo nhu cầu | Biết khi nào cần bộ đệm mutable, và giới hạn đồng bộ từng lời gọi. |
| 8 | Kiến thức nền và trình tự học Java Core String (bài này) | Lập kế hoạch luyện tập, kiểm tra trường hợp biên và hoàn thành mini project. |

**Dấu hiệu cần quay lại bài trước:** chưa phân biệt `null` với chuỗi rỗng; nhầm `==` với so nội dung; tưởng `StringBuilder` là `String`; chưa giải thích được tại sao emoji có `length() == 2`; hoặc chưa tách được encoding byte khỏi thao tác trên chuỗi. Mỗi trường hợp đều có bài học chính ở trên.

Trước khi bắt đầu chặng mới, hãy tự chạy ít nhất một chương trình `main()` và thử một giá trị biên (như `null`, chuỗi rỗng, emoji hoặc dấu phân cách ở cuối). Ghi lại cả kết quả dự đoán và kết quả thực tế để phát hiện giả định sai.

## 3. Trình tự học đề xuất: từ nền tảng đến ứng dụng

Không cần học mọi API trong một lần. Mỗi chặng nên kết thúc bằng một sản phẩm chạy được và một bộ trường hợp biên tự viết.

| Chặng | Kiến thức chính | Bài thực hành để qua chặng |
| --- | --- | --- |
| 0. Ôn Java nền | Primitive/reference, `char`, array, `null`, vòng lặp, method, exception | Giải thích vì sao `String` là đối tượng dù có cú pháp literal |
| 1. Tạo và so sánh | Literal, `new`, immutable, `equals()`, `==`, pool | Viết chương trình phân biệt cùng giá trị và cùng tham chiếu; thử `null` |
| 2. Thao tác cơ bản | `length()`, `substring()`, tìm kiếm, `strip()`, thay thế | Chuẩn hóa tiêu đề, trích phần trước/sau một dấu phân cách |
| 3. Tách và dựng chuỗi | `split()`, `join()`, regex căn bản, `StringBuilder` | Xử lý danh sách thẻ ngăn cách bằng dấu phẩy, giữ ô rỗng khi cần |
| 4. Unicode và locale | UTF-16, code point, charset, normalization, case folding ở mức phù hợp | Đo độ dài chuỗi chứa tiếng Việt, emoji; thử round trip UTF-8 |
| 5. Ứng dụng và kiểm thử | Input validation, yêu cầu null/blank, trường hợp biên, hiệu năng | Tự xây một bộ hàm làm sạch văn bản có kiểm thử nhiều trường hợp |
| 6. Đào sâu theo nhu cầu | `Pattern`/`Matcher`, `Collator`, `CharsetDecoder`, tối ưu hóa khi có số đo | Giải một bài toán thực tế có quy tắc rõ ràng và giải thích lựa chọn API |

**Cách học mỗi chặng:** đọc khái niệm → tự viết ví dụ 10–30 dòng → dự đoán kết quả → chạy và giải thích chênh lệch → sửa bài theo trường hợp biên → tự tóm tắt lúc nào nên/không nên dùng API đó. Chỉ chuyển chặng khi giải thích được kết quả, không chỉ khi chương trình chạy.

### Gợi ý bài tập theo độ khó

**Cơ bản:**

1. Viết `isBlankOrNull(String s)` trả `true` khi `s == null` hoặc `s.isBlank()`. Thử `null`, `""`, `" "` và `" Java "`.
2. Cho `"  java core  "`, tạo kết quả `"JAVA CORE"` bằng cách bỏ khoảng trắng hai đầu và chuyển chữ hoa; chứng minh chuỗi gốc vẫn giữ nguyên.
3. Viết hàm kiểm tra tên file kết thúc bằng `".java"` (phân biệt chữ hoa/thường), và tự quyết định cách xử lý `null`.

**Trung bình:**

4. Phân tích `"a, b,,c,"` thành các trường; bảo toàn trường trống cuối; loại bỏ khoảng trắng quanh mỗi trường mà không đánh mất vị trí rỗng.
5. Cho câu văn, đếm số lần xuất hiện của một từ hoặc đoạn con theo quy tắc **đã xác định** về phân biệt chữ hoa và ranh giới từ; kiểm tra trường hợp chuỗi tìm kiếm rỗng.
6. Tạo slug đơn giản cho tiêu đề theo bộ quy tắc do bạn tự định nghĩa: `strip()`, hạ chữ, đổi nhóm khoảng trắng thành `-`; lưu ý slug cho tiếng Việt có dấu cần quy định riêng, không giả định luôn phải bỏ dấu.

**Nâng cao:**

7. Đếm UTF-16 code units, code points và số byte UTF-8 của `"A😀é"`; giải thích vì sao ba con số có thể khác nhau.
8. So sánh `"é"` với `"e\u0301"` trước và sau `Normalizer.Form.NFC`; giải thích khác biệt giữa *hiển thị giống nhau* và *bằng nhau theo equals*.
9. Xây hàm nhận dữ liệu tên người dùng: yêu cầu rõ ràng về `null`/blank, có giữ dấu hay không, cách xử lý Unicode, độ dài đo theo đơn vị nào. Viết ít nhất 6 trường hợp kiểm thử.

**Mini project cuối chủ đề:** xây thư viện nhỏ `TextUtils` (các phương thức `normalizeSpaces`, `safeEquals`, `splitPreservingEmpty`, `utf8ByteLength`). Viết JUnit tests nếu đã học kiểm thử; nếu chưa, tạo `main()` in expected/actual. Phải công bố contract cho mọi hàm (đầu vào `null`, chuỗi rỗng, dữ liệu lỗi, quy tắc Unicode) và kiểm thử đúng contract.

## 4. Cách đọc tài liệu và tự kiểm chứng

- Tra cứu **Javadoc `java.lang.String` của đúng phiên bản JDK đang dùng**: chữ ký, kết quả, ngoại lệ, behavior với `null` và các phiên bản phát hành.
- Dùng `jshell` cho thử nghiệm ngắn, hoặc tạo một tệp `.java` có `public static void main(String[] args)` để quan sát hành vi nhất quán.
- Dùng `javac -version` và `java -version` để biết compiler/runtime; ưu tiên hai phiên bản tương thích. Nếu làm việc với Java 17, tránh sử dụng API chỉ được bổ sung ở phiên bản mới hơn.
- Khi ví dụ gắn với locale, charset hay regex, nêu rõ giả định đầu vào; tránh kết luận từ một chuỗi ASCII đơn giản.
- Khi gặp lỗi, thử tạo **minimum reproducible example**: chuỗi vào ngắn nhất, output mong đợi và output thực tế. Kiểm tra độ dài, chỉ số, regex, ký tự escape và `null` trước khi suy đoán do JVM.

Tài liệu chuẩn nên tra cứu: [Java SE 17: String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html), [StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html), [Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html) và [Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html).

## 5. Tiêu chí hoàn thành chủ đề

Tự trả lời được các câu sau **không cần chạy thử trước**:

1. Vì sao `"Java" == new String("Java")` là `false`, trong khi `equals()` là `true`?
2. Vì sao `text.replace("a", "b");` không thay đổi biến `text`?
3. `substring(1, 3)` lấy những vị trí nào và ngoại lệ gì xảy ra nếu chỉ số vượt biên?
4. Khác nhau giữa `null`, `""`, `"   "`, `isEmpty()` và `isBlank()`?
5. Vì sao `"😀".length()` bằng `2`? Khi nào cần `codePoints()`?
6. Khi nào dùng `replace()`, khi nào dùng `replaceAll()`, và vì sao regex cần escape?
7. Vì sao nên truyền `StandardCharsets.UTF_8` khi chuyển giữa `String` và `byte[]`?
8. Trường hợp nào `StringBuilder` hợp lý hơn phép nối `+`?
9. Vì sao chuẩn hóa Unicode hoặc so sánh theo locale cần quy tắc nghiệp vụ?
10. Bạn sẽ kiểm thử những trường hợp biên nào trước khi dùng hàm xử lý văn bản trong chương trình thật?

**Hoàn thành thực chất** khi viết được các hàm của mini project, giải thích được output, xử lý được `null`/rỗng/Unicode và kiểm tra được chuỗi đầu vào khác ví dụ mẫu. Khi đó mới nên mở rộng sang regex nâng cao, thao tác file văn bản, định dạng địa phương hóa và các API xử lý dữ liệu lớn.