# Chuyển từ StringBuffer sang String trong Java

## 1. Mục tiêu học tập

`StringBuffer` là lớp dùng để **xây dựng và chỉnh sửa** chuỗi ký tự qua nhiều thao tác như `append()`, `insert()`, `delete()`, `replace()`. Nội dung bên trong `StringBuffer` có thể thay đổi (*mutable*). Ngược lại, `String` là kiểu chuỗi **bất biến** (*immutable*): một đối tượng `String` đã được tạo không bị thay đổi nội dung.

Khi hoàn thành việc xây dựng văn bản, ta thường cần lấy kết quả dưới dạng `String`, chẳng hạn để truyền cho một API yêu cầu `String`, lưu một bản kết quả ổn định hoặc so sánh và xử lý bằng các phương thức của `String`.

Cách trực tiếp nhất là:

~~~java
StringBuffer buffer = new StringBuffer("Java");
buffer.append(" Core");

String result = buffer.toString();
System.out.println(result); // Java Core
~~~

Sau bài học, bạn cần có khả năng:

1. Phân biệt `StringBuffer` mutable với `String` immutable.
2. Chuyển `StringBuffer` sang `String` bằng `toString()`, constructor `new String(buffer)` và hiểu khi nào nên dùng `String.valueOf(buffer)`.
3. Giải thích vì sao `String` kết quả là **bản chụp nội dung** (*snapshot*) không thay đổi khi buffer tiếp tục bị sửa.
4. Nhận biết chuyển đổi không xóa, không đặt lại độ dài, không vô hiệu hóa buffer và không tự động chuyển mọi tham chiếu khác sang `String`.
5. Xử lý `null`, buffer rỗng, Unicode, định dạng đầu ra và API nhận `CharSequence`.
6. Biết giới hạn của các phương thức đồng bộ của `StringBuffer` khi có nhiều luồng.
7. Xác minh bằng ví dụ Java 17+ có thể biên dịch và chạy độc lập.

Kiến thức cần có: đối tượng/tham chiếu, phương thức, `String`, `StringBuffer`, tính bất biến và phép gán.

## 2. Cách chính: gọi StringBuffer.toString()

Cú pháp:

~~~java
StringBuffer buffer = new StringBuffer();
buffer.append("Hello");
buffer.append(" ");
buffer.append("World");

String text = buffer.toString();
~~~

`buffer.toString()` trả về một đối tượng `String` biểu diễn **nội dung ký tự hiện tại** của buffer. Đây là cách thông dụng, rõ ràng và dễ đọc nhất.

| Thuộc tính | `StringBuffer` | `String` kết quả |
| --- | --- | --- |
| Có thể sửa nội dung qua API? | Có: `append`, `delete`, `setCharAt`… | Không |
| Có thể tiếp tục bổ sung ký tự? | Có | Phải tạo kết quả `String` khác hoặc dùng builder/buffer |
| Độ dài hiện tại | `buffer.length()` | `text.length()` |
| Đổi sang loại bên kia | `buffer.toString()` | `new StringBuffer(text)` |
| Giá trị khi buffer bị sửa sau đó | Thay đổi theo phép sửa | **Giữ nguyên nội dung đã lấy** |

Điểm mấu chốt: `toString()` **không sửa buffer** và không thay đổi kiểu của biến `buffer`. Biến `buffer` vẫn tham chiếu đến cùng một đối tượng `StringBuffer` mutable sau lời gọi.

### Minh họa dòng dữ liệu

~~~text
StringBuffer buffer: "Java"
        │
        ├─ append(" Core")
        ▼
StringBuffer buffer: "Java Core"
        │
        ├─ toString()
        ▼
String text: "Java Core"   (bất biến)

Sau đó buffer.append(" 17"):

buffer = "Java Core 17"
text   = "Java Core"      (không đổi)
~~~

Đừng hình dung `toString()` như một phép "chuyển loại tại chỗ". Hai biến có **kiểu tĩnh khác nhau** và lưu các tham chiếu độc lập theo ý nghĩa dữ liệu.

## 3. Snapshot: String không thay đổi khi buffer bị sửa tiếp

~~~java
StringBuffer buffer = new StringBuffer("AB");
String snapshot = buffer.toString();

buffer.append("C");
buffer.setCharAt(0, 'X');

System.out.println(buffer);   // XBC
System.out.println(snapshot); // AB
~~~

`snapshot` nắm giữ giá trị `"AB"` tại thời điểm chuyển đổi. Thao tác `append("C")` hay `setCharAt(0, 'X')` thay đổi buffer, **không thay đổi** một đối tượng `String` đã tồn tại.

Nếu muốn cập nhật biến `snapshot` theo nội dung buffer mới, phải **gọi lại `toString()` rồi gán lại**:

~~~java
StringBuffer buffer = new StringBuffer("A");
String snapshot = buffer.toString(); // A

buffer.append("B");
snapshot = buffer.toString();        // AB

System.out.println(snapshot);       // AB
~~~

Phép `snapshot = ...` chỉ gán lại **tham chiếu biến**; nó không làm cho `String` trở nên mutable.

### Không có liên kết sống giữa hai đối tượng

~~~java
StringBuffer buffer = new StringBuffer("first");
String first = buffer.toString();

buffer.setLength(0);
buffer.append("second");
String second = buffer.toString();

System.out.println(first);  // first
System.out.println(second); // second
System.out.println(buffer); // second
~~~

`setLength(0)` xóa nội dung **đang lưu trong buffer** bằng cách giảm độ dài logic xuống 0; nó không xóa hay thay đổi `first`. Buffer vẫn được tái sử dụng.

Không nên khẳng định mỗi lần gọi `toString()` **luôn cấp phát một đối tượng String mới**. Một triển khai Java có thể dùng bộ đệm hoặc tối ưu nội bộ. Điều được API bảo đảm cho việc học này là **giá trị `String` đã trả về không bị sửa bởi những thao tác tiếp theo trên buffer**.

## 4. Các cách chuyển đổi và nên chọn cách nào?

### 4.1. Cách khuyến nghị: buffer.toString()

~~~java
StringBuffer buffer = new StringBuffer("Java");
String result = buffer.toString();
~~~

Ưu điểm: diễn đạt đúng mục đích, không cần thêm công cụ, dễ nhận ra đang lấy giá trị chuỗi từ buffer. **Đây là cách mặc định nên sử dụng** khi `buffer` khác `null`.

### 4.2. Constructor: new String(buffer)

Java cũng hỗ trợ constructor nhận `StringBuffer`:

~~~java
StringBuffer buffer = new StringBuffer("Java");
String result = new String(buffer);
~~~

Kết quả là `String` có cùng nội dung như buffer tại thời điểm tạo. Đối với nhu cầu thông thường, nó không mang lại lợi ích diễn đạt rõ ràng hơn `buffer.toString()`. Khi muốn lấy kết quả từ buffer, đa số code nên dùng `toString()`.

Chú ý đây là **`new String(StringBuffer)`**, không phải constructor nhận một kiểu byte/char bất kỳ. Nếu chỉ muốn tạo chuỗi từ `char[]`, dùng `new String(chars)` là hợp đồng khác.

### 4.3. String.valueOf(buffer)

~~~java
StringBuffer buffer = new StringBuffer("Java");
String result = String.valueOf(buffer);
~~~

`String.valueOf(Object)` dùng biểu diễn `toString()` của đối tượng khác `null`; khi đối số là `null` nó trả về **chuỗi ký tự `"null"`**. Vì `StringBuffer` không có overload `valueOf` đặc biệt, lời gọi với một biến kiểu `StringBuffer` dùng overload dành cho `Object`.

~~~java
StringBuffer missing = null;

System.out.println(String.valueOf(missing)); // null
// missing.toString();       // NullPointerException
// new String(missing);      // NullPointerException
~~~

Cần phân biệt một đối tượng chuỗi có nội dung bốn ký tự `"null"` với trạng thái thiếu dữ liệu thật sự. **Không dùng `String.valueOf(buffer)` như chính sách xử lý `null` mặc định** nếu nghiệp vụ muốn từ chối, trả `null` hoặc dùng chuỗi rỗng.

### 4.4. Nếu muốn trả null thay vì chuỗi "null"

~~~java
static String snapshotOrNull(StringBuffer buffer) {
    return buffer == null ? null : buffer.toString();
}
~~~

Hoặc nếu `null` là lỗi lập trình cần phát hiện:

~~~java
static String snapshotRequired(StringBuffer buffer) {
    java.util.Objects.requireNonNull(buffer, "buffer");
    return buffer.toString();
}
~~~

Cả hai là **đoạn phương thức minh họa**, không phải chương trình độc lập nếu đứng một mình. Quy tắc trả `null` hay ném ngoại lệ phải được thống nhất với người dùng API.

## 5. Dùng String sau chuyển đổi

Một lý do phổ biến là thư viện hoặc phương thức nghiệp vụ cần đúng kiểu `String`:

~~~java
static void saveMessage(String message) {
    System.out.println("Saved: " + message);
}

// Gọi trong một phương thức:
StringBuffer buffer = new StringBuffer();
buffer.append("Order ");
buffer.append(42);

saveMessage(buffer.toString());
~~~

Đây là **fragment minh họa**: đặt các câu lệnh vào phương thức như `main`, và `saveMessage` vào thân một lớp để biên dịch. `StringBuffer` không tự động tương thích với mọi tham số kiểu `String`.

### Nên kiểm tra kiểu tham số trước khi chuyển đổi

Một số API chấp nhận `CharSequence`, giao diện mà cả `String` và `StringBuffer` đều triển khai:

~~~java
static int textLength(CharSequence text) {
    return text.length();
}
~~~

Nếu chỉ cần đọc độ dài hoặc truy cập theo `CharSequence`, có thể truyền buffer **không cần tạo String trung gian**:

~~~java
StringBuffer buffer = new StringBuffer("ABC");
System.out.println(textLength(buffer));            // 3
System.out.println(textLength(buffer.toString())); // 3
~~~

Nhưng `CharSequence` không bảo đảm nội dung bất biến; nếu API lưu tham chiếu để dùng về sau, chuyển sang `String` có thể cần thiết để giữ một bản **ổn định**.

### Khi chỉ cần in nội dung buffer

~~~java
StringBuffer buffer = new StringBuffer("Hello");

System.out.println(buffer);            // Hello
System.out.println(buffer.toString()); // Hello
~~~

`println(Object)` sử dụng biểu diễn văn bản của đối tượng. Không nhất thiết phải tạo một biến `String` riêng chỉ để in; nhưng nếu thật sự cần giữ kết quả hoặc truyền cho nơi chỉ nhận `String`, hãy gọi `toString()`.

## 6. Tạo String ở thời điểm nào?

Trong một pipeline xây văn bản, nên lấy `String` **khi đã hoàn thiện nội dung mong muốn**:

~~~java
StringBuffer buffer = new StringBuffer();
buffer.append("Name: ");
buffer.append("Lan");
buffer.append("\n");
buffer.append("City: ");
buffer.append("Hanoi");

String report = buffer.toString();
~~~

Nếu chuyển thành `String` quá sớm rồi vẫn liên tục sửa buffer, bản `String` sớm sẽ **không được đồng bộ tự động** với nội dung cuối.

Ví dụ:

~~~java
StringBuffer buffer = new StringBuffer("Hello");

String tooEarly = buffer.toString();
buffer.append(" World");

System.out.println(tooEarly);          // Hello
System.out.println(buffer.toString()); // Hello World
~~~

Vì vậy hãy gọi `toString()` tại **ranh giới giữa quá trình xây dựng mutable và kết quả immutable**. Ví dụ ranh giới đó có thể là cuối một hàm dựng thông báo, trước khi gửi kết quả cho API hoặc khi muốn lưu trạng thái hiện tại.

Không phải lúc nào cũng chỉ chuyển một lần. Nếu hệ thống có chủ đích lưu nhiều mốc lịch sử:

~~~java
StringBuffer timeline = new StringBuffer("start");
String stage1 = timeline.toString();

timeline.append(" -> process");
String stage2 = timeline.toString();

System.out.println(stage1); // start
System.out.println(stage2); // start -> process
~~~

Đó là hai snapshot có ý nghĩa riêng, không phải thao tác thừa.

## 7. So sánh StringBuffer, StringBuilder và String

| Đặc điểm | `String` | `StringBuffer` | `StringBuilder` |
| --- | --- | --- | --- |
| Nội dung có thể sửa? | Không | Có | Có |
| Nối dần với `append()`? | Không | Có | Có |
| Dùng `toString()` để lấy String? | Giá trị vốn đã là String | Có | Có |
| Phương thức sửa đổi chủ chốt có đồng bộ? | Không có sửa tại chỗ | Có đồng bộ | Không đồng bộ |
| Thường dùng | Giá trị văn bản ổn định | Xây văn bản với nhu cầu đồng bộ | Xây văn bản trong phạm vi một luồng |
| Chỉnh sửa buffer/builder sau snapshot có đổi String? | Không áp dụng | Không | Không |

Ví dụ hai loại builder đều có thể lấy kết quả `String`:

~~~java
StringBuffer synchronizedBuilder = new StringBuffer("A");
String fromBuffer = synchronizedBuilder.toString();

StringBuilder unsynchronizedBuilder = new StringBuilder("A");
String fromBuilder = unsynchronizedBuilder.toString();

System.out.println(fromBuffer.equals(fromBuilder)); // true
~~~

Tuy nhiên, một đối tượng `StringBuffer` đang được dùng bởi nhiều luồng có thể nhận các phép thay đổi giữa những lời gọi; việc `toString()` tạo snapshot **không tự biến cả quy trình nhiều bước thành giao dịch nguyên tử** (xem mục 9).

## 8. Những lỗi thường gặp khi chuyển đổi

### 8.1. Quên gọi toString() khi nơi nhận cần String

~~~java
StringBuffer buffer = new StringBuffer("Hello");
// String text = buffer; // Lỗi biên dịch: StringBuffer không phải String
String text = buffer.toString();
~~~

`StringBuffer` và `String` là hai lớp khác nhau, dù đều chứa chuỗi ký tự. Java không thực hiện phép ép kiểu ngầm từ một `StringBuffer` sang `String`.

### 8.2. Ép kiểu bằng cast không hợp lệ

~~~java
StringBuffer buffer = new StringBuffer("Hello");
// String text = (String) buffer; // Không có quan hệ ép kiểu hợp lệ
String text = buffer.toString();
~~~

Không thể thay `toString()` bằng ép kiểu. Chúng không cùng đối tượng và không có quan hệ kế thừa cho phép cast như vậy.

### 8.3. Lưu String rồi mong nó tự cập nhật

~~~java
StringBuffer buffer = new StringBuffer("A");
String snapshot = buffer.toString();

buffer.append("B");
System.out.println(snapshot); // A
~~~

Muốn giá trị mới, lấy snapshot mới: `snapshot = buffer.toString();`.

### 8.4. Chuyển đổi làm rỗng hoặc khóa buffer

~~~java
StringBuffer buffer = new StringBuffer("ABC");
String text = buffer.toString();

System.out.println(buffer.length()); // 3
buffer.append("D");                 // Vẫn hợp lệ
System.out.println(buffer);          // ABCD
System.out.println(text);            // ABC
~~~

`toString()` **không** đặt lại độ dài, không giải phóng bộ nhớ để người lập trình quản lý, không ngăn các lời gọi `append()` sau đó.

### 8.5. Dùng equals trên StringBuffer để so nội dung

`StringBuffer` không định nghĩa `equals()` theo nội dung giống `String`. Nếu muốn so văn bản, chuyển sang `String` (hoặc dùng thuật toán so chuỗi phù hợp):

~~~java
StringBuffer a = new StringBuffer("Java");
StringBuffer b = new StringBuffer("Java");

System.out.println(a.equals(b));                     // false
System.out.println(a.toString().equals(b.toString())); // true
~~~

Đừng trộn khái niệm **tham chiếu bằng nhau** với **dữ liệu văn bản giống nhau**.

### 8.6. Trả về String rồi tiếp tục thay đổi buffer trong phương thức

Điều này có thể hoàn toàn hợp lệ nhưng cần biết phương thức đang trả **snapshot**:

~~~java
static String makeText() {
    StringBuffer b = new StringBuffer("A");
    String s = b.toString();
    b.append("B");
    return s; // "A", không phải "AB"
}
~~~

Nếu muốn trả `"AB"`, hãy chuyển ở cuối sau khi hoàn tất `append()`.

## 9. Đồng bộ và đa luồng: đảm bảo đến đâu?

`StringBuffer` được thiết kế với các phương thức chủ chốt **synchronized**, khác `StringBuilder`. Việc gọi `toString()` tạo giá trị `String` ổn định sau khi nhận được kết quả, nhưng cần phân biệt:

- Một thao tác đồng bộ riêng lẻ trên `StringBuffer` có tính bảo vệ ở phạm vi của **thao tác đó**.
- Nhiều thao tác như `append()` → `delete()` → `toString()` không trở thành **một thao tác nguyên tử** chỉ vì từng lời gọi đều được đồng bộ.
- Một luồng khác có thể thay đổi nội dung buffer giữa hai lời gọi; snapshot có thể chứa nội dung tại một mốc không như người viết dự đoán nếu thiếu phối hợp.
- `String` đã trả về bất biến, nên bản thân nội dung của nó không tiếp tục thay đổi khi các luồng sửa buffer.

Khi cần lấy snapshot của **một chuỗi thay đổi logic** mà không bị xen vào, phải có chiến lược đồng bộ bao toàn bộ chuỗi thao tác và mọi luồng liên quan cùng tuân thủ quy tắc khóa:

~~~java
StringBuffer shared = new StringBuffer();

String snapshot;
synchronized (shared) {
    shared.append("A");
    shared.append("B");
    snapshot = shared.toString();
}

System.out.println(snapshot); // AB
~~~

Đây là một ví dụ đơn luồng cho cú pháp khóa. Trong ứng dụng đa luồng, kết quả được bảo vệ khỏi thay đổi **xen vào bởi những thao tác tuân thủ cùng khóa `shared`**. Không dựa vào việc chỉ có `StringBuffer` để giải quyết mọi vấn đề đồng bộ ở cấp độ nghiệp vụ.

Lưu ý: có thể thiết kế để mỗi luồng dùng buffer riêng rồi xuất `String`; khi không cần đồng bộ, `StringBuilder` thường là lựa chọn đơn giản hơn.

## 10. Unicode, độ dài và encoding sau chuyển đổi

`StringBuffer` lưu một chuỗi các **UTF-16 code units** về mặt API `char`/chỉ số, cũng như `String`. Chuyển bằng `toString()` giữ nguyên thứ tự ký tự được biểu diễn: không tự đổi chữ hoa/thường, chuẩn hóa Unicode hay mã hóa UTF-8.

~~~java
StringBuffer buffer = new StringBuffer("A😀B");
String text = buffer.toString();

System.out.println(buffer.length()); // 4
System.out.println(text.length());   // 4
System.out.println(text.codePointCount(0, text.length())); // 3
~~~

Emoji `😀` chiếm hai đơn vị UTF-16 nhưng là một Unicode code point. Chuyển đổi sang `String` không làm thay đổi sự khác biệt này.

Để có **byte UTF-8** phục vụ lưu file/mạng:

~~~java
StringBuffer buffer = new StringBuffer("A");
byte[] encoded = buffer.toString().getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

System.out.println(encoded.length); // 1
~~~

`toString()` không phải một phương thức encode. Đặc biệt, không nhầm `StringBuffer` với `ByteBuffer`.

## 11. Chương trình hoàn chỉnh chạy trên Java 17+

Tạo file **`StringBufferToStringDemo.java`**:

~~~java
public class StringBufferToStringDemo {
    public static void main(String[] args) {
        StringBuffer buffer = new StringBuffer("Java");
        buffer.append(" Core");

        String first = buffer.toString();
        System.out.println("first=" + first);

        buffer.append(" 17");
        System.out.println("buffer=" + buffer);
        System.out.println("firstAgain=" + first);

        String second = new String(buffer);
        System.out.println("second=" + second);

        buffer.setCharAt(0, 'K');
        System.out.println("afterEdit=" + buffer);
        System.out.println("secondAgain=" + second);

        buffer.setLength(0);
        System.out.println("empty=[" + buffer.toString() + "]");
        System.out.println("firstAfterClear=" + first);

        StringBuffer missing = null;
        System.out.println("valueOfNull=" + String.valueOf(missing));

        StringBuffer other = new StringBuffer("Java Core");
        System.out.println("contentEquals="
                + first.equals(other.toString()));

        StringBuffer unicode = new StringBuffer("A😀B");
        String snapshot = unicode.toString();
        System.out.println("utf16=" + snapshot.length());
        System.out.println("codePoints="
                + snapshot.codePointCount(0, snapshot.length()));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac -encoding UTF-8 StringBufferToStringDemo.java
java StringBufferToStringDemo
~~~

**Stdout chính xác:**

~~~text
first=Java Core
buffer=Java Core 17
firstAgain=Java Core
second=Java Core 17
afterEdit=Kava Core 17
secondAgain=Java Core 17
empty=[]
firstAfterClear=Java Core
valueOfNull=null
contentEquals=true
utf16=4
codePoints=3
~~~

**Giải thích theo từng nhóm:**

1. `first` chụp nội dung buffer sau `append(" Core")`. Khi buffer được nối thêm `" 17"`, biến `first` vẫn là `"Java Core"`.
2. `second = new String(buffer)` chụp nội dung mới `"Java Core 17"`. Việc đổi `buffer.setCharAt(0, 'K')` thành `"Kava Core 17"` không sửa `second`.
3. `setLength(0)` chỉ làm buffer rỗng; `first` vẫn giữ chuỗi đầu tiên.
4. `String.valueOf(missing)` với tham chiếu null cho ra bốn ký tự văn bản `"null"`.
5. `first.equals(other.toString())` so sánh nội dung hai `String` và trả `true`.
6. Khi có emoji, `length()` tính theo UTF-16 code units; `codePointCount()` cho số code points.

Hãy thử thêm `buffer.append("again")` sau `setLength(0)`: bạn sẽ thấy buffer sử dụng lại được, trong khi `first` và `second` vẫn giữ giá trị của mình.

## 12. Chọn phương thức đúng trong từng tình huống

| Tình huống | Cách làm | Lý do |
| --- | --- | --- |
| Đã dựng xong nội dung, cần kết quả `String` | `buffer.toString()` | Trực tiếp, rõ nghĩa |
| Muốn tạo `String` từ buffer tại thời điểm hiện tại | `new String(buffer)` | Hợp lệ nhưng thường không cần thay cho `toString()` |
| Đối số có thể null và yêu cầu hiển thị chữ "null" | `String.valueOf(buffer)` | Có quy tắc chuyển null thành văn bản |
| Null cần được bảo toàn thành null | `buffer == null ? null : buffer.toString()` | Hợp đồng xử lý null rõ ràng |
| Phương thức nhận `CharSequence` và chỉ đọc ngay | Có thể truyền `buffer` | Không cần chuyển đổi nếu không cần snapshot |
| Trả dữ liệu ổn định cho phần mềm khác giữ lâu | `buffer.toString()` | Không chia sẻ trạng thái mutable |
| Tiếp tục nối sửa nhiều lần | Giữ `StringBuffer` hoặc chọn `StringBuilder` | Không cần chuyển sớm |
| Chuyển sang byte UTF-8 | `buffer.toString().getBytes(UTF_8)` | Chuyển loại văn bản và mã hóa là hai việc khác nhau |

**Lưu ý hiệu năng:** `toString()` có thể cần xử lý/sao chép dữ liệu và tạo giá trị kết quả, do đó gọi trong một vòng lặp lớn chỉ để nhìn nội dung trung gian có thể tốn chi phí. Mức phân bổ chi tiết tùy JDK và việc tối ưu; đừng giả định có hoặc không có đối tượng mới ở mọi lần gọi. Nên giữ kết quả khi thực sự cần một snapshot, không chuyển qua lại giữa buffer và `String` liên tục chỉ vì thói quen.

## 13. Bài tập luyện tập

### Bài 1 — Tạo hai snapshot

Khởi tạo `StringBuffer b = new StringBuffer("A");`. Lấy `String s1 = b.toString();`, sau đó `b.append("B");` và lấy `String s2 = b.toString();`. In cả `s1`, `s2`, `b`. Giải thích vì sao chỉ `b` và `s2` chứa chữ `B`.

### Bài 2 — new String(buffer)

Chuyển `StringBuffer("Hello")` sang `String` bằng constructor `new String(buffer)`. Sau đó gọi `buffer.delete(0, 1)`. Dự đoán chuỗi đã tạo và buffer hiện tại. Vì sao chúng khác nhau?

### Bài 3 — Null policies

Viết hàm `asTextOrNull(StringBuffer b)` trả null nếu input null, còn lại dùng `toString()`. So với `String.valueOf((Object) b)` trên null và giải thích sự khác nhau giữa chuỗi `"null"` và tham chiếu null.

### Bài 4 — Ranh giới của API

Viết hai hàm: `printText(String text)` và `readLength(CharSequence text)`. Thử truyền trực tiếp `StringBuffer` cho từng hàm. Hàm nào nhận được mà không cần chuyển? Nếu phương thức giữ tham chiếu để xử lý về sau, vì sao có thể muốn chuyển sang `String`?

### Bài 5 — Tái sử dụng buffer

Tạo buffer, append ba phần, chuyển thành `String first`. Gọi `setLength(0)`, append nội dung mới và lấy `String second`. Chứng minh `first` không thay đổi sau khi xóa buffer.

### Bài 6 — So sánh nội dung

Tạo hai `StringBuffer` có nội dung `"same"`. So `a.equals(b)` với `a.toString().equals(b.toString())`. Kết quả nào kiểm tra **nội dung**? Vì sao không nên dùng `==` để so chuỗi?

### Bài 7 — Đồng bộ ở cấp nghiệp vụ

Giả sử hai luồng cùng dùng buffer. Một luồng thực hiện `append("A")` rồi `append("B")`, luồng khác có thể append xen vào. Viết cách đồng bộ để lấy snapshot của hai thao tác như một nhóm, và giải thích vì sao mọi bên truy cập phải tuân thủ cùng quy tắc khóa.

### Bài 8 — Unicode

Chuyển `StringBuffer("A😀B")` thành `String`, đo `length()` và `codePointCount()`. Vì sao một emoji không được đếm thành một `char`? `toString()` có thực hiện UTF-8 encoding không?

## 14. Checklist nhận thức và lỗi cần tránh

- `StringBuffer.toString()` **trả về kiểu `String`**, không phải `StringBuffer`.
- Một `String` đã lấy ra **không phản ánh** các phép thay đổi trên buffer về sau.
- `toString()` **không rút nội dung ra khỏi buffer** và không tự xóa hay khóa buffer.
- `new String(buffer)` hợp lệ; `(String) buffer` không hợp lệ.
- `String.valueOf(buffer)` với null có thể cho **văn bản `"null"`** ngoài ý muốn.
- Phương thức yêu cầu `String` cần một `String`; phương thức nhận `CharSequence` có thể nhận buffer trực tiếp.
- `StringBuffer` mutable nên chia sẻ nó không giống chia sẻ một `String` bất biến.
- Một chuỗi thao tác nhiều bước chưa an toàn nguyên tử chỉ vì từng phương thức buffer đồng bộ.
- Nếu chỉ cần dựng văn bản trong phạm vi một luồng, `StringBuilder` thường đơn giản và phù hợp hơn.
- `toString()` không tự đổi Unicode, không chuẩn hóa và không chuyển sang byte UTF-8.
- Nếu cần so nội dung, dùng `equals()` trên hai đối tượng `String`.
- Nếu lấy nhiều snapshots, đặt tên rõ thời điểm: `before`, `after`, `finalText`.

**Quy tắc ghi nhớ:** dùng **`String text = buffer.toString();`** để lấy một giá trị văn bản **bất biến** từ trạng thái hiện tại của `StringBuffer`. Có thể tiếp tục sửa buffer, nhưng `text` không thay đổi. Chọn thời điểm tạo snapshot theo mục đích nghiệp vụ, và quyết định rõ chính sách với `null` và dữ liệu nhiều luồng.

## 15. Tài liệu chuẩn

- [Java SE 17 — StringBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuffer.html): `toString()`, `append()`, `setCharAt()`, `setLength()` và các thao tác mutable.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): constructor `String(StringBuffer)`, `equals()`, `valueOf()`, UTF-16 và tính bất biến.
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): biến thể builder không đồng bộ và chuyển thành String.
- [Java SE 17 — CharSequence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html): hợp đồng cho các đối tượng biểu diễn dãy ký tự.
