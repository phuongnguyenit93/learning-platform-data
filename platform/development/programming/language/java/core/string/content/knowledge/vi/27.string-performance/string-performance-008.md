# Đánh giá bộ nhớ và kết quả String trên dữ liệu ASCII, tiếng Việt và emoji

**String.length() không trả về số byte.** Trong Java, chuỗi ASCII, văn bản tiếng Việt và emoji có thể khác nhau về số đơn vị mã UTF-16, số Unicode code point, kích thước khi mã hóa UTF-8 và dung lượng bộ nhớ của đối tượng trong JVM. Đánh giá hiệu năng String phải xác định rõ **đơn vị đo**, **dữ liệu đầu vào**, **thao tác** và **phiên bản JVM**.

Bài học này xây dựng phép so sánh có thể chạy trên Java 17+, giải thích cơ chế Compact Strings, những trường hợp Unicode dễ sai và quy trình đo heap/hiệu năng phù hợp. Các số byte mã hóa được xác định trực tiếp từ dữ liệu; con số payload nội bộ chỉ là **ước lượng có điều kiện**, còn thời gian chạy và heap thực tế cần đo bằng công cụ.

## 1. Các đại lượng cần phân biệt

| Đại lượng | Cách lấy trong Java | Thể hiện |
| --- | --- | --- |
| **UTF-16 code unit** | **s.length()** | Số đơn vị kiểu **char** trong mô hình API Java String |
| **Unicode code point** | **s.codePointCount(0, s.length())** | Số điểm mã Unicode, không nhất thiết là số ký tự nhìn thấy |
| **UTF-8 bytes** | **s.getBytes(StandardCharsets.UTF_8).length** | Kích thước byte khi truyền/lưu dưới định dạng UTF-8 |
| **Grapheme cluster** | Bộ phân đoạn grapheme phù hợp Unicode | Đơn vị ký tự người dùng cảm nhận; có thể gồm nhiều code point |
| **Heap memory** | Profiler/heap dump/JOL tùy mục tiêu | Header, byte[] nội bộ, tham chiếu, padding và dữ liệu còn được giữ |
| **Allocation/op** | Benchmark/profiler GC | Dung lượng cấp phát tạm mỗi lần thực hiện thao tác |

Không suy ra heap từ **getBytes(UTF_8).length**. Khi gọi **getBytes**, JVM còn có thể cấp phát mảng byte mới cho dữ liệu được mã hóa.

### UTF-16 unit và code point khác nhau thế nào?

Một **char** trong Java lưu một đơn vị mã 16-bit, không phải lúc nào cũng là một Unicode code point. Nhiều chữ trong BMP cần một unit; một điểm mã ngoài BMP, chẳng hạn emoji **🙂**, cần **hai unit** gọi là *surrogate pair*. Do đó **"🙂".length() là 2** nhưng codePointCount là **1**.

Ngược lại, một cụm emoji hiển thị như **👩‍💻** chứa **ba code point**: 👩, ZWJ (ký tự nối U+200D) và 💻. Vì hai hình emoji thành phần nằm ngoài BMP, chuỗi cần **năm UTF-16 code unit**, trong khi bộ hiển thị có thể vẽ nó thành **một** biểu tượng.

## 2. Bộ dữ liệu đại diện và số liệu chính xác

Ta dùng sáu trường hợp kiểm thử:

- **ASCII**: năm chữ ASCII.
- **café**: có **é** U+00E9, ngoài ASCII nhưng thuộc Latin-1.
- **Việt**: có **ệ** U+1EC7, ngoài Latin-1.
- **🙂**: một điểm mã ngoài BMP.
- **👩‍💻**: chuỗi emoji có ZWJ nối ba điểm mã.
- **Việt**: dạng phân rã Unicode, gồm **V, i, e, dấu chấm dưới U+0323, dấu mũ U+0302, t**. Chuẩn hóa NFC cho dạng tương đương **Việt**.

| Dữ liệu | **length()** | **codePointCount()** | **Byte UTF-8** |
| --- | ---: | ---: | ---: |
| ASCII | 5 | 5 | 5 |
| café | 4 | 4 | 5 |
| Việt | 4 | 4 | 6 |
| 🙂 | 2 | 1 | 4 |
| 👩‍💻 | 5 | 3 | 11 |
| Việt dạng phân rã | 6 | 6 | 8 |

**Giải thích:**

- ASCII: một ký tự thông thường tương ứng một code unit và một byte UTF-8.
- Chữ **é** mã hóa UTF-8 thành hai byte nhưng chỉ một UTF-16 unit.
- Chữ **ệ** mã hóa UTF-8 thành ba byte và một UTF-16 unit.
- **🙂** dùng hai UTF-16 unit nhưng chỉ một code point; UTF-8 dùng bốn byte.
- **👩‍💻** có ba code point: 4 byte UTF-8 cho 👩, 3 byte cho ZWJ và 4 byte cho 💻, tổng cộng 11.
- Hai dấu kết hợp trong **Việt** làm tăng cả số code unit/code point và kích thước byte, dù hình thức hiển thị có thể tương tự bản dựng sẵn.

Không thể lấy một con số **“số ký tự”** rồi coi nó đồng thời là length, code point, grapheme và byte.

## 3. Ví dụ Java 17+ chạy được

Tạo tệp **StringMemoryComparison.java** với nội dung:

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class StringMemoryComparison {
    public static void main(String[] args) {
        String vietnamese = "Vi\u1EC7t";
        String decomposed = "Vie\u0323\u0302t";

        describe("ASCII", "ASCII");
        describe("Latin1", "caf\u00E9");
        describe("Vietnamese", vietnamese);
        describe("Emoji", "\uD83D\uDE42");
        describe("EmojiZWJ", "\uD83D\uDC69\u200D\uD83D\uDCBB");
        describe("Decomposed", decomposed);

        System.out.println("raw equal: "
                + decomposed.equals(vietnamese));
        System.out.println("NFC equal: "
                + Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)
                        .equals(vietnamese));
    }

    private static void describe(String name, String value) {
        int units = value.length();
        int points = value.codePointCount(0, units);
        int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;

        boolean latin1 = value.chars()
                .allMatch(unit -> unit <= 0xFF);
        int payloadEstimate = units * (latin1 ? 1 : 2);

        System.out.println(name + ": utf16=" + units
                + ", codePoints=" + points
                + ", utf8Bytes=" + utf8Bytes
                + ", compactPayloadEstimate=" + payloadEstimate);
    }
}
~~~

Các escape Unicode biểu diễn chính xác các ký tự tiếng Việt và emoji, kể cả khi font console không thể hiện thị chúng. Chương trình in nhãn ASCII để stdout không phụ thuộc cách hiển thị Unicode của terminal.

Chạy:

~~~bash
javac -encoding UTF-8 StringMemoryComparison.java
java StringMemoryComparison
~~~

Stdout (đã kiểm chứng bằng Java):

~~~text
ASCII: utf16=5, codePoints=5, utf8Bytes=5, compactPayloadEstimate=5
Latin1: utf16=4, codePoints=4, utf8Bytes=5, compactPayloadEstimate=4
Vietnamese: utf16=4, codePoints=4, utf8Bytes=6, compactPayloadEstimate=8
Emoji: utf16=2, codePoints=1, utf8Bytes=4, compactPayloadEstimate=4
EmojiZWJ: utf16=5, codePoints=3, utf8Bytes=11, compactPayloadEstimate=10
Decomposed: utf16=6, codePoints=6, utf8Bytes=8, compactPayloadEstimate=12
raw equal: false
NFC equal: true
~~~

Cột **compactPayloadEstimate** do chương trình tính theo quy tắc **một byte mỗi UTF-16 unit khi mọi unit nằm trong Latin-1, ngược lại hai byte mỗi unit**. Đây là **ước lượng riêng payload** trong những JVM sử dụng cơ chế Compact Strings, **không phải đo kích thước String trên heap**.

## 4. Compact Strings và cách hiểu đúng bộ nhớ nội bộ

Trong nhiều bản **OpenJDK/HotSpot từ Java 9**, String dùng cơ chế **Compact Strings**: nội dung có thể nằm trong mảng **byte[]** với một trong hai chế độ mã hóa nội bộ.

**LATIN1:** tất cả UTF-16 unit có giá trị không vượt quá U+00FF. JVM có thể lưu một byte cho mỗi unit.

**UTF16:** khi có unit vượt U+00FF, JVM dùng hai byte cho mỗi unit trong payload chuỗi.

Bảng ước lượng chỉ riêng **mảng dữ liệu nội bộ**:

| Chuỗi | Ứng viên chế độ | Byte payload ước tính |
| --- | --- | ---: |
| ASCII | LATIN1 | 5 |
| café | LATIN1 | 4 |
| Việt | UTF16 | 8 |
| 🙂 | UTF16 | 4 |
| 👩‍💻 | UTF16 | 10 |
| Việt phân rã | UTF16 | 12 |

Trường hợp **café** rất hữu ích để phát hiện nhầm lẫn. Nó có **5 byte UTF-8** nhưng payload LATIN1 chỉ khoảng **4 byte**. Ngược lại **Việt** có **6 byte UTF-8** nhưng payload UTF16 có thể là **8 byte**. Vì vậy **mã hóa để truyền dữ liệu** và **cách lưu trong heap** không thể đồng nhất.

Những giới hạn phải ghi rõ trong báo cáo:

1. **Compact Strings là chi tiết triển khai**, không phải bảo đảm của đặc tả Java. Không suy số byte theo cách này cho mọi JVM hay khi Compact Strings bị tắt.
2. **String object** và **byte[] object** còn có object header, tham chiếu, alignment và metadata. Tổng shallow size lớn hơn payload.
3. Nhiều biến có thể trỏ cùng String, literal có thể được intern, JVM có thể dùng tối ưu chia sẻ dữ liệu hoặc String deduplication. Không được cộng máy móc payload theo số biến.
4. Một ký tự nằm ngoài Latin-1 có thể khiến **toàn bộ payload** dùng UTF16, chứ không chỉ riêng ký tự đó.
5. Kích thước shallow và retained phụ thuộc object graph. Số byte vừa cấp phát cho một thao tác cũng khác dung lượng còn tồn tại sau garbage collection.
6. JVM có thể thay đổi biểu diễn hoặc tối ưu nối chuỗi theo phiên bản, flags và compiler/JIT.

**Ví dụ:** trong chuỗi pha trộn hàng nghìn chữ ASCII với một chữ **ệ**, ước lượng payload của String có Compact Strings theo mô hình đơn giản là **hai byte cho mỗi UTF-16 unit**. Điều này không có nghĩa toàn bộ ứng dụng đều nhân đôi bộ nhớ vì object khác và chia sẻ dữ liệu vẫn tồn tại.

## 5. Lưu ý riêng với emoji và grapheme cluster

Khi duyệt String theo từng **char**, một emoji ngoài BMP bị tách thành hai surrogate:

~~~java
String smile = "\uD83D\uDE42";
System.out.println(smile.length()); // 2
System.out.println(smile.codePointCount(0, smile.length())); // 1
System.out.println(Character.isHighSurrogate(smile.charAt(0))); // true
System.out.println(Integer.toHexString(smile.codePointAt(0))); // 1f642
~~~

Đây là snippet minh họa, đặt trong một phương thức Java khi chạy; chương trình hoàn chỉnh nằm ở phần 3.

**Sai lầm phổ biến** là dùng **substring(0, 1)** để lấy “emoji đầu tiên”. Với **🙂**, cách làm này chỉ lấy một nửa surrogate pair và có thể tạo dữ liệu Unicode không hợp lệ. Khi cần cắt theo code point, dùng **offsetByCodePoints** hoặc API xử lý code point thay vì chỉ số char tùy ý.

Nhưng **code point cũng chưa chắc tương đương ký tự nhìn thấy**. Chuỗi emoji ZWJ như **👩‍💻** có ba code point dù có thể hiển thị thành một hình. Dấu kết hợp trong tiếng Việt cũng có thể cùng chữ cơ sở tạo một grapheme cluster. Khi UI giới hạn “20 ký tự hiển thị”, cần xác định quy tắc phân đoạn **grapheme** phù hợp Unicode.

Không giả định **BreakIterator.getCharacterInstance** trên mọi phiên bản JDK đều xử lý chính xác mọi chuỗi emoji ZWJ mới theo Unicode UAX #29. Khi ứng dụng cần cắt/sắp xếp con trỏ theo grapheme, hãy kiểm tra bộ dữ liệu thực tế và cân nhắc thư viện phân đoạn grapheme cập nhật, ví dụ ICU4J phù hợp yêu cầu.

## 6. Chuẩn hóa Unicode ảnh hưởng kết quả và bộ nhớ

String.equals so sánh các đơn vị mã đã lưu; hai chuỗi có hình thức hiển thị tương tự nhưng khác dạng Unicode thường **không bằng nhau** theo equals.

~~~java
String a = "Vi\u1EC7t";       // Việt dạng dựng sẵn
String b = "Vie\u0323\u0302t"; // e kèm dấu tổ hợp

System.out.println(a.equals(b)); // false
System.out.println(
        java.text.Normalizer.normalize(
                b, java.text.Normalizer.Form.NFC)
                .equals(a)); // true
~~~

Đây cũng là snippet đặt bên trong phương thức. Dạng a dài **4 UTF-16 unit**, dài **6 byte UTF-8**. Dạng b dài **6 unit**, dài **8 byte UTF-8**. Sau NFC, dạng b có thể trở thành dạng dựng sẵn với độ dài ngắn hơn.

Nếu benchmark có dữ liệu tiếng Việt, cần nêu rõ **đầu vào đã được chuẩn hóa NFC/NFD hay chưa**. Nếu ứng dụng thực phải normalize trước mỗi thao tác, hãy đo chi phí normalize riêng hoặc đo toàn bộ pipeline, đừng loại bỏ chi phí đó mà vẫn khẳng định đây là hiệu năng end-to-end.

NFC không tự biến mọi chuỗi trông giống nhau thành bằng nhau: trường hợp biến thể chữ, quy tắc locale và dấu cần xử lý theo nghiệp vụ. Cũng không nên trộn việc chuẩn hóa với so sánh byte payload mà không công bố bước biến đổi.

## 7. Đánh giá bộ nhớ: đo cái gì và bằng công cụ nào?

Nên tách ba câu hỏi:

**Câu hỏi A: Payload UTF-8 bao nhiêu byte?** Dùng **getBytes(StandardCharsets.UTF_8).length** như chương trình phần 3. Đây là con số tái lập cho dữ liệu được mã hóa, rất hữu ích khi giới hạn dung lượng request hoặc file.

**Câu hỏi B: Một String chiếm bao nhiêu byte trên heap?** Dùng công cụ kiểm tra object layout như **JOL (Java Object Layout)** hoặc heap dump/profiler, đồng thời quan sát cả String và mảng byte nội bộ. Phân biệt **shallow size** (kích thước riêng object) và **retained size** (dữ liệu chỉ còn được giữ thông qua object đó).

**Câu hỏi C: Mỗi thao tác cấp phát bao nhiêu bộ nhớ?** Dùng allocation profiler hoặc bộ đếm **B/op** trong một microbenchmark đáng tin cậy. Ví dụ, tạo chuỗi mới, mã hóa UTF-8 và normalize có thể tạo số đối tượng tạm khác nhau dù kết quả đầu ra có cùng số byte.

Không lấy hiệu giữa hai giá trị **Runtime.totalMemory() - Runtime.freeMemory()** trước/sau một thao tác ngắn làm “kích thước chính xác của String”. Con số còn phụ thuộc GC, allocation buffer, class loading, string pool, JIT và các đối tượng nền.

Nếu cần đo heap theo nhóm ASCII/tiếng Việt/emoji:

1. Cố định **JDK version, HotSpot/JVM, architecture, heap settings** và trạng thái Compact Strings; ghi lại các tham số thực tế.
2. Tạo cùng số phần tử theo từng chính sách so sánh: cùng UTF-16 unit, cùng code point, cùng byte UTF-8 hoặc cùng grapheme.
3. Tạo đối tượng thật ở runtime và giữ tham chiếu sống trong collection trong giai đoạn đo; tránh đo toàn literal được intern hoặc constant folded.
4. Chọn phép đo phù hợp: shallow bytes, retained bytes, allocation rate hay kích thước byte mã hóa; ghi rõ có tính overhead của collection hay không.
5. Lặp phép đo và quan sát theo cỡ mẫu; kiểm tra sharing, deduplication và object alignment trước khi kết luận.

**Một byte payload không phải một byte heap**. Đặc biệt đối với hàng triệu chuỗi rất ngắn, overhead của object và tham chiếu có thể chi phối tổng bộ nhớ nhiều hơn chênh lệch giữa một và hai byte payload mỗi code unit.

## 8. Đánh giá hiệu năng CPU: thiết kế phép so sánh công bằng

Phải xác định thao tác nào được đo:

| Thao tác | Ý nghĩa về hiệu năng |
| --- | --- |
| **length()** | Trả về số UTF-16 code unit; không đếm grapheme |
| **charAt(i)** | Truy cập UTF-16 unit; có thể trả surrogate |
| **codePointAt() / codePoints()** | Duyệt Unicode code point; xử lý khác với duyệt char |
| **getBytes(UTF_8)** | Mã hóa UTF-8, thường cấp phát mảng byte |
| **new String(bytes, UTF_8)** | Giải mã UTF-8 sang String |
| **Normalizer.normalize(..., NFC)** | Chuẩn hóa Unicode, có chi phí theo dữ liệu |
| **StringBuilder.append()** | Ghép các đoạn chuỗi với buffer có thể được mở rộng |

Không có định luật chung “ASCII luôn nhanh hơn tiếng Việt” hoặc “emoji luôn chậm hơn”. **length()** có đặc điểm rất khác **encode UTF-8**, và kết quả còn phụ thuộc dữ liệu, version JVM, JIT, warm-up, tính nhất quán của workload.

### Cố định cùng loại khối lượng công việc

Tối thiểu nên chạy nhiều nhóm thí nghiệm:

- **Cùng số UTF-16 code unit:** phù hợp khi so hoạt động theo String.length hoặc charAt.
- **Cùng số Unicode code point:** phù hợp khi thao tác phải duyệt code point.
- **Cùng số byte UTF-8:** phù hợp với ràng buộc kích thước payload.
- **Cùng số grapheme cluster:** phù hợp với thao tác UI theo ký tự cảm nhận, cần bộ phân đoạn đúng.

Một chuỗi gồm 5 emoji ZWJ mang nhiều dữ liệu hơn chuỗi gồm 5 chữ ASCII theo byte và code unit; không thể gọi đây là phép so sánh cùng “5 ký tự” nếu chưa xác định ý nghĩa của ký tự.

### Benchmark Java đúng phương pháp

Đối với microbenchmark, dùng **JMH (Java Microbenchmark Harness)** thay vì đo một lần bằng System.nanoTime. Quy trình chuẩn cần:

1. Warm-up cho JVM/JIT và dùng nhiều lần chạy độc lập (**fork**).
2. Dữ liệu tạo trước trong **@State** nếu chỉ đo thao tác String; nếu muốn đo cả tạo dữ liệu, phải định nghĩa benchmark riêng.
3. Dùng kết quả để tránh **dead-code elimination** (ví dụ JMH **Blackhole**).
4. Chọn đúng đơn vị **ns/op**, **ops/s** và với allocation dùng **B/op** khi profiler hỗ trợ.
5. Ghi cấu hình JDK, GC, heap, CPU, số thread, size và tỉ lệ các dạng chuỗi.
6. Báo cáo trung bình cùng phân tán/sai số và kiểm tra phép đo tăng tuyến tính hay xuất hiện điểm bất thường.

Ví dụ một benchmark mã hóa 1.000 UTF-16 unit thuộc ba nhóm nội dung trả lời câu hỏi **chi phí encode ở cùng số unit**. Một benchmark khác cố định cùng 4.096 byte UTF-8 trả lời câu hỏi **chi phí encode trên cùng kích thước payload**. Hai kết quả không nhất thiết cho cùng thứ tự tốc độ, vì chúng đánh giá hai workload khác nhau.

Ngoài microbenchmark, với API/web/file thực tế còn phải đo **end-to-end**: chuẩn hóa, encode/decode, xử lý String, ghi/đọc I/O và các bước phụ trợ. Chênh lệch vài nanosecond ở một API có thể không đáng kể khi I/O chi phối.

## 9. Ví dụ áp dụng trong sản phẩm

### 9.1. Giới hạn request theo byte

Nếu endpoint chỉ cho phép 1.024 byte UTF-8, đừng kiểm tra **text.length() <= 1024**. Với tiếng Việt và emoji, một code point có thể sử dụng nhiều byte UTF-8.

~~~java
int utf8Bytes = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length;
boolean withinLimit = utf8Bytes <= maxUtf8Bytes;
~~~

Đoạn này minh họa, cần khai báo **text** và **maxUtf8Bytes** trong phạm vi phù hợp. Nếu chuỗi quá lớn hoặc cần streaming, có thể dùng encoder để tránh tạo toàn bộ byte[] chỉ nhằm tính kích thước.

### 9.2. Cắt nội dung theo giới hạn ký tự hiển thị

Nếu giao diện giới hạn 20 “ký tự người dùng nhìn thấy”, substring theo **20 char** có thể cắt một cặp surrogate; cắt theo **20 code point** vẫn có thể chia đôi một chuỗi emoji nối ZWJ hoặc dấu kết hợp. Hãy xác định thuật toán grapheme phù hợp trước khi cắt.

### 9.3. Tạo khóa và so sánh tiếng Việt

Nếu hai nguồn dữ liệu một bên dùng chữ dựng sẵn và một bên dùng dấu kết hợp, **String.equals** và hashCode có thể khác. Chuẩn hóa về một dạng theo quy tắc hệ thống **cả lúc ghi lẫn lúc tra cứu** trước khi đưa vào HashMap/HashSet để tránh khóa “giống mắt thường nhưng không bằng nhau”.

### 9.4. Ghép nhiều đoạn String

Khi ghép rất nhiều đoạn trong vòng lặp, có thể dùng **StringBuilder**:

~~~java
StringBuilder builder = new StringBuilder();
for (String part : parts) {
    builder.append(part);
}
String result = builder.toString();
~~~

Đoạn này minh họa với collection/array **parts** đã có. Không khẳng định StringBuilder luôn nhanh hơn phép cộng chuỗi: compiler và JIT có các tối ưu riêng, phải so sánh đúng workload.

## 10. Lỗi thường gặp

| Lỗi hoặc ngộ nhận | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng **length()** làm số byte mạng | Giới hạn byte sai với Unicode | Đo UTF-8 bytes trực tiếp |
| Coi một emoji = một char | Cắt vỡ surrogate pair | Duyệt code point, phân đoạn grapheme khi cần |
| Coi một code point = một ký tự hiển thị | Emoji ZWJ và dấu tổ hợp bị đếm sai | Dùng thuật toán grapheme phù hợp |
| Coi mọi ký tự tiếng Việt = hai byte UTF-8 | Sai với các dấu và điểm mã khác nhau | Đo theo code point thực tế |
| Coi **café** buộc phải dùng payload UTF16 | é thuộc Latin-1 | Phân biệt ASCII với Latin-1 |
| Lấy payload Compact String bằng byte UTF-8 | Lẫn hai cơ chế mã hóa | Tách byte nội bộ với serialized bytes |
| Lấy payload estimate làm heap object size | Bỏ qua header, byte[] và sharing | Dùng JOL/profiler/heap dump |
| Benchmark **nanoTime** một lượt | Nhiễu JIT/GC và loại bỏ phép tính | Dùng JMH với warm-up, forks, Blackhole |
| Bỏ qua NFC/NFD khi so sánh | Chuỗi tiếng Việt nhìn giống nhưng equals khác | Chuẩn hóa đồng nhất theo nghiệp vụ |
| Đo ASCII ngắn với emoji dài hơn rồi so tốc độ trực tiếp | Workload không công bằng | Cố định tiêu chí so sánh |

## 11. Mẫu báo cáo đánh giá tái lập

Một báo cáo kỹ thuật đủ tin cậy nên có:

**Dữ liệu:** sáu nhóm ASCII/Latin-1/tiếng Việt dựng sẵn/tiếng Việt phân rã/emoji đơn/emoji ZWJ; số phần tử, tỉ lệ nhóm, cách chuẩn hóa và cách tạo mẫu.

**Mã hóa:** với từng nhóm, bảng **UTF-16 units**, **code points**, **UTF-8 bytes** như phần 2. Nếu đo grapheme, ghi bộ phân đoạn, version và quy tắc Unicode.

**JVM:** Java 17 hay 21 hoặc bản khác, HotSpot hoặc JVM khác, Compact Strings bật/tắt, heap/GC flags, CPU và môi trường chạy.

**Bộ nhớ:** ghi rõ đo **byte mã hóa**, **payload nội bộ ước tính**, **shallow size**, **retained size** hay **allocation/op**; không gọi chúng chung là “size String”.

**Hiệu năng:** ghi thao tác, cùng đơn vị workload, warm-up/forks, kết quả theo đơn vị, phương sai và thời gian chạy toàn pipeline nếu phù hợp.

**Kết luận:** rút ra nhận xét **trong điều kiện đã đo**, có thể lặp lại và không khái quát thành tính chất bất biến của mọi JVM.

## 12. Câu hỏi tự kiểm tra

**1. Vì sao "café" dùng 5 byte UTF-8 nhưng có thể chỉ cần 4 byte payload Compact String?**

Vì **é U+00E9** mã hóa UTF-8 bằng hai byte nhưng vẫn nằm trong dải Latin-1 để lưu một byte trong cơ chế Compact Strings. Hai con số thuộc **hai cách mã hóa khác nhau**.

**2. Vì sao "Việt" có length 4, codePointCount 4, nhưng UTF-8 là 6 byte?**

Vì **ệ** là một code point thuộc BMP nhưng cần ba byte UTF-8; ba ký tự còn lại cần một byte mỗi ký tự.

**3. Chuỗi "🙂" có length 2; có phải hai emoji không?**

Không. Nó gồm một code point ngoài BMP và hai UTF-16 code unit.

**4. Nếu emoji "👩‍💻" có ba code point thì người dùng luôn thấy ba biểu tượng?**

Không. ZWJ có thể nối các phần thành một glyph; hình thức hiển thị phụ thuộc môi trường. Code point khác grapheme.

**5. Có được kết luận "emoji tốn gấp đôi heap" từ hai bảng payload không?**

Không. Phải cố định cỡ mẫu, nội dung, cơ chế JVM và đo cả object overhead/sharing. Bảng payload không đo heap thực.

**6. Khi so tốc độ giữa ba loại chuỗi, phép đo nào cần cố định?**

Phải cố định loại thao tác cùng **đơn vị workload** phù hợp: UTF-16 unit, code point, grapheme hay byte UTF-8; đồng thời kiểm soát JIT, warm-up, allocation và môi trường máy.

**Ghi nhớ:** hiệu năng String đa ngôn ngữ chỉ có ý nghĩa khi phân biệt **UTF-16 length**, **Unicode code point/grapheme**, **byte UTF-8**, **payload nội bộ** và **heap thực tế**. Kết luận đúng là kết luận gắn với **dữ liệu và phép đo xác định**.
