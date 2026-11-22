# Chi phí đối tượng, mảng lưu dữ liệu và chuỗi tạm trong Java String

## 1. Mục tiêu bài học

Khi nhìn thấy một biến `String`, ta thường nghĩ đến dãy ký tự mà nó hiển thị. Tuy nhiên, ở thời điểm chạy, một chuỗi còn có **đối tượng Java**, **vùng lưu nội dung**, metadata và những chi phí phát sinh trong quá trình nối, cắt, định dạng hoặc chuyển đổi. Nhiều chương trình chỉ gặp vấn đề khi các chuỗi được tạo với số lượng rất lớn hoặc khi thao tác trong vòng lặp nóng.

Bài này tập trung vào ba câu hỏi thực tế:

1. Một `String` chiếm bộ nhớ vì **đối tượng** và **dữ liệu ký tự** như thế nào?
2. Vì sao nhiều phiên bản JDK hiện đại có thể chứa cùng số ký tự mà tốn bộ nhớ khác nhau, và đâu là ranh giới giữa **API bảo đảm** với **chi tiết triển khai**?
3. Những phép toán nào tạo **chuỗi tạm**, khi nào chúng ảnh hưởng đến GC, và làm sao đo lường rồi tối ưu một cách có kiểm chứng?

Phạm vi minh họa là **Java 17+**, với những ghi chú rõ ràng khi nói về cách HotSpot/OpenJDK lưu trữ `String`. Không nên dùng một con số byte cố định làm “kích thước của mọi String” vì cấu hình JVM, kiến trúc, cách căn chỉnh và phiên bản JDK đều có thể thay đổi kết quả.

## 2. Phân biệt biến tham chiếu, đối tượng String và dữ liệu bên trong

Xét đoạn mã:

```java
String name = "Java";
```

Có ba khái niệm khác nhau:

- **Biến `name`**: chứa một tham chiếu đến đối tượng, không chứa trực tiếp toàn bộ bốn ký tự như một mảng ký tự nằm ngay trong biến.
- **Đối tượng `String`**: một đối tượng trên heap theo mô hình Java thông thường, có phần header và các trường nội bộ cần cho việc quản lý chuỗi.
- **Nội dung chuỗi**: dữ liệu mã hóa các ký tự/code unit, có thể được giữ trong mảng nội bộ hoặc cấu trúc khác tùy bản triển khai.

Trong OpenJDK/HotSpot hiện đại, dữ liệu nội dung của `String` thường nằm trong một mảng `byte[]` riêng. Từ đó, tổng chi phí có thể gồm cả đối tượng `String` lẫn đối tượng mảng lưu dữ liệu; song **tài liệu API `String` không cam kết layout field hay số byte cụ thể**.

Một số khác biệt cần giữ riêng:
- `name.length()` trả **số UTF-16 code unit**, không trả byte bộ nhớ.
- Số Unicode code point có thể khác `length()`, ví dụ emoji nằm ngoài BMP dùng hai UTF-16 code unit.
- `name.getBytes(StandardCharsets.UTF_8).length` trả số byte **của biểu diễn UTF-8 mới tạo**, không phải kích thước bộ nhớ của `String`.
- Các phép đo bộ nhớ heap còn tính overhead đối tượng, căn chỉnh và đôi khi những vùng/đối tượng liên quan có thể được chia sẻ.

Nếu chỉ gọi `length()`, bạn không thể suy ra một cách đáng tin rằng giá trị đó nhân với 2 chính là lượng byte cấp phát cho chuỗi.

## 3. Từ cấu trúc lưu trữ đến footprint của đối tượng

Trong nhiều OpenJDK trước Java 9, `String` giữ nội dung bằng mảng `char[]`. Với **Compact Strings** (JEP 254) từ Java 9, các bản OpenJDK/HotSpot thông dụng có thể lưu `byte[]` cùng `coder`: phần dữ liệu cần khoảng `n` byte khi toàn bộ code unit thuộc Latin-1, hoặc khoảng `2n` byte khi cần dạng UTF16, với `n = text.length()`.

Điểm quan trọng khi phân tích heap là **mảng dữ liệu và đối tượng `String` có overhead riêng**. Trên một JVM cụ thể, footprint còn phụ thuộc object/array headers, references, alignment, chia sẻ bộ đệm và liệu nhiều đối tượng đang giữ cùng dữ liệu. Do đó, con số `n` hay `2n` chỉ mô tả *phần nội dung* theo một chiến lược cài đặt; **không phải total heap cost**.

```text
String reference → String object → backing data (ví dụ byte[])
                       |                     |
                  header/fields         array header + data
```

Để học chính xác điều kiện chọn LATIN1/UTF16 và phân biệt với UTF-8 ngoài heap, xem bài **Compact Strings**. Bài này dùng cấu trúc đó làm nền cho `shallow size`, `retained size`, tốc độ cấp phát và áp lực GC, là những thước đo tác động trực tiếp đến vận hành.

## 4. Shallow size, retained size và heap dump

Ba khái niệm thường được dùng khi phân tích bộ nhớ Java:

| Khái niệm | Ý nghĩa | Với String |
| --- | --- | --- |
| Shallow size | Kích thước bộ nhớ của **chính đối tượng** | Thường chỉ tính đối tượng `String` và field/header của nó, chưa tính mảng được tham chiếu |
| Retained size | Phần bộ nhớ có thể được giải phóng nếu đối tượng không còn reachable, theo quan hệ giữ tham chiếu | Có thể gồm mảng dữ liệu do `String` giữ riêng, nhưng không nên cộng nhầm đối tượng đang được chia sẻ |
| Allocation rate | Tốc độ JVM tạo đối tượng/byte mới theo thời gian | Cho thấy tác động của các chuỗi trung gian dù chúng sống rất ngắn |

Ví dụ, một `String` mới chỉ được dùng để tạo log rồi bị bỏ ngay có thể không làm **live heap** tăng lâu dài, nhưng vẫn làm **allocation rate** tăng. Ngược lại, một cache giữ hàng triệu chuỗi nhỏ lâu dài có thể tăng retained heap, kéo dài thời gian GC hoặc làm thiếu bộ nhớ.

Các phép đo kích thước cũng phụ thuộc:
- Kiểu JVM, bitness, nén ordinary object pointers (Compressed Oops) và compressed class pointers.
- Alignment của đối tượng và header.
- Hình thức lưu trữ nội bộ ở phiên bản JDK cụ thể.
- Chuỗi có cùng tham chiếu, chuỗi khác đối tượng cùng nội dung, hay có phần dữ liệu được chia sẻ.
- GC và những tối ưu của runtime.

**Không cộng shallow size của một `String` với toàn bộ mảng chung cho từng đường tham chiếu**, nếu nhiều đối tượng chia sẻ cùng một phần dữ liệu: cách này dẫn tới đếm trùng.

## 5. Chuỗi bất biến: vì sao thao tác có thể tạo đối tượng mới?

`String` là immutable: sau khi tạo, nội dung của đối tượng không bị thay đổi bởi các phương thức `String` thông thường. Vì thế những thao tác **thay nội dung** thường trả một đối tượng `String` mới, ví dụ khi nội dung thực sự cần chỉnh.

```java
String value = "Java";
String result = value.concat(" 17");

System.out.println(value);  // Java
System.out.println(result); // Java 17
```

Các phương thức như `replace`, `toUpperCase`, `substring`, `strip` hoặc `repeat` có thể tạo biểu diễn chuỗi mới khi kết quả khác nguồn. Tuy nhiên **không được khẳng định mọi lời gọi luôn cấp phát đối tượng mới**: một số trường hợp không cần thay đổi có thể trả về chính chuỗi cũ, và JIT có thể loại bỏ cấp phát trung gian nếu chứng minh được.

Ví dụ:

```java
String source = "abcdef";
String cut = source.substring(1, 4); // "bcd"
```

Trong OpenJDK hiện đại, `substring` thường cần biểu diễn nội dung mới cho phần được cắt. Lịch sử JDK đã từng có cơ chế chia sẻ mảng nền giữa substring và chuỗi gốc; không áp dụng nguyên mẫu kinh nghiệm đó cho Java 17. Với ứng dụng, điều nên dựa vào là **hợp đồng API về nội dung trả về**, không dựa vào field nội bộ hoặc kỳ vọng danh tính đối tượng.

Ngay cả khi một thao tác tạo chuỗi tạm, GC sẽ thu hồi nó khi không còn reachable; vấn đề hiệu năng phụ thuộc **tần suất tạo**, kích thước, thời gian sống và khả năng tối ưu của JVM.

## 6. Pool, bản sao chuỗi và số lượng đối tượng

Hai literal cùng nội dung có cùng tham chiếu canonical, còn `new String(existing)` tạo một đối tượng `String` riêng, dù dữ liệu ký tự có thể được chia sẻ theo cài đặt:

```java
String canonical = "Java";
String sameLiteral = "Java";
String fresh = new String("Java");

System.out.println(canonical == sameLiteral); // true
System.out.println(canonical == fresh);       // false
System.out.println(canonical.equals(fresh));  // true
```

Về **footprint**, cần tách số **đối tượng `String`** khỏi số **mảng lưu nội dung**. `intern()` trả về đối tượng canonical; tối ưu *String deduplication* của một số GC có thể chia sẻ dữ liệu giữa những đối tượng vẫn khác tham chiếu. Hai cơ chế có chi phí, điều kiện áp dụng và ảnh hưởng đến vòng đời dữ liệu riêng; không nên intern tất cả ID ngẫu nhiên hay giả định dedup luôn bật.

Bài **Constant pool và Constable/ConstantDesc** giải thích hợp đồng interning; bài về **khác biệt giữa các JDK** trình bày lịch sử intern và dedup. Khi mục tiêu là tiết kiệm heap, hãy đo retained memory, số lượng bản sao thực và allocation rate thay vì đếm `new String` bằng mắt.

## 7. Những nguồn tạo chuỗi tạm phổ biến

### 7.1. Nối chuỗi bằng toán tử +

```java
String id = "42";
String message = "order-" + id + "-ready";
```

Về mặt ngôn ngữ, phép `+` tạo kết quả ghép chuỗi. Tuy nhiên **đừng giả định** ví dụ này tạo chính xác ba đối tượng `String` trung gian. Từ Java 9, trình biên dịch/runtime có thể sử dụng cơ chế nối dựa trên `invokedynamic` (JEP 280); JIT và constant folding còn có thể làm giảm cấp phát.

Một biểu thức chỉ chứa hằng số:

```java
String label = "Java" + " " + "17";
```

có thể được **gộp thành hằng số lúc biên dịch**. Vì vậy, đo benchmark cho chuỗi literal hằng không đại diện cho vòng lặp nối dữ liệu động.

### 7.2. Nối lặp từng bước

Cần cẩn trọng với cách viết sau, khi `part` biến đổi theo lượt lặp:

```java
String output = "";
for (String part : parts) {
    output += part;
}
```

Mỗi lượt về mặt ngữ nghĩa phải tạo kết quả ghép mới vì `String` immutable. Runtime có thể tối ưu một phần, nhưng kiểu tích lũy này thường tăng công việc sao chép nội dung lặp đi lặp lại, nhất là với chuỗi kết quả tăng dần.

Giải pháp có mục đích rõ hơn:

```java
StringBuilder builder = new StringBuilder();
for (String part : parts) {
    builder.append(part);
}
String output = builder.toString();
```

`StringBuilder` lưu trạng thái có thể thay đổi trong một bộ đệm và phát triển vùng chứa khi cần; việc `append` không yêu cầu tạo một `String` bất biến trung gian cho mỗi lượt. Cần nhớ bản thân `StringBuilder` và buffer của nó **cũng là đối tượng có chi phí**, và `toString()` tạo kết quả bất biến.

### 7.3. Chuyển kiểu và định dạng

Các thao tác như:

```java
String a = String.valueOf(12345);
String b = String.format(java.util.Locale.US, "%.2f", 12.5);
String c = "prefix" + java.util.UUID.randomUUID();
```

có thể dẫn tới cấp phát chuỗi, đối tượng hỗ trợ hoặc buffer nội bộ. `String.format` thường có xử lý định dạng phong phú hơn, phù hợp khi cần width/precision/locale; không nên thay bằng nối thô nếu làm mất yêu cầu định dạng chỉ vì muốn giảm cấp phát.

Với số lượng lời gọi lớn trong đường đi nóng, hãy đo sự khác biệt giữa `StringBuilder`, nối chuỗi `+` và formatter **trên dữ liệu và môi trường thực**, không suy luận thuần túy từ cú pháp.

### 7.4. split, replace, substring, strip và stream

Các pipeline có thể tạo thêm đối tượng hoặc mảng trung gian:

```java
String input = " red , blue , green ";
String[] tokens = input.split(",");
String first = tokens[0].strip();
String upper = first.toUpperCase(java.util.Locale.ROOT);
```

Có thể có mảng chứa phần tử, các `String` token, `String` sau chuẩn hóa và một số cấu trúc phục vụ thuật toán. Số lượng thực tế phụ thuộc đầu vào, phiên bản JDK và tối ưu. Không giả định `split` chỉ tạo một mảng mà không có chuỗi thành phần.

Nếu chỉ cần tìm một delimiter đơn và xử lý một phần nhỏ của văn bản, `indexOf`, `substring` hoặc một parser dựa trên chỉ số có thể tránh một số đối tượng. Nhưng parser tự viết cần kiểm thử các trường hợp biên và có thể làm mã khó duy trì. Chỉ tối ưu khi profiler chứng minh vị trí này đáng kể.

## 8. StringBuilder: quản lý buffer và capacity

`StringBuilder` là lớp mutable để xây dựng chuỗi theo từng phần. Hai khái niệm khác nhau:

- `length()`: số UTF-16 code unit **đang sử dụng**.
- `capacity()`: số UTF-16 code unit bộ đệm **có thể chứa trước khi cần mở rộng** theo đặc tả API.

```java
StringBuilder builder = new StringBuilder(128);
builder.append("id=").append(42);

System.out.println(builder.length()); // 5
System.out.println(builder.capacity() >= 128); // true
```

Khởi tạo capacity đủ lớn có thể giảm số lần mở rộng buffer cho một kết quả dự đoán được kích thước. Nhưng `capacity()` **không phải số byte heap**. Trong OpenJDK Java 17, vùng chứa của `StringBuilder` cũng có chi tiết triển khai tối ưu ký tự, nên lấy capacity nhân với 2 để suy ra byte sử dụng là cách tính không đáng tin.

Lạm dụng preallocation cũng có hại:

```java
StringBuilder huge = new StringBuilder(1_000_000);
huge.append("OK");
```

Đoạn trên yêu cầu bộ đệm ban đầu rất lớn dù dữ liệu chỉ có hai ký tự; nếu lặp lại nhiều lần, bộ nhớ và áp lực GC có thể tăng. Chỉ ước lượng capacity khi có cơ sở từ đặc điểm dữ liệu hoặc kết quả đo.

Sau khi `toString()` trả chuỗi kết quả, `StringBuilder` vẫn có thể bị thay đổi nhưng **chuỗi đã nhận không đổi**:

```java
StringBuilder builder = new StringBuilder("item=");
builder.append(42);
String snapshot = builder.toString();

builder.append("!");
System.out.println(snapshot); // item=42
System.out.println(builder);  // item=42!
```

`StringBuffer` tương tự về mục đích xây dựng chuỗi nhưng có các thao tác đồng bộ hóa; không tự động chọn nó cho code một luồng chỉ vì nghĩ rằng vùng lưu bộ nhớ nhỏ hơn.

## 9. Ví dụ chạy được với Java 17+

Tạo tệp `StringMemoryDemo.java`, lưu UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;

public class StringMemoryDemo {
    public static void main(String[] args) {
        String first = "alpha";
        String sameLiteral = "alpha";
        String freshObject = new String("alpha");

        System.out.println("same literal reference: "
                + (first == sameLiteral));
        System.out.println("fresh object reference: "
                + (first == freshObject));
        System.out.println("same text: "
                + first.equals(freshObject));

        String source = "abcdefgh";
        String part = source.substring(2, 5);
        System.out.println("substring: " + part);

        StringBuilder builder = new StringBuilder(32);
        builder.append("item=").append(42);
        String snapshot = builder.toString();
        builder.append("!");
        System.out.println("snapshot: " + snapshot);
        System.out.println("builder: " + builder);

        String ascii = "ABC";
        String emoji = new String(Character.toChars(0x1F600));
        System.out.println("ASCII length: " + ascii.length());
        System.out.println("emoji UTF-16 units: " + emoji.length());
        System.out.println("emoji code points: "
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("ASCII UTF-8 bytes: "
                + ascii.getBytes(StandardCharsets.UTF_8).length);

        List<String> parts = List.of("A", "B", "C");
        String joined = String.join("-", parts);
        System.out.println("joined: " + joined);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StringMemoryDemo.java
java StringMemoryDemo
```

Stdout chuẩn:

```text
same literal reference: true
fresh object reference: false
same text: true
substring: cde
snapshot: item=42
builder: item=42!
ASCII length: 3
emoji UTF-16 units: 2
emoji code points: 1
ASCII UTF-8 bytes: 3
joined: A-B-C
```

Ví dụ này **kiểm chứng ngữ nghĩa Java**, không đo trực tiếp số byte của mỗi `String`. Biểu thức `getBytes(UTF_8)` tạo một biểu diễn UTF-8 để đếm kích thước đầu ra; không dùng nó như công cụ đọc mảng nội bộ. Việc `new String("alpha")` cho tham chiếu khác là hành vi quan sát được theo API, nhưng không suy ra cần sao chép cùng một lượng byte dữ liệu ký tự bên dưới.

## 10. Tối ưu số lượng chuỗi và đối tượng tạm

### 10.1. Chọn đúng công cụ nối chuỗi

| Tình huống | Cách làm thường phù hợp | Ghi chú |
| --- | --- | --- |
| Ghép vài trường trong một biểu thức | `"id=" + id + ", status=" + status` | Cú pháp dễ đọc; JDK hiện đại tối ưu nối biểu thức |
| Tích lũy nhiều phần trong vòng lặp | `StringBuilder` + `append` | Giữ một buffer phát triển, giảm nhu cầu tạo kết quả bất biến mỗi vòng |
| Ghép collection với delimiter | `String.join(delimiter, values)` | Tránh tự xử lý delimiter đầu/cuối |
| Ghép nhiều chuỗi trong Stream | `Collectors.joining(delimiter)` | Gọn khi đã có pipeline Stream |
| Căn lề, số chữ số, locale | `String.format`, `Formatter` | Chọn vì đúng định dạng; đo nếu chạy với tần suất rất cao |
| Duyệt/parse đoạn nhỏ | `indexOf` và xử lý chỉ số nếu phù hợp | Có thể giảm mảng/token tạm; đánh đổi độ phức tạp mã |

Tối ưu phù hợp nhất thường là **tránh công việc thừa**: không lặp lại format một thông báo mà người dùng không xem, không gọi `split` khi chỉ cần kiểm tra một tiền tố, và không tạo cùng một chuỗi chuyển đổi trong từng lượt nếu giá trị thực sự không đổi.

### 10.2. Không tạo output khi không sử dụng

Ví dụ một đoạn log có điều kiện:

```java
// Chỉ minh họa cấu trúc điều kiện; logEnabled/log là API của ứng dụng.
if (logEnabled) {
    String message = "Tổng=" + total + ", mã=" + code;
    log(message);
}
```

Bằng cách kiểm tra điều kiện trước, ta tránh phải xây dựng thông báo trong nhánh không dùng tới. Với framework logging, hãy dùng các cơ chế placeholder/lazy logging mà framework cung cấp khi phù hợp; `String.format` trước khi gọi logger có thể vẫn làm công việc dù log bị vô hiệu hóa.

### 10.3. Tái sử dụng dữ liệu không đồng nghĩa intern tất cả

Nếu cùng một bộ từ khóa/nhãn cố định xuất hiện rất nhiều lần, tái sử dụng đối tượng có thể hữu ích. Nhưng `intern()` mọi ID, URL hoặc giá trị ngẫu nhiên không có tỷ lệ lặp cao có thể gây overhead. Khi cần cache, xác định rõ phạm vi sống và giới hạn kích thước; nếu không, tiết kiệm cấp phát ngắn hạn có thể biến thành tăng retained heap dài hạn.

### 10.4. StringBuilder dùng lại có giới hạn

Có thể tái sử dụng `StringBuilder` trong một luồng xử lý có kiểm soát, gọi `setLength(0)` để làm trống. Nhưng **capacity lớn vẫn được giữ** sau khi reset, nên một request bất thường có thể khiến buffer chiếm chỗ quá lâu. Ngoài ra `StringBuilder` không thread-safe; không chia sẻ builder mutable giữa nhiều luồng nếu không có đồng bộ thích hợp. Tránh giữ builder khổng lồ trong `ThreadLocal` hoặc cache vô hạn.

## 11. Đo lường thay vì dự đoán số đối tượng

### 11.1. Những câu hỏi cần profiler trả lời

Khi nhận thấy GC hoạt động nhiều, độ trễ tăng hoặc heap cao, tìm:
- Loại đối tượng nào được **cấp phát nhiều nhất**, đặc biệt `String`, `byte[]` và các mảng liên quan?
- Call path nào tạo chúng? Có phải vòng lặp nối chuỗi, format, parse hay chuyển đổi không?
- Đó là **allocation rate** cao của đối tượng sống ngắn, hay **retained heap** cao do cache và tham chiếu lâu dài?
- Có nhiều chuỗi cùng nội dung được giữ lại không? Chúng có thật sự gây ảnh hưởng đáng kể đến ứng dụng?
- Sau khi sửa, throughput, latency, số lượng cấp phát và GC có cải thiện trên dữ liệu điển hình hay không?

Công cụ hữu ích có thể gồm **Java Flight Recorder (JFR)**, **Java Mission Control (JMC)**, **VisualVM**, **Eclipse Memory Analyzer (MAT)** và profiler phù hợp môi trường. JFR có các sự kiện/cách lấy mẫu allocation; heap dump cho phép xem retained heap và đường giữ tham chiếu. Kết quả phụ thuộc cấu hình ghi và công cụ, nên cần đọc đúng định nghĩa metric.

### 11.2. Quan sát allocation với JFR

Một ví dụ trên JDK có công cụ `jfr`:

```bash
java -XX:StartFlightRecording=filename=string-profile.jfr,settings=profile \
     -jar application.jar
```

Lệnh mang tính **minh họa** cho ứng dụng thực tế `application.jar`; phần xuống dòng ở ví dụ shell chỉ dùng được trong môi trường cho phép escape tương ứng, còn trên Windows PowerShell có thể viết lệnh cùng một dòng. Có thể xem file `.jfr` bằng JMC hoặc công cụ `jfr` phù hợp. Việc record có đúng sự kiện allocation mong muốn hay không phụ thuộc profile và cấu hình JFR.

Nếu cần số liệu đáng tin cho một thao tác nhỏ, tránh tự so sánh `Runtime.totalMemory() - freeMemory()` trước/sau **một lời gọi**. GC, JIT, escape analysis, cấp phát của framework và các luồng khác khiến kết quả rất nhiễu.

### 11.3. Benchmark có kiểm soát

Với phép nối/định dạng ở hot path, nên dùng **JMH** thay cho vòng lặp bấm giờ tự viết. Khi benchmark:
1. Đặt rõ giả thuyết: giảm allocation/op, tăng throughput, hay giảm độ trễ?
2. Dùng **đầu vào biến thiên có kiểm soát** để tránh hằng số hóa toàn bộ phép toán.
3. Warm-up để JVM tối ưu trước khi đo, chạy nhiều vòng/fork phù hợp.
4. Tiêu thụ kết quả để tránh dead-code elimination (JMH cung cấp cơ chế phù hợp).
5. Đo cả số byte cấp phát trên operation nếu mục tiêu là bộ nhớ, và xem tác động GC ở mức ứng dụng.

Một benchmark micro có thể chứng minh một thao tác cụ thể nhanh hơn trong cấu hình đo, nhưng không đủ để khẳng định mọi chương trình nên thay `+` bằng `StringBuilder`.

## 12. Cấu hình JVM và tối ưu hóa liên quan

### Compact Strings

OpenJDK/HotSpot Java 17 thông thường bật Compact Strings theo mặc định. Một số JVM cho phép điều khiển qua cờ triển khai như `-XX:-CompactStrings`; đây là tùy chọn **phụ thuộc VM**, không phải cú pháp Java chuẩn hay khuyến nghị tối ưu mặc định. Thay đổi cờ có thể làm tăng footprint hoặc thay đổi hiệu năng; chỉ dùng cho nghiên cứu/benchmark có kiểm soát.

### String deduplication

Một số garbage collector, điển hình các cấu hình G1, hỗ trợ **String deduplication** qua cơ chế/cờ JVM như `-XX:+UseStringDeduplication` trên những bản phát hành tương ứng. Ý tưởng là chia sẻ mảng lưu nội dung giữa các đối tượng `String` có nội dung giống nhau, trong khi **đối tượng String vẫn khác nhau**. Tối ưu này không giúp mọi chương trình và có overhead rà soát/hash; cần kiểm tra GC/JDK đang chạy và đo bằng công cụ trước khi bật.

### JIT và escape analysis

HotSpot có thể tối ưu một số phép nối chuỗi, nội tuyến phương thức và thậm chí loại bỏ những cấp phát không “thoát” khỏi phạm vi tính toán quan sát được. Vì vậy:
- Nguồn Java có từ `new` hoặc phép tạo chuỗi không đồng nghĩa runtime chắc chắn cấp phát riêng đối tượng ở heap trong mọi lần chạy.
- Benchmark quá đơn giản có thể cho kết quả bất thường vì JIT đã hằng số hóa hoặc loại bỏ phần công việc.
- Không nên thay đổi code chỉ dựa trên số đối tượng **suy luận** từ đoạn mã; phải kết hợp profiler với hiểu biết về runtime.

Các cờ và chi tiết thuật toán JVM có thể khác theo JDK, GC và vendor; chú ý phiên bản trước khi sao chép hướng dẫn tuning.

## 13. Những hiểu lầm và lỗi thường gặp

**1. “String dài N ký tự luôn chiếm 2N byte.”** Sai nếu dùng như phép tính tổng footprint. `N = length()` là code unit UTF-16; có overhead và Compact Strings. Dữ liệu trên heap không đồng nhất với byte UTF-8.

**2. “Unicode/emoji luôn có length bằng 1.”** Không đúng với code point ngoài BMP: một emoji có thể chiếm hai UTF-16 code unit, nên `length()` có thể là 2. Nếu cần đếm code point, dùng `codePointCount(...)`, đồng thời nhớ code point chưa chắc tương ứng một *grapheme cluster* hiển thị.

**3. “Mỗi dấu + luôn tạo thêm một String trung gian.”** Kết quả biểu thức là chuỗi, nhưng compiler/JIT có thể hằng số hóa, gộp công việc và giảm cấp phát. Vấn đề thực tế là nối tích lũy trong vòng lặp và tốc độ phân bổ đã đo.

**4. “StringBuilder không tốn bộ nhớ.”** Sai. Nó là đối tượng có buffer; mở rộng buffer hoặc cấp trước quá lớn đều có chi phí. `toString()` tạo kết quả bất biến theo API.

**5. “Substring Java 17 luôn giữ nguyên cả mảng lớn gốc.”** Đây là kinh nghiệm từ một số JDK cũ có layout khác; đừng dùng nó để kết luận cho Java 17. Phải đo heap của JVM thực tế nếu cần biết khả năng chia sẻ dữ liệu.

**6. “intern và String deduplication là một.”** `intern` canonical hóa tham chiếu String, còn deduplication (khi hỗ trợ) hướng tới chia sẻ bộ đệm của các String khác đối tượng.

**7. “Heap ít chuỗi đang sống nên không thể có vấn đề String.”** Một hệ thống có thể có live heap thấp nhưng allocation rate cao, dẫn đến GC nhiều và giảm throughput.

**8. “getBytes(UTF_8).length là kích thước String trên heap.”** Đây là byte của biểu diễn mã hóa được xuất ra, không gồm overhead object và cũng không phản ánh chắc chắn cách JVM lưu bên trong.

**9. “Cứ thêm cache sẽ tiết kiệm bộ nhớ.”** Cache có thể tăng retained heap và kéo dài vòng đời đối tượng. Chỉ cache giá trị dùng lại đủ nhiều, có giới hạn phù hợp.

**10. “Benchmark nối chuỗi trên một hằng số đủ để chọn tối ưu.”** Constant folding và tối ưu JIT có thể làm kết quả mất tính đại diện; cần JMH và profile ứng dụng thực.

## 14. Bài tập tự luyện

### Bài 1. Phân biệt length và UTF-8

```java
String ascii = "ABC";
String emoji = new String(Character.toChars(0x1F600));
```

Hỏi: `ascii.length()`, `emoji.length()` và `emoji.codePointCount(0, emoji.length())` bằng bao nhiêu? Có thể lấy các số đó nhân 2 để suy ra heap bytes không?

**Đáp án:** Lần lượt là **3**, **2**, **1**. Không thể suy ra heap bytes vì chúng là các phép đếm nội dung; heap còn phụ thuộc storage representation, overhead và JVM.

### Bài 2. Về danh tính đối tượng

```java
String x = "value";
String y = "value";
String z = new String("value");
```

Hỏi: `x == y`, `x == z`, `x.equals(z)`?

**Đáp án:** `true`, `false`, `true`. Hai literal dùng cùng chuỗi canonical; `new String(...)` tạo đối tượng riêng nhưng nội dung bằng nhau.

### Bài 3. Thay vòng lặp nối nhiều phần

Từ danh sách `parts` có kiểu `List<String>`, chuyển đoạn:

```java
String result = "";
for (String part : parts) {
    result += part;
}
```

thành cách xây chuỗi có một buffer mutable:

```java
StringBuilder builder = new StringBuilder();
for (String part : parts) {
    builder.append(part);
}
String result = builder.toString();
```

Giải thích: mã sau tránh nhu cầu tạo một kết quả `String` bất biến mới trên mỗi vòng xét theo cấu trúc thuật toán; chi phí thực tế vẫn cần profiler xác nhận.

### Bài 4. Kiểm tra chi phí của một pipeline

```java
String[] values = input.split(",");
String joined = String.join("|", values);
```

Hỏi: có thể chắc chắn chỉ cấp phát đúng hai đối tượng (một mảng và một chuỗi) không?

**Đáp án:** Không. Có thể có các token `String`, mảng và đối tượng nội bộ khác; số allocation thực tế còn chịu tối ưu JVM. Đo profiler nếu đây là hot path.

### Bài 5. Xác định phép đo đúng

Một dịch vụ tạo hàng triệu chuỗi tạm mỗi giây nhưng retained heap không tăng rõ ràng. Nên xem **shallow size** của một `String` hay **allocation rate, GC activity và call path**?

**Đáp án:** Ưu tiên allocation rate, GC và call path để tìm nơi tạo đối tượng ngắn hạn. Shallow size của một đối tượng đơn lẻ không phản ánh áp lực cấp phát theo thời gian.

## 15. Ghi nhớ

- **`String` có nhiều tầng chi phí:** đối tượng, dữ liệu nội bộ, overhead mảng, căn chỉnh và vòng đời tham chiếu; `length()` không phải kích thước heap.
- **Compact Strings** trong OpenJDK/HotSpot Java 9+ thường dùng `byte[]` với Latin-1 hoặc UTF-16 để giảm phần dữ liệu; đó là **chi tiết triển khai**.
- **Chuỗi immutable:** thao tác tạo nội dung mới có thể dẫn tới cấp phát `String` và mảng mới; compiler/JIT có thể tối ưu một phần, không được đếm đối tượng chỉ từ cú pháp.
- **Literal/intern** và **string deduplication** là hai kỹ thuật khác nhau, với tác động khác nhau lên tham chiếu và dữ liệu.
- **Nối trong vòng lặp:** cân nhắc `StringBuilder`; nối vài giá trị một biểu thức bằng `+` thường phù hợp và dễ đọc.
- **Tối ưu đúng mục tiêu:** phân biệt lượng heap còn sống với tốc độ cấp phát đối tượng tạm; đo bằng profiler, JFR, heap dump và JMH phù hợp.
- **Không tối ưu mù:** cấu hình VM, GC, bộ nhớ và thời gian chạy phải được kiểm tra trên workload thực.

Tài liệu tham khảo:
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
- [OpenJDK JEP 254 — Compact Strings](https://openjdk.org/jeps/254)
- [OpenJDK JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280)
- [OpenJDK JEP 192 — String Deduplication in G1](https://openjdk.org/jeps/192)
