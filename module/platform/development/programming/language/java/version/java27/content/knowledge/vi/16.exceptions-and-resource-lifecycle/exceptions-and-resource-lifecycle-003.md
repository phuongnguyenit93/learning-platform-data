# Try-with-resources và hợp đồng AutoCloseable

Trong Java 27, một đối tượng có thể quản lý tài nguyên cần được giải phóng khi không còn sử dụng: luồng đọc/ghi tệp, socket, kết nối cơ sở dữ liệu, bộ đọc thư mục, hoặc một tài nguyên ứng dụng có vòng đời hữu hạn. **Garbage collector không thay thế hợp đồng đóng tài nguyên đúng thời điểm**. Bộ nhớ đối tượng có thể được thu hồi sau này, nhưng tệp đang mở, kết nối hoặc các tài nguyên bên ngoài thường phải được giải phóng có chủ đích.

**Try-with-resources** là cú pháp của Java giúp tự động gọi **close()** trên các tài nguyên được khai báo trong phần đầu câu lệnh **try**, kể cả khi phần thân kết thúc bằng ngoại lệ. Cơ chế này dựa vào interface **java.lang.AutoCloseable** và quy tắc xử lý ngoại lệ phụ (*suppressed exception*) để không làm mất ngoại lệ chính trong quá trình dọn dẹp.

Bài học giải thích cách sử dụng, thứ tự đóng, xử lý lỗi khi nhiều tài nguyên thất bại, thiết kế lớp AutoCloseable và những lưu ý thực tế trong Java 27. Các ví dụ chỉ sử dụng cú pháp và API vẫn còn áp dụng, không dựa vào finalizer hoặc các cơ chế dọn dẹp lỗi thời.

## 1. Vòng đời tài nguyên và quyền sở hữu

Một tài nguyên thường trải qua ba giai đoạn:

1. **Mở hoặc nhận quyền sở hữu:** tạo kết nối, mở tệp, hoặc nhận một đối tượng có nghĩa vụ đóng.
2. **Sử dụng:** đọc, ghi hoặc thực hiện công việc với tài nguyên đang hoạt động.
3. **Đóng:** kết thúc vòng đời sử dụng và giải phóng các tài nguyên mà đối tượng quản lý.

Ví dụ khái niệm:

~~~text
Mở tài nguyên
      |
      v
Sử dụng tài nguyên
      |
      +---- Thành công ------+
      |                     |
      +---- Ném ngoại lệ ----+
                            |
                            v
                       Đóng tài nguyên
~~~

Cần phân biệt **tham chiếu tới đối tượng** với **quyền sử dụng tài nguyên**. Sau khi gọi **close()**, biến tham chiếu có thể vẫn tồn tại, nhưng đối tượng có thể không còn cho phép thực hiện thao tác như khi đang mở.

Không phải mọi đối tượng đều cần đóng. **String**, **List** thông thường hoặc đối tượng dữ liệu thuần không nhất thiết sở hữu tài nguyên bên ngoài. Đừng thêm **AutoCloseable** cho một lớp chỉ vì muốn cho phép gọi một method tên **close()**.

### Quyền sở hữu quyết định bên nào đóng

Trong thiết kế API, cần xác định rõ bên nào sở hữu tài nguyên:

- **Tạo và sở hữu:** phương thức hoặc khối lệnh mở tài nguyên, sử dụng rồi đóng.
- **Nhận tài nguyên mượn:** phương thức chỉ sử dụng tài nguyên do caller sở hữu; không tự ý đóng nếu hợp đồng không chuyển quyền sở hữu.
- **Chuyển quyền sở hữu:** một thành phần nhận tài nguyên và cam kết đóng vào thời điểm được định nghĩa.

Ví dụ, một method nhận **InputStream** do người gọi cung cấp không nên tự động đóng luồng ấy nếu tài liệu API không nói rằng quyền sở hữu được chuyển giao. Đóng **System.in** ở một tiện ích đọc dữ liệu ngắn có thể khiến phần chương trình còn lại không đọc được đầu vào nữa.

Try-with-resources phù hợp nhất ở nơi **quyền sở hữu và phạm vi sống của tài nguyên đã rõ ràng**.

## 2. Cú pháp try-with-resources cơ bản

Cú pháp phổ biến:

~~~java
try (ResourceType resource = openResource()) {
    // Sử dụng resource.
}
~~~

Điều kiện chính là kiểu tài nguyên phải triển khai **AutoCloseable** (trực tiếp hoặc thông qua một interface con như **Closeable**). Khi phạm vi **try** kết thúc, Java gọi **close()** trên tài nguyên đã được khởi tạo thành công.

Ví dụ dùng API NIO để đọc tệp với bộ mã hóa xác định:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadFirstLine {
    public static void main(String[] args) {
        Path path = Path.of("notes.txt");

        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            String firstLine = reader.readLine();
            System.out.println(firstLine);
        } catch (IOException exception) {
            System.err.println("Cannot read file: " + exception.getMessage());
        }
    }
}
~~~

Diễn biến:

1. **Files.newBufferedReader(...)** mở một bộ đọc tệp; nếu mở thất bại, ngoại lệ được chuyển tới phần xử lý thích hợp.
2. Nếu mở thành công, **reader** là tài nguyên thuộc phạm vi try-with-resources.
3. **reader.readLine()** đọc dữ liệu và có thể ném **IOException**.
4. Khi ra khỏi phần thân **try**, Java cố gọi **reader.close()** cho dù đọc thành công hay ném ngoại lệ.
5. Phần **catch** xử lý **IOException** có thể xuất hiện khi mở, đọc hoặc đóng tài nguyên.

Ví dụ giả định tệp **notes.txt** có thể tồn tại tại thư mục làm việc. Khi tệp không có hoặc không đọc được, chương trình in thông tin lỗi thay vì mặc nhiên thành công.

### Không bắt buộc có catch hoặc finally

Try-with-resources **không bắt buộc phải có** mệnh đề **catch** hay **finally** viết tường minh:

~~~java
static String readLine(Path path) throws IOException {
    try (var reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

Ngay cả khi **return** xảy ra trong khối try, tài nguyên vẫn được đóng trước khi phương thức hoàn tất việc trả kết quả. Nếu **close()** ném ngoại lệ, hành vi kết thúc sẽ tuân theo quy tắc ngoại lệ tương ứng.

## 3. Hợp đồng java.lang.AutoCloseable

Interface **AutoCloseable** định nghĩa một phương thức:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

Một lớp triển khai **AutoCloseable** tuyên bố rằng nó có thể được đóng và có thể dùng làm resource trong try-with-resources.

~~~java
class Session implements AutoCloseable {
    private boolean open = true;

    public void execute() {
        if (!open) {
            throw new IllegalStateException("Session already closed");
        }
        System.out.println("Executing");
    }

    @Override
    public void close() {
        open = false;
        System.out.println("Session closed");
    }
}
~~~

Sử dụng:

~~~java
try (Session session = new Session()) {
    session.execute();
}
~~~

Kết quả:

~~~text
Executing
Session closed
~~~

**Session.close()** không khai báo checked exception nên caller không phải xử lý thêm ngoại lệ checked chỉ vì close. Điều này được phép: lớp triển khai có thể **thu hẹp danh sách ngoại lệ** so với **AutoCloseable.close() throws Exception**.

### AutoCloseable không tự đóng tài nguyên

Chỉ triển khai **AutoCloseable** không khiến tài nguyên tự động đóng trong mọi tình huống. Lời gọi **close()** diễn ra khi:

- Mã gọi **close()** tường minh; hoặc
- Tài nguyên được đưa vào try-with-resources và rời phạm vi sử dụng theo cơ chế ngôn ngữ; hoặc
- Một thành phần khác thực hiện đóng theo hợp đồng riêng của nó.

Nếu tạo một AutoCloseable bên ngoài try-with-resources nhưng không đóng, interface không thể bảo đảm tài nguyên được giải phóng.

### Exception trong hợp đồng close()

Phương thức **AutoCloseable.close()** cho phép khai báo **throws Exception**. Điều đó có nghĩa một try-with-resources sử dụng một biến có kiểu AutoCloseable tổng quát có thể buộc caller bắt hoặc khai báo **Exception**, ngay cả khi implementation cụ thể không ném checked exception.

Ví dụ:

~~~java
static void run(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("Using resource");
    }
}
~~~

Kiểu tĩnh của **resource** là **AutoCloseable**, nên compiler nhìn thấy khả năng **close()** ném **Exception**. Hãy chọn kiểu resource và hợp đồng close cụ thể nhất phù hợp, thay vì luôn công khai loại **Exception** rộng trong API.

## 4. AutoCloseable khác java.io.Closeable thế nào?

**java.io.Closeable** mở rộng **AutoCloseable** và thường được dùng bởi các đối tượng I/O.

| Đặc điểm | AutoCloseable | Closeable |
|---|---|---|
| Package | **java.lang** | **java.io** |
| Kế thừa | Interface gốc cho tài nguyên có thể đóng | **extends AutoCloseable** |
| Chữ ký close | **void close() throws Exception** | **void close() throws IOException** |
| Phạm vi dùng phổ biến | Nhiều loại tài nguyên: session, lock guard, transaction scope... | Tài nguyên I/O: stream, reader, writer... |
| Gọi close nhiều lần | Không mặc định bảo đảm idempotent | Hợp đồng **Closeable** quy định gọi lại khi đã đóng không có tác dụng |

Với tài nguyên I/O, triển khai **Closeable** có thể phù hợp khi muốn hợp đồng checked exception hẹp là **IOException**. Với tài nguyên không phải I/O, **AutoCloseable** thường đủ.

Ví dụ:

~~~java
import java.io.Closeable;
import java.io.IOException;

final class InputHandle implements Closeable {
    private boolean closed;

    public void read() throws IOException {
        if (closed) {
            throw new IOException("Handle closed");
        }
        System.out.println("Reading");
    }

    @Override
    public void close() throws IOException {
        if (closed) {
            return;
        }
        closed = true;
        System.out.println("Closing input handle");
    }
}
~~~

Đây là một triển khai Closeable tự tạo để minh họa. Với việc đọc tệp thật, nên ưu tiên các lớp có sẵn và đúng mục đích như **BufferedReader** hoặc **InputStream**.

### Có bắt buộc close() phải idempotent?

**AutoCloseable.close()** không yêu cầu mọi triển khai phải idempotent. Một số tài nguyên có thể phản ứng khác nhau khi đóng lần thứ hai. Tuy vậy, với API sở hữu tài nguyên, việc thiết kế close an toàn khi được gọi lặp lại thường giúp giảm lỗi.

Không nên đánh đồng idempotency với thread safety: một đối tượng cho phép gọi **close()** nhiều lần vẫn có thể **không an toàn khi nhiều thread sử dụng đồng thời**.

## 5. Tại sao try-with-resources tốt hơn đóng thủ công?

Nếu đóng tài nguyên thủ công mà không kiểm soát mọi đường thoát, rất dễ bỏ sót khi có ngoại lệ:

~~~java
// Ví dụ chỉ minh họa lỗi thiết kế: không nên áp dụng.
BufferedReader reader = Files.newBufferedReader(path);

String line = reader.readLine(); // Nếu dòng này ném lỗi...
reader.close();                  // ...lời gọi close có thể bị bỏ qua.
~~~

Có thể dùng **finally** để thực hiện dọn dẹp, nhưng tự triển khai quy tắc này thường dài hơn và dễ viết sai khi **close()** cũng có thể ném ngoại lệ.

~~~java
// Cách ưu tiên:
try (BufferedReader reader = Files.newBufferedReader(path)) {
    String line = reader.readLine();
    System.out.println(line);
}
~~~

Java đảm nhận việc đóng và quy tắc lựa chọn ngoại lệ chính/phụ. Mã ứng dụng tập trung vào nhiệm vụ đang làm, đồng thời thể hiện rõ phạm vi sống của tài nguyên.

Try-with-resources **không** bảo đảm rằng mọi lỗi dọn dẹp đều biến mất. Ngoại lệ từ **close()** vẫn có thể được ném ra hoặc được lưu làm **suppressed exception**; chương trình cần có chính sách quan sát và xử lý lỗi phù hợp.

## 6. Nhiều tài nguyên: mở từ trái sang phải, đóng theo thứ tự ngược lại

Phần đầu try-with-resources có thể khai báo nhiều resource, phân tách bằng dấu chấm phẩy.

~~~java
try (Resource first = openFirst();
     Resource second = openSecond();
     Resource third = openThird()) {
    work(first, second, third);
}
~~~

Thứ tự thực hiện về mặt khái niệm:

~~~text
Mở first
   |
Mở second
   |
Mở third
   |
Chạy phần thân try
   |
Đóng third
   |
Đóng second
   |
Đóng first
~~~

Java đóng theo thứ tự ngược với thứ tự khởi tạo. Điều này hữu ích khi tài nguyên được mở sau phụ thuộc vào tài nguyên được mở trước.

Ví dụ có thể chạy để quan sát:

~~~java
class TrackedResource implements AutoCloseable {
    private final String name;

    TrackedResource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}

class ResourceOrderDemo {
    public static void main(String[] args) {
        try (TrackedResource first = new TrackedResource("A");
             TrackedResource second = new TrackedResource("B")) {
            System.out.println("work");
        }
    }
}
~~~

Kết quả:

~~~text
open A
open B
work
close B
close A
~~~

### Một close thất bại không ngăn Java thử đóng các tài nguyên khác

Khi một tài nguyên ném ngoại lệ trong **close()**, try-with-resources vẫn cố đóng các tài nguyên đã mở trước đó. Ngoại lệ phụ được quản lý theo quy tắc suppression, thay vì lập tức bỏ qua các lần đóng còn lại.

Tuy nhiên, việc **gọi close()** không phải bảo đảm rằng tài nguyên bên ngoài chắc chắn đã được giải phóng nếu close thất bại. Điều đó tùy thuộc implementation và tính chất lỗi.

## 7. Nếu khởi tạo một tài nguyên ở giữa thất bại thì sao?

Giả sử resource **A** mở thành công, nhưng việc tạo resource **B** ném ngoại lệ.

~~~java
class OpenDemo {
    static TrackedResource openA() {
        return new TrackedResource("A");
    }

    static TrackedResource openB() {
        throw new IllegalStateException("Cannot open B");
    }

    public static void main(String[] args) {
        try (TrackedResource a = openA();
             TrackedResource b = openB()) {
            System.out.println("Never executed");
        } catch (IllegalStateException exception) {
            System.out.println(exception.getMessage());
        }
    }
}
~~~

Kết quả:

~~~text
open A
close A
Cannot open B
~~~

Những điều quan trọng:

- **A** đã khởi tạo thành công nên Java tự đóng nó khi bước khởi tạo **B** thất bại.
- **B** chưa được tạo thành công nên không có tài nguyên **B** để đóng.
- Phần thân **try** không được thực thi.
- Nếu **A.close()** cũng ném ngoại lệ, ngoại lệ đóng sẽ bị ghi dưới dạng **suppressed exception** của ngoại lệ khởi tạo **B**, theo quy tắc áp dụng.

Đây là lợi ích lớn của try-with-resources khi khởi tạo nhiều tài nguyên theo từng bước: các tài nguyên **đã mở thành công trước đó** vẫn được xử lý dọn dẹp.

## 8. Ngoại lệ chính và suppressed exception

Một tình huống khó: phần thân try ném ngoại lệ, rồi **close()** cũng ném một ngoại lệ khác.

Java ưu tiên giữ ngoại lệ từ phần thân làm **ngoại lệ chính (primary exception)**. Ngoại lệ phát sinh khi đóng tài nguyên được gắn vào ngoại lệ chính dưới dạng **suppressed exception**, truy cập qua **Throwable.getSuppressed()**.

Ví dụ hoàn chỉnh:

~~~java
class FailingResource implements AutoCloseable {
    @Override
    public void close() {
        throw new IllegalStateException("close failed");
    }
}

class SuppressedDemo {
    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IllegalArgumentException("body failed");
        } catch (Exception exception) {
            System.out.println("primary: " + exception.getMessage());

            for (Throwable suppressed : exception.getSuppressed()) {
                System.out.println("suppressed: "
                        + suppressed.getMessage());
            }
        }
    }
}
~~~

Kết quả:

~~~text
primary: body failed
suppressed: close failed
~~~

Nếu **close()** ném ngoại lệ nhưng phần thân kết thúc bình thường, ngoại lệ từ **close()** có thể trở thành ngoại lệ được ném ra chính.

### Không nhầm suppressed với cause

- **getCause()** thể hiện một chuỗi nguyên nhân được thiết lập cho ngoại lệ, thường dùng khi một lớp API bọc ngoại lệ từ tầng dưới.
- **getSuppressed()** chứa những ngoại lệ phụ bị dồn vào một ngoại lệ chính, điển hình khi đóng tài nguyên trong try-with-resources.

Hai cơ chế phục vụ mục tiêu khác nhau. Một ngoại lệ có thể vừa có **cause**, vừa có nhiều **suppressed exceptions**.

### Vì sao không chỉ ghi log ngoại lệ chính?

Nếu hệ thống chỉ hiển thị thông điệp của ngoại lệ chính, thông tin về lỗi đóng tài nguyên có thể bị bỏ qua. Trong xử lý lỗi, cần bảo đảm log hoặc cơ chế quan sát thể hiện stack trace và các suppressed exception có ý nghĩa.

Ví dụ, gọi **exception.printStackTrace()** trong một chương trình minh họa thường cho thấy cả ngoại lệ chính và những ngoại lệ bị suppressed. Trong ứng dụng thật, dùng cơ chế logging phù hợp; không nhất thiết tự lặp qua từng suppressed exception nếu công cụ logging đã hỗ trợ.

## 9. Thứ tự ngoại lệ khi nhiều close() cùng thất bại

Khi phần thân **không** ném ngoại lệ nhưng nhiều lần đóng đều thất bại, ngoại lệ từ tài nguyên **được đóng đầu tiên** trở thành primary; những lỗi đóng sau đó bị suppressed.

Vì các resource được đóng theo thứ tự ngược, đối với:

~~~java
try (Resource a = openA();
     Resource b = openB()) {
    doWork();
}
~~~

nếu **doWork()** hoàn tất bình thường, **b.close()** thất bại rồi **a.close()** cũng thất bại, lỗi của **b.close()** là primary và lỗi **a.close()** là suppressed.

Ngược lại, nếu **doWork()** đã ném ngoại lệ, lỗi từ cả **b.close()** và **a.close()** trở thành suppressed của ngoại lệ phần thân.

| Tình huống | Primary exception | Suppressed exception |
|---|---|---|
| Body bình thường, mọi close thành công | Không có | Không có |
| Body ném lỗi, mọi close thành công | Lỗi body | Không có |
| Body bình thường, một close ném lỗi | Lỗi close | Không có |
| Body ném lỗi, close cũng ném lỗi | Lỗi body | Lỗi từ close |
| Body bình thường, nhiều close ném lỗi | Lỗi đóng đầu tiên theo thứ tự ngược | Các lỗi đóng tiếp theo |
| Khởi tạo resource sau ném lỗi, đóng resource trước cũng lỗi | Lỗi khởi tạo | Lỗi đóng resource đã khởi tạo |

Bảng mô tả các trường hợp thông thường với exception. Nó không thay thế việc xử lý các tình huống lỗi nghiêm trọng của môi trường thực thi, chẳng hạn quá trình JVM bị kết thúc đột ngột.

## 10. catch và finally chạy vào lúc nào?

Try-with-resources cũng có thể có **catch** và **finally**:

~~~java
try (TrackedResource resource = new TrackedResource("A")) {
    System.out.println("using A");
} catch (RuntimeException exception) {
    System.out.println("caught: " + exception.getMessage());
} finally {
    System.out.println("outer finally");
}
~~~

Kết quả:

~~~text
open A
using A
close A
outer finally
~~~

Tài nguyên được đóng trong cơ chế **finally ngầm định** của try-with-resources **trước khi** mệnh đề **catch** hoặc **finally** do lập trình viên viết cho câu lệnh đó thực hiện.

Nếu phần thân hoặc quá trình đóng ném một ngoại lệ phù hợp, **catch** nhìn thấy ngoại lệ sau khi các lần đóng cần thiết đã được thử thực hiện.

### return cũng không bỏ qua close()

~~~java
static int calculate() {
    try (TrackedResource resource = new TrackedResource("A")) {
        return 27;
    }
}
~~~

Khi gọi **calculate()**, Java đóng resource trước khi trả về **27**. Nếu close ném ngoại lệ, phương thức có thể kết thúc bằng ngoại lệ thay vì trả về giá trị dự kiến.

Tương tự, **break** và **continue** đi ra khỏi phạm vi try-with-resources vẫn kích hoạt quá trình đóng khi luồng điều khiển rời phạm vi. Không nên kết luận rằng chỉ có đường thoát tự nhiên mới đóng tài nguyên.

## 11. Biến resource trong header và phạm vi sử dụng

Dạng khai báo resource:

~~~java
try (var reader = Files.newBufferedReader(Path.of("notes.txt"))) {
    System.out.println(reader.readLine());
}

// Không thể dùng tên biến reader ở đây.
~~~

Biến được khai báo trong resource specification chỉ nằm trong phạm vi phù hợp với câu lệnh try-with-resources, không phải một biến có thể sử dụng tự do sau khi khối kết thúc.

### Resource có thể khai báo bằng var

Java hỗ trợ **var** cho biến cục bộ khi compiler có đủ thông tin suy luận kiểu. Vì resource được khởi tạo ngay tại khai báo, **var** thường giúp tránh lặp tên lớp dài:

~~~java
try (var reader = Files.newBufferedReader(Path.of("notes.txt"))) {
    System.out.println(reader.readLine());
}
~~~

Từ khóa **var** không chuyển Java thành ngôn ngữ kiểu động. Compiler vẫn xác định một kiểu tĩnh cụ thể cho biến resource, bao gồm hợp đồng **close()** tương ứng.

Trong những đoạn mã cần làm nổi bật loại tài nguyên, viết rõ **BufferedReader** cũng hoàn toàn phù hợp.

## 12. Dùng lại resource đã khai báo trước try (Java 9 trở đi)

Trong Java hiện hành, try-with-resources có thể nhận một biến resource đã được khai báo trước, miễn là biến đó **final** hoặc **effectively final** và biểu thức sử dụng phù hợp quy tắc resource specification.

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static void printFirstLine(Path path) throws IOException {
    BufferedReader reader = Files.newBufferedReader(path);

    try (reader) {
        System.out.println(reader.readLine());
    }
}
~~~

Với cú pháp **try (reader)**, Java vẫn đóng đối tượng được giữ trong **reader** khi ra khỏi phạm vi. Sau đó biến **reader** vẫn nằm trong phạm vi từ vựng của phương thức, nhưng đối tượng đã được đóng, nên không nên dùng để đọc tiếp.

### Effectively final là gì?

Biến **effectively final** là biến không được gán lại sau khi nhận giá trị, dù không có từ khóa **final**.

~~~java
BufferedReader reader = Files.newBufferedReader(path);

try (reader) {
    System.out.println(reader.readLine());
}

// reader = Files.newBufferedReader(otherPath);
// Nếu gán lại reader trong cùng phạm vi, biểu thức try (reader)
// sẽ không còn đáp ứng điều kiện effectively final.
~~~

Nếu thực sự cần tạo một tài nguyên mới cho một phạm vi khác, dùng biến mới thay vì cố gán lại cùng biến đã được dùng trong resource specification.

### Không được khai báo một resource tùy ý

Một biểu thức bất kỳ gọi method tạo resource không thể dùng trực tiếp ở dạng:

~~~java
// try (Files.newBufferedReader(path)) { ... }
// Không hợp lệ: resource specification không chấp nhận
// một method invocation trần như vậy.
~~~

Hãy gán kết quả vào một biến resource:

~~~java
try (var reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
~~~

Điều này thể hiện rõ tài nguyên nào đang được sở hữu và sẽ được đóng khi kết thúc phạm vi.

## 13. Chuyện gì xảy ra nếu resource là null?

Ở góc độ cú pháp, một biến resource có thể chứa **null**. Trong trường hợp ấy, try-with-resources **không gọi close()** trên tham chiếu null.

~~~java
static void nullResourceDemo() throws Exception {
    AutoCloseable resource = null;

    try (resource) {
        System.out.println("No actual resource");
    }
}
~~~

Ví dụ vẫn hợp lệ; không có đối tượng nào để đóng. Phương thức khai báo **throws Exception** vì kiểu tĩnh **AutoCloseable** cho phép **close()** ném checked exception, dù tham chiếu trong lần chạy này là null. Tuy nhiên, điều đó **không** có nghĩa sử dụng null như một tài nguyên là thiết kế tốt. Nếu phần thân gọi một instance method qua tham chiếu null, mã vẫn có thể ném **NullPointerException**.

Nếu tài nguyên bắt buộc có mặt, hãy kiểm tra ngay khi tạo hoặc nhận:

~~~java
import java.util.Objects;

static void use(AutoCloseable resource) throws Exception {
    Objects.requireNonNull(resource, "resource");

    try (resource) {
        System.out.println("Resource accepted");
    }
}
~~~

Trong ví dụ này, **Objects.requireNonNull()** cung cấp một hợp đồng rõ rằng null bị từ chối; các lỗi liên quan đến **close()** vẫn được xử lý theo hợp đồng **AutoCloseable**.

## 14. Thiết kế một AutoCloseable tùy chỉnh

Khi tự xây lớp giữ tài nguyên cần đóng, nên làm rõ:

- Tài nguyên được mở khi nào và có thể sử dụng trong trạng thái nào?
- **close()** có giải phóng đúng những thứ lớp sở hữu không?
- Sau khi đóng, method nào không còn hợp lệ?
- Có cho phép gọi **close()** lặp lại không?
- Khi đóng thất bại, trạng thái của đối tượng và tài nguyên bên dưới được xác định thế nào?
- Lớp có an toàn khi nhiều thread truy cập hay không?
- Nếu một phần quá trình mở thất bại, tài nguyên đã mở trước đó được dọn dẹp ở đâu?

Ví dụ một tài nguyên ứng dụng đơn giản:

~~~java
import java.util.Objects;

public final class WorkScope implements AutoCloseable {
    private boolean closed;

    public void submit(String task) {
        Objects.requireNonNull(task, "task");

        if (closed) {
            throw new IllegalStateException("Scope is closed");
        }

        System.out.println("Submit: " + task);
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }

        closed = true;
        System.out.println("Scope closed");
    }
}
~~~

Sử dụng:

~~~java
try (WorkScope scope = new WorkScope()) {
    scope.submit("Import data");
    scope.submit("Generate report");
}
~~~

Kết quả:

~~~text
Submit: Import data
Submit: Generate report
Scope closed
~~~

Đây là lớp minh họa vòng đời, chưa bao gồm một tài nguyên hệ điều hành thật. Nó chủ động đánh dấu **closed** để tránh sử dụng sau close và làm **close()** an toàn khi bị gọi lặp lại. Việc dùng boolean thông thường **không tạo bảo đảm thread-safety**; ví dụ được thiết kế cho sử dụng tuần tự.

### Không dùng close() làm nơi che lỗi

Nếu thao tác dọn dẹp có thể thất bại, đừng âm thầm bỏ qua mọi ngoại lệ chỉ để câu lệnh **close()** luôn kết thúc. Hợp đồng nên xác định mức độ nghiêm trọng và cách truyền hoặc ghi nhận lỗi dọn dẹp.

Ngược lại, không nên ném **InterruptedException** từ **close()** nếu có thể tránh, vì cơ chế xử lý ngoại lệ và trạng thái ngắt của thread có những tương tác dễ gây hiểu nhầm. Đây cũng là khuyến nghị thận trọng đối với lớp triển khai AutoCloseable.

## 15. Tài nguyên lồng nhau và wrapper đóng tài nguyên bên dưới

Nhiều API tạo các lớp bọc (*wrapper*) lên tài nguyên nền. Khi đóng wrapper, nó thường đóng cả tài nguyên bên dưới theo hợp đồng của wrapper tương ứng.

Ví dụ, một **BufferedReader** có thể bọc một Reader khác. Nếu đã dùng **Files.newBufferedReader(...)**, không cần mở thêm một InputStream riêng rồi tự quản lý nhiều lớp chỉ để đọc văn bản cơ bản:

~~~java
try (var reader = Files.newBufferedReader(
        Path.of("notes.txt"), StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
~~~

### Nếu tự xây nhiều lớp bọc

Trong trường hợp cần tự mở nhiều tầng, phải xác định **ai sở hữu và đóng** tài nguyên nền. Đóng cả wrapper và tài nguyên bên dưới trong các resource declarations riêng có thể tạo ra các lần gọi close trùng nhau. Điều đó có thể vô hại với một số Closeable, nhưng không phải luôn đúng với mọi AutoCloseable.

Do đó:

- Ưu tiên một đối tượng sở hữu rõ ràng tài nguyên cần quản lý.
- Nếu wrapper có hợp đồng đóng delegate, đóng wrapper ở phạm vi hợp lý thường là đủ.
- Nếu các tài nguyên độc lập, khai báo riêng trong try-with-resources để mỗi tài nguyên được đóng.
- Không tự ý đóng resource được mượn từ component khác khi hợp đồng chưa cho phép.

### Try-with-resources không đảm bảo atomicity

Nếu một thao tác cần nhiều tài nguyên và có thay đổi trạng thái bên ngoài, việc đóng đầy đủ không có nghĩa toàn bộ thay đổi là **atomic** hoặc **transactional**.

Ví dụ, đóng một JDBC connection không mặc nhiên đồng nghĩa với commit/rollback đúng ý định giao dịch. Việc quản lý giao dịch phụ thuộc vào chế độ auto-commit, hợp đồng driver, pool và abstraction được dùng. Cần thiết kế commit/rollback riêng theo API giao dịch phù hợp.

## 16. Những API Java hiện đại cần đóng có chủ đích

Try-with-resources đặc biệt hữu ích với API I/O của **java.nio.file.Files** và những Stream nắm giữ tài nguyên bên ngoài.

### BufferedReader và BufferedWriter

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void copyFirstLine(Path source, Path target) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(source, StandardCharsets.UTF_8);
         BufferedWriter writer =
                 Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
        String line = reader.readLine();

        if (line != null) {
            writer.write(line);
            writer.newLine();
        }
    }
}
~~~

Ví dụ minh họa hai resource với thứ tự đóng **writer** trước rồi tới **reader**. Khi mở **writer**, các tùy chọn mặc định của **Files.newBufferedWriter** có thể tạo tệp hoặc cắt ngắn nội dung hiện có; vì vậy mã thực tế cần có chính sách rõ ràng về việc ghi đè dữ liệu trước khi gọi.

### Files.lines(): Stream gắn với tệp

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

**Files.lines(...)** trả về Stream mà quá trình duyệt có thể phụ thuộc vào một tệp đang mở. Khi dùng xong, **phải đóng Stream** theo hợp đồng API. Chạy terminal operation như **count()** không tự bảo đảm rằng stream được đóng.

Trong một số trường hợp, lỗi I/O xảy ra trong khi tiêu thụ Stream có thể được bao bọc dưới dạng **UncheckedIOException**. Do đó, kiểu ngoại lệ của việc mở Stream và của quá trình duyệt Stream không nhất thiết hoàn toàn giống nhau.

### Files.list() và Files.walk()

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countEntries(Path directory) throws IOException {
    try (Stream<Path> entries = Files.list(directory)) {
        return entries.count();
    }
}
~~~

Tương tự, **Files.walk(...)** có thể trả Stream gắn với các thư mục đang được duyệt. Những Stream này cần được đóng sau khi sử dụng.

**Không nên kết luận rằng mọi Stream đều cần đóng thủ công.** Stream tạo từ một danh sách trong bộ nhớ như **List.of(...).stream()** thường không nắm giữ tài nguyên hệ điều hành; thao tác **close()** không có hiệu ứng cần thiết trong ví dụ đó. Hãy dựa vào hợp đồng của nguồn cung cấp Stream.

### Một số API khác

Các loại tài nguyên có thể phù hợp try-with-resources còn bao gồm:

- **InputStream**, **OutputStream**, **Reader**, **Writer**.
- **Socket** hoặc một số channel trong **java.nio.channels**.
- **Connection**, **Statement**, **ResultSet** của JDBC, tùy cách quản lý và quyền sở hữu từ framework hoặc connection pool.
- Những resource scope hoặc handle do ứng dụng định nghĩa và triển khai **AutoCloseable**.

Không nên đóng một đối tượng thuộc quyền quản lý của framework nếu framework vẫn cần sử dụng nó; tài liệu và hợp đồng ownership của API cụ thể luôn có ưu tiên.

## 17. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ đóng resource ở cuối đường đi bình thường | Ngoại lệ có thể bỏ qua close | Dùng try-with-resources ở phạm vi sở hữu tài nguyên |
| Tưởng có AutoCloseable là tự đóng mọi lúc | Resource không được đưa vào phạm vi đóng vẫn có thể bị bỏ quên | Chủ động dùng try-with-resources hoặc quản lý vòng đời rõ ràng |
| Tưởng close lỗi sẽ luôn thay thế body lỗi | Hiểu sai ngoại lệ chính và suppressed | Dùng **getSuppressed()** khi cần phân tích đầy đủ |
| Đóng resource do caller cho mượn | Phá vòng đời ở nơi khác | Ghi rõ quyền sở hữu và trách nhiệm close trong API |
| Tạo nhiều resource rồi chỉ đóng resource cuối cùng | Các tài nguyên trước đó có thể rò rỉ khi lỗi | Khai báo các resource cần sở hữu trong try-with-resources |
| Trả một resource ra ngoài nhưng đã đóng trong method | Người gọi nhận resource đã hết vòng đời | Để caller quản lý nếu API thực sự chuyển quyền sở hữu |
| Dùng object sau khi khối try kết thúc | Nhiều API ném ngoại lệ do resource đã đóng | Giới hạn việc dùng resource trong phạm vi sống hợp lệ |
| Cho rằng close() luôn idempotent và thread-safe | Có thể phát sinh lỗi hoặc race condition | Thiết kế và tài liệu hóa hai thuộc tính này riêng biệt |
| Quên đóng **Files.lines()**, **Files.list()**, **Files.walk()** | Stream có thể giữ descriptor hoặc tài nguyên I/O | Đặt Stream trong try-with-resources |
| Cho rằng terminal operation tự đóng Stream I/O | Tài nguyên vẫn có thể mở | Gọi close thông qua try-with-resources |
| Đóng wrapper và delegate hai lần không xét hợp đồng | Có thể tạo lỗi hoặc tác dụng phụ bất ngờ | Chỉ định một owner rõ ràng |
| Dùng try-with-resources để thay giao dịch dữ liệu | Giải phóng tài nguyên không tương đương transaction commit | Thiết kế commit/rollback riêng theo API |
| Bắt và bỏ qua mọi exception từ close | Che mất lỗi tài nguyên | Log hoặc truyền ngoại lệ theo hợp đồng; xem suppressed |
| Dựa vào GC để đóng tệp/kết nối | Thời điểm giải phóng không xác định | Đóng có chủ đích; không dùng finalization để quản lý resource |

## 18. Ví dụ tổng hợp: thứ tự close và suppressed exception

Chương trình sau độc lập, không cần tệp ngoài. Nó mở hai resource, tạo lỗi trong phần thân và cố ý làm cả hai lần close thất bại để minh họa đúng cơ chế suppression.

Lưu thành tệp **ResourceLifecycleDemo.java**:

~~~java
public class ResourceLifecycleDemo {
    private static final class TraceResource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        TraceResource(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("open " + name);
        }

        void work() {
            System.out.println("work " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);

            if (failOnClose) {
                throw new IllegalStateException(
                        "failed to close " + name);
            }
        }
    }

    public static void main(String[] args) {
        try (TraceResource first = new TraceResource("A", true);
             TraceResource second = new TraceResource("B", true)) {
            first.work();
            second.work();

            throw new IllegalArgumentException("body failure");
        } catch (Exception exception) {
            System.out.println("primary: " + exception.getMessage());

            for (Throwable suppressed : exception.getSuppressed()) {
                System.out.println(
                        "suppressed: " + suppressed.getMessage());
            }
        } finally {
            System.out.println("finished");
        }
    }
}
~~~

Kết quả:

~~~text
open A
open B
work A
work B
close B
close A
primary: body failure
suppressed: failed to close B
suppressed: failed to close A
finished
~~~

Phân tích:

1. **A** được mở trước, **B** được mở sau.
2. Phần thân thực hiện công việc trên cả hai tài nguyên.
3. Ngoại lệ **IllegalArgumentException("body failure")** trở thành ngoại lệ chính.
4. Java gọi **B.close()** trước; ngoại lệ từ B được gắn dưới dạng suppressed.
5. Java tiếp tục gọi **A.close()**; ngoại lệ từ A cũng được gắn dưới dạng suppressed.
6. **catch** nhận ngoại lệ chính, đọc hai ngoại lệ bị suppressed theo thứ tự phát sinh.
7. **finally** được thực hiện sau khi quá trình đóng và xử lý catch kết thúc.

Để khảo sát trường hợp khác, có thể bỏ câu lệnh **throw** trong phần thân. Khi cả hai close vẫn thất bại, ngoại lệ của **B.close()** sẽ là primary, còn lỗi của **A.close()** sẽ bị suppressed.

Ví dụ cố ý mô phỏng close thất bại; trong một resource thật, phần triển khai **close()** cần có hợp đồng rõ ràng về lỗi và trạng thái tài nguyên sau khi thất bại.

## 19. Checklist thiết kế vòng đời tài nguyên

Trước khi hoàn tất một đoạn mã sử dụng tài nguyên trong Java 27, hãy xác nhận:

- Đối tượng này có thực sự cần giải phóng tài nguyên không, hay chỉ là đối tượng dữ liệu thông thường?
- Bên nào **sở hữu** resource và chịu trách nhiệm đóng?
- Resource có triển khai **AutoCloseable** hoặc **Closeable** không?
- Phạm vi try-with-resources có bao trùm toàn bộ thời gian sử dụng hợp lệ và không dài hơn cần thiết không?
- Nếu mở nhiều resource, thứ tự khởi tạo và đóng có phù hợp quan hệ phụ thuộc không?
- Nếu việc khởi tạo resource sau thất bại, các resource trước có được đóng tự động không?
- Nếu body và close cùng ném ngoại lệ, hệ thống có quan sát được **getSuppressed()** khi cần không?
- Catch/finally có được đặt đúng nơi để xử lý ngoại lệ sau khi resource được đóng không?
- Resource khai báo bên ngoài có **final/effectively final** nếu dùng **try (resource)** không?
- Có nguy cơ dùng tiếp resource sau khi đã close không?
- Có đang đóng resource được mượn mà caller/framework còn cần không?
- Với **Closeable**, **AutoCloseable**, có hiểu rõ hợp đồng idempotency và exception của kiểu cụ thể không?
- Các Stream gắn với I/O như **Files.lines()**, **Files.list()** và **Files.walk()** có được đóng không?
- Nếu cần transaction, đã xử lý commit/rollback độc lập với việc đóng connection chưa?
- API có tài liệu rõ về quyền sở hữu, hành vi khi close và khả năng sử dụng đồng thời không?

## Kết luận

**Try-with-resources** là lựa chọn mặc định phù hợp khi một phạm vi mã Java 27 sở hữu tài nguyên có thể đóng. Nó giúp **đóng tự động theo thứ tự ngược**, xử lý cả đường đi bình thường lẫn ngoại lệ, và giữ lỗi dọn dẹp dưới dạng **suppressed exception** để không che mất nguyên nhân chính.

**AutoCloseable** định nghĩa khả năng đóng; **Closeable** bổ sung hợp đồng phù hợp với I/O. Cả hai đều cần một thiết kế vòng đời có chủ đích: phân định ownership, không dùng resource sau close, biết cách xử lý lỗi khi đóng, và không đánh đồng việc giải phóng tài nguyên với giao dịch dữ liệu hoặc tính an toàn khi dùng đồng thời.

Khi đọc hoặc viết mã xử lý tài nguyên, hãy trả lời ba câu hỏi: **ai mở, ai sử dụng và ai đóng?** Nếu ba trách nhiệm ấy rõ ràng và được thể hiện qua try-with-resources cùng hợp đồng AutoCloseable phù hợp, phần lớn lỗi quản lý vòng đời tài nguyên có thể được tránh từ cấu trúc mã nguồn.
