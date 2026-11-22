# Bộ nạp khởi xướng, bộ nạp định nghĩa và ràng buộc giữa các bộ nạp

## 1. Mục tiêu

Một lỗi khó hiểu trong ứng dụng Java dạng plugin là `demo.Plugin cannot be cast to demo.Plugin`: hai tên lớp nhìn giống hệt nhau nhưng JVM lại coi chúng là **hai kiểu khác nhau**. Lý do nằm ở cách JVM xác định lớp runtime: **tên nhị phân và bộ nạp đã định nghĩa lớp**. Ngoài ra, lớp có thể được yêu cầu tải qua một loader nhưng do **loader khác** định nghĩa sau khi ủy quyền.

Sau bài học này, bạn cần phân biệt chính xác:

- **Initiating loader** (bộ nạp khởi xướng) và **defining loader** (bộ nạp định nghĩa), theo **JVMS §5.3**.
- **Loading** (tạo lớp từ định nghĩa), **linking/resolution** (liên kết tham chiếu) và **initialization** (chạy khởi tạo `static`).
- **Class identity**: cặp (`binary name`, `defining loader`), không chỉ là tên hoặc nội dung của tệp `.class`.
- **Parent delegation** mặc định của `ClassLoader` và giới hạn của nhận định “mọi loader đều parent-first”.
- **Loading constraints** giữa các bộ nạp, ký hiệu `N^L1 = N^L2`, nhằm bảo đảm an toàn kiểu cho các lời gọi và trường xuyên ranh giới class loader.
- Khác biệt giữa **`ClassCastException`**, **`LinkageError` do loader constraint violation**, `ClassNotFoundException` và một số lỗi linking khác.

Ví dụ thực hành dùng Java **17+**, một class plugin, hai `URLClassLoader` riêng, và xác nhận class names giống nhau không bảo đảm `Class<?>` identity giống nhau.

## 2. Hai vai trò loader trong JVMS

Đặc tả **JVMS §5.3, Creation and Loading** giải thích: với class/interface không phải array, một class loader `L` có thể trực tiếp tìm biểu diễn bytecode và đề nghị JVM **define** class, hoặc gián tiếp **delegate** việc tải cho loader khác.

**Defining loader** của một class `C` là bộ nạp trực tiếp khiến JVM tạo định nghĩa runtime của `C`, điển hình bằng `ClassLoader.defineClass`. **Initiating loader** là loader mà JVM ghi nhận đã khởi xướng việc tải `C`, dù nó trực tiếp định nghĩa hay được trả về class từ quá trình ủy quyền.

~~~text
                Cần tạo class tên N
                        |
                 loader Child (Lc)
                        |
           +------------+------------+
           |                         |
     Tự find/define              Delegate sang Parent (Lp)
           |                         |
           v                         v
  Class C = (N, Lc)            Parent định nghĩa C
           |                         |
  Lc: defining + initiating          v
                              Class C = (N, Lp)
                                    |
                          Lp: defining + initiating
                          Lc: initiating
~~~

Đây là **hai nhánh có thể có**, không phải một lời gọi sẽ cùng đi cả hai. **Một runtime class có một defining loader** nhưng **có thể có nhiều initiating loaders**. Khi chuỗi ủy quyền dài, không được mặc định tất cả loader trung gian đều là initiating loader; JVMS có quy tắc ghi nhận cụ thể cho các loader tham gia.

| Tiêu chí | Initiating loader | Defining loader |
| --- | --- | --- |
| Mô tả | Loader đứng ra khởi xướng tải `C`, trực tiếp hoặc gián tiếp | Loader thực sự định nghĩa `C` trong VM |
| Có thể nhiều loader cho cùng `C`? | Có | Không, một class runtime có một defining loader |
| Có cần tự đọc bytecode `.class`? | Không bắt buộc; có thể delegate | Phải chịu trách nhiệm trực tiếp cho quá trình định nghĩa class (bootstrap có cơ chế riêng) |
| Quyết định identity của `C`? | Không tự nó quyết định | **Có**, cùng với binary name |
| `Class.getClassLoader()` quan sát được? | Không cho danh sách các initiating loaders | Trả defining loader, hoặc `null` với bootstrap |

### Bootstrap và một yêu cầu tải qua loader con

Trên JDK thông thường, `java.lang.String` do **bootstrap class loader** định nghĩa. Giả sử loader con nhận yêu cầu:

~~~java
Class<?> c = childLoader.loadClass("java.lang.String");
System.out.println(c == String.class);
System.out.println(c.getClassLoader() == null);
~~~

Đây là đoạn **minh họa cần đặt trong method đã khai báo biến `childLoader`**. Với cơ chế delegation thông thường, hai dòng in `true`. `childLoader` có thể là initiating loader nhưng **không phải defining loader** của String.

Giá trị `null` do `String.class.getClassLoader()` trả về là biểu diễn API cho **bootstrap**, không có nghĩa String “không được bộ nạp nào tải”. Tên class và defining loader cần được quan sát cùng nhau khi chẩn đoán.

## 3. Initiating loader không tự nhân đôi runtime class identity

Đối với class/interface thông thường, JVM định danh một kiểu bằng **(`binary name`, `defining loader`)**. Hai loader cùng yêu cầu `api.Service` có thể trả đúng **một** `Class<?>` khi đều ủy quyền tới một parent; trong trường hợp đó, **initiating loaders khác nhau không làm type identity khác đi**.

Ngược lại, nếu mỗi plugin loader tự định nghĩa `demo.Plugin` từ cùng bytes, chúng tạo hai runtime types riêng. `classA.getName().equals(classB.getName())` có thể `true` trong khi `classA == classB` là `false`, và `classA.cast(objectB)` có thể ném `ClassCastException`.

**Điểm nối sang mục 6:** hai type trùng binary name có thể cùng tồn tại hợp lệ. Chỉ khi một liên kết qua field/method descriptor **đòi thống nhất ý nghĩa kiểu** thì JVM mới áp loading constraints, không phải cứ có hai defining loaders là lỗi.

## 4. Delegation là đường đi tới defining loader, không phải identity

Cơ chế `ClassLoader.loadClass(name, resolve)` mặc định theo hướng **findLoadedClass → parent/bootstrap → findClass → resolveClass nếu yêu cầu**. Parent-first là hành vi mặc định hữu ích để chia sẻ API; custom loaders có thể chủ động dùng child-first cho implementation classes khi vẫn tuân thủ các ràng buộc JVM.

Khi debug, tách ba câu hỏi: (1) **ai được gọi** `loadClass`? (2) **ai thật sự** `defineClass`? (3) **ai sở hữu API type** nằm trong method/field descriptor qua hai loaders? `Class.getClassLoader()` phản ánh defining loader (bootstrap được biểu diễn `null`), **không** trả danh sách initiating loaders.

Những lần `loadClass` hoặc `Class.forName(name, false, loader)` không tự yêu cầu chạy `<clinit>`; khởi tạo lớp là vấn đề riêng. Mục này chỉ đặt ngữ cảnh để đi sâu vào **constraint hình thức** tại mục 6, thay vì lặp lại toàn bộ thuật toán và API của bài về bootstrap/platform/application delegation.

## 5. Thực hành Java 17+: hai `URLClassLoader` cùng tải một class

Thực hành này đủ để chạy trên JDK 17+ **không dùng thư viện ngoài**. Nó chủ động giữ tệp plugin trong thư mục riêng để hai loader có thể định nghĩa hai bản độc lập.

### 5.1. Cấu trúc files

~~~text
loader-lab/
  demo/
    Plugin.java
  LoaderLab.java
~~~

Nội dung `demo/Plugin.java`:

~~~java
package demo;

public class Plugin {
    public String message() {
        return "plugin";
    }
}
~~~

Nội dung `LoaderLab.java` tại thư mục gốc `loader-lab`:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderLab {
    public static void main(String[] args) throws Exception {
        Path compiled = Path.of("plugin-classes").toAbsolutePath();
        URL[] urls = { compiled.toUri().toURL() };

        // Platform loader KHÔNG phải application loader của LoaderLab.
        // Vì vậy demo.Plugin không bị app classpath chiếm trước.
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader loaderA = new URLClassLoader(urls, parent);
             URLClassLoader loaderB = new URLClassLoader(urls, parent)) {

            Class<?> classA = loaderA.loadClass("demo.Plugin");
            Class<?> classB = loaderB.loadClass("demo.Plugin");

            Object objectA = classA.getDeclaredConstructor().newInstance();
            Object objectB = classB.getDeclaredConstructor().newInstance();

            System.out.println("same name="
                    + classA.getName().equals(classB.getName()));
            System.out.println("same class=" + (classA == classB));
            System.out.println("loader A defines="
                    + (classA.getClassLoader() == loaderA));
            System.out.println("loader B defines="
                    + (classB.getClassLoader() == loaderB));
            System.out.println("cross-instance="
                    + classA.isInstance(objectB));
            System.out.println("same within A="
                    + (objectA.getClass() == classA));

            try {
                classA.cast(objectB);
                System.out.println("unexpected cast success");
            } catch (ClassCastException expected) {
                System.out.println("cast=ClassCastException");
            }

            Class<?> stringViaA = loaderA.loadClass("java.lang.String");
            System.out.println("delegated String="
                    + (stringViaA == String.class));
            System.out.println("String bootstrap="
                    + (String.class.getClassLoader() == null));
        }
    }
}
~~~

### 5.2. Biên dịch và chạy

Tại thư mục `loader-lab` trong terminal:

~~~bash
mkdir plugin-classes
javac -d plugin-classes demo/Plugin.java
javac LoaderLab.java
java LoaderLab
~~~

Với PowerShell cũng có thể tạo thư mục trước bằng `New-Item -ItemType Directory -Force plugin-classes`. Đừng thêm `plugin-classes` vào parent **platform** loader path; ví dụ cần mỗi `URLClassLoader` tự tìm được `demo.Plugin` từ URL đầu vào. Nếu thư mục đã tồn tại, bỏ bước tạo lại.

**Stdout chính xác khi chạy trong bố cục chuẩn:**

~~~text
same name=true
same class=false
loader A defines=true
loader B defines=true
cross-instance=false
same within A=true
cast=ClassCastException
delegated String=true
String bootstrap=true
~~~

### 5.3. Vì sao từng dòng đúng?

- **`same name=true`**: tên nhị phân của hai class là `demo.Plugin`.
- **`same class=false`**: LoaderA/LoaderB là hai defining loaders riêng, nên runtime class identity khác nhau.
- **`loader A defines=true`** và **`loader B defines=true`**: hai class thực sự do đúng loader riêng định nghĩa.
- **`cross-instance=false`**: object của classB không phải instance của classA.
- **`same within A=true`**: objectA được tạo từ classA.
- **`cast=ClassCastException`**: phép cast dựa trên runtime types, không dựa trên tên hoặc bytecode giống nhau.
- **`delegated String=true`**: class String trả về khi loaderA yêu cầu vẫn là `String.class` của bootstrap.
- **`String bootstrap=true`**: Java API đại diện bootstrap loader bằng `null`.

**Quan trọng:** demo tạo **`ClassCastException` khi cố cast**, **không chủ ý tạo loading constraint violation**. Hai class trùng tên nhưng tách biệt có thể tồn tại hợp lệ. `LinkageError` liên quan loading constraints xảy ra khi **một quy tắc liên kết cụ thể** đòi hai cách hiểu tên kiểu phải khớp mà không thể khớp.

### 5.4. Nếu muốn dùng một parent chung?

Thử thay đổi kiến trúc để cả hai child ủy quyền cho **một parent đã định nghĩa `demo.Plugin`**. Khi parent trả class chung, có thể:

~~~text
classA == classB  -> true
classA.getClassLoader() == parent -> true
~~~

Đây là **kịch bản so sánh**, không phải lời khuyên tùy tiện sửa ví dụ bằng cách đổi đúng một tham số: parent cần được thiết lập có khả năng tải Plugin và việc ủy quyền phải thực sự parent-first. Mục tiêu là thấy **initiating loader có thể khác defining loader**.

## 6. Loading constraints: vì sao JVM phải ràng buộc loader với nhau?

Cho hai class đã được định nghĩa bởi các loader khác nhau, khi lớp này tham chiếu method/field của lớp kia, JVM cần thống nhất ý nghĩa của các **reference types xuất hiện trong descriptors**. Nếu không, một kiểu có tên giống nhau nhưng identity khác nhau có thể phá vỡ type safety khi chuyển giá trị qua biên giới class.

**JVMS §5.3.4** biểu diễn ràng buộc bằng dạng:

~~~text
N^L1 = N^L2

Tên class/interface N, khi được tải qua loader L1 hoặc L2,
phải cùng chỉ tới MỘT runtime class/interface.
~~~

Đây là **ràng buộc kết quả tải của một tên kiểu `N`**, không phải ràng buộc `L1 == L2`. Nếu L1 và L2 delegate tên `N` về cùng một defining loader chung, constraint được đáp ứng.

### Ví dụ phương thức đi qua API boundary

Giả sử hệ thống host định nghĩa contract:

~~~java
package api;

public interface Service {
    Message convert(Message input);
}
~~~

và `api.Message` là một class độc lập, có runtime identity do **shared host/API loader** định nghĩa. Plugin triển khai:

~~~java
package plugin;

public final class ServiceImpl implements api.Service {
    @Override
    public api.Message convert(api.Message input) {
        return input;
    }
}
~~~

**Hai đoạn trên là mã minh họa trong các file khác nhau và còn cần class `api.Message` cùng cấu hình build/classpath thích hợp; không phải một file runnable độc lập.**

Trong method descriptor `(Lapi/Message;)Lapi/Message;`, cả tham số và kết quả đều nhắc tới tên `api/Message`. Khi JVM kiểm tra khả năng override và resolution xuyên loaders, nó có thể áp loading constraint:

~~~text
api/Message ^ L_host  =  api/Message ^ L_plugin
~~~

Nếu host loader và plugin loader đều dẫn tới cùng `api.Message` do parent định nghĩa, hai vế thống nhất. Nếu plugin loader cố định nghĩa `api.Message` riêng khiến nó khác host `api.Message`, ràng buộc liên kết có thể **không thể thỏa**, gây **`LinkageError` do loader constraint violation**.

~~~text
         HOST                             PLUGIN
      loader H                           loader P
         |                                  |
  api.Service.convert(Message)   ServiceImpl.convert(Message)
         |                                  |
         +---- type N = api/Message --------+
              constraint N^H = N^P

Trường hợp đúng:
  H và P tải api.Message thành cùng runtime class từ shared loader.

Trường hợp vi phạm:
  H và P đã ghi nhận hai runtime api.Message khác nhau,
  nhưng liên kết lại yêu cầu đồng nhất type ở chữ ký.
~~~

**Không** phải cứ hai loaders có class tên trùng là VM ném lỗi. Loader constraints được áp dụng ở những mối quan hệ **liên kết cụ thể**. Hai class `demo.Plugin` riêng được dùng nội bộ, không có ràng buộc đồng nhất giữa chúng, có thể cùng tồn tại bình thường.

### Các thời điểm JVM áp loading constraints

Theo JVMS, những nơi quan trọng gồm:

1. **Preparation (§5.4.2)** của class/interface: khi method instance có thể override method của superclass/superinterface, cần bảo đảm những tên class/interface trong method descriptor không mang nghĩa mâu thuẫn giữa defining loaders.
2. **Field resolution (§5.4.3.2)**: các reference type names trong field descriptor phải được hiểu nhất quán giữa referencing class và field owner khi VM áp constraint.
3. **Method/interface method resolution (`5.4.3.3–`5.4.3.4)**: các names trong method descriptors có thể bị ràng buộc xuyên loader.
4. **Khi ghi nhận initiating loader**: VM phải kiểm tra ngay các constraints đã có; nếu bị vi phạm, bỏ thao tác ghi nhận và ném `LinkageError` theo đặc tả.

**Resolution có thể diễn ra sớm hoặc trì hoãn** theo quy tắc JVM, do đó thời điểm ném lỗi có thể không trùng dòng source nơi bạn “tạo ra” cấu hình loader. Không nên kết luận “đã chạy được `main` thì mọi method signatures xuyên plugin đã link thành công”.

### Không nhầm loading constraints với dynamic dispatch

- **Resolution** xác định kết quả symbolic reference trong constant pool.
- **Loading constraint** giữ ý nghĩa các kiểu trong descriptor nhất quán qua loaders khi liên kết.
- **Dynamic dispatch** quyết định method implementation nào chạy khi gọi ảo theo runtime object type.
- **`invokedynamic`** có cơ chế call-site/bootstrap riêng.

Các khái niệm cùng tham gia execution/linking nhưng **không thể dùng thay thế cho nhau**.

## 7. So sánh lỗi loading, linking và cast

| Triệu chứng | Loại | Ý nghĩa và hướng kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` | Checked exception | Lời gọi tải class explicit không tìm thấy tên; xem loader path, binary name, JAR/module |
| `NoClassDefFoundError` | `LinkageError` subclass | Class được tham chiếu trong execution/linking không tìm/khởi tạo được trong tình huống tương ứng; xem cause và lỗi trước |
| `ClassCastException` | Runtime exception | Object không tương thích runtime type đích; kiểm tra cả `getName` lẫn `getClassLoader` |
| `LinkageError: loader constraint violation` | `LinkageError` | Type names trong descriptors qua loader phải đồng nhất nhưng lại không thể đồng nhất |
| Duplicate class definition | `LinkageError` trong tình huống thích hợp | Cùng một defining loader cố tạo lại class có tên đã định nghĩa |
| `NoSuchMethodError` hoặc `NoSuchFieldError` | `LinkageError` subclass | Tham chiếu symbolic không phù hợp API thực được nạp; kiểm tra dependency versions |
| `IllegalAccessError` | `LinkageError` subclass | Runtime access check không cho phép; xem package identity, visibility, module exports |
| `ExceptionInInitializerError` | `LinkageError` subclass | Initialization `static` thất bại; tìm cause thay vì mặc định lỗi delegation |

**Quy tắc chẩn đoán:** không gọi mọi `LinkageError` là loader constraint violation. Ngoài ra, `ClassCastException` trong ví dụ LoaderLab **khác** `LinkageError`: tải hai class thành công, chỉ đến lúc cast mới thấy không tương thích.

### Lỗi do duplicate API jar

Một lỗi phổ biến: host đã có `api.Message`, nhưng plugin JAR cũng bundle riêng `api.Message` và custom loader là **child-first**. Việc trùng tên có thể không gây lỗi ngay. Khi plugin implement shared interface `api.Service` và method descriptor liên quan tới `api.Message`, JVM có thể cần buộc hai loader đồng nhất type đó. Cách khắc phục là **chia sẻ API definition qua loader chung**, không cố ép cast giữa hai class khác identity.

Trong Maven/Gradle hoặc hệ build tương đương, dependency chỉ dành cho compile nhưng do host cung cấp tại runtime có thể được đánh dấu `provided` hoặc `compileOnly` theo mục đích. Tuy nhiên vẫn cần kiểm tra packaging thực tế và cơ chế loader của framework, không suy rằng chỉ đổi dependency scope là tự sửa mọi lỗi.

## 8. Array classes và bootstrap: một ngoại lệ cần biết

Array classes **được JVM tạo trực tiếp** theo **JVMS §5.3.3**, không có một file `[I.class` để người viết custom loader tự tìm qua `findClass` như class Java thông thường.

- Nếu component type là **reference type**, array class có defining loader của component type.
- Nếu component là **primitive type**, array class có bootstrap defining loader.
- JVM ghi nhận initiating loader cho array class theo thủ tục của JVMS.

Ví dụ chạy được Java 17+:

~~~java
public class ArrayLoaderCheck {
    public static void main(String[] args) {
        System.out.println("String[] bootstrap="
                + (String[].class.getClassLoader() == null));
        System.out.println("int[] bootstrap="
                + (int[].class.getClassLoader() == null));
    }
}
~~~

~~~bash
javac ArrayLoaderCheck.java
java ArrayLoaderCheck
~~~

**Stdout:**

~~~text
String[] bootstrap=true
int[] bootstrap=true
~~~

Nếu `demo.Plugin` được LoaderA và LoaderB định nghĩa độc lập, các array classes `demo.Plugin[]` tương ứng cũng **khác identity** do component types khác nhau. Đừng lẫn array class identity với việc hai mảng chỉ có các phần tử cùng tên class.

## 9. Thiết kế plugin và shared API hợp lý

Một sơ đồ hữu ích:

~~~text
Host / Shared API loader
   |
   +-- api.Service
   +-- api.Message
   +-- api.PluginContext
   |
   +-- Plugin A loader
   |      pluginA.ServiceImpl
   |      pluginA.InternalCache
   |      (api.* -> delegate shared loader)
   |
   +-- Plugin B loader
          pluginB.ServiceImpl
          pluginB.InternalCache
          (api.* -> delegate shared loader)
~~~

### Quy tắc thực hành

1. **Chia sẻ API types qua một defining loader chung.** Interfaces/DTOs/classes xuất hiện trong boundary method/field descriptors nên được quản lý nhất quán.
2. **Cô lập implementation classes** ở từng plugin loader khi cần. Class nội bộ có thể cùng tên ở hai plugin nếu không ảnh hưởng API boundaries.
3. **Không đóng gói trùng API JAR vào plugin** khi custom loader có thể tự định nghĩa lại API classes. Xem xét dependency scope và runtime packaging.
4. **Log actual defining loader**, không chỉ `Class.getName()`. `getModule()` và JAR source cũng hữu ích.
5. **Cẩn trọng hot reload**: thế hệ plugin cũ và mới có thể dùng hai loaders khác nhau; instances cũ không tự chuyển sang type mới.
6. **Giải phóng references** khi unload: host singleton, thread context class loader, static maps, threads hoặc callback có thể giữ loader cũ reachable.
7. **Không coi class loader là sandbox bảo mật tuyệt đối.** Việc nạp code không tin cậy đòi ranh giới bảo mật riêng; JVM không bảo đảm isolation ở mức process chỉ nhờ hai class loaders.

### Thread context class loader (TCCL)

`Thread.currentThread().getContextClassLoader()` cho biết **context class loader** của thread. Một số API/framework, ví dụ cơ chế tìm provider, có thể sử dụng nó. Nhưng TCCL **không thay đổi defining loader** của class đã được JVM tạo trước đó.

Một dòng debug:

~~~java
System.out.println(Thread.currentThread().getContextClassLoader());
~~~

không thay thế:

~~~java
System.out.println(obj.getClass().getClassLoader());
~~~

Đoạn thứ hai cần có `obj` không `null` trong context. Nếu TCCL giữ tham chiếu tới plugin loader cũ trên thread còn sống, đây cũng có thể là nguyên nhân loader không được thu hồi khi hot reload.

## 10. Debugging: cách truy vết class identity và loader constraints

Khi gặp lỗi có tên lớp lặp lại hoặc keyword `loader constraint violation`, nên điều tra theo trình tự:

1. **Xác định loại lỗi gốc** và cause chain: `ClassCastException`, `LinkageError`, `NoClassDefFoundError`, `IllegalAccessError`?
2. **Ghi tên class và defining loaders** của cả hai bên: `Class.getName()`, `Class.getClassLoader()`, `Class.getModule()`; so loader objects bằng `==`.
3. **Đọc field/method descriptors** của API boundaries bằng `javap -v -p` hoặc `javap -s -p`. Chú ý DTO/shared interface types trong dạng `Lapi/Message;`.
4. **Kiểm tra JAR trùng lặp**: một type name có trong cả host classpath và plugin JAR không?
5. **Kiểm tra delegation policy** thực tế, nhất là classloader child-first và package allow/deny lists.
6. **Kiểm tra runtime package và module boundaries** nếu là lỗi truy cập, không chỉ import trong source.
7. **Khảo sát thread context loader** và references cũ khi hot reload.
8. **Sửa shared API ownership**, đóng gói dependency hoặc loader graph có kiểm chứng, rồi chạy lại integration tests.

Các lệnh:

~~~bash
java -version
jar tf plugin.jar
javap -s -p -classpath plugin.jar plugin.ServiceImpl
javap -v -p -classpath plugin.jar plugin.ServiceImpl
java -Xlog:class+load=info -jar host.jar
~~~

Đây là **mẫu thao tác**, thay tên JAR/class bằng file thực. `-Xlog:class+load=info` là logging trên **HotSpot hiện đại**, không bảo đảm mọi JVM hỗ trợ y hệt. Dòng log loading cho biết các lớp được load/nguồn class, nhưng để xác nhận defining loader object nên kết hợp thông tin runtime. Xem `java -Xlog:help` trên HotSpot tương ứng.

Đoạn method kiểm tra hai object (cần đặt trong một class, và cả hai đối số khác `null`):

~~~java
static void inspect(Object a, Object b) {
    Class<?> c1 = a.getClass();
    Class<?> c2 = b.getClass();

    System.out.println("name1=" + c1.getName());
    System.out.println("name2=" + c2.getName());
    System.out.println("same class=" + (c1 == c2));
    System.out.println("loader1=" + c1.getClassLoader());
    System.out.println("loader2=" + c2.getClassLoader());
    System.out.println("1 accepts 2=" + c1.isInstance(b));
}
~~~

**Không** chỉ so tên loader bằng `toString()`, vì các ID/hash có thể khác nhau giữa các lần chạy. Hãy dùng object identity khi so loader hoặc `Class<?>` thực tế.

## 11. Những nhầm lẫn cần tránh

| Hiểu nhầm | Phân biệt đúng |
| --- | --- |
| “Loader mà mình gọi `loadClass` chính là defining loader.” | Loader được gọi có thể **delegate**; `getClassLoader()` cho biết defining loader. |
| “Một class luôn chỉ có một initiating loader.” | Có thể có **nhiều** initiating loaders và một defining loader. |
| “Cùng fully qualified name nghĩa cùng Java class.” | Cần cùng **defining loader** và binary name. |
| “Cùng nội dung class bytes thì chắc chắn có thể cast qua loader.” | Khác defining loader có thể khác runtime class identity. |
| “Parent-first là luật cứng của mọi custom loader.” | Là default của `ClassLoader`, custom loader có thể có chính sách hợp lệ khác. |
| “Chỉ cần đổi tên package cho giống nhau là mở được package-private access.” | Runtime package và module rules vẫn quan trọng. |
| “Bất kỳ class trùng tên qua hai loaders sẽ ném `LinkageError`.” | Nhiều định nghĩa có thể cùng tồn tại; lỗi constraint cần quan hệ liên kết bắt buộc. |
| “`ClassCastException` và loader constraint violation là cùng lỗi.” | Một là cast runtime; một là vấn đề an toàn kiểu khi linking/preparation. |
| “Loading constraint buộc hai loader objects phải bằng nhau.” | Buộc **class được tải qua chúng** cho tên ràng buộc phải đồng nhất. |
| “Tải class tức chạy `static {}`.” | Loading khác initialization. |
| “Class loader hiện trong `getClassLoader()` là toàn bộ initiating loader history.” | API trả defining loader, không phải danh sách lịch sử. |
| “`Class.forName(name, false, loader)` đảm bảo không liên kết class.” | Nó tránh yêu cầu initialization; linking có thể xảy ra. |
| “Loader của `int[]` phải tìm bytecode `[I.class`.” | Array class được VM tạo trực tiếp. |
| “TCCL quyết định defining loader cho mọi class của thread.” | TCCL phục vụ lookup theo context cho một số API/framework; không sửa class identity đã tạo. |
| “Đóng `URLClassLoader` khiến mọi class và object nó từng định nghĩa biến mất ngay.” | Class unloading phụ thuộc reachability và GC; đóng loader không ép mọi object biến mất. |

## 12. Câu hỏi tự kiểm tra

**1.** `child.loadClass("java.lang.String")` trả `String.class`. Loader nào định nghĩa class?  
**Đáp án:** Bootstrap (trên JDK chuẩn). Child có thể là initiating loader nhưng không phải defining loader.

**2.** Vì sao hai `URLClassLoader` khác nhau đều đọc cùng bytes mà `classA != classB`?  
**Đáp án:** Runtime identity là cặp (`binary name`, `defining loader`), và defining loaders khác nhau.

**3.** `classA.getName().equals(classB.getName())` là `true` thì `classA.isInstance(objectB)` tự đúng không?  
**Đáp án:** Không. Kiểm tra kiểu dùng runtime identity, không chỉ tên.

**4.** Ràng buộc `api/Message^L1 = api/Message^L2` có ý nghĩa gì?  
**Đáp án:** Với tên `api/Message`, kết quả tải qua hai loaders phải chỉ cùng runtime class/interface, không yêu cầu loader objects là một.

**5.** Tại sao host/plugin có thể gặp loader constraint violation trong `Service.convert(Message)`?  
**Đáp án:** Nếu cùng type name `api.Message` trong descriptor lại được diễn giải thành hai classes khác nhau, JVM không thể bảo đảm hợp đồng method xuyên loader khi constraint yêu cầu đồng nhất.

**6.** Nếu hai class `demo.Plugin` chỉ được dùng riêng trong hai plugin không có ràng buộc giữa chúng, có buộc `LinkageError` không?  
**Đáp án:** Không. Chúng có thể cùng tồn tại hợp lệ.

**7.** Loader nào là defining loader khi code của nó gọi `defineClass` để tạo một class thành công?  
**Đáp án:** Chính loader đó.

**8.** `Class.getClassLoader()` có cung cấp danh sách tất cả initiating loaders không?  
**Đáp án:** Không. Nó phản ánh defining loader.

**9.** `Class.forName(name, false, loader)` có yêu cầu chạy static initializer không?  
**Đáp án:** Không chủ động yêu cầu initialization; class vẫn có thể được load/link.

**10.** `String[].class` có defining loader riêng do `URLClassLoader` đọc từ file `[Ljava/lang/String;.class` không?  
**Đáp án:** Không. Array class do VM tạo, defining loader gắn với component `String` theo quy tắc array classes.

## 13. Nguồn chính thức

- [JVMS Java SE 25 — §5.3 Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): định nghĩa initiating loader, defining loader và class identity.
- [JVMS Java SE 25 — §5.3.1–5.3.3](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3.1): tải bằng bootstrap/user-defined loader và array classes.
- [JVMS Java SE 25 — §5.3.4 Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3.4): `N^L1 = N^L2`, nơi bắt buộc kiểm tra và `LinkageError` khi vi phạm.
- [JVMS Java SE 25 — §5.4.2 Preparation](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4.2): ràng buộc cho method overriding.
- [JVMS Java SE 25 — §5.4.3 Resolution](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4.3): field/method references xuyên loader.
- [JDK 25 — ClassLoader API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `findClass`, `defineClass`.
- [JDK 25 — URLClassLoader API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): tải classes/resources qua URLs và đóng loader.
- [JDK 25 — Class API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `getName`, `isInstance`, `cast`, `forName`.
- [JLS Java SE 25 — §12.2 Loading](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.2): loading classes/interfaces và tính nhất quán giữa class loader environments.

**Ghi nhớ cuối cùng:** Muốn biết “ai yêu cầu tải?” hãy xét **initiating loader**. Muốn biết “kiểu nào trong JVM?” phải xét **binary name + defining loader**. Muốn biết “hai loader có được dùng hai cách hiểu khác nhau về một kiểu trong API boundary không?” hãy kiểm tra **loading constraints**, thay vì đồng nhất mọi lỗi cast hoặc class loading với `LinkageError`.