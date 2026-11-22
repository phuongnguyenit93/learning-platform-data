# MonitorEnter, MonitorExit và nguy cơ bế tắc khi gọi lại Java đang giữ khóa

## 1. Bài toán: đồng bộ qua ranh giới Java ↔ JNI

Trong module **Java Advance – native-interoperability**, nhóm **Luồng với JNI**, native code có thể phải bảo vệ trạng thái của một đối tượng Java đang được nhiều thread truy cập. JNI cung cấp `MonitorEnter` và `MonitorExit` để tham gia **cùng object monitor** mà Java dùng với `synchronized`. Tuy nhiên, gọi ngược từ C/C++ vào Java (*callback*) trong khi đang giữ khóa là một chỗ nguy hiểm: callback có thể đợi một khóa khác, một worker hoặc một nhiệm vụ bất đồng bộ, tạo thành **chu trình chờ** và gây deadlock.

Bài này giải thích chính xác **khi nào callback cùng khóa là tái nhập hợp lệ**, **khi nào callback có thể bế tắc**, và xây một chương trình Java 17+ / C11 chạy được với:
- Một JNI method lấy monitor của object rồi gọi Java `synchronized` method **trong cùng thread**; đây là **reentrancy**, không phải deadlock mặc định.
- Một JNI method cập nhật dữ liệu dưới monitor, **thả monitor trước khi gọi Java callback** để giảm vùng rủi ro.
- Một callback ném Java exception; C vẫn `MonitorExit`, không bỏ khóa.
- Một thread Java khác kiểm tra khóa đã thực sự được giải phóng sau exception.
- Lệnh build trên Linux, macOS, Windows, stdout chuẩn và bảng chẩn đoán deadlock.

Các kỹ năng sau bài: đọc đúng `JNIEnv *` / `jobject` / `jint`, kiểm tra return codes, đối xứng lock–unlock cả trên đường lỗi, hiểu reentrant monitor, nhận ra AB–BA lock ordering, kiểm tra thread dumps và thiết kế callback không giữ khóa không cần thiết.

**Giới hạn:** bài tập trung vào **object monitor JNI**; C mutex (`pthread_mutex_t`, `CRITICAL_SECTION`, `std::mutex`) là **loại khóa khác**, không được thay `MonitorExit` bằng unlock của C mutex hoặc ngược lại.

## 2. Một Java object, cùng monitor, hai cách truy cập

Một Java object có monitor mà Java có thể vào bằng:

~~~java
// Fragment minh họa. lock là một Java object hợp lệ.
synchronized (lock) {
    // Chỉ một thread sở hữu monitor này tại một thời điểm.
}
~~~

Nếu code C nhận một `jobject lock` hợp lệ, nó có thể vào **chính monitor của object đó**:

~~~c
/* Fragment C bên trong JNI method, với env/lock hợp lệ. */
jint result = (*env)->MonitorEnter(env, lock);
if (result != JNI_OK) {
    return;  /* Không sở hữu monitor; không gọi MonitorExit. */
}

/* Phần được bảo vệ bởi monitor của lock. */

jint exit_result = (*env)->MonitorExit(env, lock);
if (exit_result != JNI_OK) {
    return;  /* Đây là lỗi; không giả định unlock thành công. */
}
~~~

Sự loại trừ tương hỗ áp dụng cho cùng **object identity** dù lệnh enter đến từ Java bytecode hay từ JNI. Ví dụ, Java `synchronized (lock)` và C `MonitorEnter(env, lock)` cạnh tranh cùng một khóa.

### Trạng thái monitor và reentrancy

~~~text
Object monitor M của State
  owner: chưa có                count=0
  Thread T gọi JNI MonitorEnter count=1, owner=T
  C gọi ngược State.add()      synchronized trên cùng State
  Thread T vào lại M           count=2, owner=T
  Java method return           count=1, owner=T
  C JNI MonitorExit            count=0, owner=none
~~~

**Monitor là reentrant:** thread đã sở hữu monitor được vào lại nó mà không tự chặn chính mình. Vì thế:

- JNI thread T giữ monitor của `state`.
- JNI gọi `CallVoidMethod(state, add, ...)`.
- `State.add` được khai báo `synchronized` trên **cùng `state`**.
- Callback thực thi **đồng bộ trên chính T**, tăng reentrance count, rồi quay lại C.

Kịch bản này **không tự động deadlock**, vì không có thread khác chiếm monitor và không có chu trình chờ. Tuy nhiên, callback có thể khóa **object khác**, đợi `Future.get()`, gọi native API khác hoặc phối hợp với một worker khác. Chỉ cần phát sinh thứ tự lấy khóa ngược chiều là vẫn có nguy cơ deadlock.

### Không trộn hai cơ chế release

Dù dùng chung monitor, **entry của JNI và entry do Java bytecode tạo phải được release bằng đúng cơ chế đã acquire**:

- `MonitorEnter` của JNI **phải** có `MonitorExit` của JNI tương ứng. Không được dựa vào dấu `}` của Java `synchronized`, return từ Java synchronized method hoặc return khỏi native method để trả lại phần khóa do JNI sở hữu.
- Monitor entry do Java `synchronized` / bytecode `monitorenter` tạo **không được** giải phóng bằng `MonitorExit` của JNI.
- Java tự tạo đường `monitorexit` cho `synchronized` trong `finally` tương ứng; mã C của bạn **phải tự viết cleanup** cho mọi nhánh sau khi `MonitorEnter` thành công.

Đặc tả JNI có đề cập việc `DetachCurrentThread` giải phóng JNI monitors trong một số tình huống, nhưng **không được thiết kế code dựa vào việc detach để thay thế cleanup chuẩn**: detached thread có quy tắc riêng, và Java-owned thread không được detach tùy tiện.

## 3. `MonitorEnter`, `MonitorExit`: prototype, status, quyền sở hữu

Hai hàm có prototype JNI:

~~~c
jint MonitorEnter(JNIEnv *env, jobject obj);
jint MonitorExit(JNIEnv *env, jobject obj);
~~~

Cách gọi trong file **C**:

~~~c
jint status = (*env)->MonitorEnter(env, obj);
/* ... */
jint exit_status = (*env)->MonitorExit(env, obj);
~~~

Trong **C++** JNI header cung cấp cú pháp wrapper khác:

~~~cpp
jint status = env->MonitorEnter(obj);
// ...
jint exit_status = env->MonitorExit(obj);
~~~

Mã C/C++ ở trên là **fragments**, không phải chương trình độc lập. Đừng trộn cú pháp C++ vào file `.c`.

| Mục | `MonitorEnter` | `MonitorExit` |
|---|---|---|
| Tham số thứ hai | `jobject` hợp lệ, **không NULL** | Cùng object đã enter, **không NULL** |
| Hành động | Lấy monitor; nếu thread khác đang giữ thì chờ | Giảm reentrance count do thread hiện tại sở hữu; đến 0 thì thả |
| Thành công | Trả `JNI_OK` = `0` | Trả `JNI_OK` = `0` |
| Thất bại | Giá trị âm, không coi là đã giữ khóa | Giá trị âm; ví dụ có thể ném `IllegalMonitorStateException` nếu thread không sở hữu |
| Yêu cầu | `env` gắn với thread hiện tại; object ref còn hợp lệ | **Cùng thread đang là owner**; đếm đủ các lần JNI enter |
| Lỗi thiết kế | Truyền NULL, deadlock vì khóa đang do thread khác sở hữu | Quên exit, exit thiếu/thừa, exit từ thread khác |

`JNI_OK` không chỉ mang nghĩa “không có exception” mà là **acquire thành công**. Nếu `MonitorEnter` trả lỗi, không đặt cờ `locked = 1` và không gọi `MonitorExit` bừa bãi. Nếu enter thành công, phải có một đường cleanup được thực thi **chính xác một lần cho mỗi entry của JNI**. Nếu cùng thread enter hai lần bằng JNI, phải exit hai lần bằng JNI; việc gọi một Java `synchronized` method ở giữa không bù hộ số entry của JNI.

### Vì sao `env` và `obj` cũng cần đúng lifetime?

- `JNIEnv *env` chỉ hợp lệ cho thread mà JVM cấp nó; không gửi nguyên `env` sang native worker rồi lock hộ. Worker tự attach vào JVM nếu cần, lấy `JNIEnv *` của chính mình.
- `jobject obj` từ tham số JNI là local reference hợp lệ trong phạm vi JNI call. Nếu C lưu object qua callback bất đồng bộ hoặc sau khi call return, cần tạo global reference thích hợp và có đường `DeleteGlobalRef`. **Giữ monitor không biến một local ref thành global ref**.
- `obj == NULL` là **vi phạm tiền điều kiện** của hai monitor calls. Không trông chờ JVM xử lý NULL “an toàn” trên mọi nền tảng.
- Đừng cast địa chỉ từ `malloc` hoặc con trỏ C++ thành `jobject`; monitor này thuộc Java object.

### Đồng bộ bộ nhớ

Khi cùng monitor của một Java object được enter/exit đúng quy tắc, logic đồng bộ tương ứng với Java monitor lock/unlock: Java/C code phải tuân thủ cùng lock discipline đối với dữ liệu được bảo vệ. Ví dụ Java `synchronized int value()` và JNI `MonitorEnter(state)` rồi `SetIntField` giúp tránh truy cập cạnh tranh **trong phạm vi những đường đi cũng dùng monitor ấy**. Một code path khác đọc/ghi field trần không giữ khóa vẫn phá vỡ giao thức đồng bộ.

## 4. Ba dạng callback để phân biệt reentrancy với deadlock

### A. Reentrant callback cùng monitor, cùng thread

~~~text
Thread T
  JNI MonitorEnter(State)      -- M(State) owner=T, count=1
    CallVoidMethod(State.add)  -- Java synchronized State.add
      Java monitorenter State -- M(State) owner=T, count=2
      add value
      Java monitorexit        -- count=1
  JNI MonitorExit(State)       -- count=0
~~~

Đây là trường hợp được dùng có kiểm soát trong `callbackInside` của chương trình bên dưới. Vẫn nên hạn chế gọi code không biết trước trong vùng khóa: callback ở tương lai có thể đổi hành vi, lấy thêm khóa hay chờ thread khác.

### B. AB–BA: JNI giữ B rồi callback cần A; thread khác giữ A rồi cần B

~~~text
          Thread T1 (JNI callback)             Thread T2 (Java + JNI)
         --------------------------------     ---------------------------
         JNI MonitorEnter(lockB)              synchronized(lockA)
         giữ lockB                            giữ lockA
         CallVoidMethod(listener.onEvent)     gọi JNI MonitorEnter(lockB)
             synchronized(lockA)                 chờ lockB do T1 giữ
                 chờ lockA do T2 giữ
         --------------------------------     ---------------------------
                  T1 đợi A                      T2 đợi B

                            A -> B -> A (chu trình chờ)
~~~

T1 không thể hoàn thành callback để thoát `MonitorExit(lockB)` vì cần A. T2 không thể thoát `synchronized(lockA)` vì đang đợi B. Đây là **deadlock thật**, kể cả hai monitor đều reentrant: reentrancy chỉ giúp một thread vào lại **monitor mình đang sở hữu**, không cấp quyền vào monitor do thread khác giữ.

**Quy tắc phá chu trình:** một cách thường hiệu quả là **thả B trước callback** rồi mới để Java callback khóa A. Tất nhiên nếu code gọi JNI từ Java đang giữ các khóa khác, phải xét toàn bộ lock graph, không chỉ hai dòng JNI.

### C. Giữ monitor rồi chờ một thread cần chính monitor đó

~~~text
Thread T1: JNI MonitorEnter(state)
           CallVoidMethod(Java.onEvent)
             Java onEvent: Future.get() / join() đợi T2
Thread T2: synchronized(state) để hoàn tất task
           bị T1 giữ monitor
=> T1 đợi T2, T2 đợi T1
~~~

Dù callback chạy trên cùng T1, nó có thể **đợi thread khác**. Vì thế “monitor reentrant” **không có nghĩa callback luôn an toàn khi đang khóa**. Một callback có thể tự tạo deadlock gián tiếp qua thread pool, UI event dispatch thread, completion callback hoặc native mutex.

## 5. Nguyên tắc cleanup: try/finally ở Java, đường thoát chung ở JNI

Java `synchronized` tự nhả monitor bằng bytecode ngay cả khi exception thoát ra. JNI C không có cơ chế tự động như vậy:

~~~c
/* Fragment C minh họa cấu trúc cleanup; obj/env phải hợp lệ. */
jint entered = (*env)->MonitorEnter(env, obj);
if (entered != JNI_OK) {
    return;
}

/* Đã có ownership. Mọi nhánh sau đây phải tới cleanup. */
do_work_under_lock();      /* Hàm ứng dụng minh họa, có thể lỗi. */

/* Không bỏ bước này kể cả khi JNI/Java đã ném exception. */
jint exited = (*env)->MonitorExit(env, obj);
if (exited != JNI_OK) {
    return;               /* Báo lỗi theo contract ứng dụng. */
}
~~~

Đoạn minh họa chưa có `goto cleanup` nên **không được** chèn thêm `return` bên trong `do_work_under_lock`. Với native method phức tạp, dùng **một nhãn cleanup** và cờ `locked` hoặc RAII C++ scope guard được kiểm thử. Không gọi `MonitorExit` ở nhánh `MonitorEnter` thất bại.

### CallVoidMethod có thể ném Java exception, nhưng vẫn phải unlock

JNI callback:

~~~c
(*env)->CallVoidMethod(env, obj, method_id, arg);
~~~

có thể để lại **pending Java exception**, ví dụ callback Java ném `IllegalArgumentException`. Lúc này native C không được tùy ý gọi thêm các JNI methods có thể không an toàn khi exception đang pending. Tuy nhiên, JNI spec cho phép dùng **`MonitorExit`** ở trạng thái có pending exception. Cấu trúc hợp lệ:

~~~c
if ((*env)->MonitorEnter(env, obj) != JNI_OK) return;

(*env)->CallVoidMethod(env, obj, callback_id, arg);

/* Bắt buộc nhả JNI monitor ngay cả nếu callback ném exception. */
jint rc = (*env)->MonitorExit(env, obj);
if (rc != JNI_OK) return;

/* Nếu callback ném exception, trả về Java để exception lan truyền.
   Không gọi callback JNI khác khi exception còn pending. */
if ((*env)->ExceptionCheck(env)) return;
~~~

`ExceptionCheck` ở đây chỉ **kiểm tra**, không xóa exception. Khi native method return mà còn pending exception, JVM chuyển Java exception đó tới Java caller. Không tự `ExceptionClear` rồi in “thành công” trừ khi API được thiết kế để **xử lý và chuyển đổi** lỗi theo contract minh bạch.

Nếu `MonitorExit` báo lỗi (đặc biệt `IllegalMonitorStateException`), đó là **vi phạm ownership nghiêm trọng**, không được bỏ qua như một cảnh báo vô hại. Một JNI monitor bị giữ không cân xứng có thể làm các thread khác treo mãi.

## 6. Ví dụ Java 17+ và C11 đầy đủ: callback trong lock, callback ngoài lock và exception

Cây dự án:

~~~text
jni-monitor/
├─ src/
│  └─ demo/
│     └─ jni/
│        └─ MonitorLesson.java
├─ native/
│  ├─ demo_jni_MonitorLesson.h   # Generated by javac -h
│  └─ monitor_lesson.c
├─ out/
│  └─ demo/jni/MonitorLesson.class
└─ libmonitorlesson.so          # Linux;
                               # macOS: libmonitorlesson.dylib
                               # Windows: monitorlesson.dll
~~~

Các file `.class` và `.h` do `javac` sinh; bạn **không** tạo thủ công. Các lệnh dưới đây chạy từ thư mục dự án `jni-monitor`.

### 6.1. Java source hoàn chỉnh

Tạo file **`src/demo/jni/MonitorLesson.java`**:

~~~java
package demo.jni;

import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public final class MonitorLesson {
    static { System.loadLibrary("monitorlesson"); }

    private MonitorLesson() {}

    public static final class State {
        private int value;
        private int notices;

        public synchronized void add(int delta) {
            if (delta < 0) {
                throw new IllegalArgumentException("negative delta");
            }
            value += delta;
        }

        public synchronized void onNotice() { notices++; }
        public synchronized int value() { return value; }
        public synchronized int notices() { return notices; }
    }

    private static native void callbackInside(State state, int delta);
    private static native void updateThenNotify(State state, int delta);

    public static void main(String[] args) throws Exception {
        State state = new State();

        callbackInside(state, 2);
        System.out.println("afterInside=" + state.value());

        updateThenNotify(state, 3);
        System.out.println("afterOutside=" + state.value()
                + ", notices=" + state.notices());

        try {
            callbackInside(state, -1);
            throw new AssertionError("Exception expected");
        } catch (IllegalArgumentException expected) {
            if (!"negative delta".equals(expected.getMessage())) {
                throw expected;
            }
            System.out.println("caught=" + expected.getMessage());
        }

        FutureTask<Integer> probe = new FutureTask<>(state::value);
        Thread verifier = new Thread(probe, "monitor-verifier");
        verifier.setDaemon(true);
        verifier.start();
        if (probe.get(5, TimeUnit.SECONDS) != 5) {
            throw new AssertionError("Unexpected state after exception");
        }

        updateThenNotify(state, 1);
        System.out.println("afterRecovery=" + state.value()
                + ", notices=" + state.notices());
        System.out.println("RESULT: PASS");
    }
}
~~~

**Ý nghĩa từng bước:**

- `State.add` và `State.value` cùng khóa intrinsic monitor của **chính instance `state`**. `State.onNotice` cũng synchronized trên instance đó.
- `callbackInside(state, 2)`: JNI `MonitorEnter(state)` → `CallVoidMethod(state.add)` → Java `synchronized add` tái nhập trên **cùng thread** → JNI `MonitorExit`. Kết quả `value==2`.
- `updateThenNotify(state, 3)`: JNI cập nhật `value` từ 2 thành 5 dưới monitor, gọi `MonitorExit`, rồi mới callback `onNotice`, nên `notices==1`. Đó là mẫu **update–unlock–notify**.
- `callbackInside(state, -1)` gọi Java callback ném `IllegalArgumentException("negative delta")`. C **vẫn gọi `MonitorExit` trước khi trở về**. Java catch chỉ kiểm tra đúng lỗi cần thiết, không vô tình che lỗi JNI.
- `FutureTask` trong thread Java khác gọi `state.value()` — thao tác cần monitor của state. `get(5, TimeUnit.SECONDS)` tạo kiểm tra **có giới hạn thời gian**: nếu monitor bị JNI giữ sau exception, thread kiểm tra có thể không hoàn thành. Timeout là test safety phụ thuộc scheduling (có thể false fail trên máy quá tải), không phải chứng cứ thời gian thực của GC/VM; trong đường chạy bình thường nó hoàn thành.
- Sau kiểm tra, `updateThenNotify(state, 1)` tăng từ 5 lên 6 và notification lên 2. Không có đường Java nào in `RESULT: PASS` trước khi mọi kiểm tra hoàn tất.

**Giới hạn hợp đồng:** trạng thái `value` và `notices` được bảo vệ bởi monitor của `state`, và demo chỉ thao tác các giá trị nhỏ để tránh tràn `jint`. Một thư viện thật cần kiểm tra overflow và các invariants dữ liệu riêng. Cách chọn `private` cho các fields Java không khiến field bất khả truy cập bằng JNI; JNI có thể lấy field ID khi có quyền tương ứng theo JNI API.

### 6.2. Sinh header JNI và kiểm tra descriptor

Tạo cây thư mục, sau đó chạy:

~~~sh
mkdir -p src/demo/jni native out
javac --release 17 -h native -d out src/demo/jni/MonitorLesson.java
javap -s -p -classpath out demo.jni.MonitorLesson
~~~

Trên Windows CMD, có thể tạo `src\demo\jni`, `native`, `out` bằng các lệnh `mkdir` riêng; sau đó dùng `javac --release 17 -h native -d out src\demo\jni\MonitorLesson.java`.

`javac` sinh **`native/demo_jni_MonitorLesson.h`**; JNI names dựa trên `package demo.jni` và `class MonitorLesson`. Cả hai phương thức native đều nhận `State` và `int`, trả `void`. Phần mô tả method từ `javap` sẽ có:

~~~text
private static native void callbackInside(demo.jni.MonitorLesson$State, int);
  descriptor: (Ldemo/jni/MonitorLesson$State;I)V

private static native void updateThenNotify(demo.jni.MonitorLesson$State, int);
  descriptor: (Ldemo/jni/MonitorLesson$State;I)V
~~~

Các dòng trên là **phần trích**, không phải toàn bộ stdout `javap`. Ký hiệu `Ldemo/jni/MonitorLesson$State;` là kiểu Java nested static class trong JVM descriptor; `I` là `int` và `V` là `void`.

Generated C header có các prototype quan trọng:

~~~c
JNIEXPORT void JNICALL Java_demo_jni_MonitorLesson_callbackInside
  (JNIEnv *, jclass, jobject, jint);

JNIEXPORT void JNICALL Java_demo_jni_MonitorLesson_updateThenNotify
  (JNIEnv *, jclass, jobject, jint);
~~~

Vì các method là **`static native`**, phía C có đối số ẩn `JNIEnv *` rồi `jclass`, sau đó mới `jobject state` và `jint delta`. Đừng sửa thủ công generated header, và đừng bỏ `JNIEXPORT/JNICALL`.

### 6.3. C source hoàn chỉnh: luôn thoát monitor trước khi return

Tạo file **`native/monitor_lesson.c`**:

~~~c
#include "demo_jni_MonitorLesson.h"

JNIEXPORT void JNICALL Java_demo_jni_MonitorLesson_callbackInside(
        JNIEnv *env, jclass ignored, jobject state, jint delta) {
    (void)ignored;

    jclass type = (*env)->GetObjectClass(env, state);
    if (type == NULL) return;
    jmethodID add = (*env)->GetMethodID(env, type, "add", "(I)V");
    (*env)->DeleteLocalRef(env, type);
    if (add == NULL) return;

    if ((*env)->MonitorEnter(env, state) != JNI_OK) return;

    (*env)->CallVoidMethod(env, state, add, delta);

    /* Always release even if CallVoidMethod left a pending exception. */
    if ((*env)->MonitorExit(env, state) != JNI_OK) return;
}

JNIEXPORT void JNICALL Java_demo_jni_MonitorLesson_updateThenNotify(
        JNIEnv *env, jclass ignored, jobject state, jint delta) {
    (void)ignored;

    jclass type = (*env)->GetObjectClass(env, state);
    if (type == NULL) return;
    jfieldID value = (*env)->GetFieldID(env, type, "value", "I");
    if (value == NULL) { (*env)->DeleteLocalRef(env, type); return; }
    jmethodID notify = (*env)->GetMethodID(env, type, "onNotice", "()V");
    (*env)->DeleteLocalRef(env, type);
    if (notify == NULL) return;

    if ((*env)->MonitorEnter(env, state) != JNI_OK) return;

    jint old = (*env)->GetIntField(env, state, value);
    if (!(*env)->ExceptionCheck(env)) {
        (*env)->SetIntField(env, state, value, old + delta);
    }

    /* Exit first, including on exceptional paths. */
    if ((*env)->MonitorExit(env, state) != JNI_OK) return;
    if ((*env)->ExceptionCheck(env)) return;

    /* Java callback occurs after releasing this JNI monitor. */
    (*env)->CallVoidMethod(env, state, notify);
}
~~~

**Mã C này đã được biên dịch và chạy với chính Java source ở trên** trên Linux (JDK 21, GCC C11, `-Wall -Wextra -Werror -pedantic`, `-Xcheck:jni`). Trong mã:

1. `GetObjectClass` trả **local reference `jclass`**, `GetMethodID/GetFieldID` lấy ID để gọi method/truy cập field; xóa `jclass` sau khi lookup. Trong demo, ID dùng trong cùng một lời gọi native và class vẫn hiện diện; không cache local class ref qua các lần gọi.
2. Cả hai method **tra cứu method/field IDs trước `MonitorEnter`** để rút ngắn thời gian giữ monitor, tránh lookup/class initialization không cần thiết trong vùng khóa.
3. Mỗi method kiểm tra `MonitorEnter == JNI_OK` trước khi làm việc. Nếu không acquire, **không gọi `MonitorExit`**.
4. `callbackInside` cố ý `CallVoidMethod` khi giữ monitor. Callback Java `State.add` là `synchronized` trên chính state và chạy **cùng thread**, vì vậy là ví dụ reentrant hợp lệ. Nó vẫn có thể ném Java exception.
5. Dù callback ném, lệnh tiếp theo là `MonitorExit`. JNI cho phép giải phóng monitor khi Java exception đang pending; sau đó native method return để exception lan truyền về Java.
6. `updateThenNotify` đọc/ghi field `value` bên trong monitor. `State.value()` ở Java cũng synchronized trên cùng state, nên các code paths trong bài tuân thủ cùng giao thức khóa. Sau `MonitorExit`, nếu không có pending exception, C mới gọi `State.onNotice`.
7. `State.onNotice` vẫn là Java synchronized method, nhưng lúc này **native monitor do method này vừa acquire đã được thả**; do đó giảm nguy cơ lock order AB–BA. Không thể bảo đảm không có deadlock nào khác trong toàn ứng dụng nếu caller vẫn đang giữ khóa khác khi vào JNI.
8. Nếu `MonitorExit` thất bại, method dừng ngay (bản production phải báo/ghi log nguyên nhân theo error policy, không cố thực hiện callback). Một `MonitorExit` cân xứng thành công ở ví dụ này được xác minh bằng các phép thử sau khi native call return.

**Chú ý cú pháp và exception:** `MonitorExit` thuộc những JNI functions được phép gọi khi exception đang pending. Không thêm một `FindClass`, `GetMethodID`, `CallVoidMethod` tùy tiện **giữa callback ném exception và MonitorExit**. Sau `MonitorExit`, `ExceptionCheck` được dùng để quyết định có tiếp tục callback không.

### 6.4. Biên dịch native library trên từng nền tảng

**Linux** (GCC hoặc Clang):

~~~sh
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

cc -std=c11 -Wall -Wextra -pedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Inative \
  -o libmonitorlesson.so native/monitor_lesson.c

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.MonitorLesson
~~~

Nếu đã đặt `JAVA_HOME` đúng gốc JDK, không cần tính lại. `-fPIC` và `-shared` tạo shared object, còn `-I` giúp compiler tìm `jni.h`, `jni_md.h` và header do `javac -h` tạo.

**macOS** (Clang + Xcode Command Line Tools):

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home)"

cc -std=c11 -Wall -Wextra -pedantic -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Inative \
  -o libmonitorlesson.dylib native/monitor_lesson.c

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.MonitorLesson
~~~

Chọn kiến trúc native binary tương ứng với JVM (arm64 với arm64; x86-64 với x86-64). Không dùng đuôi `.so` mặc định Linux nếu môi trường macOS mong `.dylib`.

**Windows** (MSVC Developer Command Prompt, có `cl.exe`, `JAVA_HOME` trỏ JDK):

~~~bat
javac --release 17 -h native -d out src\demo\jni\MonitorLesson.java

cl /nologo /W4 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /Inative ^
  native\monitor_lesson.c /Fe:monitorlesson.dll

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.MonitorLesson
~~~

Dấu `^` để nối dòng của **CMD**, không phải PowerShell. `System.loadLibrary("monitorlesson")` nhận tên logic, JVM ánh xạ ra `libmonitorlesson.so` / `libmonitorlesson.dylib` / `monitorlesson.dll`; Java `-cp out` tìm bytecode, còn `-Djava.library.path=.` tìm native library ở working directory.

### 6.5. Stdout thành công, đã được đối chiếu bằng chạy thật

~~~text
afterInside=2
afterOutside=5, notices=1
caught=negative delta
afterRecovery=6, notices=2
RESULT: PASS
~~~

Kết quả khẳng định đúng **chuỗi hành vi bài tập**:
- Callback trong JNI lock vào lại cùng monitor được, kết quả tăng 2.
- Update–unlock–notify tăng tiếp 3 và notification một lần.
- Callback lỗi đã phát tán `IllegalArgumentException` về Java, và một thread khác vẫn lấy được monitor sau đó.
- Code tiếp tục cập nhật thêm một lần, không để lại monitor bị giữ do lỗi callback.

Kết quả này **không chứng minh mọi callback trong mọi dự án đều an toàn**. Chương trình chủ động chọn callback đơn giản, một object state và các delta nhỏ. Muốn đánh giá production cần kiểm tra thêm lock graph, wait paths, C mutex, thread pool, timeouts, exception paths và shutdown.

## 7. Deadlock AB–BA khi callback trở lại Java đang giữ khóa

### 7.1. Kịch bản mẫu: khác thứ tự acquire hai monitor

Giả sử một library có hai object `lockA` và `lockB`. Một Java callback có thể vào khóa A. Trên luồng T1, JNI code đã `MonitorEnter(lockB)` rồi gọi callback đòi A. Trong lúc đó, T2 đã `synchronized(lockA)` và muốn `MonitorEnter(lockB)`.

~~~text
Thời điểm   Thread T1                                  Thread T2
----------- ------------------------------------------ --------------------------------
t0          JNI MonitorEnter(lockB) thành công
t1                                                     synchronized(lockA) thành công
t2          CallVoidMethod(listener.callback())
t3          callback: synchronized(lockA) -- chờ T2
t4                                                     JNI MonitorEnter(lockB) -- chờ T1
t5          T1 không thể tới MonitorExit(lockB)        T2 không thể thoát synchronized(lockA)
            vì callback chưa xong                     vì JNI call chưa trả về
~~~

Biểu diễn wait-for graph:

~~~text
T1 --needs--> lockA --owned-by--> T2
 ^                                   |
 |                                   v
 +----owned-by-- lockB <--needs------+
~~~

Điều kiện deadlock: có ít nhất hai tác nhân, mỗi tác nhân giữ tài nguyên mà tác nhân kia cần, **không thể tự nhả khóa khi đang chờ**, và tạo **cycle**. Đây không phải lỗi `MonitorEnter` riêng lẻ: cả hai API đều thực hiện đúng mutual exclusion, nhưng **protocol gọi ngược/lock order của ứng dụng** không đúng.

Một fragment Java minh họa logic phía T2 (không runnable độc lập):

~~~java
// Thread T2:
synchronized (lockA) {
    nativeAcquireLockB(lockB);  // JNI MonitorEnter(lockB) có thể chờ T1.
}
~~~

Fragment mô tả phía T1 (chỉ minh họa trình tự JNI):

~~~c
// Thread T1 có JNIEnv *env và local/global refs hợp lệ.
if ((*env)->MonitorEnter(env, lockB) != JNI_OK) return;
/* Gọi Java callback có thể cố synchronized(lockA). */
(*env)->CallVoidMethod(env, listener, callbackMethod);
(*env)->MonitorExit(env, lockB);
~~~

**Không chạy hai fragments này như một demo thực tế không có timeout/kill:** nếu sắp đúng thời điểm, chương trình có thể treo. Khi học lock order nên dùng **timeline và thread dumps** thay vì dựng một deadlock vĩnh viễn rồi kỳ vọng tự phục hồi.

### 7.2. Vì sao `synchronized` callback trên cùng object không cứu được trường hợp AB–BA?

Reentrancy chỉ áp dụng nếu **chính thread đã là owner** của **chính monitor đó**. Trong tình huống AB–BA:
- T1 sở hữu B nhưng callback cần A do T2 sở hữu.
- T2 sở hữu A nhưng native method cần B do T1 sở hữu.

Không thread nào có quyền reenter monitor đang do thread khác giữ. Không có thao tác `MonitorExit` có thể chạy, vì hai thread đang chặn trước đường cleanup.

### 7.3. Vì sao gọi callback ra ngoài lock giúp giảm rủi ro?

Phương án:

~~~text
Trước:
    MonitorEnter(B)
      mutate native/Java state
      CallVoidMethod(Java callback)   <-- callback tùy ý chạy dưới B
    MonitorExit(B)

Sau:
    MonitorEnter(B)
      mutate state / tạo snapshot
    MonitorExit(B)
    CallVoidMethod(Java callback)     <-- B đã được trả lại
~~~

Từ đó, T2 có thể lấy B trong lúc callback của T1 chờ A; **không còn cạnh T1 giữ B → đợi A** do chính critical section này. Nếu callback cần đọc dữ liệu đã được cập nhật, tạo **snapshot bất biến** trong vùng khóa rồi thông báo bằng snapshot sau khi thả khóa, hoặc thiết kế listener nhận một event object copy. Không giữ một tham chiếu tới native buffer có thể bị giải phóng bởi thread khác trong khi callback đang đọc.

**Nhưng:** thả B trước callback không đủ nếu **Java caller** đang giữ một khóa C khác bên ngoài native method, hoặc callback có yêu cầu thứ tự khóa khác. Phải kiểm tra **toàn bộ hành trình Java → native → Java** và thứ tự acquire locks xuyên cả hai ngôn ngữ.

## 8. Chính sách khóa: một thứ tự duy nhất, vùng khóa ngắn, không chờ dưới khóa

Để thiết kế module JNI nhiều threads, hãy xác định **lock hierarchy** ở mức ứng dụng, ví dụ:

~~~text
Lock A (session registry) -> Lock B (per-session state)
Không có đường nào acquire A khi đã giữ B.
~~~

Khi tất cả code paths (Java synchronized, JNI MonitorEnter, C mutex) tuân thủ một thứ tự acquire, khả năng tạo cycle do đảo thứ tự được giảm mạnh. Tuy nhiên **lock hierarchy phải bao gồm callback**: library có thể không kiểm soát cách user-supplied callback lấy khóa. Vì vậy tốt nhất **không gọi arbitrary Java callback khi giữ JNI monitor hoặc C mutex**.

Các nguyên tắc thực hành:
1. **Không gọi callback không biết trước bên trong khóa.** Đây là quy tắc quan trọng hơn việc chỉ tin monitor reentrant.
2. **Giữ critical section ngắn.** Pre-resolve method/field IDs ngoài lock, kiểm tra điều kiện, cập nhật trạng thái và thả monitor ngay.
3. **Không làm I/O, network/blocking operations, `Future.get`, `Thread.join`, condition wait hoặc synchronous RPC trong monitor** trừ khi giao thức chờ và lock graph đã được phân tích rất rõ.
4. **Không lấy thêm lock theo thứ tự đảo chiều.** Nếu Java giữ A gọi native để lấy B, một callback khi giữ B không được quay lại cần A ở thread khác.
5. **Đừng giữ monitor qua attach/detach, long-running computation hoặc native thread creation/join** không cần thiết.
6. **Khóa đúng object identity**, không tự ý đổi sang synchronized ở object khác; nếu dùng global ref trong async callback, bảo đảm ref vẫn hợp lệ và được cleanup.
7. **Giảm reentrancy bất ngờ:** Callback có thể gọi lại chính JNI entry point, thay đổi state trong khi method C chưa hoàn tất. Cần thiết kế invariants hoặc chuyển callback sau khi commit+unlock.
8. **Không nuốt exception**, luôn unlock kể cả exception. Pending exception không có nghĩa monitor tự động thả; Java synchronized method release entry của Java, **không release entry JNI**.
9. **Không dùng monitor như một cơ chế cancel.** Java `Thread.interrupt` không nhất thiết dừng một thread đang chờ vào intrinsic monitor; shutdown/timeout cần được thiết kế bên ngoài và có kênh chẩn đoán.
10. **Theo dõi owner và waiter**. Trong hệ phức tạp, log tên thread, monitor/object identity ở mức có kiểm soát và thứ tự enter/exit, không log raw native pointers như một cách đo tính hợp lệ của JNI refs.

Nếu phải gọi callback trong vùng khóa vì tính nhất quán nghiệp vụ, phải **khóa giao diện callback**: chỉ được xử lý nhanh, không block, không chờ worker, không tái nhập API tạo thứ tự khóa ngược. Đưa điều kiện đó vào contract public API và có kiểm thử concurrency thực tế.

## 9. Lỗi và ngoại lệ JNI: phân biệt rò rỉ monitor với lỗi method/linker

| Triệu chứng | Tầng xảy ra | Cách kiểm tra |
|---|---|---|
| `jni.h: No such file or directory` | C compiler | JDK, `JAVA_HOME/include` và include platform |
| `conflicting types for Java_demo_jni_MonitorLesson_...` | JNI header vs C signature | Sinh lại `javac -h`; dùng `JNIEnv *, jclass, jobject, jint` |
| `UnsatisfiedLinkError: no monitorlesson in java.library.path` | JVM chưa nạp shared library | `libmonitorlesson.so`/`.dylib`/`monitorlesson.dll`, path, kiến trúc |
| `UnsatisfiedLinkError` khi gọi native method | JVM không tìm JNI exported symbol | Tên package/method, generated header, `nm`/`dumpbin`, binary mới |
| Callback Java ném exception, những thread sau đó treo | JNI MonitorExit bị bỏ qua | Đặt cleanup sau callback; xác nhận `MonitorExit` kể cả pending exception |
| `IllegalMonitorStateException` | `MonitorExit` khi thread không sở hữu monitor | Đúng object, đúng thread, cân đối số enter/exit, không tự exit Java synchronized monitor |
| Chạy bình thường một thread, treo khi có callback concurrent | AB–BA, pool wait hoặc native mutex khác | Dựng lock graph; thread dumps, mốc lock acquire và callback |
| Java `synchronized` method vào lại cùng object | Reentrant monitor bình thường | Không gán nhãn deadlock nếu không có cycle/waiter; kiểm tra callback khác |
| `-Xcheck:jni` nêu vấn đề | Sai JNI refs/API usage | Đọc cảnh báo theo function và thread; không dùng như chứng minh absence of deadlock |
| Thread bị kẹt trong `Future.get`/`join` khi giữ lock | Deadlock gián tiếp | Worker đang cần khóa nào để hoàn tất? Di chuyển wait ra ngoài lock |

Cần phân biệt **Java exception** và **native deadlock**: exception có thể xuất hiện rồi Java code catch được, nhưng native monitor vẫn bị giữ nếu C không exit. Ngược lại, deadlock có thể không có exception hay crash; JVM process còn sống nhưng những thread liên quan không tiến triển.

## 10. Debug deadlock bằng thread dumps và kiểm tra JNI

### 10.1. Thu thập bằng chứng thay vì suy đoán

Khi ứng dụng đứng yên trong lúc JNI callback:

1. **Xác định PID của JVM** và ghi thời điểm. Nếu có thể, thu **hai hoặc ba thread dumps cách nhau vài giây** để xem thread có đang chuyển trạng thái hay chờ mãi.
2. Với JDK có `jcmd`:

~~~sh
jcmd <PID> Thread.print -l
~~~

3. Hoặc dùng `jstack` trên JVM đang chạy:

~~~sh
jstack -l <PID>
~~~

`<PID>` là placeholder cần thay bằng PID thật; đây không phải lệnh chạy trực tiếp khi chưa có PID. Với HotSpot, thread dump thường thể hiện Java stack frames, trạng thái blocked/waiting, monitor ownership và một số native frames. Đọc quan hệ **“waiting to lock”**, **“locked”** và các stack frames JNI/callback. Không phải **mọi** custom C mutex, native join hoặc trạng thái trong thư viện native đều xuất hiện đầy đủ trong Java thread dump, vì vậy có thể cần native debugger, OS thread dump, logging và hồ sơ lock ownership.

4. Ghi lại **chuỗi locks theo thời gian** trên cả Java và C:
   - T1 giữ monitor nào trước `CallVoidMethod`?
   - Callback cố khóa monitor nào?
   - Thread giữ monitor đó đang chờ điều gì hoặc gọi JNI method nào?
   - Có thread đang giữ C mutex rồi chờ Java monitor hoặc ngược lại?
5. Chỉ sau khi dựng được cycle mới kết luận “deadlock”. Một thread `WAITING` hay `BLOCKED` đơn lẻ chưa đủ — có thể chỉ là contention thông thường hoặc `wait()` có chủ ý.

### 10.2. Chạy dưới `-Xcheck:jni` để tìm misuse JNI

~~~sh
java -Xcheck:jni -Djava.library.path=. \
  -cp out demo.jni.MonitorLesson
~~~

HotSpot `-Xcheck:jni` giúp phát hiện một số lỗi dùng JNI API/handles; **không phải deadlock detector**. Nó không cam kết báo sai lock order hay chờ vô hạn giữa hai thread. Một deadlock logic có thể xảy ra dù mọi JNI call riêng lẻ đều hợp lệ.

Java Management API như `ThreadMXBean.findDeadlockedThreads()` có thể hỗ trợ phát hiện chu trình liên quan Java object monitors/ownable synchronizers mà JVM biểu diễn; nhưng nó **không bảo đảm phát hiện** mọi trạng thái chờ từ C mutex, thread join ngoài JVM hoặc callback native. Không dùng việc API trả `null` làm bằng chứng tuyệt đối rằng ứng dụng không có deadlock.

### 10.3. Test có giới hạn thời gian: minh họa trong chương trình

Đoạn Java sau được lấy từ `main` của ví dụ, dùng thread khác kiểm tra monitor sau exception:

~~~java
FutureTask<Integer> probe = new FutureTask<>(state::value);
Thread verifier = new Thread(probe, "monitor-verifier");
verifier.setDaemon(true);
verifier.start();
if (probe.get(5, TimeUnit.SECONDS) != 5) {
    throw new AssertionError("Unexpected state after exception");
}
~~~

Nếu JNI quên `MonitorExit` khi callback ném, `state.value()` từ thread khác có thể bị chặn. `FutureTask.get` với timeout giúp bài test thất bại có kiểm soát thay vì chờ vô hạn; thread verifier được đặt daemon để không giữ JVM sống sau khi main ném exception. Thời gian 5 giây chỉ là **ngưỡng test**, không phải cam kết JVM sẽ lập lịch thread trong đúng thời hạn dưới mọi tải. Một timeout nên khiến người học **điều tra** chứ không tự kết luận nguyên nhân duy nhất là JNI.

## 11. Phần mở rộng: Java thread, native thread, callbacks và JavaVM

Một JNI native method do Java gọi nhận `JNIEnv *` của **thread hiện tại**. `MonitorEnter`/`MonitorExit` phải thực hiện trên thread sở hữu monitor, không để thread khác gọi `MonitorExit` “thả hộ”. Nếu thư viện tự tạo thread POSIX/Windows và muốn gọi Java:
- Phải có `JavaVM *` hợp lệ, ví dụ thu bằng `GetJavaVM` từ một JNI method.
- Native worker gọi `GetEnv` để biết đã attach chưa; nếu `JNI_EDETACHED` thì `AttachCurrentThread` thành công trước mọi JNI call.
- Dùng **`JNIEnv *` của worker**, không dùng env của Java caller.
- Nếu callback sử dụng object sau JNI call ban đầu, giữ một **global reference** hợp lệ (hoặc weak global + promote thích hợp) thay vì cất local `jobject`.
- Một worker đã attach phải dọn local refs và những monitors mình sở hữu, kết thúc callback, rồi `DetachCurrentThread` theo đúng ownership.
- Không dựa vào `DetachCurrentThread` để “dọn” monitors quên exit; giải phóng tường minh và cân đối trước detach.

Không nên gọi callback Java trong lúc đang giữ C mutex để “tránh JNI monitor” rồi cho rằng đã an toàn. Deadlock AB–BA vẫn có thể xảy ra giữa **native mutex** và **Java object monitor**. Mấu chốt là không giữ bất kỳ lock quan trọng nào qua callback không kiểm soát và dùng **lock graph của toàn hệ thống**.

## 12. Thiết kế production: callback an toàn mà vẫn giữ tính nhất quán

Trong một pipeline native nhận input rồi callback về Java, có thể tách thành ba pha:

~~~text
Pha 1: Validate/lookup bên ngoài monitor
    - kiểm tra refs và method IDs
    - chuẩn bị data/copy input hợp lệ

Pha 2: Critical section NGẮN
    - MonitorEnter(state)
    - cập nhật trạng thái / sequence number
    - tạo snapshot bất biến hoặc event payload
    - MonitorExit(state) ở mọi đường thoát

Pha 3: Thông báo SAU KHI UNLOCK
    - kiểm tra pending exception
    - CallVoidMethod(listener, event)
    - xử lý exception/cancellation theo contract
~~~

Nếu Java callback có thể gọi ngược native API (**reentrancy**) hoặc thay listener ngay trong callback, hãy xác định rõ:
- State đã được **commit** trước callback chưa?
- Callback được phép gọi `register/unregister/close` đồng thời không?
- Callback cùng thread hay chuyển sang executor thread? Việc chờ callback hoàn tất có giữ khóa nào không?
- Listener/native context còn sống khi callback chạy không? Object refs cần global/local ownership rõ ràng.
- Khi Java callback ném exception, native code còn tài nguyên chưa release không?
- Có nguy cơ callback A gọi callback B và đảo chiều lock order không?
- Nếu callback chạy ngoài lock, liệu các thread khác thay state trước lúc listener đọc? Nếu cần đúng snapshot, callback phải nhận **snapshot đã chụp** chứ không dựa vào live mutable state không được đồng bộ.

Một phương án phổ biến là **queue event rồi dispatch ngoài khóa**. Nhưng queue cũng có lock/condition và capacity riêng; đừng block khi push vào queue trong lúc vẫn giữ JNI monitor nếu consumer cần monitor ấy để làm trống queue.

### Khi vẫn cần JNI monitor

Dùng `MonitorEnter/MonitorExit` khi cần tương tác trực tiếp với Java object's intrinsic monitor mà Java code cũng đang dùng. Nếu không cần tham gia cùng Java monitor, một Java-level `synchronized` wrapper hoặc `java.util.concurrent.locks.ReentrantLock` có thể dễ diễn đạt ownership hơn; C state riêng có thể dùng mutex C tách biệt. Chọn một chiến lược rõ ràng, tránh “chồng” khóa Java và C mà không có thứ tự tổng thể.

## 13. Các lỗi code thường thấy và cách sửa

**Sai 1 — quên exit khi callback ném:**

~~~c
/* Sai: if exceptional path returns without release. */
if ((*env)->MonitorEnter(env, state) != JNI_OK) return;
(*env)->CallVoidMethod(env, state, callback);
if ((*env)->ExceptionCheck(env)) return; /* JNI monitor bị giữ. */
(*env)->MonitorExit(env, state);
~~~

Sửa bằng cách gọi `MonitorExit` **trước** nhánh `ExceptionCheck`, như ví dụ chính. Nếu phải cleanup nhiều resource, dùng một nhãn `cleanup` và trạng thái rõ.

**Sai 2 — nghĩ Java synchronized return bù JNI enter:**

~~~c
/* Sai về ownership: callback Java synchronized method return không
   giải phóng entry mà JNI MonitorEnter đã tạo. */
(*env)->MonitorEnter(env, state);
(*env)->CallVoidMethod(env, state, callback);
/* thiếu MonitorExit */
~~~

Java synchronized callback chỉ release **entry riêng của Java**; JNI entry vẫn do C giữ.

**Sai 3 — dùng sai object khi exit:**

~~~c
/* Sai: Java object A khác object B. */
(*env)->MonitorEnter(env, lockA);
(*env)->MonitorExit(env, lockB);
~~~

Có thể nhận `IllegalMonitorStateException` hoặc phá bất biến. Thực hành: lưu rõ handle của object đang lock, `MonitorExit` đúng handle/identity, và đảm bảo lifetime của ref.

**Sai 4 — unlock sai thread:**

~~~text
T1: JNI MonitorEnter(lock)
T2: JNI MonitorExit(lock)  <-- T2 không phải owner
~~~

Object monitors không chuyển ownership qua thread. Đừng “đẩy” unlock sang worker chỉ vì muốn trả kết quả bất đồng bộ.

**Sai 5 — callback trong lock gọi Future.get:**

~~~text
JNI thread T1 giữ monitor M
callback Java trên T1 chờ Future F
worker hoàn tất F cần monitor M
=> cycle
~~~

Sửa bằng update/snapshot rồi unlock trước callback hoặc thiết kế worker không cần M để hoàn tất. Chỉ thêm timeout có thể giúp **phát hiện** nhưng không tự giải quyết vấn đề lock order.

**Sai 6 — tin `JNI_OK` nghĩa là callback sẽ không block:**

`JNI_OK` ở `MonitorEnter` chỉ chứng minh **đã acquire**, hoàn toàn không đánh giá hành vi các callback về sau. Callback có thể reentrant, block, throw exception hoặc gọi API mới mà ứng dụng chưa tính tới.

## 14. Checklist trước khi merge một JNI callback implementation

- [ ] Xác định chính xác Java object làm monitor; không truyền NULL/invalid `jobject`.
- [ ] `JNIEnv *` thuộc đúng thread hiện tại, không chia sẻ env cross-thread.
- [ ] `MonitorEnter` thành công trước khi truy cập vùng bảo vệ; mỗi JNI enter được cân bằng bằng **JNI MonitorExit** ở cùng thread.
- [ ] Không nhầm Java `synchronized` entry với JNI entry trong đếm khóa và cleanup.
- [ ] Có một đường cleanup trên **normal return, exception, early error, cancellation và shutdown**.
- [ ] `MonitorExit` vẫn được thực thi nếu `CallVoidMethod` để lại pending exception.
- [ ] Không thực hiện JNI calls không được phép trong khi pending exception còn hiệu lực.
- [ ] Xác định callback có tái nhập Java synchronized method trên cùng object/thread hay phải lấy khóa khác.
- [ ] Vẽ lock graph xuyên Java + JNI + C mutex; không có vòng A–B–A hoặc wait-on-worker trong khi giữ khóa.
- [ ] Ưu tiên notify/callback sau khi unlock; nếu bất khả thi, contract callback phải rõ ràng, không block và được test concurrency.
- [ ] Mọi local/global JNI references sử dụng trong callback đúng lifetime; không cất local ref quá JNI frame.
- [ ] Có test exception path và thread khác vào monitor sau exception; test có timeout để không treo vĩnh viễn.
- [ ] Có lệnh `javac -h`, build native đúng OS/arch, `-Xcheck:jni` và công cụ thu thread dumps khi debug.
- [ ] Không coi một lần chạy PASS hoặc không có thread deadlock report là bằng chứng mọi interleaving đều an toàn.

## 15. Câu hỏi ôn tập (kèm đáp án)

**Câu 1.** JNI `MonitorEnter(state)` rồi `CallVoidMethod(state.add)`, trong đó `add` được khai báo `synchronized` trên chính `state`. Có deadlock chắc chắn không?  
**Đáp án:** Không. Nếu callback thực thi trên cùng thread, đó là **reentrant monitor**. Deadlock có thể xảy ra nếu callback phải đợi thread/lock khác, chứ không chỉ vì tái nhập cùng monitor.

**Câu 2.** Thread T1 giữ monitor B bằng JNI, gọi callback Java cần A; thread T2 giữ A rồi gọi JNI lấy B. Vì sao không thread nào tiến tiếp?  
**Đáp án:** T1 đợi A do T2 giữ; T2 đợi B do T1 giữ. Hai điều kiện chờ hợp thành cycle AB–BA. Thả B trước callback hoặc chuẩn hóa thứ tự khóa xuyên mọi đường gọi là biện pháp thiết kế thích hợp.

**Câu 3.** `CallVoidMethod` ném Java exception trong lúc JNI đang giữ `MonitorEnter`. Có được gọi `MonitorExit` trước khi return không?  
**Đáp án:** Có, và **phải** cleanup entry này. `MonitorExit` thuộc các JNI operations được phép dùng khi có pending exception. Sau đó return để Java nhận exception; không tự bỏ qua.

**Câu 4.** Java synchronized method return có tự nhả khóa do JNI `MonitorEnter` vừa lấy trước đó không?  
**Đáp án:** Không. Java và JNI dùng cùng monitor nhưng ownership của mỗi entry phải thoát bằng đúng cơ chế: JNI enter ↔ JNI exit.

**Câu 5.** Java thread T2 có thể gọi `MonitorExit` hộ monitor T1 đã enter không?  
**Đáp án:** Không. `MonitorExit` yêu cầu **current thread** là owner; sai owner có thể ném `IllegalMonitorStateException`.

**Câu 6.** Nếu callback được gọi sau `MonitorExit` thì production code đã tuyệt đối không thể deadlock?  
**Đáp án:** Chưa. Caller có thể vẫn giữ Java/C locks khác; callback có thể lấy lock theo thứ tự đảo chiều hoặc đợi worker. Phải đánh giá toàn bộ lock graph và wait dependencies.

**Câu 7.** Tại sao `FutureTask.get(5, TimeUnit.SECONDS)` xuất hiện trong demo sau khi callback ném exception?  
**Đáp án:** Để kiểm tra từ **thread khác** rằng monitor không bị JNI giữ sau exception, với deadline tránh treo vô hạn. Kết quả PASS hỗ trợ kiểm chứng đường cleanup của ví dụ, không thay thế stress tests.

## 16. Tổng kết và nguồn chuẩn

**`MonitorEnter` và `MonitorExit` cho C/C++ quyền tham gia Java object monitor.** Đó là khóa reentrant, nên callback synchronized cùng object/cùng thread có thể an toàn về mặt acquire; **nhưng callback có thể kéo thêm khóa, chờ worker hoặc tạo AB–BA**, vì vậy tránh gọi code Java tùy ý trong lúc giữ JNI monitor. Nếu phải acquire, luôn **exit bằng JNI trên mọi nhánh**, kể cả khi callback đang để lại pending Java exception. Ưu tiên *mutate under lock → MonitorExit → notify/callback* với snapshot/contract phù hợp và kiểm tra bằng thread dumps khi cần.

Đặc tả chính thức để đối chiếu:
- [Oracle Java SE 21 JNI Functions – Monitor Operations](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#monitor-operations).
- [Oracle Java SE 21 JNI Design Overview – Threads and Java Exceptions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- [Oracle Java SE 21 JNI Invocation API](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html).
- [Java SE 21 ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

Các đường dẫn build và stdout trong bài áp dụng cho hai file mẫu đã nêu; khi chuyển sang ứng dụng thật, cần có kiểm thử đặc thù lock order và lifecycle của chính ứng dụng đó.