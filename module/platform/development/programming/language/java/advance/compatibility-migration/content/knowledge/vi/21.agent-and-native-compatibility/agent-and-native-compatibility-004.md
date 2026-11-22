# JVMTI, profiler, APM và công cụ theo dõi sau nâng cấp

Sau khi nâng cấp JDK, ứng dụng Java có thể khởi động bình thường và vượt qua unit test, nhưng hệ thống quan sát lại gặp lỗi: Java agent không khởi tạo, profiler không lấy được stack trace, APM mất trace, native agent làm JVM crash, hoặc số liệu hiệu năng thay đổi đáng kể. Đây không chỉ là vấn đề của ứng dụng. **Agent và công cụ theo dõi cũng là một phần của môi trường thực thi cần được kiểm thử tương thích**.

Đặc biệt, các công cụ này có thể chạy **bên trong chính tiến trình JVM**, truy cập API nội bộ, biến đổi bytecode, phụ thuộc JVMTI hoặc gọi native library. Một plugin có thể tương thích với Java 17 nhưng không hiểu class file Java 21; một profiler có thể tương thích với JVM mới nhưng thiếu quyền truy cập bộ đếm hiệu năng trong container; một APM agent có thể khởi động nhưng không còn tạo span cho HTTP client sau khi framework được nâng cấp.

Bài học này giải thích vai trò của **JVM Tool Interface (JVMTI)**, Java instrumentation agent, profiler, Java Flight Recorder (JFR), APM và các công cụ chẩn đoán. Trọng tâm là cách kiểm chứng những công cụ này sau Java Advance Compatibility Migration mà không đánh đổi độ ổn định và an toàn production.

## 1. Phân biệt các lớp công cụ quan sát Java

Các công cụ cùng được gọi là “monitoring” nhưng có mục tiêu và mức tác động khác nhau.

| Nhóm công cụ | Thường thu thập điều gì? | Công nghệ có thể sử dụng | Rủi ro khi nâng JDK |
|---|---|---|---|
| **Native JVMTI agent** | Class load, thread, method, heap, event JVM | `jvmti.h`, JNI, thư viện `.so`/`.dll` | ABI, capability, JVM implementation, native crash |
| **Java agent** | Instrumentation, trace, metric, method timing | `java.lang.instrument`, bytecode transformers | Class-file version, framework API, module access |
| **CPU/Allocation profiler** | Hot methods, CPU time, allocations, lock contention | JFR, async sampling, JVMTI, OS perf events | Sampling semantics, OS permissions, native symbols |
| **JFR/JMC** | JVM events, GC, allocation, threads, compilation, execution samples | JDK Flight Recorder và JDK Mission Control | Event availability, settings, parsing/tool versions |
| **APM/tracing agent** | HTTP spans, SQL spans, trace context, errors, JVM metrics | Java agent, instrumentation, OpenTelemetry | Instrumentation coverage, context propagation, overhead |
| **Metrics exporter** | JVM heap, GC, threads, process metrics | JMX, Micrometer, MXBeans, HTTP exporter | Metric names/types, GC changes, dashboard assumptions |
| **Diagnostic CLI** | Thread dump, heap histogram, JVM flags, JFR recording | `jcmd`, `jstack`, `jmap` tùy JDK | Permissions, attach availability, container restrictions |

**Không nên xem mọi công cụ ở bảng trên như một agent JVMTI.** JFR có thể được bật bằng công cụ JDK mà không cần tải Java agent bên thứ ba. Một Java agent có thể dùng `Instrumentation` mà không tự viết mã C/C++. Ngược lại, một profiler native có thể dùng JVMTI và sampling từ hệ điều hành mà không cần sửa bytecode của ứng dụng.

### 1.1. Một JVM có thể mang nhiều lớp instrumentation

Ví dụ topology:

~~~text
Service Java chạy trong container
    |
    +--> -javaagent:/opt/agents/apm-agent.jar
    |        +--> biến đổi bytecode HTTP/JDBC
    |        +--> xuất trace/metric ra collector
    |
    +--> -agentpath:/opt/profiler/libprofiler.so
    |        +--> dùng native/JVMTI và sampling
    |
    +--> JVM built-in JFR
    |        +--> ghi event vào file .jfr
    |
    +--> JMX / MXBeans / exporters
             +--> heap, GC, thread, CPU metrics
~~~

Trong quá trình nâng JDK, **mỗi lớp có phiên bản, cấu hình và cơ chế tương thích riêng**. Chỉ cần một lớp bị lỗi cũng có thể làm kết quả quan sát trở nên thiếu tin cậy.

## 2. JVM Tool Interface (JVMTI) là gì?

**JVMTI** là native programming interface dành cho công cụ phát triển và giám sát JVM. Nó cung cấp cách xem trạng thái và điều khiển một số khía cạnh thực thi của JVM như class, thread, stack, object, breakpoint, heap hoặc callback sự kiện.

Theo đặc tả, JVMTI được thiết kế cho profiling, debugging, monitoring, thread analysis và coverage. Nó là **giao diện native**, thường được dùng qua code C/C++ và header `jvmti.h`. JVMTI không phải một API Java thông thường như `java.util.logging`.

### 2.1. Agent sống trong tiến trình JVM

Một JVMTI agent thường được đóng gói thành thư viện native:

- Linux: file `.so`.
- Windows: file `.dll`.
- macOS: file `.dylib` theo quy ước nền tảng.

Agent được nạp vào cùng process với ứng dụng. Nó có thể đăng ký callback nhận sự kiện JVM, hỏi thông tin về class/method hoặc yêu cầu một số capability tùy phase khởi động.

~~~text
JVM process
    |
    +-- Java application classes
    |
    +-- GC / JIT / thread runtime
    |
    +-- JVMTI environment
            |
            +-- Native agent A
            |      callbacks + capabilities
            |
            +-- Native agent B
                   callbacks + capabilities
~~~

JVMTI có thể hỗ trợ nhiều agent cùng tồn tại, mỗi agent có môi trường riêng, nhưng **chúng vẫn tác động đến cùng một JVM và cùng native process**. Hai agent có thể xung đột nếu cùng biến đổi class, xử lý sự kiện hoặc tạo áp lực CPU/bộ nhớ.

### 2.2. Khởi động native agent

Ví dụ, JVM HotSpot hỗ trợ:

~~~bash
# Nạp theo tên thư viện, JVM tìm trong đường dẫn native library.
java -agentlib:sampleProfiler=option1,option2 -jar app.jar

# Nạp một thư viện native bằng đường dẫn cụ thể.
java -agentpath:/opt/agents/libsampleProfiler.so=option1,option2 -jar app.jar
~~~

Các lệnh chỉ minh họa cú pháp; cần thư viện agent hợp lệ do vendor cung cấp. Không nên chạy với một file bất kỳ chưa được xác minh.

Đối với native JVMTI agent, JVM gọi hàm khởi động như:

~~~c
#include <jni.h>
#include <jvmti.h>

/* Ví dụ chữ ký entry point, không phải agent hoàn chỉnh. */
JNIEXPORT jint JNICALL Agent_OnLoad(
    JavaVM *vm,
    char *options,
    void *reserved
) {
    return JNI_OK;
}
~~~

Agent thực tế còn phải lấy `jvmtiEnv`, kiểm tra kết quả API, thương lượng capabilities, đăng ký callback, quản lý JNI references và tài nguyên native. Một `Agent_OnLoad` trả về lỗi khác 0 có thể làm JVM không khởi động.

### 2.3. Capability và phase quan trọng hơn một flag duy nhất

JVMTI có nhiều capability như khả năng quan sát sự kiện, biến đổi lại class, kiểm tra heap hoặc bắt breakpoint. Một số capability cần được yêu cầu sớm; không phải tất cả đều sẵn có khi agent attach vào JVM đang chạy.

Các phase quan trọng:

1. **OnLoad:** native agent khởi tạo trước khi application bắt đầu chạy.
2. **Start / Live:** JVM đã khởi động, có thể phát nhiều event và thực thi ứng dụng.
3. **Dead:** JVM đang kết thúc hoặc đã kết thúc.

Nếu profiler chỉ attach sau khi ứng dụng chạy, nó có thể không quan sát được mọi class-load hoặc sự kiện startup. Kết quả benchmark startup với late attach **không tương đương** với startup agent.

## 3. Java agent và `java.lang.instrument`

Java agent được viết bằng Java và đóng gói thành JAR. Nó có thể bổ sung logic đo lường bằng cách biến đổi bytecode của class trước hoặc sau khi class được nạp, trong phạm vi cơ chế Instrumentation hỗ trợ.

### 3.1. Startup agent với `premain`

Agent JAR có manifest khai báo `Premain-Class`. JVM có thể nạp agent ngay khi khởi động:

~~~bash
java -javaagent:/opt/agents/telemetry-agent.jar -jar app.jar
~~~

Một entry point tối giản:

~~~java
package com.example.monitoring;

import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    public static void premain(
            String agentArgs,
            Instrumentation instrumentation) {
        System.out.println("Instrumentation agent started");
        System.out.println(
            "Retransform supported: " +
            instrumentation.isRetransformClassesSupported()
        );
    }
}
~~~

Manifest ví dụ:

~~~text
Manifest-Version: 1.0
Premain-Class: com.example.monitoring.StartupAgent
Can-Retransform-Classes: true
~~~

Đây là mô tả cấu trúc, không phải một APM agent hoàn chỉnh. Tính năng retransform thực tế còn phụ thuộc khả năng JVM và agent; khai báo manifest không tự làm mọi class có thể được sửa lại.

### 3.2. Dynamic attach với `agentmain`

Một Java agent có thể có entry point `agentmain` để được nạp vào JVM đang chạy, trong những runtime còn cho phép động tác này:

~~~java
public static void agentmain(
        String agentArgs,
        Instrumentation instrumentation) {
    // Khởi tạo instrumentation khi JVM đang chạy
}
~~~

Startup agent và dynamic agent không giống nhau:

| Khía cạnh | Startup `-javaagent` | Dynamic attach |
|---|---|---|
| Thời điểm | Khi JVM khởi động | Sau khi ứng dụng đã chạy |
| Entry point | `premain` | `agentmain` |
| Khả năng quan sát startup | Có thể quan sát sớm | Có thể bỏ lỡ phần startup |
| Chính sách bảo mật | Cấu hình rõ tại launch | Chịu chính sách attach và dynamic agent loading |
| Rollout | Thường cần restart process | Có thể attach theo điều kiện runtime |
| Nguy cơ | Khởi động fail nếu agent hỏng | Attach bị chặn, capability thiếu, runtime perturbation |

### 3.3. Nhiều Java agents có thể biến đổi cùng class

Một ứng dụng có thể đồng thời dùng APM, coverage agent và một agent profiling. Các transformer có thể được áp dụng theo thứ tự và tạo bytecode đã biến đổi. Nếu chúng không tương thích, lỗi có thể là:

- `VerifyError` hoặc `ClassFormatError` khi bytecode sai.
- `LinkageError` khi class/method không khớp.
- `NoClassDefFoundError` do dependency của agent không có.
- `InaccessibleObjectException` khi framework/agent dùng deep reflection không được phép.
- Mất một span/metric do transformer không nhận diện class đã được agent khác sửa.
- Tăng CPU, allocation hoặc latency khi instrument quá nhiều điểm.

Không thể kết luận sự cố thuộc JDK chỉ vì nó xuất hiện sau khi nâng JDK: agent và thư viện bytecode cũng cần được đánh giá.

## 4. Chính sách nạp agent động và JEP 451

**JEP 451 – Prepare to Disallow the Dynamic Loading of Agents** được đưa vào JDK 21 nhằm chuẩn bị cho chính sách chặt chẽ hơn đối với việc nạp agents vào JVM đang chạy.

Trong các bản HotSpot/JDK áp dụng hành vi JEP 451, JVM cảnh báo khi nạp Java agent hoặc JVMTI agent động. Mục đích là làm rõ rằng instrumentation có thể thay đổi code của ứng dụng và cần được chủ sở hữu runtime chấp thuận.

Ví dụ thông báo có thể có dạng:

~~~text
WARNING: A Java agent has been loaded dynamically (...)
WARNING: Dynamic loading of agents will be disallowed
         by default in a future release
~~~

**Điều cần hiểu chính xác:**

- Cảnh báo không có nghĩa toàn bộ Java agent đã bị cấm.
- Agent nạp khi startup bằng `-javaagent` hoặc `-agentpath` vẫn là mô hình được thiết kế để chủ sở hữu runtime cho phép.
- **Nạp agent động** chịu chính sách riêng với attach mechanism, và khả năng cho phép/không cho phép cần kiểm tra trên đúng JDK và vendor đang triển khai.
- Không được suy từ thông báo của JDK 21 rằng tất cả các phiên bản JDK về sau có cùng mặc định; cần kiểm tra release notes của bản đích.

Với HotSpot, có thể cấu hình chấp thuận dynamic agent loading bằng tùy chọn:

~~~bash
java -XX:+EnableDynamicAgentLoading -jar app.jar
~~~

Đặt option này phải là quyết định có kiểm soát, không phải cách dập cảnh báo tự động trong mọi ứng dụng.

### 4.1. Phân biệt dynamic attach và diagnostic commands

Một số thao tác như `jcmd`, thread dump hoặc lấy JFR có thể dùng cơ chế chẩn đoán JVM mà **không phải nạp một agent tùy ý từ bên ngoài**. Không nên coi mọi thao tác attach diagnostic đều bị chi phối theo cách giống `loadAgent`.

Ngược lại, một profiler dùng attach để nạp native JVMTI agent vào JVM có thể chịu các ràng buộc dynamic agent loading và quyền truy cập OS/JVM.

### 4.2. Khi profiler cũ phụ thuộc attach vào production

Hãy xác định:

1. Profiler có bắt buộc attach động hay có thể khởi động bằng `-agentpath`?
2. JDK đích mặc định cho phép hay từ chối dynamic agent loading?
3. Có quyền truy cập process của cùng user, cùng container/PID namespace không?
4. Chính sách bảo mật tổ chức có cho phép attach agent vào JVM sản xuất không?
5. Có thể dùng JFR built-in thay cho việc nạp native agent bên thứ ba không?

Nếu khả năng attach là thiết yếu, cần lập phương án triển khai rõ ràng, kiểm chứng bằng môi trường tương tự production. Tránh thay đổi chính sách bảo vệ toàn cụm chỉ để chạy một profiler trong thời gian ngắn.

## 5. Vì sao nâng JDK có thể làm agent không tương thích?

### 5.1. Class file version và thư viện xử lý bytecode

JDK mới có thể tạo class file với major version và cấu trúc mới. Java agent sử dụng ASM, Byte Buddy hoặc thư viện tương tự có thể từ chối class file mà nó chưa hỗ trợ.

Ví dụ major version:

| Java | Class file major |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

Nếu agent cũ gặp class file mới, có thể xuất hiện lỗi dạng:

~~~text
java.lang.IllegalArgumentException:
    Unsupported class file major version ...
~~~

hoặc stack trace gắn với `ClassReader`, transformer, retransform/redefine. Hãy nâng agent hoặc dependency bytecode của agent lên phiên bản vendor hỗ trợ JDK đích, không sửa ngẫu nhiên bytecode target của ứng dụng để che lỗi nếu runtime đã nâng.

### 5.2. Bytecode instrumentation phải tuân thủ verifier

Khi agent thêm lệnh hoặc sửa control flow, bytecode mới cần có operand stack, stack map frames và metadata hợp lệ. Thay đổi cấu trúc class file hoặc chính sách verifier có thể làm lộ lỗi của transformer.

Các lỗi như `VerifyError`, `ClassFormatError` hoặc JVM crash chỉ xuất hiện **khi bật agent** là tín hiệu mạnh rằng phải thử cô lập agent.

Quy trình so sánh:

~~~text
Same JDK, same artifact, same workload
   |
   +-- Chạy không agent
   |
   +-- Chạy chỉ APM agent
   |
   +-- Chạy chỉ profiler
   |
   +-- Chạy cả APM + profiler
        |
        v
So sánh crash, error, throughput, trace, class loading
~~~

Đây là phân lập nguyên nhân, không phải kết luận rằng bản thân một agent luôn sai nếu benchmark khác.

### 5.3. JPMS và strong encapsulation

Nhiều agent cần intercept các class trong JDK hoặc framework. Một số cơ chế hợp lệ đi qua `Instrumentation.redefineModule`; một số phiên bản agent cũ lại dùng reflection trực tiếp vào package không được mở và có thể gặp:

~~~text
java.lang.reflect.InaccessibleObjectException
~~~

Không nên sao chép hàng loạt flag `--add-opens` hoặc `--add-exports` từ log mà không hiểu:

- Module/package nào cần được truy cập?
- Vì sao agent cần quyền đó?
- Vendor agent đã có bản tương thích JDK mới chưa?
- Flag có làm tăng rủi ro truy cập nội bộ JVM không?
- Có thể giảm quyền hoặc dùng API công khai không?

Các flag mở module chỉ là biện pháp có phạm vi; chúng không sửa được class file quá mới, native ABI không tương thích hoặc lỗi logic của transformer.

### 5.4. Native binary, ABI và architecture

Native JVMTI agent là mã máy. Cần đối chiếu:

- CPU architecture: `x86_64`, `aarch64`, v.v.
- OS và phiên bản kernel.
- Thư viện nền tảng/glibc và dynamic linker.
- Bản JVM/HotSpot và các tính năng JVMTI được hỗ trợ.
- Thư viện native đi kèm, chẳng hạn thư viện unwind hoặc profiler-specific dependencies.
- Cách đóng gói container và file permissions.

Ví dụ `.so` build cho `x86_64` không thể nạp vào JVM `aarch64`. JDK nâng cấp thường đi kèm đổi container image hoặc chuyển máy ARM, nên không được tự kết luận tất cả là lỗi JDK.

### 5.5. Native crash khác Java exception

Một lỗi trong mã C/C++ hoặc callback JVMTI có thể gây crash toàn bộ process, không nhất thiết tạo stack trace Java. JVM có thể sinh file lỗi như:

~~~text
hs_err_pid12345.log
~~~

Trong file đó cần tìm:

- Fatal error signal và problematic frame.
- Native library/agent ở stack hiện tại.
- JVM version/vendor/build.
- Thread đang crash.
- VM arguments, loaded libraries và GC/compiler context.

Nếu `problematic frame` nằm trong native agent hoặc thư viện đi kèm, cần thu thập log an toàn và phối hợp với vendor. Không nên gọi lại một agent không rõ nguồn trong production để “tái hiện cho chắc”.

## 6. Profiler khác APM ở mục đích và cơ chế thu thập

### 6.1. Profiler: tìm tiêu tốn tài nguyên

Profiler trả lời những câu hỏi như:

- Thread nào đang dùng CPU nhiều?
- Method nào thường xuất hiện trong CPU samples?
- Phần nào phân bổ nhiều object?
- Code đang chờ lock hay chờ I/O?
- Native stack có chiếm thời gian đáng kể không?

Một profiler sampling định kỳ lấy mẫu stack của thread. Nó cho kết quả gần đúng theo xác suất và khoảng thời gian ghi mẫu, không phải danh sách chính xác mọi method call. Profiling quá ngắn hoặc workload không đại diện có thể dẫn tới kết luận sai.

### 6.2. APM: quan sát giao dịch theo luồng nghiệp vụ

APM agent thường cung cấp:

- Transaction/endpoint latency.
- Distributed tracing và trace/span context.
- HTTP, RPC, JDBC hoặc messaging spans.
- Error/exception counts.
- JVM/runtime metrics.
- Service maps và thông tin request propagation.

Một APM agent có thể sửa bytecode tại các điểm ingress/egress để đo thời gian và lan truyền context. Những điểm instrumentation này phụ thuộc vào framework version: chuyển từ servlet sang reactive stack, nâng Netty hoặc JDBC driver có thể làm spans thiếu dù agent vẫn báo “loaded”.

### 6.3. Metrics không thay thế trace và profiler

| Câu hỏi | Dữ liệu phù hợp |
|---|---|
| “Tỷ lệ request lỗi sau upgrade có tăng?” | Metrics/SLO dashboards |
| “Endpoint nào chậm hơn?” | HTTP metrics, latency histograms, tracing |
| “Chậm ở DB hay ở ứng dụng?” | Distributed traces + DB metrics |
| “Method nào chiếm CPU?” | CPU profiler/JFR execution samples |
| “Có tạo quá nhiều object?” | Allocation profiling/JFR + GC metrics |
| “Thread nào đang đợi lock?” | JFR lock events, thread dump, lock profiler |
| “APM agent làm chậm app?” | So sánh có/không agent ở cùng workload |

Không nên lấy flame graph thay thế toàn bộ APM, hoặc dùng latency dashboard để kết luận method cụ thể tiêu CPU.

## 7. Hiểu CPU time, wall time và allocation samples

### 7.1. CPU profiling

CPU profiling ghi nhận code đang thực sự sử dụng CPU. Nó phù hợp khi throughput giảm và CPU tăng. Nhưng khi ứng dụng mất thời gian chờ network hoặc lock, CPU profile có thể chỉ thấy ít hoạt động dù request latency cao.

### 7.2. Wall-clock profiling

Wall-clock profiling lấy mẫu thời gian thực trôi qua; tùy profiler, nó có thể bao gồm các thread đang chờ, blocked hoặc sleeping. Đây là góc nhìn hữu ích để tìm latency, nhưng phải biết profiler có lọc thread states hoặc dùng chính sách sample nào.

### 7.3. Allocation profiling

Allocation profiling giúp tìm điểm tạo object và áp lực GC. Nhiều profiler **lấy mẫu allocations** thay vì ghi từng allocation; có thể bỏ sót các trường hợp hiếm hoặc rất nhỏ. Khi so sánh hai JDK, cần giữ cùng sampling settings và workload.

### 7.4. Flame graph cần đọc đúng

Flame graph thường biểu diễn một tập stack samples:

~~~text
main
  -> HTTP handler
      -> OrderService
          -> ValidateOrder
          -> DatabaseQuery
~~~

Chiều rộng của khung thường phản ánh số mẫu tương đối, không tự động là thời gian chính xác của một lần gọi. Một method có chiều rộng lớn chưa chắc là “lỗi”; nó có thể là công việc bình thường có tần suất cao.

Không nên so sánh trực tiếp hai flame graph nếu thời lượng thu thập, sampling rate, workload hoặc cách lấy stack khác nhau.

## 8. Java Flight Recorder (JFR): điểm bắt đầu hữu ích sau nâng cấp

**Java Flight Recorder** là hệ thống thu thập sự kiện được tích hợp trong các JDK HotSpot hiện đại, phù hợp để quan sát GC, compilation, thread scheduling, execution samples, allocation, I/O và nhiều hoạt động JVM khác.

JFR thường có overhead thấp theo cấu hình phù hợp và có thể dùng lâu dài trong production, nhưng **không phải mọi event hoặc mức stack trace đều miễn phí**. Một cấu hình profiling nhiều event chi tiết có thể tiêu tốn CPU, bộ nhớ và dung lượng lưu trữ cao hơn `default`.

### 8.1. Khởi động recording cùng JVM

~~~bash
java \
  -XX:StartFlightRecording=filename=upgrade-baseline.jfr,duration=5m,settings=profile \
  -jar app.jar
~~~

Lệnh minh họa trên shell kiểu Unix; với Windows cần viết trên một dòng hoặc dùng cú pháp nối dòng phù hợp.

Ý nghĩa:

- `filename`: file JFR đầu ra.
- `duration=5m`: thời lượng ghi.
- `settings=profile`: dùng bộ settings nhấn mạnh profiling, thường thu thập nhiều thông tin hơn `default`.

Chọn thời lượng theo workload có ý nghĩa, và kiểm soát kích thước file ghi ra.

### 8.2. Dùng `jcmd` với process đang chạy

Nếu JVM hỗ trợ chẩn đoán và có quyền truy cập phù hợp:

~~~bash
# Liệt kê các Java processes đang truy cập được
jcmd

# Bắt đầu một recording 2 phút
jcmd 12345 JFR.start name=UpgradeProfile settings=profile duration=2m filename=upgrade.jfr

# Xem recording đang hoạt động
jcmd 12345 JFR.check
~~~

PID `12345` chỉ là ví dụ. Trong container, cần chọn đúng PID namespace và quyền của user thực sự chạy Java process. Lệnh `jcmd` thường cần cùng máy và quyền phù hợp; không phải lúc nào sidecar ở container khác cũng có thể attach.

Nếu recording chưa có `duration` và vẫn đang chạy, có thể dump dữ liệu:

~~~bash
jcmd 12345 JFR.dump name=UpgradeProfile filename=upgrade-snapshot.jfr
~~~

`JFR.dump` có thể tạo một snapshot mà recording tiếp tục chạy. Nếu muốn dừng hẳn, dùng `JFR.stop` với tên recording thích hợp.

### 8.3. Phân tích recording

Các lệnh có sẵn trong JDK:

~~~bash
jfr summary upgrade.jfr
jfr print --events jdk.ExecutionSample upgrade.jfr
~~~

Có thể mở file `.jfr` trong **JDK Mission Control (JMC)** hoặc công cụ phân tích tương thích với format/event của bản JDK tạo recording.

Khi đổi JDK, nên nâng JMC/analyzer phù hợp. Một công cụ hiển thị cũ không nhận diện event mới chưa chắc có nghĩa recording hoặc ứng dụng hỏng.

### 8.4. Event đáng chú ý

| Mục tiêu | Nhóm JFR event/thông tin |
|---|---|
| CPU hotspots | `jdk.ExecutionSample` và stack traces |
| Allocation | Allocation samples/events, tùy cấu hình JDK |
| GC pause và heap | Garbage collection events, heap summaries |
| Contention | Monitor enter/park events |
| Thread behavior | Thread start/end, park, execution samples |
| Compilation | JIT compilation/optimization events |
| Class loading | Class loading statistics/events |
| I/O | File/socket read/write events |
| Virtual threads | Virtual-thread-specific events nếu runtime cung cấp |

Tên event, mức chi tiết và mặc định có thể thay đổi theo JDK. Trước khi dựa vào một event, kiểm tra `jfr metadata` và cấu hình `.jfc` trên runtime mục tiêu.

## 9. Async-profiler và native profilers

Một công cụ như **async-profiler** có thể lấy mẫu CPU, wall-clock, allocations hoặc lock contention trên HotSpot, thường bằng sự kết hợp của JVMTI, AsyncGetCallTrace/stack walking và cơ chế hệ điều hành tùy phiên bản/platform.

Không nên diễn giải rằng mọi chế độ đều dùng cùng API hoặc có cùng overhead. Công cụ và JVM version cần nằm trong support matrix của vendor/profiler.

### 9.1. Những ràng buộc Linux/container thường gặp

Một native profiler có thể cần quyền truy cập:

- Linux perf events hoặc cơ chế sampling tương ứng.
- `/proc` của Java process.
- Namespace chứa JVM.
- Native library loader.
- Java process với cùng user/permissions.
- Linux `perf_event_paranoid` và chính sách `seccomp`/capabilities thích hợp.

Một profiler hoạt động trên máy phát triển nhưng không thể attach trong Kubernetes có thể do **container security policy** chứ không phải do JDK.

Tránh giải pháp mặc định chạy container đặc quyền toàn phần chỉ để profiler lấy được mẫu. Nên dùng các phương án có phạm vi nhỏ hơn, phù hợp với chính sách bảo mật của môi trường.

### 9.2. Vấn đề stack native và symbolization

Nếu profiler lấy cả native stacks, thông tin debug symbols và khả năng unwind ảnh hưởng đến chất lượng flame graph. Khi đổi JDK image hoặc distro, stack có thể xuất hiện nhiều frame không có tên dù ứng dụng vẫn chạy đúng.

Nên ghi lại:

- OS/kernel và architecture.
- JDK vendor/build.
- Profiler version/build.
- Sampling mode, interval, duration.
- Native symbols/debug information availability.
- Container security permissions.

### 9.3. Khi nào ưu tiên JFR, khi nào dùng native profiler?

Bắt đầu bằng JFR khi cần góc nhìn tổng thể JVM và sử dụng công cụ JDK sẵn có. Dùng profiler chuyên sâu khi cần CPU/native/wall-clock/allocation details mà cấu hình JFR hiện tại không cung cấp đủ.

Trong cả hai trường hợp, hãy so sánh dữ liệu **cùng workload và cùng cửa sổ thời gian**, không đánh giá một JDK nhanh/chậm chỉ từ recording khác môi trường.

## 10. APM sau nâng cấp: “loaded” chưa chắc “observing”

APM agent có thể khởi động thành công và vẫn gửi heartbeat, nhưng **thiếu dữ liệu nghiệp vụ** vì framework instrumentation không còn tương thích.

Ví dụ khi nâng:

- Spring Boot hoặc Servlet API.
- Netty, Reactor hoặc các HTTP clients.
- JDBC driver, Hibernate hoặc database client.
- Kafka/RabbitMQ client.
- gRPC và các thư viện RPC khác.
- OpenTelemetry SDK/semconv mappings.
- Virtual thread scheduling trong mã bất đồng bộ.

Các triệu chứng có thể gồm:

- HTTP request count vẫn có nhưng DB spans biến mất.
- Trace có root span nhưng downstream spans không liên kết.
- Parent/child context mất khi qua executor, virtual thread hoặc reactive pipeline.
- Các lỗi exception không còn được gắn vào spans.
- Latency distribution biến đổi vì điểm đo của agent thay đổi.
- Log correlation như `trace_id`/`span_id` không xuất hiện.
- Agent tăng CPU/heap hoặc số class được transformed.

### 10.1. So sánh ba phiên bản

Có thể xây dựng ma trận:

| Ứng dụng | JDK | APM agent | Mục tiêu |
|---|---|---|---|
| Version cũ | JDK cũ | Agent cũ | Baseline |
| Version cũ | JDK mới | Agent cũ | Kiểm tra ảnh hưởng JDK, nếu cấu hình được hỗ trợ |
| Version cũ | JDK mới | Agent mới | Kiểm tra tương thích agent với JDK |
| Version mới | JDK mới | Agent mới | Kiểm tra toàn bộ stack mới |

Không nhất thiết mọi ô đều hỗ trợ; ghi rõ ô không thể chạy do vendor support. Đừng suy từ một hàng thành một kết luận chung cho toàn bộ migration.

### 10.2. Kiểm thử một trace hoàn chỉnh

Ví dụ nghiệp vụ:

~~~text
HTTP POST /orders
       |
       v
OrderController
       |
       v
OrderService
       |
       +--> JDBC INSERT orders
       |
       +--> Kafka publish OrderCreated
       |
       v
HTTP 201
~~~

Kiểm thử cần xác nhận:

1. Có root span của HTTP request.
2. Có span database nếu instrument JDBC.
3. Có span gửi message nếu integration đó được hỗ trợ.
4. Trace ID được truyền đúng theo chuẩn/config hệ thống.
5. Status, errors, latency và các thuộc tính quan trọng đúng.
6. Không thu thập credentials, token, dữ liệu cá nhân ngoài chính sách.
7. Khi APM agent bị lỗi xuất dữ liệu, ứng dụng có đáp ứng yêu cầu fail-open/fail-safe được thiết kế hay không.

Một trace đẹp trong dashboard chưa chứng minh mọi endpoint đều có coverage. Nên chọn các đại diện cho HTTP, DB, messaging và async context.

### 10.3. OpenTelemetry Java agent

Với một Java agent theo OpenTelemetry, startup thường ở dạng:

~~~bash
java \
  -javaagent:/opt/otel/opentelemetry-javaagent.jar \
  -Dotel.service.name=orders-service \
  -Dotel.exporter.otlp.endpoint=https://otel-collector.example \
  -jar orders-service.jar
~~~

Endpoint trong ví dụ là tên minh họa, không phải collector thực. Cần cấu hình authentication/TLS, exporter, sampling và resource attributes theo hệ thống đang dùng.

Version OpenTelemetry Java agent, semantic conventions và instrumentation modules có thể thay đổi; cần kiểm tra tài liệu và release notes của phiên bản agent thực tế. Không nên sao chép cấu hình exporter của một version bất kỳ rồi khẳng định tương thích mọi bản.

## 11. Virtual threads, GC và JIT: vì sao số liệu sau nâng JDK có thể khác?

### 11.1. Virtual threads (Java 21 trở lên)

Java virtual threads thay đổi cách ứng dụng có thể mô hình hóa concurrency. Công cụ APM/profiler cũ có thể giả định “một request gắn với một platform thread”, dẫn đến sai số hoặc mất trace context.

Cần kiểm tra:

- Trace context có đi theo task/request qua các bước bất đồng bộ không.
- Profiler có hiển thị virtual threads/carrier threads rõ ràng không.
- Thread counts trong dashboard còn ý nghĩa như trước không.
- JFR có cung cấp event liên quan đến virtual threads ở JDK đang chạy không.
- Metric về blocked/parked/active threads có được diễn giải phù hợp không.

Không nên dùng số lượng thread của JDK cũ như giới hạn tuyệt đối khi ứng dụng đã chuyển sang virtual-thread model.

### 11.2. Garbage collector có thể thay đổi

Dùng JDK mới có thể đi kèm thay GC, tuning flags hoặc hành vi GC. Khi so sánh:

- Pause time percentiles.
- Allocation rate và heap occupancy.
- Concurrent GC CPU.
- Humongous allocations hoặc promotion nếu GC có khái niệm tương ứng.
- Memory ngoài Java heap.
- Container CPU throttling.

Đừng quy kết mọi thay đổi latency cho “agent overhead” khi GC/runtime cũng khác. Nên có baseline JDK mới **không agent** để tách nguyên nhân.

### 11.3. JIT và warmup làm sai lệch benchmark

Profiler có thể ảnh hưởng cách HotSpot tối ưu code, và JDK mới có thể có compiler heuristics khác. Một benchmark chỉ chạy vài giây sau startup có thể đo warmup nhiều hơn steady state.

Nên thực hiện:

- Warmup theo cùng kế hoạch.
- Workload cố định.
- Nhiều lần chạy.
- Ghi phân phối p50/p95/p99 thay vì chỉ trung bình.
- Theo dõi CPU, GC, JIT compilation và allocation.
- Giữ cùng resource limits và concurrency.

### 11.4. Observability telemetry có thể đổi tên/nhãn

Sau nâng JDK hoặc exporter, số liệu có thể thay đổi tên metric, loại histogram, unit hoặc labels. Ví dụ dashboard theo dõi một tên GC cụ thể có thể trắng khi collector hoặc instrumentation mới đổi nhãn, dù GC vẫn hoạt động.

Vì vậy cần kiểm tra **pipeline dữ liệu tới dashboard và alert**, không chỉ xem file agent có được nạp.

## 12. Quy trình chẩn đoán bằng công cụ JDK

### 12.1. Bắt đầu từ identity của JVM

~~~bash
java -version
jcmd
~~~

Khi được phép truy cập process:

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
~~~

Các lệnh giúp xác nhận runtime vendor/build, startup flags và command line. Không nên in toàn bộ command line ra ticket công khai nếu có secret trong JVM arguments.

### 12.2. Kiểm tra native libraries và class loaders

Các lệnh diagnostic khả dụng phụ thuộc JVM/version:

~~~bash
jcmd 12345 help
jcmd 12345 VM.dynlibs
jcmd 12345 VM.classloader_stats
~~~

Một số command có thể không có hoặc có output khác trên một runtime nhất định. `jcmd <pid> help` là cách xem tập command thực tế trước khi sử dụng.

`VM.dynlibs` hỗ trợ khảo sát shared libraries trong quá trình xử lý crash của native agent. `VM.classloader_stats` giúp phân tích class loader count/metadata khi nghi instrumentation tạo ra nhiều class.

### 12.3. Thread dumps và heap

~~~bash
jcmd 12345 Thread.print
jcmd 12345 GC.heap_info
jcmd 12345 GC.class_histogram
~~~

Một số command có impact đáng kể; `GC.heap_dump` còn có thể tạo file lớn và/hoặc làm ứng dụng tạm dừng. Chỉ thực hiện theo runbook được phê duyệt và đủ dung lượng lưu trữ. Trong môi trường production, JFR thường là lựa chọn ít xâm lấn hơn để điều tra nhiều hiện tượng.

### 12.4. Native memory tracking

Với HotSpot và cấu hình NMT thích hợp, có thể dùng `jcmd`:

~~~bash
# Ví dụ cấu hình từ khi khởi động:
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Sau đó:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

NMT hữu ích khi nghi native memory tăng sau khi bật agent, nhưng nó cũng có overhead và không tự nhận diện mọi allocation native do thư viện ngoài quản lý. Cần hiểu giới hạn đo và baseline. Không thể giả định bật NMT chi tiết hoàn toàn động sau khi JVM đã chạy nếu lúc startup chưa cấu hình.

## 13. Ma trận tương thích trước khi nâng JDK

Một ma trận tối thiểu có thể chứa:

| Trục | Giá trị cần kiểm tra |
|---|---|
| JDK | 17 / 21 / JDK mục tiêu cùng vendor/build |
| Operating system | Linux/Windows/macOS tùy production |
| Architecture | x86_64/aarch64 nếu triển khai cả hai |
| Container | Base image, libc, kernel, security context |
| Application | Version trước và sau migration |
| Agent | APM, native profiler, coverage agent versions |
| Framework | Spring, Netty, Hibernate, HTTP/JDBC clients |
| Runtime mode | Classpath/module path, virtual/platform threads |
| Startup mode | `-javaagent`, `-agentpath` hoặc dynamic attach |
| Workload | Startup, steady state, spike, graceful shutdown |
| Telemetry | Traces, metrics, logs, profiles, JFR |
| Reliability | Crash, error rate, leaks, stalled threads |
| Performance | CPU, RSS/native memory, GC, p95/p99 latency |

Không cần chạy toàn bộ tổ hợp Cartesian nếu tốn kém; có thể ưu tiên những combination thực sự được hỗ trợ và có rủi ro cao. Nhưng các combination nằm trong production support matrix phải có bằng chứng rõ ràng.

### 13.1. Kiểm tra sự tương thích từ vendor

Trước khi nâng JDK:

1. Kiểm tra agent/profiler có hỗ trợ **JDK feature version** mục tiêu không.
2. Xem các bản JDK patch và JVM vendor được hỗ trợ.
3. Kiểm tra OS/architecture của native binaries.
4. Xem release notes của agent về bytecode library, virtual threads và module access.
5. Kiểm tra chính sách dynamic attach ở JDK mục tiêu.
6. Thử APM instrumentation coverage của framework versions.
7. Ghi lại những giới hạn/known issues mà vendor đã công bố.

Không nên dựa vào câu “Java compatible” mà không biết Java version và chức năng instrumentation nào được hỗ trợ.

## 14. Đo overhead của agent và profiler

Một bản nâng JDK có thể khiến overhead của cùng một agent thay đổi do JIT, class loading hoặc GC khác. Cần đo độc lập tác động của từng lớp.

### 14.1. Ma trận bốn thí nghiệm

~~~text
A. JDK cũ + không agent
B. JDK cũ + agent
C. JDK mới + không agent
D. JDK mới + agent
~~~

Từ đó có thể phân biệt:

- **C - A:** khác biệt runtime/JDK khi không có agent.
- **B - A:** overhead agent trên JDK cũ.
- **D - C:** overhead agent trên JDK mới.
- **(D - C) so với (B - A):** thay đổi mức tác động của agent sau migration.

Đây là khung suy luận, không phải phép toán đơn giản áp dụng trực tiếp cho mọi metric. Ví dụ p99 latency chịu tác động phi tuyến từ concurrency, GC và queueing.

### 14.2. Những metric nên ghi

| Metric | Vai trò |
|---|---|
| Throughput | Request/transaction mỗi giây |
| p50/p95/p99 latency | Tác động lên trải nghiệm và SLO |
| CPU process/container | Overhead thực thi và sampling |
| RSS/native memory | Native agent, buffer, symbols, JFR |
| Java heap/GC pause | Allocation từ instrumentation |
| Error/timeouts | Ổn định khi instrumentation hoạt động |
| Class load/transformation counts | Mức hoạt động transformer |
| Trace export queue/dropped spans | Chất lượng APM khi tải cao |
| JFR file size/sampling overhead | Chi phí chẩn đoán |
| Process crash/core dump | Tương thích native agent |

### 14.3. Không lẫn sampling overhead với “chi phí ứng dụng”

Khi profiler đang chạy ở chế độ sampling dày, CPU tăng có thể do profiler; khi APM agent bật trace sampling 100%, latency có thể khác hẳn cấu hình production sampling 1–10%. Cần giữ sampling/exporter settings tương đương thực tế và ghi lại mức cấu hình để giải thích kết quả.

Không nên chạy đồng thời nhiều profiler nặng trong một bài đo rồi kết luận từng profiler riêng lẻ tiêu tốn ít tài nguyên.

## 15. Runbook kiểm thử và triển khai sau nâng JDK

### Giai đoạn A – Inventory

- Liệt kê `-javaagent`, `-agentlib`, `-agentpath` trên JVM startup.
- Tìm agent được inject qua `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, container entrypoint hoặc platform operator.
- Ghi vendor/version của APM, profiler, coverage, debugger và security agent.
- Xác định agent có attach động, lấy JFR hay dùng chỉ JMX.
- Xem JDK, OS, architecture và framework support matrix.

### Giai đoạn B – Kiểm tra tương thích không agent

Chạy artifact ứng dụng trên JDK mục tiêu **không có agents bên thứ ba** trong môi trường thử nghiệm. Ghi baseline startup, throughput, latency, CPU, GC và JFR nếu cần.

Mục đích là biết bản thân ứng dụng/JDK có vấn đề hay không trước khi thêm một lớp instrumentation.

### Giai đoạn C – Bật từng công cụ

Theo thứ tự phù hợp:

1. Bật APM Java agent, kiểm tra startup và traces.
2. Bật metrics exporter/JMX, kiểm tra dashboard labels.
3. Bật profiler native hoặc JFR theo runbook.
4. Bật coverage/security agent nếu production cần.
5. Chạy tổ hợp agents sẽ có trong production.

Ở mỗi bước, xác nhận JVM có thể restart/gracefully shutdown, không crash và không mất telemetry quan trọng.

### Giai đoạn D – So sánh cùng workload

Dùng cùng artifact, dataset, concurrency, container resource limits và khoảng thời gian warmup. Đo overhead và xem p95/p99, error rate, CPU, allocation, native RSS và exporter drops.

Nếu có regression, phân lập theo agent/version/config và log. Không nâng đồng thời JDK, agent, framework và mọi dashboard mà không có phương án xác định nguyên nhân.

### Giai đoạn E – Canary và cảnh báo

Triển khai một tỷ lệ lưu lượng nhỏ nhưng đảm bảo **canary có cùng công cụ giám sát** như production. Kiểm tra:

- Không có lỗi startup/attach.
- Không tăng native crashes.
- APM có spans đại diện.
- Metrics có đủ nhãn và đơn vị.
- Sampling/exporter không quá tải.
- JFR có thể thu thập khi cần.
- Alerts không bị “im lặng” do metric rename.

### Giai đoạn F – Quyết định rollback

Nếu agent mới làm lỗi, có thể rollback **chỉ agent** nếu cấu hình cho phép và sự cố đã được phân lập. Nếu JVM mới làm lỗi ngay cả không agent, cần xem rollback JDK/application. Nhưng đừng hạ JDK mà quên binary compatibility hoặc data-state compatibility với bản cũ.

Rollback cần được kiểm tra riêng: agent version trước có còn chạy trên JDK hiện tại không, và application version cũ có còn xử lý data đã ghi không.

## 16. Bảng chẩn đoán nhanh

| Triệu chứng | Giả thuyết hợp lý | Hướng kiểm tra |
|---|---|---|
| JVM không khởi động khi thêm `-javaagent` | JAR thiếu, manifest lỗi, `premain` ném lỗi | Startup log, JAR, version agent |
| `Unsupported class file major version` | ASM/Byte Buddy/transformer quá cũ | Agent version, class file version |
| `VerifyError` sau khi bật APM | Bytecode transform không hợp lệ/xung đột | So sánh không agent, từng agent |
| JVM crash, có `hs_err_pid` | Native agent/JVM/library lỗi | Problematic frame, native stack, vendor |
| Profiler không attach được | Dynamic attach policy hoặc OS permissions | JDK policy, user, PID namespace |
| `InaccessibleObjectException` | Deep reflection vào module đóng | Agent version, module/opens |
| APM có heartbeat nhưng không có HTTP spans | Instrumentation chưa hỗ trợ framework mới | Agent logs, framework compatibility |
| Trace bị đứt qua async/virtual threads | Context propagation/instrumentation không phù hợp | Trace test, async executor/virtual thread |
| CPU cao chỉ khi có profiler | Sampling quá dày hoặc conflict | Profiler mode/interval, so sánh baseline |
| RSS tăng nhưng Java heap ổn | Native agent/buffer/threads | NMT, native libraries, JFR |
| JFR tool không hiểu event mới | Analyzer quá cũ hoặc schema khác | JDK/JMC versions, `jfr metadata` |
| Metrics dashboard trắng | Metric/label đổi hoặc exporter lỗi | Raw scrape/exporter logs, dashboard |
| Integration test xanh, production không attach | Container security context khác | User, namespace, `seccomp`, perf permissions |
| Startup chỉ lỗi khi có hai agents | Transformer/capability/order conflict | Bật từng agent, điều chỉnh version |
| Test chậm bất thường sau nâng JDK | GC/JIT/framework/agent cùng biến đổi | A/B/C/D performance matrix |

## 17. Bảo mật và dữ liệu nhạy cảm trong observability

Agent và profiler thường có quyền lớn trong tiến trình ứng dụng. Native agent có thể xem bộ nhớ, class state hoặc method arguments; APM có thể ghi HTTP headers, query parameters và SQL statements. Vì vậy chúng cần nằm trong chuỗi cung ứng tin cậy.

Khuyến nghị:

- Lấy agent binaries từ vendor/repository được phép và kiểm tra checksum/provenance.
- Pin version, không tự tải “latest” vào production mà chưa kiểm thử.
- Giới hạn quyền đọc/ghi filesystem và network egress của agent.
- Không để token exporter trong `-D...` hiển thị trong process listings nếu có cơ chế secret an toàn hơn.
- Cấu hình redaction cho thông tin định danh, credentials, payload nhạy cảm.
- Mã hóa telemetry trên đường truyền và kiểm soát retention.
- Giới hạn người có quyền `jcmd`/attach hoặc đọc heap/JFR dumps.
- Thu thập diagnostics theo đúng quy trình phê duyệt và xóa file tạm sau điều tra.

**Một file JFR hoặc heap dump không được coi là file vô hại.** Nó có thể chứa method names, stack traces, đường dẫn nội bộ và một phần dữ liệu nhạy cảm tùy các event/metadata được ghi. Cần quản lý theo chính sách bảo mật tổ chức.

## 18. Checklist sau nâng cấp JDK

- [ ] Đã kiểm kê mọi Java/native agents được nạp khi startup hoặc attach động.
- [ ] Đã xác nhận agent/profiler versions hỗ trợ JDK vendor/build, OS và CPU architecture.
- [ ] Đã kiểm tra class file version và Byte Buddy/ASM của công cụ instrumentation.
- [ ] Đã kiểm tra JVMTI capabilities và chế độ startup/attach.
- [ ] Đã đánh giá JEP 451 và chính sách dynamic agent loading của JDK mục tiêu.
- [ ] Đã kiểm tra `-javaagent`, `-agentpath`, `-agentlib` và injected JVM options.
- [ ] Đã xác định module access/`--add-opens` nào còn cần thiết.
- [ ] Đã thử startup và runtime khi không có agent để có baseline.
- [ ] Đã thử từng agent rồi tổ hợp agents thực tế.
- [ ] Đã kiểm tra APM spans qua HTTP, JDBC, messaging và async context.
- [ ] Đã xác nhận metrics, labels, trace propagation và alert rules.
- [ ] Đã thu JFR hoặc profiler samples với workload đại diện.
- [ ] Đã kiểm tra CPU, p95/p99 latency, allocation, GC, RSS/native memory.
- [ ] Đã test container permissions/PID namespace/perf access cho profiler.
- [ ] Đã ghi lại agent versions, JDK build, OS/kernel và sampling settings.
- [ ] Đã kiểm tra các trường hợp virtual threads hoặc framework instrumentation mới.
- [ ] Đã chuẩn bị cách tắt/rollback agent riêng, và phương án rollback JDK.
- [ ] Đã tuân thủ chính sách bảo vệ dữ liệu trong JFR/heap/profile/trace exports.

## 19. Tài liệu tham khảo chính thức

- [JVM Tool Interface (JDK 25 specification)](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html): agent startup, capabilities, events, bytecode instrumentation, native agent lifecycle.
- [`java.lang.instrument` (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html): Java agents, `premain`/`agentmain` và dynamic loading policy.
- [JEP 451](https://openjdk.org/jeps/451): cảnh báo nạp agent động và định hướng kiểm soát dynamic attach.
- [`jcmd` tool reference (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): JFR, diagnostic commands và JVM introspection.
- [`jfr` tool reference (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): xem và thao tác recording files.
- [Oracle JDK 25 Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): JFR, thread dumps, heap và các công cụ diagnostic.
- [JDK Mission Control](https://openjdk.org/projects/jmc/): công cụ phân tích JFR.
- [OpenTelemetry Java instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/): Java agent và cấu hình observability.
- [async-profiler project](https://github.com/async-profiler/async-profiler): native sampling profiler cho JVM; xem compatibility của phiên bản cụ thể.

Khi nâng từ JDK cũ lên bản mới hơn, cần đối chiếu tài liệu **đúng phiên bản đích** và **đúng version agent/profiler**. Công cụ quan sát thường phát hành độc lập với JDK, vì thế danh sách hỗ trợ có thể đổi nhanh hơn chu kỳ cập nhật của ứng dụng.

## 20. Kết luận

JVMTI và các công cụ agent cho phép quan sát sâu vào JVM nhưng cũng tạo thêm một lớp rủi ro tương thích khi nâng cấp Java. **Native JVMTI agent**, **Java bytecode instrumentation agent**, **JFR/profiler** và **APM** khác nhau về cách nạp, quyền truy cập, tác động hiệu năng và kiểu dữ liệu chúng thu thập.

Một đợt Java Advance Compatibility Migration thành công cần chứng minh **ứng dụng hoạt động đúng khi không agent**, sau đó **agent/profiler/APM vẫn tương thích**, **dữ liệu quan sát còn đầy đủ và chính xác**, và **overhead ở mức chấp nhận được** trên JDK mục tiêu. Hãy kiểm soát dynamic attach, xác minh module/native compatibility, triển khai các công cụ theo từng bước, thử canary và luôn duy trì phương án tắt agent/rollback có kiểm chứng. Công cụ giám sát chỉ phát huy giá trị khi nó giúp chẩn đoán hệ thống mà không trở thành nguyên nhân của sự cố mới.
