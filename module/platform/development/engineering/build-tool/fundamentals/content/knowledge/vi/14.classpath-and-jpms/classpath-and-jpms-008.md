# Mô-đun build và mô-đun JPMS: hai ranh giới cần phân biệt

Trong dự án Java, từ “module” thường được dùng cho hai khái niệm khác nhau. Một bên là **project/module của build tool**, chẳng hạn một subproject trong Gradle multi-project build. Bên kia là **module của Java Platform Module System (JPMS)**, được mô tả bằng file `module-info.java` và được Java compiler/JVM nhận diện trên module path.

Hai khái niệm này có thể cùng xuất hiện trong một repository và thường phối hợp với nhau, nhưng chúng không đồng nhất. Gradle project xác định cách mã nguồn, task, dependency và artifact được tổ chức để build. JPMS module xác định một đơn vị mã Java có tên, tập package được export, dependency module được yêu cầu và các quy tắc truy cập ở compile/runtime.

Nếu nhầm hai ranh giới này, ta dễ cho rằng thêm `include 'domain'` trong `settings.gradle` sẽ tự tạo ra một JPMS module, hoặc khai báo `requires com.example.domain` trong `module-info.java` sẽ tự khiến Gradle tải dependency tương ứng. Cả hai suy luận đều sai. Một dự án modular hóa đúng thường cần cấu hình ở cả build tool và JPMS, mỗi bên giải quyết một phần việc riêng.

## 1. Hai khái niệm “module” thuộc hai hệ thống khác nhau

Gradle tổ chức công việc build theo build và project. JPMS tổ chức chương trình Java theo module và package. Một Gradle project có thể tạo ra một JAR là JPMS module; nhưng tên Gradle project không tự động trở thành tên JPMS module.

| Khía cạnh | Gradle project / build module | JPMS module |
|---|---|---|
| Hệ thống quản lý | Gradle | Java Platform Module System |
| Định nghĩa chính | `settings.gradle`, build scripts, plugin | `module-info.java` hoặc quy tắc automatic module |
| Đơn vị tổ chức | Project trong một Gradle build | Module có tên trong module graph |
| Quan hệ phụ thuộc | Dependency declaration và project dependency | Chỉ thị `requires` trong module descriptor |
| Phạm vi truy cập | Build logic, source sets, configurations, tasks | Package exports, readability, opens |
| Đầu ra thường gặp | Project output, JAR, WAR, distribution | Thường là modular JAR hoặc module directory |
| Thời điểm có tác dụng | Initialization, configuration và execution của Gradle | Compile-time và runtime của Java compiler/JVM |
| Câu hỏi trả lời | Project nào build trước, task nào chạy, artifact nào được tạo? | Module nào đọc được module nào, package nào được truy cập? |

Có thể hình dung một repository như sau:

~~~text
commerce-platform/                 # Một Gradle build
├── settings.gradle
├── build.gradle
├── orders-app/                     # Một Gradle project
│   ├── build.gradle
│   └── src/main/java/
│       └── module-info.java         # JPMS module descriptor
└── orders-domain/                  # Một Gradle project khác
    ├── build.gradle
    └── src/main/java/
        └── module-info.java         # JPMS module descriptor khác
~~~

Trong ví dụ này:

- `orders-app` và `orders-domain` là Gradle project paths.
- Hai file `module-info.java` định nghĩa hai JPMS modules.
- Gradle quản lý việc biên dịch và tạo artifact cho từng project.
- JPMS kiểm soát quan hệ module giữa các JAR khi compile hoặc chạy.

Tên project có thể là `orders-domain` trong khi tên JPMS module là `com.example.orders.domain`. Hai tên phục vụ hai mục đích khác nhau và không cần giống nhau.

## 2. Gradle project là ranh giới tổ chức build

Một Gradle build có thể gồm root project và nhiều subproject. Cấu trúc này được khai báo trong settings script.

~~~groovy
rootProject.name = 'commerce-platform'

include 'orders-domain'
include 'orders-app'
include 'reporting'
~~~

Các lệnh `include` đưa project vào build. Mỗi project có thể có build script riêng, plugin riêng, source sets, configurations, task và output directory riêng.

Gradle project giúp nhóm chia mã nguồn thành các phần có trách nhiệm rõ ràng, quản lý dependency giữa project, áp dụng plugin hoặc convention chung, chạy task theo project path và tạo artifact riêng.

Ví dụ dependency giữa hai Gradle project:

~~~groovy
// orders-app/build.gradle
dependencies {
    implementation project(':orders-domain')
}
~~~

Dòng này khai báo rằng project `orders-app` phụ thuộc vào component do Gradle project `orders-domain` cung cấp. Gradle sử dụng quan hệ đó để thiết lập dependency cho configuration và task graph phù hợp. Tuy nhiên, nó chưa nói package nào của domain được phép truy cập ở cấp Java module. Đó là trách nhiệm của JPMS.

### 2.1. Project dependency không phải chỉ thị JPMS

Một Gradle project dependency có thể giúp Gradle đưa output của project producer vào classpath hoặc module path của consumer tùy cách build được cấu hình. Nhưng bản thân dòng `implementation project(':orders-domain')` không thay thế `requires` trong module descriptor.

Ngược lại, một chỉ thị `requires com.example.orders.domain` không khai báo cho Gradle biết project nào hoặc repository nào cung cấp module đó. Compiler chỉ có thể resolve tên module nếu module tương ứng đã được cung cấp trên module path của invocation compile.

Với một ứng dụng modular, thường cần cả hai khai báo:

~~~groovy
// orders-app/build.gradle
dependencies {
    implementation project(':orders-domain')
}
~~~

~~~java
// orders-app/src/main/java/module-info.java
module com.example.orders.app {
    requires com.example.orders.domain;
}
~~~

Khai báo Gradle cho build biết dependency component nằm ở đâu. Khai báo JPMS cho compiler và JVM biết module app cần đọc module domain.

## 3. JPMS module là ranh giới của chương trình Java

JPMS được giới thiệu trong Java 9 để bổ sung hệ thống module cho nền tảng Java. Một JPMS module có tên, chứa các package và có thể khai báo:

- Những module mà nó cần đọc thông qua `requires`.
- Những package được công khai cho module khác thông qua `exports`.
- Những package được mở cho reflection thông qua `opens`.
- Các service mà module sử dụng hoặc cung cấp thông qua `uses` và `provides`.

Một module tường minh (explicit/named module) thường có descriptor `module-info.java` ở root của source module. Khi biên dịch và đóng gói, descriptor trở thành `module-info.class` trong modular JAR.

Ví dụ:

~~~java
module com.example.orders.domain {
    exports com.example.orders.api;
}
~~~

Module có tên `com.example.orders.domain` và chỉ export package `com.example.orders.api`. Những package khác trong module không tự động trở thành API công khai cho module khác.

JPMS cung cấp hai cơ chế quan trọng:

- **Readability:** module này có thể đọc module khác hay không.
- **Encapsulation/accessibility:** package và type nào được module khác truy cập.

Việc một JAR có trên filesystem hoặc có mặt trong dependency graph của Gradle không tự động có nghĩa mọi package trong JAR đều được module khác truy cập.

### 3.1. `requires`: khai báo module cần đọc

~~~java
module com.example.orders.app {
    requires com.example.orders.domain;
    requires java.logging;
    requires java.sql;
}
~~~

Chỉ thị `requires` tạo quan hệ readability từ app tới domain. Tên ở đây là JPMS module name, không phải tên project Gradle hoặc Maven artifactId. Các module nền tảng như `java.logging` và `java.sql` được cung cấp bởi JDK; module bên thứ ba cần được cung cấp trên module path.

### 3.2. `exports`: công khai package nào

~~~java
module com.example.orders.domain {
    exports com.example.orders.api;
}
~~~

Module consumer có thể truy cập các public type thuộc package được export nếu module đó cũng đọc được domain. Public class nằm trong package không export không mặc nhiên trở thành API có thể truy cập từ module khác.

Đây là khác biệt với classpath truyền thống, nơi public class thường có thể được nhìn thấy miễn là JAR nằm trên classpath và package/type không bị hạn chế bởi các cơ chế khác.

### 3.3. `opens`: cho phép reflection

Một số framework cần reflection để truy cập field, constructor hoặc member không public. JPMS phân biệt export package cho truy cập thông thường và open package cho reflection.

~~~java
module com.example.orders.domain {
    exports com.example.orders.api;
    opens com.example.orders.internal.persistence;
}
~~~

`opens` mở package cho deep reflection theo quy tắc JPMS. Có thể dùng qualified opens để chỉ mở cho một module cụ thể:

~~~java
opens com.example.orders.internal.persistence to org.hibernate.orm.core;
~~~

Không nên mở toàn bộ module bằng `open module` nếu chỉ một số package cần reflection. Mở rộng quá mức làm giảm hiệu quả đóng gói mà JPMS mang lại.

## 4. Một Gradle project và một JPMS module không có quan hệ một-một bắt buộc

Trong nhiều dự án, một Gradle project Java tạo một JAR có một JPMS module descriptor. Đây là cách tổ chức dễ hiểu, nhưng không phải quy tắc đồng nhất giữa hai hệ thống.

Các trường hợp có thể gặp:

1. Một Gradle project tạo một modular JAR chứa một JPMS module.
2. Một Gradle project tạo JAR không có module descriptor; khi đặt trên module path, JAR có thể được xử lý như automatic module.
3. Một Gradle project tạo artifact chỉ dùng trên classpath, không tham gia module graph như named module.
4. Một Gradle build gồm nhiều project, mỗi project tạo một JPMS module riêng.
5. Một build có project chỉ chứa build logic, script, resource hoặc tooling, không tạo JPMS module nào.
6. Một project có nhiều source sets hoặc nhiều artifact; cách tổ chức JPMS cho các artifact đó cần được thiết kế riêng, không thể mặc định rằng mỗi source set là một module độc lập.

Vì thế, khi nghe “module domain”, cần xác định ngữ cảnh đang nói về Gradle project, Maven artifact, JPMS module hay một module nghiệp vụ theo cách gọi của nhóm.

## 5. Tên Gradle project, Maven artifact và JPMS module name

Ba loại tên này có thể khác nhau:

| Loại tên | Ví dụ | Được dùng ở đâu? |
|---|---|---|
| Gradle project path | `:orders-domain` | Task path, project dependency, cấu trúc build |
| Maven coordinates | `com.example:orders-domain:1.4.0` | Repository và dependency declaration |
| JPMS module name | `com.example.orders.domain` | `requires`, module path và module resolution |

Ví dụ build script:

~~~groovy
dependencies {
    implementation 'com.example:orders-domain:1.4.0'
}
~~~

Module descriptor:

~~~java
module com.example.orders.domain {
    exports com.example.orders.api;
}
~~~

Không có quy tắc bắt buộc rằng artifactId `orders-domain` phải bằng module name `com.example.orders.domain`. Tuy nhiên, nên chọn tên JPMS ổn định, dễ hiểu và tránh xung đột với module khác.

### 5.1. Module name của modular JAR

Với explicit module, tên module được khai báo trong `module-info.java`. Đây là nguồn xác định rõ ràng nhất.

Nếu JAR không có descriptor, nó có thể trở thành automatic module khi được đặt trên module path. Tên automatic module có thể được xác định từ manifest attribute `Automatic-Module-Name` nếu có; nếu không, tên có thể được suy ra từ tên file JAR theo quy tắc của Java.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy.client
~~~

Khai báo `Automatic-Module-Name` giúp tên module ổn định hơn khi filename hoặc version thay đổi. Nếu dự án có kế hoạch hỗ trợ JPMS, nên cung cấp tên module ổn định thay vì phụ thuộc vào tên file suy diễn.

### 5.2. Automatic module không giống explicit module

Automatic module là cách tương thích để thư viện JAR cũ có thể tham gia module path dù chưa có `module-info.java`. Nó có tên module và có thể được các named module yêu cầu, nhưng quy tắc encapsulation và dependency của nó khác explicit module.

Automatic module thường đọc các module khác theo quy tắc rộng hơn và export các package của nó. Vì vậy, nó là cầu nối chuyển tiếp, không thay thế thiết kế module descriptor tường minh khi cần kiểm soát API chặt chẽ.

## 6. Classpath và module path là hai cách cung cấp thư viện khác nhau

Java compiler và JVM có hai cơ chế quan trọng để tìm code:

- **Classpath:** tập hợp class directory và JAR được xem như classpath. Các class trên classpath thuộc unnamed module trong mô hình JPMS.
- **Module path:** nơi chứa các module có tên mà Java module system sẽ resolve thành module graph.

Ví dụ compile truyền thống:

~~~bash
javac -cp libs/orders-domain.jar -d out src/com/example/app/Main.java
~~~

Ví dụ compile theo JPMS:

~~~bash
javac --module-path mods -d out src/module-info.java src/com/example/app/Main.java
~~~

Ví dụ chạy trên classpath:

~~~bash
java -cp app.jar:libs/* com.example.app.Main
~~~

Ví dụ chạy theo module:

~~~bash
java --module-path mods --module com.example.orders.app/com.example.orders.app.Main
~~~

Trên Windows, dấu phân cách classpath thường là dấu chấm phẩy; trên Unix-like systems thường là dấu hai chấm. Ví dụ chạy thực tế cần dùng đúng cú pháp của hệ điều hành.

### 6.1. Unnamed module

Code trên classpath không có module descriptor được xem như thuộc unnamed module. Trong ứng dụng truyền thống, nhiều JAR trên classpath cùng góp phần tạo thành môi trường class loading không có ranh giới named-module rõ ràng.

Một named module không thể khai báo `requires` tới unnamed module. Vì vậy, nếu ứng dụng có `module-info.java` nhưng một dependency cần thiết chỉ được đưa lên classpath thay vì module path, compiler có thể không tìm thấy module name được yêu cầu.

Đây là lý do classpath/module path phải được cấu hình nhất quán với module descriptor.

### 6.2. Module path không chỉ là một classpath có tên khác

Khi sử dụng module path, compiler/runtime phải resolve module graph và kiểm tra các quy tắc JPMS như:

- Module được yêu cầu có tồn tại không?
- Có nhiều module cùng tên gây xung đột không?
- Quan hệ readability có hợp lệ không?
- Package có được export tới consumer không?
- Có split package hoặc xung đột package không?
- Module có phù hợp với yêu cầu runtime và phiên bản Java không?

Classpath truyền thống không thực thi cùng bộ quy tắc encapsulation và readability này.

## 7. Gradle hỗ trợ JPMS như thế nào?

Gradle vẫn là build tool: nó quản lý project, dependency configurations, task graph và artifact. Khi project sử dụng JPMS, Gradle cần cung cấp module path phù hợp cho các task biên dịch và chạy.

Java plugin có hỗ trợ suy luận module path (module path inference). Có thể cấu hình rõ trong build script:

~~~groovy
plugins {
    id 'java'
}

java {
    modularity.inferModulePath = true
}
~~~

Khi bật inference, Gradle có thể nhận diện các dependency có module descriptor hoặc automatic module phù hợp và đặt chúng lên module path cho các task Java liên quan theo quy tắc của plugin. Hành vi cụ thể còn phụ thuộc phiên bản Gradle, JDK, cấu trúc source set và dependency được resolve.

Không nên tự suy luận rằng mọi dependency sẽ tự động lên module path chỉ vì project có file `module-info.java`. Hãy kiểm tra Gradle version, cấu hình modularity và compiler arguments thực tế.

### 7.1. Gradle dependency và `requires` cần khớp nhau

Giả sử project app cần domain:

~~~groovy
// orders-app/build.gradle
dependencies {
    implementation project(':orders-domain')
}
~~~

Và module descriptor:

~~~java
// orders-app/src/main/java/module-info.java
module com.example.orders.app {
    requires com.example.orders.domain;
}
~~~

Phía domain:

~~~java
// orders-domain/src/main/java/module-info.java
module com.example.orders.domain {
    exports com.example.orders.api;
}
~~~

Ba phần phối hợp:

1. Settings script đưa cả hai Gradle project vào build.
2. Dependency declaration giúp Gradle cung cấp output của domain cho app.
3. JPMS descriptors xác định app đọc domain và domain export package API nào.

Nếu thiếu bước 2, compiler có thể không có domain module trên module path. Nếu thiếu bước 3, Gradle vẫn có thể build dependency như một project component, nhưng JPMS không có quan hệ module được khai báo như mong đợi.

### 7.2. Gradle project dependency không bảo đảm JPMS module name đúng

Dòng:

~~~groovy
implementation project(':orders-domain')
~~~

chỉ tham chiếu Gradle project path. Tên JPMS module phải được lấy từ module descriptor hoặc quy tắc automatic module của artifact. Không được tự lấy project name làm giá trị cho `requires`.

Ví dụ, project path là `:orders-domain` nhưng descriptor khai báo:

~~~java
module com.acme.sales.domain {
    exports com.acme.sales.domain.api;
}
~~~

Thì consumer cần dùng:

~~~java
requires com.acme.sales.domain;
~~~

Không phải `requires orders-domain;`.

## 8. `api` / `implementation` của Gradle khác `exports` / `requires` của JPMS

Đây là một trong những điểm dễ nhầm nhất khi modular hóa Java.

| Gradle | JPMS | Ý nghĩa |
|---|---|---|
| `implementation` | Không tương đương trực tiếp | Dependency phục vụ implementation của Gradle component |
| `api` | Không đồng nghĩa với `exports` | Dependency được đưa vào API/compile contract của consumer theo Java Library plugin |
| Project/module dependency | `requires` | Một bên nối component trong build; một bên tạo readability giữa JPMS modules |
| Published API variant | `exports` | Một bên mô tả dependency/component cho consumer build; một bên công khai package Java |
| Runtime dependency | `requires` / module resolution | Có liên quan nhưng khác lớp quản lý và không thay thế nhau |

Ví dụ một library có public API sử dụng type từ module khác:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':money-types')
}
~~~

~~~java
module com.example.orders.domain {
    requires transitive com.example.money.types;
    exports com.example.orders.api;
}
~~~

Hai khai báo phục vụ hai hệ thống:

- Gradle `api` nói với Gradle publication model rằng dependency thuộc API compile contract của consumer.
- JPMS `requires transitive` nói rằng module consumer đọc domain cũng cần có readability tới module money types theo quy tắc JPMS.
- JPMS `exports` xác định package API nào của domain được module khác truy cập.

Không nên thay `api` bằng `exports`, hoặc thay `requires` bằng `implementation`. Chúng không phải cú pháp tương đương.

### 8.1. `requires transitive` khác `api`

`requires transitive` là chỉ thị JPMS. Nó mở rộng readability: module nào đọc module hiện tại cũng có thể đọc module được yêu cầu transitive theo quy tắc module system.

Gradle `api` là cách công bố dependency trong Java Library component để consumer build có dependency cần thiết trên compile classpath. Hai cơ chế thường được dùng đồng bộ trong một library modular, nhưng phạm vi và tác dụng không giống nhau.

## 9. Ví dụ hoàn chỉnh: hai Gradle project tạo hai JPMS modules

Giả sử cấu trúc repository:

~~~text
commerce-platform/
├── settings.gradle
├── orders-domain/
│   ├── build.gradle
│   └── src/main/java/
│       ├── module-info.java
│       └── com/example/orders/api/Order.java
└── orders-app/
    ├── build.gradle
    └── src/main/java/
        ├── module-info.java
        └── com/example/orders/app/Main.java
~~~

### 9.1. Khai báo Gradle projects

File `settings.gradle`:

~~~groovy
rootProject.name = 'commerce-platform'

include 'orders-domain'
include 'orders-app'
~~~

File `orders-domain/build.gradle`:

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

java {
    modularity.inferModulePath = true
}
~~~

File `orders-app/build.gradle`:

~~~groovy
plugins {
    id 'application'
}

group = 'com.example'
version = '1.0.0'

java {
    modularity.inferModulePath = true
}

dependencies {
    implementation project(':orders-domain')
}

application {
    mainClass = 'com.example.orders.app.Main'
}
~~~

### 9.2. Khai báo JPMS module descriptors

File `orders-domain/src/main/java/module-info.java`:

~~~java
module com.example.orders.domain {
    exports com.example.orders.api;
}
~~~

File `orders-app/src/main/java/module-info.java`:

~~~java
module com.example.orders.app {
    requires com.example.orders.domain;
}
~~~

Class API trong domain:

~~~java
package com.example.orders.api;

public record Order(String id) {
}
~~~

Main class trong app:

~~~java
package com.example.orders.app;

import com.example.orders.api.Order;

public class Main {
    public static void main(String[] args) {
        Order order = new Order("ORD-1001");
        System.out.println(order.id());
    }
}
~~~

### 9.3. Điều gì xảy ra khi build?

Khi chạy:

~~~bash
./gradlew :orders-app:build
~~~

Gradle xử lý dependency giữa hai project và task graph để tạo output cần thiết. Trong quá trình compile, module descriptors được compiler xử lý; nếu module path inference được bật và dependency là modular component phù hợp, Gradle cấu hình compiler invocation để sử dụng module path theo mô hình Java plugin.

JPMS kiểm tra:

- App yêu cầu module name có tồn tại trên module path hay không.
- Domain có export package `com.example.orders.api` hay không.
- Class `Order` có public và nằm trong package được export hay không.
- Module descriptors có hợp lệ không.

Nếu build thành công, Gradle tạo output/artifact cho hai project. Việc Gradle build project dependency thành công và việc JPMS kiểm tra module descriptor là hai phần khác nhau của cùng quy trình.

## 10. Điều gì xảy ra nếu chỉ cấu hình một trong hai hệ thống?

### Trường hợp A: Có Gradle dependency nhưng thiếu `requires`

Ví dụ:

~~~groovy
dependencies {
    implementation project(':orders-domain')
}
~~~

Nhưng app module descriptor không có:

~~~java
requires com.example.orders.domain;
~~~

Gradle vẫn biết app phụ thuộc project domain. Tuy nhiên, named module app không khai báo readability tới domain. Khi source app import type từ domain, compiler có thể báo package không được khai báo trong module hoặc module không đọc được package đó, tùy cách module path được cấu hình.

Cần bổ sung chỉ thị JPMS đúng module name nếu app thực sự sử dụng API của domain như một named module.

### Trường hợp B: Có `requires` nhưng thiếu Gradle dependency

Module descriptor có:

~~~java
module com.example.orders.app {
    requires com.example.orders.domain;
}
~~~

Nhưng Gradle không đưa artifact/project domain lên module path và không có repository dependency phù hợp.

Compiler không thể resolve module name `com.example.orders.domain`. Chỉ thị `requires` không tải JAR, không thêm project vào Gradle build và không cấu hình repository.

Cần khai báo dependency trong build logic để Gradle cung cấp module tương ứng cho compile/runtime.

### Trường hợp C: Module có descriptor nhưng dependency nằm trên classpath

Một named module không thể dùng `requires` để đọc một module chỉ được đặt trên classpath như unnamed module. Nếu dependency không được đưa lên module path, compiler có thể không tìm thấy module name.

Hãy kiểm tra module path inference hoặc compiler arguments thay vì chỉ xác nhận file JAR đã được tải về.

### Trường hợp D: Module được resolve nhưng package không export

Giả sử domain có:

~~~java
module com.example.orders.domain {
    // Không export package api
}
~~~

App có:

~~~java
module com.example.orders.app {
    requires com.example.orders.domain;
}
~~~

App đọc được module domain nhưng không được truy cập package không export. Readability và accessibility là hai điều kiện riêng. Thêm `requires` không tự làm mọi package trở thành API công khai.

Domain cần export package phù hợp nếu đó là API intended for consumers.

## 11. Classpath, automatic modules và quá trình chuyển đổi dần sang JPMS

Không phải mọi dependency Java đều đã có explicit module descriptor. Một dự án hiện đại có thể trộn:

- Explicit named modules có `module-info.class`.
- Automatic modules từ JAR chưa modular hóa.
- Các dependency chỉ được sử dụng trên classpath.
- Module của JDK.

Khi một JAR không có descriptor được đặt trên module path, Java có thể coi nó là automatic module. Tên automatic module có thể đến từ manifest `Automatic-Module-Name` hoặc được suy ra từ tên JAR.

Điều này giúp thư viện cũ tham gia module graph, nhưng không cung cấp encapsulation chặt như explicit module. Các package của automatic module thường được export rộng và dependency readability rộng hơn.

### 11.1. Chuyển tiếp từ classpath sang module path

Một lộ trình có thể gồm:

1. Kiểm kê dependency và module name của từng JAR.
2. Ưu tiên thư viện đã có explicit module descriptor.
3. Với thư viện chưa modular hóa, kiểm tra `Automatic-Module-Name` hoặc tên automatic module được suy ra.
4. Đưa dependency lên module path trong một bước có kiểm soát.
5. Tạo `module-info.java` cho project.
6. Khai báo `requires` tối thiểu và `exports` đúng API.
7. Xử lý reflection bằng `opens` có phạm vi hẹp.
8. Kiểm tra compile, test và runtime trong module mode.
9. Giảm dần các tùy chọn mở rộng như `--add-reads` hoặc `--add-opens` khi module descriptor đã đầy đủ.

Không nên chuyển toàn bộ dependency cùng lúc nếu ứng dụng có nhiều thư viện cũ, framework reflection hoặc split package. Thực hiện theo từng nhóm giúp dễ xác định module nào gây lỗi.

### 11.2. `--add-reads`, `--add-exports` và `--add-opens`

Java launcher/compiler có một số tùy chọn để điều chỉnh ranh giới module trong các tình huống tương thích:

- `--add-reads`: bổ sung quan hệ readability.
- `--add-exports`: mở một package cho module đích như exported API.
- `--add-opens`: mở package cho deep reflection.

Ví dụ minh họa:

~~~bash
java --add-opens com.example.orders.domain/com.example.orders.internal=org.example.framework --module-path mods --module com.example.orders.app/com.example.orders.app.Main
~~~

Các tùy chọn này hữu ích để xử lý framework cũ hoặc chuyển đổi từng bước, nhưng chúng có thể làm giảm tính rõ ràng của module descriptor nếu được dùng lâu dài. Hãy ghi rõ lý do và giới hạn module nhận quyền truy cập.

## 12. Test trong dự án JPMS

Test có thể tạo ra một số khác biệt so với application runtime:

- Test source set có dependency riêng.
- Framework test có thể cần reflection vào package nội bộ.
- Test task có thể chạy theo classpath hoặc module path tùy cấu hình và phiên bản Gradle/plugin.
- Một test có thể cần mở package bằng `opens` hoặc `--add-opens`.
- Test code không nhất thiết được đóng gói cùng application artifact.

Nếu JUnit hoặc framework khác cần truy cập package của named module bằng reflection, có thể phải cấu hình module descriptor hoặc JVM arguments phù hợp. Không nên mở toàn bộ module cho mọi consumer chỉ để làm test chạy; có thể dùng test-specific configuration khi phù hợp.

Khi test fail trong modular build, hãy phân biệt lỗi:

- Gradle không resolve dependency.
- Compiler không tìm thấy module.
- JPMS từ chối readability hoặc package access.
- Reflection bị chặn ở runtime.
- Test framework không chạy đúng với module mode.

Mỗi loại lỗi thuộc một lớp khác nhau và cần kiểm tra đúng log/compiler arguments.

## 13. Cách kiểm tra module name và module descriptor

Một số công cụ JDK hữu ích:

### 13.1. Kiểm tra module trong JAR

~~~bash
jar --describe-module --file build/libs/orders-domain-1.0.0.jar
~~~

Lệnh này hiển thị module descriptor hoặc thông tin automatic module mà công cụ `jar` nhận diện được.

### 13.2. Liệt kê nội dung JAR

~~~bash
jar tf build/libs/orders-domain-1.0.0.jar
~~~

Tìm `module-info.class` để xác định JAR có explicit module descriptor. Nếu không có, kiểm tra manifest xem có `Automatic-Module-Name` hay không.

### 13.3. Xem module graph khi chạy

Có thể dùng tùy chọn chẩn đoán của Java launcher như `--show-module-resolution` để quan sát module được resolve:

~~~bash
java --show-module-resolution --module-path mods --module com.example.orders.app/com.example.orders.app.Main
~~~

### 13.4. Kiểm tra compiler arguments

Khi cần xác định Gradle đang dùng classpath hay module path, bật log phù hợp hoặc kiểm tra compiler invocation/arguments của task compile. Điều quan trọng là xem đường dẫn được truyền dưới `--class-path` hay `--module-path`, và dependency có thực sự xuất hiện trong module path hay không.

Không nên chỉ nhìn vào cấu trúc thư mục `build/classes` hoặc việc JAR đã tồn tại để kết luận JPMS đã được áp dụng đúng.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Gradle subproject là một JPMS module | Subproject là đơn vị build; nó chỉ là JPMS module khi artifact/source được cấu hình theo module system |
| Tên project là tên JPMS module | Module name lấy từ descriptor hoặc quy tắc automatic module |
| `implementation project(':domain')` thay cho `requires` | Một bên khai báo build dependency, bên kia khai báo readability |
| `requires` tự tải dependency | JPMS không thay thế Gradle repository/dependency resolution |
| `api` tương đương `exports` | `api` điều khiển publication/compile contract; `exports` công khai package ở JPMS |
| `implementation` tương đương `requires` | Hai chỉ thị thuộc hai mô hình khác nhau |
| Có JAR trên classpath là named module | JAR trên classpath thuộc unnamed module; module path mới resolve named/automatic modules |
| `requires` cho phép truy cập mọi package | Module còn phải export package phù hợp |
| `exports` cho phép mọi framework reflection | Deep reflection thường cần `opens` hoặc quyền tương ứng |
| Automatic module giống explicit module | Automatic module là cầu nối tương thích, có quy tắc encapsulation khác |
| Một repository phải có cùng số Gradle project và JPMS module | Không có quan hệ một-một bắt buộc |
| Bật module path là đủ để module build đúng | Cần module name, dependency, descriptor và package access khớp nhau |

## 15. Quy trình thiết kế ranh giới Gradle và JPMS

Khi bắt đầu modular hóa một ứng dụng, nên quyết định riêng hai câu hỏi.

**Ở cấp build tool:**

- Project nào cần tách riêng?
- Project nào tạo artifact độc lập?
- Dependency giữa project được khai báo ra sao?
- Plugin và source set nào được sử dụng?
- Configuration nào cung cấp compile/runtime dependencies?
- Artifact được đóng gói và publish như thế nào?

**Ở cấp JPMS:**

- Module nào cần có tên riêng?
- Module name ổn định là gì?
- Module nào cần `requires` module nào?
- Package nào là public API và cần `exports`?
- Package nào chỉ cần mở cho reflection?
- Có automatic module hoặc dependency classpath cũ nào cần chuyển tiếp?
- Runtime module graph có resolve được không?

Sau đó nối hai mô hình:

1. Khai báo Gradle project/module dependency để build cung cấp đúng component.
2. Đặt module descriptor vào source set phù hợp.
3. Đảm bảo module name trong `requires` trùng với tên module thực tế của dependency.
4. Bật/cấu hình module path inference hoặc compiler arguments phù hợp.
5. Kiểm tra compile task.
6. Kiểm tra test task và nhu cầu reflection.
7. Kiểm tra runtime module resolution.
8. Kiểm tra artifact được tạo có descriptor và nội dung đúng.

## 16. Checklist phân biệt hai ranh giới

Khi đọc một dự án Java có nhiều “module”, hãy xác định:

- [ ] Đây là Gradle project path, Maven artifact hay JPMS module name?
- [ ] Subproject được khai báo trong `settings.gradle` nào?
- [ ] Dependency build được khai báo trong configuration nào?
- [ ] Project/artifact có `module-info.java` hoặc automatic module name không?
- [ ] Module name thực tế là gì?
- [ ] Consumer có dependency Gradle cần thiết để lấy artifact không?
- [ ] Consumer có `requires` đúng tên JPMS module không?
- [ ] Dependency được đưa lên module path hay classpath?
- [ ] Package cần sử dụng đã được export chưa?
- [ ] Framework có cần package mở cho reflection không?
- [ ] Gradle module path inference và phiên bản toolchain đã được xác định chưa?
- [ ] Test và runtime đều chạy được với module graph dự kiến?

## Kết luận

Gradle project và JPMS module là hai ranh giới độc lập nhưng có thể phối hợp trong cùng một dự án Java. Gradle quản lý cấu trúc build, dependency configurations, task graph và artifact. JPMS quản lý module name, readability, exports, opens và module graph ở compile/runtime.

Một Gradle project không tự động trở thành JPMS module; tên project cũng không quyết định tên module. Dependency declaration của Gradle không thay thế `requires`, còn `requires` không thay thế việc cung cấp dependency trên classpath hoặc module path. Khi khai báo đúng cả hai phía, Gradle có thể cung cấp đúng artifact cho compiler/runtime và JPMS có thể áp dụng ranh giới truy cập rõ ràng giữa các phần của ứng dụng.
