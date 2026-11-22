# Defining loader và initiating loader trong JVM

## 1. Vì sao có hai khái niệm “loader”?

Khi đọc mã Java, bạn thường gặp biểu thức:

~~~java
Class<?> type = loader.loadClass("demo.Widget");
~~~

Dễ kết luận rằng đối tượng **loader** chính là bộ nạp đã **định nghĩa** class **demo.Widget**. Kết luận đó có thể sai: **loader** có thể nhận yêu cầu rồi **ủy quyền (delegate)** cho loader khác. JVM phân biệt hai vai trò:

- **Defining loader**: loader thực sự tạo/định nghĩa class hoặc interface runtime từ biểu diễn của kiểu; với class thông thường, đó là loader trực tiếp định nghĩa lớp.
- **Initiating loader**: loader tham gia **khởi xướng loading** của một class hoặc interface, dù có thể trả về định nghĩa được tạo bởi loader khác.

Một kiểu runtime có **một defining loader**, nhưng có thể được nhiều loader khác nhau **initiate**. Đó là lý do “loader được yêu cầu tìm lớp” và “loader sở hữu định nghĩa runtime của lớp” là hai câu hỏi riêng.

Bài này tập trung vào **cơ chế ủy quyền** và sự khác biệt giữa hai vai trò theo JVM Specification (JVMS §5.3, §5.3.4), sau đó liên hệ với đối tượng `Class`, danh tính kiểu, các API và tình huống lỗi thực tế.

## 2. Ví dụ khái niệm: A yêu cầu, B định nghĩa

Giả sử application có loader **ChildLoader A** và parent **AppLoader B**. B đã tìm và định nghĩa class **demo.Shared**.

~~~text
                 JVM / mã Java
                       |
                       | yêu cầu A tìm demo.Shared
                       v
              ChildLoader A
              (initiating)
                       |
                       | delegate theo parent-first
                       v
              AppLoader B
              (defining)
                       |
                       | tìm/định nghĩa demo.Shared
                       v
           Class<?> của demo.Shared
                       |
                       | trả cùng đối tượng Class
                       v
                  ChildLoader A
                       |
                       v
                  mã yêu cầu
~~~

Trong tình huống delegation này:

1. **A** tiếp nhận yêu cầu load. A có thể được ghi nhận là initiating loader của kiểu được trả về.
2. **B** cung cấp định nghĩa runtime thực tế; **B** là defining loader.
3. Kết quả trả về từ **A.loadClass("demo.Shared")** vẫn có **getClassLoader() == B**.
4. Nếu nhiều child loader cùng delegate tới B, chúng có thể nhận **cùng một đối tượng `Class`**.
5. Không xuất hiện một class mới “do A định nghĩa” chỉ vì A nhận yêu cầu.

**Chú ý thuật ngữ:** Các bước bên dưới mô tả việc loader nhận và delegate yêu cầu. JVMS là cơ sở chính xác để xác định *initiating loader* trong bối cảnh JVM ghi nhận loading; đừng chỉ đếm mọi object ClassLoader xuất hiện trong một chuỗi gọi Java rồi khẳng định tất cả đều được JVM ghi nhận như initiating loader. Đặc biệt, định nghĩa initiating loader gắn với các sự kiện loading của JVM, không phải một tập do ứng dụng tự đặt tên.

## 3. Định nghĩa chính xác theo JVM Specification

JVMS §5.3 mô tả loading là quá trình tìm một biểu diễn nhị phân của class/interface và tạo kiểu runtime. Với **non-array class/interface**:

- Loader **L** có thể tự lấy bytecode và yêu cầu JVM tạo class từ biểu diễn đó: **L trực tiếp định nghĩa class**.
- Loader **L** cũng có thể **ủy quyền** công việc cho loader khác, rồi trả về class mà loader kia đã định nghĩa: **L nạp gián tiếp**.
- Nếu JVM yêu cầu **L** khởi xướng việc loading và L trả về class được loader khác tạo, **initiating loader và defining loader có thể khác nhau**.
- Defining loader cũng đóng vai trò initiating loader của class nó định nghĩa. Một class có thể được ghi nhận với thêm initiating loader khác qua delegation.
- Danh tính runtime của non-array class/interface là cặp **(binary name, defining loader)**, không bao gồm tên của tất cả initiating loader.

| Câu hỏi | Defining loader | Initiating loader |
| --- | --- | --- |
| Ai thực sự định nghĩa kiểu runtime? | Chính loader này. | Có thể chính nó hoặc loader khác. |
| Một kiểu runtime có thể có bao nhiêu? | Một defining loader. | Có thể nhiều initiating loader. |
| Thành phần danh tính của class? | **Có**: kết hợp binary name. | **Không**: không tạo danh tính mới chỉ bởi việc initiate. |
| `Class.getClassLoader()` trả về? | Defining loader (hoặc null với bootstrap). | Không phải API liệt kê initiating loader. |
| Delegation có thể làm hai vai trò khác nhau? | Có. | Có. |
| Hai loader chỉ initiate cùng class thì có hai bản class? | Không. | Không. |
| Hai loader trực tiếp define cùng binary name riêng rẽ? | Tạo hai runtime class khác nhau. | Mỗi loader cũng initiate lớp mình define. |

### 3.1 “Định nghĩa một class” có nghĩa là gì?

Một class loader trực tiếp định nghĩa lớp khi JVM tạo biểu diễn runtime từ một binary representation gắn với loader đó. Với custom Java loader, hoạt động này thường dùng các overload của **ClassLoader.defineClass**.

~~~text
bytes cho demo.Widget
         |
         v
ClassLoader L -- defineClass(...) --> JVM
                                      |
                                      v
                            runtime class demo.Widget
                            defining loader = L
                                      |
                                      v
                            java.lang.Class mirror
~~~

Một lớp được định nghĩa một lần bởi L không thể bị thay lén thành một class thứ hai với **cùng binary name và cùng defining loader L** bằng việc gọi defineClass lại. Việc redefine bằng instrumentation là một cơ chế khác, không nên đánh đồng với định nghĩa thêm một class riêng.

Defining loader không chỉ ảnh hưởng đến danh tính kiểu mà còn tham gia vào xác định **runtime package** (tên package và defining loader), loading constraints và các quy tắc bảo đảm type safety.

### 3.2 “Khởi xướng loading” không đồng nghĩa “đã chạy static block”

Tên **initiating loader** nói về **loading**, không phải **class initialization**. Một lời gọi **loadClass** thường chưa làm static initializer chạy.

Ba bước khác nhau:

~~~text
LOADING
  tìm/định nghĩa kiểu; xác định initiating và defining loader
       |
       v
LINKING
  verification, preparation, resolution theo quy tắc JVM
       |
       v
INITIALIZATION
  thực thi logic static khi có active use và các trigger tương ứng
~~~

Từ “initiating” trong tên initiating loader **không có nghĩa** là “loader khởi tạo static fields”. Đây là nhầm lẫn phổ biến vì hai từ *initiate* và *initialize* có vẻ gần nghĩa.

## 4. Java ClassLoader thường ủy quyền như thế nào?

Với implementation mặc định của **ClassLoader.loadClass(name, resolve)**, quá trình thường gồm:

1. **findLoadedClass(name)** kiểm tra xem JVM đã ghi nhận class tương ứng đối với loader hiện tại chưa.
2. Nếu chưa, thử **parent.loadClass(name)**, hoặc bootstrap theo điều kiện của loader.
3. Nếu parent không tìm được, gọi **findClass(name)** do loader hiện tại cài đặt.
4. Nếu cần, thực hiện **resolveClass** rồi trả về đối tượng `Class`.

Mã giả thể hiện ý tưởng:

~~~java
// Pseudo-code minh họa, không phải mã nguồn JDK nguyên văn
Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
    Class<?> clazz = findLoadedClass(name);

    if (clazz == null) {
        try {
            clazz = delegateToParentOrBootstrap(name);
        } catch (ClassNotFoundException ignored) {
            clazz = findClass(name);
        }
    }

    if (resolve) {
        resolveClass(clazz);
    }

    return clazz;
}
~~~

Đây là cơ chế **parent-first phổ biến**, không phải quy tắc mọi ClassLoader tùy biến đều phải theo. Các plugin container, application server hay loader tự viết có thể thay đổi chính sách tìm lớp (cần bảo đảm ràng buộc JVM).

### 4.1 Vì sao một class có nhiều initiating loader?

Giả sử **Loader A** và **Loader C** là hai child loader khác nhau, cùng delegate tới **Loader B**:

~~~text
      Loader A                 Loader C
    (requester)              (requester)
        |                        |
        +-----------+------------+
                    |
                    v
                Loader B
           định nghĩa demo.Shared
                    |
                    v
        MỘT java.lang.Class duy nhất
              cho demo.Shared
~~~

Nếu JVM loading ghi nhận A và C là những initiating loader thích hợp, vẫn **chỉ có một class** vì defining loader là B.

Điều cần kiểm tra là **định nghĩa cuối cùng của class thuộc loader nào**. Việc tạo nhiều object ClassLoader không tự nhân bản những class được parent định nghĩa.

## 5. Ví dụ Java 17+ số 1: child loader initiate, parent define

Tạo tệp **DelegationRolesDemo.java** với một nested class và một child loader:

~~~java
public class DelegationRolesDemo {
    static class Shared {
        static {
            System.out.println("Shared initialized");
        }
    }

    static class ChildLoader extends ClassLoader {
        int ownFindClassCalls;

        ChildLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            ownFindClassCalls++;
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader appLoader = DelegationRolesDemo.class.getClassLoader();
        ChildLoader child = new ChildLoader(appLoader);

        Class<?> first = child.loadClass(Shared.class.getName());
        System.out.println("same Class = " + (first == Shared.class));
        System.out.println("child defines = "
                + (first.getClassLoader() == child));
        System.out.println("app defines = "
                + (first.getClassLoader() == appLoader));
        System.out.println("child findClass calls = "
                + child.ownFindClassCalls);

        Class<?> again = child.loadClass(Shared.class.getName());
        System.out.println("same repeated result = " + (first == again));

        System.out.println("before active use");
        new Shared();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DelegationRolesDemo.java
java DelegationRolesDemo
~~~

Stdout:

~~~text
same Class = true
child defines = false
app defines = true
child findClass calls = 0
same repeated result = true
before active use
Shared initialized
~~~

### Phân tích kết quả

**child.loadClass(...)** nhận yêu cầu đầu tiên nhưng dùng parent-first; application loader đã có thể tìm nested class `DelegationRolesDemo$Shared` nên **ChildLoader.findClass** không được gọi.

**first == Shared.class** đúng vì cả hai là **cùng một class runtime**, do application loader định nghĩa.

**first.getClassLoader() == child** là false; **first.getClassLoader() == appLoader** là true. Đây là chứng cứ trực tiếp xác nhận defining loader, bất kể child loader nào được yêu cầu load.

Gọi **child.loadClass(...)** lần nữa trả về cùng một `Class`; chương trình không định nghĩa bản Shared riêng.

Dòng **Shared initialized** chỉ xuất hiện khi **new Shared()** tạo active use. Các lần gọi **loadClass** trước đó không tự khởi tạo Shared.

**Cách kiểm tra thực tế:** nếu class được bootstrap định nghĩa như **java.lang.String**, **String.class.getClassLoader()** trả về **null** trong Java. Null thể hiện bootstrap loader, không có nghĩa kiểu “không có defining loader”.

## 6. Ví dụ Java 17+ số 2: hai defining loader tạo hai kiểu khác nhau

Ví dụ trước cho thấy nhiều loader delegate vẫn nhận **một** class. Bây giờ xét trường hợp hai loader thực sự tự định nghĩa cùng binary name từ cùng tệp bytecode.

Tạo cấu trúc:

~~~text
project/
├── IsolationDemo.java
└── src/
    └── sample/
        └── Payload.java
~~~

**src/sample/Payload.java**:

~~~java
package sample;

public class Payload {
    public Payload() {
    }

    public String message() {
        return "hello";
    }
}
~~~

**IsolationDemo.java**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class IsolationDemo {
    public static void main(String[] args) throws Exception {
        URL classes = Path.of("out").toUri().toURL();

        try (URLClassLoader left = new URLClassLoader(
                     new URL[]{classes},
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader right = new URLClassLoader(
                     new URL[]{classes},
                     ClassLoader.getPlatformClassLoader())) {

            Class<?> a = left.loadClass("sample.Payload");
            Class<?> b = right.loadClass("sample.Payload");

            System.out.println("same name = "
                    + a.getName().equals(b.getName()));
            System.out.println("same Class = " + (a == b));
            System.out.println("left defines a = "
                    + (a.getClassLoader() == left));
            System.out.println("right defines b = "
                    + (b.getClassLoader() == right));

            Object fromRight = b.getDeclaredConstructor().newInstance();
            try {
                a.cast(fromRight);
                System.out.println("cast succeeded");
            } catch (ClassCastException expected) {
                System.out.println("cross-loader cast = ClassCastException");
            }
        }
    }
}
~~~

Đứng trong thư mục **project**, chạy:

~~~bash
javac -d out src/sample/Payload.java IsolationDemo.java
java -cp out IsolationDemo
~~~

Stdout:

~~~text
same name = true
same Class = false
left defines a = true
right defines b = true
cross-loader cast = ClassCastException
~~~

### Tại sao hai loader đều define Payload?

Ở đây cả hai **URLClassLoader** có **platform class loader** làm parent. Platform loader trong lệnh chạy ví dụ này không tìm lớp ứng dụng `sample.Payload` ở thư mục `out`, vì vậy mỗi URLClassLoader tự tìm file ở URL riêng và tự định nghĩa lớp.

Cả **a** và **b** đều có tên nhị phân `sample.Payload`, bytecode cũng đến từ cùng file, nhưng **defining loader khác nhau**. Do đó:

~~~text
(sample.Payload, left)  !=  (sample.Payload, right)
~~~

Hai object của các lớp này không tự tương thích kiểu. Phép **a.cast(fromRight)** ném ClassCastException, dù tên class trông giống nhau.

**Điều kiện quan trọng để tái hiện:** parent của hai URLClassLoader phải **không nạp được sample.Payload**. Nếu thay parent bằng application loader (nơi `out` nằm trong classpath) và parent-first delegation thành công, cả hai có thể trả về cùng Class do application loader định nghĩa, khiến kết quả khác.

Không nên tự ý đổi parent trong ví dụ rồi vẫn mong có hai defining loader.

## 7. Danh tính kiểu: binary name + defining loader

Đối với class/interface runtime thông thường, JVMS xác định danh tính bằng cặp:

~~~text
(binary name, defining class loader)
~~~

Ví dụ:

~~~text
("com.example.Plugin", LoaderA) → Class A
("com.example.Plugin", LoaderB) → Class B
("com.example.Plugin", LoaderA) → vẫn Class A nếu đã được define
~~~

Hai class cùng binary name nhưng khác defining loader là **hai kiểu riêng biệt**. Ngược lại, hai initiating loader khác nhau nhưng cùng delegate tới một defining loader có thể sử dụng **chính cùng một Class**.

Điều này ảnh hưởng tới:

- **Ép kiểu (cast)** và toán tử `instanceof`.
- **Chữ ký method/field** chứa tên class của dependency.
- **Reflection** và so sánh `Class`.
- **Runtime package** và kiểm tra quyền truy cập package-private.
- **Nạp plugin** khi host và plugin có các bản thư viện riêng.
- **Serialization, proxy, service loading** và framework dùng reflection khi classpath/classloader bị chia tách.

### 7.1 So sánh Class chứ không chỉ tên String

~~~java
boolean sameName = first.getName().equals(second.getName());
boolean sameRuntimeType = first == second;
ClassLoader firstDefiner = first.getClassLoader();
ClassLoader secondDefiner = second.getClassLoader();
~~~

`sameName` đúng **không kéo theo** `sameRuntimeType` đúng.

Nếu **getClassLoader()** trả null, class thường do bootstrap loader định nghĩa; primitive Class mirrors cũng có cách biểu diễn đặc biệt. Không suy ra rằng một class bị lỗi chỉ vì getClassLoader trả null.

### 7.2 Class loading và runtime package

JVM xác định runtime package của class theo **tên package + defining loader**. Vì vậy hai lớp cùng khai báo `package demo;` nhưng do hai defining loader khác nhau tạo ra có thể thuộc **hai runtime package khác nhau** về kiểm tra quyền truy cập.

Đừng cho rằng cùng dòng `package demo;` trong source code tự cho phép truy cập package-private giữa các class do những loader độc lập định nghĩa. Ở ứng dụng modular, module và các quy tắc truy cập tương ứng cũng cần được xét.

## 8. Một tên lớp, nhiều loader nhưng vẫn một Class: lý do delegation hữu ích

Delegation thường được dùng để chia sẻ các kiểu chung và tránh những phiên bản class trùng không tương thích.

Hình dung một host application có interface chung:

~~~java
package api;

public interface Task {
    void execute();
}
~~~

Host và plugin đều cần **api.Task** có **cùng định nghĩa runtime** để object plugin có thể được sử dụng như Task của host.

Nếu mỗi plugin loader tự định nghĩa một bản `api.Task` riêng, chỉ giống tên và bytecode thôi chưa đủ để phép cast sang `api.Task` của host thành công. Bởi vậy nhiều plugin system chọn để API chung được định nghĩa bởi parent/shared loader, rồi child loader định nghĩa phần implementation của plugin.

~~~text
Shared API loader
   └─ defines api.Task
           ▲
           │ delegated
     +-----+-----+
     |           |
PluginLoader1  PluginLoader2
defines Impl1  defines Impl2

Impl1 / Impl2 đều dùng chung Class api.Task
~~~

Cấu hình thực tế còn phụ thuộc dependency versions, package ownership và chính sách child-first/parent-first. Quy tắc kiến trúc hữu ích là xác định rõ **API nào phải dùng chung một defining loader**, còn implementation nào được phép cô lập.

## 9. Khi nào initiating loader quan trọng hơn một “chi tiết nội bộ”?

Defining loader xác định class identity; initiating loader giúp JVM theo dõi quá trình giải quyết tên lớp một cách nhất quán qua những loader có thể ủy quyền.

### 9.1 Sự nhất quán khi nạp lại cùng binary name

JLS §12.2.2 mô tả tính chất mà những class loader vận hành tốt cần bảo đảm: khi nhận cùng tên, loader nên trả về cùng đối tượng `Class`. Nếu loader từng initiate một class và lại được yêu cầu cùng tên đó, JVM có cơ chế theo dõi để tránh thay thế tùy tiện bằng class không nhất quán.

Đó là lý do loader không được tùy ý “hôm nay trả Class A, ngày mai trả Class B” cho cùng yêu cầu và cùng ngữ cảnh; JVM thực thi những ràng buộc cần thiết bảo vệ hệ kiểu.

### 9.2 Loading constraints

JVM áp đặt **loading constraints** để các loader có cái nhìn tương thích về các kiểu xuất hiện trong quan hệ giữa method/field và những chỗ liên kết tương ứng. Ví dụ, nếu hai class khác defining loader cùng tham gia liên kết method có parameter kiểu `api.Message`, các ràng buộc có thể buộc hai phía thống nhất về danh tính của `api.Message`.

Khi các loader trả về các Class khác nhau cho kiểu buộc phải đồng nhất, linking có thể thất bại bằng **LinkageError** (ví dụ thông báo **loader constraint violation** trên một JVM cụ thể).

Không nên suy ra rằng mọi trường hợp hai loader định nghĩa cùng binary name đều lập tức là lỗi. Ví dụ IsolationDemo vẫn tạo được hai class khác nhau. Lỗi xảy ra khi JVM gặp **những ràng buộc cụ thể** đòi hỏi chúng nhất quán.

### 9.3 Gọi loadClass không phải thao tác introspection đầy đủ về initiating state

Java công khai **Class.getClassLoader()** để xem defining loader, nhưng không cung cấp một API phổ thông trên Class để liệt kê tất cả initiating loader từng liên quan.

**ClassLoader.findLoadedClass(name)** là phương thức protected, kiểm tra lớp đã được JVM ghi nhận là initiated bởi loader đó theo hợp đồng API; không nên diễn giải nó như một cách liệt kê mọi class mà loader trực tiếp define.

Vì các đường đi loading và việc JVM ghi nhận initiating loader có chi tiết đặc tả riêng, hãy dùng **kết quả loadClass, defining loader và class identity** để kiểm chứng các ví dụ; đừng suy đoán toàn bộ trạng thái nội bộ chỉ từ một lời gọi API đơn lẻ.

## 10. Các API liên quan và điều chúng nói lên

| API | Cách dùng phù hợp | Không nên suy ra |
| --- | --- | --- |
| `loader.loadClass(binaryName)` | Yêu cầu loader trả về Class theo tên. | Loader được gọi là defining loader. |
| `clazz.getClassLoader()` | Xem defining loader của class; null có thể là bootstrap. | Danh sách initiating loader. |
| `ClassLoader.getParent()` | Xem parent theo cấu trúc API. | Luôn có delegation parent-first hoặc toàn bộ class đều do parent định nghĩa. |
| `findClass(name)` | Hook thường được custom loader cài đặt để tìm/define class khi delegation không thành. | Mặc định JVM phải gọi hook này cho mọi loadClass. |
| `defineClass(...)` | Tạo class từ binary representation với loader đang define. | Được phép define lại cùng class name trong cùng loader tùy ý. |
| `findLoadedClass(name)` | Kiểm tra class được ghi nhận initiated bởi loader khi gọi trong subclass. | Chỉ phản ánh class do loader trực tiếp define. |
| `Class.forName(name, false, loader)` | Lấy Class theo loader được chỉ định, không chủ động initialization. | Loader tham số chắc chắn là defining loader. |
| `Class.forName(name)` | Tìm class bằng loader của caller thích hợp và yêu cầu initialization. | Chỉ loading mà không chạy static initializer. |

Trong các ví dụ, **Class.getName()** trả binary name của class thông thường, nhưng không đủ để xác định class identity. Thao tác trực tiếp nhất để so hai Class là **a == b**.

**Phân biệt loader của một class và context class loader của thread:** `Thread.currentThread().getContextClassLoader()` là ngữ cảnh cho một số framework/API tra class/service. Nó có thể được đặt thành một loader khác và **không phải** định nghĩa claiming loader của Class bất kỳ. Chỉ dựa trên thread context loader có thể dẫn đến kết luận sai.

## 11. Quan sát loader và class ở runtime

### 11.1 Quan sát bằng Java

Tại điểm cần điều tra một Class:

~~~java
Class<?> c = object.getClass();
System.out.println("name = " + c.getName());
System.out.println("defining loader = " + c.getClassLoader());
System.out.println("module = " + c.getModule());
System.out.println("same expected Class = " + (c == Expected.class));
~~~

Code trên là đoạn minh họa đặt vào method khi có sẵn `object` và `Expected`; nó không phải một class standalone. Thông tin `getModule()` hữu ích khi module và classloader tương tác.

Một số class do bootstrap định nghĩa trả null từ getClassLoader; đừng gọi method trên giá trị ấy mà không kiểm tra null.

### 11.2 Quan sát class loading trên JVM hỗ trợ Unified Logging

Với HotSpot / JDK hiện đại, có thể bật log:

~~~bash
java -Xlog:class+load=info DelegationRolesDemo
~~~

Số dòng và format log phụ thuộc JDK/JVM. Xem tag được hỗ trợ:

~~~bash
java -Xlog:help
~~~

Log loading có thể cho biết nguồn class; nó không phải cơ chế tuyệt đối để suy ra initiating loader list, cũng không chứng minh static initializer đã chạy. Khi cần chứng minh static initialization, tạo một ví dụ có static block in thông báo có kiểm soát như phần 5.

### 11.3 Đọc class file để kiểm tra binary name

Nếu nghi ngờ lớp trong JAR sai package/tên, dùng:

~~~bash
javap -verbose -classpath out sample.Payload
jar --list --file example.jar
~~~

`javap` xem class file/constant pool; `jar --list` kiểm tra archive entries. Hai lệnh này **không cho biết loader runtime nào đã define class** trong ứng dụng đang chạy. Việc tìm thấy `sample/Payload.class` không bảo đảm JVM đã dùng chính bytes đó, vì loader khác có thể tìm bản định nghĩa khác.

## 12. Tình huống lỗi: khi nào cần xem defining loader?

### 12.1 ClassCastException nhưng hai tên đều giống nhau

Ví dụ exception có hai class cùng `com.example.Dto`. Trước khi nghĩ rằng JVM ép kiểu sai, hãy kiểm tra **a.getClassLoader()** và **b.getClassLoader()**. Nếu defining loader khác nhau, đây là hai runtime type; cần làm rõ nơi API shared được định nghĩa và policy delegation của các plugin.

Thường nên đảm bảo DTO/interface dùng để giao tiếp được định nghĩa bởi một shared loader, trong khi code plugin cụ thể có thể cô lập ở child loader.

### 12.2 NoClassDefFoundError hoặc ClassNotFoundException

Nếu custom loader yêu cầu parent tìm class nhưng parent không thấy và child cũng không tìm được, **ClassNotFoundException** có thể phát sinh từ API loadClass. Khi JVM cần một type để resolution, lỗi nạp tương ứng có thể biểu hiện là **NoClassDefFoundError**.

Kiểm tra binary name, nguồn artifact, classpath/module path, parent loader, logic findClass và nguyên nhân gốc trong stack trace. Không giả định ngay rằng loader trong exception chính là defining loader vì có thể việc định nghĩa đã không thành công.

### 12.3 LinkageError: loader constraint violation

Nếu một interface/class cần chia sẻ qua ranh giới loader nhưng hai phía cùng trả về những bản type không tương thích trong chữ ký method, JVM có thể báo lỗi constraint. Cần đối chiếu cấu hình module, phiên bản thư viện, kiểu API truyền qua boundary và loader nào định nghĩa từng loại.

“Class có cùng tên” chỉ là một manh mối; **loader khác nhau không nhất thiết luôn sai**. Trong plugin isolation, đó có thể là thiết kế chủ đích. Lỗi là khi ranh giới cần dùng chung type mà lại không thống nhất class identity.

### 12.4 Đã tạo child loader nhưng class vẫn dùng implementation cũ

Nếu child loader parent-first và parent đã định nghĩa class, child.loadClass có thể trả Class của parent mà không gọi child.findClass. Vì vậy, việc đặt một phiên bản mới của class trong child URL **không bảo đảm** nó được dùng.

Có thể cần điều chỉnh rõ **parent visibility/delegation rules** cho những package được phép isolation. Tránh đổi sang child-first một cách tràn lan, đặc biệt với JDK classes, shared APIs hoặc packages mà VM đòi thống nhất định nghĩa.

## 13. Những trường hợp đặc biệt cần biết

### 13.1 Array classes

JVM tạo array class trực tiếp, không bằng cách tìm một file `[Lsample/Payload;.class` từ classpath. Với array có component là reference type, defining loader của array class gắn với defining loader của component type theo quy tắc JVMS. Với primitive-array class, JVM áp dụng quy tắc bootstrap.

Vì vậy, khi so sánh `Payload[].class` từ hai định nghĩa Payload khác loader, array runtime types cũng khác. Đây không phải hai bản class file của mảng do hai loader đọc được.

### 13.2 Primitive types và void

Các `Class` mirror như `int.class` và `void.class` không tương ứng với một class file thường trên classpath. Không nên diễn giải getClassLoader của primitive giống việc một custom loader đọc bytes của `int.class`.

### 13.3 Modules và custom loaders

Java Platform Module System ảnh hưởng đến nơi class được xác định, khả năng truy cập và module membership. `clazz.getModule()` cung cấp ngữ cảnh hữu ích bên cạnh defining loader. Tuy nhiên, **tên module không thay thế defining loader trong cặp class identity**; module là một chiều bổ sung về organization/accessibility.

### 13.4 Class unloading

Định nghĩa class gắn với defining loader. Việc class có thể được unload phụ thuộc các tham chiếu còn giữ class, loader và những điều kiện JVM khác. Không suy ra rằng class bị unload chỉ vì một initiating loader object không còn được dùng. Đây là phần liên quan đến GC/class lifecycle và nên phân tích theo công cụ đo thực tế khi cần.

## 14. Các hiểu nhầm nên tránh

- **“Bất kỳ loader nào gọi loadClass cũng là defining loader.”** Sai: loader có thể delegate.
- **“Nhiều initiating loader nghĩa là nhiều bản Class.”** Sai: nhiều loader có thể nhận cùng Class từ một defining loader.
- **“getClassLoader() cho biết initiating loader.”** Sai: đây là defining loader hoặc null với bootstrap.
- **“Parent loader luôn được dùng trước.”** Đúng với nhiều implementation mặc định, nhưng custom loader có thể thay đổi delegation.
- **“Tên class giống nhau thì cast được.”** Sai khi defining loader khác nhau.
- **“Bytes giống nhau thì runtime type giống nhau.”** Sai; còn phải giống defining loader và binary name.
- **“Gọi loadClass đã khởi tạo mọi static field.”** Sai; loading và initialization khác nhau.
- **“Tất cả loader nằm giữa trong Java call stack luôn được JVM ghi nhận là initiating.”** Không suy luận được; tham chiếu JVMS về JVM-initiated loading và delegation.
- **“Một field/method API dùng chung hai plugin tự động tương thích vì cùng package.”** Sai nếu shared types bị định nghĩa riêng và vi phạm class identity/loading constraints.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Loader A nhận yêu cầu rồi delegate cho B định nghĩa `pkg.Service`. `Service.class.getClassLoader()` là A hay B?

**Đáp án:** B, defining loader. A có thể đóng vai trò initiating loader trong quá trình JVM yêu cầu nạp qua delegation.

**Câu 2.** Loader A và C cùng delegate tới B cho `pkg.Service`. Có bắt buộc hai Class khác nhau không?

**Đáp án:** Không. Chúng có thể cùng nhận một đối tượng Class do B định nghĩa.

**Câu 3.** Loader A và C mỗi loader trực tiếp define `pkg.Service` bằng cùng bytes. Hai đối tượng Class có bằng nhau không?

**Đáp án:** Không, vì defining loader khác nhau. Class identity gồm binary name và defining loader.

**Câu 4.** Vì sao gọi `child.loadClass(...)` có thể không bao giờ chạy `child.findClass(...)`?

**Đáp án:** Implementation mặc định dùng parent-first delegation. Nếu parent tìm được Class, child trả ngay kết quả ấy.

**Câu 5.** `findLoadedClass` chỉ tìm những class tự define bởi loader đó?

**Đáp án:** Không; hợp đồng API dựa trên các class mà JVM đã ghi nhận loader là initiating loader, có thể gồm class được trả về qua delegation.

**Câu 6.** Đã gọi loadClass thành công, liệu static initializer của class chắc chắn chạy chưa?

**Đáp án:** Chưa. Initialization thường đợi active use riêng; `Class.forName(name)` dạng một tham số có quy tắc khởi tạo khác.

**Câu 7.** Vì sao hai plugin cần dùng chung Class object của một interface giao tiếp?

**Đáp án:** Nếu mỗi plugin định nghĩa riêng interface, runtime type identity khác nhau, dẫn đến lỗi cast hoặc linkage khi API boundary cần thống nhất kiểu.

**Câu 8.** `String.class.getClassLoader()` trả null có nghĩa String không có defining loader?

**Đáp án:** Không. Null biểu thị bootstrap loader theo hợp đồng Class API trong trường hợp này.

## 16. Tóm tắt kiến thức

Để gỡ lỗi classloader, hãy tách ba bước:

~~~text
(1) JVM / chương trình yêu cầu loader nào tìm class?
           |
           v
     initiating loader
           |
           | có thể delegate
           v
(2) Loader nào thực sự định nghĩa class?
           |
           v
      defining loader
           |
           v
(3) Runtime type được xác định bằng:
    (binary name, defining loader)
~~~

**Defining loader** xác định danh tính của class runtime; **initiating loader** thể hiện vai trò khởi xướng loading, có thể thông qua delegation. Nếu chỉ nhớ một quy tắc thực hành: **`loader.loadClass(name)` không chứng minh loader ấy đã define class; hãy xem `Class.getClassLoader()` và so sánh chính các đối tượng `Class`.**

### Tài liệu tham khảo

- **JVMS Java SE 17 §5.3 – Creation and Loading:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS Java SE 17 §5.3.4 – Loading Constraints:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
- **JLS Java SE 17 §12.2.2 – Class Loader Consistency:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2.2
- **ClassLoader API, Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Class API, Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
