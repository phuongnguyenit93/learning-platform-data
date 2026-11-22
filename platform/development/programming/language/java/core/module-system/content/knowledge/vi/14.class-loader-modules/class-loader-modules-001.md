# ClassLoader của platform, application và module trong Java

Class loader là cơ chế JVM dùng để tìm và định nghĩa lớp khi chương trình cần đến lớp đó. Từ Java 9, Java Platform Module System (JPMS) bổ sung module để tổ chức package, khai báo phụ thuộc và giới hạn quyền truy cập. Hai cơ chế phối hợp với nhau: class loader nạp lớp, còn module xác định lớp thuộc đơn vị nào và module nào được phép truy cập package đã công bố.

Bài học này giải thích ba class loader tích hợp sẵn thường gặp — bootstrap, platform và application (system) — cùng cách chúng tham gia nạp named module, module layer và ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vai trò của bootstrap, platform và application class loader.
- Giải thích quan hệ parent-child giữa các loader tích hợp sẵn.
- Phân biệt classpath, module path, named module và unnamed module.
- Xác định class loader và module của một lớp bằng Java API.
- Giải thích vì sao hai lớp cùng tên vẫn có thể là hai kiểu runtime khác nhau.
- Nhận biết khi nào module layer hoặc class loader tùy chỉnh hữu ích cho hệ thống plugin.

## 2. Class loader trong quá trình nạp lớp

Khi JVM cần sử dụng một lớp, nó phải có định nghĩa lớp đó trong runtime. Vòng đời xử lý lớp thường được chia thành ba giai đoạn lớn:

1. **Loading:** tìm bytecode và tạo biểu diễn lớp trong JVM. Class loader tham gia trực tiếp vào giai đoạn này.
2. **Linking:** kiểm tra bytecode, chuẩn bị cấu trúc dữ liệu cần thiết và phân giải các tham chiếu khi cần.
3. **Initialization:** thực thi các bộ khởi tạo tĩnh và khối `static` theo quy tắc Java.

Class loader chịu trách nhiệm tìm và định nghĩa lớp; JVM thực hiện các bước linking và initialization theo quy tắc của nền tảng.

Một lớp có **defining class loader** — loader đã định nghĩa lớp đó. Danh tính runtime của lớp phụ thuộc cả tên đầy đủ (binary name) lẫn defining loader. Nếu hai loader riêng biệt cùng định nghĩa lớp `com.example.Plugin`, JVM xem chúng là hai kiểu khác nhau, dù tên lớp giống hệt nhau. Đây là nguyên tắc quan trọng khi phát triển plugin, máy chủ ứng dụng và framework có nhiều vùng nạp lớp.

## 3. Ba class loader tích hợp sẵn

Từ Java 9, cấu trúc phổ biến của các loader mặc định có thể hình dung như sau:

```text
Bootstrap Class Loader
        |
        v
Platform Class Loader
        |
        v
Application (System) Class Loader
        |
        v
Các class loader tùy chỉnh (nếu ứng dụng tạo)
```

Sơ đồ thể hiện quan hệ ủy quyền parent phổ biến. Loader tùy chỉnh có thể được nối vào cây theo thiết kế riêng; chúng không bắt buộc phải là con của application loader.

### 3.1. Bootstrap Class Loader

Bootstrap class loader là loader nền tảng thấp nhất của JVM, chịu trách nhiệm nạp các lớp cốt lõi cần để khởi động và vận hành Java runtime, ví dụ `java.lang.Object` và `java.lang.String`.

Đặc điểm:

- Được triển khai ở mức JVM/runtime, không phải một đối tượng `ClassLoader` Java thông thường mà ứng dụng có thể thao tác trực tiếp.
- Là parent gốc của platform class loader.
- Với lớp do bootstrap loader định nghĩa, `SomeClass.class.getClassLoader()` trả về `null`. Giá trị `null` ở đây biểu diễn bootstrap loader, không có nghĩa lớp chưa được nạp.
- Nhiều lớp cốt lõi thuộc các module nền tảng được bootstrap loader định nghĩa; không nên giả định mọi lớp trong JDK đều do bootstrap loader nạp.

### 3.2. Platform Class Loader

Platform class loader là loader cha của application/system class loader. Nó nạp các lớp thuộc nền tảng Java mà bootstrap loader không định nghĩa.

Lấy loader này bằng API công khai:

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
System.out.println(platform);
```

Đặc điểm:

- Có mặt từ Java 9.
- Parent của nó là bootstrap loader; vì bootstrap loader được biểu diễn bằng `null`, gọi `platform.getParent()` thường trả về `null`.
- Đảm nhiệm việc nạp các lớp nền tảng được giao cho platform loader, bao gồm nhiều lớp thuộc các module Java SE/JDK.
- Là parent của application loader trong cấu trúc mặc định.

Trước Java 9, Java có Extension Class Loader (thường gọi ExtClassLoader). Cơ chế extension đã được loại bỏ khi nền tảng chuyển sang module system; platform class loader đảm nhiệm vai trò loader cho các lớp nền tảng tương ứng. Khi đọc code hoặc tài liệu cũ, cần phân biệt tên và hành vi của hai thế hệ.

### 3.3. Application Class Loader (System Class Loader)

Application class loader thường được gọi là system class loader. Trong cấu hình Java tiêu chuẩn, đây là loader mặc định nạp lớp ứng dụng.

Lấy loader bằng:

```java
ClassLoader app = ClassLoader.getSystemClassLoader();
System.out.println(app);
System.out.println(app.getParent());
```

Đặc điểm:

- Parent mặc định là platform class loader.
- Nạp lớp ứng dụng từ classpath, ví dụ các đường dẫn truyền qua `-cp` hoặc `--class-path`.
- Cũng tham gia nạp các named module được phân công cho system/application loader trên module path.
- Có thể được thay bằng system class loader tùy chỉnh qua cấu hình runtime; vì vậy không nên mặc định mọi môi trường đều có cùng một lớp triển khai cụ thể.

Trong ứng dụng thông thường, `ClassLoader.getSystemClassLoader()` trả về application loader mặc định của tiến trình.

## 4. Parent delegation và tìm lớp

Các class loader tích hợp sẵn sử dụng mô hình ủy quyền cho parent: khi cần nạp một lớp, loader thường hỏi parent trước; nếu parent không tìm được, loader hiện tại mới tìm trong phạm vi mà nó quản lý. Mục tiêu là tránh việc ứng dụng vô tình định nghĩa lại các lớp nền tảng như `java.lang.String`.

Luồng khái quát:

1. Ứng dụng yêu cầu JVM nạp một lớp.
2. Application loader kiểm tra lớp đã được nạp chưa.
3. Nếu chưa, loader ủy quyền lên platform loader.
4. Platform loader tiếp tục ủy quyền lên bootstrap loader.
5. Nếu các loader cha không tìm thấy, loader phù hợp tìm lớp trong nguồn mà nó quản lý.
6. Nếu không tìm thấy, JVM phát sinh `ClassNotFoundException` hoặc lỗi liên quan tùy API và thời điểm nạp/liên kết.

Mô hình trên giúp hiểu luồng phổ biến, nhưng không phải hợp đồng bắt buộc cho mọi loader tùy chỉnh. Một `ClassLoader` tự viết có thể thay đổi chiến lược trong `loadClass`; các loader tích hợp sẵn cũng có cơ chế đặc thù để xử lý lớp trong module.

Ví dụ quan sát parent:

```java
ClassLoader app = ClassLoader.getSystemClassLoader();
ClassLoader platform = ClassLoader.getPlatformClassLoader();

System.out.println(app.getParent() == platform); // thường là true
System.out.println(platform.getParent());        // null: bootstrap
```

Không nên dùng `toString()` hoặc tên lớp triển khai nội bộ của loader làm điều kiện logic. Hãy so sánh đối tượng loader hoặc dùng API công khai khi cần nhận diện.

## 5. Classpath và module path

Java 9 trở đi có hai cách phổ biến để cung cấp mã cho ứng dụng:

| Nguồn mã | Cách khai báo | Module runtime |
| --- | --- | --- |
| Classpath | `-cp`, `-classpath`, `--class-path` | Các lớp thường thuộc unnamed module của class loader tương ứng. |
| Module path | `--module-path`, `-p` | Chứa các module có tên; JVM phân giải dependency và đặt chúng vào module layer. |

### 5.1. Lớp trên classpath

Ví dụ:

```bash
javac -d out src/com/example/Main.java
java -cp out com.example.Main
```

Trong cấu hình mặc định, `com.example.Main` được application/system class loader nạp. Các lớp trên classpath thuộc unnamed module gắn với loader đó. Unnamed module không có tên để khai báo trong `module-info.java`, nhưng vẫn có đối tượng `Module` ở runtime.

Một class loader có thể có unnamed module riêng. Vì vậy, hai loader khác nhau có thể gắn với hai unnamed module khác nhau.

### 5.2. Named module trên module path

Một dự án modular có thể có cấu trúc:

```text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/Main.java
```

Nội dung `module-info.java`:

```java
module com.example.app {
    requires java.sql;
}
```

Biên dịch và chạy:

```bash
javac --module-source-path src -d mods -m com.example.app
java --module-path mods -m com.example.app/com.example.Main
```

JVM phân giải module `com.example.app` cùng các dependency cần thiết. Các module được đặt trong một module layer và gắn với class loader phù hợp. Với cấu hình mặc định, application/system loader có thể nạp nhiều named module trên module path; **không có quy tắc mỗi module luôn cần một class loader riêng**.

Module path xác định các module có thể được phân giải, còn loader chịu trách nhiệm định nghĩa lớp của module. Module graph và loader hierarchy có liên hệ nhưng không phải cùng một đồ thị.

## 6. Module liên kết với class loader ra sao?

Đối tượng `Module` đại diện cho module ở runtime. Một named module được gắn với một class loader và thuộc một module layer. Class loader có thể định nghĩa lớp cho nhiều module; do đó không thể suy luận tên module chỉ từ tên loader.

Các API hữu ích:

- `SomeClass.class.getClassLoader()` trả về loader đã định nghĩa lớp; trả về `null` nếu lớp do bootstrap loader định nghĩa.
- `SomeClass.class.getModule()` trả về module runtime chứa lớp.
- `module.getClassLoader()` trả về loader gắn với module; có thể là `null` cho module được bootstrap loader định nghĩa.
- `module.getLayer()` cho biết module layer chứa module nếu có.
- `ClassLoader.getUnnamedModule()` trả về unnamed module gắn với loader hiện tại.

Ví dụ:

```java
Class<?> type = java.sql.Driver.class;

ClassLoader loader = type.getClassLoader();
Module module = type.getModule();

System.out.println("Class: " + type.getName());
System.out.println("Loader: " + loader);
System.out.println("Module: " + module.getName());
System.out.println("Module loader: " + module.getClassLoader());
System.out.println("Layer: " + module.getLayer());
```

`java.sql.Driver` thuộc module `java.sql`. Loader cụ thể có thể quan sát trực tiếp khi chạy trên JDK của bạn. Không nên hard-code tên hoặc lớp triển khai nội bộ của loader, bởi chi tiết triển khai có thể khác giữa các bản phân phối/runtime.

### Module không đồng nghĩa với class loader

Hãy phân biệt ba khái niệm:

- **Module:** đơn vị đóng gói package, khai báo `requires`, `exports`, `opens`, `uses`, `provides` và tạo ranh giới truy cập.
- **Class loader:** cơ chế tìm và định nghĩa class ở runtime.
- **Module layer:** tập hợp module đã được phân giải và liên kết ở runtime; layer có thể có quan hệ cha với layer khác.

Hai module có thể dùng chung một class loader. Ngược lại, ứng dụng có thể tạo module layer mới với loader mới để cô lập các nhóm module. Việc một loader nạp được bytecode không tự động cấp quyền truy cập mọi package của module; quy tắc readability và `exports` của JPMS vẫn được áp dụng.

## 7. Module layer và class loader tùy chỉnh

Module layer cho phép ứng dụng xây dựng một vùng module riêng sau khi JVM khởi động. Tính năng này hữu ích cho hệ thống plugin, ứng dụng mở rộng động hoặc nền tảng cần nạp nhiều thành phần theo cấu hình.

Layer khởi động có thể lấy bằng:

```java
ModuleLayer bootLayer = ModuleLayer.boot();
System.out.println(bootLayer.modules().size());
System.out.println(bootLayer.findModule("java.base").isPresent());
```

Khi tạo layer mới, Java cung cấp các lựa chọn cấu hình loader:

- `defineModulesWithOneLoader(...)`: các module trong layer mới dùng chung một loader được chỉ định làm parent.
- `defineModulesWithManyLoaders(...)`: mỗi module trong layer mới được gắn với một loader riêng, với parent được chỉ định.
- `defineModules(...)`: cho phép ứng dụng cung cấp hàm ánh xạ tên module sang class loader.

Các phương thức này thuộc API `ModuleLayer`. Trước khi tạo layer, ứng dụng thường tìm module bằng `ModuleFinder`, tạo `Configuration` bằng API resolve/resolveAndBind, rồi mới định nghĩa layer. Việc resolve xác định module và dependency; việc define layer gắn module với loader.

Không nên tạo một class loader riêng cho mỗi module chỉ vì module có tên. Hãy chọn chiến lược theo yêu cầu cô lập, chia sẻ lớp, vòng đời plugin và khả năng quản lý dependency.

## 8. Kiểm tra class loader và module trong chương trình

Ví dụ sau chạy như một ứng dụng modular để quan sát loader của các lớp thuộc những module khác nhau.

`src/com.example.inspect/module-info.java`:

```java
module com.example.inspect {
    requires java.sql;
}
```

`src/com.example.inspect/com/example/inspect/LoaderInfo.java`:

```java
package com.example.inspect;

public class LoaderInfo {
    public static void main(String[] args) {
        printInfo(String.class);
        printInfo(java.sql.Driver.class);
        printInfo(LoaderInfo.class);

        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("Platform loader: " + platform);
        System.out.println("System loader: " + system);
        System.out.println("System parent is platform: "
                + (system.getParent() == platform));
        System.out.println("Platform parent: " + platform.getParent());
    }

    private static void printInfo(Class<?> type) {
        ClassLoader loader = type.getClassLoader();
        Module module = type.getModule();

        String loaderRole;
        if (loader == null) {
            loaderRole = "bootstrap";
        } else if (loader == ClassLoader.getPlatformClassLoader()) {
            loaderRole = "platform";
        } else if (loader == ClassLoader.getSystemClassLoader()) {
            loaderRole = "application/system";
        } else {
            loaderRole = loader.getClass().getName();
        }

        String moduleName = module.isNamed()
                ? module.getName()
                : "<unnamed>";

        System.out.printf(
                "%s | loader=%s | module=%s%n",
                type.getName(), loaderRole, moduleName
        );
    }
}
```

Biên dịch và chạy:

```bash
javac --module-source-path src -d mods -m com.example.inspect
java --module-path mods -m com.example.inspect/com.example.inspect.LoaderInfo
```

Kết quả thường cho thấy:

- `java.lang.String` được bootstrap loader định nghĩa; `getClassLoader()` trả về `null`.
- `java.sql.Driver` thuộc module `java.sql`; loader được in ra tùy cách JDK phân công lớp nền tảng.
- `LoaderInfo` thuộc module `com.example.inspect` và thường được application/system loader định nghĩa trong cấu hình mặc định.
- System loader thường có parent là platform loader; parent của platform loader được biểu diễn bằng `null`.

Hãy dùng kết quả trên JDK thực tế để quan sát. Không nên phụ thuộc vào chuỗi `toString()` cụ thể vì nó có thể thay đổi theo implementation.

## 9. Defining loader và context class loader

Ngoài defining class loader, Java còn có **thread context class loader**:

```java
ClassLoader defining = LoaderInfo.class.getClassLoader();
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

System.out.println("Defining loader: " + defining);
System.out.println("Context loader: " + context);
```

Hai loader này có thể khác nhau:

- Defining loader là loader đã định nghĩa lớp đang xét. Nó quyết định danh tính runtime của lớp.
- Context class loader là loader gắn với thread hiện tại, có thể được host/framework thiết lập để mã thư viện nạp tài nguyên hoặc provider do ứng dụng cung cấp.

Một số framework và cơ chế như `ServiceLoader.load(...)` sử dụng context class loader trong các overload tương ứng. Vì vậy, khi framework không tìm thấy plugin dù lớp ứng dụng đã được nạp, cần kiểm tra context loader, module visibility và cấu hình provider, thay vì chỉ kiểm tra defining loader.

Context loader không thay thế quan hệ parent của loader và cũng không tự cấp quyền `exports` cho module.

## 10. Lỗi thường gặp và cách xử lý

### 10.1. `ClassNotFoundException`

Thường xuất hiện khi ứng dụng yêu cầu nạp một lớp bằng tên nhưng loader được sử dụng không tìm thấy bytecode.

Kiểm tra:

- JAR/thư mục chứa lớp có nằm trong classpath hoặc module path phù hợp không?
- Tên đầy đủ của lớp có đúng không?
- Lớp có được đặt trong đúng module và package không?
- Framework đang dùng defining loader hay context class loader?
- Với module path, module có được resolve vào layer đang chạy không?

### 10.2. `NoClassDefFoundError`

Đây là lỗi liên kết hoặc sử dụng lớp khi JVM không thể tìm thấy định nghĩa cần thiết tại thời điểm đó. Nó có thể xảy ra sau một lần nạp/khởi tạo thất bại hoặc khi dependency runtime thiếu. Đọc nguyên nhân gốc (cause) và stack trace; không nên xử lý bằng cách thêm JAR ngẫu nhiên vào classpath.

### 10.3. `ClassCastException` dù hai lớp có cùng tên

Một plugin có thể được nạp bởi loader A, còn API mà ứng dụng dùng được nạp bởi loader B. Nếu mỗi loader định nghĩa riêng một lớp có cùng binary name, JVM xem đó là hai kiểu khác nhau và phép ép kiểu có thể thất bại.

Hướng xử lý:

- Đặt API dùng chung ở một loader cha mà cả host và plugin cùng nhìn thấy.
- Tránh đóng gói bản sao của API chung trong từng plugin.
- Thiết kế parent delegation nhất quán.
- Xác nhận cả tên lớp lẫn defining loader khi chẩn đoán.

### 10.4. `IllegalAccessError` hoặc lỗi module access

Lớp có thể đã được nạp nhưng module caller không đọc được module chứa kiểu, hoặc package chưa được export phù hợp. Class loading thành công không đồng nghĩa quyền truy cập đã được cấp.

Kiểm tra `requires`, `exports` và quan hệ module layer. Với tích hợp legacy, các tùy chọn `--add-reads` hoặc `--add-exports` có thể hỗ trợ chẩn đoán, nhưng thiết kế lâu dài nên được thể hiện trong module descriptor.

### 10.5. Nhầm lẫn giữa platform và application loader

Không phải mọi lớp thuộc JDK đều được định nghĩa bởi bootstrap loader. Hãy kiểm tra bằng `Class.getClassLoader()` và `Class.getModule()` thay vì suy luận từ tiền tố package như `java.*` hoặc `jdk.*`.

## 11. Nguyên tắc thiết kế khi dùng class loader với module

1. **Để loader mặc định làm việc khi không có yêu cầu đặc biệt.** Ứng dụng thông thường nên dùng module path/classpath và các loader tích hợp sẵn.
2. **Giữ API chung ở vị trí có thể chia sẻ.** Với plugin, API mà host và plugin trao đổi nên được định nghĩa bởi loader cha chung.
3. **Phân biệt nạp lớp và quyền truy cập module.** Nếu gặp lỗi `not visible` hoặc `IllegalAccessError`, kiểm tra module graph và exports; thay loader chưa chắc giải quyết đúng vấn đề.
4. **Chỉ tạo loader riêng khi có nhu cầu cô lập.** Xác định rõ vòng đời, dependency, khả năng chia sẻ API và cơ chế giải phóng tài nguyên.
5. **Không giả định một module tương ứng một loader.** Một loader có thể định nghĩa nhiều module trong cùng layer.
6. **Không hard-code tên implementation nội bộ.** Ưu tiên API công khai như `getPlatformClassLoader()`, `getSystemClassLoader()`, `Class.getClassLoader()` và `Class.getModule()`.
7. **Kiểm tra context class loader khi tích hợp framework.** Framework có thể dùng loader của thread để tìm provider/tài nguyên thay vì loader đã định nghĩa chính framework đó.

## 12. Bài tập tự kiểm tra

**Bài 1.** `String.class.getClassLoader()` trả về `null`. Điều đó có nghĩa `String` chưa được nạp?

**Đáp án:** Không. `null` biểu diễn bootstrap class loader, loader nền tảng không được trả về dưới dạng một đối tượng `ClassLoader` thông thường.

**Bài 2.** Trong cấu hình mặc định, parent của system/application class loader là gì?

**Đáp án:** Platform class loader. Parent của platform class loader là bootstrap loader và được biểu diễn bằng `null`.

**Bài 3.** Một named module trên module path có bắt buộc phải có class loader riêng không?

**Đáp án:** Không. Nhiều named module có thể được cùng một class loader định nghĩa. Module layer cho phép chọn chiến lược một loader, nhiều loader hoặc ánh xạ tùy chỉnh.

**Bài 4.** Hai class loader khác nhau cùng nạp lớp `com.demo.Plugin`. Hai lớp có thể ép kiểu cho nhau chỉ vì tên giống nhau không?

**Đáp án:** Không. Danh tính lớp còn phụ thuộc defining loader; hai lớp được định nghĩa bởi hai loader khác nhau là hai kiểu runtime khác nhau.

**Bài 5.** Một framework không tìm thấy provider do ứng dụng cung cấp. Ngoài defining loader của framework, nên kiểm tra gì?

**Đáp án:** Kiểm tra thread context class loader, cấu hình `ServiceLoader`/provider, module `uses` và `provides` nếu dùng JPMS, cùng khả năng resolve module và quyền truy cập package.

## Ghi nhớ

Bootstrap loader nạp các lớp cốt lõi; platform loader nạp các lớp nền tảng được giao cho nó; application/system loader nạp mã ứng dụng và thường là các named module ứng dụng trên module path. Trong JPMS, module xác định dependency và ranh giới package, còn class loader định nghĩa lớp ở runtime. Một module không đồng nghĩa với một loader, và một lớp cùng tên vẫn có thể là kiểu khác nếu defining loader khác nhau.