# Java 11+ — Heap profiling: Lấy mẫu cấp phát qua JVMTI

## 1. Vì sao cần lấy mẫu cấp phát trên Java heap?

Khi một ứng dụng Java dùng nhiều bộ nhớ hoặc tạo áp lực cho Garbage Collector (GC), câu hỏi quan trọng không chỉ là **heap đang giữ bao nhiêu byte**, mà còn là **những vị trí nào liên tục tạo object mới**. Cấp phát rất nhanh dù object sống ngắn có thể làm tăng GC frequency, memory bandwidth và latency; ngược lại một memory leak có thể đến từ một lượng cấp phát không lớn nhưng được giữ lại quá lâu.

**Heap allocation profiling** giúp trả lời:

- Những loại object/array nào thường được tạo?
- Luồng nào tạo nhiều object, và stack nào có khả năng là nguồn cấp phát?
- Các đường code tạo nhiều byte trên một khoảng thời gian là gì?
- Sự thay đổi sau tối ưu có làm giảm **allocation pressure** không?
- Số liệu mẫu có đáng tin ở mức thống kê hay chưa, và liệu tác động của profiler có chấp nhận được không?

Từ **Java 11**, **JEP 331 — Low-Overhead Heap Profiling** đưa cơ chế **lấy mẫu cấp phát object trên Java heap qua JVMTI (JVM Tool Interface)**. Đây là chức năng native dành cho agent/profiler và **vẫn được định nghĩa trong JVMTI của các JDK hiện đại**.

Điểm cần nhớ:

> **JVMTI sampled allocation không đếm mọi object theo mặc định.** Nó tạo các callback dựa trên một khoảng **số byte cấp phát trung bình theo từng thread**. Các sự kiện quan sát được là **mẫu**, không phải bản thống kê toàn bộ heap hay bằng chứng trực tiếp về memory leak.

Bài học đi theo mạch: **đặc tả JVMTI → capability/callback → sampling interval → native agent → Java workload → đọc kết quả có tính thống kê → an toàn và vận hành**. Ví dụ Java được biên dịch và chạy với API Java 11; native agent cần được biên dịch bằng compiler C++ tương ứng với hệ điều hành.

## 2. JVMTI nằm ở đâu trong kiến trúc Java?

**JVMTI** là một giao diện native trong JVM dành cho debugger, profiler và monitoring agent. Khác với một Java library thông thường, JVMTI agent thường là thư viện native (Linux `.so`, Windows `.dll`, macOS `.dylib`) được load **vào chính JVM process**.

```text
                       Java application (JDK 11+)
                 +---------------------------------+
                 | Thread A: new byte[4096]        |
                 | Thread B: new byte[4096]        |
                 |     Allocation / GC / heap      |
                 +------------------+--------------+
                                    |
                              JVM / HotSpot
                                    |
                       JVM TI heap sampling engine
                       per-thread allocation state
                                    |
                  after sampled allocation completes
                                    v
          JVMTI_EVENT_SAMPLED_OBJECT_ALLOC callback
                         native agent .so/.dll
                                    |
                         counters / metadata
                                    |
                         profiling report
```

Agent tải lúc JVM khởi động bằng:

```bash
java -agentpath:/absolute/path/to/libsample_alloc_agent.so AllocationWorkload
```

Đường dẫn chỉ mang tính minh họa cho Linux; trong bài thực hành ở mục 7 có cách build/load tương ứng. **`-agentpath` là lựa chọn dùng native library**, không phải `-javaagent` của Java Instrumentation API. Một file Java `.jar` thông thường không thể đăng ký `SampledObjectAlloc` chỉ bằng việc đặt manifest `Premain-Class`.

JVM TI có những khả năng khác như inspect threads/stacks, theo dõi GC và heap, nhưng bài học này giới hạn ở **allocation sampling**. Không cần và không nên bật mọi event/capability chỉ vì muốn xác định allocation hotspots.

## 3. API cốt lõi của JEP 331

JVMTI Java 11 có các thành phần sau:

| Thành phần | Chức năng | Lưu ý |
| --- | --- | --- |
| `can_generate_sampled_object_alloc_events` | **Optional capability** cho phép sinh sự kiện cấp phát được lấy mẫu. | Agent phải yêu cầu khả năng qua `AddCapabilities`, nên kiểm tra `GetPotentialCapabilities`; một JVM/provider có thể không hỗ trợ. |
| `SetHeapSamplingInterval(jint)` | Đặt **khoảng lấy mẫu trung bình tính theo byte**. | Được gọi ở **OnLoad hoặc live phase**, **không callback-safe**; giá trị âm là lỗi. |
| `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC` | Event type mang số **86** (theo đặc tả). | **Được gửi trong live phase**, phải bật qua `SetEventNotificationMode`. |
| `jvmtiEventCallbacks.SampledObjectAlloc` | Con trỏ callback do native agent cung cấp. | Đăng ký bằng `SetEventCallbacks`. |
| `jvmtiEventSampledObjectAlloc` | Prototype callback nhận thread, object, class và size. | Sự kiện được phát **sau khi allocation được lấy mẫu hoàn tất**. |
| `Agent_OnLoad` | Điểm vào agent khi JVM load native library lúc khởi động. | Lấy `jvmtiEnv`, xin capability, cấu hình callback/sampling và bật event. |
| `Agent_OnUnload` | Hook agent lúc JVM kết thúc/unload. | Có thể xuất báo cáo tổng hợp; không bảo đảm chạy sau crash/forced kill. |

Prototype trong tài liệu JVMTI:

```cpp
void JNICALL SampledObjectAlloc(
    jvmtiEnv* jvmti_env,
    JNIEnv* jni_env,
    jthread thread,
    jobject object,
    jclass object_klass,
    jlong size);
```

Giải thích các tham số:

- `jvmti_env`: môi trường JVMTI của agent để truy vấn JVM theo quy tắc API.
- `jni_env`: môi trường JNI của thread đang callback, **không** dùng `JNIEnv*` của thread khác.
- `thread`: Java thread có allocation được lấy mẫu.
- `object`: tham chiếu JNI local tới object đã được tạo; **không** giữ nguyên `jobject` qua callback mà không hiểu reference lifecycle.
- `object_klass`: tham chiếu JNI local tới lớp của object, phục vụ việc xác định type.
- `size`: kích thước **object được lấy mẫu**, tính bằng byte theo quy tắc `GetObjectSize`. **Không** phải tổng byte đã được cấp phát từ mẫu trước.

Một agent phân tích chuyên sâu có thể gọi `GetStackTrace` để biết đường code đang thực thi, và `GetClassSignature` để định danh class, nhưng các thao tác truy vấn/symbolization trong callback làm tăng overhead. Demo ở mục 6 chủ động chỉ dùng atomic counters, tránh việc mỗi allocation sample lại in log, cấp phát memory hoặc giữ object.

## 4. Cơ chế sampling thực sự vận hành thế nào?

Theo JVMTI Java 11:

- Mặc định, **sampling interval** khoảng **512 KiB = 524.288 byte**.
- Mỗi thread có trạng thái theo dõi lượng byte đã cấp phát từ lần sample trước.
- Bộ lấy mẫu dùng cơ chế **semi-random/pseudo-random** để tránh chệch do một mẫu cấp phát lặp lại có chu kỳ.
- Một event xảy ra **trung bình** sau mỗi khoảng `sampling_interval` byte đã cấp phát trên **thread đó**.
- **Không** có nghĩa cứ mỗi 512 KiB đúng tuyệt đối sẽ có một callback, hoặc mỗi callback đại diện cho một object 512 KiB.
- Việc thay interval cần thời gian để trạng thái sampler áp dụng; các allocation ngay sau lệnh thay cấu hình có thể chưa phản ánh hoàn toàn interval mới.

### 4.1. Chọn interval theo độ chi tiết và chi phí

| Interval | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| `512 * 1024` | Lấy mẫu trung bình mỗi **512 KiB/thread**. | Mốc phù hợp để bắt đầu khi đánh giá; không phải một đảm bảo số event. |
| `1024 * 1024` | Trung bình mỗi **1 MiB/thread**. | Ít callbacks hơn, giảm overhead, nhưng có thể bỏ lỡ allocation hotspots nhỏ. |
| `64 * 1024` | Trung bình mỗi **64 KiB/thread**. | Nhiều mẫu hơn, tăng độ phân giải và chi phí callback. |
| `1024` | Trung bình mỗi **1 KiB/thread**. | Có thể tạo overhead rất cao; không chọn tùy tiện trên production. |
| `0` | Sau khi cấu hình có hiệu lực, yêu cầu event cho **mỗi allocation được hệ thống hỗ trợ**. | Không còn là low-overhead sampling; chỉ dùng khi thật cần, có kiểm soát. |
| Giá trị âm | Không hợp lệ. | `JVMTI_ERROR_ILLEGAL_ARGUMENT`. |

`SetHeapSamplingInterval` không nhận phần trăm, số events/giây, millisecond hoặc số lượng object. **Tham số là byte** và có kiểu `jint`; không truyền giá trị vượt miền integer. Javadoc đặc tả việc gọi khi agent **đã có capability** `can_generate_sampled_object_alloc_events`, nếu không có thể trả `JVMTI_ERROR_MUST_POSSESS_CAPABILITY`.

Ví dụ setting qua native API:

```cpp
// Mã minh họa trong Agent_OnLoad, khi đã có jvmtiEnv* jvmti
// và đã xin capability tương ứng.
jvmtiError err = jvmti->SetHeapSamplingInterval(512 * 1024);
if (err != JVMTI_ERROR_NONE) {
    // Fail closed / báo lỗi của công cụ profiling.
}
```

**Không gọi `SetHeapSamplingInterval` bên trong callback sampling.** Theo đặc tả, hàm này **không callback-safe**. Cấu hình khi khởi động hoặc ở thời điểm điều khiển hợp lệ do agent quản lý.

### 4.2. Sampling không đồng nghĩa “mỗi object thứ N”

Giả sử một thread tạo đều mảng 4 KiB và cấu hình interval 512 KiB. Trực giác “mỗi 128 mảng có một event” chỉ là **xấp xỉ về kỳ vọng** (`512 KiB / 4 KiB = 128`), không phải lịch cố định. Thực tế có overhead object/header/alignment, các allocation khác trong cùng thread, ngẫu nhiên của sampler và chi tiết provider.

Cũng không thể suy ra rằng `sampled_event_count * 512KiB` cho ra chính xác tổng số byte của process. Con số đó có thể là **một ước lượng sơ bộ** trong một mô hình sampling phù hợp, nhưng không phải phép đo chuẩn có thể so sánh tuyệt đối với heap size hay GC metrics.

## 5. Phân biệt sampled allocation với những công cụ heap khác

| Cơ chế | Đang đo gì? | Khi nào phù hợp? |
| --- | --- | --- |
| **JVMTI `SampledObjectAlloc`** | Một số allocation events được **lấy mẫu** theo lượng byte cấp phát; callback có thread/class/object/size. | Tìm nguồn tạo object, allocation pressure, stack hotspots với overhead có kiểm soát. |
| **JVMTI `VMObjectAlloc`** | Một nhóm allocation được VM thực hiện trực tiếp trong những trường hợp theo đặc tả, **không phải mọi `new` bytecode**. | Phân tích allocation do VM trực tiếp tạo; **không thay thế `SampledObjectAlloc`**. |
| **Heap dump** | Snapshot các object và references đang **tồn tại** tại thời điểm dump. | Retained heap, dominator tree, nghi vấn leak; có thể tốn tài nguyên và nhạy cảm. |
| **Live-object/retention profiling** | Theo dõi các object mẫu còn sống sau GC, đôi khi dùng **weak references** và thời gian sống. | Tìm allocation sites có object tồn tại dài, nhưng cần cơ chế riêng ngoài callback cơ bản. |
| **JFR allocation events** | Các loại event cấp phát mà phiên bản JFR/JDK cụ thể hỗ trợ. | Phân tích với công cụ `jfr`/JDK Mission Control; **event type và semantics phụ thuộc JDK**. |
| **GC/heap metrics** | Occupancy, GC count/pause, throughput, committed/reserved memory. | Phân tích hậu quả GC và áp lực heap; không tự chỉ ra stack cấp phát. |
| **CPU profiling** | Sample nơi CPU đang thực thi hoặc các CPU-related metrics. | Tìm code dùng CPU; không đồng nghĩa code đó cấp phát nhiều. |

**Lưu ý Java 11:** không giả định có `jdk.ObjectAllocationSample` trong JFR Java 11 chỉ vì tài liệu của JDK hiện đại đề cập event này. Các JFR allocation event names và cơ chế hỗ trợ thay đổi theo bản JDK. **JVMTI `SampledObjectAlloc` được đặc tả từ Java 11** là trọng tâm của bài, tách biệt với tên các JFR events.

### Vì sao `VMObjectAlloc` không giống `SampledObjectAlloc`?

Theo tài liệu JVMTI, `VMObjectAlloc` chủ yếu liên quan đến allocation được JVM thực hiện trực tiếp; những object tạo bởi `new`/`newarray` trong bytecode thông thường thường **không** được bao phủ bởi event này. `SampledObjectAlloc` được bổ sung nhằm quan sát **các allocation Java heap nói chung**, kể cả những allocation đến từ bytecode, JNI hoặc VM, theo semantics sampling của provider.

Vì thế một agent đăng ký **chỉ `VMObjectAlloc`** rồi thấy rất ít event không thể kết luận rằng code Java ít cấp phát. Chọn event đúng với câu hỏi phân tích.

## 6. Native agent JVMTI mẫu: đếm callbacks mà không giữ object

JVMTI không phải Java SE class API. Muốn nhận `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC` trong chương trình của mình, bạn cần **native agent**. Mã dưới đây dùng **C++11** và header **`jni.h`/`jvmti.h`** từ JDK.

Thiết kế cố ý tối giản:

- Dùng `JVMTI_VERSION_11` khi lấy môi trường.
- Kiểm tra `GetPotentialCapabilities` và yêu cầu `can_generate_sampled_object_alloc_events`.
- Đăng ký `SampledObjectAlloc` callback.
- Đặt sampling interval 512 KiB.
- Bật `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC`.
- Callback chỉ tăng **hai biến `std::atomic`**, không log từng object, không giữ JNI references và không thêm allocation đáng kể.
- Khi unload bình thường, in **số mẫu và tổng size của những object được lấy mẫu**.

**Quan trọng:** native counter này không đo retained heap và **không** ước tính total allocation bytes. Nó chỉ đếm số event callback quan sát được và cộng size **của các sampled objects**.

Lưu thành **`sample_alloc_agent.cpp`**:

```cpp
#include <jni.h>
#include <jvmti.h>

#include <atomic>
#include <cstdio>
#include <cstring>

static std::atomic<unsigned long long> g_samples(0);
static std::atomic<unsigned long long> g_sampled_object_bytes(0);

static void JNICALL on_sample(
        jvmtiEnv* jvmti,
        JNIEnv* jni,
        jthread thread,
        jobject object,
        jclass object_class,
        jlong size) {
    (void) jvmti;
    (void) jni;
    (void) thread;
    (void) object;
    (void) object_class;

    // Only constant-time atomic operations. No logging or JNI object retention.
    g_samples.fetch_add(1, std::memory_order_relaxed);
    if (size > 0) {
        g_sampled_object_bytes.fetch_add(
                static_cast<unsigned long long>(size),
                std::memory_order_relaxed);
    }
}

static jint fail(const char* stage, jint code) {
    std::fprintf(stderr, "JVMTI failed at %s: code=%d\n", stage, code);
    return JNI_ERR;
}

extern "C" JNIEXPORT jint JNICALL Agent_OnLoad(
        JavaVM* vm, char* options, void* reserved) {
    (void) options;
    (void) reserved;

    jvmtiEnv* jvmti = nullptr;
    jint status = vm->GetEnv(
            reinterpret_cast<void**>(&jvmti), JVMTI_VERSION_11);
    if (status != JNI_OK || jvmti == nullptr) {
        return fail("GetEnv", status);
    }

    jvmtiCapabilities available = {};
    jvmtiError err = jvmti->GetPotentialCapabilities(&available);
    if (err != JVMTI_ERROR_NONE) {
        return fail("GetPotentialCapabilities", err);
    }
    if (!available.can_generate_sampled_object_alloc_events) {
        return fail("sampled allocation capability unavailable",
                    JVMTI_ERROR_NOT_AVAILABLE);
    }

    jvmtiCapabilities requested = {};
    requested.can_generate_sampled_object_alloc_events = 1;
    err = jvmti->AddCapabilities(&requested);
    if (err != JVMTI_ERROR_NONE) {
        return fail("AddCapabilities", err);
    }

    jvmtiEventCallbacks callbacks = {};
    callbacks.SampledObjectAlloc = &on_sample;
    err = jvmti->SetEventCallbacks(
            &callbacks, static_cast<jint>(sizeof(callbacks)));
    if (err != JVMTI_ERROR_NONE) {
        return fail("SetEventCallbacks", err);
    }

    err = jvmti->SetHeapSamplingInterval(512 * 1024);
    if (err != JVMTI_ERROR_NONE) {
        return fail("SetHeapSamplingInterval", err);
    }

    err = jvmti->SetEventNotificationMode(
            JVMTI_ENABLE, JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, nullptr);
    if (err != JVMTI_ERROR_NONE) {
        return fail("SetEventNotificationMode", err);
    }

    std::fprintf(stderr, "jvmti-sampling-enabled=true\n");
    return JNI_OK;
}

extern "C" JNIEXPORT void JNICALL Agent_OnUnload(JavaVM* vm) {
    (void) vm;

    std::fprintf(stderr, "sampled-events=%llu\n",
                 g_samples.load(std::memory_order_relaxed));
    std::fprintf(stderr, "sampled-object-size-sum=%llu\n",
                 g_sampled_object_bytes.load(std::memory_order_relaxed));
}
```

### 6.1. Tại sao callback không truy cập `object`?

Hai tham số `object` và `object_class` là **JNI local references** có vòng đời gắn với callback. Không giữ `jobject` trong một native vector toàn cục rồi sử dụng ở thread khác hoặc sau callback — reference có thể không còn hợp lệ. Nếu cần theo dõi tuổi thọ object, profiler chuyên dụng có thể tạo **weak global references** và quản lý chúng đúng cách, giải phóng khi xong. Làm điều đó sai có thể tạo leak **ngay trong profiler** hoặc làm ảnh hưởng vòng đời GC của ứng dụng.

Đối với allocation hotspot đơn giản, việc giữ object là không cần thiết. Callback nên càng nhẹ càng tốt, tránh:

- `printf` mỗi sự kiện, ghi file/JSON hoặc gửi network ngay trên application thread.
- Bật một method/class lookup hoặc stack trace đầy đủ **cho mọi callback** ở interval quá nhỏ.
- Cấp phát object mới, gọi Java code, tạo lock contention hoặc làm việc không reentrant trong callback.
- Dùng biến đếm thường `long long++` từ nhiều threads (có thể data race); ví dụ dùng `std::atomic`.
- Giữ `JNIEnv*` và local `jobject` để dùng về sau ở thread khác.
- Gọi `SetHeapSamplingInterval` từ callback, vì hàm không callback-safe.

**Với profiler production**, thiết kế buffer hữu hạn, batch processing/symbolization off-thread, bounded loss handling và error handling cho thread safety cần được thẩm định riêng. Ví dụ chỉ giữ atomic counters, không phải một sampling profiler đầy đủ có stack aggregation.

### 6.2. Vì sao cần capability và kiểm tra lỗi từng bước?

JVMTI có khái niệm **optional capabilities**. Không phải VM/vendor nào cũng hỗ trợ mọi tính năng. Nếu `can_generate_sampled_object_alloc_events` không có hoặc không thể cấp, agent nên từ chối khởi động chức năng đó và in lý do cụ thể, **không** âm thầm làm như đang profiling.

Thứ tự ở ví dụ:

```text
Agent_OnLoad
  |
  +-- JavaVM.GetEnv(JVMTI_VERSION_11)
  |
  +-- GetPotentialCapabilities
  |
  +-- AddCapabilities(can_generate_sampled_object_alloc_events)
  |
  +-- SetEventCallbacks(SampledObjectAlloc = on_sample)
  |
  +-- SetHeapSamplingInterval(512 * 1024)
  |
  +-- SetEventNotificationMode(ENABLE, SAMPLED_OBJECT_ALLOC)
  |
  +-- JVMTI receives callbacks during live phase
  |
  +-- Agent_OnUnload: print aggregate counters
```

`SetHeapSamplingInterval` phải được gọi ở **OnLoad hoặc live phase**, không trong chính sampling callback. Cấu hình event với `SetEventNotificationMode` không thay thế cho việc xin capability. `GetEnv` cần thành công và agent phải làm việc trên JVM thực sự có JVMTI API đó.

**Phần native cần toolchain ngoài `javac`.** Mã được đối chiếu với prototype trong `jvmti.h`/Oracle JVMTI 11; kết quả biên dịch native phụ thuộc compiler, OS/JDK headers và provider. Phần Java ở mục 7 có kết quả đã chạy kiểm chứng; **không nên xem số callbacks của native agent là kết quả tất định khi chưa chạy agent trên từng nền tảng**.

## 7. Chương trình Java 11 tạo tải cấp phát để kiểm thử agent

Một sampler khó kiểm thử nếu chương trình chỉ tạo vài object. Ví dụ này tạo số lượng object đủ lớn trên **hai thread riêng**, có ring buffer giữ lại một lượng nhỏ object để giảm khả năng JIT tối ưu bỏ hoàn toàn allocation. Phần lớn mảng cũ sẽ trở thành đối tượng có thể GC.

Thiết kế:

- Mỗi worker tạo **20.000 mảng `byte[4096]`**.
- Có **hai worker**, tổng **40.000 vòng cấp phát mảng**, payload **163.840.000 byte**.
- Mỗi worker giữ lại **128 mảng cuối** vào ring và công bố ring qua một **`volatile` reference**.
- Main thread `join` hai workers rồi kiểm tra kết quả giữ lại: **256 mảng**, payload **1.048.576 byte**.
- Các số này là **số vòng lặp và kích thước payload từ mã ứng dụng**, không phải JVMTI sampling count hay size toàn bộ object trên heap.

Lưu **`AllocationWorkload.java`**:

```java
public final class AllocationWorkload {
    private static final int PER_THREAD = 20000;
    private static final int ARRAY_BYTES = 4096;
    private static final int RING_SIZE = 128;
    private static volatile Object sinkA;
    private static volatile Object sinkB;

    private static byte[][] allocate() {
        byte[][] ring = new byte[RING_SIZE][];
        for (int i = 0; i < PER_THREAD; i++) {
            byte[] bytes = new byte[ARRAY_BYTES];
            bytes[0] = (byte) i;
            ring[i % RING_SIZE] = bytes;
        }
        return ring;
    }

    public static void main(String[] args) throws InterruptedException {
        Thread a = new Thread(() -> sinkA = allocate(), "allocation-A");
        Thread b = new Thread(() -> sinkB = allocate(), "allocation-B");
        a.start();
        b.start();
        a.join();
        b.join();

        byte[][] retainedA = (byte[][]) sinkA;
        byte[][] retainedB = (byte[][]) sinkB;
        int retained = 0;
        long retainedPayload = 0;
        for (byte[] data : retainedA) {
            if (data != null) {
                retained++;
                retainedPayload += data.length;
            }
        }
        for (byte[] data : retainedB) {
            if (data != null) {
                retained++;
                retainedPayload += data.length;
            }
        }

        System.out.println("workers=2");
        System.out.println("allocation-loops=" + (2 * PER_THREAD));
        System.out.println("payload-bytes=" + (2L * PER_THREAD * ARRAY_BYTES));
        System.out.println("retained-arrays=" + retained);
        System.out.println("retained-payload-bytes=" + retainedPayload);
    }
}
```

### 7.1. Biên dịch và chạy Java không cần native agent

Đặt file trên vào một thư mục test riêng và sử dụng **JDK 11 hoặc mới hơn**:

```bash
javac -encoding UTF-8 --release 11 AllocationWorkload.java
java -Xmx96m AllocationWorkload
```

**Stdout chính xác đã được kiểm chứng:**

```text
workers=2
allocation-loops=40000
payload-bytes=163840000
retained-arrays=256
retained-payload-bytes=1048576
```

Giải thích:

- `workers=2`: code tạo hai Java threads thực hiện cùng workload cấp phát.
- `allocation-loops=40000`: hai threads × 20.000 vòng. Đây không phải số callbacks sampling.
- `payload-bytes=163840000`: tổng `40000 × 4096` **byte dữ liệu mảng** được yêu cầu, chưa cộng object headers/alignment, ring arrays, thread/runtime allocations.
- `retained-arrays=256`: mỗi worker trả một ring gồm 128 phần tử có mảng không null.
- `retained-payload-bytes=1048576`: `256 × 4096` byte dữ liệu của các mảng hiện còn được giữ qua ring. Nó **không** phải toàn bộ retained heap size của process.

**Không khóa cứng `sampled-events` vào số ví dụ trong stdout.** Sampler pseudo-random, JVM/provider/JIT, khoảng thời gian khởi động, allocation từ thư viện và các thread hệ thống có thể làm tổng callback thay đổi giữa các lần chạy.

### 7.2. Build native agent trên Linux

Cần compiler C++ hỗ trợ C++11 và các development headers từ JDK:

```bash
# Giả sử JAVA_HOME trỏ đến đúng JDK và đang ở thư mục chứa hai source.
g++ -std=c++11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  sample_alloc_agent.cpp -o libsample_alloc_agent.so

javac -encoding UTF-8 --release 11 AllocationWorkload.java
java -Xmx96m \
  -agentpath:"$(pwd)/libsample_alloc_agent.so" \
  AllocationWorkload
```

Thứ tự command-line options JVM hợp lệ: `-Xmx` và `-agentpath` phải đứng **trước** tên class Java.

### 7.3. Build native agent trên Windows

Với **Visual Studio Developer Command Prompt** có MSVC C++ compiler và JDK headers:

```bat
cl /std:c++17 /EHsc /O2 /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" sample_alloc_agent.cpp /link /OUT:sample_alloc_agent.dll
javac -encoding UTF-8 --release 11 AllocationWorkload.java
java -Xmx96m "-agentpath:C:\absolute\path\sample_alloc_agent.dll" AllocationWorkload
```

Thay đường dẫn agent bằng **đường dẫn tuyệt đối** trong máy. Trên PowerShell, bảo đảm nguyên đối số `-agentpath:...` được quote nếu đường dẫn có khoảng trắng. Native binary của Windows và Linux khác nhau; **không** tải `.so` lên Windows hoặc `.dll` lên Linux. C++ build có thể cần cấu hình target architecture phù hợp (ví dụ x64 agent cho x64 JVM).

**Lệnh build native ở đây là hướng dẫn phụ thuộc toolchain.** Nếu không có `g++`/MSVC và headers, chỉ chạy được chương trình Java ở mục 7.1, **chưa thể tuyên bố callback JVMTI đã được thực thi**. Không đánh đồng việc `javac` thành công với việc native agent đã build hoặc load thành công.

### 7.4. Khi agent chạy thành công, output nên được hiểu ra sao?

Với native agent mẫu, có thể thấy một số dòng loại:

```text
jvmti-sampling-enabled=true
...
sampled-events=<số sự kiện thực sự nhận được>
sampled-object-size-sum=<tổng size của những object được lấy mẫu>
```

Các dấu `<...>` trong khối trên là **mô tả dạng output**, **không phải stdout thử nghiệm hay giá trị kỳ vọng**. Agent ghi vào **stderr**, ứng dụng Java ghi năm dòng ổn định ở **stdout**. Số callback/size sẽ phụ thuộc sampling thực tế và không được bịa thành một số cụ thể trước khi chạy.

- `jvmti-sampling-enabled=true`: `GetEnv`, capability, đăng ký callback, interval và enable event đều trả status thành công trong `Agent_OnLoad`.
- `sampled-events`: số lần callback `SampledObjectAlloc` thực sự được gọi trong vòng đời JVM; có thể có mẫu của những threads/allocations khác workload.
- `sampled-object-size-sum`: tổng **`size` của đúng các objects được chọn mẫu**, thường **nhỏ hơn nhiều** so với tổng byte đã cấp phát của toàn JVM. Không thể dùng một phép chia/nhân đơn giản để tự động suy ra retained heap.
- `Agent_OnUnload` có thể không chạy nếu JVM bị kill đột ngột, crash hoặc agent không nạp thành công; thiếu summary sau crash **không** nói sampling đã không xảy ra.

Khi kiểm thử native thật, nên capture stdout/stderr riêng, kiểm tra exit code, số lượng samples qua nhiều lần lặp và so sánh distribution với workload. Một test “`sampled-events` phải bằng chính xác 312” là không phù hợp với sampling thống kê.

## 8. Lấy thông tin allocation site và stack trace

Agent mẫu ở mục 6 chỉ **đếm**; để làm profiler hữu ích cần phân nhóm theo **class, thread, stack**. `SampledObjectAlloc` callback có sẵn `object_klass`, `thread` và `size`. Nếu cần call stack, JVM TI có **`GetStackTrace`**, nhưng phải thiết kế chi phí cẩn thận.

Ý tưởng:

```text
SampledObjectAlloc(thread, object_class, size)
       |
       +-- Nhận diện class (GetClassSignature nếu cần)
       |
       +-- Lấy stack (GetStackTrace với giới hạn số frame)
       |
       +-- Chuẩn hóa method/frame IDs
       |
       +-- Ghi record rút gọn vào bounded buffer
       |
       v
Worker/symbolizer phân tích ngoài callback
       |
       v
Nhóm theo allocation site/thread/class
       |
       v
Biểu đồ allocation hotspots + khoảng tin cậy
```

Một snippet gọi API để minh họa hướng triển khai, **không độc lập**:

```cpp
// Trong callback có jvmtiEnv* jvmti và jthread thread hợp lệ.
jvmtiFrameInfo frames[16];
jint frame_count = 0;
jvmtiError err = jvmti->GetStackTrace(
        thread, 0, 16, frames, &frame_count);
// Xử lý err; tránh symbolization/logging đắt ngay trong callback.
```

Lưu ý:

- Stack có thể bị thiếu hoặc ngắn, phụ thuộc allocation path, inlining và provider. Không coi stack trace là ảnh chụp hoàn chỉnh mọi frame nguồn Java.
- `GetClassSignature` trả string được JVMTI cấp phát; nếu gọi, phải dùng **`Deallocate`** theo hợp đồng API, không `free` như con trỏ C thuần.
- Không giữ `JNIEnv*` hoặc local `jobject` để dùng trong background thread.
- Symbolization `jmethodID`, giải tên lớp/phương thức và xuất JSON/log có chi phí; cân nhắc batch và buffer hữu hạn.
- Stack có thể chứa đường code xử lý dữ liệu nhạy cảm. Profiler production phải kiểm soát truy cập và retention.
- Những API thao tác với JNI trong callback có thể ảnh hưởng pending exception của application thread; xem JVMTI **Handling Events** và bảo toàn exception state theo đặc tả.
- Nếu cần **object lifetime/retained heap**, phải thêm thiết kế weak references/GC tracking; callback allocation đơn lẻ không cung cấp bằng chứng object còn sống bao lâu.

## 9. Diễn giải mẫu: callback count không phải allocation count

Giả sử ta thấy một phiên profiler có `N` sampled callbacks. Cần phân biệt **các đại lượng**:

| Chỉ số | Ý nghĩa | Độ tin cậy |
| --- | --- | --- |
| `allocation-loops` từ workload Java | Số vòng mà chương trình thử nghiệm đã thực thi. | Tất định đối với code demo; không đại diện toàn JVM. |
| `payload-bytes` | Tổng độ dài **nội dung byte[]** mà code yêu cầu. | Tất định; chưa cộng object overhead và các object khác. |
| `sampled-events` | Số event do JVMTI sampler gửi cho agent. | Thống kê, phụ thuộc interval/JVM/runtime. |
| `sampled-object-size-sum` | Tổng `size` của các object được chọn làm mẫu. | **Không** là tổng allocation bytes toàn process. |
| `sampling_interval` | Trung bình số byte cấp phát giữa các mẫu trên **mỗi thread**. | Mục tiêu thống kê, **không** phải khoảng chính xác. |
| `heap-used-after-GC` | Memory của các object còn được giữ theo GC/heap metric. | Khác với allocation volume. |
| `retained heap` từ heap dump | Object graph đang giữ memory. | Cần heap/GC analysis, không có sẵn từ số sample callbacks. |

### Đừng dùng mẫu sai để “chứng minh leak”

Ví dụ một vòng lặp tạo hàng triệu `byte[]` rồi **không giữ reference** có thể gây **allocation rate cao** và nhiều GC, nhưng không nhất thiết gây retained heap leak. Ngược lại, một cache/collection tăng chậm nhưng giữ objects mãi có thể gây leak dù allocation samples không quá nhiều.

Một kế hoạch phân tích thực tế:

1. Xác nhận JVM/agent có hỗ trợ sampling và event đã được bật.
2. Ghi lại interval, thời gian đo, throughput, heap/GC settings và JVM vendor/version.
3. Thu mẫu đủ lâu và đủ workload; tránh suy luận từ vài sample hiếm.
4. Nhóm theo class/stack/thread, xem **distribution** và sự ổn định giữa nhiều lần thử.
5. Đối chiếu GC pause, allocation rate counters, heap occupancy và business traffic.
6. Nếu nghi leak, điều tra retained objects/paths với heap dump hoặc live-object profiling có kiểm soát.
7. Đánh giá overhead của chính agent; lấy baseline không profiler và profile với interval khác.
8. Báo các giới hạn statistical uncertainty, sampling bias và những event không được thu.

### Ước lượng tổng lượng cấp phát cần làm đúng mô hình

Một công cụ profiling có thể dùng thuật toán và trọng số thống kê để ước lượng allocation pressure từ mẫu. Nhưng không được tự lấy `sum(sample.size)` rồi coi đó là total bytes, hoặc nhân mỗi `sample.size` với `sampling_interval` mà không có cơ sở xác suất; việc này dễ cho đơn vị và bias sai.

Nếu dùng **sample count × mean interval** như ước lượng thô cho toàn bộ traffic đã quan sát trong điều kiện ổn định, hãy ghi rõ đó chỉ là **xấp xỉ** (và phụ thuộc số threads, giai đoạn khởi động, các allocation bị tối ưu, sampler/provider). Đối với báo cáo có yêu cầu độ chính xác, dùng estimator của công cụ được thẩm định và đối chiếu với các counters độc lập.

## 10. Tối ưu overhead và tính reentrant của callback

Callback JVMTI thường được gửi trên **application thread**, không có queue tự động do JVMTI quản lý. Vì thế chi phí callback sẽ cộng vào công việc đang chạy và có thể thay đổi behavior/timing của ứng dụng.

| Hành động trong callback | Tác động tiềm ẩn | Khuyến nghị |
| --- | --- | --- |
| Tăng atomic counter | Chi phí tương đối nhỏ. | Chấp nhận cho demo; nhiều threads tranh chấp vẫn có cache contention. |
| `fprintf` mỗi mẫu | I/O và lock ở C runtime, có thể rất đắt. | Không in mỗi event ở production. |
| Lấy full stack nhiều frames | Stack walking và profiling overhead. | Giới hạn depth; đo trên workload thực. |
| Giải tên class/method mỗi mẫu | Allocation/symbol resolution, callback dài. | Cache có kiểm soát hoặc xử lý ngoài callback. |
| Lưu global strong JNI refs tới objects | Giữ object sống, biến dạng GC/heap. | Tránh; dùng weak refs nếu thiết kế retention profiler thật. |
| Buffer không giới hạn | Tốn RAM, tự tạo pressure trong profiler. | Dùng bounded queue/ring, xử lý loss/overflow rõ. |
| Lock một mutex toàn cục mỗi mẫu | Contention khi nhiều allocation threads. | Chọn cấu trúc thread-local hoặc sharded counters khi cần. |
| Thay interval bên trong callback | Vi phạm yêu cầu callback safety của API. | Đặt interval tại thời điểm hợp lệ ngoài callback. |

**Một profiler quá nặng có thể làm thay đổi chính hệ thống nó đang đo.** Vì thế mục tiêu của JEP 331 là sampling đủ tốt với overhead thấp *khi cấu hình hợp lý*, không phải bảo đảm overhead luôn không đáng kể ở mọi interval/callback implementation.

Nếu tính năng bị hai agent/profiler cấu hình đồng thời, behavior và interval có thể bị ảnh hưởng theo JVM/vendor; không chạy nhiều allocation profilers song song rồi mặc định chúng đo độc lập. Kiểm tra khả năng phối hợp và tác động của mỗi agent trong test.

## 11. Vòng đời của native agent và JVM phases

**`Agent_OnLoad`:** callback lúc load library bằng `-agentpath` ở JVM startup. Đây là nơi phù hợp để:

- Gọi `GetEnv` để lấy `jvmtiEnv*`.
- Kiểm tra `GetPotentialCapabilities` và `AddCapabilities`.
- Đăng ký `SetEventCallbacks`.
- Đặt `SetHeapSamplingInterval`.
- Bật `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC` trước workload.

**Live phase:** event `SampledObjectAlloc` chỉ được gửi trong live phase; agent có thể nhận callbacks đồng thời khi nhiều Java threads cấp phát. Runtime cụ thể có thể cho phép live attachment, nhưng **không** giả định mọi VM luôn cho attach hoặc cấp thêm optional capabilities bất cứ lúc nào.

**`Agent_OnUnload`:** có thể in/tổng hợp cuối kỳ, nhưng không dựa vào hook này làm giải pháp bắt buộc để flush dữ liệu quan trọng nếu process có nguy cơ crash/kill. Profiler sản phẩm cần cơ chế snapshot/flush độc lập và lifecycle management chuẩn.

**Dừng event:** công cụ có thể gọi `SetEventNotificationMode(JVMTI_DISABLE, JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, nullptr)` ở pha hợp lệ khi muốn tắt sampling. Đừng shutdown bộ nhớ callback/buffer khi vẫn có callback đang chạy; thiết kế synchronization và quiescence phải rõ trong agent đa luồng.

## 12. Các lỗi dễ gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Xử lý |
| --- | --- | --- |
| JVM không load native agent | Sai `-agentpath`, DLL/so không phù hợp OS/architecture, thiếu dependency hoặc export symbol sai. | Dùng **đường dẫn tuyệt đối**, build đúng x64/x86, kiểm tra runtime loader. |
| `GetEnv` thất bại | JVMTI version không có hoặc VM không hỗ trợ. | Dựa vào JDK/vendor, không ép code chạy tiếp với pointer null. |
| Capability không khả dụng | `can_generate_sampled_object_alloc_events` là optional. | Kiểm tra `GetPotentialCapabilities` và fail clearly. |
| `SetHeapSamplingInterval` trả `MUST_POSSESS_CAPABILITY` | Chưa `AddCapabilities` thành công. | Xin capability trước, kiểm tra mọi return code. |
| Interval âm trả `ILLEGAL_ARGUMENT` | Truyền số byte < 0. | Validate configuration trước khi gọi. |
| Có agent nhưng `sampled-events=0` | Event chưa bật, interval quá lớn, workload ngắn, sampler chưa áp dụng setting, provider/attach hạn chế, allocation tối ưu. | Kiểm tra activation path và workload đủ lớn, không kết luận “không cấp phát”. |
| Callback quá nhiều/latency cao | Interval quá nhỏ, callback làm việc nặng hoặc in log mọi mẫu. | Tăng interval, tối ưu callback, đo overhead. |
| Agent hỏng khi giữ `jobject` | JNI local reference được dùng sai vòng đời/thread. | Không giữ local ref, quản lý weak/global ref đúng nếu cần. |
| Agent tạo ra heap leak | Profiler giữ strong refs/buffer không giới hạn. | Giới hạn state và giải phóng references/buffers. |
| Có samples nhưng không thấy stack | Agent chỉ đếm, không gọi `GetStackTrace`; hoặc provider/stack depth hạn chế. | Thiết kế capture stack riêng, đo chi phí; không suy diễn từ count. |
| `sampled-object-size-sum` khác payload bytes | Đây là hai đại lượng khác nhau, một bên là **mẫu**, một bên là tổng payload của code. | Không so sánh bằng phép bằng tuyệt đối. |
| Heap dump nhỏ nhưng sampling nhiều | Object sống ngắn được GC thu hồi. | Phân biệt allocation pressure và retained heap. |
| Bản chạy khác ra sample count khác | Sampling giả ngẫu nhiên theo thread và runtime khác. | Thống kê nhiều lượt, nêu interval/workload, dùng confidence range nếu phù hợp. |
| Agent mới làm thay đổi performance | Có profiling overhead/lock/I/O trong callback. | Chạy baseline, A/B test và đánh giá mức overhead. |

### Những exception/error không nên “bỏ qua rồi tiếp tục”

Nếu JVM TI trả `JVMTI_ERROR_MUST_POSSESS_CAPABILITY` hoặc `JVMTI_ERROR_NOT_AVAILABLE`, đừng in một báo cáo có số sample=0 và mô tả là “đã quan sát ứng dụng không cấp phát”. Đó là lỗi **agent chưa được cấp quyền hoặc tính năng không khả dụng**. Công cụ phải phân biệt **profiling disabled/failed** với **profiling enabled nhưng không thu được sự kiện nào**.

## 13. Bảo mật và quyền kiểm soát trong profiling

Native JVMTI agent chạy **bên trong process** và có quyền quan sát sâu vào JVM. Vì vậy:

1. **Chỉ load agent tin cậy** đã được thẩm định, tương ứng đúng runtime/version.
2. Bảo vệ quyền ghi vào thư viện `.so`/`.dll` và thư mục chứa nó; không để người không được phép thay thế agent.
3. Không tự bật agent lên JVM người khác khi chưa có quyền; profiling có thể ảnh hưởng hiệu năng và tiết lộ dữ liệu.
4. Allocation class signatures, stack traces, thread names và custom metadata có thể tiết lộ tên nghiệp vụ, đường dẫn, endpoint và thông tin cá nhân.
5. Tránh log object contents/secret keys; một allocation profiler đa số không cần đọc plaintext của object để tìm hotspots.
6. Có **quota, retention và access controls** cho logs, raw samples và symbolization database.
7. Không để profiler trở thành nguồn gây OOM do buffer không giới hạn hoặc giữ strong references.
8. Đo và giới hạn overhead trong test/staging trước khi bật ở production.
9. Với ứng dụng nhạy cảm, phối hợp đội security/observability trước khi bật attach hoặc native agent.
10. Nếu có nhiều profiler/agent, đánh giá khả năng can thiệp về sampling interval và tốc độ callback.

**Lưu ý:** `JVMTI` là API native có khả năng control/inspect VM, không phải sandbox bảo mật. Tải một agent không đáng tin sẽ mở đường cho can thiệp tiến trình, dù thuật toán sampling tự thân không đọc nội dung object.

## 14. Test strategy cho JVMTI allocation sampling

Bộ test tốt cần tách **functional API test**, **statistical behavior test** và **performance impact test**:

| Nhóm test | Điều cần kiểm tra | Không nên assert |
| --- | --- | --- |
| Agent startup | `Agent_OnLoad` được gọi, `GetEnv`/`AddCapabilities`/`SetEventCallbacks`/`SetEventNotificationMode` trả success. | Không suy luận từ việc JVM chạy Java main mà bỏ qua stderr agent. |
| Java workload | Chạy `AllocationWorkload`, 2 threads tạo 40.000 mảng 4 KiB, output tất định. | Không coi số vòng là số JVMTI samples. |
| Event callback | Sau workload đủ dài, sample count có thể >0 khi feature hoạt động. | **Không** chốt một con số sample cố định cho mọi lần chạy. |
| Interval comparison | So sánh 64 KiB, 512 KiB, 1 MiB trong workload đủ lớn/lặp nhiều lần. | Không kỳ vọng số events tỷ lệ nghịch chính xác ở từng lượt ngắn. |
| Disabled event | Tắt notification và kiểm tra không phát thêm callback trong phạm vi test đúng. | Không quên concurrency/quiescence khi tắt event. |
| Invalid interval | `SetHeapSamplingInterval(-1)` trả lỗi thích hợp. | Không cho phép giá trị âm hoặc wrap overflow từ config text. |
| Missing capability | Một VM không hỗ trợ/agent không xin được thì fail clearly. | Không báo “heap có 0 allocation”. |
| Class/thread grouping | Nếu capture thêm metadata, aggregation không giữ refs vô hạn. | Không giữ `jobject` JNI local sau callback. |
| Stack capture | Kiểm tra stack symbolization và overhead với depth cố định. | Không giả định mọi sample có full Java stack. |
| Memory behavior | Agent không tạo retained heap tăng liên tục do buffers/references. | Không dựa riêng vào sample count để phát hiện leak. |
| Overhead | Baseline vs with agent cùng workload/heap/JDK. | Không dùng một benchmark duy nhất để chứng minh overhead bằng 0. |
| Portability | Build .so/.dll cho đúng JDK11+ headers/CPU/OS. | Không chạy binary của hệ điều hành/architecture khác. |

Một test lặp tốt là chạy **workload nhiều lần**, thu số callbacks mỗi lần và tính phân phối trung bình/khoảng biến thiên; sau đó tăng interval và xem xu hướng giảm callback/overhead. Nếu kết quả trái kỳ vọng, kiểm tra điều kiện khởi động, kích thước workload, warmup JIT, GC, sampler settings và các agents khác.

## 15. Sai lầm phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “JVMTI là thư viện Java gọi bằng `import`.” | JVMTI là native VM Tool Interface, cần agent/tool phù hợp. |
| “Chạy `javac` là đã build native JVMTI agent.” | Không; cần compiler C/C++ và JDK native headers. |
| “`SampledObjectAlloc` có mặt từ mọi JDK cổ.” | JVMTI sampled allocation được bổ sung **từ Java 11** theo JEP 331. |
| “`SampledObjectAlloc` chỉ bắt object do native VM tạo.” | Không: nó được thiết kế quan sát allocation Java heap theo sampling; `VMObjectAlloc` có phạm vi khác. |
| “Bật event mà không xin capability vẫn được.” | Không: phải được cấp `can_generate_sampled_object_alloc_events`. |
| “Interval = số object mỗi mẫu.” | Sai: interval tính bằng **byte cấp phát trung bình trên từng thread**. |
| “Mỗi 512KiB chính xác một callback.” | Sai: pseudo-random sampling, chỉ đúng trung bình dài hạn. |
| “Interval 0 vẫn là low overhead mặc định.” | Không: yêu cầu event cho mọi allocation được hỗ trợ sau khi áp dụng, overhead cao. |
| “`size` callback là số byte kể từ mẫu trước.” | Không: đó là **kích thước object được chọn mẫu**. |
| “Tổng size của các sampled objects là tổng heap allocated.” | Không: sampled subset, không phải total. |
| “Sample count bằng số `new`/`newarray` thực thi.” | Không: count phụ thuộc sampler, GC/JIT và runtime. |
| “Allocation hotspot chính là memory leak.” | Không: phải xem retained objects/lifetime/GC. |
| “Có `jobject` trong callback thì giữ lại mãi để phân tích.” | Nguy hiểm: JNI local reference có vòng đời giới hạn; strong refs có thể gây leak. |
| “In stack và object mỗi sample là miễn phí.” | Không: overhead profiler có thể làm sai lệch workload. |
| “Có thể đổi interval bất cứ lúc nào kể cả bên trong callback.” | Không: `SetHeapSamplingInterval` không callback-safe. |
| “Mọi JVM hỗ trợ JVMTI đều cấp được capability này.” | Không: optional capability, phụ thuộc implementation. |
| “JFR event mới nào cũng có trong Java 11.” | Không: phân biệt version JFR và JVMTI event đã có từ 11. |
| “Từ 0 callback kết luận ứng dụng không có cấp phát.” | Không: cần xác minh agent bật đúng, interval và duration. |
| “Heap dump thay được allocation profile.” | Không: heap dump phản ánh retained heap tại thời điểm chụp. |
| “Mã native chưa chạy mà in số sample ước lượng là kiểm thử thành công.” | Không: chỉ in output thực đo; số sample phải đến từ VM thật. |

## 16. Checklist áp dụng Java 11+

1. Xác định **allocation pressure** hay **retained heap leak** là mục tiêu đo.
2. Chọn **JVMTI `SampledObjectAlloc`** khi muốn sampled allocation sites; không nhầm với `VMObjectAlloc`.
3. Kiểm tra `GetEnv(JVMTI_VERSION_11)` và optional capability `can_generate_sampled_object_alloc_events`.
4. Đăng ký `SetEventCallbacks`, cấu hình interval bằng byte và bật `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC`.
5. Bắt đầu với interval có overhead phù hợp (ví dụ 512 KiB), không tự bật 0 trong production.
6. Dùng callback nhẹ, thread-safe, reentrant; hạn chế stack walking/symbolization/logging trực tiếp.
7. Không giữ JNI local object refs sau callback, tránh profiler tự làm thay đổi GC hoặc gây memory leak.
8. Ghi rõ interval, duration, JVM/JDK/vendor, threads, workload và quyền profiling.
9. Không coi raw `size` sum hoặc callback count là total allocation/retained heap.
10. Khi cần ước lượng thống kê, dùng estimator có căn cứ và test lặp với đủ mẫu.
11. Phân biệt allocation profile, JFR events, GC metrics và heap dump; phối hợp nếu cần root cause.
12. Biên dịch Java workload bằng `javac --release 11` và native agent bằng compiler C++ tương ứng.
13. Kiểm tra source native, headers, callback signature và agent load trên target OS/JDK; không claim kết quả native chưa chạy.
14. Bảo vệ binary agent và output profile; giới hạn quyền, dữ liệu nhạy cảm, storage và overhead.
15. Chỉ dùng các API JVMTI có trong **Java 11 và JDK hiện đại**, không dựa vào cờ/công cụ lỗi thời hoặc JFR event không có trên target JDK.

### Tài liệu tham khảo chính thức

- [OpenJDK JEP 331 — Low-Overhead Heap Profiling (Java 11)](https://openjdk.org/jeps/331)
- [Oracle Java SE 11 — JVM Tool Interface, Heap Monitoring / SetHeapSamplingInterval và Sampled Object Allocation](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html)
- [Oracle Java SE 25 — JVM Tool Interface, cùng các API sampling hiện đại](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html)
- [Oracle Java SE 11 — JVM TI architecture, writing agents, callbacks và native library loading](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html#writing-agents)
- [Oracle Java SE 11 — JFR API là một công cụ quan sát khác, không đồng nghĩa JVMTI event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/module-summary.html)
