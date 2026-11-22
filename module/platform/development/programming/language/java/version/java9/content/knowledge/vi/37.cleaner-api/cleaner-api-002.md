# Cleaner, Cleanable và hành động dọn dẹp

`Cleaner` được bổ sung trong Java 9 để đăng ký một hành động dọn dẹp sẽ được thực hiện khi một object trở nên *phantom reachable*. API này hữu ích làm cơ chế dự phòng cho tài nguyên nằm ngoài heap Java, chẳng hạn vùng nhớ native hoặc tài nguyên hệ thống mà ứng dụng tự quản lý.

`Cleaner` không thay thế `try-with-resources` hay `AutoCloseable`. Việc thu gom rác và chạy cleaner không có thời điểm xác định; ứng dụng cần giải phóng file, socket, lock hoặc tài nguyên có vòng đời rõ ràng phải chủ động đóng chúng. Mẫu an toàn là cung cấp `close()` để giải phóng ngay, đồng thời đăng ký `Cleaner` làm lớp bảo vệ cuối cùng nếu caller quên đóng.

## Mục tiêu

- Hiểu vai trò của `Cleaner`, `Cleaner.Cleanable` và cleaning action.
- Đăng ký một action bằng `Cleaner.register()`.
- Hiểu phantom reachability và thời điểm action có thể được chạy.
- Bảo đảm action không giữ tham chiếu mạnh tới object cần được dọn.
- Kết hợp `Cleaner` với `AutoCloseable` và try-with-resources.
- Dùng `Reference.reachabilityFence()` khi thao tác với tài nguyên native.
- Viết action ngắn, an toàn khi chạy trên cleaner thread và chỉ chạy một lần.
- Nhận biết các giới hạn của Cleaner và các lỗi thường gặp.

## 1. Các thành phần chính

`Cleaner` nằm trong package `java.lang.ref`. Một cleaner quản lý các đăng ký và thực thi cleaning action khi object đăng ký không còn reachable theo quy tắc phantom reachability.

| Thành phần | Vai trò |
| --- | --- |
| `Cleaner` | Quản lý đăng ký và chạy cleaning action |
| `Cleaner.Cleanable` | Handle đại diện cho một đăng ký; gọi `clean()` để yêu cầu dọn ngay |
| Cleaning action (`Runnable`) | Mã giải phóng tài nguyên, chạy tối đa một lần |
| Referent | Object được truyền vào `register()` và được theo dõi về reachability |

Đăng ký cơ bản:

~~~java
Cleaner cleaner = Cleaner.create();
Cleaner.Cleanable cleanable = cleaner.register(referent, cleanupAction);
~~~

`register()` trả về một `Cleaner.Cleanable`. Khi referent trở nên phantom reachable, cleaner có thể chạy action. Nếu ứng dụng gọi `cleanable.clean()` trước, action được chạy theo yêu cầu tường minh và đăng ký được xử lý; một lần dọn thứ hai không chạy lại action.

## 2. Cleaner hoạt động khi nào?

Cleaner dựa trên phantom reachability. Khi không còn strong reference hoặc các reference mạnh/yếu/soft phù hợp giữ object sống, object có thể tiến tới trạng thái phantom reachable. Cleaner phát hiện đăng ký tương ứng và lên lịch thực thi action.

~~~text
Object còn được tham chiếu mạnh
          |
          v
Không còn strong reference tới object
          |
          v
Object trở nên phantom reachable
          |
          v
Cleaner phát hiện đăng ký
          |
          v
Cleaning action được thực thi
~~~

Không thể dự đoán chính xác khi nào GC sẽ chạy hoặc khi nào cleaner thread sẽ thực thi action. `System.gc()` chỉ là yêu cầu/gợi ý cho runtime, không phải lệnh bảo đảm dọn ngay. Chương trình cũng không được giả định mọi action sẽ hoàn tất trước khi JVM thoát.

Cleaner mặc định sử dụng một daemon thread để xử lý các action. Daemon thread không giữ JVM sống chỉ để chờ dọn tài nguyên; nếu ứng dụng thoát, action chưa chạy có thể không được thực hiện. Vì vậy Cleaner chỉ là cơ chế dự phòng, không phải bảo đảm giải phóng đúng hạn.

## 3. Đăng ký action bằng register()

API:

~~~java
Cleaner.Cleanable register(Object obj, Runnable action)
~~~

`obj` là object cần theo dõi. `action` là `Runnable` được chạy khi object trở nên phantom reachable hoặc khi `Cleanable.clean()` được gọi.

~~~java
private static final Cleaner CLEANER = Cleaner.create();

private final Cleaner.Cleanable cleanable;

ResourceOwner() {
    State state = new State(nativeHandle);
    cleanable = CLEANER.register(this, state);
}
~~~

Thông thường nên dùng một Cleaner dùng chung cho nhiều object trong cùng phạm vi quản lý, thay vì tạo một Cleaner mới cho mỗi resource. Mỗi Cleaner có cơ chế thực thi action riêng; tạo quá nhiều cleaner làm tăng số luồng và chi phí quản lý không cần thiết.

## 4. Quy tắc quan trọng nhất: action không được giữ referent

Cleaning action không được tham chiếu mạnh trực tiếp hoặc gián tiếp tới object được đăng ký. Nếu action giữ referent sống, referent sẽ không bao giờ trở nên phantom reachable và action không được kích hoạt theo GC như mong đợi.

Ví dụ nguy hiểm:

~~~java
// Không nên: lambda có thể capture this.
cleanable = CLEANER.register(this, () -> releaseResource(this.handle));
~~~

Lambda trên giữ tham chiếu tới `this` để đọc `handle`. Cleaner giữ action; action lại giữ object; object vì thế không thể trở nên phantom reachable.

### 4.1. Tách trạng thái tài nguyên thành class static

Mẫu an toàn là đưa dữ liệu cần giải phóng vào một state object độc lập. State object không chứa owner và cleaning action chỉ giữ state đó.

~~~java
private static final class State implements Runnable {
    private final long nativeHandle;

    State(long nativeHandle) {
        this.nativeHandle = nativeHandle;
    }

    @Override
    public void run() {
        releaseNativeResource(nativeHandle);
    }
}

private final Cleaner.Cleanable cleanable;

ResourceOwner(long handle) {
    State state = new State(handle);
    cleanable = CLEANER.register(this, state);
}
~~~

`State` là nested class `static`, vì vậy nó không có tham chiếu ngầm tới instance bên ngoài. Action chỉ giữ state và handle tài nguyên cần giải phóng.

Tránh dùng non-static inner class cho action: mỗi instance của non-static inner class giữ tham chiếu ngầm tới object bao ngoài. Lambda tạo trong instance method cũng có thể capture `this`; hãy kiểm tra closure cẩn thận.

### 4.2. Action chỉ giữ dữ liệu cần để giải phóng

State có thể chứa native pointer, file descriptor hoặc một đối tượng quản lý tài nguyên độc lập. Nó không nên chứa:

- Tham chiếu tới owner/referent.
- Callback hoặc lambda capture owner.
- Một object khác có đường tham chiếu ngược về owner.
- Một collection hoặc context vô tình giữ owner.

Việc tách state cũng giúp action có thể chạy mà không cần gọi method instance trên object đã được thu gom.

## 5. Cleanable.clean(): dọn tường minh

`Cleaner.Cleanable.clean()` yêu cầu thực hiện cleaning action ngay. Nếu action được gọi do `clean()`, nó chạy đồng bộ trong thread gọi `clean()`. Action được thực thi tối đa một lần; gọi `clean()` thêm lần nữa không lặp lại việc giải phóng.

~~~java
public final class ResourceOwner implements AutoCloseable {
    private final Cleaner.Cleanable cleanable;

    @Override
    public void close() {
        cleanable.clean();
    }
}
~~~

Đây là cách tích hợp Cleaner với vòng đời tài nguyên tường minh. `close()` gọi `cleanable.clean()` để dùng chung một đường cleanup cho cả trường hợp caller chủ động đóng và trường hợp Cleaner phải dọn dự phòng.

Vì action chạy đồng bộ khi `clean()` được gọi, `close()` có thể mất thời gian bằng thời gian thực thi action. Không đưa thao tác block dài vào action.

## 6. Kết hợp AutoCloseable và try-with-resources

Với tài nguyên có thể đóng rõ ràng, lớp quản lý nên triển khai `AutoCloseable`. Caller sử dụng try-with-resources để bảo đảm `close()` được gọi ngay cả khi block ném exception.

~~~java
try (ResourceOwner resource = new ResourceOwner()) {
    resource.use();
}
~~~

Khi rời khỏi block, Java gọi `resource.close()`. Nếu `close()` gọi `cleanable.clean()`, action chạy ngay trong luồng hiện tại. Nếu caller không đóng object, Cleaner vẫn có thể chạy action sau khi referent trở nên phantom reachable.

### 6.1. Tránh giải phóng hai lần

Vì `Cleanable.clean()` chỉ kích hoạt action tối đa một lần, có thể dùng cùng một action cho cả explicit close và fallback cleanup. Nếu action có thể được gọi từ đường khác ngoài Cleanable, state nên tự bảo vệ thao tác giải phóng bằng cờ atomic hoặc cơ chế đồng bộ tương ứng.

Ví dụ:

~~~java
private static final class State implements Runnable {
    private final AtomicBoolean cleaned = new AtomicBoolean();

    @Override
    public void run() {
        if (cleaned.compareAndSet(false, true)) {
            releaseNativeResource();
        }
    }
}
~~~

Atomic guard giúp bảo đảm phần giải phóng chỉ thực hiện một lần nếu nhiều đường gọi có thể cùng yêu cầu cleanup. Chọn cách đồng bộ phù hợp với tài nguyên thật; không giả định `AtomicBoolean` tự làm cho mọi thao tác sử dụng tài nguyên khác trở nên an toàn khi đóng đồng thời.

## 7. Reference.reachabilityFence()

`Reference.reachabilityFence(obj)` được bổ sung trong Java 9. Nó bảo đảm `obj` vẫn strongly reachable ít nhất cho tới sau lời gọi fence.

Điều này quan trọng khi một method dùng native resource được quản lý bởi Cleaner. JIT có thể xem object không còn được dùng sau lần truy cập cuối cùng tới field, dù method vẫn đang thực hiện native operation. Nếu owner trở nên phantom reachable quá sớm, Cleaner có thể giải phóng native resource trong khi operation vẫn đang sử dụng nó.

Đặt fence trong `finally` sau lần sử dụng resource:

~~~java
void useNativeResource() {
    try {
        performNativeOperation(state.nativeHandle);
    } finally {
        Reference.reachabilityFence(this);
    }
}
~~~

Fence giữ owner reachable cho tới khi operation kết thúc, qua đó ngăn GC-triggered cleanup chạy quá sớm. Nó không thay thế synchronization và không ngăn một thread khác gọi `close()` tường minh. Nếu `use()` và `close()` có thể chạy đồng thời, lớp quản lý phải tự quy định và đồng bộ vòng đời đó.

## 8. Thiết kế cleaning action an toàn

Action thường chạy trên cleaner thread nếu được kích hoạt bởi GC. Vì vậy action cần:

- Hoàn thành nhanh và tránh chặn lâu.
- Không chờ một tác vụ khác cần cleaner thread để tiếp tục.
- Không gọi lại code có thể đăng ký hoặc chờ chính cleaner theo cách tạo deadlock.
- Không phụ thuộc vào trạng thái của object owner đã không còn reachable.
- Xử lý lỗi nội bộ và tránh để exception thoát khỏi action.
- Không truy cập UI, thread-local hoặc context gắn với thread đã tạo resource.

Nếu một action bị block, các action khác do cùng Cleaner quản lý có thể bị trì hoãn. Hãy giải phóng tài nguyên bằng thao tác ngắn; nếu cần quy trình shutdown phức tạp, hãy thực hiện bằng API close tường minh trước.

Cleaner không phải nơi thích hợp để chạy logic nghiệp vụ, gửi thông báo người dùng hoặc thực hiện công việc cần bảo đảm hoàn tất. Hãy giữ action ở mức giải phóng tài nguyên tối thiểu.

## 9. Cleaner và các cơ chế quản lý tài nguyên khác

| Cơ chế | Thời điểm thực thi | Dùng khi nào |
| --- | --- | --- |
| try-with-resources / `AutoCloseable` | Tại cuối block hoặc khi thoát block do exception | Tài nguyên cần giải phóng có thời điểm rõ ràng |
| `Cleanable.clean()` | Ngay trong thread gọi `clean()` | Caller chủ động yêu cầu cleanup |
| Cleaner sau phantom reachability | Không xác định; phụ thuộc GC và cleaner thread | Cơ chế dự phòng khi caller quên cleanup |
| `finally` | Khi luồng điều khiển rời khỏi try | Giải phóng hoặc hoàn nguyên thao tác đồng bộ trong một method |

Với file, socket, stream, JDBC connection và các API đã triển khai `AutoCloseable`, ưu tiên try-with-resources. Không tạo Cleaner chỉ để thay thế việc đóng những tài nguyên Java đã có vòng đời tường minh.

Cleaner hữu ích hơn khi lớp bọc sở hữu tài nguyên native hoặc tài nguyên không được GC quản lý trực tiếp, và cần một fallback để giảm nguy cơ rò rỉ nếu caller quên đóng.

## 10. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ sau dùng một Cleaner dùng chung. `State` là nested class static và không giữ tham chiếu tới `CleanerResourceDemo`. `close()` gọi `cleanable.clean()`; action chạy ngay và chỉ in thông báo giải phóng một lần. Ví dụ dùng một resource giả lập để kiểm tra lifecycle, không cấp phát native memory.

**Tệp:** `CleanerResourceDemo.java`

~~~java
import java.lang.ref.Cleaner;
import java.lang.ref.Reference;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CleanerResourceDemo implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final int id;
        private final AtomicBoolean cleaned = new AtomicBoolean();

        State(int id) {
            this.id = id;
        }

        void use() {
            if (cleaned.get()) {
                throw new IllegalStateException("resource is already cleaned");
            }
            System.out.println("using resource #" + id);
        }

        @Override
        public void run() {
            if (cleaned.compareAndSet(false, true)) {
                System.out.println("released resource #" + id);
            }
        }
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    CleanerResourceDemo(int id) {
        state = new State(id);
        cleanable = CLEANER.register(this, state);
    }

    void use() {
        try {
            state.use();
        } finally {
            Reference.reachabilityFence(this);
        }
    }

    @Override
    public void close() {
        cleanable.clean();
    }

    public static void main(String[] args) {
        try (CleanerResourceDemo resource = new CleanerResourceDemo(7)) {
            resource.use();
        }
        System.out.println("scope exited");
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~text
javac --release 9 CleanerResourceDemo.java
java CleanerResourceDemo
~~~

Output:

~~~text
using resource #7
released resource #7
scope exited
~~~

Giải thích:

1. `Cleaner.create()` tạo một Cleaner dùng chung.
2. Constructor tạo `State` độc lập rồi đăng ký `this` với state đó.
3. `use()` kiểm tra state và mô phỏng sử dụng tài nguyên.
4. `Reference.reachabilityFence(this)` giữ owner reachable cho tới khi thao tác use kết thúc.
5. Try-with-resources gọi `close()` khi thoát block.
6. `close()` gọi `cleanable.clean()`; action `State.run()` chạy đồng bộ và in `released resource #7`.
7. Cleaner bảo đảm action không chạy lặp lại nếu sau đó GC cũng phát hiện referent không còn reachable.

Ví dụ chủ động gọi `close()` nên output xác định. Không thêm `System.gc()` để mong chờ fallback cleanup trong test, vì thời điểm GC và cleaner thread không được bảo đảm.

## 11. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng Cleaner thay try-with-resources | Cleaner không có thời điểm chạy xác định | Dùng `AutoCloseable` và explicit close; Cleaner chỉ làm fallback |
| Action capture `this` | Cleaner giữ action, action giữ referent sống | Đưa handle vào state độc lập, thường là static nested class |
| Dùng non-static inner class làm action | Inner class giữ tham chiếu ngầm tới owner | Dùng static nested class |
| Tạo một Cleaner cho mỗi resource | Tăng số cleaner thread và chi phí quản lý | Dùng Cleaner dùng chung trong phạm vi phù hợp |
| Gọi `System.gc()` rồi giả định action chạy ngay | GC và cleaner thread không có lịch chạy xác định | Không dựa vào GC để đóng tài nguyên cần đúng hạn |
| Action thực hiện I/O hoặc chờ lâu | Có thể làm chậm các cleanup khác của cùng Cleaner | Giữ action ngắn, không block |
| Action ném exception | Cleanup khó quan sát và xử lý không đáng tin | Bắt/ghi nhận lỗi phù hợp bên trong action; không để exception thoát |
| Quên `cleanable.clean()` trong close | Explicit close không giải phóng theo yêu cầu | Cho `close()` gọi cùng action qua Cleanable |
| Dùng native handle sau khi object có thể bị thu gom | Owner có thể trở nên phantom reachable quá sớm | Dùng `Reference.reachabilityFence(this)` sau native operation |
| Nghĩ reachabilityFence ngăn explicit close | Fence chỉ bảo vệ reachability đối với GC | Đồng bộ `use()` và `close()` nếu có thể chạy đồng thời |
| Nghĩ Cleaner bảo đảm chạy trước khi JVM thoát | Cleaner thread là daemon | Không dùng Cleaner cho cleanup bắt buộc phải hoàn tất trước shutdown |

## 12. Quy tắc thực hành

1. Dùng try-with-resources và `AutoCloseable` làm đường giải phóng chính.
2. Dùng Cleaner làm fallback cho tài nguyên native hoặc tài nguyên do lớp tự quản lý.
3. Dùng một Cleaner dùng chung thay vì tạo Cleaner riêng cho từng object.
4. Đăng ký action bằng `register(referent, state)` sau khi state cleanup đã sẵn sàng.
5. Không để action giữ referent trực tiếp hoặc qua một object trung gian.
6. Dùng static nested state class để tránh capture owner ngầm.
7. Để `close()` gọi `cleanable.clean()` để explicit cleanup và fallback dùng chung một action.
8. Giữ action ngắn, no-throw và không block.
9. Dùng `Reference.reachabilityFence(this)` sau operation dùng native resource.
10. Tự đồng bộ nếu `close()` có thể cạnh tranh với operation đang sử dụng resource.
11. Không dựa vào `System.gc()` hoặc Cleaner để hoàn tất công việc có deadline.
12. Kiểm thử đường close tường minh; không viết test phụ thuộc vào thời điểm GC.

## 13. Tự kiểm tra

- Cleaner được bổ sung từ phiên bản Java nào? Java 9.
- `Cleaner.register()` nhận những gì? Referent và cleaning action (`Runnable`).
- `register()` trả về kiểu nào? `Cleaner.Cleanable`.
- Cleaner kích hoạt action tự động khi nào? Khi referent trở nên phantom reachable và cleaner thread xử lý đăng ký.
- Có thể dự đoán chính xác lúc action chạy do GC không? Không.
- `Cleanable.clean()` làm gì? Yêu cầu action chạy ngay; khi được gọi tường minh, action chạy đồng bộ và chỉ chạy tối đa một lần.
- Vì sao action không được giữ `this`? Vì action giữ referent sống, ngăn phantom reachability.
- Vì sao nên dùng static nested State? Để tránh tham chiếu ngầm tới owner.
- Cleaner có thay thế try-with-resources không? Không; cleanup xác định phải dùng explicit close.
- `Reference.reachabilityFence()` có tác dụng gì? Giữ object strongly reachable tới sau lời gọi fence.
- reachabilityFence có chặn thread khác gọi close không? Không.
- Cleaner có bảo đảm action chạy trước khi JVM thoát không? Không; cleaner thread mặc định là daemon.

Điểm cốt lõi: **Cleaner là cơ chế cleanup dự phòng dựa trên phantom reachability.** Dùng `AutoCloseable` để giải phóng tường minh, `Cleanable.clean()` để gọi action ngay, tách action khỏi referent và dùng `reachabilityFence()` khi thao tác với tài nguyên native.