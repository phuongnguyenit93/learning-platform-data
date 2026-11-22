# Kiến thức nền về kiểu dữ liệu, ngoại lệ, chuỗi và quản lý tài nguyên trong Java

> Bài định hướng cho Java 14 và các phiên bản Java hiện đại. Nội dung sử dụng các đặc điểm ngôn ngữ và API **đang còn áp dụng**, không dựa vào tính năng preview hay cách làm đã lỗi thời. Ví dụ độc lập được biên dịch/chạy bằng JDK 17+.

## Mục tiêu học tập

Sau bài này, bạn cần phân biệt kiểu nguyên thủy và tham chiếu; tránh sai số, tràn số và unboxing `null`; xử lý `String` đúng với Unicode; phân biệt ngoại lệ checked/unchecked; bảo toàn nguyên nhân lỗi; và đóng tài nguyên bằng `try-with-resources`. Đây là một luồng kiến thức chung: **đọc dữ liệu → biểu diễn đúng kiểu → kiểm tra/chuyển đổi → xử lý lỗi → giải phóng tài nguyên**.

## 1. Kiểu dữ liệu: giá trị nguyên thủy và tham chiếu

Java là ngôn ngữ kiểm tra kiểu tĩnh: kiểu của biểu thức được xác định và kiểm tra khi biên dịch. Có **8 kiểu nguyên thủy**:

| Kiểu | Đặc điểm | Trường hợp điển hình |
| --- | --- | --- |
| `byte` | Số nguyên có dấu 8 bit, −128..127 | Dữ liệu byte/giao thức |
| `short` | Số nguyên có dấu 16 bit | Trường dữ liệu 16 bit |
| `int` | Số nguyên có dấu 32 bit, −2³¹..2³¹−1 | Số đếm thông thường |
| `long` | Số nguyên có dấu 64 bit | Giá trị nguyên lớn; literal cần hậu tố `L` khi vượt `int` |
| `float` | Số thực dấu phẩy động IEEE 754, 32 bit | Trường hợp yêu cầu số thực 32 bit; literal dùng `f` |
| `double` | Số thực dấu phẩy động IEEE 754, 64 bit | Tính toán gần đúng thông thường |
| `char` | **Đơn vị mã UTF-16** 16 bit | Đọc một code unit; không chắc là trọn một ký tự Unicode |
| `boolean` | `true` hoặc `false` | Điều kiện/trạng thái |

**Kiểu tham chiếu** gồm lớp (`String`, `BigDecimal`...), interface, mảng, enum, record... Biến tham chiếu có thể mang `null` hoặc tham chiếu đến đối tượng. Hai biến có thể tham chiếu **cùng đối tượng**. Không nên suy luận rằng primitive “luôn trên stack” còn object “luôn trên heap”: vị trí vật lý phụ thuộc triển khai JVM và tối ưu hóa; ngữ nghĩa chương trình là điều cần nắm.

Biến cục bộ phải được gán trước khi dùng. Trường và phần tử mảng nhận giá trị mặc định (`0`, `0.0`, `false`, `null` tùy kiểu), nhưng nên khởi tạo tường minh khi cần nêu rõ ý nghĩa nghiệp vụ.

### Khai báo, `var`, `final` và truyền tham số

~~~java
int quantity = 12;
long views = 3_000_000_000L;
double average = 2.5;
boolean available = true;
var label = "Java";       // compiler suy ra String, KHÔNG phải dynamic typing
final int maxAttempts = 3;
~~~

`var` chỉ suy luận kiểu **biến cục bộ** đã có initializer hợp lệ; không dùng cho field, return type, tham số phương thức, hoặc `var x = null`. Sau suy luận, `label` vẫn có kiểu `String` và không thể gán một `int`. `final` ngăn **gán lại biến**, không làm đối tượng được tham chiếu thành bất biến: `final List<String> names = new ArrayList<>();` vẫn có thể `names.add(...)`.

Java **luôn truyền tham số theo giá trị**. Truyền primitive là sao chép giá trị; truyền object reference là sao chép **tham chiếu**. Vì vậy, phương thức có thể sửa trạng thái đối tượng chung qua tham chiếu, nhưng việc gán lại tham số không thay biến của bên gọi.

### Chuyển đổi kiểu, tràn số và độ chính xác

- Chuyển đổi mở rộng (`int` sang `long`) thường tự động; thu hẹp (`long` sang `int`) cần ép kiểu và có thể mất dữ liệu. Tránh ép kiểu chỉ để làm hết lỗi biên dịch.
- `7 / 2` bằng `3` vì hai toán hạng là nguyên; `(double) 7 / 2` bằng `3.5`. Ép kiểu **sau phép chia** như `(double) (7 / 2)` chỉ cho `3.0`.
- Phép cộng nguyên thông thường có thể **tràn số mà không ném ngoại lệ**. Dùng `Math.addExact`/`multiplyExact` khi cần phát hiện tràn; chọn `long`/`BigInteger` khi miền giá trị thực tế đòi hỏi.
- `float`/`double` là giá trị nhị phân gần đúng, không thích hợp để bảo đảm tính toán thập phân chính xác như tiền. Dùng `BigDecimal` được tạo từ chuỗi (`new BigDecimal("0.1")`); khi chia có thể cần chỉ rõ `RoundingMode`. `BigDecimal.equals` phân biệt scale (`1.0` khác `1.00`), còn `compareTo(...) == 0` so sánh giá trị số.
- Wrapper: `int ↔ Integer`, `long ↔ Long`, `double ↔ Double`, `boolean ↔ Boolean`... Generic collection dùng `List<Integer>`, không phải `List<int>`. **Unboxing `Integer` đang là `null` gây `NullPointerException`**. Thiết kế biểu diễn “chưa có giá trị” thay vì để lỗi phát sinh ngẫu nhiên.

**Ví dụ độc lập – `DataTypesDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public class DataTypesDemo {
    static void update(int number, List<String> names) {
        number = 99;     // chỉ thay đổi bản sao tham số
        names.add("B");  // thay đổi cùng một đối tượng List
    }

    public static void main(String[] args) {
        System.out.println(7 / 2);
        System.out.println((double) 7 / 2);

        int number = 1;
        List<String> names = new ArrayList<>();
        names.add("A");
        update(number, names);
        System.out.println(number);
        System.out.println(names);

        BigDecimal result = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println(result);

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("Tràn số");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DataTypesDemo.java
java DataTypesDemo
~~~

~~~text
3
3.5
1
[A, B]
0.3
Tràn số
~~~

**Liên hệ Java 14:** `switch expression` đã ổn định từ Java 14 và trả ra một giá trị có kiểu. Đây là **phương thức minh họa** đặt trong một lớp Java:

~~~java
static int priority(String level) {
    return switch (level) {
        case "HIGH" -> 3;
        case "MEDIUM" -> 2;
        default -> 1;
    };
}
~~~

Nếu `level` có thể là `null`, cần xác định cách xử lý theo hợp đồng phương thức; không giả định `default` luôn bao gồm `null`.

## 2. Chuỗi: bất biến, so sánh và Unicode

### `String` là immutable

Đối tượng `String` **không thay đổi sau khi tạo**. Các phép `strip()`, `replace(...)`, `substring(...)` tạo/đưa về kết quả mà không sửa chuỗi ban đầu:

~~~java
String raw = "  Học Java  ";
String cleaned = raw.strip();
// raw vẫn là "  Học Java  "
// cleaned là "Học Java"
~~~

Đừng dùng `==` để kiểm tra **nội dung** hai chuỗi: `==` kiểm tra cùng tham chiếu; `a.equals(b)` kiểm tra nội dung. Khi một/both biến có thể `null`, dùng `Objects.equals(a, b)` hoặc kiểm tra null trước.

| Nhu cầu | API/cách dùng | Cạm bẫy |
| --- | --- | --- |
| Bằng nhau về nội dung | `equals` / `Objects.equals` | `==` không kiểm tra nội dung |
| So sánh bỏ hoa/thường đơn giản | `equalsIgnoreCase` | Không thay thế xử lý ngôn ngữ/locale chuyên biệt |
| Chuỗi rỗng | `isEmpty()` | `"  "` không rỗng |
| Toàn khoảng trắng | `isBlank()` | `"  "` là blank |
| Bỏ whitespace hai đầu | `strip()` | Hữu ích với Unicode whitespace |
| Lấy đoạn | `substring(start, end)` | `start` gồm, `end` không gồm; chỉ số UTF-16 |
| Tìm vị trí | `indexOf(...)` | Trả `-1` khi không tìm được |
| Thay text thuần | `replace(old, new)` | `replaceAll(regex, new)` dùng regex |
| Tách | `split(regex)` | Dấu chấm literal cần regex `"\\."` trong mã Java |

`String.length()` đo **số đơn vị UTF-16**, không phải số điểm mã (Unicode code points) hay ký tự người đọc nhìn thấy (grapheme clusters). Emoji 🚀 gồm hai `char` (surrogate pair), nên `"🚀".length()` bằng 2 nhưng `codePointCount(0, length())` bằng 1; chuỗi có dấu kết hợp/emoji ghép còn phức tạp hơn. Không mặc định `charAt(i)` lấy được một ký tự hiển thị hoàn chỉnh.

Khi đổi text ↔ bytes, nên nêu rõ charset:

~~~java
byte[] data = "Tiếng Việt".getBytes(java.nio.charset.StandardCharsets.UTF_8);
String text = new String(data, java.nio.charset.StandardCharsets.UTF_8);
~~~

Không nên cắt tùy tiện bytes rồi coi mỗi byte là một ký tự. Khi chuyển chữ hoa/thường/sắp xếp theo ngôn ngữ, xác định `Locale` và công cụ so sánh phù hợp.

Nối vài chuỗi bằng `+` dễ đọc. Nếu phải nối trong **vòng lặp nhiều lần**, dùng `StringBuilder` để giảm đối tượng trung gian. `StringBuilder` mutable và không an toàn khi nhiều luồng cùng sửa; thường giữ ở phạm vi cục bộ.

**Ví dụ độc lập – `StringBasics.java`:**

~~~java
public class StringBasics {
    public static void main(String[] args) {
        String a = new String("Java"); // chỉ để minh họa identity
        String b = "Java";
        System.out.println(a == b);
        System.out.println(a.equals(b));

        String raw = "  Học Java  ";
        System.out.println(raw.strip());
        System.out.println("  ".isBlank());

        String rocket = "🚀";
        System.out.println(rocket.length());
        System.out.println(rocket.codePointCount(0, rocket.length()));

        StringBuilder builder = new StringBuilder("Java");
        builder.append(" hiện đại");
        System.out.println(builder);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StringBasics.java
java StringBasics
~~~

~~~text
false
true
Học Java
true
2
1
Java hiện đại
~~~

`new String("Java")` chỉ dùng trong ví dụ để tạo một đối tượng khác literal; trong mã thường ngày không cần tạo chuỗi theo cách này.

## 3. Ngoại lệ: checked, unchecked và nguyên nhân lỗi

### Phân loại theo cây kế thừa

~~~text
Throwable
├── Error                    lỗi nghiêm trọng của môi trường/JVM
└── Exception
    ├── IOException          checked
    └── RuntimeException     unchecked
        ├── NumberFormatException
        ├── IllegalArgumentException
        ├── NullPointerException
        └── IllegalStateException
~~~

`NumberFormatException` **là lớp con của `IllegalArgumentException`**. Danh sách trên minh họa nhóm ngoại lệ thông dụng, không phải sơ đồ đầy đủ từng cấp của hai lớp đó.

- **Checked exception** (ví dụ `IOException`, `SQLException`): trình biên dịch yêu cầu phương thức **bắt bằng `catch` hoặc khai báo `throws`**. Các tình huống như lỗi đọc file phù hợp để bên gọi quyết định retry, thông báo hay dừng thao tác.
- **Unchecked exception** (`RuntimeException` và các lớp con): không buộc bắt/khai báo tại thời điểm biên dịch. Thường diễn đạt đầu vào không hợp lệ, trạng thái sai, hoặc lỗi hợp đồng API.
- **`Error`:** không nên bắt hàng loạt như lỗi nghiệp vụ. Tránh `catch (Throwable t)` để che lỗi nghiêm trọng.

Checked/unchecked là quy tắc của **hệ thống kiểu/API**, không phải cam kết rằng checked luôn khôi phục được, unchecked luôn là lỗi lập trình.

### Cách ném, bắt và truyền lỗi

`throw` ném ngoại lệ tại thời điểm chạy; `throws` trên phương thức là khai báo khả năng phát sinh checked exception. `try` đặt phạm vi thao tác; `catch` chỉ xử lý những lỗi mà tầng hiện tại hiểu và có hành động hợp lý; `finally` làm việc cuối cùng khác việc đóng tài nguyên tự động. Với `catch` nhiều loại, đặt nhánh cụ thể trước nhánh tổng quát; có thể dùng multi-catch `catch (IOException | SQLException ex)` nếu xử lý giống nhau.

Nếu không có cách phục hồi, để lỗi truyền lên hoặc bọc bằng ngoại lệ có ý nghĩa hơn **kèm `cause`**. Không bắt rồi im lặng, trả về `0`/chuỗi rỗng khi điều đó đánh đồng **lỗi** với **dữ liệu hợp lệ**. Bắt `Exception` ở mọi phương thức làm mất tính cụ thể và dễ che lỗi; chỉ cân nhắc bắt rộng ở ranh giới ứng dụng có chính sách xử lý rõ ràng.

**Ví dụ độc lập – `ExceptionDemo.java`:**

~~~java
public class ExceptionDemo {
    static int parsePositive(String input) {
        final int value;
        try {
            value = Integer.parseInt(input);
        } catch (NumberFormatException cause) {
            throw new IllegalArgumentException("Phải nhập số nguyên", cause);
        }

        if (value <= 0) {
            throw new IllegalArgumentException("Phải lớn hơn 0");
        }
        return value;
    }

    public static void main(String[] args) {
        System.out.println(parsePositive("12"));

        try {
            parsePositive("abc");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
            System.out.println(ex.getCause() instanceof NumberFormatException);
        }

        try {
            parsePositive("0");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExceptionDemo.java
java ExceptionDemo
~~~

~~~text
12
Phải nhập số nguyên
true
Phải lớn hơn 0
~~~

Mã phân biệt **lỗi cú pháp số** (có `NumberFormatException` làm `cause`) với **số không dương** (vi phạm quy tắc nghiệp vụ). Cần dùng constructor cho phép truyền nguyên nhân khi bọc ngoại lệ, ví dụ `new IllegalArgumentException("Thông báo", cause)`. Khi log, bổ sung ngữ cảnh thao tác vừa đủ nhưng không lộ mật khẩu, token hay dữ liệu nhạy cảm; tránh log cùng một lỗi lặp lại ở mọi tầng.

### Một số nguyên tắc xử lý

1. Kiểm tra đầu vào ở đúng ranh giới, ví dụ `Objects.requireNonNull(value, "value")` khi null không hợp lệ.
2. Bắt loại ngoại lệ **cụ thể** và phân biệt lỗi dữ liệu với lỗi hạ tầng.
3. Không sử dụng ngoại lệ thay cho nhánh điều kiện thông thường (ví dụ kiểm tra rỗng).
4. Không `return` trong `finally`: có thể che kết quả hoặc ngoại lệ đang thoát.
5. Nếu ngoại lệ đã được xử lý hoàn toàn, trả kết quả có ý nghĩa; nếu không, truyền/bọc lỗi cùng nguyên nhân để tầng cao hơn quyết định.

## 4. Quản lý tài nguyên: `AutoCloseable` và `try-with-resources`

Bộ nhớ của object được JVM quản lý, còn **handle ngoài bộ nhớ** (stream, reader/writer, file, socket, kết nối JDBC...) cần được đóng đúng vòng đời. `AutoCloseable` định nghĩa `close()`; `Closeable` là một interface chuyên biệt. **GC không bảo đảm file descriptor hay kết nối được đóng đúng lúc.**

Với tài nguyên có `close()`, ưu tiên:

~~~java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String firstLine = reader.readLine();
    // xử lý dữ liệu...
}
~~~

Đoạn trên là **mẫu đặt trong phương thức**, cần import `java.io.BufferedReader`, `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets` và xử lý/khai báo `IOException`. `reader.close()` được gọi tự động khi ra khỏi khối, kể cả lúc có exception hoặc `return`. Nhiều tài nguyên khai báo cùng một `try(...)` đóng theo **thứ tự ngược**. Biến đã tồn tại cũng được dùng trong `try(...)` nếu `final` hoặc *effectively final* (Java 9+).

### Chọn cách đọc dữ liệu

- `Files.readString(path, StandardCharsets.UTF_8)` phù hợp với **file văn bản nhỏ** khi có thể giữ toàn bộ nội dung trong RAM.
- `Files.newBufferedReader(path, UTF_8)` cho phép đọc lần lượt các dòng, phù hợp khi file dài hoặc phải xử lý từng dòng.
- `Files.lines(path, UTF_8)` trả về `Stream<String>` gắn với tài nguyên và cần `try-with-resources`; không bỏ stream đang mở cho nơi khác mà không xác định ai có trách nhiệm đóng.
- Với JDBC, phải đóng các tài nguyên truy vấn/kết nối theo hợp đồng API. Với connection pool, `close()` có thể là trả kết nối về pool; vẫn phải gọi.
- Các tiện ích như `Files.readString` tự quản lý tài nguyên đọc bên trong, nên chuỗi kết quả không có thao tác `close()`.

### Ngoại lệ phát sinh khi đóng

Nếu thân khối `try` ném A, rồi `close()` ném B, Java giữ **A làm ngoại lệ chính** và đưa B vào `A.getSuppressed()`. Nhờ đó, lỗi đóng không xóa dấu vết lỗi xử lý ban đầu.

**Ví dụ độc lập – `ResourceDemo.java`:**

~~~java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ResourceDemo {
    static final class FailingClose implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("đóng thất bại");
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] data = "Dòng 1\nDòng 2".getBytes(StandardCharsets.UTF_8);

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        new ByteArrayInputStream(data),
                        StandardCharsets.UTF_8))) {
            System.out.println(reader.readLine());
            System.out.println(reader.readLine());
        }

        try (FailingClose resource = new FailingClose()) {
            throw new IllegalArgumentException("xử lý thất bại");
        } catch (IllegalArgumentException ex) {
            System.out.println("Lỗi chính: " + ex.getMessage());
            System.out.println("Lỗi bị nén: "
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ResourceDemo.java
java ResourceDemo
~~~

~~~text
Dòng 1
Dòng 2
Lỗi chính: xử lý thất bại
Lỗi bị nén: đóng thất bại
~~~

Trong ví dụ, `getSuppressed()[0]` chắc chắn tồn tại vì ta chủ động gây ra đúng một lỗi lúc đóng. Mã xử lý ngoại lệ tổng quát cần kiểm tra độ dài mảng trước khi truy cập.

### Lỗi tài nguyên thường gặp

| Sai sót | Rủi ro | Cách sửa |
| --- | --- | --- |
| Đóng reader chỉ khi thao tác thành công | Rò rỉ handle khi ném exception | Bao toàn bộ thời gian dùng bằng `try-with-resources` |
| Đọc file lớn bằng `readString` không xét kích thước | Tốn nhiều bộ nhớ | Đọc bằng `BufferedReader`/stream |
| Không đóng `Stream` trả từ `Files.lines` | File handle còn giữ | Quản lý `Stream` trong `try-with-resources` |
| Bắt `IOException` và trả chuỗi rỗng | Nhầm lỗi I/O với file rỗng hợp lệ | Báo lỗi hoặc trả kiểu kết quả biểu diễn thất bại rõ ràng |
| Bọc ngoại lệ mà không giữ `cause` | Mất stack trace nguyên nhân | Chuyển nguyên nhân vào exception mới |
| Cho nhiều luồng sửa cùng `StringBuilder` | Kết quả không nhất quán | Dùng biến cục bộ hoặc đồng bộ hóa khi cần |

## 5. Kết hợp: đọc một số lượng nguyên dương từ file

Giả sử dữ liệu đầu vào là một dòng UTF-8. Ta cần phân tách: **đọc file có thể ném `IOException`**, còn **chuyển và xác thực giá trị** có thể ném `IllegalArgumentException`. Reader phải đóng trong cả hai trường hợp.

Đoạn dưới là **phương thức đặt trong một lớp**, với import `java.io.*`, `java.nio.file.*` và `java.nio.charset.StandardCharsets`:

~~~java
static int loadPositiveQuantity(Path path) throws IOException {
    try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        String line = reader.readLine();
        if (line == null || line.isBlank()) {
            throw new IllegalArgumentException("Tệp thiếu số lượng");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(line.strip());
        } catch (NumberFormatException cause) {
            throw new IllegalArgumentException(
                    "Số lượng không phải số nguyên hợp lệ", cause);
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        return quantity;
    }
}
~~~

`readLine()` trả về `null` khi hết dữ liệu. Ví dụ này **chỉ đọc dòng đầu**; yêu cầu xử lý nhiều dòng cần một quy tắc riêng. `parseInt` cũng từ chối số vượt miền `int`, nên phải chọn kiểu khác nếu miền số lượng thực tế lớn hơn. Tầng gọi quyết định có retry hay hiển thị thông báo; không biến mọi lỗi thành `0`.

## 6. Tự kiểm tra và thực hành

1. Với `int a = 5, b = 2;`, giải thích tại sao `(double) (a / b)` là `2.0` nhưng `(double) a / b` là `2.5`. Đổi phép tính nếu cần kết quả thập phân.
2. Với `Integer count = null;`, dự đoán điều gì xảy ra khi chạy `int n = count;`. Đề xuất cách thể hiện giá trị “chưa biết” an toàn hơn.
3. Tạo hai chuỗi khác tham chiếu nhưng bằng nội dung; so sánh kết quả của `==` và `equals`. Sau đó thử với `null` và `Objects.equals`.
4. Đếm `length()` và `codePointCount()` của chuỗi chứa 🚀; lý giải vì sao `charAt(0)` không phải luôn là ký tự hiển thị hoàn chỉnh.
5. Viết hàm parse số dương từ `String`, phân biệt sai định dạng và số `0`; nếu bọc lỗi, giữ `cause`.
6. Đọc nhiều dòng tệp UTF-8 bằng `Files.lines` trong `try-with-resources`. Thử ném lỗi giữa lúc xử lý và kiểm tra tài nguyên vẫn đóng.
7. Viết `AutoCloseable` có `close()` ném ngoại lệ, ném thêm một ngoại lệ trong thân `try` và quan sát `getSuppressed()`.

**Checklist trước khi áp dụng:** kiểu đúng miền giá trị; tính toán đúng độ chính xác; `String` so sánh theo nội dung, có xét null/Unicode/UTF-8; ngoại lệ bắt đúng tầng và giữ nguyên nhân; mọi tài nguyên có người chịu trách nhiệm đóng. Những nguyên lý này vẫn là nền tảng của Java hiện đại.