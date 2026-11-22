# Vai trò của acquireFence, releaseFence và fullFence

Java 9 bổ sung các memory fence methods vào **VarHandle** trong package **java.lang.invoke**. Ba phương thức **acquireFence()**, **releaseFence()** và **fullFence()** đặt ranh giới về thứ tự quan sát của các thao tác đọc/ghi bộ nhớ. Chúng hữu ích trong thuật toán đồng thời cấp thấp, nơi cần kiểm soát việc sắp xếp các memory access mà không nhất thiết dùng một thao tác volatile cho từng biến.

Fence không đọc, ghi hay cập nhật một biến cụ thể. Nó đặt ràng buộc về việc các thao tác bộ nhớ ở trước và sau ranh giới có thể được quan sát theo thứ tự nào. Vì vậy, cần hiểu đúng hướng của từng fence và kết hợp nó với một cơ chế giao tiếp giữa các thread.

## 1. Memory fence giải quyết vấn đề gì?

Trong mã nguồn, các câu lệnh xuất hiện theo một thứ tự. Tuy nhiên, compiler và CPU có thể sắp xếp lại một số thao tác đọc/ghi nếu việc đó không làm thay đổi hành vi mà chương trình đơn luồng được phép quan sát. Trên nhiều lõi CPU, cache và bộ xử lý cũng ảnh hưởng đến thời điểm các thay đổi được quan sát bởi thread khác.

Java Memory Model (JMM) quy định những kết quả nào một chương trình đa luồng được phép quan sát. Các cơ chế như **synchronized**, **volatile**, các access mode của VarHandle và memory fence đặt ra những ràng buộc để chương trình không phụ thuộc vào một thứ tự thực thi tình cờ.

Một memory fence tạo ranh giới giữa các nhóm memory access:

- Các thao tác trước fence phải tuân theo những ràng buộc thứ tự do fence quy định.
- Các thao tác sau fence không được quan sát như thể đã vượt qua ranh giới theo hướng bị cấm.
- Fence không thay thế phép đọc/ghi dữ liệu và không tự thực hiện thao tác cập nhật nguyên tử.

Ba phương thức được hỏi đều là static method, không nhận tham số và trả về void:

~~~java
VarHandle.acquireFence();
VarHandle.releaseFence();
VarHandle.fullFence();
~~~

Chúng có từ Java 9 và vẫn là API hiện hành.

## 2. acquireFence(): ranh giới theo hướng acquire

**VarHandle.acquireFence()** bảo đảm rằng các phép đọc (loads) trước fence không bị sắp xếp lại với các phép đọc và ghi (loads và stores) sau fence.

Có thể hiểu theo hướng sử dụng: sau khi thread đã quan sát một tín hiệu hoặc trạng thái chia sẻ, acquire fence đặt ranh giới để những thao tác bộ nhớ tiếp theo không bị đưa lên trước các phép đọc đã xảy ra trước fence.

Ví dụ về vị trí đặt fence sau khi đọc tín hiệu:

~~~java
int signal = (int) READY.getOpaque();

if (signal == 1) {
    VarHandle.acquireFence();
    int value = payload;
}
~~~

Ở đây getOpaque() đọc biến báo hiệu. Nếu thread quan sát được giá trị 1, acquire fence đặt ranh giới trước khi đọc payload.

Acquire fence không tự tìm hay đọc tín hiệu. Chương trình phải thực hiện một thao tác đọc trước đó để biết khi nào áp dụng ranh giới. Fence cũng không làm một phép đọc trở thành atomic operation.

Nếu chỉ cần đọc một biến bằng acquire semantics, **VarHandle.getAcquire()** thường rõ ràng và dễ dùng hơn:

~~~java
int signal = (int) READY.getAcquire();
~~~

getAcquire() gắn ordering với chính phép đọc biến READY, trong khi acquireFence() cho phép đặt một ranh giới sau một nhóm thao tác đọc đã thực hiện.

## 3. releaseFence(): ranh giới theo hướng release

**VarHandle.releaseFence()** bảo đảm rằng các phép đọc và ghi trước fence không bị sắp xếp lại với các phép ghi sau fence.

Theo cách sử dụng thường gặp, thread chuẩn bị công bố dữ liệu trước, đặt release fence, rồi mới ghi tín hiệu để thread khác biết dữ liệu đã sẵn sàng:

~~~java
payload = 42;
VarHandle.releaseFence();
READY.setOpaque(1);
~~~

Release fence đặt ranh giới giữa những thao tác chuẩn bị dữ liệu và phép ghi tín hiệu phía sau. Nhờ đó, các thao tác đọc/ghi trước fence không bị đưa qua sau phép ghi công bố theo hướng bị cấm.

Release fence không tự ghi tín hiệu. Lệnh READY.setOpaque(1) trong ví dụ là thao tác ghi báo hiệu; fence đặt ordering giữa thao tác đó và các truy cập bộ nhớ trước nó.

Nếu chỉ cần công bố một giá trị qua một biến, **VarHandle.setRelease()** thường đơn giản hơn:

~~~java
READY.setRelease(1);
~~~

setRelease() kết hợp phép ghi và release semantics trong cùng một access mode. Release fence hữu ích hơn khi cần đặt một ranh giới chung cho nhiều thao tác trước một phép ghi tiếp theo, thay vì gắn ordering vào từng biến riêng lẻ.

## 4. fullFence(): ranh giới đầy đủ cho loads và stores

**VarHandle.fullFence()** đặt ràng buộc mạnh hơn cho cả hai phía của ranh giới: các phép đọc và ghi trước fence không bị sắp xếp lại với các phép đọc và ghi sau fence.

~~~java
updateState();
VarHandle.fullFence();
validateOrPublishState();
~~~

Có thể dùng full fence khi thuật toán cần ranh giới bao quát cả load-load, load-store, store-load và store-store giữa các thao tác ở hai phía. Nó thường xuất hiện trong các cấu trúc đồng thời cấp thấp, thuật toán lock-free hoặc cơ chế cần một thứ tự toàn cục mạnh hơn acquire/release.

API note của Java mô tả memory-ordering effect của fullFence() là tương thích với atomic_thread_fence(memory_order_seq_cst) của C++, đồng thời nhắc rằng hai ngôn ngữ có nhiều khác biệt về ngữ nghĩa. Vì vậy, không nên coi hai API là hoàn toàn đồng nhất.

Full fence không khóa thread, không bảo đảm mutual exclusion và không biến một chuỗi phép ghi thành một phép cập nhật nguyên tử. Nó chỉ đặt ràng buộc thứ tự bộ nhớ theo đặc tả.

## 5. So sánh ba phương thức

| Phương thức | Ràng buộc chính thức | Hướng sử dụng điển hình |
|---|---|---|
| acquireFence() | Loads trước fence không bị reorder với loads và stores sau fence | Sau khi đọc/quan sát tín hiệu, trước khi đọc dữ liệu liên quan |
| releaseFence() | Loads và stores trước fence không bị reorder với stores sau fence | Sau khi chuẩn bị dữ liệu, trước khi ghi tín hiệu công bố |
| fullFence() | Loads và stores trước fence không bị reorder với loads và stores sau fence | Khi thuật toán cần ranh giới đầy đủ cho cả đọc và ghi |

Có thể hình dung:

~~~text
Thread công bố dữ liệu                 Thread nhận dữ liệu

payload = 42                           signal = READY.getOpaque()
releaseFence()                         nếu signal == 1:
READY.setOpaque(1)                         acquireFence()
                                            đọc payload
~~~

Cặp release/acquire tạo ordering cho các thao tác liên quan đến quá trình công bố và quan sát dữ liệu. fullFence() áp dụng ràng buộc rộng hơn, bao gồm cả các phép đọc ở hai phía.

## 6. Fence khác gì setRelease(), getAcquire() và volatile?

VarHandle cung cấp cả fence methods lẫn access modes. Chúng có liên hệ về memory ordering nhưng có cách sử dụng khác nhau:

| Cách làm | Ordering gắn với | Khi nên cân nhắc |
|---|---|---|
| setRelease() | Một phép ghi qua VarHandle | Công bố một giá trị hoặc tín hiệu |
| getAcquire() | Một phép đọc qua VarHandle | Đọc tín hiệu và bảo đảm ordering cho thao tác sau |
| releaseFence() | Ranh giới giữa các access trước và các store sau | Nhiều thao tác trước một lần công bố |
| acquireFence() | Ranh giới giữa các load trước và access sau | Nhiều lần đọc trước một bước kiểm tra hoặc xử lý |
| fullFence() | Tất cả loads/stores ở hai phía | Thuật toán cần ordering toàn diện hơn |
| volatile | Các lần đọc/ghi volatile của biến | Trạng thái chia sẻ thông thường cần release/acquire và thứ tự volatile |

Trong code ứng dụng thông thường, hãy ưu tiên **volatile**, **synchronized**, các lớp **java.util.concurrent** hoặc access mode **setRelease() / getAcquire()** khi chúng đáp ứng yêu cầu. Fence phù hợp khi cần điều khiển thứ tự trên một nhóm memory access, chẳng hạn đọc nhiều trường rồi mới xác thực một trạng thái hoặc chuẩn bị nhiều trường trước một lần công bố.

Các access mode của VarHandle quyết định semantics của lần truy cập. Khi trộn plain, opaque, acquire, release và volatile trên cùng biến, cần hiểu rõ ordering của từng access; không nên giả định rằng khai báo volatile tự động nâng mọi cách truy cập VarHandle lên volatile semantics.

## 7. Kết hợp fence với một tín hiệu giao tiếp giữa các thread

Fence không phải một tín hiệu liên thread. Nó không tự mang giá trị từ thread ghi sang thread đọc. Muốn một thread biết dữ liệu đã sẵn sàng, chương trình vẫn cần một biến hoặc thao tác giao tiếp mà thread kia có thể quan sát.

Một cách dùng fence tường minh là kết hợp release/acquire fence với Opaque access trên cùng biến báo hiệu:

**Thread ghi:**

~~~java
payload = 42;
VarHandle.releaseFence();
READY.setOpaque(1);
~~~

**Thread đọc:**

~~~java
if ((int) READY.getOpaque() == 1) {
    VarHandle.acquireFence();
    int value = payload;
}
~~~

Trong ví dụ:

- payload chứa dữ liệu cần công bố.
- READY là VarHandle trỏ đến biến báo hiệu.
- setOpaque() và getOpaque() cung cấp access có tính nhất quán/coherence trên chính biến READY.
- releaseFence() đặt ordering giữa các thao tác chuẩn bị dữ liệu và phép ghi báo hiệu.
- acquireFence() đặt ordering giữa phép đọc báo hiệu và các thao tác đọc/ghi tiếp theo.

Opaque access tự nó không đặt ordering cho các biến khác. Fence bổ sung ordering giữa các truy cập ở hai phía. Nếu bỏ fence hoặc thay thao tác Opaque bằng plain access mà không có cơ chế đồng bộ phù hợp, không thể mặc định rằng dữ liệu được công bố an toàn.

Trong trường hợp đơn giản, cách viết sau thường dễ hiểu hơn và ít rủi ro hơn:

~~~java
// Thread ghi
payload = 42;
READY.setRelease(1);

// Thread đọc
if ((int) READY.getAcquire() == 1) {
    int value = payload;
}
~~~

Cặp setRelease()/getAcquire() gắn ordering trực tiếp với biến báo hiệu. Hãy chọn fence tường minh khi thuật toán thực sự cần đặt một ranh giới bao phủ nhiều thao tác.

## 8. Ví dụ hoàn chỉnh: công bố dữ liệu bằng releaseFence và acquireFence

Lưu chương trình dưới tên **MemoryFenceDemo.java**. Ví dụ dùng một biến báo hiệu được truy cập bằng Opaque mode và đặt hai fence ở đúng phía của thao tác công bố/quan sát.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class MemoryFenceDemo {
    private static int payload;
    private static int ready;
    private static final VarHandle READY;

    static {
        try {
            READY = MethodHandles.lookup().findStaticVarHandle(
                    MemoryFenceDemo.class, "ready", int.class);
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        int[] observed = {-1};

        Thread reader = new Thread(() -> {
            while ((int) READY.getOpaque() == 0) {
                Thread.onSpinWait();
            }
            VarHandle.acquireFence();
            observed[0] = payload;
        });

        Thread writer = new Thread(() -> {
            payload = 42;
            VarHandle.releaseFence();
            READY.setOpaque(1);
        });

        reader.start();
        writer.start();
        writer.join(5000);
        reader.join(5000);

        if (writer.isAlive() || reader.isAlive()) {
            throw new IllegalStateException("message publication timed out");
        }
        if (observed[0] != 42) {
            throw new AssertionError("unexpected payload: " + observed[0]);
        }

        VarHandle.fullFence();
        System.out.println("payload observed after acquire fence: " + observed[0]);
        System.out.println("release/acquire publication: successful");
        System.out.println("full fence invoked: true");
    }
}
~~~

Biên dịch và chạy trên Java 9 trở lên:

~~~bash
javac --release 9 MemoryFenceDemo.java
java MemoryFenceDemo
~~~

Kết quả stdout:

~~~text
payload observed after acquire fence: 42
release/acquire publication: successful
full fence invoked: true
~~~

Chương trình kiểm tra một lần công bố dữ liệu giữa hai thread. Thread.onSpinWait() chỉ là gợi ý cho CPU trong vòng lặp chờ; nó không tạo synchronization. Trong ứng dụng thực tế, nếu không cần một thuật toán polling cấp thấp, hãy cân nhắc CountDownLatch, Semaphore, BlockingQueue, lock hoặc các cơ chế đồng bộ cấp cao.

Lệnh fullFence() ở cuối chương trình chỉ minh họa rằng API có thể được gọi; nó không tham gia vào cặp công bố/đọc dữ liệu đã hoàn tất.

## 9. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đặt releaseFence() sau phép ghi tín hiệu | Ranh giới không còn đứng giữa dữ liệu và lần công bố | Đặt release fence trước phép ghi công bố |
| Đặt acquireFence() trước khi đọc tín hiệu | Không tạo ranh giới sau thao tác quan sát tín hiệu | Đọc tín hiệu trước, acquire fence sau khi đã nhận điều kiện cần |
| Nghĩ fence tự ghi hoặc đọc dữ liệu | Không có biến nào được cập nhật hoặc trả về | Dùng một access mode hoặc thao tác giao tiếp đi cùng |
| Nghĩ fence làm thao tác trở thành atomic | Không loại bỏ race condition hay bảo đảm mutual exclusion | Dùng CAS, atomic update, lock hoặc cơ chế phù hợp |
| Dùng plain flag để truyền tín hiệu giữa thread | Plain access không bảo đảm ordering liên thread cần thiết | Dùng access mode Opaque/Release/Acquire hoặc volatile phù hợp |
| Dùng fullFence() ở mọi nơi | Áp đặt ordering mạnh hơn mức cần thiết, làm giảm cơ hội tối ưu | Chọn acquire/release hoặc access mode cụ thể nếu đủ |
| Trộn nhiều access mode trên cùng biến mà không có quy tắc | Có thể tạo hành vi khó phân tích theo JMM | Xác định rõ mode cho từng lần đọc/ghi và giữ giao thức nhất quán |
| Cho rằng fence luôn sinh cùng một lệnh CPU | Hiệu ứng triển khai phụ thuộc JVM và kiến trúc | Dựa vào đặc tả Java, không dựa vào giả định về một CPU cụ thể |

## 10. Ghi nhớ

- acquireFence() ngăn loads trước fence bị reorder với loads và stores sau fence.
- releaseFence() ngăn loads và stores trước fence bị reorder với stores sau fence.
- fullFence() ngăn loads và stores ở hai phía bị reorder với nhau.
- Ba phương thức là static method của VarHandle, có từ Java 9 và trả về void.
- Fence đặt ordering; nó không tự đọc, ghi, cập nhật nguyên tử hay khóa một biến.
- Kết hợp fence với thao tác giao tiếp phù hợp nếu cần công bố dữ liệu giữa các thread.
- setRelease() và getAcquire() thường là lựa chọn dễ hiểu hơn khi ordering gắn với một biến báo hiệu.
- Dùng fullFence() khi thuật toán thật sự cần ordering đầy đủ; không thay thế nó cho lock hoặc atomic operation.
- Các memory fence methods vẫn là API hiện hành; không cần dùng API nội bộ như Unsafe cho nội dung này.

## Tài liệu tham khảo

- [VarHandle — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/VarHandle.html)
- [VarHandle — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Using JDK 9 Memory Order Modes — Doug Lea](https://gee.cs.oswego.edu/dl/html/j9mm.html)
- [Java Language Specification, Chapter 17: Threads and Locks](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-17.html)
