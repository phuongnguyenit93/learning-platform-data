# Cơ chế ủy quyền cho loader cha và phạm vi nhìn thấy giữa các ClassLoader trong Java

## 1. Vì sao cần hiểu ranh giới giữa các loader?

Trong Java, cùng một JVM có thể sử dụng nhiều **ClassLoader** để nạp các lớp từ classpath, module path, các JAR plugin hoặc thư mục được thêm lúc chạy. Khi xây dựng một hệ thống có khả năng mở rộng (runtime extensibility), host thường cần dùng chung một API/SPI với các plugin nhưng vẫn muốn mỗi plugin giữ các implementation và dependency riêng.

Hai câu hỏi dễ bị nhầm là:

- **Ai được yêu cầu tìm một lớp?** Ví dụ: childLoader.loadClass("demo.api.Task").
- **Loader nào thực sự định nghĩa lớp đó?** Ví dụ: Task được định nghĩa bởi application loader, mặc dù childLoader là bên nhận lời gọi.

Cơ chế **ủy quyền cho loader cha (parent delegation)** quyết định cách tìm lớp theo mặc định. Phạm vi **nhìn thấy (visibility)** mô tả lớp nào có thể được tìm thông qua loader nào, cùng điều kiện truy cập của Java. Chúng liên quan chặt chẽ nhưng không đồng nghĩa: tìm được bytecode chưa chắc có quyền sử dụng lớp, và một lớp đã được load qua child chưa chắc được child định nghĩa.

Với Java 17, hiểu đúng hai cơ chế giúp tránh ClassNotFoundException, ClassCastException, NoClassDefFoundError, xung đột phiên bản thư viện và lỗi nhận diện SPI giữa host với plugin.

## 2. Cây loader và quan hệ cha/con

Một cấu trúc thường gặp trong ứng dụng Java 17:

~~~text
Bootstrap loader (thường được biểu diễn bằng null)
          |
          v
Platform class loader
          |
          v
Application/System class loader
  - Host
  - API/SPI dùng chung
          |
          +------------------------+
          |                        |
          v                        v
   Plugin loader A          Plugin loader B
   - Provider A              - Provider B
   - Thư viện riêng A        - Thư viện riêng B
~~~

Trong cấu trúc này, hai loader A và B cùng có parent là application loader. Đây là một mô hình minh họa phổ biến, không phải một cây cố định mà mọi ứng dụng Java bắt buộc sử dụng.

- **Bootstrap loader** nạp các lớp nền tảng quan trọng. Trong nhiều API Java, Class.getClassLoader() trả về null cho lớp do bootstrap định nghĩa; null là cách biểu diễn, không phải bằng chứng không có cơ chế nạp.
- **Platform class loader** có thể truy cập qua ClassLoader.getPlatformClassLoader(); quản lý nhiều lớp nền tảng/JDK.
- **System/application class loader** lấy qua ClassLoader.getSystemClassLoader(); thông thường xử lý các lớp ứng dụng được đưa vào classpath.
- **Custom loader** như URLClassLoader có thể được tạo với một parent cụ thể và tập URL chứa lớp/plugin. Một loader con có thể là parent của các loader khác.

**Parent ở đây là quan hệ ủy quyền**, không phải quan hệ extends của các Java class tạo loader. ClassLoader A được tạo bởi một đối tượng loader B không có nghĩa B sẽ tự động là parent của A; parent được xác định bởi constructor/cấu hình.

Các built-in loader chịu thêm quy tắc của Java Platform Module System (JPMS). Với named module nâng cấp/đặc biệt, platform loader có thể phải chuyển yêu cầu tới loader khác; đừng suy diễn rằng mọi trường hợp đều là một cây tra cứu cứng nhắc chỉ có ba nút.

## 3. Thuật toán parent-first của ClassLoader.loadClass

Lớp java.lang.ClassLoader có quy ước mặc định cho phương thức loadClass(String, boolean). Ý tưởng chính khi loader L nhận yêu cầu nạp một tên nhị phân là:

1. Kiểm tra lớp đó đã được L nạp hoặc được ghi nhận là đã nạp qua L chưa, bằng **findLoadedClass**.
2. Nếu chưa có, thử **ủy quyền cho parent**. Nếu parent là null, thử đường nạp bootstrap.
3. Nếu parent/bootstrap không tìm thấy, L mới gọi **findClass** để tìm/định nghĩa lớp từ nguồn riêng.
4. Nếu yêu cầu resolve, thực hiện **resolveClass**; sau đó trả về Class tương ứng.

Sơ đồ khái niệm:

~~~text
L.loadClass("pkg.Example")
          |
          v
   findLoadedClass?
      | yes -> return Class
      | no
      v
   parent.loadClass?
      | found -> return Class từ parent
      | ClassNotFoundException
      v
   L.findClass?
      | found -> định nghĩa/trả Class thuộc L
      | not found -> ClassNotFoundException
~~~

Đây là **mã ý tưởng**, không phải toàn bộ source code của JDK. Thực tế còn có lock theo tên lớp, thao tác resolve/linking và xử lý lỗi. Một custom loader có thể ghi đè loadClass để thay đổi chiến lược; vì vậy **parent-first là quy ước mặc định của ClassLoader, không phải quy luật JVM áp đặt cho mọi loader tùy biến**.

Các method thường bị lẫn:

| API | Vai trò |
| --- | --- |
| loadClass(name) | Yêu cầu nạp class theo thuật toán của loader; mặc định thử parent trước |
| findClass(name) | Hook để custom loader tự tìm/định nghĩa class khi đường parent thất bại; không phải API tìm toàn cây |
| defineClass(...) | Chuyển bytecode thành một Class được loader hiện tại định nghĩa, chịu các ràng buộc JVM |
| findLoadedClass(name) | Tìm Class đã được ghi nhận là nạp thông qua loader này |
| resolveClass(clazz) | Thực hiện bước linking/resolution phù hợp; khác với chạy static initializer |
| Class.forName(name, initialize, loader) | Tìm class bằng loader chỉ định và có thể yêu cầu khởi tạo lớp |

**Loading, linking và initialization** không phải một việc. ClassLoader.loadClass tự nó không bảo đảm static initializer đã chạy. Class.forName(name, true, loader) yêu cầu khởi tạo; constructor hoặc truy cập thành viên static có thể kích hoạt khởi tạo theo quy tắc ngôn ngữ. Đừng suy ra "class đã load" nghĩa là "class đã được tạo object".

## 4. Parent thấy gì, child thấy gì, sibling thấy gì?

Giả sử **P** là application loader, **A** và **B** đều có parent P:

| Lớp được định nghĩa ở đâu? | P yêu cầu nạp | A yêu cầu nạp | B yêu cầu nạp |
| --- | --- | --- | --- |
| SharedApi chỉ có ở P | Thành công, Class của P | Thành công qua ủy quyền, Class của P | Thành công qua ủy quyền, Class của P |
| PluginAOnly chỉ có ở A | Không tìm thấy theo cây của P | Thành công, Class của A | Không tìm thấy theo cây của B |
| PluginBOnly chỉ có ở B | Không tìm thấy theo cây của P | Không tìm thấy theo cây của A | Thành công, Class của B |
| com.demo.Impl có bản riêng ở cả A và B, không có ở P | Không tìm thấy | Class của A | Class của B |
| com.demo.Version có bản ở P và bản khác ở A | Class của P | **Class của P** theo parent-first | Class của P nếu B cũng ủy quyền cho P |

Những kết quả này giả định các loader chuẩn parent-first, các thư mục/JAR không bị bổ sung vào classpath cha và không có quy tắc delegation tùy biến.

### 4.1. Child thường thấy lớp của ancestor

A yêu cầu tải SharedApi; A thử parent P trước. Vì P có lớp, A nhận **chính Class do P định nghĩa**, không tự tạo bản sao. B cũng nhận cùng Class này. Nhờ đó một provider ở A hoặc B có thể implements cùng một interface SPI mà host dùng.

### 4.2. Parent không tự động thấy lớp riêng của child

P không duyệt xuống các con để tìm PluginAOnly. Đồ thị ủy quyền mặc định đi **từ child lên parent**, không tự tìm các loader con. Vì vậy một thư viện nạp bằng P sẽ không tự động phát hiện lớp nằm trong A nếu nó chỉ gọi P.loadClass(name).

Tuy nhiên, host có thể **chủ động giữ tham chiếu tới A rồi gọi A.loadClass(name)**; framework cũng có thể nhận loader A qua tham số hoặc thread context class loader. Đây là việc sử dụng A một cách tường minh, không phải parent đã có quyền nhìn xuống con theo mặc định.

### 4.3. Hai loader sibling không tự nhìn thấy nhau

A và B có cùng parent P; A không trở thành parent của B và ngược lại. Khi B tìm một class chỉ nằm trong A, B thử P rồi thử nguồn riêng của B, không tự hỏi A. Muốn giao tiếp giữa hai plugin, cần một **API dùng chung ở parent**, hoặc cơ chế bridge/registry có chủ đích; không lấy class riêng của A làm hợp đồng trực tiếp mà B phải ép kiểu.

## 5. Class identity: trùng tên không có nghĩa cùng lớp

Trong JVM, identity của một reference type gắn với **tên nhị phân và defining class loader**. Vì vậy hai bản demo.provider.TaskImpl do A và B định nghĩa có thể cùng Class.getName() nhưng là hai Class khác nhau:

~~~java
// Minh họa trong một host đã có hai loader A, B:
Class<?> a = loaderA.loadClass("demo.provider.TaskImpl");
Class<?> b = loaderB.loadClass("demo.provider.TaskImpl");
boolean same = (a == b); // false nếu A và B tự định nghĩa hai bản độc lập
~~~

Một object của TaskImpl-A không thể tùy tiện cast sang TaskImpl-B. Khi hai class trùng tên nhưng identity khác nhau, ClassCastException vẫn có thể xảy ra; nhìn tên trong stack trace không đủ để hiểu nguyên nhân. Quan hệ assignability cũng phụ thuộc vào đúng Class object, không chỉ chuỗi tên.

Mặt khác, nếu cả hai TaskImpl đều implements **demo.api.Task do parent P định nghĩa**, host có thể cast mỗi instance thành Task của P:

~~~text
Task interface: P định nghĩa
         ^                 ^
         |                 |
TaskImpl-A (A)        TaskImpl-B (B)
         |                 |
   cast thành Task    cast thành Task
         \                 /
          \               /
            Host sử dụng
~~~

Đây là nền tảng của kiến trúc plugin: **chia sẻ API/SPI ổn định qua loader chung; cô lập implementation và dependency bên dưới**. Cẩn trọng nếu mỗi plugin vô tình đóng gói thêm một bản API nhưng custom loader dùng child-first: lúc đó interface có thể bị định nghĩa nhiều lần và mất khả năng gán kiểu cho host.

## 6. Ví dụ Java 17+ chạy được: hai loader con và một API chung

Bài thực hành sau minh họa đồng thời:

- Hai loader con có chung một parent và nhận cùng Class cho SPI.
- Mỗi loader con định nghĩa một provider **cùng binary name**, nhưng mỗi bản có hành vi khác.
- B không nhìn thấy class chỉ có ở A; parent không tự nhìn thấy provider của con.
- Nếu parent và A cùng chứa một binary name, **parent-first chọn bản ở parent**.

Không cần framework hoặc thư viện ngoài JDK. Các file source được đặt trong thư mục demo theo cây sau:

~~~text
demo/
├── api/
│   └── demo/
│       ├── api/Task.java
│       └── common/Origin.java
├── a/
│   └── demo/
│       ├── provider/TaskImpl.java
│       ├── common/Origin.java
│       └── only/OnlyA.java
├── b/
│   └── demo/
│       └── provider/TaskImpl.java
├── host/
│   └── demo/
│       └── host/Main.java
└── out/
    ├── api/
    ├── a/
    ├── b/
    └── host/
~~~

Lưu ý **out/** là thư mục class đã biên dịch, được tạo bởi lệnh chạy bên dưới. Khi chạy, out/api và out/host nằm trên application classpath; out/a và out/b **không** nằm trên application classpath mà chỉ được truyền làm URL cho loader con.

### 6.1. API thuộc parent

**api/demo/api/Task.java**

~~~java
package demo.api;

public interface Task {
    String id();
}
~~~

**api/demo/common/Origin.java**

~~~java
package demo.common;

public final class Origin {
    public static String where() {
        return "parent";
    }
}
~~~

Origin là lớp minh họa để kiểm tra thứ tự tìm kiếm; không phải SPI. Một bản cùng tên cũng sẽ được biên dịch vào plugin A để quan sát bản nào được chọn.

### 6.2. Hai provider ở hai loader con

**a/demo/provider/TaskImpl.java**

~~~java
package demo.provider;

import demo.api.Task;

public final class TaskImpl implements Task {
    @Override
    public String id() {
        return "alpha";
    }
}
~~~

**a/demo/common/Origin.java**

~~~java
package demo.common;

public final class Origin {
    public static String where() {
        return "child A";
    }
}
~~~

**a/demo/only/OnlyA.java**

~~~java
package demo.only;

public final class OnlyA {
}
~~~

**b/demo/provider/TaskImpl.java**

~~~java
package demo.provider;

import demo.api.Task;

public final class TaskImpl implements Task {
    @Override
    public String id() {
        return "beta";
    }
}
~~~

Hai file TaskImpl có **cùng package, cùng tên class và cùng interface**. Chúng được biên dịch ra hai thư mục độc lập. Khi chạy, URLClassLoader A chỉ tìm out/a sau khi hỏi parent; URLClassLoader B chỉ tìm out/b sau khi hỏi parent.

### 6.3. Host tạo URLClassLoader với cùng parent

**host/demo/host/Main.java**

~~~java
package demo.host;

import demo.api.Task;
import demo.common.Origin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Main {
    private static boolean canLoad(ClassLoader loader, String binaryName) {
        try {
            loader.loadClass(binaryName);
            return true;
        } catch (ClassNotFoundException expected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Expected directories A and B");
        }

        ClassLoader parent = Task.class.getClassLoader();
        URL aUrl = Path.of(args[0]).toUri().toURL();
        URL bUrl = Path.of(args[1]).toUri().toURL();

        try (URLClassLoader childA = new URLClassLoader(new URL[]{aUrl}, parent);
             URLClassLoader childB = new URLClassLoader(new URL[]{bUrl}, parent)) {

            Class<?> aClass = childA.loadClass("demo.provider.TaskImpl");
            Class<?> bClass = childB.loadClass("demo.provider.TaskImpl");

            Task a = (Task) aClass.getDeclaredConstructor().newInstance();
            Task b = (Task) bClass.getDeclaredConstructor().newInstance();

            System.out.println("A: " + a.id());
            System.out.println("B: " + b.id());
            System.out.println("Same provider class: " + (aClass == bClass));
            System.out.println("Shared SPI class: " +
                    (childA.loadClass("demo.api.Task") ==
                     childB.loadClass("demo.api.Task")));
            System.out.println("Parent defines SPI: " +
                    (childA.loadClass("demo.api.Task").getClassLoader() == parent));
            System.out.println("Parent-first duplicate: " +
                    (childA.loadClass("demo.common.Origin") == Origin.class));
            System.out.println("B sees OnlyA: " +
                    canLoad(childB, "demo.only.OnlyA"));
            System.out.println("Parent sees provider: " +
                    canLoad(parent, "demo.provider.TaskImpl"));
        }
    }
}
~~~

**Phân tích lời gọi quan trọng:** parent nhận từ Task.class.getClassLoader(), tức loader đang sở hữu SPI của host. Mỗi URLClassLoader nhận đúng parent đó. Vì parent không có demo.provider.TaskImpl, A và B mới định nghĩa hai bản riêng. Ngược lại, parent có demo.api.Task nên cả A và B trả về cùng một Class cho interface.

### 6.4. Biên dịch và chạy

Đứng tại thư mục **demo/**. Trên Linux/macOS, tạo các thư mục output:

~~~bash
mkdir -p out/api out/a out/b out/host
~~~

Trên Windows PowerShell có thể dùng:

~~~powershell
New-Item -ItemType Directory -Force out/api,out/a,out/b,out/host | Out-Null
~~~

Các lệnh javac sau chạy được trên cả hai hệ thống vì mỗi lệnh chỉ có **một classpath entry**:

~~~bash
javac --release 17 -d out/api api/demo/api/Task.java api/demo/common/Origin.java
javac --release 17 -cp out/api -d out/a a/demo/provider/TaskImpl.java a/demo/only/OnlyA.java a/demo/common/Origin.java
javac --release 17 -cp out/api -d out/b b/demo/provider/TaskImpl.java
javac --release 17 -cp out/api -d out/host host/demo/host/Main.java
~~~

Chạy trên Linux/macOS (dấu **:** phân tách các classpath entry):

~~~bash
java -cp "out/api:out/host" demo.host.Main out/a out/b
~~~

Hoặc trên Windows PowerShell/cmd (dấu **;**):

~~~powershell
java -cp "out/api;out/host" demo.host.Main out/a out/b
~~~

**Standard output chính xác:**

~~~text
A: alpha
B: beta
Same provider class: false
Shared SPI class: true
Parent defines SPI: true
Parent-first duplicate: true
B sees OnlyA: false
Parent sees provider: false
~~~

Các dòng có ý nghĩa:

1. A và B tạo được provider riêng, chạy cùng một phương thức id() nhưng trả giá trị khác.
2. Hai provider có cùng binary name nhưng **không có cùng Class identity**, bởi A và B định nghĩa chúng độc lập.
3. Hai lời gọi nạp demo.api.Task trả về một Class duy nhất của parent, giúp cả hai instance cast sang Task thành công.
4. Plugin A cũng chứa demo.common.Origin trả "child A", nhưng childA.loadClass trả về Origin của parent vì parent-first. Hai bản không được chọn theo "mới hơn" hay "nằm gần hơn".
5. Loader B không tìm được demo.only.OnlyA vì class chỉ nằm ở A. Parent không tìm được demo.provider.TaskImpl vì provider chỉ được đưa vào các URL của con.

**Điều kiện để kết quả đúng:** chạy trong JVM thông thường với classpath chỉ gồm out/api và out/host; không vô tình thêm out/a, out/b hoặc một JAR chứa provider vào classpath cha. Nếu thay đổi cách khởi chạy, phạm vi tìm lớp và kết quả có thể thay đổi.

## 7. Parent-first khác child-first ở đâu?

Default ClassLoader và URLClassLoader thường tìm parent trước rồi mới tìm nguồn riêng. Điều này tạo ra một lợi thế: các lớp Java core và các API dùng chung của host được nhìn thấy nhất quán từ plugin.

Nhưng có hệ thống plugin cần **cô lập dependency version**. Ví dụ, host có library-x phiên bản 1, plugin A cần library-x phiên bản 2. Với parent-first, nếu loader cha đã nhìn thấy library-x cùng binary name, A có thể vô tình dùng phiên bản 1, dẫn tới lỗi method/field không khớp.

Hai chiến lược thường được cân nhắc:

| Chiến lược | Nguyên tắc | Ưu và rủi ro |
| --- | --- | --- |
| Parent-first | Parent được ưu tiên trước khi child tìm lớp riêng | Giữ API dùng chung thống nhất, nhưng dễ va chạm dependency nếu parent chứa thư viện plugin |
| Child-first có kiểm soát | Với các namespace nhất định, thử nguồn riêng trước rồi mới hỏi parent | Có thể cô lập phiên bản, nhưng dễ nhân đôi class API/SPI và làm hỏng khả năng cast |

**Chỉ override findClass không tự biến loader thành child-first.** Muốn thay đổi ưu tiên phải điều chỉnh loadClass một cách có chủ đích, giữ lock, xử lý findLoadedClass, delegation, resolve và các yêu cầu về bảo toàn class identity. Không được cố định nghĩa lại lớp lõi trong namespace java.*; JVM có ràng buộc bảo vệ riêng. Một chiến lược child-first thiếu kiểm soát có thể gây ClassCastException, LinkageError, vòng phụ thuộc và deadlock khi tải lớp.

Thực tế, thường nên **parent-first cho Java/platform và API/SPI của host; quyết định rõ namespace nào của plugin được phép riêng**. Với thư viện có nguy cơ xung đột nhưng không cần xuất hiện trong API, có thể cô lập qua loader hoặc relocate/shade package khi phù hợp.

## 8. Thread context class loader: vì sao mã ở parent đôi khi tìm được plugin?

Một thư viện nằm ở loader cha thường không biết trước tên lớp hoặc đường dẫn JAR của plugin. Nó có thể dùng **thread context class loader (TCCL)** để nhận loader do môi trường thực thi cung cấp.

Ví dụ một framework muốn khám phá implementation của SPI:

~~~java
// Mã minh họa trong host đã có biến pluginLoader và MyService.class.
ClassLoader old = Thread.currentThread().getContextClassLoader();

try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    java.util.ServiceLoader<MyService> providers =
            java.util.ServiceLoader.load(MyService.class);
    for (MyService provider : providers) {
        provider.execute();
    }
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
~~~

Đây là **mảnh minh họa**, không phải chương trình độc lập; cần MyService, pluginLoader và cấu hình provider hợp lệ. ServiceLoader.load(service) sử dụng context loader của thread; cũng có overload **ServiceLoader.load(service, loader)** để chọn loader rõ ràng, thường dễ kiểm soát hơn trong host plugin.

TCCL **không đảo chiều quan hệ parent**, không khiến P.loadClass tự động nhìn thấy mọi child, và không sửa identity của các lớp. Nó chỉ thay đổi loader mà những API có ý thức dùng TCCL chọn cho thao tác discovery/loading.

Khi đổi TCCL, luôn khôi phục trong finally, nhất là trên thread pool nơi thread được tái sử dụng. Không để code plugin tùy ý chiếm context loader trong thời gian dài. Thread con có thể kế thừa context loader của thread tạo ra nó; một tham chiếu giữ lại loader cũ cũng có thể cản quá trình giải phóng plugin.

## 9. Visibility của resource không hoàn toàn giống visibility của class

ClassLoader còn tìm các **resource** như file cấu hình và META-INF/services. Với triển khai ClassLoader mặc định:

- **getResource(name)** thử parent trước rồi đến findResource của chính loader.
- **getResources(name)** có thể thu thập nhiều URL; thứ tự mặc định ưu tiên kết quả parent rồi kết quả tìm bởi loader hiện tại.
- **findResource/findResources** là hook để custom loader tìm trong nguồn riêng.
- **getResourceAsStream(name)** mở resource dưới dạng InputStream nếu tìm thấy; cần đóng stream khi dùng xong.

Ví dụ minh họa trong host:

~~~java
// Mã minh họa, pluginLoader là một ClassLoader đã cấu hình.
java.net.URL config = pluginLoader.getResource("config/plugin.properties");
if (config == null) {
    throw new IllegalStateException("Missing plugin resource");
}
~~~

Với ClassLoader.getResource, tên resource thông thường **không có dấu /** ở đầu. Ngược lại, Class.getResource có quy tắc đường dẫn tương đối với package và đường dẫn tuyệt đối bắt đầu bằng /. Hai API dễ bị nhầm.

Nếu parent và plugin cùng chứa tên resource, parent-first có thể làm cấu hình của host được chọn trước cấu hình trong plugin; vì vậy tránh dùng tên resource quá chung chung. Service descriptor cũng có thể xuất hiện ở nhiều JAR; trường hợp này API như ServiceLoader cần duyệt resource tương ứng theo quy tắc của chính nó.

**Named modules có thêm quy tắc đóng gói tài nguyên**: một resource có sẵn trong module không nhất thiết được getResource hiển thị như một file classpath tùy ý. Readability/exports/opens và quy tắc mở resource của module có thể ảnh hưởng; không suy diễn rằng mọi tài nguyên module đều được truy cập như tài nguyên của unnamed module.

## 10. Tìm được class chưa chắc truy cập hoặc ép kiểu được

Cần tách ba tầng:

1. **Reachability/loading**: loader có tìm được định nghĩa class theo tên không?
2. **Type identity/compatibility**: Class đó có cùng identity hoặc quan hệ assignability với kiểu host mong đợi không?
3. **Access control**: caller có quyền truy cập class, package, constructor và thành viên được gọi không?

Ví dụ, hai class do loader khác nhau định nghĩa có thể trùng tên nhưng không gán cho nhau. Ngay cả khi tìm đúng class, constructor không public vẫn có thể gây IllegalAccessException khi reflection tạo instance. Đối với **named module**, việc package được export hoặc open cho caller là một điều kiện khác; có class loader nhìn thấy bytecode chưa đủ để vượt module access control. Trong các hệ thống sử dụng API/SPI, host nên đặt interface/DTO công khai trong module hoặc thư viện chung có xuất bản hợp lệ.

**Runtime package** cũng phụ thuộc vào class loader (và thông tin module tương ứng), vì vậy package-private access không được bảo đảm chỉ nhờ hai class cùng chuỗi tên package nếu chúng đến từ loader khác nhau.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Khả năng chính | Cách điều tra |
| --- | --- | --- |
| ClassNotFoundException khi gọi loadClass | Không loader nào trong đường ủy quyền tìm được tên nhị phân | Kiểm tra classpath, URL, tên package/class và loader đang gọi |
| NoClassDefFoundError khi dùng một class | Dependency cần lúc linking/initialization không có hoặc class không khởi tạo thành công | Kiểm tra cause, classpath, dependencies và lỗi initializer |
| ClassCastException dù tên class nhìn giống nhau | Hai defining loader khác nhau hoặc quan hệ kiểu thực sự không tương thích | So sánh Class object và getClassLoader của từng kiểu |
| NoSuchMethodError/NoSuchFieldError | Class version được chọn khác version lúc compile | Kiểm tra parent-first đã chọn bản library nào và binary compatibility |
| LinkageError khác | Vi phạm ràng buộc liên kết hoặc các định nghĩa không tương thích | Xem cause, class loader identity và dependency graph |
| ServiceLoader không tìm provider | TCCL sai, loader không thấy META-INF/services, descriptor sai | Thử ServiceLoader.load(service, loader) với loader cụ thể; kiểm tra resource |
| Plugin A chạy, plugin B không tìm được lớp A | Hai loader sibling không tự ủy quyền cho nhau | Di chuyển contract cần chia sẻ lên API parent hoặc thiết kế bridge |
| Resource cùng tên bị lấy từ host | Parent-first trong getResource | In URL trả về và đặt tên resource rõ namespace |

Có thể in định danh loader cùng tên class để quan sát:

~~~java
// Mảnh minh họa, nhận Class<?> từ thao tác nạp thực tế.
static void describe(Class<?> type) {
    System.out.println(type.getName());
    System.out.println(type.getClassLoader());
    System.out.println(type.getModule());
}
~~~

Đoạn này chỉ minh họa ý tưởng debug, không phải một chương trình Java độc lập. Cần in cả tên lẫn loader, bởi việc Class.getName giống nhau không đủ để xác định Class identity. Với class của bootstrap, Class.getClassLoader() có thể trả null; không gọi method trên kết quả đó mà chưa kiểm tra.

Nếu cần chi tiết hơn, có thể dùng **-Xlog:class+load=info** khi khởi động JVM hỗ trợ unified logging (Java 17) để quan sát các lớp được nạp và nguồn bytecode. Việc nạp class diễn ra lazily, nên log có thể khác nhau tùy đường thực thi; không suy luận toàn bộ hệ thống từ một danh sách lớp chưa từng được truy cập.

## 12. Vòng đời và giới hạn của cơ chế delegation

Tạo URLClassLoader mới không tự động "reload" một Class đã được định nghĩa trong loader cũ. Khi muốn nhận phiên bản mới của class cùng tên, hệ thống thường tạo loader mới rồi chuyển trách nhiệm sang instance mới, bảo đảm không còn các tham chiếu cũ. Một Class đã được định nghĩa không thể bị thay đổi định nghĩa bình thường chỉ bằng việc nạp lại file cùng đường dẫn trong cùng loader.

URLClassLoader là AutoCloseable/Closeable; nên đóng khi không sử dụng để giải phóng resource và file handle. **close() không lập tức unload Class** và không bảo đảm các object/Thread/TCCL/callback đang giữ tham chiếu biến mất. Class unloading còn phụ thuộc garbage collection và việc không còn loader/class/object reachable. Nếu host giữ static registry hoặc thread context loader trỏ tới plugin cũ, việc gỡ plugin có thể không thu hồi được bộ nhớ.

Parent delegation cũng **không phải cơ chế sandbox bảo mật**. Plugin chạy cùng JVM vẫn có khả năng tác động tới tài nguyên hoặc state mà nó được cấp; muốn cách ly mã không tin cậy cần thiết kế quyền truy cập và ranh giới tiến trình phù hợp.

## 13. Ma trận kiểm thử và checklist

| Kịch bản kiểm thử | Kết quả cần xác nhận |
| --- | --- |
| Child nạp class chỉ có ở parent | Nhận đúng Class do parent định nghĩa |
| Child và parent có cùng binary name | Với parent-first, chọn bản ở parent |
| Class chỉ tồn tại trong child A | Parent và sibling B không tự nạp được nó |
| A và B tự định nghĩa cùng binary name | Hai Class object khác nhau |
| Provider ở A/B implements API do parent định nghĩa | Cả hai cast được thành SPI của host |
| Plugin mang bản API riêng và dùng child-first | Phát hiện nguy cơ class identity/assignability |
| Class.load và Class.forName với initialize | Phân biệt đã load với đã chạy static initializer |
| Parent/resource và child/resource trùng tên | Xác định thứ tự getResource/getResources |
| ServiceLoader dùng TCCL hoặc loader explicit | Discovery sử dụng đúng class loader |
| Đóng và thay plugin loader | Không giữ tham chiếu cũ trong TCCL/thread/registry |

Trước khi triển khai một extension point, hãy kiểm tra những việc sau:

1. Có một bản API/SPI dùng chung ở loader mà host và plugin thực sự cùng nhìn thấy.
2. Parent được chọn tường minh khi tạo loader; không mặc định rằng "cùng JVM" là "cùng classpath".
3. Namespace của implementation, dependency và resource đã có chính sách parent-first/child-first rõ ràng.
4. Những class cần giao tiếp qua ranh giới chỉ sử dụng các kiểu có identity chung; không xuất class riêng của plugin trong API mà các plugin khác phải trực tiếp cast.
5. Host hiểu được đường đi của ClassNotFoundException, NoClassDefFoundError, ClassCastException và lỗi linkage; có log loader identity khi cần.
6. Các thao tác discovery dùng loader explicit hoặc TCCL có kiểm soát; luôn khôi phục TCCL sau khi thay đổi.
7. Module accessibility, resource lookup và vòng đời class loader đã được kiểm chứng bằng thử nghiệm trong môi trường triển khai thực tế.

**Ghi nhớ:** default ClassLoader tìm lớp theo hướng **child → parent → nguồn riêng của child**; child có thể dùng Class của ancestor, nhưng parent và sibling không tự thấy lớp riêng của child. Chia sẻ **kiểu hợp đồng** ở loader chung và cô lập **implementation** theo loader riêng là cách thiết kế nền tảng cho runtime extensibility đáng tin cậy.

Tài liệu Java 17 chính thức:

- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
