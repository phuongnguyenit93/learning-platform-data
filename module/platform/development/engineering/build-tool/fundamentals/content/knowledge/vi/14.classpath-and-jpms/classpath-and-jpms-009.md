# Phụ thuộc có thể đọc và package được xuất trong mô hình JPMS

JPMS (Java Platform Module System) bổ sung một lớp tổ chức và kiểm soát truy cập cho ứng dụng Java. Trong mô hình module, việc một thư viện có mặt trên module path chưa đủ để một module khác sử dụng nó. Module sử dụng phải có quyền **đọc** module cung cấp, và module cung cấp phải **xuất** package chứa API mà consumer cần truy cập.

Hai quy tắc này được khai báo trong tệp **module-info.java**. Mệnh đề **requires** tạo quan hệ readability giữa các module; mệnh đề **exports** công khai package cho module khác. Hiểu đúng hai khái niệm này giúp giải thích các lỗi như module không đọc module khác, package không được export, hoặc thư viện có trong dependency graph nhưng mã nguồn vẫn không thể import lớp.

## 1. JPMS và ranh giới module

Trước JPMS, Java thường tổ chức mã nguồn theo package và classpath. Package giúp nhóm lớp theo namespace, nhưng bản thân package không tạo ra ranh giới module có metadata về dependency và quyền truy cập.

JPMS giới thiệu **named module**. Một module có:

- Tên module duy nhất trong module graph.
- Các package và lớp thuộc module đó.
- Những module mà nó yêu cầu đọc.
- Những package mà nó xuất cho module khác.
- Có thể có thêm quy tắc mở package cho reflection.

Ví dụ, một ứng dụng có thể chia thành hai module:

~~~text
project/
├── geometry/
│   └── src/main/java/
│       ├── module-info.java
│       └── com/example/geometry/api/Point.java
└── app/
    └── src/main/java/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

Module **com.example.geometry** cung cấp API hình học. Module **com.example.app** sử dụng API đó. JPMS yêu cầu cả hai phía khai báo đúng quan hệ: module app cần đọc geometry, và geometry cần export package chứa Point.

Một module có thể nằm trong thư mục module đã biên dịch, trong JAR có module descriptor, hoặc là automatic module được đặt trên module path.

## 2. Module descriptor và module-info.java

Tệp **module-info.java** là module descriptor. Nó nằm ở gốc source set của module, bên ngoài các thư mục package.

Một descriptor tối giản:

~~~java
module com.example.geometry {
}
~~~

Tên sau từ khóa **module** là tên module. Tên này là định danh được dùng trong các mệnh đề requires, exports, opens, uses và provides.

Một descriptor có thể khai báo:

~~~java
module com.example.geometry {
    requires java.logging;
    exports com.example.geometry.api;
}
~~~

Trong ví dụ:

- **requires java.logging** khai báo module geometry cần đọc module java.logging.
- **exports com.example.geometry.api** công khai package API cho các module khác đọc geometry.

Tên module không nhất thiết giống tên package, group ID hay tên file JAR. Khi dùng module path, hãy phân biệt tên module trong descriptor với tọa độ artifact của dependency.

## 3. Readability là gì?

**Readability** là quan hệ cho biết một module có thể đọc các kiểu và API được module khác cung cấp hay không.

Nếu module A khai báo:

~~~java
module com.example.app {
    requires com.example.geometry;
}
~~~

thì module **com.example.app** đọc module **com.example.geometry**. Nhờ đó, mã nguồn trong app có thể tham chiếu đến các kiểu public thuộc package mà geometry đã export.

Có thể hình dung:

~~~text
com.example.app
       |
       | requires
       v
com.example.geometry
~~~

Readability không tự động làm mọi package của module geometry trở nên công khai. Module app có thể đọc geometry nhưng chỉ truy cập các package được export phù hợp.

Vì vậy cần tách hai câu hỏi:

1. **Module app có đọc geometry không?** Được quyết định bởi requires và quan hệ readability.
2. **Module app có truy cập được package cần dùng trong geometry không?** Được quyết định bởi exports và quyền truy cập Java thông thường.

Nếu một trong hai điều kiện không thỏa mãn, việc import hoặc truy cập kiểu có thể thất bại.

## 4. requires: khai báo dependency module

Mệnh đề **requires** tạo một dependency module và làm cho module hiện tại đọc module được yêu cầu.

Ví dụ:

~~~java
module com.example.app {
    requires com.example.geometry;
}
~~~

Khi biên dịch và chạy, module geometry phải có mặt trong module graph và được tìm thấy trên module path hoặc qua một nguồn module phù hợp.

Một module có thể yêu cầu nhiều module:

~~~java
module com.example.app {
    requires com.example.geometry;
    requires java.net.http;
    requires java.logging;
}
~~~

Các module được yêu cầu trực tiếp phải được giải quyết trong module graph. Nếu thiếu một module bắt buộc, JVM hoặc compiler có thể báo lỗi module không tìm thấy.

### requires không thay thế exports

Giả sử geometry có descriptor:

~~~java
module com.example.geometry {
}
~~~

App khai báo:

~~~java
module com.example.app {
    requires com.example.geometry;
}
~~~

App đọc geometry, nhưng nếu geometry không export package **com.example.geometry.api**, app vẫn không thể sử dụng kiểu trong package đó như API công khai. Cần thêm exports ở phía geometry.

## 5. exports: công khai package cho module khác

Mệnh đề **exports** làm cho các kiểu public trong package được chỉ định có thể truy cập từ các module đọc module hiện tại, theo các quy tắc truy cập Java thông thường.

Module geometry:

~~~java
module com.example.geometry {
    exports com.example.geometry.api;
}
~~~

Lớp API:

~~~java
package com.example.geometry.api;

public class Point {
    private final double x;
    private final double y;

    public Point(double x, double y) {
        this.x = x;
        this.y = y;
    }

    public double distanceFromOrigin() {
        return Math.sqrt(x * x + y * y);
    }
}
~~~

Module app:

~~~java
module com.example.app {
    requires com.example.geometry;
}
~~~

Mã app có thể sử dụng lớp Point:

~~~java
package com.example.app;

import com.example.geometry.api.Point;

public class Main {
    public static void main(String[] args) {
        Point point = new Point(3, 4);
        System.out.println(point.distanceFromOrigin());
    }
}
~~~

Ở đây, app đọc geometry nhờ **requires**, còn Point có thể được import vì package **com.example.geometry.api** được export.

### Export package không làm mọi lớp trở thành public

Exports chỉ mở package theo quy tắc module. Những quy tắc truy cập của ngôn ngữ Java vẫn có hiệu lực:

- Lớp cần được khai báo **public** nếu muốn truy cập từ package khác.
- Constructor, method và field cũng phải có mức truy cập phù hợp.
- Thành viên **private** vẫn là private.
- Package không được export vẫn bị đóng với truy cập thông thường từ module khác.

## 6. Package không được export được đóng gói như thế nào?

Một module có thể chứa package nội bộ mà không export:

~~~text
com.example.geometry
├── com.example.geometry.api
└── com.example.geometry.internal
~~~

Descriptor:

~~~java
module com.example.geometry {
    exports com.example.geometry.api;
}
~~~

Package **com.example.geometry.internal** không được export. Module khác không thể import các kiểu trong package này như một API công khai, kể cả khi các kiểu đó được khai báo public.

Cách tổ chức này cho phép thư viện giữ implementation details ở bên trong module và chỉ công khai API ổn định. Nhóm có thể thay đổi lớp nội bộ mà không buộc consumer phụ thuộc vào các chi tiết đó.

Sơ đồ:

~~~text
com.example.geometry
├── api       [exported]
└── internal  [not exported]
~~~

Module consumer chỉ có thể sử dụng API công khai đã export. Việc giữ package nội bộ không export giúp giảm coupling và hạn chế việc ứng dụng khác phụ thuộc vào implementation.

## 7. Qualified exports: chỉ xuất package cho module được chỉ định

Không phải lúc nào một package cũng cần được công khai cho tất cả module. **Qualified exports** giới hạn package được xuất cho một hoặc một nhóm module cụ thể.

Ví dụ:

~~~java
module com.example.geometry {
    exports com.example.geometry.api;
    exports com.example.geometry.spi to com.example.plugin;
}
~~~

Trong đó:

- **com.example.geometry.api** được xuất cho mọi module đọc geometry.
- **com.example.geometry.spi** chỉ được xuất cho module **com.example.plugin**.

Module plugin phải có descriptor phù hợp:

~~~java
module com.example.plugin {
    requires com.example.geometry;
}
~~~

Khi plugin đọc geometry, nó có thể truy cập các kiểu public trong package SPI đã được export riêng cho nó. Một module khác dù có **requires com.example.geometry** cũng không tự động có quyền truy cập package SPI đó.

Qualified exports hữu ích khi một thư viện có API công khai cho mọi consumer nhưng chỉ muốn cung cấp SPI hoặc integration API cho một số module được kiểm soát.

Nếu module mục tiêu chưa được xác định trong module graph, compiler hoặc runtime có thể đưa ra cảnh báo về module target không tồn tại hoặc không được đọc. Tên trong mệnh đề to phải là tên module, không phải package hay tên artifact.

## 8. requires transitive: truyền readability qua API

Thông thường, nếu module A requires B, điều đó không có nghĩa module C requires A cũng tự động đọc B.

Giả sử:

~~~text
app -> library -> data-api
~~~

Các descriptor:

~~~java
module com.example.data {
    exports com.example.data.api;
}
~~~

~~~java
module com.example.library {
    requires com.example.data;
    exports com.example.library.api;
}
~~~

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

App đọc library. Nhưng quan hệ requires thông thường của library tới data không tự động truyền readability đến app.

Điều này có thể gây vấn đề nếu API public của library sử dụng kiểu thuộc data-api:

~~~java
package com.example.library.api;

import com.example.data.api.Record;

public interface Repository {
    Record findById(String id);
}
~~~

Consumer sử dụng Repository có thể cần truy cập kiểu Record trong chữ ký API. Khi đó module library có thể khai báo:

~~~java
module com.example.library {
    requires transitive com.example.data;
    exports com.example.library.api;
}
~~~

**requires transitive** vừa yêu cầu library đọc data, vừa làm cho module đọc library cũng đọc data thông qua quan hệ bắc cầu.

Đồ thị readability:

~~~text
com.example.app
       |
       | requires
       v
com.example.library
       |
       | requires transitive
       v
com.example.data
~~~

Khi app requires library, app cũng đọc data vì library đã khai báo dependency transitive.

### Khi nào nên dùng requires transitive?

Dùng khi dependency là một phần của API mà consumer cần nhìn thấy. Ví dụ:

- Kiểu của dependency xuất hiện trong tham số hoặc kiểu trả về của public method.
- Interface công khai kế thừa một interface từ module khác.
- Public class kế thừa hoặc triển khai kiểu từ module khác.
- Public API dùng annotation hoặc kiểu cần được consumer tham chiếu khi biên dịch.

Không nên đánh dấu mọi dependency là transitive chỉ để làm build script consumer ngắn hơn. Điều đó làm mở rộng readability graph và khiến consumer phụ thuộc gián tiếp vào module mà API của library có thể không thực sự cần công khai.

## 9. requires static: dependency cần khi biên dịch nhưng tùy chọn lúc chạy

Mệnh đề **requires static** biểu thị một dependency cần có khi biên dịch module hiện tại nhưng không bắt buộc phải hiện diện ở runtime.

Ví dụ:

~~~java
module com.example.library {
    requires static com.example.annotations;
    exports com.example.library.api;
}
~~~

Cách này có thể phù hợp với annotation hoặc công cụ chỉ cần khi biên dịch, nếu ứng dụng không cần module đó ở runtime.

Cần hiểu rõ:

- Compiler vẫn cần tìm module được yêu cầu khi biên dịch module khai báo **requires static**.
- Khi chạy, module đó không bắt buộc phải có mặt chỉ vì có mệnh đề requires static.
- Nếu module đó có mặt trong runtime module graph, quan hệ readability vẫn có thể được thiết lập theo quy tắc JPMS.
- Nếu mã runtime thực sự cần lớp từ module đó nhưng module không có mặt, ứng dụng vẫn có thể thất bại khi nạp hoặc sử dụng lớp.

Ví dụ, nếu library chỉ dùng annotation trong source và annotation không cần thiết khi chạy, requires static có thể phù hợp. Nhưng nếu code gọi method của module đó ở runtime, không thể dựa vào requires static để bỏ module khỏi runtime.

## 10. Kết hợp requires, transitive và static

Các modifier này giải quyết những vấn đề khác nhau:

| Mệnh đề | Ý nghĩa |
|---|---|
| **requires M** | Module hiện tại cần đọc M ở compile và runtime |
| **requires transitive M** | Module hiện tại cần M và truyền readability của M đến các module đọc nó |
| **requires static M** | M cần khi compile nhưng không bắt buộc ở runtime |
| **requires static transitive M** | Kết hợp dependency compile-time tùy chọn ở runtime với readability bắc cầu khi module có mặt |

Ví dụ:

~~~java
module com.example.library {
    requires transitive com.example.data;
    requires static com.example.annotations;
}
~~~

Module library công khai kiểu từ data cho consumer, nhưng chỉ cần annotations khi biên dịch theo thiết kế của thư viện.

Cần chọn modifier dựa trên cách dependency được sử dụng, không chỉ dựa trên việc module đó có nằm trong dependency graph của Gradle hay không. Gradle dependency declaration và JPMS requires có liên quan nhưng là hai lớp cấu hình khác nhau.

## 11. exports khác opens như thế nào?

**exports** công khai package cho truy cập thông thường từ module khác. **opens** cho phép reflection sâu vào các kiểu và thành viên trong package tại runtime, theo cơ chế truy cập reflection của JPMS.

Ví dụ:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal;
}
~~~

- Package **com.example.model.api** được công khai như API thông thường.
- Package **com.example.model.internal** được mở cho deep reflection lúc chạy nhưng không trở thành API compile-time thông thường.

Framework có thể dùng reflection để truy cập constructor, field hoặc method không public, ví dụ để tạo object, ánh xạ dữ liệu hoặc inject dependency. Trong module system, thao tác deep reflection như vậy có thể bị chặn nếu package không được mở phù hợp.

### Qualified opens

Có thể chỉ mở package cho một module framework cụ thể:

~~~java
module com.example.model {
    opens com.example.model.internal to com.example.orm;
}
~~~

Khi đó module **com.example.orm** có quyền reflection sâu vào package được mở. Các module khác không được cấp quyền này chỉ vì chúng đọc module model.

### Open module

Có thể mở toàn bộ package của module cho deep reflection bằng:

~~~java
open module com.example.model {
    exports com.example.model.api;
}
~~~

Một open module làm cho các package của nó được mở cho deep reflection theo quy tắc JPMS. Điều này không có nghĩa mọi package đều được export như API compile-time. **opens** và **exports** vẫn có mục đích khác nhau.

| Mệnh đề | Truy cập thông thường ở compile-time | Deep reflection ở runtime |
|---|---|---|
| **exports package** | Có, với public types và thành viên truy cập được | Không tự động cho phép mọi truy cập private |
| **opens package** | Không làm package trở thành API công khai | Có |
| **exports p to m** | Chỉ module m được truy cập API package p | Không tự động mở private members |
| **opens p to m** | Không công khai API compile-time | Chỉ module m được deep reflection vào p |

Nếu compiler báo package không được export, thêm opens không giải quyết vấn đề import. Nếu framework báo không thể truy cập private field qua reflection, exports có thể chưa đủ; cần opens phù hợp.

## 12. Readability và exports phải cùng thỏa mãn

Giả sử app muốn dùng **com.example.geometry.api.Point**. Có bốn trường hợp cơ bản:

| App requires geometry? | Geometry exports package api? | Kết quả |
|---|---|---|
| Có | Có | App có thể truy cập public API trong package |
| Có | Không | App đọc module nhưng package không được công khai |
| Không | Có | Package được export nhưng app không có readability dependency tương ứng |
| Không | Không | Không có quan hệ cần thiết để sử dụng package |

Hai khai báo phối hợp:

~~~java
// geometry/module-info.java
module com.example.geometry {
    exports com.example.geometry.api;
}
~~~

~~~java
// app/module-info.java
module com.example.app {
    requires com.example.geometry;
}
~~~

Chỉ khi cả quan hệ readability và package export phù hợp, mã app mới có thể sử dụng API geometry như ví dụ.

## 13. Module path và classpath

JPMS phân biệt **module path** và **classpath**.

- **Module path** là nơi JVM/compiler tìm các module có tên, gồm explicit modules và automatic modules.
- **Classpath** là nơi tìm các lớp và JAR theo mô hình classpath truyền thống. Các lớp trên classpath thuộc unnamed module.

Khi dùng module path, một JAR có thể là explicit module nếu chứa module descriptor, hoặc automatic module nếu không có descriptor nhưng được đặt trên module path và có thể xác định tên module.

### Explicit module

Một JAR chứa **module-info.class** được biên dịch từ module-info.java. Module descriptor xác định tên module, requires và exports.

### Automatic module

Một JAR thông thường không có module descriptor nhưng được đặt trên module path có thể trở thành automatic module. Tên module có thể được xác định từ manifest entry **Automatic-Module-Name** hoặc từ tên JAR theo quy tắc đặt tên module.

Automatic module có semantics dễ tích hợp với thư viện cũ hơn: nó đọc các named module quan sát được và export các package của chính nó. Tuy nhiên, đây là cơ chế chuyển tiếp; không nên xem automatic module như một module được thiết kế đầy đủ với ranh giới API rõ ràng.

### Unnamed module

Các lớp trên classpath thuộc unnamed module. Unnamed module có khả năng đọc các named modules quan sát được theo quy tắc JPMS, và các package của nó không bị kiểm soát bằng exports như named module.

Named module không thể khai báo **requires** đến unnamed module. Vì vậy, khi một ứng dụng chuyển sang JPMS, dependency cũ trên classpath có thể cần được chuyển sang module path dưới dạng automatic module hoặc được thay bằng phiên bản có module descriptor.

## 14. Biên dịch và chạy module bằng javac/java

Giả sử dự án có hai module:

~~~text
src/
├── com.example.geometry/
│   ├── module-info.java
│   └── com/example/geometry/api/Point.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Module geometry:

~~~java
module com.example.geometry {
    exports com.example.geometry.api;
}
~~~

Module app:

~~~java
module com.example.app {
    requires com.example.geometry;
}
~~~

Biên dịch module geometry:

~~~bash
javac -d mods/com.example.geometry \
    src/com.example.geometry/module-info.java \
    src/com.example.geometry/com/example/geometry/api/Point.java
~~~

Biên dịch app với geometry trên module path:

~~~bash
javac --module-path mods \
    -d mods/com.example.app \
    src/com.example.app/module-info.java \
    src/com.example.app/com/example/app/Main.java
~~~

Chạy module app:

~~~bash
java --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

Tùy chọn **--module-path** cho compiler hoặc JVM biết nơi tìm module. Tùy chọn **-m** hoặc **--module** chỉ định module và lớp main cần chạy.

Nếu module geometry không được export package API hoặc module app thiếu requires, quá trình biên dịch sẽ thất bại dù thư mục chứa class đã tồn tại.

## 15. Gradle và module-info.java

Với Gradle Java plugin, module descriptor thường nằm ở:

~~~text
src/main/java/module-info.java
~~~

Ví dụ dự án nhiều module có project **geometry** và **app**. Module app khai báo dependency project trong build script:

~~~kotlin
dependencies {
    implementation(project(":geometry"))
}
~~~

Đồng thời, module descriptor của app cần khai báo quan hệ JPMS:

~~~java
module com.example.app {
    requires com.example.geometry;
}
~~~

Module geometry export package API:

~~~java
module com.example.geometry {
    exports com.example.geometry.api;
}
~~~

Gradle dependency khai báo project dependency giúp Gradle biết quan hệ build và artifact cần thiết. Mệnh đề **requires** trong module-info.java mô tả readability của JPMS. Hai lớp khai báo này phục vụ các mục đích liên quan nhưng không thay thế lẫn nhau.

Java plugin của Gradle có cơ chế suy luận module path cho dự án modular. Có thể cấu hình rõ trong build script Groovy:

~~~groovy
java {
    modularity.inferModulePath = true
}
~~~

Khả năng suy luận và hành vi cụ thể phụ thuộc phiên bản Gradle, Java plugin và cách source set được cấu hình. Khi build không đặt dependency trên module path như mong muốn, hãy kiểm tra phiên bản Gradle, vị trí module-info.java và log compile task.

## 16. Các lỗi JPMS thường gặp

| Thông báo hoặc biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| **module not found** | Module được requires nhưng không có trên module path hoặc tên module sai | Kiểm tra module path, tên module và artifact |
| **module does not read** | Module hiện tại chưa khai báo requires đến module chứa kiểu cần dùng | Thêm requires phù hợp trong module-info.java |
| **package is not visible** | Module được đọc nhưng package cần dùng không được export | Export package ở module cung cấp hoặc dùng qualified exports phù hợp |
| **package is declared in module ... but module does not export it** | Package thuộc named module nhưng không được công khai cho consumer | Kiểm tra exports trong module descriptor |
| **does not open ... to ...** | Framework cần deep reflection nhưng package chưa được opens | Mở package cho module framework bằng opens hoặc cấu hình runtime phù hợp |
| **module not found khi chạy** | Module có lúc compile nhưng thiếu trên runtime module path | Kiểm tra runtime module path và dependency triển khai |
| **automatic module name thay đổi** | Tên module suy ra từ tên JAR không ổn định sau khi đổi tên artifact | Dùng Automatic-Module-Name hoặc module descriptor rõ ràng |
| **split package** | Cùng một package xuất hiện trong nhiều named module không tương thích với quy tắc module | Hợp nhất package hoặc điều chỉnh ranh giới module |

Không nên giải quyết mọi lỗi JPMS bằng cách thêm **--add-exports** hoặc **--add-opens** ngay lập tức. Các tùy chọn này có thể hữu ích để tương thích với thư viện cũ hoặc trong môi trường kiểm thử, nhưng cần xác định module nguồn, module đích và package cụ thể. Với module do nhóm kiểm soát, ưu tiên sửa module descriptor.

## 17. Cách chẩn đoán vấn đề readability và exports

Khi một module không thể sử dụng kiểu từ module khác, hãy đi theo thứ tự:

1. Xác định kiểu thuộc package và module nào.
2. Xác nhận dependency artifact có mặt trong module path.
3. Kiểm tra tên module trong module-info.java của provider.
4. Kiểm tra consumer có requires provider hay không.
5. Kiểm tra provider có exports package chứa kiểu hay không.
6. Nếu dùng qualified exports, xác nhận tên module consumer nằm trong danh sách đích.
7. Nếu lỗi xuất hiện khi framework dùng reflection, kiểm tra opens thay vì chỉ kiểm tra exports.
8. Nếu module chỉ cần ở compile-time, xem xét requires static; nếu API cần readability truyền cho consumer, xem xét requires transitive.
9. Kiểm tra runtime module path có chứa các module bắt buộc khi chạy ứng dụng.
10. Với JAR cũ, xác định nó là automatic module hay vẫn nằm trong unnamed module trên classpath.

Có thể dùng công cụ JDK để xem module descriptor:

~~~bash
jar --describe-module --file path/to/library.jar
~~~

Với một module đã được resolve trên module path:

~~~bash
java --module-path mods --describe-module com.example.geometry
~~~

Các lệnh này giúp xác định tên module và những package được export/open theo descriptor.

## 18. Những nguyên tắc cần nhớ

- JPMS dùng named module để khai báo dependency và kiểm soát ranh giới package.
- **requires** tạo readability: module hiện tại có thể đọc module được yêu cầu.
- **exports** công khai package cho module khác; nó không tự thêm dependency vào graph.
- **requires transitive** truyền readability của dependency đến các module đọc module hiện tại.
- **requires static** yêu cầu module khi biên dịch nhưng không bắt buộc nó hiện diện ở runtime.
- **qualified exports** chỉ công khai package cho module được chỉ định.
- **opens** cho phép deep reflection ở runtime; nó không thay thế exports cho truy cập compile-time.
- Package không export giúp giữ implementation details bên trong module.
- Classpath chứa unnamed module; module path chứa explicit hoặc automatic modules.
- Gradle project dependency mô tả quan hệ build, còn requires trong module descriptor mô tả readability của JPMS.
- Khi chẩn đoán, luôn kiểm tra cả module path, requires và exports; với framework reflection, kiểm tra thêm opens.

JPMS kiểm soát khả năng sử dụng thư viện bằng hai câu hỏi tách biệt: module consumer có đọc được module provider không, và package cần dùng có được provider xuất ra không. Khi cả hai điều kiện được khai báo đúng, ứng dụng có thể dùng API công khai trong khi implementation details vẫn được giữ kín bên trong module.
