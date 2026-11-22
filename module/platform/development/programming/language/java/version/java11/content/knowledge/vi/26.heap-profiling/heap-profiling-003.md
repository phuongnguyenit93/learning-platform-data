# SetHeapSamplingInterval và tần suất lấy mẫu — Heap profiling trong Java 11

## Mục tiêu

**`SetHeapSamplingInterval`** là API của **JVM Tool Interface (JVMTI)** được đưa vào Java 11 theo **JEP 331 — Low-Overhead Heap Profiling**. Đây là hàm **native** do một profiling agent gọi qua `jvmtiEnv`, không phải phương thức Java thuần hoặc một cấu hình JFR. Nó điều chỉnh **khoảng byte cấp phát trung bình giữa các mẫu** của event `SampledObjectAlloc`, nhằm giúp profiler điều tra nguồn gốc allocation với chi phí thấp hơn việc quan sát mọi object.

Bài học đi từ hợp đồng API, ý nghĩa thống kê của sampling interval đến việc tạo agent C++/Java workload chạy thật; tập trung vào các kiến thức **vẫn được hỗ trợ trên Java 11 và JDK hiện đại**, không dùng API nội bộ đã lỗi thời.

Sau bài này bạn có thể:

1. Phân biệt **allocation sampling**, heap dump, GC metrics, retained-heap leak analysis, `VMObjectAlloc` và JFR.
2. Hiểu `sampling_interval` đo bằng **bytes trung bình trên mỗi thread**, không phải thời gian hay số object.
3. Giải thích mặc định **512 KiB**, `0` đặc biệt, giá trị âm bị từ chối, overhead thay đổi khi chọn interval.
4. Biết sampling mang tính **pseudo-random** để hạn chế bias; không assert số callback chính xác từ một lượng bytes đã cấp phát.
5. Xin capability `can_generate_sampled_object_alloc_events`, cài callback, gọi `SetHeapSamplingInterval` và bật `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC`.
6. Phân biệt lỗi `JVMTI_ERROR_MUST_POSSESS_CAPABILITY`, `JVMTI_ERROR_ILLEGAL_ARGUMENT`, `JVMTI_ERROR_WRONG_PHASE`, và hiểu chức năng **Callback Safe: No**.
7. Biên dịch một **native JVMTI agent C++17** và chương trình workload **Java 11-compatible**, đo xu hướng số callback ở các interval khác nhau.
8. Không nhầm tổng size của *sampled objects* với tổng bytes ứng dụng đã cấp phát; biết giới hạn khi kết luận memory leak.
9. Chọn sampling interval dựa trên **độ phân giải, độ nhiễu thống kê, overhead và độ dài quan sát**.
10. Tránh làm profiling trở thành nguyên nhân chậm, rò rỉ references hoặc ghi dữ liệu nhạy cảm.

## 1. Khái niệm và vị trí trong JVM

### 1.1. JVMTI là giao diện native

JVMTI cho phép các công cụ monitoring/profiling chạy **trong cùng process với JVM** nhận callback, hỏi thông tin và điều khiển một số hành vi JVM. Agent được đóng gói dạng shared library:

| Hệ điều hành | Native agent | Cách nạp |
| --- | --- | --- |
| Linux | `libheapsample.so` | `-agentpath:/path/libheapsample.so=65536` |
| Windows | `heapsample.dll` | `-agentpath:C:\path\heapsample.dll=65536` |
| macOS | `libheapsample.dylib` | `-agentpath:/path/libheapsample.dylib=65536` |

`=65536` là **chuỗi options** do agent tự parse và chuyển thành `jint` khi gọi JVM TI; JVM không tự chuyển option đó thành sampling interval khi một thư viện chưa cài logic tương ứng. `-agentpath` là cú pháp JVM hỗ trợ để nạp native agent tại startup. Agent ví dụ có `Agent_OnLoad`, **không có `Agent_OnAttach`**, nên không triển khai dynamic attach.

Luồng tối giản:

~~~text
JVM startup
   |
   +--> Agent_OnLoad(JavaVM*, options, ...)
            |
            +--> GetEnv(JVMTI_VERSION_1_2)
            +--> AddCapabilities(sampled object allocation)
            +--> GetCapabilities() để xác nhận
            +--> SetEventCallbacks(SampledObjectAlloc)
            +--> SetHeapSamplingInterval(intervalBytes)
            +--> SetEventNotificationMode(JVMTI_ENABLE, event 86, NULL)
                  |
                  v
        JVM ghi nhận một phần các object allocations
                  |
                  v
        SampledObjectAlloc(... thread, object, class, size)
                  |
                  v
        Agent tổng hợp counters/stack data
                  |
                  v
          Agent_OnUnload: xuất báo cáo
~~~

### 1.2. Khác nhau giữa các công cụ heap

| Cơ chế | Phản ánh | Lưu ý |
| --- | --- | --- |
| **`SampledObjectAlloc`** | Một phần Java heap allocations được chọn mẫu, kèm thread/class/object/size | Chịu sự điều chỉnh của `SetHeapSamplingInterval`. |
| **`VMObjectAlloc`** | Một số allocation do VM thực hiện trực tiếp | Không phải callback cho mọi bytecode `new/newarray`; khác `SampledObjectAlloc`. |
| **JFR allocation events** | Event allocation do Java Flight Recorder cung cấp | Hữu ích, nhưng không đồng nhất với JVMTI API này. |
| **Heap dump** | Snapshot các đối tượng còn hiện diện cùng references | Không tự cung cấp lịch sử allocations. |
| **Retained-object analysis** | Objects còn được giữ lại sau thời gian/GC | Gần mục tiêu memory leak hơn allocation rate thuần. |
| **GC statistics** | GC count, pause, heap usage | Không tự chỉ ra call site đang cấp phát. |
| **Native memory tracking** | Native memory/metaspace/malloc | Không thuộc phạm vi Java object sampling của hàm này. |

Đặc biệt, allocation rate cao **không tự chứng minh memory leak**: nhiều objects được tạo rồi thu hồi nhanh có thể tạo GC pressure nhưng không tăng retained heap.

## 2. Hợp đồng SetHeapSamplingInterval

### 2.1. Chữ ký chuẩn Java 11

Đặc tả C của JVM TI:

~~~c
jvmtiError SetHeapSamplingInterval(
        jvmtiEnv* env,
        jint sampling_interval);
~~~

Trong wrapper C++ từ `jvmti.h`:

~~~cpp
jvmtiError err = jvmti->SetHeapSamplingInterval(65536);
~~~

Trong native C API:

~~~c
jvmtiError err =
    (*jvmti)->SetHeapSamplingInterval(jvmti, 65536);
~~~

Các đoạn trên là **minh họa**, chưa bao gồm việc lấy `jvmtiEnv*`, capability và callback; chương trình chạy đầy đủ có ở mục 6.

**`sampling_interval` là số byte trung bình giữa các mẫu**, được đo **riêng trên mỗi thread**. JVM dùng một cách tiếp cận thống kê, chứ không tăng một global counter và phát callback đúng từng bội của 65536. Thay đổi interval có thể cần **một số lần cấp phát** để trạng thái nội bộ cập nhật.

### 2.2. Các giá trị cần nhớ

| Interval | Ý nghĩa | Tác động |
| --- | --- | --- |
| **Không gọi hàm** | JVMTI `SampledObjectAlloc` mặc định **512 KiB = 524288 bytes** | Sampling ở mức trung bình. |
| `1048576` (1 MiB) | Khoảng 1 mẫu trên mỗi MiB cấp phát/thread | Thường ít callbacks, overhead thấp hơn. |
| `65536` (64 KiB) | Khoảng 1 mẫu trên mỗi 64 KiB cấp phát/thread | Nhiều mẫu hơn, overhead cao hơn. |
| `1024` | Khoảng 1 mẫu trên mỗi KiB cấp phát/thread | Có thể rất đắt với workload allocation lớn. |
| **`0`** | **Mỗi allocation được hỗ trợ**, sau khi interval mới có hiệu lực | Không phải tắt profiling; overhead có thể rất lớn. |
| `-1` hoặc bất kỳ số âm | **Không hợp lệ** | Trả `JVMTI_ERROR_ILLEGAL_ARGUMENT` nếu được truyền đến hàm. |
| Số vượt khả năng của `jint` | Không biểu diễn được | Agent phải validate trước khi cast. |

**`jint` là số nguyên signed 32-bit**; các giá trị hợp lệ không âm biểu diễn được nằm trong **0..2.147.483.647**. Đừng để parsing overflow hay cast một `long` rất lớn thành một giá trị âm ngoài ý muốn.

**Điểm dễ nhầm:** hàm `SetHeapSamplingInterval(0)` **không tắt** sampler mà chuyển tới mức phát event cho từng allocation được hỗ trợ. Muốn disable notification, dùng **`SetEventNotificationMode(JVMTI_DISABLE, JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, nullptr)`** trên JVMTI environment. Việc ngừng nhận event và việc lựa chọn interval là hai việc khác nhau.

### 2.3. Vì sao đơn vị bytes và «mỗi thread» quan trọng?

Ví dụ hai threads:

~~~text
Thread A: cấp phát 64 MiB
Thread B: cấp phát  4 MiB
sampling_interval = 1 MiB

Số callback kỳ vọng trực giác trong quan sát đủ dài:
 A ~64 samples
 B ~4 samples

KHÔNG có nghĩa:
 - cứ mỗi giây gọi 1 callback;
 - hai threads dùng chung một counter 1 MiB;
 - đúng allocation thứ N luôn bị chọn;
 - chỉ objects >=1 MiB mới được chọn;
 - sau đúng 1.048.576 bytes nhất thiết có event.
~~~

JVMTI Java 11 quy định sampler theo byte allocations của **từng thread** và chọn khoảng cách **pseudo-random**, nên một thread cấp phát ít trong khoảng đo ngắn có thể không có sample. Phân bố số callback còn bị ảnh hưởng bởi JVM startup, class loading, allocator, JIT, GC, kích thước object, scheduling và thời lượng đo.

### 2.4. Vì sao cần pseudo-random?

Giả sử chương trình lặp các allocations theo pattern `A,B,C,D` ở chu kỳ chính xác 32 KiB. Nếu sampler cứ chọn đúng bội 32 KiB, nó có thể vô tình chọn loại D quá nhiều và bỏ A/B/C. Chọn khoảng cách **pseudo-random với trung bình cố định** giúp giảm loại **phase/pattern bias** này.

Điều đó không có nghĩa các objects kích thước khác nhau có xác suất được chọn giống hệt nhau. Một allocation lớn có thể bao trùm nhiều byte, nên cần hiểu chính sách sampling/statistical weighting của profiler trước khi ước lượng **object count hoặc allocated bytes theo type/call site**.

### 2.5. Số mẫu kỳ vọng chỉ là ước lượng

Khi interval lớn hơn 0, một công thức **trực giác**:

~~~text
expected_sample_count ~ allocated_bytes / sampling_interval_bytes
~~~

Với **64 MiB = 67.108.864 payload bytes**:

| Interval | Ước lượng thô |
| --- | ---: |
| 1 MiB | ~64 samples |
| 512 KiB | ~128 samples |
| 64 KiB | ~1024 samples |
| 1 KiB | ~65536 samples |
| 0 | Không được chia cho 0; gần mỗi object allocation được hỗ trợ |

Đây **không phải các số phải kiểm định chính xác bằng assertion**. Payload bytes chưa tính headers/alignment của các mảng, các allocations khác của JVM hoặc kết quả pseudo-random. Với interval 0, callback count liên quan tới **số allocations**, không thể suy từ bytes bằng phép chia đơn giản.

### 2.6. Cảnh báo: sample size không bằng total allocation size

Callback `SampledObjectAlloc` nhận `size`, biểu diễn size của **đối tượng được lấy mẫu**. Agent ví dụ cộng các sizes:

~~~text
sampled_object_bytes_sum = SUM(size của những objects được sample)
~~~

Tổng này **không phải** tổng bytes chương trình đã allocate. Nếu một JVM cấp phát 64 MiB nhưng nhận 52 samples mỗi object khoảng 2 KiB, tổng `sampled_object_bytes_sum` chỉ khoảng 100 KiB là bình thường. Để suy ra toàn population theo call stack/class, cần mô hình thống kê/weighting phù hợp, đủ mẫu và hiểu kích thước object.

## 3. Capability, event và phase

### 3.1. Capability bắt buộc

JVMTI sampled allocation là **optional functionality**; việc có tên method trong header **không bảo đảm mọi JVM implementation đều hỗ trợ**. Agent phải xin:

~~~cpp
jvmtiCapabilities caps{};
caps.can_generate_sampled_object_alloc_events = 1;
jvmtiError error = jvmti->AddCapabilities(&caps);
~~~

Sau `AddCapabilities` nên kiểm kết quả và `GetCapabilities`. Nếu environment không sở hữu capability, `SetHeapSamplingInterval` trả **`JVMTI_ERROR_MUST_POSSESS_CAPABILITY`**. Không được lặng lẽ chuyển profiler sang trạng thái «đang lấy mẫu» nếu setup thực tế không thành công.

### 3.2. SampledObjectAlloc callback

Event **`JVMTI_EVENT_SAMPLED_OBJECT_ALLOC`** (event number **86**, Since Java 11) có callback:

~~~cpp
void JNICALL SampledObjectAlloc(
    jvmtiEnv* jvmti_env,
    JNIEnv* jni_env,
    jthread thread,
    jobject object,
    jclass object_klass,
    jlong size);
~~~

Nó được phát **sau khi một object được allocate và được sampler chọn** trong **live phase**.

- `thread`: thread thực hiện allocation.
- `object`: JNI reference đến object; không giữ lại quá callback khi chưa quản lý JNI reference lifetime.
- `object_klass`: class của object.
- `size`: số bytes của object theo semantics `GetObjectSize`.
- `JNIEnv*` và `jvmtiEnv*`: environments tương ứng tại callback.

Callback có thể xảy ra **đồng thời từ nhiều threads**. Shared counters phải thread-safe; việc log từng callback, allocate thêm objects, block trên I/O hoặc giữ lock trong callback có thể làm sai kết quả profile hay giảm throughput mạnh.

### 3.3. Phase và callback safety

Thông số JVM TI Java 11:

~~~text
Function    : SetHeapSamplingInterval
Since       : 11
Phases      : OnLoad or live
Callback Safe: No
~~~

Do **Callback Safe: No**, **không gọi `SetHeapSamplingInterval` ngay bên trong callback `SampledObjectAlloc`**. Muốn thay interval lúc runtime, phải dùng một đường điều khiển riêng của agent ở ngữ cảnh/phase hợp lệ. Agent minh họa chỉ cấu hình một lần trong `Agent_OnLoad` rồi giữ nguyên.

### 3.4. Những error codes quan trọng

| Mã | Ý nghĩa |
| --- | --- |
| `JVMTI_ERROR_NONE` | Thành công. |
| `JVMTI_ERROR_MUST_POSSESS_CAPABILITY` | Chưa có `can_generate_sampled_object_alloc_events`. |
| `JVMTI_ERROR_ILLEGAL_ARGUMENT` | Interval **< 0**. |
| `JVMTI_ERROR_WRONG_PHASE` | Gọi ngoài OnLoad/live phase. |
| `JVMTI_ERROR_UNATTACHED_THREAD` | Calling thread không được attach đúng vào JVM. |
| `JVMTI_ERROR_INVALID_ENVIRONMENT` | JVMTI env không còn hợp lệ. |
| `JVMTI_ERROR_OUT_OF_MEMORY`, `JVMTI_ERROR_INTERNAL` | Lỗi tài nguyên/hệ thống. |

Đây là các tình huống đáng chẩn đoán, không phải toàn bộ universal errors của JVMTI. Kiểm **`jvmtiError` trả về từ mọi bước**, không đoán thành công chỉ vì chương trình Java chạy xong.

## 4. Native agent hoàn chỉnh bằng C++17

### 4.1. File HeapSampleAgent.cpp

Chương trình minh họa **startup agent**, parse optional interval bytes, kiểm capability, cấu hình callback và cộng **hai atomic counters**. Callback làm rất ít việc để tránh tăng overhead do chính profiler gây ra. `Agent_OnUnload` chỉ in aggregate counters, không in thông tin mỗi object.

~~~cpp
#include <jni.h>
#include <jvmti.h>
#include <atomic>
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>

static std::atomic<unsigned long long> sampledCount{0};
static std::atomic<unsigned long long> sampledObjectBytes{0};

static void JNICALL onSampledAllocation(jvmtiEnv* jvmti, JNIEnv* jni,
        jthread thread, jobject object, jclass objectClass, jlong size) {
    (void)jvmti;
    (void)jni;
    (void)thread;
    (void)object;
    (void)objectClass;
    sampledCount.fetch_add(1, std::memory_order_relaxed);
    if (size > 0) {
        sampledObjectBytes.fetch_add(static_cast<unsigned long long>(size),
                                     std::memory_order_relaxed);
    }
}

static bool check(jvmtiError error, const char* operation) {
    if (error == JVMTI_ERROR_NONE) return true;
    std::fprintf(stderr, "[agent] %s failed: JVMTI error %d\n",
                 operation, static_cast<int>(error));
    return false;
}

extern "C" JNIEXPORT jint JNICALL Agent_OnLoad(JavaVM* vm,
        char* options, void* reserved) {
    (void)reserved;
    long interval = 512L * 1024L;
    if (options != nullptr && options[0] != '\0') {
        errno = 0;
        char* end = nullptr;
        interval = std::strtol(options, &end, 10);
        if (errno == ERANGE || end == options || *end != '\0'
                || interval < 0 || interval > INT_MAX) {
            std::fprintf(stderr,
                         "[agent] interval must be a nonnegative jint byte count\n");
            return JNI_ERR;
        }
    }

    jvmtiEnv* jvmti = nullptr;
    if (vm->GetEnv(reinterpret_cast<void**>(&jvmti), JVMTI_VERSION_1_2)
            != JNI_OK || jvmti == nullptr) {
        std::fprintf(stderr, "[agent] JVM TI 1.2 not available\n");
        return JNI_ERR;
    }

    jvmtiCapabilities request{};
    request.can_generate_sampled_object_alloc_events = 1;
    if (!check(jvmti->AddCapabilities(&request), "AddCapabilities")) {
        return JNI_ERR;
    }
    jvmtiCapabilities actual{};
    if (!check(jvmti->GetCapabilities(&actual), "GetCapabilities")
            || !actual.can_generate_sampled_object_alloc_events) {
        std::fprintf(stderr, "[agent] sampling capability unavailable\n");
        return JNI_ERR;
    }

    jvmtiEventCallbacks callbacks{};
    callbacks.SampledObjectAlloc = &onSampledAllocation;
    if (!check(jvmti->SetEventCallbacks(&callbacks, sizeof(callbacks)),
               "SetEventCallbacks")) {
        return JNI_ERR;
    }
    if (!check(jvmti->SetHeapSamplingInterval(static_cast<jint>(interval)),
               "SetHeapSamplingInterval")) {
        return JNI_ERR;
    }
    if (!check(jvmti->SetEventNotificationMode(
            JVMTI_ENABLE, JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, nullptr),
            "SetEventNotificationMode")) {
        return JNI_ERR;
    }
    std::fprintf(stderr, "[agent] interval_bytes=%ld\n", interval);
    return JNI_OK;
}

extern "C" JNIEXPORT void JNICALL Agent_OnUnload(JavaVM* vm) {
    (void)vm;
    std::fprintf(stderr,
                 "[agent] sampled_events=%llu sampled_object_bytes_sum=%llu\n",
                 sampledCount.load(std::memory_order_relaxed),
                 sampledObjectBytes.load(std::memory_order_relaxed));
}
~~~

### 4.2. Phân tích thứ tự khởi tạo

1. **Parse input:** `Agent_OnLoad` nhận options dạng string. `strtol` kiểm cú pháp/overflow, từ chối âm và số ngoài phạm vi `jint`; không ép kiểu một số lớn cho ra giá trị âm.
2. **GetEnv:** lấy `jvmtiEnv*` qua `JavaVM::GetEnv` và `JVMTI_VERSION_1_2`. Một VM không cung cấp môi trường phù hợp khiến agent trả `JNI_ERR`.
3. **AddCapabilities:** yêu cầu capability sampled allocation; `GetCapabilities` xác nhận. Không có capability thì setup thất bại, không tuyên bố profiler đang chạy.
4. **SetEventCallbacks:** đặt `SampledObjectAlloc` callback trước khi enable, tránh có notification mà handler chưa được cài.
5. **SetHeapSamplingInterval:** cấu hình interval đúng đơn vị byte, khi agent đang trong OnLoad phase.
6. **SetEventNotificationMode:** bật `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC` cho toàn bộ threads bằng tham số thread `nullptr`.
7. **Callback:** chỉ cập nhật atomic counters, không giữ `jobject`, không gọi I/O/SetHeapSamplingInterval tại đây.
8. **Unload:** in số callbacks và tổng kích thước **những objects được sample**. Đừng dùng tổng này làm tổng heap allocations.

**Đây là một agent thử nghiệm có giới hạn**, không phải profiler thương mại hoàn chỉnh. Nó chưa thu stack traces/call sites, chưa lưu thread attribution và chưa thiết kế ring buffer, sampling weights hoặc security policy. Nếu phát triển thêm, tránh cấp phát trong callback, xử lý backpressure, giới hạn retention và kiểm callback-safe APIs.

## 5. Java workload tương thích Java 11

### 5.1. File HeapSamplingWorkload.java

Mục đích: tạo đủ lượng allocations để quan sát xu hướng interval. Mỗi trong **4 threads** tạo **8192** mảng `byte[2048]`, tương đương **64 MiB tổng payload**. Một tham chiếu `volatile` ra ngoài vòng lặp đảm bảo các allocations không trở thành dữ liệu chết dễ bị JIT loại bỏ.

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public final class HeapSamplingWorkload {
    private static final int THREADS = 4;
    private static final int ARRAYS_PER_THREAD = 8192;
    private static final int BYTES_PER_ARRAY = 2048;
    private static volatile byte[] lastAllocation;

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicLong plannedPayloadBytes = new AtomicLong();
        AtomicInteger finishedWorkers = new AtomicInteger();
        Thread[] threads = new Thread[THREADS];

        for (int t = 0; t < THREADS; t++) {
            threads[t] = new Thread(() -> {
                long localBytes = 0;
                for (int i = 0; i < ARRAYS_PER_THREAD; i++) {
                    byte[] payload = new byte[BYTES_PER_ARRAY];
                    payload[0] = (byte) i;
                    lastAllocation = payload; // volatile escape
                    localBytes += payload.length;
                }
                plannedPayloadBytes.addAndGet(localBytes);
                finishedWorkers.incrementAndGet();
            }, "alloc-worker-" + t);
            threads[t].start();
        }

        for (Thread thread : threads) {
            thread.join();
        }

        check(finishedWorkers.get() == THREADS, "all threads finished");
        System.out.println("PASS four allocation threads completed");

        long expected = (long) THREADS * ARRAYS_PER_THREAD * BYTES_PER_ARRAY;
        check(expected == 67_108_864L, "expected payload arithmetic");
        check(plannedPayloadBytes.get() == expected,
                "all requested array payload bytes counted");
        System.out.println("PASS requested array payload bytes = 67108864");

        check(lastAllocation != null
                && lastAllocation.length == BYTES_PER_ARRAY,
                "allocated arrays escaped via volatile reference");
        System.out.println("PASS allocations remain observable");

        System.out.println("ALL HEAP WORKLOAD TESTS PASSED");
    }
}
~~~

**Lưu ý diễn giải:** `67.108.864` là **tổng payload bytes ứng dụng yêu cầu cấp phát**, không phải `GetObjectSize` tổng. Heap allocation thực tế có thêm array object headers, padding/alignment, allocations của JVM và các đối tượng khác. Do đó không được khẳng định sampler phải phát chính xác `67.108.864 / interval` callbacks.

## 6. Biên dịch và kiểm thử

### 6.1. Linux: C++17 + JDK 11 trở lên

Đứng trong thư mục chứa `HeapSampleAgent.cpp` và `HeapSamplingWorkload.java`. Cần `g++` cùng JDK headers:

~~~bash
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

g++ -std=c++17 -Wall -Wextra -Werror -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libheapsample.so HeapSampleAgent.cpp

javac --release 11 -encoding UTF-8 HeapSamplingWorkload.java

java -Xms64m -Xmx128m -cp . HeapSamplingWorkload

java -Xms64m -Xmx128m "-agentpath:$PWD/libheapsample.so=1048576" -cp . HeapSamplingWorkload
java -Xms64m -Xmx128m "-agentpath:$PWD/libheapsample.so=65536" -cp . HeapSamplingWorkload
java -Xms64m -Xmx128m "-agentpath:$PWD/libheapsample.so=0" -cp . HeapSamplingWorkload
~~~

Lệnh `javac --release 11` kiểm rằng source Java tương thích baseline 11. **Bộ test thực tế đã chạy trên Linux với JDK 21 và g++14** (native agent compiled `-Wall -Wextra -Werror`), **không phải runtime Java 11**. Nếu ứng dụng yêu cầu chạy Java 11, cần CI riêng trên vendor/build JDK 11 thực sự.

### 6.2. Windows (cần MSVC C++ Build Tools)

Trong **Developer PowerShell for Visual Studio**, có `cl.exe` và `JAVA_HOME` trỏ JDK:

~~~powershell
cl /nologo /std:c++17 /EHsc /LD /I "$env:JAVA_HOME\include" /I "$env:JAVA_HOME\include\win32" HeapSampleAgent.cpp /link /OUT:heapsample.dll

javac --release 11 -encoding UTF-8 HeapSamplingWorkload.java

$dll = (Resolve-Path .\heapsample.dll).Path
java -Xms64m -Xmx128m "-agentpath:$dll=65536" -cp . HeapSamplingWorkload
~~~

Đây là **hướng dẫn build Windows**, chưa được thực thi kiểm thử trên Windows trong lượt làm bài vì máy Windows không có compiler C++ khả dụng. Không dùng flags GCC `-fPIC/-shared` trực tiếp cho MSVC. Cần build agent đúng architecture của JVM và có các JNI/JVMTI headers từ JDK.

### 6.3. Stdout Java ổn định

Khi chạy workload không có agent hoặc agent cấu hình thành công, stdout Java:

~~~text
PASS four allocation threads completed
PASS requested array payload bytes = 67108864
PASS allocations remain observable
ALL HEAP WORKLOAD TESTS PASSED
~~~

Khi nạp agent, các dòng `[agent]` in ra **stderr**, nên thứ tự tương đối có thể thay đổi do buffering. Số callback **không phải exact stdout bắt buộc**. Trên **một lần chạy Linux/JDK 21**, kết quả quan sát:

~~~text
# 1 MiB interval:
[agent] interval_bytes=1048576
[agent] sampled_events=52 sampled_object_bytes_sum=107328

# 64 KiB interval:
[agent] interval_bytes=65536
[agent] sampled_events=1009 sampled_object_bytes_sum=2080536

# Interval 0:
[agent] interval_bytes=0
[agent] sampled_events=33772 sampled_object_bytes_sum=67679112

# Không truyền options, agent dùng 512 KiB:
[agent] interval_bytes=524288
[agent] sampled_events=139 sampled_object_bytes_sum=284856
~~~

Những giá trị trên là **ví dụ thực nghiệm, không phải số phải khớp**: thay đổi theo random sampling, runtime, thread scheduling, JIT, GC, allocations khác ngoài 64 MiB payload và thời lượng chạy. Điều cần thấy là xu hướng: interval nhỏ hơn làm callback count tăng và có khả năng tăng profiling overhead.

### 6.4. Kiểm giá trị âm

~~~bash
java "-agentpath:$PWD/libheapsample.so=-1" -cp . HeapSamplingWorkload
~~~

Agent mẫu **tự validate trước** nên không gọi JVM TI với số âm, báo:

~~~text
[agent] interval must be a nonnegative jint byte count
~~~

JVM có thể in thêm thông báo `agent library failed Agent_OnLoad` rồi thoát với exit code khác 0. Nếu code bỏ bước validation và gọi `SetHeapSamplingInterval(-1)` trực tiếp, JVM TI trả **`JVMTI_ERROR_ILLEGAL_ARGUMENT`** theo spec.

## 7. Đổi interval, disable callback và quản trị vòng đời

### 7.1. Đổi interval khác với disable

Mã minh họa trong agent có `jvmtiEnv*` hợp lệ:

~~~cpp
// Chuyển sang trung bình 1 MiB mỗi sample:
jvmti->SetHeapSamplingInterval(1024 * 1024);

// Tắt sampled allocation notifications:
jvmti->SetEventNotificationMode(
        JVMTI_DISABLE, JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, nullptr);

// Khi cần, bật lại notification:
jvmti->SetEventNotificationMode(
        JVMTI_ENABLE, JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, nullptr);
~~~

**Ba dòng gọi này phải kiểm `jvmtiError` ở production**, và `SetHeapSamplingInterval` chỉ được gọi tại ngữ cảnh callback-safe/phase hợp lệ. **Không dùng 0 để tắt event**. Nếu nhiều JVMTI environments/agents cùng quan sát JVM, cấu hình và hành vi có thể tương tác; profiler cần có chính sách quản lý setup/disable rõ ràng.

### 7.2. Thay interval khi ứng dụng đang chạy

Spec cho phép gọi trong **live phase**, nhưng việc cấu hình mới có thể mất một số allocations để cập nhật nội bộ. Do đó:

1. Chuyển cấu hình từ **control thread của agent**, không gọi trực tiếp từ sample callback.
2. Ghi timestamp/interval có hiệu lực theo chính sách đo, tránh nhập nhằng giai đoạn chuyển tiếp.
3. Chừa warm-up/transient period trước khi so sánh số liệu.
4. Không dùng callback đầu tiên sau khi đổi interval làm mốc tuyệt đối.
5. Kiểm lỗi API; nếu thất bại, không báo dashboard rằng interval mới đã áp dụng.

### 7.3. Sampling 0 có thể làm hỏng chính phép đo

Ở interval 0, callback được phát cho gần mọi allocation được hệ thống hỗ trợ khi cập nhật đã có hiệu lực. Nếu callback lại in log, format stack trace, allocate data structures hoặc gọi external I/O, nó có thể tạo **rất nhiều overhead**, tăng GC pressure, tạo bottleneck, thậm chí làm thay đổi allocation behavior vốn đang được đo.

Agent mẫu dùng **atomic increments với `memory_order_relaxed`** và không giữ object references, giảm bớt chi phí. Tuy vậy interval 0 trên workload lớn vẫn có thể tốn CPU; chỉ nên dùng ở **môi trường kiểm thử có kiểm soát**, không mặc định bật trong production.

## 8. Chọn interval theo mục tiêu thực tế

### 8.1. Độ phân giải và overhead là đánh đổi

| Mục tiêu | Hướng chọn interval |
| --- | --- |
| Quan sát lâu dài với chi phí thấp | Bắt đầu **1 MiB hoặc 512 KiB**, đo overhead và độ ổn định. |
| Điều tra hot allocation sites trong staging | Cân nhắc **256 KiB, 128 KiB hoặc 64 KiB**, giữ workload tương đương. |
| Cần phân tích ngắn hạn rất chi tiết | Chọn nhỏ hơn khi đã kiểm CPU/memory/disk overhead và callback cost. |
| Muốn thấy mọi allocation hỗ trợ để test agent | `0` trong bài kiểm thử **ngắn và có giới hạn**. |
| Không muốn callback nữa | **`JVMTI_DISABLE`**, không phải interval 0. |

Không có một con số «tốt nhất» chung cho mọi ứng dụng. Chọn theo **allocation throughput**, request mix, độ dài profile, CPU/latency budget, khả năng chứa samples, mục tiêu thống kê và logic callback. Một service cấp phát 2 GiB/s có thể tạo ước lượng cỡ 2048 callbacks/s ở interval 1 MiB và 32768 callbacks/s ở 64 KiB; nếu callback capture stack trace sâu và gửi qua mạng, overhead sẽ khác rất nhiều so với chỉ atomic increment.

### 8.2. Quy trình benchmark đúng

1. **Baseline:** chạy không có agent; ghi throughput, latency p95/p99, CPU, GC, heap.
2. **Profile interval lớn:** chạy 1 MiB hoặc 512 KiB trong cửa sổ đủ dài; kiểm mẫu nào có ý nghĩa thống kê.
3. **Profile interval thấp hơn:** giảm 128/64 KiB khi cần thêm detail, so overhead và tính ổn định.
4. **Warm-up:** dùng cùng Java/JDK vendor/version, GC, heap, JIT warm-up, thread count, request mix.
5. **Lặp nhiều lần:** so xu hướng và confidence, không kết luận từ một run ngắn.
6. **Phân tích theo thread/class/stack:** cần agent hoặc profiler có aggregation tương ứng; sample counter tổng chỉ dùng để học API.
7. **Giới hạn thời lượng/retention:** tránh giữ raw jobject strong references, không in secrets.
8. **Tổng hợp sau đo:** cross-check với JFR/GC/allocation metrics, không dùng JVMTI sample count thay cho heap dump.

### 8.3. Vì sao «không có samples» chưa chắc là lỗi?

Nếu một thread chỉ allocate vài KiB nhưng interval 1 MiB, việc chưa có sample là hoàn toàn bình thường. Một workload chỉ kéo dài vài milliseconds cũng có thể không đủ lượng allocations. Khi debug, nên tăng **thời lượng hoặc khối lượng workload** trước, kiểm enable/capability/phase, rồi mới giảm interval; không mở 0 trên production chỉ để nhìn thấy vài callbacks.

## 9. Troubleshooting

| Triệu chứng | Chẩn đoán |
| --- | --- |
| `-agentpath` không nạp được thư viện | Đường dẫn/architecture DLL/so sai, thiếu runtime dependencies, permission. |
| `GetEnv` thất bại | JVM TI không sẵn có hoặc yêu cầu version/VM không phù hợp. |
| `AddCapabilities` thất bại | VM không hỗ trợ optional capability hoặc không thể thêm ở phase hiện tại. |
| `MUST_POSSESS_CAPABILITY` | Agent chưa có `can_generate_sampled_object_alloc_events`. |
| `ILLEGAL_ARGUMENT` | Interval âm; kiểm parse và overflow. |
| `WRONG_PHASE` | Gọi ngoài OnLoad/live hoặc từ callback không hợp lệ. |
| Không nhận `SampledObjectAlloc` | Chưa `SetEventCallbacks`, event notification chưa enable, capability thiếu, workload quá nhỏ/interval quá lớn. |
| Interval 0 không có callback ngay ở object đầu tiên | Spec cho phép độ trễ cập nhật sampler nội bộ. |
| Số sample biến động giữa runs | Pseudo-random/per-thread/JIT/GC/thread scheduling và overhead khác nhau. |
| Tổng sampled size nhỏ hơn bytes workload | Chỉ là **sum sizes các sampled objects**, không phải total allocation. |
| Java vẫn báo PASS dù không thấy agent lines | Java workload độc lập với agent; cần nhìn **stderr** và xác nhận thư viện đã được nạp. |
| Object count cao nhưng heap không phình | Objects có thể sống ngắn và được GC, không tự là leak. |
| CPU tăng khi interval nhỏ | Callback overhead quá cao; tăng interval, giảm xử lý tại callback. |
| Windows không có `cl` hoặc thiếu `jvmti.h` | Thiếu C++ Build Tools/Developer PowerShell hoặc `JAVA_HOME/include/win32`. |
| Kết quả khác JDK 11 | `javac --release 11` không thay thế chạy native agent/JVMTI trên đúng runtime JDK11. |

## 10. Câu hỏi tự đánh giá

**1. SetHeapSamplingInterval là phương thức Java hay JVMTI?** — Là **hàm JVMTI native** trong `jvmti.h`, từ Java 11.

**2. Interval được đo theo gì?** — **Số byte cấp phát trung bình trên mỗi thread**, không theo số giây hay số object cố định.

**3. Giá trị mặc định là bao nhiêu?** — **512 KiB = 524288 bytes**.

**4. Đặt 0 có tắt callback không?** — **Không.** Nó yêu cầu lấy mẫu từng allocation được hỗ trợ khi cấu hình có hiệu lực; để tắt dùng `SetEventNotificationMode(JVMTI_DISABLE, ...)`.

**5. Giá trị âm trả lỗi gì?** — `JVMTI_ERROR_ILLEGAL_ARGUMENT` khi được truyền tới JVM TI. Agent mẫu chặn sớm bằng input validation.

**6. Capability nào bắt buộc?** — `can_generate_sampled_object_alloc_events`, cấp qua `AddCapabilities` và nên xác minh bằng `GetCapabilities`.

**7. Có thể gọi SetHeapSamplingInterval ngay trong SampledObjectAlloc callback không?** — **Không**, vì `Callback Safe: No`.

**8. Mỗi 65536 byte có chắc một callback đúng ranh giới không?** — **Không**. Sampler pseudo-random và per-thread, trung bình trong quan sát đủ dài.

**9. `SampledObjectAlloc` có giống `VMObjectAlloc` không?** — Không; chúng là hai JVMTI events với semantics khác nhau.

**10. `sampled_object_bytes_sum` có phải total heap allocations không?** — Không, chỉ là tổng sizes của các objects được chọn mẫu.

**11. Nhiều allocations có chắc là memory leak không?** — Không; cần kết hợp retained heap/GC/reachability.

**12. Vì sao callback dùng atomics?** — Có thể chạy đồng thời từ nhiều threads và cần cập nhật counters an toàn.

**13. Vì sao phải giữ `volatile` escape trong Java workload?** — Để allocations có side effect quan sát được, giảm khả năng JIT loại bỏ object chỉ dùng nội bộ.

**14. Tại sao `--release 11` chưa đủ để chứng minh native agent hoạt động trên Java 11?** — Compile target Java chỉ kiểm API/cú pháp của Java source; native library/JVMTI cần test trên **runtime** cụ thể.

## 11. Checklist

- [ ] Phân biệt SetHeapSamplingInterval (native JVMTI) với JFR, heap dump và VMObjectAlloc.
- [ ] Biết interval bytes **per-thread**, mặc định 512 KiB, pseudo-random.
- [ ] Nhớ `0` không disable sampling, giá trị âm không hợp lệ.
- [ ] Xin/kiểm capability `can_generate_sampled_object_alloc_events`.
- [ ] Cài callback và bật event `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC`.
- [ ] Không gọi SetHeapSamplingInterval từ callback; dùng đúng OnLoad/live phase.
- [ ] Callback thread-safe, không giữ mạnh references và không I/O/allocations nặng.
- [ ] Chạy được hai source files (C++ native + Java) và kiểm Java stdout.
- [ ] Không assert exact sample count hoặc coi sum sampled sizes là total bytes.
- [ ] Kiểm tác động throughput/latency/GC trước khi áp interval nhỏ.
- [ ] Có integration test trên JDK 11 runtime nếu sản phẩm nhắm Java 11.

## 12. Tài liệu chuẩn và hiện hành

1. [JVMTI Specification Java 11 — Set Heap Sampling Interval](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html) (Heap Monitoring).
2. [JVMTI Specification Java 11 — Sampled Object Allocation](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html) (event 86, default 512KB).
3. [JVMTI Specification Java 11 — Capabilities và Event Management](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html).
4. [OpenJDK JEP 331 — Low-Overhead Heap Profiling](https://openjdk.org/jeps/331).
5. [JVMTI Specification Java 26 — Set Heap Sampling Interval và SampledObjectAlloc còn được hỗ trợ](https://docs.oracle.com/en/java/javase/26/docs/specs/jvmti.html).
6. [Java SE 11 — JNI Specification](https://docs.oracle.com/en/java/javase/11/docs/specs/jni/index.html).
7. [Java SE 11 Tools — java launcher và -agentpath](https://docs.oracle.com/en/java/javase/11/tools/java.html).
