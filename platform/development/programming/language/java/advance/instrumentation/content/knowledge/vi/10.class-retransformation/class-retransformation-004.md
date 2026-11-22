# Dữ liệu ban đầu được lấy từ lần định nghĩa hoặc redefine gần nhất

Trong Java instrumentation, `Instrumentation.retransformClasses(...)` cho phép chạy lại quy trình biến đổi bytecode của một lớp **đã được JVM nạp**. Một điểm rất dễ hiểu sai là nguồn dữ liệu của lượt retransformation: JVM có lấy ngay bytecode đã cấy hook từ lượt retransform trước và thêm sửa đổi tiếp lên đó không?

**Không theo cách mặc định đó.** Theo Javadoc của `java.lang.instrument`, mỗi lượt retransform bắt đầu từ **dữ liệu class file của lần định nghĩa bằng `ClassLoader.defineClass` ban đầu hoặc lần `Instrumentation.redefineClasses` gần nhất** — trước những transformations ở lần load/redefine tương ứng. JVM tự tái sử dụng kết quả của những transformer không hỗ trợ retransform và gọi lại những transformer có hỗ trợ retransform. Nói cách khác, mốc khởi đầu phụ thuộc **define/redefine gần nhất**, không tự cập nhật sau mỗi lần retransform.

Cần thêm một điều kiện quan trọng: dữ liệu JVM dùng để khởi đầu **đại diện** cho bytes đã được truyền ở lần define/redefine, nhưng **không bắt buộc giống hệt về từng byte**. Constant pool có thể được sắp xếp lại, có thêm/bớt entries; một số attributes hoặc thứ tự methods có thể khác. Vì thế câu nói "lấy bytecode ban đầu" mô tả **mốc ngữ nghĩa và quy trình**, không cam kết một array giống file `.class` trên đĩa.

Bài thuộc nhóm **Retransformation** của Java Advance – instrumentation. Sau khi học, bạn có thể đọc đúng chuỗi define → retransform → redefine → retransform, phân biệt replay với callback mới, xử lý idempotence, thiết kế diagnostics, kiểm tra capability và tự chạy thí nghiệm Java 17+ có hai transformers A/B.

## 1. Phân biệt class definition, redefinition và retransformation

| Thao tác | API kích hoạt điển hình | Có class-file bytes mới do caller cung cấp? | Mốc của retransform sau đó |
| --- | --- | --- | --- |
| **Define** | `ClassLoader.defineClass` hoặc native tương ứng | Có, đây là bytes để định nghĩa class | Lần define đầu tiên, nếu chưa redefine |
| **Redefine** | `Instrumentation.redefineClasses(ClassDefinition...)` | **Có**, mỗi `ClassDefinition` chứa class và bytes thay thế | **Chuyển sang lần redefine thành công gần nhất** |
| **Retransform** | `Instrumentation.retransformClasses(Class<?>...)` | **Không**, caller truyền class objects, JVM tự lấy mốc | **Không thay mốc define/redefine** |

**Define:** JVM lần đầu định nghĩa class từ classfile bytes tương ứng. Các transformers được đăng ký trước đó có thể xử lý classfile bytes trong quá trình JVM chuẩn bị định nghĩa. Những bytes đầu vào của define là mốc khởi đầu logic trước mọi transformation.

**Redefine:** caller truyền classfile mới, ví dụ một phiên bản class đã biên dịch lại với body method khác nhưng cùng schema được hỗ trợ. Trong lần redefine, các transformers có thể được gọi; nếu thao tác thành công, định nghĩa hiệu lực được cập nhật. Mốc cho những lượt retransform tiếp theo là **input của redefine mới nhất**, trước các transforms tại thời điểm ấy.

**Retransform:** caller không truyền bytes mới cho JVM. Thay vì sửa chồng trực tiếp lên kết quả retransform trước, JVM tái chạy quy trình từ mốc define/redefine đã lưu với quy tắc replay. Một transformer có thể thay đổi output tùy cấu hình, nhưng đây không phải một lần redefine theo nghĩa cung cấp classfile mới.

Ví dụ tên lớp `Target`, version method `V1` ở D0 và `V2` ở D1:

~~~text
LOAD Target V1  -> mốc D0
RETRANSFORM     -> bắt đầu từ D0, không tự thành mốc mới
REDEFINE V2     -> mốc chuyển thành D1 nếu thành công
RETRANSFORM     -> bắt đầu từ D1, không quay về D0
~~~

Nếu chưa từng có redefine, kể cả lần retransform thứ mười vẫn khởi đầu từ mốc define đầu tiên theo contract; không phải luôn dùng bytecode của lần retransform thứ chín.

## 2. Hai nhóm transformers tạo nên quy tắc replay

Khi đăng ký:

~~~java
instrumentation.addTransformer(transformerA, false);
instrumentation.addTransformer(transformerB, true);
~~~

tham số `canRetransform` phân chia nhóm:

- **Retransformation-incapable** (`false`): callback `transform` được gọi cho những lần load/redefine phù hợp, **không được gọi lại ở retransform**. Tuy vậy, **kết quả cũ** của transformer từ lần load/redefine gần nhất **được JVM tự sử dụng lại** trong pipeline retransform. Không gọi callback mới **không đồng nghĩa biến đổi đã mất**.
- **Retransformation-capable** (`true`): callback được gọi khi load, redefine và **retransform** phù hợp. Nó có thể xây bytecode mới khi cấu hình agent thay đổi, phải giữ legal redefinition semantics và không tự nhân đôi hook.

| Sự kiện | A (`false`) | B (`true`) |
| --- | --- | --- |
| Lần đầu load class | A.transform được gọi | B.transform được gọi |
| Redefine class | A.transform được gọi | B.transform được gọi |
| Retransform class | **Không gọi A.transform**; JVM tái dùng kết quả của A từ load/redefine | **Gọi B.transform lần nữa** |
| Đổi config rồi retransform | A không tự tính lại kết quả | B có thể tính theo config mới |
| Redefine rồi retransform | Replay kết quả của A ở **lần redefine mới** | B nhận pipeline từ mốc redefine mới |

Bảng là trường hợp các transformers thực sự quan sát class đang xét. Nếu một transformer chỉ đăng ký sau khi class đã load, hoặc class của dependency bị loại trừ, quá trình thực tế cần kiểm tra theo contract. Không suy ra callback bắt buộc cho tất cả class của JVM.

### 2.1. Minh họa bằng các mốc D0 và D1

Đặt:

- `D0` = dữ liệu ban đầu từ lần define.
- `A0` = output logic của A áp trên D0.
- `B0` = output logic của B áp trên A0.
- `D1` = dữ liệu do một lần redefine thành công cung cấp.
- `A1` = output logic của A khi redefine từ D1.
- `B1` = output logic của B khi redefine từ A1.

~~~text
LOAD:
   D0 -> gọi A -> A0 -> gọi B -> B0 -> class hiệu lực

RETRANSFORM chưa redefine:
   D0 -> replay A0 [không gọi A] -> gọi B lại -> class hiệu lực mới

REDEFINE:
   D1 -> gọi A -> A1 -> gọi B -> B1 -> class hiệu lực mới

RETRANSFORM sau redefine:
   D1 -> replay A1 [không gọi A] -> gọi B lại -> class hiệu lực mới
~~~

Chú ý: **B không nhất thiết nhận bytes thuần D0 hoặc D1**. Vì A đứng trước trong pipeline, B có thể nhận bytes đã chứa sửa đổi của A. Vì vậy hai khẳng định tuyệt đối đều sai: "B luôn nhìn thấy file gốc nguyên bản" và "B luôn nhìn thấy mọi biến đổi từ lần retransform trước".

### 2.2. Thứ tự transformers

`ClassFileTransformer` quy định bốn nhóm, theo thứ tự:

1. Java transformers retransformation-incapable.
2. Native transformers retransformation-incapable.
3. Java transformers retransformation-capable.
4. Native transformers retransformation-capable.

Trong mỗi nhóm, thứ tự dựa trên thứ tự registration. Ở lượt retransform, các nhóm non-capable không được gọi lại; kết quả từ lần load/redefine tương ứng được replay. Ở tầng capable, callback mới xử lý bytes đang có sau các tầng trước.

Nếu một transformer trả `null`, nó không sửa bytes ở **tầng của mình**. `null` của B không tự xoá biến đổi đã được A replay. Nếu transformer trả một byte array mới, JVM đưa kết quả đó vào pipeline cho transformer kế tiếp; **không sửa trực tiếp buffer đầu vào** do JVM đưa cho callback.

## 3. "Ban đầu" không đồng nghĩa "bản copy của file trên đĩa"

Trong tài liệu `Instrumentation.retransformClasses`, initial class-file bytes biểu diễn dữ liệu từng truyền vào `ClassLoader.defineClass` hoặc `Instrumentation.redefineClasses` trước transformations. Nhưng JVM không cam kết cùng byte array hoặc cùng cấu trúc byte-for-byte:

- Constant pool có thể có nhiều hoặc ít entries hơn.
- Entries có thể được sắp xếp theo thứ tự khác.
- Index constant pool trong method bytecode vẫn phải tương ứng với cách diễn giải hợp lệ.
- Một số attributes có thể không hiện diện.
- Những thứ tự không có ý nghĩa về semantics, ví dụ thứ tự methods, có thể thay đổi.

Do đó:

~~~text
Original on disk:    SHA256(D0) = abc...
Bytes observed:      SHA256(observed) = def...
Semantic baseline:   vẫn có thể tương ứng với D0
~~~

Đây là **minh họa giả định**, không phải checksum có thật. Chỉ so hash rồi kết luận JVM đã lấy sai baseline là không chính xác. Cũng không nên đọc `Target.class` bằng `getResourceAsStream` và khẳng định mảng đó chính là bytecode hiện đang thực thi sau redefine/retransform: resource trên classpath có thể vẫn là file V1.

**Khuyến nghị:** dùng trình đọc classfile/bytecode có hiểu constant pool, method descriptors, attributes và branch offsets; khi cần idempotence, kiểm tra instruction patterns hoặc markers đáng tin, không chỉ so một checksum tuyệt đối. Nếu diagnostic lưu classfile bytes, phải có memory bound và ràng buộc bảo mật vì class bytes có thể chứa strings hoặc thông tin cần bảo vệ.

## 4. Khi redefine xuất hiện, mốc được cập nhật thế nào?

Ví dụ một ứng dụng đã load `Target.version() = "V1"`, sau đó công cụ làm:

~~~java
instrumentation.redefineClasses(
        new ClassDefinition(Target.class, version2ClassBytes));
~~~

**Mảnh này chỉ minh hoạ**: phải có biến `instrumentation`, `Target` và `version2ClassBytes` phù hợp, không phải chương trình độc lập. Nếu lời gọi thành công, file class phiên bản V2 được JVM dùng làm **input của lần redefine**, rồi các transformers của pipeline xử lý nó. Mốc cho retransform kế tiếp là **dữ liệu của redefine V2**, không phải V1.

Nếu redefine thất bại, không tự cập nhật sổ trạng thái của agent sang V2. `redefineClasses` có thể thất bại do class không modifiable, bytecode không hợp lệ, class name mismatch hoặc thay đổi schema không được JVM hỗ trợ. Tài liệu mô tả lỗi khiến không class nào trong tập được redefined thành công. Phải xem đúng loại lỗi thay vì coi việc đọc file V2 thành công là đã cài đặt V2.

Một lớp có thể được redefine nhiều lần:

~~~text
Define D0 -> Retransform -> Redefine D1 -> Retransform
          -> Redefine D2 -> Retransform -> Retransform
~~~

Hai lần retransform cuối dựa trên D2; không tự quay về D0 hoặc D1 và không tích lũy bắt buộc các outputs từ retransform trước. Replay của transformer non-capable lấy kết quả phù hợp với redefine D2.

## 5. Thí nghiệm đầy đủ bằng Java 17+: A không capable, B capable

Ta sẽ làm một thí nghiệm trong **một JVM**, sử dụng agent khởi động qua `-javaagent`. Có hai bản của lớp `Target`:

- `Target V1`: `version()` trả chuỗi `"V1"`.
- `Target V2`: `version()` trả `"V2"`, giữ nguyên tên class và chữ ký method.

Agent đăng ký hai transformers **A** và **B**, cả hai chỉ quan sát và trả `null`. Nhờ vậy, output thể hiện rõ **thứ tự callback** và **phiên bản định nghĩa hiệu lực**, không bị biến đổi bytecode của một third-party library che khuất.

Ví dụ đã được biên dịch và chạy thực tế bằng OpenJDK HotSpot 21 với `javac --release 17`. JVM cần hỗ trợ `redefineClasses` và `retransformClasses`; những runtime không có capability này sẽ không chạy demo đúng như output. Lệnh dùng JDK 17+ có đủ các công cụ `javac` và `jar`.

### 5.1. Cấu trúc source files

~~~text
demo/
  Agent.java
  Main.java
  Target.java
  MANIFEST.MF
  v2/
    Target.java
~~~

Hai file có cùng tên `Target.java` ở **hai thư mục khác nhau**; chúng được biên dịch thành hai class files ở hai output directories riêng. Không đặt `v2out` trên runtime classpath vì V2 chỉ được truyền qua `ClassDefinition` khi redefine.

### 5.2. File `Target.java` — bản V1

~~~java
public final class Target {
    public static String version() { return "V1"; }
}
~~~

### 5.3. File `v2/Target.java` — bản V2

~~~java
public final class Target {
    public static String version() { return "V2"; }
}
~~~

Hai bản có cùng binary name `Target` và cùng method descriptor `()Ljava/lang/String;`. Chúng chỉ khác method body, nên phù hợp với phạm vi redefinition được demo hỗ trợ.

### 5.4. File `Agent.java`

~~~java
import java.io.IOException;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class Agent implements ClassFileTransformer {
    private static Instrumentation instrumentation;
    private final String id;

    private Agent(String id) { this.id = id; }

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRedefineClassesSupported()
                || !inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("JVM does not support demo capabilities");
        }
        inst.addTransformer(new Agent("A"), false);
        inst.addTransformer(new Agent("B"), true);
    }

    @Override
    public byte[] transform(ClassLoader loader, String name,
            Class<?> redefining, ProtectionDomain domain, byte[] bytes) {
        if ("Target".equals(name)) {
            System.out.println(
                    "TRANSFORM=" + id + ",existing=" + (redefining != null));
        }
        return null;
    }

    public static void redefine(Class<?> target, Path newClass)
            throws IOException, ClassNotFoundException,
                   UnmodifiableClassException {
        byte[] bytes = Files.readAllBytes(newClass);
        instrumentation.redefineClasses(new ClassDefinition(target, bytes));
    }

    public static void retransform(Class<?> target)
            throws UnmodifiableClassException {
        instrumentation.retransformClasses(target);
    }
}
~~~

Giải thích:

1. `premain` nhận `Instrumentation` từ JVM, kiểm tra cả hai khả năng rồi đăng ký A và B. Agent không nhắc tới `Target.class` trong `premain`, nhờ vậy không chủ động load Target trước khi đăng ký.
2. A được đăng ký với `false`, B với `true`. Cả hai chỉ in khi `name` đúng `Target`; trong default package, tên internal là `Target`.
3. `redefining` chính là `classBeingRedefined` của overload năm tham số. Nó bằng `null` khi định nghĩa mới và khác null khi redefine **hoặc** retransform. **Không thể phân biệt chính xác redefine với retransform chỉ bằng việc kiểm tra null.**
4. `return null` thể hiện transformer không thay bytecode. Các thông điệp in ra chỉ dành cho việc học; khi viết transformer production, tránh `println`/logging và network đồng bộ trong callback class loading.
5. `redefine(...)` đọc file V2 và truyền mảng byte qua `new ClassDefinition(target, bytes)`. `retransform(...)` không nhận bytes mới, chỉ yêu cầu JVM chạy lại quá trình transformer.
6. Chức năng `Instrumentation` được cung cấp cho agent khi startup, không phải object do ứng dụng tự `new`.

### 5.5. File `Main.java`

~~~java
import java.nio.file.Path;

public final class Main {
    public static void main(String[] args) throws Exception {
        System.out.println("BEFORE=" + Target.version());

        System.out.println("STEP=REDEFINE");
        Agent.redefine(Target.class, Path.of("v2out/Target.class"));
        System.out.println("AFTER_REDEFINE=" + Target.version());

        System.out.println("STEP=RETRANSFORM");
        Agent.retransform(Target.class);
        System.out.println("AFTER_RETRANSFORM=" + Target.version());
    }
}
~~~

Để đơn giản, `Main` tham chiếu trực tiếp `Agent` trong cùng application classpath; trong sản phẩm thực, thông thường agent độc lập với ứng dụng. Từ source `Main` có thể thấy chính xác vị trí yêu cầu redefine/retransform và chỗ đọc kết quả.

### 5.6. File `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: Agent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

~~~

Đây là manifest startup agent, dùng `Premain-Class`. Hai dòng `Can-...` là yêu cầu capability, **không tự đảm bảo** rằng JVM nào cũng hỗ trợ. Giữ newline và dòng trống cuối manifest; `jar --manifest` đưa các trường này vào `META-INF/MANIFEST.MF`.

### 5.7. Biên dịch, đóng gói và chạy

Từ thư mục `demo/` chứa các file:

~~~bash
javac --release 17 -d out Agent.java Main.java Target.java
javac --release 17 -d v2out v2/Target.java
jar --create --file demo-agent.jar --manifest MANIFEST.MF -C out Agent.class
java -javaagent:demo-agent.jar -cp out Main
~~~

- `out` chứa `Agent.class`, `Main.class` và `Target.class` phiên bản V1.
- `v2out` chứa `Target.class` phiên bản V2 và **không** nằm trên `-cp`.
- Agent JAR chứa `Agent.class` và manifest đã khai báo capability.
- Lệnh `java` bật startup agent trước khi gọi `Main.main`.

**Standard output đã được biên dịch và đối chiếu chính xác trên OpenJDK HotSpot 21:**

~~~text
TRANSFORM=A,existing=false
TRANSFORM=B,existing=false
BEFORE=V1
STEP=REDEFINE
TRANSFORM=A,existing=true
TRANSFORM=B,existing=true
AFTER_REDEFINE=V2
STEP=RETRANSFORM
TRANSFORM=B,existing=true
AFTER_RETRANSFORM=V2
~~~

Kết quả minh họa ba giai đoạn:

- Khi **load**, cả A và B được gọi với `existing=false`, method trả `V1`.
- Khi **redefine**, cả A và B được gọi lại với `existing=true`, method đổi sang `V2`.
- Khi **retransform**, **chỉ B được gọi**, còn A không xuất hiện trong log callback; method vẫn trả `V2`.

Đây là bằng chứng thực nghiệm về số lần callback và phiên bản method được gọi. Nó **không** khẳng định bytes của B ở retransform giống 100% file `v2out/Target.class`; chương trình không đo byte array, và hợp đồng cũng không bảo đảm byte equality.

## 6. Ý nghĩa chính xác của output A/B

### 6.1. Load: cả hai callback hoạt động

~~~text
TRANSFORM=A,existing=false
TRANSFORM=B,existing=false
BEFORE=V1
~~~

Cả hai transformers được đăng ký trước lúc Target load. Chúng đều nhận callback; vì cùng trả `null`, JVM dùng code V1.

### 6.2. Redefine: cả A và B được gọi

~~~text
STEP=REDEFINE
TRANSFORM=A,existing=true
TRANSFORM=B,existing=true
AFTER_REDEFINE=V2
~~~

Redefine không chỉ chạy B. A non-capable vẫn được gọi vì đây là **redefine**, không phải **retransform**. Nó xử lý bytes được đưa vào qua `ClassDefinition`. Sau lần redefine thành công, method hiện dùng body V2.

### 6.3. Retransform: A được replay mà không callback

~~~text
STEP=RETRANSFORM
TRANSFORM=B,existing=true
AFTER_RETRANSFORM=V2
~~~

Không có dòng `TRANSFORM=A` nghĩa là A **không nhận callback mới**; JVM tái sử dụng kết quả của A từ redefine gần nhất. B được gọi mới; nó trả `null`. Mốc vẫn là V2, không quay về V1. Đừng hiểu thành "A bị loại khỏi pipeline" hoặc "A đã bị removeTransformer".

Trong demo cả A/B là no-op nên không chứng minh một mẫu bytecode patch cụ thể được replay. Nhưng callback pattern và behavior sau redefine đúng như Java Instrumentation API mô tả. Nếu bổ sung một transformer A chèn hook thật, phải dùng trình sửa bytecode có verifier và test riêng để xác nhận replay, không suy từ print-only demo rằng đã sửa bytes.

## 7. Các phép biến đổi không tích lũy đơn giản qua mỗi retransform

Giả sử một transformer capable B thêm một lệnh gọi helper vào method:

~~~text
B(input) -> output có thêm một helper call
~~~

Một thiết kế sai là lưu lại output của B, đến lượt retransform kế tiếp lại nạp output ấy vào bộ sửa và **thêm tiếp** helper call khác. Hợp đồng JVM không buộc bạn phải tự làm vậy. Thông thường B được gọi lại trên một pipeline được dựng từ **mốc define/redefine gần nhất**, cộng replay từ các tầng non-capable trước B.

Tuy nhiên, **không được kết luận rằng mọi input tới B đều sạch hook**: bytecode D1 của lần redefine có thể đã chứa hook, A non-capable có thể chèn hook và được replay, hoặc các transformers trong pipeline trước B đã sửa code. Vì thế idempotence cần xét **toàn bộ pipeline**, không chỉ lời giải thích về mốc gốc.

Cách làm đúng hơn cho transformer sửa bytecode thật:

1. Lọc đúng tên internal class, loader/module, method name và descriptor.
2. Nhận diện lời gọi helper đã tồn tại bằng instruction pattern hoặc marker đáng tin.
3. Exclude chính helper/exporter/agent code để tránh vòng gọi.
4. Với cùng input logic và cấu hình, kết quả nên xác định và không thêm hook trùng ngoài ý muốn.
5. Không cache raw bytes của lần retransform trước rồi tự dùng làm mốc mặc định cho lần sau.
6. Khi redefine D1 thành công, cập nhật kỳ vọng về phiên bản định nghĩa và chạy lại bộ test.
7. Không chỉ dùng `Arrays.equals` hoặc CRC của `classfileBuffer` để kết luận class đã/ chưa instrument.

Nếu cần tháo hook của capable transformer, kết quả mong muốn phải được xây dựa trên contract của pipeline hiện có. `return null` của B **không xoá** sửa đổi của A đã được replay. Tương tự, gỡ B khỏi danh sách transformers có thể ảnh hưởng lần retransform sau, nhưng không có nghĩa mọi active stack frame đang chạy sẽ ngay lập tức đổi bytecode.

## 8. Khác biệt giữa binary bytes và behavior

Một agent có thể cần kiểm tra classfile checksum để xác định artifact được build. Tuy nhiên, trong retransformation:

~~~text
Mốc ngữ nghĩa D1: định nghĩa đưa vào lần redefine gần nhất
Byte array JVM tái cung cấp: có thể khác trình tự constant pool/attributes
Behavior mới: còn phụ thuộc replay A và việc B biến đổi hay no-op
~~~

Cả ba là **ba khái niệm khác nhau**.

Chỉ vì `sha256(bytesFromTransform) != sha256(fileFromBuild)` không chứng minh JVM dùng sai định nghĩa. Ngược lại, file gốc có cùng hash cũng **không chứng minh** transformer B đã trả output đúng hoặc business behavior không bị thay đổi.

Để debug phải giữ đồng thời: phiên bản build D0/D1, nguồn sự kiện define/redefine/retransform, capability của transformers, thứ tự nhóm, log lỗi transform và kết quả chạy method ở các input đã chọn. Nếu cần khôi phục bytecode dưới dạng artifact, công cụ phải mô tả nó là bytes **tại điểm quan sát trong pipeline**, không gọi bừa là "file .class gốc chính xác".

## 9. Giới hạn của redefine/retransform và lỗi thường gặp

### 9.1. Capability và manifest

Retransformation là khả năng **tùy chọn** của JVM. Agent cần khai báo `Can-Retransform-Classes: true` trong manifest, JVM cần hỗ trợ, và class cụ thể phải modifiable. Tương tự, redefine cần `Can-Redefine-Classes: true` và khả năng phù hợp. Nên kiểm tra:

~~~java
if (!inst.isRetransformClassesSupported()) {
    // Không thể gọi retransformClasses trong cấu hình này.
}
if (!inst.isRedefineClassesSupported()) {
    // Không thể gọi redefineClasses trong cấu hình này.
}
if (!inst.isModifiableClass(targetClass)) {
    // Không thể thay định nghĩa class đích.
}
~~~

Đoạn trên là **snippet minh họa trong method đã có `inst` và `targetClass`**, không phải source độc lập. `isModifiableClass` không tự thay kiểm tra capability toàn JVM. Array classes và primitive types không modifiable theo API này.

Nếu `addTransformer(transformer, true)` được gọi trong JVM không hỗ trợ, có thể gặp `UnsupportedOperationException`. Nếu class không modifiable, `retransformClasses` có thể ném `UnmodifiableClassException`. Bytecode thay thế không hợp lệ có thể gây `ClassFormatError`, `UnsupportedClassVersionError`, `LinkageError` hoặc các lỗi khác theo nguyên nhân.

### 9.2. Không tùy tiện đổi schema

Đối với redefinition/retransformation theo những giới hạn JVM thường áp dụng, không được thay đổi tùy ý tên class, thêm/xóa fields hoặc methods, thay chữ ký hay inheritance. Biến đổi thân method mà vẫn giữ schema là một điểm khởi đầu thực tế. Demo V1/V2 dùng đúng kiểu thay đổi ấy.

Nếu redefine thất bại, API không cài được định nghĩa mới cho tập classes trong yêu cầu đó. Không lưu D1 thành "last successful redefine" chỉ vì đã gửi bytes đến JVM; phải ghi nhận thành công sau khi method trả bình thường.

### 9.3. Static state, object instances, active stack frames

Javadoc nêu rằng retransform/redefine không tự chạy lại class initializer và không làm static variables reset. Object instances đang sống cũng không tự biến thành objects mới. Nếu method đang có **active stack frames** ở thời điểm đổi, những frames ấy tiếp tục chạy bytecode cũ; các lời gọi mới dùng phiên bản method mới.

Do vậy, ngay cả khi method `Target.version()` mới đã trả V2, một request dài đang ở giữa một phiên bản method cũ có thể tiếp tục theo code cũ. Không quy kết ngay rằng retransform thất bại chỉ dựa vào stack trace hoặc trạng thái của một request đang chạy.

### 9.4. Callback lỗi không phải luôn chặn toàn pipeline

Một `ClassFileTransformer` ném exception không được xử lý thường có hiệu ứng như `return null` đối với biến đổi ở tầng ấy: các transformer sau vẫn có thể được gọi và JVM tiếp tục thử thao tác load/redefine/retransform. Vì vậy đừng dùng việc ném exception trong callback làm cơ chế đảm bảo fail-closed cho một yêu cầu bảo mật. Hãy thiết kế chiến lược an toàn và ghi nhận lỗi riêng, tránh xuất log phức tạp trong class-loading callback.

## 10. Bảng chẩn đoán theo triệu chứng

| Triệu chứng | Diễn giải có thể đúng | Bước tiếp theo |
| --- | --- | --- |
| Sau retransform, A không in nữa | A là non-capable và được replay | Xem flag lúc đăng ký, không vội kết luận hook A mất |
| Sau retransform, B vẫn in | B là capable | Kiểm tra B nhận input sau các tầng nào |
| Redefine sang V2 rồi retransform vẫn trả V2 | Mốc đã chuyển sang redefine mới nhất | Kiểm tra có transformer nào chủ động thay method không |
| Redefine sang V2 nhưng retransform lại về V1 | Có khả năng agent/transformer đang patch theo cache, stale config hoặc thay method | Truy tìm pipeline và test output, đừng mặc định do quy tắc baseline của JVM |
| Bytes retransform khác bytes của JAR | JVM được phép thay đổi constant pool/attributes | Parse cấu trúc; đừng kiểm tra bit-for-bit mù quáng |
| Callback có `classBeingRedefined != null` | Có thể là redefine **hoặc** retransform | Đối chiếu caller/phase, không phân loại chỉ bằng null |
| Class không thể retransform | Capability hoặc class không modifiable | Kiểm tra manifest + `is...Supported` + `isModifiableClass` |
| Cùng hook xuất hiện hai lần | Có thể patch trùng ở pipeline, redefine đã chứa hook, hoặc thiếu idempotence | Xem instruction pattern, thứ tự groups và source D1 |
| Lớp V2 trả kết quả sai | Helper/transformer sửa sai behavior, hoặc V2 đã khác logic | So sánh behavioral tests và bytecode methods |
| Một thread tiếp tục chạy code V1 | Active frame cũ còn hoạt động | Kiểm tra invocation mới sau điểm cập nhật |
| Gỡ B nhưng output chưa đổi ngay | Có thể chưa có retransform mới hoặc active frames vẫn cũ | Kiểm tra lifecycle và thời điểm thay định nghĩa |

Nếu phải thu dữ liệu từ trong callback, dùng counter/buffer hữu hạn, tránh ghi console/ghi network đồng bộ và không giữ mảng `classfileBuffer` lớn trong cache vô hạn. Demo in log trực tiếp chỉ để nhìn thứ tự sự kiện; không mang nguyên cách này sang production.

## 11. Thực hành thêm để phân biệt các mốc

### Bài thử A: retransform hai lần, không redefine

Sửa `Main` trong thư mục thử nghiệm để gọi `Agent.retransform(Target.class)` hai lần trước redefine. Quan sát mỗi lần chỉ có callback của B; version vẫn V1. Đây là bằng chứng rằng số lần callback A không tăng theo số yêu cầu retransform.

### Bài thử B: redefine lần hai

Tạo một thư mục `v3/` chứa `Target.java` với cùng schema và `version()` trả V3; biên dịch ra `v3out` rồi gọi `Agent.redefine(Target.class, Path.of("v3out/Target.class"))`. Sau đó retransform. Nếu redefine hợp lệ và hai transformers no-op, version phải là V3, vì đây là mốc redefine mới nhất. Không cần đổi tên class hoặc thêm fields để thử.

### Bài thử C: B thay đổi cấu hình

Tạo B capable có một config flag thay đổi giữa hai lần retransform và sửa bytecode theo flag. Chỉ áp dụng khi đã có bytecode toolkit/API phù hợp và test verifier. So sánh bytes/output ở hai cấu hình; B phải tái tạo phép biến đổi từ pipeline thích hợp, không chồng thêm tuỳ tiện lên output cũ.

### Bài thử D: A thật sự sửa bytes

Thay A no-op bằng một transformer non-capable có chèn hook hợp lệ. Khi retransform, kiểm tra A không được callback lại nhưng hook của A vẫn có hiệu lực. Đây là thử nghiệm nâng cao; demo hiện tại **không tự chứng minh** nó bằng bytecode, mà chỉ quan sát đúng nhánh replay theo hợp đồng Javadoc.

### Bài thử E: hash không trùng

Dùng parser để so sánh method body và constant-pool references giữa file nguồn và bytes mà callback B được nhận. Nếu hash khác, hãy kiểm tra sự khác biệt cấu trúc trước khi kết luận JVM đã lấy một định nghĩa cũ/sai.

## 12. Các nhầm lẫn cần tránh

1. **"Retransform luôn tiếp tục từ output retransform trước."** Không phải hợp đồng API. Nó khởi đầu từ define/redefine gần nhất, replay non-capable và chạy capable.
2. **"Mốc luôn là file class đã nạp lần đầu."** Sai khi có redefine thành công.
3. **"Non-capable không chạy nên hook của nó bị gỡ."** Sai: kết quả trước đó được replay.
4. **"Capable luôn nhận file class gốc sạch."** Sai khi có non-capable đứng trước hoặc redefine input đã có hook.
5. **"Bytes phải trùng chính xác với file JAR."** Không: constant pool và một số attributes có thể khác.
6. **"classBeingRedefined khác null là chắc chắn redefine."** Không: retransform cũng có giá trị này.
7. **"Redefine chỉ gọi capable transformers."** Sai: A và B đều được gọi theo contract khi redefine.
8. **"return null của B xóa mọi biến đổi trước đó."** Sai: nó là no-op ở tầng B.
9. **"Một lần retransform thành công tạo mốc mới."** Sai: mốc là define hoặc redefine gần nhất.
10. **"Nạp JAR agent là chắc chắn có capability."** Sai: manifest và JVM phải cùng hỗ trợ, class phải modifiable.
11. **"Redefine sẽ chạy lại static initialization."** Sai: static state giữ nguyên theo contract.
12. **"Active method frame chuyển sang bytecode mới ngay lập tức."** Sai: frame cũ tiếp tục bytecode cũ.
13. **"Chỉ cần CRC của classfile là biết version logic."** Không đủ vì bytes có thể không bit-identical.
14. **"Callback throw sẽ ngăn JVM hoàn tất retransformation."** Không được phép dựa vào giả định đó.
15. **"Print-only demo chứng minh bytecode hook đã được replay."** Không: demo chứng minh callback pattern và behavior, còn bytecode-hook replay phải thử riêng.

## 13. Checklist thiết kế agent retransform an toàn

1. Xác định class/method/loader/module đích, tránh instrument mọi class JVM vô điều kiện.
2. Khai báo capability đúng trong agent manifest và kiểm tra `isRetransformClassesSupported`, `isModifiableClass`.
3. Phân biệt mốc define D0, redefine D1, D2 và pipeline replay/non-capable/capable.
4. Cho transformer capable nhận input tại đúng tầng, không tự dùng cache bytes của lượt trước làm nguồn mặc định.
5. Thiết kế patch idempotent theo pattern/marker, tránh hook bị nhân đôi.
6. Giữ transformer nhanh, tránh class loader circularity, logger, reflection và I/O trên đường class loading.
7. Không sửa mảng `classfileBuffer` trực tiếp; trả buffer mới hợp lệ khi thực sự transform.
8. Kiểm tra constraints schema, verifier, method signatures, exception handlers và stack frames.
9. Chạy test define → retransform ×2 → redefine → retransform ×2, so behavior, số callback và metrics.
10. So sánh artifact classfile bằng cả cấu trúc/semantics, không chỉ hash.
11. Quan sát overhead CPU/GC/latency và số diagnostic events bị drop.
12. Có cách rollback cấu hình, giải phóng transformer và báo cáo lỗi xác thực.

## 14. Câu hỏi tự kiểm tra

1. Lời gọi `retransformClasses(Target.class)` có nhận một classfile byte array do caller truyền không?
2. Khi chưa có redefine, mốc của lần retransform thứ năm đến từ đâu?
3. Sau lần redefine thành công từ V1 sang V2, retransform có tự quay lại V1 không?
4. Vì sao một transformer `canRetransform=false` vẫn có thể ảnh hưởng tới output retransform?
5. Lúc retransform, B có nhận dữ liệu đã bị A sửa hay không?
6. Tại sao `classBeingRedefined != null` không phân biệt đủ redefine với retransform?
7. Hash khác nhau có đủ để khẳng định JVM đã dùng mốc không đúng không?
8. `return null` của B có gỡ bỏ output A được replay không?
9. Khi redefine D2 thất bại, mốc dùng ở lượt retransform sau đó là D2 hay redefine thành công trước đó?
10. Một method có active frame đang chạy qua redefine có dùng ngay bytecode mới không?
11. Tại sao demo có `Can-Redefine-Classes` và `Can-Retransform-Classes` trong manifest?
12. Nếu dùng helper mới, những giới hạn nào cần kiểm tra để output thành class definition hợp lệ?
13. Vì sao việc `Target.version()` trả V2 sau retransform không chứng minh bytes bit-for-bit giống V2?
14. Khi JVM không hỗ trợ retransformation, nên xử lý yêu cầu của agent thế nào?
15. Bạn sẽ kiểm tra tính idempotent của một transformer có chèn hook ra sao qua nhiều lần redefine/retransform?

## 15. Kết luận và tài liệu chính thức

**Quy tắc cần nhớ:** lúc retransformation, JVM bắt đầu từ dữ liệu class file của lần define hoặc redefine gần nhất, tự tái sử dụng kết quả của những transformer non-capable và gọi lại các transformer capable. Kết quả retransform trước **không tự trở thành mốc đầu vào mới**. Một redefine thành công sẽ thay mốc, và initial bytes mà JVM biểu diễn có thể khác file nguồn ở constant pool/attributes mà vẫn đúng hợp đồng.

Nhờ hiểu rõ ranh giới này, bạn sẽ không đếm nhầm callback, không coi replay là call mới, không chồng hook vô hạn, không suy từ checksum mà đoán sai class version, và không vô tình reset logic V2 về V1 khi triển khai các agents phức tạp.

**Tài liệu đọc thêm:**

- [Oracle Java 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `retransformClasses`, `redefineClasses`, hỗ trợ và giới hạn; đủ để đối chiếu code demo.
- [Oracle Java 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): starting from initial class file bytes, replay non-capable, active frames và constant pool.
- [Oracle Java 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): thứ tự nhóm transformers và nguồn bytes khi define/redefine/retransform.
- [Oracle Java 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class` và các manifest capabilities.
- [JVM TI specification — RetransformClasses](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RetransformClasses): mô hình tương ứng khi có native agents.
