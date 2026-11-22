# Ảnh hưởng của lời gọi native kéo dài đối với luồng ảo và khả năng phục vụ

**Bối cảnh:** Java 21 trở lên cung cấp **virtual threads** (luồng ảo) để viết ứng dụng phục vụ nhiều tác vụ đồng thời bằng mã đồng bộ dễ hiểu. Khi tác vụ chờ I/O qua các Java API được JVM hỗ trợ, virtual thread thường được **unmount** khỏi một platform thread (luồng nền của hệ điều hành, gọi là *carrier*) để carrier tiếp tục chạy tác vụ khác. Tuy nhiên, khi virtual thread đang thực thi một phương thức **JNI native** hoặc foreign function, nó không thể dựa vào cơ chế unmount thông thường trong thời gian có native frame đó. Một lời gọi C chờ I/O, mutex, thư viện bên ngoài hoặc callback quá lâu có thể giữ carrier bận hoặc chờ bất động, làm giảm số tác vụ khác được phục vụ.

Hệ quả quan trọng: **tạo một triệu virtual threads không tạo một triệu carrier threads**. Nếu nhiều virtual threads cùng mắc trong native calls kéo dài, các carrier hữu hạn có thể trở thành điểm nghẽn. Một lần gọi native ngắn không nhất thiết là vấn đề; rủi ro nằm ở **tần suất, thời gian chờ, số lời gọi đồng thời và chính sách giới hạn tải**.

Bài này tập trung vào tương tác **virtual thread ↔ carrier ↔ JNI/native code**, tác động đến throughput/latency, cách thiết kế native call an toàn, backpressure, cancellation, monitoring và ví dụ chạy được bằng **Java 21+ và C11 trên Linux**.

## 1. Virtual thread và carrier: mô hình nền tảng

Virtual thread là một đối tượng `java.lang.Thread`, có stack logic và trạng thái Java riêng, nhưng không phải cứ một virtual thread là một OS thread riêng. JVM có một scheduler gắn (mount) virtual thread đang chạy lên một platform thread (*carrier*). Khi virtual thread thực hiện thao tác chờ theo cơ chế JVM có thể quản lý, JVM có thể lưu continuation của virtual thread và tháo nó khỏi carrier.

Ví dụ, trong mã Java thông thường:

```java
Thread t = Thread.startVirtualThread(() -> {
    try {
        Thread.sleep(100);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
});
t.join();
```

Đây là đoạn Java độc lập trong ngữ cảnh đã import mặc định `java.lang` và có thể đặt trong `main`. Trên JDK hỗ trợ, `Thread.sleep` khi chạy từ virtual thread thường cho phép JVM unmount: carrier không phải ngồi chờ giấc ngủ. Điều này phù hợp với mục tiêu phục vụ nhiều request đang chờ I/O.

Tuy nhiên, khi Java gọi:

```java
// Khai báo minh họa; nativeSleepMillis được implement qua JNI.
private static native void nativeSleepMillis(int milliseconds);
```

trình tự là:

```text
Virtual thread thực thi mã Java
          |
          v
Mount trên một platform thread (carrier)
          |
          v
Gọi nativeSleepMillis(...) -> bước vào JNI frame
          |
          v
C gọi blocking syscall / chờ mutex / thư viện C
          |
          +---- native frame vẫn trên call stack ----+
          |                                         |
          | carrier bị giữ để thực thi/chờ           |
          | virtual thread không unmount như        |
          | một Java sleep/I/O thân thiện VT        |
          +-----------------------------------------+
          |
          v
Native call trả về -> quay lại Java
          |
          v
Virtual thread có thể tiếp tục, sau đó unmount
khi gặp thao tác chờ được JVM hỗ trợ
```

**Phân biệt quan trọng:** `Thread.currentThread().isVirtual()` vẫn có thể trả `true` khi lời gọi native xuất phát từ virtual thread. Điều đó **không** có nghĩa native code đang chạy trên một OS thread “ảo”. Các instruction C cuối cùng vẫn chạy trên một carrier platform thread của hệ điều hành.

### 1.1. Pinning là gì?

Trong ngữ cảnh virtual threads, **pinning** là trạng thái virtual thread không thể unmount khỏi carrier trong một tình huống mà bình thường JVM có thể giải phóng carrier khi blocking. Native frame (JNI hoặc FFM) là một nguyên nhân pinning cần cân nhắc.

- **Pinned nhưng tính toán rất ngắn:** thường không gây vấn đề đáng kể; carrier đang làm công việc hữu ích.
- **Pinned và chờ lâu:** carrier bị chiếm trong lúc không hoàn thành công việc Java khác; đây là vấn đề khả năng phục vụ.
- **Nhiều lời gọi pinned đồng thời:** có thể làm cạn năng lực carrier scheduler, khiến request mới chờ dù còn nhiều virtual threads đang tồn tại.
- **Native CPU-bound lâu:** giữ carrier để tính toán, đồng thời chiếm CPU. Đây vừa là rủi ro không nhường carrier, vừa là giới hạn tài nguyên CPU thông thường.

Không nên đánh đồng **virtual thread blocking** với **carrier blocking**. Java code chờ socket I/O qua API có hỗ trợ virtual thread có thể giải phóng carrier; native C tự gọi `read()`, `poll()`, `nanosleep()` hoặc chờ thư viện ngoại lai trong JNI không tự nhận được cơ chế đó.

## 2. Sự khác nhau giữa JDK 21–23 và JDK 24+

Đối với khả năng unmount, **phiên bản JDK là điều kiện quan trọng**.

| Tình huống | JDK 21–23 | JDK 24+ |
| --- | --- | --- |
| Java virtual thread chờ bằng API thân thiện VT ngoài native frame | Có thể unmount | Có thể unmount |
| Chờ trong `synchronized`/monitor Java | Có thể gây pinning | JEP 491 cải thiện để virtual thread có thể chờ monitor mà không giữ carrier trong phần lớn tình huống liên quan |
| Native method JNI hoặc FFM đang trên stack | **Vẫn là nguồn pinning** | **Vẫn là nguồn pinning** |
| Native code gọi ngược Java, sau đó Java code thực hiện blocking operation | Native frame vẫn có thể cản unmount | Native frame vẫn có thể cản unmount |
| Một Java thread chờ `Future.get()` cho công việc native chạy trên **platform pool khác** | Virtual thread có thể unmount trong lúc chờ | Tương tự, tùy ngữ cảnh có các nguồn pinning khác hay không |

JEP 491, **Synchronize Virtual Threads without Pinning**, được đưa vào JDK 24. Nó khắc phục vấn đề pinning do monitor Java trong các tình huống đã được JEP xác định. Nó **không biến một JNI blocking call trở thành thao tác chờ có thể unmount**. Vì vậy, chỉ nâng cấp JDK hoặc đổi `synchronized` thành `ReentrantLock` không giải quyết được nguyên nhân gốc khi chính native function chờ rất lâu.

Đừng cố “đoán” tình trạng pinning từ một dòng stacktrace duy nhất. Cần ghép thông tin phiên bản JDK, native stack, thời gian blocked và telemetry thực tế.

## 3. Tác động đến khả năng phục vụ: throughput, latency và hàng đợi

Một service thường có đường gọi:

```text
HTTP request
  -> virtual thread request handler
  -> Java business logic
  -> JNI call tới thư viện C
  -> native I/O / lock / compute
  -> JNI return
  -> Java response
```

Khi JNI call nhanh, flow này có thể hợp lý. Nhưng nếu nhiều request đồng thời chờ ở bước JNI, carrier threads bị giữ trong khi server vẫn có request đến.

### 3.1. Mô hình tính tải đơn giản

Giả sử tại thời điểm xét:

- `P` carrier threads có thể chạy tác vụ ở scheduler đang xét.
- `N` tác vụ đồng thời đều thực hiện một native call chờ lâu.
- Thời gian mỗi native call là `T` giây, và mọi native call thực sự có thể chạy song song ở tầng C (không có mutex chung hoặc giới hạn backend khác).

Trong kịch bản mô hình hóa đơn giản, mỗi carrier chỉ chạy một native call tại thời điểm đó, nên số lời gọi đang chiếm carrier khó vượt quá `P`. Phần còn lại có thể phải chờ cơ hội thực thi. Thời gian hoàn thành toàn bộ `N` tác vụ có thể xấp xỉ **`ceil(N/P) × T`** nếu cùng bắt đầu, có thời gian đồng nhất và không có cơ chế bù carrier; đây là **mô hình trực giác**, không phải cam kết đo thực tế của JVM.

Ví dụ **giả định để minh họa**, không phải số liệu benchmark:

| Đại lượng | Giá trị minh họa |
| --- | ---: |
| Carrier khả dụng `P` | 4 |
| Request cần JNI blocking đồng thời `N` | 80 |
| Thời gian native wait `T` | 250 ms |
| Số đợt lý tưởng hóa | 20 |
| Thời gian cuối đợt theo mô hình | Khoảng 5 s |

Trong cùng thời gian đó, những request chỉ cần chạy Java logic nhẹ cũng có thể bị tăng thời gian chờ vì carrier phục vụ tác vụ mới trở nên khan hiếm.

Tuy nhiên **carrier count không phải một hằng số bất biến**; JVM có scheduler, chính sách compensation, phần cứng, giới hạn môi trường và hành vi workload riêng. Không dùng phép tính trên làm SLO hay giới hạn chính thức. Nó chỉ diễn tả vì sao tăng số virtual threads **không tự tạo thêm băng thông xử lý native**.

### 3.2. Throughput và latency bị ảnh hưởng theo những cách nào?

- **Throughput (requests/s):** có thể giảm hoặc bị giới hạn bởi số carrier/thread và thời gian native wait.
- **Queueing latency:** request mới có thể nằm chờ CPU/carrier hoặc chờ native executor. Độ trễ p95/p99 có thể tăng mạnh trước khi trung bình thay đổi nhiều.
- **Tail latency:** khi native call thỉnh thoảng chậm đột biến, các request dùng chung carrier pool chịu ảnh hưởng dây chuyền.
- **Khả năng cô lập:** một native dependency chậm có thể ảnh hưởng cả những loại request không dùng dependency đó nếu tất cả cạnh tranh scheduler chung.
- **Bộ nhớ:** virtual threads đang chờ vẫn giữ request state, stack frames, data buffers và Java references. Nhiều request tồn đọng làm tăng bộ nhớ dù số OS threads không tăng theo tỷ lệ 1:1.
- **CPU utilization có thể thấp:** carrier bị chặn trong syscall/mutex dù máy chưa dùng hết CPU. Đây là dạng **resource starvation** chứ không nhất thiết là CPU bottleneck.

Theo dạng trực giác của Little's Law, số request đang ở hệ thống `L ≈ λ × W`, trong đó `λ` là tốc độ request/giây và `W` là thời gian ở hệ thống. Khi `W` tăng do chờ native, lượng request tồn đọng có thể tăng nếu tốc độ đến không giảm. Đừng để request queue phát triển vô hạn.

### 3.3. Pinning không phải nguyên nhân duy nhất gây chậm

Phải phân biệt:

| Triệu chứng | Nguyên nhân có thể | Điều nên kiểm tra |
| --- | --- | --- |
| Carrier bận trong native wait, throughput giảm | Native frame giữ carrier | Native call latency, carrier stacks, JFR, lượng calls đồng thời |
| CPU 100%, mọi request chậm | JNI tính toán nặng, Java CPU-bound, GC | CPU profiling, native CPU samples |
| Native calls xếp hàng trên mutex | Global lock trong thư viện C | Lock contention, số thread vào native và thời gian giữ lock |
| JNI nhanh nhưng kết quả ra chậm | Downstream DB/HTTP, queue, Java lock | Tracing thời gian từng bước |
| Số thread/heap tăng dù native nhanh | Quá nhiều concurrent requests, buffers và Java references | In-flight count, queue depth, heap/native memory |
| Service p99 tăng sau deploy | Thay đổi JDK, JNI library, thread pool, workload | So sánh phiên bản/cấu hình và số liệu trước–sau |

Bài toán đúng là **kiểm soát công việc đang thực sự tiêu tốn hoặc giữ một nguồn lực hữu hạn**, chứ không chỉ đổi kiểu thread.

## 4. Những loại native call cần đặc biệt cẩn trọng

### 4.1. Native code block trong OS I/O hoặc thư viện bên thứ ba

Ví dụ JNI gọi một hàm C chờ socket, file, RPC SDK native hoặc transaction với thiết bị:

```c
/* Minh họa thân native method, không phải file C độc lập. */
JNIEXPORT jint JNICALL
Java_NativeApi_readBlocking(JNIEnv *env, jclass clazz, jint fd) {
    (void)env;
    (void)clazz;

    unsigned char buffer[4096];
    ssize_t count = read(fd, buffer, sizeof buffer);
    if (count < 0) {
        return -1;  /* Cần một contract lỗi thực tế. */
    }
    return (jint)count;
}
```

Đoạn trên giả định POSIX `read()` và cần `<unistd.h>`, cùng hợp đồng riêng cho partial read, EINTR, errno, buffer và kích thước kiểu; đó là **mã minh họa**, chưa xử lý đầy đủ lỗi. Ngay cả khi OS call có thể block trong khi CPU rảnh, virtual thread vẫn có native frame và carrier có thể bị giữ.

### 4.2. Native code giữ mutex hoặc semaphore

Một thư viện C có global mutex hoặc tài nguyên serial bên trong sẽ khiến nhiều JNI calls phải chờ lock. Nếu 100 virtual threads cùng gọi native method giữ lock, việc không giới hạn đồng thời có thể tạo **nhiều carrier threads chờ cùng một tài nguyên**, gây tổn thất lớn hơn lợi ích của virtual threads.

Hãy đặt giới hạn truy cập trước khi bước vào native, hoặc tổ chức một hàng đợi và số worker native hữu hạn. Không nên chỉ tăng kích thước carrier pool để “đi quanh” một lock vốn serialize toàn bộ công việc.

### 4.3. JNI gọi ngược Java (callback)

Một native method có thể gọi `CallVoidMethod`/`CallObjectMethod` để thực thi Java code rồi quay trở lại C. Dù callback là Java, **native frame vẫn ở bên dưới call stack** khi chưa return. Nếu callback thực hiện `Thread.sleep`, chờ future hoặc I/O, môi trường vẫn có nguồn pinning từ native frame.

Vì thế cách sửa kiểu “C gọi Java rồi Java tự sleep” không tự giải phóng carrier. Muốn xử lý thật sự bất đồng bộ, phải **kết thúc lời gọi JNI hiện tại** và tổ chức completion/lifecycle phù hợp; không giữ native stack trong lúc chờ.

### 4.4. CPU-intensive native function

Một thuật toán mã hóa, nén, image processing hoặc machine learning bằng C chạy 500 ms không phải I/O wait; nó thực sự tiêu CPU. Virtual threads không làm CPU computations chạy nhanh hơn hoặc tăng số lõi. Native function giữ carrier trong thời gian tính toán; nếu nạp quá nhiều tác vụ, số lượng CPU-ready threads và tranh chấp cache cũng có thể tăng.

Trong trường hợp CPU-bound, một **bounded executor** có parallelism gần tài nguyên CPU hoặc giới hạn thư viện C thường dễ kiểm soát hơn. Không lấy số virtual threads làm số phép tính native chạy song song.

### 4.5. JNI critical sections và GC

Nếu JNI dùng `GetPrimitiveArrayCritical` hay `GetStringCritical`, tài liệu JNI yêu cầu giữ critical region ngắn và tránh các thao tác gây block hoặc gọi JNI tùy tiện trong vùng đó. Tùy VM, critical access có thể liên quan pin/copy và ảnh hưởng đến khả năng thu gom rác. Một native call kéo dài **không có nghĩa mọi native call đều ngăn GC**, nhưng một critical region bị giữ lâu có thể tạo tác động JVM khác ngoài carrier starvation.

Để giảm rủi ro: chỉ giữ các JNI critical pointers trong phạm vi thực sự cần, dùng `ReleasePrimitiveArrayCritical` hoặc `ReleaseStringCritical` đúng cặp, không thực hiện I/O/network wait trong critical region.

## 5. Ví dụ chạy được: JNI sleep trực tiếp so với offload sang platform worker

Ta sẽ viết một chương trình Java 21+ với JNI gọi `nanosleep()` của POSIX. Ví dụ có hai đường:

1. **Direct:** virtual thread gọi thẳng `nativeSleepMillis(50)`. Đây là mẫu có thể giữ carrier trong lời gọi native.
2. **Offload:** virtual thread gửi native work vào **platform thread pool giới hạn**, sau đó chờ `Future.get()` từ Java. Virtual thread có thể unmount trong lúc đợi future nếu không có nguồn pinning khác; native call chạy trên platform worker đã được chọn rõ.

Ví dụ **chỉ minh họa thread identity và đúng đường xử lý**; thời gian 50 ms và một task không chứng minh throughput trong production. Các dòng stdout là xác định; lịch trình và thời gian thực tế phụ thuộc JVM/hệ điều hành.

### 5.1. File Java: `NativeImpactDemo.java`

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class NativeImpactDemo {
    static {
        System.loadLibrary("nativeimpact");
    }

    private NativeImpactDemo() {}

    private static native void nativeSleepMillis(int milliseconds);

    public static void main(String[] args) throws Exception {
        // Mỗi task Java được chạy trong một virtual thread.
        try (ExecutorService virtual =
                 Executors.newVirtualThreadPerTaskExecutor();
             ExecutorService nativeWorkers =
                 new ThreadPoolExecutor(
                     2, 2, 0L, TimeUnit.MILLISECONDS,
                     new ArrayBlockingQueue<>(4),
                     Executors.defaultThreadFactory(),
                     new ThreadPoolExecutor.AbortPolicy())) {

            Future<Boolean> direct = virtual.submit(() -> {
                nativeSleepMillis(50);
                return Thread.currentThread().isVirtual();
            });
            System.out.println("direct-caller-virtual=" + direct.get());

            Future<Boolean> offloaded = virtual.submit(() -> {
                Future<Boolean> work = nativeWorkers.submit(() -> {
                    nativeSleepMillis(50);
                    return Thread.currentThread().isVirtual();
                });
                // Virtual caller chờ một Future bằng Java API.
                return work.get();
            });
            System.out.println("offloaded-worker-virtual="
                               + offloaded.get());
        }

        System.out.println("done");
    }
}
```

Chi tiết thiết kế:

- `Executors.newVirtualThreadPerTaskExecutor()` được hỗ trợ từ Java 21, tạo một virtual thread cho mỗi task. Nó **không** có ý nghĩa giới hạn số native calls trong hệ thống.
- `new ThreadPoolExecutor(2, 2, ...)` tạo pool tối đa 2 platform worker và một hàng đợi hữu hạn 4 phần tử. Trong ví dụ chạy tuần tự hai trường hợp, không có queue overflow; trong production, `AbortPolicy` tạo `RejectedExecutionException` khi pool+queue đầy.
- `Executors.defaultThreadFactory()` tạo platform threads, khác với virtual-thread factory. Vì vậy native call trong đường offload chạy trên platform worker; virtual caller đang chờ Java `Future.get()` có thể được scheduler tháo khỏi carrier.
- `Future.get()` còn là điểm nhận lại exception từ worker qua `ExecutionException`; đừng quên xử lý `InterruptedException` và deadline trong service thực.
- `try-with-resources` đóng executors khi thoát scope; trong các ứng dụng server, pool thường sống cùng component và được shutdown có thứ tự thay vì tạo/destroy mỗi request.

### 5.2. Sinh JNI header

```bash
javac -h . NativeImpactDemo.java
```

Lệnh này tạo `NativeImpactDemo.class` và `NativeImpactDemo.h`. Prototype JNI do compiler sinh có dạng:

```c
JNIEXPORT void JNICALL
Java_NativeImpactDemo_nativeSleepMillis(
    JNIEnv *, jclass, jint);
```

Đây là **trích minh họa chữ ký**, không thay thế file header được sinh. Vì native method là `static` nên tham số thứ hai là `jclass`; `int` Java tương ứng `jint`.

### 5.3. File C hoàn chỉnh: `NativeImpactDemo.c` (Linux/POSIX)

```c
#define _POSIX_C_SOURCE 200809L

#include "NativeImpactDemo.h"
#include <errno.h>
#include <time.h>

static void throw_java(JNIEnv *env,
                       const char *type,
                       const char *message) {
    jclass exception_type = (*env)->FindClass(env, type);
    if (exception_type != NULL) {
        (*env)->ThrowNew(env, exception_type, message);
        (*env)->DeleteLocalRef(env, exception_type);
    }
}

JNIEXPORT void JNICALL
Java_NativeImpactDemo_nativeSleepMillis(
    JNIEnv *env, jclass clazz, jint milliseconds) {
    (void)clazz;

    if (milliseconds < 0) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "milliseconds must be non-negative");
        return;
    }

    struct timespec requested = {
        .tv_sec = milliseconds / 1000,
        .tv_nsec = (long)(milliseconds % 1000) * 1000000L
    };
    struct timespec remaining;

    while (nanosleep(&requested, &remaining) == -1) {
        if (errno == EINTR) {
            requested = remaining;
            continue;
        }
        throw_java(env, "java/lang/IllegalStateException",
                   "nanosleep failed");
        return;
    }
}
```

`nanosleep()` minh họa một hàm C chờ ở mức OS và có thể bị gián đoạn bởi signal (`EINTR`). Vòng `while` tiếp tục ngủ phần thời gian còn lại sau khi bị signal. Đây là ví dụ POSIX cho Linux, không phải API ISO C; trên Windows phải dùng một native wait API khác.

**Điểm cần nhớ:** Java `Thread.interrupt()` không được JNI tự biến thành thao tác hủy `nanosleep()` này. Chương trình C còn có thể tiếp tục đợi dù virtual thread đã được đánh dấu interrupted. Với production, cần API native có timeout và cơ chế cancel được thiết kế rõ, chứ không coi Java interruption là lời hứa tự dừng mọi blocking C call.

Mã này gọi `FindClass` và `ThrowNew` khi không có pending Java exception từ trước; sau đó xóa local reference tới class. Các thao tác JNI không làm biến một native wait thành thao tác thân thiện virtual thread.

### 5.4. Build/run với JDK 21+ trên Linux

Đặt `NativeImpactDemo.java` và `NativeImpactDemo.c` cùng thư mục. `JAVA_HOME` phải trỏ tới JDK đang chạy và chứa `include/jni.h`:

```bash
javac -h . NativeImpactDemo.java

cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  NativeImpactDemo.c -o libnativeimpact.so

java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. NativeImpactDemo
```

Khi chạy thành công, **stdout chính xác**:

```text
direct-caller-virtual=true
offloaded-worker-virtual=false
done
```

Dòng đầu chỉ cho biết Java code bao quanh native call chạy trong virtual thread. Dòng thứ hai xác nhận code Java chạy trong `nativeWorkers` là platform thread. Không có dòng nào khẳng định số ms chính xác hay rằng VM bắt buộc tạo một JFR pinning event.

Nếu gặp `UnsatisfiedLinkError`, kiểm tra tên `libnativeimpact.so`, `java.library.path`, CPU architecture, JNI header vừa sinh và tính tương thích của compiler/JDK. Khi dùng Windows/macOS, cần thay build flags, tên shared library và API sleep; không sao chép nguyên đường include `linux`. Trên các JDK mới có cảnh báo native access, `--enable-native-access=ALL-UNNAMED` là lựa chọn cho ứng dụng chạy trên classpath; trong ứng dụng JPMS, cấp quyền cho đúng named module.

### 5.5. Ví dụ này chứng minh được gì?

Ví dụ xác nhận mô hình thread được chọn, **không đo pinning trực tiếp**. Để đánh giá tác động hiệu năng, phải tạo tải đồng thời với tỉ lệ request thực tế, đo latency/throughput/queue depth và quan sát carrier hoạt động. Không lấy một `Thread.sleep(50)` trên Java so với một `nanosleep(50)` ở C để tuyên bố native code chậm hơn theo hằng số; rủi ro chủ yếu phát sinh khi **nhiều lời gọi chờ đồng thời**.

## 6. Vì sao offload giúp và giới hạn của nó

Offloading nghĩa là virtual request thread **không trực tiếp thực thi JNI blocking call**. Nó gửi công việc vào một pool platform workers giới hạn và chờ completion bằng một Java API hỗ trợ virtual threads.

```text
Virtual request handler
      |
      v
submit(native-work) ----> bounded queue ----> platform worker
      |                                       |
      | Future.get() / async await            | JNI
      | virtual thread có thể unmount         | native blocking call
      v                                       |
carrier có thể chạy request khác <---- result/exception
```

Đổi lại, hệ thống **vẫn cần OS threads để thực thi các blocking C calls**. Lợi ích là số OS threads bị giữ bởi native được kiểm soát và không chiếm trực tiếp carrier pool phục vụ Java virtual threads. Đây là phương pháp cô lập và kiểm soát tải, không phải cách làm C wait bỗng trở nên nonblocking.

### 6.1. Không dùng một hàng đợi vô hạn làm “giải pháp”

`Executors.newFixedThreadPool(n)` tạo số worker hữu hạn nhưng theo cấu hình thông dụng có **queue không giới hạn**. Nếu request đến nhanh hơn khả năng xử lý native, queue có thể tăng lâu dài. Thêm virtual threads cũng không làm native xử lý nhanh hơn; lúc đó heap/latency có thể xấu đi.

Một `ThreadPoolExecutor` có **bounded queue** và **rejection policy** rõ ràng làm giới hạn được số việc tồn đọng. Trong ví dụ, tối đa 2 task thực thi cộng 4 task đang chờ được nhận trong pool ở thời điểm cụ thể; request thứ bảy (khi queue và workers đầy) có thể bị từ chối. Số này nhằm minh họa; production phải đo và chọn giới hạn theo năng lực native dependency, CPU, memory và latency target.

Một API server nên chuyển `RejectedExecutionException` thành tín hiệu **overloaded/busy** rõ ràng hoặc áp dụng cơ chế backpressure với deadline, thay vì im lặng chạy ở carrier thread bằng `CallerRunsPolicy`: nếu caller là virtual request thread, chạy native task ngay tại caller có thể tái tạo rủi ro pinning đang muốn tránh.

### 6.2. Chọn kích thước native worker pool

Không có con số duy nhất cho mọi hệ thống:

- Native **CPU-bound**: giới hạn theo CPU cores, tài nguyên thư viện và số phép tính thật sự chạy đồng thời.
- Native **I/O-bound** không có API async: pool có thể lớn hơn core count, nhưng vẫn bị giới hạn bởi OS threads, file descriptors, native memory, backend concurrency và cancellation/timeout.
- Native thư viện có **global lock**: thêm worker có thể chỉ làm nhiều thread xếp hàng chờ khóa.
- Native thư viện không **thread-safe**: phải serialize hoặc sửa contract, không cố gọi đồng thời.
- Native library có rate limit/token quota: áp dụng concurrency cap hoặc rate limiter độc lập với kích thước thread pool.

Đo **service time**, queue wait, p95/p99, rejection rate, CPU, native allocations và mức sử dụng backend trước khi chọn kích thước. Không mặc định giá trị `Runtime.getRuntime().availableProcessors()` là số carrier thực tế đang chạy, cũng không mặc định số native workers nên bằng số virtual threads.

### 6.3. Tách resource bottleneck khỏi thread bottleneck

Chuyển sang platform pool có thể làm Java carriers rảnh hơn nhưng chưa chắc tăng throughput nếu tài nguyên native chỉ xử lý được một việc một lúc. Ví dụ mã C có một global mutex bảo vệ thiết bị: pool 2 hay 32 workers vẫn lần lượt qua mutex. Khi đó phải giải quyết contention, batching hoặc native asynchronous API; không chạy theo thread count.

Một thiết kế có thể kết hợp: virtual threads cho phần HTTP/JDBC thích hợp, native executor riêng cho blocking C, bulkhead/concurrency limit cho mỗi library, timeout, retry có giới hạn, metrics và circuit breaker tại boundary.

## 7. Chuyển sang native async API: giảm thời gian giữ JNI frame

Nếu thư viện C hỗ trợ **bất đồng bộ thực sự**, có thể thiết kế JNI chỉ làm thao tác **bắt đầu công việc nhanh**, trả về Java ngay, còn completion xảy ra khi C/OS xử lý xong.

Ví dụ luồng kiến trúc:

```text
Virtual request thread
      |
      v
JNI nativeStart(request, completion-id)
      |
      +--> tạo/copy dữ liệu cần sống qua lời gọi
      +--> submit native asynchronous operation
      +--> RETURN ngay, không chờ kết quả
      |
      v
Java CompletableFuture / callback registry
      |
      | Java chờ completion qua API hỗ trợ VT
      v
Native completion thread/event loop
      |
      +--> attach JVM thread nếu callback vào Java
      +--> tạo local refs cần thiết
      +--> complete result / exception
      +--> dọn local/global references đúng lifecycle
      v
Virtual request thread tiếp tục khi completion tới
```

**Giới hạn quan trọng:** “start async” mà bên trong vẫn đợi hoàn tất rồi mới return **không giải quyết gì**. Chỉ khi native entry point trả về nhanh và phần chờ được quản lý bên ngoài carrier của request thì mới giảm thời gian giữ native frame của request.

Thiết kế async phải quy định:

1. **Lifetime dữ liệu:** không giữ pointer tới Java array/string sau JNI call trừ khi dùng cơ chế JNI được phép; sao chép dữ liệu native hoặc sử dụng global ref đúng lúc. Local `jobject`/`jclass` không được lưu lâu hoặc truyền sang thread khác.
2. **Thread attachment:** native-created thread muốn gọi JNI phải lấy `JavaVM *`, gọi `AttachCurrentThread` rồi sử dụng `JNIEnv *` riêng thread; `DetachCurrentThread` khi kết thúc theo quy tắc JVM.
3. **Hoàn thành đúng một lần:** kết quả, lỗi hoặc cancellation không được complete hai lần; dùng state machine/atomic transitions.
4. **Cancel/timeout:** timeout phía Java không mặc nhiên dừng native operation; cần native cancel handle nếu hỗ trợ hoặc cơ chế bỏ kết quả muộn và dọn tài nguyên.
5. **Backpressure:** không biến async queue thành danh sách yêu cầu vô hạn; vẫn cần giới hạn in-flight.
6. **Exception:** nếu callback Java ném exception trong native thread, phải kiểm tra/clear hoặc báo lỗi theo contract trước khi tiếp tục JNI thông thường.
7. **Thread safety:** synchronization, ownership và release callback không được làm sống lại resource đã đóng.

Đây là lựa chọn có nhiều công việc thiết kế hơn so với một bounded platform pool. Dùng khi native SDK hỗ trợ async có lợi thật, hoặc độ tải cần thiết đủ cao để bù chi phí tích hợp.

## 8. Cancellation, interruption, timeout và khả năng phục vụ

Một service tốt phải có deadline cho request; tuy nhiên với JNI, **deadline phía Java và deadline native không tự động đồng nhất**.

Giả sử virtual request thread đang gọi C và bị:

```java
// Minh họa bên ngoài một native call đang chạy.
requestThread.interrupt();
```

Các điều sau đều cần phân biệt:

- Java `Thread.interrupt()` thiết lập yêu cầu interrupt theo Java thread semantics. Nó **không** đảm bảo dừng một C syscall hay một third-party native function đang chờ.
- `Future.cancel(true)` có thể đánh dấu Future bị cancel và yêu cầu interrupt worker Java; JNI code không có nghĩa vụ tự rời blocking C call nếu thư viện chưa thiết kế cancellation.
- `Future.get(timeout, unit)` chỉ giới hạn **thời gian chờ kết quả của caller**, không hứa native operation đã kết thúc.
- `CompletableFuture.orTimeout(...)` chỉ thay đổi completion/timeout state của future theo API; native C code có thể tiếp tục chạy.
- Nếu timeout xảy ra mà native vẫn hoạt động, cần có **late-result handling** và giữ resource sống đến lúc native thực sự không cần nữa. Không free buffer cho native khi nó còn có thể dereference.

Ví dụ cấu trúc timeout (trích minh họa; `nativeWorkers` là executor đã tồn tại, `nativeOperation` là callable do hệ thống định nghĩa):

```java
Future<Result> result = nativeWorkers.submit(nativeOperation);

try {
    return result.get(500, TimeUnit.MILLISECONDS);
} catch (TimeoutException timeout) {
    result.cancel(true); // Không đảm bảo C call đang chạy bị dừng.
    throw timeout;
}
```

Đây **không phải chương trình độc lập**; cần có `Result`, `nativeWorkers` và `nativeOperation`. Nó chỉ mô tả nguy cơ: nếu native operation không hỗ trợ cancel, phần cleanup của request **không được giải phóng ngay** những native buffers vẫn do operation đang dùng.

Thiết kế đáng tin cậy dùng cả **timeout tại JNI/native SDK** (nếu được hỗ trợ), **deadline phía request**, và **lifetime state machine**. Với native library có block vô hạn không có cách cancel, có thể cần worker process riêng và khả năng cô lập/terminate ở mức process thay vì tin rằng cancel Java thread sẽ giải quyết.

## 9. JNI và luồng: những sai lầm không liên quan trực tiếp đến carrier nhưng làm tăng rủi ro

Một native call kéo dài còn kéo dài lifetime các tài nguyên JNI đã tạo ra trong lời gọi.

### 9.1. Local references và GC

Các local `jobject` được tạo bởi `GetObjectArrayElement`, `NewStringUTF`, `FindClass`... thường tự hết hiệu lực khi native method trả về. Nhưng trong một native loop chạy rất lâu, nếu liên tục tạo local refs mà không `DeleteLocalRef` hoặc pop local frame, bảng JNI references có thể tăng; các object còn được giữ mạnh và khó được GC thu hồi khi không còn dùng.

Giải pháp: release refs từng iteration bằng `DeleteLocalRef`, hoặc dùng `PushLocalFrame`/`PopLocalFrame` theo batch. Không để một native wait dài giữ những JNI references không còn cần tới.

### 9.2. `JNIEnv *` là thread-local

`JNIEnv *` chỉ hợp lệ trong thread hiện tại; không lưu pointer này sang một worker C khác hoặc sang completion callback trên thread khác. Native-created thread phải attach và lấy `JNIEnv *` của chính nó. Đừng dùng Java `Thread.currentThread().isVirtual()` từ một thread native attach rồi suy ra đang ở virtual thread của request ban đầu; task native đã chuyển thread thì context không tự chuyển.

### 9.3. Giữ monitor, lock hoặc critical pointer khi block

Native code có thể lấy JNI monitor bằng `MonitorEnter`, hoặc thao tác với critical array pin/copy. Nếu nó chờ rất lâu trước khi `MonitorExit`/release đúng cặp, có thể kéo dài lock contention và ảnh hưởng GC. Cần thiết kế phạm vi ngắn, tránh network I/O hoặc những thao tác chờ không giới hạn khi đang giữ resource như vậy.

### 9.4. JNI error và native error là hai kênh khác nhau

Khi C gặp timeout từ thư viện native, cần map sang Java exception hoặc result rõ ràng. `ExceptionCheck` chỉ báo **Java exception đang pending**; nó không tự phát hiện `errno`, return code hoặc native timeout. Nếu cần `ThrowNew`, phải kiểm tra rằng chưa có pending exception khác để không làm mất thông tin ban đầu.

## 10. Quan sát pinning và service ở production

Để kết luận native calls gây nghẽn, theo dõi cả **JVM-level** và **application-level**:

| Tín hiệu | Điều cần quan sát |
| --- | --- |
| JNI call duration histogram | p50/p95/p99, số call vượt deadline, loại operation |
| In-flight native calls | Số native work đang chạy; số platform workers thực sự bận |
| Native executor queue | Độ dài hàng đợi, thời gian chờ queue, rejection |
| Service throughput | Request/s hoàn thành, không chỉ số request đến |
| Request latency | p95/p99 của toàn request, theo endpoint và dependency |
| Virtual threads | Số đang chạy/chờ, stack Java nơi request blocked |
| Carrier/platform threads | OS thread states, stacks, số bị block trong C |
| CPU và native resources | CPU time, mutex contention, file descriptors, native heap |
| GC | Pause times, Java heap và JNI references/critical regions nếu có |
| Timeout/cancel | Số request timeout nhưng native work tiếp tục sống |

### 10.1. JDK Flight Recorder (JFR)

Trên các JDK phù hợp, JFR có sự kiện `jdk.VirtualThreadPinned`. Tài liệu Oracle mô tả sự kiện này dùng quan sát trường hợp virtual thread bị pin khi thực hiện một số **blocking operations**, thường với ngưỡng duration mặc định khoảng 20 ms. Có thể bắt đầu bản ghi rồi in:

```bash
java -XX:StartFlightRecording=filename=native-impact.jfr,dumponexit=true,settings=profile \
  --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. NativeImpactDemo

jfr print --events jdk.VirtualThreadPinned native-impact.jfr
```

**Cảnh báo diễn giải:** một lời gọi C trực tiếp vào `nanosleep()` có thể **không xuất hiện** như một `jdk.VirtualThreadPinned` event tùy cách JVM ghi nhận blocking. JFR event không phải máy đếm mọi nanosecond trong mọi JNI call. Không có event pinning **không chứng minh** native code không giữ carrier. Với JNI trực tiếp, hãy kết hợp đo timer quanh call, thread sampling, native profiling và số lượng active callers.

Một event ở ngữ cảnh callback Java có thể ghi reason như `Native or VM frame on stack`; điều quan trọng là stack và duration cho thấy nơi carrier không được giải phóng. Các trường chi tiết của event khác nhau theo JDK.

### 10.2. Thread dump và profiler

Ví dụ một Java process đang chạy có PID đã biết:

```bash
jcmd <PID> Thread.dump_to_file -format=json threads.json
```

Đây là **lệnh minh họa**, phải thay `<PID>` bằng PID thực tế; đừng gõ literal `<PID>` trong shell. Thread dump có thể hiển thị virtual threads đang chờ, mounted virtual threads và các native frames ở mức stack có thể lấy được. Với JDK/VM hỗ trợ, dùng JFR và native CPU profiler hoặc OS thread sampling để truy vết thời gian chờ trong thư viện C.

**Không kết luận từ một mẫu đơn lẻ.** Một profiler có thể lấy mẫu đúng lúc task vừa mới bắt đầu; để biết long-tail, cần nhiều samples và tracing theo request.

### 10.3. Thử tải có kiểm soát

Cần so sánh ít nhất hai đường chạy **cùng work**:

1. **Direct JNI trên virtual thread.**
2. **Offload JNI sang bounded platform executor, virtual thread chờ completion.**

Giữ cùng native library, dữ liệu, thời gian chờ và giới hạn dependency; đo nhiều mức concurrency (ví dụ 1, 4, 16, 64, 256). Thu p50/p95/p99, throughput, native in-flight, worker utilization và queue wait. Bên cạnh đó có một Java-only sleep/I/O baseline để thấy khả năng unmount khi không có native frame.

Không áp các kết quả thử tải trên Linux vào Windows, macOS hoặc JDK khác mà không kiểm chứng. Tuning của scheduler và thư viện native có thể ảnh hưởng đáng kể.

## 11. Checklist thiết kế JNI cho dịch vụ dùng virtual threads

**Trước khi triển khai:**

1. Liệt kê mọi JNI native methods được gọi từ request virtual threads và xem chúng có block, lock, sleep, I/O hoặc CPU work dài không.
2. Xác định thời gian bình thường và worst-case của từng call; nếu không có deadline/timeout trong native API, coi đây là rủi ro service.
3. Kiểm tra thread-safety và concurrency limit của C library, global mutex, memory pool, file descriptors, downstream backend.
4. Chọn trực tiếp JNI (khi ngắn), bounded platform pool (khi sync-blocking), hoặc async native API có completion (khi workload đáng đầu tư).
5. Áp dụng backpressure với giới hạn **số native calls đang chạy + số yêu cầu đang chờ**, không dùng queue vô hạn.
6. Xác định chính sách khi pool quá tải: rejection, timeout hoặc retry có giới hạn; tránh caller-runs vô tình làm blocking JNI trên carrier.
7. Quy định cancellation và lifecycle native resources: `Thread.interrupt`/`Future.cancel` không phải native cancel mặc định.
8. Cleanup JNI refs, arrays, strings, local frames và native allocations ở mọi nhánh lỗi/thành công; không giữ critical pointer qua I/O wait.
9. Không chia sẻ `JNIEnv *` giữa threads; dùng global reference đúng cách nếu async worker cần giữ Java object qua lời gọi.
10. Đo carrier contention, request latency, native call duration, queue depth và JFR; kiểm tra cả JDK 21–23 và JDK 24+ nếu sản phẩm hỗ trợ nhiều runtime.
11. Giữ các API Java chờ `Future` hoặc kết quả native **ngoài native frame** khi muốn virtual thread unmount trong lúc chờ.
12. Không dùng tăng số virtual threads làm biện pháp tăng công suất một thư viện C có năng lực cố định.

**Quy tắc thực hành:** virtual threads rất hữu ích khi số lượng lớn request chờ bằng Java APIs có khả năng nhường carrier. Nhưng nếu request đi vào một **JNI native call kéo dài**, carrier có thể bị giữ cho đến khi native trả về. Hãy đo loại chờ, giới hạn số JNI calls đang thực thi, cô lập blocking work hoặc dùng native async thực sự và kiểm soát deadline. Mục tiêu là để service vẫn xử lý được request khác ngay cả khi một native dependency chậm.

### Tài liệu tham khảo

- [Oracle JDK 21 — Virtual Threads, scheduling, pinning và JFR](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle JDK 25 — Virtual Threads, native pinning và diagnostics](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [Java SE 21 — JNI Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html)
- [Java SE 21 — JNI Functions, references và critical regions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html)
