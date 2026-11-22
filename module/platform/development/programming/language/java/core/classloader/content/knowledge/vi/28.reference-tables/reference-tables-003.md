# Bảng lỗi theo giai đoạn nạp, liên kết, khởi tạo và sử dụng lớp Java

Khi ứng dụng Java báo lỗi ở lớp, classloader, dependency JAR, framework, plugin hoặc reflection, việc **nhìn tên exception mà sửa ngay classpath** thường không đủ. Một class đi qua nhiều bước khác nhau của JVM: **loading**, **linking** (verification, preparation, resolution), **initialization**, sau đó mới đến **sử dụng class/object/method**. Mỗi giai đoạn có những lỗi điển hình với nguyên nhân và cách khắc phục khác nhau.

Ví dụ:

- `ClassNotFoundException`: code **chủ động tìm class bằng tên** nhưng loader được chọn không tìm ra.
- `NoClassDefFoundError`: JVM cần class definition không tìm được theo tham chiếu bytecode, hoặc class trước đó đã initialization thất bại.
- `VerifyError`: bytecode không vượt được các kiểm tra verification.
- `NoSuchMethodError`: symbolic method reference không khớp method của **phiên bản class thực sự được nạp**.
- `ExceptionInInitializerError`: static initialization chạy rồi ném non-`Error` exception.
- `ClassCastException`: object không thể cast về runtime type được yêu cầu, đôi khi do cùng binary name nhưng **khác defining class loader**.

Bài này là **tài liệu tra cứu** theo giai đoạn, có bảng lỗi, ví dụ Java 17+ tái hiện những trường hợp phổ biến, lệnh chẩn đoán và quy trình khoanh vùng nguyên nhân. Các bảng mô tả **giai đoạn nguyên nhân**; JVM có quyền thực hiện một số hoạt động linking/resolution sớm hoặc muộn nên **thời điểm stack trace phát ra lỗi có thể không trùng chính xác với bước mà người viết dự đoán**.

## 1. Bản đồ giai đoạn Class Loading của JVM

Theo JVMS §5, luồng khái quát:

~~~text
    Source .java / library dependency / bytecode generator
                          |
                        javac
                          |
                     Class file bytes
                          |
                          v
                   (1) LOADING
           ClassLoader.loadClass/findClass
                          |
       find class representation, define runtime Class
                          |
                          v
                   (2) LINKING
         +----------------+------------------+
         |                |                  |
     Verification      Preparation        Resolution
     bytecode rules    static storage     symbolic refs
         |                |                  |
         +----------------+------------------+
                          |
                          v
                 (3) INITIALIZATION
             static fields / static blocks
                          |
                          v
                    (4) USAGE
         constructors, calls, reflection, casts,
          ServiceLoader, JNI, resource lookup
~~~

Thứ tự khái niệm không có nghĩa tất cả symbolic references **đều** phải được resolve hết trước khi class initialized. JVMS cho phép eager/lazy resolution tùy quy tắc; một số `LinkageError` có thể chỉ xuất hiện khi chương trình **thực sự gọi method hoặc truy cập field** trong một code path.

**Điểm cốt lõi:** Nếu exception phát sinh khi gọi `foo.bar()`, nó có thể là **lỗi linking/resolution** dù class `Foo` đã được loaded/initialized từ trước.

## 2. Bảng tra cứu nhanh theo giai đoạn

| Giai đoạn / tình huống | Throwable tiêu biểu | Dấu hiệu | Điều tra trước |
|---|---|---|---|
| Explicit class lookup | `ClassNotFoundException` | `Class.forName`/`loadClass` theo tên thất bại | Binary name, caller/explicit loader, classpath/URL |
| JVM cần dependency class | `NoClassDefFoundError` | Cần definition khi link/use nhưng thiếu, hoặc init từng fail | `Caused by`, runtime dependencies, init history |
| Derive class từ bytes | `ClassFormatError` | Class file cấu trúc không hợp lệ | Bytes/JAR, generator và corruption |
| Unsupported class-file version | `UnsupportedClassVersionError` | Bytecode build bằng version mới hơn runtime | `javac --release` và `java -version` |
| Verification | `VerifyError` | Bytecode không thỏa type-safety/stack-map rules | Compiler/instrumentation/transformer |
| Inheritance loading | `ClassCircularityError` | Superclass/interface graph circular bất hợp lệ | Bytecode/inheritance graph |
| Resolution method | `NoSuchMethodError` | Method name + descriptor không có ở runtime type | ABI và version của defining loader |
| Resolution field | `NoSuchFieldError` | Field symbol thiếu sau khi đổi version | Field name/type/staticness/runtime JAR |
| Binary compatibility | `IncompatibleClassChangeError` | Thay đổi không tương thích class/interface/instance/static shape | Compiler vs runtime ABI |
| Invocation | `AbstractMethodError` | Call không có concrete implementation tương thích | Version skew/interface/class hierarchy |
| Access checking | `IllegalAccessError` | JVM từ chối truy cập method/field/class | Runtime package, loader identity, module exports |
| Static initialization | `ExceptionInInitializerError` | Static block/field initializer ném non-Error exception | Root cause trong `<clinit>` |
| Previous failed initialization | `NoClassDefFoundError` | `Could not initialize class ...` ở lần sau | **Lỗi initializer đầu tiên** |
| Reflective lookup | `NoSuchMethodException`/`NoSuchFieldException` | Reflection tìm member theo name/signature không thấy | Java reflection API và đúng signature |
| Reflective accessibility | `IllegalAccessException`/`InaccessibleObjectException` | Reflection bị chặn bởi visibility/module | `public`, `exports`, `opens`, caller |
| Runtime cast | `ClassCastException` | Object không phải instance của runtime target type | `Class.getClassLoader()` của cả hai |
| Array store | `ArrayStoreException` | Ghi object sai runtime component type | Component type và array covariance |
| Native linking | `UnsatisfiedLinkError` | Load JNI binary hoặc native symbol sai | `java.library.path`, ABI, loader ownership |
| Service discovery | `ServiceConfigurationError` | Provider descriptor/type/constructor lỗi | `META-INF/services`, TCCL, module uses/provides |
| Bootstrap method | `BootstrapMethodError` | Bootstrap của `invokedynamic`/dynamic constant fail | Generated bytecode và bootstrap cause |
| Classloader resource exhaustion | `OutOfMemoryError` | Heap/metaspace/native limit | Memory/GC/loader leaks và allocations |

Các bảng là **gợi ý khoanh vùng**, không phải cam kết một throwable chỉ xuất hiện duy nhất ở một bước. Ví dụ `NoClassDefFoundError` có thể xuất hiện do missing dependency **hoặc** class erroneous sau initialization failure.

## 3. Loading: tìm class bytes và tạo runtime class

### 3.1. `ClassNotFoundException` là checked exception của explicit lookup

~~~java
Class<?> type = Class.forName("com.example.plugin.Entry");
~~~

Nếu caller's loader không tìm được tên `com.example.plugin.Entry`, lời gọi có thể ném `ClassNotFoundException`. Đây là **checked exception**, cần catch hoặc `throws`.

Các API hay dùng:

~~~java
Class.forName("p.Entry");
Class.forName("p.Entry", false, pluginLoader);
pluginLoader.loadClass("p.Entry");
~~~

Đây là **mảnh minh họa**; biến `pluginLoader` cần được khai báo. Overload một tham số của `Class.forName` dùng loader của caller theo quy tắc API; overload có `ClassLoader` dùng loader được truyền. `ClassLoader.loadClass` thông thường không yêu cầu initialize ngay, còn `Class.forName(String)` mặc định yêu cầu initialize.

**Những nguyên nhân phổ biến:**

- Binary name sai: dùng `p/Entry.class` thay vì `p.Entry`.
- Sai package capitalization, nested class phải dùng `Outer$Inner`.
- Thư viện có trong build classpath nhưng **không** ở runtime classpath.
- Host class loader không nhìn thấy child plugin JAR.
- `java -jar` dùng manifest/classpath semantics khác `java -cp`.
- Plugin JAR nằm ở URL khác hoặc chưa copy file class vào artifact.
- JPMS named module chưa được resolved trong layer cần thiết.

**Cách xử lý:** xác minh name + loader + artifact roots trước khi thay global classpath.

### 3.2. `NoClassDefFoundError`: không luôn đồng nghĩa CNFE

Một class `Main` đã compile với:

~~~java
MissingLibrary.run();
~~~

nhưng runtime thiếu `MissingLibrary.class`. JVM giải quyết symbolic reference ở code path cần class và có thể ném `NoClassDefFoundError`. Throwable này là một **`LinkageError`**, không phải checked exception.

Thông thường cause chain có thể chứa:

~~~text
java.lang.NoClassDefFoundError: p/MissingLibrary
Caused by: java.lang.ClassNotFoundException: p.MissingLibrary
~~~

Đây là **dạng thông báo minh họa**, stack trace cụ thể phụ thuộc JDK và loader. `NoClassDefFoundError` còn xuất hiện khi class đã bị đánh dấu erroneous sau một initialization failure — nguyên nhân khác hẳn thiếu file.

**Cảnh báo:** Không catch CNFE rồi mặc định rằng mọi `NoClassDefFoundError` sẽ biến mất; phải xác định root cause và phase.

### 3.3. `ClassFormatError` và `UnsupportedClassVersionError`

- `ClassFormatError`: class-file bytes không hợp lệ theo cấu trúc JVM class file, có thể do JAR hỏng, bytecode generator hoặc instrumentation tạo bytes sai.
- `UnsupportedClassVersionError` là subtype của `ClassFormatError`, thường do class file version mới hơn VM hỗ trợ.

Chẩn đoán:

~~~bash
java -version
javac -version
javap -verbose -classpath libs/plugin.jar p.Entry
~~~

`javap -verbose` cho biết `major version` của class khi tool đọc được artifact. Không nên kết luận dựa trên version của source file; compiler `--release`/target mới quyết định bytecode version.

Một cách build tương thích JDK 17:

~~~bash
javac --release 17 -d out src/p/Entry.java
~~~

Lệnh này là mảnh minh họa yêu cầu source đúng path. Với JDK hỗ trợ target 17, nó tạo class file version tương ứng Java 17 và hạn chế API reference theo target release. Nhưng **dependency runtime có native/API version khác** vẫn có thể gây lỗi khác.

### 3.4. `ClassCircularityError`

Khi superclass/superinterface graph bất hợp lệ tạo vòng lặp mà JVM phát hiện trong quá trình loading/linking, `ClassCircularityError` có thể xảy ra. Mã nguồn Java thông thường đã được compiler ngăn nhiều dạng circular inheritance; lỗi này thường liên quan tới bytecode generated/instrumented hoặc classloader có hành vi bất thường.

Không sửa bằng cách tạo thêm loader tùy tiện; kiểm tra **binary class hierarchy**, cycle và generator/build tool.

## 4. Linking gồm verification, preparation và resolution

### 4.1. Verification — `VerifyError`

JVM cần xác nhận bytecode thỏa các ràng buộc về kiểu, operand stack, control flow và class file verification. Ví dụ một transformer sửa bytecode nhưng không cập nhật stack map frames/bytecode metadata phù hợp có thể gây:

~~~text
java.lang.VerifyError: Bad type on operand stack
~~~

Đây là ví dụ wording, không phải output cố định. Những hướng kiểm tra:

- JVM/classfile version đúng không?
- Bytecode generator/ASM/Byte Buddy phiên bản có hỗ trợ target không?
- StackMapTable/branch targets/instruction signatures có hợp lệ không?
- Có Java agent/transformer khác sửa bytes sau compile không?
- Test class file trước và sau instrumentation.

**Đừng tắt bytecode verification trong production** chỉ để vượt lỗi; làm mất lớp bảo vệ type safety.

### 4.2. Preparation — static fields và bộ nhớ

Trong preparation, JVM cấp phát và khởi tạo giá trị mặc định cho những static fields theo quy tắc class preparation (không nhầm với việc chạy các initializer expressions Java trong `<clinit>`). Các lỗi có thể liên quan `OutOfMemoryError` hoặc failures khi chuẩn bị cấu trúc.

Ví dụ:

~~~java
static int count = compute();
~~~

`compute()` không được thực thi bởi preparation như một Java initializer thông thường; nó chạy ở **initialization** khi class được khởi tạo.

Cần phân biệt:

- **Preparation:** tạo trạng thái static mặc định.
- **Initialization:** chạy static field initializers và static blocks theo thứ tự Java.
- **Compile-time constants:** có quy tắc đặc biệt theo JVMS/JLS; đừng giả định mỗi lần đọc constant đều cần initialize class.

### 4.3. Resolution — symbolic references sang runtime entities

Bytecode có các symbolic references tới classes, methods, fields và dynamic call sites. Khi JVM resolve chúng, tên/symbol phải khớp với runtime definitions và access constraints.

Lỗi thường gặp:

| Lỗi | Nguyên nhân điển hình | Cần so sánh |
|---|---|---|
| `NoSuchMethodError` | Runtime class thiếu method đúng descriptor | Method name, params, return descriptor, runtime JAR |
| `NoSuchFieldError` | Runtime class thiếu field tương ứng | Field name/type và binary version |
| `IllegalAccessError` | Access check bị từ chối | `public`/package-private, loader, module |
| `IncompatibleClassChangeError` | Method/class/interface shape không tương thích | Instance vs static, class vs interface, ABI |
| `AbstractMethodError` | Không có concrete implementation phù hợp lúc invocation | Interface evolution, class hierarchy, version skew |
| `BootstrapMethodError` | Bootstrap method của dynamic call site/constant thất bại | Bootstrap target và nested cause |

**Quan trọng:** JVM có thể resolve references khi lần đầu sử dụng chúng, không phải ngay khi class được nạp. Do đó một plugin có thể khởi động thành công nhưng khi gọi một chức năng ít dùng mới phát sinh `NoSuchMethodError`.

### 4.4. Tại sao những lỗi này thường xuất hiện sau khi update thư viện?

Giả sử:

~~~text
Compile-time:
  api.Library v2 có static String extra()

Runtime:
  api.Library v1 không có extra()
~~~

Code `Client` compile được với v2, nhưng application loader thực tế nạp v1. Khi bytecode thực thi `invokestatic api.Library.extra()`, method không tồn tại ở runtime type và JVM ném `NoSuchMethodError`.

Không khắc phục bằng cách đổi `Class.forName` overload khi class đã nạp đúng tên nhưng **sai version/ABI**. Cần sửa classpath/container dependency version hoặc loader ownership.

## 5. Demo Java 17+ tái hiện NoSuchMethodError do version skew

Thí nghiệm cố ý compile `Client` với Library v2 nhưng chạy với v1.

### 5.1. Cấu trúc project

~~~text
project/
  src/
    v1/api/Library.java
    v2/api/Library.java
    client/Client.java
  out/
    v1/
    v2/
    client/
~~~

### 5.2. `src/v1/api/Library.java`

~~~java
package api;

public final class Library {
    public static String hello() {
        return "v1";
    }
}
~~~

### 5.3. `src/v2/api/Library.java`

~~~java
package api;

public final class Library {
    public static String hello() {
        return "v2";
    }

    public static String extra() {
        return "new-api";
    }
}
~~~

### 5.4. `src/client/Client.java`

~~~java
import api.Library;

public final class Client {
    public static void main(String[] args) {
        System.out.println(Library.extra());
    }
}
~~~

### 5.5. Build và chạy

~~~bash
mkdir -p out/v1 out/v2 out/client

javac -d out/v1 src/v1/api/Library.java
javac -d out/v2 src/v2/api/Library.java

javac -cp out/v2 -d out/client src/client/Client.java

java -cp "out/client:out/v1" Client
~~~

Lệnh chạy **cố ý** dùng v1 thay v2. Kết quả là lỗi thuộc dạng:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError: 'java.lang.String api.Library.extra()'
~~~

Đây là **dòng chính minh họa**; stack trace sẽ còn vị trí source và có thể thay đổi chữ ký trình bày tùy JVM. Nếu chạy đúng runtime dependency v2:

~~~bash
java -cp "out/client:out/v2" Client
~~~

Stdout:

~~~text
new-api
~~~

**Bài học:** class `api.Library` vẫn tồn tại và được nạp; vấn đề là **method symbol không khớp runtime definition**. Nó không phải `ClassNotFoundException`.

Trên Windows, classpath separator ở các lệnh `-cp` cần là dấu `;` thay vì `:`.

## 6. Initialization — chạy static blocks và static field initializers

Một class được initialized khi active use hoặc thao tác API yêu cầu theo quy tắc JLS/JVMS. `Class.forName(name, true, loader)` yêu cầu initialization; `Class.forName(name, false, loader)` không yêu cầu.

### `ExceptionInInitializerError`

Nếu static block hoặc static field initializer ném một exception không phải `Error`, JVM thường bọc exception thành `ExceptionInInitializerError`.

~~~java
final class Config {
    static final String VALUE = load();

    static String load() {
        throw new IllegalStateException("bad config");
    }
}
~~~

Đây là class minh họa, chưa có `main`. Khi class được initialized, lỗi gốc có thể là `IllegalStateException` nhưng Throwable ngoài cùng là `ExceptionInInitializerError`. **Đọc `getCause()`** để thấy nguyên nhân thực.

Nếu initializer đã ném một `Error` như `UnsatisfiedLinkError` từ `System.loadLibrary`, Error có thể được propagate trực tiếp, không nhất thiết bị bọc thành `ExceptionInInitializerError`.

### Lần sử dụng sau — `NoClassDefFoundError`

Một runtime class đã thất bại initialization có thể bị đánh dấu **erroneous**. Với cùng defining loader/runtime class, các lần active use sau thường ném:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class ...
~~~

**Không có nghĩa class-file bỗng dưng biến mất.** Muốn sửa, phải tìm **lỗi initializer đầu tiên** và sửa config/dependency/logic; tạo loader generation mới nếu cần nạp định nghĩa class mới. Không retry initializer vô hạn trên cùng erroneous class.

### Nguyên nhân thường gặp của init failure

- Đọc file cấu hình thiếu, environment variable không hợp lệ.
- Static initializer gọi network/database rồi throw.
- Static code dùng dependency method không tương thích.
- `System.loadLibrary` thất bại do JNI binary hoặc duplicate load.
- Circular static initialization tạo trạng thái không như dự định.
- Một static cache tạo resource lớn gây memory issue.

**Thiết kế tốt hơn:** Giảm side effects trong static initializer; dùng factory/lifecycle method có error handling rõ ràng khi khởi tạo plugin/service.

## 7. Demo Java 17+ phân biệt 4 loại lỗi trực tiếp

File độc lập **`PhaseErrorsDemo.java`** dưới đây tạo các trường hợp có chủ đích. Program chỉ bắt rộng `Throwable` trong test harness để in tên lỗi và không che sự khác nhau giữa các tình huống; **không** áp dụng kỹ thuật catch broad này trong production business logic.

### 7.1. Toàn bộ file `PhaseErrorsDemo.java`

~~~java
public final class PhaseErrorsDemo {

    static final class Exploding {
        static {
            if (alwaysFail()) {
                throw new IllegalStateException("broken initializer");
            }
        }

        static boolean alwaysFail() {
            return true;
        }
    }

    public static void main(String[] args) {
        // 1. Explicit lookup một class không có.
        try {
            Class.forName("missing.DoesNotExist");
        } catch (ClassNotFoundException ex) {
            System.out.println("lookup: "
                    + ex.getClass().getSimpleName());
        }

        // 2. Lần active use đầu tiên: initializer exception.
        try {
            Class.forName(
                    Exploding.class.getName(),
                    true,
                    PhaseErrorsDemo.class.getClassLoader());
        } catch (ExceptionInInitializerError ex) {
            System.out.println("init first: "
                    + ex.getClass().getSimpleName());
        }

        // 3. Lần sau: class ở trạng thái erroneous.
        try {
            Class.forName(
                    Exploding.class.getName(),
                    true,
                    PhaseErrorsDemo.class.getClassLoader());
        } catch (NoClassDefFoundError ex) {
            System.out.println("init second: "
                    + ex.getClass().getSimpleName());
        }

        // 4. Object có runtime type String không thể thành Integer.
        Object value = "hello";

        try {
            Integer number = (Integer) value;
            System.out.println(number);
        } catch (ClassCastException ex) {
            System.out.println("cast: "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

### 7.2. Biên dịch và chạy

~~~bash
javac PhaseErrorsDemo.java
java PhaseErrorsDemo
~~~

**Stdout dự kiến trên JDK 17+:**

~~~text
lookup: ClassNotFoundException
init first: ExceptionInInitializerError
init second: NoClassDefFoundError
cast: ClassCastException
~~~

**Giải thích:**

1. `missing.DoesNotExist` không có trong loader của caller nên explicit lookup ném checked `ClassNotFoundException`.
2. `Exploding.class` chỉ lấy class literal, không yêu cầu initialize. `Class.forName(..., true, ...)` lần đầu chạy static block; `alwaysFail()` trả `true` và `IllegalStateException` bị bọc thành `ExceptionInInitializerError`.
3. JVM không tự chạy lại initializer của cùng erroneous class như một class mới; lần active use tiếp theo gây `NoClassDefFoundError`.
4. Object String và runtime type Integer không tương thích nên cast ném `ClassCastException` ở **giai đoạn sử dụng**.

Dòng 2–3 chứng minh vì sao phải lưu **stack trace của lần thất bại đầu tiên**: nếu logs chỉ bắt đầu ở lần retry, người vận hành có thể nhìn `NoClassDefFoundError` và tưởng thiếu file class.

## 8. Usage — lỗi xuất hiện dù loading và initialization thành công

### 8.1. `ClassCastException` và defining class loader

Hai class có cùng binary name nhưng được hai defining loaders khác nhau định nghĩa là **hai runtime types khác nhau**:

~~~text
(com.acme.Plugin, LoaderA) != (com.acme.Plugin, LoaderB)
~~~

Một object tạo bởi LoaderA không thể tự động cast thành implementation type do LoaderB định nghĩa, dù bytecode giống nhau. Trong hệ plugin, lỗi này thường do:

- Shared SPI/interface bị child-first loader định nghĩa lại.
- Host và plugin đóng gói hai bản API cùng tên.
- Classloader hierarchy không delegate đúng parent.
- Object từ generation cũ được truyền sang generation mới.

**Fix:** đưa shared API/DTOs vào loader cha chung và giao tiếp qua những runtime types thống nhất. Không dùng `--add-opens` để “sửa” class identity khác loader; module openness không hợp nhất hai loại `Class<?>`.

### 8.2. `NoSuchMethodException` khác `NoSuchMethodError`

Reflection:

~~~java
String.class.getMethod("methodThatDoesNotExist");
~~~

Ném **checked `NoSuchMethodException`** vì người gọi đang tìm method theo tên và signature bằng API reflection.

Ngược lại, bytecode `invokevirtual`/`invokestatic` tham chiếu method mà runtime type không có có thể gây **`NoSuchMethodError`**. Đây là `LinkageError`, thường do binary incompatibility.

**Không dùng hai tên lỗi này thay thế cho nhau** khi tìm hướng xử lý.

### 8.3. `IllegalAccessException` và `IllegalAccessError`

`IllegalAccessException` thuộc checked exceptions của reflection khi caller không được phép truy cập method/constructor/field theo access checks.

`IllegalAccessError` thuộc `LinkageError`, có thể xảy ra khi bytecode truy cập member/class không còn accessible ở runtime, chẳng hạn:

- Method từng `public` khi compile nhưng runtime version giảm visibility.
- Hai class cùng source package bị chia vào **different defining loaders**, nên không còn cùng runtime package cho package-private access.
- Một module export/access change phá rule bytecode cần.

Với JPMS reflection, `InaccessibleObjectException` là **runtime exception** có thể phát sinh khi `setAccessible(true)` bị từ chối do module encapsulation. Không chỉ cần “đúng tên” class mà còn phải tuân thủ exports/opens.

### 8.4. `ArrayStoreException`

Java arrays có runtime component type; khi lưu object không assignable vào reference array:

~~~java
Object[] elements = new String[1];
elements[0] = 123;
~~~

Đây là **mảnh minh họa**, chạy gây `ArrayStoreException`. Class loading và linking có thể hoàn toàn đúng; lỗi thuộc hành vi sử dụng/mutation của array.

### 8.5. `ServiceConfigurationError`

`ServiceLoader` đọc service provider config hoặc module `provides` và tìm/khởi tạo provider lazy. Các lỗi:

- `META-INF/services/<SPI binary name>` sai tên.
- Descriptor chứa provider binary name không tồn tại.
- Provider không assignable về runtime SPI interface.
- Constructor/factory method không đúng contract.
- TCCL hoặc explicit loader không thấy plugin.
- Module provider chưa resolved hoặc consumer thiếu `uses` theo module contract.

Có thể ném `ServiceConfigurationError` khi iterate/stream, không phải lúc `ServiceLoader.load(...)` tạo instance. Đây là **Error do service discovery**, có thể chứa CNFE/linkage/init failures làm cause.

### 8.6. `UnsatisfiedLinkError`

Native linkage có đường xử lý riêng:

~~~java
System.loadLibrary("codec");
~~~

Đây là mảnh minh họa, yêu cầu JNI binary thật. Nếu không tìm thấy library, sai OS/ABI/architecture, thiếu native dependency, JNI symbol hoặc native library đã thuộc classloader khác, có thể ném `UnsatisfiedLinkError`.

JNI library trong nhiều child loaders có **ownership rule**; thêm Java classpath không phải cách sửa cross-loader native-library conflict. Thường cần shared JNI bridge ở parent hoặc tách process khi native state không thể chia sẻ.

## 9. Bảng so sánh những cặp dễ nhầm

| Cặp lỗi | Sự khác nhau chủ yếu | Ví dụ nhận diện |
|---|---|---|
| `ClassNotFoundException` vs `NoClassDefFoundError` | Explicit string lookup (checked) vs JVM class definition/linkage/previous init (Error) | `Class.forName("missing.X")` vs bytecode `new X()` thiếu dependency |
| `NoSuchMethodException` vs `NoSuchMethodError` | Reflection lookup checked vs symbolic method resolution binary mismatch | `getMethod("missing")` vs build v2/run v1 |
| `IllegalAccessException` vs `IllegalAccessError` | Reflection API access denied vs bytecode access/linkage denied | `getMethod.invoke` vs runtime package split |
| `ExceptionInInitializerError` vs `NoClassDefFoundError` after init | Lần đầu static non-Error exception vs lần sau class erroneous | Demo `Exploding` |
| `ClassFormatError` vs `VerifyError` | Class-file structure invalid vs bytecode fails verifier constraints | Broken format vs invalid operand stack |
| `ClassCastException` vs `IllegalAccessError` | Runtime type mismatch vs bytecode access denied | Duplicate SPI classes vs package-private split |
| `UnsatisfiedLinkError` vs `ClassNotFoundException` | Native library/method linkage vs Java class name lookup | `System.loadLibrary` vs `loadClass` |
| `OutOfMemoryError` vs classloader leak | Throwable là resource exhaustion; leak chỉ là một khả năng nguyên nhân | Metaspace tăng + retained loaders |

Một error message có thể chứa **nhiều loại Throwable trong cause chain**. Hãy phân loại **outermost error + root cause + first failure**, không chỉ tìm chữ “class” trong thông báo.

## 10. Cách xác định giai đoạn từ stack trace/cause chain

### Bước 1 — Xác định thao tác đang chạy

- `Class.forName`/`ClassLoader.loadClass`: explicit name lookup, có initialization flag không?
- Constructor call/`new`: có cần linking/init không?
- `invokestatic`/`invokevirtual`: method resolution/invocation.
- `getstatic`/`putstatic`: field resolution/initialization.
- `ServiceLoader` iterator: provider discovery/instantiate.
- `System.load`/`native`: JNI loader/symbol.
- Reflection `getMethod`/`invoke`: reflective lookup/access/target invocation.

### Bước 2 — Đọc cause chain đầy đủ

Ví dụ:

~~~text
ExceptionInInitializerError
  caused by IllegalStateException: missing config
~~~

Fix thiếu config/static init, **không** thêm JAR ngẫu nhiên.

Ví dụ:

~~~text
NoClassDefFoundError: p/Dependency
  caused by ClassNotFoundException: p.Dependency
~~~

Fix runtime dependency/loader visibility.

Ví dụ:

~~~text
ServiceConfigurationError
  caused by provider not found / not assignable
~~~

Fix provider descriptor/visibility/runtime SPI identity.

### Bước 3 — In classloader và nguồn class

Khi đã có `Class<?>`:

~~~java
Class<?> type = object.getClass();
ClassLoader loader = type.getClassLoader();

System.out.println("type=" + type.getName());
System.out.println("loader=" + loader);
System.out.println("module=" + type.getModule());
~~~

Đây là mảnh minh họa với `object` khác null. `getClassLoader() == null` với bootstrap classes là bình thường.

Nếu CodeSource khả dụng:

~~~java
var domain = type.getProtectionDomain();
var codeSource = domain == null ? null : domain.getCodeSource();

System.out.println(codeSource == null
        ? "source unknown"
        : codeSource.getLocation());
~~~

Không phải class nào cũng có CodeSource hữu ích; có thể `null`. Với error chưa load được class, bắt đầu từ **caller loader, binary name và actual runtime URLs**.

### Bước 4 — Kiểm tra artifact/ABI

~~~bash
jar --list --file libs/plugin.jar
javap -classpath libs/plugin.jar -public p.Api
javap -classpath libs/plugin.jar -verbose p.Api
~~~

Các lệnh là ví dụ chẩn đoán, cần JAR và class tương ứng. `javap -public` có thể kiểm tra method signatures, `-verbose` xem class-file major version và constant pool; đừng chỉ tin dependency tree lúc build.

### Bước 5 — JVM logging/JFR

Trên HotSpot Java 17:

~~~bash
java -Xlog:class+load=info,class+unload=info \
    -cp out/app Main
~~~

Đây là **lệnh chẩn đoán**, không phải stdout cố định. Class-loading logs/JFR giúp thấy class/source/load/unload behavior nhưng không tự giải thích mọi access/cast/init/linkage errors. Khi nghi leak, phối hợp classloader stats, metaspace metrics, thread/TCCL inspection và heap dump.

## 11. Phân biệt lỗi do classpath, loader identity và module access

### Classpath/configuration

Một class `p.Feature` có thể nằm ở `plugins/p/Feature.class` nhưng JVM chỉ chạy với `-cp out/app`. Explicit lookup qua app loader không thấy nó và CNFE. Dùng đúng root URL/classpath hoặc explicit plugin loader.

### Loader identity

Hai copies cùng `api.Service` trong host và child-first plugin không phải cùng runtime interface. Cast/provider verification có thể fail dù class file tồn tại ở cả hai nơi.

### JPMS module access

Một class trong named module có thể tồn tại và được resolved, nhưng package không exported/opened phù hợp cho caller. Điều này không đồng nghĩa luôn CNFE; có thể gặp `IllegalAccessError`, `IllegalAccessException` hoặc `InaccessibleObjectException` tùy API/phase.

**Không dùng `--add-opens` như “fix mọi lỗi class loading”**; nó không đổi class identity và không thêm thiếu methods/dependencies.

## 12. Binary compatibility và change matrix

| Thay đổi giữa compile/runtime | Nguy cơ |
|---|---|
| Xóa method hoặc đổi method descriptor | `NoSuchMethodError` |
| Xóa field/đổi descriptor | `NoSuchFieldError` |
| Đổi method từ static sang instance hoặc ngược lại | `IncompatibleClassChangeError` hoặc subtype liên quan |
| Đổi class thành interface hoặc ngược lại | `IncompatibleClassChangeError` |
| Thay visibility khiến caller không access được | `IllegalAccessError` |
| Thêm abstract method nhưng runtime implementation không thỏa | `AbstractMethodError` khi invocation |
| Thay superclass/interfaces không nhất quán | Có thể `IncompatibleClassChangeError` hoặc lỗi liên quan |
| Build class file cho Java cao hơn runtime | `UnsupportedClassVersionError` |
| Instrumentation làm bytecode invalid | `VerifyError` hoặc `ClassFormatError` |
| Duplicate shared API ở nhiều loaders | `ClassCastException`, `LinkageError`/provider errors |
| Native library/method ABI không hợp lệ | `UnsatisfiedLinkError` |

Đây là bảng **nguy cơ thường gặp**, không đảm bảo mỗi thay đổi chỉ dẫn tới đúng một throwable duy nhất. JVM resolution/invocation rules và code path cụ thể quyết định lỗi được quan sát.

### Tại sao chỉ compiler/test unit vẫn chưa đủ?

Mã `Client` biên dịch với dependency v2, nhưng production launcher/container dùng v1. Compile-time classpath **khác runtime loader graph**, nên unit test có thể pass còn deployment ném `NoSuchMethodError`.

**Nên test cuối cùng với artifact và startup command thực tế**: parent classloader, child loaders, module path, JAR order, Java runtime version, resources và providers.

## 13. Quy trình xử lý lỗi theo nhóm

### A. Explicit lookup thất bại

1. Ghi chuỗi binary name thực sự truyền vào API.
2. Xác định overload `Class.forName`/`loadClass` và loader đang dùng.
3. Kiểm tra `jar --list`/directory root.
4. Xem launcher `-cp`, `-jar`, JPMS module graph.
5. Dùng explicit loader khi class được sở hữu bởi plugin child; đừng phá shared API boundary.

### B. Linking/ABI thất bại

1. Tìm method/field/class symbol trong exception.
2. Xác định defining loader của class thực tế được JVM nạp.
3. So runtime CodeSource/JAR với compile-time version.
4. So binary descriptors bằng `javap`.
5. Sửa version alignment hoặc selective loader policy nếu private dependencies cần bản riêng.

### C. Initialization thất bại

1. Tìm **lỗi đầu tiên** trong `<clinit>`.
2. Đọc underlying cause: config, JNI, DB, static code, dependency.
3. Không retry initializer vô hạn trên cùng erroneous class.
4. Sau khi sửa, dùng JVM/plugin generation phù hợp theo lifecycle.

### D. Runtime sử dụng/cast/access thất bại

1. So runtime `Class<?>` identity, không chỉ tên.
2. Xác minh shared SPI/DTO/interface từ một defining loader.
3. Kiểm tra reflection access/module exports/opens nếu liên quan.
4. Đừng đổi classpath mù quáng khiến thêm duplicate classes.

### E. Native/service discovery thất bại

1. JNI: kiểm tra lib path, OS/architecture, symbols, cross-loader native library ownership.
2. SPI: kiểm tra `META-INF/services` hoặc `uses`/`provides`.
3. Kiểm tra TCCL/explicit loader, provider class và constructor.
4. Chạy test thật sự instantiate provider/native call.

## 14. Anti-pattern khi chẩn đoán

**Bắt mọi Throwable rồi bỏ qua:**

~~~java
try {
    Class.forName(configuredName);
} catch (Throwable ignored) {
    // Sai: che hết linkage, init, memory, native...
}
~~~

Đây là đoạn **anti-pattern minh họa**, không phải giải pháp. Nếu cần plugin tùy chọn, bắt `ClassNotFoundException` ở boundary phù hợp và phân loại các loại `LinkageError` nghiêm trọng theo policy rõ ràng.

**Sửa tất cả bằng cách thêm mọi JAR vào application classpath:** có thể khiến Java class lookup pass nhưng phá version isolation, tạo `ClassCastException`, `NoSuchMethodError` hoặc duplicate native wrappers.

**Dùng `System.gc()` để chữa mọi lỗi classloader:** GC không thay binary method signatures, không sửa classpath, không buộc native library unload ngay và không tái chạy static initializer của erroneous class.

**Bật `--add-opens` bất kể lỗi:** module openness chỉ giải quyết một phần reflection/resource access; không chữa missing class/method hoặc type identity.

**Chỉ đọc exception message, bỏ cause:** nhiều errors là wrappers của lỗi sâu hơn; cần chuỗi cause, suppressed exceptions và thời điểm thất bại đầu tiên.

## 15. Checklist tra cứu nhanh trước khi sửa code

- [ ] Xác định throwable ngoài cùng thuộc `Exception`, `Error`, `LinkageError` hay runtime exception.
- [ ] Tìm giai đoạn loading, linking, initialization hay usage gây ra lỗi.
- [ ] Xác định API call/bytecode operation kích hoạt hành vi.
- [ ] Kiểm tra binary class/member name và chữ ký đầy đủ.
- [ ] Phân biệt `ClassNotFoundException` với `NoClassDefFoundError`.
- [ ] Nếu `NoClassDefFoundError`, kiểm tra init history và root cause.
- [ ] Nếu `ExceptionInInitializerError`, giữ nguyên stack trace của lần đầu.
- [ ] Nếu `NoSuchMethodError`/`NoSuchFieldError`, so compile/runtime ABI.
- [ ] Nếu `ClassCastException`, kiểm tra defining loader hai bên.
- [ ] Nếu `IllegalAccessError`, kiểm tra runtime package identity và JPMS exports.
- [ ] Nếu `VerifyError`, xem transformer/generator và classfile version.
- [ ] Nếu `UnsupportedClassVersionError`, kiểm tra Java target/runtime.
- [ ] Nếu `UnsatisfiedLinkError`, kiểm tra native ABI/library ownership.
- [ ] Nếu `ServiceConfigurationError`, kiểm tra descriptor/TCCL/JPMS provider rules.
- [ ] Không suy ra error timing luôn trùng thời điểm `loadClass`; linking resolution có thể lazy.
- [ ] Không dùng cùng giải pháp “thêm JAR” cho mọi nhóm lỗi.
- [ ] Test artifact cuối đúng launcher và classloader policy.
- [ ] Ghi đủ metadata loader/code source mà không lộ secrets.
- [ ] Nếu dùng plugin generation, dọn TCCL/caches/threads đúng lifecycle.

## 16. Bài tập tự kiểm tra

**Câu 1.** `Class.forName("p.Missing")` ném checked exception gì?

**Đáp án:** `ClassNotFoundException` nếu loader của caller không tìm được class; hãy kiểm tra binary name và loader/search path.

**Câu 2.** Client compile với method `Library.extra()` của v2 nhưng runtime nạp Library v1. Lỗi thường là gì?

**Đáp án:** `NoSuchMethodError` khi resolve/invoke method symbol, vì v1 không có method descriptor tương ứng.

**Câu 3.** Static initializer ném `IllegalStateException` ở lần dùng đầu, lỗi ngoài cùng có thể là gì?

**Đáp án:** `ExceptionInInitializerError`. Lần active use sau trên same erroneous class có thể thành `NoClassDefFoundError`.

**Câu 4.** Hai loaders khác nhau tự define cùng `api.Plugin`. Có chắc object plugin cast được về host `api.Plugin` không?

**Đáp án:** Không. Cùng binary name không đủ; khác defining loader là runtime types khác nhau, có thể `ClassCastException`.

**Câu 5.** `NoSuchMethodException` có luôn nghĩa `NoSuchMethodError` không?

**Đáp án:** Không. Một cái là checked reflection lookup exception, cái kia là `LinkageError` do symbolic method resolution/invocation mismatch.

**Câu 6.** Tại sao `VerifyError` không nên được sửa bằng cách tắt verifier?

**Đáp án:** Nó phản ánh bytecode không thỏa type-safety constraints; cần sửa generator/transformer/classfile thay vì bỏ lớp kiểm tra an toàn của JVM.

**Câu 7.** Class file major version quá mới so với JDK chạy, loại lỗi nào thường gặp?

**Đáp án:** `UnsupportedClassVersionError`; dùng compiler `--release` hoặc runtime phù hợp.

**Câu 8.** Plugin loader có class `p.C` nhưng `Class.forName("p.C")` từ host CNFE. Vì sao?

**Đáp án:** Caller loader không nhìn thấy child plugin loader; cần explicit plugin loader hoặc framework API phù hợp.

**Câu 9.** Reflection `setAccessible(true)` bị cấm vì named module không mở package. Đây có phải missing class không?

**Đáp án:** Không. Đây là access/module encapsulation issue, có thể `InaccessibleObjectException`; xử lý module policy phù hợp.

**Câu 10.** JNI lib nạp vào LoaderA rồi LoaderB cố nạp cùng library. Lỗi gì và fix kiến trúc?

**Đáp án:** `UnsatisfiedLinkError` do native-library ownership; dùng shared JNI bridge do parent sở hữu hoặc tách process nếu cần native state độc lập.

## 17. Cây quyết định tra cứu

~~~text
Throwable xuất hiện khi dùng Java class/plugin
                      |
                      v
          API/action nào kích hoạt?
           /       |        |       \
       Lookup    Linkage   Init    Runtime usage
         |         |        |         |
         v         v        v         v
    CNFE/NCDFE  ABI/verify  static    cast/access/
         |      /format      code     reflection/JNI
         |         |        |         |
   name+loader  version+    cause    type identity/
   +artifact    bytecode    chain    service/native
         \         |         |         /
          \        |         |        /
                  v
       Xác nhận giai đoạn + root cause
                  |
        so runtime defining loader,
        CodeSource, module, signature
                  |
                  v
       sửa đúng dependency/policy/code
                  |
                  v
      kiểm thử với artifact + JVM thật
~~~

**Kết luận:** Một lỗi “có chữ class” không nhất thiết là lỗi classpath. **Loading** chủ yếu là tìm/định nghĩa kiểu; **linking** là kiểm tra và giải quyết symbolic references; **initialization** chạy static code; **usage** gồm gọi method, reflection, cast, SPI và JNI. Xác định đúng giai đoạn, **Throwable type**, **cause chain**, **runtime defining loader** và **artifact ABI** mới cho phép sửa lỗi bền vững mà không tạo xung đột classloaders khác.

### Tài liệu chuẩn

- [JVMS 17 — Chapter 5: Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java SE 17 — ClassNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html)
- [Java SE 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html)
- [Java SE 17 — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html)
- [Java SE 17 — LinkageError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html)
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java 17 Java Language Specification — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
