# Reference.reachabilityFence để giữ đối tượng sống đủ lâu

**Reference.reachabilityFence(Object)** là API của Java 9 dùng để bảo đảm một đối tượng vẫn **strongly reachable** cho tới sau điểm gọi phương thức. Nó xử lý một tình huống tinh tế: JVM có thể xác định đối tượng không còn cần thiết trước khi method đang chạy kết thúc, vì vậy Cleaner có thể bắt đầu cleanup trong lúc method vẫn đang sử dụng tài nguyên gắn với đối tượng.

Trường hợp điển hình là wrapper Java quản lý tài nguyên ngoài heap như native handle, vùng nhớ off-heap hoặc tài nguyên hệ thống. Phần code dùng tài nguyên có thể vẫn đang chạy sau lần cuối cùng nó đọc field của wrapper. Gọi **Reference.reachabilityFence(this)** ở cuối vùng sử dụng giúp ngăn Cleaner xem wrapper là phantom reachable quá sớm.

API này kiểm soát thời điểm object có thể được thu hồi. Nó không thay thế close(), try-with-resources, lock hay cơ chế đồng bộ vòng đời tài nguyên.

## 1. Reachability và vòng đời đối tượng

Một đối tượng không nhất thiết còn sống chỉ vì một method được gọi trên nó chưa trả về. JVM được phép tối ưu dựa trên những lần sử dụng thực tế: khi không còn thao tác nào cần tham chiếu tới object, object có thể trở nên unreachable ngay cả khi stack frame của method vẫn tồn tại.

Ví dụ về hình dạng vấn đề:

~~~java
int read() {
    long address = state.nativeAddress();
    return nativeRead(address);
}
~~~

Sau khi lấy address, phần native call có thể vẫn đang sử dụng tài nguyên nhưng không còn đọc field nào của this. Nếu không còn strong reference nào khác tới wrapper, Cleaner có thể chạy cleanup và giải phóng native resource trước khi nativeRead hoàn tất.

Điểm quan trọng là **lexical scope không đồng nghĩa với object lifetime**. Biến cục bộ hoặc receiver chỉ được giữ sống tới lần sử dụng cuối cùng mà JVM cần, không nhất thiết tới dấu ngoặc đóng của method.

### Các mức reachability liên quan

Java phân biệt các mức reachability của đối tượng:

- **Strongly reachable:** có thể được truy cập từ computation đang tiếp diễn mà không cần đi qua referent của một Reference.
- **Softly reachable:** không còn strongly reachable nhưng vẫn được giữ bởi soft reference; GC có thể thu hồi tùy áp lực bộ nhớ.
- **Weakly reachable:** không còn strong/soft reachability và có weak reference trỏ tới; GC có thể clear weak reference.
- **Phantom reachable:** không còn strong, soft hoặc weak reachability và đã đủ điều kiện cho phantom reference/Cleaner xử lý.

Cleaner dựa trên phantom reachability. reachabilityFence(x) bảo đảm x vẫn strongly reachable cho tới sau lời gọi fence, do đó quá trình xử lý reference dựa trên việc x không còn reachable chưa thể xảy ra trước điểm đó.

## 2. Cú pháp và hợp đồng của reachabilityFence

Cú pháp:

~~~java
Reference.reachabilityFence(object);
~~~

Phương thức có kiểu trả về void, nhận một Object và được giới thiệu từ Java 9.

Hợp đồng chính:

1. Đối tượng được truyền vào vẫn strongly reachable ít nhất cho tới sau khi lời gọi reachabilityFence hoàn tất.
2. GC không thể thu hồi đối tượng hoặc clear/enqueue các reference tới nó trước điểm fence đó.
3. Các hành động trong thread trước lời gọi fence happens-before GC clear reference tới đối tượng.
4. Nếu đối số là null, phương thức không có tác dụng.
5. Phương thức không khởi chạy GC, không xử lý reference và không gọi cleaning action.

Có thể hiểu fence như một mốc cuối cùng mà tại đó chương trình nói với JVM: “đối tượng này vẫn cần sống tới đây”.

~~~text
đọc state / lấy native handle
             |
             v
       gọi native code
             |
             v
Reference.reachabilityFence(this)
             |
             v
method kết thúc; object mới có thể trở nên unreachable
nếu không còn strong reference nào khác
~~~

Fence chỉ bảo đảm reachability tới điểm gọi. Nó không giữ object sống vô thời hạn và không tự ngăn object được thu hồi sau khi method kết thúc.

## 3. Vì sao JVM có thể thu hồi object khi method chưa kết thúc?

JVM có thể tối ưu mã bằng cách nạp field sớm, lưu giá trị cần thiết vào biến cục bộ hoặc loại bỏ những lần sử dụng tham chiếu không còn cần thiết. Vì vậy, thời điểm object trở nên unreachable có thể sớm hơn điều mà người đọc suy ra từ phạm vi biến trong source code.

Một tình huống phổ biến:

~~~java
final class NativeBuffer {
    private final long address;

    NativeBuffer(long address) {
        this.address = address;
    }

    int readByte(int index) {
        long handle = address;
        return nativeRead(handle, index);
    }

    private static native int nativeRead(long handle, int index);
}
~~~

Sau khi lấy address, nativeRead chỉ nhận giá trị long. Nếu NativeBuffer là wrapper duy nhất giữ quyền sở hữu resource và không còn strong reference nào khác, object có thể trở nên unreachable trong lúc native call còn chạy.

Nếu Cleaner của wrapper giải phóng native handle, cleanup có thể chạy quá sớm. Cách sửa là giữ receiver sống qua toàn bộ thao tác sử dụng resource:

~~~java
int readByte(int index) {
    try {
        long handle = address;
        return nativeRead(handle, index);
    } finally {
        Reference.reachabilityFence(this);
    }
}
~~~

finally bảo đảm fence vẫn được gọi khi native method trả về bình thường hoặc ném exception. Fence được đặt sau thao tác dùng resource; đặt trước native call sẽ không bảo vệ khoảng thời gian native call đang chạy.

## 4. Kết hợp reachabilityFence với Cleaner

Cleaner là API cleanup dự phòng hiện hành cho đối tượng quản lý tài nguyên cần giải phóng khi wrapper không còn được sử dụng. Cleaner theo dõi object đã đăng ký bằng phantom reference và chạy một Runnable khi object trở thành phantom reachable.

Một thiết kế thường có ba phần:

- **Owner object:** API công khai mà ứng dụng sử dụng.
- **Cleanup state:** trạng thái độc lập chứa native handle hoặc thông tin cần để giải phóng resource.
- **Cleanable:** token do Cleaner.register(owner, state) trả về, cho phép cleanup tường minh.

Cleanup state không được giữ tham chiếu ngược tới owner. Nếu action hoặc lambda giữ owner, owner không bao giờ trở thành phantom reachable và cleanup tự động sẽ không xảy ra.

Ví dụ cấu trúc:

~~~java
private static final Cleaner CLEANER = Cleaner.create();

private static final class State implements Runnable {
    // Chỉ giữ native handle và dữ liệu cleanup cần thiết.
}

private final State state;
private final Cleaner.Cleanable cleanable;

Resource() {
    state = new State(...);
    cleanable = CLEANER.register(this, state);
}
~~~

State là static nested class để không vô tình giữ tham chiếu tới instance bên ngoài. Với lambda, cần kiểm tra capture: chỉ cần lambda truy cập field của owner là có thể giữ owner sống mãi.

### Cleaner không thay thế close()

Cleanup do GC phát hiện phantom reachability là bất đồng bộ và không có thời hạn thực thi cố định. Không được dựa vào Cleaner để giải phóng file, socket, lock hoặc native memory đúng một thời điểm nghiệp vụ.

Cách dùng chính vẫn là:

~~~java
try (Resource resource = new Resource()) {
    resource.perform();
}
~~~

close() nên gọi cleanable.clean() để giải phóng tường minh. Cleaner chỉ là lớp dự phòng nếu caller quên đóng. Cleaning action được gọi tối đa một lần; action nên ngắn, không block và xử lý lỗi nội bộ vì exception từ action bị bỏ qua bởi Cleaner.

## 5. Đặt fence ở đâu?

Nguyên tắc là đặt fence **sau lần sử dụng cuối cùng của resource**, không phải ngay sau lần đọc field đầu tiên.

~~~java
int perform() {
    try {
        return useNativeHandle(state.handle());
    } finally {
        Reference.reachabilityFence(this);
    }
}
~~~

finally chạy trên cả đường trả về bình thường lẫn đường ném exception. Nếu method có nhiều nhánh return hoặc callback, phải bảo đảm mọi đường thực thi cần giữ object đều đi qua fence.

Nếu callback được gọi đồng bộ và callback đang dùng resource, fence phải nằm sau khi callback hoàn tất. Nếu callback được lên lịch bất đồng bộ rồi method trả về ngay, fence trong method hiện tại không giữ object sống tới lúc callback chạy; cần truyền một strong reference vào task hoặc dùng một cơ chế ownership/lifecycle riêng.

Không cần gọi fence cho mọi object hoặc mọi method. Chỉ dùng khi việc object bị thu hồi sớm có thể gây hiệu ứng nhìn thấy được, chẳng hạn Cleaner đóng resource trong khi code còn đang dùng resource. Với object heap thông thường không quản lý resource bên ngoài, reachabilityFence thường không cần thiết.

## 6. Ví dụ Java chạy được: Cleaner và reachabilityFence

Ví dụ dưới đây mô phỏng wrapper giữ một resource ngoài heap. State độc lập với owner, Cleaner đăng ký state làm cleanup action, read() đặt fence sau thao tác sử dụng và close() cho phép giải phóng tường minh.

~~~java
import java.lang.ref.Cleaner;
import java.lang.ref.Reference;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ReachabilityFenceExample implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class NativeState implements Runnable {
        private final int value;
        private final AtomicBoolean released = new AtomicBoolean();

        NativeState(int value) {
            this.value = value;
        }

        int read() {
            if (released.get()) {
                throw new IllegalStateException("resource is closed");
            }
            return value;
        }

        @Override
        public void run() {
            if (released.compareAndSet(false, true)) {
                System.out.println("resource released");
            }
        }
    }

    private final NativeState state;
    private final Cleaner.Cleanable cleanable;

    public ReachabilityFenceExample(int value) {
        this.state = new NativeState(value);
        this.cleanable = CLEANER.register(this, state);
    }

    public int read() {
        try {
            return state.read();
        } finally {
            Reference.reachabilityFence(this);
        }
    }

    @Override
    public void close() {
        cleanable.clean();
    }

    public static void main(String[] args) {
        try (ReachabilityFenceExample resource =
                new ReachabilityFenceExample(42)) {
            System.out.println("value=" + resource.read());
        }
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -Xlint:all ReachabilityFenceExample.java
java ReachabilityFenceExample
~~~

Kết quả stdout chính xác:

~~~text
value=42
resource released
~~~

Giải thích:

1. Constructor tạo NativeState, sau đó đăng ký owner cùng cleanup action với Cleaner.
2. NativeState là static nested class và không tham chiếu tới ReachabilityFenceExample.
3. read() dùng state trước, sau đó gọi Reference.reachabilityFence(this) trong finally.
4. Fence bảo đảm owner chưa thể trở thành phantom reachable trong lúc state.read() đang chạy.
5. Khi try-with-resources kết thúc, close() gọi cleanable.clean() và cleanup action chạy tường minh. Vì vậy output của ví dụ xác định, không phụ thuộc thời điểm GC.

NativeState ở đây mô phỏng trạng thái native resource bằng một số nguyên. Trong thư viện native thật, state thường giữ handle/pointer và action gọi hàm giải phóng tương ứng. Nếu API cho phép close() đồng thời với read() từ thread khác, cần thêm lock hoặc protocol lifecycle để phối hợp explicit close với thao tác đang sử dụng resource. reachabilityFence chỉ ngăn cleanup do object trở nên unreachable; nó không chặn một thread khác gọi cleanable.clean().

Ví dụ dùng try-with-resources nên cleanup được gọi tường minh. Nó xác nhận cú pháp, thứ tự sử dụng và cleanup; không cố kiểm thử thời điểm GC tự chạy Cleaner vì thời điểm đó không được bảo đảm.

## 7. Quan hệ với happens-before và cleanup

reachabilityFence có memory consistency effect riêng: mọi hành động trong thread trước lời gọi fence happens-before GC clear reference tới đối tượng đó.

Khi kết hợp với Cleaner, chuỗi ordering này giúp cleanup action nhìn thấy các cập nhật trạng thái đã xảy ra trước fence. Điều này hữu ích nếu cleanup state chứa bookkeeping được cập nhật trong lúc resource được sử dụng.

Tuy nhiên, fence không phải lock:

- Nó không bảo vệ một nhóm field khỏi cập nhật đồng thời.
- Nó không làm thao tác read/modify/write trở thành nguyên tử.
- Nó không đồng bộ explicit close() với một thao tác đang chạy.
- Nó không thay thế volatile, synchronized, Lock hoặc Atomic class khi các thread cùng sửa trạng thái.

Nếu nhiều thread cùng sử dụng hoặc đóng resource, cần một giao thức concurrency riêng. Fence chỉ giải quyết thời điểm object có thể mất strong reachability do GC.

## 8. Khi nào cần và khi nào không cần?

| Tình huống | Cần reachabilityFence? |
|---|---|
| Wrapper giữ native handle; method dùng handle sau lần đọc field cuối | Có thể cần |
| Cleaner có thể giải phóng resource khi owner phantom reachable | Có thể cần |
| Method đang dùng resource và có thể kết thúc bằng exception | Đặt trong finally nếu cần |
| Object heap thông thường, không có cleanup/reference processing quan sát được | Thường không |
| Object còn được sử dụng rõ ràng sau thao tác resource | Thường không cần thêm fence |
| Muốn ngăn thread khác gọi close() trong lúc read() | Không; cần lock/lifecycle coordination |
| Muốn kích hoạt GC hoặc Cleaner ngay lập tức | Không; fence không làm việc đó |
| Muốn giữ object sống sau khi method kết thúc | Không; cần giữ một strong reference thực sự |

## 9. Các lỗi thường gặp

- **Nghĩ rằng object luôn sống tới khi method kết thúc:** JVM có thể xem object không còn cần thiết sau lần sử dụng cuối, dù method chưa return.
- **Đặt fence trước native call:** object có thể trở nên unreachable trong chính khoảng native call đang sử dụng resource.
- **Đặt fence sau một nhánh nhưng bỏ sót nhánh khác:** đường exception hoặc return khác có thể không đi qua fence.
- **Dùng fence để giữ object sống mãi:** fence chỉ giữ tới sau invocation của nó.
- **Nghĩ fence gọi GC hoặc Cleaner:** nó chỉ thiết lập reachability ordering; không khởi chạy cleanup.
- **Cleanup action giữ owner:** Cleaner không thể quan sát owner phantom reachable nếu action giữ strong reference tới owner.
- **Dùng non-static inner class làm cleanup state:** inner class giữ tham chiếu ngầm tới instance bên ngoài.
- **Dùng Cleaner làm cơ chế đóng tài nguyên đúng hạn:** cleanup tự động không có deadline; ưu tiên AutoCloseable và try-with-resources.
- **Cho rằng fence ngăn explicit close từ thread khác:** fence không thay thế lock hoặc protocol đóng tài nguyên.
- **Giả định Cleaner action luôn chạy trước khi tiến trình thoát:** không có bảo đảm cleanup action hoàn tất khi System.exit xảy ra.
- **Cho cleanup action block lâu:** một action block có thể trì hoãn các action khác của cùng Cleaner.
- **Coi ví dụ gọi System.gc() là kiểm thử chắc chắn:** GC không được bảo đảm chạy ngay; kiểm thử đúng nên dùng close tường minh cho kết quả xác định.

## 10. Tài liệu tham khảo chính thức

- [Reference.reachabilityFence — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ref/Reference.html): hợp đồng strongly reachable, thời điểm clear/enqueue, memory consistency effects và ví dụ đặt fence trong finally.
- [Cleaner — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ref/Cleaner.html): đăng ký cleanup action, phantom reachability, Cleanable.clean và yêu cầu không giữ tham chiếu owner.
- [AutoCloseable — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng đóng tài nguyên và tích hợp với try-with-resources.