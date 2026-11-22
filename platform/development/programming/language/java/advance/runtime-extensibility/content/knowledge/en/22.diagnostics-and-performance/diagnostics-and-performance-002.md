# Phân biệt ClassNotFoundException, NoClassDefFoundError và lỗi khởi tạo lớp

Khi ứng dụng Java tải plugin, khám phá provider qua `ServiceLoader`, gọi reflection hoặc tạo `ModuleLayer` mới, ba tình huống sau thường bị gộp chung thành “thiếu class”:

- **`ClassNotFoundException`:** code chủ động yêu cầu tìm/nạp một lớp theo tên, nhưng loader không tìm được định nghĩa phù hợp. Đây là **checked exception** của thao tác lookup; một lỗi phổ biến ở `Class.forName(...)` và `ClassLoader.loadClass(...)`.
- **`NoClassDefFoundError`:** JVM cần định nghĩa một class khi tải, liên kết hoặc thực thi, nhưng định nghĩa đó **không khả dụng** (ví dụ dependency có khi compile nhưng biến mất lúc chạy). Đây là **`LinkageError`**, không phải một `Exception`. Nó còn có thể xuất hiện **sau khi quá trình khởi tạo class đã thất bại**, dù file `.class` vẫn còn nguyên.
- **Lỗi khởi tạo lớp:** initializer của class thất bại khi JVM chạy phần khởi tạo static (`<clinit>`). Nếu nguyên nhân không phải `Error`, lần đầu thường thấy **`ExceptionInInitializerError`** bọc nguyên nhân; các lần sử dụng tiếp theo trong cùng loader thường thấy **`NoClassDefFoundError: Could not initialize class ...`**.

**Điểm quyết định:** phải tách **lookup, loading/linking và initialization**, xem *toàn bộ cause chain* và nhận diện **class loader/module layer thực tế**. Không phải cứ thấy `NoClassDefFoundError` là phải thêm JAR; nếu lớp đã khởi tạo lỗi, thêm JAR không sửa được trạng thái erroneous của lớp đó trong loader hiện tại.

Bài viết này đi từ cơ chế theo Java SE 17 đến một ví dụ có thể chạy và tái hiện chính xác cả ba nhánh, rồi xây quy trình chẩn đoán cho hệ thống plugin và runtime extensibility.

## 1. Bức tranh vòng đời một lớp trong JVM

Cần phân biệt các bước theo Java Language Specification (JLS):

```text
Code yêu cầu một kiểu Java
        |
        v
Loading: tìm/đọc bytes và tạo đối tượng Class
        |
        v
Linking
   - Verification: kiểm tra bytecode
   - Preparation: tạo static fields và giá trị mặc định
   - Resolution: liên kết symbolic references khi cần
        |
        v
Initialization
   - thực thi static field initializers và static blocks
   - thực thi khởi tạo superclass/superinterfaces liên quan theo JLS
        |
        v
Sử dụng class / gọi method / tạo instance
```

Các bước này **không phải lúc nào cũng diễn ra đồng loạt theo một timeline đơn giản**: JVM có thể *lazy resolve* một số symbolic reference khi lần đầu cần, còn initialization chỉ kích hoạt ở những “active uses” nhất định. Vì thế stack trace có thể trỏ tới **dòng đang gọi method của plugin**, trong khi nguyên nhân là một dependency được resolve muộn hoặc một static initializer chạy vào đúng thời điểm đó.

### Các cột mốc đáng nhớ

**Loading** là việc tìm representation của class và tạo runtime class tương ứng, thông qua bootstrap loader hoặc class loader do ứng dụng dùng. Các loader không có nghĩa vụ thấy cùng classpath. Tên lớp cộng với **defining class loader** quyết định class identity.

**Linking** gồm verification, preparation và resolution. Việc resolution tìm một kiểu/method/field được nhắc tới trong bytecode có thể bị hoãn. Các lỗi như `NoClassDefFoundError`, `NoSuchMethodError`, `NoSuchFieldError`, `VerifyError` hoặc `UnsupportedClassVersionError` thuộc nhóm sự cố liên kết/định nghĩa nhưng **khác nguyên nhân** và không nên sửa bằng một cách giống nhau.

**Initialization** là thực thi các initializer static. Nó có thể tạo object, đọc cấu hình, tìm dịch vụ hoặc gọi hệ thống bên ngoài. Nếu logic trong đó ném lỗi, class có thể bị đánh dấu **erroneous** trong loader đã định nghĩa nó.

Tách ba giai đoạn giúp trả lời đúng: “JVM chưa tìm ra class, đang cố resolve một dependency, hay đã thấy class nhưng code khởi tạo bị lỗi?”

## 2. So sánh ba loại lỗi cốt lõi

| Tiêu chí | `ClassNotFoundException` | `NoClassDefFoundError` | `ExceptionInInitializerError` |
| --- | --- | --- | --- |
| Nhóm kiểu | `ReflectiveOperationException` → `Exception` (checked) | `LinkageError` → `Error` (unchecked) | `LinkageError` → `Error` (unchecked) |
| Tình huống tiêu biểu | Yêu cầu lớp bằng tên, loader không thấy | Bytecode cần dependency đã thiếu tại runtime; hoặc class đã init thất bại | Lần đầu chạy static initializer ném một throwable **không phải `Error`** |
| Vị trí thường gặp | `Class.forName`, `ClassLoader.loadClass` | Resolve class trong code đã compile; active use class erroneous | `static { ... }` hoặc static field initialization |
| `catch (Exception)` bắt được? | Có | Không | Không |
| Chỉ thêm JAR là luôn đủ? | Không: còn loader scope/module/version | Không: có thể là erroneous class hoặc mismatch khác | Không: phải sửa nguyên nhân bên trong initializer |
| Cách đọc nguyên nhân | Requested binary name, loader lookup path | Missing binary name hoặc message `Could not initialize class`, cause chain | `getCause()` hoặc `getException()`, lỗi gốc ở initializer |
| Khả năng thử lại | Có thể đổi loader/cấu hình, tùy lookup | Phụ thuộc loại lỗi, trạng thái class/loader | Lớp đã erroneous không được khởi tạo lại trong cùng defining loader |

**Đừng coi đây là ba exception ngang hàng.** Hai loại cuối là subclass của `Error`, không thuộc `Exception`; code chỉ `catch (Exception e)` có thể bỏ lọt chúng. Trong ứng dụng production, giải pháp là **sửa deploy/loader/initializer**, không phải bọc `try/catch(Throwable)` quanh mọi request rồi tiếp tục dùng một class đã lỗi.

### Quan hệ với lỗi khác

- `ClassCastException`: hai object/type không cast được, thường do hai loader định nghĩa cùng tên API class khác nhau; không phải “không tìm thấy”.
- `NoSuchMethodException`: reflection lookup không tìm được method theo signature; khác với `NoSuchMethodError` do binary incompatibility ở runtime.
- `NoSuchFieldError` và `NoSuchMethodError`: bytecode đã compile nhưng linked binary/API khác version; thường do classpath/dependency conflict.
- `UnsupportedClassVersionError`: class file do Java version mới hơn hoặc định dạng không được runtime hỗ trợ; không phải thiếu class.
- `VerifyError`: bytecode không vượt qua verification.
- `ServiceConfigurationError`: phát sinh khi SPI provider cấu hình sai hoặc load/instantiate lỗi; **có thể bọc hoặc xuất phát từ** các lỗi loading/linking/init bên dưới.

Nếu stack trace có một exception bên ngoài từ framework, phải **đi tới root cause** thay vì dừng ở tên wrapper.

## 3. ClassNotFoundException: lookup theo tên không thành công

`ClassNotFoundException` thường xảy ra khi một API được yêu cầu **tìm class bằng chuỗi binary name**, nhưng class loader không tìm thấy định nghĩa:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("com.acme.plugin.Handler");
```

Đây là **snippet**, cần context loader không null và class tương ứng có sẵn. `loadClass` có thể ném `ClassNotFoundException`. Nó thông thường **không khởi tạo class**; nếu cần khởi tạo bằng reflection, hãy xem `Class.forName` ở phần 6.

Ví dụ:

```java
Class.forName("com.acme.plugin.MissingHandler");
```

API `Class.forName(String)` ném `ClassNotFoundException` nếu không tìm thấy binary name được yêu cầu bằng loader của caller phù hợp. Khi truyền tham số rõ ràng:

```java
Class.forName("com.acme.plugin.Handler", true, pluginLoader);
```

`pluginLoader` phải tồn tại; `initialize=true` còn yêu cầu initialization sau lookup. Vì vậy lời gọi này **có thể ném cả lỗi linking/initialization**, không chỉ `ClassNotFoundException`.

### Nguyên nhân phổ biến

1. **Sai tên:** dùng đường dẫn `com/acme/Handler.class` hoặc tên package cũ thay cho binary name `com.acme.Handler`.
2. **Không đóng gói class:** file `.class` không vào JAR, artifact deployment thiếu hoặc khác build profile.
3. **Đúng JAR nhưng sai loader:** system loader, thread context class loader (TCCL), loader plugin hoặc loader của một `ModuleLayer` không có cùng khả năng nhìn thấy.
4. **Modularity:** named module chưa được resolve/define trong layer đang tra, loader/module path không đúng hoặc layer không chứa implementation.
5. **Dynamic plugin:** candidate loader chưa được tạo hoặc đã đóng; registry cố tìm class từ generation khác.
6. **Shading/relocation:** build đã đổi package name nhưng metadata reflection/SPI vẫn chứa tên cũ.

**Không chỉ nhìn classpath in ra ở shell.** Trong hệ thống plugin, classpath ứng dụng có thể đúng nhưng `pluginLoader`/TCCL vẫn không tìm thấy class. Hãy log **requested binary name + loại/identity của loader + artifact/module version dự kiến**.

### Checked exception, không đồng nghĩa thiếu dependency tĩnh

`ClassNotFoundException` hợp lý khi code **chủ động yêu cầu** một tên mà compiler có thể chưa biết. Một class được compile sẵn tham chiếu trực tiếp `Helper`, rồi lúc chạy JVM không resolve được `Helper`, thường dẫn tới `NoClassDefFoundError` ở điểm tham chiếu — dù lỗi nền tảng vẫn là “class bị thiếu”.

Do đó, hai lỗi có thể cùng bắt nguồn từ việc JAR vắng mặt, nhưng **đường đi của lỗi** khác nhau.

## 4. NoClassDefFoundError: thiếu định nghĩa khi JVM đang cần

`NoClassDefFoundError` không có nghĩa “có class nhưng compiler không thấy”. Trong tình huống điển hình, **compile thành công**, nhưng dependency dùng bởi bytecode không có ở runtime.

Ví dụ:

```java
package demo.dependent;

public final class Broken {
    public static final String VALUE = Helper.message();
}
```

`Broken.java` compile thành công khi `Helper.class` tồn tại. Nếu build hoặc deploy chỉ chứa `Broken.class` mà thiếu `Helper.class`, truy cập `Broken.VALUE` hoặc khởi tạo `Broken` sẽ khiến JVM cần `Helper` và thất bại với `NoClassDefFoundError`.

### Đọc message

Ví dụ từ Java 17:

```text
java.lang.NoClassDefFoundError: demo/dependent/Helper
```

Tên trong message có thể dùng **dấu `/` nội bộ JVM** thay vì `.` trong binary name. Kiểm tra JAR/runtime environment xem `demo/dependent/Helper.class` thực sự có ở nguồn loader sử dụng không.

Với lỗi thiếu dependency, cause chain thường có thể cho biết loader đã thử và ném `ClassNotFoundException`. Điều này **không biến outer error thành checked exception**. Hãy báo cáo cả outer `NoClassDefFoundError` lẫn nguyên nhân sâu nhất.

### Vì sao thiếu file ở runtime dù compile thành công?

- Dependency có scope `provided`/`compileOnly` nhưng không được cung cấp ở runtime.
- Fat JAR/shading bỏ quên class, package bị relocate không đồng bộ, hoặc duplicate versions ghi đè.
- Container/application server nạp dependency ở parent loader khác; plugin loader không thấy hoặc class identity không khớp.
- Optional dependency thực ra đã được gọi vào một code path; chỉ khi chạy đường hiếm mới resolve class ấy.
- Build có class trên compile classpath nhưng runtime classpath/module path khác.
- Loader/layer của thế hệ plugin cũ đã bị thu hồi hoặc ứng dụng tiếp tục dùng một object/class không thuộc generation mới.

**Lưu ý:** không phải mọi `NoClassDefFoundError` là do file vật lý thiếu. Nó còn chỉ ra tình trạng “class không còn khởi tạo được” sau một initialization failure; phân biệt bằng message/stack trace và lần lỗi đầu tiên.

## 5. Lỗi khởi tạo lớp: ExceptionInInitializerError và class erroneous

Java chạy **class initialization** khi xảy ra các active uses theo JLS: tạo instance bằng `new`, gọi static method, truy cập/ghi static field không thuộc trường hợp compile-time constant, hoặc yêu cầu initialization bằng `Class.forName(..., true, loader)`. Việc đọc `static final int X = 1` như một constant variable có thể được inline và **không** gây initialization của class chứa nó.

Ví dụ:

```java
package demo.init;

public final class Failing {
    static {
        setup();
    }

    private static void setup() {
        throw new IllegalStateException("bad config");
    }
}
```

Class này **có mặt**, bytecode hợp lệ, nhưng `setup()` ném `IllegalStateException` khi chạy `<clinit>`.

### Lần đầu: ExceptionInInitializerError

Khi initializer kết thúc đột ngột vì một throwable **không phải `Error`**, JVM bọc nó vào `ExceptionInInitializerError`. Với ví dụ trên:

```text
java.lang.ExceptionInInitializerError
Caused by: java.lang.IllegalStateException: bad config
```

**Chẩn đoán đúng là dòng `IllegalStateException: bad config` và cách code/config được nạp trong `setup()`**, không phải tìm một JAR tên “ExceptionInInitializerError”.

Nếu initializer **ném một `Error`**, JVM có thể ném chính `Error` ấy trực tiếp thay vì bọc `ExceptionInInitializerError`. Vì thế **không** khẳng định mọi lỗi static initializer đều bắt đầu bằng `ExceptionInInitializerError`. Dù theo nhánh nào, việc initialization của class thất bại vẫn có thể khiến class bị đánh dấu erroneous.

### Lần tiếp theo: NoClassDefFoundError dù class file vẫn tồn tại

Trong cùng defining class loader, JVM không chỉ chạy lại initializer của class đã đánh dấu lỗi. Thay vào đó lần active use tiếp theo có thể ném:

```text
java.lang.NoClassDefFoundError: Could not initialize class demo.init.Failing
```

Đây là lỗi **trạng thái initialization**, không phải bằng chứng `Failing.class` biến mất. Nếu chỉ xem log của request thứ hai mà bỏ qua request thứ nhất, đội vận hành rất dễ “thêm lại JAR” nhưng không sửa được gì.

Một quy trình xác minh tốt:

1. Tìm **stack trace đầu tiên** xuất hiện trước thông báo `Could not initialize class`.
2. Xem cause của `ExceptionInInitializerError` hoặc direct `Error` để tìm lỗi gốc.
3. Kiểm tra static field initializers, static blocks, initialization của superclass/superinterfaces theo JLS, configuration, environment và dependency phát sinh trong `<clinit>`.
4. Sửa code/config; tạo **new class loader / layer** thích hợp hoặc khởi động process lại khi cần. Đừng kỳ vọng thay file config/JAR trên đĩa khiến class erroneous tự chuyển thành initialized.

### Class loading không luôn kích hoạt initialization

Hai API có khác biệt quan trọng:

```java
Class<?> loaded = Class.forName(
        "demo.init.Failing", false,
        Thread.currentThread().getContextClassLoader());
// initialize=false: không chủ động chạy static initializer.
```

`ClassLoader.loadClass(name)` thông thường tải class **mà không initialize** nó. Ngược lại, `Class.forName(name)` (overload một tham số) yêu cầu initialization. Bởi vậy test “`loadClass` chạy được” **không đủ** để kết luận plugin đã sẵn sàng; readiness check cần kiểm tra hợp đồng chạy thật và quản lý side effects.

## 6. Ví dụ Java 17 đầy đủ: tái hiện 3 lỗi và lần dùng sau của class hỏng

Ví dụ xây ba nhóm source trong một project nhỏ:

- `demo.missing.Ghost` **không được tạo**, để lookup bằng tên gây `ClassNotFoundException`.
- `demo.dependent.Broken` compile với `Helper`, nhưng ta chủ động xóa **chỉ bytecode `Helper.class` trong thư mục build thử nghiệm** trước khi chạy, để tái hiện `NoClassDefFoundError` do runtime dependency thiếu.
- `demo.init.Failing` có static initializer cố tình ném exception; `Class.forName(..., false, loader)` chỉ load, còn `true` làm initializer chạy và thất bại.

**Cảnh báo:** chỉ xóa file build `out/demo/dependent/Helper.class` trong thư mục demo riêng; không xóa file nguồn hoặc file trong dự án thật.

### 6.1. Cấu trúc source

```text
class-error-demo/
├── ErrorTaxonomyDemo.java
└── demo/
    ├── dependent/
    │   ├── Helper.java
    │   └── Broken.java
    └── init/
        └── Failing.java

out/ (do javac sinh ra, riêng cho demo)
```

### 6.2. Code của từng file

**`demo/dependent/Helper.java`**

```java
package demo.dependent;

public final class Helper {
    public static String message() {
        return "ready";
    }
}
```

**`demo/dependent/Broken.java`**

```java
package demo.dependent;

public final class Broken {
    public static final String VALUE = Helper.message();
}
```

`VALUE` không phải compile-time constant vì giá trị lấy từ lời gọi method. Khi initialize `Broken`, JVM phải resolve/call `Helper.message()`; nếu `Helper.class` không còn, lỗi xuất hiện lúc runtime.

**`demo/init/Failing.java`**

```java
package demo.init;

public final class Failing {
    static {
        setup();
    }

    private static void setup() {
        throw new IllegalStateException("bad config");
    }
}
```

`setup()` luôn ném exception từ static initialization. Việc gọi một method riêng cũng tránh quy tắc của compiler rằng một static initializer không được **hoàn thành đột ngột ở mọi đường đi mà compiler nhận biết trực tiếp**.

**`ErrorTaxonomyDemo.java`**

```java
public final class ErrorTaxonomyDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader loader = ErrorTaxonomyDemo.class.getClassLoader();

        try {
            Class.forName("demo.missing.Ghost", true, loader);
        } catch (ClassNotFoundException ex) {
            System.out.println("lookup=" + ex.getClass().getSimpleName());
        }

        try {
            Class.forName("demo.dependent.Broken", true, loader);
        } catch (NoClassDefFoundError ex) {
            System.out.println("missingDependency=" + ex.getClass().getSimpleName());
            System.out.println("missingName=" + ex.getMessage());
        }

        Class<?> notInitialized =
                Class.forName("demo.init.Failing", false, loader);
        System.out.println("loadedOnly=" + notInitialized.getSimpleName());

        try {
            Class.forName("demo.init.Failing", true, loader);
        } catch (ExceptionInInitializerError ex) {
            Throwable cause = ex.getCause();
            System.out.println("firstInit=" + ex.getClass().getSimpleName());
            System.out.println("rootCause=" + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage());
        }

        try {
            Class.forName("demo.init.Failing", true, loader);
        } catch (NoClassDefFoundError ex) {
            System.out.println("retryInit=" + ex.getClass().getSimpleName());
        }
    }
}
```

Các `catch` riêng ở đây nhằm **phân loại kết quả có chủ đích trong một chương trình minh họa**; đó không phải policy “bắt mọi `Error` và tiếp tục chạy” cho production. Ở production cần log theo boundary thích hợp và sửa lỗi gốc.

### 6.3. Biên dịch và tạo lỗi deployment có kiểm soát

Chạy bằng **JDK 17 trở lên** trong thư mục `class-error-demo`:

```bash
mkdir -p out
javac --release 17 -d out \
  ErrorTaxonomyDemo.java \
  demo/dependent/Helper.java \
  demo/dependent/Broken.java \
  demo/init/Failing.java

# Chỉ xóa dependency trong build output của demo:
rm out/demo/dependent/Helper.class

java -cp out ErrorTaxonomyDemo
```

Nếu dùng Windows PowerShell, có thể chạy từng lệnh tương ứng:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out ErrorTaxonomyDemo.java demo/dependent/Helper.java demo/dependent/Broken.java demo/init/Failing.java
Remove-Item -LiteralPath "out/demo/dependent/Helper.class" -Force
java -cp out ErrorTaxonomyDemo
```

**Stdout đã kiểm chứng với `javac --release 17` và `java` trên Java 17:**

```text
lookup=ClassNotFoundException
missingDependency=NoClassDefFoundError
missingName=demo/dependent/Helper
loadedOnly=Failing
firstInit=ExceptionInInitializerError
rootCause=IllegalStateException:bad config
retryInit=NoClassDefFoundError
```

### 6.4. Diễn giải từng dòng

1. **`lookup=ClassNotFoundException`:** `Class.forName` chủ động yêu cầu `demo.missing.Ghost` nhưng chưa hề có class definition tương ứng.
2. **`missingDependency=NoClassDefFoundError`:** `Broken.class` vẫn tồn tại; khi initialize, JVM cần `Helper.class`, nhưng file đó đã bị xóa khỏi runtime output.
3. **`missingName=demo/dependent/Helper`:** tên dependency bị thiếu, **không phải `Broken`**, được thấy trong message ở môi trường thử nghiệm.
4. **`loadedOnly=Failing`:** `Class.forName(..., false, loader)` thu được `Class<?>` mà chưa chạy static initializer; tên class được hiển thị bình thường.
5. **`firstInit=ExceptionInInitializerError`:** initializer mới chạy khi `initialize=true` và ném `IllegalStateException`.
6. **`rootCause=IllegalStateException:bad config`:** cần sửa config/logic trong `setup()`, không phải thêm JAR cho `Failing`.
7. **`retryInit=NoClassDefFoundError`:** class `Failing` vẫn có file, nhưng trạng thái initialization đã failed trong cùng defining loader.

Nếu sau khi biên dịch bỏ qua lệnh xóa `Helper.class`, nhánh missing dependency **không** xảy ra và output của demo khác. Điều đó cho thấy đây là lỗi runtime packaging/visibility, không phải lỗi compile.

## 7. Cách tìm root cause trong stack trace

Một stack trace có thể nhiều lớp lỗi:

```text
java.lang.NoClassDefFoundError: demo/dependent/Helper
    at demo.dependent.Broken.<clinit>(Broken.java:4)
    ...
Caused by: java.lang.ClassNotFoundException: demo.dependent.Helper
    at ...ClassLoader...
```

Đây là **hình minh họa** theo mẫu thường gặp, không phải stdout cố định của `ErrorTaxonomyDemo`. Đọc như sau:

- **Outer error**: JVM không resolve được một class mà bytecode cần.
- **`Broken.<clinit>`**: lỗi xuất hiện trong code khởi tạo static của `Broken` (dòng này không nói Helper đã khởi tạo lỗi; đây là đường call gây yêu cầu resolution).
- **Cause `ClassNotFoundException`**: một lookup do loader thực hiện đã thất bại. Vẫn phải điều tra *loader nào* thực hiện lookup và phạm vi nó nhìn thấy.

Đối với class initialization:

```text
java.lang.ExceptionInInitializerError
    at ...
Caused by: java.lang.IllegalStateException: bad config
    at demo.init.Failing.setup(Failing.java:...)
    at demo.init.Failing.<clinit>(Failing.java:...)
```

Nếu chỉ ghi outer `ExceptionInInitializerError` mà không giữ nguyên cause, bạn sẽ mất lỗi config thực sự. Sau vài request, log chỉ còn `NoClassDefFoundError: Could not initialize class demo.init.Failing`; cần tìm **lần thất bại đầu tiên**.

### Checklist đọc lỗi theo thứ tự

1. **Tên ngoại lệ ngoài cùng:** `ClassNotFoundException`, `NoClassDefFoundError`, `ExceptionInInitializerError` hay wrapper từ framework?
2. **Message có gì?** `com/foo/Bar` gợi ý dependency không có; `Could not initialize class` gợi ý class erroneous.
3. **Root cause là gì?** `ClassNotFoundException` ở loader, `IllegalStateException` từ config, `NullPointerException` trong initializer, hay lỗi incompatibility?
4. **Điểm đầu tiên trong mã của mình:** `<clinit>`, `Class.forName`, `ServiceLoader`, API plugin registry hay code nghiệp vụ?
5. **Class loader / module layer nào?** Đối chiếu identity, parent delegation, TCCL, tên module và phiên bản artifact.
6. **Lần lỗi đầu tiên diễn ra khi nào?** Lỗi hiện tại có thể chỉ là hệ quả của initialization thất bại từ trước.
7. **Có tái hiện trên đúng artifact sản xuất không?** IDE và unit-test classpath có thể khác bản deploy thật.

Đừng bắt `Throwable` để “che” những lỗi này trong toàn ứng dụng. Ở boundary khởi tạo plugin, có thể cô lập candidate lỗi, ghi đầy đủ stack trace và giữ active generation đang tốt. Nếu lỗi đã xảy ra trên một class của generation đang hoạt động, phải đánh giá tình trạng instance/module loader và áp dụng chính sách restart/replace hợp lệ.

## 8. Vấn đề class loader: đúng JAR vẫn có thể sai phạm vi nhìn thấy

Trong Java plugin architecture, có nhiều đường tra cứu:

```java
ClassLoader defining = PluginEntry.class.getClassLoader();
ClassLoader context = Thread.currentThread().getContextClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
```

Đây là **snippet**, `PluginEntry` cần tồn tại và được load. Ba biến không bắt buộc cùng một loader. `context` thậm chí có thể `null`, và trong hệ thống nhiều thread TCCL có thể khác nhau theo request.

### Class identity theo tên + defining loader

`com.acme.api.Plugin` do loader P định nghĩa **không phải** cùng runtime type với `com.acme.api.Plugin` do loader C định nghĩa. Khi host kỳ vọng API type từ P nhưng plugin nạp bản riêng từ C, có thể xuất hiện `ClassCastException` hoặc `LinkageError` khác, dù class files đều tồn tại. Cách giải quyết thông thường:

- Host/shared parent loader **sở hữu service interface và contract API**.
- Child plugin loader chỉ sở hữu implementation và dependencies cần cách ly.
- Candidate generation mới dùng loader/layer riêng khi cần class definition mới.
- Registry theo dõi generation, tránh truyền Class/instance V1 sang V2 như thể chúng có cùng identity.

Đừng “giải” mọi lỗi bằng cách đưa toàn bộ JAR vào system classpath. Cách này có thể che vấn đề classloader và tăng nguy cơ xung đột version.

### Parent delegation và TCCL

Class loader mặc định thường **parent-first** khi tìm class. Điều này có thể khiến plugin mong đợi API/dependency V2 nhưng thực tế nhận V1 từ parent. TCCL được framework sử dụng trong một số lookup, nhất là discovery/ServiceLoader; nếu context không đúng, provider có thể không được tìm ra.

Cần so sánh:

- `getClass().getClassLoader()` đối với object/class liên quan;
- `Thread.currentThread().getContextClassLoader()` tại điểm discovery;
- loader được truyền tường minh cho `Class.forName(name, true, loader)`;
- `ModuleLayer.findLoader(moduleName)` nếu dùng JPMS;
- loader parent chain và danh sách JAR/module mà loader có thể tìm.

**Không mặc định system loader có tất cả dependencies** trong app server hoặc modular runtime. Nếu `ClassLoader.getSystemClassLoader()` không thấy một class thì chưa kết luận plugin loader cũng không thấy.

## 9. Liên hệ JPMS, ModuleLayer và ServiceLoader

**Named module phải được resolve/defined và đúng dependency graph.** JAR nằm trong một thư mục không đủ để nó trở thành module khả dụng cho layer. Với plugin dùng `ModuleFinder`, `Configuration.resolve/resolveAndBind` và `ModuleLayer`, hãy kiểm tra:

- module chứa service API đã được resolve; consumer có `requires` phù hợp;
- provider đã được đưa vào layer nếu kỳ vọng `ServiceLoader` khám phá nó; với `uses`/`provides`, `resolveAndBind` có thể bổ sung provider modules;
- class loader được lấy từ đúng layer và module; module access/exports/opens đúng hợp đồng;
- nhà cung cấp SPI đăng ký metadata đúng và constructor/provider method hợp lệ.

`ClassNotFoundException` lúc tìm class theo string và `ServiceConfigurationError` khi load SPI provider là hai dấu hiệu khác nhau; cần xem nguyên nhân sâu nhất. `ServiceLoader` có thể báo lỗi khi provider class không tìm thấy, không assignable tới service, khởi tạo lỗi hoặc metadata không hợp lệ. Đừng biến `ServiceConfigurationError` thành “không có plugin” và tự bỏ qua.

### Tái nạp plugin không chữa được class erroneous của generation cũ

Khi static initialization đã thất bại trong loader của V1:

- `ServiceLoader.reload()` chỉ xóa cache discovery của instance ServiceLoader; nó **không reset trạng thái initialization** của `Class<?>` trong defining loader.
- Thay file JAR V1 trên đĩa không đổi class definition đã nạp.
- Nếu muốn sửa code/config bằng deployment V2, thông thường phải **dựng generation mới** với loader/layer mới rồi validate; request đang dùng V1 vẫn cần xử lý/drain theo policy.
- Giữ strong references từ V1 (thread, static caches, callback, listener, TCCL) có thể ngăn giải phóng loader cũ.

Do đó trong quy trình plugin hot replacement, readiness/health check phải **kích hoạt những code path đủ cần thiết** (với side effects có kiểm soát) để tránh publish một candidate chỉ “loadClass thành công” nhưng lỗi ở static initialization.

## 10. Các công cụ chẩn đoán khi lỗi không tái hiện trong IDE

### Kiểm tra artifact

Đối với JAR sản xuất:

```bash
jar --list --file plugin.jar
```

Tìm tên entry dạng `com/acme/plugin/Handler.class` và dependencies liên quan. Với JAR đóng gói classpath, tên entry phải tương ứng package; nếu class được shading/relocate, cần tra đúng binary name sau build. Với modular JAR, kiểm tra cả `module-info.class` và module dependencies.

Có thể kiểm tra mô tả/bytecode của class khi đã biết artifact và classpath:

```bash
javap -classpath plugin.jar com.acme.plugin.Handler
```

`javap` giúp xem public type/method signatures để nhận ra version lệch. Lệnh này là **mẫu sử dụng**, không có `plugin.jar` trong demo; thay bằng artifact thật. Với nhiều dependencies, cần cung cấp classpath/module path phù hợp để giải quyết thông tin bạn cần.

### Xem class loading thật bằng JVM logs

Với Java 17:

```bash
java -Xlog:class+load=info -cp out ErrorTaxonomyDemo
```

Đây là lệnh chạy demo đã biên dịch; log class loading có thể rất dài, nên dùng khi chẩn đoán và lọc theo tên package/loader cần tìm. Tùy JVM và cấu hình logging, output chứa nguồn class/JAR; tránh đưa vào log công khai nếu đường dẫn môi trường nhạy cảm.

`-verbose:class` cũng là tùy chọn thông dụng, nhưng unified logging `-Xlog:class+load=info` giúp tùy chỉnh ở Java 17. **Class-load log chỉ ghi sự kiện load; không tự cho bạn biết initializer nào thất bại nếu không đọc stack trace/cause.**

### Kiểm tra dependency tree/build/deployment

Các hệ thống Maven/Gradle có dependency scopes và quy tắc packaging khác nhau. Kiểm tra **effective runtime dependencies**, không chỉ compile dependencies. Nếu có nhiều bản cùng class, xác minh **bản được class loader thực sự chọn** qua log/code source phù hợp. Đối với plugin deployment, ghi rõ plugin ID, generation ID, artifact hash, loader identity, module layer và runtime Java version.

Những công cụ như `jdeps` hữu ích để tìm static bytecode dependencies, nhưng **không phát hiện đầy đủ dependency bằng reflection, resource name tạo động, ServiceLoader metadata hoặc đường code chưa thực thi**. Cần kết hợp static inspection với integration test.

## 11. Lỗi xảy ra ở bước nào thì hướng sửa khác nhau

| Triệu chứng | Câu hỏi cần hỏi | Hướng điều tra/khắc phục |
| --- | --- | --- |
| `ClassNotFoundException: com.x.Plugin` tại `Class.forName` | Tên binary đúng chưa; loader nào lookup? | Kiểm tra package, artifact, TCCL, parent/child loader, ModuleLayer |
| `NoClassDefFoundError: com/x/Helper` khi gọi `Plugin.start` | Helper có khi compile nhưng vắng mặt lúc chạy? | So sánh build output và runtime packaging, scopes, module graph |
| `NoClassDefFoundError: Could not initialize class com.x.Plugin` | Có lỗi `<clinit>` trước đó không? | Tìm first failure, root cause, sửa initializer/config, tạo loader/generation mới |
| `ExceptionInInitializerError` | Cause có `NullPointerException`/`IllegalStateException` gì? | Sửa static initialization, health checks, side effects |
| `UnsupportedClassVersionError` | Runtime JDK đủ để đọc class file version không? | Dùng target `--release` phù hợp hoặc nâng runtime |
| `NoSuchMethodError`/`NoSuchFieldError` | Runtime API/dependency có khác bản compile? | Kiểm tra binary compatibility, class shadowing, transitive conflicts |
| `ClassCastException` giữa host/plugin API | Có hai loader định nghĩa cùng API FQCN không? | Đặt shared API ở parent, chỉ implementation trong child |
| `ServiceConfigurationError` | Metadata/implementation/constructor/provider method lỗi gì? | Kiểm tra `META-INF/services` hoặc `provides`, cause và context loader |
| Lỗi chỉ sau redeploy | Loader V1/threads/caches còn sống? | Kiểm tra classloader retention, registry, lifecycle và clean cutover |
| Lỗi ngẫu nhiên khi chạy song song | Static initialization phụ thuộc state/lock hay request context? | Loại side effects khỏi `<clinit>`, đồng bộ đúng, validate từng generation |

### Những điều không nên làm

**Không xóa cache JAR một cách mù quáng.** Nếu lỗi do class initialization đã thất bại, xóa cache file không thay được runtime class state.

**Không `catch (Throwable)` rồi tiếp tục phục vụ bằng class hỏng.** Có thể ghi log hoặc cô lập candidate lỗi tại ranh giới rõ, nhưng nhiều `Error` chỉ ra sự cố không thể phục hồi an toàn trong ngữ cảnh đó.

**Không đổi class loader chỉ để che thiếu dependency.** Loader mới vẫn thất bại nếu artifact thiếu `Helper.class`. Muốn sửa phải đảm bảo deployment graph đúng.

**Không giữ mutable global state trong static initializer nếu có thể tránh.** Phần khởi tạo tĩnh phụ thuộc config/runtime I/O là nguồn lỗi khó hồi phục, nhất là với plugin được tải động.

**Không đoán lỗi qua top line một mình.** Với `ExceptionInInitializerError` và `NoClassDefFoundError` dạng erroneous, phần quan trọng có thể nằm trong log trước đó hoặc nested cause.

## 12. Thiết kế plugin để lỗi có thể cô lập và phục hồi

Một plugin manager nên tách ba lớp trách nhiệm:

```text
Artifact/Dependency validation
    |
    | check manifest, Java target, dependencies, signature
    v
Candidate loader/layer (chưa phục vụ request)
    |
    | load + link + initialize + construct + health/contract tests
    v
Validated generation
    |
    | atomic publish sau khi đạt readiness
    v
Active generation
    |
    | request-scoped lease / lifecycle
    v
Retire -> drain -> cleanup old generation
```

### Vì sao phải chạm tới initialization khi validate?

Chỉ gọi `ClassLoader.loadClass` có thể trả về một `Class<?>` hợp lệ dù static initialization sẽ thất bại khi request đầu tiên chạy. Health check nên chủ động thực thi một **hợp đồng readiness đủ đại diện**, ví dụ gọi method không gây side effects ngoài ý muốn, kiểm tra cấu hình và khởi tạo provider theo contract.

Không nên “gọi mọi method” để chắc chắn — một số method có thể gửi giao dịch, xóa dữ liệu hoặc phụ thuộc input. Readiness cần **được thiết kế riêng** và chạy ở môi trường/cấu hình phù hợp.

### Cô lập candidate thất bại

Nếu V2 có `ExceptionInInitializerError`, `NoClassDefFoundError` hoặc `ServiceConfigurationError` trong prepare/validate, có thể:

1. Ghi error/cause chain/loader identity/artifact version và cleanup các resources của candidate.
2. **Không** publish candidate V2.
3. Giữ generation V1 đã hoạt động tiếp tục phục vụ nếu còn khỏe mạnh.
4. Sửa dependency/configuration hoặc triển khai lại thành **candidate generation mới**; đừng cố chạy lại static initializer của class erroneous trong cùng loader.
5. Không recycle class loader hoặc engine context đã ở trạng thái không rõ nếu nó vừa khởi tạo một phần.

Khi bắt lỗi ở boundary plugin, phải phân biệt tình huống có thể cô lập với lỗi nghiêm trọng của JVM như `OutOfMemoryError`; không nên giả định mọi `Error` đều recover được chỉ vì có code catch.

### Cân bằng hiệu năng và chẩn đoán

Quét classpath, tạo loader/layer, load plugin và chạy static initializer có chi phí. Không nên làm lại những bước này theo từng request. Hãy **prepare/validate trước rồi publish immutable generation**, request sau đó chỉ dùng snapshot phù hợp.

Tuy nhiên cũng không nên cache lỗi “class chưa thấy” vĩnh viễn nếu loader/module graph thực sự được cập nhật theo cách có kiểm soát: chính sách cache phải gắn với **loader/generation version**. Một new generation với new loader/layer là ranh giới tự nhiên để reload những implementation đã đổi.

Class-load logging rất hữu ích khi debug nhưng có overhead và lượng log đáng kể; bật theo nhu cầu. Trong operation bình thường nên giữ metadata hạn chế: plugin ID/version, tên exception, missing binary name, loader identity và tracking ID, không ghi secrets/bytecode.

## 13. Bảng quyết định xử lý sự cố

```text
Lỗi khi plugin load/execute?
       |
       +-- ClassNotFoundException?
       |       |
       |       +-- Explicit lookup theo tên thất bại
       |             -> kiểm tra binary name + đúng loader/layer + artifact
       |
       +-- NoClassDefFoundError?
       |       |
       |       +-- Message "Could not initialize class ..."?
       |       |        -> tìm lần khởi tạo đầu tiên thất bại
       |       |        -> root cause tại <clinit> + state erroneous
       |       |
       |       +-- Thiếu "pkg/Class" hoặc "wrong name"?
       |                -> kiểm tra runtime dependency + bytecode/package/loader
       |
       +-- ExceptionInInitializerError?
       |       |
       |       +-- đọc getCause() và stack trace <clinit>
       |       +-- sửa code/config và thay generation/loader khi cần
       |
       +-- LinkageError khác?
       |       |
       |       +-- NoSuchMethodError/NoSuchFieldError/VerifyError/...
       |                -> kiểm tra binary compatibility, Java target, bytecode
       |
       +-- ServiceConfigurationError hoặc framework wrapper?
               |
               +-- mở toàn bộ cause chain và điều tra class loader/provider
```

Flow này là **hướng dẫn chẩn đoán**, không phải quy tắc tuyệt đối cho mọi JVM implementation. `NoClassDefFoundError` còn nhiều tình huống phức tạp ngoài các nhánh nêu trên; cần xem message, cause, bytecode references và quá trình runtime thực tế.

## 14. Checklist trước khi phát hành và khi điều tra incident

**Trước khi phát hành plugin:**

- [ ] JAR/module chứa đầy đủ runtime dependencies, không chỉ compile classpath.
- [ ] Dùng đúng `--release`/target Java tương thích với runtime vận hành.
- [ ] Plugin API chung nằm ở loader/module thích hợp; implementation/dependencies phiên bản riêng không va class identity.
- [ ] SPI metadata, `uses/provides` hoặc `META-INF/services` được đóng gói và kiểm thử trong runtime tương đương production.
- [ ] Static initializer không phụ thuộc vào thao tác I/O nguy hiểm, global state khó kiểm soát hoặc config chưa validate.
- [ ] Candidate được load, initialize, instantiate và health/contract test **trước** atomic cutover.
- [ ] Có nguyên tắc cleanup candidate lỗi, không tái sử dụng loader/class đã ở trạng thái erroneous.
- [ ] Có test thiếu dependency sau compile, sai loader, Java target version, static initialization fail và retry.
- [ ] Logger giữ nguyên cause chain + generation ID, nhưng không rò bí mật.

**Khi gặp sự cố:**

- [ ] Phân loại đúng checked `ClassNotFoundException`, `LinkageError` và `ExceptionInInitializerError`.
- [ ] Kiểm tra toàn bộ stack trace/cause, không chỉ top line.
- [ ] Nếu message `Could not initialize class`, tìm **lần lỗi đầu tiên** của initializer.
- [ ] Xác định binary name, package/path, class version và artifact hash thực tế.
- [ ] Ghi defining loader, TCCL, parent loader, ModuleLayer và request/generation context phù hợp.
- [ ] So sánh runtime dependency graph với build-time graph.
- [ ] Chỉ dùng `-Xlog:class+load=info`/`javap`/`jar --list` khi cần và bảo vệ thông tin môi trường.
- [ ] Ưu tiên khôi phục bằng generation đã validate hoặc process restart có kiểm soát; không ép dùng class erroneous.

### Tài liệu Java SE 17

- [`ClassNotFoundException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html)
- [`NoClassDefFoundError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html)
- [`ExceptionInInitializerError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html)
- [`Class.forName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader))
- [JLS `12.2–12.4: loading, linking, initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)
- [`ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)

**Kết luận:** `ClassNotFoundException` báo một **explicit lookup** không tìm được lớp; `NoClassDefFoundError` báo JVM không thể có một class definition cần thiết **hoặc một class đã khởi tạo lỗi không thể được sử dụng tiếp**; `ExceptionInInitializerError` đưa bạn tới **nguyên nhân trong static initialization** ở lần lỗi đầu tiên. Muốn sửa đúng và nhanh trong hệ thống plugin, luôn phân biệt *giai đoạn lỗi*, *class loader/module layer* và *root cause*, rồi xử lý deployment/initialization theo vòng đời generation — không đoán chỉ từ tên exception.