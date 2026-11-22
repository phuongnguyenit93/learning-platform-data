# Biến đổi xác định theo đầu vào và khả năng chịu được nhiều lần xử lý trong Java Instrumentation

## 1. Tại sao transformer phải ổn định?

Trong Java Instrumentation, một `ClassFileTransformer` có thể được gọi khi JVM định nghĩa lớp, khi lớp được redefine hoặc (nếu transformer hỗ trợ) khi lớp được retransform. Một lớp cũng có thể đi qua **nhiều transformer**, đến từ cùng agent hoặc các agent khác nhau. Đầu ra của transformer trước chính là đầu vào của transformer sau.

Nếu mỗi lần gặp cùng class file mà transformer lại tạo ra bytecode khác nhau một cách không có chủ đích, hoặc mỗi lần xử lý lại chèn thêm hook, wrapper, metric hay field, hệ thống dễ gặp:

- Kết quả chạy khác nhau giữa hai lần khởi động dù cùng mã và cấu hình.
- Log/metric bị ghi hai, ba lần vì cùng một hook được chèn nhiều lần.
- Stack trace và thứ tự gọi method khó dự đoán; chi phí instrumentation tăng theo số lượt.
- `ClassFormatError`, `VerifyError` hoặc lỗi khi retransform vì cấu trúc class file không còn hợp lệ.
- Một agent khác không xử lý được output mới, hoặc pipeline đổi hành vi theo thứ tự đăng ký.

Hai thuộc tính cần thiết kế là:

1. **Biến đổi xác định theo đầu vào** (*deterministic transformation*): cùng bytecode đầu vào và cùng ngữ cảnh/cấu hình cố định thì tạo cùng kết quả.
2. **Chịu được nhiều lần xử lý** (*idempotence* hoặc *repeat-safe transformation*): khi cùng phép biến đổi tác động lặp lên output của chính nó, kết quả không tiếp tục bị thay đổi ngoài ý muốn.

Hai thuộc tính **khác nhau**. Một phép biến đổi có thể hoàn toàn deterministic nhưng vẫn chèn thêm hook ở mỗi lần chạy; ngược lại, một phép biến đổi có thể tránh chèn trùng nhưng còn sinh tên helper ngẫu nhiên và vì vậy không deterministic.

## 2. Mô hình hóa rõ ràng

Gọi `B` là class file bytes, `C` là ngữ cảnh đã được xác định (tên lớp, class loader/module, cấu hình agent, phiên bản schema và các input thực sự có ảnh hưởng). Với phép biến đổi hiệu dụng `T(B, C)`:

### 2.1. Determinism

```text
B1 = B2 và C1 = C2
             =>
T(B1, C1) = T(B2, C2)
```

Ở đây dấu bằng có thể được kiểm bằng **byte-for-byte equality** khi đó là hợp đồng chủ đích của transformer; ít nhất phải bảo đảm **ngữ nghĩa output tương đương** nếu thư viện phát sinh constant-pool ordering khác giữa những cách tạo class hợp lệ. Trong một bài test cố định trên cùng công cụ/cấu hình, so sánh byte array chính xác sẽ phát hiện độ bất định rõ ràng nhất.

Không được hiểu “input” chỉ là mảng byte nếu transformer còn đọc file cấu hình, system property, biến môi trường, tên module hoặc loader. Khi những giá trị đó thay đổi, đầu ra khác nhau **không vi phạm** determinism đối với một hợp đồng input bao gồm chúng.

Ví dụ **không deterministic** khi muốn cùng input cho cùng output:

```java
String helperName = "agent$" + System.nanoTime();
```

Cùng một class file có thể nhận hai tên helper khác nhau. Một cách ổn định hơn là tạo tên từ class/method descriptor và version cấu hình, ví dụ hash cố định của `className + methodName + descriptor + ruleVersion`, rồi xử lý collision một cách xác định.

### 2.2. Idempotence

```text
T(T(B, C), C) = T(B, C)
```

Điều này có nghĩa xử lý lại **output đã xử lý** không tiếp tục tăng mức can thiệp. Với bytecode instrumentation, “idempotent” thường được hiện thực bằng cách **phát hiện hook đã tồn tại** rồi không chèn thêm một bản nữa.

Ví dụ transformer không idempotent:

```text
Ban đầu:   public void work() { businessLogic(); }
Lượt 1:    public void work() { trace(); businessLogic(); }
Lượt 2:    public void work() { trace(); trace(); businessLogic(); }
```

Transformer tốt hơn kiểm tra probe trước khi chèn:

```text
Ban đầu:   work() { businessLogic(); }
Lượt 1:    work() { trace(); businessLogic(); }
Lượt 2:    work() { trace(); businessLogic(); }   // Không chèn trùng.
```

**Chú ý hợp đồng Java:** `ClassFileTransformer.transform(...)` có quyền trả về `null` nếu không cần thay đổi bytes. Khi suy luận về `T` ở trên, hiểu `return null` là **phép đồng nhất**: đầu ra hiệu dụng bằng bytes đầu vào, chứ không coi `null` là một class file.

### 2.3. Deterministic không tự động idempotent

Phép xử lý dưới đây luôn cho cùng output nếu cùng input:

```java
String addHook(String text) {
    return "trace();" + text;
}
```

Nó deterministic nhưng **không idempotent**: `addHook(addHook("work();"))` chứa hai lần `trace();`. Cần thêm điều kiện nhận biết đã instrument hoặc viết lại thuật toán theo một dạng chuẩn tắc (*canonical form*).

### 2.4. Idempotent không đồng nghĩa không có side effects

Một hàm tạo bytecode có thể idempotent nhưng callback vẫn ghi log, tăng counter, đăng ký shutdown hook hoặc mở resource **mỗi lần được gọi**. Do đó phân biệt:

- **Idempotence của output class file**: không tăng hook hay wrapper trong bytes.
- **Repeat safety của side effects**: logging, đăng ký thread/handler, lưu cache và cập nhật trạng thái không gây hành vi nhân đôi không mong muốn.
- **Idempotence của toàn pipeline**: các transformer khác nhau khi kết hợp vẫn không sinh tác động mới ở mỗi lần chạy lại.

Không phải mọi side effect đều phải triệt tiêu. Một counter “số lượt callback” chủ động tăng mỗi lần là hợp lệ; chỉ không được lấy nó làm giá trị thay đổi cách sinh bytecode khi muốn kết quả deterministic.

## 3. Hợp đồng thực tế của `ClassFileTransformer`

Một agent đăng ký transformer:

```java
instrumentation.addTransformer(transformer);
```

hoặc:

```java
instrumentation.addTransformer(transformer, canRetransform);
```

Khi một lớp được định nghĩa, JVM gọi các transformer theo thứ tự nhóm và đăng ký được đặc tả. Trong một chuỗi transformer `A` rồi `B`:

```text
Class file bytes ban đầu
           |
           v
A.transform(..., input)
           |
           +-- return null  -> giữ nguyên input
           |
           +-- return bytes -> output A
           |
           v
B.transform(..., output hiệu dụng của A)
           |
           v
JVM verify và định nghĩa class
```

Các nguyên tắc:

- **Không chỉnh trực tiếp `classfileBuffer` đầu vào**. Khi cần sửa, tạo **`byte[]` mới**; không sửa object được truyền cho callback.
- Nếu không có thay đổi cần thiết, **trả `null`**, không phải array rỗng.
- Output phải là **class file hợp lệ** cho JVM mục tiêu. Một byte array không hợp lệ không trở nên đúng chỉ vì phép xử lý deterministic.
- Bộ lọc lớp sử dụng tên dạng JVM internal như `com/example/Service`; nên viết null-safe: `"com/example/Service".equals(className)`.
- `loader` có thể `null` cho bootstrap loader. Các loader khác nhau có thể định nghĩa hai class cùng tên; đừng gộp cache chỉ theo `className` khi output phụ thuộc vào class loader/module.
- Các transformer được gọi trong quá trình class loading; tránh load thêm class không cần thiết, I/O tùy tiện, recursion hoặc khóa toàn cục khó kiểm soát.

Trên Java 17, cả hai overload của `ClassFileTransformer.transform` (dạng có/không có `Module`) đều có **default implementation**. Vì vậy `ClassFileTransformer` không phải functional interface: ví dụ Java 17 nên dùng class/anonymous class override method, **không viết lambda** cho interface này.

### Khi có nhiều transformer

Với hai phép `A` và `B`:

```text
F(B) = B_transform(A_transform(B))
```

Phép hợp thành `F` có thể khác nếu đổi thứ tự A/B, tức **không mặc định giao hoán**. Hơn nữa, dù A và B đều idempotent riêng rẽ, **F chưa chắc idempotent**.

Một ví dụ đơn giản trên chuỗi:

- `A` đổi `a → b`; tự chạy lặp không đổi thêm gì.
- `B` đổi `c → a`; tự chạy lặp không đổi thêm gì.
- Chuỗi `F = B ∘ A` cho `F(c) = a`, nhưng `F(F(c)) = F(a) = b`.

Điều này lý giải vì sao phải test **cả pipeline theo đúng thứ tự đăng ký**, không chỉ test từng transformer. Các phép biến đổi cần precondition và định nghĩa ownership rõ ràng: transformer nào được quyền chèn method, attribute hoặc hook nào; làm sao nhận biết dấu vết của transformer khác.

## 4. Retransformation có phải “chạy T lên T(B) lần nữa” không?

**Không nhất thiết.** Đây là khác biệt rất quan trọng giữa mô hình toán học kiểm tra idempotence và cơ chế JVM.

Theo `Instrumentation.retransformClasses` trong Java SE 17:

1. JVM bắt đầu từ **initial class file bytes** của lần định nghĩa hoặc redefine gần nhất (có thể không trùng từng byte với bản trên đĩa do JVM chuẩn hóa constant pool và các thuộc tính).
2. Đối với transformer đăng ký `canRetransform=false`, JVM **tái sử dụng kết quả cũ**, **không gọi lại `transform(...)`** của transformer đó.
3. Đối với transformer đăng ký `canRetransform=true`, JVM **gọi lại `transform(...)`** trên bytecode theo chuỗi đang hình thành.
4. Khi hợp lệ, JVM cài đặt definition mới.

```text
Lần load đầu:
  input B -> A(canRetransform=false) -> B(canRetransform=true) -> JVM

Lần retransform:
  initial bytes
     -> áp lại output trước của A, KHÔNG gọi A
     -> gọi B với input ở giai đoạn tương ứng
     -> JVM
```

Vì thế, nhiều lần retransform không chứng minh transformer đã nhận đúng bytes output của **chính lượt trước**. Để kiểm tra idempotence thực sự, cần có unit/property test **chủ động truyền output của T vào T lần thứ hai**. Đồng thời phải có test integration trên JVM thật vì classfileBuffer của retransform có thể khác với byte array của lần load đầu.

Tuy nhiên repeat safety vẫn quan trọng khi:

- Cùng phép patch vô tình được đăng ký **hai lần**;
- Nhiều transformer cùng dùng một thư viện rewrite;
- Công cụ build-time và runtime cùng instrument một class;
- Re-define đưa một class đã instrument trở lại JVM;
- Agent bật/tắt một số rule và chạy lại pipeline trên nhiều lớp.

JVM cho phép đăng ký cùng một transformer nhiều lần nhưng API **không khuyến khích** cách làm này. Cần quản lý vòng đời và registration riêng, không chỉ dựa vào idempotence bytecode để chữa lỗi đăng ký trùng.

## 5. Chiến lược tạo biến đổi ổn định trong production

### 5.1. Dựa trên class identity và cấu hình bất biến

Một policy có thể biểu diễn thành:

```text
TransformInput {
  className,
  definingClassLoader,
  module,
  classfileBuffer,
  immutableRuleSet,
  instrumentationSchemaVersion
}
```

Không nên dựa vào `System.nanoTime()`, UUID ngẫu nhiên, thứ tự duyệt `HashMap` không ổn định hoặc số lần callback để sinh tên helper, mã probe hay thứ tự method/attribute khi determinism là yêu cầu.

Nếu cấu hình có thể thay đổi lúc chạy, lấy một **snapshot bất biến** cho từng lượt transform. Ghi rõ version rule. Cùng input nhưng config version mới thì output mới là có chủ đích, không phải lỗi nondeterminism.

### 5.2. Nhận diện biến đổi đã áp dụng

Các cách thông dụng khi dùng ASM/Byte Buddy hoặc công cụ tương đương:

- **Kiểm tra cấu trúc bytecode**: tìm đúng lời gọi tới helper đã biết (owner/name/descriptor), hoặc pattern wrapper đã instrument, trước khi chèn.
- **Marker có namespace và version**: thêm dấu hiệu có chủ sở hữu rõ, chỉ khi định dạng class và JVM cho phép; marker phải phản ánh **đúng trạng thái thực**, không chỉ một chuỗi dễ va chạm.
- **Canonical rewriting**: phân tích method thành cấu trúc logic, loại các probe thuộc version cũ của chính agent và sinh lại đúng một lần theo rule hiện hành. Cách này cần xử lý rất thận trọng các probe của agent khác.

Marker đơn giản có thể lỗi thời nếu một agent khác đã thay đổi bytecode; kiểm tra marker và cấu trúc quan trọng cần đi cùng nhau. Đừng xóa marker hoặc hook của công cụ khác nếu không có hợp đồng rõ ràng.

### 5.3. Sinh output ổn định và hợp lệ

- Dùng tool hiểu **constant pool**, opcode, stack map frames, exception table, method descriptors và classfile version; tránh tìm/replace raw bytes theo chuỗi tên class/method ở nơi tùy tiện.
- Với ASM, cố định cách duyệt/sinh cấu trúc và chiến lược tính toán frames/max stack. Với Byte Buddy, giữ cấu hình/matcher/naming strategy ổn định.
- Không đổi schema class trong retransformation nếu JVM không hỗ trợ; nhiều loại thay đổi field/method/supertype bị hạn chế.
- Nếu không có thay đổi, trả `null`. Nếu sửa, trả bản sao mới hợp lệ.
- Nếu transformer tạo side effect, cân nhắc gắn correlation ID/trace và cơ chế dedup riêng, không để những side effect đó quyết định bytecode một cách ngẫu nhiên.

## 6. Ví dụ Java 17 chạy được: một transformer deterministic và idempotent

Ví dụ này **cố ý nhỏ** để nhìn trực tiếp tính chất đầu vào/đầu ra. Nó sửa đúng một hằng chuỗi ASCII trong **constant pool** của một class mẫu:

```text
"ORIGIN"  ->  "PATCH!"
```

Cả hai chuỗi đều 6 byte ASCII, nên không cần đổi độ dài CONSTANT_Utf8 hoặc các offset sau nó. Transformer chỉ xử lý class `Target` và không sửa `classfileBuffer` tại chỗ.

Ví dụ là bài minh họa cơ chế, **không phải bộ sửa class file tổng quát**. Production nên dùng ASM/Byte Buddy thay vì tự viết parser. Parser bên dưới nhận biết các tag constant pool thuộc Java 17 và giả định input là class file hợp lệ do `javac` sinh ra; không nhằm xử lý dữ liệu tùy ý hoặc class file hỏng.

### 6.1. Các tệp cần tạo

```text
stable-demo/
├── StableAgent.java
├── PatchTransformer.java
├── Target.java
├── DemoApp.java
└── agent.mf
```

Mọi class ở default package để tập trung vào thuật toán. Chạy lệnh ở chính thư mục chứa các tệp.

### 6.2. `Target.java`

```java
public final class Target {
    private Target() {
    }

    public static String value() {
        return "ORIGIN";
    }
}
```

Phương thức này chứa literal duy nhất `ORIGIN` mà transformer tìm ở CONSTANT_Utf8. Khi lớp được JVM định nghĩa qua agent, literal sẽ được thay bằng `PATCH!`.

### 6.3. `StableAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class StableAgent {
    private StableAgent() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        inst.addTransformer(new PatchTransformer(), false);
    }
}
```

Agent đăng ký đúng một transformer, không gọi retransform, không cần `Can-Retransform-Classes`. Callback diễn ra lúc JVM định nghĩa `Target` sau khi agent đã được cài.

### 6.4. `PatchTransformer.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.nio.charset.StandardCharsets;

public final class PatchTransformer implements ClassFileTransformer {
    private static final byte[] OLD =
            "ORIGIN".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] NEW =
            "PATCH!".getBytes(StandardCharsets.US_ASCII);

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!"Target".equals(className)) {
            return null; // Không can thiệp class khác.
        }

        return patch(classfileBuffer);
    }

    // Hàm thuần: cùng bytes đầu vào -> cùng bytes đầu ra.
    // Trả null nếu đã patch hoặc không có literal cần thay.
    public static byte[] patch(byte[] original) {
        if (original.length < 10
                || (original[0] & 0xff) != 0xca
                || (original[1] & 0xff) != 0xfe
                || (original[2] & 0xff) != 0xba
                || (original[3] & 0xff) != 0xbe) {
            throw new IllegalArgumentException("Not a class file");
        }

        int cpCount = u2(original, 8);
        int p = 10;            // Đầu constant_pool.
        byte[] changed = null; // Chỉ cấp phát khi thực sự cần.

        for (int i = 1; i < cpCount; i++) {
            int tag = original[p++] & 0xff;

            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int length = u2(original, p);
                    p += 2;

                    if (length == OLD.length
                            && equalsAt(original, p, OLD)) {
                        if (changed == null) {
                            changed = original.clone();
                        }
                        System.arraycopy(
                                NEW, 0, changed, p, NEW.length);
                    }

                    p += length;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 -> p += 4;
                case 5, 6 -> { // Long/Double chiếm 2 index.
                    p += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> p += 2;
                case 15 -> p += 3;
                default -> throw new IllegalArgumentException(
                        "Unsupported constant pool tag: " + tag);
            }
        }

        return changed; // null = input không cần đổi.
    }

    private static int u2(byte[] bytes, int p) {
        return ((bytes[p] & 0xff) << 8)
                | (bytes[p + 1] & 0xff);
    }

    private static boolean equalsAt(
            byte[] bytes, int offset, byte[] expected) {
        for (int i = 0; i < expected.length; i++) {
            if (bytes[offset + i] != expected[i]) {
                return false;
            }
        }
        return true;
    }
}
```

Giải thích chi tiết:

- `transform` kiểm tra đúng tên internal `"Target"`, vì class mẫu không có package; các class còn lại không bị tác động.
- `patch` chỉ duyệt cấu trúc **constant pool**, không tìm chuỗi bằng cách quét cả classfileBuffer; vì vậy không vô tình đổi bytes của method body, length field hay attribute.
- Chỉ khi tìm thấy `CONSTANT_Utf8` có đúng 6 bytes `ORIGIN` mới tạo `original.clone()` và thay vào bản clone. JVM vẫn nhận mảng đầu vào nguyên vẹn.
- Lượt sau, chuỗi đã thành `PATCH!`, không còn `ORIGIN`; `patch` trả `null`, tương đương “giữ nguyên input đã được patch”.
- Thuật toán không phụ thuộc đồng hồ, random, số lần gọi hoặc trạng thái toàn cục có thể thay đổi.
- Các case `5` và `6` xử lý quy tắc một constant pool entry Long/Double dùng hai index. Ví dụ đơn giản này không xử lý class file hỏng hoặc tag trong định dạng tương lai.
- Đổi literal cùng độ dài không thay đổi schema class, method signatures, stack map frames hay offset, nên là thay đổi hợp lệ cho class mẫu trong Java 17.

Trong một ứng dụng thật, thay literal từ constant pool một cách tổng quát có thể ảnh hưởng **mọi chỗ cùng tham chiếu** tới hằng đó, không chỉ một method. Do đó ví dụ giới hạn một class và một chuỗi cụ thể; nếu cần chèn hook theo method, hãy phân tích cấu trúc method và instruction bằng thư viện bytecode.

### 6.5. `DemoApp.java` — kiểm tra tính chất, sau đó chạy class đã instrument

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) throws Exception {
        byte[] original = Files.readAllBytes(Path.of("Target.class"));
        byte[] snapshot = original.clone();

        byte[] one = PatchTransformer.patch(original);
        if (one == null) {
            throw new AssertionError("No ORIGIN literal found");
        }

        byte[] sameInputAgain = PatchTransformer.patch(original);
        byte[] secondPass = PatchTransformer.patch(one);

        System.out.println("[test] deterministic="
                + Arrays.equals(one, sameInputAgain));
        System.out.println("[test] idempotent="
                + (secondPass == null));
        System.out.println("[test] inputUnchanged="
                + Arrays.equals(original, snapshot));

        // Lần đầu JVM dùng Target sau khi agent đã đăng ký.
        System.out.println("[app] value=" + Target.value());
    }
}
```

Ba dòng `[test]` được kiểm bằng cách gọi **hàm patch thuần** với bytes tệp `Target.class` trên đĩa. Đây là test tự chủ nhằm kiểm tra `T(B)` và `T(T(B))`, chứ **không** phải khẳng định JVM đã gọi callback ba lần.

Dòng `[app]` xác nhận đường tích hợp JVM: sau `premain`, `Target` được định nghĩa và transformer thực sự sửa literal trong class bytes dùng cho execution.

### 6.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: StableAgent
Main-Class: DemoApp

```

Hai thuộc tính đều ở **main section** và tệp kết thúc bằng một dòng trống. `Premain-Class` dùng cho `-javaagent`, còn `Main-Class` giúp chạy ứng dụng bằng `-jar`.

### 6.7. Lệnh biên dịch, đóng gói, chạy

Mở terminal trong thư mục `stable-demo/`. Dùng JDK 17+ có hỗ trợ target 17:

```bash
javac --release 17 StableAgent.java PatchTransformer.java Target.java DemoApp.java
jar --create --file stable-demo.jar --manifest agent.mf StableAgent.class PatchTransformer.class Target.class DemoApp.class
java -javaagent:stable-demo.jar -jar stable-demo.jar
```

**Stdout mong đợi trên JVM Java 17+ tương thích**:

```text
[test] deterministic=true
[test] idempotent=true
[test] inputUnchanged=true
[app] value=PATCH!
```

Lý do:

- Hai lời gọi `patch(original)` sinh **mảng byte có cùng nội dung**, dù là hai object khác nhau.
- `patch(one)` trả `null`: không cần sửa thêm, kết quả hiệu dụng sau lượt hai vẫn là `one`.
- `original` không bị chỉnh sửa vì `patch` clone trước khi ghi.
- Lúc JVM nạp `Target` từ JAR, transformer đã đăng ký sửa `ORIGIN` thành `PATCH!`, nên code thực thi trả về `PATCH!`.

`javac` và `jar` thông thường không in stdout khi thành công. Nếu chạy `java -jar stable-demo.jar` **mà bỏ `-javaagent`**, không có transformer được đăng ký và `Target.value()` sẽ trả về `ORIGIN`; tuy nhiên các kiểm tra trực tiếp với `PatchTransformer.patch` vẫn trả `true` như cũ.

### 6.8. Phạm vi của ví dụ

- Parser chỉ dùng cho class file hợp lệ từ `javac` trong demo; nó chưa kiểm tra biên mọi offset hay xử lý malformed input, attributes tùy biến hoặc mọi biến thể classfile tương lai.
- Không thể thay thế các literal tùy ý có độ dài UTF-8 khác nhau bằng cách copy bytes cùng offset; khi cần đổi độ dài phải cập nhật biểu diễn classfile đúng chuẩn.
- Bài không thể hiện method advice hoặc constructor instrumentation; trong production hãy dùng ASM/Byte Buddy với kiểm tra marker/structure đúng đắn.
- Đoạn mã minh họa **bytecode idempotence**, không chứng minh pipeline nhiều agent tự động idempotent. Phần tiếp theo nêu cách kiểm thử kết hợp.

## 7. Kiểm thử đúng tính ổn định

### 7.1. Unit/property tests cho một transformer

Với mỗi fixture `B` và cấu hình `C`:

1. Tính `x = effective(T(B, C), B)`, trong đó output `null` nghĩa là giữ nguyên input.
2. Tính `y = effective(T(B, C), B)` lần nữa từ **bản input gốc**. Xác nhận `Arrays.equals(x, y)`.
3. Tính `z = effective(T(x, C), x)`. Nếu transformer được thiết kế idempotent, xác nhận `Arrays.equals(x, z)`.
4. Kiểm tra input `B` không bị sửa.
5. Dùng ASM `CheckClassAdapter` hoặc JVM định nghĩa class để kiểm tra output hợp lệ; chỉ so sánh hash không phát hiện class sai.
6. Lặp với class có phương thức overload, constructor, annotation, generic signature, exception handler, record, lambda và các module/class loader phù hợp mục tiêu.

Đối với transformer trả `null`, một helper test có thể hiểu kết quả như sau (**đoạn minh họa, không độc lập**):

```java
static byte[] effective(byte[] input, byte[] result) {
    return result == null ? input : result;
}
```

Không làm `Arrays.equals(null, transformedBytes)` rồi kết luận transformer không idempotent; `null` mang ý nghĩa no-op hợp lệ theo hợp đồng instrumentation.

### 7.2. Integration test trên JVM thật

Đăng ký transformer ở cùng điều kiện production:

- Test load lần đầu qua `-javaagent` với artifact thật.
- Nếu hỗ trợ, test `retransformClasses` với `Can-Retransform-Classes: true` và `addTransformer(t, true)`.
- Nếu có redefine, test thêm `redefineClasses` trên class đã instrument.
- Test nhiều transformer theo **thứ tự đăng ký thực tế**, vì order và khả năng `canRetransform` quyết định bytes đầu vào của từng callback.
- Test hai class có cùng tên từ loader khác nhau, tránh cache/key bị trộn giữa classloader/module.
- Test bật/tắt cấu hình: bản nào được phép cập nhật và bản nào phải giữ nguyên.

Đo chính xác số probe trong **bytecode/trace ứng dụng**, số lần hook thực sự chạy và tính tương đương output. `transform` callback count có thể khác nhau giữa JVM/cấu hình; không lấy callback count làm bằng chứng duy nhất về idempotence.

### 7.3. Build reproducibility và đối chiếu artifact

Nếu yêu cầu output class byte-for-byte ổn định để cache, hãy cố định:

- JDK target và phiên bản ASM/Byte Buddy, rule/agent version;
- classfile input thực tế, module/class-loader context và policy;
- thứ tự transformer/visitor, serialization của metadata và cách đặt tên class/method;
- phương pháp so sánh bytes/canonical hash.

Kết quả retransform từ JVM có thể không trùng bytes của class file ban đầu vì JVM được phép tái tổ chức constant pool/attributes trong những giới hạn đặc tả. **Không so sánh hash của hai lượt callback rồi kết luận nondeterministic** nếu input thực tế đã khác. Cần log hoặc snapshot input tương ứng và kiểm tra hợp đồng một cách công bằng.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Mỗi lần build cùng source ra bytecode instrumented khác nhau | Tên helper sinh ngẫu nhiên, thứ tự duyệt map/set không cố định, metadata timestamp hoặc config thay đổi | Cố định input/config, sort cấu trúc, đặt tên deterministic, loại dữ liệu biến động khỏi output |
| Hook chạy hai lần sau khi instrument lại | Không phát hiện probe đã có hoặc chạy hai pipeline instrumentation | Kiểm tra cấu trúc/marker, chỉ chèn một lần, kiểm thử `T(T(B))` |
| Transformer trả `byte[0]` để báo không sửa | Hiểu sai API | Trả `null` khi no-op; mảng rỗng không phải classfile hợp lệ |
| Có test deterministic nhưng output tăng hook mỗi lần | Determinism không suy ra idempotence | Test riêng tính chất `T(T(B)) = T(B)` |
| Hai transformer đều idempotent nhưng pipeline vẫn thay đổi tiếp | Phép hợp thành chưa chắc idempotent hoặc hai agent rewrite cùng vị trí | Test đúng order, thiết lập ownership/precondition, xem xét canonicalization |
| Retransform không gọi một transformer | Transformer đăng ký `canRetransform=false` | JVM reuse output cũ; chỉ transformer `true` được callback khi retransform |
| Hai lần callback thấy byte array khác dù source không đổi | JVM có thể cung cấp bytes khác ở lượt retransform; transformer trước cũng có thể thay bytes | Đo input tại mỗi callback và xét cả pipeline, không so raw hash của những input khác nhau |
| `VerifyError`/`ClassFormatError` | Sinh method/stack map/constant pool không hợp lệ | Kiểm tra classfile version, verify bytecode, dùng thư viện phù hợp và tests |
| Classloader leak sau instrumentation | Cache giữ mạnh `ClassLoader` hoặc `Class<?>` của plugin đã dỡ | Dùng key/lifecycle phù hợp, giải phóng cache, cân nhắc weak references khi an toàn |
| Thay đổi dữ liệu chỉ vì log callback | Transformer phụ thuộc counter, current time hoặc kết quả I/O | Tách telemetry khỏi input quyết định output, snapshot policy bất biến |
| Lượt đầu không đổi, lượt sau mới thêm hook | Marker chưa đồng bộ, rule phụ thuộc state mutable hoặc transformer A/B đổi order | Làm rõ trạng thái, hiệu lực của rule, thứ tự pipeline và preconditions |

## 9. Checklist cho một chuỗi transformer ổn định

1. **Định nghĩa input đầy đủ**: classfileBuffer, class name/loader/module và phiên bản cấu hình có thể ảnh hưởng output.
2. **Deterministic**: cùng input và context bất biến sinh cùng bytecode hoặc cùng ngữ nghĩa theo hợp đồng; không dùng random/time/counter làm nguồn tên helper.
3. **Idempotent theo yêu cầu**: sau khi gắn hook một lần, lượt chạy nữa không gắn thêm; có dấu hiệu đáng tin để nhận diện instrumented code.
4. **No-op đúng chuẩn**: khi không đổi thì `return null`, không mutate input array.
5. **Composition**: test đầy đủ với nhiều transformer theo đúng thứ tự và kiểm soát các marker/hook của từng agent.
6. **Retransform hiểu đúng**: phân biệt transformer `canRetransform=false` được reuse với transformer `true` được gọi lại; không giả định luôn nhận output của lần gọi trước.
7. **Classfile hợp lệ**: giữ giới hạn JVM, schemas, stack frames, class version và bytecode verifier.
8. **Side effects có kiểm soát**: logging và resource registration không nhân đôi không chủ đích; rollback/de-registration rõ ràng.
9. **Quan sát lỗi thực tế**: đo lỗi verify/linkage, số hook thực thi, overhead, và ảnh hưởng khi có nhiều agent.
10. **Integration test trên runtime đích**: classloader/module, build tool, retransform và class file do JVM cung cấp.

## 10. Câu hỏi tự kiểm tra

**Câu 1:** `T(x)` luôn chèn `trace()` trước code hiện có, không dùng random. T deterministic không?

**Đáp án:** Có, nếu mọi input và rule cố định. Nhưng không idempotent vì `T(T(x))` sẽ chèn hai hook.

**Câu 2:** `transform` trả `null` khi class đã có marker. Có vi phạm idempotence do output Java trả về khác kiểu không?

**Đáp án:** Không. Theo API, `null` biểu thị giữ nguyên bytes nhận vào. Xét **output hiệu dụng** thì có thể hoàn toàn idempotent.

**Câu 3:** Cùng một transformer được đăng ký `canRetransform=false` và JVM gọi `retransformClasses`. JVM có gọi lại callback không?

**Đáp án:** Không. Theo hợp đồng, kết quả trước của transformer không có khả năng retransform được áp lại mà không gọi callback.

**Câu 4:** Hai transformer A và B đều idempotent riêng rẽ. Có thể khẳng định `B ∘ A` idempotent không?

**Đáp án:** Không. Phải test cả pipeline và thứ tự thực thi; hai phép idempotent vẫn có thể kết hợp thành phép không idempotent.

**Câu 5:** Cùng một class và rule nhưng `classfileBuffer` ở lượt retransform khác thứ tự constant pool so với lượt load đầu. Hash khác có chứng minh transformer nondeterministic không?

**Đáp án:** Không. Đầu vào **đã khác**; cần so sánh kết quả với **cùng input bytes**, cùng ngữ cảnh và cùng phiên bản thuật toán, hoặc kiểm tra ngữ nghĩa/canonical output theo hợp đồng.

## 11. Tài liệu chuẩn

- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): chuỗi biến đổi, thứ tự, `return null`, không sửa `classfileBuffer`, semantics khi retransform/redefine.
- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, capability và việc tái sử dụng kết quả transformer `false`.
- [Java Virtual Machine Specification SE 17 — Chapter 4, The class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool, `CONSTANT_Utf8`, Long/Double chiếm hai index và giới hạn class file.
- [ASM — User Guide / API](https://asm.ow2.io/): hướng tiếp cận thực tế khi cần rewrite bytecode, kiểm tra structure và frames.
- [Byte Buddy — project documentation](https://bytebuddy.net/): API instrumentation có khả năng tạo advice và matcher chuyên biệt.

**Ghi nhớ:** **Deterministic** nghĩa cùng input/context cho cùng output; **idempotent** nghĩa xử lý lại output không tạo thêm biến đổi; **repeat-safe** còn bao gồm side effects và tương tác giữa nhiều transformer. Khi JVM retransform, callback **không bắt buộc** nhận output của lần trước, nên hãy kiểm thử cả hàm biến đổi thuần lẫn pipeline instrumentation thực tế.
