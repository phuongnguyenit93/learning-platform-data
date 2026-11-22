# Tra cứu nguồn gốc tính năng và hợp đồng API hiện hành (Java 7)

## Mục tiêu học tập

Một câu hỏi như “`Files.readAllLines` là tính năng Java 7 phải không?” thực ra có **hai phần khác nhau**: *nguồn gốc* (xuất hiện từ phiên bản nào?) và *hợp đồng hiện hành* (trên phiên bản JDK đang được dùng, phương thức bảo đảm điều gì?). Biết một tên API từ Java 7 chưa đủ để chọn nó cho ứng dụng hôm nay. Cần kiểm chứng chữ ký cụ thể, quy tắc ngôn ngữ, phiên bản hỗ trợ, hành vi được đặc tả và trường hợp lỗi.

Sau bài này, bạn có thể:

- Truy nguồn một **cú pháp Java** bằng release notes và Java Language Specification (JLS).
- Truy nguồn một **API** bằng tài liệu Java SE theo phiên bản, `Since` và chữ ký chính xác của từng overload.
- Đọc hợp đồng phương thức: tham số, giá trị trả về, exception, charset, thứ tự, tài nguyên, giới hạn bộ nhớ và những điều **không được bảo đảm**.
- Tách hành vi đặc tả khỏi hành vi riêng của một triển khai OpenJDK hoặc một lần thử nghiệm.
- Chứng minh kết luận bằng tài liệu chính thức và ví dụ Java 17+ có thể biên dịch/chạy.

**Giới hạn phạm vi:** Java 7 là **mốc lịch sử để xác định nguồn gốc**, không phải bản JDK được khuyên triển khai mới. Các kỹ thuật dưới đây dùng được khi làm việc với Java hiện đại; chỉ tra tài liệu bản cũ để xác nhận thời điểm tính năng xuất hiện, không sao chép hướng dẫn đã lỗi thời.

## 1. Ba loại câu hỏi cần ba loại nguồn

| Muốn biết | Nguồn chính | Cách đọc |
| --- | --- | --- |
| Từ khi nào có `try-with-resources`, multi-catch, diamond `<>`, `switch` với `String`? | Tài liệu ngôn ngữ Java SE 7 và **JLS của phiên bản mục tiêu** | Release gốc cho mốc xuất hiện; JLS hiện hành cho cú pháp và ngữ nghĩa |
| Có từ khi nào và dùng thế nào `Files.readAllLines(Path, Charset)`? | **Java SE API Specification / JavaDoc** hiện hành, kết hợp API tại release gốc | So đúng package, tên phương thức, kiểu/số lượng tham số và `Since` |
| Tại sao OpenJDK trên một hệ điều hành xử lý như vậy? | Mã nguồn, issue và phép thử của **đúng bản JDK/vendor** | Cung cấp bằng chứng triển khai, không mặc nhiên là lời hứa cho mọi JDK |

Một **hợp đồng API** là phần hành vi tài liệu công khai cam kết để code dựa vào. Mã nguồn có thể giúp hiểu cách thực hiện nhưng thuật toán nội bộ có thể thay đổi. Thực nghiệm trên một JDK cũng không đủ để khẳng định hành vi mang tính portable nếu đặc tả không nói rõ.

Thứ tự tham khảo nên dùng: (1) **Java SE API/JLS** theo JDK mục tiêu, (2) API/release notes/JEP/CSR chính thức cho lịch sử và thay đổi, (3) mã nguồn và kiểm thử OpenJDK, (4) bài viết cộng đồng. Không phải mọi tính năng Java 7 đều có một JEP riêng; việc không tìm thấy JEP không phủ nhận một tính năng đã xuất hiện.

## 2. Quy trình tra cứu từng bước

### Bước 1 — Ghim phiên bản và câu hỏi

Ghi rõ **JDK dùng biên dịch**, **JDK runtime**, phiên bản Java thấp nhất mà dự án hỗ trợ và đối tượng cần tra. Ví dụ: `java.nio.file.Files.readAllLines(Path, Charset)` trên Java 17+, chứ không chỉ “Files trong Java”.

~~~bash
java -version
javac -version
javac --help
~~~

`javac --release N` kiểm tra cú pháp và API công khai theo release `N`, với điều kiện compiler hiện tại hỗ trợ `N`. Danh sách release được hỗ trợ thay đổi theo phiên bản compiler và được nêu trong `javac --help`. Đừng giả định JDK mới luôn hỗ trợ `--release 7`. Không dùng `--source`/`--target` riêng lẻ thay cho việc kiểm tra tập API bằng `--release`. Kết quả biên dịch cũng chưa thay thế được kiểm thử trên runtime mục tiêu.

### Bước 2 — Tìm đúng đối tượng và đối chiếu nguồn gốc

**Với cú pháp**, mở [Java SE 7 Language Enhancements](https://docs.oracle.com/javase/7/docs/technotes/guides/language/enhancements.html) để xác minh mốc xuất hiện; rồi mở [JLS §14.20.3 của Java SE 25](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.3) khi cần quy tắc `try-with-resources` hiện hành. Cú pháp có thể được **mở rộng ở các phiên bản sau**, vì thế mốc đầu tiên không chứng minh toàn bộ cú pháp hiện tại đều hợp lệ trong Java 7.

**Với API**, mở JavaDoc đúng bản JDK, tìm **đúng overload**; xem `Since` ở lớp và ngay tại thành viên. Nếu không có `Since` riêng, đừng tự suy ra tất cả overload ra đời cùng lúc: đối chiếu API của release gốc và các release liên tiếp. Ví dụ, phải phân biệt `readAllLines(Path, Charset)` với `readAllLines(Path)`, dù chỉ khác một tham số.

**Với JEP/CSR/release notes**, kiểm tra trạng thái và bản phát hành thực sự; đề xuất chưa đồng nghĩa với tính năng ổn định đã có mặt. Khi không có JEP, tài liệu release và Java SE specification vẫn có thể xác nhận nguồn gốc.

### Bước 3 — Tách các điều khoản của hợp đồng hiện tại

Đọc JavaDoc theo thứ tự: mô tả phương thức → `Parameters`/`Returns` → `Throws` → `API Note`/`Implementation Requirements` → `Since`/`Deprecated` → `See Also`. Đặt các câu hỏi sau:

- `null` có hợp lệ không? Những ngoại lệ checked và unchecked nào được nêu?
- Phương thức trả dữ liệu đã gom hết vào bộ nhớ hay mở một stream? Ai đóng resource?
- Có cam kết về charset, thứ tự, thời gian đóng, tính mutable của collection, tính atomic, thread safety không?
- Lỗi giải mã, quyền truy cập, file biến mất, tài nguyên không đủ hoặc filesystem khác nhau ảnh hưởng thế nào?
- API có `Deprecated`, `forRemoval`, preview/incubator hay giới hạn module không? Có lựa chọn phù hợp hơn với ứng dụng hiện tại không?

Nếu đặc tả **không hứa** một tính chất, hãy viết “không được bảo đảm”, dù triển khai bạn đang chạy tình cờ có tính chất đó.

### Bước 4 — Kiểm chứng bằng trường hợp tái hiện

Tạo chương trình nhỏ có input độc lập, ghi lệnh compile/run, stdout và phiên bản JDK. Khi quan trọng, thêm trường hợp lỗi; sau đó so với đoạn JavaDoc/JLS đã đọc. Việc chạy thành công **xác nhận một trường hợp**, còn tài liệu đặc tả xác định hành vi mà các triển khai phải tuân theo.

### Bước 5 — Lưu kết luận có thể kiểm tra lại

Ghi: tên đầy đủ và chữ ký; release đầu tiên có bằng chứng; JDK biên dịch/runtime mục tiêu; link đến **đúng phần** API/JLS; hành vi được bảo đảm, giới hạn và ngoại lệ; lựa chọn sử dụng; bằng chứng biên dịch/chạy. Đây là cách tạo một quyết định kỹ thuật có thể review trong quá trình nâng cấp Java.

## 3. Ví dụ thực tế: `Files.readAllLines(Path, Charset)`

### 3.1. Xác minh lịch sử mà không nhầm overload

[Java SE 7 `Files` API](https://docs.oracle.com/javase/7/docs/api/java/nio/file/Files.html) có lớp `java.nio.file.Files` (`Since: 1.7`) và phương thức `readAllLines(Path, Charset)`. Điều đó xác nhận **overload nhận hai tham số** đã có ở Java 7.

Trong [Java SE 25 `Files` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html), cũng có:

| Chữ ký | Mốc xuất hiện | Lưu ý |
| --- | --- | --- |
| `readAllLines(Path, Charset)` | Java 7 | Chỉ định charset tường minh |
| `readAllLines(Path)` | Java 8 (`Since: 1.8`) | Dùng UTF-8 |
| `readString(Path)` | Java 11 (`Since: 11`) | Đọc toàn bộ văn bản thành String, bao gồm dấu xuống dòng |
| `lines(Path, Charset)` | Java 8 (`Since: 1.8`) | Trả Stream giữ file mở, phải đóng stream sau sử dụng |

**Bài học:** `Since: 1.7` của **lớp** không đồng nghĩa mọi phương thức hoặc overload trong lớp đều có từ Java 7. Khi code phải hỗ trợ một bản Java tối thiểu, so chữ ký đầy đủ với API ở bản đó.

### 3.2. Hợp đồng hiện còn áp dụng

Theo JavaDoc hiện hành, `Files.readAllLines(Path, Charset)`:

- Đọc **toàn bộ các dòng** vào `List<String>`, giải mã bằng charset được truyền.
- **Đóng file** khi đã đọc xong hoặc khi lỗi I/O/runtime xảy ra trong lúc đọc; bên gọi không nhận stream mở cần đóng.
- Nhận biết `CRLF`, `LF` và `CR`; dữ liệu `List<String>` chứa các dòng, không giữ nguyên dấu phân cách. Trong tương lai có thể nhận biết thêm ký tự xuống dòng Unicode.
- Ném `IOException` nếu đọc hoặc giải mã byte gặp lỗi; các unchecked exception khác vẫn có thể phát sinh theo điều kiện liên quan.
- **Không cam kết** danh sách trả về có thể chỉnh sửa; JavaDoc nói tính modifiable phụ thuộc triển khai.
- **Không dành cho file rất lớn**, bởi mọi dòng đều nằm trong bộ nhớ.

Từ hợp đồng này có thể kết luận: dùng cho file văn bản nhỏ, charset đã biết; không suy ra `lines.add("x")` luôn thành công, không dùng nó làm giải pháp stream dữ liệu lớn.

### 3.3. Chương trình Java 17+ độc lập

Tạo tệp `ApiContractDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;

public class ApiContractDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("api-contract-", ".txt");
        try {
            Files.write(file, Arrays.asList("alpha", "beta"),
                    StandardCharsets.UTF_8);
            List<String> lines =
                    Files.readAllLines(file, StandardCharsets.UTF_8);

            System.out.println("count=" + lines.size());
            System.out.println("first=" + lines.get(0));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac --release 17 ApiContractDemo.java
java ApiContractDemo
~~~

Kết quả trên hệ thống cho phép tạo/đọc/ghi file tạm:

~~~text
count=2
first=alpha
~~~

`Files.write` tạo hai dòng UTF-8; `readAllLines` thu được đúng hai phần tử. `finally` dọn **tệp tạm**, khác với việc phương thức đọc đã tự đóng file handle. Đây là kiểm tra nhánh thành công; không chứng minh danh sách mutable hay mức sử dụng RAM với file lớn.

### 3.4. Khi nhu cầu thay đổi, chọn API hiện hành phù hợp

| Nhu cầu thực tế | API phù hợp | Điều cần nhớ |
| --- | --- | --- |
| File nhỏ, cần `List<String>` | `Files.readAllLines(path, charset)` | Không bảo đảm tính mutable của List |
| File nhỏ, cần **toàn bộ chuỗi** và dấu xuống dòng | `Files.readString(path, charset)` (Java 11+) | Đọc hết vào bộ nhớ; kiểm tra mức JDK tối thiểu |
| File lớn, cần xử lý từng dòng | `Files.newBufferedReader(path, charset)` | Đọc dần trong `try-with-resources` |
| Cần Stream API | `Files.lines(path, charset)` (Java 8+) | Đóng stream bằng `try-with-resources`; không để resource sống quá lâu |

Đoạn minh họa trong một phương thức (`path` và `process` do code gọi cung cấp), dùng cách đọc từng dòng vẫn phù hợp ngày nay:

~~~java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
~~~

`var` là cú pháp biến cục bộ từ Java 10; đây là cách viết hiện đại. Nếu target yêu cầu ngôn ngữ cũ hơn, thay `var` bằng `BufferedReader`. Ví dụ về **API đã có từ Java 7** không đồng nghĩa mọi cú pháp xung quanh cũng xuất hiện ở Java 7.

## 4. Ví dụ cú pháp: nguồn gốc và hợp đồng `try-with-resources`

Tài liệu [Java SE 7 Language Enhancements](https://docs.oracle.com/javase/7/docs/technotes/guides/language/enhancements.html) ghi nhận `try-with-resources` được bổ sung ở Java 7; interface [`AutoCloseable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html) có `Since: 1.7`. [JLS §14.20.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.3) giải thích ngữ nghĩa hiện hành:

- Resource được khởi tạo **từ trái sang phải**, đóng **theo thứ tự ngược**.
- Nếu khởi tạo resource sau gặp lỗi, các resource đã khởi tạo vẫn được đóng.
- Nếu phần thân `try` ném exception và `close()` cũng ném exception, exception của thân `try` là **primary**; exception đóng được giữ trong `getSuppressed()`.
- Các phiên bản sau Java 7 mở rộng cú pháp resource để có thể tham chiếu một biến có sẵn nếu nó `final` hoặc effectively final. Vì vậy cần tra JLS của **mức ngôn ngữ đang áp dụng**, không gán mọi biến thể cú pháp hiện hành cho Java 7.

Chương trình độc lập `CloseContractDemo.java`:

~~~java
public class CloseContractDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new IllegalArgumentException("body");
        } catch (RuntimeException ex) {
            System.out.println(ex.getMessage());
            System.out.println(ex.getSuppressed().length);
            System.out.println(ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 CloseContractDemo.java
java CloseContractDemo
~~~

~~~text
body
1
close
~~~

Lỗi `body` là primary; lỗi `close` là suppressed. Trong code ứng dụng, `close()` phải được thiết kế theo hợp đồng resource thực tế; việc chủ động ném lỗi chỉ nhằm chứng minh ngữ nghĩa đã được đặc tả. Cơ chế quản lý tài nguyên bằng `try-with-resources` vẫn phù hợp cho file, socket, JDBC và nhiều resource hiện hành.

## 5. Những lỗi thường gặp khi tra API

1. **Nhầm bản tài liệu:** trang Java SE 7 dùng để biết **lịch sử**, nhưng hợp đồng vận hành phải đọc ở Java SE của bản JDK mà dự án dùng.
2. **Nhầm overload:** chung tên phương thức không có nghĩa cùng `Since`; kiểm tra đầy đủ kiểu và số lượng tham số.
3. **Nhầm implementation với specification:** code OpenJDK và thử nghiệm có thể giúp debug, nhưng không biến hành vi chưa được bảo đảm thành hợp đồng đa nền tảng.
4. **Nhầm output thử nghiệm với cam kết:** thấy một `List` sửa được không chứng minh bản JDK khác cũng như vậy; thấy stdout đúng không xác nhận nhánh exception.
5. **Bỏ qua vòng đời tài nguyên:** `Files.readAllLines` tự đóng file của nó; `Files.lines` trả stream giữ file mở và bên gọi cần đóng.
6. **Không kiểm tra giới hạn dữ liệu:** API vẫn hợp lệ nhưng dùng `readAllLines` với file quá lớn có thể ngốn bộ nhớ; khi cần streaming hãy dùng API xử lý từng dòng.
7. **Nhầm mốc xuất hiện với tính phù hợp hiện tại:** kiểm tra deprecation/`forRemoval`, preview/incubator, JDK runtime thực tế và release notes trước khi chọn API.
8. **Dùng `--release` thiếu kiểm chứng:** compiler chỉ chấp nhận một số release; còn phải chạy test trên JDK runtime mục tiêu, đặc biệt với I/O, charset và môi trường hệ thống.

## 6. Mẫu biên bản tra cứu cho code review

~~~text
Câu hỏi: Files.readAllLines(Path, Charset) dùng được trên Java 17?
Tên/chữ ký: java.nio.file.Files.readAllLines(Path, Charset)
Nguồn gốc: xuất hiện trong Java SE 7 Files API.
JDK mục tiêu: Java 17+; tài liệu hợp đồng đối chiếu: Java SE 25 Files API.
Cam kết: giải mã theo charset chỉ định, trả toàn bộ dòng,
          đóng file, IOException khi lỗi đọc/giải mã.
Không cam kết: List trả về có thể chỉnh sửa.
Giới hạn: không chọn cho file lớn.
Kiểm tra: javac --release 17 ApiContractDemo.java
          java ApiContractDemo -> count=2 / first=alpha
Quyết định: dùng cho input văn bản nhỏ có giới hạn dung lượng;
            trường hợp dữ liệu lớn dùng BufferedReader hoặc Stream có đóng.
Bằng chứng: link Java SE 7 API, Java SE 25 API và mã kiểm tra.
~~~

Một kết luận đáng tin cần có **phiên bản, chữ ký, hành vi được đặc tả, giới hạn và liên kết kiểm chứng**; không sao chép nguyên quyết định sang dự án có minimum JDK hoặc khối lượng dữ liệu khác.

## 7. Câu hỏi tự kiểm tra

**1.** `Files` có `Since: 1.7`, vậy `Files.readString(Path)` cũng có từ Java 7?  
**Đáp án:** Không. Xem `Since` của **overload cụ thể**: `readString(Path)` có từ Java 11.

**2.** Có thể giả định `Files.readAllLines(path, cs).add("new")` luôn chạy được?  
**Đáp án:** Không. JavaDoc không cam kết tính mutable; nếu cần sửa, tạo collection riêng, chẳng hạn `new ArrayList<>(lines)`.

**3.** Nếu thân `try-with-resources` và `close()` cùng lỗi, nên kiểm tra ở đâu?  
**Đáp án:** Exception của thân `try` là primary; dùng `getSuppressed()` để xem lỗi đóng.

**4.** Chương trình chạy ổn trên một JDK có đủ bằng chứng về API portable?  
**Đáp án:** Chưa. Cần đối chiếu đúng Java SE API Specification/JLS của release mục tiêu, rồi dùng test để bổ trợ.

## Nguồn chính thống

- [Java SE Documentation](https://docs.oracle.com/en/java/javase/) — danh mục các bản JDK, chọn đúng bản dự án đang sử dụng.
- [Java SE 7 — Language Enhancements](https://docs.oracle.com/javase/7/docs/technotes/guides/language/enhancements.html) — chứng cứ nguồn gốc những cải tiến ngôn ngữ Java 7.
- [Java SE 7 — Files API](https://docs.oracle.com/javase/7/docs/api/java/nio/file/Files.html) — chứng cứ chữ ký `Files.readAllLines(Path, Charset)` đã có ở Java 7.
- [Java SE 25 — Files API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html) — hợp đồng API, overload, `Since` và giới hạn hiện hành.
- [Java SE 25 — AutoCloseable API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html) và [JLS 25 §14.20.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.3) — hợp đồng đóng resource, thứ tự và suppressed exceptions.
- [Tài liệu `javac` hiện hành về `--release`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — hỗ trợ biên dịch theo release và giới hạn.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — nguồn tra cứu các thay đổi và cảnh báo gần đây; khi thực hiện nâng cấp phải xem bản tương ứng của **runtime thực tế**.

**Ghi nhớ:** Lịch sử Java 7 cho biết tính năng **đến từ đâu**; JavaDoc và JLS đúng phiên bản JDK mục tiêu cho biết code **có thể dựa vào điều gì hôm nay**.