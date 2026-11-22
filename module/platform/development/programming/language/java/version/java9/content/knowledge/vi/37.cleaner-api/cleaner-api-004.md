# Gọi `clean()` chủ động từ `close()`

`Cleaner` là API được bổ sung trong Java 9 để cung cấp một cơ chế dọn dẹp dự phòng khi object không còn được sử dụng và trở nên phantom reachable. Tuy nhiên, việc chờ garbage collector phát hiện object không phù hợp với vòng đời tài nguyên cần giải phóng đúng thời điểm. Với một wrapper quản lý tài nguyên, cách thiết kế rõ ràng là triển khai `AutoCloseable` và gọi `Cleanable.clean()` trực tiếp từ `close()`.

Khi `close()` được gọi, cleaning action được thực thi ngay bởi lời gọi `clean()` và `Cleanable` được disassociate khỏi `Cleaner`. Nếu caller quên đóng object, Cleaner vẫn có thể chạy cùng action như một phương án dự phòng khi object đủ điều kiện được thu gom. Hai đường đi dùng chung một action, nên trạng thái cleanup phải an toàn khi chỉ chạy một lần.

## 1. Cleaner giải quyết vấn đề gì?

Một object Java đôi khi sở hữu một tài nguyên bên ngoài heap, ví dụ native memory, native handle, tài nguyên hệ điều hành hoặc một vùng cấp phát từ thư viện native. Garbage collector quản lý bộ nhớ heap nhưng không biết chính xác thời điểm nghiệp vụ mà tài nguyên bên ngoài nên được giải phóng.

`Cleaner` cho phép đăng ký một cleaning action gắn với vòng đời reachability của object. Khi object được đăng ký không còn được tham chiếu mạnh và trở nên phantom reachable, Cleaner có thể thực thi action trên thread dọn dẹp của nó.

Cleaner là cơ chế dự phòng. Thời điểm action tự động chạy phụ thuộc vào garbage collection và không được bảo đảm xảy ra ngay khi object không còn được sử dụng. Ứng dụng không nên dựa vào Cleaner để đóng file, socket, lock hoặc tài nguyên có giới hạn đúng thời hạn.

Với tài nguyên có vòng đời xác định, hãy cung cấp `close()` và khuyến khích caller dùng try-with-resources. Cleaner chỉ bổ sung một lớp bảo vệ khi caller quên đóng.

## 2. Các thành phần của Cleaner

API chính nằm trong `java.lang.ref`:

- `Cleaner.create()` tạo một Cleaner dùng để quản lý các cleaning action.
- `Cleaner.register(object, action)` đăng ký object và action, trả về một `Cleaner.Cleanable`.
- `Cleanable.clean()` yêu cầu thực thi action ngay nếu action chưa chạy; action chỉ chạy tối đa một lần.
- `Cleaner` có thể dùng chung cho nhiều object; thường không cần tạo một Cleaner riêng cho mỗi tài nguyên.

Một wrapper thường giữ `Cleanable`, còn cleaning action giữ phần state cần thiết để giải phóng tài nguyên:

```text
ManagedResource
    |
    +---- Cleanable
              |
              v
        Cleanup State ----> native handle

Cleanup State không được giữ tham chiếu mạnh tới ManagedResource.
```

Điều kiện cuối cùng rất quan trọng. Nếu action giữ trực tiếp hoặc gián tiếp object được đăng ký, object đó sẽ không trở nên phantom reachable; Cleaner không thể tự động chạy action và tài nguyên có thể bị giữ mãi.

## 3. Vì sao `close()` nên gọi `cleanable.clean()`?

Wrapper có thể triển khai `AutoCloseable` và định nghĩa:

```java
@Override
public void close() {
    cleanable.clean();
}
```

Cách này dùng cùng một cleaning action cho cả hai trường hợp:

1. Caller đóng tài nguyên chủ động bằng `close()` hoặc try-with-resources.
2. Caller quên đóng; Cleaner chạy action sau khi wrapper không còn được tham chiếu mạnh.

Khi `cleanable.clean()` được gọi tường minh, action được chạy trong thread gọi `clean()`. Khi Cleaner tự động kích hoạt action, action được chạy bởi thread dọn dẹp của Cleaner. Vì vậy, cleanup action cần ngắn, an toàn khi chạy trên thread khác và không phụ thuộc vào thread-local state của caller.

`Cleanable.clean()` bảo đảm action chỉ được thực thi tối đa một lần, kể cả khi nhiều thread cùng gọi `close()` hoặc Cleaner đồng thời phát hiện object đủ điều kiện. Dù vậy, phần state quản lý tài nguyên vẫn nên có cơ chế one-time release rõ ràng, ví dụ `AtomicBoolean.compareAndSet(false, true)` hoặc `AtomicLong.getAndSet(0)`.

## 4. Cleanup State phải tách khỏi object được đăng ký

Không viết cleaning action bằng lambda hoặc inner class vô tình capture `this`:

```java
// Không an toàn: lambda có thể giữ tham chiếu đến wrapper.
cleaner.register(this, () -> this.releaseResource());
```

Action trên giữ wrapper sống vì nó cần gọi phương thức instance. Cleaner giữ action; action giữ wrapper; wrapper vì thế không thể trở nên phantom reachable.

Hãy dùng một static nested class chỉ giữ handle hoặc state tối thiểu:

```java
private static final class State implements Runnable {
    private final NativeHandle handle;

    State(NativeHandle handle) {
        this.handle = handle;
    }

    @Override
    public void run() {
        handle.release();
    }
}
```

`State` không có tham chiếu tới wrapper. Nó chỉ sở hữu thông tin đủ để giải phóng tài nguyên. Tránh non-static inner class, method reference tới instance wrapper hoặc lambda tham chiếu đến field/method của `this`.

## 5. Cleanup phải idempotent và an toàn khi cạnh tranh

Cleanup có thể được kích hoạt bởi `close()` hoặc Cleaner. Caller cũng có thể gọi `close()` nhiều lần, hoặc nhiều thread cùng gọi `close()`. Do đó, giải phóng tài nguyên cần được bảo vệ để chỉ xảy ra một lần.

Với một native handle có giá trị số, một mẫu thường dùng là:

```java
private static final class State implements Runnable {
    private final AtomicLong handle;

    State(long value) {
        handle = new AtomicLong(value);
    }

    @Override
    public void run() {
        long value = handle.getAndSet(0L);
        if (value != 0L) {
            releaseNativeHandle(value);
        }
    }
}
```

Chỉ thread lấy được handle khác `0` mới thực hiện release. Các lần gọi sau nhìn thấy `0` và không giải phóng lại. Cách này giả định `0` là giá trị không hợp lệ và hàm release không ném exception; nếu handle có miền giá trị khác, hãy chọn sentinel phù hợp.

Không dựa vào Cleaner để đồng bộ mọi thao tác sử dụng tài nguyên. Nếu `use()` có thể chạy đồng thời với `close()`, wrapper phải định nghĩa rõ hợp đồng: chặn thao tác mới sau khi đóng, đồng bộ thao tác đang chạy và tránh truy cập handle sau release. `Cleanable` chỉ điều phối việc chạy action một lần; nó không tự làm cho toàn bộ API của wrapper thread-safe.

## 6. Ví dụ hoàn chỉnh: `AutoCloseable.close()` gọi `cleanable.clean()`

Ví dụ sau mô phỏng một native handle bằng state có cờ `released`. `ManagedResource` giữ handle để sử dụng và đăng ký một static cleanup state với Cleaner. `close()` gọi `cleanable.clean()`; try-with-resources kích hoạt đường đóng chủ động. Gọi `close()` lần nữa không release lần hai.

Trong ứng dụng thật, `NativeHandle.release()` sẽ gọi hàm giải phóng native handle hoặc API giải phóng tài nguyên tương ứng. Phần mô phỏng giúp quan sát vòng đời mà không phụ thuộc thư viện native.

Tạo tệp `CleanerCloseDemo.java`:

```java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CleanerCloseDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class NativeHandle {
        private final String name;
        private final AtomicBoolean released = new AtomicBoolean();
        private final AtomicInteger releaseCount = new AtomicInteger();

        NativeHandle(String name) {
            this.name = name;
        }

        void use() {
            if (released.get()) {
                throw new IllegalStateException("Resource is already released");
            }
            System.out.println("Using resource: " + name);
        }

        void release() {
            if (released.compareAndSet(false, true)) {
                releaseCount.incrementAndGet();
                System.out.println("Released resource: " + name);
            }
        }

        boolean isReleased() {
            return released.get();
        }

        int releaseCount() {
            return releaseCount.get();
        }
    }

    private static final class State implements Runnable {
        private final NativeHandle handle;

        State(NativeHandle handle) {
            this.handle = handle;
        }

        @Override
        public void run() {
            handle.release();
        }
    }

    private static final class ManagedResource implements AutoCloseable {
        private final NativeHandle handle;
        private final Cleaner.Cleanable cleanable;

        ManagedResource(String name) {
            handle = new NativeHandle(name);
            cleanable = CLEANER.register(this, new State(handle));
        }

        void use() {
            handle.use();
        }

        boolean isReleased() {
            return handle.isReleased();
        }

        int releaseCount() {
            return handle.releaseCount();
        }

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        ManagedResource resource = new ManagedResource("demo");

        try (resource) {
            resource.use();
        }

        System.out.println("Released after close: " + resource.isReleased());

        resource.close();
        System.out.println("Release count after second close: "
                + resource.releaseCount());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all CleanerCloseDemo.java
java CleanerCloseDemo
```

Kết quả stdout:

```text
Using resource: demo
Released resource: demo
Released after close: true
Release count after second close: 1
```

Trong ví dụ, `try (resource)` gọi `close()` khi thoát block. `close()` gọi `cleanable.clean()`, nên action chạy trước dòng in trạng thái released. Lời gọi `resource.close()` tiếp theo không làm tăng `releaseCount`; cleaning action đã được thực thi và disassociate.

Ví dụ không gọi `System.gc()` để cố kích hoạt Cleaner. GC không phải cơ chế điều khiển thời điểm cleanup và một test dựa vào `System.gc()` không thể bảo đảm action chạy ngay.

## 7. Dùng Cleaner như safety net, không thay thế try-with-resources

Với tài nguyên có API đóng rõ ràng, hãy để caller sở hữu vòng đời bằng try-with-resources:

```java
try (ManagedResource resource = new ManagedResource("connection")) {
    resource.use();
}
```

Đường đóng chủ động có thời điểm xác định và lỗi có thể được báo cho caller theo hợp đồng `close()`. Cleaner chỉ xử lý trường hợp caller bỏ sót bước đóng. Nếu Cleaner tự chạy, thời điểm cleanup không xác định và có thể quá muộn so với giới hạn tài nguyên.

Không dùng Cleaner để thay thế `AutoCloseable`, `Closeable` hoặc các API quản lý tài nguyên đã có. Với file, socket, stream, channel, database connection hoặc lock, hãy dùng cơ chế đóng chính thức và try-with-resources. Cleaner chỉ nên bổ sung cho state ngoài heap mà wrapper thực sự sở hữu.

## 8. Lỗi và ngoại lệ trong cleaning action

Cleaning action có thể được gọi tự động trên Cleaner thread. Nếu action ném exception, không có caller nghiệp vụ đang chờ để nhận và xử lý lỗi như trong một lời gọi `close()` thông thường. Vì vậy action nên tự xử lý lỗi, ghi nhận metric/log phù hợp và không để exception thoát ra ngoài.

Nếu explicit close phải báo lỗi cho caller, thiết kế đường đóng tường minh sao cho lỗi được trả qua `close()` theo hợp đồng của tài nguyên. Cùng lúc đó, cần một state dùng chung để Cleaner không thực hiện release lần hai. Không che mất lỗi quan trọng chỉ bằng cách chuyển mọi thao tác đóng sang một Runnable không có kênh trả lỗi.

Với `AutoCloseable`, `close()` có thể khai báo exception phù hợp, ví dụ `IOException`. Try-with-resources sẽ giữ exception từ thân block làm exception chính và ghi nhận exception phát sinh trong `close()` dưới dạng suppressed exception khi cần. Hãy duy trì semantics này nếu wrapper quản lý tài nguyên Java có thao tác đóng có thể thất bại.

## 9. Threading và hiệu năng của cleanup action

Cleaning action tự động chạy trên thread do Cleaner quản lý; action gọi từ `Cleanable.clean()` chạy trong thread gọi phương thức. Do đó:

- Không giả định action luôn chạy trên một thread cố định.
- Không phụ thuộc thread-local, transaction context hoặc request context của thread tạo resource.
- Không block lâu, chờ vô hạn hoặc thực hiện công việc không liên quan trong action.
- Không giữ lock toàn cục trong thời gian dài; cleanup chậm có thể làm chậm các action khác dùng cùng Cleaner.
- Nếu release cần phối hợp với executor hoặc event loop, thiết kế việc chuyển giao có giới hạn và bảo đảm tài nguyên vẫn được giữ hợp lệ đến lúc release thực sự hoàn tất.

`Cleaner.create(ThreadFactory)` cho phép cung cấp cách tạo thread dọn dẹp khi có yêu cầu đặc biệt về đặt tên hoặc cấu hình thread. Hãy giữ thread dọn dẹp là daemon theo hợp đồng phù hợp của ứng dụng và không biến Cleaner thành một executor đa mục đích.

## 10. Cleaner và finalization

Không xây dựng quản lý tài nguyên mới dựa trên `finalize()`. Finalization là cơ chế cũ, có thời điểm chạy không xác định, khó dự đoán và đã bị deprecated để loại bỏ trong các phiên bản Java hiện đại.

`Cleaner` là API hiện hành cho cleanup dự phòng dựa trên reachability, nhưng nó cũng không bảo đảm thời điểm chạy. Khác biệt quan trọng là Cleaner dùng một cleaning action tách khỏi object được đăng ký và cho phép gọi `Cleanable.clean()` chủ động từ `close()`.

Không dùng `System.gc()` như một cách thay thế cho `close()`, và không viết test yêu cầu Cleaner phải chạy trong một khoảng thời gian ngắn sau khi bỏ reference.

## 11. Các lỗi thường gặp

- **Chỉ trông chờ Cleaner tự chạy:** cleanup có thể đến muộn; gọi `cleanable.clean()` từ `close()` và dùng try-with-resources.
- **Action giữ `this`:** object không thể trở nên phantom reachable; chuyển dữ liệu cleanup sang static nested state.
- **Tạo Cleaner riêng cho từng resource:** gây nhiều thread/overhead; thường dùng một Cleaner chung cho nhiều instance.
- **Cleanup không idempotent:** close lặp hoặc cạnh tranh có thể giải phóng handle nhiều lần; dùng one-time state.
- **Giả định action luôn chạy trên Cleaner thread:** explicit `clean()` chạy trên thread gọi; viết action an toàn với cả hai ngữ cảnh.
- **Block trong action:** có thể làm chậm các cleanup khác; giữ action ngắn và có timeout ở những thao tác có thể chờ.
- **Dùng Cleaner thay cho API đóng chính thức:** mất thời điểm cleanup xác định và có thể không báo lỗi cho caller.
- **Ép GC trong test:** `System.gc()` không bảo đảm action chạy; kiểm thử đường chủ động qua `close()` và `Cleanable.clean()`.
- **Không phối hợp `use()` với `close()`:** thao tác có thể truy cập tài nguyên sau release; định nghĩa hợp đồng thread-safety của wrapper.

## 12. Quy trình triển khai

1. Xác định tài nguyên bên ngoài heap mà wrapper sở hữu và API release tương ứng.
2. Cung cấp `close()` và triển khai `AutoCloseable` để caller có thể dùng try-with-resources.
3. Tạo hoặc dùng chung một `Cleaner` phù hợp với vòng đời ứng dụng.
4. Tách cleanup state thành static nested class; chỉ giữ handle và dữ liệu cần thiết, không giữ wrapper.
5. Đăng ký bằng `cleaner.register(this, state)` và lưu `Cleanable` trong wrapper.
6. Trong `close()`, gọi `cleanable.clean()` để thực thi cùng action ngay khi caller yêu cầu.
7. Bảo vệ release bằng one-time state; xác định cách xử lý exception và các thao tác use/close đồng thời.
8. Giữ action ngắn, không phụ thuộc thread-local và không block vô hạn.
9. Kiểm thử explicit close, close lặp, close cạnh tranh và hành vi sau khi resource đã đóng.
10. Không dựa vào GC để xác định thời điểm release; xem Cleaner là safety net cho trường hợp caller quên đóng.

Gọi `cleanable.clean()` từ `close()` kết hợp được cleanup chủ động, có thời điểm xác định với cơ chế dự phòng của Cleaner. Thiết kế đúng cần một cleanup state độc lập với wrapper, action idempotent và một hợp đồng `AutoCloseable` rõ ràng. Cleaner bảo vệ trường hợp caller quên đóng; try-with-resources vẫn là con đường chính để giải phóng tài nguyên đúng lúc.