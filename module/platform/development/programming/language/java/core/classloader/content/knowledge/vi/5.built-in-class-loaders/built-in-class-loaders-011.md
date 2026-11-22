# Tùy chỉnh system class loader bằng `java.system.class.loader`

Trong Java, **system class loader** là bộ nạp lớp mặc định mà `ClassLoader.getSystemClassLoader()` trả về. Ở cách khởi chạy thông thường của JDK, đó là bộ nạp lớp ứng dụng (application loader); nó thường tham gia nạp các lớp ứng dụng và là parent mặc định của `new ClassLoader()`.

Khi cần thay đổi đối tượng được dùng làm **system class loader của JVM**, có thể đặt system property `java.system.class.loader` **lúc khởi động JVM**:

```bash
java -Djava.system.class.loader=CustomSystemLoader -cp . SystemLoaderDemo
```

Trong lệnh này, `CustomSystemLoader` là **tên nhị phân đầy đủ của một lớp Java** do ứng dụng cung cấp (nếu có package thì viết cả package). JVM tìm và tạo một instance của lớp đó thông qua cơ chế quy định trong `ClassLoader.getSystemClassLoader()`; instance mới trở thành system class loader.

Đây là tính năng cấp JVM có thể tác động tới các thư viện gọi `ClassLoader.getSystemClassLoader()`, chứ không chỉ tới một lời gọi `loadClass` đơn lẻ. Vì vậy cần hiểu rõ **cơ chế khởi tạo, quan hệ parent delegation, giới hạn áp dụng và cách chẩn đoán** trước khi sử dụng.

## 1. Ba đối tượng cần phân biệt

```text
                JVM startup
                    |
                    v
      Built-in default system class loader
        (thường là application loader)
                    |
     nạp class CustomSystemLoader từ đây
                    |
     new CustomSystemLoader(defaultLoader)
                    |
                    v
          CustomSystemLoader instance
          được công bố làm system loader
                    |
       ClassLoader.getSystemClassLoader()
                    |
                    v
       trả về custom instance này
```

Chú ý quan hệ dưới đây khi constructor gọi `super(parent)`:

```text
CustomSystemLoader        <-- ClassLoader.getSystemClassLoader()
        |
        | getParent()
        v
Default built-in app loader
        |
        v
Platform loader (môi trường JDK thông thường)
        |
        v
Bootstrap loader (không có object ClassLoader Java như loader khác)
```

| Khái niệm | Vai trò |
|---|---|
| **Default system class loader** | Bộ nạp lớp tích hợp mà JVM sử dụng để tìm/nạp lớp provider `CustomSystemLoader` và truyền cho constructor của nó |
| **Custom system loader** | Instance được khởi tạo từ tên lớp trong `java.system.class.loader`, thay cho đối tượng system loader mặc định được công bố qua `getSystemClassLoader()` |
| **Defining loader của một lớp cụ thể** | Loader thực sự gọi cơ chế định nghĩa lớp runtime; có thể là parent tích hợp, dù việc `loadClass` bắt đầu từ custom loader |
| **Thread context class loader (TCCL)** | Loader gắn với từng thread, truy vấn bằng `Thread.currentThread().getContextClassLoader()`; thread có thể thay đổi context loader độc lập |
| **Bootstrap/platform loaders** | Các loader khác trong kiến trúc nạp lớp; không bị thay thế đồng loạt chỉ vì thay system loader |

**Không hiểu nhầm:** thay system loader **không tự động chuyển quyền sở hữu định nghĩa của mọi lớp** sang custom loader, và không làm thay đổi tất cả các tham chiếu `ClassLoader` đang tồn tại trong JVM.

## 2. JVM thiết lập system loader tùy chỉnh như thế nào?

Theo tài liệu `java.lang.ClassLoader.getSystemClassLoader()` (Java 17+), khi property `java.system.class.loader` đã được thiết lập tại thời điểm JVM lần đầu khởi tạo system loader, quy trình về cơ bản là:

1. JVM biết **default system class loader** do môi trường cung cấp.
2. Lấy giá trị property `java.system.class.loader` làm tên lớp provider, ví dụ `com.example.loader.CustomSystemLoader`.
3. **Nạp lớp provider bằng default system class loader**, không dùng một instance custom chưa được tạo.
4. Yêu cầu lớp provider có **public constructor nhận đúng một tham số kiểu `ClassLoader`**.
5. Gọi constructor đó và truyền vào **default system class loader**.
6. Instance được tạo trở thành **system class loader**; những lời gọi `ClassLoader.getSystemClassLoader()` sau khi thiết lập thành công trả instance đó.

Quy trình trong Java API quy định rằng tham số constructor là loader mặc định, dự kiến được dùng làm **delegation parent**. Để tuân thủ ý nghĩa đó, constructor thường gọi `super(parent)` hoặc truyền `parent` cho constructor superclass tương ứng.

### Hợp đồng constructor quan trọng

```java
public final class CustomSystemLoader extends ClassLoader {
    public CustomSystemLoader(ClassLoader parent) {
        super(parent);
    }
}
```

Đây là **lớp provider tối thiểu**, chưa thay đổi cách tìm lớp: do không override cơ chế tìm kiếm, nó kế thừa mô hình delegation mặc định của `ClassLoader`.

Điều kiện bắt buộc:

- Tên trong property phải là tên lớp mà **default system loader có thể nạp được** khi JVM khởi động.
- Constructor cần có chữ ký chính xác **`public CustomSystemLoader(ClassLoader parent)`**.
- Constructor thực hiện được thành công, và nên thiết lập parent bằng tham số JVM cấp.
- Provider phải là một `ClassLoader` hợp lệ; không thể cung cấp một lớp không kế thừa/không phải `ClassLoader`.
- Nếu provider nằm trong package, property phải chứa tên đủ package; ví dụ `-Djava.system.class.loader=com.example.loader.CustomSystemLoader`.

**Không đủ:** constructor `public CustomSystemLoader()` không tham số, một constructor `protected`, constructor nhận `URL[]` hoặc constructor nhận `Object`. Những chữ ký ấy không đáp ứng hợp đồng của property.

## 3. Ví dụ Java 17+ chạy được: thay system loader và quan sát delegation

Ví dụ gồm **hai tệp Java**, không cần Maven, Gradle hoặc thư viện bên ngoài. Bộ nạp tùy chỉnh sẽ ghi log khi được JVM tạo và khi ta yêu cầu nạp một lớp có tên `DemoTarget`. Nó **ủy quyền cho parent**, vì vậy ví dụ còn phân biệt được *loader nhận yêu cầu* và *loader thực sự định nghĩa lớp*.

### Tệp 1 — `CustomSystemLoader.java`

```java
public final class CustomSystemLoader extends ClassLoader {

    // Bắt buộc là public và nhận đúng một ClassLoader.
    public CustomSystemLoader(ClassLoader parent) {
        super(parent);
        System.out.println("CustomSystemLoader constructed");
    }

    @Override
    protected Class<?> loadClass(String name, boolean resolve)
            throws ClassNotFoundException {
        if ("DemoTarget".equals(name)) {
            System.out.println("CustomSystemLoader requested DemoTarget");
        }

        // Giữ parent-first delegation do ClassLoader cung cấp.
        return super.loadClass(name, resolve);
    }
}
```

**Giải thích:**

- JVM sẽ nạp chính lớp `CustomSystemLoader` bằng default system loader trước khi tạo custom instance.
- `super(parent)` giữ đúng parent do JVM cấp, tránh tự thiết kế lại chuỗi loader.
- Override `loadClass(String, boolean)` ở đây chỉ để quan sát yêu cầu đối với `DemoTarget`. Cuối cùng, `super.loadClass` vẫn ưu tiên lớp đã nạp hoặc parent trước khi gọi `findClass`.
- Vì `DemoTarget` ở classpath của loader tích hợp, nó được parent định nghĩa. Việc nhận yêu cầu qua custom loader không chứng minh rằng class được *defined by custom loader*.

### Tệp 2 — `SystemLoaderDemo.java`

```java
public class SystemLoaderDemo {
    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("custom system loader: "
                + (system instanceof CustomSystemLoader));

        // Yêu cầu một cách tường minh qua system loader.
        Class<?> type = system.loadClass("DemoTarget");

        System.out.println("target class: " + type.getSimpleName());
        System.out.println("defined by custom: "
                + (type.getClassLoader() == system));
        System.out.println("system has parent: "
                + (system.getParent() != null));
    }
}

// javac tạo DemoTarget.class từ lớp top-level package-private này.
class DemoTarget {
}
```

Lệnh biên dịch trong thư mục có hai file:

```bash
javac CustomSystemLoader.java SystemLoaderDemo.java
```

### Chạy bình thường, không đặt property

```bash
java -cp . SystemLoaderDemo
```

**Stdout của ví dụ trên JDK thông thường:**

```text
custom system loader: false
target class: DemoTarget
defined by custom: true
system has parent: true
```

Tại đây, `getSystemClassLoader()` là loader ứng dụng tích hợp. Biểu thức `type.getClassLoader() == system` trả `true` vì chính loader tích hợp đã nạp/định nghĩa `DemoTarget`.

### Chạy với custom system loader

```bash
java -Djava.system.class.loader=CustomSystemLoader -cp . SystemLoaderDemo
```

**Stdout dự kiến:**

```text
CustomSystemLoader constructed
custom system loader: true
CustomSystemLoader requested DemoTarget
target class: DemoTarget
defined by custom: false
system has parent: true
```

Một số bản HotSpot/JDK có thể ghi thêm **cảnh báo về CDS/Class Data Sharing ra stderr** khi dùng `java.system.class.loader`. Cảnh báo phụ thuộc runtime và **không thuộc stdout liệt kê ở trên**.

**Vì sao có dòng `defined by custom: false`?**

`system.loadClass("DemoTarget")` gọi method đã override trên custom loader, nhưng `super.loadClass` ủy quyền cho **default built-in app loader**, nơi đã nhìn thấy `DemoTarget.class` trên `-cp .`. Vì parent định nghĩa kiểu, `type.getClassLoader()` trả về parent, không phải custom instance.

Do đó:

```text
Ai nhận yêu cầu?         CustomSystemLoader
Ai trả về đối tượng Class? CustomSystemLoader.loadClass(...)
Ai định nghĩa DemoTarget? Default application loader (parent)
Ai là system loader?     CustomSystemLoader
```

Đây là một kết quả bình thường của **parent delegation**, không phải dấu hiệu thay system loader thất bại.

### Đọc đúng đầu ra

- `CustomSystemLoader constructed`: custom instance đã được tạo trong giai đoạn startup.
- `custom system loader: true`: `getSystemClassLoader()` trả về instance thuộc lớp provider.
- `CustomSystemLoader requested DemoTarget`: một lời gọi `loadClass` thật sự đi qua instance custom.
- `defined by custom: false`: parent mới là **defining loader** của `DemoTarget`.
- `system has parent: true`: custom loader giữ parent mà JVM cung cấp.

Bài học quan trọng: **thay system loader quyết định đối tượng mặc định được công bố, còn quyền định nghĩa mỗi kiểu phụ thuộc chính sách load/delegation thực tế**.

## 4. Cần làm gì để custom loader tự định nghĩa những lớp riêng?

Nếu mục tiêu là nạp plugin hoặc bytecode từ nguồn riêng, chỉ override để ghi log như ví dụ trên vẫn chưa đủ. Có thể bổ sung khả năng tìm lớp bằng cách kế thừa `URLClassLoader` hoặc tự triển khai `findClass` để đọc bytecode và gọi `defineClass`.

Ví dụ **phác thảo cấu hình**, chỉ dùng khi đã có thư mục `plugins` chứa bytecode đúng tên package:

```java
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class DirectorySystemLoader extends URLClassLoader {
    public DirectorySystemLoader(ClassLoader parent)
            throws MalformedURLException {
        super(
            "directory-system-loader",
            new URL[] { Path.of("plugins").toUri().toURL() },
            parent
        );
    }
}
```

Đây là **một provider khác**, phải lưu trong `DirectorySystemLoader.java` và biên dịch riêng; nó **không thuộc ví dụ đầu tiên**, và cần dữ liệu `plugins` tương ứng mới có tác dụng. Cấu hình:

```bash
java -Djava.system.class.loader=DirectorySystemLoader -cp . SystemLoaderDemo
```

Ý nghĩa: URLClassLoader sẽ thử parent theo chính sách ủy quyền trước. **Chỉ khi parent không tìm được tên lớp và URL loader có bytecode phù hợp**, nó mới có thể định nghĩa lớp từ URL đã cung cấp. Class đã hiện diện ở parent không tự động chuyển sang được custom loader định nghĩa. Thứ tự này giúp hạn chế việc vô tình tách một API dùng chung thành hai định nghĩa kiểu khác nhau.

Đối với bài toán plugin có vòng đời riêng, việc tạo **một URLClassLoader chuyên dụng cho plugin** thường dễ quản lý hơn so với thay system loader của cả ứng dụng. `java.system.class.loader` thích hợp khi thực sự cần thay cách các thành phần ứng dụng/framework tìm system loader mặc định.

**Vấn đề bảo vệ cần cân nhắc khi triển khai loader bytecode tùy chỉnh:** xác nhận đường dẫn/JAR tin cậy, xử lý package/sealing khi có, không tùy tiện định nghĩa lớp trong không gian package bị hạn chế, và không xem cơ chế class loader là sandbox bảo mật.

## 5. Khác gì với tạo một custom ClassLoader thông thường?

Xét hai cách cấu hình:

| Cách | Phạm vi | Ví dụ | Ưu tiên dùng khi |
|---|---|---|---|
| Tạo loader tường minh | Chỉ nơi code giữ/tham chiếu đến loader | `new URLClassLoader(urls, parent)` | Plugin, mô-đun riêng, dynamic loading có vòng đời độc lập |
| Đặt `java.system.class.loader` khi startup | Thay instance được `ClassLoader.getSystemClassLoader()` trả về | `-Djava.system.class.loader=...` | Muốn thay hành vi system loader cho chương trình/thư viện dựa vào system loader |
| Đặt thread context loader | Theo từng thread, kế thừa hoặc thay đổi theo cơ chế Thread | `Thread.currentThread().setContextClassLoader(loader)` | Service/provider lookup theo context hoặc tích hợp thư viện cần TCCL |

`new MyLoader(parent)` **không** biến nó thành system loader. `Thread.currentThread().setContextClassLoader(myLoader)` cũng **không** làm `ClassLoader.getSystemClassLoader()` đổi thành `myLoader`.

Tương tự, `System.setProperty("java.system.class.loader", "...")` bên trong `main` **không phải cách đáng tin để thay loader**: thông thường JVM đã thiết lập system loader trong quá trình khởi động. Đặt property từ lệnh `java -D...` ngay khi mở JVM.

### Liên hệ với thread context class loader

Tài liệu `ClassLoader.getSystemClassLoader()` mô tả system loader là context class loader cho main application thread khi runtime tạo nó. Nhưng context loader có thể được thay đổi độc lập:

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader context = Thread.currentThread().getContextClassLoader();
System.out.println(system == context);
```

Đoạn này chỉ minh họa kiểm tra; **không được khẳng định `true` cho mọi môi trường**: framework hoặc ứng dụng có thể đã thay TCCL. Thread pool còn có thể giữ context loader được thiết lập ở thời điểm thread tạo ra.

Nếu thư viện sử dụng `Thread.currentThread().getContextClassLoader()`, việc tùy chỉnh system loader **không bảo đảm** thư viện ấy luôn sử dụng custom loader trong mọi thread.

## 6. Các giới hạn: thay system loader không thay mọi classloader của JVM

### 6.1. Không thay bootstrap hay platform loader

`java.system.class.loader` tác động tới **system loader**; nó không làm bootstrap loader trở thành loader Java tùy chỉnh. Với `String.class`:

```java
ClassLoader loader = String.class.getClassLoader();
System.out.println(loader == null);
```

Trong JVM Java thông thường, kết quả `true` vì `java.lang.String` do bootstrap loader định nghĩa. Đây là mảnh code minh họa độc lập với đoạn demo chính.

Tương tự, các lớp nền tảng/module có thể do platform hoặc bootstrap loader phục vụ theo cơ chế runtime; không nên kỳ vọng custom system loader sẽ định nghĩa lại `java.lang.String`, `java.util.List` hay các lớp trong `java.base`.

### 6.2. “System loader được sử dụng để chạy ứng dụng” không có nghĩa mọi Class thuộc về nó

Loader thực sự định nghĩa một class có thể được kiểm tra:

```java
System.out.println(SystemLoaderDemo.class.getClassLoader());
System.out.println(DemoTarget.class.getClassLoader());
System.out.println(ClassLoader.getSystemClassLoader());
```

Đây là ba thông tin **có thể khác nhau** theo launch mode, classpath/module path, parent delegation và implementation. Không phải mọi JVM đều hiển thị cùng chuỗi `toString()` hoặc cùng tên class cho loader.

Cách so sánh đáng tin hơn với một class cụ thể:

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader defining = DemoTarget.class.getClassLoader();
boolean definedBySystem = defining == system;
```

Với custom parent-first ví dụ trên, `definedBySystem` là `false`, và đó là kết quả có chủ đích.

### 6.3. Runtime module, classpath và tính nhìn thấy kiểu

Provider phải nằm ở vị trí **default system loader** có thể tìm thấy khi khởi động. Chạy với classpath không chứa `CustomSystemLoader.class` thì JVM không thể tự “cứu” bằng custom loader, vì nó còn chưa tồn tại.

Đối với dự án modular (JPMS), còn phải xét cơ chế tìm class theo module path, module readability và khả năng truy cập. Ví dụ `-cp .` đơn giản ở trên dùng unnamed module nên tránh các ràng buộc module phức tạp. Không áp dụng nguyên xi mọi ví dụ classpath cho chương trình đóng gói thành named modules hoặc custom runtime image.

### 6.4. Framework/JAR launcher có thể quản lý loader riêng

Một ứng dụng chạy bằng launcher riêng, nested JAR hoặc framework có thể thiết lập classloader và TCCL riêng. Việc chỉ đặt `java.system.class.loader` **không bảo đảm** thay cơ chế nạp mọi thư viện/framework. Hãy xác định thư viện đang gọi:

- `ClassLoader.getSystemClassLoader()`;
- `Thread.currentThread().getContextClassLoader()`;
- `SomeClass.class.getClassLoader()`;
- hoặc một loader do framework tự giữ.

Mỗi cách có thể trả đối tượng khác nhau trong cùng một tiến trình.

### 6.5. Quy tắc parent-first không phải bắt buộc cho mọi loader tùy biến

`ClassLoader.loadClass` mặc định dùng delegation, nhưng subclass có thể thay chính sách. Child-first giúp nạp phiên bản thư viện riêng, song dễ gặp lỗi type identity/`ClassCastException`/`LinkageError` nếu cùng API được định nghĩa hai lần.

Với system loader, thay chính sách quá rộng có thể tác động các thư viện vốn mong các kiểu phổ biến được chia sẻ qua parent. Nên giới hạn override ở những package đã xác định, dùng hợp đồng type chung từ loader cha khi cần.

## 7. Những lỗi khởi động thường gặp

### 7.1. Không tìm thấy lớp provider

Ví dụ chạy:

```bash
java -Djava.system.class.loader=com.example.Missing -cp . SystemLoaderDemo
```

Khi property đã khai báo nhưng lớp không thể nạp, theo `getSystemClassLoader()` JVM có thể ném một **`Error`**, thường kèm nguyên nhân gốc trong `getCause()`. Kiểm tra chính tả tên nhị phân, package, classpath/module path, phiên bản bytecode và tính sẵn có của class provider.

**Không chờ tới khi `main` chạy mới phát hiện:** vì setup diễn ra ở quá trình startup, chương trình có thể dừng **trước `main`**.

### 7.2. Constructor sai chữ ký

```java
// Sai hợp đồng java.system.class.loader:
public CustomSystemLoader() {
    super();
}
```

Đây chỉ là mảnh minh họa chữ ký **không hợp lệ cho provider**. JVM cần đúng `public CustomSystemLoader(ClassLoader parent)`. Nếu constructor phù hợp không tồn tại hoặc không public, tạo system loader thất bại và lỗi có thể xuất hiện trước `main`.

### 7.3. Constructor ném exception

```java
public CustomSystemLoader(ClassLoader parent) {
    super(parent);
    throw new IllegalStateException("bad configuration");
}
```

Đây là mảnh minh họa lỗi, **không phải code nên sử dụng**. Theo JDK API, thất bại từ constructor dẫn tới `Error` ở lúc tạo system loader, với nguyên nhân gốc có thể truy ra từ `getCause()`. Tránh làm quá nhiều logic nặng, phụ thuộc cấu hình chưa sẵn sàng hoặc load plugin phức tạp ngay trong constructor.

### 7.4. Gọi `getSystemClassLoader()` trong constructor: vòng khởi tạo

```java
public CustomSystemLoader(ClassLoader parent) {
    super(parent);

    // SAI: system loader đang được tạo, có nguy cơ vòng khởi tạo.
    ClassLoader wrong = ClassLoader.getSystemClassLoader();
}
```

Đoạn này là **ví dụ phản diện**, không biên dịch độc lập. JDK quy định nếu phát hiện gọi đệ quy lúc đang tạo system loader từ property, JVM ném `IllegalStateException`. Thay vì gọi `getSystemClassLoader()`, constructor đã có **parent** mà JVM cung cấp.

Một sai lầm tương tự là dùng constructor `super()` không tham số. Constructor này mặc định tìm `getSystemClassLoader()` làm parent, nên có thể kích hoạt đúng đường vòng đang cần tránh. **Luôn dùng `super(parent)` cho provider đơn giản.**

### 7.5. Đổi property sau khi khởi động

```java
System.setProperty(
    "java.system.class.loader", "OtherSystemLoader");
```

Không xem thao tác trên là thay instance system loader đã thiết lập. Hợp đồng `getSystemClassLoader()` kiểm tra property khi khởi tạo system loader; thao tác `setProperty` về sau chỉ thay dữ liệu property, không phải API “hot swap” toàn bộ loader.

### 7.6. Lỗi cast khi dùng lại class cùng tên

Giả sử `com.example.Api` đã được parent định nghĩa, nhưng custom loader lại tự định nghĩa thêm một kiểu mang đúng tên đó. Java coi chúng là **hai kiểu khác nhau** nếu defining loader khác. Cast, method linkage hoặc interface assignment có thể thất bại dù log in cùng class name.

Khi chẩn đoán, log cả tên và loader:

```java
Class<?> type = obj.getClass();  // obj phải khác null
System.out.println(type.getName());
System.out.println(type.getClassLoader());
```

Không coi `ClassLoader.getSystemClassLoader() == type.getClassLoader()` là điều mặc định phải đúng.

## 8. Khi nào nên chọn `java.system.class.loader`?

**Nên cân nhắc** khi cần một instance system loader có hành vi khác với bộ nạp lớp mặc định và các thành phần liên quan **thực sự truy cập qua system loader**: instrumentation/development tooling đặc thù, một runtime tích hợp phức tạp, hoặc ứng dụng chủ động xây dựng lớp tải mặc định có kiểm soát.

**Nên dùng loader tường minh trước** nếu chỉ cần đọc plugin JAR từ một thư mục, cô lập một extension, hoặc tải lớp theo yêu cầu trong một phần ứng dụng. Cách này giới hạn tác động và thuận lợi cho vòng đời unload: sử dụng `URLClassLoader` và đóng tài nguyên thích hợp khi không dùng nữa, giải phóng mọi tham chiếu đến class/loader/thread/context nếu muốn có cơ hội unload.

Một checklist quyết định:

1. Thư viện cần thay **có gọi `getSystemClassLoader()`** không, hay dùng TCCL/custom loader?
2. Có cần thay loader **ngay khi startup** không?
3. Provider có thể được default system loader nạp và có **public constructor(ClassLoader)** đúng không?
4. Chính sách ủy quyền sẽ giữ **các API dùng chung** ở parent chứ?
5. Có kế hoạch kiểm chứng đường nạp trong môi trường packaging thực tế (classpath, modules, Spring Boot launcher, test runner) không?
6. Lỗi của custom loader có khiến cả JVM khởi động thất bại không, và ứng dụng có chấp nhận rủi ro đó không?

Nếu câu trả lời chủ yếu là “chỉ muốn load plugin theo đường dẫn riêng”, việc thay global system loader thường không cần thiết.

## 9. Kiểm chứng bằng những công cụ sẵn có của JVM

### Xác định system loader đang dùng

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();
System.out.println(loader.getClass().getName());
System.out.println(loader.getParent());
```

Kết quả phụ thuộc VM; phần class name và parent cung cấp bằng chứng tốt hơn việc nhìn giá trị property đơn thuần. Trong ví dụ của bài, custom loader tự in log khi được JVM xây dựng.

### Xác định class được loader nào định nghĩa

```java
Class<?> type = Class.forName(
        "DemoTarget",
        false,
        ClassLoader.getSystemClassLoader());

System.out.println(type.getClassLoader());
```

Đây là mảnh code minh họa sử dụng Class có sẵn trong hai-file demo. `Class.forName(name, false, loader)` chủ động tra cứu/nạp và liên kết nhưng không yêu cầu initialize lớp; phần `getClassLoader()` trả về **defining loader**, không phải chắc chắn loader được truyền vào.

### Ghi log hoạt động tải lớp trên HotSpot

```bash
java -Xlog:class+load=info -Djava.system.class.loader=CustomSystemLoader -cp . SystemLoaderDemo
```

HotSpot có thể ghi log kiểu đã nạp và nguồn nạp. Nội dung/thứ tự chi tiết khác nhau giữa các bản Java và launcher; các log này là công cụ chẩn đoán, không phải stdout cố định của ví dụ học tập.

### Thử tình huống lỗi có kiểm soát

Có thể thay tạm property bằng tên provider không tồn tại để xem lỗi khởi động, rồi trở về ví dụ hợp lệ. Không cần sửa mã nguồn `SystemLoaderDemo`; vấn đề nằm ở property/tính tìm thấy provider.

## 10. Các ngộ nhận phổ biến

1. **“`java.system.class.loader` là tên class loader Java đã tồn tại sẵn.”** Sai. Giá trị là **tên lớp provider**, JVM nạp nó bằng default loader và gọi constructor phù hợp để tạo instance.
2. **“Chỉ cần subclass `ClassLoader` là đủ.”** Chưa đủ. Provider phải có **public constructor(ClassLoader)**.
3. **“Custom provider tự nạp chính bản thân mình.”** Sai. JVM nạp provider bằng **default system loader** trước khi tạo custom instance.
4. **“System loader mới bắt buộc phải tự định nghĩa mọi class ứng dụng.”** Sai. Parent-first delegation có thể để parent định nghĩa class.
5. **“`loadClass` được gọi qua custom, nên `clazz.getClassLoader()` phải bằng custom.”** Sai. `getClassLoader()` trả defining loader; caller/initiating loader có thể khác.
6. **“Đặt `System.setProperty` trong `main` là đổi system loader.”** Sai. System loader thường đã được tạo trước `main`; phải đặt property khi JVM startup.
7. **“Dùng `super()` trong provider constructor vẫn ổn như `super(parent)`.”** Có nguy cơ vòng khởi tạo vì `super()` tìm system loader làm parent. Dùng tham số `parent` được truyền.
8. **“Property này thay bootstrap/platform loader.”** Sai. Nó chọn system loader; các tầng loader còn lại vẫn có vai trò riêng.
9. **“TCCL của mọi thread luôn bằng system loader.”** Sai. TCCL gắn với từng thread và có thể được ứng dụng/framework thay đổi.
10. **“Tính năng này là hot reload class toàn JVM.”** Sai. Thay system loader ở startup không tự tải lại định nghĩa lớp đã có; hot reload/redefinition là cơ chế khác với điều kiện riêng.
11. **“Không có rủi ro nếu constructor làm việc phức tạp.”** Sai. Lỗi nạp provider, sai constructor hoặc khởi tạo vòng có thể chặn startup trước `main`.
12. **“Custom system loader mặc định có quyền mở mọi package/module.”** Sai. Việc truy cập module/bytecode và phân giải kiểu vẫn chịu quy tắc JVM, module và visibility.

## 11. Tự kiểm tra

**Câu 1.** `CustomSystemLoader` cần constructor nào để JVM chọn bằng `-Djava.system.class.loader=CustomSystemLoader`?

**Đáp án:** `public CustomSystemLoader(ClassLoader parent)`. Lớp provider phải được default system loader tìm thấy; constructor dùng parent đó làm delegation parent.

**Câu 2.** Tại sao `system.loadClass("DemoTarget")` trong ví dụ chạy custom loader nhưng `type.getClassLoader() == system` lại là `false`?

**Đáp án:** Vì `super.loadClass` ủy quyền tìm `DemoTarget` cho parent tích hợp; parent định nghĩa lớp và trở thành defining loader. Custom chỉ khởi đầu và trả kết quả của lời gọi.

**Câu 3.** Có thể gọi `System.setProperty("java.system.class.loader", "...")` sau khi chạy `main` để đổi system loader tức thì không?

**Đáp án:** Không. Java không cung cấp cơ chế thay instance system loader bằng việc sửa property sau khi nó đã được thiết lập.

**Câu 4.** Trong constructor provider, tại sao nên dùng `super(parent)` và tránh gọi `ClassLoader.getSystemClassLoader()`?

**Đáp án:** Vì instance system loader mới đang được tạo; lấy system loader đệ quy có thể kích hoạt `IllegalStateException`. Constructor đã nhận sẵn default loader cần dùng làm parent.

**Câu 5.** Một thư viện gọi `Thread.currentThread().getContextClassLoader()` nhưng vẫn dùng loader cũ. Đã chắc property không hoạt động chưa?

**Đáp án:** Chưa. TCCL là trạng thái theo từng thread và có thể bị framework/app thay đổi; phải kiểm tra TCCL, system loader và defining loader riêng biệt.

**Câu 6.** Bạn muốn tải một plugin JAR khác đường dẫn mà không thay class loading mặc định của ứng dụng. Nên ưu tiên lựa chọn nào?

**Đáp án:** Một custom/`URLClassLoader` chuyên biệt được truyền tường minh tới thành phần plugin, thay vì thay global system loader chỉ cho nhu cầu cục bộ.

## 12. Sơ đồ ra quyết định

```text
Cần nạp class từ nguồn / đường dẫn tùy chỉnh?
                         |
                         v
     Có thành phần nào bắt buộc dùng getSystemClassLoader()
          và cần tác động trên toàn ứng dụng không?
              /                         \
            Không                        Có
              |                          |
   Tạo loader chuyên biệt          Đặt property lúc startup
   và dùng trực tiếp                 java.system.class.loader
              |                          |
   Quản lý plugin/lifecycle       Provider tìm được bởi default loader?
                                      |
                                      v
                              public constructor(ClassLoader)?
                                      |
                                      v
                              super(parent), thiết kế delegation
                                      |
                                      v
                                Chạy demo/quan sát loader
                                và defining loader thực tế
```

**Ghi nhớ ba ý chính:** `java.system.class.loader` chọn **instance system loader được công bố**, JVM tạo instance qua **public constructor(ClassLoader parent)** và truyền **default system loader** làm parent, còn **loader nào thực sự định nghĩa từng lớp** phụ thuộc cách ủy quyền và tìm bytecode. Nắm vững ba điểm này sẽ tránh được phần lớn sai lầm khi đổi loader cấp ứng dụng.

### Tài liệu tham khảo

- [Java SE 17 — ClassLoader.getSystemClassLoader()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getSystemClassLoader())
- [Java SE 21 — ClassLoader API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
