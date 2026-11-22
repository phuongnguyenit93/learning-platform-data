# Class.forName(String) và lựa chọn loader mặc định

`Class.forName(String)` là API quen thuộc khi một chương trình Java cần lấy `Class<?>` từ **tên class ở runtime**: tìm implementation từ cấu hình, đăng ký driver, khởi tạo plugin hoặc dùng reflection. Điểm dễ nhầm nhất là từ “mặc định”: overload một tham số **không tự chọn thread context class loader, không luôn dùng system loader, và cũng không định nghĩa class bằng bootstrap loader chỉ vì phương thức nằm trong `java.lang.Class`**.

Theo Java SE 17, lời gọi:

```java
Class<?> type = Class.forName("com.example.Service");
```

tương đương về ý nghĩa với:

```java
Class<?> type = Class.forName(
        "com.example.Service",
        true,
        currentLoader
);
```

trong đó **`currentLoader` là defining class loader của class đang gọi `Class.forName(String)`**. `true` yêu cầu **khởi tạo class/interface** nếu chưa khởi tạo trước đó. `currentLoader` là ký hiệu giải thích của đặc tả, không phải biến có sẵn trong Java.

Bài học thuộc nhóm **API nạp lớp** của Java core – classloader. Ta sẽ phân biệt loader mặc định với system loader và thread context loader; hiểu tên đầu vào, hành vi loading–linking–initialization, so sánh các overload; chạy chương trình thực nghiệm và xử lý các lỗi thường gặp trong plugin/module application.

## 1. `Class.forName(String)` làm gì?

Chữ ký trong Java 17:

```java
public static Class<?> forName(String className)
        throws ClassNotFoundException
```

`className` là tên dạng binary name của class hoặc interface cần tìm; với kiểu mảng, API chấp nhận tên mảng theo quy ước `Class.getName()`. Khi gọi:

1. **Chọn loader theo caller:** JVM xác định *class đang gọi trực tiếp phương thức này*, lấy **defining loader** của class đó.
2. **Tìm/nạp class:** yêu cầu loader đó tìm class đã có hoặc load class tương ứng, dùng cơ chế delegation/module mapping của loader.
3. **Liên kết khi cần:** JVM đảm bảo những điều kiện linking mà thao tác yêu cầu, gồm resolution thích hợp.
4. **Khởi tạo:** với class/interface thông thường, tham số khởi tạo hiệu dụng là `true`; nếu class chưa khởi tạo, JVM thực hiện initialization trước khi trả thành công.
5. **Trả `Class<?>`:** đó là đối tượng metadata/runtime identity của class được tìm thấy; hàm **không tạo instance** của class đích.

Nếu class đã khởi tạo thành công, lời gọi tiếp theo không chạy lại static initializer. Nếu quá trình tìm, liên kết hoặc khởi tạo thất bại, phương thức báo lỗi tương ứng.

### Ba loader cần gọi đúng tên

| Khái niệm | Cách lấy | Ý nghĩa trong `Class.forName(String)` |
| --- | --- | --- |
| **Loader của class đang gọi** | `Caller.class.getClassLoader()` | **Là lựa chọn mặc định** của overload một tham số |
| **System/application loader** | `ClassLoader.getSystemClassLoader()` | Chỉ trùng với loader mặc định khi class đang gọi thực sự do system loader định nghĩa |
| **Thread context class loader (TCCL)** | `Thread.currentThread().getContextClassLoader()` | **Không được overload một tham số tự động chọn**; muốn dùng thì truyền rõ qua overload ba tham số |
| **Bootstrap loader** | Thường biểu diễn bằng `null` trong `Class.getClassLoader()` | Có thể là loader mặc định khi caller do bootstrap định nghĩa; `null` còn có nghĩa chọn bootstrap khi truyền cho overload ba tham số |
| **Loader của class trả về** | `type.getClassLoader()` | Defining loader của **class kết quả**; có thể khác loader được dùng để bắt đầu tìm |

**Quan trọng:** “Loader được dùng để bắt đầu tìm” và “loader định nghĩa class đã tìm” khác nhau. Ví dụ system loader được yêu cầu tìm `java.lang.String` nhưng parent delegation có thể trả `Class<String>` do bootstrap định nghĩa; `String.class.getClassLoader()` thường là `null`.

## 2. Vì sao không thể mặc định hiểu là system loader?

Đối với chương trình đơn giản chạy bằng `java -cp . Main`, `Main` thường do system/application loader định nghĩa. Trong bối cảnh đó, `Class.forName("pkg.Tool")` nhìn giống `ClassLoader.getSystemClassLoader().loadClass("pkg.Tool")` vì hai lời gọi thường bắt đầu từ cùng một loader.

Sự giống nhau ấy **không phải quy tắc chung**:

- **Plugin loader:** class `PluginEntry` được loader riêng định nghĩa; khi code trong `PluginEntry` gọi `Class.forName("plugin.Helper")`, loader mặc định là loader đã định nghĩa `PluginEntry`. System loader có thể hoàn toàn không nhìn thấy `plugin.Helper`.
- **Thư viện dùng chung:** class `LibraryHelper` do parent/system loader định nghĩa; nếu chính `LibraryHelper` gọi `Class.forName(name)`, lời gọi mặc định dùng **loader của `LibraryHelper`**, ngay cả khi plugin ở loader con gọi vào method của helper.
- **Container/application server:** mỗi ứng dụng có thể có loader riêng. Hai ứng dụng gọi cùng tên `com.acme.Model` qua class caller ở hai loader khác nhau có thể nhận hai class khác nhau.
- **Module layer tự tạo:** một module có thể được gán cho loader riêng từ `ModuleLayer`; class trong module đó gọi overload một tham số theo loader đã định nghĩa class caller, không tự quay về system loader.
- **Bootstrap-defined caller:** nếu code caller thực sự ở lớp do bootstrap định nghĩa, defining loader được biểu diễn là `null`.

Vì vậy, cần hỏi **“class nào chứa câu lệnh `Class.forName(...)` và class đó do ai định nghĩa?”**, thay vì chỉ hỏi “chương trình được chạy từ đâu?”.

### Caller-sensitive: chính caller của `forName` quyết định

JDK đánh dấu một số API là *caller-sensitive*, vì hành vi của chúng phải phản ánh class đứng ở call site. Một method wrapper thường có hành vi khác so với việc plugin gọi trực tiếp:

```java
public final class LibraryHelper {
    private LibraryHelper() { }

    public static Class<?> load(String name)
            throws ClassNotFoundException {
        return Class.forName(name);
    }
}
```

Đây là **class hoàn chỉnh có thể biên dịch**, không có `main`. Khi plugin gọi `LibraryHelper.load("plugin.Widget")`, class thực hiện lời gọi `Class.forName` là **`LibraryHelper`**. Nếu `LibraryHelper` được định nghĩa bởi parent loader không thấy `plugin.Widget`, lời gọi có thể phát `ClassNotFoundException` dù plugin loader tìm được class.

Không có quy tắc “tự đi ngược call stack đến application/plugin gốc để mượn loader của họ”. Nếu helper muốn tải class theo miền của plugin, thiết kế API nên nhận `ClassLoader` hoặc `ModuleLayer`/`Module` một cách tường minh.

## 3. Ví dụ Java 17+: thay TCCL mà overload một tham số vẫn dùng caller loader

Tạo một file **`ForNameDemo.java`**:

```java
public class ForNameDemo {
    static class Target {
        static {
            System.out.println("Target initialized");
        }
    }

    static class Deferred {
        static {
            System.out.println("Deferred initialized");
        }
    }

    static class ArrayElement {
        static {
            System.out.println("ArrayElement initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader callerLoader = ForNameDemo.class.getClassLoader();
        ClassLoader isolated = new ClassLoader(null) { };

        Thread thread = Thread.currentThread();
        ClassLoader previous = thread.getContextClassLoader();

        thread.setContextClassLoader(isolated);
        try {
            System.out.println("caller loader is context: "
                    + (callerLoader == thread.getContextClassLoader()));

            System.out.println("one arg");
            Class<?> target = Class.forName("ForNameDemo$Target");
            System.out.println("found target: " + (target == Target.class));

            try {
                Class.forName("ForNameDemo$Target", false, isolated);
                System.out.println("unexpected");
            } catch (ClassNotFoundException expected) {
                System.out.println("explicit context: not found");
            }

            Class<?> deferred = Class.forName(
                    "ForNameDemo$Deferred", false, callerLoader);
            System.out.println("deferred loaded: "
                    + (deferred == Deferred.class));

            System.out.println("initialize deferred");
            Class.forName("ForNameDemo$Deferred", true, callerLoader);

            Class<?> array = Class.forName(
                    "[LForNameDemo$ArrayElement;");
            System.out.println("array found: " + array.isArray());

            System.out.println("initialize component");
            Class.forName("ForNameDemo$ArrayElement");
        } finally {
            thread.setContextClassLoader(previous);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 ForNameDemo.java
java -cp . ForNameDemo
```

Stdout dự kiến trên Java SE thông thường, chạy bằng application class path:

```text
caller loader is context: false
one arg
Target initialized
found target: true
explicit context: not found
deferred loaded: true
initialize deferred
Deferred initialized
array found: true
initialize component
ArrayElement initialized
```

### Tại sao các dòng xuất hiện đúng thứ tự?

1. `ForNameDemo` do application loader định nghĩa khi chạy `java -cp .`. `isolated` là custom loader có parent `null` (delegate tới bootstrap), không có bytecode `ForNameDemo$Target`.
2. Sau khi gán `isolated` làm TCCL, `callerLoader == thread.getContextClassLoader()` trả `false`.
3. `Class.forName("ForNameDemo$Target")` chạy **ngay trong `ForNameDemo.main`**, do đó dùng loader của `ForNameDemo`, không dùng TCCL. Class được tìm thấy và initializer in `Target initialized` trước khi API trả về.
4. `Class.forName(name, false, isolated)` dùng đúng custom loader được truyền. Loader ấy không có class đích và parent bootstrap cũng không có, nên phát `ClassNotFoundException`.
5. `Class.forName("ForNameDemo$Deferred", false, callerLoader)` lấy `Class<?>` nhưng **chưa chạy** static block. Lời gọi với `true` sau đó mới in `Deferred initialized`.
6. `Class.forName("[LForNameDemo$ArrayElement;")` tìm class **mảng**; component type có thể được load, nhưng static initializer của `ArrayElement` **không bị buộc chạy chỉ vì array class được tìm**. Lời gọi một tham số theo tên component sau đó mới in `ArrayElement initialized`.
7. TCCL cũ được khôi phục trong `finally` để tránh làm ảnh hưởng thao tác khác cùng thread.

Ví dụ trên cố tình dùng **hai loader khác nhau** và **ba loại khởi tạo** để chứng minh hành vi API. Kết quả phụ thuộc bối cảnh chạy được nêu rõ: mặc định JDK 17+, trên application class path, không có hệ thống tùy biến loader bất thường.

## 4. So sánh các overload và `ClassLoader.loadClass`

| API | Chọn loader | Khởi tạo class thông thường? | Nếu không tìm được |
| --- | --- | --- | --- |
| `Class.forName(String name)` | **Defining loader của caller** | **Có**, nếu chưa khởi tạo | `ClassNotFoundException` |
| `Class.forName(String name, boolean initialize, ClassLoader loader)` | **Loader truyền vào**; `null` là bootstrap | Theo `initialize` | `ClassNotFoundException` |
| `Class.forName(Module module, String name)` | **Module truyền vào** và loader gắn với module đó | **Không yêu cầu link/init** theo hợp đồng overload này | Trả `null` nếu không tìm thấy class trong module |
| `ClassLoader.loadClass(String name)` | Loader được gọi; dùng chính sách `loadClass` | **Không tự yêu cầu initialize** | `ClassNotFoundException` |
| `T.class` | Kết quả được compiler/JVM resolve theo ngữ cảnh class caller | **Không do riêng class literal** | Không phải API nhận tên động; lỗi liên kết nếu class dependency không hợp lệ |

Đối với `Class.forName(String, boolean, ClassLoader)`, tham số `initialize = true` đồng nghĩa **khởi tạo class/interface** khi cần. Nếu class đã khởi tạo thành công, JVM không khởi tạo lại.

`ClassLoader.loadClass(name)` **không phải bản thay thế đồng nghĩa** cho `Class.forName(name)`: nó trả `Class<?>` mà không tự kích hoạt initialization. Một bước sử dụng sau đó như gọi static method, truy cập static field không phải compile-time constant hay tạo instance mới có thể buộc khởi tạo.

Overload `Class.forName(Module, String)` ra đời để xác định module đích rõ hơn. Nó nhận **binary name**, không dùng tên mảng theo cách overload chuỗi/loader; return `null` nếu module đích không chứa class được yêu cầu. Phương thức này không đảm bảo đã link hay initialize class; muốn sử dụng thành viên vẫn phải tuân theo quy tắc JVM/module access.

## 5. Một hay ba tham số: chọn API theo mục đích

### Trường hợp A – biết class đích ở cùng miền loader với caller

Dùng:

```java
Class<?> type = Class.forName("com.example.local.Handler");
```

Đây là **đoạn minh họa**, chỉ chạy nếu class tương ứng tồn tại và accessible theo loader của class caller. Phù hợp với chương trình có một loader ứng dụng hoặc code chủ động muốn dùng namespace của mình.

### Trường hợp B – cần chọn loader của plugin

Dùng overload ba tham số:

```java
public static Class<?> loadPluginType(
        String binaryName, ClassLoader pluginLoader)
        throws ClassNotFoundException {
    return Class.forName(binaryName, true, pluginLoader);
}
```

Đây là **method minh họa đầy đủ**, cần đặt vào một class. Để chỉ tìm type và tránh static side effect trước lúc cần thực thi, cân nhắc `false`:

```java
Class<?> pluginType =
        Class.forName(binaryName, false, pluginLoader);
```

`false` không đảm bảo “không xảy ra bất kỳ công việc nào”: JVM vẫn có thể load/link class và phụ thuộc cần thiết. Nó chỉ nói **không yêu cầu khởi tạo class đích** ngay trong lời gọi này.

### Trường hợp C – library/framework nhận plugin thông qua TCCL

Một số framework (ví dụ cơ chế khám phá provider) chủ động dùng **thread context class loader** để tìm implementation do child loader định nghĩa. Nếu đó là hợp đồng mong muốn:

```java
ClassLoader contextLoader = Thread.currentThread()
        .getContextClassLoader();

Class<?> implementation =
        Class.forName(binaryName, true, contextLoader);
```

Đoạn trên giả định `binaryName` được xác định, context loader phù hợp và code nằm trong method có xử lý `ClassNotFoundException`. Nếu TCCL bằng `null`, overload ba tham số dùng **bootstrap loader**, không tự chuyển sang system loader. Nếu framework cần fallback `system` khi TCCL null, phải **viết chính sách fallback rõ ràng** theo contract framework.

TCCL là trạng thái có thể thay đổi của thread. Khi tạm gán cho plugin request hoặc service discovery, luôn khôi phục loader cũ trong `finally`, nhất là khi thread được tái sử dụng bởi thread pool.

### Trường hợp D – lớp thuộc một named module cụ thể

Nếu đã biết module:

```java
Module module = /* module đích trong layer thích hợp */;
Class<?> type = Class.forName(module, "com.example.api.Service");
if (type == null) {
    throw new IllegalArgumentException("Class not in target module");
}
```

Đây là **mã minh họa**; `module` phải được lấy từ module thực tế. Với module layer do ứng dụng tạo, có thể lấy loader qua `layer.findLoader("m.plugin")` và dùng overload ba tham số nếu còn cần **initialize** lớp đó. Đừng tự cho rằng lớp trong custom `ModuleLayer` luôn hiện diện qua system loader.

## 6. Tên đầu vào: binary name và tên kiểu mảng

`Class.forName(String)` nhận **binary name** của class/interface; với lớp thành viên dùng dấu `$` thay vì cú pháp `Outer.Inner` của Java source. Ví dụ:

| Kiểu cần tìm | Tên hợp lệ |
| --- | --- |
| Class thông thường | `java.lang.String` |
| Member class | `java.util.Map$Entry` |
| `String[]` | `[Ljava.lang.String;` |
| `String[][]` | `[[Ljava.lang.String;` |
| `int[]` | `[I` |

Dùng `SomeType.class.getName()` để quan sát tên thực tế, đặc biệt với nested classes. Các chuỗi `java/util/Map$Entry`, `java.util.Map.Entry` và `java.lang.String[]` không phải tên tìm tương ứng của các kiểu trong bảng. `"int"` và `"void"` không trả primitive/void class; dùng `int.class` hoặc `void.class`.

Array class có quy tắc riêng: `Class.forName("[Lpkg.Component;")` có thể load component type nhưng không khởi tạo component chỉ vì phép tìm array. Những chi tiết về từng tham số, dấu hiệu lỗi và nhiều ví dụ lookup theo loader được triển khai sâu hơn trong bài overload ba tham số.

## 7. Tại sao `forName` có thể kích hoạt `<clinit>`?

Class initialization xảy ra trong giai đoạn JVM phải hoàn tất khởi tạo class trước khi thao tác yêu cầu tiếp tục. Overload một tham số của `Class.forName` có `initialize = true`, nên khi class chưa khởi tạo, static field initializers và các static blocks (được compiler thể hiện bằng `<clinit>` khi cần) sẽ chạy.

Ví dụ:

```java
public class InitOnlyDemo {
    static class Configuration {
        static final int VALUE = initialize();

        static int initialize() {
            System.out.println("Configuration initialized");
            return 10;
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("before");
        Class<?> type = Class.forName(
                "InitOnlyDemo$Configuration");
        System.out.println("after");
        System.out.println("class: " + type.getSimpleName());
    }
}
```

```bash
javac --release 17 InitOnlyDemo.java
java -cp . InitOnlyDemo
```

Stdout chính xác:

```text
before
Configuration initialized
after
class: Configuration
```

Không có `new Configuration()` hay lời gọi method thủ công; chỉ `Class.forName` đã yêu cầu init. Với `Configuration.class`, bản thân class literal không buộc initializer chạy.

**Chú ý hằng:** nếu code chỉ đọc một `static final int X = 10` là *constant variable* trong source, compiler có thể inline giá trị nên không cần init class khai báo. Nhưng `Class.forName("SomeClass")` **vẫn yêu cầu initialization** của `SomeClass`, bất kể class có field hằng hay không; hai loại thao tác không được đánh đồng.

### `forName` với array khác class component

Nếu `name` là tên array class, API trả `Class<?>` của **mảng**; component type được load nhưng **không bị khởi tạo** chỉ bởi `forName` với tên array. Ví dụ phần `ForNameDemo` cho thấy `"[LForNameDemo$ArrayElement;"` không làm chạy `ArrayElement` static block. Đừng suy rằng `true` sẽ khởi tạo component class trong mọi trường hợp.

## 8. Xử lý lỗi chính xác

API có thể phát **`ClassNotFoundException`**, **`LinkageError`** và **`ExceptionInInitializerError`** trong những trường hợp khác nhau:

| Tình huống | Kết quả thường gặp | Ý nghĩa |
| --- | --- | --- |
| Loader được chọn không tìm được binary name | `ClassNotFoundException` | Không có class qua phạm vi loader/delegation ấy |
| Class file tồn tại nhưng phụ thuộc linkage bị lỗi hoặc class có bytecode không tương thích | `LinkageError` (hoặc subclass) | JVM không hoàn thành linking như yêu cầu |
| Static initializer ném exception không phải `Error` | `ExceptionInInitializerError` | `<clinit>` thất bại trong lần initialize đầu |
| Class đã từng thất bại initialization, được dùng lần nữa | Thường `NoClassDefFoundError` | Class ở trạng thái erroneous, không tự thử chạy lại initializer |
| Muốn tải tên primitive `"int"` | Thường `ClassNotFoundException` | API không dùng để lấy primitive class |
| Tìm thấy class nhưng code sau đó không được phép truy cập thành viên | `IllegalAccessException`, `IllegalAccessError` hoặc ngoại lệ reflection tương ứng | Tìm class không đồng nghĩa có quyền sử dụng mọi thành viên |

`ExceptionInInitializerError` là subclass của `LinkageError`. Nếu code muốn log lỗi riêng, đặt catch chuyên biệt trước catch `LinkageError`; không nhất thiết nên bắt các lỗi này để tiếp tục công việc, vì class có thể đã chuyển sang trạng thái erroneous.

### Lỗi khởi tạo ở lần đầu và lần sau

Khi `<clinit>` ném một exception không thuộc `Error`, JVM thường bọc nó trong `ExceptionInInitializerError` ở lần kích hoạt đầu tiên. Class trở thành **erroneous**, nên lần active use tiếp theo đối với **cùng runtime class** thường nhận `NoClassDefFoundError`, không chạy lại initializer. Vì vậy cần giữ stack trace và cause của lỗi đầu tiên. Bài về overload `Class.forName(name, initialize, loader)` thực hành riêng tình huống này với hai lần gọi `initialize=true`.

## 9. Vì sao tải được class chưa chắc sử dụng được?

`Class.forName` là API **tìm metadata của class**. Khả năng tìm một `Class<?>` chưa chứng minh:

- Có constructor không tham số để tạo instance.
- Class không abstract/interface.
- Caller có quyền gọi constructor hoặc private method.
- Named module đã `exports` hoặc `opens` package cho truy cập cần thiết.
- Client và class plugin dùng **cùng định nghĩa interface**; trong Java, danh tính kiểu là binary name + defining loader.
- Dependency của class sẽ liên kết thành công trong mọi đường code được gọi về sau.

Ví dụ code:

```java
Class<?> type = Class.forName(binaryName, false, pluginLoader);
Object instance = type.getDeclaredConstructor().newInstance();
```

Đây là **đoạn minh họa**, giả định `binaryName` và `pluginLoader` có sẵn, class có constructor truy cập được và các exception đã được xử lý. Dòng đầu `initialize=false` chỉ tìm class. Dòng thứ hai có thể yêu cầu initialization khi tạo instance, đồng thời phải vượt qua access/module checks và có thể phát exception từ constructor.

Nếu plugin implement một interface của host, nên kiểm tra:

```java
Class<?> type =
        Class.forName(binaryName, true, pluginLoader);
if (!PluginApi.class.isAssignableFrom(type)) {
    throw new IllegalArgumentException(
            "Not an implementation of PluginApi");
}
```

Đây là **mã minh họa**, giả định `PluginApi` thuộc API chung mà cả host và plugin resolve về **cùng `Class<?>`**. Khi mỗi loader tự định nghĩa một bản `PluginApi` trùng tên, kiểm tra assignability có thể thất bại dù tên interface giống nhau; sửa layout class loader/delegation, không chỉ sửa chuỗi `forName`.

## 10. Có nên dùng `Class.forName` để kích hoạt đăng ký driver?

Trong các phiên bản JDBC cũ, nhiều ví dụ gọi:

```java
Class.forName("com.example.jdbc.Driver");
```

để buộc static initializer của driver đăng ký với `DriverManager`. Đây là một **mẫu lịch sử** thể hiện side effect của `forName`; chuỗi `com.example.jdbc.Driver` ở trên chỉ là tên minh họa, không đại diện driver tồn tại.

Trong JDBC 4+ hiện đại, driver phù hợp thường được khám phá qua **service-provider mechanism**, khi JAR/module được đóng gói đúng. Do đó không nên mặc định thêm `Class.forName` cho mọi ứng dụng JDBC hoặc suy rằng nó là cách duy nhất đăng ký driver.

Nếu driver không được phát hiện, điều tra dependency, `META-INF/services/java.sql.Driver` hoặc khai báo module `provides`, TCCL, hệ module và driver manager. `Class.forName` có thể ép init class cụ thể nếu đúng loader, nhưng không sửa được mọi lỗi service discovery hay binary compatibility.

## 11. Vấn đề loader trong ứng dụng nhiều module hoặc plugin

Giả sử host dùng system loader, mỗi plugin có loader riêng:

```text
               [system loader]
                  /         \
          [plugin A]       [plugin B]
           demo.Impl        demo.Impl
```

Nếu code trong **plugin A** gọi `Class.forName("demo.Impl")`, API mặc định dùng defining loader của class caller thuộc plugin A (giả sử caller được plugin A định nghĩa); kết quả có thể là `demo.Impl` của A.

Nếu **host/helper** ở system loader gọi chính `Class.forName("demo.Impl")`, class này có thể không được tìm thấy do system loader không nhìn xuống child plugin loader. Nếu **plugin B** gọi, có thể nhận `demo.Impl` do plugin B định nghĩa — **hai `Class<?>` không đồng nhất**.

Điều này không có nghĩa `forName` vô tình “thay loader theo tên thread”. Nó chọn theo **định nghĩa của class caller tại call site**, còn mỗi loader thực hiện chính sách tìm riêng. Cùng một chuỗi `"demo.Impl"` có thể có các kết quả khác nhau mà vẫn đúng hợp đồng API.

### Thiết kế helper rõ ràng

Trong library phát triển cho nhiều loader, cung cấp overload nhận tham số loader:

```java
public final class PluginClasses {
    private PluginClasses() { }

    public static Class<?> find(
            String binaryName,
            boolean initialize,
            ClassLoader loader) throws ClassNotFoundException {
        return Class.forName(binaryName, initialize, loader);
    }
}
```

Class này **biên dịch được với Java 17+** và không yêu cầu một framework riêng. Thay vì phụ thuộc vào loader của chính `PluginClasses`, caller chọn loader phù hợp với plugin/layer được yêu cầu. Tuy nhiên, **không** tùy tiện truyền TCCL hoặc system loader: cần quyết định từ kiến trúc plugin về namespace, API dùng chung, vòng đời và quyền truy cập.

Nếu plugin loader cần được tháo bỏ, tránh giữ `Class<?>` hoặc instance class plugin trong static cache sống lâu hơn plugin, vì những tham chiếu đó có thể giữ loader và ngăn garbage collection.

## 12. Cách chẩn đoán một lời gọi `forName` đang dùng loader nào

Thêm log gần **đúng nơi gọi `Class.forName(String)`**:

```java
ClassLoader callerLoader = MyCaller.class.getClassLoader();
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
ClassLoader tccl = Thread.currentThread().getContextClassLoader();

System.out.println("caller=" + callerLoader);
System.out.println("system=" + systemLoader);
System.out.println("tccl=" + tccl);

Class<?> result = Class.forName(binaryName);
System.out.println("defined by=" + result.getClassLoader());
System.out.println("module=" + result.getModule());
```

Đây là **đoạn minh họa**, giả định `MyCaller` chính là class chứa đoạn mã tại call site, `binaryName` hợp lệ và đã xử lý `ClassNotFoundException`. Không dùng `MyCaller.class.getClassLoader()` trong một class không phải caller rồi nhầm đó là loader hiệu dụng.

Trình tự kiểm tra lỗi:

1. **Xác định call site trực tiếp:** câu lệnh ở class nào? Có đi qua wrapper/helper do loader khác định nghĩa không?
2. **So loader:** in defining loader của caller, system, TCCL; nhớ rằng `null` thường biểu diễn bootstrap.
3. **Kiểm tra đúng tên:** binary name của member/nested class, tên array hoặc package. Đừng đưa source canonical name sai cho nested class.
4. **Kiểm tra class path/module layer:** class thật sự được định nghĩa cho loader nào? Có lọt ở child loader nhưng lời gọi xuất phát từ parent không?
5. **Phân biệt giai đoạn thất bại:** `ClassNotFoundException` là tìm class thất bại; `ExceptionInInitializerError` là initialization thất bại; `NoClassDefFoundError` có thể là phụ thuộc thiếu hoặc class erroneous.
6. **Kiểm tra module access:** class có tìm được nhưng reflection/invocation bị chặn bởi `exports`/`opens` hoặc access Java không?
7. **Sửa lựa chọn loader tại ranh giới API:** truyền `ClassLoader`/`Module`/`ModuleLayer` khi bối cảnh cần rõ ràng; tránh thay TCCL toàn ứng dụng để vá tạm một lời gọi.

Trên HotSpot có thể dùng logging cho class loading:

```bash
java -Xlog:class+load=info -cp . ForNameDemo
```

Log này nói về **loading**, không phải bằng chứng duy nhất cho lựa chọn caller-sensitive hoặc thời điểm class initialization. Quan sát output từ static block và giá trị `getClassLoader()` ở đúng call site để phân tích chính xác hơn.

## 13. Những câu hỏi thường gặp

**Q1.** Vì sao `Class.forName("java.lang.String")` hoạt động dù caller ở application loader?

**Đáp án:** Application loader có thể delegate qua platform/bootstrap để lấy `String`. Loader mặc định bắt đầu yêu cầu là của caller, nhưng class trả về do bootstrap định nghĩa.

**Q2.** Nếu TCCL trỏ vào plugin loader thì `Class.forName("plugin.Driver")` tự dùng plugin loader không?

**Đáp án:** Không. Overload một tham số dùng defining loader của class caller. Muốn dùng TCCL thì lấy `Thread.currentThread().getContextClassLoader()` và truyền qua overload ba tham số theo chính sách API.

**Q3.** Hai method đều gọi `Class.forName("pkg.Type")` mà kết quả khác nhau có sai không?

**Đáp án:** Không nhất thiết. Nếu hai method nằm trong class do các defining loader khác nhau nạp, API có thể tìm hai định nghĩa `pkg.Type` khác nhau. Danh tính JVM của class phụ thuộc **binary name + defining loader**.

**Q4.** `Class.forName(name, false, loader)` có bảo đảm class chưa từng khởi tạo không?

**Đáp án:** Không. Nó chỉ **không yêu cầu** initialization trong lần gọi này. Class có thể đã khởi tạo do một thao tác khác, và lời gọi có thể load/link những gì JVM cần.

**Q5.** `Class.forName("pkg.Example")` đã gọi constructor chưa?

**Đáp án:** Chưa. Class initializer `<clinit>` có thể chạy, còn instance constructor `<init>` chỉ chạy khi thực sự tạo instance bằng `new` hoặc reflection/cơ chế tương đương.

**Q6.** Tại sao `Class.forName("int")` không trả `int.class`?

**Đáp án:** `int` không phải binary name của một class có thể được loader tìm như class thông thường. Lấy primitive class qua `int.class` hoặc `Integer.TYPE`. Với array primitive có thể dùng tên array như `"[I"`.

**Q7.** Vì sao `Class.forName("[Lpkg.Component;")` không chạy static initializer của `Component` dù overload một tham số có `initialize=true`?

**Đáp án:** Với tên array, component type được load nhưng **không tự init** chỉ vì tìm array class. Lần sử dụng component theo thao tác có yêu cầu initialization mới kích hoạt.

**Q8.** `Class.forName(Module, String)` có tự động init không?

**Đáp án:** Không. Overload này không link hoặc chạy class initializer theo hợp đồng API, và nếu class không nằm trong module đích có thể trả `null`. Nó khác overload ba tham số có `initialize=true`.

**Q9.** Vì sao host ở parent loader không tìm được class trong plugin child loader dù plugin gọi API host thành công?

**Đáp án:** Parent delegation chủ yếu cho child hỏi parent, không tự làm parent thấy mọi class do child định nghĩa. Khi host cần class plugin, hãy truyền loader/plugin layer có chủ đích hoặc dùng cơ chế discovery phù hợp.

**Q10.** Có thể bắt mọi lỗi của `forName` bằng `catch (ClassNotFoundException e)` không?

**Đáp án:** Không. Lỗi linking và initialization có thể là `LinkageError`, gồm `ExceptionInInitializerError` hoặc `NoClassDefFoundError` trong tình huống cụ thể.

## 14. Bài tập ngắn có đáp án

**Bài 1.** Trong `ForNameDemo`, giải thích vì sao `Class.forName("ForNameDemo$Target")` thành công khi TCCL đã gán một loader không tìm được `Target`.

*Đáp án:* Caller là `ForNameDemo`, nên overload một tham số dùng defining loader của `ForNameDemo`. Nó không đọc TCCL. Custom loader `isolated` chỉ được dùng trong lời gọi ba tham số rõ ràng.

**Bài 2.** Một thư viện `FrameworkHelper` do system loader định nghĩa nhận tên class plugin `com.acme.PluginImpl` và gọi `Class.forName(name)`, nhưng trả `ClassNotFoundException`. Cần thay đổi ranh giới API ở đâu?

*Đáp án:* Cho plugin/module layer truyền đúng loader hoặc module context vào helper, sau đó dùng `Class.forName(name, initialize, loader)` hoặc API module tương ứng. Thay đổi TCCL của thread chưa đủ nếu helper vẫn dùng overload một tham số.

**Bài 3.** Code sau có thể in gì?

```java
Class<?> c = Class.forName("java.lang.String");
System.out.println(c.getClassLoader() == null);
```

*Đáp án:* Trong Java SE thông thường, in `true` vì `String` do bootstrap định nghĩa. Class caller có thể nằm ở application loader, nhưng loader của class kết quả được quyết định qua delegation.

**Bài 4.** `Class<?> c = Class.forName("pkg.Type", false, loader);` có ngăn `pkg.Type` được initialize về sau không?

*Đáp án:* Không. Nó tránh yêu cầu initialization **trong lần gọi hiện tại**. Lần đầu gọi static method, tạo instance hay thao tác yêu cầu khác sẽ buộc khởi tạo nếu class chưa được khởi tạo.

**Bài 5.** Vì sao loader dùng để trả `Class<?>` và khả năng dùng được constructor qua reflection là hai câu hỏi khác nhau?

*Đáp án:* Loading/class lookup cung cấp một đối tượng `Class<?>`. Constructor invocation còn cần class đã sẵn sàng để khởi tạo, constructor phù hợp và điều kiện truy cập Java/module. Các bước sau có thể thất bại dù tìm class đã thành công.

## Ghi nhớ

Khi thấy `Class.forName(name)`, hãy đọc nó thành **“tìm và yêu cầu khởi tạo class theo defining loader của class chứa lời gọi này”**. Nếu hệ thống có plugin, application server, custom `ModuleLayer` hoặc TCCL, hãy xác định rõ **class caller**, **defining loader**, **tên binary**, **loader mong muốn** và **có cần initialization ngay không**. Chọn overload ba tham số hoặc overload theo `Module` khi cần diễn đạt lựa chọn ấy một cách rõ ràng.

Nguồn tham khảo chuẩn:

- [Class – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): hợp đồng `Class.forName(String)`, `Class.forName(String, boolean, ClassLoader)` và `Class.forName(Module, String)`.
- [ClassLoader – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass` và loader tích hợp.
- [JLS 17, 12.4 – Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): thời điểm initialize và hành vi lỗi.
- [JVMS 17, 5 – Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining/initiating loader, danh tính kiểu và cơ chế linking.
