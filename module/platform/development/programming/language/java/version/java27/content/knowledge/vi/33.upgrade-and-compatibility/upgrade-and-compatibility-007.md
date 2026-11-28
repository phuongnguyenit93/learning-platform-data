# Kiểm tra thư viện đọc bytecode, agent và công cụ instrumentation

Khi nâng cấp một ứng dụng lên **Java 27**, không chỉ mã nguồn Java và JVM phải tương thích. Nhiều thư viện còn **đọc, sinh, kiểm tra hoặc sửa bytecode** khi build, chạy unit test, tạo proxy, mock đối tượng, đo coverage hoặc thu thập telemetry. Một parser đã cũ có thể từ chối file **.class** mà JVM Java 27 nạp được bình thường. Ngược lại, một agent có thể đọc được class file nhưng tạo bytecode không hợp lệ, xung đột với agent khác hoặc gặp giới hạn module.

Chủ đề này thuộc chương **Nâng cấp và tương thích Java 27** của mô-đun **Java 27 và các kiến thức liên quan**. Bài học tập trung vào những API và cơ chế **vẫn còn áp dụng trong Java 27**, không dựa vào workaround của các phiên bản Java cũ.

Sau bài học, bạn có thể xác định class file version, kiểm tra công cụ **ASM, Byte Buddy, JaCoCo, PIT, Mockito**, nhận diện **shaded dependencies**, hiểu Java agents **premain/agentmain**, phân biệt **transform/retransform/redefine**, sử dụng **Class-File API** chính thức, và xây dựng một ma trận kiểm thử upgrade có thể lặp lại.

## 1. Vì sao upgrade JDK lại làm công cụ instrumentation lỗi?

Một file **.class** được biên dịch có định dạng nhị phân do **Java Virtual Machine Specification (JVMS)** quy định. Bytecode parser cần hiểu:

- Class file major/minor version và constant pool.
- Access flags, fields, methods, attributes.
- Stack map frames và quy tắc verification.
- Các cấu trúc mới mà compiler có thể tạo ra.
- Thuộc tính do compiler/framework sinh ra hoặc giữ lại.

Với **Java SE 27**, major version của class file thông thường là **71**. Một thư viện chỉ nhận tới Java 21 (major 65) có thể báo lỗi khi đọc file mới, cho dù JVM Java 27 chạy file đó bình thường.

~~~mermaid
flowchart TD
    A["javac 27 tạo class file"]
    B["major version 71"]
    C{"Thành phần đọc bytecode"}
    D["JVM Java 27"]
    E["ASM / Byte Buddy / build plugin"]
    F["JaCoCo / Mockito / APM agent"]
    G{"Có hỗ trợ định dạng và quy tắc JVM 27?"}
    H["Đọc và xử lý thành công"]
    I["Lỗi version, format, frames hoặc transform"]
    A --> B --> C
    C --> D --> G
    C --> E --> G
    C --> F --> G
    G -->|Có| H
    G -->|Không| I
~~~

Một lỗi upgrade có thể xuất hiện **trước khi main() chạy**, trong **compile/test**, hoặc chỉ khi framework tạo class động ở runtime. Do đó phải kiểm tra từng giai đoạn.

## 2. Năm lớp tương thích khác nhau

| Lớp | Cần xác minh | Dấu hiệu không tương thích |
|---|---|---|
| **JVM/runtime** | Java runtime có thể nạp class file và module? | UnsupportedClassVersionError |
| **Compiler/build** | javac, Gradle/Maven, compiler plugin hỗ trợ JDK/target? | Compile/build error |
| **Bytecode reader/writer** | ASM, Byte Buddy, enhancer hiểu class file 71? | Unsupported class file major version 71 |
| **Agent/instrumentation** | Agent cài đặt và biến đổi bytecode hợp lệ? | ClassFormatError, VerifyError, agent startup fail |
| **Access/integrity** | JPMS, quyền attach, module access có cho phép? | InaccessibleObjectException, attach warning |

**Tương thích binary không đồng nghĩa đúng chức năng.** Một agent có thể chạy mà không xuất spans, một coverage agent có thể tạo report rỗng, hoặc một mocking engine chỉ lỗi ở final classes.

Hãy phân biệt kết quả **khởi động thành công** với **tính năng instrumentation thực sự hoạt động**.

## 3. Class file version của Java 27

Header của file **.class** bắt đầu bằng magic bytes **0xCAFEBABE**, tiếp theo là hai số **minor_version** và **major_version**.

| Release | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |
| **Java 27** | **71** |

Ví dụ **Greeting.java**:

~~~java
public final class Greeting {
    public static String message() {
        return "Hello Java 27";
    }
}
~~~

Biên dịch với JDK 27:

~~~bash
javac --release 27 Greeting.java
~~~

Kiểm tra:

~~~bash
javap -verbose Greeting.class
~~~

Các dòng mong đợi:

~~~text
minor version: 0
major version: 71
~~~

### 3.1. Runtime version khác target version

Lệnh:

~~~bash
javac --release 21 Greeting.java
~~~

sử dụng ngôn ngữ, API và binary target của Java 21, nên thường tạo class file major **65**. Nhưng **build daemon**, **compiler plugin** và **test process** vẫn có thể đang chạy trên JDK 27 hoặc một JDK khác.

Không lấy kết quả **java -version** trong terminal làm bằng chứng duy nhất rằng mọi process trong pipeline đều chạy cùng JDK.

### 3.2. Minor version và preview

Trên Java 27, class file thông thường có minor **0**. Class file **71.65535** biểu thị phụ thuộc preview feature của chính Java 27 và yêu cầu runtime cho phép preview.

Class preview của release khác không phải binary có thể nạp tùy tiện trên Java 27. Theo yêu cầu phạm vi bài này, **không sử dụng preview** để vượt qua lỗi tương thích.

### 3.3. Vì sao không sửa thủ công major version?

Đổi hai byte header từ **71** sang **65** không thay đổi những instruction, attributes hoặc ngữ nghĩa Java 27 mà bytecode có thể sử dụng. File sau khi sửa có thể bị từ chối khi verify hoặc chạy sai.

Phải nâng **parser/transformer** hoặc biên dịch bằng **--release** thích hợp, không giả mạo class file header.

## 4. API chuẩn java.lang.classfile trong Java 27

Từ **Java 24**, **Class-File API** chính thức có mặt trong **java.lang.classfile** (module **java.base**). Nó hỗ trợ đọc, xây dựng, biến đổi và kiểm tra class file mà không phải dựa vào các package nội bộ của JDK.

| API | Chức năng |
|---|---|
| **ClassFile.of()** | Tạo context đọc/sinh/transform class file |
| **ClassFile.parse(Path)** | Phân tích file thành ClassModel |
| **ClassModel.majorVersion()** | Đọc major version |
| **ClassModel.minorVersion()** | Đọc minor version |
| **ClassModel.thisClass()** | Metadata của lớp trong constant pool |
| **ClassModel.fields()/methods()** | Danh sách field/method |
| **ClassFile.verify(...)** | Kiểm tra và trả về các VerifyError |
| **ClassFile.transformClass(...)** | Tạo class bytes mới bằng ClassTransform |

### 4.1. Ví dụ đọc file .class độc lập

Tạo tệp **ClassFileInspector.java**:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Path;

public final class ClassFileInspector {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                "Usage: java ClassFileInspector <class-file>"
            );
            return;
        }

        Path path = Path.of(args[0]);

        ClassFile classFile = ClassFile.of();
        ClassModel model = classFile.parse(path);

        System.out.println(
            "Name: " + model.thisClass().asInternalName()
        );
        System.out.println("Major: " + model.majorVersion());
        System.out.println("Minor: " + model.minorVersion());
        System.out.println("Fields: " + model.fields().size());
        System.out.println("Methods: " + model.methods().size());

        var errors = classFile.verify(model);

        System.out.println(
            "Verification issues: " + errors.size()
        );

        for (var error : errors) {
            System.out.println(error);
        }
    }
}
~~~

Chạy bằng JDK 27:

~~~bash
javac ClassFileInspector.java
java ClassFileInspector Greeting.class
~~~

Đối với Greeting.class được biên dịch bằng **--release 27**, major mong đợi là **71**.

**ClassFile.parse** có thể đọc dữ liệu theo nhu cầu: một file malformed có thể tạo lỗi trong quá trình truy cập sâu vào model. **ClassFile.verify** là kiểm tra cấu trúc class file, không chứng minh các dependencies tồn tại, class loading thành công hay logic nghiệp vụ đúng.

### 4.2. Class-File API có thay ASM hoàn toàn không?

Không nhất thiết. Class-File API là lựa chọn tốt cho công cụ mới **chỉ chạy trên JDK 24+**. Nhưng nếu library cần hỗ trợ **Java 17/21**, nó không thể gọi trực tiếp API này trên runtime không có package tương ứng.

Các framework có nhiều target JDK vẫn có thể cần ASM/Byte Buddy hoặc cơ chế đa phiên bản. Chọn công cụ theo **JDK tối thiểu, chức năng biến đổi, khả năng bảo trì và ma trận hỗ trợ**.

## 5. Nhận diện các công cụ phụ thuộc bytecode

| Nhóm công cụ | Ví dụ | Vì sao cần kiểm tra? |
|---|---|---|
| Bytecode parser/writer | **ASM** | Parse/sinh class, stack map frames |
| Runtime code generation | **Byte Buddy** | Proxy, advice, agent, dynamic classes |
| Coverage | **JaCoCo** | Instrument class để đo test coverage |
| Mocking | **Mockito** và backend | Inline mock, final class/record |
| Mutation testing | **PIT** | Thay đổi bytecode và chạy test |
| ORM/DI/framework | Proxy/enhancer/weaver | Sinh hoặc sửa classes ở runtime |
| APM/tracing | Java agent của nhà cung cấp | Instrument HTTP, DB, framework |
| Static analysis | Bytecode scanner | Đọc constant pool và class metadata |
| Build-time enhancer | Maven/Gradle plugin | Sửa class trước khi đóng gói |
| Security scanner | Class analyzer | Xử lý mọi class trong dependencies |

Có thể lỗi chỉ xuất hiện trên một đường đi ít gặp, ví dụ chỉ khi mock final record, ORM lazy-load một entity hoặc APM instrument JDBC driver.

## 6. Kiểm tra các phiên bản bytecode libraries

Tại thời điểm xây dựng tài liệu Java 27 (cuối năm 2026), các tài liệu phát hành cho biết:

- **ASM 9.11.1** đã phát hành tháng **10/2026**.
- **JaCoCo 0.8.16** (10/2026) công bố **hỗ trợ chính thức Java 27** và dựa vào **ASM 9.11.1**.
- **Byte Buddy 1.18.x** có các bản cập nhật năm 2026, với **1.18.16** cập nhật ASM 9.11.1; release notes tháng 11/2026 ghi nhận **1.18.17**.

**Các mốc version không phải giấy đảm bảo cho mọi framework.** Thư viện có thể đóng gói ASM cũ, dùng classloading đặc biệt hoặc bị hạn chế bởi module.

Hãy ghi phiên bản **thực sự được resolved**, không chỉ phiên bản mà bạn muốn trong file cấu hình.

### 6.1. Ví dụ dependency không hiển nhiên

~~~text
application
 +-- framework A
 |    +-- embedded bytecode parser cũ
 +-- mocking runtime
 |    +-- Byte Buddy
 +-- testing
 |    +-- JaCoCo
 +-- APM agent (JAR độc lập)
      +-- ASM được shaded/relocated
~~~

Nâng ASM ở project root **không tự nâng** ASM được nhúng trong một agent độc lập.

### 6.2. Kiểm tra bản tương thích có ba bước

1. **Đọc compatibility/release notes** chính thức của thành phần.
2. **Xác nhận artifact/phiên bản được load** trong build/test/runtime.
3. **Chạy canary** đọc, transform, mock và instrument class file version 71 thật.

Thiếu bước thứ ba, một phiên bản được công bố tương thích vẫn có thể xung đột với tổ hợp công nghệ của bạn.

## 7. Kiểm tra dependencies trong Maven

Xem dependency tree:

~~~bash
mvn dependency:tree
~~~

Lọc những thành phần liên quan:

~~~bash
mvn dependency:tree -Dincludes=org.ow2.asm:*,net.bytebuddy:*
~~~

Tùy shell, cách truyền dấu * và dấu : có thể cần quoting. Cần phân biệt:

- **Project dependencies** chạy trong ứng dụng.
- **Test dependencies** chạy trong forked test JVM.
- **Maven plugin dependencies** có classloader khác và không nhất thiết hiển thị cùng dependency tree.

Khi lỗi xảy ra trong plugin lúc build, hãy kiểm tra **phiên bản chính plugin đó** và dependencies mà nó đóng gói, không chỉ runtime libraries.

## 8. Kiểm tra dependencies trong Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Với test:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Xem lý do chọn Byte Buddy version:

~~~bash
./gradlew dependencyInsight --dependency byte-buddy --configuration testRuntimeClasspath
~~~

Trong Windows PowerShell, dùng **gradlew.bat** và có thể đặt tham số trên một dòng.

**Gradle daemon Java**, **compiler toolchain Java** và **test JVM Java** không phải luôn là một. Cần ghi cả ba khi tái hiện lỗi.

Bản Gradle/plugin dùng để chạy daemon cũng phải hỗ trợ JDK 27; việc compiler toolchain nhận 27 không chứng minh build plugin đang dùng ASM tương thích.

## 9. Shading và relocated libraries

Một Java agent có thể mang:

~~~text
agent-vendor.jar
  vendor/internal/bytecode/ClassReader.class
  vendor/internal/bytecode/ClassWriter.class
~~~

Đây có thể là ASM đã được relocate. Dependency tree thông thường sẽ không cho biết artifact ASM gốc.

Kiểm tra nội dung JAR:

~~~bash
jar --list --file agent-vendor.jar
~~~

Kết hợp:

- Manifest.
- SBOM (nếu có).
- Release notes.
- Thông tin dependency từ vendor.
- Stack trace hoặc nguồn mã của plugin.
- Kiểm thử class file 71 thực tế.

**Không suy đoán phiên bản chỉ từ tên package.** Một bản shaded có thể đổi tên lớp hoặc sửa mã nguồn nội bộ.

### 9.1. Force version không sửa được shaded JAR

Thêm dependency ASM 9.11.1 mới vào project thường **không thay thế** những bytes ASM đã được đóng gói sẵn trong agent JAR.

Phải nâng **đúng vendor agent/plugin** hoặc thay bằng giải pháp được hỗ trợ.

## 10. Java agent và Instrumentation API

Java có module **java.instrument**, cung cấp:

- **Instrumentation**: đăng ký transformers, kiểm tra capabilities, hỗ trợ retransform/redefine theo giới hạn.
- **ClassFileTransformer**: callback xử lý bytes của class trước khi class được định nghĩa hoặc khi class được biến đổi lại.
- **ClassDefinition**: dữ liệu class bytes cho redefine.
- **UnmodifiableClassException** và **IllegalClassFormatException**: những tình huống lỗi cụ thể.

~~~mermaid
flowchart TD
    A["java -javaagent:agent.jar"]
    B["JVM đọc Premain-Class"]
    C["Gọi premain(String, Instrumentation)"]
    D["Agent đăng ký transformer"]
    E["Class của ứng dụng được load"]
    F["JVM gọi transform"]
    G{"Transformer có sửa bytes?"}
    H["return null: giữ nguyên"]
    I["return byte[] mới: áp dụng transform"]
    J["JVM verify và define class"]
    A --> B --> C --> D --> E --> F --> G
    G -->|Không| H --> J
    G -->|Có| I --> J
~~~

### 10.1. Startup agent và dynamic agent khác nhau

| Cơ chế | Thời điểm | Entry point/manifest |
|---|---|---|
| **-javaagent** | Khi JVM khởi động | **Premain-Class** và **premain** |
| **Dynamic agent loading** | JVM đã chạy | **Agent-Class** và **agentmain** |
| **Launcher-Agent-Class** | Agent đóng trong executable JAR theo launcher được hỗ trợ | **agentmain** trước application main |

Một agent có thể triển khai cả premain và agentmain, nhưng cách khởi tạo và quyền nạp vẫn phải được kiểm tra riêng.

## 11. Ví dụ agent chỉ quan sát class loading

Đây là ví dụ đơn giản nhất để kiểm tra một agent startup có thể cài đặt transformer. Nó **không sửa bytecode**, vì mục tiêu là phân lập các vấn đề đóng gói và classloading.

Tạo **demo/agent/LoggingAgent.java**:

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class LoggingAgent {

    public static void premain(
            String options,
            Instrumentation instrumentation
    ) {
        System.out.println("[agent] installed");

        instrumentation.addTransformer(
            new ClassFileTransformer() {
                @Override
                public byte[] transform(
                        Module module,
                        ClassLoader loader,
                        String className,
                        Class<?> classBeingRedefined,
                        ProtectionDomain domain,
                        byte[] bytes
                ) {
                    if ("demo/app/Main".equals(className)) {
                        System.out.println(
                            "[agent] observed demo/app/Main"
                        );
                    }

                    return null;
                }
            }
        );
    }
}
~~~

Tạo **demo/app/Main.java**:

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("[app] hello Java 27");
    }
}
~~~

### 11.1. Đóng gói JAR

Biên dịch trong một thư mục lab:

~~~bash
javac -d out demo/agent/LoggingAgent.java demo/app/Main.java
~~~

Tạo file văn bản **agent.mf**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.LoggingAgent

~~~

Có một dòng trống cuối file manifest. Sau đó:

~~~bash
jar --create --file logging-agent.jar --manifest agent.mf -C out demo/agent
java -javaagent:logging-agent.jar -cp out demo.app.Main
~~~

Kết quả minh họa:

~~~text
[agent] installed
[agent] observed demo/app/Main
[app] hello Java 27
~~~

Đây là output dự kiến của ví dụ, không phải kết quả chạy thực tế khi biên soạn bài.

### 11.2. Bài test này xác minh điều gì?

- JVM thấy **Premain-Class**.
- Agent được khởi động trước main của ứng dụng.
- Transformer quan sát class có **internal name** dùng dấu gạch chéo.
- Trả **null** không sửa bytecode.
- Lỗi manifest hoặc thiếu module có thể được tách khỏi lỗi parser/transformer phức tạp.

Nó **chưa chứng minh** agent hỗ trợ mọi class hoặc có khả năng inject mã đúng. Cần phép thử riêng khi dùng transformer thật.

## 12. Hợp đồng quan trọng của ClassFileTransformer

Một callback nhận module, classloader, class name, protection domain và bytes class. Khi **redefine/retransform**, nó còn có thông tin class đang được thay.

| Giá trị trả về | Ý nghĩa |
|---|---|
| **null** | Không biến đổi class |
| **byte[] mới và hợp lệ** | Thay class bytes theo hợp đồng |
| **Ném ngoại lệ** | JVM có thể tiếp tục xử lý các transformer khác; không nên coi đó là cơ chế abort tin cậy |

**Không sửa trực tiếp mảng classfileBuffer đầu vào.** Javadoc yêu cầu trả một mảng byte mới nếu thực sự sửa class.

Trong callback, tránh những thao tác nạp/resolve chính class đang được transform, vì có thể tạo **ClassCircularityError** hoặc **LinkageError** khó chẩn đoán.

### 12.1. Ví dụ filter transformer an toàn

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> redefined,
        java.security.ProtectionDomain domain,
        byte[] classBytes
) {
    if (!"demo/app/Main".equals(className)) {
        return null;
    }

    // Chỉ thực hiện transform khi scope đã được xác minh.
    // Trả null nếu không cần thay bytes.
    return null;
}
~~~

Đoạn trên là minh họa một method bên trong ClassFileTransformer, không phải một class độc lập.

## 13. Nhiều agent: thứ tự biến đổi cần được test

Một ứng dụng có thể khởi động:

~~~bash
java -javaagent:coverage-agent.jar -javaagent:apm-agent.jar -jar app.jar
~~~

Startup agent được gọi theo thứ tự xuất hiện trên launcher. Các transformers được áp dụng theo nhóm và thứ tự đăng ký. Khi một transformer trả bytes mới, transformer tiếp theo có thể nhận bytes đã biến đổi.

Các vấn đề thường gặp:

- JaCoCo và APM cùng sửa một method.
- Agent A sinh helper class, Agent B lại instrument helper ấy.
- Một tool giả định stack map frames không thay đổi.
- Agent chạy trong startup nhưng lỗi khi có retransformation.
- Agent mới xung đột với mocking backend của test.

Một vòng kiểm thử nên có:

1. **Không agent**.
2. **Chỉ coverage**.
3. **Chỉ APM/tracing**.
4. **Chỉ mocking/test instrumentation** theo use case.
5. **Tổ hợp giống production**.
6. **Hoán đổi thứ tự** chỉ để điều tra khi được phép, không mặc định thay thứ tự production.

## 14. Retransform và redefine có giới hạn

**Instrumentation.retransformClasses(...)** tái áp dụng quy trình transformation lên class đã nạp. **Instrumentation.redefineClasses(...)** nhận class definitions thay thế theo hợp đồng JVM.

Không thể tùy ý sử dụng chúng để thay toàn bộ cấu trúc lớp.

Ví dụ khả năng cần hỏi:

~~~java
static void checkCapabilities(
        java.lang.instrument.Instrumentation inst
) {
    System.out.println(
        inst.isRetransformClassesSupported()
    );

    System.out.println(
        inst.isRedefineClassesSupported()
    );
}
~~~

Manifest có thể khai báo:

~~~text
Premain-Class: demo.agent.LoggingAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

~~~

Đây chỉ là mẫu khi agent **cần và hỗ trợ** capabilities đó; không nên bật quyền không cần thiết.

### 14.1. Những thay đổi thường không được chấp nhận

Trong HotSpot thông thường, retransform/redefine không cho phép tự do:

- Thêm hoặc xóa fields.
- Thêm hoặc xóa methods, đổi method signatures.
- Thay superclass hoặc interfaces một cách không được hỗ trợ.
- Đổi các ràng buộc schema của class mà JVM không cho phép.

Thay body method trong phạm vi hợp lệ vẫn cần đúng verifier, stack map frames và class semantics.

### 14.2. Kiểm tra trước khi gọi

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    inst.retransformClasses(targetClass);
}
~~~

Các biến **inst** và **targetClass** là giá trị agent tự quản lý. Đoạn này cần xử lý ngoại lệ, lifecycle và quyền thích hợp trong chương trình thật.

**Không** thử retransform mọi class đã nạp trên production chỉ để xem tính năng có hoạt động hay không.

## 15. Dynamic attach và JEP 451

Từ JDK 21, **JEP 451** chuẩn bị cho việc hạn chế nạp agent động. JVM có thể phát **warning khi agent được nạp sau startup**; hướng đi của nền tảng là chủ ứng dụng phải chủ động cho phép khả năng sửa bytecode runtime.

Trong Java 27:

- **-javaagent** tại startup tiếp tục là cơ chế chuẩn.
- Dynamic agent loading còn được hỗ trợ ở môi trường cho phép, nhưng chịu cảnh báo/quyền theo cấu hình.
- Kế hoạch **vô hiệu hóa mặc định trong một release tương lai** không có nghĩa mọi Java 27 JVM hiện đã mặc định cấm.
- **-XX:+EnableDynamicAgentLoading** là lựa chọn bật rõ ràng quyền nạp động trên JVM hỗ trợ, nên chỉ dùng khi có yêu cầu và được quản trị.

Một phép thử compatibility hướng tương lai:

~~~bash
java -XX:-EnableDynamicAgentLoading -jar app.jar
~~~

Nếu framework tự attach agent để mock hoặc instrument và không có phương án khác, test sẽ bộc lộ dependency đó.

**Không** bật tự động self-attach hoặc bỏ cơ chế kiểm soát integrity làm giải pháp mặc định. Nếu có thể, hãy cấu hình agent từ startup hoặc nâng thư viện lên bản có tích hợp được hỗ trợ.

## 16. Class-File API so với ASM và Byte Buddy

| Tiêu chí | Class-File API | ASM | Byte Buddy |
|---|---|---|---|
| Nằm trong JDK | Có, từ Java 24 | Không | Không |
| Mức trừu tượng | Class model/build/transform | Bytecode visitor/tree | Codegen/agent/advice mức cao |
| Dùng trực tiếp trên Java 17/21 | Không | Tùy bản | Tùy bản |
| Phụ thuộc class file 71 | JDK 27 hỗ trợ | Cần ASM tương thích | Cần Byte Buddy và dependencies tương thích |
| Use case | Công cụ chỉ dành JDK mới | Parser/transform chi tiết | Mocking, proxy, runtime agent |

**Không phải mọi dự án nên thay ASM/Byte Buddy bằng Class-File API.** Chọn theo JDK tối thiểu phải hỗ trợ, tính ổn định API, nhu cầu framework và khả năng bảo trì.

## 17. Test toolchain: Mockito, JaCoCo và PIT

Java 27 có thể chạy unit tests thông thường nhưng một mock engine hoặc agent đo coverage thất bại riêng.

~~~text
JUnit Jupiter tests
  |
  +-- Mockito / mock maker
  |     |
  |     +-- Byte Buddy và instrumentation
  |
  +-- JaCoCo agent
  |     |
  |     +-- ASM và bytecode instrumentation
  |
  +-- PIT mutation testing
        |
        +-- Bytecode analysis và mutators
~~~

### 17.1. Mockito và inline mock

Một số use case của Mockito cần instrumentation để mock **final class**, **record** hoặc các phương thức mà kỹ thuật subclass truyền thống không xử lý như mong đợi.

Sau nâng cấp:

1. Xác định version Mockito thực sự đang dùng.
2. Xác định Byte Buddy và phần agent tương ứng.
3. Chạy test mock **interface**, **class** và những final types được dự án sử dụng.
4. Chạy dưới JDK 27 và chính sách dynamic-agent phù hợp.
5. Nếu lỗi chỉ xuất hiện ở final type, kiểm tra inline mock maker/agent trước khi sửa mã nghiệp vụ.

Nên dùng constructor injection và test doubles qua interface khi phù hợp. Không bắt buộc dùng instrumentation cho mọi unit test.

### 17.2. JaCoCo

**JaCoCo 0.8.16** đã công bố hỗ trợ chính thức class files Java 27. Khi cập nhật, cần kiểm tra:

- Version plugin/agent được nạp trong **JVM test thực tế**.
- Test suite hoàn thành, không lỗi khi instrument class 71.
- Report có dữ liệu lớp, nhánh và dòng phù hợp.
- Lớp generated, record, lambda và code đã được transform có mặt đúng phạm vi.
- Khi chạy cùng mocking/APM agent, report không bị rỗng hoặc mất class.

**Test PASS không đồng nghĩa coverage agent đã hoạt động.** Build có thể chạy test nhưng bỏ qua JaCoCo agent hoặc không thu được execution data.

### 17.3. PIT mutation testing

PIT tạo mutants bằng cách biến đổi bytecode rồi chạy các test liên quan. Điều này khiến PIT đặc biệt nhạy với **bytecode version** và **test runner adapter**.

Cần kiểm tra phiên bản PIT, plugin Maven/Gradle, adapter JUnit đang dùng và những thư viện nằm bên trong. Không tự suy ra bản PIT nào cũng hỗ trợ Java 27 chỉ vì JUnit tests có thể chạy.

Một smoke test nên có:

- Unit test trên bản gốc PASS.
- Mutation engine tìm được mutants ở class mục tiêu.
- Có mutants **KILLED/SURVIVED** thay vì một report rỗng vì scope sai.
- Không có lỗi class format hoặc unsupported bytecode.
- Thời gian thực thi và memory phù hợp CI.

## 18. Module access và strong encapsulation

Java 27 tiếp tục áp dụng **Java Platform Module System (JPMS)**. Một agent/parser có thể hiểu class file 71 nhưng bị chặn khi reflect vào private fields hoặc internal JDK types.

Các thông điệp tiêu biểu:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
~~~

Cần phân biệt:

| Cơ chế | Vai trò |
|---|---|
| **exports** | Cho phép truy cập public types/members theo quy tắc module |
| **opens** | Cho phép deep reflection vào package cho module được phép |
| **--add-exports** | Thêm export trong cấu hình runtime được kiểm soát |
| **--add-opens** | Thêm quyền reflective access có phạm vi |
| **Instrumentation.redefineModule** | Agent được tin cậy có thể mở rộng quan hệ module theo hợp đồng |

### 18.1. Ví dụ module do ứng dụng sở hữu

~~~java
module demo.application {
    exports demo.application.api;
    opens demo.application.model to demo.mapper;
}
~~~

Đây là ví dụ cấu hình ý tưởng, không phải file hiện hữu của ứng dụng.

Nếu một thư viện chỉ cần public API, không mở private package chỉ để làm cho lỗi biến mất.

Trong trường hợp migration tạm thời, có thể cân nhắc một tùy chọn **--add-opens** có phạm vi:

~~~bash
java --add-opens demo.application/demo.application.model=ALL-UNNAMED -jar app.jar
~~~

Hãy ghi rõ lý do, package, nhóm quyền hưởng lợi và kế hoạch thay thế. **Không** mở toàn bộ các package JDK cho mọi module bằng một danh sách tùy chọn sao chép từ Internet.

### 18.2. Vì sao không dùng --illegal-access?

Cờ **--illegal-access** phục vụ một giai đoạn chuyển tiếp cũ; trên Java 27, nó đã **obsolete** và không phải một cách hợp lệ để bỏ qua strong encapsulation. Nâng cấp thư viện hoặc cấu hình module có phạm vi là hướng đúng.

## 19. Phát hiện sử dụng API nội bộ với jdeps

**jdeps** là công cụ chuẩn để phân tích sự phụ thuộc tĩnh của class files.

~~~bash
jdeps --jdk-internals suspicious-library.jar
~~~

Có thể kiểm tra module dependencies:

~~~bash
jdeps --list-deps suspicious-library.jar
~~~

Với dependencies khác trên classpath:

~~~bash
jdeps --class-path "libs/*" --jdk-internals suspicious-library.jar
~~~

Kết quả giúp nhận diện các thành phần phụ thuộc vào internal JDK APIs.

**Giới hạn:** jdeps chủ yếu phân tích liên kết tĩnh từ class files. Reflection sử dụng string, bytecode được tạo động hoặc native code có thể không xuất hiện đầy đủ. Vì vậy, jdeps không thay thế integration tests.

Khi tìm được dependency tới **jdk.internal.*** hoặc API không có hợp đồng công khai:

1. Kiểm tra nhà phát hành có phiên bản đã chuyển sang public APIs không.
2. Ưu tiên nâng thư viện hoặc thay thế thành phần.
3. Tách các trường hợp không thể nâng ngay thành rủi ro được quản lý.
4. Không lấy quyền truy cập internal API như cam kết tương thích tương lai.

## 20. Java 27 và custom runtime images

Ứng dụng dùng **jlink** có thể chạy trên một runtime image không chứa đầy đủ modules của JDK phát triển.

Một số module đáng kiểm tra:

| Module | Khi nào có thể cần |
|---|---|
| **java.instrument** | Java instrumentation API |
| **java.management** | Management APIs được agent/ứng dụng dùng |
| **jdk.jfr** | JFR API và custom events |
| **jdk.attach** | Attach API trong môi trường hỗ trợ |
| **java.compiler / jdk.compiler** | Công cụ biên dịch hoặc compiler services nếu ứng dụng dùng |
| Modules ứng dụng | Những module framework cần thực sự |

Kiểm tra:

~~~bash
java --list-modules
~~~

Không xem việc không có executable **jcmd** trong runtime image là bằng chứng JVM không hỗ trợ instrumentation hay JFR. Runtime image tối giản thường không mang mọi công cụ CLI của JDK đầy đủ.

**Không thêm toàn bộ JDK modules cho chắc**, vì có thể làm tăng kích thước image và phạm vi vận hành. Hãy xây image theo phụ thuộc thực tế và chạy smoke tests với đúng image phân phối.

## 21. Multi-release JAR

Một JAR có thể có nhiều biến thể của cùng một class:

~~~text
META-INF/MANIFEST.MF
demo/Example.class
META-INF/versions/9/demo/Example.class
META-INF/versions/17/demo/Example.class
META-INF/versions/21/demo/Example.class
META-INF/versions/27/demo/Example.class
~~~

Với manifest **Multi-Release: true**, runtime Java chọn class phù hợp theo quy tắc multi-release JAR. Một scanner chỉ đọc lớp base có thể không nhìn thấy class thực sự được Java 27 load.

Kiểm tra nội dung:

~~~bash
jar --list --file library.jar
~~~

Dùng jdeps với lựa chọn phiên bản multi-release:

~~~bash
jdeps --multi-release 27 library.jar
~~~

Đó là lệnh phân tích, **không** chuyển đổi thư viện cũ thành thư viện hỗ trợ Java 27.

Với JAR có class files từ nhiều phiên bản, cần kiểm tra:

- Branch nào được JVM load.
- Bytecode parser có đọc được branch được chọn không.
- Code coverage có map về nguồn đúng không.
- APM/agent có transform đúng phiên bản class không.

## 22. Phân biệt những lỗi thường gặp

| Lỗi hoặc triệu chứng | Khả năng nguyên nhân | Điểm kiểm tra tiếp |
|---|---|---|
| **Unsupported class file major version 71** | Parser ASM/Byte Buddy/build plugin cũ | Classpath, shaded JAR, release notes |
| **UnsupportedClassVersionError** | JVM đang load class có binary version không hỗ trợ | JVM runtime, major version |
| **ClassFormatError** | Class bytes malformed hoặc transformer tạo dữ liệu không hợp lệ | Original/transformed bytes, parser |
| **VerifyError** | StackMapTable, control flow hoặc stack types không hợp lệ | Transformer/frames/verifier |
| **ClassCircularityError** | Agent vô tình load class liên quan khi transform | Stack trace và callback |
| **NoClassDefFoundError** | Class/dependency không thể load/link | Classpath, module path, dependency |
| **NoSuchMethodError** | Binary API mismatch giữa versions | Resolved version và loaded classes |
| **InaccessibleObjectException** | JPMS không cho deep reflection | Mở module có mục tiêu, nâng library |
| **IllegalAccessError** | Không được phép liên kết member/type | Module access và bytecode |
| **UnmodifiableClassException** | Class không được JVM cho phép sửa | isModifiableClass, capability |
| **Agent failed to initialize** | Manifest, agent entry point hoặc dependency sai | Premain-Class, classpath, agent logs |
| **Inline mock maker cannot initialize** | Byte Buddy/agent/attach policy không phù hợp | Mockito backend và agent config |
| **Coverage report rỗng** | Test không có agent, agent crash hoặc report sai scope | Startup args, test JVM, execution data |
| **APM không có spans** | Agent lỗi instrument hoặc không hỗ trợ framework | Logs, agent version, integration smoke |
| **Chỉ lỗi khi bật nhiều agents** | Transform ordering hoặc helper classes xung đột | Chạy riêng từng agent rồi tổ hợp |

### 22.1. Parser lỗi khác JVM load lỗi

Nếu stack trace cho thấy:

~~~text
org.objectweb.asm.ClassReader
IllegalArgumentException: Unsupported class file major version 71
~~~

lỗi có thể đến từ một **thư viện phân tích class file**.

Nếu gặp:

~~~text
java.lang.UnsupportedClassVersionError
~~~

JVM có thể đang từ chối **nạp** file do một Java runtime cũ hơn không hỗ trợ version đó.

Hai loại lỗi có hướng xử lý khác nhau. Đừng chỉ đọc một dòng log cuối cùng; phải xác định **thành phần đầu tiên báo lỗi và class loader liên quan**.

## 23. Quy trình điều tra một lỗi class file version 71

Khi nhận lỗi:

~~~text
Unsupported class file major version 71
~~~

Hãy điều tra theo thứ tự:

1. Ghi **java -version** ở runtime thực tế.
2. Ghi compiler JDK, Gradle daemon JDK và test process JDK.
3. Dùng **javap -verbose** trên file bị báo lỗi.
4. Tìm stack trace đầu tiên cho biết parser nào ném lỗi.
5. Dùng Maven/Gradle dependency resolution trong **đúng configuration/classloader**.
6. Kiểm tra agent JAR và shaded bytecode libraries.
7. Đối chiếu release notes của phiên bản được load.
8. Nâng đúng thư viện hoặc plugin, không force version mù quáng.
9. Chạy test canary class version 71 và tính năng instrumentation thực.
10. Chạy lại toàn bộ tổ hợp agents.
11. So sánh coverage/telemetry, không chỉ startup status.
12. Đánh giá tác động performance và chuẩn bị rollback.

**Không nâng tất cả dependencies cùng một lần** nếu có thể cô lập lỗi để giảm rủi ro. Sau khi xác định nguồn, nâng theo nhóm có chủ đích và giữ kết quả đo trước/sau.

## 24. Lập bộ canary classes

Một bộ test tương thích nên có đại diện cho những dạng class mà framework thật sự sẽ xử lý.

Ví dụ **CanaryOrder.java**:

~~~java
package demo.canary;

import java.util.List;

public record CanaryOrder(
    String id,
    List<String> tags
) {
    public String label() {
        return id + ":" + tags.size();
    }
}
~~~

Ví dụ này dùng các tính năng ổn định:

- Record.
- Generic type declaration.
- Accessors.
- Phần thân method với string concatenation.

Khi ứng dụng dùng chúng, có thể bổ sung:

- Sealed classes.
- Pattern matching ổn định.
- Lambdas và method references.
- Annotations và type-use annotations.
- Những class bị proxy/mocked.
- Custom classloaders và multi-release JARs.

### 24.1. Canary cần xác minh nhiều thứ

1. Biên dịch với **--release 27**.
2. Xác nhận major 71.
3. JVM Java 27 load class.
4. Parser/tool đọc class không ném lỗi.
5. Code generator sinh proxy/mock đúng.
6. Coverage agent có dữ liệu.
7. Agent APM ghi metric/span dự kiến.
8. Nếu dùng retransform, capability và class scope hợp lệ.
9. Kết quả vẫn đúng khi bật đủ agents và test concurrency.

Một bài test chỉ khởi tạo JVM thành công **chưa đủ**.

## 25. Ma trận kiểm thử upgrade

| Kiểm tra | Baseline JDK cũ | Java 27, không agent | Java 27, đủ agents |
|---|---|---|---|
| Compile và unit tests | Ghi thực tế | Cần PASS | Cần PASS |
| Load classes | Ghi thực tế | Cần PASS | Cần PASS |
| Bytecode parser version 71 | Không áp dụng nếu chưa cần | Cần PASS | Cần PASS |
| Runtime proxy/mock | Ghi thực tế | Cần PASS | Cần PASS |
| JaCoCo execution data | Ghi thực tế | Theo test config | Cần PASS |
| APM tracing/metrics | Ghi thực tế | N/A | Cần PASS |
| Module access | Ghi thực tế | Cần PASS | Cần PASS |
| Integration tests | Ghi thực tế | Cần PASS | Cần PASS |
| p95/p99 và CPU overhead | Baseline | Mốc so sánh | Không vượt ngân sách |
| Startup và shutdown | Ghi thực tế | Cần PASS | Cần PASS |
| Recovery/rollback | Có hướng dẫn | Có hướng dẫn | Có hướng dẫn |

**“Cần PASS” là điều kiện mục tiêu**, không phải kết quả đã thực thi cho một project cụ thể.

### 25.1. Chạy theo tầng

- **Tầng 1:** JDK 27 và ứng dụng không agent để tách lỗi runtime.
- **Tầng 2:** Bật một agent để xác định thành phần.
- **Tầng 3:** Bật agent khác riêng lẻ.
- **Tầng 4:** Bật toàn bộ agents đúng thứ tự production.
- **Tầng 5:** Kiểm tra load test, latency, GC và correctness.
- **Tầng 6:** Canary deployment và theo dõi production metrics.

### 25.2. Điều kiện rollback

Nên định nghĩa sớm:

- Lỗi class loading hoặc exception startup lặp lại.
- Mất một phần coverage/telemetry bắt buộc.
- p99 latency tăng vượt ngưỡng đã thống nhất.
- Tăng CPU/heap đáng kể do agent.
- Không thể tắt agent lỗi hoặc không có cách quay về JDK cũ trong thời hạn cần thiết.

Không đợi tới khi lỗi xảy ra mới thiết kế rollback.

## 26. Kiểm kê startup arguments và môi trường thật

Agent có thể đến từ nhiều nơi ngoài build files:

- **-javaagent** trong lệnh khởi động.
- **JAVA_TOOL_OPTIONS**.
- **JDK_JAVA_OPTIONS**.
- Container entrypoint và startup scripts.
- Platform/APM injection.
- Plugin build fork JVM test.
- Cấu hình runtime của IDE hoặc CI.

Với JVM có quyền truy cập phù hợp:

~~~bash
jcmd <pid> VM.command_line
~~~

Thay **<pid>** bằng PID hợp lệ. Khi ghi lại command line, **che token, password và đường dẫn nhạy cảm**.

Nên có bảng lưu:

~~~text
Application build:        commit hoặc release
JDK vendor/build:         Java 27 + patch version
Build tool:               Gradle/Maven version
Compile target:           --release 27
ASM/Byte Buddy:           resolved versions
JaCoCo/Mockito/PIT:       versions + plugins
APM/agent:                vendor version + checksum
JVM flags/agent order:    secrets redacted
Container image:          immutable image digest
~~~

## 27. Bảo mật và integrity của Java agent

Agent có thể sửa bytecode, quan sát arguments và can thiệp runtime. Cần xem nó như một thành phần **quyền cao**, không phải một tiện ích vô hại.

Checklist:

- Chỉ chấp nhận agent từ nguồn được phê duyệt.
- Kiểm tra checksum/chữ ký khi phân phối.
- Pin artifact version và khóa dependency khi có thể.
- Không nhận URL agent JAR tùy ý từ người dùng.
- Giới hạn người có thể sửa lệnh startup và môi trường chứa agent.
- Không log plaintext credentials hoặc dữ liệu người dùng vào spans.
- Quản lý những module đã mở và quyền native/attach.
- Giám sát security advisories của ASM/Byte Buddy/agent vendor.
- Kiểm thử update và có rollback cho agent độc lập.

**Tương thích không chỉ là “không crash”.** Một agent phải an toàn, có nguồn gốc rõ và không phá chính sách truy cập dữ liệu.

## 28. Anti-patterns cần tránh

| Anti-pattern | Vì sao nguy hiểm | Thay bằng |
|---|---|---|
| Chỉ kiểm tra java -version | Không kiểm tra build plugins/agents | Ma trận process/JDK |
| Sửa 2 byte header class file | Có thể tạo bytecode sai | Nâng parser hoặc compile đúng target |
| Nâng ASM trực tiếp rồi coi xong | Shaded ASM vẫn cũ | Nâng vendor plugin/agent |
| Dùng thư viện không công bố hỗ trợ Java 27 | Dễ lỗi khi parse/transform | Release notes + canary |
| Không kiểm tra report coverage | Agent fail nhưng tests vẫn pass | Assert report có dữ liệu |
| Bật mọi agent cùng lúc ở lượt đầu | Khó xác định nguồn lỗi | Test từng agent rồi tổ hợp |
| Tắt warning dynamic agent | Che vấn đề integrity | Xác định nhu cầu attach |
| Mở mọi package java.base | Mở rộng quyền không cần thiết | Public API/opens có phạm vi |
| Dùng --illegal-access | Cơ chế đã obsolete | Nâng framework/module đúng |
| Sửa input classfileBuffer tại chỗ | Vi phạm ClassFileTransformer contract | Trả byte[] mới |
| Transform core JDK classes tùy tiện | Circularity/linkage error | Giới hạn class scope |
| Giả định redefine thêm được field | JVM có giới hạn schema | Tuân thủ capability |
| Bỏ qua multi-release JAR | Không thấy class Java 27 thực tế | Phân tích versions của JAR |
| Chỉ kiểm tra dependency tree | Không phát hiện shaded/embedded libs | Kiểm tra vendor JAR/SBOM |
| Không đo agent overhead | Có thể làm tail latency xấu | A/B với cùng workload |
| Cài agent không xác minh nguồn | Rủi ro supply-chain | Chính sách artifact và checksum |

## 29. Bài thực hành

### Bài A — Đọc class version

1. Biên dịch **Greeting.java** bằng **javac --release 27**.
2. Dùng **javap -verbose** đọc major/minor.
3. Chạy **ClassFileInspector** và so sánh kết quả.
4. Biên dịch lại cùng mã với **--release 21**.
5. Giải thích vì sao 65 và 71 không chứng minh riêng một parser cũ đã hỗ trợ cả hai.

### Bài B — Java agent startup

1. Viết **LoggingAgent** và **Main** trong thư mục lab.
2. Tạo manifest có **Premain-Class**.
3. Đóng gói agent JAR và chạy **-javaagent**.
4. Kiểm tra agent nhận **demo/app/Main** theo internal name.
5. Chạy lại không agent để đối chiếu.
6. Giải thích tại sao **return null** nghĩa là không transform.

### Bài C — Tìm dependency bị shaded

Giả sử hệ thống có:

~~~text
Build plugin    -> ASM version A
Test runtime    -> Mockito + Byte Buddy version B
Coverage agent  -> JaCoCo + ASM version C
APM agent JAR   -> shaded ASM version D
~~~

Hãy:

1. Xem dependency tree.
2. Kiểm tra JAR/manifest/release notes của APM agent.
3. Lập bảng version và classfile 71 support.
4. Xác nhận phiên bản JVM thực của build/test/runtime.
5. Chạy một test record và final mocking.
6. Chạy test với JaCoCo trước, APM sau.
7. Đo report coverage/telemetry và p95.
8. Xác định thành phần cần nâng và kế hoạch rollback.

### Bài D — Phân tích ba lỗi

Phân loại:

~~~text
Unsupported class file major version 71
java.lang.reflect.InaccessibleObjectException
java.lang.UnsupportedClassVersionError
~~~

Với từng lỗi, ghi:

- Thành phần nào có thể ném lỗi.
- Dữ liệu cần thu thập.
- Công cụ/chạy lệnh cần dùng.
- Cách sửa an toàn.
- Tín hiệu test đủ để kết luận đã khắc phục.

## 30. Câu hỏi tự kiểm tra

1. Java 27 sử dụng class file major version nào?
2. Vì sao JVM hiểu class 71 nhưng ASM cũ có thể không?
3. **--release 21** khác chạy test bằng JDK 21 như thế nào?
4. Class-File API chuẩn có từ Java version nào?
5. Vì sao một ASM được shaded không hiện trong dependency tree?
6. JaCoCo bản nào có xác nhận chính thức Java 27?
7. **premain** và **agentmain** khác thời điểm nào?
8. Java agent JAR cần manifest key nào cho **-javaagent**?
9. ClassFileTransformer trả **null** có ý nghĩa gì?
10. Vì sao không được sửa classfileBuffer đầu vào tại chỗ?
11. Hai agents cùng transform một method có rủi ro gì?
12. Retransform có tùy ý thêm field không?
13. Cảnh báo dynamic agent loading từ JEP 451 có ý nghĩa gì?
14. **--add-exports** khác **--add-opens** như thế nào?
15. Vì sao **--illegal-access** không còn là cách sửa trên Java 27?
16. **jdeps --jdk-internals** phát hiện gì, bỏ sót gì?
17. Tại sao multi-release JAR cần kiểm tra riêng?
18. Báo cáo JaCoCo rỗng có chứng minh test suite không chạy không?
19. Cần test gì để khẳng định agent APM hoạt động đúng?
20. Vì sao Java agent phải trải qua kiểm soát supply-chain?

## 31. Ghi nhớ

- Java 27 sử dụng class file **major 71**.
- Kiểm tra đủ **JDK runtime, compiler/build, bytecode parser, agent và module access**.
- **Class-File API** trong **java.lang.classfile** là API chuẩn có từ Java 24.
- ASM, Byte Buddy, JaCoCo, PIT, Mockito và APM agents cần được đánh giá theo version **thực sự được nạp**.
- **ASM 9.11.1**, **JaCoCo 0.8.16** và các bản **Byte Buddy 1.18.x** là các mốc cần đối chiếu với Java 27 cuối năm 2026.
- **Shaded libraries** có thể không nằm trong dependency tree.
- Startup agent **-javaagent** dùng **premain**; agent nạp động dùng **agentmain** theo cơ chế cho phép.
- **JEP 451** cảnh báo về dynamic agent loading; không xem self-attach là quyền mặc định lâu dài.
- **ClassFileTransformer** trả **null** để giữ nguyên bytes hoặc trả **byte[] mới hợp lệ** để transform.
- **Retransform/redefine** có giới hạn, không cho sửa cấu trúc lớp tùy ý.
- Lỗi parser, JVM class loading và JPMS encapsulation là những lớp lỗi khác nhau.
- Dùng **javap**, **Class-File API**, **jdeps**, dependency inspection và smoke tests.
- Xác minh **coverage, mocking, telemetry và tính đúng khi các agents cùng hoạt động**.
- Kết luận nâng cấp chỉ được chấp nhận khi có **bằng chứng test, performance baseline và rollback**.

## Tài liệu tham khảo

- [Java SE 27 — JVM Specification, Class File Format](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html)
- [Java SE 27 API — ClassFile](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [Java SE 27 API — ClassModel](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassModel.html)
- [Java SE 27 API — java.lang.instrument](https://docs.oracle.com/en/java/javase/27/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java SE 27 API — Instrumentation](https://docs.oracle.com/en/java/javase/27/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java SE 27 API — ClassFileTransformer](https://docs.oracle.com/en/java/javase/27/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java SE 27 — javap command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html)
- [Java SE 27 — jdeps command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html)
- [Java SE 27 — Java launcher](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [OpenJDK JEP 484 — Class-File API](https://openjdk.org/jeps/484)
- [OpenJDK JEP 451 — Prepare to Disallow Dynamic Loading of Agents](https://openjdk.org/jeps/451)
- [ASM — Versions and Release Notes](https://asm.ow2.io/versions.html)
- [JaCoCo — Change History](https://www.jacoco.org/jacoco/trunk/doc/changes.html)
- [Byte Buddy — Java Version Compatibility](https://github.com/raphw/byte-buddy#java-version-compatibility)
- [Byte Buddy — Release Notes](https://github.com/raphw/byte-buddy/blob/master/release-notes.md)
