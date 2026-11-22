# Quan hệ cha và phạm vi lớp mà mỗi loader phụ trách

Trong Java, **class loader** nhận yêu cầu tìm một kiểu theo tên nhị phân, có thể chuyển yêu cầu lên **parent loader** hoặc tự tìm bytecode để định nghĩa kiểu. Trên Java 17+, hệ thống thường có ba tầng loader tích hợp: **bootstrap**, **platform** và **application/system**. Việc hiểu quan hệ cha và phạm vi trách nhiệm của từng tầng giúp giải thích vì sao `java.lang.String` và class tự viết có loader khác nhau, tại sao loader con thường dùng được lớp do loader cha định nghĩa, và vì sao hai class trùng tên đôi khi không ép kiểu được cho nhau.

Bài học thuộc nhóm **Loader tích hợp** của Java core – classloader. Trọng tâm là: xác định **ai là parent**, **ai thực sự định nghĩa class**, **mỗi loader tìm lớp ở đâu**, các ngoại lệ của mô hình delegation và cách kiểm tra bằng Java 17+.

## 1. Ba loader tích hợp và sơ đồ quan hệ cha

Trong cấu hình khởi chạy Java SE thông thường, sơ đồ parent delegation có thể hình dung như sau:

```text
Bootstrap class loader  [tích hợp trong JVM; thường biểu diễn bằng null]
          ↑ parent của
Platform class loader   [ClassLoader.getPlatformClassLoader()]
          ↑ parent của
Application/system      [ClassLoader.getSystemClassLoader()]
          ↑ parent của
Custom class loader     [nếu bạn tạo với parent = system loader]
```

Mũi tên ở đây biểu thị **quan hệ parent để hỏi tìm class**, không phải quan hệ kế thừa `extends`, không biểu thị loader nào tạo instance loader khác và cũng không khẳng định mọi yêu cầu luôn đi đúng tuyến này.

| Loader | Cách lấy/nhận biết | Trách nhiệm điển hình | Parent |
| --- | --- | --- | --- |
| **Bootstrap** | Thường quan sát là `null` qua `SomeCoreClass.class.getClassLoader()`; không có một instance `ClassLoader` Java thông thường để giữ | Định nghĩa các lớp trong một số module nền tảng quan trọng, ví dụ phần cốt lõi `java.base` | Không có |
| **Platform** | `ClassLoader.getPlatformClassLoader()` | Các lớp nền tảng Java SE và JDK được phân cho platform loader hoặc loader tổ tiên | Trong cấu hình chuẩn, chuyển yêu cầu tới bootstrap |
| **Application / system** | `ClassLoader.getSystemClassLoader()` | Lớp ứng dụng trên application class path, application module path và các lớp/công cụ JDK thích hợp | Platform (hoặc một loader tổ tiên tương đương trong cấu hình tích hợp) |
| **Custom loader** | Instance do chương trình/framework tạo, ví dụ `new URLClassLoader(urls, parent)` | Plugin, mã tải động, vùng namespace riêng hoặc nguồn bytecode khác | Do ứng dụng chọn; mặc định constructor `ClassLoader()` lấy system loader làm parent |

**Bootstrap không đồng nghĩa platform.** Từ Java 9, hệ thống module thay đổi cách phân phối các lớp JDK: bootstrap xác định một số module nền tảng, trong khi platform và system định nghĩa/khởi đầu nhiều class của các module khác. Tránh ghi nhớ quy tắc cũ “bootstrap tải tất cả `java.*`, extension tải `javax.*`, app tải phần còn lại”: tên package không phải bảng phân quyền chính xác.

Trong Java 8 và cũ hơn thường gặp thuật ngữ **extension class loader** và `jre/lib/ext`. Từ Java 9 trở đi, extension mechanism đã bị loại bỏ, thay bằng **platform class loader** trong phân chia loader tích hợp. Không dùng `ExtClassLoader` hay `rt.jar` như giả định kiến trúc của Java 17+.

## 2. Parent loader là gì và có phải là nơi chứa class không?

Mỗi `ClassLoader` có thể tham chiếu tới một **parent loader** để ủy quyền yêu cầu nạp lớp. API `getParent()` trả quan hệ delegation được cấu hình, không phải “loader đã tạo ra object này”. Loader con có thể hỏi cha trước để tránh định nghĩa lại các lớp cha đã cung cấp.

Ba khái niệm cần tách bạch:

1. **Requesting loader:** loader mà ứng dụng hoặc JVM gọi để yêu cầu class, ví dụ `child.loadClass("java.lang.String")`.
2. **Defining loader:** loader thực sự tạo định nghĩa class bằng dữ liệu class tương ứng (thường qua `defineClass`), hoặc bootstrap do JVM phụ trách. Xem bằng `SomeType.class.getClassLoader()`.
3. **Initiating loader:** loader mà JVM ghi nhận đã khởi đầu quá trình loading cho tên class đó; loader con có thể là initiating loader dù class được parent định nghĩa.

Nếu gọi `child.loadClass("java.lang.String")` trong mô hình parent-first, parent có thể trả lại cùng `Class<String>` do bootstrap định nghĩa. **Kết quả trả về không đồng nghĩa child đã định nghĩa `String`.** Gọi `getClassLoader()` trên class trả về mới cho biết defining loader trong biểu diễn Java.

Một lớp Java được nhận diện về mặt runtime bằng **tên nhị phân + defining class loader**, chứ không phải chỉ tên. Hai loader khác nhau có thể định nghĩa hai class cùng tên `com.example.Plugin` nhưng đó là **hai kiểu độc lập**; cast có thể thất bại. Trái lại, nếu hai loader con cùng delegate đến một định nghĩa do parent cung cấp, cả hai có thể nhận **cùng đối tượng `Class<?>`**.

### Parent của một loader có thể là `null`

`ClassLoader.getParent() == null` thường biểu diễn parent bootstrap vì bootstrap không phải instance `ClassLoader` thông thường. Điều đó **không có nghĩa** loader đang xét chính là bootstrap. Ví dụ platform loader trong cấu hình chuẩn có thể có `getParent() == null`, nhưng bản thân platform loader vẫn là object `ClassLoader` riêng.

Khi tự tạo `new URLClassLoader(urls, null)`, `null` có nghĩa delegate tới bootstrap, **không phải vô hiệu hóa toàn bộ delegation**. Lưu ý từ JDK 9: bootstrap không cung cấp tất cả platform classes, nên custom loader có parent `null` có thể không thấy các API vốn được platform loader định nghĩa; nếu plugin cần các API ấy, cân nhắc đặt parent là `ClassLoader.getPlatformClassLoader()` hoặc system loader theo kiến trúc mong muốn.

## 3. Phạm vi thực tế của từng loader

### 3.1 Bootstrap: nền tảng tối thiểu để JVM vận hành

Bootstrap do JVM cung cấp. Nó định nghĩa các class cốt lõi như `java.lang.Object`, `java.lang.String` và `java.lang.Class` trong các module nền tảng liên quan. Với các kiểu thông dụng này:

```java
System.out.println(String.class.getClassLoader() == null);
System.out.println(Object.class.getClassLoader() == null);
```

Đây là **đoạn minh họa hai lệnh**, cần đặt trong method chạy được. Ở Java SE 17 thông thường, cả hai dòng in `true`. Đừng viết `ClassLoader bootstrap = String.class.getClassLoader(); bootstrap.loadClass(...)`: biến `bootstrap` có giá trị `null`, gọi method sẽ gây `NullPointerException`.

Giới hạn cần hiểu:

- Bootstrap không mặc nhiên nạp từng file người dùng hay mọi class trong JDK.
- Một custom loader có parent bootstrap không chắc truy cập được tất cả platform APIs.
- Class được bootstrap định nghĩa thường có `Class.getClassLoader() == null`; cách biểu diễn này là một quy ước API, không cho phép thao tác trực tiếp với một đối tượng bootstrap.

### 3.2 Platform: phần nền tảng rộng hơn lớp bootstrap

Platform loader chịu trách nhiệm các **platform classes** mà runtime gán cho nó hoặc cho các loader tổ tiên. Platform classes có thể là Java SE API, class triển khai hoặc các lớp JDK đặc thù. API trả loader này là:

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
```

Platform không chỉ “tải tất cả thư viện ngoại vi”. Nhiều thư viện của người dùng nằm trên application class path và được application loader định nghĩa. Cũng không được suy định nghĩa chỉ từ tiền tố `java.`, `javax.` hay `jdk.`: hệ thống module và cấu hình runtime quyết định cách phân phối.

**Ngoại lệ delegation quan trọng:** tài liệu `ClassLoader` cho phép platform loader trong một số tình huống **upgraded modules** phải delegate sang loader khác, kể cả application loader, dù application không phải ancestor của platform. Vì thế sơ đồ parent ở đầu bài là **mô hình mặc định cho quan hệ cha**, không phải một định luật cứng rằng mọi lần tra cứu chỉ đi từ con lên cha mà không bao giờ có cạnh khác.

### 3.3 Application/system: điểm tựa mặc định của ứng dụng

`ClassLoader.getSystemClassLoader()` thường trả loader dùng để khởi động ứng dụng. Với cấu hình launcher mặc định, nó định nghĩa lớp từ **application class path** (`-cp`/`--class-path`) và những lớp/module phù hợp từ **application module path**. Trên JDK built-in, system loader thường có tên `"app"`.

Ví dụ lệnh chạy class path:

```bash
javac --release 17 Hello.java
java -cp . Hello
```

Nếu `Hello` là class đơn giản trong thư mục hiện tại và không có system loader tùy biến, `Hello.class.getClassLoader()` thường chính là `ClassLoader.getSystemClassLoader()`.

Phạm vi này có giới hạn:

- Một class không xuất hiện trên class path/module path thích hợp thường không được app loader tìm thấy.
- **Parent không biết tự động class do child định nghĩa**. Nếu plugin class chỉ do plugin loader định nghĩa, system loader không tự tìm được nó.
- System loader có thể được tùy biến qua thuộc tính `java.system.class.loader`. Vì vậy không khẳng định tên class implementation, chuỗi `toString()` hay thậm chí quan hệ trực tiếp với platform luôn cố định trong mọi ứng dụng.
- Class path và module path không phải một khối tương đương: named modules còn tuân theo module readability, exports và opens.

## 4. Chạy thử Java 17+: quan hệ cha và loader định nghĩa

Tạo file `LoaderRolesDemo.java`:

```java
public class LoaderRolesDemo {
    static class Sample {
    }

    public static void main(String[] args) throws ClassNotFoundException {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();
        ClassLoader sampleLoader = Sample.class.getClassLoader();

        System.out.println("String by bootstrap: "
                + (String.class.getClassLoader() == null));
        System.out.println("Platform parent bootstrap: "
                + (platform.getParent() == null));
        System.out.println("System parent platform: "
                + (system.getParent() == platform));
        System.out.println("Sample defined by system: "
                + (sampleLoader == system));

        Class<?> viaSystem = system.loadClass("java.lang.String");
        System.out.println("Same String class: "
                + (viaSystem == String.class));

        Class<?> viaPlatform = platform.loadClass("java.lang.String");
        System.out.println("Platform delegates String: "
                + (viaPlatform == String.class));
    }
}
```

Biên dịch/chạy bằng JDK 17+ trên class path, không đặt `java.system.class.loader`:

```bash
javac --release 17 LoaderRolesDemo.java
java -cp . LoaderRolesDemo
```

Trên JDK chuẩn với ba loader built-in và launcher mặc định, stdout dự kiến:

```text
String by bootstrap: true
Platform parent bootstrap: true
System parent platform: true
Sample defined by system: true
Same String class: true
Platform delegates String: true
```

Giải thích:

- `String` được bootstrap định nghĩa nên `getClassLoader()` trả `null`.
- `platform.getParent() == null` **không** có nghĩa platform là bootstrap; nó biểu diễn parent delegation tới bootstrap.
- `system.getParent() == platform` mô tả cạnh parent chuẩn giữa app và platform.
- `Sample` là một class được compile cùng chương trình và load từ class path hiện tại, vì vậy app/system là defining loader trong cấu hình nêu trên.
- Hai lời gọi `loadClass("java.lang.String")` vào system/platform cùng trả đối tượng `String.class`, vì các loader này delegate để dùng định nghĩa sẵn từ bootstrap.

Nếu chạy với một system loader tùy biến, sửa class path/module path hoặc đổi launcher/runtime, một số dòng đối chiếu có thể thay đổi. Điều chính yếu là kiểm tra **quan hệ và danh tính** bằng API, tránh học thuộc tên class implementation bên trong JDK.

### In chuỗi parent để chẩn đoán

Một đoạn util (đặt trong method Java) có thể duyệt từ system lên parent:

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();
while (loader != null) {
    System.out.println(loader.getName());
    loader = loader.getParent();
}
System.out.println("<bootstrap represented as null>");
```

Đây là **đoạn mã minh họa chèn vào method**, không phải một file chạy độc lập. Trên JDK tích hợp phổ biến, tên `app` và `platform` có thể xuất hiện, nhưng tên của custom loader có thể `null`; không suy đoán quyền hạn/chỗ lưu class chỉ dựa trên tên. Vòng lặp đi theo **parent chain** được cấu hình; nó không liệt kê mọi mối liên hệ module hay delegation phi cây.

## 5. Parent-first delegation hoạt động như thế nào?

`ClassLoader.loadClass(String)` gọi quá trình tìm class theo thuật toán mặc định của `loadClass(String, boolean)`:

1. **Đã tải chưa?** Dùng `findLoadedClass(name)` trong ngữ cảnh loader để tránh xử lý lại.
2. **Hỏi parent trước.** Gọi `parent.loadClass(name, false)`; nếu parent là `null`, dùng cơ chế bootstrap để tìm.
3. **Parent không tìm được:** loader hiện tại gọi `findClass(name)` để tự định nghĩa/lấy class từ nguồn nó quản lý.
4. **Nếu có yêu cầu resolve:** JVM liên kết qua `resolveClass`; bản thân `loadClass` không mặc nhiên khởi tạo static initializer.

Sơ đồ:

```text
child.loadClass("demo.Feature")
       |
       v
Đã load trước đó? ----- có ------> trả Class
       |
      chưa
       v
Hỏi parent.loadClass(...) --- tìm thấy --> trả Class của parent
       |
     không thấy
       v
child.findClass(...) ------- tìm thấy --> child định nghĩa Class
       |
   không thấy
       v
ClassNotFoundException
```

Đây là **default parent-first**, không phải yêu cầu tuyệt đối cho mọi loader tùy biến. Subclass có thể override `loadClass` để thực hiện chính sách khác, nhưng phải tuân thủ các ràng buộc JVM và xử lý các class quan trọng an toàn. Theo khuyến nghị API, đa số custom loader nên override `findClass`, giữ thuật toán `loadClass` mặc định khi không có lý do mạnh để thay.

Parent-first giúp tái sử dụng class nền tảng, tránh vô ý định nghĩa bản sao không tương thích và cho phép nhiều child dùng chung kiểu do parent cung cấp. Tuy nhiên nó không tự giải quyết version conflict: nếu parent đã thấy một dependency phiên bản cũ, child sẽ được trả class của parent theo thuật toán mặc định.

### Ví dụ chạy được: yêu cầu qua child nhưng định nghĩa ở parent

Tạo file `DelegationDemo.java`:

```java
public class DelegationDemo {
    static class ChildLoader extends ClassLoader {
        ChildLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            System.out.println("findClass: " + name);
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader child = new ChildLoader(
                ClassLoader.getSystemClassLoader());

        Class<?> core = child.loadClass("java.lang.String");
        System.out.println("String shared: "
                + (core == String.class));

        Class<?> local = child.loadClass("DelegationDemo");
        System.out.println("App class shared: "
                + (local == DelegationDemo.class));

        try {
            child.loadClass("demo.Missing");
        } catch (ClassNotFoundException expected) {
            System.out.println("Missing class");
        }
    }
}
```

```bash
javac --release 17 DelegationDemo.java
java -cp . DelegationDemo
```

Stdout:

```text
String shared: true
App class shared: true
findClass: demo.Missing
Missing class
```

Điểm mấu chốt:

- Child yêu cầu `String` nhưng bootstrap cung cấp định nghĩa: `findClass` của child **không được gọi**.
- Child yêu cầu `DelegationDemo` nhưng app/system loader đã định nghĩa class đó: child nhận **cùng `Class<?>`**.
- Với `demo.Missing`, parent không tìm thấy, child mới thử `findClass` rồi báo `ClassNotFoundException`.
- Ví dụ cố ý không tạo bytecode cho class thiếu; mục tiêu là quan sát **thứ tự delegation**, không mô phỏng plugin loader hoàn chỉnh.

Nếu muốn child tự định nghĩa class, phải cung cấp bytecode hợp lệ và gọi `defineClass(...)` trong `findClass`; cần bảo đảm quan hệ loader, package, module, visibility và vòng đời phù hợp. Không được tùy ý định nghĩa các class trong namespace cấm như `java.*`, và không nên phá parent-first chỉ để né dependency clash mà chưa phân tích danh tính kiểu.

## 6. Quan hệ loader không phải quan hệ kế thừa class Java

Nhầm lẫn thường gặp:

- `class P extends ClassLoader` chỉ nói **P là một loại loader** trong hệ thống class của Java.
- `new P(parent)` chỉ nói **instance P này sẽ hỏi parent nào** khi delegate, nếu code constructor và override tuân theo tham số đó.
- `MyService extends BaseService` là quan hệ kế thừa của **hai class ứng dụng**. `MyService` và `BaseService` có thể được định nghĩa bởi loader khác nhau, miễn JVM có thể resolve và áp dụng đúng các ràng buộc.
- Loader của một class không nhất thiết là loader của mọi class mà nó tham chiếu. JVM có thể dùng loader của class đang tham chiếu để yêu cầu kiểu phụ thuộc rồi nhận về định nghĩa từ parent.

Một parent loader không tự nhiên có quyền tìm thấy class mà child đã định nghĩa. Quan hệ delegation thông thường là **child hỏi parent trước**, không phải mọi loader đều chia sẻ chung một kho class vô hạn. Nếu một framework cần nạp plugin do child định nghĩa, framework phải biết cách nhận được plugin loader hoặc giao cho một cơ chế discovery phù hợp.

## 7. Phạm vi lớp, module và class path là ba khái niệm khác nhau

Trên Java 17, loader tích hợp hoạt động cùng **Java Platform Module System (JPMS)**:

- **Class path:** mã chạy theo cơ chế class path thường thuộc **unnamed module** của loader tương ứng. Application loader là nơi phổ biến định nghĩa class ứng dụng từ `-cp`.
- **Module path:** các named modules được runtime xác định, resolve và gắn với loader theo cơ chế module system; không suy ra rằng “cứ named module là platform loader” hoặc “cứ module người dùng là một loader riêng”.
- **Module readability:** module có thể đọc module nào liên quan tới phụ thuộc tĩnh/động của module.
- **Exports/opens:** quyết định truy cập API và reflection tới package theo quy tắc module. Class có thể **được nạp** mà code khác vẫn bị chặn truy cập thành viên do module encapsulation.
- **Resource lookup:** `getResource` hoặc `getResources` còn bị ảnh hưởng bởi path, thứ tự tìm và cơ chế đóng gói/module. Việc biết một class load được không đảm bảo tìm được mọi resource cùng package theo đúng cách cũ.

**Phạm vi loader trả lời câu hỏi “bộ định nghĩa class nào được thấy/khởi đầu theo yêu cầu?”**; **module boundary trả lời thêm “code nào được quyền đọc, truy cập và phản chiếu?”**. Hai kiểm tra có thể liên quan nhưng không thay thế nhau.

Một class có thể thuộc một named module nhưng lại được platform hoặc app loader định nghĩa tùy module và runtime. Khi cần biết thực tế, kiểm tra trực tiếp:

```java
Class<?> type = java.util.ArrayList.class;
System.out.println(type.getModule().getName());
System.out.println(type.getClassLoader());
```

Đây là **mã minh họa chèn trong một method**. `getModule().getName()` cho biết module của class; `getClassLoader()` cho biết defining loader. Không đoán loader bằng cách nhìn tên module.

### Khi nào chọn parent bootstrap, platform hay app cho custom loader?

| Mục tiêu | Parent thường cân nhắc | Đánh đổi |
| --- | --- | --- |
| Plugin cần API Java SE mở rộng và không muốn tự thấy toàn bộ app | **Platform loader** | Vẫn phải tổ chức API chung, module visibility và phụ thuộc bổ sung |
| Plugin cần interface/API do chính ứng dụng khai báo | **System loader** hoặc loader đã định nghĩa API chung | Giúp plugin nhận cùng định nghĩa interface; có thể bị ảnh hưởng bởi version của dependency ở parent |
| Loader cách ly tối đa, chỉ dựa một số class nền tảng bootstrap | Parent `null` | Không được bảo đảm thấy mọi platform class; chi phí quản lý phụ thuộc cao |
| Framework có hệ sinh thái loader riêng | Parent do framework hợp đồng hóa | Cần kiểm tra contract/framework vì parent-first/child-first có thể biến đổi |

Chọn parent dựa vào **những kiểu phải dùng chung**, nguồn class cần truy cập và policy xung đột phiên bản. Đừng dùng `null` chỉ vì muốn “bảo mật hơn” hoặc muốn làm loader nhẹ hơn; class loader isolation tự nó không phải security boundary đầy đủ.

## 8. Thread context class loader khác loader định nghĩa class hiện tại

Có một khái niệm khác dễ nhầm với parent: **thread context class loader (TCCL)**.

```java
ClassLoader context = Thread.currentThread()
        .getContextClassLoader();
ClassLoader defining = MyType.class.getClassLoader();
```

Đây là **đoạn minh họa**, giả định có `MyType`. `context` do thread giữ để framework/service discovery chọn nguồn class hoặc resource. `defining` là loader đã định nghĩa `MyType`. Chúng có thể khác nhau và TCCL **không tự thay đổi** defining loader của class đã tồn tại.

Trong `main` của ứng dụng khởi chạy bình thường, context loader thường là system loader, nhưng executor, app server hoặc framework có thể gán khác. Một pattern an toàn khi tạm thay TCCL là:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Thực hiện thao tác discovery cần pluginLoader.
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây là **đoạn minh họa**, giả định `pluginLoader` đã tồn tại. Khôi phục context trong `finally` để công việc sau của cùng thread không vô tình nhìn namespace plugin. Trong môi trường có thread pool, giữ TCCL cũ sau request rất dễ gây rò rỉ tham chiếu tới plugin loader hoặc nạp nhầm class.

TCCL có thể cho framework mã hóa ở loader “cao hơn” tìm provider do loader “thấp hơn” quản lý, nhưng chỉ khi framework **chủ động dùng TCCL**. Nó không đảo ngược toàn bộ cơ chế parent delegation của mọi lớp.

## 9. Cùng tên nhưng khác loader: vì sao có lỗi ép kiểu?

Giả sử hai plugin loader độc lập đều định nghĩa tên nhị phân `demo.api.Task`:

```text
system loader -> định nghĩa demo.api.Task (nếu có API chung)
     |
     +--> PluginLoader A -> định nghĩa demo.impl.Service
     |
     +--> PluginLoader B -> định nghĩa demo.impl.Service
```

Hai `demo.impl.Service` có thể cùng bytecode nhưng là hai class khác nhau vì **defining loader khác nhau**. Không được coi object của A là instance của class B chỉ vì tên giống. Muốn chia sẻ object qua ranh giới plugin, cần **API/interface chung** do loader dùng chung (thường parent) định nghĩa, để code cả hai phía resolve về **cùng Class object** của hợp đồng API.

Nếu mỗi plugin định nghĩa riêng cả interface `demo.api.Task` thì tên interface giống nhau vẫn là hai kiểu không tương thích. Trong log, thông báo `ClassCastException` có thể hiển thị hai tên lớp giống nhau nhưng thêm định danh loader/module khác nhau. Khi điều tra, hãy in:

```java
System.out.println(instance.getClass().getName());
System.out.println(instance.getClass().getClassLoader());
System.out.println(instance.getClass().getModule());
```

Đây là **đoạn minh họa**, với `instance` là object đang điều tra. Cần kiểm tra bằng identity của `Class<?>`/`ClassLoader`, thay vì chỉ so `getName()` hoặc dựa hoàn toàn vào `toString()`.

## 10. Debug loader nào đang nạp và định nghĩa class

Có ba hướng kiểm tra bổ trợ nhau:

**A. Đọc metadata tại runtime**

```java
static void inspect(Class<?> type) {
    System.out.println("class=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
}
```

Đây là **method minh họa**, cần đặt trong class đang biên dịch. Nếu `getClassLoader()` trả `null`, đó là biểu diễn bootstrap của JVM. Nếu `getModule().getName()` là `null`, module không có tên (unnamed module).

**B. Xem dấu vết class loading trên HotSpot**

```bash
java -Xlog:class+load=info LoaderRolesDemo
```

Unified logging ở nhiều bản HotSpot in thông tin các class đã load và nguồn liên quan. Format, nguồn được báo và mức độ chi tiết phụ thuộc runtime; **log source không nhất thiết hiển thị đầy đủ defining loader**. Dùng nó để bổ trợ việc kiểm tra qua `Class.getClassLoader()` và cấu hình class path/module path. Trên runtime không hỗ trợ tùy chọn này, tham khảo flag logging tương đương của nhà cung cấp.

**C. Xem đường tìm class**

```bash
java -cp ".;libs/*" LoaderRolesDemo
```

Dấu chấm phẩy `;` trong ví dụ trên là **separator class path trên Windows**. Trên Linux/macOS dùng dấu hai chấm `:`: `java -cp ".:libs/*" LoaderRolesDemo`. Kiểm tra lỗi do JAR thiếu, trùng class hoặc version khác nhau trong class path là việc khác với việc đọc parent chain. Với named modules, xem thêm `--module-path`, `--add-reads`, `--add-exports` khi phù hợp để chẩn đoán quyền truy cập module; đừng sửa flag bừa bãi chỉ để làm lỗi biến mất.

### Phân biệt lỗi phổ biến

| Hiện tượng | Kiểm tra trước tiên |
| --- | --- |
| `ClassNotFoundException` từ `loadClass` hoặc `Class.forName` | Tên nhị phân, class path/module path thực tế, parent, custom `findClass`, source JAR |
| `NoClassDefFoundError` khi code tham chiếu class | Class/dependency runtime thiếu, lỗi linking hoặc một khởi tạo class trước đó đã thất bại; đọc `cause`/stack trace |
| `ClassCastException` giữa hai tên giống nhau | Có phải hai class do hai defining loaders khác nhau tạo? |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary compatibility của dependency được loader thật sự trả về; tên/descriptor của method/field |
| `IllegalAccessError` / `InaccessibleObjectException` | Access level, package/module readability, exports/opens, reflective access |
| `ServiceLoader` không tìm thấy provider | Context loader được dùng, module service declarations, file `META-INF/services`/cấu hình module, provider visibility |
| Plugin unload rồi nhưng loader vẫn sống | Object/thread/TCCL/static cache/stack đang giữ tham chiếu tới class, instance hoặc loader của plugin |

Một vài lưu ý chẩn đoán:

- `ClassNotFoundException` là checked exception thường gặp với API nạp lớp chủ động; `NoClassDefFoundError` là một linkage error, không luôn đồng nghĩa file vật lý vắng mặt.
- `ClassLoader.loadClass(String)` không mặc nhiên **initialize** class; `Class.forName(String)` overload một tham số yêu cầu initialization. Đây là khác biệt vòng đời, không phải khác biệt parent tree.
- Nếu dependency nằm ở parent với phiên bản không phù hợp, child parent-first thường nhận bản ở parent. Cần xử lý kiến trúc dependency/version thay vì mong Java chọn “JAR gần hơn” theo cảm tính.
- Không dùng kết quả `getResources()` như danh sách chính xác tất cả class một loader có thể định nghĩa, vì resource lookup có quy tắc khác class loading và có module encapsulation.

## 11. Tình huống thiết kế và quyết định phù hợp

**Tình huống A – ứng dụng Java đơn giản:** mã của bạn và dependency trên `-cp`. System loader định nghĩa đa số class ứng dụng, còn JDK core class thường tới từ bootstrap/platform. Thường không cần tự tạo custom loader.

**Tình huống B – plugin cùng sử dụng `PluginApi`:** đặt `PluginApi` vào classpath/module của **parent chung**, còn implementation của từng plugin để loader plugin định nghĩa. Khi host gọi method qua `PluginApi`, các bên cùng dùng một định nghĩa interface. Cẩn thận nếu host cũng đóng gói bản sao API bên trong JAR plugin, đặc biệt khi child-first.

**Tình huống C – plugin cần các API JDK rộng hơn bootstrap nhưng không cần thấy toàn bộ ứng dụng:** platform loader có thể phù hợp làm parent; dùng kiểm tra thực tế với module/service mà plugin cần. Nếu plugin phải cast sang interface của host, cần giải quyết việc chia sẻ defining loader của interface.

**Tình huống D – application server/container:** container có thể cung cấp loader tùy biến, có policy child-first cho một số thư viện và parent-first cho nền tảng. Không áp dụng máy móc cây loader của `java -cp . Main` cho toàn hệ thống; kiểm tra tài liệu framework và runtime objects.

**Tình huống E – plugin framework dùng TCCL:** provider do plugin loader định nghĩa nhưng discovery code ở lớp cha. Framework có thể chọn context loader để tìm provider. Cần đặt và khôi phục context tại phạm vi tác vụ, nhất là thread pool.

## 12. Kiến thức cần tự kiểm tra

**Câu 1.** `ClassLoader.getSystemClassLoader().loadClass("java.lang.String")` trả về `String.class`. Có thể kết luận system loader định nghĩa `String` không?

**Đáp án:** Không. Trong cấu hình JDK chuẩn, system loader delegate qua platform tới bootstrap; defining loader của `String` được biểu diễn bằng `null`. Loader nhận yêu cầu khác loader định nghĩa class.

**Câu 2.** `ClassLoader.getPlatformClassLoader().getParent() == null` có nghĩa platform loader là bootstrap loader không?

**Đáp án:** Không. Platform vẫn là instance `ClassLoader`; `null` ở đây biểu diễn bootstrap trong quan hệ parent.

**Câu 3.** Vì sao custom loader parent `null` không chắc tìm được mọi lớp API Java SE?

**Đáp án:** Nó chỉ delegate tới bootstrap theo cơ chế chuẩn. Từ Java 9, nhiều platform classes được định nghĩa ngoài bootstrap, nên parent `null` không đảm bảo toàn bộ nền tảng hiện diện.

**Câu 4.** PluginLoader A và B đều tìm `java.lang.String`. Vì sao `Class<?>` có thể giống nhau? Nhưng hai `demo.impl.Service` lại không thể cast qua nhau?

**Đáp án:** Cùng delegate tới một định nghĩa `String` của bootstrap nên nhận cùng `Class<?>`. Còn mỗi plugin có thể tự định nghĩa `Service`, tạo hai kiểu riêng do khác defining loader.

**Câu 5.** Khi nào `findClass` trong custom loader mặc định được gọi?

**Đáp án:** Sau khi `findLoadedClass` không trả class sẵn có và parent không tìm thấy class được yêu cầu. Nếu parent tìm ra class, mặc định không gọi `findClass` của child.

**Câu 6.** `getParent()`, `getContextClassLoader()` và `SomeClass.class.getClassLoader()` trả lời ba câu hỏi nào?

**Đáp án:** `getParent()`: loader nào được hỏi như parent. `getContextClassLoader()`: context loader hiện được thread giữ cho các API dùng nó. `Class.getClassLoader()`: defining loader của class (bootstrap có thể là `null`).

**Câu 7.** Chỉ cần class load được thì mọi module khác đều gọi reflection vào private member được?

**Đáp án:** Không. Loader visibility khác quyền truy cập Java/module; JPMS readability, exports và opens cùng cơ chế reflection còn áp dụng.

**Câu 8.** Muốn cùng một API interface dùng được giữa host và hai plugin độc lập, nên đặt định nghĩa interface ở đâu?

**Đáp án:** Trong nguồn được **loader chung** của host và plugin nhìn thấy, thường là parent/API loader; tránh để mỗi plugin tự định nghĩa bản sao riêng của cùng tên interface.

## Ghi nhớ thực hành

Để giải thích đúng một sự kiện nạp lớp, lần lượt hỏi:

1. **Tên nhị phân** của class đang được yêu cầu là gì?
2. **Ai nhận yêu cầu** và **parent** của loader ấy là ai?
3. Loader có **delegate parent-first** hay policy khác? Những nguồn class/module nào mỗi loader quản lý?
4. **Ai thực sự định nghĩa** class trả về (`Class.getClassLoader()`)?
5. Các class phải tương tác có dùng **cùng định nghĩa API** không, hay bị tách qua defining loaders?
6. Module readability/exports/opens, resource lookup và TCCL có ảnh hưởng tới việc đang làm không?

Đừng suy ra quyền truy cập class chỉ từ dấu `.` trong package hoặc tên JAR. **Quan hệ parent giải thích hướng ủy quyền; defining loader xác định danh tính runtime của kiểu; module và thread context bổ sung các quy tắc nhìn thấy/tìm kiếm cần thiết.**

Nguồn chuẩn để kiểm tra thêm:

- [Java SE 17 API – `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): ba loader built-in, parent, `loadClass`, `findClass` và các ngoại lệ delegation.
- [Java SE 17 API – `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader()` và `getModule()`.
- [JVM Specification 17 – §5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): danh tính kiểu, defining/initiating loader và liên kết.
