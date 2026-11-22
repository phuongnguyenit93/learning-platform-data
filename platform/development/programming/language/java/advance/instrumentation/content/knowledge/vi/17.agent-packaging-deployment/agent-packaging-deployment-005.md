# Không phụ thuộc các lớp xử lý bytecode nội bộ không được JDK hỗ trợ

## 1. Vì sao đây là yêu cầu của việc đóng gói và triển khai Java agent?

Một Java agent có thể hoạt động tốt trên máy phát triển, nhưng lỗi ngay khi đem sang JDK hoặc runtime khác nếu agent **dựa trực tiếp vào các lớp xử lý bytecode nội bộ của JDK**, ví dụ `jdk.internal.org.objectweb.asm.ClassReader`. Các lớp như vậy là chi tiết triển khai của JDK, không phải hợp đồng lập trình công khai dành cho ứng dụng. Dùng được trên một bản JDK **không đồng nghĩa được hỗ trợ ổn định**.

Trong Java 9+, hệ thống module còn giới hạn truy cập vào package nội bộ. Một import `jdk.internal...` có thể bị từ chối ngay ở compile time; nếu ép compiler bằng `--add-exports`, khi chạy lại có thể gặp `IllegalAccessError` vì JVM đích không có cờ tương ứng. Ngay cả khi tạm “mở” được, phiên bản lớp nội bộ có thể thay đổi trong bản cập nhật JDK mà agent không kiểm soát.

**Mục tiêu chính của bài:** thiết kế, đóng gói và kiểm thử agent có khả năng xử lý bytecode mà **không liên kết tới API nội bộ không được hỗ trợ của JDK**. Cách ưu tiên:

1. Sử dụng **`java.lang.instrument`** — API chính thức để nhận `Instrumentation`, đăng ký transformer, retransform hoặc redefine class.
2. Với Java 17/21, dùng thư viện xử lý bytecode **công khai, được quản lý phiên bản** như OW2 ASM hoặc Byte Buddy, thay vì bản ASM nội bộ trong JDK.
3. Đóng gói các dependency cần thiết **vào agent JAR** hoặc bố trí class loader được kiểm soát; cân nhắc **shade và relocate** để tránh trùng version với thư viện của ứng dụng đích.
4. Nếu triển khai tối thiểu trên **JDK 24+**, có thể sử dụng API công khai `java.lang.classfile` được chuẩn hóa từ JDK 24 (JEP 484). **Không dùng API này khi cần chạy trên JVM 17/21**.
5. Kiểm tra bytecode target version, manifest, dependency graph và thử trên JVM thực tế với `jdeps --jdk-internals` cùng `-Xverify:all`.

Bài có ba thí nghiệm: **lỗi có chủ đích** khi import ASM nội bộ; một **agent Java 17+ thật** dùng ASM từ Maven, shading và chèn probe thành công; một ví dụ **Class-File API công khai của JDK 24** có thể parse và transform classfile Java 17.

## 2. Phân biệt API được hỗ trợ và implementation detail

### 2.1. Bảng nhận diện nhanh

| Nhóm | Ví dụ | Đánh giá khi viết Java agent |
|---|---|---|
| Java SE public API | `java.lang.instrument.Instrumentation`, `ClassFileTransformer` | Được tài liệu hóa và hỗ trợ trong phạm vi phiên bản Java SE |
| Java SE public Class-File API từ JDK 24 | `java.lang.classfile.ClassFile`, `ClassModel` | Dùng công khai từ JDK 24; không có trên 17/21 |
| Thư viện bên ngoài có release riêng | `org.objectweb.asm.ClassReader`, `org.objectweb.asm.commons.AdviceAdapter` | Hợp lệ nếu khai báo dependency, chọn phiên bản phù hợp và phân phối đúng |
| Thư viện instrumentation bên ngoài | `net.bytebuddy.*` | Hợp lệ nếu quản lý dependency và tương thích runtime |
| JDK internal package | `jdk.internal.org.objectweb.asm.*` | **Không dùng làm dependency sản phẩm**; không có compatibility contract cho app |
| JDK internal/compiler implementation | Một số `com.sun.tools.javac.*` hoặc `jdk.internal.*` | Cần kiểm tra hợp đồng API thực tế; không tự coi là supported chỉ vì compile được với flags |
| API riêng được tài liệu hóa của một JDK | Ví dụ module `jdk.attach` với `com.sun.tools.attach.VirtualMachine` | Có thể là **JDK-specific API được công bố**, không được đánh đồng mọi tên `jdk.*`/`com.sun.*` với unsupported |

**Điểm cần nhớ:** package name có thể là dấu hiệu, **không phải phép phân loại duy nhất**. Ranh giới quyết định là API có tài liệu công khai và compatibility/support contract cho ứng dụng hay chỉ là implementation detail bên trong JDK.

### 2.2. Hai gói ASM khác nhau về trách nhiệm

~~~text
org.objectweb.asm.ClassReader
  -> OW2 ASM chính thức, khai báo từ org.ow2.asm:asm
  -> nhóm phát triển quản lý version và release độc lập
  -> bạn chủ động đóng gói dependency cần thiết

jdk.internal.org.objectweb.asm.ClassReader
  -> bản ASM nằm bên trong JDK, package nội bộ java.base
  -> không phải thư viện ứng dụng công khai
  -> JDK có thể nâng cấp/sửa API mà không bảo đảm tương thích với agent
~~~

Dù tên class có phần cuối giống nhau, **không được thay import giữa hai package như thể chúng là hai implementation tương đương được hỗ trợ**. Agent import `jdk.internal.org.objectweb.asm` có dependency tới hình dạng JDK cụ thể và có thể bị chặn bởi JPMS.

### 2.3. “Có trên máy” không đồng nghĩa “được đóng gói đúng”

Một số developer nghĩ rằng vì `jdk.internal.org.objectweb.asm` đã nằm sẵn trong Java runtime, dùng nó sẽ tiết kiệm kích thước JAR và đơn giản deployment. Cách này tạo **dependency ẩn vào nhà cung cấp và phiên bản JVM đích**. Thứ bạn tiết kiệm được khi build có thể chuyển thành lỗi runtime khó sửa, đặc biệt khi agent được triển khai độc lập trên hàng trăm JVM.

Ngược lại, nếu dùng OW2 ASM chính thức, bạn có thể pin version, có checksum, dependency inventory, security updates và build artifact có thể kiểm toán.

## 3. Vì sao module encapsulation làm code nội bộ thất bại?

Kể từ Java 9, package nội bộ không được export cho unnamed module hoặc module ứng dụng theo mặc định, trừ những ngoại lệ được tài liệu hóa. `jdk.internal.org.objectweb.asm` nằm trong `java.base` nhưng **không được export như một Java SE API công khai**.

### 3.1. Lỗi lúc compile

Một ví dụ cố ý sai, tệp **`InternalAsmDemo.java`**:

~~~java
import jdk.internal.org.objectweb.asm.ClassReader;

public final class InternalAsmDemo {
    public static void main(String[] args) {
        System.out.println(
                "internal-class=" + ClassReader.class.getName());
    }
}
~~~

Với một JDK hiện đại, chạy:

~~~bash
javac -d outInternal InternalAsmDemo.java
~~~

Thông thường `javac` từ chối và chỉ rõ package trong `java.base` **không visible/không exported** cho unnamed module. Nếu dùng `javac --release 17`, những API không thuộc Java 17 supported symbols cũng không trở thành API hợp lệ.

**Đây là negative test có chủ đích**. Không giải quyết bằng cách đổi source sang import nội bộ khác.

### 3.2. Ép biên dịch bằng --add-exports vẫn không biến nó thành API public

Trên JDK kiểm thử, lệnh dưới cho phép biên dịch thí nghiệm:

~~~bash
javac --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED -d outInternal InternalAsmDemo.java
~~~

Nhưng chạy **không có runtime export**:

~~~bash
java -cp outInternal InternalAsmDemo
~~~

thì bị lỗi **`IllegalAccessError`** do class trong unnamed module không được `java.base` export package tương ứng.

Nếu chạy tiếp với cờ mở export:

~~~bash
java --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED -cp outInternal InternalAsmDemo
~~~

thí nghiệm trên JDK 24.0.2 in:

~~~text
internal-class=jdk.internal.org.objectweb.asm.ClassReader
~~~

Đây chỉ là **workaround để chứng minh access control**, không phải kiến trúc sản phẩm. Muốn agent chạy ở máy khác, bạn phải bảo đảm flags tương tự được truyền cho tất cả JVM, nhưng **ngay cả như vậy** JDK vẫn không cam kết giữ API internal ổn định.

**Phân biệt cờ:** `--add-exports` mở khả năng truy cập package với public types theo module rules; `--add-opens` chủ yếu mở **deep reflection**. Không dùng `--add-opens` như thuốc chữa mặc định cho lỗi source import hay bytecode linkage.

### 3.3. Kiểm tra phụ thuộc tĩnh bằng jdeps

Sau khi ép compile chỉ cho mục đích kiểm chứng:

~~~bash
jdeps --jdk-internals outInternal/InternalAsmDemo.class
~~~

Trên JVM đã kiểm thử, `jdeps` chỉ ra:

~~~text
InternalAsmDemo.class -> java.base
   InternalAsmDemo -> jdk.internal.org.objectweb.asm.ClassReader  JDK internal API (java.base)
~~~

`jdeps` còn cảnh báo rằng các JDK internal API là implementation detail, có thể bị loại bỏ hoặc thay đổi không tương thích. Đây là một **công cụ QA quan trọng** trước khi xuất bản agent JAR.

**Giới hạn của jdeps:** phân tích phụ thuộc tĩnh qua classfile, không bảo đảm phát hiện tên class nội bộ được ráp bằng chuỗi rồi gọi reflection, code được generate ở runtime hoặc native dependencies. Vì vậy cần kết hợp quét source, dependency graph và thử nghiệm hành vi.

## 4. Rủi ro triển khai khi gắn với ASM nội bộ

### 4.1. Không ổn định giữa các JDK update

Bản ASM được nhúng trong JDK phục vụ nhu cầu **của JDK**, không phải mục tiêu quản lý semantic version cho ứng dụng. Các methods, constructors, constants và bản sửa đổi nội bộ có thể khác bản ASM mà bạn tìm thấy trên Maven Central. Agent có nguy cơ `NoSuchMethodError`/`NoSuchFieldError` hoặc hành vi parsing khác sau nâng JDK.

### 4.2. Build server và production JVM khác nhau

Một agent compile trên JDK X cùng `--add-exports` có thể:

- không compile trên môi trường CI/JDK Y;
- compile được nhưng JVM đích không có runtime `--add-exports`, gây `IllegalAccessError`;
- link được nhưng không hiểu classfile major/attributes của class ứng dụng;
- phụ thuộc vào nội bộ vendor-specific khác nhau.

**Cần test thực tế trên supported runtime matrix**, không coi máy developer là nguồn sự thật duy nhất.

### 4.3. Flags là debt vận hành

Việc bắt cả đội vận hành thêm `--add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED` cho mọi ứng dụng chỉ để agent chạy làm tăng deployment coupling. Đây là một ngoại lệ mạnh vào JPMS, cần được đánh dấu và giới hạn nếu chỉ dùng tạm để migration.

### 4.4. Tránh sử dụng chính sách phủ định quá rộng

Không phải tất cả `com.sun.*`, `sun.*`, `jdk.*` đều giống nhau về tình trạng hỗ trợ. Ví dụ `jdk.attach` có tài liệu JDK-specific công khai. Quy tắc an toàn là: **chỉ dựa trên API chính thức có hợp đồng cho runtime mục tiêu**, không dùng trực tiếp implementation namespace chỉ vì nó nằm trên classpath/boot layer.

## 5. Chọn phương án bytecode processing được hỗ trợ

| Yêu cầu | Giải pháp | JDK runtime tối thiểu | Lưu ý |
|---|---|---|---|
| Java agent nhận class bytes, cài transformer | `java.lang.instrument` | Java 5+ (nhiều capability có từ Java 6/9) | API quản lý instrumentation, không tự cung cấp parser/visitor bytecode tổng quát trước JDK 24 |
| Java 17/21/24, cần đọc/sửa bytecode thấp tầng | **OW2 ASM** chính thức `org.ow2.asm` | Tùy bản ASM chọn | Chọn ASM release hiểu classfile major phiên bản JVM đích |
| Muốn khai báo advice/interception dễ hơn | **Byte Buddy** | Tùy release Byte Buddy và VM | Thư viện cấp cao, cần packaging/compatibility testing |
| JVM chỉ JDK 24+ và muốn public JDK API | **`java.lang.classfile`** | **JDK 24** | Chuẩn hóa theo JEP 484; không khả dụng trên Java 17/21 |
| Chỉ cần telemetry không sửa body Java | JFR, JVM metrics hoặc APIs đã được công bố | Tùy API và runtime | Tránh bytecode dependency khi không cần thiết |
| Đã viết code dùng `jdk.internal.org.objectweb.asm` | Thay sang OW2 ASM hoặc public Class-File API nếu phù hợp | Theo lựa chọn | Không dừng ở việc thêm flags; kiểm soát dependency graph |

**Khuyến nghị trong bài này:** vì một agent thường cần hỗ trợ Java 17 trở lên, phần thực hành sử dụng **OW2 ASM 9.11.1** và **Maven Shade Plugin 3.6.2**, cả hai là dependencies **công khai** được khai báo theo version. Ví dụ đã được biên dịch bằng `--release 17` và chạy với `-Xverify:all`.

Nếu dự án chọn Byte Buddy, cũng phải pin version, kiểm tra tương thích classfile và package dependency đúng. Đừng xem việc dùng thư viện bên ngoài là lý do bỏ qua verification.

## 6. End-to-end: Java 17 agent với OW2 ASM được đóng gói riêng

Chương trình thực hành **không import bất kỳ package JDK internal nào**. Agent:

1. Dùng `java.lang.instrument.Instrumentation` để đăng ký `ClassFileTransformer`.
2. Lọc đúng class `demo.Service` lúc JVM nạp.
3. Dùng OW2 ASM `ClassReader`, `ClassVisitor`, `ClassWriter` và `AdviceAdapter` thêm một lệnh `System.out.println("agent:enter-hello")` khi vào method `hello()`.
4. Giữ nguyên giá trị trả về `"hello"` của method.
5. Đóng gói ASM `org.objectweb.asm` **trong agent JAR** và **relocate** thành `demo.agent.shaded.asm` để tránh đụng package với ASM phiên bản khác ở ứng dụng.
6. Chạy qua `-javaagent`, không truyền `--add-exports` hay `--add-opens` nào.

Thí nghiệm giúp phân biệt hai cách viết:

~~~text
SAI VỀ HỢP ĐỒNG API:
  import jdk.internal.org.objectweb.asm.ClassReader;

ĐÚNG VỀ PHẠM VI DEPENDENCY:
  import org.objectweb.asm.ClassReader;
  (dependency org.ow2.asm:asm được khai báo và đóng gói)
~~~

**Lưu ý:** Sau khi shading, source vẫn import `org.objectweb.asm.*` tại compile time, nhưng plugin **viết lại bytecode và di chuyển class files** trong final JAR. Không tự sửa import Java thành package shaded trong source.

### 6.1. Cấu trúc project

~~~text
safe-asm-agent/
├── pom.xml
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               └── Agent.java
├── app/
│   └── demo/
│       ├── Service.java
│       └── Main.java
├── app-out/               # tạo khi build
└── target/                # tạo bởi Maven
    └── safe-asm-agent-1.0.0.jar
~~~

`app` chứa code demo **không nằm trong agent JAR**. `mvn package` đóng gói agent và ASM thành artifact độc lập; sau đó `javac` compile application bằng target Java 17.

## 7. Maven POM: pin version và relocate ASM

Tệp **`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>safe-asm-agent</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.11.1</version>
    </dependency>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm-commons</artifactId>
      <version>9.11.1</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.2</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>

              <relocations>
                <relocation>
                  <pattern>org.objectweb.asm</pattern>
                  <shadedPattern>demo.agent.shaded.asm</shadedPattern>
                </relocation>
              </relocations>

              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <manifestEntries>
                    <Premain-Class>demo.Agent</Premain-Class>
                  </manifestEntries>
                </transformer>
              </transformers>

              <filters>
                <filter>
                  <artifact>*:*</artifact>
                  <excludes>
                    <exclude>META-INF/*.SF</exclude>
                    <exclude>META-INF/*.DSA</exclude>
                    <exclude>META-INF/*.RSA</exclude>
                  </excludes>
                </filter>
              </filters>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Giải thích từng phần:**

- `maven.compiler.release=17`: source và output classfile của agent nhắm tới Java 17, không phụ thuộc compile-time API Java 24.
- `org.ow2.asm:asm` và `asm-commons`: hai thư viện OW2 ASM public được Maven quản lý, không dùng bản ASM nội bộ của JDK.
- `asm-commons` cung cấp `AdviceAdapter`. Maven sẽ tải các transitive dependencies cần thiết theo dependency graph.
- `maven-shade-plugin` chạy ở pha `package` để tạo **agent JAR chứa dependencies**.
- `relocations` đổi `org.objectweb.asm` thành namespace riêng `demo.agent.shaded.asm` trong JAR cuối; cả `asm` và `asm-commons` cùng được relocate.
- `ManifestResourceTransformer` ghi main manifest `Premain-Class: demo.Agent` để `-javaagent` tìm đúng entry point.
- `META-INF/*.SF`, `*.DSA`, `*.RSA` bị loại khỏi uber JAR vì chữ ký gốc của các JAR dependency **không còn hợp lệ sau khi hợp nhất/relocate**. Đây không có nghĩa nên tắt việc kiểm chứng supply-chain: build vẫn cần xác minh dependency nguồn, checksum/signature và policy của tổ chức.
- `createDependencyReducedPom=false` làm ví dụ dễ dự đoán, không tự thay POM thành reduced version trong bài; dự án phát hành library có thể dùng cách khác.
- **Không bật `minimizeJar` một cách mù quáng**; các class dùng qua reflection, `ServiceLoader`, module/service descriptors hoặc bootstrap có thể bị công cụ phân tích phụ thuộc tĩnh bỏ sót.

**Lựa chọn version:** 9.11.1 và 3.6.2 là các version đã được build và kiểm thử trong bài. Với dự án thực tế, vẫn cần xác nhận support window, bản vá bảo mật và lịch cập nhật dependency thay vì tự động giữ chúng mãi mãi.

## 8. Source Java agent: chỉ dùng Instrumentation và ASM public

Tệp **`src/main/java/demo/Agent.java`**:

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.commons.AdviceAdapter;

public final class Agent {
    public static void premain(
            String options, Instrumentation inst) {

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String name,
                    Class<?> redefining,
                    ProtectionDomain domain,
                    byte[] bytes) {

                if (!"demo/Service".equals(name)) {
                    return null;
                }

                ClassReader reader = new ClassReader(bytes);
                ClassWriter writer = new ClassWriter(
                        reader, ClassWriter.COMPUTE_MAXS);

                ClassVisitor visitor = new ClassVisitor(
                        Opcodes.ASM9, writer) {

                    @Override
                    public MethodVisitor visitMethod(
                            int access,
                            String method,
                            String desc,
                            String sig,
                            String[] exceptions) {

                        MethodVisitor mv = super.visitMethod(
                                access, method, desc, sig, exceptions);

                        if (mv == null
                                || !"hello".equals(method)
                                || !"()Ljava/lang/String;".equals(desc)) {
                            return mv;
                        }

                        return new AdviceAdapter(
                                Opcodes.ASM9,
                                mv, access, method, desc) {

                            @Override
                            protected void onMethodEnter() {
                                visitFieldInsn(
                                        Opcodes.GETSTATIC,
                                        "java/lang/System",
                                        "out",
                                        "Ljava/io/PrintStream;");

                                visitLdcInsn(
                                        "agent:enter-hello");

                                visitMethodInsn(
                                        Opcodes.INVOKEVIRTUAL,
                                        "java/io/PrintStream",
                                        "println",
                                        "(Ljava/lang/String;)V",
                                        false);
                            }
                        };
                    }
                };

                reader.accept(visitor, 0);
                return writer.toByteArray();
            }
        }, false);
    }
}
~~~

### 8.1. Mục đích từng API

- `Instrumentation` được JVM cấp qua `premain`; agent không tự tạo instance của interface này.
- `ClassFileTransformer` nhận `byte[]` classfile khi class được define; trả `null` nếu không sửa class nào, hoặc `byte[]` mới khi có biến đổi.
- `name` dùng **dạng internal JVM name** `demo/Service`, không phải `demo.Service`.
- `ClassReader` đọc classfile của class đích; `ClassWriter` tạo bytes mới.
- `AdviceAdapter.onMethodEnter` thêm một lệnh `println` vào đầu method `hello`.
- `COMPUTE_MAXS` giúp ASM tính `max_stack/max_locals` cần thiết cho phép chèn đơn giản; không có nghĩa mọi thay đổi control flow đều tự hợp lệ. Nếu thêm branches/exception handlers hoặc frames phức tạp, cần chiến lược `COMPUTE_FRAMES` phù hợp và kiểm thử verifier cùng class hierarchy/class loader.
- `Opcodes.ASM9` là **API version constant của ASM** dùng trong visitor, không phải classfile major hay số version dependency 9.11.1.
- `addTransformer(..., false)` chỉ yêu cầu transform khi class ban đầu được nạp/redefine phù hợp; ví dụ không yêu cầu retransformation. Nếu cần instrument class **đã load**, phải thiết kế riêng capability `Can-Retransform-Classes` và ``addTransformer(transformer,true)` cùng `retransformClasses`, và tuân thủ giới hạn thay đổi cấu trúc.
- Agent cố ý chỉ instrument một class demo; không instrument `java.*`, ASM của chính mình hay helper classes, tránh class loading recursion và deadlock.

**Tại sao chèn `System.out.println`?** Vì target chỉ phải resolve một public JDK API sẵn có, tránh làm bài phụ thuộc việc nạp helper class từ class loader khác. Ở production hãy thay logging synchronous bằng telemetry an toàn/ít overhead, đồng thời kiểm soát module/package access.

### 8.2. Tránh lỗi thứ tự load class

Với `-javaagent`, JVM gọi `premain` **trước `Main.main`**. Sau đó `Main` mới tạo `Service`, transformer có cơ hội nhận classfile của `Service` khi nó được định nghĩa. Nếu `Service` đã load trước khi đăng ký transformer, ví dụ startup này không tự cập nhật class đã có. Khi cần hỗ trợ attach muộn, phải dùng retransform/redefine trong giới hạn của VM.

### 8.3. Vì sao không import jdk.internal?

Source trên chỉ import:

~~~java
org.objectweb.asm.ClassReader
org.objectweb.asm.ClassVisitor
org.objectweb.asm.ClassWriter
org.objectweb.asm.MethodVisitor
org.objectweb.asm.Opcodes
org.objectweb.asm.commons.AdviceAdapter
~~~

Đây là API **từ Maven dependencies được khai báo**. Final JAR relocate thành `demo.agent.shaded.asm`. Không có một import hoặc invocation tới `jdk.internal.org.objectweb.asm`. Vì thế agent không cần yêu cầu người vận hành thêm `--add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED`.

## 9. Ứng dụng thử nghiệm độc lập

Tệp **`app/demo/Service.java`**:

~~~java
package demo;

public final class Service {
    public String hello() {
        return "hello";
    }
}
~~~

Tệp **`app/demo/Main.java`**:

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app:begin");
        System.out.println(
                "result=" + new Service().hello());
        System.out.println("app:end");
    }
}
~~~

Code ứng dụng **không import ASM**. Nó chỉ dùng Java API; đó là một mục tiêu deployment: app không phải biết agent đang xử lý bytecode bằng công cụ nào và không phải cài cùng version ASM.

### 9.1. Tạo thư mục

Ở thư mục gốc `safe-asm-agent`:

~~~bash
mkdir -p app-out
~~~

Với PowerShell:

~~~powershell
New-Item -ItemType Directory -Force app-out
~~~

### 9.2. Lệnh build và chạy

~~~bash
mvn -q -DskipTests package
javac --release 17 -d app-out app/demo/Service.java app/demo/Main.java
java -Xverify:all -javaagent:target/safe-asm-agent-1.0.0.jar -cp app-out demo.Main
~~~

Nếu build đang ở một môi trường Maven có dependency proxy nội bộ, cấu hình repository/mirror theo quy trình tổ chức. Không tự tải JAR từ nguồn không tin cậy rồi đưa vào agent production. Bản lab trên máy có Maven 3.9.12, javac 24.0.2 biên dịch với `--release 17` và JVM 24.0.2 để chạy.

**Stdout thực tế:**

~~~text
app:begin
agent:enter-hello
result=hello
app:end
~~~

Có bốn kết luận độc lập:

1. `mvn package` đã tạo JAR agent có manifest hợp lệ.
2. JVM nạp `Agent.premain` và đăng ký transformer.
3. `ClassFileTransformer` đọc đúng `demo/Service` và chèn probe trước logic `hello`.
4. Giá trị trả về `hello` không đổi; chạy với `-Xverify:all` không phát sinh `VerifyError`.

Nếu chạy **không có `-javaagent`**:

~~~bash
java -cp app-out demo.Main
~~~

Output ứng dụng sẽ thiếu dòng `agent:enter-hello` nhưng vẫn có các dòng `app:begin`, `result=hello`, `app:end`. Đây là phép đối chứng hữu ích khi giải thích tác động của instrumentation.

### 9.3. Kiểm tra JAR sau shading

~~~bash
jar tf target/safe-asm-agent-1.0.0.jar
~~~

Trong bản đã kiểm thử:

- `demo/Agent.class` tồn tại.
- `demo/agent/shaded/asm/ClassReader.class` **có trong JAR**.
- `org/objectweb/asm/ClassReader.class` **không còn ở tên chưa relocate** trong JAR cuối.
- `jdk/internal/org/objectweb/asm/ClassReader.class` **không tồn tại**.
- `META-INF/MANIFEST.MF` chứa `Premain-Class: demo.Agent`.

Có thể xem manifest:

~~~bash
unzip -p target/safe-asm-agent-1.0.0.jar META-INF/MANIFEST.MF
~~~

`unzip` là tiện ích tùy hệ điều hành; nếu máy không có, dùng `jar xf` vào một thư mục kiểm tra tạm hoặc đọc entry bằng Java `JarFile`. **Không chỉnh sửa manifest trong agent JAR sau khi đã ký/phát hành** nếu không có bước đóng gói và ký lại phù hợp.

### 9.4. jdeps ở sản phẩm cuối

~~~bash
jdeps --jdk-internals target/safe-asm-agent-1.0.0.jar
~~~

Mục đích là tìm phụ thuộc **tĩnh** tới JDK internal APIs trong artifact cuối. Một lần quét không thấy lỗi **không bảo đảm** tất cả reflection/runtime-generated code an toàn; quét thêm source/pom/transitive dependencies và thực hiện integration tests.

Thử cả cờ `--multi-release` khi kiểm tra một **multi-release JAR** thực tế, để không bỏ sót các version-specific entries.

## 10. Vì sao Shade/relocation quan trọng với Java agent?

### 10.1. Agent chạy trong JVM của ứng dụng khác

Java agent không chỉ là một thư viện app thông thường: nó được nạp trong JVM của ứng dụng đích và có thể bị ảnh hưởng bởi **classpath, system/boot class loader, module boundaries và nhiều agents**. Nếu agent đóng gói ASM nguyên `org.objectweb.asm` còn app đã có ASM version khác, class loading có thể chọn version ngoài dự kiến và gây:

- `NoSuchMethodError` hoặc `NoSuchFieldError` khi API ASM khác nhau;
- `LinkageError` vì class từ hai versions không tương thích;
- khác hành vi parser/visitor với classfile major mới;
- kết quả không tái hiện được giữa test và production.

**Shading** gom dependencies vào artifact deploy; **relocation** chuyển namespace để giảm xác suất xung đột binary names. Hai thao tác liên quan nhưng **không đồng nghĩa**.

### 10.2. Đặt namespace riêng, không đặt dưới jdk.internal

Trong `pom.xml`:

~~~xml
<relocations>
  <relocation>
    <pattern>org.objectweb.asm</pattern>
    <shadedPattern>demo.agent.shaded.asm</shadedPattern>
  </relocation>
</relocations>
~~~

Namespace `demo.agent.shaded.asm` thuộc quyền quản lý của agent, không phải `jdk.internal.*`. Không relocate ASM thành `jdk.internal.org.objectweb.asm`: đây là package nội bộ của `java.base` và không phải chỗ để deploy thư viện của bạn.

### 10.3. Những rủi ro shading vẫn phải QA

- Relocation thay bytecode references và tên entry class, nhưng những class names dùng ở **strings/reflection** có thể không được cập nhật theo cách bạn nghĩ.
- Resource names trong `META-INF/services`, framework metadata hoặc provider declarations có thể cần resource transformers riêng.
- Signed artifacts có chữ ký cũ không còn phù hợp sau khi merge, nên cấu hình ví dụ loại bỏ signature metadata. Kiểm soát supply-chain phải được thực hiện **trước đóng gói** và trên artifact phát hành mới.
- Không relocate public packages mà API của agent muốn chia sẻ cho ứng dụng, trừ khi có chiến lược compatibility rõ ràng.
- Không áp dụng `minimizeJar` nếu công cụ không phân tích được class dùng qua reflection hoặc dynamic class loading.
- Nếu đóng gói agent thành multi-release JAR hoặc gắn vào modular application, kiểm tra manifest/resources/classfile versions ở **final JAR**, không chỉ output `target/classes`.

### 10.4. Bootstrap class loader không tự thấy mọi helper

Nếu transformer chèn lời gọi tới helper class nằm trong agent JAR, class được instrument có thể được nạp bởi class loader **không thấy helper**. Đặc biệt nếu instrument lớp bootstrap, việc gọi helper từ system classloader không phải lúc nào cũng hợp lệ.

Các cách xử lý gồm:

- Thiết kế probe chỉ gọi API có sẵn trong bootstrap module khi đủ (như demo).
- Cấp một helper JAR tối giản cho bootstrap bằng `Instrumentation.appendToBootstrapClassLoaderSearch` theo hợp đồng API, với kiểm soát signed JAR, dependencies và package boundaries.
- Dùng `Instrumentation.redefineModule` để bổ sung read/export/open edges khi thực sự cần module accessibility; phương thức này không thay đổi vị trí class loader và không tự làm helper class xuất hiện.
- Đặt helper vào một loader mà cả target và agent có thể liên kết hợp lệ.

**Đừng đưa toàn bộ parser/ASM/Jackson/logging stack vào bootstrap chỉ vì tiện**. Điều đó mở rộng coupling và có thể gây lỗi class loading ở thời điểm JVM đang khởi tạo.

## 11. Public Class-File API của JDK 24+: không dùng JDK internal

Từ **JDK 24**, `java.lang.classfile` là một API công khai của Java platform để parse, generate và transform classfiles. Nó được chuẩn hóa bằng **JEP 484**, sau các giai đoạn preview trong JDK 22 (JEP 457) và JDK 23 (JEP 466).

Các loại có tài liệu chính thức:

- `java.lang.classfile.ClassFile`: context parse/build/transform.
- `java.lang.classfile.ClassModel`: mô hình class đã được parse.
- `java.lang.classfile.ClassTransform`: biểu diễn phép transform.
- `ClassFile.of()`: tạo context.
- `ClassFile.parse(...)`: parse class bytes.
- `ClassFile.transformClass(...)`: tạo class bytes từ transformation.
- `ClassFile.verify(...)`: kiểm tra class bytes theo API.

**Ràng buộc quan trọng:** code liên kết tới `java.lang.classfile` **không chạy trên Java 17/21** vì package này chưa có ở những runtime đó. Nếu agent phải hỗ trợ 17/21, dùng ASM/Byte Buddy phù hợp hoặc phát hành artifact riêng/multi-release có dispatch được thiết kế và kiểm thử.

### 11.1. Ví dụ thực tế không cần ASM

Tệp **`Sample.java`**:

~~~java
public final class Sample {
    public static int twice(int input) {
        return input * 2;
    }
}
~~~

Tệp **`PublicClassfileDemo.java`**, chạy trên **JDK 24+**:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PublicClassfileDemo {
    public static void main(String[] args)
            throws Exception {
        ClassFile api = ClassFile.of();
        ClassModel model = api.parse(
                Files.readAllBytes(Path.of(args[0])));

        byte[] copy = api.transformClass(
                model, ClassTransform.ACCEPT_ALL);

        System.out.println(
                "name=" + model.thisClass().asInternalName());
        System.out.println(
                "major=" + model.majorVersion());
        System.out.println(
                "copy-valid=" + api.verify(copy).isEmpty());
    }
}
~~~

Chương trình này sử dụng **pass-through transform** `ClassTransform.ACCEPT_ALL` để minh họa API public và kiểm tra classfile được tạo; **không tự chèn probe vào method**. Muốn instrument thực tế, phải cung cấp `ClassTransform`/`MethodTransform`/`CodeTransform` phù hợp, quản lý stack maps và kiểm chứng kết quả.

### 11.2. Build và run trên JDK 24+

Tạo hai output directories:

~~~bash
mkdir -p out17 out24
~~~

Build:

~~~bash
javac --release 17 -d out17 Sample.java
javac -d out24 PublicClassfileDemo.java
java -Xverify:all -cp out24 PublicClassfileDemo out17/Sample.class
~~~

**Stdout đã kiểm thử trên JDK 24.0.2:**

~~~text
name=Sample
major=61
copy-valid=true
~~~

Giải thích: `Sample.class` được build Java 17, nên classfile major **61**; JDK 24 API công khai đọc và tạo lại một classfile hợp lệ. **Không đồng nhất việc đọc classfile 17 bằng tool JDK 24 với việc chạy tool đó trên JVM 17**.

### 11.3. Không ép --release 17 cho code import java.lang.classfile

Nếu `PublicClassfileDemo.java` import `java.lang.classfile`, biên dịch trên JDK 24 bằng `javac --release 17 ...` sẽ **không thành công**: `--release 17` giới hạn API đến Java SE 17, và `java.lang.classfile` chưa là API của release ấy.

Chỉ chọn công nghệ sau khi đã đặt ra **runtime minimum**. Một artifact agent compile ở Java 24 thường có classfile major **68**, JVM 17 không thể load trực tiếp. Nếu cần chạy trên 17 và 24, cách đơn giản nhất là dùng **agent ASM build target 17** như ở mục 6–9; chỉ cân nhắc multi-release packaging khi thực sự có giá trị và đội vận hành có khả năng kiểm thử mọi biến thể.

## 12. Tương thích phiên bản Java và classfile major

| JVM đích | Classfile major tối đa thông thường | Public Class-File API? | Cách triển khai nên cân nhắc |
|---|---:|---|---|
| Java 17 | 61 | Không | `java.lang.instrument` + ASM/Byte Buddy được đóng gói |
| Java 21 | 65 | Không | `java.lang.instrument` + ASM/Byte Buddy tương thích bytecode 65 |
| Java 24 | 68 | Có, chuẩn từ 24 | Có thể dùng `java.lang.classfile` hoặc ASM/Byte Buddy được hỗ trợ |
| Java mới hơn | Phụ thuộc release | Có nếu vẫn trong supported API | Kiểm tra classfile major mới, library support và compatibility matrix |

Cần phân biệt ba thứ:

1. **Source/API release của agent:** `--release 17` hay `--release 24` quyết định bytecode của agent và các APIs có thể gọi.
2. **Classfile major của class đích:** app target Java 24 có thể tạo classfile major 68 mà ASM cũ không hiểu, dù agent chạy trên JVM 24.
3. **JVM chạy agent:** phải load được bytecode của chính agent và mọi dependency shaded; classfile target thấp hơn **không tự bảo đảm** library xử lý bytecode hỗ trợ định dạng classfile của JVM mới.

Version của **ASM library** và hằng `Opcodes.ASM9` cũng là hai khái niệm khác nhau. `Opcodes.ASM9` là mức API visitor, không phải yêu cầu ASM artifact version `9.0` hoặc classfile major 9.

### 12.1. Khi nào có ý nghĩa dùng multi-release agent JAR?

Một `Multi-Release: true` JAR có thể chứa implementation tối ưu theo runtime version, nhưng muốn kết hợp base agent Java 17 với code Java24 Class-File API cần:

- entry point agent của base JAR vẫn load được trên JVM 17;
- những class Java24 chỉ được load khi runtime version phù hợp;
- `META-INF/versions/24/...` được đóng gói đúng quy tắc multi-release JAR;
- không vô tình để base classes có constant pool references tới `java.lang.classfile`, gây lỗi link trên Java 17;
- test đúng matrix Java17, 21, 24+ và cả Java class loaders/module layer.

**Đây là một lựa chọn phức tạp, không phải yêu cầu mặc định.** Nếu chỉ cần một agent cho Java 17+, dùng ASM phù hợp thường đơn giản hơn và dễ kiểm soát hơn.

## 13. Kiểm chứng artifact chứ không chỉ code source

### 13.1. Quy trình kiểm tra tối thiểu

~~~text
Source và POM
    |
    +--> scan imports; jdk.internal.* có xuất hiện không?
    |
    +--> xác minh version dependency, license, checksum/policy
    |
Build --release 17
    |
    +--> Maven Shade tạo agent JAR với manifest chính xác
    |
    +--> jar tf kiểm tra relocated dependencies
    |
    +--> jdeps --jdk-internals trên artifact cuối
    |
Integration Test
    |
    +--> JVM 17/21/24 trong support matrix
    +--> -Xverify:all
    +--> đã chạy target application thật
    +--> telemetry, classloader, module edge, overhead
    |
Release
    |
    +--> immutable artifact + checksum/SBOM + rollback
~~~

Nếu build có agent và app khác repositories, CI nên gắn version rõ ràng cho **agent artifact**, **target Java releases** và **external bytecode libraries**. Một agent sinh bytecode hợp lệ trên Java17 chưa chắc nhận đúng mọi classfile trên Java24 nếu ASM version quá cũ.

### 13.2. Quét source và binary

Mẫu command từ project root trên hệ thống có `grep`:

~~~bash
grep -R -n -E 'jdk[.]internal[.]org[.]objectweb[.]asm|sun[.]misc|com[.]sun[.]tools[.]javac' src
~~~

Lệnh này tìm **dấu hiệu cần review**, không có nghĩa mọi trùng khớp đều chắc chắn là unsupported API trong cùng một ngữ cảnh. Trên Windows PowerShell có thể dùng:

~~~powershell
Get-ChildItem -Path src -Recurse -File -Include *.java |
    Select-String -Pattern 'jdk\.internal\.org\.objectweb\.asm|sun\.misc|com\.sun\.tools\.javac'
~~~

Sau build:

~~~bash
jdeps --jdk-internals target/safe-asm-agent-1.0.0.jar
jar tf target/safe-asm-agent-1.0.0.jar
~~~

Nếu `jdeps` báo phụ thuộc `jdk.internal.org.objectweb.asm`, phải truy ra **source hoặc transitive dependency** tạo reference đó, rồi thay/sửa ngay trong build, không chỉ giấu lỗi bằng launcher flag.

### 13.3. Dependency report và reproducibility

~~~bash
mvn dependency:tree
mvn -q -DskipTests package
~~~

Báo cáo dependency tree giúp xác định ASM/Byte Buddy versions đang được kéo vào, nhưng cuối cùng phải kiểm tra **artifact đã shaded** vì nó mới là JAR triển khai thực tế.

Trong CI, nên khóa repository mirror, kiểm chứng checksums, lưu SBOM/license inventory, chạy security scanning và lưu checksum artifact. Nếu có signing, phải ký artifact **sau** bước shading/relocation. Phải test đúng file JAR sẽ phát hành, không chỉ thư mục `target/classes`.

## 14. Hạn chế và lỗi phổ biến

| Triệu chứng | Nguyên nhân cần xem | Hướng giải quyết |
|---|---|---|
| `package jdk.internal... is not visible` lúc compile | Import JDK internal ASM bị JPMS chặn | Đổi sang `org.objectweb.asm` chính thức; không dùng flag làm chiến lược lâu dài |
| `IllegalAccessError` lúc chạy agent | Link tới package nội bộ nhưng JVM không export | Loại bỏ JDK internal dependency; flag chỉ để test migration |
| `InaccessibleObjectException` khi reflection | Package/module không open cho caller | Kiểm tra reflection thật sự cần hay không; dùng API public hoặc module access tối thiểu |
| `NoClassDefFoundError: org/objectweb/asm/...` | ASM chưa được đóng gói vào agent JAR | Kiểm tra `mvn package`, `jar tf` và dependency scopes |
| `NoClassDefFoundError` với package shaded | Relocation/transformer/manifest hay class loader sai | Kiểm tra package sau shade, references trong bytes và resource paths |
| `NoSuchMethodError` trong ASM/Byte Buddy | Runtime nạp version library khác version compile | Relocate, pin version, kiểm tra loader resolution và final JAR |
| `Unsupported class file major version` | Bytecode library không nhận classfile mới | Nâng library release phù hợp và test trên runtime đích |
| `UnsupportedClassVersionError` | Agent/dependency classfile compiled cho JVM mới hơn | Build `--release` phù hợp runtime minimum |
| `VerifyError` / `ClassFormatError` | Transformer sinh bytecode hoặc frames sai | Test `-Xverify:all`, method signature, stack maps, control flow |
| `ClassCircularityError` hoặc startup treo | Transformer làm nạp class/ASM/helper theo vòng phụ thuộc | Lọc class chặt, tránh self-instrument và work nặng trong callback |
| JVM báo thiếu `Premain-Class` | Manifest bị mất hoặc shade ghi sai | Xem `META-INF/MANIFEST.MF` của final agent JAR |
| Có `Premain-Class` nhưng ASM không hoạt động | Agent không bắt kịp class loading, filter class name sai | Kiểm tra `-javaagent` trước app, callback, loader và target `demo/Service` |
| `UnsupportedOperationException` khi retransform | Chưa có capability hoặc đổi schema không được hỗ trợ | Kiểm tra manifest/`isRetransformClassesSupported` và target structure |
| Agent chạy trên 24, thất bại trên 17 | Code dùng `java.lang.classfile` hoặc build target 24 | Dùng public external ASM target17 hoặc artifact variant riêng |
| Scan `jdeps` không báo nhưng runtime reflection nội bộ vẫn lỗi | Reflection/dynamic names không được phát hiện bằng static analysis | Quét strings, cấu hình, integration tests và runtime logs |

**Phải phân loại lỗi trước khi sửa:** compile-time module export, runtime access control, missing shaded dependency, classfile major incompatibility và invalid transformed bytecode **là các nguyên nhân khác nhau**. Đừng áp `--add-opens` cho tất cả những lỗi này.

### 14.1. Kiểm tra manifest trước khi nghi ngờ ASM

Một JAR chỉ có `demo.Agent.class` mà thiếu `Premain-Class` sẽ **không được JVM khởi chạy như Java agent**. Trường hợp này không liên quan ASM. Dùng `jar tf` và trích manifest, sau đó kiểm tra tên entry `demo.Agent` và public static method `premain(String, Instrumentation)` trong source.

### 14.2. Phân biệt exception từ chính agent với exception của app

Transformer có thể ném exception/return invalid bytes; tùy giai đoạn, JVM có thể tiếp tục những transformers khác hoặc từ chối class definition. Một probe cố tình chèn `println` quá sớm vào bootstrap/core class có thể gây class loading recursion. Hãy đặt filter chặt và coi error handling của transformer là thành phần quan trọng của deployment.

## 15. Những tình huống mở rộng

### 15.1. Application đã có ASM riêng

Nếu app dùng ASM phiên bản cũ để generate proxy, còn agent dùng ASM phiên bản mới, **không cho rằng chỉ vì class names giống thì hai phiên bản tương thích**. Package relocation trong agent giúp giảm xung đột nhưng không giải quyết mọi vấn đề nếu agent tự chèn reference tới shaded ASM vào class ứng dụng.

**Thiết kế đúng:** ASM là **công cụ xây class bytes bên trong agent**, còn bytecode được chèn vào target ưu tiên chỉ gọi **public Java APIs hoặc helper có loader visibility rõ ràng**. Không để app method vô tình phụ thuộc trực tiếp ASM parser của agent.

### 15.2. Multiple agents

JVM có thể nạp nhiều agents bằng nhiều `-javaagent`. Mỗi transformer có lifecycle và thứ tự riêng. Một agent dùng ASM shaded tránh làm hỏng dependency của agent khác, nhưng **transformed bytes vẫn được các transformers xử lý theo pipeline**. Tránh chèn cùng một probe nhiều lần; cần idempotence, markers và phân quyền class targets.

### 15.3. Classloader và JPMS

Agent JAR chạy trong JVM không có nghĩa mọi class đích đều nhìn thấy classes của agent. Để tránh `IllegalAccessError`, `NoClassDefFoundError` hoặc module resolution failures:

- kiểm tra `ClassLoader` và `Module` của target trong callback;
- tránh inject helper references nếu helper không accessible;
- chỉ mở `reads`/`exports`/`opens` khi thật sự cần;
- không dùng JDK internal classes như cách “né” lỗi classloader;
- không tự ý sửa boot module `java.base` hoặc deploy shaded ASM vào package `java.*`.

### 15.4. Tests trên JDK khác vendors

API công khai giúp giảm rủi ro nhưng không thay thế việc test. Các JVM vendors và minor updates có thể có khác biệt performance, classloading và classfile support. Đặt support matrix rõ: Java 17, 21, 24+ nếu đó là các runtime tổ chức sử dụng. Cập nhật agent khi library xử lý bytecode chưa hỗ trợ classfile version mới.

## 16. Bài tập tự luyện

### Bài tập A — tìm lỗi dependency

Code agent import `jdk.internal.org.objectweb.asm.ClassReader` và dùng `--add-exports` ở CI. Hãy giải thích ba rủi ro khi deploy lên một JVM không có flag và khi nâng JDK.

**Đáp án:** runtime có thể báo `IllegalAccessError`; API internal không có compatibility contract; build/runtime gắn chặt vào flags và version nội bộ.

### Bài tập B — đổi import nhưng chưa sửa đóng gói

Bạn thay thành `org.objectweb.asm.ClassReader`, Maven compile thành công, nhưng production agent báo `NoClassDefFoundError: org/objectweb/asm/ClassReader`. Lỗi ở đâu?

**Đáp án:** thư viện không có ở runtime loader. Cần đóng gói ASM (hoặc cấu hình classpath/loader hợp lệ); thử shade/relocation và `jar tf` trên final artifact.

### Bài tập C — so sánh shade và relocate

Vì sao chỉ gom `asm.jar` vào uber JAR có thể vẫn gặp conflict nếu app cũng có `org.objectweb.asm.*`? Relocation `org.objectweb.asm -> demo.agent.shaded.asm` giúp gì? Nó có làm app tự tìm thấy mọi helper của agent không?

**Đáp án:** class binary names vẫn trùng nếu không relocate. Đổi namespace giúp tách dependency; nhưng **không tự giải quyết** helper visibility/module access hoặc resource names.

### Bài tập D — kiểm chứng tác động probe

Chạy `safe-asm-agent` ở mục 6–9 **có** và **không có** `-javaagent`. So sánh stdout. Vì sao chỉ thêm một dòng `agent:enter-hello` và `result=hello` vẫn giữ nguyên?

### Bài tập E — thử scan JDK internals

Compile `InternalAsmDemo` với `--add-exports` rồi chạy `jdeps --jdk-internals`. Giải thích vì sao build success không đủ để kết luận là API được hỗ trợ. Sau đó bỏ import internal và quét lại artifact.

### Bài tập F — chọn JDK24 Class-File API

Dùng `PublicClassfileDemo` parse `Sample.class` Java17 major61. Nếu cố compile chính tool `PublicClassfileDemo` với `--release 17`, dự đoán kết quả và giải thích dựa trên API availability.

### Bài tập G — thử thay đổi control flow

Dùng ASM mở rộng transformer để thêm branch hoặc exception handler. Vì sao cấu hình chỉ `COMPUTE_MAXS` ở demo có thể không đủ? Hãy thử `COMPUTE_FRAMES` với một hierarchy resolver nhìn thấy đúng target classes, rồi kiểm tra `-Xverify:all` và cả các exception paths.

### Bài tập H — lập support matrix

Agent phải chạy trên Java 17 và 24, target classfiles có major61 hoặc68. Hãy định nghĩa phiên bản ASM hỗ trợ cả hai, build target release17, test JVM17/24, và quy trình xử lý nếu xuất hiện classfile major mới. Không quyết định chỉ dựa vào Java version của máy CI.

### Câu hỏi kiểm tra

1. **Import `jdk.internal.org.objectweb.asm` là supported API không?** — Không.
2. **Import `org.objectweb.asm` có được JDK cung cấp như Java SE API không?** — Không; đây là thư viện bên ngoài, phải quản lý dependency.
3. **Dùng `--add-exports` có biến JDK internal class thành API public không?** — Không.
4. **Lệnh nào phát hiện phụ thuộc JDK internal tĩnh?** — `jdeps --jdk-internals`.
5. **Java SE public API cho instrumentation là gì?** — `java.lang.instrument`.
6. **Class-File API công khai được finalized từ release nào?** — JDK 24.
7. **Dùng `java.lang.classfile` trên Java 17 được không?** — Không.
8. **Shading và relocation có giống nhau không?** — Không; một cái gom dependencies, một cái đổi namespace.
9. **Vì sao cần kiểm tra final JAR?** — Vì shading/manifest/packaging có thể làm artifact khác kết quả compile.
10. **`-Xverify:all` chứng minh mọi thứ chạy production sẽ đúng không?** — Không; cần test classloader, behavior, concurrency, performance và runtime matrix.

## 17. Checklist release và kết luận

### Trước khi build

- [ ] Không có import/bytecode references không chủ đích tới `jdk.internal.org.objectweb.asm` và JDK private packages.
- [ ] Dùng `java.lang.instrument` để nhận transformer/Instrumentation.
- [ ] Nếu cần parser cho Java17/21, khai báo ASM/Byte Buddy chính thức với version tương thích classfile major.
- [ ] Nếu dùng `java.lang.classfile`, xác định **runtime tối thiểu JDK 24**.
- [ ] Pin dependencies và kiểm chứng supply-chain/source/license/patch policy.
- [ ] Đặt `maven.compiler.release` theo **JVM thấp nhất** phải hỗ trợ.

### Khi đóng gói

- [ ] Đảm bảo agent JAR có `Premain-Class` và/hoặc `Agent-Class` tùy entry point thực sự triển khai.
- [ ] Đóng gói ASM/Byte Buddy runtime dependencies vào agent hoặc cấu hình loader chính xác.
- [ ] Relocate dependency packages có nguy cơ trùng, tránh namespace `jdk.internal.*`/`java.*`.
- [ ] Kiểm tra resource transformers, service metadata và signatures sau shading.
- [ ] Không dùng `minimizeJar` nếu chưa kiểm chứng reflection/ServiceLoader/bootstrap.
- [ ] Kiểm tra final `jar tf`, manifest và `jdeps --jdk-internals`.

### Trước khi phát hành

- [ ] Chạy agent trên JVM thực trong support matrix, không chỉ máy build.
- [ ] Chạy `-Xverify:all` trong test và kiểm tra transformed class bytes.
- [ ] Xác nhận probe thêm đúng điểm, không thay business return/exception behavior.
- [ ] Kiểm tra khác biệt giữa startup agent và attach agent nếu hỗ trợ cả hai.
- [ ] Kiểm tra classloader/module visibility và bootstrap instrumentation.
- [ ] Thử ứng dụng có dependency ASM khác version và nhiều agents.
- [ ] Kiểm tra rollback, logging, overhead, JIT/GC/latency khi enable agent.
- [ ] Gắn artifact checksum, release notes, SBOM và hướng dẫn chạy rõ ràng.

**Kết luận:** một Java agent có thể dùng các API chính thức của JDK để nhận bytecode, kết hợp **thư viện xử lý bytecode được quản lý độc lập** (OW2 ASM/Byte Buddy), rồi đóng gói dependencies đúng cách. Không lấy việc JDK có bản ASM nội bộ làm lý do phụ thuộc vào `jdk.internal.org.objectweb.asm`. Với JDK 24+, `java.lang.classfile` là lựa chọn chuẩn công khai; với Java17/21, dùng thư viện ngoài có release rõ và build target phù hợp.

**Ba phép kiểm tra phải thực hiện:** (1) build không cần `--add-exports` nội bộ; (2) artifact cuối không chứa static references tới JDK internal APIs; (3) agent JAR chạy với `-Xverify:all` và output đúng trên JVM đích. Đây là nền tảng để triển khai instrumentation ổn định, thay vì dựa vào implementation details có thể đổi mà không báo trước.

### Tài liệu chính thức và nguồn tiếp theo

- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent JAR, `-javaagent`, `premain`, `agentmain`, manifest capabilities.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký transformer, class retransform/redefine, bootstrap class loader support và module graph.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback và quy tắc trả transformed bytes.
- [Oracle JDK Migration Guide — JDK internal APIs / jdeps](https://docs.oracle.com/en/java/javase/20/migrate/migrating-jdk-8-later-jdk-releases.html): strong encapsulation, migration và hướng phát hiện JDK internal.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module encapsulation và `--add-exports`/`--add-opens`.
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484): API chuẩn hóa trong JDK24.
- [Java SE 24 — java.lang.classfile.ClassFile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): parse/transform/generate và `ClassFile.of()`.
- [OW2 ASM](https://asm.ow2.io/): thư viện public và release/documentation chính thức.
- [Apache Maven Shade — Relocating Classes](https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html): lý do relocate và cấu hình package mang dependency.
- [Byte Buddy](https://bytebuddy.net/): framework bytecode manipulation/instrumentation ở mức abstraction cao hơn.
