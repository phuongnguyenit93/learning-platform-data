# Reactor thu thập, sắp xếp và build các mô-đun trong Maven

## 1. Tổng quan: Reactor là cơ chế điều phối build nhiều module

Khi một dự án Maven gồm nhiều mô-đun (module), mỗi mô-đun có `pom.xml` riêng và có thể phụ thuộc vào một mô-đun khác, việc chạy lệnh build lần lượt từng thư mục bằng tay vừa mất thời gian vừa dễ sai thứ tự. **Maven Reactor** là cơ chế trong Maven Core giúp Maven:

1. **Thu thập (collect)** các dự án/mô-đun tham gia phiên build.
2. **Sắp xếp (sort)** chúng theo các mối quan hệ cần được xây dựng trước.
3. **Chọn phạm vi build (select)** nếu có các tùy chọn CLI như `-pl`, `-am`.
4. **Thực thi (build)** lifecycle/goals lên các dự án đã chọn theo thứ tự hợp lệ.

Với Maven 3, tài liệu thường mô tả ngắn gọn Reactor theo ba công việc: collect, sort, build. Tài liệu Maven 4 tách riêng bước chọn subproject để diễn đạt rõ các trường hợp chọn một phần reactor. Trong cả hai, ý tưởng quan trọng là **build graph** chứ không phải “Maven chạy từng module theo thứ tự tên thư mục”.

Sơ đồ:

~~~text
Aggregator POM: <modules>
      |
      v
[COLLECT]
  đọc POM và danh sách modules
  nhận diện các dự án thành viên
      |
      v
[SORT]
  phân tích quan hệ module -> dependency/plugin/extension
  lập thứ tự phù hợp các ràng buộc
      |
      v
[SELECT]
  toàn reactor hoặc chọn -pl, -am, -amd, -rf...
      |
      v
[BUILD]
  chạy phase/goals cho các dự án được chọn
  ghi Reactor Summary và trạng thái
~~~

**Reactor không phải một plugin tùy chọn phải tải riêng.** Nó là chức năng Maven Core khi thực thi multi-module build. Đừng nhầm nó với một plugin cũ hoặc `maven-dependency-plugin`.

Sau bài học, bạn có thể đọc POM, dự đoán các ràng buộc build order, phân biệt aggregation/inheritance/dependency, tạo project nhiều module Java 17 chạy được, dùng reactor CLI để build từng phần và chẩn đoán lỗi vòng phụ thuộc hoặc dependency không được resolve.

## 2. Thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Có tự tạo quan hệ build order không? |
| --- | --- | --- |
| **Maven project** | Đơn vị có POM và Maven coordinates | Là node trong build graph nếu được thu thập |
| **Module/subproject** | Dự án con được aggregator liệt kê | Tham gia reactor khi được collect |
| **Aggregator** | POM liệt kê các module trong `<modules>` (Maven 3) | Tạo phạm vi collect, không tự khai báo mọi quan hệ dependency |
| **Parent POM** | POM được child khai báo trong `<parent>` để kế thừa config | Là quan hệ inheritance; thường xuất hiện trong reactor nếu được collect |
| **Project dependency** | Khai báo `<dependency>` tới artifact khác | Nếu dependency cũng là module trong reactor, là ràng buộc sort |
| **Dependency management** | Quản lý version/scope của dependencies | **Không** tự tạo project dependency hay sort edge |
| **Plugin declaration** | Plugin được thực sự dùng trong `<build><plugins>` | Có thể tạo sort edge nếu plugin cũng được build trong reactor |
| **Plugin management** | Quản lý plugin version/config | **Không** tự tạo sort edge |
| **Build extension** | Artifact extension tham gia build | Có thể tạo sort edge nếu là module trong reactor |
| **Lifecycle** | Chuỗi phases như compile, test, package, verify | Chạy cho từng module sau khi reactor sắp xếp |
| **JPMS Java module** | `module-info.java` của Java Platform Module System | **Không đồng nghĩa** Maven module trong `<modules>` |

**Một Maven module không cần có `module-info.java`.** Ví dụ dự án Java 17 trong bài là multi-module Maven nhưng không sử dụng JPMS. Ngược lại, một project Maven đơn lẻ có thể chứa một Java module JPMS.

Các từ *upstream* và *downstream* cũng hữu ích:

- Nếu `runner` phụ thuộc `greeter`, thì `greeter` là **upstream dependency** của `runner`.
- `runner` là **downstream dependent** của `greeter`.
- Build order cần thỏa `greeter` hoàn thành các bước cần thiết trước khi `runner` sử dụng nó.

## 3. Aggregation khác inheritance và dependency

Ba mối quan hệ này thường xuất hiện cùng lúc nhưng **không thay thế nhau**.

### 3.1. Aggregation: liệt kê các module

Một POM tổng hợp điển hình:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>api</module>
    <module>service</module>
    <module>web</module>
</modules>
~~~

Những giá trị `api`, `service`, `web` là **đường dẫn tương đối tới module/POM**, không phải `artifactId` bắt buộc trùng tên. Reactor đọc các POM ở các đường dẫn đó để thu thập project.

`packaging=pom` là kiểu phù hợp cho aggregator/parent không tạo JAR ứng dụng riêng. Một folder chỉ chứa subfolder nhưng **không được aggregator liệt kê** thì không vì thế tự tham gia Maven 3 reactor.

### 3.2. Inheritance: kế thừa từ parent

Child POM có thể khai báo:

~~~xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>root-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Child nhận config/properties/pluginManagement phù hợp từ parent theo quy tắc POM inheritance. **Dòng `<parent>` không tự biến child thành module được aggregator collect**. Để chạy mọi child từ root với Maven 3, root vẫn cần khai báo `<modules>` phù hợp.

### 3.3. Dependency: mã mô-đun này dùng artifact mô-đun khác

Ví dụ `service` dùng class từ `api`:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>api</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Đây là ràng buộc project dependency. Khi `api` và `service` đều được thu thập vào cùng reactor, Maven có thể **build `api` trước `service`** và sử dụng artifact ở reactor ngay trong phiên build.

**Chỉ vì hai child cùng parent không có nghĩa một child tự phụ thuộc child kia.** Nếu code import class từ sibling, phải khai báo dependency phù hợp. Parent config chỉ chia sẻ cấu hình.

### 3.4. Ví dụ phân biệt nhanh

~~~text
root/pom.xml
    ├── modules: api, service
    └── đóng vai trò parent cho cả api và service

api/pom.xml
    └── parent: root

service/pom.xml
    ├── parent: root
    └── dependency: api
~~~

- `modules` làm **api/service** được thu thập khi build root.
- `parent` làm chúng nhận chung Java release/version/plugin config.
- `dependency: api` buộc **api trước service** khi Reactor sorting.

Nếu bỏ `dependency: api` khỏi `service` nhưng Java source vẫn import API class, compiler sẽ không tìm thấy class, dù hai module cùng nằm trong `<modules>`.

## 4. Reactor thu thập module thế nào trong Maven 3?

Khi đứng tại root có `pom.xml`:

~~~bash
mvn -B clean verify
~~~

Maven 3 đọc project POM khởi đầu, phân tích các `<module>` bên trong `<modules>`, rồi **đệ quy collect** những module được khai báo bởi các aggregator con. Khi các profiles đang active có thêm `<modules>`, danh sách thu thập cũng chịu ảnh hưởng của profile.

Ví dụ cấu trúc:

~~~text
root/
├── pom.xml               # modules: platform, applications
├── platform/
│   ├── pom.xml           # modules: core, utilities
│   ├── core/pom.xml
│   └── utilities/pom.xml
└── applications/
    ├── pom.xml           # modules: server, cli
    ├── server/pom.xml
    └── cli/pom.xml
~~~

Reactor có thể chứa aggregator root, platform, applications và các module descendants tương ứng. **Maven không quét toàn bộ subfolders để “đoán” module nào cần build**. Chỉ những project được liên kết qua cấu hình multi-module hợp lệ mới được collect.

Các điều kiện phải đúng:

- Mỗi `<module>` dẫn tới POM tồn tại, đọc được và có XML hợp lệ.
- Module path thường tương đối với aggregator POM chứa `<modules>`, không phụ thuộc tùy ý vào shell cwd.
- Các POM phải có GAV/parent resolution hợp lệ.
- Project không xuất hiện trùng một cách gây lỗi trong cùng reactor.
- Các profiles cần thiết đã được active.
- Chạy từ đúng aggregator root hoặc dùng `-f` trỏ đúng POM.

**Nếu một folder có POM nhưng không được liệt kê**, build từ root Maven 3 không tự build nó. Nếu module được liệt kê nhưng POM không tồn tại, Maven sẽ báo lỗi ở giai đoạn đọc/collect project, chưa tới Java compile.

### 4.1. Chọn file POM từ vị trí khác

Ở thư mục cha của root:

~~~bash
mvn -f reactor-lab/pom.xml -B clean verify
~~~

Maven dùng POM được chỉ định bởi `-f`, không đòi người dùng đứng trong đúng root khi chạy. Lệnh `-f` không có nghĩa Maven tự tìm ra mọi folder project trên filesystem.

### 4.2. Non-recursive

~~~bash
mvn -N validate
~~~

`-N` (`--non-recursive`) yêu cầu không thực thi xuống các child modules như một reactor build thông thường; rất hữu ích để xác minh POM aggregator riêng. Nếu chỉ chạy parent `packaging=pom`, đừng mong các module Java con được compile.

Lưu ý: Maven CLI có thể thay đổi chi tiết của project discovery giữa các major versions; các ví dụ thực hành sau được thiết kế chủ yếu cho **Maven 3.9.x**.

## 5. Reactor sorting là sắp xếp topo của đồ thị phụ thuộc

Hãy xem các modules như **đỉnh** trong một đồ thị có hướng.

Nếu `service` cần artifact của `core`, ta có ràng buộc:

~~~text
core -----> service
  \           |
   \          v
    -------> cli
~~~

Mũi tên ở đây có nghĩa **module bên trái phải được build trước module bên phải**, không phải chiều mà developer viết import trong Java.

Bài toán của Reactor là tìm một thứ tự topo (topological order) thỏa tất cả các ràng buộc có thật. Với đồ thị không có chu trình, có thể có **nhiều thứ tự hợp lệ**: hai module độc lập có thể đổi vị trí mà không sai.

### 5.1. Những quan hệ dùng để sort

Tài liệu Maven 3 về Reactor Sorting liệt kê:

1. Một project có **dependency** tới một module khác trong reactor.
2. Một module **khai báo plugin thực tế** mà plugin ấy là module khác trong reactor.
3. Một plugin có **dependency** tới module khác trong reactor.
4. Một **build extension** tham chiếu module khác trong reactor.
5. Nếu không có ràng buộc nào quyết định, sử dụng **thứ tự `<modules>`** làm tie-breaker.

**Cực kỳ quan trọng:** chỉ những tham chiếu đã được **instantiated/thực sự khai báo như dependency hoặc plugin/extension** mới tác động sorting. Các entry chỉ nằm trong `<dependencyManagement>` hoặc `<pluginManagement>` **không tạo sort edge**.

Đừng dùng một `dependencyManagement` entry để buộc Maven build một sibling trước. Nếu một project thực sự cần artifact của sibling, nó phải có direct/appropriate actual dependency hoặc một quan hệ build thật.

### 5.2. `<modules>` order không phải thứ tự buộc build

Giả sử root khai báo:

~~~xml
<modules>
    <module>runner</module>
    <module>greeter</module>
    <module>report</module>
    <module>math-core</module>
</modules>
~~~

Dù `runner` đứng đầu trong XML, nếu `runner` phụ thuộc `greeter`/`report`, còn hai module ấy phụ thuộc `math-core`, Maven **không build runner trước**. Reactor ưu tiên quan hệ dependency thực tế và sẽ sắp module upstream trước module downstream.

Nếu hai module **không có quan hệ trực tiếp/gián tiếp** với nhau, thứ tự liệt kê trong `<modules>` thường được dùng khi cần thứ tự mặc định; với parallel build, chúng có thể chạy đồng thời. Vì vậy không dùng module listing để thay thế dependency graph.

## 6. Demo Java 17 hoàn chỉnh: bốn module có đồ thị khác thứ tự khai báo

Bài thực hành tạo bốn module JAR và một aggregator/parent POM:

- `math-core`: tính tổng hai số.
- `greeter`: phụ thuộc `math-core`, tạo lời chào.
- `report`: phụ thuộc `math-core`, tạo chuỗi báo cáo.
- `runner`: phụ thuộc cả `greeter` và `report`, có `main` và JUnit 5 test.

Root cố tình liệt kê `runner` đầu tiên để minh họa Reactor sorting không mù quáng theo thứ tự XML.

### 6.1. Cấu trúc project

~~~text
reactor-lab/
├── pom.xml
├── math-core/
│   ├── pom.xml
│   └── src/main/java/com/example/reactor/core/Numbers.java
├── greeter/
│   ├── pom.xml
│   └── src/main/java/com/example/reactor/greeter/Greeter.java
├── report/
│   ├── pom.xml
│   └── src/main/java/com/example/reactor/report/Report.java
└── runner/
    ├── pom.xml
    ├── src/main/java/com/example/reactor/runner/Main.java
    └── src/test/java/com/example/reactor/runner/MainTest.java
~~~

Các module dùng chung `groupId=com.example.reactor` và version `1.0.0`; root artifactId là `reactor-lab`. **Tên folder không phải Maven coordinates**. Đồ thị:

~~~text
reactor-lab (pom aggregator/parent)
     |
     +----> math-core
                 |
        +--------+--------+
        v                 v
     greeter            report
        |                 |
        +--------+--------+
                 v
               runner
~~~

Đây là một **DAG** (directed acyclic graph). Không có dependency từ `math-core` quay về `runner`, nên Maven có thể tìm được topo order.

### 6.2. Root pom.xml — vừa aggregator vừa parent

Tạo `reactor-lab/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.reactor</groupId>
    <artifactId>reactor-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>runner</module>
        <module>greeter</module>
        <module>report</module>
        <module>math-core</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

**Đọc root POM theo ba vai trò:**

- `<packaging>pom</packaging>`: root không tạo JAR chứa ứng dụng của cả hệ thống.
- `<modules>`: root liệt kê bốn module sẽ được collect.
- `<properties>` và `<pluginManagement>`: root đóng vai trò parent để các child kế thừa Java release và quản lý plugin versions.

**Đặc biệt:** `<pluginManagement>` là cấu hình quản lý plugin; nó **không** tự tạo một dependency giữa `math-core`/`greeter`/`report`/`runner`. Sort order của demo đến từ `<dependencies>` trong child POM, không phải từ danh sách phiên bản Compiler/Surefire/JAR Plugin.

Đoạn này dùng Maven POM model `4.0.0`, phù hợp với Maven 3.9.x và tương thích với Maven 4 ở chế độ POM cũ.

### 6.3. math-core/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.reactor</groupId>
        <artifactId>reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>math-core</artifactId>
    <packaging>jar</packaging>
</project>
~~~

`math-core` **không có dependency tới sibling nào**. Nó kế thừa `groupId`, `version`, Java release và pluginManagement từ parent.

### 6.4. math-core/Numbers.java

Tạo `math-core/src/main/java/com/example/reactor/core/Numbers.java`:

~~~java
package com.example.reactor.core;

public final class Numbers {

    private Numbers() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }
}
~~~

Code dùng `Math.addExact` của Java chuẩn, không cần external runtime dependencies. Nếu tổng tràn `int`, method ném `ArithmeticException`; trong demo dùng các số nhỏ nên kết quả xác định.

### 6.5. greeter/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.reactor</groupId>
        <artifactId>reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeter</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.reactor</groupId>
            <artifactId>math-core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Dependency được khai báo bằng **đúng Maven coordinates** `com.example.reactor:math-core:1.0.0`. Nếu code dùng `Numbers` từ module core nhưng POM không có dependency này, việc cùng nằm trong reactor không tự thêm classpath.

### 6.6. greeter/Greeter.java

Tạo `greeter/src/main/java/com/example/reactor/greeter/Greeter.java`:

~~~java
package com.example.reactor.greeter;

import com.example.reactor.core.Numbers;

public final class Greeter {

    private Greeter() {
    }

    public static String message() {
        return "Greeter sum=" + Numbers.add(2, 3);
    }
}
~~~

Module `greeter` compile thành class gọi `Numbers.add` từ artifact `math-core`. Reactor phải cung cấp đúng upstream artifact khi compile `greeter`.

### 6.7. report/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.reactor</groupId>
        <artifactId>reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>report</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.reactor</groupId>
            <artifactId>math-core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

`report` và `greeter` **không phụ thuộc trực tiếp nhau**; cả hai chỉ phụ thuộc `math-core`. Đây là cơ hội để Reactor chạy song song nếu dùng parallel build hợp lệ.

### 6.8. report/Report.java

Tạo `report/src/main/java/com/example/reactor/report/Report.java`:

~~~java
package com.example.reactor.report;

import com.example.reactor.core.Numbers;

public final class Report {

    private Report() {
    }

    public static String summary() {
        return "Report sum=" + Numbers.add(4, 6);
    }
}
~~~

### 6.9. runner/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.reactor</groupId>
        <artifactId>reactor-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>runner</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.reactor</groupId>
            <artifactId>greeter</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>com.example.reactor</groupId>
            <artifactId>report</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**Giải thích:**

- `runner` dùng artifact của `greeter` và `report`, nên cần hai dependencies tương ứng.
- `greeter` và `report` transitively kéo `math-core` vào runtime/test classpath theo quy tắc Maven của dependencies mặc định `compile`.
- JUnit chỉ có scope `test`, không đóng gói vào `runner` JAR.
- Các coordinates của sibling đều cùng `1.0.0` như reactor.
- Dự án root dùng `pluginManagement` để pin Surefire 3.5.2, hỗ trợ chạy JUnit Jupiter trong phase `test`.
- Việc `runner` nằm **đầu danh sách `<modules>`** ở root không khiến Maven compile runner đầu tiên.

**Chú ý dòng `xsi:schemaLocation`:** cần dùng cặp namespace và URL schema Maven chuẩn. Khi tự sao chép dự án mẫu, bạn có thể chuẩn hóa nó như các POM khác trong bài:

~~~xml
xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd"
~~~

Dòng URL schema dùng để XML tooling/IDE nhận diện schema; reactor sorting dựa trên POM model và dependencies, không dựa thứ tự của attribute này.

### 6.10. runner/Main.java

Tạo `runner/src/main/java/com/example/reactor/runner/Main.java`:

~~~java
package com.example.reactor.runner;

import com.example.reactor.greeter.Greeter;
import com.example.reactor.report.Report;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.message());
        System.out.println(Report.summary());
    }
}
~~~

`Main` không import `math-core` trực tiếp nhưng sẽ cần class của core khi gọi phương thức từ hai module upstream. Đây là lý do runtime classpath phải bao gồm cả dependency transitively cần thiết.

### 6.11. runner/MainTest.java

Tạo `runner/src/test/java/com/example/reactor/runner/MainTest.java`:

~~~java
package com.example.reactor.runner;

import org.junit.jupiter.api.Test;

import com.example.reactor.greeter.Greeter;
import com.example.reactor.report.Report;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {

    @Test
    void combinesResultsFromOtherModules() {
        assertEquals("Greeter sum=5", Greeter.message());
        assertEquals("Report sum=10", Report.summary());
    }
}
~~~

Đây là **một JUnit 5 test method** nằm ở `runner`; các module còn lại không có tests trong demo. Test sẽ chạy bằng Maven Surefire khi reactor thực thi phase `test` cho runner.

## 7. Bản đồ dependency của demo và thứ tự build

Các quan hệ thực tế:

~~~text
math-core -> greeter
math-core -> report
greeter   -> runner
report    -> runner
~~~

Do đó một thứ tự **hợp lệ** của các module Java là:

~~~text
math-core
greeter
report
runner
~~~

Hoặc:

~~~text
math-core
report
greeter
runner
~~~

Vì `greeter` và `report` độc lập lẫn nhau, hai thứ tự đều đúng về mặt dependency. Maven 3 có quy tắc tie-breaker theo khai báo `<modules>` khi không có edge khác, nên với lệnh build tuần tự thường sẽ thấy `greeter` trước `report` theo thứ tự POM minh họa. Tuy nhiên **không viết CI dựa trên log timestamp/order của hai module độc lập**, đặc biệt khi `-T` được bật.

Aggregator `reactor-lab` có `packaging=pom` thường xuất hiện trước các child vì chúng khai báo POM này làm parent; do đó **Reactor Build Order** điển hình có năm mục:

~~~text
reactor-lab
math-core
greeter
report
runner
~~~

Không cần dựa vào tên folder theo alphabet; điều kiện bất biến là **math-core trước greeter/report, và cả greeter/report trước runner**.

### Chứng minh bằng thay đổi thứ tự XML

Nếu root chuyển `<modules>` thành:

~~~xml
<modules>
    <module>runner</module>
    <module>report</module>
    <module>greeter</module>
    <module>math-core</module>
</modules>
~~~

thì Reactor vẫn phải bảo đảm upstream trước downstream. Việc đổi thứ tự `report` và `greeter` có thể đổi tie-breaker giữa chúng, nhưng **không thể hợp lệ hóa runner build trước math-core**.

Không nên sửa POM production chỉ để ép một class phụ thuộc sai thứ tự được compile. Nếu relationship là thật, **khai báo đúng `<dependency>`** mới là cách giải quyết.

## 8. Chạy demo: `mvn clean verify`

Từ thư mục `reactor-lab/`:

~~~bash
mvn -version
java -version
mvn -B clean verify
~~~

**Điều kiện:** Maven 3.9.x, JDK 17+ và truy cập repository để resolve các plugin/JUnit khi cache chưa có.

Maven sẽ:

1. Đọc root aggregator và các POM child.
2. Thu thập năm project: `reactor-lab`, `math-core`, `greeter`, `report`, `runner`.
3. Dựng dependency graph từ GAV trong child POMs.
4. Sắp thứ tự thỏa dependencies.
5. Thực thi clean lifecycle và default lifecycle đến verify cho mỗi project được chọn theo reactor execution plan.
6. Compile `math-core`; các module downstream dùng artifact upstream trong reactor.
7. Chạy JUnit test ở runner khi tới phase `test`.
8. Đóng gói các module JAR khi tới `package`.
9. In **Reactor Summary** với thành công/thất bại của từng project.

Các output JAR dự kiến:

~~~text
math-core/target/math-core-1.0.0.jar
greeter/target/greeter-1.0.0.jar
report/target/report-1.0.0.jar
runner/target/runner-1.0.0.jar
~~~

Root POM **không** tạo `reactor-lab-1.0.0.jar`, vì `packaging=pom`. Reactor Summary có thể chứa thời gian chạy khác nhau và thông báo plugin/JUnit khác nhau, vì vậy **không khẳng định toàn bộ Maven stdout là một chuỗi cố định**.

### 8.1. Chạy Main từ các compiled module classes

Ví dụ POSIX/Linux/macOS, vẫn đứng tại thư mục `reactor-lab`:

~~~bash
java -cp "runner/target/classes:greeter/target/classes:report/target/classes:math-core/target/classes" com.example.reactor.runner.Main
~~~

Trên Windows PowerShell:

~~~powershell
java -cp "runner\target\classes;greeter\target\classes;report\target\classes;math-core\target\classes" com.example.reactor.runner.Main
~~~

**Stdout chính xác từ chương trình Java**:

~~~text
Greeter sum=5
Report sum=10
~~~

Cả bốn module class directories đều được đưa vào `-cp`. Dù Main chỉ import Greeter/Report, hai class đó dùng MathCore `Numbers`, nên nếu bỏ `math-core/target/classes`, JVM có thể lỗi lúc gọi phương thức.

**Maven không tự tạo một executable Uber JAR từ toàn reactor.** Mỗi module tạo JAR riêng. `java -jar runner/target/runner-1.0.0.jar` không tự làm việc trong demo này: chưa có `Main-Class` manifest và runtime dependencies cũng chưa được bundle. Nếu muốn một-file executable, phải chọn cơ chế packaging riêng như Maven Shade/Assembly hoặc build distribution có `lib/`.

### 8.2. Chứng minh bằng Reactor Summary

Trong Maven output, tìm phần tương đương:

~~~text
Reactor Summary for reactor-lab 1.0.0:
  reactor-lab .... SUCCESS
  math-core ...... SUCCESS
  greeter ........ SUCCESS
  report ......... SUCCESS
  runner ......... SUCCESS
~~~

Đây chỉ là **sơ đồ các status cần thấy**, không phải nguyên văn stdout Maven: Maven có prefix `[INFO]`, tên project và duration thay đổi theo version/concurrency.

Nếu một module fail và các dependent modules bị skip, Reactor Summary có thể hiển thị `FAILURE` và `SKIPPED` tương ứng. Đây là đầu mối tốt để tìm **module đầu tiên gây lỗi**, thay vì đọc một dòng lỗi cuối ở root.

## 9. Reactor build không đồng nghĩa `mvn install` từng module

Một ưu điểm lớn của Reactor: trong một **phiên multi-module build**, Maven có thể phân giải một sibling artifact đã được build trong reactor khi downstream module cần nó, **không bắt buộc chạy `mvn install` thủ công cho mọi sibling trước khi build tiếp**.

Ví dụ:

~~~bash
mvn -B clean verify
~~~

từ root có thể biên dịch `math-core`, `greeter`, `report`, `runner` trong một reactor, dù local Maven repository chưa có sẵn bộ GAV `com.example.reactor:*:1.0.0`.

**`verify` khác `install`:**

- `verify`: build và chạy các checks đến phase verify, tạo artifacts trong `target/` từng module.
- `install`: đi thêm phase install, lưu artifacts/POM vào **local Maven repository**.
- `deploy`: publish theo cấu hình tới remote repository.
- Reactor resolution: cho phép sử dụng artifacts **của module đang tham gia cùng phiên build**, không phải cứ có sibling folder là tự resolve bên ngoài reactor.

Với CI thường chỉ cần kiểm tra và đóng gói, `mvn clean verify` là lựa chọn tốt. Dùng `install` khi một công cụ/build riêng cần tìm artifact từ local repo hoặc workflow thực sự yêu cầu bước đó, chứ không dùng `install` như workaround mặc định cho dependency graph sai.

### 9.1. Khi build một module riêng thì sao?

Nếu đứng vào `runner/` và chạy:

~~~bash
mvn clean verify
~~~

trên Maven 3 mà không tham gia full reactor, Maven cần resolve `greeter`/`report` (và transitively `math-core`) từ **local/remote repositories**. Nếu những artifacts này chưa được install/publish đúng version, build có thể fail.

Trong Maven 3, để làm một bước build **có cả những upstream modules** từ root, dùng `-pl` và `-am`; cách làm được giới thiệu ở phần tiếp theo.

Maven 4 có cải tiến project root discovery và reactor-aware subproject builds; không suy luận chi tiết Maven 4 từ ví dụ `cd runner; mvn ...` dành cho Maven 3.

## 10. Chọn phần Reactor bằng `-pl`, `-am`, `-amd`

Thay vì build toàn bộ bốn module Java, có thể dùng các Maven CLI switches. Với ví dụ, chạy từ root.

### 10.1. `-pl`: chọn project

~~~bash
mvn -B -pl :runner verify
~~~

`-pl` là `--projects`, selector `:runner` chỉ artifactId `runner` trong reactor. Bạn cũng có thể dùng:

~~~bash
mvn -B -pl com.example.reactor:runner verify
~~~

hoặc đường dẫn module:

~~~bash
mvn -B -pl runner verify
~~~

**Chọn `runner` không tự buộc Maven 3 build tất cả dependencies của nó**. Nếu `greeter`/`report` chưa có trong repository local/remote, build chỉ với `-pl :runner` có thể thất bại. Khi muốn build upstream siblings trong reactor, hãy thêm `-am`.

### 10.2. `-am`: also-make upstream dependencies

~~~bash
mvn -B -pl :runner -am clean verify
~~~

Maven chọn `runner` và những **project dependencies cần thiết có trong reactor**. Trong demo, đó là `greeter`, `report`, `math-core` (và parent/aggregator cần thiết cho model).

Một cách hiểu:

~~~text
selected: runner
    |
    +-- needs greeter ---> needs math-core
    |
    +-- needs report ----> needs math-core
~~~

Maven sẽ sort sao cho upstream được build trước runner. `-am` **không thay việc khai báo dependency**: nó chỉ có thể tìm quan hệ đã có trong POM/build graph.

Nếu `runner` chỉ viết import từ `math-core` mà không có direct/transitive Maven dependency hợp lệ, `-am` không có phép thuật tự phát hiện `import com.example...` rồi thêm module. Maven làm việc dựa trên **metadata POM**, không tự suy luận graph từ Java source.

### 10.3. `-amd`: also-make-dependents downstream

~~~bash
mvn -B -pl :math-core -amd verify
~~~

`-amd` chọn các project trong reactor **phụ thuộc vào** `math-core`, trực tiếp hoặc gián tiếp. Trong demo, `greeter` và `report` dùng core, còn `runner` dùng hai module đó. Đây là một chiến lược hữu ích khi sửa core library và muốn test những consumers chịu tác động.

Cần phân biệt:

- `-am` kéo **dependencies (upstream)** của module được chọn.
- `-amd` kéo **dependents (downstream)** của module được chọn.

### 10.4. `-pl` có thể nhận danh sách

~~~bash
mvn -B -pl :greeter,:report verify
~~~

Dấu phẩy chọn hai artifacts. Nhưng vì cả hai cần `math-core`, nếu muốn build tất cả từ source trong cùng reactor, thêm:

~~~bash
mvn -B -pl :greeter,:report -am verify
~~~

**Không nhầm `:artifactId` với folder name**. Trong demo chúng giống nhau do thiết kế, nhưng một `<module>libraries/core</module>` có thể chứa `<artifactId>math-core</artifactId>` và khi đó selector `:math-core` không phải path `libraries/core`.

## 11. `-rf`: resume-from và bẫy khi dependencies chưa được install

Giả sử build thất bại ở module `runner` sau khi `math-core`, `greeter`, `report` đã build thành công. Maven 3 có thể gợi ý:

~~~bash
mvn -B -rf :runner verify
~~~

`-rf` tương ứng `--resume-from`: bắt đầu từ project được chọn trong reactor order thay vì build lại các project trước nó.

**Bẫy Maven 3:** build trước đó dùng `verify`, nên artifacts upstream có thể chỉ nằm ở `target/` chứ chưa được install vào local repo. Một lượt `-rf :runner verify` riêng có thể **không có upstream artifacts trong reactor mới** và cũng không tìm thấy chúng trong repository, dẫn tới lỗi resolve dependency.

Cách xử lý:

1. Với demo nhỏ, chạy lại **`mvn -B -pl :runner -am clean verify`** sau khi sửa lỗi.
2. Hoặc build full reactor `mvn -B clean verify`.
3. Nếu workflow bắt buộc resume trong Maven 3, hiểu rõ artifacts upstream đã được install/publish hay chưa.
4. Không dùng `-rf` để “sửa” bản thân dependency/version mismatch.
5. Đọc Reactor Summary để biết chính xác module nào fail trước khi chọn resume.

**Maven 4** cải thiện reactor-aware resume và hỗ trợ `--resume` (`-r`) cùng cách xử lý upstream khi tiếp tục. Không mặc định áp cùng semantics của `-r` ở Maven 4 cho mọi Maven 3 installation.

## 12. `-N`: chỉ xử lý POM bắt đầu

~~~bash
mvn -B -N validate
~~~

Đây là cách hữu ích khi muốn kiểm tra aggregator POM hoặc một goal chỉ dành cho root mà **không chạy các modules**.

Lưu ý:

- `-N` không biến một module Java thành independent artifact.
- `-N` không tự install sibling dependencies.
- `mvn -N clean verify` tại root `packaging=pom` không thể được hiểu như “đã build toàn bộ hệ thống”.
- Trong Maven 4, kết hợp `--non-recursive` với `--projects` có thể có semantics riêng về descendants; hãy đọc đúng tài liệu phiên bản.

Khi cần build một module và upstream, dùng `-pl :module -am` là mô hình rõ hơn việc cố dùng `-N` rồi chạy riêng từng folder.

## 13. Failure modes: `-ff`, `-fae`, `-fn`

Reactor có chính sách xử lý một module build thất bại:

| Cờ | Tên dài | Hành vi |
| --- | --- | --- |
| `-ff` | `--fail-fast` | Dừng khi gặp module failure; mặc định thường là fail-fast |
| `-fae` | `--fail-at-end` | Tiếp tục các module còn có thể build độc lập, tổng kết lỗi cuối reactor |
| `-fn` | `--fail-never` | Không dùng kết quả thất bại để trả exit status thất bại như bình thường |

Ví dụ:

~~~bash
mvn -B -fae clean verify
~~~

Nếu một module fail, các module **độc lập với module fail** vẫn có thể được thử build, còn dependent modules không thể build đúng vẫn có thể bị skip. `-fae` giúp thu thập nhiều lỗi trong một lượt CI, nhưng không có nghĩa Maven sẽ build bất chấp thiếu upstream.

~~~bash
mvn -B -ff clean verify
~~~

Giúp dừng sớm ở module lỗi đầu tiên.

~~~bash
mvn -B -fn clean verify
~~~

**Không khuyến nghị làm CI quality gate.** `--fail-never` có thể khiến Maven command exit status là 0 dù Reactor Summary/logs có failure; pipeline dựa vào exit code sẽ đánh dấu job xanh nhầm. Chỉ dùng trong các workflow chấp nhận kết quả thiếu, không để release/publish phụ thuộc vào nó.

### 13.1. Ví dụ failure graph

Nếu `math-core` fail compile:

~~~text
math-core  FAILURE
greeter    SKIPPED (cần math-core)
report     SKIPPED (cần math-core)
runner     SKIPPED (cần greeter + report)
~~~

Nếu chỉ `report` fail test, `greeter` có thể build được vì không phụ thuộc report; `runner` không nên được xây dựng thành công với một upstream bị fail.

**Reactor Summary không phải dấu hiệu bug khi downstream bị SKIPPED** — đó thường là phản ứng hợp lý để tránh dùng artifact chưa được xác minh.

## 14. Reactor parallel build với `-T`

Maven có thể chạy multi-module reactor song song khi graph cho phép:

~~~bash
mvn -B -T 2 clean verify
~~~

`-T 2` yêu cầu tối đa khoảng hai build threads cho phần xử lý parallel phù hợp. Một dạng khác:

~~~bash
mvn -B -T 1C clean verify
~~~

`1C` liên hệ với số lõi CPU theo cách Maven định nghĩa. **Không phải `-T` bắt mọi module chạy cùng lúc**.

Với demo:

~~~text
math-core
   |
   +--> greeter ---+
   |               +--> runner
   +--> report ----+
~~~

- `math-core` phải sẵn sàng trước `greeter` và `report`.
- `greeter` và `report` có thể chạy đồng thời nếu scheduler/threads cho phép.
- `runner` phải chờ cả hai upstream hoàn tất thành công.
- Logs giữa các modules có thể xen kẽ; dựa vào Reactor Summary và per-module reports để debug.

### 14.1. Parallel không tự bảo đảm build tools thread-safe

Nếu modules dùng custom Maven plugin, external generators, shared temp directories hoặc cùng một database test, chúng có thể ghi đè kết quả của nhau. Reactor graph biết **Maven project dependencies**, không tự nhìn thấy một file global như `/tmp/generated.json` mà hai modules cùng ghi.

Các nguyên tắc:

1. Dùng `${project.build.directory}` riêng cho output của từng module.
2. Không có hai module cùng ghi file global không có lock.
3. Kiểm tra các Maven goals/plugins có hỗ trợ thread-safe execution.
4. Khi cùng sử dụng shared integration test backend, có per-job namespace/data.
5. Không suy đoán test pass tuần tự sẽ pass song song.
6. Bắt đầu với `-T 2` và tăng theo đo đạc, không mặc định càng nhiều càng nhanh.
7. Với lỗi không tái hiện được, thử build tuần tự để phân biệt race với dependency metadata sai.

`-T` giúp tối ưu throughput khi graph có module độc lập, **không thay đổi cấu trúc dependency**.

## 15. Một phiên Reactor thực thi lifecycle ra sao?

Mỗi Maven project có model, packaging và plugin bindings riêng. Khi gọi:

~~~bash
mvn clean verify
~~~

Maven thực thi goals/phases trên các projects đã chọn theo reactor plan. Trong demo:

- Aggregator `reactor-lab` có `packaging=pom`, không biên dịch Java và không tạo app JAR.
- `math-core`, `greeter`, `report`, `runner` có `packaging=jar`, nên dùng compiler/test/jar defaults phù hợp.
- `runner` có JUnit 5 test và Surefire được pin version.
- PluginManagement trong parent quản lý versions nhưng không tự làm mọi plugin goal tùy ý chạy.
- Reactor thỏa prerequisite relationships trước khi build downstream ở thời điểm cần dùng artifacts.

**Reactor sorting không có nghĩa Maven chạy phase `compile` trên tất cả modules cùng lúc rồi phase `test` trên tất cả modules rồi phase `package` trên tất cả modules theo thứ tự global.** Với Maven 3 build tuần tự, Maven thường thực thi các phases được yêu cầu cho một project theo lifecycle trước khi chuyển sang project kế tiếp, trong phạm vi scheduler và aggregator/non-aggregator goals; với `-T`, những module độc lập có thể chạy đan xen.

Sự khác biệt này quan trọng với:
- Plugin truy cập `target/classes` của sibling khi sibling chưa có.
- Generated sources được truyền qua artifacts.
- Script thực hiện side effects khi đến phase package.
- CI logs hiển thị plugin goal của module khác nhau xen kẽ.

Nên **khai báo dependencies và lifecycle bindings**, không điều phối dựa trên “thấy module X in log trước module Y”.

## 16. Module path không phải artifact coordinates

Giả sử aggregator viết:

~~~xml
<modules>
    <module>libraries/core</module>
    <module>apps/command-line</module>
</modules>
~~~

POM của `libraries/core` có thể khai báo:

~~~xml
<artifactId>math-core</artifactId>
~~~

và `apps/command-line` có:

~~~xml
<artifactId>runner</artifactId>
~~~

Đây là **hai namespace khác nhau**:

| Dữ liệu | Ví dụ | Chức năng |
| --- | --- | --- |
| Aggregator module path | `libraries/core` | Chỉ đường đến POM khi collect |
| ArtifactId | `math-core` | Một phần định danh Maven artifact |
| Full GAV | `com.example.reactor:math-core:1.0.0` | Resolve artifact cho dependencies |
| Java package | `com.example.reactor.core` | Namespace của Java source/class |
| Java module name (nếu dùng JPMS) | `com.example.reactor.core` | JPMS identity, độc lập với reactor listing |

Không thể dùng `<module>math-core</module>` thay cho `<dependency>` trong `runner` nếu runner cần import `Numbers`. Và không nên chọn `-pl :libraries/core` vì selector `:artifactId` khác path: chọn `-pl libraries/core` hoặc `-pl :math-core`.

## 17. Version matching và lỗi reactor resolve dependency

Một lỗi điển hình: root/child version đang là `1.0.0-SNAPSHOT`, nhưng consumer dependency vẫn khai báo:

~~~xml
<dependency>
    <groupId>com.example.reactor</groupId>
    <artifactId>math-core</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Nếu module thật trong reactor là `com.example.reactor:math-core:1.0.0-SNAPSHOT`, đó là **hai tọa độ artifact khác nhau**. Reactor không tự coi chúng tương đương chỉ vì cùng tên folder.

Có thể gặp:

~~~text
Could not resolve dependencies for project ...
Could not find artifact com.example.reactor:math-core:jar:1.0.0 ...
~~~

Đây là **dạng lỗi minh họa**. Maven có thể cố resolve `1.0.0` từ repository, và nếu một artifact phiên bản cũ tồn tại, build còn nguy hiểm hơn: nó có thể dùng code cũ trong khi bạn tưởng đang build source của sibling.

### 17.1. Chiến lược version trong multi-module

- Dùng version thống nhất cho các modules trong cùng release train khi phù hợp.
- Khai báo child `<parent>` version chính xác.
- Quản lý versions của sibling dependencies qua parent `<dependencyManagement>` để tránh copy nhiều lần.
- Khi dùng `${project.version}`, `${revision}` hoặc CI-friendly versions, kiểm tra Maven version và POM interpolation/flattening phù hợp.
- Không đổi version của mỗi module một cách riêng lẻ rồi kỳ vọng reactor vẫn nhận quan hệ cũ.
- Dùng `mvn help:effective-pom` và `dependency:tree` để xác minh các coordinates cuối.

**`dependencyManagement` có thể quản lý version cho dependency được khai báo, nhưng không tự thêm dependency vào child.** Đây là khác biệt giữa quản lý metadata và tạo graph edge.

## 18. Một module không được collect dù folder tồn tại

Triệu chứng:

~~~text
reactor-lab/
├── pom.xml  # modules: greeter, runner
├── math-core/pom.xml
├── greeter/pom.xml
└── runner/pom.xml
~~~

`math-core` có POM và code nhưng không xuất hiện trong root `<modules>`; Maven 3 reactor **không tự collect** nó khi build root.

Nếu `greeter` khai báo dependency tới math-core, Maven có thể tìm artifact trong local/remote repository, hoặc fail nếu chưa có. Điều này không chứng minh root Reactor đã build `math-core`.

Cách sửa:
1. Nếu math-core thuộc build này, thêm module path đúng vào aggregator.
2. Nếu math-core là external dependency đã publish, không nhất thiết thêm vào modules; chỉ cần GAV/version/repository đúng.
3. Kiểm tra module path do active profile định nghĩa.
4. Xem Reactor Build Order/Summary để biết project thực sự tham gia.

**Tệp `pom.xml` nằm trên filesystem không đồng nghĩa một reactor node.** Việc thu thập phải đi qua cơ chế aggregation/project discovery tương ứng Maven version.

## 19. Vòng phụ thuộc giữa các modules làm Reactor không thể sort

Một DAG cho phép topo order. Nhưng nếu:

~~~text
module-a -> module-b
module-b -> module-c
module-c -> module-a
~~~

thì không có thứ tự nào xây cả ba mà không thiếu prerequisite. Maven sẽ phát hiện **cyclic reference/dependency** trong reactor graph và fail trước khi build bình thường.

Ví dụ sai:

~~~xml
<!-- Trong module-a -->
<dependency>
    <groupId>com.example</groupId>
    <artifactId>module-b</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

~~~xml
<!-- Trong module-b -->
<dependency>
    <groupId>com.example</groupId>
    <artifactId>module-a</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Đây là **hai fragments minh họa một thiết kế không hợp lệ**, không phải POM độc lập để chạy.

### Cách sửa vòng phụ thuộc

1. Xác định API/data types nào thật sự được cả hai module dùng.
2. Tách những interfaces/contracts dùng chung vào `shared-api` nằm **upstream**.
3. Đổi chiều dependency để một module phụ thuộc abstraction thay vì implementation ngược lại.
4. Dùng dependency injection/ports-adapters để tránh coupling.
5. Nếu hai module không có ranh giới hữu ích, cân nhắc hợp nhất chúng thành một module.
6. Tránh thêm `-am`, `-T` hoặc đảo `<modules>` để “vượt qua” cycle: **không có topo order cho chu trình**.

Vòng POM inheritance cũng là lỗi cấu hình riêng cần sửa; đừng tạo parent trỏ ngược vào child hoặc các `relativePath` dẫn đến graph không hợp lệ.

## 20. Quan hệ plugin và extension cũng có thể ảnh hưởng thứ tự

Dễ hiểu nhất là dependency giữa Java modules, nhưng Reactor còn cần ưu tiên một module **định nghĩa Maven plugin** trước module **sử dụng plugin ấy** khi cả hai đều là members của build graph.

Ví dụ mô hình:

~~~text
reactor:
  codegen-maven-plugin (packaging=maven-plugin)
         |
         v
  app-generator-consumer (khai báo plugin đó)
~~~

Nếu `app-generator-consumer` dùng plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>com.example.build</groupId>
            <artifactId>codegen-maven-plugin</artifactId>
            <version>1.0.0</version>
        </plugin>
    </plugins>
</build>
~~~

và `codegen-maven-plugin` là module khác trong reactor, Maven có thể sắp plugin module trước consumer. Đây là **fragment về quan hệ plugin**, không phải runnable plugin đầy đủ; để build plugin thực tế còn cần packaging, plugin descriptors và dependencies phù hợp.

Các quan hệ khác:

- Plugin có dependency tới module khác trong reactor.
- Build extension được khai báo và nằm trong reactor.
- Module dùng một artifact khác làm parent POM (có những quy tắc riêng theo Maven version).

### Điều gì không đủ?

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>com.example.build</groupId>
                <artifactId>codegen-maven-plugin</artifactId>
                <version>1.0.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

**Chỉ một entry dưới `pluginManagement` không tạo sort relationship.** Nếu consumer thực sự sử dụng plugin, phải có declaration tương ứng trong build hoặc cơ chế plugin activation hợp lệ.

Tương tự, một artifact trong `<dependencyManagement>` chưa phải dependency edge. Reactor không đoán “có thể tương lai dùng nó”.

## 21. Parent và aggregator không cần là cùng một POM

Nhiều dự án nhỏ dùng một root POM vừa parent vừa aggregator (như demo), nhưng đó chỉ là một lựa chọn.

### 21.1. Parent chỉ để kế thừa

Một corporate parent POM có thể quản lý:

- Java release.
- Dependency/plugin versions.
- Encoding và test configuration.
- Release policy.

Module A và B có thể kế thừa cùng parent nhưng nằm trong **hai repositories khác nhau**, không thuộc một reactor. Một parent không có `<modules>` không tự làm mọi descendants đang dùng nó trở thành thành viên phiên build hiện tại.

### 21.2. Aggregator chỉ để gom build

Một POM aggregator có thể liệt kê các projects **không kế thừa nó**. Mỗi module có thể sử dụng parent khác, ví dụ Spring Boot starter parent. Aggregation quyết định collect; inheritance quyết định effective POM/config.

### 21.3. Vì sao phân biệt quan trọng?

- Nếu thiếu một property/plugin config, kiểm tra **parent inheritance**, không chỉ module path.
- Nếu module không xuất hiện trong Reactor Summary, kiểm tra **aggregation**, không chỉ `<parent>`.
- Nếu build order sai so với dependency, kiểm tra **actual dependency graph**, không chỉ parent và module listing.
- Nếu module có package version khác, xem GAV thực tế và dependency coordinates.

Ba câu hỏi “module có được collect không?”, “module kế thừa config nào?” và “module cần ai trước?” phải được trả lời độc lập.

## 22. Active profiles có thể đổi tập modules được thu thập

Root POM có thể điều kiện hóa module collection bằng Maven profiles:

~~~xml
<modules>
    <module>math-core</module>
</modules>

<profiles>
    <profile>
        <id>full-build</id>
        <modules>
            <module>greeter</module>
            <module>report</module>
            <module>runner</module>
        </modules>
    </profile>
</profiles>
~~~

Đây là **mảnh POM minh họa**, không phải root POM demo phần 6. Khi active profile:

~~~bash
mvn -Pfull-build clean verify
~~~

Maven có thể collect thêm các modules đã khai báo trong profile. Nếu profile không active, module list khác.

Những điểm cần lưu ý:

1. POM model được dựng từ active profiles trước khi reactor execution plan cuối được xác định.
2. Không giả định profile chỉ đổi compiler flags; nó có thể thay **tập modules**.
3. Đừng chọn `-pl :runner` khi `runner` không nằm trong reactor được collect.
4. Với CI, ghi rõ profile dùng cho full build vs lite build.
5. Một profile active vì OS/JDK/property/file có thể khiến danh sách khác developer laptop.
6. Nếu định nghĩa `<module>` trùng hoặc path sai, việc collect có thể fail.

Kiểm tra:

~~~bash
mvn help:active-profiles
mvn help:effective-pom
~~~

Các lệnh help plugin có thể chịu chi tiết aggregator execution, nên hãy xác nhận đúng project khi đọc output trong multi-module.

## 23. Maven 3 và Maven 4: `modules` vs `subprojects`

Các ví dụ runnable ở trên dùng **Maven 3.9.x / modelVersion 4.0.0**. Maven 4 cải thiện multi-project builds và dùng từ **subproject** để tránh nhầm với JPMS Java modules.

### 23.1. Maven 3 / POM model 4.0.0

~~~xml
<modelVersion>4.0.0</modelVersion>
<modules>
    <module>core</module>
    <module>app</module>
</modules>
~~~

### 23.2. Maven 4 / POM model 4.1.0

Maven 4 hỗ trợ:

~~~xml
<modelVersion>4.1.0</modelVersion>
<subprojects>
    <subproject>core</subproject>
    <subproject>app</subproject>
</subprojects>
~~~

**Cảnh báo tương thích:** `<subprojects>` dành cho Maven 4 model 4.1.0. **Không copy vào POM Maven 3**. Maven 4 vẫn đọc POM model 4.0.0 và `<modules>` cũ; model 4.1.0 có thay đổi về schema, parent/version handling và root discovery.

### 23.3. Root discovery và resume được cải thiện

Maven 4 có khả năng tìm root multi-project setup từ một subproject bằng cách đi lên tree cho tới POM root được xác định bởi `.mvn` hoặc `root` attribute (trong model 4.1.0), với các quy tắc fallback nhất định.

Maven 4 còn cải thiện reactor-aware resume (`-r`, `--resume`, `--resume-from`) và subfolder builds. **Không đồng nhất behavior này với Maven 3** khi bạn gõ `mvn verify` trong folder `runner`; hãy kiểm tra `mvn -version` và tài liệu của version đang dùng.

### 23.4. Những điều không thay đổi về mặt khái niệm

- Phải có một tập projects/subprojects được thu thập hợp lệ.
- Các GAV và dependencies thật vẫn quyết định nhiều quan hệ build.
- `dependencyManagement`/`pluginManagement` không tự tạo một execution dependency edge.
- Cyclic dependencies vẫn không cho topo order hợp lệ.
- Child Maven project khác JPMS Java module.
- Parent inheritance và aggregation vẫn là hai khái niệm riêng.
- Nếu không có quan hệ thật, không nên dựa vào thứ tự log để điều phối build.

Tài liệu Maven 4 về collect/select có nhiều chi tiết CLI mới. Với script CI dùng Maven 3.9, hãy áp dụng option semantics của Maven 3 thay vì tự kết hợp các ví dụ Maven 4.

## 24. Lệnh chọn module theo tình huống thực tế

| Nhu cầu | Lệnh Maven 3.9.x từ root | Ý nghĩa |
| --- | --- | --- |
| Build và test toàn bộ reactor | `mvn -B clean verify` | Tất cả project đã collect |
| Chỉ kiểm tra root POM | `mvn -B -N validate` | Không build child modules |
| Build runner cùng dependencies | `mvn -B -pl :runner -am clean verify` | Phù hợp khi local repo trống |
| Chỉ build runner | `mvn -B -pl :runner verify` | Có thể cần upstream artifacts đã publish/install |
| Build core và downstream tests | `mvn -B -pl :math-core -amd verify` | Hữu ích khi thay core |
| Build greeter và report cùng prerequisites | `mvn -B -pl :greeter,:report -am verify` | Chọn nhiều modules |
| Chạy build song song | `mvn -B -T 2 clean verify` | Tôn trọng graph, tối đa threads phù hợp |
| Dừng sớm khi fail | `mvn -B -ff clean verify` | Default fail-fast |
| Cố gắng build modules độc lập sau lỗi | `mvn -B -fae clean verify` | Thu nhiều failure mà không bỏ dependencies |
| Resume từ runner trên Maven 3 | `mvn -B -rf :runner verify` | Cẩn thận missing upstream artifacts |
| Gọi root POM từ folder khác | `mvn -f reactor-lab/pom.xml -B clean verify` | Dùng đúng aggregator |
| Install cả reactor vào local repository | `mvn -B clean install` | Chỉ khi cần local repo artifact |

**Đừng đưa `-fn` vào CI release gate**. Đọc các tùy chọn cụ thể với `mvn -help` của bản Maven đang chạy để tránh nhầm version.

## 25. Debug “Maven không build module tôi mong đợi”

### 25.1. Module chưa được collect

Dấu hiệu: thiếu module trong `Reactor Build Order`/`Reactor Summary`.

Kiểm tra:
- Path trong `<modules>` có đúng không?
- POM file nằm ở đó không?
- Module được khai báo trong active profile hay inactive profile?
- Lệnh có `-N`, `-pl`, `-f` chọn POM/tập module khác không?
- Nested aggregator có liệt kê đúng descendants không?

Không sửa bằng cách thêm dependency ở random module: collection và sorting là hai tầng khác nhau.

### 25.2. Module có trong reactor nhưng build ở vị trí “lạ”

Dấu hiệu: `runner` được build sau `math-core` dù root liệt kê runner trước.

Đây thường là **đúng** vì `runner` cần `math-core` transitively qua greeter/report. Kiểm tra `<dependencies>` để hiểu graph. Nếu muốn module B chờ A vì **dùng artifact của A**, hãy khai báo dependency/plugin/extension relation thật, không dựa vào `<modules>` order.

### 25.3. Module có trong reactor nhưng Maven vẫn cố tải artifact từ repository

Kiểm tra:
- GAV/version/type/classifier mà consumer yêu cầu có khớp project sibling không?
- Module upstream có nằm trong **tập selected projects** sau `-pl` không?
- Có đang dùng `-rf` bỏ qua upstream vừa build ở một invocation khác?
- Artifact cần dùng có type/classifier riêng chưa được sibling tạo ở phase yêu cầu không?
- Có profile/parent đang đổi version không?
- Có một artifact cũ cùng GAV trong local repo làm bạn đọc sai kết quả không?

Lệnh giúp quan sát:

~~~bash
mvn help:effective-pom
mvn dependency:tree
~~~

Trong multi-module, hãy xác định project/module nào đang được plugin xử lý khi đọc output.

### 25.4. Circular dependency

Dấu hiệu: Maven báo cyclic dependency/interpolation/parent error trước compile. Đọc graph và tách API chung upstream. Đổi `-T` hay `-am` không tạo ra thứ tự topo hợp lệ cho cycle.

### 25.5. Build một module riêng không tìm được parent

`<relativePath>../pom.xml</relativePath>` cần trỏ đúng parent nếu parent chưa có trong local repo. Nếu parent ở chỗ khác hoặc đã publish, cấu hình `relativePath` phù hợp. Đừng copy POM root vào các module cho dễ, vì sẽ phân kỳ config/version.

### 25.6. Module bị SKIPPED sau module FAIL

Đọc **lỗi thực tế đầu tiên** của upstream. Nếu `math-core` fail, việc runner bị skipped là phản ứng có chủ đích để tránh dùng artifact không hợp lệ. Sửa core trước, sau đó build phần upstream/downstream cần thiết.

### 25.7. CI chạy module đã thay đổi nhưng thiếu downstream checks

Nếu chỉ build `-pl :math-core`, bạn có thể bỏ sót lỗi biên dịch hoặc test ở greeter/report/runner. Khi sửa API của core, `-pl :math-core -amd` hoặc full reactor verify đáng tin hơn, tùy yêu cầu pipeline.

## 26. Maven Reactor và dependency tree: hai đồ thị liên quan nhưng khác nhau

**Dependency tree** của một module có thể chứa artifacts nằm ngoài reactor (third-party JARs, parent POMs, BOM-managed libraries). **Reactor graph** gồm các Maven projects được thu thập/selected trong **phiên build hiện tại** và quan hệ giữa chúng.

Ví dụ:

~~~text
runner dependency tree:
  runner
    +-- greeter
    |     +-- math-core
    +-- report
    |     +-- math-core
    +-- junit-jupiter (test)
          +-- junit-jupiter-api
          +-- junit-jupiter-engine
~~~

Trong đó JUnit libraries đến từ Maven repository, không nhất thiết là modules của `reactor-lab`. Reactor chỉ build project mà root/selection thu thập; không tự build source JUnit Jupiter chỉ vì module runner có dependency JUnit.

**Sự khác biệt thiết yếu:**

- `mvn dependency:tree` hiển thị graph resolution/scope của dependencies theo project.
- `Reactor Build Order` hiển thị các project tham gia build theo thứ tự sort.
- `jar tf`/artifact inspection hiển thị những gì đã thực sự được đóng gói.
- `Reactor Summary` hiển thị kết quả thành công/thất bại của từng project.

Không xem một trong bốn công cụ quan sát đó là bằng chứng đầy đủ cho mọi câu hỏi.

## 27. Reproducibility và CI: điều nên cố định

Một reactor build ổn định cần:

1. Cố định Maven major/minor thông qua Maven Wrapper hoặc CI image.
2. Cố định JDK và `maven.compiler.release`.
3. Pin plugin versions và dependency versions.
4. Khai báo GAV của sibling dependencies nhất quán.
5. Không dựa vào artifact còn sót trong local Maven repository.
6. Chạy `mvn clean verify` từ đúng aggregator cho full quality gate.
7. Khi build chọn lọc, dùng `-pl`/`-am`/`-amd` có chủ đích.
8. Không trộn `-rf` với giả định Maven 3 sẽ tự phục hồi upstream chưa install.
9. Cẩn thận với `-T` khi plugins/tests dùng shared files hoặc database.
10. Xác nhận số tests và reports từng module, không chỉ Reactor Summary xanh.
11. Giữ output modules trong `${project.build.directory}` riêng biệt.
12. Không dùng `-fn` để đánh dấu CI pass.
13. Kiểm tra active profiles vì chúng có thể thay collection và dependency graph.
14. Chỉ dùng Maven cache để tăng tốc, không thay dependency metadata chính xác.
15. Kiểm soát external repositories, credentials và artifact provenance.
16. Khi ứng dụng cần executable/distro cuối, chọn module assembly/shade thích hợp; reactor tự nó không gộp các JAR thành một.
17. Nếu phát hành nhiều modules, publish theo một release train/version policy rõ ràng.
18. Khi nâng Maven 3 → Maven 4, thử lại lệnh CLI đặc biệt và POM model migration.

### Vì sao “build toàn bộ” vẫn hữu ích?

Chỉ test module thay đổi có thể nhanh, nhưng bỏ sót regression ở consumer downstream. Với API modules như `math-core`, build downstream quan trọng. Một chiến lược hợp lý là:
- Pull request nhanh: build affected modules **và dependents** theo graph.
- Integration/nightly/release: build full reactor trong môi trường sạch.
- Khi cần release artifacts: kiểm tra installation/deployment đúng với scopes và POM publication.

Phạm vi chính xác của affected-project build tùy quy mô và policy; Maven không tự phân tích Git diff để quyết định module nào thay đổi chỉ từ `-pl`.

## 28. Bài tập: tự kiểm tra cách Reactor xử lý các tình huống

**Câu 1.** Root liệt kê `service` trước `core`, nhưng service phụ thuộc core. Module nào phải được build trước?

**Đáp:** `core`, vì reactor ưu tiên project dependency thật hơn module declaration order.

**Câu 2.** Hai module `a` và `b` không phụ thuộc nhau, điều gì quyết định thứ tự mặc định?

**Đáp:** Trong Maven 3 sorting, thứ tự khai báo `<modules>` được dùng khi không có ràng buộc khác; với parallel build, execution có thể đồng thời.

**Câu 3.** Một artifact chỉ nằm trong `<dependencyManagement>`. Nó có làm Reactor build module đó trước không?

**Đáp:** Không. Management không tự tạo một dependency edge.

**Câu 4.** Hai module có cùng parent nhưng không có direct/indirect dependency. Có bắt buộc module đầu làm trước module sau?

**Đáp:** Không vì chỉ cùng parent không nói rằng chúng cần artifact của nhau. Chúng có thể độc lập trong reactor.

**Câu 5.** `-pl :runner` có tự build mọi upstream modules trên Maven 3 không?

**Đáp:** Không. Dùng `-am` khi muốn build prerequisites trong reactor.

**Câu 6.** `-pl :math-core -amd` khác `-am` thế nào?

**Đáp:** `-amd` chọn downstream dependents; `-am` chọn upstream dependencies.

**Câu 7.** Sau `mvn clean verify`, dùng `-rf :runner` có luôn resolve upstream artifacts trên Maven 3 không?

**Đáp:** Không. Upstream có thể chưa được install vào local repo; chạy chọn lọc với `-am` hoặc full reactor khi cần.

**Câu 8.** Reactor có tự đóng gói bốn module JAR thành một Uber JAR không?

**Đáp:** Không. Nó điều phối build projects; packaging bundle yêu cầu plugin/distro module riêng.

**Câu 9.** Nếu module `a` phụ thuộc `b`, còn `b` phụ thuộc `a`, đảo thứ tự `<modules>` có sửa được không?

**Đáp:** Không. Đồ thị có chu trình, không tồn tại topo order hợp lệ.

**Câu 10.** `mvn -N validate` tại root có chứng minh child Java modules compile không?

**Đáp:** Không, vì `-N` không build descendants.

**Câu 11.** Một module folder không được liệt kê trong `<modules>` nhưng có `pom.xml`, Maven 3 root reactor có tự build nó không?

**Đáp:** Không. Cần aggregation hoặc cơ chế project selection/collection phù hợp.

**Câu 12.** Khi `-T 2`, hai module độc lập luôn có thứ tự log giống nhau?

**Đáp:** Không. Logs có thể xen kẽ; chỉ những prerequisite relationships phải được tôn trọng.

**Câu 13.** `-fn` có thích hợp cho release CI quality gate không?

**Đáp:** Không. Nó có thể che failure trong exit status, khiến pipeline báo thành công sai.

**Câu 14.** Maven 4 `<subprojects>` và Maven 3 `<modules>` có thể dùng lẫn tùy ý trên POM 4.0.0 không?

**Đáp:** Không. `<subprojects>` là cơ chế modelVersion 4.1.0 của Maven 4; Maven 3 dùng `<modules>`.

**Câu 15.** Nếu `greeter` dùng `math-core:1.0.0` nhưng reactor có `math-core:2.0.0`, Maven có tự coi là cùng một artifact vì folder trùng không?

**Đáp:** Không. Maven resolve theo coordinates/version; cần sửa dependency hoặc version strategy.

**Câu 16.** Nếu `runner` chỉ import `Greeter` trong source nhưng không khai báo Maven dependency, `-am` có tự phát hiện import không?

**Đáp:** Không. Reactor sorting và selection dựa trên POM/build metadata.

**Câu 17.** Một parent POM có thể không là aggregator không?

**Đáp:** Có. Parent phục vụ inheritance, aggregator phục vụ collection.

**Câu 18.** Nếu Java test ở runner cần `Numbers.class` gián tiếp, runtime classpath phải có gì?

**Đáp:** Cần runner, greeter, report và math-core classes/JARs theo dependency graph; demo truyền đủ bốn thư mục qua `java -cp`.

**Câu 19.** Maven plugin do một module build và được module khác khai báo là plugin thật có tác động sort không?

**Đáp:** Có thể có, vì plugin declaration tương ứng module trong reactor là một quan hệ sorting được tài liệu nêu.

**Câu 20.** Khi thấy Reactor Summary `runner SKIPPED` sau `math-core FAILURE`, nên sửa module nào trước?

**Đáp:** Bắt đầu với `math-core` vì đó là upstream failure; runner bị skipped do không có prerequisite hợp lệ.

## 29. Checklist trước khi merge hoặc release một multi-module Maven build

1. Root aggregator có `packaging=pom` và liệt kê đúng modules.
2. Tất cả module paths dẫn tới POM hợp lệ; không có folder bị bỏ sót hoặc path trùng.
3. Child POM khai báo parent/relativePath phù hợp.
4. `groupId`, `artifactId`, `version`, type và classifier nhất quán giữa sibling dependency và producer.
5. Có actual `<dependency>` cho mọi module source dùng sibling artifact.
6. Không hiểu nhầm dependencyManagement/pluginManagement thành quan hệ sort.
7. Không có chu trình trong dependency graph.
8. Có quy tắc rõ ràng cho plugin modules/extensions được sử dụng trong cùng reactor.
9. Java release, Maven/JDK/plugin versions được pin và tương thích.
10. Unit/integration tests chạy đúng ở mỗi module cần kiểm.
11. `mvn -B clean verify` từ root chạy thành công trên môi trường sạch.
12. Reactor Summary có đúng tập projects và status dự kiến.
13. Test ứng dụng cuối với đầy đủ runtime classpath/distribution packaging.
14. Khi chạy `-pl`, dùng `-am` nếu cần build source của upstream modules.
15. Khi đổi API của core, chọn downstream tests (`-amd`) hoặc full reactor.
16. Không dựa vào `-rf` Maven 3 để tìm upstream artifacts chưa install.
17. Không dùng `-fn` ở CI release.
18. Khi `-T`, không có hai module ghi cùng một output/global file thiếu lock.
19. Không giả định thứ tự build theo tên folder/đường dẫn.
20. Active profiles không làm collection khác môi trường ngoài ý muốn.
21. Multi-module builds không tự là Uber JAR; chọn packaging/distro strategy riêng.
22. CI có logs/reports theo module, không che failure/skip.
23. Repository/cache chỉ tăng tốc, không thay metadata đúng.
24. Với Maven 4, phân biệt model 4.0.0 và 4.1.0, root discovery và `subprojects`.
25. Đã thử từ clean checkout và documented commands trên OS/JDK mục tiêu.

## Tài liệu tham khảo

- [Apache Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Guide to Working with Multiple Subprojects (Maven 4)](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)
- [Apache Maven — POM Reference: Aggregation, Inheritance, Dependencies](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [Apache Maven — What's New in Maven 4](https://maven.apache.org/whatsnewinmaven4.html)
- [Apache Maven — Maven CLI Options Reference](https://maven.apache.org/ref/current/maven-embedder/cli.html)
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [JUnit — User Guide](https://docs.junit.org/5.11.4/user-guide/)

