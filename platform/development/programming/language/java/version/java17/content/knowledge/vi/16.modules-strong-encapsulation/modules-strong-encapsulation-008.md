# Giới hạn phạm vi --add-exports và --add-opens khi tích hợp bắt buộc

Java Platform Module System (JPMS) chia ứng dụng thành các module có tên, mỗi module khai báo dependency và những package được phép cung cấp cho module khác. Cơ chế này giúp giới hạn truy cập ở ranh giới module. Từ Java 17, việc đóng gói mạnh các API nội bộ của JDK được áp dụng nghiêm ngặt; một thư viện cũ dựa vào package không được export hoặc dùng reflection để chạm vào thành viên không public có thể gặp lỗi khi chạy.

Trong trường hợp tích hợp bắt buộc chưa thể thay thế ngay, Java cung cấp hai tùy chọn để mở đúng ranh giới cần thiết:

- **`--add-exports`**: export một package từ module nguồn cho module đích, cho phép code đích truy cập các kiểu và thành viên public trong package đó theo quy tắc Java.
- **`--add-opens`**: mở một package từ module nguồn cho module đích để reflection có thể truy cập sâu vào các thành viên không public tại runtime.

Hai tùy chọn này giải quyết hai loại truy cập khác nhau. Dùng nhầm tùy chọn thường không sửa được lỗi; mở rộng phạm vi quá mức lại làm suy yếu lợi ích đóng gói của module. Bài học này tập trung vào cú pháp, phạm vi tối thiểu, cấu hình compile/runtime và cách giới hạn ngoại lệ khi một integration thực sự cần chúng.

## 1. Vì sao module cần exports và opens?

Một module có thể chứa nhiều package, nhưng không phải package nào cũng là API công khai. Ví dụ:

```text
com.example.payment
├── com.example.payment.api
├── com.example.payment.spi
└── com.example.payment.internal
```

Module có thể chỉ export `api` và `spi`; package `internal` được giữ bên trong:

```java
module com.example.payment {
    exports com.example.payment.api;
    exports com.example.payment.spi;
}
```

Một module khác có thể sử dụng các public type thuộc package đã export. Nhưng nó không thể tùy ý import các type trong `com.example.payment.internal`.

Đóng gói module có hai lớp cần phân biệt:

1. **Readability:** module hiện tại có đọc module kia hay không. Thường được khai báo bằng `requires` trong `module-info.java`.
2. **Accessibility/export:** package của module kia có được export cho module hiện tại hay không.

`--add-exports` và `--add-opens` xử lý quyền truy cập package theo những cách khác nhau. Chúng **không thay thế `requires` và không tự thêm quan hệ readability** cho code Java thông thường.

### 1.1. Ví dụ module chỉ export API

```java
module com.example.payment {
    exports com.example.payment.api;
}
```

Code bên ngoài có thể dùng các public type thuộc `com.example.payment.api` nếu module bên ngoài cũng đọc module này. Các package khác vẫn được đóng kín đối với truy cập thông thường từ module ngoài.

### 1.2. Đóng gói mạnh trong JDK

Từ Java 9, các module nền tảng đã tổ chức API theo module và package. Những package công khai được mô tả trong tài liệu API; các package nội bộ của JDK không phải cam kết tương thích cho ứng dụng.

Java 17 tiếp tục đóng gói mạnh các thành phần nội bộ của JDK theo JEP 403. Vì vậy, một thư viện từng truy cập `sun.*`, `com.sun.*` hoặc `jdk.internal.*` có thể không còn chạy nếu dựa vào quyền truy cập không được hỗ trợ.

Không nên coi `--add-exports` là cách biến API nội bộ thành API được hỗ trợ lâu dài. Tùy chọn chỉ nới ranh giới module cho một package và target được chỉ định; nó không tạo cam kết rằng package đó sẽ tồn tại hoặc giữ nguyên trong bản JDK tương lai.

## 2. --add-exports: cho phép truy cập kiểu và thành viên public

`--add-exports` export một package từ module nguồn cho một hoặc nhiều module đích.

Cú pháp:

```text
--add-exports <source-module>/<package>=<target-module>(,<target-module>)*
```

Có thể viết dấu `=` liền với option:

```text
--add-exports=java.base/jdk.internal.misc=com.example.app
```

Ý nghĩa từng thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `source-module` | Module đang chứa package cần export. |
| `package` | Tên package cần mở quyền truy cập kiểu public. |
| `target-module` | Module nhận quyền truy cập package đó. |
| `ALL-UNNAMED` | Tất cả unnamed module, thường là code được nạp từ classpath. |

Ví dụ giả định:

```text
--add-exports=com.vendor.legacy/com.vendor.internal=com.example.app
```

Tùy chọn này cho module `com.example.app` truy cập các public type trong package `com.vendor.internal` thuộc module `com.vendor.legacy`, nếu module ứng dụng cũng đọc module nguồn.

### 2.1. --add-exports không mở private member cho reflection sâu

`--add-exports` cho phép truy cập thông thường tới **public types và public/protected members** trong package được export, theo các quy tắc truy cập của Java.

Nó không có nghĩa:

- Mọi package khác của module nguồn cũng được export.
- Mọi lớp hoặc thành viên package-private/private đều trở thành public.
- Reflection có thể gọi `setAccessible(true)` trên private field hoặc private method của package đó.
- Module đích tự động có quyền đọc module nguồn.

Nếu thư viện cần đọc hoặc ghi private field qua reflection, cần xem xét `--add-opens`, không phải chỉ thêm `--add-exports`.

### 2.2. Cấu hình lúc biên dịch

Khi code module cần import public type từ một package chưa export, `javac` hỗ trợ `--add-exports`:

```bash
javac --module-path mods --add-exports=com.vendor.legacy/com.vendor.internal=com.example.app -d out ...
```

Trong ví dụ, module ứng dụng vẫn phải khai báo dependency nếu nó cần đọc module nguồn:

```java
module com.example.app {
    requires com.vendor.legacy;
}
```

`--add-exports` xử lý việc package được export cho module đích; `requires` xử lý quan hệ readability. Một quyền không tự suy ra quyền còn lại.

### 2.3. Cấu hình lúc chạy

Nếu code được biên dịch dựa trên export bổ sung, runtime cũng cần cấu hình tương ứng:

```bash
java --module-path mods --add-exports=com.vendor.legacy/com.vendor.internal=com.example.app -m com.example.app/com.example.app.Main
```

Nếu chỉ thêm tùy chọn lúc compile mà quên lúc chạy, module system vẫn có thể chặn truy cập khi ứng dụng thực thi.

## 3. --add-opens: cho phép reflection truy cập sâu

`--add-opens` mở một package để code trong module đích có thể thực hiện **deep reflection** trên các thành viên của package tại runtime.

Cú pháp:

```text
--add-opens <source-module>/<package>=<target-module>(,<target-module>)*
```

Ví dụ:

```text
--add-opens=com.example.app/com.example.domain=com.example.orm
```

Giả sử module `com.example.app` có package `com.example.domain` chứa các model với field private. ORM `com.example.orm` cần dùng reflection để đọc/ghi những field đó. Tùy chọn trên mở đúng package domain cho đúng module ORM.

### 3.1. Vì sao reflection cần opens?

Một lớp có thể có field private:

```java
package com.example.domain;

public class Customer {
    private String email;

    public Customer(String email) {
        this.email = email;
    }
}
```

Thư viện ORM có thể tìm field bằng reflection và muốn truy cập giá trị dù field không public. Trên module path, package phải được open cho module thực hiện deep reflection.

Nếu package chưa mở, các thao tác như `Field.setAccessible(true)` có thể ném `InaccessibleObjectException` (một loại runtime exception) khi module system từ chối quyền truy cập.

Khi đã mở package đúng cho module ORM, framework có thể thực hiện deep reflection theo quy tắc reflection của Java.

### 3.2. --add-opens chỉ có tác dụng lúc runtime

`--add-opens` là tùy chọn runtime của Java launcher; nó không phải tùy chọn biên dịch để cho phép code import một package chưa export.

Ví dụ:

```bash
java --module-path mods --add-opens=com.example.app/com.example.domain=com.example.orm -m com.example.app/com.example.app.Main
```

Nếu cần mở package trong cấu hình module lâu dài, có thể khai báo `opens` trong `module-info.java`:

```java
module com.example.app {
    opens com.example.domain to com.example.orm;
}
```

`opens` trong module descriptor và `--add-opens` đều hướng tới quyền truy cập reflection tại runtime. Dạng khai báo trong descriptor có lợi khi chính module sở hữu package kiểm soát được cấu hình; command line hữu ích khi tích hợp bên ngoài chưa thể sửa module descriptor.

### 3.3. opens không phải exports

Một package được mở cho reflection không tự động trở thành API mà module khác có thể import trong mã Java:

```java
module com.example.app {
    opens com.example.domain to com.example.orm;
}
```

Module `com.example.orm` có thể dùng deep reflection vào package domain khi module graph và các điều kiện liên quan phù hợp. Nhưng `opens` không thay thế `exports` cho truy cập Java thông thường tới public type.

Ngược lại, export một package không có nghĩa module khác được phép phá encapsulation để truy cập private member qua reflection.

## 4. So sánh trực tiếp --add-exports và --add-opens

| Tiêu chí | `--add-exports` | `--add-opens` |
| --- | --- | --- |
| Mục tiêu | Truy cập kiểu/thành viên public trong package | Deep reflection vào thành viên package, kể cả không public |
| Thời điểm | Compile time và runtime | Runtime |
| Dùng với `javac` | Có | Không |
| Dùng với Java launcher | Có | Có |
| Cho phép import public type trong package chưa export | Có, nếu module readability cũng được đáp ứng | Không |
| Cho phép reflection truy cập private member | Không tự cấp quyền này | Có thể, trong phạm vi package và target đã mở |
| Khai báo tương ứng trong `module-info.java` | `exports p to m;` | `opens p to m;` |
| Phạm vi | Một package và target cụ thể | Một package và target cụ thể |

Hãy chọn theo loại lỗi:

- `package ... is not visible` hoặc compile error do package không export: xem `requires` và `--add-exports`.
- `InaccessibleObjectException` khi framework dùng reflection vào private field/method: xem `opens` hoặc `--add-opens`.
- `module X does not read module Y`: kiểm tra `requires` hoặc cơ chế readability phù hợp; không giải quyết chỉ bằng `--add-exports`/`--add-opens`.

## 5. Xác định đúng source module, package và target module

Một tùy chọn chỉ có tác dụng nếu cả ba phần được xác định chính xác.

### 5.1. Source module

Đây là module **sở hữu package đang cần export/open**. Nó không nhất thiết là module của thư viện đang gọi.

Ví dụ:

```text
com.example.app/com.example.domain
^^^^^^^^^^^^^^^^
source module
```

Nếu package nằm trong module ứng dụng, source module là `com.example.app`. Nếu package nằm trong JDK, source module có thể là `java.base`, `java.sql`, `java.desktop` hoặc module JDK khác.

### 5.2. Package

Package phải là tên package chính xác, không phải tên class hoặc tên file JAR.

Ví dụ:

```text
com.example.app/com.example.domain=com.example.orm
                        ^^^^^^^^^^^^^^^^^^^^^
                        package
```

Option chỉ export/open package được chỉ định. Nó không tự áp dụng cho package con như `com.example.domain.internal`; nếu cần package khác, phải đánh giá và cấu hình riêng.

### 5.3. Target module

Target là module sẽ nhận quyền:

- Nếu caller là named module, ghi tên module đó, ví dụ `com.example.orm`.
- Nếu caller nằm trên classpath, code của nó thuộc unnamed module; dùng `ALL-UNNAMED` khi thực sự cần cấp quyền cho các unnamed module.

Không dùng tên JAR như `orm-1.2.jar` làm target module. Hãy xác định module name trong `module-info.java`, metadata `Automatic-Module-Name` hoặc tên module được hệ thống module suy ra.

### 5.4. Giới hạn của ALL-UNNAMED

Ví dụ:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
```

Tùy chọn này mở package `java.lang` trong module `java.base` cho **mọi unnamed module** trong JVM. Nó có phạm vi rộng hơn việc mở package cho một module cụ thể.

Chỉ dùng `ALL-UNNAMED` khi caller thực sự chạy trong unnamed module và không thể xác định target module hẹp hơn. Nếu thư viện đã là named module, hãy chỉ định tên module của thư viện.

## 6. Ví dụ tích hợp ORM cần reflection vào model

Giả sử ứng dụng có hai module:

```text
com.example.app
  └── com.example.domain.Customer

com.example.orm
  └── framework cần đọc private field của Customer
```

Module ứng dụng:

```java
module com.example.app {
    requires com.example.orm;
    exports com.example.api;
}
```

Module ORM có thể sử dụng public API của ứng dụng qua các package đã export. Nếu framework phải truy cập private field trong package domain, mở đúng package:

```java
module com.example.app {
    requires com.example.orm;
    exports com.example.api;
    opens com.example.domain to com.example.orm;
}
```

Hoặc, khi không thể sửa module descriptor của ứng dụng, truyền option lúc chạy:

```bash
java --module-path mods --add-opens=com.example.app/com.example.domain=com.example.orm -m com.example.app/com.example.app.Main
```

Ở đây chỉ `com.example.domain` được mở và chỉ module `com.example.orm` nhận quyền deep reflection. Package API khác vẫn giữ chính sách export/open riêng.

### 6.1. Nếu ORM nằm trên classpath

Nếu ORM chưa được đóng gói thành named module và được nạp từ classpath, target của tùy chọn là `ALL-UNNAMED`:

```bash
java --module-path mods --class-path "libs/orm.jar" --add-opens=com.example.app/com.example.domain=ALL-UNNAMED -m com.example.app/com.example.app.Main
```

Đây là ví dụ về phạm vi cho caller trên classpath. Trong ứng dụng thực tế, còn phải bảo đảm quan hệ readability và cách tích hợp classpath/module path phù hợp với module graph của ứng dụng. Không thêm `ALL-UNNAMED` chỉ để thử vận may khi chưa biết framework được nạp từ đâu.

## 7. Ví dụ thư viện cần public type trong package chưa export

Trường hợp khác: ứng dụng cần biên dịch và gọi một public class trong package của module thư viện chưa export.

Giả sử:

```java
module com.vendor.legacy {
    // Không export com.vendor.legacy.internal
}
```

Ứng dụng:

```java
module com.example.app {
    requires com.vendor.legacy;
}
```

Nếu integration bắt buộc dùng public type từ `com.vendor.legacy.internal`, có thể tạm thêm export khi compile:

```bash
javac --module-path mods --add-exports=com.vendor.legacy/com.vendor.legacy.internal=com.example.app -d out ...
```

Và khi chạy:

```bash
java --module-path mods --add-exports=com.vendor.legacy/com.vendor.legacy.internal=com.example.app -m com.example.app/com.example.app.Main
```

Nếu có thể sửa module sở hữu package và việc export phù hợp với thiết kế API, một qualified export rõ ràng trong module descriptor sẽ dễ quản lý hơn:

```java
module com.vendor.legacy {
    exports com.vendor.legacy.internal to com.example.app;
}
```

Nhưng nếu package có tên `internal`, việc phụ thuộc vào nó vẫn là coupling với chi tiết triển khai. Hãy xem đây là ngoại lệ tích hợp có thời hạn và có kế hoạch thay thế bằng API được hỗ trợ.

## 8. Dùng option trên JDK internals: chỉ khi không còn lựa chọn phù hợp

Một thư viện cũ có thể phụ thuộc package nội bộ của JDK. Ví dụ cú pháp export một package nội bộ của `java.base` cho ứng dụng:

```bash
java --add-exports=java.base/jdk.internal.misc=com.example.app --module-path mods -m com.example.app/com.example.app.Main
```

Đây là ví dụ về **cách giới hạn target**, không phải lời khuyên phụ thuộc `jdk.internal.misc`. Package nội bộ có thể thay đổi hoặc bị loại bỏ; tùy chọn chỉ nới module access trong lần chạy hiện tại.

Trước khi thêm option, nên:

1. Xác định chính xác stack trace và package bị chặn.
2. Kiểm tra thư viện đã có phiên bản mới hỗ trợ Java 17 hay chưa.
3. Tìm API công khai được JDK hỗ trợ thay thế.
4. Nếu buộc phải giữ dependency, chỉ export/open package cần thiết cho module thực sự gọi nó.
5. Ghi lại lý do và điều kiện gỡ bỏ option.

Có thể dùng công cụ `jdeps` để tìm dependency tới JDK internal API:

```bash
jdeps --jdk-internals app.jar
```

Kết quả giúp nhận diện những package nội bộ mà artifact đang phụ thuộc. Việc tìm thấy dependency không có nghĩa cứ thêm `--add-exports` là giải pháp lâu dài; hãy xem cảnh báo và thay thế API khi có thể.

## 9. Không dùng --illegal-access như một cách mở rộng thay thế

`--illegal-access` từng được dùng trong các giai đoạn chuyển tiếp của hệ module để nới một số truy cập reflection tới JDK internals. Trên **Java 17**, tùy chọn này không còn là cách bật lại cơ chế truy cập cũ; nó không vô hiệu hóa strong encapsulation và chỉ có thể phát ra cảnh báo rằng tùy chọn không còn hiệu lực.

Không nên thêm:

```bash
# Không dùng như giải pháp trên Java 17:
java --illegal-access=permit -jar app.jar
```

Nếu một thư viện cần quyền truy cập package cụ thể, xác định đúng nhu cầu và dùng `--add-exports` hoặc `--add-opens` với target hẹp, sau khi đã cân nhắc nâng cấp hoặc thay thư viện.

## 10. Chọn mức mở nhỏ nhất có thể

Khi tích hợp bắt buộc, mục tiêu là giảm số package và số module được cấp quyền.

### 10.1. Ưu tiên named target

Nếu ORM là module `com.example.orm`, dùng:

```text
--add-opens=com.example.app/com.example.domain=com.example.orm
```

Chỉ dùng `ALL-UNNAMED` nếu caller thực sự là code trên classpath.

### 10.2. Mở đúng package

Nếu framework chỉ cần reflection vào `com.example.domain`, không mở toàn bộ module:

```java
module com.example.app {
    opens com.example.domain to com.example.orm;
}
```

Tránh `open module com.example.app { ... }` nếu chỉ một package cần reflection. `open module` làm mọi package trong module được mở cho deep reflection ở runtime, phạm vi rộng hơn nhiều.

### 10.3. Không export hoặc open cả module

Option không có cú pháp “export toàn bộ module” theo cách thay thế cho việc chọn package. Mỗi option nên nêu rõ package cần cấp quyền. Nếu một integration cần nhiều package, hãy liệt kê từng package và xác minh từng nhu cầu thay vì dùng một cấu hình rộng không rõ lý do.

### 10.4. Tránh mở JDK internals cho mọi code

Ví dụ sau có phạm vi rất rộng:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
```

Nó cho tất cả unnamed modules deep reflection vào package `java.lang`. Chỉ dùng nếu có bằng chứng một thư viện trên classpath thực sự cần quyền này và không thể nâng cấp/thay thế ngay. Nếu caller là named module, chỉ định module đó thay vì mở cho tất cả.

## 11. Quản lý option ở môi trường chạy ứng dụng

Các option phải được truyền tới **JVM thực sự chạy code cần quyền truy cập**. Việc thêm chúng vào một lệnh build không tự động đảm bảo JVM chạy ứng dụng hoặc test nhận được cấu hình.

Một số nơi cần xem xét:

- Lệnh chạy trực tiếp bằng `java`.
- Script khởi động dịch vụ hoặc container entrypoint.
- Cấu hình JVM options của application server.
- JVM fork riêng khi chạy test.
- Runtime của công cụ build khi nó khởi chạy tiến trình con.
- Cấu hình triển khai ở môi trường staging/production.

Ví dụ chạy ứng dụng module:

```bash
java --add-opens=com.example.app/com.example.domain=com.example.orm --module-path mods -m com.example.app/com.example.app.Main
```

Đừng nhầm JVM của Maven/Gradle với JVM của test hoặc ứng dụng được fork. Nếu lỗi chỉ xảy ra trong test, cần đặt option vào JVM test tương ứng; nếu lỗi ở production, cấu hình trong tiến trình production.

### 11.1. Dùng biến môi trường JDK_JAVA_OPTIONS

Java launcher hỗ trợ biến môi trường `JDK_JAVA_OPTIONS` để thêm option vào lệnh launcher:

```bash
JDK_JAVA_OPTIONS="--add-opens=com.example.app/com.example.domain=com.example.orm" java --module-path mods -m com.example.app/com.example.app.Main
```

Cách đặt biến môi trường khác nhau theo shell và hệ điều hành. Chỉ dùng cơ chế này khi đội vận hành quản lý rõ môi trường tiến trình. Với triển khai cần tái lập, cấu hình option ngay trong script hoặc manifest triển khai thường dễ kiểm soát và kiểm toán hơn.

### 11.2. Tránh cấu hình bị thất lạc giữa các môi trường

Nếu một option chỉ có ở máy phát triển, ứng dụng có thể chạy local nhưng thất bại ở staging hoặc production. Nên lưu cấu hình cùng nơi quản lý runtime của ứng dụng, ghi chú:

- Package được export/open.
- Module nhận quyền.
- Thư viện hoặc tính năng đang cần quyền đó.
- Phiên bản thư viện/JDK đã kiểm tra.
- Điều kiện để gỡ option.

Không nên thêm option vào mọi môi trường hoặc mọi JVM một cách tự động khi chưa xác định tiến trình nào cần quyền.

## 12. Cách chẩn đoán lỗi module access

Khi gặp lỗi, hãy phân loại theo thông báo:

| Thông báo hoặc tình huống | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `package ... is not visible` | Package không export cho module đang compile. | Kiểm tra `requires`, `exports` hoặc `--add-exports`. |
| `module X does not read module Y` | Thiếu quan hệ readability. | Khai báo `requires` hoặc cấu hình readability phù hợp; export không thay thế điều này. |
| `InaccessibleObjectException` | Reflection bị module system chặn do package chưa open. | Mở đúng package cho module caller bằng `opens` hoặc `--add-opens`. |
| `IllegalAccessError` lúc runtime | Quyền truy cập module lúc chạy khác với lúc compile hoặc package không được export. | Đối chiếu runtime options và module graph thực tế. |
| Lỗi chỉ xảy ra khi dùng classpath | Caller thuộc unnamed module hoặc cấu hình target chưa đúng. | Xác định module của caller; chỉ dùng `ALL-UNNAMED` nếu phù hợp. |
| Option không sửa được lỗi | Dùng sai package, sai source/target module hoặc nhầm loại quyền. | Kiểm tra chính xác stack trace, module name và loại truy cập cần thiết. |

Một quy trình thực tế:

1. Đọc thông báo đầy đủ và xác định module nguồn, package bị chặn, module caller.
2. Xác định code đang cần import public type hay reflection vào thành viên không public.
3. Kiểm tra module descriptor và cách thư viện được nạp (module path hay classpath).
4. Chọn `--add-exports` hoặc `--add-opens` theo đúng nhu cầu.
5. Giới hạn target vào module cụ thể; chỉ dùng `ALL-UNNAMED` khi caller nằm trong unnamed module.
6. Kiểm tra cả compile-time và runtime nếu dùng `--add-exports`.
7. Chạy lại trong đúng JVM của test hoặc ứng dụng.
8. Ghi lại kế hoạch loại bỏ option khi dependency được nâng cấp.

## 13. Ví dụ tổng hợp: phân biệt compile access và deep reflection

Giả sử ứng dụng tích hợp một thư viện legacy:

- Thư viện có public type trong package chưa export; ứng dụng cần import type đó.
- Một ORM khác cần reflection vào private field trong model của ứng dụng.

Hai yêu cầu này cần hai cấu hình riêng:

```bash
# Cho app truy cập public type của package legacy:
javac --module-path mods --add-exports=com.vendor.legacy/com.vendor.legacy.internal=com.example.app -d out ...

# Khi chạy: giữ export và mở package model cho ORM:
java --module-path mods --add-exports=com.vendor.legacy/com.vendor.legacy.internal=com.example.app --add-opens=com.example.app/com.example.domain=com.example.orm -m com.example.app/com.example.app.Main
```

Trong ví dụ này:

- `--add-exports` cấp quyền truy cập public API của package legacy cho app.
- `--add-opens` cấp quyền deep reflection vào package model cho ORM.
- `requires` trong module descriptor vẫn phải mô tả dependency cần thiết.
- Không mở package legacy cho ORM nếu ORM không cần nó.
- Không mở package model cho mọi unnamed module nếu ORM đã là named module.

Đây là hai ngoại lệ có mục tiêu khác nhau; không nên gộp chúng thành một cấu hình “mở module” chung.

## 14. Lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao xảy ra | Cách khắc phục |
| --- | --- | --- |
| Dùng `--add-opens` để sửa lỗi import package. | `opens` chỉ phục vụ deep reflection runtime, không export package cho compile-time. | Dùng `--add-exports` hoặc khai báo `exports` phù hợp. |
| Dùng `--add-exports` nhưng `setAccessible(true)` vẫn bị chặn. | Export không mở private member cho deep reflection. | Dùng `--add-opens` hoặc `opens` cho đúng caller. |
| Thêm option cho sai source module. | Module được ghi không sở hữu package trong stack trace. | Xác định module chứa package bằng module descriptor hoặc tài liệu module. |
| Ghi tên JAR làm target module. | Target phải là module name, không phải filename. | Dùng tên trong `module-info.java`, `Automatic-Module-Name` hoặc module name được suy ra. |
| Dùng `ALL-UNNAMED` dù thư viện là named module. | Cấp quyền cho mọi unnamed module, không đúng đối tượng cần quyền. | Dùng module name chính xác của thư viện. |
| Chỉ thêm `--add-exports` khi compile. | Runtime module graph vẫn có thể chặn truy cập. | Truyền export tương ứng vào JVM chạy ứng dụng. |
| Nghĩ export package đồng nghĩa module đã được đọc. | Readability và export là hai điều kiện riêng. | Bổ sung `requires` hoặc cấu hình readability phù hợp. |
| Mở toàn bộ module để sửa lỗi một field. | Phạm vi deep reflection lớn hơn nhu cầu. | Dùng qualified `opens` cho đúng package và target. |
| Dùng `--illegal-access=permit` trên Java 17. | Tùy chọn chuyển tiếp cũ không còn mở lại encapsulation. | Dùng API công khai hoặc option chính xác sau khi xác định nhu cầu. |
| Quên option trong JVM test/production. | Build JVM và runtime JVM có thể là các tiến trình khác nhau. | Cấu hình ở đúng tiến trình thực thi code cần quyền. |

## 15. Nguyên tắc giới hạn quyền khi tích hợp bắt buộc

Khi không thể loại bỏ ngay một dependency cần quyền đặc biệt, hãy áp dụng các nguyên tắc sau:

1. **Chỉ cấp đúng loại quyền:** public API cần export; deep reflection cần open.
2. **Chỉ chọn đúng package:** không mở package anh em hoặc toàn module nếu không có bằng chứng cần thiết.
3. **Chỉ chọn đúng caller:** ưu tiên tên named module; `ALL-UNNAMED` chỉ khi code gọi thực sự thuộc unnamed module.
4. **Giữ readability tách biệt:** xử lý `requires`/module graph độc lập với export/open.
5. **Đặt option ở đúng runtime:** bảo đảm test, service hoặc ứng dụng fork nhận đúng cấu hình.
6. **Ưu tiên API được hỗ trợ:** nâng cấp thư viện, dùng SPI hoặc API công khai trước khi truy cập nội bộ.
7. **Ghi nhận và gỡ bỏ:** mỗi ngoại lệ cần có lý do, chủ sở hữu và điều kiện loại bỏ.

Mở package là một quyết định về ranh giới module. Một cấu hình nhỏ, rõ module đích và có thời hạn sẽ dễ kiểm soát hơn một option rộng được thêm vào để làm cho lỗi biến mất.

## 16. Bài tập thực hành

### Bài 1 — Chọn đúng option

Một ứng dụng không biên dịch được vì cần import public class từ package chưa export của module `com.vendor.lib`. Xác định option cần dùng và giải thích vì sao `--add-opens` không giải quyết lỗi import.

### Bài 2 — Deep reflection

Một ORM chạy trong module `com.example.orm` cần đọc private field trong package `com.example.model` thuộc module `com.example.app`. Viết option runtime có phạm vi tối thiểu. Sau đó viết directive `opens` tương đương trong `module-info.java`.

### Bài 3 — Caller trên classpath

Một framework cũ chạy trên classpath cần reflection vào package `com.example.model` của ứng dụng module. Viết option phù hợp và giải thích `ALL-UNNAMED` cấp quyền cho nhóm caller nào.

### Bài 4 — Tách readability và exports

Ứng dụng đã có `--add-exports` nhưng compiler báo module `com.example.app` không đọc `com.vendor.lib`. Phân tích vì sao export không tự thêm readability và viết dependency cần thiết.

### Bài 5 — Giới hạn phạm vi

Một ứng dụng đang dùng `--add-opens=com.example.app/com.example=ALL-UNNAMED`, nhưng stack trace cho thấy chỉ ORM module `com.example.orm` cần reflection vào package `com.example.model`. Đề xuất cấu hình hẹp hơn và giải thích rủi ro của cấu hình hiện tại.

### Bài 6 — Kế hoạch loại bỏ workaround

Một thư viện đang dùng JDK internal package và yêu cầu `--add-exports`. Hãy lập kế hoạch kiểm tra dependency bằng `jdeps --jdk-internals`, tìm API thay thế, nâng cấp thư viện và kiểm thử sau khi gỡ option.

## 17. Tài liệu Java 17 chính thức

- [Java SE 17 Launcher — add-exports và add-opens](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cú pháp và cách truyền option cho JVM.
- [Java SE 17 javac — add-exports](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): tùy chọn export bổ sung trong lúc biên dịch.
- [JLS Java SE 17, §7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): khai báo module, `requires`, `exports`, `opens` và các directive liên quan.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): thiết kế module system và các tùy chọn điều chỉnh ranh giới module.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): đóng gói mạnh các thành phần nội bộ của JDK trong các bản Java hiện đại.
- [Java SE 17 jdeps tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích dependency, bao gồm phụ thuộc vào JDK internal API.

Khi tích hợp bắt buộc, hãy nhớ: **`--add-exports` dành cho truy cập public qua ranh giới package; `--add-opens` dành cho deep reflection tại runtime**. Xác định đúng source module, package và target module; chỉ cấp quyền nhỏ nhất cần thiết, đồng thời giữ quan hệ readability riêng. Đây là workaround có phạm vi rõ ràng, không phải lý do để phụ thuộc lâu dài vào API nội bộ của JDK.
