# Đăng ký trạng thái dọn dẹp không giữ tham chiếu tới đối tượng với `Cleaner`

`java.lang.ref.Cleaner` được giới thiệu trong Java 9 để đăng ký một hành động dọn dẹp sẽ được thực hiện khi đối tượng được đăng ký trở nên *phantom reachable*. API này hữu ích khi một object đại diện cho tài nguyên ngoài heap, chẳng hạn native handle, file descriptor do thư viện native quản lý hoặc vùng nhớ ngoài JVM.

Điều kiện quan trọng nhất là **cleanup action và toàn bộ trạng thái mà nó giữ không được tham chiếu ngược tới object được đăng ký**. Nếu action giữ object đó trực tiếp hoặc gián tiếp, object không thể trở nên phantom reachable và Cleaner sẽ không thể kích hoạt cleanup theo cơ chế tự động.

Trong ứng dụng hiện đại, hãy giải phóng tài nguyên một cách tường minh bằng `AutoCloseable` và `try-with-resources`. `Cleaner` đóng vai trò dự phòng khi caller quên đóng object; không dùng nó làm cơ chế quản lý vòng đời tài nguyên chính.

## 1. Cleaner quản lý vòng đời cleanup như thế nào?

`Cleaner` quản lý các object được đăng ký cùng cleanup action tương ứng. Khi object được đăng ký trở nên phantom reachable, Cleaner có thể chạy action trên thread dọn dẹp của nó.

Vòng đời tổng quát:

1. Tạo hoặc dùng một Cleaner dùng chung.
2. Tạo trạng thái dọn dẹp độc lập với object sở hữu tài nguyên.
3. Gọi `cleaner.register(referent, action)` và giữ lại `Cleaner.Cleanable`.
4. Khi cần giải phóng tường minh, gọi `cleanable.clean()`.
5. Nếu caller không gọi `clean()`, Cleaner có thể chạy action sau khi referent trở nên phantom reachable.
6. Action chỉ được thực hiện tối đa một lần cho registration đó; lần gọi `clean()` tiếp theo không giải phóng lại tài nguyên.

```text
Resource object
     |
     | register(this, cleanupState)
     v
Cleaner.Cleanable -----> cleanupState
     |                       |
     | clean()               | chỉ giữ resource handle
     | hoặc referent         | và dữ liệu độc lập
     | phantom reachable     v
     +-----------------> release resource
```

`Cleaner` mặc định dùng daemon thread để xử lý các action tự động. Vì thread này không giữ JVM sống, ứng dụng không được dựa vào Cleaner để bảo đảm tài nguyên chắc chắn được giải phóng trước khi tiến trình kết thúc.

## 2. Vì sao cleanup action không được giữ referent?

Khi gọi:

```java
Cleaner.Cleanable cleanable = cleaner.register(resource, action);
```

Cleaner cần chờ `resource` không còn được tham chiếu mạnh, yếu hoặc mềm và trở nên phantom reachable. Nếu cleanup action giữ một tham chiếu mạnh đến chính `resource`, chuỗi tham chiếu sẽ giống như:

```text
Cleaner
   |
   v
cleanup action
   |
   v
resource (referent)
```

Cleaner vẫn giữ action để có thể chạy nó, action lại giữ resource, nên resource không thể trở nên phantom reachable. Cleanup action sẽ không được kích hoạt tự động.

### Những cách vô tình giữ referent

- Lambda dùng `this`, ví dụ `() -> release(this.handle)`, vì lambda capture object hiện tại.
- Method reference như `this::release`, vì method reference giữ receiver.
- Non-static inner class, vì instance của inner class giữ tham chiếu ngầm đến instance outer.
- Một state object có field `owner`, `resource` hoặc callback đóng kín tham chiếu đến object cần dọn dẹp.
- Một collection hoặc listener được cleanup action giữ mà trong đó có tham chiếu ngược đến referent.

Giải pháp đơn giản là dùng **static nested class** làm cleanup state. Static nested class không có tham chiếu ngầm đến instance bên ngoài. Chỉ đưa vào state những dữ liệu độc lập cần thiết để giải phóng tài nguyên, chẳng hạn native handle, file descriptor hoặc địa chỉ vùng nhớ.

## 3. Tách cleanup state khỏi object sở hữu tài nguyên

Một thiết kế phổ biến có ba thành phần:

- `Resource`: object mà ứng dụng sử dụng và đăng ký với Cleaner.
- `CleanupState`: trạng thái độc lập, triển khai `Runnable`, chỉ giữ dữ liệu cần thiết để giải phóng tài nguyên.
- `Cleaner.Cleanable`: registration handle dùng để yêu cầu cleanup tường minh.

Ví dụ cấu trúc:

```java
private static final Cleaner CLEANER = Cleaner.create();

private static final class CleanupState implements Runnable {
    private final AtomicLong resourceId;

    CleanupState(long resourceId) {
        this.resourceId = new AtomicLong(resourceId);
    }

    @Override
    public void run() {
        long id = resourceId.getAndSet(0);
        if (id != 0) {
            releaseResource(id);
        }
    }
}
```

`CleanupState` là static và chỉ giữ một resource ID độc lập. Nó không có field trỏ tới `Resource`, không nhận `Resource` trong constructor và không gọi method instance của `Resource`.

`AtomicLong.getAndSet(0)` lấy handle và chuyển state sang giá trị đã đóng trong một thao tác nguyên tử. Nếu `close()` và Cleaner cùng cố gắng chạy action, chỉ một bên lấy được handle khác `0`; tài nguyên do đó chỉ được giải phóng một lần. Ví dụ dùng `0` làm sentinel, nên trong ứng dụng thật cần chọn sentinel phù hợp với loại handle; nếu `0` là giá trị hợp lệ, hãy dùng một cờ trạng thái riêng.

## 4. Đăng ký với `Cleaner.register`

Phương thức đăng ký:

```java
Cleaner.Cleanable register(Object obj, Runnable action);
```

`obj` là referent cần theo dõi; `action` là hành động được thực hiện khi cleanup xảy ra. Phương thức trả về `Cleanable` để caller có thể chủ động dọn dẹp.

Ví dụ:

```java
CleanupState state = new CleanupState(nativeHandle);
Cleaner.Cleanable cleanable = CLEANER.register(this, state);
```

Giữ `Cleanable` trong object sở hữu tài nguyên để `close()` có thể gọi `cleanable.clean()`. Cleaner giữ registration và cleanup state cần thiết, nhưng cleanup state phải độc lập với referent.

Không tạo một Cleaner mới cho từng resource. `Cleaner.create()` tạo bộ quản lý và daemon thread riêng; thông thường dùng một Cleaner tĩnh dùng chung cho lớp hoặc cho nhóm tài nguyên có cùng chính sách.

## 5. `Cleanable.clean()` và cleanup idempotent

`Cleaner.Cleanable` cung cấp phương thức:

```java
void clean();
```

Gọi `clean()` sẽ yêu cầu thực hiện cleanup action và loại bỏ registration. Action chỉ được chạy tối đa một lần, kể cả khi:

- Caller gọi `close()` nhiều lần.
- Cleaner đã bắt đầu cleanup tự động.
- Caller gọi `clean()` sau khi cleanup đã hoàn tất.

Vì vậy, `close()` nên idempotent: gọi một lần hay nhiều lần đều không giải phóng tài nguyên hai lần và không làm object chuyển sang trạng thái không hợp lệ ngoài hợp đồng đã định.

Cleanup state vẫn nên tự bảo vệ bằng atomic flag hoặc cơ chế đồng bộ thích hợp. Điều này đặc biệt quan trọng khi cleanup action có thể cạnh tranh với thao tác đóng tường minh hoặc với các thao tác sử dụng resource.

## 6. Ví dụ hoàn chỉnh: Resource dùng Cleaner mà không giữ referent

Chương trình sau mô phỏng một native resource bằng ID. `CleanupState` là static nested class, chỉ giữ ID và `AtomicLong`; nó không tham chiếu đến object `Resource`. `Resource.close()` gọi `Cleanable.clean()` để giải phóng ngay lập tức và an toàn khi được gọi nhiều lần.

```java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicLong;

public class Main {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class CleanupState implements Runnable {
        private final AtomicLong resourceId;

        CleanupState(long resourceId) {
            this.resourceId = new AtomicLong(resourceId);
        }

        @Override
        public void run() {
            long id = resourceId.getAndSet(0);
            if (id != 0) {
                releaseResource(id);
            }
        }
    }

    private static final class Resource implements AutoCloseable {
        private final CleanupState state;
        private final Cleaner.Cleanable cleanable;

        Resource(long resourceId) {
            state = new CleanupState(resourceId);
            cleanable = CLEANER.register(this, state);
        }

        long id() {
            long id = state.resourceId.get();
            if (id == 0) {
                throw new IllegalStateException("resource is closed");
            }
            return id;
        }

        boolean isClosed() {
            return state.resourceId.get() == 0;
        }

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    private static void releaseResource(long resourceId) {
        System.out.println("released resource: " + resourceId);
    }

    public static void main(String[] args) {
        Resource resource = new Resource(73);
        System.out.println("resource id: " + resource.id());
        resource.close();
        resource.close();
        System.out.println("closed: " + resource.isClosed());
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Stdout chính xác:

```text
resource id: 73
released resource: 73
closed: true
```

Action chỉ in ra thông báo để mô phỏng giải phóng native resource. Trong ứng dụng thực tế, thay `releaseResource` bằng lời gọi giải phóng tài nguyên phù hợp; phần cleanup state vẫn chỉ giữ handle hoặc dữ liệu độc lập, không giữ `Resource`.

## 7. Kết hợp với `AutoCloseable` và try-with-resources

`Cleaner` không thay thế việc đóng tài nguyên tường minh. Khi tài nguyên có vòng đời rõ ràng, triển khai `AutoCloseable` và dùng `try-with-resources`: 

```java
try (Resource resource = new Resource(73)) {
    System.out.println("using resource: " + resource.id());
}
```

Khi rời khỏi khối `try`, Java tự gọi `close()`. Trong thiết kế ở trên, `close()` gọi `cleanable.clean()`, nên cleanup xảy ra ngay tại thời điểm đóng. Nếu caller quên đóng và object sau đó trở nên phantom reachable, Cleaner là lớp dự phòng.

Cách kết hợp này đem lại hai đường cleanup:

- **Đường chính:** `close()` hoặc `try-with-resources` giải phóng tài nguyên một cách xác định.
- **Đường dự phòng:** Cleaner xử lý trường hợp object bị bỏ quên và cuối cùng trở nên phantom reachable.

Không gọi `System.gc()` để cố ép cleanup trong logic ứng dụng. Yêu cầu GC chỉ là gợi ý và không bảo đảm object được thu gom hoặc cleanup action chạy tại một thời điểm cụ thể.

## 8. Thread thực thi cleanup action

Cleanup action có thể được kích hoạt bởi Cleaner thread khi referent trở nên phantom reachable, hoặc bởi thread gọi `Cleanable.clean()` khi caller chủ động cleanup.

Vì vậy, cleanup action cần được thiết kế để chạy an toàn trong nhiều ngữ cảnh:

- Không giả định nó chạy trên UI thread, request thread hoặc thread tạo resource.
- Không truy cập trạng thái mutable của referent.
- Không phụ thuộc vào thứ tự cleanup giữa các resource khác nhau.
- Tránh chặn lâu, chờ vô hạn hoặc thực hiện I/O kéo dài; một action chậm có thể trì hoãn các cleanup khác trên Cleaner thread.
- Không để exception thoát khỏi action như một cơ chế báo lỗi cho caller; cleanup tự động không phải kênh xử lý lỗi nghiệp vụ.
- Bảo đảm thao tác giải phóng an toàn khi được gọi sau một lần đóng tường minh.

Nếu việc đóng tài nguyên có thể thất bại và caller cần xử lý lỗi, hãy thực hiện thao tác đó trong `close()` theo hợp đồng `AutoCloseable`. Cleaner chỉ là phương án dự phòng; không dựa vào nó để trả lỗi về nơi đã tạo resource.

## 9. Cleanup state và đồng bộ khi resource được dùng đồng thời

Ví dụ trên bảo đảm lấy và giải phóng handle tối đa một lần, nhưng một resource thực tế có thể được dùng trên nhiều thread. Khi đó, thao tác sử dụng resource và thao tác close cần có quy tắc đồng bộ rõ ràng.

Ví dụ race cần xử lý:

1. Thread A đọc handle để bắt đầu thao tác native.
2. Thread B gọi `close()` và giải phóng handle.
3. Thread A tiếp tục dùng handle đã được giải phóng.

`AtomicLong.getAndSet(0)` ngăn giải phóng lặp, nhưng tự nó không bảo đảm một thao tác đang chạy không bị giải phóng tài nguyên giữa chừng. Tùy API native, cần dùng lock, reference counting, lease hoặc cơ chế retain/release để bảo đảm resource còn sống trong suốt thao tác.

Không giữ lock của object referent trong cleanup action nếu action có thể chạy sau khi object đã không còn được truy cập bình thường. Đặt dữ liệu đồng bộ cần thiết trong cleanup state độc lập và thiết kế thứ tự lock để tránh deadlock.

## 10. Tạo Cleaner với ThreadFactory tùy chỉnh

`Cleaner.create()` dùng cấu hình mặc định. API cũng cho phép truyền `ThreadFactory` khi cần kiểm soát cách tạo thread xử lý cleanup:

```java
ThreadFactory factory = task -> {
    Thread thread = new Thread(task, "resource-cleaner");
    thread.setDaemon(true);
    return thread;
};

Cleaner cleaner = Cleaner.create(factory);
```

Thread xử lý cleanup nên là daemon để không giữ JVM sống chỉ vì các registration còn tồn tại. Thread factory tùy chỉnh cần tạo thread có cấu hình phù hợp; không dùng Cleaner thread cho công việc ứng dụng thông thường.

## 11. Kiểm thử Cleaner đúng cách

Không nên viết kiểm thử phụ thuộc vào thời điểm GC. Thay vào đó, kiểm thử hành vi xác định qua `Cleanable.clean()`:

1. Tạo resource và xác nhận handle có thể sử dụng.
2. Gọi `close()` và xác nhận cleanup state đã chuyển sang closed.
3. Gọi `close()` lần nữa và xác nhận release chỉ xảy ra một lần.
4. Gọi `id()` sau khi đóng và xác nhận API từ chối sử dụng resource đã đóng.
5. Kiểm tra cleanup state không có field hoặc callback giữ referent.
6. Kiểm tra try-with-resources gọi cleanup khi thoát scope.
7. Với resource dùng đa luồng, kiểm tra race giữa use và close bằng cơ chế đồng bộ thực tế của resource.

Không dùng `Thread.sleep()` hoặc `System.gc()` làm bằng chứng rằng Cleaner đã chạy. GC có thể trì hoãn tùy áp lực bộ nhớ, collector và trạng thái runtime.

## 12. Lỗi thường gặp

1. **Cleanup action capture `this`.** Action giữ object được đăng ký nên object không thể trở nên phantom reachable.
2. **Dùng non-static inner class làm cleanup state.** Instance inner class giữ tham chiếu ngầm tới outer object.
3. **Gọi method instance của Resource từ action.** Việc này thường buộc action giữ referent; chuyển thao tác giải phóng sang hàm static nhận handle độc lập.
4. **Tạo một Cleaner cho mỗi object.** Điều này tạo nhiều bộ quản lý và daemon thread không cần thiết; dùng Cleaner dùng chung.
5. **Chỉ dựa vào Cleaner để đóng file hoặc socket.** Thời điểm GC không xác định; dùng `AutoCloseable` và try-with-resources cho đường chính.
6. **Không giữ `Cleanable`.** Nếu không giữ registration handle, object sở hữu không thể chủ động gọi cleanup qua `close()`.
7. **Cleanup không idempotent.** Close tường minh và cleanup tự động có thể cạnh tranh; dùng atomic state để chỉ giải phóng một lần.
8. **Cleanup action chặn lâu.** Một action chậm có thể làm chậm các action khác; chỉ thực hiện công việc giải phóng cần thiết.
9. **Giả định Cleaner thread giữ JVM sống.** Cleaner thread mặc định là daemon; tiến trình có thể kết thúc trước khi cleanup dự phòng chạy.
10. **Dùng `System.gc()` để điều khiển vòng đời.** GC không bảo đảm thời điểm chạy; không dùng nó thay cho close tường minh.
11. **Cho rằng atomic close bảo vệ mọi thao tác đồng thời.** Cần đồng bộ cả thời gian sử dụng resource, không chỉ thao tác giải phóng.
12. **Để cleanup state giữ object gián tiếp.** Kiểm tra cả collection, callback, listener và object lồng nhau, không chỉ field trực tiếp.

## 13. Ghi nhớ

1. `Cleaner` được giới thiệu trong Java 9 và chạy cleanup action khi referent trở nên phantom reachable.
2. Cleanup action và toàn bộ state mà nó giữ không được tham chiếu trực tiếp hoặc gián tiếp tới referent.
3. Dùng static nested cleanup state chỉ chứa native handle hoặc dữ liệu độc lập cần để giải phóng.
4. `Cleaner.register(referent, action)` trả về `Cleaner.Cleanable`; giữ nó để hỗ trợ cleanup tường minh.
5. `Cleanable.clean()` cho phép đóng ngay và action chỉ được thực hiện tối đa một lần.
6. Triển khai `AutoCloseable`; ưu tiên `close()` và try-with-resources, dùng Cleaner làm phương án dự phòng.
7. Cleanup action có thể chạy trên Cleaner daemon thread hoặc thread gọi `clean()`; không giả định thread cụ thể.
8. Dùng atomic state để chống giải phóng lặp, đồng thời thiết kế đồng bộ riêng cho thao tác sử dụng resource.
9. Không dựa vào `System.gc()` hoặc Cleaner để bảo đảm thời điểm giải phóng tài nguyên.