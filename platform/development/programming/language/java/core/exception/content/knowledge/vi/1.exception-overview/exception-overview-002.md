# Phân biệt lỗi biên dịch, thất bại khi chạy và kết quả nghiệp vụ trong Java

Một chương trình Java có thể **không biên dịch được**, **biên dịch thành công nhưng thất bại khi chạy**, hoặc **chạy đúng và trả về kết quả nghiệp vụ không như người dùng mong muốn**. Ba tình huống này khác nhau về thời điểm xuất hiện, nguyên nhân, cách biểu diễn và trách nhiệm xử lý. Trong chủ đề Java Core – Exception, phân biệt chúng là bước đầu tiên để quyết định khi nào cần sửa mã nguồn, khi nào xử lý exception và khi nào chỉ cần kiểm tra một kết quả bình thường.

## 1. Ba loại tình huống nhìn từ vòng đời chương trình

| Góc nhìn | Lỗi biên dịch (compile-time error) | Thất bại khi chạy (runtime failure) | Kết quả nghiệp vụ (business outcome) |
| --- | --- | --- | --- |
| Thời điểm | Khi `javac` kiểm tra/biên dịch mã nguồn | Khi chương trình đang thực thi | Khi nghiệp vụ đưa ra một quyết định trong lúc chạy |
| Ví dụ | Gán `String` vào `int`; dùng biến không khai báo; không xử lý checked exception | `NullPointerException`; tệp cấu hình không đọc được; kết nối cơ sở dữ liệu thất bại | Đơn hàng hết hàng; đăng nhập sai mật khẩu; hồ sơ không đạt điều kiện |
| Có tạo được bản biên dịch mới? | Không, đối với phần nguồn đang lỗi | Có thể có; lỗi xuất hiện trong lúc thực thi | Có; chương trình hoàn toàn có thể chạy đúng |
| Java có bắt buộc ném exception? | Không: trình biên dịch báo lỗi | Không phải mọi thất bại đều ném exception; nhiều lỗi có exception hoặc `Error` | Không: có thể biểu diễn bằng giá trị trả về hoặc trạng thái |
| Phản ứng chính | Sửa mã, kiểu dữ liệu, cú pháp, khai báo hoặc phụ thuộc | Chẩn đoán nguyên nhân, khôi phục nếu khả thi, hoặc chuyển lỗi qua ranh giới thích hợp | Xử lý nhánh nghiệp vụ và thông báo phù hợp cho người dùng |
| Có luôn là bug? | Thường là lỗi mã/thiết lập biên dịch cần sửa | Có thể là bug, dữ liệu sai, sự cố môi trường hoặc tình huống dự liệu trước | Không: “hết hàng” có thể là quyết định hoàn toàn đúng của hệ thống |

Cần phân biệt thêm **kết quả nghiệp vụ** với **lỗi logic**: nếu hệ thống phải trừ 10 điểm nhưng lại trừ 100 điểm mà không ném exception, chương trình vẫn có thể chạy tới cuối. Đây là bug về tính đúng đắn khi chạy, không phải một kết quả nghiệp vụ hợp lệ chỉ vì không có exception.

Một chu trình giản lược:

1. Viết mã nguồn `.java` và chạy `javac`. Nếu việc biên dịch thất bại, sửa mã hoặc cấu hình biên dịch trước khi có thể chạy bản mới.
2. Chạy bytecode bằng `java`. Trong lúc chạy có thể phát sinh exception, lỗi môi trường, treo chương trình, hoặc cho ra giá trị sai.
3. Nếu hoạt động kỹ thuật thành công, các quy tắc nghiệp vụ vẫn có thể trả về “được chấp nhận”, “bị từ chối”, “không còn hàng”, “chưa đủ điều kiện”…

Một ứng dụng thực tế có thể biên dịch thành công, xử lý hàng nghìn yêu cầu bình thường, rồi chỉ một yêu cầu cụ thể gặp lỗi runtime. Ngược lại, một yêu cầu bị từ chối do quy tắc nghiệp vụ có thể được xử lý thành công hoàn toàn.

## 2. Lỗi biên dịch: chương trình bị từ chối trước khi chạy

Trình biên dịch Java kiểm tra cú pháp và nhiều quy tắc tĩnh: tên biến, kiểu dữ liệu, khả năng truy cập thành viên, một số đường đi trả về, và nghĩa vụ xử lý/khai báo **checked exception**. Ví dụ tệp `CompileDemo.java`:

```java
public class CompileDemo {
    public static void main(String[] args) {
        int quantity = "3"; // Sai: String không tự chuyển thành int
        System.out.println(quantity);
    }
}
```

Chạy:

```bash
javac CompileDemo.java
```

Lệnh thất bại với thông báo về **kiểu dữ liệu không tương thích**; nội dung và cách trình bày chẩn đoán phụ thuộc phiên bản `javac`. Đây không phải `ClassCastException` trong lúc chạy. Lỗi xuất hiện vì trình biên dịch đã phát hiện phép gán không hợp lệ. Một cách sửa là dùng `int quantity = 3;`; nếu giá trị thực sự đến từ văn bản, việc chuyển đổi như `Integer.parseInt(text)` lại có thể gặp exception **khi chạy**, nếu văn bản không phải số nguyên hợp lệ.

Một tình huống liên quan đến exception:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class CheckedExample {
    static String load(Path file) throws IOException {
        return Files.readString(file);
    }

    static void show() {
        String data = load(Path.of("config.txt")); // Lỗi biên dịch
        System.out.println(data);
    }
}
```

`Files.readString` có thể ném `IOException`, là checked exception. Phương thức `show()` phải **bắt** nó bằng `try/catch` hoặc **khai báo** `throws IOException` (hay kiểu cha phù hợp). Nếu sửa chữ ký thành `static void show() throws IOException`, mã có thể biên dịch; điều đó **không bảo đảm** tệp tồn tại hoặc việc đọc sẽ thành công. `throws` chỉ làm rõ hợp đồng lan truyền exception, không xử lý nguyên nhân ở runtime.

**Giới hạn của trình biên dịch:** biên dịch thành công không chứng minh nghiệp vụ đúng, không bảo đảm dữ liệu đầu vào hợp lệ, không bảo đảm kết nối mạng khả dụng và không loại bỏ `NullPointerException`. Ngược lại, cảnh báo biên dịch không đồng nghĩa với lỗi khiến `javac` phải dừng. Lỗi do không tìm thấy thư viện ở compile classpath hoặc phiên bản JDK không tương thích cũng có thể làm build thất bại, dù không phải lỗi logic trong từng câu lệnh Java.

## 3. Thất bại khi chạy: mã hợp lệ nhưng thao tác không hoàn tất như dự định

Ví dụ tệp `RuntimeDemo.java`:

```java
public class RuntimeDemo {
    public static void main(String[] args) {
        System.out.println("Bắt đầu chuyển đổi");
        int quantity = Integer.parseInt("abc");
        System.out.println("Số lượng: " + quantity);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 RuntimeDemo.java
java RuntimeDemo
```

`javac` biên dịch thành công. Khi chạy, **stdout** in:

```text
Bắt đầu chuyển đổi
```

Sau đó `Integer.parseInt("abc")` ném `NumberFormatException` vì chuỗi không biểu diễn một số nguyên thập phân hợp lệ. Không có `catch` nào xử lý nên exception thoát khỏi `main`; JVM in thông tin exception và stack trace ra **stderr**, và câu lệnh in “Số lượng” không được thực hiện. Không cần dự đoán từng dòng stack trace vì chi tiết có thể khác theo phiên bản JDK.

Các dạng thất bại runtime thường gặp:

- **Lỗi dữ liệu hoặc tiền điều kiện:** `NumberFormatException`, `IllegalArgumentException`, nhiều `NullPointerException`. Nguyên nhân có thể nằm ở dữ liệu không mong đợi hoặc bug của bên gọi.
- **I/O và tài nguyên bên ngoài:** `IOException` khi đọc/ghi, lỗi kết nối, timeout. Cần biết thao tác có thể thử lại an toàn hay không.
- **Trạng thái/cạnh tranh:** `IllegalStateException`, tranh chấp tài nguyên, deadlock, race condition. Một deadlock có thể khiến chương trình treo **mà không ném exception**.
- **Giới hạn môi trường:** hết bộ nhớ có thể dẫn đến `OutOfMemoryError`; `Error` thường biểu thị vấn đề mà luồng nghiệp vụ thông thường không thể tự xử lý an toàn.
- **Lỗi logic âm thầm:** phép tính tràn số nguyên `int` thông thường không tự ném exception; chương trình vẫn có thể trả về giá trị sai.

Trong Java, `Throwable` là gốc của `Exception` và `Error`. Hai nhóm thường gặp trong `Exception` là **checked exception** (ví dụ `IOException`) và **unchecked exception** (các lớp con của `RuntimeException`, ví dụ `NumberFormatException`). Các lớp con của `Error` cũng không phải checked exception. Không nên suy luận rằng “checked = luôn khôi phục được” hoặc “unchecked = luôn là bug”: khả năng khôi phục do ngữ cảnh và hợp đồng phương thức quyết định.

`try/catch` chỉ hoạt động khi chương trình đã chạy tới một exception tương ứng. Nó không bắt lỗi cú pháp hay lỗi kiểu mà `javac` từ chối; cũng không tự phát hiện deadlock, kết quả sai nhưng không ném exception, hoặc mọi sự cố nghiêm trọng của JVM.

## 4. Kết quả nghiệp vụ: bị từ chối vẫn có thể là xử lý thành công

Hãy xét thao tác đặt hàng. Nếu khách yêu cầu 7 sản phẩm nhưng kho chỉ còn 5, “không đủ hàng” là **trạng thái dự kiến** của quy tắc nghiệp vụ. Nó không đòi hỏi một lỗi Java; phía gọi cần biết phải gợi ý giảm số lượng, báo hết hàng hay dừng quy trình mua. Tương tự: mật khẩu sai, đơn vượt hạn mức, phiếu giảm giá hết hạn, tài khoản chưa đủ điều kiện là các nhánh nghiệp vụ có thể dự liệu.

Một cách biểu diễn rõ ràng là trả về đối tượng kết quả có mã trạng thái. Tệp `CheckoutDemo.java` dưới đây chạy độc lập bằng Java 17+:

```java
public class CheckoutDemo {
    enum Status {
        PLACED, OUT_OF_STOCK, INVALID_QUANTITY
    }

    record CheckoutResult(Status status, String message) {}

    static CheckoutResult placeOrder(int quantity, int stock) {
        // stock do hệ thống quản lý: giá trị âm vi phạm tiền điều kiện kỹ thuật.
        if (stock < 0) {
            throw new IllegalArgumentException("Tồn kho không được âm");
        }

        // quantity từ yêu cầu của người dùng: từ chối theo quy tắc nghiệp vụ.
        if (quantity <= 0) {
            return new CheckoutResult(
                    Status.INVALID_QUANTITY, "Số lượng phải lớn hơn 0");
        }
        if (quantity > stock) {
            return new CheckoutResult(
                    Status.OUT_OF_STOCK, "Không đủ tồn kho");
        }
        return new CheckoutResult(Status.PLACED, "Đặt hàng thành công");
    }

    public static void main(String[] args) {
        System.out.println(placeOrder(2, 5));
        System.out.println(placeOrder(7, 5));
        System.out.println(placeOrder(0, 5));

        try {
            placeOrder(1, -1);
        } catch (IllegalArgumentException e) {
            System.out.println("Lỗi dữ liệu hệ thống: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 CheckoutDemo.java
java CheckoutDemo
```

**stdout chính xác** trong môi trường hiển thị UTF-8:

```text
CheckoutResult[status=PLACED, message=Đặt hàng thành công]
CheckoutResult[status=OUT_OF_STOCK, message=Không đủ tồn kho]
CheckoutResult[status=INVALID_QUANTITY, message=Số lượng phải lớn hơn 0]
Lỗi dữ liệu hệ thống: Tồn kho không được âm
```

Điểm cần chú ý:

- Cả ba kết quả đầu đều trở về bình thường từ `placeOrder`, kể cả `OUT_OF_STOCK` và `INVALID_QUANTITY`. Bên gọi xử lý qua `status()` mà không cần `catch`.
- Ở ví dụ này, `stock` là dữ liệu nội bộ đã được giả định hợp lệ. Giá trị âm biểu thị **vi phạm hợp đồng của bên gọi/dữ liệu hệ thống**, nên `IllegalArgumentException` là một lựa chọn có chủ ý. Nếu tồn kho âm vốn là tình huống nghiệp vụ được cho phép trong một hệ thống khác, cách phân loại và biểu diễn sẽ khác.
- Việc dùng `record` chỉ giúp tạo một loại dữ liệu kết quả ngắn gọn, bất biến ở mức tham chiếu của các thành phần ví dụ; không phải quy định rằng mọi kết quả nghiệp vụ đều phải dùng `record`.
- Chạy thành công không đồng nghĩa với “đặt hàng thành công”: **thao tác kỹ thuật** thành công có thể trả về **quyết định nghiệp vụ** bị từ chối.

Nếu màn hình nhập số lượng là nơi người dùng có thể gõ sai, dữ liệu không hợp lệ thường nên được xác thực và trả về kết quả có cấu trúc. Nếu API thư viện quy định đối số bắt buộc là số dương và bên lập trình gọi sai hợp đồng, `IllegalArgumentException` lại có thể phù hợp. **Nguồn dữ liệu, kỳ vọng và hợp đồng giữa các tầng** quyết định cách xử lý; không chỉ riêng kiểu exception.

## 5. Không đồng nhất exception với “lỗi nghiệp vụ”

Tên của một lớp không tự xác định cách hệ thống diễn giải nó. Ví dụ `NumberFormatException` là một exception xảy ra lúc chạy, nhưng:

- Khi người dùng nhập `"abc"` vào ô “số lượng”, tầng nhập liệu có thể bắt lỗi chuyển đổi và trả thông báo “Số lượng phải là số nguyên” như **kết quả xác thực dự kiến**.
- Khi dịch vụ đọc `"abc"` từ một tệp cấu hình bắt buộc phải chứa số, cùng exception có thể chỉ ra **dữ liệu cấu hình hỏng**, khiến thao tác kỹ thuật thất bại.
- Nếu mã đã xác thực dữ liệu là số trước đó nhưng vẫn parse sai, có thể tồn tại **bug hoặc sai lệch hợp đồng giữa các tầng**.

Tương tự, “không tìm thấy bản ghi” có thể là kết quả bình thường của chức năng tìm kiếm, hoặc là lỗi bất thường nếu ứng dụng đang cập nhật một bản ghi vừa xác nhận tồn tại. Có dự án dùng `Optional`, mã trạng thái, `Result`/`Either` hoặc một **domain exception** cho trường hợp này; điều quan trọng là hợp đồng nhất quán và bên gọi biết chính xác cách xử lý.

Một exception nghiệp vụ được định nghĩa riêng **vẫn là exception Java phát sinh lúc chạy** khi được ném; nó không biến thành “lỗi biên dịch”, cũng không chứng minh chương trình gặp sự cố kỹ thuật. Cần phân biệt **cơ chế truyền tín hiệu** (throw/catch hay return) với **ý nghĩa sự kiện** (kết quả dự kiến hay thất bại bất thường).

## 6. Chọn cách biểu diễn và vị trí xử lý

Các lựa chọn thông dụng:

| Tình huống | Biểu diễn thường hợp lý | Lý do |
| --- | --- | --- |
| Điều kiện nghiệp vụ dự kiến: hết hàng, giảm giá hết hạn, thiếu điều kiện | Kết quả có kiểu, trạng thái hoặc nhánh domain rõ ràng | Bên gọi phải ra quyết định bình thường |
| Thao tác tìm kiếm có thể không có dữ liệu | `Optional<T>` nếu chỉ cần có/không; loại kết quả riêng nếu cần lý do | Tránh dùng exception như nhánh điều khiển thông thường |
| Đối số từ lập trình viên vi phạm tiền điều kiện API | `IllegalArgumentException` hoặc `NullPointerException` theo hợp đồng | Báo bên gọi đã sử dụng API sai |
| Không đọc được tệp, gọi dịch vụ ngoài thất bại | Exception phù hợp, kèm ngữ cảnh; xử lý ở nơi có chiến lược | Lỗi không thể được bỏ qua như một kết quả thành công |
| Vi phạm bất biến nội bộ hoặc trạng thái không được phép | `IllegalStateException` hay loại exception tương ứng | Báo chương trình đang ở trạng thái không hợp lệ |
| Nghiệp vụ cần cả thành công lẫn nhiều lý do từ chối | `enum` + `record`, sealed hierarchy hoặc kiểu kết quả rõ ràng | Giúp gọi hàm xử lý đầy đủ các nhánh |

Không có nguyên tắc “mọi thất bại phải ném exception” hoặc “không bao giờ dùng domain exception”. Khi từ chối là nhánh thường xuyên, việc dùng giá trị kết quả thường dễ đọc, dễ kiểm thử và ít khiến người gọi tưởng đó là lỗi hạ tầng. Khi phương thức không thể thực hiện hợp đồng hoặc muốn dừng nhanh luồng xử lý bất thường, exception có thể phù hợp. Nếu chọn domain exception, cần ghi rõ loại nào được phép xảy ra, nơi bắt, cách chuyển thành phản hồi và liệu hệ thống có cần rollback.

Với checked exception, `catch` khi tầng hiện tại thực sự có thể khôi phục, chọn đường thay thế hoặc chuyển thành lỗi có ý nghĩa. Nếu tầng hiện tại không đủ thông tin, có thể khai báo `throws` (nếu hợp đồng cho phép) hay chuyển ngoại lệ kèm nguyên nhân:

```java
try {
    return Files.readString(path);
} catch (IOException cause) {
    throw new IllegalStateException("Không thể nạp cấu hình: " + path, cause);
}
```

Đây là **đoạn minh họa bên trong một phương thức** đã có biến `path` kiểu `Path` và `import` cần thiết; không phải chương trình độc lập. Lưu `cause` giúp chẩn đoán ngọn nguồn. Việc chuyển sang unchecked exception chỉ phù hợp nếu tầng này không thể xử lý tại chỗ và hợp đồng của API cho phép; không dùng nó chỉ để né nghĩa vụ xử lý checked exception.

Không bắt rồi bỏ qua exception, trả `null` hay trả “thành công” giả:

```java
// Phản ví dụ: lỗi đọc dữ liệu bị che giấu.
try {
    return Files.readString(path);
} catch (IOException e) {
    return ""; // Không biết tệp thực sự rỗng hay đã đọc thất bại.
}
```

Nếu chuỗi rỗng là phương án dự phòng được **quy định rõ và an toàn** trong nghiệp vụ, có thể dùng; nếu không, cách này làm mất sự khác biệt giữa dữ liệu hợp lệ và sự cố.

## 7. Ranh giới tầng và cách báo cho người dùng

Trong ứng dụng nhiều tầng, nơi exception **phát sinh** có thể khác nơi quyết định **phản hồi**:

1. **Tầng nhập liệu:** xác thực dữ liệu người dùng; trả danh sách lỗi trường nếu đó là nhánh dự kiến.
2. **Tầng nghiệp vụ:** thực hiện quy tắc; trả kết quả `PLACED`/`OUT_OF_STOCK` hoặc domain outcome tương đương.
3. **Tầng tích hợp:** phát hiện lỗi tệp, mạng, cơ sở dữ liệu; ném exception có đủ ngữ cảnh và không làm lộ thông tin nhạy cảm.
4. **Tầng giao tiếp/API:** chuyển kết quả/exception thành phản hồi giao thức, log thông tin chẩn đoán cần thiết, giữ nguyên ý nghĩa nghiệp vụ.

Ví dụ trong một HTTP API (chỉ là gợi ý thiết kế, **không phải quy tắc của Java**):

| Sự kiện | Phản hồi có thể phù hợp |
| --- | --- |
| Người dùng gửi số lượng không hợp lệ | `400 Bad Request`, kèm mô tả lỗi nhập liệu |
| Đặt hàng bị từ chối vì thiếu hàng | `409 Conflict` hoặc mã trạng thái domain trong phản hồi, tùy hợp đồng API |
| Tìm theo ID nhưng không có kết quả | `404 Not Found` nếu URI đại diện tài nguyên không tồn tại |
| Kho dữ liệu tạm thời không truy cập được | `503 Service Unavailable` nếu đây là tình trạng tạm thời, hoặc mã 5xx phù hợp |
| Bug nội bộ chưa xử lý được | `500 Internal Server Error`, tránh lộ stack trace cho người dùng |

`400`, `404`, `409`, `500` chỉ mô tả hợp đồng của dịch vụ HTTP; **chúng không phải các loại exception Java**. API có thể trả mã 4xx dù Java không ném exception; ngược lại một exception được bắt và chuyển thành lỗi nhập liệu phù hợp cũng không cần khiến ứng dụng dừng.

Đừng lấy mọi exception làm `500` một cách máy móc, cũng đừng tự động biến mọi lỗi kỹ thuật thành “nghiệp vụ từ chối”. Một phản hồi có thể mang mã lỗi cho người dùng nhưng cần giữ dấu vết kỹ thuật nội bộ để điều tra.

## 8. Quy trình chẩn đoán thực tế

Khi thấy thông báo “lỗi”, hãy đi theo thứ tự câu hỏi sau:

1. **`javac`/build có thất bại không?** Đọc file, dòng, tên ký hiệu, kiểu dữ liệu, API, import, cấu hình build. Nếu lỗi xuất hiện trước khi chạy bản mới, xử lý ở pha biên dịch.
2. **Chương trình có chạy và có exception/`Error` không?** Đọc **loại exception**, message, `cause` và stack trace từ điểm lỗi tới lời gọi. Xác định đầu vào, trạng thái và tài nguyên tại thời điểm xảy ra.
3. **Không có exception nhưng hành vi vẫn sai?** So sánh kết quả thực với đặc tả, kiểm thử ca biên, dữ liệu và phép tính. Đây có thể là lỗi logic hoặc lỗi đồng bộ; không được mặc định là kết quả nghiệp vụ hợp lệ.
4. **Có trả một trạng thái từ chối dự kiến không?** Đối chiếu quy tắc nghiệp vụ: chẳng hạn `OUT_OF_STOCK` với `requested > available` là kết quả đúng. Xử lý ở bên gọi bằng lời nhắn hoặc hành động tiếp theo.
5. **Sự kiện được chuyển đổi giữa các tầng ra sao?** Một exception phát sinh bên trong có thể đã được bắt và chuyển thành kết quả; theo dõi cả nguyên nhân ban đầu và hợp đồng bên ngoài trước khi phân loại.

Đặc biệt với lỗi runtime: thử lại thường có ý nghĩa khi lỗi là **tạm thời** và thao tác **an toàn để lặp lại** (cần cân nhắc idempotency, giao dịch và side effect). Không tự động retry một đơn hàng khi không biết lần trước đã ghi thành công hay chưa. Một kết quả `OUT_OF_STOCK` sẽ không biến thành thành công chỉ vì thực hiện lại ngay nhiều lần.

## 9. Kiểm thử ba lớp hành vi khác nhau

- **Kiểm tra biên dịch:** chạy build/`javac` để phát hiện sai cú pháp, sai kiểu, thiếu thư viện, checked exception chưa xử lý. Build thành công là điều kiện cần nhưng chưa đủ.
- **Kiểm thử tình huống runtime:** cho dữ liệu hoặc môi trường gây lỗi đã dự kiến (số không hợp lệ, tệp vắng mặt, dịch vụ ngoài tạm ngắt) và xác minh exception/đường xử lý/ghi log phù hợp. Phân biệt exception mong đợi trong test với exception thoát ra làm test thất bại.
- **Kiểm thử nghiệp vụ:** xác minh nhiều nhánh bình thường như đủ hàng, hết hàng, số lượng bằng 0, dữ liệu ở ranh giới; so sánh trạng thái và thông báo, không chỉ kiểm tra “không ném exception”.
- **Kiểm thử tính đúng đắn:** kiểm tra các giá trị tính toán, tình huống cạnh biên và side effect, vì kết quả sai có thể không tạo exception.

Với `CheckoutDemo`, ba lời gọi đầu bao phủ ba nhánh kết quả; lời gọi có `stock = -1` kiểm tra tiền điều kiện bị vi phạm. Trong sản phẩm thực, cần thêm test cho số lượng sát ranh giới tồn kho, các bất biến và tính nhất quán khi nhiều yêu cầu đặt hàng đồng thời.

## 10. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Biên dịch qua nghĩa là code không có lỗi.” | Java chỉ kiểm tra được một phần; lỗi logic, tài nguyên và dữ liệu xuất hiện khi chạy. |
| “Lỗi biên dịch có thể sửa bằng `try/catch`.” | `try/catch` chỉ dùng cho exception tại runtime; phải sửa mã/cấu hình để `javac` chấp nhận. |
| “Cứ `throws` là đã xử lý lỗi.” | `throws` khai báo khả năng lan truyền; bên gọi hoặc ranh giới trên cùng vẫn cần chính sách xử lý. |
| “Đơn bị từ chối nghĩa là server bị lỗi.” | Nếu từ chối theo quy tắc dự kiến, đó có thể là kết quả nghiệp vụ đúng. |
| “Bất cứ exception nào cũng là bug lập trình.” | Một số exception do I/O, dữ liệu không hợp lệ, hoặc điều kiện môi trường; đánh giá theo hợp đồng. |
| “Không có exception tức là thành công.” | Chương trình có thể treo, tính sai hoặc trả trạng thái từ chối hợp lệ. |
| “Bắt `Exception` rồi trả `true` là an toàn.” | Che giấu lỗi, làm mất nguyên nhân và phát tín hiệu thành công giả. |
| “Dùng `catch (Throwable)` cho mọi tình huống.” | Có thể nuốt cả `Error` nghiêm trọng; tránh dùng làm luồng xử lý chung. |

## 11. Tự phân loại nhanh

1. `int x = "10";` → **Lỗi biên dịch** vì kiểu dữ liệu không tương thích.
2. `Integer.parseInt("xyz")` không được bắt → **Exception khi chạy**, loại `NumberFormatException`.
3. Đặt 8 sản phẩm trong khi tồn kho chỉ còn 3, hàm trả `OUT_OF_STOCK` → **Kết quả nghiệp vụ dự kiến**.
4. Đặt hàng trả “thành công” nhưng hệ thống không ghi đơn → **Bug khi chạy hoặc thất bại xử lý bị che giấu**, cần truy nguyên; không phải thành công đúng nghĩa.
5. Gọi API đọc tệp khai báo `throws IOException` mà bên gọi chưa bắt hoặc khai báo → **Lỗi biên dịch** tại vị trí gọi; nếu đã xử lý hợp đồng nhưng tệp vẫn không đọc được thì đó là **sự cố lúc chạy**.
6. Màn hình yêu cầu số lượng, người dùng gõ chữ; bộ chuyển đổi ném `NumberFormatException` rồi tầng giao tiếp trả lỗi nhập liệu → **Exception ở bên trong**, nhưng **kết quả xác thực dự kiến** ở ranh giới người dùng.

Ghi nhớ nguyên tắc: hãy xác định **pha xuất hiện** (biên dịch hay thực thi), **cơ chế báo hiệu** (diagnostic, exception, return value) và **ý nghĩa trong hợp đồng** (bug/sự cố hay nhánh nghiệp vụ dự kiến). Ba câu hỏi này giúp thiết kế API dễ dùng, xử lý lỗi đúng tầng và tránh báo lỗi giả cho người dùng.
