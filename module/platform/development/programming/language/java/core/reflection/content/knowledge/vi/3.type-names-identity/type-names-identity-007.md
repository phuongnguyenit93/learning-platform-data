# Class.getPackage(), Class.getPackageName() và Class.getModule() trong Java Reflection

## 1. Mục tiêu và bối cảnh

Khi đã có một đối tượng **Class<?>**, Reflection cho phép bạn hỏi kiểu đó thuộc package nào và module nào. Ba API thường bị nhầm lẫn là:

- **Class.getPackage()**: trả đối tượng **Package** để truy vấn metadata của package tại runtime.
- **Class.getPackageName()**: trả **String** là tên package, tiện để hiển thị, phân loại và ghi log.
- **Class.getModule()**: trả đối tượng **Module** của Java Platform Module System (JPMS), dùng khi cần biết kiểu thuộc named module hay unnamed module, hoặc cần xem quan hệ đọc/xuất/mở package.

Đây là **ba góc nhìn khác nhau về cùng một kiểu**, không phải ba cách gọi thay thế nhau. Package tổ chức namespace của class; module nhóm các package và diễn đạt phụ thuộc/ranh giới truy cập; đối tượng Class là điểm bắt đầu để truy vấn metadata.

Sau bài học, bạn có thể giải thích giá trị trả về, cách xử lý null, kết quả đặc biệt với array/primitive/void, phân biệt unnamed package và unnamed module, viết code Reflection tránh giả định sai và dự đoán output của ví dụ Java 17+.

## 2. Ba API và mối quan hệ Class → Package → Module

| API trên Class<?> | Kiểu trả về | Câu hỏi trả lời | Kết quả đáng chú ý |
| --- | --- | --- | --- |
| **getPackage()** | **java.lang.Package** (có thể null) | Package runtime của class này có metadata gì? | **null** với array, primitive, void |
| **getPackageName()** | **String** | Tên package đầy đủ là gì? | **""** với unnamed package; **"java.lang"** với primitive/void; array dùng package của element type |
| **getModule()** | **java.lang.Module** | Class này thuộc module runtime nào? | Array dùng module của element type; primitive/void thuộc **java.base**; class trên classpath thường thuộc unnamed module |

Ba phương thức đều là phương thức instance của **java.lang.Class**, không phải phương thức của một object bất kỳ:

~~~java
Class<?> type = String.class;
Package pkg = type.getPackage();
String packageName = type.getPackageName();
Module module = type.getModule();
~~~

Nếu có đối tượng hiện hữu, lấy Class token bằng **instance.getClass()**, với điều kiện **instance != null**. Class token biểu diễn **kiểu thực tế của object**, còn kiểu khai báo của biến không làm đổi package hay module của object đó.

Sơ đồ khái niệm:

~~~text
Class<?>  ----getPackage()----> Package metadata (hoặc null)
    |
    +-------getPackageName()--> Chuỗi tên package
    |
    +-------getModule()------> Module metadata

Ví dụ String.class:
  class              = java.lang.String
  package            = java.lang
  named module       = java.base
~~~

Một module có thể chứa nhiều package. Một package gồm các class/interface được tổ chức dưới cùng tên package; package không đồng nghĩa với module. Tên package có thể trùng một đoạn trong tên module nhưng Java không yêu cầu hai tên khớp nhau.

## 3. Class.getPackage(): khi nào cần đối tượng Package?

Chữ ký:

~~~java
public Package getPackage()
~~~

Với class thông thường, API trả về đối tượng **Package** đại diện package runtime của class. Khác với một chuỗi tên, Package có metadata và API riêng:

- **getName()**: tên package.
- **getSpecificationTitle()**, **getSpecificationVersion()**, **getSpecificationVendor()**: thông tin đặc tả nếu có.
- **getImplementationTitle()**, **getImplementationVersion()**, **getImplementationVendor()**: thông tin triển khai nếu có.
- **isSealed()** và **isSealed(URL)**: thông tin sealing của package.
- **getAnnotation(...)**, **isAnnotationPresent(...)**: truy vấn annotation trên package khi có metadata tương ứng, ví dụ từ **package-info.class** với annotation lưu ở runtime.

Nhiều trường thông tin phiên bản/vendor **có thể null**. Java không tự lấy phiên bản ứng dụng, phiên bản Maven/Gradle hay phiên bản module từ tên package. Không nên coi **Package.getImplementationVersion()** là nguồn luôn tồn tại cho phiên bản hệ thống.

Ví dụ an toàn khi đọc metadata:

~~~java
Package info = String.class.getPackage();

if (info != null) {
    System.out.println("Package: " + info.getName());
    String version = info.getImplementationVersion();
    System.out.println("Has implementation version: " + (version != null));
}
~~~

Dòng đầu ở trên in **Package: java.lang**. Dòng thứ hai phụ thuộc metadata và môi trường Java, vì vậy không nên ghi cứng rằng nhất định true hay false.

### 3.1. getPackage() có thể null

Theo API, **getPackage() trả null** khi Class token biểu diễn:

- Array: **String[].class**, **int[][].class**, ...
- Primitive: **int.class**, **boolean.class**, ...
- Void: **void.class**.

Vì vậy code sau có lỗi runtime:

~~~java
// String[].class.getPackage().getName(); // NullPointerException
~~~

Hãy kiểm tra null trước khi dùng Package, hoặc dùng **getPackageName()** nếu chỉ cần tên:

~~~java
Class<?> type = String[].class;
Package info = type.getPackage();

String name = info == null ? type.getPackageName() : info.getName();
System.out.println(name); // java.lang
~~~

**Lưu ý:** Giá trị null của Package đối với array/primitive/void là quy tắc của API, không có nghĩa array không có runtime module hoặc không xác định được tên package theo quy ước **getPackageName()**.

## 4. Class.getPackageName(): dùng khi chỉ cần tên package

Chữ ký:

~~~java
public String getPackageName()
~~~

Phương thức có từ **Java 9**, trả tên package đầy đủ, không kèm tên class. Đây thường là lựa chọn trực tiếp nhất cho báo cáo, phân loại class hoặc logging.

Ví dụ:

~~~java
System.out.println(String.class.getPackageName());           // java.lang
System.out.println(java.util.Map.Entry.class.getPackageName()); // java.util
System.out.println(String[].class.getPackageName());         // java.lang
System.out.println(int.class.getPackageName());              // java.lang
~~~

Khác biệt cần nhớ:

1. Class ở **named package** trả tên đầy đủ, ví dụ **java.util**.
2. Class ở **unnamed package** (source không khai báo package) trả chuỗi rỗng **""**, không phải null.
3. Nested/member class trả tên package của enclosing class. **Map.Entry** là nested interface nhưng vẫn thuộc **java.util**, không thuộc một package có tên **java.util.Map**.
4. Local/anonymous class lấy package từ class bao quanh theo định nghĩa API.
5. Array trả tên package của **element type**: **String[]**, **String[][]** đều cho **java.lang**.
6. Primitive và **void** trả **java.lang** theo quy định đặc biệt. Điều này không có nghĩa có source class tên **java.lang.int** hoặc **java.lang.void**.

### 4.1. Unnamed package khác với unnamed module

Ví dụ tệp **Demo.java** đặt trong thư mục gốc, không có khai báo **package**:

~~~java
public class Demo {
    public static void main(String[] args) {
        System.out.println("[" + Demo.class.getPackageName() + "]");
    }
}
~~~

~~~bash
javac Demo.java
java Demo
~~~

Stdout:

~~~text
[]
~~~

Dấu ngoặc vuông giúp thấy rõ chuỗi package rỗng.

**Unnamed package** là trường hợp class không có khai báo package. **Unnamed module** là module runtime dành cho class không thuộc named module (điển hình các class chạy trên **classpath**). Hai khái niệm độc lập: class có **package com.example** vẫn có thể thuộc **unnamed module** nếu được chạy trên classpath.

### 4.2. Không tự cắt chuỗi getName() để suy package

**Class.getName()** không đảm bảo định dạng "package.class" cho mọi loại Class token:

- Nested class thường có dấu **$** trong binary name.
- Array có định dạng kiểu **[Ljava.lang.String;** hoặc **[I**.
- Primitive trả tên keyword như **int**.
- Các loại class đặc biệt có quy tắc tên riêng.

Vì vậy, nếu mục tiêu chỉ là tên package, dùng **getPackageName()** thay cho việc tìm dấu chấm cuối cùng trong **getName()**. Điều này giảm lỗi với mảng và những trường hợp đặc biệt.

## 5. Class.getModule(): metadata của Java module

Chữ ký:

~~~java
public Module getModule()
~~~

Phương thức có từ **Java 9**, là điểm vào của Java Platform Module System (JPMS). **java.lang.Module** mô tả một module runtime, gồm hai nhóm:

- **Named module**: có tên module (ví dụ **java.base**, **java.sql**, hoặc tên tự định nghĩa trong **module-info.java**).
- **Unnamed module**: không có tên module, thường chứa class chạy trên classpath. Runtime gắn unnamed module với class loader tương ứng.

Với bất kỳ Class token hợp lệ nào, **getModule()** trả một Module, kể cả class ở unnamed module, array, primitive và void; kết quả **Module.getName()** có thể null nếu module không tên.

Ví dụ:

~~~java
Module javaBase = String.class.getModule();

System.out.println(javaBase.getName()); // java.base
System.out.println(javaBase.isNamed()); // true
~~~

Đối với class ứng dụng chạy trên classpath, **MyClass.class.getModule().isNamed()** thường là false và **getName()** trả null. Đừng gọi **getModule().getName().length()** mà không kiểm tra null.

### 5.1. Các API hữu ích trên Module

| API | Dùng để hiểu |
| --- | --- |
| **getName()** | Tên named module; null nếu unnamed module |
| **isNamed()** | Named hay unnamed module |
| **getDescriptor()** | Module descriptor; null với unnamed module |
| **getPackages()** | Tập tên package trong module |
| **canRead(Module other)** | Module này có quan hệ đọc module khác không |
| **isExported(String packageName)** | Package có được export vô điều kiện không |
| **isExported(String packageName, Module other)** | Package có được export cho module đích không |
| **isOpen(String packageName)** | Package có được open vô điều kiện không |
| **isOpen(String packageName, Module other)** | Package có được open cho module đích không |

**Không đồng nhất exports với opens**:

- **exports** chủ yếu cho phép các module đủ quan hệ đọc truy cập public type và public member từ package được xuất, theo kiểm tra của Java.
- **opens** cho phép deep reflection vào package theo cơ chế truy cập Reflection (vẫn có những điều kiện truy cập khác).
- Một package có thể được **qualified export/open** chỉ cho một số module; khi đó phép kiểm tra không có tham số module đích không phản ánh đầy đủ quyền của từng caller.
- Có được đối tượng **Module** và tên module không tự trao quyền đọc/ghi member private. Các thao tác như **setAccessible(true)** vẫn có thể không được phép.

**Module** ở đây là JPMS module tại runtime. Nó không phải khái niệm "module Gradle" hay "module Maven" mặc dù các hệ công cụ build có thể tạo ra artifact chứa named module.

### 5.2. Quy tắc đặc biệt với array, primitive, void

Theo đặc tả của **Class.getModule()**:

- Với array, trả Module của **element type**. **String[]** thuộc module **java.base**; một array của class ứng dụng thuộc module của chính element class đó.
- Với primitive hoặc **void**, trả **java.base**.
- Với class trong unnamed module, trả đối tượng Module không tên của class loader định nghĩa class ấy.

Đây là lý do **String[].class.getPackage() == null** và **String[].class.getModule()** vẫn là Module **java.base**: package metadata của array và module theo element type được API xử lý theo hai quy tắc khác nhau.

## 6. Ví dụ Java 17+ chạy được: so sánh cả ba API

Tạo tệp **ClassNamespaceDemo.java** trong thư mục không khai báo package.

~~~java
public class ClassNamespaceDemo {
    private static void inspect(String label, Class<?> type) {
        Package pkg = type.getPackage();
        Module module = type.getModule();

        String pkgObject = pkg == null ? "null" : pkg.getName();
        String moduleName = module.isNamed()
                ? module.getName()
                : "<unnamed>";

        System.out.println(label
                + " | getPackageName=" + type.getPackageName()
                + " | getPackage=" + pkgObject
                + " | getModule=" + moduleName);
    }

    public static void main(String[] args) {
        inspect("String", String.class);
        inspect("String[]", String[].class);
        inspect("int", int.class);
        inspect("void", void.class);

        System.out.println("Local package: ["
                + ClassNamespaceDemo.class.getPackageName() + "]");
        System.out.println("Local module named: "
                + ClassNamespaceDemo.class.getModule().isNamed());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên trên **classpath**, không khai báo **module-info.java**:

~~~bash
javac ClassNamespaceDemo.java
java ClassNamespaceDemo
~~~

Stdout:

~~~text
String | getPackageName=java.lang | getPackage=java.lang | getModule=java.base
String[] | getPackageName=java.lang | getPackage=null | getModule=java.base
int | getPackageName=java.lang | getPackage=null | getModule=java.base
void | getPackageName=java.lang | getPackage=null | getModule=java.base
Local package: []
Local module named: false
~~~

Giải thích:

1. **String.class** là class bình thường thuộc package **java.lang**, named module **java.base**.
2. **String[].class** là array: không có đối tượng Package từ **getPackage()**, nhưng tên package và module lấy từ element type String.
3. **int.class** và **void.class** có **getPackage() == null**, **getPackageName() == "java.lang"** và module **java.base** theo đặc tả.
4. **ClassNamespaceDemo** được đặt ở unnamed package nên tên package là chuỗi rỗng. Khi chạy lệnh **java ClassNamespaceDemo** qua classpath, nó thuộc unnamed module.
5. Ví dụ dùng **module.isNamed()** trước khi đọc tên để tránh suy luận sai rằng null là lỗi tìm module.

**Phạm vi kết quả:** Lệnh ở trên giả định tệp nằm trong unnamed package và được chạy bằng classpath như minh họa. Nếu bạn đưa cùng class vào một named module hoặc thay source khai báo package, phần thông tin của **ClassNamespaceDemo** sẽ đổi tương ứng.

## 7. Ví dụ named module: package name độc lập với module name

Để thấy rõ khác biệt, tạo một Java module nhỏ với cấu trúc:

~~~text
src/
└── com.example.namespace/
    ├── module-info.java
    └── demo/
        └── api/
            └── NamespaceApp.java
~~~

Nội dung tệp **src/com.example.namespace/module-info.java**:

~~~java
module com.example.namespace {
    exports demo.api;
}
~~~

Nội dung tệp **src/com.example.namespace/demo/api/NamespaceApp.java**:

~~~java
package demo.api;

public class NamespaceApp {
    public static void main(String[] args) {
        Class<?> type = NamespaceApp.class;
        Module module = type.getModule();

        System.out.println(type.getPackageName());
        System.out.println(type.getPackage().getName());
        System.out.println(module.getName());
        System.out.println(module.isNamed());
    }
}
~~~

Đứng ở thư mục có **src/**, dùng JDK 17+:

~~~bash
javac --module-source-path src -d out -m com.example.namespace
java --module-path out -m com.example.namespace/demo.api.NamespaceApp
~~~

Kết quả:

~~~text
demo.api
demo.api
com.example.namespace
true
~~~

Đối chiếu:

- **demo.api** là tên **package** của class NamespaceApp.
- **com.example.namespace** là tên **named module** chứa package đó.
- **Package.getName()** và **Class.getPackageName()** khớp trong trường hợp class bình thường này.
- **Module.getName()** khác với tên package và có nhiệm vụ khác.

Hãy thử thay **exports demo.api;** bằng một chỉ thị module hợp lệ khác phù hợp với mục tiêu học; nhớ rằng quyền truy cập giữa module còn phụ thuộc **requires**, **exports**, **opens** và caller. Ví dụ hiện tại chỉ dùng truy cập public và tự quan sát metadata trong cùng module.

## 8. Bảng các trường hợp dễ gây nhầm

| Loại Class token | getPackage() | getPackageName() | getModule() |
| --- | --- | --- | --- |
| **String.class** | Package có tên **java.lang** | **java.lang** | named module **java.base** |
| **java.util.List.class** | Package có tên **java.util** | **java.util** | named module **java.base** |
| **String[].class** | **null** | **java.lang** | module của String: **java.base** |
| **int.class** | **null** | **java.lang** | **java.base** |
| **void.class** | **null** | **java.lang** | **java.base** |
| **Class ở unnamed package** | Đọc Package metadata một cách null-safe | **""** | Phụ thuộc module chứa class; trên classpath thường unnamed |
| **Class package demo.api trên classpath** | Package có tên **demo.api** | **demo.api** | unnamed module của class loader |
| **Class package demo.api trong named module com.example.namespace** | Package có tên **demo.api** | **demo.api** | named module **com.example.namespace** |

Các trường hợp đầu là kiến thức API độc lập với tên project; hai trường hợp cuối cần xét **cách class được triển khai và nạp**, không suy ra JPMS module chỉ từ chuỗi package.

### getPackageName() có phải là duy nhất để nhận diện lớp?

Không. Hai class có cùng **package name** (thậm chí cùng binary class name) nhưng do class loader khác nhau định nghĩa không nhất thiết là cùng kiểu runtime. Một **String** đơn lẻ không mô tả đầy đủ identity của Class token. Khi thiết kế registry Reflection hoặc plugin, cần cân nhắc cả **Class object**, class loader và module tương ứng; đừng dùng package name như khóa duy nhất toàn hệ thống.

## 9. Dùng trong ứng dụng và framework như thế nào?

### 9.1. Ghi log để xác định nguồn class

~~~java
static String identify(Class<?> type) {
    Module module = type.getModule();
    String moduleName = module.isNamed() ? module.getName() : "<unnamed>";
    return type.getName()
            + " | package=" + type.getPackageName()
            + " | module=" + moduleName;
}
~~~

Đây là đoạn **method minh họa** (không phải chương trình độc lập). Nó giúp chẩn đoán vì sao một class đến từ named module hay classpath, nhất là khi ứng dụng pha trộn jar truyền thống và JPMS.

### 9.2. Truy vấn package annotation

~~~java
Package pkg = targetClass.getPackage();
if (pkg != null && pkg.isAnnotationPresent(MyMarker.class)) {
    // Package này có MyMarker với retention phù hợp ở runtime.
}
~~~

Đoạn trên là **mã minh họa**, giả định **targetClass** và annotation **MyMarker** đã được khai báo. Annotation cần **@Retention(RetentionPolicy.RUNTIME)** nếu muốn thấy khi phản chiếu; package annotation thường được khai báo trong **package-info.java**. Cần dùng **Package** thay vì chỉ chuỗi tên vì **String** không mang annotation.

### 9.3. Kiểm tra truy cập package qua module

~~~java
Module owner = targetClass.getModule();
Module caller = SomeCaller.class.getModule();
String packageName = targetClass.getPackageName();

boolean exportedToCaller = owner.isExported(packageName, caller);
boolean openToCaller = owner.isOpen(packageName, caller);
~~~

Đây là **mã minh họa** (giả định **targetClass** và **SomeCaller** đã được cung cấp). Hai boolean phản ánh trạng thái **exports**/**opens** theo module đích, giúp phân tích một phần điều kiện truy cập. Chúng không tự thực hiện lời gọi Reflection và cũng không thay thế toàn bộ luật truy cập Java. Nếu đang xử lý array hoặc primitive, hãy xác định rõ bạn muốn truy vấn package/module của **element type** hay metadata theo quy tắc riêng của Class API, tránh dùng nhầm giá trị suy ra.

### 9.4. Chọn API theo mục đích

- **Chỉ cần chuỗi namespace trong log/cấu hình** → **getPackageName()**.
- **Cần phiên bản, sealing hoặc annotation của runtime package** → **getPackage()** và kiểm tra null.
- **Cần named/unnamed module, exports, opens, reads** → **getModule()**, tiếp tục qua **Module**.
- **Cần tên đầy đủ class** → **getName()** hoặc API tên phù hợp, không thay thế bằng package name.
- **Cần biết đối tượng hiện tại có class gì** → **obj.getClass()**, rồi mới truy vấn ba API trên.

## 10. Lỗi phổ biến và cách tránh

**Lỗi 1: coi ba API tương đương.** Package object, package name và Module object có kiểu trả về cũng như ý nghĩa khác nhau. Ví dụ **String[].class.getPackage()** null nhưng hai API kia vẫn trả thông tin có ích.

**Lỗi 2: gọi thẳng getPackage().getName() cho mọi Class token.** Có thể ném **NullPointerException** trên array/primitive/void. Dùng **getPackageName()** nếu chỉ cần tên hoặc xử lý nhánh null.

**Lỗi 3: suy ra tên module từ tên package.** **java.lang** thuộc **java.base**; class **demo.api** có thể ở unnamed module trên classpath hoặc named module khác. Chỉ **getModule()** cho biết module runtime thực tế.

**Lỗi 4: suy ra unnamed package và unnamed module là một.** Một class khai báo **package demo.api** vẫn có thể ở unnamed module nếu triển khai qua classpath.

**Lỗi 5: dùng Module.getName() mà không xét unnamed module.** **getModule()** vẫn trả Module, nhưng **getName()** trả null khi unnamed. Kiểm tra **isNamed()** trước khi xử lý tên.

**Lỗi 6: mặc định Package luôn chứa version hoặc vendor.** Metadata nhiều khi không có và các getter trả null. Nếu ứng dụng yêu cầu version, cần có nguồn dữ liệu được khai báo rõ ràng trong quá trình đóng gói.

**Lỗi 7: cho rằng có module nghĩa là Reflection được mở khóa.** Module có thể export package cho public access nhưng không open package cho deep reflection. Cần hiểu JPMS access rules và kiểm tra điều kiện của caller.

**Lỗi 8: tách package bằng substring từ getName().** Dễ sai với array, primitive, nested class. Dùng API chuyên dụng **getPackageName()**.

**Lỗi 9: bỏ qua runtime class loader.** Cùng tên class/package không đảm bảo Class token giống nhau; điều này đặc biệt quan trọng khi viết plugin container hoặc cơ chế nạp lớp động.

## 11. Bài tập tự kiểm tra

**Câu 1.** Đúng hay sai: **String[].class.getPackage().getName()** trả **java.lang**?

**Câu 2.** Với **String[].class**, vì sao **getPackage()** trả null nhưng **getModule().getName()** lại là **java.base**?

**Câu 3.** Class **demo.api.Service** được nạp từ classpath, không có **module-info.java**. Có thể chắc chắn module runtime của nó tên **demo.api** không?

**Câu 4.** Khi chỉ cần xuất tên package của một **Class<?>** bất kỳ (kể cả array/primitive), nên chọn API nào?

**Câu 5.** Nếu gọi **someClass.getModule().getName()** và nhận null thì class có "không thuộc module nào" hay không?

**Câu 6.** Khi cần phát hiện package annotation ở runtime, nên dùng tên package String hay Package metadata? Điều kiện về annotation là gì?

**Câu 7.** Named module **com.example.namespace** có class trong package **demo.api**. Dự đoán **getPackageName()** và **getModule().getName()** của class đó.

### Đáp án giải thích

1. **Sai.** **getPackage()** của array trả null; chuỗi lời gọi sẽ ném NullPointerException. **getPackageName()** mới trả **java.lang**.
2. Vì **getPackage()** áp dụng quy tắc array => null, còn **getModule()** dùng module của **element type String** là **java.base**.
3. **Không.** Nếu class không nằm trong named JPMS module thì nó thuộc **unnamed module**, thường **isNamed() == false** và **getName() == null**.
4. **getPackageName()**. Đây là API trả String và có xử lý đặc biệt cho các loại Class token đó.
5. **Vẫn có Module object**; chỉ là unnamed module có tên null.
6. Dùng **Package**; annotation cần có metadata tương ứng (thường trong **package-info.class**) và **RUNTIME retention** để truy vấn runtime.
7. **demo.api** và **com.example.namespace**: package name khác module name.

## 12. Ghi nhớ

**getPackage()** trả runtime Package metadata, có thể null; **getPackageName()** trả chuỗi tên package; **getModule()** trả JPMS Module của Class token. Khi phân tích lỗi Reflection, xác định rõ mục tiêu là package **metadata**, package **name** hay module **membership/access**, đồng thời xét các trường hợp array/primitive/void, unnamed module và class loader.

### Tài liệu chuẩn

- Java SE 17 API — **Class**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 API — **Package**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Package.html
- Java SE 17 API — **Module**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java Language Specification — packages and modules: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
