# Java 7 — AutoCloseable: Hợp đồng close và lựa chọn ngoại lệ được khai báo

## 1. Nội dung chính cần nắm

**`AutoCloseable`** là interface trong `java.lang` với một phương thức duy nhất:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Đây là **chữ ký rút gọn** để học hợp đồng API, không phải yêu cầu tự khai báo lại interface có sẵn của JDK. Interface này xuất hiện cùng **try-with-resources** từ Java 7 và vẫn được sử dụng trên Java 17+ và các phiên bản mới hơn. Một đối tượng thực thi `AutoCloseable` có thể đặt trong ngoặc của `try (...)`; khi rời khối, Java sẽ cố gọi `close()` tự động.

Điểm quyết định trong bài là: **`throws Exception` ở interface gốc không bắt buộc mọi implementation cũng khai báo `Exception`.** Khi ghi đè phương thức, lớp hoặc interface con có thể **thu hẹp** loại checked exception, hoặc **không khai báo checked exception nào**.

Ba kiểu hợp đồng điển hình:

```java
// 1) Có thể khai báo Exception tổng quát: hợp lệ nhưng ít cụ thể.
final class BroadResource implements AutoCloseable {
    @Override
    public void close() throws Exception {
        // Cleanup có thể báo một checked exception.
    }
}

// 2) Thu hẹp thành IOException: hợp lệ và cụ thể hơn.
final class IoResource implements AutoCloseable {
    @Override
    public void close() throws java.io.IOException {
        // Cleanup liên quan I/O.
    }
}

// 3) Không có checked exception: hợp lệ.
final class QuietResource implements AutoCloseable {
    @Override
    public void close() {
        // Cleanup không cần khai báo checked exception.
    }
}
```

Ba khai báo lớp độc lập nói trên là **mã minh họa hợp lệ** nếu đặt trong một tệp Java thích hợp; không có phương thức `main`. Cách chọn khai báo `throws` ảnh hưởng trực tiếp tới **API người gọi**, **kiểm tra checked exception khi biên dịch** và **cách dùng try-with-resources**. Không nên chọn kiểu ngoại lệ chỉ theo sự tiện lợi của người viết lớp; hãy dựa vào khả năng thất bại thực tế và ý nghĩa của thao tác đóng.

## 2. Hợp đồng `AutoCloseable.close()` thực sự cam kết gì?

Một implementation của `AutoCloseable` cần xác định rõ:

1. **Đóng hoặc giải phóng trách nhiệm nào?** Ví dụ giải phóng file handle, socket, database connection, lock scope, buffer hoặc một phiên giao dịch được sở hữu.
2. **Đối tượng ở trạng thái nào sau khi đóng?** Các phương thức nghiệp vụ có còn được phép gọi không? Có được gọi lại `close()` không?
3. **Khi không đóng được, lỗi nào có thể phát sinh?** Có cần báo lỗi checked để caller xử lý/ghi nhận, hay trạng thái đó được quản lý theo chính sách khác?
4. **Nếu thân try cũng thất bại thì sao?** Java sẽ giữ ngoại lệ chính và thường gắn ngoại lệ từ `close()` dưới dạng *suppressed*; implementation cần tránh phá hủy thêm thông tin chẩn đoán.
5. **Ai sở hữu vòng đời?** Nếu một phương thức mượn resource của caller, nó không mặc nhiên được phép đóng. Đặt vào TWR đồng nghĩa với việc khối đó **chịu trách nhiệm đóng** đối tượng khi thoát.

Một điều **không được đảm bảo chỉ vì implements `AutoCloseable`**: thao tác `close()` tự động thành công, đóng được gọi đúng một lần trên toàn vòng đời, hoặc việc đóng an toàn khi nhiều thread dùng đồng thời. Các chi tiết này tùy hợp đồng của implementation.

**`AutoCloseable.close() throws Exception` là mức cho phép rộng nhất của interface** đối với checked exception. Nó không có nghĩa runtime sẽ tự tạo một `Exception`, và không có nghĩa implementation bắt buộc phải phát sinh lỗi.

## 3. So sánh `AutoCloseable` với `java.io.Closeable`

`Closeable` là interface trong `java.io`, kế thừa `AutoCloseable` và **thu hẹp** chữ ký đóng thành:

```java
public interface Closeable extends AutoCloseable {
    @Override
    void close() throws IOException;
}
```

Đây cũng là **chữ ký khái quát hóa** của API chuẩn; trong mã thật phải dùng `java.io.Closeable` và `java.io.IOException` thay vì tự định nghĩa lại.

| Tiêu chí | `AutoCloseable` | `Closeable` |
| --- | --- | --- |
| Package | `java.lang` | `java.io` |
| Quan hệ kiểu | Interface nền cho TWR | **Extends AutoCloseable** |
| Chữ ký `close` | `void close() throws Exception` | `void close() throws IOException` |
| Lĩnh vực sử dụng | Resource có vòng đời chung, không nhất thiết I/O | Resource theo hợp đồng đóng kiểu I/O |
| Checked exception được phép khi override | Có thể giữ `Exception`, thu hẹp hoặc bỏ | Có thể giữ `IOException`, thu hẹp hoặc bỏ; không được mở rộng sang `Exception` |
| Đóng nhiều lần | Interface không bắt buộc `close()` phải idempotent | Hợp đồng `Closeable.close()` yêu cầu việc gọi khi đã đóng không còn tác dụng |
| Có dùng trong `try (...)`? | Có | Có, vì là subtype của `AutoCloseable` |

**Hai điều khác nhau cần tránh nhầm:**

- Một lớp implements `Closeable` **đương nhiên cũng là** `AutoCloseable`. Không phải mọi `AutoCloseable` đều là `Closeable`.
- `throws IOException` là kiểu lỗi cụ thể hơn `throws Exception`. Chọn `Closeable` chỉ vì muốn compiler dễ tính là không hợp lý nếu lỗi khi đóng thực chất không thuộc miền I/O. Khi đó giữ `AutoCloseable` và dùng một loại checked exception phù hợp với domain, hoặc không khai báo checked exception nếu cleanup không cần loại đó.

Ví dụ hiện hành: `InputStream`, `Reader`, nhiều lớp I/O implement `Closeable`; các kiểu resource ngoài I/O như một số handle/transaction scope có thể chỉ implement `AutoCloseable`. Hãy đọc chính hợp đồng lớp cụ thể để biết `close()` có thể ném gì.

## 4. Quy tắc Java khi override: chỉ được thu hẹp checked exception

Java kiểm tra chữ ký phương thức khi ghi đè. Nếu phương thức cha khai báo checked exception `Exception`, phương thức con có thể khai báo cùng loại, một subtype, nhiều subtype phù hợp, hoặc không khai báo checked exception. Ngược lại, **không thể thêm checked exception rộng hơn hợp đồng đã được kế thừa**.

### 4.1. Các ví dụ hợp lệ

```java
class FileLease implements AutoCloseable {
    @Override
    public void close() throws java.io.IOException {
        // ...
    }
}

class NoThrowLease implements AutoCloseable {
    @Override
    public void close() {
        // ...
    }
}

class DatabaseLease implements AutoCloseable {
    @Override
    public void close() throws java.sql.SQLException {
        // ...
    }
}

class StrictReader implements java.io.Closeable {
    @Override
    public void close() throws java.io.IOException {
        // ...
    }
}
```

Các lớp trong khối mã là **minh họa**, không có `main`. `IOException` và `SQLException` đều là subtype của `Exception` nên hợp lệ khi override `AutoCloseable.close()`. `StrictReader.close()` phù hợp với giới hạn `IOException` mà `Closeable` khai báo.

### 4.2. Các ví dụ sai tại compile-time

```java
class WrongReader implements java.io.Closeable {
    @Override
    public void close() throws Exception {
        // Sai: Exception rộng hơn IOException của Closeable.close().
    }
}
```

Khối trên **cố ý không biên dịch**: lớp triển khai `Closeable` không được mở rộng checked exception thành `Exception`. Tương tự, `close() throws SQLException` là sai khi override `Closeable.close()` vì `SQLException` không phải subtype của `IOException`.

```java
class WrongSignature implements AutoCloseable {
    // Sai: close(int) là overload, không phải override close().
    public void close(int reason) { }
}
```

Khối trên cũng cố ý sai: còn thiếu phương thức `public void close()` không tham số. Ngoài ra, phương thức implement interface phải có mức truy cập **`public`**, không được tự ý giảm thành package-private hoặc `private`.

**Unchecked exception** (như `RuntimeException`) không tuân theo ràng buộc checked-throws theo cách tương tự. Một implementation vẫn có thể ném lỗi unchecked khi close; điều đó không có nghĩa nên chuyển mọi lỗi cleanup sang unchecked để tránh hợp đồng. Chọn lỗi dựa trên ý nghĩa, khả năng phục hồi và ranh giới xử lý.

## 5. Kiểu khai báo của biến resource quyết định ngoại lệ cần xử lý

Đây là phần dễ gây bất ngờ: compiler nhìn vào **kiểu tĩnh của biến resource** trong `try (...)`, chứ không chỉ nhìn constructor của đối tượng được tạo.

### 5.1. Dùng kiểu cụ thể có `close()` không khai báo checked exception

```java
static void useQuietResource() {
    try (QuietResource resource = new QuietResource()) {
        System.out.println("work");
    }
}
```

Đây là **phương thức minh họa** đặt trong lớp có `QuietResource` như phần 1. Vì kiểu tĩnh `QuietResource` có `close()` không khai báo checked exception, caller **không phải thêm `throws Exception` chỉ để gọi close**. Nếu các lời gọi khác trong thân try không ném checked exception thì không cần catch.

### 5.2. Dùng kiểu `AutoCloseable` thì hợp đồng rộng có hiệu lực

```java
static void useBroadReference() throws Exception {
    try (AutoCloseable resource = new QuietResource()) {
        System.out.println("work");
    }
}
```

Mặc dù đối tượng thực tế là `QuietResource` có close không khai báo lỗi checked, **kiểu tĩnh ở đây là `AutoCloseable`**. Vì chữ ký `AutoCloseable.close()` cho phép `throws Exception`, compiler phải tính tới khả năng close ném checked `Exception`. Do đó phương thức khai báo `throws Exception` hoặc phải bắt phù hợp.

Ví dụ sau **cố ý không biên dịch**:

```java
static void missingThrows() {
    try (AutoCloseable resource = new QuietResource()) {
        System.out.println("work");
    }
    // Sai: chưa bắt/khai báo Exception có thể từ AutoCloseable.close().
}
```

**Chọn kiểu khai báo sát hợp đồng** khi có thể: `QuietResource` nếu caller cần đúng loại resource cụ thể, hoặc một interface chuyên biệt có `close()` khai báo narrow throws phù hợp. Tuy nhiên không nên làm rò rỉ implementation class chỉ để tránh `throws Exception`; thiết kế một abstraction có hợp đồng rõ ràng thường tốt hơn.

### 5.3. `var` và biến có sẵn

Với JDK 17+, có thể dùng:

```java
try (var resource = new QuietResource()) {
    System.out.println("work");
}
```

Vì `var` ở khai báo biến cục bộ được suy luận thành `QuietResource`, compiler sử dụng hợp đồng `close()` cụ thể của kiểu đó. `var` xuất hiện từ Java 10; **không phải cú pháp có ngay ở Java 7**.

Từ Java 9, TWR cũng cho phép tham chiếu một biến resource **đã khai báo bên ngoài và final/effectively final**:

```java
QuietResource existing = new QuietResource();

try (existing) {
    System.out.println("work");
}
```

Khối minh họa này dùng cú pháp Java 9+; sự tồn tại của biến ở ngoài không thay đổi quy tắc TWR sẽ đóng resource sau khi sử dụng. Không thêm `close()` thủ công trong finally cho cùng resource.

## 6. Chọn checked exception hợp lý cho `close()`

### 6.1. Khi nào nên khai báo `IOException`?

Với resource thực sự thực hiện I/O (ví dụ stream, file writer, kết nối với thao tác đóng/flush có thể thất bại), `IOException` có thể là hợp đồng hợp lý. Implementation của `Closeable` có sẵn kiểu ngoại lệ đó. Caller có thể bắt `IOException` hoặc khai báo `throws IOException`.

**Lưu ý:** đóng một writer có thể thực hiện flush và báo lỗi. Vì vậy không được coi lỗi từ close là “chi tiết không quan trọng” trong mọi trường hợp; nếu đã trả về thành công nhưng đóng thất bại, dữ liệu có thể chưa được ghi như mong muốn.

### 6.2. Khi nào nên dùng loại checked exception thuộc domain?

Một resource không phải I/O, như handle giao dịch/đối tượng quản lý tài nguyên nghiệp vụ, có thể có lỗi cleanup phù hợp với một exception checked khác. Khi đó `AutoCloseable.close() throws SQLException` hoặc một exception domain cụ thể có thể phù hợp.

```java
interface DatabaseSession extends AutoCloseable {
    void execute() throws java.sql.SQLException;

    @Override
    void close() throws java.sql.SQLException;
}
```

Đây là **interface minh họa hợp lệ** để thể hiện hợp đồng, không phải implementation. Caller dùng TWR trên `DatabaseSession` sẽ biết cần xử lý `SQLException`, thay vì `Exception` quá rộng. Việc `close()` có nghĩa là rollback, return-to-pool, disconnect hay commit **phải được quy định riêng**: `AutoCloseable` không tự định nghĩa hành vi giao dịch.

### 6.3. Khi nào nên không khai báo checked exception?

Nếu cleanup về mặt hợp đồng không có lỗi checked mà caller cần xử lý, sử dụng `close()` không khai báo `throws` giúp API đơn giản hơn. Ví dụ một scope guard phục hồi trạng thái cục bộ hoặc đối tượng chỉ phát một tín hiệu giải phóng không có thao tác I/O có thể triển khai như vậy.

**Không đồng nghĩa “close sẽ không bao giờ ném lỗi”.** Những lỗi unchecked vẫn có thể xảy ra, và các trường hợp bug nghiêm trọng không thể giải quyết bằng cách bắt chung rồi bỏ qua. Hãy thiết kế cleanup có độ tin cậy cao, kiểm thử nhiều đường thoát và mô tả hành vi thất bại phù hợp.

### 6.4. Vì sao không nên mặc định `throws Exception` ở lớp triển khai?

`throws Exception` hợp lệ vì khớp interface `AutoCloseable`, nhưng nó có thể buộc caller phải:

- khai báo `throws Exception` quá rộng;
- viết `catch (Exception ex)` gom nhiều loại lỗi không liên quan;
- khó phân biệt lỗi cleanup với lỗi nghiệp vụ khi review và test;
- mở rộng bề mặt lỗi của abstraction mà không cung cấp thêm ý nghĩa.

Vì vậy trong API do mình quản lý, **narrow throws khi mô hình lỗi cho phép**. Không cố bóp ngoại lệ thành một checked exception không đúng nghĩa chỉ để chữ ký ngắn hơn.

## 7. Chương trình Java 17+ hoàn chỉnh: ba kiểu hợp đồng close

Ví dụ dưới đây minh họa đồng thời:

1. `close()` không khai báo checked exception;
2. `Closeable.close() throws IOException`;
3. `AutoCloseable.close() throws Exception`;
4. hành vi **body lỗi và close lỗi cùng lúc**: close exception được lưu thành *suppressed* của lỗi chính.

Để stdout ổn định, ví dụ cố ý tạo lỗi bằng code thay vì phụ thuộc file, database hoặc mạng.

Tạo tệp **`CloseContractDemo.java`**:

```java
import java.io.Closeable;
import java.io.IOException;

public class CloseContractDemo {
    static final class QuietResource implements AutoCloseable {
        String read() {
            return "ready";
        }

        @Override
        public void close() {
            System.out.println("quiet close");
        }
    }

    static final class IoResource implements Closeable {
        @Override
        public void close() throws IOException {
            System.out.println("io close");
            throw new IOException("flush failed");
        }
    }

    static final class GenericResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            System.out.println("generic close");
            throw new Exception("generic failure");
        }
    }

    static String quiet() {
        try (QuietResource resource = new QuietResource()) {
            System.out.println("quiet work");
            return resource.read();
        }
    }

    static String io() {
        try (IoResource resource = new IoResource()) {
            System.out.println("io work");
            return "pending";
        } catch (IOException ex) {
            return "io caught: " + ex.getMessage();
        }
    }

    static String generic() {
        try (GenericResource resource = new GenericResource()) {
            System.out.println("generic work");
            return "pending";
        } catch (Exception ex) {
            return "generic caught: " + ex.getMessage();
        }
    }

    static void suppressed() {
        try (IoResource resource = new IoResource()) {
            System.out.println("throw body");
            throw new IllegalStateException("body error");
        } catch (IllegalStateException ex) {
            System.out.println("primary: " + ex.getMessage());
            for (Throwable extra : ex.getSuppressed()) {
                System.out.println("suppressed: " + extra.getMessage());
            }
        } catch (IOException ex) {
            System.out.println("unexpected: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("quiet result: " + quiet());
        System.out.println(io());
        System.out.println(generic());
        suppressed();
    }
}
```

Biên dịch/chạy trên JDK 17 hoặc mới hơn:

```bash
javac --release 17 CloseContractDemo.java
java CloseContractDemo
```

**Stdout chính xác:**

```text
quiet work
quiet close
quiet result: ready
io work
io close
io caught: flush failed
generic work
generic close
generic caught: generic failure
throw body
io close
primary: body error
suppressed: flush failed
```

### Giải thích kết quả theo hợp đồng của từng resource

**`QuietResource`:** `quiet()` gọi TWR trên kiểu cụ thể `QuietResource`, thân try in `quiet work` và chuẩn bị trả `"ready"`. Trước khi return hoàn tất, TWR gọi `close()`, in `quiet close`. Vì close không ném lỗi, return thành công rồi main mới in `quiet result: ready`. Chữ ký `quiet()` không cần `throws Exception`.

**`IoResource`:** `io()` gặp `return "pending"` trong thân try. TWR vẫn gọi `close()`, in `io close` rồi ném `IOException("flush failed")`. Lỗi close **hủy return đang chờ** và được `catch (IOException)` bắt. Vì vậy kết quả trả về là `"io caught: flush failed"`, không phải `"pending"`. Method `io()` không phải khai báo `throws IOException` vì đã xử lý lỗi.

**`GenericResource`:** `close()` của implementation khai báo `throws Exception`. `generic()` buộc phải bắt `Exception` hoặc khai báo `throws Exception`; ví dụ chủ động bắt và trả chuỗi minh họa. Đây là lý do khi viết API thực tế nên cân nhắc exception cụ thể hơn.

**`suppressed()`:** thân try chủ động ném `IllegalStateException("body error")`. TWR vẫn gọi `IoResource.close()`, nó ném `IOException("flush failed")`. Java giữ `IllegalStateException` làm ngoại lệ **primary**, gắn `IOException` vào `ex.getSuppressed()` và catch được ngoại lệ chính; không chuyển lỗi đóng thành primary trong trường hợp này.

Trong dự án thật, không nên biến các lỗi I/O thành chuỗi rồi trả về một cách tùy tiện như bài demo. Ở đây các phương thức trả chuỗi nhằm giúp người học nhìn thấy đường đi của exception. Code nghiệp vụ nên có chính sách retry, phản hồi lỗi, logging và rollback phù hợp.

## 8. `close()` trong TWR liên quan thế nào đến `catch`, `finally` và `return`?

Một câu lệnh TWR về mặt khái niệm đi theo trật tự:

```text
resource initializer(s)
         |
         v
body of try
         |
         v
auto-close acquired resources
         |
         +-- if exception -> matching catch (if any)
         |
         v
finally (if present)
         |
         v
normal exit / return / exception propagation
```

Các tài nguyên đã mở được đóng **ngược thứ tự khởi tạo**. Nếu khởi tạo resource thứ hai lỗi, Java vẫn cố đóng resource thứ nhất đã thành công.

**`return` trong thân try không bỏ qua close.** Giá trị trả về được tính, nhưng chỉ hoàn tất sau quá trình đóng. Nếu close ném checked exception, một `return` đang chờ có thể bị hủy và ngoại lệ được bắt hoặc truyền ra ngoài. Điều này áp dụng dù `close()` khai báo `IOException` hay `Exception`.

**`catch` nhận cả ngoại lệ từ khởi tạo, thân try hoặc close.** Nếu `catch (IOException)` trong một TWR, không nên mặc định IOException chắc chắn đến từ phép đọc/ghi bên trong body. Lỗi mở hoặc lỗi đóng cũng có thể dẫn đến catch.

**`finally` chạy sau khi đã cố đóng resource** và sau catch nếu catch phù hợp được thực thi. Không cần gọi `resource.close()` một lần nữa trong finally. `return` trong finally là lỗi thiết kế nguy hiểm vì có thể ghi đè return hoặc exception đang chờ, làm mất chẩn đoán.

## 9. Ngoại lệ primary, `suppressed` và trách nhiệm của `close()`

Một lợi ích then chốt của TWR là **bảo toàn lỗi quan trọng hơn** nếu vừa thao tác vừa đóng resource đều thất bại.

- **Không lỗi ở body, close lỗi:** ngoại lệ của close trở thành lỗi chính và có thể thoát ra cho caller.
- **Body đã ném lỗi E, close ném F:** E giữ vai trò primary; F thường được bổ sung vào `E.getSuppressed()`.
- **Nhiều resource cùng close lỗi:** Java cố đóng theo thứ tự ngược; khi đã có primary, các lỗi close được suppressed theo thứ tự tương ứng. Nếu chưa có lỗi từ body, lỗi close đầu tiên có thể là primary và các lỗi close sau trở thành suppressed.
- **Có `catch` bên ngoài cùng TWR:** catch chạy **sau** giai đoạn auto-close. Nếu đang có E là primary, catch phù hợp với E; nó không tự chuyển sang catch phù hợp F chỉ vì F nằm trong suppressed.

Ví dụ mã minh họa cần đặt trong một phương thức có `openResource()` và các phương thức thích hợp:

```java
try (AutoCloseable resource = openResource()) {
    performWork();
} catch (Exception ex) {
    System.err.println("Primary: " + ex);
    for (Throwable closeFailure : ex.getSuppressed()) {
        System.err.println("Suppressed: " + closeFailure);
    }
}
```

Cần chú ý `catch (Exception)` trong ví dụ này **rộng** vì biến resource có kiểu `AutoCloseable`. Với code nghiệp vụ thật, nên khai báo kiểu resource/exceptions cụ thể, tránh một catch rộng làm che lỗi nếu không có chính sách xử lý rõ ràng. Đồng thời không chỉ ghi `ex.getMessage()` rồi bỏ qua stack trace/cause/suppressed; ưu tiên logging API nhận nguyên `Throwable` ở ranh giới có trách nhiệm xử lý.

### 9.1. Tại sao không nên ném `InterruptedException` từ close?

Javadoc của `AutoCloseable` **khuyến cáo mạnh không khai báo hoặc ném `InterruptedException` từ `close()`**. Nguyên nhân là InterruptedException thường mang ngữ nghĩa về trạng thái ngắt của thread; khi TWR đang có một lỗi chính, lỗi close có thể bị suppressed, khiến xử lý ngắt khó chính xác hoặc gây trạng thái khó dự đoán.

Nếu cleanup có thao tác có thể bị ngắt, thiết kế chính sách interruption/cleanup cẩn thận theo hợp đồng concurrency của ứng dụng, thay vì coi `InterruptedException` là loại lỗi close mặc định. Không nuốt interruption để “làm cho close không có throws”; nếu thật sự xử lý interrupted state, phải xét vai trò tầng hiện tại, tín hiệu ngắt và các phương án phục hồi.

### 9.2. Khi nào cần kiểm tra `getSuppressed()`?

Trong lỗi khi body ném exception và close cũng ném exception, chỉ nhìn `getCause()` hoặc message của primary có thể không cho thấy lỗi close. Logging đầy đủ `Throwable` thường giúp giữ những thông tin này. Với test, có thể kiểm tra cụ thể:

```java
try (IoResource resource = new IoResource()) {
    throw new IllegalStateException("body");
} catch (IllegalStateException ex) {
    assert ex.getSuppressed().length == 1;
    assert ex.getSuppressed()[0] instanceof java.io.IOException;
}
```

Đây là **đoạn minh họa trong cùng lớp có `IoResource`**; khi dùng `assert`, phải bật `-ea` để xác nhận lúc chạy. Ví dụ có thể dùng công cụ kiểm thử như JUnit thay cho `assert` trong dự án; các điều kiện trên phản ánh đúng mục đích của suppression.

## 10. Tính idempotent, quản lý vòng đời và lỗi cleanup

**Idempotent close** nghĩa là gọi close lần sau khi resource đã đóng không tạo thêm tác động. Nhưng không được suy luận mọi implementation của `AutoCloseable` đều đảm bảo như vậy.

- Hợp đồng `AutoCloseable` khuyến khích nhiều implementation đóng lặp an toàn, nhưng **không bắt buộc `close()` phải idempotent**.
- Hợp đồng `Closeable.close()` có yêu cầu mạnh hơn: nếu stream/resource đã đóng, gọi close lại không còn tác dụng.
- Với resource do bạn thiết kế, hãy **tài liệu hóa rõ** có cho phép đóng lặp hay không, trạng thái sau lỗi close và ai chịu trách nhiệm đóng. Nếu sử dụng các kiểu “scope guard” không idempotent, không nên vô ý đóng hai lần.
- Đừng lấy việc dùng TWR làm bằng chứng rằng một resource an toàn khi nhiều thread cùng truy cập hoặc đóng đồng thời. Thread safety là hợp đồng khác.

**Không cần `finally { resource.close(); }` cho cùng resource đã nằm trong TWR.** Làm vậy có thể khiến close chạy hai lần, gây lỗi hoặc hành vi phụ không mong muốn. Dọn tài nguyên nên có một owner chính.

### 10.1. Chọn mức đảm bảo của close

Một phương thức close tốt thường:

1. giảm thiểu side effect không liên quan;
2. cố giải phóng tài nguyên thật sự sở hữu;
3. mô tả hậu điều kiện nếu thành công/thất bại;
4. dùng exception có nghĩa khi không thể bảo đảm hậu điều kiện;
5. không vô tình thay đổi stack trace/cause của lỗi đã tồn tại;
6. cân nhắc cách kiểm thử đường đóng thành công và thất bại.

**Không phải mọi cleanup đều là thao tác “không thể thất bại”.** Ví dụ flush khi đóng writer, commit/rollback được gắn vào close của một loại resource tùy thiết kế, hoặc trả một connection về pool đều có thể có lỗi riêng. Trước khi cam kết `close()` không khai báo checked exception, cần chắc chắn đó là một lời hứa API hợp lý.

## 11. Chọn `AutoCloseable`, `Closeable` hoặc một interface chuyên biệt

### 11.1. Resource I/O với lỗi đóng kiểu IOException

```java
interface DocumentSource extends java.io.Closeable {
    String nextLine() throws java.io.IOException;

    @Override
    void close() throws java.io.IOException;
}
```

Interface minh họa này phù hợp khi việc đóng thuộc miền I/O. Thực tế nếu chỉ đọc dòng, có thể dùng các lớp chuẩn như `BufferedReader` thay vì tạo abstraction mới. Mục đích là thể hiện rằng mọi client có thể biết `IOException` là nhóm checked exception phải xử lý.

### 11.2. Resource domain không phải I/O

```java
interface JobLease extends AutoCloseable {
    void execute() throws JobException;

    @Override
    void close() throws JobException;
}

final class JobException extends Exception {
    JobException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Các khai báo này là **minh họa**; implementation cụ thể và chính sách lỗi cần bổ sung ở dự án. Vì `JobException extends Exception`, chữ ký `close() throws JobException` là override hợp lệ của `AutoCloseable.close()`. Nếu caller chỉ cần `JobLease`, compiler cho phép khai báo `throws JobException` thay vì một `Exception` không phân biệt lỗi.

Chỉ tạo custom checked exception khi có ý nghĩa: caller cần phục hồi hoặc ra quyết định dựa trên loại lỗi đó. Nếu abstraction không cần checked failure, có thể khai báo `void close()`. Tránh thiết kế cả cây exception chỉ để làm đẹp ví dụ.

### 11.3. Resource không có checked close failure

```java
interface ScopeHandle extends AutoCloseable {
    @Override
    void close();
}
```

Chỉ nên cam kết kiểu này nếu hành vi cleanup đủ tin cậy theo hợp đồng. Nó cho phép dùng try-with-resources mà **không bắt/khai báo Exception chỉ vì close**, ngay cả khi biến được khai báo là `ScopeHandle`. Dùng `AutoCloseable` trực tiếp trong chữ ký caller sẽ đánh mất lợi ích narrow-throws ở compile-time.

### 11.4. Khi nào giữ nguyên `Exception`?

Nếu API nhận `AutoCloseable` của bên ngoài mà không biết loại close failure, việc khai báo hoặc xử lý `Exception` có thể không tránh khỏi:

```java
static void withResource(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("using externally provided resource");
    }
}
```

Đây là **phương thức minh họa Java 9+**. `resource` là parameter, được dùng lại trong ngoặc TWR (cú pháp resource variable). Phương thức cần xử lý/khai báo `Exception` vì kiểu `AutoCloseable` được chấp nhận quá rộng. Đồng thời cần quy định **ownership**: lời gọi này sẽ đóng resource của caller. Không viết utility như vậy nếu caller vẫn cần sử dụng resource sau khi hàm trả về, trừ khi hợp đồng giao ownership đã rất rõ.

## 12. Kiểm thử các hợp đồng close thay vì chỉ kiểm tra happy path

Với một resource tự thiết kế, kiểm thử ít nhất:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Tạo và sử dụng thành công, close thành công | Resource được đóng và hậu điều kiện đúng. |
| Body có `return` | Close vẫn được gọi trước khi caller nhận kết quả. |
| Body ném lỗi, close thành công | Lỗi body được giữ lại. |
| Body thành công, close ném lỗi checked | Caller nhận hoặc bắt loại đã được công bố ở chữ ký close. |
| Body ném E và close ném F | E là primary; F nằm trong `getSuppressed()` nếu TWR xử lý theo cơ chế chuẩn. |
| Có hai resource | Đóng ngược thứ tự tạo; vẫn cố đóng resource còn lại khi một close lỗi. |
| Khởi tạo resource thứ hai thất bại | Resource thứ nhất được đóng trước khi exception truyền ra. |
| Gọi close lần nữa | Phù hợp với hợp đồng idempotency đã được công bố. |
| Trạng thái sau close lỗi | Không để resource ở trạng thái nguy hiểm mà caller tưởng đã giải phóng; báo lỗi/ghi nhận phù hợp. |
| Kiểu tĩnh khác nhau | Chữ ký `throws` của phương thức sử dụng phản ánh đúng kiểu resource được khai báo. |

Test loại ngoại lệ và cause/suppressed, không chỉ khớp message. Với code chạy trong CI, biên dịch ở mức `--release` đúng JDK hỗ trợ để phát hiện phụ thuộc API/cú pháp mới ngoài mục tiêu.

## 13. Những lỗi thiết kế và suy luận thường gặp

**Lỗi 1 — “Implements AutoCloseable thì close phải throws Exception.”** Sai. Implementation được phép thu hẹp hoặc không khai báo checked exception.

**Lỗi 2 — “Muốn try-with-resources thì nhất thiết implements Closeable.”** Sai. Chỉ cần resource là subtype của `AutoCloseable`; `Closeable` là một subtype chuyên biệt.

**Lỗi 3 — “Closeable có thể throws SQLException vì SQLException là Exception.”** Sai. `Closeable.close` chỉ cho phép `IOException` hoặc checked subtype phù hợp; `SQLException` không là subtype của `IOException`.

**Lỗi 4 — “Object runtime có close không throws thì kiểu AutoCloseable cũng không cần xử lý Exception.”** Sai. Compiler dựa trên kiểu tĩnh của resource, không chỉ class được khởi tạo.

**Lỗi 5 — “Một return trong try ngăn close ném ngoại lệ.”** Sai. Auto-close diễn ra trước khi return hoàn thành; lỗi close có thể hủy return.

**Lỗi 6 — “Close lỗi trong khi body lỗi sẽ ghi đè lỗi body.”** TWR thông thường giữ lỗi body làm primary và gắn lỗi close vào suppressed; đây là điểm cải tiến quan trọng.

**Lỗi 7 — “Đặt thêm close() trong finally sẽ an toàn hơn.”** Không. Với cùng resource do TWR quản lý, đó là hành động đóng lặp và có thể tạo lỗi không cần thiết.

**Lỗi 8 — “AutoCloseable.close() luôn idempotent.”** Sai. Đó không phải bảo đảm chung của interface; đọc hợp đồng loại resource cụ thể.

**Lỗi 9 — “Cho mọi close throws Exception giúp API linh hoạt.”** Có thể làm caller phải bắt/khai báo lỗi quá rộng và khó phân biệt nguyên nhân. Thiết kế ngoại lệ dựa trên miền lỗi thực.

**Lỗi 10 — “Có thể bỏ qua InterruptedException trong close cho đơn giản.”** Không nên. Javadoc khuyến cáo tránh dùng InterruptedException làm loại lỗi close; nếu cleanup bị ngắt, phải thiết kế xử lý gián đoạn theo chính sách concurrency.

**Lỗi 11 — “Đóng resource là commit thành công.”** Không đúng với AutoCloseable nói chung; commit/rollback và kết quả nghiệp vụ phải do loại resource cụ thể định nghĩa.

**Lỗi 12 — “Cứ catch Exception quanh mọi TWR là an toàn.”** Không. Catch rộng có thể che bug hoặc nuốt lỗi không thuộc khả năng phục hồi. Ưu tiên checked types cụ thể, logging có nguyên Throwable và chính sách rõ ở ranh giới xử lý.

## 14. Quy trình lựa chọn ngoại lệ cho một lớp mới

1. **Liệt kê việc close thật sự làm:** flush, release, rollback, unlock, return-to-pool, dispose...
2. **Xác định lỗi cleanup caller phải thấy:** là I/O (`IOException`), SQL (`SQLException`), lỗi nghiệp vụ có cấu trúc riêng hay không có checked exception?
3. **Chọn interface và chữ ký:** `Closeable` nếu tuân thủ hợp đồng I/O; `AutoCloseable` nếu vòng đời rộng hơn; nếu API cần, tạo interface chuyên biệt với `close() throws SpecificException`.
4. **Không mở rộng throws vô lý:** khi override chỉ được giữ hoặc thu hẹp checked exceptions so với phương thức cha.
5. **Kiểm tra ảnh hưởng tới caller:** `try (SpecificResource r = ...)` cần khai báo/bắt gì? Nếu chỉ thấy kiểu `AutoCloseable` thì có phải khai báo `Exception` không?
6. **Định nghĩa ownership và hậu điều kiện:** ai đóng, có đóng nhiều lần được không, trạng thái sau lỗi close thế nào?
7. **Viết test cho close lỗi:** cả body thành công, body thất bại, return đang chờ, nhiều resource và suppressed.
8. **Sử dụng TWR nhất quán:** không đóng thêm trong finally; không vô tình che lỗi chính bằng exception mới bỏ cause.
9. **Đảm bảo kiểu lỗi đủ thông tin:** giữ cause/suppressed khi wrap, log nguyên Throwable ở tầng có trách nhiệm, không log lặp vô ích.
10. **Biên dịch trên JDK mục tiêu:** kiến thức TWR/AutoCloseable từ Java 7 vẫn áp dụng, nhưng không cần dùng JDK 7 đã cũ để kiểm thử triển khai hiện đại.

## 15. Câu hỏi tự kiểm tra

**1.** Interface `AutoCloseable.close()` khai báo ngoại lệ checked nào? — **`Exception`**. Implementation có thể khai báo checked exception hẹp hơn hoặc không khai báo.

**2.** `Closeable.close()` được khai báo khác ở đâu? — Nó thu hẹp thành **`IOException`** và có hợp đồng đóng lặp mạnh hơn.

**3.** Lớp `LocalScope implements AutoCloseable` có thể override `public void close()` mà không có `throws`? — **Có**, và caller dùng kiểu `LocalScope` không phải xử lý checked close exception chỉ vì thuộc tính AutoCloseable.

**4.** `java.io.Closeable.close() throws Exception` trong implementation có hợp lệ không? — **Không**, vì đã mở rộng checked throws vượt quá `IOException`.

**5.** `try (AutoCloseable r = new QuietResource())` có phải xử lý `Exception` không? — **Có theo kiểm tra kiểu tĩnh**, dù `QuietResource.close()` không khai báo checked exception.

**6.** `try (QuietResource r = new QuietResource())` có tự bắt buộc `throws Exception` không? — **Không**, trừ khi các thao tác khác trong try đòi hỏi xử lý checked exception.

**7.** Nếu cả body và close đều ném lỗi, lỗi nào primary? — Trong TWR thông thường, lỗi body primary, lỗi close bị **suppressed**.

**8.** TWR tự gọi close khi gặp `return`? — **Có**; return chỉ hoàn tất sau khi đóng, trừ khi có lỗi hoặc hành vi khác thay thế.

**9.** Một class nghiệp vụ có close ném `SQLException` nên implements `Closeable` hay `AutoCloseable`? — **`AutoCloseable`** hoặc abstraction chuyên biệt kế thừa nó; `SQLException` không được phép làm checked throws của `Closeable.close()`.

**10.** Tại sao không chọn `throws Exception` cho mọi resource? — Vì làm API caller phải xử lý lỗi rộng và giảm khả năng thể hiện domain failure chính xác.

**11.** Từ việc implements `AutoCloseable` có suy ra `close()` thread-safe và idempotent không? — **Không**; phải đọc hợp đồng riêng của implementation.

**12.** Có nên tự viết `finally { resource.close(); }` khi đã dùng `try (resource)`? — **Không nên** cho cùng vòng đời; TWR đã đảm nhiệm việc đóng.

## Tài liệu chuẩn để tham khảo

- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): chữ ký `close() throws Exception`, idempotency và lưu ý `InterruptedException`.
- [Java SE 17 API — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): quan hệ kế thừa với AutoCloseable, `close() throws IOException` và đóng lại.
- [Java Language Specification 17 §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): checked exceptions khi override phương thức.
- [Java Language Specification 17 §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cơ chế tự đóng, ngoại lệ suppressed, thứ tự xử lý.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()` và `getSuppressed()`.

**Ghi nhớ:** `AutoCloseable.close()` cho phép **`throws Exception`**, không buộc implementation phải dùng mức rộng đó. Chọn **checked exception cụ thể** (hoặc không có checked exception khi phù hợp), hiểu **kiểu tĩnh của resource** quyết định yêu cầu xử lý `throws`, và để **try-with-resources** quản lý đóng/suppression một cách nhất quán.