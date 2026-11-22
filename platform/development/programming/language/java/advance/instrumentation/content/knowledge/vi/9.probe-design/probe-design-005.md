# Xử lý ngoại lệ phát sinh từ lời gọi hoặc lệnh khác mà không có athrow trực tiếp

Khi thiết kế một điểm đo ở **cuối phương thức** bằng Java bytecode instrumentation, chỉ nhìn lệnh **ATHROW** xuất hiện trong method là **chưa đủ** để ghi nhận mọi lần phương thức kết thúc vì ngoại lệ. Ví dụ, một method có thể chỉ gọi **INVOKEVIRTUAL**, **INVOKESTATIC** hoặc thực hiện **IDIV**, **GETFIELD**, **AALOAD** rồi kết thúc bất thường vì lời gọi bên dưới ném exception, chia cho 0, dereference **null** hoặc vượt biên mảng. **Trong bytecode của method đang được đo không nhất thiết có lệnh ATHROW trực tiếp ở đường thực thi đó.**

Nếu agent chỉ chèn logic vào các vị trí **RETURN** và **ATHROW** bằng **ASM AdviceAdapter.onMethodExit(opcode)**, điểm đo sẽ dễ bỏ sót những **exceptional exits do instruction khác gây ra**. Cách tổng quát hơn để ghi nhận *ngoại lệ thoát ra khỏi phạm vi method* là bọc **toàn bộ phần body cần quan sát** bằng một **exception handler bắt Throwable**, ghi nhận exception ở handler rồi **ném lại đúng đối tượng ban đầu**. Các đường return bình thường được xử lý riêng; lệnh **ATHROW** trực tiếp trong body không được ghi log lần thứ hai nếu đã có catch-all.

Bài này phân biệt bytecode có **ATHROW tường minh**, ngoại lệ **truyền lên từ lời gọi**, ngoại lệ **do VM phát sinh khi thực hiện instruction**, cơ chế **exception table**, và cách dùng Java 17 + ASM để instrument đúng một method. Trọng tâm là **giữ semantics gốc của ứng dụng**, không nuốt hay biến ngoại lệ thành kết quả bình thường.

## 1. Kết quả cần nắm

Sau bài học, bạn có thể:

1. Giải thích tại sao một method có thể thoát bằng exception mà **không thực thi ATHROW trực tiếp trong method đó**.
2. Phân biệt lệnh **ATHROW**, **exception handler**, **exception table** và **unwinding** của JVM.
3. Biết giới hạn của hook theo opcode **AdviceAdapter.onMethodExit(ATHROW)**.
4. Thiết kế một **catch-all handler** bao phủ method body, nhưng **không ghi đúp** hoặc ghi nhầm exception đã được body xử lý nội bộ.
5. Giữ đúng kiểu trả về, operand stack, local variables, **StackMapTable**, thứ tự handler và object **Throwable** ban đầu.
6. Hiểu những tình huống không có điểm đo method entry/exit thông thường: lỗi trước khi vào method, async failure, constructor, native method và callback trên thread khác.
7. Chạy ví dụ Java 17 minh họa **return**, **lời gọi ném exception**, **null dereference**, **chia 0** và **ATHROW trực tiếp**, rồi kiểm chứng agent không đổi kiểu ngoại lệ mà caller quan sát.

## 2. Tại sao không có ATHROW vẫn có ngoại lệ?

### 2.1. Ngoại lệ từ lời gọi method

Xét mã Java:

~~~java
// Đoạn minh họa; không phải file độc lập.
static int service() {
    return repository();
}

static int repository() {
    throw new IllegalStateException("database unavailable");
}
~~~

Bytecode của **service()** có thể là:

~~~text
invokestatic  #... // Method repository:()I
ireturn
~~~

**ATHROW nằm trong repository()**, còn **service()** chỉ thực thi **INVOKESTATIC**. Khi repository ném **IllegalStateException**, lời gọi trong service **không trả về giá trị** để đi đến **IRETURN**. JVM tìm exception handler phù hợp trong service; nếu không có, tiếp tục unwind sang caller của service. Một instrumentation chỉ kiểm tra các opcode **IRETURN/RETURN/ARETURN/.../ATHROW** của service **không có cơ hội chạy onMethodExit** trên đường exception này nếu không cài handler riêng.

Điều tương tự xảy ra với **INVOKEVIRTUAL**, **INVOKEINTERFACE**, **INVOKESPECIAL**, **INVOKESTATIC**, **INVOKEDYNAMIC**: chính lời gọi hoặc phương thức đích có thể dẫn đến exception. Một số lỗi liên kết/khởi tạo lớp cũng có thể xuất hiện khi thực thi instruction liên quan.

### 2.2. Ngoại lệ do instruction phát sinh

| Instruction hoặc nhóm | Tình huống | Throwable thường gặp |
| --- | --- | --- |
| **IDIV/IREM/LDIV/LREM** | Chia hoặc lấy dư với divisor bằng 0 | **ArithmeticException** |
| **GETFIELD/PUTFIELD** | Truy cập field instance qua reference null | **NullPointerException** |
| **INVOKEVIRTUAL/INVOKEINTERFACE/INVOKESPECIAL** | Receiver null hoặc callee ném lỗi | **NullPointerException** hoặc Throwable từ callee |
| **ARRAYLENGTH**, **AALOAD/IALOAD/...** | Mảng null, index vượt phạm vi | **NullPointerException**, **ArrayIndexOutOfBoundsException** |
| **AASTORE** | Thử lưu object không tương thích kiểu thành phần của mảng | **ArrayStoreException** |
| **CHECKCAST** | Object không thuộc kiểu cần cast | **ClassCastException** |
| **NEWARRAY/ANEWARRAY/MULTIANEWARRAY** | Kích thước âm, thiếu bộ nhớ | **NegativeArraySizeException**, có thể **OutOfMemoryError** |
| **NEW**, **GETSTATIC**, **INVOKESTATIC** và những lệnh liên quan | Resolution, class initialization hoặc thực thi gây lỗi | **LinkageError**, **ExceptionInInitializerError**, v.v. |

Không phải mọi instruction trên đều luôn ném lỗi; bảng nêu **đường phát sinh có thể xảy ra**. Điều quan trọng là **exceptional method exit không đòi hỏi method có một lệnh ATHROW ở vị trí đó**.

### 2.3. Ba tình huống cần phân biệt

~~~text
(A) Phương thức tự ném:
    NEW IllegalArgumentException
    ...
    ATHROW                       ← ATHROW trực tiếp trong method

(B) Method gọi callee:
    INVOKESTATIC callOther()
       └── callee throws
    IRETURN không được chạy       ← caller không cần ATHROW riêng

(C) Method thực hiện instruction có thể throw:
    ILOAD dividend
    ILOAD divisor
    IDIV  (divisor == 0)          ← ArithmeticException tại IDIV
    IRETURN không được chạy
~~~

Cả ba đều là **lần kết thúc method bằng exception** nếu exception không được xử lý trước khi rời method. Nhưng một hook được kích hoạt **khi visitor nhìn thấy opcode ATHROW** chỉ có tín hiệu chắc chắn trong trường hợp A; không thể suy đoán B/C từ việc thiếu lệnh RETURN trong callback tĩnh.

## 3. JVM tìm exception handler như thế nào?

Một **Code attribute** trong class file có **exception table**. Mỗi entry chứa:

- **start_pc**: offset đầu phạm vi được bảo vệ (inclusive).
- **end_pc**: offset cuối (exclusive).
- **handler_pc**: nơi JVM chuyển điều khiển đến khi bắt được ngoại lệ.
- **catch_type**: class exception được bắt; nếu bằng 0 là handler cho mọi Throwable phù hợp (thường dùng để biên dịch finally). Với agent, có thể dùng catch_type là **java/lang/Throwable**.

Khi một instruction ném exception, JVM tìm **handler đầu tiên trong bảng** có phạm vi chứa offset instruction và kiểu exception tương thích. Nếu tìm thấy, JVM chuyển sang handler với **exception object trên operand stack**; nếu không, frame hiện tại bị unwind và exception được truyền lên phương thức gọi. Handler có thể:

- Xử lý exception rồi tiếp tục bình thường.
- Chuyển thành exception khác theo nghiệp vụ.
- **Ném lại cùng Throwable** để giữ kết quả exception nguyên bản.
- Chạy **finally/cleanup** rồi rethrow.

Cụ thể, method:

~~~java
// Đoạn minh họa: method có catch nội bộ.
static int parse(String input) {
    try {
        return Integer.parseInt(input);
    } catch (NumberFormatException ex) {
        return -1;
    }
}
~~~

**NumberFormatException** được xử lý hoàn toàn bên trong method, nên **parse() trả về bình thường**. Một agent đo **exceptional exits của parse()** không nên báo lỗi chỉ vì **Integer.parseInt()** từng ném exception. Synthetic catch-all handler cần được thêm **sau các handler hiện có** để những nhánh catch nội bộ tiếp tục hoạt động; chỉ các exception **thực sự thoát khỏi method** mới chạm handler của agent.

Điều này phân biệt hai KPI:

- **Thrown events**: số lần exception xuất hiện ở instruction/callee (kể cả đã được bắt nội bộ).
- **Exceptional method exits**: số lần method đang đo **thoát ra caller bằng exception**.

Bài này giải quyết chủ yếu **exceptional method exits**. Nếu muốn đo mọi thrown event, phải instrument phạm vi khác, ví dụ các throw sites, catch sites hoặc cơ chế sự kiện JVM phù hợp; đó là bài toán khác, không thể suy ra hoàn toàn bằng một catch-all cuối method.

## 4. Giới hạn của AdviceAdapter.onMethodExit

ASM commons có lớp **AdviceAdapter** hỗ trợ chèn code vào method entry và trước các opcode return/ATHROW. Ví dụ minh họa:

~~~java
// Đoạn minh họa nằm trong một AdviceAdapter; chưa phải Java độc lập.
@Override
protected void onMethodExit(int opcode) {
    if (opcode == ATHROW) {
        // Chỉ biết rằng visitor đã gặp lệnh ATHROW trực tiếp.
        logErrorExit();
    } else {
        logNormalExit();
    }
}
~~~

Nhược điểm:

1. Visitor **thấy instruction ATHROW trong bytecode đang được duyệt**, không phải một callback JVM khi runtime ném Throwable.
2. Exception từ **INVOKESTATIC**, **INVOKEVIRTUAL**, **IDIV** hay **GETFIELD** không tự tạo một lời gọi **onMethodExit(ATHROW)** tại method đang đo.
3. Một opcode ATHROW có thể xuất hiện **bên trong try/catch của chính method**; exception đó có thể được bắt và method tiếp tục trả về bình thường. Nếu ghi error exit tại **mọi ATHROW**, KPI exit sẽ **đếm sai**.
4. Nếu vừa ghi lỗi ở **onMethodExit(ATHROW)** vừa cài catch-all handler cũng ghi lỗi, một exception thực sự thoát method có thể bị ghi **hai lần**.

Vì vậy, khi mục tiêu là **đếm/trace mọi lần method thoát bằng exception**, cách đáng tin là:

- Chèn **normal-exit hook** ở các opcode return.
- **Không** ghi exceptional-exit ở riêng opcode ATHROW.
- Cài một **catch-all exception handler** bao phủ code gốc cần đo.
- Trong handler, ghi nhận exception, sau đó **load lại và ATHROW cùng object**.
- Đảm bảo handler không bắt lại chính nó, không nằm trước handler nghiệp vụ và không thay đổi ngoại lệ gốc.

### 4.1. So sánh hai cách

| Tiêu chí | Chỉ onMethodExit(ATHROW) | Catch-all bao phủ body |
| --- | --- | --- |
| ATHROW tường minh và exception thoát method | Có thể quan sát | Quan sát |
| Callee ném, caller không có ATHROW | **Bỏ sót** | Quan sát |
| IDIV/GETFIELD ném exception | **Bỏ sót** | Quan sát |
| ATHROW nội bộ rồi được catch trong method | Có thể **báo nhầm exit** | Không báo exceptional exit nếu handler nội bộ xử lý |
| Hoạt động đúng khi method return bình thường | Cần xử lý các return opcode | Cần normal-exit hook riêng |
| Rủi ro tự gây lỗi | Thấp hơn về CFG | Phải dựng exception table và frame hợp lệ |
| Constructor/native/synchronized | Cần xử lý riêng | Cũng cần xử lý riêng |

## 5. Mẫu cấu trúc bytecode cho exceptional exit

Phần lớn thiết kế instrument **method thông thường** sẽ có hình dạng sau:

~~~text
Method m(args):
    call TraceHooks.enter()             ← điểm bắt đầu đo

    L_start:
        ... original method body ...
        ... calls, field accesses, arithmetic ...
        ... method's own try/catch ...
        ...
        RETURN / IRETURN / ARETURN:
            call TraceHooks.normal()    ← ngay trước normal return
            RETURN / IRETURN / ARETURN

    L_end:
    L_handler:                           ← không nằm trong phạm vi try
        ASTORE localThrowable           ← giữ Throwable trên operand stack
        ALOAD localThrowable
        call TraceHooks.exception(Throwable)
        ALOAD localThrowable
        ATHROW                           ← ném lại cùng object

Exception table:
    [L_start, L_end) -> L_handler catch java/lang/Throwable
~~~

Đây là **sơ đồ bytecode**, không phải file Java nguồn. Handler phải nằm **ngoài chính phạm vi bảo vệ** để nếu logic handler ném exception, không tạo vòng lặp bắt chính nó. Bảng exception của ứng dụng phải có cơ hội xử lý trước; khi dùng ASM, synthetic catch-all thường được **thêm sau những handler đã có**.

### 5.1. Vì sao catch Throwable thay vì Exception?

**Throwable** bao gồm **Exception** và **Error**. Một instruction có thể dẫn đến **OutOfMemoryError**, **LinkageError**, **ExceptionInInitializerError** hoặc lỗi không phải subclass của **Exception**. Nếu muốn quan sát **mọi exceptional exit**, cần handler bao phủ **Throwable**.

Tuy nhiên, “bắt Throwable để **ghi nhận rồi ném lại**” khác với “bắt Throwable rồi **nuốt**”. Không nên nuốt **ThreadDeath**, **VirtualMachineError** hoặc thay đổi cách JVM báo lỗi nghiêm trọng. Điểm đo phải ưu tiên giữ hành vi nguyên bản; logger trong handler cần tối thiểu, không blocking và hạn chế cấp phát.

### 5.2. Giữ đúng exception object và stack

Tại entry của handler, JVM đặt object Throwable trên stack. Một mẫu an toàn:

~~~text
ASTORE exceptionSlot
ALOAD  exceptionSlot
INVOKESTATIC TraceHooks.exception(Throwable)
ALOAD  exceptionSlot
ATHROW
~~~

Ở đây **exceptionSlot** là một local variable slot mới do instrumenter cấp phát, không được vô tình đè lên local của ứng dụng. **ATHROW cuối handler là lệnh do agent chèn**, dùng để truyền tiếp exception ban đầu. Đó không phải yêu cầu rằng mọi exception từ body phải đi qua một ATHROW trực tiếp của body.

Không làm:

~~~text
POP
RETURN
~~~

vì như vậy biến lỗi thành return bình thường, phá hợp đồng method. Cũng không nên luôn tạo **new RuntimeException(original)** nếu mục tiêu là bảo toàn Throwable; cách đó đổi kiểu, identity, stack trace và có thể phá luồng xử lý ở caller.

### 5.3. Hook không được phá semantics khi bản thân nó thất bại

Nếu **TraceHooks.normal()** ném exception, một method vốn trả kết quả hợp lệ có thể trở thành method ném lỗi. Nếu **TraceHooks.exception(t)** ném exception mới, caller có thể không còn nhìn thấy Throwable gốc. Vì thế production instrumentation nên dùng **hook không ném exception ra ngoài**, ghi log có kiểm soát, tránh gọi framework phức tạp ngay trên đường class load/hot path, và có chính sách xử lý lỗi của logger.

Với ví dụ chạy bên dưới, hook chỉ in một dòng để dễ học; đó **không phải bộ telemetry production**. Khi áp dụng thực tế, cần lựa chọn đường ghi không blocking và xét cả lỗi của hệ thống quan sát.

## 6. Bước một: chương trình Java 17 chưa có instrumentation

Ta xây một chương trình nhỏ gồm một method **run(String)** mà các đường lỗi chính **không có lệnh ATHROW trực tiếp ở caller**. Một method **directThrow()** riêng làm đối chứng.

**File src/main/java/demo/App.java**

~~~java
package demo;

public final class App {
    public static final class Worker {
        private Worker() { }

        public static int run(String mode) {
            return switch (mode) {
                case "ok" -> 7;
                case "call" -> downstream();
                case "null" -> ((String) null).length();
                case "divide" -> 10 / zero();
                default -> -1;
            };
        }

        public static int directThrow() {
            throw new IllegalArgumentException("direct");
        }

        private static int downstream() {
            throw new IllegalStateException("from callee");
        }

        private static int zero() {
            return 0;
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[] {
                "ok", "call", "null", "divide", "explicit"
        }) {
            try {
                int answer = mode.equals("explicit")
                        ? Worker.directThrow()
                        : Worker.run(mode);
                System.out.println("RESULT " + mode + "=" + answer);
            } catch (Throwable error) {
                System.out.println("CAUGHT " + mode + " "
                        + error.getClass().getSimpleName());
            }
        }
    }
}
~~~

Giải thích từng trường hợp:

- **ok**: method trả **7**, đi qua normal return.
- **call**: **run** gọi **downstream()**; method downstream dùng ATHROW nhưng **run** chỉ gọi method và truyền exception lên.
- **null**: trong **run**, instruction gọi **String.length()** trên reference null ném **NullPointerException**.
- **divide**: phép chia **10 / zero()** thực thi IDIV với divisor 0, ném **ArithmeticException**.
- **explicit**: **directThrow()** tự ném **IllegalArgumentException**; phương thức này có ATHROW tường minh và là đối chứng.

Chỉ riêng **run(String)** không cần một ATHROW trực tiếp để có ba loại exception exit. Với switch expression Java 17, **javac** có thể dùng lookupswitch hoặc chuỗi so sánh để dispatch, nhưng điều đó không thay đổi semantics ngoại lệ.

Nếu chỉ muốn chạy bản Java không agent, sau khi đã lưu App.java, có thể biên dịch độc lập:

~~~bash
javac --release 17 -d out src/main/java/demo/App.java
java -cp out demo.App
~~~

Output ổn định của bản không instrument:

~~~text
RESULT ok=7
CAUGHT call IllegalStateException
CAUGHT null NullPointerException
CAUGHT divide ArithmeticException
CAUGHT explicit IllegalArgumentException
~~~

### 6.1. Đọc disassembly bằng javap

~~~bash
javap -c -p -classpath out 'demo.App$Worker'
~~~

Lệnh trên dùng dấu nháy đơn cho shell POSIX để giữ ký tự **$**. Với Windows PowerShell, cũng dùng single quotes; nếu chạy Windows cmd.exe, cần quoting tương ứng.

Hãy quan sát method **run(java.lang.String)**: những nhánh lỗi sẽ có instruction như:

~~~text
invokestatic ... downstream:()I
...
invokevirtual ... java/lang/String.length:()I
...
idiv
...
ireturn
~~~

Đây là **các dòng minh họa rút gọn**, không phải transcript đầy đủ vì vị trí/index trong constant pool do compiler quyết định. Không có nhu cầu viết ATHROW trực tiếp trong **run** để các lỗi kia thoát ra. **directThrow()**, trái lại, có thể quan sát opcode **athrow** trong disassembly.

## 7. Bước hai: instrument method bằng ASM AdviceAdapter và catch-all

Ví dụ agent sử dụng **ASM 9.7.1** trên Java 17. ASM được đóng gói vào JAR bằng **Maven Shade**, nên khi dùng **-javaagent** không cần truyền hai JAR ASM ở classpath bên ngoài. Có hai source Java (App.java và ExitAgent.java), cùng một pom.xml. Ví dụ cố ý chỉ biến đổi **demo/App$Worker**, đúng các method **run(String)** và **directThrow()**; không đụng constructor, native method hay lớp khác.

### 7.1. pom.xml

Tạo file **pom.xml** ở thư mục dự án:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>exception-exit-agent</artifactId>
  <version>1.0.0</version>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.7.1</version>
    </dependency>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm-commons</artifactId>
      <version>9.7.1</version>
    </dependency>
  </dependencies>

  <build>
    <finalName>exception-exit-agent</finalName>
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
                    <Premain-Class>demo.ExitAgent</Premain-Class>
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

**ASM** không thuộc Java SE/JDK; Maven cần tải dependency từ Maven Central ở lần chạy đầu nếu chưa được cache. Dependency được đóng gói vào **exception-exit-agent.jar** bằng Shade plugin; thực tế nên rà soát relocation/conflict nếu nhiều agent đồng thời mang ASM khác phiên bản.

### 7.2. ExitAgent.java

**File src/main/java/demo/ExitAgent.java**

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.commons.AdviceAdapter;
import org.objectweb.asm.commons.Method;

public final class ExitAgent {
    private ExitAgent() { }

    public static void premain(String options, Instrumentation inst) {
        inst.addTransformer(new ExitTransformer(), false);
    }
}

final class ExitTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!"demo/App$Worker".equals(className)) {
            return null;
        }

        ClassReader reader = new ClassReader(classfileBuffer);
        ClassWriter writer = new ClassWriter(
                reader, ClassWriter.COMPUTE_FRAMES
                        | ClassWriter.COMPUTE_MAXS);

        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(
                    int access,
                    String name,
                    String descriptor,
                    String signature,
                    String[] exceptions) {

                MethodVisitor original = super.visitMethod(
                        access, name, descriptor, signature, exceptions);

                boolean selected =
                        ("run".equals(name)
                                && "(Ljava/lang/String;)I"
                                        .equals(descriptor))
                        || ("directThrow".equals(name)
                                && "()I".equals(descriptor));

                if (!selected) {
                    return original;
                }

                return new AdviceAdapter(
                        Opcodes.ASM9, original,
                        access, name, descriptor) {

                    private final Label bodyStart = new Label();
                    private final Label bodyEnd = new Label();
                    private final Label errorHandler = new Label();

                    @Override
                    protected void onMethodEnter() {
                        invokeStatic(
                                Type.getType(ExitHooks.class),
                                new Method("enter", "()V"));
                        mark(bodyStart);
                    }

                    @Override
                    protected void onMethodExit(int opcode) {
                        // ATHROW trực tiếp sẽ được handler xử lý nếu
                        // exception thực sự thoát khỏi method.
                        if (opcode != ATHROW) {
                            invokeStatic(
                                    Type.getType(ExitHooks.class),
                                    new Method("normal", "()V"));
                        }
                    }

                    @Override
                    public void visitMaxs(int maxStack, int maxLocals) {
                        // Thêm handler sau những handler có sẵn:
                        // catch nội bộ của method giữ quyền xử lý trước.
                        mark(bodyEnd);
                        visitTryCatchBlock(
                                bodyStart, bodyEnd, errorHandler,
                                "java/lang/Throwable");
                        mark(errorHandler);

                        int exceptionLocal =
                                newLocal(Type.getType(Throwable.class));
                        storeLocal(exceptionLocal);

                        loadLocal(exceptionLocal);
                        invokeStatic(
                                Type.getType(ExitHooks.class),
                                new Method(
                                        "exception",
                                        "(Ljava/lang/Throwable;)V"));

                        loadLocal(exceptionLocal);
                        throwException(); // ném lại đúng Throwable

                        super.visitMaxs(maxStack, maxLocals);
                    }
                };
            }
        };

        reader.accept(visitor, ClassReader.EXPAND_FRAMES);
        return writer.toByteArray();
    }
}

// Helper cùng runtime package/class loader với App$Worker trong demo.
final class ExitHooks {
    private ExitHooks() { }

    public static void enter() {
        System.out.println("TRACE_ENTER");
    }

    public static void normal() {
        System.out.println("TRACE_NORMAL");
    }

    public static void exception(Throwable error) {
        System.out.println("TRACE_EXCEPTION "
                + error.getClass().getSimpleName());
    }
}
~~~

**Điểm quan trọng trong code:**

1. **ExitTransformer** lọc đúng internal class name **demo/App$Worker**. Các class khác trả **null**, nên ASM không phải xử lý mọi class do JVM tải.
2. **visitMethod** lọc cả tên method và descriptor. Điều này tránh instrument nhầm overload.
3. **onMethodEnter** chèn **ExitHooks.enter()** rồi đánh dấu **bodyStart**. Vì hai method đích đều **static, không phải constructor**, không gặp vấn đề **uninitialized this**.
4. **onMethodExit** chỉ chèn **ExitHooks.normal()** cho các opcode return bình thường. **ATHROW** bị bỏ qua để không báo lỗi hai lần và không ghi nhầm một ATHROW được catch nội bộ.
5. **visitMaxs** thêm **catch-all handler** bao phủ đoạn từ **bodyStart** tới **bodyEnd**. Nó được thêm khi các handler ban đầu đã được reader chuyển qua visitor, để handler nghiệp vụ đã có được xét trước.
6. Tại handler, JVM cung cấp **Throwable** trên stack; **storeLocal** giữ object vào local mới, **ExitHooks.exception** ghi nhận, rồi **throwException()** ném lại chính object ấy.
7. **bodyEnd** nằm trước handler, nên **handler không tự bắt chính nó**.
8. **ClassWriter.COMPUTE_MAXS | COMPUTE_FRAMES** giúp tính lại stack/local limits và frames cho class demo; **ClassReader.EXPAND_FRAMES** đọc các frame dạng expanded tương thích quá trình viết.
9. Class được định nghĩa sau khi transformer trả bytes mới; ứng dụng gọi method thật mới là bằng chứng JVM đã chấp nhận và sử dụng instrumentation.

**Giới hạn demo:** Ví dụ không cài transformer **canRetransform=true**, không instrument constructor/native/abstract method, không định nghĩa logic rollback và giả định tất cả lớp demo cùng system/application class loader trong unnamed module. Trong production, **COMPUTE_FRAMES** có thể cần một **ClassWriter.getCommonSuperClass** phù hợp với class loader của lớp đích; giải quyết type hierarchy bằng loader sai có thể dẫn đến lỗi verifier hoặc class loading lồng nhau. Agent không nên dùng biến đổi mẫu trên cho mọi class nếu chưa kiểm tra access/module/classloader và handler order của class thật.

### 7.3. Build và chạy

Sau khi tạo đúng cấu trúc thư mục:

~~~text
exception-exit-agent/
  pom.xml
  src/
    main/
      java/
        demo/
          App.java
          ExitAgent.java
~~~

Ở thư mục chứa pom.xml:

~~~bash
mvn -q -DskipTests package
java -cp target/exception-exit-agent.jar demo.App
java -javaagent:target/exception-exit-agent.jar \
     -cp target/exception-exit-agent.jar demo.App
~~~

Dấu **\\** ở cuối dòng trên là cú pháp nối dòng trong shell POSIX; trong Windows PowerShell có thể nhập toàn bộ lệnh trên **một dòng**:

~~~text
java -javaagent:target/exception-exit-agent.jar -cp target/exception-exit-agent.jar demo.App
~~~

Lần chạy **không agent**:

~~~text
RESULT ok=7
CAUGHT call IllegalStateException
CAUGHT null NullPointerException
CAUGHT divide ArithmeticException
CAUGHT explicit IllegalArgumentException
~~~

Lần chạy **có agent** (trên môi trường Java 17 tiêu chuẩn với ví dụ này):

~~~text
TRACE_ENTER
TRACE_NORMAL
RESULT ok=7
TRACE_ENTER
TRACE_EXCEPTION IllegalStateException
CAUGHT call IllegalStateException
TRACE_ENTER
TRACE_EXCEPTION NullPointerException
CAUGHT null NullPointerException
TRACE_ENTER
TRACE_EXCEPTION ArithmeticException
CAUGHT divide ArithmeticException
TRACE_ENTER
TRACE_EXCEPTION IllegalArgumentException
CAUGHT explicit IllegalArgumentException
~~~

**Điều phải nhận ra:** **call**, **null**, **divide** đều sinh **TRACE_EXCEPTION** dù method **run(String)** không có lệnh ATHROW trực tiếp tương ứng. **explicit** cũng chỉ tạo một **TRACE_EXCEPTION**. Các dòng **CAUGHT** có cùng exception type ở cả hai lượt chạy; agent ghi nhận chứ không nuốt hoặc thay lỗi.

Trong một dự án dùng JDK khác hoặc nhiều agent khác, hãy kiểm tra thứ tự class load, class loader và manifest; ví dụ cố định rõ các thành phần để kết quả dễ tái lập.

### 7.4. Vì sao handler không bắt exception đã được method xử lý?

Trong ASM, những bảng exception của method gốc được chuyển vào visitor trong quá trình đọc class. Handler **catch Throwable** của ví dụ được thêm sau cùng. JVM duyệt exception table theo thứ tự, nên nếu original method có **try/catch** tương ứng và exception xảy ra trong vùng đó, original handler được chọn trước.

Nếu original catch xử lý lỗi rồi method trở về bình thường, **normal-exit hook** sẽ ghi **TRACE_NORMAL**; **exceptional-exit hook** không chạy. Nếu original catch ném lại exception hoặc ném exception khác ra ngoài, catch-all của agent có thể quan sát lần rời method thực tế.

**Tuy nhiên**, không nên giả định mọi cấu hình visitor đều giữ thứ tự handler như ví dụ. Một công cụ khác có thể thêm catch-all trước các handler ứng dụng, hoặc class writer có thể bị sử dụng sai. Hãy kiểm tra exception table cuối bằng **javap -v** và test method có catch nội bộ.

## 8. Một cách hiểu khác bằng Java try/finally thông thường

Vì handler ASM trông hơi trừu tượng, có thể hình dung method được đo tương đương mã Java nguồn sau (chỉ mô tả semantics; agent không sửa source):

~~~java
// Mô hình Java nguồn minh họa, không phải code biến đổi trực tiếp.
static int observed(String mode) {
    ExitHooks.enter();
    try {
        int result = Worker.run(mode);
        ExitHooks.normal();
        return result;
    } catch (Throwable original) {
        ExitHooks.exception(original);
        throw original;
    }
}
~~~

Nếu Worker.run("call") ném IllegalStateException từ downstream, khối **catch** ở wrapper vẫn chạy. Nếu Worker.run("divide") ném ArithmeticException tại **IDIV**, wrapper vẫn bắt được. Mô hình này cho thấy điểm đo phải bao quanh **quá trình thực thi**, không chỉ các statement **throw** của method.

Tuy nhiên, mã nguồn trên **không hoàn toàn giống transform được chèn vào chính body** khi method có các catch nội bộ, nhiều return và exception phát sinh từ hook: wrapper có thể bắt cả ngoại lệ từ **ExitHooks.normal()**, trong khi production nên thiết kế hook không ném exception. Ngoài ra, một wrapper bên ngoài có thể không thấy ngoại lệ đã bị target method bắt và chuyển thành return bình thường, đúng với khái niệm exceptional *exit*.

### 8.1. Vì sao không chỉ dùng finally?

**finally** có thể ghi một sự kiện “method kết thúc” cho cả return lẫn exception; nhưng nếu cần phân biệt **NORMAL** với **EXCEPTIONAL**, phải thiết kế thêm state hoặc catch để biết kiểu exit. Một biến cờ gán trước return có thể hoạt động cho mã đơn giản, nhưng nếu logic cleanup/hook ném exception sau đó, trạng thái báo cáo có thể khác kết quả caller thực nhận. Catch-all với handler rethrow có ngữ nghĩa rõ hơn cho **exceptional exits**, còn normal hook được gắn riêng ở return.

Nếu muốn chỉ có một sự kiện duy nhất ở mọi exit, có thể thiết kế chung một finally-like hook với trạng thái và kiểm tra control flow; vẫn phải cập nhật bytecode/frame, giữ exception object và không ghi đúp. Chỉ chèn code trước những opcode return sẽ không xử lý mọi exceptional exit.

## 9. Những giới hạn không thể giải quyết chỉ bằng catch-all method body

### 9.1. Method chưa thực sự được vào

Lỗi **NoClassDefFoundError**, **ExceptionInInitializerError** hoặc lỗi liên kết có thể xảy ra khi **caller cố gọi method** nhưng lớp đích chưa được khởi tạo/resolve đầy đủ. Trong tình huống đó, bytecode của **method đích** có thể **chưa hề được thực thi**, nên handler bên trong method đích không thể ghi entry/exit. Instrument **call site** hoặc method caller nếu muốn quan sát thất bại ở ranh giới lời gọi.

Phải phân biệt:

~~~text
Caller -> chuẩn bị/resolve class của Callee -> thất bại
            (Callee body không bắt đầu)

Caller -> Callee body chạy -> ném lỗi
            (handler ở Callee có thể bắt exceptional exit)
~~~

### 9.2. Exception được xử lý bên trong method

Nếu method tự catch lỗi và trả giá trị fallback, nó **trả về bình thường**. Handler catch-all ở cuối không nên ghi exceptional exit; nếu muốn đếm tất cả exception từng bị throw, cần instrument thrown/catch events với một định nghĩa KPI khác.

### 9.3. Exception xảy ra bất đồng bộ

Method có thể trả **CompletableFuture**, **CompletionStage**, **Future**, **Publisher**, hoặc khởi chạy thread rồi trả về trước khi công việc thực sự thất bại. Ví dụ:

~~~java
// Đoạn minh họa không độc lập; future thất bại sau khi method return.
java.util.concurrent.CompletableFuture<String> loadAsync() {
    return java.util.concurrent.CompletableFuture.supplyAsync(() -> {
        throw new IllegalStateException("background");
    });
}
~~~

Method **loadAsync()** đã **return bình thường** với một future; exception xảy ra ở task thread và được biểu diễn qua future completion. Handler quanh **loadAsync** không thể tự bắt lỗi này. Muốn đo **lỗi nghiệp vụ bất đồng bộ**, instrument completion callback, async boundary hoặc task execution thích hợp; cần truyền trace context giữa thread nếu cần.

### 9.4. Constructor và uninitialized this

**AdviceAdapter.onMethodEnter** có ngữ nghĩa riêng cho constructor: nó thường chỉ gọi sau khi lời gọi **super()/this()** phù hợp đã hoàn thành. Catch-all bao phủ cả vùng trước khi object được khởi tạo hợp lệ có thể gây lỗi verifier hoặc vi phạm quy tắc uninitialized-this. Ví dụ chỉ instrument **static methods**. Với constructor, phải đặt handler và advice sau mốc hợp lệ hoặc dùng thiết kế chuyên biệt có kiểm thử JVM verifier.

### 9.5. Native, abstract và synchronized methods

- **Abstract/native method** không có Java **Code attribute** để chèn try/catch body theo cách thông thường. Cần giải pháp khác hoặc instrument caller/wrapper.
- Với **synchronized method**, hook normal-exit được chèn trước return của body, còn monitor do JVM quản lý có thể được release khi method thực sự kết thúc. Việc đo duration ở hook có thể chưa bao gồm toàn bộ chi phí ngoài body/monitor release tùy định nghĩa. Tránh gọi logging blocking trong synchronized method vì làm kéo dài thời gian giữ monitor.
- Với **JNI**, exception có thể được tạo/lưu theo cơ chế native và truyền lại khi native call kết thúc; catch-all trong Java caller có thể thấy Throwable khi nó lan ra, nhưng không quan sát được từng chi tiết bên trong native body chỉ nhờ bytecode Java.

### 9.6. Lỗi của cơ chế instrumentation

Nếu JVM từ chối bytes agent trả về (sai exception table, sai StackMapTable, bytecode không hợp lệ), ứng dụng có thể nhận **VerifyError/ClassFormatError/LinkageError** khi định nghĩa hoặc sử dụng class. Đó là lỗi **của quá trình cài instrumentation**, không phải exceptional exit bình thường của method đã instrument. Phải có bước kiểm tra class load/retransform và phép thử behavior riêng.

## 10. Kiểm tra bytecode, stack frame và handler order

Sau khi build, có thể kiểm tra **method gốc trên đĩa** bằng:

~~~bash
javap -c -v -p -classpath target/exception-exit-agent.jar 'demo.App$Worker'
~~~

JAR chứa class file **chưa được JVM transform tại runtime**, nên javap đọc trực tiếp nó **không hiển thị synthetic handler của agent**. Để xem kết quả transform thực, cần dump byte[] mà agent trả về vào file **có kiểm soát**, hoặc dùng công cụ/đường export thích hợp rồi disassemble bản đó. Không kết luận “transformer không chạy” chỉ vì javap của file gốc không thấy handler.

Khi xem bản transformed, cần kiểm tra:

1. Có một **exception table entry** bổ sung với phạm vi chính xác **[bodyStart, bodyEnd)** và catch type **java/lang/Throwable**.
2. Entry catch-all của agent nằm **sau handler nghiệp vụ** cần ưu tiên.
3. Handler ghi vào **local slot mới**, không đè lên local thuộc method.
4. Handler **không nằm trong chính protected range**.
5. Những opcode return phù hợp đều có normal hook.
6. Opcode **ATHROW** tường minh không bị xử lý hai lần; exception được truyền đúng.
7. **Max stack/max locals/StackMapTable** được ghi lại hợp lệ; JVM verifier chấp nhận class.
8. Các instruction/callsite gốc và try/catch logic không bị vô tình thay đổi.

Với class có inheritance phức tạp hoặc custom defining class loader, **ClassWriter.COMPUTE_FRAMES** mặc định có thể cố resolve common superclass bằng class loader không đúng với target. Đó là lý do không nên triển khai mẫu đơn giản này lên mọi class production mà thiếu chính sách type-resolution, classloader visibility và tests.

### 10.1. Khi nào cần test exception handler có sẵn?

Tạo một method:

~~~java
// Đoạn minh họa.
static int safeParse(String value) {
    try {
        return Integer.parseInt(value);
    } catch (NumberFormatException ignored) {
        return -1;
    }
}
~~~

Nếu test **safeParse("not-a-number")**, kết quả đúng của **exceptional-exit instrumentation** là **NORMAL** vì method trả **-1**. Nếu handler agent ghi **EXCEPTION** trước khi catch của ứng dụng chạy, thứ tự exception table hoặc phạm vi catch-all đã bị cài sai.

Nếu ứng dụng chỉ catch **NumberFormatException** nhưng callee ném **OutOfMemoryError**, handler bắt **Throwable** của agent có thể nhìn thấy error thoát method và phải ném lại cùng object. Không dùng catch-all để làm ứng dụng có vẻ “ổn định” bằng cách giấu những lỗi nguy hiểm.

## 11. Test matrix cho điểm đo cuối method

| Trường hợp | Có ATHROW ở method đang đo? | Kỳ vọng event |
| --- | --- | --- |
| Return bình thường | Không | **NORMAL** đúng một lần |
| Method tự throw và không catch | Có | **EXCEPTIONAL** đúng một lần |
| Method gọi callee ném unchecked exception | Có thể không | **EXCEPTIONAL** đúng một lần |
| IDIV chia 0 | Không cần | **EXCEPTIONAL** đúng một lần |
| Dereference null | Không cần | **EXCEPTIONAL** đúng một lần |
| Index ngoài mảng | Không cần | **EXCEPTIONAL** đúng một lần |
| Method catch nội bộ rồi return fallback | Có thể có ở callee | **NORMAL**, không ghi false exceptional exit |
| Method catch rồi rethrow | Có hoặc không | **EXCEPTIONAL** đúng một lần |
| Hook quan sát tự lỗi | Không thuộc business method | Không được phá semantics ứng dụng theo thiết kế production |
| Async task lỗi sau khi method trả | Không nằm trong method return này | **NORMAL** cho method, đo async completion riêng |
| Constructor lỗi trước super init | Phụ thuộc tình huống | Không suy luận từ catch-all đặt trong body sau super |
| Lỗi class initialization trước khi vào method | Method chưa chạy | Cần quan sát ở caller/call site |

### 11.1. Những assertion quan trọng

Khi test, ngoài log hãy kiểm tra:

- **Caller nhận đúng kiểu Throwable** (**IllegalStateException**, **NullPointerException**, **ArithmeticException**, …).
- **Cùng object Throwable** được ném lại nếu đo trực tiếp identity (không wrapper ngoài ý muốn).
- Không có thay đổi return value/side effect của method bình thường.
- Event **NORMAL** và **EXCEPTIONAL** không xuất hiện cùng nhau cho một invocation hợp lệ.
- Có đúng một event exit cho mỗi invocation (trừ chính sách sampling/drop có chủ đích).
- Handler có sẵn được ưu tiên, nên exception đã được method xử lý không bị tính là exceptional exit.
- Dưới load đồng thời, biến đếm/log không race, deadlock hoặc leak class loader.

Nếu thêm latency measurement, định nghĩa rõ đồng hồ bắt đầu/kết thúc, overhead của hook, sự khác nhau giữa synchronous completion và async completion. **System.nanoTime()** thích hợp đo duration tương đối trong cùng JVM nhưng không nên dùng để suy ra wall-clock timestamp tuyệt đối.

## 12. Những lỗi thiết kế phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ hook ATHROW | Bỏ sót callee/instruction exception | Thêm catch-all bảo vệ body |
| Hook ATHROW và catch-all cùng log | Đếm trùng explicit throw | Bỏ exceptional hook tại ATHROW; handler ghi một lần |
| Hook mọi ATHROW dù method tự catch | Ghi false exceptional exit | Để handler ứng dụng có quyền xử lý trước |
| Catch-all đứng trước catch gốc | Thay semantics try/catch của ứng dụng | Thêm catch-all sau handler gốc |
| Handler không rethrow | Biến lỗi thành return hoặc nuốt Error | Ném lại đúng Throwable object |
| Handler tạo exception mới | Đổi type/cause/stack/identity | Ghi rồi rethrow ban đầu |
| Handler nằm trong protected region | Tự bắt lỗi của chính handler | Đặt handler ngoài [start, end) |
| Chèn advice vào constructor trước super | Verifier/uninitialized-this lỗi | Điểm đo riêng cho constructor |
| Sai local slot hoặc frame | VerifyError/class load failure | Cấp local qua ASM và tính frame đúng |
| Instrument method mà helper không visible | NoClassDefFoundError/IllegalAccessError lúc chạy | Quản lý loader/module và package access |
| Logger blocking/ném exception | Tăng latency hoặc phá exception gốc | Hook tối thiểu, nonthrowing, fallback |
| Coi future failure là sync method exit | Đếm sai lỗi async | Instrument completion/callback |
| Dùng javap trên JAR gốc để kiểm chứng transformed bytes | Không thấy handler dù agent hoạt động | Dump đúng output classfileBuffer để đối chiếu |
| Chỉ nhìn log TRANSFORMED rồi coi là thành công | JVM có thể từ chối bytes | Kiểm tra class definition + hành vi thật |

## 13. Câu hỏi tự kiểm tra

1. **Service chỉ gọi repository(), nhưng repository() ném exception; Service có cần ATHROW không?** Không. Lệnh invocation có thể kết thúc bất thường và exception unwind qua Service.
2. **IDIV với divisor 0 ném exception qua opcode nào?** **IDIV** gây **ArithmeticException**; không cần ATHROW trực tiếp trong body.
3. **AdviceAdapter.onMethodExit(ATHROW) có thấy exception được callee ném qua INVOKESTATIC không?** Không, nếu method caller không thực thi ATHROW trên đường lỗi đó.
4. **Vì sao hook ATHROW có thể gây false positive?** ATHROW có thể nằm trong nhánh được catch nội bộ; method sau đó return bình thường.
5. **Synthetic catch-all handler nên nằm ở đâu?** Bao phủ body cần đo, đặt ngoài chính phạm vi bắt của nó và sau các exception handler nghiệp vụ khi cần giữ ưu tiên.
6. **Vì sao phải catch Throwable?** Để quan sát cả **Exception** lẫn **Error** thoát method, đồng thời ném lại thay vì nuốt.
7. **Có thể return giá trị mặc định sau khi catch để app tiếp tục không?** Không nếu yêu cầu bảo toàn semantics; điều đó che lỗi của ứng dụng.
8. **Nếu method trả CompletionStage thành công rồi task sau đó lỗi, catch-all quanh method có thấy lỗi không?** Không. Lỗi xuất hiện ở asynchronous completion, cần instrument ranh giới khác.
9. **Javap trên class JAR gốc có hiển thị handler chèn lúc runtime không?** Không. Phải kiểm tra bytes thực do transformer cung cấp hoặc kết quả runtime.
10. **Bằng chứng đúng nhất cho một điểm đo exceptional exit là gì?** Caller vẫn thấy đúng Throwable, log nhận **một exceptional-exit event** ở cả direct throw, callee exception và implicit instruction exception; normal return và catch nội bộ không bị báo sai.

## 14. Checklist áp dụng vào Java agent thực tế

- Tôi đã xác định KPI là **exception thrown event**, **exceptional method exit**, hay **async task failure**; không trộn chúng.
- Tôi hiểu **ATHROW không bao phủ mọi exceptional exit** từ method calls/instructions.
- Instrumenter dùng đúng method name/descriptor, class loader/module, không chỉnh nhầm method/lớp khác.
- Normal exit hook có mặt ở các return opcode hợp lệ; exceptional exit dùng catch-all chứ không chỉ ATHROW.
- Catch-all bao phủ đúng vùng body, **không nuốt exception** và **rethrow cùng object**.
- Handler ứng dụng được ưu tiên, synthetic handler nằm ngoài protected range của chính nó.
- Stack, local slots, exception table và StackMapTable hợp lệ sau khi viết class file.
- Hook telemetry được thiết kế để không làm đổi lỗi/return của ứng dụng; overhead và tác động locking được đánh giá.
- Constructors, native/abstract methods, class initialization failures và asynchronous operations có chiến lược riêng.
- Tôi đã thử **normal, callee throw, NPE, arithmetic, explicit throw, internally caught exception** và ít nhất một phép thử concurrency khi cần.
- Tôi xác minh JVM đã **chấp nhận class file** và caller vẫn quan sát đúng hành vi, không chỉ dựa vào log transform.

## 15. Tài liệu chuẩn

- [Java Virtual Machine Specification 17 — Exceptions, §2.10](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.10): xử lý exception và tìm exception handler.
- [Java Virtual Machine Specification 17 — Code attribute, §4.7.3](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3): exception table, start_pc, end_pc, handler_pc và catch_type.
- [Java Virtual Machine Specification 17 — ATHROW và tập lệnh JVM](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): semantics instruction, implicit exceptions.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): return byte[], giữ nguyên input buffer và transformer contract.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký transformer và khả năng retransform.
- [ASM commons 9.7.1 trên Maven Central](https://central.sonatype.com/artifact/org.ow2.asm/asm-commons/9.7.1): thư viện chứa AdviceAdapter và các tiện ích cho bytecode instrumentation.

**Kết luận:** để đo **mọi lần một method kết thúc vì Throwable**, không thể chỉ dựa trên việc bytecode của method có lệnh **ATHROW**. Ngoại lệ có thể **lan lên từ callee** hoặc **phát sinh tại nhiều instruction khác**. Giải pháp điển hình là **normal hook cho return + catch-all handler bao phủ body**, giữ đúng thứ tự catch và **rethrow cùng Throwable**; sau đó kiểm chứng bằng bytecode thực và hành vi của ứng dụng.
