# Tổ chức trình sinh bytecode với hợp đồng kiểu rõ ràng (Java 15+)

## 1. Bài toán: sinh bytecode đúng cú pháp chưa đủ

Trong Java, một trình sinh bytecode (*bytecode generator*) có thể tạo mảng `byte[]` chứa class file rồi đưa nó cho JVM định nghĩa lớp ở thời gian chạy. Từ **Java 15**, `MethodHandles.Lookup.defineHiddenClass` là một API chuẩn để định nghĩa **hidden class** từ class file: phù hợp với những lớp trợ giúp nội bộ, ví dụ adapter, biểu thức được biên dịch động hoặc implementation do framework sinh ra.

Tuy nhiên, “sinh được file `.class`” **chưa đồng nghĩa** lớp sinh ra sử dụng được. Lỗi có thể đến từ:

- Tên package của class file không phù hợp với `Lookup`.
- Phiên bản class file không tương thích runtime.
- Descriptor tham số hoặc kiểu trả về khác với mã gọi.
- Lớp thiếu interface, constructor hoặc phương thức đã cam kết.
- Bytecode không hợp lệ hoặc sai quy tắc JVM verifier.
- JVM chấp nhận cấu trúc lớp nhưng phương thức lại **tính toán sai về mặt nghiệp vụ**.
- Cách khởi tạo `static`, xử lý ngoại lệ hoặc giữ tham chiếu đến hidden class không đúng vòng đời.

Giải pháp có tính mở rộng là đặt **hợp đồng kiểu (*type contract*) ở ranh giới giữa bộ sinh mã và bộ gọi**. Generator phải tạo một class thỏa hợp đồng; phần định nghĩa/tải lớp phải xác minh hợp đồng; phần gọi phải sử dụng đúng chữ ký đã công bố; các bài test phải kiểm tra cả kiểu lẫn kết quả.

Một pipeline hợp lý:

~~~text
Đặc tả nghiệp vụ + Type contract
             |
             v
  Bộ sinh source / bytecode
             |
             v
     byte[] class file
             |
             v
Kiểm tra cấu trúc + giới hạn phiên bản
             |
             v
Lookup.defineHiddenClass(...)
             |
             v
Class<?> + Lookup + contract validation
             |
             v
instance / MethodHandle / API đã định kiểu
             |
             v
       Test hành vi thực tế
~~~

**Điểm then chốt:** `byte[]` chỉ là dữ liệu đầu ra của generator. Hợp đồng thật sự phải diễn tả **những phương thức, tham số, kiểu trả về và khả năng truy cập mà consumer có quyền dựa vào**.

Bài này dùng ví dụ Java 15+ vẫn còn áp dụng hiện nay. Để không cần thư viện bytecode ngoài JDK, chương trình mẫu dùng **`javax.tools.JavaCompiler` để biên dịch nguồn Java trong bộ nhớ thành class bytes**, rồi gọi `defineHiddenClass`. Đây là *một cách tạo bytecode* thông qua compiler, **không phải thao tác trực tiếp viết từng instruction JVM**. Ở dự án lớn, có thể thay bước tạo bytes bằng ASM hoặc Byte Buddy; những phần thiết kế hợp đồng, xác minh và gọi lớp vẫn giữ nguyên.

## 2. Hợp đồng kiểu nên chứa những gì?

Giả sử runtime muốn sinh một phép toán nhận hai số nguyên và trả về số nguyên. Thay vì để consumer gọi theo tên phương thức `"apply"` và đoán chữ ký, hãy công bố interface Java:

~~~java
public interface IntBinaryOp {
    int apply(int left, int right);
}
~~~

Hợp đồng này thể hiện:

1. **Tên operation:** `apply`.
2. **Số tham số:** hai.
3. **Kiểu tham số:** `int, int`, là các primitive 32-bit của Java.
4. **Kiểu trả về:** `int`.
5. **Cơ chế gọi:** phương thức instance thông qua interface; đối tượng implementation phải thực sự implement `IntBinaryOp`.
6. **Giới hạn nghiệp vụ:** riêng interface chưa nói rõ kết quả làm tròn, tràn số hay lỗi; những điều đó cần đặc tả và test bổ sung.

JVM method descriptor tương ứng là `(II)I`. Trong API method handles, chữ ký này được biểu diễn bằng:

~~~java
MethodType expected = MethodType.methodType(
        int.class,
        int.class,
        int.class
);
~~~

`MethodType.methodType(returnType, parameterTypes...)` có **kiểu trả về đứng trước**, tiếp theo là danh sách kiểu tham số. Trong ví dụ, `expected` là `(int,int)int`.

**Hai lớp bảo vệ bổ trợ nhau:**

- Interface `IntBinaryOp` tạo hợp đồng **Java-level**: implementation phải có `int apply(int,int)`, compiler và JVM có thể kiểm tra.
- `MethodType` tạo hợp đồng **invoke-level**: khi sử dụng `MethodHandle`, consumer biết chính xác kiểu tham số và kiểu trả về, không phải đoán từ `Object`.

Ở framework phức tạp, đặc tả còn có thể gồm mã phiên bản contract, chính sách nullability với reference types, checked exceptions, quy tắc xử lý overflow, tính thuần của hàm và ràng buộc thread safety. Những phần **không được Java type system thể hiện** phải được ghi thành hợp đồng nghiệp vụ và kiểm thử riêng.

## 3. Tách trách nhiệm thành các tầng có thể kiểm thử

Không nên gom mọi việc vào một hàm khổng lồ “sinh mã rồi gọi”. Một tổ chức dễ bảo trì gồm:

| Tầng | Đầu vào | Đầu ra / trách nhiệm | Kiểm tra phù hợp |
| --- | --- | --- | --- |
| **Contract** | Yêu cầu chức năng | Interface, `MethodType`, quy tắc hành vi | Compile-time API tests và contract tests. |
| **Generator** | Contract + dữ liệu cấu hình | Class bytes `byte[]` | Sinh bytes hợp lệ, đúng class name/package, target class-file version. |
| **Definition** | Bytes + `Lookup` | `Lookup` của hidden class và `Class<?>` | `defineHiddenClass` thành công, quyền truy cập đúng, lỗi link/verify được xử lý. |
| **Validation** | `Class<?>` + contract | Kết luận implementation dùng được | `isAssignableFrom`, `findConstructor`, `findVirtual`/`MethodType`. |
| **Invocation** | Instance/handle + input | Kết quả hoặc lỗi có kiểm soát | Đúng descriptor, đúng `invokeExact`, đúng semantics. |
| **Lifecycle** | Reference tới lớp, handle và cache | Quản lý vòng đời lớp sinh động | Không cache vô hạn, lựa chọn initialization/unloading theo mục đích. |

Trong dự án thật, generator có thể nhận một đối tượng đặc tả, ví dụ:

~~~java
// Minh hoa API thiet ke, khong phai chuong trinh doc lap.
interface BytecodeGenerator {
    byte[] generate(OperationContract contract);
}
~~~

`OperationContract` ở đây là **kiểu miền nghiệp vụ do dự án định nghĩa**, không phải kiểu có sẵn trong JDK. Nếu muốn API này chạy được, bạn phải cung cấp định nghĩa cụ thể, versioning, validation và các implementation phù hợp. Ví dụ đầy đủ bên dưới dùng một interface Java có sẵn thay vì thêm kiểu đặc tả giả.

**Quy tắc quan trọng:** Mọi producer phải thống nhất một contract với consumer. Nếu generator sinh một chữ ký khác, hãy báo lỗi ở **bước compile/verify/validation**, thay vì âm thầm tự ép kiểu hoặc để lỗi xảy ra ngẫu nhiên sau này.

## 4. Ví dụ đầy đủ: sinh class bytes trong bộ nhớ và áp hợp đồng kiểu

Mục tiêu: ở runtime, sinh một lớp triển khai `IntBinaryOp`, gọi được bằng interface và `MethodHandle`, đồng thời dùng `Math.addExact` để bắt lỗi tràn số. Ví dụ dùng các API chuẩn của Java 15, không cần thư viện ngoài JDK.

Vì `defineHiddenClass` yêu cầu class bytes mô tả lớp trong **cùng package** với `Lookup`, ví dụ sử dụng package `demo.codegen` cho cả class chính và class được sinh.

### 4.1. Cấu trúc và chạy chương trình

Tạo đúng một file:

~~~text
demo/
  codegen/
    BytecodeContractDemo.java
~~~

Nội dung **`demo/codegen/BytecodeContractDemo.java`**:

~~~java
package demo.codegen;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class BytecodeContractDemo {
    public interface IntBinaryOp {
        int apply(int left, int right);
    }

    private static final String GENERATED_NAME =
            "demo.codegen.GeneratedAdder";

    private static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String binaryName, String code) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') +
                    Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private static final class Bytecode extends SimpleJavaFileObject {
        private final ByteArrayOutputStream buffer =
                new ByteArrayOutputStream();

        Bytecode(String binaryName, Kind kind) {
            super(URI.create("memory:///" +
                    binaryName.replace('.', '/') +
                    kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return buffer;
        }

        byte[] getBytes() {
            return buffer.toByteArray();
        }
    }

    private static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private Bytecode output;

        MemoryManager(StandardJavaFileManager fileManager) {
            super(fileManager);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {
            if (!GENERATED_NAME.equals(className)
                    || kind != JavaFileObject.Kind.CLASS) {
                throw new IOException(
                        "Unexpected compiled class: " + className);
            }
            output = new Bytecode(className, kind);
            return output;
        }

        byte[] getClassBytes() {
            if (output == null) {
                throw new IllegalStateException(
                        "No class bytes were emitted");
            }
            return output.getBytes();
        }
    }

    static byte[] generateBytecode() throws IOException {
        String source = """
                package demo.codegen;
                public final class GeneratedAdder
                        implements BytecodeContractDemo.IntBinaryOp {
                    public GeneratedAdder() {}

                    @Override
                    public int apply(int left, int right) {
                        return Math.addExact(left, right);
                    }
                }
                """;

        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Requires a JDK with JavaCompiler");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager standard =
                    compiler.getStandardFileManager(
                            diagnostics,
                            Locale.ROOT,
                            StandardCharsets.UTF_8);
                MemoryManager manager =
                    new MemoryManager(standard)) {

            List<String> options = List.of(
                    "--release", "15",
                    "-classpath",
                    System.getProperty("java.class.path"));

            Boolean ok = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    options,
                    null,
                    List.of(new Source(GENERATED_NAME, source))
            ).call();

            if (!Boolean.TRUE.equals(ok)) {
                throw new IllegalStateException(
                        "Generated source invalid: " +
                                diagnostics.getDiagnostics());
            }

            return manager.getClassBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = generateBytecode();

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup()
                        .defineHiddenClass(bytes, true);

        Class<?> hiddenClass = hiddenLookup.lookupClass();

        if (!hiddenClass.isHidden()
                || !IntBinaryOp.class.isAssignableFrom(
                        hiddenClass)) {
            throw new IllegalStateException(
                    "Contract not satisfied");
        }

        MethodHandle constructor =
                hiddenLookup.findConstructor(
                        hiddenClass,
                        MethodType.methodType(void.class));
        IntBinaryOp operation =
                (IntBinaryOp) constructor.invoke();

        MethodType signature = MethodType.methodType(
                int.class, int.class, int.class);

        MethodHandle apply =
                MethodHandles.lookup().findVirtual(
                        IntBinaryOp.class,
                        "apply",
                        signature);

        System.out.println(
                "hidden=" + hiddenClass.isHidden());
        System.out.println(
                "contract=" +
                        (operation instanceof IntBinaryOp));
        System.out.println(
                "result=" + operation.apply(7, 5));
        System.out.println(
                "handle=" +
                        (int) apply.invokeExact(operation, 7, 5));

        try {
            operation.apply(Integer.MAX_VALUE, 1);
            System.out.println("overflow=missed");
        } catch (ArithmeticException ex) {
            System.out.println("overflow=detected");
        }
    }
}
~~~

Biên dịch và chạy từ **thư mục cha chứa `demo/`**:

~~~bash
javac --release 15 -encoding UTF-8 demo/codegen/BytecodeContractDemo.java
java -cp . demo.codegen.BytecodeContractDemo
~~~

Chạy cần **JDK có module `jdk.compiler`**; `ToolProvider.getSystemJavaCompiler()` có thể trả `null` trong runtime image không chứa trình biên dịch. Ví dụ đã kiểm chứng trên **JDK 24** với `javac --release 15`.

Đầu ra chính xác:

~~~text
hidden=true
contract=true
result=12
handle=12
overflow=detected
~~~

Đoạn mã không tạo file `GeneratedAdder.java` hay `GeneratedAdder.class` trên đĩa. `Source` cung cấp nguồn Java cho compiler; `MemoryManager` hứng bytecode `.class` qua `ByteArrayOutputStream`. Sau khi compiler trả về mảng bytes, `defineHiddenClass` định nghĩa chúng thành **hidden class**, và chương trình gọi class đó thông qua contract đã công bố.

### 4.2. Cơ chế từng bước

**Bước 1 — Contract được khai báo trước generator.** `IntBinaryOp` là interface có một phương thức `int apply(int,int)`. Đoạn nguồn được sinh dùng `implements BytecodeContractDemo.IntBinaryOp` và `@Override`. Nếu đổi phương thức thành `long apply(long,long)` mà vẫn giữ interface, bước biên dịch sẽ thất bại trước khi chạy mã.

**Bước 2 — Generator trả class bytes, không trả đối tượng tùy ý.** `generateBytecode()` có kiểu trả về `byte[]`. `JavaCompiler` gọi một `JavaFileManager` tùy biến để ghi bytecode vào bộ nhớ. `GENERATED_NAME` được dùng đồng nhất ở nguồn và bộ quản lý đầu ra, đồng thời bộ quản lý từ chối các class phụ không mong đợi. Đây là chính sách có chủ ý của **ví dụ một lớp**; nếu sinh nhiều class hoặc lambda/nested class, trình quản lý đầu ra phải hỗ trợ một map các binary names thay vì chỉ một buffer.

**Bước 3 — Chốt class-file target.** `--release 15` kiểm tra ngôn ngữ và API tương thích Java 15 và tạo class file target phù hợp. Trong dự án, hãy xác định JDK thấp nhất mà runtime phải hỗ trợ. Class file sinh cho Java mới hơn không tự tương thích ngược với runtime cũ.

**Bước 4 — Định nghĩa bằng đúng `Lookup`.** `MethodHandles.lookup()` được gọi trong `BytecodeContractDemo` cùng package `demo.codegen` với class được sinh. `defineHiddenClass(bytes, true)` yêu cầu `Lookup` có *full privilege access*, class bytes hợp lệ và package phù hợp. Ở đây `true` yêu cầu khởi tạo hidden class ngay trong lời gọi; nó không thay đổi chữ ký phương thức.

**Bước 5 — Kiểm tra contract trước khi gọi.** `hiddenClass.isHidden()` xác nhận kiểu mới là hidden class; `IntBinaryOp.class.isAssignableFrom(hiddenClass)` xác nhận kiểu mới triển khai interface đã thỏa thuận. Nếu điều kiện không đúng, caller báo lỗi thay vì tiếp tục gọi một implementation sai.

**Bước 6 — Tìm constructor đúng kiểu.** `findConstructor(hiddenClass, MethodType.methodType(void.class))` yêu cầu constructor không tham số. Việc cast kết quả `constructor.invoke()` sang `IntBinaryOp` có thể thực hiện sau khi JVM xác nhận quan hệ kiểu.

**Bước 7 — Gọi theo interface hoặc `MethodHandle`.** `operation.apply(7,5)` là lời gọi Java có kiểm tra kiểu; `MethodHandles.lookup().findVirtual(IntBinaryOp.class, "apply", signature)` trả handle cho phương thức interface. `invokeExact(operation,7,5)` yêu cầu các kiểu đúng chính xác tại call site.

**Bước 8 — Kiểm tra nghiệp vụ.** `Math.addExact` trả 12 cho 7+5 và ném `ArithmeticException` khi phép cộng `int` tràn phạm vi. Contract kiểu `int apply(int,int)` **không tự bảo đảm** cách xử lý tràn số; test nghiệp vụ mới xác nhận phần đó.

## 5. `MethodType` và `invokeExact`: chỗ hợp đồng kiểu hay bị phá vỡ

### 5.1. Descriptor của method handle có cả receiver

`MethodType.methodType(int.class,int.class,int.class)` mô tả **chữ ký khai báo** `int apply(int,int)`.

Khi dùng:

~~~java
MethodHandle handle = MethodHandles.lookup()
        .findVirtual(IntBinaryOp.class, "apply", signature);
~~~

thì **kiểu của handle** thực tế có thêm receiver ở đầu:

~~~text
(IntBinaryOp, int, int)int
~~~

Bởi vậy, lời gọi:

~~~java
int value = (int) handle.invokeExact(operation, 7, 5);
~~~

phải được biên dịch với `operation` có kiểu tĩnh `IntBinaryOp`, hai `int` và kiểu trả về `int`. `invokeExact` là phương thức signature-polymorphic: kiểu tĩnh của tham số và ngữ cảnh trả về được dùng để tạo descriptor của call site.

**Không lẫn `invokeExact` với `invoke`:**

- `invokeExact` yêu cầu descriptor của call site **trùng tuyệt đối** với kiểu của handle, nếu không có thể ném `WrongMethodTypeException`.
- `invoke` cho phép một số chuyển đổi kiểu theo quy tắc method handles, nhưng không thể biến một hợp đồng sai thành đúng về nghiệp vụ.

Ví dụ sử dụng biến tham số `Object obj = operation;` rồi gọi `handle.invokeExact(obj, 7, 5)` sẽ có receiver tĩnh là `Object`, **không trùng** `IntBinaryOp`, nên lỗi dù object runtime vẫn chứa implementation phù hợp.

Một phương án nếu không muốn method handles là gọi trực tiếp `IntBinaryOp.apply`. Đây thường là cách **rõ hợp đồng nhất** khi consumer có thể phụ thuộc vào interface.

### 5.2. Nhầm `findVirtual` và `findStatic`

Bài toán dùng **phương thức instance** `apply`, vì vậy `findVirtual` là phù hợp. Nếu generator tạo `public static int apply(int,int)` thì hợp đồng phải đổi theo hướng đó; không thể vừa dựa vào interface instance `IntBinaryOp` vừa mặc định coi implementation là phương thức static.

Đối với phương thức static, API thường dùng là `Lookup.findStatic(ownerClass, "apply", methodType)` và handle **không có receiver**. Chọn từ đầu: contract theo interface instance, static utility hay factory. Không trộn hai kiểu mà không có lớp adapter rõ ràng.

### 5.3. Runtime validation không thay thế verifier

`isAssignableFrom` và `findVirtual` kiểm tra quan hệ kiểu, member tồn tại và quyền truy cập theo API. JVM verifier kiểm tra những ràng buộc cấu trúc bytecode khác như kiểu operand stack, local variables và luồng điều khiển.

Nhưng **verifier không chứng minh ý nghĩa nghiệp vụ**. Một phương thức `int apply(int,int)` trả `0` cho mọi input có thể là bytecode hợp lệ và thỏa interface, dù hoàn toàn sai yêu cầu cộng hai số.

Vì thế cần ba lớp kiểm tra:

1. **Class-file/bytecode validation:** sinh class hợp lệ và được JVM chấp nhận.
2. **Type-contract validation:** method, descriptor, interface và quyền truy cập đúng.
3. **Behavior-contract validation:** test logic, exception, edge case và hiệu năng theo yêu cầu.

## 6. Khi generator dùng ASM, Byte Buddy hoặc trình biên dịch nguồn

Trong hệ thống thực tế, bước tạo `byte[]` có thể thực hiện theo các cách khác nhau. Hãy chọn dựa vào độ phức tạp của mã và mức kiểm soát cần thiết:

| Cách tiếp cận | Đầu ra và kiểm soát | Điểm cần chú ý |
| --- | --- | --- |
| `JavaCompiler` qua `javax.tools` | Biên dịch Java source thành class bytes; tận dụng type checker và diagnostics của `javac`. | Cần compiler trên runtime; chi phí biên dịch và quản lý classpath/modules. |
| **ASM** (thư viện bytecode) | Tạo và biến đổi instruction, descriptor và metadata của JVM trực tiếp. | Quản lý class-file version, frames/stack, descriptor, verifier; cần kiến thức bytecode sâu. |
| **Byte Buddy** (thư viện sinh mã) | API ở mức cao để định nghĩa/triển khai type, method và interceptor; có thể lấy class bytes từ type được sinh. | Phải hiểu cách framework resolve type, class loading/hidden class integration và version thư viện. |
| Sinh source/file `.class` ở build-time | Tách sinh mã khỏi lúc ứng dụng chạy. | Phù hợp khi cấu trúc type biết trước và không cần biến đổi động theo từng request. |

**Bài mẫu dùng `JavaCompiler` chỉ để minh họa pipeline**, không hàm ý rằng các trình sinh bytecode production đều phải sinh source trước. Nếu dùng ASM/Byte Buddy, vẫn nên giữ `IntBinaryOp` hoặc một hợp đồng tương đương ổn định ở ranh giới producer–consumer.

Ví dụ với generator trực tiếp phát ra JVM bytecode:

- Phần khai báo `implements` phải nêu đúng interface.
- Phương thức `apply` phải có descriptor `(II)I`, tên và visibility chính xác.
- Constructor phải tồn tại nếu consumer tìm constructor không tham số.
- Mỗi instruction, kiểu trên operand stack và stack map frames phải hợp lệ.
- Class-file major version phải phù hợp runtime.
- Nếu class dùng API hoặc module khác, tham chiếu kiểu phải resolve được khi liên kết và sử dụng.

Không dựa vào tên phương thức giống nhau như một bảo đảm hợp đồng: `apply(int,int)` và `apply(long,long)` là **hai descriptor khác nhau**. `apply(int,int)` trả `long` cũng khác chữ ký đã cam kết.

## 7. Điều kiện riêng khi định nghĩa hidden class ở Java 15+

Khi consumer sử dụng `Lookup.defineHiddenClass`, cần đặt thêm các ràng buộc vòng đời và quyền truy cập vào hợp đồng kỹ thuật.

### 7.1. Cùng runtime package và quyền `Lookup`

Class bytes phải có tên class thuộc **cùng package** với lookup class. `Lookup` cần **full privilege access**. Trong ví dụ, lớp chính và tên class được sinh đều thuộc `demo.codegen`.

Nếu lớp được sinh vào `other.package` nhưng `MethodHandles.lookup()` chạy trong `demo.codegen`, `defineHiddenClass` không phải cơ chế “tự chuyển class sang package của mình”. Thao tác sẽ không đáp ứng điều kiện API. Nếu môi trường dùng Java modules có ranh giới quyền truy cập, thiết kế lookup/module context đúng thay vì tìm cách vượt quyền.

### 7.2. Hidden class có identity riêng, không tra theo tên bình thường

`defineHiddenClass` tạo **class ẩn mới** từ mảng bytes. Nó có `Class<?>` riêng và vẫn có thể implement một interface bình thường như `IntBinaryOp`. Không kỳ vọng `Class.forName("demo.codegen.GeneratedAdder")` tìm được hidden class đó theo đường dẫn nạp class có tên thông thường.

Vì vậy, consumer nên giữ **`Class<?>` / `Lookup` / instance / handle** cần thiết thay vì tự ghép tên để tìm lại. Tránh phụ thuộc vào chuỗi tên debug của hidden class như một identifier ổn định cho nghiệp vụ.

### 7.3. Khởi tạo lớp không phải kiểm tra contract

Tham số `initialize` trong `defineHiddenClass(bytes, true)` yêu cầu **khởi tạo lớp ngay trước khi phương thức trả bình thường**; `false` không chủ động khởi tạo ở bước đó. Nó **không chọn kiểu phương thức** và **không làm bytes hợp lệ hơn**.

Nếu class có `static { ... }`, chọn `true` có thể kích hoạt side effects ngay lúc định nghĩa; chọn `false` có thể trì hoãn lỗi khởi tạo đến khi được sử dụng. Cần tài liệu hóa chính sách này và kiểm tra riêng nếu nó quan trọng.

### 7.4. Vòng đời và cache

Hidden class mặc định có thể được dỡ riêng khi không còn được giữ sống, kể cả khi defining class loader vẫn sống; dùng `MethodHandles.Lookup.ClassOption.STRONG` khi cần vòng đời gắn chặt với loader như class thông thường.

Lưu `Class<?>`, `Lookup`, `MethodHandle` hoặc instance trong cache có thể kéo dài vòng đời hidden class. Một generator tạo một lớp mới cho từng request nhưng cache mọi handle vô hạn có thể gây áp lực class metadata/metaspace. Chỉ cache theo scope và chính sách cần thiết, và không đặt unit test phụ thuộc vào thời điểm GC/unload.

`ClassOption.NESTMATE` điều chỉnh quan hệ nest access, **khác** `STRONG` và khác `initialize`. Các tùy chọn này không làm thay đổi contract `IntBinaryOp` trừ khi quyền truy cập thực tế vào class/member là phần của đặc tả hệ thống.

## 8. Quản lý lỗi theo từng ranh giới pipeline

Một code generator được tổ chức tốt phải biết **lỗi xảy ra ở tầng nào**, để có thể báo cho người vận hành và viết test mục tiêu.

| Triệu chứng / exception | Tầng lỗi thường gặp | Hành động |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | Môi trường thiếu compiler | Chạy trên JDK có module `jdk.compiler` hoặc dùng bộ sinh bytecode không cần `javac`. |
| `JavaCompiler.getTask(...).call()` trả `false` | Source được sinh không biên dịch | Thu thập `DiagnosticCollector`; kiểm tra tên class, `@Override`, import và classpath. |
| `UnsupportedClassVersionError` | Class file target cao hơn runtime hỗ trợ | Tạo bytes phù hợp runtime đích; kiểm soát class-file version. |
| `ClassFormatError` hoặc `VerifyError` | Bytes/bytecode cấu trúc không hợp lệ | Kiểm tra emitter, frame, descriptor, instruction và class file. |
| `IllegalAccessException` tại `defineHiddenClass` | `Lookup` không đủ quyền | Tạo lookup đúng runtime/module/package, không cố vượt kiểm soát truy cập. |
| `IllegalArgumentException` do class package không phù hợp | Class bytes không cùng package với `Lookup` | Đặt package đúng ở generator và xác minh trước định nghĩa. |
| `IntBinaryOp.class.isAssignableFrom(hiddenClass) == false` | Thiếu contract interface | Từ chối class sinh ra; sửa generator để implement contract. |
| `NoSuchMethodException` tại `findConstructor` hoặc `findVirtual` | Member/descriptor cần dùng không có | Đồng bộ chữ ký trong contract và bytecode. |
| `WrongMethodTypeException` từ `invokeExact` | Call-site descriptor không khớp handle | Kiểm tra kiểu tĩnh receiver, tham số, kiểu trả về. |
| `ClassCastException` khi cast instance | Không thỏa type relationship cần thiết | Kiểm tra contract trước khi cast; tránh ép kiểu mù. |
| `ExceptionInInitializerError` / lỗi khởi tạo | Logic `static` trong lớp sinh ra lỗi | Tách lỗi khởi tạo khỏi lỗi verifier/generator, ghi lại cause. |
| Sai kết quả nhưng class chạy được | Hợp đồng hành vi chưa được đáp ứng | Thêm test input, boundary/overflow và đối chiếu oracle. |

**Đừng nuốt mọi `Throwable` rồi xem như “bytecode lỗi”.** `Throwable` có thể đến từ generator, linker, initializer, phương thức nghiệp vụ hoặc tài nguyên runtime; log và phân loại chính xác mới giúp sửa đúng tầng.

Trong chương trình mẫu, `main throws Throwable` chỉ giúp ví dụ gọn khi gọi `MethodHandle.invoke`/`invokeExact`. **Ứng dụng production** nên phân tách exception theo ranh giới, không sử dụng `throws Throwable` như thiết kế xử lý lỗi mặc định.

## 9. Bảo mật và dữ liệu không tin cậy

JVM verifier kiểm tra những quy tắc hợp lệ của class file và an toàn kiểu nhất định, **không biến bytecode tùy ý thành mã đáng tin cậy**. Một class được định nghĩa hợp lệ vẫn có thể đọc dữ liệu nhạy cảm, thực hiện I/O hoặc chạy vòng lặp tốn CPU nếu code được phép và được gọi.

Do đó:

- Chỉ định nghĩa class bytes từ **nguồn đáng tin cậy** hoặc qua quy trình kiểm soát chặt.
- Giới hạn những thành phần bytecode mà generator được phép tạo; kiểm thử allowlist các operation khi nhận yêu cầu động.
- Không coi `defineHiddenClass` là sandbox an ninh hoặc cách vượt module access.
- Không dùng chuỗi đầu vào của người dùng để chắp nguồn Java tùy ý rồi compile khi không có chiến lược kiểm soát injection và thực thi.
- Kiểm soát kích thước bytecode, số class được sinh, thời gian compile, bộ nhớ và concurrency của generator.
- Không đưa toàn bộ nguồn hoặc dữ liệu nhạy cảm vào diagnostic logs nếu có nguy cơ tiết lộ.

Ở bài mẫu, đoạn source được sinh là **hằng do chương trình kiểm soát** và implementation dùng `Math.addExact`. Nếu nguồn đó được ghép từ input không tin cậy, một type contract đúng **không bảo đảm** implementation an toàn.

## 10. Kiểm thử hợp đồng: từ compile-time đến runtime

Một bộ test nên gồm các tầng dưới đây.

### 10.1. Test cấu trúc contract

Kiểm tra generator phát ra bytes mà `defineHiddenClass` chấp nhận:

- Class nằm trong đúng package.
- Interface cần thiết có thể được triển khai và resolve.
- Method name và descriptor đúng.
- Constructor/phương thức factory cần thiết tồn tại.
- Class-file version được hỗ trợ.
- `Class<?>` thực sự thỏa `IntBinaryOp.class.isAssignableFrom`.

**Negative test hữu ích:** cố tình cho generator tạo `public long apply(long,long)` nhưng khai báo `implements IntBinaryOp`. Với JavaCompiler và `@Override`, compilation phải thất bại; với emitter trực tiếp, verifier/validation phải phát hiện hoặc việc sử dụng không đúng contract bị từ chối.

### 10.2. Test invocation và semantics

Cho implementation chạy qua **đúng API mà consumer sẽ dùng**. Với ví dụ:

| Đầu vào | Kết quả / hành vi kỳ vọng |
| --- | --- |
| `apply(7, 5)` | `12`. |
| `apply(0, 0)` | `0`. |
| `apply(-4, 2)` | `-2`. |
| `apply(Integer.MAX_VALUE, 1)` | Ném `ArithmeticException` với implementation `Math.addExact`. |
| `apply(Integer.MIN_VALUE, -1)` | Ném `ArithmeticException`. |

Ngoài ra, so sánh kết quả gọi qua interface với kết quả gọi qua `MethodHandle`. Điều này không có nghĩa kiểm thử hai đường gọi là đủ cho mọi generator; cần test cụ thể các input nghiệp vụ và đường lỗi.

### 10.3. Test phiên bản và môi trường

- Biên dịch với target Java được công bố, ví dụ `--release 15`.
- Chạy trên JDK đích mà ứng dụng yêu cầu.
- Kiểm thử khi compiler không có (nếu deployment có runtime image tối giản), khi classpath/module path thiếu contract, và khi generator không trả class bytes.
- Nếu đổi version của interface, phải có chiến lược compatibility: tạo contract version mới, tái sinh lớp hoặc từ chối bytes không tương thích, chứ không tự cast bất chấp.
- Nếu chạy đa luồng, kiểm tra cách cache bytecode, compiler/file manager và instance được sử dụng; tránh chia sẻ state không được thiết kế thread-safe.

**Lưu ý:** Code sample `MemoryManager` được thiết kế cho **một lần sinh một class**, không phải thư viện hoàn chỉnh cho multi-output compiler hoặc concurrent compilation. Trong production, manager và output buffers nên gắn riêng với từng compilation task, lưu theo binary class name và xử lý diagnostics có cấu trúc.

## 11. Những lỗi thiết kế phổ biến

| Lỗi | Vì sao khó bảo trì hoặc nguy hiểm? | Cách làm đúng |
| --- | --- | --- |
| Chỉ mô tả hợp đồng bằng `String methodName` | Thiếu receiver/descriptor, sai overload và return type. | Dùng interface và `MethodType` rõ ràng. |
| Để generator tự quyết định tên class, package, method độc lập với consumer | Dễ vỡ tích hợp khi đổi một phía. | Dùng contract chung và versioning khi cần. |
| Sinh bytecode rồi gọi ngay, không validate | Lỗi xuất hiện muộn và khó truy nguyên. | Tách bước define, validate và invoke. |
| Dùng `Object` ở mọi nơi rồi ép kiểu | Mất thông tin kiểu tĩnh và dễ sai `invokeExact`. | Ưu tiên interface hoặc type-specific handle. |
| Tưởng JVM verifier kiểm tra phép cộng “đúng nghiệp vụ” | Verifier kiểm tra tính hợp lệ của bytecode, không kiểm chứng thuật toán. | Viết test semantics/boundary. |
| Nhầm `findStatic` với `findVirtual` | Static và instance có descriptor/receiver khác. | Xác định rõ kiểu operation trước khi sinh. |
| Sinh class file cho JDK mới rồi tải ở JDK cũ | Không hỗ trợ major version mới. | Chọn target release từ đầu. |
| Tạo class package khác rồi gọi `defineHiddenClass` | Vi phạm yêu cầu same package/lookup access. | Sinh class trong đúng runtime package. |
| Dùng `Class.forName` để tìm hidden class | Hidden class không được tìm như class có tên thông thường. | Giữ `Lookup`/`Class<?>`/typed instance. |
| Không phân biệt `initialize` với policy unloading | Thời điểm chạy `static` khác quan hệ class/loader. | Chọn initialization và `STRONG` riêng. |
| Cache mọi hidden class/handle vô hạn | Có thể giữ class metadata lâu, tốn metaspace. | Thiết kế cache và vòng đời rõ ràng. |
| Coi type contract là sandbox | Class hợp lệ có thể có side effects bất kỳ. | Chỉ xử lý mã tin cậy và kiểm soát thực thi. |

## 12. Tự kiểm tra

**Câu 1.** Vì sao generator nên tạo class `implements IntBinaryOp` thay vì chỉ có phương thức tên `apply`?

**Trả lời:** Interface đặt hợp đồng kiểu mà Java compiler/JVM có thể xác minh, gồm tên, số tham số và kiểu. Phương thức chỉ “trùng tên” chưa chứng minh đủ chữ ký và khả năng gọi mà consumer cần.

**Câu 2.** Chữ ký `MethodType.methodType(int.class,int.class,int.class)` nghĩa là gì?

**Trả lời:** Phương thức **trả `int`** và nhận hai tham số `int`. `MethodType` đặt return type đầu tiên. Với `findVirtual(IntBinaryOp.class, "apply", signature)`, kiểu của handle còn có receiver `IntBinaryOp` ở đầu khi gọi.

**Câu 3.** `invokeExact` có tự động chấp nhận biến tham số tĩnh kiểu `Object` nếu đối tượng runtime implement `IntBinaryOp` không?

**Trả lời:** Không. `invokeExact` yêu cầu descriptor ở call site trùng chính xác với handle. Biến tĩnh kiểu `Object` tạo call-site receiver khác `IntBinaryOp`; cần giữ kiểu tĩnh phù hợp hoặc có chuyển đổi handle rõ ràng.

**Câu 4.** `defineHiddenClass(bytes, true)` bảo đảm điều gì mà `false` không chủ động làm?

**Trả lời:** `true` yêu cầu JVM **khởi tạo hidden class ngay trong lời gọi** trước khi trả bình thường. Cả hai vẫn phải định nghĩa/liên kết lớp; việc chạy khởi tạo không thay thế xác thực contract.

**Câu 5.** Dùng `JavaCompiler` để tạo bytes ở runtime có phải là viết instruction bytecode thủ công không?

**Trả lời:** Không. Đây là biên dịch Java source thành class bytes thông qua compiler. Với generator viết instruction trực tiếp như ASM, vẫn nên giữ cùng contract và validation pipeline.

**Câu 6.** Lớp sinh ra implement đúng interface nhưng trả sai kết quả thì hệ thống đã an toàn chưa?

**Trả lời:** Chưa. Interface và JVM verifier kiểm tra quan hệ kiểu và tính hợp lệ cấu trúc, nhưng **không chứng minh đúng logic nghiệp vụ**. Cần behavioral tests và kiểm soát nguồn mã.

## Ghi nhớ

- **Hợp đồng kiểu phải được định nghĩa trước khi sinh bytecode.** Dùng interface, method descriptor/`MethodType` và semantics được ghi rõ.
- **Tách generator → class bytes → define → validate → invoke → test.** Mỗi ranh giới có lỗi, kiểm tra và thông báo riêng.
- **`invokeExact` rất nghiêm ngặt về kiểu.** Với handle phương thức instance, receiver cũng thuộc chữ ký khi gọi.
- **`defineHiddenClass` yêu cầu `Lookup` có quyền và class bytes trong cùng package**, đồng thời tạo một class identity riêng.
- **Bytecode hợp lệ không tự động đúng nghiệp vụ hay an toàn.** Test edge cases và không dùng hidden class làm sandbox.
- **JavaCompiler, ASM, Byte Buddy là những cách tạo bytes khác nhau; hợp đồng kiểu và kiểm soát vòng đời vẫn thiết yếu.**

### Tài liệu chuẩn còn áp dụng

- [Oracle Java — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, `findVirtual`, `findStatic`, `findConstructor` và yêu cầu truy cập.
- [Oracle Java — MethodType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html): descriptor và cách xác định tham số/return type.
- [Oracle Java — MethodHandle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `invoke`, chuyển đổi kiểu và ngoại lệ.
- [Oracle Java — JavaCompiler](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): API compiler, `JavaFileManager`, diagnostics và compilation task.
- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): hidden classes được chuẩn hóa từ Java 15.
- [Java Virtual Machine Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): descriptor, class-file structures, verification-related constraints.
