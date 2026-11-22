# Dừng callback và luồng nền trước khi giải phóng thư viện hoặc handle

> **Ngữ cảnh:** Java Advance → Native Interoperability → Vòng đời JNI. Bài học giải thích vì sao shutdown là một giao thức đồng bộ có thứ tự: **ngăn callback mới → dừng nhận việc → chờ các callback/worker đang chạy kết thúc → giải phóng handle, JNI global reference và thư viện native**. Nếu đảo thứ tự, lỗi thường là use-after-free, crash JVM, deadlock hoặc JVM không thể kết thúc.

## 1. Vì sao một lệnh free đơn giản chưa đủ?

Trong JNI, Java có thể mở một **native session**, tạo handle C/C++, đăng ký callback vào SDK, tạo thread pool hoặc `pthread` và cho native gọi ngược về Java. Những tài nguyên này có vòng đời không giống nhau:

- **Handle native:** con trỏ/ID do C/C++/SDK cấp; có thể chứa mutex, queue, trạng thái và pointer đến tài nguyên OS.
- **Callback registration:** SDK giữ một function pointer và thường giữ cả `void* userData` trỏ đến context của ứng dụng. SDK có thể gọi lại từ thread mà ứng dụng không kiểm soát.
- **Native worker:** thread nền còn thực thi mã C/C++, có thể đang ngủ, xử lý buffer, gọi JNI hoặc callback.
- **JNI global reference:** giữ Java listener/object sống qua ranh giới JNI frame và native thread; cần `DeleteGlobalRef` khi không còn ai sử dụng.
- **Dynamic library:** `.so` / `.dylib` / `.dll` chứa mã hàm callback/worker; nếu thư viện bị unload trong lúc thread còn chạy vào mã của nó, instruction pointer/function pointer có thể trở thành không hợp lệ.
- **Java facade:** lớp `AutoCloseable`/service giữ native handle và cung cấp API cho caller Java.

Ví dụ nguy hiểm:

```text
Java gọi nativeClose(handle)
   -> free(handle) NGAY
   -> DeleteGlobalRef(listener) NGAY
   -> dlclose(nativeLibrary) NGAY
                           |
                           v
     SDK callback hoặc worker vẫn chạy:
       onEvent(handle->listener)
       truy cập handle đã free / gọi mã trong library đã unload
                           |
                           v
                  crash / memory corruption / UB
```

Dù chỉ một callback đến muộn, lỗi đã có thể xảy ra. `try/catch` của Java không thể cứu một JVM đã gặp native memory corruption. Điều cần đảm bảo là **không còn đường thực thi nào có thể chạm tài nguyên trước khi giải phóng**.

## 2. Bốn kiểu hoạt động cần phân biệt

| Kiểu | Callback xảy ra ở đâu? | Điều kiện kết thúc đúng |
|---|---|---|
| **Callback đồng bộ trong native call** | SDK gọi callback trước khi API native trả về | Chờ mọi lời gọi native đang hoạt động kết thúc; callback đã return |
| **Callback bất đồng bộ từ SDK** | SDK quản lý worker/event loop riêng | Unregister, hiểu chính xác guarantee của unregister, chờ callbacks *đang chạy* và callbacks còn trong queue |
| **Native worker do ứng dụng tạo** | `pthread`, `std::thread`, worker pool | Set stop flag/cancel, wake, join/await termination, bảo đảm không còn native instruction sử dụng state |
| **Java callback dispatcher/Executor** | Java `ExecutorService` hay message queue | Ngừng enqueue, đợi task/callback đã nhận kết thúc, đóng Java executor theo hợp đồng |

**Unregister không nhất thiết đồng nghĩa quiescent.** Có SDK đảm bảo sau khi `unregister` trả về thì callback đã hoàn toàn ngừng; có SDK chỉ ngăn đăng ký mới, còn một callback đã bắt đầu vẫn đang chạy. Phải đọc hợp đồng cụ thể; nếu không có cam kết rõ, dùng bộ đếm `inFlight`, signal/barrier hoặc stop-acknowledgement riêng.

**Join một worker cũng chưa đủ** nếu vẫn còn callback từ thread của SDK khác. Cần xác định toàn bộ nguồn gọi vào handle và library: Java calls, native worker, external callback, timer, queued task và Java executor.

## 3. State machine và thứ tự shutdown chuẩn

Một mô hình có thể dùng được:

```text
                  open/start success
                          |
                          v
                       OPEN
               nhận request, callback
                          |
                          | close() / stop request
                          v
                      CLOSING
         reject new work, unregister/cancel
                          |
                          | callbacks in-flight = 0
                          | workers joined, Java tasks drained
                          v
                     QUIESCENT
                không còn ai dùng state
                          |
                          | DeleteGlobalRef
                          | free native handle/buffer
                          | unload library nếu được quản lý
                          v
                       CLOSED
```

Trình tự cụ thể:

1. **Đổi trạng thái** `OPEN → CLOSING` dưới mutex/atomic/CAS. Từ đó, API mới trả `closed`/`shutting down`. Thao tác `close` lặp phải idempotent hoặc có chính sách rõ về caller nào đang thực hiện cleanup.
2. **Ngắt nguồn tạo callback:** tắt timer, rút registration khỏi SDK, ngăn task mới được enqueue, gửi tín hiệu stop cho worker; **đánh thức** thread đang đợi condition variable/queue I/O.
3. **Kết thúc việc đang chạy:** cho in-flight operations kết thúc hoặc hủy có hợp đồng; đợi counter về 0, queue drain hoặc drop có chính sách. Không free `userData` trong khi callback có thể còn dereference.
4. **Join/await worker:** đợi thread thực sự kết thúc; với worker đã attach JVM, nó phải dọn local refs/exception rồi `DetachCurrentThread` trước khi return.
5. **Giải phóng tài nguyên cấp thấp:** chỉ sau quiescence mới `DeleteGlobalRef`, `free/delete` native state, close socket/file/context, tháo callback trampoline. Nếu ứng dụng sở hữu `dlopen`/`LoadLibrary` handle, cân nhắc `dlclose`/`FreeLibrary` **cuối cùng**, sau khi bảo đảm không còn function pointer hoặc instruction nào tới thư viện.
6. **Công bố CLOSED:** Java facade đặt handle = 0 hoặc đánh dấu CLOSED và bảo đảm mọi caller đã đợi cùng shutdown hoàn thành. Không phát thông báo “đã đóng” trước khi worker/callback thực sự quiescent.

Đây là **thứ tự logic**, không phải mọi hệ thống đều cần gọi cả sáu API. SDK có thể gộp stop+join; một session không có worker thì không cần join. Nhưng bất biến “không ai còn sử dụng trước khi free/unload” luôn áp dụng.

### Hai quy tắc đồng bộ

- **Không giữ mutex mà callback cần trong lúc chờ callback hoặc join.** Ví dụ thread A giữ `state.mutex` rồi `pthread_join`, worker B muốn lock mutex để kiểm tra `stopping` → deadlock.
- **Không gọi close dạng blocking từ chính worker/callback mà close đang chờ.** `pthread_join(pthread_self())` là deadlock/lỗi; callback đồng bộ gọi `close()` khi close đang giữ một Java monitor khác cũng có thể treo. Tách `requestStop()` không chặn với `awaitStopped()` chạy từ control thread độc lập.

## 4. In-flight callback và ranh giới release

Giả sử SDK dùng function pointer `nativeCallback(void *ctx, Event *ev)`. Một callback cần “quyền sử dụng” context từ lúc bắt đầu cho đến lúc return.

Đoạn mô hình dưới đây **là pseudocode C**, không phải file biên dịch độc lập:

```c
// protected by mutex state->lock
bool beginCallback(State *state) {
    lock(state->lock);
    if (state->closing) {
        unlock(state->lock);
        return false;
    }
    state->inFlight++;
    unlock(state->lock);
    return true;
}

void endCallback(State *state) {
    lock(state->lock);
    state->inFlight--;
    if (state->closing && state->inFlight == 0) {
        signal(state->drained);
    }
    unlock(state->lock);
}

// shutdown thread:
lock(state->lock);
state->closing = true;
unlock(state->lock);

sdk_unregister_callback(); // cần kiểm tra guarantee của SDK
lock(state->lock);
while (state->inFlight != 0) {
    wait(state->drained, state->lock);
}
unlock(state->lock);
// Chỉ sau khi chắc chắn SDK không thể bắt đầu callback mới
// và inFlight==0, mới được hủy state/userData.
```

**Điểm tinh vi:** `beginCallback(state)` cũng dereference `state`. Nếu SDK vẫn có thể gọi vào `ctx=state` sau khi `free(state)`, ngay cả thao tác tăng counter đã là use-after-free. Vì vậy counter đơn lẻ **không** thay thế hợp đồng unregister/quiescence của SDK. Phải chặn callback bắt đầu trước khi hủy context, hoặc để callback trampoline/context sống bằng một owner độc lập có reference counting và điểm release an toàn.

Nếu SDK unregister ngăn invocation mới nhưng không đợi invocation cũ, có thể dùng counter để đợi callback còn hoạt động. Nếu SDK không có barrier nào bảo đảm callback cuối cùng đã được phát, cần xây một tầng dispatch có lifetime riêng, hoặc tránh unload/free cho tới khi nguồn callback thực sự tắt.

## 5. JNI resources: trước và sau khi worker dừng

### `JNIEnv*` và `JavaVM*`

`JNIEnv *env` chỉ hợp lệ với **thread sở hữu**; không chuyển `env` từ Java caller sang worker. Lấy `JavaVM*` qua `GetJavaVM` hoặc `JNI_OnLoad`, rồi trên native worker gọi:

```c
// Trích đoạn minh họa trong native-created thread:
JNIEnv *env = NULL;
jint rc = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);
if (rc == JNI_EDETACHED) {
    if ((*vm)->AttachCurrentThread(vm, (void **)&env, NULL) != JNI_OK) {
        // Không gọi JNI khi chưa attach.
        return;
    }
    // Thread này cần DetachCurrentThread trước khi thoát.
} else if (rc != JNI_OK) {
    // Không có JNIEnv hợp lệ.
    return;
}
```

Khi thread kết thúc phải dọn mọi JNI local references và bộ nhớ acquired, giải quyết pending Java exception, sau đó `DetachCurrentThread` **nếu chính thread native đã attach**. Không tự detach một Java-created thread đang có Java frame. Dùng `AttachCurrentThreadAsDaemon` không biến worker thành “tự động sạch”; daemon vẫn cần stop và dọn resources theo contract.

### Strong global reference

Nếu callback muốn gọi `listener.onEvent(...)` sau khi JNI method Java→native trả về, tham số `jobject listener` ở native method vốn chỉ là **local reference**. Trước khi chuyển sang worker:

```c
// Trong native entrypoint ở thread Java, env thuộc thread này.
jobject listenerGlobal = (*env)->NewGlobalRef(env, listener);
if (listenerGlobal == NULL) {
    // Xử lý lỗi JNI/pending exception; không start worker.
}
// Nếu thành công: worker đã attach được dùng listenerGlobal.
// Chỉ DeleteGlobalRef sau khi chắc chắn mọi callback dừng.
```

`jmethodID` và `jfieldID` không phải local/global references, nhưng chúng cũng phụ thuộc vòng đời class loader. Giữ global ref đến listener/class có thể giữ loader còn sống; nếu không xóa, thư viện JNI có thể không bao giờ đạt điều kiện để JVM unload.

**Không dùng `DeleteGlobalRef` như lệnh “hủy mọi callback”.** Lệnh chỉ xóa một JNI root. Nếu worker vẫn dùng đối tượng, nó có thể dùng handle đã xóa. Phải stop/join/drain trước rồi mới delete.

### Exception trong callback

Nếu native worker gọi Java bằng `CallVoidMethod` và Java callback ném exception, exception sẽ **pending trên worker JNI thread**; nó không tự chuyển sang Java thread gọi `close`. Worker phải quan sát `ExceptionCheck`, log/translate hoặc chuyển exception về owner bằng một global reference có quản lý vòng đời. Đừng tiếp tục gọi JNI APIs tùy tiện khi exception pending; đừng âm thầm `ExceptionClear` mà không có chính sách báo lỗi.

## 6. Ví dụ hoàn chỉnh Java 17+ / JNI C: close đợi callback và worker

Ví dụ này tạo **một background pthread** trong thư viện JNI. Java đăng ký callback; Java gửi từng giá trị `1`, `2`, `3` cho native worker; worker attach JVM, gọi `listener.onEvent(value)`, rồi chờ sự kiện tiếp theo. Khi `Session.close()` được gọi trên luồng điều khiển, JNI đặt stop flag, đánh thức worker, **join**, xóa global reference và giải phóng state.

Thiết kế cố ý **đơn giản và có giới hạn** để nhìn rõ thứ tự:

- Một session có một worker và tối đa **một request chờ** (single-slot mailbox). Java đợi callback trước khi gửi request kế tiếp.
- `submit` và `close` trên Java session được tuần tự hóa bằng `synchronized`, tránh việc free handle trong lúc một submit đang dùng. Callback mẫu chỉ ghi vào `BlockingQueue`, **không gọi ngược `submit` hay `close`**.
- Khi đóng, worker xử lý request còn trong mailbox rồi thoát. `close` thành công bảo đảm worker đã kết thúc; không có callback đang chạy sau khi `close` trả về.
- Đây là ví dụ quản lý native handle, **không gọi `dlclose` trực tiếp**. JVM quản lý thư viện được load bởi `System.loadLibrary`. Bài mục 8 bàn về unload thực tế.
- Môi trường build bên dưới: **Linux, GCC, pthread, JDK 17+**, `JAVA_HOME` trỏ tới JDK; không áp dụng nguyên lệnh Linux cho Windows.

### 6.1. Java facade: `JniLifecycleDemo.java`

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public final class JniLifecycleDemo {
    static {
        System.loadLibrary("lifecyclejni");
    }

    @FunctionalInterface
    public interface Listener {
        void onEvent(int value);
    }

    private static native long nativeOpen(Listener listener);
    private static native void nativeSubmit(long handle, int value);
    private static native int nativeClose(long handle);

    static final class Session implements AutoCloseable {
        // Chỉ truy cập handle trong các synchronized methods.
        private long handle;

        Session(Listener listener) {
            if (listener == null) {
                throw new IllegalArgumentException("listener is null");
            }
            handle = nativeOpen(listener);
            if (handle == 0L) {
                throw new IllegalStateException("nativeOpen failed");
            }
        }

        synchronized void submit(int value) {
            if (handle == 0L) {
                throw new IllegalStateException("session is closed");
            }
            nativeSubmit(handle, value);
        }

        @Override
        public synchronized void close() {
            if (handle == 0L) {
                return; // idempotent
            }

            // nativeClose chặn đến khi worker đã join và free state.
            // Nếu nó ném trước khi free, vẫn giữ handle để sửa/retry.
            int workerError = nativeClose(handle);
            handle = 0L;

            if (workerError != 0) {
                throw new IllegalStateException(
                        "worker failed: " + workerError);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> received = new LinkedBlockingQueue<>();

        try (Session session = new Session(received::offer)) {
            for (int expected = 1; expected <= 3; expected++) {
                session.submit(expected);
                Integer actual = received.poll(5, TimeUnit.SECONDS);
                if (actual == null || actual != expected) {
                    throw new IllegalStateException(
                            "unexpected callback: " + actual);
                }
                System.out.println("event = " + actual);
            }
        }

        // Chỉ in sau khi close đã join worker và giải phóng state.
        System.out.println("closed");
    }
}
```

`received::offer` thích ứng với `Listener.onEvent(int)`: kiểu trả về `boolean` của `offer` được bỏ đi với functional method trả `void`. `BlockingQueue` là cấu trúc thread-safe. `poll(5, TimeUnit.SECONDS)` hạn chế thời gian **đợi event trong demo**; nó không phải timeout cho `close`, vì chờ native thread kết thúc có thể cần chính sách riêng.

**Một ràng buộc quan trọng của mẫu:** callback được gọi trên native worker và **không được gọi `Session.close()` hoặc bất kỳ synchronized method nào trên Session**. Nếu gọi close từ callback, có thể self-join; nếu main đang giữ Session monitor khi join thì callback đang đòi monitor cũng có thể gây deadlock. Ứng dụng cần dừng từ callback nên **gửi yêu cầu stop sang control executor khác**; thiết kế production có thể tách `requestStop` và `awaitStopped`.

### 6.2. Sinh JNI header

```bash
javac -encoding UTF-8 -h . JniLifecycleDemo.java
```

Compiler sinh `JniLifecycleDemo.h`. Ba phương thức `native` là `static`, nên tham số thứ hai của JNI C function là `jclass`. Tham số `long handle` của Java tương ứng `jlong` trong JNI.

### 6.3. Native implementation: `JniLifecycleDemo.c`

```c
#include <jni.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include "JniLifecycleDemo.h"

typedef struct {
    JavaVM *vm;
    jobject listenerGlobal;
    jmethodID onEventId;
    pthread_t worker;
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    int stopping;
    int hasPending;
    jint pendingValue;
    int workerError;
} State;

static void throwState(JNIEnv *env, const char *message) {
    // Nếu Java exception đã pending, giữ nguyên nguyên nhân.
    if ((*env)->ExceptionCheck(env)) return;
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalStateException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

static void *workerMain(void *arg) {
    State *state = (State *)arg;
    JNIEnv *env = NULL;

    // Native-created thread phải attach và lấy JNIEnv riêng.
    if ((*state->vm)->AttachCurrentThread(
            state->vm, (void **)&env, NULL) != JNI_OK) {
        pthread_mutex_lock(&state->mutex);
        state->workerError = 1;
        state->stopping = 1;
        state->hasPending = 0;
        pthread_mutex_unlock(&state->mutex);
        return NULL;
    }

    for (;;) {
        pthread_mutex_lock(&state->mutex);
        while (!state->stopping && !state->hasPending) {
            pthread_cond_wait(&state->changed, &state->mutex);
        }

        // Khi closing nhưng vẫn có một event chờ: xử lý nốt event.
        if (!state->hasPending) {
            pthread_mutex_unlock(&state->mutex);
            break;
        }

        jint value = state->pendingValue;
        state->hasPending = 0;
        pthread_mutex_unlock(&state->mutex);

        // Không giữ mutex khi callback sang Java.
        (*env)->CallVoidMethod(
                env, state->listenerGlobal, state->onEventId, value);

        if ((*env)->ExceptionCheck(env)) {
            // Trong demo: báo lỗi qua workerError, tránh bỏ qua.
            (*env)->ExceptionDescribe(env);
            (*env)->ExceptionClear(env);
            pthread_mutex_lock(&state->mutex);
            state->workerError = 2;
            state->stopping = 1;
            state->hasPending = 0;
            pthread_mutex_unlock(&state->mutex);
            break;
        }
    }

    // Không còn Java callback/frame đang chạy trên worker.
    if ((*state->vm)->DetachCurrentThread(state->vm) != JNI_OK) {
        pthread_mutex_lock(&state->mutex);
        state->workerError = 3;
        pthread_mutex_unlock(&state->mutex);
    }
    return NULL;
}

JNIEXPORT jlong JNICALL Java_JniLifecycleDemo_nativeOpen(
        JNIEnv *env, jclass owner, jobject listener) {
    (void)owner;

    if (listener == NULL) {
        throwState(env, "listener is null");
        return 0;
    }

    State *state = (State *)calloc(1, sizeof(*state));
    if (state == NULL) {
        throwState(env, "out of native memory");
        return 0;
    }

    if (pthread_mutex_init(&state->mutex, NULL) != 0) {
        free(state);
        throwState(env, "mutex init failed");
        return 0;
    }

    if (pthread_cond_init(&state->changed, NULL) != 0) {
        pthread_mutex_destroy(&state->mutex);
        free(state);
        throwState(env, "condition init failed");
        return 0;
    }

    if ((*env)->GetJavaVM(env, &state->vm) != JNI_OK) {
        goto fail;
    }

    jclass listenerClass = (*env)->GetObjectClass(env, listener);
    if (listenerClass == NULL) goto fail;

    state->onEventId = (*env)->GetMethodID(
            env, listenerClass, "onEvent", "(I)V");
    (*env)->DeleteLocalRef(env, listenerClass);
    if (state->onEventId == NULL) goto fail;

    // Chuyển local listener thành global trước khi start pthread.
    state->listenerGlobal = (*env)->NewGlobalRef(env, listener);
    if (state->listenerGlobal == NULL) goto fail;

    if (pthread_create(&state->worker,
                       NULL, workerMain, state) != 0) {
        goto fail;
    }

    // Java long là opaque native handle; chỉ còn hợp lệ đến close.
    return (jlong)(intptr_t)state;

fail:
    // Chỉ vào nhánh này trước khi worker được tạo.
    if (state->listenerGlobal != NULL) {
        (*env)->DeleteGlobalRef(env, state->listenerGlobal);
    }
    pthread_cond_destroy(&state->changed);
    pthread_mutex_destroy(&state->mutex);
    free(state);
    throwState(env, "nativeOpen failed");
    return 0;
}

JNIEXPORT void JNICALL Java_JniLifecycleDemo_nativeSubmit(
        JNIEnv *env, jclass owner, jlong handle, jint value) {
    (void)owner;

    if (handle == 0) {
        throwState(env, "closed handle");
        return;
    }
    State *state = (State *)(intptr_t)handle;
    int failure = 0;

    pthread_mutex_lock(&state->mutex);
    if (state->stopping || state->workerError != 0) {
        failure = 1;
    } else if (state->hasPending) {
        // Demo có đúng một slot, không ghi đè request chưa xử lý.
        failure = 2;
    } else {
        state->pendingValue = value;
        state->hasPending = 1;
        pthread_cond_signal(&state->changed);
    }
    pthread_mutex_unlock(&state->mutex);

    if (failure == 1) throwState(env, "session stopping");
    if (failure == 2) throwState(env, "pending slot is full");
}

JNIEXPORT jint JNICALL Java_JniLifecycleDemo_nativeClose(
        JNIEnv *env, jclass owner, jlong handle) {
    (void)owner;
    if (handle == 0) return 0;

    State *state = (State *)(intptr_t)handle;

    // Không bao giờ join chính callback/worker thread.
    if (pthread_equal(pthread_self(), state->worker)) {
        throwState(env, "close from callback thread");
        return -1;
    }

    pthread_mutex_lock(&state->mutex);
    state->stopping = 1;
    pthread_cond_broadcast(&state->changed);
    pthread_mutex_unlock(&state->mutex);

    // Join không được giữ mutex: worker cần mutex để thoát.
    if (pthread_join(state->worker, NULL) != 0) {
        // Không free state: worker có thể vẫn đang sử dụng nó.
        throwState(env, "pthread_join failed");
        return -1;
    }

    int result = state->workerError;

    // Không còn worker/callback sử dụng listener hoặc State.
    (*env)->DeleteGlobalRef(env, state->listenerGlobal);
    pthread_cond_destroy(&state->changed);
    pthread_mutex_destroy(&state->mutex);
    free(state);
    return result;
}
```

**Vì sao không có use-after-free trong demo khi dùng đúng hợp đồng?**

- Java `Session.submit` và `Session.close` là `synchronized`, nên chỉ một trong hai đang chuyển handle vào JNI tại một thời điểm; `close` không free khi một `submit` vẫn đang trong native function.
- `nativeOpen` tạo JNI strong global reference và khởi tạo mutex/condition **trước** khi khởi chạy worker. Trên thất bại trước `pthread_create`, code dọn tài nguyên vừa cấp phát.
- Worker tạo `JNIEnv*` trên **chính** thread của mình, gọi Java listener bằng global ref. Callback kết thúc trước khi worker đi tiếp; mutex không bị giữ trong lúc vào Java.
- `nativeClose` đặt `stopping` và `pthread_cond_broadcast` để đánh thức worker chờ; worker xử lý event còn trong một slot rồi thoát.
- `pthread_join` là **barrier**: sau join, worker không thể còn dùng `State` hoặc listener global ref. Chỉ khi đó caller gọi `DeleteGlobalRef`, destroy mutex/condition và `free`.
- Java `close` chuyển handle về `0` **sau** khi nativeClose hoàn thành. Nếu callback ném Java exception, worker log/clear nó, đánh dấu `workerError`; `nativeClose` hoàn tất cleanup rồi trả mã lỗi để Java ném exception sau khi handle đã được đặt về 0.
- Nếu `pthread_join` thất bại, code **không free** state để tránh use-after-free. Trong chương trình thực cần cơ chế recovery và đóng control plane để không rò tài nguyên; không giả định join luôn thành công mà bỏ qua return code.

**Giới hạn giáo dục:** ví dụ bảo vệ **một worker** và ba JNI methods của **Session**. Nó không hỗ trợ nhiều producer native gọi trực tiếp cùng handle, callback gọi phương thức `Session`, hoặc SDK bên ngoài giữ function pointer. Các trường hợp này cần ownership/refcount, callback-registration barrier và cơ chế shutdown riêng ở mục 4, 7, 9.

### 6.4. Biên dịch/chạy

```bash
gcc -std=c11 -fPIC -pthread -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o liblifecyclejni.so JniLifecycleDemo.c

java -Djava.library.path=. JniLifecycleDemo
```

Với JDK 24+ trên classpath có thể cấp native access tường minh:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. JniLifecycleDemo
```

**stdout khi chạy thành công:**

```text
event = 1
event = 2
event = 3
closed
```

`System.loadLibrary("lifecyclejni")` ánh xạ tên logic `lifecyclejni` tới `liblifecyclejni.so` trên Linux. Với macOS, cần `.dylib`/`include/darwin` và bộ flag phù hợp; với Windows, dùng DLL, JNI headers `include/win32` và API thread tương ứng. Không thể dùng nguyên lệnh `pthread`/GCC Linux như build cross-platform duy nhất.

## 7. Những giới hạn về handle và concurrency mà hệ thống thật phải giải quyết

### 7.1. `long` là địa chỉ, không có cơ chế lifetime tự động

Một lớp Java thường giữ `long nativeHandle` để truyền vào JNI. Cast như `(State*)(intptr_t)handle` **không kiểm tra** pointer đã bị free hay chưa. Số `0` chỉ là sentinel theo thỏa thuận; handle khác 0 vẫn có thể là stale pointer.

Nếu nhiều Java threads cùng sử dụng session, cần guard **mọi native entrypoint**:

- Lock cùng một lifecycle monitor quanh check+use của handle; hoặc
- Bảng handle có generation/token và reference count, bảo đảm `acquire(handle)` tăng in-flight usage trước khi close xóa entry; hoặc
- Native wrapper dùng shared ownership, CAS/atomic state machine và dọn sau khi last reference rời scope.

Không tách rời `if (handle != 0) nativeUse(handle)` khỏi một thao tác `close` có thể xảy ra đồng thời. Đây là check-then-use race. Java `volatile` hoặc `AtomicLong.get()` **một mình** không giữ native pointer sống; `AtomicLong.getAndSet(0)` chỉ chặn double-close, chưa đủ nếu operation khác đã lấy handle rồi vẫn còn chạy.

### 7.2. Callback có thể vào cùng lúc với close

Đừng chỉ chặn `nativeSubmit` nếu external SDK vẫn có thể gọi callback. Cần cùng lifecycle guard cho SDK callback registration, timer và native observer. Phân biệt số lượng `inFlightJavaCalls`, `inFlightNativeCallbacks` và `workerThreads` theo toàn bộ đường dùng state.

### 7.3. Shutdown lặp hoặc đồng thời

Một close idempotent chuẩn nên bảo đảm **mọi caller thấy closed chỉ khi cleanup hoàn tất**. Nếu caller A bắt đầu cleanup còn caller B gọi close, B nên chờ cùng completion (hoặc nhận một future/closed status có contract rõ), không chỉ thấy handle=0 rồi trả về khi worker của A vẫn chạy.

Với Java class trong ví dụ, `synchronized close` khiến caller B đợi A hoàn tất trước khi vào method, đáp ứng điều đó. Tuy nhiên callback không được lock vào cùng Session monitor khi A đang join. Thiết kế production phức tạp hơn có thể dùng `CompletableFuture<Void> stopped` với không đồng bộ hóa trên đường callback.

## 8. Unload thư viện native: JVM khác với `dlclose`/`FreeLibrary`

### `System.loadLibrary` không tạo “close library” theo session

`System.loadLibrary(...)` load và liên kết native library cho class loader; Java standard API **không cung cấp** đối xứng `System.unloadLibrary` cho mỗi `Session.close`. `Session.close` nên dọn **session resources** của chính nó; JVM quản lý vòng đời thư viện theo runtime/class loader.

Theo JNI Invocation API, thư viện có thể xuất:

```c
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_6;
}

// Nếu export JNI_OnUnload, JVM có thể gọi khi class loader
// chứa thư viện được garbage-collected.
JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    // Chỉ cleanup thận trọng; tránh gọi Java callbacks tùy ý.
}
```

Đây là **trích đoạn minh họa**, không cần thêm hai hàm này vào ví dụ mục 6. `JNI_OnUnload` chạy trong ngữ cảnh không xác định, có thể không được gọi đúng thời điểm `Session.close` và không nên dùng làm nơi duy nhất chờ callback/worker kết thúc hoặc gọi Java tùy ý. Global references chưa giải phóng có thể giữ class loader còn sống, càng làm việc dựa vào `JNI_OnUnload` không đáng tin.

### Handle thư viện do ứng dụng tự load

Nếu JNI wrapper của bạn dùng `dlopen`/`dlsym` hoặc `LoadLibrary`/`GetProcAddress` để load một plugin C/C++ thứ hai, thì **plugin handle** có lifetime độc lập với thư viện JNI wrapper và từng native session. Cần đảm bảo:

1. Không còn request/callback/worker nào có thể đi vào plugin.
2. Không còn callback function pointer, vtable, code pointer hay pending task thuộc plugin có thể bị gọi lại.
3. Tài nguyên do plugin tạo đã được destroy bằng API tương ứng trong lúc code plugin **vẫn đang load**.
4. Mọi native thread có khả năng thực thi plugin đã join/quiescent.
5. Chỉ sau các bước đó mới release plugin library reference bằng `dlclose`/`FreeLibrary`.

Không gọi unload ngay từ một callback hoặc chính một hàm thuộc plugin đang thực thi. `dlclose`/`FreeLibrary` không thay thế giao thức quiescence; bản thân dynamic linker có thể giữ module vì reference khác, nhưng không được dựa vào điều đó để hợp thức hóa lifetime sai.

## 9. Deadlock và callback tái nhập: lý do phải tách stop với wait

Ví dụ deadlock điển hình:

```text
Thread A (controller)                Thread B (native worker)
lock(state.mutex)
state.stopping = true
pthread_join(B)  ---------------->    lock(state.mutex)  (bị chặn)
   A chờ B                             B chờ A
                        => DEADLOCK
```

Đúng: đặt stop flag dưới mutex, signal/broadcast, **unlock mutex**, sau đó mới join. Nếu callback từ B sang Java có thể yêu cầu một lock Java mà A đang giữ trong `close`, deadlock tương tự xảy ra **xuyên qua JNI boundary**.

Một API production có thể tách:

```java
// Pseudocode Java: triển khai cụ thể tùy executor và native SDK.
session.requestStop();          // Không blocking, không tự join.
session.stopped().join();       // Chỉ control thread gọi để chờ barrier.
session.releaseResources();     // Chỉ sau stopped barrier.
```

Điều quan trọng là kiểm soát **ai chờ ai**, không nhất thiết mọi API đều phải tên như vậy.

Quy tắc callback:

- Callback có thể báo `stopRequested` hoặc enqueue một command vào control thread.
- Callback không tự join thread hiện tại, không giành lifecycle monitor đang bị close nắm giữ.
- Native callback trampoline tránh giữ mutex nội bộ khi gọi Java vì Java callback có thể gọi lại native, tạo reentrancy.
- Nếu SDK đòi callback trả về nhanh, đừng block chờ toàn bộ shutdown trong callback; ghi nhận event rồi để controller thực hiện cleanup.
- Nếu callback ném exception, chuyển sang trạng thái lỗi và đóng có trật tự; đừng giải phóng context ngay khi đang ở giữa native callback.

## 10. Timeout, cancellation và lỗi khi shutdown

“Đợi worker hoàn tất” không có nghĩa là được phép đợi mãi trong production. Nhưng **timeout không được biến thành `free` cưỡng bức khi worker còn chạy**.

Các trường hợp:

| Tình huống | Cách xử lý đúng |
|---|---|
| Worker chờ condition variable | Đặt stop flag, `signal`/`broadcast`, sau đó join |
| Worker bị kẹt trong blocking I/O | Dùng I/O cancel/close/socket shutdown có contract; sau đó chờ thực sự thoát |
| Worker đang chạy native call không hỗ trợ cancellation | Báo shutdown chưa hoàn tất, giữ state/library sống; cân nhắc cô lập native work trong helper process |
| SDK unregister trả về nhưng còn in-flight callback | Đợi quiescence barrier/counter trước khi free |
| Callback Java ném exception | Xử lý/ghi nhận trên thread JNI, chuyển lỗi về owner; không tiếp tục JNI calls tùy tiện khi pending |
| `pthread_join` thất bại | Không hủy state có thể vẫn đang được worker sử dụng; cần recovery/diagnostics |
| `close` bị gọi nhiều lần | Chỉ một caller cleanup, caller khác đợi completion hoặc nhận trạng thái đã đóng thật sự |
| JVM đang shutdown | Dừng nhận task, đóng session từ lifecycle owner, giới hạn và log timeout; không phụ thuộc hoàn toàn vào shutdown hook |

Nếu user yêu cầu “đóng trong 2 giây” nhưng plugin có thể treo vĩnh viễn, mô hình **cùng tiến trình** có giới hạn an toàn: không thể đảm bảo vừa trả về ngay vừa `free` state mà không có stop acknowledgement. Giải pháp thường là helper **process** riêng để có thể terminate process sau timeout và cách ly crash, hoặc SDK có cancellation/quiescence contract mạnh.

**POSIX `pthread_cancel` cũng không phải nút reset an toàn**: cancellation xảy ra ở những điểm nhất định, đòi cleanup handlers và rất dễ làm bỏ sót mutex/global refs/SDK state. `Thread.stop` trong Java có rủi ro tương tự về invariant. Ưu tiên cooperative stop và protocol rõ ràng.

## 11. Cleaner, AutoCloseable và startup/shutdown ứng dụng

`AutoCloseable` và `try-with-resources` là lựa chọn phù hợp cho session sống theo scope của Java:

```java
// Trích đoạn minh họa, sử dụng Session của mục 6.
try (var session = new JniLifecycleDemo.Session(value -> {
    System.out.println(value);
})) {
    session.submit(42);
    // Trong ứng dụng thật cần đợi callback và tuân thủ thread rules.
}
// AutoCloseable.close() thực hiện stop/join/free theo contract.
```

`Cleaner`/finalizer **không** phù hợp làm biện pháp shutdown chính cho background worker native:

- Thời điểm GC/Cleaner không xác định; code vẫn đang chạy có thể giữ JNI global ref đến Java object, khiến GC không thể thu dọn object đó.
- Cleaner thread có thể chạy trong ngữ cảnh không phù hợp để join một callback đang cần Java resources/lock.
- Dùng Cleaner như safety net cũng phải có ownership/refcount và lộ trình quiescence; không trực tiếp `free(pointer)` nếu native worker còn dùng.

Trong server, đặt `close` ở lifecycle owner rõ ràng: component `stop`/shutdown hook được kiểm soát, `@PreDestroy` nếu framework quản lý và bảo đảm thứ tự dependency, hoặc phần quản lý native session tập trung. Không dựa duy nhất vào OS process exit để biện minh rò handles khi ứng dụng hot-reload/plugin-reload.

**Thứ tự shutdown giữa các component cũng quan trọng:** ngừng upstream producer trước, dừng callback/worker kế tiếp, giải phóng plugin session, rồi mới stop executor/VM phụ thuộc. Tắt Java executor mà native callback còn cần nó có thể gây lost events hoặc exception trong teardown.

## 12. Chiến lược kiểm thử và quan sát lỗi lifecycle

Một số bài test có thể xác minh bằng hành vi:

1. **Normal close:** mở session, gửi vài event, đợi nhận, close; kiểm tra không có callback nào sau khi close thành công.
2. **Close khi mailbox có event:** gửi event rồi close; xác định rõ chính sách drain/drop và số lần callback, không để use-after-free.
3. **Double close:** close 2 lần; lần thứ hai không gọi `DeleteGlobalRef`/`free` thêm lần nào.
4. **Submit sau close:** nhận exception/trạng thái closed rõ ràng; không dereference stale handle.
5. **Parallel submit vs close:** tạo race có kiểm soát; bảo đảm entrypoint đã acquire handle trước close, hoặc trả closed, không crash.
6. **Callback slow/blocked:** cho callback đợi trên latch; kiểm tra close chờ đúng barrier, rồi giải phóng sau khi callback được nhả. Test cần control thread độc lập để không tự gây deadlock.
7. **Callback ném exception:** native worker báo lỗi về lifecycle owner, dọn JNI references và thoát thread.
8. **Native worker startup failure:** inject lỗi tạo thread/allocation, bảo đảm không leak global refs/mutex.
9. **SDK callback sau unregister:** mô phỏng callback chạy trễ và xác minh lifetime protocol của dispatcher.
10. **Plugin reload/unload:** mở/đóng nhiều vòng với class loader hoặc plugin handle phù hợp, bảo đảm không có callback gọi code đã unload.

Công cụ hữu ích:

- **`-Xcheck:jni`:** giúp phát hiện một số lỗi JNI (reference/thread/method usage), nhưng không chứng minh C memory safety.
- **AddressSanitizer / UndefinedBehaviorSanitizer:** tìm use-after-free, out-of-bounds và UB trong native code; cấu hình toolchain và process phù hợp.
- **ThreadSanitizer / race detectors:** hữu ích cho data race C/C++ (chạy với JVM có thể có giới hạn tương thích; thường kiểm thử thành phần native riêng trước).
- **Heap/native memory monitoring:** theo dõi global refs, native allocations, thread count và số session ACTIVE/CLOSING để phát hiện rò.
- **Structured logs:** log session ID, thread ID, lifecycle state, `inFlight` count, queue depth, callback start/end, stop request và join completion. Không log raw pointer như định danh nghiệp vụ duy nhất.

Test nhiều lần và xen kẽ lịch chạy có thể phát hiện race, nhưng **không chứng minh không có race**. Cần bất biến ownership cùng kết quả từ công cụ kiểm tra.

## 13. Bảng lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| `DeleteGlobalRef(listener)` khi callback đang chạy | Stale reference/use-after-delete | Unregister, chờ callback quiescent, rồi delete |
| `free(state)` ngay khi set stop flag | Worker vẫn dereference state | Signal, join/await, rồi free |
| `dlclose` khi thread/callback còn trong library | Gọi mã không còn hợp lệ, crash | Bảo đảm mọi code path quiescent trước unload |
| Chỉ gọi SDK unregister rồi free, không biết guarantee | Callback in-flight truy cập freed userData | Xác minh SDK contract, barrier/refcount |
| `pthread_join` khi giữ mutex mà worker cần | Deadlock | Unlock trước join |
| `close` trong native callback đang chạy | Self-join hoặc lock inversion | Callback chỉ requestStop; controller thread await |
| Java `long` handle được đọc không lock khi close đồng thời | Check-then-use race, stale pointer | Monitor/acquire-release/refcount hoặc handle registry |
| `AtomicLong.getAndSet(0)` được xem là bảo vệ mọi native calls | Có thể còn in-flight call cầm pointer cũ | Track in-flight entrypoints, đóng sau khi drain |
| Không wake worker đang đợi queue | `join` treo | Signal/broadcast/sentinel event sau stop |
| Worker không `DetachCurrentThread` | Leak thread attachment; JVM có thể chưa tắt | Dọn local refs và detach khi native-created thread rời JVM |
| Chỉ dựa vào Cleaner/`JNI_OnUnload` | Cleanup không đúng thời điểm hoặc không xảy ra | Explicit owner lifecycle và `AutoCloseable` |
| Java callback ném exception rồi native tiếp tục bình thường | Pending exception che khuất lỗi, trạng thái dở dang | Log/translate, stop có trật tự và báo lỗi |
| Timeout rồi giải phóng dù worker chưa dừng | Hủy tài nguyên đang sử dụng | Timeout trả trạng thái chưa dừng, giữ resource hoặc cô lập process |

## 14. Bài tập tự kiểm chứng (kèm đáp án)

**Bài 1 — xác định thứ tự.** Một plugin đăng ký `sdk_register(callback, state)` rồi bắt đầu hai worker. Khi shutdown, đội phát triển viết `free(state); sdk_unregister(callback); join(workers);`. Sai ở đâu?

**Đáp án:** `state` bị free trước khi SDK ngừng callback và worker kết thúc. Phải ngăn việc mới, unregister với guarantee ngăn callback mới, chờ in-flight callbacks, signal/join workers rồi mới free state và cuối cùng unload plugin nếu có.

**Bài 2 — ngăn double free.** Java giữ `AtomicLong handle`; close dùng `getAndSet(0)` rồi free. Có đủ an toàn khi `submit` chạy đồng thời không?

**Đáp án:** **Chưa.** Thread submit có thể đã đọc handle cũ trước getAndSet rồi vào JNI sau free. Cần lock quanh check+use hoặc native handle registry/refcount/acquire barrier.

**Bài 3 — callback tự close.** Native worker gọi Java listener, listener lập tức gọi `session.close()`; `nativeClose` cố `pthread_join` worker. Điều gì xảy ra?

**Đáp án:** Thread đang callback có thể tự join hoặc bị lock inversion. Callback chỉ gửi `requestStop`; một controller độc lập thực hiện `awaitStopped` và release sau khi callback return.

**Bài 4 — JNI_OnUnload.** Tại sao đặt toàn bộ stop/join/free vào `JNI_OnUnload` không bảo đảm vòng đời đúng khi người dùng nhấn “close session”?

**Đáp án:** `JNI_OnUnload` liên quan đến class loader/native library lifecycle, không phải thời điểm Java session close; nó có thể chạy trong ngữ cảnh không phù hợp để Java callback hoặc không được gọi đúng lúc. Session phải có explicit close.

**Bài 5 — timeout.** Callback bị kẹt trong native function không hỗ trợ cancel. Có thể `dlclose` sau khi đợi 1 giây rồi cho Java tiếp tục không?

**Đáp án:** **Không an toàn.** Callback vẫn có thể thực thi mã/tài nguyên đã unload. Báo trạng thái timeout, giữ library/state còn sống cho đến quiescence, hoặc cô lập trong helper process để có chính sách terminate process.

**Bài 6 — release reference.** Worker đã `DetachCurrentThread` nhưng SDK callback khác vẫn giữ pointer đến listener global. Có thể `DeleteGlobalRef` chưa?

**Đáp án:** **Chưa.** Detach một worker không bảo đảm mọi nguồn callback khác đã dừng. Cần dừng nguồn callback còn lại và barrier trên tất cả in-flight paths.

## 15. Checklist quyết định trước khi giải phóng

Trước mọi `free`, `DeleteGlobalRef`, `dlclose`/`FreeLibrary` hoặc destroy SDK handle, lần lượt xác nhận:

- [ ] State đã đổi khỏi `OPEN` và API không nhận thêm request/registration mới.
- [ ] SDK callback/timer/event source không thể khởi tạo callback mới theo contract đã kiểm chứng.
- [ ] Các callback đang chạy và request đang sử dụng handle đã hoàn tất, hủy an toàn hoặc được giữ tài nguyên sống.
- [ ] Queue/worker đã nhận stop, được đánh thức và mọi thread cần thiết đã join/await.
- [ ] Không còn Java/native method đang giữ pointer đã định free.
- [ ] JNI worker đã xử lý pending exception và detach nếu được attach từ native.
- [ ] JNI local refs, global refs và native buffers có owner duy nhất, release đúng thứ tự.
- [ ] Không có callback code/function pointer còn có thể được gọi trong plugin sắp unload.
- [ ] Lệnh close từ callback/reentrant thread không tự chờ chính nó và không giữ mutex gây deadlock.
- [ ] Chỉ khi mọi điều trên đạt, handle/library được release rồi session được công bố CLOSED.

**Kết luận:** JNI shutdown đúng là một **quiescence protocol**. `stop` chỉ biểu thị ý định; `join`, callback barriers và in-flight tracking tạo bằng chứng không còn người sử dụng; **`free`/`DeleteGlobalRef`/library unload phải nằm sau bằng chứng đó**.

### Tài liệu chính thức

- [JNI Specification — Invocation API: Attach/Detach/GetEnv, JNI_OnLoad và JNI_OnUnload](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html)
- [JNI Specification — JNI Functions: NewGlobalRef, DeleteGlobalRef, exception APIs](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [JNI Specification — Design Overview: JNI Interface Pointers và Reference Management](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html)
- [Java 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [POSIX — pthread_join](https://pubs.opengroup.org/onlinepubs/9699919799/functions/pthread_join.html)
