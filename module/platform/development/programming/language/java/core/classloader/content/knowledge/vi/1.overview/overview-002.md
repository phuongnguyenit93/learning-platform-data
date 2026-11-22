# Từ mã nguồn, bytecode đến lớp đang tồn tại trong JVM

Một lớp Java không đi thẳng từ tệp `.java` thành đối tượng trong bộ nhớ. Trước tiên, mã nguồn được biên dịch thành định dạng `.class`; khi chương trình chạy, JVM sử dụng class loader để tìm và định nghĩa lớp, thực hiện các bước liên kết, rồi khởi tạo lớp khi điều kiện của Java yêu cầu. Sau đó, các đối tượng mới có thể được tạo và bytecode của các phương thức được thực thi.

Bài này tập trung vào **chuỗi chuyển đổi từ mã nguồn → class file → lớp do JVM quản lý** và vai trò cụ thể của class loader. Phân biệt được từng bước sẽ giúp giải thích vì sao lớp có trên đĩa nhưng JVM chưa nạp, vì sao hai lớp cùng tên không nhất thiết là một kiểu, và vì sao một lỗi có thể xuất hiện khi chạy dù biên dịch đã thành công.

## 1. Bức tranh tổng thể

```text
Mã nguồn: src/demo/Target.java
          |
          | javac --release 17
          v
Class file: out/demo/Target.class
  - tên nhị phân, constant pool, field/method, bytecode, metadata
          |
          | JVM cần tham chiếu đến lớp
          v
Class loader: tìm dữ liệu lớp + defineClass (hoặc cơ chế JVM tương ứng)
          |
          v
Loading → Linking [Verification → Preparation → Resolution*]
          |
          | sử dụng chủ động làm phát sinh yêu cầu khởi tạo
          v
Initialization: thực hiện <clinit> một lần cho mỗi lớp được định nghĩa
          |
          v
Class<?> / metadata lớp trong JVM
          |
          +--> new / reflection có thể tạo instance (đối tượng)
          +--> gọi phương thức: interpreter / JIT thực thi mã
```

Dấu `*`: **resolution** có thể được JVM thực hiện theo nhu cầu, không bắt buộc hoàn tất hết mọi tham chiếu trước khi initialization. Một biểu đồ tuyến tính mô tả quan hệ logic, không có nghĩa tất cả các bước chỉ xảy ra một lần tại một thời điểm cố định.

| Thành phần | Ở đâu/vai trò | Phân biệt |
| --- | --- | --- |
| `Target.java` | Tệp văn bản mã nguồn | JVM thông thường không chạy trực tiếp nội dung này như bytecode đã được biên dịch; lệnh `java Target.java` (source-file mode) có bước biên dịch do launcher thực hiện. |
| `Target.class` | Tệp hoặc tài nguyên chứa class-file bytes | Có thể nằm trong thư mục, JAR, module image hoặc được tạo trong bộ nhớ; không nhất thiết tồn tại như tệp riêng. |
| Bytecode | Chỉ thị trong `Code` attribute của phương thức cụ thể | Là đầu vào cho cơ chế thực thi của JVM, không phải mã máy CPU và không bao gồm toàn bộ nội dung class file. |
| Class loader | Thành phần xác định lớp từ dữ liệu nhị phân | Tham gia quyết định **định danh kiểu** cùng với tên nhị phân của lớp. |
| `java.lang.Class<?>` | Đối tượng phản chiếu đại diện cho lớp/kiểu ở thời gian chạy | Không phải bản sao tệp `.class` hay instance của chính lớp nghiệp vụ. |
| Instance | Đối tượng được tạo từ lớp, thường bằng `new` | Một lớp có thể đã được nạp mà chưa có instance nào. |

Lưu ý hai mốc độc lập: **`javac` thành công** chỉ chứng minh mã nguồn qua được các kiểm tra biên dịch; **JVM nạp/liên kết/khởi tạo thành công** còn phụ thuộc bytecode thực tế, phiên bản runtime, thư viện, loader và logic khởi tạo.

## 2. Từ `.java` sang `.class`: trình biên dịch làm gì?

`javac` đọc mã nguồn, phân tích token/cú pháp, kiểm tra kiểu, giải quyết tên dựa trên classpath/module path của **thời điểm biên dịch**, rồi sinh class file. Các lambda, generic, `switch`, `try`... được ánh xạ sang cấu trúc phù hợp trong class file. Generic thông thường dùng **type erasure**; các kiểu tham số hóa không tự động tạo một class file riêng cho mỗi `List<String>` và `List<Integer>`.

Một class file bắt đầu bằng magic number `0xCAFEBABE` và mang phiên bản định dạng (Java 17 tương ứng **major version 61**, Java 21 tương ứng 65). Trong đó có constant pool, thông tin tên lớp/cha/interface, modifiers, fields, methods, attributes và phần bytecode của các phương thức có mã. Constant pool chứa các hằng và các **symbolic references** như tên lớp, tên phương thức và descriptor; không có nghĩa mọi lớp được nhắc tới đều đã được nạp ngay khi file được đọc.

Tên nhị phân (binary name) của `demo.Target` là `demo.Target`; đường dẫn điển hình theo classpath là `demo/Target.class`. Đường dẫn tệp chỉ là một cách lưu trữ; cùng dữ liệu có thể nằm trong JAR hoặc đến từ loader tự viết.

### Bài thực hành A — quan sát biên dịch, nạp và khởi tạo

Tạo hai tệp chính xác theo cây thư mục:

```text
project/
└── src/
    └── demo/
        ├── Target.java
        └── App.java
```

**`src/demo/Target.java`**

```java
package demo;

public class Target {
    static {
        System.out.println("06 - Target initialized");
    }

    public static void hello() {
        System.out.println("07 - Target.hello()");
    }
}
```

**`src/demo/App.java`**

```java
package demo;

public class App {
    public static void main(String[] args) throws Exception {
        System.out.println("01 - main started");

        Class<?> byLiteral = Target.class;
        System.out.println("02 - " + byLiteral.getName());

        ClassLoader loader = App.class.getClassLoader();
        Class<?> byLoadClass = loader.loadClass("demo.Target");
        System.out.println("03 - same Class: " + (byLiteral == byLoadClass));

        Class<?> withoutInit = Class.forName("demo.Target", false, loader);
        System.out.println("04 - same Class: " + (byLiteral == withoutInit));

        System.out.println("05 - before active use");
        Target.hello();
        System.out.println("08 - main ended");
    }
}
```

Trong thư mục `project`, chạy bằng JDK 17 trở lên:

```sh
javac --release 17 -d out src/demo/Target.java src/demo/App.java
java -cp out demo.App
```

**Kết quả chuẩn:**

```text
01 - main started
02 - demo.Target
03 - same Class: true
04 - same Class: true
05 - before active use
06 - Target initialized
07 - Target.hello()
08 - main ended
```

Giải thích từng quan sát:

1. `Target.class` trả về đối tượng `Class` cho `demo.Target` nhưng **không bắt buộc khởi tạo** `Target`. VM có quyền nạp/liên kết trước thời điểm chương trình quan sát được.
2. `loader.loadClass("demo.Target")` tìm/trả về lớp qua loader, **thông thường không khởi tạo** nó. Do cả hai tham chiếu đến cùng lớp do cùng loader định nghĩa, phép so sánh `==` là `true`.
3. `Class.forName("demo.Target", false, loader)` yêu cầu tìm lớp nhưng **`initialize=false`**, nên cũng chưa chạy khối `static`.
4. Gọi phương thức static `Target.hello()` là **active use** làm JVM khởi tạo `Target` trước khi thân phương thức chạy: in `06` rồi `07`. Khởi tạo lớp chỉ diễn ra một lần đối với lớp đó trong loader đó.
5. `App` đã phải được JVM khởi tạo để chạy `main` của nó. Các thao tác với `Target` trong ví dụ không cho phép suy luận rằng mọi lớp được tham chiếu trong chương trình đều khởi tạo cùng lúc.

Đổi thử `Class.forName("demo.Target", false, loader)` thành `Class.forName("demo.Target", true, loader)`, rồi biên dịch/chạy lại trong tiến trình JVM mới: dòng `06` sẽ xuất hiện **trước dòng `04`**. Tham số thứ hai đã kích hoạt việc khởi tạo. Nếu gọi `Class.forName(String)`, mặc định nó yêu cầu khởi tạo và dùng loader của lớp gọi theo hợp đồng của API.

Để nhìn vào bytecode và metadata, chạy:

```sh
javap -classpath out -c -p demo.App
javap -classpath out -verbose demo.Target
```

Trong output `javap -c` của `App`, có thể tìm các lệnh như `ldc` (lấy class literal), `invokevirtual`, `invokestatic`; `-verbose` của `Target` cho biết `major version: 61` vì ta biên dịch với `--release 17`. `javap` **giải mã class file** để người đọc quan sát, không phải công cụ chứng minh một lớp đã được JVM nạp khi ứng dụng chạy.

> **Điểm mấu chốt:** Có `.class` không có nghĩa lớp đã được nạp; được nạp không đồng nghĩa đã khởi tạo; khởi tạo lớp cũng không đồng nghĩa có instance của lớp đó.

## 3. Loading: JVM lấy lớp từ đâu?

Khi JVM cần lớp `demo.Target`, một loader phù hợp được dùng để tìm dữ liệu nhị phân, kiểm tra yêu cầu định nghĩa lớp và tạo biểu diễn runtime của lớp. Với loader Java tự viết, đường đi thường là `loadClass` → ủy quyền cho parent → `findClass` → đọc bytes → `defineClass`. Đây là mẫu **parent delegation** phổ biến, không phải quy tắc rằng mọi loader phải tải tệp từ đĩa hay dùng đúng thuật toán đó.

Các loader cơ bản trong JDK 17+:

- **Bootstrap loader**: nạp các lớp cốt lõi của nền tảng; Java biểu diễn loader này bằng `null` trong `Class.getClassLoader()`, nhưng `null` không có nghĩa lớp không được nạp.
- **Platform loader**: phục vụ nhiều lớp/module của nền tảng; lấy qua `ClassLoader.getPlatformClassLoader()`.
- **Application/System loader**: thường nạp lớp của ứng dụng từ classpath và các module ứng dụng phù hợp; lấy qua `ClassLoader.getSystemClassLoader()`.
- **Custom loader**: có thể nạp plugin, class bytes do hệ thống phát sinh, hoặc classpath cách ly theo yêu cầu.

Phác họa cách ủy quyền thông thường:

```text
Application / Custom loader
         |
         | hỏi parent trước (nếu loader theo parent-first)
         v
     Platform loader
         |
         v
   Bootstrap loader
         |
    nếu parent không tìm thấy, loader con tự tìm
```

**Parent loader** không đồng nghĩa **parent Java class** (từ khóa `extends`); đó là hai quan hệ khác nhau. Một custom loader có thể dùng child-first theo thiết kế và các loader hỗ trợ Java Platform Module System có cơ chế tra cứu phức tạp hơn sơ đồ trên. Không nên giả định rằng mọi lớp đi qua đúng một chuỗi ủy quyền đơn giản.

### Classpath, JAR, module path có tác động thế nào?

Ở ví dụ A, `java -cp out demo.App` đặt `out` lên classpath. Application loader có thể tìm `demo/App.class` và `demo/Target.class` theo tên nhị phân. Với JAR, có thể dùng `java -cp app.jar demo.App` nếu JAR chứa các entry phù hợp. Với named module, `--module-path` và việc resolve module quyết định module nào có thể được nhìn thấy, cùng với các ràng buộc readability/exports; không thể quy giản toàn bộ thành việc thêm đường dẫn vào `-cp`.

Nếu file không tồn tại tại vị trí loader đang tìm, nếu một dependency vắng mặt, hoặc nếu module không đọc/export package cần thiết, mã nguồn biên dịch trước đó vẫn có thể gặp lỗi khi chạy trong môi trường khác.

## 4. Linking: biến bytes thành lớp có thể sử dụng an toàn

Theo Java Virtual Machine Specification, **linking** gồm ba phần:

**Verification — xác minh:** Kiểm tra class file có cấu trúc hợp lệ và các ràng buộc kiểu của bytecode được tôn trọng. Tệp `.class` bị sửa lỗi, bytecode không hợp lệ hoặc sự không nhất quán nhất định có thể gây `VerifyError` hoặc lỗi định dạng class.

**Preparation — chuẩn bị:** JVM cấp phát và đặt **giá trị mặc định** cho các `static` fields của lớp trong cấu trúc quản lý phù hợp. Ví dụ `static int count = 5`: tại preparation, giá trị khởi đầu mặc định là `0`; đoạn gán `5` thông thường được thực hiện lúc initialization. Trường `static final` là **constant variable** có `ConstantValue` attribute có thể được gán giá trị hằng ngay ở preparation, nên không dùng quy tắc `0` cho mọi trường hợp.

**Resolution — phân giải:** JVM thay các tham chiếu tượng trưng trong constant pool bằng các tham chiếu runtime thích hợp khi cần, kiểm tra sự tồn tại và khả năng truy cập của class, field, method liên quan. Resolution có thể xảy ra **theo nhu cầu**; lỗi thiếu dependency hoặc sai chữ ký API có thể xuất hiện muộn khi lệnh liên quan được thực thi.

Trình tự ràng buộc: lớp phải được **verified và prepared trước khi initialization**; resolution có thể được thực hiện linh hoạt. Một số lớp phụ thuộc có thể được nạp trước để phục vụ việc xác minh hoặc phân giải mà chưa nhất thiết đã initialized.

Các khái niệm này không thay thế cho **compile-time linking** của công cụ native. Java class file giữ nhiều symbolic references để JVM giải quyết ở runtime.

## 5. Initialization: khi nào `static` thực sự chạy?

Initialization thực thi phương thức đặc biệt `<clinit>` do compiler/JVM tổng hợp từ các initializer của trường static và khối `static { ... }` theo thứ tự nguồn, nếu lớp cần đoạn mã này. Trước khi khởi tạo lớp con, JVM phải khởi tạo lớp cha thích hợp; với interface, quy tắc khởi tạo liên quan khác với class.

Những thao tác thường làm phát sinh yêu cầu khởi tạo lớp:

- Tạo instance bằng `new Target()`.
- Gọi static method được khai báo bởi lớp, như `Target.hello()`.
- Đọc/ghi static field được khai báo bởi lớp, trừ một số trường hợp **constant variable** được compiler inlining.
- Gọi API reflection có cờ khởi tạo `true`, hoặc một số thao tác reflection thực hiện active use.
- JVM khởi tạo lớp chứa `main` trước khi chạy phương thức `main`.

Những thao tác **không tự chúng đòi hỏi khởi tạo** `Target`: lấy `Target.class`, đọc class name từ `Class`, `ClassLoader.loadClass("demo.Target")`, và `Class.forName("demo.Target", false, loader)`. JVM vẫn có thể chuẩn bị/nạp sớm để tối ưu nhưng không được làm lộ side effect initialization trước thời điểm ngôn ngữ cho phép.

Ví dụ về **hằng biên dịch**:

```java
package demo;

public class Constants {
    public static final int PORT = 8080; // constant variable
    public static final Integer BOXED_PORT = 8080; // không phải constant variable
    static {
        System.out.println("Constants initialized");
    }
}
```

Một class khác đọc `Constants.PORT` có thể nhận giá trị đã inline mà **không kích hoạt `Constants` initialization**. Ngược lại, đọc `Constants.BOXED_PORT` làm phát sinh active use và khởi tạo. Thí nghiệm này cần đặt phần đọc ở lớp khác và chạy một tiến trình JVM mới, vì một lớp chỉ initialized một lần trong phạm vi định nghĩa của nó. Việc thay đổi giá trị constant trong một thư viện mà không biên dịch lại consumer có thể khiến consumer giữ giá trị cũ.

Nếu `<clinit>` ném exception, lần đầu truy cập có thể nhận `ExceptionInInitializerError` (tùy loại lỗi); lớp đó có thể chuyển sang trạng thái khởi tạo thất bại và các lần sử dụng tiếp theo thường gặp `NoClassDefFoundError` với thông tin rằng lớp không thể được initialized. Nạp và liên kết thành công không bảo đảm logic khởi tạo thành công.

## 6. "Một lớp đang tồn tại trong JVM" chính xác là gì?

JVM định nghĩa danh tính runtime của một reference class/interface bằng cặp **(binary name, defining class loader)**. Hai loader khác nhau có thể định nghĩa hai lớp có **cùng tên**, từ những bytes giống hệt nhau, nhưng JVM coi là **hai kiểu khác nhau**. Vì vậy thông báo lỗi cast đôi khi trông kỳ lạ: `demo.Plugin cannot be cast to demo.Plugin`, do hai vế cùng tên nhưng do loader khác nhau định nghĩa.

Có hai vai trò phải tách bạch:

- **Initiating loader**: loader được yêu cầu tải lớp và có thể ủy quyền.
- **Defining loader**: loader thực sự định nghĩa lớp. Ví dụ loader con yêu cầu `java.lang.String` nhưng parent/bootstrap định nghĩa nó; defining loader của `String` là bootstrap.

Lớp runtime có metadata (tên, cha, interfaces, fields, methods, constant pool runtime...) và có đối tượng phản chiếu `Class<?>` tương ứng. **Method area** là vùng bộ nhớ logic được JVM Specification mô tả; **Metaspace** là chi tiết hiện thực của HotSpot cho phần lớn class metadata, còn đối tượng `java.lang.Class` là một Java object. Không đồng nhất mọi metadata với heap của instance, cũng không khẳng định mọi JVM dùng Metaspace.

**Loading ≠ initialization ≠ instantiation**:

- Loading: JVM có định nghĩa runtime của lớp.
- Initialization: static initialization của lớp hoàn thành (hoặc thất bại), theo quy tắc riêng.
- Instantiation: tạo **một** object cụ thể của lớp; có thể tạo nhiều object, hoặc không object nào.

Lớp có thể trở nên **có thể dỡ tải (unload)** khi defining loader và các class/object liên quan không còn được tham chiếu đủ để giữ sống. Việc dỡ tải do GC/runtime quyết định, không xảy ra bảo đảm ngay khi gọi `URLClassLoader.close()` hoặc gán biến `null`. JDK có thêm hidden classes và class generated at runtime; chúng có quy tắc riêng, vì thế đường đi từ file trên đĩa không phải con đường duy nhất.

### Bài thực hành B — cùng tên nhưng khác defining loader

Tạo thêm hai tệp cùng package `demo` trong `src/demo/` (giữ nguyên hai tệp của bài A):

**`src/demo/Plugin.java`**

```java
package demo;

public class Plugin {
    public String message() {
        return "hello plugin";
    }
}
```

**`src/demo/LoaderIdentityDemo.java`**

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderIdentityDemo {
    public static void main(String[] args) throws Exception {
        URL classesDir = Path.of("out").toAbsolutePath().toUri().toURL();

        try (URLClassLoader left = new URLClassLoader(new URL[] {classesDir}, null);
             URLClassLoader right = new URLClassLoader(new URL[] {classesDir}, null)) {

            Class<?> a = left.loadClass("demo.Plugin");
            Class<?> b = right.loadClass("demo.Plugin");

            System.out.println("same name: " + a.getName().equals(b.getName()));
            System.out.println("same Class: " + (a == b));
            System.out.println("assignable: " + a.isAssignableFrom(b));
        }
    }
}
```

Biên dịch và chạy **từ thư mục `project`**:

```sh
javac --release 17 -d out src/demo/Plugin.java src/demo/LoaderIdentityDemo.java
java -cp out demo.LoaderIdentityDemo
```

**Stdout chính xác:**

```text
same name: true
same Class: false
assignable: false
```

Ở đây hai `URLClassLoader` khác nhau đều có `parent=null` (ủy quyền về bootstrap khi thích hợp), tự định nghĩa `demo.Plugin` từ cùng thư mục `out`. Dù tên và bytecode giống nhau, `a` khác `b` vì defining loader khác. Đường dẫn `Path.of("out")` cố ý phụ thuộc thư mục chạy lệnh; chạy từ thư mục khác phải điều chỉnh đường dẫn. Đây là minh họa về **type identity**, không phải lời khuyên dùng parent `null` cho plugin production: mô hình cách ly thực tế cần cân nhắc API chia sẻ, quyền truy cập module, tài nguyên và vòng đời loader.

Nếu chuyển thành hai loader có parent là application loader và vẫn giữ `Plugin` trên classpath, quy tắc parent-first có thể khiến chúng ủy quyền để nhận lại **cùng** `demo.Plugin`. Đây là lý do phải xác định **defining loader** trước khi kết luận lớp nào được nạp từ file nào.

## 7. JVM thực thi bytecode sau khi nạp ra sao?

`Class` metadata và bytecode hợp lệ cho phép JVM xác định phương thức khi được gọi. Runtime có thể dùng **interpreter** để diễn giải bytecode và **JIT compiler** để biên dịch các đoạn nóng thành machine code. Điều này diễn ra sau/đan xen với nhu cầu sử dụng lớp; không đồng nghĩa toàn bộ class file được JIT ngay lúc loading. Optimizer có thể inline hoặc thay đổi cách thực thi nhưng phải duy trì hành vi Java được yêu cầu.

Một phương thức được gọi từ ứng dụng vẫn có thể làm phát sinh việc nạp/liên kết các lớp khác trong lúc chạy, do tham chiếu tới chúng chỉ vừa được sử dụng. Vì vậy biểu đồ đầu bài chỉ là **khung khái niệm**, chứ không phải toàn bộ các class của một ứng dụng sẽ cùng đi qua loading rồi linking rồi initialization ngay tại `main`.

Để khảo sát các sự kiện loading trên HotSpot hiện đại, có thể chạy:

```sh
java -Xlog:class+load=info -cp out demo.App
```

Đây là flag logging của HotSpot/JDK hỗ trợ Unified Logging; kết quả dài và phụ thuộc phiên bản JDK, classpath và môi trường. Dùng log để xem nguồn lớp và thời điểm có sự kiện nạp, **không** suy ra thời điểm initialization chỉ từ một dòng log loading.

## 8. Phân biệt lỗi theo giai đoạn

| Triệu chứng | Thường gắn với | Cần kiểm tra |
| --- | --- | --- |
| `javac: cannot find symbol` / `package ... does not exist` | Biên dịch | Import, tên kiểu, compile classpath/module path. |
| `ClassNotFoundException` | Tra cứu qua `loadClass` / `Class.forName` không tìm được tên yêu cầu | Binary name, JAR/classpath/module path, initiating loader. |
| `NoClassDefFoundError` | JVM cần định nghĩa/sử dụng class nhưng không tìm được hoặc lớp đã thất bại initialization trước đó | Dependency runtime, nested cause, class initializer trước đó. |
| `UnsupportedClassVersionError` | Class file mới hơn khả năng hỗ trợ của JVM | Phiên bản JDK chạy so với `javap -verbose` major version. |
| `ClassFormatError` / `VerifyError` | Định dạng class/kiểm tra bytecode | Tool sinh bytecode, bản build, thao tác sửa class. |
| `NoSuchMethodError` / `NoSuchFieldError` | Runtime resolution không khớp API từng biên dịch | Version JAR thực tế, dependency conflict, binary compatibility. |
| `ExceptionInInitializerError` | Static initialization có lỗi | Stacktrace nguyên nhân ở `<clinit>`, thứ tự gán static, side effects. |
| `ClassCastException` với cùng tên lớp ở hai vế | Hai định nghĩa lớp với defining loader khác nhau | Log loader, `getClassLoader()`, phiên bản plugin và shared API. |

Đây là **dấu hiệu định hướng**, không phải bảng ánh xạ 1–1 cho mọi tình huống. Đọc cả `Caused by` và ngữ cảnh lỗi; các lỗi thuộc họ `LinkageError` có thể xảy ra khi tham chiếu được dùng lần đầu, thay vì ngay khi chạy lệnh `java`.

Một checklist chẩn đoán ngắn: (1) xem **binary name** và nơi chứa `.class`, (2) xác minh JDK phiên bản biên dịch/chạy, (3) xác minh runtime classpath/module path thực tế, (4) xác minh **initiating/defining loader**, (5) xác định lỗi trước hay trong initialization, (6) đối chiếu dependency versions và stacktrace. `getClassLoader()` trả `null` cho bootstrap là điều bình thường.

## 9. Tự kiểm tra hiểu bài

1. **Có `out/demo/Target.class` trên đĩa thì `Target` đã ở trong JVM chưa?** Chưa chắc. Class file là tài nguyên, phải có nhu cầu/hoạt động loading để lớp runtime được định nghĩa.
2. **`Target.class` và `new Target()` có giống nhau?** Không. Biểu thức thứ nhất lấy `Class<?>` và không tự yêu cầu initialization; biểu thức thứ hai tạo instance và đòi hỏi initialization của lớp phù hợp trước.
3. **Vì sao `loadClass` tìm thấy `Target` mà khối `static` chưa in?** Loading và initialization là hai giai đoạn khác nhau; `loadClass(String)` thông thường không yêu cầu initialization.
4. **Tại sao cùng `demo.Plugin` có thể không cast được?** Runtime type identity còn chứa defining loader, ngoài binary name.
5. **Resolution có buộc xảy ra tất cả trước khi chạy `main`?** Không. JVM có thể phân giải tham chiếu theo nhu cầu; kiểm tra được yêu cầu của từng giai đoạn phải vẫn đúng.
6. **JVM chỉ dùng interpreter?** Không. HotSpot và nhiều implementation kết hợp interpreter/JIT; cách tối ưu không đổi semantics.
7. **Đóng `URLClassLoader` có lập tức unload các lớp?** Không. Close giải phóng tài nguyên mở bởi loader; unload còn phụ thuộc reachability và GC.

## 10. Ghi nhớ để đi tiếp trong chủ đề ClassLoader

Hãy luôn trả lời riêng bốn câu khi phân tích một lớp Java: **(1) Dữ liệu class đến từ đâu? (2) Loader nào định nghĩa? (3) Lớp đã verified/prepared/resolved tới mức nào? (4) Lớp đã initialized hay chưa?** Sau đó mới hỏi có instance nào, phương thức nào được thực thi và có JIT hay không.

Chuỗi chuẩn để nhớ là **source → compilation → class-file bytes → loading → linking → initialization khi active use → thực thi/instance theo nhu cầu**. Trên thực tế loading và resolution của nhiều lớp có thể đan xen, và một binary name có thể tương ứng nhiều runtime types qua nhiều defining loaders. Đây chính là điểm nối từ kiến thức về class file sang kiến trúc parent delegation, custom loader, plugin isolation và các lỗi classpath trong ứng dụng Java.
