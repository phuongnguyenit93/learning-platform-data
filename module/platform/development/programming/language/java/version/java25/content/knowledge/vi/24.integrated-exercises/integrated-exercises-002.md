# Tổ chức import module và giải quyết xung đột tên kiểu trong ví dụ nhiều package

Một ứng dụng Java có thể dùng nhiều thư viện, mỗi thư viện đóng gói nhiều package trong một module. Khi cần các kiểu dữ liệu từ nhiều module, danh sách import truyền thống có thể dài. Java 25 cung cấp **Module Import Declarations** qua **JEP 511**, cho phép nhập các public top-level type được export bởi một module bằng một khai báo duy nhất:

~~~java
import module java.base;
~~~

Cách viết ngắn hơn cũng làm tăng khả năng gặp xung đột tên. Hai module có thể export các package khác nhau nhưng cùng khai báo một kiểu tên **Point**, **List**, **Date** hoặc **Configuration**. Khi một compilation unit import cả hai module, tên đơn giản có thể trở nên mơ hồ.

Bài thực hành này xây dựng một ứng dụng gồm hai module thư viện: hình học và định vị. Cả hai cùng export một kiểu **Point** trong hai package riêng. Bạn sẽ tạo lỗi biên dịch có chủ đích, đọc thông báo compiler, rồi sửa bằng single-type import hoặc fully qualified name. Bài cũng dùng xung đột **java.awt.List** và **java.util.List** để luyện cách giải quyết trên các module có sẵn của JDK.

**Phạm vi phiên bản:** Module Import Declarations là tính năng đã hoàn tất trong Java 25 theo JEP 511. Bài dùng cú pháp chính thức của Java 25, không bật preview và không dùng các ví dụ preview cũ của những JDK trước.

## 1. Mục tiêu thực hành

Hoàn thành bài này, bạn có thể:

1. Giải thích sự khác nhau giữa package, module, readability và exported package.
2. Viết cú pháp **import module ModuleName;**.
3. Giải thích một module import đưa những public top-level type nào vào phạm vi tên của compilation unit.
4. Phân biệt module import với **requires** trong **module-info.java**.
5. Tạo dự án nhiều module, mỗi module chứa nhiều package.
6. Nhận diện lỗi ambiguous reference khi nhiều module export type cùng simple name.
7. Dùng single-type import để chọn kiểu mặc định và shadow các module import.
8. Dùng fully qualified name khi cần đồng thời hai kiểu trùng tên.
9. Biết khi nào nên giữ import tường minh thay vì gom mọi package vào module import.
10. Biên dịch và chạy dự án bằng JDK 25 mà không bật **--enable-preview**.

## 2. Bối cảnh: một ứng dụng dùng hai thư viện

Giả sử ứng dụng cần xử lý hai loại tọa độ:

- Tọa độ hình học trên mặt phẳng, biểu diễn bằng trục **x** và **y**.
- Tọa độ địa lý, biểu diễn bằng vĩ độ và kinh độ.

Hai thư viện được phát triển độc lập. Cả hai đều chọn tên kiểu **Point**, nhưng đặt trong package khác nhau:

| Module | Package export | Kiểu trùng tên | Ý nghĩa |
|---|---|---|---|
| **com.acme.geometry** | **com.acme.geometry** | **Point** | Tọa độ Descartes x, y |
| **com.acme.navigation** | **com.acme.navigation** | **Point** | Tọa độ địa lý latitude, longitude |
| **com.acme.app** | **com.acme.app** | **Main** | Ứng dụng sử dụng cả hai thư viện |

Tên đầy đủ của hai kiểu không trùng nhau:

- **com.acme.geometry.Point**
- **com.acme.navigation.Point**

Chúng chỉ trùng **simple name** là **Point**. Đây là tình huống điển hình để hiểu vì sao module import tiện lợi nhưng cần quản lý namespace cẩn thận.

~~~mermaid
flowchart TD
    APP["com.acme.app"] -->|requires| GEO["com.acme.geometry"]
    APP -->|requires| NAV["com.acme.navigation"]
    GEO --> GP["com.acme.geometry.Point"]
    GEO --> GS["com.acme.geometry.Geometry"]
    NAV --> NP["com.acme.navigation.Point"]
    NAV --> NR["com.acme.navigation.Route"]
    APP --> MAIN["com.acme.app.Main"]
~~~

## 3. Cấu trúc thư mục dự án

Tạo một thư mục dự án có cấu trúc sau:

~~~text
module-import-lab/
└── src/
    ├── com.acme.geometry/
    │   ├── module-info.java
    │   └── com/
    │       └── acme/
    │           └── geometry/
    │               ├── Point.java
    │               └── Geometry.java
    ├── com.acme.navigation/
    │   ├── module-info.java
    │   └── com/
    │       └── acme/
    │           └── navigation/
    │               ├── Point.java
    │               └── Route.java
    └── com.acme.app/
        ├── module-info.java
        └── com/
            └── acme/
                └── app/
                    └── Main.java
~~~

Mỗi thư mục cấp đầu tiên trong **src** là một module source root. Bên trong mỗi module, cấu trúc thư mục tiếp tục phản ánh package.

## 4. Tạo module hình học

### 4.1. Module descriptor

File **src/com.acme.geometry/module-info.java**:

~~~java
module com.acme.geometry {
    exports com.acme.geometry;
}
~~~

Module **com.acme.geometry** export package **com.acme.geometry**. Các public type trong package này có thể được module khác truy cập nếu module đó đọc **com.acme.geometry**.

### 4.2. Kiểu Point hình học

File **src/com.acme.geometry/com/acme/geometry/Point.java**:

~~~java
package com.acme.geometry;

public record Point(double x, double y) {
}
~~~

Record **Point** lưu tọa độ hai chiều. Constructor và accessor được compiler sinh tự động.

### 4.3. Lớp Geometry

File **src/com.acme.geometry/com/acme/geometry/Geometry.java**:

~~~java
package com.acme.geometry;

public final class Geometry {

    private Geometry() {
    }

    public static double distance(Point first, Point second) {
        double dx = second.x() - first.x();
        double dy = second.y() - first.y();
        return Math.hypot(dx, dy);
    }
}
~~~

Lớp **Geometry** sử dụng **Point** trong cùng package nên không cần import. Phương thức **distance** tính khoảng cách Euclid giữa hai điểm.

## 5. Tạo module định vị

### 5.1. Module descriptor

File **src/com.acme.navigation/module-info.java**:

~~~java
module com.acme.navigation {
    exports com.acme.navigation;
}
~~~

Module này export package **com.acme.navigation**.

### 5.2. Kiểu Point địa lý

File **src/com.acme.navigation/com/acme/navigation/Point.java**:

~~~java
package com.acme.navigation;

public record Point(double latitude, double longitude) {
}
~~~

Tên simple name vẫn là **Point**, nhưng các thành phần dữ liệu khác với **com.acme.geometry.Point**.

### 5.3. Lớp Route

File **src/com.acme.navigation/com/acme/navigation/Route.java**:

~~~java
package com.acme.navigation;

public final class Route {

    private static final double KM_PER_LATITUDE_DEGREE = 110.57;
    private static final double KM_PER_LONGITUDE_DEGREE = 111.32;

    private Route() {
    }

    public static double approximateDistanceKm(Point from, Point to) {
        double meanLatitude = Math.toRadians(
                (from.latitude() + to.latitude()) / 2.0);

        double dx = (to.longitude() - from.longitude())
                * KM_PER_LONGITUDE_DEGREE
                * Math.cos(meanLatitude);

        double dy = (to.latitude() - from.latitude())
                * KM_PER_LATITUDE_DEGREE;

        return Math.hypot(dx, dy);
    }
}
~~~

Đây là công thức xấp xỉ để phục vụ bài thực hành. Trong hệ thống bản đồ thực tế, hãy chọn phép tính địa lý phù hợp với phạm vi, độ chính xác và mô hình trái đất của sản phẩm.

## 6. Tạo module ứng dụng

File **src/com.acme.app/module-info.java**:

~~~java
module com.acme.app {
    requires com.acme.geometry;
    requires com.acme.navigation;
}
~~~

Hai dòng **requires** thiết lập readability: module ứng dụng được phép đọc các module thư viện.

**Điểm quan trọng:** **requires** và **import module** giải quyết hai vấn đề khác nhau.

- **requires** nằm trong **module-info.java**, khai báo dependency giữa các module.
- **import module** nằm trong một compilation unit, đưa các public top-level type được phép truy cập vào phạm vi tên của file đó.

Khai báo **import module com.acme.geometry;** không tự thêm **requires com.acme.geometry;** vào module descriptor. Nếu module ứng dụng chưa đọc module được import, compiler báo lỗi.

## 7. Thử module import và cố ý tạo xung đột

Tạo file **src/com.acme.app/com/acme/app/Main.java** với nội dung ban đầu:

~~~java
package com.acme.app;

import module com.acme.geometry;
import module com.acme.navigation;

public class Main {

    public static void main(String[] args) {
        Point start = new Point(0, 0);
        Point end = new Point(3, 4);

        System.out.println(
                "Distance = " + Geometry.distance(start, end));
    }
}
~~~

Hai module đều export một kiểu tên **Point**. Khi compiler phân giải **Point**, nó tìm thấy hai ứng viên:

- **com.acme.geometry.Point**
- **com.acme.navigation.Point**

Vì vậy, tham chiếu **Point** không xác định được kiểu nào cần dùng. Đây là lỗi biên dịch, không phải lỗi runtime.

Thông báo có thể có dạng:

~~~text
reference to Point is ambiguous
both record com.acme.geometry.Point in com.acme.geometry
and record com.acme.navigation.Point in com.acme.navigation match
~~~

Nội dung thông báo thực tế có thể khác theo build JDK, nhưng nguyên nhân là hai module import đưa hai kiểu cùng simple name vào phạm vi on-demand import.

### 7.1. Tại sao compiler không tự chọn một kiểu?

Module import không đặt thứ tự ưu tiên giữa các module. Thứ tự viết hai dòng import không làm module đầu tiên thắng module thứ hai.

Compiler cần một khai báo đủ rõ để xác định kiểu. Bạn có ba hướng giải quyết:

1. Chọn một kiểu làm tên đơn giản bằng single-type import.
2. Viết fully qualified name ở những nơi cần kiểu còn lại.
3. Bỏ module import rộng và dùng các import tường minh theo từng type/package.

## 8. Cách 1: single-type import để chọn kiểu mặc định

Trong ứng dụng này, **Point** hình học xuất hiện thường xuyên hơn. Hãy chọn nó làm kiểu mặc định.

Sửa **Main.java**:

~~~java
package com.acme.app;

import module com.acme.geometry;
import module com.acme.navigation;

import com.acme.geometry.Point;

public class Main {

    public static void main(String[] args) {
        Point start = new Point(0, 0);
        Point end = new Point(3, 4);

        double distance = Geometry.distance(start, end);

        System.out.println("Geometry distance = " + distance);
    }
}
~~~

Single-type import:

~~~java
import com.acme.geometry.Point;
~~~

đưa chính xác **com.acme.geometry.Point** vào simple name **Point**. Khai báo này **shadow** các type cùng tên được đưa vào theo module import. Vì vậy, **Point** trong file này được hiểu là **com.acme.geometry.Point**.

Các kiểu khác như **Geometry** và **Route** vẫn có thể được tham chiếu bằng simple name do hai module import cung cấp.

### 8.1. Dùng cả hai kiểu Point trong cùng file

Nếu cần tọa độ địa lý trong cùng compilation unit, hãy viết fully qualified name cho kiểu còn lại:

~~~java
package com.acme.app;

import module com.acme.geometry;
import module com.acme.navigation;

import com.acme.geometry.Point;

public class Main {

    public static void main(String[] args) {
        Point start = new Point(0, 0);
        Point end = new Point(3, 4);

        double geometryDistance = Geometry.distance(start, end);

        com.acme.navigation.Point gpsStart =
                new com.acme.navigation.Point(10.0, 20.0);

        com.acme.navigation.Point gpsEnd =
                new com.acme.navigation.Point(10.01, 20.02);

        double routeDistance =
                Route.approximateDistanceKm(gpsStart, gpsEnd);

        System.out.println("Geometry distance = " + geometryDistance);
        System.out.printf("Route distance = %.2f km%n", routeDistance);
    }
}
~~~

Kết quả dự kiến:

~~~text
Geometry distance = 5.0
Route distance = 2.45 km
~~~

Cách tổ chức này phù hợp khi một kiểu là mặc định của file và kiểu còn lại chỉ xuất hiện ở một vài vị trí.

### 8.2. Không import hai type cùng simple name tường minh

Không sửa thành:

~~~java
import com.acme.geometry.Point;
import com.acme.navigation.Point;
~~~

Hai single-type import cùng đưa tên **Point** từ hai type khác nhau vào cùng compilation unit. Đây là lỗi biên dịch do trùng tên trong các single-type import.

Nếu cần cả hai kiểu, chỉ import một type và dùng tên đầy đủ cho type kia, hoặc dùng fully qualified name cho cả hai.

## 9. Cách 2: fully qualified name cho cả hai kiểu

Nếu hai kiểu xuất hiện với tần suất tương đương, có thể không import **Point** tường minh:

~~~java
package com.acme.app;

import module com.acme.geometry;
import module com.acme.navigation;

public class Main {

    public static void main(String[] args) {
        com.acme.geometry.Point geometryStart =
                new com.acme.geometry.Point(0, 0);

        com.acme.geometry.Point geometryEnd =
                new com.acme.geometry.Point(3, 4);

        com.acme.navigation.Point gpsStart =
                new com.acme.navigation.Point(10.0, 20.0);

        com.acme.navigation.Point gpsEnd =
                new com.acme.navigation.Point(10.01, 20.02);

        double geometryDistance =
                Geometry.distance(geometryStart, geometryEnd);

        double routeDistance =
                Route.approximateDistanceKm(gpsStart, gpsEnd);

        System.out.println("Geometry distance = " + geometryDistance);
        System.out.printf("Route distance = %.2f km%n", routeDistance);
    }
}
~~~

Ưu điểm:

- Không còn tên **Point** mơ hồ.
- Người đọc nhìn thấy package sở hữu kiểu ngay tại nơi sử dụng.
- Có thể dùng cả hai type trong cùng method hoặc class.

Nhược điểm là tên đầy đủ dài hơn. Có thể dùng import tường minh cho những kiểu không trùng tên như **Geometry**, **Route**, và chỉ viết fully qualified name cho **Point**.

## 10. Cách 3: dùng import tường minh thay cho module import

Module import là lựa chọn, không phải yêu cầu bắt buộc. Nếu một file chỉ dùng một vài type, import theo type hoặc package có thể rõ ràng hơn:

~~~java
package com.acme.app;

import com.acme.geometry.Geometry;
import com.acme.geometry.Point;
import com.acme.navigation.Route;

public class Main {

    public static void main(String[] args) {
        Point start = new Point(0, 0);
        Point end = new Point(3, 4);

        com.acme.navigation.Point gpsStart =
                new com.acme.navigation.Point(10.0, 20.0);

        com.acme.navigation.Point gpsEnd =
                new com.acme.navigation.Point(10.01, 20.02);

        System.out.println(Geometry.distance(start, end));
        System.out.println(Route.approximateDistanceKm(gpsStart, gpsEnd));
    }
}
~~~

Cách này bỏ hai module import rộng và chỉ import các type cần dùng. **Point** hình học được chọn làm simple name; **Point** địa lý vẫn dùng fully qualified name.

Không có quy tắc rằng module import luôn tốt hơn import tường minh. Hãy chọn dựa trên số type sử dụng, mức độ trùng tên, phạm vi API và khả năng đọc của file.

## 11. Bài đối chiếu với module có sẵn của JDK: List

JDK 25 có một ví dụ thực tế về xung đột tên kiểu:

- **java.util.List** được export bởi module **java.base**.
- **java.awt.List** được export bởi module **java.desktop**.

Tạo một module ứng dụng có thể đọc **java.desktop**.

File **module-info.java**:

~~~java
module com.acme.ui {
    requires java.desktop;
}
~~~

Trong **Main.java**, thử:

~~~java
package com.acme.ui;

import module java.base;
import module java.desktop;

public class Main {

    public static void main(String[] args) {
        List<String> values = List.of("Java", "25");
        Class<?> awtListType = java.awt.List.class;
        System.out.println(values);
        System.out.println("AWT type = " + awtListType.getName());
    }
}
~~~

Compiler không thể tự quyết định **List** là **java.util.List** hay **java.awt.List**.

### 11.1. Giải quyết bằng single-type import

Nếu ứng dụng muốn dùng collection **java.util.List** làm kiểu mặc định:

~~~java
package com.acme.ui;

import module java.base;
import module java.desktop;

import java.util.List;

public class Main {

    public static void main(String[] args) {
        List<String> values = List.of("Java", "25");

        java.awt.List awtList = new java.awt.List();
        values.forEach(awtList::add);

        System.out.println(values);
        System.out.println("AWT item count = " + awtList.getItemCount());
    }
}
~~~

Single-type import **java.util.List** shadow **java.awt.List** được đưa vào bởi module import. Khi cần tham chiếu kiểu AWT, dùng tên đầy đủ **java.awt.List**. Ví dụ dùng class literal để không cần khởi tạo UI component, nhờ đó có thể chạy trong môi trường headless.

Tên **java.awt.List** ở đây là một class trong API AWT. Ví dụ chỉ nhằm minh họa xung đột tên giữa hai module; khi phát triển giao diện mới, hãy chọn API UI phù hợp với yêu cầu sản phẩm.

## 12. Module import thực sự nhập những gì?

Khai báo:

~~~java
import module M;
~~~

nhập theo nhu cầu tất cả public top-level class và interface trong:

1. Các package mà module **M** export cho module hiện tại.
2. Các package được export bởi những module mà module hiện tại đọc được do đọc module **M**.

Điều này giúp code sử dụng API của một module mà không cần liệt kê từng package con hoặc các package được export qua dependency transitive phù hợp.

### 12.1. Chỉ package được export mới được nhập

Giả sử module có cấu trúc:

~~~java
module com.acme.geometry {
    exports com.acme.geometry;
}
~~~

Các type public trong **com.acme.geometry** có thể được import từ module khác. Nếu module còn có package **com.acme.geometry.internal** nhưng không export package đó, type trong package internal không trở thành accessible chỉ vì có:

~~~java
import module com.acme.geometry;
~~~

Module import không phá vỡ encapsulation của module.

### 12.2. Module import không nhập mọi thứ bên trong module

Một module import không đưa vào phạm vi tên:

- Type không **public**.
- Type trong package không export cho module hiện tại.
- Type lồng bên trong một top-level type như một simple top-level name riêng.
- Field hoặc method static.
- Package name như thể đã viết một package import.

Nó đưa public top-level class và interface của các package đủ điều kiện vào phạm vi theo kiểu import-on-demand.

### 12.3. Module import không tự tạo readability

Trong một named module, module được import phải là module mà module hiện tại đọc được.

Ví dụ:

~~~java
module com.acme.app {
    requires com.acme.geometry;
}
~~~

Sau đó source file mới có thể dùng:

~~~java
import module com.acme.geometry;
~~~

Nếu bỏ **requires com.acme.geometry;**, module import không tự thêm dependency vào module graph. Compiler có thể báo module không được đọc.

### 12.4. Vai trò của requires transitive

Giả sử module **com.acme.facade** khai báo:

~~~java
module com.acme.facade {
    exports com.acme.facade;
    requires transitive com.acme.geometry;
}
~~~

Module nào đọc **com.acme.facade** cũng được đọc **com.acme.geometry** thông qua quan hệ transitive. Module import **com.acme.facade** có thể đưa vào phạm vi các public type từ những package được export của module mà current module đọc do đọc **com.acme.facade**.

Nếu một dependency chỉ được khai báo **requires** thông thường, các package của dependency đó không tự động trở thành tập type được module import gián tiếp đưa vào theo quy tắc transitive. Hãy phân biệt **requires**, **requires transitive** và **import module**.

## 13. Module import chỉ có phạm vi trong một compilation unit

Một import declaration chỉ có hiệu lực trong file nguồn chứa khai báo đó.

Ví dụ:

- **Main.java** có **import module com.acme.geometry;**.
- **GeometryAdapter.java** nằm cùng package nhưng không có module import.
- **GeometryAdapter.java** không tự động nhận các simple name từ import của **Main.java**.

Mỗi compilation unit cần khai báo import của chính nó hoặc dùng fully qualified name. Import không phải cấu hình chung cho package, module hay toàn bộ project.

## 14. Module import có dùng được khi không tự tạo named module?

Có. Module import declarations có thể xuất hiện trong ordinary compilation unit, kể cả source file không thuộc một named module. Các module chuẩn như **java.base** và **java.sql** có thể được import trong chương trình không được tổ chức thành named module, miễn là module cần import đã được resolve và đọc bởi compilation context.

Tuy nhiên, bài thực hành chính vẫn dùng named modules để bạn luyện đầy đủ cả hai phần:

- **requires** và **exports** của module system.
- **import module** trong compilation unit.

## 15. Biên dịch và chạy dự án nhiều module

Đặt JDK 25 trong PATH rồi kiểm tra compiler và runtime:

~~~bash
javac --version
java --version
~~~

Đứng tại thư mục gốc **module-import-lab** và biên dịch ba module:

~~~bash
javac --release 25 --module-source-path src -d out -m com.acme.geometry,com.acme.navigation,com.acme.app
~~~

Tùy chọn **--module-source-path src** chỉ vị trí các module source root. Tùy chọn **-m** liệt kê các module cần biên dịch; **-d out** đặt module output vào thư mục **out**. **--release 25** chọn source/API/bytecode Java 25. Module Import Declarations đã final trong release này, nên không cần **--enable-preview**.

Sau khi sửa **Main.java** bằng một trong các cách ở phần trên, chạy ứng dụng:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Với bản dùng single-type import và fully qualified name, output dự kiến:

~~~text
Geometry distance = 5.0
Route distance = 2.45 km
~~~

Nếu muốn tái hiện lỗi, thay **Main.java** bằng phiên bản ở mục 7 rồi chạy lại lệnh **javac**. Compiler sẽ dừng ở tham chiếu **Point** mơ hồ. Sau đó áp dụng cách sửa ở mục 8 hoặc 9, biên dịch lại và chạy ứng dụng.

## 16. Khi nào nên dùng module import?

| Tình huống | Cách dùng gợi ý | Lý do |
|---|---|---|
| Ví dụ học tập, demo API của một module | Module import | Giảm số dòng import |
| File sử dụng nhiều type từ một module cohesive | Module import | Tận dụng ranh giới module |
| File chỉ dùng một vài type | Single-type import | Nêu rõ dependency trực tiếp |
| Hai module export nhiều type trùng tên | Single-type import + fully qualified name | Kiểm soát simple name |
| API public của thư viện cần dễ rà soát dependency | Import tường minh | Người đọc thấy type cụ thể đang dùng |
| Module có nhiều package nội bộ không export | Module import vẫn an toàn | Chỉ type từ package được export mới được đưa vào |
| Dùng static method hoặc constant | **import static** hoặc tên đầy đủ | Module import không nhập static member |

Một module import rộng không có nghĩa chương trình tự động phụ thuộc vào mọi package trong module ở cấp runtime. Nó là cách làm các type public đủ điều kiện có thể được tham chiếu bằng simple name trong compilation unit.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| **reference to Point is ambiguous** | Nhiều module import export type cùng simple name | Thêm single-type import hoặc dùng fully qualified name |
| **reference to List is ambiguous** | **java.base** và **java.desktop** đều export **List** | Chọn **java.util.List** hoặc **java.awt.List** tường minh |
| Module không được đọc | Chưa khai báo **requires** trong module descriptor | Thêm dependency phù hợp vào **module-info.java** |
| Type public nhưng không truy cập được | Package chứa type không được export | Export package nếu đó là API công khai cần thiết |
| Type trong package internal không xuất hiện | Package không được export | Dùng API public hoặc thiết kế lại module boundary |
| Single-type import bị trùng tên | Import hai type khác nhau có cùng simple name | Chỉ import một type; qualify type còn lại |
| Import module nhưng không thấy static method | Module import chỉ nhập type | Gọi qua tên class hoặc dùng **import static** |
| Import trong file này nhưng file khác không thấy type | Import có phạm vi compilation unit | Khai báo import trong từng file cần dùng |
| Cú pháp **import module** bị từ chối | Compiler/source release thấp hơn Java 25 | Dùng JDK 25+ và **--release 25** hoặc cao hơn |
| Compiler báo preview flag không liên quan | Đang bật preview không cần thiết hoặc build nhầm release | Module Import Declarations final trong Java 25; bỏ **--enable-preview** nếu không dùng feature preview khác |

## 18. Bài tập mở rộng

**Bài 1 — Tạo module:** tạo đủ ba module **com.acme.geometry**, **com.acme.navigation** và **com.acme.app**. Khai báo exports và requires đúng theo cấu trúc bài.

**Bài 2 — Module import:** thay các import type riêng lẻ trong **Main.java** bằng **import module com.acme.geometry;** và **import module com.acme.navigation;**.

**Bài 3 — Tạo ambiguity:** tham chiếu **Point** bằng simple name mà không có single-type import. Ghi lại lỗi compiler.

**Bài 4 — Chọn kiểu mặc định:** thêm **import com.acme.geometry.Point;**. Dùng **Point** cho tọa độ hình học và fully qualified name cho tọa độ địa lý.

**Bài 5 — Không dùng import tường minh:** xóa single-type import, đổi cả hai biến **Point** thành fully qualified name. So sánh độ dễ đọc.

**Bài 6 — Thử explicit import conflict:** thêm cả **import com.acme.geometry.Point;** và **import com.acme.navigation.Point;**. Quan sát lỗi do hai single-type import cùng tên.

**Bài 7 — Module JDK:** tạo module dùng **java.desktop**, import **java.base** và **java.desktop**, rồi tái hiện xung đột **List**.

**Bài 8 — Readability:** xóa một dòng **requires** trong module app nhưng giữ **import module**. Quan sát lỗi và giải thích vì sao import không tạo dependency.

**Bài 9 — Encapsulation:** thêm package **com.acme.geometry.internal** nhưng không export. Tạo type public trong package đó và thử truy cập từ app.

**Bài 10 — Phạm vi import:** tạo **GeometryAdapter.java** cùng package với **Main.java**, không khai báo module import. Kiểm tra vì sao simple name không tự được đưa vào file mới.

**Bài 11 — So sánh:** viết một phiên bản dùng package wildcard imports và một phiên bản dùng module imports. So sánh số import, xung đột và khả năng nhận diện dependency.

**Bài 12 — Thiết kế:** đề xuất quy tắc import cho một dự án lớn: file nào được phép dùng module import, khi nào bắt buộc import tường minh và cách xử lý type trùng tên.

## 19. Checklist hoàn thành

- [ ] Biết Module Import Declarations là tính năng final của Java 25 theo JEP 511.
- [ ] Dùng cú pháp **import module ModuleName;**.
- [ ] Không bật **--enable-preview** chỉ để dùng module import.
- [ ] Hiểu module import đưa public top-level type từ exported package vào phạm vi tên.
- [ ] Phân biệt module import với **requires**.
- [ ] Hiểu module phải được current module đọc.
- [ ] Hiểu **exports** quyết định package nào được truy cập từ module khác.
- [ ] Nhận diện xung đột simple name giữa hai module.
- [ ] Dùng single-type import để shadow module import.
- [ ] Dùng fully qualified name khi cần cả hai kiểu cùng tên.
- [ ] Biết không thể import alias bằng cú pháp **as**.
- [ ] Biết import chỉ có hiệu lực trong compilation unit hiện tại.
- [ ] Biết module import không nhập static member.
- [ ] Biết module import không làm lộ package không export.
- [ ] Biết **requires transitive** ảnh hưởng đến module readability và tập type được import.
- [ ] Biên dịch và chạy được ứng dụng nhiều module trên JDK 25.

## Tài liệu tham khảo chính thức

- [JEP 511 — Module Import Declarations](https://openjdk.org/jeps/511): đặc tả tính năng đã hoàn tất trong Java 25.
- [Oracle Java 25 — Module Import Declarations](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html): cách dùng module import, phạm vi import và ví dụ xung đột List/Label.
- [Java Language Specification 25 — 7.5.5 Single-Module-Import Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5.5): quy tắc nhập public top-level type và điều kiện module readability.
- [Java Language Specification 25 — 7.5.1 Single-Type-Import Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5.1): quy tắc import một type, xung đột và shadowing.
- [Java Language Specification 25 — 7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7): khai báo module, requires và exports.
- [Oracle Java 25 — The javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): tùy chọn biên dịch và module source path.

## Kết luận

Module Import Declarations giúp code sử dụng API của một module ngắn gọn hơn bằng cách đưa các public top-level type từ package được export vào phạm vi tên của compilation unit. Trong Java 25, đây là tính năng final theo JEP 511 và không cần bật preview.

Khi nhiều module export type trùng simple name, compiler yêu cầu code chỉ rõ ý định. Dùng single-type import để chọn kiểu mặc định và shadow module import, hoặc dùng fully qualified name khi cần nhiều kiểu cùng tên. Hãy luôn giữ rõ ranh giới **requires/exports** trong module descriptor: **module import tổ chức tên trong source file, còn module system quyết định module nào được đọc và package nào được truy cập.**
