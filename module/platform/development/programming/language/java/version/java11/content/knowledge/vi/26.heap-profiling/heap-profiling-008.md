# Heap profiling — Quản lý vòng đời agent, callback và dữ liệu mẫu (Java 11)

## 1. Bài toán cần giải quyết

Heap profiling giúp trả lời: **đối tượng nào đang được cấp phát, từ thread/stack nào, với kích thước bao nhiêu và liệu hoạt động đó có gây áp lực lên GC hoặc hiệu năng hay không?** Trên Java 11, **JEP 331 — Low-Overhead Heap Profiling** bổ sung cơ chế **sampled allocations** qua **JVM Tool Interface (JVMTI)**, cho phép một *native agent* đăng ký nhận callback khi JVM chọn một allocation làm mẫu.

Điểm trọng tâm của bài này không chỉ là “bật profiler”, mà là quản lý **toàn bộ vòng đời**:

1. **Agent được nạp:** JVM tìm native library, gọi `Agent_OnLoad` lúc startup hoặc `Agent_OnAttach` nếu có hỗ trợ attach vào JVM đang chạy.
2. **Agent yêu cầu capability:** `can_generate_sampled_object_alloc_events` là tính năng **tùy chọn**, không thể mặc định mọi JVM đều hỗ trợ.
3. **Đăng ký callback:** cấu hình `jvmtiEventCallbacks.SampledObjectAlloc` bằng `SetEventCallbacks`.
4. **Thiết lập mức lấy mẫu:** `SetHeapSamplingInterval` quyết định ngân sách trung bình bằng **byte allocated theo thread**, không phải “mỗi N object”.
5. **Bật event:** `SetEventNotificationMode(JVMTI_ENABLE, JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, nullptr)`.
6. **Tiếp nhận dữ liệu:** callback nhận `thread`, `object`, `object_klass` và `size`; xử lý ngắn, an toàn với GC và thread.
7. **Lưu/tổng hợp mẫu có giới hạn:** tránh giữ object mạnh vô hạn, tránh log mỗi allocation, tránh queue không giới hạn.
8. **Dừng và kết thúc:** disable event khi còn ở phase hợp lệ, chờ xử lý callback đang diễn ra khi cần, xuất thống kê có kiểm soát và giải phóng tài nguyên ở `VMDeath`/`Agent_OnUnload`.

Các nguyên lý trên **còn áp dụng trên JDK hiện đại**, không dựa trên API Java đã legacy. JVMTI là interface native của JVM, khác `java.lang.instrument` Java agent; JFR cũng cung cấp các công cụ theo dõi allocation ở mức cao hơn nhưng **không đồng nhất** với JVMTI callback được trình bày ở bài này.

**Sau bài học**, bạn sẽ hiểu entry points của agent, lifecycle/capability/event callback, cách diễn giải sample có xác suất, giới hạn quyền sở hữu JNI references, mô hình buffer/aggregation, shutdown an toàn, kiểm thử/benchmark và sự khác nhau giữa histogram sample với live-heap dump.

## 2. JVM TI, native agent và các thành phần

**JVM Tool Interface (JVMTI)** là C/C++ interface dành cho profiler, debugger và công cụ quan sát JVM. Native agent chạy **trong cùng tiến trình** với ứng dụng Java, thông qua một dynamic library (`.so` trên Linux, `.dylib` trên macOS, `.dll` trên Windows). Nó có thể nhận event mà không yêu cầu sửa source của ứng dụng.

| Thành phần | Vai trò | Vòng đời |
| --- | --- | --- |
| `JavaVM*` | Handle của Java VM, dùng `GetEnv` lấy môi trường JVMTI | Do JVM quản lý |
| `jvmtiEnv*` | Môi trường của **một agent**, giữ capabilities/callbacks/event settings | Từ lúc lấy thành công đến khi không còn hợp lệ |
| `JNIEnv*` | Giao diện JNI **gắn với thread callback hiện tại** | Không chia sẻ tùy tiện sang thread khác |
| `jvmtiCapabilities` | Các quyền agent xin JVM cấp | Xin trước khi dùng event tùy chọn |
| `jvmtiEventCallbacks` | Bảng hàm callback do agent đăng ký | JVM sao chép khi `SetEventCallbacks` thành công |
| `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC` | Event nhận khi chọn allocation làm mẫu | Chỉ phát ở JVM **live phase** |
| `SetHeapSamplingInterval` | Cấu hình khoảng lấy mẫu trung bình | Gọi ở `OnLoad` hoặc live phase |
| `Agent_OnLoad/OnAttach` | Entry points khởi tạo agent | Khởi động/attach theo cơ chế hỗ trợ |
| `VMDeath/Agent_OnUnload` | Tín hiệu JVM kết thúc / thư viện sắp unload | Không bảo đảm chạy khi process bị kill cưỡng bức |

**Đặc điểm quan trọng:** nhiều JVMTI agents có thể tồn tại cùng JVM, mỗi agent có môi trường và callbacks riêng, nhưng chúng **cùng ảnh hưởng đến JVM và chia sẻ môi trường native**. Không suy rằng mọi profiler chạy đồng thời sẽ hoàn toàn độc lập về overhead, khả năng lấy mẫu hoặc trạng thái JVM.

### 2.1. Không nhầm các cơ chế theo dõi bộ nhớ

| Công cụ/cơ chế | Theo dõi gì? | Ranh giới |
| --- | --- | --- |
| JVMTI `SampledObjectAlloc` | **Mẫu các lần cấp phát object** trong lúc chương trình chạy | Không phải full census hay retained heap |
| JVMTI `VMObjectAlloc` | Những allocation do VM thực hiện thuộc phạm vi event đó | **Không** thay thế sampled event cho tất cả bytecode allocations |
| JVMTI `ObjectFree` / object tagging | Một số sự kiện về object được GC thu hồi khi dùng capability thích hợp | Cần thiết kế tags/liveness, không tự có từ `SampledObjectAlloc` |
| JFR allocation events | Sự kiện allocation theo cơ chế JFR/JDK | API/cấu hình khác với callback JVMTI |
| Heap dump/histogram | Snapshot các object còn hiện diện tại một thời điểm | Có thể tốn thời gian/dung lượng, không cho lịch sử allocation đầy đủ |
| `MemoryMXBean`/GC metrics | Thống kê heap used/committed/GC | Không chỉ trực tiếp allocation call sites |

**Sampled allocation ≠ memory leak.** Số mẫu allocation cao có thể do một vòng lặp tạo object tạm rồi GC dọn sạch. Memory leak đòi hỏi phân tích **retention**, đồ thị references, tăng live heap sau GC hoặc các dấu hiệu phù hợp qua thời gian.

## 3. Luồng vòng đời tổng thể

```text
java -agentpath:/path/to/native-agent.so ...
              |
              v
         Agent_OnLoad
              |
          JavaVM.GetEnv
              |
      GetPotentialCapabilities
              |
         AddCapabilities
              |
        SetEventCallbacks
              |
      SetHeapSamplingInterval
              |
     SetEventNotificationMode
              |
       JVM live (application)
              |
  SampledObjectAlloc callback(s)
     (nhiều thread, nhiều lần)
              |
   atomic counters / bounded buffer
              |
        JVM shutdown
              |
      VMDeath (nếu xảy ra)
              |
       Agent_OnUnload
              |
          release state
```

Với **dynamic attach**, entry point là `Agent_OnAttach` thay cho `Agent_OnLoad` khi runtime/attach mechanism hỗ trợ; agent bắt đầu quan sát **từ lúc được attach**, không tự khôi phục allocation đã xảy ra trước đó.

Các phase từ JVMTI:

- **OnLoad:** trong lúc `Agent_OnLoad` đang chạy; nhiều thao tác JNI/JVMTI chưa hợp lệ, nhưng yêu cầu capabilities và đăng ký callbacks được cho phép.
- **Primordial/start:** JVM chưa vào fully live; callback sampled allocation chỉ được phát khi JVM ở **live**.
- **Live:** ứng dụng chạy; sampled events có thể được phát, có thể bật/tắt event, đổi sampling interval theo quy định.
- **Dead:** sau VM death hoặc startup failure; không gọi các hàm JVMTI đòi live phase.

**Không** lưu `JNIEnv*` từ callback rồi sử dụng trên một thread exporter. Mỗi thread có JNI environment riêng; nếu cần worker native tương tác JVM, nó phải attach đúng cách và tuân thủ phase/permission, nhưng nên giữ callback path càng độc lập JVM càng tốt.

## 4. Khởi tạo agent: `Agent_OnLoad` và `Agent_OnAttach`

Các chữ ký tiêu chuẩn cho dynamic native agent:

```cpp
extern "C" JNIEXPORT jint JNICALL Agent_OnLoad(
        JavaVM* vm, char* options, void* reserved);

extern "C" JNIEXPORT jint JNICALL Agent_OnAttach(
        JavaVM* vm, char* options, void* reserved);

extern "C" JNIEXPORT void JNICALL Agent_OnUnload(JavaVM* vm);
```

- `extern "C"` cần khi viết bằng C++ để xuất symbol không bị name mangling.
- `JNIEXPORT`/`JNICALL` dùng convention phù hợp nền tảng/JNI.
- `options` là chuỗi ký tự được cung cấp bởi `-agentpath`/`-agentlib` hoặc lệnh attach; **có vòng đời giới hạn trong chính lời gọi entry point**. Muốn dùng về sau phải **copy nội dung** đã validate vào cấu trúc sở hữu bởi agent.
- `reserved` không dùng; không dereference.
- `Agent_OnLoad` trả **0** khi thành công, khác 0 khiến JVM startup **thất bại** theo đặc tả.
- `Agent_OnAttach` trả khác 0 báo attach thất bại; thông thường JVM đang chạy không bị kết thúc chỉ vì attach lỗi, nhưng cách báo lỗi tùy runtime.
- `Agent_OnUnload` là hook cleanup khi thư viện sắp bị dỡ; **không** mặc định có callback khi hệ điều hành kill process đột ngột.

**Nhớ lựa chọn bảo mật:** một native agent có khả năng chạy code trong tiến trình ứng dụng. Chỉ nạp thư viện đáng tin, được kiểm soát version, xuất xứ và quyền hệ điều hành. Việc cho phép attach tùy runtime, quyền OS/container và chính sách vận hành; **không** coi attach là quyền mặc định mà mọi tài khoản đều có.

### 4.1. Lấy `jvmtiEnv*` đúng cách

```cpp
jvmtiEnv* ti = nullptr;
if (vm->GetEnv(reinterpret_cast<void**>(&ti),
               JVMTI_VERSION_1_2) != JNI_OK || ti == nullptr) {
    return JNI_ERR;
}
```

Đây là **trích đoạn** bên trong hàm init, cần các header JNI/JVMTI. `JVMTI_VERSION_1_2` là version identifier thích hợp trong `jvmti.h` JDK 11; không dùng `JNI_VERSION_1_8` để xin một JVMTI environment, vì đó là API khác. Sampled allocation event được bổ sung từ JVMTI version triển khai cùng Java 11; capability vẫn phải được kiểm tra.

Khi sử dụng nhiều JVMTI environments/agents, không lấy pointer từ một agent rồi gắn callback của agent khác tùy ý.

## 5. Capability: điều kiện trước khi đăng ký event

`SampledObjectAlloc` là **optional capability**. Phải kiểm tra JVM hiện tại có thể cấp:

```cpp
jvmtiCapabilities potential{};
if (ti->GetPotentialCapabilities(&potential)
        != JVMTI_ERROR_NONE) {
    return JNI_ERR;
}
if (!potential.can_generate_sampled_object_alloc_events) {
    return JNI_ERR; // Runtime không cung cấp capability.
}

jvmtiCapabilities requested{};
requested.can_generate_sampled_object_alloc_events = 1;
if (ti->AddCapabilities(&requested)
        != JVMTI_ERROR_NONE) {
    return JNI_ERR;
}
```

Đây là **trích đoạn** của phương thức init. Lỗi `JVMTI_ERROR_MUST_POSSESS_CAPABILITY` là dấu hiệu agent đang gọi event/sampling function mà chưa có capability tương ứng.

Lý do **không xin tất cả capabilities**: nhiều quyền debugging/profiling có thể làm JVM thay đổi đường tối ưu hóa hoặc tăng overhead, và một số quyền có thể xung đột giữa agents. Theo nguyên tắc đặc quyền tối thiểu, yêu cầu đúng capability cần dùng.

Nếu service cho phép profiler không hoạt động mà ứng dụng vẫn chạy, production có thể chọn **graceful degrade** với thông báo rõ thay vì fail startup. Bài demo dùng fail-fast để tránh báo “đang lấy mẫu” trong khi sampling chưa được bật.

## 6. Callback `SampledObjectAlloc`: chữ ký và semantics

Đặc tả JVMTI Java 11:

```cpp
void JNICALL on_sample(
    jvmtiEnv* jvmti_env,
    JNIEnv* jni_env,
    jthread thread,
    jobject object,
    jclass object_klass,
    jlong size);
```

Callback chỉ được gọi khi một allocation được **chọn làm mẫu**, không phải mọi lần cấp phát nếu interval dương. Tham số:

| Tham số | Ý nghĩa | Quy tắc sử dụng |
| --- | --- | --- |
| `jvmti_env` | Môi trường đang phát event | Không dùng ngoài phase/lifecycle hợp lệ |
| `jni_env` | JNI của thread callback hiện tại | Không giữ để dùng từ thread khác |
| `thread` | Thread tạo object | Reference JNI chỉ dùng trong phạm vi hợp lệ |
| `object` | Object mới được cấp phát, được truyền dưới dạng **JNI local reference** | Không lưu trực tiếp pointer cho xử lý sau callback |
| `object_klass` | Java class của object, cũng là JNI local reference | Không giữ qua callback nếu chưa tạo reference phù hợp |
| `size` | Kích thước object được cấp phát, bằng **byte** | Là kích thước **object được chọn mẫu**, không phải tổng heap |

Event được phát trong **live phase**. Trong callback, tránh làm những việc có thể cấp phát Java object hoặc kích hoạt thêm callback sampling. Các khuyến nghị cốt lõi từ JVMTI spec:

- Callback được gọi đồng bộ trong luồng thực thi event và JVM **không tự queue** lại cho agent.
- Callback phải **re-entrant**, vì có thể được gọi đồng thời trên nhiều application threads.
- Một JNI call trong callback có thể gây Java exception và **ghi đè pending exception** của ứng dụng nếu không xử lý đúng.
- Một callback chậm có thể kéo dài đường cấp phát object của thread ứng dụng; overhead không chỉ nằm ở profiler thread.
- Thông tin về object/thread/class trong callback không có nghĩa reference sẽ sống mãi sau callback.
- Không suy rằng lần nào callback cũng có stack trace đã resolve sẵn; nếu muốn stack, phải thu thập có chọn lọc, với overhead và điều kiện JVMTI riêng.

**Đừng nhầm với `JVMTI_EVENT_VM_OBJECT_ALLOC`:** event đó có ý nghĩa khác về những object do VM cấp phát; mục tiêu của JEP 331 là sampled object allocations khi chương trình chạy, bao gồm những allocation mà bạn muốn quan sát bằng phương pháp thống kê.

## 7. Cấu hình sampling interval: con số byte, không phải số object

`SetHeapSamplingInterval(jint sampling_interval)` có từ Java 11. Theo JVMTI spec:

- Mỗi thread duy trì bộ đếm **byte được cấp phát**.
- Một sampled event phát ra theo một cơ chế **bán ngẫu nhiên**, có trung bình khoảng `sampling_interval` byte allocated **trên mỗi thread** giữa các mẫu.
- **Mặc định là 512 KiB** trên JVM triển khai quy định này.
- `sampling_interval=1024*1024` là một giá trị thử nghiệm **1 MiB**, thường ít callback hơn so với 1 KiB.
- `sampling_interval=0` yêu cầu sự kiện gần như mỗi allocation được hệ thống hỗ trợ sau khi cấu hình có hiệu lực; **chi phí rất lớn**, không nên dùng mặc định ở production.
- Đổi interval **không có tác dụng đồng bộ tức thì** với mọi thread; cần có thêm các allocations để trạng thái nội bộ được cập nhật.
- Tham số âm không hợp lệ, có thể trả `JVMTI_ERROR_ILLEGAL_ARGUMENT`.

```cpp
const jint interval_bytes = 1024 * 1024; // 1 MiB
jvmtiError err = ti->SetHeapSamplingInterval(interval_bytes);
if (err != JVMTI_ERROR_NONE) {
    return JNI_ERR;
}
```

Đây là **trích đoạn init** với `jvmtiEnv* ti`. Tùy provider, sampling support không thể bảo đảm trên tất cả JVM; phải check capability và error code trước khi tuyên bố đã bật.

### 7.1. Sample count không chính xác bằng total allocation count

Giả sử Java code tạo 4.096 mảng `byte[8192]`. Phần payload được yêu cầu về mặt Java là:

```text
4096 * 8192 = 33,554,432 bytes
```

Nhưng agent **không** nên báo:

```text
sample_count = 4096
sampled_object_bytes = 33,554,432
```

vì điều đó **không phải cam kết** của sampling. Ngoài phân bổ của test còn có VM/JDK allocations, array header/alignment và JIT optimizations; số mẫu khác nhau theo run, threads, GC, interval và workload.

Kể cả `sampled_object_bytes` là tổng `size` của những object được chọn, đó **không phải tổng byte allocated của toàn JVM**. Muốn ước lượng allocation rate hoặc histogram có trọng số phải dùng **phương pháp thống kê phù hợp cơ chế sampling**, đánh giá bias và confidence; không coi `count*interval` là con số tuyệt đối không sai số.

## 8. Ví dụ native agent C++: lifecycle, callback và atomic counters

Ví dụ này cố ý **không lưu jobject, không gọi JNI bên trong hot callback, không tạo queue không giới hạn và không log mỗi sample**. Nó giúp thấy rõ các bước bắt buộc trên JVMTI Java 11.

File **`heap_sample_agent.cpp`**:

```cpp
#include <jni.h>
#include <jvmti.h>
#include <atomic>
#include <cstdio>

static std::atomic<unsigned long long> g_samples{0};
static std::atomic<unsigned long long> g_sampled_bytes{0};
static std::atomic<bool> g_enabled{false};
static std::atomic<bool> g_started{false};
static std::atomic<bool> g_reported{false};

static void report_once() {
    if (!g_started.load(std::memory_order_acquire)) {
        return;
    }
    if (g_reported.exchange(true, std::memory_order_acq_rel)) {
        return;
    }
    std::fprintf(
        stderr,
        "[heap-agent] samples=%llu sampled_object_bytes=%llu\n",
        g_samples.load(std::memory_order_relaxed),
        g_sampled_bytes.load(std::memory_order_relaxed));
}

static void JNICALL on_sample(
        jvmtiEnv*,
        JNIEnv*,
        jthread,
        jobject,
        jclass,
        jlong size) {
    if (!g_enabled.load(std::memory_order_acquire)) {
        return;
    }
    g_samples.fetch_add(1, std::memory_order_relaxed);
    if (size > 0) {
        g_sampled_bytes.fetch_add(
            static_cast<unsigned long long>(size),
            std::memory_order_relaxed);
    }
}

static void JNICALL on_vm_death(jvmtiEnv*, JNIEnv*) {
    // JVM không phát event sau VMDeath; tổng hợp một lần.
    g_enabled.store(false, std::memory_order_release);
    report_once();
}

static jint configure(JavaVM* vm) {
    if (g_started.load(std::memory_order_acquire)) {
        return JNI_ERR; // Demo chỉ hỗ trợ một lần init.
    }

    jvmtiEnv* ti = nullptr;
    if (vm->GetEnv(reinterpret_cast<void**>(&ti),
                   JVMTI_VERSION_1_2) != JNI_OK ||
        ti == nullptr) {
        return JNI_ERR;
    }

    jvmtiCapabilities potential{};
    if (ti->GetPotentialCapabilities(&potential)
            != JVMTI_ERROR_NONE ||
        !potential.can_generate_sampled_object_alloc_events) {
        return JNI_ERR;
    }

    jvmtiCapabilities requested{};
    requested.can_generate_sampled_object_alloc_events = 1;
    if (ti->AddCapabilities(&requested)
            != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }

    jvmtiEventCallbacks callbacks{};
    callbacks.SampledObjectAlloc = &on_sample;
    callbacks.VMDeath = &on_vm_death;
    if (ti->SetEventCallbacks(
            &callbacks, sizeof(callbacks)) != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }

    const jint interval_bytes = 1024 * 1024; // 1 MiB.
    if (ti->SetHeapSamplingInterval(interval_bytes)
            != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }

    g_started.store(true, std::memory_order_release);
    g_enabled.store(true, std::memory_order_release);

    if (ti->SetEventNotificationMode(
            JVMTI_ENABLE,
            JVMTI_EVENT_SAMPLED_OBJECT_ALLOC,
            nullptr) != JVMTI_ERROR_NONE) {
        g_enabled.store(false, std::memory_order_release);
        g_started.store(false, std::memory_order_release);
        return JNI_ERR;
    }

    if (ti->SetEventNotificationMode(
            JVMTI_ENABLE,
            JVMTI_EVENT_VM_DEATH,
            nullptr) != JVMTI_ERROR_NONE) {
        (void) ti->SetEventNotificationMode(
            JVMTI_DISABLE,
            JVMTI_EVENT_SAMPLED_OBJECT_ALLOC,
            nullptr);
        g_enabled.store(false, std::memory_order_release);
        g_started.store(false, std::memory_order_release);
        return JNI_ERR;
    }
    return JNI_OK;
}

extern "C" JNIEXPORT jint JNICALL Agent_OnLoad(
        JavaVM* vm, char*, void*) {
    return configure(vm);
}

extern "C" JNIEXPORT jint JNICALL Agent_OnAttach(
        JavaVM* vm, char*, void*) {
    return configure(vm);
}

extern "C" JNIEXPORT void JNICALL Agent_OnUnload(JavaVM*) {
    g_enabled.store(false, std::memory_order_release);
    report_once();
}
```

### 8.1. Những gì code này bảo đảm — và không bảo đảm

**Có trong ví dụ:**

- Sử dụng `JVMTI_VERSION_1_2`, hằng `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC`, `JVMTI_EVENT_VM_DEATH` và field `can_generate_sampled_object_alloc_events` đúng theo header JDK.
- Kiểm tra capability và lỗi trả về từ từng bước quan trọng.
- Đăng ký bảng callback và bật event theo lifecycle hợp lệ.
- Chỉ dùng **atomic increments/loads** trong callback nóng, tránh cấp phát native/Java memory ở mỗi mẫu.
- Dùng `std::atomic` để nhiều application threads ghi count/byte mà không xảy ra data race với các biến thống kê.
- In kết quả ở shutdown qua `VMDeath` hoặc `Agent_OnUnload`, dùng cờ để tránh in hai lần.

**Không phải profiler production hoàn chỉnh:**

- Chưa có cơ chế pause/resume từ control plane, sampling interval tùy chỉnh, bounded ring buffer, per-class histogram hoặc stack capture.
- Chưa ghi metrics ra endpoint khi service chạy liên tục; chỉ in khi có shutdown có kiểm soát.
- Chưa có cơ chế đợi mọi callback in-flight sau khi chuyển trạng thái disable. Trong demo, các counters là **static storage tồn tại tới khi process kết thúc**, không bị `free()` trong callback, nên tránh được một lớp use-after-free; khi xây agent phức tạp với heap-allocated buffers cần synchronization/drain mạnh hơn.
- `g_samples` và `g_sampled_bytes` là counters tăng theo tuổi process, có thể overflow nếu dùng vô hạn trong một chương trình dài ngày; production dùng epoch/snapshot/reset hoặc kế hoạch chống overflow phù hợp.
- `SetHeapSamplingInterval` có thể ảnh hưởng hành vi sampling tổng thể, và nhiều profiler/agent có thể tương tác với JVMTI implementation; thử nghiệm đồng thời nhiều agents.
- Chưa bắt lỗi và phân loại chi tiết `jvmtiError`/JNI/OS; production nên dùng mã lỗi rõ, lấy tên lỗi bằng JVMTI API trong **đường control** có phase thích hợp (không trong hot callback).
- `Agent_OnUnload` có thể không được chạy khi process bị kill mạnh; không coi dòng tổng kết là durable audit.

**Độ tin cậy biên dịch:** phần chữ ký/hằng JVMTI trong đoạn C++ đã được đối chiếu với `jvmti.h` của một JDK hiện đại và đặc tả JVM TI 11. Tuy nhiên mã native này **cần được build và chạy trên compiler + JDK + OS đích** trước khi sử dụng; kết quả chạy callback không được tuyên bố có output số lượng cố định.

### 8.2. Vì sao dùng `std::atomic`?

Callback có thể được gọi **đồng thời** từ nhiều application threads. `++ordinary_global_count` trên biến toàn cục không đồng bộ sẽ gây **data race trong C++**, dẫn đến undefined behavior và số liệu sai.

`fetch_add(..., std::memory_order_relaxed)` là đủ cho **đếm độc lập** khi không dùng counter làm cơ chế publish dữ liệu khác. `g_enabled` dùng load/store acquire-release cho trạng thái. Đừng dùng atomic counters như một lời bảo đảm snapshot nhiều field tuyệt đối nhất quán: nếu đọc hai counters lúc vẫn có callback, chúng có thể phản ánh hai thời điểm rất gần nhưng khác nhau. Với thống kê cần snapshot đồng nhất, dùng epoch, buffered handoff hoặc quiescence theo thiết kế.

### 8.3. Vì sao không `printf` trong `on_sample`?

`fprintf` vào stderr/file khi callback xảy ra thường xuyên có thể:

- Giữ lock của I/O library và gây contention.
- Thay đổi phân bố thời gian cấp phát của ứng dụng.
- Bão hòa disk hoặc log pipeline.
- Tạo overhead lớn hơn chính thao tác đang đo.
- Làm các thống kê profiler bị méo do **observer effect**.

Nguyên tắc: callback chỉ **ghi số liệu tối thiểu vào cấu trúc đã cấp phát trước**, bộ phận exporter/control phía ngoài callback gom dữ liệu theo chu kỳ. Nếu ring buffer đầy, phải có chính sách **drop và tăng dropped counter**, không block application allocation thread vô hạn.

## 9. Biên dịch native agent và nạp bằng `-agentpath`

Cần **JDK headers** `jni.h`/`jvmti.h` và native compiler cho đúng kiến trúc OS/JVM. Đây là các **lệnh mẫu trên máy build thực**, thay đổi path và compiler theo môi trường. Bản demo native chưa được biên dịch trong môi trường không có C++ compiler; hãy xem output compiler/ABI khi triển khai.

### 9.1. Linux + GCC/Clang C++

```bash
g++ -std=c++11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libheapsample.so heap_sample_agent.cpp

javac --release 11 -encoding UTF-8 HeapSamplingWorkload.java
java -agentpath:"$(pwd)/libheapsample.so" HeapSamplingWorkload
```

Nếu project dùng package/classpath, thêm `-cp` đúng. `JAVA_HOME` phải trỏ tới **JDK**, không phải JRE/custom image thiếu header; compiler architecture phải khớp JVM architecture.

### 9.2. macOS

```bash
c++ -std=c++11 -O2 -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libheapsample.dylib heap_sample_agent.cpp

javac --release 11 -encoding UTF-8 HeapSamplingWorkload.java
java -agentpath:"$(pwd)/libheapsample.dylib" HeapSamplingWorkload
```

Cần compiler/toolchain và kiến trúc tương ứng; macOS ARM64 và x86_64 libraries không được đổi lẫn.

### 9.3. Windows MSVC (Developer Command Prompt)

```bat
cl /nologo /EHsc /std:c++14 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  heap_sample_agent.cpp /Fe:heapsample.dll

javac --release 11 -encoding UTF-8 HeapSamplingWorkload.java
java -agentpath:C:\agents\heapsample.dll HeapSamplingWorkload
```

Đây là **lệnh mẫu**, bạn phải đặt `heapsample.dll` đúng đường dẫn hoặc sửa `-agentpath` theo nơi đã build. Nếu DLL dùng thư viện runtime phụ thuộc, môi trường JVM cần tìm được chúng. Lệnh `cl` chạy trong **Developer Command Prompt**, không phải PowerShell trống chưa có MSVC environment. Đừng ghi đè một DLL agent đang được JVM sử dụng trong production.

### 9.4. Phân biệt `-agentpath`, `-agentlib`, `-javaagent`

| Cách nạp | Dành cho | Entry point |
| --- | --- | --- |
| `-agentpath:/absolute/path/library.so` | Native JVMTI agent theo path cụ thể | `Agent_OnLoad` |
| `-agentlib:heapsample` | Native agent theo tên library và library search path | `Agent_OnLoad` |
| `-javaagent:/path/agent.jar` | Java Instrumentation agent | `premain`, **không** phải `Agent_OnLoad` |
| Dynamic native attach | Chỉ khi runtime/permission hỗ trợ | `Agent_OnAttach` |

Không thể thay `-agentpath` bằng `-javaagent` chỉ vì cả hai đều gọi là “agent”. Hai API có vòng đời và quyền khác nhau.

## 10. Chương trình tải Java 11 có stdout xác định

Để quan sát sampling, cần tạo đủ allocations và tránh bị tối ưu hóa hoàn toàn. Tạo file **`HeapSamplingWorkload.java`**:

```java
public final class HeapSamplingWorkload {
    private static volatile byte[] last;

    public static void main(String[] args) {
        final int allocations = 4096;
        final int payloadBytes = 8192;

        for (int i = 0; i < allocations; i++) {
            byte[] bytes = new byte[payloadBytes];
            bytes[0] = (byte) i;
            last = bytes;
        }

        System.out.println("requested_arrays=" + allocations);
        System.out.println("requested_payload_bytes="
                + ((long) allocations * payloadBytes));
        System.out.println("last_array_length=" + last.length);
    }
}
```

Biên dịch/chạy **không có agent** trước:

```bash
javac --release 11 -encoding UTF-8 HeapSamplingWorkload.java
java HeapSamplingWorkload
```

**Stdout xác định của Java workload** — đã biên dịch với `--release 11` và chạy kiểm chứng:

```text
requested_arrays=4096
requested_payload_bytes=33554432
last_array_length=8192
```

Khi chạy thêm native agent như mục 9, chương trình Java vẫn in ba dòng trên nếu thành công; native agent có thể in thêm ở **stderr**:

```text
[heap-agent] samples=<giá trị thay đổi> sampled_object_bytes=<giá trị thay đổi>
```

Dòng thứ hai là **minh họa định dạng**, không phải stdout cố định: hai giá trị có thể khác mỗi lần chạy và chỉ xuất hiện khi agent khởi tạo, JVM hỗ trợ sampling và shutdown hook được gọi. Thứ tự stdout/stderr sau khi được terminal gom lại **không bảo đảm**.

### 10.1. Vì sao `volatile last`?

Gán mảng vừa tạo vào một trường `volatile` khiến việc cấp phát/mutation có hiệu ứng quan sát được; điều này giúp demo tránh bị tối ưu hóa toàn bộ allocations theo những cách đơn giản. Tuy vậy, JIT/GC/runtime vẫn có quyền tối ưu các chi tiết phù hợp Java Memory Model; **không** diễn giải số byte payload được yêu cầu là phép đo tổng allocation của JVM.

### 10.2. Phân biệt các loại kích thước

| Con số | Ý nghĩa | Có bằng total allocated heap không? |
| --- | --- | --- |
| `4096` | Số lần loop tạo mảng trong Java source | Không đếm JVM/JDK allocations khác |
| `8192` | Độ dài payload mảng `byte[]` | Không gồm array header/alignment |
| `33,554,432` | Tổng payload byte được yêu cầu | **Không**, thiếu overhead và runtime |
| Callback `size` | Kích thước của **object được chọn mẫu** | Không phải kích thước mọi object |
| `g_sampled_bytes` | Tổng `size` của các **sampled objects** | **Không phải** tổng bytes allocated |
| Heap used sau GC | Dung lượng object đang còn sống + khác biệt JVM | Không phải tổng cumulative allocations |

Đừng đặt assertion `samples == 32` chỉ vì workload tạo payload khoảng 32 MiB với interval 1 MiB. Sampling là ngẫu nhiên và có trạng thái theo thread, còn runtime tạo object khác ngoài code demo.

## 11. Chủ sở hữu dữ liệu mẫu: JNI local refs, weak refs và lifetime

Một mẫu có `object` và `object_klass` là JNI references, không phải hai “con trỏ heap ổn định” để giữ mãi:

- **JNI local reference** từ callback chỉ hợp lệ trong phạm vi JNI/local frame tương ứng. Không lưu raw `jobject`/`jclass` vào queue cho worker thread đọc sau.
- **Strong global reference** (`NewGlobalRef`) có thể giữ object sống, thay đổi chính heap/liveness mà profiler đang đo và làm tăng memory pressure; không nên tự động tạo một strong ref cho mọi sampled allocation.
- **Weak global reference** (`NewWeakGlobalRef`) là lựa chọn có thể dùng trong thiết kế theo dõi lifetime, nhưng vẫn có chi phí/giới hạn số reference, cần `DeleteWeakGlobalRef` khi không cần; muốn dereference phải kiểm tra object còn sống theo JNI semantics.
- Một object được chọn làm mẫu có thể **đã chết ở thời điểm bạn phân tích**, dù vẫn có dữ liệu allocation type/size được tổng hợp.
- `GetObjectSize` hoặc thông tin `size` liên quan kích thước object tại thời điểm đo, không suy ra “bao nhiêu bytes mà object đó đang giữ qua toàn bộ object graph”.

### 11.1. Một cấu trúc record an toàn hơn raw object references

Một record mẫu tối thiểu, chỉ giá trị thuần:

```cpp
struct SampleRecord {
    unsigned long long sequence;
    unsigned long long sampled_size_bytes;
    unsigned long long monotonic_time_ns;
    unsigned int class_id;
    unsigned int thread_id;
};
```

Đây là **schema minh họa** của hệ thống có bước ánh xạ ID do profiler quản lý; JVMTI **không tự cung cấp** các trường `sequence`, `monotonic_time_ns`, `class_id`, `thread_id` qua một callback duy nhất. Bạn phải tự gán và làm rõ nguồn của timestamp/ID. **Không copy raw JNI local refs** vào `class_id` hoặc `thread_id` bằng cast rồi dùng lâu dài.

Với bài demo cơ bản, giữ **atomic count** và **sum(sampled sizes)** là đủ minh họa vòng đời. Nếu cần histogram theo class, bạn phải trích xuất/định danh class hợp lệ theo JVMTI/JNI và xây cấu trúc bounded; không coi `jclass` local reference là ID bền vững.

### 11.2. Thu stack trace có chi phí riêng

JVMTI có `GetStackTrace` để khảo sát frames. Làm điều đó tại mỗi sampled callback có thể tăng chi phí mạnh:

- Có thể cần truy vấn frames, resolve tên phương thức/class, xử lý class unloading.
- Có thể chạm locks/metadata hoặc tạo bộ nhớ native.
- Dữ liệu stack có thể tiết lộ package/method/logic nội bộ.
- Callback diễn ra trên **application thread** nên việc xử lý nặng ảnh hưởng latency.

Nếu thật sự cần allocation call sites, chọn interval phù hợp, lấy số frame có giới hạn, giải phóng strings theo API JVMTI `Deallocate`, kiểm soát lỗi/phase/exception và đo overhead. Bài tập hiện tại không tự ghi stack trace ở callback để tránh đánh đồng một ví dụ tối thiểu với profiler thương mại.

## 12. Callback đồng thời, re-entrancy và tránh tạo feedback loop

Một thiết kế sai thường gặp:

```cpp
// Anti-pattern minh họa: không dùng trong hot callback.
static std::vector<jobject> all_objects;
void bad_callback(jobject object) {
    all_objects.push_back(object);
    std::printf("new object = %p\n", object);
}
```

Đoạn **không hoàn chỉnh** còn có những lỗi:

- `std::vector` phình vô hạn và `push_back` có thể cấp phát lại native memory, giữ lock nếu bảo vệ bằng mutex.
- `jobject` từ callback là local ref, không thể sử dụng lâu dài trong vector.
- Hàm không xử lý concurrency nên có data race.
- `printf` cho từng sample rất tốn I/O và có thể gây lock contention.
- Hiểu nhầm tất cả mẫu đều có lifetime dài dẫn tới việc tạo strong global refs, vô tình giữ sống object.

**Mô hình chuẩn hơn:**

```text
SampledObjectAlloc callback (app thread)
  |
  +-- read size / cheap counters
  +-- optionally enqueue bounded, preallocated scalar record
           |
           +-- success: exporter worker periodically aggregates
           |
           +-- full: increment dropped counter, return quickly

Exporter/control thread
  |
  +-- snapshot counts / histogram
  +-- rate-limited export
  +-- apply retention and privacy policy
```

Nếu chọn lock-free ring buffer, yêu cầu tính đúng memory ordering, ownership slots, backpressure và stop/drain; không đơn giản lấy `volatile` trong C++ để thay atomic. Nếu queue nhiều producer một consumer, chọn cấu trúc MPSC đã được test; **không** tự tuyên bố một `std::vector` với mutex là “zero overhead”.

### 12.1. Error handling trong callback

Theo JVMTI spec, callback thường chạy trong context thread ứng dụng; JNI calls có thể để lại hoặc thay pending Java exception. Vì thế:

1. Đường nóng nên tránh JNI calls không thật cần thiết.
2. Nếu phải dùng JNI, kiểm tra `ExceptionCheck` và bảo toàn trạng thái lỗi theo chiến lược đã xác minh; không tự nuốt exception nghiệp vụ.
3. Không throw C++ exception xuyên qua ranh giới callback `JNICALL`.
4. Không tạo Java object/logging callback rồi dẫn đến allocation recursion.
5. Không block dài chờ filesystem/network.
6. Có counters cho `errors`/`drops`; đường ghi lỗi phải nhẹ và rate-limited.
7. Các native allocations/strings trả về từ JVMTI API cần `Deallocate` đúng nơi và đúng phase, tránh native leaks.

## 13. Tạm dừng và shutdown: phân biệt bốn thao tác

Có ít nhất bốn hành động khác nhau:

| Thao tác | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `JVMTI_DISABLE` event | Dừng gửi `SampledObjectAlloc` mới cho environment theo thiết lập | Pause profiling / shutdown có kiểm soát |
| `SetEventCallbacks` đổi callback table | Thay/remove callback functions | Thay handler, cleanup khi phase cho phép |
| `VMDeath` callback | JVM thông báo sắp kết thúc live lifecycle | Flush/snapshot nhẹ và đánh dấu kết thúc |
| `Agent_OnUnload` | JVM dỡ thư viện agent | Dọn tài nguyên native ở thời điểm phù hợp |

### 13.1. Tắt event khi vẫn ở live phase

Trong control function được gọi hợp lệ khi JVM còn live:

```cpp
jvmtiError error = ti->SetEventNotificationMode(
    JVMTI_DISABLE,
    JVMTI_EVENT_SAMPLED_OBJECT_ALLOC,
    nullptr);
if (error != JVMTI_ERROR_NONE) {
    // Báo lỗi có kiểm soát trong control plane.
}
```

Đây là **trích đoạn**, cần `jvmtiEnv* ti` còn hợp lệ và phase cho phép. **Không gọi tùy tiện ở `Agent_OnUnload` khi JVM có thể đã dead.** Event đã disable không có nghĩa mọi callback chạy đồng thời chắc chắn đã hoàn tất ở đúng thời điểm dòng gọi trả về; với state có thể bị `free`, hãy thiết kế cơ chế quiescence/drain riêng.

Ví dụ mã sản phẩm nên có state machine:

```text
CREATED -> CONFIGURED -> RUNNING -> STOPPING -> STOPPED
                              |
                              +-> FAILED (và cleanup an toàn)
```

**Không** đặt trạng thái STOPPED trước khi hoàn tất yêu cầu disable, xử lý lỗi và drain theo hợp đồng. Việc thay interval hoặc cấu hình mới có thể được thực hiện trong RUNNING nhưng cần phân chia epoch và ghi log **metadata** an toàn để biết thời điểm chính sách thay đổi.

### 13.2. Thứ tự shutdown gợi ý

1. Ngừng nhận lệnh start mới.
2. Thử chuyển sang `STOPPING` và disable sampled event **khi còn live**.
3. Không cho callback mới chạm state sắp giải phóng; bảo đảm những callback đang thực thi đã xong hoặc state vẫn tồn tại.
4. Snapshot counts/buffer với synchronization thích hợp.
5. Flush chỉ số ở exporter riêng, với timeout và quyền truy cập đã định.
6. Dọn JNI weak/global refs, JVMTI-allocated memory, locks/buffers nếu đã sử dụng, đúng cơ chế của chúng.
7. Đánh dấu `STOPPED`, không dùng `jvmtiEnv*`/`JNIEnv*` đã hết hiệu lực.

Với JVM process shutdown do ứng dụng kết thúc, `VMDeath` xảy ra **trước** `Agent_OnUnload` trong trường hợp bình thường có callback VMDeath; nhưng chúng không phải hai lời gọi được bảo đảm trong mọi failure mode. **Không dựa vào shutdown hook cho dữ liệu phải bền vững tuyệt đối.**

### 13.3. Vì sao ví dụ chỉ in ở VMDeath/OnUnload?

Đây là demo ngắn. Counter không bị hủy trước khi callback kết thúc, nên việc in tổng kết ở cuối minh họa vòng đời đơn giản. Khi service chạy nhiều ngày, báo cáo chỉ lúc shutdown không đủ. Product profiler cần **periodic export**, snapshots theo epoch, health metrics và retention hạn chế, nhưng vẫn phải tránh heavy work ở hot callback.

## 14. Dữ liệu mẫu nào nên giữ, dữ liệu nào phải giới hạn?

| Trường | Giá trị chẩn đoán | Chi phí/rủi ro |
| --- | --- | --- |
| `size` byte của sample | Hỗ trợ histogram kích thước | Đơn giản, phù hợp aggregate |
| Allocation class | Nhận diện class cấp phát nhiều | Resolve tên class có overhead, metadata cần cache |
| Thread identifier | Biết thread phát allocation | Thread name có thể chứa dữ liệu nội bộ; không dùng làm request ID |
| Stack trace | Tìm allocation call sites | Tốn chi phí và có thể tiết lộ code nội bộ |
| Timestamp/epoch | So với metric/GC timeline | Cần clock/format chính xác, chưa có sẵn như tham số callback |
| Weak reference/liveness | Khảo sát sampled object có còn sống không | Reference management phức tạp, có overhead |
| Full object graph/payload | Thường không cần để đo allocation rate | Rủi ro PII/secrets và ảnh hưởng heap lớn |

**Không tự lưu payload/nội dung object chỉ vì callback có `jobject`.** Heap có thể chứa password, access token, thông tin người dùng, request body, encryption key. Profiler nên tổng hợp metadata kỹ thuật theo một allowlist và có retention/quyền truy cập phù hợp.

### 14.1. Giới hạn bộ nhớ cho sample buffer

Nếu profiler muốn ghi 100.000 mẫu/giây và mỗi record 64 byte, chỉ dữ liệu thô đã khoảng:

```text
100,000 samples/s * 64 bytes = 6,400,000 bytes/s
10 minutes ≈ 3.84 GB
```

Đây là **phép tính minh họa** chưa gồm queue objects/allocator overhead. Không thể gọi là “low overhead” nếu agent cứ giữ tất cả sample mãi trong heap/native memory.

Nên có các giới hạn:

- Kích thước queue cố định, ví dụ `maxRecords` theo ngân sách đã đo.
- `droppedSamples` khi buffer đầy; báo số drop để biết chất lượng dữ liệu.
- `maxStackDepth` và hạn chế tên class/string.
- Giới hạn thời gian quan sát và số epoch.
- Tổng hợp theo bucket thay vì lưu từng raw record nếu bài toán chỉ cần histogram.
- Export rate limit và file rotation; không ghi hàng trăm file mỗi giây.
- Reset/rollover counters có kiểm soát, không âm thầm overflow.

## 15. Sampled allocations và retained heap: những kết luận được/không được đưa ra

**Có thể dùng mẫu để gợi ý:**

- Những loại object/call sites thường xuất hiện trong hoạt động cấp phát.
- Thay đổi tương đối allocation pressure giữa hai lần load test tương đồng.
- Những nhóm workload tăng allocation rate.
- Xu hướng thay đổi khi thay sampling interval/GC/JIT, với lưu ý sai số.

**Không thể kết luận chỉ từ callback count:**

- Tổng số object JVM đã từng tạo.
- Tổng byte được cấp phát chính xác.
- Những object còn sống sau GC.
- Kích thước object graph giữ bởi một reference.
- Một class có leak chỉ vì có nhiều allocation samples.
- Khoảng thời gian lifetime chính xác của object nếu không có tracking bổ sung.

Muốn theo dõi **liveness** của những sampled objects, có thể nghiên cứu JNI weak global references kết hợp cơ chế GC/liveness và kiểm thử trên JVM hỗ trợ. Nhưng việc thêm strong global refs sẽ **tác động trực tiếp lên đối tượng đo**. Khi nghi ngờ memory leak, hãy đối chiếu **heap after GC, GC logs/JFR metrics, heap dump/retained-size analysis**, thay vì coi allocation sampling như một heap census.

## 16. Kiểm thử agent và kết quả có xác suất

### 16.1. Các điều kiện test đúng

| Kịch bản | Kỳ vọng |
| --- | --- |
| JDK/runtime hỗ trợ capability | Agent xin được, enable thành công |
| Runtime không hỗ trợ | Agent báo lỗi rõ, không báo sampling đã chạy |
| Không có `-agentpath` | Workload Java vẫn chạy bình thường |
| Thêm agent nhưng interval dương | Event/counters **có thể** xuất hiện; số mẫu không được assert chính xác |
| Interval rất lớn | Trung bình ít mẫu hơn trên workload tương đồng |
| Interval nhỏ | Trung bình nhiều mẫu và overhead cao hơn |
| Interval 0 | Có thể gây overhead cực cao; không mặc định production |
| Multi-thread allocation | Callback đồng thời, atomics không data race |
| Pause/resume live | Event mode được đổi đúng; xử lý callbacks in-flight |
| JVM kết thúc bình thường | Báo cáo một lần nếu lifecycle hook xảy ra |
| Process bị kill cưỡng bức | Không kỳ vọng flush thành công |
| Disk/full exporter fail | Có dropped/error metrics, không crash app tùy chính sách |
| Queue đầy | Drop có đếm hoặc degrade có kiểm soát, không block vô hạn |
| Class/thread refs | Không giữ JNI local refs sau callback |
| Nhiều agents | Không đếm nhầm hoặc giả định overhead độc lập |
| Module/classloader đặc biệt | Không ghi tên class/stack sai hoặc giữ refs quá lâu |
| Native error | Agent trả lỗi init/attach có thể hành động, cleanup đúng |

### 16.2. Không assert số lượng callback cố định

Một test dễ flaky:

```text
Expected samples = 32
Actual samples   = 29
Test failed
```

Đó **không nhất thiết là bug**. Khoảng sampling là trung bình và có randomness; JIT, GC, thread interleaving và allocation từ JVM khác nhau giữa các lần chạy.

Test tốt hơn:

1. Xác minh native library load được và `Agent_OnLoad`/`Agent_OnAttach` return thành công.
2. Xác minh callback registration và enable return `JVMTI_ERROR_NONE`.
3. Chạy workload đủ lớn nhiều lượt trên môi trường kiểm soát.
4. Đo **phân bố** sampled events/overhead thay vì một số sample chính xác.
5. Test interval nhỏ/lớn, kiểm tra xu hướng thống kê khi có đủ mẫu.
6. Xác minh `sampled_object_bytes` không bị ghi nhầm thành `total_allocated_bytes`.
7. Benchmark baseline vs enabled sampling ở p95/p99 latency, CPU, GC, RSS/native heap.
8. Kiểm tra shutdown không crash/hang, không leak buffers/refs.
9. Ghi rõ JVM/vendor/version, số thread, GC, warm-up, thời gian chạy và interval.

### 16.3. Code Java kiểm chứng độc lập

`HeapSamplingWorkload.java` mục 10 đã được **biên dịch và chạy** với `--release 11`, stdout cố định:

```text
requested_arrays=4096
requested_payload_bytes=33554432
last_array_length=8192
```

Còn số mẫu do agent báo **không cố định**. Bài học vì thế phân tách rõ **test có thể assert chính xác** (Java workload) với **test phải đánh giá thống kê** (sampled callback).

## 17. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Coi `SampledObjectAlloc` là callback cho mọi allocation | Kết luận sai total count | Hiểu sampling probabilistic/average interval |
| Quên xin `can_generate_sampled_object_alloc_events` | Enable/cấu hình lỗi | `GetPotentialCapabilities` + `AddCapabilities` |
| Chỉ đặt callback nhưng không enable event | Không có mẫu | `SetEventCallbacks` **và** `SetEventNotificationMode` |
| Enable nhưng không cài callback | Không nhận event | Đăng ký cả hai bước |
| Lấy `JNIEnv*` trong OnLoad như ở live thread | Gọi API sai phase | Phân biệt `JavaVM*`, `jvmtiEnv*`, `JNIEnv*` |
| Gọi `SetHeapSamplingInterval(-1)` | Argument không hợp lệ | Dùng byte interval >=0, khuyến nghị dương |
| Chọn interval 0 trên service tải nặng | Overhead rất cao | Dùng interval dương và benchmark |
| Nghĩ interval đổi tức thời | Diễn giải sai epoch sample | Ghi thời điểm config change, chờ ổn định |
| Dùng `std::vector` không khóa trong callback | Data race / crash | Atomics hoặc bounded queue đúng concurrency |
| `printf` từng sample | Chậm app, bão hòa log | Counters/aggregation, exporter riêng |
| Giữ raw `jobject` sau callback | Reference không còn hợp lệ | Chỉ giữ scalar metadata hoặc weak/global refs đúng cách |
| Giữ strong global ref của mọi sampled object | Làm object không được thu hồi, sai profiler | Tránh strong refs; đánh giá weak refs |
| Quên `Deallocate` của JVMTI | Native memory leak | Giải phóng theo API tương ứng |
| Khẳng định sum(sampled size) là total heap | Kết luận sai | Báo rõ sampled bytes vs estimated vs retained |
| Coi sampled allocations nhiều là memory leak | Có thể chỉ là object tạm | So live heap/retained graph/GC |
| Dùng `JVMTI_EVENT_VM_OBJECT_ALLOC` như thay thế | Bỏ sót/khác semantics | Dùng `SAMPLED_OBJECT_ALLOC` đúng mục đích |
| Dùng `-javaagent` cho DLL | Entry point sai | `-agentpath`/`-agentlib` cho native |
| Đòi `Agent_OnUnload` phải chạy khi kill -9 | Có thể không xảy ra | Periodic export và durable pipeline riêng |
| Free state ngay khi disable, không chờ callback | Use-after-free | Quiescence/drain hoặc lifetime static |
| Gọi JVMTI live-only sau VM dead | Lỗi phase/crash | Dọn theo phase, không gọi JVMTI tùy tiện trong unload |
| Ghi raw object content/stack lên dashboard công khai | Rò dữ liệu nhạy cảm | Allowlist, phân quyền, retention |
| Dùng callback đếm chính xác 32 mẫu trong unit test | Flaky do sampling xác suất | Test thống kê, không hardcode exact samples |

## 18. Checklist trước production

- [ ] Đã xác định mục tiêu: allocation pressure, hot allocation sites hay **retained leak**? Không đánh đồng chúng?
- [ ] Dùng đúng JVM TI Java 11+ và xác nhận provider triển khai capability?
- [ ] Native library có signature, ABI, arch và compiler đúng với JVM target?
- [ ] Phân biệt `Agent_OnLoad`/`Agent_OnAttach`/`VMDeath`/`Agent_OnUnload`?
- [ ] Xin đúng `can_generate_sampled_object_alloc_events`, không xin quyền thừa?
- [ ] `SetEventCallbacks` và `SetEventNotificationMode` đều thành công?
- [ ] `SetHeapSamplingInterval` hợp lệ, đủ thưa theo benchmark?
- [ ] Callback không allocation/log/block vô hạn và an toàn khi nhiều thread cùng gọi?
- [ ] Không giữ `JNIEnv*` hoặc local `jobject/jclass` sau callback?
- [ ] Nếu dùng weak refs/tags/stacks, có kế hoạch liveness/cleanup/chi phí?
- [ ] Aggregation/buffer có capacity, drop policy, epoch và overflow handling?
- [ ] `sample_count`/`sampled_object_bytes` không được trình bày như exact total heap?
- [ ] Có cơ chế pause/stop ở **live phase**, chặn in-flight callbacks chạm state đã free?
- [ ] Có periodic export/retention khi service chạy lâu, không chỉ OnUnload?
- [ ] Có test runtime unsupported, attach disabled, nhiều agents và shutdown bất thường?
- [ ] Có baseline CPU, p95/p99 latency, RSS, native heap, GC trước/sau?
- [ ] Dữ liệu class/thread/stack không ghi secrets/PII và đã được phân quyền?
- [ ] Có versioning và kiểm thử sau khi nâng JDK hoặc đổi GC/architecture?

## 19. Bài luyện tập có đáp án

**Bài 1.** Một agent cài `callbacks.SampledObjectAlloc` nhưng không gọi `SetEventNotificationMode`. Vì sao không có mẫu?

**Đáp án:** Theo JVMTI, callback phải được **đăng ký và enable**; việc cài bảng callback không tự bật event.

**Bài 2.** `GetPotentialCapabilities` cho `can_generate_sampled_object_alloc_events=false`. Có nên vẫn gọi `SetHeapSamplingInterval` và bỏ qua return code?

**Đáp án:** Không. Đây là optional capability; báo unsupported, fail-fast hoặc graceful degrade có ghi trạng thái đúng chính sách. Không trình bày số liệu sampling giả.

**Bài 3.** App tạo 4.096 mảng 8 KiB payload và agent interval 1 MiB. Có thể assert callback đúng 32 lần?

**Đáp án:** Không. Khoảng là trung bình bán ngẫu nhiên theo byte/thread, có JVM allocations/header/alignment/JIT. Chỉ stdout của Java workload có count/payload cố định.

**Bài 4.** Vì sao `SampledObjectAlloc` callback không nên tạo `NewGlobalRef` cho mọi object?

**Đáp án:** Strong global refs giữ sống object, làm méo liveness/heap và tăng memory; nếu cần lifetime tracking phải dùng phương án khác được review, ví dụ weak refs với cleanup.

**Bài 5.** Có thể lưu `JNIEnv*` và `jobject` từ callback vào vector để worker native đọc sau không?

**Đáp án:** Không. `JNIEnv*` là per-thread; `jobject` được cấp dưới dạng local ref ở callback có lifetime giới hạn. Chỉ chuyển metadata scalar hoặc refs được quản lý đúng cơ chế.

**Bài 6.** Vì sao `std::atomic.fetch_add(relaxed)` hợp lý cho hai counter độc lập?

**Đáp án:** Đảm bảo mỗi increment là atomic, tránh data race; không cần ordering giữa counters với dữ liệu khác. Nhưng đọc hai counter đồng thời không tự cho snapshot transaction-consistent.

**Bài 7.** `Agent_OnUnload` có đủ để bảo đảm lưu mọi sample khi pod bị kill không?

**Đáp án:** Không. Khi process bị kill cưỡng bức hoặc crash, hook có thể không chạy. Dùng periodic export, quota và retention riêng nếu cần bền vững hơn.

**Bài 8.** Một class có allocation sample rất nhiều có chắc gây memory leak?

**Đáp án:** Không. Nó có thể tạo nhiều object tạm ngắn hạn. Leak cần kiểm tra retained/live heap, GC và object references theo thời gian.

**Bài 9.** Muốn đổi sampling interval từ 1 MiB xuống 256 KiB khi đang chạy, lưu ý gì?

**Đáp án:** Gọi `SetHeapSamplingInterval` trong phase hợp lệ, kiểm tra error/capability, ghi epoch thay đổi, chờ cơ chế per-thread cập nhật và benchmark overhead; không giả định event frequency đổi tức thì/chính xác.

**Bài 10.** Một agent dùng `-javaagent:heapsample.dll`. Có hoạt động như native JVMTI agent không?

**Đáp án:** Không. `-javaagent` dành cho JAR Java Instrumentation, thường có `premain`/`agentmain`. DLL JVMTI dùng `-agentpath` hoặc `-agentlib`, với `Agent_OnLoad`/`Agent_OnAttach` tương ứng.

## 20. Tổng kết và tài liệu tham khảo

**Nhớ mô hình:**

```text
Load/Attach agent
  -> request capability
  -> register callback
  -> set interval
  -> enable sampled event
  -> record bounded scalar metadata
  -> aggregate/export with privacy and quotas
  -> disable/drain/cleanup while phases permit
  -> VMDeath / Agent_OnUnload
```

**Ba phân biệt quan trọng nhất:** (1) callback quan sát **mẫu allocation** chứ không phải mọi allocation; (2) `size`/sampled bytes không phải retained heap; (3) JVMTI native agent chạy trong process và phải quản lý thread safety, JNI references, failure/shutdown như code hệ thống thật. Với ứng dụng không muốn duy trì native agent, cân nhắc profiler/JFR đã được kiểm thử thay vì tự xây code native production từ ví dụ.

**Tài liệu chính thức, còn áp dụng:**

- [Oracle Java SE 11 — JVM Tool Interface, tổng quan và Agent Start-Up/Shutdown](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html): `Agent_OnLoad`, `Agent_OnAttach`, `Agent_OnUnload`, phases, callback model.
- [Oracle Java SE 11 — Heap Monitoring / SetHeapSamplingInterval](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html#HeapMonitoring): khoảng mẫu, capability, error semantics.
- [Oracle Java SE 11 — Sampled Object Allocation event](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html#SampledObjectAllocation): callback arguments, live phase, 512 KiB default.
- [Oracle Java SE 11 — Event Management](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html#EventManagement): `SetEventCallbacks` và `SetEventNotificationMode`.
- [OpenJDK JEP 331 — Low-Overhead Heap Profiling](https://openjdk.org/jeps/331): đưa sampling qua JVMTI vào Java 11.
- [Oracle Java SE 11 — Java launcher / -agentpath](https://docs.oracle.com/en/java/javase/11/tools/java.html): nạp native JVMTI agent từ startup.
- [Oracle JNI specification](https://docs.oracle.com/en/java/javase/11/docs/specs/jni/index.html): local/global/weak JNI references, ownership và thread handling.
- [Oracle Java SE 25 — JVM Tool Interface](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html): cùng cơ chế sampling tiếp tục được hỗ trợ ở runtime hiện đại.
