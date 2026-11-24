# Java agent và instrumentation: tra cứu khả năng hỗ trợ theo phiên bản

Java agent và instrumentation thường được dùng để quan sát hoặc thay đổi bytecode khi ứng dụng chạy. Công cụ APM, profiler, coverage, mocking và một số framework có thể sử dụng `java.lang.instrument`, `ClassFileTransformer`, Attach API hoặc JVM Tool Interface (JVMTI). Khi chuyển Spring Boot sang GraalVM Native Image, không thể mặc định rằng những công cụ đang hoạt động trên JVM sẽ tiếp tục hoạt động trong native executable.

Điểm quan trọng là phân biệt ba cơ chế: **Java agent của JVM**, **Native Image Tracing Agent dùng để thu thập reachability metadata**, và **runtime class loading của GraalVM Native Image**. Chúng có mục tiêu và phạm vi hỗ trợ khác nhau. Bài này hướng dẫn tra cứu theo phiên bản JDK/GraalVM, xác định giới hạn của từng cơ chế và lựa chọn cách kiểm thử phù hợp cho ứng dụng Spring Boot native.

## 1. Java agent và instrumentation là gì?

Java agent là một thành phần được JVM nạp để quan sát hoặc biến đổi class bytecode. Agent thường triển khai một trong hai entry point:

- `premain(...)`: JVM gọi khi agent được nạp lúc khởi chạy bằng `-javaagent`.
- `agentmain(...)`: JVM gọi khi agent được nạp vào một JVM đang chạy, nếu implementation hỗ trợ dynamic attach.

API `java.lang.instrument.Instrumentation` cho phép agent đăng ký `ClassFileTransformer`, truy vấn khả năng instrumentation và trong một số trường hợp redefine/retransform class đã nạp.

Một agent thường có các thành phần:

~~~text
audit-agent.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/agent/
    └── AuditAgent.class
~~~

Manifest tối thiểu cho agent chạy lúc JVM khởi động:

~~~text
Premain-Class: com.example.agent.AuditAgent
Can-Retransform-Classes: false
~~~

Ví dụ agent đơn giản ghi nhận tên các class ứng dụng khi JVM nạp chúng:

~~~java
package com.example.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class AuditAgent {

    public static void premain(
            String agentArgs,
            Instrumentation instrumentation) {

        instrumentation.addTransformer(
                new ClassFileTransformer() {
                    @Override
                    public byte[] transform(
                            Module module,
                            ClassLoader loader,
                            String className,
                            Class<?> classBeingRedefined,
                            ProtectionDomain protectionDomain,
                            byte[] classfileBuffer) {

                        if (className != null
                                && className.startsWith("com/example/")) {
                            System.out.println("Loading: " + className);
                        }

                        // null nghĩa là không thay đổi bytecode.
                        return null;
                    }
                },
                false
        );
    }
}
~~~

Biên dịch agent với JDK phù hợp, đóng gói JAR có manifest ở trên rồi chạy ứng dụng JVM:

~~~bash
java -javaagent:target/audit-agent.jar -jar target/application.jar
~~~

JVM nạp agent và gọi `premain` trước khi gọi `main` của ứng dụng. Nếu agent không khởi động được hoặc `premain` ném exception không được xử lý, JVM có thể dừng trước khi ứng dụng bắt đầu.

Agent ví dụ chỉ ghi log, không biến đổi bytecode. Một agent thực tế có thể dùng thư viện như Byte Buddy hoặc ASM để tạo bytecode mới, nhưng khi đó cần kiểm tra thêm khả năng tương thích giữa thư viện, JDK và môi trường chạy.

## 2. Phân biệt các cơ chế thường bị gọi chung là “agent”

Tên gọi gần nhau nhưng các tùy chọn dưới đây không thay thế lẫn nhau:

| Cơ chế | Cách nạp | Mục tiêu | Nơi thường sử dụng |
| --- | --- | --- | --- |
| Java agent | `-javaagent:agent.jar` | Gọi `premain`, cung cấp `Instrumentation` để transform class | JVM lúc khởi động |
| Dynamic Java agent | Attach API, `jcmd` hoặc công cụ tương đương | Gọi `agentmain` trong JVM đang chạy | JVM sau khi khởi động |
| Native/JVM TI agent | `-agentlib:lib` hoặc `-agentpath:path` | Nạp thư viện native triển khai JVMTI | JVM có hỗ trợ JVMTI |
| Native Image Tracing Agent | `-agentlib:native-image-agent=...` | Quan sát truy cập động trên JVM và sinh metadata cho Native Image | JVM trong giai đoạn thu thập cấu hình |
| Native Image runtime class loading | `-H:+RuntimeClassLoading` lúc build | Cho phép một số class loader định nghĩa class từ bytecode khi native executable chạy | Native Image từ GraalVM 25.1 trở lên, ở trạng thái experimental |

Đặc biệt, `native-image-agent` **không phải Java agent mà ứng dụng cần để instrument chính native executable**. Đây là công cụ của GraalVM chạy trên một JVM thông thường để quan sát các truy cập động như reflection, resource, JNI và dynamic proxy, sau đó tạo metadata phục vụ quá trình build native.

Tương tự, `-H:+RuntimeClassLoading` chỉ mở một khả năng định nghĩa class từ bytecode ở runtime. Nó không tạo ra một JVM đầy đủ bên trong native executable và không tự cung cấp `Instrumentation`, `ClassFileTransformer`, Attach API hay JVMTI.

## 3. Java Instrumentation trên JDK: tra cứu theo phiên bản

`java.lang.instrument` thuộc nền tảng Java SE. Tuy nhiên, việc một implementation cung cấp agent startup hoặc dynamic attach còn phụ thuộc JVM cụ thể. Khi tra cứu, cần tách hai câu hỏi:

1. JDK/JVM có hỗ trợ nạp agent bằng `-javaagent` lúc khởi động không?
2. JVM có cho phép Attach API nạp agent vào một tiến trình đang chạy không, và chính sách mặc định của phiên bản đó là gì?

### Mốc thay đổi đáng chú ý: JDK 21

Từ JDK 21, HotSpot phát cảnh báo khi Java agent hoặc JVM TI agent được nạp động vào một JVM đang chạy. Đây là thay đổi theo JEP 451 nhằm chuẩn bị cho chính sách integrity-by-default. Nạp agent ngay lúc khởi động bằng `-javaagent` hoặc `-agentlib` không tạo cảnh báo này.

Trên HotSpot, `-XX:+EnableDynamicAgentLoading` là opt-in rõ ràng cho dynamic agent loading và đồng thời loại bỏ cảnh báo. Có thể dùng `-XX:-EnableDynamicAgentLoading` để kiểm tra xem ứng dụng hoặc thư viện có đang phụ thuộc vào dynamic attach hay không.

### Bảng tra cứu JDK

| Phiên bản JDK | Agent lúc khởi động | Dynamic attach | Điểm cần xác minh |
| --- | --- | --- | --- |
| JDK 8–20 | HotSpot hỗ trợ `-javaagent` và `-agentlib` | Có thể dùng nếu JVM implementation hỗ trợ Attach API | Kiểm tra vendor, Attach API, quyền OS và agent manifest |
| JDK 21–25 | `-javaagent` lúc khởi động vẫn được hỗ trợ trên HotSpot | HotSpot cảnh báo khi nạp động; `-XX:+EnableDynamicAgentLoading` là opt-in | Kiểm tra warning, flag và hướng dẫn của JDK vendor |
| JDK 26 hoặc release mới hơn | Không suy ra chỉ từ số phiên bản | Chính sách có thể thay đổi theo JEP/release và vendor | Đọc Javadoc, release notes và chạy smoke test trên đúng bản JDK |

Bảng trên mô tả mốc chính sách của HotSpot và giúp định hướng tra cứu; nó không thay thế tài liệu của một distribution cụ thể. Java SE specification mô tả dynamic attach theo dạng implementation-specific, vì vậy không nên coi mọi JVM đều có cùng hành vi.

### Cách nhận diện agent đang được nạp động

Nếu ứng dụng JVM in cảnh báo tương tự:

~~~text
WARNING: A Java agent has been loaded dynamically
WARNING: Dynamic loading of agents will be disallowed by default in a future release
~~~

Hãy kiểm tra thư viện nào gọi Attach API. Với HotSpot, có thể chạy thử:

~~~bash
java -XX:-EnableDynamicAgentLoading -jar target/application.jar
~~~

Nếu ứng dụng hoặc test thất bại, có thể đang có dependency tự nạp agent. `-Djdk.instrument.traceUsage` giúp truy vết việc sử dụng API instrumentation trong những tình huống được JDK hỗ trợ.

Ưu tiên cấu hình agent ngay từ đầu JVM bằng `-javaagent` nếu môi trường thực sự cần agent. Dùng `-XX:+EnableDynamicAgentLoading` khi đã xác nhận cần dynamic attach và chấp nhận opt-in đó; không thêm flag chỉ để che cảnh báo mà chưa xác định nguồn nạp agent.

## 4. Giới hạn của Java agent trong GraalVM Native Image

Native Image dùng static analysis và closed-world model để tạo native executable. Bytecode không còn được JVM nạp và thực thi theo cách thông thường tại runtime. Do đó, các công cụ dựa trên việc quan sát hoặc biến đổi bytecode trong một JVM đang chạy không thể mặc nhiên hoạt động trong native executable.

Theo Native Image Compatibility Guide hiện hành, **JVMTI và các công cụ dựa trên bytecode không được hỗ trợ trong Native Image runtime**. Điều này ảnh hưởng trực tiếp đến những cơ chế sau:

- `-javaagent` dùng để nạp agent và nhận `Instrumentation`.
- `ClassFileTransformer` để biến đổi class khi load/retransform.
- Redefine/retransform class đã nạp thông qua Java Instrumentation.
- Attach API và công cụ dựa vào việc gắn agent vào tiến trình đang chạy.
- JVMTI agent được nạp bằng `-agentlib` hoặc `-agentpath`.
- Các profiler, debugger hoặc coverage tool phụ thuộc vào JVM bytecode và JVMTI.

Không nên đưa `-javaagent:...` vào command chạy native executable với kỳ vọng nó hoạt động như khi chạy `java -jar`. Native executable không phải một HotSpot JVM chỉ được đóng gói theo cách khác.

### Điều này ảnh hưởng tới Spring Boot ra sao?

Một ứng dụng Spring Boot chạy JVM có thể được gắn APM agent, coverage agent hoặc Java agent của thư viện. Khi chuyển sang native:

- Agent JVM không tự chuyển thành thành phần của native executable.
- Việc Spring AOT sinh mã khởi tạo context không tự tạo lại khả năng transform bytecode lúc runtime.
- Native Image có thể cần reachability metadata cho các truy cập động, nhưng metadata không tương đương với instrumentation.
- Một thư viện tạo proxy hoặc class động cần được đánh giá riêng: class generation có thể có lựa chọn khác theo GraalVM version, nhưng không có nghĩa agent dùng để redefine class được hỗ trợ.

Vì vậy, cần kiểm tra theo **cơ chế mà thư viện thực sự sử dụng**, thay vì chỉ nhìn tên thư viện hoặc dòng lệnh JVM cũ.

## 5. Native Image Tracing Agent: công cụ thu metadata, không phải agent runtime

GraalVM cung cấp Native Image Tracing Agent để chạy ứng dụng trên JVM và ghi nhận các truy cập động mà static analysis có thể không tự suy ra, ví dụ:

- Reflection: tra cứu class, constructor, method hoặc field.
- Dynamic proxy: tạo proxy interface.
- JNI: truy cập kiểu/member từ native code.
- Classpath resources và resource bundles.
- Một số dạng class được định nghĩa động, thông qua tùy chọn experimental theo version.

Chạy ứng dụng Spring Boot JAR trên GraalVM JDK với tracing agent:

~~~bash
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config/ \
  -jar target/application.jar
~~~

Đối với Windows, dùng `java.exe` từ GraalVM JDK và điều chỉnh đường dẫn theo hệ điều hành. Tùy chọn `-agentlib` phải đặt trước `-jar`, tên main class hoặc tham số ứng dụng.

Sau khi ứng dụng kết thúc, agent ghi metadata vào thư mục cấu hình. Có thể chạy nhiều lần với các luồng nghiệp vụ khác nhau để tăng độ bao phủ:

~~~bash
# Lần đầu tạo bộ metadata.
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config/ \
  -jar target/application.jar

# Lần tiếp theo bổ sung metadata vào bộ đã có.
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=config-merge-dir=target/native-agent-config/ \
  -jar target/application.jar
~~~

Hãy chạy các kịch bản có thể kích hoạt các đường truy cập động: đăng nhập, xử lý request, đọc cấu hình, serialize, gọi plugin, tạo proxy và các nhánh lỗi. Agent chỉ quan sát những gì thực sự chạy; nó không chứng minh mọi nhánh của ứng dụng đã được ghi nhận.

### Xem lại metadata trước khi build

Không nên đưa toàn bộ output vào production mà không review. Hãy:

1. Xác định class/member/resource nào được thêm.
2. Kiểm tra có metadata thừa do test framework, devtools hoặc thư viện không cần trong production không.
3. So sánh nhiều lần chạy để tìm phần thiếu.
4. Kiểm tra tên class, member và resource có đúng với source/dependency hiện tại không.
5. Đưa metadata đã duyệt vào vị trí được Native Image build đọc.

Với các bản GraalVM mới, metadata hợp nhất có thể nằm trong `reachability-metadata.json` dưới `META-INF/native-image/`. Các release cũ có thể tạo nhiều file như `reflect-config.json`, `resource-config.json`, `proxy-config.json`, `jni-config.json` hoặc `serialization-config.json`. Hãy xem output thực tế và schema của đúng GraalVM version, không đổi tên file theo một hướng dẫn cũ một cách máy móc.

## 6. Thay đổi theo GraalVM version: metadata và dynamic class loading

GraalVM thay đổi định dạng metadata và bổ sung dần khả năng tương thích. Cần tra cứu đúng release line, nhất là khi dùng plugin build native được nâng cấp độc lập với JDK.

| GraalVM Native Image | Metadata tracing | Dynamic class loading ở runtime | Java agent/JVMTI ở native runtime |
| --- | --- | --- | --- |
| 22.x | Thường gặp các file metadata riêng theo từng loại; kiểm tra tài liệu release cụ thể | Không có tính năng runtime class loading mới như dòng 25.1; có thể có predefined-class support experimental ở một số bản | JVMTI và công cụ bytecode không được hỗ trợ |
| 23.x | Chuyển sang `reachability-metadata.json`; các file riêng cũ bị deprecated nhưng còn được chấp nhận | Không nên suy ra có runtime class loading tổng quát từ việc metadata format thay đổi | Không được hỗ trợ |
| 24.x | Dùng `reachability-metadata.json` và schema theo release; một số tùy chọn chẩn đoán missing registration đã có | Vẫn phải kiểm tra giới hạn dynamic class loading theo release; predefined classes là hướng experimental riêng | Không được hỗ trợ |
| 25.0 LTS | Dùng unified reachability metadata; tra schema và agent options theo 25.0 | Không đồng nhất với tính năng mới được công bố trong 25.1 | Không được hỗ trợ |
| 25.1 trở lên | Tracing agent và reachability metadata tiếp tục được cập nhật | Có early/experimental runtime class loading qua `-H:+RuntimeClassLoading` | Vẫn không đồng nghĩa hỗ trợ Java Instrumentation hoặc JVMTI |

Bảng là mốc định hướng để tra cứu, không phải ma trận chứng nhận mọi bản patch, nền tảng và distribution. GraalVM có các dòng LTS và feature/innovation releases; một tính năng có thể xuất hiện ở feature release trước khi có trong dòng LTS.

### Điểm mới từ GraalVM 25.1

GraalVM 25.1 giới thiệu phiên bản sớm của dynamic class loading cho thư viện/công cụ tạo JVM bytecode lúc runtime, chẳng hạn một số use case của Byte Buddy. Bật bằng build option:

~~~text
-H:+RuntimeClassLoading
~~~

Đây là tính năng **experimental**, cần mở experimental VM options theo hướng dẫn của release:

~~~bash
native-image \
  -H:+UnlockExperimentalVMOptions \
  -H:+RuntimeClassLoading \
  -H:-UnlockExperimentalVMOptions \
  -jar target/application.jar
~~~

Tính năng này cho phép class loader định nghĩa class từ bytecode thông qua `ClassLoader.defineClass`. Nó không làm cho Native Image có JVM TI, không cấp `Instrumentation` và không cho phép agent transform/retransform class đã nạp.

Một số giới hạn cần xem trước khi bật:

- Class loader không thể định nghĩa lại cùng binary name trong chính loader đó.
- Parallel class loading chưa được hỗ trợ.
- `URLClassLoader` và việc nạp class từ JDK/application class loader có thể cần cấu hình bổ sung.
- Static analysis có thể loại bỏ method hoặc static field mà class được định nghĩa động cần truy cập; có thể phải bảo toàn package bằng `-H:Preserve=package=...`.
- Image size và memory usage có thể tăng.
- Tính năng runtime class loading không kết hợp được với predefined classes.

Nếu một thư viện dùng Byte Buddy để **tạo class mới** thì tính năng này có thể liên quan. Nếu thư viện dùng Java agent để **biến đổi class đang tồn tại** bằng `Instrumentation.redefineClasses` hoặc `retransformClasses`, `-H:+RuntimeClassLoading` không giải quyết được nhu cầu đó.

## 7. Predefined classes và tracing agent experimental

Một hướng khác cho ứng dụng cũ là predefined classes: tracing agent quan sát class được sinh/định nghĩa trong lúc chạy JVM, lưu bytecode để Native Image đưa vào build metadata; khi native runtime gặp class có cùng tên và bytecode, predefined class có thể được cung cấp.

Tùy chọn thường gặp trong các release hỗ trợ:

~~~bash
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config/,experimental-class-define-support \
  -jar target/application.jar
~~~

Đây là tùy chọn **experimental**. Output có thể có thư mục `agent-extracted-predefined-classes` cùng metadata tương ứng.

Không xem predefined classes như một JVM class loader tổng quát:

- Nó dựa vào các class đã được quan sát và thu thập trong lúc tracing.
- Nó không bảo đảm class mới tùy ý, có bytecode khác hoặc chỉ xuất hiện ở production sẽ hoạt động.
- Tài liệu GraalVM mô tả đây là best-effort cho các dự án legacy, không bảo đảm thành công.
- Trong tài liệu hiện hành, predefined classes không kết hợp với `-H:+RuntimeClassLoading`.

Nếu có thể, ưu tiên tạo code/proxy ở build time hoặc dùng API/framework có tích hợp AOT. Chỉ cân nhắc predefined classes sau khi đã kiểm tra release hỗ trợ và chứng minh use case thực tế bằng native integration test.

## 8. Ma trận chọn giải pháp theo use case

Trước khi quyết định cách xử lý, xác định agent hoặc thư viện đang cần thao tác gì:

| Nhu cầu | JVM | Native Image | Hướng xử lý |
| --- | --- | --- | --- |
| Nạp Java agent lúc khởi động để transform bytecode | `-javaagent` | Không hỗ trợ như JVM runtime | Chuyển instrumentation sang compile/build time hoặc dùng native-compatible integration |
| Attach agent vào JVM đang chạy | Attach API / `agentmain`, phụ thuộc JDK | JVMTI/Attach không được hỗ trợ theo mô hình JVM agent | Dùng native observability hoặc chuyển workload này sang JVM |
| Profiler/coverage dựa trên bytecode | Thường dùng Java agent/JVMTI | Không hoạt động theo cách JVM thông thường | Chạy coverage trên JVM; dùng native profiler cho native binary |
| APM agent dùng `ClassFileTransformer` | Thường dùng `-javaagent` | Không tự hoạt động trong native runtime | Dùng SDK/agent được nhà cung cấp hỗ trợ riêng cho Native Image |
| Thu thập reflection/resource metadata | Có thể chạy ứng dụng với tracing agent | Metadata được dùng khi build native | Dùng `native-image-agent` trên JVM rồi review output |
| Tạo proxy class từ bytecode lúc runtime | JVM hỗ trợ theo class loader/framework | Có thể thử `RuntimeClassLoading` từ GraalVM 25.1+ | Kiểm tra experimental feature, preserve metadata và test trên target |
| Redefine/retransform class đã nạp | `Instrumentation` nếu JVM hỗ trợ | Không được giải quyết bằng RuntimeClassLoading | Thiết kế lại hoặc giữ workload này trên JVM |
| Tạo class trước khi build native | Build-time code generation/annotation processing | Có thể phân tích và compile class đã tạo | Ưu tiên build-time generation và đưa output vào native build |

### Ví dụ: Byte Buddy có thể dùng theo hai cách khác nhau

Một thư viện dùng Byte Buddy có thể:

1. Tạo class proxy mới từ bytecode tại runtime thông qua class loader.
2. Cài agent để thay đổi bytecode của một class đã nạp.

Hai use case này không giống nhau. GraalVM 25.1 runtime class loading nhắm tới trường hợp thứ nhất, trong giới hạn của tính năng experimental. Trường hợp thứ hai phụ thuộc `Instrumentation`/JVMTI và không được hỗ trợ như trên JVM.

Hãy đọc stack trace và API mà thư viện gọi. Tìm các từ khóa `ClassLoader.defineClass`, `ClassFileTransformer`, `Instrumentation`, `redefineClasses`, `retransformClasses`, `VirtualMachine.attach` hoặc `JVMTI` để xác định đúng nhu cầu.

## 9. Cấu hình và kiểm tra phiên bản trong Maven/Gradle

Không chỉ JDK quyết định kết quả. Một dự án Spring Boot native còn có Spring Boot version, GraalVM distribution, Native Build Tools plugin, builder image và hệ điều hành/kiến trúc mục tiêu.

### Ghi lại phiên bản thực tế

Chạy các lệnh trên đúng build environment:

~~~bash
java -version
native-image --version
./mvnw --version
./mvnw dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
~~~

Ghi lại ít nhất:

| Thành phần | Thông tin cần ghi |
| --- | --- |
| JDK | Vendor, version, build number |
| GraalVM | Distribution, Native Image version, LTS/feature release |
| Spring Boot | Framework version và plugin version |
| Native Build Tools | Maven/Gradle plugin version |
| Agent | Tên, version, API sử dụng (`java.lang.instrument`, JVMTI hay tracing agent) |
| Build environment | OS, architecture, compiler/linker |
| Runtime target | OS, architecture, libc/container image |

Không suy ra Native Image version chỉ từ `java -version`. Một JDK GraalVM có thể được cập nhật riêng, và build plugin có thể gọi toolchain khác với runtime Java đang nằm trên `PATH`.

### Truyền RuntimeClassLoading vào Maven

Với dự án đã dùng `native-maven-plugin`, thêm build arguments vào cấu hình plugin hiện có:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-H:+UnlockExperimentalVMOptions</buildArg>
            <buildArg>-H:+RuntimeClassLoading</buildArg>
            <buildArg>-H:-UnlockExperimentalVMOptions</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Cấu hình trên chỉ dành cho GraalVM version có hỗ trợ tùy chọn này. Đừng thêm nó như một cách bật Java agent; nó chỉ mở runtime class loading experimental.

### Truyền RuntimeClassLoading vào Gradle

Ví dụ Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-H:+UnlockExperimentalVMOptions")
            buildArgs.add("-H:+RuntimeClassLoading")
            buildArgs.add("-H:-UnlockExperimentalVMOptions")
        }
    }
}
~~~

Kiểm tra API DSL theo Native Build Tools plugin version đang dùng. Với Kotlin DSL, sử dụng API typed tương ứng của plugin.

Nếu dự án không cần runtime class loading, không thêm option này chỉ vì thấy một thư viện có chữ “dynamic”. Trước hết hãy xác định thư viện đang dùng `defineClass` hay `Instrumentation`.

## 10. Quy trình tra cứu khả năng hỗ trợ theo phiên bản

Khi một agent hoặc thư viện báo không tương thích, thực hiện theo trình tự:

1. **Xác định loại agent:** `-javaagent`, `-agentlib`, `-agentpath`, Attach API, hay `native-image-agent`.
2. **Xác định API mà agent gọi:** `Instrumentation`, `ClassFileTransformer`, JVMTI, `ClassLoader.defineClass`, reflection hay JNI.
3. **Ghi chính xác toolchain:** JDK vendor/version, GraalVM Native Image version, Spring Boot và Native Build Tools plugin.
4. **Đọc Java Instrumentation Javadoc:** xác nhận manifest, `premain`/`agentmain`, startup option và dynamic attach policy.
5. **Đọc Native Image Compatibility Guide đúng version:** tìm mục Debugging and Monitoring, JVMTI và bytecode-based tools.
6. **Đọc Native Image Tracing Agent docs đúng version:** xác nhận option, metadata output format và các experimental agent options.
7. **Nếu cần định nghĩa class lúc runtime:** đọc Run-Time Class Loading docs và release notes; xác nhận có `-H:+RuntimeClassLoading` hay không.
8. **Tạo smoke test nhỏ:** kiểm tra đúng thao tác agent cần làm, không chỉ kiểm tra executable khởi động.
9. **Chạy test trong native binary:** xác minh cả luồng thành công và nhánh lỗi.
10. **Ghi kết luận theo version:** version nào đã test, cơ chế nào hoạt động, cơ chế nào không, giới hạn nào còn lại.

### Các trang chính thức nên tra cứu

- Java SE `java.lang.instrument` API: https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html
- JEP 451 — Prepare to Disallow the Dynamic Loading of Agents: https://openjdk.org/jeps/451
- GraalVM Native Image Compatibility Guide: https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/Compatibility/
- GraalVM Tracing Agent: https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/AutomaticMetadataCollection/
- GraalVM Runtime Class Loading: https://www.graalvm.org/dev/reference-manual/native-image/runtime-class-loading/
- GraalVM 25.1 release notes: https://www.graalvm.org/release-notes/25.1/
- GraalVM JDK 23 release notes: https://www.graalvm.org/release-notes/JDK_23/

Đọc tài liệu có selector/version cụ thể và chọn đúng release trước khi áp dụng ví dụ. Trang `latest` hoặc `dev` có thể mô tả tính năng chưa có trong LTS mà dự án đang dùng.

## 11. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| JVM chạy với `-javaagent`, native báo không hỗ trợ agent | Agent dựa vào Java Instrumentation/JVMTI | Xác nhận API agent sử dụng; tìm native-compatible integration hoặc chuyển sang build-time instrumentation |
| `premain` không được gọi | Agent JAR thiếu `Premain-Class`, sai đường dẫn hoặc không dùng JVM launcher | Kiểm tra manifest, lệnh chạy và log JVM |
| Dynamic attach in warning trên JDK 21+ | Agent được nạp vào JVM đang chạy | Tìm nguồn Attach API; ưu tiên `-javaagent` lúc startup hoặc opt-in có chủ đích |
| Native executable không có `Instrumentation` | Native runtime không triển khai mô hình JVM agent | Không cố nạp agent bằng `-javaagent`; dùng cơ chế quan sát phù hợp native |
| `native-image-agent` không tạo đủ metadata | Kịch bản tracing chưa đi qua nhánh động | Chạy nhiều kịch bản và merge output, review metadata |
| Metadata từ GraalVM cũ không được nhận diện như mong đợi | Khác schema/định dạng giữa các release | Kiểm tra `reachability-metadata.json` và schema của toolchain hiện tại |
| Byte Buddy tạo class thất bại trong native | Runtime class loading chưa bật hoặc thiếu setup/preserve | Xác minh GraalVM 25.1+, experimental option, class loader và giới hạn |
| `ClassLoader.defineClass` hoạt động nhưng redefine class lỗi | Runtime class loading không cung cấp `Instrumentation.redefineClasses` | Thiết kế lại use case; dynamic class definition và class retransformation là hai cơ chế khác nhau |
| Agent hoạt động trong test JVM nhưng native test không có coverage | Test agent chỉ instrument JVM test process | Chạy coverage trên JVM hoặc dùng công cụ native-aware |
| Native build thành công nhưng APM không thấy trace | APM phụ thuộc bytecode agent hoặc không có native integration | Dùng SDK instrumentation/library-level hoặc agent riêng do nhà cung cấp hỗ trợ Native Image |

### Checklist khi review pull request

- [ ] Agent có thật sự cần `Instrumentation`/JVMTI không?
- [ ] Agent được nạp lúc startup hay attach sau startup?
- [ ] Có đang nhầm `native-image-agent` với agent của ứng dụng không?
- [ ] Có đang nhầm runtime class loading với bytecode transformation không?
- [ ] GraalVM release có hỗ trợ đúng tính năng cần dùng không?
- [ ] Các tùy chọn experimental đã được ghi nhận và test trên target chưa?
- [ ] Metadata tracing đã bao phủ các đường nghiệp vụ cần thiết chưa?
- [ ] Native executable đã được test với đúng APM/profiler/monitoring integration dự kiến chưa?

## 12. Bài thực hành: kiểm tra một agent trên JVM và đánh giá đường chuyển sang native

Tạo một Java agent nhỏ theo ví dụ ở mục 1, sau đó dùng cùng một ứng dụng Spring Boot để so sánh hai chế độ.

**Phần A — JVM**

1. Đóng gói agent với manifest có `Premain-Class`.
2. Chạy Spring Boot JAR bằng `java -javaagent:... -jar ...`.
3. Xác minh `premain` được gọi và transformer nhìn thấy class ứng dụng.
4. Thử một test JVM dùng công cụ instrumentation để ghi nhận method hoặc class được gọi.
5. Trên JDK 21 trở lên, kiểm tra riêng dynamic attach warning nếu một dependency sử dụng Attach API.

**Phần B — Native Image**

1. Build ứng dụng bằng Spring AOT và GraalVM Native Image.
2. Chạy native executable, xác minh `-javaagent` không phải cơ chế để instrument native runtime.
3. Chạy JVM ứng dụng với `-agentlib:native-image-agent=config-output-dir=...` để thu reachability metadata cho các đường truy cập động.
4. Review metadata và build lại native executable.
5. Nếu ứng dụng sinh class bằng `ClassLoader.defineClass`, tạo một nhánh thử nghiệm với GraalVM 25.1+ và `-H:+RuntimeClassLoading`; kiểm tra riêng giới hạn của feature.
6. Ghi lại kết quả cho từng cơ chế: startup agent, dynamic attach, tracing metadata, runtime class loading.

### Câu hỏi tự kiểm tra

1. `premain` và `agentmain` khác nhau ở thời điểm nào?
2. `-javaagent` khác `-agentlib` và `-agentpath` như thế nào?
3. JEP 451 thay đổi điều gì đối với dynamic agent loading từ JDK 21?
4. Vì sao một Java agent chạy tốt trên JVM có thể không chạy trong Native Image?
5. Native Image Tracing Agent tạo metadata gì và nó chạy trong tiến trình nào?
6. Vì sao tracing agent không thể tự chứng minh tất cả dynamic access đã được thu thập?
7. `reachability-metadata.json` khác các file metadata riêng trong các GraalVM release cũ như thế nào?
8. `-H:+RuntimeClassLoading` từ GraalVM 25.1 hỗ trợ thao tác nào?
9. Vì sao runtime class loading không đồng nghĩa với hỗ trợ `Instrumentation.redefineClasses`?
10. Khi nào nên dùng build-time bytecode weaving thay vì load-time Java agent?

**Tiêu chí đạt:** phân biệt được Java agent, JVMTI agent, Native Image Tracing Agent và runtime class loading; tra cứu được giới hạn theo JDK/GraalVM release; giải thích được thay đổi dynamic attach từ JDK 21; nhận diện đúng tính năng experimental từ GraalVM 25.1; đồng thời đưa ra được phương án kiểm thử và thay thế phù hợp cho ứng dụng Spring Boot Native Image.
