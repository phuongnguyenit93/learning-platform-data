# Maven Plugin và Goal: Goal chạy từng mô-đun và goal tổng hợp toàn dự án

> **Chủ đề:** Build Tool Maven · **Nhóm:** Plugin và goal  
> **Trọng tâm:** phân biệt goal xử lý từng Maven module, goal có thuộc tính `aggregator`, và quy tắc thực thi trong một reactor nhiều module.

## 1. Câu trả lời cốt lõi

Trong một dự án Maven nhiều mô-đun (*multi-module*), **reactor** thu thập các module, sắp xếp chúng theo quan hệ phụ thuộc và chạy phần build được yêu cầu. Mỗi thao tác cụ thể của Maven plugin được gọi là một **goal**; lớp/đơn vị triển khai goal trong plugin được gọi là **Mojo**.

Không phải goal nào cũng có cùng phạm vi:

- **Goal thông thường (không phải aggregator):** khi gọi trực tiếp trong reactor, Maven có thể thực thi goal cho **từng project/module được chọn**. Ví dụ `dependency:tree` hiển thị dependency tree theo từng project, không mặc nhiên gộp thành một cây toàn hệ thống.
- **Aggregator goal (`aggregator=true` trong descriptor):** khi gọi **trực tiếp từ Maven CLI** trong Maven 3, goal được thực thi **một lần theo reactor được chọn**, thay vì mỗi module một lần. Ví dụ chính thức: `help:effective-pom` và `javadoc:aggregate` đều có metadata `Executes as an aggregator goal`.
- **Lưu ý quan trọng nhất:** trong Maven 3, nếu một **aggregator goal được bind vào lifecycle phase trong POM**, thì thuộc tính `aggregator=true` **không tự bảo đảm chỉ một execution cho toàn reactor**. Maven có thể thực thi binding ở **từng module nơi binding tồn tại**; nếu cấu hình plugin được kế thừa, có nguy cơ chạy lặp. Đây là điểm khác biệt giữa **gọi goal từ CLI** và **gắn goal vào phase** mà rất nhiều bài giới thiệu bỏ sót.

Cũng cần phân biệt hai khái niệm cùng mang chữ *aggregate*:

1. **Aggregator POM/project**: một POM liệt kê `<modules>` để Maven biết module nào thuộc reactor, thường có `<packaging>pom</packaging>`.
2. **Aggregator goal/Mojo**: thuộc tính của **một goal cụ thể** trong plugin descriptor; quyết định cách Maven gọi goal đó trong nhiều project theo ngữ cảnh.

Có root POM tổng hợp module **không có nghĩa mọi goal chạy một lần**. Ngược lại, một plugin có aggregator goal **không tự tạo reactor** nếu chỉ chạy trong một project độc lập.

Sau bài này bạn sẽ biết đọc metadata của plugin, dự đoán số lần chạy goal, xây một project Maven/Java 17 ba POM, dùng `-pl`, `-am`, `-N`, `-rf`, phân biệt direct CLI và lifecycle, và thiết kế bước CI để tạo báo cáo tổng hợp đúng thời điểm.

## 2. Thuật ngữ cần nắm

| Thuật ngữ | Nghĩa chính xác | Ví dụ |
| --- | --- | --- |
| Maven plugin | Tập các goals triển khai những chức năng build | `maven-compiler-plugin`, `maven-dependency-plugin` |
| Goal | Một tác vụ cụ thể trong plugin | `compiler:compile`, `dependency:tree` |
| Mojo | Thành phần code thực hiện một goal | Java class được đăng ký tên goal |
| Build phase | Mốc trong lifecycle, có thể kích hoạt nhiều goals | `compile`, `test`, `package`, `verify` |
| Lifecycle | Chuỗi phases Maven thực thi tới mốc được yêu cầu | `default`, `clean`, `site` |
| Reactor | Cơ chế Maven tập hợp, sắp xếp, build nhiều project được chọn | root POM có `core` và `app` |
| Module/subproject | Project với POM riêng, có GAV và phần build riêng | `core/pom.xml`, `app/pom.xml` |
| Aggregator project | Project khai báo `<modules>` để tập hợp reactor | `reactor-goals-demo/pom.xml` |
| Aggregator goal | Goal có metadata aggregator để xử lý đa project trong reactor | `help:effective-pom` |
| Plugin execution | Một binding goal vào phase và cấu hình trong POM | `<execution><phase>verify</phase>...` |
| Plugin inheritance | Plugin/configuration/executions từ parent có thể được child kế thừa | `<inherited>false</inherited>` để hạn chế |
| Thread-safe goal | Goal được plugin đánh dấu hỗ trợ concurrent execution | Thuộc tính **khác** `aggregator` |

**Đừng nhầm phase với goal:** `mvn package` chạy các phase mặc định đến `package`; `mvn dependency:tree` gọi một plugin goal. Chạy `mvn package dependency:tree` là yêu cầu cả một lifecycle segment và một goal, không phải định nghĩa phase mới.

## 3. Reactor thực sự hoạt động ra sao?

Giả sử:

```text
reactor-goals-demo/
├── pom.xml                 # root aggregator + parent
├── core/
│   ├── pom.xml             # org.example:core:1.0.0
│   └── src/main/java/...
└── app/
    ├── pom.xml             # org.example:app:1.0.0
    └── src/main/java/...
```

`app` khai báo dependency trực tiếp vào `core`.

Khi chạy từ root:

```bash
mvn clean package
```

Reactor có nhiệm vụ chọn projects, xác định **thứ tự hợp lệ** rồi build từng project. Trong dự án mẫu, thứ tự hợp lý là:

```text
reactor-goals-demo (packaging pom)
          |
          v
         core (jar)
          |
          v
          app (jar, phụ thuộc core)
```

Với reactor Maven 3, những quan hệ ảnh hưởng sorting bao gồm dependencies giữa các module, plugin/plugin dependencies trong reactor, build extensions và parent POM; thứ tự `<modules>` được dùng khi không có quan hệ mạnh hơn. **`dependencyManagement` và `pluginManagement` thuần túy không tạo quan hệ thứ tự build** vì chúng không tự hiện thực dependency/plugin instance.

**Reactor không đồng nghĩa “thực hiện mọi phase một lần rồi chuyển sang phase tiếp theo cho tất cả module”**. Theo cách xây dựng thông thường, Maven sẽ xử lý lifecycle của các project theo reactor order; vì vậy root project được xử lý sớm. Nếu một báo cáo toàn reactor chỉ nên chạy khi mọi JAR đã tạo xong, việc bind báo cáo ấy ở root phase `verify` chưa chắc an toàn: root `verify` có thể xảy ra **trước** child `package`.

### 3.1. `<modules>` và `<parent>` là hai quan hệ độc lập

Root có thể là **aggregator** vì khai báo `<modules>`. Các module có thể có root là **parent** vì khai báo `<parent>` trong child POM. Hai cơ chế thường được dùng chung nhưng không phải một:

- `<modules>` giúp Maven **chọn project để build** trong reactor.
- `<parent>` giúp child **kế thừa model** như properties, dependencyManagement, pluginManagement.
- Một module được liệt kê trong `<modules>` không nhất thiết kế thừa root POM nếu không khai báo quan hệ parent phù hợp.
- Một project có parent POM không nhất thiết là module được aggregator hiện tại liệt kê.

Khi muốn plugin execution chỉ ở root, cần xét **cả aggregation lẫn inheritance**, không chỉ dựa vào `packaging=pom`.

## 4. Goal xử lý từng module

Một goal thông thường, không có cờ `aggregator`, được Maven gọi trong ngữ cảnh **project hiện tại**. Với reactor nhiều module và CLI goal phù hợp, Maven thực hiện goal lần lượt cho các project trong tập reactor đã chọn.

Ví dụ:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Trang tài liệu chính thức gọi goal này là `dependency:tree`, mô tả “Displays the dependency tree for this project”; nó **không** khai báo `Executes as an aggregator goal`. Vì vậy khi gọi từ root reactor, bạn thường thấy cây dependency **theo từng project**.

Với dự án mẫu:

- Root `packaging=pom` không có Jackson hay `core` làm dependency ứng dụng; phần tree của root sẽ ít hoặc không có dependency.
- `core` không khai báo dependency bên ngoài; phần tree của core cũng đơn giản.
- `app` có **direct dependency** vào `core`, nên cây của app thể hiện `org.example:core:jar:1.0.0:compile` theo mẫu.

Đây **không phải một tree chung** chứa mọi dependency của toàn hệ thống theo nghĩa hợp nhất/khử trùng lặp. Cùng một external dependency có thể được nhắc ở cây của nhiều modules nếu mỗi module thật sự phụ thuộc vào nó.

### 4.1. Compiler goals cũng có ngữ cảnh project

`compiler:compile` biên dịch các source của **module hiện tại** và ghi class vào `target/classes` của module đó (theo cấu hình hiệu lực). Nếu có hai JAR modules:

```text
core/target/classes/org/example/core/Greeter.class
app/target/classes/org/example/app/Main.class
```

Khi chạy `mvn compile` từ root, Maven đi qua phase compile của từng project có binding tương ứng theo packaging/lifecycle. **Root `packaging=pom` thường không biên dịch Java classes**; `core` và `app` mới có mã Java để compile.

Việc Maven gọi cùng goal cho nhiều project **không** có nghĩa sẽ trộn hai thư mục `target/classes` lại thành một. Mỗi module có POM, build directory, dependencies, outputs và test results riêng, trừ khi bạn chủ động cấu hình khác.

### 4.2. Per-module không phải lúc nào cũng “đúng số thư mục nhìn thấy”

Phần reactor **được chọn** có thể khác toàn bộ module trong root:

- `mvn -pl :app ...` chọn dự án có artifactId `app`.
- `mvn -pl :app -am ...` chọn `app` cộng các **reactor dependencies** cần build trước nó; thường có `core` và phần parent/aggregator liên quan nếu thuộc reactor.
- `mvn -N ...` chỉ xử lý project ở working directory, không đi đệ quy vào `<modules>`.
- IDE hoặc `-f` có thể chọn một POM khác làm đầu vào.
- Một plugin goal có cấu hình `skip` hoặc điều kiện riêng thì được gọi nhưng có thể không tạo output.

Vì vậy đừng phát biểu rằng “goal per-module phải chạy đúng ba lần” nếu không xác định tập selected reactor projects và cấu hình của goal.

## 5. Aggregator goal: thuộc tính của Mojo, không phải phép cộng tự động

Một goal được plugin đánh dấu `aggregator=true` có khả năng xử lý context của nhiều projects trong reactor. Ví dụ các trang plugin chính thức:

| Goal | Metadata chính thức | Công dụng |
| --- | --- | --- |
| `help:effective-pom` | **Executes as an aggregator goal** | Hiển thị effective POM/model với profiles |
| `help:describe` | **Executes as an aggregator goal** | Mô tả plugin, goal và tham số |
| `javadoc:aggregate` | **Executes as an aggregator goal** | Sinh API documentation tổng hợp theo khả năng của plugin |
| `dependency:tree` | **Không ghi aggregator**; goal cho project | Liệt kê dependency tree theo project |

Đọc chính metadata của **goal cụ thể**, không đoán từ tên plugin. Một plugin có thể có cả goal thường và aggregator goals; thuộc tính được áp dụng ở mức **Mojo/goal** chứ không phải mọi goal trong plugin có chung phạm vi.

### 5.1. Direct CLI trong Maven 3: aggregator goal thường chạy một lần

Từ root reactor, ví dụ:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

Goal `help:effective-pom` có descriptor `aggregator`, nên **khi gọi trực tiếp qua CLI**, Maven 3 xử lý goal như một aggregator execution trong reactor đã chọn. Output của plugin có thể chứa thông tin effective POM từ nhiều projects, tùy cấu hình/phiên bản; đừng dùng số khối XML để suy ra **số lần goal được gọi**.

Ngược lại:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

là một goal theo project và sẽ chạy trong ngữ cảnh từng project được chọn. Đây là cặp lệnh thuận tiện để **quan sát sự khác biệt**.

### 5.2. Aggregator flag không tự gom dữ liệu

Đánh dấu `aggregator=true` chỉ ảnh hưởng execution semantics và một số cách Maven cấp reactor context/giải quyết dependencies/fork goal. Tự nó không sinh summary HTML, không tự đọc mọi `target` và không bảo đảm artifact được đóng gói xong.

Chính **code của plugin** quyết định có thật sự đọc `reactorProjects`, `MavenSession` hoặc outputs từng module và tổng hợp thành một report hay không. Một goal có aggregator metadata nhưng chỉ in thông tin cấu hình vẫn là aggregator goal, không phải một thuật toán “merge dependencies” mặc định.

### 5.3. Aggregator goal không phải `pluginManagement`

Đặt version của Maven Javadoc Plugin vào `<pluginManagement>` **không làm goal `javadoc:aggregate` tự chạy**. Plugin phải được gọi bằng CLI, được khai báo trong lifecycle/reporting phù hợp, hoặc được kích hoạt bằng cấu hình khác.

Tương tự, `dependencyManagement` không tạo Maven reactor edges: quản lý versions là một hành vi khác so với thực thi plugin goal.

## 6. Điểm dễ sai: gọi trực tiếp và bind vào lifecycle khác nhau

Đây là **ngoại lệ thiết yếu của Maven 3**.

| Tình huống | Hành vi cần nhớ |
| --- | --- |
| Gọi `mvn plugin:aggregator-goal` trực tiếp trên reactor | Aggregator Mojo được **gọi một lần** trong execution đó |
| Bind cùng goal vào phase `verify` trong root POM | Maven thực thi goal khi phase `verify` của một project có binding chạy; **không tự hoãn đến cuối toàn reactor** |
| Binding trong root POM được child **kế thừa** | Có thể có execution ở **nhiều modules**; cờ `aggregator=true` không tự loại bỏ sự lặp |
| Binding root `<inherited>false</inherited>` | Có thể ngăn child kế thừa plugin/execution; **root vẫn chạy ở phase của root**, thường sớm |
| Chạy goal không aggregator trong reactor | Có thể gọi trên **mỗi project được chọn**, tùy context và cấu hình |
| `-T` parallel reactor | Cần xét `threadSafe`, lock/đồng bộ và plugin compatibility; aggregator không có nghĩa chạy song song an toàn |

Tài liệu thiết kế/historical issue của Apache Maven ghi nhận cụ thể nhược điểm: **aggregator Mojo được gọi một lần qua direct CLI, nhưng khi gắn vào lifecycle vẫn chạy cho mỗi project có binding**. Đây là lý do tài liệu plugin thường khuyên chọn một trong hai cách: gọi aggregator goal riêng sau build, hoặc cấu hình lifecycle thật cẩn thận về inheritance và thời điểm.

### 6.1. Cấu hình dễ gây chạy lặp

**Phản ví dụ minh họa**, đặt trong parent/root `<build><plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.12.0</version>
    <executions>
        <execution>
            <id>aggregate-docs</id>
            <phase>verify</phase>
            <goals>
                <goal>aggregate</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Nếu parent POM này được child kế thừa, **execution có thể được bind ở nhiều modules**; cờ aggregator của `javadoc:aggregate` không bảo đảm đúng một lần từ lifecycle. Ngoài ra root `verify` thường chạy trước `core`/`app` build xong, nên báo cáo có thể thiếu classes/source outputs được kỳ vọng. Không copy fragment này vào production như một best practice.

### 6.2. `inherited=false` giải quyết lặp, không giải quyết thời điểm

Một cách ngăn plugin/execution được kế thừa:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.12.0</version>
    <inherited>false</inherited>
    <executions>
        <execution>
            <id>aggregate-docs</id>
            <phase>verify</phase>
            <goals>
                <goal>aggregate</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

**Fragment** này dành cho POM nơi bạn muốn cấu hình root-only. Nó ngăn plugin config được child kế thừa theo quy tắc Maven thông thường. Tuy nhiên, khi root là một project ở đầu reactor, execution ở `verify` của root vẫn **không đồng nghĩa “sau tất cả child verify”**.

Muốn aggregate output **sau khi modules đã package**, cách dễ hiểu trong Maven 3 là **hai invocation rõ ràng**:

```bash
mvn -B clean verify
mvn -B org.apache.maven.plugins:maven-javadoc-plugin:3.12.0:aggregate
```

Lệnh thứ nhất hoàn tất reactor build. Lệnh thứ hai gọi aggregator goal trực tiếp từ root, sau khi các modules đã build. `javadoc:aggregate` còn có thể fork phase `compile` theo chính tài liệu plugin; vì vậy tổng chi phí có thể gồm việc xét/biên dịch lại những phần Maven cần và JDK Javadoc Tool phải khả dụng.

**Đừng hứa luôn chỉ tạo một file HTML**: Maven Javadoc Plugin có các lựa chọn report, output directories và hành vi nhiều module riêng theo version; từ các bản 3.x có thể tạo aggregated report ở những vị trí theo module. Điều cốt lõi cần kiểm tra là **execution scope, timing và nội dung báo cáo**, không phải đếm HTML bằng cảm giác.

## 7. Bài thực hành Java 17: root POM + core + app

Bây giờ xây một reactor thật với mã chạy được. Dự án gồm hai JAR modules và một POM aggregator/parent:

1. Root `reactor-goals-demo` có `<packaging>pom</packaging>`, `<modules>core, app</modules>`.
2. `core` cung cấp class `org.example.core.Greeter`.
3. `app` khai báo dependency vào `core` và in lời chào.
4. Các modules kế thừa Java release 17 và compiler plugin version từ parent.

Mục tiêu không phải viết plugin riêng; chúng ta dùng **các goals có sẵn** để quan sát reactor và metadata aggregator/per-module.

### 7.1. Cấu trúc thư mục đầy đủ

```text
reactor-goals-demo/
├── pom.xml
├── core/
│   ├── pom.xml
│   └── src/main/java/org/example/core/Greeter.java
└── app/
    ├── pom.xml
    └── src/main/java/org/example/app/Main.java
```

Cần JDK 17+ và Maven 3.9.x. Máy có thể cần Internet/repository mirror hợp lệ để tải build plugins. Không cần library runtime ngoài Java để chạy ứng dụng, chỉ có dependency reactor `app -> core`.

### 7.2. Root pom.xml — đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>reactor-goals-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích:

- `packaging=pom` phù hợp với POM không sinh JAR chính.
- `<modules>` chọn hai module để reactor xử lý.
- `<maven.compiler.release>17</maven.compiler.release>` đặt Java target nhất quán cho children.
- `maven-compiler-plugin` có version xác định và được kế thừa theo quy tắc POM inheritance; nó không khiến root phải có `src/main/java`.
- `<modules>` chưa khẳng định app cần core; chính khai báo `<dependency>` trong `app` tạo quan hệ để reactor sắp xếp.

### 7.3. core/pom.xml — đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example</groupId>
        <artifactId>reactor-goals-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>
</project>
```

`groupId`, `version` và compiler settings đến từ parent. Java sources của `core` được compile như một project JAR độc lập trong reactor. POM không cần tự nhắc `<modules>`; nó là child module, không phải aggregator chứa thêm module.

### 7.4. core/src/main/java/org/example/core/Greeter.java

```java
package org.example.core;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Hello from core";
    }
}
```

Class không có external imports. Hàm `message()` trả chuỗi cố định và không dùng network, file hay thời gian hiện tại, nên kết quả nhất quán.

### 7.5. app/pom.xml — đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example</groupId>
        <artifactId>reactor-goals-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

`${project.version}` là biểu thức Maven hợp lệ trong `<version>` của **dependency** ở đây, được thay bằng project version hiệu lực (`1.0.0`). `app` giờ có direct dependency vào `core`, nên reactor biết phải build `core` trước `app`.

**Không nhầm với `<modules>`:** dù root liệt kê `core` trước `app`, chúng ta vẫn cần một dependency ở `app` nếu App.java dùng class `Greeter`. `<modules>` không tự đặt mọi module JAR lên compile classpath của mọi module khác.

### 7.6. app/src/main/java/org/example/app/Main.java

```java
package org.example.app;

import org.example.core.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("app -> " + Greeter.message());
    }
}
```

Các đường dẫn/tên package khớp POM và source files. Đây là chương trình Java biên dịch được với JDK 17, với điều kiện `core` artifact có mặt qua reactor hoặc local Maven repository.

### 7.7. Build toàn reactor và chạy ứng dụng

Tại thư mục root `reactor-goals-demo/`:

```bash
java -version
javac -version
mvn -version
mvn -B clean install
```

Build `install` sẽ đi qua các phases tương ứng cho root POM và hai JAR modules, đưa các artifacts build thành công vào **local Maven repository** của bạn. Làm bước này trước để khi **chạy riêng app** ở lệnh sau, Maven có thể resolve artifact `org.example:core:1.0.0` đã install.

Chạy App bằng Exec Maven Plugin, version cố định:

```bash
mvn -q -f app/pom.xml org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=org.example.app.Main
```

**Stdout chính xác của ứng dụng** (không tính Maven/plugin log):

```text
app -> Hello from core
```

Maven Exec Plugin dựng classpath của `app`, gồm `core` JAR đã cài trong local repository. Trong ví dụ này không có external runtime library nào ngoài `core`.

Không chạy `java -cp app/target/classes org.example.app.Main` rồi kỳ vọng tìm thấy `Greeter` — `core` nằm trong một JAR/module khác. Nếu muốn dùng Java CLI, phải tự cung cấp cả `app/target/classes` và `core/target/classes` hoặc JAR trên classpath, với dấu phân cách path đúng OS. Maven Exec Plugin tránh khác biệt đó.

**Kết quả build mong đợi:**

```text
core/target/classes/org/example/core/Greeter.class
core/target/core-1.0.0.jar

app/target/classes/org/example/app/Main.class
app/target/app-1.0.0.jar
```

Root project `packaging=pom` không tạo `reactor-goals-demo-1.0.0.jar` như một JAR ứng dụng. Nó tham gia reactor và được install như một POM artifact. Các plugin logs có thể thay đổi theo version và OS; chỉ coi dòng `app -> Hello from core` là stdout cần đối chiếu.

## 8. Thực nghiệm 1: per-module goal dependency:tree

Sau `mvn -B clean install`:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Từ root reactor, goal không aggregator này chạy theo từng project được chọn, và log có thể gồm phần riêng cho:

- `reactor-goals-demo`
- `core`
- `app`

Ở phần của `app`, bạn cần nhận ra quan hệ:

```text
org.example:app:jar:1.0.0
\- org.example:core:jar:1.0.0:compile
```

Đây là **phần logic của tree**, không phải bản sao toàn bộ Maven output. Root và `core` không có dependencies ứng dụng nên cây có thể ít dòng. Các bản plugin có thể khác indentation/ký tự vẽ cây.

### 8.1. Chỉ phân tích module app

```bash
mvn -pl :app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

`-pl :app` dùng artifactId để chọn project `app` trong reactor; chỉ còn phần dependency tree của app là nội dung quan tâm. Bạn có thể dùng path tương đối `-pl app` nếu đang đứng tại root và module nằm trong thư mục `app/`.

### 8.2. Build cả những module mà app cần

```bash
mvn -B -pl :app -am clean package
```

`-am` (*also-make*) đưa các **reactor project dependencies cần thiết** vào tập build, giúp không phải cài `core` trước cho một lần **package** app qua reactor. Tùy cấu trúc project, parent/aggregator có thể cũng thuộc tập chọn, nên hãy đọc phần `Reactor Build Order`/`Reactor Summary` thay vì tự đếm số lần goal.

Một điểm đáng nhớ: `-am` không có nghĩa mọi module trong repo đều được build. Nó chọn **những module cần để build mục tiêu**, không phải một flag “build everything”.

## 9. Thực nghiệm 2: aggregator goal help:effective-pom

Dùng một plugin goal được tài liệu chính thức đánh dấu aggregator:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

Đặc điểm:

- `help:effective-pom` có thuộc tính **Executes as an aggregator goal**.
- Khi gọi trực tiếp từ root của reactor trong Maven 3, đây là **một aggregator goal invocation**, khác với `dependency:tree` per-project.
- Nội dung do plugin xuất ra có thể cung cấp effective POM/model với parent inheritance và active profiles; định dạng/vị trí output phụ thuộc option/phiên bản.
- Không kết luận “chỉ có một project được xử lý” chỉ vì goal được gọi một lần: aggregator có thể **đọc nhiều projects** trong reactor.

Bạn có thể chạy:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=org.apache.maven.plugins:maven-help-plugin:3.5.2 -Dgoal=effective-pom -Ddetail
```

Goal `help:describe` cũng là aggregator goal. Nó giúp tìm metadata và parameters của goal đích. Tuy nhiên output mô tả có thể không in đúng một dòng `aggregator=true` ở tất cả phiên bản; trang documentation HTML của từng goal (xem tài liệu tham khảo) là nguồn rõ ràng hơn.

### 9.1. Số lần gọi goal khác số module hiện diện trong report

Ví dụ `help:effective-pom` có thể ghi thông tin của nhiều modules trong một lần gọi, còn `dependency:tree` có thể tạo nhiều mục nhỏ trong terminal. Đừng dùng số dòng log hoặc số file đầu ra như thước đo duy nhất.

**Cần tách ba câu hỏi** khi điều tra:

1. **Execution count:** Maven gọi goal bao nhiêu lần?
2. **Input scope:** goal nhận ngữ cảnh module hiện tại hay tập reactor projects?
3. **Output layout:** goal tạo một file, nhiều file, một bảng hay console output?

Flag aggregator chủ yếu ảnh hưởng execution semantics; plugin implementation và cấu hình quyết định phần lớn input/output thực tế.

## 10. Thực nghiệm 3: thay đổi tập reactor bằng CLI flags

Các flags quan trọng:

| Flag | Tên dài | Công dụng |
| --- | --- | --- |
| `-pl` | `--projects` | Chọn project/module cần build |
| `-am` | `--also-make` | Thêm reactor dependencies của projects đã chọn |
| `-amd` | `--also-make-dependents` | Thêm các projects phụ thuộc vào project đã chọn |
| `-N` | `--non-recursive` | Chỉ xử lý project hiện tại, không recurse `<modules>` |
| `-rf` | `--resume-from` | Tiếp tục reactor từ một project chỉ định |
| `-T` | `--threads` | Build multi-module với parallel threads (khi phù hợp) |
| `-ff` | `--fail-fast` | Dừng sớm ở lỗi đầu tiên (thường là mặc định) |
| `-fae` | `--fail-at-end` | Tiếp tục các module có thể build rồi báo lỗi cuối |
| `-f` | `--file` | Chọn POM file đầu vào |

Thử từ root:

```bash
mvn -B -pl :core clean package
mvn -B -pl :app -am clean package
mvn -B -pl :core -amd clean package
mvn -N validate
```

**Phân tích:**

- `-pl :core`: chọn module `core`, không bắt buộc chạy `app`.
- `-pl :app -am`: chọn `app` và upstream reactor dependencies cần thiết, đặc biệt `core`.
- `-pl :core -amd`: chọn `core` và **dependents** của nó, trong ví dụ có `app`. Quan hệ build có thể cần thêm những project khác theo cấu trúc reactor.
- `-N`: chỉ root `pom` project, không xây `core`/`app`.

### 10.1. `-N` với aggregator goal không phải tổng hợp toàn dự án

```bash
mvn -N org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

Đây vẫn là **aggregator goal**, nhưng Maven đang ở **non-recursive build**. Tập reactor projects mà nó nhận bị giới hạn. Không thể chỉ nhìn tên goal `aggregate` rồi suy ra nó đã thấy mọi module trong repository.

Nếu muốn tổng hợp toàn reactor, hãy gọi từ root với tập modules đúng và không dùng `-N` hoặc `-pl` hạn chế ngoài chủ đích. Nếu chỉ cần báo cáo một nhóm modules, chọn nhóm phù hợp và kiểm tra cách plugin xử lý selection.

### 10.2. `-rf` không phải công tắc tự phục hồi đầy đủ

Ví dụ sau khi lỗi ở `app`:

```bash
mvn -rf :app package
```

`-rf` chọn nơi bắt đầu lại trong reactor; nó **không tự đảm bảo** những module cần thiết đã được build/install đúng và không tự phục hồi mọi artifact còn thiếu. Với module phụ thuộc vào `core`, nếu local repository chưa có `core` đúng version, có thể cần `-am` hoặc build/install prerequisites theo quy tắc Maven của version bạn đang dùng.

Maven 3 và Maven 4 có khác biệt về reactor/resume behaviors; đừng giả định mọi kết hợp `-rf`, `-pl`, `-am` đều cho kết quả giống nhau ở mọi bản Maven.

## 11. Nếu đang phát triển Maven plugin riêng

Đối với tác giả plugin, mỗi Maven goal thường là một Java class **Mojo**, với annotation `org.apache.maven.plugins.annotations.Mojo`.

**Fragment minh họa ý tưởng**, không phải một plugin hoàn chỉnh có POM/plugin descriptor/packaging:

```java
@Mojo(name = "summary", aggregator = true, threadSafe = false)
public final class SummaryMojo extends AbstractMojo {

    @Parameter(defaultValue = "${session}",
               readonly = true, required = true)
    private MavenSession session;

    @Override
    public void execute() throws MojoExecutionException {
        int selected = session.getProjects().size();
        getLog().info("Reactor projects available: " + selected);
    }
}
```

Các imports tương ứng (chỉ minh họa, không phải code tự chạy):

```java
import org.apache.maven.execution.MavenSession;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;
```

**Giải thích:**

- `name = "summary"` đăng ký goal `myplugin:summary` nếu class nằm trong một Maven plugin được đóng gói và phát hành đúng cách.
- `aggregator = true` là thông tin để Maven xử lý Mojo như aggregator trong **ngữ cảnh được hỗ trợ**.
- `session.getProjects()` lấy các MavenProjects được MavenSession ghi nhận; danh sách có thể khác nếu người dùng chọn subset reactor bằng `-pl` hoặc dùng `-N`.
- `threadSafe = false` **không** nói Mojo có thể chạy parallel an toàn; cờ này tách biệt với aggregator.
- Plugin cần dependency/plugin API, Maven plugin annotations, packaging và plugin descriptor generation đúng để chạy. Đoạn code chỉ giúp hình dung metadata, **không phải project Java 17 runnable độc lập**.

Muốn viết goal **per-module**, thường để `aggregator=false` (mặc định) và lấy `MavenProject` hiện tại bằng injection. Muốn goal tổng hợp thật, bạn phải **tự code logic đọc projects, kiểm tra/thu thập kết quả và tạo report**. Chỉ thêm annotation không sinh report.

### 11.1. Aggregator không đồng nghĩa thread-safe

Maven có thể chạy reactor với:

```bash
mvn -T 2 clean verify
```

Đây là ví dụ build parallel, không khuyến khích bật mặc định trước khi kiểm tra plugin compatibility. Các Mojos có metadata `threadSafe` mới tuyên bố hỗ trợ concurrent execution. Aggregator goal có thể cần quyền đọc/ghi reactor-wide và có thể làm các tác vụ khác chờ khóa để tránh race conditions; Maven 3 đã có các cảnh báo loại **aggregator mojo requires exclusive access** trong một số parallel builds.

**Không xem thông báo chờ lock như bằng chứng goal bị thực thi hai lần hoặc deadlock ngay lập tức.** Xem build logs, timeline, plugin metadata và thử tuần tự khi cần. Khi ghi chung một output directory từ nhiều modules, phải có chiến lược đồng bộ riêng.

## 12. Khi nào nên chạy report tổng hợp ở CI?

Một workflow an toàn và dễ hiểu cho Maven 3:

```bash
mvn -B clean verify
mvn -B org.apache.maven.plugins:maven-javadoc-plugin:3.12.0:aggregate
```

Lệnh đầu build/verify **các module đã chọn** theo reactor. Lệnh thứ hai mới gọi goal tổng hợp docs từ root. Cách tách này có ưu điểm:

1. Reports không chạy khi nhiều child modules còn chưa compile.
2. Dễ xác định **tập reactor** cho cả hai lệnh, tránh gọi ở một module con ngẫu nhiên.
3. Debug đơn giản: build lỗi ở bước 1 khác với Javadoc/report lỗi ở bước 2.
4. Không vô tình bind aggregator goal vào `verify` của mọi module chỉ vì parent POM inheritance.
5. Có thể lưu artifacts/caches/logs trước khi chạy docs.

**Giới hạn:** `javadoc:aggregate` có thể fork phase `compile`; nó cần JDK có Javadoc Tool, source Java hợp lệ và dependencies. Với site reports, cấu hình `reporting`/Site Plugin có đường chạy khác; đừng coi hai lệnh trên là cách duy nhất cho mọi tổ chức. Nếu pipeline có nhiều modules và muốn một report thật sự toàn reactor, cần xem **tài liệu đúng version của goal** và xác định nơi xuất output.

### 12.1. Nếu chỉ cần thông tin một module

Đừng dùng aggregator goal cho mọi tác vụ. Ví dụ muốn xem dependency của `app`:

```bash
mvn -pl :app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Muốn compile `core` và các module cần nó:

```bash
mvn -B -pl :app -am compile
```

Chọn đúng scope thường nhanh hơn và không tạo report dư. Nếu goal per-module có tham số output file, hãy bảo đảm đường dẫn **module-relative** như `${project.build.directory}` thay vì hardcode một đường dẫn chung cho mọi module.

### 12.2. Root-only lifecycle binding khi cần thiết

Một số build cần tác vụ **chỉ ở root**, nhưng không nhất thiết là aggregator goal. Có thể hạn chế inheritance:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-help-plugin</artifactId>
    <version>3.5.2</version>
    <inherited>false</inherited>
</plugin>
```

Đây là fragment POM, **không tự bind goal và không tự chạy**. Nếu thật sự bind một goal vào phase, cần thêm `<executions>` phù hợp và kiểm tra tác dụng ở root. `<inherited>false</inherited>` làm hạn chế kế thừa plugin config, **không** chuyển một goal thông thường thành aggregator hay tự dời execution đến cuối reactor.

### 12.3. Vì sao không dùng `mvn -N verify` rồi mong có report toàn reactor?

`-N` ngăn Maven đi vào modules. Nó thích hợp kiểm tra riêng root POM hoặc chạy một số thao tác root-only không cần artifacts khác, nhưng **không build children**. Nếu một report cần classes/JARs của `core` và `app`, cần đảm bảo chúng đã build ở bước trước và plugin có cơ chế truy cập chúng.

## 13. Những hiểu nhầm phổ biến

| Nhận định dễ sai | Thực tế |
| --- | --- |
| Root POM có `<modules>` thì mọi plugin goal chỉ chạy một lần | Không. Reactor và Mojo aggregator là hai khái niệm khác nhau |
| Goal aggregator luôn chạy đúng một lần trong mọi cách kích hoạt | Trong Maven 3, **direct CLI** và **lifecycle binding** có khác biệt |
| Bind aggregator goal vào root `verify` là chạy sau khi mọi child verify xong | Không. Root thường nằm đầu reactor order |
| `<inherited>false</inherited>` tự hoãn execution đến cuối reactor | Không. Nó ảnh hưởng inheritance, không phải timing |
| `dependency:tree` gộp tất cả module thành một dependency tree | Không. Goal cho dependency tree **của project** |
| `help:effective-pom` chỉ biết root POM vì gọi một lần | Không. Aggregator có thể nhìn/hiển thị nhiều project models |
| `-pl :app` và `-pl :app -am` là như nhau | Không. `-am` thêm reactor prerequisites |
| `-N` vẫn build toàn bộ `<modules>` | Không. Non-recursive chỉ xử lý project hiện tại |
| `pluginManagement` quyết định số lần goal được thực thi | Không. Nó quản lý cấu hình/version; invocation còn phụ thuộc binding/CLI |
| `aggregator=true` tự ghép các JAR modules thành fat JAR | Không. Đó là việc của plugin packaging/assembly/shade riêng |
| `threadSafe=true` nghĩa goal chạy một lần toàn reactor | Không. Thread safety độc lập với aggregation |
| `-T` luôn tăng tốc goals aggregator | Không. Locks, dependency order và goal compatibility có thể giới hạn |
| `pom` packaging không bao giờ chạy bất kỳ plugin nào | Sai. Root POM có default bindings/config/explicit goals phù hợp |
| Một goal có chữ “aggregate” trong tên thì metadata chắc aggregator | Cần kiểm tra docs của **goal version cụ thể** |
| Tất cả modules cùng khai báo parent thì automatically là reactor của root | Không. `<modules>` mới chọn reactor từ aggregator |
| Parent `<modules>` đảm bảo `app` tìm thấy class của `core` khi compile | Không. `app` phải khai báo dependency vào `core` |
| Goal aggregator bắt buộc sinh đúng một file report | Không. Output layout do plugin quyết định |
| `-rf` tự giải quyết mọi prerequisite bị thiếu | Không. Cần xem selection, versions, local repo và reactor |
| Report chạy vào `package` đảm bảo đã đọc artifacts mọi child | Không nếu project chứa execution chưa đợi các child package xong |
| Chỉ cần nhìn `[INFO]` rồi đếm dòng là biết goal chạy mấy lần | Log format khác nhau; cần hiểu reactor selection, Mojo descriptor và execution binding |

## 14. Quy trình chẩn đoán khi goal chạy thừa, thiếu hoặc sai thời điểm

### Bước 1 — Xác định phạm vi reactor

```bash
mvn -version
mvn -B validate
```

Quan sát `Reactor Build Order`/`Reactor Summary` nếu Maven in ra. Xem lệnh có `-N`, `-pl`, `-am`, `-amd`, `-rf`, `-f` hay profile thay đổi module set không.

### Bước 2 — Xem goal metadata

Mở tài liệu goal phiên bản đang dùng, đặc biệt:

- `Executes as an aggregator goal`
- `Binds by default to the lifecycle phase`
- `Requires a Maven project`
- `Requires dependency resolution`
- `The goal is thread-safe` hoặc không

Không đoán dựa vào tên plugin; ngay trong một plugin, các goals có thể khác nhau.

### Bước 3 — Xem invocation path

Goal được gọi **trực tiếp** bằng `mvn plugin:goal` hay được bind vào lifecycle trong POM? Nếu bị gọi lặp ở nhiều modules, tìm `<executions>` và plugin inheritance. Có khi user vừa bind goal vào `verify` **vừa gọi lại trực tiếp**, khiến hai đường thực thi cùng hoạt động.

### Bước 4 — Kiểm tra effective POM của module

```bash
mvn -pl :app org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

Đọc phần `<build><plugins>` và `<executions>` của module. Khi mục tiêu là điều tra inheritance, xem POM hiệu lực riêng của root, `core`, `app` và so sánh execution IDs/phases. Không chỉ nhìn POM root rồi suy ra tất cả children giống nhau.

### Bước 5 — Kiểm tra timing và artifacts

Nếu goal tổng hợp báo không tìm thấy outputs, xác minh:

```text
core/target/core-1.0.0.jar
app/target/app-1.0.0.jar
```

Nếu các file này chưa được tạo khi aggregator root `verify` chạy, vấn đề có thể là **thời điểm gọi**, không phải Java compiler error. Cân nhắc tách `clean verify` và aggregator CLI thành hai bước.

### Bước 6 — Xác định scope của report/output

Nếu report bị ghi đè hoặc kết quả của nhiều modules vào cùng một đường dẫn:

- Tác vụ per-module nên dùng output dưới module `${project.build.directory}`.
- Tác vụ tổng hợp cần thư mục báo cáo riêng và quy tắc ghi file để tránh race/overwrite.
- Với parallel `-T`, xem thread-safety và giới hạn khóa của plugin.
- Đừng tắt kiểm tra lỗi hoặc bỏ qua modules để làm report “đủ xanh”.

## 15. Bài tự kiểm tra

**Câu 1.** Root POM có `<modules>core,app</modules>`. Nếu gọi `mvn dependency:tree`, có nghĩa một dependency tree chung của cả project?  
**Đáp án:** Không. `dependency:tree` là goal theo project; nó tạo kết quả trong ngữ cảnh từng reactor project được chọn.

**Câu 2.** `help:effective-pom` được docs đánh dấu aggregator. Gọi trực tiếp từ root reactor Maven 3 có điểm gì khác?  
**Đáp án:** Đây là một aggregator goal invocation thay vì một execution trên mỗi module.

**Câu 3.** Nếu goal `aggregator=true` được bind vào `verify` trong parent POM, có luôn chỉ chạy đúng một lần?  
**Đáp án:** Không. Lifecycle binding có thể chạy ở từng module nhận execution. `aggregator=true` không tự ngăn kế thừa/lặp.

**Câu 4.** Đặt `<inherited>false</inherited>` vào plugin config có đảm bảo aggregator chạy sau các child build không?  
**Đáp án:** Không. Nó hạn chế inheritance; timing vẫn theo phase của project chứa execution.

**Câu 5.** Nếu CI cần aggregated Javadoc từ classes mọi modules, chọn workflow nào dễ hiểu ở Maven 3?  
**Đáp án:** Build/verify toàn reactor trước; sau đó gọi `javadoc:aggregate` trực tiếp ở một invocation riêng từ root.

**Câu 6.** `-pl :app -am` khác `-pl :app` như thế nào?  
**Đáp án:** `-am` thêm reactor prerequisites của `app`, gồm `core` trong bài ví dụ.

**Câu 7.** Dùng `-N` ở root rồi gọi aggregator goal, có chắc đọc tất cả child projects không?  
**Đáp án:** Không. `-N` chọn non-recursive reactor, giới hạn tập projects mà goal nhìn thấy.

**Câu 8.** Root `packaging=pom` có tự tạo một JAR chứa `core` và `app` không?  
**Đáp án:** Không. Mỗi JAR module đóng gói riêng; cần assembly/shade hoặc công cụ phù hợp nếu muốn artifact kết hợp.

**Câu 9.** `threadSafe` và `aggregator` có cùng nghĩa không?  
**Đáp án:** Không. Thread-safe nói về concurrent execution; aggregator nói về reactor/multi-project execution semantics.

**Câu 10.** App import `Greeter` nhưng chỉ có root `<modules><module>core</module>...`. Vì sao compile có thể lỗi?  
**Đáp án:** Vì `<modules>` không tự thêm `core` vào app classpath; `app/pom.xml` cần `<dependency>` tới `core`.

**Câu 11.** `-pl :core -amd` có nghĩa gì?  
**Đáp án:** Chọn `core` và các reactor modules phụ thuộc vào `core`, trong ví dụ có `app`.

**Câu 12.** Một aggregator goal sinh nhiều file HTML. Có phải chắc chắn Maven đã gọi goal nhiều lần?  
**Đáp án:** Không. Output layout là quyết định của plugin; phải xác minh invocation count riêng.

## 16. Checklist khi thiết kế plugin execution trong multi-module

- [ ] Đã xác định **goal name + plugin version** trước khi đưa vào POM/CI.
- [ ] Đã đọc metadata **aggregator** của goal; không đoán từ tên.
- [ ] Đã phân biệt **gọi goal trực tiếp** và **gắn goal vào phase**.
- [ ] Đã biết root aggregator POM và parent POM có thể là cùng file nhưng là hai quan hệ độc lập.
- [ ] Đã xác định reactor selection từ `-pl`, `-am`, `-N`, `-rf`, `-f` và profiles.
- [ ] Đã xác minh `app` khai báo dependency vào `core` thật sự.
- [ ] Goals per-module ghi output riêng mỗi module, không đè vào cùng một file vô ý.
- [ ] Aggregated report chỉ chạy khi dữ liệu mọi module cần đọc đã sẵn sàng.
- [ ] Không dùng `aggregator=true` làm thay thế cho việc tự code logic tổng hợp report.
- [ ] Nếu binding ở parent, đã kiểm tra inheritance và execution count ở children.
- [ ] Với CI Maven 3, ưu tiên **hai invocation** cho build rồi report khi timing quan trọng.
- [ ] Không bật `-T` trước khi kiểm tra goal thread safety và locking.
- [ ] `help:effective-pom`, `dependency:tree` và logs được kiểm tra trên cùng bộ flags.
- [ ] Kiểm tra Maven 3/4 version để tránh suy diễn các tính năng lifecycle/reactor khác thế hệ.
- [ ] Chạy build Java 17 đầy đủ và xác nhận stdout `app -> Hello from core`.

## 17. Tài liệu chính thức để đào sâu

1. [Apache Maven — Guide to Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
2. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
3. [Apache Maven — Introduction to the POM: Aggregation và Inheritance](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
4. [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
5. [Apache Maven Help Plugin — help:effective-pom, goal aggregator](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
6. [Apache Maven Help Plugin — help:describe, goal aggregator](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
7. [Apache Maven Dependency Plugin — dependency:tree, goal theo project](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
8. [Apache Maven Javadoc Plugin — javadoc:aggregate, goal aggregator](https://maven.apache.org/plugins/maven-javadoc-plugin/aggregate-mojo.html)
9. [Apache Maven — Maven Plugin Descriptor / aggregator Metadata](https://maven.apache.org/ref/4-LATEST/compat/maven-plugin-api/plugin.html)
10. [Apache Maven — Aggregator Plugins historical design](https://cwiki.apache.org/confluence/spaces/MAVENOLD/pages/9798429/Aggregator%2BPlugins)
11. [Apache Maven JIRA — MNG-6336: Aggregator Mojo in lifecycle](https://issues.apache.org/jira/browse/MNG-6336)
12. [Apache Maven — Maven 4 Multiple Subprojects Guide](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html)
13. [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)

**Ghi nhớ cuối bài:** Trong Maven 3, `aggregator=true` của một Mojo giúp goal được gọi **một lần khi direct CLI trên reactor**. Nhưng lifecycle binding, inheritance, reactor selection và thời điểm build của từng project vẫn quyết định điều gì thật sự xảy ra. Muốn báo cáo tổng hợp sau khi mọi module build xong, hãy thiết kế **đúng cả phạm vi lẫn thời điểm**, không chỉ trông vào tên `aggregate`.
