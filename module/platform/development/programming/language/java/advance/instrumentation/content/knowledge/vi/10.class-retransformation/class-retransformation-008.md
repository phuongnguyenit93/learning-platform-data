# Giới hạn retransformation: sửa thân phương thức được, thêm field/method hoặc đổi kế thừa thì không

Trong Java instrumentation, `Instrumentation.retransformClasses(...)` giúp cập nhật **định nghĩa của class đã được JVM nạp**, ví dụ để thêm lệnh ghi log, thu thập thời gian thực thi hay đổi logic trong một method. Nhưng đây **không phải cơ chế thay class bằng một class có cấu trúc tùy ý**.

Trên JVM theo hợp đồng Java 17/JVMTI, retransformation có thể thay **thân phương thức**, constant pool và các attribute **không bị cấm**. Ngược lại, nó không được thay đổi *schema* của class: không thêm, xóa hay đổi tên field/method; không đổi method signature, modifier hoặc quan hệ kế thừa; một số class attribute đặc biệt cũng phải giữ ổn định.

Bài này thuộc phần **Retransformation**, tập trung vào câu hỏi: “Vì sao thay đổi `return "old"` thành `return "new"` có thể thành công, còn thêm `private int x`, thêm method `foo()` hoặc đổi `extends` lại thất bại?”

Sau bài học, bạn sẽ:

- Phân biệt **thay đổi phần thân** và **thay đổi cấu trúc class**.
- Biết rõ những thay đổi **được phép, bị cấm, hoặc còn phải kiểm tra thêm**.
- Hiểu điều kiện `Can-Retransform-Classes`, `isRetransformClassesSupported()` và `isModifiableClass()`.
- Chạy ví dụ Java 17+ chứng minh một bản method body được áp dụng, nhưng bản có **field mới** bị từ chối.
- Hiểu số phận của object, static state và active stack frames sau khi retransform.
- Biết hướng thiết kế khác nếu cần “thêm trạng thái” hoặc “thêm hành vi” cho class đang chạy.

## 1. Retransformation là gì? Nó làm việc trên một class *đã nạp*

Khi JVM nạp class lần đầu, luồng tổng quát là:

```text
.class bytes ban đầu
       |
       v
ClassFileTransformer.transform(...)
       |
       v
class file bytes sau các transformer
       |
       v
JVM kiểm tra/định nghĩa class -> java.lang.Class<?> tồn tại
```

Sau khi class đã có trong JVM, một agent được cấp khả năng có thể gọi:

```java
instrumentation.retransformClasses(com.example.Target.class);
```

Đây là **một lời gọi minh họa**; giả định biến `instrumentation` đã nhận qua `premain`/`agentmain` và class `com.example.Target` đang tồn tại. Retransformation yêu cầu JVM chạy lại quy trình biến đổi bytecode cho class được chỉ định, nhưng **không định nghĩa một class thứ hai có cùng tên**, và **không tạo class có cấu trúc hoàn toàn khác**.

Trên API `java.lang.instrument`:

```java
void retransformClasses(Class<?>... classes)
        throws UnmodifiableClassException
```

Một lời gọi có thể yêu cầu nhiều class cùng lúc. Nếu có lỗi khi kiểm tra/cài đặt kết quả, JVM không cài đặt phiên bản mới cho bất kỳ class nào thuộc tập được yêu cầu trong lời gọi đó. Điều này giúp tránh một số trạng thái cập nhật dở dang ở cấp tập class, nhưng **không** thay thế quy trình kiểm thử nghiệp vụ và khả năng tương thích.

**Điểm xuất phát quan trọng:** class ban đầu **đã được định nghĩa**. JVM phải giữ những thông tin nhận dạng và cấu trúc vốn được các object, lời gọi và cơ chế linkage đang sử dụng. Vì vậy một số thay đổi có thể thực hiện khi **load-time instrumentation** nhưng không còn hợp lệ khi **retransform** class đó về sau.

## 2. Method body khác gì class schema?

Xét class nguồn:

```java
package demo;

public class Service {
    private int count = 0;

    public String message() {
        return "before";
    }

    public int count() {
        return count;
    }
}
```

### 2.1. Thay method body: thường hợp lệ

```java
public String message() {
    return "after";
}
```

Chữ ký vẫn là:

```text
message()Ljava/lang/String;
```

Mọi thứ thuộc phần “khung” class vẫn giống trước: class name, superclass, interfaces, fields, method name, descriptor và modifiers. Chỉ instruction/constant sử dụng bên trong `message()` được thay. Đây là **trường hợp điển hình** của instrumentation: thêm `println`, nhánh đo, tracer call hoặc sửa một phần xử lý nội bộ.

Không vì thế mà bất kỳ mảng byte nào cũng được chấp nhận. Class file mới phải hợp lệ, bytecode phải qua verifier, instruction/stack map/constant pool phải nhất quán, và mọi giới hạn liên quan vẫn áp dụng.

### 2.2. Thêm field: thay class schema, bị cấm

```java
private int count = 0;
private String newState; // Field chưa tồn tại trong class đã load.
```

Field mới làm thay **tập thành viên field** và có thể ảnh hưởng bố trí object, metadata reflection, hành vi truy cập. `retransformClasses` **không** mở rộng cấu trúc object hiện hữu theo cách đó. Trên JVM chuẩn của ví dụ, attempt này bị từ chối bằng `UnsupportedOperationException`.

Không có ngoại lệ đặc biệt chỉ vì field là `private`, `static`, `transient`, một reference nhỏ hoặc “chưa từng được đọc”.

### 2.3. Thêm method: cũng là thay schema, bị cấm

```java
public String message() {
    return "after";
}

public void newMethod() {  // Method mới.
    System.out.println("hello");
}
```

Thêm method thay tập method mà JVM biết cho class đó. Retransformation không dùng để mở rộng method table/vtable hoặc tạo API mới cho class đã load.

**Mẹo quan trọng khi dùng framework:** nếu một công cụ instrumentation tự tạo *synthetic method*, bridge method, accessor hoặc helper method **trong chính class đích**, phép biến đổi có thể hợp lệ lúc load lần đầu nhưng không hợp lệ khi retransform. Phải đọc bytes cuối cùng mà transformer trả về, chứ không chỉ nhìn mã Java ban đầu.

### 2.4. Đổi quan hệ kế thừa: thay type identity graph, bị cấm

```java
// Định nghĩa đã nạp:
public class Child extends BaseA implements Runnable { ... }

// Định nghĩa mới muốn áp dụng:
public class Child extends BaseB implements AutoCloseable { ... }
```

Việc đổi direct superclass hoặc tập interface trực tiếp làm thay quan hệ subtype, method resolution và dispatch. JVMTI không cho phép thay đổi inheritance như vậy trong retransformation.

Việc **thay một lời gọi ở trong body** từ `super.foo()` sang một lời gọi hợp lệ khác (với class structure vẫn ổn định) không đồng nghĩa đổi `extends`; cần đánh giá bytecode thực tế và access rules.

## 3. Ma trận: thay đổi nào có thể áp dụng lên class đã nạp?

| Thay đổi mong muốn | Retransform Java 17/JVMTI | Giải thích |
|---|---|---|
| Thêm log/metric vào thân method có sẵn | **Có thể** | Chỉ thay instructions trong `Code` attribute |
| Đổi nhánh hoặc hằng số sử dụng trong method có sẵn | **Có thể** | Giữ schema, bytes hợp lệ |
| Thay `return 1` bằng `return 2` trong method `int value()` | **Có thể** | Method name/descriptor không đổi |
| Thay exception handling bên trong một method | **Có thể**, phải verify | Bytecode và exception table phải hợp lệ |
| Sửa constant pool phục vụ body | **Có thể**, trong giới hạn class file | Constant pool có thể thay; không phải quyền sửa schema |
| Thay một số attributes không bị cấm | **Tùy attribute** | JVMTI cho phép một số attributes, nhưng có danh sách cấm |
| Thêm field instance hoặc static | **Không** | Tập field của class bị thay |
| Xóa hoặc đổi tên field | **Không** | Schema field bị thay |
| Thay field descriptor/type | **Không** | Tập field/schema không giữ nguyên |
| Thêm method (kể cả private/synthetic) | **Không** | Tập method bị thay |
| Xóa hoặc đổi tên method có sẵn | **Không** | Tập method bị thay |
| Đổi return type hoặc parameter types | **Không** | Method descriptor/signature bị thay |
| Thêm overload `foo(int)` mới | **Không** | Thực chất thêm method |
| Đổi method/class modifiers | **Không** | JVMTI cấm modifier changes |
| Đổi `extends BaseA` thành `extends BaseB` | **Không** | Direct superclass thay đổi |
| Thêm/bớt `implements InterfaceX` | **Không** | Tập interface trực tiếp thay đổi |
| Đổi `NestHost`/`NestMembers` | **Không** | Class attribute bị cấm thay |
| Đổi `Record` hoặc `PermittedSubclasses` | **Không** | Class attribute bị cấm thay |
| Thay đổi tên nhị phân của class | **Không** | Class identity không tương ứng |

Ở đây **“Có thể” không có nghĩa “luôn thành công”**: còn phụ thuộc JVM có capability, class có thể sửa được, bytecode mới có hợp lệ, các transformer khác có thay bytes không, và yêu cầu verifier/linkage/access control.

Tương tự, “không được đổi signature” không chỉ là quy tắc của Java compiler ở source. JVM xác định method bằng **name + descriptor** ở class file. `void f(int)` và `void f(long)` là hai descriptor khác nhau; đổi kiểu tham số tương đương xóa một method và thêm method khác đối với đối chiếu schema.

**Về attributes:** tài liệu JVMTI Java 17 đặc biệt cấm đổi `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`; đừng suy từ câu “attributes may change” rằng **mọi** attribute đều có thể thay. Các annotation/signature metadata cũng nên được kiểm thử từng loại, không tự đưa vào danh sách “luôn được phép”.

## 4. Vì sao JVM bắt giữ cấu trúc class ổn định?

Một class đang tồn tại được JVM và chương trình dùng ở nhiều nơi:

- **Object layout:** mỗi instance có field storage đã được cấp theo định nghĩa class đang tồn tại.
- **Runtime type checks:** `instanceof`, casts và định tuyến method phụ thuộc kế thừa/interface graph.
- **Linkage:** bytecode của class khác có thể đã resolve tham chiếu field/method theo name + descriptor.
- **Reflection và MethodHandle:** metadata tồn tại, có thể đã được truy cập và lưu giữ.
- **Active stack frames:** method đang chạy có frame và locals/operand stack tương ứng với phiên bản bytecode đã bắt đầu thực thi.
- **JIT/native code:** runtime có thể đã tối ưu các đường gọi dựa theo thông tin class.

Để cho phép sửa method body **mà vẫn bảo toàn identity và schema**, JVM có thể cài **phiên bản thực thi mới của method** cho những invocation tiếp theo; nó không cần làm mất tất cả instance hay thiết lập một type hierarchy khác ngay lập tức.

Điều này khác hoàn toàn với việc tải một class **mới** bằng một `ClassLoader` riêng: đó tạo ra một class có identity khác (tên nhị phân giống nhau vẫn có thể là hai runtime types nếu loader khác). Tạo class mới bằng loader khác **không phải** retransform class cũ.

## 5. Điều kiện để gọi `retransformClasses` thành công

### 5.1. Capability là optional

Cần **cả** JVM hỗ trợ khả năng retransform **và** agent có manifest phù hợp:

```text
Manifest-Version: 1.0
Premain-Class: agent.SchemaAgent
Can-Retransform-Classes: true

```

`Can-Retransform-Classes: true` là một **yêu cầu capability**, không phải cam kết của mọi JVM. Trên một JVM có hỗ trợ, `Instrumentation.isRetransformClassesSupported()` trả `true`. Nếu `false`, gọi `retransformClasses(...)` không phải cách ép JVM bật capability.

Agent có thể bắt đầu bằng:

```java
if (!inst.isRetransformClassesSupported()) {
    System.out.println("Retransformation not supported");
    return;
}
if (!inst.isModifiableClass(targetClass)) {
    System.out.println("Target class is not modifiable");
    return;
}
```

Đây là **đoạn method minh họa** (các biến `inst`, `targetClass` phải tồn tại), không phải chương trình độc lập. Hai API trả lời **hai câu hỏi khác nhau**:

- `isRetransformClassesSupported()`: cấu hình agent/JVM có khả năng này không?
- `isModifiableClass(targetClass)`: class cụ thể này có thể được định nghĩa lại/retransform theo loại class hay không?

Một class có thể được đánh giá “modifiable” nhưng capability retransform của agent vẫn không được bật. Các primitive class và array class không modifiable theo tài liệu `Instrumentation`.

### 5.2. Đăng ký transformer có khả năng retransform

```java
inst.addTransformer(transformer, true);
```

Tham số `true` yêu cầu callback của transformer được gọi khi `retransformClasses(...)` chạy. Nếu JVM/agent không hỗ trợ, việc đăng ký có thể ném `UnsupportedOperationException`.

Trái lại:

```java
inst.addTransformer(transformer, false);
```

hoặc:

```java
inst.addTransformer(transformer);
```

là transformer **không có khả năng callback lại** khi retransform. Kết quả biến đổi cũ từ nhóm này được **tái áp dụng** theo hợp đồng, chứ không gọi lại `transform(...)` chỉ vì retransform xảy ra.

Dù callback có được gọi lại hay không, **bytes cuối** sau toàn bộ chuỗi transformers vẫn phải giữ đúng schema mà JVM cho phép. Một transformer khác thêm field có thể khiến retransform thất bại ngay cả khi transformer của bạn chỉ sửa một instruction.

### 5.3. Khi nào gọi?

Agent có thể đăng ký transformer lúc `premain(String, Instrumentation)` hoặc `agentmain(String, Instrumentation)`, rồi yêu cầu retransform sau khi target class đã tồn tại.

- `-javaagent` + `premain`: agent được khởi động trước application `main`, nhưng vẫn có thể chủ động load class rồi retransform nó.
- Attach + `agentmain`: agent được nạp vào JVM đang chạy, phù hợp với bài toán bật instrumentation sau startup (nếu runtime cho phép dynamic agent loading).
- Không dùng `-javaagent` để “mặc nhiên tự retransform”; phải có code gọi `retransformClasses` hoặc cơ chế khác yêu cầu hoạt động.

## 6. Ví dụ Java 17+ hoàn chỉnh: sửa thân method thành công, thêm field bị từ chối

Ví dụ này tạo **ba class file có cùng tên nhị phân** `demo.Target`, nhưng chỉ **một bản** được JVM nạp làm class thật:

1. **`base`**: class gốc được nạp, `status()` trả `"before"`.
2. **`body`**: cùng schema, `status()` trả `"after"`.
3. **`field`**: giống schema gốc **ngoại trừ có thêm một field**, `status()` trả `"forbidden"`.

Một agent `SchemaAgent` đọc trước hai class file thay thế, đăng ký `ClassFileTransformer` rồi gọi `retransformClasses` hai lần. Lần đầu dùng bản `body` phải thành công trên môi trường có capability; lần sau dùng bản `field` phải bị từ chối theo giới hạn schema.

**Yêu cầu:** JDK 17+ có `javac`, `jar`, `java`, `Instrumentation` hỗ trợ retransform; không cần ASM, Byte Buddy, Maven hoặc Gradle. Ví dụ được kiểm tra bằng OpenJDK 21 với `javac --release 17`.

### 6.1. Sơ đồ file

```text
schema-retransform-demo/
├── src/
│   ├── base/demo/Target.java
│   ├── body/demo/Target.java
│   ├── field/demo/Target.java
│   ├── app/demo/App.java
│   └── agent/agent/SchemaAgent.java
├── agent.mf
└── out/                  (sinh ra khi biên dịch)
    ├── base/
    ├── body/
    ├── field/
    └── agent/
```

**Phải tạo đúng các thư mục `src/...` và file tương ứng.** Ba file `Target.java` cùng package/tên class được biên dịch **riêng** vào ba output directory khác nhau; không đưa cả ba vào cùng một lần `javac -d out/base` vì sẽ gây duplicate class.

### 6.2. `src/base/demo/Target.java`: phiên bản gốc

```java
package demo;

public final class Target {
    private static int counter = 10;

    public static void increment() {
        counter++;
    }

    public static int count() {
        return counter;
    }

    public static String status() {
        return "before";
    }
}
```

Đây là class thật được application class loader nạp. Trạng thái static `counter` bắt đầu ở `10`; để kiểm chứng dữ liệu runtime không bị reset, agent sẽ gọi `increment()` một lần trước khi retransform.

### 6.3. `src/body/demo/Target.java`: chỉ thay method body

```java
package demo;

public final class Target {
    private static int counter = 10;

    public static void increment() {
        counter++;
    }

    public static int count() {
        return counter;
    }

    public static String status() {
        return "after";
    }
}
```

So với bản `base`, class này có **cùng**:

- Tên `demo.Target` và modifier `public final`.
- Field `private static int counter`.
- Method `increment()V`, `count()I` và `status()Ljava/lang/String;`.
- Constructor và superclass mặc định `java.lang.Object`.

Điểm khác là instruction/constant được sử dụng trong **thân `status()`**. Bản classfile có thể có constant pool khác nhưng hợp đồng retransform cho phép thay đổi thích hợp này.

### 6.4. `src/field/demo/Target.java`: cố ý làm sai schema

```java
package demo;

public final class Target {
    private static int counter = 10;
    private static String addedField = "new";

    public static void increment() {
        counter++;
    }

    public static int count() {
        return counter;
    }

    public static String status() {
        return "forbidden";
    }
}
```

Sự khác biệt cố ý gây lỗi là:

```java
private static String addedField = "new";
```

Thêm field là một thay đổi **class schema**, không phải chỉ sửa method body. Class file này vẫn có thể **biên dịch hợp lệ và nạp lần đầu** nếu đứng riêng, nhưng **không được dùng để thay schema của `demo.Target` đã nạp** bằng `retransformClasses`.

Đây là đối chứng quan trọng: “`javac` biên dịch không lỗi” **không** đủ chứng minh class bytes là bản cập nhật hợp lệ cho runtime class hiện hữu.

### 6.5. `src/app/demo/App.java`: ứng dụng sử dụng phiên bản đang có trong JVM

```java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println("[app] status=" + Target.status()
                + ",count=" + Target.count());
    }
}
```

Khi chạy không có agent, app sẽ in `status=before,count=10`. Khi có agent cập nhật thân `status()`, app sẽ dùng body mới dù bytecode trên đĩa ở `out/base` không hề bị ghi đè.

### 6.6. `src/agent/agent/SchemaAgent.java`: điểm vào và transformer

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class SchemaAgent {
    static volatile String phase = "none";

    public static void premain(String args, Instrumentation inst)
            throws Exception {

        if (!inst.isRetransformClassesSupported()) {
            System.out.println("[agent] retransformation unsupported");
            return;
        }

        // Cố ý nạp class thật trước khi đăng ký transformer:
        // ta đang THỬ retransformation, không phải load-time transform.
        Class<?> type = Class.forName(
                "demo.Target",
                true,
                ClassLoader.getSystemClassLoader());

        if (!inst.isModifiableClass(type)) {
            throw new IllegalStateException("Target cannot be modified");
        }

        Method status = type.getMethod("status");
        Method count = type.getMethod("count");
        Method increment = type.getMethod("increment");

        System.out.println("[agent] before=" + status.invoke(null)
                + ",count=" + count.invoke(null));
        increment.invoke(null);

        // Đọc hai file thành byte[] trước khi gọi retransform.
        // Path tương đối được hiểu từ working directory của JVM.
        byte[] allowed = Files.readAllBytes(Path.of(
                "out", "body", "demo", "Target.class"));
        byte[] forbidden = Files.readAllBytes(Path.of(
                "out", "field", "demo", "Target.class"));

        inst.addTransformer(
                new PatchTransformer(allowed, forbidden), true);

        phase = "body";
        inst.retransformClasses(type);
        System.out.println("[agent] after-body=" + status.invoke(null)
                + ",count=" + count.invoke(null));

        phase = "field";
        try {
            inst.retransformClasses(type);
            throw new AssertionError(
                    "Adding a field was unexpectedly accepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("[agent] add-field=REJECTED");
        } finally {
            phase = "none";
        }

        System.out.println("[agent] final=" + status.invoke(null)
                + ",count=" + count.invoke(null));
    }
}

// Top-level class không public, cùng file SchemaAgent.java.
final class PatchTransformer implements ClassFileTransformer {
    private final byte[] allowed;
    private final byte[] forbidden;

    PatchTransformer(byte[] allowed, byte[] forbidden) {
        this.allowed = allowed;
        this.forbidden = forbidden;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!"demo/Target".equals(className)
                || classBeingRedefined == null) {
            return null;
        }

        return switch (SchemaAgent.phase) {
            case "body" -> allowed.clone();
            case "field" -> forbidden.clone();
            default -> null;
        };
    }
}
```

**Giải thích từng phần của agent:**

1. `isRetransformClassesSupported()` kiểm tra capability trước khi dùng.
2. `Class.forName(...)` nạp và khởi tạo `demo.Target` **trước** khi transformer được đăng ký. Điều này phân biệt rõ thí nghiệm với load-time transformation.
3. `status`, `count` và `increment` là các `Method` phản chiếu method của **cùng một runtime class**. Không tạo `ClassLoader` mới hay định nghĩa tên lớp mới.
4. `increment.invoke(null)` làm `counter` thành `11` trước khi cập nhật method body.
5. `Files.readAllBytes` lấy hai classfile đã được biên dịch, không cần thư viện chỉnh bytecode. Đường dẫn tương đối giả định chương trình chạy từ thư mục `schema-retransform-demo`.
6. `addTransformer(..., true)` đăng ký transformer có khả năng tham gia retransform. Manifest ở mục tiếp theo phải cho phép capability.
7. `phase = "body"` khiến transformer trả bytes bản **cùng schema, body khác**, và `retransformClasses(type)` yêu cầu JVM áp dụng.
8. `phase = "field"` khiến transformer trả bytes bản **có field mới**. JVM kiểm tra class schema và từ chối. `UnsupportedOperationException` được in thành nhãn ổn định, thay vì phụ thuộc thông điệp lỗi HotSpot cụ thể.
9. `finally { phase = "none"; }` trả transformer về chế độ không áp dụng thêm biến đổi.
10. Nếu phép retransform thất bại, **không cài bản `field`**; method đã cập nhật ở lần thành công trước vẫn có hiệu lực.
11. `return null` trong transformer nghĩa là **không đổi bytes** đối với callback không thuộc `demo.Target` hoặc không phải phiên retransform cần kiểm tra. `return allowed.clone()` / `forbidden.clone()` trả mảng mới, không sửa trực tiếp `classfileBuffer`.

Một câu hỏi thường gặp: vì sao `SchemaAgent` giữ biến `phase` dạng `volatile`? Vì callback của JVM có thể thực thi trong bối cảnh thread khác, và biến dùng để lựa chọn phiên bản bytes. `volatile` đảm bảo visibility cơ bản; đối với agent có **nhiều class retransform đồng thời**, cần thiết kế trạng thái và tương quan phức tạp hơn thay vì dùng một cờ global như demo.

Mã này dùng `switch` expression được Java 17 hỗ trợ, không cần Java preview. Dạng `transform(Module, ...)` là overload có `Module` của `ClassFileTransformer` trên Java 9+.

### 6.7. Manifest `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: agent.SchemaAgent
Can-Retransform-Classes: true

```

`Premain-Class` chọn điểm vào startup agent. `Can-Retransform-Classes: true` yêu cầu khả năng retransform. Cần giữ một dòng trống kết thúc main section khi tạo file manifest.

Không cần `Can-Redefine-Classes: true` cho ví dụ này vì nó **không gọi `redefineClasses`**. Hai capability độc lập và phải kiểm tra đúng API cần dùng.

### 6.8. Lệnh biên dịch và đóng JAR (JDK 17+)

Mở terminal ở thư mục gốc `schema-retransform-demo`, nơi có `src` và `agent.mf`. Tạo các thư mục output:

```bash
mkdir out
mkdir out/base
mkdir out/body
mkdir out/field
mkdir out/agent
```

Nếu thư mục đã tồn tại, bỏ qua lệnh tạo tương ứng. Sau đó biên dịch từng phiên bản cùng tên class vào **thư mục riêng**:

```bash
javac --release 17 -d out/base src/base/demo/Target.java
javac --release 17 -d out/body src/body/demo/Target.java
javac --release 17 -d out/field src/field/demo/Target.java

javac --release 17 -cp out/base -d out/base src/app/demo/App.java
javac --release 17 -d out/agent src/agent/agent/SchemaAgent.java
```

Lệnh `javac` thứ tư đặt `App.class` cùng classpath với bản `Target` gốc. Agent được biên dịch riêng và **không phụ thuộc compile-time** vào `demo.Target`; nó dùng reflection để truy cập runtime class.

Đóng **chỉ hai class của agent** vào JAR:

```bash
jar --create --file schema-agent.jar --manifest agent.mf -C out/agent agent/SchemaAgent.class -C out/agent agent/PatchTransformer.class
```

`SchemaAgent.java` chứa hai top-level class (`SchemaAgent` public và `PatchTransformer` package-private), nên `javac` tạo **hai file `.class`**. Phải đưa cả hai vào JAR để tránh `NoClassDefFoundError` khi agent tạo transformer.

Kiểm tra archive:

```bash
jar --list --file schema-agent.jar
```

Các entry quan trọng phải có:

```text
META-INF/MANIFEST.MF
agent/SchemaAgent.class
agent/PatchTransformer.class
```

`demo.Target` không có trong agent JAR; JVM tải nó từ `-cp out/base`. Hai bản thay thế `out/body/demo/Target.class` và `out/field/demo/Target.class` nằm trên filesystem cho agent đọc lúc chạy.

### 6.9. Chạy và giải thích stdout

Không có agent:

```bash
java -cp out/base demo.App
```

Stdout:

```text
[app] status=before,count=10
```

Có agent:

```bash
java -javaagent:schema-agent.jar -cp out/base demo.App
```

**Stdout được kiểm tra thực tế bằng OpenJDK 21 với toàn bộ class biên dịch `--release 17`:**

```text
[agent] before=before,count=10
[agent] after-body=after,count=11
[agent] add-field=REJECTED
[agent] final=after,count=11
[app] status=after,count=11
```

Giải thích từng dòng:

- **Before:** bản `out/base/demo/Target.class` đang được nạp; `status()` trả `"before"`, `counter` vừa khởi tạo là `10`.
- **After-body:** phép retransform đầu **được chấp nhận**, invocation mới của `status()` trả `"after"`; `counter=11` vì trước đó đã gọi `increment()`.
- **Add-field REJECTED:** bản thứ hai có field `addedField`, làm schema thay đổi và JVM từ chối.
- **Final:** class vẫn dùng bản body đã cập nhật, không biến thành bản chứa field mới; static counter vẫn `11`.
- **App:** sau khi `premain` kết thúc, `App.main()` gọi chính class đang tồn tại, thấy method body cập nhật và state cũ.

Đây là ví dụ về **cùng một class object được retransform**, không có thao tác replace class file ở `out/base` và không có class loader thứ hai. Các dòng `REJECTED` được **chính mã agent** in khi bắt `UnsupportedOperationException`; lời nhắn lỗi chi tiết của JVM khác nhau giữa phiên bản và không được dùng làm chuẩn kiểm thử.

**Nếu JVM không hỗ trợ retransform:** `SchemaAgent` sẽ in `[agent] retransformation unsupported` và trả về, ứng dụng chạy bản gốc. Trên môi trường được thử thành công (OpenJDK 21), nhánh đó không xuất hiện.

### 6.10. Quan sát classfile bằng `javap`

```bash
javap -p -classpath out/base demo.Target
javap -p -classpath out/body demo.Target
javap -p -classpath out/field demo.Target
```

Kiểm tra:

- `base` và `body`: cùng field và cùng method declarations; khác body `status()` (xem thêm `javap -c`).
- `field`: có thêm field `private static java.lang.String addedField;`.

Để xem instructions:

```bash
javap -c -p -classpath out/base demo.Target
javap -c -p -classpath out/body demo.Target
```

Trong method `status()`, hai bản có `ldc` trỏ đến các hằng chuỗi khác nhau rồi `areturn`. Index constant pool có thể khác giữa bản biên dịch; **không phụ thuộc vào offset/index chính xác** mà hãy kiểm tra hành vi và cấu trúc.

## 7. Object, static field và `<clinit>` có bị tạo lại khi retransform không?

**Không.** Retransformation không làm JVM khởi tạo lại class theo ý agent. Những object đã tồn tại không bị tạo mới hoặc tái bố trí field storage; giá trị field của chúng vẫn là giá trị runtime trước khi cập nhật (trừ khi code ứng dụng/agent chủ động thay đổi chúng sau đó).

Trong ví dụ, trước khi retransform:

```text
demo.Target.counter = 11
```

Bản `body` có khai báo source `private static int counter = 10`, nhưng cập nhật không có nghĩa JVM chạy lại `<clinit>` và đặt nó về `10`. Output chứng minh sau retransform **vẫn là 11**.

Phân biệt ba trường hợp:

1. **Khởi tạo class lần đầu:** JVM thực thi class initialization theo ngữ nghĩa Java thông thường.
2. **Retransformation class đã khởi tạo:** không chạy lại `<clinit>` để reset static fields.
3. **Logic method mới tự thay state khi được gọi:** có thể đổi field bình thường bằng chính code mới, nhưng đó là hành vi thực thi method, **không phải** hiệu ứng reset do retransform.

Nếu agent cần một cấu trúc state mới gắn với từng object mà không được thêm field, nó phải thiết kế một kho state **bên ngoài class đích** hoặc thay đổi thiết kế từ trước lúc load, không suy rằng JVM sẽ tự cấp thêm slot object.

## 8. Active stack frames: vì sao đang chạy có thể thấy bytecode cũ?

Một điểm quan trọng khác của hợp đồng là **method version**.

Khi class được cập nhật bằng retransformation:

- **Lần gọi method mới** sau khi cập nhật sẽ dùng phiên bản method mới.
- **Stack frame đã đang thực thi method đó** tại thời điểm cập nhật có thể tiếp tục chạy **bytecode của phiên bản cũ** đến khi frame kết thúc.

Mô hình:

```text
Thread A                            Thread B / Agent
--------                            ----------------
enter Service.work() [old bytes]
   |
   |---- work đang chạy ---------------------|
   |                                        |
   |                              retransform Service
   |                                 old -> new
   |                                        |
   |---- frame đang chạy vẫn theo old -------|
   |
return old outcome

lần gọi work() tiếp theo ----------> new method version
```

Vì vậy một lần retransform thành công **không đồng nghĩa tất cả lời gọi đang chạy lập tức chuyển sang code mới giữa method**. Nếu bạn chèn tracing advice vào một method đang rất bận, các invocation đã bắt đầu trước lúc cập nhật có thể không phát ra event mới từ những active frames cũ.

Đừng viết phép đo dựa vào giả định “ngay sau `retransformClasses` trả về, mọi stack frame đều đã instrument”. Đây là khác biệt thực tế quan trọng khi bật agent trong một hệ thống production đang xử lý request.

**Lưu ý thêm:** các frame cũ tiếp tục dùng bytecode cũ nhưng heap/object/field state vẫn được chia sẻ theo runtime. “Old bytecodes” không có nghĩa tạo bản sao heap, static state hoặc một hệ class song song.

## 9. Retransformation khác redefinition và load-time instrumentation thế nào?

| Cơ chế | Thời điểm | Input chính | Có thể thêm field/method cho class đã load? |
|---|---|---|---|
| Load-time `ClassFileTransformer` | **Trước khi JVM định nghĩa** class lần đầu | Bytes class ban đầu của lần load | Có thể tạo class schema khác hợp lệ ở thời điểm load, tùy giới hạn bytecode/runtime |
| `Instrumentation.retransformClasses` | **Sau khi class đã load** | JVM xuất phát từ initial class bytes và chạy lại chuỗi transformer theo hợp đồng | **Không** theo JVMTI Java 17 |
| `Instrumentation.redefineClasses` | **Sau khi class đã load** | Agent cung cấp class bytes mới qua `ClassDefinition` | **Không** theo JVMTI Java 17 |

**Không dùng `redefineClasses` như một mẹo để vượt các giới hạn schema** của `retransformClasses`. Hai cơ chế khác nhau về đường cung cấp bytes, nhưng `RedefineClasses` cũng cấm các thay đổi schema, modifiers và inheritance đang bàn ở đây.

### Quy trình retransform có thể có nhiều transformer

Theo `Instrumentation.retransformClasses`:

1. JVM bắt đầu từ initial class file bytes thích hợp, có thể không giống bit-by-bit bytes trên disk.
2. Biến đổi của các transformer **không capable** (`addTransformer(t, false)`) từ lần nạp/redefine trước được **tái áp dụng** mà không gọi lại callback của chúng.
3. Các transformer **capable** (`addTransformer(t, true)`) được gọi lại theo thứ tự nhóm.
4. JVM kiểm tra **bytes cuối**; chỉ sau đó mới cài đặt định nghĩa class mới nếu hợp lệ.

Vì vậy nếu một transformer khác ở chuỗi đã thêm member trong lúc class được load **ban đầu**, việc tái áp dụng biến đổi đó có thể làm sơ đồ bytecode nhìn khác file `.class` gốc nhưng vẫn nhất quán với định nghĩa đang tồn tại. Cần xem **schema đã được JVM định nghĩa**, không chỉ `javap` file nguồn ban đầu, để phân tích chính xác.

## 10. Trường hợp “thêm field/method để đo đạc”: cách thiết kế khác

Một số thư viện instrumentation muốn chèn:

- `private long $timerStart;` vào mỗi instance.
- `private static Counter $counter;` vào class.
- `private void $helper$method()` để gọi từ body đã sửa.
- Interface mới nhằm bổ sung marker hoặc hook behavior.

Đây đều là thay đổi **class structure** nếu thực hiện trong chính class đã được nạp. Retransformation không phải công cụ thích hợp.

### 10.1. Dùng state ngoài class đích

Thay vì thêm field vào `Service` đã load:

```java
// Ý tưởng thiết kế, KHÔNG phải agent độc lập.
private static final Map<Object, State> states =
        Collections.synchronizedMap(new WeakHashMap<>());
```

Đây là **đoạn field minh họa** trong một class quản lý state riêng, không phải code chèn vào target. `WeakHashMap` chỉ hữu ích khi hiểu rõ vòng đời object, equality/hashCode và sự sống của key/value; nếu `State` vô tình giữ strong reference về key, dữ liệu vẫn có thể bị giữ lại. Trong hệ concurrency cao, cần thiết kế thread-safety, identity semantics và GC phù hợp.

Nếu điểm đo chỉ cần state **theo invocation** (timestamp, trace context), thường giữ nó ở local variable/stack trong method body đã được instrument, hoặc trong một tracer service phù hợp, không nhất thiết cần thêm instance field.

### 10.2. Đưa helper method vào **class khác**

Nếu cần logic hỗ trợ phức tạp:

```java
// Đoạn method body minh họa của class đích sau transform:
public int work(int x) {
    AgentHelper.onEnter();
    try {
        return x * 2;
    } finally {
        AgentHelper.onExit();
    }
}
```

Điều này **không thêm method vào class đích**; chỉ sửa thân `work` để gọi method của `AgentHelper` thuộc **class helper riêng** đã được load/đóng gói hợp lệ. Cần đảm bảo helper thực sự có thể được class loader/module của target thấy, có access permission và không gây recursion khi instrument.

Đừng nhầm “thân method mới gọi method mới ở helper class” với “thêm method mới vào target class”. Cái thứ nhất là body edit có thể hợp lệ; cái thứ hai thay schema.

### 10.3. Cần thêm field/method thật thì làm khi class chưa được định nghĩa

Nếu bạn kiểm soát load-time instrumentation, có thể biến đổi class bytes **trước khi JVM định nghĩa class lần đầu** để tạo schema mong muốn. Nhưng phải chuẩn bị đủ compatibility, class loading, verification, class initialization và code gọi mới.

Nếu class đã load, một lựa chọn khác là **triển khai phiên bản phần mềm mới và khởi động lại** hoặc dùng kiến trúc class-loader versioning có quản lý rõ ràng. Thay loader có thể tạo type identity khác và cần giải quyết reference/serialization; không phải “retransform vượt rào” đơn giản.

### 10.4. Không phải mọi yêu cầu thay đổi trạng thái cần sửa schema

Ví dụ “thêm biến đếm” có thể giải quyết bằng:

- Counter bên ngoài, khóa theo method ID/class identity.
- Span start timestamp trong local variable được chèn vào method.
- Thread-local context có lifecycle được quản lý đúng.
- Weak-key state store với eviction/GC và chính sách identity rõ ràng.
- Nhờ code hiện có gọi helper để quan sát, thay vì thêm field vào object.

Mỗi hướng có tradeoff về memory, overhead, thread-safety và classloader leak, nhưng đều tránh yêu cầu JVM thêm field vào class đã nạp.

## 11. Giới hạn modifiers, attributes và inheritance — những trường hợp bị bỏ sót

Đặc tả JVM TI Java 17 nêu rõ ngoài field/method changes còn cấm:

- **Đổi method/class modifiers**: ví dụ thay `public` thành `private`, `final` thành không `final`, hoặc đổi tính chất static của method.
- **Đổi direct superclass**: `extends A` thành `extends B`.
- **Đổi tập interface trực tiếp**: `implements A` thành `implements A, B`.
- **Đổi `NestHost`/`NestMembers`**: quan hệ nest dùng cho access control của các class liên quan.
- **Đổi `Record` attribute**: metadata cấu trúc record (Java 16+).
- **Đổi `PermittedSubclasses`**: danh sách permitted subclasses của sealed class (Java 17+).

Một bytecode library có thể tạo ra bản `.class` hợp lệ về mặt hình thức nhưng lại thay các attributes này khi rebuild class. **Class file hợp lệ không đủ**, vì còn phải hợp lệ **như một phiên bản thay thế của chính class đang chạy**.

Ví dụ:

```text
Old: class demo.Service extends java.lang.Object
New: class demo.Service extends demo.Parent
```

Dù `Parent` có tồn tại và class mới có thể được JVM load bình thường như một type độc lập, **không** thể cài nó lên runtime type `demo.Service` đã tồn tại qua retransform.

Tương tự, thay một `public int f()` thành `private int f()` có thể không đổi descriptor nhưng vẫn làm **modifier khác**, nên cũng bị cấm. Không nên giới hạn checklist ở việc so sánh tên field/method.

## 12. Lỗi phổ biến: nhận biết lỗi capability, class target và schema

| Triệu chứng | Lý do có thể xảy ra | Cách xử lý |
|---|---|---|
| `isRetransformClassesSupported()` trả `false` | JVM/agent không có capability; manifest không yêu cầu | Kiểm tra `Can-Retransform-Classes: true` và runtime |
| `addTransformer(t, true)` báo `UnsupportedOperationException` | Capability retransform không bật | Kiểm tra hỗ trợ trước khi đăng ký |
| `retransformClasses` ném `UnmodifiableClassException` | Target không modifiable | Kiểm tra `isModifiableClass(target)` |
| `retransformClasses` ném `UnsupportedOperationException` | Capability thiếu **hoặc** thay đổi schema/khác không hỗ trợ | Phân biệt bằng pre-check; kiểm tra bytecode mới |
| Agent chỉ log, method không đổi | Transformer trả `null`, filter không match hoặc không được gọi khi retransform | Kiểm tra `className` dạng nội bộ, đăng ký `true`, bytes trả về |
| Transformer báo thành công nhưng method cũ còn chạy trong một thread | Frame đó đã active từ trước | Những invocation mới dùng method version mới |
| Thay body nhưng có `VerifyError` hoặc lỗi classfile | Bytecode/stack map/constant pool không hợp lệ | Chạy verifier, `javap`, kiểm tra tool chỉnh bytes |
| Đổi `extends` hoặc thêm interface bị từ chối | Inheritance graph bị thay | Giữ nguyên direct superclass/interfaces |
| Thêm `private static` field vẫn bị từ chối | Static field cũng là class schema | Lưu state ở helper class/ngoài target |
| Helper method không có trong bản gốc | Thêm method vào target bị cấm | Chuyển logic sang class helper riêng |
| Một lần retransform trước thành công, lần sau fail | Bytes của lần sau có thay đổi không hợp lệ | Đảm bảo lần fail không cài phiên bản mới; xem bytes cuối |
| Reflection không cho thấy field mới | Retransform không được thêm field | Không dùng reflection làm “proof” rằng field vừa được thêm |
| `ClassNotFoundException`/`NoClassDefFoundError` từ helper | Classloader/module không thấy dependency mới | Xem visibility, classpath, loader và module access |
| `ClassFormatError`/`UnsupportedClassVersionError` | Bytes không hợp lệ hoặc classfile version không tương thích | Biên dịch đúng target JDK và validate |

**Đừng bắt mọi `Throwable` rồi in “schema rejected”**. Một `IOException` đọc file sai, `ClassFormatError` do dữ liệu hỏng, hay lỗi classloader hoàn toàn khác với việc JVM từ chối thêm member. Ví dụ mục 6 chỉ xem `UnsupportedOperationException` là chỉ dấu cho nhánh bị cấm khi đã qua capability pre-check.

## 13. Preflight thực tế trước khi retransform trong production

Một quy trình an toàn nên có:

1. **Khóa đúng target class:** tên class cùng `ClassLoader`/`Module`, không chọn chỉ theo string khi có nhiều loader.
2. **Kiểm tra capability:** `inst.isRetransformClassesSupported()`.
3. **Kiểm tra từng class:** `inst.isModifiableClass(clazz)`.
4. **Kiểm tra manifest:** `Can-Retransform-Classes: true`; nếu dùng attach, kiểm tra chính sách dynamic agent loading riêng.
5. **Đánh giá schema:** so sánh tên/descriptor field/method, class modifiers, superclass/interfaces và attributes bị cấm giữa bản trước và bản sau.
6. **Giữ method descriptor và access flags:** đặc biệt khi library có xu hướng sinh method bridge/synthetic.
7. **Kiểm tra bytecode:** stack map frames, max stack/locals, labels, exception tables và verifier.
8. **Thử nhiều transformer:** đảm bảo không có transformer khác làm thay schema ở bước cuối.
9. **Thử active invocations:** không suy luận rằng mọi frame lập tức dùng bytecode mới.
10. **Thử state preservation:** object và static state đang có phải được bảo toàn.
11. **Lập phương án rollback:** muốn bỏ instrumentation cần biết chuỗi transformers và bytes nguồn; `return null` tại callback mới không tự xóa tất cả thay đổi từ các transformer khác.
12. **Triển khai theo đợt:** đo overhead/latency của callback, lỗi verifier, classloader leaks và tác động tới production traffic.

Trong một pipeline phức tạp, **bản classfile trả về cuối cùng** mới là thứ JVM xác minh. Không đủ nếu transformer của bạn giữ schema nhưng transformer bên cạnh lại thêm field hoặc sửa modifiers.

### 13.1. So sánh schema trước khi gửi bytes

Nếu có hai bản class file trên disk, có thể dùng:

```bash
javap -p -classpath out/base demo.Target
javap -p -classpath out/body demo.Target
javap -p -classpath out/field demo.Target
```

Đây là bước kiểm tra **mang tính minh họa**, không phải phép so sánh schema đầy đủ cho mọi loại attributes. Đối với bài toán phức tạp, dùng thư viện ClassFile reader/ASM hoặc Java Class-File API ở JDK phù hợp để so sánh có hệ thống.

### 13.2. Không đồng nhất compile-time, load-time và runtime schema

Có ba đối tượng thường bị nhầm:

- **File `.class` trên disk:** có thể được biên dịch lại bất kỳ lúc nào.
- **Class mới được JVM nạp lần đầu:** có thể có schema được instrument từ đầu.
- **Class object đã tồn tại:** chỉ được phép cập nhật trong giới hạn retransform/redefine của JVM.

Trong ví dụ, `out/field/demo/Target.class` có thể biên dịch **hợp lệ**, nhưng điều đó không có nghĩa nó có thể được cài vào runtime class `demo.Target`. JVM không kiểm tra chỉ “bytes có hợp lệ không”, mà còn “bytes có được phép là **phiên bản mới của chính type đó** không”.

## 14. Bài tập áp dụng

**Câu 1.** Class đã được load có method `int cost()` trả `3`. Agent sửa thân method để trả `5` nhưng không đổi method name/descriptor. Có thể retransform không?

**Đáp án:** Có thể, nếu capability/class modifiable và bytecode hợp lệ; đây là body edit điển hình.

**Câu 2.** Agent muốn thêm field `private long startNs` vào class đã load để theo dõi thời gian từng instance. Có thể dùng `retransformClasses` không?

**Đáp án:** Không. Field mới thay class schema. Dùng state ngoài class hoặc thiết kế instrumentation trước load; nếu cần thay schema thật phải có đường phát hành/kiến trúc khác.

**Câu 3.** Agent thêm `private static final String TAG = "x"` vào class đã load, nhưng cho rằng static field không thay layout object. Có hợp lệ không?

**Đáp án:** Không. Dù không tăng kích thước instance, nó vẫn thêm **field trong class schema**.

**Câu 4.** Agent thay thân `foo(int)` bằng code mới, đồng thời đổi nó thành `foo(long)`. Có hợp lệ không?

**Đáp án:** Không. Descriptor thay từ `(I)` sang `(J)`; method signature thay đổi.

**Câu 5.** Agent thay `extends BaseA` thành `extends BaseB`, cả hai superclass đều hợp lệ và cùng interface. Có chấp nhận không?

**Đáp án:** Không. Direct superclass thay đổi, vi phạm inheritance restriction.

**Câu 6.** Agent không thêm member nhưng đổi `public` thành `private` ở một method. Kết quả?

**Đáp án:** Bị từ chối theo giới hạn thay đổi modifiers.

**Câu 7.** Sau khi retransform, method đang chạy trong Thread A có lập tức chuyển sang code mới ở instruction tiếp theo không?

**Đáp án:** Không. Active frames tiếp tục chạy bytecode của phiên bản method cũ; invocation mới dùng phiên bản mới.

**Câu 8.** `Target.counter` đang bằng `11`. Bản classfile mới có `private static int counter = 10;`. Retransform làm `counter` reset về `10` không?

**Đáp án:** Không. Retransform không tự chạy lại class initializer, và static state hiện hữu được giữ.

**Câu 9.** Một transformer khác trong pipeline thêm synthetic helper method trước khi kết quả tới JVM. Transformer của bạn chỉ đổi `ireturn` trong body. Re-transform có thể thành công không?

**Đáp án:** Không thể khẳng định; JVM xem bytes cuối của cả chuỗi. Nếu kết quả cuối thêm method so với runtime schema, thay đổi đó không được phép.

**Câu 10.** Nếu `retransformClasses(type)` bị từ chối vì thêm field, liệu method body của lần retransform trước có tự bị reset về bản gốc không?

**Đáp án:** Không. Lần cập nhật thất bại không cài định nghĩa mới; phiên bản đã cài thành công trước đó vẫn là bản đang có.

**Câu 11.** Có thể đổi `NestMembers` hoặc `PermittedSubclasses` mà không thêm method/field không?

**Đáp án:** Không. Đây là các class attributes thuộc danh sách bị cấm thay trong JVM TI Java 17.

**Câu 12.** Muốn có logic helper mới để phục vụ body của `Service.work()`, nhưng `Service` đã được load. Cách nào phù hợp?

**Đáp án:** Đưa helper method vào **class khác** có thể nhìn thấy và sửa body của `Service.work()` để gọi helper đó; vẫn phải đảm bảo bytecode/loader/module hợp lệ.

## 15. Tóm tắt

- Retransformation là công cụ **cập nhật bytecode của một runtime class đã nạp**, không phải công cụ thay đổi toàn bộ class schema.
- **Sửa method body** là use case cốt lõi; thay constant pool và một số attributes có thể hợp lệ nếu đúng giới hạn và verifier.
- **Thêm/xóa/đổi tên field hoặc method, đổi descriptor, modifier, inheritance** là các thay đổi không hợp lệ đối với retransform Java 17/JVMTI.
- `NestHost`, `NestMembers`, `Record` và `PermittedSubclasses` cũng nằm trong các class attributes **không được đổi**.
- `Can-Retransform-Classes: true`, `isRetransformClassesSupported()` và `isModifiableClass()` là các bước kiểm tra cần thiết, nhưng chưa đảm bảo bytes mới hợp lệ.
- **Object và static field state không reset** khi retransform; active stack frames có thể tiếp tục bytecode cũ, invocation mới dùng bản method mới.
- `redefineClasses` **không** phải cách lách các ràng buộc schema trong Java 17.
- Khi cần state/helper mới sau startup, cân nhắc **helper class**, **external state store** hoặc **load-time instrumentation** từ trước khi class được định nghĩa.
- Ví dụ JDK 17+ đã kiểm tra thực tế: **body edit thành công, added field bị từ chối, state không mất**.

## Tài liệu chính thức

- Oracle Java 17 — [`Instrumentation.retransformClasses(...)`, capability, active stack frames và atomic failure](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle Java 17 — [JVM Tool Interface, `RetransformClasses`: thay đổi được phép/bị cấm, method modifiers, class attributes, error codes](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html).
- Oracle Java 17 — [`ClassFileTransformer`: callback, group order, `return null` và cách dùng bytes](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).
- Oracle Java 17 — [Package `java.lang.instrument`: manifest capability và startup agent](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).
- Oracle Java 17 — [Java Virtual Machine Specification, Class File Format (Chương 4)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html).
