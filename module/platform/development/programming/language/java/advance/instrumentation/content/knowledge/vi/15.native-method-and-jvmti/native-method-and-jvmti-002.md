# Bọc native bằng phương thức Java khi định nghĩa lớp lần đầu

Một phương thức Java khai báo **native** không có **Code attribute** chứa JVM instructions, nên không thể đặt trực tiếp lời gọi đo thời gian, tracing hoặc logging vào phần thân method ấy bằng ASM AdviceAdapter. Muốn đo **lời gọi đi từ Java sang native**, một Java agent có thể biến đổi class file **ở thời điểm JVM định nghĩa lớp lần đầu**, tạo một **Java wrapper không native** giữ tên/descriptor gốc và đổi tên native declaration bằng prefix riêng. Wrapper chứa bytecode ghi nhận rồi gọi native đã đổi tên.

Tuy nhiên, đổi tên native method gây ra câu hỏi: **thư viện JNI C/C++ hiện có làm sao được liên kết**, nếu nó export tên cũ như **Java_demo_NativeMath_add** chứ không export tên mới? Java Instrumentation có **Instrumentation.setNativeMethodPrefix(...)**, cho phép JVM thử lại native method resolution bằng cách xét một prefix do transformer đăng ký.

Mục tiêu bài học là hiểu cơ chế và giới hạn của **native wrapping lúc initial class definition**, phân biệt Java Instrumentation với **JNI** và **JVM TI**, đồng thời triển khai demo Java 17 + JNI C + ASM. Đây **không phải** kỹ thuật thay implementation C/C++ hay cơ chế thêm method vào bất kỳ lớp đã load nào bằng retransformation.

## 1. Phân biệt native method và Java method

~~~java
// Code nguồn của ứng dụng.
public static native int add(int a, int b);
~~~

Class file ghi cờ **ACC_NATIVE** và một method descriptor, ví dụ **(II)I** (nhận hai int, trả int). Native declaration **không có Java Code attribute**. Trong khi đó method Java bình thường:

~~~java
public static int addJava(int a, int b) {
    return a + b;
}
~~~

có **Code attribute** và các instruction như ILOAD, IADD, IRETURN. ClassFileTransformer có thể biến đổi bytes class file, nhưng không thể “chèn ILOAD vào Code của native method” khi không có Code.

| Đặc tính | Java method thông thường | Native method |
| --- | --- | --- |
| ACC_NATIVE | Không | Có |
| Code attribute | Có, với method có body | Không |
| JVM instructions biểu diễn thân method | Có | Không |
| ASM AdviceAdapter chèn vào method body | Có thể | Không trực tiếp |
| Đường thực thi | JVM/interpreter/JIT | JNI/native implementation |
| Điểm đo Java phù hợp | Chèn advice vào Code | Tạo **Java wrapper** rồi gọi native |
| Tính tương thích JNI symbol | Không có native resolution | Phải phân giải đúng native implementation |

Nếu vừa giữ **ACC_NATIVE** vừa thêm Code attribute vào **cùng một method**, class file không hợp lệ. Nếu bỏ ACC_NATIVE mà không tạo Code hợp lệ cho method Java, class file cũng có thể bị từ chối. Đúng hơn là **hai method khác nhau**, một native declaration và một Java wrapper.

## 2. Mô hình trước và sau biến đổi

Ban đầu:

~~~java
// Source ban đầu: demo.NativeMath
public static native int add(int a, int b);
~~~

Sau khi transformer xử lý class file ở initial load, JVM thấy cấu trúc tương đương:

~~~java
// Mô hình Java để giải thích; không phải source được compiler sửa.
public static int add(int a, int b) {
    recordEnter();
    int value = $$$DemoNative$$_add(a, b);
    recordExit();
    return value;
}

public static native int $$$DemoNative$$_add(int a, int b);
~~~

Trong đó:

- **add(II)I** vẫn là API mà caller đã biên dịch và gọi. Nhưng giờ nó là **Java method có Code**, không phải native.
- **$$$DemoNative$$_add(II)I** là native declaration mới với cùng descriptor, nên vẫn có thể dẫn tới code C gốc.
- **setNativeMethodPrefix(transformer, "$$$DemoNative$$_")** cho JVM biết cách retry native resolution khi tên mới không tìm thấy implementation theo quy tắc thông thường.
- **recordEnter/recordExit** có thể là event/metric/tracing code. Trong demo, ta in ra console để dễ chứng minh.
- Nếu native call ném Throwable, lệnh recordExit nằm **sau invocation** không chạy; để ghi cả exceptional exit phải dựng handler Java riêng và rethrow đúng Throwable.

Sơ đồ:

~~~text
App.main
   |
   v
NativeMath.add(2,3)       <- wrapper Java mới
   |
   +-- WRAP_ENTER
   |
   +-- $$$DemoNative$$_add(2,3)  <- native method có tiền tố
                |
                v
           JVM JNI resolution
                |
                +-- thử symbol theo tên mới
                |
                +-- nếu không thấy: native-prefix fallback
                |
                v
           Java_demo_NativeMath_add(JNIEnv*, jclass, jint, jint)
                |
                v
             return 5
   |
   +-- WRAP_EXIT
   |
   v
RESULT=5
~~~

Điểm đo Java có thể quan sát **thời gian quanh lời gọi native**, nhưng không tự thấy instruction C, malloc/native heap, native locks hay chi tiết JNI functions bên trong. Muốn đo nội bộ native cần native profiler, JVMTI hoặc instrumentation C/C++ phù hợp.

## 3. Vì sao phải tạo wrapper ngay khi lớp được định nghĩa?

Khi **ClassFileTransformer** nhận bytes trong **lần định nghĩa lớp đầu**, JVM chưa cài method schema của class đó. Transformer được phép đề xuất một class file hợp lệ chứa:

1. Native method gốc đã **đổi tên**.
2. Một Java method **mới** có tên và descriptor gốc.
3. Code bytecode để ghi nhận và gọi prefixed native.

Tức là có **thay đổi cấu trúc class**.

**retransformClasses** và **redefineClasses** đối với class đã load có giới hạn quan trọng về việc thêm/xóa/đổi tên methods, fields và những phần schema khác. Không thể mặc định attach agent lúc ứng dụng đã chạy rồi retransform một native method đã load thành hai methods. Một số loại instrumentation trên Code của method Java đã tồn tại vẫn được hỗ trợ, nhưng **native wrapper cần method mới và đổi tên method native** là trường hợp khác.

Timeline chính xác:

~~~text
JVM -javaagent:... khởi động
   |
   v
premain(agentArgs, Instrumentation)
   |
   +-- kiểm tra isNativeMethodPrefixSupported()
   +-- addTransformer(t, false)
   +-- setNativeMethodPrefix(t, PREFIX)
   |
   v
Ứng dụng bắt đầu dùng demo.NativeMath
   |
   v
ClassFileTransformer.transform(...) ở initial definition
   |
   +-- match className / method descriptor / ACC_NATIVE
   +-- rename native add -> PREFIX + add
   +-- add Java method add() chứa Code
   +-- return byte[] class file mới
   |
   v
JVM verify/link/define class
   |
   v
NativeMath.add() gọi wrapper -> prefixed native -> C implementation
~~~

Đăng ký **trước khi class đích load** là điểm then chốt. Nếu mã premain hoặc dependency agent vô tình gọi NativeMath trước khi đăng ký transformer, cơ hội tạo wrapper ở initial load đã qua. Không nên đưa application target class vào agent JAR rồi dùng nó ngay trong premain.

**Cảnh báo:** ClassFileTransformer cũng có thể được gọi khi redefine/retransform; ví dụ bên dưới chỉ hỗ trợ initial definition và chủ động bỏ qua khi **classBeingRedefined != null**. Khi class đã load, không cố trả bytes thêm method mới.

## 4. Native method prefix: capability và thứ tự đăng ký

Hai API Java SE 17 cần biết:

~~~java
// Chữ ký từ java.lang.instrument.Instrumentation.
boolean isNativeMethodPrefixSupported();

void setNativeMethodPrefix(
        ClassFileTransformer transformer, String prefix);
~~~

**Native-prefix capability là tùy chọn**, được JVM cung cấp nếu manifest agent yêu cầu **Can-Set-Native-Method-Prefix: true** và JVM hỗ trợ. Manifest thiếu thuộc tính này thường khiến **isNativeMethodPrefixSupported()** trả false.

Trình tự code đúng:

~~~java
// Đoạn minh họa trong premain, không phải file độc lập.
if (!inst.isNativeMethodPrefixSupported()) {
    throw new IllegalStateException(
        "Native method prefix unsupported");
}

ClassFileTransformer transformer = new NativeWrapTransformer();
inst.addTransformer(transformer, false);
inst.setNativeMethodPrefix(transformer, "$$$DemoNative$$_");
~~~

**setNativeMethodPrefix** phải nhận **transformer đã được đăng ký**, nếu không có thể ném **IllegalArgumentException**. Nếu transformer là null, có thể ném **NullPointerException**; nếu capability không được cấp, **UnsupportedOperationException**. Prefix rỗng/null không giúp retry native resolution bằng prefix cho transformer đó.

Một prefix như **wrapped_** rất dễ đụng tên method sẵn có; dùng tên riêng cho agent, ví dụ **$$$DemoNative$$_**. Prefix phải **trùng khớp từng ký tự** giữa tên native declaration do transformer tạo và argument của setNativeMethodPrefix.

### 4.1. Prefix không tự tạo method

Chỉ gọi setNativeMethodPrefix mà không thực sự biến đổi class file **không tạo wrapper** và không thay native method. Transformer vẫn cần nhận classfileBuffer, ghi class file hợp lệ và return một **byte[] mới**. Nếu class không đúng phạm vi, **return null**.

### 4.2. JNI resolution: automatic và RegisterNatives

Theo JNI, JVM có thể tìm native implementation bằng:

- **Automatic native method resolution**: tìm symbol theo class/method name đã escape, ví dụ **Java_demo_NativeMath_add**.
- **RegisterNatives**: native library chủ động gắn method name + descriptor với con trỏ C function.

Javadoc **setNativeMethodPrefix** quy định fallback cho **cả hai** đường:

- Automatic: JVM thử symbol của prefixed native method; nếu không tìm thấy, có thể thử lại với prefix được bỏ khỏi tên implementation đang tìm.
- RegisterNatives: khi association theo tên gốc không tìm ra declaration tương ứng sau khi đổi tên, JVM có thể thử lại association dùng method name đã thêm prefix.

Bởi vậy thư viện C có thể tiếp tục export **Java_demo_NativeMath_add**, còn Java declaration được đổi thành **$$$DemoNative$$_add**. Cơ chế này chỉ dùng khi normal resolution thất bại, nên có thể **bọc chọn lọc** một số native methods.

**Không bảo đảm mọi thư viện JNI bên thứ ba tự động tương thích**: có thư viện tự gọi GetMethodID, dùng đăng ký native động, bootstrap class loader khác hoặc có metadata/native symbol đặc biệt. Test trên native library và JDK mục tiêu là cần thiết.

## 5. Bài thực hành: Java 17 + JNI C + ASM

Ta tạo một chương trình hoàn chỉnh có native method **demo.NativeMath.add(int,int)**, C implementation trả tổng hai số, và Java startup agent dùng ASM biến method native thành wrapper. Không có thư viện bytecode nào trong **application**; ASM chỉ thuộc **agent**.

Kết quả cần chứng minh:

- **Không agent**: JNI hoạt động, output **RESULT=5**.
- **Có agent**: console in **AGENT_PREFIX_READY**, **AGENT_WRAPPED**, **WRAP_ENTER**, **WRAP_EXIT**, và cuối cùng vẫn **RESULT=5**.
- Tên JNI symbol C gốc **không thay đổi**.

### 5.1. Cấu trúc thư mục

~~~text
nativewrap-demo/
  pom.xml
  src/
    agent/
      java/
        demo/
          NativeAgent.java
    app/
      java/
        demo/
          NativeMath.java
          App.java
    native/
      nativeops.c
  out/
    app/             <-- do javac tạo
    include/         <-- JNI header do javac -h tạo
  target/
    nativewrap-agent.jar  <-- do Maven Shade tạo
~~~

Tách code application ra khỏi agent để **demo.NativeMath không vô tình được define trước thời điểm transformer được đăng ký**.

### 5.2. File src/app/java/demo/NativeMath.java

~~~java
package demo;

public final class NativeMath {
    static {
        System.loadLibrary("nativeops");
    }

    private NativeMath() {
    }

    public static native int add(int a, int b);
}
~~~

**System.loadLibrary("nativeops")** nạp thư viện theo tên nền tảng: Linux **libnativeops.so**, macOS **libnativeops.dylib**, Windows **nativeops.dll**. Nó không tự biên dịch C. Class initializer chạy trước lần gọi native method đầu tiên.

### 5.3. File src/app/java/demo/App.java

~~~java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("RESULT=" + NativeMath.add(2, 3));
    }
}
~~~

Class NativeMath chưa được dùng trong premain nên khi main bắt đầu và thực thi lời gọi, transformer đã sẵn sàng.

### 5.4. File src/native/nativeops.c

~~~c
#include "demo_NativeMath.h"

JNIEXPORT jint JNICALL Java_demo_NativeMath_add(
        JNIEnv* env, jclass owner, jint a, jint b) {
    (void) env;
    (void) owner;
    return a + b;
}
~~~

Header **demo_NativeMath.h** được sinh bằng **javac -h** từ declaration gốc. Vì method **static**, JNI tham số thứ hai là **jclass**. Instance native method dùng **jobject** ở vị trí đó. **JNIEnv*** gắn với thread, không được lưu rồi tái sử dụng tùy tiện ở thread khác.

C function vẫn tên **Java_demo_NativeMath_add**, không đổi thành symbol mang tiền tố. Phần prefix fallback của JVM làm nhiệm vụ liên kết.

### 5.5. File src/agent/java/demo/NativeAgent.java

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

public final class NativeAgent {
    private static final String PREFIX = "$$$DemoNative$$_";

    private NativeAgent() {
    }

    public static void premain(String args, Instrumentation inst) {
        if (!inst.isNativeMethodPrefixSupported()) {
            throw new IllegalStateException(
                    "Native prefix unsupported");
        }

        ClassFileTransformer t = new NativeWrapTransformer();
        inst.addTransformer(t, false);
        inst.setNativeMethodPrefix(t, PREFIX);
        System.out.println("AGENT_PREFIX_READY");
    }

    private static final class NativeWrapTransformer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer) {

            if (!"demo/NativeMath".equals(className)
                    || classBeingRedefined != null) {
                return null;
            }

            ClassReader reader = new ClassReader(classfileBuffer);
            ClassWriter writer = new ClassWriter(
                    reader, ClassWriter.COMPUTE_MAXS);
            boolean[] changed = {false};

            ClassVisitor visitor = new ClassVisitor(
                    Opcodes.ASM9, writer) {

                @Override
                public MethodVisitor visitMethod(
                        int access,
                        String name,
                        String descriptor,
                        String signature,
                        String[] exceptions) {

                    boolean selected =
                            "add".equals(name)
                            && "(II)I".equals(descriptor)
                            && (access & Opcodes.ACC_NATIVE) != 0
                            && (access & Opcodes.ACC_STATIC) != 0;

                    if (!selected) {
                        return super.visitMethod(
                                access, name, descriptor,
                                signature, exceptions);
                    }

                    changed[0] = true;

                    // Method gốc vẫn native, nhưng có prefix.
                    return super.visitMethod(
                            access, PREFIX + name, descriptor,
                            signature, exceptions);
                }

                @Override
                public void visitEnd() {
                    if (changed[0]) {
                        MethodVisitor mv = super.visitMethod(
                                Opcodes.ACC_PUBLIC
                                        | Opcodes.ACC_STATIC,
                                "add", "(II)I", null, null);

                        mv.visitCode();
                        print(mv, "WRAP_ENTER");

                        mv.visitVarInsn(Opcodes.ILOAD, 0);
                        mv.visitVarInsn(Opcodes.ILOAD, 1);
                        mv.visitMethodInsn(
                                Opcodes.INVOKESTATIC,
                                "demo/NativeMath",
                                PREFIX + "add",
                                "(II)I", false);

                        mv.visitVarInsn(Opcodes.ISTORE, 2);
                        print(mv, "WRAP_EXIT");
                        mv.visitVarInsn(Opcodes.ILOAD, 2);
                        mv.visitInsn(Opcodes.IRETURN);

                        // Với COMPUTE_MAXS, ASM tính max.
                        mv.visitMaxs(0, 0);
                        mv.visitEnd();
                    }
                    super.visitEnd();
                }

                private void print(
                        MethodVisitor mv, String message) {
                    mv.visitFieldInsn(
                            Opcodes.GETSTATIC,
                            "java/lang/System", "out",
                            "Ljava/io/PrintStream;");
                    mv.visitLdcInsn(message);
                    mv.visitMethodInsn(
                            Opcodes.INVOKEVIRTUAL,
                            "java/io/PrintStream", "println",
                            "(Ljava/lang/String;)V",
                            false);
                }
            };

            reader.accept(visitor, 0);

            if (!changed[0]) {
                return null;
            }

            System.out.println(
                    "AGENT_WRAPPED demo/NativeMath.add");
            return writer.toByteArray();
        }
    }
}
~~~

Đây là file Java hoàn chỉnh, dùng **ASM 9.7.1**. Chú ý những nguyên tắc:

1. Transformer lọc class name nội bộ **demo/NativeMath**, và bỏ qua callback redefinition. Với môi trường class loader phức tạp, cần lọc thêm defining loader/module.
2. Match **name + descriptor (II)I + ACC_NATIVE + ACC_STATIC**; không áp dụng mù quáng cho overload.
3. Original native được đổi tên thành **$$$DemoNative$$_add** nhưng **giữ ACC_NATIVE**, flags và descriptor. Nó không nhận Code.
4. Wrapper thêm method **public static add(II)I**, **không có ACC_NATIVE**, có Code.
5. Wrapper in WRAP_ENTER, load hai int ở local slot 0/1, **INVOKESTATIC** native có prefix, lưu result ở slot 2, in WRAP_EXIT rồi IRETURN.
6. **ClassWriter.COMPUTE_MAXS** tính lại kích thước stack/local cho method đơn giản không branch. ClassfileBuffer không bị mutate, writer trả mảng bytes mới.
7. Khi không tìm thấy method native phù hợp, return null; không tạo bản class mới vô nghĩa.
8. Log **AGENT_WRAPPED** cho biết transformer cung cấp bytes mới, **không phải bằng chứng JNI đã chạy đúng**. Cần quan sát output của ứng dụng.

Mã demo không thêm exceptional-exit hook, không hỗ trợ method instance, void/long/double/object return hoặc native method có synchronized. Những phần này cần generator tổng quát và kiểm chứng bytecode riêng.

### 5.6. File pom.xml: package ASM vào agent

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>nativewrap-agent</artifactId>
  <version>1.0.0</version>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.7.1</version>
    </dependency>
  </dependencies>

  <build>
    <sourceDirectory>src/agent/java</sourceDirectory>
    <finalName>nativewrap-agent</finalName>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.5.3</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <manifestEntries>
                    <Premain-Class>demo.NativeAgent</Premain-Class>
                    <Can-Set-Native-Method-Prefix>true</Can-Set-Native-Method-Prefix>
                  </manifestEntries>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Maven biên dịch **chỉ source agent** từ src/agent/java, đóng gói ASM vào JAR và tạo manifest với **Premain-Class** và **Can-Set-Native-Method-Prefix: true**. Maven cần tải dependency từ repository lần đầu hoặc dùng bản đã cache. Nếu nhiều agents mang các phiên bản ASM khác nhau, cần cân nhắc **shading/relocation** hoặc class loader isolation để tránh xung đột.

**Can-Retransform-Classes** và **Can-Redefine-Classes** không cần cho demo initial-load wrapper này. Cả hai là capability khác với native prefix.

## 6. Lệnh build và output trên Linux

### 6.1. Biên dịch Java và tạo JNI header

~~~bash
mkdir -p out/app out/include

javac --release 17 -h out/include -d out/app \
  src/app/java/demo/NativeMath.java \
  src/app/java/demo/App.java
~~~

Dùng **javac -h** để sinh **out/include/demo_NativeMath.h** có JNI prototype chính xác. File **out/app/demo/NativeMath.class** vẫn là class gốc có native declaration, chưa có wrapper.

### 6.2. Biên dịch thư viện C với gcc

Đặt **JAVA_HOME** đến thư mục JDK. Trong shell POSIX trên Linux có readlink -f, có thể tính:

~~~bash
JDK_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

gcc -shared -fPIC \
  -I"$JDK_HOME/include" \
  -I"$JDK_HOME/include/linux" \
  -Iout/include \
  -o libnativeops.so \
  src/native/nativeops.c
~~~

Lệnh build shared library và đường include phụ thuộc OS. macOS thường dùng **include/darwin** và **libnativeops.dylib**; Windows dùng công cụ biên dịch phù hợp để tạo **nativeops.dll**. Đừng đưa .so vào Java classpath để thay cho **System.loadLibrary**.

### 6.3. Package agent

~~~bash
mvn -q -DskipTests package
jar tf target/nativewrap-agent.jar
~~~

JAR phải chứa **META-INF/MANIFEST.MF**, **demo/NativeAgent.class** và những class ASM được đóng gói. Manifest phải có **Premain-Class: demo.NativeAgent** và **Can-Set-Native-Method-Prefix: true**. Nếu thiếu prefix attribute, **isNativeMethodPrefixSupported()** có thể false dù JVM nói chung hỗ trợ khả năng ấy.

### 6.4. Chạy đối chứng không agent

~~~bash
java -Djava.library.path=. -cp out/app demo.App
~~~

Output:

~~~text
RESULT=5
~~~

Không có wrapper, native method gốc được phân giải tới C implementation và trả 2+3=5.

### 6.5. Chạy với agent

~~~bash
java -Djava.library.path=. \
  -javaagent:target/nativewrap-agent.jar \
  -cp out/app demo.App
~~~

Output mong đợi:

~~~text
AGENT_PREFIX_READY
AGENT_WRAPPED demo/NativeMath.add
WRAP_ENTER
WRAP_EXIT
RESULT=5
~~~

**Giải thích output:** premain đăng ký prefix; transformer nhìn thấy NativeMath ở initial definition và trả class bytes đã có wrapper; wrapper ghi entry rồi gọi prefixed native; JNI tìm lại symbol native C gốc; wrapper ghi exit; caller nhận **5**.

Nếu native call ném exception, **WRAP_EXIT** sẽ không xuất hiện vì không có handler exceptional path trong demo. Khi triển khai telemetry production, phải quyết định đo **normal exit** và **exceptional exit** riêng.

**Độ tin cậy của demo:** cùng thuật toán ASM và native-prefix resolution đã được kiểm tra với một JDK tương thích bằng công cụ ASM có API tương đương. Phần build Maven sử dụng ASM 9.7.1 như chỉ dẫn nhưng chưa được kiểm tra trực tiếp trong môi trường sản xuất của người đọc.

## 7. Cơ chế native resolution phía sau ví dụ

### 7.1. JNI name mangling

JVM có quy tắc tạo tên native symbol từ class/method name, gồm prefix **Java_**, binary class name đã escape, dấu underscore và method name đã escape. Với overload native, tên dài bổ sung parameter descriptor đã escape có thể cần thiết.

Ví dụ không overload:

~~~text
Java class:          demo.NativeMath
Native declaration:  add(II)I
JNI symbol:          Java_demo_NativeMath_add
~~~

Các escape quan trọng: **/** thường thành **_**, underscore trong tên gốc thành **_1**, dấu chấm phẩy trong descriptor thành **_2**, dấu **[** thành **_3**. Hãy dùng **javac -h** thay vì tự ghép tên JNI bằng chuỗi nếu có overloaded methods, arrays hoặc object parameters.

### 7.2. Prefix fallback trong ví dụ

~~~text
Native method trong class đã transform:
    $$$DemoNative$$_add(II)I

JVM tìm symbol theo tên prefixed native
    |
    +-- không tìm thấy implementation phù hợp
    |
    +-- native prefix của transformer là "$$$DemoNative$$_"
    |
    +-- thử lại phân giải theo tên gốc add
    |
    v
Java_demo_NativeMath_add -> mã C hiện có
~~~

**setNativeMethodPrefix không tự động rename C symbol**; nó thay chiến lược fallback của JVM. Vì fallback chỉ dùng sau khi normal resolution thất bại, một native method không bị rename vẫn hoạt động như trước, giúp transformer bọc có chọn lọc.

### 7.3. JNI RegisterNatives

Nếu thư viện dùng **JNI RegisterNatives** thay vì export symbol tự động, JVM cũng có quy tắc retry association khi method name được prefixed bởi transformer. Tuy vậy native library có thể dùng chính sách custom, method lookup hoặc registration path phức tạp; phải thử đúng phiên bản native library và JVM đích.

### 7.4. Điều kiện “native library đã được nạp”

**System.loadLibrary("nativeops")** chạy ở static initializer của NativeMath trong demo. Nếu bỏ lệnh đó hoặc JVM không tìm thấy **libnativeops.so**, wrapper có thể được định nghĩa đúng nhưng invocation sẽ thất bại bằng **UnsatisfiedLinkError**. Đây là lỗi **JNI load/linkage**, không phải bằng chứng ClassFileTransformer không hoạt động.

## 8. Dùng javap để xác minh đúng class file

Đối với file gốc:

~~~bash
javap -c -p -s -classpath out/app demo.NativeMath
~~~

Bạn sẽ thấy native method **add(II)I**, nhưng không thấy wrapper. Đó là bình thường: ClassFileTransformer không ghi đè **out/app/demo/NativeMath.class**; nó trả bytes để JVM dùng khi định nghĩa lớp trong bộ nhớ.

Muốn kiểm tra class đã biến đổi cần dump **bytes do transformer trả về** trong môi trường kiểm thử và chạy javap trên bản dump đó, hoặc dùng công cụ phân tích classes/runtime phù hợp. Không nên dump class bytes bừa bãi trong production vì overhead và nguy cơ rò rỉ dữ liệu.

Disassembly rút gọn của class sau transform:

~~~text
public static native int $$$DemoNative$$_add(int, int);
  descriptor: (II)I
  flags: ACC_PUBLIC, ACC_STATIC, ACC_NATIVE

public static int add(int, int);
  descriptor: (II)I
  flags: ACC_PUBLIC, ACC_STATIC
  Code:
    getstatic java/lang/System.out
    ldc "WRAP_ENTER"
    invokevirtual java/io/PrintStream.println
    iload_0
    iload_1
    invokestatic demo/NativeMath.$$$DemoNative$$_add
    istore_2
    getstatic java/lang/System.out
    ldc "WRAP_EXIT"
    invokevirtual java/io/PrintStream.println
    iload_2
    ireturn
~~~

Đây là **minh họa logic instruction**: các constant-pool indexes, bytecode offsets và cú pháp in chính xác phụ thuộc javap/ASM/JDK. Điều cần xác minh là **native declaration không có Code**, **wrapper Java có Code**, và instruction gọi đúng prefixed native với descriptor **(II)I**.

## 9. Mở rộng cho instance, overload và các kiểu dữ liệu

Ví dụ chỉ bọc **static int add(int,int)**. Một transformer tổng quát cần xử lý nhiều trường hợp:

| Loại phương thức | Điều cần thay đổi trong wrapper | JNI argument thứ hai |
| --- | --- | --- |
| static native | Arguments bắt đầu local slot 0; gọi INVOKESTATIC | jclass |
| instance native | Local slot 0 là this; arguments bắt đầu slot 1; gọi opcode thích hợp với access | jobject |
| void return | Kết thúc bằng RETURN | Tùy static/instance |
| int/boolean/byte/short/char | IRETURN | Tùy static/instance |
| long | LRETURN, local chiếm 2 slot | Tùy static/instance |
| float | FRETURN | Tùy static/instance |
| double | DRETURN, local chiếm 2 slot | Tùy static/instance |
| object/array | ARETURN | Tùy static/instance |

Descriptor là hợp đồng quan trọng. Một method nhận long, double và String có dạng:

~~~text
(JDLjava/lang/String;)V

Nếu là instance method:
slot 0    -> this
slot 1-2  -> long
slot 3-4  -> double
slot 5    -> String
~~~

Không thể dùng **ILOAD 0, ILOAD 1** cho mọi method như demo. Phải tính local slots và opcode từ JVM descriptor; ASM **Type** hoặc thư viện bytecode khác giúp xử lý đúng.

### 9.1. Overloaded native methods

~~~java
// Hai method cùng tên nhưng có descriptor khác nhau.
public static native int add(int a, int b);
public static native long add(long a, long b);
~~~

Transformer phải match **name + descriptor**. JNI automatic resolution có cơ chế **short name** và **long name** (thêm encoded parameter descriptor) để phân biệt overloaded native methods. Nếu đổi cả hai, mỗi native declaration cần wrapper đúng descriptor và JNI symbol resolution phải được test với overload thực tế.

### 9.2. Synchronized native

Native method gốc có thể mang **ACC_SYNCHRONIZED**. Khi biến đổi thành Java wrapper và native đã đổi tên, cần quyết định **method nào giữ monitor** và giữ đúng thời điểm/đối tượng lock. Với static method monitor gắn Class object; với instance method monitor gắn receiver.

Copy toàn bộ flags sang cả wrapper và native một cách máy móc có thể làm thao tác lock hai tầng, tăng overhead hoặc thay nghĩa điểm đo. Nếu muốn monitor bao quanh cả advice và native call, thường thiết kế wrapper giữ synchronized, còn prefixed native được điều chỉnh có chủ đích; mọi thay đổi flags/ABI phải được kiểm chứng. Demo không có synchronized nên không xử lý trường hợp này.

### 9.3. Throwable từ native

Nếu C code gọi JNI ThrowNew hoặc native call hoàn thành với pending exception, lời gọi Java prefixed native có thể ném Throwable sang wrapper. Để quan sát exceptional exit, một wrapper tổng quát có thể có cấu trúc:

~~~java
// Pseudocode source-level, chưa phải mã ASM độc lập.
static int add(int a, int b) {
    hookEnter();
    try {
        int value = prefixedNativeAdd(a, b);
        hookSuccess(value);
        return value;
    } catch (Throwable original) {
        hookFailure(original);
        throw original;
    }
}
~~~

Phải bảo toàn **Throwable type, identity, stack/exception semantics**, và bảo đảm chính hook không vô tình thay lỗi gốc. Khi phát sinh try/catch bằng ASM, cần cập nhật **exception table, StackMapTable và frame computation**. Không dùng kiểu “catch mọi Throwable rồi return 0” cho công cụ quan sát.

### 9.4. Reflection và metadata

Sau biến đổi, reflection có thể nhìn thấy một method native có tên prefixed và một method Java có tên gốc. Nếu method gốc mang **annotations, generic Signature, parameter annotations, declared exceptions** hoặc framework-specific metadata, transformer phải xác định metadata cần nằm trên wrapper hay native declaration.

Bài demo không có annotations, nên giữ code ngắn. Với API public, không được coi việc di chuyển metadata là chi tiết không quan trọng: frameworks dựa vào annotations có thể đổi hành vi dù JNI result vẫn đúng.

## 10. Native wrapping với nhiều agents

Nhiều ClassFileTransformer có thể bọc cùng một native method. Mỗi transformer cần một **prefix riêng**; thứ tự transformer và cách chúng nhận bytes tạo thành **chuỗi wrappers**.

~~~text
Gốc:                   native foo
Transformer A:         Java wrapper foo
                       native $A_foo

Transformer B:         có thể thêm wrapper cho $A_foo
                       native $B_$A_foo

JVM native resolution: liên kết qua chuỗi prefix phù hợp
                       tới implementation JNI gốc của foo
~~~

Theo Javadoc, cơ chế prefix có xét **wrapper hiện diện ở các tầng trung gian** để tránh áp dụng prefix của transformer không thực sự bọc native method. Prefix được xét theo thứ tự transformer liên quan; một meta-agent có thể cần quản lý nhiều prefixes.

**Rủi ro điển hình:**

- Agent B xây lại class từ bytes gốc, vô tình xóa wrapper A.
- Hai agents dùng chung prefix, tạo collision method names.
- Agent B nhận bytes đã có wrapper nhưng match sai ACC_NATIVE/descriptor.
- Một transformer được gọi lại và chèn trùng wrapper.
- Thứ tự transformer khác kỳ vọng vì nhóm canRetransform/native Java transformer khác nhau.

Hãy kiểm thử riêng **A**, **B**, **A+B**, **B+A** và giữ logic biến đổi idempotent. Với nhiều agents, **một dòng log transformed** không chứng minh mọi wrapper khác còn hoạt động.

## 11. JVM TI SetNativeMethodPrefix khác Java Instrumentation ra sao?

Java agent thường dùng **ClassFileTransformer** và **Instrumentation.setNativeMethodPrefix**. Native JVMTI agent dùng **ClassFileLoadHook** để nhận dữ liệu class file và **SetNativeMethodPrefix** khi có capability tương ứng.

Các chữ ký tham khảo:

~~~c
// JVMTI interface, không phải JNI function trên JNIEnv*.
jvmtiError SetNativeMethodPrefix(
    jvmtiEnv* env, const char* prefix);

jvmtiError SetNativeMethodPrefixes(
    jvmtiEnv* env,
    jint prefix_count,
    char** prefixes);
~~~

**SetNativeMethodPrefixes** dùng cho môi trường phải quản lý nhiều prefixes như một meta-agent. Native prefix capability tương ứng trong JVMTI là **can_set_native_method_prefix**. Java Instrumentation cung cấp lớp API Java gắn prefix với **một ClassFileTransformer** đã đăng ký; không yêu cầu người dùng Java agent trực tiếp thao tác con trỏ **jvmtiEnv**.

**JNI khác JVMTI:** JNI dùng JNIEnv để native code tương tác với JVM và triển khai methods; JVM TI dành cho công cụ quan sát/điều khiển JVM theo events/capabilities. Đừng nhầm **SetNativeMethodPrefix** của JVMTI với một JNI function mà C implementation của NativeMath có thể gọi tùy ý.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
| --- | --- | --- |
| isNativeMethodPrefixSupported=false | Manifest thiếu capability hoặc JVM không hỗ trợ | Manifest và JDK/JVM |
| setNativeMethodPrefix ném IllegalArgumentException | Transformer chưa đăng ký | addTransformer trước |
| Có AGENT_PREFIX_READY nhưng không có AGENT_WRAPPED | Lớp đã load hoặc className/filter sai | Thời điểm load, internal name, loader |
| Có AGENT_WRAPPED nhưng không có WRAP_ENTER | Wrapper chưa được gọi hoặc class bị từ chối | Class load errors, callsite/descriptor |
| WRAP_ENTER rồi UnsatisfiedLinkError | Library/symbol/prefix resolution lỗi | System.loadLibrary, JNI symbol, prefix |
| JNI library thiếu | java.library.path sai | File .so/.dll/.dylib, loader errors |
| ClassFormatError | Native flags/Code/duplicate name không hợp lệ | javap và classfile structure |
| VerifyError | Stack/local/frames/return opcode sai | ASM verifier, JVM verification |
| NoSuchMethodError | Tên native prefixed hoặc descriptor không đúng | Owner/name/descriptor |
| IllegalAccessError | Visibility/module/helper access sai | ACC flags, defining loader, JPMS |
| WRAP_EXIT không xuất hiện | Native ném lỗi hoặc JVM crash | Exception/crash diagnostics |
| Attach agent muộn không có wrapper | Initial class definition đã diễn ra | Đổi chiến lược caller instrumentation |
| Kết quả đổi khi có hai agents | Prefix collision/thứ tự transformer | A/B/A+B/B+A tests |
| Native crash | ABI/JNI usage C sai | JNI header, -Xcheck:jni, native debugger |

### 12.1. Công cụ chẩn đoán

- **javac -h**: JNI header và function prototype.
- **javap -c -p -s -v**: method descriptor, flags, Code attribute.
- **jar tf** và manifest inspection: agent entry point/capability.
- **nm -D libnativeops.so** trên Linux: native symbols được export.
- **-Xcheck:jni** trên JVM hỗ trợ: phát hiện một số lỗi JNI usage.
- **JVM exception stack trace / hs_err_pid log**: phân biệt class definition failure, UnsatisfiedLinkError và native crashes.
- **Thread dumps/profilers**: overhead, race, deadlock.

Khi debug, ghi rõ **className, defining loader, module, original method descriptor, prefix, native JNI symbol**, và tách các mức: transformer được gọi, byte[] mới được trả, class được JVM chấp nhận, wrapper chạy, JNI implementation trả kết quả mong muốn.

## 13. Những trường hợp cần giải pháp khác

- **Lớp đã load**: phương pháp thêm method wrapper ở initial definition không áp dụng lại nguyên vẹn qua retransform. Instrument callsites hoặc dùng JVMTI/native tooling tùy nhu cầu.
- **Cần đo bên trong implementation C**: Java wrapper chỉ thấy boundary; phải instrument native code hoặc dùng native profiler.
- **Native method được gọi từ native code không đi qua wrapper Java**: Java wrapper không quan sát được mọi native-to-native calls.
- **Method có ABI phức tạp hoặc overload**: dùng descriptor/JNI header chuẩn và generator tương ứng.
- **JDK internal native methods**: phụ thuộc classloader/bootstrap, module encapsulation và những ràng buộc JVM đặc biệt; không mở rộng demo sang toàn bộ java.base tùy tiện.
- **Nhiều class loader cùng FQCN**: lọc đúng Class/loader; native library có classloader-specific lifecycle.
- **Production latency thấp**: ghi console mỗi invocation có overhead lớn; cần hook an toàn, hạn chế cấp phát và benchmark sau warm-up.

## 14. Ma trận test thiết yếu

| Test | Expected |
| --- | --- |
| Baseline không agent | RESULT=5, không có WRAP lines |
| Native wrapper đúng prefix | WRAP_ENTER, WRAP_EXIT, RESULT=5 |
| Capability tắt | Agent báo rõ unsupported, không giả thành công |
| JNI library thiếu | UnsatisfiedLinkError được phát hiện |
| JNI symbol sai | Native method resolution thất bại |
| Method không thuộc filter | Transformer return null |
| Prefixed method đã tồn tại | Không tạo duplicate/collision |
| Class đã được load trước agent | Không tự thêm wrapper bằng retransform |
| Overload native | Match descriptor/JNI long-name đúng |
| Instance native | this/jobject và invocation opcode đúng |
| long/double arguments | Local slot widths đúng |
| Native ném Throwable | Không nuốt, caller thấy loại/identity thích hợp |
| synchronized native | Monitor semantics không đổi |
| Hai agents | Prefix và wrapper composition đúng |
| Reflection/annotations | API metadata được bảo toàn theo contract |
| Concurrent calls | Hook không race/deadlock |
| Module/classloader khác | Helper/native visibility hợp lệ |
| Classfile verification | JVM chấp nhận class definition |

## 15. Câu hỏi tự kiểm tra

1. **Tại sao ClassFileTransformer không chèn advice trực tiếp vào body native?** Native method không có Code attribute chứa JVM bytecode.
2. **Cần tạo gì để quan sát cuộc gọi native ở Java?** Một wrapper Java có Code giữ tên/descriptor gốc và native declaration prefixed giữ descriptor cũ.
3. **setNativeMethodPrefix có tự đổi class file không?** Không; nó chỉ hỗ trợ retry native method resolution.
4. **Điều gì xảy ra nếu thiếu manifest capability?** Native-prefix support có thể không được cấp; phải kiểm tra trước khi set.
5. **Tại sao addTransformer gọi trước setNativeMethodPrefix?** Prefix được gắn với một transformer đã đăng ký.
6. **Vì sao cần làm ở initial class definition?** Đổi tên original và thêm wrapper là thay đổi method schema thường bị cấm trong retransformation của class đã load.
7. **Có phải sửa tên C symbol Java_demo_NativeMath_add?** Không trong demo: native prefix fallback cho phép liên kết với implementation cũ.
8. **Nếu native ném exception, WRAP_EXIT có chạy không?** Không khi chỉ đặt lệnh sau invocation. Cần handler/finally nếu muốn log cả exceptional exit.
9. **Static JNI khác instance JNI thế nào?** Static nhận jclass, instance nhận jobject; wrapper local slots/invocation phải tương ứng.
10. **Nếu hai agents cùng bọc native, có thể dùng chung prefix không?** Không nên; mỗi transformer cần prefix riêng tránh collision.
11. **Log AGENT_WRAPPED đã chứng minh native call thành công chưa?** Chưa. Phải xem wrapper thực thi và result/exception thật.
12. **JVMTI SetNativeMethodPrefix có dùng JNIEnv* không?** Không; thuộc giao diện JVMTI với jvmtiEnv và capability riêng.

## 16. Checklist áp dụng vào agent thật

- Tôi hiểu **ACC_NATIVE** và lý do native method không có Code.
- Tôi biết **method name + descriptor + flags**, classloader và module đích.
- Transformer chạy khi **initial class definition** chứ không cố thêm method vào lớp đã load.
- Manifest có **Can-Set-Native-Method-Prefix: true**, JVM support được kiểm tra.
- addTransformer chạy trước setNativeMethodPrefix.
- Prefix độc nhất, khớp với tên native đã đổi và không va chạm.
- Java wrapper giữ API gốc, native declaration vẫn giữ descriptor và ACC_NATIVE.
- Wrapper gọi đúng opcode, local slots, return opcode và class owner.
- Byte[] output hợp lệ, **không mutate classfileBuffer**; ngoài scope thì return null.
- JNI automatic resolution/RegisterNatives đã được thử với thư viện thật.
- Return, exception, synchronized, annotations và caller visibility được giữ đúng.
- Không đánh đồng Java wrapper với instrument code C bên trong.
- Đã thử baseline/wrapped, lỗi JNI, nhiều agents, class loader/module và concurrency.
- Kết quả thành công được xác minh bằng behavior thực, không chỉ log transformer.

## 17. Tài liệu chuẩn

- [Java 17 — Instrumentation.setNativeMethodPrefix](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#setNativeMethodPrefix(java.lang.instrument.ClassFileTransformer,java.lang.String)): thiết kế wrapper native, fallback cho JNI automatic resolution/RegisterNatives, nhiều prefixes và exceptions.
- [Java 17 — Instrumentation.isNativeMethodPrefixSupported](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#isNativeMethodPrefixSupported()): capability tùy chọn.
- [Java 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): -javaagent, Premain-Class, Can-Set-Native-Method-Prefix.
- [Java 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transform lúc class load, immutable input và return bytes.
- [JNI Specification 17 — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): native library loading, mangled symbol names, RegisterNatives và JNI argument conventions.
- [JVM Specification 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): ACC_NATIVE, Code attribute, descriptors.
- [JVM TI 17 Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): ClassFileLoadHook, native method prefix functions và capability.
- [ASM 9.7.1](https://central.sonatype.com/artifact/org.ow2.asm/asm/9.7.1): reader/visitor/writer dùng để tạo method bytecode.

**Ghi nhớ:** Native method không có Java Code để chèn trực tiếp điểm đo. Hãy **bọc native bằng Java method có Code tại lần định nghĩa lớp đầu**, đổi tên native bằng một **prefix của transformer**, đăng ký **setNativeMethodPrefix** đúng capability trước class load, giữ nguyên descriptor/JNI semantics và kiểm tra cả wrapper lẫn implementation native thực sự hoạt động.
