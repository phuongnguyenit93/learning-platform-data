# Reflection và việc chọn loader cho tên lớp

## 1. Vấn đề cốt lõi: tên lớp không tự quyết định lớp runtime

Trong Java, reflection cho phép tìm một lớp qua tên dạng chuỗi, xem constructor/method/field và tạo instance hoặc gọi method khi chương trình đang chạy. Nhưng câu hỏi **“tìm lớp bằng tên nào?”** luôn phải đi kèm câu hỏi **“dùng class loader nào để tìm?”**.

Ví dụ, chuỗi `"plugin.OnlyChild"` chỉ là **binary name**. Nếu class đó nằm trong plugin JAR/thư mục chỉ được một loader con nhìn thấy, thì application loader của host chưa chắc tìm được. Thậm chí hai loader khác nhau có thể định nghĩa **hai class runtime khác nhau cùng binary name**.

Theo mô hình JVM, danh tính của class thông thường dựa trên **binary name + defining class loader**, không chỉ chuỗi tên.

~~~text
                    Host / Application Loader
                    ├── ReflectionLoaderDemo
                    └── API dùng chung
                               |
              +----------------+----------------+
              |                                 |
       URLClassLoader A                   URLClassLoader B
       plugin.OnlyChild                   plugin.OnlyChild
         (Class A)                           (Class B)
              |                                 |
           cùng tên và cùng bytes, nhưng Class A != Class B
~~~

Vì vậy, lựa chọn loader ảnh hưởng đến:

- **ClassNotFoundException**: một loader không thấy class dù class có ở một nguồn khác.
- **ClassCastException**: instance từ class do loader B định nghĩa không thể ép thành class cùng tên do loader A định nghĩa.
- **Liên kết phụ thuộc**: khi class được định nghĩa bởi loader nào, symbolic references trong bytecode của nó được JVM giải qua defining loader thích hợp, không tự động qua loader của code đang dùng reflection.
- **Initialization**: một số API tìm class chỉ nạp class, API khác chủ động khởi tạo nó, làm khối `static { ... }` chạy.
- **Module access**: tìm được đối tượng `Class<?>` không bảo đảm được phép gọi constructor hoặc truy cập member private.

Bài này tập trung vào **chọn loader cho một binary name khi dùng reflection**, phân biệt `Class.forName`, `ClassLoader.loadClass`, TCCL và class identity.

## 2. Những API tìm lớp theo tên cần phân biệt

| API | Loader dùng để tìm | Có yêu cầu initialization? | Khi không thấy |
| --- | --- | --- | --- |
| `Class.forName("pkg.Type")` | Defining loader của **class đang thực hiện lời gọi** | **Có** | `ClassNotFoundException` |
| `Class.forName("pkg.Type", false, loader)` | `loader` tường minh | **Không** chủ động initialize | `ClassNotFoundException` |
| `Class.forName("pkg.Type", true, loader)` | `loader` tường minh | **Có** nếu chưa initialized | `ClassNotFoundException` |
| `loader.loadClass("pkg.Type")` | `loader` được gọi, theo delegation policy của nó | **Không** chủ động initialize | `ClassNotFoundException` |
| `Class.forName(module, "pkg.Type")` | Module và cơ chế loader gắn với module đó | **Không** link hay initialize theo hợp đồng overload này | **`null`** khi không tìm đúng class trong module |
| `SomeType.class` | Class literal được compiler/JVM biết qua bytecode hiện tại | Không phải một phép tìm bằng chuỗi; không chủ động initialize chỉ do dùng literal | Lỗi compile/linkage phù hợp nếu type không sẵn |

**Đừng suy diễn** rằng `Class.forName(name)` tương đương `Class.forName(name, true, Thread.currentThread().getContextClassLoader())`. Theo Java API, overload một tham số dùng **defining class loader của class thực hiện lời gọi**, **không tự lấy TCCL**.

Tương tự, `ClassLoader.loadClass(name)` tương đương overload `loadClass(name, false)` theo API mặc định: nó không chủ động chạy static initializer. Từ `resolve` trong overload protected `loadClass(name, boolean resolve)` nói về **linking**, không phải cờ `initialize` của `Class.forName`.

### Khi chọn loader=null

~~~java
Class<?> jdk = Class.forName("java.lang.String", false, null);
~~~

Đoạn trên minh họa overload ba tham số: `loader == null` ở đây nghĩa là yêu cầu **bootstrap class loader**, không phải lấy TCCL hoặc tự động chọn application loader. Với class của ứng dụng/plugin không do bootstrap nhìn thấy, truyền `null` thường không tìm được.

Cũng vì thế, `String.class.getClassLoader()` thường trả `null`: đó là đại diện Java API cho bootstrap loader, **không có nghĩa String chưa được nạp**.

## 3. Chọn loader thế nào trong host và plugin?

Giả sử host được chạy với:

~~~text
java -cp out/host ReflectionLoaderDemo out/plugin
~~~

Các file plugin nằm tại:

~~~text
out/plugin/plugin/OnlyChild.class
~~~

Ứng dụng host có thể tạo một `URLClassLoader` riêng với root `out/plugin`:

~~~java
URL source = Path.of("out/plugin").toAbsolutePath().toUri().toURL();

try (URLClassLoader pluginLoader = new URLClassLoader(
        new URL[]{source}, Host.class.getClassLoader())) {
    Class<?> pluginClass = Class.forName(
            "plugin.OnlyChild", false, pluginLoader);
}
~~~

Đây là đoạn **minh họa**, giả định `Host` và các imports tương ứng tồn tại; chương trình hoàn chỉnh nằm ở phần 6. `URLClassLoader` mặc định dùng parent-first delegation:

~~~text
Class.forName(name, false, pluginLoader)
                   |
                   v
          pluginLoader.loadClass(name)
                   |
           đã nạp tên này chưa?
                   |
             hỏi loader cha
               /       \
           có class    không
              |           |
           trả cha    tìm từ URL plugin
                          |
                        defineClass
~~~

Điều cần nhớ:

- **Chỉ định `pluginLoader` không bảo đảm chính loader này định nghĩa class.** Nếu parent đã nhìn thấy một class cùng binary name, thuật toán parent-first có thể trả class của parent.
- `clazz.getClassLoader()` cho biết **defining loader** của đối tượng `Class<?>`, không nhất thiết là loader được truyền vào ban đầu.
- `clazz.getName()` chỉ cho binary name; hai class từ hai loader có thể có `getName()` bằng nhau nhưng `clazzA != clazzB`.
- Nếu cần child-first, phải thiết kế chính sách nạp riêng và quản lý ranh giới API/loader identity. Không thể đảo thứ tự delegation bằng cách đổi tham số `initialize`.

### Source và runtime classpath không giống nhau

Khi biên dịch host, nếu host chỉ dùng reflection bằng tên chuỗi, nó **không cần compile-time import** implementation plugin. Ở runtime, không nên đưa plugin vào `-cp` của host nếu mục tiêu là chứng minh plugin chỉ nhìn thấy qua child loader. Nếu cùng lúc đưa plugin vào application classpath, parent sẽ có thể nhìn thấy class và thử nghiệm loader con không còn thể hiện đúng sự khác nhau.

## 4. Class.forName, loading, linking và initialization

Các giai đoạn cần phân biệt:

| Giai đoạn | Diễn giải | Có chạy khối `static`? |
| --- | --- | --- |
| Loading | Tạo hoặc tìm đối tượng `Class<?>` qua cơ chế loader. | Không tự động chỉ vì vừa load. |
| Linking | Verification, preparation, resolution theo quy tắc JVM. | Không phải initialization. |
| Initialization | Thực thi static initializer của class khi chưa được initialize. | **Có** khi initializer tồn tại. |

Trong API `Class.forName(name, boolean initialize, loader)`:

- `initialize=false`: yêu cầu load/link theo hợp đồng phù hợp nhưng **không chủ động initialize**. JVM có thể làm một số linking theo thời điểm hợp lệ; đừng diễn giải thành “chưa link bất cứ thứ gì”.
- `initialize=true`: sau bước tìm và link theo yêu cầu, **chủ động initialize** class nếu chưa initialized.
- `Class.forName(name)` tương đương `Class.forName(name, true, callerDefiningLoader)` theo Javadoc. Caller ở đây là class chứa lời gọi, không phải bất kỳ object/plugin class nào có liên quan về mặt logic.
- `loader.loadClass(name)` chỉ trả `Class<?>` qua loader, không yêu cầu chạy initializer.

Ví dụ định nghĩa plugin:

~~~java
package plugin;

public final class OnlyChild {
    static {
        System.out.println("OnlyChild initialized");
    }

    public String message() {
        return "plugin says hello";
    }
}
~~~

Khi chạy:

~~~java
Class<?> type = Class.forName("plugin.OnlyChild", false, pluginLoader);
System.out.println(type.getName()); // chưa chủ động initialize
Class.forName("plugin.OnlyChild", true, pluginLoader); // active initialization
~~~

Đây chỉ là **đoạn minh họa** nằm trong ngữ cảnh có `pluginLoader`; chương trình độc lập sẽ chứng minh lần khởi tạo ở phần 6. Tên class literal, truy vấn metadata và load bình thường không tương đương việc gọi `new`, gọi static method hay yêu cầu initialization bằng `Class.forName(..., true, ...)`.

**Lưu ý:** nếu class đã initialized trước đó, gọi `forName(..., true, ...)` lần nữa **không** chạy lại `static`. Nhưng hai loader khác nhau định nghĩa hai class runtime cùng tên, nên mỗi bản có quá trình initialization riêng.

## 5. Thread context class loader (TCCL) không phải “loader toàn cục”

Java hỗ trợ:

~~~java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();
~~~

TCCL là **một thuộc tính của thread**. Nó thường được framework, API dịch vụ, container hoặc thư viện dùng để tìm providers/resources theo ngữ cảnh xử lý. Ví dụ:

~~~java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    Class<?> plugin = Thread.currentThread()
            .getContextClassLoader().loadClass("plugin.OnlyChild");
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
~~~

Đoạn trên giả định `pluginLoader` đã tạo. Cần **khôi phục TCCL cũ trong finally**, nhất là với thread pool, để không làm tác vụ sau vô tình dùng loader plugin và không giữ loader sống ngoài mong muốn.

**Nhưng:** riêng `Class.forName("plugin.OnlyChild")` trong code host **không tự dùng TCCL** vừa được gán. Nó vẫn dựa vào defining loader của class chứa lời gọi; chỉ phiên bản truyền `loader` tường minh mới cho bạn kiểm soát loader ngay trong API này.

TCCL cũng không thay đổi quy tắc JVM khi giải symbolic reference của bytecode: theo JVMS, khi class D có symbolic reference tới class C, bước resolve class reference sử dụng **defining loader của D**. Không phải JVM nhìn TCCL mỗi lần cần một class phụ thuộc.

### Khi nào nên dùng TCCL?

- Khi API/framework **được tài liệu quy định rõ là dùng TCCL**, ví dụ overload `ServiceLoader.load(ServiceType.class)` thường chọn context class loader.
- Khi host chủ động muốn code/library tìm implementation theo loader plugin mà framework cho phép.
- Khi cần giữ tương thích với SPI/container đã dựa trên TCCL.

Nếu đang tự làm reflection bằng tên class, cách dễ đọc và dễ kiểm thử hơn thường là **truyền loader tường minh cho `Class.forName(name,false,loader)`** thay vì thay đổi trạng thái thread để hy vọng một API chọn đúng nguồn.

## 6. Thực hành Java 17+ chạy độc lập: hai loader và reflection

Mục tiêu: chương trình host không có plugin trên application classpath; hai URLClassLoader đều nhìn thấy cùng file plugin; mỗi loader định nghĩa một runtime class riêng.

### Cây source

~~~text
example/
├── src/
│   ├── host/
│   │   └── ReflectionLoaderDemo.java
│   └── child/
│       └── plugin/
│           └── OnlyChild.java
└── out/
    ├── host/               (tạo sau biên dịch)
    └── plugin/
        └── plugin/
            └── OnlyChild.class
~~~

### File src/child/plugin/OnlyChild.java

~~~java
package plugin;

public final class OnlyChild {
    static { System.out.println("OnlyChild initialized"); }

    public String message() {
        return "plugin says hello";
    }
}
~~~

### File src/host/ReflectionLoaderDemo.java

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class ReflectionLoaderDemo {
    public static void main(String[] args) throws Exception {
        URL source = Path.of(args[0])
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader first = new URLClassLoader(
                     new URL[]{source},
                     ReflectionLoaderDemo.class.getClassLoader());
             URLClassLoader second = new URLClassLoader(
                     new URL[]{source},
                     ReflectionLoaderDemo.class.getClassLoader())) {

            try {
                Class.forName("plugin.OnlyChild");
                System.out.println("caller unexpectedly found plugin");
            } catch (ClassNotFoundException expected) {
                System.out.println(
                        "caller loader: ClassNotFoundException");
            }

            Class<?> typeA =
                    Class.forName("plugin.OnlyChild", false, first);
            System.out.println("first defines plugin: "
                    + (typeA.getClassLoader() == first));
            System.out.println("loadClass same Class: "
                    + (typeA == first.loadClass("plugin.OnlyChild")));

            Thread current = Thread.currentThread();
            ClassLoader oldContext = current.getContextClassLoader();
            try {
                current.setContextClassLoader(first);
                try {
                    Class.forName("plugin.OnlyChild");
                    System.out.println("TCCL unexpectedly used");
                } catch (ClassNotFoundException expected) {
                    System.out.println("forName ignores TCCL: true");
                }
                System.out.println("explicit TCCL works: "
                        + (current.getContextClassLoader()
                            .loadClass("plugin.OnlyChild") == typeA));
            } finally {
                current.setContextClassLoader(oldContext);
            }

            System.out.println("request initialization");
            Class.forName("plugin.OnlyChild", true, first);

            Object instanceA =
                    typeA.getDeclaredConstructor().newInstance();
            System.out.println("reflection: "
                    + typeA.getMethod("message").invoke(instanceA));

            Class<?> typeB =
                    Class.forName("plugin.OnlyChild", false, second);
            System.out.println("same name: "
                    + typeA.getName().equals(typeB.getName()));
            System.out.println("same runtime Class: "
                    + (typeA == typeB));

            Object instanceB =
                    typeB.getDeclaredConstructor().newInstance();

            try {
                typeA.cast(instanceB);
                System.out.println("unexpected cast success");
            } catch (ClassCastException expected) {
                System.out.println(
                        "cross-loader cast: ClassCastException");
            }

            System.out.println("bootstrap represented as null: "
                    + (String.class.getClassLoader() == null));
        }
    }
}
~~~

**Giải thích thiết kế:**

- `first` và `second` là **hai loader instance khác nhau** cùng nhận URL của thư mục plugin.
- Parent đều là loader của `ReflectionLoaderDemo`, nhưng host không đưa thư mục plugin lên `-cp`, nên parent không có `plugin.OnlyChild`.
- `Class.forName(name)` ở trong host tìm bằng caller defining loader, vì vậy ném `ClassNotFoundException`.
- Overload `Class.forName(name,false,first)` tìm thành công nhưng chưa chủ động khởi tạo plugin.
- Đổi TCCL sang first **không** khiến overload `Class.forName(name)` tự dùng first.
- `Class.forName(name,true,first)` chủ động khởi tạo class do first định nghĩa.
- Instance từ `second` không cast thành class của `first` dù binary name giống hệt.
- `try-with-resources` đóng các URLClassLoader sau khi thí nghiệm kết thúc; đóng loader giải phóng nguồn I/O, không đảm bảo unload class ngay lập tức.

### Biên dịch và chạy Linux/macOS

Trong thư mục `example` có hai source:

~~~bash
mkdir -p out/plugin out/host

javac --release 17 -d out/plugin src/child/plugin/OnlyChild.java
javac --release 17 -d out/host src/host/ReflectionLoaderDemo.java

java -cp out/host ReflectionLoaderDemo out/plugin
~~~

### Biên dịch và chạy Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out\plugin, out\host | Out-Null
javac --release 17 -d out\plugin src\child\plugin\OnlyChild.java
javac --release 17 -d out\host src\host\ReflectionLoaderDemo.java
java -cp out\host ReflectionLoaderDemo out\plugin
~~~

**Không** thêm `out/plugin` vào `java -cp`; điều đó sẽ khiến parent loader cũng tìm được plugin, làm thay đổi kết quả kiểm chứng.

### Stdout đã kiểm chứng

~~~text
caller loader: ClassNotFoundException
first defines plugin: true
loadClass same Class: true
forName ignores TCCL: true
explicit TCCL works: true
request initialization
OnlyChild initialized
reflection: plugin says hello
same name: true
same runtime Class: false
OnlyChild initialized
cross-loader cast: ClassCastException
bootstrap represented as null: true
~~~

Mã đã được **biên dịch với `javac --release 17` và chạy trên OpenJDK 21** với thư mục plugin tách khỏi host classpath; stdout khớp nguyên văn.

### Đọc từng điểm của output

1. **Caller loader thất bại** vì `ReflectionLoaderDemo` được định nghĩa ở host loader, không nhìn thấy thư mục plugin.
2. **first defines plugin: true** xác nhận plugin thực sự do first định nghĩa, không chỉ first đóng vai initiating loader.
3. **loadClass same Class: true** cho thấy lookup lặp của cùng loader không tự define lại class.
4. **forName ignores TCCL: true** chứng minh overload một tham số không tự chọn context loader.
5. **explicit TCCL works: true** chứng minh khi bạn **chủ động gọi** `contextLoader.loadClass`, lookup mới dùng context loader đã chọn.
6. **request initialization**, sau đó **OnlyChild initialized**: class first chỉ chạy initializer khi yêu cầu initialize=true.
7. **reflection: plugin says hello**: reflection đã tạo instance rồi gọi public instance method trên đúng `Class<?>`.
8. **same name: true / same runtime Class: false**: binary name giống nhưng defining loaders khác.
9. Dòng **OnlyChild initialized** thứ hai xuất hiện khi tạo instance từ class second; đó là **một class runtime khác**, không phải JVM khởi tạo lại class first.
10. **cross-loader cast: ClassCastException** là hậu quả của khác danh tính kiểu.
11. **bootstrap represented as null: true** minh họa cách `Class.getClassLoader()` biểu diễn bootstrap loader với `java.lang.String` trên JVM chuẩn.

Nếu chạy bài với một build tool hoặc classpath khác, trước tiên kiểm tra không vô tình đưa plugin vào source lookup của parent, và không tạo sẵn class/plugin trong host output.

## 7. Reflection sau khi đã chọn đúng Class<?>: quyền truy cập vẫn phải kiểm tra

Có đối tượng `Class<?>` chưa đủ để mọi thao tác reflection thành công. Một số API phổ biến:

| API | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| `clazz.getConstructor(parameterTypes...)` | Tìm public constructor phù hợp | `NoSuchMethodException` |
| `clazz.getDeclaredConstructor(parameterTypes...)` | Tìm constructor được khai báo trực tiếp, kể cả không public | Có thể cần mở quyền khi gọi |
| `clazz.getMethod("run", ...)` | Tìm public method phù hợp, kể cả inherited public methods | `NoSuchMethodException` |
| `clazz.getDeclaredMethod("run", ...)` | Tìm method được khai báo trực tiếp, kể cả private | Không tự cho quyền `invoke` |
| `constructor.newInstance(args...)` | Tạo instance (kích hoạt initialization nếu cần) | `InvocationTargetException`, `IllegalAccessException`, v.v. |
| `method.invoke(instance,args...)` | Gọi method qua reflection; static method dùng target `null` | Sai receiver/args, quyền truy cập, exception trong method |
| `clazz.cast(object)` | Dynamic type cast theo chính đối tượng `Class<?>` | `ClassCastException` nếu object thuộc class runtime khác |
| `clazz.isInstance(object)` | Test tương thích kiểu tại runtime | `false` với bản class trùng tên khác loader |

Trong ví dụ, `OnlyChild` có public no-arg constructor và public method nên không cần `setAccessible(true)`. Nếu class/method private hoặc package không mở, phải tuân các điều kiện Java access và JPMS.

### Modules: load được vẫn có thể không được reflect sâu

Ở Java 9+, class trong **named module** chịu readability, exports/opens và access rules riêng. `Class.forName` hoặc `ClassLoader.loadClass` có thể trả về `Class<?>`, nhưng code ở module khác vẫn có thể không được gọi member nếu package không exported. Với reflection vào private members, có thể cần `opens p to caller.module;`; nếu thiếu, `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Không nên sửa bằng cách mở mọi package hoặc dùng `--add-opens` vô điều kiện. Ưu tiên một **SPI/interface chung ở loader/module được chia sẻ**, expose public API đúng nghĩa và chỉ mở package khi thực sự cần deep reflection.

### Vì sao không dùng Class.newInstance?

`Class.newInstance()` đã deprecated từ Java 9; API đó xử lý và biểu diễn exception kém rõ ràng. Nên dùng:

~~~java
Object instance = clazz.getDeclaredConstructor().newInstance();
~~~

Đây là đoạn minh họa, giả định class có constructor không tham số truy cập được và biến `clazz` đã được chọn đúng loader. Constructor có thể ném exception được phản ánh qua `InvocationTargetException`; xử lý nguyên nhân gốc thích hợp thay vì nuốt lỗi.

## 8. Class.forName(Module, String): chọn module, không chỉ loader

Từ Java 9 có overload:

~~~java
Class<?> type = Class.forName(module, "com.acme.plugin.Impl");
~~~

Trong đó `module` là đối tượng `java.lang.Module` cụ thể. Sự khác biệt theo tài liệu Java SE:

- Tìm class với **binary name ở đúng module được chỉ định**.
- **Không link hoặc chạy initializer** theo hợp đồng overload này.
- Nếu class không thuộc module đó hoặc không được tìm thấy, trả **`null`** thay vì `ClassNotFoundException`.
- Nếu cùng loader định nghĩa nhiều modules mà tên class thuộc module khác, overload vẫn có thể trả `null` vì yêu cầu là **đúng module**.
- Việc tìm được `Class<?>` không tự kiểm tra class có accessible với caller hay không. Khi truy cập member vẫn phải tuân module/access checks.
- Không hỗ trợ tìm array class bằng tên array descriptor như overload `forName(String,boolean,ClassLoader)`.

Đoạn trên chỉ minh họa, giả định có biến `module`. Khi dùng `ModuleLayer`, có thể lấy module từ layer đã resolve và dùng `Class.forName(module, binaryName)` để kiểm tra một class thuộc **module cụ thể**; nhưng nếu mục tiêu là service provider discovery, hãy dùng `ServiceLoader.load(layer, service)` thay cho tự duyệt class bằng chuỗi tên.

**Phân biệt rõ:** `Class.forName(Module,String)` không phải dạng rút gọn của `Class.forName(name, false, module.getClassLoader())`, vì nó còn ràng buộc tên class vào **đúng named module** và có hợp đồng riêng về link/error/null.

## 9. Class literals, arrays, nested classes và binary name

Tên chuỗi cho `loadClass` và `Class.forName` cần đúng cú pháp phù hợp:

| Kiểu Java | Binary name thông thường | Lưu ý |
| --- | --- | --- |
| `com.example.Widget` | `com.example.Widget` | Dấu chấm giữa package |
| Member class `com.example.Outer.Inner` | `com.example.Outer$Inner` | Dấu `$` trong binary name của member class |
| Array của reference type | `[Lcom.example.Widget;` | Dạng JVM array descriptor cho `Class.forName` overload theo loader |
| Array của `int` | `[I` | Dạng descriptor; class loader của mảng primitive là bootstrap/null |
| Primitive `int` | Không dùng `Class.forName("int")` để lấy primitive `Class` | Dùng `int.class` |
| Kiểu ở module | Phải có module phù hợp khi gọi overload module | Module overload không hỗ trợ array types |

Các cú pháp trên không phải đường dẫn file `com/example/Widget.class` và không phải tên URL JAR. Reflection nhận **binary name**, loader sẽ tự áp dụng chính sách tìm nguồn bytes.

Ngoài ra, type parameters của generics bị **type erasure** ở runtime; `List<String>` và `List<Integer>` không tự trở thành hai runtime classes riêng chỉ vì chuỗi kiểu generic khác. Nếu cần phân tích signatures/generic types, dùng các API `java.lang.reflect.Type` phù hợp thay vì coi chuỗi tên đơn giản là đầy đủ thông tin kiểu.

## 10. Loader được dùng để resolve dependency có thể khác loader chọn từ code host

Một hiểu lầm nguy hiểm: host dùng `child.loadClass("plugin.Entry")` để lấy entry, vậy tất cả dependency của entry sẽ được chọn bởi **host loader** hoặc **TCCL hiện hành**. Không đúng theo quy tắc JVM.

Ví dụ:

~~~text
HostClass (defined by AppLoader)
    |
    | reflection: child.loadClass("plugin.Entry")
    v
Entry (defined by ChildLoader)
    |
    | bytecode references plugin.Helper
    v
Helper được yêu cầu qua defining loader của Entry
(theo quy tắc symbolic reference resolution)
~~~

Khi JVM giải một symbolic reference trong runtime constant pool của class D, **defining loader của D** được dùng để load class tương ứng. Điều này giúp lý giải:

- Plugin có thể đọc dependency do loader con hoặc parent của nó nhìn thấy.
- Host class do parent định nghĩa **không tự tìm** dependency chỉ có ở child khi bytecode của host có symbolic reference đó.
- Chuyển TCCL không tự sửa mọi lỗi `NoClassDefFoundError` của bytecode đã định nghĩa.
- Reflection chọn đúng một `Class<?>` không bảo đảm mọi dependency của class đều hợp lệ trong môi trường runtime.

Với plugin thực tế, nên đặt **shared API ở parent**, implementation/dependencies riêng ở child và tạo API bridge. Nếu host cần một contract như `api.Plugin`, cả hai bên phải dùng cùng đối tượng `Class<api.Plugin>`, thay vì dùng reflection để trao đổi object không cùng loader identity.

## 11. Quy trình chọn loader theo tình huống

| Tình huống | Lựa chọn hợp lý |
| --- | --- |
| Class trên application classpath, host dùng class đó trực tiếp | `SomeClass.class` hoặc `Class.forName(name)` khi thật sự cần tên động |
| Class ở plugin URL riêng | `Class.forName(name, false, pluginLoader)`, sau đó reflection qua `Class<?>` trả về |
| Cần chủ động chạy static initializer của plugin | `Class.forName(name, true, pluginLoader)` nếu tên/loader được xác định rõ |
| Chỉ cần metadata mà chưa muốn initialize | `Class.forName(name, false, loader)` hoặc `loader.loadClass(name)` |
| Framework document rõ là dùng TCCL | Gán TCCL tạm thời và **khôi phục trong finally** |
| Cần provider của SPI | `ServiceLoader` với đúng ClassLoader hoặc ModuleLayer |
| Cần class của một named module cụ thể | `Class.forName(module, binaryName)`, kiểm tra kết quả có thể null |
| Cần nạp từ JAR/thư mục | `URLClassLoader`, truyền package root/JAR URL chính xác, parent phù hợp |
| Cần cùng interface giữa host/plugin | Đặt interface ở loader/module cha được chia sẻ, để child ủy quyền |
| Cần version plugin riêng dù parent có cùng class name | Class loading policy child-first có chọn lọc, có test identity và dependency |
| Muốn chạy code không tin cậy | Không coi class loader là security sandbox; cần isolation/security model riêng |

### Checklist debug từng bước

1. Binary name chính xác không? Với nested member class, đã dùng dấu `$` khi cần chưa?
2. Lời gọi là `Class.forName(name)`, overload có loader, hay `loader.loadClass(name)`?
3. **Caller** của overload một tham số được định nghĩa bởi loader nào?
4. Class có nằm trong URL/plugin root hoặc module path đã resolve đúng chưa?
5. Parent-first có đang trả phiên bản của parent không? In `clazz.getClassLoader()` để biết defining loader.
6. TCCL đang là gì? API sử dụng có **thực sự chủ động đọc TCCL** không?
7. Có đang kỳ vọng `loadClass` chạy initializer, hay nhầm `resolve=true` với `initialize=true` không?
8. Hai đối tượng `Class<?>` có cùng tên nhưng khác loader không? Dùng `a == b`, `isInstance` hoặc `cast` để xác định.
9. Exception thuộc nhóm nào: `ClassNotFoundException`, `NoClassDefFoundError`, `ClassCastException`, `IllegalAccessException`, `InaccessibleObjectException` hay `ExceptionInInitializerError`?
10. Nếu dùng JPMS, package có `exports`/`opens` phù hợp với module caller không?
11. Có sửa TCCL nhưng quên khôi phục hoặc đóng loader quá sớm không?
12. Host và plugin có chia sẻ **cùng defining loader cho SPI interface** không?

### Những lỗi phổ biến

| Biểu hiện | Nguyên nhân khả dĩ | Cách giải quyết |
| --- | --- | --- |
| `Class.forName(name)` báo không tìm thấy nhưng `pluginLoader.loadClass(name)` tìm được | Caller loader không nhìn thấy nguồn plugin | Chọn plugin loader tường minh |
| Đổi TCCL vẫn không sửa `Class.forName(name)` | Overload một tham số không lấy TCCL | Gọi overload có loader |
| Cả hai loader nhận class cùng tên nhưng cast lỗi | Khác defining loaders tạo type identity khác | Chia sẻ API contract qua parent |
| Khối `static` chạy sớm ngoài mong muốn | Dùng `Class.forName(name)` hoặc `initialize=true` | Chọn `initialize=false` để chỉ tìm metadata |
| Class được load nhưng gọi method báo `NoClassDefFoundError` | Dependency không thấy qua defining loader, hoặc lớp trước đó init thất bại | Xem cause/stack trace và loader của class chứa reference |
| `getDeclaredMethod` tìm ra private method nhưng `invoke` lỗi | Java access/module opens chưa cho phép | Dùng public API hoặc mở package có chọn lọc |
| `Class.forName(module,name)` trả null | Tên không thuộc đúng module, dù loader có thể định nghĩa module khác | Xác minh module identity và binary name |
| Đóng URLClassLoader rồi plugin ngừng tìm class mới | `close()` giải phóng nguồn tìm mới | Quản lý loader lifecycle và streams phù hợp |
| Log `clazz.getClassLoader() == null` | Class do bootstrap loader định nghĩa | Đây không phải trạng thái “chưa load” |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Plugin `plugin.OnlyChild` chỉ nằm trong `out/plugin`. Tại sao `Class.forName("plugin.OnlyChild")` từ host thất bại nhưng overload truyền `pluginLoader` lại thành công?

**Đáp:** Overload một tham số dùng defining loader của class caller (host); overload ba tham số dùng loader được chỉ định. Parent host không biết nguồn plugin, trong khi child có URL tương ứng.

**Câu 2.** Gán TCCL bằng pluginLoader, gọi `Class.forName(name)` có tự chọn TCCL không?

**Đáp:** Không. Nếu muốn chọn TCCL phải **gọi API dùng nó** hoặc truyền `Thread.currentThread().getContextClassLoader()` cho overload ba tham số.

**Câu 3.** Hai URLClassLoader khác nhau đều đọc cùng bytecode `plugin.OnlyChild`, tại sao `clazzA == clazzB` là false?

**Đáp:** JVM phân biệt class runtime bằng binary name **và defining loader**. Cùng tên cùng bytes chưa đủ làm cùng Class object.

**Câu 4.** `loadClass(name)` đã thành công nhưng `static { ... }` không in gì; có phải lỗi loader?

**Đáp:** Không. Lookup không tự yêu cầu initialization. `Class.forName(name,true,loader)` hoặc active use phù hợp mới khởi tạo class nếu cần.

**Câu 5.** `Class.forName(module,name)` khác overload ba tham số ở điểm nào?

**Đáp:** Nó yêu cầu class trong **module cụ thể**, không link/initialize theo hợp đồng, và trả null khi không tìm đúng class trong module, thay vì checked `ClassNotFoundException`.

**Câu 6.** Vì sao chỉ chỉnh TCCL của thread host chưa chắc sửa lỗi dependency trong class plugin?

**Đáp:** JVM giải symbolic references theo defining loader của class chứa reference; TCCL chỉ có tác dụng khi API/framework chủ động dùng nó.

## Tài liệu tham khảo chính thức

- [Class.forName và Class.getClassLoader, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): overload theo name, loader, module; initialization; kiểm tra defining loader.
- [ClassLoader, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent-first delegation, loadClass, findClass và loader identity.
- [Thread.getContextClassLoader, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#getContextClassLoader()): quản lý context class loader của thread.
- [java.lang.reflect.Method, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): gọi method qua reflection và quyền truy cập.
- [JVMS Java SE 21 §5.3 và §5.4.3.1](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): defining loader, class identity và symbolic reference resolution.
