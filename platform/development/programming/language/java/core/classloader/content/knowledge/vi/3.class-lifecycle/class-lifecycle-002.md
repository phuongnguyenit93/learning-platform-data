# Tìm biểu diễn nhị phân và tạo `Class` trong JVM

## 1. Mục tiêu

Trong vòng đời lớp Java, **nạp lớp (loading)** trả lời hai câu hỏi thực tế:

1. JVM lấy **biểu diễn nhị phân** của lớp hoặc interface từ đâu?
2. Từ biểu diễn đó, JVM tạo **định nghĩa kiểu ở runtime** và đối tượng **java.lang.Class** đại diện cho kiểu như thế nào?

Đây là bước trọng tâm trước khi phân tích sâu các bước **linking** và **initialization**. Việc đã có một đối tượng **Class** **không đồng nghĩa** với việc mã khởi tạo **static** đã được thực thi.

Sau bài này, bạn có thể:
- Giải thích mối quan hệ giữa tên nhị phân, file class, nguồn bytecode và class loader.
- Mô tả cách JVM yêu cầu loader tìm hoặc định nghĩa lớp, cũng như cách nó tạo Class mirror.
- Phân biệt **initiating loader** với **defining loader** và giải thích danh tính của một lớp.
- Hiểu vì sao cùng tên lớp nhưng khác loader có thể không ép kiểu được cho nhau.
- Kiểm chứng bằng Java 17+ và các lệnh **javap**, **jar** và logging của JVM.

## 2. Từ mã nguồn đến biểu diễn nhị phân

Với lớp Java thông thường, chương trình đi qua đường đi sau:

~~~text
src/demo/Widget.java
         │ javac -d out ...
         ▼
out/demo/Widget.class          ┐
hoặc tệp trong một JAR         ├─ nguồn chứa class-file bytes
hoặc bytecode từ nguồn khác    ┘
         │
         │ JVM yêu cầu class loader tìm/định nghĩa lớp
         ▼
JVM đọc biểu diễn nhị phân được cung cấp
         │
         ├─ kiểm tra tên và định nghĩa cần thiết
         ├─ tạo biểu diễn kiểu nội bộ của JVM
         └─ gắn với đối tượng java.lang.Class
         │
         ▼
Class<?> đại diện cho demo.Widget
         │
         ├─ có thể được liên kết theo quy tắc JVM
         └─ được khởi tạo khi các điều kiện initialization xảy ra
~~~

**Biểu diễn nhị phân (binary representation)** là dữ liệu mô tả cấu trúc và mã thực thi của lớp/interface. Trong trường hợp quen thuộc, đó là **định dạng class file của JVM**. Trình biên dịch Java **javac** thường tạo **.class** từ **.java**, nhưng JVM không yêu cầu mọi lớp phải xuất phát từ một tệp **.class** riêng nằm trên ổ đĩa: bytecode cũng có thể được lấy từ JAR, sinh động trong bộ nhớ hoặc nguồn riêng của loader.

Một file **.jar** thông thường là **gói ZIP chứa nhiều entry**, trong đó các entry như **demo/Widget.class** chứa bytecode từng lớp. JAR **không phải** một biểu diễn nhị phân duy nhất của tất cả lớp bên trong.

### 2.1 Những thành phần có trong class file

Class file có cấu trúc theo Java Virtual Machine Specification, chẳng hạn:

| Phần | Vai trò |
| --- | --- |
| Magic number **0xCAFEBABE** | Dấu hiệu định dạng class file. |
| Phiên bản major/minor | Cho biết phiên bản định dạng class file cần hỗ trợ. |
| **constant_pool** | Chứa hằng, tên, kiểu và các **symbolic reference** cần thiết. |
| Access flags, this_class, super_class, interfaces | Mô tả lớp, superclass, interface, các thuộc tính truy cập. |
| Fields và methods | Mô tả thành viên, descriptor và thuộc tính; code của method phù hợp được lưu trong thuộc tính **Code**. |
| Attributes | Siêu dữ liệu như Code, SourceFile, LineNumberTable, annotations, bootstrap methods... tùy class. |

Ví dụ, **demo.Widget** có thể được tham chiếu trong constant pool bằng tên kiểu nội bộ **demo/Widget**. Khi chạy, các tham chiếu ký hiệu này sẽ được xử lý theo quy tắc liên kết; việc có constant pool **không có nghĩa** mọi tham chiếu đã được phân giải ngay khi lớp được nạp.

JVM định nghĩa định dạng class file và các ràng buộc để loader cung cấp bytes hợp lệ. Bytecode hỏng, có tên không khớp hoặc không được JVM đang chạy hỗ trợ có thể dẫn tới lỗi như **ClassFormatError**, **NoClassDefFoundError** hoặc **UnsupportedClassVersionError**, tùy nguyên nhân cụ thể. Những lỗi ấy khác với việc đơn thuần không tìm thấy tài nguyên trên classpath.

### 2.2 Ba dạng tên rất dễ nhầm

Xét lớp khai báo là **package demo; public class Widget**:

| Ngữ cảnh | Tên tương ứng | Công dụng |
| --- | --- | --- |
| **Binary name** | **demo.Widget** | Tên class được truyền cho **ClassLoader.loadClass** hay **Class.forName** với lớp thông thường. |
| **Internal name** trong class file | **demo/Widget** | Dạng dấu **/** trong nhiều cấu trúc class file. |
| **Resource path** thường gặp | **demo/Widget.class** | Đường dẫn entry tìm trong classpath/JAR khi triển khai loader kiểu thông thường. |
| **Descriptor** của tham chiếu tới kiểu | **Ldemo/Widget;** | Cú pháp field/method descriptor. |

Lớp lồng không phải top-level có thể có binary name như **demo.Outer$Inner**. **demo.Outer.Inner** là cách viết tên trong nhiều ngữ cảnh mã nguồn, nhưng không phải binary name của loại nested class thông thường đó.

**Lưu ý:** việc đổi dấu chấm thành dấu **/** rồi thêm **.class** là quy ước tra tài nguyên thường dùng, không phải thuật toán bắt buộc cho mọi loader. Một custom loader có thể đọc bytes từ bộ nhớ, cơ sở dữ liệu, mạng hoặc dữ liệu mã hóa.

## 3. Ai tìm lớp? Class loader và delegation

JVM sử dụng các class loader để đưa định nghĩa lớp vào runtime. Trong ứng dụng Java phổ biến có:

- **Bootstrap loader:** được JVM cung cấp để định nghĩa nhiều lớp nền tảng; **Class.getClassLoader()** thường trả **null** với lớp được bootstrap định nghĩa.
- **Platform loader:** phục vụ các module của nền tảng thích hợp.
- **Application/System loader:** thường nạp mã ứng dụng từ classpath/module path trong phạm vi phụ trách.
- **Custom loader:** do ứng dụng/thư viện xây dựng, ví dụ hệ plugin, engine hoặc container.

Đây là mô hình khái quát; không nên coi thứ tự này là một chuỗi thư mục cố định trên ổ đĩa hoặc một cam kết rằng mọi JVM/custom loader đều tìm lớp từ cùng các vị trí.

### 3.1 Cơ chế delegation phổ biến

Với cách cài đặt mặc định của **ClassLoader.loadClass(name, resolve)**, loader thường:

1. Kiểm tra lớp với tên đó đã được loader này tìm/nạp trước chưa.
2. Nếu chưa, yêu cầu parent loader (hoặc bootstrap nếu phù hợp).
3. Nếu parent không tìm được, gọi **findClass(name)** của chính nó.
4. Nếu tham số **resolve** yêu cầu, thực hiện bước resolveClass phù hợp trước khi trả về.

Ý tưởng là cho các loader liên quan chia sẻ lớp nền tảng và tránh định nghĩa trùng không cần thiết. Tuy nhiên, Java cho phép **custom class loader** có chính sách delegation riêng. Không thể áp quy tắc **parent-first** cho mọi loader mà không xem mã triển khai.

### 3.2 Initiating loader và defining loader khác nhau

Giả sử application loader **A** được yêu cầu tìm **java.lang.String**, rồi ủy quyền cho bootstrap loader **B** định nghĩa String:

~~~text
load request tới A
       │
       └─ A chuyển cho B
                  │
                  └─ B định nghĩa java.lang.String
                         │
                         └─ A nhận lại Class<?> tương ứng
~~~

Theo thuật ngữ JVM:
- **Initiating loader:** loader mà JVM ghi nhận đã khởi xướng việc loading của lớp đó (có thể bao gồm loader ủy quyền).
- **Defining loader:** loader **thực sự định nghĩa** class/interface từ biểu diễn nhị phân hoặc theo quy tắc tạo lớp thích hợp.

Trong ví dụ, **A** có thể là initiating loader, còn **B** là defining loader. Việc gọi **A.loadClass(...)** **không chứng minh** A là defining loader của kết quả.

Với một lớp thông thường, **clazz.getClassLoader()** cho biết loader định nghĩa lớp đó (hoặc **null** nếu lớp được bootstrap định nghĩa). Nó không phải API liệt kê tất cả initiating loader đã từng yêu cầu lớp.

## 4. JVM tạo đối tượng Class khi nào và dùng để làm gì?

Khi JVM tạo một class/interface runtime từ biểu diễn nhị phân, nó cũng có một đối tượng **java.lang.Class** tương ứng để Java code có thể mô tả và thao tác với kiểu. Đây thường được gọi là **Class mirror**.

Đối tượng Class có thể được lấy qua:

~~~java
Class<?> a = String.class;
Class<?> b = someObject.getClass();
Class<?> c = Class.forName("demo.Widget", false, loader);
Class<?> d = loader.loadClass("demo.Widget");
~~~

Các thao tác trên không tương đương hoàn toàn:

- **T.class** lấy Class mirror cho kiểu T, không tự yêu cầu chạy static initializer của T.
- **object.getClass()** lấy lớp runtime thực của đối tượng đã tồn tại.
- **Class.forName(name, false, loader)** yêu cầu load (và link theo hợp đồng API) lớp tìm được nhưng **không khởi tạo lớp theo lời gọi này**.
- **ClassLoader.loadClass(name)** tìm/nạp và trả đối tượng Class; cách gọi này **không chủ động khởi tạo** lớp. Việc phân giải tham chiếu phụ thuộc thời điểm/quy tắc JVM và overload được gọi.
- **Class.forName(name)** dạng một tham số mặc định yêu cầu initialization cho lớp tìm được, nên có thể làm static initializer chạy ngay.

**Class mirror không phải là instance của lớp được mô tả.** Ví dụ **Widget.class** có kiểu tĩnh **Class<Widget>**; đối tượng đó dùng cho metadata/reflection, còn **new Widget()** là cách tạo instance của Widget. **getDeclaredConstructor().newInstance()** cũng tạo instance và có thể kích hoạt initialization trước khi gọi constructor.

Thông tin mà Class mirror cho phép xem có tên lớp, superclass, interfaces, declared members, annotation, module và class loader. JVM có các cấu trúc dữ liệu runtime nội bộ phục vụ thực thi, nhưng đặc tả **không bắt buộc** phải có một bố cục bộ nhớ cố định cho mọi JVM; đối tượng **java.lang.Class** không phải bản sao trực tiếp từng byte của file **.class**.

## 5. Ví dụ Java 17+: tìm bytecode và quan sát Class mirror

Tạo hai file sau trong đúng thư mục:

~~~text
project/
└── src/
    └── demo/
        ├── Widget.java
        └── LoadingDemo.java
~~~

**src/demo/Widget.java**:

~~~java
package demo;

public class Widget {
    static {
        System.out.println("Widget initialized");
    }

    public String message() {
        return "Hello";
    }
}
~~~

**src/demo/LoadingDemo.java**:

~~~java
package demo;

public class LoadingDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader loader = LoadingDemo.class.getClassLoader();

        String resource = "demo/Widget.class";
        System.out.println("resource found = "
                + (loader.getResource(resource) != null));

        Class<?> type = loader.loadClass("demo.Widget");
        System.out.println("binary name = " + type.getName());

        Class<?> again = Class.forName("demo.Widget", false, loader);
        System.out.println("same Class = " + (type == again));

        System.out.println("before instance creation");
        Object instance = type.getDeclaredConstructor().newInstance();
        System.out.println("instance type = "
                + instance.getClass().getSimpleName());
    }
}
~~~

Đứng tại thư mục **project**, chạy:

~~~bash
javac -d out src/demo/Widget.java src/demo/LoadingDemo.java
java -cp out demo.LoadingDemo
~~~

**Stdout kỳ vọng** khi dùng application classpath đúng như lệnh trên:

~~~text
resource found = true
binary name = demo.Widget
same Class = true
before instance creation
Widget initialized
instance type = Widget
~~~

Phân tích:

1. **javac -d out** tạo các file **out/demo/Widget.class** và **out/demo/LoadingDemo.class**. Đây là các biểu diễn nhị phân để application loader tìm.
2. **getResource("demo/Widget.class")** cho thấy bytecode dạng tài nguyên có thể được tìm trong ví dụ này. Chỉ thấy resource **chưa có nghĩa** class đã được JVM định nghĩa.
3. **loadClass("demo.Widget")** trả đối tượng Class mô tả Widget. Chưa có dòng **Widget initialized**: chương trình chưa kích hoạt initialization của Widget.
4. **Class.forName(..., false, ...)** trả cùng Class vì yêu cầu cùng binary name qua cùng hệ loader trong ví dụ; toán tử **==** đúng vì cùng một định nghĩa runtime.
5. **getDeclaredConstructor().newInstance()** kích hoạt initialization trước khi tạo instance; static block in ra đúng một lần rồi mới tới dòng cuối.

Ở những loader đặc biệt, **getResource** có thể bị chặn, ánh xạ khác hoặc tìm được tài nguyên mà **loadClass** lại không định nghĩa được lớp tương ứng. Vì vậy phương pháp dò resource hữu ích khi gỡ lỗi classpath thông thường, nhưng **không thay thế** kết quả thực tế của **loadClass**.

### 5.1 Xem biểu diễn nhị phân bằng javap

Sau khi biên dịch:

~~~bash
javap -classpath out -v demo.Widget
~~~

Một số thông tin nên tìm trong output (giá trị version và các index thay đổi theo JDK/compiler):

- **Classfile .../out/demo/Widget.class**, tên class, superclass;
- **major version** cùng constant pool;
- tên kiểu hoặc mô tả method/field;
- method **<clinit>** chứa mã cho static initializer;
- thuộc tính **Code** trong các method có bytecode.

Để chỉ xem lệnh bytecode, sử dụng:

~~~bash
javap -classpath out -c -p demo.Widget
~~~

Tùy ngôn ngữ shell, nội dung output có thể dài. **javap** giúp kiểm tra class file đã biên dịch; nó **không chứng minh** JVM runtime đã nạp class từ đúng tệp đó nếu ứng dụng chạy với classpath, module path hoặc loader khác.

Nếu đóng gói JAR:

~~~bash
jar --create --file example.jar -C out .
jar --list --file example.jar
~~~

Bạn sẽ thấy các entry kiểu **demo/Widget.class** và **demo/LoadingDemo.class**. Lệnh **jar --list** chỉ liệt kê dữ liệu trong archive, không nạp hay khởi tạo class vào JVM đang chạy.

## 6. Define class từ bytecode: điều gì tạo nên một định nghĩa mới?

Trong custom loader, phương thức **defineClass(...)** được hỗ trợ bởi ClassLoader cho phép chuyển mảng byte hợp lệ thành class do loader đó định nghĩa. Một luồng thường gặp là:

~~~text
ClassLoader.loadClass(name)
       │
       ├─ trả class đã biết / ủy quyền parent
       │
       └─ tìm bytecode (ví dụ trong findClass)
               │
               ▼
     defineClass(binaryName, bytes, ...)
               │
               ▼
       Class<?> mới của loader định nghĩa
~~~

Nếu gọi **defineClass** cho cùng binary name mà cùng loader đã định nghĩa một lần, không thể âm thầm thay Class hiện tại bằng nội dung khác: JVM có ràng buộc về định nghĩa trùng và có thể báo **LinkageError**. Cơ chế **redefine/retransform** do instrumentation cung cấp là vấn đề khác, không phải một lần defineClass mới để tạo Class thứ hai trong cùng loader.

Loader cần cung cấp binary name phù hợp, bytes hợp lệ và tuân thủ ràng buộc package/protection domain và loading constraints. **defineClass** là thao tác tạo định nghĩa runtime, không phải API bảo đảm class đã chạy các static initializer.

### 6.1 Danh tính class = (binary name, defining loader)

Trong JVM, danh tính của một class/interface được xác định bởi **binary name kết hợp defining class loader**. Hệ quả trực tiếp:

- Cùng tên và **cùng định nghĩa class**: tham chiếu Class giống nhau.
- Cùng tên nhưng **được định nghĩa bởi hai loader khác nhau**: hai kiểu runtime **khác nhau**.
- Việc in ra **Class.getName()** giống nhau chưa đủ để xác nhận hai object có thể ép kiểu với nhau.

Mô hình:

~~~text
                  bytecode cho isolated.Payload
                             │
                     ┌───────┴────────┐
                     ▼                ▼
              defining loader L1   defining loader L2
                     │                │
                     ▼                ▼
               Class #1           Class #2
                name =             name =
          isolated.Payload    isolated.Payload
                     │                │
                     └───────┬────────┘
                             ▼
                 Class #1 != Class #2
~~~

Trong các ứng dụng có plugin, modular runtime và container, đây là nguyên nhân phổ biến của lỗi **ClassCastException** nhìn bề ngoài có vẻ vô lý: hai lớp cùng tên nhưng thuộc hai định nghĩa runtime.

### 6.2 Ví dụ chạy được: hai loader tự định nghĩa cùng một binary name

Tạo cấu trúc:

~~~text
project/
└── src/
    └── isolated/
        ├── Payload.java
        └── TwinLoadersDemo.java
~~~

**src/isolated/Payload.java**:

~~~java
package isolated;

public class Payload {
    public String value() {
        return "payload";
    }
}
~~~

**src/isolated/TwinLoadersDemo.java**:

~~~java
package isolated;

import java.nio.file.Files;
import java.nio.file.Path;

public class TwinLoadersDemo {
    static final class ByteArrayLoader extends ClassLoader {
        Class<?> defineOwn(byte[] classBytes) {
            return defineClass(
                    "isolated.Payload",
                    classBytes,
                    0,
                    classBytes.length
            );
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("out/isolated/Payload.class")
        );

        ByteArrayLoader left = new ByteArrayLoader();
        ByteArrayLoader right = new ByteArrayLoader();

        Class<?> a = left.defineOwn(bytes);
        Class<?> b = right.defineOwn(bytes);

        System.out.println("same name = "
                + a.getName().equals(b.getName()));
        System.out.println("same Class = " + (a == b));
        System.out.println("different defining loader = "
                + (a.getClassLoader() != b.getClassLoader()));

        Object first = a.getDeclaredConstructor().newInstance();
        Object second = b.getDeclaredConstructor().newInstance();
        System.out.println("same runtime type = "
                + (first.getClass() == second.getClass()));

        try {
            a.cast(second);
        } catch (ClassCastException ex) {
            System.out.println("cross-loader cast = ClassCastException");
        }
    }
}
~~~

Tại thư mục **project**:

~~~bash
javac -d out src/isolated/Payload.java src/isolated/TwinLoadersDemo.java
java -cp out isolated.TwinLoadersDemo
~~~

Stdout:

~~~text
same name = true
same Class = false
different defining loader = true
same runtime type = false
cross-loader cast = ClassCastException
~~~

Cả hai ByteArrayLoader đều nhận **đúng cùng mảng bytes** nhưng gọi **defineClass** một cách riêng rẽ. Đây là ví dụ chủ động định nghĩa riêng để chứng minh danh tính lớp; phương thức **defineOwn** minh họa trực tiếp API defineClass, **không đi qua cơ chế parent delegation mặc định của loadClass**. Trong ứng dụng thực, bạn thường triển khai **findClass** có kiểm soát rồi để **loadClass** thực hiện quy trình delegation thích hợp.

Nếu sửa ví dụ để hai loader đều ủy quyền cho cùng parent định nghĩa Payload, kết quả có thể là **cùng** đối tượng Class; chỉ khởi tạo hai loader object không tự làm phát sinh hai định nghĩa của Payload.

## 7. Trường hợp đặc biệt: array, primitive, hidden class và module

Không nên áp mô hình **tìm tệp .class trên đĩa** cho mọi kiểu JVM hỗ trợ.

### 7.1 Array class

Với biểu thức như:

~~~java
String[] names = new String[2];
Class<?> arrayType = names.getClass();
~~~

JVM tạo array class theo quy tắc riêng, không tìm tệp **[Ljava/lang/String;.class**. Component type ảnh hưởng đến defining loader của array class; mảng có component type là primitive có bootstrap loader. Tạo mảng **Foo[]** không yêu cầu khởi tạo Foo chỉ vì mảng được cấp phát.

Tên runtime của class mảng được biểu diễn theo descriptor, ví dụ **[Ljava.lang.String;** trong **Class.getName()**, nên không thể coi đó là tên file thông thường.

### 7.2 Primitive và void

**int.class**, **boolean.class** và **void.class** có Class mirror, nhưng không tương ứng với class file kiểu **int.class** trên classpath. JVM tạo và quản lý các Class object này theo quy tắc đặc biệt.

### 7.3 Hidden classes

Các API như **MethodHandles.Lookup.defineHiddenClass** hỗ trợ những lớp dành cho mục đích runtime đặc biệt; không nên giả định rằng mọi lớp có thể được tìm lại bằng binary name qua **ClassLoader.loadClass**. Hidden classes cần được phân biệt với lớp/interface thông thường do loader định nghĩa bằng tên.

### 7.4 Module và phạm vi tra cứu

Khi dùng Java Module System, **module path**, module graph, readability, exports và chính sách loader/module ảnh hưởng đến việc lớp nào tìm được và ai có thể truy cập nó. Đường dẫn có file **.class** hoặc **.jar** **không đủ** để kết luận lớp được truy cập thành công ở runtime. **Class.getModule()** là một nguồn dữ liệu khi kiểm tra runtime, còn tên module và tên binary class vẫn là hai khái niệm khác nhau.

## 8. Phân biệt tìm thấy bytes, load, link và initialize

| Điều quan sát | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| **jar --list** hiện ra **demo/Widget.class** | JAR có entry với tên đó. | JVM đã nạp Widget. |
| **getResource** trả URL/stream | Loader hoặc cơ chế resource tìm thấy tài nguyên. | Bytes đó nhất định đã được define thành Class. |
| **loadClass("demo.Widget")** trả Class | Lời gọi trả về Class runtime tương ứng. | Static initializer của Widget đã chạy. |
| **Class.forName(name, false, loader)** trả Class | Lớp được tìm/nạp và link theo hợp đồng API, không yêu cầu init ở lời gọi này. | Mọi symbolic reference đều đã resolution ngay thời điểm đó. |
| **Class.forName(name)** trả Class | Với class thông thường, lời gọi yêu cầu initialization. | Constructor instance đã chạy hay object Widget đã được tạo. |
| **new Widget()** thành công | Widget đã được khởi tạo theo quy tắc trước khi tạo instance. | Class sẽ được khởi tạo lại cho các đối tượng tiếp theo. |

Vì **linking** có verification/preparation/resolution với thời điểm chi tiết theo đặc tả, việc kết hợp **javap**, logging và chương trình có static block sẽ cho nhiều góc nhìn hơn so với dùng riêng một log.

## 9. Chẩn đoán lỗi tìm định nghĩa lớp

### 9.1 File/JAR có lớp nhưng ClassNotFoundException

Kiểm tra:

1. Tên truyền cho **Class.forName** hoặc **loadClass** có đúng **binary name** chưa? Với nested class cần kiểm tra ký tự **$**.
2. Runtime **-cp**, **--module-path** và cấu hình thư viện khác có chứa định nghĩa cần thiết không? Classpath dùng lúc **javac** không tự động bảo đảm classpath lúc **java** giống nhau.
3. Loader nào đang nhận yêu cầu? Nó có delegation/filter riêng không? Chẳng hạn code trong một plugin có thể dùng loader khác code ứng dụng.
4. Class có thực sự tồn tại dưới đúng package và tên sau khi build hoặc đóng JAR không?

**ClassNotFoundException** là checked exception thường gặp từ API tìm lớp theo tên. **NoClassDefFoundError** là LinkageError có thể xuất hiện khi JVM cần định nghĩa class không có sẵn hoặc class trước đó không khởi tạo được. Hai lỗi có thể liên quan nhưng **không đồng nghĩa**.

### 9.2 ClassFormatError hoặc UnsupportedClassVersionError

**ClassFormatError** chỉ dữ liệu class file không hợp lệ về định dạng; **UnsupportedClassVersionError** xảy ra khi VM không hỗ trợ phiên bản class file được cung cấp. Kiểm tra compiler **javac -version**, runtime **java -version**, hoặc **javap -verbose** để so sánh version. Không giải quyết lỗi này chỉ bằng thay class name.

### 9.3 NoSuchMethodError, IllegalAccessError, LoaderConstraintViolation

Đó có thể là lỗi ở quá trình resolution/linking hoặc không tương thích nhị phân, ví dụ có hai phiên bản thư viện trên đường nạp thực tế. Với các loader khác nhau, JVM còn áp ràng buộc nhất quán kiểu tại một số điểm sử dụng; lỗi **LinkageError** về loading constraint cần kiểm tra defining loader của những lớp cùng tên.

### 9.4 ClassCastException mặc dù hai tên giống nhau

Lấy đối tượng và xem:

~~~java
Class<?> actual = object.getClass();

System.out.println(actual.getName());
System.out.println(actual.getClassLoader());
System.out.println(actual.getModule());
~~~

Đối chiếu với Class của kiểu đích bằng **==**, **getClassLoader()**, **getModule()** và nơi bytecode thực sự xuất phát. Thông báo lỗi casting gần đây thường cho biết loader/module của các class liên quan. **Không khắc phục bằng ép kiểu cưỡng bức**; cần thống nhất contract API chung, loader visibility hoặc cách chia sẻ kiểu giữa host và plugin.

## 10. Công cụ quan sát class thực tế

Trong môi trường Java 17+, một lựa chọn tương đối hữu ích khi cần xem JVM đã load các lớp nào:

~~~bash
java -Xlog:class+load=info -cp out demo.LoadingDemo
~~~

Log thường thể hiện tên lớp và nguồn theo khả năng của VM đang dùng, nhưng format và số lượng dòng phụ thuộc JDK/VM. Để kiểm tra các tag và mức log được VM hỗ trợ:

~~~bash
java -Xlog:help
~~~

**Giới hạn:** log class loading giúp biết lớp đã được load, **không chứng minh thời điểm chạy <clinit>**. Với vấn đề danh tính class, hãy kiểm tra **Class.getClassLoader()** hoặc quan sát thực thể Class thực tế. Với class file trên đĩa, dùng **javap -v** để đọc cấu trúc. Với artifact đóng gói, dùng **jar --list** để xác nhận entry có tồn tại.

Trong các hệ thống lớn, ghi log đầy đủ cho mọi class có thể gây nhiễu. Hãy tạo ví dụ nhỏ tái hiện trước, dùng đúng classpath/module path, rồi mở rộng quan sát nếu cần.

## 11. Những hiểu nhầm phổ biến

- **“Tên class là đủ để xác định kiểu.”** Chưa đủ: defining loader là thành phần của danh tính runtime.
- **“Tôi tìm thấy .class trong JAR, vậy JVM chắc chắn đã load nó.”** Sai: JAR có entry không đồng nghĩa loader đang chạy đã dùng entry đó.
- **“loadClass luôn đọc lại file mỗi lần gọi.”** Sai: loader thường dùng cache/cơ chế tìm lớp đã được load; định nghĩa trùng trong cùng loader bị ràng buộc.
- **“Loader nhận yêu cầu chính là loader định nghĩa.”** Sai khi có delegation.
- **“Class<?> là bản bytecode còn nằm nguyên trong heap.”** Sai: Class là đối tượng phản chiếu kiểu runtime; bố cục nội bộ là chi tiết VM.
- **“Đã có Class thì static initializer đã chạy.”** Sai: loading và initialization khác nhau.
- **“Mọi kiểu đều có một tệp .class.”** Sai: primitive, void, array và một số dạng runtime đặc biệt được xử lý riêng.
- **“Custom loader nào cũng parent-first.”** Không nhất thiết; cần đọc chính sách delegation của loader.
- **“Dùng getResource là đủ để chứng minh class được define.”** Sai: tài nguyên và cơ chế define class là hai bước riêng.

## 12. Tự kiểm tra

**Câu 1.** Với package **demo**, tại sao **demo.Widget**, **demo/Widget** và **demo/Widget.class** là ba chuỗi khác nhau?

**Đáp án:** Chúng lần lượt là binary name, dạng internal name và đường dẫn tài nguyên phổ biến. API **loadClass** cho lớp thông thường nhận binary name, còn file/JAR thường chứa resource path.

**Câu 2.** Tại sao **loader.loadClass("demo.Widget")** có thể trả về Class mà chưa in dòng trong static block?

**Đáp án:** Nó nạp/trả Class nhưng không chủ động khởi tạo lớp; static initializer chạy khi gặp điều kiện initialization.

**Câu 3.** Hai ByteArrayLoader nhận cùng bytes và đều gọi defineClass cho cùng tên. Tại sao Class khác nhau?

**Đáp án:** Binary name giống, nhưng defining loader khác; JVM coi đó là hai định nghĩa class riêng.

**Câu 4.** Một custom loader A ủy quyền cho parent B và nhận lại Class do B định nghĩa. **getClassLoader()** của Class trả A hay B?

**Đáp án:** Trả về defining loader B (nếu không phải bootstrap). A có thể là initiating loader.

**Câu 5.** Có nên suy ra VM đã khởi tạo một lớp nếu chỉ thấy **class+load** log?

**Đáp án:** Không. Log class loading phản ánh loading; initialization phải được xác minh riêng.

**Câu 6.** Tại sao lớp primitive **int** vẫn có **int.class** dù không có class file trên đĩa?

**Đáp án:** JVM cung cấp Class mirror cho primitive theo quy tắc riêng; nó không cần lookup file class thông thường.

## 13. Ghi nhớ

Hãy phân tích đường đi thành các câu hỏi độc lập:

~~~text
Tên nhị phân
    ↓
Ai nhận yêu cầu load?
    ↓
Loader tìm bytes ở nguồn nào?
    ↓
Loader nào thực sự định nghĩa class?
    ↓
JVM tạo định nghĩa runtime + Class mirror
    ↓
Linking/initialization xảy ra theo các điều kiện riêng
~~~

**Binary representation** là dữ liệu mô tả lớp; **defining loader** cùng binary name quyết định danh tính của lớp runtime; **Class mirror** là đối tượng Java biểu diễn định nghĩa ấy. Ba khái niệm này giải thích đa số vấn đề classpath, plugin isolation và nhầm lẫn giữa “đã thấy bytecode” với “JVM đã định nghĩa lớp”.

**Đọc thêm từ đặc tả Java SE 21:**
- JLS §12.2 (*Loading of Classes and Interfaces*): https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2
- JVMS §4 (*The class File Format*): https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- JVMS §5.3 (*Creation and Loading*): https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3
- ClassLoader API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
