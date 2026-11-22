# SampledObjectAlloc và khả năng hỗ trợ của JVM (Heap profiling, Java 11+)

**Chủ đề cha: Heap profiling.** Khi ứng dụng Java liên tục tạo object, dung lượng heap sau một lần GC đôi khi vẫn thấp nhưng CPU/GC/độ trễ lại tăng. Để xác định **object được cấp phát ở đâu** mà không ghi lại mọi allocation, JDK 11 đưa vào JVM Tool Interface (**JVMTI**) sự kiện **`SampledObjectAlloc`** thông qua **JEP 331 — Low-Overhead Heap Profiling**. Một native profiler có thể nhận callback khi JVM chọn một object allocation làm mẫu, lấy kích thước, class, thread và theo chính sách có thể truy vấn stack để tìm call site.

**Điểm cần nắm chắc:** `SampledObjectAlloc` là **JVMTI event (Java 11+)**, *không* phải event `jdk.ObjectAllocationSample` của **Java Flight Recorder (JFR)**. Event JFR mang tên `jdk.ObjectAllocationSample` chỉ được thêm từ **JDK 16**. Ngoài ra, API chuẩn JVMTI không đồng nghĩa mọi JVM hỗ trợ: agent phải kiểm tra và xin **optional capability** `can_generate_sampled_object_alloc_events` trên runtime thực. Đây là những kiến thức **vẫn còn áp dụng hiện nay**, không cần dựa vào cách làm legacy trước Java 11.

Bài này giải thích sampling, capability negotiation, `SetHeapSamplingInterval`, event notification, giới hạn thống kê, cách xây native agent Java 11 chạy được trên Linux và cách lựa chọn JFR hiện đại khi JVMTI không phù hợp. Các chương trình Java dùng API hiện còn được hỗ trợ; có ghi chú rõ khi yêu cầu JDK 17+.

## 1. Allocation profiling khác với heap dump và memory leak analysis

Một chương trình có thể cấp phát hàng GB object trong vài phút nhưng vẫn sử dụng rất ít heap tại một thời điểm, vì nhiều object chết nhanh và được GC thu dọn.

```java
for (int i = 0; i < 10_000; i++) {
    byte[] temporary = new byte[16 * 1024];
    consume(temporary);
}
```

Đây là **đoạn minh họa**: `consume(byte[])` cần được khai báo riêng. Nó cho thấy ý tưởng tạo nhiều allocations; compiler/JIT có thể tối ưu khác nhau tùy cách sử dụng dữ liệu thực tế.

| Câu hỏi | Công cụ phù hợp | Điều không được suy ra |
| --- | --- | --- |
| Object được cấp phát ở đâu và với tốc độ nào? | Allocation sampling/profiling, stack attribution | Không tự biết object có sống lâu |
| Những object nào còn chiếm heap? | Heap histogram/dump, retained-size analysis | Không hiện mọi object đã cấp phát rồi bị GC |
| Tại sao GC chậm? | GC logs, JFR GC events và heap metrics | Không thể chỉ nhìn callback allocation |
| Method nào dùng nhiều CPU? | CPU profiler và JFR execution samples | Allocation count không phải CPU time |
| Có memory leak hay không? | Live set qua thời gian, heap dump/dominator | Một sample cấp phát không chứng minh leak |

**Event của JVMTI phát khi object được cấp phát**, không phải khi object vẫn sống trong heap ở thời điểm hiện tại. Một object được sample có thể đã chết trước khi file profiling được xem. Nếu muốn theo dõi live/dead objects, cần thêm cơ chế weak references, tagging/GC analysis được thiết kế đúng.

## 2. SampledObjectAlloc là gì?

JVMTI là native interface dành cho agent/profiler/debugger chạy **bên trong** JVM. Java 11 bổ sung:

- `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC` (event number **86**), callback tên `SampledObjectAlloc`.
- Capability `can_generate_sampled_object_alloc_events`.
- Hàm `SetHeapSamplingInterval(jint sampling_interval)` để điều chỉnh khoảng trung bình theo **byte đã cấp phát**.

Sơ đồ:

```text
Java application: new Object(), new byte[], libraries, JNI, ...
                         |
                         v
               Java heap allocation
                         |
                 JVMTI heap sampler
                         |
                selected allocation?
                  /             \
                no              yes
                |                |
                v                v
          no callback     SampledObjectAlloc(
                            jvmtiEnv, JNIEnv,
                            thread, object, klass, size)
                                      |
                                      v
                        native profiler aggregate results
```

Một agent nhận mẫu có thể biết **class của object**, **kích thước object** và **thread đang cấp phát**. Có thể thu call stack bằng `GetStackTrace` hoặc cơ chế profiler tương ứng, nhưng phải tính overhead và giữ callback ngắn.

### Không nhầm với VMObjectAlloc

JVMTI cũng có event `VMObjectAlloc` từ lâu. Nó mô tả những allocations trực tiếp do VM thực hiện trong một số trường hợp; **không** phải nguồn bao phủ mọi lệnh `new` của bytecode. `SampledObjectAlloc` là cơ chế sampling allocation có phạm vi ứng dụng rộng hơn cho heap profiling.

| Cơ chế | Ý nghĩa |
| --- | --- |
| `SampledObjectAlloc` | JVMTI sample một Java heap allocation theo thống kê |
| `VMObjectAlloc` | JVM TI event cho allocations do VM trực tiếp thực hiện theo quy tắc riêng |
| `ObjectFree` | JVMTI event khi tagged object được giải phóng; phục vụ analysis khác |
| `jdk.ObjectAllocationSample` | JFR event, được thêm từ JDK 16 |
| `jdk.ObjectAllocationInNewTLAB` | JFR event đã có ở Java 11, có semantics/overhead khác |
| `jdk.ObjectAllocationOutsideTLAB` | JFR event đã có ở Java 11, có semantics/overhead khác |

## 3. Sampling diễn ra ra sao?

Theo đặc tả JVMTI, mỗi thread có bộ đếm lượng byte đã cấp phát từ lần mẫu trước, kết hợp điểm mẫu mang tính **bán ngẫu nhiên**. Điều này giúp tránh thiên lệch khi ứng dụng có một mẫu phân bổ lặp đều.

- Mức mặc định được mô tả là **512 KB** (524.288 byte trung bình một sample).
- Sau mỗi khoảng trung bình, một allocation được chọn để báo qua callback.
- **Không** phải timer: interval tính theo **bytes**, không tính theo giây.
- **Không** phải đếm chính xác một event cho mỗi 512 KB: các khoảng và object được chọn có thể khác nhau.
- Tracking/sampling theo thread khiến phân bố samples chịu ảnh hưởng số lượng threads và pattern workload.
- Khi thay đổi interval, JVM có thể cần thêm các allocations để cập nhật trạng thái sampling; không bảo đảm hiệu lực chính xác từ allocation kế tiếp.

Ví dụ khái niệm:

```text
Thread A:
[16KB][64KB][4KB][100KB][...sample...][8KB]...
           khoảng bán ngẫu nhiên

Thread B:
[256B][256B][...][...sample...]...
           bộ đếm khác

Trên thời gian dài: số mẫu tỷ lệ với lượng cấp phát,
nhưng không cho số object/tổng bytes chính xác theo từng lần.
```

### SetHeapSamplingInterval

Chữ ký JVMTI:

```c
jvmtiError SetHeapSamplingInterval(
    jvmtiEnv *env, jint sampling_interval);
```

Cách gọi qua C function table:

```c
jvmtiError err =
    (*ti)->SetHeapSamplingInterval(ti, 512 * 1024);
```

**Đoạn trên minh họa**, giả sử `jvmtiEnv *ti` đã được tạo và agent đang sở hữu capability.

| Interval | Ý nghĩa trung bình | Đánh đổi |
| --- | --- | --- |
| `0` | Cố gắng lấy mẫu **mỗi allocation được hỗ trợ** | Overhead rất cao, chỉ thử có kiểm soát |
| `1024` bytes | Khoảng 1 KB/mẫu | Nhiều callbacks; có thể nhiễu và nặng |
| `65536` bytes | Khoảng 64 KB/mẫu | Nhiều chi tiết hơn, nhiều chi phí hơn |
| `524288` bytes | Khoảng 512 KB/mẫu | Giá trị mặc định được JVMTI mô tả |
| `4194304` bytes | Khoảng 4 MB/mẫu | Ít samples hơn, giảm overhead |

**Cực kỳ quan trọng:** `SetHeapSamplingInterval(0)` **không phải tắt sampling**. Nếu muốn ngừng event, dùng `SetEventNotificationMode(JVMTI_DISABLE, JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, ...)` hoặc cơ chế quản lý profiler đã được thiết kế. Tham số âm trả `JVMTI_ERROR_ILLEGAL_ARGUMENT`; gọi khi thiếu capability có thể trả `JVMTI_ERROR_MUST_POSSESS_CAPABILITY`.

Trong production, chọn khoảng có ý nghĩa thống kê và đo overhead thật. Không bật mọi allocation toàn hệ thống chỉ vì muốn làm bảng đếm “chính xác”.

## 4. Callback nhận những dữ liệu nào?

Chữ ký trong JVMTI spec:

```c
void JNICALL SampledObjectAlloc(
    jvmtiEnv *jvmti_env,
    JNIEnv *jni_env,
    jthread thread,
    jobject object,
    jclass object_klass,
    jlong size);
```

| Tham số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `jvmti_env` | JVMTI environment của agent | Dùng gọi hàm JVMTI đúng giai đoạn |
| `jni_env` | JNI environment của thread liên quan | Không chia sẻ với thread khác |
| `thread` | Thread thực hiện allocation | Dùng lấy stack nếu profiler cần |
| `object` | JNI local reference tới object được sample | Không giữ ngoài callback nếu chưa quản lý reference hợp lệ |
| `object_klass` | JNI local reference tới class của object | Dùng phân loại object |
| `size` | Kích thước **object được chọn**, đơn vị byte | Không phải tổng allocated bytes của JVM |

Callback xảy ra **sau khi** allocation của object được thực hiện. Có thể kết hợp class/size/stack để xác định call site gây áp lực cấp phát. Tuy nhiên:

- Stack bị ảnh hưởng bởi JIT inlining, native frames và metadata debug; không hứa luôn hiện đúng một dòng source.
- Không log mỗi sample, gọi I/O tốn kém hoặc tạo thêm vô số object từ callback; điều đó làm sai phép đo và tăng overhead.
- JNI local references không được giữ tùy tiện qua vòng đời callback.
- Nếu cần giữ dấu vết object sau callback, thiết kế weak-reference/tagging phù hợp. Strong refs của profiler có thể **làm object sống lâu giả tạo**.
- Không suy GC behavior hoặc memory leak chỉ từ callback lúc cấp phát.

## 5. Capability là tùy chọn: không phải mọi JVM đều hỗ trợ

Đặc tả Java 11 đánh dấu `SampledObjectAlloc` và `SetHeapSamplingInterval` là **Optional Functionality**. Vì vậy, một JVM có JVMTI nói chung nhưng không cấp capability này vẫn phù hợp với đặc tả.

Một agent cần thực hiện:

```text
JavaVM
  |
  +-- GetEnv(...JVMTI_VERSION_1_2)
  |        +-- fail -> không có JVMTI interface phù hợp
  |
  +-- GetPotentialCapabilities
  |        +-- bit can_generate_sampled_object_alloc_events = 0
  |                     -> UNSUPPORTED/UNAVAILABLE tại phase hiện tại
  |
  +-- AddCapabilities(requested)
  |        +-- error -> không được cấp
  |
  +-- GetCapabilities
  |        +-- bit vẫn 0 -> không tiếp tục
  |
  +-- SetHeapSamplingInterval
  |
  +-- SetEventCallbacks
  |
  +-- SetEventNotificationMode(
  |         JVMTI_ENABLE,
  |         JVMTI_EVENT_SAMPLED_OBJECT_ALLOC,
  |         NULL)
  |
  +-- SampledObjectAlloc callbacks
```

**Phân biệt ba hàm kiểm tra:**

1. `GetPotentialCapabilities`: những capability **có thể xin** ở thời điểm/phase hiện tại. Không có bit này có thể do JVM không hỗ trợ hoặc không còn cho xin trong phase đó.
2. `AddCapabilities`: thực sự **xin quyền**. Phải kiểm tra `jvmtiError`; không thể bỏ qua kết quả.
3. `GetCapabilities`: kiểm chứng agent **đang sở hữu** bit đó sau khi xin.

**`java -version` không phải capability probe.** Nó chỉ cho build/version/vendor; có những runtime HotSpot, OpenJ9, GraalVM, native image hoặc bản tối giản với mức hỗ trợ khác nhau. Không kết luận từ “Java 11+” hay “JFR.start hoạt động” rằng JVMTI SampledObjectAlloc đã khả dụng.

Ở môi trường production, nhiều agent có thể cạnh tranh capabilities hoặc đặt sampling interval khác nhau; xem chính sách profiler và test trên runtime thực.

## 6. Ví dụ native agent C: kiểm tra capability rồi ghi nhận samples

Đây là một **chương trình JVMTI thật**, không mô phỏng bằng Java object counters. Chạy trên **Linux + JDK 11+ có jvmti.h + GCC hỗ trợ C11**. Trên Windows/macOS phải thay toolchain, include platform và đuôi shared library. Agent được load ở JVM startup, không phải attach vào process đã chạy.

### Tệp sampled_alloc_agent.c

```c
#include <jni.h>
#include <jvmti.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

static atomic_ullong samples = 0;
static atomic_ullong sampled_object_bytes = 0;

static void JNICALL on_sample(
        jvmtiEnv *ti, JNIEnv *jni,
        jthread thread, jobject object,
        jclass object_klass, jlong size) {
    // Không giữ JNI references; callback cần ngắn và thread-safe.
    (void)ti; (void)jni; (void)thread;
    (void)object; (void)object_klass;

    atomic_fetch_add_explicit(&samples, 1ULL,
                              memory_order_relaxed);
    if (size > 0) {
        atomic_fetch_add_explicit(
            &sampled_object_bytes,
            (unsigned long long)size,
            memory_order_relaxed);
    }
}

static jint fail(const char *phase, jvmtiError err) {
    fprintf(stderr, "JVMTI error at %s: %d\n", phase, (int)err);
    return JNI_ERR;
}

JNIEXPORT jint JNICALL Agent_OnLoad(
        JavaVM *vm, char *options, void *reserved) {
    (void)options;
    (void)reserved;
    jvmtiEnv *ti = NULL;

    jint jniStatus =
            (*vm)->GetEnv(vm, (void **)&ti, JVMTI_VERSION_1_2);
    if (jniStatus != JNI_OK || ti == NULL) {
        fprintf(stderr, "JVMTI interface unavailable\n");
        return JNI_ERR;
    }

    jvmtiCapabilities potential;
    memset(&potential, 0, sizeof(potential));
    jvmtiError err =
            (*ti)->GetPotentialCapabilities(ti, &potential);
    if (err != JVMTI_ERROR_NONE) {
        return fail("GetPotentialCapabilities", err);
    }

    if (!potential.can_generate_sampled_object_alloc_events) {
        fprintf(stderr,
                "UNSUPPORTED: sampled allocation capability\n");
        return JNI_ERR;
    }

    jvmtiCapabilities requested;
    memset(&requested, 0, sizeof(requested));
    requested.can_generate_sampled_object_alloc_events = 1;

    err = (*ti)->AddCapabilities(ti, &requested);
    if (err != JVMTI_ERROR_NONE) {
        return fail("AddCapabilities", err);
    }

    jvmtiCapabilities granted;
    memset(&granted, 0, sizeof(granted));
    err = (*ti)->GetCapabilities(ti, &granted);
    if (err != JVMTI_ERROR_NONE) {
        return fail("GetCapabilities", err);
    }
    if (!granted.can_generate_sampled_object_alloc_events) {
        fprintf(stderr, "Sampled allocation capability not granted\n");
        return JNI_ERR;
    }

    err = (*ti)->SetHeapSamplingInterval(ti, 512 * 1024);
    if (err != JVMTI_ERROR_NONE) {
        return fail("SetHeapSamplingInterval", err);
    }

    jvmtiEventCallbacks callbacks;
    memset(&callbacks, 0, sizeof(callbacks));
    callbacks.SampledObjectAlloc = &on_sample;

    err = (*ti)->SetEventCallbacks(
            ti, &callbacks, (jint)sizeof(callbacks));
    if (err != JVMTI_ERROR_NONE) {
        return fail("SetEventCallbacks", err);
    }

    err = (*ti)->SetEventNotificationMode(
            ti, JVMTI_ENABLE,
            JVMTI_EVENT_SAMPLED_OBJECT_ALLOC, NULL);
    if (err != JVMTI_ERROR_NONE) {
        return fail("SetEventNotificationMode", err);
    }

    fprintf(stderr,
            "SampledObjectAlloc enabled: interval=524288 bytes\n");
    return JNI_OK;
}

JNIEXPORT void JNICALL Agent_OnUnload(JavaVM *vm) {
    (void)vm;

    unsigned long long count =
            atomic_load_explicit(&samples, memory_order_relaxed);
    unsigned long long sizes =
            atomic_load_explicit(&sampled_object_bytes,
                                 memory_order_relaxed);

    fprintf(stderr, "sample callbacks: %llu\n", count);
    fprintf(stderr,
            "sum of sampled object sizes: %llu bytes\n", sizes);
}
```

### Agent này thực hiện những gì?

- Lấy JVMTI environment, kiểm tra potential capability, cấp quyền và xác minh lại trước khi bật event.
- Đặt interval 512 KB. Callback cập nhật counters dạng atomic để không tạo data race khi nhiều Java threads cấp phát.
- Không gọi Java code hoặc giữ references ra ngoài callback, không in log trên từng allocation.
- In kết quả trong `Agent_OnUnload` khi JVM kết thúc **bình thường**. Nếu JVM crash/kill đột ngột, cleanup có thể không chạy và dữ liệu demo có thể mất.
- Trả `JNI_ERR` khi unsupported, nghĩa là **demo cố tình từ chối khởi động JVM** để báo lỗi rõ. Production profiler phải có fallback/feature flag và không được làm service mất khả năng khởi động chỉ vì thiếu profiling.

**Chỉ số `sum of sampled object sizes` là tổng kích thước những object thực sự được chọn mẫu**, không phải tổng allocation traffic. Để ước lượng bytes allocated theo stack cần mô hình sampling/trọng số phù hợp. Không tự nhân số callbacks với 512KB rồi tuyên bố có số đo chính xác.

## 7. Workload Java 11 cho agent

Tệp Java sau tạo các mảng `byte[]` và giữ lại một số object qua ring buffer. Điều này giúp tạo đủ nhiều actual heap allocations để quan sát sampler thay vì giả định một số lượng allocations từ source luôn được JIT giữ nguyên.

### Tệp HeapSampleWorkload.java

```java
public final class HeapSampleWorkload {
    private static volatile byte[][] retained;

    public static void main(String[] args) {
        final int count = 20_000;
        final int size = 16 * 1024;

        byte[][] ring = new byte[256][];
        for (int i = 0; i < count; i++) {
            byte[] block = new byte[size];
            block[0] = (byte)i;
            ring[i % ring.length] = block;
        }

        retained = ring;
        System.out.println("allocated blocks: " + count);
        System.out.println("block payload bytes: " + size);
    }
}
```

Biên dịch trên **Linux + JDK 11+ + GCC** (cần `$JAVA_HOME/include/jni.h` và `jvmti.h`):

```bash
javac --release 11 -encoding UTF-8 HeapSampleWorkload.java

gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  sampled_alloc_agent.c -o libsampled_alloc_agent.so

java -Xmx128m -agentpath:"$(pwd)/libsampled_alloc_agent.so" \
  HeapSampleWorkload
```

Đảm bảo `JAVA_HOME` trỏ tới JDK thực chứa headers và phiên bản Java tương thích. Dấu `\` là cú pháp nối dòng **Bash**, không copy nguyên vào PowerShell.

Kết quả thành công có dạng:

```text
SampledObjectAlloc enabled: interval=524288 bytes
allocated blocks: 20000
block payload bytes: 16384
sample callbacks: <gia-tri-thay-doi>
sum of sampled object sizes: <gia-tri-thay-doi> bytes
```

**Hai dòng đầu/các giá trị block cố định trong demo**, nhưng `sample callbacks` và tổng sampled sizes **không có một stdout cố định**. Không test chính xác “N callbacks = số byte đã cấp phát chia cho 524288” vì sampling mang tính ngẫu nhiên và overhead kích thước object khác payload.

Nếu log `UNSUPPORTED`, hoặc `AddCapabilities`/`SetEventNotificationMode` lỗi, agent đã làm đúng nhiệm vụ **báo khả năng hỗ trợ thực tế**. Không gỡ phần kiểm tra capability để ép kết quả thành công.

## 8. Quyền, phase và cách load agent

`-agentpath:/full/path/libsampled_alloc_agent.so` sử dụng `Agent_OnLoad` **tại JVM startup**. Nó không phải cú pháp điều khiển một JVM đã chạy; muốn attach agent tại runtime cần triển khai `Agent_OnAttach` và có JVM hỗ trợ attach, đúng quyền OS, security policy và khả năng cấp capability ở **live phase**.

Các giới hạn cần ghi nhớ:

1. **OnLoad vs live:** một capability có thể xin được lúc khởi động nhưng không còn xin được hoặc bị chiếm tại live phase; luôn kiểm tra bằng `GetPotentialCapabilities` đúng lúc.
2. **Native library:** đúng architecture, ABI, toolchain và hệ điều hành. File `.so` Linux không chạy trực tiếp trên Windows.
3. **Security:** agent native có quyền mạnh đối với tiến trình; chỉ load agent được tin cậy.
4. **Containers:** JVM trong container có thể không có toolchain/headers; nên build ngoài image runtime, copy library hợp lệ và cấp quyền tối thiểu.
5. **Overhead:** bắt đầu bằng interval tương đối lớn, đo CPU/latency/throughput và GC trước–sau.
6. **Phòng ngừa lỗi:** disable profiling an toàn khi thiếu capability; không thay JVM chính bằng phiên bản debug nguy hiểm chỉ để chạy mẫu.
7. **Không kết luận có thể attach từ xa:** các lệnh JVMTI agent mặc định chạy local/in-process. Điều khiển từ xa cần cơ chế bảo mật riêng của profiler.

## 9. JFR và JVMTI: hai hệ thống sự kiện khác nhau

Từ Java 11 có cơ chế JVMTI sample allocation, nhưng event JFR low-overhead mang tên **`jdk.ObjectAllocationSample` xuất hiện trong JDK 16**. Oracle công bố event này được bật trong các preset JFR `default` và `profile` của JDK 16, với throttle ban đầu lần lượt 150 và 300 events/giây. Không coi các con số throttle của JDK 16 là giá trị vĩnh viễn cho mọi JDK/provider.

| Tên | Cơ chế | Trên JDK 11 | Trên JDK 17/21+ |
| --- | --- | --- | --- |
| `SampledObjectAlloc` | JVMTI callback, cần capability | **Có theo JEP 331 nếu VM hỗ trợ** | Có trong các JVM tiếp tục hỗ trợ capability |
| `jdk.ObjectAllocationSample` | JFR event | **Chưa được chuẩn JFR Java 11 cung cấp** | Thường có trên HotSpot có JFR |
| `jdk.ObjectAllocationInNewTLAB` | JFR event | Có, tùy bật/tắt | Có nhưng thường tắt ở preset mặc định |
| `jdk.ObjectAllocationOutsideTLAB` | JFR event | Có, tùy bật/tắt | Có nhưng thường tắt ở preset mặc định |

**Không được làm:**

```java
// Sai: "SampledObjectAlloc" là tên sự kiện JVMTI,
// không phải tên JFR event có thể bật như bên dưới.
// recording.enable("SampledObjectAlloc");
```

Nếu dùng JFR, chọn **tên JFR event thực có trong JVM**, rồi kiểm tra settings, throttle, sampling và schema trong file. Nếu dùng JVMTI, phải xin capability và bật `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC`.

### Sự khác nhau về dữ liệu

JVMTI callback cung cấp `object_klass`, `size`, `thread`, object reference. Với JFR event `jdk.ObjectAllocationSample`, một số bản JDK có các fields `objectClass` và `weight` (trọng số mẫu), kèm thread/stack khi cấu hình hỗ trợ. **Không dùng `weight` như thể là `size` được truyền từ JVMTI callback**; chúng có ngữ nghĩa khác nhau.

## 10. Kiểm tra JFR event types ngay trong JVM

Nếu đang dùng JFR để profiling, mã Java sau liệt kê availability của các event allocation, **không giả định dựa vào version string**.

### Tệp AllocationEventAvailability.java

```java
import java.util.HashSet;
import java.util.Set;

import jdk.jfr.EventType;
import jdk.jfr.FlightRecorder;

public class AllocationEventAvailability {
    public static void main(String[] args) {
        Set<String> eventNames = new HashSet<>();

        for (EventType type :
                FlightRecorder.getFlightRecorder().getEventTypes()) {
            eventNames.add(type.getName());
        }

        System.out.println("feature version: "
                + Runtime.version().feature());
        System.out.println("JFR allocation sample: "
                + eventNames.contains("jdk.ObjectAllocationSample"));
        System.out.println("JFR new TLAB event: "
                + eventNames.contains("jdk.ObjectAllocationInNewTLAB"));
        System.out.println("JFR outside TLAB event: "
                + eventNames.contains("jdk.ObjectAllocationOutsideTLAB"));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 AllocationEventAvailability.java
java AllocationEventAvailability
```

Stdout tùy JVM; trên HotSpot JDK 11 thông thường có thể thấy JFR allocation sample = `false`, trên HotSpot JDK 17+ thường là `true`. **Không ép kết quả trong assertion** vì JVM custom có thể khác. Nếu JFR module không tồn tại hoặc không thể khởi tạo, chương trình có thể không chạy; đó không phải bằng chứng về JVMTI capability.

**Giới hạn:** `FlightRecorder.getEventTypes()` kiểm tra **JFR event registry**, không kiểm tra JVMTI `can_generate_sampled_object_alloc_events`. Java program không thay thế native capability probe ở mục 6.

## 11. Ví dụ JFR allocation sampling trên JDK 17+

Đây là một chương trình **Java 17+**, chỉ dùng event khi runtime thật sự công bố `jdk.ObjectAllocationSample`. Nó tạo recording, sinh allocation pressure, ghi file và đếm samples. Vì là chương trình JFR chứ không phải JVMTI, nó **không** thực hiện `GetPotentialCapabilities`.

### Tệp JfrAllocationSampleDemo.java

```java
import java.nio.file.Path;
import java.util.HashSet;
import java.util.Set;

import jdk.jfr.EventType;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrAllocationSampleDemo {
    private static volatile byte[][] retained;

    static void allocate() {
        byte[][] ring = new byte[256][];
        for (int i = 0; i < 50_000; i++) {
            byte[] data = new byte[4096];
            data[0] = (byte)i;
            ring[i % ring.length] = data;
        }
        retained = ring;
    }

    public static void main(String[] args) throws Exception {
        Set<String> types = new HashSet<>();
        for (EventType e :
                FlightRecorder.getFlightRecorder().getEventTypes()) {
            types.add(e.getName());
        }

        if (!types.contains("jdk.ObjectAllocationSample")) {
            System.out.println("JFR allocation sample unavailable");
            return;
        }

        Path path = Path.of("allocation-sample.jfr");

        try (Recording recording = new Recording()) {
            recording.enable("jdk.ObjectAllocationSample")
                    .withStackTrace();
            recording.start();
            allocate();
            recording.stop();
            recording.dump(path);
        }

        long count = 0;
        long weight = 0;
        try (RecordingFile reader = new RecordingFile(path)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                if (!"jdk.ObjectAllocationSample".equals(
                        event.getEventType().getName())) {
                    continue;
                }
                count++;
                if (event.hasField("weight")) {
                    weight += event.getLong("weight");
                }
            }
        }

        System.out.println("file created: " + path);
        System.out.println("samples observed: " + count);
        System.out.println("sum sample weights: " + weight);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 JfrAllocationSampleDemo.java
java JfrAllocationSampleDemo
jfr summary allocation-sample.jfr
```

Số sample và tổng trọng số **không cố định**; có thể rất ít hoặc 0 nếu event không phát đủ trong cửa sổ thu, runtime throttling hoặc các thiết lập khác. File `.jfr` có thể được xem bằng JDK Mission Control, `jfr print` hoặc `RecordingFile`. Chỉ kết luận về **những events có thật**, không biến absence của sample thành bằng chứng không có allocations.

### Với tiến trình đã chạy

Trên JVM có JFR event phù hợp và quyền điều khiển, một quy trình điều tra ngắn:

```bash
jcmd 12345 JFR.start name=alloc settings=profile duration=60s filename=/var/tmp/alloc.jfr
jcmd 12345 JFR.check name=alloc verbose=true

# Sau khi recording xuất file:
jfr summary /var/tmp/alloc.jfr
jfr print --events jdk.ObjectAllocationSample /var/tmp/alloc.jfr
```

**PID 12345 chỉ minh họa**; dùng PID thực. Tên event chính xác phải được JVM hỗ trợ; trên JDK 11 **đừng chờ** `jdk.ObjectAllocationSample` nếu runtime chỉ có các event TLAB cũ.

## 12. Cách chọn phương án trên Java 11

Nếu đang dùng Java 11 và muốn phân tích allocation:

1. Nếu cần **native low-overhead heap sampling**, sử dụng profiler có triển khai JVMTI JEP 331 và **kiểm tra capability** như ở ví dụ C.
2. Nếu chỉ có JFR và không dùng native agent, kiểm tra các loại event `jdk.ObjectAllocationInNewTLAB` và `jdk.ObjectAllocationOutsideTLAB`; bật chúng có kiểm soát vì overhead có thể cao.
3. Nếu cần tìm object **đang bị giữ lại**, dùng heap dump/histogram và retained heap analysis, không chỉ allocation sampling.
4. Nếu có thể nâng cấp JVM được hỗ trợ, JDK 17/21+ có JFR `jdk.ObjectAllocationSample` trong các runtime cung cấp event này; dùng JFR configuration phù hợp thay vì giả định có trên JDK 11.
5. Nếu JVM không hỗ trợ JVMTI capability/attach, không cố vượt security controls; chọn công cụ profiler/JFR khác được vendor cho phép.

Đoạn code JFR sau chỉ **minh họa** API trong môi trường test (cần đối tượng `jdk.jfr.Recording recording`). Bật hai event TLAB ở JDK 11 có thể gây overhead và **không** giống sampled allocation event JDK 16:

```java
recording.enable("jdk.ObjectAllocationInNewTLAB")
         .withStackTrace();
recording.enable("jdk.ObjectAllocationOutsideTLAB")
         .withStackTrace();
```

JFR trong Java 11 có thể dùng cấu hình `.jfc` để kiểm soát chúng; nên thu trong cửa sổ ngắn, xác nhận settings/threshold bằng `JFR.check verbose=true` và benchmark overhead. Không mặc định mỗi event tương ứng **một** object allocation thường gặp: event TLAB và trường size/heap capacity có semantics riêng.

## 13. Đọc đúng thống kê: sampled size không phải total allocation

Giả sử một report ghi:

```text
Stack A: 120 samples
Stack B:  20 samples
Stack C:   5 samples
```

Không thể tự suy ra rằng stack A đã tạo chính xác 120 objects, có 120 objects còn sống, hoặc cấp phát đúng 120 × 512 KB.

| Số liệu | Có thể hiểu | Không thể hiểu |
| --- | --- | --- |
| Số callback JVMTI | Bao nhiêu allocations đã được sampler chọn trong cửa sổ | Tổng objects được tạo |
| Tổng `size` callback | Tổng kích thước các **object được chọn mẫu** | Toàn bộ bytes allocated |
| JFR `weight` | Trọng số sample theo schema/thuật toán JFR | JVMTI callback size hoặc live heap |
| Heap used sau GC | Snapshot heap tại thời điểm đó | Tổng allocation rate |
| GC pause duration | Thời lượng của các event GC đã ghi | Toàn bộ thời gian chậm của request |

Muốn ước lượng allocation **rate**, cần có thời gian thu và phép tổng hợp/statistical estimator phù hợp. Muốn gán áp lực allocation cho **call site**, cần stack attribution. Muốn xác định leak, phải phân tích object retention.

### Lưu ý về khác biệt kích thước

`new byte[16384]` có payload 16.384 byte nhưng trên heap còn có header, alignment và chi phí layout; `size` của object theo JVM có thể lớn hơn payload. Số size cụ thể thay đổi theo runtime và layout. Không viết test kỳ vọng `size == array.length`.

### Đừng tự chia số event cho số threads

Mỗi thread có mô hình sampling riêng, nhưng tổng áp lực còn phụ thuộc khối lượng allocations và thời gian hoạt động. Nếu cần so sánh thread A/B, phân tích thời gian quan sát, sampling interval, threads mới tạo/kết thúc và worker context. Một thread làm ít việc nhưng có nhiều objects cỡ lớn có thể sinh samples khác với thread tạo nhiều objects nhỏ.

## 14. Kiểm thử theo thuộc tính thay vì số lượng cố định

| Test case | Cách thực hiện | Tiêu chí hợp lệ |
| --- | --- | --- |
| JVM có capability | Chạy agent mẫu | GetPotentialCapabilities/AddCapabilities/GetCapabilities thành công |
| JVM không có capability | Chạy trên runtime không hỗ trợ | Báo UNSUPPORTED rõ; không giả tạo samples |
| Callback được bật | Agent đăng ký đúng event 86 | Có samples trong workload đủ lớn trên VM được hỗ trợ |
| Interval lớn hơn | Chạy ở staging với 4 MB | Số samples thường thưa hơn, không có tỷ lệ cố định |
| Interval nhỏ hơn | Chạy staging với 64 KB | Overhead có thể tăng; số mẫu thường nhiều hơn |
| Interval 0 | Chỉ thử ở môi trường cô lập | Biết là rất tốn chi phí, **không dùng production** |
| Java 11 JFR registry | Chạy AllocationEventAvailability | Không giả định `jdk.ObjectAllocationSample` xuất hiện |
| Java 17+ JFR registry | Chạy AllocationEventAvailability | Quan sát event thực tế của runtime |
| JFR sample recording | Chạy JfrAllocationSampleDemo | File tạo nếu event có; không đòi sample count cố định |
| Heap leak | So sánh live objects qua thời gian | Không chỉ dựa trên callbacks khi cấp phát |

**Điều kiện QA cốt lõi** là khả năng hỗ trợ được phát hiện đúng, agent không bỏ qua errors, workload thực sự tạo allocations và báo cáo ghi rõ **sample/estimated**, không gắn mác số đếm chính xác.

## 15. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Java 11 tức là mọi JVM có SampledObjectAlloc” | Optional JVMTI capability | Probe trên runtime và phase thực |
| Dùng `recording.enable("SampledObjectAlloc")` | Nhầm JVMTI với JFR | Chọn đúng event namespace |
| Dùng `SetHeapSamplingInterval(0)` để disable | 0 có nghĩa sample mỗi allocation hỗ trợ | `SetEventNotificationMode(JVMTI_DISABLE,...)` |
| Coi interval là thời gian | Nó là byte allocation trung bình | Ghi đơn vị bytes |
| Coi callback được gọi đúng mỗi 512 KB | Sampling bán ngẫu nhiên, theo thread | Đánh giá thống kê |
| Cộng `size` rồi coi total allocated | Chỉ là size của sampled objects | Dùng estimator đúng |
| Dùng `VMObjectAlloc` để đếm mọi `new` | Event có phạm vi khác | Chọn SampledObjectAlloc nếu capability hỗ trợ |
| Giữ `jobject` trong biến global từ callback | JNI local ref không có vòng đời global | Dùng reference management hợp lệ |
| Log mọi sampled allocation | Overhead và có thể tạo thêm allocations | Buffer/aggregate gọn, hạn mức |
| Cập nhật counter `long` không đồng bộ | Callback có thể chạy ở nhiều threads | Atomics/thiết kế thread-safe |
| Coi sample nghĩa là object còn sống | Event lúc allocation | Dùng retained analysis nếu nghi leak |
| Chạy native agent không kiểm chứng | Agent có quyền mạnh, có thể crash JVM | Dùng agent tin cậy, staging trước |
| Nghĩ Agent_OnLoad tự attach vào JVM live | OnLoad chỉ khởi động | Attach cần entrypoint/permission khác |
| Nghĩ JDK 11 JFR có jdk.ObjectAllocationSample | Event JFR từ JDK 16 | Dùng JDK11 TLAB events hoặc JVMTI |
| Không thấy sample nghĩa không có allocation | Có thể event chưa bật, sampling thưa | Kiểm tra support/config/workload |

## 16. Checklist triển khai production

- [ ] Biết JVM vendor, build, Java feature/update, GC, container/OS.
- [ ] Kiểm tra `can_generate_sampled_object_alloc_events` ở phase cần dùng.
- [ ] Xác nhận `AddCapabilities` và `GetCapabilities` thành công.
- [ ] Đặt interval bằng bytes hợp lý, đo overhead trên workload thật.
- [ ] Bật đúng `JVMTI_EVENT_SAMPLED_OBJECT_ALLOC`.
- [ ] Callback xử lý thread-safe, ngắn, không log secret/object contents.
- [ ] Không giữ JNI local reference quá vòng đời callback.
- [ ] Có window, rate limiter, buffer/exporter và chính sách stop profiling.
- [ ] Có fallback khi capability không hỗ trợ, không làm mất service.
- [ ] Phân biệt JVMTI samples với JFR events/schema/weights.
- [ ] Không dùng sample size làm thống kê live heap hoặc tổng cấp phát chính xác.
- [ ] Bảo vệ file profiling/heap dumps và giới hạn truy cập.
- [ ] Khi nghi leak, kết hợp retained heap analysis.

## 17. Câu hỏi tự luyện

**1.** `SampledObjectAlloc` thuộc JVMTI hay JFR? Có từ Java nào?

**2.** Tại sao `java -version` không đủ để xác nhận JVM hỗ trợ nó?

**3.** Capability cần xin tên gì? Ba hàm liên quan đến quyền là gì?

**4.** Khoảng sampling 524288 có bảo đảm mỗi event cách nhau đúng 524288 byte không?

**5.** `SetHeapSamplingInterval(0)` có tắt sampling không?

**6.** `size` trong callback có phải tổng memory allocation của Java heap không?

**7.** Số callback thấp có chứng minh ứng dụng không tạo object không?

**8.** JFR `jdk.ObjectAllocationSample` xuất hiện từ JDK mấy?

**9.** Code native có `Agent_OnLoad` và dùng `-agentpath` có attach vào JVM đang chạy không?

**10.** Nếu heap sau GC ổn định nhưng allocation sampling cao, có thể kết luận memory leak ngay không?

**Đáp án:** (1) JVMTI, Java 11/JEP331; (2) capability optional và khác vendor/phase; (3) `can_generate_sampled_object_alloc_events`, `GetPotentialCapabilities`/`AddCapabilities`/`GetCapabilities`; (4) không, sampling bán ngẫu nhiên trung bình; (5) không, 0 có chi phí cao; (6) không, chỉ object mẫu; (7) không; (8) JDK 16; (9) không, OnLoad chạy khi startup; (10) không, cần retained heap analysis.

## 18. Kết luận

**`SampledObjectAlloc` là sự kiện JVMTI từ Java 11, phục vụ low-overhead heap-allocation sampling (JEP331).** Nó khác JFR `jdk.ObjectAllocationSample` ra đời từ JDK16. Vì là optional capability, việc triển khai phải **kiểm tra ngay trên JVM mục tiêu**, cấp quyền hợp lệ, đặt interval theo byte và hiểu callback trả dữ liệu mẫu chứ không phải một bản thống kê heap chính xác. Khi JVM không hỗ trợ capability, chọn JFR events/profiler khác được kiểm chứng thay vì tự giả định hay cố bypass hạn chế runtime.

## Tài liệu chính thức và hiện hành

- [OpenJDK JEP 331 — Low-Overhead Heap Profiling (Java 11)](https://openjdk.org/jeps/331).
- [Oracle Java 11 — JVM TI Specification: Sampled Object Allocation, SetHeapSamplingInterval, Capabilities](https://docs.oracle.com/en/java/javase/11/docs/specs/jvmti.html).
- [Oracle JDK 11 Release Notes — JEP331](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html).
- [Oracle JDK 16 Release Notes — New jdk.ObjectAllocationSample JFR event](https://www.oracle.com/java/technologies/javase/16all-relnotes.html).
- [Java SE 11 — JFR FlightRecorder API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/FlightRecorder.html).
- [Java SE 11 — JFR Recording API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Java SE 11 — JFR RecordingFile API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- [OpenJDK JFR metadata — ObjectAllocationSample weight](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/jfr/metadata/metadata.xml).
