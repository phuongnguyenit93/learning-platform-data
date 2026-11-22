# Phân biệt `finally`, `final` và `finalize()` trong Java

Ba tên **`finally`**, **`final`** và **`finalize()`** trông giống nhau nhưng có ý nghĩa hoàn toàn khác trong Java. `finally` là một phần của cấu trúc xử lý ngoại lệ, `final` là từ khóa hạn chế việc gán lại hoặc kế thừa/ghi đè, còn `finalize()` là một phương thức cũ thuộc cơ chế finalization của đối tượng, đã bị **deprecated** và không thích hợp để dọn dẹp tài nguyên đáng tin cậy.

Điểm cần nắm chắc: **`finally` gắn với luồng điều khiển của `try`; `final` gắn với khai báo trong mã nguồn; `finalize()` gắn với một cơ chế vòng đời đối tượng không xác định được thời điểm thực hiện.** Chúng không thể thay thế cho nhau và không có quan hệ “bản rút gọn/bản nâng cao”.

## 1. So sánh nhanh

| Tiêu chí | `finally` | `final` | `finalize()` |
| --- | --- | --- | --- |
| Loại cú pháp | Từ khóa mở đầu một khối trong cấu trúc `try` | Từ khóa modifier | Phương thức instance của `java.lang.Object` |
| Công dụng chính | Chạy công việc khi rời `try`/`catch` | Ngăn gán lại biến hoặc ngăn kế thừa/override | Cơ chế finalization cũ cho đối tượng trước khi bị thu hồi |
| Nơi xuất hiện | Sau phần thân `try` hoặc các `catch` tương ứng | Khai báo biến, tham số, field, phương thức, lớp (theo quy tắc) | `protected void finalize() throws Throwable` ở lớp kế thừa nếu override |
| Cơ chế thực thi | Khi điều khiển rời cấu trúc `try` qua các đường hợp lệ | Được compiler kiểm tra về phép gán và kế thừa | Có thể được hệ thống finalization gọi sau khi đối tượng đủ điều kiện, **không bảo đảm khi nào hoặc có chạy hay không** |
| Có phải công cụ xử lý ngoại lệ? | Có liên quan đến `try`, nhưng **không tự bắt lỗi** | Không | Không phải cơ chế xử lý ngoại lệ thông thường |
| Dùng trong Java mới? | Có, nhất là với công việc kết thúc/cleanup ngoài quản lý `AutoCloseable` | Có, rất phổ biến | **Không nên dùng cho thiết kế mới** |
| Ví dụ | `try { work(); } finally { cleanup(); }` | `final int limit = 10;` | `protected void finalize() throws Throwable` |

**Nhớ theo ba câu ngắn:** `finally` = *thực hiện khi rời try*; `final` = *giới hạn một số thay đổi trong mã*; `finalize()` = *cơ chế finalizer cũ, không đáng tin để đóng tài nguyên*.

## 2. `finally`: phần cuối của cấu trúc `try`

Dạng đơn giản:

~~~java
try {
    doWork();
} finally {
    cleanup();
}
~~~

Với cấu trúc có xử lý ngoại lệ:

~~~java
try {
    doWork();
} catch (IOException ex) {
    handleIOException(ex);
} finally {
    cleanup();
}
~~~

Các đoạn trên là **minh họa cấu trúc**, cần những phương thức và `import` tương ứng. Trong Java, `finally` là **từ khóa**, không phải tên phương thức, không có cặp ngoặc tham số `()`, không thể gọi bằng `object.finally()`.

### 2.1. Khi nào `finally` chạy?

Thông thường khi luồng thực thi rời một cấu trúc `try` liên quan, `finally` chạy dù phần `try`:

- hoàn tất bình thường, không ném ngoại lệ;
- ném ngoại lệ đã được một `catch` phù hợp xử lý;
- ném ngoại lệ chưa được bắt tại cấu trúc hiện tại, đang truyền lên tầng ngoài;
- đang chuẩn bị `return`, `break` hoặc `continue` làm rời cấu trúc;
- hoặc khi một `catch` được chọn tự ném tiếp ngoại lệ.

Ví dụ nhỏ:

~~~java
// Đặt trong phương thức.
try {
    System.out.println("Trong try");
} finally {
    System.out.println("Trong finally");
}
System.out.println("Sau try");
~~~

Stdout:

~~~text
Trong try
Trong finally
Sau try
~~~

Không có ngoại lệ nào, nhưng `finally` vẫn chạy. Vì vậy hiểu `finally` là “chỉ xử lý khi lỗi” là sai.

### 2.2. `finally` không tự xử lý hoặc nuốt ngoại lệ

~~~java
// Đặt trong phương thức được phép ném unchecked exception.
try {
    throw new IllegalStateException("thất bại");
} finally {
    System.out.println("Đã chạy finally");
}
~~~

Dòng in `Đã chạy finally` xuất hiện, sau đó `IllegalStateException` tiếp tục truyền ra ngoài nếu `finally` hoàn tất bình thường. Khối `finally` **không tương đương** với `catch (IllegalStateException)`.

Nếu muốn xử lý lỗi, dùng `catch` ở tầng có chiến lược xử lý phù hợp. Nếu muốn dọn dẹp lúc rời một thao tác, `finally` có thể thích hợp. Hai mục đích khác nhau.

### 2.3. `finally` không phải cam kết tuyệt đối bất chấp việc JVM dừng

Nếu JVM/tiến trình bị kết thúc cưỡng bức, gọi `Runtime.halt`, một đường `System.exit` hoàn tất việc dừng máy ảo, hoặc luồng không bao giờ rời khối `try`, không nên kỳ vọng `finally` vẫn hoàn tất. Sự cố như crash hoặc mất điện cũng có thể làm công việc chưa được thực hiện.

Bảo đảm của `finally` là **quy tắc luồng điều khiển Java khi thực thi còn tiếp tục**, không phải cơ chế phục hồi giao dịch bền vững. Các yêu cầu như ghi dữ liệu an toàn sau crash cần chiến lược khác.

## 3. `final`: modifier được kiểm tra khi biên dịch

`final` có ý nghĩa tùy theo nơi xuất hiện, nhưng đều nhằm giới hạn một số phép thay đổi:

- **Biến/field/parameter `final`:** không thể gán lại sau khi đã được gán giá trị theo luật definite assignment.
- **Phương thức `final`:** không thể bị override (hoặc hidden đối với những trường hợp phương thức static tương ứng) ở lớp con.
- **Lớp `final`:** không thể được kế thừa.
- **Tham số `catch` đơn có thể khai báo `final`:** không được gán lại biến tham chiếu đã bắt. Riêng tham số multi-catch được ngôn ngữ coi là final.

`final` **không tự đóng tài nguyên, không giữ lỗi khỏi lan truyền, không tạo `try` hoặc `catch`**.

### 3.1. Biến cục bộ `final`

~~~java
final int maxRetries = 3;
System.out.println(maxRetries); // 3

// Không biên dịch nếu bỏ chú thích:
// maxRetries = 4;
~~~

Biến được gán một lần thì không thể gán lại. Một biến cục bộ `final` chưa được khởi tạo ngay ở khai báo có thể được gán **một lần trên mỗi đường điều khiển hợp lệ** mà compiler xác nhận:

~~~java
final int limit;
if (premiumUser) {
    limit = 100;
} else {
    limit = 20;
}
// Từ đây limit đã được gán; không thể gán lại.
// premiumUser là biến boolean ở ngữ cảnh bao ngoài.
~~~

Điều kiện là cả hai nhánh không làm biến nhận hai lần gán trên cùng đường thực thi. Compiler áp dụng quy tắc **definite assignment**; không phải “cứ có chữ `final` thì phải có giá trị ngay ở dòng khai báo”.

### 3.2. `final` với tham chiếu đối tượng không làm đối tượng bất biến

~~~java
final StringBuilder builder = new StringBuilder("A");
builder.append("B");            // Hợp lệ: đổi trạng thái đối tượng.
System.out.println(builder);   // AB

// Không biên dịch:
// builder = new StringBuilder("C");
~~~

`final` bảo vệ **biến `builder` khỏi được gán sang tham chiếu khác**. Nó không cấm gọi phương thức làm đổi trạng thái của đối tượng được tham chiếu.

Tương tự, `final List<String> items = new ArrayList<>();` không tự biến `items` thành danh sách bất biến; `items.add("x")` vẫn có thể hợp lệ. Nếu cần tính bất biến, thiết kế API của đối tượng cũng phải bảo đảm điều đó (ví dụ dùng giá trị immutable, defensive copy hoặc các collection bất biến phù hợp).

Phân biệt:
- **`final` reference:** không thể gán lại biến tham chiếu.
- **Immutable object:** bản thân đối tượng không cho thay đổi trạng thái quan sát được sau khi tạo.
- **Unmodifiable view:** cấm thao tác sửa qua một view, nhưng dữ liệu nền có thể vẫn thay đổi bởi nơi khác tùy implementation.

Ba khái niệm này không đồng nghĩa.

### 3.3. `final` field, constructor và giá trị khởi tạo

~~~java
class Order {
    private final long id;

    Order(long id) {
        this.id = id;
    }

    long id() {
        return id;
    }
}
~~~

Một instance field `final` có thể được khởi tạo tại chỗ hoặc gán trong đường khởi tạo/constructor theo luật Java. Trường hợp trên, mỗi `Order` được tạo thành công có `id` được gán đúng một lần.

Với `static final`:

~~~java
class Defaults {
    static final int MAX_SIZE = 100;
    static final String APP_NAME = "Training";
}
~~~

`static final` là một cách thông dụng để diễn đạt các hằng/giá trị cấu hình cấp lớp. Nhưng **không phải mọi `static final` đều là compile-time constant**; ví dụ `static final StringBuilder BUFFER = new StringBuilder();` có tham chiếu final nhưng đối tượng vẫn mutable. Các biến hằng theo ngôn ngữ có tiêu chí riêng về kiểu primitive/`String` và constant expression.

### 3.4. `final` class và method

~~~java
final class ImmutableTag {
    private final String value;

    ImmutableTag(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    String value() {
        return value;
    }
}
~~~

`final class ImmutableTag` cấm viết lớp con `extends ImmutableTag`. Tuy nhiên, bản thân việc khai báo `final class` **không tự đảm bảo bất biến**: ví dụ một lớp final vẫn có thể chứa mutable field.

Phương thức final:

~~~java
class BaseService {
    public final String version() {
        return "1.0";
    }
}

class ChildService extends BaseService {
    // Không thể override method version().
}
~~~

Compiler ngăn lớp con định nghĩa một phương thức override `version()` theo chữ ký tương ứng. Khác với `finally`, `final` không thực hiện câu lệnh nào khi phương thức kết thúc.

## 4. Ví dụ Java 17+ hoàn chỉnh kết hợp `final` và `finally`

Tạo tệp `FinalAndFinallyDemo.java`:

~~~java
public class FinalAndFinallyDemo {
    static final class Receipt {
        private final int id;
        private final StringBuilder notes = new StringBuilder();

        Receipt(int id) {
            this.id = id;
        }

        final String label() {
            return "R-" + id;
        }

        void append(String text) {
            notes.append(text);
        }

        String notes() {
            return notes.toString();
        }
    }

    static int process(boolean fail) {
        try {
            System.out.println("Trong try");
            if (fail) {
                throw new IllegalStateException("xử lý lỗi");
            }
            return 7;
        } catch (IllegalStateException ex) {
            System.out.println("Trong catch: " + ex.getMessage());
            return -1;
        } finally {
            System.out.println("Trong finally");
        }
    }

    public static void main(String[] args) {
        final Receipt receipt = new Receipt(17);
        receipt.append("A");
        receipt.append("B");
        System.out.println("Receipt: " + receipt.label() + " / " + receipt.notes());
        System.out.println("Thành công: " + process(false));
        System.out.println("Thất bại: " + process(true));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FinalAndFinallyDemo.java
java FinalAndFinallyDemo
~~~

Stdout chính xác:

~~~text
Receipt: R-17 / AB
Trong try
Trong finally
Thành công: 7
Trong try
Trong catch: xử lý lỗi
Trong finally
Thất bại: -1
~~~

**Giải thích:**

1. `Receipt` là lớp `final`, nên không có lớp con hợp lệ. Field `id` là `final`, được gán trong constructor, còn `label()` là phương thức `final`, không thể override.
2. Biến `receipt` trong `main` là **tham chiếu final**. Bạn không được gán `receipt = new Receipt(...)` ở phần còn lại của phương thức, nhưng vẫn được gọi `receipt.append(...)`, làm thay đổi đối tượng `StringBuilder` bên trong. Vì thế đầu ra là `AB`.
3. Khi `process(false)` chạy, `try` chuẩn bị trả về `7`. **`finally` thực thi trước khi lời gọi hoàn tất**, nên `Trong finally` xuất hiện trước `Thành công: 7`.
4. Khi `process(true)` chạy, `try` ném `IllegalStateException`, `catch` in thông báo và chuẩn bị trả về `-1`. Khối `finally` vẫn được thực hiện trước khi `main` in `Thất bại: -1`.
5. `final` trên biến/lớp/method **không quyết định** `finally` có chạy hay không. Hai từ khóa kiểm soát hai khía cạnh độc lập.

### Một lỗi biên dịch xác nhận ý nghĩa của `final`

Tệp `InvalidChild.java` sau đây **cố ý không biên dịch**:

~~~java
final class NonExtendable { }
class InvalidChild extends NonExtendable { }
~~~

Khi chạy `javac InvalidChild.java`, compiler báo lỗi chứa thông tin tương tự:

~~~text
error: cannot inherit from final NonExtendable
~~~

Lỗi được phát hiện **ở thời điểm biên dịch**; nó không liên quan tới ngoại lệ runtime, `try`, `catch` hay `finally`.

## 5. `finalize()`: phương thức cũ liên quan tới vòng đời đối tượng

`finalize()` là một **phương thức instance** được định nghĩa trên `java.lang.Object`. Trong cơ chế finalization lịch sử, một đối tượng có override `finalize()` có thể được hệ thống gọi khi đối tượng đã trở nên không còn được truy cập bình thường, trước khi bộ nhớ có thể được thu hồi theo quy tắc của cơ chế đó.

Chữ ký truyền thống:

~~~java
// Minh họa API cũ; KHÔNG khuyến nghị dùng.
@Override
protected void finalize() throws Throwable {
    try {
        // Logic finalizer cũ, không đáng tin để giải phóng tài nguyên.
    } finally {
        super.finalize();
    }
}
~~~

Đoạn trên là **phần thân phương thức minh họa đặt trong một lớp**, không phải chương trình chạy độc lập; có thể phát sinh cảnh báo deprecation tùy phiên bản JDK. Không viết mới kiểu thiết kế này.

Những điều cần biết:

- `finalize` là **tên phương thức**, khác với từ khóa `final` và `finally`. Có dấu `()`, có thể được override trong một số lớp cũ và có quy tắc truy cập/exception của phương thức.
- Finalization **không đồng nghĩa với garbage collection**: GC quyết định quản lý và thu hồi bộ nhớ; finalizer là cơ chế callback cũ được gắn với một số đối tượng khi đủ điều kiện.
- **Không có đảm bảo thời điểm thực hiện `finalize()`, cũng không có đảm bảo nó sẽ chạy trước khi chương trình kết thúc.** `System.gc()` chỉ là yêu cầu/hint và không biến finalization thành một lịch trình xác định.
- Một finalizer có thể không được gọi nếu đối tượng vẫn được tham chiếu, JVM dừng sớm hoặc hệ thống finalization bị vô hiệu hóa. Dựa vào nó để đóng file/socket/connection dễ làm rò rỉ tài nguyên.
- Ngoại lệ chưa bắt phát sinh trong finalizer không được xử lý như lỗi thông thường do lời gọi ứng dụng thực hiện; theo hợp đồng finalization lịch sử, nó không cung cấp một kênh báo lỗi đáng tin cho luồng gọi. Vì vậy finalizer không phải nơi thích hợp để xử lý lỗi nghiệp vụ.
- Finalizers có rủi ro về hiệu năng, bảo mật, hành vi khó dự đoán và **object resurrection** (đối tượng được đưa trở lại trạng thái có thể truy cập). Điều này làm vòng đời và điều kiện race trở nên phức tạp.

**Trạng thái theo phiên bản Java:** `Object.finalize()` đã được đánh dấu deprecated từ Java 9. JEP 421 đưa ra việc **deprecate finalization for removal trong JDK 18** và định hướng loại bỏ cơ chế này trong tương lai. Vì bài học ưu tiên Java 17+, cần phân biệt **deprecated ở Java 17** với mốc **for-removal gắn với JDK 18**. Dù đang dùng phiên bản vẫn cung cấp API, lập trình viên nên tránh viết code mới dựa vào finalization.

Không nên gọi trực tiếp `someObject.finalize()` để “kích hoạt GC”. Nếu một phương thức có thể truy cập được và được gọi thủ công, đó chỉ là một lời gọi phương thức Java bình thường trong ngữ cảnh ấy; nó **không buộc GC thu hồi đối tượng** và có thể làm cleanup bị thực thi sai thời điểm/nhiều lần.

## 6. Vì sao không dùng `finalize()` để thay `finally`?

Giả sử code cần mở một tài nguyên hệ điều hành như tệp, socket hoặc kết nối cơ sở dữ liệu. Điều bạn cần là **đóng tài nguyên khi đã dùng xong**, không phải đợi khi đối tượng có thể được GC thu hồi.

| Vấn đề | `finally` / `try-with-resources` | `finalize()` |
| --- | --- | --- |
| Thời điểm liên quan | Khi rời phạm vi `try` đã quy định | Không xác định; tùy điều kiện vòng đời đối tượng và runtime |
| Có nằm trong đường thực thi do code gọi chủ động không? | Có | Không phải đường điều khiển thông thường của caller |
| Có thể lập luận thứ tự các bước cleanup? | Có, theo quy tắc `try` và resource close | Không đáng tin để quản lý thứ tự tài nguyên |
| Có phù hợp cho `AutoCloseable`? | Ưu tiên `try-with-resources` | Không |
| Nếu cleanup thất bại? | Có thể bắt/lan truyền; `try-with-resources` hỗ trợ suppressed exceptions | Không có đường xử lý lỗi đáng tin cho caller |
| Khuyến nghị cho code mới | Có | Không |

`finally` chạy khi rời cấu trúc `try` (theo các điều kiện thực thi đã nêu). Finalization không gắn với thời điểm một lời gọi phương thức dùng xong tài nguyên. Mặc dù tên giống nhau, **chúng không có quan hệ kế thừa chức năng và không thể dùng thay thế**.

Một điểm thực tế: **`finally` viết thủ công cũng không phải luôn là cách tốt nhất để đóng tài nguyên**. Đối với `AutoCloseable`, ưu tiên `try-with-resources` vì Java tự đóng và có cơ chế giữ suppressed exception khi thân `try` và `close()` đều ném lỗi.

## 7. Ví dụ Java 17+: `try-with-resources` thay vì finalizer

Tạo tệp `FinallyResourceDemo.java`:

~~~java
public class FinallyResourceDemo {
    static class Resource implements AutoCloseable {
        Resource() {
            System.out.println("Mở tài nguyên");
        }

        void work(boolean fail) {
            System.out.println("Đang xử lý");
            if (fail) {
                throw new IllegalStateException("lỗi tác vụ");
            }
        }

        @Override
        public void close() {
            System.out.println("Đóng tài nguyên");
        }
    }

    static void run(boolean fail) {
        try (Resource resource = new Resource()) {
            resource.work(fail);
        } catch (IllegalStateException ex) {
            System.out.println("Bắt lỗi: " + ex.getMessage());
        } finally {
            System.out.println("Finally của run");
        }
    }

    public static void main(String[] args) {
        run(false);
        run(true);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FinallyResourceDemo.java
java FinallyResourceDemo
~~~

Stdout chính xác:

~~~text
Mở tài nguyên
Đang xử lý
Đóng tài nguyên
Finally của run
Mở tài nguyên
Đang xử lý
Đóng tài nguyên
Bắt lỗi: lỗi tác vụ
Finally của run
~~~

**Diễn giải:**

1. `Resource implements AutoCloseable` khai báo cách đóng tài nguyên bằng `close()`. Đây là một hợp đồng **chủ động và dự đoán được** ở cuối phạm vi sử dụng tài nguyên.
2. Lượt `run(false)`: `work` thành công → `close()` được gọi tự động → không có `catch` → `finally` in thông báo kết thúc.
3. Lượt `run(true)`: `work` ném `IllegalStateException` → tài nguyên được đóng **trước khi** `catch` của cấu trúc chạy → `catch` in thông báo → `finally` in dòng cuối.
4. Chương trình không cần override `finalize()`, không cần `System.gc()`, không phụ thuộc việc GC có thu hồi đối tượng trong khoảng thời gian nào.

Đối với code sản phẩm, `AutoCloseable` và `try-with-resources` là hướng chính để quản lý tài nguyên phải đóng. Nếu muốn tùy biến hành vi dọn dẹp, đặt nó vào `close()` có hợp đồng rõ ràng thay vì trong finalizer.

## 8. Các tình huống dễ nhầm về `finally`

### 8.1. `return` trong `try` không bỏ qua `finally`

~~~java
// Đoạn minh họa nằm trong lớp.
static int compute() {
    int number = 5;
    try {
        return number;
    } finally {
        number = 9;
    }
}
~~~

Phương thức trả **5**, nếu `finally` hoàn tất bình thường. Biểu thức `return number` được đánh giá trước khi `finally` thực thi; việc gán biến cục bộ trong `finally` không tính lại kết quả. Nếu kiểu trả về là tham chiếu tới một đối tượng mutable, thay đổi chính đối tượng trong `finally` có thể được người gọi quan sát — phải phân biệt với gán lại biến tham chiếu.

### 8.2. `return` hoặc `throw` trong `finally` có thể che lỗi

~~~java
// Ví dụ cố ý cho thấy anti-pattern.
static int unsafe() {
    try {
        throw new IllegalStateException("lỗi ban đầu");
    } finally {
        return 42; // Che lỗi ban đầu; KHÔNG nên viết như vậy.
    }
}
~~~

Nếu gọi `unsafe()`, nó trả về **42** thay vì ném `IllegalStateException`. Trường hợp `finally` ném ngoại lệ khác cũng có thể thay thế ngoại lệ đang lan truyền. Tránh `return` trong `finally`; khi cleanup có thể lỗi, cân nhắc quản lý bằng `try-with-resources` hoặc một chính sách bảo toàn lỗi chính thích hợp.

### 8.3. `final` không bảo vệ khỏi ngoại lệ

~~~java
final String text = null;
System.out.println(text.length()); // Vẫn ném NullPointerException.
~~~

`final` chỉ ngăn gán lại biến `text`. Nó không bảo đảm khác `null`, không thay việc kiểm tra đầu vào, không sinh `catch` và không giải phóng tài nguyên. Cũng vậy, một lớp `final` có thể ném bất kỳ ngoại lệ hợp lệ nào mà code bên trong lớp tạo ra.

### 8.4. Có thể dùng `final` trong `catch`, nhưng đó không phải `finally`

~~~java
try {
    throw new IllegalArgumentException("sai");
} catch (final IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
}
~~~

Cách viết hợp lệ: biến tham số `ex` không được gán lại, song vẫn có thể dùng để đọc thông tin lỗi. Đây là cú pháp `final` trên tham số, **không phải khối `finally`**. Với multi-catch, tham số được xem là final theo quy tắc Java ngay cả khi không ghi từ khóa đó.

### 8.5. `finally` không làm thay đổi quan hệ `final` / override

Nếu bạn đánh dấu phương thức `final`, các lớp con không được override phương thức đó. Việc thêm `try/finally` bên trong phương thức không làm phương thức mất trạng thái `final`. Ngược lại, không có modifier `final` nào tự làm các khối `finally` bên trong phương thức hoạt động khác đi.

## 9. `final` và đa luồng: cần phân biệt với cleanup

Trong Java Memory Model, các `final` field có một số quy tắc đặc biệt giúp **an toàn khởi tạo** khi đối tượng được xây dựng đúng cách và tham chiếu không bị công bố sai trong lúc xây dựng. Tuy nhiên, **`final` không tự làm mọi phương thức thread-safe**.

Ví dụ, một field `final StringBuilder buffer` đảm bảo bản thân biến field không đổi tham chiếu sau khi gán, nhưng `StringBuilder` vẫn mutable và không được thiết kế cho truy cập cập nhật đồng thời không đồng bộ. Nếu nhiều luồng cùng gọi `buffer.append`, vẫn cần chiến lược đồng bộ hoặc dùng cấu trúc dữ liệu khác.

Điều này càng làm rõ ba tên:

- `final` liên quan đến ràng buộc khai báo và, với final fields, một số quy tắc hiển thị dữ liệu đã khởi tạo.
- `finally` liên quan đến thời điểm hoàn tất một vùng thực thi.
- `finalize()` là cơ chế vòng đời cũ và còn khó dự đoán hơn khi có nhiều luồng; nó không phải công cụ đồng bộ.

Không nên suy luận từ chữ *final* rằng dữ liệu, thao tác tài nguyên hay vòng đời đối tượng đã “an toàn cuối cùng” ở mọi nghĩa.

## 10. Khi cần dọn dẹp tài nguyên, nên chọn gì?

**Đối với tài nguyên đóng được:**

~~~java
// Đoạn minh họa trong phương thức có throws IOException.
try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(path)) {
    return reader.readLine();
}
~~~

Đây là code fragment; `path` là một `Path` ở ngữ cảnh chứa và phương thức phải xử lý hoặc khai báo `IOException`. `try-with-resources` đóng `reader` khi rời khối, kể cả khi đọc thất bại. Cơ chế này được thiết kế riêng cho tài nguyên `AutoCloseable`.

**Đối với công việc cuối không thuộc `AutoCloseable`:**

~~~java
// Đoạn minh họa trong phương thức.
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Đoạn trên giả định `lock` là đối tượng khóa hợp lệ và `updateSharedState()` đã được khai báo; nguyên tắc là khóa được thả ở `finally` khi phần thân hoàn tất hoặc ném lỗi. Với `Lock` trong `java.util.concurrent.locks`, đây là mẫu thường gặp. `unlock()` phải được gọi bởi luồng đang giữ khóa và chỉ sau khi `lock.lock()` thành công.

**Đối với cơ chế dự phòng quản lý tài nguyên cực kỳ chuyên biệt:** Java có `Cleaner` và các API tham chiếu của `java.lang.ref`. Chúng chỉ nên dùng nếu bạn hiểu vòng đời, tính bất định của cleanup và không thể biểu diễn trách nhiệm đóng trực tiếp. `Cleaner` không thay thế `close()` đúng lúc, và không nên tạo ấn tượng rằng nó cung cấp đảm bảo thời gian thực hoặc sẽ chạy trước khi JVM dừng.

**Không chọn `finalize()` cho code mới.** Nếu gặp finalizer trong hệ thống cũ, xác định tài nguyên nó đang quản lý, chuyển trách nhiệm cleanup sang cơ chế chủ động phù hợp, kiểm thử cả đường thành công và thất bại, rồi loại bỏ dần sự phụ thuộc vào finalization.

## 11. Phân biệt về cú pháp: ba tên không thay thế được

| Cách viết | Ý nghĩa/kết quả |
| --- | --- |
| `try { run(); } finally { cleanup(); }` | Hợp lệ: `finally` là khối thuộc cấu trúc `try`. |
| `final int n = 1;` | Hợp lệ: biến `n` không được gán lại. |
| `final class A { }` | Hợp lệ: lớp `A` không được kế thừa. |
| `final void m() { }` | Hợp lệ trong khai báo phương thức của lớp, tùy bối cảnh: không cho override. |
| `protected void finalize() throws Throwable { ... }` | Cú pháp override finalizer lịch sử, nhưng deprecated/không khuyến nghị. |
| `finally int x = 1;` | Sai: `finally` không phải modifier biến. |
| `try { run(); } final { cleanup(); }` | Sai: `final` không mở khối cleanup. |
| `finalize { cleanup(); }` | Sai: `finalize` không phải từ khóa của cấu trúc `try`. |
| `object.finally()` | Sai: `finally` là từ khóa, không thể dùng làm định danh phương thức. |
| `finalize()` thay cho `resource.close()` | Không phải cơ chế quản lý tài nguyên đáng tin và không bảo đảm GC đóng đúng lúc. |

Các đoạn có `...` trong bảng chỉ là cú pháp gợi ý, **không phải tệp Java độc lập có thể biên dịch**. Chỉ các ví dụ được ghi tên tệp và lệnh chạy là chương trình hoàn chỉnh.

## 12. Lỗi phổ biến khi học và sử dụng

| Nhầm lẫn | Vì sao sai? | Điều nên làm |
| --- | --- | --- |
| `final` là dạng viết ngắn của `finally` | Một từ khóa hạn chế gán/kế thừa, một từ khóa mở khối thuộc `try`. | Xem ngữ cảnh khai báo hay luồng xử lý ngoại lệ. |
| `finally` chỉ chạy khi có ngoại lệ | Khi `try` thành công, `finally` vẫn chạy trên đường rời cấu trúc. | Kiểm thử cả đường bình thường lẫn lỗi. |
| `finally` tự `catch` mọi lỗi | Lỗi chưa xử lý tiếp tục lan truyền sau `finally`, nếu `finally` hoàn tất bình thường. | Dùng `catch` khi cần xử lý lỗi. |
| Biến `final` tham chiếu tới object thì object không thể thay đổi | `final` ngăn gán lại biến, không tự cấm mutation của object. | Dùng đối tượng bất biến/defensive copy khi cần. |
| Lớp `final` chắc chắn immutable | Lớp không thể bị kế thừa vẫn có thể chứa trạng thái mutable. | Kiểm tra toàn bộ field và phương thức. |
| Phương thức `final` không thể ném ngoại lệ | Hạn chế override không liên quan việc ném `Throwable`. | Phân biệt hợp đồng phương thức với modifier. |
| `finalize()` được gọi ngay khi biến ra khỏi scope | Scope của biến không xác định được thời điểm hoặc khả năng GC/finalization. | Đóng tài nguyên chủ động. |
| `System.gc()` bảo đảm finalizer chạy | GC không phải lệnh hẹn giờ đáng tin cho finalization. | Không phụ thuộc finalizer để cleanup. |
| Dùng finalizer để đóng stream/connection | Thời điểm không xác định, dễ rò rỉ tài nguyên hoặc hành vi khó kiểm soát. | Dùng `AutoCloseable` và `try-with-resources`. |
| `return` trong `finally` vô hại | Có thể che `return` hoặc ngoại lệ đang chờ. | Tránh `return`/`throw` tùy tiện trong `finally`. |
| Dùng `finally` đóng tài nguyên nhưng bỏ qua lỗi từ `close()` | Ngoại lệ đóng có thể che lỗi chính. | Ưu tiên `try-with-resources` để giữ suppressed exception. |
| Gọi `finalize()` thủ công tương đương chạy GC | Chỉ là lời gọi phương thức (khi hợp lệ về truy cập), không ép GC thu hồi đối tượng. | Thiết kế API `close()` rõ ràng. |

## 13. Câu hỏi tự kiểm tra

1. **`finally` là từ khóa hay phương thức?** — Từ khóa mở khối thuộc cấu trúc `try`, thường để thực hiện công việc khi rời cấu trúc.
2. **`final` trên biến tham chiếu có ngăn gọi phương thức thay đổi đối tượng không?** — Không. Nó ngăn gán lại tham chiếu của biến.
3. **Có thể viết `class Child extends FinalClass` khi `FinalClass` được khai báo `final` không?** — Không, compiler từ chối.
4. **Một phương thức `final` có được chứa `try/catch/finally` không?** — Có; `final` không giới hạn cấu trúc xử lý ngoại lệ bên trong.
5. **`try` không ném lỗi thì `finally` có chạy không?** — Có, khi rời cấu trúc theo đường bình thường.
6. **Nếu `try` ném lỗi chưa được bắt, `finally` có xử lý xong lỗi không?** — Không; nó chạy rồi lỗi tiếp tục lan truyền nếu `finally` hoàn tất bình thường.
7. **`finalize()` có chắc chắn được gọi trước khi tiến trình kết thúc không?** — Không; không có bảo đảm đó.
8. **`Object.finalize()` đã deprecated ở mốc nào?** — Deprecated từ Java 9; JEP 421 đưa trạng thái deprecate-for-removal ở JDK 18.
9. **Muốn đóng một `BufferedReader`, nên ưu tiên `finalize()`, `final` hay `try-with-resources`?** — `try-with-resources` và `AutoCloseable`; hai lựa chọn kia không giải quyết việc đóng đúng lúc.
10. **Nếu `finally` có `return` và `try` đang ném lỗi, điều gì có thể xảy ra?** — `return` có thể thay thế đường thoát bằng ngoại lệ, khiến lỗi gốc bị che.

## 14. Tài liệu tham khảo chính thức

- [Java Language Specification 17 — §14.20, The `try` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): quy tắc thực hiện `try`, `catch` và `finally`.
- [Java Language Specification 17 — §4.12.4, `final` Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): biến `final`, definite assignment.
- [Java Language Specification 17 — §8.1.1.2, `final` Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): lớp `final` không thể có lớp con.
- [Java Language Specification 17 — §8.4.3.3, `final` Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.3.3): phương thức `final` và ghi đè.
- [Java SE 17 API — `java.lang.Object.finalize()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#finalize()): hợp đồng và tình trạng deprecated của phương thức.
- [OpenJDK JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): bối cảnh deprecate-for-removal từ JDK 18, rủi ro finalization và hướng thay thế.
- [Java SE 17 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): cơ chế đóng tài nguyên chủ động dùng với `try-with-resources`.

**Kết luận:** `finally` là khối thực thi khi rời `try`; `final` là modifier được compiler kiểm tra đối với biến, field, lớp và phương thức; `finalize()` là phương thức thuộc cơ chế finalization cũ, không nên dùng để dọn dẹp tài nguyên. Khi cần quản lý tài nguyên, chọn `try-with-resources`/`close()`; khi cần logic cuối cho một vùng thực thi, dùng `finally`; khi cần ràng buộc khai báo, dùng `final`.
