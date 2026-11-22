# Java agent, profiler và tài nguyên do công cụ giám sát mở

Java agent, profiler và công cụ giám sát giúp quan sát ứng dụng, đo hiệu năng, thu thập trace hoặc bổ sung instrumentation mà không phải sửa từng class nghiệp vụ. Tuy nhiên, những công cụ này cũng có thể tạo thêm thread, socket, file descriptor, executor, buffer native, hook của JVM và kết nối tới hệ thống telemetry. Khi ứng dụng dùng CRaC, các tài nguyên đó nằm trong cùng tiến trình hoặc gắn với tiến trình cần checkpoint, nên phải được xem xét như một phần của vòng đời ứng dụng.

CRaC không tự động biết cách dừng profiler, flush telemetry, đóng exporter hay khởi tạo lại native agent. Instrumentation đã được áp dụng vào bytecode có thể vẫn là một phần của trạng thái JVM, trong khi các tài nguyên đang hoạt động như socket, sampling thread hoặc file descriptor có thể cần đóng trước checkpoint và tạo lại sau restore. Mức độ tương thích phụ thuộc từng agent, profiler, phiên bản JDK và checkpoint engine.

Muốn dùng công cụ giám sát an toàn với CRaC, trước hết cần xác định cách công cụ được nạp, thành phần nào chạy bên trong JVM, tài nguyên nào do tiến trình bên ngoài sở hữu và nhà cung cấp có hỗ trợ checkpoint/restore hay không. Sau đó thiết kế quy trình dừng, giải phóng, khởi tạo lại và kiểm thử cho đúng từng thành phần.

## 1. Phân biệt Java agent, profiler và monitoring agent

Các tên gọi này có thể chồng lấn nhau. Một APM agent vừa instrument bytecode, vừa thu thập trace, metric và profile. Một profiler có thể là Java agent, native JVMTI agent hoặc tiến trình bên ngoài lấy mẫu từ hệ điều hành.

| Loại công cụ | Mục tiêu chính | Thành phần có thể tạo ra |
|---|---|---|
| Java instrumentation agent | Thay đổi hoặc bổ sung bytecode để quan sát hành vi ứng dụng. | Class transformer, classloader, hook, object cache, thread và cấu hình runtime. |
| APM/monitoring agent | Thu thập metric, trace, log và gửi về backend. | Exporter, queue, scheduler, HTTP/gRPC client, socket, credential và background thread. |
| Java profiler | Đo CPU, allocation, lock contention, call stack hoặc latency. | Sampling thread, timer, recording, event buffer và dữ liệu profile. |
| Native/JVMTI agent | Quan sát hoặc điều khiển JVM ở mức thấp. | Native thread, callback, JVMTI environment, native memory, signal handler và file descriptor. |
| External profiler/controller | Điều khiển hoặc lấy mẫu một JVM từ tiến trình khác. | Kết nối attach, perf event, socket điều khiển và trạng thái gắn với PID/target. |

Điểm cần phân biệt là instrumentation không đồng nghĩa với toàn bộ tài nguyên của agent. Một transformer đã đăng ký có thể vẫn cần thiết sau restore để giữ hành vi instrumented; nhưng thread gửi telemetry hoặc socket tới backend có thể phải được tạo lại.

## 2. Các cách nạp agent vào JVM

Java cung cấp nhiều cơ chế nạp agent. Cách nạp ảnh hưởng đến thời điểm khởi tạo và cách vận hành, nhưng không tự quyết định agent có tương thích CRaC hay không.

### 2.1. Java instrumentation agent qua `-javaagent`

Một Java agent thường được đóng gói trong JAR và khai báo `Premain-Class` trong manifest. JVM gọi phương thức `premain(...)` trước khi gọi `main(...)` của ứng dụng. Agent nhận đối tượng `Instrumentation` để đăng ký `ClassFileTransformer`, truy vấn class đã nạp hoặc yêu cầu retransformation/redefinition nếu được phép.

Ví dụ cách khởi chạy:

```bash
java -javaagent:/opt/agents/monitoring-agent.jar=service=orders -jar application.jar
```

Manifest của agent có thể khai báo:

```text
Premain-Class: com.example.agent.MonitoringAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
```

Ví dụ điểm vào:

```java
public final class MonitoringAgent {

    public static void premain(
            String agentArgs,
            java.lang.instrument.Instrumentation instrumentation) {
        AgentRuntime.install(agentArgs, instrumentation);
    }
}
```

`premain(...)` chạy trong giai đoạn khởi động JVM. Nếu agent khởi tạo kết nối từ xa, mở file hoặc tạo thread ngay tại đây, những tài nguyên đó tồn tại trước khi ứng dụng hoàn tất startup và có thể ảnh hưởng tới checkpoint. Agent nên tách việc đăng ký transformer khỏi việc khởi động exporter hoặc background worker nếu các thành phần sau cần quản lý vòng đời riêng.

### 2.2. Dynamic attach qua `agentmain`

Một số agent được nạp sau khi JVM đã chạy thông qua Attach API. JVM gọi phương thức `agentmain(...)` của agent sau khi attach thành công. Cách này thường được profiler hoặc công cụ chẩn đoán sử dụng để bắt đầu quan sát một tiến trình đang hoạt động.

```java
public final class MonitoringAgent {

    public static void agentmain(
            String agentArgs,
            java.lang.instrument.Instrumentation instrumentation) {
        AgentRuntime.install(agentArgs, instrumentation);
    }
}
```

Với dynamic attach, cần chú ý:

- Agent được cài sau startup nên trạng thái ban đầu khác với agent nạp bằng `-javaagent`.
- Attach có thể bị giới hạn bởi cấu hình JDK, quyền hệ điều hành, container hoặc chính sách bảo mật.
- Việc attach lại sau restore có thể tạo transformer, thread hoặc exporter trùng nếu logic cài đặt không idempotent.
- Tiến trình profiler/controller bên ngoài có vòng đời riêng và có thể cần reconnect hoặc attach lại sau khi JVM restore.

Không nên mặc định rằng agent đã attach trước checkpoint sẽ được công cụ bên ngoài quản lý đúng sau restore. Cần xác nhận cách công cụ nhận diện target, PID, socket điều khiển và trạng thái session.

### 2.3. Native agent qua JVMTI

Các công cụ profiler, debugger và monitoring ở mức thấp có thể dùng JVM Tool Interface (JVMTI). Native agent thường được nạp bằng `-agentlib` hoặc `-agentpath`:

```bash
java -agentlib:sampleprofiler=interval=10 -jar application.jar
```

Hoặc chỉ định đường dẫn thư viện native:

```bash
java -agentpath:/opt/profiler/lib/libsampleprofiler.so=interval=10 -jar application.jar
```

JVMTI cho phép agent đăng ký event callback, yêu cầu capability và truy cập thông tin runtime. Agent chạy trong cùng process với JVM và có thể dùng native memory, native thread, file descriptor hoặc signal. Những thành phần này cần được kiểm tra kỹ khi checkpoint.

Một JVM có thể có nhiều JVMTI agent cùng lúc. Mỗi agent có môi trường JVMTI riêng, nhưng các agent vẫn quan sát và tác động lên cùng VM/native process; một agent có thể ảnh hưởng đến agent khác. Vì vậy, việc một profiler tương thích CRaC không chứng minh các agent còn lại cũng tương thích.

## 3. Những tài nguyên mà agent và profiler có thể mở

Không nên chỉ kiểm tra heap object của agent. Hãy kiểm kê mọi tài nguyên mà công cụ sử dụng.

| Tài nguyên | Ví dụ | Vấn đề khi checkpoint/restore |
|---|---|---|
| Thread Java | Exporter thread, sampler, scheduler, polling worker. | Có thể đang xử lý công việc hoặc chờ I/O; cần dừng ở safe point hoặc khởi tạo lại. |
| Thread native | JVMTI worker, sampling thread, native event loop. | Vòng đời và trạng thái native phụ thuộc agent; cần hướng dẫn từ nhà cung cấp. |
| Socket | HTTP/gRPC exporter, agent control channel, remote profiler. | Peer có thể đóng kết nối trong thời gian checkpoint; thường cần tạo lại. |
| File descriptor | Log file, profile output, perf event, pipe. | File hoặc descriptor có thể không còn hợp lệ trong môi trường restore. |
| Buffer và native memory | Direct buffer, mmap, native allocation. | Cần biết ownership và cách giải phóng/tạo lại. |
| JVM hook | Transformer, JVMTI event callback, native hook. | Có thể vẫn cần giữ để instrumentation tiếp tục; không gỡ tùy tiện. |
| Queue telemetry | Span queue, metric batch, profile samples. | Cần flush hoặc loại bỏ có chủ đích trước checkpoint để tránh mất/lặp dữ liệu. |
| Credential/configuration | Token, endpoint, certificate, API key. | Có thể hết hạn hoặc thay đổi khi tiến trình ngừng chạy; cần nạp lại nếu phù hợp. |

CRaC tạo checkpoint cho trạng thái tiến trình. Nó không đóng vai trò quản lý vòng đời cho backend monitoring hoặc tiến trình profiler ở bên ngoài. Các socket và file đang mở là ví dụ điển hình về tài nguyên cần được giải phóng hoặc xử lý theo chính sách tương thích trước khi checkpoint. 

## 4. Phân biệt trạng thái instrumentation với hoạt động giám sát

Đây là điểm quan trọng khi quyết định nên giữ hay khởi tạo lại thành phần nào.

### 4.1. Instrumentation đã được áp dụng

Một Java agent có thể đăng ký transformer để thay đổi bytecode khi class được nạp. Sau khi class đã được instrument, bytecode đã nạp và trạng thái transformer thuộc về JVM đang chạy.

Không nên gỡ transformer hoặc retransformation tất cả class chỉ vì checkpoint sắp diễn ra. Việc đó có thể:

- Làm mất instrumentation cần thiết sau restore.
- Thay đổi hành vi class trong khi các thread khác vẫn đang chạy.
- Tạo khác biệt giữa class đã nạp và class được nạp sau restore.
- Gây chi phí khởi tạo lớn hoặc làm sai dữ liệu đo.

Hãy xác định agent có cần giữ transformer và instrumentation state hay không. Chỉ gỡ hoặc cài lại khi tài liệu agent yêu cầu. Nếu cần retransformation, phải kiểm tra capability, tính idempotent và thời điểm an toàn.

### 4.2. Exporter và background worker

Exporter gửi dữ liệu telemetry thường có vòng đời độc lập với transformer. Nó có thể giữ HTTP client, gRPC channel, batch queue và scheduled flush. Trước checkpoint, agent có thể:

1. Ngừng nhận span/metric/profile mới hoặc chuyển sang buffer có giới hạn.
2. Chờ các batch đang gửi hoàn tất trong thời hạn cho phép.
3. Flush dữ liệu còn lại theo chính sách.
4. Đóng channel/socket và dừng scheduler/exporter thread.

Sau restore, agent tạo channel mới, nạp credential/configuration hiện hành, khởi động lại scheduler và tiếp tục export. Nếu backend chưa sẵn sàng, cần retry có giới hạn và tránh chặn toàn bộ quá trình restore vô thời hạn.

### 4.3. Sampling và profiler recording

Profiler có thể dùng timer, sampling thread, JFR recording, JVMTI event hoặc native perf event. Cần phân biệt:

- Recording/session có thể được giữ trong trạng thái JVM.
- Sampler thread hoặc native descriptor có thể cần dừng và khởi tạo lại.
- Công cụ điều khiển bên ngoài có thể cần reconnect hoặc attach lại.
- Dữ liệu profile trong lúc checkpoint/restore có thể không đại diện cho workload bình thường.

Không có quy tắc chung rằng mọi profiler tự tiếp tục chính xác sau restore. Hãy theo tài liệu tương thích CRaC của profiler cụ thể. Nếu không có xác nhận, lựa chọn an toàn là dừng recording, giải phóng tài nguyên có thể đóng, rồi khởi tạo recording mới sau restore.

## 5. Tích hợp agent với CRaC Resource API

Nếu agent do nhóm phát triển kiểm soát và có thể quản lý vòng đời, agent có thể đăng ký một `org.crac.Resource` để phối hợp với runtime. Resource nên đại diện cho một nhóm tài nguyên có cùng owner, chẳng hạn telemetry exporter hoặc profiler runtime.

Ví dụ cấu trúc đơn giản:

```java
package com.example.agent;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.lang.instrument.Instrumentation;

public final class MonitoringAgent {

    private static AgentRuntime runtime;

    public static void premain(
            String args,
            Instrumentation instrumentation) {
        install(args, instrumentation);
    }

    public static void agentmain(
            String args,
            Instrumentation instrumentation) {
        install(args, instrumentation);
    }

    private static synchronized void install(
            String args,
            Instrumentation instrumentation) {
        if (runtime != null) {
            return;
        }

        AgentRuntime candidate = AgentRuntime.start(args, instrumentation);
        Core.getGlobalContext().register(candidate);
        runtime = candidate;
    }
}

final class AgentRuntime implements Resource {

    private volatile TelemetryExporter exporter;
    private volatile ProfilerSampler sampler;

    static AgentRuntime start(String args, Instrumentation instrumentation) {
        AgentRuntime runtime = new AgentRuntime();
        runtime.installInstrumentation(instrumentation);
        runtime.startExporter(args);
        runtime.startSampler(args);
        return runtime;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        sampler.pauseAndAwaitSafePoint();
        exporter.flushWithTimeout();
        exporter.close();
        sampler.releaseNativeResources();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        exporter = TelemetryExporter.createAndStart();
        sampler = ProfilerSampler.createAndStart();
    }

    private void installInstrumentation(Instrumentation instrumentation) {
        // Đăng ký transformer một lần; giữ instrumentation nếu cần sau restore.
    }

    private void startExporter(String args) { /* ... */ }
    private void startSampler(String args) { /* ... */ }
}
```

`AgentRuntime`, `TelemetryExporter` và `ProfilerSampler` là abstraction minh họa, không phải class có sẵn trong JDK hoặc CRaC. `install(...)` được đồng bộ và chỉ ghi nhận runtime sau khi tạo và đăng ký thành công; implementation thật vẫn cần tự dọn các thành phần đã khởi tạo một phần nếu `AgentRuntime.start(...)` thất bại. Ví dụ cũng giả định agent đóng gói và sử dụng được `org.crac` compatibility API. Với agent thương mại, hãy dùng cơ chế tích hợp chính thức của nhà cung cấp nếu có; không thêm một Resource thứ hai cùng đóng tài nguyên mà agent đã tự quản lý.

### 5.1. Vì sao cần đăng ký Resource đúng một lần?

Agent có thể được nạp bằng `premain`, dynamic attach hoặc cơ chế framework. Nếu cả hai entry point cùng gọi cài đặt, hoặc công cụ attach lại sau restore, có thể tạo nhiều runtime và đăng ký nhiều Resource cho cùng một exporter.

Hãy thiết kế cài đặt idempotent:

- Chỉ tạo một runtime owner cho mỗi JVM/classloader mà agent quản lý.
- Không đăng ký lặp Resource khi agent được attach nhiều lần.
- Quản lý rõ trường hợp agent dùng classloader riêng hoặc được nạp bởi nhiều module.
- Không giả định một static flag ở classloader khác có thể ngăn cài đặt trùng trên toàn JVM.

Nếu agent hỗ trợ nhiều classloader hoặc nhiều instance, cần có registry có scope rõ ràng thay vì chỉ dựa vào một static boolean đơn giản.

### 5.2. Xử lý lỗi callback

Nếu `beforeCheckpoint(...)` không thể dừng sampler hoặc flush exporter trong deadline, agent cần báo lỗi theo chính sách đã định. Không nên đóng tài nguyên khi sampler vẫn đang dùng chúng hoặc bỏ qua lỗi rồi để checkpoint tiếp tục trong trạng thái không rõ ràng.

Nếu `afterRestore(...)` không tạo lại được exporter hoặc native sampler, agent cần giữ trạng thái không sẵn sàng, retry có giới hạn hoặc báo lỗi để ứng dụng áp dụng degraded/fail-stop policy. Không nên giả vờ telemetry đã hoạt động chỉ vì Resource callback đã được gọi.

## 6. Lưu ý riêng với profiler và native agent

Profiler native có thể phụ thuộc vào tài nguyên hệ điều hành mà Java Resource API không tự hiểu. Ví dụ: perf event descriptor, signal handler, native sampling thread, mmap buffer hoặc file output. Agent cần có API stop/detach và start/attach tương ứng.

Một quy trình tổng quát:

**Trước checkpoint**

1. Ngừng tạo sample mới.
2. Chờ callback đang xử lý hoặc native sampling loop đạt safe point.
3. Flush profile buffer nếu dữ liệu cần giữ.
4. Đóng perf event/file descriptor hoặc giải phóng native handle theo API của profiler.
5. Dừng native thread do agent sở hữu.
6. Giữ lại cấu hình cần thiết để có thể tạo recording mới sau restore.

**Sau restore**

1. Xác minh profiler runtime và native library còn tương thích với môi trường.
2. Tạo lại native handle, buffer và sampling thread.
3. Nạp lại cấu hình, quyền và đường dẫn output.
4. Bắt đầu recording mới hoặc tiếp tục theo khả năng được nhà cung cấp hỗ trợ.
5. Xác minh dữ liệu sample mới thực sự được ghi nhận.

Không tự serialize con trỏ native, `JNIEnv*`, file descriptor hoặc handle nội bộ để phục hồi bằng tay. Các giá trị đó gắn với thread hoặc trạng thái hệ điều hành và phải được tạo/giải phóng qua API chính thức. Với native agent, việc giữ một con trỏ trong heap không làm cho tài nguyên mà con trỏ trỏ tới trở nên hợp lệ sau restore.

## 7. Công cụ profiler chạy ngoài tiến trình

Một số profiler chạy dưới dạng tiến trình riêng và attach vào JVM đích. Tiến trình profiler bên ngoài không phải một phần của checkpoint image của ứng dụng. Khi target được restore:

- Session attach cũ có thể không còn hợp lệ.
- PID hoặc thông tin nhận diện target có thể khác tùy checkpoint engine và cách restore.
- Socket điều khiển hoặc perf event có thể đã bị đóng.
- Profiler có thể cần phát hiện lại JVM, detach session cũ và attach lại.
- Việc attach lại có thể cần quyền hoặc cấu hình đặc biệt trong container.

Hãy phân biệt tài nguyên thuộc JVM đích với tài nguyên thuộc tiến trình profiler/controller. Đừng cố đóng file descriptor của profiler ngoài từ callback Java trong target. Việc reconnect cần do controller hoặc hệ thống orchestration thực hiện theo hướng dẫn công cụ.

Nếu mục tiêu là đo thời gian restore, cần xác định profiler có làm thay đổi startup path hoặc làm chậm restore hay không. Nên có lần chạy baseline không profiler để biết overhead thực tế.

## 8. Monitoring agent và telemetry exporter

Monitoring agent thường có nhiều thành phần hoạt động liên tục:

- Span processor và batch queue.
- Metric reader và periodic exporter.
- Log appender hoặc log shipper.
- HTTP/gRPC client tới telemetry backend.
- Background thread gửi batch và retry.
- Credential provider, TLS context và endpoint configuration.

Trước checkpoint, agent nên dừng việc tạo batch mới hoặc đưa nó vào trạng thái có kiểm soát, flush queue trong thời hạn, đóng channel và tạm dừng scheduler. Sau restore, agent tạo channel mới, nạp lại credential nếu cần và khởi động periodic export.

### 8.1. Tránh mất hoặc gửi lặp telemetry

Nếu checkpoint được tạo sau khi một batch đã được gửi nhưng trước khi agent nhận acknowledgement, sau restore agent có thể gửi lại batch đó. Ngược lại, nếu xóa queue trước khi backend xác nhận, dữ liệu có thể bị mất.

Telemetry thường chấp nhận mức bảo đảm at-least-once hoặc best-effort tùy cấu hình. Hãy hiểu semantics của exporter và backend:

- Flush có bảo đảm đợi acknowledgement từ backend hay chỉ đẩy dữ liệu vào socket?
- Queue có persistent hay chỉ nằm trong heap?
- Exporter có batch ID hoặc deduplication không?
- Khi flush timeout, dữ liệu được giữ, loại bỏ hay retry?
- Timestamp và duration của span có ý nghĩa thế nào khi tiến trình ngừng chạy trong một khoảng dài?

Không thể đưa ra bảo đảm exactly-once chỉ bằng checkpoint/restore. Nếu duplicate telemetry là vấn đề, cần cơ chế deduplication hoặc định danh batch ở tầng exporter/backend.

### 8.2. Credential và cấu hình sau restore

Token telemetry có thể hết hạn trong lúc checkpoint. Endpoint, proxy, certificate hoặc service identity cũng có thể thay đổi. Agent nên lấy credential từ provider theo lifecycle phù hợp, thay vì giả định object token được giữ trong heap luôn hợp lệ.

Không ghi token, API key, header xác thực hoặc payload nhạy cảm vào log để chẩn đoán checkpoint. Checkpoint image có thể chứa object telemetry trong heap, vì vậy cần bảo vệ quyền đọc và thời hạn lưu image.

## 9. Java Flight Recorder và profiler tích hợp trong JDK

Java Flight Recorder (JFR) là cơ chế ghi sự kiện có sẵn trong JDK, khác với một Java agent độc lập. Tuy nhiên, các ứng dụng và công cụ profiling có thể điều khiển JFR qua API hoặc command line, và recording vẫn là một phần của trạng thái quan sát cần được kiểm tra quanh checkpoint.

Trước khi dùng JFR với CRaC, cần quyết định:

- Recording đang chạy có được giữ và tiếp tục đúng như mong đợi trên JDK CRaC đang dùng không?
- Event buffer và dữ liệu chưa ghi ra file được xử lý thế nào?
- Recording có chứa khoảng thời gian checkpoint/restore khiến duration hoặc timestamp khó diễn giải không?
- Có nên dump/stop recording trước checkpoint rồi start recording mới sau restore không?
- File output có được đóng an toàn và mở lại sau restore không?

Không khẳng định JFR recording luôn tiếp tục hoặc luôn phải dừng. Hành vi phụ thuộc JDK distribution, phiên bản, cách recording được cấu hình và hỗ trợ CRaC cụ thể. Hãy kiểm thử trên đúng runtime. Nếu mục tiêu là so sánh hiệu năng sau restore, nên đánh dấu rõ recording trước và sau restore để không gộp thời gian ngừng tiến trình vào cùng một khoảng đo.

## 10. Thứ tự lifecycle và phối hợp nhiều agent

Một JVM có thể có nhiều agent cùng hoạt động. Một agent có thể sở hữu exporter, agent khác sở hữu profiler sampler, còn framework có thể tự quản lý thread pool. Nếu mỗi bên tự đóng và tạo lại tài nguyên mà không biết ownership của nhau, có thể xảy ra:

- Đóng cùng một socket hoặc executor nhiều lần.
- Agent A dừng thread mà agent B vẫn đang chờ.
- Exporter được khởi động lại trước khi credential provider sẵn sàng.
- Profiler attach lại trong khi session cũ chưa detach.
- Nhiều periodic task cùng gửi một loại telemetry.

Hãy lập sơ đồ ownership và dependency. Nếu agent có tài nguyên dùng chung, chỉ một component chịu trách nhiệm đóng/mở. Với nhiều Resource, đăng ký theo thứ tự phụ thuộc được tài liệu CRaC hỗ trợ: `beforeCheckpoint(...)` theo thứ tự đăng ký và `afterRestore(...)` theo thứ tự ngược lại. Nếu quan hệ phức tạp, dùng một coordinator thay vì phụ thuộc vào thứ tự ngầm định giữa các agent không liên quan.

## 11. Cấu hình triển khai khi dùng agent với CRaC

Trước khi tạo checkpoint, ghi lại cấu hình agent chính xác:

- Java command line và thứ tự `-javaagent`, `-agentlib`, `-agentpath`.
- Phiên bản JDK và các JVM option liên quan.
- Phiên bản agent/profiler/native library.
- Các biến môi trường và đường dẫn cấu hình.
- Endpoint, proxy, TLS trust store và credential provider.
- Quyền truy cập perf event, attach, file và socket.
- Các resource được agent đăng ký với CRaC.

Sau restore, phải bảo đảm môi trường có các thư viện native và cấu hình tương thích. Nếu checkpoint được restore trên máy khác, native library, kiến trúc CPU, hệ điều hành và đường dẫn file có thể ảnh hưởng tới khả năng hoạt động. Không dùng checkpoint image như một artifact độc lập với runtime/agent version nếu chưa xác nhận tương thích.

Nếu agent không hỗ trợ CRaC, có thể cần tắt agent trong quá trình tạo checkpoint hoặc dùng chế độ agent được nhà cung cấp khuyến nghị. Nhưng tắt agent có thể làm thay đổi bytecode instrumentation, class state hoặc workload được warm-up; cần đo và kiểm thử riêng thay vì chỉ thêm/bỏ `-javaagent` tùy ý.

## 12. Quy trình kiểm thử agent và profiler qua checkpoint/restore

Nên kiểm thử từng loại công cụ riêng trước khi kết hợp nhiều agent.

### 12.1. Kiểm thử baseline

Chạy ứng dụng không có agent để đo cold start, checkpoint duration, restore duration, time-to-readiness, memory footprint và hành vi request. Đây là mốc so sánh khi bật agent.

### 12.2. Kiểm thử từng agent

Với mỗi agent:

1. Xác định cơ chế nạp: `-javaagent`, `-agentlib`, `-agentpath` hay dynamic attach.
2. Xác định thread, socket, file descriptor, native handle và queue do agent sở hữu.
3. Kiểm tra tài liệu nhà cung cấp về CRaC/checkpoint support.
4. Nếu agent tự quản lý Resource, xác nhận callback được đăng ký và không trùng.
5. Tạo workload đại diện và bắt đầu profiler/monitoring.
6. Dừng/flush tài nguyên theo chính sách trước checkpoint.
7. Tạo checkpoint và restore trên đúng runtime.
8. Xác nhận instrumentation vẫn hoạt động, exporter kết nối lại và profiler tạo sample mới.
9. So sánh overhead, memory và thời gian với baseline.

### 12.3. Kiểm thử nhiều agent cùng lúc

Sau khi từng agent hoạt động độc lập, bật chúng theo cấu hình production. Kiểm tra xung đột transformer, native library, signal handler, thread, exporter và quyền attach. JVMTI cho phép nhiều agent nhưng các agent vẫn tác động lên cùng VM và native process, vì vậy không thể suy ra tương thích tổ hợp từ các lần thử riêng lẻ.

### 12.4. Ma trận tình huống

| Tình huống | Điều cần xác nhận |
|---|---|
| Java agent nạp bằng `-javaagent` | `premain` hoàn tất; transformer cần thiết còn hiệu lực sau restore. |
| Agent nạp bằng dynamic attach | Agent không bị cài trùng khi attach lại; session bên ngoài có thể reconnect. |
| Native JVMTI agent | Native thread, event callback và descriptor được xử lý theo hướng dẫn vendor. |
| Exporter đang gửi batch | Flush có giới hạn; queue không bị mất hoặc gửi lặp ngoài chính sách. |
| Profiler đang sampling | Sampler đạt safe point, native resource được giải phóng và recording mới hoạt động sau restore. |
| Backend telemetry không sẵn sàng | Agent retry có giới hạn và không chặn ứng dụng vô thời hạn. |
| Token hết hạn khi checkpoint | Agent lấy credential mới hoặc giữ trạng thái export lỗi có thể quan sát. |
| Hai agent dùng chung native hook | Không xung đột signal, callback hoặc class transformer. |
| Agent callback thất bại | Checkpoint/restore lỗi được truyền ra; không giả định công cụ vẫn hoạt động. |

## 13. Chẩn đoán khi checkpoint hoặc restore gặp lỗi với agent

Khi checkpoint thất bại, hãy phân loại lỗi theo chủ sở hữu:

- Resource Java do agent đăng ký báo lỗi trong `beforeCheckpoint(...)`.
- File hoặc socket do agent mở vẫn còn hoạt động.
- Native agent giữ descriptor, thread hoặc handle không được checkpoint engine hỗ trợ.
- Profiler bên ngoài đang attach hoặc giữ session điều khiển.
- Agent exporter bị treo trong flush hoặc chờ backend.
- Sau restore, agent không khởi động lại được do thiếu thư viện, quyền hoặc credential.

Một số CRaC-enabled JDK có tùy chọn chẩn đoán để liệt kê resource hoặc dump heap khi checkpoint thất bại. Cờ JVM và output phụ thuộc distribution; hãy dùng tài liệu đúng JDK. Không bật cờ vendor-specific trong mọi môi trường rồi giả định chúng có trên tất cả JDK CRaC.

Thu thập thông tin:

- JDK vendor, version, build và OS/kernel.
- Agent/profiler version, cách nạp và command line đầy đủ.
- Log agent trước checkpoint và sau restore.
- Thread dump và danh sách file descriptor khi có thể.
- Lỗi callback, native library hoặc checkpoint engine.
- Trạng thái exporter, profiler session và backend.

Không đưa secret hoặc telemetry payload nhạy cảm vào báo cáo lỗi. Khi cần tái hiện, giảm cấu hình xuống một agent để khoanh vùng rồi bật lại từng thành phần.

## 14. Những lỗi thiết kế thường gặp

**Cho rằng Java agent chỉ thêm bytecode nên không có tài nguyên cần xử lý.** Agent có thể tạo exporter, thread, socket, native memory và file descriptor. Hãy kiểm kê runtime component chứ không chỉ transformer.

**Gỡ mọi transformer trước checkpoint.** Việc này có thể làm mất instrumentation cần thiết sau restore và khiến class state không nhất quán. Chỉ thay đổi transformer khi vendor yêu cầu.

**Giữ nguyên exporter vì object vẫn tồn tại trong heap.** Socket hoặc TLS session có thể đã bị peer đóng. Tạo lại channel sau restore theo lifecycle phù hợp.

**Flush telemetry vô hạn trong callback.** Backend có thể không sẵn sàng và làm checkpoint treo. Đặt deadline, chính sách giữ/bỏ queue và trạng thái lỗi rõ ràng.

**Attach lại profiler mà không kiểm tra session cũ.** Có thể tạo sampling thread, transformer hoặc recording trùng. Cần detach/reconnect idempotent.

**Cho rằng native agent tự tương thích vì Java agent khác đã chạy được.** JVMTI agent dùng native state và có thể phụ thuộc OS resource riêng. Kiểm tra từng agent và tổ hợp.

**Đưa profiler ngoài tiến trình vào giả định checkpoint của target.** Controller ngoài không nằm trong checkpoint image. Phải quản lý session ở controller/orchestrator.

**Coi exit code của checkpoint là bằng chứng agent hoạt động.** Cần xác minh sample, trace, metric và kết nối thực tế sau restore.

## 15. Checklist tích hợp agent, profiler và monitoring với CRaC

- [ ] Liệt kê mọi Java agent, native agent, profiler và monitoring tool.
- [ ] Ghi rõ cách nạp: `-javaagent`, `-agentlib`, `-agentpath` hoặc dynamic attach.
- [ ] Ghi phiên bản JDK, agent, profiler và native library.
- [ ] Xác định transformer/instrumentation nào cần giữ sau restore.
- [ ] Liệt kê thread, executor, socket, file descriptor, buffer native và queue do agent sở hữu.
- [ ] Kiểm tra tài liệu hỗ trợ CRaC chính thức của từng nhà cung cấp.
- [ ] Đăng ký Resource nếu agent tự quản lý được và API tương thích.
- [ ] Dừng sampler/worker tại safe point trước checkpoint.
- [ ] Flush exporter trong deadline và xử lý queue theo semantics rõ ràng.
- [ ] Đóng socket, file và native handle cần tạo lại.
- [ ] Sau restore, tạo lại exporter, sampler và credential cần thiết.
- [ ] Ngăn đăng ký Resource, transformer, thread hoặc periodic task trùng lặp.
- [ ] Quản lý profiler/controller ngoài tiến trình bằng reconnect/reattach riêng.
- [ ] Kiểm thử từng agent độc lập và kiểm thử tổ hợp production.
- [ ] Xác nhận trace, metric, profile và instrumentation hoạt động sau restore.

## 16. Thuật ngữ cần nhớ

- **Java agent:** JAR được JVM nạp qua instrumentation API, thường có `premain` hoặc `agentmain`.
- **`premain`:** entry point của agent được nạp khi JVM khởi động qua `-javaagent`.
- **`agentmain`:** entry point của agent được nạp sau startup qua cơ chế attach.
- **Instrumentation:** cơ chế thêm hoặc thay đổi bytecode để quan sát/chỉnh sửa hành vi class.
- **`ClassFileTransformer`:** thành phần nhận class bytes và trả về bytecode đã biến đổi.
- **JVMTI:** giao diện native cho profiler, debugger và công cụ phân tích JVM.
- **Native agent:** agent dùng thư viện native và thường tương tác với JVM qua JVMTI/JNI.
- **Dynamic attach:** cơ chế gắn agent vào JVM đang chạy.
- **Exporter:** thành phần gửi telemetry tới backend.
- **Sampler:** thành phần lấy mẫu thread, stack hoặc sự kiện để tạo dữ liệu profile.
- **Telemetry queue:** hàng đợi chứa span, metric, log hoặc profile chưa export.
- **CRaC Resource:** đối tượng đăng ký callback `beforeCheckpoint(...)` và `afterRestore(...)` để quản lý vòng đời tài nguyên.

Java agent, profiler và monitoring tool có thể tiếp tục cung cấp giá trị sau restore nếu từng phần của chúng được quản lý đúng vòng đời. Hãy giữ instrumentation cần thiết, dừng và giải phóng những thread, kết nối và native handle không thể dùng qua checkpoint, rồi khởi tạo lại exporter hoặc sampler sau restore. Với công cụ bên thứ ba, chỉ dựa vào hỗ trợ CRaC đã được nhà cung cấp xác nhận và kiểm thử trên đúng JDK, agent version cùng môi trường triển khai.

## Tài liệu tham khảo

- [Java Instrumentation API — Java SE](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `premain`, `agentmain`, `Instrumentation` và class transformation.
- [Java Instrumentation Package Specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): cách JVM nạp Java agent và yêu cầu entry point.
- [JVM Tool Interface (JVMTI) Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jvmti.html): agent environment, event callbacks, capabilities và nhiều JVMTI agent cùng tồn tại.
- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore và trách nhiệm phối hợp tài nguyên của ứng dụng.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): Resource API và cách ứng dụng giải phóng/tạo lại tài nguyên.
