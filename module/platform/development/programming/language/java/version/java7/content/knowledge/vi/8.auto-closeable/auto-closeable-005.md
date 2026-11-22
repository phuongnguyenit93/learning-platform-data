# Quy tắc đóng một lần, đóng lặp và trạng thái sau khi đóng với `AutoCloseable` trong Java

## 1. Vấn đề: “tự đóng” không đồng nghĩa với “không bao giờ đóng lặp”

Một đối tượng `AutoCloseable` đại diện cho tài nguyên có thể kết thúc vòng đời bằng lời gọi `close()`. Đó có thể là luồng tệp, socket, kết nối cơ sở dữ liệu, một phiên giao dịch hoặc tài nguyên tự thiết kế. Từ Java 7, `try-with-resources` giúp tự gọi `close()` khi kết thúc phạm vi sử dụng:

```java
try (SomeResource resource = openResource()) {
    useResource(resource);
}
```

Đây là **cú pháp minh họa**: `SomeResource`, `openResource()` và `useResource(...)` không phải tên API tiêu chuẩn có sẵn. Chương trình độc lập, có thể biên dịch bằng Java 17+, được trình bày ở mục 6.

Ba câu hỏi cần phân biệt:

1. **Đóng một lần:** Ai sở hữu tài nguyên và chịu trách nhiệm gọi `close()`? Một mục tài nguyên trong `try-with-resources` được xử lý đóng khi kết thúc phạm vi.
2. **Đóng lặp:** Nếu cùng đối tượng nhận **nhiều lời gọi** `close()`, lần thứ hai có làm gì, ném lỗi hoặc gây side effect không?
3. **Trạng thái sau đóng:** Sau khi `close()` được gọi, đối tượng được phép thực hiện thao tác nào? Nếu việc đóng thất bại giữa chừng, trạng thái có chắc chắn là “đã đóng” không?

**Thông điệp cốt lõi:** Giao diện `AutoCloseable` cho phép quản lý tài nguyên có cấu trúc, nhưng **không tự bảo đảm `close()` là idempotent, không ngăn mọi lần gọi lặp và không đặt ra quy tắc chung cho mọi phương thức sau đóng**. Những thuộc tính đó phụ thuộc hợp đồng và cách triển khai của từng loại tài nguyên.

## 2. Hợp đồng `AutoCloseable.close()`

`AutoCloseable` nằm trong gói `java.lang` và có phương thức:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Đây là **chữ ký giao diện rút gọn để học**, không phải tệp mã nguồn cần sao chép để khai báo lại `AutoCloseable` của JDK.

- Lớp triển khai phải cung cấp một `public void close()` phù hợp (trực tiếp hoặc thông qua kế thừa).
- Phương thức triển khai được phép khai báo **ít checked exception hơn** hoặc không khai báo checked exception nào. Không buộc mọi lớp phải `throws Exception`.
- `try-with-resources` yêu cầu **kiểu tĩnh** của tài nguyên tương thích với `AutoCloseable`; chỉ có phương thức tên `close` nhưng không triển khai interface thì không đủ.
- Việc gọi `close()` có ý nghĩa theo **hợp đồng của chính tài nguyên**. Interface không tự đóng file/socket, không tự thiết lập cờ `closed` và cũng không làm đối tượng thread-safe.

Một triển khai tối giản:

```java
class SmallResource implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("Resource is closed");
        }
        // Làm việc khi tài nguyên còn hiệu lực.
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        // Thực hiện giải phóng thực tế nếu lớp sở hữu tài nguyên.
    }
}
```

Đây là **khung minh họa trong một chương trình đơn luồng**, chưa giải phóng tài nguyên I/O thật. Nó cho thấy cách tự định nghĩa quy tắc “sau đóng” và cách bỏ qua lời gọi đóng lặp. Với tài nguyên thật, cần quyết định cách xử lý lỗi trong lúc giải phóng và trạng thái trung gian, không sao chép phần thân này mà bỏ qua phần quản lý tài nguyên thực.

## 3. Đóng một lần: trách nhiệm thuộc về ai?

Về mặt thiết kế, nên có **một chủ sở hữu rõ ràng** chịu trách nhiệm kết thúc vòng đời tài nguyên. Phần mã chỉ mượn để đọc/ghi tạm thời thường không tự đóng tài nguyên nếu tài nguyên phải còn hoạt động cho caller.

Ví dụ khi hàm **tự tạo và sở hữu** luồng:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String readFirstLine(Path path) throws IOException {
    try (var reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Đây là phương thức minh họa **đặt trong một lớp Java**; `var` là cú pháp Java 10+, vì vậy ví dụ này biên dịch trên Java 17+. `reader` được tạo trong `try` và thuộc phạm vi sở hữu của lời gọi này; Java đóng nó khi trả kết quả hoặc khi một thao tác ném lỗi.

Ngược lại, nếu hàm nhận một `Reader` do caller truyền vào và caller còn muốn sử dụng sau lời gọi, hàm không nên tự ý đóng nó nếu hợp đồng không giao ownership:

```java
import java.io.IOException;
import java.io.Reader;

static int readOneCharacter(Reader borrowed) throws IOException {
    return borrowed.read(); // Không đóng: caller vẫn sở hữu borrowed.
}
```

**Hợp đồng sở hữu** quan trọng hơn việc thêm `try-with-resources` ở mọi chỗ. Tự động đóng một tài nguyên được chia sẻ quá sớm có thể làm những chỗ khác bị lỗi.

### Một mục tài nguyên, một lần đóng do cú pháp tạo ra

```java
try (SmallResource r = new SmallResource()) {
    r.use();
}
```

Nếu khởi tạo thành công và `r` khác `null`, Java thực hiện thao tác đóng của mục `r` khi rời khối. Việc thoát bằng đường thông thường, `return` hoặc ngoại lệ không làm bỏ qua xử lý đóng theo luồng điều khiển Java thông thường.

Tuy nhiên, câu này **không phải lời hứa “mỗi đối tượng chỉ có đúng một lời gọi `close()` trong cả chương trình”**. Người lập trình vẫn có thể gọi `r.close()` bên trong khối, gọi nó từ một hàm khác, hoặc đưa cùng đối tượng vào nhiều mục tài nguyên.

Nếu khởi tạo tài nguyên thất bại, những tài nguyên đã khởi tạo thành công ở các mục trước đó vẫn được đóng; đối tượng chưa khởi tạo thành công không tự trở thành một tài nguyên đã đăng ký để đóng. Trường hợp nguồn `null` thì thao tác tự động đóng bỏ qua nguồn đó, nhưng truy cập vào nó trong thân `try` vẫn có thể gây `NullPointerException`.

## 4. Đóng lặp: khái niệm *idempotent* và sự khác biệt giữa hai interface

**Idempotent** nghĩa là việc thực hiện cùng thao tác thêm lần nữa không làm thay đổi **trạng thái/kết quả mong muốn của tài nguyên** sau lần đầu đã hoàn tất. Với `close()` idempotent, tài nguyên đã đóng sẽ không bị giải phóng hai lần hoặc làm biến đổi vòng đời theo cách ngoài dự kiến.

Cần tách:

- **Số lần `close()` được gọi:** có thể là 2 hoặc nhiều hơn.
- **Số lần tài nguyên thực sự được giải phóng:** một triển khai idempotent thường bảo vệ để chỉ giải phóng một lần.
- **Số lần in log/đếm lời gọi:** một chương trình có thể vẫn ghi log mỗi lần gọi, dù trạng thái tài nguyên sau đóng không đổi. Vì vậy không nên chỉ đếm log rồi kết luận tài nguyên đã được giải phóng nhiều lần.

Hai giao diện có hợp đồng khác nhau:

| Đặc điểm | `java.lang.AutoCloseable` | `java.io.Closeable` |
| --- | --- | --- |
| Quan hệ | Giao diện tổng quát của tài nguyên có thể đóng | `Closeable extends AutoCloseable` |
| Chữ ký chính | `void close() throws Exception` | `void close() throws IOException` |
| Đóng lặp | **Không bắt buộc** `close()` idempotent | Hợp đồng yêu cầu gọi `close()` trên một tài nguyên **đã đóng** không có tác dụng |
| Khả năng dùng `try-with-resources` | Có | Có |
| Loại lỗi checked | Có thể rộng là `Exception`; triển khai được phép hẹp hơn | Thường theo hợp đồng `IOException` |

Javadoc của `AutoCloseable` **khuyến khích** nhà triển khai viết `close()` idempotent nếu phù hợp, nhưng **không bắt buộc**. Một lớp triển khai `AutoCloseable` có thể ném lỗi hoặc có side effect ở lần gọi sau. `Closeable` có hợp đồng chặt hơn: với đối tượng đã ở trạng thái đóng, gọi `close()` thêm lần nữa không có tác dụng.

Đừng hiểu yêu cầu của `Closeable` như một quy tắc rằng mọi thao tác `close()` đều chắc chắn thành công hoặc mọi implementation đều hoàn hảo. Nếu lần đóng trước **đã báo lỗi**, ứng dụng vẫn phải dựa vào hợp đồng cụ thể để biết tài nguyên có thật sự được đóng hay không.

## 5. Vì sao `try-with-resources` vẫn có thể gọi `close()` nhiều lần?

### 5.1. Gọi thủ công bên trong `try`

```java
try (SmallResource r = new SmallResource()) {
    r.use();
    r.close(); // Gọi thủ công lần thứ nhất.
}              // Java vẫn thực hiện thao tác đóng tự động.
```

Khi rời khối, Java **không tự phát hiện** rằng lập trình viên đã gọi `close()` trước đó để bỏ qua phần đóng của mục tài nguyên. Nếu lớp không bảo vệ đóng lặp, lần sau có thể có hiệu ứng khác hoặc ném ngoại lệ.

**Thực hành tốt:** trong trường hợp sở hữu rõ ràng, thường **để `try-with-resources` tự đóng**, không gọi `close()` thủ công bên trong khối. Chỉ làm việc đó nếu hợp đồng thật sự đòi hỏi giải phóng sớm và đã thiết kế trạng thái cho tình huống gọi lặp.

### 5.2. Cùng một đối tượng xuất hiện ở hai mục tài nguyên

```java
Unguarded shared = new Unguarded();

try (Unguarded first = shared;
     Unguarded second = shared) {
    System.out.println("body");
}
```

Ở đây `first` và `second` là hai biến khác nhau **cùng trỏ đến một đối tượng**. Java xử lý từng mục tài nguyên, gọi `second.close()` rồi `first.close()`, nên cùng đối tượng nhận **hai lời gọi**. Cú pháp không tự loại bỏ phần tử trùng hoặc kiểm tra “đã gọi close cho identity này chưa”.

Đoạn trên sử dụng lớp `Unguarded` trong chương trình chạy đầy đủ ở mục 6. Với tài nguyên thật, việc chia sẻ ownership kiểu này thường không nên làm trừ khi API hỗ trợ đóng lặp an toàn.

### 5.3. Dùng biến tài nguyên đã khai báo trước

Từ Java 9, một biến `final` hoặc *effectively final* có thể xuất hiện trực tiếp trong ngoặc:

```java
SmallResource resource = new SmallResource();
try (resource) {
    resource.use();
}
```

Sau khi khối kết thúc, **biến `resource` vẫn tồn tại trong phạm vi**, nhưng đối tượng mà nó trỏ tới đã nhận lời gọi `close()`. Java **không tự gán biến về `null`**. Vì thế, việc biến còn tồn tại không có nghĩa tài nguyên còn mở. Cú pháp `try (resource)` được bổ sung ở Java 9; phần khai báo tài nguyên trong ngoặc đã có từ Java 7.

Nếu gọi `resource.close()` một lần nữa sau đó, hành vi vẫn theo hợp đồng của lớp triển khai. Tương tự, đưa biến đó vào một khối `try (resource)` khác sẽ khiến nó được đóng lại khi khối thứ hai kết thúc; điều này không có nghĩa tài nguyên tự mở lại.

## 6. Chương trình Java 17+ đầy đủ: đóng một lần và hai lời gọi vào cùng đối tượng

Ví dụ minh họa hai lớp:

- `Guarded` đánh dấu trạng thái và bỏ qua các lần đóng sau, nên số lần **giải phóng theo logic** là 1.
- `Unguarded` không có bước bảo vệ, nên số lần gọi `close()` được phản ánh rõ qua bộ đếm; nó mô phỏng một triển khai `AutoCloseable` **không idempotent về side effect**.

Tạo tệp **`CloseLifecycleDemo.java`**:

```java
public class CloseLifecycleDemo {

    static final class Guarded implements AutoCloseable {
        private final String name;
        private boolean closed;
        private int releases;

        Guarded(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        void use() {
            if (closed) {
                throw new IllegalStateException(name + " is closed");
            }
            System.out.println("use " + name);
        }

        boolean isClosed() {
            return closed;
        }

        int releaseCount() {
            return releases;
        }

        @Override
        public void close() {
            if (closed) {
                return;
            }
            closed = true;
            releases++;
            System.out.println("release " + name);
        }
    }

    static final class Unguarded implements AutoCloseable {
        private int calls;

        @Override
        public void close() {
            calls++;
            System.out.println("unguarded close #" + calls);
        }

        int closeCalls() {
            return calls;
        }
    }

    public static void main(String[] args) {
        Guarded resource = new Guarded("A");

        // Java 9+: resource là biến effectively final tạo sẵn.
        try (resource) {
            resource.use();
            resource.close(); // Minh họa đóng thủ công.
            System.out.println("inside try, closed = "
                    + resource.isClosed());
        }

        resource.close(); // Thêm một lời gọi ngoài try.
        System.out.println("release count = "
                + resource.releaseCount());

        try {
            resource.use();
        } catch (IllegalStateException ex) {
            System.out.println("after close: " + ex.getMessage());
        }

        Unguarded shared = new Unguarded();

        // Hai mục tài nguyên cùng trỏ đến một đối tượng.
        try (Unguarded first = shared; Unguarded second = shared) {
            System.out.println("same instance in two entries");
        }

        System.out.println("unguarded calls = "
                + shared.closeCalls());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CloseLifecycleDemo.java
java CloseLifecycleDemo
```

**Stdout chính xác:**

```text
open A
use A
release A
inside try, closed = true
release count = 1
after close: A is closed
same instance in two entries
unguarded close #1
unguarded close #2
unguarded calls = 2
```

Diễn giải từng phần:

1. `resource` được tạo và ở trạng thái mở. Lệnh `use()` đầu tiên chạy thành công.
2. Lệnh `resource.close()` thủ công đánh dấu `closed = true`, tăng `releases` lên 1 rồi in `release A`.
3. Khi rời `try (resource)`, Java vẫn gọi `close()`. Vì có `if (closed) return;`, lần này không tăng `releases` và không in thêm.
4. `resource.close()` sau khối là lời gọi thứ ba; `releases` vẫn là 1 vì lớp bảo vệ đóng lặp.
5. `resource.use()` sau đóng ném `IllegalStateException` theo quy tắc do `Guarded` tự định nghĩa.
6. `first` và `second` cùng tham chiếu tới `shared`. Hai lần đóng tự động gọi cùng một `Unguarded.close()`, làm bộ đếm lên 2.

**Giới hạn mẫu:** hai lớp chỉ mô phỏng việc “giải phóng”, không sở hữu socket hay file descriptor thật, và biến boolean chưa bảo đảm an toàn khi bị nhiều luồng truy cập đồng thời. Trong ứng dụng thực tế, mã giải phóng tài nguyên và xử lý lỗi cần được viết theo hợp đồng của hệ thống.

## 7. Sau khi đóng: trạng thái không được `AutoCloseable` quy định chung

Với `Guarded` trong ví dụ, sau khi `closed` được đặt thành `true`, phương thức `use()` chủ động từ chối sử dụng:

```java
if (closed) {
    throw new IllegalStateException("Resource is closed");
}
```

Đây là **chính sách của lớp `Guarded`**, không phải quy tắc mà Java tự chèn vào mọi lớp triển khai `AutoCloseable`.

Những hành vi có thể gặp ở các loại tài nguyên khác nhau:

| Sau `close()` | Hành vi có thể có | Cần ghi nhớ |
| --- | --- | --- |
| Gọi `read()`, `write()` hoặc thao tác I/O | Có thể ném `IOException` hoặc lỗi trạng thái tương ứng | Đọc hợp đồng của lớp cụ thể, không dựa vào interface chung |
| Gọi `execute()` trên đối tượng database đã đóng | Có thể báo `SQLException` theo API | Không coi tham chiếu còn tồn tại là kết nối còn mở |
| Gọi `isClosed()` nếu lớp có hỗ trợ | Trả trạng thái theo định nghĩa lớp | `AutoCloseable` **không định nghĩa** `isClosed()` |
| Gọi `close()` lần nữa | Có thể không có tác dụng, gây side effect hoặc thất bại | `AutoCloseable` không đòi idempotence |
| Gọi phương thức lấy thông tin đã lưu | Một số lớp vẫn cho phép, một số lớp cấm | Quy tắc do lớp/ API xác định |
| Gọi `open()` hoặc tạo lại đối tượng | Phụ thuộc loại tài nguyên | `AutoCloseable` không cung cấp cơ chế tự mở lại |

Một ví dụ đặc biệt trong JDK: `java.io.ByteArrayInputStream.close()` không có tác dụng đối với việc đọc từ mảng byte của nó; đối tượng vẫn có thể đọc dữ liệu sau `close()`. Điều này nhắc rằng **“đã gọi `close()`” không mặc nhiên đồng nghĩa với “mọi phương thức của đối tượng sẽ ném lỗi”**.

Ngược lại, với các tài nguyên gắn với hệ điều hành hoặc dịch vụ bên ngoài, ứng dụng nên coi lời gọi `close()` là mốc **kết thúc quyền sử dụng**, trừ khi hợp đồng tài nguyên nói rõ có thể tiếp tục.

### Nên dùng một trạng thái hay nhiều trạng thái?

Với tài nguyên đơn giản, mô hình có thể chỉ là:

```text
OPEN --close()--> CLOSED

CLOSED --close()--> CLOSED    (nếu thiết kế idempotent)
CLOSED --use()----> ERROR     (nếu hợp đồng không cho sử dụng lại)
```

Với tài nguyên phức tạp, có thể cần:

```text
OPEN --> CLOSING --> CLOSED
          |
          +-------> FAILED / PARTIALLY_CLOSED
```

Sơ đồ thứ hai chỉ là **mô hình thiết kế**, không phải những trạng thái bắt buộc của `AutoCloseable`. Một kết nối có thể được đóng một phần khi thao tác dọn dẹp thất bại; việc nên thử đóng lại, báo lỗi vĩnh viễn hay mở một tài nguyên mới phải theo API cụ thể.

## 8. Nếu `close()` ném ngoại lệ thì tài nguyên đã đóng chưa?

**Không thể khẳng định chỉ từ chữ ký `AutoCloseable`.** Phương thức `close()` có thể ném checked exception như `IOException`, `SQLException` hay kiểu do ứng dụng định nghĩa, hoặc ném unchecked exception. Việc thất bại xảy ra **trước**, **giữa** hoặc **sau** các bước giải phóng tùy triển khai.

Xét hai cách bố trí trạng thái, chỉ để phân tích:

```java
// Mẫu A (minh họa): ngăn retry trước khi thực hiện dọn dẹp.
@Override
public void close() throws java.io.IOException {
    if (closed) return;
    closed = true;
    releaseOwnedResource(); // Có thể ném IOException.
}
```

`releaseOwnedResource()` là phương thức do ứng dụng định nghĩa. Nếu nó thất bại, `closed` đã là `true`, nên lần gọi tiếp theo bị bỏ qua. Cách này giúp tránh việc giải phóng lặp trong vài thiết kế, nhưng có thể để lại tài nguyên **chưa giải phóng hoàn toàn**. Không nên đánh đồng cờ `closed` với bằng chứng hệ điều hành đã giải phóng mọi thứ.

```java
// Mẫu B (minh họa): chỉ đổi trạng thái sau khi dọn dẹp thành công.
@Override
public void close() throws java.io.IOException {
    if (closed) return;
    releaseOwnedResource(); // Có thể ném IOException.
    closed = true;
}
```

Nếu giải phóng thất bại, cờ vẫn là `false`, nhưng **điều đó cũng không bảo đảm retry an toàn**: lần đầu có thể đã giải phóng một phần tài nguyên. Đây là lý do vòng đời tài nguyên thật cần hợp đồng riêng cho lỗi đóng và chính sách thử lại.

**Hướng tiếp cận an toàn:** ưu tiên để API đóng tự quản lý trạng thái đúng; không viết vòng lặp retry `close()` chung cho mọi `AutoCloseable`. Nếu tài nguyên bị lỗi đóng, báo lỗi và ghi nhận các thông tin cần thiết. Khi muốn retry, phải xác minh API đó **cho phép và định nghĩa rõ** hành vi retry.

## 9. Ngoại lệ khi đóng và cơ chế `try-with-resources`

`try-with-resources` ưu tiên giữ ngoại lệ từ thân `try`, rồi đính kèm những ngoại lệ phát sinh khi đóng tài nguyên theo cơ chế **suppressed exceptions**:

```java
import java.io.IOException;

// Class minh họa; khai báo trong một lớp Java phù hợp.
class FaultyResource implements AutoCloseable {
    @Override
    public void close() throws IOException {
        throw new IOException("close failed");
    }
}

// Đặt trong phương thức hoặc main:
try (FaultyResource r = new FaultyResource()) {
    throw new IOException("work failed");
} catch (IOException ex) {
    System.out.println(ex.getMessage());              // work failed
    System.out.println(ex.getSuppressed().length);     // 1
}
```

Thân `try` ném `IOException("work failed")` và `close()` ném `IOException("close failed")`. Ngoại lệ `work failed` vẫn là **ngoại lệ chính**, lỗi `close failed` được thêm vào danh sách trả bởi `getSuppressed()`.

Nếu thân `try` thành công nhưng `close()` thất bại, lỗi `close()` có thể trở thành ngoại lệ chính. Nếu có nhiều tài nguyên, chúng được đóng **theo thứ tự ngược với thứ tự khai báo**, và các lỗi đóng phát sinh sau có thể được gắn suppressed vào lỗi chính. Không có cơ chế “tự retry `close()` đến khi thành công” từ cú pháp này.

Quan trọng: **đừng tự động gọi `close()` lần nữa trong `catch`** chỉ vì gặp lỗi đóng. Lỗi thứ hai có thể không có tác dụng, có tác dụng phụ hoặc che khuất lỗi ban đầu tùy lớp. Khi cần chẩn đoán, đọc `getSuppressed()`, giữ stack trace và hợp đồng API của đối tượng.

## 10. Tài nguyên bọc ngoài và quyền sở hữu: tránh đóng trùng

Nhiều tài nguyên là *wrapper* quanh tài nguyên khác, ví dụ một `BufferedReader` bọc một `Reader`. Nếu wrapper **sở hữu** tài nguyên bên trong và `close()` của nó đóng luôn bên trong, việc bạn đăng ký cả hai làm hai mục tài nguyên riêng có thể dẫn đến **nhiều lời gọi đóng** lên đối tượng bên trong.

```java
import java.io.BufferedReader;
import java.io.Reader;

// Minh họa: 'source' do ứng dụng cung cấp.
Reader source = obtainReader();
try (BufferedReader buffered = new BufferedReader(source)) {
    System.out.println(buffered.readLine());
}
```

`obtainReader()` là hàm do ứng dụng định nghĩa, chưa được cung cấp trong đoạn mã. Trong trường hợp thông thường, đóng `buffered` sẽ đóng `source` mà nó bọc. Nếu `source` là tài nguyên được chia sẻ với nơi khác, **đừng bàn giao nó cho một wrapper sẽ tự đóng** trừ khi hợp đồng ownership cho phép.

Quy tắc thiết kế hữu ích:

- Tài nguyên do hàm **tạo mới và sở hữu**: hàm đóng (thường qua `try-with-resources`).
- Tài nguyên chỉ **đi mượn** từ caller: không tự đóng nếu caller còn cần sử dụng.
- Tài nguyên **được wrapper nhận quyền sở hữu**: hiểu rõ wrapper có đóng tài nguyên gốc không, tránh tạo nhiều chủ sở hữu không phối hợp.
- Tài nguyên dùng chung nhiều luồng: cần cơ chế ownership và đồng bộ, không dùng duy nhất cờ `boolean closed` thông thường rồi mặc định an toàn trong race condition.

Nếu một thư viện cung cấp cơ chế đếm tham chiếu (reference counting), pooling hoặc lease, hãy làm theo quy tắc trả tài nguyên/giải phóng **của thư viện**. `AutoCloseable` tự nó không quyết định rằng gọi `close()` là phá hủy vật lý, trả kết nối vào pool hay chỉ kết thúc lease.

## 11. Các lỗi thường gặp

| Sai lầm | Vì sao nguy hiểm/sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ `try-with-resources` bảo đảm một đối tượng chỉ được gọi `close()` đúng một lần trong đời | Có thể gọi thủ công, đăng ký trùng hoặc dùng lại cùng tham chiếu | Quản lý ownership; thiết kế đóng lặp an toàn khi thích hợp |
| Nghĩ `AutoCloseable.close()` đương nhiên idempotent | Interface không yêu cầu | Đọc API cụ thể; cân nhắc bảo vệ trạng thái |
| Nhầm `AutoCloseable` và `Closeable` có cùng hợp đồng đóng lặp | `Closeable` có quy tắc gọi lại trên đối tượng đã đóng không có tác dụng | Phân biệt giao diện và hợp đồng `close()` |
| Gọi `close()` thủ công bên trong `try` mà không cân nhắc lần đóng tự động | Gây lời gọi lặp không cần thiết | Thông thường để `try` tự đóng |
| Hai mục tài nguyên cùng trỏ đến một đối tượng | `close()` có thể bị gọi hai lần | Chỉ có một mục sở hữu hoặc bảo đảm quy tắc đóng lặp |
| Giữ tham chiếu ngoài `try` rồi tiếp tục `use()` | Tham chiếu còn, tài nguyên có thể đã đóng | Kiểm tra hợp đồng và vòng đời, không tái sử dụng sai |
| Tưởng `AutoCloseable` cung cấp `isClosed()` | Giao diện chỉ đặt hợp đồng đóng | Dựa vào API/trạng thái của lớp cụ thể |
| Luôn ném `IllegalStateException` sau `close()` | Không phải hành vi chung của mọi tài nguyên | Chỉ là một lựa chọn thiết kế của lớp |
| Coi `close()` ném lỗi là chắc chắn chưa đóng | Có thể đã giải phóng một phần hoặc toàn bộ | Thiết kế xử lý lỗi/trạng thái theo API |
| Retry `close()` vô điều kiện khi thất bại | Có thể gây side effect hoặc đóng lặp | Chỉ retry nếu API cho phép |
| Tạo wrapper rồi tự đóng cả wrapper lẫn nguồn dù wrapper đã đóng nguồn | Có thể đóng trùng, đặc biệt với đối tượng không idempotent | Thỏa thuận ownership của các tầng |
| Chỉ đọc lỗi chính mà bỏ qua `getSuppressed()` | Mất thông tin lỗi đóng tài nguyên | Kiểm tra suppressed khi cần chẩn đoán |
| Dùng `boolean closed` không đồng bộ cho đối tượng đa luồng | Có thể race và giải phóng tài nguyên nhiều lần | Áp dụng đồng bộ/thiết kế thread-safe phù hợp |

**Điểm cần nhớ:** Mục tiêu của đóng tài nguyên là **giải phóng đúng và bảo vệ vòng đời**, không phải chỉ tăng bộ đếm hoặc đặt cờ. Với tài nguyên thật, kiểm tra tình huống đóng thành công, đóng thất bại giữa chừng, đóng lặp, dùng sau đóng và nhiều luồng nếu có.

## 12. Bài tập tự kiểm tra và đáp án

### Bài 1. Có phải `close()` chỉ được gọi một lần?

```java
Unguarded x = new Unguarded();
try (Unguarded a = x; Unguarded b = x) {
    System.out.println("work");
}
```

**Câu hỏi:** Cùng đối tượng `x` nhận bao nhiêu lời gọi `close()` khi rời khối, giả sử các bước không ném lỗi?

**Đáp án:** Hai. Java đóng **hai mục tài nguyên** `b` rồi `a`; cả hai tham chiếu tới cùng `x`. `try-with-resources` không tự loại bỏ tham chiếu trùng.

### Bài 2. So sánh hai giao diện

**Câu hỏi:** `AutoCloseable` có bắt buộc `close()` idempotent không? `Closeable` quy định thế nào khi đối tượng đã đóng?

**Đáp án:** `AutoCloseable` không bắt buộc idempotence, dù khuyến khích thiết kế như vậy. Hợp đồng `java.io.Closeable` yêu cầu gọi `close()` khi đối tượng đã ở trạng thái đóng không có tác dụng.

### Bài 3. Biến có sẵn sau `try`

```java
Guarded resource = new Guarded("X");
try (resource) {
    resource.use();
}
System.out.println(resource.isClosed());
```

**Câu hỏi:** Trên Java 17, đoạn này hợp lệ không và thông thường in gì với lớp `Guarded` của mục 6?

**Đáp án:** Hợp lệ vì `resource` là biến *effectively final* được phép dùng từ Java 9. `try` tự gọi `close()`, nên `resource.isClosed()` trả `true` và in `true`. Biến vẫn tồn tại nhưng tài nguyên đã đóng.

### Bài 4. Gọi `close()` mà phát sinh ngoại lệ

**Câu hỏi:** Nếu `close()` ném `IOException`, có thể kết luận tài nguyên hoàn toàn chưa đóng và cứ gọi `close()` lại cho đến khi hết lỗi không?

**Đáp án:** Không. `AutoCloseable` không quy định trạng thái sau lỗi đóng hoặc tính an toàn khi thử lại. Cần xem hợp đồng tài nguyên và lựa chọn chính sách xử lý lỗi có chủ đích.

### Bài 5. Dùng sau đóng

**Câu hỏi:** Vì sao `resource.close(); resource.use();` không nhất thiết ném cùng một ngoại lệ ở mọi lớp triển khai `AutoCloseable`?

**Đáp án:** Vì `AutoCloseable` không định nghĩa `use()`, `isClosed()` hoặc quy tắc chung cho mọi thao tác sau `close()`. Lớp `Guarded` tự chọn `IllegalStateException`; lớp khác có thể ném `IOException`, không cho phép thao tác hoặc có phương thức vẫn dùng được.

### Bài 6. Thân `try` và `close()` cùng thất bại

**Câu hỏi:** Với `try-with-resources`, thân `try` ném `IOException("work failed")`, rồi `close()` cũng ném `IOException("close failed")`. Lỗi nào là chính, và lỗi nào nằm trong suppressed?

**Đáp án:** `work failed` là ngoại lệ chính; `close failed` thường được gắn vào danh sách `getSuppressed()` của lỗi chính. `try-with-resources` không tự động thử gọi `close()` một lần khác.

## 13. Tóm tắt áp dụng trong Java hiện đại

- **Tách biệt ownership với khả năng đóng:** một đối tượng `AutoCloseable` có thể đóng được không có nghĩa mọi nơi giữ tham chiếu đều được phép đóng nó.
- **Hiểu đúng đóng một lần:** `try-with-resources` quản lý lời gọi `close()` cho **từng mục tài nguyên**; không bảo đảm một đối tượng sẽ không bị gọi lại ở nơi khác.
- **Không đánh đồng hai interface:** `AutoCloseable.close()` không bắt buộc idempotent; `Closeable.close()` có hợp đồng chặt hơn với đối tượng đã đóng.
- **Sau đóng phải theo hợp đồng cụ thể:** `AutoCloseable` không có `isClosed()`, không bảo đảm các phương thức tiếp tục được dùng, cũng không bắt buộc ném một loại lỗi duy nhất.
- **Lỗi đóng không xác định hoàn toàn trạng thái:** thiết kế chiến lược thất bại/retry theo tài nguyên; lưu ý suppressed exceptions và tránh đóng lại vô điều kiện.
- **Giữ thiết kế nhất quán:** ưu tiên `try-with-resources`, không đóng thủ công nếu không cần, không giao ownership cho nhiều chủ thể không phối hợp và kiểm thử trạng thái đóng trong ứng dụng.

Những nguyên tắc trên bắt nguồn từ hợp đồng `AutoCloseable` và `Closeable` cùng ngữ nghĩa `try-with-resources` được giới thiệu trong Java 7; chúng **vẫn áp dụng trong Java 17+ và các phiên bản Java hiện đại**.