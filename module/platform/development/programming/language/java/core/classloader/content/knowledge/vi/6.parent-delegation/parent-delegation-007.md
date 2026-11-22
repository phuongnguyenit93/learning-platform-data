# Khả năng nhìn thấy từ loader con tới loader cha

## 1. Ý nghĩa của “nhìn thấy” trong cơ chế ủy quyền

Trong Java, ClassLoader không chỉ có nhiệm vụ đọc file `.class`. Nó quyết định **loader nào được phép tham gia tìm một lớp hoặc tài nguyên** và **loader nào thực sự định nghĩa runtime class**. Với mô hình **parent-first delegation** thông thường, một loader con thử nhờ loader cha tìm lớp trước. Nếu cha không tìm được, loader con mới tìm trong nguồn riêng của nó.

Điều quan trọng nhất của bài học là tính **bất đối xứng**:

- **Con → cha:** loader con thường nhìn thấy các lớp mà loader cha hoặc tổ tiên của cha tìm được thông qua cơ chế ủy quyền.
- **Cha → con:** loader cha **không tự động tìm** trong JAR, thư mục hoặc các lớp mà riêng loader con quản lý.
- “Nhìn thấy” không nhất thiết là “tự định nghĩa”: loader con có thể **trả về đúng class do cha định nghĩa**, không tạo bản sao.
- Cơ chế ủy quyền về việc tìm class **không bỏ qua** Java access control, tính toàn vẹn runtime type hoặc quy tắc module.

Đây là mô hình của `ClassLoader.loadClass` mặc định và các subclass tuân theo delegation. Một ClassLoader tùy biến có thể override `loadClass` để thay đổi quy tắc tìm kiếm; JPMS còn có những đường liên kết module đặc biệt. Vì vậy đừng coi quan hệ cha–con là một luật về tầm nhìn bất biến trong mọi ClassLoader của mọi framework.

## 2. Mô hình trực quan

Ví dụ JVM có loader ứng dụng (cha) và một `URLClassLoader` tải JAR plugin (con):

~~~text
                     Bootstrap ClassLoader
                               ▲
                               │
                     Platform ClassLoader
                               ▲
                               │
                     Application Loader
                     (cha / parent)
                       ├── demo.api.Greeter
                       └── demo.host.Host
                               ▲
                  loadClass()   │ ủy quyền lên cha
                               │
                     URLClassLoader
                     (con / child)
                       └── hello-plugin.jar
                             ├── demo.plugin.HelloGreeter
                             └── plugin-message.txt
~~~

Giả sử chỉ parent có `demo.api.Greeter` và chỉ child có `demo.plugin.HelloGreeter`:

| Yêu cầu | Kết quả theo parent-first thông thường | Lớp do ai định nghĩa? |
|---|---|---|
| `child.loadClass("demo.api.Greeter")` | Child nhờ parent, parent tìm thấy | **Parent** |
| `child.loadClass("demo.plugin.HelloGreeter")` | Parent không thấy; child tìm trong JAR | **Child** |
| `parent.loadClass("demo.api.Greeter")` | Parent tìm lớp thuộc classpath của mình | **Parent** |
| `parent.loadClass("demo.plugin.HelloGreeter")` | Không thấy nếu JAR plugin chỉ thuộc child | Không có kết quả, ném `ClassNotFoundException` |
| `child.getResource("plugin-message.txt")` | Child tìm thấy resource riêng sau khi parent không thấy | URL tài nguyên thuộc JAR plugin |
| `parent.getResource("plugin-message.txt")` | Không tìm thấy resource chỉ có trong child | Trả về `null` |

**Chiều của mũi tên là chiều ủy quyền truy vấn từ con lên cha.** Java không có cơ chế mặc định yêu cầu cha tự duyệt tất cả các loader con đang tồn tại. Parent còn có thể không giữ bất cứ danh sách child nào.

“Cha không thấy con” **không** có nghĩa là mã được parent định nghĩa không bao giờ sử dụng class từ child. Host hoàn toàn có thể giữ một tham chiếu tới child loader, gọi `child.loadClass(...)` hoặc nhận instance plugin qua interface chung. Khi đó host **chủ động gọi tới loader con**, chứ parent không tự tìm ngược bằng `parent.loadClass(...)`.

## 3. Parent-first tìm class ra sao?

Về mặt ý tưởng, cài đặt mặc định của `ClassLoader.loadClass(String, boolean)` thực hiện:

1. Kiểm tra class đã được loader nhận biết qua `findLoadedClass(name)`.
2. Nếu chưa, **ủy quyền cho parent** bằng `parent.loadClass(name, false)`; nếu không có parent thì thử cơ chế bootstrap.
3. Chỉ khi cha/bộ nạp bootstrap báo không tìm thấy thì gọi `findClass(name)` của chính loader.
4. Nếu caller yêu cầu `resolve == true`, thực hiện resolution cần thiết cho kết quả.

Một cách mô tả giả mã:

~~~java
// GIẢ MÃ: không phải một method chạy độc lập.
Class<?> loadClassConceptually(String name) throws ClassNotFoundException {
    Class<?> already = findLoadedClass(name);
    if (already != null) {
        return already;
    }

    try {
        return delegateToParentOrBootstrap(name);
    } catch (ClassNotFoundException notFoundByParent) {
        return findClass(name);
    }
}
~~~

Đây là **mô hình logic**, không chép lại nguyên văn implementation thật. Bản thật có xử lý đồng bộ hóa, exception, resolution và nhiều chi tiết khác.

Các điểm dễ nhầm:

- `loadClass(...)` có thể trả về class do **parent định nghĩa**, dù chính child là object nhận lời gọi.
- Mỗi lần gọi `loadClass` **không nhất thiết** đọc lại bytecode; loader và JVM ghi nhớ những class đã được nạp.
- Phép kiểm tra parent-first áp dụng cho class **được yêu cầu tìm**; nó không bắt JVM khởi tạo tất cả class của parent trước.
- `loadClass(String)` thường **không kích hoạt class initialization**. Muốn chủ động initialize có thể dùng `Class.forName(name, true, loader)` sau khi hiểu nhu cầu.
- `ClassLoader` mặc định tuân parent-first; một framework có thể dùng child-first hoặc quy tắc dành riêng cho package/module.

## 4. Ví dụ Java 17+ có thể chạy: host, API và plugin

Ta sẽ tạo chương trình thực nghiệm chứng minh bốn kết quả: **child nhìn thấy API từ parent**, **parent không nhìn thấy implementation chỉ thuộc child**, **child nạp implementation và resource từ plugin JAR**, và **hai child riêng định nghĩa hai class cùng tên nhưng khác runtime type**.

### 4.1. Cấu trúc dự án

Tạo các thư mục và file theo đúng đường dẫn:

~~~text
visibility-demo/
├── host-src/
│   └── demo/
│       ├── api/
│       │   └── Greeter.java
│       └── host/
│           └── Host.java
├── plugin-src/
│   └── demo/
│       └── plugin/
│           └── HelloGreeter.java
└── plugin-resources/
    └── plugin-message.txt
~~~

Các thư mục `build/host`, `build/plugin` và file `build/hello-plugin.jar` sẽ được tạo ở bước biên dịch. **Không đưa plugin JAR vào classpath của lệnh chạy host**, vì mục tiêu là cho host và plugin ở hai loader khác nhau.

### 4.2. Hợp đồng chung trong parent

File **`host-src/demo/api/Greeter.java`**:

~~~java
package demo.api;

public interface Greeter {
    String greet(String name);
}
~~~

Interface này được biên dịch vào classpath của host. Plugin được phép phụ thuộc `Greeter` lúc **biên dịch**, nhưng lúc **chạy** sẽ resolve interface qua parent loader.

### 4.3. Lớp triển khai chỉ thuộc child

File **`plugin-src/demo/plugin/HelloGreeter.java`**:

~~~java
package demo.plugin;

import demo.api.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Đây là `public` class với `public` constructor không tham số, nên host có thể tạo instance bằng reflection. Plugin có thể gọi phương thức interface do parent định nghĩa vì plugin loader có thể nhờ parent tải `demo.api.Greeter`.

File văn bản **`plugin-resources/plugin-message.txt`**:

~~~text
Only the plugin loader sees this resource by default.
~~~

Tệp này chỉ nằm trong plugin JAR, dùng để kiểm tra rằng tìm **resource** cũng có chiều ủy quyền và không tự quay ngược từ parent xuống child.

### 4.4. Host chủ động tạo loader con

File **`host-src/demo/host/Host.java`**:

~~~java
package demo.host;

import demo.api.Greeter;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Host {
    private Host() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: Host <path-to-plugin-jar>");
        }

        Path jar = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException("Missing JAR: " + jar);
        }

        ClassLoader parent = Greeter.class.getClassLoader();
        URL[] urls = {jar.toUri().toURL()};

        try (URLClassLoader child = new URLClassLoader(urls, parent);
             URLClassLoader anotherChild = new URLClassLoader(urls, parent)) {

            Class<?> apiViaChild =
                    child.loadClass("demo.api.Greeter");
            System.out.println("Child sees parent API: "
                    + (apiViaChild == Greeter.class));

            boolean parentSeesPlugin;
            try {
                parent.loadClass("demo.plugin.HelloGreeter");
                parentSeesPlugin = true;
            } catch (ClassNotFoundException ignored) {
                parentSeesPlugin = false;
            }
            System.out.println("Parent finds child-only class: "
                    + parentSeesPlugin);

            Class<?> implementation =
                    child.loadClass("demo.plugin.HelloGreeter");
            System.out.println("Plugin defined by child: "
                    + (implementation.getClassLoader() == child));

            Greeter instance = (Greeter) implementation
                    .getConstructor()
                    .newInstance();
            System.out.println("Call through shared API: "
                    + instance.greet("Java"));

            System.out.println("Child finds plugin resource: "
                    + (child.getResource("plugin-message.txt") != null));
            System.out.println("Parent finds plugin resource: "
                    + (parent.getResource("plugin-message.txt") != null));

            Class<?> implementationTwo =
                    anotherChild.loadClass("demo.plugin.HelloGreeter");
            System.out.println("Two child classes identical: "
                    + (implementation == implementationTwo));

            System.out.println("Both implement shared API: "
                    + (Greeter.class.isAssignableFrom(implementation)
                    && Greeter.class.isAssignableFrom(implementationTwo)));
        }
    }
}
~~~

**Vì sao chọn `Greeter.class.getClassLoader()` làm parent?** Vì đây là loader **định nghĩa interface mà host và plugin cần chia sẻ**. Trong chương trình classpath mẫu, nó chính là application/system loader; trong framework phức tạp, loader của interface có thể khác system loader. Lấy parent theo interface giúp thiết kế đúng với mục tiêu chia sẻ runtime type.

Ta tạo **hai** `URLClassLoader` với cùng một đường dẫn JAR nhằm chứng minh hai loader con độc lập vẫn có thể định nghĩa hai class triển khai mang **cùng tên nhị phân** nhưng không phải cùng runtime class.

## 5. Biên dịch và chạy thực nghiệm

Yêu cầu JDK **17 trở lên** với `javac`, `jar` và `java`. Mở terminal tại thư mục `visibility-demo/` đã chứa đủ bốn file nguồn/tài nguyên.

**Bash trên Linux/macOS hoặc Git Bash:**

~~~bash
mkdir -p build/host build/plugin

javac -encoding UTF-8 \
  -d build/host \
  host-src/demo/api/Greeter.java \
  host-src/demo/host/Host.java

javac -encoding UTF-8 \
  -cp build/host \
  -d build/plugin \
  plugin-src/demo/plugin/HelloGreeter.java

jar --create --file build/hello-plugin.jar \
  -C build/plugin . \
  -C plugin-resources .

java -cp build/host demo.host.Host build/hello-plugin.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/host,build/plugin | Out-Null

javac -encoding UTF-8 -d build/host host-src/demo/api/Greeter.java host-src/demo/host/Host.java

javac -encoding UTF-8 -cp build/host -d build/plugin plugin-src/demo/plugin/HelloGreeter.java

jar --create --file build/hello-plugin.jar -C build/plugin . -C plugin-resources .

java -cp build/host demo.host.Host build/hello-plugin.jar
~~~

Lệnh đóng gói giữ `demo/plugin/HelloGreeter.class` và `plugin-message.txt` trong plugin JAR, còn `Greeter.class` ở `build/host`. Kiểm tra nếu cần:

~~~bash
jar --list --file build/hello-plugin.jar
~~~

Trong output lệnh liệt kê, đảm bảo có ít nhất hai entry `demo/plugin/HelloGreeter.class` và `plugin-message.txt`; JAR có thể có thêm `META-INF/MANIFEST.MF` và các entry thư mục.

**Stdout của chương trình trên classpath chuẩn đã chỉ định:**

~~~text
Child sees parent API: true
Parent finds child-only class: false
Plugin defined by child: true
Call through shared API: Hello, Java!
Child finds plugin resource: true
Parent finds plugin resource: false
Two child classes identical: false
Both implement shared API: true
~~~

Không in tên class loader nội bộ kiểu `jdk.internal.loader.ClassLoaders$AppClassLoader@...` vì string này không ổn định giữa các JVM hay các lần chạy. Các phép so sánh `==` tạo ra kết quả cụ thể, có thể kiểm tra.

## 6. Phân tích đường đi cho từng lời gọi

### 6.1. Child yêu cầu class của parent

~~~java
Class<?> apiViaChild = child.loadClass("demo.api.Greeter");
~~~

Child kiểm tra `demo.api.Greeter` rồi hỏi parent. Parent đã nhìn thấy `Greeter` từ `build/host`, nên trả class do chính nó định nghĩa. Child nhận và trả **cùng đối tượng `Class<?>`**:

~~~java
apiViaChild == Greeter.class  // true
~~~

Không có bản sao `Greeter` được định nghĩa bởi child. Nếu khai báo rằng “gọi `child.loadClass` tức class thuộc child” thì sẽ giải thích sai cả mã host/plugin và khả năng ép kiểu qua API.

### 6.2. Parent yêu cầu class chỉ nằm trong child

~~~java
parent.loadClass("demo.plugin.HelloGreeter");
~~~

JAR plugin **không có trong classpath của parent**, nên parent và tổ tiên của nó không tìm thấy `HelloGreeter`. Parent không có bước chuẩn “thử mọi child của tôi” và ném `ClassNotFoundException`.

Kết luận chỉ áp dụng cho cấu hình ví dụ. Nếu cùng JAR plugin được đặt thêm vào application classpath, hoặc parent được cấu hình thêm nguồn tìm class, parent **có thể tìm thấy** plugin. Tức là chiều nhìn thấy phụ thuộc **cả quan hệ loader lẫn vị trí bytecode**.

### 6.3. Child yêu cầu class triển khai từ JAR riêng

~~~java
Class<?> implementation =
        child.loadClass("demo.plugin.HelloGreeter");
~~~

Child nhờ parent; parent không tìm thấy, child tiếp tục dùng chức năng `findClass` của `URLClassLoader` đọc class từ JAR. Vì thế:

~~~java
implementation.getClassLoader() == child  // true
~~~

Trong quá trình JVM liên kết class này, interface `demo.api.Greeter` được tìm theo parent; do đó object plugin có thể được ép kiểu sang `Greeter` và host gọi `greet("Java")`. Hai bên không cần cùng loader **cho mọi class**, mà cần chia sẻ đúng **cùng runtime interface** tại ranh giới giao tiếp.

### 6.4. Resource có cùng chiều tra cứu mặc định

~~~java
child.getResource("plugin-message.txt")   // URL khác null
parent.getResource("plugin-message.txt")  // null trong ví dụ
~~~

`URLClassLoader` triển khai `getResource` theo parent-first: hỏi parent trước, rồi tìm URL của mình. Nhưng parent tự truy vấn **không biết các URL của child** nên không tìm được resource của plugin. Tương tự, `getResources` có thể tập hợp resource từ parent và child theo quy tắc triển khai, và `ServiceLoader` dùng resource `META-INF/services/...` để tìm provider khi chạy theo cơ chế classpath.

Đối với tài nguyên của **named modules**, còn có quy tắc đóng/mở package và cơ chế module; không giả định mọi resource có thể đọc được từ mọi loader.

### 6.5. Hai child, hai class triển khai độc lập

~~~java
Class<?> implementationTwo =
        anotherChild.loadClass("demo.plugin.HelloGreeter");
~~~

`child` và `anotherChild` có cùng JAR URL và parent, nhưng mỗi loader **tự định nghĩa** `demo.plugin.HelloGreeter`. Với JVM, runtime class identity phụ thuộc vào **tên nhị phân cộng với defining loader**:

~~~text
(demo.plugin.HelloGreeter, child)
    !=
(demo.plugin.HelloGreeter, anotherChild)
~~~

Vì vậy `implementation == implementationTwo` trả `false`. Dù vậy cả hai implementation đều sử dụng `demo.api.Greeter` do **cùng parent** định nghĩa, nên `Greeter.class.isAssignableFrom(...)` cho cả hai trả `true`.

Đây là một kiểu cách ly hữu ích cho plugin: implementation giữa hai phiên bản có thể là các runtime type khác nhau, trong khi host vẫn giao tiếp qua cùng API.

## 7. Nhìn thấy class khác với được phép truy cập thành viên

Ngay cả khi child tìm được class của parent, Java vẫn kiểm tra quyền truy cập tới class, constructor, method và field:

- Thành viên `public` của một public API có thể được sử dụng nếu quy tắc module tương ứng cho phép.
- Thành viên `private` không trở thành truy cập được chỉ nhờ quan hệ loader cha–con.
- **Runtime package** không chỉ được xác định bởi tên package mà còn bởi **defining loader** (và trong hệ module còn có module). Hai class cùng chuỗi package nhưng được hai loader khác nhau định nghĩa **không đương nhiên có package-private access** vào nhau.
- Reflection cũng chịu kiểm soát quyền truy cập và JPMS `exports`/`opens`. Quan hệ parent không tự vượt qua `InaccessibleObjectException` hay `IllegalAccessException`.

Ví dụ: đặt class `demo.api.Helper` trong parent với package-private method, rồi thêm class cùng package `demo.api.PluginCode` vào child **không làm** hai class trở thành cùng runtime package. Cố truy cập trái phép có thể gây `IllegalAccessError` trong quá trình liên kết/thực thi, tùy trường hợp.

Khi xây dựng plugin, đặt hợp đồng chung ở **public exported API** theo thiết kế phù hợp; không trông chờ “đều nằm trong package `demo.api`” để chia sẻ thành viên mặc định.

## 8. Tại sao đôi khi parent vẫn có thể gọi mã ở child?

Một chương trình host vốn được parent nạp vẫn có thể làm việc với object plugin thông qua hai cơ chế:

**Cách 1 — Chủ động dùng loader con.** Ví dụ `Host` gọi `child.loadClass(...)`, phản xạ khởi tạo và chuyển đối tượng về `Greeter`. Đây chính là ví dụ runnable đã thực hiện. Class mà host trực tiếp tham chiếu trong source không nhất thiết phải import implementation plugin.

**Cách 2 — Truyền đối tượng qua giao diện chung.** Loader con tạo instance implement `Greeter`, rồi host nhận instance qua interface. Sau đó host không cần biết tên lớp triển khai. Một framework có thể kết hợp thêm `ServiceLoader.load(Greeter.class, child)` để tìm provider trong JAR plugin có service descriptor phù hợp.

**Thread Context ClassLoader (TCCL)** cũng là một phương thức *chọn loader tra cứu* theo ngữ cảnh. Một thư viện được loader cha định nghĩa có thể hỏi:

~~~java
ClassLoader lookup = Thread.currentThread().getContextClassLoader();
~~~

Nếu framework đặt TCCL thành child loader, thư viện có thể dùng loader đó để tìm class/resource thuộc plugin. Tuy nhiên, **TCCL không sửa quan hệ parent** và không biến `parent.loadClass(...)` thành việc tìm child. Nó chỉ cho phép code chủ động chọn một loader khác. Khi đặt TCCL tạm thời, phải khôi phục trong `finally` để tránh ảnh hưởng các tác vụ khác trên cùng thread.

## 9. Những trường hợp ngoại lệ và giới hạn của mô hình

### 9.1. Child-first loader

Một số plugin framework hoặc application server cài chiến lược **child-first**: thử nguồn riêng của child trước rồi mới hỏi parent (thường vẫn ngoại lệ cho các class quan trọng của JDK). Điều này thay đổi **ưu tiên** khi parent và child cùng có một tên class, không loại bỏ yêu cầu runtime type identity.

Child-first có thể khiến plugin dùng thư viện phụ thuộc phiên bản riêng nhưng cũng dễ dẫn tới `ClassCastException`, `LinkageError` hoặc `ServiceConfigurationError` nếu plugin tự định nghĩa cả API mà host đang dùng.

### 9.2. JPMS và module layers

Các module có quy tắc **readability**, `exports` và `opens` ngoài quan hệ loader. ClassLoader có thể được liên kết với named modules; việc resolve class giữa module không luôn tuân một sơ đồ “chỉ parent trước rồi mới child” đơn giản.

Đặc biệt, trong `ModuleLayer`, cùng tên class trong các module hoặc loader khác nhau có thể chịu các constraint riêng. Muốn biết code có thể truy cập class hay không, xem cả loader **và** khả năng đọc/export của module.

### 9.3. Bootstrap và loader `null`

`Class.getClassLoader() == null` thường có nghĩa class được **bootstrap loader** định nghĩa, không có nghĩa lớp “không được nạp”. Bootstrap loader thường là ancestor cuối cùng khi child loader sử dụng parent-first. Một loader có parent `null` không mặc nhiên thấy toàn bộ application classpath.

### 9.4. Class visibility không phải security boundary

ClassLoader phân chia namespace và nguồn tìm class; nó **không phải sandbox** cho plugin không tin cậy. Một plugin chạy cùng JVM có thể thực thi mã với quyền của tiến trình host. Nếu cần cách ly quyền truy cập hệ thống, sử dụng ranh giới tiến trình/container và cơ chế kiểm soát thích hợp.

## 10. Lỗi thường gặp khi suy luận về khả năng nhìn thấy

| Hiện tượng | Hiểu nhầm phổ biến | Phân tích đúng |
|---|---|---|
| `child.loadClass("demo.api.Greeter")` thành công | “Class này do child định nghĩa” | Có thể chính parent đã định nghĩa class, child chỉ ủy quyền |
| `parent.loadClass("demo.plugin.HelloGreeter")` thất bại | “Host không thể dùng plugin” | Host có thể giữ tham chiếu child và gọi `child.loadClass`, hoặc nhận plugin qua API |
| Child có một file `Greeter.class` riêng nhưng host cast thất bại | “Cùng FQCN thì là cùng class” | Nếu hai loader thực sự tự định nghĩa hai bản, runtime type khác nhau |
| `child.getResource(...)` trả resource của parent | “Resource đã được copy vào child” | Parent-first resource lookup có thể trả URL thuộc parent |
| Hai child cùng trỏ một JAR mà class khác nhau | “JVM nạp sai cùng một file” | Identity gồm tên class **và defining loader** |
| Class tìm được nhưng truy cập member lỗi | “Tìm thấy class nghĩa là có mọi quyền” | Java access control, runtime package và JPMS vẫn áp dụng |
| `ServiceLoader` không tìm được plugin | “Parent nên tự tìm provider bên child” | Truyền loader plugin rõ ràng hoặc cấu hình TCCL đúng cách |
| `ClassNotFoundException` và `NoClassDefFoundError` bị đánh đồng | “Đều chỉ là file class không tồn tại” | `ClassNotFoundException` thường từ yêu cầu tìm tên; `NoClassDefFoundError` có thể xảy ra khi liên kết/phụ thuộc ở runtime |
| Plugin dependency cùng tên thư viện với host | “Child luôn lấy thư viện của mình” | Parent-first thường ưu tiên bản ở parent; child-first có thể đổi ưu tiên và tạo xung đột |

## 11. Quy tắc thiết kế plugin theo visibility

1. **Định vị hợp đồng API:** Interface/DTO dùng để trao đổi giữa host và plugin nên được định nghĩa bởi loader có thể dùng chung, thường là loader của host.
2. **Chọn parent có chủ đích:** Nếu plugin cần gọi API host, dùng `SomeHostApi.class.getClassLoader()` làm parent (hoặc loader được chứng minh nhìn thấy API đó). Chọn platform loader sẽ thường **không** thấy classpath ứng dụng host.
3. **Giữ implementation ở nguồn riêng:** Plugin implementation và dependency riêng nên nằm trong child JAR URL; tránh vô tình đưa chúng lên classpath host khi muốn child định nghĩa.
4. **Xác minh bằng định danh thật:** So sánh `SomeClass.class.getClassLoader()`, `loaderA == loaderB`, `Class<?> == Class<?>` thay vì chỉ nhìn tên package hoặc in hash code.
5. **Quản lý vòng đời:** `URLClassLoader.close()` đóng nguồn tài nguyên, nhưng không buộc JVM lập tức unload class. Muốn giải phóng loader cũ phải dọn các tham chiếu tới class/object/loader, thread, callback, cache và tài nguyên plugin liên quan.
6. **Chẩn đoán cả resource:** Khi dùng `ServiceLoader`, kiểm tra `META-INF/services/...` và loader lookup. Khi dùng JPMS, kiểm tra cả cấu hình module.

## 12. Câu hỏi thực hành

**Câu 1.** Parent định nghĩa `com.app.Api`, child định nghĩa `com.plugin.Impl implements Api`. Lệnh `child.loadClass("com.app.Api")` trả về class do loader nào định nghĩa?

**Đáp án:** Thông thường là class do **parent** định nghĩa, nếu child tuân parent-first và parent nhìn thấy API. Việc dùng `child.loadClass` không thay đổi defining loader.

**Câu 2.** Tại sao `parent.loadClass("com.plugin.Impl")` ném `ClassNotFoundException` nhưng host vẫn tạo được instance `Impl`?

**Đáp án:** Parent không tìm ngược các class riêng của child. Host có thể gọi **`child.loadClass("com.plugin.Impl")`** rồi reflection tạo instance và ép sang interface chung do parent định nghĩa.

**Câu 3.** Hai `URLClassLoader` khác nhau cùng đọc một JAR, cùng nạp class có FQCN `com.plugin.Impl`. Hai kết quả `Class<?>` có bằng `==` không?

**Đáp án:** **Không** nếu mỗi loader thật sự tự định nghĩa class. Chúng là hai runtime type khác nhau. Trường hợp class được parent định nghĩa và hai child chỉ ủy quyền thì có thể **bằng nhau**.

**Câu 4.** Đặt TCCL bằng child có thay đổi `parent.loadClass(...)` để nó tự tìm từ child không?

**Đáp án:** **Không.** TCCL chỉ là tham chiếu loader do thread giữ để mã gọi chủ động dùng. Nó không đảo hướng ủy quyền của `parent.loadClass`.

**Câu 5.** Plugin cùng package name với class host có thể tự đọc package-private member của class host không?

**Đáp án:** Không mặc nhiên. Hai class được các loader khác nhau định nghĩa thuộc **runtime package khác nhau**; còn phải xét thêm ràng buộc module và quyền truy cập.

## 13. Tài liệu chính thức

- [Java SE 17 — ClassLoader: delegation, loadClass, getResource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java SE 17 — Class.getClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader())
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java Virtual Machine Specification 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)

**Ghi nhớ:** Với parent-first delegation, **loader con có thể nhờ cha tìm lớp, nhưng cha không tự tìm xuống con**. Child dùng chung API do cha định nghĩa và vẫn tự định nghĩa implementation từ JAR riêng; bản sắc runtime class phụ thuộc **tên lớp + defining loader**.