# Điều phối callback tái nhập và tránh giữ khóa khi vượt ranh giới Java/C

## Mục tiêu và bối cảnh

Khi Java gọi mã C qua JNI (Java Native Interface), mã C có thể gọi ngược một phương thức Java (*callback*). Callback ấy có thể lại gọi C, chạy trên cùng luồng hoặc trên một luồng native khác. Vì vậy, lời gọi tưởng như tuyến tính `Java → C` thực tế có thể thành `Java → C → Java → C`, thậm chí lặp nhiều tầng. Các quy tắc dưới đây cũng áp dụng về mặt thiết kế cho lời gọi *downcall/upcall* của Foreign Function & Memory API (FFM); cú pháp và phiên bản JDK của FFM khác JNI.

Sau bài này, người học cần:

1. Phân biệt callback **đồng bộ/tái nhập trên cùng luồng** với callback **bất đồng bộ từ luồng khác**.
2. Giải thích được deadlock do mutex C không tái nhập, Java monitor bị giữ khi chờ callback, và đảo thứ tự khóa giữa hai runtime.
3. Thiết kế giao thức **chuẩn bị trạng thái → nhả khóa → gọi qua biên → callback cập nhật trạng thái**.
4. Giữ tính đúng đắn của dữ liệu, vòng đời tài nguyên, xử lý lỗi và hủy tác vụ ngay cả khi callback xảy ra tức thì, nhiều lần hoặc sau khi yêu cầu đã hết hiệu lực.
5. Kiểm tra và chẩn đoán các tình huống callback gây treo mà không tạo một bài test treo vô thời hạn.

## 1. Hiểu đúng “tái nhập” qua Java/C

Xét đường đi:

```text
Java Thread T1: service.run()
  └─ nativeCall()                    Java → C
       └─ CallVoidMethod(callback)  C → Java
            └─ callback.onEvent()
                 └─ nativeQuery()   Java → C (tái nhập)
```

* **Tái nhập đồng bộ:** C gọi callback trước khi lời gọi native ban đầu trả về. Với JNI `CallVoidMethod` thông thường, callback chạy trên **chính luồng đang gọi JNI**. Stack có nhiều tầng Java/C; trạng thái phía ngoài có thể vẫn đang “thực hiện dở”.
* **Callback trên luồng native riêng:** C phát sự kiện từ một worker thread đã attach vào JVM. Luồng Java ban đầu có thể đang chờ kết quả hoặc đã trả về. Lúc này các mutex/monitor bị giữ ở luồng khác thực sự chặn callback.
* **Reentrant lock không đồng nghĩa an toàn callback:** Java `synchronized` và `ReentrantLock` cho **cùng luồng** lấy lại **chính khóa đó**. Nhưng callback có thể thấy bất biến dữ liệu chưa hoàn tất, gây đệ quy ngoài dự kiến, hoặc cần khóa do **luồng khác** giữ. `pthread_mutex_t` thông thường (mặc định) không nên được giả định là mutex đệ quy; tự khóa lại có thể gây deadlock/hành vi phụ thuộc loại mutex.

Java monitor và `pthread_mutex_t` của C là **hai cơ chế khóa khác nhau**. Việc bảo vệ một biến bằng monitor Java không tự bảo vệ biến native bằng mutex C, và ngược lại. Nếu một thao tác phải phối hợp cả hai phía, cần một giao thức trạng thái và thứ tự đồng bộ rõ ràng.

### Ba tình huống gây lỗi tiêu biểu

**A — C gọi Java khi vẫn giữ mutex C:**

```text
T1: C lock(M_C)
T1: C → Java callback.onEvent()
T1: callback → JNI readNativeState()
T1: C cố lock(M_C) lần nữa → có thể tự deadlock
```

Đổi sang mutex recursive chỉ che được tình huống cùng luồng; callback vẫn có thể nhìn thấy trạng thái nửa chừng và tạo vòng khóa với luồng khác. Cách sửa cơ bản là **nhả M_C trước khi gọi Java**.

**B — Java giữ monitor rồi chờ callback từ luồng khác:**

```text
T1: synchronized(M_J) → gọi C → đợi worker hoàn thành
T2: native worker → Java callback → cần synchronized(M_J)
T1: đợi T2             T2: đợi M_J của T1
```

`synchronized` có khả năng tái nhập cũng không cứu được vì T1 và T2 là hai luồng khác nhau. Timeout có thể phát hiện tình huống, nhưng **không thay thế** sửa đồ thị phụ thuộc.

**C — Đảo thứ tự khóa (ABBA):**

```text
T1: giữ M_J → đợi M_C
T2: giữ M_C → callback Java → đợi M_J
```

Dù mỗi khóa được dùng đúng cú pháp, hai luồng tạo thành vòng chờ. Thứ tự khóa toàn hệ thống là một giải pháp khi không thể tách các vùng tới hạn, nhưng ở ranh giới có callback tùy ý, cách bền vững hơn là **không thực hiện lời gọi có thể callback trong lúc giữ khóa**.

## 2. Giao thức an toàn ở ranh giới

Quy tắc thiết kế: **Mọi lời gọi qua Java/C phải được xem là có thể tái nhập, chặn, ném lỗi hoặc kích hoạt callback, trừ khi hợp đồng của API đảm bảo ngược lại.**

Một thao tác mẫu:

```text
Java                                  C
-----                                 -----
lock(stateLock)
  kiểm tra điều kiện
  ghi requestId và trạng thái PENDING
  chụp dữ liệu cần gửi
unlock(stateLock)
      JNI invoke(requestId, snapshot) ─────►
                                      lock(nativeMutex)
                                        đọc/cập nhật trạng thái ngắn
                                      unlock(nativeMutex)
                          ◄────────── callback(requestId, result)
lock(stateLock)
  xác thực requestId còn hiệu lực
  ghi COMPLETED/FAILED một lần
unlock(stateLock)
thực hiện thông báo/hành động tiếp theo ngoài khóa
```

Các điểm cần giữ:

- **Đăng ký trạng thái chờ trước khi gọi native.** Callback đồng bộ có thể xảy ra ngay trong lời gọi JNI, trước khi `invoke` trả về. Nếu tạo `pending` sau `invoke`, callback sẽ không tìm thấy yêu cầu.
- **Chụp dữ liệu dưới khóa, sử dụng bản chụp sau khi nhả khóa.** Bản chụp nên bất biến hoặc thuộc quyền sở hữu rõ ràng; không truyền tham chiếu đến vùng nhớ có thể bị giải phóng/sửa đồng thời.
- **Callback thực hiện một bước chuyển trạng thái ngắn.** Sau khi nhả khóa mới gọi listener, JNI khác, ghi log có thể chặn, gửi kết quả qua queue/executor hoặc hoàn thành future.
- **Không chờ completion khi vẫn giữ monitor/mutex.** `Future.get`, `join`, `CountDownLatch.await`, I/O, RPC hoặc chờ điều kiện C phải ở ngoài vùng khóa, trừ khi có một giao thức rất cụ thể chứng minh an toàn.
- **Đặt quy tắc callback rõ ràng:** inline hay trên thread khác, một lần hay nhiều lần, thứ tự sự kiện, thread affinity, quyền gọi lại API, cách truyền lỗi, cách hủy và quy tắc “không callback dưới khóa”.
- **Kiểm tra khóa ở tầng gọi phía trên.** Dù phương thức wrapper JNI không có `synchronized`, caller vẫn có thể đang giữ monitor khi gọi wrapper.

Một bảng quy chiếu nhanh:

| Thao tác dễ gây nguy hiểm dưới khóa | Thay thế |
| --- | --- |
| `synchronized(lock) { nativeCall(); }` | Chuẩn bị state trong `synchronized`, gọi `nativeCall` sau khi ra khỏi khối. |
| `pthread_mutex_lock` → `CallVoidMethod` → unlock | Chụp/cập nhật native state, unlock, rồi `CallVoidMethod`. |
| Callback vừa đổi state vừa gọi listener ngoài hệ thống | Commit ngắn dưới khóa, nhận việc tiếp theo và dispatch sau unlock. |
| Luồng gọi giữ khóa trong lúc đợi callback | Đợi bên ngoài khóa; dùng timeout/cancellation và trạng thái rõ ràng. |
| Tùy tiện khóa Java rồi khóa C, và ngược lại | Cắt chuỗi khóa xuyên ranh giới; nếu bắt buộc lồng khóa, xác định thứ tự duy nhất và kiểm tra mọi đường đi. |

## 3. Ví dụ Java 17 chạy độc lập: callback inline và callback trên worker

Ví dụ sau **mô phỏng** ranh giới native bằng một `Gateway`, để nhìn rõ vị trí nhả khóa mà không cần biên dịch thư viện C. Đây là chương trình Java hoàn chỉnh, tên tệp `CallbackBoundaryDemo.java`:

```java
public final class CallbackBoundaryDemo {
    @FunctionalInterface
    interface Gateway {
        void invoke(Runnable callback) throws InterruptedException;
    }

    private final Object stateLock = new Object();
    private int pending;
    private int completed;

    void dispatch(Gateway gateway) throws InterruptedException {
        // Công bố trạng thái trước: callback có thể chạy inline.
        synchronized (stateLock) {
            pending++;
        }

        // Quan trọng: không giữ stateLock khi qua "native boundary".
        gateway.invoke(this::onEvent);
    }

    private void onEvent() {
        synchronized (stateLock) {
            if (pending <= 0) {
                throw new IllegalStateException("Unexpected callback");
            }
            pending--;
            completed++;
        }
        // Nếu cần gọi listener/native khác, hãy làm ở ngoài khóa.
    }

    String status() {
        synchronized (stateLock) {
            return "completed=" + completed + ", pending=" + pending;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CallbackBoundaryDemo demo = new CallbackBoundaryDemo();

        demo.dispatch(Runnable::run); // Callback ngay trên luồng gọi.
        System.out.println("inline: " + demo.status());

        demo.dispatch(callback -> {
            Thread worker = new Thread(callback, "native-simulation");
            worker.start();
            worker.join(); // Đợi ngoài stateLock.
        });
        System.out.println("worker: " + demo.status());
    }
}
```

Biên dịch/chạy:

```bash
javac CallbackBoundaryDemo.java
java CallbackBoundaryDemo
```

Kết quả chuẩn:

```text
inline: completed=1, pending=0
worker: completed=2, pending=0
```

Ở lần đầu, callback xảy ra trước khi `dispatch` trả về; ở lần hai, nó chạy từ worker khác. Cả hai đều lấy được `stateLock` vì `dispatch` đã nhả khóa. Nếu chuyển `gateway.invoke(...)` **vào bên trong** `synchronized (stateLock)`, lần inline có thể vẫn chạy nhờ Java monitor tái nhập, nhưng lần worker với `join` sẽ deadlock: luồng gọi đợi worker, worker đợi monitor. **Không dùng thay đổi nguy hiểm này làm bài thử không có timeout.**

Ví dụ chỉ minh họa khóa và trình tự callback. Hệ thống thực phải xử lý `invoke` thất bại, interruption, callback lặp/đến muộn, yêu cầu bị hủy và trạng thái đang chờ; không được mặc định mỗi callback luôn tương ứng một `pending`.

## 4. Ví dụ JNI/C thực: C → Java → C tái nhập mà không giữ mutex

Ví dụ Linux dưới đây dùng Java 17+, JNI và `pthread_mutex_t`. Java gọi `emit()` sang C. C tăng bộ đếm dưới mutex rồi **nhả mutex trước** khi callback `onEvent(int)`. Callback lại gọi `readSequence()` sang C, lấy **chính mutex** đó để đọc. Nếu giữ mutex trong `CallVoidMethod`, đường tái nhập này có thể treo.

Tệp `JniCallbackDemo.java`:

```java
public final class JniCallbackDemo {
    static {
        System.loadLibrary("jnicallback");
    }

    private final Object stateLock = new Object();
    private int lastId = -1;
    private int lastNative = -1;

    private native void emit();
    private native int readSequence();

    // JNI gọi callback trên luồng đã vào emit().
    private void onEvent(int eventId) {
        int observed = readSequence(); // Java -> C lần thứ hai.
        synchronized (stateLock) {
            lastId = eventId;
            lastNative = observed;
        }
    }

    public static void main(String[] args) {
        JniCallbackDemo demo = new JniCallbackDemo();
        demo.emit(); // Không giữ stateLock quanh lời gọi native.
        synchronized (demo.stateLock) {
            System.out.println("event=" + demo.lastId
                    + ", native=" + demo.lastNative);
        }
    }
}
```

Tệp `jni_callback.c`:

```c
#include <jni.h>
#include <pthread.h>

static pthread_mutex_t native_mutex = PTHREAD_MUTEX_INITIALIZER;
static jint sequence = 0;

JNIEXPORT void JNICALL
Java_JniCallbackDemo_emit(JNIEnv *env, jobject self) {
    // Vùng tới hạn phía C: chỉ thao tác trên state native.
    pthread_mutex_lock(&native_mutex);
    jint event_id = ++sequence;
    pthread_mutex_unlock(&native_mutex);

    // Không được giữ native_mutex khi gọi ngược sang Java.
    jclass type = (*env)->GetObjectClass(env, self);
    if (type == NULL) {
        return; // JVM đã có pending exception nếu lookup thất bại.
    }

    jmethodID on_event =
        (*env)->GetMethodID(env, type, "onEvent", "(I)V");
    if (on_event != NULL) {
        (*env)->CallVoidMethod(env, self, on_event, event_id);
    }
    // DeleteLocalRef là JNI operation được phép khi exception pending.
    (*env)->DeleteLocalRef(env, type);
}

JNIEXPORT jint JNICALL
Java_JniCallbackDemo_readSequence(JNIEnv *env, jobject self) {
    (void)env;
    (void)self;

    pthread_mutex_lock(&native_mutex);
    jint result = sequence;
    pthread_mutex_unlock(&native_mutex);
    return result;
}
```

Trên **Linux** với JDK và GCC được cài, tại thư mục chứa hai tệp:

```bash
javac -h . JniCallbackDemo.java
gcc -std=c11 -shared -fPIC -pthread \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libjnicallback.so jni_callback.c
java -Djava.library.path=. JniCallbackDemo
```

Kết quả với một lần `emit` trong tiến trình mới:

```text
event=1, native=1
```

Lưu ý triển khai: khai báo `JAVA_HOME` trỏ đến JDK đang biên dịch; tên/đuôi thư viện và lệnh build thay đổi trên Windows/macOS. `javac -h .` sinh header JNI tương ứng tên lớp/method; ví dụ dùng lớp **không có package** nên ký hiệu C như trên. Bản production phải kiểm tra mã trả về của `pthread_mutex_lock/unlock`, quản lý lỗi và vòng đời native resource; phần này tập trung vào thứ tự khóa và callback.

**Phản ví dụ C (chỉ minh họa lỗi, không ghép vào chương trình chạy):**

```c
pthread_mutex_lock(&native_mutex);
(*env)->CallVoidMethod(env, self, on_event, event_id);
pthread_mutex_unlock(&native_mutex); // Có thể không đến được đây.
```

Callback `onEvent` gọi `readSequence` rồi lại chờ `native_mutex` đang do lời gọi `emit` bên ngoài giữ. Đây là cùng luồng nhưng mutex native không được giả định có khả năng tái nhập. Tương tự, trong Java không viết `synchronized (stateLock) { emit(); }` vì callback hoặc worker có thể cần lại monitor ấy.

## 5. Khi callback thật sự chạy trên luồng C riêng

Ví dụ JNI ở trên callback **đồng bộ trên luồng gọi Java**, nên `JNIEnv *env` do JVM truyền vào đã hợp lệ. Nếu thư viện C tự tạo `pthread` rồi gọi Java, phải xét thêm:

1. Lưu `JavaVM *` thích hợp, dùng `AttachCurrentThread` để lấy `JNIEnv *` **trên chính luồng đang callback**, và `DetachCurrentThread` khi luồng native tự attach hoàn tất công việc. Không chuyển `JNIEnv *` từ luồng này sang luồng khác.
2. Nếu object Java cần tồn tại qua thời điểm native method ban đầu trả về, dùng JNI **global reference** (`NewGlobalRef`) với quy tắc tạo/xóa rõ ràng (`DeleteGlobalRef`). Không giữ `jobject` local reference qua lifetime của callback bất đồng bộ.
3. Không giữ mutex C khi `AttachCurrentThread`, gọi callback Java, chờ callback hoặc thực hiện tác vụ có thể chặn. Không giữ Java monitor khi đợi native worker.
4. Thiết kế shutdown: đánh dấu `closing`, dừng phát sự kiện mới, xử lý callback đang chạy, hoàn tất hủy/timeout, giải phóng global ref và tài nguyên C **sau** khi chắc chắn callback không còn dùng chúng.
5. Xác định nơi chạy callback: nếu callback thao tác UI hoặc một executor chuyên trách, chuyển event sang executor thích hợp. Việc gửi vào queue phải được thiết kế để không chặn lúc đang giữ mutex.

Với JNI, Java exception xuất hiện trong callback được giữ thành **pending exception** trên luồng JNI. Sau `CallVoidMethod`, native code có thể dùng `ExceptionCheck` để nhận biết; hoặc để exception truyền trở lại Java khi native method trả về. Không tùy tiện gọi tiếp các JNI API không được phép trong lúc exception pending; nếu chủ động `ExceptionClear` thì phải có chính sách chuyển/ghi nhận lỗi, không âm thầm nuốt exception. Trong ví dụ trên, `DeleteLocalRef` là thao tác cleanup được phép và C trả về ngay.

Đặc biệt, vùng giữa `GetPrimitiveArrayCritical` và `ReleasePrimitiveArrayCritical` có ràng buộc JNI nghiêm ngặt: không gọi JNI khác hoặc thao tác có thể chặn chờ Java thread. Vì vậy **không callback, không khóa chờ, không I/O chặn** khi còn giữ con trỏ critical. Với native memory thông thường, quy tắc vòng đời, race và đồng bộ vẫn phải được thiết kế riêng.

## 6. Trạng thái, thứ tự và vòng đời khi callback tái nhập

Một thiết kế chỉ “nhả khóa rồi callback” vẫn chưa đủ nếu giao thức dữ liệu không chặt. Nên mô tả request theo ID và các trạng thái, ví dụ:

```text
CREATED → REGISTERED/PENDING → COMPLETED
                       ├──────→ FAILED
                       └──────→ CANCELLED/TIMED_OUT
callback muộn hoặc trùng → kiểm tra ID/state → bỏ qua hoặc ghi nhận có kiểm soát
```

- **Đăng ký trước khi gọi:** tạo `requestId`, cất callback/future/state `PENDING`, rồi mới gọi C. Callback inline được xử lý như callback bình thường.
- **Chuyển trạng thái một lần:** dưới một khóa ngắn hoặc qua CAS/atomic phù hợp, chỉ một đường thắng từ `PENDING` sang trạng thái kết thúc. Callback trùng không hoàn tất future hai lần hoặc giải phóng buffer hai lần.
- **Chấp nhận thứ tự bất kỳ:** callback có thể xảy ra trước khi native call trả về, hoặc nhiều callback có thứ tự khác với thời điểm gửi. Dùng ID/số phiên bản (*generation*) để loại bỏ sự kiện từ phiên làm việc cũ.
- **Tách cập nhật state khỏi hành động ngoài:** lấy danh sách listener/kết quả cần phát khi đang giữ khóa, **release** rồi mới gọi listener hoặc `CompletableFuture.complete` vì completion handler có thể chạy ngay trên luồng đang gọi và tái nhập hệ thống.
- **Ownership rõ ràng:** ai cấp phát/giải phóng buffer C, khi nào Java được đọc, và callback có thể đến sau `close()` không? Hủy logic không tự động dừng C đang chạy; phải có giao thức dừng/quiescence trước khi free.
- **Không đánh đồng memory model:** `volatile`/monitor/atomic ở Java bảo đảm theo quy tắc Java Memory Model đối với biến Java; mutex/atomic C bảo vệ state C theo quy tắc C/native. Việc phối hợp trạng thái xuyên biên cần một giao thức publish/snapshot/copy có chứng cứ; không coi hai khóa khác nhau là một hàng rào bộ nhớ chung. `volatile` riêng lẻ cũng không bảo vệ thao tác ghép nhiều trường.

Nếu nhất thiết phải lồng khóa ở một nhánh nội bộ, lập thứ tự khóa chính thức như `M_J trước M_C` và chứng minh **mọi** đường gọi, kể cả callback và error cleanup, tuân thủ. Với callback tùy ý từ C vào Java, quy tắc “không gọi xuyên biên khi giữ khóa” thường dễ kiểm soát hơn thứ tự khóa toàn cục.

## 7. Các lỗi thường gặp và cách kiểm tra

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Treo chỉ khi C callback gọi lại một native function | `CallVoidMethod` chạy khi còn giữ mutex C; mutex bị lấy lại. | Chụp state, unlock trước callback; tránh dùng recursive mutex như cách vá mặc định. |
| Treo chỉ khi callback chạy trên native worker | Luồng Java giữ monitor trong lúc `join/get/await`; worker cần monitor đó. | Nhả monitor trước khi chờ; callback commit state trong vùng khóa ngắn. |
| Chạy được một luồng nhưng treo dưới tải | ABBA, lock order ẩn qua helper, listener hoặc ngoại lệ. | Vẽ đồ thị chờ giữa thread/lock; audit cả đường callback và cleanup. |
| Callback báo “unknown request” | Trạng thái `pending` được đăng ký sau khi gọi native; callback chạy inline. | Đăng ký/công bố state trước crossing. |
| Hoàn thành hai lần, use-after-free | Callback trùng hoặc đến sau timeout/close. | State machine theo ID/generation, kết thúc một lần, ownership và quiescence. |
| Deadlock không xuất hiện trong Java thread dump | Luồng đang nằm ở `pthread_mutex_lock` hoặc syscall native. | Kết hợp `jcmd <pid> Thread.print -l` với native backtrace (`gdb`/`lldb`) khi phù hợp. |

**Bộ kiểm thử tối thiểu** nên gồm:

1. Callback inline ngay trong native call, có gọi ngược API C lần nữa; đảm bảo không deadlock và thứ tự state hợp lệ.
2. Callback từ luồng native khác trong khi Java caller đang đợi kết quả, với timeout có giới hạn; kiểm tra caller không còn giữ monitor.
3. Hai luồng chạy đường `Java → C` và `C → Java` đồng thời, cố tạo trường hợp lock order đảo; chạy lặp nhiều lần với barrier/latch.
4. Callback ném exception, lỗi lookup JNI và đường hủy: mọi nhánh nhả khóa, không mất lỗi, không dùng reference đã bị giải phóng.
5. Callback trùng/đến muộn, đóng module trong lúc callback, và thử luồng native tự attach/detach.

Kiểm thử đồng thời nên có **timeout có giới hạn** để phát hiện treo và thu thập bằng chứng, không để CI treo vô thời hạn. Để xác định nguyên nhân, ghi log `requestId`, thread name/id, điểm `lock/unlock` và hướng đi `Java→C`/`C→Java`; không gọi logger có thể chặn ngay trong đoạn khóa nguy hiểm.

## 8. Danh sách tự kiểm trước khi tích hợp

- [ ] Hợp đồng callback nêu rõ inline/async, thread, tính tái nhập, số lần, thứ tự và lỗi.
- [ ] Không có monitor Java hay mutex C bị giữ xuyên lời gọi có thể callback/chặn.
- [ ] Mọi thay đổi state trước crossing đã được commit/công bố; callback tìm được request ngay cả khi chạy inline.
- [ ] Callback chỉ commit dữ liệu ngắn trong khóa; mọi lời gọi listener, JNI, `complete`, chờ/I/O chạy ngoài khóa.
- [ ] Có chính sách lock order cho trường hợp khóa lồng thực sự không tránh được.
- [ ] JNI `JNIEnv` đúng luồng; local/global refs, exception pending và attach/detach đúng vòng đời.
- [ ] Có quy tắc hủy, timeout, callback trùng/đến muộn và giải phóng memory an toàn.
- [ ] Có test cho đồng bộ, đa luồng, tái nhập lồng, lỗi và shutdown; có cách quan sát cả Java lẫn native stack.

**Nguyên tắc nhớ lâu:** đưa trạng thái về nhất quán **trước** khi qua biên; **nhả khóa** rồi mới để mã Java/C gọi lẫn nhau; callback **kiểm tra và ghi state ngắn gọn**, sau đó tiếp tục các hành động có khả năng tái nhập ở ngoài khóa.

### Tài liệu tham khảo

- [Oracle JNI Specification — JNI Functions (Call Methods, MonitorEnter/Exit, Critical Arrays)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Oracle JNI Specification — Invocation API (AttachCurrentThread, DetachCurrentThread)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Java Language Specification — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
