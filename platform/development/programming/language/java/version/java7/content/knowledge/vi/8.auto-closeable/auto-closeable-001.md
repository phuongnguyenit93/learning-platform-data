# Thiết kế kiểu có vòng đời tài nguyên rõ ràng với AutoCloseable

**Chủ đề:** Java 7 — `AutoCloseable`  
**Bài học:** Thiết kế kiểu có vòng đời tài nguyên rõ ràng  
**Phạm vi thực hành:** Java 17+; trình bày các quy tắc và API **vẫn có giá trị hiện nay**, không sử dụng mẫu cleanup phụ thuộc finalizer hay công nghệ đã lỗi thời.

## 1. Tại sao cần thiết kế vòng đời, không chỉ gọi close()?

Một đối tượng Java thông thường có thể tồn tại cho đến khi bộ thu gom rác xử lý bộ nhớ. Nhưng một đối tượng quản lý **tài nguyên bên ngoài heap** có thể giữ file descriptor, socket, file channel, database cursor/connection, native handle hoặc một subscription. Những thứ này cần được giải phóng theo **hợp đồng xác định thời điểm**, thay vì chờ garbage collector.

`AutoCloseable` là giao diện nhỏ trong thư viện chuẩn:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Đoạn trên thể hiện **chữ ký API**, không phải một lớp chạy độc lập. Một kiểu triển khai `AutoCloseable` có thể sử dụng với `try-with-resources`, để JVM thực hiện logic `close()` do kiểu đó định nghĩa khi rời phạm vi `try`.

Nhưng việc implements `AutoCloseable` **chưa đủ để API có vòng đời rõ ràng**. Một thiết kế tốt còn phải trả lời:

1. **Ai tạo và ai sở hữu?** Resource do factory trả cho caller, do helper tự tạo hay chỉ là tham chiếu được mượn từ bên ngoài?
2. **Trạng thái nào cho phép thao tác?** Object có thể đang `OPEN`, `CLOSED` hoặc ở trạng thái lỗi sau khi đóng thất bại?
3. **Khi nào đóng?** Khi hoàn thành một scope, khi request kết thúc, khi transaction hoàn tất hay khi service shutdown?
4. **Đóng có được gọi lặp không?** Có cần idempotent không, và nếu `close()` ném lỗi thì object còn sử dụng được không?
5. **Có sở hữu resource phụ thuộc không?** Nếu object chứa nhiều tài nguyên, thứ tự giải phóng và cách giữ ngoại lệ ra sao?
6. **Hợp đồng nào được kiểm tra?** Làm sao test đường thành công, thất bại, đóng hai lần, dùng sau đóng, mở mới thất bại?

> Mục tiêu của bài này là **thiết kế một kiểu** dễ sử dụng đúng và khó dùng sai. `try-with-resources` là cơ chế đóng; *ownership* và *lifecycle contract* mới quyết định cơ chế đó được áp dụng ở đâu.

## 2. Các loại ownership thường gặp

| Quan hệ | Ai chịu trách nhiệm close? | Mẫu API |
| --- | --- | --- |
| **Owned** — method tự mở tài nguyên | Chính method, trừ khi chuyển giao rõ | `read(Path)` mở reader, dùng TWR, trả `String` |
| **Transferred** — factory trả đối tượng đang mở | Caller sau khi nhận thành công | `ReportSession.open(path)` trả `ReportSession implements AutoCloseable` |
| **Borrowed** — callee chỉ được mượn resource | Caller/owner ban đầu | `parse(Reader borrowed)` không đóng reader |
| **Shared/framework-owned** | Scope của framework, pool hoặc ứng dụng | Helper không tự ý đóng `System.in` hay connection của transaction bên ngoài |
| **Composite owner** — một object sở hữu nhiều handle | Object wrapper chịu trách nhiệm đóng các handle con | `ArchiveSession` sở hữu `InputStream` + `ZipFile`, đóng theo thứ tự phù hợp |

Java **không có cơ chế ownership/borrow checker ở cấp kiểu** giống một số ngôn ngữ khác. Vì vậy tài liệu API, scope, đóng gói field và test là yếu tố thiết yếu. Tên tham số như `borrowed`/`transferred` có thể giúp đọc code, nhưng **không thay** hợp đồng JavaDoc.

**Quy tắc:** người sở hữu kết thúc vòng đời; người mượn không tự ý đóng. Nếu phương thức nhận tham số `AutoCloseable`, điều đó **không mặc nhiên** cho phép phương thức gọi `close()` trên đối tượng của caller.

### 2.1. Một hướng API ít gây nhầm

- **Factory sở hữu việc khởi tạo:** `MySession.open(config)` mở resource và **trả ownership** cho caller.
- **Instance giữ các handle private:** không đưa những resource nội bộ có thể đóng ra ngoài nếu caller không được phép đóng chúng.
- **Operation có kiểm tra trạng thái:** `session.read()`/`session.write()` chỉ hoạt động khi session còn mở.
- **close() có hợp đồng rõ:** giải phóng tài nguyên, đặt đối tượng vào trạng thái không còn dùng được; mô tả liệu close lặp có vô hại và ngoại lệ nào có thể xuất hiện.
- **Scope caller điều khiển:** `try (MySession session = MySession.open(...)) { ... }` biểu thị rõ thời điểm kết thúc.

Thiết kế này thích hợp cho tài nguyên được dùng trong một scope ngắn. Với resource sống xuyên nhiều request, hãy quyết định **owner ở scope lớn hơn** (ví dụ application context) và không để một handler tùy tiện đóng shared instance.

## 3. Vòng đời tối thiểu: OPEN → CLOSED

Nhiều loại tài nguyên có thể mô hình hóa như sau:

```text
       tạo thành công
              |
              v
            OPEN  -- close() --> CLOSED
              |                   |
              | use()/read()      | use()/read()
              v                   v
         hoạt động hợp lệ       lỗi rõ ràng
```

Một số implementation có thể cần các trạng thái `NEW`, `OPENING`, `CLOSING`, `FAILED`, `CLOSED`, nhưng **đừng thêm state nếu không phục vụ hợp đồng thật**. Mục tiêu là các bất biến đơn giản:

- Ở `OPEN`, method nghiệp vụ có thể thực thi.
- Khi `close()` bắt đầu kết thúc ownership, method nghiệp vụ không được lặng lẽ tiếp tục dùng handle đã giải phóng.
- Sau `CLOSED`, các method cần resource phải **fail fast** bằng lỗi rõ ràng (thường `IllegalStateException`), trừ khi API công bố hành vi khác.
- Trạng thái closed không nên tự chuyển ngược về open trên **cùng đối tượng** nếu thiết kế không chủ đích hỗ trợ re-open; thông thường tạo phiên mới dễ hiểu hơn.
- Phải làm rõ khi `close()` **thất bại**: object có được phép dùng tiếp không? Với nhiều handle, an toàn hơn là coi object không còn khả dụng và truyền lỗi đóng cho caller, dù hệ thống có thể cần cơ chế cleanup/diagnostics riêng.

### 3.1. Ví dụ chạy được: một kiểu AutoCloseable có contract rõ

Lưu `LifecycleTypeDemo.java`:

```java
public class LifecycleTypeDemo {
    static final class ReportSession implements AutoCloseable {
        private final String name;
        private boolean closed;

        ReportSession(String name) {
            this.name = name;
            System.out.println("open:" + name);
        }

        void append(String text) {
            ensureOpen();
            System.out.println("append:" + name + ":" + text);
        }

        boolean isClosed() {
            return closed;
        }

        private void ensureOpen() {
            if (closed) {
                throw new IllegalStateException("session closed");
            }
        }

        @Override
        public void close() {
            if (closed) {
                return;
            }
            closed = true;
            System.out.println("close:" + name);
        }
    }

    public static void main(String[] args) {
        ReportSession session = new ReportSession("daily");

        try (session) {
            session.append("ready");
        }

        try {
            session.append("late");
        } catch (IllegalStateException ex) {
            System.out.println("rejected:" + ex.getMessage());
        }

        session.close();
        System.out.println("isClosed=" + session.isClosed());
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 LifecycleTypeDemo.java
java LifecycleTypeDemo
```

**stdout chính xác:**

```text
open:daily
append:daily:ready
close:daily
rejected:session closed
isClosed=true
```

**Phân tích thiết kế:**

1. `ReportSession implements AutoCloseable` thông báo rằng kiểu có điểm kết thúc vòng đời. `close()` ở đây không khai báo checked exception vì logic đóng minh họa không thể ném checked exception.
2. Field `closed` là `private`; caller không thể trực tiếp sửa trạng thái để bỏ qua việc kiểm tra. `ensureOpen()` được gọi từ operation cần tài nguyên.
3. `close()` chuyển sang terminal state và chỉ in `close:daily` **một lần**. Đây là **idempotence do tác giả class tự chọn**; giao diện `AutoCloseable` không bắt buộc mọi implementation idempotent.
4. `try (session)` dùng biến đã khai báo và effectively final, hỗ trợ từ **Java 9**. Dùng cú pháp Java 7 tương đương: `try (ReportSession session = new ReportSession("daily")) { ... }` nếu không cần tham chiếu bên ngoài.
5. Sau khi TWR đóng session, `append("late")` bị từ chối rõ ràng. Gọi `close()` thêm lần nữa không phát sinh hành động trong **implementation này**.

**Giới hạn:** Ví dụ chỉ dùng **một luồng**. `boolean closed` và việc gọi `ensureOpen()` ở đây **không bảo đảm thread-safety** nếu `append` và `close` được gọi đồng thời. Phần 11 giải thích cách đưa concurrency vào hợp đồng.

## 4. AutoCloseable so với Closeable

`java.io.Closeable` là subtype của `AutoCloseable`, dùng phổ biến trong I/O:

| Đặc điểm | `AutoCloseable` | `Closeable` |
| --- | --- | --- |
| Phương thức | `close() throws Exception` | `close() throws IOException` |
| Phạm vi | Nhiều loại tài nguyên cần cleanup | Chủ yếu các resource I/O |
| Checked exception | Interface cho phép `Exception`; implementation có thể khai báo hẹp hơn hoặc không khai báo | Hợp đồng đóng thiên về `IOException` |
| Close lặp | **Không bắt buộc** idempotent; nên thiết kế có thể gọi lặp an toàn khi hợp lý | Hợp đồng `Closeable.close()` mô tả gọi trên resource đã đóng không có hiệu lực |
| TWR | Có | Có, vì `Closeable extends AutoCloseable` |

**Chọn giao diện theo ngữ nghĩa:** một reader thực sự thực hiện I/O có thể triển khai `Closeable` để báo lỗi bằng `IOException`. Một session không nhất thiết gắn với I/O có thể triển khai `AutoCloseable` và thu hẹp chữ ký `close()` phù hợp.

Cú pháp `try-with-resources` nhận mọi kiểu implements `AutoCloseable`. Đừng bắt mọi `close()` ném `Exception` nếu implementation biết chính xác loại lỗi; chữ ký hẹp giúp caller dễ xử lý.

Ví dụ:

```java
final class LocalScope implements AutoCloseable {
    @Override
    public void close() {
        // Cleanup không phát sinh checked exception.
    }
}
```

Đoạn code này là **class minh họa**, không phải chương trình `main` độc lập. Nếu giữ biến theo kiểu cụ thể `LocalScope`, `close()` không yêu cầu catch checked exception. Nếu chỉ giữ tham chiếu theo kiểu `AutoCloseable`, chữ ký nhìn thấy từ giao diện vẫn là `throws Exception` và phần code gọi/TWR phải xử lý tương ứng.

## 5. Ownership qua ranh giới phương thức: borrowed và transferred

Một callee có thể dùng resource mà **không sở hữu** nó. Sự khác biệt không nằm ở kiểu Java, mà ở hợp đồng của phương thức.

Lưu `OwnershipApiDemo.java`:

```java
public class OwnershipApiDemo {
    static final class SampleSource implements AutoCloseable {
        private final String name;
        private final int[] values;
        private int cursor;
        private boolean closed;

        SampleSource(String name, int... values) {
            this.name = name;
            this.values = values;
            System.out.println("open:" + name);
        }

        int next() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            return values[cursor++];
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("close:" + name);
            }
        }
    }

    // Mượn: không đóng nguồn dữ liệu của caller.
    static int sumTwo(SampleSource borrowed) {
        return borrowed.next() + borrowed.next();
    }

    // Nhận chuyển quyền: phương thức được phép đóng resource.
    static int consumeOwned(SampleSource transferred) {
        try (transferred) {
            return transferred.next();
        }
    }

    public static void main(String[] args) {
        try (SampleSource caller =
                     new SampleSource("caller", 2, 3, 5)) {
            System.out.println("sum=" + sumTwo(caller));
            System.out.println("remaining=" + caller.next());
        }

        SampleSource passed = new SampleSource("passed", 7);
        System.out.println("consumed=" + consumeOwned(passed));

        try {
            passed.next();
        } catch (IllegalStateException ex) {
            System.out.println("after-transfer:" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 OwnershipApiDemo.java
java OwnershipApiDemo
```

```text
open:caller
sum=5
remaining=5
close:caller
open:passed
close:passed
consumed=7
after-transfer:closed
```

**Đọc đúng thiết kế:**

- `sumTwo` chỉ **mượn** `SampleSource`. Caller vẫn có thể đọc giá trị tiếp theo, và caller's TWR chịu trách nhiệm `close()`.
- `consumeOwned` nhận ownership **theo hợp đồng**, dùng `try (transferred)` và đóng trước khi trả giá trị. Sau lời gọi, caller không được coi `passed` là một resource còn mở.
- Khả năng biên dịch `try (transferred)` không xác nhận ownership đúng: nếu phương thức đặt tên `borrowed` nhưng vẫn dùng `try (borrowed)`, đó có thể là lỗi API nghiêm trọng.
- Vì đây là mẫu dạy học, ví dụ in log lúc mở/đóng. Code production nên dùng logging/metrics phù hợp và không làm lộ dữ liệu nhạy cảm khi log.

**Nên có JavaDoc ở API thật:**

```java
/**
 * Reads two values without taking ownership.
 * The caller remains responsible for closing the source.
 */
static int sumTwo(SampleSource borrowed) {
    return borrowed.next() + borrowed.next();
}
```

Snippet trên trình bày hợp đồng, không phải chương trình độc lập. Với một method **chuyển ownership**, cũng cần ghi rõ rằng callee sẽ đóng resource cả khi operation thành công lẫn thất bại.

## 6. Thiết kế factory: không để lộ resource mở dở

Một class bao nhiều handle có thể thất bại trong quá trình khởi tạo. Nếu đã mở handle A nhưng việc mở B ném exception, caller **chưa nhận được object wrapper**, nên không thể đóng A qua wrapper. Chính factory/constructor phải xử lý cleanup phần đã mở.

### 6.1. Factory an toàn với việc khởi tạo từng phần

Lưu `SafeFactoryDemo.java`:

```java
public class SafeFactoryDemo {
    static final class Handle implements AutoCloseable {
        private final String name;
        private boolean closed;

        Handle(String name) {
            this.name = name;
            System.out.println("open:" + name);
        }

        String name() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            return name;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("close:" + name);
            }
        }
    }

    static final class Pair implements AutoCloseable {
        private final Handle left;
        private final Handle right;
        private boolean closed;

        private Pair(Handle left, Handle right) {
            this.left = left;
            this.right = right;
        }

        static Pair open(boolean failSecond) {
            Handle left = new Handle("left");
            try {
                if (failSecond) {
                    System.out.println("attempt:right");
                    throw new IllegalStateException(
                            "cannot-open-right");
                }
                Handle right = new Handle("right");
                return new Pair(left, right);
            } catch (RuntimeException | Error ex) {
                left.close();
                throw ex;
            }
        }

        void work() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            System.out.println(
                    "use:" + left.name() + "+" + right.name());
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                right.close();
                left.close();
            }
        }
    }

    public static void main(String[] args) {
        try (Pair ok = Pair.open(false)) {
            ok.work();
        }

        try (Pair failing = Pair.open(true)) {
            failing.work();
        } catch (IllegalStateException ex) {
            System.out.println("caught:" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 SafeFactoryDemo.java
java SafeFactoryDemo
```

```text
open:left
open:right
use:left+right
close:right
close:left
open:left
attempt:right
close:left
caught:cannot-open-right
```

**Điều cần thấy:**

1. Ở đường thành công, `Pair` là **owner duy nhất** của hai handle. Caller đặt `Pair` vào TWR; `Pair.close()` đóng handle phụ thuộc `right` trước rồi tới `left`.
2. Ở đường thất bại, `right` chưa được cấp phát nên `Pair` không được tạo; `left` vẫn được đóng **ngay trong factory**.
3. `Pair` giữ constructor ở mức `private` để tránh caller bất cẩn tự tạo wrapper từ hai resource đang do nơi khác sở hữu.
4. `Pair.close()` ở ví dụ này gọi trực tiếp hai `Handle.close()` vì implementation `Handle` **không có đường ném exception**. Với resource thực tế có thể lỗi khi đóng, cần chiến lược cố đóng tất cả và bảo toàn lỗi theo phần 7; không sao chép lối gọi liên tiếp này vào class bao các `AutoCloseable` bất kỳ.

**Ranh giới lỗi trong factory:** nếu `left.close()` cũng có thể ném exception, không nên để lỗi cleanup che lỗi mở `right`. Có thể bắt lỗi cleanup, gắn vào nguyên nhân chính bằng `ex.addSuppressed(closeEx)` rồi ném lại nguyên nhân chính. Đối với API dùng checked exceptions, chữ ký factory phải khai báo/biến đổi đúng loại lỗi đó và bảo toàn cause.

## 7. Khi class sở hữu nhiều tài nguyên: close tất cả và giữ lỗi

Một loại AutoCloseable có thể chứa nhiều thành phần, mỗi thành phần đều có `close()` có khả năng lỗi. Nếu chỉ viết:

```java
first.close();
second.close();
```

và `first.close()` ném exception, `second.close()` **có thể không chạy**, gây rò rỉ. Vì vậy composite owner nên có một chính sách giải phóng **tất cả thành phần** và trả thông tin lỗi đầy đủ.

Một chiến lược hợp lý:

1. Chuyển object wrapper sang trạng thái **không được tiếp tục dùng**.
2. Đóng các thành phần theo thứ tự phụ thuộc ngược lại với lúc mở.
3. Lưu ngoại lệ đầu tiên làm **primary close exception**.
4. Các lỗi close tiếp theo thêm vào `primary.addSuppressed(...)`.
5. Ném lại primary sau khi đã thử đóng tất cả.
6. Không cho sử dụng lại object sau khi close dù close thất bại một phần.

### 7.1. Ví dụ chạy được: composite close và suppressed exception

Lưu `CompositeErrorsDemo.java`:

```java
import java.io.IOException;

public class CompositeErrorsDemo {
    static final class Fragile implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;
        private boolean closed;

        Fragile(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("open:" + name);
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            System.out.println("use:" + name);
        }

        @Override
        public void close() throws IOException {
            if (closed) {
                return;
            }
            closed = true;
            System.out.println("close:" + name);
            if (failOnClose) {
                throw new IOException("close-" + name);
            }
        }
    }

    static final class Owner implements AutoCloseable {
        private final Fragile first;
        private final Fragile second;
        private boolean closed;

        Owner(Fragile first, Fragile second) {
            this.first = first;
            this.second = second;
        }

        void work() {
            if (closed) {
                throw new IllegalStateException("owner closed");
            }
            first.use();
            second.use();
        }

        @Override
        public void close() throws IOException {
            if (closed) {
                return;
            }
            closed = true;

            IOException primary = null;
            try {
                second.close();
            } catch (IOException ex) {
                primary = ex;
            }
            try {
                first.close();
            } catch (IOException ex) {
                if (primary == null) {
                    primary = ex;
                } else {
                    primary.addSuppressed(ex);
                }
            }
            if (primary != null) {
                throw primary;
            }
        }
    }

    public static void main(String[] args) {
        try (Owner owner = new Owner(
                new Fragile("one", true),
                new Fragile("two", true))) {
            owner.work();
        } catch (IOException ex) {
            System.out.println("primary:" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println(
                        "suppressed:" + suppressed.getMessage());
            }
        }

        try (Fragile resource = new Fragile(
                "body-resource", true)) {
            resource.use();
            throw new IllegalStateException("body-failed");
        } catch (Exception ex) {
            System.out.println(
                    "body-primary:" + ex.getMessage());
            System.out.println(
                    "body-suppressed:" + ex.getSuppressed().length);
        }
    }
}
```

```bash
javac -encoding UTF-8 CompositeErrorsDemo.java
java CompositeErrorsDemo
```

```text
open:one
open:two
use:one
use:two
close:two
close:one
primary:close-two
suppressed:close-one
open:body-resource
use:body-resource
close:body-resource
body-primary:body-failed
body-suppressed:1
```

**Có hai tầng xử lý lỗi khác nhau:**

- `Owner.close()` chủ động tổng hợp lỗi khi đóng các thành phần mà **Owner sở hữu**. Nếu `second.close()` ném lỗi, nó vẫn thử `first.close()`, lưu lỗi thứ hai dưới dạng suppressed. Đây là logic mà **tác giả class** phải viết vì `AutoCloseable` không tự dọn tất cả field của một object.
- `try (Owner owner = ...)` tự gọi **một** lần `owner.close()` khi rời scope. Nếu close đó ném exception, caller nhận được exception do `Owner` xây dựng.
- Ở block thứ hai, thân try ném `IllegalStateException("body-failed")` và `Fragile.close()` cũng ném `IOException`. TWR đặt **lỗi body** làm primary, lỗi close làm suppressed; không làm mất nguyên nhân đầu tiên.

**Lưu ý về exception contract:** `Owner.close()` trong ví dụ chỉ bắt `IOException` vì cả hai field là `Fragile`, mà `Fragile.close()` đã thu hẹp chữ ký thành `throws IOException`. Nếu field chỉ có kiểu tổng quát `AutoCloseable`, compiler phải tính đến `throws Exception` và có thể có unchecked `RuntimeException`/`Error`. Thiết kế production cần quyết định chính sách cho **cả những loại lỗi đó**, không sao chép cơ học `catch (IOException)` sang mọi composite resource.

**Một giới hạn khác:** ví dụ tạo hai `Fragile` qua constructor không ném exception nên không có bước khởi tạo dở. Nếu thay bằng factory mở tệp/network có thể thất bại giữa chừng, cần kết hợp với kỹ thuật dọn phần mở dở ở phần 6.

## 8. Ví dụ thực tế: kiểu đọc file có owner rõ ràng

Một API tốt có thể đóng gói `BufferedReader` thành một class nhỏ cung cấp method nghiệp vụ, nhưng **không cho caller truy cập trực tiếp handle bên dưới để tự ý đóng**. Factory nhận `Path`, mở reader, chuyển quyền đóng cho object; caller sử dụng TWR trên object này.

Lưu `FileReaderTypeDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileReaderTypeDemo {
    static final class Lines implements AutoCloseable {
        private final BufferedReader reader;
        private boolean closed;

        private Lines(BufferedReader reader) {
            this.reader = reader;
        }

        static Lines open(Path path) throws IOException {
            return new Lines(Files.newBufferedReader(
                    path, StandardCharsets.UTF_8));
        }

        String next() throws IOException {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            return reader.readLine();
        }

        @Override
        public void close() throws IOException {
            if (!closed) {
                closed = true;
                reader.close();
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile(
                "auto-closeable-demo-", ".txt");
        try {
            Files.writeString(
                    path, "alpha\nbeta\n",
                    StandardCharsets.UTF_8);

            Lines lines = Lines.open(path);
            try (lines) {
                System.out.println(lines.next());
                System.out.println(lines.next());
            }

            try {
                lines.next();
            } catch (IllegalStateException ex) {
                System.out.println(
                        "rejected:" + ex.getMessage());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac -encoding UTF-8 FileReaderTypeDemo.java
java FileReaderTypeDemo
```

```text
alpha
beta
rejected:closed
```

Ở đây `Lines.open(path)` trả một object có trách nhiệm đóng reader. Caller dùng TWR trên `Lines`; khi thoát scope, `Lines.close()` đóng `BufferedReader`. Cố gọi `next()` sau đó bị từ chối **trước khi truy cập handle đã đóng**.

- `reader` là field `private final`: caller không có quyền thay thế reader hay gọi `close()` lên nó trực tiếp.
- `closed` được đánh dấu **trước khi** gọi `reader.close()`: sau khi thử đóng, object không cho phép thao tác đọc lại, ngay cả nếu close ném lỗi.
- `Files.newBufferedReader` khai báo lỗi `IOException`; do đó `Lines.open` báo đúng loại lỗi mở.
- `Lines.close() throws IOException` thu hẹp exception contract phù hợp với `BufferedReader`.
- File được tạo bằng `Files.createTempFile` và xóa bằng `Files.deleteIfExists` trong `finally`, **ngoài** resource scope của reader; file temp chỉ để minh họa thử nghiệm.

Trong trường hợp áp dụng thật, có thể **đọc toàn bộ hoặc vật hóa kết quả** rồi trả về immutable data thay vì trả một resource object cho caller, nếu API chỉ thực hiện một truy vấn ngắn. Không nhất thiết phải viết wrapper AutoCloseable cho mọi tác vụ; dùng thư viện chuẩn với TWR trực tiếp có thể đơn giản hơn.

## 9. Thiết kế API theo owner, không theo thói quen

So sánh các chữ ký:

| Chữ ký | Ai đóng? | Điều nên ghi trong hợp đồng |
| --- | --- | --- |
| `List<String> load(Path path)` | Method, vì tự mở tài nguyên bên trong | Khi method trả về, tài nguyên đã đóng; kết quả độc lập với handle |
| `Lines open(Path path)` | Caller | Caller nhận ownership của `Lines`; phải đóng bằng TWR |
| `void process(InputStream borrowed)` | Caller | Method chỉ sử dụng, không đóng; không giữ tham chiếu sau khi return trừ khi hợp đồng cho phép |
| `Result consume(InputStream transferred)` | Callee | Caller giao quyền đóng; method sẽ đóng cả khi thành công lẫn thất bại |
| `void withConnection(Connection supplied)` | Tùy chủ sở hữu transaction | Nếu framework/caller quản lý connection, method không được đóng hoặc commit tùy tiện |

**Các mối quan hệ không thể suy luận an toàn chỉ từ chữ ký Java**. Hãy dùng tên, JavaDoc và test. Với JDBC, một lần `Connection.close()` ở kết nối lấy từ pool thường **trả connection về pool** theo hợp đồng pool, không có nghĩa đóng toàn bộ pool; transaction commit/rollback vẫn là trách nhiệm riêng.

Với standard streams như `System.in`/`System.out`, helper không nên đóng nguồn dùng chung chỉ vì chúng implements các interface có `close()`. Cũng phải chú ý wrapper như `BufferedReader` thường **đóng luôn stream/reader bên dưới** khi wrapper bị đóng. Nếu underlying là tài nguyên mượn, việc đóng wrapper có thể vi phạm ownership.

### 9.1. Khi nào không cần tự tạo AutoCloseable?

Không phải mọi kiểu đều cần lifecycle:

- DTO/record immutable chỉ chứa dữ liệu đã vật hóa thường **không cần** `AutoCloseable`.
- `StringReader` hoặc stream thuần trong bộ nhớ có thể có `close()` nhưng việc giải phóng handle OS không phải lúc nào cũng là lý do sử dụng; ownership vẫn phải rõ.
- `Stream.of(...)`/`collection.stream()` thường không giữ tài nguyên hệ thống. Trong khi `Files.lines(path)` có file-backed resource, cần close stream khi hoàn tất.
- Factory cho thao tác một lần thường có thể trả kết quả cuối cùng thay vì cấp quyền sở hữu handle cho caller.

**Không làm API phức tạp hơn mức cần thiết.** Tạo kiểu custom AutoCloseable khi thực sự cần biểu diễn một session/lease/vòng đời và ràng buộc các thao tác vào scope đó.

## 10. Các lỗi thiết kế cần tránh

### 10.1. Trả tài nguyên từ scope đã đóng

```java
// Sai về vòng đời; đoạn minh họa, không phải hàm runnable độc lập:
// static Lines openWrong(Path path) throws IOException {
//     try (Lines result = Lines.open(path)) {
//         return result; // caller nhận object đã bị đóng!
//     }
// }
```

Nếu factory chuyển ownership, factory **không** tự đóng resource trước khi caller nhận. Hãy trả `Lines.open(path)` trực tiếp và ghi rõ nghĩa vụ đóng của caller.

### 10.2. Để lộ handle private và hai bên cùng nghĩ mình là owner

`getReader()` trả reader nội bộ cho caller rồi cả wrapper và caller cùng có thể đóng reader là dấu hiệu ownership mơ hồ. Cân nhắc chỉ expose thao tác nghiệp vụ trên wrapper, hoặc tài liệu hóa rõ trả **borrowed view**/chuyển ownership. Đừng giả định gọi close nhiều lần là an toàn.

### 10.3. Dựa vào finalize hoặc garbage collector để đóng

Không thiết kế tài nguyên mới bằng cách hy vọng `finalize()` được gọi. Finalization đã bị **deprecated for removal** và không bảo đảm cleanup đúng thời điểm. Cleaner, nếu dùng như lớp phòng vệ cuối, **không thay thế** explicit close và không mang ý nghĩa close ngay khi kết thúc nghiệp vụ.

Cách chuẩn cho resource sở hữu theo scope vẫn là `try-with-resources`.

### 10.4. Nuốt lỗi close hoặc che lỗi nghiệp vụ

Nếu body và cleanup cùng thất bại, không thay thế nguyên nhân gốc bằng một lỗi close mới không giữ cause. TWR tự gắn suppressed. Khi tự viết `close()` composite, cần tổng hợp các lỗi và bảo đảm resource tiếp theo vẫn được thử đóng. Nếu exception được ghi log, đừng chỉ ghi mỗi `getMessage()` mà bỏ stack trace, cause, suppressed.

### 10.5. Đóng trong helper chỉ vì kiểu implements AutoCloseable

Một helper chỉ **mượn** `Reader`/`Connection`/`InputStream` không được tạo `try (borrowed)` nếu không có quyền đóng. Cú pháp Java có thể hợp lệ nhưng hợp đồng API sai. Tương tự, đóng underlying resource từ wrapper có thể gián tiếp đóng tài nguyên mượn.

### 10.6. Cho thao tác sử dụng resource sau close mà không có chính sách

Nếu phần lớn operation dựa vào handle đã đóng, hãy kiểm tra `OPEN` trước khi thao tác và ném exception rõ. Đừng để lỗi mơ hồ từ lớp thấp xuất hiện rất xa nơi object bị đóng. Một số method truy vấn metadata như `isClosed()` có thể vẫn dùng sau close, miễn hợp đồng xác định rõ.

### 10.7. Giả định close đồng nghĩa commit/durability

`close()` không tự bảo đảm database transaction được commit, dữ liệu đã fsync bền vững hoặc network peer đã nhận payload. Đừng gộp cleanup với chính sách giao dịch mà không mô tả rõ. Nếu có commit/rollback, hãy tách chức năng và kiểm thử mọi đường lỗi.

## 11. Concurrency: use() và close() có thể chạy đồng thời không?

Các ví dụ ở trên cố ý **single-threaded**. Với class chia sẻ nhiều luồng, đây là một quyết định API cần công bố:

- **Thread-confined:** một instance chỉ được dùng từ một thread/scope; đơn giản, thường phù hợp cho file reader hoặc session ngắn.
- **Externally synchronized:** caller phải bảo đảm không gọi operation và `close()` đồng thời.
- **Internally synchronized:** object tự khóa quanh cả operation và close, bảo đảm một call đang xử lý không bị đóng handle giữa chừng.
- **Asynchronous close/cancellation:** cần contract riêng về các operation đang chạy, thời hạn chờ, khả năng hủy, việc đánh thức waiter và outcome của close.

Ví dụ *minh họa* nếu một `Session` cần bảo đảm `read` và `close` không chạy xen kẽ:

```java
// Các method này nằm trong cùng class quản lý handle.
// Không phải chương trình độc lập.
public synchronized String read() throws java.io.IOException {
    ensureOpen();
    return reader.readLine();
}

@Override
public synchronized void close() throws java.io.IOException {
    if (!closed) {
        closed = true;
        reader.close();
    }
}
```

Khóa chung quanh **toàn bộ thao tác** (chứ không chỉ field `closed`) giúp tránh tình huống thread A vừa kiểm tra `!closed` thì thread B đóng reader trước khi A đọc. Nhưng synchronization có thể ảnh hưởng throughput hoặc chặn caller lâu khi I/O bị treo; chọn chiến lược theo yêu cầu thực tế. **Chỉ thêm `volatile boolean` hoặc `AtomicBoolean` cho trạng thái không tự động bảo vệ một operation dài chống close đồng thời.**

Với tài nguyên mà framework quản lý concurrency, nên đi theo contract framework thay vì áp một khóa tùy tiện.

## 12. Test lifecycle như một hợp đồng

Một lớp AutoCloseable nên được kiểm thử theo *state transition* và các đường exception, không chỉ theo kết quả nghiệp vụ:

| Test | Thiết lập | Kết quả mong muốn |
| --- | --- | --- |
| Mở thành công | Factory tạo resource | Trạng thái OPEN, operation hợp lệ |
| Đóng bình thường | Thoát TWR | close được thực hiện, handle giải phóng, trạng thái CLOSED |
| Dùng sau đóng | Gọi operation sau TWR | Lỗi rõ ràng, thường `IllegalStateException` |
| Đóng lặp | Gọi `close()` lần hai | Theo hợp đồng implementation; nếu tự chọn idempotent thì không có tác dụng phụ lặp |
| Body ném exception | Operation thất bại giữa chừng | TWR vẫn gọi close; nguyên nhân body được bảo toàn |
| Close ném exception | Handle báo lỗi cleanup | Exception lan truyền theo chữ ký; caller quan sát được |
| Body + close cùng lỗi | Hai nguồn lỗi đồng thời | Lỗi body primary, lỗi close suppressed |
| Mở resource thứ hai thất bại | Factory đã mở resource thứ nhất | Resource thứ nhất được đóng, không rò rỉ |
| Nhiều thành phần lỗi lúc đóng | Composite owner có hai close ném lỗi | Vẫn thử đóng cả hai, primary/suppressed được giữ |
| Borrowed input | Caller truyền resource vào helper mượn | Helper không đóng, caller tiếp tục dùng được |
| Ownership transfer | Callee nhận toàn quyền | Caller không dùng lại, callee đóng chính xác theo contract |
| Close concurrent với operation | Có hai thread | Hành vi phù hợp với thread-safety contract công bố |

Trong test tự động, có thể dùng fake resource ghi lại số lần `close()` và thứ tự event, ví dụ một danh sách event; khi cần, cho fake ném `IOException` chủ động để kiểm tra suppressed exception. Không phụ thuộc vào GC hoặc chờ timeout để “đoán” tài nguyên đã đóng.

**Đo resource leak trong môi trường thật:** ngoài unit test, quan sát số lượng file descriptor, active connections, open cursors, heap/OS metrics và timeout dưới tải. Những chỉ số này hỗ trợ kiểm chứng vòng đời nhưng không thay thế contract ở cấp mã nguồn.

## 13. Hướng dẫn viết JavaDoc cho kiểu AutoCloseable

Đối với một class xử lý file hoặc session, JavaDoc nên cho người dùng biết:

```java
/**
 * A single-owner reader session.
 *
 * <p>The caller owns each session returned by open(Path) and
 * must close it, preferably with try-with-resources.
 * Operations other than isClosed() are invalid after close().
 * close() may throw IOException and does not reopen the session.
 *
 * <p>Instances are not thread-safe; do not call read()
 * concurrently with close().
 */
```

Đoạn này là **JavaDoc minh họa**, không phải file Java độc lập. Nêu rõ *owner*, *lifecycle*, *exception*, *thread-safety*. Nếu class có chính sách close idempotent hoặc close lỗi vẫn khiến object terminal, ghi thêm vào JavaDoc.

Tránh những thông báo quá chung như “Caller should manage resources appropriately”. Hợp đồng tốt phải trả lời trực tiếp: **bên nào đóng, khi nào phải đóng, sau đó còn làm được gì, close thất bại có nghĩa gì**.

## 14. Bài tập

**Bài 1 — Đọc state machine:** Chạy `LifecycleTypeDemo`. Chỉ ra thời điểm state chuyển sang CLOSED; giải thích vì sao gọi `append` sau TWR bị chặn nhưng `isClosed()` vẫn dùng được. Thử bỏ `ensureOpen()` và nêu nguy cơ.

**Bài 2 — Ownership:** Chạy `OwnershipApiDemo`. Vẽ trách nhiệm caller/callee cho `sumTwo` và `consumeOwned`. Thử thêm TWR trong `sumTwo` rồi quan sát code còn quyền đọc phần tử thứ ba không.

**Bài 3 — Lỗi khởi tạo:** Chạy `SafeFactoryDemo`. Thử làm `Pair.open` thất bại khi mở handle đầu tiên và khi mở handle thứ hai. Xác định ai có thể đóng những handle đã khởi tạo thành công.

**Bài 4 — Lỗi đóng:** Chạy `CompositeErrorsDemo`. Vì sao `Owner.close()` vẫn đóng `first` dù `second.close()` ném exception? Lỗi nào primary và lỗi nào suppressed? So sánh với body exception do TWR xử lý.

**Bài 5 — Kiểu đọc file:** Chạy `FileReaderTypeDemo`. Đổi `Lines.next()` để trả `Optional<String>` nếu muốn API tách rõ EOF và “không có dòng”. Giữ nguyên contract close, và kiểm tra đường dùng sau close.

**Bài 6 — Tài liệu API:** Viết JavaDoc cho phương thức nhận `InputStream borrowed` và factory `openOwned(Path)`. Mô tả rõ ownership, scope, exception và có hỗ trợ concurrent use/close hay không.

**Bài 7 — Test:** Tạo fake AutoCloseable ghi đếm `closeCount`. Viết kiểm thử xác nhận đúng một lần đóng theo contract class, lỗi khi dùng sau close, và thứ tự đóng ngược đối với hai resource.

## 15. Checklist cuối cùng

- Kiểu **chỉ implements AutoCloseable khi thực sự có tài nguyên/lifecycle** cần đóng theo scope.
- Factory/open method phải rõ người nhận ownership; borrowed resource **không bị helper đóng**.
- Tài nguyên nội bộ nên được **đóng gói private**; operation kiểm tra OPEN và fail fast sau CLOSED.
- `close()` giải phóng tài nguyên thuộc sở hữu, theo thứ tự phụ thuộc phù hợp và **bảo toàn lỗi** khi nhiều thành phần cùng thất bại.
- Gọi close lặp có an toàn không là **hợp đồng của implementation**; đừng mặc định `AutoCloseable` bảo đảm idempotence.
- Khi mở nhiều resource, **dọn phần đã mở nếu bước sau thất bại**, ngay trong factory trước khi trả object.
- Dùng TWR của caller với resource được chuyển ownership, tránh trả resource từ TWR đã đóng.
- Chữ ký `close()` nên thu hẹp exception nếu có thể; `Closeable` phù hợp với resource I/O.
- Thread safety của `use` và `close` phải được xác định; kiểm tra field đóng không đủ bảo vệ tác vụ đang chạy.
- Không dựa vào `finalize()`, garbage collector, close trùng lặp hoặc niềm tin “close tương đương commit” để thay lifecycle rõ ràng.

## Tài liệu chính thức

- [AutoCloseable — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html): chữ ký `close()`, idempotence và TWR.
- [Closeable — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Closeable.html): hợp đồng cho resource I/O.
- [JLS `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): cách gọi close và suppressed exceptions.
- [Files — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): mở reader, xử lý Path và tài nguyên file.
