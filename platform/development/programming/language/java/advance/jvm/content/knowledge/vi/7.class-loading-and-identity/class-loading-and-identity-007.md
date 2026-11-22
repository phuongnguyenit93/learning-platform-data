# Nạp lớp theo yêu cầu qua `Class.forName` và `ClassLoader.loadClass`

Java cho phép chương trình biết **tên lớp dưới dạng chuỗi** rồi yêu cầu JVM tìm và nạp lớp đó khi cần. Hai API rất phổ biến là `Class.forName(...)` và `ClassLoader.loadClass(...)`. Chúng có thể trả về cùng một đối tượng `Class<?>`, nhưng **không đồng nghĩa về thời điểm khởi tạo lớp (initialization)**, nguồn class loader mặc định, cách xử lý lỗi và mức kiểm soát vòng đời.

Đây là kiến thức nền cho reflection, driver JDBC, cơ chế plugin, Dependency Injection container, dynamic discovery và điều tra các lỗi như `ClassNotFoundException`, `NoClassDefFoundError` hoặc `ExceptionInInitializerError`. Bài lấy **Java SE 17** làm mốc, phân biệt hành vi được API/JLS/JVMS quy định với quyết định riêng của compiler/JVM/class loader.

## 1. Ba mốc khác nhau trước khi dùng một lớp

Hãy đọc `Class<?>` như **runtime representation của kiểu**, không phải dấu hiệu `static {}` đã chạy. JVM phân biệt **loading** (tạo class representation), **linking** (verification, preparation, resolution, trong đó một phần resolution có thể trì hoãn) và **initialization** (thực hiện static field initializers/`<clinit>` theo quy tắc).

Đối với bài này, câu hỏi không phải mô tả lại toàn bộ JVM lifecycle mà là **hai API lấy `Class<?>` có tự yêu cầu initialization hay không**. `Class.forName(name)` thường yêu cầu initialization; `Class.forName(name, false, loader)` và `loader.loadClass(name)` không chủ động làm điều đó. Dù `initialize=false`, lỗi loading/linking vẫn có thể xảy ra; chỉ có `Class<?>` chưa đồng nghĩa đã tạo instance hay chạy plugin lifecycle.

## 2. Hai API: giống tên lớp, khác ý nghĩa mặc định

### `Class.forName(String className)`

```java
Class<?> type = Class.forName("com.example.Plugin");
```

Đây là **đoạn minh họa**; lớp `com.example.Plugin` giả định có trong classpath/module path phù hợp. Overload một tham số:

- Tìm lớp/interface theo **binary name** được cung cấp.
- Dùng **defining class loader của lớp gọi `Class.forName`** theo quy tắc caller-sensitive, không mặc định lấy `Thread.currentThread().getContextClassLoader()`.
- **Yêu cầu initialization** nếu kiểu chưa được khởi tạo và là lớp/interface phù hợp.
- Có thể ném **`ClassNotFoundException`** (checked) khi lớp không tìm thấy, cũng như các lỗi liên kết hoặc khởi tạo thích hợp.

Nếu chỉ muốn lấy metadata mà **không chủ động khởi tạo**, overload một tham số không phải lựa chọn tốt. Dùng overload có cờ `initialize=false` khi thích hợp.

### `Class.forName(String name, boolean initialize, ClassLoader loader)`

```java
ClassLoader loader = SomeCaller.class.getClassLoader();
Class<?> metadataOnly = Class.forName("com.example.Plugin", false, loader);
Class<?> ready = Class.forName("com.example.Plugin", true, loader);
```

Đây cũng là **đoạn minh họa**, không phải chương trình độc lập; `SomeCaller` và `Plugin` là tên giả định.

- `name`: binary name của lớp/interface cần tìm, hoặc dạng tên mảng mà API cho phép.
- `initialize=false`: yêu cầu nạp và liên kết nhưng **không chủ động khởi tạo** lớp.
- `initialize=true`: bảo đảm initialization được thực hiện nếu cần theo quy tắc VM.
- `loader`: chọn loader cụ thể; `null` biểu thị **bootstrap class loader** cho overload này.
- Class đã được khởi tạo trước đó sẽ **không chạy lại static initializers** chỉ vì gọi `forName` lần nữa.

Lưu ý: một lời gọi `forName(name, false, loader)` không “khóa” lớp ở trạng thái chưa khởi tạo. **Một active use khác** trong ứng dụng có thể làm lớp khởi tạo trước khi bạn kiểm tra tiếp. Cờ `false` chỉ nói rằng lời gọi hiện tại **không yêu cầu** initialization.

### `ClassLoader.loadClass(String name)`

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("com.example.Plugin");
```

**Đoạn minh họa:** giả sử context class loader không phải `null` và biết tìm lớp đang cần.

- API này yêu cầu **load** một lớp có binary name đã cho qua chính loader được chọn.
- Phần triển khai `ClassLoader.loadClass(name)` mặc định tương ứng cơ chế `loadClass(name, false)` của class loader: **không yêu cầu resolve/link toàn bộ ngay**, và **không yêu cầu initialization**.
- Loader đã được tùy biến có thể quyết định nguồn bytecode và chính sách delegation; logic nạp có thể khác nhau giữa các loader.
- Việc trả `Class<?>` không tự chạy static block của target class chỉ vì code sau đó định tạo instance hoặc dùng reflection.

Có overload protected `loadClass(String name, boolean resolve)` dùng trong cách cài đặt class loader. **`resolve=true` không có nghĩa `initialize=true`**. Resolution/linking khác initialization; hơn nữa overload đó là **protected**, không phải cờ mà caller thông thường đưa vào public `loadClass(String)`.

### Bảng đối chiếu nhanh

| API | Loader dùng mặc định | Yêu cầu khởi tạo? | Chọn loader tường minh? | Kết quả |
| --- | --- | --- | --- | --- |
| `Class.forName(name)` | Defining loader của caller | **Có** | Không trong overload này | `Class<?>` |
| `Class.forName(name, true, loader)` | Loader truyền vào | **Có** | Có | `Class<?>` |
| `Class.forName(name, false, loader)` | Loader truyền vào | **Không** | Có | `Class<?>` |
| `loader.loadClass(name)` | Chính `loader` được gọi | **Không** theo đường mặc định | Có, qua instance loader | `Class<?>` |

**Quy tắc thực hành:** Nếu phải **chắc chắn lớp được initialize**, dùng `Class.forName(name, true, loader)` hoặc một active use được đặc tả; nếu chỉ cần `Class` để đọc metadata, chọn `Class.forName(name, false, loader)` hoặc `loader.loadClass(name)` tùy nhu cầu linking/loader và xử lý tác dụng phụ.

## 3. Chương trình Java 17: nhìn chính xác thứ tự initialization

Tạo file **`LazyLoadLab.java`**:

```java
public class LazyLoadLab {

    public static class Passive {
        static {
            System.out.println("Passive.<clinit>");
        }

        public static void ping() {
            System.out.println("Passive.ping");
        }
    }

    public static class Active {
        static {
            System.out.println("Active.<clinit>");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = LazyLoadLab.class.getClassLoader();
        String passiveName = LazyLoadLab.class.getName() + "$Passive";
        String activeName = LazyLoadLab.class.getName() + "$Active";

        System.out.println("1: loadClass");
        Class<?> passive = loader.loadClass(passiveName);

        System.out.println("2: forName(false)");
        Class<?> same = Class.forName(passiveName, false, loader);
        System.out.println("same=" + (passive == same));

        System.out.println("3: invoke static method");
        passive.getDeclaredMethod("ping").invoke(null);

        System.out.println("4: forName(true) again");
        Class.forName(passiveName, true, loader);

        System.out.println("5: forName(true) on another class");
        Class.forName(activeName, true, loader);

        System.out.println("6: done");
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac --release 17 LazyLoadLab.java
java LazyLoadLab
```

**Stdout chính xác trong chương trình này**:

```text
1: loadClass
2: forName(false)
same=true
3: invoke static method
Passive.<clinit>
Passive.ping
4: forName(true) again
5: forName(true) on another class
Active.<clinit>
6: done
```

**Diễn giải:**

- `loader.loadClass(passiveName)` tìm lớp và trả đối tượng `Class` mà **không in `Passive.<clinit>`**.
- `Class.forName(passiveName, false, loader)` không yêu cầu khởi tạo; trong cùng loader, hai lời gọi xác định cùng một lớp, nên `passive == same` là `true`.
- Lấy method bằng `getDeclaredMethod` để chuẩn bị reflection **chưa phải lời gọi method**; nhưng `Method.invoke(null)` đối với method static là active use và kích hoạt initialization của `Passive` trước khi chạy `ping`.
- `Class.forName(passiveName, true, loader)` tiếp theo không chạy initializer lần hai vì class đã được khởi tạo.
- `Class.forName(activeName, true, loader)` làm `Active` khởi tạo và in đúng một dòng từ static block.

Dấu `<clinit>` trong output là chuỗi do ví dụ chủ động in, không phải tên một method Java có thể viết bằng source và gọi trực tiếp. Compiler có thể tạo method JVM `<clinit>` chứa static initializer code.

### Tại sao không dùng `new Passive()` để kiểm tra loading?

`new Passive()` là một **active use** khiến `Passive` phải được initialize nếu chưa được khởi tạo. Nó không thể hiện rõ sự khác nhau giữa `loadClass` và `forName(false)`. Với phép thử về loading, tránh vô tình tạo instance, truy cập static field không phải compile-time constant hoặc gọi static method trước thời điểm quan sát.

## 4. Khi nào JVM khởi tạo lớp?

JLS §12.4.1 mô tả những thời điểm class/interface phải được initialize trước lần active use tương ứng. Những trường hợp hay gặp:

- Tạo instance của lớp bằng `new`.
- Gọi một **static method** được khai báo ở lớp/interface có liên quan.
- Đọc hoặc ghi một static field **không phải constant variable** của lớp/interface theo quy tắc Java.
- Một số hoạt động reflection yêu cầu initialization.
- Gọi `Class.forName(name, true, loader)`.

Ví dụ **không nhất thiết** kích hoạt initialization của lớp thành phần:

- Lấy class literal bằng `SomeType.class`.
- Gọi `ClassLoader.loadClass(name)`.
- Gọi `Class.forName(name, false, loader)`.
- Tạo mảng `new SomeType[10]` (không khởi tạo component class chỉ vì tạo array).
- Đọc một `static final` **constant variable** thích hợp đã được compiler đưa vào nơi sử dụng.

### Ví dụ kiểm chứng constant và class literal

File **`InitializationTriggers.java`**:

```java
public class InitializationTriggers {

    static class Values {
        static final int MAGIC = 42;
        static final int COMPUTED = compute();

        static int compute() {
            System.out.println("Values.<clinit>");
            return 99;
        }
    }

    public static void main(String[] args) {
        System.out.println("constant=" + Values.MAGIC);

        Class<?> type = Values.class;
        System.out.println("literal=" + type.getSimpleName());

        System.out.println("computed=" + Values.COMPUTED);
    }
}
```

```bash
javac --release 17 InitializationTriggers.java
java InitializationTriggers
```

**Stdout**:

```text
constant=42
literal=Values
Values.<clinit>
computed=99
```

`MAGIC` là `static final int` được khởi tạo bằng một constant expression; việc đọc nó từ caller thường được compiler inlined và **không làm `Values` initialize**. Biểu thức `Values.class` trả `Class<?>` cũng không khởi tạo lớp. `COMPUTED` không phải constant variable vì gọi một method, nên truy cập `Values.COMPUTED` kích hoạt initialization; `compute()` in dòng giữa và trả về `99`.

Đừng tổng quát hóa thành “mọi `static final` đều không khởi tạo class”: ví dụ `static final Object O = new Object();` hoặc `static final int N = compute();` không phải compile-time constant variable.

### Khởi tạo có thể liên quan tới superclass và interface

- Khi khởi tạo một class, JVM bảo đảm các **superclass** cần thiết được initialize trước; còn có các quy tắc đặc biệt đối với superinterfaces khai báo default methods.
- Nạp một subclass không tự đồng nghĩa toàn bộ hierarchy đã chạy static initializers.
- Khởi tạo một interface không có nghĩa mọi superinterface của nó đều được initialize một cách đệ quy giống class.
- Initialization có cơ chế đồng bộ theo class/interface để tránh hai thread cùng thực thi `<clinit>`; những thread khác có thể phải đợi khi một thread đang khởi tạo.

Điểm quan trọng trong debug: thứ tự log static initializer có thể đến từ quy tắc phụ thuộc kiểu, **không chỉ** từ dòng `forName` nằm ở đâu.

## 5. Binary name, canonical name và dạng tên mảng

Các API nhận tên lớp bằng chuỗi thường cần **binary name** theo quy tắc của JLS, **không đơn giản tên hiển thị ở source**:

| Kiểu | Tên đáng dùng để nạp theo string | Lưu ý |
| --- | --- | --- |
| Top-level class `java.lang.String` | `java.lang.String` | Tên package/class với dấu chấm |
| Nested class `Outer.Inner` | `Outer$Inner` | Binary name có ký tự `$` cho nested class |
| Một lớp trong package `demo.` | `demo.Helper` | Package phải khớp tên binary trong class file |
| Mảng String | `[Ljava.lang.String;` | Tên theo `Class.getName()`/descriptor-like syntax của array |
| Mảng int | `[I` | Dạng tên array của primitive component |
| Primitive `int` | Không dùng `Class.forName("int")` như cách lấy primitive class | Dùng `int.class` hoặc `Integer.TYPE` |

Với `Class.forName`, tên `java.lang.String[]` theo dạng source không phải tên array đúng; `[Ljava.lang.String;` mới là dạng hỗ trợ. Bản thân mảng là một class loại array; **tạo hoặc nạp array class không mặc nhiên initialize component class**.

Đừng ghép tên nested class tùy ý bằng cách thay mọi dấu chấm thành `$`. Dùng `SomeNested.class.getName()` nếu đã có class literal, hoặc tài liệu về binary name của chính kiểu đó.

### Chương trình quan sát tên và dạng mảng

Tạo file **`NameForms.java`**:

```java
public class NameForms {
    public static class Nested {
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = NameForms.class.getClassLoader();
        Class<?> nested = loader.loadClass(NameForms.class.getName() + "$Nested");

        System.out.println("nested=" + nested.getName());
        System.out.println("simple=" + nested.getSimpleName());
        System.out.println("array=" + Class.forName("[Ljava.lang.String;").isArray());
        System.out.println("intArray=" + Class.forName("[I").isArray());
        System.out.println("primitive=" + int.class.getName());
    }
}
```

```bash
javac --release 17 NameForms.java
java NameForms
```

**Stdout**:

```text
nested=NameForms$Nested
simple=Nested
array=true
intArray=true
primitive=int
```

Ví dụ để class ở **default package** nên binary name của nested class có dạng `NameForms$Nested`. Nếu đặt vào package `demo`, phần prefix sẽ là `demo.NameForms$Nested`.

## 6. Định danh lớp: cùng binary name chưa chắc là cùng một lớp JVM

Một class/interface runtime được định danh bởi **binary name kết hợp với defining class loader**. Hệ quả:

- Hai đối tượng `Class<?>` của một lớp do **cùng defining loader** định nghĩa sẽ biểu diễn cùng runtime class; gọi lại `loadClass`/`forName` không tự sinh “phiên bản mới”.
- Hai defining class loader **khác nhau** có thể định nghĩa hai lớp có **cùng binary name** nhưng JVM xem đó là **hai kiểu khác nhau**.
- Vì vậy hai object trông “đều là `plugin.Api`” vẫn có thể không cast được cho nhau; method lookup, interface compatibility và identity của class không dựa vào tên chuỗi riêng lẻ.
- Một loader **initiating** việc nạp có thể nhận class thực sự do loader cha **defining**; không được đồng nhất “loader tôi gọi `loadClass` trên đó” với “loader thực sự định nghĩa lớp” trong mọi trường hợp.

Có thể quan sát lớp đã trả về bằng:

```java
Class<?> type = Class.forName(name, false, loader);
System.out.println(type.getName());
System.out.println(type.getClassLoader());
```

Đây là **đoạn minh họa** với `name` và `loader` giả định đã được xác định. `type.getClassLoader()` trả về defining loader; **`null`** thường đại diện cho bootstrap loader. Tránh suy rằng một lớp thuộc module JDK bắt buộc có loader là `null`, vì Java 9+ còn có platform class loader và app class loader.

### Parent delegation là mô hình phổ biến, không phải nguyên lý “chỉ tồn tại một loader”

`ClassLoader.loadClass` theo triển khai mặc định thường:

1. Kiểm tra class đã được loader nạp trước đó chưa (`findLoadedClass`).
2. Nếu chưa, hỏi parent loader trước (hoặc bootstrap loader nếu không có parent).
3. Nếu parent không tìm thấy, dùng `findClass` của loader hiện tại.
4. Nếu caller yêu cầu resolve ở overload tương ứng, có thể gọi `resolveClass`.

Đây là **parent-first delegation** phổ biến. Tuy nhiên các class loader tùy biến có thể thay đổi đường tìm kiếm, áp dụng child-first cho một số package hoặc giới hạn không gian tên. Việc có thể viết loader tùy biến không có nghĩa được tùy tiện định nghĩa trùng các package bị hệ thống bảo vệ.

Ví dụ loader riêng có thể dùng để tách hai phiên bản thư viện/plugin. Cần quyết định rõ lớp API chia sẻ nào phải được parent load để plugin object có thể cast sang interface chung; nếu cả plugin và host cùng tải một bản sao interface từ hai loader khác nhau, cast có thể thất bại dù tên binary trùng.

## 7. Ví dụ về lỗi loader identity thường gặp trong plugin

Giả sử host có interface:

```java
package api;

public interface Plugin {
    String name();
}
```

Và plugin class:

```java
package impl;

public class PluginImpl implements api.Plugin {
    @Override
    public String name() {
        return "demo";
    }
}
```

**Hai snippet là các file Java riêng biệt theo package**, không phải một file tự chạy. Để host cast được `PluginImpl` thành `api.Plugin`, interface `api.Plugin` mà plugin implements phải tương ứng **cùng runtime class** với `api.Plugin` phía host. Cách triển khai phổ biến là đặt API chung trong loader cha và cho plugin loader delegate việc nạp API ấy.

Nếu plugin loader tự định nghĩa một bản `api.Plugin` khác, hai interface đều có binary name `api.Plugin` nhưng thuộc hai defining loader: về mặt runtime **không cùng kiểu**. Khi đó `ClassCastException` hoặc lỗi liên kết/loader constraints có thể xuất hiện; không sửa bằng cách đổi ép kiểu trong Java source.

### Không nhầm `Class<?>` với object plugin

`Class.forName("impl.PluginImpl", true, loader)` trả về **đối tượng `Class`**, không phải object `PluginImpl` đã được tạo. Để tạo instance, có thể dùng reflection với constructor phù hợp và kiểm tra type:

```java
Class<?> candidate = Class.forName("impl.PluginImpl", true, loader);
Object instance = candidate.getDeclaredConstructor().newInstance();
api.Plugin plugin = api.Plugin.class.cast(instance);
```

Đây là **đoạn minh họa**; giả định có public no-arg constructor, class được truy cập hợp lệ theo module/access rules, loader nhất quán cho API chung và exception đã được xử lý. Không mặc định `newInstance()` tạo được object nếu class abstract, không có constructor phù hợp hoặc module không cho reflection.

**`Class.forName` không phải API dependency injection**: nó chỉ tìm/nạp/initialize class; việc chọn constructor, quản lý lifecycle, inject dependencies, startup/shutdown là trách nhiệm tầng trên.

## 8. Context ClassLoader trong ứng dụng plugin và framework

`Thread.currentThread().getContextClassLoader()` (TCCL) cung cấp một **context loader** mà thư viện/framework có thể chủ động dùng để tìm plugin/providers trong bối cảnh thread hiện tại.

Ví dụ snippet:

```java
ClassLoader context = Thread.currentThread().getContextClassLoader();
if (context == null) {
    throw new IllegalStateException("No context class loader");
}
Class<?> pluginClass = Class.forName("com.example.Plugin", true, context);
```

Đây là **đoạn minh họa**, không phải chương trình độc lập; tên plugin giả định.

Phải phân biệt:

- `Class.forName(name)` **không tự động tra TCCL**; overload một tham số dùng loader liên quan tới **caller**.
- `Class.forName(name, initialize, context)` **đang chủ động chọn** TCCL.
- `context.loadClass(name)` dùng loader context được lấy từ thread, nhưng **không yêu cầu initialize**.
- Các framework như `ServiceLoader` có quy tắc chọn loader riêng theo overload/API; ví dụ `ServiceLoader.load(Service.class)` theo API thường sử dụng TCCL. Phải đọc contract của từng framework, không suy từ `Class.forName`.

TCCL là **mutable per-thread context**. Trong thread pool, một task có thể chạy với context loader do môi trường đặt từ trước; task cần thay đổi nó nên lưu lại loader cũ và phục hồi trong `finally`, tránh rò rỉ ảnh hưởng các task khác. Việc có quyền đặt TCCL hoặc nạp class còn phụ thuộc môi trường bảo mật và policies của ứng dụng.

### Ví dụ khung khôi phục TCCL

```java
Thread current = Thread.currentThread();
ClassLoader original = current.getContextClassLoader();
try {
    current.setContextClassLoader(pluginLoader);
    // Gọi framework sử dụng TCCL để tra provider.
    runDiscovery();
} finally {
    current.setContextClassLoader(original);
}
```

Đây là **fragment** nằm trong method nơi `pluginLoader` và `runDiscovery()` đã tồn tại, không phải chương trình chạy độc lập. Đoạn này không thay đổi defining loader của các class đã load; nó chỉ thay context mà một số framework dùng để tìm class tiếp theo.

## 9. Lỗi và ngoại lệ: không đồng nhất `ClassNotFoundException` với `NoClassDefFoundError`

| Tình huống | Biểu hiện thường gặp | Hướng điều tra |
| --- | --- | --- |
| `forName`/`loadClass` nhận tên lớp không tìm được qua loader đã chọn | **`ClassNotFoundException`** (checked) | Binary name, package, classpath/module path, jar, loader |
| Đã có class tham chiếu đến dependency nhưng JVM không thể định nghĩa/tải dependency khi cần | **`NoClassDefFoundError`** | Xem cause, jar/runtime dependency, name và loader |
| Class initialization chạy static initializer rồi thất bại do exception thích hợp | Có thể là **`ExceptionInInitializerError`** | Tìm exception gốc trong static init, không chỉ đổi loader |
| Class đã bị đánh dấu erroneous sau initialization failure; lần dùng sau | Có thể là **`NoClassDefFoundError`** “Could not initialize class ...” | Tìm **lỗi khởi tạo lần đầu**, không nhầm với file .class biến mất |
| Class file không hợp lệ hoặc bytecode sai | **`ClassFormatError`**, **`VerifyError`** | Kiểm tra format, class major version và instrumentation |
| Runtime JVM quá cũ so với class-file major version | **`UnsupportedClassVersionError`** | Kiểm tra version của class đã compile và runtime |
| Truy cập method/field không còn hợp lệ do binary mismatch | `NoSuchMethodError`, `IllegalAccessError`, `IncompatibleClassChangeError`... | Kiểm tra binary compatibility, loader, package/module |

`ClassNotFoundException` là một checked exception thường được các API nạp lớp thông báo khi **không tìm thấy tên được yêu cầu**. `NoClassDefFoundError` là một `LinkageError`; ngoài thiếu dependency lúc linking, nó còn có thể xảy ra sau **initialization failure**. Không nên tự động coi hai loại là cùng một lỗi rồi bắt/nuốt cả hai.

### Ví dụ minh họa class initialization thất bại

```java
public class InitFailure {
    static class Broken {
        static final int VALUE = compute();

        static int compute() {
            throw new IllegalStateException("startup failed");
        }
    }

    public static void main(String[] args) {
        try {
            Class.forName(InitFailure.class.getName() + "$Broken");
        } catch (ExceptionInInitializerError err) {
            System.out.println("initialization failed");
        }

        try {
            Class.forName(InitFailure.class.getName() + "$Broken");
        } catch (NoClassDefFoundError err) {
            System.out.println("class is erroneous");
        } catch (ClassNotFoundException err) {
            System.out.println("class not found");
        }
    }
}
```

**Đây là file Java 17 chạy độc lập** để minh họa đường lỗi. Biên dịch/chạy:

```bash
javac --release 17 InitFailure.java
java InitFailure
```

**Stdout trong một JVM chạy chương trình độc lập:**

```text
initialization failed
class is erroneous
```

Lần đầu `Class.forName` yêu cầu initialize `Broken`; static initializer thất bại, VM báo `ExceptionInInitializerError` vì lỗi nguồn là một `RuntimeException`. Sau đó cùng class/loader ở trạng thái erroneous, lần khởi tạo tiếp theo có thể báo `NoClassDefFoundError` vì nó không thể được khởi tạo thành công nữa.

Đối với ứng dụng thật, **không nên “retry” bằng cách gọi `forName` lần nữa trong cùng loader** rồi mong initializer chạy lại. Nếu cần recovery, thiết kế lifecycle và xử lý lỗi chủ động; nạp lại bằng một loader hoàn toàn khác cũng có những hệ quả về định danh kiểu và tài nguyên, không phải bản vá mặc định cho initialization bug.

## 10. Reflection: lấy metadata, khởi tạo class và tạo object là ba việc

Phân biệt các thao tác:

| Thao tác | Có yêu cầu tạo instance? | Có yêu cầu initialization? |
| --- | --- | --- |
| `Class.forName(name, false, loader)` | Không | Không |
| `loader.loadClass(name)` | Không | Không theo cơ chế thông thường |
| `type.getName()`, `type.getDeclaredMethods()` | Không | Không chỉ vì tra metadata; việc phân giải kiểu phụ thuộc có thể xảy ra |
| `Class.forName(name, true, loader)` | Không | **Có**, nếu cần |
| `type.getDeclaredConstructor().newInstance()` | **Có** | **Có**, trước khi instance được tạo/constructor chạy |
| `type.getDeclaredMethod("run").invoke(null)` với static method | Không | **Có** trước khi gọi method nếu cần |
| `field.get(null)` với static field thường | Không | Thường là active use và yêu cầu initialization |
| `SomeClass.class` | Không | Không tự khởi tạo |

Reflection không đảm bảo bypass kiểm tra truy cập. Java 9+ module boundaries có thể từ chối truy cập private internals qua `setAccessible(true)` bằng `InaccessibleObjectException`, ngay cả khi class đã tìm thấy. Và `Constructor.newInstance` có thể bao lỗi do constructor thành `InvocationTargetException`; cần xem **cause** để biết nguyên nhân thật.

### Nạp class không đồng nghĩa object “đã sẵn sàng”

Class initialization chạy một lần không có nghĩa mọi service/resource của ứng dụng đã sẵn sàng. Plugin có thể cần constructor injection, cấu hình runtime, kết nối DB hoặc lifecycle callback khác. Ngược lại, dùng `Class.forName(name, true, loader)` chỉ để kiểm tra **lớp có tồn tại hay không** có thể vô tình kích hoạt static initialization tốn thời gian hoặc nguy hiểm.

## 11. Class loader trong Java 9+ modules và các overload khác

Java 9 đưa vào hệ thống module và thêm `Class.forName(Module module, String name)`. Overload này khác với `forName(String, boolean, ClassLoader)`:

- Tìm class theo **tên** trong **module cụ thể** và có thể trả về `null` nếu không tìm thấy lớp thuộc module ấy.
- **Không khởi tạo** lớp chỉ vì lời gọi overload theo `Module`; contract của nó cũng khác về liên kết và kiểm tra visibility.
- `module` không tự động thay thế chính sách class loader do hệ thống module áp dụng; class cũng có defining loader.
- Các module có thể áp dụng **readability/exports/opens** khiến lớp có thể được tìm thấy nhưng những thao tác truy cập cụ thể vẫn bị hạn chế.

Ví dụ dùng API module (Java 17):

```java
public class ModuleLookup {
    public static void main(String[] args) {
        Module module = String.class.getModule();
        Class<?> found = Class.forName(module, "java.lang.String");
        Class<?> missing = Class.forName(module, "java.lang.DoesNotExist");

        System.out.println("found=" + (found != null));
        System.out.println("missing=" + (missing == null));
    }
}
```

```bash
javac --release 17 ModuleLookup.java
java ModuleLookup
```

**Stdout**:

```text
found=true
missing=true
```

Dùng overload này khi mục tiêu của bạn thật sự là **tìm lớp trong một module**, không đơn thuần yêu cầu initialization bằng tên class. Đừng thay thế máy móc `Class.forName(name, true, loader)` bằng `Class.forName(module, name)` rồi mong static initializer vẫn chạy.

## 12. Khi nào nên dùng API nào?

| Mục tiêu | Lựa chọn hay dùng | Lý do |
| --- | --- | --- |
| Kiểm tra/tra một class bằng tên với semantics caller loader và muốn initialization | `Class.forName(name)` | Ngắn, yêu cầu initialization |
| Quét plugin class bằng loader đã biết nhưng **chưa muốn side effect** | `Class.forName(name, false, pluginLoader)` | Có thể kiểm tra metadata trước khi initialize |
| Cần class qua custom class loader đang nắm giữ | `pluginLoader.loadClass(name)` | Dùng cơ chế loader ấy; không initialize mặc định |
| Muốn rõ ràng initialize class qua custom loader | `Class.forName(name, true, pluginLoader)` | Chọn loader và bật initialization một cách tường minh |
| Tạo instance plugin sau khi xác thực class type | `type.getDeclaredConstructor().newInstance()` | Tạo object và kích hoạt initialization nếu cần |
| Framework lookup qua TCCL | `Class.forName(name, ..., tccl)` hoặc API framework thích hợp | Tránh lệ thuộc defining loader của chính framework |
| Tìm lớp trong một Java module cụ thể | `Class.forName(module, name)` | Nhắm đúng module; không tự initialize |
| Chỉ cần class literal tại compile time | `SomeType.class` | Không cần lookup bằng chuỗi; compiler kiểm tra tên kiểu |

**Ưu tiên type-safe code** khi class đã biết ở compile time. Nạp theo tên string thích hợp cho cấu hình và plugin, nhưng làm mất kiểm tra tên/lớp ở compile time, dễ phát sinh vấn đề loader, version và lỗi runtime.

## 13. Những điểm thiết kế plugin thực tế

### Tách việc khám phá và khởi chạy

Một quy trình hợp lý:

1. Đọc cấu hình hoặc danh sách tên class plugin.
2. Chọn **đúng loader** theo kiến trúc của host, không lấy ngẫu nhiên system/app loader.
3. Nạp **chưa khởi tạo** nếu cần quét metadata: `Class.forName(name, false, pluginLoader)`.
4. Kiểm tra class implement/extends API được host dùng: `Plugin.class.isAssignableFrom(type)`.
5. Kiểm tra điều kiện khởi tạo như modifier, constructor và quyền truy cập.
6. Chủ động khởi tạo/tạo object khi ứng dụng sẵn sàng; xử lý lỗi trong phạm vi lifecycle.
7. Khởi động plugin và giải phóng resources bằng hook/framework lifecycle rõ ràng.
8. Khi unload/reload, quản lý class loader, thread, static references, TCCL và caches để tránh class loader leak.

Một mẫu thiết kế tối thiểu:

```java
Class<?> type = Class.forName(className, false, pluginLoader);
if (!Plugin.class.isAssignableFrom(type)) {
    throw new IllegalArgumentException("Not a Plugin: " + className);
}
Class<? extends Plugin> pluginType = type.asSubclass(Plugin.class);
Plugin plugin = pluginType.getDeclaredConstructor().newInstance();
plugin.start();
```

**Đây là fragment minh họa**, giả sử `Plugin` là API của host, `className`/`pluginLoader` hợp lệ, plugin có public no-arg constructor và `start()` được định nghĩa. Trong code thật cần xử lý checked exceptions, trạng thái khởi tạo thất bại, shutdown và module/access policies. `asSubclass` kiểm tra quan hệ kiểu runtime; nó không thể cứu tình huống API `Plugin` đã bị các loader khác nhau định nghĩa thành hai kiểu khác nhau.

### Đừng lạm dụng static initializer để đăng ký mọi plugin

Legacy code đôi khi gọi `Class.forName("...Driver")` chỉ để static initializer tự đăng ký provider. Cách này giải thích một số mẫu JDBC cũ, nhưng không phải cơ chế plugin phổ quát. Java hiện đại có `ServiceLoader` và các cơ chế framework riêng; chọn chúng khi cần discovery, dependency management và lifecycle chuẩn. Không dùng `Class.forName` như một “lệnh cài plugin” bất kể thư viện.

## 14. Các lỗi hiểu sai thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “`loadClass` đồng nghĩa static block chạy” | `loadClass(name)` không yêu cầu initialization |
| “`Class.forName(name)` chỉ load, không làm gì thêm” | Overload một tham số **yêu cầu initialization** |
| “Cờ `resolve=true` là cờ `initialize=true`” | Linking/resolution khác initialization |
| “`Class.forName(name)` luôn dùng TCCL” | Nó dùng loader của caller theo semantics caller-sensitive; TCCL phải được chọn tường minh nếu cần |
| “Hai class cùng tên nghĩa là cùng kiểu” | JVM còn xét **defining class loader** |
| “`Class.forName` trả về instance plugin” | Nó trả `Class<?>`; tạo object là bước riêng |
| “`SomeClass.class` luôn khởi tạo class” | Class literal không tự yêu cầu initialization |
| “Đọc mọi `static final` đều không khởi tạo class” | Chỉ những trường hợp constant variable phù hợp được xử lý theo quy tắc compile-time constant |
| “Lần nạp đầu tiên sẽ chạy `<clinit>`” | Loading và initialization là hai giai đoạn |
| “Nếu class init lỗi, `forName` lần tiếp sẽ thử lại nguyên vẹn” | Class có thể trở thành erroneous trong cùng loader; lần sau báo `NoClassDefFoundError` |
| “`ClassNotFoundException` và `NoClassDefFoundError` là cùng nguyên nhân” | Một là checked exception cho lookup, một là linkage error với nhiều nguyên nhân, kể cả prior init failure |
| “`Class.forName("int")` lấy được primitive class” | Dùng `int.class`/`Integer.TYPE`; tên primitive không được xử lý như binary class name thường |
| “`Outer.Inner` luôn là chuỗi dùng cho nested class” | Binary name thường có `Outer$Inner` |
| “`Class.forName(module, name)` luôn khởi tạo class” | Overload dùng `Module` **không** yêu cầu initialization |
| “Đã chọn một class loader thì chắc chắn nó định nghĩa class” | Parent delegation có thể trả class do loader khác định nghĩa |

## 15. Quy trình debug nạp lớp thất bại

Khi lỗi xảy ra, lần lượt kiểm tra:

1. **Tên**: giá trị string truyền vào là binary name chính xác chưa? Nested class dùng `$`? Array dùng đúng tên? Không vô tình truyền source-style `String[]`?
2. **API và cờ**: code dùng `forName(name)`, `forName(name, false, loader)` hay `loader.loadClass(name)`? Có kích hoạt initialization ngoài ý muốn không?
3. **Loader thực**: in `type.getClassLoader()` nếu đã nạp được; phân biệt app/platform/bootstrap/plugin loader và TCCL.
4. **Classpath/module path**: jar thực sự nằm đâu? Có bản duplicate? Manifest, class path, module exports/opens và launch mode có phù hợp?
5. **Thời điểm failure**: lỗi xảy ra ở loading, verification/linking, initialization hay reflection/constructor?
6. **Nested cause**: với `ExceptionInInitializerError` xem cause; với `NoClassDefFoundError` kiểm tra lỗi initialization trước đó và dependency missing.
7. **Class identity**: host và plugin có đang dùng cùng định nghĩa API interface không? Xem defining loader của cả hai.
8. **Concurrency/lifecycle**: một thread khác có đang initialize class? Static initializer có block, nắm lock, gọi I/O hoặc tạo vòng chờ?
9. **JDK version**: class-file major version có phù hợp runtime không? Ví dụ Java 17 thường là **major 61**, Java 8 là **major 52**.
10. **Sự cần thiết của reflection**: nếu có thể dùng `ServiceLoader` hoặc API type-safe, cân nhắc thay cơ chế lookup thủ công.

## 16. Câu hỏi tự kiểm tra

**Câu 1:** `ClassLoader.loadClass("demo.Plugin")` trả `Class<?>`. Chắc chắn `Plugin` đã chạy static block?

**Không.** Public `loadClass(name)` không yêu cầu initialization; việc khởi tạo là giai đoạn riêng.

**Câu 2:** `Class.forName("demo.Plugin")` có tự dùng TCCL của thread hiện tại?

**Không theo mặc định.** Nó dùng loader liên quan đến caller. Muốn dùng TCCL thì lấy và truyền vào overload ba tham số.

**Câu 3:** Hai loader định nghĩa hai class đều tên `demo.Plugin`; có thể cast object của loader này sang kiểu của loader kia chỉ dựa vào trùng tên không?

**Không.** Định danh runtime còn phụ thuộc defining loader, nên đây có thể là hai kiểu khác nhau.

**Câu 4:** `Class.forName(name, false, loader)` trả về; sau đó `getDeclaredMethod("run").invoke(null)` gọi static method. Lúc nào initialization xảy ra?

**Khi invocation yêu cầu**, nếu lớp chưa được khởi tạo trước đó; `forName(false)` không tự kích hoạt.

**Câu 5:** Đọc `SomeClass.CONSTANT` có luôn làm `SomeClass` initialize?

**Không.** Nếu trường là constant variable được truy cập theo quy tắc compile-time constant, compiler có thể inline và class chưa cần initialize.

**Câu 6:** Vì sao gọi `forName` lần hai sau một lỗi `<clinit>` có thể nhận `NoClassDefFoundError`?

**Vì class đã ở trạng thái erroneous** đối với loader ấy; JVM không bắt đầu lại initialization như mới.

**Câu 7:** `Class.forName(module, "java.lang.String")` và `Class.forName("java.lang.String")` có cùng contract initialization không?

**Không.** Overload theo module tìm trong module và không yêu cầu initialization; overload một chuỗi yêu cầu initialization.

## Tài liệu chuẩn để đối chiếu

- [JLS Java SE 17 §12.2 — Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2): ngữ nghĩa loading và class loaders.
- [JLS Java SE 17 §12.3 — Linking of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3): verification, preparation, resolution.
- [JLS Java SE 17 §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): trigger và thứ tự khởi tạo.
- [JVMS Java SE 17 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): loading, defining/initiating loader.
- [JVMS Java SE 17 §5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4): quy tắc linking.
- [JVMS Java SE 17 §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): initialization procedure và lỗi.
- [`Class` API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): các overload `forName`, `getName`, `getClassLoader`.
- [`ClassLoader` API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `resolveClass` và delegation model.
- [`ServiceLoader` API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery và class loader.
- [`ClassNotFoundException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html), [`NoClassDefFoundError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html), [`ExceptionInInitializerError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): nhận diện các đường lỗi.

**Ghi nhớ:** `Class.forName(name)` thường là “**tìm + yêu cầu khởi tạo**”; `Class.forName(name, false, loader)` là “**tìm nhưng chưa khởi tạo**”; `loader.loadClass(name)` là “**nhờ loader nạp nhưng chưa chủ động khởi tạo**”. Khi thiết kế plugin, **định danh lớp còn gồm defining class loader**, và việc có `Class<?>` không đồng nghĩa đã tạo instance hay chạy lifecycle của ứng dụng.
