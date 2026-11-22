# Dùng Class-File API để chèn một lời gọi helper rồi kiểm chứng bytecode

## 1. Mục tiêu thí nghiệm và kết quả cần chứng minh

Bài thực hành thuộc nhóm **Thực nghiệm agent** của **Java Advance - instrumentation**. Ta sẽ tạo một **Java agent thực sự** sử dụng **Class-File API chuẩn của JDK 24** để thêm một lời gọi `invokestatic` tới helper vào đầu một phương thức Java, sau đó kiểm chứng bằng **ba tầng**: phân tích bytes ngay trong transformer, phân tích độc lập tệp class đã biến đổi và chạy ứng dụng với bộ kiểm tra bytecode của JVM.

Trong bài, ứng dụng có phương thức:

~~~java
package demo.app;

public final class Greeter {
    public static String greet(String name) {
        return "Hello " + name;
    }
}
~~~

Khi chưa có agent, `Greeter.greet("Java")` chỉ nối chuỗi và trả về `Hello Java`. Khi chạy với agent:

~~~text
Trước biến đổi:
    Greeter.greet(String)
        -> xử lý tên
        -> return "Hello " + name

ClassFileTransformer nhận class-file bytes
        |
        v
ClassFile.of().parse(...)
        |
        v
ClassTransform.transformingMethodBodies(...)
        |
        v
CodeBuilder.invokestatic(Probe.hit, ()V)
        |
        v
ClassFile.transformClass(...) -> byte[] mới
        |
        v
JVM verifier và class loading
        |
        v
Sau biến đổi:
    Greeter.greet(String)
        -> invokestatic demo.agent.Probe.hit:()V
        -> xử lý tên
        -> return "Hello " + name
~~~

Chúng ta sẽ chứng minh được:

1. **Không có agent:** helper không được gọi; phương thức vẫn trả đúng kết quả nghiệp vụ.
2. **Có agent:** transformer được gọi **trước khi `demo.app.Greeter` được định nghĩa**, tạo class bytes mới và xác minh đúng **một lời gọi `Probe.hit()`** trong `greet`.
3. **Chạy thực tế:** helper tăng counter đúng một lần, giá trị trả về của `greet` không đổi.
4. **Kiểm chứng bytecode độc lập:** `javap -c -p` hiện một instruction `invokestatic` mới ở offset 0 của `greet`; chương trình kiểm tra dựa trên Class-File API đối chiếu **original=0** và **transformed=1**.
5. **Verify của JVM:** chạy ứng dụng với `-Xverify:all` thành công, không có `VerifyError`.

**Phạm vi có chủ đích:** chỉ biến đổi một phương thức `greet` rất đơn giản, không có try/catch, không phải constructor, không có overload. Mục tiêu là hiểu và tự kiểm chứng một thao tác chèn lời gọi helper, **không** tuyên bố đã xây được agent tổng quát cho mọi dạng bytecode production.

## 2. Điều kiện môi trường: JDK 24 là bắt buộc cho mã nguồn trong bài

**Class-File API chuẩn `java.lang.classfile` có mặt từ JDK 24** (JEP 484). Ở các phiên bản JDK 22/23, API trải qua giai đoạn preview với những khác biệt có thể có; **Java 17 hoặc 21 không biên dịch được trực tiếp mã sử dụng `java.lang.classfile` chuẩn như ở đây**.

| Thành phần | Yêu cầu cho thí nghiệm |
| --- | --- |
| JDK để compile | **JDK 24**, gồm `javac` và `jar` |
| JVM chạy ứng dụng và agent | **JDK 24** |
| Class-File API | `java.lang.classfile` trong `java.base` |
| Instrumentation API | `java.lang.instrument` trong module `java.instrument` |
| Tài liệu/API đối chiếu | Javadoc Java SE 24, JEP 484 |
| Thư viện ngoài | **Không cần** ASM, Byte Buddy hoặc Javassist |
| Cơ chế nạp agent | `-javaagent:demo-agent.jar` lúc JVM khởi động |
| Kiểm chứng tệp class | `javap` và Java Class-File API |
| Preview flag | **Không cần `--enable-preview` trên JDK 24** |

Kiểm tra:

~~~bash
java -version
javac -version
jar --help
javap -help
~~~

Các lệnh trên là kiểm tra môi trường, không phải stdout cố định. Nếu `javac` báo JDK thấp hơn 24, hãy dùng JDK 24 trước khi chạy mã. Ví dụ `--release 24` bảo đảm compiler phát bytecode phù hợp mức Java 24, class-file major version **68**.

**Đã kiểm thử:** toàn bộ chương trình Java trong bài được biên dịch bằng **Zulu/OpenJDK 24.0.2** với `javac --release 24`, chạy cùng `-javaagent` và `-Xverify:all`. Các kết quả được ghi trong những phần tiếp theo là kết quả thực nghiệm, không phải output suy đoán.

## 3. Các đối tượng Class-File API cần nắm

| API / kiểu | Vai trò |
| --- | --- |
| `ClassFile.of()` | Tạo ngữ cảnh đọc/ghi/biến đổi class file với các option mặc định |
| `ClassFile.parse(byte[])` | Đọc mảng bytes thành `ClassModel` |
| `ClassModel` | Mô hình lớp, chứa method/field/attribute ở dạng có thể truy vấn |
| `MethodModel` | Mô hình một method; `methodName()`, `methodType()`, `code()` |
| `ClassTransform` | Hướng dẫn xây class mới từ các class elements |
| `ClassTransform.transformingMethodBodies(filter, codeTransform)` | Chỉ chuyển đổi body của các method đáp ứng điều kiện lọc |
| `CodeTransform` | Xử lý dòng `CodeElement`; có thể thêm/bỏ/thay element |
| `CodeTransform.ofStateful(supplier)` | Tạo **state transform mới cho mỗi traversal** |
| `CodeBuilder.invokestatic(owner, name, type)` | Phát instruction gọi static method |
| `ClassFile.transformClass(model, transform)` | Ghi ra **mảng `byte[]` class-file mới** từ model và transform |
| `CodeModel.elementStream()` | Duyệt code elements để kiểm tra instruction |
| `InvokeInstruction` / `Opcode.INVOKESTATIC` | Nhận dạng đúng instruction gọi helper |

Cách liên kết các tầng:

~~~text
byte[] classfileBuffer
     -> ClassFile.of().parse(...)
     -> ClassModel
        -> MethodModel ("greet")
           -> CodeModel
              -> CodeElement: load, invokedynamic, return...
     -> ClassTransform
        -> CodeTransform
           -> CodeBuilder.invokestatic(...)
           -> CodeBuilder.with(originalElement)
     -> ClassFile.transformClass(...)
     -> byte[] transformedBytes
~~~

Mô hình **bất biến về mặt API**, nhưng **parsing được thực hiện trì hoãn (lazy)** nên không giả định rằng `parse` một lần sẽ phát hiện tất cả lỗi class file. Javadoc Java 24 lưu ý một số accessor có thể ném `IllegalArgumentException` khi gặp dữ liệu hỏng, và model truy cập lazy có thể không thread-safe cho việc chia sẻ không kiểm soát. Trong demo, mỗi callback có model riêng và xử lý tuần tự trong chính callback.

### 3.1. Khác với thao tác sửa chuỗi bytes thủ công

Nếu chỉ scan mảng bytes rồi chèn vài byte `invokestatic` vào một vị trí bất kỳ, ta phải tự quản lý:

- Độ dài `Code` và `attribute_length`;
- constant-pool entries cho owner, tên method và descriptor;
- offsets của lệnh nhảy;
- exception table ranges;
- `StackMapTable`, line numbers và local variable metadata;
- giới hạn class-file format và JVM verifier.

Class-File API hỗ trợ **mô hình hóa và tái tạo cấu trúc**, giảm rủi ro sai offset/constant pool. Tuy nhiên, người viết vẫn phải nắm **ngữ nghĩa bytecode**, thứ tự instruction, entry point, stack effects và ranh giới loader/module. API không biến mọi thao tác chèn code thành hợp lệ một cách tự động.

## 4. Cấu trúc dự án thử nghiệm

~~~text
classfile-agent-demo/
  agent-src/
    demo/agent/
      ClassFileAgent.java
      Probe.java
  app-src/
    demo/app/
      Greeter.java
      Main.java
  tools-src/
    VerifyBytecode.java
  MANIFEST.MF
  agent-classes/             (tạo lúc build)
  app-classes/               (tạo lúc build)
  tool-classes/              (tạo lúc build)
  demo-agent.jar             (tạo lúc build)
  transformed/
    demo/app/Greeter.class   (agent ghi để kiểm chứng trong demo)
~~~

**Phân chia trách nhiệm:**

- `ClassFileAgent` nhận `Instrumentation` qua `premain` và đăng ký `ClassFileTransformer`.
- `Probe` là helper có static method `hit()` và counter. Class do agent tạo phải **nhìn thấy** helper khi chạy.
- `Greeter` là class đích; mã nguồn **không chứa** lời gọi `Probe.hit()`.
- `Main` là chương trình gọi thử, dùng counter của helper để xác minh kết quả.
- `VerifyBytecode` là công cụ **độc lập** đọc bản gốc và bản đã biến đổi, không dùng dữ liệu báo cáo của transformer.

Tệp `transformed/...` chỉ được ghi **để phục vụ thực nghiệm bằng `javap`**, không phải yêu cầu của `ClassFileTransformer`. Trong production, **không nên thực hiện file I/O đồng bộ trong class-load callback** như ví dụ này.

## 5. Helper: `Probe.hit()` là method được chèn vào bytecode

**Tệp `agent-src/demo/agent/Probe.java`**

~~~java
package demo.agent;

import java.util.concurrent.atomic.AtomicInteger;

public final class Probe {
    private static final AtomicInteger HITS = new AtomicInteger();

    public static void hit() {
        System.out.println("hook.hit=" + HITS.incrementAndGet());
    }

    public static int hits() {
        return HITS.get();
    }
}
~~~

Method signature thực sự là:

~~~text
Owner (internal name): demo/agent/Probe
Method name:           hit
JVM descriptor:        ()V
Opcode:                INVOKESTATIC
~~~

`()V` nghĩa **không có tham số và trả `void`**. Không có giá trị nào được đẩy lên operand stack bởi `Probe.hit()` sau khi nó trả về thành công. Điều này làm ví dụ dễ đọc: instruction mới không cần `aload`, không cần thay đổi local variables hay xử lý giá trị trả về của `greet`.

`AtomicInteger` bảo đảm số đếm hoạt động chính xác khi nhiều thread cùng gọi helper, nhưng `System.out.println` ngay trong hook **chỉ dành cho demo**. Với agent tải lớn, lời gọi log đồng bộ ở mọi method entry gây overhead và có nguy cơ tự instrument/reentrancy. Production nên dùng helper tối giản, queue có giới hạn, sampling và cơ chế bảo vệ khi exporter lỗi.

**Lưu ý:** helper không mặc nhiên là một “hàm JVM đặc biệt”. Đó là class/method Java bình thường. Nếu target không resolve được `demo.agent.Probe`, bytecode đã chèn có thể gây `NoClassDefFoundError` hoặc lỗi liên kết khi chạy.

## 6. Class đích không có lời gọi helper trong source

**Tệp `app-src/demo/app/Greeter.java`**

~~~java
package demo.app;

public final class Greeter {
    public static String greet(String name) {
        return "Hello " + name;
    }
}
~~~

**Tệp `app-src/demo/app/Main.java`**

~~~java
package demo.app;

import demo.agent.Probe;

public final class Main {
    public static void main(String[] args) {
        System.out.println("result=" + Greeter.greet("Java"));
        System.out.println("helper.hits=" + Probe.hits());
    }
}
~~~

Mã nguồn `Greeter` **không import helper**, không có `Probe.hit()` và không có lệnh in `hook.hit=...`. Sau khi có agent, lời gọi chỉ có thể đến từ **class file đã biến đổi** (trong phạm vi demo này).

`Main` import `Probe` **chỉ để đọc bộ đếm sau khi gọi thử**. Nó không gọi `hit()`. Khi chạy không có agent, `helper.hits=0`; khi chạy với agent, số đếm dự kiến bằng 1.

Đây là ví dụ phù hợp để so sánh before/after vì body `greet` rất ngắn và kết quả nghiệp vụ xác định. Với target method có overload, constructor, bytecode nhảy phức tạp hoặc try/catch, cần thêm điều kiện lọc và kiểm thử riêng.

## 7. Agent dùng Class-File API để chèn `invokestatic`

**Tệp `agent-src/demo/agent/ClassFileAgent.java`** — toàn bộ class đã biên dịch và chạy trên JDK 24:

~~~java
package demo.agent;

import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeBuilder;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class ClassFileAgent {
    private static final String TARGET = "demo/app/Greeter";
    private static final ClassDesc HOOK = ClassDesc.of("demo.agent.Probe");
    private static final MethodTypeDesc NO_ARGS_VOID =
            MethodTypeDesc.ofDescriptor("()V");

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new HookTransformer(), false);
        System.out.println("agent=installed");
    }

    private static final class HookTransformer implements ClassFileTransformer {
        @Override
        public byte[] transform(ClassLoader loader, String className,
                Class<?> redefining, ProtectionDomain domain, byte[] bytes) {
            if (!TARGET.equals(className)) return null;

            ClassFile cf = ClassFile.of();
            CodeTransform prepend = CodeTransform.ofStateful(() ->
                    new CodeTransform() {
                boolean first = true;

                @Override
                public void accept(CodeBuilder out, CodeElement element) {
                    if (first) {
                        out.invokestatic(HOOK, "hit", NO_ARGS_VOID);
                        first = false;
                    }
                    out.with(element);
                }
            });

            byte[] changed = cf.transformClass(cf.parse(bytes),
                    ClassTransform.transformingMethodBodies(
                            method -> method.methodName()
                                    .equalsString("greet"),
                            prepend));

            long hits = cf.parse(changed).methods().stream()
                    .filter(method -> method.methodName()
                            .equalsString("greet"))
                    .flatMap(method ->
                            method.code().orElseThrow().elementStream())
                    .filter(e -> e instanceof InvokeInstruction i
                            && i.owner().asSymbol().equals(HOOK)
                            && i.name().equalsString("hit"))
                    .count();

            System.out.println("agent.transform=" + className);
            System.out.println("agent.hookCount=" + hits);
            if (hits != 1) {
                throw new AssertionError(
                        "Unexpected probe count: " + hits);
            }

            try {
                Path destination =
                        Path.of("transformed/demo/app/Greeter.class");
                Files.createDirectories(destination.getParent());
                Files.write(destination, changed);
            } catch (java.io.IOException ex) {
                throw new IllegalStateException(
                        "Demo dump failure", ex);
            }
            return changed;
        }
    }
}
~~~

**Các API chính xác được dùng trong bản thử:**

- `ClassDesc.of("demo.agent.Probe")` nhận **binary name dùng dấu chấm**, không phải chuỗi internal name dấu slash của callback.
- `MethodTypeDesc.ofDescriptor("()V")` tạo mô tả lời gọi static method; descriptor phải trùng **chính xác** method `Probe.hit()`.
- `ClassTransform.transformingMethodBodies(predicate, prepend)` chọn method theo `methodName` và chỉ biến đổi **`Code`** của method đó.
- `CodeTransform.ofStateful(...)` tạo một transform có trạng thái cục bộ cho traversal. Biến `first` bảo đảm chỉ chèn lời gọi **một lần ở phần đầu**.
- `CodeBuilder.invokestatic(HOOK, "hit", NO_ARGS_VOID)` phát instruction `INVOKESTATIC` cùng symbolic reference tới helper.
- `out.with(element)` đưa **mọi code element gốc** qua builder. Nếu bỏ dòng này, transform sẽ loại chúng, làm method không còn thân code như ý định.
- `cf.transformClass(cf.parse(bytes), ...)` sinh **mảng byte mới**; code không sửa `bytes` đầu vào.
- Dòng `cf.parse(changed)` và `InvokeInstruction` dùng cùng Class-File API để kiểm tra có đúng một invocation helper.
- `Files.write(...)` chỉ dump class-file **sau biến đổi** ra một đường dẫn test để có thể dùng `javap`/kiểm tra độc lập.

### 7.1. Vì sao transformer lọc class name trước khi phân tích bytes?

`className` trong callback dùng **internal name**, nên so khớp:

~~~java
if (!"demo/app/Greeter".equals(className)) {
    return null;
}
~~~

Đây là **mảnh code rút từ transformer**. Tác dụng:

1. Tránh phân tích mọi class JDK/ứng dụng/agent; giảm CPU và allocation tại class load.
2. Tránh tự instrument `demo.agent.ClassFileAgent` và `demo.agent.Probe`, gây recursion hoặc circular loading.
3. Giữ phạm vi thí nghiệm **một class xác định**, không lỡ can thiệp class loader khác.
4. `className` có thể là `null` trong một số tình huống; `"literal".equals(className)` vẫn an toàn.

**Không đổi dấu slash thành dấu chấm khi so với `className`**. Nhưng ở `ClassDesc.of` phải dùng cú pháp binary name dấu chấm. Đây là hai bề mặt API khác nhau.

### 7.2. Vì sao chèn lời gọi phải dùng descriptor đúng?

`INVOKESTATIC` tham chiếu một phương thức cụ thể theo **owner + name + descriptor**, không chỉ tên. Trong bài:

~~~text
demo/agent/Probe.hit:()V
    |
    +-- ClassDesc: demo.agent.Probe
    +-- Name: hit
    +-- MethodTypeDesc: ()V
~~~

Nếu helper thật là `hit(String)` nhưng transform vẫn phát `()V`, JVM có thể báo `NoSuchMethodError` khi liên kết, vì không có method đúng descriptor. Nếu helper là instance method nhưng transform lại phát `invokestatic`, có thể có `IncompatibleClassChangeError`. Nếu helper không visible từ defining loader của target, có thể gặp `NoClassDefFoundError`.

Bản ví dụ cố ý không truyền tham số để tránh phải tự đẩy `this`/argument lên operand stack. Nếu muốn gửi tên method hoặc trace ID, cần thiết kế stack effect cho `ldc`/`aload`/`invoke...` đúng opcode và descriptor.

### 7.3. Vì sao dùng `CodeTransform.ofStateful`?

Một `CodeTransform` có thể được tái sử dụng khi xử lý nhiều code bodies. Nếu một biến `boolean first` được giữ trên transform dùng chung, lần đầu chèn ở phương thức A có thể làm phương thức B không được chèn nữa. `ofStateful` cung cấp transform mới cho mỗi traversal theo hợp đồng API.

Trong thí nghiệm chỉ có một `greet`, nhưng cách viết này tránh tạo ra một thói quen sai khi sau đó mở rộng matcher sang nhiều phương thức.

Ngoài ra, khi xử lý code element đầu tiên, builder được yêu cầu viết `invokestatic` **trước** khi chuyển nguyên code element gốc. Trên `Greeter.greet` đơn giản, bytecode verifier chấp nhận và `javap` xác nhận đây là **instruction đầu tiên ở offset 0**.

**Không tổng quát hóa tùy tiện:** việc chèn trước instruction đầu có thể không phù hợp cho constructor `<init>` (ràng buộc uninitialized `this`), code với try/catch/labels, synchronized hoặc các stack-map frames phức tạp. Một agent production cần xử lý vị trí insertion an toàn, labels/ranges, stack effects và verifier đúng từng loại method.

### 7.4. Vì sao không biến mọi method trong class?

`ClassTransform.transformingMethodBodies(...)` chỉ áp dụng tới những method có **`Code`** và đáp ứng predicate. Trong bài predicate kiểm tra **`methodName()=="greet"`**; lớp demo có duy nhất một `greet`.

Với overload production, hãy lọc thêm **descriptor**:

~~~java
method -> method.methodName().equalsString("greet")
        && method.methodType()
                .equalsString("(Ljava/lang/String;)Ljava/lang/String;")
~~~

Đây là **mảnh predicate Java** dùng trong `ClassTransform.transformingMethodBodies`, không phải chương trình độc lập. Nó giúp chỉ chọn đúng chữ ký `greet(String):String` thay vì mọi overload cùng tên. Cũng nên loại trừ `<init>`, `<clinit>`, synthetic/bridge methods hoặc native/abstract methods theo mục tiêu.

### 7.5. Ghi tệp trong transformer chỉ để phục vụ bài học

Bản test ghi `transformed/demo/app/Greeter.class` trực tiếp trong callback. Trong sản phẩm thật, tránh:

- Ghi đĩa, mạng, logger nặng hoặc gọi class loading phản xạ ngay trong transformer;
- Đặt file dump bằng tên class cố định nếu có nhiều class loaders tạo class cùng tên;
- Để sự cố quota/filesystem làm mất kết quả nghiệp vụ;
- Cấp phát/dump mọi class file khiến heap/đĩa tăng ngoài kiểm soát.

Có thể bật dump trong môi trường test/debug riêng, dùng tên file theo loader/session, hoặc kiểm chứng bằng Class-File API trực tiếp trên bytes mới và unit tests. **Hợp đồng transformer chỉ cần trả `byte[]` hợp lệ**; không có yêu cầu phải tạo tệp `.class` trên ổ đĩa.

## 8. Manifest: JVM gọi `premain` trước `main`

**Tệp `MANIFEST.MF`**

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ClassFileAgent

~~~

File cần một dòng trống ở cuối phần main attributes. `Premain-Class` chỉ đúng tên **lớp agent**, không phải lớp helper hay target.

Trong code:

~~~java
public static void premain(String args, Instrumentation inst) {
    inst.addTransformer(new HookTransformer(), false);
    System.out.println("agent=installed");
}
~~~

Đây là **mảnh code từ agent**, thứ tự gọi đăng ký là điều kiện thực nghiệm: target `Greeter` phải **chưa được load** trước lúc đăng ký. `-javaagent` cung cấp instance `Instrumentation`; ta không tự khởi tạo interface này.

`addTransformer(..., false)` nghĩa transformer **không được đánh dấu có khả năng retransform**. Thí nghiệm chỉ can thiệp **initial class definition**, không cần `Can-Retransform-Classes: true`, không gọi `retransformClasses` và không cần dynamic attach.

Đừng nhầm `-javaagent:...` với `-agentlib` (native JVMTI) hoặc `-cp`. JVM load agent JAR ở startup; runtime classpath ở demo cũng đưa agent JAR vào để bảo đảm `Probe` accessible từ ứng dụng.

## 9. Lệnh xây dựng và chạy trên Linux/macOS

Tạo cây thư mục theo mục 4, sau đó chạy từ **thư mục gốc `classfile-agent-demo`**:

~~~bash
mkdir -p agent-classes app-classes tool-classes

javac --release 24 -d agent-classes \
  agent-src/demo/agent/ClassFileAgent.java \
  agent-src/demo/agent/Probe.java

jar --create --file demo-agent.jar \
  --manifest MANIFEST.MF \
  -C agent-classes .

javac --release 24 -cp demo-agent.jar -d app-classes \
  app-src/demo/app/Greeter.java \
  app-src/demo/app/Main.java

# Baseline khong co agent:
java -cp "app-classes:demo-agent.jar" demo.app.Main

# Bien doi class that, va xac minh boi JVM:
java -Xverify:all -javaagent:demo-agent.jar \
  -cp "app-classes:demo-agent.jar" demo.app.Main
~~~

**Lưu ý:** `:\` phân tách entries trong `-cp` trên Unix, còn trên Windows là **dấu chấm phẩy** `;`. File `transformed/demo/app/Greeter.class` chỉ xuất hiện sau **lệnh chạy có agent**. Mọi lệnh có dấu `\` nối dòng trong block này dùng cú pháp Bash.

### 9.1. Lệnh tương đương trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force agent-classes, app-classes, tool-classes | Out-Null

javac --release 24 -d agent-classes agent-src/demo/agent/ClassFileAgent.java agent-src/demo/agent/Probe.java

jar --create --file demo-agent.jar --manifest MANIFEST.MF -C agent-classes .

javac --release 24 -cp demo-agent.jar -d app-classes app-src/demo/app/Greeter.java app-src/demo/app/Main.java

java -cp "app-classes;demo-agent.jar" demo.app.Main

java -Xverify:all -javaagent:demo-agent.jar -cp "app-classes;demo-agent.jar" demo.app.Main
~~~

Lệnh được thử trong môi trường PowerShell với JDK 24. `jar` phải chứa các `.class` của `ClassFileAgent`, nested class của transformer và `Probe`; dùng `-C agent-classes .` sẽ đóng cả thư mục class đã biên dịch.

**Không** chạy `jar --create` trước khi `javac` tạo agent classes. Nếu manifest có `Premain-Class` sai, JVM có thể không khởi tạo agent và không vào ứng dụng như ý định.

## 10. Stdout: so sánh không có agent và có agent

### 10.1. Baseline không có agent

Chạy:

~~~bash
java -cp "app-classes:demo-agent.jar" demo.app.Main
~~~

Trên PowerShell, thay `:` trong classpath bằng `;`. Output thực tế:

~~~text
result=Hello Java
helper.hits=0
~~~

**Điểm quan trọng:** chỉ đưa `demo-agent.jar` vào **classpath** không làm `premain` chạy. Lớp `Probe` có thể được load khi `Main` đọc counter, nhưng không có lệnh gọi `Probe.hit()` bên trong `Greeter`, nên `hits=0`.

### 10.2. Khi chạy với Java agent thật

Chạy:

~~~bash
java -Xverify:all -javaagent:demo-agent.jar -cp "app-classes:demo-agent.jar" demo.app.Main
~~~

Output chính xác trên Zulu/OpenJDK 24.0.2:

~~~text
agent=installed
agent.transform=demo/app/Greeter
agent.hookCount=1
hook.hit=1
result=Hello Java
helper.hits=1
~~~

Giải thích từng dòng:

1. `agent=installed`: `premain` chạy trước application `main`.
2. `agent.transform=demo/app/Greeter`: callback khớp chính xác class name.
3. `agent.hookCount=1`: sau khi dựng bytes mới, chính agent parse output và tìm được **một** `InvokeInstruction` gọi helper.
4. `hook.hit=1`: lúc `Greeter.greet` chạy, instruction mới thực sự gọi static helper.
5. `result=Hello Java`: kết quả nghiệp vụ của method được giữ nguyên.
6. `helper.hits=1`: ứng dụng xác nhận counter tăng đúng một lần.

Không có lỗi `VerifyError` khi chạy với `-Xverify:all`. Đây là một bằng chứng **bytecode đã vượt qua JVM verifier đối với test này**. Nó không tự đảm bảo mọi class ở mọi JVM hoặc mọi biến thể code cũng an toàn.

### 10.3. Tại sao stdout có `hook.hit=1` trước `result=...`?

Trong `Main`, biểu thức:

~~~java
System.out.println("result=" + Greeter.greet("Java"));
~~~

Java cần đánh giá `Greeter.greet("Java")` **trước** khi gọi `println` để in chuỗi kết quả. Vì helper được chèn vào đầu `greet`, `Probe.hit()` in dòng hook trước; sau đó `greet` return, rồi `Main` in dòng kết quả.

Thứ tự in này chỉ là quan sát của **test một thread**, không phải một cách thay thế cho việc đếm instruction trong class file.

## 11. Kiểm chứng bằng `javap` trên hai bản class file

Sau khi chạy agent, vẫn ở thư mục gốc dự án:

~~~bash
javap -classpath app-classes -c -p demo.app.Greeter
javap -classpath transformed -c -p demo.app.Greeter
~~~

Lệnh đầu đọc **bytes gốc do `javac` tạo**, lệnh sau đọc **bytes mới do transformer dump ra**.

### 11.1. Phần `greet` trước biến đổi

Trích đoạn thực nghiệm trên JDK 24:

~~~text
public static java.lang.String greet(java.lang.String);
  Code:
     0: aload_0
     1: invokedynamic #7,  0
     6: areturn
~~~

Một số thông tin comment của `javap` bị lược để tập trung vào opcode. `invokedynamic` ở đây là cách compiler thực hiện nối chuỗi; JDK/compiler khác có thể phát instruction tương đương theo cách khác. **Điểm kiểm chứng chính:** chưa có `invokestatic demo/agent/Probe.hit:()V`.

### 11.2. Phần `greet` sau biến đổi

Trích đoạn thực nghiệm:

~~~text
public static java.lang.String greet(java.lang.String);
  Code:
     0: invokestatic  #37     // Method demo/agent/Probe.hit:()V
     3: aload_0
     4: invokedynamic #7,  0
     9: areturn
~~~

**Thấy rõ thay đổi:**

- Instruction mới được chèn ở **offset 0**.
- JVM opcode `INVOKESTATIC` gọi `demo/agent/Probe.hit:()V`.
- Instruction gốc `aload_0` chuyển từ offset 0 sang offset 3; instruction nối chuỗi/return tiếp tục tồn tại.
- Chỉ số constant pool `#37` là **chi tiết của bản class đã test**; có thể khác nếu compiler, constant pool hoặc options thay đổi. Không viết test hardcode `#37`.
- Các offsets sau chèn dịch tương ứng với kích thước instruction mới. Không nên tự cộng offset bằng tay với class có branches/exception table/stackmaps.

Việc `javap` hiển thị lời gọi **ở trong `greet`** cho thấy đây là biến đổi bytecode của class đích, không chỉ là `System.out.println` trong `premain`.

## 12. Kiểm chứng độc lập bằng Class-File API

Để tránh chỉ tin vào `agent.hookCount=1` (chính transformer tự thông báo), tạo một chương trình khác **đọc hai tệp class từ filesystem** và đếm instruction cụ thể.

**Tệp `tools-src/VerifyBytecode.java`**

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.Instruction;
import java.lang.classfile.Opcode;
import java.lang.classfile.MethodModel;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class VerifyBytecode {
    private static final ClassDesc HELPER =
            ClassDesc.of("demo.agent.Probe");

    private static void report(String label, Path file) throws Exception {
        MethodModel greet = ClassFile.of().parse(Files.readAllBytes(file))
                .methods().stream()
                .filter(m -> m.methodName().equalsString("greet"))
                .findFirst().orElseThrow();

        List<Instruction> instructions = greet.code().orElseThrow()
                .elementStream().filter(e -> e instanceof Instruction)
                .map(e -> (Instruction) e).toList();

        long calls = instructions.stream()
                .filter(VerifyBytecode::isHelperCall).count();

        System.out.println(label + ".firstHook="
                + isHelperCall(instructions.getFirst()));
        System.out.println(label + ".helperCalls=" + calls);
    }

    private static boolean isHelperCall(Instruction instruction) {
        return instruction instanceof InvokeInstruction call
                && call.opcode() == Opcode.INVOKESTATIC
                && call.owner().asSymbol().equals(HELPER)
                && call.name().equalsString("hit");
    }

    public static void main(String[] args) throws Exception {
        report("original",
                Path.of("app-classes/demo/app/Greeter.class"));
        report("transformed",
                Path.of("transformed/demo/app/Greeter.class"));
    }
}
~~~

**Lệnh chạy:**

~~~bash
javac --release 24 -d tool-classes tools-src/VerifyBytecode.java
java -cp tool-classes VerifyBytecode
~~~

**Stdout chính xác đã kiểm thử:**

~~~text
original.firstHook=false
original.helperCalls=0
transformed.firstHook=true
transformed.helperCalls=1
~~~

`firstHook` chỉ kiểm tra **instruction thực thi đầu tiên** (lọc bỏ pseudo-elements như line/label) có phải helper invocation không. `helperCalls` đếm tất cả những instruction `INVOKESTATIC` có đúng **owner + name** trong `greet`. Với lớp demo chỉ có một `hit()` không overload, kiểm tra này phù hợp. Với agent production, nên kiểm tra thêm **descriptor** `()V`/`i.typeSymbol()` để tránh nhầm các overload cùng tên.

### 12.1. Vì sao kiểm tra cả opcode thay vì chỉ tìm chuỗi `Probe`?

Một class có thể chứa tên helper trong constant pool vì metadata, string hoặc code khác, nhưng **không thực sự gọi helper**. Duyệt `InvokeInstruction` và xác minh:

~~~text
opcode = INVOKESTATIC
owner  = demo.agent.Probe
name   = hit
type   = ()V
~~~

sát với instruction thực thi hơn việc tìm chuỗi `"Probe"` trong bytes hoặc tìm name trong constant pool.

Với test nghiêm ngặt hơn, hãy kiểm tra:

- Chính xác **một** `INVOKESTATIC Probe.hit:()V` trong method đích.
- Không có call đó ở class/method không được chọn.
- Instruction xuất hiện ở đầu phần code của method được chọn.
- Class có thể được JVM verify và chạy đúng trong một JVM thử riêng.
- Bytecode cũ vẫn tồn tại theo đúng thứ tự và semantics.
- Kết quả và exception của business method không bị thay đổi trong các tình huống test.

## 13. Tại sao chỉ nhìn stdout chưa đủ để xác minh instrumentation?

Nếu chỉ thấy dòng `hook.hit=1`, nhiều nguyên nhân có thể tạo ra output tương tự:

- Lời gọi helper **được viết sẵn trong source** thay vì do agent chèn.
- Agent chỉ in `hook.hit=1` trong `premain`.
- Có một wrapper khác gọi helper bên ngoài class đích.
- Đoạn code đã được instrument từ lần build trước, không phải lúc class loading.
- Có hai lời gọi helper nhưng code chỉ in một lần do sampling hoặc flag.

Thí nghiệm này dùng bằng chứng độc lập:

| Bằng chứng | Điều khẳng định |
| --- | --- |
| Source của `Greeter` không chứa `Probe.hit()` | Helper không được gọi từ source gốc |
| Baseline `helper.hits=0` | Chưa có biến đổi khi không chạy agent |
| `agent.transform=demo/app/Greeter` | Callback agent khớp class đích |
| Parse bytes mới và `agent.hookCount=1` | Class-file output có một instruction gọi helper |
| `javap` original vs transformed | Bytecode thực sự có opcode mới và offsets thay đổi |
| `VerifyBytecode` chạy độc lập | Không chỉ phụ thuộc log của transformer |
| JVM `-Xverify:all` và `result=Hello Java` | Test chạy được và kết quả nghiệp vụ không đổi |

**Nguyên tắc:** mỗi công cụ xác minh một tầng. `javap` giúp quan sát instruction; Class-File API giúp assert chính xác; JVM verifier và test runtime xác minh bytecode khả thi trên JVM cụ thể. Không dùng một tầng để thay thế toàn bộ các tầng còn lại.

## 14. Vì sao chèn `invokestatic` trước code element đầu hoạt động ở đây?

Mã `greet(String)`:

~~~java
public static String greet(String name) {
    return "Hello " + name;
}
~~~

Không phải constructor, không có try/catch, không giữ monitor, và helper `hit()`:

- **Không nhận đối số** nên không cần lấy value từ stack/local.
- **Trả `void`** nên không để kết quả trên operand stack.
- Không chỉnh `this` hay class initialization order của constructor.
- Không can thiệp nhánh jump/exception handler trong method đơn giản này.

Nhưng `invokestatic` **có thể gây side effect và ném exception**. Trong demo, helper chỉ in và tăng counter; nếu helper lỗi hoặc class không resolve được, method nghiệp vụ có thể không chạy tiếp. Vì thế “chèn một lời gọi trước body” không bảo đảm **semantics không đổi** trong mọi trường hợp.

### 14.1. Một số tình huống cần chiến lược khác

| Dạng method | Rủi ro khi chèn như demo | Cách tiếp cận |
| --- | --- | --- |
| `<init>` | `this` chưa hoàn tất initialization; có quy tắc verifier chặt | Đặt hook ở vị trí an toàn sau lệnh super/this constructor theo thiết kế |
| `<clinit>` | Reentrancy/class initialization order, helper làm load class | Chỉ instrument có chủ đích, guard circular initialization |
| Method có try/catch/finally | Labels, exception-handler ranges và stack map offsets | Dùng transform kiểm soát phạm vi và test mọi đường exception |
| Method synchronized | Chi phí/exception khi giữ monitor; deadlock logging | Helper non-blocking/guard, kiểm tra monitor lifecycle |
| Method overload `greet` | Lọc theo tên có thể instrument nhiều chữ ký | Lọc thêm descriptor |
| Method native hoặc abstract | **Không có `Code`** trong chính method | Không dùng transformingMethodBodies để chèn code trực tiếp |
| Bridge/synthetic | Có thể được compiler gọi tự động, đếm trùng | Filter access flags và hiểu call graph |
| Class do plugin loader định nghĩa | Target có thể không resolve helper | Kiểm soát loader/module visibility |
| Class JDK/core runtime | Circularity hoặc verifier/module constraints | Exclude và nghiên cứu riêng |
| Retransformation | Nguy cơ chèn lặp, thay đổi schema không hợp lệ | Idempotence, capability và kiểm thử retransform |

Đối với code phức tạp, nên kiểm tra số stack slots/exception handler/StackMapTable, class-loader-specific hierarchy resolution và khả năng method exit exceptional path. `ClassFile.of()` có các options về stack maps/debug/line numbers và hierarchy resolver; **mặc định không loại bỏ nhu cầu test** trên những class mà agent sẽ xử lý.

## 15. Lỗi dễ gặp với Class-File API JDK 24

### 15.1. Lỗi phiên bản JDK

~~~text
error: package java.lang.classfile does not exist
~~~

Nguyên nhân thường gặp: đang compile trên JDK 17/21 hoặc compiler/runtime không đúng JDK 24. Không chữa bằng `--add-exports` vì package **chưa có** trên JDK cũ. Dùng JDK 24+ phù hợp với API của ví dụ.

### 15.2. Sai descriptor hoặc helper không thấy được

- `NoSuchMethodError`: bytecode gọi sai name/descriptor.
- `NoClassDefFoundError`: loader của target không resolve được helper hoặc phụ thuộc helper.
- `IllegalAccessError`: class/method/package/module không cho phép truy cập.
- `IncompatibleClassChangeError`: opcode static/instance không khớp dạng method.
- `ExceptionInInitializerError`: helper class initialization thất bại.

Với bài, agent JAR được đặt thêm vào classpath rõ ràng để `demo.app.Main`/`Greeter` và helper nằm trong môi trường nạp lớp có khả năng tương tác. Trong plugin loaders hoặc named modules, cần thiết kế loader và JPMS reads/exports/opens, không mặc định một cấu hình demo dùng được cho mọi ứng dụng.

### 15.3. Quên `out.with(element)`

Nếu chỉ emit `invokestatic` mà không chuyển các phần tử code cũ, builder sẽ không giữ nguyên thân method, có thể tạo code vô nghĩa hoặc không hợp lệ. `CodeTransform` cho phép **thay thế/bỏ** elements bằng cách không gọi `with` — đó là chức năng có chủ đích của API, không phải mặc định giữ nguyên.

### 15.4. Lặp hook khi biến đổi lại

Nếu transform được áp dụng **hai lần** lên bytes đã có hook, có thể xuất hiện hai `invokestatic Probe.hit`. Bản demo dùng initial-load transform và không đăng ký retransform; không phải cơ chế chống lặp cho mọi trường hợp.

Trong agent thật:

1. Parse bytes và kiểm tra trước khi chèn (chỉ chèn nếu chưa có pattern/marker phù hợp).
2. Đăng ký transformer với capability chính xác; không cho callback được gọi không cần thiết.
3. Không dùng marker name chung dễ va chạm với mã ứng dụng.
4. Test nhiều transformer/agent cùng chạy, bytecode đã sửa và lần redefine/retransform.
5. Gỡ transformer không tự xóa hook khỏi class đã load.

### 15.5. Không xử lý lỗi transform, rồi tưởng đã instrument

Javadoc `ClassFileTransformer` nói rằng khi transformer ném exception chưa bắt, JVM **vẫn tiếp tục xử lý** các transformer khác và attempt load/redefine; trong nhiều tình huống điều này tương đương **trả `null`**. Vì vậy **lỗi trong transform không đồng nghĩa chương trình chắc chắn dừng ngay**, và hệ thống có thể chạy **không có hook**.

Một agent production cần ghi diagnostic qua kênh an toàn, có counter transform failures và test output. Không dùng exception ném ra như một cơ chế fail-fast đáng tin cậy cho agent. Trong demo, kiểm chứng độc lập và stdout giúp nhận ra nếu class không được sửa.

### 15.6. Mutate input bytes hoặc dùng model qua threads

Hợp đồng `ClassFileTransformer` yêu cầu **không sửa mảng `classfileBuffer` đầu vào**; trả mảng mới nếu đã biến đổi. Bản demo dùng `transformClass` để dựng `changed`, không sửa `bytes`.

`ClassModel` có cơ chế parse lazy và tài liệu JDK 24 cảnh báo model có thể không thread-safe khi chia sẻ; đừng cache một model mutable/lazy để nhiều callback đồng thời thao tác mà không có biện pháp phù hợp. Nếu cần xử lý parallel, tạo model theo nhiệm vụ hoặc đồng bộ/đóng gói snapshot an toàn.

### 15.7. Ghi log/I/O đồng bộ trong transformer

Trong bài, `System.out.println` và `Files.write` làm bằng chứng thực nghiệm. Trong production đây là anti-pattern: có thể gây circular class initialization, chặn class load, tăng allocation và recursive instrumentation. Nên giới hạn matcher sớm và chuyển việc phân tích nặng/export ra khỏi callback khi phù hợp.

## 16. Các lựa chọn thiết kế nếu đưa thử nghiệm thành Java agent thực tế

Một lộ trình mở rộng hợp lý:

1. **Chọn class theo internal name, loader và module**, exclude `agent/helper/logger/exporter` ngay trước parse.
2. **Chọn method bằng name + descriptor**, tránh constructor/native/abstract/bridge nếu chưa có chiến lược riêng.
3. **Thiết kế helper API ổn định và ít phụ thuộc**, có fail-open guard và không tự instrument.
4. **Thiết kế điểm chèn an toàn** cho entry/exit, normal/exceptional exit, try/finally, synchronized và constructors.
5. **Đặt idempotence check**, không tạo hook trùng nếu class được transform nhiều lần.
6. **Xác minh bytecode hai tầng**: Class-File API scan instructions và JVM verification/runtime tests.
7. **Giới hạn chi phí**: sampling, bounded buffer, không xử lý I/O nặng trong callback.
8. **Tôn trọng classloader/JPMS**: target có thể không nhìn thấy helper; dùng shared bridge hoặc cấu hình phù hợp.
9. **Định nghĩa lifecycle**: disable helper khác với remove transformer; rollback loaded class cần retransform/redefine có điều kiện.
10. **Kiểm thử trên nhiều class patterns**: methods có branches/exceptions/lambdas, packages/modules, multi-loader và concurrency.

**Quan trọng về stack maps:** Class-File API có thể tự phát sinh hoặc cập nhật một số thông tin cấu trúc khi dựng lại class file tùy options/defaults. Nhưng agent vẫn phải chịu trách nhiệm **đúng type flow và class hierarchy**: nếu các referenced classes không visible với resolver mặc định, phải cung cấp hierarchy resolver phù hợp hoặc cách kiểm thử/biến đổi khác. Không tự hủy `StackMapTable` nhằm “vượt” verifier.

### 16.1. Khi nào dùng `javap`, khi nào dùng API verifier?

| Cách | Mạnh ở đâu? | Hạn chế |
| --- | --- | --- |
| `javap -c -p` | Người học thấy ngay opcode/offset/symbolic reference | Output text có thể đổi format hoặc constant-pool index |
| `ClassFile.of().parse` + `InvokeInstruction` | Assertion máy kiểm tra được owner/name/opcode/type | Chỉ là structural check, chưa chạy JVM |
| `java -Xverify:all` | JVM kiểm tra và chạy class file thật | Không chứng minh business semantics ở mọi input |
| Unit/integration tests | Kiểm tra return, exception, concurrency, perf | Chỉ bao phủ các case thực sự kiểm thử |
| Bytecode dump diff | Cho phép debug biến đổi rõ ràng | Không nên dump mọi class trong production |

Kết hợp cả nhiều lớp kiểm thử thay vì coi một chữ `"success"` của transformer là bằng chứng đủ.

## 17. Checklist thực hành

- [ ] Dùng **JDK 24** và `javac --release 24` cho mã Class-File API này.
- [ ] Agent có `Premain-Class` đúng và được chạy bằng `-javaagent`.
- [ ] Transformer được đăng ký **trước khi `Greeter` được load**.
- [ ] Matcher chỉ chọn `demo/app/Greeter`, không chọn helper/agent.
- [ ] `ClassDesc` dùng `demo.agent.Probe`, callback `className` dùng `demo/app/Greeter`.
- [ ] Descriptor `()V` phù hợp `public static void hit()`.
- [ ] `CodeTransform` chỉ chèn một lần và giữ mọi `CodeElement` gốc bằng `out.with(element)`.
- [ ] `transformClass` trả `byte[]` mới và không sửa `classfileBuffer`.
- [ ] Baseline không agent có `helper.hits=0`.
- [ ] Với agent, kết quả `greet` không đổi và helper được gọi một lần.
- [ ] `VerifyBytecode` xác nhận trước 0, sau 1, instruction đầu đúng helper.
- [ ] `javap` cho thấy instruction `invokestatic` mới trước `aload_0`.
- [ ] `-Xverify:all` không báo `VerifyError`.
- [ ] Không lấy constant-pool index/offset cố định làm API contract trên mọi compiler.
- [ ] Khi chuyển production, bỏ dump/log I/O đồng bộ, thêm idempotence, error policy và multi-loader tests.

## 18. Câu hỏi tự kiểm tra

1. Vì sao `java.lang.classfile` trong bài yêu cầu JDK 24 chứ không thể biên dịch nguyên văn bằng Java 17?
2. `ClassFile.of().parse(bytes)` trả kiểu model nào, và `ClassFile.transformClass` trả kiểu dữ liệu gì?
3. Vì sao `CodeBuilder.invokestatic` cần cả `ClassDesc` lẫn `MethodTypeDesc`?
4. Tại sao `"demo/app/Greeter"` dùng ở matcher nhưng `ClassDesc.of("demo.agent.Probe")` dùng dấu chấm?
5. Điều gì xảy ra nếu bỏ `out.with(element)` khỏi `CodeTransform`?
6. Vì sao `CodeTransform.ofStateful` hữu ích ngay cả khi demo chỉ instrument một method?
7. Lệnh `-Xverify:all` chứng minh điều gì, và chưa chứng minh điều gì?
8. Vì sao `Main` có thể import `Probe` để đọc counter mà `Greeter` không cần import helper trong source?
9. `javap` trước/sau cho thấy instruction nào được thêm ở offset 0?
10. Vì sao không nên viết assertion rằng constant-pool index của helper luôn là `#37`?
11. Vì sao một callback lỗi có thể khiến JVM tiếp tục chạy mà class không được instrument như mong đợi?
12. Nếu muốn chèn vào hai overload `greet` khác nhau, bạn sẽ thay predicate thế nào?
13. Vì sao constructor `<init>` không nên áp dụng máy móc vị trí chèn của demo?
14. Vì sao helper có `System.out.println` phù hợp demo nhưng không phù hợp agent đo hàng triệu calls/s?
15. Thử thay `Greeter.greet` thành method có nhánh và exception: cần bổ sung những kiểm thử bytecode nào?
16. Nếu class do plugin loader định nghĩa không resolve được `demo.agent.Probe`, lỗi nào có thể xuất hiện?
17. Nếu muốn instrument class đã load, tại sao phải nghiên cứu `retransformClasses` và khả năng chèn lặp?
18. Vì sao chương trình `VerifyBytecode` độc lập tăng độ tin cậy so với chỉ đọc `agent.hookCount`?
19. Một method `native` không có `Code` có thể áp dụng `transformingMethodBodies` để thêm JVM instruction trực tiếp vào native body không?
20. Khi chuyển sang production, bước nào đảm bảo trạng thái ứng dụng không bị phá nếu helper hoặc exporter lỗi?

**Kết luận:** Thí nghiệm đã tạo thành công **một Java agent thật với Class-File API JDK 24**: `ClassFile.parse` đọc class-file bytes, `ClassTransform.transformingMethodBodies` chọn `greet`, `CodeBuilder.invokestatic` chèn `Probe.hit()` trước instruction gốc và `ClassFile.transformClass` trả bytes mới cho JVM. Bản gốc có **0** helper call; bản mới có **1**, và lời gọi mới được chứng minh bằng `javap`, bộ kiểm tra Class-File API độc lập và thực thi dưới `-Xverify:all`. Hãy giữ sự khác biệt giữa **đúng một demo cụ thể đã kiểm chứng** và **agent production tổng quát**: constructor/exception flow/loader/module/concurrency/idempotence vẫn cần thiết kế và kiểm thử riêng.

### Tài liệu chính thức

- [JDK 24 — java.lang.classfile package: parse/build/transform models](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html)
- [JDK 24 — ClassFile: parse và transformClass](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [JDK 24 — ClassTransform: transformingMethodBodies](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html)
- [JDK 24 — CodeTransform: ofStateful](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeTransform.html)
- [JDK 24 — CodeBuilder: invokestatic](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html)
- [JDK 24 — InvokeInstruction và Opcode](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/instruction/InvokeInstruction.html)
- [JDK 24 — ClassFileTransformer contract](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JEP 484 — Class-File API chuẩn hóa trong JDK 24](https://openjdk.org/jeps/484)
