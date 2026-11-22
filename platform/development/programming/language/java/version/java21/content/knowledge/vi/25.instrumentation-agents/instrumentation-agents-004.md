# Nhận diện thư viện kiểm thử hoặc quan sát đang tự attach agent

## 1. Vì sao thư viện tự attach agent?

Java agent là thành phần chạy bên trong JVM và có thể quan sát hoặc thay đổi bytecode của ứng dụng. Agent thường được dùng cho profiler, APM, công cụ kiểm thử, coverage, mocking nâng cao và các công cụ chẩn đoán runtime.

Một số thư viện không yêu cầu người dùng cấu hình agent ngay từ lúc khởi động JVM. Thay vào đó, khi một tính năng được sử dụng lần đầu, thư viện tìm hoặc đóng gói một agent rồi **attach vào JVM đang chạy** để cài transformer hoặc thực hiện instrumentation. Cơ chế này thường được gọi là dynamic attach hoặc self-attach, dù thư viện có thể tạo một tiến trình phụ để thực hiện thao tác attach vào JVM đích.

Ví dụ, một số phiên bản/cấu hình của thư viện mocking inline sử dụng Byte Buddy agent để hỗ trợ mock final class, static method hoặc constructor. Một số profiler và công cụ quan sát cũng có chế độ attach vào tiến trình đang chạy để bắt đầu instrumentation mà không cần restart ứng dụng.

Không phải mọi thư viện kiểm thử hoặc quan sát đều tự attach. Nhiều công cụ dùng agent được nạp ngay lúc JVM khởi động, hoặc chỉ sử dụng API Java/JMX/JFR mà không cần Java agent. Cần nhận diện đúng cơ chế thực tế thay vì suy luận chỉ từ tên thư viện.

## 2. Phân biệt startup agent và dynamic attach

Java hỗ trợ hai cách phổ biến để khởi chạy agent:

| Cách nạp | Thời điểm | Manifest entry | Entry point |
|---|---|---|---|
| Startup Java agent | Khi JVM khởi động, trước `main` | `Premain-Class` | `premain(...)` |
| Dynamic Java agent | Sau khi JVM đã chạy | `Agent-Class` | `agentmain(...)` |

### 2.1. Startup agent qua `-javaagent`

Agent có thể được chỉ định trực tiếp trên command line:

```bash
java -javaagent:/opt/agents/observability-agent.jar -jar application.jar
```

JAR phải khai báo `Premain-Class` trong manifest. JVM gọi `premain` trước khi gọi `main` của ứng dụng:

```java
import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    public static void premain(String arguments, Instrumentation instrumentation) {
        // Đăng ký ClassFileTransformer hoặc khởi tạo instrumentation.
    }
}
```

Có thể khai báo nhiều `-javaagent` trên cùng command line. JVM gọi `premain` theo thứ tự agent xuất hiện. Startup agent là lựa chọn phù hợp khi ứng dụng hoặc môi trường triển khai đã biết trước agent cần dùng.

Native JVM TI agent cũng có thể được nạp lúc khởi động qua `-agentlib` hoặc `-agentpath`. Những agent được nạp bằng các startup option này không phải dynamic attach sau khi JVM chạy.

### 2.2. Dynamic attach vào JVM đang chạy

Với dynamic Java agent, JAR khai báo `Agent-Class` và class agent có method `agentmain`:

```java
import java.lang.instrument.Instrumentation;

public final class DynamicAgent {
    public static void agentmain(String arguments, Instrumentation instrumentation) {
        // Khởi tạo agent sau khi JVM đích đã chạy.
    }
}
```

Một công cụ attach có thể dùng Attach API để kết nối đến tiến trình JVM đích rồi nạp agent:

```java
import com.sun.tools.attach.VirtualMachine;

static void attachAgent(String pid, String agentJar) throws Exception {
    VirtualMachine vm = VirtualMachine.attach(pid);
    try {
        vm.loadAgent(agentJar, "mode=test");
    } finally {
        vm.detach();
    }
}
```

Đây là code của tiến trình công cụ attach, không phải code chạy bên trong ứng dụng đích. Module chứa code này cần truy cập `jdk.attach`. Một thư viện có thể che giấu các bước trên trong helper class hoặc tiến trình phụ, vì vậy người dùng chỉ thấy cảnh báo xuất hiện khi chạy test.

Một JAR có thể đồng thời khai báo cả `Premain-Class` và `Agent-Class`. Chỉ nhìn manifest chưa đủ để kết luận agent đã được nạp bằng cách nào; cần kiểm tra command line, log và trace lúc chạy.

## 3. Cảnh báo dynamic agent loading trong Java 21

JEP 451 được đưa vào JDK 21 để chuẩn bị hạn chế dynamic loading agent trong tương lai. Trong Java 21, dynamic loading vẫn được cho phép mặc định, nhưng JVM phát cảnh báo khi Java agent hoặc JVM TI agent được nạp vào một JVM đang chạy.

Ví dụ cảnh báo có thể có dạng:

```text
WARNING: A Java agent has been loaded dynamically (/path/to/byte-buddy-agent.jar)
WARNING: If a serviceability tool is in use, please run with -XX:+EnableDynamicAgentLoading to hide this warning
WARNING: If a serviceability tool is not in use, please run with -Djdk.instrument.traceUsage for more information
WARNING: Dynamic loading of agents will be disallowed by default in a future release
```

Đường dẫn JAR trong dòng đầu là manh mối quan trọng: nó cho biết agent nào vừa được nạp. Nếu thấy `byte-buddy-agent`, hãy kiểm tra dependency tree để tìm thư viện nào kéo Byte Buddy vào và gọi cơ chế attach.

Các điểm cần hiểu đúng:

- Đây là cảnh báo về agent được nạp **sau khi JVM đã khởi động**.
- Agent được nạp từ đầu bằng `-javaagent`, `-agentlib` hoặc `-agentpath` không tạo cảnh báo dynamic loading này.
- Trong Java 21, cảnh báo chưa có nghĩa thao tác attach đã bị chặn; agent vẫn có thể được nạp nếu JVM cho phép.
- Cảnh báo nhằm chuẩn bị cho thay đổi bảo mật ở release tương lai, nơi dynamic loading dự kiến bị tắt mặc định.
- Cảnh báo thường nhận diện agent qua đường dẫn JAR hoặc thư viện native được nạp.

Không nên bỏ qua cảnh báo trong CI chỉ vì test vẫn chạy thành công. Nó có thể chỉ ra một dependency đang dựa vào khả năng sửa đổi JVM sau startup và cần được chuẩn bị trước khi nâng JDK.

## 4. Nhận diện thư viện từ warning và stack trace

Khi warning xuất hiện, hãy bắt đầu từ JAR path:

```text
WARNING: A Java agent has been loaded dynamically (/home/runner/.m2/repository/net/bytebuddy/byte-buddy-agent/1.x/byte-buddy-agent-1.x.jar)
```

Đường dẫn này cho biết agent artifact. Nó chưa chắc là thư viện trực tiếp mà code test gọi. Ví dụ, test có thể dùng Mockito, MockK hoặc một framework khác; framework đó gọi Byte Buddy; Byte Buddy agent mới là JAR thực sự được attach.

Hãy phân biệt ba khái niệm:

1. **Agent artifact**: JAR được nạp vào JVM, ví dụ `byte-buddy-agent`.
2. **Thư viện kích hoạt attach**: dependency gọi Attach API hoặc một helper của agent.
3. **Tính năng làm phát sinh attach**: ví dụ inline mocking, class redefinition hoặc bắt đầu profiler.

Để tìm đúng dependency gốc, cần lần theo stack trace và dependency graph thay vì chỉ loại bỏ JAR xuất hiện trong warning.

## 5. Dùng `-Djdk.instrument.traceUsage` để tìm nơi gọi Instrumentation API

Java 21 cung cấp system property `jdk.instrument.traceUsage`. Khi bật property này, các lần sử dụng API `java.lang.instrument` sẽ in thông tin trace và stack trace, giúp xác định code path liên quan đến instrumentation.

Khởi chạy ứng dụng hoặc test JVM với:

```bash
java -Djdk.instrument.traceUsage=true -jar application.jar
```

Với Maven Surefire, có thể truyền property vào JVM chạy test thông qua cấu hình `argLine`:

```xml
<configuration>
    <argLine>-Djdk.instrument.traceUsage=true</argLine>
</configuration>
```

Nếu build đã dùng `argLine` cho JaCoCo hoặc agent khác, phải kết hợp property vào cấu hình hiện có; không ghi đè làm mất các JVM argument đã được plugin thêm vào.

Với Gradle, thêm JVM argument cho test worker:

```groovy
tasks.withType(Test).configureEach {
    jvmArgs '-Djdk.instrument.traceUsage=true'
}
```

Đặt property trên đúng JVM thực thi test. Trong môi trường có Gradle daemon, test worker riêng, Maven fork hoặc IDE, JVM nhận property có thể khác JVM đang chạy build tool.

Khi đọc trace:

- Tìm class nằm ngoài JDK, đặc biệt package của mocking framework, bytecode library hoặc profiler.
- Lần theo stack từ lời gọi `Instrumentation` về framework đang khởi tạo tính năng.
- Ghi nhận test class hoặc thao tác cụ thể khiến agent được kích hoạt.
- So sánh trace khi bật/tắt tính năng nghi ngờ để xác định dependency nào thực sự cần instrumentation.

`jdk.instrument.traceUsage` là công cụ chẩn đoán. Nó không phải cách cho phép attach và không thay thế cấu hình agent. Sau khi xác định xong nguyên nhân, bỏ property này khỏi cấu hình thông thường nếu không còn cần trace.

Property này theo dõi việc sử dụng API `java.lang.instrument`; nó không phải bộ trace tổng quát cho mọi lệnh Attach API hoặc mọi native JVM TI agent. Nếu warning nói về JVM TI agent native, hãy dùng đường dẫn thư viện trong warning, log của profiler/serviceability tool và command line để truy ngược nguồn nạp.

## 6. Tìm dependency kéo agent vào test runtime

Agent thường là dependency bắc cầu (transitive dependency). Kiểm tra runtime classpath của test thay vì chỉ nhìn dependency trực tiếp trong file build.

### 6.1. Maven

Liệt kê dependency test và tìm các artifact liên quan đến Byte Buddy:

```bash
mvn dependency:tree -Dscope=test -Dincludes=net.bytebuddy:*
```

Nếu warning nêu tên một artifact khác, thay filter bằng group/artifact tương ứng hoặc xem toàn bộ test dependency tree:

```bash
mvn dependency:tree -Dscope=test
```

Xác định dependency cha trong cây để biết framework nào kéo agent vào. Đừng xóa trực tiếp dependency bắc cầu khi framework vẫn cần nó; hãy xem phiên bản framework và hướng dẫn cấu hình instrumentation.

### 6.2. Gradle

Xem test runtime classpath:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Tra ngược dependency cụ thể:

```bash
./gradlew dependencyInsight --dependency byte-buddy-agent --configuration testRuntimeClasspath
```

Trên Windows có thể dùng `gradlew.bat` thay cho `./gradlew`. Nếu test dùng configuration khác, hãy thay bằng đúng configuration mà task test đang chạy.

### 6.3. Kiểm tra command line của JVM

`jcmd` có thể hiển thị command line của JVM đang chạy:

```bash
jcmd <pid> VM.command_line
```

Nếu agent xuất hiện dưới dạng `-javaagent:...`, đó là startup agent. Nếu warning xuất hiện nhưng command line không có agent tương ứng, đây là manh mối cho dynamic attach; hãy dùng `traceUsage` và log để xác nhận.

Command line chỉ cho biết argument lúc khởi động. Nó không liệt kê đầy đủ các agent được nạp sau startup.

## 7. Kiểm tra manifest của agent JAR

Manifest cho biết JAR có khả năng khởi chạy theo cơ chế nào. Có thể đọc `META-INF/MANIFEST.MF` bằng `jar` hoặc một đoạn Java nhỏ:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;

static void inspectAgentManifest(Path jarPath) throws IOException {
    try (JarFile jar = new JarFile(jarPath.toFile())) {
        if (jar.getManifest() == null) {
            System.out.println("No manifest");
            return;
        }

        Attributes attributes = jar.getManifest().getMainAttributes();
        System.out.println("Premain-Class: " + attributes.getValue("Premain-Class"));
        System.out.println("Agent-Class: " + attributes.getValue("Agent-Class"));
        System.out.println("Can-Redefine-Classes: " + attributes.getValue("Can-Redefine-Classes"));
        System.out.println("Can-Retransform-Classes: " + attributes.getValue("Can-Retransform-Classes"));
    }
}
```

Ý nghĩa:

- `Premain-Class`: entry point dành cho startup Java agent qua `-javaagent`.
- `Agent-Class`: entry point dành cho dynamic Java agent được nạp vào JVM đang chạy.
- `Can-Redefine-Classes`: agent khai báo nhu cầu redefine class.
- `Can-Retransform-Classes`: agent khai báo nhu cầu retransform class.

Nếu cả `Premain-Class` và `Agent-Class` cùng có mặt, JAR có thể hỗ trợ cả hai cơ chế. Manifest chỉ mô tả khả năng; cần xem command line và runtime trace để xác định lần chạy cụ thể đã sử dụng cơ chế nào.

## 8. Những thư viện thường cần kiểm tra

Một số nhóm thư viện có thể liên quan đến agent loading:

| Nhóm | Ví dụ hoặc dấu hiệu | Điều cần kiểm tra |
|---|---|---|
| Bytecode manipulation | Byte Buddy, ASM-based instrumentation | Có artifact agent riêng và code gọi attach hay không |
| Mocking nâng cao | Một số phiên bản/cấu hình Mockito inline, MockK hoặc framework mock final/static | Tính năng nào kích hoạt inline mock maker; framework hỗ trợ startup agent không |
| Code coverage | JaCoCo hoặc agent coverage khác | Thường được cấu hình startup bằng `-javaagent`; xác minh command line và plugin build |
| APM/observability | Java agent của OpenTelemetry, Elastic APM hoặc agent vendor | Được nạp startup qua `-javaagent` hay được attach bởi một công cụ quản trị |
| Profiler/diagnostic | Công cụ profiler hoặc serviceability tool | Attach có chủ đích khi operator bắt đầu phiên profiling hay bị dependency tự kích hoạt |

Các tên trên là gợi ý điều tra, không phải kết luận rằng mọi phiên bản đều dynamic attach. Ví dụ, JaCoCo thường chạy như startup agent do build plugin cấu hình; việc thấy JaCoCo trong test classpath không tự chứng minh nó gây warning dynamic attach. Tương tự, APM agent thường được triển khai bằng `-javaagent`, nhưng một số công cụ có chế độ attach riêng.

Với Mockito hoặc MockK, hành vi phụ thuộc phiên bản, mock maker và cấu hình test. Nếu warning chỉ xuất hiện khi test mock final class, static method hoặc constructor, hãy kiểm tra cấu hình inline mocking và dependency Byte Buddy được framework sử dụng.

## 9. Phân biệt warning với lỗi test

Trong Java 21, warning của JEP 451 thường không làm test thất bại ngay. Dynamic loading vẫn được phép mặc định, vì vậy test có thể tiếp tục chạy thành công sau khi in warning.

| Kết quả | Diễn giải |
|---|---|
| Warning xuất hiện, test pass | Agent đã được nạp động; cần xác định dependency và chuẩn bị cho chính sách JDK tương lai |
| Không có warning, test pass | Có thể agent được nạp từ startup, không dùng agent hoặc đường code attach không chạy; chưa đủ để kết luận không có instrumentation |
| Có warning rồi `AgentLoadException`/lỗi khởi tạo | Attach hoặc khởi tạo agent thất bại; kiểm tra quyền attach, manifest, phiên bản agent và JVM |
| Test fail khi tắt dynamic loading | Một tính năng đang phụ thuộc vào attach sau startup; cần chuyển sang startup agent hoặc thay đổi dependency/configuration |

Đừng bỏ qua một test fail chỉ bằng cách thêm cờ bật dynamic loading. Trước tiên cần xác định agent có phải thành phần cần thiết, có tương thích JDK đang dùng và có nguồn gốc đáng tin cậy không.

## 10. Cách xử lý theo nguyên nhân

### 10.1. Thư viện hỗ trợ startup agent

Ưu tiên cấu hình agent lúc khởi động JVM nếu tài liệu thư viện hỗ trợ. Ví dụ tổng quát:

```bash
java -javaagent:/path/to/approved-agent.jar -jar application.jar
```

Với test, truyền `-javaagent` vào đúng JVM test worker hoặc forked test process. Không chỉ thêm vào JVM của Maven/Gradle daemon nếu test thực tế chạy trong process khác.

Startup agent phải có `Premain-Class`. Không thể tùy tiện lấy mọi JAR có `Agent-Class` rồi dùng làm `-javaagent`; hãy dùng đúng artifact và cách cấu hình được nhà cung cấp hỗ trợ.

### 10.2. Dynamic attach là chủ đích của công cụ vận hành

Nếu operator hoặc serviceability tool cần attach vào JVM đang chạy, có thể opt in rõ ràng trên HotSpot:

```bash
java -XX:+EnableDynamicAgentLoading -jar application.jar
```

Trong Java 21, tùy chọn này cho phép dynamic loading và ngăn warning tương ứng. Đây là sự chấp thuận rõ ràng cho khả năng nạp code agent vào JVM đang chạy; nó không loại bỏ dynamic attach và không thay thế việc đánh giá độ tin cậy của agent.

Không bật cờ này toàn cục chỉ để làm log sạch nếu chưa biết thư viện nào đang attach. Hãy giới hạn phạm vi ở JVM thực sự cần công cụ serviceability đó.

### 10.3. Kiểm tra hành vi tương lai bằng cách tắt dynamic loading

Trên HotSpot Java 21, có thể chạy thử với:

```bash
java -XX:-EnableDynamicAgentLoading -jar application.jar
```

Tùy chọn này từ chối agent được nạp động. Dùng trong một job CI hoặc môi trường test riêng để tìm dependency còn phụ thuộc attach. Một số công cụ quản trị đang được dùng có chủ đích cũng có thể không hoạt động; hãy đánh giá kết quả theo chức năng cần kiểm thử.

### 10.4. Nâng cấp hoặc thay đổi dependency

Nếu thư viện kiểm thử tự attach chỉ để hỗ trợ một tính năng, hãy kiểm tra release note và hướng dẫn mới nhất của thư viện:

- Phiên bản mới có hỗ trợ khai báo startup agent không?
- Có mock maker hoặc chế độ khác không cần inline instrumentation không?
- Có thể thay thế test phụ thuộc static/final mocking bằng dependency injection hoặc seam kiểm thử rõ ràng không?
- Agent artifact có thể được nạp một lần ở startup test worker thay vì attach trong mỗi lần chạy test không?

Không xóa agent JAR bắc cầu một cách tùy tiện. Framework có thể cần đúng phiên bản đó để khởi tạo instrumentation; loại bỏ có thể làm lỗi test hoặc gây `NoClassDefFoundError`/`AgentInitializationException`.

## 11. Rủi ro bảo mật và quyền hạn của agent

Agent chạy trong tiến trình JVM đích và có thể được cấp `Instrumentation` để transform class, retransform hoặc redefine class nếu manifest và JVM cho phép. Một agent có thể quan sát hoặc thay đổi hành vi code trong tiến trình; vì vậy, quyền nạp agent tương đương một khả năng rất mạnh.

Trước khi cho phép agent:

- Xác minh nguồn tải, phiên bản, checksum/signature và chuỗi cung ứng dependency.
- Kiểm tra agent có đến từ dependency trực tiếp hay transitive dependency không mong muốn.
- Chỉ cho phép attach trên JVM và môi trường thực sự cần thiết.
- Tránh bật `-XX:+EnableDynamicAgentLoading` rộng khắp chỉ để che warning.
- Không tải agent JAR từ nguồn không tin cậy vào JVM đang giữ credential hoặc dữ liệu nhạy cảm.
- Trong CI, dùng dependency lock/version pinning và theo dõi thay đổi agent artifact.

JEP 451 hướng tới cải thiện integrity mặc định của JVM bằng cách yêu cầu ứng dụng opt in rõ ràng khi cần dynamic agent loading. Đây là lý do cảnh báo cần được xem như tín hiệu về quyền hạn runtime, không chỉ là thông báo thẩm mỹ.

## 12. Quy trình điều tra trong dự án thực tế

Khi test hoặc ứng dụng in warning dynamic agent loading, thực hiện theo thứ tự:

1. **Lưu nguyên warning**: ghi lại tên và đường dẫn agent JAR, loại agent và JVM process phát warning.
2. **Xác định process**: kiểm tra test worker, Maven/Gradle fork, IDE hoặc process production; không mặc định warning thuộc build daemon.
3. **Bật trace tạm thời**: chạy đúng JVM với `-Djdk.instrument.traceUsage=true` để lấy stack trace sử dụng Instrumentation API.
4. **Tra dependency graph**: dùng Maven `dependency:tree` hoặc Gradle `dependencyInsight` để tìm dependency kéo agent và framework kích hoạt nó.
5. **Kiểm tra startup arguments**: dùng `jcmd <pid> VM.command_line` hoặc cấu hình build để phân biệt agent startup với dynamic attach.
6. **Kiểm tra manifest và tài liệu thư viện**: xác định `Premain-Class`, `Agent-Class`, tính năng cần agent và cách cấu hình được hỗ trợ.
7. **Chọn hướng xử lý**: startup agent, nâng cấp/thay dependency, hoặc opt in dynamic loading cho công cụ vận hành được phê duyệt.
8. **Thử strict mode**: chạy test với `-XX:-EnableDynamicAgentLoading` trong môi trường kiểm soát để tìm chỗ còn phụ thuộc attach.
9. **Xác minh lại**: test vẫn pass, không có warning ngoài dự kiến, chức năng mocking/profiling/observability vẫn hoạt động và cấu hình chỉ áp dụng cho JVM cần thiết.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Mọi `-javaagent` đều là dynamic attach | `-javaagent` nạp agent lúc JVM startup; warning JEP 451 nhắm vào dynamic loading sau startup |
| Có Byte Buddy trong dependency tree nghĩa là chắc chắn có self-attach | Chỉ một số đường code/tính năng gọi agent; cần warning hoặc trace để xác nhận |
| Warning JDK 21 có nghĩa agent đã bị chặn | Trong Java 21, dynamic loading vẫn được phép mặc định nhưng phát warning |
| `-Djdk.instrument.traceUsage` cho phép agent chạy | Property này chỉ giúp trace việc dùng Instrumentation API |
| `-XX:+EnableDynamicAgentLoading` chuyển agent sang startup | Cờ này cho phép dynamic loading; agent vẫn attach sau startup |
| Có `Agent-Class` trong manifest chứng minh JAR đã attach | Manifest chỉ cho biết JAR có entry point dynamic; cần runtime evidence để xác nhận |
| Không có warning nghĩa là không dùng instrumentation | Agent có thể đã được nạp lúc startup hoặc không đi qua đường dynamic attach |
| Có thể xóa `byte-buddy-agent` khỏi classpath để hết warning | Framework có thể cần artifact đó; phải xác định dependency cha và cấu hình được hỗ trợ |

## 14. Tài liệu tham khảo chính thức

- [JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): mục tiêu cảnh báo và lộ trình yêu cầu opt in cho dynamic agent loading.
- [JDK 21 Release Notes — Prepare to Disallow the Dynamic Loading of Agents](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): hành vi warning, `-XX:+EnableDynamicAgentLoading`, `-XX:-EnableDynamicAgentLoading` và `-Djdk.instrument.traceUsage`.
- [Java SE 21 API — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agent, dynamic agent, `premain`, `agentmain` và manifest attributes.
- [Java SE 21 API — `VirtualMachine`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): Attach API để kết nối tới JVM và nạp agent.
- [Java SE 21 API — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer, redefine và retransform class.

Khi thấy warning dynamic agent loading trong Java 21, hãy bắt đầu từ đường dẫn agent JAR, sau đó dùng `-Djdk.instrument.traceUsage` và dependency tree để tìm thư viện kích hoạt attach. Phân biệt agent được nạp lúc startup với agent được nạp sau startup; ưu tiên cấu hình startup agent khi thư viện hỗ trợ, và chỉ bật `-XX:+EnableDynamicAgentLoading` khi dynamic attach là nhu cầu vận hành đã được xác nhận. Cách làm này giúp chuẩn bị cho chính sách JDK tương lai đồng thời giữ rõ ranh giới tin cậy của JVM.
