# Phân biệt loading, linking và initialization trong Java 15+ — Khởi tạo và sinh mã

## 1. Ba khái niệm khác nhau trong vòng đời một class

Trong Java, việc JVM biết đến một class **không đồng nghĩa** mã trong khối `static` đã chạy. JVM phân biệt ba hoạt động:

1. **Loading (nạp lớp):** lấy biểu diễn nhị phân của một class/interface và tạo đối tượng `Class<?>` tương ứng trong JVM.
2. **Linking (liên kết):** kiểm tra tính đúng đắn của class file và bytecode (*verification*), chuẩn bị vùng dữ liệu tĩnh (*preparation*), và phân giải tham chiếu tượng trưng (*resolution*) khi thích hợp.
3. **Initialization (khởi tạo lớp):** chạy các bộ khởi tạo trường `static` và khối `static { ... }`; trong mô hình JVM, logic khởi tạo class tương ứng phương thức đặc biệt `<clinit>`.

Các cơ chế này vẫn được quy định trong Java Language Specification (JLS) §12.2–§12.4 và Java Virtual Machine Specification (JVMS) Chương 5, áp dụng trên Java 17+ và các JDK hiện đại. Trong module Java 15, chúng đặc biệt hữu ích khi hiểu `MethodHandles.Lookup.defineHiddenClass`, class loader và code generation.

```text
Mã .class / byte[] do compiler hoặc code generator tạo ra
                         |
                         v
              LOADING  → Class<?>
                         |
                         v
              LINKING
                - Verification
                - Preparation
                - Resolution (*)
                         |
                         v
              INITIALIZATION → chạy khối static và bộ khởi tạo static
                         |
                         v
              Sử dụng class đã khởi tạo
```

**Dấu `(*)` quan trọng:** Resolution có thể được thực hiện sớm hoặc trì hoãn tới lúc sử dụng tham chiếu. Sơ đồ chỉ thể hiện quan hệ khái niệm, không cam kết mọi JVM sẽ phân giải toàn bộ dependency trước khi chạy phần khởi tạo tĩnh.

| Hoạt động | Kết quả chính | Bản thân thao tác có yêu cầu chạy static initializer không? |
| --- | --- | --- |
| Loading | Tạo/nhận `Class<?>` đại diện lớp | Không |
| Linking | Verify, prepare và resolve theo quy tắc JVM | Không |
| Initialization | Thực thi code khởi tạo tĩnh của lớp | Có |

Quy tắc cốt lõi: một class **phải được nạp, xác minh và chuẩn bị trước khi khởi tạo**; nhưng việc nạp hoặc liên kết không bắt buộc kéo theo khởi tạo.

## 2. Loading: class được nhận diện trong JVM như thế nào?

Đối với class có tên thông thường, JVM thông qua `ClassLoader` tìm một biểu diễn nhị phân (thường là file `.class`) và tạo đối tượng `Class<?>` đại diện. Class loader có vai trò xác định danh tính và môi trường nạp class.

Ví dụ dùng loader theo tên:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("java.util.ArrayList");
```

Lời gọi trên có thể trả về `Class<?>` của `ArrayList`; nó **không tự yêu cầu thực thi static initializer** của class. Danh tính một class thường được xác định bởi tên nhị phân (*binary name*) kết hợp defining class loader; cùng tên do hai loader khác nhau định nghĩa có thể là hai class khác nhau.

Điều cần phân biệt:

- *Tìm/nạp class* không tương đương *tạo đối tượng của class* bằng `new`.
- Một class có `Class<?>` nhưng chưa được initialize vẫn là class hợp lệ trong runtime.
- Khi tải class, JVM có thể phải nạp thêm superclass và những phụ thuộc cần thiết.
- Class có thể được nạp từ bytecode do `javac` sinh hoặc từ cơ chế sinh class động được Java hỗ trợ.

**Riêng hidden class:** `Lookup.defineHiddenClass(byte[], ...)` tạo class từ `byte[]` và trả về `Lookup` của class mới. Hidden class vẫn có đối tượng `Class<?>`, nhưng **không có binary name để `Class.forName` hay `ClassLoader.loadClass` tìm lại theo tên**. Không nhầm hạn chế tra cứu tên với việc “không được nạp hoặc không được liên kết”.

## 3. Linking gồm ba hoạt động nào?

### 3.1. Verification — xác minh bytecode

JVM kiểm tra định dạng và tính đúng đắn của class file/bytecode: opcode hợp lệ, kiểu operand stack phù hợp, vị trí nhảy đúng ranh giới instruction, chữ ký method và những cấu trúc JVM có liên quan.

Một class file sai có thể dẫn tới `ClassFormatError`; class file có phiên bản không được JVM hiện tại hỗ trợ có thể dẫn tới `UnsupportedClassVersionError`; bytecode không vượt qua quy tắc verifier có thể dẫn tới `VerifyError`.

Các lỗi này **không cần chờ static initializer chạy**: với class sinh động, chỉ riêng việc định nghĩa/liên kết class cũng đã có thể phát hiện lỗi.

### 3.2. Preparation — chuẩn bị static fields

Preparation tạo không gian và cấu trúc runtime cho các trường `static`, với giá trị mặc định theo kiểu dữ liệu. Các phép gán từ source code của bộ khởi tạo trường `static` thông thường được thực hiện ở **initialization**, không phải preparation.

```java
class Counter {
    static int count = 10;
}
```

Ở preparation, `count` được chuẩn bị với giá trị mặc định của `int` là `0`; khi initialize class, phép gán `count = 10` mới chạy.

**Ngoại lệ cần nhớ:** các *constant variables* như `static final int LIMIT = 10` có quy tắc `ConstantValue` và có thể được compiler nhúng vào bytecode nơi sử dụng. Đừng suy luận rằng mọi trường `static final` sẽ đợi chạy `<clinit>` mới có giá trị có thể đọc được.

### 3.3. Resolution — phân giải symbolic references

Class file có thể chứa tham chiếu tượng trưng đến class, method và field khác. Resolution là hoạt động chuyển các tham chiếu đó thành thành phần runtime phù hợp, đồng thời kiểm tra quyền truy cập và tính tương thích.

Ví dụ: bytecode tham chiếu method có tên và descriptor, nhưng ở runtime phiên bản dependency đã thay đổi. JVM có thể báo `NoSuchMethodError`, `NoSuchFieldError` hoặc `IllegalAccessError` khi phân giải/thực sự sử dụng tham chiếu.

**Không phải mọi resolution xảy ra trước initialization.** JVM được phép giải một số tham chiếu sớm, một số khác khi có nhu cầu sử dụng. Vì vậy, không thể dựa vào một bản in log để khẳng định lịch trình resolution cố định cho mọi JVM.

## 4. Initialization: khi nào `<clinit>` chạy?

Initialization của class thực thi các biểu thức khởi tạo trường tĩnh và khối `static { ... }` theo thứ tự quy định. JVM tự đồng bộ hóa việc khởi tạo class trước nhiều luồng, và một class đã khởi tạo thành công sẽ không chạy lại static initializer mỗi lần được gọi.

Những tình huống phổ biến **yêu cầu** class được initialize trước khi sử dụng:

- Tạo instance bằng `new` khi class đó chưa được khởi tạo.
- Gọi phương thức `static` được khai báo bởi class.
- Gán trường `static` hoặc đọc một trường `static` không phải *constant variable*.
- Gọi `Class.forName(binaryName)` hoặc `Class.forName(binaryName, true, loader)`.
- Một số thao tác reflection hoặc Method Handles có yêu cầu khởi tạo.
- Chủ động gọi `MethodHandles.Lookup.ensureInitialized(clazz)` bằng lookup có quyền phù hợp.

Khi initialize một class, JVM cũng bảo đảm superclass cần thiết được khởi tạo trước; các superinterface khai báo default method có những điều kiện liên quan theo JLS §12.4.1. Không nên cho rằng mọi interface đều được initialize chỉ vì một class được nạp.

### 4.1. Những thao tác không tự yêu cầu initialization

```java
Class<?> type = Example.class;
Class<?> loaded = loader.loadClass("com.example.Example");
Class<?> found = Class.forName("com.example.Example", false, loader);
```

`Example.class` (class literal), `ClassLoader.loadClass(String)` và `Class.forName(name, false, loader)` **không tự yêu cầu** khối `static` chạy. Tuy nhiên, class có thể đã qua loading hoặc linking, và các class liên quan có thể chịu những hoạt động riêng.

Ngược lại, `Class.forName(name)` hoặc `Class.forName(name, true, loader)` yêu cầu class được khởi tạo. Vì vậy, khi đọc cấu hình class/plugin theo tên, lựa chọn tham số `initialize` có thể làm thay đổi thời điểm các side effect của static initializer xuất hiện.

### 4.2. Compile-time constant khác static field thông thường

```java
class Config {
    static final int VERSION = 7;    // compile-time constant
    static int runtimeVersion = compute();

    static int compute() {
        return 8;
    }
}
```

Việc đọc `Config.VERSION` có thể chỉ sử dụng hằng `7` đã được compiler nhúng, **không kéo theo initialization** của `Config`. Nhưng đọc `Config.runtimeVersion` yêu cầu class khởi tạo, do đó `compute()` được thực thi.

Đây là lỗi suy luận phổ biến khi kiểm thử “class đã initialize hay chưa” chỉ bằng việc đọc một trường `static final`.

## 5. So sánh các API trong Java hiện đại

| API/tác vụ | Nhận class/định nghĩa class? | Có chủ động yêu cầu khởi tạo class đích? |
| --- | --- | --- |
| `SomeClass.class` | Nhận `Class<?>` của class | Không |
| `loader.loadClass(name)` | Tra cứu/nạp class có tên | Không |
| `Class.forName(name, false, loader)` | Tìm/nạp, liên kết class khi cần | Không |
| `Class.forName(name)` | Tìm/nạp class | Có |
| `Class.forName(name, true, loader)` | Tìm/nạp class | Có |
| `Lookup.defineHiddenClass(bytes, false)` | Định nghĩa và liên kết hidden class mới | Không |
| `Lookup.defineHiddenClass(bytes, true)` | Định nghĩa và liên kết hidden class mới | Có |
| `hiddenLookup.ensureInitialized(hidden)` | Sử dụng class đã có | Có, nếu class chưa init |

Ghi chú: **`initialize=false` không có nghĩa “chỉ load, không link”**. Với `defineHiddenClass`, đặc tả API nói rõ hidden class mới được JVM **linked** sau khi tạo; cờ `initialize` điều khiển việc có tiếp tục chạy class initialization hay không.

## 6. Ví dụ Java 17+ đầy đủ, chạy độc lập

Ví dụ này dùng một named class, một class khác khởi tạo qua `Class.forName(..., true, ...)`, rồi dùng bytecode nested class làm khuôn tạo **hidden class**. Dòng log giúp phân biệt rõ thời điểm chạy static initializer.

Tạo file **`ClassLifecycleDemo.java`**:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class ClassLifecycleDemo {
    static class Named {
        static final int CONSTANT = 7;
        static int value = init();
        static int init() {
            System.out.println("Named <clinit>");
            return 42;
        }
    }
    static class Eager {
        static {
            System.out.println("Eager <clinit>");
        }
    }
    static class Template {
        static {
            System.out.println("Hidden <clinit>");
        }
        static String hello() {
            return "hidden-ready";
        }
    }

    static byte[] templateBytes() throws Exception {
        Class<?> type = Template.class;
        String path = "/" + type.getName().replace('.', '/') + ".class";
        try (InputStream in = type.getResourceAsStream(path)) {
            if (in == null) {
                throw new IllegalStateException("Missing: " + path);
            }
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        ClassLoader loader = ClassLifecycleDemo.class.getClassLoader();
        String name = ClassLifecycleDemo.class.getName() + "$Named";

        System.out.println("constant=" + Named.CONSTANT);
        Class<?> loaded = loader.loadClass(name);
        System.out.println("loadClass=" + loaded.getSimpleName());
        Class<?> linked = Class.forName(name, false, loader);
        System.out.println("forNameFalseSame=" + (loaded == linked));
        System.out.println("beforeNamedActiveUse");
        System.out.println("namedValue=" + Named.value);
        System.out.println("namedValueAgain=" + Named.value);

        String eagerName = ClassLifecycleDemo.class.getName() + "$Eager";
        System.out.println("beforeForNameTrue");
        Class.forName(eagerName, true, loader);
        System.out.println("afterForNameTrue");

        MethodHandles.Lookup hiddenLookup = MethodHandles.lookup()
                .defineHiddenClass(templateBytes(), false,
                        MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> hidden = hiddenLookup.lookupClass();
        System.out.println("isHidden=" + hidden.isHidden());
        System.out.println("beforeHiddenInit");
        hiddenLookup.ensureInitialized(hidden);
        System.out.println("afterHiddenInit");
        hiddenLookup.ensureInitialized(hidden);
        MethodHandle mh = hiddenLookup.findStatic(hidden, "hello",
                MethodType.methodType(String.class));
        System.out.println("hiddenCall=" + (String) mh.invokeExact());
    }
}
```

Dùng JDK 17 trở lên, **biên dịch trước khi chạy** (để tạo cả file `ClassLifecycleDemo$Template.class`), rồi thực hiện:

```bash
javac --release 17 ClassLifecycleDemo.java
java ClassLifecycleDemo
```

Output chính xác (đã kiểm chứng bằng JDK 24 khi biên dịch `--release 17`):

```text
constant=7
loadClass=Named
forNameFalseSame=true
beforeNamedActiveUse
Named <clinit>
namedValue=42
namedValueAgain=42
beforeForNameTrue
Eager <clinit>
afterForNameTrue
isHidden=true
beforeHiddenInit
Hidden <clinit>
afterHiddenInit
hiddenCall=hidden-ready
```

### 6.1. Giải thích phần named classes

1. `constant=7` xuất hiện trước bất kỳ log `Named <clinit>` nào, vì `CONSTANT` là compile-time constant và được nhúng tại nơi dùng.
2. `loadClass=Named` chứng minh `loader.loadClass(name)` tìm được class nhưng **chưa chạy** initializer.
3. `forNameFalseSame=true` chứng minh overload `false` trả về cùng class object mà vẫn chưa init.
4. Ngay khi đọc `Named.value`, JVM cần khởi tạo `Named`; vì vậy `Named <clinit>` xuất hiện **trước** `namedValue=42`.
5. `namedValueAgain=42` không có log initializer lặp lại.
6. `Class.forName(eagerName, true, loader)` yêu cầu khởi tạo `Eager`, nên `Eager <clinit>` xuất hiện giữa `beforeForNameTrue` và `afterForNameTrue`.

### 6.2. Giải thích phần hidden class

1. `Template.class` và `getResourceAsStream` lấy bytecode của nested class nhưng không tự chạy static initializer của `Template`.
2. `defineHiddenClass(..., false, NESTMATE)` **định nghĩa và liên kết** một hidden class mới từ bytecode. `false` không yêu cầu khởi tạo ngay; `hidden.isHidden()` vẫn trả về `true`.
3. Dòng `beforeHiddenInit` xuất hiện rồi `hiddenLookup.ensureInitialized(hidden)` mới chạy mã `static`, tạo log `Hidden <clinit>`.
4. Sau `afterHiddenInit`, việc gọi `ensureInitialized` lần hai không chạy static initializer lần nữa.
5. `findStatic` tạo `MethodHandle` phù hợp; `invokeExact()` gọi được phương thức của hidden class và trả `hidden-ready` dù class không thể được tra cứu lại theo tên thông thường.

`<clinit>` trong các log là chuỗi được code cố ý in ra, **không phải dòng JVM tự in**.

## 7. `Lookup.defineHiddenClass`: loading, linking và initialization trong sinh mã

Với class sinh động, framework có thể tạo `byte[]` class file rồi gọi:

```java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(classBytes, false);
Class<?> hidden = hiddenLookup.lookupClass();
```

Điều kiện quan trọng của API là lookup cần quyền thích hợp và class file phải nằm cùng runtime package với lookup class theo hợp đồng. JVM định nghĩa class mới rồi **liên kết class**, nghĩa là các yêu cầu định dạng và xác minh không tự biến mất.

Nếu truyền `true`:

```java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(classBytes, true);
```

hidden class còn được **khởi tạo ngay trước khi lời gọi trả về**. Nếu initializer có side effect, side effect sẽ xuất hiện tại đây.

Với `false`, khi cần khởi tạo rõ ràng sau đó:

```java
hiddenLookup.ensureInitialized(hidden);
```

Hãy dùng `Lookup` có quyền đối với class tương ứng; việc tạo method handle hoặc gọi thành viên cũng chịu quy tắc truy cập Java hiện hành.

**Không dùng `Class.forName(hidden.getName())` để tìm hidden class.** Tên `Class.getName()` của hidden class không phải binary name có thể dùng trong các API tìm class theo tên. Nếu cần dùng class ở bước sau, hãy lưu `Lookup`, `Class<?>`, instance hoặc method handle, không chỉ chuỗi tên.

Option `NESTMATE` trong ví dụ liên quan quyền truy cập giữa các nestmate; nó **không** thay thế cờ `initialize` và không làm bypass verifier.

## 8. Class initialization khác object construction

Khởi tạo class chỉ thực thi phần `static`; nó khác việc tạo từng object và chạy constructor.

```java
class Example {
    static {
        System.out.println("class init");
    }

    Example() {
        System.out.println("new instance");
    }
}
```

Lần đầu `new Example()`, JVM cần bảo đảm class đã initialize trước khi chạy logic tạo instance. Mỗi lần `new` có thể gọi constructor để tạo object mới, nhưng `static` initializer của cùng một class identity **không chạy lại** nếu đã thành công.

Cũng không nên nhầm resolution trong linking với việc gọi phương thức: resolution giải tham chiếu tượng trưng, không tự động thực thi body của mọi phương thức được tham chiếu.

## 9. Vì sao class đã load mà lỗi vẫn xuất hiện muộn?

Bởi JVM có quyền chọn thời điểm resolution, một class có thể nạp thành công nhưng sau đó vẫn phát sinh lỗi khi sử dụng method/field của dependency khác. Ngoài ra, initialization có thể gọi code khác, khiến việc nạp/link class phụ thuộc xảy ra gián tiếp.

| Nơi phát sinh điển hình | Lỗi có thể gặp | Hướng kiểm tra |
| --- | --- | --- |
| Loading/định nghĩa | `ClassNotFoundException` từ API theo tên; `NoClassDefFoundError` với lớp phụ thuộc | Class loader, module path, classpath, tên class |
| Định dạng class file | `ClassFormatError`, `UnsupportedClassVersionError` | File magic, major/minor, compiler và phiên bản JVM |
| Verification | `VerifyError` | Bytecode, kiểu trả về, stack/stack-map, công cụ sinh class |
| Resolution/linking | `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` | Dependency runtime, binary compatibility, quyền truy cập |
| Initialization | `ExceptionInInitializerError` khi initializer ném exception phù hợp | Code trong `static`, thứ tự field init, dependency gọi khi init |

Nếu một class đã **khởi tạo thất bại**, những lần sử dụng tiếp theo có thể thấy `NoClassDefFoundError` báo không thể khởi tạo class. Không phải mọi `NoClassDefFoundError` đều do file `.class` mất khỏi classpath.

Đặc biệt trong code generation:

- `defineHiddenClass(bytes, false)` vẫn có thể thất bại ở bước kiểm tra/định nghĩa/linking dù chưa chạy static initializer.
- `defineHiddenClass(bytes, true)` ngoài các lỗi đó còn có thể thất bại do code trong bộ khởi tạo tĩnh.
- Không sửa lỗi verifier bằng cách “tắt kiểm chứng”; hãy sửa bytecode sinh ra và đảm bảo class file khớp runtime.

## 10. Sai lầm thường gặp

1. **“`ClassLoader.loadClass` đã gọi `static {}`.”** Sai: `loadClass(String)` không tự yêu cầu khởi tạo class.
2. **“`Class.forName(name)` và `Class.forName(name, false, loader)` có cùng side effect.”** Sai: overload một tham số yêu cầu khởi tạo; overload `false` không.
3. **“Chỉ cần có `SomeClass.class` thì class đã init.”** Sai: class literal không tự khởi tạo.
4. **“Preparation thực thi `static int x = f()`.”** Sai: phép gọi `f()` thuộc initialization.
5. **“Linking luôn phải giải xong mọi tham chiếu trước khi init.”** Sai: resolution có thể lazy.
6. **“`static final int LIMIT = 7` bắt buộc kích hoạt `<clinit>` khi đọc.”** Sai với compile-time constant được nhúng.
7. **“`defineHiddenClass(bytes, false)` không verify hoặc không link.”** Sai: hidden class vẫn được liên kết, dù chưa yêu cầu init.
8. **“Hidden class không có class loader thì không thể init.”** Sai: hidden class vẫn có defining loader và có thể initialize; không thể *tìm lại theo tên* là chuyện khác.
9. **“Mỗi lần gọi static method là chạy `<clinit>` lại.”** Sai: một class được khởi tạo thành công một lần cho mỗi class identity.
10. **“Lỗi `NoClassDefFoundError` luôn chứng minh thiếu file.”** Sai: lỗi khởi tạo trước đó hoặc liên kết phụ thuộc cũng có thể dẫn đến lỗi này.

## 11. Khi áp dụng vào dự án thực tế

Nếu công cụ sinh mã cần **định nghĩa class nhưng chưa chạy static setup**, cân nhắc `defineHiddenClass(..., false)`; chuẩn bị dữ liệu class file hợp lệ và giữ tham chiếu `Lookup` để có thể sử dụng sau.

Nếu cần **đảm bảo static setup hoàn tất trước khi chạy một thao tác**, hãy yêu cầu khởi tạo bằng API đúng:

```java
Class.forName(className, true, loader);   // named class
hiddenLookup.ensureInitialized(hidden);  // hidden class, có lookup thích hợp
```

Khi kiểm thử thời điểm khởi tạo, nên chọn class chưa từng sử dụng trong lần chạy JVM đó, ghi log trong `static` initializer và đo hành vi theo **thứ tự log**; không suy luận toàn bộ hoạt động resolution chỉ từ việc class đã xuất hiện trong `ClassLoader`. Nếu test cần tái hiện một lần khởi tạo hoàn toàn mới, dùng class identity mới hoặc môi trường test cô lập thay vì hy vọng một class đã initialize sẽ tự reset.

Checklist cuối:

- Đang cần nạp class, liên kết bytecode hay thực thi bộ khởi tạo?
- Đã kiểm soát `initialize` trong `Class.forName` hoặc `defineHiddenClass` chưa?
- Bytecode generated có hợp lệ về format, version và verifier?
- Có trường `static final` compile-time constant nào gây nhầm về thời điểm init?
- Có giữ `Class<?>`/`Lookup` cho hidden class không?
- Có hiểu rằng resolution có thể xảy ra muộn và errors có thể xuất hiện ở điểm sử dụng dependency?

**Ghi nhớ:** Loading tạo biểu diễn runtime; linking xác minh, chuẩn bị và có thể phân giải muộn; initialization mới chạy static initializer. Trong Java 15+, hidden class được `defineHiddenClass` **định nghĩa và liên kết ngay cả với `initialize=false`**.

## Tài liệu chuẩn còn áp dụng

- [JLS Java SE 26 — Chương 12: Execution](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html): §12.2 loading, §12.3 linking và §12.4 initialization.
- [JVMS Java SE 26 — Chương 5](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-5.html): ngữ nghĩa JVM của loading, linking, initialization và lỗi.
- [Oracle Java SE 26 — MethodHandles.Lookup.defineHiddenClass](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)): liên kết hidden class và cờ `initialize`.
- [Oracle Java SE 26 — Class.forName](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): yêu cầu nạp và khởi tạo theo tham số.
- [Oracle Java SE 26 — ClassLoader.loadClass](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String)): tra cứu/nạp class theo tên.

Các cơ chế này tiếp tục là API và ngữ nghĩa chính thức của Java hiện đại; ví dụ tương thích Java 17+ và không dựa vào tính năng legacy hay preview đã hết hiệu lực.