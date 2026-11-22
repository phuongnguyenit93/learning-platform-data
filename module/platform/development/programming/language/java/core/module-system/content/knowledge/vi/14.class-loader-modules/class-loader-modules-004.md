# Class identity giữa các loader khác nhau

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao hai lớp có **cùng tên đầy đủ và cùng bytecode** vẫn có thể là hai kiểu khác nhau trong JVM.
- Phân biệt **binary name**, **defining class loader** và **initiating class loader**.
- Tự tái hiện tình huống ép kiểu thất bại giữa các class loader bằng Java 21.
- Nhận biết tác động đến kiểu dữ liệu, biến static, reflection, SPI, module và cơ chế nạp lại plugin.
- Chẩn đoán lỗi class loader bằng bằng chứng từ đối tượng và môi trường chạy.

## 2. JVM xác định danh tính lớp như thế nào?

Trong một JVM, danh tính của một lớp thông thường được xác định bởi cặp:

> **Class identity = (binary name, defining class loader)**

**Binary name** là tên nhị phân của lớp, chẳng hạn **com.example.Plugin**. **Defining class loader** là loader thực sự định nghĩa lớp đó vào JVM. Lưu ý: đây là quan hệ danh tính đối với lớp được định nghĩa lúc chạy; tên file, tên JAR hay nội dung bytecode không thay thế được danh tính của loader.

Giả sử hai loader độc lập là **L1** và **L2** cùng định nghĩa lớp có binary name **com.example.Plugin** từ một bộ bytecode giống hệt nhau:

| Thuộc tính | Lớp do L1 định nghĩa | Lớp do L2 định nghĩa |
|---|---|---|
| Binary name | com.example.Plugin | com.example.Plugin |
| Bytecode | Có thể giống nhau hoàn toàn | Có thể giống nhau hoàn toàn |
| Defining loader | L1 | L2 |
| Đối tượng Class | C1 | C2 |
| Danh tính JVM | (com.example.Plugin, L1) | (com.example.Plugin, L2) |

Kết luận: **C1 khác C2**, nên đối tượng tạo từ C1 không tự động là một thể hiện của C2. Hai lớp có cùng tên có thể có các bộ trạng thái static và vòng đời độc lập.

Trong Java, **Class#getName()** kiểm tra tên; **toán tử == trên hai đối tượng Class** mới kiểm tra chúng có đại diện cho chính cùng một lớp lúc chạy hay không.

### Defining loader và initiating loader

- **Defining loader**: loader đã gọi cơ chế định nghĩa lớp (thường qua ClassLoader#defineClass, hoặc cơ chế tương đương của JVM). Danh tính lớp gắn với loader này.
- **Initiating loader**: loader được yêu cầu bắt đầu việc nạp lớp. Nó có thể trả về lớp do loader cha hoặc loader khác định nghĩa thông qua cơ chế ủy quyền.
- **Class#getClassLoader()** trả về defining loader; một lớp của bootstrap loader có thể trả về **null**.

Ví dụ: loader con yêu cầu nạp **java.lang.String**, rồi ủy quyền cho bootstrap loader. Loader con tham gia yêu cầu nạp nhưng không trở thành defining loader của String. Vì thế, không thể suy ra rằng “hai yêu cầu nạp đến từ hai loader” luôn tạo ra hai lớp riêng.

## 3. Ủy quyền loader quyết định việc có trùng lớp hay không

Cơ chế thường gặp của **ClassLoader#loadClass** là **parent-first delegation**:

1. Kiểm tra lớp đã được nạp/khởi tạo yêu cầu trước đó hay chưa.
2. Hỏi loader cha có thể nạp lớp này không.
3. Nếu cha không tìm được, loader hiện tại mới tự tìm và định nghĩa (thường ở **findClass**).

Nhờ đó, nhiều loader con có thể chia sẻ một lớp đã được loader cha định nghĩa. Khi cả L1 và L2 đều ủy quyền thành công cho cùng một lớp ở cha, kết quả **C1 == C2**.

Ngược lại, nếu mỗi loader có thể tự định nghĩa bản sao của lớp (ví dụ hai plugin cô lập, mỗi plugin có đường dẫn nạp riêng và loader cha không thấy lớp đó), chúng sẽ có hai danh tính khác nhau. Một số hệ thống plugin dùng chiến lược **child-first** có chọn lọc để ưu tiên lớp trong plugin. Cách này tăng mức cô lập nhưng phải kiểm soát các lớp API được chia sẻ.

**Phân biệt ba điều thường bị nhầm:**

- Cùng tên class: chỉ cho biết tên, chưa đủ xác định cùng kiểu.
- Cùng đường dẫn/JAR hoặc cùng mã bytecode: chỉ cho biết nguồn mã, chưa đủ xác định cùng kiểu.
- Cùng đối tượng Class: xác nhận cùng lớp lúc chạy; các phép kiểm tra kiểu dựa trên đúng danh tính này.

## 4. Thực hành: cùng tên và bytecode, khác Class identity

Ví dụ sau chạy với **JDK 21** (cũng áp dụng từ Java 9 trở lên). Ta dùng hai **URLClassLoader**, cả hai đều đọc thư mục **out**, nhưng mỗi loader có quyền tự định nghĩa **demo.Greeter**. Dùng **platform class loader** làm cha để lớp demo không bị application loader nạp và chia sẻ ngoài ý muốn.

Cấu trúc thư mục trước khi biên dịch:

~~~text
class-identity-demo/
├── demo/
│   └── Greeter.java
└── IdentityDemo.java
~~~

Tạo **demo/Greeter.java**:

~~~java
package demo;

public final class Greeter {
    public static int count = 0;

    public String greet() {
        return "Xin chào từ Greeter";
    }
}
~~~

Tạo **IdentityDemo.java**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class IdentityDemo {
    public static void main(String[] args) throws Exception {
        URL classesDirectory = Path.of("out").toUri().toURL();

        // Platform loader không nạp lớp demo.Greeter trên application classpath.
        ClassLoader sharedParent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader loader1 =
                     new URLClassLoader(new URL[] {classesDirectory}, sharedParent);
             URLClassLoader loader2 =
                     new URLClassLoader(new URL[] {classesDirectory}, sharedParent)) {

            Class<?> class1 = Class.forName("demo.Greeter", true, loader1);
            Class<?> class2 = Class.forName("demo.Greeter", true, loader2);

            System.out.println("Cùng tên: "
                    + class1.getName().equals(class2.getName()));
            System.out.println("Cùng đối tượng Class: " + (class1 == class2));
            System.out.println("class1 do loader1 định nghĩa: "
                    + (class1.getClassLoader() == loader1));
            System.out.println("class2 do loader2 định nghĩa: "
                    + (class2.getClassLoader() == loader2));

            Object fromLoader1 = class1.getDeclaredConstructor().newInstance();
            System.out.println("class1.isInstance: "
                    + class1.isInstance(fromLoader1));
            System.out.println("class2.isInstance: "
                    + class2.isInstance(fromLoader1));

            try {
                class2.cast(fromLoader1);
            } catch (ClassCastException expected) {
                System.out.println("Ép kiểu thất bại: "
                        + expected.getClass().getSimpleName());
            }

            class1.getField("count").setInt(null, 7);
            System.out.println("Static count thuộc class1: "
                    + class1.getField("count").getInt(null));
            System.out.println("Static count thuộc class2: "
                    + class2.getField("count").getInt(null));
        }
    }
}
~~~

Tại thư mục **class-identity-demo**, thực hiện:

~~~bash
mkdir out
javac -encoding UTF-8 -d out demo/Greeter.java IdentityDemo.java
java -cp out IdentityDemo
~~~

Kết quả dự kiến:

~~~text
Cùng tên: true
Cùng đối tượng Class: false
class1 do loader1 định nghĩa: true
class2 do loader2 định nghĩa: true
class1.isInstance: true
class2.isInstance: false
Ép kiểu thất bại: ClassCastException
Static count thuộc class1: 7
Static count thuộc class2: 0
~~~

### Giải thích theo từng bước

1. **Class.forName** với loader1 và loader2 yêu cầu nạp cùng binary name. Hai loader cùng thấy một file **out/demo/Greeter.class**.
2. Loader cha được chọn không nạp lớp demo; vì vậy mỗi URLClassLoader tự định nghĩa một lớp. Kết quả có cùng tên nhưng **class1 != class2**.
3. Đối tượng **fromLoader1** thuộc class1. **class2.isInstance(fromLoader1)** trả về false, và **class2.cast(fromLoader1)** ném **ClassCastException**.
4. Trường **static count** được sở hữu bởi từng lớp đã định nghĩa. Đặt giá trị bằng 7 ở class1 không đổi count của class2. Điều này cũng áp dụng cho static initializer và nhiều bộ nhớ đệm static.

**Điểm mấu chốt của thí nghiệm:** chỉ thay đổi loader mà vẫn dùng cùng file biên dịch đã đủ tạo ra hai kiểu khác nhau. Đóng URLClassLoader bằng **close()** chỉ giải phóng các tài nguyên liên quan; nó không bảo đảm JVM lập tức dỡ lớp khỏi bộ nhớ.

### Thử thay đổi để kiểm chứng vai trò của delegation

Nếu cho cả hai URLClassLoader dùng application class loader làm cha, và **demo.Greeter** nằm trên application classpath, cơ chế parent-first thông thường sẽ trả về lớp chung của cha. Khi đó **class1 == class2** có thể là true, **getClassLoader()** trỏ về application loader, và trạng thái static được chia sẻ. Kết quả phụ thuộc vào chính xác loader nào thực sự định nghĩa lớp, chứ không phụ thuộc vào việc đã tạo bao nhiêu đối tượng URLClassLoader.

## 5. Hệ quả khi các lớp khác identity

### 5.1. ClassCastException và kiểm tra kiểu

Khi mã ở plugin A chuyển đối tượng **com.example.Message** sang một nơi kỳ vọng **com.example.Message** do plugin B định nghĩa, tên trong thông báo lỗi có thể giống nhau nhưng JVM xem chúng là hai kiểu khác nhau.

- Ép kiểu trực tiếp, **Class#cast** và **Class#isInstance** đều dựa trên quan hệ kiểu lúc chạy.
- **isAssignableFrom** cũng xét danh tính và quan hệ kế thừa/interface thật sự; không so tên chuỗi.
- Trong thông báo ClassCastException của Java hiện đại thường có chi tiết loader/module giúp phân biệt hai phía. Tận dụng các chi tiết đó khi chẩn đoán.

Ví dụ, nếu cả hai loader cùng định nghĩa **api.Task**, một plugin triển khai **api.Task** của loader A sẽ không được JVM coi là triển khai **api.Task** của loader B dù tên interface giống nhau.

### 5.2. Biến static, singleton và khởi tạo lớp

Mỗi lớp được định nghĩa riêng có một tập static fields và quá trình khởi tạo lớp riêng. Singleton lưu bằng trường static trong một class không đương nhiên là singleton toàn JVM nếu class đó có nhiều bản định nghĩa từ nhiều loader. Logger registries, caches hoặc bộ đếm static cũng có thể phân tách tương tự.

Không nên dựa vào static field trong plugin để giữ trạng thái cần chia sẻ xuyên các loader. Đưa trạng thái cần chia sẻ vào service/interface có vòng đời và loader được xác định rõ.

### 5.3. Reflection và lỗi liên kết

Reflection có thể lấy được tên phương thức và tạo đối tượng thành công nhưng vẫn thất bại khi truyền đối tượng có kiểu tham số không đúng identity. Khi các loader phải giải quyết một kiểu xuất hiện trong chữ ký phương thức, JVM có thể áp dụng **loading constraints** để buộc các bên thống nhất về lớp được tham chiếu. Vi phạm ràng buộc có thể tạo **LinkageError**, đôi khi kèm thông báo **loader constraint violation**.

**Không đánh đồng các lỗi:**

| Hiện tượng | Ý nghĩa thường gặp | Cách xác minh |
|---|---|---|
| ClassCastException | Đối tượng không thuộc kiểu đích tại runtime | In tên và defining loader của hai Class |
| LinkageError / loader constraint violation | Xung đột khi liên kết các định nghĩa class qua loader | Kiểm tra chữ ký, API chung và đường ủy quyền |
| ClassNotFoundException | Loader được hỏi không tìm thấy binary name yêu cầu | Kiểm tra classpath/module path và loader đã dùng |
| NoClassDefFoundError | JVM không thể hoàn tất việc dùng lớp cần thiết, ví dụ thiếu dependency hoặc lỗi khởi tạo trước đó | Xem nguyên nhân gốc trong stack trace |

Các lỗi trên có thể liên quan cùng một cấu hình loader sai, nhưng không phải mọi trường hợp đều là “hai class cùng tên”.

## 6. Thiết kế API chung cho hệ thống plugin

Giả sử ứng dụng chủ định nghĩa một API:

~~~java
package api;

public interface Task {
    String execute();
}
~~~

Plugin chỉ nên tự định nghĩa **plugin.impl.TaskImpl** và tham chiếu tới **api.Task** đã được loader dùng chung định nghĩa.

~~~java
package plugin.impl;

import api.Task;

public final class TaskImpl implements Task {
    @Override
    public String execute() {
        return "Hoàn thành";
    }
}
~~~

Mô hình loader mong muốn:

~~~text
Application / shared API loader
    └── định nghĩa api.Task
         ├── Plugin loader A
         │    └── định nghĩa plugin.a.TaskImpl
         └── Plugin loader B
              └── định nghĩa plugin.b.TaskImpl
~~~

Nhờ hai loader plugin đều ủy quyền **api.Task** cho cùng loader cấp trên, các implementation có thể được sử dụng qua interface chung mà vẫn cách ly lớp nội bộ của từng plugin.

Nếu plugin A tự nạp một bản **api.Task** khác và plugin B/application dùng bản còn lại, kiểm tra **api.Task.class.isAssignableFrom(pluginClass)** có thể thất bại hoặc xuất hiện lỗi liên kết. Vì vậy:

- Đặt các **interface, DTO, exception và kiểu xuất hiện trong hợp đồng giao tiếp** vào một API chung do một loader xác định.
- Cho loader plugin **ủy quyền các package API chung**. Chỉ cô lập các package triển khai thực sự cần độc lập.
- Truyền đối tượng qua interface chung hoặc dữ liệu trung lập (ví dụ JSON/byte array với schema rõ ràng) khi các implementation cố ý tách biệt.
- Khi dùng **ServiceLoader**, chọn loader rõ ràng, ví dụ **ServiceLoader.load(Task.class, pluginLoader)**; provider phải tương thích với đúng **Task.class** mà phía gọi sử dụng. **Thread context class loader (TCCL)** cũng ảnh hưởng nhiều framework khi chúng tra cứu provider hoặc resource.

**Lưu ý:** chỉ đưa cùng tên interface vào cả hai JAR chưa đủ. API cần có **cùng Class identity** tại thời điểm chạy.

## 7. Liên hệ với package và Java Platform Module System (JPMS)

Từ Java 9, hệ thống module thêm ranh giới truy cập và metadata module. Tuy nhiên, module có tên giống nhau hoặc các package trùng tên không làm cho hai class do hai loader khác nhau định nghĩa trở thành một class.

Phân biệt:

- **Binary name**: tên nhị phân, như **demo.Greeter**.
- **Runtime class identity**: binary name kết hợp với defining loader.
- **Runtime package**: package được xác định theo tên package và defining loader; vì vậy hai lớp trong cùng package chữ viết nhưng do hai loader khác nhau định nghĩa không tự động có quyền truy cập package-private của nhau.
- **Module**: miền chứa lớp với các quy tắc readability/exports/opens riêng; **Class#getModule()** cho biết module của lớp. Classpath classes thường thuộc unnamed module của loader tương ứng.

Hai loader khác nhau có thể tạo hai unnamed modules khác nhau. Cần phân biệt **module access error** (quyền truy cập giữa module) với **type identity error** (kiểu khác identity). Cả hai có thể xuất hiện trong cùng hệ thống nhưng cách sửa khác nhau.

## 8. Chẩn đoán tại runtime

Khi thấy hai kiểu cùng tên trong stack trace, hãy ghi nhận đúng các bằng chứng sau tại cả nơi tạo đối tượng và nơi ép kiểu:

~~~java
static void inspect(Object value) {
    Class<?> type = value.getClass();
    ClassLoader loader = type.getClassLoader();

    System.out.println("Class name: " + type.getName());
    System.out.println("Class object: " + type);
    System.out.println("Defining loader: " + loader);
    System.out.println("Loader identity: "
            + (loader == null ? "bootstrap" : System.identityHashCode(loader)));
    System.out.println("Module: " + type.getModule());
}
~~~

Sau đó so sánh trực tiếp **sourceClass == targetClass**, **targetClass.isInstance(value)** và nếu cần **sourceClass.getClassLoader() == targetClass.getClassLoader()**. Không dùng riêng **loader.toString()** hoặc hash code làm bằng chứng tuyệt đối, vì chúng chỉ phục vụ nhận diện trong log; phép so sánh tham chiếu mới là phép kiểm tra danh tính.

Trong ứng dụng thực tế, tiếp tục kiểm tra:

1. Loader cha của từng loader và chế độ parent-first/child-first.
2. Các bản sao dependency/API trong application classpath, module path, plugin JAR hoặc fat JAR.
3. Loader mà framework dùng để tìm class/resource, đặc biệt TCCL và ServiceLoader.
4. Các đối tượng, luồng, cache hoặc callback còn giữ tham chiếu tới loader cũ sau khi reload.
5. Các stack trace đầy đủ của ClassCastException hoặc LinkageError, nhất là chi tiết loader/module.

## 9. Class identity khi hot reload và ứng dụng lâu dài

Các container, application server, plugin engine và hệ thống hot reload thường tạo class loader mới cho phiên bản mới. Điều này cho phép nạp lớp phiên bản mới mà không tái sử dụng class identity cũ. Hai phiên bản có thể tồn tại cùng lúc trong JVM; đối tượng cũ không thể mặc nhiên ép thành lớp mới dù vẫn giữ cùng tên package và class.

Để phiên bản cũ đủ điều kiện được dỡ, ứng dụng cần ngừng sử dụng đối tượng, Class, loader và các tham chiếu liên quan (bao gồm thread, ThreadLocal, listener, registry hoặc static cache). **Garbage collection và class unloading không diễn ra ngay theo yêu cầu**, nên không nên kết luận có memory leak chỉ từ việc còn thấy một class loader ngắn hạn.

Thực tế nên thiết kế API ổn định ở loader dùng chung, quản lý vòng đời resource/plugin rõ ràng, và chuyển dữ liệu giữa các phiên bản theo định dạng không gắn với lớp triển khai của loader cũ.

## 10. Tự kiểm tra kiến thức

**Tình huống A:** L1 và L2 đều hỏi loader cha nạp **api.Task**, và cha trả về cùng một Class. Dù có hai loader con, kết quả **L1.loadClass("api.Task") == L2.loadClass("api.Task")** là gì?

**Đáp án:** true, khi cả hai lời gọi nhận đúng cùng lớp mà cha đã định nghĩa.

**Tình huống B:** Hai URLClassLoader riêng đọc cùng file **plugin.Widget.class**, mỗi loader tự định nghĩa lớp. Hai đối tượng Class có **getName()** giống nhau. Liệu gọi **classB.cast(instanceOfA)** có hợp lệ không?

**Đáp án:** Không. Instance của lớp do loader A định nghĩa không tự động là instance của lớp do loader B định nghĩa; phép cast sẽ ném ClassCastException.

**Tình huống C:** Ứng dụng reload plugin bằng loader mới, nhưng singleton static trong loader cũ vẫn còn giá trị. Có phải JVM vi phạm quy tắc singleton không?

**Đáp án:** Không. Singleton static gắn với một lớp được định nghĩa cụ thể. Loader cũ và loader mới có class identity và static state riêng.

## 11. Ghi nhớ

- **Tên class + defining loader** là cơ sở để nhận diện lớp trong JVM.
- Cùng bytecode, cùng file JAR hoặc cùng binary name **không đảm bảo** cùng Class identity.
- Parent-first delegation có thể giúp các loader con dùng chung một định nghĩa class; loader cô lập có thể tạo các định nghĩa riêng.
- Ranh giới loader ảnh hưởng trực tiếp đến cast, reflection, API/plugin contracts, static state, module/package access và hot reload.
- Khi gặp lỗi, hãy so sánh **Class object và defining loader thực tế** ở cả hai phía trước khi sửa classpath hay thay đổi cách nạp lớp.

**Tài liệu nền tảng:** Java Virtual Machine Specification, chương 5 (Loading, Linking, and Initializing); Java SE API của **java.lang.Class**, **java.lang.ClassLoader**, **java.net.URLClassLoader** và **java.util.ServiceLoader**.
