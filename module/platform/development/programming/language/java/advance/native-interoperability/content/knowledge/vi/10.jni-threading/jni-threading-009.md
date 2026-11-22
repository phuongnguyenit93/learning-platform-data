# Quy định hủy hợp tác thay vì giả định `interrupt` luôn dừng được hàm C

## 1. Bài toán trong Java–JNI: yêu cầu dừng không phải cưỡng bức dừng

Một Java thread gọi hàm native thông qua **Java Native Interface (JNI)**. Hàm C có thể tính toán nhiều giây, đợi thiết bị, gọi thư viện C/C++ bên thứ ba hoặc mắc trong một thao tác chặn. Trong khi hàm native đang chạy, thread Java khác gọi:

~~~java
worker.interrupt();
~~~

**Không có cam kết chung rằng lệnh trên lập tức cắt ngang hàm C, hủy vòng lặp C, giải phóng tài nguyên hay đưa native method trở về Java.** `Thread.interrupt()` là cơ chế **gửi yêu cầu ngắt hợp tác** cho thread, không phải lệnh “kill” một khối mã tùy ý.

Khi đang thực thi native method, tiến trình Java vẫn chạy native machine code. Mã C/C++ **không tự động** đọc cờ interrupt của Java ở từng bước lặp. Nếu native method không hỗ trợ đường thoát, JVM thường không có cách an toàn để bắt nó dừng tại vị trí tùy ý mà vẫn bảo toàn stack, mutex, vùng nhớ và trạng thái của thư viện.

Do đó, thiết kế đúng là **quy định giao thức hủy hợp tác (cooperative cancellation)**:

- Bên yêu cầu hủy **phát tín hiệu** bằng một cơ chế có memory visibility rõ ràng.
- Native code **kiểm tra tín hiệu** ở các điểm an toàn, với độ trễ hủy có giới hạn hoặc được tài liệu hóa.
- Native code **không bỏ dở giữa trạng thái bất nhất**: dừng nhận việc mới, kết thúc hoặc rollback đơn vị công việc hiện tại và dọn tài nguyên đang sở hữu.
- Bên gọi **quan sát kết quả xác nhận** rằng native method đã kết thúc, thay vì coi `interrupt()` hoặc `Future.cancel(true)` là bằng chứng đã dừng.
- Khi native code có thể bị treo không hợp tác, cần **timeout ở đúng tầng hoặc cách ly sang tiến trình khác** chứ không hứa hủy tức thời.

Mục tiêu không phải thay thế mọi interrupt bằng một boolean; mục tiêu là **thỏa thuận rõ ai yêu cầu, ai quan sát, điểm kiểm tra, phản ứng khi hủy và lúc nào được coi là dừng xong**.

## 2. Phân biệt “interrupt”, “cancellation request” và “terminated”

| Sự kiện | Ý nghĩa | Điều *không* được suy ra |
| --- | --- | --- |
| `thread.interrupt()` | Đặt trạng thái ngắt của thread hoặc gây cơ chế ngắt được định nghĩa cho một số thao tác Java đang chờ/chặn | Không có nghĩa thread đã chết hay mọi lời gọi JNI/C đã dừng |
| `thread.isInterrupted()` | Đọc trạng thái interrupt mà không xóa cờ | Không phải kiểm chứng rằng native function đã return |
| `Thread.interrupted()` | Đọc **và xóa** interrupt status của **thread hiện tại** | Không tương đương với `isInterrupted()` |
| `InterruptedException` | Một số Java blocking methods thoát vì interrupt; quy tắc phổ biến là trạng thái interrupt đã bị xóa khi exception được ném | Không đảm bảo một syscall C hoặc thư viện native có hành vi giống vậy |
| `cancelToken.set(true)` | Gửi yêu cầu hủy theo giao thức ứng dụng; với `AtomicBoolean` có bảo đảm visibility qua các thao tác atomic/volatile | Không tự dừng C nếu C chưa kiểm tra token |
| Native method trả về `CANCELLED` hoặc xác nhận hoàn tất | Native code đã đi qua điểm xử lý hủy, thực hiện cleanup đã định nghĩa và trở về | Không nói rằng mọi công việc phụ trợ ở thread/process khác đã dừng, trừ khi giao thức bao quát chúng |
| `Future.cancel(true)` | Yêu cầu hủy task; **có thể** interrupt thread thực thi theo cơ chế executor | Không bảo đảm C nhận yêu cầu hoặc đã thoát; trạng thái future không nhất thiết phản ánh tài nguyên native |
| `worker.join()` trả về sau khi thread kết thúc | Có thể xác nhận thread đó không còn thực thi | Không tự cho biết kết quả hủy thành công hay cleanup đúng; phải kiểm tra thêm outcome |

Ví dụ Java thuần:

~~~java
// Minh họa semantics, không phải chương trình hoàn chỉnh.
worker.interrupt();          // Gửi yêu cầu ngắt.
boolean pending = worker.isInterrupted(); // Chỉ đọc cờ.
worker.join();               // Chờ Java thread thực sự kết thúc.
~~~

`join()` có thể chờ mãi nếu native code không bao giờ return. Vì vậy trong hệ thống phục vụ request, không thể dùng một `join()` vô hạn trên đường xử lý chính như giải pháp “hủy có timeout”. Cần contract về thời gian, metrics và mức cách ly thích hợp.

## 3. Tại sao interrupt không thể tự dừng mọi mã C?

### 3.1. Interrupt flag thuộc JVM; native loop không tự kiểm tra

Mã C sau có thể tiếp tục chạy ngay cả khi thread Java bị interrupt:

~~~c
/* Mã C chỉ minh họa, không phải JNI native method độc lập. */
for (;;) {
    do_cpu_work();
}
~~~

Không có lệnh nào trong vòng lặp hỏi JVM về interrupt hay token hủy. JVM không thể giả định vị trí bất kỳ trong `do_cpu_work()` là điểm dừng an toàn.

Một số thư viện native có API hủy/timeout riêng; chúng chỉ hoạt động khi **ứng dụng tích hợp API đó**, không phải vì Java `interrupt()` mặc nhiên nối với chúng.

### 3.2. Ngắt của Java được định nghĩa cho những thao tác cụ thể

Các thao tác Java như `Thread.sleep`, `Object.wait`, `Thread.join` và nhiều phương thức interruptible trong `java.util.concurrent` có hợp đồng riêng về interrupt và `InterruptedException`. Với một số I/O Java, interrupt có thể gây đóng kênh hoặc exception theo API tương ứng.

**Không suy rộng** từ các hành vi ấy sang:

- `read()`/`recv()`/`poll()`/`select()` được C gọi trực tiếp;
- `pthread_mutex_lock` hoặc thư viện đồng bộ native;
- lời gọi thư viện đồ họa, database driver native, GPU hoặc thiết bị;
- hàm C xử lý file, nén, mã hóa hoặc tính toán CPU dài.

OS signal, EINTR, logic restart syscall, timeout, callback và API cancel của thư viện là các cơ chế **khác**. Tùy môi trường, một số lời gọi native có thể tự trả lỗi khi bị OS signal, nhưng **không thể coi `Thread.interrupt()` là một OS signal hủy chuẩn hóa** cho mọi hàm C.

### 3.3. Dừng cưỡng bức ở điểm tùy ý có thể phá hỏng bất biến

Giả sử một native function đang:

~~~text
lock(mutex)
allocate(buffer)
write half of output
update native state
...
unlock(mutex)
free(buffer)
~~~

Nếu ép thread dừng ngay sau khi lock hoặc ghi nửa chừng, thread khác có thể mắc kẹt, buffer bị rò, dữ liệu dang dở hoặc native state hỏng. Giao thức hủy cần quy định **điểm thoát an toàn**: hoàn tất chunk/transaction, trả tài nguyên, rollback nếu có và phát kết quả rõ.

Vì lý do đó, tránh dùng `Thread.stop`, thủ thuật giết thread OS (`pthread_cancel` không kiểm soát, `TerminateThread`...) hoặc tự ý giải phóng native context khi một call khác vẫn dùng nó. Đây không phải các thay thế an toàn cho cooperative cancellation.

## 4. Thiết kế hợp đồng hủy hợp tác

Một hợp đồng có thể viết ngắn gọn thành:

> Bên Java gửi **CANCEL_REQUESTED** bằng token chia sẻ. Native worker kiểm tra token giữa các đơn vị công việc hữu hạn hoặc khi hết thời gian chờ. Khi thấy yêu cầu, worker không bắt đầu đơn vị tiếp theo; nếu cần, hoàn tất/rollback phần dang dở, release tất cả tài nguyên thuộc lượt gọi, rồi trả **CANCELLED**. Bên gọi chỉ xác nhận “đã dừng” sau khi quan sát native method kết thúc.

### 4.1. Định nghĩa rõ năm thành phần

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Đường yêu cầu** | Ai gửi, bằng API nào, từ thread nào? | `AtomicBoolean.cancelRequested.set(true)` |
| **Visibility** | Thread native nhìn thấy thay đổi thế nào? | Gọi `AtomicBoolean.get()` qua JNI; hoặc `_Atomic bool`/`std::atomic<bool>` có quy tắc memory order |
| **Điểm kiểm tra** | Bao lâu kiểm tra một lần? | Sau mỗi chunk tính toán; trước khi bắt đầu native I/O mới; sau timeout polling |
| **Quy tắc cleanup** | Ai chịu trách nhiệm đóng/giải phóng tài nguyên? | Luôn release JNI buffers, đóng file do worker sở hữu, unlock theo thứ tự; không gọi `DeleteGlobalRef` khi còn người dùng |
| **Kết quả/xác nhận** | Bên gọi phân biệt completed/cancelled/failed thế nào? | Method trả enum/status hoặc ném exception đã quy ước; Java thread báo kết thúc qua `CountDownLatch` |

Một số chính sách nên chốt trước khi triển khai:

- **Hủy là best-effort hay có upper bound?** Nếu một chunk tối đa 50 ms, cộng thêm sleep/poll timeout 20 ms, ứng dụng có thể tài liệu hóa độ trễ hủy dự kiến; không nên hứa một upper bound nghiêm ngặt nếu hệ điều hành/thiết bị không bảo đảm.
- **Hủy ở đâu?** Chỉ trước khi commit, hay cho phép rollback nửa chừng? Nếu đã commit thành công, có thể trả `COMPLETED` dù yêu cầu hủy tới rất muộn.
- **Ai sở hữu token và native context?** Không được giải phóng vùng nhớ trong lúc worker còn có thể đọc nó.
- **Đường lỗi ưu tiên thế nào?** Nếu vừa có lỗi I/O vừa có cancel, ghi nhận trạng thái nhất quán và log nguyên nhân; đừng che giấu lỗi thực.
- **Bên gọi chờ đến khi nào?** Timeout của “chờ xác nhận” phải khác với “thời hạn cho phép công việc chạy”; nếu quá thời hạn, cần escalation có kiểm soát.

### 4.2. Sơ đồ vòng đời

~~~text
Java requester              JNI/C worker                 Java supervisor
      |                          |                              |
      | -- submit -------------->|                              |
      |                          | -- start native work ------->|
      |                          |    process chunk             |
      | -- cancel token=true --->|                              |
      |                          | -- poll token                |
      |                          | -- stop new chunks           |
      |                          | -- cleanup resources         |
      |                          | -- return CANCELLED -------->|
      |                          |                              |
      |<------------------------- observe worker termination ---|
~~~

Nếu native code đang ở syscall blocking hoặc lời gọi C bên thứ ba **không thể kiểm tra token**, mũi tên “poll token” chỉ xảy ra khi call ấy trả về. Cần thêm timeout/cancellation API của thư viện, non-blocking design hoặc process isolation để có hành vi đáng tin.

## 5. Chia loại công việc native để chọn cách hủy

| Loại công việc | Điểm kiểm tra hủy thích hợp | Ràng buộc cần biết |
| --- | --- | --- |
| CPU-bound loop trong C/C++ do ta sở hữu | Sau mỗi block hữu hạn; trước chunk tiếp theo | Chunk dài làm tăng cancellation latency |
| Tính toán có commit/side effect | Giữa các bước transaction, trước commit, sau rollback | Không hủy giữa khi invariant đang tạm thời sai |
| Native I/O có timeout/poll | Sau mỗi lần poll/read chặn có timeout; hoặc qua API cancel của thư viện | Không giả định interrupt Java tự làm syscall return |
| Gọi một thư viện native có cancel API | Gửi lệnh cancel bằng API chính thức và chờ acknowledgement | Phải tuân theo thread-safety/lifetime của thư viện |
| Thư viện đen chặn vô hạn, không có cancel/timeout | Cách ly vào process riêng có IPC và timeout | Không hứa hủy an toàn in-process; khi kill process mất toàn bộ trạng thái process đó |
| Callback JNI / FFM/native loop có Java state | Kiểm tra token giữa các callback an toàn | Không gọi JNI tùy ý khi đang giữ critical primitive array/string section |

Điểm cuối đặc biệt quan trọng: sau `GetPrimitiveArrayCritical` hoặc `GetStringCritical`, code phải tuân theo giới hạn critical section; đừng giữ lâu rồi tùy ý gọi `CallBooleanMethod` để hỏi token bên Java. **Release critical section nhanh**, sau đó mới kiểm tra hủy ở safe point.

## 6. Dùng `AtomicBoolean` làm cancellation token qua JNI

Một phương án học tập đơn giản, minh bạch về memory visibility:

- Java tạo `AtomicBoolean cancelRequested = new AtomicBoolean(false)`.
- Java truyền object token vào native method bằng `jobject`.
- Một Java thread khác gọi `cancelRequested.set(true)`.
- Native worker gọi `AtomicBoolean.get()` qua `JNIEnv` giữa các chunk công việc.
- Khi `get()` trả `true`, C dọn tài nguyên rồi return trạng thái hủy.

**Vì sao dùng `AtomicBoolean` mà không dùng một Java `boolean` thường?**

Java `AtomicBoolean.set` và `get` có ngữ nghĩa volatile write/read theo Java Memory Model: cung cấp visibility cần thiết giữa hai thread. Một trường boolean thường không `volatile` mà bị đọc/ghi đồng thời, không có đồng bộ, không cung cấp contract visibility tương đương. `AtomicBoolean` giúp dễ biểu diễn token và tránh tự chế giao thức memory barrier.

**Vì sao native đọc token qua JNI thay vì ép `jobject` thành con trỏ C?**

`jobject` là opaque reference do JVM quản lý, không phải con trỏ tới layout Java object. Native phải sử dụng `GetObjectClass`, `GetMethodID` và `CallBooleanMethod` hoặc JNI accessors phù hợp. Phương pháp gọi `AtomicBoolean.get()` bảo toàn ngữ nghĩa Java và tránh đoán offset bộ nhớ.

**Chi phí:** Mỗi lần `CallBooleanMethod` là một cuộc gọi qua JNI vào method Java, có overhead. Nếu loop chạy hàng triệu lượt/giây, chỉ kiểm tra ở ranh giới chunk thích hợp, hoặc thiết kế token native atomic được quản lý chặt chẽ. Ví dụ dưới ưu tiên **đúng ngữ nghĩa, dễ hiểu và runnable** hơn throughput cực hạn.

## 7. Ví dụ hoàn chỉnh Java 17 + C/JNI: interrupt không đủ; token cho phép thoát

Mục tiêu demo:

1. Java tạo một worker thread và cho worker vào native method.
2. Native method báo đã bắt đầu bằng `CountDownLatch.countDown()`.
3. Thread chính gọi `worker.interrupt()` **nhưng chưa bật token**. Native method vẫn nằm trong vòng lặp vì C không có logic kiểm tra interrupt status.
4. Java xác nhận worker chưa hoàn thành sau một khoảng chờ có giới hạn.
5. Java gọi `cancel.set(true)`. Native code quan sát token qua `AtomicBoolean.get()` và trả về.
6. Java xác nhận native method đã return; worker vẫn có thể giữ interrupt flag, vì mã này không gọi API nào xóa cờ.

Môi trường: **Linux + JDK 17 trở lên + GCC** tương thích kiến trúc JVM. Tạo hai tệp `NativeCancellationDemo.java` và `native_cancel.c` trong cùng thư mục. Đặt biến môi trường `JAVA_HOME` tới JDK.

### 7.1. Java — `NativeCancellationDemo.java`

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class NativeCancellationDemo {
    static {
        System.loadLibrary("nativecancel");
    }

    private static native boolean runUntilCancelled(
            AtomicBoolean cancel, CountDownLatch entered);

    public static void main(String[] args)
            throws InterruptedException {

        AtomicBoolean cancel = new AtomicBoolean(false);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        AtomicBoolean nativeSawCancel = new AtomicBoolean(false);
        AtomicBoolean interruptStillSet = new AtomicBoolean(false);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try {
                boolean cancelled = runUntilCancelled(cancel, entered);
                nativeSawCancel.set(cancelled);
                interruptStillSet.set(
                        Thread.currentThread().isInterrupted());
            } catch (Throwable error) {
                failure.set(error);
            } finally {
                exited.countDown();
            }
        }, "native-worker");

        worker.start();
        entered.await(); // C đã vào native method.

        worker.interrupt(); // Chỉ đặt interrupt status.
        boolean stoppedByInterruptAlone =
                exited.await(75, TimeUnit.MILLISECONDS);

        cancel.set(true);  // Giao thức hủy hợp tác: C có kiểm tra.
        worker.join();     // Chờ worker THỰC SỰ kết thúc.

        if (failure.get() != null) {
            throw new IllegalStateException(
                    "Native worker failed", failure.get());
        }

        System.out.println(
                "stoppedByInterruptAlone="
                + stoppedByInterruptAlone);
        System.out.println(
                "nativeSawCancel=" + nativeSawCancel.get());
        System.out.println(
                "interruptStillSet=" + interruptStillSet.get());
    }
}
~~~

Những lựa chọn trong mã Java:

- `entered.await()` chỉ return sau khi native code đã gọi `countDown()`; vì vậy thread chính không phải đoán thời điểm native bắt đầu.
- `exited.await(75, TimeUnit.MILLISECONDS)` chỉ là khoảng quan sát có giới hạn, **không phải thời gian hủy bắt buộc của JVM**. Vì native method chỉ có đường thoát thành công khi token `true`, nó không thể kết thúc “do interrupt một mình” trong trường hợp demo bình thường.
- `cancel.set(true)` là tín hiệu mà native code **thực sự đọc**. `worker.join()` ở đây dùng để xác nhận worker đã kết thúc trong môi trường demo; production cần timeout và chính sách escalation.
- `AtomicReference<Throwable> failure` chuyển lỗi không mong muốn từ worker sang thread chính để ví dụ không im lặng in một kết quả giả như đã thành công.
- `Thread.currentThread().isInterrupted()` đọc cờ **không xóa** nó. Ví dụ không gọi `Thread.interrupted()`, không gọi `sleep()` Java và không đón `InterruptedException` trong worker.

### 7.2. C/JNI — `native_cancel.c`

~~~c
#define _POSIX_C_SOURCE 200809L

#include <jni.h>
#include <time.h>
#include "NativeCancellationDemo.h"

JNIEXPORT jboolean JNICALL
Java_NativeCancellationDemo_runUntilCancelled(
        JNIEnv *env,
        jclass owner,
        jobject cancel,
        jobject entered) {

    (void) owner;

    if (cancel == NULL || entered == NULL) {
        jclass invalid = (*env)->FindClass(
                env, "java/lang/IllegalArgumentException");
        if (invalid != NULL) {
            (*env)->ThrowNew(
                    env, invalid, "cancel and entered are required");
            (*env)->DeleteLocalRef(env, invalid);
        }
        return JNI_FALSE;
    }

    /* Chuẩn bị method AtomicBoolean.get(): boolean. */
    jclass tokenClass = (*env)->GetObjectClass(env, cancel);
    if (tokenClass == NULL) {
        return JNI_FALSE;
    }
    jmethodID getMethod = (*env)->GetMethodID(
            env, tokenClass, "get", "()Z");
    (*env)->DeleteLocalRef(env, tokenClass);

    if (getMethod == NULL) {
        return JNI_FALSE;
    }

    /* Chuẩn bị CountDownLatch.countDown(): void. */
    jclass latchClass = (*env)->GetObjectClass(env, entered);
    if (latchClass == NULL) {
        return JNI_FALSE;
    }
    jmethodID countDown = (*env)->GetMethodID(
            env, latchClass, "countDown", "()V");
    (*env)->DeleteLocalRef(env, latchClass);

    if (countDown == NULL) {
        return JNI_FALSE;
    }

    /* Thông báo: native method đã vào vùng chạy chính. */
    (*env)->CallVoidMethod(env, entered, countDown);
    if ((*env)->ExceptionCheck(env)) {
        return JNI_FALSE;
    }

    for (;;) {
        /* Poll token qua JNI: thấy AtomicBoolean.get() == true
           thì native method hợp tác return. */
        jboolean cancelled = (*env)->CallBooleanMethod(
                env, cancel, getMethod);

        if ((*env)->ExceptionCheck(env)) {
            return JNI_FALSE; /* Propagate Java exception. */
        }
        if (cancelled == JNI_TRUE) {
            return JNI_TRUE;
        }

        /* Minh họa native wait có giới hạn: 10 ms mỗi lượt.
           nanosleep thuộc POSIX/Linux, không phải JNI API. */
        struct timespec delay = {0, 10 * 1000 * 1000};
        (void) nanosleep(&delay, NULL);
    }
}
~~~

**Đọc các điểm then chốt:**

- `jobject cancel` và `jobject entered` là các **JNI local references** hợp lệ suốt lời gọi native này; Java cũng giữ hai object, nên không cần tạo global reference.
- `GetObjectClass` tạo local `jclass`; code xóa ngay bằng `DeleteLocalRef` sau khi tìm `jmethodID`. Method IDs không phải JNI object references và không dùng `DeleteLocalRef`.
- Descriptor `"()Z"` biểu diễn method `get()` không có tham số, trả `boolean`; `"()V"` biểu diễn `countDown()` không có tham số, trả `void`.
- `CallVoidMethod` báo cho Java rằng C đã vào vùng chờ. JNI calls được dùng với `JNIEnv*` của chính thread worker.
- `CallBooleanMethod` thực thi `AtomicBoolean.get()` để xem trạng thái hủy. Native code **không tự đọc/ghi field Java bằng offset C**.
- Nếu JNI callback gây pending Java exception, method return để Java xử lý lỗi; nó không xóa exception và tiếp tục vòng lặp bất tận.
- `nanosleep` giảm CPU busy-wait và minh họa kiểm tra định kỳ. Một lời gọi ngủ native có thể kết thúc sớm vì OS signal; ví dụ đơn giản bỏ qua kết quả và quay lại kiểm tra token. Không có lệnh nào trong vòng lặp **buộc dừng vì Java interrupt flag**.
- Return `JNI_TRUE` nghĩa là **native loop đã quan sát token true và kết thúc theo giao thức**, không phải có một cơ chế Java kill C bí mật.

Ví dụ cố ý không mô phỏng tài nguyên phức tạp. Khi thêm native buffer, file, mutex, Java global ref hoặc thiết bị, mọi đường return phải đi qua cleanup phù hợp trước khi thông báo hoàn tất.

### 7.3. Biên dịch và chạy trên Linux

Từ thư mục chứa cả hai file:

~~~bash
javac -h . NativeCancellationDemo.java

gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libnativecancel.so native_cancel.c

java -Djava.library.path=. NativeCancellationDemo
~~~

- `javac -h .` sinh `NativeCancellationDemo.class` và `NativeCancellationDemo.h` với chữ ký JNI khớp Java method.
- `gcc -std=c11 -fPIC -shared` tạo shared library Linux `libnativecancel.so`. Macro `_POSIX_C_SOURCE` bật khai báo POSIX `nanosleep`.
- `-Djava.library.path=.` giúp `System.loadLibrary("nativecancel")` tìm thư viện trong working directory; đây không phải Java classpath.
- Native binary và JDK phải tương thích kiến trúc CPU và ABI.

**Stdout dự kiến chính xác** khi chương trình chạy thành công trong môi trường trên, không có lỗi phụ trợ:

~~~text
stoppedByInterruptAlone=false
nativeSawCancel=true
interruptStillSet=true
~~~

Lý do:

1. Worker đã báo `entered` rồi đi vào vòng lặp chỉ thoát khi `AtomicBoolean.get()` trả true.
2. Java `interrupt()` chỉ đổi interrupt status; C không hỏi `Thread.isInterrupted()`, không tự dừng.
3. Trong 75 ms trước khi `cancel.set(true)`, worker không có đường kết thúc bình thường nên `exited.await` trả false.
4. Sau `cancel.set(true)`, vòng lặp nhìn thấy yêu cầu, trả `JNI_TRUE`; Java ghi `nativeSawCancel=true`.
5. Không có code nào trên worker chủ động xóa trạng thái interrupt, do đó `isInterrupted()` trả true.

**Giới hạn của ví dụ:** Nếu chương trình gặp lỗi JVM/native, `entered.await()` hoặc `join()` có thể không đạt đến lộ trình thành công; đây là bài học cơ chế, **không** phải trình giám sát sản xuất có watchdog. Để vận hành thật, bổ sung deadline, error propagation và xử lý khi native library không đáp ứng.

Trên macOS, JNI header nằm trong `$JAVA_HOME/include/darwin`, thư viện động có tên thường là `libnativecancel.dylib` và có thể build bằng Clang `-dynamiclib`. Trên Windows không có POSIX `nanosleep` theo cùng API; thay bằng primitive chờ có timeout của Windows hoặc thiết kế cross-platform C++ phù hợp. JNI cancellation token và hợp đồng return vẫn giữ nguyên.

## 8. Quan sát Java interrupt status trong mã C khi thực sự cần

Có ứng dụng muốn **dùng chính Java interrupt flag làm một nguồn yêu cầu hủy**. Điều đó **có thể làm được nếu native code chủ động gọi JNI để đọc nó**; không có cơ chế tự động toàn cục.

Đường thực hiện về mặt khái niệm:

1. Trong native method, lấy `java.lang.Thread` class thích hợp.
2. Gọi static `Thread.currentThread()` để lấy thread hiện tại (tạo local JNI reference).
3. Gọi instance `isInterrupted()` trên thread đó để đọc flag **mà không xóa**.
4. Dọn local references, kiểm tra exceptions; chỉ poll ở safe point và thực hiện cleanup trước return.

Các descriptor tương ứng:

~~~text
java/lang/Thread
currentThread : ()Ljava/lang/Thread;
isInterrupted : ()Z
~~~

Đây là **sơ đồ API**, không phải một đoạn C runnable độc lập. Có thể dùng `GetStaticMethodID` + `CallStaticObjectMethod` để lấy thread và `GetMethodID` + `CallBooleanMethod` để đọc cờ. Không dùng `Thread.interrupted()` tùy tiện vì method static này đọc **và xóa** flag của thread hiện tại, có thể làm mất tín hiệu mà tầng Java cần thấy.

Nhược điểm của việc chỉ dựa trên interrupt status:

- Cần quy ước rõ **ai là owner của cờ interrupt** và có code Java/JNI nào có thể clear cờ khi gặp `InterruptedException` hoặc gọi `Thread.interrupted()`.
- Một native task có thể chạy trên Java thread được tái sử dụng bởi executor. Nếu task không xử lý chính sách interrupt đúng, việc quan sát flag tồn dư hoặc làm mất flag có thể gây hành vi khó đoán.
- Interrupt status không biểu diễn tất cả lý do hủy (client disconnect, service shutdown, deadline, cancel riêng một operation).
- Hủy một native operation không nhất thiết đồng nghĩa muốn interrupt toàn bộ Java thread hoặc mọi việc khác trên thread ấy.

Vì vậy, với tác vụ JNI lâu, **token chuyên biệt cho operation** thường rõ hơn. Có thể quy định `interrupt` sẽ **kích hoạt token**, nhưng vẫn phải để native code poll, cleanup và return.

## 9. Native cancellation flag bằng C atomic: đúng bộ nhớ, đúng ownership

Khi gọi Java `AtomicBoolean.get()` qua JNI ở mỗi chunk là quá đắt, có thể dùng native flag, ví dụ C11 `_Atomic bool` hoặc C++ `std::atomic<bool>`. Tuy nhiên, sự đúng đắn **không** đến từ `volatile` của C.

### 9.1. Chỉ dùng `volatile` là không đủ

Sai kỳ vọng:

~~~c
/* Minh họa một thiết kế sai về đồng bộ đa luồng. */
static volatile int cancel_requested = 0;

/* Thread A ghi cancel_requested = 1;
   Thread B đọc cancel_requested trong loop. */
~~~

`volatile` trong C **không** tự tạo synchronization/happens-before giữa các thread như một atomic operation; nếu truy cập một biến thường đồng thời mà không đồng bộ, chương trình C có thể có data race và hành vi không xác định. Điều đó không được sửa chỉ bằng cách gọi thêm `Thread.interrupt()`.

Ý tưởng đúng trong C11:

~~~c
/* Trích đoạn minh họa, không phải JNI program độc lập. */
#include <stdatomic.h>
#include <stdbool.h>

_Atomic bool requested = false;

/* Thread gửi yêu cầu. */
atomic_store_explicit(
        &requested, true, memory_order_release);

/* Thread xử lý kiểm tra tại safe point. */
if (atomic_load_explicit(
        &requested, memory_order_acquire)) {
    /* Cleanup rồi return CANCELLED. */
}
~~~

Nếu flag chỉ dùng để truyền một bit cancellation, `memory_order_relaxed` có thể đủ trong thiết kế không cần publish dữ liệu khác; nhưng khi publication/ownership phức tạp, hãy chọn memory order theo hợp đồng đầy đủ. Không sao chép một đoạn minh họa rồi cho rằng đã có lifecycle an toàn.

### 9.2. Không dùng `jlong` native handle mà thiếu quy tắc vòng đời

Một API đôi khi dùng `long nativeHandle` ở Java để trỏ tới C struct chứa atomic cancel flag. Điều đó kéo theo các vấn đề riêng:

- Ai tạo và giải phóng struct?
- Nếu thread Java gửi cancel sau khi worker đã `free` struct, có thể xảy ra **use-after-free**.
- Nếu worker kết thúc rồi handle được tái sử dụng cho object khác, lệnh hủy cũ có thể tác động nhầm operation (**ABA/reuse**).
- Làm sao đồng bộ giữa `cancel()`, `close()` và native `run()`?
- Trên hệ 32/64 bit, chuyển đổi integer-pointer và ABI phải đúng; không coi `jlong` là con trỏ “an toàn mặc định”.
- Nếu JNI native code tạo thread phụ, phải xử lý `AttachCurrentThread`/`DetachCurrentThread` đúng quy định nếu thread ấy cần gọi JVM.

Giải pháp có thể cần reference counting, handle table có generation, lock, trạng thái `RUNNING/CANCELLING/STOPPED` và **cleanup sau khi mọi người dùng handle đã hoàn tất**. Đối với bài học nhập môn cancellation, Java `AtomicBoolean` qua JNI giúp tách biệt rõ visibility và tránh phải tự thiết kế toàn bộ native handle lifecycle.

## 10. Safe point, chunk và giới hạn độ trễ hủy

Hủy hợp tác chỉ nhanh như **điểm kiểm tra gần nhất**. Nếu một chunk C xử lý một triệu record trong 20 giây rồi mới kiểm tra token, yêu cầu hủy có thể mất khoảng 20 giây mới được đáp ứng.

Một mô hình:

~~~text
time ->
[check][chunk A: 5 ms][check][chunk B: 8 ms][check]
                                      ^
                              cancel requested
                                      |
                                đợi đến check
~~~

Nếu một native function có logic:

~~~c
/* Ý tưởng: không phải hàm C độc lập. */
for (size_t start = 0; start < total; start += chunk_size) {
    if (is_cancel_requested()) {
        cleanup();
        return CANCELLED;
    }

    process_chunk(start, chunk_size);
}
~~~

thì độ trễ quan sát token chủ yếu bị chi phối bởi thời gian tối đa của một `process_chunk`, chi phí kiểm tra, lịch CPU và các thao tác dọn. **Không thể hứa độ trễ chặt chẽ** nếu process_chunk có thể chặn vô thời hạn.

Một số quy tắc:

- Chọn chunk đủ ngắn để đáp ứng mục tiêu latency nhưng không quá nhỏ gây overhead JNI/atomic.
- Không poll bằng busy-spin 100% CPU nếu không cần; dùng event/condition có tín hiệu hoặc timed wait.
- Đừng đánh đổi consistency: nếu một chunk là transaction không thể hủy giữa chừng, chỉ dừng sau commit/rollback.
- Nếu có critical array pinning JNI, release đúng API trước khi gọi JNI để poll.
- Ghi metrics: `cancelRequestedAt`, `cancelObservedAt`, `nativeExitAt`; phân biệt delay do polling, I/O và cleanup.

Ví dụ mục tiêu kỹ thuật, **không phải cam kết của JVM**: “worker kiểm tra token sau tối đa 25 ms CPU work; native wait dùng timeout tối đa 50 ms; supervisor chờ xác nhận 2 giây rồi nâng mức xử lý nếu chưa xong.” Những giá trị này do ứng dụng lựa chọn và phải đo trong điều kiện thực tế.

## 11. Khi bị chặn trong native I/O hoặc thư viện C bên thứ ba

Đây là trường hợp mà một token đúng vẫn **không đủ nếu không có safe point**.

### 11.1. Blocking I/O

Giả sử C gọi `read(fd, ...)` và không có dữ liệu trong nhiều phút. Worker không thể kiểm tra `cancelRequested` trong lúc syscall còn đang chặn. Một số cách thiết kế tùy nền tảng:

- Dùng **non-blocking I/O** hoặc `poll`/`select`/`epoll`/`kqueue` với timeout hữu hạn, kiểm tra token sau mỗi lượt.
- Sử dụng API asynchronous/cancel chính thức nếu thư viện hoặc OS cung cấp.
- Có thể dùng cơ chế wake-up riêng (pipe/eventfd/event/condition) để hủy việc đợi; cần tránh race giữa wake-up, đóng descriptor và thao tác I/O.
- Cấu hình **timeout tại chính tầng native library/driver**, không chỉ Java `Future.get(timeout)`.
- Trên Windows, I/O model và cancellation API có đặc thù riêng; không giả định hành vi Linux POSIX tương đương.

Không tự ý `close(fd)` từ thread khác rồi tin rằng mọi thao tác đang chặn sẽ dừng an toàn và ngay lập tức trên mọi hệ điều hành. Phải theo tài liệu OS/library, quản lý ownership của descriptor và phản ứng khi trả lỗi.

### 11.2. Native third-party libraries

Nếu một lời gọi như `vendor_process(...)` chặn một lần rất dài, code JNI bên ngoài **không thể poll token ở bên trong**. Hãy xem library có:

- tham số `timeout` hoặc deadline;
- callback `shouldCancel`;
- API `requestCancel/abort` đồng bộ hoặc bất đồng bộ;
- API đóng session có quy định thread-safety;
- khả năng xử lý mỗi batch/stream chunk thay vì một lời gọi nguyên khối.

Khi vendor library không hỗ trợ, đừng công bố rằng `Thread.interrupt` đã cung cấp khả năng cancel. Nếu tính cô lập là yêu cầu hệ thống, chạy phần native đó trong **tiến trình con**: có thể cắt tiến trình sau timeout với cơ chế của OS, với đánh đổi mất toàn bộ trạng thái của process con và trách nhiệm thu dọn file/temp data/IPC.

### 11.3. GPU, accelerator hoặc thiết bị ngoại vi

Lệnh đã gửi tới thiết bị có thể tiếp tục chạy dù Java task bị hủy. Hợp đồng phải xác định: chỉ dừng enqueue việc mới, có thực sự cancel work đang chạy được không, khi nào buffer/driver handle có thể được giải phóng, và lúc nào Java caller được báo kết thúc. Hủy Java thread **không** có nghĩa phép tính trên GPU đã được rollback.

## 12. Trả kết quả thế nào để người gọi không hiểu nhầm?

Phân biệt **yêu cầu hủy được ghi nhận**, **native đã nhìn thấy hủy**, và **tài nguyên đã giải phóng**.

Một giao thức kết quả tối thiểu:

| Trạng thái | Nghĩa | Hành động bên gọi |
| --- | --- | --- |
| `COMPLETED` | Native đã hoàn tất công việc theo hợp đồng, kể cả trường hợp cancel đến sau commit | Nhận kết quả, không tự gán `CANCELLED` chỉ vì từng gọi interrupt |
| `CANCELLED` | Worker thấy token và thoát qua cleanup có xác nhận | Không dùng partial output nếu contract không cho phép |
| `FAILED` | Có lỗi native/JNI/I/O, không phải hủy bình thường | Giữ thông tin lỗi gốc, rollback/dọn thích hợp |
| `TIMED_OUT_WAITING` | Bên chờ hết thời gian nhưng worker chưa xác nhận thoát | **Chưa được coi native đã dừng**; không tự giải phóng resources worker có thể đang dùng |

Ví dụ interface Java mang tính thiết kế:

~~~java
// Minh họa contract, không phải chương trình độc lập.
enum Outcome {
    COMPLETED, CANCELLED, FAILED
}

interface CancellableNativeOperation {
    void requestCancel();  // Chỉ phát tín hiệu.
    Outcome awaitResult();  // Chờ và nhận kết quả thật.
}
~~~

Nếu cần deadline cho `awaitResult`, trả riêng trạng thái `TIMED_OUT_WAITING` hoặc ném timeout exception biểu thị **chờ quá hạn**, không tự diễn giải thành hủy thành công. Khi đã công bố cancel, cần quyết định phần kết quả partial, transaction commit và cleanup của file/native buffer.

Một `boolean` đủ cho demo `runUntilCancelled`, nhưng trong sản phẩm thực nên dùng status/exception rõ ràng để không gộp `FAILED` với `COMPLETED` hoặc `CANCELLED`.

## 13. Tương tác với `ExecutorService` và `Future.cancel(true)`

Một mẫu Java phổ biến:

~~~java
// Ví dụ Java minh họa, chưa đầy đủ imports/khởi tạo.
Future<?> future = executor.submit(() -> nativeCall());
future.cancel(true);
~~~

`cancel(true)` trên `Future` có thể cố ngắt thread thực thi, nhưng **không có bảo đảm rằng nativeCall() dừng** nếu nó đang ở trong một hàm C không hợp tác. Trạng thái `Future` có thể thành cancelled dù công việc native bên dưới chưa thực sự ngừng sử dụng tài nguyên.

Vì vậy, nếu tác vụ có native state quan trọng:

1. Mỗi operation có cancellation token/handle riêng.
2. Khi caller cancel future, coordinator **phát yêu cầu hủy vào đúng operation** (không chỉ gọi `future.cancel(true)`).
3. Worker native poll token hoặc nhận API cancel từ library và **acknowledge lúc thoát**.
4. Coordinator giữ native context sống cho tới khi worker thực sự kết thúc và cleanup xong; không `free`/close handle dùng dở.
5. Nếu deadline bị vượt, log trạng thái “hủy chưa hoàn tất”, cô lập tài nguyên hoặc escalate theo chính sách chứ không gọi thành công.

Đặc biệt, `CompletableFuture.cancel(boolean)` không có semantics giống việc cưỡng bức dừng task đang chạy: tài liệu `CompletableFuture` nêu tham số `mayInterruptIfRunning` không điều khiển việc sử dụng interrupts của implementation này. Càng phải tách **future cancellation state** khỏi **native worker termination**.

### Shutdown service

`ExecutorService.shutdownNow()` thường cố ngắt các task đang chạy, nhưng đó vẫn là **best-effort**. Nếu nhiều worker mắc kẹt trong C, đừng chờ rằng `shutdownNow` sẽ giải phóng tài nguyên native ngay. Giao thức shutdown hợp lý: stop nhận job mới → phát cancel tới từng operation → chờ acknowledgement theo deadline → xử lý những operation không hợp tác.

## 14. Exception, cleanup và JNI thread rules

### 14.1. Mỗi đường thoát phải dọn tài nguyên được sở hữu

Ví dụ minh họa về mã C dùng resource:

~~~c
/* Pseudocode C: không phải chương trình runnable độc lập. */
int result = FAILED;
Resource *resource = open_resource();
if (resource == NULL) {
    return FAILED;
}

for (;;) {
    if (cancel_requested()) {
        result = CANCELLED;
        break;
    }

    if (work_finished()) {
        result = COMPLETED;
        break;
    }

    if (work_failed()) {
        result = FAILED;
        break;
    }
}

close_resource(resource); /* Cleanup trước khi báo kết quả. */
return result;
~~~

Mẫu có một cửa cleanup để giảm rủi ro quên giải phóng khi hủy hoặc lỗi. Đây là **pseudocode**, không chứa định nghĩa của `Resource`/`work_finished` và không có ý định copy/compile nguyên đoạn.

Với JNI, cleanup có thể gồm:

- `ReleaseIntArrayElements`/`ReleasePrimitiveArrayCritical` cho vùng phần tử mảng đã acquire;
- `ReleaseStringUTFChars`/`ReleaseStringChars` cho buffer ký tự đã acquire;
- `DeleteLocalRef` cho local JNI references có thể dọn sớm;
- `DeleteGlobalRef` chỉ khi global reference đã hết người sử dụng;
- giải phóng `malloc`/`free`, resource C++ RAII, file descriptor và mutex đúng ownership.

**Không thể thay `Release...` cho buffer JNI bằng `DeleteLocalRef`**, và không thể `free(jobject)` vì object vẫn do JVM quản lý.

### 14.2. JNI exceptions

Các lệnh `GetObjectClass`, `GetMethodID`, `CallBooleanMethod` có thể thất bại hoặc để pending Java exception. Nếu một JNI callback thất bại:

- Kiểm tra kết quả/null/`ExceptionCheck`.
- Không tiếp tục đường xử lý thường như thể callback thành công.
- Dọn tài nguyên native đang sở hữu bằng các API cleanup được phép.
- Propagate exception hiện tại, hoặc chuyển thành lỗi rõ ràng theo giao thức **mà không âm thầm xóa nguyên nhân**.

Ví dụ hoàn chỉnh ở trên trả `JNI_FALSE` khi JNI exception pending; Java sẽ nhận exception trước khi có thể tin giá trị boolean. Không coi `JNI_FALSE` là một kết quả nghiệp vụ thành công khi Java exception còn tồn tại.

### 14.3. `JNIEnv*` không dùng xuyên thread

`JNIEnv*` gắn với thread hiện tại. Nếu native code tự sinh thread, thread đó cần `AttachCurrentThread`/`GetEnv` để có `JNIEnv*` tương ứng, rồi `DetachCurrentThread` khi thích hợp. Không chuyển `JNIEnv*` của worker A sang worker B.

JNI local references cũng không dùng trực tiếp ở thread khác. Nếu token Java cần truy cập từ **native thread phụ** sống sau lời gọi gốc, phải tạo global reference hợp lệ khi local còn sống, đồng bộ ownership và xóa khi không còn sử dụng; dùng `JNIEnv*` của chính thread đó. Trong demo, token được **truyền như tham số cho native method và chỉ truy cập trong cùng lời gọi và thread**, nên local reference là đủ.

### 14.4. Không gọi JNI tùy ý trong critical sections

Khi native code đang giữ con trỏ qua `GetPrimitiveArrayCritical` hoặc `GetStringCritical`, hợp đồng JNI áp đặt hạn chế để tránh làm JVM không thể tiến hành những hoạt động cần thiết. Poll token bằng `CallBooleanMethod` **bên trong một critical section dài** là thiết kế rủi ro, có thể vi phạm giới hạn của JNI. Hãy chia việc thành các đoạn nhỏ, release critical region trước khi kiểm tra hủy.

## 15. Những anti-patterns thường gặp

### Anti-pattern 1: “Đã gọi `interrupt()` nên thread chắc chắn dừng”

~~~java
// SAI VỀ SUY LUẬN: native work không nhất thiết ngừng.
worker.interrupt();
nativeContext.close(); // Có nguy cơ đóng context khi C còn dùng.
~~~

Cách đúng: phát cancel request, **chờ tín hiệu worker đã thoát**, rồi mới release native context theo ownership; nếu chờ quá hạn, ghi nhận chưa dừng và escalate đúng cơ chế.

### Anti-pattern 2: “C cứ gọi `sleep` nên Java interrupt sẽ ngắt `nanosleep`”

`Thread.interrupt()` trong Java không định nghĩa chuyện OS `nanosleep` của native C phải ném `InterruptedException`; C cũng không có Java checked exception đó. Một native sleep có thể bị OS signal theo semantics OS, nhưng không được dựa vào đó để làm hợp đồng hủy chung. Thay bằng timed wait có poll token/notification phù hợp.

### Anti-pattern 3: “Đổi biến C thường từ Java thread, native sẽ tự thấy”

Biến C thường bị đọc và ghi từ hai native threads mà không atomic/lock có thể gây data race. `volatile` C không tự thay thế synchronization. Dùng `AtomicBoolean` qua JNI, `std::atomic` hoặc `_Atomic` với lifetime đúng.

### Anti-pattern 4: “Future cancelled là cleanup đã xong”

Trạng thái `Future` và trạng thái native worker **không nhất thiết đồng bộ**. Trước khi free buffer, unload native library hoặc tái sử dụng handle, phải chờ native acknowledgement. Nếu không, có thể use-after-free, double close hoặc kết quả ghi dở.

### Anti-pattern 5: “Kiểm tra cancel ở mọi instruction”

Poll quá thường xuyên có thể gây overhead lớn; poll quá ít làm UX chậm. Dùng chunk và safe points phù hợp công việc, đo độ trễ bằng test. Với I/O, cần wake-up/cancel API hoặc timeout tại chính tầng chặn.

### Anti-pattern 6: “Hủy là ném exception bất kỳ”

Nếu native method đang giữ mutex hoặc buffer, ném hoặc return đột ngột trước cleanup có thể phá invariant. Định nghĩa vùng không được hủy, rollback/commit, một đường cleanup và status/exception rành mạch.

### Anti-pattern 7: “Java token luôn giúp dừng một lời gọi C bất kỳ”

Không. Nếu C đang ở thư viện bên thứ ba chặn không thể quay lại poll, token sẽ không được quan sát. Cần timeout/cancel hỗ trợ trong native library, callback hoặc process isolation.

### Anti-pattern 8: “Interrupt flag luôn còn nguyên”

Một số Java blocking APIs có thể clear status khi ném `InterruptedException`; `Thread.interrupted()` cũng clear. Không trộn lẫn interrupt với token nghiệp vụ mà không định nghĩa rõ cách preserve/restore. Trong Java code bắt `InterruptedException` mà không thể kết thúc ngay, có thể cần `Thread.currentThread().interrupt()` để khôi phục trạng thái theo contract, nhưng phải cân nhắc luồng lỗi và lớp gọi.

## 16. Checklist review một JNI operation có hủy

Trước khi đưa JNI operation dài vào production, kiểm tra:

1. **Ai tạo yêu cầu hủy?** User, HTTP disconnect, deadline, service shutdown hay executor?
2. **Cancellation channel là gì?** Atomic Java token qua JNI, native atomic flag, API của thư viện, timed wait/event hay IPC?
3. **Visibility được bảo đảm chưa?** Java Memory Model, C/C++ atomics và native handle ownership đều rõ?
4. **Safe points ở đâu?** Trong CPU loop, giữa batch, trước commit, sau mỗi blocking call? Có call nào có thể chặn vô hạn không?
5. **Tài nguyên sẽ dọn ở đâu?** Có một đường cleanup cho successful completion, cancellation và failure?
6. **Java interrupt flag được xử lý ra sao?** Có method nào clear flag? Có muốn một interrupt hủy operation hiện tại hay mọi task trên thread?
7. **Cách xác nhận đã dừng?** Return value, JNI status, latch, worker termination, completion callback? Có phân biệt *requested* với *done*?
8. **Timeout nào áp dụng?** Timeout của native I/O/driver, timeout của chờ result, timeout shutdown; không nhập nhằng.
9. **Nếu không hợp tác thì sao?** Isolate process, log và vận hành escalations, tránh unload/free context đang chạy.
10. **Có test race không?** Cancel trước khi bắt đầu, trong CPU chunk, khi chờ I/O, đúng lúc commit, sau khi completed, trong cleanup và cùng lúc đóng context.
11. **Đã kiểm tra lỗi JNI chưa?** Dùng HotSpot `-Xcheck:jni` và test với JVM/OS/architecture thực tế.
12. **Có monitoring không?** Đếm cancellations requested, cancellations confirmed, timeouts waiting for native exit, leak, hung threads và exceptions.

Một bộ test tối thiểu nên bao gồm:

| Test | Kỳ vọng |
| --- | --- |
| Cancel trước khi native xử lý chunk đầu | Native thấy token sớm, không bắt đầu công việc không cần thiết |
| Cancel giữa nhiều chunk | Native hoàn tất/rollback chunk theo hợp đồng rồi trả CANCELLED |
| Cancel ngay sau completed | Trả COMPLETED nếu đã commit, không biến thành CANCELLED sai |
| Interrupt nhưng không set token | Với worker chỉ poll token, native **không** return vì interrupt |
| Có native exception hoặc Java exception trong callback | Không log “cancelled” giả; cleanup và propagate lỗi |
| Bên chờ hết timeout nhưng native còn chạy | Không free context, đánh dấu chờ quá hạn, áp dụng policy |
| Cancel cùng lúc close native handle | Không double free/use-after-free; ownership được đồng bộ |
| Worker đang bị chặn ở vendor API | Kiểm tra timeout/cancel thật của library, không chỉ Java flag |

## 17. Câu hỏi tự kiểm tra

1. Vì sao `Thread.interrupt()` không phải lệnh giết một native function C bất kỳ?
2. Trạng thái `Future.cancel(true)` có chứng minh JNI worker đã release buffer và return không?
3. Trong ví dụ `NativeCancellationDemo`, tại sao `stoppedByInterruptAlone` là `false`?
4. Vì sao `cancel.set(true)` có thể được native nhìn thấy khi C gọi `AtomicBoolean.get()` qua JNI?
5. Nếu C đang gọi một blocking vendor function không có timeout/cancel, việc poll token ở vòng lặp bao quanh có bảo đảm dừng đúng deadline không?
6. Vì sao dùng một biến C `volatile int` có thể vẫn sai khi hai thread ghi/đọc để hủy?
7. Khi `GetPrimitiveArrayCritical` còn hiệu lực, có nên poll token bằng `CallBooleanMethod` tùy ý không?
8. Điểm nào cần có để coi hủy **đã hoàn tất**, thay vì chỉ **đã yêu cầu**?
9. Nếu một thread native phụ muốn dùng Java token sau khi JNI invocation ban đầu return, có thể giữ raw local `jobject` không?
10. Tại sao việc đóng/free native context ngay sau `interrupt` có thể gây use-after-free?
11. Nếu yêu cầu hủy tới sau khi dữ liệu đã commit, có luôn phải trả `CANCELLED` không?
12. Nếu native library không hỗ trợ hủy và có thể treo, lựa chọn kiến trúc nào cho phép thực hiện timeout cách ly mạnh hơn?

**Đáp án tóm tắt:** (1) interrupt mang tính hợp tác và C không mặc định poll; (2) không; (3) worker chỉ thoát sau khi token true, chưa set token ở thời điểm kiểm tra; (4) semantics volatile của AtomicBoolean và JNI gọi Java method thật; (5) không, phải có API/timeout bên trong call; (6) volatile C không thay cho atomic/synchronization; (7) không, cần release critical region trước; (8) native return/acknowledgement sau cleanup; (9) không, cần global ref/ownership và attach thread đúng; (10) native còn đang dùng context; (11) không, phụ thuộc contract commit; (12) tiến trình con với IPC/timeout và chính sách tiêu hủy process.

## 18. Tài liệu chuẩn

- [Java SE 17 — `Thread.interrupt`, `isInterrupted`, `interrupted`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
- [Java SE 17 — `AtomicBoolean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html)
- [Java SE 17 — `Future.cancel(boolean)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — JNI Functions (`CallBooleanMethod`, critical arrays, exceptions)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Java SE 17 — JNI Invocation API (`AttachCurrentThread`)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Java SE 17 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

**Kết luận:** `Thread.interrupt()` và `Future.cancel(true)` là những **yêu cầu ngắt/hủy**, không phải bằng chứng mọi hàm native C đã bị dừng. JNI operation đáng tin phải có **cancellation signal đọc được**, **safe points**, **cleanup/ownership đúng** và **acknowledgement sau khi native thực sự return**. Khi native code không thể hợp tác, cần **timeout/cancellation API ở tầng thực thi** hoặc **cách ly tiến trình**; tuyệt đối không mặc nhiên cho rằng interrupt sẽ làm C thoát an toàn.
