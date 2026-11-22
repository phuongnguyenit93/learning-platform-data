# Đóng tài nguyên bằng AutoCloseable và try-with-resources trong Java 17+

## 1. Tại sao có garbage collector mà vẫn phải đóng tài nguyên?

Java quản lý bộ nhớ heap bằng cơ chế garbage collection (GC). Khi một object không còn reachable, JVM có thể thu hồi bộ nhớ của object ấy vào một thời điểm **không được bảo đảm**. Nhưng một Java object có thể đang **sở hữu tài nguyên bên ngoài heap**, chẳng hạn file descriptor, socket, kết nối cơ sở dữ liệu, native handle hoặc file lock. Những tài nguyên đó thường cần kết thúc đúng thời điểm của một nghiệp vụ, thay vì đợi GC.

Hai cơ chế giải quyết hai trách nhiệm khác nhau:

- **Garbage collection:** quản lý khả năng thu hồi memory của những objects không còn được chương trình truy cập.
- **`close()` và `try-with-resources`:** quản lý vòng đời của resource có trách nhiệm đóng, trên đường điều khiển cụ thể của chương trình.

`AutoCloseable` là interface diễn đạt thao tác kết thúc tài nguyên. `try-with-resources`, viết tắt TWR, là cú pháp `try` giúp **tự gọi `close()`** trên resource đã khởi tạo thành công khi thoát scope, kể cả lúc body ném exception.

~~~java
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(
                     new java.io.StringReader("Java"))) {
    System.out.println(reader.readLine());
}
~~~

Đây là snippet hợp lệ nếu được đặt trong một method có khai báo hoặc xử lý `IOException`. Reader được đóng khi block kết thúc. Chỉ vì biến reader hết scope **không** có nghĩa GC đã chạy; điều được bảo đảm ở đây đến từ TWR.

Bài thuộc **Java core – class-object**, nhóm **Vòng đời đối tượng**, chủ đề **Đóng tài nguyên bằng AutoCloseable và try-with-resources**. Các chương trình độc lập bên dưới dùng **Java 17+**, không bật preview; mỗi ví dụ hoàn chỉnh đều có tên file, lệnh `javac`/`java` và output xác định. Những snippets chỉ nhằm mô tả cú pháp được đánh dấu tách biệt.

## 2. Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

1. Phân biệt object lifetime trên heap với **resource ownership/lifetime**.
2. Đọc và implement `AutoCloseable.close()` đúng chữ ký.
3. Dùng TWR với một resource, nhiều resources và biến đã khai báo trước `try`.
4. Giải thích **mở từ trái sang phải, đóng từ phải sang trái**.
5. Dự đoán việc đóng nếu body throw, return hoặc resource thứ hai khởi tạo thất bại.
6. Phân biệt **primary exception** và **suppressed exceptions**.
7. Giải thích vì sao `AutoCloseable` và `Closeable` không hoàn toàn đồng nghĩa.
8. Xử lý checked exceptions của `close()`.
9. Biết tránh đóng trùng khi wrapper sở hữu underlying stream.
10. Dùng TWR với `BufferedReader`, file streams, `Files.lines` và JDBC.
11. Không tự đóng resource chỉ được mượn từ caller/framework.
12. Thiết kế `close()` idempotent khi thích hợp và xem xét use-after-close.
13. Biết khi nào phải dùng `finally` thay vì TWR.
14. Nhớ `ExecutorService` và `Lock` của Java 17 không trực tiếp là AutoCloseable.
15. Kiểm thử cleanup mà không dựa vào finalizer, Cleaner hoặc GC timing.

## 3. `AutoCloseable`: hợp đồng đóng tài nguyên

Chữ ký public API Java 17 có dạng:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

Đây là mô tả interface có sẵn trong JDK, **không phải source cần tự tạo**. Phương thức quan trọng duy nhất là `close()`; nó có return type `void`. Interface cho phép ném checked `Exception` nhưng implementation có thể khai exception **hẹp hơn**, ví dụ `IOException`, hoặc không khai bất kỳ checked exception nào.

Một class tự implement:

~~~java
final class Lease implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("released");
    }
}
~~~

Đây là một khai báo class hợp lệ. Vì `close()` không khai checked exception, code sử dụng `Lease` trong TWR không cần bắt Exception chỉ vì thao tác đóng.

`AutoCloseable` không tự cấp phát, không tự đồng bộ nhiều threads và không tự làm hành vi đóng an toàn nếu gọi hai lần. Tất cả còn tùy contract của concrete resource type.

## 4. Cú pháp và phạm vi cơ bản

Mẫu mô tả:

~~~text
try (ResourceType resource = expressionCreatingResource) {
    statementsUsingResource
}
~~~

Đây là **mẫu diễn giải**, không phải Java source runnable. Resource expression cần có kiểu là subtype của AutoCloseable; biến resource khai báo trong header có tính **implicitly final** và được sử dụng trong try body.

Khi body kết thúc bình thường, TWR cố gọi close trước khi chương trình đi tiếp. Khi body kết thúc bất thường, ví dụ vì exception hoặc return, TWR vẫn thực hiện cleanup theo các quy tắc JLS.

Một ích lợi lớn so với `finally` viết tay là xử lý **suppressed exceptions** khi nhiều chỗ cùng ném lỗi.

## 5. Chương trình hoàn chỉnh 1 — open, work, close

Tạo tệp **`BasicAutoCloseDemo.java`**:

~~~java
final class DemoResource implements AutoCloseable {
    DemoResource() {
        System.out.println("opened");
    }

    void work() {
        System.out.println("working");
    }

    @Override
    public void close() {
        System.out.println("closed");
    }
}

public class BasicAutoCloseDemo {
    public static void main(String[] args) {
        try (DemoResource resource = new DemoResource()) {
            resource.work();
        }
        System.out.println("after try");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BasicAutoCloseDemo.java
java BasicAutoCloseDemo
~~~

**Stdout:**

~~~text
opened
working
closed
after try
~~~

`close()` chạy **trước** statement sau try. Không có `System.gc()`; cơ chế đóng này dựa vào luồng điều khiển, không chờ object biến mất khỏi heap.

## 6. Body ném exception: tài nguyên vẫn được đóng

Một lập trình viên chỉ gọi `stream.close()` ở cuối happy path có thể bỏ sót tài nguyên khi việc đọc/ghi ném exception giữa chừng. TWR giải quyết đường lỗi phổ biến này.

Quy tắc đơn giản:
- Resource được tạo thành công.
- Body bắt đầu.
- Body có thể throw.
- Trước khi catch bên ngoài được chạy, Java cố đóng resource.
- Nếu close không ném thêm exception, exception từ body tiếp tục đi tới handler.

TWR đảm bảo **thực hiện lời gọi close** theo luật ngôn ngữ, không đảm bảo rằng `close()` luôn hoàn tất thành công.

## 7. Chương trình hoàn chỉnh 2 — đóng trước catch

Tệp **`FailureCleanupDemo.java`**:

~~~java
final class UnitOfWork implements AutoCloseable {
    void execute() {
        System.out.println("execute");
        throw new IllegalStateException("failed");
    }

    @Override
    public void close() {
        System.out.println("close");
    }
}

public class FailureCleanupDemo {
    public static void main(String[] args) {
        try (UnitOfWork unit = new UnitOfWork()) {
            unit.execute();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
        System.out.println("end");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FailureCleanupDemo.java
java FailureCleanupDemo
~~~

**Stdout:**

~~~text
execute
close
caught=failed
end
~~~

Đầu tiên body in `execute`; sau đó throw; resource close được gọi trước catch. Dù UnitOfWork object vẫn có thể chưa được GC thu gom, resource lifecycle của nó đã được kết thúc tường minh.

## 8. Nhiều resources: khởi tạo từ trái qua phải, đóng ngược

Với:

~~~java
try (A a = openA();
     B b = openB();
     C c = openC()) {
    use(a, b, c);
}
~~~

Đây là snippet **cú pháp minh họa**, cần A/B/C và methods được định nghĩa nếu muốn chạy.

Nếu tất cả khởi tạo thành công, Java mở/đánh giá resources từ **A → B → C**, rồi đóng **C → B → A**. Điều này tương tự ngăn xếp LIFO và thường hợp lý với dependencies: resource ở tầng trong có thể dựa vào tầng ngoài.

Khi close của C thất bại, Java vẫn cố đóng B và A. Lỗi tiếp theo được xử lý theo luật primary/suppressed exceptions.

## 9. Chương trình hoàn chỉnh 3 — thứ tự đóng LIFO

Tệp **`MultiResourceDemo.java`**:

~~~java
final class NamedResource implements AutoCloseable {
    private final String name;

    NamedResource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}

public class MultiResourceDemo {
    public static void main(String[] args) {
        try (NamedResource a = new NamedResource("A");
             NamedResource b = new NamedResource("B");
             NamedResource c = new NamedResource("C")) {
            System.out.println("body");
        }
        System.out.println("finished");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 MultiResourceDemo.java
java MultiResourceDemo
~~~

**Stdout:**

~~~text
open A
open B
open C
body
close C
close B
close A
finished
~~~

Đây là quy tắc deterministic của TWR, không liên quan tới thứ tự GC xem xét ba objects.

## 10. Resource thứ hai không mở được: resource thứ nhất vẫn được đóng

Nếu Java đã mở A nhưng lời gọi để mở B thất bại, A phải được đóng mặc dù try body **chưa chạy**. Đây là quy tắc đặc biệt quan trọng khi thu nhận nhiều file/connection theo một thao tác.

Nếu **constructor của B** ném sau khi đã tạo một resource native bên trong, TWR không thể tự biết resource ẩn đó để đóng; bản thân constructor/factory phải bảo đảm **exception safety trong giai đoạn khởi tạo**.

Một số người mới học tưởng TWR chỉ quản lý resources sau khi vào thân try. Thực tế, failure ngay ở phần header cũng có cleanup đối với những resources đã được khởi tạo thành công.

## 11. Chương trình hoàn chỉnh 4 — thất bại khi mở B

Tệp **`OpenFailureDemo.java`**:

~~~java
final class Channel implements AutoCloseable {
    private final String name;

    Channel(String name, boolean fail) {
        System.out.println("opening " + name);
        if (fail) {
            throw new IllegalStateException("bad-" + name);
        }
        this.name = name;
    }

    @Override
    public void close() {
        System.out.println("closing " + name);
    }
}

public class OpenFailureDemo {
    public static void main(String[] args) {
        try (Channel a = new Channel("A", false);
             Channel b = new Channel("B", true)) {
            System.out.println("body");
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OpenFailureDemo.java
java OpenFailureDemo
~~~

**Stdout:**

~~~text
opening A
opening B
closing A
caught=bad-B
~~~

B không hoàn tất constructor, nên không có một completed B resource để TWR đóng; A đã mở và được đóng. Body không chạy.

## 12. Checked exceptions và `throws` của close

`AutoCloseable.close()` được khai với `throws Exception`, nên nếu bạn giữ resource ở **static type `AutoCloseable`**, enclosing method có thể cần khai `throws Exception` hoặc catch.

Một concrete class override:

~~~java
@Override
public void close() {
    // cleanup without checked exception
}
~~~

không bắt caller xử lý checked exception từ close qua static type của class đó. Điều này giải thích vì sao `main` trong BasicAutoCloseDemo không khai `throws Exception`.

Với I/O, nhiều classes implement `java.io.Closeable`, có `close() throws IOException`. Nên để error types cụ thể ở API, không tùy tiện khai `throws Exception` khắp ứng dụng.

## 13. Primary và suppressed exceptions: hai nơi cùng lỗi

Giả sử body ném IOException("body"), trong khi `close()` của resource cũng ném IOException("close"). Nếu viết `finally` thủ công không cẩn thận, lỗi close có thể **che lỗi body**.

TWR có cơ chế đặc biệt:
- Exception từ body trở thành **primary exception**.
- Exception xảy ra trong cleanup được gắn vào primary dưới dạng **suppressed**.
- Caller xem danh sách bằng `Throwable.getSuppressed()`.
- Với nhiều tài nguyên, suppressed exceptions thường xuất hiện theo thứ tự thất bại khi close (ngược thứ tự mở).

Nếu body **không** ném mà close ném, lỗi close trở thành primary.

## 14. Chương trình hoàn chỉnh 5 — hai suppressed exceptions

Tệp **`SuppressedDemo.java`**:

~~~java
import java.io.IOException;

final class BrokenClose implements AutoCloseable {
    private final String name;

    BrokenClose(String name) {
        this.name = name;
    }

    @Override
    public void close() throws IOException {
        System.out.println("close " + name);
        throw new IOException("close-" + name);
    }
}

public class SuppressedDemo {
    public static void main(String[] args) {
        try (BrokenClose a = new BrokenClose("A");
             BrokenClose b = new BrokenClose("B")) {
            throw new IOException("body");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("count=" + ex.getSuppressed().length);
            for (Throwable t : ex.getSuppressed()) {
                System.out.println("suppressed=" + t.getMessage());
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SuppressedDemo.java
java SuppressedDemo
~~~

**Stdout:**

~~~text
close B
close A
primary=body
count=2
suppressed=close-B
suppressed=close-A
~~~

B và A lần lượt ném trong `close()`, nhưng body exception vẫn giữ nguyên tính primary. Trong production logging, nên bảo toàn cả cause và suppressed data khi cần debug.

## 15. Chỉ close thất bại: lỗi close trở thành primary

TWR không “nuốt” lỗi close nếu thân try không có lỗi. Ví dụ đóng một Writer có thể trigger flush; nếu underlying I/O gặp lỗi lúc đóng, caller phải được thông báo theo exception contract.

Không nên đánh đồng “toàn bộ dòng `write()` đã được gọi” với “dữ liệu đã được hoàn tất thành công trên thiết bị”. Tùy API, lỗi có thể chỉ xuất hiện ở close.

## 16. Chương trình hoàn chỉnh 6 — lỗi chỉ xảy ra lúc close

Tệp **`CloseOnlyFailureDemo.java`**:

~~~java
import java.io.IOException;

final class WriterLike implements AutoCloseable {
    @Override
    public void close() throws IOException {
        System.out.println("close attempt");
        throw new IOException("flush failed");
    }
}

public class CloseOnlyFailureDemo {
    public static void main(String[] args) {
        try (WriterLike output = new WriterLike()) {
            System.out.println("body succeeded");
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
            System.out.println("suppressed count="
                    + ex.getSuppressed().length);
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CloseOnlyFailureDemo.java
java CloseOnlyFailureDemo
~~~

**Stdout:**

~~~text
body succeeded
close attempt
caught=flush failed
suppressed count=0
~~~

Vì body hoàn thành bình thường, close exception là primary. Không có lỗi thứ hai để suppressed.

## 17. Return, break và continue có bỏ qua close không?

Không. Khi `return` trong thân TWR, biểu thức return được đánh giá, Java thực hiện cleanup resource trước khi caller nhận giá trị trả về. Khi `break` hoặc `continue` làm control rời khỏi vùng quản lý, close cũng được thực hiện theo luật Java.

Nếu close ném exception, một lệnh return đang được chuẩn bị có thể không hoàn tất tới caller. Đây là hậu quả quan trọng nếu resource được đóng khi method trả một kết quả thành công giả định.

Không nên đặt side effects bất ngờ trong close khiến caller hiểu sai trạng thái transaction.

## 18. Chương trình hoàn chỉnh 7 — close trước return

Tệp **`ReturnCleanupDemo.java`**:

~~~java
final class Gate implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("gate closed");
    }
}

public class ReturnCleanupDemo {
    static int answer() {
        try (Gate gate = new Gate()) {
            System.out.println("computing");
            return 42;
        }
    }

    public static void main(String[] args) {
        System.out.println("result=" + answer());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ReturnCleanupDemo.java
java ReturnCleanupDemo
~~~

**Stdout:**

~~~text
computing
gate closed
result=42
~~~

Dù có return trong body, close vẫn diễn ra trước khi caller in kết quả.

## 19. Biến resource khai trong header là implicitly final

Cú pháp:

~~~java
try (SomeResource resource = create()) {
    resource.use();
}
~~~

là mẫu cần SomeResource/create được định nghĩa. Reference `resource` trong header là **implicitly final**. Không thể gán `resource = other` trong thân try để đổi object được theo dõi.

Điều này khác với tính mutable của object: resource vẫn có thể tăng file cursor, gửi bytes, ghi buffer và chuyển từ trạng thái OPEN sang CLOSED. Final ở đây khóa **biến reference**, không khiến resource trở thành immutable object.

Nếu cần mở một resource mới, hãy tạo một scope TWR mới hoặc đăng ký resource thứ hai ở header, thay vì cố gán lại biến resource cũ.

## 20. Biến resource đã có: tính năng Java 9+, có trong Java 17

Từ Java 9, có thể viết:

~~~java
SomeResource resource = create();
try (resource) {
    resource.use();
}
~~~

Đây là snippet cần SomeResource/create. Điều kiện: biến local `resource` **final hoặc effectively final**. Effectively final nghĩa là không được gán lại theo quy tắc biên dịch, dù không viết keyword `final`.

Vì biến được khai bên ngoài, reference có thể **vẫn nằm trong scope sau try**, nhưng tài nguyên đã đóng. Vì vậy, không tiếp tục gọi những operation đòi resource mở chỉ vì bạn còn có biến để gọi.

Nếu biến được gán lại làm mất tính effectively final, `try (resource)` bị từ chối lúc biên dịch.

## 21. Chương trình hoàn chỉnh 8 — existing resource variable

Tệp **`ExistingVariableDemo.java`**:

~~~java
final class Permit implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("closed");
        }
        System.out.println("permit used");
    }

    boolean closed() {
        return closed;
    }

    @Override
    public void close() {
        closed = true;
        System.out.println("permit closed");
    }
}

public class ExistingVariableDemo {
    public static void main(String[] args) {
        Permit permit = new Permit();

        try (permit) {
            permit.use();
        }

        System.out.println("closed flag=" + permit.closed());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ExistingVariableDemo.java
java ExistingVariableDemo
~~~

**Stdout:**

~~~text
permit used
permit closed
closed flag=true
~~~

Resource reference vẫn còn, nhưng object đã chuyển sang trạng thái CLOSED. TWR xử lý **resource lifetime**, không nhất thiết làm object biến mất khỏi memory.

## 22. Null resource: Java không gọi close trên null

Nếu resource value là null, TWR bỏ qua bước gọi close cho resource ấy, không ném NullPointerException chỉ vì cleanup.

Ví dụ:

~~~java
AutoCloseable resource = null;
try (resource) {
    System.out.println("body");
}
~~~

Snippet hợp lệ trong method khai `throws Exception` hoặc xử lý checked exception. Lưu ý nếu body tự gọi `resource.close()` thì NPE vẫn có thể xảy ra bình thường.

## 23. Chương trình hoàn chỉnh 9 — null resource

Tệp **`NullResourceDemo.java`**:

~~~java
public class NullResourceDemo {
    public static void main(String[] args) throws Exception {
        AutoCloseable resource = null;

        try (resource) {
            System.out.println("body");
        }

        System.out.println("done");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NullResourceDemo.java
java NullResourceDemo
~~~

**Stdout:**

~~~text
body
done
~~~

`main` khai `throws Exception` do static type AutoCloseable có close() throws Exception. Runtime value null khiến cleanup không cần gọi close.

## 24. `Closeable` và `AutoCloseable`: khác gì?

`java.io.Closeable` **extends AutoCloseable**, với chữ ký `void close() throws IOException`. Nó phục vụ đặc biệt cho I/O resources, thay vì mọi loại resources tùy ý.

| Đặc điểm | AutoCloseable | Closeable |
| --- | --- | --- |
| Package | `java.lang` | `java.io` |
| Interface method | `close() throws Exception` | `close() throws IOException` |
| Dùng TWR | Có | Có |
| Checked close exception | Có thể rộng | Hẹp hơn, IOException |
| Gọi close nhiều lần | Không có cam kết idempotent chung | Contract Closeable nói gọi close trên stream đã đóng không gây tác dụng nữa |
| GC giải phóng đúng hạn? | Không | Không |

Một concrete class có thể override close không throws để caller không phải catch checked exception. Khi thiết kế API, nên khai ngoại lệ có ý nghĩa, không vô cớ nâng lên Exception.

## 25. Chương trình hoàn chỉnh 10 — `Closeable` I/O

Tệp **`CloseableDemo.java`**:

~~~java
import java.io.Closeable;
import java.io.IOException;

final class Channel implements Closeable {
    void read() {
        System.out.println("read");
    }

    @Override
    public void close() throws IOException {
        System.out.println("closed");
    }
}

public class CloseableDemo {
    public static void main(String[] args) throws IOException {
        try (Channel channel = new Channel()) {
            channel.read();
        }
        System.out.println("finished");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CloseableDemo.java
java CloseableDemo
~~~

**Stdout:**

~~~text
read
closed
finished
~~~

Chữ ký IOException của `close()` được phép theo interface Closeable. Example chạy bình thường nhưng vẫn khai IOException để xử lý đúng compile-time contract.

## 26. AutoCloseable có thể là lambda target

Vì AutoCloseable có một abstract method `close()`, bạn có thể khai một lambda có static type AutoCloseable và đăng ký nó trong TWR. Hình thức này phù hợp với một số cleanup actions rất nhỏ.

Không nên dùng lambda cleanup để che giấu ownership hoặc mối quan hệ giữa nhiều resources phức tạp. Một class có tên thường tốt hơn khi cần state machine và diagnostics.

## 27. Chương trình hoàn chỉnh 11 — lambda cleanup

Tệp **`LambdaCleanupDemo.java`**:

~~~java
public class LambdaCleanupDemo {
    public static void main(String[] args) throws Exception {
        AutoCloseable action =
                () -> System.out.println("cleanup action");

        try (action) {
            System.out.println("work");
        }

        System.out.println("end");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LambdaCleanupDemo.java
java LambdaCleanupDemo
~~~

**Stdout:**

~~~text
work
cleanup action
end
~~~

Lambda không mở file thật, chỉ mô phỏng một thao tác cleanup. Khi try kết thúc, Java gọi `action.close()` và chạy lambda.

## 28. `BufferedReader`, `StringReader` và wrapper ownership

Nếu một `BufferedReader` bọc một `StringReader` hoặc file reader, đóng wrapper thường **đóng underlying reader** theo contract của wrapper. Do đó không cần mặc định đăng ký cả hai ở hai resource declarations khác nhau.

Trường hợp phổ biến:

~~~java
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(
                     new java.io.StringReader("first\nsecond"))) {
    System.out.println(reader.readLine());
}
~~~

Đây là snippet cần IOException handling. Reader bên trong là dữ liệu chuỗi có sẵn, không mở file descriptor hệ điều hành; nhưng TWR vẫn minh họa ownership và close.

Với wrapper native hoặc custom, cần xem API quy định **wrapper sở hữu underlying resource hay chỉ mượn nó**. Tránh double-close nếu đóng wrapper đã đóng underlying rồi và underlying không bảo đảm idempotent.

## 29. Chương trình hoàn chỉnh 12 — reader hai dòng

Tệp **`BufferedReaderDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class BufferedReaderDemo {
    public static void main(String[] args) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(
                             new StringReader("alpha\nbeta\n"))) {
            System.out.println("one=" + reader.readLine());
            System.out.println("two=" + reader.readLine());
            System.out.println("end=" + (reader.readLine() == null));
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BufferedReaderDemo.java
java BufferedReaderDemo
~~~

**Stdout:**

~~~text
one=alpha
two=beta
end=true
~~~

TWR đóng BufferedReader ở cuối body; việc đã đọc đến EOF không nhất thiết là một replacement cho close.

## 30. Đọc file thực và xử lý temporary files

`Files.newBufferedReader(path, charset)` tạo BufferedReader tương ứng file path, cần đóng. TWR đảm bảo reader được cố đóng khi đã đọc xong hoặc gặp exception.

Nhưng **đóng reader không xóa file**. Nếu application tự tạo temporary file rồi muốn xóa sau khi đọc, đó là một hành động độc lập cần tổ chức ở `finally` hoặc cleanup policy khác. Đồng thời, I/O có thể thất bại do môi trường, permissions, disk full, nên expected stdout chỉ nên mô tả luồng thành công.

## 31. Chương trình hoàn chỉnh 13 — file tạm với UTF-8

Tệp **`TemporaryFileDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TemporaryFileDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lesson-", ".txt");

        try {
            Files.writeString(
                    file, "Java\nseventeen\n",
                    StandardCharsets.UTF_8);

            try (BufferedReader reader =
                         Files.newBufferedReader(
                                 file, StandardCharsets.UTF_8)) {
                System.out.println(reader.readLine());
                System.out.println(reader.readLine());
            }

            System.out.println("reader scope ended");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 TemporaryFileDemo.java
java TemporaryFileDemo
~~~

**Stdout khi hệ thống cho phép tạo/đọc/xóa file tạm:**

~~~text
Java
seventeen
reader scope ended
~~~

Tên file tạm không được in nên output không phụ thuộc đường dẫn ngẫu nhiên. TWR đóng BufferedReader trước `finally` xóa file.

## 32. `Files.lines` trả một `Stream` cần close

Không phải mọi `Stream<T>` đều giữ external resource. Nhưng `Files.lines(Path)` trả một stream backed bởi file; tài liệu API yêu cầu đóng stream đó sau khi sử dụng.

~~~java
try (java.util.stream.Stream<String> lines =
             java.nio.file.Files.lines(path)) {
    long count = lines.count();
}
~~~

Đây là snippet yêu cầu Path hợp lệ và IOException handling. Terminal operation `count()` **không thay thế** hành động close cần thiết của file-backed stream.

Một stream tạo từ `List.of(...).stream()` thông thường không nắm file/socket, nên việc đóng stream ấy không phải cùng loại yêu cầu resource ownership.

## 33. Chương trình hoàn chỉnh 14 — Files.lines

Tệp **`FilesLinesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FilesLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lines-", ".txt");
        try {
            Files.writeString(file, "one\n\ntwo\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                long nonBlank = lines
                        .filter(s -> !s.isBlank())
                        .count();
                System.out.println("nonblank=" + nonBlank);
            }
            System.out.println("stream closed");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FilesLinesDemo.java
java FilesLinesDemo
~~~

**Stdout trong môi trường file tạm hoạt động bình thường:**

~~~text
nonblank=2
stream closed
~~~

Hai dòng có chữ là one và two; dòng rỗng không được đếm. Stream được đóng trước khi xóa file.

## 34. JDBC: Connection, PreparedStatement và ResultSet

Một truy vấn JDBC có thể nắm nhiều resources với quan hệ:

~~~text
Connection
    |
    +-- PreparedStatement
            |
            +-- ResultSet
~~~

Mẫu tích hợp:

~~~java
try (java.sql.Connection connection =
             dataSource.getConnection();
     java.sql.PreparedStatement statement =
             connection.prepareStatement(
                     "SELECT name FROM users WHERE id = ?")) {

    statement.setLong(1, userId);

    try (java.sql.ResultSet results =
                 statement.executeQuery()) {
        while (results.next()) {
            consume(results.getString("name"));
        }
    }
}
~~~

Đây là **snippet tích hợp**, không phải chương trình standalone: cần `dataSource`, `userId`, `consume` và database/driver. ResultSet đóng trước statement/connection theo nesting của TWR.

Với **connection pool**, `Connection.close()` có thể trả logical connection về pool thay vì đóng physical network connection. TWR vẫn nên được dùng khi caller được giao ownership phù hợp.

## 35. TWR không tự commit hoặc rollback transaction

TWR chỉ kiểm soát việc **cố đóng** resources. Nó không hứa thực thi một transaction policy bất kỳ:

- Với manual JDBC transaction, caller thường phải set autoCommit theo nhu cầu.
- Khi thành công, business logic quyết định `commit()`.
- Khi lỗi, nó cần `rollback()` nếu thích hợp, đồng thời xử lý lỗi rollback nếu có.
- Cuối cùng Connection được đóng/trả pool theo ownership.
- Với transaction do framework quản lý, hãy để framework quản lý lifecycle và commit/rollback; đừng tự đóng connection mà không được quyền.

Không suy rằng việc `close()` connection sẽ tự tạo một transaction commit theo business intent. Semantics khi đóng một connection còn transaction chưa hoàn thành phụ thuộc JDBC contract/driver/pool và không nên là nền tảng của nghiệp vụ quan trọng.

## 36. Tránh đóng nhầm tài nguyên “đi mượn”

Một reference được truyền vào method **không nhất thiết chuyển ownership**.

~~~java
static void append(java.io.Writer writer)
        throws java.io.IOException {
    writer.write("hello");
}
~~~

Đây là snippet method hợp lệ. Caller có thể muốn ghi tiếp sau `append`, vì vậy method không nên tự đóng writer trừ khi contract nói rõ.

Các trường hợp dễ mắc lỗi:
- Bọc `System.in` trong Scanner rồi đóng Scanner giữa application khiến standard input không còn sử dụng được.
- Tự đóng Connection do transaction framework quản lý.
- Đóng một HTTP response/stream trước khi caller tiêu thụ hết dữ liệu.
- Đăng ký cả buffered wrapper lẫn underlying stream rồi đóng trùng.

**Ownership quan trọng hơn cú pháp:** chỉ dùng TWR tại nơi có quyền và trách nhiệm đóng.

## 37. Chương trình hoàn chỉnh 15 — borrowed writer

Tệp **`BorrowedWriterDemo.java`**:

~~~java
import java.io.IOException;
import java.io.StringWriter;
import java.io.Writer;

public class BorrowedWriterDemo {
    static void addGreeting(Writer writer) throws IOException {
        writer.write("Hello");
    }

    public static void main(String[] args) throws IOException {
        StringWriter writer = new StringWriter();

        addGreeting(writer);
        writer.write(" Java");

        System.out.println(writer.toString());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BorrowedWriterDemo.java
java BorrowedWriterDemo
~~~

**Stdout:**

~~~text
Hello Java
~~~

Method chỉ mượn writer. `StringWriter` là buffer trong memory và `close()` không ảnh hưởng tới việc dùng tiếp theo contract; ví dụ dạy quyền sở hữu, không phải chứng minh mọi Writer đều có thể được dùng sau close.

## 38. `close()` có bắt buộc idempotent không?

`AutoCloseable` không bảo đảm mọi concrete implementation có thể đóng nhiều lần an toàn. API khuyến nghị idempotency nếu có thể, nhưng một native handle hoặc transaction resource có thể có ràng buộc riêng.

Một implementation đơn giản có thể giữ flag `closed`:

~~~java
@Override
public void close() {
    if (!closed) {
        closed = true;
        release();
    }
}
~~~

Đây là snippet cần field `closed` và `release` thích hợp. Nó không tự thread-safe. Nếu hai threads đồng thời close, boolean flag không có synchronization có thể gây double release.

Nên quyết định rõ:
- Close lần hai là no-op hay ném lỗi?
- Use-after-close báo exception gì?
- Nếu release thất bại, state được cập nhật thế nào?
- Close có được gọi bởi thread khác không?
- Nếu resource có nhiều subresources, thứ tự release nào đúng?

## 39. Chương trình hoàn chỉnh 16 — idempotent close theo thiết kế

Tệp **`IdempotentDemo.java`**:

~~~java
final class SafeLease implements AutoCloseable {
    private boolean closed;

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("released");
        }
    }

    boolean isClosed() {
        return closed;
    }
}

public class IdempotentDemo {
    public static void main(String[] args) {
        SafeLease lease = new SafeLease();

        try (lease) {
            System.out.println("using");
        }

        lease.close();
        System.out.println("closed=" + lease.isClosed());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 IdempotentDemo.java
java IdempotentDemo
~~~

**Stdout:**

~~~text
using
released
closed=true
~~~

TWR gọi close một lần; lời gọi thêm không in `released` vì implementation tự thiết kế idempotency. Không suy ra mọi AutoCloseable đều có hành vi tương tự.

## 40. Custom AutoCloseable cho một lock lease

Trong Java 17, `java.util.concurrent.locks.Lock` **không extends AutoCloseable**, nên không thể đặt trực tiếp một Lock trong TWR. Nhưng bạn có thể tạo một wrapper **LockLease** nắm ownership để lock/unlock với scope.

Đây là pattern hữu ích nhưng cần cẩn thận: `ReentrantLock.unlock()` phải do thread phù hợp thực hiện. Nếu resource có thể di chuyển sang thread khác, bạn cần một thiết kế concurrent ownership khác.

## 41. Chương trình hoàn chỉnh 17 — wrapper quản lý ReentrantLock

Tệp **`LockLeaseDemo.java`**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

final class LockLease implements AutoCloseable {
    private final ReentrantLock lock;
    private boolean closed;

    LockLease(ReentrantLock lock) {
        this.lock = lock;
        lock.lock();
        System.out.println("acquired");
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            lock.unlock();
            System.out.println("released");
        }
    }
}

public class LockLeaseDemo {
    public static void main(String[] args) {
        ReentrantLock lock = new ReentrantLock();

        try (LockLease lease = new LockLease(lock)) {
            System.out.println("held=" + lock.isHeldByCurrentThread());
        }

        System.out.println("held after="
                + lock.isHeldByCurrentThread());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LockLeaseDemo.java
java LockLeaseDemo
~~~

**Stdout:**

~~~text
acquired
held=true
released
held after=false
~~~

Chương trình chạy một thread, không có contention; output ổn định. Một lock lease trong hệ thống thực cần thiết kế state và thread-affinity rõ ràng.

## 42. Khi cần `finally` thay TWR

Không phải mọi API cleanup đều implement AutoCloseable. Với Lock đơn thuần:

~~~java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

Đây là snippet cần `lock` và `updateSharedState` được định nghĩa. `finally` phù hợp với contract Lock của Java 17.

Nếu đang sở hữu một resource có AutoCloseable, TWR thường ít lỗi hơn `finally` viết tay, vì:
- Không quên đóng ở đường return/throw.
- Đóng nhiều resource đúng thứ tự.
- Bảo tồn primary/suppressed exceptions khi close ném.
- Không phải tự viết logic null check đơn giản.

Tuy nhiên, TWR không thể thay thế một transaction protocol, chống process crash, hoặc bù trừ các side effects bên ngoài.

## 43. Chương trình hoàn chỉnh 18 — cleanup bằng finally

Tệp **`FinallyDemo.java`**:

~~~java
public class FinallyDemo {
    static void runTask() {
        try {
            System.out.println("work");
            throw new IllegalStateException("failed");
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        try {
            runTask();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 FinallyDemo.java
java FinallyDemo
~~~

**Stdout:**

~~~text
work
cleanup
caught=failed
~~~

`finally` được ngôn ngữ thực hiện theo luồng control; không phải callback GC. Nếu cleanup ở finally cũng throw, code thủ công cần cẩn thận tránh vô tình che lỗi ban đầu.

## 44. `try-with-resources` có luôn cleanup ngay cả khi JVM dừng không?

Không. Cơ chế ngôn ngữ được áp dụng khi control rời khỏi try scope theo đường chạy Java thông thường, bao gồm return và exceptions. Nhưng process có thể chết mà không unwind stack frames:

- `Runtime.halt(...)` chấm dứt VM một cách cưỡng bức.
- `System.exit(...)` làm tiến trình shutdown, không hứa mọi currently active try scopes hoàn tất theo đường thông thường.
- OS kill, power failure, native crash hay JVM crash có thể ngăn close code chạy.
- Một `close()` có thể block vô hạn hoặc ném lỗi theo implementation.

Do đó TWR **không phải** cam kết giao dịch bền vững sau crash. Khi dữ liệu cần all-or-nothing hay durability, phải thêm transaction, flush policy, atomic file move, journal/recovery hoặc protocol thích hợp.

## 45. `Cleaner` và `finalize` không thay được close đúng lúc

Legacy finalization không có thời điểm chạy được bảo đảm và không phù hợp để quản lý file/socket đúng hạn. `Cleaner` có thể hữu ích làm **backup** cho resource holders có native state, nhưng automatic clean vẫn phụ thuộc reachability, scheduling và lifecycle của JVM.

Với TWR, caller có thể xác định rõ một mốc **close attempt** theo scope. Đó là sự khác biệt giữa resource cleanup dùng quyền sở hữu và GC-based cleanup không có deadline.

Nếu class vừa có `close()` vừa có backup Cleaner, action Cleaner không nên giữ strong reference tới chính referent, vì như vậy có thể ngăn automatic cleanup. Khi đóng tường minh, cũng cần phòng tránh double release.

**Không viết test “sleep 1 giây rồi finalizer phải in closed”.** Hãy dùng fake AutoCloseable và assert những dấu hiệu do close tạo ra.

## 46. Use-after-close: reference còn nhưng tài nguyên đã đóng

Nếu resource được khai **bên ngoài** try, biến vẫn có thể còn trong scope sau đó. Nhưng trạng thái object đã có thể chuyển từ OPEN sang CLOSED.

Một API tốt nên định nghĩa điều gì xảy ra khi caller đọc/ghi sau close: thường throw `IllegalStateException` hoặc `IOException`, tùy contract. Đừng gọi `getClass()` hay so reference còn khác null rồi kết luận nó vẫn sử dụng tài nguyên được.

Điều này giúp phân biệt **vòng đời object trên heap** với **vòng đời external handle**.

## 47. Chương trình hoàn chỉnh 19 — chặn thao tác sau close

Tệp **`ClosedStateDemo.java`**:

~~~java
final class ManagedResource implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("resource closed");
        }
        System.out.println("used");
    }

    @Override
    public void close() {
        closed = true;
        System.out.println("closed");
    }
}

public class ClosedStateDemo {
    public static void main(String[] args) {
        ManagedResource resource = new ManagedResource();

        try (resource) {
            resource.use();
        }

        try {
            resource.use();
        } catch (IllegalStateException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ClosedStateDemo.java
java ClosedStateDemo
~~~

**Stdout:**

~~~text
used
closed
rejected=resource closed
~~~

Object vẫn còn được biến `resource` tham chiếu khi catch chạy, nhưng phương thức use bị từ chối vì lifecycle đã đóng.

## 48. Kiểm thử đóng tài nguyên bằng event log

Một bài kiểm thử tốt cho TWR không cần I/O thật hay GC. Bạn có thể tạo FakeResource implements AutoCloseable và ghi lại events `open`, `use`, `close`. Kiểm tra sequence, số lần close và thứ tự giữa nhiều resources.

Nếu test suppressed exceptions, ném ngoại lệ có message cố định ở body/close rồi đọc `getSuppressed()`, không cần giả định stack trace format giữa các JDK.

Tách bạch:
- **Unit test TWR:** ngôn ngữ gọi close đúng lúc?
- **Integration test I/O:** filesystem/socket/pool có release theo contract?
- **GC observation:** JVM thu hồi object lúc nào (không deterministic, không phải correctness check của TWR)?

## 49. Chương trình hoàn chỉnh 20 — ghi dấu thứ tự close

Tệp **`CloseAuditDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class AuditedResource implements AutoCloseable {
    private final String name;
    private final List<String> events;

    AuditedResource(String name, List<String> events) {
        this.name = name;
        this.events = events;
        events.add("open-" + name);
    }

    void use() {
        events.add("use-" + name);
    }

    @Override
    public void close() {
        events.add("close-" + name);
    }
}

public class CloseAuditDemo {
    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        try (AuditedResource a = new AuditedResource("A", events);
             AuditedResource b = new AuditedResource("B", events)) {
            a.use();
            b.use();
        }

        System.out.println(events);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CloseAuditDemo.java
java CloseAuditDemo
~~~

**Stdout:**

~~~text
[open-A, open-B, use-A, use-B, close-B, close-A]
~~~

Chương trình kiểm tra thứ tự resource close chính xác, hoàn toàn không phụ thuộc memory GC hoặc file system.

## 50. Lỗi biên dịch và sai lầm thường gặp

| Sai lầm | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `try (new Object())` | Không đúng resource syntax/type AutoCloseable | Khai/nhận resource implements AutoCloseable |
| Resource là một class không implements AutoCloseable | TWR không biết close | Implement interface hoặc dùng finally đúng contract |
| Gán lại resource header variable | Implicitly final | Khai resource mới ở scope khác |
| `try (existing)` nhưng biến không effectively final | Java 9+ yêu cầu final/effectively final | Ngừng reassign |
| Không bắt/khai checked exception từ close | Vi phạm checked exception analysis | Catch/declare đúng loại |
| Cho rằng body catch chạy trước close | Cleanup xảy ra trước outer catch | Hiểu thứ tự exception processing |
| Đóng wrapper và raw stream hai lần | Wrapper có thể sở hữu raw | Chỉ một owner, tra cứu contract |
| Resource khai trước try nhưng method vẫn dùng sau close | Object đã CLOSED | Không dùng operations đòi open |
| Nhầm TWR với tự động xóa temporary files | Close không delete file | `Files.deleteIfExists` theo cleanup policy |
| Dùng `try (System.in)` rồi còn muốn đọc tiếp | Ownership standard input bị xâm phạm | Đừng tự đóng stream chung |
| Bỏ qua suppressed exceptions | Thiếu dữ kiện cleanup failure | Xem `getSuppressed()` |
| Dùng Java 17 ExecutorService trong TWR | ExecutorService Java 17 không extends AutoCloseable | Dùng shutdown APIs |
| Chỉ rely on GC để đóng resource | GC timing không được bảo đảm | TWR hoặc explicit close |
| Dùng `try (resource)` như cơ chế bảo đảm transaction commit | Close không phải transaction policy | Commit/rollback rõ |

Đặc biệt, **Java 17 `ExecutorService` không phải AutoCloseable**: cú pháp dùng `try (ExecutorService executor = Executors.newSingleThreadExecutor())` như một resource **không biên dịch ở target Java 17**. API trên các phiên bản JDK mới có thể khác; luôn kiểm tra `--release 17` trong dự án yêu cầu tương thích 17.

## 51. Khi nào không cần `try-with-resources`?

Không phải mọi object cần đóng:
- Immutable values như String, Integer, BigDecimal và phần lớn records thuần dữ liệu.
- Collections in-memory bình thường như ArrayList, HashMap.
- Stream thuần từ Collection, nếu không có close handler/resource ownership đặc biệt.
- Objects không implement AutoCloseable và không đại diện resource lifecycle.
- Resource được **mượn** từ caller mà contract yêu cầu callee không được đóng.
- Framework-managed resource/transaction nơi caller không sở hữu close boundary.

Ngược lại, một object `AutoCloseable` có thể được trả cho caller với hợp đồng “caller must close”; điều quan trọng là truyền trách nhiệm ownership rõ. Nếu method mở InputStream rồi **trả stream để caller đọc tiếp**, đừng đặt chính InputStream đó vào một TWR scope kết thúc trước `return`: bạn sẽ trả về stream đã đóng.

## 52. Bài tập kiểm tra kiến thức

**Câu 1.** Vì sao GC không thay `close()` cho file descriptor?

**Câu 2.** AutoCloseable nằm trong package nào và có method nào?

**Câu 3.** Nếu implementation `close()` không khai checked exception, main có phải khai `throws Exception` chỉ vì TWR không?

**Câu 4.** Với ba resources A, B, C trong header, thứ tự mở và đóng là gì?

**Câu 5.** Khi body throw, Java có cố đóng resources đã mở không?

**Câu 6.** Nếu B constructor thất bại nhưng A đã mở, A có được đóng không?

**Câu 7.** TWR có biết mọi native resource được cấp phát một phần bên trong constructor B thất bại để tự giải phóng không?

**Câu 8.** Nếu body và close đều ném, exception nào là primary?

**Câu 9.** Đọc suppressed exceptions bằng method nào?

**Câu 10.** Nếu body thành công và chỉ close ném IOException, caller có nhận exception không?

**Câu 11.** Return trong body có bỏ qua close không?

**Câu 12.** Resource header variable có được gán lại không?

**Câu 13.** Java 17 có cho `try (resource)` với biến khai báo trước không?

**Câu 14.** Biến khai báo trước phải có tính chất nào để dùng trong `try (resource)`?

**Câu 15.** Khi resource value là null, TWR có tự ném NPE ở cleanup không?

**Câu 16.** Closeable có extends AutoCloseable không và khác checked exception ra sao?

**Câu 17.** Tại sao BufferedReader wrapper thường không cần đăng ký underlying reader để close lần nữa?

**Câu 18.** `Files.lines` có yêu cầu đóng stream result không?

**Câu 19.** `Files.newBufferedReader` được đóng thì file trên đĩa tự xóa không?

**Câu 20.** TWR tự commit hay rollback một JDBC transaction theo business policy không?

**Câu 21.** Pooled Connection.close() có luôn hủy physical socket không?

**Câu 22.** Một method mượn Writer có nên tự đóng nó không?

**Câu 23.** AutoCloseable.close() luôn idempotent không?

**Câu 24.** Nếu close được gọi từ nhiều threads, một boolean flag không đồng bộ đã bảo đảm exactly-once release chưa?

**Câu 25.** `Lock` Java 17 có extends AutoCloseable không?

**Câu 26.** `ExecutorService` Java 17 có dùng trực tiếp trong TWR không?

**Câu 27.** Tại sao không nên đợi finalizer/Cleaner thay close đúng hạn?

**Câu 28.** TWR có bảo đảm close chạy nếu Runtime.halt làm JVM chấm dứt không?

**Câu 29.** Resource object còn được tham chiếu sau try có thể vẫn CLOSED không?

**Câu 30.** Nêu một cách unit-test cleanup mà không cần GC.

**Câu 31.** Nếu method tạo InputStream và trả cho caller, nơi nào chịu trách nhiệm close?

**Câu 32.** Nếu resource có lỗi close khi body đã lỗi, muốn log đầy đủ cần xem điều gì?

### Đáp án có giải thích

1. GC không có deadline; native/file resources cần explicit release theo ownership.
2. `java.lang.AutoCloseable`, method `void close() throws Exception`.
3. Không khi static concrete close signature không khai checked exception.
4. Mở A→B→C; đóng C→B→A.
5. Có, các resources khởi tạo thành công được thử đóng.
6. Có.
7. Không; constructor B phải tự bảo vệ partial initialization.
8. Lỗi body là primary, lỗi đóng được suppressed.
9. `Throwable.getSuppressed()`.
10. Có, close exception là primary.
11. Không, close xảy ra trước khi caller nhận return value.
12. Không, resource header variable implicitly final.
13. Có, từ Java 9.
14. Final hoặc effectively final.
15. Không; null resource không được gọi close tự động.
16. Có; Closeable hẹp hơn với IOException.
17. Wrapper thường tự đóng underlying; tránh double close ngoài ownership.
18. Có; file-backed stream phải được đóng.
19. Không; xóa file là operation khác.
20. Không; transaction policy phải được thiết kế riêng.
21. Không, nhiều pools trả logical connection về pool.
22. Không, trừ khi contract chuyển ownership.
23. Không; implementation cần tự chọn hợp đồng.
24. Chưa, cần concurrency-safe close protocol.
25. Không.
26. Không trong Java 17; dùng shutdown/awaitTermination.
27. GC/cleaner scheduling không được đảm bảo thời hạn.
28. Không; halt có thể ngăn unwind scopes.
29. Có; reference lifetime khác resource lifetime.
30. Fake AutoCloseable ghi events và assert thứ tự/số lần gọi.
31. Caller nếu API nêu rõ chuyển ownership.
32. Primary/cause và suppressed exceptions.

## 53. Checklist khi code review

- [ ] Xác định ai sở hữu resource và ai phải đóng?
- [ ] Resource có implement AutoCloseable/Closeable không?
- [ ] Nếu resource được tạo tại đây và cần đóng, đã dùng TWR đúng scope?
- [ ] Có phân biệt external resource cleanup với garbage collection?
- [ ] Với nhiều resources, có dự tính thứ tự đóng ngược?
- [ ] Có xử lý khi resource sau thất bại ngay trong header?
- [ ] Constructor tự dọn acquisition một phần khi ném?
- [ ] Exception body và close được bảo toàn primary/suppressed?
- [ ] Không nuốt checked exception từ close vô cớ?
- [ ] Resource variables dùng `try (existing)` có final/effectively final?
- [ ] Có tránh dùng resource tiếp sau khi CLOSED?
- [ ] Có tránh đóng resource đang được caller/framework sở hữu?
- [ ] Với wrapper, có xác định underlying resource ownership?
- [ ] Có dùng TWR cho Files.lines và I/O streams phù hợp?
- [ ] JDBC transaction và connection pool lifecycle đã được xử lý riêng?
- [ ] Temporary file có deletion policy riêng?
- [ ] Custom close có idempotency/use-after-close contract?
- [ ] Nếu resource concurrent, có safe close/release state?
- [ ] Không tưởng mọi Lock/ExecutorService Java 17 đều AutoCloseable?
- [ ] Không dựa finalizer/Cleaner/GC để đóng đúng thời điểm?
- [ ] Đã kiểm thử success, body exception, close exception, acquisition failure và return?
- [ ] Không phụ thuộc GC timing để xác minh cleanup?
- [ ] Có tài liệu hóa ownership khi API trả stream/resource ra ngoài?

## 54. Tài liệu Java 17 chính thức

- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): method close, exception và contract.
- [Java SE 17 API — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): I/O close, IOException, idempotency.
- [JLS Java 17 §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): resource specification, evaluation, close order và exceptions.
- [JLS Java 17 §4.12.4 — final variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final và effectively final.
- [Java SE 17 API — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): suppressed exceptions.
- [Java SE 17 API — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): buffered text input.
- [Java SE 17 API — Files.newBufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset)): resource cần close.
- [Java SE 17 API — Files.lines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset)): file-backed Stream.
- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): AutoCloseable stream.
- [Java SE 17 API — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): JDBC lifecycle, transaction.
- [Java SE 17 API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): SQL prepared statement.
- [Java SE 17 API — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): SQL result set.
- [Java SE 17 API — Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): automatic cleanup chỉ dự phòng.
- [Java SE 17 API — Lock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): lock/unlock.
- [Java SE 17 API — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown trong Java 17.
- [JEP 213 — Milling Project Coin](https://openjdk.org/jeps/213): sử dụng effectively final resource có sẵn trong TWR.
- [Oracle Java Tutorials — The try-with-resources Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): thứ tự close và suppressed exceptions.

## 55. Tổng kết

**`AutoCloseable`** diễn đạt “đối tượng này có thao tác `close()`”. **`try-with-resources`** bảo đảm Java **cố gọi close theo scope**, bất kể thân try thành công hay ném exception hoặc return. Với nhiều tài nguyên, mở trái sang phải và đóng theo thứ tự ngược. Khi body và close cùng ném lỗi, Java giữ **primary exception** và ghi nhận lỗi cleanup dưới dạng **suppressed exceptions**.

Trong Java 17 có thể dùng biến khai trực tiếp trong TWR header hoặc biến đã khai báo trước nhưng final/effectively final. `Closeable` là một subtype hẹp hơn của AutoCloseable cho I/O. Những tài nguyên như files, file-backed streams và JDBC objects thường cần close theo ownership; transaction commit/rollback, xóa file hay shutdown executor là những trách nhiệm khác, không tự xuất hiện chỉ vì TWR.

**Nguyên tắc thực hành:** GC quản lý memory reclamation, còn **owner của resource** phải quản lý thời điểm close. Khi ownership, exception behavior và concurrency được xác định rõ, TWR giúp code dễ đọc, ít bỏ sót resource và giữ nguyên những thông tin lỗi quan trọng.
