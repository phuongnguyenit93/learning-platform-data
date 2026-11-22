# Ranh giới lựa chọn Java Instrumentation, JVM TI, debugger và công cụ lấy mẫu

> **Ngữ cảnh:** Java Advance → Instrumentation → **Native và JVM TI**. Khi cần hiểu một JVM đang làm gì, không nên hỏi ngay “dùng Java agent hay debugger?”. Hãy xác định loại bằng chứng cần có: **mỗi lần một method được gọi**, **trạng thái của một thread tại một thời điểm**, **sự kiện cấp JVM**, hay **mẫu thống kê về nơi CPU/thời gian bị tiêu tốn**. Bốn nhóm công cụ — Java Instrumentation, JVM TI native agent, debugger qua JPDA và profiler/sampling tools — có các ranh giới khác nhau về mức kiểm soát, độ đầy đủ, độ xâm lấn và chi phí. Bài dùng Java 17+; phần Java agent và JFR đã được kiểm chứng với OpenJDK 24.

## 1. Khởi đầu bằng câu hỏi cần trả lời, không bằng tên công cụ

Hãy hình dung một dịch vụ Java đang chậm. Có ít nhất năm câu hỏi *rất khác nhau*:

1. **“Method `OrderService.pay()` chạy bao nhiêu lần, mỗi lần mất bao lâu và ném lỗi nào?”** Nếu cần đúng các invocation đã được instrument, đây thường là bài toán **Java bytecode instrumentation** hoặc application-level hooks/tracing.
2. **“Lúc lỗi xảy ra, biến `orderId` trong frame hiện tại là bao nhiêu, thread nào đang giữ lock?”** Đây là bài toán **debugger**; bạn muốn breakpoint, step, stack frame và inspect state trong một thời điểm cụ thể.
3. **“Cần nhận VM events cấp thấp, thao tác với class-loading hooks, thread/heap/JVM state hoặc một capability không được Java API bọc sẵn?”** Có thể cần **JVM Tool Interface (JVM TI)** native agent.
4. **“Phần lớn CPU đang được tiêu tại đâu, hàm nóng nào đáng tối ưu, allocation/lock/GC có liên quan không?”** Trước hết hãy dùng **profiler/JFR/sampling** có cấu hình thích hợp.
5. **“Có thể lấy dữ liệu đủ tin cậy trong production mà không dừng request hoặc sửa ứng dụng không?”** Đây là câu hỏi **chi phí và rủi ro vận hành**, không chỉ là vấn đề một API có tồn tại hay không.

Sai lầm phổ biến: dùng debugger để suy luận latency production, dùng sampling để “chứng minh một invocation đã chạy”, hoặc thêm transformer vào mọi method khi chỉ cần xác định hot path. Mỗi công cụ trả lời **một dạng câu hỏi riêng**.

### Bốn khái niệm cốt lõi

- **Instrumentation:** thay/bao bọc mã hoặc chèn probe vào đường chạy để nhận dữ liệu ở **điểm cụ thể**. Có thể là Java `ClassFileTransformer`, thư viện như ASM/Byte Buddy hoặc nguồn đã có hooks.
- **JVM TI:** giao diện native do JVM cung cấp cho các agent C/C++ truy vấn/điều khiển VM và nhận events; có những tính năng tùy capability/VM.
- **Debugger:** sản phẩm hoặc client cho phép breakpoint, stepping, inspect frame/local variable, tạm dừng/tiếp tục. Trong Java, kiến trúc chuẩn là **JPDA**: JDI ↔ JDWP ↔ VM back-end/JVM TI.
- **Sampling/profiling:** thu thập một tập **mẫu** stack/CPU/wall time/allocation, rồi suy luận phân bố hoạt động. Có thể có thêm các sự kiện JVM **không phải mẫu**, đặc biệt trong **Java Flight Recorder (JFR)**.

**Lưu ý tầng kiến trúc:** bốn nhóm này **không phải bốn giao diện độc lập, ngang hàng và loại trừ nhau**. Một debugger thường sử dụng JVM TI ở phía VM; một native profiler có thể dùng JVM TI; Java agent có thể kết hợp JFR; JFR không chỉ có sampling. Bảng bên dưới là ranh giới **lựa chọn giải pháp**, không phải phân loại “mỗi tool chỉ dùng duy nhất một công nghệ”.

## 2. Bảng quyết định nhanh

| Tiêu chí | Java Instrumentation | JVM TI native agent | Debugger / JPDA | Profiler / sampling (JFR, async-profiler...) |
|---|---|---|---|---|
| Điểm vào tiêu biểu | `-javaagent:agent.jar` / Java Attach nếu được phép | `-agentpath:/path/lib...` hoặc `-agentlib:name`, đôi khi native attach | IDE/`jdb`, JDWP local/remote | JFR startup/`jcmd`; profiler attach/start |
| Cấp API | Java `Instrumentation`, `ClassFileTransformer` | C/C++ `jvmti.h` và JNI | JDI client, JDWP transport, JVM back-end | JFR events/recordings; sampling native/JVM tùy công cụ |
| Dữ liệu mạnh nhất | Các execution points **đã chèn probe**: invocation, latency, argument/outcome theo thiết kế | VM events/state/capabilities cấp thấp, class load, threads, heap và nhiều VM hooks | Breakpoint, local variables, exact frame **khi dừng**, step/exception | Hot paths, CPU/wall/allocation distribution, GC/locks và timeline tùy profile |
| Độ bao phủ | Phụ thuộc classes/loader/timing, method đã instrument và retransform capability | Phụ thuộc VM/capabilities/phase và events được bật | Phụ thuộc debug symbols, thread suspension và debuggee state | Phụ thuộc sampling rate/event settings, thời lượng recording, khả năng stack walking |
| Tính đầy đủ | Có thể đếm **đúng các lời gọi đi qua probe**, nếu probe và đường lỗi chính xác | Sự kiện được bật và được VM phát; không mặc định mọi loại event có sẵn/nhẹ | Chính xác cho **trạng thái quan sát tại breakpoint**, không đại diện workload bình thường | **Thống kê**, không bảo đảm thấy mọi invocation hoặc thứ tự tuyệt đối |
| Chi phí | Thêm code vào hot path, allocations, logging, class-transform startup, retransform | Native lifecycle, callbacks, capability, lỗi native ảnh hưởng process; có event rất đắt | Pause/scheduling thay đổi đáng kể, có thể lộ dữ liệu/khóa thread | Thường phù hợp chẩn đoán rộng; overhead phụ thuộc settings, frequency, stack depth |
| Khi nên ưu tiên | Cần business-specific **per-call telemetry** dài hạn | Cần primitive VM không có ở Java API/công cụ cấp cao | Cần biết **vì sao một lần thực thi cụ thể sai** | Chưa biết hot spot; tối ưu CPU/memory/GC; production triage |
| Sai lầm chính | Tưởng instrument toàn VM và không overhead | Tưởng native == luôn nhanh/đầy đủ/an toàn | Tưởng breakpoint đại diện timing bình thường | Tưởng sample count == exact call count |

**Không có thứ tự “tốt nhất” tuyệt đối.** Một câu hỏi có thể bắt đầu với JFR để khoanh vùng, tiếp tục với Java instrumentation tại 2–3 methods quan trọng, và kết thúc bằng debugger để xác định biến gây lỗi trong một request tái hiện được. JVM TI thường là bước leo thang vì nhu cầu **đặc thù cấp VM**, không phải lựa chọn mặc định.

## 3. Java Instrumentation: khi cần probe có chủ đích vào Java code

API chính:

~~~java
public static void premain(String options,
                           java.lang.instrument.Instrumentation inst) {
    inst.addTransformer(transformer);
}
~~~

Đây là **mảnh minh họa**: cần một class entry point, manifest và biến `transformer` đã được định nghĩa. Agent JAR khai `Premain-Class` và JVM gọi `premain` trước `main`. Với agent được hỗ trợ nạp động, dùng `Agent-Class` và `agentmain`.

### API cho phép điều gì?

- Dùng `ClassFileTransformer.transform(...)` để nhận **class-file bytes** khi JVM định nghĩa hoặc redefine class; nếu đăng ký `canRetransform=true` và capability phù hợp, có thể được gọi khi retransform.
- Trả `null` để không thay đổi bytes; hoặc trả một **byte[] mới hợp lệ** chứa class code được instrument. Transformer **không phải callback “mỗi lần method được gọi”**. Callback của transformer xảy ra tại **class definition/redefinition/retransformation**; muốn bắt method invocation, phải **thực sự chèn probe vào thân method** hoặc dùng hook trong code ứng dụng.
- Có thể dùng `getAllLoadedClasses()`, `isModifiableClass()`, `retransformClasses(...)` khi cần thêm instrumentation cho class đã load, với capability và giới hạn schema tương ứng.
- Có thể hỗ trợ module access/search path bằng những API instrumentation chuyên dụng, nhưng không tự động vượt mọi rào cản loader/JPMS.

### Ranh giới không được bỏ qua

1. **Không mặc định tất cả class đã load sẽ được instrument.** Một transformer mới đăng ký không quay lại áp dụng tự động cho mọi class cũ. Cần tính thời điểm startup, retransform capability và `isModifiableClass`.
2. **Không thay đổi cấu trúc class tùy ý sau khi JVM định nghĩa.** Retransformation/redefinition không cho phép tự do thêm/bớt fields/methods hoặc đổi superclass, signature, những metadata như nest/record/sealed.
3. **Probe có overhead:** đo `System.nanoTime()`, tạo span, đọc arguments hoặc serialize payload trong hot path đều có giá. Một probe Java có thể nhanh nhưng không phải zero-cost.
4. **Đừng tự định nghĩa latency sai:** method trả `Future`/`CompletionStage` nhanh không có nghĩa tác vụ async đã hoàn tất. Muốn đo completion phải quan sát **đúng completion stage** hoặc producer work lifecycle.
5. **Đường lỗi cũng là một outcome:** bytecode instrumentation cần xử lý normal return, exception, nested calls, async context propagation, class loaders và recursion guards.
6. **Đúng class identity:** cùng binary name được hai defining loaders khác nhau định nghĩa là hai class khác nhau. Bootstrap target không tự nhìn thấy system-only helper.
7. **Không sử dụng bytecode rewriting như một debugger giả:** method probe liên tục không thay thế khả năng dừng ở một dòng và xem local variables hiện tại.

### Chọn Java agent khi nào?

Dùng khi câu hỏi đòi hỏi **định lượng business execution path** như exact count những call đi qua method đã instrument, duration per invocation, tags ổn định, exception outcomes; khi đã biết những điểm cần đo và muốn thu thập dài hạn. Một agent tích hợp vào APM/tracing có thể cung cấp dữ liệu hữu ích hơn stack samples đối với giao dịch cụ thể. Ngược lại, nếu **chưa biết chỗ nào nóng**, instrument tất cả methods là phương pháp dễ tạo overhead và dữ liệu nhiễu.

## 4. JVM TI: khi thực sự cần điểm điều khiển cấp VM

**JVM Tool Interface (JVM TI)** là native API phục vụ công cụ debug, profiling, monitoring và VM state/control. Native agent thường dùng `Agent_OnLoad`, gọi `JavaVM.GetEnv(..., JVMTI_VERSION_...)` để nhận `jvmtiEnv*`, xin capability rồi đăng ký callbacks/enable events.

~~~text
Native shared library (C/C++)
  └─ Agent_OnLoad(JavaVM*, char* options, void*)
       └─ GetEnv(... JVMTI_VERSION_1_2 ...)
            ├─ GetPotentialCapabilities / AddCapabilities (nếu cần)
            ├─ SetEventCallbacks (chỉ những callback có mục đích)
            ├─ SetEventNotificationMode(JVMTI_ENABLE, ...)
            └─ event callbacks trong VM/thread context
~~~

Cơ chế phổ biến là chạy:

~~~text
java -agentpath:/absolute/path/to/native-agent-library ... Main
~~~

Đây là **cú pháp mẫu**, không phải một thư viện đã được build trong bài. Trên Windows, path dùng định dạng hệ điều hành phù hợp; với `-agentlib:shortName` JVM tìm native library theo native library search rules. Nếu cần C/C++, phải compile đúng ABI/architecture cho JVM, có JDK headers `jni.h`, `jvmti.h` và toolchain tương ứng.

### Một số việc JVM TI có thể hỗ trợ

- **VM/class lifecycle:** `ClassFileLoadHook`, class load/prepare, VM init/death.
- **Thread và execution:** một số events `MethodEntry`, `MethodExit`, `Breakpoint`, `SingleStep`, exceptions, monitor contention; tùy capability.
- **Heap/memory:** VM object allocation events, sampled allocation events, heap inspection theo API/capability.
- **Runtime state/control:** stack frames, threads, class/method metadata, class retransform/redefine, tùy trạng thái VM và capabilities.

**Quan trọng:** một số capabilities là **optional**, không phải VM/JDK nào cũng hỗ trợ. JVM TI có **phases** (onload, start, live, dead); nhiều functions chỉ hợp lệ ở phase thích hợp. Tài liệu JVMTI nêu rõ agents phải kiểm tra return code `jvmtiError`, capabilities và callback safety.

### Vì sao không dùng native JVM TI cho mọi bài toán?

- Agent native chạy **trong cùng process** JVM, có quyền mạnh và rủi ro lớn: null pointer, use-after-free, data race hoặc lỗi ABI có thể khiến JVM crash, chứ không chỉ ném Java exception.
- Một số callback chạy trên **application thread** ở ngữ cảnh nhạy cảm. Blocking, malloc, JNI calls hoặc logging nặng trong callback có thể làm chậm/đổi hành vi chương trình, thậm chí deadlock.
- `MethodEntry`/`MethodExit` ở quy mô toàn JVM có thể rất đắt; “sự kiện thật ở cấp thấp” không đồng nghĩa có overhead thấp hơn bytecode probes.
- Native agent phải quản lý **vòng đời, capability, thread safety, reentrancy, synchronization và GC/JNI references**. Không được để callback cũ sử dụng resource sau khi giải phóng.
- Một số native JVMTI agents cũng **biến đổi Java bytecode** qua `ClassFileLoadHook`. Điều này thể hiện các tầng có thể phối hợp, không phải hai cách tiếp cận hoàn toàn không giao nhau.

### Phác thảo C — chỉ để hiểu cấu trúc, không phải lab đã biên dịch

~~~c
#include <jni.h>
#include <jvmti.h>
#include <string.h>

static void JNICALL on_entry(jvmtiEnv *ti, JNIEnv *jni,
                              jthread thread, jmethodID method) {
    // Minh họa callback; không thực hiện I/O/blocking trên hot path.
    // Một agent thực tế phải xử lý state, reentrancy và overhead.
}

JNIEXPORT jint JNICALL Agent_OnLoad(JavaVM *vm, char *options, void *reserved) {
    jvmtiEnv *ti = NULL;
    jint rc = (*vm)->GetEnv(vm, (void **)&ti, JVMTI_VERSION_1_2);
    if (rc != JNI_OK || ti == NULL) return JNI_ERR;

    jvmtiCapabilities caps;
    memset(&caps, 0, sizeof(caps));
    caps.can_generate_method_entry_events = 1;
    if ((*ti)->AddCapabilities(ti, &caps) != JVMTI_ERROR_NONE)
        return JNI_ERR;

    jvmtiEventCallbacks callbacks;
    memset(&callbacks, 0, sizeof(callbacks));
    callbacks.MethodEntry = &on_entry;
    if ((*ti)->SetEventCallbacks(ti, &callbacks, sizeof(callbacks))
            != JVMTI_ERROR_NONE)
        return JNI_ERR;

    if ((*ti)->SetEventNotificationMode(ti, JVMTI_ENABLE,
            JVMTI_EVENT_METHOD_ENTRY, NULL) != JVMTI_ERROR_NONE)
        return JNI_ERR;

    return JNI_OK;
}
~~~

Đây là **skeleton giáo dục**, **chưa compile/run trong bài** và callback cố ý không thu thập dữ liệu. Nó không có đầy đủ lifecycle/cleanup, không lọc method, không xử lý JNI pending exceptions và sẽ bật `MethodEntry` rộng nếu chạy — **không triển khai nguyên xi trong production**. Việc `AddCapabilities` có thể thất bại là một nhánh bình thường nếu VM không có capability yêu cầu. Trong native agent thật, mọi JVMTI call cần kiểm tra `jvmtiError` và phase.

**Chọn JVM TI khi:** một requirement rõ ràng bắt buộc native VM event/state/control mà Java `Instrumentation`, JFR hoặc debugger chuẩn chưa đáp ứng; đội ngũ có thể kiểm soát native ABI, JVM version, an toàn callback và vận hành. **Không chọn chỉ vì “JVM TI nghe có vẻ gần JVM hơn nên chính xác hơn”.**

## 5. Debugger: khi cần dừng đúng nơi và xem state

Java Platform Debugger Architecture (**JPDA**) có ba tầng:

~~~text
Debuggee JVM + JDWP back-end (thường dùng JVM TI)
       ⇅ Java Debug Wire Protocol (JDWP)
Debugger front-end dùng Java Debug Interface (JDI)
       ↓
IDE debugger / jdb / debugger client khác
~~~

Như vậy **debugger thường được xây trên các dịch vụ cấp JVM TI** ở VM side. Nó là một **workflow** để tìm lỗi cụ thể, không đơn giản là “một Java agent khác”.

### Debugger làm tốt điều gì?

- Đặt **breakpoint** theo line/method/exception.
- Tạm dừng một thread hoặc một tập threads theo suspend policy, sau đó xem call stack và giá trị locals/fields ở thời điểm đó.
- `step`/`next` để theo dõi nhánh code/logic; inspect trạng thái tại thời điểm lỗi; xem exception stack.
- Có thể dùng JDI để phát triển debugger custom mà không cần tự viết native JVM TI agent.

Nhưng có giới hạn:

- Breakpoint **thay đổi thời điểm thực thi và scheduling**. Thread bị dừng có thể giữ lock; thread khác tiếp tục/chờ; timeout của network/distributed systems có thể bị kích hoạt. Không nên dùng thời gian lúc breakpoint như latency bình thường.
- Debugger không tự tạo **phân bố thống kê workload**; chỉ thấy trạng thái ở những lần bạn dừng. Một thread đang ở method `slow()` lúc breakpoint không chứng minh đó là hot path lớn nhất.
- Locals phụ thuộc **debug information, JIT optimizations, phiên bản class và hỗ trợ JVM**. Không phải biến nào cũng luôn inspect được.
- JDWP mở bề mặt **điều khiển VM**; không để debug port lắng nghe công khai trên production. Cần loopback/ACL/tunnel, xác thực và chính sách của môi trường. Lộ debug port có thể dẫn đến truy cập/điều khiển process không mong muốn.

### Bài thử `jdb` gắn với ví dụ ở phần 9

Sau khi biên dịch ứng dụng, dùng:

~~~bash
jdb -classpath out/app demo.app.DecisionDemo
~~~

Trong prompt của `jdb`:

~~~text
stop in demo.app.DecisionDemo$Work.compute
run
where
cont
exit
~~~

Tùy trạng thái breakpoint, `where` cần được gọi **khi thread đang dừng** để in stack thích hợp. `jdb` có thể báo breakpoint deferred khi nested class chưa được load; đó là bình thường. **Không có stdout cố định** cho một phiên debug tương tác: breakpoints, source line, thread IDs và lệnh `where` tùy JVM/JDK/debug information. Nếu thấy class not found, xác nhận `-classpath out/app` và tên binary class gồm ký tự `$`.

### Debugger từ xa: chỉ loopback khi tự học

Ví dụ khởi chạy JVM ở trạng thái chờ debugger:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out/app demo.app.DecisionDemo
~~~

Sau đó mở terminal thứ hai:

~~~bash
jdb -attach 127.0.0.1:5005
~~~

Đây là các lệnh **minh họa kết nối**, không phải phần script tự động có stdout cố định. Cổng phải **chưa được sử dụng**, và target JVM sẽ **tạm dừng trước khi chạy main** cho đến khi debugger kết nối/tiếp tục. Chỉ dùng localhost ở lab; **không** chuyển `address=127.0.0.1:5005` thành wildcard `address=*:5005` nếu không hiểu rủi ro bảo mật, nhất là trên server.

**Chọn debugger khi:** bạn tái hiện được một lỗi, cần examine chính xác object/stack tại một điểm, làm unit-level debugging hoặc kiểm tra nhánh exception. **Không chọn** để lấy p99 production latency hoặc số lượng method calls trong nhiều giờ.

## 6. Sampling/profiling: trước hết để tìm điểm nóng

**Sampling** nghĩa là quan sát một số thời điểm/sự kiện theo chu kỳ hoặc quy tắc chọn mẫu, rồi ước lượng phân bố. Ví dụ 65% samples chứa `OrderService.calculate` ở stack có thể gợi ý method đó đang chiếm phần đáng kể **thời gian được đo theo chế độ sampling**, nhưng **không** chứng minh 65% request gọi method đó, hoặc method đó chạy đúng 65% tổng số milliseconds.

### Đặt câu hỏi đúng về loại samples

| Chế độ | Đo thứ gì? | Không chứng minh |
|---|---|---|
| **CPU sampling** | Stack ở các mẫu liên quan đến CPU execution/hot code | Exact invocation count, wall time của từng request, mọi blocking wait |
| **Wall-clock sampling** | Stack theo thời gian trôi qua, có thể gồm threads chờ tùy công cụ/cấu hình | CPU utilization thuần túy, thứ tự xảy ra của từng event |
| **Allocation sampling** | Nơi có allocation với thống kê mẫu/threshold | Mỗi object đã được tạo, lifetime/leak chỉ từ một mẫu |
| **Lock/GC/IO events** trong JFR | Sự kiện có cấu hình và threshold tương ứng | Mọi event đều là sampling; hoặc file recording luôn có mọi event |

**Quan trọng về JFR:** Java Flight Recorder là **event recorder** của JDK, không chỉ là CPU sampler. Nó có cả stack samples như `jdk.ExecutionSample` lẫn events về GC, class loading, locks, sockets, allocation và nhiều metric khác, tùy configuration. **Không hứa mọi events đều có mặt**: một số bị disabled, threshold/filter, hoặc không phát sinh trong recording window.

### JFR: điểm bắt đầu tốt cho nhiều ca production

JDK cung cấp:

- `-XX:StartFlightRecording=...` — khởi động JFR cùng JVM.
- `jcmd <PID> JFR.start ...`, `JFR.check`, `JFR.dump`, `JFR.stop` — điều khiển recording trong JVM đang chạy, nếu attach/diagnostic commands được phép.
- `jfr summary file.jfr` — liệt kê các loại event/số lượng.
- `jfr print --events jdk.ExecutionSample file.jfr` — xem CPU execution samples, nếu cấu hình đã ghi event loại đó.
- JDK Mission Control hoặc công cụ phân tích tương ứng để xem timeline, flame graph và event relationships.

JFR có hai cấu hình dựng sẵn:

- **`default.jfc`:** phù hợp ghi lâu dài, cân bằng chi phí và lượng dữ liệu.
- **`profile.jfc`:** thu thập phong phú hơn, hữu ích khi profiling thời gian ngắn; **có thể tăng overhead**.

Không tuyên bố overhead của JFR luôn đúng một con số trong mọi workload. Sampling period, enabled events, stack depth, allocation thresholds, JDK, dữ liệu và tải máy đều ảnh hưởng độ chính xác lẫn chi phí.

### async-profiler và công cụ sampling khác

Một profiler chuyên dụng như **async-profiler** có các chế độ CPU, wall-clock, allocation và nhiều cơ chế lấy mẫu stacks của Java/native code tùy nền tảng. Trên Linux, chế độ CPU có thể dựa vào OS `perf_events` phối hợp stack Java; cách lấy stack và độ bao phủ native frames phụ thuộc công cụ/OS/quyền runtime. Đây là **công cụ bên thứ ba, không phải Java SE API**.

Dùng profiler chuyên dụng khi bạn cần phân tích CPU/native/wall/alloc sâu hơn, so sánh flame graphs hoặc giảm thiên lệch của phương pháp chỉ đợi thread tới safepoint. Nhưng **profiler cũng là sampling**: không dùng nó làm chứng cứ chính xác rằng một transaction cụ thể đã gọi method `X` bao nhiêu lần.

### Vì sao debugger stack hoặc một lần `jstack` không phải profiler?

Một thread dump là **ảnh chụp** của thread states/stacks tại một thời điểm. Nó hữu ích để chẩn đoán deadlock, blocked threads, thread pools, nhưng một snapshot không tạo ra phân bố thống kê đáng tin cho một giờ workload. Có thể lấy nhiều samples theo thiết kế, nhưng đừng nhầm `Thread.print` chạy một lần với CPU sampling có interval, chọn mẫu, aggregation và thống kê.

**Chọn JFR/sampler khi:** chưa biết bottleneck ở đâu; cần xem CPU, allocation, GC, lock, timeline/hot paths trong workload thực, đặc biệt khi không muốn suspend application bằng debugger. Sau khi khoanh vùng, mới thêm instrumentation chính xác nếu cần đếm/đo per-invocation.

## 7. Chọn công cụ bằng tình huống

| Tình huống | Khởi đầu hợp lý | Nếu còn thiếu |
|---|---|---|
| p99 request tăng nhưng không biết vì sao | JFR `profile.jfc` ngắn hoặc profiler có cấu hình thích hợp | Java instrumentation/tracing vào endpoint, dependency, async completion |
| Muốn số lần gọi `charge()` và exception rate chính xác theo request | Java Instrumentation tại điểm method/business span | App metrics/hook tại boundary; JFR để điều tra CPU |
| Deadlock, thread bị BLOCKED, starvation | `jcmd Thread.print` / JFR lock events | Debugger trong lab tái hiện; JVM TI nếu cần hook cấp thấp |
| Bug chỉ khi `customerId` cụ thể làm nhánh logic sai | Debugger với breakpoint/conditional breakpoint | Thêm log có kiểm soát hoặc method probe nếu không tái hiện |
| Cần native heap/thread/VM event mà Java API không có | Kiểm tra JVM TI capabilities | Viết native JVMTI agent khi thật sự cần |
| CPU cao nhưng dashboard request latency thấp | CPU sampling trước để tìm hot stack | Kiểm tra GC, contention, executor và phân biệt CPU/wall |
| Async method trả `CompletableFuture` sớm | Instrument method return **và stage completion** | Worker/executor hook để đo queue/runtime thật |
| Muốn tìm allocation hot spots và GC pressure | JFR allocation/GC hoặc allocation profiler | Heap dump/retained size analysis nếu nghi leak |
| Chỉ muốn biết process có sống và thread nào đang chạy | `jcmd Thread.print`/health metrics | Không cần native agent hoặc debugger |
| Cần inspect native+Java execution rất sâu | Profiler phù hợp/async-profiler; cân nhắc JVM TI nếu yêu cầu đặc biệt | Phân tích native stack, symbols, OS permissions |
| Production bị giới hạn attach/debug | JFR bật từ startup hoặc metrics có sẵn | Cấu hình qua deployment, không tìm cách bypass chính sách |
| Test instrumentation có đúng class loader không? | Java agent logging ở transform callback, test class identity | `getAllLoadedClasses`/retransform phù hợp; JVM TI khi Java API thiếu |

### Quy trình leo thang ít xâm lấn

~~~text
Đặt câu hỏi / SLO / symptom
           |
           v
Dữ liệu có sẵn? metrics, logs, spans, thread dump
           |
           v
JFR / sampling có cấu hình và thời lượng hợp lý
           |
           +--- Đã tìm ra hot path? ----> thêm Java probe có chủ đích
           |                                  |
           |                                  +--- Cần inspect một lần lỗi? -> debugger (lab)
           |
           +--- Yêu cầu primitive VM đặc thù? -> đánh giá JVM TI capability,
                                                 ABI và chi phí native agent
~~~

**Ngoại lệ có lý do:** nếu bạn đang phát triển debugger thì chọn JDI ngay. Nếu một requirement native-only đã rõ, không bắt buộc đi qua JFR chỉ để hoàn thành quy trình. Ý chính là **không leo thang mức xâm lấn trước khi nhu cầu được chứng minh**.

## 8. Ranh giới về độ chính xác, overhead và an toàn

### “Có sự kiện” khác “đo đúng tất cả”

**Instrumentation** có thể ghi chính xác **các invocation của những method thực sự được instrument** và những đường điều khiển đã được probe bao phủ. Nó không phải định lý cho mọi JVM method vì nhiều class có thể đã load, bị loại trừ, nằm ở bootstrap/custom loader hoặc không modifiable.

**JVM TI events** đến từ VM khi capability/event được kích hoạt; mỗi loại event có semantics riêng. Một số events gửi trên application thread, yêu cầu callback an toàn. Nếu agent không enable event hoặc VM không có capability, không có dữ liệu.

**Debugger** nhìn thấy trạng thái thật của thread/frame khi breakpoint được xử lý, nhưng thao tác dừng có thể làm thay đổi vấn đề đang đo. Lỗi race đôi khi biến mất dưới debugger do lịch chạy thay đổi (*Heisenbug*).

**Sampling** cho ước lượng phân bố, thường dùng stack attribution. Nó không bảo đảm nhìn thấy method ngắn, request hiếm hoặc sự kiện xảy ra giữa hai lần lấy mẫu. Một sample stack cũng có thể chịu sai lệch do JIT, stack walking, interval và thread eligibility.

### Ảnh hưởng tới production

| Tác động | Instrumentation | Native JVM TI | Debugger | Sampling/JFR |
|---|---|---|---|---|
| Startup / class loading | Có khi premain/transform nhiều class | Có khi native agent init/hooks | Có thể có khi bật JDWP | Có khi khởi động JFR hoặc attach profiler |
| Hot path | Probe chèn làm tăng chi phí mỗi lần đi qua | Callback/event có thể rất lớn nếu enable rộng | Breakpoint gây suspend đáng kể | Chi phí thống kê phụ thuộc rate/events |
| Phạm vi dữ liệu nhạy cảm | Argument/result/payload từ probes | VM memory, heap, thread state | Locals, heap, object state, remote control | Stacks, method names, thread/events, có thể chứa dữ liệu |
| Rủi ro hệ thống | Verify/linkage lỗi, recursion/locks | **Native crash**/lỗi JNI/VM state, không chỉ exception | Dừng request/lock, debug port security | Disk buffers, overhead, attach permission, độ phân giải thống kê |
| Khả năng rollback | Remove transformer không hoàn tác bytecode đã cài | Phụ thuộc từng event/VM capability | Detach/resume không đảo side effects do debug | Stop recording không thay code, nhưng không xóa dữ liệu đã thu |

**Không có công cụ nào là “zero overhead” tuyệt đối.** Benchmark nên kiểm tra throughput, p50/p95/p99, GC, allocations, JIT warmup và logs trước/sau trong workload đại diện. Đặc biệt đừng lấy latency khi debugger đang suspend để kết luận sản xuất chậm bao nhiêu.

### An toàn truy cập

- Với Java agent/JVM TI, native hoặc bytecode có thể có đặc quyền rất lớn trong process. Chỉ chạy agent đáng tin, kiểm soát JAR/native-library integrity và deployment flags.
- Với JDWP, **không expose debug listener ra Internet**. Bind loopback, dùng tunnel/ACL và theo chính sách vận hành; debugger có thể inspect và thay đổi process state.
- Với JFR/profiler, review ai có quyền attach, đọc .jfr và xem method names, stacks, class names hoặc dữ liệu ứng dụng. Recording là artifact cần bảo vệ.
- Trong môi trường không cho attach, tôn trọng chính sách; có thể dùng JVM startup flags/observability đã cấu hình sẵn, không tự tìm cách vượt hạn chế.

## 9. Bài lab chạy được: Java Instrumentation và JFR nhìn cùng một chương trình

Mục tiêu: cùng một app CPU-bound, thấy **sự kiện xác định lúc class được transform** từ Java agent và **stack samples** từ JFR. Đây là so sánh “mốc cụ thể” với “bằng chứng thống kê”, **không** tuyên bố agent log đã biến đổi bytecode.

### 9.1 Cấu trúc thư mục

~~~text
tool-choice-lab/
├── manifest.mf
├── src/
│   └── demo/
│       ├── agent/
│       │   └── ChoiceAgent.java
│       └── app/
│           └── DecisionDemo.java
└── out/
    ├── agent/
    ├── app/
    └── choice-agent.jar
~~~

Cần **JDK 17+**, có `java`, `javac`, `jar`, `jfr`. Nếu dùng debugger thì thêm `jdb`. Chạy các lệnh tại thư mục gốc `tool-choice-lab/`.

### 9.2 Java agent — `src/demo/agent/ChoiceAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ChoiceAgent {
    private ChoiceAgent() {}

    public static void premain(String options, Instrumentation instrumentation) {
        System.out.println("[AGENT] premain");

        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String className, Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain, byte[] classfileBuffer) {
                if ("demo/app/DecisionDemo$Work".equals(className)) {
                    System.out.println("[AGENT] transform=" + className);
                }
                return null;
            }
        });
    }
}
~~~

Ý nghĩa:

- JVM gọi `premain` trước app `main`.
- Transformer được đăng ký **một lần**, chỉ log khi JVM định nghĩa class có internal name `demo/app/DecisionDemo$Work`.
- `return null` nghĩa là **không sửa bytecode**; dấu mốc `[AGENT] transform=...` **không phải** dấu mốc method invocation.
- `DecisionDemo$Work` là nested static class của app, được load khi app lần đầu dùng nó sau `[APP] begin`. Đây là lý do log xuất hiện đúng vị trí trong thử nghiệm.
- `"literal".equals(className)` tránh null pointer khi callback truyền tên null.
- Không dùng `System.out.println` trong transformer production khi có hàng nghìn classes: logging trên đường class loading có thể làm chậm JVM, tạo recursive class loading và lock contention.

### 9.3 App — `src/demo/app/DecisionDemo.java`

~~~java
package demo.app;

public final class DecisionDemo {
    private static volatile long checksum;

    public static void main(String[] args) {
        System.out.println("[APP] begin");
        checksum = Work.compute();
        System.out.println("[APP] checksumPositive=" + (checksum > 0));
        System.out.println("[APP] end");
    }

    static final class Work {
        static long compute() {
            long total = 0;
            for (int round = 0; round < 10; round++) {
                for (int i = 0; i < 20_000_000; i++) {
                    total += i % 7;
                }
            }
            return total;
        }
    }
}
~~~

Đây là **công việc CPU nhân tạo có kết quả xác định**. `checksum` là field `volatile` để kết quả công việc được dùng và in ra; giá trị chi tiết không phải trọng tâm, nên chỉ in điều kiện `> 0`. Khối CPU được chạy một lần và app kết thúc; thời gian thực tế sẽ khác theo CPU/JIT/JVM, do đó ví dụ không hard-code milliseconds.

### 9.4 Agent manifest — `manifest.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ChoiceAgent

~~~

Cần newline và dòng trống kết thúc manifest. Mẫu này **không** dùng `Agent-Class` hay `Can-Retransform-Classes` vì không attach động và không retransform class đã load.

### 9.5 Build trên macOS/Linux

~~~bash
mkdir -p out/agent out/app
javac --release 17 -d out/agent src/demo/agent/ChoiceAgent.java
javac --release 17 -d out/app src/demo/app/DecisionDemo.java
jar --create --file out/choice-agent.jar --manifest manifest.mf -C out/agent .
~~~

Build trên **Windows PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app | Out-Null
javac --release 17 -d out/agent src/demo/agent/ChoiceAgent.java
javac --release 17 -d out/app src/demo/app/DecisionDemo.java
jar --create --file out/choice-agent.jar --manifest manifest.mf -C out/agent .
~~~

Kiểm tra `jar --list --file out/choice-agent.jar` thấy `META-INF/MANIFEST.MF` và `demo/agent/ChoiceAgent.class` (cùng anonymous transformer class). Dùng `--release 17` để class files/API tương thích Java 17+.

### 9.6 Chạy không agent

~~~bash
java -cp out/app demo.app.DecisionDemo
~~~

**Stdout đã kiểm chứng trên OpenJDK 24:**

~~~text
[APP] begin
[APP] checksumPositive=true
[APP] end
~~~

Không có Javaagent nên không có `premain` hoặc transformer callback. App chạy bình thường.

### 9.7 Chạy với Java Instrumentation

**Bash:**

~~~bash
java -javaagent:out/choice-agent.jar -cp out/app demo.app.DecisionDemo
~~~

**Windows PowerShell:**

~~~powershell
java "-javaagent:out/choice-agent.jar" -cp out/app demo.app.DecisionDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
[AGENT] premain
[APP] begin
[AGENT] transform=demo/app/DecisionDemo$Work
[APP] checksumPositive=true
[APP] end
~~~

Đọc log:

- `[AGENT] premain`: JVM gọi startup agent trước ứng dụng.
- `[APP] begin`: app đã vào main.
- `[AGENT] transform=...`: JVM định nghĩa nested class; transformer quan sát một **class file load event**.
- `[APP] checksumPositive=true`: CPU work đã hoàn tất và kết quả được dùng.
- `[APP] end`: app kết thúc.

**Điều không được suy ra:** vì thấy một callback transform, không có nghĩa `Work.compute()` chỉ chạy một lần theo thống kê của agent. Transformer log theo **class definition**, không theo method call. Ở phiên bản app này thực tế `compute()` được gọi một lần là do **source code của app**, không phải thứ transformer chứng minh.

### 9.8 Chạy với JFR (không cần Java agent)

**Bash:**

~~~bash
java -XX:StartFlightRecording=filename=choice.jfr,settings=profile,dumponexit=true -cp out/app demo.app.DecisionDemo
~~~

**PowerShell:**

~~~powershell
java "-XX:StartFlightRecording=filename=choice.jfr,settings=profile,dumponexit=true" -cp out/app demo.app.DecisionDemo
~~~

JVM ghi `choice.jfr` vào working directory khi process kết thúc, nếu runtime hỗ trợ JFR. Bạn có thể thấy một vài dòng log `[jfr,startup]` trước ba dòng `[APP]`. **Không hard-code** PID, timestamp, recording ID, sample count hoặc số bytes của file vào expected stdout: những giá trị này phụ thuộc JDK và máy.

Xem thống kê và một số CPU samples:

~~~bash
jfr summary choice.jfr
jfr print --events jdk.ExecutionSample --stack-depth 5 choice.jfr
~~~

Một event mẫu có cấu trúc **tương tự** (timestamp và thread ID thay đổi):

~~~text
jdk.ExecutionSample {
  startTime = ...
  sampledThread = "main" (...)
  state = "STATE_RUNNABLE"
  stackTrace = [
    demo.app.DecisionDemo$Work.compute() ...
    demo.app.DecisionDemo.main(String[]) ...
  ]
}
~~~

Trong lần chạy kiểm chứng, file `choice.jfr` được tạo; `jfr summary` liệt kê `jdk.ExecutionSample` và `jfr print` có mẫu stack liên quan đến `Work.compute()`. **Không có guarantee một chương trình ngắn sẽ luôn có sample đúng method đó**; interval và workload thời lượng ngắn có thể bỏ qua một số frames. Có thể tăng số vòng chạy hoặc độ dài recording khi thử, đồng thời không thay đổi ý nghĩa thống kê.

### 9.9 Có thể bật cả Java agent lẫn JFR

**Bash:**

~~~bash
java -XX:StartFlightRecording=filename=combined.jfr,settings=profile,dumponexit=true -javaagent:out/choice-agent.jar -cp out/app demo.app.DecisionDemo
~~~

**PowerShell:**

~~~powershell
java "-XX:StartFlightRecording=filename=combined.jfr,settings=profile,dumponexit=true" "-javaagent:out/choice-agent.jar" -cp out/app demo.app.DecisionDemo
~~~

Kiểm chứng thực tế trên OpenJDK 24:

- Stdout vẫn có `[AGENT] premain`, `[APP] begin`, `[AGENT] transform=demo/app/DecisionDemo$Work` và kết thúc bình thường.
- JVM phát các dòng `[jfr,startup]` riêng, thay đổi theo runtime.
- File `combined.jfr` được tạo.
- `jfr print --events jdk.ExecutionSample --stack-depth 2 combined.jfr` cho thấy ít nhất một sampled stack gồm `Work.compute()` và `DecisionDemo.main(...)` trong môi trường kiểm chứng.

Như vậy **hai cơ chế bổ sung nhau**: Java agent log một điểm class-loading chính xác; JFR ghi nhiều events/samples để nhìn phân bố thực thi. Đừng cộng “1 transform callback” với “N execution samples” như hai bộ đếm cùng đơn vị.

### 9.10 JFR với JVM đang chạy bằng `jcmd`

Khi JVM còn chạy và bạn biết PID, JDK cung cấp lệnh:

~~~bash
jcmd -l
jcmd 12345 JFR.start name=triage settings=profile duration=30s filename=triage.jfr
jcmd 12345 JFR.check
~~~

`12345` là **PID minh họa**, phải thay bằng PID thực của tiến trình; đừng chạy nguyên giá trị đó. Lệnh `JFR.start` yêu cầu recording trong **30 giây**, file `triage.jfr` thường được ghi **khi recording dừng** sau duration, không nhất thiết tồn tại ngay khi `JFR.start` trả về. Sau khi có file, dùng `jfr summary triage.jfr` để xem events.

Nếu muốn lấy snapshot giữa lúc đang recording mà không dừng recording:

~~~bash
jcmd 12345 JFR.dump name=triage filename=triage-snapshot.jfr
~~~

Một snapshot hiện thời có thể khác recording cuối cùng. Quyền attach và cùng-user/OS policy có thể hạn chế lệnh; không suy ra thiếu support JFR từ một lỗi attach.

**Không dùng process ngắn của mục 9.6 để thử attach sau khi app đã thoát.** Muốn kiểm tra `jcmd` cần app còn sống đủ lâu, hoặc một dịch vụ đã chạy. Các lệnh `jcmd` ở đây là hướng dẫn tương tác, không phải thao tác đã thực hiện trên một PID production.

### 9.11 Debugger và Java agent có thể cùng xuất hiện

Có thể debug ứng dụng `DecisionDemo` bằng `jdb` như mục 5, đồng thời dùng Java agent hoặc JFR. Tuy nhiên khi debugger dừng thread tại breakpoint, **sampling và durations có thể bị thay đổi đáng kể**. Tránh so sánh hai kết quả performance “có debugger” và “không debugger” như thể cùng điều kiện.

## 10. Không đồng nhất các loại mốc trong dashboard

Những metric sau là các đối tượng đo **khác nhau**:

| Tên metric hợp lý | Nguồn | Định nghĩa |
|---|---|---|
| `class_transform_count` | Java transformer | Số class-file transform callbacks khớp bộ lọc |
| `method_invocation_count` | Probe chèn trong method | Số invocation **đã đi qua probe** |
| `method_duration_nanos` | Entry/exit probe | Duration của method theo semantics đồng bộ |
| `async_stage_completion_latency` | Listener completion của stage trả về | Duration tới lúc callback quan sát terminal outcome; không mặc định worker đã dừng sau cancel |
| `jfr_execution_sample_count` | JFR | Số samples đã ghi trong recording window |
| `jvmti_method_entry_event_count` | JVM TI nếu bật | Số events được VM phát và agent nhận theo capability/filter |
| `debugger_breakpoint_hit_count` | Debugger | Số lần breakpoint bị chạm trong phiên debug |

Ví dụ nếu JFR ghi 12 samples có `Work.compute`, điều đó **không** có nghĩa `Work.compute` được gọi 12 lần. Ngược lại, một transformer log class `Work` đúng một lần không nghĩa method của nó chỉ chạy một lần. Đối với method instrumentation, một callback ở **method entry** mới có khả năng đếm invocations, sau khi xử lý đầy đủ các trường hợp classload, inlining, exceptions và exclusion theo cách agent cấy probe.

### Khi đo async workload

Method trả `Future` không chứng minh task đã hoàn tất. Nếu cần latency end-to-end, phải:

1. Ghi mốc entry của API.
2. Ghi mốc method trả handle riêng.
3. Gắn listener vào **đúng `CompletionStage`** hoặc instrument producer/executor để ghi mốc completion thích hợp.
4. Phân biệt success, failure, cancellation và timeout; canceled promise có thể dừng trước khi underlying worker thật sự dừng.
5. Không gọi `future.get()`/`join()` ở method-exit probe chỉ để đợi completion: điều đó phá nonblocking semantics và có thể deadlock.

Một CPU sampler có thể nói “thời gian CPU nằm ở `Worker.run()`”; nó **không** thay thế business tracing để nối một task với request ID và completion outcome.

## 11. Sai lầm thường gặp và cách tránh

| Quan sát / đề xuất sai | Vì sao sai | Điều nên làm |
|---|---|---|
| “Cứ dùng JVM TI, gần VM nên nhanh nhất” | Native capabilities/events có overhead và crash risk | Chọn primitive cấp thấp **chỉ khi Java/JFR/JDI không đủ** |
| “`ClassFileTransformer` cho callback mỗi lần method được gọi” | Callback ở class definition/redefinition/retransform | Chèn code probe vào method hoặc dùng hook khác |
| “`retransformClasses` sẽ tự instrument mọi class đã load” | Phải chọn classes, capability, modifiable và bytes hợp lệ | Kiểm tra `isRetransformClassesSupported`, `isModifiableClass` và filters |
| “Debugger cho p99 latency chính xác” | Suspension thay đổi timing | Đo production bằng metrics/tracing/sampling, debug trong lab |
| “Một thread dump là một CPU profile” | Một thời điểm không cho phân bố | JFR/sampler có chu kỳ phù hợp |
| “5% samples nghĩa 5% requests gọi method” | Samples không đại diện số requests | Đếm invocation bằng probe/span |
| “JFR chỉ lấy mẫu CPU, không có events khác” | JFR ghi nhiều event types/thresholds | Chọn `default.jfc`/`profile.jfc` hoặc cấu hình có chủ đích |
| “JFR luôn dưới 1% overhead” | Còn phụ thuộc settings và workload | Benchmark overhead và giới hạn duration/size |
| “JDWP chỉ là cổng đọc logs” | Debugger có khả năng inspect/control VM | Bảo vệ listener, chỉ bind loopback khi lab |
| “JVM TI MethodEntry bật toàn bộ là rẻ” | Event callbacks có thể tác động mọi method/thread | Lọc, giới hạn và đo chi phí, cân nhắc bytecode probes |
| “Native agent ném Java exception nếu lỗi” | Lỗi native có thể làm cả process crash | Kiểm soát ABI/threads/JNI references, test trên staging |
| “JFR không có sample nên method không chạy” | Sampling có thể bỏ qua method ngắn/cấu hình thiếu | Xem settings/window; nếu cần evidence chính xác, dùng probe |
| “Có method probe nên biết nguyên nhân race” | Probe có thể đổi scheduling, chỉ ghi events được instrument | Dùng debugger, deterministic tests và concurrency analysis |
| “Stop JFR hoặc gỡ transformer xóa telemetry/bytecode trước đó” | Recording đã ghi và class đã instrument vẫn tồn tại | Thiết kế lifecycle, retention và rollback đúng khả năng |
| “Cài nhiều agents sẽ không tương tác” | Chúng dùng chung VM/process và có thể ảnh hưởng nhau | Test kết hợp, làm rõ ownership, classloader và transform order |

## 12. Câu hỏi tự kiểm tra

1. **Cần xem biến local khi request lỗi, nên bắt đầu bằng gì?** Debugger/JDI nếu có ca tái hiện và môi trường an toàn; instrumentation nếu cần ghi một tập fields có chọn lọc qua nhiều request.
2. **Cần tìm 3 methods đang tiêu CPU nhiều nhất mà chưa biết vị trí?** JFR/profiler CPU sampling trước, sau đó instrument nếu muốn per-call metrics.
3. **`ClassFileTransformer.transform` nhận callback mỗi method invocation không?** Không. Nó xử lý classfile bytes khi class load/redefine/retransform.
4. **JVM TI native agent phải kiểm tra gì trước khi enable event?** VM phase, capability hỗ trợ, error codes, callback signatures và concurrency constraints.
5. **Java debugger và JVM TI có phải hai công nghệ hoàn toàn không liên quan?** Không. Trong JPDA thông thường, JDWP backend dùng JVM TI ở phía debuggee.
6. **JDWP dùng để làm gì?** Giao thức truyền request/events giữa debugger và target VM, không phải profiler.
7. **JFR có chỉ sampling không?** Không. Nó vừa ghi sampling events vừa ghi nhiều event types khác.
8. **Một mẫu `jdk.ExecutionSample` chứa `Work.compute` chứng minh method chạy bao nhiêu lần?** Không xác định exact call count từ mẫu đó.
9. **JFR `profile.jfc` có phù hợp bật vô hạn trên mọi production không?** Không nên mặc định; cân nhắc overhead, size, thời lượng và workload.
10. **Khi method async trả Future nhanh, nên đo ở đâu?** Phân biệt method-return latency, future/stage terminal và actual worker completion.
11. **Debug port bind `*:5005` có an toàn cho mọi máy không?** Không; hạn chế listener, ưu tiên loopback và các lớp bảo vệ.
12. **Nếu cần inspect một primitive VM không có trong Java API/JDI/JFR thì sao?** Đánh giá JVM TI, capabilities và native engineering cost.
13. **Một profiler native có thể quan sát Java/native stacks nhưng vẫn là sample không?** Có; nó có thể ít lệch hơn phương pháp khác nhưng không chuyển thành exact trace mọi call.
14. **Java agent và JFR có dùng cùng nhau được không?** Có. Chúng tạo hai loại dữ liệu có thể bổ sung nhau nếu quản lý overhead.
15. **Chọn công cụ dựa vào tiêu chí nào trước tiên?** Câu hỏi cần bằng chứng, độ chính xác, thời gian quan sát, ảnh hưởng production, quyền triển khai và kỹ năng vận hành.

## 13. Checklist quyết định trước khi triển khai

- [ ] Viết câu hỏi rõ: *exact per-invocation*, *snapshot state*, *VM event*, hay *statistical hotspots*?
- [ ] Xác định môi trường: Java/JDK version, vendor, OS, JVM/agent capabilities và chính sách attach.
- [ ] Ưu tiên dữ liệu ít xâm lấn có sẵn (metrics, logs, spans, JFR) nếu đáp ứng yêu cầu.
- [ ] Với Java instrumentation, kiểm tra loader/module, class-load timing, retransform support, probe coverage và overhead.
- [ ] Với JVM TI, kiểm tra native ABI, capabilities, VM phases, callback safety, JNI exception state và native failure risk.
- [ ] Với debugger, chỉ dùng breakpoint trên môi trường cho phép suspend và bảo vệ JDWP port.
- [ ] Với sampling, chọn CPU vs wall vs allocation; duration, rate, stack depth và event settings có mục tiêu.
- [ ] Không kết luận “không xảy ra” chỉ vì **sample không thấy**; không kết luận “method được gọi” chỉ vì transformer thấy class file.
- [ ] Giữ cùng điều kiện khi benchmark on/off tool; quan sát overhead và tail latency.
- [ ] Không log secrets từ arguments, stacks hoặc heap; quản lý .jfr files, debug access và retention.
- [ ] Test tương tác nếu chạy nhiều agents/profilers đồng thời.
- [ ] Với async APIs, định nghĩa rõ điểm bắt đầu/kết thúc trước khi ghi latency.
- [ ] Khi không có capability/attach permission, dùng fallback có phép thay vì bypass.
- [ ] Ghi lại loại bằng chứng và giới hạn để không biến thống kê thành “sự thật tuyệt đối”.

## 14. Tài liệu tham khảo chính thức và kỹ thuật

- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): Javaagent startup, agent manifest và class loader/module loading.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, capabilities và giới hạn.
- [JVM Tool Interface 21 Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): native agent, capabilities/phases, callbacks, errors và events.
- [JPDA Architecture](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/architecture.html): mối quan hệ JVM TI, JDWP, JDI và debugger.
- [Java SE 21 — `jdb` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html): breakpoints, step, `where`, `cont`, debugger attach.
- [Java SE 21 — JDWP connection/invocation](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html): `-agentlib:jdwp`, transport và cấu hình connection.
- [Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start/check/dump/stop`, `Thread.print`.
- [Java SE 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `jfr summary`, `jfr print --events` và phân tích recordings.
- [Java Flight Recorder configurations](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html): `default.jfc` và `profile.jfc`.
- [async-profiler — Profiling Modes](https://github.com/async-profiler/async-profiler/blob/master/docs/ProfilingModes.md): CPU/wall/allocation sampling, Java/native stack collection (third-party tool, phụ thuộc môi trường).
