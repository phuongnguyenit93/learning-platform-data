# Java 7 — AutoCloseable: Quản lý tài nguyên được tạo, được mượn hoặc được chia sẻ

## Mục tiêu và bối cảnh

Một đối tượng triển khai `AutoCloseable` cung cấp phương thức `close()` để kết thúc việc sử dụng tài nguyên. Từ Java 7, câu lệnh **try-with-resources** (`try (...) { ... }`) giúp đóng tài nguyên đã được quản lý trong phạm vi `try` khi rời phạm vi đó, kể cả khi công việc ném ngoại lệ. Đây vẫn là cơ chế quan trọng trong Java 17+ và các JDK hiện đại.

Nhưng có một câu hỏi **quan trọng hơn cú pháp**: **Ai sở hữu quyền và trách nhiệm đóng đối tượng này?** Cùng một đối tượng `AutoCloseable` có thể được:

1. **Tạo và sở hữu tại đây (owned):** hàm/khối mở nó và chịu trách nhiệm đóng khi hoàn thành.
2. **Mượn từ caller (borrowed):** hàm chỉ được sử dụng tạm; chủ sở hữu ở bên ngoài quyết định thời điểm đóng.
3. **Chia sẻ giữa nhiều consumer (shared):** nhiều thành phần dùng cùng resource; một owner ở cấp vòng đời phù hợp quản lý mở/đóng để không cắt ngang các consumer.
4. **Chuyển giao ownership:** factory tạo tài nguyên nhưng giao trách nhiệm đóng cho caller khi trả về.

**Tính chất cốt lõi:** `AutoCloseable` cho biết một đối tượng *có thể được đóng*, nhưng **không tự xác định ai phải đóng**. Java không có bộ kiểm tra ownership tuyến tính ở cấp kiểu để chặn mọi trường hợp đóng sớm; người thiết kế API cần quy ước rõ, kiểm thử và quản lý vòng đời.

Bài này giúp bạn nhận diện ranh giới ownership, chọn vị trí `try-with-resources`, xử lý lỗi khi `close()` thất bại, tránh double-close hoặc premature-close, nhận biết ảnh hưởng của wrapper stream và thiết kế hợp đồng cấp method/factory. Các ví dụ độc lập bên dưới dùng **JDK 17+** (`javac --release 17`), kiến thức chỉ gồm các cơ chế hiện vẫn được hỗ trợ.

## 1. AutoCloseable và phạm vi của try-with-resources

Giao diện `java.lang.AutoCloseable` khai báo một phương thức `close()`; lớp triển khai quyết định cách giải phóng tài nguyên. Cú pháp thông dụng:

```java
try (SomeResource resource = openResource()) {
    use(resource);
}
```

Đoạn này là **minh họa**, cần định nghĩa `SomeResource` và các hàm `openResource`/`use`. Về ý nghĩa:

- Resource được khởi tạo trước khi chạy thân `try`.
- Nếu khởi tạo thành công, Java gọi `close()` khi kết thúc phạm vi, dù thân `try` kết thúc bình thường, `return` hay ném ngoại lệ.
- Nếu nhiều resource được khai báo, Java đóng theo **thứ tự ngược** thứ tự khai báo/khởi tạo thành công.
- `close()` có thể ném ngoại lệ. Nếu cả thân `try` và `close()` cùng lỗi, lỗi thân thường là **primary**, lỗi đóng được giữ trong `getSuppressed()` của primary.
- Nếu phần xử lý thành công nhưng `close()` lỗi, lỗi đóng có thể trở thành exception chính mà caller nhận, thay cho một lần hoàn tất bình thường.

Khi dùng Java hiện đại, cũng có thể đưa một biến resource đã được khai báo trước vào header nếu nó là `final` hoặc **effectively final**:

```java
SomeResource resource = openResource();
try (resource) {
    use(resource);
}
```

Đây là **mã minh họa**. Cú pháp reuse biến trong header `try (resource)` được hỗ trợ từ **Java 9**, không phải cú pháp ban đầu của Java 7. Nó vẫn **đóng đối tượng** khi rời khối `try`. Biến được khai báo trước hay khai báo ngay trong dấu ngoặc không làm đổi quy tắc ownership: **đưa resource vào header tức là nhận trách nhiệm đóng nó tại ranh giới đó**, dù đối tượng được mở ở chỗ khác.

### 1.1. AutoCloseable, Closeable và ngoại lệ của close

- `AutoCloseable.close()` trong giao diện gốc có thể khai báo `throws Exception`.
- `java.io.Closeable` mở rộng `AutoCloseable`, với `close()` khai báo `throws IOException`; hợp đồng của `Closeable` còn có quy định riêng về việc đóng lặp.
- Lớp cụ thể thường thu hẹp exception trong phương thức override hoặc không ném checked exception.
- **Kiểu tĩnh của biến resource quan trọng đối với checked-exception analysis.** Nếu khai báo biến là `AutoCloseable`, compiler có thể yêu cầu xử lý `Exception` theo chữ ký giao diện, trong khi khai báo với kiểu lớp cụ thể có `close()` không `throws` có thể không yêu cầu.
- Không suy ra rằng mọi `close()` đều vô hại nếu gọi hai lần: hợp đồng `AutoCloseable` tổng quát **không yêu cầu idempotent**. Điều đó khác với các lớp/giao diện cụ thể có hợp đồng mạnh hơn.

```java
// Hai ví dụ định hướng; cần lớp và method tương ứng.
try (MyConnection connection = openConnection()) {
    connection.send();
}

// Nếu chỉ biết kiểu tĩnh AutoCloseable, close() có thể khai báo Exception.
try (AutoCloseable resource = acquireGeneric()) {
    doWork();
}
```

Đoạn trên không phải lớp chạy độc lập. Khi viết mã thật, cần xét loại `close()`, ngoại lệ có thể phát sinh từ tạo/sử dụng/đóng tài nguyên và quy ước xử lý của caller.

## 2. Bảng quyết định ownership

| Trường hợp | Ai tạo đối tượng? | Ai được đóng? | Khi nào đóng? | Cách diễn đạt |
| --- | --- | --- | --- | --- |
| **Owned tại một method** | Method hiện tại | Method hiện tại | Sau công việc hoàn tất hoặc thất bại | `try (R r = create()) { ... }` |
| **Borrowed** | Caller hoặc scope cao hơn | Owner bên ngoài | Theo vòng đời của owner | Callee dùng resource, **không** thêm nó vào try-with-resources |
| **Shared** | Application manager/pool/container | Một thành phần được chỉ định quản lý lifecycle | Sau khi mọi consumer ngừng sử dụng | Consumer chỉ mượn; owner đóng tại shutdown/scope end |
| **Transferred** | Factory | Caller sau khi factory trả về thành công | Khi caller không còn cần | Factory trả `R`, caller `try (R r = factory())` |
| **Wrapper sở hữu underlying** | Có thể khác nơi tạo underlying | Theo hợp đồng wrapper và source | Khi wrapper đóng | Xác minh `wrapper.close()` có đóng underlying không |
| **Resource do framework quản lý** | Framework/container | Framework/container, theo contract | Theo request/session/app scope đã định nghĩa | Không tự đóng khi framework chưa trao quyền |
| **Resource từ pool** | Pool | Thường người mượn gọi close để trả lease **nếu contract quy định** | Kết thúc lease | Đọc contract vì “close” có thể là trả về pool, không phải hủy kết nối vật lý |

Điểm cuối rất quan trọng: không suy diễn theo tên `close` rằng nó luôn hủy resource vật lý. Ví dụ proxy/lease của connection pool có thể biến `close()` thành hành động **trả kết nối về pool**. Điều này phụ thuộc thư viện, phải xem tài liệu cụ thể.

**Một nguyên tắc hữu ích:** Chỉ có **một authority chịu trách nhiệm quyết định thời điểm kết thúc vòng đời**, dù có thể có nhiều người dùng. Nếu chuyển quyền, xác định rõ thời điểm chuyển và ai đóng khi xảy ra ngoại lệ giữa chừng.

## 3. Phần A — Resource do method tạo và sở hữu

Nếu method mở một phiên làm việc chỉ dùng trong chính method ấy, try-with-resources đặt gần điểm mở là cách rõ ràng nhất để bảo đảm đóng trên cả đường thành công và lỗi.

### Chương trình hoàn chỉnh: `OwnedResourceDemo.java`

```java
import java.io.IOException;

public final class OwnedResourceDemo {
    private static final class Session implements AutoCloseable {
        private final String name;
        private boolean closed;

        Session(String name) {
            this.name = name;
            System.out.println(name + ":open");
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("session closed");
            }
            System.out.println(name + ":use");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println(name + ":close");
            }
        }
    }

    private static void run(String name, boolean fail) throws IOException {
        try (Session session = new Session(name)) {
            session.use();
            if (fail) {
                throw new IOException("work failed");
            }
            System.out.println(name + ":done");
        }
    }

    public static void main(String[] args) {
        for (boolean fail : new boolean[]{false, true}) {
            String name = fail ? "failure" : "success";
            try {
                run(name, fail);
            } catch (IOException e) {
                System.out.println("caller:" + e.getMessage());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 OwnedResourceDemo.java
java OwnedResourceDemo
```

Output đã kiểm chứng:

```text
success:open
success:use
success:done
success:close
failure:open
failure:use
failure:close
caller:work failed
```

### Phân tích ownership và đường đi lỗi

- `run` là **owner**: nó trực tiếp tạo `new Session(name)` và giữ session trong phạm vi khối `try`.
- Đường thành công: session mở, sử dụng, in `done`, rồi `close` trước khi caller tiếp tục.
- Đường lỗi: sau khi `use`, thân `try` ném `IOException`; Java vẫn gọi `close`, rồi ngoại lệ lan lên caller.
- Caller không được trao session để dùng sau khi `run` kết thúc, nên vòng đời đã được đóng gọn trong method.
- `Session.close()` trong ví dụ có một guard `closed` để tránh in lần thứ hai; đây là **hành vi do chúng ta tự thiết kế**, không phải tính chất mà `AutoCloseable` bắt buộc mọi implementation phải có.
- Resource ở đây không chứa kết nối thật. `IOException` được ném có chủ ý để kiểm thử nhánh lỗi, không phải vì `Session` nhất thiết là I/O resource.

### Quy tắc áp dụng

Khi bạn tạo resource tại đây và không trả/giao nó cho người khác, **ưu tiên scope nhỏ, rõ**:

```java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    String firstLine = reader.readLine();
    // Xử lý dữ liệu khi reader còn mở.
}
```

Đây là **mảnh minh họa** cần import `BufferedReader`, `Files`, biến `Path path` và xử lý `IOException`. Sau khi ra khỏi `try`, `reader` đã được đóng. Không giữ tham chiếu reader trong một callback hoặc trả về reader để caller dùng nếu nó đã bị đóng ngay tại method.

## 4. Phần B — Resource được mượn: callee không sở hữu quyền đóng

Giả sử caller sở hữu một handle và truyền vào hai hàm xử lý. Mỗi hàm chỉ mượn nó để làm việc. Nếu một hàm tự đặt handle vào try-with-resources, nó đã **đóng resource của caller**; lần dùng kế tiếp có thể thất bại.

Đây là lỗi ownership **hợp lệ về cú pháp Java**: compiler không biết phương thức `wrongBorrow` có được phép đóng hay không. Vì vậy test vòng đời rất cần thiết.

### Chương trình hoàn chỉnh: `BorrowedResourceDemo.java`

```java
public final class BorrowedResourceDemo {
    private static final class Handle implements AutoCloseable {
        private boolean closed;
        private int closeCount;

        void use(String who) {
            if (closed) {
                throw new IllegalStateException("handle already closed");
            }
            System.out.println(who + ":use");
        }

        int closeCount() {
            return closeCount;
        }

        @Override
        public void close() {
            closeCount++;
            closed = true;
            System.out.println("handle:close");
        }
    }

    private static void borrow(Handle handle, String who) {
        handle.use(who);
    }

    private static void wrongBorrow(Handle handle) {
        try (Handle mistakenlyOwned = handle) {
            mistakenlyOwned.use("wrong");
        }
    }

    public static void main(String[] args) {
        Handle good = new Handle();
        try (Handle owner = good) {
            borrow(good, "first");
            borrow(good, "second");
            System.out.println("insideCloseCount=" + good.closeCount());
        }
        System.out.println("afterCloseCount=" + good.closeCount());

        Handle bad = new Handle();
        wrongBorrow(bad);
        try {
            borrow(bad, "afterWrongBorrow");
        } catch (IllegalStateException e) {
            System.out.println("caught=" + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BorrowedResourceDemo.java
java BorrowedResourceDemo
```

Output:

```text
first:use
second:use
insideCloseCount=0
handle:close
afterCloseCount=1
wrong:use
handle:close
caught=handle already closed
```

### Đọc đúng kết quả

**Nhánh đúng:**

1. `main` là owner, tạo `Handle good`.
2. `borrow` chỉ gọi `use`, **không** đóng handle.
3. Hai lần mượn đều thành công; trước khi kết thúc scope của owner, `insideCloseCount=0`.
4. Owner kết thúc `try`, Java đóng handle đúng tại ranh giới đã định; `afterCloseCount=1`.

**Nhánh sai có chủ ý:**

1. `wrongBorrow` chỉ được truyền `bad` do caller tạo nhưng lại khai báo `try (Handle mistakenlyOwned = handle)`.
2. Cú pháp này tạo một **biến local mới trỏ tới cùng object**; nó không nhân bản handle. Khi thoát scope, `close()` được gọi lên **chính handle của caller**.
3. Caller thử mượn lại và nhận `IllegalStateException("handle already closed")`.
4. Đây là **lỗi về hợp đồng ownership**, không phải lỗi compile-time và không nên sao chép `wrongBorrow` vào code sản phẩm.

### 4.1. Hợp đồng của API mượn nên rõ

```java
/**
 * Reads data using a caller-owned handle.
 * This method never closes the handle.
 */
static Result readFrom(BorrowedHandle handle) {
    // Dùng handle trong phạm vi gọi; không lưu giữ dài hạn hay close.
}
```

Đây là **chữ ký minh họa**, `Result`/`BorrowedHandle` chưa được định nghĩa. Đối với method mượn resource, tài liệu cần làm rõ:

- Caller vẫn sở hữu quyền đóng.
- Có được giữ lại tham chiếu sau khi method return không? Mặc định **không**, nếu chỉ mượn để dùng đồng bộ trong một lời gọi.
- Callee có được gọi các phương thức mutate state/seek/flush không? Quyền sử dụng khác với quyền đóng.
- Resource có được chia sẻ với thread khác không? `AutoCloseable` không tự cung cấp bảo đảm thread-safe.
- Nếu callee ném ngoại lệ, owner vẫn đóng tại scope thích hợp; callee không tự giành quyền đóng vì “đã có lỗi”.

Một hàm được gọi nhiều lần với cùng resource nên được test rằng nó **không đóng sau lần gọi đầu** và rằng owner đóng đúng một lần tại boundary phù hợp.

## 5. Phần C — Resource được chia sẻ giữa các consumer

Resource shared thường sống dài hơn một lời gọi. Ví dụ nhiều service component cần dùng một engine/cache/connection manager trong cùng application scope. Nếu mỗi consumer đều có `try (engine)`, consumer đầu tiên hoàn thành có thể đóng tài nguyên mà consumer khác vẫn đang cần.

**Phương án rõ ràng:** ứng dụng có một **lifecycle owner**; các client chỉ nhận tham chiếu dùng tạm thời. Owner đóng khi ứng dụng hoặc scope kết thúc, sau khi bảo đảm không còn consumer đang sử dụng.

### Chương trình hoàn chỉnh: `SharedLifecycleDemo.java`

```java
public final class SharedLifecycleDemo {
    private static final class SharedEngine implements AutoCloseable {
        private boolean closed;
        private int operations;

        int run(String client) {
            if (closed) {
                throw new IllegalStateException("engine closed");
            }
            operations++;
            System.out.println(client + ":operation=" + operations);
            return operations;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("engine:close");
            }
        }

        boolean isClosed() {
            return closed;
        }
    }

    private static void customerOne(SharedEngine engine) {
        engine.run("clientOne");
    }

    private static void customerTwo(SharedEngine engine) {
        engine.run("clientTwo");
    }

    public static void main(String[] args) {
        SharedEngine engine = new SharedEngine();
        try (SharedEngine owner = engine) {
            customerOne(engine);
            customerTwo(engine);
            System.out.println("duringScopeClosed=" + engine.isClosed());
        }
        System.out.println("afterScopeClosed=" + engine.isClosed());
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SharedLifecycleDemo.java
java SharedLifecycleDemo
```

Output:

```text
clientOne:operation=1
clientTwo:operation=2
duringScopeClosed=false
engine:close
afterScopeClosed=true
```

### Phân tích

- `main` đóng vai trò scope owner; nó quyết định thời gian sống của `SharedEngine`.
- `customerOne` và `customerTwo` là consumer: được mượn cùng engine, không gọi `close`.
- Sau hai tác vụ, engine vẫn mở (`duringScopeClosed=false`). Khi scope của owner kết thúc, `close` được gọi.
- Đối tượng trong demo **không thread-safe**: `closed` và `operations` là các field không đồng bộ hóa. Demo chạy tuần tự để minh họa ownership, không phải ví dụ truy cập đồng thời an toàn.
- Trong ứng dụng có tác vụ async/thread, lifecycle owner cần **phối hợp việc dừng nhận tác vụ, đợi các thao tác đang chạy hoàn tất và sau đó đóng resource**. Một `try` đơn thuần không thực hiện toàn bộ chính sách phối hợp đó.

### 5.1. Shared ownership không đồng nghĩa “ai cũng được close”

Có ba pattern thường gặp (phải dựa trên API contract thực tế):

| Mô hình | Consumer làm gì? | Ai đóng tài nguyên nền? |
| --- | --- | --- |
| Một owner, nhiều borrower | Sử dụng, không close | Lifecycle owner |
| Pool + lease | Lấy lease; trả lease qua `close()` nếu contract quy định | Pool đóng resource vật lý khi lifecycle pool kết thúc |
| Reference-counted/shared handle | Phát hành handle có quyền release riêng, đếm số người sử dụng | Manager đóng underlying khi điều kiện ownership đạt, thường cần đồng bộ |

Không tự triển khai reference-counting bằng một biến `int` thông thường trong code đa luồng rồi coi là an toàn. Cần bảo vệ race giữa acquire/release/close, lỗi khi người dùng quên release và hành vi sau shutdown; thư viện/framework quản lý lifecycle thường có contract rõ hơn.

### 5.2. Quy ước cho framework-managed resources

Nếu framework tạo `DataSource`, client, connection manager, server hay service container, resource có thể do framework sở hữu. Method nghiệp vụ không nên đóng đối tượng cấp ứng dụng nếu framework vẫn dùng. Ngược lại, một **connection lease** được lấy từ pool thường phải được trả theo quy tắc riêng của pool; nó không đồng nhất với lifetime của `DataSource`.

**Không suy luận ownership từ kiểu interface đơn thuần.** Cùng một `AutoCloseable` được trả bởi các factory khác nhau có thể mang hợp đồng khác nhau. Đọc tài liệu API, scope của dependency injection hoặc hợp đồng provider.

## 6. Phần D — Factory tạo và chuyển quyền đóng cho caller

Đôi khi chính **factory** tạo resource, nhưng resource cần tiếp tục sống **sau khi factory return** để caller sử dụng. Nếu factory dùng try-with-resources bao quanh resource rồi `return` nó, `close()` chạy trước khi caller nhận resource — có nguy cơ trả một đối tượng **đã đóng**.

Muốn chuyển quyền sở hữu, factory nên trả resource còn mở và ghi rõ **caller phải đóng**.

### Chương trình hoàn chỉnh: `TransferOwnershipDemo.java`

```java
public final class TransferOwnershipDemo {
    private static final class ExportSession implements AutoCloseable {
        private boolean closed;

        void export() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            System.out.println("export:write");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("export:close");
            }
        }
    }

    private static ExportSession createForCaller() {
        System.out.println("factory:create");
        return new ExportSession();
    }

    public static void main(String[] args) {
        try (ExportSession session = createForCaller()) {
            session.export();
            System.out.println("caller:complete");
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TransferOwnershipDemo.java
java TransferOwnershipDemo
```

Output:

```text
factory:create
export:write
caller:complete
export:close
```

### Ranh giới ownership trong ví dụ

1. Factory gọi constructor và trả lại `ExportSession` **vẫn mở**.
2. Tại thời điểm nhận đối tượng, caller nhận trách nhiệm đóng khi không còn dùng.
3. Caller đặt nó trong `try-with-resources`, thực hiện `export` rồi kết thúc scope.
4. `close` chỉ diễn ra ở caller. Factory không bọc resource bằng try-with-resources rồi trả về ngay trong scope đó.

**Hợp đồng cần ghi:** “Caller owns the returned session and must close it.” Nếu factory khởi tạo nhiều thành phần và lỗi trước khi trả về resource hoàn chỉnh, **factory vẫn có trách nhiệm cleanup những phần đã cấp phát**; không có caller để nhận quyền khi method ném trước khi return.

### Anti-pattern: trả tài nguyên từ phạm vi sẽ đóng nó

```java
static Session badFactory() {
    try (Session session = new Session()) {
        return session; // session sẽ bị close trước khi caller nhận!
    }
}
```

Đây là **mảnh minh họa sai**, yêu cầu lớp `Session` tương ứng. Nó có thể **biên dịch và chạy**, nên lỗi không nhất thiết hiện ở bước compile. Với các resource có kiểm tra trạng thái, lần dùng đầu của caller sẽ thất bại; với implementation khác, tác hại có thể khó quan sát ngay.

## 7. Wrapper có thể đóng cả underlying resource

Một ranh giới ownership dễ bỏ qua: **đóng wrapper có thể đóng resource mà wrapper đang bọc**. Ví dụ `BufferedReader` sở hữu một `Reader` bên dưới, `InputStreamReader` lại bọc một `InputStream`. Khi đóng `BufferedReader`, cơ chế đóng được truyền xuống các tầng wrapper.

Đối với stream **do caller cho mượn**, việc callee tự tạo wrapper rồi đặt wrapper vào try-with-resources có thể vẫn **đóng underlying stream của caller**. Bạn đã đóng “đối tượng vừa tạo”, nhưng lại vô tình đóng cả nguồn được mượn. Cần xét **chuỗi ownership** xuyên qua wrapper.

### Chương trình hoàn chỉnh: `WrapperOwnershipDemo.java`

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public final class WrapperOwnershipDemo {
    private static final class TrackingInput extends ByteArrayInputStream {
        private boolean closed;

        TrackingInput(String data) {
            super(data.getBytes(StandardCharsets.UTF_8));
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
            System.out.println("input:close");
        }

        boolean wasClosed() {
            return closed;
        }
    }

    public static void main(String[] args) throws IOException {
        TrackingInput input = new TrackingInput("data");
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8))) {
            System.out.println("line=" + reader.readLine());
        }
        System.out.println("underlyingClosed=" + input.wasClosed());
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 WrapperOwnershipDemo.java
java WrapperOwnershipDemo
```

Output:

```text
line=data
input:close
underlyingClosed=true
```

**Cần rút ra:** `BufferedReader` được đóng cuối scope, kéo theo việc đóng `InputStreamReader` và gọi `close()` của `TrackingInput`. `TrackingInput` trong demo ghi nhận `closed=true`; việc subclass `ByteArrayInputStream` này chỉ để **quan sát lời gọi close**. Trong Java, `ByteArrayInputStream.close()` mặc định không làm các thao tác đọc tiếp theo bị lỗi; vì vậy demo dùng flag riêng thay vì giả định sau đóng mọi loại stream đều thất bại như nhau.

Nếu input thực sự thuộc caller và phải còn sống sau lời gọi, cần chọn một thiết kế khác: caller tạo và sở hữu toàn bộ chuỗi wrapper, callee chỉ nhận một `Reader` và không close; hoặc dùng adapter không đóng underlying **được tài liệu hóa/kiểm chứng cẩn thận** khi đó là yêu cầu. Không tự nghĩ rằng tạo wrapper bằng `new` sẽ làm underlying trở thành tài nguyên của bạn.

### Bảng kiểm tra chuỗi ownership của wrapper

| Tình huống | Câu hỏi bắt buộc |
| --- | --- |
| `new BufferedReader(new InputStreamReader(input))` | Đóng reader có đóng `input` không? |
| Reader chỉ dùng trong method | Method sở hữu cả chuỗi reader/input hay chỉ mượn input? |
| Trả `Stream`/`Reader` cho caller | Scope nào giữ underlying còn mở đến lúc caller dùng xong? |
| Client/response body từ HTTP library | Closing response/stream có ảnh hưởng connection pool hoặc request không? |
| Wrapper tùy biến triển khai `AutoCloseable` | `close()` có chuyển tiếp lời gọi xuống delegate? Có idempotent không? |

Đừng áp dụng một quy tắc “đóng wrapper luôn luôn đóng delegate” cho **mọi** thư viện mà chưa xem API contract. Với `BufferedReader`/`InputStreamReader` ở ví dụ trên, hành vi này đã được minh họa và kiểm chứng.

## 8. Thực tế: API ownership nên công khai ở chữ ký, tài liệu và kiểm thử

Kiểu `AutoCloseable` cho thấy khả năng đóng, nhưng không phân biệt owned với borrowed. Có thể tăng độ rõ của API bằng **tên, tài liệu, scope và factory**.

### 8.1. Ba contract rõ ràng

```java
// Owned: hàm tự tạo, tự dùng, tự đóng.
static Result loadFromFile(Path file) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(file)) {
        return parse(reader);
    }
}

// Borrowed: caller sở hữu Reader; hàm không đóng.
static Result parse(Reader reader) throws IOException {
    return parseWithoutClosing(reader);
}

// Transferred: caller nhận và phải đóng Reader trả về.
static BufferedReader openForCaller(Path file) throws IOException {
    return Files.newBufferedReader(file);
}
```

Các đoạn này là **phương thức minh họa**, cần import `Path`, `Files`, `BufferedReader`, `Reader`, `IOException` và định nghĩa `Result`, `parseWithoutClosing`; không phải lớp độc lập. Hợp đồng nên ghi rõ:

- `loadFromFile` đóng reader do chính nó mở, kể cả khi `parse` thất bại.
- `parse` nhận reader caller-owned: có thể đọc, nhưng không giữ tham chiếu lâu dài và không close.
- `openForCaller` chuyển ownership, yêu cầu caller dùng `try-with-resources` hoặc đóng theo lifecycle đã thỏa thuận.
- Nếu trả một `Stream` lazy đọc file, phải giữ nguồn còn mở trong suốt quá trình tiêu thụ và định rõ caller phải close stream; **không** đóng nguồn ngay trước khi trả stream.

### 8.2. Đọc hợp đồng sở hữu ở nơi nào?

Xem tài liệu API và JavaDoc (đặc biệt câu “caller must close”, “do not close”, “takes ownership”), điểm tạo object, nguồn DI/framework, trách nhiệm stop/shutdown, đường trả về, và các callback/asynchronous job có tiếp tục dùng object sau method hay không.

Với nguồn do framework tạo: không chỉ xem đối tượng triển khai `AutoCloseable`; kiểm tra framework giao quyền close cho component nào. Các tài nguyên do hệ thống chia sẻ có thể tồn tại lâu hơn vòng đời một request/method.

### 8.3. Không giữ resource sống sai phạm vi

Trường hợp trả `Iterator`, `Stream` hoặc callback truy cập một `Reader` đã đóng là lỗi lifetime, dù method mở/đóng resource rất “đúng cú pháp”. Tài nguyên và phép tính lazy phải có vòng đời tương thích. Có thể chọn trả về dữ liệu đã materialize đầy đủ hoặc chuyển ownership của stream/resource cho caller, tùy yêu cầu.

## 9. Đường đi lỗi khi tạo, dùng, chuyển giao và đóng

Khi thiết kế ownership, đừng chỉ test happy path. Có ít nhất bốn thời điểm có thể phát sinh lỗi:

1. **Khởi tạo:** constructor/factory tạo resource thất bại. Không có object hoàn chỉnh để chuyển cho caller; factory phải tự dọn những phần đã mở thành công.
2. **Sử dụng:** owner hoặc borrower gọi `read`/`write`/`run` và gặp exception. Nếu borrower ném lỗi, ownership thông thường **không chuyển sang borrower**; owner vẫn đóng đúng scope.
3. **Đóng:** `close()` thất bại, có thể trở thành exception chính hoặc suppressed tùy body đã lỗi hay chưa.
4. **Chuyển giao:** method trả resource cho caller nhưng caller không dùng try-with-resources, tạo **resource leak**; hoặc factory đóng trước khi return, tạo **premature close**.

### 9.1. Primary và suppressed khi body và close đều lỗi

```java
try (Resource resource = open()) {
    doWork(resource); // Giả sử ném một exception A.
} // Giả sử close() cũng ném exception B.
```

Đoạn minh họa cần định nghĩa `Resource` và các hàm. Với cơ chế try-with-resources chuẩn, nếu body ném `A` rồi close ném `B`, `A` được giữ làm **primary**, `B` được gắn qua `A.getSuppressed()`. Nếu body thành công nhưng close ném `B`, chính `B` có thể là primary.

Điều này có nghĩa là caller phải xem xét cả **chính exception lẫn suppressed/cause chain** khi chẩn đoán lỗi tài nguyên. Không xử lý close failure như một lỗi “không đáng kể” mặc định; một số resource có thể thực hiện flush khi close.

### 9.2. Không làm mất ngoại lệ bằng finally thủ công

```java
try {
    doWork(resource);
} finally {
    resource.close();
}
```

Đây là ví dụ **minh họa**; nếu thân ném một exception và `close()` cũng ném, một `finally` ném lỗi có thể thay thế lý do lỗi trước đó. Try-with-resources được thiết kế để biểu diễn rõ lifecycle và giữ những lỗi close phụ qua suppressed. Dùng try-with-resources thay cho cleanup thủ công khi bạn **sở hữu** resource và muốn đóng trong scope đó.

Nếu resource là **borrowed**, chuyển nó vào try-with-resources không phải cách sửa lỗi cleanup; nó **đổi ownership** ngoài hợp đồng. Giải quyết trách nhiệm đóng ở đúng owner.

### 9.3. Chuyển giao thất bại giữa chừng

Ví dụ một factory mở resource A rồi cần cấu hình thêm B trước khi trả handle A. Nếu tạo B ném exception, factory chưa chuyển quyền cho caller, nên factory phải đóng A trong đường lỗi. Có thể bố trí cleanup cẩn thận bằng try-with-resources cho những resource vẫn thuộc factory trong giai đoạn khởi tạo, nhưng không được đóng handle **sau khi** chuyển giao thành công.

Khi có nhiều resource độc lập, đặt chúng trong scope đúng theo chủ sở hữu. Không dùng một `try-with-resources` dài trên resource đã chuyển quyền cho thành phần khác chỉ để “chắc chắn không leak”.

## 10. Lỗi thường gặp trong code review

### 10.1. “Có AutoCloseable là cứ try-with-resources”

Sai: một borrowed resource vẫn có thể triển khai `AutoCloseable` nhưng callee **không được** đóng. Kiểm tra ownership trước khi thêm `try(...)`.

### 10.2. “Tôi tạo wrapper nên underlying cũng thuộc tôi”

Không nhất thiết. `BufferedReader` có thể đóng `InputStreamReader` và underlying `InputStream` khi bị đóng. Nếu underlying do caller sở hữu, đóng wrapper có thể vi phạm hợp đồng. Test lan truyền `close()` của chuỗi wrapper.

### 10.3. “`close()` luôn idempotent”

`AutoCloseable` tổng quát không bắt buộc mọi implementation gọi `close()` nhiều lần là vô hại. Một số lớp/interface cụ thể có hợp đồng mạnh hơn, nhưng không áp dụng suy rộng. Đóng đúng một lần bởi đúng owner vẫn là mục tiêu đơn giản, dễ kiểm chứng.

### 10.4. “Đóng shared resource trong mỗi request”

Một resource cấp application do nhiều request mượn không thể bị đóng ngay sau request đầu tiên nếu request khác còn dùng. Owner ở cấp lifecycle phù hợp phải điều phối lúc shutdown; consumer chỉ release **lease** nếu contract yêu cầu, không tự đóng shared manager.

### 10.5. “Factory tạo thì factory phải đóng”

Factory có thể **chuyển giao ownership**. Khi trả về một resource còn mở theo contract, caller phải đóng. Factory không nên return resource nằm trong scope sắp tự close, trừ khi API cố ý trả một đối tượng đã hoàn tất và không cần dùng tài nguyên nữa.

### 10.6. “Sau khi method return thì callback/lazy stream không còn cần resource”

Có thể ngược lại: stream lazy hoặc callback tiếp tục cần resource. Bảo đảm lifetime kéo dài đủ, hoặc materialize dữ liệu trong scope resource trước khi return.

### 10.7. “Tất cả close failure giống nhau”

`close()` của một resource có thể là no-op, release, flush, commit-like step hoặc trả lease về pool tùy contract. Không gộp mọi close failure thành lỗi có thể bỏ qua/auto retry. Quan sát exception của body, của close và suppressed.

### 10.8. “`AutoCloseable` tự bảo đảm thread-safety”

Không. Interface chỉ quy định khả năng đóng, không đồng bộ hóa thao tác dùng/đóng. Với resource shared đa luồng, bảo đảm không đóng giữa các thao tác đang chạy, hoặc dùng API được tài liệu hóa hỗ trợ concurrency.

### 10.9. “Borrowed resource có thể lưu trong field bất kỳ”

Lưu borrowed resource để dùng sau khi caller đã đóng dẫn tới lỗi lifetime. Nếu cần giữ lâu dài, phải nâng hợp đồng thành ownership transfer, shared managed lifecycle hoặc cơ chế lease rõ ràng.

### 10.10. “Cứ bắt Exception để tránh lỗi close”

`catch (Exception e) { }` rỗng có thể nuốt lỗi sử dụng/đóng. Chọn boundary xử lý, log đúng nơi và làm rõ khi nào close failure làm toàn bộ operation thất bại. Với checked exceptions, đừng bỏ `throws` chỉ bằng cách biến lỗi thành success giả.

## 11. Test ownership bằng ma trận vòng đời

| Ca kiểm tra | Ai sở hữu? | Các hành động | Kỳ vọng |
| --- | --- | --- | --- |
| `OwnedResourceDemo` thành công | `run` | Tạo → use → done → scope end | `close()` gọi sau `done` |
| `OwnedResourceDemo` thất bại | `run` | Tạo → use → throw IOException | `close()` vẫn gọi trước caller catch |
| `BorrowedResourceDemo` đúng | `main` | Gọi `borrow` 2 lần trong scope | Không đóng sau lần borrow đầu; owner đóng khi kết thúc |
| `BorrowedResourceDemo` sai có chủ ý | Caller nhưng callee đóng nhầm | `wrongBorrow` đóng handle | Caller mượn lại gặp “already closed” |
| `SharedLifecycleDemo` | `main` | Hai client dùng chung | Chưa đóng trong scope; đóng khi owner kết thúc |
| `TransferOwnershipDemo` | Caller nhận từ factory | Factory tạo → caller dùng → caller scope end | Factory không đóng sớm; caller đóng |
| `WrapperOwnershipDemo` | Theo hợp đồng wrapper/underlying | Đóng BufferedReader | Lời gọi close truyền tới TrackingInput |
| Không phải `AutoCloseable` | Không áp dụng | `try (String s=...)` | Compiler từ chối |
| Checked `close()` chưa xử lý | Owner method | `close() throws IOException`, không catch/throws | Compiler từ chối |

Các ca chạy trong năm chương trình Java được cung cấp; hai ca compile âm cần thử trong những file riêng.

### 11.1. Negative compile test A: đối tượng không AutoCloseable

```java
public final class BadResource {
    static void run() {
        try (String value = "text") { // CỐ Ý SAI
            System.out.println(value);
        }
    }
}
```

Lưu thành `BadResource.java`, chạy:

```bash
javac --release 17 -encoding UTF-8 BadResource.java
```

**Kỳ vọng:** FAIL — `String` không triển khai `AutoCloseable`, không phải một resource hợp lệ trong header `try-with-resources`.

### 11.2. Negative compile test B: thiếu hợp đồng checked close

```java
import java.io.IOException;

public final class BadCheckedClose {
    static final class R implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close");
        }
    }

    static void run() {
        try (R resource = new R()) {
            System.out.println("work");
        }
    }
}
```

Lưu thành `BadCheckedClose.java`, chạy:

```bash
javac --release 17 -encoding UTF-8 BadCheckedClose.java
```

**Kỳ vọng:** FAIL — phương thức `run()` không bắt hoặc khai báo `IOException` có thể phát sinh từ `R.close()`. Giải pháp phụ thuộc hợp đồng: `run() throws IOException` nếu caller cần xử lý, hoặc catch/translate lỗi tại boundary phù hợp.

**Lưu ý:** Hai ví dụ trên **cố ý không biên dịch**; không đưa chúng vào cùng lệnh biên dịch năm chương trình đầy đủ rồi đánh giá các chương trình đúng là thất bại.

## 12. Quy trình thiết kế và review ownership

Trước khi thêm một resource vào `try-with-resources`, hãy đi theo các bước:

1. **Xác định điểm tạo:** `new`/factory/framework/pool hoặc caller truyền vào?
2. **Xác định chủ sở hữu:** ai cam kết chịu trách nhiệm đóng và khi nào? Chưa rõ thì đọc API contract/JavaDoc.
3. **Xác định thời gian sống:** chỉ trong method, trong request, trong một async task hay suốt ứng dụng?
4. **Xác định consumer:** có bao nhiêu thành phần? Có truy cập đồng thời hay chỉ nối tiếp?
5. **Chọn ranh giới đóng:** owned local → try-with-resources gần điểm tạo; borrowed → owner đóng; shared → lifecycle manager; transferred → caller đóng.
6. **Kiểm tra chuỗi wrapper:** đóng object ở scope có đóng resource bên dưới không? Ai sở hữu underlying?
7. **Kiểm tra failure paths:** tạo lỗi, dùng lỗi, close lỗi, trả về trước close, async giữ tham chiếu sau khi scope kết thúc.
8. **Kiểm tra checked exceptions:** constructor, use và `close()` khai báo gì? `throws` hoặc catch đủ chưa?
9. **Kiểm tra tránh đóng lặp:** không có hai owner cùng gọi `close`. Nếu dùng lease/pool, tuân theo contract release.
10. **Viết test theo event trace:** thứ tự open/use/close, số lần close, trạng thái sau mỗi mượn, hành vi sau shutdown, exception/cause/suppressed.

### Checklist trước khi merge

- [ ] Mọi resource có owner và phạm vi đóng được ghi rõ bằng code hoặc JavaDoc.
- [ ] Resource do method tạo và giữ có scope đóng phù hợp, kể cả khi lỗi.
- [ ] Callee không close resource borrowed nếu không được chuyển quyền rõ ràng.
- [ ] Không đóng resource shared khi vẫn có consumer/async task dùng.
- [ ] Nếu factory trả resource, caller biết mình phải close; factory xử lý cleanup khi không thể return.
- [ ] Không trả reader/stream đã đóng cho caller cần tiếp tục đọc.
- [ ] Wrapper close đã được kiểm tra có ảnh hưởng underlying hay không.
- [ ] Không giả định mọi `AutoCloseable.close()` idempotent, thread-safe hay luôn không ném.
- [ ] Có test cả đường thành công, lỗi sử dụng, lỗi close và trường hợp đóng sớm.
- [ ] Với managed pool/framework, code tuân đúng hợp đồng lifecycle và lease.
- [ ] Chữ ký checked exception được compiler chấp nhận; không bắt rộng rồi nuốt lỗi.
- [ ] Không thêm cleanup trùng hoặc làm thay đổi ownership khi refactor.

## 13. Bài tập thực hành

**Bài 1 — Owned:** Viết một lớp `AutoCloseable` ghi sự kiện `open`/`use`/`close`. Dùng try-with-resources và cố ý ném lỗi từ `use`; kiểm tra `close` vẫn được gọi đúng một lần.

**Bài 2 — Borrowed:** Viết `process(Reader reader)` chỉ đọc một dòng, không đóng `reader`. Cho caller gọi hai lần trong cùng scope. Vì sao đưa reader vào `try(reader)` trong `process` sẽ vi phạm hợp đồng mượn, dù cú pháp hợp lệ trên Java 17?

**Bài 3 — Shared:** Hai service dùng một resource ứng dụng. Viết sơ đồ lifecycle: start → acquire/use → stop accepting work → wait for in-flight operations → close. Phân tích điều gì xảy ra nếu service đầu tự close resource.

**Bài 4 — Transferred:** Tạo factory trả `AutoCloseable` còn mở. Cho caller sử dụng trong try-with-resources. Đảo thử bằng một `badFactory` đóng resource trước khi return rồi dự đoán lỗi đầu tiên của caller.

**Bài 5 — Wrapper:** Dùng `WrapperOwnershipDemo`; giải thích tại sao đóng `BufferedReader` làm `TrackingInput.wasClosed() == true`. Nếu `input` là caller-owned, callee phải thay đổi contract/architecture ra sao?

**Bài 6 — Close failure:** Tạo một `AutoCloseable` có `close() throws IOException`. Cho body thành công rồi đóng lỗi; cho body ném exception rồi đóng lỗi. Trong mỗi tình huống, exception nào là primary, cái nào nằm trong `getSuppressed()`?

**Bài 7 — Code review:** Với một method nhận `DataSource` từ dependency injection, mở `Connection` để truy vấn và trả về kết quả đã materialize, chỉ ra ba vòng đời khác nhau: `DataSource` (shared), connection lease (owned by method theo pool contract), kết quả (dữ liệu của caller). Vì sao không đóng toàn bộ `DataSource` khi method kết thúc?

### Đáp án định hướng

- Bài 1: Resource tạo trong try-with-resources thì `close` được gọi khi rời scope, kể cả đường ném exception.
- Bài 2: Callee không được đóng borrowed reader; owner cần đọc nhiều lần hoặc quyết định khi nào kết thúc.
- Bài 3: Lifetime của shared resource phải dài hơn tất cả use đang chạy; cơ chế ngăn race/đóng sớm phụ thuộc manager.
- Bài 4: Quyền đóng chuyển sang caller khi factory trả resource mở. Tài nguyên bị đóng trong factory không còn bảo đảm dùng được.
- Bài 5: Wrapper close lan xuống underlying theo hợp đồng lớp trong demo. Đừng đóng wrapper nếu việc đó đóng resource caller-owned ngoài ý muốn.
- Bài 6: Body thành công + close lỗi → close exception là primary. Body lỗi + close lỗi → body exception là primary, close exception bị suppressed.
- Bài 7: `DataSource` cấp ứng dụng và `Connection` lease có ownership khác nhau; không gộp lifecycle.

## Tài liệu chính thức (đang được áp dụng)

- [Java SE 17 — AutoCloseable API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()` và ghi chú về repeated close.
- [Java SE 17 — Closeable API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): subtype của `AutoCloseable`, `IOException` và hợp đồng đóng.
- [Java Language Specification 17 — `14.20.3: try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): resource initialization, close order, suppressed exceptions.
- [Java Language Specification 17 — `14.20.3.1 Basic try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.1): phạm vi và hành vi đóng.
- [Java SE 17 — BufferedReader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html) và [InputStreamReader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html): vòng đời reader và tài nguyên bên dưới.
- [Java SE 17 — Throwable API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()` và `getCause()` khi chẩn đoán lỗi.

**Ghi nhớ:** Quy tắc đóng đúng phụ thuộc vào **ownership, không chỉ vào việc đối tượng triển khai `AutoCloseable`**. Tạo và sở hữu tại đây → đóng trong scope; chỉ mượn → không đóng; chia sẻ → owner của lifecycle đóng sau khi hết consumer; chuyển quyền → caller đóng. Kiểm tra thêm wrapper, checked exception, close failure và đường đi bất thường để tránh resource leak lẫn premature close.