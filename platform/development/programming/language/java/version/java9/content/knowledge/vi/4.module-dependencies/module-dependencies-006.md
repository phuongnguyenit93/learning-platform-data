# Phát hiện phụ thuộc mô-đun thiếu hoặc có chu kỳ

## Mục tiêu

Trong Java Platform Module System (JPMS), mỗi module khai báo các module mà nó cần bằng chỉ thị `requires` trong `module-info.java`. Tập hợp các quan hệ phụ thuộc tạo thành một đồ thị có hướng: một cạnh `A → B` nghĩa là module A cần module B. Đồ thị này phải được phân giải thành công trước khi chương trình modular có thể biên dịch hoặc khởi chạy.

Phát hiện phụ thuộc thiếu giúp tìm module được khai báo nhưng không có trong nguồn biên dịch hoặc module path. Phát hiện phụ thuộc có chu kỳ giúp tìm nhóm module phụ thuộc lẫn nhau theo vòng, khiến đồ thị không còn là một thứ tự phụ thuộc hợp lệ. Hai lỗi thường xuất hiện ở bước biên dịch hoặc khi JVM phân giải cấu hình module lúc khởi động.

## 1. JPMS xây dựng đồ thị phụ thuộc như thế nào?

Một module có tên và descriptor. Descriptor thường nằm trong `module-info.java`; khi biên dịch, nó trở thành `module-info.class` trong thư mục module hoặc modular JAR.

```java
module com.example.service {
    requires com.example.model;
    exports com.example.service;
}
```

Chỉ thị `requires` tạo quan hệ phụ thuộc bắt buộc. Module khai báo phải đọc được module được yêu cầu, và module được yêu cầu phải có thể được tìm thấy trong nguồn module hoặc module path.

Các biến thể quan trọng:

- `requires B;`: phụ thuộc thông thường. B phải được tìm thấy để phân giải module A.
- `requires transitive B;`: A phụ thuộc B và truyền khả năng đọc B cho module đọc A. Dùng khi API công khai của A để lộ kiểu thuộc B. Chỉ thị này không làm B trở thành tùy chọn và không giải quyết được chu kỳ.
- `requires static B;`: B cần có khi biên dịch nhưng có thể vắng mặt trong cấu hình chạy. Chỉ dùng cho phụ thuộc thực sự tùy chọn ở runtime; nếu đường chạy thực tế vẫn cần lớp của B thì thiếu lớp có thể gây lỗi liên kết hoặc nạp lớp.
- `requires static transitive B;`: kết hợp ý nghĩa truyền khả năng đọc với tính tùy chọn ở runtime của `static`.

`java.base` được mọi module thông thường phụ thuộc ngầm định; không cần viết `requires java.base;`. Tên module phân biệt chữ hoa/chữ thường và phải khớp chính xác với tên trong descriptor.

## 2. Phụ thuộc thiếu được phát hiện ở đâu?

### Khi biên dịch

`javac` cần tìm được các module được yêu cầu để kiểm tra kiểu và biên dịch. Nếu module descriptor khai báo một module không có trong module source path hoặc module path, trình biên dịch báo lỗi dạng:

```text
error: module not found: com.example.model
```

Ví dụ: `com.example.service` khai báo `requires com.example.model;`, nhưng thư mục nguồn hoặc modular JAR của `com.example.model` không được cung cấp. Lỗi xuất hiện trước khi tạo được bộ output hoàn chỉnh.

### Khi chạy

Java launcher phân giải module gốc được yêu cầu cùng các phụ thuộc bắt buộc trước khi gọi `main`. Nếu thiếu một module trong cấu hình chạy, JVM dừng ở bước khởi tạo boot layer và có thể báo:

```text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.example.model not found, required by com.example.service
```

Đây là lỗi tìm module, không phải lỗi class không tìm thấy bên trong một module đã phân giải. Khi gặp `FindException`, hãy kiểm tra module path và tên module trước khi điều tra code ứng dụng.

## 3. Những nguyên nhân thường gặp và cách xử lý

1. **Quên đưa một modular JAR vào module path.** Thêm JAR đúng phiên bản vào `--module-path` của cả lệnh biên dịch và lệnh chạy.
2. **Đặt nhầm JAR trên class path.** Một module có tên khai báo trong `requires` cần được tìm qua module path. Thêm JAR vào `--class-path` không tự biến nó thành module có tên tương ứng.
3. **Tên module không khớp.** So sánh tên trong `requires` với tên trong `module-info.java` hoặc kết quả `jar --describe-module --file path/to/library.jar`.
4. **Cấu hình source path không đúng cấu trúc.** Với `--module-source-path src`, mỗi module nguồn cần nằm trong thư mục con mang tên module, ví dụ `src/com.example.model/module-info.java`.
5. **Đưa nhầm thư mục vào module path.** Module path có thể chứa thư mục module đã biên dịch (exploded module) hoặc modular JAR. Đảm bảo đường dẫn trỏ tới đúng vị trí.
6. **JAR thư viện chưa có descriptor module.** JAR thường vẫn có thể được dùng như automatic module khi đặt trên module path; tên có thể lấy từ `Automatic-Module-Name` trong manifest hoặc suy ra từ tên file. Đây là cơ chế chuyển tiếp hữu ích, nhưng với module mới nên ưu tiên descriptor rõ ràng và tên ổn định.
7. **Có nhiều bản cùng tên module.** Loại bỏ bản trùng hoặc sửa cách đóng gói để module path chỉ cung cấp một module có tên đó.

### Phân biệt với lỗi khả năng đọc

Không phải mọi lỗi liên quan dependency đều là `module not found`. Nếu module tồn tại nhưng module gọi không đọc được module chứa một kiểu mà nó sử dụng, compiler có thể báo package không hiển thị hoặc module không đọc module kia. Kiểm tra `requires` và `requires transitive` theo ranh giới API. Không thêm `transitive` chỉ để làm biến mất một lỗi chưa hiểu rõ.

## 4. Phụ thuộc có chu kỳ là gì?

Chu kỳ xuất hiện khi có thể đi theo các cạnh `requires` từ một module và quay lại chính module đó. Ví dụ:

```text
com.example.a → com.example.b
com.example.b → com.example.a
```

Trong hai descriptor dưới đây, A cần B và B lại cần A:

**`cycle-src/com.example.a/module-info.java`**

```java
module com.example.a {
    requires com.example.b;
    exports com.example.a;
}
```

**`cycle-src/com.example.b/module-info.java`**

```java
module com.example.b {
    requires com.example.a;
    exports com.example.b;
}
```

Khi biên dịch hai module trên cùng một module source path, `javac` báo lỗi ở các chỉ thị `requires`, ví dụ:

```text
error: cyclic dependence involving com.example.b
error: cyclic dependence involving com.example.a
2 errors
```

JVM cũng kiểm tra tính hợp lệ của cấu hình khi phân giải module. Không nên dựa vào việc tách lệnh chạy, đổi thứ tự tham số hoặc thêm `requires transitive` để che chu kỳ trong descriptor.

## 5. Thiết kế lại để loại bỏ chu kỳ

Mục tiêu là làm cho đồ thị phụ thuộc có hướng không có chu trình (DAG). Hãy tìm trách nhiệm chung đang khiến hai module cần biết trực tiếp về nhau, rồi tách hợp đồng đó thành module thứ ba.

Trước:

```text
com.example.order ↔ com.example.inventory
```

Sau khi tách API chung:

```text
com.example.order     → com.example.contracts
com.example.inventory → com.example.contracts
```

Module `contracts` chứa interface, kiểu dữ liệu hoặc sự kiện ổn định mà cả hai bên cần. Module triển khai có thể phụ thuộc vào hợp đồng; module điều phối cấp cao kết nối các implementation. Một cách khác là đảo chiều phụ thuộc bằng interface hoặc SPI: module gọi định nghĩa interface, còn implementation đăng ký dịch vụ và được nạp qua `ServiceLoader` khi phù hợp.

Quy trình refactor:

1. Ghi lại các module và từng cạnh `requires`; đánh dấu cạnh nào tạo thành vòng.
2. Xác định kiểu hoặc trách nhiệm chung khiến các module phụ thuộc ngược nhau.
3. Di chuyển hợp đồng ổn định sang module API nhỏ, ít phụ thuộc.
4. Chỉnh descriptor để các module cùng phụ thuộc vào hợp đồng; tránh để hợp đồng phụ thuộc ngược vào implementation.
5. Biên dịch toàn bộ module liên quan từ một module source path sạch và chạy lại kiểm thử tích hợp.

Không nên gộp tất cả module chỉ để né lỗi. Chỉ gộp khi ranh giới module không còn mang lại lợi ích kiến trúc; nếu không, hãy sửa hướng phụ thuộc.

## 6. Ví dụ chạy được: ứng dụng có đồ thị không chu kỳ

Ví dụ gồm ba module: `com.example.app` phụ thuộc `com.example.service`, còn service phụ thuộc `com.example.model`. Đồ thị là app → service → model.

```text
src/
├── com.example.app/
│   ├── module-info.java
│   └── com/example/app/Main.java
├── com.example.service/
│   ├── module-info.java
│   └── com/example/service/Service.java
└── com.example.model/
    ├── module-info.java
    └── com/example/model/Model.java
```

**Module model — `src/com.example.model/module-info.java`**

```java
module com.example.model {
    exports com.example.model;
}
```

**`src/com.example.model/com/example/model/Model.java`**

```java
package com.example.model;

public final class Model {
    private Model() {}

    public static String version() {
        return "1.0";
    }
}
```

**Module service — `src/com.example.service/module-info.java`**

```java
module com.example.service {
    requires com.example.model;
    exports com.example.service;
}
```

**`src/com.example.service/com/example/service/Service.java`**

```java
package com.example.service;

public final class Service {
    private Service() {}

    public static String message() {
        return "Application ready with model "
                + com.example.model.Model.version();
    }
}
```

**Module app — `src/com.example.app/module-info.java`**

```java
module com.example.app {
    requires com.example.service;
}
```

**`src/com.example.app/com/example/app/Main.java`**

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println(com.example.service.Service.message());
    }
}
```

Tạo thư mục output trước khi biên dịch:

```powershell
New-Item -ItemType Directory -Force out
javac --module-source-path src -d out -m com.example.app,com.example.service,com.example.model
java --module-path out -m com.example.app/com.example.app.Main
```

Trên shell POSIX, lệnh tạo thư mục tương ứng là `mkdir -p out`; hai lệnh `javac` và `java` giữ nguyên.

Stdout:

```text
Application ready with model 1.0
```

### Tái hiện phụ thuộc thiếu lúc chạy

Giữ nguyên output đã biên dịch, nhưng chỉ đưa hai module app và service vào module path. Trên Windows PowerShell:

```powershell
java --module-path "out\com.example.app;out\com.example.service" -m com.example.app/com.example.app.Main
```

Trên Linux/macOS, dấu phân cách các mục của module path là `:`:

```bash
java --module-path "out/com.example.app:out/com.example.service" -m com.example.app/com.example.app.Main
```

Vì `com.example.model` bị bỏ khỏi module path, launcher báo `java.lang.module.FindException: Module com.example.model not found, required by com.example.service` và không gọi `main`.

### Tái hiện phụ thuộc thiếu lúc biên dịch

Tạo một bản sao của cây `src` chỉ chứa `com.example.app` và `com.example.service`, bỏ thư mục `com.example.model`, sau đó biên dịch hai module còn lại:

```powershell
New-Item -ItemType Directory -Force out-missing
javac --module-source-path src-missing -d out-missing -m com.example.app,com.example.service
```

Trình biên dịch báo `error: module not found: com.example.model`. Hãy kiểm tra thư mục nguồn đã bị bỏ hoặc module path của dependency chưa được cung cấp.

## 7. Tái hiện phụ thuộc vòng

Tạo hai module `com.example.a` và `com.example.b` theo hai descriptor ở mục 4. Mỗi module cần có một lớp Java trong package được export, ví dụ `A.java` và `B.java` với nội dung lần lượt `package com.example.a; public class A {}` và `package com.example.b; public class B {}`.

Tạo thư mục output rỗng rồi biên dịch:

```powershell
New-Item -ItemType Directory -Force cycle-out
javac --module-source-path cycle-src -d cycle-out -m com.example.a,com.example.b
```

Trên Linux/macOS, dùng `mkdir -p cycle-out` trước lệnh `javac`. Kết quả là lỗi `cyclic dependence involving` tại cả hai cạnh `requires`. Sửa descriptor để một module không phụ thuộc ngược vào module còn lại, rồi biên dịch lại.

## 8. Quy trình chẩn đoán thực tế

1. **Đọc tên module bị nêu trong lỗi.** Với `module not found`, ghi lại đúng tên module; không suy đoán từ tên file JAR.
2. **Kiểm tra descriptor.** Mở `module-info.java` hoặc chạy `jar --describe-module --file path/to/dependency.jar` để xác nhận tên module và các `requires` của nó.
3. **Kiểm tra hai classpath riêng biệt.** Đảm bảo module được đặt trên `--module-path`; đảm bảo `--module-source-path` có đúng thư mục module khi biên dịch từ nguồn.
4. **So sánh môi trường build và runtime.** Một module có thể có trong cấu hình biên dịch nhưng bị thiếu trong module path lúc chạy.
5. **Với lỗi chu kỳ, vẽ đồ thị cạnh `requires`.** Đi theo từng cạnh cho đến khi thấy đường quay lại module ban đầu; sửa kiến trúc thay vì thử thêm flag.
6. **Biên dịch lại từ output sạch.** Xóa output build tạm trong workspace thử nghiệm, tạo thư mục mới và biên dịch toàn bộ nhóm module để tránh dùng nhầm class cũ.
7. **Chạy kiểm thử tích hợp.** Khởi chạy module gốc với module path đúng như môi trường triển khai; xác minh cả trường hợp dependency thiếu được phát hiện sớm.

Để xem JVM đang phân giải module nào khi chạy thành công, có thể thêm `--show-module-resolution` vào lệnh `java`. Tùy chọn này hữu ích để đối chiếu module gốc và các phụ thuộc được nạp.

## 9. Những nhầm lẫn cần tránh

- **Nhầm module path với class path:** JAR trên class path thuộc unnamed module; nó không tự đáp ứng một `requires` có tên.
- **Nhầm thiếu module với thiếu package export:** module có thể tồn tại nhưng package cần dùng không được export hoặc module gọi không đọc được module chứa kiểu đó.
- **Dùng `requires transitive` để sửa dependency bị thiếu:** `transitive` chỉ truyền khả năng đọc cho module đọc module hiện tại; nó không cài đặt hoặc cung cấp module.
- **Dùng `requires static` cho dependency bắt buộc khi chạy:** `static` cho phép module vắng mặt ở runtime. Nếu ứng dụng thực sự cần nó, khai báo phụ thuộc thông thường.
- **Cho rằng thứ tự `requires` quyết định thứ tự biên dịch:** JPMS phân giải đồ thị module; việc đổi thứ tự các dòng không phá được chu kỳ.
- **Dùng automatic module như cách né lỗi kiến trúc:** automatic module giúp chuyển đổi thư viện chưa modular, nhưng không thay thế việc khai báo phụ thuộc rõ ràng cho thiết kế mới.

## Tài liệu tham khảo

1. [Java Language Specification, Java SE 25 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7), quy tắc khai báo module và các chỉ thị `requires`.
2. [Java Platform Module System — Module Resolution](https://docs.oracle.com/javase/9/docs/api/java/lang/module/package-summary.html), mô hình tìm và phân giải module trong JPMS.
3. [Java SE 25 API — ModuleFinder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleFinder.html), tìm module từ module path hoặc nguồn module.
4. [Java SE 25 API — FindException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/FindException.html) và [ResolutionException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ResolutionException.html), lỗi tìm module và lỗi phân giải cấu hình.
5. [The javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html), các tùy chọn `--module-source-path`, `--module-path` và `-m`.