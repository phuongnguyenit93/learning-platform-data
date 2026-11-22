# Tổ chức test cho bytecode, agent và thư viện tích hợp

Các dự án Java 21 có sử dụng bytecode transformation, Java agent hoặc thư viện tích hợp cần kiểm thử nhiều hơn unit test thông thường. Một transformer có thể chạy đúng với bytecode đơn giản nhưng thất bại khi gặp class file Java 21; agent có thể hoạt động khi attach thủ công nhưng không được truyền vào test JVM; một thư viện có thể chạy riêng nhưng xung đột khi cùng Mockito, JaCoCo hoặc APM agent instrument một lớp.

Chiến lược phù hợp là chia kiểm thử thành nhiều tầng: kiểm tra logic transformer, xác minh bytecode sau biến đổi, chạy agent trong JVM con bằng startup configuration, kiểm thử tích hợp với thư viện thật và chạy ma trận agent/runtime trong CI. Với Java 21, cần chú ý class file version 65 và JEP 451: dynamic agent loading vẫn được cho phép mặc định trên HotSpot JDK 21 nhưng phát cảnh báo; agent cần thiết lâu dài nên được kiểm thử và cấu hình ngay từ lúc JVM khởi động khi công cụ hỗ trợ.

## 1. Vì sao cần test riêng bytecode và agent?

Unit test của ứng dụng thường kiểm tra kết quả method hoặc quy tắc nghiệp vụ. Khi có instrumentation, ứng dụng còn phụ thuộc vào một chuỗi xử lý khác:

1. Build tạo class file và đóng gói agent/library.
2. JVM nạp agent và gọi `premain` hoặc `agentmain` theo cách nạp.
3. Agent đăng ký `ClassFileTransformer` và có thể yêu cầu retransformation/redefinition.
4. Transformer đọc bytecode, sửa đổi và trả byte array mới.
5. JVM kiểm tra, định nghĩa hoặc nạp lại lớp đã biến đổi.
6. Framework và thư viện tích hợp gọi các lớp đó trong môi trường thực tế.

Lỗi ở bất kỳ bước nào cũng có thể khiến ứng dụng không khởi động, lớp không được instrument, test thất bại hoặc hành vi runtime sai. Vì vậy, test cần xác nhận cả ba kết quả: agent được nạp đúng, bytecode hợp lệ và hành vi sau instrumentation đúng mong đợi.

## 2. Các tầng kiểm thử nên có

| Tầng | Phạm vi | Mục tiêu |
|---|---|---|
| Unit test transformer | Input bytecode và output bytecode | Kiểm tra điều kiện chọn lớp, biến đổi và xử lý lỗi |
| Bytecode verification | Class file sau biến đổi | Phát hiện bytecode sai cấu trúc hoặc không qua verifier |
| Agent startup test | JVM con với `-javaagent` hoặc `-agentpath` | Xác nhận manifest, entry point và transformer được nạp |
| Retransformation test | Lớp đã nạp trước đó | Kiểm tra capability và giới hạn retransform/redefine |
| Class loader/module test | Class loader riêng, classpath và module path | Kiểm tra khả năng tìm lớp và truy cập module |
| Library integration test | Framework, JDBC, HTTP, serializer, logging... | Xác nhận instrumentation tương thích với thư viện thật |
| Multi-agent test | Hai hoặc nhiều agent trong cùng JVM | Phát hiện xung đột transformer, thứ tự và overhead |
| CI compatibility matrix | Các JDK/runtime và phiên bản dependency được hỗ trợ | Phát hiện lỗi phụ thuộc môi trường hoặc nâng cấp |

Không phải mọi dự án đều cần tất cả tầng ở mọi lần commit. Có thể chạy unit/bytecode test nhanh ở mỗi commit, còn startup, integration và matrix tests ở pull request hoặc pipeline trước release. Các tầng quan trọng cần được chạy định kỳ để không bỏ sót thay đổi của dependency.

## 3. Đặt mục tiêu bytecode đúng với Java 21

Java 21 tạo class file có major version **65**. Nếu agent dùng ASM, Byte Buddy hoặc thư viện phân tích/biến đổi bytecode khác, phiên bản đó phải đọc được class file version 65 và các cấu trúc bytecode mà compiler tạo ra.

Trong build, đặt release target tường minh:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Hoặc với Gradle Kotlin DSL:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

`--release 21` vừa chọn mức bytecode vừa giới hạn API Java được phép dùng khi biên dịch theo Java 21. Toolchain giúp build chọn JDK compiler phù hợp. Trong CI, vẫn cần xác minh runtime test là JDK dự kiến, vì compiler JDK và runtime test có thể được cấu hình riêng.

Tạo fixture bytecode bao phủ các cấu trúc mà agent cần hỗ trợ, ví dụ:

- Class, interface, enum, annotation và generic signature.
- Record và sealed class/interface.
- Lambda, method reference và `invokedynamic`.
- Nest-based access và inner class.
- Switch expression và pattern matching được hỗ trợ chính thức trong Java 21.
- Annotation runtime, exception handler, stack map frame và debug metadata nếu transformer xử lý các thuộc tính này.

Không nhất thiết phải có mọi cấu trúc trong một fixture. Tách fixture theo tính năng giúp xác định nhanh parser hoặc transformer hỏng ở loại bytecode nào.

## 4. Unit test cho ClassFileTransformer

Transformer nên có phần logic có thể kiểm thử độc lập với quá trình attach. Có thể tách thành các bước:

1. Kiểm tra internal class name, module, class loader và package có thuộc phạm vi instrument không.
2. Đọc bytecode đầu vào.
3. Áp dụng thay đổi.
4. Trả `null` nếu không cần thay đổi, hoặc trả byte array mới nếu có transform.
5. Ghi nhận lỗi theo cách không làm hỏng quá trình nạp lớp ngoài dự kiến.

Ví dụ cấu trúc transformer:

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class MetricsTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (className == null || !className.startsWith("com/example/service/")) {
            return null;
        }

        // Chuyển bytecode sang component xử lý riêng để dễ unit test.
        return BytecodeInstrumenter.instrument(className, classfileBuffer);
    }
}
```

`BytecodeInstrumenter` là thành phần của ứng dụng cần được triển khai và kiểm thử riêng. Trong thực tế, transformer phải tránh instrument chính agent, thư viện bytecode mà agent phụ thuộc hoặc các lớp nền tảng nếu điều đó có thể tạo vòng lặp nạp lớp.

Các trường hợp unit test nên có:

- Class nằm trong package được include được biến đổi.
- Class nằm ngoài phạm vi hoặc trong exclude package trả `null`.
- Tên lớp hoặc dữ liệu đầu vào không hợp lệ được xử lý theo chính sách đã định.
- Bytecode có annotation, generic, record/sealed hoặc lambda được xử lý đúng.
- Lỗi parser/transformer không để lại trạng thái toàn cục bị hỏng.
- Transformer không thay đổi input array ngoài ý muốn nếu thiết kế yêu cầu giữ nguyên input.

Unit test chỉ xác nhận logic transformer. Nó chưa chứng minh JVM có thể định nghĩa lớp sau khi biến đổi; cần thêm bytecode verification và test trong JVM thật.

## 5. Kiểm tra bytecode sau biến đổi

Đừng chỉ kiểm tra byte array đầu ra khác byte array đầu vào. Một transformer có thể tạo bytecode khác nhưng sai stack map frame, descriptor, access flag hoặc exception table.

Một số cách kiểm tra:

- Đọc lại output bằng cùng parser bytecode để phát hiện cấu trúc không hợp lệ.
- Dùng verifier của thư viện bytecode như ASM `CheckClassAdapter` trong test khi phù hợp.
- Định nghĩa lớp bằng class loader cô lập và gọi method đã biến đổi.
- Chạy test JVM con với `-Xverify:all` để yêu cầu verifier kiểm tra class file trong tiến trình kiểm thử.
- Kiểm tra kết quả hành vi: method trả đúng, exception được giữ đúng và side effect instrumentation xuất hiện đúng một lần.

Ví dụ chạy một smoke main với verifier bật:

```shell
java -Xverify:all -cp build/classes/java/test com.example.BytecodeSmokeMain
```

Nếu test cần agent startup, thêm `-javaagent` vào cùng command line như phần tiếp theo. `-Xverify:all` hữu ích cho test chuyên biệt; không nhất thiết phải bật cho mọi tiến trình production.

### Những ràng buộc khi retransformation/redefinition

Nếu agent yêu cầu retransformation hoặc redefinition, kiểm tra capability trước khi dùng:

```java
if (!instrumentation.isRetransformClassesSupported()) {
    throw new IllegalStateException("Retransformation không được hỗ trợ");
}

if (!instrumentation.isModifiableClass(targetClass)) {
    throw new IllegalStateException("Class không thể retransformation");
}

instrumentation.retransformClasses(targetClass);
```

Agent JAR cần khai báo `Can-Retransform-Classes: true` nếu cần đăng ký retransformation-capable transformer; khi gọi `addTransformer(transformer, true)`, JVM cũng phải hỗ trợ capability đó. Không giả định mọi class đều có thể sửa.

HotSpot và Instrumentation API đặt giới hạn cấu trúc đối với redefine/retransform: không thể tùy tiện thêm/xóa field hoặc method, thay đổi signature, superclass hay interfaces của lớp đã định nghĩa. Test nên xác nhận transformer chỉ thay đổi những gì JVM cho phép, thường là phần method body hoặc metadata phù hợp.

## 6. Test agent trong JVM con bằng startup configuration

Kiểm thử `premain` trong JVM con là cách đáng tin cậy để xác nhận agent JAR, manifest và transformer hoạt động như khi ứng dụng khởi động. Tách JVM giúp tránh trạng thái instrumentation bị rò rỉ sang các test khác.

Agent JAR cần khai báo manifest tối thiểu:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.MetricsAgent
Can-Retransform-Classes: true
```

Ví dụ entry point:

```java
import java.lang.instrument.Instrumentation;

public final class MetricsAgent {
    public static void premain(String args, Instrumentation instrumentation) {
        instrumentation.addTransformer(new MetricsTransformer(), true);
    }
}
```

Nếu agent không cần retransformation, bỏ capability khỏi manifest và đăng ký transformer với `addTransformer(transformer)` thay vì yêu cầu khả năng không sử dụng.

### Smoke test cho startup agent

Tạo một fixture class mà transformer nhận diện, rồi viết một main nhỏ nạp class đó và kiểm tra marker do transformer tạo ra. Ví dụ transformer test có thể đặt system property khi nhìn thấy lớp fixture; test main kiểm tra property sau `Class.forName(...)`.

```java
public final class AgentSmokeMain {
    public static void main(String[] args) throws Exception {
        Class.forName("com.example.fixture.Target");

        if (!"seen".equals(System.getProperty("agent.test.target"))) {
            throw new IllegalStateException("Agent chưa quan sát fixture class");
        }
    }
}
```

Trong test harness, khởi chạy tiến trình Java con bằng `ProcessBuilder` với các đối số:

```text
<java-executable>
-Xverify:all
-javaagent:<absolute-path-to-agent.jar>
-cp
<test-classpath>
com.example.AgentSmokeMain
```

Chờ process kết thúc, thu stdout/stderr, kiểm tra exit code bằng 0 và xác nhận marker. Khi kiểm thử, timeout cho process con để tránh CI bị treo nếu agent hoặc class loading deadlock. Không dùng một test JVM đã chạy để giả lập startup `premain`, vì `premain` chỉ được gọi trong quá trình khởi động JVM.

## 7. Cấu hình agent cho test task trong Gradle

Nếu dự án có module đóng gói agent riêng, có thể truyền JAR đó vào forked test JVM. Ví dụ Kotlin DSL khi task `jar` của project tạo đúng agent JAR:

```kotlin
import org.gradle.jvm.tasks.Jar

val agentJar = tasks.named<Jar>("jar")

tasks.test {
    dependsOn(agentJar)
    doFirst {
        jvmArgs("-javaagent:${agentJar.get().archiveFile.get().asFile.absolutePath}")
    }
}
```

Manifest của JAR phải được cấu hình `Premain-Class` và các capability cần thiết. Với multi-module build, dùng artifact/task của đúng agent module thay vì nhầm JAR ứng dụng hoặc JAR test. Nếu test task có JaCoCo, Mockito hoặc agent khác, ghép tất cả JVM arguments có chủ đích và không làm mất agent do plugin tự cấu hình.

Với Maven Surefire/Failsafe, cấu hình `-javaagent` trong JVM fork chạy test thông qua `argLine`. Nếu JaCoCo cũng quản lý `argLine`, cần dùng cơ chế late property evaluation/merge theo tài liệu plugin để giữ cả hai agent; không ghi đè `argLine` do JaCoCo tạo ra.

## 8. Test dynamic attach và JEP 451 riêng biệt

Startup agent và dynamic attach là hai đường nạp khác nhau, vì vậy test cũng phải tách riêng.

Trên HotSpot JDK 21:

- Dynamic loading được cho phép mặc định nhưng phát warning khi agent được nạp vào JVM đang chạy.
- `-XX:+EnableDynamicAgentLoading` opt-in tường minh và suppress warning.
- `-XX:-EnableDynamicAgentLoading` từ chối nạp agent động, hữu ích để tìm công cụ đang phụ thuộc self-attach.
- `-Djdk.instrument.traceUsage` giúp truy tìm nơi sử dụng Java Instrumentation API.

Trong CI, có thể chạy startup-agent smoke test với `-XX:-EnableDynamicAgentLoading`. Nếu agent được nạp bằng `-javaagent`, test vẫn phải chạy; điều này giúp xác nhận agent không vô tình dựa vào dynamic attach sau startup.

Nếu sản phẩm thực sự hỗ trợ dynamic attach, tạo test riêng với JVM đích được khởi chạy rõ ràng theo chính sách cần kiểm tra. Attach API phải kết nối đến đúng process đích; đặt flag trên JVM điều khiển attach không thay đổi flag của JVM đích. Không nên kiểm tra bằng cách so khớp toàn bộ văn bản warning, vì nội dung có thể thay đổi giữa bản JDK update và vendor. Kiểm tra hành vi, trạng thái attach và log ở mức phù hợp.

Không thêm `-XX:+EnableDynamicAgentLoading` vào mọi CI job chỉ để làm biến mất warning. Nếu test chỉ thành công khi bật flag này, xác định công cụ nào self-attach và xem có thể chuyển sang startup agent hay không.

## 9. Test class loader và Java module system

Instrumentation thường gặp vấn đề với class loader vì cùng một tên lớp có thể được định nghĩa bởi nhiều loader khác nhau. Transformer nên kiểm tra đúng class name, loader và protection domain theo yêu cầu, tránh giả định mọi lớp ứng dụng đều do system class loader định nghĩa.

Nên có test cho:

- Lớp được nạp bởi application class loader.
- Lớp được nạp bởi custom class loader hoặc plugin loader.
- Hai class loader định nghĩa hai lớp cùng tên nhưng có identity khác nhau.
- Lớp thuộc module có tên và lớp trên classpath/unnamed module.
- Package không được mở cho deep reflection.
- Lớp bootstrap/platform mà agent cần quan sát, nếu phạm vi sản phẩm có yêu cầu.

Java 21 duy trì strong encapsulation của module JDK. Nếu agent cần reflection vào package không được export/open, ưu tiên dùng API công khai hoặc cơ chế instrumentation/module phù hợp. Chỉ thêm `--add-opens` cho đúng module/package khi đã xác định yêu cầu và phạm vi; tránh mở rộng toàn bộ module JDK chỉ để test qua.

## 10. Test thư viện tích hợp bằng dependency thật

Mock có ích cho unit test nhưng không thay thế integration test. Agent thường phụ thuộc vào chi tiết bytecode hoặc điểm mở rộng của thư viện; một mock tự tạo không phản ánh class loader, proxy, generated class hoặc call path thật.

Chọn thư viện quan trọng theo kiến trúc sản phẩm, ví dụ:

| Nhóm thư viện | Điều cần xác nhận |
|---|---|
| HTTP server/framework | Request handler được instrument đúng; trace/metric không bị duplicate |
| HTTP client | Outbound call được nhận diện; context propagation đúng qua callback/executor |
| JDBC driver/connection pool | Query span/metric đúng; connection lifecycle không bị thay đổi |
| Messaging client | Producer/consumer instrumentation và context propagation hoạt động |
| JSON/serialization | Generated accessor/record/reflective access không bị phá |
| Logging | Correlation ID/trace context được truyền đúng; không tạo vòng lặp instrumentation |
| Dependency injection/proxy | Proxy hoặc generated class được xử lý đúng class loader và module |
| Mocking/coverage | Mockito, Byte Buddy và JaCoCo chạy cùng nhau theo cấu hình test |

Integration test nên chạy với phiên bản thư viện thực tế mà ứng dụng hỗ trợ. Dùng database/server test hoặc container cô lập nếu cần kiểm tra giao tiếp thật; giữ test deterministic, đặt timeout và thu log để chẩn đoán. Không dựa vào một mock duy nhất để khẳng định agent tương thích với toàn bộ thư viện.

## 11. Kiểm tra tương tác giữa nhiều agent

Mockito inline mocking, JaCoCo, APM và profiler có thể cùng đăng ký transformer trong một JVM. Một transformer chạy riêng thành công không đảm bảo tổ hợp sẽ hoạt động.

Các nguyên nhân xung đột có thể gồm:

- Transformer đầu tiên tạo bytecode mà transformer sau không phân tích được.
- Một agent giả định method body chưa được agent khác instrument.
- Capability retransformation khác nhau hoặc transformer không xử lý bytecode đã biến đổi trước đó.
- Nhiều agent instrument cùng method, dẫn đến duplicate span, metric hoặc probe.
- Agent thay đổi class loader/module visibility theo cách ảnh hưởng agent khác.
- Overhead tổng hợp làm test timeout hoặc trở nên flaky.

JVM xử lý transformer theo các nhóm capability và thứ tự đăng ký trong từng nhóm. Thứ tự các `-javaagent` có thể ảnh hưởng thứ tự `premain` và đăng ký transformer, nhưng đổi thứ tự không phải cách sửa tổng quát. Cần đọc log và xác định transformer nào tạo ra bytecode gây lỗi.

Ma trận tổ hợp tối thiểu:

1. Không agent (baseline).
2. Chỉ agent của sản phẩm.
3. Chỉ mocking agent.
4. Chỉ coverage agent.
5. Chỉ APM/profiler nếu dùng trong môi trường test.
6. Các tổ hợp thực tế được triển khai cùng nhau.

Chỉ chạy tổ hợp cần thiết để tránh tăng thời gian CI quá mức, nhưng phải có ít nhất một job xác nhận cấu hình thực tế trước release.

## 12. Kiểm tra thư viện bytecode và dependency tree

Agent có thể đóng gói ASM, Byte Buddy hoặc một thư viện bytecode khác. Dependency bắc cầu bị ép về phiên bản cũ có thể khiến agent lỗi dù dependency trực tiếp đã nâng cấp.

Trong CI:

- In hoặc lưu dependency tree của agent và test runtime khi có lỗi tương thích.
- Kiểm tra dependency convergence và version conflict theo công cụ build.
- Tránh để hai bản khác nhau của thư viện bytecode cùng tồn tại trong cùng class loader nếu chúng có package/class trùng nhau.
- Nếu shade/relocate thư viện bytecode, kiểm tra manifest, service metadata và package relocation trong artifact đã đóng gói.
- Xác nhận bản thư viện được dùng có hỗ trợ class file 65 và các cấu trúc Java 21 mà fixture kiểm thử.
- Cập nhật dependency theo release đã được dự án kiểm tra; không chọn phiên bản chỉ vì số version lớn hơn.

Đừng chỉ chạy test trên class file được compiler tạo trong cùng module agent. Hãy có fixture được biên dịch độc lập hoặc từ module ứng dụng để phát hiện lỗi khi agent gặp bytecode đến từ compiler/plugin khác.

## 13. Ma trận CI cho Java 21

Một pipeline có thể chia theo thời gian và mức độ rủi ro:

| Job | Nội dung | Khi chạy |
|---|---|---|
| Compile/static checks | Compile với `--release 21`, lint, kiểm tra dependency | Mỗi commit/PR |
| Transformer unit tests | Include/exclude, input edge cases, bytecode fixture | Mỗi commit/PR |
| Bytecode verification | Verify output và load transformed classes với `-Xverify:all` | Mỗi commit/PR |
| Startup agent integration | Fork JVM con với `-javaagent` và kiểm tra hành vi | Mỗi PR |
| Dynamic loading policy | Test tương thích với dynamic loading bị tắt hoặc opt-in nếu sản phẩm cần attach | PR/release |
| Library integration | HTTP/JDBC/messaging/framework thật theo kiến trúc | PR hoặc nightly |
| Multi-agent compatibility | Mocking + coverage + APM/profiler theo cấu hình thực tế | PR/release |
| Runtime compatibility | JDK 21 baseline và các runtime mới hơn mà sản phẩm cam kết hỗ trợ | Nightly/release |
| Packaging smoke test | Kiểm tra agent JAR, manifest và artifact cuối cùng | Release |

JDK 21 là baseline của module này. Nếu sản phẩm cam kết chạy trên các JDK mới hơn, thêm runtime đó vào matrix để phát hiện thay đổi của verifier, module system, attach policy hoặc JIT. Không suy ra rằng chỉ vì build bằng JDK 21 thì mọi runtime mới hơn đều đã được kiểm thử.

## 14. Ví dụ workflow CI ở mức khái quát

Pipeline có thể thực hiện các bước sau:

```text
Checkout source
      |
      v
Setup JDK 21 + dependency cache
      |
      v
Compile with --release 21
      |
      v
Transformer unit tests
      |
      v
Bytecode verification (-Xverify:all)
      |
      v
Build agent JAR + validate manifest
      |
      v
Forked JVM startup-agent tests
      |
      v
Library integration + multi-agent tests
      |
      v
Package artifacts + publish test reports
```

Với Gradle có thể chạy:

```shell
./gradlew --no-daemon clean check
```

Với Maven có thể chạy:

```shell
./mvnw -B -ntp clean verify
```

Đây là lệnh tổng quát; task/phase thực tế phụ thuộc cấu hình dự án. Đảm bảo integration test và forked JVM test thực sự được gắn vào lifecycle CI, không chỉ tạo test class nhưng không có task nào chạy chúng.

## 15. Làm cho CI có thể tái lập

Instrumentation test dễ bị ảnh hưởng bởi thứ tự test, trạng thái JVM và dependency biến động. Để kết quả đáng tin cậy:

- Pin JDK vendor/update và version của plugin/dependency trong pipeline.
- Dùng Maven Wrapper hoặc Gradle Wrapper đã được commit cùng cấu hình wrapper được kiểm tra.
- Dùng lockfile hoặc dependency constraints nếu dự án cần tái lập dependency resolution.
- Lưu command line của JVM test worker, agent list và build metadata khi test thất bại.
- Dùng JVM con riêng cho test cần startup agent hoặc trạng thái instrumentation độc lập.
- Không chạy test phụ thuộc thứ tự toàn cục trong cùng một JVM nếu có thể cô lập bằng fork.
- Dùng timeout cho subprocess, attach, network và database test.
- Giữ fixture và test data ổn định; dọn process, port và container sau test.
- Cache dependency đã tải, nhưng tránh tái sử dụng output build cũ làm mất tính đúng đắn của clean build.
- Lưu test report, agent log, GC/JFR recording khi job chẩn đoán thất bại và cần điều tra sâu.

Không cache các file trạng thái runtime hoặc output instrumented giữa những build không tương thích. Nếu bytecode được instrument trong build directory, clean/rebuild khi thay đổi compiler, JDK, transformer hoặc dependency liên quan.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Agent không chạy trong test | `-javaagent` được truyền vào Gradle/Maven daemon thay vì forked test JVM | Kiểm tra command line của test worker |
| `premain` không được gọi | Manifest thiếu/sai `Premain-Class` hoặc JAR sai | Kiểm tra manifest của artifact đã đóng gói |
| `UnsupportedClassVersionError` hoặc parser bytecode lỗi | Bytecode tool chưa hỗ trợ class file 65 | Nâng parser/agent lên bản hỗ trợ Java 21 |
| `VerifyError` sau transform | Stack map frame, descriptor hoặc bytecode không hợp lệ | Verify output, load fixture trong JVM con và kiểm tra transformer |
| Retransform thất bại | Capability không được bật hoặc lớp không modifiable | Kiểm tra manifest, `isRetransformClassesSupported()` và `isModifiableClass()` |
| Test chỉ chạy được khi dynamic attach được bật | Framework hoặc agent đang self-attach | Cấu hình startup agent hoặc quản lý opt-in riêng cho môi trường cần attach |
| Test pass riêng nhưng fail khi bật JaCoCo + Mockito | Transformer interaction hoặc thứ tự instrumentation | Cô lập từng agent, xem log và thử cấu hình startup đồng bộ |
| Class không được instrument | Exclude rule, class loader hoặc module không đúng | Ghi nhận class name/loader/module và kiểm tra filter |
| `InaccessibleObjectException` | Agent hoặc thư viện reflection vào package đóng | Cập nhật thư viện, dùng API công khai; chỉ mở package cần thiết khi có lý do |
| Integration test flaky | Shared JVM state, port, external dependency hoặc race condition | Fork/cô lập test, dùng test dependency có kiểm soát và timeout |
| CI khác local | JDK, flags, OS, dependency hoặc JVM test process khác nhau | Lưu metadata và tái hiện đúng command line CI |

## 17. Checklist tổ chức test

- Compile ứng dụng và fixture bằng target Java 21 (`--release 21`).
- Xác nhận bytecode library hỗ trợ class file version 65.
- Unit test transformer với fixture đại diện và các trường hợp không instrument.
- Verify bytecode output và load class sau biến đổi trong JVM thật.
- Kiểm tra giới hạn retransform/redefine và modifiable class nếu agent sử dụng các API này.
- Build agent JAR và xác nhận manifest có entry point/capability đúng.
- Chạy startup agent test trong JVM con, không tái sử dụng test JVM.
- Kiểm tra dynamic attach riêng theo JEP 451; thử disable để tìm self-attach dependency.
- Test class loader, module path và package access theo kiến trúc thực tế.
- Chạy integration test với phiên bản thư viện thực tế, không chỉ mock.
- Test tổ hợp mocking, coverage, APM và profiler nếu chúng cùng xuất hiện trong một JVM.
- Giữ đúng thứ tự agent và JVM arguments giữa local, CI và production.
- Dùng timeout, log và test report để chẩn đoán lỗi agent/process.
- Pin toolchain/dependency và chạy clean build trong pipeline release.
- Duy trì runtime matrix cho JDK 21 và các JDK mới hơn mà sản phẩm hỗ trợ.

Kiểm thử bytecode, agent và thư viện tích hợp cần xác nhận cả artifact, cách nạp agent, bytecode sau transform và hành vi của ứng dụng trong JVM thật. Tách unit test khỏi forked startup test, kiểm tra dynamic attach theo JEP 451 và chạy tổ hợp agent/dependency trong CI giúp phát hiện sớm lỗi class file, verifier, class loader và xung đột instrumentation trên Java 21.
