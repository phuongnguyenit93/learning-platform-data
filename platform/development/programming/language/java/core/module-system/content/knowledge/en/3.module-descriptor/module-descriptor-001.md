# module-info.java và vai trò của module descriptor

Java Platform Module System (JPMS) bổ sung một lớp cấu trúc cho ứng dụng Java: thay vì chỉ đưa các thư mục và JAR vào classpath, ta có thể khai báo module nào tồn tại, module đó cần những module nào và package nào được phép sử dụng từ bên ngoài. Điểm khai báo ở mã nguồn của một named module là tệp `module-info.java`.

Tệp này được biên dịch thành `module-info.class`, chứa metadata được gọi là **module descriptor**. Descriptor không chứa logic nghiệp vụ. Nó mô tả hợp đồng của module với hệ thống: danh tính, dependency, API công khai, quyền reflection và các dịch vụ mà module sử dụng hoặc cung cấp.

## 1. module-info.java là gì?

`module-info.java` là một compilation unit đặc biệt của Java. Nó chứa một khai báo module ở cấp cao nhất, không khai báo một class thông thường và không nằm trong package của các lớp nghiệp vụ.

Ví dụ một module có tên `com.example.catalog`:

```text
catalog/
└── src/
    └── com.example.catalog/
        ├── module-info.java
        └── com/
            └── example/
                └── catalog/
                    ├── api/
                    │   └── Product.java
                    └── internal/
                        └── ProductRepository.java
```

Tệp descriptor nằm ở gốc source root của module. Các lớp còn lại vẫn được tổ chức trong package Java bình thường.

Một module có thể bắt đầu bằng descriptor rỗng:

```java
module com.example.catalog {
}
```

Khi cần sử dụng module khác hoặc công khai package, ta thêm các chỉ thị:

```java
module com.example.catalog {
    requires java.sql;

    exports com.example.catalog.api;
}
```

Trong ví dụ, module có tên `com.example.catalog`, cần đọc module `java.sql` và công khai package `com.example.catalog.api`.

Tên module thường theo quy ước tên miền đảo ngược, chẳng hạn `com.example.catalog`, để giảm khả năng xung đột tên. Tên module và tên package là hai khái niệm riêng: một module có thể chứa nhiều package.

## 2. Từ module-info.java đến module descriptor

Khi biên dịch một module, `javac` xử lý `module-info.java` cùng các tệp mã nguồn của module. Tệp descriptor ở dạng mã nguồn được chuyển thành `module-info.class`.

```text
module-info.java + các tệp .java
             |
             | javac
             v
       module-info.class
       các tệp .class
             |
             | đóng gói JAR
             v
       modular JAR
             |
             | module path
             v
       module resolution và module graph
```

Cần phân biệt hai thuật ngữ:

- **`module-info.java`** là tệp nguồn mà lập trình viên viết.
- **Module descriptor** là metadata mô tả module; trong artifact đã biên dịch, metadata này được lưu trong `module-info.class`.

Một modular JAR thường đặt `module-info.class` ở gốc JAR, bên cạnh các package và lớp đã biên dịch. Khi JAR được đặt trên module path, công cụ Java đọc descriptor để nhận diện module và các chỉ thị của nó.

Descriptor không chứa mã xử lý nghiệp vụ và cũng không phải toàn bộ module graph của ứng dụng. Mỗi descriptor mô tả module mà nó thuộc về. Khi chạy, Java kết hợp descriptor của các module có liên quan để phân giải module graph cho môi trường đó.

## 3. Cú pháp tổng quát

Một module declaration có dạng:

```java
[open] module module.name {
    requires other.module;
    exports some.package;
    opens another.package;
    uses some.service.Interface;
    provides some.service.Interface
        with some.provider.Implementation;
}
```

Các thành phần:

- `module` bắt đầu khai báo module.
- `module.name` là tên module.
- Từ khóa `open` là tùy chọn, dùng để mở tất cả package cho deep reflection.
- Các chỉ thị trong thân khai báo mô tả dependency, package, reflection và dịch vụ.

Một descriptor có thể không có chỉ thị nào. Khi module cần thêm khả năng, ta chỉ khai báo những quan hệ thực sự cần thiết. Các chỉ thị có thể được sắp xếp theo nhóm để người đọc dễ nhận ra dependency và API công khai.

## 4. Các chỉ thị trong module descriptor

### 4.1. requires: khai báo dependency

`requires` khai báo module hiện tại cần đọc một module khác:

```java
module com.example.orders {
    requires com.example.catalog;
    requires java.sql;
}
```

Nếu mã nguồn của `com.example.orders` sử dụng các kiểu được công khai bởi `com.example.catalog`, module orders cần khai báo quan hệ này. Java dùng thông tin đó khi biên dịch và phân giải module graph.

Mọi named module đều có quan hệ đọc tới `java.base` một cách ngầm định, vì vậy không cần viết `requires java.base;`. Những module JDK khác như `java.sql`, `java.logging` hoặc `java.xml` cần được khai báo khi module sử dụng chúng.

Có hai modifier thường gặp:

**`requires transitive`**

```java
module com.example.catalog {
    requires transitive com.example.money;
    exports com.example.catalog.api;
}
```

`transitive` công bố dependency cho các module đọc module hiện tại. Nếu API public của catalog sử dụng kiểu thuộc `com.example.money`, module sử dụng catalog có thể cần đọc cả money để biên dịch và sử dụng API đó. Khi đó, `requires transitive` thể hiện rằng dependency này là một phần của hợp đồng API.

Không nên dùng `transitive` chỉ để tiện truyền dependency. Nó ảnh hưởng đến khả năng đọc của các module phụ thuộc vào module hiện tại.

**`requires static`**

```java
module com.example.reporting {
    requires static com.example.annotations;
}
```

`static` biểu thị dependency cần có khi biên dịch nhưng không bắt buộc phải có ở runtime chỉ vì descriptor khai báo nó. Modifier này thường phù hợp với một số thư viện annotation hoặc dependency chỉ phục vụ compile time. Nếu mã thực tế cần lớp đó khi chạy, ứng dụng vẫn phải cung cấp dependency runtime tương ứng.

Có thể kết hợp hai modifier:

```java
requires static transitive com.example.annotations;
```

Chỉ dùng tổ hợp này khi cả ngữ nghĩa compile-time và dependency bắc cầu đều phù hợp với hợp đồng module.

### 4.2. exports: công khai package

`exports` cho phép module khác truy cập các kiểu public trong package được công khai:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Giả sử module có hai package:

```text
com.example.catalog
├── api
└── internal
```

Trong descriptor trên, `com.example.catalog.api` được công khai. Package `com.example.catalog.internal` không tự động trở thành API chỉ vì nó chứa các lớp có modifier `public`.

Có thể giới hạn việc export cho một số module cụ thể bằng qualified exports:

```java
module com.example.catalog {
    exports com.example.catalog.api;
    exports com.example.catalog.integration
        to com.example.orders, com.example.reporting;
}
```

Trong ví dụ, package integration chỉ được export cho hai module được nêu tên. Cách này hữu ích khi một package chỉ phục vụ một số thành phần tích hợp đã xác định.

Export không bỏ qua access modifier của Java. Lớp hoặc thành viên vẫn phải đáp ứng các quy tắc truy cập thông thường như `public`, `protected`, package-private và `private`. `exports` thiết lập ranh giới ở cấp package/module; nó không biến thành viên private thành public.

### 4.3. opens: cho phép deep reflection

Một số framework cần reflection sâu để truy cập thành viên không public, ví dụ framework ánh xạ object, dependency injection hoặc serialization. `opens` cho phép hoạt động đó trên package được chỉ định:

```java
module com.example.catalog {
    exports com.example.catalog.api;

    opens com.example.catalog.model
        to com.example.json;
}
```

Ở đây, package model được mở cho module `com.example.json`. Phạm vi mở có thể giới hạn theo module đích, giúp framework được cấp quyền cần thiết.

Cần phân biệt:

- `exports` công khai API Java thông thường.
- `opens` cho phép deep reflection tại runtime.
- Một package được export không mặc nhiên được mở cho reflection sâu.
- Một package được mở không tự động trở thành API công khai cho mã Java thông thường.

Nếu muốn mở package cho mọi module, có thể dùng:

```java
opens com.example.catalog.model;
```

Nên giới hạn phạm vi mở vào package và framework thực sự cần sử dụng.

### 4.4. open module: mở mọi package cho reflection

Có thể khai báo toàn module là open:

```java
open module com.example.legacy {
    requires java.sql;
    exports com.example.legacy.api;
}
```

Với `open module`, tất cả package của module được mở cho deep reflection tại runtime. Tuy nhiên, các package vẫn cần `exports` nếu muốn công khai API Java thông thường.

Một open module không khai báo các chỉ thị `opens` riêng lẻ bên trong. Chỉ nên dùng cách này khi framework thực sự cần reflection rộng; nếu chỉ một vài package cần thiết, qualified `opens` giữ ranh giới rõ hơn.

### 4.5. uses và provides: khai báo dịch vụ

JPMS tích hợp mô hình dịch vụ với `ServiceLoader`.

Module sử dụng service khai báo `uses`:

```java
module com.example.application {
    requires com.example.catalog.api;

    uses com.example.catalog.spi.PriceProvider;
}
```

Module cung cấp implementation khai báo `provides ... with ...`:

```java
module com.example.catalog.provider {
    requires com.example.catalog.api;

    provides com.example.catalog.spi.PriceProvider
        with com.example.catalog.provider.DefaultPriceProvider;
}
```

Ứng dụng có thể tìm provider bằng API `ServiceLoader`:

```java
ServiceLoader<PriceProvider> providers =
        ServiceLoader.load(PriceProvider.class);

for (PriceProvider provider : providers) {
    System.out.println(provider.priceFor("BOOK-01"));
}
```

Service interface thường nằm trong package được export để module tiêu thụ có thể tham chiếu. Lớp triển khai provider không cần được export chỉ để ServiceLoader phát hiện provider đã khai báo trong descriptor.

Cơ chế này cho phép module sử dụng phụ thuộc vào service interface thay vì gắn chặt vào một lớp triển khai cụ thể.

## 5. Module descriptor tham gia vào những giai đoạn nào?

### 5.1. Nhận diện module

Tên trong descriptor giúp công cụ Java nhận diện explicit named module trên module path. Tên module là danh tính được dùng trong các chỉ thị `requires` và khi phân giải module graph.

Một JAR chưa có `module-info.class` vẫn có thể được dùng như automatic module khi đặt trên module path. Tên của nó có thể đến từ thuộc tính `Automatic-Module-Name` trong manifest hoặc được suy ra từ tên JAR. Automatic module hỗ trợ chuyển đổi thư viện cũ, nhưng không cung cấp descriptor tường minh với ranh giới API chi tiết như explicit module.

### 5.2. Phân giải module graph

Các chỉ thị `requires` tạo quan hệ dependency. Khi khởi chạy ứng dụng modular, Java bắt đầu từ các root module và phân giải các module cần thiết dựa trên descriptor cùng những module có sẵn trên module path.

Nếu một dependency bắt buộc không tìm thấy hoặc module graph không thể phân giải hợp lệ, ứng dụng có thể thất bại trước khi logic nghiệp vụ chạy. Nhờ đó, một số lỗi cấu trúc được phát hiện sớm.

Module descriptor của từng module chỉ mô tả các quan hệ mà module đó khai báo. Module graph hoàn chỉnh là kết quả của quá trình phân giải trong môi trường chạy cụ thể.

### 5.3. Kiểm soát khả năng đọc và truy cập

`requires` xác định quan hệ đọc giữa các module. `exports` xác định package nào được truy cập như API công khai. `opens` xác định package nào được phép deep reflection.

Khi biên dịch, `javac` có thể báo lỗi nếu mã nguồn sử dụng một module chưa được đọc hoặc truy cập package không được export. Ở runtime, module system tiếp tục áp dụng các quy tắc truy cập tương ứng.

### 5.4. Công bố dịch vụ

`uses` và `provides` mô tả module tiêu thụ và module cung cấp service. Runtime có thể sử dụng metadata này khi tìm implementation thông qua `ServiceLoader`.

Nhờ đó, ứng dụng có thể thay đổi provider mà không phải sửa mọi nơi đang sử dụng service interface, miễn là provider mới đáp ứng cùng hợp đồng.

### 5.5. Hỗ trợ công cụ Java

Các công cụ JDK đọc module descriptor để hiển thị thông tin module, phân tích dependency hoặc tạo runtime image. Một số lệnh hữu ích:

```shell
jar --describe-module --file libs/catalog.jar
java --describe-module java.sql
jdeps --summary libs/catalog.jar
```

`jar --describe-module` hiển thị thông tin module của JAR; `java --describe-module` hiển thị thông tin module trong runtime image; `jdeps` hỗ trợ phân tích dependency từ artifact. Các công cụ này giúp kiểm tra metadata và đối chiếu descriptor với cấu trúc mã đã biên dịch.

## 6. Ví dụ hoàn chỉnh về module descriptor

Giả sử module geometry có package API, package nội bộ và một lớp chạy ứng dụng:

```text
src/
└── com.example.geometry/
    ├── module-info.java
    └── com/example/geometry/
        ├── api/
        │   └── Shape.java
        ├── internal/
        │   └── Circle.java
        └── app/
            └── Main.java
```

Tệp `Shape.java`:

```java
package com.example.geometry.api;

public interface Shape {
    double area();
}
```

Tệp `Circle.java`:

```java
package com.example.geometry.internal;

import com.example.geometry.api.Shape;

public final class Circle implements Shape {
    private final double radius;

    public Circle(double radius) {
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}
```

Tệp `Main.java`:

```java
package com.example.geometry.app;

import com.example.geometry.internal.Circle;

public class Main {
    public static void main(String[] args) {
        Circle circle = new Circle(2);
        System.out.println(circle.area());
    }
}
```

Descriptor:

```java
module com.example.geometry {
    exports com.example.geometry.api;
}
```

Module geometry chỉ export package API. Lớp `Main` vẫn có thể dùng `Circle` vì chúng thuộc cùng module. Module bên ngoài chỉ có thể sử dụng các kiểu public trong package API đã export.

Với cấu trúc source root ở trên, có thể biên dịch bằng:

```shell
javac --module-source-path src -d out -m com.example.geometry
```

Sau khi biên dịch, chạy lớp main:

```shell
java --module-path out -m com.example.geometry/com.example.geometry.app.Main
```

Tùy chọn `-m` chỉ định module và lớp main. Cú pháp `module-info.java` không có chỉ thị khai báo main class; lớp main được chỉ định khi chạy hoặc thông qua metadata đóng gói phù hợp.

## 7. Descriptor khác gì cấu hình Maven hoặc Gradle?

`module-info.java` thuộc mô hình module của nền tảng Java. Nó không thay thế `build.gradle`, `pom.xml` hay cấu hình dependency của công cụ build.

Ví dụ, Gradle khai báo dependency artifact:

```groovy
dependencies {
    implementation project(":catalog")
    implementation "org.example:json-library:1.2.0"
}
```

Descriptor khai báo quan hệ module mà mã Java cần đọc:

```java
module com.example.orders {
    requires com.example.catalog;
    requires com.example.json;
}
```

Hai lớp thông tin này có mục tiêu khác nhau:

- Gradle/Maven quản lý project, artifact, phiên bản, repository, plugin và task build.
- JPMS mô tả danh tính module, quan hệ đọc và ranh giới package.
- Cấu hình build phải cung cấp dependency trên đúng đường dẫn biên dịch và runtime để các module được phân giải.

Tên project Gradle, tên artifact Maven, tên JAR và tên module JPMS có thể khác nhau. Khi tích hợp thư viện, cần kiểm tra tên module thực tế mà JAR công bố, nhất là với automatic module hoặc thư viện bên thứ ba.

## 8. Những nhầm lẫn thường gặp

**Nhầm module-info.java là một class cấu hình.**

Đây là compilation unit đặc biệt chỉ chứa module declaration. Nó không có method để chạy và không phải nơi đặt logic nghiệp vụ.

**Nhầm tên module với tên package.**

Module có danh tính riêng và có thể chứa nhiều package. Một package không tự động là một module.

**Nhầm exports với opens.**

Export công khai API Java thông thường; open cho phép deep reflection. Framework cần reflection không nhất thiết yêu cầu export mọi package.

**Cho rằng export package làm mọi thành viên trở nên public.**

Các access modifier của Java vẫn có hiệu lực. Export không làm thành viên private hoặc package-private trở thành public.

**Khai báo quá nhiều requires.**

Mỗi dependency là một quan hệ kiến trúc được công bố. Dependency không cần thiết làm module graph phức tạp và che khuất quan hệ thực sự.

**Dùng requires transitive cho mọi dependency.**

Modifier này ảnh hưởng tới khả năng đọc của module phụ thuộc. Chỉ dùng khi dependency đó là một phần của hợp đồng API.

**Mở toàn module để sửa một lỗi reflection.**

Nếu chỉ một package cần framework truy cập sâu, hãy cân nhắc qualified opens để giới hạn quyền.

**Cho rằng descriptor quản lý phiên bản thư viện.**

JPMS khai báo quan hệ module, không chọn phiên bản artifact. Maven hoặc Gradle vẫn đảm nhiệm việc giải quyết dependency.

## 9. Nguyên tắc thiết kế module-info.java

Khi viết descriptor, nên áp dụng các nguyên tắc sau:

1. **Đặt tên module ổn định:** dùng quy ước nhất quán và giảm khả năng trùng tên.
2. **Khai báo dependency thực sự cần:** chỉ thêm `requires` cho module mà mã nguồn hoặc API sử dụng.
3. **Export API có chủ đích:** công khai những package mà người dùng module cần phụ thuộc.
4. **Giữ implementation nội bộ:** không export package chỉ để truy cập tiện hơn từ module khác.
5. **Mở reflection theo phạm vi hẹp:** ưu tiên qualified `opens` khi chỉ framework cụ thể cần quyền này.
6. **Dùng service cho điểm mở rộng:** cân nhắc `uses` và `provides` khi muốn tách module tiêu thụ khỏi implementation.
7. **Kiểm soát dependency bắc cầu:** chỉ dùng `requires transitive` khi API thực sự công bố dependency đó.
8. **Đối chiếu descriptor với build:** đảm bảo module path cung cấp đủ module và tên module khớp với khai báo.

Một descriptor rõ ràng thường ngắn và thể hiện được dependency cùng API cốt lõi. Nếu phải export gần như mọi package hoặc mở toàn bộ module, nên xem lại ranh giới module và cách tích hợp framework.

## Kết luận

`module-info.java` là nơi khai báo module ở mã nguồn. Khi biên dịch, nó tạo ra `module-info.class`, tức module descriptor mà công cụ Java sử dụng. Descriptor xác định tên module, dependency, package được export hoặc mở cho reflection và các quan hệ dịch vụ.

Descriptor cung cấp dữ liệu để trình biên dịch kiểm tra khả năng đọc và truy cập, để JVM phân giải module graph và thực thi ranh giới module, đồng thời hỗ trợ các công cụ phân tích và đóng gói runtime.

Hãy xem `module-info.java` như hợp đồng giữa một module với phần còn lại của ứng dụng: module cần gì, cung cấp API nào và package nào được giữ lại bên trong. Một hợp đồng rõ ràng giúp cấu trúc ứng dụng dễ hiểu và giúp nhóm phát triển thay đổi phần triển khai với ít rủi ro hơn.