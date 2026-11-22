# Khai báo unchecked exception và vai trò tài liệu hóa trong Java

**Unchecked exception** là ngoại lệ thuộc nhánh `RuntimeException` hoặc `Error`, bao gồm cả các lớp con. Java **không bắt buộc** phương thức hoặc constructor phải liệt kê những ngoại lệ này trong mệnh đề `throws`, và cũng **không bắt buộc** mã gọi bắt hoặc khai báo chúng. Tuy vậy, một API vẫn có thể viết `throws IllegalArgumentException`, `throws IllegalStateException` hay tài liệu Javadoc `@throws` để diễn đạt những trường hợp thất bại mà người dùng API cần biết.

Bài học tập trung vào câu hỏi: **khi nào nên khai báo unchecked exception trong `throws`, khi nào nên mô tả bằng Javadoc và hợp đồng API, và những điều compiler thực sự kiểm tra là gì?** Những nội dung quan trọng gồm cách viết chữ ký phương thức/constructor, phân biệt quy tắc ngôn ngữ với khuyến nghị tài liệu hóa, công bố điều kiện gây lỗi, xử lý khi override và những rủi ro về thiết kế API.

## 1. Nhận diện unchecked exception chính xác

Trong Java, `Throwable` có hai nhánh lớn: `Exception` và `Error`. `RuntimeException` là lớp con của `Exception` nhưng được xếp vào nhóm **unchecked**; `Error` cùng các lớp con cũng là unchecked.

~~~text
Throwable
├── Error                                   unchecked
│   ├── AssertionError                      unchecked
│   ├── LinkageError                        unchecked
│   └── ...
└── Exception
    ├── IOException                         checked
    ├── SQLException                        checked
    ├── InterruptedException                checked
    └── RuntimeException                    unchecked
        ├── IllegalArgumentException        unchecked
        │   └── NumberFormatException       unchecked
        ├── IllegalStateException           unchecked
        ├── NullPointerException            unchecked
        ├── IndexOutOfBoundsException       unchecked
        └── ...
~~~

**Điều kiện phân loại:** mọi lớp con của `RuntimeException` và `Error` là unchecked. Các kiểu `Throwable` còn lại là checked. Không phải mọi lớp con của `Exception` đều là checked; `RuntimeException` là ngoại lệ cần nhớ.

Ví dụ về ý nghĩa của các unchecked exception thường thấy:

| Loại | Tình huống thường gặp | Người dùng API nên hiểu |
| --- | --- | --- |
| `IllegalArgumentException` | Đối số vi phạm quy tắc hợp đồng như giá trị âm không hợp lệ | Cần sửa đầu vào trước khi gọi |
| `IllegalStateException` | Đối tượng chưa khởi tạo xong, đã đóng hoặc đang ở trạng thái không cho phép thao tác | Cần kiểm tra vòng đời/trạng thái sử dụng |
| `NullPointerException` | Tham chiếu `null` bị dùng ở nơi cần đối tượng khác `null` | Cần tuân thủ quy ước nullability của API |
| `IndexOutOfBoundsException` | Chỉ số ngoài phạm vi dữ liệu | Cần giới hạn chỉ số hợp lệ |
| `NumberFormatException` | Chuỗi không chuyển được thành số theo cú pháp được yêu cầu | Cần kiểm tra hoặc xử lý dữ liệu đầu vào |
| `UnsupportedOperationException` | Một thao tác được biểu diễn trong API nhưng implementation không hỗ trợ | Cần chọn cách gọi hoặc implementation phù hợp |
| `Error` và các lớp con | Ví dụ một số lỗi nghiêm trọng của môi trường chạy hoặc liên kết lớp | Thông thường không được dùng làm cơ chế báo lỗi nghiệp vụ có thể phục hồi |

Việc phân loại checked/unchecked là thuộc tính **của kiểu ngoại lệ**, không phụ thuộc vào tên ngoại lệ, mức độ nghiêm trọng cụ thể, có `throws` trong chữ ký hay có thực sự phát sinh ở một lần chạy.

## 2. `throws` với unchecked exception hoàn toàn hợp lệ

Cú pháp của mệnh đề `throws` giống nhau với checked và unchecked exception:

~~~java
// Đoạn minh họa là các khai báo đặt trong một lớp.
public static int parseAge(String raw)
        throws NumberFormatException {
    return Integer.parseInt(raw);
}

public static int parseAgeWithoutDeclaration(String raw) {
    return Integer.parseInt(raw);
}
~~~

Hai phương thức đều có thể ném `NumberFormatException`. Chúng chỉ khác ở chỗ phương thức thứ nhất **nêu rõ kiểu ngoại lệ trong chữ ký**. Vì `NumberFormatException` là unchecked, cả hai lời gọi đều có thể được viết **mà không có `try/catch` hoặc `throws` ở phía người gọi**.

~~~java
// Đoạn minh họa bên trong một phương thức.
int a = parseAge("17");
int b = parseAgeWithoutDeclaration("25");
System.out.println(a + b); // 42
~~~

Nếu truyền `"mười bảy"` vào một trong hai lời gọi, `Integer.parseInt` có thể ném `NumberFormatException`. Java vẫn thực hiện cơ chế runtime tìm `catch` gần nhất và lan truyền ngoại lệ như những kiểu `Throwable` khác.

Constructor cũng được phép khai báo unchecked exception:

~~~java
class UserAge {
    private final int value;

    UserAge(int value) throws IllegalArgumentException {
        if (value < 0) {
            throw new IllegalArgumentException("tuổi âm");
        }
        this.value = value;
    }
}
~~~

Lời gọi `new UserAge(-1)` có thể ném `IllegalArgumentException`; tuy nhiên đoạn mã gọi `new UserAge(20)` **không bị compiler bắt buộc bắt** kiểu ngoại lệ này. Khai báo `throws IllegalArgumentException` ở constructor chủ yếu là một tín hiệu cho người đọc và công cụ xem chữ ký API.

Không có yêu cầu phải “đăng ký” mọi unchecked exception có thể phát sinh; Java cũng không tự chèn chúng vào mệnh đề `throws`.

## 3. Khác biệt cốt lõi với checked exception

Xét hai trường hợp:

~~~java
import java.io.IOException;

// Hai phương thức minh họa đặt trong một lớp.
static void readFile() throws IOException {
    throw new IOException("không đọc được");
}

static void validate() throws IllegalArgumentException {
    throw new IllegalArgumentException("dữ liệu sai");
}
~~~

Quy tắc ở nơi gọi:

- **Gọi `readFile()`:** vì `IOException` là checked, lời gọi phải nằm trong đường xử lý `catch` phù hợp hoặc phương thức chứa lời gọi phải khai báo `throws IOException` (hay kiểu cha hợp lệ), trừ khi ngữ cảnh đã xử lý khác theo luật Java.
- **Gọi `validate()`:** vì `IllegalArgumentException` là unchecked, mã gọi không cần `catch` và không cần `throws IllegalArgumentException`, dù phương thức `validate` đã khai báo nó.
- **Lúc runtime:** cả hai loại đều đi qua cùng cơ chế `throw`, tìm `catch`, chạy `finally` và lan truyền nếu chưa được xử lý.

Ví dụ này không tạo ra các nhóm “unchecked nhưng có khai báo sẽ thành checked”. Thêm `throws RuntimeException` không thay đổi cơ chế kiểm tra của compiler.

| Khía cạnh | Checked exception | Unchecked exception |
| --- | --- | --- |
| Ví dụ | `IOException`, `SQLException` | `IllegalArgumentException`, `IllegalStateException` |
| Compiler yêu cầu `catch` hoặc `throws` khi có thể thoát? | Có, theo quy tắc kiểm tra ngoại lệ | Không |
| Có được ghi trong `throws`? | Có | Có |
| Có được mô tả bằng Javadoc `@throws`? | Có | Có |
| Gọi phương thức có `throws` có tự ném lỗi? | Không | Không |
| Có truyền qua ngăn xếp lời gọi nếu thực sự bị ném? | Có | Có |

## 4. Vì sao vẫn cần tài liệu hóa unchecked exception?

Khi một API công bố điều kiện gây ra `IllegalArgumentException` hay `IllegalStateException`, người gọi biết cách **sử dụng API đúng**, phòng tránh lỗi, xử lý đầu vào và định vị lỗi khi chạy.

Ví dụ lời khai báo `void transfer(int amount)` chưa nói rõ giá trị nào được phép. Tài liệu tốt nên làm rõ:

- **Điều kiện kích hoạt:** `amount <= 0` có hợp lệ không? Chuyển tiền khi tài khoản đã đóng thì sao?
- **Loại ngoại lệ:** lỗi đối số trả về `IllegalArgumentException` hay lỗi trạng thái trả về `IllegalStateException`?
- **Trạng thái khi thất bại:** dữ liệu có thay đổi một phần hay thao tác thất bại trước khi thay đổi?
- **Cách sử dụng đúng:** những giá trị, trạng thái hoặc bước chuẩn bị mà người gọi cần bảo đảm.

Mục tiêu của tài liệu hóa là biến những kỳ vọng quan trọng thành **hợp đồng đọc hiểu và kiểm thử được**. Nó không thay thế kiểm tra đầu vào trong code và cũng không khiến compiler xác minh rằng thông điệp Javadoc luôn đúng.

Đối với thư viện dùng bởi bên ngoài, Javadoc mô tả các tình huống lỗi có chủ đích thường quan trọng hơn việc liệt kê một cách máy móc mọi `RuntimeException` từ thư viện phụ thuộc hoặc lỗi bất ngờ do bug. Một API không thể cam kết rằng sẽ không bao giờ có bất kỳ unchecked exception nào khác; không cần tạo một bảng liệt kê vô hạn.

## 5. Hai cách công bố: mệnh đề `throws` và Javadoc `@throws`

Có thể viết **cả hai**, hoặc chỉ viết Javadoc.

### 5.1. Khai báo trong chữ ký

~~~java
public void deposit(int amount)
        throws IllegalArgumentException, IllegalStateException {
    // Triển khai của một API.
}
~~~

Phần `throws` này có thể nhìn thấy qua chữ ký nguồn và metadata phản chiếu (reflection) của phương thức. Nhưng nó **chỉ liệt kê kiểu**, không giải thích tình huống nào gây ra lỗi. Vì đó là unchecked exception, nó không buộc người gọi bắt hoặc khai báo.

### 5.2. Mô tả điều kiện bằng Javadoc

~~~java
/**
 * Nạp số tiền dương vào tài khoản đang hoạt động.
 *
 * @param amount số tiền cần nạp; phải lớn hơn 0
 * @throws IllegalArgumentException nếu amount nhỏ hơn hoặc bằng 0
 * @throws IllegalStateException nếu tài khoản đã bị đóng
 */
public void deposit(int amount) {
    // Triển khai của một API.
}
~~~

**`@throws` là thẻ tài liệu Javadoc**, không phải từ khóa Java trong chữ ký. Nó có thể mô tả unchecked exception **ngay cả khi không xuất hiện mệnh đề `throws`**. Thẻ `@exception` là bí danh lịch sử của `@throws`, nhưng nên dùng `@throws` nhất quán.

Thông thường, khi tài liệu hóa một ngoại lệ unchecked, thông tin có giá trị nhất là **điều kiện cụ thể** khiến ngoại lệ xảy ra. Chỉ viết `@throws IllegalArgumentException có thể ném IllegalArgumentException` gần như không giúp người dùng.

### 5.3. Kết hợp cả hai

~~~java
/**
 * Cập nhật số tiền theo quy tắc của API.
 *
 * @param amount số tiền dương
 * @throws IllegalArgumentException nếu amount không dương
 * @throws IllegalStateException nếu tài khoản đã bị khóa
 */
public void deposit(int amount)
        throws IllegalArgumentException, IllegalStateException {
    // Triển khai của một API.
}
~~~

Sử dụng `throws` trong chữ ký là tùy chọn đối với unchecked exception; chọn có hoặc không dựa trên phong cách nhất quán của API. **Thẻ `@throws` vẫn nên ghi rõ điều kiện lỗi quan trọng**, dù có liệt kê kiểu trong chữ ký hay không.

Chú ý quy tắc ngôn ngữ khác nhau: với checked exception, tài liệu Javadoc `@throws IOException` **không thay cho** khai báo `throws IOException` cần thiết để mã nguồn biên dịch. Javadoc không biến kiểu checked thành unchecked, và mệnh đề `throws` không thay thế phần diễn giải điều kiện trong tài liệu.

## 6. Ví dụ Java 17+ hoàn chỉnh: API có hợp đồng lỗi rõ ràng

Lưu đoạn mã sau thành `UncheckedDocumentationDemo.java`:

~~~java
public class UncheckedDocumentationDemo {
    static final class Counter {
        private int value;
        private boolean closed;

        Counter(int initialValue) {
            if (initialValue < 0) {
                throw new IllegalArgumentException("giá trị đầu âm");
            }
            value = initialValue;
        }

        /**
         * Tăng giá trị khi bộ đếm đang mở.
         *
         * @param delta số nguyên dương cần cộng
         * @throws IllegalArgumentException nếu delta không dương hoặc gây tràn số
         * @throws IllegalStateException nếu bộ đếm đã đóng
         */
        void add(int delta) throws IllegalArgumentException, IllegalStateException {
            if (delta <= 0) {
                throw new IllegalArgumentException("delta phải dương");
            }
            if (closed) {
                throw new IllegalStateException("bộ đếm đã đóng");
            }
            if (value > Integer.MAX_VALUE - delta) {
                throw new IllegalArgumentException("tăng gây tràn số");
            }
            value += delta;
        }

        int value() {
            return value;
        }

        void close() {
            closed = true;
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter(2);
        counter.add(3);
        System.out.println("Giá trị: " + counter.value());

        try {
            counter.add(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Đối số: " + ex.getMessage());
        }

        counter.close();
        try {
            counter.add(1);
        } catch (IllegalStateException ex) {
            System.out.println("Trạng thái: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 UncheckedDocumentationDemo.java
java UncheckedDocumentationDemo
~~~

Stdout chính xác:

~~~text
Giá trị: 5
Đối số: delta phải dương
Trạng thái: bộ đếm đã đóng
~~~

**Điểm cần hiểu từ chương trình:**

1. Constructor `Counter(int initialValue)` kiểm tra tiền điều kiện về giá trị ban đầu. Nó không viết `throws IllegalArgumentException`, nhưng vẫn được phép ném ngoại lệ unchecked khi đối số sai.
2. `add(int delta)` khai báo hai unchecked exception trong mệnh đề `throws`, đồng thời giải thích từng điều kiện bằng Javadoc `@throws`.
3. `main` gọi `counter.add(3)` **mà không có `try/catch`**; compiler chấp nhận vì các kiểu đã khai báo đều là unchecked.
4. Hai khối `try/catch` tiếp theo là lựa chọn xử lý có chủ đích để trình diễn nhánh thất bại, không phải yêu cầu bắt buộc từ compiler.
5. Kiểm tra đầu vào và trạng thái diễn ra trước khi cập nhật `value`, nên các lỗi được kiểm tra ở đây không làm tăng dở dang giá trị. Đây là tính chất thiết kế hữu ích có thể nêu trong hợp đồng API.
6. `value > Integer.MAX_VALUE - delta` tránh tràn số nguyên trên đường cập nhật sau khi đã xác nhận `delta > 0`; điều kiện tràn được công bố cùng `IllegalArgumentException`.

Để thử riêng trường hợp constructor, có thể viết trong một phương thức:

~~~java
// Minh họa trong mã gọi có quyền truy cập lớp Counter.
try {
    new UncheckedDocumentationDemo.Counter(-1);
} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage()); // giá trị đầu âm
}
~~~

Đoạn này cho thấy constructor không cần khai báo `throws IllegalArgumentException` vẫn có thể thực sự ném nó. Trong mã thư viện, constructor cũng nên được tài liệu hóa bằng `@throws` nếu điều kiện đầu vào là phần quan trọng của API.

## 7. Sinh tài liệu từ thẻ `@throws`

Công cụ `javadoc` trong JDK chuyển các chú thích tài liệu `/** ... */` thành tài liệu API. Thẻ `@throws` đóng góp phần mô tả ngoại lệ, thường xuất hiện trong khu vực **Throws** của phương thức/constructor khi phần tử đó được đưa vào tài liệu.

Với tệp từ mục 6, có thể tạo tài liệu bằng:

~~~bash
javadoc -private -encoding UTF-8 -charset UTF-8 -d docs UncheckedDocumentationDemo.java
~~~

Lệnh `-private` giúp đưa cả lớp lồng và thành viên không công khai trong ví dụ vào đầu ra; khi tài liệu hóa thư viện thực tế, hãy chọn phạm vi hiển thị phù hợp với API mà người dùng cần. Tệp HTML được tạo trong thư mục `docs`; kết quả có thể gồm các trang lớp/thành viên và khu vực mô tả ngoại lệ của `add(int)`.

Trong dự án thực, thường dùng các plugin build (Gradle/Maven) để sinh Javadoc nhất quán, nhưng quy tắc viết `@throws` vẫn như nhau. Công cụ `javadoc` **không tự sửa code** để thực thi mọi điều kiện tài liệu; đoạn kiểm tra trong phương thức phải đúng với điều kiện được mô tả.

Các điểm cần đối chiếu trước khi phát hành API:

- Mỗi `@throws` mô tả được **một điều kiện kích hoạt cụ thể**, không chỉ lặp lại tên kiểu.
- Danh sách tài liệu phản ánh các ngoại lệ mà caller có thể dự đoán từ hợp đồng, thay vì mọi lỗi runtime có thể xảy ra do bug hoặc môi trường.
- Nếu điều kiện lỗi thay đổi khi refactor, cập nhật Javadoc và kiểm thử cùng mã triển khai.
- Tài liệu ở interface/lớp cha nên thống nhất với cam kết từ lớp triển khai, tránh mô tả những bảo đảm mà mọi implementation không thể giữ.

## 8. Có cần `throws RuntimeException` hoặc `throws Exception` cho chắc không?

Thông thường **không cần và không hữu ích** nếu mục tiêu chỉ là nói “phương thức có thể gặp một số lỗi runtime”.

~~~java
// Hợp lệ nhưng không mô tả được loại thất bại cụ thể.
static void process(String input) throws RuntimeException {
    // ...
}
~~~

`RuntimeException` là kiểu cha rộng của nhiều ngoại lệ unchecked, nên khai báo như trên không buộc caller xử lý và cũng không tiết lộ điều kiện hợp đồng cụ thể. Thay vào đó, nếu có một quy tắc đầu vào rõ ràng, ghi Javadoc cho ngoại lệ cụ thể sẽ giá trị hơn.

`throws Exception` còn rộng hơn: nó là checked exception trong phân cấp Java, vì vậy nếu API công bố `throws Exception`, lời gọi thường bị kiểm tra theo kiểu checked này. Không nên thêm `throws Exception` chỉ để “bao tất cả unchecked exception” vì nó thay đổi nghĩa vụ biên dịch và làm suy giảm khả năng đọc hợp đồng.

Cũng không nên viết `throws Throwable` hay `throws Error` như một thói quen. Mệnh đề `throws Error` là hợp lệ vì `Error` là unchecked, nhưng `Error` không phải kiểu thích hợp để biểu thị lỗi đầu vào hoặc trạng thái nghiệp vụ thông thường.

**Quy tắc thực hành:** nếu unchecked exception có điều kiện rõ và quan trọng với người sử dụng, hãy ghi loại lỗi cùng điều kiện trong Javadoc; việc lặp tên kiểu ở mệnh đề `throws` là một lựa chọn về phong cách và mức độ nổi bật của chữ ký.

## 9. Override, interface và `throws` unchecked exception

Với **checked exception**, phương thức override không được thêm loại checked mới hoặc rộng hơn so với phương thức cha/interface. Với **unchecked exception**, hạn chế này **không áp dụng**: override có thể khai báo hoặc ném thêm `RuntimeException` và lớp con, ngay cả khi giao diện không ghi chúng.

Chương trình chạy được `UncheckedOverrideDemo.java`:

~~~java
import java.util.Locale;

interface TextTransformer {
    /**
     * Chuyển chữ đầu vào.
     * @throws IllegalArgumentException nếu văn bản trống
     */
    String transform(String raw);
}

class StrictTransformer implements TextTransformer {
    @Override
    public String transform(String raw) throws IllegalArgumentException {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("văn bản trống");
        }
        return raw.trim().toUpperCase(Locale.ROOT);
    }
}

public class UncheckedOverrideDemo {
    public static void main(String[] args) {
        TextTransformer transformer = new StrictTransformer();
        System.out.println(transformer.transform("  java  "));
        try {
            transformer.transform(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 UncheckedOverrideDemo.java
java UncheckedOverrideDemo
~~~

Stdout chính xác:

~~~text
JAVA
Lỗi: văn bản trống
~~~

`TextTransformer.transform` không khai báo `throws`, nhưng có thẻ `@throws IllegalArgumentException` mô tả tiền điều kiện. `StrictTransformer.transform` thêm `throws IllegalArgumentException` hợp lệ vì đây là unchecked exception. Đối tượng được sử dụng qua kiểu interface `TextTransformer`; compiler vẫn không bắt caller xử lý kiểu này.

Đối với **chính sách API**, việc một override được phép phát sinh unchecked exception **không đồng nghĩa nên tùy tiện đưa ra lỗi không phù hợp hợp đồng**. Một implementation nên tôn trọng ý nghĩa của phương thức cha, tài liệu và kỳ vọng của caller. Nếu một phương thức trong interface chấp nhận mọi chuỗi kể cả rỗng, implementation tự ý từ chối chuỗi rỗng có thể phá vỡ tính thay thế ngay cả khi Java vẫn cho biên dịch.

Nếu cùng một ngoại lệ được công bố ở interface và implementation, có thể dùng cơ chế kế thừa tài liệu Javadoc theo quy tắc của công cụ, nhưng cần kiểm tra trang tài liệu thực tế. Với điều kiện đặc thù implementation, mô tả thêm ở implementation để người dùng biết khác biệt.

## 10. Hợp đồng API: document tiền điều kiện, hậu điều kiện và trạng thái

Đối với unchecked exception, trọng tâm thường là **lỗi sử dụng API hoặc trạng thái không phù hợp**, hơn là một tình huống lỗi bên ngoài bắt buộc caller phục hồi.

Giả sử bạn thiết kế:

~~~java
/**
 * Gửi một yêu cầu khi client còn mở.
 *
 * @param request yêu cầu khác null
 * @throws NullPointerException nếu request là null
 * @throws IllegalStateException nếu client đã đóng
 */
void send(Request request);
~~~

Đây là **chữ ký minh họa** (cần định nghĩa `Request` và bối cảnh lớp). Caller hiểu rằng cần bảo đảm `request != null` và vòng đời client còn hiệu lực. Trong phần triển khai, bạn có thể dùng `Objects.requireNonNull(request, "request")` để chủ động kiểm tra `null` và ném `NullPointerException` rõ ràng:

~~~java
// Đoạn minh họa trong một phương thức có tham số request.
java.util.Objects.requireNonNull(request, "request");
~~~

Đối với input khác `null` nhưng sai miền giá trị, `IllegalArgumentException` thường phù hợp hơn; đối với đối tượng không ở trạng thái cho phép thao tác, `IllegalStateException` thường rõ nghĩa hơn. Tuy nhiên các tên kiểu không thay thế được **quy định rõ điều kiện**. Những API khác nhau có thể chọn kiểu khác nhau miễn nhất quán và được tài liệu hóa.

Một số nguyên tắc viết hợp đồng:

1. Nêu ngắn gọn thao tác và các điều kiện thành công ở `@param` và phần mô tả.
2. Dùng `@throws` cho điều kiện lỗi có chủ đích mà caller thực sự cần tránh hoặc có thể xử lý.
3. Nếu phương thức phải bảo đảm “không thay đổi trạng thái khi đầu vào không hợp lệ”, hãy triển khai để bảo đảm đó đúng và thử với các trường hợp lỗi.
4. Nếu API có thể thất bại do môi trường (I/O, kết nối, quyền truy cập), cân nhắc ngoại lệ checked hoặc mô hình kết quả theo thiết kế API cụ thể; đừng tự động bọc mọi checked exception thành unchecked.
5. Giữ tên thông điệp và loại lỗi nhất quán để người dùng đọc log dễ hơn, nhưng không phụ thuộc vào việc so sánh chuỗi thông điệp để quyết định nhánh xử lý.

## 11. Ghi vào `throws` có giúp reflection hay IDE nhận diện không?

Có. Mệnh đề `throws` là một phần metadata ngoại lệ được khai báo của phương thức/constructor và có thể được đọc bằng các API reflection, ví dụ:

~~~java
// Đoạn minh họa, đặt trong phương thức có throws ReflectiveOperationException.
Class<?>[] declared =
        UncheckedDocumentationDemo.Counter.class
                .getDeclaredMethod("add", int.class)
                .getExceptionTypes();
~~~

Với mã `Counter.add` ở mục 6, danh sách `getExceptionTypes()` bao gồm `IllegalArgumentException` và `IllegalStateException` như chúng được khai báo ở chữ ký. Nó **không đồng nghĩa với danh sách tất cả ngoại lệ runtime có thể xuất hiện**, và **không đọc trực tiếp phần văn bản của thẻ Javadoc `@throws`**.

IDE và công cụ phân tích mã có thể dùng chữ ký cùng tài liệu nguồn để hiển thị hợp đồng. Tuy nhiên, `throws` không cung cấp điều kiện chi tiết, còn Javadoc thường nằm ở mã nguồn hoặc tài liệu sinh ra. Vì vậy hai kênh thông tin bổ trợ nhau:

- **`throws`**: kiểu ngoại lệ được khai báo trong chữ ký, có thể phản chiếu.
- **`@throws`**: mô tả điều kiện cho con người và tài liệu API, không biến thành ràng buộc biên dịch mới.

Nếu API của bạn chỉ ghi `@throws IllegalArgumentException` mà không có mệnh đề `throws`, `getExceptionTypes()` không thể suy ra loại đó từ Javadoc.

## 12. Ảnh hưởng đến tương thích và thay đổi API

Vì unchecked exception không bị ràng buộc bởi catch-or-declare, **việc thêm `throws IllegalStateException` trong chữ ký không làm caller buộc thêm `catch`**. Nhưng thay đổi hành vi thực tế — ví dụ một phiên bản mới bắt đầu từ chối đối số vốn được chấp nhận — vẫn có thể làm hỏng ứng dụng sử dụng thư viện.

Các ví dụ cần thận trọng:

- Trước đây `send(null)` có ý nghĩa “không làm gì”, nhưng phiên bản sau ném `NullPointerException`: đây là thay đổi hợp đồng hành vi dù mã cũ vẫn biên dịch.
- `read()` trước đây cho phép gọi sau `close()`, nay ném `IllegalStateException`: cần đánh giá khả năng tương thích và cập nhật tài liệu/test.
- Một lớp thay `IllegalArgumentException` bằng `IllegalStateException` cho cùng một trường hợp: caller có thể đang bắt riêng một trong hai loại để phục hồi; nên cân nhắc ổn định ngữ nghĩa ngoại lệ.
- Thêm `throws IOException` (checked) vào API thì khác: caller hiện hữu có thể nhận lỗi biên dịch nếu chưa xử lý kiểu checked mới.

Không nên nhầm “không có lỗi biên dịch” với “không có thay đổi đáng kể đối với người dùng API”. Hợp đồng tài liệu hóa là một phần quan trọng của thiết kế công khai.

## 13. Lỗi thường gặp

| Nhầm lẫn/sai sót | Vì sao không đúng | Cách cải thiện |
| --- | --- | --- |
| Nghĩ unchecked exception không được khai báo trong `throws` | Java cho phép khai báo các kiểu con `RuntimeException`/`Error`. | Có thể ghi khi hữu ích; compiler vẫn không yêu cầu caller bắt. |
| Nghĩ chỉ cần thêm `throws IllegalArgumentException` là caller buộc `catch` | Đây là unchecked exception, không áp dụng nghĩa vụ catch-or-declare. | Viết điều kiện `@throws` và xử lý ở caller khi có chiến lược phù hợp. |
| Nghĩ `@throws` bắt buộc tương ứng với mệnh đề `throws` | Đối với unchecked exception, Javadoc có thể tài liệu hóa cả khi chữ ký không khai báo. | Phân biệt Javadoc với cú pháp ngôn ngữ. |
| Ghi `@throws RuntimeException nếu xảy ra lỗi` | Điều kiện quá mơ hồ, khó dùng để viết mã đúng. | Ghi loại cụ thể và tình huống như `delta <= 0`. |
| Liệt kê mọi exception do JVM và thư viện phụ thuộc có thể ném | Tài liệu nhiễu, khó bảo trì, dễ cam kết sai. | Chỉ công bố những ngoại lệ thuộc hợp đồng và có giá trị với caller. |
| Dùng `throws Exception` chỉ để “nhắc rằng có lỗi runtime” | Gây nghĩa vụ xử lý checked `Exception`, làm chữ ký quá rộng. | Bỏ khai báo rộng; dùng `@throws` cụ thể nếu cần. |
| Thêm unchecked exception ở override rồi cho rằng chắc chắn đúng hợp đồng | Ngôn ngữ cho phép nhưng hành vi có thể phá cam kết interface. | Giữ tiền điều kiện và hậu điều kiện hợp lý với hợp đồng đã công bố. |
| Tài liệu ghi một điều kiện, code ném lỗi trong điều kiện khác | Người dùng API không thể dựa vào tài liệu. | Đồng bộ code, Javadoc và bài kiểm thử điều kiện biên. |
| Dùng `Error` như lỗi nghiệp vụ bình thường | `Error` thường biểu thị tình trạng đặc biệt nghiêm trọng, không dành cho yêu cầu nhập liệu. | Ưu tiên exception phù hợp theo ý nghĩa API. |
| Ghi log, nuốt hoặc bọc tùy tiện mọi unchecked exception | Có thể giấu bug hoặc mất chuỗi nguyên nhân. | Xử lý nơi có giải pháp thực sự; khi bọc nên giữ `cause`. |

## 14. Tự kiểm tra

1. **`NumberFormatException` là checked hay unchecked?** — Unchecked vì nó thuộc nhánh `IllegalArgumentException → RuntimeException`.
2. **Gọi `void save() throws IllegalStateException` có bắt buộc thêm `try/catch` không?** — Không; đây là unchecked exception.
3. **Nếu một API không ghi `throws IllegalArgumentException`, nó có được `throw new IllegalArgumentException(...)` không?** — Có.
4. **Javadoc `@throws IllegalArgumentException` có tác động tới kiểm tra ngoại lệ của compiler không?** — Không; nó mô tả hợp đồng API cho người đọc.
5. **Viết `@throws` cho unchecked exception nhưng bỏ nó khỏi chữ ký `throws` có hợp lệ không?** — Có.
6. **Phương thức override có thể thêm `throws IllegalArgumentException` dù interface không khai báo không?** — Có về mặt ngôn ngữ; vẫn cần bảo đảm hợp đồng hành vi.
7. **Vì sao `throws Exception` không phải cách tốt để tài liệu hóa một `IllegalArgumentException`?** — `Exception` là checked và quá rộng, gây nghĩa vụ biên dịch và làm mờ hợp đồng.
8. **Khi nào `@throws IllegalStateException` hữu ích?** — Khi có điều kiện trạng thái cụ thể, như gọi phương thức sau khi đối tượng đã đóng.
9. **Reflection `getExceptionTypes()` có suy ra thẻ `@throws` không?** — Không; nó đọc các kiểu được khai báo trong chữ ký, không phải văn bản Javadoc.
10. **Thêm unchecked exception mới vào hành vi API có thể phá tính tương thích không?** — Có về mặt hành vi dù mã nguồn của caller vẫn có thể biên dịch.

## Tài liệu đối chiếu

- [Java Language Specification 17 — §11.1.1, The Kinds of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.1.1): phân loại checked và unchecked exception.
- [Java Language Specification 17 — §11.2, Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): các kiểu ngoại lệ được compiler yêu cầu bắt hoặc khai báo.
- [Java Language Specification 17 — §8.4.6, Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): mệnh đề `throws` trong phương thức.
- [Java Language Specification 17 — §8.4.8.3, Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): giới hạn checked exception khi override.
- [Javadoc Tool — `@throws` và `@exception` Tags](https://docs.oracle.com/en/java/javase/17/javadoc/javadoc.html): cú pháp tài liệu mô tả ngoại lệ.
- [Java SE 17 API — `Executable.getExceptionTypes()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html#getExceptionTypes()): kiểu ngoại lệ đã được khai báo trong chữ ký.

**Ghi nhớ:** với unchecked exception, mệnh đề `throws` là tùy chọn theo luật Java; thẻ Javadoc `@throws` giải thích **khi nào và vì sao** lỗi xảy ra. Một API tốt dùng chúng có chủ đích để công bố điều kiện sử dụng, đồng thời thực thi đúng hợp đồng trong mã nguồn.
