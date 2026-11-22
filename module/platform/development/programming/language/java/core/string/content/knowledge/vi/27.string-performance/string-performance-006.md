# Đánh đổi giữa tính dễ đọc và tối ưu theo dữ liệu đo khi xử lý String trong Java

## 1. Mục tiêu: mã dễ hiểu, đúng trước; tối ưu khi có bằng chứng

Xử lý `String` hiện diện trong hầu hết ứng dụng Java: ghép thông điệp, tạo đường dẫn, lọc dữ liệu, chuẩn hóa chuỗi, tách ký tự, định dạng số, đọc JSON hoặc tạo nội dung trả về. Nhiều cách viết có cùng kết quả nhưng khác độ rõ ràng, mức cấp phát bộ nhớ, lượng xử lý và khả năng bảo trì.

**Nguyên tắc cốt lõi:** ưu tiên cách diễn đạt đúng, dễ đọc và dễ kiểm thử; khi có yêu cầu hiệu năng cụ thể hoặc số đo cho thấy đoạn xử lý chuỗi là nút thắt, mới chọn phương án tối ưu có thể chứng minh là cải thiện. Kết quả đo nên phản ánh đúng dữ liệu, quy mô và điều kiện chạy thực tế.

Điều này không có nghĩa bỏ qua các lỗi thiết kế dễ nhận thấy. Ví dụ, việc nối chuỗi tăng dần bằng `+=` trong một vòng lặp dài có khả năng gây nhiều cấp phát và sao chép lại; dùng một `StringBuilder` xuyên suốt vòng lặp thường là cách viết vừa đúng ý định vừa hợp lý. Nhưng đổi mọi `"Hello " + name` sang một `StringBuilder` nhiều dòng không tự động làm ứng dụng nhanh hơn.

Ba câu hỏi trước khi sửa mã:

1. **Đúng không?** Hai cách làm có giống nhau về Unicode, `null`, dấu phân cách, locale, thứ tự, lỗi và kết quả không?
2. **Chậm ở đâu?** Profiler, benchmark hoặc chỉ số production có chỉ ra đoạn chuỗi này góp phần đáng kể vào mục tiêu cần cải thiện không?
3. **Đáng đổi không?** Mức cải thiện trong workload đại diện có đủ lớn và ổn định để bù thêm mã, bộ nhớ, rủi ro và chi phí bảo trì không?

## 2. Bốn tầng tối ưu cần phân biệt

Không phải mọi thay đổi nhanh hơn trong một phép đo vi mô đều cải thiện ứng dụng.

| Tầng | Câu hỏi cần trả lời | Bằng chứng phù hợp |
|---|---|---|
| Tính đúng và khả năng bảo trì | Mã có rõ nghĩa, đúng định dạng, dễ kiểm thử và thay đổi không? | Review, unit test, so sánh kết quả với trường hợp biên |
| Cục bộ: xử lý String | Phép nối, chuyển đổi hoặc regex có tốn CPU/cấp phát quá mức không? | JMH với đầu vào đại diện, profiler CPU và allocation |
| Luồng xử lý ứng dụng | Đoạn String có thực sự nằm trên critical path không? | Profiling request, số lần gọi, phân tích heap/GC |
| Trải nghiệm/hệ thống | Thay đổi có cải thiện latency, throughput, tài nguyên hoặc chi phí không? | Load test, p95/p99 latency, throughput, GC và memory thực tế |

Ví dụ: thay `String.format` bằng `StringBuilder` trong một đoạn chạy 500 lần/ngày có thể cải thiện phép đo trong JMH mà gần như không ảnh hưởng thời gian phản hồi ứng dụng nếu phần lớn độ trễ là truy vấn dữ liệu hoặc mạng. Ngược lại, thay đổi nhỏ trong một vòng lặp chạy hàng triệu lần trên đường xử lý nóng có thể đáng giá.

Trước khi tối ưu, xác định mục tiêu: giảm latency, tăng throughput, giảm byte cấp phát trên một yêu cầu, giảm thời gian GC, hay giảm bộ nhớ lưu giữ. Các mục tiêu này có thể không cùng đi theo một hướng.

## 3. Một số lựa chọn String thường gặp

### 3.1. Phép nối `+`: ưu tiên khi biểu thức ngắn

~~~java
String greeting = "Xin chào, " + name + "!";
~~~

Đây là cách viết rõ ràng cho một vài thành phần cố định. Với Java hiện đại, trình biên dịch và JVM có cơ chế tối ưu nối chuỗi (chẳng hạn `invokedynamic` và `StringConcatFactory` trong triển khai thông thường từ Java 9), nên không chính xác khi mặc định rằng mỗi dấu `+` đồng nghĩa một `StringBuilder` được tạo hoặc một lần cấp phát độc lập.

Tuy nhiên, mẫu cập nhật dồn vào cùng biến trong một vòng lặp lớn cần chú ý:

~~~java
String result = "";
for (String item : items) {
    result += item;
}
~~~

Vì `String` bất biến, thao tác nối phải tạo kết quả mới về mặt ngữ nghĩa. Qua nhiều vòng lặp, lượng dữ liệu đã nối có thể bị sao chép nhiều lần; tổng chi phí có thể tăng nhanh theo số phần tử. Cách tự nhiên hơn cho kiểu tích lũy này là:

~~~java
StringBuilder builder = new StringBuilder();
for (String item : items) {
    builder.append(item);
}
String result = builder.toString();
~~~

Đây là lựa chọn thiết kế cho một quá trình xây dựng chuỗi dài; không phải quy tắc thay thế mọi dấu `+` trong mã nguồn.

### 3.2. `String.join`: ý định ghép danh sách rõ nhất

~~~java
List<String> tags = List.of("Java", "Spring", "SQL");
String output = String.join(", ", tags);
// Java, Spring, SQL
~~~

Nếu nhiệm vụ đơn thuần là ghép một dãy với cùng dấu phân cách, `String.join` diễn đạt trực tiếp ý định và giảm lỗi dư dấu phân cách đầu/cuối. Không cần tự cài đặt vòng lặp chỉ vì cho rằng vòng lặp chắc chắn nhanh hơn.

Khi cần liên tục thêm dữ liệu từng bước, tiền tố/hậu tố hoặc quy tắc rỗng, `StringJoiner` có thể phù hợp:

~~~java
StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("Java").add("Spring");
// [Java, Spring]
~~~

Dùng `StringBuilder` nếu cần kiểm soát chi tiết hơn: định dạng xen kẽ, chèn/xóa ký tự hoặc nhiều quy tắc nối khác nhau.

### 3.3. `StringBuilder`: hợp lý ở đoạn tạo chuỗi có trạng thái

~~~java
StringBuilder builder = new StringBuilder();
for (int i = 0; i < tags.size(); i++) {
    if (i > 0) {
        builder.append(", ");
    }
    builder.append(tags.get(i));
}
String output = builder.toString();
~~~

So với `String.join`, cách này dài hơn và tự gánh trách nhiệm quản lý dấu phân cách. Nó trở nên có giá trị khi yêu cầu đầu ra phức tạp hơn và việc xây dựng chuỗi trong một bộ đệm là tự nhiên.

Một chú ý về trường hợp biên: đừng dùng `builder.length() > 0` làm dấu hiệu chắc chắn “đã thêm ít nhất một phần tử” nếu phần tử đầu có thể là chuỗi rỗng. Dùng chỉ số hoặc biến `first` để bảo toàn số phần tử đã xử lý.

`StringBuilder` là đối tượng mutable, không an toàn khi nhiều luồng tự do sửa cùng instance. Thường tạo nó trong phạm vi một phương thức/tác vụ và không chia sẻ giữa các request.

### 3.4. Định dạng và regex: ưu tiên đúng ý nghĩa

~~~java
String label = String.format(Locale.US, "price=%.2f", 12.5);
// price=12.50
~~~

Thay bằng `"price=" + price` có thể nhanh trong một số trường hợp nhưng **không tương đương**: kết quả có thể thành `price=12.5` và không giữ quy tắc hai chữ số thập phân. Nếu cần locale hoặc làm tròn, phải bảo toàn hành vi đó.

Với regex, đoạn sau dễ hiểu:

~~~java
String normalized = text.replaceAll("\\s+", " ");
~~~

Nếu cùng một mẫu regex được dùng lặp đi lặp lại trên đường xử lý nóng, có thể cân nhắc biên dịch một `Pattern` dùng lại:

~~~java
private static final Pattern WHITESPACE = Pattern.compile("\\s+");

// Trong phương thức:
String normalized = WHITESPACE.matcher(text).replaceAll(" ");
~~~

`Pattern` được biên dịch trước có thể tránh chi phí biên dịch pattern lặp lại. Nhưng tổng thời gian vẫn phụ thuộc dữ liệu và tần suất sử dụng; kiểm chứng bằng đo đạc. Không thay regex bằng một vòng lặp tự viết nếu vô tình làm thay đổi hành vi đối với tab, xuống dòng, ký tự Unicode hoặc đầu vào đặc biệt.

## 4. “Tương đương” là điều kiện tiên quyết để so hiệu năng

Muốn so sánh hai cách viết, phải xác định một **hợp đồng kết quả** chung. Ví dụ với danh sách các thành phần:

- Dữ liệu có thể là chuỗi rỗng không?
- Có thể chứa `null` không, và khi gặp `null` thì giữ, bỏ qua hay báo lỗi?
- Có cần dấu phân cách, escape/quote, prefix/suffix không?
- Thứ tự phần tử có bắt buộc giữ nguyên không?
- Kết quả phải theo locale nào?
- Unicode được xử lý theo code unit, code point hay grapheme cluster?
- Có yêu cầu định dạng chuẩn CSV, JSON, SQL, URL không?

Ví dụ, hai cách sau **không tương đương** nếu danh sách có chuỗi rỗng:

~~~java
List<String> items = List.of("", "B");

String joined = String.join("|", items); // |B

StringBuilder wrong = new StringBuilder();
for (String item : items) {
    if (wrong.length() > 0) {
        wrong.append('|');
    }
    wrong.append(item);
}
// wrong.toString() là "B", không phải "|B"
~~~

Nếu muốn so đo `String.join` với `StringBuilder`, phiên bản builder phải bảo toàn đúng việc phân cách phần tử, kể cả chuỗi rỗng:

~~~java
StringBuilder correct = new StringBuilder();
for (int i = 0; i < items.size(); i++) {
    if (i != 0) {
        correct.append('|');
    }
    correct.append(items.get(i));
}
// correct.toString() là "|B"
~~~

Tối ưu không được làm thay đổi dữ liệu mà người dùng hoặc hệ thống khác quan sát được. Hãy có unit test cho đầu vào rỗng, một phần tử, nhiều phần tử, Unicode, dữ liệu dài và các quy tắc lỗi trước khi so hiệu năng.

## 5. Hiểu chi phí thực tế của String

### 5.1. Cấp phát và sao chép

`String` bất biến giúp giá trị ổn định và có thể chia sẻ an toàn giữa luồng khi bản thân đối tượng được xuất bản đúng cách. Đổi lại, việc xây dựng một kết quả mới có thể cần cấp phát và sao chép dữ liệu.

Cần phân biệt:

- **Số đối tượng cấp phát**: có thể ảnh hưởng áp lực GC.
- **Số byte cấp phát**: một ít đối tượng lớn vẫn có thể tốn nhiều bộ nhớ.
- **Tổng ký tự/byte phải duyệt hoặc sao chép**: ảnh hưởng CPU và băng thông bộ nhớ.
- **Bộ nhớ giữ lại lâu**: ảnh hưởng heap, GC và cache; khác với cấp phát ngắn hạn.
- **Chi phí cuối cùng của `toString()`**: xây dựng trong bộ đệm vẫn cần tạo một kết quả `String` ở cuối.

Đừng suy ra số cấp phát chỉ từ việc đếm số dòng mã. JVM có tối ưu JIT, phân tích escape và khả năng loại bỏ một số cấp phát; mức tối ưu phụ thuộc ngữ cảnh và JDK. Dùng profiler/công cụ đo allocation để biết chuyện gì thật sự diễn ra.

### 5.2. Chi phí thuật toán thường quan trọng hơn vài ký tự mã

Nếu mỗi vòng lặp phải ghép cả phần chuỗi đã có, chi phí có thể tăng rất nhanh khi số lượng phần tử tăng. Trong khi đó, một `StringBuilder` được sử dụng xuyên suốt thường duy trì khả năng thêm dữ liệu hiệu quả.

Tuy nhiên, không cần tự suy đoán công thức chi phí chính xác cho mọi phiên bản compiler/JVM. Điều cần nhớ là **đặc điểm tăng trưởng theo kích thước dữ liệu**. Hãy thử nhiều cỡ dữ liệu đại diện thay vì chỉ một chuỗi ngắn.

### 5.3. `StringBuilder` và capacity

Có thể khởi tạo `StringBuilder` với dung lượng dự kiến:

~~~java
StringBuilder builder = new StringBuilder(1024);
~~~

Điều này có thể giảm số lần mở rộng bộ đệm nếu đã biết gần đúng kích thước đầu ra. Nhưng cấp phát quá lớn cho hàng triệu request nhỏ cũng làm tăng chi phí bộ nhớ. Chỉ pre-size khi đã có ước lượng hợp lý và số đo chứng minh nó hữu ích.

`length()` là độ dài nội dung hiện có; `capacity()` là sức chứa bộ đệm và có thể lớn hơn `length()`. Đây không phải hai đại lượng tương đương.

### 5.4. Compact Strings và khác biệt môi trường

Các JDK hiện đại có tối ưu biểu diễn `String` (chẳng hạn Compact Strings), nên số byte chiếm dụng có thể phụ thuộc nội dung ký tự và phiên bản JVM. Không nên giả định mọi `char` của mọi chuỗi tương ứng cố định hai byte heap, cũng không nên suy ra hiệu năng thực chỉ từ một mô hình bộ nhớ đơn giản.

Nếu tối ưu cấp phát là yêu cầu quan trọng, ghi lại JDK, JVM, cấu hình heap, GC, dạng dữ liệu Latin/Unicode và các tham số đo để kết quả có thể tái hiện.

## 6. Chọn phép đo theo vấn đề cần giải quyết

Đo đạc nên bắt đầu từ triệu chứng thực tế:

| Triệu chứng | Đo cái gì trước? | Có thể khám phá |
|---|---|---|
| Request chậm | p95/p99 latency, CPU profile | Chi phí xử lý String có nằm trên critical path không |
| Throughput giảm khi tải tăng | requests/s, CPU utilization, contention | Vòng lặp xử lý, mã hóa/giải mã hay log quá nhiều |
| GC dày đặc | allocation rate, bytes/op, thời gian GC | Tạo nhiều String tạm, phân tích regex lặp, format lặp |
| Heap cao | retained heap, heap dump, số lượng đối tượng | Cache String không giới hạn hoặc giữ dữ liệu lâu |
| Đoạn xử lý cụ thể bị nghi chậm | JMH time/op hoặc throughput/op | So sánh triển khai tương đương ở nhiều kích thước dữ liệu |

Đo cả **baseline** trước sửa và ứng viên sau sửa. Một kết quả đo riêng lẻ sau tối ưu không thể cho biết cải thiện bao nhiêu.

Một cách đặt mục tiêu cụ thể: “Giảm allocation của bước tạo kết quả xuống mức đủ làm giảm GC dưới tải đại diện, không đổi đầu ra”. Mục tiêu nên dựa trên nhu cầu và số đo thực, không đặt con số cải thiện tùy ý.

## 7. Vì sao benchmark bằng System.nanoTime() dễ sai?

Một cách thử thường thấy:

~~~java
long start = System.nanoTime();
// Một lần gọi mã cần đo
long elapsed = System.nanoTime() - start;
~~~

Đo một lần như vậy không đủ để kết luận API nào nhanh hơn. Kết quả bị ảnh hưởng bởi nhiều yếu tố: khởi động JVM, biên dịch JIT, warm-up, GC, lập lịch hệ điều hành, CPU frequency, cache, input quá nhỏ, noise và thậm chí việc trình biên dịch tối ưu bỏ tính toán không được sử dụng.

Lặp nhiều lần trong cùng một phương thức cũng chưa chắc giải quyết được lỗi đo: kết quả có thể bị JIT coi là bất biến, benchmark có thể tối ưu khác với production, hoặc một phiên bản đang làm ít việc hơn phiên bản kia.

Với microbenchmark Java, **JMH (Java Microbenchmark Harness)** là lựa chọn tiêu chuẩn vì cung cấp warm-up, các vòng đo, fork JVM, quản lý trạng thái và cách tiêu thụ kết quả. Nhưng JMH cũng không thay thế profiling và load test toàn hệ thống.

## 8. Thiết kế phép thử công bằng với JMH

Phần này minh họa **mã benchmark JMH**, không phải chương trình Java độc lập chỉ cần `javac` với JDK. Cần cài dependency JMH và cấu hình annotation processor của JMH trong dự án trước khi chạy.

~~~java
import java.util.List;
import java.util.stream.IntStream;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(2)
public class JoinBenchmark {
    @Param({"10", "100", "1000"})
    public int size;

    private List<String> items;

    @Setup(Level.Trial)
    public void setup() {
        items = IntStream.range(0, size)
                .mapToObj(Integer::toString)
                .toList();
    }

    @Benchmark
    public String usingJoin() {
        return String.join(",", items);
    }

    @Benchmark
    public String usingBuilder() {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < items.size(); i++) {
            if (i > 0) {
                builder.append(',');
            }
            builder.append(items.get(i));
        }
        return builder.toString();
    }
}
~~~

Giải thích thiết kế:

1. Hai phiên bản tạo **cùng một chuỗi** cho cùng danh sách đầu vào; không thực hiện thêm việc lọc, format hay tạo dữ liệu ngẫu nhiên ở chỉ một phiên bản.
2. `@Param` kiểm thử ba quy mô để thấy xu hướng khi lượng dữ liệu tăng; những kích thước thực tế của ứng dụng có thể khác và cần thay thế phù hợp.
3. `@Setup(Level.Trial)` tạo dữ liệu ngoài đoạn được đo để không trộn chi phí tạo input với chi phí ghép chuỗi.
4. `@State(Scope.Thread)` cho mỗi luồng benchmark trạng thái riêng, tránh chia sẻ `List` hoặc bộ đệm mutable theo cách vô tình gây nhiễu.
5. `@Warmup` cho JVM có cơ hội biên dịch/tối ưu trước khi đo; `@Measurement` thu kết quả sau warm-up; `@Fork` đo trên JVM mới để giảm phụ thuộc trạng thái một lần chạy.
6. Kết quả `String` được trả từ `@Benchmark` để JMH có thể sử dụng đầu ra thay vì để trình biên dịch dễ loại bỏ toàn bộ phép tính.

**Không điền sẵn “kết quả winner” cho hai phương thức.** Máy, phiên bản JDK, dữ liệu và thiết lập JMH khác nhau có thể tạo thứ tự và mức chênh lệch khác nhau.

### Những biến số quan trọng cần lưu lại

- Phiên bản JDK/JVM, GC, CPU, hệ điều hành, cấu hình heap.
- Cỡ và phân bố input: số phần tử, độ dài, ASCII/Unicode, có null/rỗng hay không.
- Chế độ JMH: average time hoặc throughput, số warm-up/measurement/fork.
- Đơn vị đo rõ ràng: microsecond/op, ops/s, bytes/op.
- Phương pháp so sánh: cùng máy, điều kiện tải ổn định, kết quả qua nhiều lần thử; xem độ dao động và sai số chứ không chỉ giá trị trung bình.
- Kết quả kiểm thử tính đúng của cả hai triển khai trên cùng tập dữ liệu.

Nếu quan tâm memory allocation, dùng profiler JMH phù hợp (ví dụ GC profiler) để xem bytes/op bên cạnh thời gian. Nếu quan tâm latency trong dịch vụ, đo tiếp dưới tải ở tầng request.

## 9. Ví dụ Java 17+ chạy được: giữ kết quả, so hai cách viết

Tạo tệp **`StringTradeoffDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

public class StringTradeoffDemo {
    private static final Pattern SPACES = Pattern.compile("\\s+");

    static String readableJoin(List<String> parts) {
        return String.join(" | ", parts);
    }

    static String manualBuilder(List<String> parts) {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < parts.size(); i++) {
            if (i > 0) {
                builder.append(" | ");
            }
            builder.append(parts.get(i));
        }
        return builder.toString();
    }

    public static void main(String[] args) {
        List<String> parts = List.of("Java", "Spring", "SQL");
        String readable = readableJoin(parts);
        String manual = manualBuilder(parts);

        System.out.println("join: " + readable);
        System.out.println("builder: " + manual);
        System.out.println("equivalent: " + readable.equals(manual));

        List<String> edge = List.of("", "B");
        System.out.println("empty: " + String.join("|", edge));

        String formatted = String.format(
                Locale.US, "price=%.2f", 12.5);
        System.out.println(formatted);

        String text = "  a   b \t c  ";
        String normalized = SPACES.matcher(text.strip())
                .replaceAll(" ");
        System.out.println("normalized: " + normalized);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StringTradeoffDemo.java
java StringTradeoffDemo
~~~

Đầu ra:

~~~text
join: Java | Spring | SQL
builder: Java | Spring | SQL
equivalent: true
empty: |B
price=12.50
normalized: a b c
~~~

Ở ví dụ này, `readableJoin()` truyền đạt yêu cầu rõ hơn và dễ thay đổi hơn. `manualBuilder()` được giữ để cho thấy cách xây dựng một triển khai tương đương khi có nhu cầu bổ sung quy tắc hoặc khi benchmark cho thấy lợi ích đáng kể. Việc hai kết quả bằng nhau **chưa chứng minh** một cách nhanh hơn cách còn lại.

`String.format` bảo toàn yêu cầu hai chữ số thập phân; `Pattern` lưu regex để tái sử dụng nếu áp dụng cho nhiều chuỗi. Các lựa chọn này mang ý nghĩa khác nhau: độ rõ ràng, tính đúng của định dạng và cơ hội giảm công việc lặp; không thể thay thế đánh giá thực tế bằng suy luận từ độ dài mã.

## 10. Đọc kết quả benchmark đúng cách

Giả sử một phép đo JMH (chỉ là ví dụ về **cách phân tích**, không phải số liệu thực nghiệm) cho thấy hai bản chênh lệch ít trên workload nhỏ. Trước khi chọn bản có số trung bình thấp hơn, hãy xem:

- Chênh lệch có lớn so với độ dao động/sai số không?
- Chênh lệch có tồn tại qua nhiều lần chạy, nhiều fork và bộ dữ liệu không?
- Khi input tăng, hiệu năng thay đổi ra sao?
- Có khác biệt allocation hoặc GC làm thay đổi mục tiêu hay không?
- Số lần gọi thực tế đủ nhiều để tác động đến request latency hoặc tài nguyên máy chủ không?
- Phiên bản nhanh hơn có gây thêm lỗi, phức tạp hoặc khó bảo trì không?

**Hiệu năng cục bộ khác hiệu quả thực tế.** Nếu một đoạn chỉ chiếm 1% thời gian request, ngay cả tối ưu lý tưởng loại bỏ hoàn toàn chi phí đoạn đó cũng chỉ có thể tiết kiệm tối đa khoảng 1% tổng thời gian trong giả định các phần còn lại không đổi (ý tưởng của Amdahl's law). Đừng suy ra rằng cải thiện 2 lần một hàm tự động cải thiện 2 lần toàn ứng dụng.

Với các mục tiêu như giảm độ trễ đầu cuối, quyết định cuối cùng cần dựa trên số đo đầu cuối và phạm vi tác động thực, ngoài microbenchmark.

## 11. Khi nào nên chấp nhận mã phức tạp hơn?

Một tối ưu hóa đáng cân nhắc nếu đồng thời có nhiều điều kiện:

1. Nó nằm ở đoạn xử lý quan trọng theo profiler hoặc chỉ số vận hành.
2. Nó cải thiện chỉ số được ưu tiên trên input và quy mô đại diện.
3. Kết quả vẫn đúng theo bộ test hiện có, gồm các trường hợp biên.
4. Chênh lệch vượt noise đo đạc và được tái hiện.
5. Chi phí tăng về code complexity, allocation, bảo trì và rủi ro đã được xem xét.
6. Người đọc sau này có thể hiểu **vì sao** phương án phức tạp được chọn.

Ví dụ comment hợp lý:

~~~java
// This formatter is reused within one request because profiling
// identified repeated pattern compilation on the hot path.
~~~

Comment giải thích lý do đo được và điều kiện áp dụng, thay vì phát biểu chung kiểu “fast code”.

Nếu một benchmark đã cũ hoặc điều kiện JDK thay đổi, tối ưu từng hợp lý có thể cần được đánh giá lại. Mã dễ hiểu hơn là lợi ích thực: giúp sửa lỗi, kiểm thử và mở rộng mà không vô tình đổi hợp đồng dữ liệu.

## 12. Checklist trước và sau một tối ưu String

**Trước khi sửa:**

1. Mô tả chính xác hành vi mong muốn và các dữ liệu biên cần giữ nguyên.
2. Có số đo baseline cho latency/throughput/allocation đúng nhu cầu.
3. Dùng profiler xác định đoạn thực sự tốn tài nguyên.
4. Ghi rõ JDK, input và môi trường đo.
5. Xác định giả thuyết: ví dụ giảm việc biên dịch regex lặp lại hoặc tránh chuỗi trung gian trong vòng lặp.

**Sau khi sửa:**

1. Chạy lại unit test và các ca Unicode/locale/null/rỗng phù hợp.
2. Đo ứng viên và baseline trong điều kiện tương đương.
3. Kiểm tra độ dao động, allocation/GC và hành vi khi input tăng.
4. Đo tác động ở tầng ứng dụng hoặc load test nếu mục tiêu là hiệu năng hệ thống.
5. Chỉ giữ phần phức tạp thêm nếu lợi ích đáng kể, lặp lại được và đáng chi phí bảo trì.
6. Ghi chú ngắn lý do tối ưu và điều kiện đo để người bảo trì biết khi nào cần xem xét lại.

Có thể mô tả kết luận review theo mẫu: “`String.join` vẫn được giữ vì hai phương án có kết quả tương đương, chênh lệch đo không đáng kể đối với input thực tế, và phiên bản này ngắn/dễ đọc hơn”, hoặc “Dùng bộ đệm chung trong vòng lặp vì profiling cho thấy allocation ở đường xử lý nóng giảm đáng kể và load test xác nhận cải thiện”. Đây là **mẫu diễn đạt quyết định**, không phải kết quả đo đã có sẵn của ứng dụng.

## 13. Những ngộ nhận cần tránh

**“StringBuilder luôn nhanh hơn dấu +.”** Không có quy luật tổng quát cho mọi biểu thức, compiler/JVM và workload. `+` trong một biểu thức ngắn thường là lựa chọn hợp lý; ghép dồn bằng `+=` trong vòng lặp dài đáng xem xét.

**“Đo bằng nanoTime một lần đủ để kết luận.”** Một lần chạy chứa warm-up, jitter và tối ưu JIT chưa ổn định. Sử dụng JMH cho microbenchmark, kèm profiling khi xác định nút thắt.

**“Thay String.format bằng nối chuỗi mà không đổi hành vi.”** Locale, precision, dấu nhóm và số chữ số thập phân có thể khác. Cần chứng minh tính tương đương trước khi so nhanh/chậm.

**“Giảm một cấp phát chắc chắn giảm latency.”** JVM có nhiều tối ưu; chi phí cấp phát, GC và phần việc khác thay đổi theo tải. Phải đo metric thực sự cần cải thiện.

**“Đầu vào benchmark càng nhỏ càng đại diện.”** Một chuỗi vài ký tự không phản ánh các xử lý trên dữ liệu hàng nghìn phần tử, Unicode, regex dài hoặc input hỗn hợp.

**“Cách nhanh nhất trên máy phát triển chắc chắn tốt nhất ở production.”** Phần cứng, JDK, profile dữ liệu, tải song song và giới hạn tài nguyên có thể khác nhau.

**“Càng ít dòng mã càng nhanh.”** Độ dài source không phản ánh tổng chi phí thực thi; ngược lại, mã dài hơn cũng không chắc tối ưu hơn. Đọc logic và đo thực tế mới là căn cứ.

**“Đã benchmark thì không cần test đúng/sai.”** Hai cách làm có thể đạt số liệu đẹp vì một bản bỏ bớt việc cần làm. Đảm bảo output, exception, Unicode, locale và các điều kiện biên trước.

## 14. Kết luận áp dụng

Khi xử lý `String` trong Java, hãy chọn **cách đơn giản nhất diễn đạt đúng yêu cầu**: `+` cho một biểu thức ngắn, `String.join` cho danh sách có delimiter, `StringJoiner` khi thêm phần tử từng bước và cần prefix/suffix, `StringBuilder` khi tạo chuỗi có trạng thái hoặc trong vòng lặp, `String.format` khi cần quy tắc định dạng và `Pattern` khi cùng regex phải dùng nhiều lần.

Nếu có nghi ngờ hiệu năng, hãy phát biểu một giả thuyết có thể đo, chuẩn bị đầu vào đại diện, lấy baseline, dùng JMH/profiler đúng phạm vi, kiểm tra lại tính đúng, rồi xác nhận tác động trong ứng dụng. **Tính dễ đọc là một giá trị kỹ thuật; số đo đáng tin mới là cơ sở để đánh đổi nó lấy độ phức tạp tối ưu.**
