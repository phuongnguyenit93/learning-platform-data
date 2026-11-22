# Xác minh cấu trúc với `ClassFile.verify` rồi kiểm tra nạp, chạy trên JVM

> **Mục tiêu:** Nắm được quy trình kiểm thử classfile do Java instrumentation sinh ra: **kiểm chứng tĩnh** bằng Java Class-File API `ClassFile.verify(...)`, sau đó **nạp đúng bytes đã xác minh vào JVM**, kích hoạt khởi tạo, kiểm tra liên kết và chạy các ca kiểm thử về return value, exception và dependency. Biết tại sao kết quả verification rỗng không đồng nghĩa hành vi đúng, vì sao cần thử trên class loader/module/JDK thực tế, và cách phân loại lỗi khi phát hành Java agent. Bài có ví dụ Java **JDK 24+** hoàn chỉnh với ba overload `verify`, một lần load cô lập và một lần chạy trên JVM mới.

Bài thuộc nhóm **Kiểm thử và chẩn đoán**. `ClassFile` trong tên bài là `java.lang.classfile.ClassFile` thuộc **Class-File API chuẩn từ JDK 24 (JEP 484)**. Java 17 không có package chuẩn này; nếu ứng dụng production chạy JDK 17, có thể đặt tooling kiểm chứng ở JDK 24+ rồi chạy integration test trên **JDK 17 đích** với classfile có version tương thích. **Không** copy nguyên lab sử dụng `java.lang.classfile` sang `javac 17` và chờ nó biên dịch.

## 1. Vì sao có hai tầng kiểm thử?

Một `ClassFileTransformer` hoặc bộ sinh bytecode có thể trả về một mảng bytes mà JVM sẽ dùng để định nghĩa lại một class. Có hai câu hỏi khác nhau:

1. **Bytes có hợp lệ theo định dạng và quy tắc kiểm chứng bytecode?**
2. **Class có được JVM thật nạp/liên kết/khởi tạo và thực thi đúng nghiệp vụ?**

Hai câu hỏi cần hai loại bằng chứng:

```text
source .class
     │
     ▼
parse → transform / build
     │
     ▼
candidate byte[]
     │
     ├── ClassFile.verify(candidate)
     │       └── lỗi cấu trúc/verification → sửa output
     │
     ▼
verification không phát hiện lỗi
     │
     ▼
write đúng artifact .class/.jar
     │
     ▼
JVM đích + defining ClassLoader + JPMS graph
     │
     ├── load/link/initialize → lỗi runtime?
     │
     ▼
gọi method, test branches/exception/state
     │
     ├── kết quả nghiệp vụ sai hoặc quá chậm?
     │
     ▼
CI / integration / canary evidence
```

**`verify PASS` không đồng nghĩa `runtime PASS`**, và runtime PASS trên một method không chứng minh toàn bộ class/dependencies/paths đều đúng. Hãy ghi riêng ba trạng thái: `verification_passed`, `load_link_passed`, `behavior_tests_passed`.

Một classfile có thể được verifier chấp nhận nhưng dùng `invokestatic` gọi helper chưa có ở target loader; JVM có thể ném `NoClassDefFoundError` hoặc `NoSuchMethodError` khi instruction ấy được thực thi. Một class khác có thể nạp và chạy không lỗi nhưng trả `x * 3` thay vì `x * 2`. Đó là lỗi logic, không phải lỗi stack map.

## 2. Chính xác `ClassFile.verify` cung cấp gì?

API chuẩn JDK 24+ có ba overload:

```java
import java.lang.VerifyError;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Path;
import java.util.List;

// Các biến bytes và path phải được chương trình cấp trước.
ClassFile cf = ClassFile.of();
ClassModel model = cf.parse(bytes);

List<VerifyError> modelErrors = cf.verify(model);
List<VerifyError> byteErrors = cf.verify(bytes);
List<VerifyError> diskErrors = cf.verify(path);
```

**Đây là đoạn minh họa chứ chưa phải file Java độc lập**, vì `bytes` và `path` được giả định đã tồn tại. Phần lab sẽ cung cấp toàn bộ chương trình.

| API | Đầu vào | Sử dụng trong pipeline |
| --- | --- | --- |
| `verify(ClassModel model)` | Mô hình class đã parse | Kiểm chứng mô hình đọc được, ví dụ trước transform |
| `verify(byte[] bytes)` | Candidate bytes | Kiểm chứng **bytes cuối** do transformer/builder trả về |
| `verify(Path path)` | Tệp `.class` đã ghi | Kiểm chứng artifact vật lý trước khi đóng gói/triển khai |

Giá trị trả về là **`List<java.lang.VerifyError>`**: list rỗng nghĩa là không tìm thấy verification errors trong lần kiểm tra đó. List không rỗng phải được in/đưa vào báo cáo lỗi và khiến test **thất bại**, không chỉ ghi warning.

`verify(Path)` có thể ném `IOException` khi không đọc được file; parser hay hierarchy resolver cũng có thể báo exception do input sai hoặc môi trường không đầy đủ. Không giả định mọi dữ liệu malformed luôn trở về dưới dạng một phần tử list.

Mẫu kiểm tra:

```java
// Đặt trong method có biến byte[] candidateBytes.
List<VerifyError> errors =
        ClassFile.of().verify(candidateBytes);

if (!errors.isEmpty()) {
    for (VerifyError error : errors) {
        System.err.println(error);
    }
    throw new AssertionError("Candidate verification failed");
}
```

Đây là ví dụ snippet có `candidateBytes` từ bên ngoài. Trong CI, phải để tiến trình trả exit code khác 0 nếu phát hiện lỗi. Một log `"verification failed"` nhưng build vẫn tạo artifact release có thể khiến lỗi lọt vào production.

### `VerifyError` trong list và `VerifyError` trong JVM khác nhau ở pha báo lỗi

Cùng là `java.lang.VerifyError`, nhưng:

- Trong `List<VerifyError>` nó là **kết quả dữ liệu** của phép xác minh Class-File API.
- Khi JVM ném `VerifyError`, đó là **exception/error thực tế** trong quá trình load/verify/link class.

Chỉ thấy một list rỗng không chứng minh rằng JVM trong deployment khác, với loader/module khác, không thể ném `VerifyError` hoặc các `LinkageError` khác.

## 3. Parse thành công chưa phải verification toàn bộ

`ClassFile.of().parse(bytes)` tạo `ClassModel`, là mô hình bất biến mô tả classfile. Nhưng Class-File API có thiết kế **lazy parsing**: một số attributes/instructions chỉ được diễn giải khi ứng dụng duyệt hoặc truy cập. Javadoc cảnh báo `IllegalArgumentException` có thể xuất hiện ở một accessor vì bytes malformed.

Do đó:

```text
parse(bytes) không báo lỗi
      ≠
verify(bytes) trả empty list
      ≠
JVM thực thi mọi method không có lỗi
```

Trong một công cụ instrumentation, có thể parse để đọc tên class và methods, biến đổi một số elements rồi serialize thành bytes mới. **Bước verify phải thực hiện trên bytes mới**, không chỉ model ban đầu.

### Những lớp lỗi verification quan tâm

- Header và classfile version không hợp lệ.
- Constant pool entries/tags/indexes sai.
- Tên internal class, type descriptors, method descriptors không hợp lệ.
- Instructions hỏng hoặc sử dụng operand sai.
- Branch target không trỏ tới instruction boundary hợp lệ.
- Exception handler table/phạm vi bytecode sai.
- Operand stack, local variable type và data-flow không nhất quán.
- `StackMapTable` và các frame type constraints không phù hợp.
- Attributes/metadata bị thao tác hỏng trong quá trình viết lại.

Đây là nhóm lỗi theo **định dạng/JVMS**, không có nghĩa mọi lỗi luôn được `ClassFile.verify` biểu diễn bằng một message cố định. Phải ghi nhận cả `IllegalArgumentException`, `List<VerifyError>` và JVM-side errors một cách riêng biệt.

### Những lỗi không thuộc phạm vi một phép verification tĩnh

- Logic nghiệp vụ trả sai số hoặc đánh giá nhầm điều kiện.
- Helper class ở class loader khác nên không thể link.
- Tên method/field có trong constant pool nhưng thực tế runtime không có method/field tương ứng.
- Named module không đọc được module, package không export/open hợp lệ.
- Static initializer ném exception hoặc deadlock.
- Concurrent invocation gây race hoặc mất dữ liệu metrics.
- Probe được gọi hai lần thay vì một lần trên exception path.
- Thread/blocking/network overhead vượt ngân sách SLO.
- Transformer chain khác giữa local test và production.
- Trường hợp JDK đích không hỗ trợ major/minor version của candidate.

`ClassFile.verify` là **một cổng chất lượng**, không phải công cụ chứng minh độ đúng tuyệt đối của hệ thống.

## 4. Kiểm chứng đúng candidate chứ không phải một bản gần giống

Dữ liệu qua chuỗi transformer có thể là:

```text
B0 original bytes
    │
    ▼
T1 → B1
    │
    ▼
T2 → B2
    │
    ▼
T3 → B3 (candidate cuối)
```

Nếu bạn verify **B1** nhưng deploy **B3**, kết quả không đủ chứng minh B3 hợp lệ. Trong JVM, các transformer Java/native được áp dụng theo nhóm; output của mỗi transformer có thể trở thành input của transformer tiếp theo. Không có một agent đơn lẻ nào luôn biết output cuối sau mọi agent khác.

Vì thế test nên bám theo **exact candidate**:

1. Xác định bytes được sinh từ source nào, công cụ/version nào, JDK nào.
2. Chạy `ClassFile.verify(candidateBytes)`.
3. Ghi bytes ra artifact cuối (`.class` hoặc `.jar`) đúng đường dẫn nội bộ.
4. Đọc/verify artifact đó một lần nữa; khi cần ghi hash SHA-256.
5. Trên JVM thử nghiệm, nạp **artifact đó**, không phải class cùng tên từ system classpath.
6. Kiểm thử runtime semantic, exception, concurrency và hiệu năng.
7. Khi phát hành, dùng chính artifact đã được kiểm chứng hoặc so hash trước deploy.

**Không** kết luận “đã verify” vì một file `.class` ở thư mục source có tên giống bản được chuyển qua `ClassDefinition`; `redefineClasses` có thể nhận bytes mới hoặc đi qua các transformers đang đăng ký.

### Giải thích `ClassTransform.ACCEPT_ALL`

Trong bài lab, ta dùng:

```java
byte[] output =
        ClassFile.of().transformClass(
                model, ClassTransform.ACCEPT_ALL);
```

`ClassTransform.ACCEPT_ALL` là transform **giữ các elements** và cho phép bộ builder tái tạo classfile. Nó là **no-op transform về ý định nghiệp vụ**; không tạo probe. Lý do dùng nó là minh họa đường đi `parse → transformClass → verify output → JVM load`, không dạy cách chèn method call vào bytecode.

Muốn biến đổi thật, cung cấp `ClassTransform`/`MethodTransform`/`CodeTransform` phù hợp, bảo đảm stack maps/frames và verify output sau khi hoàn tất. `transformClass` có thể tạo bytes không giống hệt binary ban đầu ở mức byte-for-byte nhưng vẫn giữ semantics; vì vậy chỉ so kích thước file hay hash không phải phép so tương đương logic.

## 5. Hierarchy resolver: điểm mù thường gặp của verify trong agent

Đối với stack-map verification/type merges, Class-File API có thể cần thông tin kế thừa và interface hierarchy. JDK 24 cung cấp `ClassFile.ClassHierarchyResolverOption`.

Resolver mặc định dùng **system class loader và reflection**. Điều đó có thể không đủ nếu:

- Class mục tiêu được định nghĩa bởi plugin/servlet/custom loader.
- Có hai classes cùng tên ở các loader khác nhau.
- Tên class chỉ tồn tại trong bytes mới, chưa có trên system classpath.
- Module/layer kiểm soát visibility khác so với môi trường test.
- Agent không muốn kích hoạt bất kỳ class loading nào trong callback.

Theo Javadoc, `ClassHierarchyResolver.ofClassLoading(loader)` có thể tra cứu class bằng loading/reflection. `ofResourceParsing(loader)` đọc classfile resources tương ứng thay vì dựa hoàn toàn vào việc load class. `ClassHierarchyResolver.of(...)` có thể dùng metadata về interfaces/supertypes đã được biết trước.

Đoạn cấu hình minh họa:

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassHierarchyResolver;

// targetLoader được môi trường test cung cấp trước đó.
ClassFile cf = ClassFile.of(
        ClassFile.ClassHierarchyResolverOption.of(
                ClassHierarchyResolver.ofResourceParsing(targetLoader))
);
```

**Đoạn trên chưa runnable độc lập** vì `targetLoader` cần được khai báo từ hệ thống test. Với loader chuyên biệt, có thể cần resolver tổng hợp hoặc metadata của những generated classes chưa có trong resources.

**Cảnh giác khi gọi từ `ClassFileTransformer`:** Nếu verifier/resolver thử `Class.forName` hoặc load class đang định nghĩa, có thể xảy ra recursive loading, `ClassCircularityError`, `LinkageError` hoặc deadlock do class-loading locks. Vì vậy dùng verification chuyên sâu trong **CI/integration test** hoặc bộ resolver dựa trên metadata là lựa chọn thực tế hơn là verify toàn bộ class khi JVM đang nạp dưới tải lớn.

### Cache và concurrency

`ClassHierarchyResolver.cached()` mặc định **không thread-safe**. Nếu shared cùng resolver giữa nhiều callback threads, phải xét đồng bộ phù hợp; đồng thời cache theo tên mà không xét loader/version có thể giữ thông tin stale sau redefine hoặc redeploy.

**Không lẫn hai vấn đề:** Một resolver cấu hình sai có thể gây kết quả xác minh không đầy đủ/báo lỗi khi input vẫn hợp lệ trong target loader. Ngược lại, resolver đúng không cứu được bytecode có branch target/stack map sai.

## 6. Các pha của JVM và loại lỗi có thể xuất hiện

| Pha | Điều phải kiểm | Loại lỗi thường thấy |
| --- | --- | --- |
| **Loading/definition** | Loader có thể định nghĩa class từ bytes có đúng binary name? | `ClassFormatError`, `UnsupportedClassVersionError`, `NoClassDefFoundError` |
| **Verification** | Type/stack/frames và quy tắc bytecode hợp lệ trên JVM? | `VerifyError` |
| **Resolution/linking** | Method/field/class references có thật và truy cập được? | `NoSuchMethodError`, `NoClassDefFoundError`, `IllegalAccessError`, `IncompatibleClassChangeError` |
| **Initialization** | `<clinit>` có hoàn tất đúng? | `ExceptionInInitializerError`, deadlock |
| **Execution** | Return values, exceptions và side effects đúng? | Business errors, `AssertionError`, timeout |
| **Deployment** | Artifact/JDK/agent/module/config trùng môi trường thật? | Lỗi không tái hiện ở unit test |

JVM có thể thực hiện **lazy symbolic resolution**; `ClassLoader.defineClass(...)` không bắt buộc giải quyết mọi method reference trong code chưa chạy. Một class có thể load được, `Class.forName(..., true, loader)` có thể initialize được, nhưng một branch hiếm chưa được gọi vẫn gây `NoSuchMethodError` sau này.

Bởi vậy cần **thực thi các đường code quan trọng**; không chỉ tạo `Class<?>` rồi in `"PASS"`.

### `defineClass`, `Class.forName`, `Method.invoke` phục vụ các phép kiểm khác nhau

- `defineClass(name, bytes, 0, bytes.length)` định nghĩa class cụ thể dưới **defining loader** mà bạn kiểm soát.
- `Class.forName(name, true, loader)` buộc tìm class qua loader đó và yêu cầu **initialization**.
- `getMethod` kiểm tra public method có mặt với tên/tham số yêu cầu.
- `Method.invoke` chạy method và cho phép kiểm thử return value. Nếu target method ném exception, reflection bọc trong `InvocationTargetException`, cần xem `getCause()`.
- Chạy một **JVM process mới** với `-cp` chỉ trỏ đúng artifact là phép kiểm tra deployment bổ sung: không vô tình dùng một `Class<?>` đã load trong test runner cũ.

Một lần load trong custom loader không thay thế bài test với **đúng defining loader và module graph của production**. Lab chỉ là bước nền có thể chạy được.

## 7. Bài lab Java 24+: source → verify → load → run → fresh JVM

Lab chỉ cần JDK, không dùng ASM/Byte Buddy/agent. Nó dựng một classfile candidate bằng Class-File API rồi xác minh ba cách:

1. Compile class `Calculator` bằng `javac`.
2. Parse và `verify(ClassModel)` source model.
3. `transformClass(model, ClassTransform.ACCEPT_ALL)` tạo candidate mới.
4. `verify(byte[])` candidate.
5. Ghi `.class` thật và `verify(Path)`.
6. Phá magic header một bản copy để kiểm tra parser từ chối input malformed.
7. Nạp candidate vào isolated loader, initialize, chạy success/edge/exception paths.
8. Khởi động JVM mới với `-Xverify:all`, nạp file đã ghi và test return.

### 7.1. Cấu trúc file

```text
verify-then-run/
├── src/
│   ├── demo/sample/Calculator.java
│   ├── demo/run/FreshJVM.java
│   └── VerifyAndRun.java
└── out/                    # lệnh build tạo
    ├── original/
    ├── verifier/
    ├── runner/
    └── checked/
```

**Quan trọng:** Khi chạy `VerifyAndRun`, runtime classpath **không chứa `out/original`**. Nếu bạn vô tình cho cả hai bản `Calculator.class` vào classpath, parent delegation hoặc thứ tự classpath có thể khiến test nạp sai bản.

### 7.2. `src/demo/sample/Calculator.java`

```java
package demo.sample;

public final class Calculator {
    private Calculator() {
    }

    public static int twice(int number) {
        if (number < 0) {
            throw new IllegalArgumentException("negative input");
        }
        return number * 2;
    }
}
```

Hai trường hợp thành công cần kiểm:

- `twice(21) == 42`.
- `twice(0) == 0`.

Với `twice(-1)`, method phải ném `IllegalArgumentException` có message `"negative input"`. Không dựa vào việc verifier có thể đoán business contract này: verifier chỉ phân tích classfile/bytecode, còn ý nghĩa `twice` phải do test định nghĩa.

### 7.3. `src/VerifyAndRun.java`

```java
import java.lang.VerifyError;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class VerifyAndRun {
    private static final String NAME = "demo.sample.Calculator";

    private static final class IsolatedLoader extends ClassLoader {
        IsolatedLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> define(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    private static void assertVerified(
            String stage, List<VerifyError> errors) {
        if (!errors.isEmpty()) {
            for (VerifyError error : errors) {
                System.err.println(stage + ": " + error);
            }
            throw new AssertionError(
                    stage + ": verification failed");
        }
        System.out.println(stage + ": verify=PASS");
    }

    private static void assertNegativePath(Method method)
            throws Exception {
        try {
            method.invoke(null, -1);
            throw new AssertionError(
                    "Expected IllegalArgumentException");
        } catch (InvocationTargetException wrapper) {
            Throwable cause = wrapper.getCause();
            if (!(cause instanceof IllegalArgumentException)
                    || !"negative input".equals(cause.getMessage())) {
                throw new AssertionError(
                        "Unexpected target exception", cause);
            }
        }
        System.out.println(
                "runtime: twice(-1)=IllegalArgumentException");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: VerifyAndRun <source.class> <output-root>");
        }

        Path source = Path.of(args[0]);
        Path outputRoot = Path.of(args[1]);

        ClassFile cf = ClassFile.of();
        byte[] input = Files.readAllBytes(source);

        // 1. Verify bản model sau parse.
        ClassModel model = cf.parse(input);
        assertVerified("source", cf.verify(model));

        // 2. Tái tạo class bytes qua Class-File API.
        byte[] candidate =
                cf.transformClass(model, ClassTransform.ACCEPT_ALL);
        assertVerified("generated", cf.verify(candidate));

        // 3. Verify đúng artifact đã ghi xuống disk.
        Path output = outputRoot.resolve(
                "demo/sample/Calculator.class");
        Files.createDirectories(output.getParent());
        Files.write(output, candidate);
        assertVerified("disk", cf.verify(output));

        // 4. Negative control: hỏng magic header.
        byte[] broken = candidate.clone();
        broken[0] = 0;
        try {
            cf.parse(broken);
            throw new AssertionError(
                    "Malformed input should have failed");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "negative: malformed-header=rejected");
        }

        // 5. Nạp CHÍNH candidate vào loader riêng.
        IsolatedLoader loader = new IsolatedLoader();
        Class<?> defined = loader.define(NAME, candidate);
        if (defined.getClassLoader() != loader) {
            throw new AssertionError("Wrong defining loader");
        }

        Class<?> initialized = Class.forName(NAME, true, loader);
        if (initialized != defined) {
            throw new AssertionError("Wrong class identity");
        }
        System.out.println("runtime: loader=isolated");

        // 6. Gọi method thật và kiểm tra logic.
        Method method = defined.getMethod("twice", int.class);
        Object answer = method.invoke(null, 21);
        if (!Integer.valueOf(42).equals(answer)) {
            throw new AssertionError("Wrong result: " + answer);
        }
        System.out.println("runtime: twice(21)=42");

        Object zero = method.invoke(null, 0);
        if (!Integer.valueOf(0).equals(zero)) {
            throw new AssertionError("Wrong zero result: " + zero);
        }
        System.out.println("runtime: twice(0)=0");

        assertNegativePath(method);
        System.out.println("integration: PASS");
    }
}
```

**Giải thích từng điểm quan trọng:**

- `ClassFile.of()` dùng default options phù hợp với class rất đơn giản của lab, không có external hierarchy.
- `cf.parse(input)` có thể ném `IllegalArgumentException` nếu classfile malformed hoặc version không được JDK hiện tại hỗ trợ.
- `ClassTransform.ACCEPT_ALL` có nhiệm vụ đưa elements sang builder, **không** chèn probe; candidate là một classfile tái tạo từ model.
- `assertVerified` nhận list lỗi và **fail test** nếu list khác rỗng, thay vì tiếp tục chạy với bytes chưa hợp lệ.
- `Files.write` ghi classfile đúng path từ binary name, sau đó `verify(Path)` kiểm tra **dữ liệu trên disk**.
- Negative control tạo bản copy rồi thay byte magic đầu tiên; `cf.parse` được kỳ vọng từ chối header hỏng bằng `IllegalArgumentException`. Không coi negative test này là một `verify` overload.
- `IsolatedLoader` dùng platform parent nên không có bản `Calculator` ở application/system loader; `defineClass` nhận **đúng candidate**.
- `Class.forName(NAME,true,loader)` yêu cầu initialize class và kiểm tra identity; nếu gọi trên class đã nạp ở loader khác, identity check sẽ phát hiện.
- `Method.invoke` bọc exception nghiệp vụ trong `InvocationTargetException`. Test negative path phải kiểm tra `wrapper.getCause()`.
- `Integer.valueOf(42).equals(answer)` kiểm tra return value thực sự, không chỉ method signature.
- Chương trình chỉ in `integration: PASS` nếu mọi bước trước đó đạt. Nếu lỗi `NoSuchMethodError`, `VerifyError` hoặc `AssertionError`, process không giả vờ thành công.

### 7.4. `src/demo/run/FreshJVM.java`

```java
package demo.run;

import demo.sample.Calculator;

public final class FreshJVM {
    public static void main(String[] args) {
        int value = Calculator.twice(21);
        if (value != 42) {
            throw new AssertionError(
                    "Wrong result: " + value);
        }
        System.out.println(
                "fresh-jvm: twice(21)=" + value);
    }
}
```

File này compile với **API của class gốc** nhưng khi chạy sử dụng `.class` đã qua `verify(Path)` trong `out/checked`. Vì là process JVM mới, không có nguy cơ class `Calculator` cùng tên đã được test runner nạp từ trước. Có thể bổ sung test exception path ở JVM mới nếu cần; mục tiêu ở đây là xác nhận **fresh classpath resolution**.

### 7.5. Build/run trên Bash (Linux/macOS/Git Bash)

Ở thư mục `verify-then-run`, dùng JDK 24+:

```bash
mkdir -p out/original out/verifier out/runner out/checked

javac -encoding UTF-8 -d out/original \
    src/demo/sample/Calculator.java

javac -encoding UTF-8 -d out/verifier \
    src/VerifyAndRun.java

javac -encoding UTF-8 -cp out/original -d out/runner \
    src/demo/run/FreshJVM.java

java -cp out/verifier VerifyAndRun \
    out/original/demo/sample/Calculator.class out/checked

java -Xverify:all -cp out/runner:out/checked \
    demo.run.FreshJVM
```

Thứ tự có ý nghĩa: runner cần `Calculator` ở **compile time** nhưng runtime classpath chỉ chứa `out/runner` và `out/checked`, **không** có `out/original`. Các path Unix dùng dấu `:` để nối nhiều classpath entries.

### 7.6. Build/run trên PowerShell (Windows)

```powershell
New-Item -ItemType Directory -Force `
    -Path out/original, out/verifier, out/runner, out/checked |
    Out-Null

javac -encoding UTF-8 -d out/original `
    src/demo/sample/Calculator.java

javac -encoding UTF-8 -d out/verifier `
    src/VerifyAndRun.java

javac -encoding UTF-8 -cp out/original -d out/runner `
    src/demo/run/FreshJVM.java

java -cp out/verifier VerifyAndRun `
    out/original/demo/sample/Calculator.class out/checked

java -Xverify:all -cp "out/runner;out/checked" `
    demo.run.FreshJVM
```

PowerShell dùng backtick để nối dòng. Khi có nhiều classpath entries trên Windows, dùng dấu `;`; trên Bash dùng `:`. Không cần `--enable-preview` cho Class-File API chuẩn trên JDK 24.

### 7.7. Stdout kỳ vọng

Với JDK 24+ có thể đọc classfile đã compile và không có môi trường/agent khác ảnh hưởng:

```text
source: verify=PASS
generated: verify=PASS
disk: verify=PASS
negative: malformed-header=rejected
runtime: loader=isolated
runtime: twice(21)=42
runtime: twice(0)=0
runtime: twice(-1)=IllegalArgumentException
integration: PASS
fresh-jvm: twice(21)=42
```

Ba dòng đầu kiểm tra các overload `ClassFile.verify`. Dòng negative xác nhận parser từ chối header hỏng. Bốn dòng runtime kiểm tra loader identity, success, zero và failure path; dòng integration chỉ xuất hiện khi tất cả assertion qua. Dòng `fresh-jvm` đến từ **lệnh java thứ hai**, tức JVM khác.

Nếu runner nhận lỗi, bạn sẽ thấy stderr/exit nonzero thay vì output kỳ vọng; cần giữ stack trace để sửa nguyên nhân. Không dùng “stdout mẫu” làm bằng chứng chương trình đã chạy thành công khi chưa thật sự chạy.

## 8. Vì sao `-Xverify:all` vẫn chưa đủ?

`-Xverify:all` yêu cầu JVM kiểm chứng trong phạm vi các class được tải. Tuy nhiên:

- Nó không buộc ứng dụng chạy tất cả method/branches.
- Có những lỗi dependency chỉ xuất hiện khi một symbolic reference được resolve trong code path cụ thể.
- Nó không biết business contract `twice(x)==2*x`.
- Nó không kiểm tra overhead và concurrency side effects.
- Nó không tự bảo đảm file trên classpath là cùng file build đã verify nếu deployment đã thay artifact.

Do vậy ta chạy song song **JVM verifier** và **functional tests**. Trong CI có thể tách static verification và JVM smoke tests thành hai stages để phát hiện lỗi sớm hơn. Với hệ thống lớn, cần integration tests dùng cùng JDK vendor/version và cùng agent/classloader/module graph với production.

### Nên thêm negative tests gì?

Đừng chỉ test một file hỏng magic; thêm những loại fixture an toàn trong test environment:

- Classfile có StackMapTable không nhất quán với control flow.
- Branch offset không nằm ở instruction boundary.
- `invokestatic` tới method không tồn tại (bytecode có thể parse nhưng runtime resolution lỗi).
- Helper package không thấy qua custom loader (để tìm `NoClassDefFoundError`).
- Method có `try/finally` và ném exception, để phát hiện probe làm mất exception gốc.
- Class cần redefine nhưng replacement thay schema bị cấm.
- Generated class major version quá mới cho target runtime.
- Test bên trong named module có thiếu read/exports/opens edge.

**Lưu ý:** Các trường hợp tiêu cực cần tạo ở môi trường test, không cố tình đưa classfile hỏng vào JVM production. Một test có thể assert đúng loại lỗi hoặc ít nhất assert process **không thành công**, nhưng message JVM cụ thể có thể khác giữa vendors/versions.

## 9. Với Java agent thật, nên test các gì ngoài lab?

### 9.1. Instrumentation helper resolution

Transformer thường chèn instruction như:

```text
invokestatic com/example/agent/bridge/ProbeBridge.hit:()V
```

Đây là **mô tả method reference**, không phải Java source. JVM class loader của class được instrument cần tìm thấy helper. Nếu helper nằm trong system loader mà class target chỉ delegate tới bootstrap/platform, một classfile có thể `verify` PASS nhưng invocation lỗi `NoClassDefFoundError`.

Đối với named module, còn cần read edge/visibility theo JPMS. Test qua loader/modules **thật**; không chỉ chạy ứng dụng trên system classpath trong lab.

### 9.2. Runtime semantic preservation

Trong instrumented methods, test:

- Normal returns và early returns.
- Checked/unchecked exception được giữ type/message.
- `finally` chạy đúng một lần.
- Không làm thay giá trị trả về hoặc side effects.
- Không gọi probe hai lần với một request.
- Không thay control flow khi method có synchronized block/monitor.
- Không đưa network I/O nặng vào hot path.
- Không tạo class-loading recursion khi helper, logger, exporter bị instrument.
- Không ghi dữ liệu nhạy cảm vào event payload không được phép.

Một stack map hợp lệ không thể chứng minh những invariant nghiệp vụ này.

### 9.3. Bytecode integrity sau nhiều transformer

Nhiều Java agents, native JVMTI hooks hoặc redefinition có thể tạo chain:

```text
source bytes → A → B → C → JVM
```

Một unit test trực tiếp của A không biết B/C có chèn lại instructions hoặc làm sai metadata không. Cần tích hợp **đúng thứ tự agents và JVM**. Nếu một transformer trả `null`, đó là “không đổi output hiện tại”, không phải “đã rollback output của transformer trước”.

### 9.4. Redefinition/retransformation

Một classfile đủ điều kiện để **load mới** chưa chắc có thể **redefine** class hiện hữu:

- `Instrumentation.isRedefineClassesSupported()` và `isModifiableClass(target)` phải phù hợp.
- Replacement không được tùy tiện thêm/xóa field/method, đổi descriptors hoặc superclass/interface.
- Java transformers đã đăng ký có thể vẫn được gọi trong redefine.
- `retransformClasses` không nhận replacement `byte[]` như redefine.
- Active method frames có thể tiếp tục chạy bytecode cũ; invocation mới mới dùng phiên bản mới.
- Static state không tự reset và class initializer không tự chạy lại.

Vì vậy test `ClassFile.verify(candidate)` là bước mở đầu, còn phải gọi đúng API trên JVM test và kiểm tra response/errors/runtime sau đó.

## 10. Chẩn đoán khi verification hoặc runtime thất bại

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `parse(...)` ném `IllegalArgumentException` | Classfile malformed hoặc unsupported version | Kiểm tra bytes source, header/version, parser |
| `verify(...)` trả list không rỗng | Kiểu stack/frames/instructions/attributes sai | In đủ lỗi, so `javap -v`, method offset |
| `verify(Path)` ném `IOException` | File path/permission không đúng | Sửa test artifact, không gán là bytecode bug |
| Verify báo lỗi liên quan hierarchy | Resolver mặc định không thấy custom loader classes | Cung cấp hierarchy resolver hợp lệ |
| `UnsupportedClassVersionError` | Runtime JVM cũ hơn classfile major version | Compile/generate theo `--release` phù hợp |
| `ClassFormatError` | Classfile format JVM không chấp nhận | So hash bytes cuối, check constant pool/attributes |
| JVM `VerifyError` | Stack-map/dataflow/type safety sai | Dump exact bytes, `-Xverify:all`, kiểm tra frames |
| `NoClassDefFoundError` | Missing dependency/helper hoặc resolution failure | Kiểm tra loader, module, JAR và load timing |
| `NoSuchMethodError` | Method descriptor/ABI của helper thay đổi | `javap -p -s`, đối chiếu runtime JAR |
| `IllegalAccessError` | Package, module, access flags không cho gọi | Xem exports/reads/opens và defining loader |
| `ExceptionInInitializerError` | Static initializer lỗi | Test `Class.forName(...,true,loader)` |
| `InvocationTargetException` | Method được invoke ném exception | Đọc cause, so contract |
| Test pass trên CI nhưng fail ở server | JDK, classpath, custom loader, agent order khác | Reproduce đúng deployment và artifact |
| Test bytecode pass nhưng logic sai | Branch/return/side effect semantics lỗi | Golden tests cho nhiều đường code |
| JVM chậm dù verify pass | Allocation, locking, exporter block | JFR/profile/benchmark có–không instrumentation |
| Lỗi chỉ trên redeploy | Class-loader leak hoặc cache stale | Log defining loader và lifecycle |

### `javap` nên dùng như thế nào?

Ví dụ sau khi đã ghi candidate:

```bash
javap -v -p out/checked/demo/sample/Calculator.class
```

`javap -v` cho thấy constant pool, bytecodes, `StackMapTable`, exception tables và metadata. Khi lỗi thuộc method cụ thể, hãy so version **trước và sau** transform, không chỉ nhìn source Java. Nếu muốn xem method descriptors:

```bash
javap -p -s out/checked/demo/sample/Calculator.class
```

Cần giữ thông tin class-loader/module/runtime khi đối chiếu, vì một symbolic reference có thể hợp lệ ở loader A nhưng không resolve được ở loader B.

## 11. Đặt verification ở đâu trong một sản phẩm agent?

**Tốt nhất ở build/test:** Thu các classfile fixtures, chạy transform, verify output, khởi tạo JVM test với versions thật. Điều này phát hiện lỗi trước deployment và không làm production startup chậm.

**Có thể ở integration test:** Nếu có nhiều agents/classloaders, chạy JVM riêng với `-javaagent` thật, test output cuối. Có thể bật diagnostics và lưu artifacts debug ở vùng được bảo vệ.

**Thận trọng trong callback production:** `ClassFileTransformer.transform(...)` xảy ra giữa quá trình class loading và có thể chạy đồng thời trên nhiều thread. `ClassFile.verify` với hierarchy resolver mặc định có thể thử reflection/load thêm classes trong khi JVM đang giữ lock. Việc gọi verifier nặng cho mọi class có thể làm tăng latency, GC hoặc gây recursion/deadlock.

Một agent chạy JDK 17 cũng **không thể** dựa trên Class-File API chuẩn JDK 24 trong chính callback; khi cần, dùng tooling khác phù hợp JDK, hoặc đặt verification trên JDK 24+ ở CI nhưng vẫn thử bytecode dưới JVM đích.

### Checklist dành cho CI

1. Tạo class bytes từ đúng source và transformer version.
2. Xác nhận classfile major version tương thích JDK đích.
3. Parse/verify input khi cần.
4. Verify **generated bytes**, không chỉ source.
5. Ghi artifact và verify file đã lưu.
6. Gắn hash/artifact identifier vào test report.
7. Test `defineClass` trong isolated/target loader.
8. Test `Class.forName(...,true,loader)` và các methods/exception paths.
9. Chạy một JVM mới với đúng artifact.
10. Thử cùng agent/loader/module graph của deployment.
11. Test counters/probe call frequency, exception propagation.
12. Benchmark startup, CPU, memory/GC và latency.
13. Kiểm tra policies cho PII/secrets và dữ liệu output.
14. Nếu runtime/JVM báo lỗi, CI phải fail chứ không chỉ log warnings.
15. Không phát hành artifact mới nếu bước verifier/runtime regression bị bỏ qua.

## 12. Những hiểu nhầm thường gặp

**1. “`ClassFile.verify` trả empty list nghĩa class chạy đúng.”**  
Không. Nó chỉ nói không phát hiện lỗi verification trong context được dùng.

**2. “`parse(bytes)` trả `ClassModel` nghĩa mọi attribute đều hợp lệ.”**  
Không. Class-File API parse lazily; accessor/verify có thể phát hiện lỗi về sau.

**3. “Verifier bắt được mọi thiếu dependency.”**  
Không. Loader/module và symbolic resolution runtime còn cần test JVM.

**4. “`ClassFile.verify` có ở JDK 17.”**  
Không. API chuẩn được đưa vào JDK 24; đó là yêu cầu tối thiểu cho lab.

**5. “`ClassTransform.ACCEPT_ALL` đã chèn instrumentation.”**  
Không. Nó giữ elements, dùng trong lab để dựng lại bytes.

**6. “Load được class nghĩa mọi method references đã được resolve.”**  
Không. JVM có lazy resolution; branch chưa được gọi vẫn có thể lỗi.

**7. “`-Xverify:all` test được business logic.”**  
Không. Nó là JVM verification option, vẫn cần assertions.

**8. “Bản class trong runtime JAR luôn giống file tôi vừa verify.”**  
Không tự động. Cần kiểm tra artifact/hash, không dùng class trùng trên classpath.

**9. “Default hierarchy resolver luôn đúng với plugin loader.”**  
Không. Nó dựa system loader/reflection, có thể thiếu class metadata của plugin.

**10. “Một classfile hợp lệ để load thì chắc chắn redefine được.”**  
Không. Redefinition có giới hạn schema/capability riêng.

**11. “`NoSuchMethodError` chứng minh `ClassFile.verify` hỏng.”**  
Không nhất thiết. Nó có thể do runtime ABI/helper version không khớp.

**12. “Một lần chạy test trên Java 24 đủ cho server JDK 17.”**  
Không. JDK17 có classfile limits và class loader/module/dependency khác.

**13. “Một lỗi exception trong method đồng nghĩa JVM VerifyError.”**  
Không. `IllegalArgumentException` từ business method là lỗi nghiệp vụ; verifier không loại bỏ nó.

**14. “Chỉ cần viết unit test trực tiếp transformer là đủ.”**  
Không. Cần integration test với đúng chain/JVM/helper/loader khi phát hành.

**15. “Nên tắt verification của JVM để tránh VerifyError.”**  
Không. Điều đó che lỗi bytecode và có thể gây rủi ro; sửa classfile và stack maps.

## 13. Câu hỏi tự luyện

**1.** Các overload của `ClassFile.verify` nhận những gì?  
**Đáp:** `ClassModel`, `byte[]`, `Path`, trả `List<VerifyError>`.

**2.** Khi nào nên verify `Path` thay vì chỉ `byte[]`?  
**Đáp:** Sau khi ghi artifact để tránh kiểm tra mảng bytes khác file triển khai.

**3.** Vì sao `parse` có thể thành công mà `verify` vẫn báo lỗi?  
**Đáp:** Parse có thiết kế lazy và không thực hiện toàn bộ xác minh ngay.

**4.** `ClassFile.verify` có chạy method `Calculator.twice(21)` không?  
**Đáp:** Không. Cần load và invoke method.

**5.** Vì sao lab dùng isolated loader?  
**Đáp:** Để chứng minh candidate bytes đã verify được định nghĩa thực sự, không vô tình nạp bản trên system classpath.

**6.** `Class.forName(...,true,loader)` thêm phép kiểm nào?  
**Đáp:** Yêu cầu initialization trong loader đã chọn.

**7.** Vì sao `Method.invoke` cần bắt `InvocationTargetException`?  
**Đáp:** Đây là wrapper quanh exception do target method ném.

**8.** Vì sao lab dùng thêm JVM mới?  
**Đáp:** Để kiểm tra artifact được nạp từ disk/classpath trong process độc lập, không dùng class đã nạp ở runner cũ.

**9.** `NoClassDefFoundError` có thể xuất hiện khi verifier tĩnh PASS không?  
**Đáp:** Có, vì runtime loader không tìm được dependency/helper.

**10.** Default hierarchy resolver có vấn đề gì với plugin loader?  
**Đáp:** Dùng system loader và reflection, nên có thể không thấy các class riêng của plugin.

**11.** `redefineClasses` chấp nhận mọi classfile verify PASS không?  
**Đáp:** Không. Còn giới hạn schema, class modifiability và capability.

**12.** Tại sao không verify mọi class trực tiếp trong callback transformer?  
**Đáp:** Cost và nguy cơ class loading recursion/deadlock, đặc biệt khi cần hierarchy resolution.

**13.** Nếu JDK24 tạo classfile mới, JVM JDK17 chạy được không?  
**Đáp:** Chỉ khi classfile version và features phù hợp JDK17; thường cần build theo `--release 17` và kiểm thử trên JDK17.

**14.** Tại sao `ClassTransform.ACCEPT_ALL` không đủ chứng minh code injection?  
**Đáp:** Nó không thêm bytecode; muốn chứng minh instrumentation cần transformer thật và runtime tests.

**15.** Kết quả cần lưu khi chẩn đoán một lỗi classfile?  
**Đáp:** Exact candidate hash, JDK version, loader/module, transform chain, verify errors, JVM stack trace và runtime test outcome.

## 14. Tài liệu tham khảo chính thức

- [JDK 24 — `java.lang.classfile.ClassFile`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `parse`, `transformClass`, ba overload `verify`.
- [JDK 24 — `ClassTransform`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): `ACCEPT_ALL` và semantics transform.
- [JDK 24 — `ClassModel`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassModel.html): mô hình classfile và lazy parsing.
- [JDK 24 — `ClassHierarchyResolver`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassHierarchyResolver.html): system default, `ofResourceParsing`, `ofClassLoading`, cache.
- [JDK 24 — `ClassFile.ClassHierarchyResolverOption`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.ClassHierarchyResolverOption.html): cấu hình resolver cho verification/stack maps.
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484): API chuẩn hóa từ JDK 24.
- [JVMS 24 — Verification](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html#jvms-4.10): bytecode/stack map verification.
- [JVMS 24 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-5.html): phases và resolution.
- [JDK 24 — ClassLoader](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ClassLoader.html): `defineClass` và loader identity.
- [JDK 24 — Instrumentation](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): redefine/retransform capability và giới hạn.
- [JDK 24 — java launcher](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html): `-Xverify:all`.

**Ghi nhớ:** Dùng `ClassFile.verify` để bắt lỗi classfile/bytecode sớm, nhưng **đừng dừng ở list rỗng**. Hãy kiểm tra **chính generated bytes** trong đúng JVM/loader/module, chạy các method và exception paths, rồi thử trên một JVM mới với artifact cuối cùng. Verification, linkage, behavior và hiệu năng là **những tầng bằng chứng bổ sung**, không thay thế nhau.