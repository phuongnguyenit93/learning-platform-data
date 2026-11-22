# Vì sao loader cha không tự tìm phụ thuộc của loader con?

## 1. Vấn đề cốt lõi: quan hệ cha–con không tạo quyền nhìn hai chiều

Trong cơ chế nạp lớp Java thông thường, khi một **child class loader** cần một lớp, nó thường hỏi **parent class loader** trước. Nếu parent không tìm được, child mới thử tìm trong nguồn bytecode riêng của mình. Đây là **parent-first delegation**.

Chiều ngược lại **không tự xảy ra**: khi một lớp do parent định nghĩa cần một kiểu phụ thuộc, JVM dùng ngữ cảnh nạp lớp của chính lớp parent đó để resolve kiểu. JVM không đi tìm trong tất cả những child loader có thể tồn tại. Vì vậy:

> **Child thường nhìn được lớp của parent qua delegation; parent không mặc nhiên nhìn được lớp chỉ do child cung cấp.**

Một ví dụ phổ biến là framework nằm trên application classpath, còn plugin được mở từ thư mục/JAR riêng bằng `URLClassLoader` con. Framework có thể biết interface chung `PluginApi`, nhưng nếu từ framework gọi trực tiếp một class cụ thể chỉ nằm trong plugin JAR, parent loader thường không tìm thấy nó. Điều này vẫn đúng khi plugin đã được child loader nạp thành công.

**Không nhầm hai vấn đề:**

1. **Visibility / lookup:** loader đang được hỏi có tìm và định nghĩa/nhận được lớp theo binary name không?
2. **Type identity / linkage:** nếu lớp có thể được nạp, lớp nào thực sự được định nghĩa bởi loader nào, và kiểu đó có tương thích ở các ranh giới lời gọi không?

Để giải thích vì sao parent không tự tìm dependency của child, trước hết phải hiểu **hướng tìm kiếm** và **loader được JVM dùng khi resolve tham chiếu từ bytecode**.

## 2. Hướng ủy quyền và giới hạn của parent
`ClassLoader.loadClass` mặc định theo trình tự `findLoadedClass` → parent/bootstrap → `findClass` của child. Child nhờ parent tìm API chung; parent không tự có danh sách mọi child, nên `parent.loadClass("plugin.Helper")` không thể nhìn vào nguồn riêng của child trừ khi parent đã được cấu hình một đường lookup khác.
```text
Child → Parent: có thể trả Class của parent
Parent → Child: không có cạnh reverse-delegation mặc định
```
Lưu ý parent-first là chính sách mặc định, không bắt buộc mọi custom loader hay loader gắn với JPMS phải dùng đúng cùng thuật toán. Quan trọng hơn, như §3 giải thích, **bytecode của class parent khi resolve phụ thuộc vẫn dùng loader định nghĩa class parent**, kể cả khi child là caller.

## 3. Điểm quan trọng nhất: phụ thuộc của một lớp được resolve theo defining loader

Giả sử bytecode của lớp `Host` có câu lệnh:

~~~java
return plugin.Helper.message();
~~~

Tham chiếu biểu tượng trong constant pool của `Host` chứa tên kiểu `plugin.Helper` và thông tin thành viên `message`. Khi JVM cần resolve tham chiếu đó, nó sử dụng **defining loader của lớp chứa tham chiếu**, tức loader đã định nghĩa `Host`, để bắt đầu việc nạp kiểu cần tham chiếu. Nó không tự dùng:

- Loader của bất kỳ đối tượng nào tình cờ gọi phương thức `Host`.
- Thread context class loader, trừ khi mã Java/framework chủ động dùng API đọc giá trị đó.
- Loader con đã nạp một lớp cùng tên ở nơi khác.
- “Loader mới nhất” hoặc “loader gần nhất” xuất hiện trong stack trace.

Đây là quy tắc quan trọng trong **JVMS §5.3 và §5.4.3**: resolution gắn với lớp đang chứa symbolic reference. Nếu `Host` thuộc parent thì phép resolve `plugin.Helper` do parent khởi xướng; khi parent không có nguồn này và không có đường ủy quyền phù hợp, nó thất bại. Child có thể đã nạp `plugin.Helper` nhưng điều đó **không bổ sung tự động lớp vào không gian tìm kiếm của parent**.

Đổi hướng gọi thành `child.loadClass("Host")` cũng không giúp: nếu delegation trả về bản `Host` do parent định nghĩa, các dependency trong bytecode `Host` vẫn dùng loader của `Host`.

### Defining loader khác initiating loader

- **Defining loader:** loader thực sự định nghĩa class/interface từ biểu diễn của nó. Danh tính kiểu runtime của class/interface phụ thuộc **binary name + defining loader**.
- **Initiating loader:** loader được JVM ghi nhận là tham gia khởi đầu nạp kiểu. Một child có thể là initiating loader cho lớp do parent định nghĩa khi delegation thành công.
- `SomeType.class.getClassLoader()` báo **defining loader** của class/interface thông thường, không phải nhất thiết loader mà người gọi trực tiếp sử dụng.
- Việc `parent.loadClass("plugin.Helper")` thất bại không chứng minh `plugin.Helper` không tồn tại trong toàn JVM; nó chỉ chứng minh loader và chính sách tra cứu ấy không tìm được kiểu theo yêu cầu.

Điều này cũng giải thích vì sao một lớp Java có thể đã được nạp bởi child nhưng lời gọi bên parent vẫn gặp `ClassNotFoundException` hoặc `NoClassDefFoundError`.

## 4. Thí nghiệm chạy được: parent không tìm thấy child-only dependency

Thí nghiệm dùng hai thư mục output để tạo **hai nguồn classpath tách biệt**. `Host` và `Demo` chạy từ application classpath. `Plugin` và `Helper` chỉ nằm trong thư mục được child `URLClassLoader` đọc. Trong bước **biên dịch**, `Host` được cấp `Helper` trên compile classpath; trong bước **chạy**, thư mục plugin không nằm trong application classpath. Đây là chủ ý để mô phỏng tình huống compile thấy dependency nhưng runtime parent không thấy.

Cấu trúc file nguồn:

~~~text
example/
├── app/
│   ├── Host.java
│   └── Demo.java
└── plugin/
    └── child/
        ├── Helper.java
        └── Plugin.java
~~~

### File `plugin/child/Helper.java`

~~~java
package child;

public class Helper {
    public static String message() {
        return "helper ready";
    }
}
~~~

### File `plugin/child/Plugin.java`

~~~java
package child;

public class Plugin {
    public static String run() {
        return Helper.message();
    }
}
~~~

`Plugin` và `Helper` cùng thuộc nguồn bytecode riêng của child.

### File `app/Host.java`

~~~java
public class Host {
    public static String callChildDependency() {
        return child.Helper.message();
    }
}
~~~

`Host` được định nghĩa bởi application/system loader khi chạy. Dù compile thành công, nó vẫn cần resolve `child.Helper` khi gọi `callChildDependency()`.

### File `app/Demo.java`

~~~java
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class Demo {
    public static void main(String[] args) throws Exception {
        ClassLoader parent = Demo.class.getClassLoader();

        try {
            parent.loadClass("child.Helper");
            System.out.println("parent unexpectedly found Helper");
        } catch (ClassNotFoundException expected) {
            System.out.println("parent: ClassNotFoundException");
        }

        try {
            System.out.println("Host: " + Host.callChildDependency());
        } catch (NoClassDefFoundError expected) {
            System.out.println("Host: NoClassDefFoundError");
        }

        URL pluginUrl = Path.of(args[0]).toUri().toURL();
        try (URLClassLoader child =
                     new URLClassLoader(new URL[]{pluginUrl}, parent)) {
            Class<?> plugin = child.loadClass("child.Plugin");
            System.out.println("Plugin defined by child: "
                    + (plugin.getClassLoader() == child));

            Method run = plugin.getMethod("run");
            System.out.println("Plugin: " + run.invoke(null));

            System.out.println("Host via child is parent class: "
                    + (child.loadClass("Host") == Host.class));

            try {
                Host.callChildDependency();
                System.out.println("Host unexpectedly resolved Helper");
            } catch (NoClassDefFoundError expected) {
                System.out.println("Host still: NoClassDefFoundError");
            }
        }
    }
}
~~~

### Biên dịch và chạy trên Linux/macOS (Bash)

Đứng trong thư mục `example/`, sử dụng JDK 17 trở lên:

~~~bash
mkdir -p out/plugin out/app
javac -d out/plugin plugin/child/Helper.java plugin/child/Plugin.java
javac -cp out/plugin -d out/app app/Host.java app/Demo.java
java -cp out/app Demo out/plugin
~~~

Các lệnh này **cố ý không thêm** `out/plugin` vào runtime `-cp`. Nó chỉ được dùng làm compile classpath của `Host` hoặc làm URL riêng cho child loader. Trên Windows, có thể tạo hai thư mục bằng `mkdir out\plugin` và `mkdir out\app` trong PowerShell, sau đó chạy cùng các lệnh `javac`/`java` với dấu phân cách đường dẫn thích hợp.

### Stdout đã kiểm chứng

~~~text
parent: ClassNotFoundException
Host: NoClassDefFoundError
Plugin defined by child: true
Plugin: helper ready
Host via child is parent class: true
Host still: NoClassDefFoundError
~~~

### Phân tích từng dòng

1. `parent.loadClass("child.Helper")` kiểm tra các nguồn parent nhìn thấy; `out/plugin` không nằm trên runtime classpath của parent, nên ném `ClassNotFoundException`.
2. `Host.callChildDependency()` thực thi bytecode tham chiếu `child.Helper`. JVM resolve dependency trong ngữ cảnh defining loader của `Host`, tức parent; khi thất bại, quá trình liên kết cần lớp này tạo `NoClassDefFoundError` (với nguyên nhân liên quan không tìm thấy class).
3. Child `URLClassLoader` tìm `child.Plugin` từ `out/plugin`, vì parent không có nó, nên `plugin.getClassLoader() == child` là `true`.
4. `Plugin.run()` gọi `Helper.message()`. `Plugin` do child định nghĩa; khi resolve `Helper`, child tìm được tệp class trong cùng nguồn, nên in `helper ready`.
5. Khi gọi `child.loadClass("Host")`, child hỏi parent và nhận `Host.class`; nó không tạo bản sao `Host`. Bởi vậy kết quả so sánh là `true`.
6. Gọi `Host.callChildDependency()` thêm một lần vẫn không khiến parent đổi hướng sang child. Lỗi còn đó; việc plugin đã được child nạp không chuyển quyền định nghĩa/resolve phụ thuộc của `Host`.

**Điều thí nghiệm chứng minh:** parent không tự tìm class riêng của child, và dependency lookup của mã parent không đổi theo loader của caller. Nếu chạy sai lệnh và thêm `out/plugin` vào `java -cp`, parent sẽ tìm được `Helper` ngay từ đầu, làm mất điều kiện của thí nghiệm.

## 5. Vì sao JVM không tự quét mọi loader con?

### 5.1. Không có đồ thị children chuẩn để duyệt

Một `ClassLoader` được khởi tạo với tham chiếu đến parent. Chiều ngược lại không phải một registry chuẩn bắt buộc. Ứng dụng có thể tạo, bỏ, thay thế nhiều child loader để cách ly plugin, test, hot reload hoặc nhiều phiên bản thư viện.

Parent không biết phải chọn child nào nếu có:

~~~text
           Parent
        /    |     \
   Child A Child B Child C
   Helper v1 Helper v2 (không có Helper)
~~~

Nếu parent tự quét, câu hỏi “`Helper` của phiên bản nào?” trở thành mơ hồ. Chính sách parent-first và ngữ cảnh defining loader giúp hành vi có thể giải thích bằng một đường tra cứu xác định, thay vì phụ thuộc thứ tự chạy hoặc danh sách loader tình cờ còn sống.

### 5.2. Bảo toàn isolation và danh tính kiểu

Hai child khác nhau có thể cùng định nghĩa `plugin.Helper` từ bytecode khác nhau. JVM coi chúng là **hai kiểu runtime khác nhau** vì defining loader khác nhau. Parent không thể tùy tiện chọn một trong hai mà vẫn bảo đảm mọi lời gọi được liên kết kiểu an toàn.

Ngay cả khi tên và source nhìn giống nhau, casting giữa hai lớp cùng binary name do loader khác nhau định nghĩa có thể thất bại. Với API giao tiếp giữa parent và child, các class/interface thuộc hợp đồng chung nên được định nghĩa ở một loader chung (thường là parent) để cả hai phía dùng cùng định danh kiểu.

### 5.3. Không làm lớp thư viện cha phụ thuộc tùy tiện vào plugin con

Nếu parent tự nạp mọi thứ từ child, framework và thư viện dùng chung sẽ khó đảm bảo độc lập: một plugin có thể làm đổi kết quả tìm lớp của plugin khác, hoặc khiến framework vô tình nhận lớp không thuộc phạm vi thiết kế. Parent-first mặc định hỗ trợ chia sẻ API ổn định và đóng gói phụ thuộc riêng trong từng child.

Đây là **cơ chế tổ chức không gian tên và phân giải kiểu**, không phải ranh giới sandbox bảo mật tuyệt đối. Việc dùng custom class loader không tự khiến bytecode không đáng tin trở nên an toàn.

## 6. Phân biệt các tình huống thường nhầm

| Tình huống | Parent thấy lớp child? | Lý do |
| --- | --- | --- |
| `child.loadClass("api.Contract")`, `Contract` nằm ở parent | Không cần parent thấy child | Child ủy quyền lên parent và nhận class chung. |
| `parent.loadClass("plugin.Helper")`, `Helper` chỉ ở child | Thường không | Parent không tự hỏi các child. |
| Lớp `Host` do parent định nghĩa tham chiếu trực tiếp `plugin.Helper` | Thường không | Resolution từ `Host` bắt đầu bằng defining loader của `Host`. |
| Child gọi phương thức `Host.doWork()` của parent, và `Host` tham chiếu tới plugin | Không tự động | Loader của caller không thay loader gắn với `Host`. |
| `child.loadClass("Host")` trả class của parent | Vẫn là class parent | Delegation không tạo bản class mới. |
| App đặt plugin JAR lên chính runtime classpath của parent | Có thể | Bấy giờ dependency đã ở nguồn parent; ví dụ isolation child không còn đúng. |
| Parent chủ động gọi `Class.forName("plugin.Helper", false, child)` | Có thể tìm được | Đây là **chủ động chỉ định child** trong API, khác với tự tìm thông qua parent-first. |
| Framework dùng thread context class loader để tìm plugin | Có thể | Chỉ khi mã/framework **thực sự dùng** context loader; JVM không tự dùng TCCL cho mọi resolution. |
| Một custom parent được lập trình riêng để hỏi child | Có thể, theo thiết kế | Đây là custom lookup/reverse delegation, không phải mặc định của `ClassLoader`. |

**Không đồng nhất `ClassNotFoundException` và `NoClassDefFoundError`:** gọi `ClassLoader.loadClass` trực tiếp thường báo `ClassNotFoundException` khi không tìm được lớp. Khi JVM resolve một symbolic reference cần class không thể nạp, code sử dụng class có thể thấy `NoClassDefFoundError`. Thông điệp và cause giúp xác định nơi lỗi xảy ra. Ngoài ra, `NoClassDefFoundError` có thể có nguyên nhân khác (ví dụ khởi tạo lớp đã thất bại).

## 7. Cách thiết kế đúng khi framework ở parent, plugin ở child

### 7.1. Đặt hợp đồng giao tiếp ở parent

Giả sử framework định nghĩa:

~~~java
package api;

public interface Plugin {
    String execute();
}
~~~

Plugin do child định nghĩa có thể viết:

~~~java
package plugin;

import api.Plugin;

public class GreetingPlugin implements Plugin {
    @Override
    public String execute() {
        return "Hello from plugin";
    }
}
~~~

Hai đoạn mã là **hai tệp riêng**, lần lượt có tên `api/Plugin.java` và `plugin/GreetingPlugin.java`. Chúng chỉ minh họa giao diện đặt ở parent và triển khai trong child; không phải một chương trình độc lập như ví dụ ở phần 4.

Loader con ủy quyền nạp `api.Plugin` cho parent. Framework có thể nạp class triển khai bằng child loader và ép về `api.Plugin` chung:

~~~java
Class<?> implementation = Class.forName("plugin.GreetingPlugin", true, childLoader);
api.Plugin plugin =
        (api.Plugin) implementation.getDeclaredConstructor().newInstance();
String result = plugin.execute();
~~~

Đoạn mã này nằm trong framework đã có biến `childLoader` và API chung. Khi runtime thực thi, class triển khai tồn tại trong nguồn riêng child, constructor có thể truy cập được, và `api.Plugin` chỉ có một defining loader dùng chung. Đây là cách kết nối qua interface thay vì để parent hard-code một class chỉ nằm trong child.

**Sai lầm dễ gặp:** đưa một bản sao `api.Plugin` vào plugin JAR rồi dùng child-first để định nghĩa bản thứ hai. Dù tên `api.Plugin` giống nhau, hai `Class` khác nhau có thể gây `ClassCastException` hoặc lỗi loading constraint. Với API chung, cố gắng thiết kế sao cho plugin **ủy quyền về một bản API duy nhất**.

### 7.2. Dùng loader được truyền tường minh để nạp plugin

Khi cần lớp cụ thể ở child, parent có thể nhận một `ClassLoader` từ thành phần quản lý plugin, rồi gọi:

~~~java
Class<?> pluginType = Class.forName(
        "plugin.GreetingPlugin", true, pluginLoader);
~~~

Đây là **mã ứng dụng chủ động** chọn loader; nó không thay đổi nguyên tắc bytecode trong một class parent vốn tham chiếu tĩnh tới `plugin.Helper`. Chỉ việc gọi `Class.forName` ở một chỗ không khiến mọi tham chiếu khác trong parent tự chuyển sang child.

Khi làm plugin manager, quản lý vòng đời `URLClassLoader`, đóng loader khi không còn dùng, và tránh giữ tham chiếu tới `Class`/object/loader plugin nếu muốn có thể giải phóng bộ nhớ. Việc đóng URLClassLoader chỉ giải phóng tài nguyên của nó; nó không trực tiếp “unload” mọi lớp nếu còn tham chiếu sống.

### 7.3. Service Provider Interface và Thread Context ClassLoader

Một thư viện trong parent đôi khi cần tìm implementation nằm trong ứng dụng/plugin child. Thư viện có thể **cố ý dùng** *thread context class loader* (TCCL):

~~~java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();
~~~

Các API như `ServiceLoader.load(service)` mặc định dùng thread context class loader của luồng đang chạy. Với API service ở parent và provider ở child, caller/framework có thể cấu hình TCCL hoặc gọi `ServiceLoader.load(service, childLoader)` để chọn phạm vi khám phá provider. Điều này còn phụ thuộc cấu hình service metadata, module/provider accessibility và cùng danh tính interface giữa hai phía.

**TCCL không phải sửa đổi toàn cục quy tắc parent-first:** JVM không tự lấy TCCL khi resolve mọi symbolic reference. Chỉ những API/library chủ động truy xuất và dùng nó mới có tác dụng đổi nơi tìm lớp. TCCL cũng là trạng thái theo luồng, nên nếu tạm đổi cần khôi phục trong `finally`:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();
try {
    current.setContextClassLoader(pluginLoader);
    // Gọi framework/API có hợp đồng sử dụng context loader.
} finally {
    current.setContextClassLoader(previous);
}
~~~

Đoạn này giả định `pluginLoader` đã được tạo ở nơi khác; nó minh họa cách giữ nguyên trạng thái luồng sau lời gọi.

### 7.4. Khi nào cần child-first hoặc reverse delegation?

Một số container/module/plugin system tự định nghĩa chính sách class loading, thí dụ ưu tiên thư viện của plugin thay vì phiên bản ở host. Khi đó có thể override `loadClass`, nhưng phải giữ ràng buộc đồng bộ `getClassLoadingLock(name)`, kiểm tra `findLoadedClass`, dùng `resolveClass` đúng lúc và bảo vệ API nền tảng/kiểu chia sẻ khỏi việc định nghĩa bản trùng.

Child-first cho phép **child ưu tiên tự tìm** trước parent; nó **không làm parent tự biết children**. Nếu cần parent tìm implementation của child, phải thiết kế một registry, SPI, API nạp qua loader được chọn hoặc cơ chế giao tiếp tường minh. Không sửa class loader cha của JDK theo kiểu quét mọi class loader con.

## 8. Những bẫy thường gặp khi debug

1. **Compile thành công rồi runtime lỗi:** compiler có thể thấy dependency qua compile classpath, nhưng loader của class chứa tham chiếu không thấy nó tại runtime. Hãy kiểm tra *compile classpath*, *runtime classpath* và URL riêng của child; chúng không nhất thiết trùng nhau.
2. **Nhầm classpath của parent với nguồn child:** đặt JAR trong thư mục plugin không tự thêm nó vào system loader. Nếu child giữ URL tới JAR, chỉ child có cơ chế tìm trong URL đó.
3. **Nhìn stack trace rồi đoán loader:** một hàm parent được gọi từ plugin không đổi defining loader của hàm đó. Kiểm tra `Host.class.getClassLoader()` và `PluginImpl.class.getClassLoader()`.
4. **Nhầm “đã load ở đâu đó” với “mọi loader đều thấy”:** không có bảng toàn JVM bảo đảm mọi loader trả cùng `Class<?>` chỉ vì tên giống nhau.
5. **Tưởng `Thread.currentThread().setContextClassLoader(child)` sửa mọi lỗi:** resolution bytecode của `Host` vẫn dùng loader gắn với `Host`. TCCL chỉ giúp ở API/framework có dùng nó.
6. **Nạp bản sao shared API ở child:** hai bản `api.Plugin` cùng tên nhưng khác defining loader không đảm bảo cast được. Chia sẻ API qua parent.
7. **Bắt nhầm exception:** `ClassNotFoundException` là checked exception từ tra cứu tường minh; lỗi khi JVM resolve có thể là `NoClassDefFoundError`. Đọc `getCause()` và chain nguyên nhân.
8. **Cho rằng mọi JDK loader đều là cây parent-first tuyệt đối:** từ Java 9, module system có các ngoại lệ và cơ chế delegation phức tạp hơn. Phân tích từng loader và policy thay vì khái quát quá mức.

### Checklist chẩn đoán ngắn

Khi một class chỉ nằm ở plugin child mà parent không tìm thấy, hãy trả lời lần lượt:

- Class nào đang chứa symbolic reference tới phụ thuộc, và `ThatClass.class.getClassLoader()` là gì?
- Dependency có mặt trong nguồn/JAR mà **loader đó** có thể tra cứu không?
- Loader con nào đang giữ dependency? Có bị chồng tên/phiên bản với parent hoặc sibling không?
- Framework có hợp đồng SPI/loader argument/TCCL để tìm implementation mà không cần static reference trực tiếp không?
- Shared API có do parent định nghĩa duy nhất không?
- Exception xảy ra trong `loadClass` trực tiếp hay trong JVM linking/resolution/initialization?

## 9. Câu hỏi tự kiểm tra

**Tình huống A:** `Plugin` do child định nghĩa gọi `PluginHelper` do child định nghĩa. Child hỏi parent, parent không có, child `findClass` thành công. Vì sao chạy được?

**Đáp:** Vì resolution của `Plugin` do chính defining loader của `Plugin` khởi xướng; child là loader có nguồn `PluginHelper` nên tìm được sau khi parent không tìm thấy.

**Tình huống B:** `Host` do parent định nghĩa, một child gọi `Host.invoke()`. Trong `Host.invoke()` có tham chiếu trực tiếp `PluginHelper` chỉ nằm ở child. JVM có dùng child để resolve phụ thuộc của `Host` không?

**Đáp:** Không theo class-loading mặc định. Dependency trong bytecode của `Host` được resolve với defining loader của `Host`, tức parent. Hướng gọi phương thức không đổi loader định nghĩa `Host`.

**Tình huống C:** Có thể làm framework tìm provider của plugin mà không thêm toàn bộ plugin JAR vào parent không?

**Đáp:** Có. Đặt interface chung ở parent, cho child nạp implementation, và dùng loader tường minh/SPI/TCCL trong các API có thiết kế hỗ trợ. Child chỉ cần thấy parent API và nguồn implementation của mình.

## Tài liệu chuẩn

- [Java SE 21 – ClassLoader: parent delegation, loadClass và findClass](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html).
- [JVM Specification Java SE 21, §5.3 – Loading, Defining và Initiating Loader](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3).
- [JVM Specification Java SE 21, §5.4.3 – Resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3).
- [Java SE 21 – ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): lựa chọn class loader để tìm provider.
- [Java SE 21 – Thread.getContextClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#getContextClassLoader()): thread context loader cho framework/tooling.
