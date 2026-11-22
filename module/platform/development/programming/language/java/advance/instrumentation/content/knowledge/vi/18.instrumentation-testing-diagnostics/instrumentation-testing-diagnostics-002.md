# Biến đổi byte trong bài kiểm thử trước khi cài Java agent vào JVM thử nghiệm

## 1. Mục tiêu: kiểm thử bộ biến đổi bytecode trước, cài agent sau

Một Java agent dùng `ClassFileTransformer` để thay đổi class-file bytes trước khi JVM định nghĩa hoặc cập nhật một class. Sai sót trong logic này có thể gây `ClassFormatError`, `VerifyError`, `LinkageError`, class-loading recursion, khác biệt module/loader hoặc hành vi không như dự kiến. Nếu chỉ kiểm tra bằng cách khởi động cả ứng dụng với `-javaagent`, một lỗi nhỏ có thể làm **JVM thử nghiệm không khởi động được**, còn log từ class loading khiến khó xác định lỗi nằm ở thuật toán, cấu hình agent hay runtime.

Một chiến lược tốt là **tách logic biến đổi class file thành phần có thể chạy trực tiếp trong bài kiểm thử**, rồi kiểm tra kết quả trước khi cho agent tác động đến JVM thử nghiệm:

1. **Kiểm thử biến đổi byte offline:** đọc một `.class` đã biên dịch thành `byte[]`, gọi transformer hoặc hàm biến đổi trực tiếp, kiểm tra bytes đầu vào không bị sửa, output đúng và no-op trả `null`.
2. **Kiểm tra tính hợp lệ và hành vi:** phân tích/disassemble output, dùng class loader cô lập trong một bài test JVM hoặc một JVM con có `-Xverify:all` để xác minh class mới có thể được định nghĩa, liên kết và chạy theo kỳ vọng.
3. **Kiểm thử tích hợp agent:** chỉ sau hai bước trên, đóng gói JAR có `Premain-Class` rồi khởi chạy JVM riêng với `-javaagent`, kiểm tra callback thật, loader/module, thứ tự transformer và behavior.
4. **Kiểm thử môi trường giống production:** xác nhận bootstrap/module visibility, multiple loaders, redefine/retransform, concurrency và chi phí vận hành nếu tính năng sử dụng những khả năng đó.

**Điều phải phân biệt:** gọi `transform(...)` như một phương thức Java thông thường **không phải** JVM instrumentation. Offline test mô phỏng những đối số, bytes và tình huống bạn chủ động cung cấp; nó không chứng minh JVM đã đăng ký/cấp capability cho agent, cũng không tự kiểm tra mọi điều kiện runtime.

Bài thuộc mục **Kiểm thử và chẩn đoán** của Java Advance — Instrumentation, trình bày quy trình, các lớp kiểm thử, cách phát hiện lỗi sớm, ví dụ runnable Java 17 hoàn chỉnh và checklist trước khi cài agent vào JVM thử nghiệm.

## 2. Hợp đồng đầu vào/đầu ra của transformer cần kiểm thử

Trên Java 17, `ClassFileTransformer` có overload sáu tham số:

```java
default byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
        throws IllegalClassFormatException;
```

Đoạn trên chỉ trích chữ ký, cần import `java.security.ProtectionDomain` và `java.lang.instrument.IllegalClassFormatException`.

Những trường cần hiểu:

| Tham số/giá trị | Khi JVM thật gọi | Khi test offline gọi trực tiếp |
| --- | --- | --- |
| `module` | Module runtime chứa class được biến đổi | Có thể truyền đối tượng Module thích hợp; `null` trong demo chỉ là **ngữ cảnh giả lập**, không đại diện unnamed module |
| `loader` | Defining class loader; `null` cho bootstrap | Có thể cung cấp loader mô phỏng; `null` trong demo không chứng minh target do bootstrap định nghĩa |
| `className` | JVM internal name, ví dụ `demo/Greeter` | Test phải cung cấp **đúng dạng slash**; không nhầm `demo.Greeter` |
| `classBeingRedefined` | `null` cho initial load; non-null khi redefine/retransform | `null` mô phỏng initial-load path; không cho thấy JVM đã load class nào |
| `protectionDomain` | Domain của class đang định nghĩa/cập nhật | Có thể là `null` trong unit test nếu rule không cần; điều này không kiểm thử protection domain |
| `classfileBuffer` | Toàn bộ class-file bytes hiện tại trong chuỗi transformer | Đọc từ file `.class` hoặc từ emitter; **không phải nội dung `.java`/JAR** |
| Giá trị trả về `null` | Không biến đổi bytes ở bước này | Unit test khẳng định no-op đúng hợp đồng |
| Giá trị trả về `byte[]` | Mảng classfile mới, JVM/transformer sau sẽ xử lý | Test kiểm tra tính toàn vẹn, cấu trúc và behavior của mảng |

**Quy tắc quan trọng của Javadoc Java 17:**

- Không sửa `classfileBuffer` trực tiếp; nếu có biến đổi, trả **một mảng byte mới**.
- Không cần biến đổi thì trả **`null`**, không trả `new byte[0]` hoặc thay bằng bản clone vô ích.
- Transformer phải sinh class file hợp lệ cho JVM mục tiêu. Không được chỉ sửa code mà bỏ qua constant pool, method descriptors, exception table hoặc stack map frames nếu chúng bị ảnh hưởng.
- Các transformer **được xâu chuỗi**; bytes của transformer trước làm input cho transformer sau. Một unit test một transformer không chứng minh toàn bộ pipeline đúng.
- Exception từ transformer không đương nhiên chặn class loading; JVM có thể tiếp tục gọi transformer sau và thử định nghĩa class với bytes trước đó.
- Với `redefineClasses`/`retransformClasses`, còn có những giới hạn về thay đổi schema/field/method/hierarchy.

Trong Java 17, cả dạng năm và sáu tham số đều có default implementation, nên `ClassFileTransformer` **không phải functional interface**. Không viết `ClassFileTransformer t = (...) -> ...`; dùng class/anonymous class có `@Override`.

## 3. Ranh giới của ba lớp kiểm thử

### 3.1. Kiểm thử hàm biến đổi byte thuần

Có thể trích lõi biến đổi thành một hàm gần như thuần:

```java
static byte[] transformBytes(
        String internalName, byte[] originalBytes)
        throws IllegalClassFormatException {
    // Lọc đúng class, parse input, tạo output khi có thay đổi.
    // Nếu không sửa, trả null.
}
```

Đây là chữ ký minh họa, chưa phải chương trình đầy đủ. Với cùng input bytes, cùng rule và cùng cấu hình bất biến, output hiệu dụng nên **xác định** (deterministic). Test có thể kiểm tra:

- **Target match:** class mong muốn được sửa.
- **Non-target:** trả `null`, không sửa input.
- **Input immutable:** snapshot ban đầu vẫn bằng bytes sau gọi.
- **No-op/idempotence:** chạy lại trên bytes đã được patch không tạo thay đổi trùng.
- **Negative input:** malformed bytes bị phát hiện thay vì truy cập mảng ngoài phạm vi.
- **Output valid:** parser/VM có thể nhận class file mới.
- **Behavior:** method sau biến đổi trả kết quả đúng.

**Ưu điểm:** nhanh, dễ lặp nhiều lần và khi thất bại có thể giữ lại input/output để phân tích; không phải restart cả ứng dụng.

### 3.2. Kiểm tra bằng class loader riêng trong test JVM

Có thể tạo một subclass của `ClassLoader` và gọi `defineClass(String binaryName, byte[], ...)` trên output. JVM thực sự **define** class từ bytes đó, vì thế kiểm tra được nhiều lỗi class-file/verification/linkage và có thể gọi method qua reflection.

Nhưng lưu ý đây **vẫn là một JVM thực thi bài test**: nó không hoàn toàn “không động tới JVM”. Cái **không** xảy ra là cài/register Java agent lên JVM thử nghiệm; lớp được định nghĩa **cô lập trong loader riêng của test runner**.

Hai bước không thay thế nhau:

- Parser/test thuần phát hiện lỗi logic transform.
- Class loader cô lập xác nhận một phần khả năng JVM dùng bytes mới.

Nếu class phụ thuộc vào native libraries, security domain đặc biệt, module reads/exports, bootstrap helpers hoặc plugin loader, loader cô lập **không** tái hiện tự động tất cả điều kiện đó. Cần JVM tích hợp riêng.

### 3.3. Kiểm thử thực tế với `-javaagent`

Chỉ trong JVM được khởi động với:

```bash
java -javaagent:patch-agent.jar -cp ... Main
```

JVM mới thực hiện quy trình nạp agent, gọi `premain`, đăng ký transformer qua `Instrumentation.addTransformer` và gọi `transform` với **module/loader/domain thực**. Test này phát hiện thêm các vấn đề về manifest, classpath, module graph, class loading order, quyền truy cập, helper dependencies và agent startup.

Nên có cả:

- **Negative control:** chạy cùng ứng dụng **không** `-javaagent`, kết quả chưa bị patch.
- **Positive control:** chạy với `-javaagent`, kết quả đã patch.
- **Verifier run:** thêm `-Xverify:all` trên JVM test khi phù hợp.
- **Isolation:** dùng process riêng, thời gian chạy giới hạn, thu stdout/stderr và exit code; không đụng JVM production.

### 3.4. Bảng kiểm thử theo chi phí và phạm vi

| Lớp kiểm thử | Có cài agent? | Bắt được gì? | Không chứng minh được |
| --- | --- | --- | --- |
| Kiểm tra pure byte[] | Không | Rule matching, bytes, determinism, no-op, input unchanged | JVM accept output, real loader/module |
| Kiểm tra `javap`/bytecode parser | Không | Constant pool/methods/attributes, structural differences | Toàn bộ runtime linkage/behavior |
| `defineClass` trong isolated loader | Không | JVM define/verify, gọi method đơn giản, binary name | JPMS/agent registration/production loader semantics |
| JVM con `-Xverify:all` dùng output bytes | Không bắt buộc | Class verification và hành vi khi chạy file mới | Callback do agent thật gọi |
| JVM con `-javaagent` | **Có** | Manifest, `premain`, callback, loader/module thực, behavior | Production traffic, nhiều agent/version/layers |
| Staging giống production | Có | Multi-loader, multi-module, concurrency, compatibility/overhead | Bảo đảm mọi workload thật đều có cùng kết quả |

Mục tiêu không phải xóa mọi rủi ro bằng một unit test, mà là **đẩy lỗi đơn giản về lớp test rẻ nhất** trước khi khởi động hệ thống phức tạp.

## 4. Chuẩn bị fixture: class gốc phải đúng artifact mục tiêu

Trước khi test, hãy **biên dịch một class Java thành full class-file bytes**:

```bash
javac --release 17 -d build/classes src/demo/Greeter.java
```

Sau đó file cần đọc là:

```text
build/classes/demo/Greeter.class
```

**Không dùng:**

- Nội dung của `src/demo/Greeter.java` (UTF-8 source text).
- Toàn bộ `.jar`/ZIP chứa class.
- Mã của một method riêng lẻ thay cho file `.class`.
- File class cùng tên nhưng **khác loader/module/build version** nếu muốn tái hiện lỗi thực.
- Một bản bytecode khác với bytes mà transformer sẽ thực sự nhận sau các transformer đứng trước nó.

Khi JVM có nhiều transformers, **thứ tự** có ảnh hưởng: output của transformer A có thể là input của B, nên test của B cần cả fixture cơ sở và fixture đã qua A. Unit test với input được chọn tùy tiện có thể bỏ sót lỗi composition.

### 4.1. Mốc kiểm tra artifact

Trong CI có thể lưu:

- File path từ build artifact và hash SHA-256.
- Class-file major version; Java 17 có major version **61**.
- JVM target và `javac --release`.
- Binary name `demo.Greeter` và internal name `demo/Greeter`.
- Module/loader namespace nếu rule phụ thuộc.
- Cấu hình transformer và bản dependency parser/writer.
- Đầu ra `javap` hoặc báo cáo verifier khi lỗi.

Không dùng một hash output **duy nhất** làm bằng chứng đúng trong mọi build: debug attributes, line numbers hoặc compiler options có thể thay classfile bytes mà không đổi behavior. Hash giúp **xác định artifact đã thử**, còn correctness cần assertions/verification.

## 5. Tạo một transformer Java 17 dễ kiểm thử

Ví dụ dùng một phép sửa nhỏ, có thể tái lập: đổi constant-pool UTF8 literal `"BEFORE"` thành `"AFTER!"` trong class `demo/Greeter`.

Hai chuỗi đều dài **6 byte ASCII**, nên phép patch giữ nguyên độ dài của `CONSTANT_Utf8` và các offsets sau đó. Đây là **fixture cố tình giới hạn** để tập trung vào quy trình kiểm thử; trong agent thật, các phép biến đổi instruction, annotation, signature hoặc stack frame phức tạp phải dùng ASM/Byte Buddy hay Java Class-File API trên JDK 24+.

### 5.1. Cấu trúc dự án

```text
offline-transform-lab/
├── agent.mf
└── src/
    ├── demo/
    │   └── Greeter.java
    ├── BytePatchTransformer.java
    ├── OfflineCheck.java
    ├── PatchAgent.java
    └── AgentApp.java
```

Tất cả code tương thích **Java 17**. Không cần Maven/Gradle hoặc JUnit để chạy bài thử này, dù trong dự án thực có thể chuyển assertions sang JUnit 5.

### 5.2. File `src/demo/Greeter.java`

```java
package demo;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "BEFORE";
    }
}
```

Bản gốc có một method public static trả chuỗi `BEFORE`. Chúng ta sẽ **không biên dịch source phiên bản khác**: toàn bộ thay đổi sẽ được thực hiện trực tiếp trên mảng bytes của `Greeter.class`.

### 5.3. File `src/BytePatchTransformer.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class BytePatchTransformer
        implements ClassFileTransformer {

    private static final byte[] OLD =
            "BEFORE".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] NEW =
            "AFTER!".getBytes(StandardCharsets.US_ASCII);

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer)
            throws IllegalClassFormatException {

        // Bỏ qua mọi class khác và các callback redefine/retransform.
        if (!"demo/Greeter".equals(className)
                || classBeingRedefined != null) {
            return null;
        }

        // Lõi không phụ thuộc Instrumentation hay global JVM state.
        return patchConstantPool(classfileBuffer);
    }

    private static byte[] patchConstantPool(byte[] input)
            throws IllegalClassFormatException {

        if (input == null || input.length < 10) {
            throw new IllegalClassFormatException(
                    "Missing/truncated class file");
        }

        if ((input[0] & 255) != 0xCA
                || (input[1] & 255) != 0xFE
                || (input[2] & 255) != 0xBA
                || (input[3] & 255) != 0xBE) {
            throw new IllegalClassFormatException(
                    "Invalid CAFEBABE magic");
        }

        int poolCount = u2(input, 8);
        int p = 10;
        byte[] output = null;

        for (int i = 1; i < poolCount; i++) {
            require(input, p, 1);
            int tag = input[p++] & 255;

            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int length = u2(input, p);
                    p += 2;
                    require(input, p, length);

                    if (length == OLD.length
                            && equalsAt(input, p, OLD)) {
                        // Không bao giờ sửa input buffer tại chỗ.
                        if (output == null) {
                            output = input.clone();
                        }
                        System.arraycopy(
                                NEW, 0, output, p, NEW.length);
                    }
                    p += length;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 -> {
                    require(input, p, 4);
                    p += 4;
                }
                case 5, 6 -> { // Long/Double chiếm hai pool slots.
                    require(input, p, 8);
                    p += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> {
                    require(input, p, 2);
                    p += 2;
                }
                case 15 -> {
                    require(input, p, 3);
                    p += 3;
                }
                default -> throw new IllegalClassFormatException(
                        "Unsupported constant-pool tag: " + tag);
            }
        }

        // null có nghĩa không có literal cần thay đổi.
        return output;
    }

    private static int u2(byte[] input, int position)
            throws IllegalClassFormatException {
        require(input, position, 2);
        return ((input[position] & 255) << 8)
                | (input[position + 1] & 255);
    }

    private static void require(
            byte[] input, int position, int length)
            throws IllegalClassFormatException {
        if (position < 0 || length < 0
                || position > input.length - length) {
            throw new IllegalClassFormatException(
                    "Truncated constant pool");
        }
    }

    private static boolean equalsAt(
            byte[] input, int at, byte[] pattern) {
        // Caller đã kiểm tra bound cho UTF8 entry.
        for (int j = 0; j < pattern.length; j++) {
            if (input[at + j] != pattern[j]) {
                return false;
            }
        }
        return true;
    }
}
```

**Giải thích cấu trúc và giới hạn:**

- Filter `className` dùng JVM internal name với dấu `/`; `"literal".equals(className)` an toàn khi `className == null`.
- `classBeingRedefined != null` bị bỏ qua trong demo để tập trung **initial load**. Production muốn hỗ trợ redefine/retransform cần một rule tương thích với schema và lifecycle riêng.
- `patchConstantPool` là logic xử lý bytes, có thể gọi trực tiếp thông qua `transform` trong unit test mà không có `Instrumentation`.
- Input được validate ở header và khi duyệt từng constant-pool entry; mảng input **không bị mutate**.
- Chỉ khi tìm thấy `BEFORE` mới `clone`; nếu không match trả `null`.
- Khi gọi lại trên output chứa `AFTER!`, không còn entry `BEFORE` nên kết quả thứ hai là `null`: phép patch **idempotent theo nghĩa hiệu dụng** trên fixture này.
- Parser đọc những tag constant pool trong Java 17. Nó **không** chứng minh full class validity, không kiểm tra mọi attributes/methods, và không phải thư viện xử lý classfile bất kỳ. Thay literal trên fixture có độ dài bằng nhau không cần chỉnh instruction offsets, stack map frames hay descriptors.
- Nếu class khác có cùng internal name trong loader khác, filter theo tên đơn thuần có thể patch class đó: demo chạy trong môi trường cô lập; sản phẩm thật nên xét loader/module/artifact nếu yêu cầu.
- Không gọi `Class.forName`/reflection trong callback, tránh loading chính class đang được JVM định nghĩa.
- Callback trả exception theo contract `IllegalClassFormatException` khi thấy classfile không hợp lệ; **JVM không bị buộc abort** chỉ vì transformer ném exception này. Unit test trực tiếp có thể quan sát exception nhưng integration phải kiểm tra JVM behavior riêng.

## 6. Viết unit test offline kiểm tra chính bytes và hành vi

### 6.1. File `src/OfflineCheck.java`

```java
import java.lang.instrument.IllegalClassFormatException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public final class OfflineCheck {
    private OfflineCheck() {
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class IsolatedLoader extends ClassLoader {
        IsolatedLoader() {
            // Chỉ delegate tới bootstrap; không lấy Greeter từ app classpath.
            super(null);
        }

        Class<?> define(String binaryName, byte[] bytes) {
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    private static String invokeMessage(byte[] bytes)
            throws Exception {

        // Mỗi lần dùng một defining loader mới:
        // hai phiên bản cùng binary name không đụng identity.
        Class<?> type = new IsolatedLoader().define(
                "demo.Greeter", bytes);

        Method method = type.getMethod("message");
        return (String) method.invoke(null);
    }

    public static void main(String[] args) throws Exception {
        check(args.length == 1,
                "Usage: OfflineCheck <Greeter.class>");

        Path inputFile = Path.of(args[0]);
        byte[] original = Files.readAllBytes(inputFile);
        byte[] snapshot = original.clone();
        BytePatchTransformer transformer =
                new BytePatchTransformer();

        // 1. Non-target phải no-op.
        byte[] unrelated = transformer.transform(
                null, null, "other/Name",
                null, null, original);
        check(unrelated == null,
                "Unrelated class should be ignored");

        // 2. Target phải sinh một mảng bytes MỚI.
        byte[] changed = transformer.transform(
                null, null, "demo/Greeter",
                null, null, original);
        check(changed != null, "Target was not patched");
        check(changed != original,
                "Output must not alias original input");
        check(!Arrays.equals(changed, original),
                "Output bytes must differ from input");

        // 3. Buffer gốc không bị thay đổi.
        check(Arrays.equals(original, snapshot),
                "Transformer mutated original bytes");

        // 4. Idempotence: patch lần 2 là no-op.
        byte[] repeated = transformer.transform(
                null, null, "demo/Greeter",
                null, null, changed);
        check(repeated == null,
                "Repeated patch must be no-op");

        // 5. JVM test định nghĩa 2 class trong 2 loaders cô lập.
        String before = invokeMessage(original);
        String after = invokeMessage(changed);
        check("BEFORE".equals(before),
                "Unexpected original behavior");
        check("AFTER!".equals(after),
                "Unexpected transformed behavior");

        // 6. Malformed classfile: unit call phải báo lỗi.
        boolean rejected = false;
        try {
            transformer.transform(
                    null, null, "demo/Greeter",
                    null, null, new byte[]{1, 2, 3});
        } catch (IllegalClassFormatException expected) {
            rejected = true;
        }
        check(rejected, "Invalid bytes were not rejected");

        // 7. Ghi output để javap và JVM con kiểm tra tiếp.
        Path outputFile =
                Path.of("build/rewritten/demo/Greeter.class");
        Files.createDirectories(outputFile.getParent());
        Files.write(outputFile, changed);

        System.out.println("[offline] nonTarget=null");
        System.out.println("[offline] inputUnchanged=true");
        System.out.println("[offline] changed=true");
        System.out.println("[offline] repeat=null");
        System.out.println("[offline] before=" + before);
        System.out.println("[offline] after=" + after);
        System.out.println("[offline] invalid=rejected");
        System.out.println("[offline] PASS");
    }
}
```

### 6.2. Những assertion thật sự chứng minh điều gì?

| Kiểm tra | Chứng minh | Không chứng minh |
| --- | --- | --- |
| `unrelated == null` | Rule không patch một tên class khác | Agent không patch những class khác trên JVM thật do cấu hình khác |
| `changed != original` | Output là mảng khác object | Output là class file hợp lệ |
| `!Arrays.equals(changed, original)` | Có byte-level change | Thay đổi đó là điều bạn muốn |
| `Arrays.equals(original, snapshot)` | Input array được giữ nguyên | Code không giữ reference input trong cache |
| `repeated == null` | Với fixture này, patch lần hai no-op | Mọi transformer trong pipeline đều idempotent |
| `invokeMessage(original)` trả `BEFORE` | JVM có thể định nghĩa và gọi bản gốc | JVM production nạp đúng loader/module này |
| `invokeMessage(changed)` trả `AFTER!` | JVM có thể define/link/invoke output trong test loader | Agent đã chạy, hoặc mọi method/exception path đều đúng |
| Invalid bytes bị từ chối | Parser phát hiện một classfile lỗi rõ ràng | Parser xử lý an toàn mọi input malformed |
| Output được viết ra `build/rewritten` | Artifact để inspect ở bước kế tiếp | Tự cài bytes lên JVM thử nghiệm |

**Điểm đáng chú ý:** `ClassLoader#defineClass` nhận **binary name** `demo.Greeter`, khác `className` callback là **internal name** `demo/Greeter`. Trong test, nhầm hai dạng này có thể gây `NoClassDefFoundError` hoặc test không đi đúng code path.

### 6.3. Tại sao mỗi phiên bản dùng một loader?

Trong một JVM, **cùng binary name không thể được define hai lần trong cùng defining loader**. Nếu bạn gọi `defineClass("demo.Greeter", ...)` hai lần trên cùng loader, lượt thứ hai có thể ném `LinkageError` vì duplicate definition. Hai phiên bản trong `OfflineCheck` dùng **hai IsolatedLoader instances** khác nhau, nên không phải duplicate class identity.

Cách này thích hợp khi thử raw bytes nhưng **không tương đương `Instrumentation.redefineClasses`**: redefinition thay thân method trong class identity đã tồn tại, còn loader cô lập tạo class identity mới. Nếu muốn kiểm thử redefinition, phải chạy một bài tích hợp có capability đúng.

## 7. Lệnh chạy unit test offline với JDK 17

### 7.1. Biên dịch

Từ thư mục gốc `offline-transform-lab/`:

```bash
mkdir -p build/classes

javac --release 17 -d build/classes \
  src/demo/Greeter.java \
  src/BytePatchTransformer.java \
  src/OfflineCheck.java \
  src/PatchAgent.java \
  src/AgentApp.java
```

Phần test **không cài agent**. `PatchAgent.java` và `AgentApp.java` được định nghĩa ở phần 9; có thể biên dịch đủ năm file từ đầu để chạy các bước theo đúng thứ tự.

### 7.2. Chạy trực tiếp bộ test

```bash
java -cp build/classes OfflineCheck \
  build/classes/demo/Greeter.class
```

**Stdout mong đợi, khi bài test PASS:**

```text
[offline] nonTarget=null
[offline] inputUnchanged=true
[offline] changed=true
[offline] repeat=null
[offline] before=BEFORE
[offline] after=AFTER!
[offline] invalid=rejected
[offline] PASS
```

Nếu một assertion thất bại, chương trình ném `AssertionError` và tiến trình thoát với nonzero status. Không có dòng `PASS` là tín hiệu test chưa qua. Không bắt mọi exception để in `PASS` bằng mọi giá.

Lệnh `OfflineCheck` **không có `-javaagent`**. JVM vẫn thực thi bytecode của test runner và định nghĩa hai bản class trong isolated loaders, nhưng **không có `premain` và không đăng ký transformer**: đó là khác biệt chính với integration test.

### 7.3. Đọc class file gốc và output

`OfflineCheck` lưu:

```text
build/rewritten/demo/Greeter.class
```

Lệnh kiểm tra:

```bash
javap -v -p build/classes/demo/Greeter.class
javap -v -p build/rewritten/demo/Greeter.class

javap -c -p build/classes/demo/Greeter.class
javap -c -p build/rewritten/demo/Greeter.class
```

Trong output gốc, constant pool chứa literal `BEFORE`; trong output mới, literal tương ứng là `AFTER!`. Method `message()` vẫn có dạng `ldc` + `areturn` với constant phù hợp; indices có thể khác tùy build/JDK.

**Đừng so sánh toàn bộ stdout của `javap` từng byte** giữa hai build khác nhau: constant pool indexes, debug attributes hoặc line numbers có thể khác. Trong demo, bytes mới sinh trực tiếp từ bytes cũ và thay một constant-pool entry cùng độ dài, nên khác biệt dự kiến được giới hạn rất rõ.

### 7.4. Xác minh trong một JVM con có bật verifier

```bash
java -Xverify:all \
  -cp "build/rewritten:build/classes" AgentApp
```

**Stdout:**

```text
[agent-jvm] message=AFTER!
```

Lệnh **không dùng `-javaagent`**. Vì `build/rewritten` đứng trước `build/classes` trong classpath, system loader của JVM con tìm `demo.Greeter` từ bytes đã patch; `AgentApp` nằm ở `build/classes`. Việc chạy với `-Xverify:all` giúp kiểm tra verification trong môi trường JVM thật, nhưng không có nghĩa đã chứng minh mọi đường method, ngoại lệ, module hoặc runtime composition đều đúng.

Lệnh đối chứng chỉ dùng output gốc:

```bash
java -Xverify:all -cp build/classes AgentApp
```

**Stdout đối chứng:**

```text
[agent-jvm] message=BEFORE
```

**Ghi chú:** không nên giả định rằng lựa chọn verification flags trên tất cả JVM/versions đều có tác dụng hệt nhau, và class được verify mà không có lỗi không chứng minh business logic đúng. Assertion hành vi và integration tests vẫn cần thiết.

## 8. Khi nào dùng ASM, Byte Buddy hoặc Java Class-File API?

Bộ patch raw bytes ở đây được giới hạn vào **constant-pool UTF8 cùng độ dài**. Nếu biến đổi thực tế của bạn là chèn method-entry advice, thay invoke instructions, sửa exceptions, annotations, bootstrap methods hoặc frames, hãy sử dụng công cụ hiểu cấu trúc class file.

| Công cụ | Điểm mạnh | Cần lưu ý |
| --- | --- | --- |
| **ASM** | Đọc/ghi class file mức thấp, visitors, tree API, frames, `CheckClassAdapter` | Chọn version hỗ trợ classfile target; hiểu `COMPUTE_FRAMES` và hierarchy resolution |
| **Byte Buddy** | Khai báo behavior/advice ở mức cao, có testing tiện hơn | Vẫn chịu giới hạn JVM instrumentation, class loader và helper visibility |
| **Java Class-File API (JDK 24+)** | API chuẩn JDK `java.lang.classfile`; đọc/viết/verify class models | **Không có trong Java 17**; phải dùng đúng target JDK |
| **`javap` + JVM verifier** | Có sẵn trong JDK, dễ inspect/kiểm tra artifact | Không phải replacement cho semantic assertions |
| **Unit test transformer thuần** | Chạy nhanh, cô lập lỗi logic và byte-level invariants | Không xác nhận agent lifecycle hoặc module graph |

### 8.1. Kiểm thử output với ASM nếu dự án đã dùng ASM

Với ASM, có thể dùng `org.objectweb.asm.util.CheckClassAdapter` để kiểm tra cấu trúc bytecode, đồng thời JVM verifier cho hành vi thực tế. Đặt compiler/bytecode library dependencies ở **test scope** nếu runtime agent không cần chúng, hoặc đóng gói/shade đúng trong agent nếu production cần.

Ví dụ định hướng (không phải chương trình độc lập và cần các JAR ASM tương thích):

```java
ClassReader reader = new ClassReader(transformedBytes);
CheckClassAdapter.verify(reader, false, printWriter);
```

`transformedBytes` là full class-file output; `printWriter` là `PrintWriter` được thiết lập trong bài test. Chỉ kiểm tra bằng một verifier/library vẫn chưa thay thế test JVM thực nếu code phụ thuộc loader/module hoặc runtime APIs.

### 8.2. Stack maps và control flow

Khi chèn instructions/try-finally:

- Cập nhật branch offsets, max stack/max locals và exception tables.
- Bảo toàn hoặc tính lại `StackMapTable` cho JVM target.
- Kiểm tra constructor `<init>` và initialization rules.
- Không quên `normal exit` lẫn `exceptional exit` khi chèn timer.
- Test synchronized method/`monitorenter`/`monitorexit` để không phá monitor balance.
- Chọn resolver hierarchy không kích hoạt class loading sai namespace khi tính frames.

Không nên chấp nhận lời khuyên “chỉ cần `COMPUTE_FRAMES` là luôn đúng” nếu hierarchy resolver đang dùng sai loader hoặc vô tình nạp classes mới. Cần test với namespace/môi trường thật.

## 9. Chỉ sau offline PASS: đóng agent JAR và chạy JVM tích hợp

Để kiểm tra **callback thật** thay vì gọi tay, ta dùng lại `BytePatchTransformer`.

### 9.1. File `src/PatchAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class PatchAgent {
    private PatchAgent() {
    }

    public static void premain(
            String agentArgs, Instrumentation inst) {

        // JVM sẽ gọi transform(...) khi class mục tiêu được define.
        inst.addTransformer(new BytePatchTransformer(), false);
    }
}
```

Agent chỉ cần transform lúc class load mới; vì vậy **không cần** `Can-Redefine-Classes` hoặc `Can-Retransform-Classes` trong manifest. Registration với `canRetransform=false` vẫn cho phép callback ở initial load.

### 9.2. File `src/AgentApp.java`

```java
import demo.Greeter;

public final class AgentApp {
    private AgentApp() {
    }

    public static void main(String[] args) {
        System.out.println(
                "[agent-jvm] message=" + Greeter.message());
    }
}
```

Đây là ứng dụng cực nhỏ chỉ tải `demo.Greeter` khi chạy, sau `premain`. Nó không tự gọi `BytePatchTransformer.transform`. Nếu JVM gọi callback đúng, `message()` đổi từ `BEFORE` sang `AFTER!`.

### 9.3. File `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: PatchAgent

```

Đây là manifest của agent JAR; có **dòng trống cuối main section**. Tên `PatchAgent` phải trùng binary name của class chứa `premain`.

### 9.4. Tạo JAR sau khi unit tests đã PASS

```bash
jar --create --file patch-agent.jar \
  --manifest agent.mf \
  -C build/classes PatchAgent.class \
  -C build/classes BytePatchTransformer.class

jar --list --file patch-agent.jar
```

JAR cần chứa `PatchAgent.class`, `BytePatchTransformer.class` và `META-INF/MANIFEST.MF`. Ví dụ transformer không có anonymous/nested helper; nếu agent thật có các class/helper khác, phải đóng gói đủ dependencies.

### 9.5. Đối chứng và chạy với agent

**Không có agent:**

```bash
java -cp build/classes AgentApp
```

**Stdout:**

```text
[agent-jvm] message=BEFORE
```

**Có agent, dùng JVM mới và bật verifier:**

```bash
java -Xverify:all \
  -javaagent:patch-agent.jar \
  -cp build/classes AgentApp
```

**Stdout mong đợi:**

```text
[agent-jvm] message=AFTER!
```

Đây mới là test chứng minh: manifest hợp lệ, JVM khởi động `premain`, transformer được đăng ký, class mục tiêu được định nghĩa qua transformer và method thực sự dùng output. Dù vậy chưa chứng minh tính an toàn trên JVM production với nhiều module/layer, agent khác, custom loader hoặc retransform.

### 9.6. Windows PowerShell

Từ thư mục chứa `src` và `agent.mf`:

```powershell
New-Item -ItemType Directory -Force build/classes | Out-Null

javac --release 17 -d build/classes src/demo/Greeter.java src/BytePatchTransformer.java src/OfflineCheck.java src/PatchAgent.java src/AgentApp.java

java -cp build/classes OfflineCheck build/classes/demo/Greeter.class

javap -v -p build/rewritten/demo/Greeter.class

java -Xverify:all -cp "build/rewritten;build/classes" AgentApp

jar --create --file patch-agent.jar --manifest agent.mf -C build/classes PatchAgent.class -C build/classes BytePatchTransformer.class

java -cp build/classes AgentApp
java -Xverify:all -javaagent:patch-agent.jar -cp build/classes AgentApp
```

Trên Windows classpath có nhiều entries dùng dấu **`;`**, trên POSIX dùng **`:`**. Với build/rewritten trên classpath, đặt nó trước build/classes như hướng dẫn để ưu tiên transformed class. Khi test agent, **không** đặt build/rewritten trước build/classes, nếu không bạn có thể quan sát kết quả đúng dù agent chẳng làm gì.

## 10. Những gì direct `transform` unit test không mô phỏng đầy đủ

Một test có thể PASS trong môi trường tổng hợp nhưng không PASS khi JVM gọi thật. Các khác biệt quan trọng:

### 10.1. Module, loader, protection domain

Trong `OfflineCheck`, ta truyền `null` cho module, loader và protection domain **có chủ đích**, bởi transformer của demo chỉ cần internal name và byte buffer. Điều đó không tương đương với JVM truyền null trong initial class load của một classpath app.

- Với class thông thường trong unnamed module, callback thật có **đối tượng Module** và `module.isNamed() == false`.
- `loader == null` trong callback JVM thật có ý nghĩa bootstrap loader; truyền null bằng tay không tạo bootstrap loading.
- `className` phải đúng dạng internal/slash, ngay cả khi `defineClass` dùng binary/dot.
- `classBeingRedefined` khác null khi redefine/retransform, và callback có thể gặp input bytes đã qua các transformers khác.

Nếu transformer production dùng module identity/loader equality hoặc `ProtectionDomain`, unit test phải cung cấp fixtures và assertions phù hợp **và vẫn cần integration test** để xác thực module/loader thực.

### 10.2. Thứ tự transformer

Giả sử JVM đăng ký A trước rồi B. B không nhất thiết nhìn thấy original bytes từ JAR: nó có thể thấy **output của A**. Đơn vị B nên được test với:

```text
B(originalBytes)       — test độc lập
B(A(originalBytes))    — test thành phần theo thứ tự
```

Với `null` return, cách ghép phải hiểu đúng:

```text
effective(input, transformer) =
    result == null ? input : result
```

Không ghép mảng `null` như thể đó là bytes class file. Không chỉ test các transformer riêng và bỏ qua thứ tự, vì hai phép biến đổi đều đúng riêng có thể xung đột khi phối hợp.

### 10.3. Redefine, retransform, active frames

Kiểm thử define một class **mới** không kiểm tra giới hạn redefinition. Nếu agent sản xuất dùng:

```java
inst.redefineClasses(new ClassDefinition(target, newBytes));
inst.retransformClasses(target);
```

(thí dụ minh họa với `target` là đối tượng `Class<?>` có sẵn), cần:

- Capability manifest `Can-Redefine-Classes` / `Can-Retransform-Classes` và API support checks;
- `inst.isModifiableClass(target)`;
- Không đổi field/method schema, modifiers, hierarchy ngoài giới hạn JVM;
- Tính đến transformer `canRetransform=false` được reuse thay vì gọi lại trên retransform;
- Kiểm tra active stack frames cũ và state của class không tự reset;
- Kiểm thử nhiều lượt để phát hiện double instrumentation.

Không thể thay thế các bài này bằng hai isolated class loaders định nghĩa hai class identities riêng.

### 10.4. Helper class và visibility

Nếu output có thêm lời gọi tới `agent.Helper`, isolated loader với parent null có thể không tìm thấy helper, trong khi JVM app/system loader có hoặc ngược lại. Test phải cố tình chọn loader topology giống runtime, hoặc dùng module/JPMS-aware configuration tương ứng.

**Không chỉ kiểm tra “class được define” mà quên gọi code path chứa helper reference**: một số lỗi liên kết xuất hiện khi JVM thực sự resolve target method/class. Nếu helper nằm ở bootstrap search hay named module, cần xác minh reads/exports/opens theo yêu cầu.

## 11. Xây test matrix chuẩn cho CI

| Ca kiểm thử | Kỳ vọng | Tầng tối thiểu |
| --- | --- | --- |
| ClassName không khớp | `null`, input unchanged | Unit |
| ClassName đúng, bytes gốc | Output new array, thay đổi đúng | Unit |
| Input byte array không bị sửa | `Arrays.equals(original, snapshot)` | Unit |
| Chạy patch lần hai | No-op/idempotent theo rule | Unit |
| Buffer không đủ header | `IllegalClassFormatException` trong direct call | Unit |
| Output không có Code/constant pool bị hỏng | Verifier/parser báo lỗi | Bytecode verify |
| Một method quan trọng sau patch | Return value đúng | Isolated loader hoặc JVM con |
| Binary name sai | Test fail thay vì silently nạp class khác | Isolated loader |
| JDK target/class-file version | Accept đúng version, reject version không hỗ trợ | JVM con |
| Có/không có agent | BEFORE/AFTER! theo JVM process | Integration |
| Agent manifest bị thiếu hoặc sai | Process fail/không có instrumentation | Integration |
| Module/loader khác | Policy chỉ tác động đúng class identity | Integration |
| Callback có threads chạy đồng thời | Không race, deadlock hoặc state bleed | Integration |
| Two transformers | Output đúng theo thứ tự | Unit composition + integration |
| Repeated retransform/redefine | Không chèn trùng, vẫn hợp lệ | Integration với capability |
| Classfile phức tạp | Frames, try/catch, constructor, synchronized vẫn đúng | Verifier + behavioral tests |
| Agent logging/performance | Không log storm, overhead trong budget | Staging load test |

Nên giữ fixture nhỏ nhất mà vẫn tái hiện lỗi. Với bug phụ thuộc stack frames hoặc exception handlers, đừng chỉ dùng class trả về chuỗi đơn giản; thêm fixtures có branches, try/finally, checked exceptions, records, interfaces, lambdas, bootstrap/module access và custom loaders khi phù hợp.

## 12. Diagnostic khi output không đúng

### 12.1. Unit test trả `null` ở target

Kiểm tra:

- `className` là `demo/Greeter`, không phải `demo.Greeter`.
- Tên class có đúng case và package không.
- Có đang set `classBeingRedefined != null` khiến rule bỏ qua không.
- Input `.class` có thật chứa literal mong đợi không.
- Output đã bị patch một lần trước đó chưa; idempotence sẽ trả `null`.
- Dữ liệu đọc từ đúng path/artifact chưa.

### 12.2. Unit test sinh bytes khác nhưng JVM vẫn trả BEFORE

Có thể:

- Test đã patch một constant-pool entry không được method sử dụng.
- `AgentApp` nạp bản class trên classpath khác hoặc loader khác.
- Trong JVM tích hợp, class được load **trước** lúc agent đăng ký.
- Các transformer đứng sau ghi đè output.
- Phép biến đổi không tác động đến method được gọi (hoặc JIT/frames trong redefinition cần phân tích riêng).

Dùng `javap -v -p` trên **file output chính xác**, kiểm tra loader/class source trong JVM nếu cần và thử negative/positive controls ở **hai JVM mới**.

### 12.3. `ClassFormatError`, `VerifyError`, `LinkageError`

- `ClassFormatError`: classfile malformed, constant-pool tags/lengths, attributes/hierarchy không đúng.
- `VerifyError`: instruction control flow, stack types hoặc stack map frames không đáp ứng verifier.
- `LinkageError`: name/loader/duplicate definition/module/helper resolution tùy subtype.
- `NoClassDefFoundError`: binary name không khớp, dependency không load được hoặc liên kết thất bại.
- `IllegalAccessError`: module/package/class access hoặc method/field visibility không đúng.

Đừng kết luận chỉ từ một exception name. Giữ **exact input/output class files**, JDK version, classpath/module path, transformer order, stderr và full stack trace **ngoài callback** để tái hiện.

### 12.4. Test trực tiếp PASS nhưng `-javaagent` lỗi startup

Kiểm tra:

- `META-INF/MANIFEST.MF` thật có `Premain-Class: PatchAgent` ở main section không.
- JAR chứa `PatchAgent.class` và `BytePatchTransformer.class` chưa.
- Có bỏ sót nested/helper classes hoặc dependency ASM/Byte Buddy của agent không.
- `premain` có khởi tạo logger/loader/hệ thống DI gây recursion không.
- `-javaagent` và classpath/module path có đúng không.
- JVM hỗ trợ class-file version của agent và target không.
- Agent có vô tình instrument chính helper/library của mình không.

**Lưu ý:** khi agent startup lỗi, JVM có thể dừng sớm và log nhiều thông tin hơn unit test. Đó là lý do phải qua bước offline trước khi bật agent trong môi trường lớn.

## 13. Các quy tắc bảo toàn độ tin cậy và hiệu năng

- **Không sửa classfileBuffer tại chỗ.** Snapshot bytes trước test để phát hiện mutation.
- **Trả null nếu không đổi.** Không dùng empty array để báo no-op.
- **Không load class mục tiêu trong transform bằng `Class.forName`.** Có thể tạo circular loading.
- **Tránh logger I/O trong callback.** Unit tests có thể log ngoài, agent production dùng counters/bounded events.
- **Không giữ mọi `byte[]`/`ClassLoader`/`Class<?>` trong static cache.** Thiết kế size limit/eviction hoặc weak references phù hợp.
- **Giữ output deterministic.** Tránh tên helper ngẫu nhiên, timestamp, nondeterministic ordering khi không cần.
- **Tách test baseline và test instrumented trong JVM processes riêng.** Không cố define lại cùng binary name trên cùng loader để so behavior.
- **Không bỏ qua module/loader khi policy dựa vào chúng.** Null synthetic args chỉ chấp nhận cho test rule độc lập với metadata đó.
- **Kiểm tra bytes cuối pipeline.** Input của một transformer sau có thể đã khác artifact gốc.
- **Kiểm tra JVM verifier và hành vi runtime.** Static parser không thể chứng minh mọi branch, exception, liên kết và concurrency.
- **Đặt test deadline.** JVM con có agent lỗi có thể treo ở classloader deadlock; CI cần timeout và thu stderr.
- **Không cài agent thử vào JVM production.** Sử dụng JVM con/staging với artifact, version và cấu hình được kiểm soát.

## 14. Quy trình đề xuất cho một thay đổi transformer

```text
Thay đổi rule/instrumentation
       |
       v
Build .class fixture đúng --release và artifact
       |
       v
Unit: gọi transform(...) trực tiếp
       |
       +-- FAIL --> sửa rule, fixture, parser
       |
       v
Kiểm tra input bất biến, no-op, idempotence
       |
       v
javap / ASM verifier / class-file validation
       |
       +-- FAIL --> sửa bytecode, frames, constant pool
       |
       v
Isolated loader / JVM con -Xverify:all
       |
       +-- FAIL --> sửa linking, code/loader dependencies
       |
       v
Package agent JAR và kiểm tra manifest
       |
       v
JVM con mới: baseline vs -javaagent
       |
       +-- FAIL --> điều tra lifecycle/callback/module/loader
       |
       v
Integration: multiple transformers, modules, loaders,
redefine/retransform, threads, rollback, performance
       |
       v
Staging / canary theo quy trình vận hành
```

Tách các bước giúp biết lỗi xảy ra **trước khi** hay **sau khi** JVM tham gia vào lifecycle agent thật. Đừng ghép tất cả vào một lệnh khởi động ứng dụng lớn rồi chỉ so stdout cuối.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Gọi `transform(null, null, "demo/Greeter", null, null, bytes)` có nghĩa đã cài agent vào JVM không?

**Đáp án:** Không. Đây là lời gọi Java thông thường tới method trong một object transformer. Module/loader/domain null là giá trị do test truyền, không phải metadata do JVM cấp.

**Câu 2.** Vì sao unit test phải so sánh `original` với `original.clone()` sau biến đổi?

**Đáp án:** Để phát hiện code vô tình sửa `classfileBuffer` tại chỗ, vi phạm hợp đồng `ClassFileTransformer`.

**Câu 3.** Vì sao `defineClass("demo.Greeter", output,...)` dùng dấu chấm nhưng `className` callback là `demo/Greeter`?

**Đáp án:** `ClassLoader.defineClass` dùng **binary name**, còn callback dùng JVM **internal name**.

**Câu 4.** Nếu `transform` trả mảng output khác input, đã chứng minh class sẽ được JVM chấp nhận chưa?

**Đáp án:** Chưa. Cần classfile verification, test define/link/invoke và integration ở runtime mục tiêu.

**Câu 5.** Vì sao cần hai `IsolatedLoader` để so sánh BEFORE với AFTER!?

**Đáp án:** Cùng binary name không được define hai lần trong cùng defining loader. Hai loaders tạo hai class identities độc lập cho fixture.

**Câu 6.** Vì sao unit test PASS vẫn có thể thất bại lúc chạy `-javaagent`?

**Đáp án:** Vì unit test chưa kiểm tra manifest, `premain`, thứ tự callback, thực tế module/loader/protection domain, helper visibility, JVM verifier trong đường đầy đủ và transformer chain khác.

**Câu 7.** `retransformClasses` có thể được kiểm thử đầy đủ bằng cách dùng hai class loaders không?

**Đáp án:** Không. Retransformation sửa bytecode của một class identity đã nạp với capability và JVM semantics riêng; isolated definition không thay thế được.

**Câu 8.** Vì sao nên bật `-Xverify:all` trong một JVM con thử nghiệm?

**Đáp án:** Để nhận diện nhiều lỗi verifier/linking khi chạy bytes mới với JVM, nhưng vẫn cần semantic tests và kiểm tra class loader/module đúng bối cảnh.

## 16. Tài liệu chính thức

- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): overloads, metadata callback, `return null`, input immutability, transformer chain và exception semantics.
- [Oracle Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `defineClass`, binary names, loader identity, class loading.
- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `redefineClasses`, `retransformClasses` và capability checks.
- [Oracle Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent manifest, `premain` và Java agent startup.
- [Oracle Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): `-v`, `-c`, `-p` và kiểm tra class files.
- [JVMS SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool, Code, StackMapTable và class-file format.
- [OpenJDK — ASM Commons/util](https://asm.ow2.io/): tài liệu thư viện bytecode, `CheckClassAdapter` dành cho projects dùng ASM.

**Ghi nhớ:** hãy kiểm tra **class bytes như dữ liệu** trước khi cài agent: khẳng định đúng class match, input bất biến, output khác hợp lệ, no-op/idempotence, JVM có thể define/invoke trong môi trường thử riêng. Chỉ sau đó đóng agent và khởi chạy **một JVM mới với `-javaagent`** để xác nhận lifecycle, module/loader và kết quả thật. Offline PASS là cửa kiểm soát chất lượng quan trọng, **không phải** bằng chứng thay thế toàn bộ integration test.
