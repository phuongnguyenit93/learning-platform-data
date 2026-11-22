# Kiểm tra java.instrument, jdk.attach và các module cần thiết trong runtime tùy chỉnh

Khi đóng gói ứng dụng Java bằng **jlink** hoặc **jpackage** với một **custom runtime image**, chương trình có thể chạy tốt trên JDK phát triển nhưng Java agent lại không khởi động được, hoặc công cụ attach không thể nạp agent vào JVM đang chạy. Nguyên nhân thường gặp là **runtime được rút gọn thiếu module cần thiết**, nhầm vai trò của **java.instrument** với **jdk.attach**, hoặc thiếu những điều kiện khác ngoài module (manifest, JVM support, quyền OS, class loader, module cho logging/JMX/JFR và các thư viện agent).

Điểm cần phân biệt ngay:

- **java.instrument** cung cấp **java.lang.instrument.Instrumentation**, **ClassFileTransformer** và cơ chế hỗ trợ Java agent. Runtime **đích** dùng **-javaagent** hoặc nhận một **Java agent** nạp động cần có khả năng instrumentation phù hợp, thường bao gồm module này.
- **jdk.attach** cung cấp **com.sun.tools.attach.VirtualMachine**, **AttachProvider** và API cho **công cụ chủ động kết nối tới JVM khác**. Nó cần có ở **runtime của attach client**. Trên HotSpot Java 17+, **JVM đích không nhất thiết phải chứa jdk.attach** chỉ để nhận agent từ một client bên ngoài.
- **Có module không có nghĩa là tính năng chắc chắn hoạt động**. Agent JAR còn cần manifest/callback đúng; attach còn phụ thuộc implementation JVM, OS permissions, PID namespace, JVM flags và đường dẫn agent JAR mà JVM đích đọc được.
- **jdeps chỉ là điểm bắt đầu**. Nó phân tích các phụ thuộc tĩnh nhận diện được trong class files; module dùng bằng reflection, service loading, JNI, plugin hoặc cơ chế agent có thể phải thêm thủ công khi chạy **jlink --add-modules**.

Bài này hướng tới **Java 17 trở lên**, sử dụng **Java 17 APIs và lệnh build có thể chạy**, phân biệt ba runtime image (chạy startup agent, chạy attach client, và cả hai), cung cấp ví dụ agent có **premain + agentmain**, probe module bằng **ModuleFinder**, một attach client thật, phép thử thiếu module và checklist triển khai/CI. Các kết quả môi trường nêu rõ phần nào phụ thuộc JDK/vendor/OS.

## 1. Sơ đồ tổng quát: runtime đích và runtime công cụ

Hãy hình dung một service chạy trên máy hoặc container A, còn một công cụ quản trị cần nạp agent vào service ấy:

~~~text
BUILD JDK (có jlink, jdeps, javac, jar)
    |
    |-- tạo runtime-image target
    |      ├── java.base
    |      ├── java.instrument   <-- cần cho Java agent phía target
    |      └── các module nghiệp vụ/monitoring thực sự dùng
    |
    |-- tạo runtime-image client
           ├── java.base
           └── jdk.attach       <-- chứa Attach API phía client

PRODUCTION / TARGET PROCESS
  rt-target/bin/java -javaagent:probe-agent.jar ...  (startup agent)
          hoặc
  rt-target/bin/java -cp ... Target                 (chờ attach)
                     ^
                     | Attach API / JVM attach mechanism
                     |
ADMIN / CLIENT PROCESS
  rt-client/bin/java -cp ... AttachClient PID agent.jar
       |
       └── VirtualMachine.attach(PID), loadAgent(path), detach()
~~~

**Hai process có thể dùng hai runtime image khác nhau.** Nếu agent chỉ được khởi động bằng **-javaagent**, thường **không cần jdk.attach trong target image**. Nếu tool chỉ thực hiện attach từ bên ngoài, **client cần jdk.attach** nhưng bản thân nó **không bắt buộc có java.instrument** để gọi VirtualMachine.loadAgent. Target muốn nhận **Java agent** vẫn phải có cơ chế Java instrumentation và quyền attach khả dụng.

Trong ứng dụng *tự attach chính nó*, cả hai vai trò nằm trong một JVM; khi đó phải xem xét cả hai module/capability và hạn chế self-attach. Đây **không** phải workflow khuyến nghị cho mọi ứng dụng.

## 2. Bảng chọn module theo tình huống

| Nhu cầu | Runtime thực thi | Module cần kiểm tra | Các điều kiện khác |
| --- | --- | --- | --- |
| Chạy **-javaagent:agent.jar** từ startup | **Target JVM** | **java.instrument** | Premain-Class, premain hợp lệ, jar đọc được |
| Agent dùng **ClassFileTransformer** | **Target JVM** | **java.instrument** | Đúng classloader, bytecode hợp lệ, capability nếu cần |
| Attach API gọi **VirtualMachine.attach(pid)** | **Client JVM** | **jdk.attach** | Provider hỗ trợ, PID, OS rights |
| Attach API gọi **loadAgent(agent.jar)** | Client + Target | **jdk.attach ở client**, **java.instrument ở target** | Target cho phép attach, Agent-Class/agentmain, JAR nhìn thấy ở target |
| Client tự attach vào cùng JVM | Cùng JVM | Thường **jdk.attach + java.instrument** | Self-attach policy của JVM, không mặc định được phép |
| **JMX / ManagementFactory** | JVM có component đó | **java.management** | Export/management config, network nếu remote |
| **HotSpotDiagnosticMXBean** | JVM dùng API đó | **jdk.management**, các dependencies | Phụ thuộc vendor/API khả dụng |
| **Java Flight Recorder APIs** | JVM dùng JFR | **jdk.jfr** | JVM JFR support, file/path/permissions |
| **Remote JMX management agent** | Target | Có thể cần **jdk.management.agent**, java.management.rmi và các dependencies | Quyền mạng, credentials/TLS và cấu hình management |
| **Debug bằng JDWP** | JVM debug | **jdk.jdwp.agent** hoặc các modules theo vendor | -agentlib:jdwp, cổng/transport/security |
| **jcmd** như serviceability tool | Runtime chứa công cụ | **jdk.jcmd** và các dependencies phù hợp | Bản image có tool; attach mechanism vẫn phải cho phép |
| Logging dùng java.util.logging | Runtime chứa code | **java.logging** | Config handler/file permissions |
| Framework dùng sun.misc.Unsafe | Runtime chứa code | Có thể cần **jdk.unsupported** | Cân nhắc thay internal API; kiểm tra vendor |
| JDBC, XML, DNS, crypto providers, charsets, locale | Runtime chứa code | **java.sql, java.xml, jdk.naming.dns, jdk.crypto.ec, jdk.charsets, jdk.localedata** khi thực sự cần | Provider/service binding và dữ liệu runtime |

Danh sách trên **không phải cấu hình bắt buộc cho mọi ứng dụng**. Mục đích của jlink là gom **đúng modules ứng dụng + agent + tools** thực sự cần, cùng dependencies tương ứng, không phải nhét tất cả module JDK vào một image để tránh lỗi.

### 2.1. java.instrument là module của agent, không phải JAR agent

Module **java.instrument** chỉ cung cấp Java platform API/VM integration. **Agent logic** vẫn nằm ở **agent.jar** do bạn phân phối, có **Premain-Class**, **Agent-Class** hoặc cả hai. Chỉ thêm java.instrument vào image không tự sinh một transformer, không khiến agent tự được nạp và không cung cấp các thư viện riêng của agent như ASM/Byte Buddy.

Một startup agent có thể được kích hoạt bằng:

~~~bash
rt-target/bin/java -javaagent:probe-agent.jar -cp out/classes Probe
~~~

Còn một agent nạp sau startup dùng một tiến trình có Attach API để gọi **VirtualMachine.loadAgent(...)**. Đây là hai con đường **khác giai đoạn**; cùng một JAR có thể hỗ trợ cả hai nếu manifest và callback được khai báo đầy đủ.

### 2.2. jdk.attach không phải “bật quyền attach” trong target

**jdk.attach** chứa API dùng ở phía **client**. Một HotSpot target không chứa module này vẫn có thể nhận attach từ bên ngoài qua attach mechanism của VM, nếu target có runtime support thích hợp và không bị chặn. Thêm jdk.attach vào target **không tự khắc phục**:

- JVM được chạy với **-XX:+DisableAttachMechanism**.
- OS/container không cho client nhìn thấy PID hoặc liên lạc qua attach socket.
- Khác user/permissions, security policy hoặc attach provider không phù hợp.
- Target không có **java.instrument** hoặc không hỗ trợ dynamic Java agent loading.
- **Agent-Class/agentmain** thiếu hoặc agent JAR chỉ tồn tại trên filesystem của client.

**Chẩn đoán đúng vai trò:** khi client gặp **NoClassDefFoundError: com/sun/tools/attach/VirtualMachine**, kiểm tra **jdk.attach của client**. Khi target báo không tìm thấy instrumentation library/module lúc chạy **-javaagent**, kiểm tra **java.instrument của target**.

## 3. jlink xây custom runtime ra sao?

**jlink** lấy các **root modules** trong **--add-modules**, giải quyết và đóng gói các **transitive module dependencies**, rồi tạo một runtime image cho hệ điều hành/kiến trúc của JDK đang build.

~~~bash
# Image chỉ dành cho startup Java agent và target nhận agent.
jlink --add-modules java.base,java.instrument \
      --output rt-target

# Image dành cho client gọi Attach API.
jlink --add-modules java.base,jdk.attach \
      --output rt-client

# Image cần cả hai vai trò trong cùng một runtime.
jlink --add-modules java.base,java.instrument,jdk.attach \
      --output rt-full
~~~

Đây là lệnh **JDK build**, không chạy bằng **rt-target/bin/jlink**. Custom image thường không chứa các lệnh phát triển **javac/jlink/jdeps/jar** trừ khi bạn chủ động đưa những tool modules vào image. Image nên xây bằng JDK cùng target version, vendor, OS/architecture phù hợp; không coi một image Linux x86-64 là portable sang Windows hoặc ARM.

**Không cần liệt kê mọi transitive dependency thủ công.** Chẳng hạn module jdk.attach có thể kéo thêm module phục vụ attach provider; hãy kiểm tra output image thực thay vì copy cứng danh sách phụ thuộc cho mọi JDK.

### 3.1. Cú pháp module path

Nếu chỉ link modules JDK, **jlink** mặc định tìm chúng ở thư mục **jmods** của JDK build. Với ứng dụng modular thực sự, có thể chỉ định **--module-path** tới thư mục JMOD/JAR của ứng dụng cùng JDK modules và đưa tên module ứng dụng vào **--add-modules**.

~~~bash
# Ví dụ tham khảo cho ứng dụng modular có module demo.app trong mods.
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules demo.app,java.instrument,jdk.attach \
      --output rt-modular
~~~

Dấu **:** giữa các module-path entries phù hợp Linux/macOS; Windows dùng **;**. Ví dụ chỉ đúng khi **mods** đã chứa module demo.app hợp lệ và JAVA_HOME trỏ tới JDK có jmods. Nếu ứng dụng được chạy ở **classpath**, có thể tạo runtime chỉ từ JDK modules như ba lệnh đầu và **phân phối các application JAR riêng**.

### 3.2. Không phải module nào cũng được resolve ở boot layer

Có ba trạng thái cần phân biệt:

1. Module **có trong build JDK** (bộ đầu vào của jlink).
2. Module **đã được link vào runtime image** (có thể thấy bằng **--list-modules**).
3. Module **đã được resolve vào boot layer của một process cụ thể** (có thể kiểm tra bằng **ModuleLayer.boot().findModule(...)**).

Với **named modules**, dependency cần được giải quyết qua **requires**, launcher root module selection và khi thích hợp **--add-modules**. Có module trong image là điều kiện để nó *có thể* được resolve, không tự chứng minh class trong mọi process đều đã đọc được module ấy.

**--add-modules jdk.attach** trên một image đã link thiếu jdk.attach **không thể tạo module từ không khí**; phải build lại image có module đó trước.

## 4. Kiểm tra trực tiếp runtime image trước khi deploy

Đừng dựa vào output của **java --list-modules** thuộc JDK phát triển nếu production sử dụng **rt-target/bin/java**. Luôn chạy đúng binary mà sản phẩm sẽ dùng.

### 4.1. Kiểm tra version và java.home

~~~bash
./rt-target/bin/java -version

./rt-target/bin/java -XshowSettings:properties -version
~~~

Trong kết quả properties, kiểm tra **java.home**, **java.version**, **java.vendor**, **os.arch**. Điều này giúp phát hiện container/app launcher đang chạy **JDK hệ thống** thay vì **custom runtime image** mà build đã tạo. Nếu output dài, có thể lọc trong CI; nhưng hãy lưu cả stderr vì những lệnh version/settings thường in ở stderr.

### 4.2. Liệt kê những module thực sự nằm trong image

~~~bash
./rt-target/bin/java --list-modules
./rt-client/bin/java --list-modules
./rt-full/bin/java --list-modules
~~~

Ví dụ cấu trúc đầu ra (dấu version phụ thuộc bản JDK build):

~~~text
# rt-target:
java.base@<runtime-version>
java.instrument@<runtime-version>

# rt-client:
java.base@<runtime-version>
jdk.attach@<runtime-version>
jdk.internal.jvmstat@<runtime-version>

# rt-full:
java.base@<runtime-version>
java.instrument@<runtime-version>
jdk.attach@<runtime-version>
jdk.internal.jvmstat@<runtime-version>
~~~

Đây là **minh họa với bản HotSpot đã thử**, không phải cam kết module phụ thuộc sẽ có đúng tên/tập như vậy trên mọi JVM. Đừng cắt các module transitive khỏi image bằng thao tác file thủ công.

### 4.3. Xem mô tả từng module

~~~bash
./rt-full/bin/java --describe-module java.instrument
./rt-full/bin/java --describe-module jdk.attach
./rt-full/bin/java --validate-modules
~~~

**--describe-module** cung cấp module descriptor từ runtime image; **--validate-modules** giúp kiểm tra một số xung đột module. Nếu module thiếu, lệnh describe-module sẽ thông báo không tìm thấy. Tuy vậy **--validate-modules thành công** không chứng minh agent JAR hợp lệ hay attach có được OS cho phép.

### 4.4. Phân biệt module khả dụng và module đã resolve bằng Java

Có thể kiểm tra bằng Java API:

~~~java
// Đoạn minh họa từ một JVM đang chạy.
boolean available = java.lang.module.ModuleFinder.ofSystem()
        .find("java.instrument").isPresent();

boolean bootResolved = ModuleLayer.boot()
        .findModule("java.instrument").isPresent();
~~~

**ModuleFinder.ofSystem()** kiểm tra module hệ thống khả dụng ở runtime hiện tại. **ModuleLayer.boot()** kiểm tra module đã resolve của process. Hai phép kiểm tra phục vụ hai câu hỏi khác nhau. Ví dụ chương trình hoàn chỉnh ở phần 6 sẽ in các giá trị này.

## 5. jdeps giúp tìm module nhưng không thể tìm hết dependency động

**jdeps** phân tích dependencies ở mức class file và có output phù hợp cho jlink:

~~~bash
jdeps --print-module-deps --multi-release 17 app.jar
jdeps --print-module-deps --multi-release 17 agent.jar
~~~

Đầu ra thường là **danh sách module, phân cách bằng dấu phẩy**. Có thể dùng danh sách như đầu vào cho **jlink --add-modules**, sau khi kiểm tra/ghép thêm những root modules dùng tại runtime.

Với demo bên dưới, lệnh phân tích chỉ riêng class agent và client có các kết quả tối thiểu:

~~~bash
jdeps --print-module-deps probe-agent.jar
jdeps --print-module-deps out/classes/AttachClient.class
~~~

Output quan sát trên JDK thử nghiệm:

~~~text
java.base,java.instrument
java.base,jdk.attach
~~~

Đó là minh họa rõ vai trò: code **RuntimeAgent** sử dụng **java.lang.instrument**, code **AttachClient** import **com.sun.tools.attach.VirtualMachine**. Nhưng **ứng dụng target** có thể chỉ import **java.base** trong source, trong khi vẫn cần **java.instrument** vì agent được chỉ định bằng **-javaagent**. Nếu chỉ chạy **jdeps app.jar**, bạn có thể **bỏ sót module quan trọng của startup agent**.

### 5.1. Những phụ thuộc jdeps thường không nhìn thấy đầy đủ

- **Class.forName("...")** và tên class được ghép động từ cấu hình.
- **ServiceLoader** và các **provider modules** chưa được làm rõ khi link image.
- Agent được load qua **-javaagent**, **Attach API** hoặc tên JAR nằm ngoài application JAR.
- Native code JNI/JVM TI gọi Java classes hoặc cần native libraries bên ngoài.
- Plugin discovery theo thư mục hoặc classloader tùy biến.
- Một thư viện chỉ gọi code của module nhất định theo feature flag hoặc lúc xử lý lỗi.
- Bytecode generation tạo tham chiếu tới class/helper sau khi tiến trình đã khởi động.
- Reflection sâu cần **--add-opens**, một chuyện khác với chỉ có module trong image.
- Multi-release JAR có các class phụ thuộc module khác nhau ở các phiên bản JDK.

Đừng dùng **--ignore-missing-deps** để giấu vấn đề rồi kết luận image hợp lệ; chỉ dùng khi hiểu phụ thuộc bị bỏ qua và có một kiểm thử runtime tương ứng.

### 5.2. Cách tổng hợp module roots cho một sản phẩm

1. Chạy **jdeps** cho **application artifacts** và **agent JAR**, không chỉ cho main class.
2. Đọc source/config đường **Attach API** hoặc các công cụ monitoring bên ngoài.
3. Thêm **java.instrument** nếu target dùng startup/dynamic Java agent.
4. Thêm **jdk.attach** **vào client runtime** nếu client gọi Attach API.
5. Thêm các module JMX/JFR/logging/JDBC/service providers phù hợp mà agent hoặc app cần.
6. Dùng jlink với root modules đã kiểm tra; không dựa vào một danh sách phụ thuộc cố định áp dụng cho mọi dự án.
7. Chạy smoke/integration tests **bằng image thành phẩm**, không bằng JDK đầy đủ.
8. Kiểm tra lại sau mỗi thay đổi JDK/vendor, agent version, framework, OS image hoặc cấu hình packaging.

**jlink --bind-services** có thể kéo thêm các provider modules theo service binding; hãy đánh giá ảnh hưởng về size và test thay vì coi đó là tùy chọn bắt buộc cho mọi agent.

## 6. Ví dụ Java 17 chạy được: ba runtime image, startup agent và attach

Ví dụ dùng **bốn file Java và một manifest**. Không dùng thư viện bên ngoài, chỉ yêu cầu JDK 17+ để compile và tạo image bằng jlink. Code:

- **Probe**: in module có mặt trong runtime image và module jdk.attach đã resolve ở boot layer hay chưa.
- **RuntimeAgent**: có **premain** cho startup và **agentmain** cho dynamic attach.
- **Target**: process đang chạy, tạo khoảng thời gian để client attach.
- **AttachClient**: sử dụng **VirtualMachine.attach(pid)** rồi **loadAgent**.

**Đây là ví dụ dành cho môi trường thử nghiệm do bạn kiểm soát**, chạy hai process cùng máy/hệ điều hành và user phù hợp. Không dùng attach vào process bất kỳ không có quyền quản lý.

### 6.1. Cấu trúc thư mục

~~~text
runtime-modules-demo/
  src/
    Probe.java
    RuntimeAgent.java
    Target.java
    AttachClient.java
  agent.mf
  out/
    classes/               <- javac tạo
  probe-agent.jar           <- jar tạo
  rt-target/                <- jlink tạo
  rt-client/                <- jlink tạo
  rt-full/                  <- jlink tạo
~~~

Các class trong **default package** chỉ để đơn giản hóa lệnh học. Khi đóng gói sản phẩm, nên dùng package riêng và bảo đảm manifest trỏ đúng **binary class name**.

### 6.2. File src/Probe.java

~~~java
import java.lang.module.ModuleFinder;

public final class Probe {
    private Probe() {
    }

    public static void main(String[] args) {
        System.out.println("HAS_INSTRUMENT="
                + ModuleFinder.ofSystem()
                        .find("java.instrument").isPresent());

        System.out.println("HAS_ATTACH="
                + ModuleFinder.ofSystem()
                        .find("jdk.attach").isPresent());

        System.out.println("ATTACH_RESOLVED="
                + ModuleLayer.boot()
                        .findModule("jdk.attach").isPresent());

        System.out.println("PROBE_OK");
    }
}
~~~

**ModuleFinder.ofSystem().find** không import **java.lang.instrument** hay **com.sun.tools.attach**. Nó chỉ hỏi graph/module catalog ở **runtime đang thực thi Probe**. Điều này có ích khi probe phải chạy được cả trên image tối giản không có java.instrument hoặc jdk.attach.

**ATTACH_RESOLVED** cho thấy jdk.attach đã ở boot layer chưa. Nếu image có module nhưng chưa resolve theo cách launch hiện tại, có thể cần cấu hình **requires** hoặc **--add-modules jdk.attach** thích hợp; không thể dùng --add-modules để thay cho bước jlink inclusion.

### 6.3. File src/RuntimeAgent.java

~~~java
import java.lang.instrument.Instrumentation;

public final class RuntimeAgent {
    private RuntimeAgent() {
    }

    public static void premain(
            String options, Instrumentation inst) {
        System.out.println("PREMAIN_OK");
        System.out.println("RETRANSFORM="
                + inst.isRetransformClassesSupported());
    }

    public static void agentmain(
            String options, Instrumentation inst) {
        System.out.println("AGENTMAIN_OK");
    }
}
~~~

Ở đây **premain** nhận **Instrumentation** trực tiếp từ JVM khi **-javaagent** có hiệu lực; **agentmain** nhận Instrumentation khi agent được load sau startup. Không tạo object Instrumentation bằng new, không dùng singleton tự đoán. Để bài tập tập trung vào **runtime modules**, agent chưa đăng ký ClassFileTransformer.

**RETRANSFORM=false** trong output mẫu do manifest của bài **không khai báo Can-Retransform-Classes: true**. Có java.instrument không đồng nghĩa mọi capability tùy chọn đều được bật. Nếu agent thật cần retransform/redefine/native prefix, phải khai báo capability cần thiết trong manifest, kiểm tra **isRetransformClassesSupported() / isRedefineClassesSupported() / isNativeMethodPrefixSupported()**, rồi xử lý giới hạn class modifications.

### 6.4. File src/Target.java

~~~java
public final class Target {
    private Target() {
    }

    public static void main(String[] args)
            throws InterruptedException {
        System.out.println("TARGET_READY");
        Thread.sleep(15000);
        System.out.println("TARGET_END");
    }
}
~~~

Lớp này tạo **một JVM đích** sống 15 giây để client có cơ hội attach. Thời gian được chọn vì đơn giản, không phù hợp kiểm thử chạy trên máy CI rất chậm. Trong test production thực, nên dùng một service/ready signal có lifecycle được kiểm soát, không dựa hoàn toàn vào sleep.

### 6.5. File src/AttachClient.java

~~~java
import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachClient {
    private AttachClient() {
    }

    public static void main(String[] args)
            throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: AttachClient PID agent.jar");
        }

        String pid = args[0];
        String agentJar = Path.of(args[1])
                .toAbsolutePath().toString();

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(agentJar, "smoke");
            System.out.println("ATTACH_OK");
        } finally {
            vm.detach();
        }
    }
}
~~~

**VirtualMachine.attach** ở **client process** mở kết nối tới target theo provider của JDK/OS. **loadAgent** truyền **đường dẫn JAR để target đọc** và khiến target gọi **agentmain**, không phải premain. **finally** luôn detach sau khi đã attach thành công.

Nếu client chạy ở container khác hoặc filesystem khác, đường dẫn **agentJar phải tồn tại và đọc được ở target**, không chỉ ở client. Java Attach API thông thường là một cơ chế tương tác với VM đang chạy trên môi trường được provider hỗ trợ, không phải giao thức nạp JAR từ xa tùy ý qua Internet.

### 6.6. File agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: RuntimeAgent
Agent-Class: RuntimeAgent
~~~

Lưu file có **newline ở cuối**. **Premain-Class** phục vụ **-javaagent**; **Agent-Class** phục vụ **VirtualMachine.loadAgent**. Một JAR có thể chứa cả hai. Không nhất thiết phải thêm **Can-Retransform-Classes** nếu ví dụ chỉ in log. Nếu manifest thiếu **Agent-Class**, attach client có thể mở kết nối thành công nhưng **loadAgent** thất bại do không tìm được agent entry point thích hợp.

### 6.7. Compile và tạo JAR

Trong thư mục gốc, với JDK 17+ và shell POSIX:

~~~bash
mkdir -p out/classes

javac --release 17 -d out/classes \
    src/Probe.java src/RuntimeAgent.java \
    src/Target.java src/AttachClient.java

jar cfm probe-agent.jar agent.mf \
    -C out/classes RuntimeAgent.class
~~~

Lưu ý:

- **javac --release 17** khiến code dùng API tương thích Java 17 và class file tương ứng.
- Compilation được thực hiện bằng **JDK build** có **jdk.attach** (để compile AttachClient), không phải bằng image chỉ gồm java.base.
- Agent JAR chỉ cần **RuntimeAgent.class** và manifest trong bài, không cần đóng gói Probe/Target/AttachClient.
- Các file ứng dụng/test dùng **out/classes** làm classpath riêng.
- Nếu source là modular, cần khai báo **requires java.instrument** hoặc **requires jdk.attach** ở module thực sự import API và biên dịch với module path phù hợp; demo default-package thuộc unnamed module nên không có module-info.java.

Để kiểm tra JAR:

~~~bash
jar tf probe-agent.jar
jdeps --print-module-deps probe-agent.jar
jdeps --print-module-deps out/classes/AttachClient.class
~~~

Đầu ra của hai lệnh jdeps cuối ở bộ test này:

~~~text
java.base,java.instrument
java.base,jdk.attach
~~~

### 6.8. Build ba runtime images

~~~bash
jlink --add-modules java.base,java.instrument \
      --output rt-target

jlink --add-modules java.base,jdk.attach \
      --output rt-client

jlink --add-modules java.base,java.instrument,jdk.attach \
      --output rt-full
~~~

Chạy jlink bằng **JDK 17+ xây image** và chỉ định output directory chưa tồn tại. Đừng chạy lại trùng tên output đã tạo rồi cho rằng jlink tự thay thế atomically; trong build pipeline nên dùng đường dẫn build mới, kiểm tra rồi promote artifact.

### 6.9. Test target chỉ chứa java.instrument

~~~bash
./rt-target/bin/java -cp out/classes Probe
~~~

Output:

~~~text
HAS_INSTRUMENT=true
HAS_ATTACH=false
ATTACH_RESOLVED=false
PROBE_OK
~~~

Startup agent vẫn hoạt động:

~~~bash
./rt-target/bin/java \
    -javaagent:probe-agent.jar \
    -cp out/classes Probe
~~~

Output:

~~~text
PREMAIN_OK
RETRANSFORM=false
HAS_INSTRUMENT=true
HAS_ATTACH=false
ATTACH_RESOLVED=false
PROBE_OK
~~~

**Kết luận:** **-javaagent không cần jdk.attach** ở target trong ví dụ. java.instrument được link vào image, agent JAR có Premain-Class và premain hoạt động.

### 6.10. Test client chỉ chứa jdk.attach

~~~bash
./rt-client/bin/java -cp out/classes Probe
~~~

Output quan sát trên HotSpot thử nghiệm:

~~~text
HAS_INSTRUMENT=false
HAS_ATTACH=true
ATTACH_RESOLVED=true
PROBE_OK
~~~

Client chứa Attach API nên có thể gọi VirtualMachine; nó không cần java.instrument trong **chính runtime client** vì không chạy agent Java tại client. Module jdk.attach kéo các dependencies cần thiết khi jlink tạo image.

**Lưu ý về boot resolution:** Với cấu hình classpath demo này, jdk.attach được resolve ở boot layer như output. Với named module hoặc chế độ launch khác, hãy kiểm tra chính process bằng **ModuleLayer.boot()**, và dùng **requires/--add-modules** khi cần.

### 6.11. Test dynamic attach từ client vào target

Với Linux/macOS và shell POSIX, đứng trong thư mục dự án:

~~~bash
# Chạy target ở background và lưu PID.
./rt-target/bin/java -cp out/classes Target \
    > target.log 2>&1 &
TARGET_PID=$!

# Đợi target in TARGET_READY.
sleep 1

# Client khác JVM, dùng image chỉ có jdk.attach.
./rt-client/bin/java -cp out/classes AttachClient \
    "$TARGET_PID" "$(pwd)/probe-agent.jar"

wait "$TARGET_PID"
cat target.log
~~~

Trong một môi trường HotSpot cho phép attach, output client:

~~~text
ATTACH_OK
~~~

Output phần **ứng dụng** trong target.log:

~~~text
TARGET_READY
AGENTMAIN_OK
TARGET_END
~~~

**Thứ tự này được quan sát trong ví dụ đơn giản.** Target log có thể chứa thêm warning/diagnostic từ VM, nhất là trên các JDK mới. Các warning không thay thế event **AGENTMAIN_OK**. Nếu attach bị cấm hoặc target đã thoát trước khi client kết nối, **AttachNotSupportedException**, **IOException**, **AgentLoadException** hoặc **AgentInitializationException** có thể xảy ra và phải được chẩn đoán thay vì gán mặc định cho thiếu module.

Trên Windows, thay shell background/PID bằng quy trình quản lý hai terminal và PID tương ứng, dùng đường dẫn target/agent phù hợp. Cơ chế PID và permissions phụ thuộc OS.

**Kết quả đã thử nghiệm:** bộ mã tương đương được build bằng **javac --release 17** và chạy trên **OpenJDK 21 (Linux)**. Image target chỉ có **java.base + java.instrument**, image client có **java.base + jdk.attach**, và một attach client riêng đã nạp agent vào target thành công. Điều này xác nhận ngữ nghĩa **target không cần jdk.attach chỉ để nhận agent** trong môi trường HotSpot thử nghiệm; không phải cam kết mọi JVM vendor/OS đều giống hệt.

### 6.12. rt-full khi cần cả hai vai trò

~~~bash
./rt-full/bin/java -cp out/classes Probe
~~~

Output:

~~~text
HAS_INSTRUMENT=true
HAS_ATTACH=true
ATTACH_RESOLVED=true
PROBE_OK
~~~

Dùng **rt-full** khi một runtime image thật sự chạy ứng dụng có cả instrumentation và Attach API. Nếu production chỉ dùng startup agent, image **rt-target** là ví dụ tối giản hơn; không nên thêm jdk.attach chỉ vì tên chức năng nghe có liên quan.

## 7. Negative test: image thiếu java.instrument

Có thể tạo một image tối giản để thấy lỗi:

~~~bash
jlink --add-modules java.base --output rt-minimal

./rt-minimal/bin/java \
    -javaagent:probe-agent.jar \
    -cp out/classes Probe
~~~

Trên môi trường HotSpot Linux đã thử, VM dừng rất sớm với thông điệp tương tự:

~~~text
Error occurred during initialization of VM
Could not find agent library instrument on the library path
Module java.instrument may be missing from runtime image.
~~~

Thông điệp **được rút gọn để nêu ý chính**; phiên bản HotSpot, OS và dynamic library loader có thể chèn tên **libinstrument.so** cùng mô tả khác. Không kỳ vọng chuỗi lỗi byte-for-byte giống nhau trên mọi hệ điều hành.

**Giải pháp đúng:** build lại runtime image với **java.instrument**. Không thể sửa thiếu module này bằng cách thêm **--add-opens**, **--add-exports** hay **--add-modules java.instrument** vào image vốn đã thiếu module đó. Các tùy chọn access/resolution không tự thêm binary của module bị loại khỏi image.

### 7.1. Ngược lại: image thiếu jdk.attach ở client

Nếu **AttachClient.class** được compile trên JDK đầy đủ nhưng chạy bằng runtime không có **jdk.attach**, việc load/link API **com.sun.tools.attach.VirtualMachine** có thể thất bại bằng **NoClassDefFoundError** hoặc lỗi module resolution tương ứng. Vì vậy hãy chạy test AttachClient **bằng rt-client/bin/java**, không phải java của JDK build.

Có **jdk.attach** ở client cũng chưa đảm bảo attach provider hoạt động với target bất kỳ: còn PID, OS permissions, VM implementation và attach mechanism.

## 8. Phân biệt module có mặt, module resolved và quyền JPMS

Một class ở **named module** có thể vẫn không gọi được helper của agent dù runtime image có đầy đủ modules. Ba khía cạnh tách biệt:

- **Presence**: module đã được jlink đưa vào image.
- **Resolution/readability**: module nằm trong module graph, module caller đọc được module callee.
- **Access**: package của callee được **exports** cho ordinary public access hoặc **opens** cho deep reflection khi cần.

Nếu agent inject bytecode vào class trong named module **com.example.app**, làm class ấy gọi helper ở module **com.example.trace**, phía app có thể cần **read edge tới com.example.trace** và phía trace cần exports package helper. Nếu framework deep-reflect private fields của app, module app phải **opens package đó tới module đang phản chiếu**. Đó là vấn đề **Instrumentation.redefineModule / --add-reads / --add-exports / --add-opens**, **khác** với việc thiếu **java.instrument/jdk.attach** trong runtime image.

~~~text
Có java.instrument          -> có cơ chế Agent API
Có jdk.attach ở client      -> có Attach API client
Có com.example.trace        -> module helper có sẵn
App reads Trace             -> caller có read edge
Trace exports p to App      -> public API access phù hợp
App opens q to Reflector    -> deep reflection nếu thực sự cần
~~~

**Đừng dùng --add-opens=ALL-UNNAMED theo thói quen** nếu sự cố thật là thiếu Java module trong image hoặc class helper chưa được đóng gói. Mở module rộng không sinh ra thư viện hoặc method bị thiếu, và có thể làm tăng phạm vi truy cập phản chiếu.

## 9. Manifest/capabilities cũng là một phần của deployment contract

Một agent JAR có thể có:

~~~text
Manifest-Version: 1.0
Premain-Class: com.example.agent.StartupAgent
Agent-Class: com.example.agent.DynamicAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true
~~~

Đây là **manifest mẫu có nhiều capability** cho một agent thực sự cần chúng, **không phải manifest demo**. Các thuộc tính capability có tính tùy chọn và chỉ nên xin nếu cần.

| Manifest attribute | Dùng khi nào? |
| --- | --- |
| **Premain-Class** | Agent được bật bằng **-javaagent** lúc startup |
| **Agent-Class** | Agent được load sau startup qua **Attach API/loadAgent** |
| **Can-Retransform-Classes** | Agent cần retransform các class đã load nếu JVM cho phép |
| **Can-Redefine-Classes** | Agent cần redefine class definitions |
| **Can-Set-Native-Method-Prefix** | Agent cần native method prefix để bọc native |

Sự hiện diện của **java.instrument** không tự cấp các capability tùy chọn. Kiểm tra runtime bằng **Instrumentation** trong premain/agentmain:

~~~java
// Pseudocode bên trong callback agent.
boolean canRetransform =
        inst.isRetransformClassesSupported();
boolean canRedefine =
        inst.isRedefineClassesSupported();
boolean canPrefix =
        inst.isNativeMethodPrefixSupported();
~~~

Khi thiếu capability, một số thao tác có thể ném **UnsupportedOperationException** hoặc thất bại theo API. Không chỉ sửa jlink image nếu vấn đề do manifest thiếu đúng attribute.

### 9.1. Agent JAR, libraries và native binaries ngoài JDK

Custom runtime image thường chứa **JDK modules + native libraries JDK liên quan**, không tự đóng gói agent JAR của bạn, ASM/Byte Buddy dependencies, application classes hoặc native libraries riêng của agent nếu chúng không nằm trong các artifacts bạn ship.

Chọn cách đóng gói phù hợp:

- Ship **agent.jar** bên cạnh app JAR và cấu hình đường dẫn **-javaagent** hợp lệ.
- Nếu agent phụ thuộc thư viện ngoài, package dependencies đúng cách (shaded/fat agent JAR hoặc classpath được JVM nhìn thấy), tránh version collision.
- Nếu agent dùng JNI/JVMTI native library riêng, ship đúng binary cho OS/architecture và native library search path.
- Nếu agent tải cấu hình/cert/keystore từ file, bảo đảm file và permissions có trong runtime container.
- Kiểm tra **system class loader**, named/unnamed module và visibility của helper khi bytecode được inject.

jlink không tự bảo đảm các artifacts ngoài JDK được đưa vào final distribution. Nếu dùng **jpackage**, hãy kiểm tra lại **runtime-image thực trong package cuối**, không chỉ thư mục image trung gian.

## 10. Attach: các nguyên nhân thất bại ngoài module

**VirtualMachine.attach(pid)** cần môi trường được provider hỗ trợ, không phải một RPC client phổ quát. Một target có jdk.attach vẫn có thể không nhận attach.

| Tình huống | Dấu hiệu thường gặp | Hướng xác minh |
| --- | --- | --- |
| Client runtime thiếu **jdk.attach** | Class/link module lỗi trước khi attach | Client --list-modules, ModuleFinder |
| Target runtime thiếu **java.instrument** | Startup agent lỗi; dynamic Java agent load có thể lỗi | Target --list-modules và smoke -javaagent |
| **-XX:+DisableAttachMechanism** | Attach không hoạt động | Command line JVM đích |
| User/permissions không phù hợp | AttachNotSupportedException/IOException | OS uid, ACL, security policy |
| PID namespace khác | Client không tìm thấy đúng PID | Container PID mapping / namespace |
| Target JVM đã thoát | Không attach được | Process lifecycle |
| Provider/JVM khác hoặc unsupported | Không có compatible AttachProvider | Vendor, JDK version, module jdk.attach |
| Agent jar không nằm trên target filesystem | AgentLoadException hoặc I/O error | Absolute target-readable JAR path |
| Manifest chỉ có Premain-Class | loadAgent không tìm Agent-Class | Manifest JAR |
| agentmain ném exception | AgentInitializationException | Target logs/exception |
| Self attach bị giới hạn | “Can not attach to current VM” hoặc tương đương | Chạy client khác process, kiểm tra JVM self-attach policy |
| Dynamic agent loading bị giới hạn ở JDK/version | Warnings hoặc loadAgent từ chối | JEP/JDK release notes, flags, vendor |
| Module helper/permission thiếu | Agent start nhưng invoke lỗi | Module read/export/open và class loader |

Trên HotSpot Java 17, **-XX:+DisableAttachMechanism** tắt cơ chế cho các tools attach. Không đưa **-Djdk.attach.allowAttachSelf=true** hay các flags nới attach vào production một cách tự động; tự attach có security/operational implications riêng.

### 10.1. Thay đổi chính sách ở những JDK sau Java 17

Một số JDK mới hơn phát cảnh báo khi **Java agent được nạp động**, theo định hướng tăng kiểm soát integrity của JVM (ví dụ **JEP 451** trên JDK 21). Do đó một ví dụ chạy được trên HotSpot Java 17 có thể in thêm cảnh báo trên JDK 21, và cơ chế default/flags có thể thay đổi ở bản JDK kế tiếp.

Đừng dùng “không thấy warning” hoặc “module vẫn tồn tại” như kết luận về khả năng attach. Đọc release notes của đúng **vendor + JDK build đang deploy**, kiểm tra flags như **-XX:+EnableDynamicAgentLoading** nếu JDK/vấn đề cụ thể yêu cầu và được chính sách vận hành cho phép; **startup -javaagent** và **dynamic agent loading** có chính sách khác nhau.

## 11. Module mở rộng khi agent dùng quản trị và quan sát

Không phải mọi instrument agent chỉ cần java.instrument. Nếu agent đo class loading rồi xuất metrics, trace hoặc JFR/JMX, nó có thể dùng thêm modules:

### 11.1. Logging

Một agent sử dụng **java.util.logging.Logger** cần module **java.logging**. Nếu chỉ dùng **System.out.println**, module java.base đủ cho output demo. Tuy nhiên logging production có thể cần file handlers, config hoặc thư viện ngoài, nên phải test output path/quyền ghi.

### 11.2. JMX và management

Code gọi **java.lang.management.ManagementFactory** cần **java.management**. Nếu dùng các extension của HotSpot như **com.sun.management.HotSpotDiagnosticMXBean**, có thể cần **jdk.management**. Remote JMX agent có requirements riêng về **jdk.management.agent**, RMI modules, network security và authentication. Đừng chỉ thêm **jdk.attach** vì thấy từ “management”.

### 11.3. Java Flight Recorder

Khi app/agent thực sự import **jdk.jfr.Recording** hoặc các API JFR, cần kiểm tra **jdk.jfr**. Không phải mọi profiler dùng sampling/JFR giống nhau. Với runtime image rút gọn, module hoặc provider thiếu có thể gây lỗi dù **ClassFileTransformer** vẫn hoạt động.

### 11.4. Diagnostics và tools

Các công cụ như **jcmd**, **jmap** hoặc JDWP phụ thuộc những modules/tools và JVM support khác nhau. Đừng mong **rt-target/bin/jcmd** tự tồn tại chỉ vì image có jdk.attach; **jdk.jcmd** là yêu cầu khác, và jlink có các tùy chọn loại native commands. Có thể chọn vận hành tool ngoài target container bằng một JDK đầy đủ phù hợp, nếu chính sách môi trường cho phép.

### 11.5. Providers/crypto/locale

Một agent đẩy telemetry qua TLS, resolve DNS, xử lý XML/JSON theo thư viện hoặc dùng non-default charsets có thể cần providers/locale modules mà code chính không dùng trực tiếp. **jdeps** không bảo đảm nhìn thấy mọi provider được ServiceLoader tải động. Hãy rà soát agent dependencies và test kịch bản thật trước khi quyết định dùng **--bind-services** hoặc đưa thêm các modules.

## 12. Quy trình CI/CD nên thực hiện

~~~text
1. Phân tích ứng dụng (jdeps, module-info.java)
2. Phân tích agent JAR + attach client + plugins
3. Tổng hợp các root modules tĩnh và động
4. Tạo image với jlink từ JDK build được pin version/vendor
5. Chạy chính image/bin/java, không dùng java của host
6. Kiểm tra --list-modules / ModuleFinder / ModuleLayer
7. Test startup -javaagent và đúng premain
8. Nếu cần attach: test client (jdk.attach) -> target (java.instrument)
9. Test retransform/redefine/JMX/JFR nếu sản phẩm dùng
10. Đóng gói image + app + agent jar + configs/native libs
11. Smoke-test bản phân phối cuối dưới OS/container thực
12. Chỉ promote artifact sau khi đủ bằng chứng
~~~

Có thể viết **check script** (shell POSIX):

~~~bash
set -eu

./rt-target/bin/java --list-modules \
  | grep '^java.instrument@'

./rt-client/bin/java --list-modules \
  | grep '^jdk.attach@'

./rt-target/bin/java -javaagent:probe-agent.jar \
  -cp out/classes Probe
~~~

Đây là script minh họa, trong đó **grep module@version** phù hợp JDK modules có version trong image; một số vendor/cấu hình có thể biểu diễn khác, nên CI sản xuất có thể dùng **ModuleFinder** hoặc parse tên module trước dấu @ cho chắc chắn. Script này chỉ kiểm tra presence và startup, **không thay** attach integration test.

**Không tự động “sửa lỗi” bằng việc thêm tất cả JDK modules** vào image rồi bỏ qua smoke tests. Làm vậy làm mất mục tiêu giảm surface/size, và vẫn không khắc phục lỗi manifest/permissions/provider.

## 13. Failure-analysis theo từng bước

### 13.1. -javaagent không chạy ở custom runtime

Thứ tự kiểm tra:

1. Xác nhận lệnh thực sự gọi **<image>/bin/java**, không gọi java từ PATH.
2. **--list-modules** trong image có **java.instrument**?
3. Agent JAR tồn tại ở đường dẫn startup của **process đích**?
4. Manifest có **Premain-Class** đúng binary name?
5. premain signature là **public static void premain(String, Instrumentation)** hoặc overload hỗ trợ?
6. Agent class và dependencies có thể load bằng system class loader?
7. premain có ném exception? Transformer có gây lỗi khi define class?
8. JVM vendor/architecture có đủ native support của instrumentation?

### 13.2. Attach client thiếu API

1. Confirm client đang chạy bằng **rt-client/bin/java**.
2. **ModuleFinder.ofSystem()** của client có **jdk.attach**?
3. Nếu module có nhưng chưa resolved, kiểm tra named module **requires jdk.attach** hoặc launcher **--add-modules jdk.attach**.
4. Kiểm tra **AttachProvider.providers()** nếu cần, cùng JVM implementation.
5. Đừng nhầm lỗi Java module/linkage ở client với lỗi target PID/permission.

### 13.3. Client attach được nhưng loadAgent lỗi

1. Phân biệt **VirtualMachine.attach** thành công với **vm.loadAgent** thành công.
2. Target có **java.instrument** và JVM cho phép dynamic agent loading?
3. Agent JAR có **Agent-Class** và **agentmain** đúng?
4. Target đọc được absolute path của JAR không?
5. Native/JVM platform policy, security flags và module/class loader availability có đủ?
6. Agentmain có ném exception hoặc không tìm được helper/library?
7. Chỉ báo **AGENTMAIN_OK** hoặc hiệu ứng instrumentation thật khi target xác nhận chạy được; một **ATTACH_OK** do client in sau loadAgent chưa tự chứng minh business behavior.

### 13.4. Agent load được nhưng instrument không hiệu lực

Module presence đã đủ nhưng có thể:

- Class cần transform đã load trước startup/attach.
- Transformer lọc sai internal class name/module/classloader.
- **Can-Retransform-Classes** không được cấp mặc dù agent cần sửa class đã load.
- Bytecode output không hợp lệ, JVM không nhận, hoặc return null.
- Module helper không được package/export/open/đọc đúng.
- Code mới chạy ở active frame cũ/khác classloader.
- Native or networking dependency của agent thiếu trong final distribution.

Đây là vấn đề **runtime behavior/bytecode**, không tự sửa bằng jlink nếu modules đã đúng.

## 14. Ma trận kiểm thử tối thiểu

| Kịch bản | Image / cấu hình | Kỳ vọng |
| --- | --- | --- |
| Runtime target có java.instrument | rt-target | HAS_INSTRUMENT=true |
| Runtime target không jdk.attach | rt-target | Startup -javaagent vẫn PREMAIN_OK |
| Runtime client có jdk.attach | rt-client | HAS_ATTACH=true |
| Runtime client không java.instrument | rt-client | Attach API vẫn làm việc như client |
| Runtime full | rt-full | Cả hai modules có mặt |
| Image chỉ java.base | rt-minimal + -javaagent | JVM không khởi động agent, báo instrumentation thiếu |
| Agent JAR thiếu Premain-Class | Target startup | Agent startup thất bại |
| Agent JAR thiếu Agent-Class | Target dynamic loading | loadAgent thất bại |
| Target không hỗ trợ attach | DisableAttachMechanism | Attach không thành công |
| Target trong PID namespace khác | Cross-container | Không tự giả định pid tương ứng |
| Target thiếu đường dẫn JAR | Agent path chỉ trên client filesystem | loadAgent không thành công |
| Self-attach | Client cùng PID với target | Phụ thuộc JVM policy, không mặc định |
| Agent dùng ManagementFactory | Image thiếu java.management | Code management có thể không link/load |
| Agent dùng JFR | Image thiếu jdk.jfr | JFR APIs không khả dụng |
| Class helper thuộc named module khác | Modules có mặt nhưng thiếu reads/exports | Linkage/access lỗi |
| Chỉ jdeps application JAR | Không phân tích agent | Có nguy cơ thiếu java.instrument |
| Đổi agent/JDK build | Image chưa rebuild | Module graph hoặc behavior có thể thay đổi |
| Kiểm thử trên host JDK thay vì image | Chạy nhầm java binary | Kết quả sai so với production |

## 15. Checklist trước khi phát hành custom runtime

- Tôi biết sản phẩm là **startup agent**, **dynamic attach target**, **attach client**, hay kết hợp.
- Tôi phân biệt **java.instrument của target** với **jdk.attach của client**.
- Tôi đã chạy **jdeps** cho application, agent và attach tooling khi thích hợp.
- Các phụ thuộc động từ reflection, ServiceLoader, JNI, plugin và telemetry đã được rà soát.
- **jlink --add-modules** chứa các root modules cần thiết và dependencies được giải quyết.
- Tôi kiểm tra **<image>/bin/java --list-modules** ngay trên image được phân phối.
- Tôi xác nhận **ModuleFinder.ofSystem** và khi cần **ModuleLayer.boot** trong process thật.
- JAR agent có **Premain-Class** và/hoặc **Agent-Class**, callback đúng.
- Capability retransform/redefine/native prefix được khai báo/kiểm tra nếu agent cần.
- **-javaagent** được test trên target image, không chỉ bằng JDK build.
- Nếu dùng attach, **VirtualMachine.attach + loadAgent + agentmain** được kiểm thử end-to-end.
- Target PID, permissions, namespace, dynamic agent policy và đường dẫn JAR được xác minh.
- Agent helper class, package/modules, native libraries và config files đều có trong distribution.
- Các module như **java.management, jdk.management, jdk.jfr, java.logging, jdk.unsupported** chỉ được thêm khi thực sự có nhu cầu.
- Pipeline dùng version/vendor JDK rõ ràng, tạo image mới khi đổi dependency và test final **jpackage/container** artifact.
- Tôi không coi **module present** là bằng chứng instrumentation effect; cần test method/event/metric thật.

## 16. Tài liệu chuẩn Java 17 và ghi chú tương thích

- [Java SE 17 — Module java.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/module-summary.html): module cung cấp Java instrumentation service.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): -javaagent, Premain-Class, Agent-Class, premain/agentmain và class loading.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer, retransform/redefine capability và module instrumentation.
- [Java SE 17 — jdk.attach](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/module-summary.html): client Attach API.
- [Java SE 17 — VirtualMachine](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): attach, loadAgent, detach và failure types.
- [JDK 17 — jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): --add-modules, --module-path, --output, service binding và custom runtime image.
- [JDK 17 — jdeps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): --print-module-deps và giới hạn phân tích static dependencies.
- [JDK 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): --list-modules, --describe-module, --add-modules và -XX:+DisableAttachMechanism.
- [JDK 17 — jpackage](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): đóng gói app image/custom runtime.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): thay đổi cảnh báo/chính sách động đối với agent loading ở những JDK sau 17.

**Kết luận:** Chọn module theo **vai trò của process**, không chỉ theo tên công nghệ. **java.instrument thuộc phía JVM chạy/nhận Java agent; jdk.attach thuộc phía tool gọi Attach API**. Dùng **jdeps + kiểm tra phụ thuộc động** để quyết định jlink roots, kiểm tra **đúng image/bin/java**, rồi chứng minh end-to-end bằng **premain** hoặc **VirtualMachine.attach → loadAgent → agentmain**. Một module có mặt không thể thay thế manifest hợp lệ, VM/OS permissions, class loader visibility và kiểm thử hành vi thật.
