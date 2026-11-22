# Bootstrap, platform, application class loader và cơ chế ủy quyền

## 1. Mục tiêu học tập

Một chương trình Java có thể sử dụng hàng nghìn lớp nhưng chúng không nhất thiết được tìm và định nghĩa bởi cùng một thành phần. JVM dùng **class loader** để tạo lớp từ biểu diễn nhị phân, giải quyết tham chiếu và tổ chức không gian tên. Từ Java 9, hệ thống class loader tích hợp thường được giải thích qua ba thành phần: **bootstrap**, **platform** và **application/system**.

Sau bài học, bạn có thể:

- Phân biệt trách nhiệm của ba loader tích hợp, cách lấy chúng qua Java API và vai trò của classpath/module path.
- Đọc chính xác thuật toán ủy quyền **parent-first** thông thường, các hàm **loadClass**, **findLoadedClass**, **findClass**, **defineClass** và **resolveClass**.
- Hiểu **defining loader** so với **initiating loader**, danh tính lớp dựa trên tên nhị phân **và** loader định nghĩa.
- Giải thích tại sao **String.class.getClassLoader()** thường là **null**, nhưng **null** không có nghĩa là không có lớp.
- Phân biệt **loading**, **linking** (verification, preparation, resolution) và **initialization**.
- Nhận biết trường hợp loader tùy biến, context class loader, Java modules, ServiceLoader, nhiều phiên bản dependency và các lỗi thường gặp.
- Thực hành Java 17+ để quan sát loader, chứng minh hai class cùng binary name vẫn khác kiểu khi có hai defining loaders và phân biệt nạp lớp với khởi tạo lớp.

Phạm vi: các quy tắc nền tảng của Java SE 17+ và mô hình JVM; chi tiết tên lớp triển khai loader, đường dẫn, output chẩn đoán có thể khác nhau giữa các JDK.

## 2. Class loader thực hiện điều gì?

**Class loader** là cơ chế đưa định nghĩa lớp/interface đến JVM. Với lớp thông thường, một loader có thể lấy các byte của class từ classpath, module path, JAR, mạng, bộ nhớ hoặc nguồn do ứng dụng cung cấp, rồi dùng cơ chế JVM để định nghĩa lớp.

Phân biệt:

- **Tìm class bytes:** tìm nơi chứa dữ liệu, ví dụ entry **com/example/Order.class** trong JAR.
- **Định nghĩa class (define):** JVM tạo lớp runtime từ dữ liệu class hợp lệ, gắn danh tính lớp với một **defining loader**.
- **Nạp class (load):** lời yêu cầu nạp có thể được một loader giải quyết bằng cách ủy quyền cho loader khác; loader nhận yêu cầu không nhất thiết là loader trực tiếp định nghĩa.
- **Liên kết (link):** thực hiện các công việc xác minh, chuẩn bị và giải quyết tham chiếu theo quy tắc JVM.
- **Khởi tạo (initialize):** chạy công việc khởi tạo lớp, ví dụ static field initializers và static initializer blocks, vào thời điểm được Java quy định.

Vì vậy, câu “loader đã tìm thấy class” không tự động có nghĩa **static initializer đã chạy** hoặc mọi tham chiếu của lớp đã được resolve xong.

Một **Class<?>** là đối tượng đại diện cho một kiểu tại runtime; **Class.getClassLoader()** cung cấp loader đã định nghĩa lớp thông thường đó. Với array class và primitive, API có quy tắc riêng sẽ đề cập bên dưới.

## 3. Ba loader tích hợp trong Java hiện đại

Một mô hình tổng quát cho JDK 17 với hệ thống loader mặc định:

~~~text
                    JVM / Java runtime
                          |
                          v
                  Bootstrap loader
                          ^
                          | delegation
                  Platform loader
                          ^
                          | delegation
             Application / System loader
                          ^
                          | delegation
             Class loader riêng của ứng dụng
~~~

Mũi tên biểu thị đường **ủy quyền thông thường từ loader con lên parent**. Đây là sơ đồ tư duy, không phải lời khẳng định mọi lookup Java modules luôn đi theo một cây cứng nhắc hoặc mọi loader tùy biến đều dùng parent-first.

| Loader | Nhiệm vụ khái quát | API/thông tin quan sát |
| --- | --- | --- |
| **Bootstrap** | Nạp/định nghĩa các lớp lõi mà VM/runtime cung cấp, ví dụ phần lõi **java.base** | Là loader tích hợp trong JVM; với **Class.getClassLoader()**, lớp được bootstrap định nghĩa thường trả **null** |
| **Platform** | Nạp nhiều platform classes/modules Java SE, JDK và thành phần runtime theo phân công của JDK | **ClassLoader.getPlatformClassLoader()** |
| **Application / System** | Loader hệ thống dùng cho ứng dụng trên application classpath, application module path và các phạm vi thích hợp | **ClassLoader.getSystemClassLoader()**; thường là loader của main class trong lệnh chạy classpath thông thường |

Trước Java 9, nhiều tài liệu dùng thuật ngữ **extension class loader**. Từ Java 9, cơ chế extension cũ đã thay đổi và **platform class loader** là khái niệm phù hợp cho JDK 17+. Không thiết kế chương trình Java 17 dựa vào thư mục **jre/lib/ext** như cơ chế hiện hành.

### 3.1. Bootstrap class loader

Bootstrap là thành phần nền tảng được JVM cung cấp, không bắt buộc tồn tại dưới dạng một đối tượng Java **ClassLoader** bình thường. Khi hỏi:

~~~java
String.class.getClassLoader()
~~~

kết quả trên JVM Java SE thông dụng là **null**, mang ý nghĩa lớp **String** do bootstrap định nghĩa.

Điều này **không có nghĩa lớp String không có class loader**; nó có defining loader là bootstrap theo cơ chế JVM. Giá trị **null** là quy ước ở Java API cho loader bootstrap trong những trường hợp tương ứng.

Bootstrap không có parent. Những lớp thiết yếu như **java.lang.Object**, **java.lang.String** thường do bootstrap định nghĩa. Không nên khẳng định mọi lớp bắt đầu bằng **java.** đều do bootstrap định nghĩa: nhiều loại platform classes được phân công cho loader khác.

### 3.2. Platform class loader

Platform loader chịu trách nhiệm về nhiều lớp nền tảng Java/JDK không thuộc tập do bootstrap định nghĩa. Java cung cấp:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
~~~

Bạn có thể dùng platform loader làm parent của custom class loader khi chỉ muốn custom loader có phạm vi kế thừa class nền tảng mà không mặc nhiên được nhìn thấy các class ứng dụng.

**Ngoại lệ quan trọng đối với sơ đồ cây:** từ Java 9, module system ảnh hưởng khả năng nhìn thấy lớp. Tài liệu ClassLoader Java 17 ghi rõ platform loader **có thể phải ủy quyền tới loader khác, ví dụ application loader**, để xử lý các mô-đun được nâng cấp/ghi đè mà modules tương ứng có quan hệ đọc. Vì thế không nên tuyên bố “platform loader tuyệt đối không thể nhìn thấy lớp của application loader trong mọi trường hợp”.

### 3.3. Application/system class loader

Application loader còn được gọi là **system class loader**:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

Trong cách chạy điển hình:

~~~bash
java -cp out com.example.Main
~~~

main class trong **out** thường được định nghĩa bởi system loader mặc định. Loader này nhìn thấy các lớp ứng dụng theo classpath/module configuration và có thể ủy quyền để sử dụng các lớp nền tảng.

Trong JDK hiện đại, implementation class của system loader là chi tiết nội bộ. **Không cast system loader thành URLClassLoader** và không giả định nó luôn có hàm **addURL** hoặc cấu trúc URL classpath giống JDK 8. Nếu Java được chạy với cấu hình system loader tùy biến, một số phép so sánh phụ thuộc môi trường có thể khác.

**Đường kế thừa:** theo API, platform loader là **parent hoặc ancestor** của system loader. Với hệ mặc định thường trực tiếp là parent; các system class loader tùy biến có thể thêm tầng trung gian.

## 4. Parent không phải quan hệ kế thừa lớp Java

Trong:

~~~java
ClassLoader child = new ClassLoader(parent) {};
~~~

**parent** là loader để **ủy quyền tìm lớp**. Nó không có nghĩa child có quan hệ **extends parent.getClass()** hay child tự động sao chép toàn bộ những class đã được parent định nghĩa.

Cần phân biệt ba quan hệ:

| Quan hệ | Câu hỏi |
| --- | --- |
| **ClassLoader parent** | Khi loader này được yêu cầu một class, nó có thể hỏi loader nào trước? |
| **Class extends/interface implements** | Một kiểu Java kế thừa/hiện thực kiểu nào? |
| **Module reads/exports/opens** | Một module được phép tham chiếu/truy cập các package/class nào? |

Ba quan hệ tương tác nhưng không thay thế cho nhau. Parent delegation không tự mở quyền reflective access đến package bị module đóng; việc một class nạp thành công cũng không làm mọi thành viên của nó trở nên truy cập được.

## 5. Thuật toán ủy quyền parent-first thông thường

Cài đặt mặc định của **ClassLoader.loadClass(String, boolean)**, khi không bị override, hoạt động theo tinh thần:

~~~text
loadClass(binaryName, resolve)
    |
    v
1. findLoadedClass(binaryName)
   Đã được loader này ghi nhận là nạp? -> sử dụng lại
    |
    v chưa tìm thấy
2. Hỏi parent.loadClass(binaryName)
   Nếu parent == null: thử bootstrap loader của JVM
    |
    +-- thành công -> dùng class do parent/bootstrap cung cấp
    |
    v không tìm được
3. Gọi findClass(binaryName) của chính loader
    |
    +-- tìm được bytes / định nghĩa class -> trả Class
    |
    v không tìm được
4. Ném ClassNotFoundException
    |
    v nếu tìm được class
5. Nếu resolve=true: resolveClass(theClass)
6. Trả Class<?>
~~~

Điểm cần nhớ:

- **findLoadedClass** dùng để tránh định nghĩa trùng một class trong cùng loader.
- **Parent-first** nghĩa là ưu tiên hỏi parent rồi mới đến **findClass** của con. Nó giúp lớp lõi Java và các dependency chung được chia sẻ nhất quán.
- **findClass** là hook thích hợp khi viết loader tùy biến vẫn giữ cơ chế ủy quyền mặc định.
- **defineClass(name, bytes, off, len)** thực sự đưa định nghĩa mới đến JVM, nếu dữ liệu hợp lệ.
- **resolveClass** liên quan tới bước linking; nó **không đồng nghĩa khởi tạo static fields**.
- **ClassNotFoundException** là kết quả khi một yêu cầu nạp lớp theo tên không tìm thấy định nghĩa phù hợp; lỗi linkage có thể xảy ra ở giai đoạn khác.

Thuật toán trên là cài đặt mặc định của **ClassLoader**, không phải hợp đồng bắt buộc mọi loader custom phải dùng đúng thứ tự. Loader có thể override **loadClass** để dùng **child-first** hoặc cơ chế module-specific, nhưng phải tôn trọng ràng buộc của JVM về danh tính lớp, kiểu, quyền và tính nhất quán.

### 5.1. Ví dụ parent-first tránh một bản sao lớp lõi

Giả sử application loader được yêu cầu **java.lang.String**:

~~~text
Application loader -> Platform loader -> Bootstrap loader
                                     -> định nghĩa java.lang.String
                 <- trả về cùng Class
        <- trả về cùng Class
~~~

Các loader con **có thể initiate loading** bằng ủy quyền; class runtime được bootstrap định nghĩa. Mặc định, application loader không tạo bản sao tùy ý của **java.lang.String**.

Custom loader không nên cố định nghĩa các lớp thuộc **java.*** bằng **defineClass**; Java API đặt ràng buộc an ninh với tên package này, bên cạnh các điều kiện về module, package và class file.

### 5.2. Mẫu code override findClass

Mã sau chỉ minh họa cấu trúc **findClass**; không phải chương trình độc lập vì phần lấy dữ liệu byte chưa được cung cấp:

~~~java
class ResourceClassLoader extends ClassLoader {
    ResourceClassLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String binaryName)
            throws ClassNotFoundException {
        byte[] bytes = readClassBytes(binaryName);
        if (bytes == null) {
            throw new ClassNotFoundException(binaryName);
        }
        return defineClass(binaryName, bytes, 0, bytes.length);
    }

    private byte[] readClassBytes(String binaryName) {
        // Cơ chế lấy class bytes từ một nguồn riêng sẽ được cài đặt ở đây.
        return null;
    }
}
~~~

Vì mẫu này trả null nên nó **chưa thực sự tải được class mới**; nó chỉ cho thấy nơi cài đặt logic. Ví dụ chạy được ở mục 9 sẽ thực hiện việc định nghĩa từ mảng byte hoàn chỉnh, không cần cơ chế tải dữ liệu ngoài.

Lưu ý **binaryName** ở API **loadClass/findClass** thường có dạng **com.example.MyType**, không phải **com/example/MyType**. Khi tìm entry trong JAR, loader tự chuyển thành đường dẫn **com/example/MyType.class** nếu cơ chế nguồn của nó cần như vậy.

## 6. Defining loader, initiating loader và danh tính lớp

Khi loader A nhận yêu cầu nạp **com.example.Service** rồi ủy quyền thành công cho loader B, cần gọi đúng tên:

- **B là defining loader** nếu B thực sự định nghĩa class từ bytes.
- **A là initiating loader** theo quá trình nạp mà JVM ghi nhận, dù A không trực tiếp định nghĩa.
- Class runtime đó có **danh tính gắn với binary name và defining loader**.

Về mặt khái niệm, một class/runtime interface được định danh bằng cặp:

~~~text
(binary name, defining loader)
~~~

Do đó, hai lớp **plugin.Task** do hai loader khác nhau trực tiếp định nghĩa là **hai kiểu runtime khác nhau**, mặc dù:

- cùng binary name **plugin.Task**;
- cùng class bytes;
- cùng method signatures;
- cùng superclass **java.lang.Object**.

Với hai kiểu này:

~~~text
("plugin.Task", LoaderA) != ("plugin.Task", LoaderB)
~~~

**Class<?>** không bằng nhau; instance của lớp từ LoaderA không tự được cast thành kiểu từ LoaderB. Các bài toán plugin isolation, application server redeployment và nhiều phiên bản thư viện cần hiểu đúng tính chất này.

### 6.1. Điều gì xảy ra khi loader con chỉ ủy quyền?

Nếu cả **LoaderA** và **LoaderB** đều parent-first đến cùng parent đã định nghĩa **shared.Api**, hai yêu cầu có thể trả **cùng một Class object** của **shared.Api**. **LoaderA != LoaderB** không bắt buộc class cuối cùng phải khác nhau: cần kiểm tra **ai thực sự định nghĩa lớp**.

### 6.2. Runtime package cũng xét loader

Không đủ để hai lớp có cùng chuỗi package **com.example**. JVM xem runtime package dựa trên **package name và defining loader** (cùng các quy định module liên quan). Hai class cùng package name nhưng đến từ các defining loaders khác nhau **không tự được quyền truy cập package-private** của nhau.

Điều này lý giải những lỗi IllegalAccessError khó hiểu khi class sinh bằng bytecode cùng package string với class gốc nhưng được định nghĩa bởi loader khác.

### 6.3. Loading constraints khi giao tiếp giữa loaders

Các phương thức/field có descriptor tham chiếu kiểu được định nghĩa bởi loader khác nhau có thể chịu **loading constraints** để bảo đảm type safety khi linking. Không thể chỉ tạo hai class có cùng binary name rồi cho hệ thống coi chúng là một kiểu khi truyền object qua ranh giới loader.

Các giải pháp thực tế gồm: đưa API dùng chung lên loader cha, truyền dữ liệu qua format ổn định hoặc dùng interface mà cả hai phía nhìn thấy **cùng Class object** của interface đó.

## 7. Phân biệt loading, linking và initialization

Sơ đồ vòng đời rút gọn:

~~~text
Nguồn class bytes
      |
      v
Loading / define class
      |
      v
Linking
  +--> Verification: class file/bytecode và ràng buộc kiểu
  +--> Preparation: chuẩn bị static fields với giá trị mặc định thích hợp
  +--> Resolution: giải quyết các symbolic references (có thể lazy)
      |
      v
Initialization
  +--> static initializers và static field initializers của lớp
      |
      v
Lớp sẵn sàng cho các cách sử dụng cần khởi tạo
~~~

Quá trình chuẩn bị và giải quyết có các quy tắc thứ tự và có thể xảy ra từng phần. **Resolution** không nhất thiết được thực hiện đồng loạt cho tất cả tham chiếu ngay khi gọi loadClass. Không đồng nhất linking với chạy constructor đối tượng.

Ví dụ các hành động thường có tác dụng khác nhau:

| Hành động | Có bắt buộc khởi tạo lớp mục tiêu ngay không? |
| --- | --- |
| **loader.loadClass("demo.Widget")** | Thông thường **không**; mặc định tương đương loadClass(name, false) |
| **Class.forName("demo.Widget", false, loader)** | **Không yêu cầu initialization** |
| **Class.forName("demo.Widget")** | Có yêu cầu load/link và **initialize** theo contract overload một tham số |
| **Class.forName("demo.Widget", true, loader)** | Yêu cầu initialization |
| **new Widget()** | Là active use, cần lớp được khởi tạo theo quy tắc |
| Truy cập static field/method không phải ngoại lệ constant variables | Có thể kích hoạt initialization theo quy tắc JLS/JVMS |
| Tham chiếu **Widget.class** | Không tự khởi tạo Widget chỉ vì lấy class literal |

Không xem **Class.forName** như một API “chỉ kiểm tra tên” mà quên tham số **initialize**. Việc khởi tạo có thể chạy static code với side effects và lỗi.

## 8. Ví dụ runnable 1: quan sát ba loader

Tạo tệp **LoaderBasics.java**:

~~~java
public class LoaderBasics {
    public static void main(String[] args) throws ClassNotFoundException {
        ClassLoader app = LoaderBasics.class.getClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        System.out.println("mainIsSystem=" + (app == system));
        System.out.println("platformIsDifferent=" + (platform != system));
        System.out.println("stringBootstrap="
                + (String.class.getClassLoader() == null));
        System.out.println("primitiveArrayBootstrap="
                + (int[].class.getClassLoader() == null));
        System.out.println("ownArrayUsesApp="
                + (LoaderBasics[].class.getClassLoader() == app));
        System.out.println("forNameIsString="
                + (Class.forName("java.lang.String", false, app)
                        == String.class));
    }
}
~~~

Với JDK 17 và system loader mặc định, thực hiện trong thư mục chứa tệp:

~~~bash
javac --release 17 -encoding UTF-8 LoaderBasics.java
java -cp . LoaderBasics
~~~

**Stdout trong môi trường Java 17 điển hình dùng system loader mặc định:**

~~~text
mainIsSystem=true
platformIsDifferent=true
stringBootstrap=true
primitiveArrayBootstrap=true
ownArrayUsesApp=true
forNameIsString=true
~~~

Diễn giải:

1. Main class trên application classpath do system loader mặc định định nghĩa.
2. Platform loader là thành phần riêng so với system loader.
3. **String** là lớp lõi được bootstrap định nghĩa và biểu diễn loader bằng null.
4. **int[]** được JVM tạo cho primitive array, nên **getClassLoader()** cũng trả null.
5. Array class có component reference type do app loader định nghĩa có loader tương ứng với component.
6. **Class.forName** được yêu cầu tìm String qua app loader; nhờ ủy quyền nó nhận đúng cùng Class object **String.class** do bootstrap cung cấp.

Nếu chạy trong application server hoặc cấu hình system loader tùy biến, dòng **mainIsSystem** có thể khác. Bài thực hành giả định đúng lệnh **java -cp . LoaderBasics** không dùng custom launcher.

### 8.1. Tại sao array cũng cần quy tắc riêng?

Array classes được tạo bởi JVM khi cần, không phải bằng cách đọc tệp **[L...;.class** thông thường. **Class.getClassLoader()** của reference array bằng loader của component reference type; primitive array có loader biểu diễn bằng null.

Ví dụ:

~~~java
// Mã minh họa trong một phương thức:
ClassLoader a = String[].class.getClassLoader();   // Thông thường null
ClassLoader b = LoaderBasics[].class.getClassLoader(); // Loader của LoaderBasics
ClassLoader c = int[][].class.getClassLoader();     // null
~~~

Không suy từ tên array trông như descriptor rằng file JAR chứa entry có tên **[Ljava/lang/String;.class**.

## 9. Ví dụ runnable 2: cùng tên, hai defining loaders, hai kiểu khác nhau

Bài này dùng **hai tệp Java độc lập** và hai instance của một custom class loader. Nó minh họa class identity mà không phụ thuộc plugin framework.

Cấu trúc thư mục:

~~~text
workspace/
  ClassIdentityDemo.java
  plugin/
    Task.java
  out/                     (tạo trước khi biên dịch)
~~~

Tệp **plugin/Task.java**:

~~~java
package plugin;

public final class Task {
    public int run() {
        return 7;
    }
}
~~~

Tệp **ClassIdentityDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class ClassIdentityDemo {
    static final class ByteArrayLoader extends ClassLoader {
        private final byte[] bytecode;

        ByteArrayLoader(byte[] bytecode) {
            super((ClassLoader) null); // Ủy quyền chỉ tới bootstrap
            this.bytecode = bytecode.clone();
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("plugin.Task")) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytecode, 0, bytecode.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("out", "plugin", "Task.class"));

        ClassLoader first = new ByteArrayLoader(bytes);
        ClassLoader second = new ByteArrayLoader(bytes);

        Class<?> one = Class.forName("plugin.Task", false, first);
        Class<?> two = Class.forName("plugin.Task", false, second);

        System.out.println("sameName="
                + one.getName().equals(two.getName()));
        System.out.println("sameClass=" + (one == two));
        System.out.println("sameLoader="
                + (one.getClassLoader() == two.getClassLoader()));
        System.out.println("eachOwns="
                + (one.getClassLoader() == first
                        && two.getClassLoader() == second));
        System.out.println("assignable="
                + one.isAssignableFrom(two));
        System.out.println("sharedObject="
                + (one.getSuperclass() == two.getSuperclass()));
    }
}
~~~

Từ thư mục **workspace**, với **out** đã tồn tại (nếu chưa, tạo thư mục):

~~~bash
mkdir out
javac --release 17 -encoding UTF-8 -d out plugin/Task.java ClassIdentityDemo.java
java -cp out ClassIdentityDemo
~~~

Nếu **out** đã tồn tại, bỏ qua lệnh **mkdir out**. **Stdout**:

~~~text
sameName=true
sameClass=false
sameLoader=false
eachOwns=true
assignable=false
sharedObject=true
~~~

Lý do:

- **first** và **second** đều nhận cùng byte array từ **Task.class**, nhưng là **hai ClassLoader instances độc lập**.
- Mỗi loader có parent null theo quy ước ủy quyền tới bootstrap; bootstrap không cung cấp **plugin.Task**. Sau khi parent không tìm thấy lớp, **findClass** của từng loader định nghĩa một bản riêng.
- Hai lớp mang cùng **binary name = plugin.Task** nên **sameName=true**.
- **Defining loader** khác nhau khiến **Class object** khác nhau, nên **sameClass=false**, **assignable=false**.
- Cả hai lớp mặc định kế thừa cùng **java.lang.Object** được bootstrap định nghĩa, nên superclass Class object của chúng là một: **sharedObject=true**.

Chương trình không truyền instance giữa hai lớp này; nếu thử cast instance từ loại một sang loại hai, Java sẽ từ chối theo kiểm tra kiểu runtime.

**Giới hạn ví dụ:** Loader chỉ phục vụ đúng tên **plugin.Task**, và Task không có dependency plugin tùy chỉnh. Trong hệ thống thật cần quản lý nhiều class, resources, package sealing, module, native library, bảo mật dữ liệu đầu vào, concurrency và vòng đời loader. Dùng cùng tên class từ nguồn không tin cậy với **defineClass** cần ranh giới bảo mật rõ ràng.

### 9.1. Vì sao không dùng parent=system trong ví dụ này?

Nếu loader có parent là system loader, và system đã thấy **plugin.Task** trên classpath **out**, thuật toán parent-first mặc định sẽ hỏi system trước, rồi cả hai loader con có thể nhận **cùng lớp do system định nghĩa**. Khi đó ví dụ không còn chứng minh hai defining loaders khác nhau. Đặt parent null là quyết định có chủ đích để cô lập lớp **plugin.Task** trong thí nghiệm.

Trong ứng dụng thật, thường nên dùng parent chia sẻ các API chung (ít nhất platform loader hoặc một API loader riêng), thay vì giả định bootstrap parent thích hợp cho mọi plugin.

## 10. Ví dụ runnable 3: loading không tự chạy static initializer

Tạo tệp **InitializationDemo.java**:

~~~java
public class InitializationDemo {
    static class Target {
        static {
            System.out.println("init:Target");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = InitializationDemo.class.getClassLoader();

        Class<?> type =
                Class.forName("InitializationDemo$Target", false, loader);
        System.out.println("loaded=" + (type == Target.class));

        Class.forName("InitializationDemo$Target", true, loader);
        System.out.println("initialized");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 InitializationDemo.java
java InitializationDemo
~~~

**Stdout:**

~~~text
loaded=true
init:Target
initialized
~~~

**Tại sao:** Lệnh **Class.forName(..., false, loader)** cung cấp **Class object** nhưng không yêu cầu khởi tạo Target. Tham chiếu **Target.class** chỉ lấy class literal, không kích hoạt static initializer. Lệnh **Class.forName(..., true, loader)** sau đó yêu cầu initialization và in **init:Target** một lần; cuối cùng main in **initialized**.

Nếu Target từng được khởi tạo trước đó trong cùng JVM, static block không tự chạy lại. Trong chương trình độc lập này, nó chưa từng được khởi tạo trước bước gọi với **true**.

## 11. Context class loader: vì sao có loader “ngữ cảnh”?

**Thread context class loader (TCCL)** là một tham chiếu loader gắn với thread:

~~~java
ClassLoader context = Thread.currentThread().getContextClassLoader();
Thread.currentThread().setContextClassLoader(context);
~~~

Nó **khác về khái niệm** so với parent loader hoặc defining loader của một class:

| Loại | Được xác định bởi | Công dụng |
| --- | --- | --- |
| Defining loader của class | Loader thực sự định nghĩa class | Danh tính của kiểu runtime |
| Parent của loader | Cấu hình ủy quyền loader | Nơi hỏi trước để tìm class/resource |
| Context loader của thread | Trạng thái ngữ cảnh do thread/framework đặt | Giúp thư viện hạ tầng tìm provider/component trong phạm vi ứng dụng gọi nó |

Một thư viện dùng chung được nạp bởi bootstrap/platform có thể cần tìm extension được đóng gói trong ứng dụng. Nếu chỉ dùng loader định nghĩa thư viện, nó không nhất thiết thấy provider trong application classpath. TCCL cung cấp một cách truyền phạm vi lookup đến thư viện theo convention.

Ví dụ **ServiceLoader.load(MyService.class)** (overload nhận service class) theo Java API thường sử dụng context class loader của thread để tìm providers. Một số framework, JDBC, logging, SPI và application server dùng TCCL hoặc cơ chế lookup tương tự.

**Không được nhầm:** đặt context loader mới bằng **setContextClassLoader** không thay defining loader của những lớp đã nạp, và không thay đổi parent chain của system loader.

### 11.1. Thiết lập TCCL đúng vòng đời

Một pattern hữu ích khi tạm đổi ngữ cảnh:

~~~java
// Mã minh họa bên trong một phương thức:
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Thực hiện lời gọi framework/SPI cần pluginLoader.
} finally {
    thread.setContextClassLoader(old);
}
~~~

Đây là đoạn minh họa, với **pluginLoader** được cung cấp từ bên ngoài. Khôi phục loader cũ trong **finally** để tránh rò rỉ ngữ cảnh sang tác vụ kế tiếp của cùng thread, nhất là trong thread pool.

## 12. Java Platform Module System làm sơ đồ nạp lớp tinh tế hơn

Từ Java 9, JDK dùng module system. **Module path** và **classpath** có tính chất khác nhau:

- Classpath thường chứa các class thuộc **unnamed module** của loader tương ứng.
- Module path cho phép runtime giải quyết **named modules** theo mô tả module, exports, reads và các cấu hình module.
- Một module có thể do bootstrap, platform hoặc application loader định nghĩa tùy JDK/module graph.
- Loader có thể tìm lớp dựa vào mapping module/package, và một số yêu cầu lookup có thể đi tới loader khác do module readability/configuration.

Một ví dụ đơn giản:

~~~bash
java -cp out com.example.Main
~~~

Đây là cách gọi main class qua classpath; khác với lệnh khởi chạy modular application bằng:

~~~bash
java --module-path mods --module com.example.app/com.example.Main
~~~

Dòng modular là **cú pháp minh họa**, yêu cầu thực tế phải có module descriptor hợp lệ và artifact trong **mods**. Đừng giả định chỉ đổi **-cp** thành **--module-path** là đủ.

**Module encapsulation** cũng là lớp kiểm soát riêng: dù một loader tìm được class, reflective access vào thành viên không được mở vẫn có thể bị từ chối, ví dụ **InaccessibleObjectException** trong các tình huống phù hợp.

### 12.1. Tránh các giả định JDK 8 đã lỗi thời

- **Extension class loader** không còn là tên chính thức của tầng hiện hành trong JDK 17.
- **rt.jar** và mô hình JRE/extension directory cũ không còn là cách chắc chắn để xác định nguồn lớp Java SE.
- Built-in app loader không bắt buộc là **URLClassLoader**.
- Không dựa vào tên triển khai nội bộ như **jdk.internal.loader.ClassLoaders$AppClassLoader** để viết cast hoặc API production.

Dựa vào **ClassLoader.getPlatformClassLoader()**, **getSystemClassLoader()**, **getParent()**, **getResource(...)** và contracts công khai khi thiết kế code.

## 13. Custom loader và child-first: khi nào có ích, khi nào có rủi ro?

**Parent-first** hữu ích để chia sẻ các lớp nền tảng và API ổn định. Tuy nhiên plugin isolation hoặc các container có thể cố ý dùng **child-first** cho một tập package riêng, để hai module chạy các phiên bản thư viện khác nhau.

Một chính sách khả thi theo từng package:

~~~text
Yêu cầu nạp java.*, javax.* hoặc API chung:
  ủy quyền parent trước

Yêu cầu nạp plugin.internal.*:
  ưu tiên bản trong plugin

Các class khác:
  ủy quyền/lookup theo chính sách loader
~~~

Đây là mô tả ý tưởng, **không phải một thuật toán chuẩn áp dụng cho mọi plugin system**. Các rủi ro:

1. **Class identity conflict:** lớp API chung bị định nghĩa hai lần nên cast, MethodHandle hoặc reflection không còn khớp.
2. **LinkageError/loader constraint violation:** descriptors giữa các loader đòi cùng kiểu nhưng lại ánh xạ tới các class khác nhau.
3. **Package-private access sai:** hai class có cùng tên package nhưng khác loader không nằm trong cùng runtime package.
4. **Deadlock trong loading:** các loader khóa theo thứ tự không phù hợp khi nhiều thread nạp các lớp phụ thuộc lẫn nhau.
5. **Resource/service discovery lệch:** class được tìm từ một loader, resource/provider lại được tìm qua loader khác.
6. **Giới hạn module/bảo mật:** class có mặt không có nghĩa mọi package đều mở hoặc có thể define tùy ý.
7. **Rò rỉ loader:** thread, ThreadLocal, static caches, timers, MBean, callback hay registry giữ strong reference đến Class/ClassLoader khiến plugin không được giải phóng.

Khi cần loader tùy biến, nên giữ **API/interface chung** trong một parent ổn định, ưu tiên tái dùng thư viện tiêu chuẩn và framework đã xử lý resource/module/class identity, chỉ override **loadClass** khi chính sách thực sự cần thay đổi.

### 13.1. Đồng thời và việc định nghĩa lặp

**ClassLoader.loadClass** mặc định dùng cơ chế khóa **getClassLoadingLock(name)**, kèm bước **findLoadedClass**. Khi viết loader tùy biến, phải tránh hai thread cùng định nghĩa một binary name trong cùng loader; điều đó có thể gây lỗi linkage.

Class loader muốn nạp song song các tên khác nhau có thể đăng ký **parallel-capable** theo quy tắc Java API. Việc đăng ký có yêu cầu thực hiện trong giai đoạn khởi tạo lớp loader và cách phối hợp lớp cha; không đủ chỉ thêm synchronized ở vài chỗ là mọi chính sách song song đều đúng.

## 14. Classpath, resource lookup và delegation

Class loader cũng tìm **resources**. Tên resource thường là đường dẫn dạng **/**, ví dụ:

~~~text
config/defaults.properties
images/logo.png
META-INF/services/com.example.MyService
~~~

Trong khi tên binary class thường dùng dấu chấm:

~~~text
com.example.MyService
~~~

Sự khác biệt này dẫn đến lỗi phổ biến khi gọi:

~~~java
// Minh họa trong phương thức:
ClassLoader loader = Thread.currentThread().getContextClassLoader();
var resource = loader.getResource("config/defaults.properties");
~~~

Nếu gọi **getResource("com.example.MyService")** để tìm tệp class theo mặc định, bạn đang dùng sai định dạng tên resource. Với class file, resource path thường sẽ là **com/example/MyService.class**.

**Resource delegation** thường đi qua parent, nhưng có các quy tắc resource lookup riêng và Java modules có encapsulation. Không nên kết luận từ việc **getResource(...) == null** rằng lớp Java chắc chắn không thể được nạp trong mọi tình huống; có thể class được tạo từ bytes động, package chưa được mở, path khác hoặc loader khác.

## 15. Chẩn đoán các lỗi class loader hay gặp

| Triệu chứng/lỗi | Ý nghĩa thường gặp | Cần kiểm tra |
| --- | --- | --- |
| **ClassNotFoundException** | Một yêu cầu tìm class bằng tên không tìm được | Binary name, caller loader, classpath/module path, custom findClass, TCCL |
| **NoClassDefFoundError** | JVM cần một class khi linkage/use nhưng không lấy được định nghĩa cần thiết; cũng có thể xuất hiện sau lỗi khởi tạo | Root cause, dependency, class bytes, initialization failure trước đó |
| **ExceptionInInitializerError** | Một static initializer thất bại và lỗi được bọc theo quy tắc | Exception gốc trong static initializer |
| **ClassCastException** dù tên lớp giống nhau | Hai Class objects khác defining loader hoặc interface/version không khớp | In binary name và **getClassLoader()** của cả hai bên |
| **LinkageError** (các dạng khác nhau) | Vi phạm ràng buộc liên kết/định nghĩa, ví dụ duplicate definition hay loader constraints | Loader nào define, descriptors, class versions và log load |
| **IllegalAccessError** | Quy tắc truy cập JVM bị vi phạm khi linking/runtime | Runtime package, defining loader, module access |
| **InaccessibleObjectException** | Reflective access bị module encapsulation chặn | Opens/exports, module graph, tránh reflection vào API nội bộ |
| **ServiceConfigurationError** | Provider SPI không tìm được/tạo được/không assignable | TCCL, META-INF/services, provider module, type identity |
| Plugin không unload được | Tham chiếu mạnh vẫn giữ loader, class hoặc thread của plugin | ThreadLocals, executors, caches, callbacks, service registries |

Một lỗi hiển thị **ClassNotFoundException: com.example.Foo** không đủ chứng minh file Foo.class thiếu khỏi toàn bộ máy: có thể class ở một loader khác không nằm trong đường delegation, hoặc tên module/cấu hình path khác.

### 15.1. Hướng điều tra từng bước

1. Xác định **class nào đang được yêu cầu** và binary name chính xác.
2. Xác định **điểm phát sinh yêu cầu**: reflection, application main, framework, ServiceLoader, loader tùy biến.
3. In **Class.getClassLoader()** của lớp đã nạp liên quan và đường parent bằng **getParent()**; lưu ý bootstrap thường hiển thị null.
4. Kiểm tra **ClassLoader.getSystemClassLoader()**, **getPlatformClassLoader()** và TCCL của thread hiện hành khi có SPI/plugin.
5. Kiểm tra classpath/module path thực sự của tiến trình, dependency version và JAR entries.
6. Với custom loader, xem thứ tự **findLoadedClass → parent → findClass**, đồng bộ hóa, và liệu loader có define trùng một tên hay không.
7. Với lỗi cast/linkage, so sánh **Class object identity** và defining loader, không chỉ so tên kiểu.
8. Với lỗi khởi tạo, tìm exception gốc trong static initializer trước khi đổi classpath.
9. Nếu dùng JPMS, kiểm tra reads, exports, opens và package thuộc module nào.
10. Sửa đúng ranh giới; chạy lại integration test trên đúng cách khởi động ứng dụng.

### 15.2. Công cụ quan sát

Với HotSpot/JDK 17 có thể sử dụng:

~~~bash
java -Xlog:class+load=info -cp . LoaderBasics
~~~

Tùy cấu hình, thông tin nạp lớp được ghi vào log, có thể gồm nhiều dòng ở output streams; **không** dùng tổng output của lệnh này làm stdout chuẩn của ví dụ vì nó phụ thuộc runtime.

Một tùy chọn tương thích trong nhiều phiên bản Java là:

~~~bash
java -verbose:class -cp . LoaderBasics
~~~

Với tiến trình đang chạy và **jcmd** được hỗ trợ, có thể xem danh sách diagnostic commands:

~~~bash
jcmd <PID> help
~~~

Rồi dùng các lệnh về class loader như **VM.classloaders** hoặc thống kê loader nếu có trong JVM cụ thể. Chuỗi **<PID>** là placeholder của lệnh terminal, không phải ký tự nên gõ nguyên văn; thay bằng PID của tiến trình thực. Cần quyền phù hợp để attach/chẩn đoán.

Khi log ghi một class “được load từ nơi X”, đừng chỉ nhìn nguồn JAR để kết luận class identity; hai loaders vẫn có thể đọc cùng JAR mà định nghĩa hai class khác nhau.

## 16. Bài tập tự kiểm tra

**Câu 1.** Trong JDK 17 mặc định, **String.class.getClassLoader()** thường trả giá trị gì? Có phải String không được nạp?

**Đáp án:** Trả **null**, đại diện bootstrap loader. String vẫn là class runtime đã được JVM nạp/định nghĩa.

**Câu 2.** Application loader gọi **loadClass("java.lang.String")**, rồi parent/bootstrap tìm được class. Ai là defining loader?

**Đáp án:** Bootstrap; application loader có thể là initiating loader theo yêu cầu, nhưng không tạo định nghĩa mới cho String.

**Câu 3.** Hai loader custom riêng cùng define **com.example.Widget** từ cùng class bytes. Hai class runtime bằng nhau không?

**Đáp án:** Không. Danh tính class là cặp **(binary name, defining loader)**; nếu defining loader khác, Class objects khác.

**Câu 4.** Nếu hai loader child khác nhau đều delegate tới cùng parent đã define **shared.Api**, hai kết quả có thể là cùng Class object không?

**Đáp án:** Có. Parent-first trả định nghĩa từ parent; child không tự động define bản sao.

**Câu 5.** Thứ tự mặc định trong **ClassLoader.loadClass(name, resolve)** là gì?

**Đáp án:** Kiểm tra **findLoadedClass**, ủy quyền parent/bootstrap, nếu không tìm được thì **findClass** của chính loader; khi cần có bước **resolveClass**. Nếu không tìm được thì báo **ClassNotFoundException**.

**Câu 6.** **loadClass** có bắt buộc chạy static initializer ngay không?

**Đáp án:** Không. Nạp lớp và initialization là hai giai đoạn khác; **Class.forName(name, true, loader)** chủ động yêu cầu initialization.

**Câu 7.** Thay TCCL có khiến một class đã do system loader định nghĩa được “chuyển” sang plugin loader không?

**Đáp án:** Không. TCCL thay ngữ cảnh lookup cho những API/framework sử dụng nó, không thay defining loader của class đã tạo.

**Câu 8.** Vì sao ServiceLoader có thể không tìm thấy provider dù JAR có trên hệ thống?

**Đáp án:** Tùy overload và môi trường, nó có thể đang dùng TCCL hoặc module/configuration khác, provider không nằm trong phạm vi loader được dùng, thiếu metadata hoặc provider không tương thích kiểu API chung.

**Câu 9.** Khi thấy **ClassCastException** với hai tên kiểu giống nhau, nên kiểm tra những gì?

**Đáp án:** So sánh chính **Class objects**, defining loaders, loader parent paths và các bản sao dependency/API. Cùng tên binary không đủ chứng minh cùng kiểu runtime.

**Câu 10.** Platform loader có tuyệt đối không thể delegate sang application loader trên JDK 17 không?

**Đáp án:** Không. Tài liệu Java 17 lưu ý những trường hợp module visibility/upgrading có thể khiến platform loader delegate sang loader khác, kể cả application loader.

**Câu 11.** Array class của kiểu primitive có tên dạng **[I** có file **[I.class** để loader đọc hay không?

**Đáp án:** Không theo mô hình Java class file thông thường. JVM tạo array class theo nhu cầu; primitive array có loader hiển thị **null**. Reference array dùng defining loader của component reference type khi hỏi Class.getClassLoader().

**Câu 12.** Vì sao không nên ép **ClassLoader.getSystemClassLoader()** sang **URLClassLoader** trên Java 17?

**Đáp án:** Built-in system loader là implementation detail và không được API bảo đảm thuộc URLClassLoader. Dùng public APIs hay cơ chế build/deployment thích hợp.

## 17. Checklist áp dụng khi thiết kế hệ thống

- **Classpath app đơn giản:** dựa vào system loader mặc định; không cần tự tạo ClassLoader.
- **Chạy plugin tùy biến:** xác định parent, namespace của plugin, API chung và chính sách delegation theo package.
- **Đăng ký SPI:** hiểu TCCL, ServiceLoader, provider metadata và module configuration.
- **Tách phiên bản dependency:** kiểm tra class identity qua defining loader, tránh sao chép API/interface chung vào từng loader con.
- **Dùng Reflection:** chọn loader rõ ràng khi cần; cân nhắc **Class.forName(name, false, loader)** nếu chỉ muốn tìm/kiểm tra loại mà chưa muốn initialize.
- **Quản lý lifecycle:** dừng thread/timer, giải phóng registry/cache và TCCL khi plugin ngừng dùng để loader có thể được thu gom khi không còn reachable.
- **Module system:** kiểm tra cả loader visibility và quan hệ reads/exports/opens.
- **Chẩn đoán lỗi:** ghi tên class, defining loader, nơi load, error cause và trạng thái thread context phù hợp; tránh dựa duy nhất vào tên package hay JAR.
- **Bytecode instrumentation:** đảm bảo class bytes, package, module, class loader identity và linking constraints cùng phù hợp; tránh define trùng tên trong một loader.

### Tài liệu chính thức

- **Java 17 API — java.lang.ClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java 17 API — java.lang.Class**, các phương thức **getClassLoader**, **forName**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java 17 API — java.lang.Thread**, **getContextClassLoader/setContextClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- **Java 17 API — java.util.ServiceLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **JVMS Java SE 17, §5.3 — Creation and Loading**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS Java SE 17, §5.4 — Linking**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- **JVMS Java SE 17, §5.5 — Initialization**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5

**Ghi nhớ:** Trên Java 17+, **bootstrap** cung cấp nền tảng lõi, **platform** xử lý nhiều platform classes, và **application/system** thường nạp lớp ứng dụng. ClassLoader mặc định **ưu tiên ủy quyền parent trước rồi mới findClass**, nhưng custom loader và cơ chế module có thể phức tạp hơn sơ đồ cây. **Cùng binary name + khác defining loader = khác class runtime**. **Loading không đồng nghĩa initialization**; **TCCL không phải defining loader**. Khi xử lý class loading, hãy luôn chỉ ra **loader nào nhận yêu cầu, loader nào định nghĩa, và lớp đang ở giai đoạn nào của vòng đời JVM**.
