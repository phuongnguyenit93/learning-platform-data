# Báo cáo giả thuyết, bằng chứng bytecode, kết quả chạy và giới hạn của Java agent

## 1. Từ “agent chạy được” đến một báo cáo có thể kiểm chứng

Khi thực nghiệm Java instrumentation, kết luận **“đã instrument thành công”** chỉ đáng tin nếu đi kèm các bằng chứng có thể kiểm tra độc lập. Một dòng log `agent started` chứng minh JVM có gọi điểm khởi động agent, **không** chứng minh transformer đã khớp lớp, đã sinh bytecode hợp lệ, method thực sự chạy instruction mới hay dữ liệu nghiệp vụ còn nguyên.

Báo cáo tốt phải nối được chuỗi:

~~~text
Đề xuất / giả thuyết (có thể bị bác bỏ)
        |
        v
Điều kiện thí nghiệm + baseline + đối chứng âm
        |
        v
Bằng chứng cấu trúc: original .class vs transformed .class
        |
        v
Bằng chứng thực thi: JVM verifier + input/output + side effects
        |
        v
Phân tích: kết quả nào ủng hộ giả thuyết nào?
        |
        v
Giới hạn, giả định, sự cố có thể lọt qua và thử nghiệm kế tiếp
~~~

Bài Knowledge này cung cấp **một báo cáo thí nghiệm hoàn chỉnh**, từ câu hỏi nghiên cứu đến mã nguồn, lệnh chạy, stdout đã kiểm chứng, trích đoạn `javap`, chương trình xác minh bytecode riêng và kết luận đúng phạm vi.

Ví dụ thực tế: một Java agent sử dụng **Class-File API chuẩn JDK 24** chèn đúng **một lời gọi `Probe.hit()` ở đầu `PriceService.price(int)`**. Báo cáo sẽ kiểm tra phương thức trả về bình thường, đường ném ngoại lệ, một method không được chọn trong cùng class và một class đối chứng không thuộc matcher.

**Điểm quan trọng:** đây là bài về **phương pháp chứng minh kết quả agent**, không phải lời khẳng định chỉ cần một log, một screenshot hoặc một lần chạy thành công là đủ để chứng minh an toàn production.

## 2. Sáu khái niệm phải tách bạch trong báo cáo

| Thành phần | Định nghĩa | Ví dụ trong bài |
| --- | --- | --- |
| **Giả thuyết (H)** | Phát biểu cụ thể có khả năng bị kết quả thực nghiệm bác bỏ | “Output class có đúng một `INVOKESTATIC Probe.hit:()V` trong `price(int)`.” |
| **Dự đoán (prediction)** | Điều có thể đo trước khi chạy | Baseline probe count 0, với agent probe count 2 |
| **Phép thử (procedure)** | Điều kiện, lệnh, input, bước tạo evidence | `javac --release 24`, `-javaagent`, `javap`, verifier |
| **Quan sát (observation)** | Dữ liệu công cụ thực sự trả về | `transformed.price.probeCalls=1` |
| **Diễn giải (interpretation)** | Lập luận gắn quan sát với giả thuyết | Một callsite helper được thêm vào method `price` |
| **Giới hạn (limitation)** | Điều quan sát **chưa thể** chứng minh | Không chứng minh mọi loader/JVM/method/luồng đều an toàn |

Một **assertion được kiểm thử** nên nằm ở tầng quan sát được. Ví dụ, “bytecode đã đổi” nên được xác nhận bằng phép duyệt instruction hoặc `javap`, **không** dựa duy nhất vào thông báo do chính transformer in ra. Tương tự, “không ảnh hưởng nghiệp vụ” nên có ít nhất các input đối chứng và exception cases, nhưng ngay cả vậy cũng chỉ đúng **với những trường hợp đã chạy**.

### 2.1. Phân biệt evidence trực tiếp và suy luận

**Evidence trực tiếp:** JDK Class-File API đọc bản class sau transform và tìm được instruction:

~~~text
INVOKESTATIC demo/agent/Probe.hit:()V
~~~

**Suy luận hợp lý có giới hạn:** phương thức `price` sau biến đổi đã chứa callsite static tới helper, và khi chạy qua code path test, counter helper tăng.

**Suy luận quá mức:** “Mọi method trong mọi module đều sẽ được instrument”, “không bao giờ có `VerifyError`”, “overhead bằng không”, hoặc “mọi exception đều được đo”. Những khẳng định đó **không được phép** suy ra từ một test nhỏ.

### 2.2. Báo cáo phải có tiêu chí dừng và tiêu chí thất bại

Trước khi viết transformer, định nghĩa:

- **PASS:** bao nhiêu lời gọi helper phải tồn tại, ở method nào; stdout nào phải xuất hiện; loại exception nào phải giữ nguyên; JVM verifier phải không báo lỗi.
- **FAIL:** sai owner/opcode/descriptor, zero hoặc double instrumentation, output nghiệp vụ thay đổi, class control bị tác động, exception sai loại, JVM load thất bại.
- **INCONCLUSIVE:** chưa chạy được JVM đúng phiên bản, không có transformed bytes, tool kiểm tra hỏng, hoặc thiếu phép đối chứng cần thiết.

Không dùng kết luận “PASS” khi chỉ chạy compile mà bỏ qua runtime, cũng không coi “transformer trả non-null” là một bằng chứng đầy đủ.

## 3. Câu hỏi nghiên cứu và bốn giả thuyết có thể bác bỏ

**Câu hỏi:** Một agent load-time có thể thêm một lời gọi helper tại entry của đúng một method mà những quan sát nghiệp vụ đã chọn vẫn không thay đổi không?

Trong môi trường thử:

- Target class: `demo.report.PriceService`.
- Target method: `public static int price(int)` với descriptor JVM `(I)I`.
- Helper: `demo.agent.Probe.hit():void`, descriptor `()V`.
- Control trong cùng class: `PriceService.label()`.
- Control class khác: `demo.report.ControlService`.
- Hai input cho target: `price(3)` (normal return) và `price(-1)` (throws).

| Mã | Giả thuyết được công bố **trước khi chạy** | Tiêu chí bác bỏ rõ ràng |
| --- | --- | --- |
| **H1 — biến đổi có mục tiêu** | Output `PriceService.class` có đúng **1** `INVOKESTATIC Probe.hit:()V` trong `price(int)`, ở instruction đầu; bản gốc có 0 | Không có hook, có nhiều hơn 1, sai opcode/owner/type hoặc hook không ở đầu |
| **H2 — không lan sang method đối chứng** | `label()` vẫn có **0** lời gọi `Probe.hit`; transformer không chủ động chọn `ControlService` | Verifier thấy hook trong `label` hoặc control không còn hành vi dự kiến |
| **H3 — giữ output/exception đã chọn** | Có và không có agent đều cho `price(3)=21`, `price(-1)` ném `IllegalArgumentException`, `label=SAFE`, `ControlService.twice(5)=10` | Một trong bốn kết quả khác baseline |
| **H4 — side effect của hook thật sự xảy ra** | Không có agent: `Probe.hits=0`; có agent: sau hai lời gọi `price`, `Probe.hits=2` | Counter khác dự đoán hoặc JVM verifier/load thất bại |

H1 là bằng chứng **class-file structure**. H2 dùng đối chứng trong cùng class và control class. H3 là bằng chứng **behavior trên bộ input kiểm thử**. H4 là bằng chứng **runtime execution** và việc gọi hook ở cả entry của normal/throw path; nó **không** chứng minh agent phân loại outcome return/throw, vì demo chỉ đếm entry.

### 3.1. Vì sao cần cả đối chứng âm?

Nếu chỉ thấy counter 2 sau hai lần gọi, có thể `Probe.hit()` đã được viết sẵn ở source, được gọi từ `Main`, hoặc agent vô tình instrument quá rộng. Đối chứng và diff bytecode giúp loại trừ một số giải thích khác:

- Source `PriceService` **không** gọi helper.
- Baseline không agent có `probe.hits=0`.
- `PriceService.label()` không có helper invocation trong bản gốc **và** bản biến đổi.
- `ControlService.twice(5)` trả 10 trong cả hai chế độ.
- Chỉ `price(int)` có instruction mới ở đầu body.

Đối chứng âm giúp tăng độ tin cậy, **nhưng vẫn không chứng minh** tất cả các class khác trong JVM không bao giờ bị instrument: thí nghiệm chỉ quan sát phạm vi cụ thể.

## 4. Thiết kế thí nghiệm để so sánh công bằng

Thực hiện **hai tiến trình JVM tách biệt**:

~~~text
Nhánh A — baseline:
    app-classes + agent JAR trong classpath
    KHÔNG có -javaagent
    gọi price(3), price(-1), label(), twice(5)
    in Probe.hits

Nhánh B — treatment:
    CÙNG app-classes + agent JAR
    CÓ -javaagent:report-agent.jar
    CÓ -Xverify:all
    gọi CÙNG input và thứ tự
    in Probe.hits

Thu thêm evidence:
    original PriceService.class
    transformed PriceService.class
    javap original / transformed
    VerifyEvidence đọc hai tệp và assert cấu trúc
~~~

**Giữ giống nhau:** compiler `javac --release 24`, source, các input, classpath và cách gọi business method. **Khác nhau có chủ đích:** nhánh B có tham số khởi động `-javaagent`, làm JVM gọi `premain` và đăng ký `ClassFileTransformer`.

Đặt agent JAR trong classpath **ở cả hai nhánh** giúp class `Probe` có mặt để `Main` đọc counter, nhưng **chỉ nhánh B** mới chạy `premain`. Điều này tránh ngộ nhận “chỉ cần thêm agent JAR vào `-cp` là agent hoạt động”.

### 4.1. Các yếu tố không hoàn toàn được kiểm soát

Không đồng nhất hai JVM với cùng một tiến trình: JVM có thể chọn JIT timing/GC/scheduling khác nhau. Bài **không so thời gian thực thi**, nên những biến đó không làm vô hiệu các assertion **đếm instruction, counter và output cụ thể**. Nếu muốn đo overhead sau này, cần lặp đủ lượt, warmup, phân tích thống kê và môi trường ổn định.

Trong ứng dụng thực tế, việc nạp class có thể xảy ra sớm hơn mong muốn. Agent phải được đăng ký trước target class definition; nếu target đã load thì `addTransformer(..., false)` đơn thuần không biến đổi class đó ngược thời gian.

## 5. Môi trường và công cụ được ghi trong báo cáo

**Môi trường đã dùng để kiểm chứng ví dụ:**

| Thuộc tính | Giá trị thực nghiệm |
| --- | --- |
| Hệ điều hành/shell | Windows, PowerShell |
| Compiler | `javac 24.0.2` |
| Runtime | Zulu/OpenJDK **24.0.2** |
| Mức bytecode | `javac --release 24`, class-file major **68** |
| Class-file manipulation | `java.lang.classfile`, chuẩn hóa trong **JDK 24** (JEP 484) |
| Cơ chế agent | `java.lang.instrument`, `premain` với `-javaagent` |
| JVM verification | `-Xverify:all` trên cả hai lần chạy |
| Đọc opcode | `javap -c -p` |
| Kiểm chứng tự động | `VerifyEvidence` đọc bytes bằng JDK 24 Class-File API |
| Bên thứ ba | Không dùng ASM/Byte Buddy |
| Input | `3` và `-1` cho `price`; `5` cho control |

**Phiên bản là yếu tố bắt buộc:** JDK 17/21 không hỗ trợ package **`java.lang.classfile` chuẩn** theo mẫu JDK 24 này. Không được báo `COMPLETED/RUN_PASS` từ máy JDK 17 nếu chưa có một quy trình test thực với API khác.

**Thông tin nên ghi trong report thật:** timestamp thực thi, git revision hoặc content hashes của source, full `java -version`/`javac -version`, architecture, module/classpath, command line, test inputs, exit codes, logs và SHA-256 của artifacts. Đừng giả định dữ liệu mẫu của một máy là giá trị bắt buộc trên mọi máy.

### 5.1. Hợp đồng `ClassFileTransformer`

Javadoc xác nhận transformer được gọi **trước khi JVM định nghĩa class**, trả `null` nếu không thay đổi, hoặc **một mảng `byte[]` mới** nếu thay đổi; **không** được sửa mảng `classfileBuffer` đầu vào. Nhiều transformer có thể được gọi nối tiếp, nên không được mặc định bytes cuối cùng chỉ do một agent quyết định.

Javadoc cũng nói exception chưa bắt trong transformer không nhất thiết làm class loading dừng; JVM vẫn thử các transformer tiếp theo và tiếp tục load tương tự transformer trả `null`. Vì thế việc **assert dựa vào output class thực tế** quan trọng hơn một dòng log từ transformer.

Nguồn: [Java 24 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).

## 6. Cấu trúc dự án để người khác tái lập

~~~text
agent-evidence-report/
  agent-src/demo/agent/
    Probe.java
    ReportAgent.java
  app-src/demo/report/
    PriceService.java
    ControlService.java
    Main.java
  tool-src/
    VerifyEvidence.java
  MANIFEST.MF
  agent-classes/                    (javac tạo)
  app-classes/                      (javac tạo)
  tool-classes/                     (javac tạo)
  report-agent.jar                  (jar tạo)
  transformed/demo/report/
    PriceService.class              (agent dump khi test)
~~~

Có **6 tệp Java đầy đủ**. `Probe` được đóng trong JAR agent; `Main` tham chiếu `Probe.hits()` nhưng không gọi `Probe.hit()` trực tiếp. `VerifyEvidence` là chương trình độc lập dùng cùng JDK 24 nhưng **không chạy trong callback transformer**, tránh chỉ tin vào báo cáo do agent tự in.

Tất cả các đường dẫn ở đây tương đối so với **thư mục gốc dự án**. Bản dump dưới `transformed` chỉ là artifact của bài kiểm chứng; production không cần ghi classfile ra đĩa trong hot path.

## 7. Mã nguồn ứng dụng: kết quả nghiệp vụ và đối chứng

### 7.1. `app-src/demo/report/PriceService.java`

~~~java
package demo.report;

public final class PriceService {
    public static int price(int units) {
        if (units < 0) throw new IllegalArgumentException("units");
        return units * 7;
    }

    public static String label() {
        return "SAFE";
    }
}
~~~

Trong `price(int)` có **hai đường thoát**: `return units * 7` và `throw IllegalArgumentException`. Phương thức `label()` cùng class là một **negative control** để kiểm tra matcher không vô tình chèn hook vào tất cả các method.

### 7.2. `app-src/demo/report/ControlService.java`

~~~java
package demo.report;

public final class ControlService {
    public static int twice(int number) {
        return number * 2;
    }
}
~~~

Đây là một **class khác** mà agent **không chọn**. Việc nó vẫn trả `10` cho input `5` là control hành vi. Nó không đại diện cho mọi class khác của JVM: test không quét toàn bộ hệ thống.

### 7.3. `app-src/demo/report/Main.java`

~~~java
package demo.report;
import demo.agent.Probe;

public final class Main {
    public static void main(String[] args) {
        System.out.println("price3=" + PriceService.price(3));
        try {
            PriceService.price(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "error=" + expected.getClass().getSimpleName());
        }
        System.out.println("label=" + PriceService.label());
        System.out.println("control=" + ControlService.twice(5));
        System.out.println("probe.hits=" + Probe.hits());
    }
}
~~~

**Vì sao `Main` dùng `Probe.hits()`?** Để in counter sau hai invocation. `Main` **không** gọi `Probe.hit()`, nên khi counter tăng trong treatment, kết hợp với bằng chứng bytecode có thể quy về lời gọi mới trong `price`.

**Vì sao không bắt rộng `Throwable`?** Trong bài test, caller chỉ mong đợi `IllegalArgumentException` ở input âm. Nếu agent làm xuất hiện `LinkageError` hoặc lỗi khác, chúng phải lộ ra để test thất bại thay vì bị một `catch(Throwable)` che giấu.

## 8. Helper và hợp đồng side effect được phép

**Tệp `agent-src/demo/agent/Probe.java`**

~~~java
package demo.agent;
import java.util.concurrent.atomic.AtomicInteger;

public final class Probe {
    private static final AtomicInteger HITS = new AtomicInteger();

    private Probe() { }

    public static void hit() {
        HITS.incrementAndGet();
    }

    public static int hits() {
        return HITS.get();
    }
}
~~~

Đây là helper nhỏ, chỉ tăng counter. Trên đường hot path thật, `AtomicInteger` vẫn tạo overhead; nhưng so với `System.out.println` mỗi invocation, nó dễ kiểm thử và ít tác động hơn.

**Hợp đồng đo của demo:** một lần vào `price` ⇒ một lần gọi `Probe.hit`, bất kể method sau đó return hay throw. Vì hook được chèn **ở entry**, kết quả `probe.hits=2` không nói được trong hai lời gọi có bao nhiêu return/throw, trừ khi kết hợp với output/exception test. Nếu cần đo **exit outcomes**, phải chèn exit hooks/exception handler riêng với kiểm thử tương ứng.

`AtomicInteger` là thread-safe cho phép cộng, nhưng nó không phân biệt class loader hoặc trace ID. Nếu helper được định nghĩa ở **hai class loaders khác nhau**, có thể có hai bản static counter độc lập. Ví dụ dùng classpath/loader đơn giản để tránh biến đó.

## 9. Java agent tạo bytecode mới bằng Class-File API JDK 24

**Tệp `agent-src/demo/agent/ReportAgent.java`**, toàn bộ mã đã biên dịch và chạy:

~~~java
package demo.agent;

import java.lang.classfile.*;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class ReportAgent {
    private static final ClassDesc PROBE =
            ClassDesc.of("demo.agent.Probe");
    private static final MethodTypeDesc NO_ARGS_VOID =
            MethodTypeDesc.ofDescriptor("()V");

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new OneMethodTransformer(), false);
        System.out.println("agent.ready=true");
    }

    private static final class OneMethodTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(ClassLoader loader, String className,
                Class<?> redefining, ProtectionDomain domain, byte[] bytes) {
            if (!"demo/report/PriceService".equals(className)) {
                return null;
            }

            ClassFile cf = ClassFile.of();
            CodeTransform addEntry = CodeTransform.ofStateful(() ->
                    new CodeTransform() {
                @Override
                public void atStart(CodeBuilder out) {
                    out.invokestatic(PROBE, "hit", NO_ARGS_VOID);
                }

                @Override
                public void accept(
                        CodeBuilder out, CodeElement element) {
                    out.with(element);
                }
            });

            byte[] result = cf.transformClass(cf.parse(bytes),
                    ClassTransform.transformingMethodBodies(
                            m -> m.methodName().equalsString("price")
                                    && m.methodType().equalsString("(I)I"),
                            addEntry));
            try {
                Path destination = Path.of(
                        "transformed/demo/report/PriceService.class");
                Files.createDirectories(destination.getParent());
                Files.write(destination, result);
            } catch (java.io.IOException ex) {
                throw new IllegalStateException(
                        "test dump failed", ex);
            }

            System.out.println("agent.transformed=" + className);
            return result;
        }
    }
}
~~~

### 9.1. Match class, rồi match đúng method descriptor

Trong callback, `className` ở dạng **internal name với dấu slash** `"demo/report/PriceService"`. Còn `ClassDesc.of("demo.agent.Probe")` dùng **binary name có dấu chấm**. Nếu dùng nhầm một trong hai biểu diễn, transform có thể không khớp hoặc không gọi được helper.

Predicate:

~~~java
m -> m.methodName().equalsString("price")
        && m.methodType().equalsString("(I)I")
~~~

là **mảnh code lọc method**. Descriptor `(I)I` nghĩa nhận một `int` và trả một `int`. Nó tránh vô tình instrument overload `price(String)` nếu sau này được thêm.

`ClassTransform.transformingMethodBodies` biến đổi các method bodies được predicate chọn; các method khác được chuyển qua nguyên dạng mô hình. Trong bài, `label()` không được chọn, nên verifier phải cho `transformed.label.probeCalls=0`.

### 9.2. Vì sao `atStart` và `out.with(element)`?

`CodeTransform.ofStateful` cung cấp instance transform cho traversal, và `atStart(CodeBuilder)` phát instruction:

~~~java
out.invokestatic(PROBE, "hit", NO_ARGS_VOID);
~~~

Nó đặt một `INVOKESTATIC` ở entry, trước code gốc. `accept(...){ out.with(element); }` chuyển **mọi code element cũ** vào builder. Quên `out.with(element)` có thể làm mất thân method.

`NO_ARGS_VOID` là descriptor `()V`, phù hợp `public static void Probe.hit()`. Trong bản thử, helper không nhận tham số và không trả dữ liệu nên không phá operand stack đang dùng để tính `units * 7`.

**Không suy rộng:** method constructor, class initializer, native/abstract, exception handlers phức tạp, synchronized method hay bytecode có stack-map phức tạp có các ràng buộc riêng. Một thao tác `atStart` chạy được trên `price(int)` **không** tự động an toàn ở mọi method.

### 9.3. Tệp dump là công cụ tạo bằng chứng, không phải thao tác agent bắt buộc

Transformer ghi bản mới vào `transformed/demo/report/PriceService.class` bằng `Files.write` **chỉ để test độc lập**. Không cần dump để JVM nhận bytes; giá trị `byte[] result` trả về mới là đầu vào cho các bước tiếp theo của JVM.

Trong production, I/O đồng bộ trong `transform` có thể chặn class loading, gây recursion/circularity và tràn đĩa. Hệ thống báo cáo tự động nên dump với cờ debug trong môi trường kiểm thử, giới hạn số lớp, hash/dedupe và cleanup phù hợp.

### 9.4. Điều agent không làm

Bản thử **không**:

- Chỉnh source `PriceService.java`;
- Ghi đè `app-classes/demo/report/PriceService.class` gốc;
- Đổi constructor hoặc `label()`;
- Instrument `ControlService`;
- Đo elapsed time/CPU;
- Dùng `retransformClasses` cho class đã load;
- Chèn hook trước `return` hoặc sau exception;
- Bảo đảm helper luôn available trong mọi module/class loader;
- Thực hiện benchmark production.

Nêu rõ cả những việc **không** làm giúp ngăn người đọc diễn giải một kết quả PASS thành khả năng agent chưa từng được thử.

## 10. Verifier độc lập: biến lời báo cáo thành assertion

**Tệp `tool-src/VerifyEvidence.java`**

~~~java
import java.lang.classfile.*;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class VerifyEvidence {
    private static final ClassDesc HOOK =
            ClassDesc.of("demo.agent.Probe");

    private static void check(String label, Path file)
            throws Exception {
        ClassModel model = ClassFile.of()
                .parse(Files.readAllBytes(file));
        for (String name : new String[] {
                "price", "label"}) {
            var method = model.methods().stream()
                    .filter(m -> m.methodName().equalsString(name))
                    .findFirst().orElseThrow();
            var code = method.code().orElseThrow();
            List<Instruction> instructions =
                    code.elementStream()
                            .filter(e -> e instanceof Instruction)
                            .map(e -> (Instruction) e).toList();

            long probes = instructions.stream()
                    .filter(VerifyEvidence::isProbe)
                    .count();
            System.out.println(label + "." + name
                    + ".probeCalls=" + probes);

            long expected = label.equals("transformed")
                    && name.equals("price") ? 1 : 0;
            if (probes != expected) {
                throw new AssertionError(
                        label + "." + name + " count");
            }

            if (name.equals("price")) {
                boolean first =
                        isProbe(instructions.getFirst());
                System.out.println(label
                        + ".price.firstIsProbe=" + first);
                if (first != label.equals("transformed")) {
                    throw new AssertionError(
                            label + ".price first instruction");
                }
            }
        }
    }

    private static boolean isProbe(Instruction instruction) {
        return instruction instanceof InvokeInstruction call
                && call.opcode() == Opcode.INVOKESTATIC
                && call.owner().asSymbol().equals(HOOK)
                && call.name().equalsString("hit")
                && call.typeSymbol()
                        .descriptorString().equals("()V");
    }

    public static void main(String[] args)
            throws Exception {
        check("original", Path.of(
                "app-classes/demo/report/PriceService.class"));
        check("transformed", Path.of(
                "transformed/demo/report/PriceService.class"));
        System.out.println("verification=PASS");
    }
}
~~~

Khác với việc chỉ in số lượng, tool này có **`AssertionError` khi kết quả không khớp**; chỉ in `verification=PASS` khi **tất cả assertion đã chạy qua**.

Nó không hỏi transformer “bạn đã chèn gì?”, mà tự parse **hai tệp khác nhau** từ file system. Điều kiện `isProbe` kiểm tra:

- Opcode là `INVOKESTATIC`;
- Owner là `demo.agent.Probe`;
- Method name là `hit`;
- Descriptor là `()V`.

Không kiểm chứng bằng cách tìm chuỗi `Probe` trong constant pool: một class có thể chứa chuỗi đó trong metadata nhưng **không có instruction gọi method**.

**Đối chứng trong verifier:** `price` được kỳ vọng thay đổi 0→1, còn `label` giữ 0→0. Thêm kiểm tra instruction đầu tiên của `price` để phát hiện trường hợp hook được đặt sai vị trí dù tổng count vẫn bằng 1.

## 11. Manifest và lệnh biên dịch, chạy

**Tệp `MANIFEST.MF`**

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ReportAgent

~~~

Cần kết thúc main attributes bằng dòng trống. Ví dụ dùng `premain` và `-javaagent`, không dùng dynamic attach hay `agentmain`.

### 11.1. Windows PowerShell (đã thử)

Từ thư mục gốc `agent-evidence-report`:

~~~powershell
New-Item -ItemType Directory -Force agent-classes, app-classes, tool-classes | Out-Null

javac --release 24 -d agent-classes agent-src/demo/agent/ReportAgent.java agent-src/demo/agent/Probe.java

jar --create --file report-agent.jar --manifest MANIFEST.MF -C agent-classes .

javac --release 24 -cp report-agent.jar -d app-classes app-src/demo/report/PriceService.java app-src/demo/report/ControlService.java app-src/demo/report/Main.java

# A: baseline
java -Xverify:all -cp "app-classes;report-agent.jar" demo.report.Main

# B: agent
java -Xverify:all -javaagent:report-agent.jar -cp "app-classes;report-agent.jar" demo.report.Main

# Kiểm chứng độc lập, sau khi nhánh B đã tạo transformed/
javac --release 24 -d tool-classes tool-src/VerifyEvidence.java
java -cp tool-classes VerifyEvidence
~~~

PowerShell dùng dấu **chấm phẩy** để phân tách classpath. Mỗi lệnh có thể chạy riêng và nên kiểm tra **exit code**, không coi stdout đẹp là thành công nếu `javac`/`java` đã trả mã lỗi.

### 11.2. Linux/macOS Bash

~~~bash
mkdir -p agent-classes app-classes tool-classes

javac --release 24 -d agent-classes \
  agent-src/demo/agent/ReportAgent.java \
  agent-src/demo/agent/Probe.java

jar --create --file report-agent.jar --manifest MANIFEST.MF \
  -C agent-classes .

javac --release 24 -cp report-agent.jar -d app-classes \
  app-src/demo/report/PriceService.java \
  app-src/demo/report/ControlService.java \
  app-src/demo/report/Main.java

java -Xverify:all -cp "app-classes:report-agent.jar" demo.report.Main

java -Xverify:all -javaagent:report-agent.jar \
  -cp "app-classes:report-agent.jar" demo.report.Main

javac --release 24 -d tool-classes tool-src/VerifyEvidence.java
java -cp tool-classes VerifyEvidence
~~~

Bash dùng dấu **hai chấm** trong classpath và dấu `\` để nối dòng. Phần source Java tương thích JDK 24, nhưng **bản chạy đã thực hiện trên Windows**; trên macOS/Linux cần tái kiểm thử nếu muốn đưa nền tảng đó vào phạm vi xác nhận.

### 11.3. Tệp và dữ liệu phải thu thập sau khi chạy

Giữ tối thiểu:

~~~text
evidence/
  environment.txt      (java/javac version, OS, commands)
  baseline.stdout      (output không -javaagent)
  treatment.stdout     (output có -javaagent)
  original.javap.txt   (javap -c -p của .class gốc)
  transformed.javap.txt(javap -c -p của .class mới)
  verify.stdout        (stdout + exit code của VerifyEvidence)
  hashes.txt           (SHA-256 của các .class)
  hypothesis.md        (H1...H4 và tiêu chí PASS/FAIL)
  conclusion.md        (bảng bằng chứng, giới hạn)
~~~

Đây là **mẫu danh mục evidence**, không phải tuyên bố script phía trên tự tạo mọi file này. Người thực hiện có thể redirect stdout hoặc dùng CI artifact collector, và phải giữ đường dẫn/phiên bản đồng nhất để người khác không vô tình so output của các lần build khác nhau.

## 12. Kết quả chạy thực tế: baseline trước, treatment sau

### 12.1. Baseline — không có `-javaagent`

~~~text
price3=21
error=IllegalArgumentException
label=SAFE
control=10
probe.hits=0
~~~

**Giải thích quan sát:** method `price(3)` trả `3×7=21`, `price(-1)` ném đúng exception, hai đối chứng trả `SAFE`/`10`, helper count không tăng.

Câu “class `Probe` có trong classpath” **không** đồng nghĩa “đã instrument”. `Main` đọc `Probe.hits()` nhưng không gọi `hit()`.

### 12.2. Treatment — có agent và `-Xverify:all`

~~~text
agent.ready=true
agent.transformed=demo/report/PriceService
price3=21
error=IllegalArgumentException
label=SAFE
control=10
probe.hits=2
~~~

**Quan sát được:** JVM gọi `premain`, transformer khớp class đích, cả bốn kết quả nghiệp vụ đang theo dõi không đổi, và helper count tăng lên **2** sau hai lần gọi target.

Vì hook ở **entry**, cả `price(3)` và `price(-1)` đều tăng counter. **Không** được viết “agent đo 2 thành công”: một trong hai invocation đã ném exception. Muốn phân loại return/throw cần exit instrumentation riêng.

### 12.3. Một bảng before/after minh bạch

| Phép thử | Baseline | Có agent | Đánh giá trong phạm vi test |
| --- | --- | --- | --- |
| `price(3)` | `21` | `21` | Kết quả giống nhau |
| `price(-1)` | `IllegalArgumentException` | Cùng loại | Exception type được giữ |
| `label()` | `SAFE` | `SAFE` | Method đối chứng không đổi về output |
| `ControlService.twice(5)` | `10` | `10` | Control class không đổi về output |
| `Probe.hits()` | `0` | `2` | Side effect hook khác biệt đúng dự đoán |
| `-Xverify:all` | JVM chạy | JVM chạy | Bytecode của các class dùng trong test được VM chấp nhận |

**Tại sao không coi `Probe.hits=2` là performance metric?** Đây là số lần gọi helper, không phải thời gian, allocation, throughput, số trace được backend lưu hay xác suất sampling.

## 13. Bằng chứng bytecode: những instruction nào thực sự thay đổi?

Sau nhánh B, có hai files:

~~~text
app-classes/demo/report/PriceService.class
transformed/demo/report/PriceService.class
~~~

Dùng:

~~~bash
javap -c -p -classpath app-classes demo.report.PriceService
javap -c -p -classpath transformed demo.report.PriceService
~~~

### 13.1. `price(int)` ở bản gốc

Trích đoạn opcode, offsets đã kiểm thử:

~~~text
public static int price(int);
  Code:
     0: iload_0
     1: ifge          14
     4: new           #7    // class java/lang/IllegalArgumentException
     7: dup
     8: ldc           #9    // String units
    10: invokespecial #11  // Method IllegalArgumentException.<init>...
    13: athrow
    14: iload_0
    15: bipush        7
    17: imul
    18: ireturn
~~~

Tệp gốc không có `invokestatic demo/agent/Probe.hit:()V`. Có `athrow` cho input âm và `ireturn` cho input không âm.

### 13.2. `price(int)` ở bản đã biến đổi

~~~text
public static int price(int);
  Code:
     0: invokestatic  #31   // Method demo/agent/Probe.hit:()V
     3: iload_0
     4: ifge          17
     7: new           #7    // class java/lang/IllegalArgumentException
    10: dup
    11: ldc           #9    // String units
    13: invokespecial #11  // Method IllegalArgumentException.<init>...
    16: athrow
    17: iload_0
    18: bipush        7
    20: imul
    21: ireturn
~~~

**Evidence E1:** ở bản mới, instruction đầu `offset 0` là `INVOKESTATIC Probe.hit:()V`; code gốc vẫn hiện hữu sau đó. Các offsets phía sau thay đổi do instruction mới chiếm 3 bytes trong test.

**Không dùng constant-pool index `#31` hoặc offsets cụ thể làm invariant đa JDK/compiler**. Phần đáng tin hơn là opcode + symbolic owner + method name + descriptor và đúng vị trí. Với source/compiler khác, constant pool và vị trí branch có thể khác.

### 13.3. Đối chứng trong cùng class

`PriceService.label()` ở hai bản:

~~~text
public static java.lang.String label();
  Code:
     0: ldc           #14   // String SAFE
     2: areturn
~~~

Đây là **trích đoạn có cùng lệnh gốc và được kiểm chứng**. Mặc dù `PriceService.class` tổng thể đã thay đổi (do constant pool và `price`), method `label` **không được chèn helper**.

**Giới hạn:** `javap` xác nhận các instruction được hiển thị trong hai file, không tự kết luận mọi attribute/debug metadata giống nhau từng byte. Muốn chứng minh class unchanged ở một mức cấu trúc cụ thể phải định nghĩa mức so sánh, không nhầm **semantic equivalence** với **byte-for-byte equality**.

## 14. Bằng chứng độc lập: stdout của `VerifyEvidence`

Sau khi compile và chạy tool ở mục 10:

~~~text
original.price.probeCalls=0
original.price.firstIsProbe=false
original.label.probeCalls=0
transformed.price.probeCalls=1
transformed.price.firstIsProbe=true
transformed.label.probeCalls=0
verification=PASS
~~~

**Evidence E2:** chương trình riêng đã đọc original/transformed bytes, đếm đúng `INVOKESTATIC Probe.hit:()V` và assert:

- `price`: **0 → 1** probe calls;
- instruction đầu của `price`: **not probe → probe**;
- `label`: **0 → 0** probe calls;
- khi sai expected count hoặc vị trí, tool **ném `AssertionError`** thay vì in `PASS`.

**Đây không phải một “self-report” của agent.** Tool chạy **sau khi JVM ứng dụng đã kết thúc**, trên artifact files được tạo trong cùng thư mục thí nghiệm. Nó kiểm tra chính xác điều đã đặt trong H1/H2.

Tuy vậy, một tool parse thành công vẫn không chứng minh mọi đường chạy an toàn. Vì thế `-Xverify:all` và runtime behavior test là **hai tầng bằng chứng bổ sung**, không nên bỏ.

## 15. Kích thước, SHA-256 và tính toàn vẹn của artifact

Trong lần kiểm thử được mô tả:

| Artifact | Kích thước | SHA-256 |
| --- | ---: | --- |
| Original `PriceService.class` | 478 bytes | `5720381FD6619E0921094173C7C7D0718E7E8AECCEAD88154163025EC3791DF5` |
| Transformed `PriceService.class` | 519 bytes | `A9550ADD556B25665C10978C14FC93B4495BC4BB71D71232F98864AFB1198059` |

Hash được lấy **trực tiếp từ hai tệp đã kiểm thử** (JDK 24.0.2, đúng mã và build path ở đây). Hai hash khác nhau là bằng chứng bytes khác nhau, **không tự chứng minh class bytes hợp lệ** hay chỉ có một thay đổi dự kiến.

Đo lại trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 app-classes/demo/report/PriceService.class
Get-FileHash -Algorithm SHA256 transformed/demo/report/PriceService.class
Get-Item app-classes/demo/report/PriceService.class, transformed/demo/report/PriceService.class | Select-Object Name, Length
~~~

Đo lại trên Bash:

~~~bash
sha256sum app-classes/demo/report/PriceService.class \
  transformed/demo/report/PriceService.class
wc -c app-classes/demo/report/PriceService.class \
  transformed/demo/report/PriceService.class
~~~

Kết quả hash có thể khác khi compiler/build options/constant pool/source khác. **Không** đưa một hash cố định ở trên thành điều kiện PASS của mọi máy. Tiêu chí quan trọng hơn là **hai artifacts có provenance rõ**, class target ở bản đã transform có callsite mới chính xác và hành vi test đúng.

### 15.1. Vì sao phải giữ cả original lẫn transformed?

Nếu chỉ lưu tệp đã biến đổi, người review khó xác định instruction có phải đã có từ source hoặc từ một build khác. Giữ bản gốc cùng build và cùng test session cho phép `diff`:

- Trước: method `price` bắt đầu bằng `iload_0`.
- Sau: method `price` bắt đầu bằng `invokestatic Probe.hit`.
- Sau: `label` không có hook mới.
- Cùng: các phép thử output đã chọn vẫn đúng.

Một bằng chứng có thể truy ngược nguồn (source → javac output → transform output → verifier output → runtime output) đáng tin hơn screenshot một đoạn log thiếu provenance.

## 16. Bảng kết luận cho từng giả thuyết

| Giả thuyết | Dữ liệu hỗ trợ | Kết luận đúng phạm vi |
| --- | --- | --- |
| **H1** — một hook ở entry `price` | `javap` offset 0; verifier `0→1` và `firstIsProbe=true` | **PASS** trên classfile của build thử |
| **H2** — không lan sang `label` | `label.probeCalls=0` trước và sau; `label=SAFE` | **PASS** cho method đối chứng đã kiểm |
| **H3** — output/exception đã chọn được giữ | `price3=21`, `error=IllegalArgumentException`, `label=SAFE`, `control=10` ở cả hai JVM | **PASS** cho bộ input cụ thể |
| **H4** — hook thực thi hai lần | `Probe.hits=0` không agent, `2` khi có agent | **PASS** ở thứ tự lời gọi test |
| **Bytecode validity** | Treatment chạy với `-Xverify:all` không `VerifyError` | **PASS** cho class/JVM/đường load này |
| **Hiệu năng production** | Không có benchmark tải/latency hoặc phân phối mẫu | **NOT TESTED** |
| **An toàn mọi method/JVM** | Chỉ kiểm thử một class, một method, một runtime | **NOT TESTED** |

Không có lý do gọi toàn bộ kết luận là “một phương pháp luôn hoạt động trên mọi ứng dụng”. Kết luận chính xác hơn là **“bốn giả thuyết của thí nghiệm cụ thể được ủng hộ bởi nhiều loại bằng chứng, trong phạm vi cấu hình và dữ liệu được kiểm thử”**.

**Từ ngữ báo cáo:** có thể viết `PASS` cho một assertion có đầu vào/điều kiện/expected/actual rõ ràng. Không viết “đã chứng minh agent an toàn tuyệt đối” chỉ vì tất cả test hiện có đều pass.

## 17. Độ tin cậy: các tầng evidence không thay thế nhau

| Tầng | Bằng chứng | Lỗi vẫn có thể lọt qua |
| --- | --- | --- |
| **E0 — source review** | Grep/đọc source không có lời gọi helper gốc | Build khác source, class đã bị xử lý bởi tool khác |
| **E1 — transform output** | Mảng bytes mới, dump file, SHA khác | Bytecode có thể sai/không bao giờ được JVM áp dụng |
| **E2 — bytecode structure** | `javap` + `VerifyEvidence` assert instruction | Verifier độc lập chưa chứng minh semantics runtime |
| **E3 — JVM load/verification** | `-Xverify:all` chạy thành công | JVM không kiểm chứng correctness nghiệp vụ ở mọi input |
| **E4 — runtime behavior** | Output baseline/treatment và counter 0→2 | Chỉ vài input, không chứng minh concurrency/perf/long-run |
| **E5 — production assurance** | Soak/load/security/cross-loader/restart tests | Chưa có trong thí nghiệm này |

**Dùng nhiều tầng độc lập:** nếu transformer in “chèn xong”, đó là **E1 tự báo**. Nếu `VerifyEvidence` khác process xác nhận opcode và method, có thêm **E2**. Nếu JVM load thành công và chạy đúng output, có thêm **E3/E4**. Không cần một tầng duy nhất “chứng minh tất cả”.

Đừng coi hashes là E4: hash chỉ chứng minh content identity của artifacts đã ghi, không chứng minh chúng chạy đúng.

## 18. Giới hạn nội tại của thí nghiệm

### 18.1. Phạm vi phương thức và kiểu bytecode

Bài chỉ chọn một `public static int price(int)` có điều kiện và return, một explicit exception. Không kiểm thử:

- Constructors `<init>` và class initializers `<clinit>`;
- Methods `native`/`abstract` không có `Code`;
- Return `long`/`double`/`void`/reference;
- Methods có try/catch/finally phức tạp, synchronized, monitor enter/exit;
- Lambdas, bridge/synthetic methods, invokedynamic phức tạp;
- Interface default methods hoặc nhiều overload cùng tên;
- Method-level security/access ở named module.

Class-File API hỗ trợ thao tác rộng, nhưng chính **transform logic của thí nghiệm** chưa giải quyết những trường hợp này.

### 18.2. Mức tác động được quan sát

Bài chứng minh **entry probe** làm counter tăng, chưa đo:

- Thời gian elapsed/CPU;
- Phân loại return vs throw;
- Trace correlation/baggage;
- Memory allocations, GC pause;
- Event loss, batching, exporter retry;
- Tác động p95/p99 latency và throughput.

Thậm chí khi output nghiệp vụ giống baseline, method đã chạy thêm `AtomicInteger.incrementAndGet()`. Vì vậy **“không thay đổi những kết quả nghiệp vụ đã kiểm thử”** khác với **“không có tác động nào đến ứng dụng”**.

### 18.3. Ranh giới class loader, module và concurrency

Classpath ví dụ dùng một loader đơn giản. Trên application server/plugin framework:

- Class target có thể do custom class loader định nghĩa, không nhìn thấy `demo.agent.Probe`.
- Named module có thể thiếu read edge hoặc package export, dẫn đến `IllegalAccessError` hoặc vấn đề liên kết.
- Có thể có nhiều `PriceService` cùng binary name ở các loaders khác nhau; matcher chỉ theo tên **không đủ** để ràng buộc đúng một class identity.
- Nhiều class loads/transformers cùng lúc có thể tạo race và thứ tự biến đổi khác.
- Helper có thể có nhiều static counters nếu class được định nghĩa ở nhiều loaders.

Vì vậy thí nghiệm **không** chứng minh tính đúng của mọi class-loader/module-layer topology.

### 18.4. Thời điểm load, lỗi transformer, và rollback

Transformer đăng ký trong `premain` và chỉ can thiệp initial class definition; nếu class đã load, lần gọi `addTransformer(..., false)` không tự quay về quá khứ.

Nếu `transform` ném exception, Javadoc cho biết JVM vẫn có thể tiếp tục load không có thay đổi từ transformer này. Trong production, phải có error counter/diagnostics; không chỉ dựa vào exception để ép fail fast.

`removeTransformer` chỉ gỡ registration cho các biến đổi tương lai, **không tự xóa instruction đã được thêm vào class đã load**. Nếu cần rollback, phải thiết kế retransform/redefine có điều kiện hoặc restart JVM, đồng thời xác minh bytes/hành vi sau rollback.

### 18.5. Rủi ro khi helper thất bại

`Probe.hit()` chạy **trước** business instructions. Nếu helper tự ném `Error`, method `price` có thể không thực thi body. Hành vi “giữ output” mà bài kiểm thử được bảo đảm **chỉ khi helper vận hành bình thường** trong test.

Một agent production cần:

- Guard chống recursion và exclude agent/helper/logger/exporter;
- Chính sách fail-open khi telemetry lỗi, nhưng không nuốt mù quáng mọi JVM-critical `Error`;
- Bounded queue, sampling và backpressure rõ ràng;
- Không ghi file/log/network đồng bộ trong hot path;
- Kiểm tra báo cáo lỗi không chứa dữ liệu nhạy cảm;
- Kiểm thử cố tình làm helper lỗi để hiểu tác động lên original exception/return.

## 19. Cách viết phần “kết quả” để tránh thiên lệch báo cáo

Một lỗi thường gặp là bắt đầu thí nghiệm bằng kỳ vọng “phải thành công”, sau đó chỉ chọn những dòng log trông phù hợp. Quy trình tốt hơn:

1. Viết H1–H4 và tiêu chí FAIL **trước khi sửa agent**.
2. Giữ cùng source/build inputs, thay đúng một biến: bật/tắt `-javaagent`.
3. Chạy baseline trước để xác định behavior gốc.
4. Capture stdout, stderr, **exit code** và các artifacts, kể cả khi thất bại.
5. Dùng tool độc lập để assert opcode/owner/name/descriptor và vị trí.
6. Chỉ kết luận về những trường hợp có data; để “NOT TESTED” cho phạm vi ngoài.
7. Tái chạy trên clean build nếu thay compiler flags/agent code.
8. Nếu phát hiện mismatch, **không sửa bảng expected cho khớp actual** mà không giải thích nguyên nhân và lập phiên bản test mới.

**Trích dẫn evidence trong báo cáo:** thay vì “agent chạy tốt”, hãy viết “Trong build JDK 24.0.2, `VerifyEvidence` trả `transformed.price.probeCalls=1`, process exit code 0, JVM `-Xverify:all` chạy đúng `price3=21` và `probe.hits=2`.”

### 19.1. Các trạng thái báo cáo đề xuất

| Trạng thái | Khi nào dùng |
| --- | --- |
| `PASS` | Phép thử có expected rõ, đã chạy, exit code và actual đúng |
| `FAIL` | Đã chạy nhưng assertion sai hoặc JVM không hoàn tất theo hợp đồng |
| `BLOCKED` | Thiếu JDK/tool/permission/library khiến chưa thể chạy |
| `INCONCLUSIVE` | Có dữ liệu nhưng không phân biệt được nguyên nhân hoặc evidence thiếu |
| `NOT TESTED` | Chưa từng có phép thử cho phạm vi đó |

Không dùng `SKIPPED` như synonym của `PASS`; skipping là **không thực hiện phép thử**, không nói hệ thống đã vượt qua.

## 20. Mẫu báo cáo thí nghiệm có thể tái sử dụng

Trong công việc thực tế, một báo cáo nên có các mục sau (tùy quy mô rút gọn):

~~~markdown
# Báo cáo Java Agent — <mô tả tính năng>

## Phạm vi
- Class/method/descriptor/loader/module được chọn
- Phiên bản JVM/JDK, flags, hệ điều hành, revision
- Hành vi mong đợi / những hành vi ngoài phạm vi

## Giả thuyết
| ID | Dự đoán | Điều kiện PASS | Điều kiện FAIL |

## Thiết kế kiểm thử
- Baseline, treatment, đối chứng
- Mẫu input (normal/throw/boundary)
- Cách thu stdout/stderr/exit code/bytes
- Các biến được giữ cố định

## Bằng chứng
- E1: source revision và compile logs
- E2: original vs transformed class bytes, SHA-256
- E3: javap diff và chương trình assert opcode
- E4: JVM verifier + runtime stdout
- E5: tải/concurrency/security tests nếu có

## Kết quả
| H | Expected | Actual | Evidence ID | PASS/FAIL |

## Giới hạn và rủi ro
- JVM/version/loader/module/performance/coverage
- Failures còn chưa được thử
- Các kết luận không được phép suy ra

## Hành động tiếp theo
- Tests bổ sung, owner, acceptance criteria
~~~

Đây là **template Markdown**, các trường trong dấu `<...>` là tên trường cho người lập báo cáo thay bằng thông tin thật, **không phải một sản phẩm đã được chạy**. Đừng chèn template chưa điền vào một báo cáo cuối cùng và tuyên bố đã hoàn tất.

## 21. Báo cáo mẫu đã điền từ thí nghiệm thực tế

### Phạm vi và giả thuyết

**Đối tượng:** `PriceService.price(int)`, chỉ biến đổi tại initial-load trên JDK 24. **Kiểu thay đổi:** thêm một `INVOKESTATIC Probe.hit:()V` tại method entry. **Đối chứng:** `PriceService.label` và `ControlService.twice`. **Giả thuyết:** H1–H4 tại mục 3.

**Build:** `javac --release 24` trên Zulu/OpenJDK 24.0.2; agent được nạp bằng `-javaagent:report-agent.jar`; JVM verifier bật `-Xverify:all`. Không dùng ASM/Byte Buddy.

### Tóm tắt evidence gắn với yêu cầu

| Evidence ID | Bằng chứng thu từ đâu | Quan sát |
| --- | --- | --- |
| **E-B0** | Baseline Java stdout | `price3=21`, `error=IllegalArgumentException`, controls bình thường, `probe.hits=0` |
| **E-T1** | Treatment Java stdout | Cùng outputs nghiệp vụ, `probe.hits=2`, agent callback đúng class |
| **E-BC1** | `javap -c -p` bản gốc | `price` bắt đầu bằng `iload_0`; không có helper call |
| **E-BC2** | `javap -c -p` bản mới | `price` bắt đầu bằng `invokestatic Probe.hit:()V` |
| **E-IV1** | `VerifyEvidence` | `price.probeCalls 0→1`, `label 0→0`, `verification=PASS` |
| **E-SHA** | `Get-FileHash -Algorithm SHA256` | Hai file gốc/mới có hashes khác nhau |
| **E-VM** | `-Xverify:all`, exit code 0 | JVM chấp nhận bytecode trong bài test |

### Quyết định

**H1 PASS, H2 PASS, H3 PASS, H4 PASS** trong phạm vi test trên. **Không kết luận** khả năng instrument mọi class loaders, không khẳng định production overhead, không có dữ liệu cho retransform/redefine, error handling của helper hoặc tải đa luồng.

**Bước tiếp theo hợp lý:** mở rộng test matrix cho nhiều loaders, overloads, method có try/catch, concurrent calls, helper failure, JDK khác, và đo overhead trên bản đã bỏ `Files.write`/log khỏi transform path.

Báo cáo mẫu minh họa cách gắn từng kết luận với **một nguồn evidence có thể kiểm chứng**, không lẫn thông tin từ code source, compiler, transformed bytes và runtime counters.

## 22. Những sai lầm dễ làm báo cáo “đẹp nhưng sai”

| Ngộ nhận trong báo cáo | Tại sao sai | Cách sửa |
| --- | --- | --- |
| “Thấy `premain` log nghĩa đã instrument” | Chỉ chứng minh khởi tạo agent | Kiểm chứng target transform + bytecode |
| “Transformer trả non-null ⇒ bytecode luôn hợp lệ” | JVM có thể reject hoặc lớp không chạy đúng | `-Xverify:all` + runtime tests |
| “Có `Probe` trong constant pool ⇒ method đã gọi” | Có thể chỉ là metadata/string | Duyệt `InvokeInstruction` đúng opcode/descriptor |
| “Hash khác ⇒ logic chỉ thay đúng một lệnh” | Hash không chỉ ra semantic diff | `javap`/Class-File API structural diff |
| “Không agent có `Probe` trên classpath thì vẫn instrument” | `-cp` không kích hoạt `premain` | So `-javaagent` và baseline |
| “Agent count 2 ⇒ hai request đều thành công” | Hook ở entry, không phân loại outcome | Giữ input/exception outcomes riêng |
| “`label=SAFE` ⇒ toàn class byte-for-byte unchanged” | Class chứa method đã sửa/constant pool khác | Chỉ kết luận method output/probes như test |
| “JVM verifier PASS ⇒ performance tốt” | Verifier kiểm cấu trúc, không benchmark | Load/latency/GC tests |
| “Một lần chạy không lỗi ⇒ mọi input đúng” | Không bao phủ boundary/concurrency | Test matrix và property-based tests |
| “Không thấy log lỗi ⇒ không có drop/exception” | Logger/exporter có thể bị tắt | Collect stderr, exit codes, counters |
| “Đối chứng âm nên không cần source/provenance” | Control cũng có thể bị build từ source khác | Giữ revision/hashes |
| “Đã test Java 24 ⇒ test Java 17” | API/package/bytecode khác phiên bản | Ghi đúng JDK version, không tự hạ yêu cầu |
| “Gỡ transformer xong là rollback bytes” | Lớp đã load vẫn mang biến đổi | Retransform/redefine có điều kiện hoặc restart |
| “Không có overhead vì output giống” | Extra hook/atomic op vẫn tốn chi phí | Benchmark có warmup và đối chứng |
| “Agent không bao giờ đụng class khác” | Chỉ thấy một callback trong test không bao trùm mọi JVM | Scope rõ, kiểm thử thêm và đặt matcher chặt |
| “Báo cáo chỉ cần ảnh chụp màn hình” | Khó grep, diff, verify version/hashes | Lưu artifacts dạng text/máy đọc được |

## 23. Checklist chất lượng trước khi công bố báo cáo

**Giả thuyết và phép thử**

- [ ] Có tên class, method và **descriptor** chính xác.
- [ ] H1–Hn có tiêu chí PASS/FAIL trước khi thực hiện.
- [ ] Baseline chỉ khác treatment ở yếu tố có chủ đích.
- [ ] Có control trong cùng class và class đối chứng khi phù hợp.
- [ ] Input bao phủ normal result và ít nhất một error path nếu liên quan.
- [ ] Không tự thay expected sau khi thấy actual mà không ghi lý do.

**Bằng chứng bytecode**

- [ ] Giữ original/transformed bytes của cùng build.
- [ ] Kiểm tra đúng opcode/owner/name/descriptor.
- [ ] Kiểm tra vị trí instruction và không tạo duplicate hook.
- [ ] Kiểm tra method không được chọn vẫn không có hook.
- [ ] `javap` và chương trình cấu trúc độc lập đưa kết quả phù hợp.
- [ ] Ghi SHA-256/size như thông tin provenance, không dùng hash thay cho semantic assertion.

**Kết quả chạy và môi trường**

- [ ] JDK/compiler, version, build flags, classpath/agent flags rõ ràng.
- [ ] JVM `-Xverify:all` chạy, ghi stderr và exit code.
- [ ] Baseline và treatment có stdout thực, không tự sửa thứ tự.
- [ ] Return value và exception type được kiểm tra ở cùng inputs.
- [ ] Lỗi helper/class loader/module được xem xét và báo nếu chưa thử.
- [ ] Nếu chưa chạy được, dùng `BLOCKED`/`NOT TESTED` thay vì `PASS`.

**Giới hạn và tính trung thực**

- [ ] Giới hạn về JDK, method kinds, retransform và class loaders rõ ràng.
- [ ] Không nhầm counts với durations hoặc end-to-end tracing.
- [ ] Không đánh đồng verify class với an toàn production.
- [ ] Chỉ công bố hiệu năng khi có benchmark đúng phương pháp.
- [ ] Nêu next tests có acceptance criteria cụ thể.
- [ ] Người khác có thể chạy lại từ source và lệnh đã mô tả.

## 24. Câu hỏi tự kiểm tra

1. Vì sao `agent.ready=true` không đủ để chứng minh đã chèn `Probe.hit()`?
2. Giả thuyết H1 có những điều kiện nào khiến nó bị bác bỏ?
3. Tại sao `PriceService.label()` là đối chứng âm hữu ích ngay trong class đã biến đổi?
4. Vì sao cần class `ControlService` riêng dù đã có `label()`?
5. Thí nghiệm đã giữ biến nào giống nhau giữa baseline và treatment?
6. Tại sao cần giữ **hai tệp class** nguyên bản/đã biến đổi thay vì chỉ một?
7. Lệnh `javap` cho biết điều gì mà stdout runtime một mình không chứng minh được?
8. Vì sao kiểm tra `INVOKESTATIC + owner + name + descriptor` tốt hơn tìm chuỗi `"Probe"`?
9. Vì sao `Verification=PASS` từ tool độc lập tăng độ tin cậy so với log do transformer in ra?
10. Hai SHA-256 khác nhau có chứng minh đã chèn đúng một instruction không?
11. Vì sao `probe.hits=2` không chứng minh cả hai lời gọi đều return?
12. Vì sao `error=IllegalArgumentException` không chứng minh exception object/stack trace giống nhau từng chi tiết?
13. `-Xverify:all` chứng minh điều gì và **không** chứng minh điều gì?
14. Vì sao phải báo rõ JDK 24 thay vì ghi “Java 17+” một cách chung chung?
15. Những rủi ro nào xuất hiện khi helper không resolve được từ custom class loader?
16. Vì sao constructor hoặc native method cần test/thiết kế khác `price(int)`?
17. Vì sao `removeTransformer` không phải “tắt mọi hook đã có”?
18. Trong báo cáo, trường hợp thiếu Java compiler cần dùng `BLOCKED` hay `PASS`?
19. Nếu helper tự ném một `Error`, giả thuyết H3 có còn đúng không?
20. Khi muốn tuyên bố “overhead dưới 2%”, cần thêm thiết kế thí nghiệm và dữ liệu nào?

**Kết luận:** Một báo cáo Java agent tốt phải chỉ rõ **giả thuyết có thể bác bỏ**, cung cấp **bằng chứng bytecode nguyên bản/đã biến đổi**, **kết quả runtime có baseline và đối chứng**, rồi **giới hạn kết luận**. Trong thí nghiệm được chạy trên JDK 24.0.2, agent chèn đúng một `INVOKESTATIC Probe.hit:()V` vào `PriceService.price(int)`, các output/exception đã kiểm giữ nguyên và helper count đổi từ 0 thành 2. `javap`, verifier độc lập và JVM `-Xverify:all` nhất quán. Kết quả đó ủng hộ H1–H4 **cho phạm vi thí nghiệm**, không tự biến một prototype thành agent production an toàn toàn diện.

### Tài liệu tham khảo chính thức

- [JDK 24 — ClassFileTransformer và transform contract](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JDK 24 — Instrumentation.addTransformer](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [JDK 24 — ClassFile: parse và transformClass](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [JDK 24 — ClassTransform.transformingMethodBodies](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html)
- [JDK 24 — CodeTransform / ClassFileTransform: atStart và with](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeTransform.html)
- [JDK 24 — InvokeInstruction / Opcode](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/instruction/InvokeInstruction.html)
- [JEP 484 — Class-File API chuẩn hóa trong JDK 24](https://openjdk.org/jeps/484)
