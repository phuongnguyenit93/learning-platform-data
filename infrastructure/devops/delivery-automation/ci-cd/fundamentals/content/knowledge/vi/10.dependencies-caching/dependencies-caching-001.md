# Phân biệt phụ thuộc trực tiếp, phụ thuộc bắc cầu và công cụ build

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt phụ thuộc trực tiếp (direct dependency), phụ thuộc bắc cầu (transitive dependency) và công cụ build (build tool).
- Đọc đồ thị phụ thuộc để biết thư viện nào được khai báo trực tiếp, thư viện nào được kéo vào gián tiếp và vì sao một phiên bản được chọn.
- Hiểu rằng một công cụ build có thể có các phụ thuộc riêng, nhưng không mặc nhiên là thư viện runtime của ứng dụng.
- Chọn đúng scope hoặc configuration cho dependency theo nơi nó được sử dụng.
- Dùng các lệnh và báo cáo của Maven, Gradle hoặc hệ sinh thái khác để điều tra dependency.
- Quản lý phiên bản, lockfile, repository, cache và bằng chứng chuỗi cung ứng trong CI/CD.

## 1. Vì sao cần phân biệt ba khái niệm?

Một dự án phần mềm hiếm khi chỉ gồm mã nguồn do đội ngũ viết. Để biên dịch, kiểm thử, đóng gói và chạy ứng dụng, dự án sử dụng thư viện, plugin, compiler, test runner, công cụ đóng gói và nhiều thành phần khác. Các thành phần này tạo thành một đồ thị phụ thuộc có thể khá lớn.

Nếu không phân biệt rõ các loại thành phần, đội ngũ dễ gặp một số vấn đề:

- Khai báo một thư viện ở sai scope khiến nó xuất hiện trong runtime package dù chỉ dùng để kiểm thử.
- Một thư viện bắc cầu có lỗ hổng nhưng không ai biết ứng dụng đang sử dụng nó.
- Nâng phiên bản một thư viện trực tiếp làm thay đổi nhiều thư viện gián tiếp và gây lỗi tương thích.
- Nhầm Maven hoặc Gradle với thư viện của ứng dụng, dẫn đến quản lý sai phạm vi và đánh giá sai bề mặt tấn công.
- Cache build bị coi là nguồn dữ liệu chuẩn, khiến pipeline phụ thuộc vào trạng thái cũ hoặc không thể tái tạo kết quả.

Ba khái niệm này trả lời ba câu hỏi khác nhau:

| Khái niệm | Câu hỏi cần trả lời |
|---|---|
| Direct dependency | Dự án chủ động khai báo và phụ thuộc trực tiếp vào thành phần nào? |
| Transitive dependency | Thành phần nào được đưa vào vì một dependency khác cần nó? |
| Build tool | Công cụ nào điều phối việc biên dịch, kiểm thử, đóng gói và tạo artifact? |

Chúng có liên quan nhưng không phải ba cấp độ của cùng một loại đối tượng. Direct và transitive mô tả quan hệ trong đồ thị phụ thuộc. Build tool mô tả vai trò của công cụ trong quá trình tạo phần mềm. Một build tool hoặc plugin cũng có thể có dependency riêng, nhưng điều đó không biến nó thành thư viện runtime của ứng dụng.

## 2. Direct dependency: phụ thuộc mà dự án khai báo trực tiếp

Một direct dependency là thư viện hoặc module được dự án khai báo rõ ràng trong cấu hình quản lý phụ thuộc vì mã nguồn hoặc quy trình của dự án cần sử dụng nó.

Ví dụ, một dịch vụ Java có thể khai báo:

- Spring Web để cung cấp HTTP endpoint.
- Jackson để chuyển đổi JSON nếu mã nguồn sử dụng trực tiếp API của Jackson.
- PostgreSQL JDBC driver để kết nối cơ sở dữ liệu.
- JUnit để viết và chạy kiểm thử.
- Một thư viện logging để ghi log từ mã ứng dụng.

Việc khai báo trực tiếp thể hiện ý định của dự án. Khi dependency được nâng cấp, thay thế hoặc loại bỏ, đội ngũ có thể xem xét thay đổi đó như một phần của hợp đồng kỹ thuật mà ứng dụng đang sử dụng.

Một dependency nên được khai báo trực tiếp nếu mã nguồn hoặc cấu hình của chính dự án phụ thuộc vào API hay hành vi của nó. Ví dụ, nếu code import một lớp từ thư viện A, dự án nên khai báo A trực tiếp ngay cả khi một thư viện B hiện tại cũng kéo A vào gián tiếp.

Không nên dựa vào việc một thư viện tình cờ xuất hiện trong đồ thị bắc cầu để sử dụng API của nó. Nếu dependency B thay đổi và không còn kéo A vào, dự án có thể không biên dịch được. Đây là dạng phụ thuộc ngầm (undeclared dependency), khó bảo trì và dễ vỡ khi nâng cấp.

### 2.1. Direct dependency không đồng nghĩa với dependency runtime

Một dependency trực tiếp có thể chỉ dùng trong lúc kiểm thử hoặc build. Ví dụ JUnit thường là dependency trực tiếp của dự án nhưng không cần được đóng gói trong ứng dụng production.

Do đó, cần phân biệt hai trục:

- **Quan hệ:** trực tiếp hay bắc cầu.
- **Phạm vi sử dụng:** compile, runtime, test, build hoặc một configuration cụ thể.

Một dependency có thể là trực tiếp và chỉ dùng cho test; một dependency bắc cầu có thể cần thiết ở runtime. Không nên suy luận scope từ việc dependency là direct hay transitive.

## 3. Transitive dependency: phụ thuộc được kéo vào gián tiếp

Một transitive dependency là thành phần được đưa vào đồ thị phụ thuộc vì một dependency khác khai báo rằng nó cần thành phần đó.

Giả sử dự án khai báo thư viện A. A cần thư viện B, còn B cần thư viện C. Đồ thị có dạng:

~~~mermaid
flowchart TD
    APP["Ứng dụng của dự án"] --> A["A: direct dependency"]
    A --> B["B: transitive dependency"]
    B --> C["C: transitive dependency"]
~~~

Dự án chỉ khai báo A, nhưng quá trình phân giải dependency có thể đưa cả B và C vào classpath hoặc package cuối cùng tùy theo scope và cách đóng gói.

Ví dụ thực tế:

- Ứng dụng khai báo framework web.
- Framework web kéo theo thư viện HTTP, JSON hoặc logging.
- Các thư viện này lại cần những module tiện ích khác.

Đội ngũ có thể không trực tiếp gọi API của B hoặc C, nhưng ứng dụng vẫn chịu ảnh hưởng từ phiên bản, tính tương thích và lỗ hổng của chúng.

### 3.1. Vì sao transitive dependency vẫn cần được quản lý?

Có bốn lý do chính:

1. **Tính tương thích:** phiên bản B hoặc C được chọn có thể không tương thích với phiên bản A hoặc với JDK mà ứng dụng sử dụng.
2. **Bảo mật:** lỗ hổng trong một thư viện bắc cầu vẫn có thể ảnh hưởng đến ứng dụng.
3. **Kích thước và hiệu năng:** một nhánh phụ thuộc lớn có thể làm tăng kích thước artifact, thời gian khởi động hoặc số lượng thành phần cần tải.
4. **Tính ổn định:** thay đổi dependency ở cấp A có thể làm thay đổi toàn bộ nhánh B và C dù mã ứng dụng không sửa trực tiếp.

Không nên xem thư viện bắc cầu là thành phần “không phải trách nhiệm của mình”. Đội ngũ vẫn cần biết chúng tồn tại, phiên bản nào được chọn và liệu có vấn đề cần xử lý hay không.

### 3.2. Đồ thị thực tế có thể có nhiều nhánh

Trong dự án lớn, nhiều dependency trực tiếp có thể cùng kéo một thư viện bắc cầu. Ví dụ A và D đều cần C nhưng yêu cầu các phiên bản khác nhau.

~~~mermaid
flowchart TD
    APP["Ứng dụng"] --> A["A: direct"]
    APP --> D["D: direct"]
    A --> B["B: transitive"]
    B --> C1["C: phiên bản yêu cầu 1"]
    D --> C2["C: phiên bản yêu cầu 2"]
~~~

Build tool hoặc dependency resolver phải áp dụng quy tắc phân giải để chọn phiên bản, hoặc báo xung đột nếu không thể tạo đồ thị hợp lệ. Quy tắc cụ thể phụ thuộc vào hệ sinh thái và cấu hình.

Điều quan trọng là không nên đoán phiên bản cuối cùng chỉ bằng cách đọc một dòng khai báo trong file cấu hình. Cần xem báo cáo dependency sau khi resolver thực sự chạy.

## 4. Build tool là gì và khác dependency như thế nào?

Build tool là công cụ điều phối các bước biến mã nguồn và tài nguyên đầu vào thành đầu ra có thể kiểm thử hoặc triển khai. Các nhiệm vụ phổ biến gồm:

- Phân tích cấu trúc dự án và cấu hình.
- Tải và phân giải dependency.
- Biên dịch mã nguồn.
- Chạy unit test và các tác vụ kiểm thử được cấu hình.
- Xử lý tài nguyên, sinh mã hoặc chạy annotation processor.
- Đóng gói JAR, WAR, package hoặc artifact khác.
- Tạo báo cáo, kiểm tra chất lượng và publish artifact.

Trong hệ sinh thái Java, các build tool phổ biến gồm:

- **Maven:** mô tả project, dependency và lifecycle trong POM; thực hiện các phase thông qua plugin.
- **Gradle:** định nghĩa build bằng DSL, task và configuration; hỗ trợ plugin và dependency resolution.
- **Ant:** công cụ build dựa trên task, thường gặp trong các dự án cũ hoặc quy trình tùy biến.

Build tool thường chạy trên máy lập trình viên hoặc CI runner. Nó có thể tải plugin, compiler, thư viện và công cụ hỗ trợ để thực hiện build. Những thành phần đó thuộc môi trường hoặc đồ thị phụ thuộc của quá trình build.

Cần phân biệt các lớp sau:

| Thành phần | Vai trò | Có mặc nhiên nằm trong runtime artifact không? |
|---|---|---|
| Maven hoặc Gradle | Điều phối build | Không |
| Maven/Gradle plugin | Thêm tác vụ hoặc hành vi cho build | Không |
| JDK compiler | Biên dịch mã nguồn | Không |
| Annotation processor | Sinh hoặc xử lý mã trong build | Không, trừ khi ứng dụng còn cần thư viện tương ứng ở runtime |
| JUnit hoặc test framework | Chạy kiểm thử | Thường không |
| Thư viện ứng dụng | Cung cấp chức năng khi ứng dụng chạy | Có thể, tùy cách đóng gói và scope |
| Runtime framework | Cung cấp nền tảng thực thi ứng dụng | Thường có |

Build tool có thể có dependency riêng của nó. Ví dụ một plugin Maven cần thư viện nội bộ để chạy. Những dependency này thuộc classloader hoặc môi trường của plugin, không tự động trở thành dependency của ứng dụng.

Tuy nhiên, ranh giới có thể phức tạp hơn khi plugin sinh mã, đóng gói thư viện hoặc thêm thành phần vào artifact. Vì vậy, cần kiểm tra cả cấu hình plugin lẫn nội dung đầu ra thay vì giả định mọi thứ được tải trong build đều bị loại khỏi runtime.

## 5. Ba trục cần phân biệt khi đọc cấu hình

Khi xem file pom.xml hoặc build.gradle, hãy xác định ba trục độc lập:

| Trục | Các câu hỏi |
|---|---|
| Quan hệ dependency | Thành phần được khai báo trực tiếp hay được kéo vào gián tiếp? |
| Scope / configuration | Thành phần cần ở compile, runtime, test, annotation processing hay build plugin? |
| Nơi thực thi | Thành phần chạy trong ứng dụng, trong test runner, trong build process hay trên CI runner? |

Ví dụ:

- JUnit: direct dependency, test scope, chạy trong test process.
- Jackson: có thể là direct dependency, compile/runtime tùy ứng dụng, được sử dụng trong ứng dụng.
- Một module logging do framework kéo vào: transitive dependency, runtime scope, chạy cùng ứng dụng.
- Maven Surefire Plugin: plugin build, chạy để điều phối test; dependency riêng của plugin không mặc nhiên thuộc runtime graph.
- JDK: toolchain của môi trường build và runtime tùy kiến trúc triển khai; không nên xem JDK compiler là một thư viện ứng dụng thông thường.

Cách phân loại này giúp tránh lỗi như đóng gói JUnit vào production, thiếu driver ở runtime hoặc nâng một plugin build rồi tưởng rằng dependency ứng dụng cũng đã được nâng.

## 6. Cách khai báo dependency trong Maven

Maven dùng phần dependencies trong POM để khai báo dependency của project. Ví dụ:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.4.0</version>
  </dependency>

  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.0</version>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Trong ví dụ:

- Starter web là dependency được project khai báo trực tiếp.
- JUnit là dependency trực tiếp nhưng chỉ dùng cho test.
- Các thư viện mà starter web kéo vào là dependency bắc cầu nếu project không khai báo chúng trực tiếp.

Phiên bản trong ví dụ chỉ nhằm minh họa cấu trúc. Dự án thực tế nên chọn phiên bản phù hợp với BOM, framework, JDK và chính sách cập nhật của đội ngũ.

### 6.1. Scope trong Maven

Scope quyết định dependency được dùng ở giai đoạn nào và có được truyền tiếp cho project phụ thuộc hay không.

| Scope | Compile | Runtime | Test | Ghi chú |
|---|---:|---:|---:|---|
| compile | Có | Có | Có | Mặc định; thường được truyền theo dependency graph |
| provided | Có | Không theo runtime classpath thông thường | Có | Môi trường chạy được kỳ vọng cung cấp |
| runtime | Không cần cho compile source chính | Có | Có | Ví dụ driver chỉ cần lúc chạy |
| test | Không | Không | Có | Chỉ phục vụ kiểm thử |
| system | Có | Không theo runtime classpath thông thường | Có | Tương tự provided nhưng lấy JAR từ đường dẫn cục bộ; không truyền bắc cầu, khó tái lập và nên tránh |

Scope không thay thế quan hệ direct/transitive. Một dependency khai báo trực tiếp với scope test vẫn là direct dependency. Một dependency compile được kéo vào bởi starter vẫn có thể là transitive dependency.

### 6.2. Plugin trong Maven được khai báo riêng

Plugin thường nằm trong phần build/plugins:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>21</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Maven Compiler Plugin điều khiển việc biên dịch. Nó không phải thư viện mà code ứng dụng cần import để xử lý request. Plugin có thể có dependency của riêng nó và chạy trong Maven process.

Không nên đặt plugin vào phần dependencies chỉ vì nó cần thiết để build. Tương tự, không nên khai báo thư viện runtime trong phần plugin chỉ vì build tool tải được nó.

## 7. Cách khai báo dependency trong Gradle

Gradle dùng configurations để xác định dependency cần ở giai đoạn nào. Với plugin Java, một số configuration phổ biến là:

| Configuration | Ý nghĩa |
|---|---|
| implementation | Dependency dùng để biên dịch và triển khai nội bộ module |
| api | Dependency là một phần API công khai mà consumer cần thấy |
| compileOnly | Cần khi compile nhưng không được đưa vào runtime classpath thông thường |
| runtimeOnly | Chỉ cần khi chạy |
| testImplementation | Dùng khi biên dịch và chạy test |
| testRuntimeOnly | Chỉ cần khi chạy test |
| annotationProcessor | Dùng trong quá trình xử lý annotation và sinh mã |

Ví dụ:

~~~kotlin
plugins {
    java
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web:3.4.0")
    runtimeOnly("org.postgresql:postgresql:42.7.4")

    testImplementation("org.junit.jupiter:junit-jupiter:5.11.0")
    annotationProcessor("org.projectlombok:lombok:1.18.36")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Trong ví dụ:

- Starter web là dependency trực tiếp của ứng dụng.
- PostgreSQL driver được khai báo trực tiếp nhưng chỉ cần ở runtime.
- JUnit được khai báo trực tiếp cho test.
- Lombok annotation processor được dùng trong build để xử lý annotation.

Lombok còn có thể cần một dependency compileOnly tương ứng để IDE và compiler hiểu annotation trong source. Đây là ví dụ cho thấy một thư viện có thể tham gia ở nhiều configuration khác nhau tùy vai trò.

### 7.1. Plugin Gradle là một lớp cấu hình khác

Gradle plugin có thể được khai báo trong block plugins:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.4.0"
    id("io.spring.dependency-management") version "1.1.7"
}
~~~

Plugin mở rộng khả năng của build, thêm task hoặc áp dụng cấu hình. Plugin có thể tải dependency riêng để hoạt động. Những dependency đó thuộc build logic, không mặc nhiên là dependency runtime của ứng dụng.

Với build logic phức tạp, Gradle còn có thể dùng buildSrc hoặc included build để tách logic dùng chung. Những phần này cần được quản lý phiên bản và kiểm tra bảo mật như mã build của dự án.

## 8. Vì sao cần xem đồ thị dependency thực tế?

File cấu hình chỉ thể hiện những dependency được khai báo trực tiếp và một phần quy tắc quản lý phiên bản. Nó không luôn cho thấy toàn bộ dependency cuối cùng mà ứng dụng sử dụng.

Một resolver có thể:

- Chọn phiên bản theo quy tắc mediation hoặc conflict resolution.
- Loại bỏ dependency theo exclusion.
- Áp dụng dependency constraint hoặc BOM.
- Chọn variant phù hợp với attribute hoặc platform.
- Áp dụng scope/configuration và dependency substitution.
- Nhận dependency từ plugin hoặc build logic riêng.

Do đó, khi điều tra cần xem kết quả sau khi build tool phân giải.

### 8.1. Maven

Một số lệnh hữu ích:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dverbose
mvn dependency:tree -Dincludes=org.example:library-name
mvn help:effective-pom
~~~

- dependency:tree hiển thị cây phụ thuộc của project.
- verbose giúp xem thêm thông tin về các dependency bị bỏ qua hoặc xung đột tùy phiên bản plugin.
- includes giúp tập trung vào một groupId/artifactId.
- effective-pom hiển thị POM sau khi kế thừa parent, profile và cấu hình được áp dụng.

Maven sử dụng dependency mediation để quyết định phiên bản trong đồ thị. Khi có nhiều đường dẫn đến cùng artifact, thứ tự và độ gần của dependency có thể ảnh hưởng đến phiên bản được chọn. DependencyManagement và BOM giúp quản lý phiên bản nhất quán nhưng không đồng nghĩa với việc mọi dependency được thêm vào classpath.

### 8.2. Gradle

Các lệnh thường dùng:

~~~bash
./gradlew dependencies
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

- dependencies hiển thị đồ thị theo project hoặc configuration.
- dependencyInsight giải thích vì sao một dependency xuất hiện và quy tắc nào dẫn đến phiên bản được chọn.
- Chọn đúng configuration giúp tránh nhầm lẫn giữa compile, runtime và test.

Gradle có quy tắc conflict resolution riêng và hỗ trợ constraints, platforms, version catalogs, dependency locking và verification. Không nên suy luận kết quả Gradle bằng quy tắc của Maven.

### 8.3. Hệ sinh thái khác

Các hệ sinh thái khác cũng có công cụ xem đồ thị phụ thuộc:

~~~bash
npm ls --all
go mod graph
pipdeptree
~~~

Mỗi hệ sinh thái có cách khai báo trực tiếp, phân giải bắc cầu, lock phiên bản và xử lý scope riêng. Cần đọc đúng tài liệu của công cụ đang dùng, tránh áp dụng nguyên xi quy tắc Maven hoặc Gradle sang npm, Go hay Python.

## 9. Xung đột phiên bản và cách xử lý

Một xung đột phổ biến xảy ra khi hai dependency trực tiếp yêu cầu hai phiên bản khác nhau của cùng một thư viện bắc cầu.

Ví dụ:

~~~text
Ứng dụng
├── A 2.x
│   └── C 1.x
└── B 4.x
    └── C 2.x
~~~

Resolver cần chọn phiên bản C hoặc báo lỗi tùy hệ sinh thái và chính sách. Nếu chọn được một phiên bản, build vẫn có thể thành công nhưng ứng dụng có thể gặp lỗi runtime do API hoặc hành vi không tương thích.

Ví dụ, Maven thường dùng quy tắc nearest definition: đường dẫn có độ sâu gần project hơn được ưu tiên; nếu cùng độ sâu, thứ tự khai báo có thể quyết định. Gradle mặc định thường chọn phiên bản cao hơn khi xử lý xung đột phiên bản, nhưng constraints, platforms, rich version constraints hoặc resolution rules có thể thay đổi kết quả. Hãy xem báo cáo của chính resolver thay vì áp dụng một quy tắc chung cho mọi build tool.

Khi xử lý xung đột, nên đi theo trình tự:

1. Xác định dependency nào đưa từng phiên bản vào đồ thị.
2. Xác định phiên bản nào thực sự được chọn trong configuration bị lỗi.
3. Đọc compatibility matrix hoặc release notes của A, B và C.
4. Ưu tiên nâng cấp dependency trực tiếp để các nhánh tương thích với nhau.
5. Dùng BOM, platform hoặc dependency constraint để quản lý phiên bản nhất quán khi phù hợp.
6. Chỉ override dependency bắc cầu khi đã xác minh tương thích và có kiểm thử.
7. Chạy test trên đúng runtime classpath và xác minh artifact cuối cùng.

Không nên override một thư viện bắc cầu chỉ để làm báo cáo scan biến mất. Một bản vá bảo mật có thể cần thiết, nhưng phải xác nhận API tương thích, kiểm thử hành vi và ghi lại lý do chọn phiên bản.

### 9.1. Exclusion không phải cách sửa mặc định

Maven và Gradle cho phép loại bỏ một dependency bắc cầu. Exclusion hữu ích khi:

- Dependency không được sử dụng trong ứng dụng.
- Có một bản thay thế được quản lý trực tiếp.
- Một thành phần không tương thích cần được loại bỏ có chủ đích.

Tuy nhiên, loại bỏ dependency có thể làm thiếu lớp hoặc service mà thư viện khác kỳ vọng. Chỉ dùng exclusion sau khi hiểu đường phụ thuộc và kiểm thử các luồng liên quan.

## 10. Dependency management, BOM, constraints và lockfile

Có nhiều cơ chế giúp giữ phiên bản nhất quán, nhưng chúng giải quyết những vấn đề khác nhau.

**Dependency management hoặc BOM:** tập trung quy định phiên bản cho một nhóm thư viện tương thích. Maven có dependencyManagement và import BOM; Gradle có platforms hoặc version catalogs kết hợp constraints. BOM giúp giảm việc khai báo phiên bản rời rạc, nhưng không nhất thiết khóa toàn bộ đồ thị chính xác cho mọi lần build.

**Dependency constraints:** thể hiện phiên bản mong muốn, giới hạn hoặc quy tắc chọn phiên bản. Chúng hữu ích khi nhiều module cần dùng chung một thư viện.

**Lockfile / dependency locking:** ghi lại phiên bản đã được phân giải để những lần build sau có thể sử dụng cùng kết quả. Gradle hỗ trợ dependency locking. Các hệ sinh thái như npm và Go có lock/sum files riêng. Maven thường dùng BOM, dependencyManagement và các cơ chế bổ sung; không nên giả định mọi dự án Maven có một lockfile chuẩn được tạo tự động.

**Checksum và verification metadata:** giúp xác minh nội dung artifact tải về có khớp với giá trị đã tin cậy. Gradle dependency verification có thể kiểm tra checksum hoặc chữ ký theo cấu hình. Các hệ sinh thái khác có cơ chế checksum hoặc checksum database tương ứng.

Cần hiểu đúng:

- BOM giúp quản lý phiên bản theo một tập thư viện.
- Locking giúp cố định kết quả phân giải.
- Checksum/signature giúp xác minh nội dung tải về.
- SBOM giúp mô tả thành phần có trong artifact.
- Provenance giúp ghi nhận artifact được tạo từ nguồn và quy trình nào.

Không cơ chế nào thay thế hoàn toàn các cơ chế còn lại.

## 11. Bảo mật dependency trực tiếp và bắc cầu

Một lỗ hổng trong dependency bắc cầu có thể ảnh hưởng đến ứng dụng giống như lỗ hổng trong dependency trực tiếp. Vì vậy, kiểm tra bảo mật cần xét đồ thị đã phân giải và artifact cuối cùng.

Các rủi ro thường gặp:

- Dependency có lỗ hổng đã công bố.
- Package giả mạo tên gần giống package thật (typosquatting).
- Dependency confusion do cấu hình repository không rõ ràng.
- Artifact bị thay thế hoặc tải từ nguồn không tin cậy.
- Plugin build độc hại thực thi mã trong quá trình CI.
- Phiên bản cũ không còn được duy trì.
- Build script hoặc plugin có quyền truy cập secret quá rộng.

Một quy trình quản lý cơ bản nên gồm:

1. Chỉ định repository tin cậy và thứ tự ưu tiên rõ ràng.
2. Hạn chế khai báo repository tùy tiện trong từng module nếu tổ chức có chính sách tập trung.
3. Theo dõi dependency trực tiếp và bắc cầu bằng công cụ phù hợp.
4. Đánh giá cả plugin, build logic và toolchain.
5. Dùng checksum hoặc chữ ký khi hệ sinh thái hỗ trợ.
6. Ghi nhận SBOM và provenance theo yêu cầu của sản phẩm.
7. Cập nhật dependency có kế hoạch và chạy kiểm thử sau nâng cấp.
8. Giới hạn secret và quyền của CI job có nhiệm vụ resolve hoặc execute build.

Đừng chỉ quét thư viện runtime rồi bỏ qua plugin build. Plugin chạy trong CI có thể thực thi mã với quyền của runner, đọc workspace hoặc truy cập credential mà job được cấp.

## 12. Build tool và toolchain cũng cần được quản lý phiên bản

Kết quả build không chỉ phụ thuộc vào thư viện ứng dụng. Nó còn phụ thuộc vào:

- Phiên bản Maven hoặc Gradle.
- Phiên bản JDK và compiler.
- Phiên bản plugin.
- Hệ điều hành và kiến trúc runner.
- Biến môi trường và cấu hình build.
- Repository và dependency resolver.
- Các công cụ sinh mã hoặc đóng gói bên ngoài.

Nếu máy lập trình viên dùng JDK 21 nhưng CI dùng JDK 17, build có thể cho kết quả khác hoặc thất bại. Nếu phiên bản plugin thay đổi ngoài dự kiến, task hoặc artifact cũng có thể thay đổi.

Một số biện pháp thực tế:

- Dùng Maven Wrapper hoặc Gradle Wrapper để xác định phiên bản build tool.
- Khai báo Java toolchain để xác định JDK cần dùng.
- Cố định phiên bản plugin quan trọng.
- Khóa dependency theo khả năng của hệ sinh thái.
- Ghi nhận phiên bản runner, toolchain và build parameters.
- Dùng container build image có phiên bản rõ ràng nếu phù hợp.
- Tránh tải và thực thi script build không được kiểm chứng từ nguồn tùy ý.

Wrapper giúp chuẩn hóa build tool nhưng không tự đảm bảo mọi dependency, plugin hoặc JDK đều bất biến. Cần quản lý từng lớp riêng.

## 13. Cache dependency không thay thế dependency management

Cache trong CI/CD thường lưu các file đã tải hoặc kết quả build để giảm thời gian chạy. Ví dụ Maven local repository, Gradle dependency cache hoặc cache của package manager có thể được tái sử dụng giữa các lần chạy.

Cache là tối ưu hiệu năng, không phải nguồn sự thật về phiên bản dependency.

Một cache key tốt thường gắn với:

- Hệ điều hành hoặc kiến trúc runner khi nội dung phụ thuộc vào chúng.
- Phiên bản JDK và build tool.
- File khai báo dependency hoặc lockfile.
- Cấu hình repository và các tham số ảnh hưởng đến resolution.
- Phiên bản schema cache nếu cấu trúc lưu trữ thay đổi.

Nếu cache key quá rộng, pipeline có thể tái sử dụng dữ liệu không phù hợp. Nếu quá hẹp, cache gần như không có tác dụng.

Cần nhớ:

- Không dùng cache để thay thế lockfile hoặc version pinning.
- Không coi cache là kho artifact phát hành.
- Không chia sẻ cache ghi được giữa các job hoặc nhánh không cùng mức tin cậy nếu có rủi ro đầu độc cache.
- Có chiến lược làm mới hoặc xóa cache khi dependency, toolchain hoặc cấu hình thay đổi.
- Build vẫn phải xác minh dependency theo chính sách dù dữ liệu được lấy từ cache.

Cache có thể chứa file tải từ repository và script được thực thi trong build. Vì vậy, quyền ghi và đọc cache cũng là một phần của chuỗi cung ứng phần mềm.

## 14. Quy trình quản lý dependency trong CI/CD

Một luồng tham khảo cho dự án Java:

~~~mermaid
flowchart TD
    A["Thay đổi POM / Gradle build"] --> B["Review khai báo direct dependencies"]
    B --> C["Resolve dependency graph"]
    C --> D["Kiểm tra phiên bản và lock/constraints"]
    D --> E["Dependency vulnerability scan"]
    E --> F{"Policy đạt?"}
    F -- "Không" --> X["Chặn build hoặc yêu cầu waiver"]
    F -- "Có" --> G["Compile và test"]
    G --> H["Package artifact"]
    H --> I["Tạo SBOM / provenance nếu cần"]
    I --> J["Publish artifact bất biến"]
~~~

Một pipeline có thể chia công việc thành các bước sau:

| Bước | Việc thực hiện | Bằng chứng |
|---|---|---|
| Review | Kiểm tra dependency trực tiếp mới, thay đổi scope và nguồn | Pull request review |
| Resolve | Phân giải toàn bộ graph theo cấu hình xác định | Dependency tree/report |
| Verify | Kiểm tra checksum, lock state hoặc repository policy | Verification result |
| Scan | Quét dependency trực tiếp và bắc cầu | Vulnerability report |
| Build | Biên dịch, test và package bằng toolchain được xác định | Test/build result |
| Inventory | Tạo SBOM hoặc danh sách thành phần khi cần | SBOM gắn artifact |
| Publish | Lưu artifact có digest và metadata | Artifact ID, digest, provenance |

Không nhất thiết mọi dự án phải tạo SBOM hoặc ký artifact ở cùng mức độ. Hãy chọn theo yêu cầu chuỗi cung ứng, mức độ nhạy cảm và chính sách phát hành. Nhưng dự án nào cũng cần biết dependency nào được resolve và build tool nào đã tạo artifact.

## 15. Những dấu hiệu dependency đang được quản lý chưa tốt

| Dấu hiệu | Rủi ro | Cách điều tra |
|---|---|---|
| Code import thư viện không khai báo trực tiếp | Phụ thuộc ngầm vào dependency bắc cầu | Tìm API được sử dụng và khai báo trực tiếp |
| Dependency chỉ dùng trong test nhưng xuất hiện ở runtime | Artifact thừa, tăng bề mặt tấn công | Kiểm tra scope/configuration và package |
| Không biết thư viện bắc cầu đến từ đâu | Khó đánh giá lỗ hổng và tương thích | Xem dependency tree hoặc insight |
| Nhiều phiên bản cùng xuất hiện trong graph | Có thể gây xung đột hoặc tăng kích thước | Xem đường dẫn và quy tắc resolution |
| Build máy local thành công nhưng CI thất bại | Khác toolchain, cache hoặc repository | So sánh wrapper, JDK, config và dependency graph |
| Build lúc được lúc không | Phiên bản động hoặc repository thay đổi | Kiểm tra dynamic version, lock và metadata |
| Plugin build dùng phiên bản không cố định | Kết quả build có thể thay đổi | Khai báo và kiểm soát phiên bản plugin |
| Chỉ scan direct dependencies | Bỏ sót lỗ hổng trong graph thực tế | Scan resolved graph và artifact |
| Cache dùng chung giữa các nhánh không tin cậy | Nguy cơ cache poisoning hoặc rò rỉ | Phân vùng cache theo mức tin cậy và quyền ghi |
| Nâng dependency mà không có kiểm thử | Lỗi tương thích ở compile hoặc runtime | Chạy test theo scope và kiểm tra artifact |

## 16. Ví dụ thực hành: điều tra một dependency bắc cầu

Giả sử một ứng dụng Java khai báo framework web và build thành công. Báo cáo bảo mật cho biết một phiên bản thư viện JSON có lỗ hổng. Trong POM không thấy thư viện đó được khai báo trực tiếp.

Cách điều tra:

1. Chạy dependency tree để tìm đường đi từ ứng dụng đến thư viện JSON.
2. Xác định dependency trực tiếp nào kéo thư viện đó vào.
3. Kiểm tra scope để biết nó xuất hiện trong compile, runtime hay test.
4. Xem phiên bản nào được resolver chọn và vì sao.
5. Kiểm tra phiên bản framework hoặc BOM có bản cập nhật tương thích không.
6. Nếu cần override, khai báo phiên bản có chủ đích ở dependencyManagement hoặc cơ chế tương ứng.
7. Chạy unit test, integration test và kiểm tra runtime package.
8. Chạy lại scan và lưu bằng chứng cho artifact mới.

Không nên thêm dependency JSON trực tiếp chỉ để ép resolver chọn phiên bản nếu chưa hiểu framework có yêu cầu tương thích nào. Nếu phải override tạm thời để xử lý lỗ hổng, hãy ghi rõ lý do, phạm vi ảnh hưởng, kiểm thử đã chạy và điều kiện loại bỏ override khi upstream cập nhật.

## 17. Checklist trước khi thêm hoặc nâng dependency

- [ ] Mã nguồn hoặc build logic thực sự cần dependency này.
- [ ] Đã xác định nó là dependency trực tiếp hay chỉ xuất hiện bắc cầu.
- [ ] Đã chọn đúng scope/configuration.
- [ ] Đã kiểm tra license và nguồn repository theo chính sách.
- [ ] Phiên bản tương thích với framework, JDK và các dependency liên quan.
- [ ] Đã xem dependency graph và xung đột phiên bản.
- [ ] Có lock, constraint hoặc cơ chế quản lý phiên bản phù hợp.
- [ ] Đã kiểm tra lỗ hổng của dependency trực tiếp và bắc cầu.
- [ ] Plugin và build logic liên quan cũng được đánh giá.
- [ ] Đã chạy test trên classpath/configuration tương ứng.
- [ ] Artifact cuối cùng không chứa thành phần test/build ngoài dự kiến.
- [ ] Cache không được dùng làm nguồn chuẩn cho dependency.
- [ ] Có thể truy vết artifact đến commit, toolchain và dependency graph.

## 18. Bài tập tự đánh giá

Một dịch vụ Java có cấu hình như sau:

~~~text
application
├── framework-web
│   ├── json-core
│   └── logging-api
├── database-driver
└── test-framework (test scope)
~~~

Đội ngũ phát hiện:

- Mã ứng dụng gọi trực tiếp API của json-core nhưng chỉ khai báo framework-web.
- Một báo cáo scan cho biết logging-api có lỗ hổng.
- Một developer thêm compiler plugin vào phần dependencies thay vì phần build plugins.
- Máy local dùng JDK 21 nhưng CI runner dùng JDK 17.
- Build CI đôi khi dùng cache cũ và cho kết quả khác với build sạch.

Hãy phân tích:

1. Thành phần nào là direct dependency, thành phần nào là transitive dependency?
2. Vì sao json-core nên được khai báo trực tiếp nếu code sử dụng API của nó?
3. logging-api cần được điều tra như thế nào nếu nó là dependency bắc cầu?
4. Vì sao compiler plugin thuộc cấu hình build?
5. Cần phân biệt scope/configuration của test framework với runtime dependency ra sao?
6. JDK và build tool cần được chuẩn hóa bằng cơ chế nào?
7. Cache key cần phản ánh những yếu tố nào?
8. Những bằng chứng nào cần lưu để truy vết artifact và dependency graph?

Một câu trả lời tốt cần phân loại đúng ba trục: quan hệ direct/transitive, scope sử dụng và nơi thành phần được thực thi. Sau đó mới đề xuất thay đổi cấu hình và kiểm thử phù hợp.

## Kết luận

Direct dependency thể hiện những thành phần dự án chủ động sử dụng; transitive dependency là những thành phần được kéo vào qua dependency khác; build tool điều phối quá trình biến mã nguồn thành artifact. Ba khái niệm này có quan hệ nhưng không thể thay thế cho nhau.

Quản lý CI/CD tốt cần kiểm soát cả đồ thị dependency đã phân giải, scope/configuration, phiên bản plugin và toolchain. Khi hiểu rõ thành phần nào chạy trong ứng dụng, thành phần nào chỉ phục vụ build và thành phần nào được kéo vào gián tiếp, đội ngũ có thể giảm phụ thuộc ngầm, phát hiện rủi ro bảo mật và tạo ra artifact ổn định, có thể truy vết.

