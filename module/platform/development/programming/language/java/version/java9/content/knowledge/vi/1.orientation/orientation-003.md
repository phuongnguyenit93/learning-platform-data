# Phân biệt mô-đun JPMS với package và đơn vị xây dựng dự án

## Mục tiêu

Sau bài này, bạn có thể phân biệt ba loại ranh giới thường cùng xuất hiện trong một dự án Java:

- **Package** tổ chức tên và kiểu Java, đồng thời tham gia quyết định quyền truy cập ở cấp ngôn ngữ.
- **Mô-đun JPMS** khai báo phụ thuộc, khả năng đọc và những package được công khai giữa các mô-đun ở cấp nền tảng Java.
- **Đơn vị xây dựng dự án** tổ chức việc biên dịch, kiểm thử, đóng gói và quản lý phụ thuộc theo công cụ như Gradle hoặc Maven.

Ba khái niệm có thể được dùng cùng nhau, nhưng chúng được khai báo ở những nơi khác nhau và giải quyết những vấn đề khác nhau.

## 1. So sánh nhanh

| Tiêu chí | Package | Mô-đun JPMS | Đơn vị xây dựng |
|---|---|---|---|
| Vai trò | Nhóm và định danh các kiểu Java | Tạo ranh giới phụ thuộc và đóng gói ở cấp mô-đun Java | Chia cấu trúc build thành các phần có thể biên dịch, kiểm thử và đóng gói |
| Nơi khai báo | Câu lệnh package trong tệp .java | module-info.java | settings.gradle(.kts), pom.xml và cấu hình build tương ứng |
| Tên được dùng ở đâu | Trong package và import | Trong module, requires, exports | Trong cấu hình project/module của Gradle hoặc Maven |
| Phạm vi quản lý | Namespace và quyền truy cập của kiểu | Đồ thị mô-đun, khả năng đọc và package được xuất | Source set, dependency, task, test và artifact |
| Có tạo JAR không? | Không | Bản thân mô-đun không phải công cụ đóng gói; mô tả mô-đun có thể được đưa vào JAR | Thường tạo hoặc tham gia tạo JAR, WAR hay artifact khác |

Ví dụ, trong một dự án có thể đồng thời có:

- Gradle project tên **:geometry**;
- JPMS module tên **com.example.geometry**;
- package tên **com.example.geometry.api**.

Ba tên này có thể liên quan với nhau theo quy ước của dự án, nhưng không đồng nghĩa.

## 2. Package: namespace của các kiểu Java

Package là cách Java nhóm các lớp, interface, enum, record và những kiểu khác dưới một namespace. Tệp nguồn khai báo package bằng câu lệnh package:

~~~java
package com.example.geometry.api;

public record Point(int x, int y) {}
~~~

Tên package thường được phản ánh qua cấu trúc thư mục, chẳng hạn **com/example/geometry/api/Point.java**. Cấu trúc thư mục là quy ước tổ chức phổ biến; điều quan trọng với trình biên dịch là khai báo package và cách source được đưa vào quá trình biên dịch.

Package hỗ trợ hai việc chính:

1. Tránh trùng tên giữa các kiểu thuộc những vùng tên khác nhau. Hai package khác nhau có thể cùng chứa một kiểu tên Config.
2. Tạo phạm vi truy cập ở cấp ngôn ngữ. Kiểu hoặc thành viên không có modifier truy cập thường chỉ được truy cập từ cùng package; protected, public và private có quy tắc riêng.

Package **không** tự khai báo đồ thị phụ thuộc giữa các nhóm mã. Việc một lớp nằm trong package **com.example.geometry.api** không tự tạo ra một mô-đun, một Gradle project hay một artifact độc lập.

Cũng cần phân biệt public với khả năng truy cập qua ranh giới JPMS. Một kiểu public vẫn có thể không được mô-đun khác sử dụng nếu package chứa kiểu đó không được mô-đun chủ quản xuất ra.

## 3. Mô-đun JPMS: ranh giới ở cấp nền tảng Java

JPMS là viết tắt của **Java Platform Module System**. Hệ thống này được đưa vào Java 9 và vẫn là một phần của Java hiện đại. Một mô-đun có tên tường minh khai báo hợp đồng của mình trong tệp **module-info.java**.

Ví dụ:

~~~java
module com.example.geometry {
    exports com.example.geometry.api;
}
~~~

Tệp trên khai báo mô-đun tên **com.example.geometry** và xuất package **com.example.geometry.api**. Nó không phải một câu lệnh package và cũng không phải cấu hình Gradle/Maven.

Các chỉ thị thường gặp trong module descriptor:

| Chỉ thị | Ý nghĩa |
|---|---|
| requires | Khai báo mô-đun phụ thuộc mà mô-đun hiện tại cần đọc |
| exports | Công khai một package cho các mô-đun đọc mô-đun này |
| opens | Cho phép truy cập phản chiếu sâu vào package ở runtime |
| uses | Khai báo mô-đun sử dụng một service |
| provides ... with ... | Khai báo implementation cung cấp cho một service |

### requires khác import

requires dùng **tên mô-đun** để khai báo quan hệ phụ thuộc trong đồ thị JPMS:

~~~java
module com.example.app {
    requires com.example.geometry;
}
~~~

import dùng **tên package và kiểu** để tham chiếu kiểu Java trong mã nguồn:

~~~java
import com.example.geometry.api.Point;
~~~

Khai báo requires com.example.geometry không tự đưa mọi kiểu trong mô-đun vào namespace của lớp. Mã nguồn vẫn import kiểu cần sử dụng, và package đó phải được mô-đun cung cấp xuất ra.

### exports khác opens

- exports cho phép mã của mô-đun khác sử dụng các kiểu public trong package được xuất, nếu mô-đun gọi có quyền đọc mô-đun cung cấp.
- opens phục vụ truy cập phản chiếu sâu ở runtime, thường cần cho framework hoặc thư viện phải đọc/ghi thành viên không công khai bằng reflection. opens không thay thế exports cho việc import và gọi API thông thường lúc biên dịch.

Vì vậy, một mô-đun có thể giữ package nội bộ không được exports, dù các lớp trong đó có khai báo public. Đây là một phần của cơ chế đóng gói mạnh ở cấp mô-đun. Quyền truy cập của JPMS và modifier truy cập của Java cùng được áp dụng.

### Mô-đun có thể chứa nhiều package

Một mô-đun JPMS thường chứa nhiều package. Module descriptor quyết định package nào được xuất và mô-đun nào được yêu cầu; package vẫn giữ vai trò tổ chức các kiểu bên trong mô-đun.

Tên mô-đun không bắt buộc trùng tên package. Ví dụ:

- Mô-đun: **com.example.geometry**
- Package API: **com.example.geometry.api**
- Package nội bộ: **com.example.geometry.internal**

Tránh đặt cùng một package trong nhiều mô-đun có tên cùng tham gia một module layer. Kiểu tổ chức đó tạo ra split package và có thể khiến việc biên dịch hoặc phân giải mô-đun thất bại.

### Module path và các dạng mô-đun

JPMS phân giải các mô-đun từ **module path**. Khi biên dịch hoặc chạy một ứng dụng modular, có thể chỉ định đường dẫn này bằng tùy chọn **--module-path**.

Trong môi trường Java hiện nay, cần nhận diện ba trường hợp:

- **Explicit module:** JAR hoặc đầu vào mô-đun có module descriptor **module-info.class**, được tạo từ **module-info.java**.
- **Automatic module:** JAR không có module descriptor nhưng được đặt trên module path. Tên mô-đun có thể lấy từ thuộc tính manifest **Automatic-Module-Name**; nếu không có, tên được suy ra từ tên JAR. Đây là cơ chế tương thích hữu ích khi chuyển dần thư viện sang JPMS.
- **Unnamed module:** Mã được nạp từ classpath thuộc unnamed module. Cách chạy này vẫn được hỗ trợ, nhưng không có cùng hợp đồng đóng gói tường minh như một explicit module.

Một JAR không tự động trở thành explicit module chỉ vì nó là JAR. Cần xét module descriptor và vị trí JAR được đưa vào khi biên dịch hoặc chạy.

## 4. Đơn vị xây dựng: ranh giới của Gradle hoặc Maven

Trong bài này, **đơn vị xây dựng** được hiểu là một Gradle project/subproject hoặc một Maven module. Đây là khái niệm của công cụ build, không phải một loại package hay một loại mô-đun được Java định nghĩa.

Đơn vị xây dựng thường quyết định:

- Mã nguồn và source set nào được biên dịch;
- Dependency nào được đưa vào compile classpath hoặc runtime classpath/module path;
- Task kiểm thử, đóng gói và các bước build cần chạy;
- Artifact nào được tạo, phiên bản và cách artifact được tiêu thụ bởi project khác.

Ví dụ với Gradle Kotlin DSL:

~~~kotlin
rootProject.name = "geometry-workspace"
include("geometry", "app")
~~~

Khai báo trên tạo hai Gradle subproject có định danh **:geometry** và **:app**. Nó **không** tự tạo hai JPMS module. Muốn hai project là explicit JPMS module, source của chúng cần có module descriptor phù hợp và quá trình biên dịch/đóng gói phải xử lý descriptor đó.

Một đơn vị xây dựng có thể:

- Tạo JAR không có module descriptor;
- Tạo modular JAR chứa **module-info.class**;
- Quản lý nhiều package trong cùng một artifact;
- Tham gia một build lớn có nhiều project và nhiều artifact.

Do đó, quan hệ giữa Gradle/Maven module và JPMS module là quan hệ do cách tổ chức dự án quyết định. Mô hình thường gặp là mỗi build subproject tạo một modular JAR, nhưng JPMS không bắt buộc mọi build project phải tương ứng một-một với một mô-đun Java.

## 5. Ví dụ chạy được: hai JPMS module

Ví dụ sau có hai mô-đun tường minh. Mô-đun **com.example.geometry** cung cấp kiểu **Point**; mô-đun **com.example.app** khai báo phụ thuộc và sử dụng kiểu đó.

Cấu trúc thư mục:

~~~text
src/
├── com.example.geometry/
│   ├── module-info.java
│   └── com/example/geometry/api/Point.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

**Mô-đun geometry — src/com.example.geometry/module-info.java:**

~~~java
module com.example.geometry {
    exports com.example.geometry.api;
}
~~~

**Kiểu được xuất — src/com.example.geometry/com/example/geometry/api/Point.java:**

~~~java
package com.example.geometry.api;

public record Point(int x, int y) {}
~~~

**Mô-đun ứng dụng — src/com.example.app/module-info.java:**

~~~java
module com.example.app {
    requires com.example.geometry;
}
~~~

**Lớp chạy — src/com.example.app/com/example/app/Main.java:**

~~~java
package com.example.app;

import com.example.geometry.api.Point;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Point(3, 4));
    }
}
~~~

Mở terminal tại thư mục chứa **src/**, dùng JDK 17 trở lên và chạy:

~~~bash
javac -d out --module-source-path src -m com.example.geometry,com.example.app
java --module-path out -m com.example.app/com.example.app.Main
~~~

Kết quả chuẩn:

~~~text
Point[x=3, y=4]
~~~

Ví dụ này thể hiện ba lớp khái niệm:

1. **com.example.geometry** và **com.example.app** là tên JPMS module, xuất hiện trong **module-info.java** và **requires**.
2. **com.example.geometry.api** và **com.example.app** là package, xuất hiện trong khai báo **package** và câu lệnh **import**.
3. Nếu đặt mã nguồn của hai mô-đun trên trong hai Gradle subproject, **:geometry** và **:app** sẽ là đơn vị xây dựng. Tên project có thể khác tên JPMS module.

Lệnh javac biên dịch hai mô-đun từ module source path và đưa kết quả vào **out**. Lệnh java phân giải mô-đun từ module path, sau đó chạy lớp chính thuộc mô-đun ứng dụng. Ví dụ đã được biên dịch và chạy trên JDK 24; mã nguồn sử dụng record nên tương thích với JDK 17 trở lên.

## 6. Cách nhận diện trong một repository

Khi đọc một dự án Java, hãy tìm đúng loại khai báo tương ứng:

| Dấu hiệu trong repository | Khái niệm cần nhận diện |
|---|---|
| package com.example...; trong tệp .java | Package |
| module-info.java có module, requires, exports | JPMS module |
| include("...") trong settings.gradle(.kts) | Gradle project/subproject |
| modules trong POM aggregator | Maven module |
| module-info.class ở gốc JAR | Module descriptor đã biên dịch và được đóng gói |

Có thể kiểm tra JAR để xem descriptor có được đóng gói hay không:

~~~bash
jar --describe-module --file geometry.jar
~~~

Lệnh này hiển thị thông tin mô-đun mà JDK nhận diện từ JAR. Với JAR không có descriptor, kết quả có thể cho thấy đó là automatic module nếu JAR được xử lý theo ngữ cảnh module path.

Đừng suy ra loại ranh giới chỉ từ tên thư mục. Một thư mục tên module có thể chỉ là thư mục con của build; một package có tên kết thúc bằng .module vẫn chỉ là package nếu không có module descriptor.

## 7. Những nhầm lẫn thường gặp

1. **Package chính là JPMS module.** Không đúng. Package nhóm kiểu; JPMS module nhóm package và khai báo quan hệ phụ thuộc, khả năng đọc, phần API được xuất.
2. **Có public là mô-đun khác dùng được.** Chưa đủ. Kiểu còn phải nằm trong package được mô-đun chủ quản xuất ra và mô-đun gọi phải đọc được mô-đun đó.
3. **Gradle include tạo JPMS module.** Không đúng. Nó khai báo build subproject. JPMS module được khai báo bằng module descriptor.
4. **Mỗi JAR đều là explicit module.** Không đúng. JAR có thể có descriptor, có thể trở thành automatic module trên module path, hoặc được dùng trên classpath.
5. **exports và opens giống nhau.** Không đúng. exports công khai API ở cấp package; opens cho phép truy cập phản chiếu sâu ở runtime.
6. **requires thay cho import.** Không đúng. requires khai báo phụ thuộc mô-đun; import tham chiếu kiểu trong mã nguồn.
7. **Tên Gradle project phải trùng tên JPMS module.** Không bắt buộc. Hai tên thuộc hai hệ thống khác nhau và chỉ cần được cấu hình nhất quán khi build.

## 8. Chọn ranh giới phù hợp

- Dùng **package** để tổ chức namespace, API và mã nội bộ trong mã nguồn Java.
- Dùng **JPMS module** khi cần khai báo phụ thuộc rõ ràng, giới hạn package được công khai và kiểm soát khả năng truy cập giữa các phần của ứng dụng hoặc thư viện.
- Dùng **đơn vị xây dựng** để chia quá trình biên dịch, kiểm thử, đóng gói, quản lý dependency và phát hành theo nhu cầu của dự án.

Ba ranh giới có thể phối hợp: Gradle chia dự án thành các subproject; mỗi subproject tạo một modular JAR; bên trong từng mô-đun, package phân chia API và phần triển khai. Cách ánh xạ này là lựa chọn kiến trúc của dự án.

Không cần thêm JPMS descriptor chỉ để đổi tên package hoặc chia Gradle project. Hãy dùng JPMS khi lợi ích về hợp đồng phụ thuộc và đóng gói mô-đun thực sự cần thiết; nếu chưa cần, package và cấu trúc build vẫn đảm nhiệm tốt vai trò riêng của chúng.
