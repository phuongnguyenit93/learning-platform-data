# Chờ công việc bất đồng bộ kết thúc trước khi trả vùng đệm hoặc handle

Trong Java native interoperability (JNI, Foreign Function & Memory API – FFM, thư viện C/C++, thiết bị hoặc driver), lời gọi **bắt đầu** thao tác bất đồng bộ thường kết thúc trước khi thao tác native thực sự ngừng dùng tài nguyên. Vì vậy, thời điểm phương thức Java trả về **không đồng nghĩa** với thời điểm có thể giải phóng, đóng hoặc trả vùng đệm/handle về pool.

**Mục tiêu:** xác định đúng vòng đời tài nguyên; nhận biết tín hiệu hoàn tất thực sự; phối hợp giữa Java và native; xử lý nhiều công việc đồng thời, lỗi, timeout và hủy mà không gây use-after-free hoặc rò rỉ.

## 1. Phân biệt thao tác, tài nguyên và quyền sở hữu

- **Buffer/vùng đệm:** địa chỉ off-heap do FFM Arena hoặc malloc cấp, DirectByteBuffer mà native có thể lấy địa chỉ, vùng nhớ dùng cho I/O/DMA, hoặc bộ nhớ do thư viện native trả về.
- **Handle:** định danh hoặc con trỏ đại diện cho một tài nguyên native như request, session, stream, file, socket, bộ giải mã hoặc GPU command queue; có thể phải gọi close/release/free riêng.
- **In-flight operation:** công việc đã được chấp nhận hoặc gửi đi nhưng vẫn có khả năng đọc/ghi buffer, dùng handle hay phát callback. Một lệnh submit có thể tạo nhiều công việc nội bộ.
- **Owner:** thành phần chịu trách nhiệm giải phóng tài nguyên. Phải biết tài nguyên do Java hay native sở hữu, được mượn, được chuyển quyền sở hữu hay đã được sao chép.
- **Quiescence (ngừng sử dụng):** trạng thái đã có bảo đảm không còn worker, DMA, completion callback hoặc đường xử lý native nào được phép truy cập tài nguyên cần giải phóng.

Nguyên tắc quản lý vòng đời:

> **Chỉ close/free/recycle khi mọi công việc có quyền dùng tài nguyên đã thực sự kết thúc và API native bảo đảm không còn truy cập nó nữa.** Nếu native nhận bản sao độc lập thì có thể giải phóng bản gốc sớm hơn, nhưng chỉ khi tài liệu API khẳng định việc sao chép đã hoàn tất.

Đây là vấn đề **lifetime/ownership**, không đơn thuần là việc gọi phương thức chờ của Java.

## 2. Vì sao trả tài nguyên ngay sau submit là lỗi?

Giả sử thư viện C cung cấp thao tác bất đồng bộ writeAsync(pointer, size, callback) và chỉ trả về trạng thái **đã nhận yêu cầu**:

~~~text
Sai:
t0 Java cấp buffer tại địa chỉ p
t1 Java gọi nativeWriteAsync(p) → trả về "accepted"
t2 Java free(p), Arena.close() hoặc trả buffer về pool
t3 native worker/DMA tiếp tục đọc p          ← use-after-free
t4 callback báo kết quả (nếu chương trình chưa lỗi)

Đúng:
t0 cấp buffer/handle
t1 submit công việc native; giữ nguyên owner và lifetime
t2 chờ tín hiệu completion có nghĩa "không còn dùng p/handle"
t3 xử lý kết quả và bảo đảm không còn callback truy cập tài nguyên
t4 close/free/recycle đúng một lần
~~~

Nếu vùng nhớ vừa giải phóng được cấp lại cho request khác, lỗi có thể biểu hiện thành dữ liệu sai, tiết lộ dữ liệu giữa request, lỗi ngẫu nhiên hoặc JVM crash. Kiểm tra phạm vi truy cập của **MemorySegment** từ Java không thể bảo vệ thao tác C đang dùng một con trỏ thô đã bị giải phóng.

**Trả buffer về pool cũng nguy hiểm như free:** request mới có thể ghi đè vùng đang được native đọc, dù địa chỉ vẫn hợp lệ.

## 3. Đọc hợp đồng completion của thư viện native trước khi viết wrapper

Đừng suy đoán ý nghĩa tên callback hay giá trị trả về. Các mốc sau rất khác nhau:

| Mốc | Điều đã biết | Có thể giải phóng buffer/handle? |
| --- | --- | --- |
| submit trả về | Native đã nhận hoặc từ chối yêu cầu | **Chưa**, trừ khi API đã sao chép toàn bộ dữ liệu và nói rõ |
| queued/enqueued | Công việc nằm trong hàng đợi | **Chưa** |
| I/O completed / device event signaled | Một tầng công việc đã xong | **Chỉ nếu** hợp đồng bảo đảm mọi tầng đều ngừng dùng tài nguyên |
| callback hoàn tất thực sự | Thư viện xác nhận operation quiesced | **Có**, sau khi các callback/người dùng khác cũng không còn truy cập |
| close/abort request hoàn tất | Thư viện xác nhận đã hủy, drain và ngừng mọi truy cập | **Có**, theo thứ tự giải phóng được tài liệu quy định |

Các câu hỏi bắt buộc khi tích hợp một API:

1. Submit có **copy input** hay chỉ giữ **pointer**? Output buffer còn được viết sau khi submit trả về không?
2. Callback được gọi **trước, đúng lúc hay sau** lần truy cập cuối? Sau callback có callback phụ hoặc worker nào còn dùng handle không?
3. Khi báo lỗi, timeout hoặc cancel, thư viện có bảo đảm **operation đã ngừng** chưa?
4. Có thể có nhiều request chia sẻ một buffer/handle không? Có thể submit request mới trong lúc close không?
5. Phải gọi release request, unmap, unregister callback, close handle và free buffer theo **thứ tự nào**?

Không tìm được lời hứa rõ ràng về quiescence thì không thể suy ra thời điểm free chỉ từ một **CompletableFuture** do chính wrapper tự tạo.

## 4. Mẫu an toàn cơ bản: submit → completion thực → cleanup

Wrapper lý tưởng tách hai khái niệm:

- **Kết quả nghiệp vụ:** thành công, lỗi, bị hủy theo yêu cầu, hoặc hết thời gian chờ của caller.
- **Tín hiệu an toàn để giải phóng (noMoreNativeAccess / quiesced):** chỉ hoàn tất khi native cam kết không còn dùng tài nguyên, kể cả các nhánh xử lý lỗi và hủy.

Quy trình:

1. Cấp phát buffer và khởi tạo handle; ghi nhận ai là owner.
2. Submit request khi tài nguyên còn sống. Native giữ tham chiếu, quyền dùng hoặc bản sao theo hợp đồng.
3. Theo dõi request bằng callback, completion queue, event, wait function hoặc native request handle. Mỗi cơ chế cần tạo được tín hiệu **quiesced** đáng tin.
4. Ngừng nhận request mới vào handle sắp đóng và chờ mọi request đang chạy đạt quiescence.
5. Lấy kết quả, giải phóng từng request theo đúng API, sau đó release buffer/handle một lần; giải phóng toàn bộ cả khi có lỗi.
6. Hoàn tất Future cung cấp cho caller và thông báo lỗi phù hợp. Nếu Future caller được phép cancel/timeout sớm thì giữ **tín hiệu quiesced nội bộ tách biệt**, không dùng Future đó làm điều kiện free.

Quan hệ cần đúng là:

~~~text
mọi lần sử dụng cuối của native
            ↓
      native quiesced
            ↓
    Java thấy completion
            ↓
     close/free/recycle
~~~

Một Future chỉ an toàn khi nhà cung cấp bảo đảm nó đại diện đúng mốc **native quiesced**, không chỉ mốc “đã xếp hàng”, “đã yêu cầu hủy” hoặc “đã có kết quả cho UI”.

## 5. Java 17+: ví dụ runnable minh họa chờ trước khi đóng handle

Ví dụ sau mô phỏng một native worker bằng thread Java để kiểm chứng thứ tự vòng đời; lớp **NativeHandle** không phải binding JNI thật. Tín hiệu **completion** được phát **sau lần truy cập cuối** vào handle. Trong dự án thật, thay phần mô phỏng bằng callback hoặc wait native có hợp đồng quiescence tương đương.

**File: AsyncHandleLifecycle.java**

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AsyncHandleLifecycle {
    static final class NativeHandle implements AutoCloseable {
        private boolean released;

        synchronized int read() {
            if (released) throw new IllegalStateException("released");
            return 7;
        }

        @Override
        public synchronized void close() {
            released = true;
            System.out.println("handle released");
        }
    }

    static CompletableFuture<Integer> submitSimulatedNativeWork(
            NativeHandle handle, ExecutorService worker) {
        CompletableFuture<Integer> completion = new CompletableFuture<>();
        worker.execute(() -> {
            try {
                int result = handle.read() * 6;
                // Từ đây worker không còn đọc/ghi handle.
                completion.complete(result);
            } catch (RuntimeException ex) {
                completion.completeExceptionally(ex);
            }
        });
        return completion;
    }

    public static void main(String[] args) {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (NativeHandle handle = new NativeHandle()) {
            CompletableFuture<Integer> completed =
                    submitSimulatedNativeWork(handle, worker);
            System.out.println("result=" + completed.join());
        } finally {
            worker.shutdown();
        }
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac AsyncHandleLifecycle.java
java AsyncHandleLifecycle
~~~

Stdout:

~~~text
result=42
handle released
~~~

**Vì sao thứ tự đúng?** **join()** đợi Future của tác vụ mô phỏng hoàn tất; worker đã thực hiện lần truy cập cuối **trước** khi gọi **completion.complete(...)**. Khi thoát khối **try-with-resources**, handle mới được đóng. Đây là bài mô phỏng vòng đời, **không chứng minh** callback của một thư viện C tùy ý đã thực sự ngừng dùng con trỏ; phải xác minh hợp đồng API đó.

Nếu tác vụ báo lỗi sau lần truy cập cuối, **join()** ném **CompletionException**, nhưng **try-with-resources** vẫn gọi close. Điều này chỉ an toàn khi **cả completion thành công lẫn completion lỗi đều được phát sau quiescence**. Trong ví dụ, không có đường gọi **cancel()** khiến Future hoàn tất sớm.

## 6. FFM từ Java 22: giữ Arena sống qua tác vụ trên thread khác

FFM API chính thức có trong **java.lang.foreign** từ JDK 22. **Arena** quyết định vòng đời bộ nhớ off-heap do nó cấp; đóng Arena làm mất hiệu lực các MemorySegment liên kết và giải phóng vùng native backing.

- **Arena.ofConfined():** truy cập MemorySegment qua Java chỉ từ owner thread. Không chuyển MemorySegment sang một Java worker khác để đọc/ghi.
- **Arena.ofShared():** nhiều Java thread có thể truy cập segment; tuy vậy, vẫn phải tự phối hợp khi chúng ghi/đọc chung dữ liệu. Shared **không** có nghĩa là tự động chờ native worker dừng.
- **Arena.ofAuto()** hoặc **Arena.global()** không thay thế một quy trình close đúng lúc cho tài nguyên native cần giải phóng xác định.

Ví dụ dưới đây chạy trên JDK 22+, dùng **Arena.ofShared()** vì tác vụ Java bất đồng bộ sử dụng segment ở thread khác. Đây vẫn là **mô phỏng công việc native**, nhằm cho thấy chỗ đặt điểm chờ:

**File: ForeignMemoryWait.java**

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.CompletableFuture;

public class ForeignMemoryWait {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment buffer = arena.allocate(ValueLayout.JAVA_INT);
            CompletableFuture<Integer> operation =
                    CompletableFuture.supplyAsync(() -> {
                        buffer.set(ValueLayout.JAVA_INT, 0, 42);
                        return buffer.get(ValueLayout.JAVA_INT, 0);
                    });

            int result = operation.join(); // chờ xong trước khi đóng Arena
            System.out.println("result=" + result);
        }
        System.out.println("arena closed");
    }
}
~~~

Chạy:

~~~bash
javac ForeignMemoryWait.java
java ForeignMemoryWait
~~~

Stdout:

~~~text
result=42
arena closed
~~~

Đối với lời gọi FFM downcall bất đồng bộ thực tế, cần kiểm tra xem thư viện native có **lưu địa chỉ** để dùng sau khi downcall trả về hay không. Hàng rào kiểm tra lifetime của **MemorySegment** áp dụng cho các thao tác được FFM quản lý; nó **không phát hiện được** native C đang truy cập con trỏ đã lưu ngoài Java. Chỉ đóng Arena sau tín hiệu quiescence thực của native. Nếu thư viện giữ lại callback/upcall stub hoặc user-data pointer, phạm vi sống của chính chúng cũng phải kéo dài đến lúc native ngừng gọi.

## 7. JNI, DirectByteBuffer và callback từ native thread

Với JNI, native thường lấy địa chỉ từ **GetDirectBufferAddress** hoặc giữ **jobject** để gọi callback muộn hơn. Cần phân biệt hai loại lifetime:

| Đối tượng | Quy tắc |
| --- | --- |
| DirectByteBuffer Java | Giữ Java object sống trong suốt thời gian native sử dụng backing memory; một địa chỉ thô riêng lẻ không bảo đảm object còn sống |
| JNI local reference | Chỉ hợp lệ trong native method/frame và thread thích hợp; không giữ qua lúc native method trả về |
| JNI global reference | Dùng **NewGlobalRef** nếu native phải giữ đối tượng Java/callback qua nhiều lời gọi; **DeleteGlobalRef** khi đã hết callback |
| JNIEnv* | Có tính thread-local; native worker cần gắn thread với JVM trước khi gọi JNI và bỏ gắn đúng cách khi kết thúc |
| Native malloc pointer / handle | Giải phóng bằng đúng allocator hoặc API cung cấp, sau khi các worker và callback đã ngừng dùng |

**Không giữ một JNI local reference làm callback state dài hạn.** Nếu C lưu callback Java để gọi lại ở thread khác, tạo global reference theo hợp đồng JNI, quản lý việc gắn thread, và chỉ xóa global reference sau lần callback cuối. Không tự giải phóng DirectByteBuffer bằng địa chỉ thu được từ GetDirectBufferAddress: quyền sở hữu backing memory cần được xác định riêng; nếu là vùng memory external do native cấp thì dùng đúng API release của owner.

Cẩn thận với callback: một số thư viện gọi callback khi callback nội bộ vẫn đang chạy hoặc khi worker còn bước dọn dẹp cuối. Nếu wrapper close handle **ngay trong callback** nhưng native tiếp tục tham chiếu nó sau khi callback trả về, đây vẫn là use-after-free. Hãy dựa trên hợp đồng “callback xong thì không còn access”, hoặc dùng yêu cầu drain/join riêng rồi mới free.

## 8. Nhiều request dùng chung buffer hoặc handle

Với các request r1, r2, … cùng dùng một handle, chỉ được close khi **tất cả** đã đạt quiescence. Nếu mỗi request cung cấp một tín hiệu **không thể bị hủy sớm** và hoàn tất sau lần native access cuối, có thể ghép chúng:

~~~java
// Minh họa trong phương thức quản lý tài nguyên; không phải chương trình độc lập.
CompletableFuture<Void> allQuiesced = CompletableFuture.allOf(
        request1.noMoreNativeAccess(),
        request2.noMoreNativeAccess(),
        request3.noMoreNativeAccess());

try {
    allQuiesced.join();
} finally {
    nativeHandle.close();
}
~~~

**Điều kiện:** ba tín hiệu trên phản ánh đúng completion native (kể cả đường lỗi/cancel). Nếu **join()** ném ngoại lệ, **allOf** vẫn chỉ hoàn tất khi mọi future đầu vào đã hoàn tất; khối finally an toàn khi từng future đầu vào chỉ hoàn tất sau quiescence. Nếu một future bị **cancel()** để báo timeout sớm, điều kiện này bị phá vỡ: **không** dùng nó để giải phóng.

Trong hệ thống động, chờ một danh sách snapshot là chưa đủ nếu request mới vẫn được submit. Dùng một **lifecycle gate**:

~~~text
OPEN: cho phép nhận request mới; tăng số in-flight trước khi submit
       ↓ close được yêu cầu
DRAINING: chặn mọi submit mới; đợi in-flight về 0 sau tín hiệu native quiesced
       ↓
CLOSED: free buffer/close handle một lần
~~~

Phải đồng bộ việc chuyển **OPEN → DRAINING** với thao tác đăng ký request, tránh race “thread A thấy số in-flight = 0 và close, thread B vừa submit request mới”. Có thể dùng lock, state machine với atomic/CAS đúng đắn, hoặc cơ chế reference counting của thư viện. Nếu C có request handle riêng, giải phóng từng request theo thứ tự API yêu cầu; handle cha chỉ đóng khi mọi request con đã drain.

## 9. Timeout, cancel, lỗi và shutdown: mốc quan trọng nhất

- **CompletableFuture.cancel(true)** chỉ đổi trạng thái Future; bản thân CompletableFuture **không** dùng interrupt để dừng công việc. Với native I/O, GPU, DMA hay C worker, càng không có bảo đảm đã dừng.
- **orTimeout(...)**, **completeOnTimeout(...)**, **Future.get(timeout, ...)** hoặc việc thread Java bị interrupt chỉ cho biết caller hết chờ hoặc Future bị hoàn tất theo chính sách. **Không suy ra** native không còn dùng buffer.
- Khi timeout: trả lỗi/timeout cho caller nếu cần, yêu cầu **nativeCancel(request)** theo hợp đồng, nhưng tiếp tục giữ buffer/handle cho đến khi có **cancel acknowledgement hoặc terminal completion xác nhận quiescence**.
- Khi native báo lỗi hoặc completion callback ném ngoại lệ: chuyển trạng thái request vào luồng cleanup, không bỏ quên decrement in-flight và giải phóng reference; đảm bảo callback chỉ đánh dấu quiesced **một lần**.
- Khi shutdown: chặn request mới, yêu cầu hủy hoặc drain các request cũ, đợi tín hiệu native kết thúc, sau đó đóng request handle, buffer, parent handle và executor theo thứ tự. Nếu API không hỗ trợ cancel an toàn, phải giữ tài nguyên đến khi operation kết thúc hoặc chấp nhận cô lập/quản lý theo vòng đời process thay vì free sớm.

Một cách tổ chức hữu ích là hai Future khác nhau: **resultForCaller** có thể timeout/cancel, còn **nativeQuiesced** chỉ do sự kiện hoàn tất thực của native giải quyết và được giữ kín trong lớp quản lý resource. **Không cho consumer bên ngoài complete/cancel nativeQuiesced**. Native có thể báo hủy thành công về mặt nghiệp vụ nhưng vẫn cần thêm bước drain trước khi free.

## 10. Đồng bộ dữ liệu và thread safety

Chờ completion giải quyết **lifetime**; nó chưa tự giải quyết mọi race dữ liệu.

- Java thread A ghi input rồi submit native: bảo đảm native nhìn thấy dữ liệu đã ghi theo cách mà API giao tiếp quy định (memory barrier, fence, pin/map, đồng bộ driver hoặc các phép truy cập đồng bộ thích hợp).
- Native hoàn tất ghi output: cần bảo đảm dữ liệu được công bố tới Java trước khi Java đọc. Trật tự callback/Future trong Java **không thể tùy tiện thay thế** yêu cầu bộ nhớ/thiết bị trong hợp đồng C/driver.
- Shared Arena cho phép Java threads truy cập segment, nhưng không tự biến các đọc/ghi cùng địa chỉ thành atomic hoặc không có data race.
- Không dùng một vùng đệm mutable cho hai request chồng lấn trừ khi có phân vùng, đồng bộ hoặc thư viện bảo đảm an toàn.

Khi thiết kế wrapper, hãy ghi rõ contract: ai ghi, ai đọc, lúc nào dữ liệu sẵn sàng, và từ mốc nào được phép tái sử dụng bộ nhớ.

## 11. Các anti-pattern và cách sửa

| Anti-pattern | Hậu quả | Thay bằng |
| --- | --- | --- |
| Đóng Arena/handle ngay sau **submitAsync(...)** | Native còn giữ pointer → use-after-free | Giữ owner sống đến terminal quiescence |
| Đặt **try-with-resources** chỉ bao quanh lời gọi submit | Scope kết thúc trước worker | Đặt điểm chờ/cleanup trong phạm vi còn giữ resource |
| Dùng **cancel()** hoặc timeout làm tín hiệu free | Native có thể vẫn chạy | Cancel native, rồi chờ ack/drain thực |
| Trả DirectByteBuffer về pool sau khi enqueue | Request khác ghi đè input/output đang dùng | Trả pool sau completion được API bảo đảm |
| Giữ JNI local ref cho callback muộn | Reference hết hiệu lực | NewGlobalRef, xóa sau callback cuối |
| Dùng Arena.ofConfined() cho Java worker khác thread | WrongThreadException khi truy cập qua Java | ofShared khi cần Java truy cập liên thread; đồng bộ dữ liệu |
| Chờ một Future khi còn request khác chung handle | Đóng quá sớm | Chờ tất cả in-flight + khóa submit mới |
| Để callback vừa release vừa gọi API trên cùng handle không có quy ước | Deadlock/reentrancy/use-after-free | Thống nhất thứ tự callback, drain, cleanup theo hợp đồng |

## 12. Cách kiểm tra wrapper trong thực tế

1. Vẽ timeline **allocate → submit → native use → completion thực → cleanup** cho từng buffer và handle.
2. Ghi rõ completion nghĩa là gì và dẫn đến đâu trong tài liệu native; kiểm tra cả thành công, lỗi, cancel và shutdown.
3. Stress test với callback nhanh/chậm, nhiều request, timeout, cancel, lỗi native, đóng đồng thời; ghi log request ID, owner ID, in-flight count và thời điểm free.
4. Kiểm tra không có request mới khi **DRAINING**, không double-close, không buffer bị pool tái sử dụng khi còn dùng, không rò rỉ trên đường lỗi.
5. Khi có C/C++ tự biên dịch, cân nhắc AddressSanitizer/ThreadSanitizer, công cụ phát hiện rò rỉ, kiểm tra JNI và native crash dump. Những công cụ này giúp tìm lỗi nhưng không thay thế việc xác minh contract hoàn tất.

**Bài tập tự kiểm:** Một thư viện trả về Future báo “đã gửi yêu cầu lên thiết bị”, còn callback báo “DMA complete”. Bạn phải trả buffer về pool ở đâu? **Đáp án:** sau callback **DMA complete** nếu tài liệu xác nhận đó cũng là lần sử dụng cuối của thiết bị/native và không còn callback phụ dùng buffer; nếu chưa xác nhận, phải đợi mốc drain/quiescence muộn hơn.

## Tài liệu chuẩn để đối chiếu

- Oracle, Java SE 22 FFM package: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html
- Dev.java, quản lý lifetime của Arena và MemorySegment: https://dev.java/learn/api/io/ffm/access-memory/
- Oracle, Java SE 17 CompletableFuture (nhất là cancel, join, allOf): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Oracle, JNI Design Overview (global/local references): https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html
