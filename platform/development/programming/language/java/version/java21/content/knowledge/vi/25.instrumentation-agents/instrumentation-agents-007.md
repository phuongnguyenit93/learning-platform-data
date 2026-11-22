# Kiểm tra tính tương thích của mocking, coverage, profiler và APM

Trên Java 21, các công cụ mocking, đo coverage, profiler và APM có thể cùng can thiệp vào quá trình nạp lớp hoặc hoạt động bên trong JVM. Một công cụ có thể dùng Java agent lúc startup, công cụ khác tự attach agent khi test bắt đầu, còn profiler có thể dùng JVM TI native agent hoặc JFR tích hợp trong JDK. Vì vậy, kiểm tra tương thích không chỉ là xác nhận công cụ chạy được trên Java 21; cần xác định **cách nạp agent, phiên bản hỗ trợ bytecode, khả năng retransformation, class loader, module access và tương tác giữa nhiều công cụ**.

JEP 451 trong JDK 21 phát cảnh báo khi agent được nạp động vào JVM đang chạy. Dynamic loading vẫn được cho phép mặc định trong JDK 21, nhưng công cụ tự attach có thể phát warning và phụ thuộc vào chính sách sẽ chặt hơn ở các JDK mới. Khi công cụ hỗ trợ startup agent, hãy cấu hình rõ trong JVM chạy ứng dụng hoặc test để giảm phụ thuộc vào dynamic attach.

## 1. Các lớp tương thích cần kiểm tra

Một bộ công cụ instrumentation có thể tương thích ở một khía cạnh nhưng thất bại ở khía cạnh khác. Hãy kiểm tra tối thiểu các lớp sau:

| Lớp tương thích | Câu hỏi cần trả lời | Dấu hiệu lỗi thường gặp |
|---|---|---|
| JDK/runtime | Công cụ hỗ trợ đúng JDK 21 và bản update đang chạy không? | `UnsupportedClassVersionError`, lỗi khởi tạo agent |
| Class file/bytecode | Bytecode Java 21 (major version 65) và các cấu trúc mới có được parser hỗ trợ không? | `IllegalArgumentException`, lỗi ASM/Byte Buddy, `VerifyError` |
| Cơ chế nạp | Công cụ dùng startup agent, dynamic attach, JVM TI hay JFR? | Warning JEP 451, attach bị từ chối |
| Instrumentation capability | Có cần retransformation/redefinition hoặc bootstrap instrumentation không? | Transformer không chạy với lớp đã nạp, API báo không hỗ trợ |
| Class loader/module | Agent nhìn thấy đúng lớp và có quyền truy cập cần thiết không? | `ClassNotFoundException`, `IllegalAccessError`, `InaccessibleObjectException` |
| Tương tác agent | Các transformer có làm thay đổi bytecode của nhau không? | Test lỗi verifier, coverage thiếu, profiler/APM không thấy method |
| Nền tảng native | Profiler/JVM TI library có đúng OS, kiến trúc CPU và runtime không? | Không load được `.so`, `.dylib`, `.dll`, lỗi native crash |
| Vận hành | Agent có được truyền vào đúng JVM process không? | Chạy local được nhưng CI hoặc production thiếu instrumentation |

Không nên đánh giá bằng một smoke test đơn lẻ. Hãy xác nhận từng công cụ riêng, sau đó chạy các tổ hợp thực tế trong cùng một JVM.

Java 21 tiếp tục áp dụng strong encapsulation cho các module của JDK. Nếu agent gặp `InaccessibleObjectException` hoặc `IllegalAccessError`, trước hết kiểm tra phiên bản agent và cách nó truy cập API nội bộ. Chỉ thêm `--add-opens` cho đúng package khi tài liệu của công cụ yêu cầu và đã đánh giá phạm vi; không mở hàng loạt package của JDK như một cách sửa chung.

Khi agent cần retransformation hoặc redefinition, kiểm tra capability mà JVM thực sự cung cấp. Agent JAR có thể khai báo `Can-Retransform-Classes: true` hoặc `Can-Redefine-Classes: true`; code agent nên kiểm tra `Instrumentation.isRetransformClassesSupported()` hoặc `isRedefineClassesSupported()` trước khi dựa vào tính năng đó. Một lớp cụ thể cũng có thể không sửa được; dùng `Instrumentation.isModifiableClass(...)` để kiểm tra thay vì giả định mọi class đều instrument được.

Ví dụ kiểm tra trước khi đăng ký transformer có hỗ trợ retransformation:

```java
if (!instrumentation.isRetransformClassesSupported()) {
    throw new IllegalStateException("JVM không hỗ trợ retransformation");
}

instrumentation.addTransformer(transformer, true);
```

Không phải mọi công cụ đều cần retransformation. Nếu agent chỉ instrument class khi class được nạp lần đầu, không nên bật capability này một cách không cần thiết.

## 2. Những điểm cần lưu ý riêng trên Java 21

### Class file version 65

Java 21 tạo class file với major version 65. Các thư viện phân tích hoặc biến đổi bytecode như Byte Buddy và ASM phải hỗ trợ class file version mà compiler tạo ra. Nếu framework mocking hoặc agent kéo theo một parser bytecode cũ, lỗi có thể xuất hiện khi instrument một lớp mới dù ứng dụng vẫn chạy bình thường khi không bật agent.

Kiểm tra phiên bản của cả công cụ chính lẫn dependency bytecode mà nó sử dụng. Không chỉ nâng plugin build; hãy xác nhận dependency runtime của agent cũng được cập nhật và không bị dependency management ép về phiên bản cũ.

### JEP 451 và dynamic agent loading

JDK 21 phát warning khi Java agent hoặc JVM TI agent được nạp vào JVM đang chạy. Trường hợp thường gặp là mocking framework tự attach Byte Buddy agent khi cần inline mock maker. Startup agent dùng `-javaagent` hoặc native agent dùng `-agentlib`/`-agentpath` không tạo warning JEP 451 theo cơ chế này.

Trên HotSpot JDK 21:

- Mặc định dynamic loading vẫn được cho phép nhưng warning được phát khi agent nạp động.
- `-XX:+EnableDynamicAgentLoading` thể hiện opt-in tường minh và suppress warning.
- `-XX:-EnableDynamicAgentLoading` từ chối nạp agent động, hữu ích để phát hiện phụ thuộc vào self-attach.
- `-Djdk.instrument.traceUsage` giúp truy tìm nơi sử dụng Java Instrumentation API.

Không dùng `-XX:+EnableDynamicAgentLoading` như cách sửa mặc định cho mọi warning. Trước tiên hãy xác định công cụ nào đang attach và xem công cụ đó có hỗ trợ cấu hình startup agent hay không.

## 3. Kiểm tra mocking framework, đặc biệt là inline mocking

Mocking framework có thể tạo mock bằng subclass hoặc bằng cách instrument trực tiếp lớp cần mock. Inline mocking hữu ích khi cần mock final class, final method, static method hoặc constructor tùy khả năng framework. Cơ chế này thường cần Instrumentation API và có thể cần agent.

Với Mockito 5, inline mock maker là mock maker mặc định. Trên JDK 21, cơ chế tự attach agent của thư viện có thể phát warning JEP 451. Tài liệu Mockito hướng dẫn cấu hình Mockito làm startup Java agent để instrumentation có sẵn từ đầu test JVM.

### Cấu hình Mockito làm startup agent trong Gradle Kotlin DSL

Ví dụ sau giả định dự án đã dùng Mockito trong test và muốn cung cấp cùng artifact `mockito-core` cho test runtime lẫn startup agent:

```kotlin
val mockitoAgent = configurations.create("mockitoAgent")

dependencies {
    testImplementation("org.mockito:mockito-core:<version>")
    add("mockitoAgent", "org.mockito:mockito-core:<version>") {
        isTransitive = false
    }
}

tasks.withType<Test>().configureEach {
    jvmArgs("-javaagent:${mockitoAgent.asPath}")
}
```

Thay `<version>` bằng cùng một phiên bản Mockito đã được dự án quản lý. `-javaagent` phải được truyền cho JVM thực thi test. Thêm flag vào Gradle daemon nhưng không vào forked test JVM sẽ không giải quyết được vấn đề.

Nếu dùng Maven Surefire hoặc Failsafe, cấu hình agent trong JVM test tương ứng. Khi JaCoCo cũng quản lý `argLine`, hãy ghép các JVM arguments theo cách plugin hỗ trợ và giữ lại giá trị `argLine` mà JaCoCo tạo ra; ghi đè toàn bộ `argLine` có thể vô tình làm mất JaCoCo agent.

### Chọn đúng mock maker

- Nếu chỉ mock interface hoặc có thể mock bằng subclass, mock maker không cần inline instrumentation có thể giảm phụ thuộc vào agent.
- Nếu cần mock final/static/constructor, kiểm tra chính xác yêu cầu của framework và mock maker đang dùng.
- Không đổi mock maker chỉ để làm mất warning nếu test đang dựa vào hành vi inline mocking.
- Nâng Mockito và Byte Buddy lên phiên bản hỗ trợ JDK 21; kiểm tra release notes thay vì chỉ thay riêng một dependency bắc cầu.

Một test suite chạy thành công nhưng vẫn in warning không có nghĩa instrumentation đã được cấu hình tối ưu. Hãy kiểm tra warning, thử startup agent và thử `-XX:-EnableDynamicAgentLoading` để biết test còn dựa vào self-attach hay không.

## 4. Kiểm tra code coverage với JaCoCo

JaCoCo đo coverage bằng cách instrument bytecode. Agent thường được nạp vào test JVM qua `-javaagent`; plugin Maven/Gradle có thể tự cấu hình bước này. JaCoCo đã hỗ trợ chính thức class file Java 21 từ phiên bản 0.8.11; với dự án hiện tại nên dùng một bản phát hành còn được duy trì và hỗ trợ Java 21, thay vì cố định vào bản tối thiểu nếu đã có bản sửa lỗi mới hơn.

### Maven

JaCoCo Maven Plugin thường dùng goal `prepare-agent` để thêm `-javaagent` vào JVM chạy test và thu file execution data:

```xml
<plugin>
    <groupId>org.jacoco</groupId>
    <artifactId>jacoco-maven-plugin</artifactId>
    <version>${jacoco.version}</version>
    <executions>
        <execution>
            <goals>
                <goal>prepare-agent</goal>
            </goals>
        </execution>
        <execution>
            <id>report</id>
            <phase>verify</phase>
            <goals>
                <goal>report</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

`${jacoco.version}` nên được quản lý tập trung trong Maven properties hoặc version catalog của dự án. Nếu test plugin tự khai báo `argLine`, phải giữ tham số agent JaCoCo được inject bởi `prepare-agent`; cấu hình `argLine` ghi đè có thể làm mất coverage.

### Gradle

Với Gradle, dùng plugin JaCoCo tương thích với Gradle/JDK của dự án và chạy task test trước task report. Plugin quản lý agent và execution data theo task. Không thêm thủ công một JaCoCo `-javaagent` thứ hai nếu plugin đã cấu hình agent cho test JVM.

### Các điểm xác minh

- Agent có được truyền vào đúng forked test JVM không?
- File execution data có được tạo sau khi test chạy không?
- Report có phân tích được class file Java 21 không?
- Các lớp được instrument có phải cùng phiên bản bytecode với class file dùng để tạo report không?
- Có class bị exclude hoặc loader không được agent instrument theo cấu hình không?
- Khi chạy cùng Mockito/APM agent, coverage có thay đổi bất thường không?

Coverage thấp bất thường có thể do test không thực thi code, do class bị exclude, do agent không được nạp vào đúng process hoặc do xung đột instrumentation. Không vội kết luận là lỗi của JaCoCo chỉ từ một báo cáo thiếu dữ liệu.

## 5. Kiểm tra profiler: JFR và native profiler

Profiler không nhất thiết phải là Java agent. Phân biệt cơ chế nạp sẽ giúp tránh áp dụng nhầm chính sách dynamic agent loading.

### Java Flight Recorder (JFR)

JFR được tích hợp trong JDK, có thể bắt đầu ghi khi khởi động:

```shell
java -XX:StartFlightRecording=filename=profile.jfr,dumponexit=true -jar app.jar
```

Hoặc điều khiển recording của tiến trình đang chạy bằng `jcmd` nếu môi trường và quyền vận hành cho phép:

```shell
jcmd <PID> JFR.start name=profile settings=profile duration=60s filename=profile.jfr
```

JFR không cần tự attach một Java agent chỉ để ghi recording thông thường. Vì vậy, JEP 451 không nên bị hiểu là cấm mọi hình thức profiling động; hãy phân biệt JFR với profiler dựa trên agent.

### async-profiler và JVM TI/native agent

Một số profiler như async-profiler có thể khởi động native agent ngay từ đầu bằng `-agentpath`, hoặc dùng công cụ attach để gắn vào JVM đang chạy. Cách attach động có thể chịu cảnh báo/chính sách của JEP 451 vì đây là JVM TI agent được nạp vào tiến trình đã chạy.

Khi kiểm tra profiler, xác minh:

- Binary/native library phù hợp OS, CPU architecture và JDK.
- Quyền truy cập perf events, kernel interfaces và container capabilities nếu profiler yêu cầu.
- Cách khởi chạy là startup (`-agentpath`) hay dynamic attach.
- Profiler có hỗ trợ virtual threads và loại sự kiện cần đo trong phiên bản đang dùng không.
- Overhead khi profiling có chấp nhận được với workload đại diện không.

Không dùng số liệu từ một lần profiling có instrumentation nặng để đại diện trực tiếp cho latency production. So sánh với baseline không bật profiler và ghi rõ cấu hình thu thập.

## 6. Kiểm tra APM agent

APM agent thường dùng Java agent để instrument framework và thư viện phổ biến, ví dụ HTTP server/client, JDBC, messaging và logging. Cách triển khai thông dụng là thêm `-javaagent` vào JVM command line:

```shell
java -javaagent:/opt/agents/opentelemetry-javaagent.jar \
     -Dotel.service.name=orders-api \
     -jar app.jar
```

Với OpenTelemetry Java agent hoặc agent của nhà cung cấp APM khác, cần kiểm tra ma trận hỗ trợ JDK, framework, thư viện client/server, servlet container và database driver. Một agent có thể hỗ trợ Java 21 nhưng chưa instrument một phiên bản framework hoặc thư viện cụ thể.

Các điểm kiểm tra:

- Agent startup có được truyền vào đúng process/container không?
- Agent có log lỗi khi transform một class hoặc không tìm thấy instrumentation module không?
- Các span inbound/outbound, database và messaging có xuất hiện đúng không?
- Context propagation có được giữ qua executor, CompletableFuture và virtual threads theo cách agent hỗ trợ không?
- Có duplicate span hoặc double instrumentation khi dùng đồng thời agent và manual instrumentation không?
- Agent có làm thay đổi latency, allocation rate hoặc startup time vượt ngân sách không?

Không kết luận APM hoạt động chỉ vì ứng dụng khởi động được. Hãy tạo request đại diện và kiểm tra trace/metric/log thực sự đến backend quan sát, với service name và resource attributes đúng.

## 7. Kiểm tra nhiều agent trong cùng một JVM

Mocking, coverage và APM có thể cùng instrument một lớp. JVM gọi transformer theo các nhóm capability (retransformation-incapable/capable và Java/native), rồi theo thứ tự đăng ký trong từng nhóm; kết quả bytecode được chuyển tiếp qua chuỗi transformer. Vì vậy, agent có thể hoạt động riêng nhưng xung đột khi chạy chung.

Các dạng xung đột có thể gặp:

- Một transformer thay đổi cấu trúc method hoặc class theo cách transformer sau không xử lý được.
- Agent không khai báo hoặc không hỗ trợ retransformation nhưng công cụ khác yêu cầu retransformation.
- Agent bỏ qua lớp do class loader, package hoặc include/exclude filter.
- Một công cụ instrument class trước, công cụ khác chỉ nhận bytecode đã được biến đổi.
- Nhiều agent tạo overhead CPU/allocation hoặc thay đổi timing làm test nhạy với thời gian bị flaky.

Hãy thử theo từng bước:

1. Chạy test không agent để có baseline.
2. Chạy chỉ mocking agent.
3. Chạy chỉ coverage agent.
4. Chạy chỉ APM/profiler nếu phù hợp với môi trường test.
5. Chạy các tổ hợp cần có trong pipeline thật.
6. Nếu tổ hợp lỗi, đổi thứ tự startup agent có chủ đích và kiểm tra tài liệu của từng công cụ; không giả định đổi thứ tự luôn sửa được xung đột.

Nhiều `-javaagent` có thể xuất hiện trên cùng command line. Thứ tự cấu hình có thể ảnh hưởng thứ tự transformer và hành vi instrumentation, nên phải giữ ổn định giữa local, CI và production nếu cần so sánh kết quả.

## 8. Kiểm tra đúng JVM chạy test hoặc ứng dụng

Một dự án có thể có nhiều JVM process: Gradle daemon, Maven process, forked test worker, application process và profiler controller. Cấu hình agent vào sai process là nguyên nhân phổ biến khiến công cụ không hoạt động hoặc warning vẫn xuất hiện.

Kiểm tra runtime:

```shell
java -version
```

Kiểm tra command line của JVM đích bằng `jcmd`:

```shell
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
```

Với Gradle, xem log thực thi task test và cấu hình `Test.jvmArgs`; với Maven, kiểm tra cấu hình Surefire/Failsafe và `argLine`. Không dựa vào `JAVA_HOME` một mình nếu build tool hoặc CI image có thể dùng một Java executable khác.

Đối với test forked, `-javaagent` phải có trong command line của test worker. Đối với APM/profiler production, agent phải được gắn vào JVM service thực tế, không chỉ vào shell hoặc tiến trình launcher.

## 9. Ma trận kiểm thử tương thích đề xuất

Nên ghi kết quả theo từng tổ hợp công cụ và chế độ nạp, ví dụ:

| Kịch bản | Mocking | Coverage | Profiler/APM | Mục đích |
|---|---|---|---|---|
| Baseline | Không | Không | Không | Xác nhận ứng dụng/test chạy thuần trên JDK 21 |
| Mocking | Inline hoặc mock maker đang dùng | Không | Không | Kiểm tra agent, Byte Buddy và final/static mocking nếu cần |
| Coverage | Không | JaCoCo | Không | Kiểm tra class file 65, execution data và report |
| Observability | Không | Không | APM startup agent hoặc JFR | Kiểm tra telemetry và overhead |
| Combined test | Có | Có | Theo pipeline | Phát hiện xung đột transformer và agent order |
| Dynamic attach disabled | Công cụ như pipeline | Theo pipeline | Theo pipeline | Chạy với `-XX:-EnableDynamicAgentLoading` để tìm self-attach |

Mỗi lần chạy nên ghi lại:

- JDK vendor, version/update và OS/architecture.
- Phiên bản mocking framework, Byte Buddy/ASM, JaCoCo, profiler và APM agent.
- Command line thực tế của JVM chạy test/application.
- Warning JEP 451, lỗi agent, lỗi transform hoặc verifier.
- Test pass/fail, coverage, trace/metric nhận được và thời gian thực thi.
- CPU, memory và latency khi bật/tắt từng agent nếu cần đánh giá overhead.

## 10. Quy trình xử lý warning hoặc lỗi instrumentation

Khi test hoặc ứng dụng xuất hiện warning JEP 451, `VerifyError`, coverage thiếu hoặc APM không có trace, đi theo trình tự:

1. **Xác định process:** tìm JVM nào phát warning và kiểm tra command line thực tế.
2. **Xác định agent:** đọc path trong warning/log và truy ra thư viện hoặc plugin khởi tạo attach.
3. **Kiểm tra phiên bản:** xác minh công cụ hỗ trợ JDK 21, class file version 65 và framework đang dùng.
4. **Chuyển sang startup agent nếu có:** thêm `-javaagent` hoặc `-agentpath` vào đúng JVM process.
5. **Thử tắt dynamic loading:** chạy test/staging với `-XX:-EnableDynamicAgentLoading` để tìm phụ thuộc còn sót.
6. **Cô lập agent:** chạy từng công cụ riêng, sau đó thêm dần các agent còn lại.
7. **Kiểm tra transform/module/class loader:** đọc log của agent, xác định class bị bỏ qua hoặc lỗi truy cập.
8. **Đo lại:** xác nhận chức năng mocking, coverage, profiling và telemetry; đo overhead khi các agent cùng hoạt động.

Chỉ bật `-XX:+EnableDynamicAgentLoading` trên HotSpot khi dynamic attach là yêu cầu vận hành có chủ đích và công cụ chưa thể chuyển sang startup mode. Flag này phải nằm trên command line của JVM đích; thêm nó vào JVM chạy công cụ attach không thay đổi chính sách của process được attach.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Warning “A Java agent has been loaded dynamically” khi chạy test | Mocking framework hoặc dependency tự attach agent | Cập nhật framework và cấu hình agent startup nếu được hỗ trợ |
| Mockito inline mock không khởi tạo trên JDK mới | Agent/Byte Buddy attach hoặc phiên bản không tương thích | Cấu hình Mockito startup agent và cập nhật dependency đồng bộ |
| `UnsupportedClassVersionError` hoặc lỗi parse class | Công cụ không hiểu class file Java 21 | Nâng công cụ bytecode/agent lên bản hỗ trợ class file 65 |
| JaCoCo không tạo execution data | Agent không vào test JVM, task không chạy hoặc cấu hình `argLine` bị ghi đè | Kiểm tra test process, plugin execution và command line |
| JaCoCo report báo class không khớp | Execution data và class file report không cùng build hoặc bytecode đã thay đổi | Dùng class file đúng build, clean/rebuild và kiểm tra transformer khác |
| Profiler không attach được | Dynamic loading bị tắt, thiếu quyền OS hoặc native library không tương thích | Kiểm tra JDK flag, quyền và binary đúng nền tảng; cân nhắc startup agent/JFR |
| APM agent chạy nhưng không có trace | Instrumentation module không hỗ trợ framework hoặc export cấu hình sai | Kiểm tra agent log, supported libraries, endpoint và resource attributes |
| Một agent chạy riêng nhưng lỗi khi kết hợp | Transformer order, retransformation hoặc class loader xung đột | Thử từng tổ hợp và theo dõi lỗi transform/verifier |
| `-XX:-EnableDynamicAgentLoading` làm test fail | Có công cụ đang phụ thuộc self-attach | Chuyển sang startup agent hoặc thay cách mock/instrument phù hợp |
| Thêm `-javaagent` nhưng warning vẫn còn | Flag vào sai JVM hoặc vẫn còn agent khác tự attach | Kiểm tra PID, command line và stack trace từ `jdk.instrument.traceUsage` |

## 12. Checklist triển khai Java 21

- Xác nhận JDK 21 thực tế của application process và test worker.
- Dùng các phiên bản mocking/coverage/profiler/APM có hỗ trợ Java 21 và class file version 65.
- Xác định công cụ nào dùng startup Java agent, JVM TI agent, dynamic attach hoặc JFR.
- Cấu hình startup agent cho Mockito inline mocking khi framework yêu cầu instrumentation.
- Để plugin JaCoCo quản lý agent và giữ lại JVM arguments mà plugin inject.
- Ưu tiên JFR hoặc startup native agent cho profiling theo cách phù hợp với công cụ.
- Cấu hình APM Java agent trong command line của service và xác minh telemetry end-to-end.
- Chạy từng agent riêng rồi chạy tổ hợp để phát hiện xung đột transformer.
- Kiểm tra class loader, module access, retransformation và native OS/architecture support.
- Thử `-XX:-EnableDynamicAgentLoading` trong CI/staging để phát hiện phụ thuộc self-attach.
- Chỉ opt-in dynamic loading khi có nhu cầu serviceability rõ ràng và được quản lý.
- Đo overhead, latency, startup time và độ ổn định khi bật đầy đủ agent.

Tính tương thích của mocking, coverage, profiler và APM trên Java 21 phụ thuộc cả phiên bản công cụ lẫn cách agent được nạp vào đúng JVM. Hãy xác nhận hỗ trợ class file 65, kiểm tra dynamic attach theo JEP 451, cấu hình startup agent khi có thể và chạy thử từng công cụ trước khi kết hợp. Quy trình này giúp phát hiện sớm lỗi bytecode, warning, xung đột transformer và thiếu telemetry trong CI hoặc production.

## Tài liệu tham khảo

- [JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)
- [Oracle JDK 21 Release Notes — Dynamic Agent Loading](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
- [Mockito — Explicitly setting up instrumentation for inline mocking (Java 21+)](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html)
- [JaCoCo Change History](https://www.jacoco.org/jacoco/trunk/doc/changes.html)
- [OpenTelemetry Java Agent](https://opentelemetry.io/docs/zero-code/java/agent/)
- [async-profiler — Integrating async-profiler](https://github.com/async-profiler/async-profiler/blob/master/docs/IntegratingAsyncProfiler.md)
