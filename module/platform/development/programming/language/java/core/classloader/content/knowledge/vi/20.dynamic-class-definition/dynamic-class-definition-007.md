# Instrumentation: transform trước khi định nghĩa lớp

Trong Java, **instrumentation** là cách quan sát hoặc điều chỉnh **bytecode của class** để bổ sung chức năng như tracing, đo thời gian, thu thập coverage hoặc thay đổi một phần hành vi mà không cần sửa trực tiếp mã nguồn ứng dụng. Với **load-time instrumentation**, JVM cho một `ClassFileTransformer` cơ hội nhận bytes ClassFile, biến đổi chúng và trả bytes mới **trước khi class được định nghĩa** bởi JVM.

Chủ đề quan trọng ở đây là **thời điểm transform**, không chỉ thuật ngữ “agent”. Một transform được đăng ký sớm có thể thay đổi bytes mà JVM chuẩn bị sử dụng trong `defineClass`; trái lại, khi class đã được định nghĩa, tạo thêm transformer **không tự chạy lại quá trình định nghĩa đó**. Trường hợp sau cần cơ chế riêng như `retransformClasses` hoặc `redefineClasses` nếu JVM/class hỗ trợ và các ràng buộc được thỏa mãn.

**Ý tưởng cốt lõi:**

~~~text
Agent được khởi động bằng -javaagent
         |
         v
premain(..., Instrumentation)
         |
         v
instrumentation.addTransformer(transformer)
         |
         v
ClassLoader yêu cầu định nghĩa một class mới
         |
         v
JVM/Instrumentation gọi ClassFileTransformer.transform(...)
         |
         +--- trả null ---> giữ bytecode hiện tại
         |
         +--- trả byte[] --> dùng bytes đã biến đổi cho bước tiếp
         |
         v
các transformer tiếp theo (nếu có)
         |
         v
JVM kiểm tra, liên kết, định nghĩa Class<?> theo quy tắc
         |
         v
class được sử dụng/khởi tạo khi thích hợp
~~~

Đây là đường đi **khái quát**. Transformer có thể được gọi ở những ngữ cảnh ngoài new class loading, tùy registration/capabilities; JVM cũng thực hiện nhiều bước kiểm tra và liên kết khác không thể giản lược thành một lời gọi `defineClass` duy nhất. Quan trọng nhất: **trả bytecode đã biến đổi không có nghĩa bypass verifier, access control, type identity hoặc module rules**.

Bài này trình bày `java.lang.instrument` trong Java 17, Java agent, `ClassFileTransformer`, `Instrumentation.addTransformer`, thứ tự transform, các cơ chế load/retransform/redefine, lỗi thường gặp, và một **demo Java 17 tự chạy** thay giá trị chuỗi trong constant pool trước khi JVM định nghĩa class mục tiêu.

## 1. Phân biệt instrumentation và class loading thông thường

**Class loading** giải quyết câu hỏi: “Ai tìm, nạp và định nghĩa ClassFile này?” Với class loader tùy chỉnh, câu trả lời thường xuất hiện quanh `loadClass`, `findClass` và `defineClass`. JVM dùng **binary name + defining class loader** làm một phần định danh runtime của class/interface.

**Instrumentation** giải quyết câu hỏi khác: “Trước khi định nghĩa/áp dụng class bytes, có được quan sát hoặc thay đổi biểu diễn ClassFile không?”

| Thành phần | Vai trò | Điều không tự thực hiện |
| --- | --- | --- |
| `ClassLoader.loadClass` | Tìm Class theo tên, dùng cache/delegation theo chính sách | Không tự instrument mọi ClassFile |
| `ClassLoader.findClass` | Subclass tìm nguồn bytecode rồi có thể `defineClass` | Không phải hook instrumentation chuẩn toàn JVM |
| `ClassLoader.defineClass` | Đề nghị JVM định nghĩa class từ bytes theo loader/name | Không bảo đảm bytes được nhận chính xác như ban đầu nếu có transformer |
| `Instrumentation` | API do JVM cấp cho agent để đăng ký transformers, truy vấn và yêu cầu một số thao tác | Không phải ClassLoader và không tự bảo đảm mọi class đều modifiable |
| `ClassFileTransformer` | Nhận ClassFile bytes để biến đổi/quan sát ở giai đoạn JVM xử lý định nghĩa hoặc cập nhật | Không tự nạp một class hay tạo một defining loader mới |
| `-javaagent` + `premain` | Đưa agent vào JVM khi khởi động, trước application `main` | Không hứa mọi class nền tảng còn chưa được load khi agent đăng ký |

Cùng một binary name `com.example.Service` mà hai defining loader khác nhau định nghĩa thì vẫn là **hai class JVM khác nhau**, dù instrumentation áp dụng cùng phép biến đổi. Transformer **không hợp nhất type identity** của chúng.

### Cơ chế tải lớp tùy chỉnh và agent có thể cùng tồn tại

~~~text
Host / plugin yêu cầu loadClass("plugin.impl.Task")
                    |
                    v
          PluginClassLoader.findClass
                    |
                    v
                 byte[] ClassFile
                    |
                    v
       defineClass(name, bytes, off, len)
                    |
                    v
        JVM transformer chain có thể chạy
                    |
                    v
          Class<?> của PluginClassLoader
~~~

Nếu dùng `Instrumentation` được JVM quản lý, transformer sẽ có cơ hội xử lý **class definition mới** theo registration của agent, kể cả class được custom loader định nghĩa. Điều này **không đồng nghĩa mọi class chắc chắn được chỉnh**: transformer thường lọc theo `className`, loader, module, class redefinition state hoặc chính sách ứng dụng.

Một loader còn có thể **tự thay bytes** trước `defineClass`, chẳng hạn thực hiện một bước preprocess bytecode của riêng nó. Khi đó phải phân biệt **bytes mà loader chủ động đổi** với **transformer do JVM gọi** trong đường instrumentation. Cả hai diễn ra trước khi class tương ứng hoàn tất định nghĩa nhưng thuộc các tầng API khác nhau.

## 2. Java agent được kích hoạt như thế nào?

Một Java agent thông thường được đóng gói thành **JAR riêng** có main manifest attribute:

~~~text
Premain-Class: Agent
~~~

Trong đó `Agent` là **binary name của agent class**, không phải tên file `Agent.java` hay đường dẫn `Agent.class`. Agent class cung cấp method public static:

~~~java
public static void premain(
        String agentArgs, java.lang.instrument.Instrumentation inst) {
    // đăng ký transformer trước khi application main chạy
}
~~~

Đây là **fragment chữ ký**, không phải chương trình độc lập. Trường hợp khởi động JVM với:

~~~bash
java -javaagent:transform-agent.jar -cp app-classes demo.Main
~~~

JVM khởi tạo agent, gọi `premain`, sau khi `premain` hoàn tất mới gọi `demo.Main.main`. Nếu thiếu `Premain-Class`/method phù hợp hoặc `premain` ném lỗi chưa xử lý, việc khởi động agent có thể thất bại và JVM chấm dứt trước khi application chạy.

### Phân biệt premain, agentmain và main

- `premain`: đường agent khởi động bằng `-javaagent`, được gọi **trước application `main`**.
- `agentmain`: đường agent được khởi động **sau khi JVM đã chạy** thông qua cơ chế attach được runtime hỗ trợ; thường dùng manifest attribute `Agent-Class`. Không phải JVM nào hoặc cấu hình nào cũng cho phép dynamic attach.
- `main`: entry point ứng dụng thông thường; không phải callback instrumentation.

Bài này dùng **`premain`**, vì muốn chứng minh một transform diễn ra **trước khi class `demo.Greeter` được định nghĩa lần đầu**. Không dùng attach/retransform để cố chỉnh class đã load.

**Chú ý phạm vi JVM:** `premain` chạy trước application `main` nhưng JVM đã khởi tạo và có thể đã nạp một số class nội bộ/JDK để gọi agent. Không thể suy “agent bắt đầu trước mọi class loading của JVM”.

### Multiple agents có tương tác thế nào?

JVM có thể khởi động nhiều agent thông qua nhiều tùy chọn `-javaagent`. Khi nhiều transformer tồn tại, các kết quả được **xâu chuỗi** theo nhóm/thứ tự registration phù hợp hợp đồng `ClassFileTransformer`. Một transformer có thể nhận **bytes đã được transformer trước thay đổi**, nên tính tương thích và idempotency rất quan trọng. Không viết code dựa vào giả định “transformer của tôi luôn nhận đúng file gốc trên disk”.

## 3. ClassFileTransformer.transform nhận và trả dữ liệu gì?

Một trong hai overload của `ClassFileTransformer` (overload lịch sử vẫn dùng được ở Java 17):

~~~java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    // trả null nếu không đổi bytes
    return null;
}
~~~

Đây là **fragment** dùng bên trong một implementation của `ClassFileTransformer`. Ý nghĩa các tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `loader` | ClassLoader tham gia định nghĩa class; có thể là `null` cho bootstrap loader theo API. |
| `className` | Tên class theo dạng **internal name** với dấu `/`, ví dụ `demo/Greeter`. Có ngữ cảnh mà giá trị có thể null; không dereference mù quáng. |
| `classBeingRedefined` | Thường `null` khi đang định nghĩa class lần đầu; có Class tương ứng khi redefinition/retransformation theo trường hợp. |
| `protectionDomain` | Miền bảo vệ liên quan class, có thể cần cho chính sách/diagnostics. |
| `classfileBuffer` | Bytes ClassFile hiện tại mà transformer được yêu cầu xử lý; **không được sửa trực tiếp array đầu vào**. |

Java 9+ còn có overload:

~~~java
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
~~~

Đây là **chữ ký fragment**, không phải method body; `module` giúp biết module liên quan khi transform named-module classes. Java 17 cho phép override overload 5 đối số; overload 6 đối số có default implementation chuyển tiếp vào overload cũ theo API. Nếu cần filter theo JPMS module, có thể override overload chứa `Module`.

**Kết quả:**

- Trả **`null`** khi không sửa bytes: JVM tiếp tục dùng bytes hiện tại của transformer chain.
- Trả **mảng `byte[]` mới** chứa một biểu diễn ClassFile phù hợp khi muốn biến đổi. Cần bảo toàn định dạng ClassFile hợp lệ, không hỏng constant pool/method descriptors.
- Không sửa tại chỗ `classfileBuffer`: clone/copy hoặc thư viện bytecode có output buffer riêng. API cho phép JVM dùng buffer gốc ở những bước khác; sửa tại chỗ là sai hợp đồng.
- Nếu class bị JVM từ chối vì định dạng, kiểm tra hoặc type constraints thì transformer **không thể ép class ấy trở thành hợp lệ** chỉ bằng việc return một mảng tùy tiện.

### Tại sao className có dấu slash?

`className` trong callback dùng **internal form**:

~~~text
Binary name:       demo.Greeter
Transformer name:  demo/Greeter
Class file path:   demo/Greeter.class
~~~

Nếu viết `if ("demo.Greeter".equals(className))` trong transformer thì callback sẽ **không** bắt mục tiêu dự kiến. Trong ví dụ bên dưới dùng:

~~~java
if (!"demo/Greeter".equals(name)) {
    return null;
}
~~~

Đây là fragment đúng theo signature callback. Nên thêm điều kiện về **loader identity** nếu chương trình có nhiều bản cùng tên mà chỉ muốn biến đổi một defining loader cụ thể; lọc tên đơn thuần sẽ tác động mọi class mới thỏa tên ở nhiều loader.

## 4. Ví dụ Java 17 hoàn chỉnh: thay một UTF8 constant trước khi define class

Ví dụ tự chứa này có ba source files:

- `demo.Greeter` trả chuỗi literal `ORIGINAL`.
- `demo.Main` in kết quả gọi `Greeter.message()`.
- `Agent` đăng ký `ClassFileTransformer`. Khi JVM sắp định nghĩa `demo/Greeter`, transformer tìm một entry **`CONSTANT_Utf8_info`** trong constant pool chứa đúng tám byte ASCII `ORIGINAL`, tạo **bản sao byte array**, đổi sang tám byte `PATCHED!`, rồi trả array mới.

Hai chuỗi **cùng số byte (8)** để ví dụ tránh phải cập nhật cấu trúc/độ dài constant pool entry. Khác với thay byte tùy tiện ở mọi vị trí trong ClassFile, parser minh họa chỉ xét **các entry constant pool có tag UTF8 và đúng độ dài**. Đây là kỹ thuật học tập có scope rất hẹp; trong sản phẩm thực tế nên dùng thư viện bytecode chuyên dụng thay vì tự viết parser/transformer dạng byte patch.

### 4.1. Cấu trúc project

~~~text
instrumentation-demo/
├── src/
│   ├── Agent.java
│   └── demo/
│       ├── Greeter.java
│       └── Main.java
├── agent.mf
├── agent-classes/       (javac tạo)
├── app-classes/         (javac tạo)
└── transform-agent.jar  (jar tạo)
~~~

### 4.2. File src/demo/Greeter.java

~~~java
package demo;

public final class Greeter {
    public static String message() {
        return "ORIGINAL";
    }
}
~~~

Chuỗi `ORIGINAL` xuất hiện trong constant pool của ClassFile `demo.Greeter` do `javac --release 17` tạo. `message()` là method được app gọi, nên việc đổi literal trong ClassFile làm kết quả runtime thay đổi. Đây không phải phép sửa Java source trong file `Greeter.java`.

### 4.3. File src/demo/Main.java

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Message: " + Greeter.message());
    }
}
~~~

Code gọi method `Greeter.message()`, không dùng `public static final String` được compile-time constant-fold vào `Main`. Cách viết này giúp quan sát trực tiếp biến đổi bytes của `Greeter`, không vướng chuyện hằng số đã được inline ở caller.

### 4.4. File src/Agent.java

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;
import java.util.Arrays;

public final class Agent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("Agent ready");
        inst.addTransformer(new PatchTransformer(), false);
    }

    private static final class PatchTransformer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(ClassLoader loader, String name,
                Class<?> redefining, ProtectionDomain domain,
                byte[] bytes) {

            if (!"demo/Greeter".equals(name)
                    || redefining != null) {
                return null;
            }

            byte[] replacement =
                    patchConstantUtf8(bytes, "ORIGINAL", "PATCHED!");

            if (replacement != null) {
                System.out.println("Transformed: demo.Greeter");
            }

            return replacement;
        }
    }

    private static byte[] patchConstantUtf8(
            byte[] bytes, String original, String replacement) {

        byte[] from = original.getBytes(StandardCharsets.US_ASCII);
        byte[] to = replacement.getBytes(StandardCharsets.US_ASCII);

        if (from.length != to.length) {
            throw new IllegalArgumentException("length");
        }

        byte[] copy = bytes.clone();
        ByteBuffer cp = ByteBuffer.wrap(copy)
                .order(ByteOrder.BIG_ENDIAN);

        if (cp.getInt() != 0xCAFEBABE) {
            return null;
        }

        cp.getShort(); // minor version
        cp.getShort(); // major version
        int cpCount = Short.toUnsignedInt(cp.getShort());
        int patches = 0;

        for (int i = 1; i < cpCount; i++) {
            int tag = Byte.toUnsignedInt(cp.get());

            switch (tag) {
                case 1: {
                    int size = Short.toUnsignedInt(cp.getShort());
                    int start = cp.position();

                    if (size == from.length
                            && Arrays.equals(
                                    copy, start, start + size,
                                    from, 0, from.length)) {

                        System.arraycopy(
                                to, 0, copy, start, to.length);
                        patches++;
                    }

                    cp.position(start + size);
                    break;
                }

                case 3: case 4: case 9: case 10:
                case 11: case 12: case 17: case 18:
                    cp.position(cp.position() + 4);
                    break;

                case 5: case 6:
                    cp.position(cp.position() + 8);
                    i++;
                    break;

                case 7: case 8: case 16:
                case 19: case 20:
                    cp.position(cp.position() + 2);
                    break;

                case 15:
                    cp.position(cp.position() + 3);
                    break;

                default:
                    throw new IllegalArgumentException("tag: " + tag);
            }
        }

        return patches == 1 ? copy : null;
    }
}
~~~

**Giải thích code Agent:**

1. `premain` được JVM gọi trước application `main` khi lệnh chạy có `-javaagent`. Nó in `Agent ready` và đăng ký transformer bằng `inst.addTransformer(..., false)`. Giá trị `false` nghĩa transformer **không được đăng ký là retransformation-capable**; demo chỉ quan tâm initial class definition.
2. `transform` được JVM gọi khi định nghĩa class mới và trong những tình huống redefinition phù hợp API. Nó trả `null` cho mọi tên khác `demo/Greeter` hoặc khi đang xử lý lại một Class đã định nghĩa. Trong demo chuẩn chỉ có một class mới phù hợp.
3. `patchConstantUtf8` đọc **magic `CAFEBABE`**, minor/major version, số entries trong constant pool rồi lần lượt bỏ qua những entry theo độ rộng tương ứng. Tag `1` là `CONSTANT_Utf8_info`.
4. Với tag `1`, code lấy độ dài entry từ `u2` và so đúng tám byte ASCII. Nếu bằng `ORIGINAL`, nó copy tám byte `PATCHED!` **vào mảng clone**, không sửa mảng gốc của JVM.
5. Tag `5`/`6` (long/double) chiếm hai vị trí constant-pool index nên code tăng `i` thêm một. Các tag còn lại được skip theo định dạng ClassFile hỗ trợ đến Java 17.
6. Chỉ khi **chính xác một entry được sửa**, transformer trả byte array mới. Nếu không tìm được hoặc gặp hai entry phù hợp, nó trả `null` để demo không dùng một phép thay không rõ kết quả. Đây là cách tối thiểu hóa thay đổi trong ví dụ.
7. Khi transformer trả mảng đã thay, JVM tiếp tục các bước định nghĩa/kiểm tra class; sau đó `Greeter.message()` trả `PATCHED!`.

**Giới hạn parser:** Đây là parser tối giản để học, không có các kiểm tra biên đầy đủ như một công cụ đọc ClassFile không tin cậy. Nó chỉ thay ASCII trong một `CONSTANT_Utf8_info` có cùng byte length. Java ClassFile dùng **modified UTF-8** cho `CONSTANT_Utf8_info`, nên phương pháp mã hóa ASCII đơn giản **không áp dụng tổng quát** cho Unicode tùy ý, chuỗi dài khác kích thước, đổi tên class, đổi method descriptor, đổi stack map frames hoặc sửa control flow.

Nếu muốn thêm advice vào method, thay đổi instruction list hoặc instrument ứng dụng thật, nên dùng **ASM, Byte Buddy hoặc công cụ bytecode hiểu ClassFile**, cập nhật constant pool, offsets, StackMapTable, exception tables và các metadata liên quan một cách hợp lệ. Không tìm-thay bytes thô trên toàn JAR rồi hy vọng verifier chấp nhận.

### 4.5. File agent.mf

Nội dung file `agent.mf`:

~~~text
Premain-Class: Agent
~~~

Lưu file ở root project. Công cụ `jar --manifest agent.mf` sẽ tạo main manifest trong agent JAR; nó có thể bổ sung các thuộc tính manifest thông thường theo hành vi `jar`. Demo **không** cần `Agent-Class` vì không dùng dynamic attach và không cần `Can-Retransform-Classes: true` vì đăng ký transformer với `false`.

### 4.6. Build, đóng gói và chạy trên Java 17

Từ thư mục `instrumentation-demo`, trước hết tạo hai output directories.

Trên Bash/Linux/macOS:

~~~bash
mkdir -p agent-classes app-classes
javac --release 17 -d agent-classes src/Agent.java
javac --release 17 -d app-classes src/demo/Greeter.java src/demo/Main.java
jar --create --file transform-agent.jar --manifest agent.mf -C agent-classes .
java -cp app-classes demo.Main
java -javaagent:transform-agent.jar -cp app-classes demo.Main
~~~

Trên Windows PowerShell, phần build tương đương:

~~~powershell
New-Item -ItemType Directory -Force agent-classes, app-classes | Out-Null
javac --release 17 -d agent-classes src/Agent.java
javac --release 17 -d app-classes src/demo/Greeter.java src/demo/Main.java
jar --create --file transform-agent.jar --manifest agent.mf -C agent-classes .
java -cp app-classes demo.Main
java -javaagent:transform-agent.jar -cp app-classes demo.Main
~~~

**Kết quả đã biên dịch bằng `javac --release 17` và chạy thử trên OpenJDK:**

Khi chạy **không có agent**:

~~~text
Message: ORIGINAL
~~~

Khi chạy **có `-javaagent`**:

~~~text
Agent ready
Transformed: demo.Greeter
Message: PATCHED!
~~~

Những dòng này là **stdout của hai lệnh chạy Java khác nhau**, không phải một lần chạy in tất cả trong một process.

### 4.7. Vì sao kết quả chứng minh transform trước định nghĩa?

- Khi không có agent, JVM load classfile gốc `demo/Greeter.class` và method trả literal `ORIGINAL`.
- Khi có agent, JVM gọi `premain` rồi đăng ký transformer trước `demo.Main.main`.
- Lúc app lần đầu cần `demo.Greeter`, class bytes được transformer kiểm tra, bản clone đã đổi constant pool được trả về **trước khi `Greeter` được định nghĩa và dùng**.
- JVM định nghĩa và sau đó gọi static method của **class đã được instrument**, nên string trả về là `PATCHED!`.
- Không cần xóa hoặc sửa file `src/demo/Greeter.java`, cũng không sửa `app-classes/demo/Greeter.class` trên đĩa. Nếu chạy lại **không có agent**, kết quả là `ORIGINAL`.
- Nếu `Greeter` đã được định nghĩa trước khi agent đăng ký, đường load-time transform **không tự làm lại**; cần xem cơ chế retransform/redefine và khả năng JVM hỗ trợ.

**Không suy ra** loader đã bị thay bằng agent: `demo.Greeter` vẫn được application/system loader định nghĩa trong cách chạy này. Instrumentation thay **class bytes**, không tự tạo một loader mới.

## 5. Mối quan hệ giữa transform và defineClass

Có ba khái niệm thời gian cần tách:

### 5.1. Load-time transform (class chưa định nghĩa)

~~~text
ClassFile source
    |
    v
ClassLoader đọc bytes
    |
    v
defineClass(...)/JVM define request
    |
    v
ClassFileTransformer chain
    |
    v
JVM verify/link/apply ClassFile mới theo quy tắc
    |
    v
Class<?> xuất hiện với defining loader đã chọn
~~~

Điểm quan trọng là **transformer được gọi trước class definition**. Các bước nội bộ khác có thể diễn ra ở thứ tự/pha thích hợp của JVM, vì thế không nên diễn giải sơ đồ thành “tất cả linking/verification chỉ diễn ra đúng một lần và hoàn toàn sau transform” trong mọi JVM.

Một class loader tự xây có thể **chủ động tiền xử lý** ClassFile trước `defineClass`:

~~~java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {

    byte[] original = readBytesFromApprovedSource(name);
    byte[] changed = preprocessBytes(original);

    return defineClass(name, changed, 0, changed.length);
}
~~~

Đây là **fragment triển khai**, hai hàm `readBytesFromApprovedSource` và `preprocessBytes` là helper **chưa định nghĩa**; không phải chương trình độc lập. Nó minh họa đường biến đổi bytes *do loader sở hữu*, khác với callback `ClassFileTransformer` do JVM điều phối.

Một hệ thống có thể có **cả hai**: loader tự preprocess rồi gọi `defineClass`; sau đó JVM gọi transformer đã đăng ký trước khi hoàn tất định nghĩa. Khi debug, phải xác định bytecode tại mỗi giai đoạn.

### 5.2. Retransformation (class đã load)

`Instrumentation.retransformClasses(Class<?>...)` yêu cầu xử lý lại các class **đã tồn tại**, nếu `Instrumentation.isRetransformClassesSupported()` và `isModifiableClass(type)` cho phép. Đây **không phải** nạp một type mới với defining loader mới.

Điểm quan trọng:

- Transformer đăng ký với `canRetransform=true` có thể được gọi lại khi retransform.
- Với transformer **không retransformation-capable** như demo, JVM có thể **tái sử dụng kết quả transform trước** thay vì gọi lại chính method transform trên retransformation.
- Những phép đổi schema như tùy ý thêm/xóa field, method, thay inheritance hoặc một số thuộc tính cấu trúc **bị ràng buộc** trong retransform/redefine; không thể hiểu retransform như đổi ClassFile tự do giống lần định nghĩa đầu.
- JVM vẫn áp dụng method verification, access/module constraints và khả năng hỗ trợ cụ thể.
- Thay bytes của method sau khi class đã load **không làm static fields reset và không tạo `Class<?>` mới**.
- Active stack frames có thể tiếp tục thực thi bytecode cũ theo quy tắc instrumentation; đừng giả định mọi method đang chạy lập tức đổi hành vi tại giữa một frame.

Muốn dùng retransform, agent manifest/capabilities phải phù hợp. Với `-javaagent` có nhu cầu này, `Can-Retransform-Classes: true` thường được khai báo; agent vẫn phải kiểm tra API runtime trước khi gọi `retransformClasses`.

### 5.3. Redefinition (class đã load, bytes do caller cung cấp)

`Instrumentation.redefineClasses(ClassDefinition...)` nhận một hoặc nhiều **ClassDefinition** chứa Class hiện tại và ClassFile bytes thay thế. Đây cũng là cơ chế cho class đã load và tuân theo những giới hạn JVM về các loại biến đổi cấu trúc.

| Cơ chế | Đầu vào và thời điểm | Type identity |
| --- | --- | --- |
| **Load-time transform** | Class mới sắp được định nghĩa, transformer xử lý `classfileBuffer` | Tạo định nghĩa Class theo defining loader hiện tại |
| **Retransform** | Class đã nạp, JVM chạy lại pipeline thích hợp | **Giữ Class<?> identity**; không tạo defining loader mới |
| **Redefine** | Class đã nạp, agent cung cấp `ClassDefinition` mới | **Giữ Class<?> identity**; không định nghĩa class hoàn toàn mới theo tên khác |
| **New loader / new class definition** | Một defining loader khác định nghĩa ClassFile khác hoặc cùng tên | **Type khác** nếu defining loader khác |

Không dùng retransform để “reset” một class đã initialize lỗi hoặc bắt nó chạy lại `<clinit>`. Nếu muốn thử initialization độc lập, cần class definition mới trong loader mới hoặc JVM process mới theo phạm vi state.

## 6. Thứ tự transformer và hợp đồng bytes

Khi JVM có nhiều transformer, kết quả được **xâu chuỗi**: transformer sau có thể nhìn bytes đã thay đổi bởi transformer trước.

Ở mức khái quát, ClassFileTransformer API phân nhóm theo khả năng retransform và theo native/Java transformer; trong mỗi nhóm áp dụng thứ tự đăng ký. Vì vậy:

- Đừng giả định ClassFile bytes luôn trùng với bản trên đĩa tại thời điểm callback.
- Transform cần **idempotent** nếu có thể được áp lại trong những kịch bản hỗ trợ; hoặc phải có detection marker rõ và tránh vá đè khiến ClassFile hỏng.
- Nếu transformer A thay constant pool và transformer B dựa vào offset/hình dạng trước đó, kết quả có thể thất bại. Dùng công cụ ClassFile-aware, thực hiện QA với nhiều agent/framework cùng lúc.
- Chỉ filter theo class name có thể gây xung đột khi nhiều loader định nghĩa cùng internal name. Filter theo `loader` và `module`/code source nếu cần.
- Mỗi transformer nên xử lý input **như immutable**, cấp byte array mới khi sửa.
- Nếu không thay đổi, **return `null`** là rõ ràng và tiết kiệm.

**Về exception:** ClassFileTransformer API có cách xử lý ngoại lệ từ `transform` theo hợp đồng (nhiều exception được JVM bỏ qua và coi như không transform, thay vì làm hỏng ngay ứng dụng). Vì vậy **không dùng `throw RuntimeException` từ transformer như một chính sách “chặn mọi class xấu” chắc chắn**. Nếu cần fail-closed vì lý do bảo mật, phải xây đường kiểm tra artifact/loader policy **có khả năng từ chối class definition một cách rõ ràng**, và kiểm thử behavior trên JVM đích.

Một instrumentation agent có thể chạy trên nhiều class rất sớm trong startup. Log không hạn chế từ `transform` có thể sinh ra lượng dữ liệu khổng lồ hoặc gây reentrancy khi logging framework tự nạp thêm class. Nên filter trước, hạn chế allocation/I/O trong callback và tránh gọi framework/plugin không kiểm soát khi JVM đang trong quá trình định nghĩa class.

## 7. Những vấn đề ClassFile thường làm bytecode instrument hỏng

Một patch trông đơn giản có thể làm ClassFile không hợp lệ. Ví dụ:

| Thay đổi | Rủi ro |
| --- | --- |
| Đổi `CONSTANT_Utf8` sang chuỗi dài hơn mà không cập nhật `u2 length` và offsets | Hỏng parser constant pool, `ClassFormatError` |
| Chèn instruction nhưng không cập nhật branch offsets và exception table | Nhảy sai bytecode, verification/linking error |
| Thêm code làm stack heights thay đổi nhưng không cập nhật stack map frames | `VerifyError` trên class version hiện đại |
| Đổi method descriptor nhưng không cập nhật call sites/constants | Lỗi resolution/`NoSuchMethodError` hoặc invalid bytecode |
| Đổi binary class name không phù hợp request `defineClass(name, ...)` | `NoClassDefFoundError`, thường kèm wrong name |
| Biến đổi class trong signed JAR hoặc sealed package mà không xét packaging policy | Rủi ro integrity, signer/package policy, code source |
| Cố dùng retransform để thay inheritance hoặc tùy ý thêm field | Giới hạn schema, `UnmodifiableClassException` hoặc lỗi khác tùy runtime |
| Biến đổi nhiều class tương tác nhưng dùng bản API do loader khác định nghĩa | `ClassCastException`/`LinkageError` do type identity khác |

Trong demo, ta tránh đa số nguy cơ nhờ chỉ thay **một entry UTF8 ASCII cùng độ dài**; JVM vẫn kiểm tra class sau transform. Ví dụ không làm JVM verifier “bỏ qua” điều kiện nào.

Để biến đổi bytecode thông thường, nên dùng framework hiểu cấu trúc ClassFile:

- **ASM:** đọc ClassFile, thay method instructions/visitors, hỗ trợ tính toán lại stack map frames/max stack khi cấu hình đúng.
- **Byte Buddy:** xây dựng instrumentation ở mức mô hình Java/agent, giảm lượng xử lý bytecode thủ công.
- **Javassist hoặc tool tương đương:** lựa chọn khác tùy yêu cầu và tương thích JDK.

Dù dùng thư viện, vẫn phải kiểm thử class loading trên phiên bản JVM mục tiêu, xử lý module access/exports/opens, loader dependencies và nguồn bytecode; thư viện bytecode không tự cung cấp security boundary.

## 8. Module (JPMS), ProtectionDomain và loader identity

Kể từ Java 9, `ClassFileTransformer` có overload nhận `Module`. Một class mới có thể được định nghĩa trong:

- **Named module** thuộc boot/dynamic `ModuleLayer`;
- **Unnamed module** của class loader tương ứng;
- Package/classloader đặc biệt theo cơ chế JVM.

Các ràng buộc JPMS vẫn tồn tại. Instrumentation có các cơ chế hỗ trợ module access phù hợp API, và `Instrumentation.redefineModule` cho phép agent điều chỉnh **một số quan hệ module** khi được JVM cho phép; nó không phải “tắt JPMS toàn process”.

### ClassLoader và ProtectionDomain có thay đổi không?

Load-time transformer **không tự đổi defining loader**. Kể cả khi bytes được sửa, `Class<?>.getClassLoader()` vẫn phản ánh loader định nghĩa class theo request. `ProtectionDomain`/`CodeSource` cần được xem riêng nếu agent dựa vào nguồn code hoặc chính sách security.

Trong demo:

~~~text
Agent class             → system/application loader
demo.Main               → system/application loader
demo.Greeter            → system/application loader
java.lang.instrument.*  → runtime loader phù hợp module Java
~~~

Agent có `premain` chạy trên system loader là behavior theo package specification cho startup agents; nhưng không nên dựa vào một chuỗi toString cụ thể của loader để viết assertion. Trong hệ plugin, transformer có thể tác động class được **custom loader** định nghĩa và Class identity vẫn đi cùng custom defining loader đó.

**Không nhầm `-javaagent` với `ClassLoader` tự xây:** agent đặt một hook biến đổi ở mức JVM instrument; custom loader quyết định nguồn bytes/namespace/delegation. Có thể phối hợp nhưng không thay thế nhau.

## 9. Instrumentation được dùng vào việc gì?

### 9.1. Tracing, metrics, coverage

Agent có thể thêm bytecode tại method entry/exit để đo thời gian, trace hoặc phủ code. Cần:

- Tránh tạo vòng recursion do tracer lại gọi method được instrument.
- Không bỏ qua `finally`, exceptions, synchronized methods hoặc asynchronous execution.
- Có policy exclude cho JDK/agent/helper classes cần thiết.
- Chú ý performance overhead, class loading time, allocations và startup cost.
- Có fallback/rollout/canary khi agent gặp class version hoặc bytecode shape chưa hỗ trợ.

### 9.2. Testing và fault injection

Agent có thể ghi instrumented probes, thay target branch cho test hoặc mô phỏng fault theo scenario. Nhưng nên **tách kịch bản bằng loader/JVM mới** khi cần reset static state, class initialization hoặc transformers đã có từ trước; việc remove transformer không làm các class đã biến đổi tự quay về bytecode gốc.

### 9.3. Plugin framework và dynamic classes

Một plugin loader có thể nạp một implementation do JAR ngoài cung cấp. Agent có thể log/tạo span cho class được custom loader định nghĩa, nhưng phải phân biệt:

- Plugin **được phép** đến từ nguồn nào (JAR checksum/signature/policy);
- Class **do loader nào định nghĩa**;
- Transformer **có hay không áp vào class ấy**;
- Những Class khác cùng tên trong parent/child có được biến đổi tương đương không.

Class loader và instrumentation **không tự sandbox** code không tin cậy. Bytecode transformer có quyền và tầm ảnh hưởng lớn đối với JVM: một agent lỗi có thể phá class loading trên diện rộng. Hãy xác minh nguồn agent JAR, config và phiên bản của nó như một thành phần có đặc quyền đáng kể.

## 10. Chẩn đoán khi agent không transform

### Trường hợp 1 — chạy không có output "Agent ready"

Kiểm tra:

- Thực sự truyền `-javaagent:transform-agent.jar` vào **lệnh `java` dùng chạy app**?
- Manifest trong agent JAR có `Premain-Class: Agent`?
- `Agent.class` và nested `Agent$PatchTransformer.class` có nằm trong JAR?
- `premain(String, Instrumentation)` có đúng `public static` signature?
- Agent có bị lỗi từ startup không? Đọc **stderr** và JVM exit code.

Có thể xem nội dung agent JAR:

~~~bash
jar --list --file transform-agent.jar
~~~

Tên nested class sẽ được tạo bởi `javac` và có trong `agent-classes` được đưa vào JAR theo lệnh `-C agent-classes .`.

### Trường hợp 2 — có "Agent ready", không có "Transformed"

Kiểm tra:

1. `demo.Greeter` có bị **load trước khi transformer đăng ký**? Với demo chuẩn thì không.
2. `className` có là `demo/Greeter` hay bạn đang so nhầm `demo.Greeter`?
3. Có một class cùng tên được **parent loader** cung cấp và class bạn định instrument không phải bản đang được dùng?
4. `PatchTransformer` có tìm thấy chính xác một `CONSTANT_Utf8_info` mang tám byte `ORIGINAL` không?
5. Compiler có thay đổi literal hoặc artifact trên classpath không giống file source mà bạn tưởng?
6. Có agent khác đã biến đổi constant pool trước đó không?
7. Agent có register với `false` và bạn đang mong nó chạy lại trên class đã load khi `retransformClasses` được gọi không?

### Trường hợp 3 — class load thất bại sau transform

Đọc exception thật:

- `ClassFormatError`: cấu trúc ClassFile có thể không hợp lệ, sai constant pool length/tag/offset.
- `VerifyError`: bytecode không thỏa type/stack/local/stack-map constraints.
- `NoClassDefFoundError`: class dependencies thiếu, tên khai báo sai hoặc class initialization từng lỗi.
- `UnsupportedClassVersionError`: phiên bản ClassFile không được JVM hỗ trợ.
- `LinkageError`: định nghĩa trùng hoặc loader constraints; không tự xem đây là lỗi transformer.
- `IllegalAccessError`/module-related access errors: JPMS/member visibility hoặc những dependency thêm bởi transformer không được phép.

Để phân biệt lỗi từ bytes gốc với lỗi transformer: chạy **không có agent**, rồi so kết quả với **có agent**. Có thể lưu instrumented bytes trong một môi trường test có kiểm soát để dùng `javap -v -p`/verifier kiểm tra, nhưng không xuất bytes đến nơi có thể lộ code/secrets và không ghi file tùy tiện trong callback startup.

### Trường hợp 4 — println output đúng nhưng không chắc loader nào định nghĩa

Trong app, fragment:

~~~java
System.out.println(demo.Greeter.class.getName());
System.out.println(demo.Greeter.class.getClassLoader());
System.out.println(demo.Greeter.class.getModule());
~~~

Đây là **fragment**; loader/module details phụ thuộc môi trường. Dòng thay đổi `Message: PATCHED!` chứng minh behavior được instrument trong demo, nhưng muốn chứng minh **loader-specific transformation** cần log/đối chiếu `loader` của callback và `Class.getClassLoader()`.

### Bắt đầu bằng cặp đối chứng

~~~text
No agent:   bytecode gốc       → Message: ORIGINAL
With agent: bytecode biến đổi → Message: PATCHED!
~~~

Đây là test đối chứng sạch vì mỗi `java` invocation tạo **JVM process mới**, tránh chuyện class đã nạp trong process trước đó. Cũng có thể dùng hai custom loaders mới cho cùng một JVM, nhưng phải xác nhận parent không trả Class đã load và transformer không phụ thuộc state toàn cục của agent.

## 11. Ranh giới, hiệu năng và bảo mật

**Agent là thành phần có đặc quyền và tầm ảnh hưởng lớn.** Nó có thể nhìn/biến đổi code của nhiều class nếu không filter; do đó:

1. **Tin cậy artifact agent:** kiểm tra provenance, pin checksum/signature và quản lý config giống những thành phần release khác.
2. **Filter tối thiểu:** chỉ instrument packages/classes thực sự cần, có allowlist loader/module khi ứng dụng có plugin.
3. **Tránh deadlock hoặc reentrancy:** callback class loading có thể chạy trong ngữ cảnh liên quan khóa của loader; không gọi ngược custom loader hoặc logger/framework không kiểm soát trong lúc đang transform.
4. **Giảm overhead:** parse ClassFile, reflection, allocation và I/O từ mọi callback rất tốn chi phí; cần đo startup/runtime.
5. **Không sửa mảng gốc:** trả null hoặc bản byte[] mới. Xử lý ClassFile hợp lệ và có test verifier.
6. **Chú ý thứ tự transformer:** nhiều agent cùng chỉnh một method/class có thể tương tác bất ngờ.
7. **Không dùng transformer exception để chặn code bất tín:** API không bảo đảm exception từ callback tương đương deny policy. Với nguồn plugin ngoài, gate artifact và parent/child loader policy phải được thực thi riêng.
8. **Kiểm tra target JDK/module:** class file version, named modules và internal packages có thể thay giữa bản JDK.
9. **Đừng xem biến đổi bytes là isolation:** code sau instrumentation vẫn chạy trong JVM với quyền process, tùy giới hạn OS/module/runtime.
10. **Vòng đời:** `removeTransformer` dừng callback cho những class tiếp theo phù hợp registration; nó không tự hoàn tác những Class đã được định nghĩa từ bytes đã biến đổi.

## 12. Tự kiểm tra kiến thức

**Câu 1.** `ClassFileTransformer` load-time được gọi trước hay sau khi JVM hoàn tất định nghĩa Class mới?

**Đáp án:** **Trước** khi class mới được định nghĩa, trong pipeline xử lý ClassFile bytes của JVM.

**Câu 2.** Nếu `transform` trả `null`, JVM dùng gì?

**Đáp án:** Tiếp tục với bytes hiện tại của transformer chain, tức transformer ấy **không cung cấp thay đổi**.

**Câu 3.** Vì sao ví dụ so `"demo/Greeter"` thay vì `"demo.Greeter"`?

**Đáp án:** Tham số `className` của `ClassFileTransformer` dùng **internal name** với slash; `demo.Greeter` là binary name thông thường của Java.

**Câu 4.** Trong ví dụ, source `Greeter.java` vẫn chứa `ORIGINAL` nhưng app in `PATCHED!`. Điều đó chứng tỏ gì?

**Đáp án:** Agent đã thay constant pool bytes trước khi class được định nghĩa; file source/ClassFile lưu trên disk không bị sửa bởi transformer trong demo.

**Câu 5.** Một class đã được system loader định nghĩa, sau đó mới đăng ký transformer. Tạo transformer có tự đổi class đã load không?

**Đáp án:** Không. Muốn thay class đã load cần xem `retransformClasses`/`redefineClasses` nếu runtime hỗ trợ và class modifiable.

**Câu 6.** Trong demo, vì sao truyền `false` vào `addTransformer`?

**Đáp án:** Đăng ký một transformer **không retransformation-capable**; bài chỉ minh họa load-time transformation của một class mới.

**Câu 7.** Có thể return một `byte[]` tùy ý, sai cấu trúc rồi JVM vẫn tạo Class không?

**Đáp án:** Không. JVM vẫn cần ClassFile hợp lệ và tuân thủ verifier/linker/module constraints, có thể ném `ClassFormatError`, `VerifyError` hoặc lỗi khác.

**Câu 8.** Java agent có thay thế security checks cho plugin JAR không?

**Đáp án:** Không. Instrumentation không tự xác minh nguồn/trust của code, không phải sandbox và có thể làm thay đổi hành vi JVM trên diện rộng.

**Câu 9.** Hai classloader định nghĩa cùng binary name sau transform với bytes giống nhau có trở thành một Class không?

**Đáp án:** Không. Defining loader khác nhau thì identity khác nhau.

**Câu 10.** Nếu muốn chèn nhiều instruction và đổi stack/control flow, có nên dùng parser constant pool tối giản này không?

**Đáp án:** Không. Dùng thư viện bytecode hiểu đầy đủ ClassFile như ASM/Byte Buddy, cập nhật stack map frames/offsets và kiểm thử bằng JVM verifier.

## Ghi nhớ

`-javaagent` cho phép một agent đăng ký `ClassFileTransformer` qua `Instrumentation`. Khi một class mới được định nghĩa, JVM có thể gọi transformer **trước bước định nghĩa**: trả `null` để giữ bytes hiện tại hoặc trả **byte[] ClassFile mới** để JVM tiếp tục kiểm tra/định nghĩa. Đây là **load-time instrumentation**, khác với `retransformClasses` và `redefineClasses` cho class đã load; nó cũng khác một custom loader tự chỉnh bytes trước `defineClass`. Instrumentation không thay defining loader, không reset static state và không bỏ qua verifier/module rules.

**Tài liệu chuẩn Java SE 17:**

- `java.lang.instrument` package, agent deployment/manifest/premain: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- `Instrumentation`, `addTransformer`, `retransformClasses`, `redefineClasses`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- `ClassFileTransformer`, signatures và thứ tự chaining: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- `ClassLoader`, `defineClass`/parent delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- JVMS Java 17, ClassFile format/constant pool (§4): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- JVMS Java 17, loading/linking/initializing (§5): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
