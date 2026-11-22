# 16.1 Khi nào cần `JavaCompiler` thay cho reflection hoặc tạo proxy

## 1. Mục tiêu: chọn đúng công cụ cho thay đổi lúc chạy

Trong module **Java Advance – dynamic-runtime**, ba nhóm API dễ bị nhầm lẫn là:

- **Reflection** (`java.lang.reflect`): khám phá và thao tác với **class, constructor, field, method đã tồn tại** trong bytecode được nạp hoặc có thể nạp.
- **JDK dynamic proxy** (`java.lang.reflect.Proxy`, `InvocationHandler`): tạo một object triển khai **interface đã tồn tại**, rồi chuyển những lời gọi interface vào một handler tại runtime.
- **JavaCompiler** (`javax.tools.JavaCompiler`, JSR 199): **biên dịch Java source mới tại runtime** thành bytecode `.class`, sau đó có thể dùng class loader để nạp và thực thi.

Ba cơ chế đều hỗ trợ ứng dụng linh hoạt, nhưng **chúng không giải quyết cùng một bài toán**. Bạn không cần trình biên dịch chỉ để gọi một method không biết tên từ trước, hoặc để bọc logging quanh interface; ngược lại, Reflection không thể tự biến một đoạn Java source mới thành method bytecode mới.

Sau bài này, bạn cần trả lời được: *“Tôi cần tìm/gọi thứ đã có, chặn một giao diện đã có, hay định nghĩa một implementation mới chưa từng được biên dịch?”* Đồng thời, bạn sẽ biết quy trình dùng `ToolProvider.getSystemJavaCompiler()`, `StandardJavaFileManager`, `DiagnosticCollector`, `JavaCompiler.CompilationTask`, `URLClassLoader`, quản lý tài nguyên và hạn chế bảo mật.

> **Quy tắc chọn nhanh:** Nếu logic đã tồn tại dưới dạng class/method thì ưu tiên Reflection hoặc gọi tĩnh thông thường. Nếu muốn bọc một interface bằng chính sách chung thì cân nhắc JDK Proxy. Chỉ chọn `JavaCompiler` khi bạn thực sự cần **mã Java mới**, với chi phí biên dịch, quản trị class loader và rủi ro thực thi mã đó được chấp nhận.

## 2. So sánh bản chất ba cơ chế

| Tiêu chí | Reflection | JDK Proxy | `JavaCompiler` |
| --- | --- | --- | --- |
| Đầu vào chính | `Class`/`Method`/`Field`/`Constructor` đã có | Các **interface đã có** và `InvocationHandler` | **Java source** cùng options/classpath/module path |
| Có tạo bytecode implementation mới không? | Không; nó tìm và gọi thành viên đã được định nghĩa | **Có**, JDK tạo proxy class cho interface; nhưng hành vi do handler quyết định | **Có**, compiler chuyển source tùy biến thành class thực |
| Có thể thêm một method body Java mới vào class đã load? | Không | Không; handler xử lý các interface methods đã xác định | Có thể **biên dịch một class mới** với method body mới; không vá class cũ đang load chỉ bằng compiler |
| Kiểu mà caller nhìn thấy | Kiểu trả về từ `Method.invoke` thường là `Object` | Interface được khai báo | Class/interface do code được sinh ra triển khai |
| Trường hợp phù hợp | Plugin đã biên dịch, tìm method theo annotation, gọi method theo tên | Logging, retry, metrics, authorization, lazy delegation qua interface | Sinh mã chuyên biệt theo schema/DSL được tin cậy, compile một implementation Java mới |
| Phụ thuộc công cụ build lúc runtime | Không cần `jdk.compiler` | Không cần `jdk.compiler` | Cần compiler provider, thường trong module JDK `jdk.compiler` |
| Chi phí/runtime | Lookup/Reflection invoke; có thể cache metadata | Tạo proxy một lần, qua handler mỗi lời gọi | **Compile + lưu/nhận bytecode + load class**, chi phí đáng kể trước khi gọi |
| Rủi ro chính | Access control, sai method/overload, reflection invocation exception | Recursion ở handler, Object methods, giới hạn interface | Java source injection, diagnostics, classpath, loading, memory/classloader leaks, thực thi mã thiếu tin cậy |

**Nuance quan trọng:** Nói “Proxy không tạo class mới” là **sai**: `Proxy.newProxyInstance` tạo hoặc dùng một JDK-generated proxy class ở runtime. Điều Proxy **không làm** là biên dịch **source Java tùy ý** hoặc tạo tùy tiện một subclass của class nghiệp vụ; nó sinh hình dạng triển khai các interface được chỉ định và định tuyến lời gọi đến handler.

Tương tự, nói “JavaCompiler có thể sửa method của class đang chạy” cũng **sai**. Nó tạo một bộ `.class` mới. JVM không thể nạp hai định nghĩa khác nhau của cùng tên class bằng **cùng defining class loader**; nếu muốn versioning/hot reload cần class loader mới, framework/instrumentation phù hợp hoặc cơ chế triển khai riêng.

## 3. Khi Reflection là đủ: khám phá và gọi code đã có

### 3.1. Reflection không biên dịch source

Một framework plugin có sẵn implementation đã được build:

```java
public final class ExistingRule {
    public int apply(int value) {
        return value * 2;
    }
}
```

Nếu tên class hoặc method đến từ cấu hình, có thể dùng Reflection:

```java
// Trích đoạn minh họa; ExistingRule phải tồn tại trên classpath.
Class<?> type = Class.forName("ExistingRule");
Object instance = type.getConstructor().newInstance();
java.lang.reflect.Method method =
        type.getMethod("apply", int.class);
int result = (int) method.invoke(instance, 5);
// result = 10
```

`Class.forName` tìm/nạp **class đã có**. `getMethod` tìm member public với đúng tham số. `Method.invoke` sử dụng giá trị đối số và có thể boxing/unboxing phù hợp. Không hề có Java source mới được biên dịch.

Đây là lựa chọn đúng khi:

- Có nhiều implementation được build/deploy sẵn và cần chọn bằng tên.
- Framework quét annotation rồi gọi các method đã tồn tại.
- Cần dựng object qua constructor được chọn tại runtime.
- Đầu vào động chỉ là **tên method, instance hoặc dữ liệu**, không phải phần thân method mới.

### 3.2. Reflection có những hạn chế gì?

Reflection **không thể** lấy chuỗi source `"return amount * 3 + 2;"` rồi biến nó thành bytecode chạy được. Nó cũng không thể tạo một method public mới trên class đã load chỉ bằng `getDeclaredMethods` hoặc `Method.invoke`.

Reflection còn bị Java access control/JPMS giới hạn. `getDeclaredMethod` nhìn thấy metadata private không có nghĩa có quyền thực thi. `setAccessible(true)` có thể bị từ chối bởi strong encapsulation; `privateLookupIn` cũng cần quyền/module openness hợp lệ. `JavaCompiler` không phải phương tiện vượt rào cản này — class mới được sinh ra vẫn phải tuân thủ cùng luật Java.

Nếu số lượng biến thể hành vi chỉ là vài thông số như `factor=2` hay `factor=3`, một implementation nhận tham số constructor là **đơn giản và an toàn hơn biên dịch cả class mới**.

## 4. Khi JDK Proxy là đủ: bọc lời gọi qua interface

Giả sử interface đã tồn tại:

```java
interface PriceRule {
    int apply(int amount);
}
```

Một implementation thật được truyền vào `InvocationHandler`. Proxy có thể đếm số lần gọi, kiểm tra quyền, log, hoặc forward:

```java
// Trích đoạn minh họa, PriceRule và delegate được định nghĩa sẵn.
PriceRule proxy = (PriceRule) java.lang.reflect.Proxy.newProxyInstance(
        PriceRule.class.getClassLoader(),
        new Class<?>[]{PriceRule.class},
        (receiver, method, args) -> {
            System.out.println("called=" + method.getName());
            try {
                return method.invoke(delegate,
                        args == null ? new Object[0] : args);
            } catch (java.lang.reflect.InvocationTargetException ex) {
                throw ex.getCause();
            }
        });
```

Khi code gọi `proxy.apply(5)`, JDK-generated proxy chuyển lời gọi sang handler. Handler sau đó quyết định trả kết quả hay ủy quyền sang `delegate`.

**Proxy phù hợp khi:**

- Caller chỉ cần làm việc qua interface có sẵn.
- Muốn thêm **hành vi trước/sau** lời gọi: tracing, metrics, caching, access control, circuit breaker.
- Muốn chọn delegate tại runtime.
- Có thể diễn tả biến thể nghiệp vụ bằng cấu hình/strategy/handler mà không cần một Java source class mới.

**Proxy không phù hợp khi:**

- Bắt buộc phải tạo một **subclass của một concrete class** mà caller/API yêu cầu; JDK Proxy **không extends class tùy ý**.
- Cần sinh một bộ method với tên/chữ ký mới không nằm trong những interface đã định nghĩa.
- Muốn mã Java cụ thể có cấu trúc phức tạp và được compiler kiểm tra tĩnh, thay vì một handler tập trung giải thích mọi lời gọi.
- Hệ thống bên ngoài bắt buộc nhận **một class implementation cụ thể** với cấu trúc bytecode/annotation mà JDK proxy không cung cấp.

**Nuance:** Handler **có thể tự tính toán logic mới** (ví dụ trả `amount * 3 + 2`) mà không có delegate. Vì vậy câu “cứ thay đổi business logic là phải dùng JavaCompiler” là **sai**. Nếu logic chỉ là một hàm nhỏ có thể hiện thực ngay trong handler hoặc strategy, Proxy có thể là lựa chọn nhẹ hơn.

### 4.1. Giới hạn của proxy với lớp và module

`Proxy.newProxyInstance` nhận danh sách **interface**, không phải class thông thường. Nó tạo proxy class theo các quy tắc access/package/module của JDK. Không thể truyền `ArrayList.class` như thể đó là một interface muốn intercept.

Mỗi method `equals`, `hashCode`, `toString` theo cơ chế JDK Proxy cũng có thể đi qua handler; code handler dùng `method.invoke(proxy,args)` để forward có thể tái nhập và đệ quy. Trường hợp đơn giản nên forward tới **delegate thật**, đồng thời thiết kế chính sách Object methods nhất quán.

Proxy không tự biến code chạy với quyền cao hơn: handler, delegate, reflection và generated proxy đều chịu quy tắc truy cập JVM. Nếu interface không nhìn thấy từ class loader được chỉ định hoặc không thỏa điều kiện proxy, quá trình tạo sẽ thất bại.

## 5. Khi nào thực sự cần `JavaCompiler`?

**`javax.tools.JavaCompiler` là API chính thức của Java cho compiler được gọi từ code Java.** Nó thuộc module `java.compiler` (API), với compiler implementation thường do JDK cung cấp trong `jdk.compiler`.

Hãy chọn biên dịch lúc chạy khi một trong các yêu cầu thực sự cần **một implementation Java mới** và việc triển khai bằng strategy/proxy/Reflection trở nên kém phù hợp:

### 5.1. Sinh lớp chuyên biệt theo schema hoặc DSL đã kiểm soát

Một hệ thống xử lý dữ liệu có schema được kiểm duyệt có thể sinh Java source chuyên biệt:

```java
// Java source được sinh ra từ cấu hình ĐÃ KIỂM TRA, không phải input tùy ý.
public final class GeneratedPriceRule implements PriceRule {
    @Override public int apply(int amount) {
        return amount * 3 + 2;
    }
}
```

Compiler kiểm tra cú pháp, kiểu và tạo bytecode có method body thực sự. Sau khi load, caller có thể dùng generated object như một `PriceRule` thông thường.

Nhưng **đừng biên dịch chỉ vì factor=3** nếu `new ExistingRule(3)` đã đáp ứng yêu cầu. Ví dụ này dùng phép tính nhỏ để minh họa pipeline kỹ thuật; trong production lợi ích biên dịch rõ hơn khi logic lớn, nhiều nhánh/schema hoặc tối ưu specialization đáng kể.

### 5.2. Tạo implementation cho interface hoặc subclass của class không final

Có thể sinh một class Java hoàn chỉnh:

- `implements ExistingInterface` với method body mới.
- `extends AccessibleBaseClass` nếu base không final, constructor hợp lệ và không override final methods.
- Khai báo public methods/fields/annotations cần cho công cụ ngoài (trong giới hạn Java compiler, accessibility và module).

JDK Proxy chỉ cung cấp sự chặn lời gọi qua **interface**, không tạo subclass concrete tùy ý. Reflection chỉ dùng những class có trước. Khi framework bên thứ ba đòi class implement/subclass với **shape cụ thể**, việc biên dịch source là một lựa chọn hợp lý.

Tuy nhiên, nếu nhu cầu chính là **sinh bytecode chứ không phải source**, một thư viện như Byte Buddy/ASM có thể phù hợp hơn; đó là giải pháp khác, có chi phí bảo trì và giới hạn riêng.

### 5.3. Sinh code theo yêu cầu nhưng vẫn sử dụng hệ thống type của Java

Ví dụ:

- Engine rule nội bộ tạo code từ AST/DSL đã parse, validate, then emit.
- Bộ chuyển đổi dữ liệu giữa schema thay đổi thường xuyên, khi mapping chuyên biệt đem lại lợi ích rõ rệt.
- Template compiler của ứng dụng sinh class/method với các signature cụ thể.
- Plugin builder cho **mã nguồn tin cậy** được quản lý và kiểm thử.
- Các integration cần class được build từ spec/cấu hình lúc runtime và được nạp sau khi tạo.

Điểm có giá trị là **lớp mới có Java source được compiler kiểm tra** và class loader có thể nạp, chứ không chỉ là method được gọi trễ.

### 5.4. Khi nào *không* nên dùng `JavaCompiler`?

Không nên dùng compiler nếu chỉ muốn:

- Gọi một method hiện hữu với tên được cấu hình → Reflection/MethodHandle.
- Chọn giữa các strategy có sẵn → interface + dependency injection/factory.
- Log hoặc ủy quyền lời gọi qua interface → Proxy/decorator.
- Thay một hệ số hoặc predicate đơn giản → data/configuration + function.
- Biến một biểu thức người dùng **không tin cậy** thành Java chạy ngay trong cùng JVM → nguy cơ thực thi mã tùy ý, không phải sandbox.
- Có vài biến thể được biết trước từ lúc build → compile ahead of time thường dễ triển khai/test hơn.

## 6. Quy trình chuẩn khi dùng JSR 199

Pipeline tối thiểu gồm các bước:

```text
1. Java source tin cậy + class name hợp lệ
              |
2. ToolProvider.getSystemJavaCompiler()
              |
3. JavaFileObject(s) + JavaFileManager
              |
4. Diagnostics + compiler options
              |
5. CompilationTask.call()
       /                    \
  false/exception           true
       |                      |
  thông báo lỗi              .class bytes
                              |
6. ClassLoader load class + xác nhận kiểu
                              |
7. Tạo instance / gọi method / cache kết quả
```

### 6.1. Lấy compiler provider

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "No system Java compiler; a full JDK is required");
}
```

**Quan trọng:** Một chương trình Java chạy được **không đảm bảo** trong runtime image có compiler provider. Với jlink image tối giản, môi trường Java được đóng gói thiếu module `jdk.compiler`, hoặc cấu hình runtime khác, `getSystemJavaCompiler()` có thể trả `null`.

Trong môi trường named module, API `javax.tools` ở module `java.compiler` cần được đọc bởi module của ứng dụng (ví dụ `requires java.compiler;`). Sự hiện diện của API **không tự chứng minh** compiler implementation đã có; cần đóng gói/resolve provider `jdk.compiler` hoặc một provider tương thích khi triển khai.

### 6.2. Chuẩn bị source và file manager

JSR 199 dùng `JavaFileObject` để đại diện các source/bytecode units và `JavaFileManager` để quản lý file tương ứng. Ví dụ chọn cách dễ hiểu là ghi source tạm ra đĩa:

```java
Path source = scratch.resolve("GeneratedPriceRule.java");
Files.writeString(source, generatedSource, StandardCharsets.UTF_8);

DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();
try (StandardJavaFileManager fm =
             compiler.getStandardFileManager(
                     diagnostics, null, StandardCharsets.UTF_8)) {
    Iterable<? extends JavaFileObject> units =
            fm.getJavaFileObjectsFromPaths(List.of(source));
    // Gọi compiler.getTask(...) bên trong try.
}
```

Đây là **trích đoạn**, giả định đã có `scratch`, `generatedSource` và `compiler`, cùng các imports tương ứng; chương trình hoàn chỉnh ở mục 8 khai báo tất cả.

Không nhất thiết phải ghi ra đĩa: có thể tự triển khai `SimpleJavaFileObject` nhận source trong memory và dùng `ForwardingJavaFileManager` giữ bytecode ở `ByteArrayOutputStream`. Cách in-memory có ích cho hệ thống biên dịch nhiều lần, nhưng phức tạp hơn vì phải quản lý `JavaFileObject` output, class loader và resource life cycle. Khi mới học, file manager mặc định + thư mục tạm là điểm bắt đầu tốt.

### 6.3. Gọi compiler và xử lý diagnostics

```java
List<String> options = List.of(
        "-encoding", "UTF-8", "-proc:none",
        "--release", "17",
        "-classpath", System.getProperty("java.class.path"),
        "-d", output.toString());

boolean success = Boolean.TRUE.equals(
        compiler.getTask(
                null, fm, diagnostics, options, null, units).call());
```

Đây là **trích đoạn**, biến được khai báo đầy đủ trong chương trình mục 8.

- `"-d"`: thư mục đích cho bytecode `.class`.
- `"-classpath"`: vị trí tìm các types đã compile, gồm interface/implementation mà generated source cần nhìn thấy. Ví dụ chạy trong classpath đơn giản nên có thể dùng `System.getProperty("java.class.path")`.
- `"--release", "17"`: biên dịch với API/language của Java 17 tương ứng nếu compiler hỗ trợ release đó; **không** tạo sandbox.
- `"-proc:none"`: tắt annotation processing trong lần compile này; hữu ích khi không cần chạy các processor có thể được phát hiện từ classpath. Nó **không biến mã Java nguồn thành an toàn**.
- `DiagnosticCollector`: tập hợp diagnostic có `kind`, file, line, column và message. Không nên chỉ kiểm tra `.call()==false` rồi im lặng.

`CompilationTask.call()` trả Boolean chỉ việc **biên dịch** thành công hay không. Biên dịch thành công **chưa chứng minh** class load thành công, mọi dependency có mặt, hoặc method chạy đúng logic. Cần bước nạp và kiểm thử riêng.

## 7. Thiết kế ví dụ so sánh ba phương pháp

Trong ví dụ chạy được, ta dùng cùng hợp đồng:

```java
public interface PriceRule {
    int apply(int amount);
}
```

Ba cách đưa tới kết quả:

| Phương pháp | Mã có trước / mới | Lời gọi | Kết quả với `amount=5` |
| --- | --- | --- | --- |
| Reflection | `ExistingRule(factor=2)` **đã compile** | `Method.invoke(existing,5)` | `10` |
| Proxy | Bọc `ExistingRule(2)` qua `PriceRule` | `proxy.apply(5)` (handler intercept rồi delegate) | `10` |
| JavaCompiler | `GeneratedPriceRule` **chưa có trước khi chương trình chạy** | `generated.apply(5)` | `17` vì `5*3+2=17` |

**Ý nghĩa:** Reflection giải quyết **lựa chọn/call method**, Proxy giải quyết **interception/delegation**, JavaCompiler giải quyết **tạo class implementation mới**. Việc đầu ra khác nhau (10/17) là lựa chọn cố ý của ví dụ, không phải bằng chứng proxy không thể tự tạo logic.

Để tránh nhập nhằng giữa hai class loaders, generated class **implements chính interface `RuntimeCompilerDecisionDemo.PriceRule`** đã được class loader cha nạp. Loader của generated code sử dụng parent loader nhìn thấy interface đó. Điều này cho phép cast instance mới sang cùng interface class identity.

## 8. Ví dụ Java 17+ hoàn chỉnh và đã kiểm chứng

Lưu toàn bộ mã dưới đây thành **`RuntimeCompilerDecisionDemo.java`**. Chương trình dùng source do chính tác giả định nghĩa (tin cậy), tạo thư mục tạm để compile, load class mới, chạy và dọn file. Ngoài ra còn compile một source sai cú pháp để chứng minh cách lấy diagnostics.

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class RuntimeCompilerDecisionDemo {
    public interface PriceRule {
        int apply(int amount);
    }

    public static final class ExistingRule implements PriceRule {
        private final int factor;

        public ExistingRule(int factor) {
            this.factor = factor;
        }

        @Override public int apply(int amount) {
            return amount * factor;
        }
    }

    public static void main(String[] args) throws Exception {
        // 1. Reflection: gọi implementation ĐÃ được compile.
        Class<?> known = Class.forName(
                RuntimeCompilerDecisionDemo.ExistingRule.class.getName());
        Object existing = known.getConstructor(int.class).newInstance(2);
        Method apply = known.getMethod("apply", int.class);
        System.out.println("reflection=" + apply.invoke(existing, 5));

        // 2. JDK Proxy: intercept interface, rồi gọi logic cũ.
        PriceRule delegate = new ExistingRule(2);
        int[] intercepted = {0};
        PriceRule proxy = (PriceRule) Proxy.newProxyInstance(
                PriceRule.class.getClassLoader(),
                new Class<?>[]{PriceRule.class},
                (receiver, method, callArgs) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "toString" -> "PriceRuleProxy";
                            case "hashCode" -> System.identityHashCode(receiver);
                            case "equals" -> receiver == callArgs[0];
                            default -> throw new UnsupportedOperationException();
                        };
                    }
                    intercepted[0]++;
                    System.out.println("intercepted=" + method.getName());
                    try {
                        return method.invoke(delegate,
                                callArgs == null ? new Object[0] : callArgs);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                });
        System.out.println("proxy=" + proxy.apply(5));
        System.out.println("proxy calls=" + intercepted[0]);

        // 3. JavaCompiler: biên dịch class MỚI không có trong build ban đầu.
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        System.out.println("compiler available=" + (compiler != null));
        if (compiler == null) {
            throw new IllegalStateException(
                    "A full JDK with the jdk.compiler module is required");
        }

        Path scratch = Files.createTempDirectory("rule-demo-");
        try {
            Path output = Files.createDirectory(scratch.resolve("classes"));
            Path source = scratch.resolve("GeneratedPriceRule.java");
            Files.writeString(source, """
                    public final class GeneratedPriceRule
                            implements RuntimeCompilerDecisionDemo.PriceRule {
                        @Override public int apply(int amount) {
                            return amount * 3 + 2;
                        }
                    }
                    """, StandardCharsets.UTF_8);

            List<String> options = List.of(
                    "-encoding", "UTF-8", "-proc:none",
                    "--release", "17",
                    "-classpath", System.getProperty("java.class.path"),
                    "-d", output.toString());

            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();
            try (StandardJavaFileManager fm =
                         compiler.getStandardFileManager(
                                 diagnostics, null, StandardCharsets.UTF_8)) {
                Iterable<? extends JavaFileObject> units =
                        fm.getJavaFileObjectsFromPaths(List.of(source));
                boolean compiled = Boolean.TRUE.equals(
                        compiler.getTask(null, fm, diagnostics,
                                options, null, units).call());
                System.out.println("compiled=" + compiled);
                if (!compiled) {
                    for (Diagnostic<? extends JavaFileObject> d :
                            diagnostics.getDiagnostics()) {
                        System.err.println(d.getKind()
                                + ": " + d.getMessage(null));
                    }
                    throw new IllegalStateException("Compilation failed");
                }
            }

            try (URLClassLoader loader =
                         new URLClassLoader(new URL[]{output.toUri().toURL()},
                                 PriceRule.class.getClassLoader())) {
                Class<?> generatedType =
                        Class.forName("GeneratedPriceRule", true, loader);
                PriceRule generated =
                        (PriceRule) generatedType.getConstructor().newInstance();
                System.out.println("new class=" + generatedType.getSimpleName());
                System.out.println("generated=" + generated.apply(5));
                System.out.println("same interface="
                        + PriceRule.class.isAssignableFrom(generatedType));
            }

            // Negative control: source Java sai cú pháp bị từ chối.
            Path invalidSource = scratch.resolve("InvalidPriceRule.java");
            Files.writeString(invalidSource,
                    "public class InvalidPriceRule { syntax error }",
                    StandardCharsets.UTF_8);
            DiagnosticCollector<JavaFileObject> invalidDiagnostics =
                    new DiagnosticCollector<>();
            try (StandardJavaFileManager fm =
                         compiler.getStandardFileManager(
                                 invalidDiagnostics, null, StandardCharsets.UTF_8)) {
                boolean invalidCompiled = Boolean.TRUE.equals(
                        compiler.getTask(
                                null, fm, invalidDiagnostics, options, null,
                                fm.getJavaFileObjectsFromPaths(
                                        List.of(invalidSource))).call());
                boolean hasErrors = invalidDiagnostics.getDiagnostics().stream()
                        .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
                System.out.println("invalid compiled=" + invalidCompiled);
                System.out.println("diagnostic error=" + hasErrors);
            }
        } finally {
            // Dọn file tạm sau khi file managers và class loader đóng.
            try (var paths = Files.walk(scratch)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

### 8.1. Chạy chương trình

Tại thư mục chứa file trên, cần JDK 17 hoặc mới hơn:

```bash
javac --release 17 RuntimeCompilerDecisionDemo.java
java RuntimeCompilerDecisionDemo
```

**Stdout chính xác đã được kiểm chứng trong thử nghiệm trên JDK có compiler:**

```text
reflection=10
intercepted=apply
proxy=10
proxy calls=1
compiler available=true
compiled=true
new class=GeneratedPriceRule
generated=17
same interface=true
invalid compiled=false
diagnostic error=true
```

Trong thử nghiệm, cả lệnh `javac` ban đầu và `java` đều thoát với exit code **0**. Thư mục tạm được tạo bên ngoài dự án và được dọn trước khi chương trình kết thúc. Nếu bạn chạy trên runtime image **không có compiler provider**, chương trình sẽ in `compiler available=false` rồi ném `IllegalStateException` có thông báo, thay vì lặng lẽ coi việc compile thành công.

### 8.2. Giải thích output và các ranh giới kỹ thuật

**`reflection=10`:** `Class.forName` tải/nhận `ExistingRule` đã được biên dịch, Reflection tạo instance với factor 2 và gọi method `apply(5)`. Không có compiler mới tham gia.

**`intercepted=apply` và `proxy=10`:** JDK Proxy gọi `InvocationHandler` trước khi ủy quyền tới `ExistingRule(2)`. Handler đếm đúng một lời gọi `apply` trong kịch bản một luồng. Biến `int[] intercepted` trong ví dụ chỉ phục vụ quan sát tuần tự, **không** phải bộ đếm production thread-safe.

**`compiler available=true`:** JVM chạy cùng JDK chứa compiler provider. Đây là một **kiểm tra môi trường**, không phải trạng thái đảm bảo ở mọi deployment.

**`compiled=true`:** `JavaCompiler.CompilationTask.call` biên dịch source `GeneratedPriceRule.java` thành `GeneratedPriceRule.class` bên trong thư mục `classes` tạm. Tại thời điểm này mới biết compilation thành công, **chưa** biết việc gọi class có đúng nghiệp vụ.

**`new class=GeneratedPriceRule`, `generated=17`:** `URLClassLoader` nhìn thấy output folder, `Class.forName` nạp class mới, constructor public được gọi, và `apply(5)` thực thi logic `5 * 3 + 2`.

**`same interface=true`:** Generated class có thể gán được cho `RuntimeCompilerDecisionDemo.PriceRule` do trình biên dịch đã kiểm tra implementation và loader của generated class tham chiếu cùng interface từ parent loader. Việc thiết kế class loader đúng rất quan trọng; hai class có **cùng binary name nhưng khác defining loader** vẫn có thể là hai kiểu JVM khác nhau.

**`invalid compiled=false` và `diagnostic error=true`:** Thử nghiệm cố ý compile source sai cú pháp. `CompilationTask.call()` trả `false`; `DiagnosticCollector` nhận ít nhất một diagnostic `ERROR`. Ví dụ chỉ in boolean, không in số lỗi hoặc message nhằm tránh phụ thuộc khác biệt wording của compiler giữa các phiên bản.

### 8.3. Tại sao source được viết trong default package?

Để giữ ví dụ tự chạy bằng một `javac` command và không yêu cầu tạo cây thư mục `src/main/java/...`, cả outer class `RuntimeCompilerDecisionDemo` và generated class `GeneratedPriceRule` đều ở **default package**. Đây là lựa chọn cho **laboratory**, không phải mẫu kiến trúc production.

Trong dự án thực:

- Đặt generated type trong **named package** phù hợp, với package declaration và source path tương ứng.
- Không giả định classloader nhìn thấy tất cả classes từ unnamed module hoặc module path.
- Không tạo tùy tiện binary names trùng với class đã có.
- Quản lý class name/versioning/loader theo namespace riêng của hệ thống.

Nếu generated source cần dùng type thuộc named module, có thể cần `--module-path`, `--add-modules` hoặc cấu hình Java compiler/module-info hợp lệ, không chỉ `-classpath`.

## 9. Những lỗi thường gặp ở bước biên dịch

### 9.1. `getSystemJavaCompiler()==null`

Triệu chứng:

```text
compiler available=false
```

Nguyên nhân có thể là môi trường chỉ chứa thành phần runtime, custom `jlink` image không có `jdk.compiler` hoặc compiler provider không thể tìm thấy. Giải pháp:

- Kiểm tra deployment có compiler provider phù hợp.
- Dùng JDK/runtime image chứa `jdk.compiler` nếu yêu cầu compile ở runtime.
- Nếu không thể mang compiler vào production, cân nhắc **compile ahead of time** rồi deploy classes như plugin.
- Trong named module, cấu hình module graph rõ ràng cho API `java.compiler` và provider tương ứng.

**Đừng** kết luận là do source Java sai khi còn chưa lấy được compiler. Bài mẫu kiểm tra null **trước** mọi compilation task.

### 9.2. `CompilationTask.call()==false`

Một source sai cú pháp, thiếu type hoặc vi phạm access sẽ khiến compiler báo lỗi. `DiagnosticCollector` giúp lấy:

```java
// Trích đoạn dùng sau khi gọi compiler.getTask(...).
for (Diagnostic<? extends JavaFileObject> d :
        diagnostics.getDiagnostics()) {
    System.out.println("kind=" + d.getKind());
    System.out.println("line=" + d.getLineNumber());
    System.out.println("column=" + d.getColumnNumber());
    System.out.println("message=" + d.getMessage(null));
}
```

Đây là **trích đoạn** với biến `diagnostics` đã có. Nên xử lý cả `ERROR`/`WARNING`/`MANDATORY_WARNING` theo chính sách, giữ thông tin file/line nếu hiển thị cho developer. Khi log production, tránh đưa full source code hoặc secrets vào thông điệp lỗi.

**Đừng tiếp tục `Class.forName("Generated...")` khi compilation đã thất bại.** Nó có thể nạp một class cũ cùng tên từ classpath và tạo kết quả gây hiểu nhầm, hoặc ném `ClassNotFoundException`.

### 9.3. Biên dịch thành công nhưng nạp thất bại

Lỗi thường thấy:

| Lỗi | Tầng | Nguyên nhân điển hình |
| --- | --- | --- |
| `ClassNotFoundException` | Load | Loader không trỏ tới thư mục có generated `.class`, sai binary name/package |
| `NoClassDefFoundError` | Link/load dependencies | Class phụ thuộc của generated code không hiện diện khi nạp/thực thi |
| `ClassCastException` | Cast instance | Generated type không thật sự implement đúng **class identity** của interface được caller dùng |
| `IllegalAccessException` | Reflection instantiation | Constructor/class không public hoặc caller không đủ quyền |
| `NoSuchMethodException` | Reflection instantiation | Không có public no-arg constructor như code mong đợi |
| `LinkageError` | JVM linking | Binary incompatibility, duplicate definition trong cùng loader, classfile/module inconsistency |
| Exception từ generated method | Runtime invocation | Lỗi logic nghiệp vụ, không liên quan việc `CompilationTask.call()` thành công hay không |

Compiler sẽ kiểm tra dependencies trong **classpath/module path khi biên dịch**; JVM kiểm tra/load dependencies trong **loader/module graph lúc chạy**. Hai môi trường đó phải được thiết kế tương thích. Compilation success **không loại trừ** runtime linkage errors.

### 9.4. Dùng sai binary name và source filename

Một source khai báo `public class GeneratedPriceRule` thường cần file `GeneratedPriceRule.java`; sau khi compile, binary name để nạp là `GeneratedPriceRule` nếu không có package, hoặc `com.example.GeneratedPriceRule` nếu có `package com.example;`.

Không dùng đường dẫn file `classes/GeneratedPriceRule.class` làm đối số `Class.forName`; API này nhận **binary class name**.

### 9.5. Class loader vẫn giữ phiên bản cũ

Cùng tên class được nạp bởi cùng defining class loader chỉ có một định nghĩa. Nếu đã load `GeneratedPriceRule` phiên bản A, compile lại source A thành B rồi ghi đè file trên đĩa **không** có nghĩa class object đang chạy tự đổi method body.

Một hướng thiết kế versioning là dùng loader mới cho version B, đổi reference tới implementation hiện hành, và **giải phóng reference tới loader cũ** khi không còn dùng. Đây là một chiến lược class-loader isolation, không phải chức năng tự động của `JavaCompiler`.

## 10. Những rủi ro bảo mật quan trọng khi compile lúc chạy

### 10.1. JavaCompiler không phải một sandbox cho mã người dùng

**Không dùng `JavaCompiler` để chạy source Java tùy ý do người dùng không tin cậy gửi lên ngay trong JVM của server.** Mã được nạp và chạy có thể gọi filesystem, network, process APIs, thread APIs hoặc truy cập dữ liệu mà ứng dụng có quyền; việc build qua JSR 199 không tự hạn chế những quyền đó.

`"-proc:none"` chỉ tắt annotation processing trong compilation task. Nó **không** kiểm chứng source an toàn, không chặn class initializer, không chặn lệnh nguy hiểm khi generated class được chạy, và không tạo isolation boundary.

Nếu cần chạy mã do người dùng viết, nên cân nhắc **môi trường thực thi cô lập thực sự** với giới hạn CPU, RAM, thời gian, filesystem, network, tài khoản/quyền và process/container isolation phù hợp. Java in-process cùng quyền server **không** phải biện pháp bảo mật đủ mạnh cho mã tùy ý.

### 10.2. Source injection từ template

Ví dụ hệ thống ghép string người dùng trực tiếp vào method body:

```java
// PHẢN VÍ DỤ: input không tin cậy có thể trở thành Java source.
String generated = "public int apply(int x) { return "
        + userExpression + "; }";
```

Mã trên là **trích đoạn chống chỉ định** nếu `userExpression` đến từ bên ngoài mà không được ràng buộc. Một attacker có thể thao túng cú pháp, thêm statement/import/class, hoặc tạo source có side effects. Dù compiler báo lỗi khi payload sai syntax, compiler **không bảo đảm payload đúng syntax là an toàn**.

Hướng an toàn hơn:

1. **Không** mở bề mặt viết Java source tự do khi không cần.
2. Dùng một **DSL/AST whitelist** với tập phép toán, identifier và kiểu được kiểm soát.
3. Generate source từ AST hợp lệ, tránh ghép raw strings.
4. Từ chối constructs không thuộc miền cho phép và đặt resource limits.
5. Chỉ load/run code trong môi trường có chính sách bảo mật thích hợp.
6. Ghi log/diagnostics theo nguyên tắc tránh lộ dữ liệu nhạy cảm.

### 10.3. Annotation processors và quá trình compilation

Annotation processors có thể chạy trong bước compile nếu môi trường/options cho phép; chúng là code thực sự, không phải chỉ metadata. Ví dụ dùng `-proc:none` để tắt processor khi không cần.

Tuy nhiên, **đừng coi `-proc:none` là cơ chế sandbox**: nó chỉ xử lý một nguồn thực thi trong quá trình build. Generated class sau khi load vẫn có thể thực hiện bất kỳ hành vi nào được JVM và môi trường cho phép.

### 10.4. Class loading và tên class xung đột

Không cho source không tin cậy tự chọn package `java.*`, tên lớp trùng application internals, hoặc loader path mà hệ thống không kiểm soát. Parent-first delegation và package/module constraints giúp giảm một số rủi ro, nhưng **không** thay thế việc chỉ cho phép trusted code và cấu hình isolation.

Ngoài tính bảo mật, class name collisions làm phát sinh hành vi không nhất quán: loader có thể trả về class đã nạp từ parent thay vì class mới. Khi đó caller nghĩ đang chạy version mới nhưng thực chất chạy version cũ.

## 11. Quản lý class loader, tài nguyên và tốc độ

### 11.1. Không compile trên mỗi request trừ khi có lý do đặc biệt

Biên dịch lúc chạy có chi phí:

- Parse source và type checking.
- Truy vấn dependencies qua classpath/module path.
- Tạo bytecode, ghi/đọc file hoặc byte buffer.
- Define/link/verify class.
- JIT warm-up và khởi tạo metadata sau khi bắt đầu dùng.

Nếu một rule được gọi hàng triệu lần nhưng chỉ đổi khi deploy, compile **một lần** và cache object/method handle thường hợp lý hơn compile ở mỗi request.

Một chiến lược có thể là:

```text
Input schema/config được kiểm duyệt
        |
        v
Stable key = hash(source + options + dependency version)
        |
        +-- cache hit --> reuse generated instance/class
        |
        +-- cache miss --> compile --> validate --> load --> cache
```

**Đừng cache chỉ theo một tên như `"GeneratedRule"`** khi source, compiler options hoặc dependency version có thể thay đổi. Cache theo identity rõ ràng để tránh dùng implementation không khớp spec.

### 11.2. Không quên đóng resources

Trong ví dụ chạy:

- `StandardJavaFileManager` dùng `try-with-resources`.
- `URLClassLoader` được đóng sau khi dùng.
- Temp files được xóa trong `finally`.
- Nội dung generated source tin cậy, không dựa vào dữ liệu người dùng.

Trong production, **đóng `URLClassLoader` không đồng nghĩa class đã unload ngay**. JVM chỉ có thể unload class/loader khi không còn các reference quan trọng và đủ điều kiện GC. Giữ static cache, `ThreadLocal`, thread context class loader, scheduled task, event listener hoặc MethodHandle tham chiếu generated class có thể giữ loader sống lâu. Compile hàng nghìn phiên bản mà không quản lý vòng đời có thể gây tăng metaspace/memory.

### 11.3. Tạo class trong memory: khi nào đáng dùng?

Với khối lượng compile lớn, có thể triển khai custom:

- `SimpleJavaFileObject` biểu diễn source trong RAM.
- `ForwardingJavaFileManager` ghi bytecode vào `ByteArrayOutputStream`.
- Class loader gọi `defineClass` từ bytes.

Cách này tránh filesystem I/O, nhưng tăng số nhánh lỗi và trách nhiệm quản lý binary names, dependent classes, resources, class loader identity và caching. Với một tác vụ build occasional, **filesystem-based example** thường dễ chẩn đoán hơn.

### 11.4. Đừng bỏ qua classpath và module path

Chương trình ví dụ đơn giản chạy trên classpath thông thường. Với ứng dụng JPMS:

- Module muốn **gọi API `javax.tools`** thường khai báo `requires java.compiler;`.
- Compiler provider thường được cung cấp bởi `jdk.compiler`; runtime image/module graph phải có đủ thành phần.
- Generated classes dùng types của named modules có thể cần các compiler options như `--module-path`, `--add-modules` và source/package design đúng.
- Khi load generated class, runtime loader/module visibility vẫn cần hợp lệ; compiler options không bảo đảm mọi module access lúc chạy.
- `--release 17` đặt API/language target, không tự đảm bảo dependent application classes trên classpath tương thích hoàn toàn với mọi môi trường chạy.

## 12. Bảng quyết định theo yêu cầu thật

| Yêu cầu thực tế | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Đọc annotation và gọi method của plugin đã biên dịch | Reflection | Method đã có, chỉ cần khám phá rồi invoke |
| Cần gọi một method theo tên đã chọn trong configuration | Reflection hoặc MethodHandle | Không có Java source mới |
| Thêm logging/authorization vào service interface | JDK Proxy hoặc decorator | Intercept lời gọi qua giao diện có sẵn |
| Runtime chọn implementation đã đăng ký | Factory/strategy/DI; có thể dùng Reflection để load | Không cần tạo bytecode mới |
| Biên dịch implementation mới với cấu trúc nhiều method từ schema nội bộ | `JavaCompiler` | Cần một Java class mới, được type-check |
| Integration API bắt buộc concrete subclass với code mới | `JavaCompiler` hoặc bytecode generator | JDK Proxy không subclass class thường |
| Formula đơn giản `x*rate+offset`, dữ liệu thay đổi liên tục | Function/config; không cần compile | Compiler có overhead lớn không cần thiết |
| Mã source do người dùng không tin cậy nhập | **Không chạy in-process** chỉ bằng `JavaCompiler` | Compiler không phải sandbox |
| Muốn tái dùng lambda/functional behavior thay vì sinh source | Lambda, strategy, MethodHandle | Nhẹ hơn và dễ test hơn |
| Chỉ cần Java type-safe API sẵn có, biết type từ build | Gọi Java bình thường | Reflection/proxy/compiler đều có thể là quá mức |
| Cần tái build plugin nhiều phiên bản runtime | `JavaCompiler` + loader isolation/caching/versioning | Cần quản lý lifecycle, dependencies và class identity |
| Cần thêm method vào **class đã load** | Không giải quyết trực tiếp bằng ba API trên | Cần cân nhắc instrumentation/hot-swap/kiến trúc mới |

### 12.1. Quy tắc ba câu hỏi

1. **Mã đã tồn tại chưa?** Nếu có, ưu tiên API thường, Reflection, MethodHandle hay factory để truy cập/dispatch.
2. **Có interface thích hợp cho việc chặn/ủy quyền không?** Nếu có, JDK Proxy hoặc decorator thường là đủ.
3. **Có cần Java source/bytecode implementation mới thật sự không?** Nếu có, hãy đánh giá `JavaCompiler` cùng compiler availability, class loader, performance và security.

Chỉ trả lời “có” ở câu 3 là **điều kiện cân nhắc compiler**, không phải bắt buộc phải dùng compiler. Có thể dùng bytecode generation hoặc codegen ở build time tùy bài toán.

## 13. Các anti-pattern và cách sửa

### 13.1. “User sửa công thức một chút thì compile lại Java class”

Nếu chỉ là phép tính `amount*factor+offset`, có thể dùng object giữ hai thông số:

```java
// Ví dụ Java đầy đủ ở cấp class nhưng không chứa main().
public final class ConfigurablePriceRule {
    private final int factor;
    private final int offset;

    public ConfigurablePriceRule(int factor, int offset) {
        this.factor = factor;
        this.offset = offset;
    }

    public int apply(int amount) {
        return amount * factor + offset;
    }
}
```

Cách này tránh compiler và classloader hoàn toàn. Chỉ chuyển sang code generation nếu benchmark và đặc điểm schema cho thấy lợi ích rõ ràng.

### 13.2. “Dùng Reflection để sinh body mới”

Reflection chỉ khám phá/call bytecode đã có. Nếu cần `public int apply(int){return ...;}` mới mà chưa có class nào cung cấp, phải có bước tạo implementation (biên dịch source, sinh bytecode, hoặc dùng closure/strategy phù hợp). `Method.invoke` không nhận Java source string.

### 13.3. “Proxy thay được bất kỳ class nào”

JDK Proxy chỉ implement interface; truyền một concrete class không phải interface vào `Proxy.newProxyInstance` là sai. Nếu caller cần subtype của class cụ thể, cân nhắc public non-final subclass được biên dịch hoặc công cụ subclass generation phù hợp. Không thể vượt `final` hoặc access control của Java.

### 13.4. “Biên dịch thành công là plugin chạy an toàn”

Source hợp lệ vẫn có thể:

- Ném exception khi thực thi.
- Gọi API nguy hiểm.
- Không tìm thấy dependency khi load ở loader khác.
- Trả kết quả sai nghiệp vụ.
- Gây memory leak qua loader references.

Compilation test cần theo sau bằng **load test, type check, behavior tests và security boundary**.

### 13.5. “Cùng class name thì JVM tự cập nhật class khi file .class thay đổi”

Sau khi một loader đã define class, thay file trên đĩa không tự đổi định nghĩa trong JVM. Cần loader/version lifecycle rõ ràng hoặc chọn kiến trúc không dựa vào hot code replacement.

### 13.6. “Để compiler tự tìm mọi dependency”

Compiler sử dụng **classpath/module path theo config**, không nhất thiết giống class loader mà runtime sẽ dùng. Truyền đúng options, bố trí generated source đúng package và kiểm tra class identity của interface chung.

### 13.7. “Khi diagnostic rỗng thì compile chắc chắn thành công”

Phải kiểm tra Boolean trả về của `CompilationTask.call()`; diagnostic collector là kênh báo vấn đề, không phải nguồn xác nhận thay thế return status. Các compilation failures có thể xuất hiện dưới nhiều hình thức, bao gồm exceptions của file manager/compiler. Khi compile thành công, vẫn cần kiểm tra class load và behavior.

## 14. Checklist triển khai `JavaCompiler` đúng quy mô

Khi đã quyết định cần JavaCompiler, thực hiện theo thứ tự:

1. **Chốt hợp đồng plugin:** interface/abstract base class, chữ ký methods, validation rules và return type.
2. **Chốt nguồn sinh:** trusted template hoặc AST/DSL whitelist; không ghép raw input tùy ý vào Java source.
3. **Đặt binary name và package ổn định:** tránh trùng class từ parent loader và xác nhận source filename/package hợp lệ.
4. **Kiểm tra compiler provider:** `ToolProvider.getSystemJavaCompiler()`, module/runtime image và target Java version.
5. **Chuẩn bị compiler options:** `-encoding`, `--release`, `-classpath`/`--module-path`, `-d` và `-proc:none` khi không cần annotation processing.
6. **Thu diagnostics:** `DiagnosticCollector`, lưu kind/file/line/column/message phù hợp, tránh leak source nhạy cảm.
7. **Kiểm tra compilation result:** `Boolean.TRUE.equals(task.call())`; dừng nếu false.
8. **Nạp bằng loader phù hợp:** parent có thể nhìn thấy shared interface, không định nghĩa cùng binary name nhiều lần trong cùng loader.
9. **Xác nhận type:** `expectedInterface.isAssignableFrom(generatedType)` trước khi ép kiểu; khởi tạo constructor hợp lệ.
10. **Kiểm thử hành vi:** happy path, boundary, exceptions, performance, giới hạn số lượng class.
11. **Cache có khóa đúng:** source hash + compiler options + dependency/version; giới hạn cache size và vòng đời.
12. **Đóng/dọn tài nguyên:** file manager, classloader, temp files khi đã hết dùng; kiểm soát strong references.
13. **Đặt security boundary:** không chạy arbitrary user Java cùng quyền ứng dụng; isolation nếu yêu cầu.
14. **Theo dõi vận hành:** compilation latency, errors by diagnostic kind, loader/metaspace growth và số version đang sống.

Cần nhận ra rằng **JavaCompiler là một compiler thật**. Nó không chỉ thêm chút overhead cho một lời gọi: dùng nó biến ứng dụng runtime thành một hệ thống có cả **build pipeline, dependency resolution và class loading** ngay trong production. Chỉ đáng làm khi lợi ích tạo code mới tương xứng.

## 15. Bài tập tự kiểm tra

**Câu 1.** Một hệ thống đã có `CreditRule` và `DebitRule` trên classpath. Configuration chọn class name lúc chạy. Có cần `JavaCompiler` không?  
**Đáp án:** Không. Dùng factory/DI hoặc Reflection/MethodHandle để chọn class đã compile.

**Câu 2.** Muốn đếm số lần gọi `OrderService.submit` qua interface `OrderService` mà không sửa implementation. Nên chọn gì?  
**Đáp án:** JDK Proxy hoặc decorator; `InvocationHandler` chặn rồi delegate. Không cần biên dịch source mới.

**Câu 3.** Framework phải phát sinh một class `implements TransformationRule` chứa method body mới được dựng từ AST hợp lệ. Có thể dùng API nào?  
**Đáp án:** `JavaCompiler` tạo Java source, compile thành `.class` rồi load; hoặc lựa chọn bytecode generator nếu phù hợp. Cần validate input và class loader.

**Câu 4.** `ToolProvider.getSystemJavaCompiler()` trả `null`. Có thể gọi `getTask` không?  
**Đáp án:** Không. Cần compiler provider, thường từ JDK module `jdk.compiler`; hoặc đổi kiến trúc sang build ahead of time.

**Câu 5.** Có `JavaCompiler`, nhưng generated source tham chiếu `PriceRule` mà compiler không thấy. Vì sao?  
**Đáp án:** Compile classpath/module path thiếu dependency/shared interface hoặc package/visibility sai. Cần cấu hình đường tìm class và module.

**Câu 6.** `CompilationTask.call()` trả `false`. Có nên thử load `GeneratedPriceRule` không?  
**Đáp án:** Không nên. Đọc diagnostics, sửa source/options; nếu load ngay có thể gặp class cũ hoặc `ClassNotFoundException`.

**Câu 7.** Generated class có cùng tên `com.example.Rule` với một class parent loader đã nạp. Khi `Class.forName` với child `URLClassLoader`, chắc chắn nhận version mới chứ?  
**Đáp án:** Không. Parent-first delegation có thể trả class đã có. Cần namespace/versioning/loader design phù hợp.

**Câu 8.** Dùng `-proc:none` thì compile và chạy Java source do người dùng lạ gửi vào cùng JVM đã an toàn chưa?  
**Đáp án:** Chưa. Option chỉ tắt annotation processors; source đã biên dịch vẫn là code tùy ý có quyền của JVM process. Cần isolation và security model khác.

**Câu 9.** Muốn một implementation mới chỉ khác hệ số 2 thành 3. Có nên mặc định compile class mới?  
**Đáp án:** Không. Constructor parameter/configurable strategy dễ hơn. Compile chỉ khi có lý do chuyên biệt hóa đáng giá.

**Câu 10.** Vì sao source compiled success nhưng cast object sang interface của ứng dụng vẫn có thể thất bại?  
**Đáp án:** Class loader có thể define **hai class khác nhau cùng binary name** của interface; class identity trong JVM bao gồm defining loader. Chọn parent loader chia sẻ interface hợp lệ.

**Câu 11.** JDK Proxy có tạo class mới ở runtime không?  
**Đáp án:** Có. Nó tạo proxy class triển khai interfaces. Nhưng không biên dịch arbitrary Java source, không subclass một concrete class tùy ý.

**Câu 12.** `java.compiler` và `jdk.compiler` khác nhau thế nào?  
**Đáp án:** `java.compiler` chứa API/tool contracts như `javax.tools.JavaCompiler`; `jdk.compiler` cung cấp triển khai javac trong JDK. API có mặt không bảo đảm provider chạy được trong mọi runtime image.

**Câu 13.** Sau khi compile lại `GeneratedRule.java`, method của một instance đã nạp sẽ đổi hành vi ngay không?  
**Đáp án:** Không. Thay classfile không thay định nghĩa class đã load trong cùng loader. Cần architecture versioning/loader mới hoặc cơ chế instrumentation phù hợp.

**Câu 14.** `URLClassLoader.close()` có lập tức giải phóng metaspace của generated class không?  
**Đáp án:** Không. Close giải phóng tài nguyên liên quan loader nhưng class unload phụ thuộc các reference còn sống và điều kiện GC. Quản lý caches và vòng đời.

## 16. Tổng kết và nguồn tham khảo

**Tóm tắt lựa chọn:**

```text
Đã có code/class cần gọi?
    |
    +-- Có --> Gọi tĩnh / Factory / Reflection / MethodHandle
    |
    +-- Muốn intercept interface? --> JDK Proxy / Decorator
    |
    +-- Thực sự cần class Java mới?
            |
            +-- Có --> JavaCompiler hoặc bytecode generation
            |
            +-- Không --> Dùng dữ liệu, strategy, function/lambda
```

**Những điểm cần nhớ:**

- Reflection **không tạo Java method body mới**; nó khám phá và gọi code đã tồn tại.
- JDK Proxy **có tạo proxy class**, nhưng chỉ implement interfaces và định tuyến calls tới `InvocationHandler`; nó không nhận source Java tùy ý.
- `JavaCompiler` tạo bytecode từ Java source mới. Sau compile vẫn cần **class loading, type check, instantiation và tests**.
- Trong JDK, provider thường đến từ `jdk.compiler`; `ToolProvider.getSystemJavaCompiler()` có thể trả `null` nếu runtime image không có provider.
- `CompilationTask.call()` và `DiagnosticCollector` phải được xử lý rõ ràng; không nạp class khi compile fail.
- `--release` không phải sandbox, `-proc:none` không làm arbitrary source an toàn; class loader boundary cũng **không** phải một sandbox bảo mật.
- Chi phí compilation, class loader identity và memory management là những yếu tố kiến trúc quan trọng.
- Chọn compiler dựa trên **nhu cầu tạo implementation mới**, không phải chỉ vì hệ thống có “runtime” trong tên tính năng.

**Tài liệu chính thức (Java 17):**

- [`javax.tools.JavaCompiler` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, `CompilationTask` và compiler contracts.
- [`javax.tools.ToolProvider` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): `getSystemJavaCompiler()`.
- [`javax.tools.DiagnosticCollector` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): diagnostic warnings/errors.
- [`javax.tools.StandardJavaFileManager` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): quản lý source/output files.
- [`java.lang.reflect.Proxy` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html) và [`InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): JDK dynamic proxies.
- [`java.lang.reflect.Method` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): reflection invocation.
- [`java.net.URLClassLoader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): nạp classes từ URLs, close resources và giới hạn class loading.
- [`javac` Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `-classpath`, `--module-path`, `-proc:none`, `-d`.
