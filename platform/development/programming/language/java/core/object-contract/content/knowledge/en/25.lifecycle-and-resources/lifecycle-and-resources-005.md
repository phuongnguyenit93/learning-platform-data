# AutoCloseable và try-with-resources: đóng tài nguyên tường minh trong Java

## 1. Vấn đề: vì sao tài nguyên cần được đóng?

Đối tượng Java được Garbage Collector (GC) quản lý bộ nhớ heap, nhưng nhiều đối tượng còn sở hữu tài nguyên **ngoài heap**: file descriptor, socket, kết nối cơ sở dữ liệu, luồng nhập/xuất, handle hệ điều hành hoặc vùng nhớ native. Khi đối tượng không còn được tham chiếu, GC có thể thu hồi bộ nhớ của nó; điều đó **không bảo đảm** tài nguyên ngoài heap được giải phóng đúng thời điểm. Đợi GC để đóng file hay trả kết nối về pool có thể gây cạn tài nguyên, khóa file, giữ kết nối lâu và khiến chương trình khó dự đoán.

Với tài nguyên có vòng đời rõ ràng, nguyên tắc là: **mở khi cần, sử dụng trong phạm vi ngắn nhất hợp lý, đóng chắc chắn khi kết thúc phạm vi**. Java cung cấp giao diện **AutoCloseable** và cú pháp **try-with-resources** để diễn đạt nguyên tắc ấy trực tiếp trong mã nguồn.

Tài nguyên thường cần đóng: **InputStream**, **OutputStream**, **Reader**, **Writer**, **Scanner** (khi sở hữu nguồn cần đóng), **java.sql.Connection**, **Statement**, **ResultSet**, **java.nio.channels.Channel**, **Files.lines(...)** và các đối tượng tự định nghĩa có phương thức giải phóng tài nguyên. Một đối tượng chỉ nằm trên heap, không nắm tài nguyên hữu hạn bên ngoài, thường không cần tự biến thành AutoCloseable.

## 2. Hợp đồng của AutoCloseable và Closeable

**java.lang.AutoCloseable** khai báo một phương thức:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

Đối tượng triển khai giao diện này có thể đứng trong phần khai báo tài nguyên của **try-with-resources**. Java tự gọi **close()** khi thoát khối, kể cả khi khối hoàn tất bình thường, ném ngoại lệ hoặc thực hiện **return**.

**java.io.Closeable** kế thừa AutoCloseable nhưng thu hẹp kiểu checked exception thành **IOException**:

~~~java
public interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
~~~

Một số khác biệt cần nắm:

| Thuộc tính | AutoCloseable | Closeable |
| --- | --- | --- |
| Phạm vi sử dụng | Giao diện tổng quát cho đối tượng cần cleanup | Truyền thống dùng cho các nguồn/đích I/O |
| Khai báo close | Có thể ném Exception | Có thể ném IOException |
| Gọi close nhiều lần | Không bắt buộc idempotent; nên thiết kế an toàn nếu có thể | Hợp đồng yêu cầu lần gọi sau khi đã đóng không có tác dụng |
| Tương thích try-with-resources | Có | Có |

**Idempotent** ở đây nghĩa là gọi **close()** thêm lần nữa không làm đổi trạng thái hoặc gây tác dụng phụ mới. Không được suy ra mọi AutoCloseable đều an toàn khi đóng hai lần; hãy đọc hợp đồng của loại tài nguyên cụ thể.

**close()** chỉ có nghĩa là hoàn tất/giải phóng phần việc mà lớp đó cam kết. Nó không đồng nghĩa tuyệt đối với “hủy đối tượng”, “xóa dữ liệu” hay “ngắt kết nối vật lý”: chẳng hạn **Connection.close()** của một connection pool thường trả kết nối về pool theo hợp đồng thư viện.

## 3. Cú pháp và vòng đời chuẩn

~~~java
try (ResourceType resource = acquire()) {
    use(resource);
} catch (Exception e) {
    handle(e);
}
~~~

Ở đây **ResourceType** phải triển khai AutoCloseable; **acquire**, **use** và **handle** là tên minh họa chứ chưa phải chương trình Java độc lập. Trình tự thực tế là:

1. Đánh giá biểu thức và khởi tạo tài nguyên.
2. Chạy thân **try**.
3. Gọi **close()** tự động khi rời thân **try**.
4. Nếu có **catch** hoặc **finally** gắn với toàn bộ cấu trúc, chúng được thực hiện sau bước đóng tài nguyên, tùy luồng điều khiển và ngoại lệ.

Nếu có nhiều tài nguyên, chúng được tạo theo **thứ tự từ trái sang phải** nhưng đóng theo **thứ tự ngược lại**. Đây là nguyên tắc “vào sau, ra trước”, rất hữu ích khi tài nguyên phía sau phụ thuộc vào tài nguyên phía trước.

### Ví dụ chạy được: thứ tự mở/đóng

Tệp **ResourceOrderDemo.java**:

~~~java
public class ResourceOrderDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        void work() {
            System.out.println("work " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Tracked first = new Tracked("A");
             Tracked second = new Tracked("B")) {
            first.work();
            second.work();
        }
        System.out.println("done");
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac ResourceOrderDemo.java
java ResourceOrderDemo
~~~

Kết quả chuẩn:

~~~text
open A
open B
work A
work B
close B
close A
done
~~~

Không cần gọi **first.close()** hoặc **second.close()** trong thân **try**. Nếu ném ngoại lệ khi đang khởi tạo **second**, **first** vẫn được đóng; tài nguyên nào chưa khởi tạo thành công thì không có lần đóng tương ứng. Nếu thân khối dùng **return**, Java vẫn cố đóng các tài nguyên trước khi phương thức thật sự trả về.

## 4. Áp dụng với tệp và luồng dữ liệu

Ví dụ dưới đây mở cả nguồn đọc lẫn đích ghi và để Java đóng cả hai. Tệp **CopyTextFile.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyTextFile {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.out.println("Cách dùng: java CopyTextFile <nguồn> <đích>");
            return;
        }

        Path source = Path.of(args[0]);
        Path destination = Path.of(args[1]);

        try (BufferedReader reader =
                     Files.newBufferedReader(source, StandardCharsets.UTF_8);
             BufferedWriter writer =
                     Files.newBufferedWriter(destination, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                writer.write(line);
                writer.newLine();
            }
        }

        System.out.println("Đã sao chép tệp.");
    }
}
~~~

Chạy:

~~~bash
javac CopyTextFile.java
java CopyTextFile input.txt output.txt
~~~

Nếu **input.txt** tồn tại, đọc được và không có lỗi ghi, chương trình in:

~~~text
Đã sao chép tệp.
~~~

**Files.newBufferedWriter** với tùy chọn mặc định sẽ tạo tệp đích nếu chưa có hoặc ghi đè nội dung hiện có. Không dùng cùng một đường dẫn cho nguồn và đích trong ví dụ này: việc mở đích có thể cắt ngắn tệp ngay khi nguồn còn đang đọc. Đoạn mã sao chép **dòng văn bản** và chuẩn hóa ký tự xuống dòng theo nền tảng; khi cần sao chép nguyên byte và metadata phù hợp, xem **Files.copy(...)**. Đối với dữ liệu bí mật hoặc quan trọng, cần chủ động thiết kế quy tắc ghi tệp tạm, xác thực kết quả và thay thế tệp đích an toàn.

Phần đóng tài nguyên có thể tự **flush** dữ liệu đệm theo hợp đồng Writer; tuy nhiên lỗi khi flush/close cũng có thể phát sinh. Không được giả định “đến cuối thân try” đồng nghĩa dữ liệu đã được ghi và đóng thành công. Với thao tác ghi quan trọng, để ngoại lệ lan ra hoặc xử lý minh bạch sau khi đóng.

## 5. Ngoại lệ khi đóng: primary và suppressed

Một khác biệt quan trọng giữa **try-with-resources** và khối **finally** viết thủ công là Java giữ được ngoại lệ có ý nghĩa chính khi cả thân **try** và **close()** đều thất bại.

- Nếu thân **try** ném ngoại lệ **A**, rồi **close()** ném ngoại lệ **B**, **A** tiếp tục là ngoại lệ chính; **B** được lưu trong **A.getSuppressed()**.
- Nếu thân **try** thành công nhưng **close()** thất bại, ngoại lệ từ **close()** được ném ra ngoài.
- Nếu có nhiều tài nguyên và nhiều lần đóng thất bại, ngoại lệ đóng đầu tiên xảy ra (theo thứ tự đóng ngược) có thể trở thành ngoại lệ chính khi thân **try** chưa thất bại; các ngoại lệ đóng còn lại được thêm dưới dạng suppressed.
- Nếu tạo tài nguyên tiếp theo thất bại, Java vẫn đóng các tài nguyên đã được tạo trước đó; lỗi đóng bổ sung cũng được gắn suppressed vào lỗi khởi tạo chính.

### Ví dụ chạy được: không làm mất lỗi nghiệp vụ

Tệp **SuppressedDemo.java**:

~~~java
public class SuppressedDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IllegalStateException("lỗi xử lý");
        } catch (Exception e) {
            System.out.println("primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("suppressed: " + suppressed.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac SuppressedDemo.java
java SuppressedDemo
~~~

Kết quả chuẩn:

~~~text
primary: lỗi xử lý
suppressed: lỗi đóng
~~~

Trong xử lý lỗi thực tế, nên ghi log đầy đủ **Throwable** hoặc kiểm tra **getSuppressed()** khi điều tra lỗi cleanup. Chỉ in **getMessage()** như ví dụ có thể bỏ mất stack trace. Ngoại lệ từ **close()** phải được quyết định xử lý dựa trên hợp đồng: có thể lan truyền, gói lại với nguyên nhân, báo lỗi cho người gọi hoặc ghi log khi không thể khôi phục. Không nuốt mọi lỗi đóng một cách âm thầm.

### Vì sao finally thủ công dễ che mất lỗi?

~~~java
// Minh họa vấn đề; không phải chương trình độc lập:
Resource resource = acquire();
try {
    use(resource);          // có thể ném lỗi A
} finally {
    resource.close();       // có thể ném lỗi B, che mất A
}
~~~

**try-with-resources** xử lý việc bảo toàn lỗi chính và lỗi suppressed một cách nhất quán. Nó cũng tránh quên đóng tài nguyên trên một nhánh **return** hoặc một nhánh ném ngoại lệ. Tuy nhiên, dù tự động đóng, tài nguyên vẫn có thể báo lỗi khi đóng, và chương trình phải chọn chiến lược xử lý đúng.

## 6. Khai báo nhiều tài nguyên và dùng biến có sẵn

### Khai báo nhiều tài nguyên

~~~java
try (InputStream source = Files.newInputStream(sourcePath);
     OutputStream target = Files.newOutputStream(targetPath)) {
    source.transferTo(target);
}
~~~

Đây là đoạn minh họa trong phạm vi phương thức đã có **sourcePath**, **targetPath** và các import tương ứng. **target** đóng trước **source**. Chỉ dùng khi hai đường dẫn hợp lệ và không trùng nhau; **Files.newOutputStream** mặc định có thể cắt ngắn tệp đích. Với một số wrapper, chỉ cần đóng wrapper ngoài cùng vì việc đóng của nó sẽ đóng luồng bên dưới; cần xác định rõ ai sở hữu luồng gốc.

### Java 9+: biến final hoặc effectively final

Từ Java 9 có thể dùng biến tài nguyên đã khai báo trước khối, miễn là biến đó **final hoặc effectively final**:

~~~java
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
~~~

Đây là đoạn mã minh họa trong một phương thức có **path**, import và xử lý **IOException** phù hợp. Biến **reader** không được gán lại sau khi khởi tạo; nếu gán lại, cú pháp **try (reader)** không hợp lệ. Sau khối **try**, biến có thể vẫn tồn tại về mặt phạm vi nhưng đối tượng đã đóng; không tiếp tục sử dụng nó như tài nguyên đang mở.

Cân nhắc khai báo tài nguyên **ngay trong try** khi có thể: cú pháp ấy cho biết phạm vi sở hữu rõ nhất và dễ kiểm tra hơn khi review.

### Có catch và finally

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
} catch (IOException e) {
    System.err.println("Không đọc được tệp: " + e.getMessage());
} finally {
    System.out.println("Đã kết thúc thao tác đọc");
}
~~~

Nếu quá trình mở, đọc hay đóng phát sinh **IOException**, nhánh **catch** có thể xử lý ngoại lệ đó. **finally** của câu lệnh chạy sau các lần đóng tài nguyên; không dùng nó để gọi **reader.close()** thêm lần nữa. Nếu đối tượng AutoCloseable cụ thể có phương thức **close()** khai báo kiểu ngoại lệ rộng hơn, kiểu ngoại lệ phải được bắt hoặc khai báo theo quy tắc Java.

## 7. Thiết kế lớp AutoCloseable của riêng bạn

Việc triển khai AutoCloseable hợp lý khi một đối tượng **thực sự sở hữu** một tài nguyên hữu hạn cần đóng theo thời điểm xác định (session, handle native, transaction scope, bộ thu thập dữ liệu...). Lớp nên ghi rõ ai tạo, ai đóng, các phương thức nào còn hợp lệ sau khi đóng và việc đóng nhiều lần có an toàn hay không.

Tệp **SessionDemo.java** là mô hình tối giản về trạng thái vòng đời; nó không mở kết nối mạng thật:

~~~java
public class SessionDemo {
    static final class Session implements AutoCloseable {
        private boolean closed;

        void send(String message) {
            if (closed) {
                throw new IllegalStateException("Session đã đóng");
            }
            System.out.println("send: " + message);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("session closed");
            }
        }
    }

    public static void main(String[] args) {
        try (Session session = new Session()) {
            session.send("hello");
        }
        System.out.println("finished");
    }
}
~~~

~~~bash
javac SessionDemo.java
java SessionDemo
~~~

Kết quả chuẩn:

~~~text
send: hello
session closed
finished
~~~

Ví dụ chủ động làm **close()** idempotent. Với tài nguyên thật, **close()** cần giải phóng hoặc bàn giao quyền sở hữu đúng cách; nếu lớp đang giữ nhiều tài nguyên, cần nghĩ tới thứ tự cleanup và xử lý khi một lần đóng thất bại. Nếu có đồng thời nhiều luồng thao tác, boolean **closed** đơn giản như ví dụ chưa đủ bảo đảm thread safety; phải có hợp đồng đồng bộ riêng. Không coi ví dụ mô phỏng như một session mạng production.

Nếu triển khai **AutoCloseable.close()** không thể phát sinh checked exception, có thể khai báo **public void close()** như ví dụ; người dùng lớp sẽ không phải bắt một **Exception** chung không cần thiết. Nếu có lỗi I/O, cân nhắc **Closeable**, **IOException** hoặc một loại exception cụ thể phù hợp API.

## 8. Ai là chủ tài nguyên? Ranh giới ownership

Câu hỏi quan trọng nhất trước khi thêm **try-with-resources** là: **đối tượng đang nằm trong phạm vi này có thuộc trách nhiệm đóng của mình không?**

- **Tạo và sở hữu**: phương thức tự gọi **Files.newInputStream** thường có trách nhiệm đóng stream đó, tốt nhất bằng try-with-resources.
- **Mượn để dùng**: nếu nhận một stream từ caller và hợp đồng nói caller quản lý vòng đời, không tự đóng stream trong helper; việc đóng sẽ làm caller bất ngờ và có thể phá các thao tác tiếp theo.
- **Chuyển quyền sở hữu**: nếu API trả về một AutoCloseable cho caller, ghi rõ rằng caller phải đóng. Đừng đóng ngay trước khi trả về đối tượng.
- **Wrapper**: đóng **BufferedReader** hoặc **BufferedInputStream** thông thường sẽ đóng nguồn bên dưới; không đưa thêm nguồn vào cùng try-with-resources chỉ để đóng trùng khi wrapper đã sở hữu nó, trừ khi hợp đồng yêu cầu.
- **Tài nguyên dùng chung**: không đặt một shared client hoặc shared pool vào try-with-resources của từng request nếu việc đóng có thể ảnh hưởng request khác.

Ví dụ API sở hữu rõ ràng:

~~~java
// Caller cung cấp stream và tiếp tục sở hữu stream:
static String firstLine(BufferedReader borrowed) throws IOException {
    return borrowed.readLine();     // helper không đóng borrowed
}

// Phương thức tự mở và tự đóng stream:
static String firstLine(Path path) throws IOException {
    try (BufferedReader owned = Files.newBufferedReader(path)) {
        return owned.readLine();
    }
}
~~~

Hai phương thức trên là **các đoạn phương thức minh họa**, cần đặt trong lớp Java với import thích hợp. Chúng có kết quả đọc như nhau nhưng trách nhiệm đóng rất khác. Tránh lập trình “đóng cho chắc” khi chưa xác định ownership.

## 9. Trường hợp quen thuộc ngoài file I/O

### JDBC

Các loại tài nguyên JDBC chính (**Connection**, **Statement/PreparedStatement**, **ResultSet**) đều có thể được quản lý bằng try-with-resources. Ví dụ khi **dataSource** đã được cung cấp và SQL trả về dữ liệu:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("SELECT name FROM users WHERE id = ?")) {
    statement.setLong(1, userId);

    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            System.out.println(rows.getString("name"));
        }
    }
}
~~~

Đây là đoạn mã **minh họa, không phải chương trình độc lập**: cần import **java.sql.***, đối tượng **dataSource**, **userId**, schema tương ứng và xử lý **SQLException**. Thứ tự đóng: ResultSet, PreparedStatement, Connection. Với connection pool, gọi **close()** trên proxy kết nối thường là thao tác trả kết nối về pool, theo hợp đồng pool.

**Đóng tài nguyên không thay thế quản lý transaction**. Với JDBC giao dịch thủ công, phải xác định rõ lúc **commit/rollback**; không giả định Connection.close() tự commit thay nghiệp vụ. Việc rollback tự động, nếu có, phụ thuộc driver/pool và cấu hình.

### Files.lines và Stream

**Stream** cũng có cơ chế **close()**, nhưng không phải mọi stream đều nắm tài nguyên ngoài heap. Ví dụ **Files.lines(path)** duy trì nguồn đọc bên dưới nên cần đóng:

~~~java
try (java.util.stream.Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(line -> !line.isBlank()).count();
    System.out.println(count);
}
~~~

Đoạn này thuộc một phương thức có **path**, các import và xử lý **IOException** phù hợp. Trái lại, stream tạo từ **list.stream()** thường không có tài nguyên cần giải phóng. Với stream từ file, tránh trả **Stream** ra ngoài một **try** đã đóng: caller sẽ nhận một stream mà nguồn đọc có thể đã đóng. Nếu cần trả stream, phải chuyển rõ trách nhiệm đóng cho caller hoặc trả dữ liệu đã vật hóa.

### Scanner và System.in

**Scanner** triển khai Closeable. Nhưng **new Scanner(System.in)** được đóng sẽ đóng luôn nguồn **System.in** bên dưới. Nếu code chỉ mượn đầu vào chuẩn của cả ứng dụng, đừng tùy tiện đóng nó trong một helper ngắn; quyết định đóng thuộc về tầng quản lý vòng đời ứng dụng.

## 10. Các lỗi phổ biến và cách tránh

| Lỗi | Tác động | Cách làm phù hợp |
| --- | --- | --- |
| Mở stream/connection rồi chỉ đóng ở nhánh thành công | Rò rỉ tài nguyên khi có exception/return | Đặt tài nguyên sở hữu trong try-with-resources |
| Tin GC sẽ tự đóng file đúng lúc | Giữ handle/connection không dự đoán được | Đóng tường minh tại ranh giới sở hữu |
| Gọi close() trên tài nguyên caller cho mượn | Caller nhận tài nguyên đã đóng | Nêu rõ và tôn trọng ownership |
| Đóng wrapper và nguồn gốc không rõ hợp đồng | Đóng lặp; lớp AutoCloseable có thể không idempotent | Nắm chuỗi sở hữu, đóng đúng đối tượng |
| Bắt Exception rồi bỏ qua toàn bộ | Che lỗi nghiệp vụ hoặc lỗi cleanup | Xử lý hoặc lan truyền lỗi có thông tin |
| Chỉ log ngoại lệ chính | Mất dấu lỗi khi close() thất bại | Kiểm tra suppressed/ghi log stack trace |
| Trả về tài nguyên sau khi đã kết thúc try | Người nhận dùng đối tượng đã đóng | Trả dữ liệu hoặc chuyển ownership rõ ràng |
| Giữ connection quá lâu trong khối try | Cạn pool, tăng thời gian giữ lock | Thu hẹp phạm vi sử dụng |
| Đưa tài nguyên dùng chung vào try từng request | Đóng sớm, hỏng tác vụ khác | Để owner cấp cao quản lý lifecycle |
| Mở công việc bất đồng bộ rồi rời try ngay | Worker có thể dùng tài nguyên đã đóng | Đợi công việc hoàn thành trong scope hoặc chuyển ownership có kiểm soát |

### Lưu ý với bất đồng bộ và đa luồng

**try-with-resources** quản lý một **phạm vi từ vựng đồng bộ**: nó gọi close khi việc thực thi rời block. Nó **không tự đợi** một **CompletableFuture**, thread mới hoặc callback dùng tài nguyên được khởi chạy trong block. Nếu callback tiếp tục sau khi block thoát, tài nguyên có thể đã đóng. Hãy đặt toàn bộ thời gian sử dụng tài nguyên trong scope hoặc thiết kế một chủ sở hữu sống đủ lâu để đóng khi tác vụ bất đồng bộ thực sự kết thúc. **AutoCloseable** cũng không mặc nhiên bảo đảm việc dùng/đóng đồng thời là an toàn.

## 11. Quy tắc kiểm tra khi review code

Khi đọc một đoạn mã Java có tài nguyên, lần lượt xác nhận:

1. **Tài nguyên là gì?** Nó sở hữu file descriptor, socket, cursor, connection hay handle nào cần kết thúc đúng lúc?
2. **Ai sở hữu?** Code hiện tại tạo, mượn hay nhận chuyển giao ownership?
3. **Mở có thành công từng phần không?** Nếu mở tài nguyên thứ hai thất bại, tài nguyên thứ nhất đã được dọn chưa?
4. **Mọi đường thoát đều đóng chưa?** Thành công, **return**, lỗi khởi tạo, lỗi xử lý và lỗi đóng đều cần xét.
5. **Thứ tự đóng phù hợp không?** Tài nguyên phụ thuộc thường cần đóng trước chủ sở hữu của nó.
6. **Lỗi close() được thấy không?** Có mất nguyên nhân gốc, có suppressed exception cần quan sát không?
7. **Phạm vi đủ ngắn và đủ dài chưa?** Đừng giữ tài nguyên vô ích; cũng đừng đóng trước khi tác vụ đang dùng kết thúc.
8. **Hợp đồng thư viện cụ thể nói gì?** Closeable, JDBC pool, wrapper I/O, stream từ Files và custom AutoCloseable có ngữ nghĩa khác nhau.

## 12. Bài tập tự kiểm tra

**Bài 1 — Dự đoán thứ tự.** Với hai tài nguyên **A** rồi **B** trong cùng try-with-resources, thân try in **body**. Trình tự liên quan đến đóng là gì?

Đáp án: **body**, rồi **B.close()**, rồi **A.close()**; nếu constructor có in log thì thông báo khởi tạo theo **A** trước **B**.

**Bài 2 — Lỗi kép.** Thân try ném **IllegalStateException("business")**, tài nguyên close ném **IOException("close")**. Ngoại lệ nào được ném ra ngoài?

Đáp án: **IllegalStateException("business")** là ngoại lệ chính; **IOException("close")** nằm trong **getSuppressed()** của ngoại lệ chính (giả sử không có ngoại lệ bất thường khác).

**Bài 3 — Review ownership.** Một helper nhận **InputStream** do caller quản lý, chỉ cần đọc header. Có nên đặt stream vào **try (input)** trong helper không?

Đáp án: Không, nếu hợp đồng nói caller sở hữu. Helper đọc và để caller tự đóng. Chỉ nhận quyền đóng khi API quy định chuyển ownership rõ ràng.

**Bài 4 — Bất đồng bộ.** Một tác vụ nền còn đọc tệp khi khối try chứa stream vừa kết thúc. Chuyện gì có thể xảy ra?

Đáp án: Luồng đọc nền có thể gặp lỗi do nguồn đã đóng. Phải tổ chức vòng đời để đóng sau khi tác vụ hoàn tất.

## 13. Ghi nhớ

**AutoCloseable** là hợp đồng tài nguyên có thể được đóng; **try-with-resources** biến hợp đồng đó thành cleanup tự động, theo thứ tự ngược khi có nhiều tài nguyên và bảo toàn ngoại lệ chính bằng suppressed exception. Dùng nó khi **scope hiện tại sở hữu tài nguyên**, phối hợp xử lý lỗi close, theo dõi vòng đời tài nguyên qua async và tuân theo hợp đồng riêng của từng API. Quản lý bộ nhớ bằng GC không thay thế được quản lý tài nguyên tường minh.
