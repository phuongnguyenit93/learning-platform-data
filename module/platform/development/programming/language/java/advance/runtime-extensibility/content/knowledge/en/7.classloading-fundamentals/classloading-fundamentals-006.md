# Nạp lớp từ URLClassLoader và chuyển về kiểu hợp đồng dùng chung

## 1. Bài toán: host không biên dịch trực tiếp với lớp plugin

Một ứng dụng có thể cần tải thêm hành vi từ một JAR nằm bên ngoài lúc khởi động hoặc khi người dùng cài plugin. Host không nên phải import và biên dịch lại mỗi khi có một implementation mới. Thay vào đó, **host và plugin cùng hiểu một hợp đồng Java**, chẳng hạn interface GreetingPlugin; host dùng URLClassLoader để tìm class trong JAR và tạo instance, sau đó gọi instance thông qua interface chung.

Ví dụ một plugin cung cấp class **example.impl.VietnameseGreeter**, còn ứng dụng chỉ biết **example.ext.Greeter**:

~~~text
Host (biết interface Greeter)
          |
          | tìm JAR và tên class plugin từ cấu hình
          v
URLClassLoader -> example.impl.VietnameseGreeter
          |
          | kiểm tra implements Greeter, tạo instance
          v
Greeter greeter -> greeter.greet("Java")
~~~

Điều quan trọng là **hai phía dùng cùng một Class object của interface Greeter**, do class loader chung (thường là parent của plugin loader) cung cấp. Trong JVM, tên lớp giống nhau chưa đủ để bảo đảm một đối tượng ép kiểu được: **danh tính của một class gắn với tên binary và class loader đã định nghĩa nó**.

Bài này thực hiện lần lượt: tạo hợp đồng chung, đóng gói provider riêng thành JAR, dựng URLClassLoader, nạp lớp chưa biết tại thời điểm biên dịch, kiểm tra hợp đồng, chuyển về kiểu có kiểm tra và sử dụng instance. Sau đó phân tích lỗi thường gặp và cách quản lý vòng đời.

## 2. Phân biệt ba vai trò khi nạp lớp

| Thành phần | Vai trò | Ai nhìn thấy khi biên dịch? |
|---|---|---|
| **API/SPI hợp đồng** | Interface Greeter định nghĩa phương thức chung | Cả host và plugin |
| **Plugin implementation** | Class VietnameseGreeter implements Greeter | Plugin; host không import trực tiếp |
| **Host/Plugin Loader** | Biết đường dẫn JAR, FQN class, kiểm tra và khởi tạo implementation | Host; nó chỉ cần interface |

**API (Application Programming Interface)** là thứ code host sử dụng; khi làm điểm mở rộng, hợp đồng mà provider phải triển khai thường được gọi là **SPI (Service Provider Interface)**. Ở ví dụ này, cùng một interface Greeter đóng cả hai vai trò. Đặt interface trong thư viện API nhỏ và ổn định, được host nạp trước và cho plugin tham chiếu.

**URLClassLoader** nhận các URL đến **JAR** hoặc **thư mục chứa các file .class theo cấu trúc package**, rồi tìm class/resource trong đó. Nó là một ClassLoader, nghĩa là có cơ chế ủy quyền cho parent. Constructor thường dùng:

~~~java
// Mảnh minh họa: Greeter là interface dùng chung, jarUrl trỏ tới plugin JAR.
URLClassLoader pluginLoader = new URLClassLoader(
        new URL[] { jarUrl },
        Greeter.class.getClassLoader()
);
~~~

- Tham số đầu là danh sách URL của plugin/dependency cần nạp; với JAR trên đĩa, nên tạo bằng **Path.toUri().toURL()**.
- Tham số thứ hai là **parent loader**, ở đây chính loader đã nạp hợp đồng Greeter. Cách này tránh để plugin dùng một bản Greeter tách biệt với bản host đang sử dụng.
- Theo cơ chế mặc định, URLClassLoader **hỏi parent trước** rồi mới tìm trên URL của nó; đây là *parent-first delegation*. Nếu class implementation đã hiện diện trong parent classpath, parent có thể trả về class ấy, không phải bản trong JAR mới.

Việc nạp class từ JAR không tự tạo instance. Lệnh **loadClass(name)** trả về một **Class<?>**, chưa phải một **Greeter**.

## 3. Vì sao cùng tên class vẫn có thể không ép kiểu được?

JVM phân biệt các kiểu reference thông qua **class/interface được định nghĩa bởi class loader nào**. Hình dung có hai loader độc lập:

~~~text
AppLoader                     IsolatedPluginLoader
  |                                  |
  +-- example.ext.Greeter            +-- example.ext.Greeter
       (Class object A)                   (Class object B)
~~~

Hai interface cùng tên binary **example.ext.Greeter** nhưng do hai defining loader khác nhau định nghĩa: **A != B**. Class plugin implements interface B sẽ **không phải** là một instance của interface A trong mắt host. Việc viết package, method và chữ ký trông hoàn toàn giống nhau không khắc phục được khác biệt này.

Các lỗi thường thấy:

- **ClassCastException** khi host ép instance sang Greeter của mình.
- **Class.asSubclass(Greeter.class)** báo ClassCastException vì implementation không assignable tới interface do host biết.
- Có thể xuất hiện thông điệp dạng *X cannot be cast to X* khi hai Class khác nhau nhưng cùng tên binary bị nạp qua loader khác nhau.
- Khi host gọi reflective method với tham số là kiểu API thuộc loader khác, có thể gặp IllegalArgumentException hoặc lỗi liên kết.

Thiết kế loader phù hợp thường là:

~~~text
Application/Shared API ClassLoader
  +-- example.ext.Greeter        <-- chỉ một định nghĩa chung
  +-- example.host.PluginHost
  |
  +-- child URLClassLoader
        +-- example.impl.VietnameseGreeter
              implements Greeter từ parent
~~~

**Điểm kiểm tra quyết định:** **Greeter.class.isAssignableFrom(rawClass)** phải trả true, hoặc dùng trực tiếp **rawClass.asSubclass(Greeter.class)** để chuyển Class<?> sang Class<? extends Greeter> có kiểm tra runtime. Nếu không đúng, đừng cố cast mù hoặc gọi setAccessible(true) để “vượt” qua ràng buộc kiểu.

## 4. Ví dụ đầy đủ Java 17: nạp provider JAR, chuyển sang interface, gọi nghiệp vụ

Ví dụ độc lập này cố ý dùng một plugin JAR **không nằm trên classpath của host**. Host chỉ biết đường dẫn JAR, tên binary class và interface Greeter. Cách xây dựng bằng JDK thuần giúp kiểm tra trực tiếp hành vi của URLClassLoader, không cần Spring hoặc thư viện plugin nào.

### 4.1. Cấu trúc thư mục

Tạo cây thư mục sau từ một thư mục làm việc trống, ví dụ **urlclassloader-demo**:

~~~text
urlclassloader-demo/
├── api/
│   └── src/
│       └── example/ext/Greeter.java
├── plugin/
│   └── src/
│       └── example/impl/VietnameseGreeter.java
├── host/
│   └── src/
│       └── example/host/PluginHost.java
└── build/                         # sẽ tạo bằng lệnh biên dịch
    ├── api/
    ├── plugin/
    ├── host/
    └── vietnamese-greeter.jar
~~~

Ba nhóm nguồn được tách riêng để làm rõ phụ thuộc. Hợp đồng API được biên dịch trước; implementation plugin dùng API đó; host cũng dùng API đó nhưng không được đưa JAR plugin vào classpath khi chạy.

### 4.2. Tạo hợp đồng trong API

**Tệp api/src/example/ext/Greeter.java**:

~~~java
package example.ext;

public interface Greeter {
    String greet(String name);
}
~~~

Host biên dịch dựa vào đúng interface này. Plugin cũng biên dịch dựa vào interface, nhưng JAR plugin ở bước sau sẽ **chỉ chứa implementation**, không đóng gói lại Greeter.class.

Trong thực tế, interface nên có JavaDoc về giá trị null, lỗi, tính thread-safe, lifecycle và phiên bản API hỗ trợ. Ví dụ giữ đơn giản để tập trung vào class loader và ép kiểu.

### 4.3. Tạo implementation trong plugin

**Tệp plugin/src/example/impl/VietnameseGreeter.java**:

~~~java
package example.impl;

import example.ext.Greeter;

public final class VietnameseGreeter implements Greeter {
    public VietnameseGreeter() {
        // Public no-arg constructor để host gọi qua reflection.
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Plugin class là **public**, implements Greeter và có **public constructor không tham số**. Đây là những điều kiện cho cách tạo đối tượng bằng **getConstructor().newInstance()** ở ví dụ; chúng không phải điều kiện bắt buộc cho mọi mô hình plugin. Một plugin có dependency/constructor arguments có thể dùng factory do host gọi theo hợp đồng khác.

### 4.4. Host tạo loader, kiểm tra và chuyển kiểu

**Tệp host/src/example/host/PluginHost.java**:

~~~java
package example.host;

import example.ext.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PluginHost {
    private static final String IMPLEMENTATION_CLASS =
            "example.impl.VietnameseGreeter";

    public static void main(String[] args) throws Exception {
        Path jar = Path.of("build", "vietnamese-greeter.jar")
                .toAbsolutePath();

        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException("Plugin JAR not found: " + jar);
        }

        URL[] locations = { jar.toUri().toURL() };
        ClassLoader apiLoader = Greeter.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                new URLClassLoader(locations, apiLoader)) {

            // Bước 1: nạp mô tả class, chưa tạo instance plugin.
            Class<?> rawClass =
                    pluginLoader.loadClass(IMPLEMENTATION_CLASS);

            // Bước 2: kiểm tra class do ai định nghĩa và có đúng hợp đồng.
            System.out.println("Loaded by plugin loader: "
                    + (rawClass.getClassLoader() == pluginLoader));
            System.out.println("Implements shared Greeter: "
                    + Greeter.class.isAssignableFrom(rawClass));

            // Bước 3: chuyển Class<?> thành Class<? extends Greeter>.
            Class<? extends Greeter> pluginClass =
                    rawClass.asSubclass(Greeter.class);

            // Bước 4: khởi tạo bằng public no-arg constructor.
            Greeter plugin = pluginClass.getConstructor().newInstance();

            // Bước 5: từ đây host chỉ cần biết kiểu Greeter.
            System.out.println(plugin.greet("Java"));
        }
    }
}
~~~

Giải thích từng ranh giới:

1. **Path.toUri().toURL()** tạo URL file hợp lệ kể cả khi đường dẫn chứa khoảng trắng; tránh tự ghép chuỗi **file:** thiếu escape.
2. **Greeter.class.getClassLoader()** là loader của API mà host đã biên dịch với nó. Đây là parent của plugin loader.
3. **pluginLoader.loadClass("example.impl.VietnameseGreeter")** trả Class<?>. Tên cần là **fully qualified binary name**, không phải tên file .java, .class hay đường dẫn slash.
4. **isAssignableFrom** kiểm tra subclass/implements ở runtime. Với interface, nó trả true nếu class được kiểm tra implements interface ấy trực tiếp hoặc gián tiếp, với đúng danh tính kiểu.
5. **asSubclass** kiểm tra lần nữa và cho giá trị có kiểu **Class<? extends Greeter>**. Nếu sai, nó ném **ClassCastException** thay vì để host tạo một đối tượng không tương thích.
6. **getConstructor().newInstance()** tìm constructor **public** không tham số và tạo object. Đó là lúc khởi tạo class/instance cần thiết được thực thi; constructor hoặc static initialization của plugin có thể gây lỗi.
7. Phương thức **greet** được gọi qua interface; host không cần import VietnameseGreeter hoặc reflective invocation của method greet.
8. **try-with-resources** đóng URLClassLoader khi đã dùng xong trong ví dụ. Việc đóng loader không có nghĩa Java GC ngay mọi class hay object đã được nạp.

### 4.5. Biên dịch và đóng gói, không đưa plugin JAR vào host classpath

Từ thư mục **urlclassloader-demo**, chạy trên Linux/macOS (bash):

~~~bash
mkdir -p build/api build/plugin build/host

javac --release 17 -encoding UTF-8 -d build/api \
  api/src/example/ext/Greeter.java

javac --release 17 -encoding UTF-8 -cp build/api -d build/plugin \
  plugin/src/example/impl/VietnameseGreeter.java

jar --create --file build/vietnamese-greeter.jar -C build/plugin .

javac --release 17 -encoding UTF-8 -cp build/api -d build/host \
  host/src/example/host/PluginHost.java

java -cp build/api:build/host example.host.PluginHost
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/api, build/plugin, build/host | Out-Null

javac --release 17 -encoding UTF-8 -d build/api api/src/example/ext/Greeter.java

javac --release 17 -encoding UTF-8 -cp build/api -d build/plugin plugin/src/example/impl/VietnameseGreeter.java

jar --create --file build/vietnamese-greeter.jar -C build/plugin .

javac --release 17 -encoding UTF-8 -cp build/api -d build/host host/src/example/host/PluginHost.java

java -cp "build/api;build/host" example.host.PluginHost
~~~

Chú ý **dấu phân cách classpath**: **:** ở Linux/macOS và **;** ở Windows. Tham số của Java **-cp** chỉ chứa **build/api** và **build/host**, không có JAR plugin. Plugin được tìm qua URL truyền vào URLClassLoader, chính là trọng tâm bài học.

**Stdout dự kiến chính xác** với JDK 17+ và cây tệp như trên:

~~~text
Loaded by plugin loader: true
Implements shared Greeter: true
Xin chào, Java!
~~~

Giá trị true đầu tiên xuất hiện vì **VietnameseGreeter** chỉ có trong JAR plugin, do child URLClassLoader định nghĩa. Giá trị true thứ hai xuất hiện vì class được biên dịch để implements **cùng Greeter interface** do parent cung cấp. Dòng cuối xác nhận host sử dụng được instance qua hợp đồng chung.

**Nếu chạy trên console có thiết lập mã hóa khác UTF-8**, ký tự tiếng Việt có thể hiển thị sai dù logic Java đúng; lệnh biên dịch dùng **-encoding UTF-8** để lưu đúng literal trong bytecode.

### 4.6. Kiểm tra JAR có đúng class không

Để liệt kê mục trong JAR (lệnh tương tự trên cả hai hệ điều hành):

~~~bash
jar --list --file build/vietnamese-greeter.jar
~~~

Nội dung phải có **example/impl/VietnameseGreeter.class**. Vì lệnh đóng gói lấy nội dung từ **build/plugin**, ví dụ không đưa **example/ext/Greeter.class** vào JAR. Điều này bảo đảm host là nơi cung cấp một API chung, thay vì plugin tự mang bản hợp đồng riêng.

## 5. Vì sao nên dùng asSubclass thay vì ép kiểu Class tùy tiện?

Giá trị từ **loadClass** có kiểu **Class<?>**; compiler không thể biết trước nó có implements Greeter hay không. Đoạn sau không bảo đảm an toàn:

~~~java
// Mảnh mã minh họa cách làm cần tránh:
Class<?> raw = pluginLoader.loadClass("example.impl.VietnameseGreeter");

// Cách cast Class trực tiếp không có kiểm tra kiểu tại compile-time
// đủ mạnh; dễ dẫn đến unchecked warning nếu ép sang Class<Greeter>.
// Class<Greeter> cũng không biểu diễn mọi subclass của Greeter.
@SuppressWarnings("unchecked")
Class<Greeter> unchecked = (Class<Greeter>) raw;
~~~

Hãy dùng:

~~~java
// Mảnh mã minh họa; biến pluginLoader có sẵn trong khối try.
Class<?> raw = pluginLoader.loadClass("example.impl.VietnameseGreeter");
Class<? extends Greeter> typed = raw.asSubclass(Greeter.class);
Greeter result = typed.getConstructor().newInstance();
~~~

Các khác biệt quan trọng:

- **Greeter.class.isAssignableFrom(raw)** trả boolean để bạn có thể kiểm tra hoặc tạo thông báo lỗi.
- **raw.asSubclass(Greeter.class)** trực tiếp thực hiện phép kiểm tra kiểu và trả Class<? extends Greeter>, phù hợp với cả một class triển khai interface qua các lớp cha.
- **Greeter.class.cast(object)** dùng khi đã có Object và muốn cast **instance** có kiểm tra runtime; không thay thế bước chuyển kiểu Class khi bạn cần một typed Class trước khi tạo instance.
- **(Greeter) object** cũng có kiểm tra runtime nhưng không giúp làm rõ vấn đề giữa nhiều loader và không cung cấp thông tin cho API reflection sớm bằng asSubclass.

Ví dụ tương đương khi tạo instance trước rồi mới cast:

~~~java
// Mảnh minh họa: hợp lệ, nhưng lỗi kiểu xuất hiện muộn hơn.
Object object = raw.getConstructor().newInstance();
Greeter plugin = Greeter.class.cast(object);
~~~

**Không dùng Class.newInstance()**: phương thức cũ đã deprecated từ Java 9; ưu tiên **getConstructor().newInstance()** nếu constructor public, hoặc một factory được thiết kế rõ ràng. Không gọi **setAccessible(true)** mặc định vì một plugin production nên công bố entry point có quyền truy cập hợp lệ, đồng thời không phá nguyên tắc encapsulation.

## 6. Nạp lớp, khởi tạo class và tạo đối tượng là những bước khác nhau

Phân biệt:

| Thao tác | Điều gì xảy ra |
|---|---|
| **pluginLoader.loadClass(fqn)** | Yêu cầu tìm/nạp class theo tên, thường **không khởi tạo class** |
| **Class.forName(fqn, false, pluginLoader)** | Yêu cầu nạp/liên kết với khởi tạo class đặt **false** |
| **Class.forName(fqn, true, pluginLoader)** | Yêu cầu cả **khởi tạo class** (có thể chạy static initializer) |
| **rawClass.asSubclass(Greeter.class)** | Kiểm tra quan hệ kiểu và thu hẹp kiểu Class, **không tạo instance** |
| **typed.getConstructor().newInstance()** | Gọi constructor để tạo instance; class được khởi tạo khi cần thiết |
| **plugin.greet(...)** | Chạy nghiệp vụ qua hợp đồng chung |

Mã **loadClass** có thể gây nạp các lớp liên quan, đọc dữ liệu JAR và lỗi liên kết; “chưa tạo instance” không đồng nghĩa “không phát sinh side effect/chi phí”. Static initializer sẽ chạy khi JVM khởi tạo class theo quy tắc của Java, chẳng hạn trước lần tạo instance đầu tiên nếu class chưa được khởi tạo.

Nếu một plugin đòi hỏi cấu hình, token, dependency hoặc constructor tham số, không cố áp đặt public no-arg constructor. Một hợp đồng **PluginFactory** hoặc một static factory entry point có phương thức/chữ ký được thống nhất trước sẽ thích hợp hơn. Vẫn cần **chuyển kiểu về API chung** trước khi cho host gọi nghiệp vụ.

## 7. Parent-first delegation và những điểm gây lỗi

### 7.1. Phải chọn parent để chia sẻ hợp đồng

Trong ví dụ, dùng:

~~~java
ClassLoader parent = Greeter.class.getClassLoader();
URLClassLoader loader = new URLClassLoader(
        new URL[] { pluginJar.toUri().toURL() },
        parent
);
~~~

Parent **phải nhìn thấy và cung cấp đúng Greeter** mà host dùng. Nếu chọn parent chỉ thấy các class của JDK và URL plugin lại chứa một bản Greeter khác, có thể tạo hai kiểu có tên giống nhau nhưng không cast qua lại được.

Một trường hợp đặc biệt là **Greeter** do bootstrap loader nạp, **Greeter.class.getClassLoader()** có thể là null; URLClassLoader cho phép parent null, nhưng nó không phù hợp nếu còn các shared API khác chỉ parent ứng dụng nhìn thấy. Khi làm plugin host thực tế, hãy xác định toàn bộ ranh giới API và parent cho đúng.

### 7.2. Parent-first cũng có thể khiến “plugin mới” không được dùng

Nếu command khởi động host vô tình thêm plugin JAR vào **application classpath**, parent có thể nạp luôn VietnameseGreeter. Khi đó:

~~~java
rawClass.getClassLoader() == pluginLoader
~~~

có thể trả **false**. Class vẫn implements Greeter, nhưng không được định nghĩa bởi URLClassLoader mới như bạn mong đợi. Hãy kiểm tra classpath của host và **ProtectionDomain/CodeSource** khi cần xác định class được lấy từ đâu.

### 7.3. Không tự ý chuyển sang child-first cho toàn bộ package

Framework plugin đôi khi cần **child-first** để cô lập phiên bản thư viện phụ thuộc. Tuy nhiên nếu cũng ưu tiên child-first cho package API chung, plugin có thể định nghĩa lại Greeter và làm hỏng khả năng cast.

Một chính sách loader nâng cao thường **parent-first cho các package API/JDK**, rồi mới cân nhắc child-first cho một số package implementation/dependency đã xác định. URLClassLoader mặc định không thực hiện chính sách tùy biến này cho bạn; cần thiết kế, kiểm thử và xem xét xung đột package cẩn thận nếu tạo custom ClassLoader.

### 7.4. Vì sao copy cùng interface class vào JAR plugin là một mùi thiết kế?

Trong ví dụ parent-first, một bản Greeter.class lỡ bị đóng gói trong JAR có thể vẫn bị bỏ qua khi parent tìm thấy bản tương ứng; vì thế **không phải cứ có file trùng trong JAR là cast lập tức thất bại**. Nhưng việc phân phối API trùng:

- làm khó kiểm soát version của hợp đồng,
- tăng nguy cơ nhầm loader khi chuyển sang child-first hoặc loader độc lập,
- có thể gây LinkageError/NoSuchMethodError khi runtime và compile-time API không tương thích,
- khiến người dùng tưởng plugin tự mang một định nghĩa API riêng.

Ưu tiên artifact API được host sở hữu, plugin khai báo dependency kiểu **provided/compileOnly** nếu dùng build tool và không đóng gói API vào plugin JAR.

## 8. Xử lý lỗi trong quá trình nạp và chuyển kiểu

Một host thực tế nên báo lỗi rõ theo các bước **tìm file → nạp class → kiểm tra hợp đồng → khởi tạo → gọi nghiệp vụ**. Bảng dưới chỉ ra một số lỗi quan trọng:

| Triệu chứng/exception | Nguyên nhân hay gặp | Hướng kiểm tra |
|---|---|---|
| **ClassNotFoundException** | Tên class sai, JAR thiếu class, URL không trỏ đúng JAR/thư mục | Kiểm tra binary name, jar --list, đường dẫn/URL |
| **NoClassDefFoundError** | Class phụ thuộc được tham chiếu nhưng không tìm thấy, hoặc class không khởi tạo được trước đó | Kiểm tra dependency của plugin và nguyên nhân gốc; đừng chỉ nhìn class entry point |
| **ClassCastException** tại asSubclass hoặc cast | Plugin không implements contract đúng, hoặc có hai định nghĩa API qua hai loader | Kiểm tra isAssignableFrom, loader của contract và interface thực tế |
| **NoSuchMethodException** tại getConstructor | Không có public no-arg constructor | Công bố constructor đúng hoặc dùng factory contract |
| **IllegalAccessException** | Constructor/class không accessible từ host | Kiểm tra visibility/module boundaries |
| **InvocationTargetException** | Constructor plugin tự ném lỗi | Xem **getCause()** để biết lỗi do constructor |
| **ExceptionInInitializerError** | Static initialization thất bại | Kiểm tra static initializer và nguyên nhân |
| **UnsupportedClassVersionError** | Plugin được biên dịch cho JDK mới hơn JVM đang chạy | Điều chỉnh target Java hoặc nâng runtime |
| **NoSuchMethodError/AbstractMethodError** | API host và plugin không tương thích nhị phân | Kiểm tra version artifact API và dependency |
| **IOException** khi close hoặc đọc JAR | Tệp, resource, môi trường đóng loader có vấn đề | Ghi log đường dẫn và cause; bảo đảm cleanup |

**ClassNotFoundException** và **NoClassDefFoundError** không giống nhau: lỗi đầu thường là thất bại khi chủ động tìm class qua tên; lỗi sau thường xuất hiện khi JVM đã cần một định nghĩa class phụ thuộc nhưng không thể liên kết/tải/khởi tạo nó trong ngữ cảnh liên quan.

Một cách bọc lỗi rõ ràng (mảnh minh họa; đặt trong code host, biến loader và tên class đã xác định):

~~~java
try {
    Class<?> raw = loader.loadClass(className);
    Class<? extends Greeter> typed = raw.asSubclass(Greeter.class);
    return typed.getConstructor().newInstance();
} catch (ClassNotFoundException e) {
    throw new IllegalStateException("Missing plugin class: " + className, e);
} catch (ClassCastException e) {
    throw new IllegalStateException(
            "Plugin does not implement shared Greeter: " + className, e);
} catch (ReflectiveOperationException e) {
    throw new IllegalStateException(
            "Cannot create plugin: " + className, e);
}
~~~

Đây là **mảnh phương thức minh họa**, không phải chương trình độc lập: ví dụ giả định code nằm trong một phương thức trả Greeter, có biến **loader**, **className**, import và contract Greeter sẵn có. Một số **LinkageError** hoặc lỗi runtime của plugin không thuộc các catch trên; ở ranh giới tải plugin có thể cần ghi nhận thêm mà không nuốt lỗi hệ thống bừa bãi.

Khi dùng **getConstructor().newInstance()**, một exception do constructor ném thường nằm trong **InvocationTargetException.getCause()**. Host có thể phân loại lỗi cấu hình/plugin riêng, thay vì biến tất cả thành một thông báo “không tìm thấy class”.

## 9. URL trỏ đến gì và phụ thuộc plugin được giải quyết ra sao?

### 9.1. JAR hoặc thư mục .class

URLClassLoader nhận URL đến JAR hoặc thư mục chứa class/resource có đường dẫn package chuẩn:

~~~java
// Mảnh minh họa, đường dẫn đã tồn tại:
URL jarUrl = Path.of("plugins", "greeter.jar")
        .toAbsolutePath().toUri().toURL();

URL classesUrl = Path.of("plugins", "classes")
        .toAbsolutePath().toUri().toURL();
~~~

**file URL kết thúc bằng /** được hiểu là thư mục; URL đến file JAR được xử lý như JAR. Khi dùng **Path.toUri()** trên một thư mục tồn tại, JDK tạo URI dạng thư mục phù hợp. Với class **a.b.C**, thư mục root phải chứa **a/b/C.class**, không trỏ thẳng vào package a/b.

Không nên tạo URL bằng cách ghép **"file:" + path.toString()**: đường dẫn Windows, khoảng trắng, ký tự Unicode và encoding dễ sai.

### 9.2. Thư viện mà plugin cần

Nếu VietnameseGreeter sử dụng thêm một JAR thư viện không có ở parent, cung cấp URL đó trong mảng URL:

~~~java
// Mảnh minh họa:
URL[] locations = {
        Path.of("plugins", "greeter.jar").toUri().toURL(),
        Path.of("plugins", "helper-lib.jar").toUri().toURL()
};
URLClassLoader loader =
        new URLClassLoader(locations, Greeter.class.getClassLoader());
~~~

Không phải URLClassLoader tự tìm tất cả JAR trong một thư mục chỉ vì bạn truyền URL của thư mục đó. Cần chỉ ra từng JAR, hoặc dùng cơ chế build/deployment/manifest Class-Path có kiểm soát. Hãy đặc biệt chú ý thư viện API chung: phiên bản mà plugin biên dịch cần tương thích với API được parent cung cấp.

### 9.3. Resource và ServiceLoader

URLClassLoader còn có thể tìm resource nằm trong plugin JAR (config, schema...). Nếu plugin khai báo service bằng **META-INF/services**, host có thể kết hợp:

~~~java
// Mảnh minh họa cho trường hợp plugin khai báo SPI hợp lệ:
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, pluginLoader);

for (Greeter candidate : services) {
    System.out.println(candidate.greet("Java"));
}
~~~

Trong cách này **ServiceLoader** đảm nhiệm discovery và tạo provider theo quy tắc SPI, thay cho host giữ một tên class cụ thể. **Điều kiện:** plugin phải đăng ký service hợp lệ; JAR ví dụ ở phần 4 không có META-INF/services nên riêng ví dụ đó sẽ không được ServiceLoader tự phát hiện.

Tính mở rộng thay đổi ở bước khám phá/khởi tạo, nhưng nguyên tắc **shared contract class loader** vẫn giống nhau. Đừng nhầm ServiceLoader với URLClassLoader: **URLClassLoader cung cấp cách tìm class/resource**, còn **ServiceLoader dùng metadata service để tìm provider**.

## 10. Quản lý vòng đời URLClassLoader và plugin

URLClassLoader triển khai **Closeable/AutoCloseable**, nên có thể dùng try-with-resources:

~~~java
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    // load class, tạo và dùng plugin
}
~~~

**close()** đóng file handle/JAR đã mở và ngăn loader tải thêm các class/resource mới do nó định nghĩa. Tuy nhiên:

- Class và object đã nạp **không biến mất ngay** chỉ vì close().
- GC chỉ có thể thu hồi loader/class metadata khi **không còn reference mạnh** đến loader, Class, instance, thread, context class loader, static registry/callback hoặc những đối tượng giữ chúng.
- Nếu plugin tạo thread, executor, timer, stream, socket, file handle..., plugin/host phải đóng chúng theo hợp đồng lifecycle riêng.
- Không đóng loader trong khi plugin còn cần tải thêm các class chưa nạp (ví dụ lần đầu sử dụng một feature phụ) hoặc còn yêu cầu chạy song song.
- Không gọi **close()** đồng thời với việc loader đang load class ở thread khác; tài liệu API không bảo đảm kết quả của lần load đang diễn ra.

Ở ví dụ nhỏ, host dùng plugin xong trước khi ra khỏi try nên hợp lý. Với plugin chạy nhiều giờ, nên giữ loader sống theo phiên plugin và chỉ đóng sau khi **ngừng nhận yêu cầu → kết thúc công việc → đóng plugin → gỡ đăng ký callback → đóng loader**.

**URLClassLoader không phải API hot-reload tự động.** Để thay phiên bản plugin, một thiết kế thường cần tạo loader mới cho JAR mới, chuyển traffic sang instance mới, ngừng instance cũ và giải phóng mọi tham chiếu đến loader cũ. Thay JAR file trên đĩa không biến đổi những Class object đã được JVM định nghĩa trước đó.

## 11. Ranh giới bảo mật và giới hạn của cơ chế

**Nạp JAR bằng URLClassLoader là thực thi mã Java trong cùng JVM**, không phải sandbox. Constructor, static initializer và các phương thức plugin có thể chạy mã tùy ý với quyền của process. URLClassLoader không tự cung cấp ranh giới bảo mật mạnh, timeout, giới hạn CPU/RAM, cách ly thread hoặc khả năng hoàn tác thao tác của plugin.

Với plugin của bên thứ ba:

1. Xác thực nguồn artifact (checksum/signature theo chính sách phát hành) và kiểm soát ai được cài plugin.
2. Chỉ tải plugin từ thư mục được quản lý; kiểm tra đường dẫn thực tế và tránh cho input tùy ý mở URL từ mạng.
3. Ràng buộc phiên bản API, dependency và hệ điều hành/JDK hỗ trợ.
4. Thiết kế timeout, thread/resource ownership và xử lý lỗi nghiệp vụ theo ngữ cảnh.
5. Nếu mã plugin không đáng tin cậy hoặc cần cách ly thực sự, cân nhắc **process/container riêng** và giao tiếp qua IPC/RPC thay vì chạy cùng JVM.

Không nên dùng class loader như cách ngăn code độc hại truy cập file, network hoặc bộ nhớ của host. Nó chủ yếu là cơ chế **nạp/lập namespace class**.

## 12. Tương tác với Java Platform Module System (JPMS)

Ví dụ runnable ở phần 4 chạy trên **classpath**, nên class trong plugin JAR được nạp vào môi trường **unnamed module** tương ứng với URLClassLoader. Việc tạo URLClassLoader **không tự resolve một named module** chỉ vì JAR có **module-info.class**.

Khi ứng dụng triển khai bằng **module path** với module descriptor, cần hiểu thêm:

- Một API trong named module có package **exports** để code plugin được phép tham chiếu.
- Quy tắc module readability và reflective access khác với classpath; một class nạp được chưa chắc mọi constructor/member đều được truy cập.
- Nếu muốn quản lý các plugin thành **named modules** ở runtime, thiết kế dựa vào **ModuleFinder/Configuration/ModuleLayer** và các loader tương ứng; đó là quy trình khác với đơn thuần nạp JAR từ URLClassLoader.
- Các plugin cung cấp service bằng **provides ... with ...**, host khai báo **uses**, có thể kết hợp **ServiceLoader** theo module layer.

Do đó, trước khi chọn URLClassLoader cho hệ thống thực tế, xác định bạn đang dùng **classpath plugins** hay **module-layer plugins**. Không trộn hai mô hình một cách ngẫu nhiên rồi xử lý lỗi bằng cast hoặc reflective access không kiểm soát.

## 13. Cách debug một plugin không nạp hoặc không cast được

Khi gặp lỗi, kiểm tra theo thứ tự sau:

**(1) Có đúng JAR và entry class?**

~~~bash
jar --list --file build/vietnamese-greeter.jar
~~~

Đảm bảo class tồn tại đúng đường dẫn **example/impl/VietnameseGreeter.class**, không bị lồng thêm thư mục **build/plugin/** bên trong JAR.

**(2) URL có trỏ đúng artifact?** In **jar.toAbsolutePath()**, **jar.toUri()** và đường dẫn thật. Dùng Files.isRegularFile() để phát hiện sai tệp. Nếu là thư mục .class, URL phải đến **package root**.

**(3) Parent có phải loader của hợp đồng không?**

~~~java
// Mảnh minh họa cho debug trong host:
System.out.println("API loader: " + Greeter.class.getClassLoader());
System.out.println("Implementation loader: " + rawClass.getClassLoader());
System.out.println("Assignable: "
        + Greeter.class.isAssignableFrom(rawClass));
~~~

Nếu assignable false, đừng chỉ in tên class; kiểm tra xem classloader nào định nghĩa từng interface. **rawClass.getInterfaces()** có thể giúp inspect direct interface nhưng không liệt kê mọi interface được thừa kế gián tiếp; **isAssignableFrom** là kiểm tra trực tiếp, chính xác hơn cho mục đích cast.

**(4) Constructor có phù hợp?** Nếu class không public hoặc không có public no-arg constructor, **getConstructor()** hay **newInstance()** sẽ thất bại. Hãy định nghĩa rõ entry point; trường hợp cần injection hãy dùng factory API thay vì mở quyền reflection vô tội vạ.

**(5) Dependency có tìm được không?** Plugin có thể nạp class entry point thành công nhưng lỗi **NoClassDefFoundError** khi chạy một nhánh code chỉ lúc đó mới dùng dependency còn thiếu. Kiểm tra JAR liên quan, API version và thứ tự delegation. Đừng kết luận plugin chạy tốt chỉ vì loadClass thành công.

**(6) Class có được host vô tình nạp trước?** Nếu **rawClass.getClassLoader()** chính là parent, implementation đã nằm trong parent classpath. Điều này thay đổi ranh giới cách ly và khiến thay JAR bằng loader mới không có tác dụng cho class đó.

**(7) Vòng đời có còn đúng?** Nếu plugin gọi thêm class sau khi URLClassLoader đã close(), việc tải class mới có thể thất bại. Nếu loader không được thu hồi sau khi disable plugin, tìm reference từ instance, static field, thread và Thread Context ClassLoader.

## 14. Những sai lầm thiết kế dễ gặp

### Sai lầm 1: Host import thẳng class plugin

~~~java
// Mảnh minh họa anti-pattern:
Greeter g = new example.impl.VietnameseGreeter();
~~~

Host như vậy phải có plugin trên compile/runtime classpath; thêm plugin mới có thể buộc sửa host. Hãy dùng interface API chung, đường dẫn artifact và tên class/configuration/discovery để tạo implementation lúc chạy.

### Sai lầm 2: Dùng loader độc lập làm mất hợp đồng

~~~java
// Mảnh minh họa anti-pattern: parent không thấy API của ứng dụng.
URLClassLoader isolated = new URLClassLoader(
        urls,
        ClassLoader.getPlatformClassLoader()
);
~~~

Nếu plugin JAR chứa bản Greeter của nó, có thể làm phát sinh class identity riêng. Dùng parent của **Greeter.class** trong ví dụ là cách đúng để bảo toàn kiểu hợp đồng chung; vẫn phải thiết kế chi tiết cho host phức tạp có nhiều API loaders.

### Sai lầm 3: Cast trước rồi mới kiểm tra

~~~java
// Mảnh minh họa anti-pattern:
Object obj = rawClass.getConstructor().newInstance();
Greeter greeter = (Greeter) obj;
~~~

Phép cast ở đây không tự động sai, nhưng nếu class không phù hợp thì lỗi chỉ phát hiện **sau khi đã tạo object**, có thể đã kích hoạt side effects. Dùng **asSubclass** trước khi tạo object để kiểm tra ngay ranh giới.

### Sai lầm 4: Dùng reflection cho mọi lần gọi nghiệp vụ

~~~java
// Mảnh minh họa anti-pattern:
Object obj = rawClass.getConstructor().newInstance();
Object value = rawClass.getMethod("greet", String.class).invoke(obj, "Java");
~~~

Nếu service đã có interface chung, chỉ dùng reflection tại bước khởi tạo và sau đó gọi **Greeter.greet** trực tiếp. Cách này giúp compiler kiểm tra chữ ký, giảm stringly-typed logic và dễ kiểm thử hơn.

### Sai lầm 5: Bỏ quên API version và dependency

Chỉ việc một plugin class được nạp không chứng minh version API tương thích. Một plugin biên dịch với method mới trên Greeter nhưng chạy với API cũ ở parent có thể gặp lỗi liên kết/NoSuchMethodError. Quản lý tương thích nhị phân, phát hành API ổn định và kiểm thử plugin trên phiên bản host được hỗ trợ.

### Sai lầm 6: Coi close() là unload tức thời

Đóng loader giải phóng file handle và ngăn load mới, nhưng class và instance vẫn có thể tồn tại. Có thread/callback/static cache do plugin giữ sẽ cản việc thu hồi loader. Cần cleanup lifecycle rõ ràng.

## 15. Khi nào cách này phù hợp, khi nào nên thay bằng SPI/DI?

**URLClassLoader + tên class + shared contract** phù hợp khi host biết artifact cụ thể, muốn tạo một loader riêng cho plugin JAR, không muốn phụ thuộc vào implementation tại compile-time và cần ranh giới API tường minh. Nó đặc biệt dễ hiểu trong launcher, tool, sandbox thử nghiệm *của mã tin cậy*, hoặc hệ thống cho người vận hành chỉ định chính xác plugin class.

Khi có nhiều provider và người viết plugin cần tự đăng ký, có thể xây **registry** hoặc dùng **ServiceLoader** với META-INF/services. Khi dùng Spring/DI container, container có thể quản lý factory, dependency và lifecycle. Các cơ chế này không thay đổi nguyên lý quan trọng: **host và implementation phải có một kiểu hợp đồng tương thích ở runtime**.

Nếu cần cô lập phiên bản thư viện riêng của nhiều plugin, policy **parent-first cho API** và **cách xử lý dependency xung đột** trở thành phần thiết kế riêng. Nếu cần nạp/gỡ named modules, dùng hướng tiếp cận ModuleLayer phù hợp. Nếu cần mã thực sự không tin cậy, cách ly bằng process thay vì tin vào classloader.

## 16. Bài tập tự kiểm tra

**Câu 1.** Host chỉ có Greeter.class trong classpath và một đường dẫn JAR. Vì sao vẫn gọi được **greeter.greet("Java")**?

**Đáp án:** Host biết kiểu interface Greeter khi biên dịch. Lúc chạy, URLClassLoader nạp class implements chính interface ấy, host kiểm tra bằng asSubclass và tạo instance. Lời gọi qua interface được JVM dispatch tới implementation tương ứng.

**Câu 2.** Nếu Greeter.class.isAssignableFrom(rawClass) trả false dù rawClass có tên interface Greeter trong phần implements, cần kiểm tra điều gì?

**Đáp án:** Có thể tồn tại hai Class object Greeter cùng binary name nhưng do hai defining loaders khác nhau nạp. Cần xem parent của plugin loader và loader của API mà host sử dụng, thêm cả version API và thứ tự delegation.

**Câu 3.** Chỉ gọi pluginLoader.loadClass(name) đã chạy constructor chưa?

**Đáp án:** Chưa. Lệnh trả **Class<?>**; việc tạo instance ở **getConstructor().newInstance()** mới gọi constructor. Tuy nhiên nạp/liên kết class vẫn có thể gây chi phí hoặc lỗi.

**Câu 4.** Tại sao plugin JAR trong ví dụ không nằm trong tham số **java -cp**?

**Đáp án:** Đó là điều kiện để minh họa cơ chế nạp động. Nếu parent classpath đã thấy implementation, URLClassLoader con có thể nhận lại class do parent cung cấp và không chứng minh việc nạp riêng từ URL.

**Câu 5.** Có thể thay JAR trên đĩa rồi gọi cùng pluginLoader.loadClass(name) để nhận class implementation mới không?

**Đáp án:** Không thể coi đó là cơ chế reload đúng. Class đã được định nghĩa trong loader được cache theo danh tính đó; thay code cần chiến lược tạo loader mới, ngừng plugin cũ và quản lý cleanup/reference.

## 17. Checklist trước khi triển khai

1. **API chung:** đặt interface trong artifact API riêng, host và plugin dùng version tương thích; plugin không cần đóng gói trùng API.
2. **Loader hierarchy:** parent cung cấp đúng API Class object; implementation được URLClassLoader con tìm từ JAR/thư mục phù hợp.
3. **Tên class/JAR:** kiểm tra đường dẫn thực tế, binary name và nội dung JAR; không đưa implementation vào parent classpath nếu cần nạp riêng.
4. **Kiểm tra kiểu:** sử dụng **isAssignableFrom** để chẩn đoán và **asSubclass** để chuyển Class<?> thành Class<? extends Contract>.
5. **Khởi tạo rõ ràng:** dùng **public constructor** được thống nhất hoặc factory API; tránh deprecated Class.newInstance và reflective access tùy tiện.
6. **Xử lý lỗi:** phân biệt file/URL, class loading, link dependencies, cast, constructor và business exception; log cause và version liên quan.
7. **Lifecycle:** ngừng công việc plugin, đóng tài nguyên, gỡ listener/thread/static references rồi đóng URLClassLoader đúng thời điểm.
8. **Giới hạn:** URLClassLoader không tự phát hiện metadata plugin, không tự unload/reload an toàn và không tạo security sandbox.

**Kết quả mong muốn của bài học:** một host chỉ phụ thuộc vào **hợp đồng chung** vẫn có thể tìm class mới từ JAR bằng **URLClassLoader**, dùng **asSubclass** để bảo đảm quan hệ kiểu trước khi tạo instance, và tiếp tục gọi nghiệp vụ qua interface mà không gắn code host vào implementation của plugin.

### Tài liệu Java SE 17

- URLClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- ClassLoader và cơ chế parent delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Class.asSubclass, Class.cast và getConstructor: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Constructor.newInstance: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html
