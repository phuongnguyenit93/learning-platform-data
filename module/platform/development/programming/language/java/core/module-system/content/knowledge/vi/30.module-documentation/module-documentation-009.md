# Ví dụ modular tối thiểu có thể build và chạy

Bài thực hành này xây dựng một ứng dụng **Java Platform Module System (JPMS)** nhỏ nhưng hoàn chỉnh, gồm **hai named modules**: một module cung cấp API chào hỏi và một module ứng dụng sử dụng API đó. Bạn sẽ tạo các tệp `module-info.java`, biên dịch bằng `javac`, chạy bằng `java --module-path -m`, sau đó đóng gói thành các modular JAR có thể chạy độc lập từ thư mục phân phối.

Toàn bộ ví dụ sử dụng JDK tiêu chuẩn, **không cần Maven, Gradle hay thư viện bên thứ ba**. Nếu sao chép đúng cấu trúc và mã nguồn, các lệnh có thể chạy trên JDK 17 trở lên; JPMS được giới thiệu từ Java 9.

## 1. Kết quả mong đợi

Khi hoàn thành, bạn có:

- Module `com.example.greeting` cung cấp lớp public `Greeter` trong package được export.
- Module `com.example.app` khai báo `requires com.example.greeting;` và gọi `Greeter`.
- Hai thư mục module đã biên dịch trong `out/`.
- Hai modular JAR trong `dist/`.
- Lệnh chạy với module path và một root module.

Ví dụ chạy:

```shell
java --module-path out --module com.example.app/com.example.app.Main
```

Đầu ra:

```text
Xin chào, Java!
```

Truyền tên qua command-line argument:

```shell
java --module-path out -m com.example.app/com.example.app.Main Lan
```

Đầu ra:

```text
Xin chào, Lan!
```

Ví dụ này minh họa đầy đủ hai khái niệm quan trọng: **`requires` tạo quan hệ đọc giữa các module** và **`exports` công khai package API**. Nếu thiếu một trong hai, việc module ứng dụng sử dụng lớp `Greeter` sẽ không hợp lệ theo mô hình truy cập JPMS.

## 2. Chuẩn bị môi trường

Cần cài **JDK**, không chỉ một runtime rút gọn không có compiler. Các công cụ được sử dụng:

- `java`: khởi chạy ứng dụng.
- `javac`: biên dịch Java source và module descriptor.
- `jar`: đóng gói modular JAR và xem descriptor.
- `jdeps`: tùy chọn, dùng để phân tích dependency sau khi build.

Kiểm tra JDK trong terminal:

```shell
java -version
javac -version
jar --version
```

Ví dụ output có thể hiển thị `17`, `21` hoặc một phiên bản JDK mới hơn. Quan trọng là `java` và `javac` sử dụng cùng toolchain thích hợp, đặc biệt nếu máy có nhiều phiên bản Java.

Nếu `javac` không được nhận diện, kiểm tra JDK đã được cài và thư mục `bin` nằm trên `PATH`. Trong hệ thống quản lý nhiều JDK, có thể dùng đường dẫn đầy đủ tới `java`, `javac` và `jar` thay vì trông chờ `PATH`.

Các lệnh trong bài được thực hiện từ **thư mục gốc của dự án**. Cần tạo tệp bằng đúng tên và package khai báo. Trên Windows có thể dùng PowerShell; trên Linux/macOS dùng shell thông thường.

## 3. Cấu trúc dự án

Tạo một thư mục, ví dụ `jpms-hello`, với cấu trúc:

```text
jpms-hello/
└── src/
    ├── com.example.greeting/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── greeting/
    │               └── api/
    │                   └── Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
```

Lưu ý:

1. `src/com.example.greeting` và `src/com.example.app` là **hai module source roots**.
2. Mỗi module có `module-info.java` tại gốc module.
3. Các đường dẫn con dưới module root tương ứng với tên package Java.
4. `out/` và `dist/` được tạo ở các bước tiếp theo, không cần đặt trong source tree.

Đây là cách tổ chức phù hợp cho lệnh:

```shell
javac --module-source-path src -d out -m com.example.greeting,com.example.app
```

Nếu dùng cách tổ chức source khác, cần điều chỉnh `--module-source-path` tương ứng. Trình biên dịch không tự suy ra cấu trúc module từ mọi kiểu thư mục tùy ý.

## 4. Tạo module cung cấp API: com.example.greeting

### 4.1. Viết module-info.java

Tạo tệp `src/com.example.greeting/module-info.java`:

```java
/**
 * Cung cấp API tạo lời chào đơn giản.
 *
 * <p>Các module khác sử dụng lớp Greeter qua
 * package com.example.greeting.api.
 */
module com.example.greeting {
    exports com.example.greeting.api;
}
```

Module descriptor có hai ý nghĩa:

- `module com.example.greeting`: đặt tên cho named module.
- `exports com.example.greeting.api;`: cho phép module khác đọc `com.example.greeting` sử dụng những kiểu `public` trong package API đó.

Module này không cần khai báo `requires java.base;`, vì mọi named module đều đọc `java.base` một cách ngầm định. Những kiểu cơ bản như `String` nằm trong nền tảng này.

### 4.2. Viết lớp Greeter

Tạo `src/com.example.greeting/com/example/greeting/api/Greeter.java`:

```java
package com.example.greeting.api;

/**
 * API tạo một lời chào có tên người nhận.
 */
public final class Greeter {

    /**
     * Trả về lời chào dành cho tên được truyền vào.
     *
     * @param name tên người nhận
     * @return lời chào
     */
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Lớp `Greeter` là `public` và nằm trong package `com.example.greeting.api` đã được export. Vì vậy, một module khác có quan hệ readability phù hợp có thể khởi tạo và gọi phương thức `greet`.

Nếu bỏ `public` ở khai báo class, module khác sẽ không được sử dụng lớp đó như một public API, dù package đã export. `exports` không làm các kiểu hoặc thành viên package-private trở thành public.

## 5. Tạo module ứng dụng: com.example.app

### 5.1. Viết module-info.java

Tạo `src/com.example.app/module-info.java`:

```java
/**
 * Ứng dụng minh họa cách sử dụng một module API khác.
 */
module com.example.app {
    requires com.example.greeting;
}
```

Directive `requires com.example.greeting;` cho biết app cần đọc module `com.example.greeting`. Khi Java phân giải app làm root module, dependency này phải được tìm thấy từ module path hoặc nguồn module phù hợp.

App không cần `exports com.example.app;`, vì lớp `Main` chỉ phục vụ điểm vào chương trình; không có module consumer nào cần import package đó. Main class của ứng dụng không bắt buộc phải thuộc package được export.

### 5.2. Viết Main.java

Tạo `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.greeting.api.Greeter;

public final class Main {

    public static void main(String[] args) {
        String recipient = args.length == 0 ? "Java" : args[0];

        Greeter greeter = new Greeter();
        System.out.println(greeter.greet(recipient));
    }
}
```

Phân biệt hai yếu tố:

- `import com.example.greeting.api.Greeter;` giúp mã nguồn gọi lớp bằng tên ngắn `Greeter`.
- `requires com.example.greeting;` trong descriptor khai báo dependency giữa các module.

`import` không thay thế `requires`; `requires` cũng không tự làm package chưa export trở nên truy cập được. Hai module trong ví dụ phối hợp qua **readability** ở phía app và **exports** ở phía greeting.

## 6. Biên dịch bằng javac --module-source-path

Mở terminal tại thư mục `jpms-hello` và chạy:

```shell
javac --module-source-path src -d out -m com.example.greeting,com.example.app
```

Giải thích các tham số:

| Tham số | Ý nghĩa |
|---|---|
| `--module-source-path src` | Thư mục chứa mã nguồn của các module |
| `-d out` | Thư mục kết quả biên dịch |
| `-m com.example.greeting,com.example.app` | Các module nguồn được yêu cầu biên dịch |

Khi biên dịch thành công, output thường có dạng:

```text
out/
├── com.example.greeting/
│   ├── module-info.class
│   └── com/example/greeting/api/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

Tệp `module-info.java` được biên dịch thành `module-info.class`, chứa module descriptor dưới dạng metadata phù hợp với JVM. Những module đã biên dịch trong `out/` được gọi là **exploded modules**.

Khi dùng `--module-source-path`, compiler có thể tìm mã nguồn của cả module app và dependency greeting. Nếu một module yêu cầu module khác nhưng module đó không có trong source path, module path hoặc system modules, compiler sẽ báo lỗi.

### 6.1. Không dùng javac -cp theo cách cũ

Cách truyền thống:

```shell
javac -cp libs/* ...
```

cung cấp thư viện qua classpath. Nó không tự thiết lập một cấu hình named modules giống `--module-source-path` hoặc `--module-path`. Trong bài này, cần biên dịch cả `module-info.java` và code thành các named modules để có JPMS thực sự.

### 6.2. Biên dịch theo hai lượt (tham khảo)

Nếu muốn biên dịch dependency trước rồi app sau, có thể làm:

```shell
javac -d out/com.example.greeting src/com.example.greeting/module-info.java src/com.example.greeting/com/example/greeting/api/Greeter.java
```

Sau đó:

```shell
javac --module-path out -d out/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
```

Lượt thứ hai sử dụng `--module-path out` để tìm exploded module `com.example.greeting` vừa biên dịch. Đây là cách minh họa sự khác biệt giữa **module-source-path** (tìm nguồn) và **module-path** (tìm module đã biên dịch).

Cách một lệnh ở đầu mục đơn giản hơn cho bài thực hành này.

## 7. Chạy exploded modules trực tiếp

Sau khi biên dịch, chạy:

```shell
java --module-path out --module com.example.app/com.example.app.Main
```

Dạng viết ngắn tương đương:

```shell
java -p out -m com.example.app/com.example.app.Main
```

Kết quả:

```text
Xin chào, Java!
```

Chạy với đối số:

```shell
java -p out -m com.example.app/com.example.app.Main Minh
```

Kết quả:

```text
Xin chào, Minh!
```

Trong đó:

- `-p out` chỉ định vị trí các module đã biên dịch.
- `-m com.example.app/com.example.app.Main` chọn module khởi động và tên class chứa `main`.
- `Minh` là phần tử đầu tiên của mảng `String[] args`, không phải một phần tên module.

Ở thời điểm khởi chạy, Java launcher tìm module `com.example.app`, đọc descriptor, phát hiện dependency `com.example.greeting` và phân giải cả hai module. Sau đó app có thể dùng lớp `Greeter` qua package đã export.

## 8. Điều gì xảy ra trong module resolution?

Cấu trúc module graph của bài thực hành:

```text
       com.example.app
              |
              | requires
              v
    com.example.greeting
              |
              | implicit requires
              v
           java.base
```

Module `java.base` đã có trong runtime image. Không cần đóng gói hoặc sao chép nó vào `out/`.

Khi khởi động:

1. Java tìm `com.example.app` từ module path và chọn làm root module.
2. Resolver đọc `requires com.example.greeting;`.
3. Resolver tìm `com.example.greeting` trong module path.
4. Các system module cần thiết, như `java.base`, được xử lý theo quy tắc nền tảng.
5. Module graph được hình thành; runtime định nghĩa các module và class loader phù hợp.
6. Launcher tìm `com.example.app.Main` và gọi phương thức `main`.
7. App sử dụng API `Greeter` từ module greeting.

Không phải mọi JAR có trên module path đều tự động được phân giải. Resolver bắt đầu từ các root module và các quan hệ dependency; tùy chọn như `--add-modules` có thể đưa thêm root module vào graph khi cần.

## 9. Đóng gói thành modular JAR

Khi muốn phát hành ứng dụng, thường đóng gói mỗi module thành JAR.

Tạo thư mục `dist`.

Trên Linux/macOS:

```shell
mkdir -p dist
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path dist | Out-Null
```

Đóng gói module greeting:

```shell
jar --create --file dist/com.example.greeting.jar -C out/com.example.greeting .
```

Đóng gói module app:

```shell
jar --create --file dist/com.example.app.jar -C out/com.example.app .
```

Thư mục phân phối trở thành:

```text
dist/
├── com.example.greeting.jar
└── com.example.app.jar
```

Mỗi JAR có `module-info.class` ở gốc nên đây là **explicit modular JAR**. Tên module lấy từ descriptor, không phải tự động từ tên file `.jar`. Trong ví dụ, tên file được đặt giống module name để dễ nhận biết, nhưng đó chỉ là quy ước.

Kiểm tra nội dung:

```shell
jar --list --file dist/com.example.greeting.jar
jar --list --file dist/com.example.app.jar
```

Bạn sẽ thấy `module-info.class`, class file và metadata của JAR.

## 10. Chạy ứng dụng từ modular JAR

Thay `out` bằng `dist` trong module path:

```shell
java --module-path dist --module com.example.app/com.example.app.Main
```

Đầu ra mong đợi:

```text
Xin chào, Java!
```

Để truyền argument:

```shell
java -p dist -m com.example.app/com.example.app.Main "Học JPMS"
```

Đầu ra:

```text
Xin chào, Học JPMS!
```

Dấu ngoặc kép quanh `"Học JPMS"` giữ cả cụm thành một command-line argument.

Tùy chọn khác là ghi **main class** khi đóng gói module app:

```shell
jar --create --file dist/com.example.app.jar --main-class com.example.app.Main -C out/com.example.app .
```

Lệnh trên tạo lại app JAR với metadata main class. Khi đó có thể chạy mà không phải ghi tên lớp sau dấu `/`:

```shell
java --module-path dist --module com.example.app
```

Nếu chưa ghi main class trong module artifact, vẫn dùng dạng `-m com.example.app/com.example.app.Main` để chỉ định điểm vào chương trình.

## 11. Kiểm tra module descriptor sau khi đóng gói

Dùng `jar --describe-module` để xem metadata:

```shell
jar --describe-module --file dist/com.example.greeting.jar
```

Thông tin đáng quan tâm:

- Module name: `com.example.greeting`.
- Package được export: `com.example.greeting.api`.
- Quan hệ tới `java.base`.

Với app:

```shell
jar --describe-module --file dist/com.example.app.jar
```

Thông tin cần thấy là dependency tới `com.example.greeting`; nếu đã đóng gói với `--main-class`, descriptor hiển thị thông tin main class tương ứng.

Khi sửa `module-info.java`, cần **biên dịch và đóng gói lại** để JAR chứa descriptor mới. Chỉ sửa file `.java` sau khi đã tạo JAR không làm metadata bên trong artifact phát hành tự thay đổi.

## 12. Quan sát module resolution khi chạy

Java launcher có các tùy chọn hữu ích để xem cấu hình:

**Liệt kê module có thể quan sát:**

```shell
java --module-path dist --list-modules
```

Danh sách bao gồm system modules và các module có thể tìm từ module path. Nó chưa chứng minh mọi module đều được phân giải khi chạy app.

**Mô tả một module:**

```shell
java --module-path dist --describe-module com.example.app
```

**In quá trình resolution:**

```shell
java --show-module-resolution --module-path dist -m com.example.app/com.example.app.Main
```

Bạn có thể tìm những thông tin tương tự quan hệ app đọc greeting. Đầu ra chi tiết thay đổi tùy phiên bản JDK.

**Chỉ thử khởi tạo module graph mà không chạy main:**

```shell
java --show-module-resolution --dry-run --module-path dist -m com.example.app/com.example.app.Main
```

`--dry-run` phù hợp khi muốn kiểm tra resolution và module setup mà không thực thi logic trong `main`. Nó không thay thế việc chạy ứng dụng để quan sát kết quả nghiệp vụ.

**Kiểm tra cấu trúc module path:**

```shell
java --module-path dist --validate-modules
```

Lệnh hỗ trợ phát hiện một số vấn đề về module trùng tên hoặc xung đột package. Với ví dụ nhỏ đúng cấu trúc, không kỳ vọng gặp lỗi validation.

## 13. Kiểm tra dependency tĩnh bằng jdeps

`jdeps` đọc class file/JAR và phân tích dependency:

```shell
jdeps --module-path dist --list-deps dist/com.example.app.jar
```

Khi phân tích module app, bạn kỳ vọng nhận diện dependency tới `com.example.greeting` và những system modules cần thiết. Lệnh này hữu ích khi codebase lớn hơn và muốn xem dependency được suy ra từ bytecode và metadata.

Muốn xem dependency ở mức package:

```shell
jdeps --module-path dist -verbose:package dist/com.example.app.jar
```

`jdeps` không phát hiện đầy đủ mọi dependency được nạp động bằng reflection, `ServiceLoader` hoặc tên class dạng chuỗi. Ở ví dụ tối thiểu này, dependency được khai báo tường minh nên công cụ dễ quan sát hơn.

## 14. Phân biệt module path và classpath

Hai cách chạy có thể trông giống nhau nhưng không tương đương.

**Module path (JPMS):**

```shell
java --module-path dist -m com.example.app/com.example.app.Main
```

Java sử dụng `module-info.class`, phân giải `requires`, thực thi ranh giới `exports` và các quy tắc module.

**Classpath truyền thống:**

```shell
java --class-path "dist/*" com.example.app.Main
```

Khi đưa modular JAR lên classpath như một thư viện classpath, các lớp được sử dụng theo mô hình unnamed module của class loader tương ứng thay vì module graph explicit đã được phân giải từ `--module-path`.

Trong trường hợp classpath có đủ hai JAR, code vẫn có thể chạy, nhưng bạn không còn kiểm tra đúng các ranh giới JPMS đã thiết kế. Vì mục tiêu của bài là một ứng dụng **modular**, hãy dùng `--module-path` và `-m`.

Tương tự, `java -jar dist/com.example.app.jar` không tương đương `java -m com.example.app`: `-jar` dùng manifest `Main-Class` và ngữ nghĩa khởi chạy JAR/classpath, không biến JAR thành root named module chỉ vì nó chứa `module-info.class`.

## 15. Thử thay đổi descriptor để hiểu requires và exports

Có thể thực hiện các thử nghiệm riêng sau khi đã build và chạy thành công.

### 15.1. Bỏ requires ở app

Thay descriptor app thành:

```java
module com.example.app {
}
```

Giữ nguyên lệnh `import com.example.greeting.api.Greeter;` trong `Main.java` và biên dịch lại. Compiler sẽ không cho module app sử dụng API của greeting theo cách thông thường vì app không đọc module greeting.

Đây là lỗi **readability**. Việc JAR greeting tồn tại trong module path không thay thế quan hệ `requires`.

Khôi phục:

```java
module com.example.app {
    requires com.example.greeting;
}
```

### 15.2. Bỏ exports ở greeting

Giữ `requires com.example.greeting;` trong app, nhưng đổi descriptor greeting thành:

```java
module com.example.greeting {
}
```

Biên dịch lại. App có thể đọc greeting, nhưng package `com.example.greeting.api` không được export ra ngoài. Compiler sẽ báo package không khả dụng cho module app.

Đây là lỗi **package encapsulation**, không phải thiếu module.

Khôi phục:

```java
module com.example.greeting {
    exports com.example.greeting.api;
}
```

### 15.3. Đổi sai tên module

Nếu app khai báo:

```java
requires com.example.greeter;
```

trong khi module thực tế là `com.example.greeting`, compiler/resolver có thể báo không tìm thấy module. JPMS dùng **module name** chính xác, không tự thay thế theo tên class hoặc package gần giống.

Ba thử nghiệm này giúp phân biệt ba lỗi: thiếu module, thiếu readability và package chưa export.

## 16. Các lỗi thường gặp khi build/run

### Lỗi 1: `javac: command not found`

Nguyên nhân: không có JDK compiler trong `PATH`, hoặc đang dùng môi trường chỉ có runtime.

Khắc phục: cài JDK phù hợp, kiểm tra `javac -version` và `java -version`. Không cần thay đổi source code.

### Lỗi 2: Không tìm thấy module app

Thông báo có thể dạng:

```text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.example.app not found
```

Kiểm tra:

- Đã chạy `javac` thành công chưa?
- Có `out/com.example.app/module-info.class` không?
- `--module-path` đang trỏ tới `out`, không phải một thư mục sai cấp?
- Tên module ở `-m` có trùng descriptor không?
- Nếu chạy modular JAR, file app có nằm trong `dist` không?

### Lỗi 3: Không tìm thấy dependency greeting

App có `requires com.example.greeting;`, nhưng module greeting không nằm trong module path hoặc chưa được biên dịch/đóng gói.

Kiểm tra thư mục `out/com.example.greeting` hoặc file `dist/com.example.greeting.jar`, rồi xem descriptor:

```shell
jar --describe-module --file dist/com.example.greeting.jar
```

### Lỗi 4: Package chưa được export

Nếu thấy thông báo tương tự package thuộc một module khác nhưng không được export, kiểm tra descriptor greeting có:

```java
exports com.example.greeting.api;
```

Đừng cố sửa lỗi bằng cách đưa tất cả lớp vào classpath; việc đó bỏ qua mục tiêu học cách sử dụng JPMS.

### Lỗi 5: Main class không phù hợp

Lệnh sau dùng tên nhị phân đầy đủ của class:

```shell
java -p out -m com.example.app/com.example.app.Main
```

Nếu viết sai package, thiếu `Main.class` hoặc đổi tên class mà không cập nhật lệnh, launcher sẽ không tìm đúng entry point. Hãy kiểm tra package declaration và cấu trúc output.

### Lỗi 6: Đặt sai cấp module source root

Với lệnh:

```shell
javac --module-source-path src -d out -m com.example.app,com.example.greeting
```

compiler kỳ vọng `src` chứa thư mục tương ứng từng module, và trong mỗi module root có `module-info.java`. Nếu bạn đặt `src/module-info.java` chung cho cả hai module hoặc đặt code sai thư mục, compiler có thể báo không tìm thấy source module hoặc source file không nằm trong module mong đợi.

### Lỗi 7: Chạy trên Windows nhưng dùng dấu `:` cho nhiều path

Với một module path chỉ là `out` hoặc `dist`, cú pháp giống nhau ở mọi hệ điều hành. Nhưng khi có nhiều đường dẫn:

Windows:

```powershell
java --module-path "dist;third-party" -m com.example.app/com.example.app.Main
```

Linux/macOS:

```shell
java --module-path "dist:third-party" -m com.example.app/com.example.app.Main
```

Không nhầm ký tự phân cách module path với dấu `/` trong cú pháp `module/main-class`.

## 17. Một phiên bản tối giản chỉ có một module

Hai module giúp minh họa rõ `requires` và `exports`. Nếu chỉ muốn xem cách một named module tự chạy, phiên bản một module còn nhỏ hơn:

```text
single/
└── src/
    └── com.example.simple/
        ├── module-info.java
        └── com/example/simple/Main.java
```

Descriptor:

```java
module com.example.simple {
}
```

Main:

```java
package com.example.simple;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Hello modular Java!");
    }
}
```

Biên dịch từ thư mục `single`:

```shell
javac --module-source-path src -d out -m com.example.simple
```

Chạy:

```shell
java --module-path out -m com.example.simple/com.example.simple.Main
```

Kết quả:

```text
Hello modular Java!
```

Tại sao không có `requires` và `exports`? Module chỉ sử dụng API từ `java.base` và không có package nào cần công khai cho module bên ngoài. Đây vẫn là explicit named module vì có `module-info.java`.

Tuy nhiên, phiên bản hai module ở các mục trước nên được dùng làm bài thực hành chính khi học **module graph** và dependency access.

## 18. Có thể đưa ví dụ vào README dự án như thế nào?

Một README thực dụng cho ứng dụng modular nên chứa các phần:

1. **Yêu cầu:** phiên bản JDK tối thiểu và build tool nếu có.
2. **Source layout:** module roots và tên module thực tế.
3. **Module responsibilities:** module nào cung cấp API, module nào là entry point.
4. **Build command:** một hoặc vài lệnh có thể chạy từ thư mục gốc.
5. **Run command:** chính xác `--module-path` và `-m module/main-class`.
6. **Expected output:** kết quả cụ thể để người đọc đối chiếu.
7. **Packaging:** cách tạo modular JAR nếu cần phát hành.
8. **Troubleshooting:** lỗi module not found, exports, main class và toolchain.
9. **Module inspection:** `jar --describe-module` và `--show-module-resolution`.
10. **Versioning:** phiên bản JDK/toolchain mà lệnh đã được thiết kế để hỗ trợ.

Khi dự án dùng Maven hoặc Gradle, có thể thay thế các lệnh `javac`/`jar` thủ công bằng build commands tương ứng, nhưng nên giữ **lệnh `java -p ... -m ...` hoặc mô tả rõ lệnh tương đương**. Điều này chứng minh ứng dụng thật sự chạy theo mô hình modular, không phải vô tình chạy bằng classpath.

## 19. Checklist kiểm tra bài thực hành

- [ ] Có JDK và chạy được `java`, `javac`, `jar`.
- [ ] Hai module source roots có tên khớp `com.example.greeting`, `com.example.app`.
- [ ] Mỗi module có `module-info.java` tại gốc.
- [ ] Greeting export `com.example.greeting.api`.
- [ ] App khai báo `requires com.example.greeting;`.
- [ ] `Greeter.java` và `Main.java` khai báo đúng package.
- [ ] `javac --module-source-path src -d out -m com.example.greeting,com.example.app` hoàn tất.
- [ ] `out` chứa hai exploded modules và `module-info.class` tương ứng.
- [ ] `java -p out -m com.example.app/com.example.app.Main` in ra lời chào.
- [ ] Đã tạo cả hai JAR trong `dist`.
- [ ] `jar --describe-module` hiển thị module name và các directive đúng.
- [ ] `java -p dist -m com.example.app/com.example.app.Main` chạy được.
- [ ] Nếu dùng dạng `-m com.example.app`, app JAR có metadata main class.
- [ ] Không phải thêm các tùy chọn `--add-exports` hoặc `--add-opens` cho ví dụ cơ bản.

## Kết luận

Một ví dụ JPMS tối thiểu nhưng thể hiện được dependency thực tế cần ít nhất hai named modules: một module cung cấp API và một module tiêu thụ API đó. Module `com.example.greeting` khai báo `exports com.example.greeting.api;`, còn `com.example.app` khai báo `requires com.example.greeting;` và có class `Main`.

Với cấu trúc source theo module, chỉ cần lệnh `javac --module-source-path src -d out -m com.example.greeting,com.example.app` để biên dịch. Sau đó, `java --module-path out -m com.example.app/com.example.app.Main` khởi chạy trực tiếp exploded modules. Khi đóng gói thành JAR, thay module path từ `out` sang `dist`, giữ nguyên root module và main class.

Ví dụ này tạo nền tảng để học các chủ đề JPMS tiếp theo như `requires transitive`, qualified exports, `opens`, service binding, module layers và migration từ classpath. Nắm rõ cách build và chạy ví dụ đơn giản giúp phân biệt được lỗi source code với lỗi module resolution hoặc package access trong những dự án lớn hơn.
