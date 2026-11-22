# Tọa độ Maven và quan hệ giữa phụ thuộc trực tiếp với phụ thuộc bắc cầu

## 1. Mục tiêu học tập

Trong một dự án Spring Boot, viết một dòng dependency tưởng như đơn giản có thể kéo theo hàng chục thư viện. Để build và đóng gói đúng, cần biết **đang yêu cầu thư viện nào**, **thư viện ấy đưa thêm những phụ thuộc nào vào dự án**, và **phiên bản cuối cùng được chọn theo quy tắc nào**.

Sau bài học, bạn có thể:

1. Đọc được tọa độ Maven theo `groupId:artifactId:version`, phân biệt tọa độ module với `scope`, `type`, `classifier` và nơi tải artifact.
2. Phân biệt phụ thuộc trực tiếp (**direct dependency**) với phụ thuộc bắc cầu (**transitive dependency**) theo góc nhìn của dự án hiện tại.
3. Đọc một dependency graph có nhiều đường dẫn đến cùng module, giải thích vì sao dependency được chọn hoặc bị loại.
4. Phân biệt **khai báo dependency** với **quản lý phiên bản qua BOM** và **kết quả resolve thực tế**.
5. Dùng Maven/Gradle để tìm đường dẫn kéo theo một thư viện, xác minh version được chọn, xác định compile/runtime/test classpath.
6. Tránh lỗi đóng gói thiếu dependency, xung đột version, sử dụng API của thư viện bắc cầu mà không khai báo trực tiếp.

**Phạm vi:** Đây là bài nền tảng của mục **Phụ thuộc và BOM** trong chủ đề **Spring Boot Build Tooling Packaging**. Trọng tâm là danh tính và quan hệ dependency. Quy trình phát hành artifact, bảo mật chuỗi cung ứng, kiểm thử và chiến lược nâng cấp framework sẽ chỉ được đề cập ở mức cần thiết để hiểu tác động đến build/packaging.

## 2. Tọa độ Maven là gì?

Trong hệ sinh thái Maven, một dependency thường được định danh bằng ba phần quan trọng:

~~~text
groupId : artifactId : version
~~~

Ví dụ:

~~~text
org.springframework.boot : spring-boot-starter-web : 3.3.5
com.fasterxml.jackson.core : jackson-databind : 2.17.2
org.slf4j : slf4j-api : 2.0.13
~~~

Các phiên bản trên chỉ minh họa cú pháp tọa độ, **không phải chỉ dẫn tự chọn phiên bản thủ công cho một ứng dụng Spring Boot**. Trong dự án thực tế, version có thể được quản lý tập trung bởi BOM hoặc platform.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `groupId` | Nhóm/tổ chức phát hành module trong hệ sinh thái artifact | `org.springframework.boot` |
| `artifactId` | Tên artifact/module trong group đó | `spring-boot-starter-web` |
| `version` | Phiên bản artifact được yêu cầu hoặc cuối cùng được chọn | `3.3.5` |
| `type` / extension | Kiểu artifact, thường mặc định `jar` đối với dependency Java thông thường | `jar`, `pom`, đôi khi `war` |
| `classifier` | Biến thể bổ sung, khi artifact xuất bản có classifier | `sources`, `javadoc`, classifier đặc thù nền tảng |
| `scope` / configuration | Quy định dependency dùng cho giai đoạn/classpath nào; đây là **quan hệ sử dụng**, không phải phần GAV | Maven `test`; Gradle `implementation` |

Điều quan trọng: tọa độ Maven **không phải** tên Java package. Một thư viện có groupId `org.apache.commons` hoàn toàn có thể chứa các package Java có cách đặt tên khác; cũng không nên suy đoán một artifact bằng cách nhìn riêng tên class.

Khi lưu vào Maven repository theo layout thông dụng, các thành phần tọa độ ánh xạ thành đường dẫn gần như:

~~~text
groupId dấu chấm đổi thành dấu / / artifactId / version / artifactId-version.jar
org/springframework/boot/spring-boot-starter-web/3.3.5/spring-boot-starter-web-3.3.5.jar
~~~

Ví dụ này mô tả **layout repository**, không cam kết mọi repository, classifier hay loại artifact đều có đường dẫn/đuôi giống hệt. Maven/Gradle còn đọc **POM và metadata** để biết dependencies, phạm vi, variant và các quy tắc khác. JAR chỉ là sản phẩm nhị phân; POM/metadata giúp build tool hiểu cách module liên kết với phần còn lại.

### 2.1. Tọa độ trong Maven POM

Khai báo Maven XML có dạng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <version>3.3.5</version>
    </dependency>
</dependencies>
~~~

Ở đây `groupId`, `artifactId` và `version` mô tả module muốn dùng. Khi `version` được quản lý bởi `dependencyManagement` hoặc BOM, có thể **bỏ version** trong chính dependency đó; điều kiện là có quản lý version thích hợp trong effective POM.

### 2.2. Cùng module trong Gradle

Với Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.5'
}
~~~

Chuỗi tọa độ `group:name:version` là một cách viết gọn. `implementation` là **configuration khai báo**, không nằm trong identity của module.

Với Kotlin DSL, tương đương:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web:3.3.5")
}
~~~

Gradle còn sử dụng Gradle Module Metadata, attributes và variants để chọn đúng thành phần của một module. Vì vậy, **giống GAV không có nghĩa mọi configuration luôn resolve một file hay tập dependency giống nhau**. Với Java application thông thường, mô hình jar/POM vẫn là nền tảng dễ bắt đầu nhất.

### 2.3. Phân biệt artifact dependency và plugin

Một dependency trong `dependencies` được dùng khi compile/chạy chương trình. Một **build plugin** thêm task và logic cho build, chẳng hạn `org.springframework.boot` trong Gradle `plugins` hoặc `spring-boot-maven-plugin` trong Maven `build/plugins`. Plugin có identity, version và dependency riêng, nhưng không vì tên giống thư viện runtime mà tự động xuất hiện trên classpath của ứng dụng.

## 3. Phụ thuộc trực tiếp và bắc cầu

Giả sử dự án `app` khai báo thư viện `B`, còn `B` khai báo thư viện `C`:

~~~text
app
 └── B       (trực tiếp đối với app)
      └── C  (bắc cầu đối với app; trực tiếp đối với B)
~~~

**Phụ thuộc trực tiếp (direct)** là quan hệ do dự án hiện tại chủ động khai báo trong build file. **Phụ thuộc bắc cầu (transitive)** là dependency đến từ metadata của một dependency khác (có thể qua nhiều cấp). Cách gọi “trực tiếp” hay “bắc cầu” **phụ thuộc vào điểm nhìn**: `C` trực tiếp đối với `B` nhưng là bắc cầu đối với `app`.

Một mô hình gần thực tế Spring Boot:

~~~text
Ứng dụng (app)
 └── org.springframework.boot:spring-boot-starter-web
      ├── org.springframework.boot:spring-boot-starter
      ├── org.springframework.boot:spring-boot-starter-json
      │    └── com.fasterxml.jackson.core:jackson-databind
      ├── org.springframework.boot:spring-boot-starter-tomcat
      ├── org.springframework:spring-web
      └── org.springframework:spring-webmvc
~~~

Sơ đồ đã **rút gọn** các cạnh, nhiều thư viện con và phiên bản, chỉ nhằm cho thấy vai trò của starter. Dependency graph thật có thể khác theo phiên bản Spring Boot, excludes, profiles, variants và cấu hình build.

Nếu `app` chỉ khai báo `spring-boot-starter-web`, đó là direct dependency. `jackson-databind` có thể đến thông qua `spring-boot-starter-json`, nên là transitive dependency của `app`. Nếu chính mã của `app` dùng `com.fasterxml.jackson.databind.ObjectMapper`, bạn đang sử dụng **API của thư viện bắc cầu**. Cách biên dịch ấy có thể thành công hôm nay, nhưng hợp đồng dependency của app lại chưa được diễn đạt rõ.

### 3.1. Vì sao build tool tự đi theo phụ thuộc bắc cầu?

Build tool đọc metadata của module được yêu cầu, tiếp tục xử lý các dependency có hiệu lực, xác định phiên bản phù hợp rồi tạo **resolved dependency graph** cho từng configuration/classpath. Không phải cứ module được đề cập trong POM là luôn được đưa vào mọi classpath; còn scope, optional, exclusion, platform, conflict resolution và variant selection.

Quy trình khái niệm:

~~~text
Khai báo trong app
      |
      v
Tìm module theo tọa độ ở repository
      |
      v
Đọc POM/metadata của module và các dependency được phép truyền
      |
      v
Tính graph + scope/configuration + version constraints/conflicts
      |
      v
Resolved classpath cho compile / runtime / test / task khác
      |
      v
Task compile, test, bootJar, image... sử dụng classpath thích hợp
~~~

Graph thực tế thường có nhiều đường dẫn cùng trỏ đến một module, không đơn thuần là cây không có nhánh gặp lại. Một dependency xuất hiện nhiều lần trong bản in graph không nhất thiết làm JAR ấy được đưa nhiều lần lên classpath.

### 3.2. Có nên khai báo trực tiếp mọi dependency bắc cầu?

**Không cần khai báo lặp tất cả thư viện nội bộ của một starter.** Lợi ích của starter là cung cấp một tập dependency phối hợp. Tuy nhiên:

- Nếu **source của app gọi trực tiếp API của thư viện X**, nên khai báo X là dependency trực tiếp, dù X hiện đang được một starter kéo vào. Điều này làm hợp đồng của app rõ ràng và tránh lỗi khi starter thay đổi dependency.
- Nếu X chỉ là chi tiết triển khai của thư viện Y và app không dùng API X, thường để Y quản lý quan hệ với X, tránh tạo pin version không cần thiết.
- Nếu X có vai trò runtime rõ ràng mà app trực tiếp cần (chẳng hạn JDBC driver), khai báo X bằng configuration/scope thích hợp, không chỉ hy vọng một nhánh khác kéo theo.
- Nếu cần kiểm soát version X vì tương thích hoặc lỗ hổng bảo mật, dùng BOM, dependency management, constraints hoặc khai báo có chủ đích rồi xác minh **resolved version**. Chỉ thêm một khai báo tùy tiện chưa bảo đảm mọi công cụ sẽ chọn đúng version mong muốn.

## 4. Ví dụ chạy được: Java 17, Maven và Jackson

Ví dụ dưới đây cố tình dùng `spring-boot-starter-web` để chứng minh thư viện bắc cầu có thể được Java source nhìn thấy trên compile classpath. Ta chưa cần chạy một Spring Boot HTTP server. Mục tiêu là quan sát **dependency graph**, rồi chuyển dependency thực sự được dùng trong mã thành **trực tiếp**.

**Điều kiện:** JDK 17+ và Maven có thể truy cập repository chứa dependencies; phiên bản Spring Boot `3.3.5` là phiên bản minh họa đã phát hành, không phải đề xuất phiên bản mới nhất. Đây là dự án Maven thông thường; **không cấu hình tạo executable Spring Boot JAR**.

Tạo cấu trúc:

~~~text
demo-dependency/
 ├── pom.xml
 └── src/
      └── main/
           └── java/
                └── demo/
                     └── Main.java
~~~

Nội dung `pom.xml` đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example.learning</groupId>
    <artifactId>demo-dependency</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>3.3.5</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích: `spring-boot-dependencies` được **import trong `dependencyManagement`**, nên nó cung cấp version quản lý cho starter và các thư viện liên quan. Import BOM **không tự thêm tất cả các thư viện đó** vào dự án. Dòng trong `dependencies` mới khai báo starter thực sự cần dùng.

Nội dung `src/main/java/demo/Main.java`:

~~~java
package demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public class Main {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        JsonNode json = mapper.readTree("{\"ready\":true}");
        System.out.println(json.path("ready").asBoolean());
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn compile exec:java -Dexec.mainClass=demo.Main
~~~

Kết quả do chính chương trình in ra:

~~~text
true
~~~

Maven có thể in thêm log download/plugin trước hoặc sau dòng đó; `true` là **stdout của `Main.main`**, không phải toàn bộ log Maven.

Tại sao compile được khi `pom.xml` chưa khai báo `jackson-databind`? Vì class `ObjectMapper` có trên compile classpath nhờ dependency bắc cầu theo starter. Kiểm tra:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Kết quả cụ thể sẽ có phiên bản, scope và các nhánh khác; không nên cố gán một cây dependency hoàn chỉnh khi chưa chạy lệnh trong môi trường thực tế.

**Bước cải thiện hợp đồng dependency:** vì `Main.java` **import trực tiếp** API Jackson, thêm vào **bên trong** `<dependencies>` của `pom.xml`:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
~~~

Maven BOM vẫn quản lý version; không cần chép một version Jackson bất kỳ. Sau khi thêm, Jackson trở thành dependency **trực tiếp** của app. Nó có thể vẫn tồn tại qua nhánh starter-web → starter-json, nhưng quan hệ app → Jackson đã được công khai. Chạy lại `mvn dependency:tree` để xác nhận version resolved thực tế.

**Lưu ý về packaging:** POM trên mặc định tạo JAR thường với lifecycle `package`; chưa thêm Spring Boot Maven plugin/repackage và main class Spring Boot. Vì vậy **không** suy ra có thể gọi `java -jar target/demo-dependency-1.0.0.jar` để khởi động server. Ví dụ này chứng minh đường đi dependency và compile/run bằng plugin exec, không minh họa đóng gói Boot executable archive.

## 5. Ví dụ tương đương với Gradle (Groovy DSL)

Để kiểm tra cùng graph bằng Gradle, có thể dùng `application` plugin thay vì bật toàn bộ packaging Spring Boot. Với file Java `src/main/java/demo/Main.java` giữ nguyên như mục 4, tạo `settings.gradle`:

~~~groovy
rootProject.name = 'demo-dependency'
~~~

Và `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}

application {
    mainClass = 'demo.Main'
}
~~~

`application` đã áp dụng Java plugin và thêm task chạy ứng dụng Java. `platform(...)` import BOM bằng hỗ trợ gốc của Gradle, giúp quản lý version; còn `implementation '...:spring-boot-starter-web'` là dependency trực tiếp. **Ví dụ không áp dụng plugin `org.springframework.boot`**, nên không có task `bootJar`.

Nếu dự án có Gradle Wrapper tương thích với JDK/Gradle đang dùng:

~~~bash
./gradlew run
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`. Nếu chưa có Wrapper thì cần dùng bản Gradle tương thích đã cài hoặc khởi tạo Wrapper theo quy trình dự án. Với ví dụ có thư viện tải được, chương trình `demo.Main` sẽ in:

~~~text
true
~~~

Lệnh `dependencies` cho biết module nào xuất hiện trong từng configuration; `dependencyInsight` giúp giải thích **vì sao** một module được chọn và đường đi liên quan. Nếu bạn dùng API Jackson trực tiếp như `Main.java`, thêm vào `dependencies`:

~~~groovy
implementation 'com.fasterxml.jackson.core:jackson-databind'
~~~

BOM đang được import sẽ cung cấp phiên bản phù hợp cho module nằm trong danh sách của nó. Không phải tất cả thư viện ngoài hệ sinh thái đều được BOM quản lý; nếu một tọa độ không có version và không có constraint phù hợp, resolution có thể thất bại.

**So sánh hai ví dụ:** Maven thể hiện version management bằng `<dependencyManagement>`; Gradle bản này dùng `platform()`. Cả hai vẫn cần khai báo **thực sự sử dụng starter**, rồi mới resolve các module bắc cầu. Một dependency xuất hiện trên graph không đủ để kết luận nó là direct; phải đối chiếu khai báo gốc của app.

## 6. BOM quản lý phiên bản, không tự biến mọi module thành dependency

**BOM (Bill of Materials)** là POM chứa danh sách các tọa độ cùng version/scope quản lý, nhằm giữ các thư viện liên quan tương thích. BOM giúp trả lời: *“Khi dự án cần module X, nên sử dụng version nào trong tập được khuyến nghị?”* Khai báo dependency thực tế trả lời: *“Dự án có cần module X hay không?”*

### 6.1. Maven: dependencyManagement và dependencies

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **khối quản lý**. Nó không tương đương với:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **khối khai báo sử dụng**. Version của starter có thể bỏ vì quản lý đã được áp dụng. Maven cũng có cách dùng `spring-boot-starter-parent` làm parent POM; khi đó phần quản lý dependency được kế thừa từ parent và không cần import BOM theo đúng mẫu trên. Hai cách dùng khác nhau về thiết lập POM tổng thể, nhưng cùng phục vụ ý tưởng quản lý version.

`dependencyManagement` còn có thể ảnh hưởng version của **dependency bắc cầu** khi tọa độ khớp. Tuy nhiên dependency có `<version>` được khai báo trực tiếp và các quy tắc hợp nhất POM/BOM có thể tạo kết quả khác dự tính. Luôn xem **effective POM** và dependency tree khi có nghi vấn.

### 6.2. Gradle: platform và dependency constraints

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Theo cơ chế Gradle, `platform` biến BOM thành các version constraints trên những configuration có hiệu lực. Một **regular platform** đưa ra version được khuyến nghị nhưng có thể bị yêu cầu/constraint khác trong graph đẩy lên version khác. `enforcedPlatform` áp đặt mạnh hơn và có thể gây tác động ngoài dự án hiện tại khi dùng trong library; chỉ dùng khi hiểu hệ quả. Không mặc định coi `platform` là một khoá version tuyệt đối.

Spring Boot Gradle plugin có thể phối hợp với `io.spring.dependency-management` để nhập BOM tương ứng phiên bản Boot plugin. Khi chọn cách **native Gradle BOM** bằng `platform`, không mặc nhiên cho rằng chỉ áp dụng Spring Boot plugin đã kích hoạt cùng cách quản lý version ấy. Nên biết dự án đang dùng cơ chế nào.

### 6.3. BOM khác dependency lock và version catalog

| Cơ chế | Chức năng |
| --- | --- |
| BOM / platform | Cung cấp tập version được quản lý/khuyến nghị, điều phối thư viện liên quan |
| Maven `dependencyManagement` | Quản lý version, scope và thông số áp dụng cho dependency có hiệu lực; không tự thêm dependency |
| Gradle `libs.versions.toml` (Version Catalog) | Tập trung **cách khai báo** aliases, tọa độ và version; không tự áp đặt dependency resolution trên graph |
| Dependency lockfile | Ghi lại kết quả resolution đã chọn để hỗ trợ build lặp lại theo chính sách công cụ |
| Resolved dependency graph | Bằng chứng cuối cùng về version và đường dẫn dependency **ở một configuration cụ thể** |

Một BOM thường là điểm khởi đầu hợp lý cho Spring Boot vì các phiên bản đã được điều phối cho bộ framework đó. Nhưng BOM **không thể bảo đảm** mọi thư viện ngoài tập nó quản lý đều tương thích, và việc override một thành phần có thể phá sự phối hợp đã được kiểm thử.

## 7. Phạm vi phụ thuộc: không có một classpath duy nhất

Một module có thể được yêu cầu cho compile nhưng không cần đóng gói runtime, hoặc ngược lại. Đối với từng build task, hãy hỏi **“dependency này nằm trong configuration/scope nào?”** trước khi kết luận nó sẽ có mặt ở sản phẩm cuối.

### 7.1. Maven scope (mô hình khái quát)

| Scope | Ý định thường gặp | Hệ quả cần nhớ |
| --- | --- | --- |
| `compile` (mặc định) | Thư viện mã nguồn production dùng khi compile và runtime | Thường xuất hiện trên compile/runtime classpath và có thể truyền bắc cầu |
| `runtime` | Chỉ cần khi chạy, ví dụ một driver runtime | Không phải dependency compile chính của mã nguồn ứng dụng |
| `provided` | Cần khi compile/test nhưng môi trường triển khai cung cấp | Không thuộc runtime classpath tiêu chuẩn theo Maven; đóng gói WAR/Boot có quy tắc riêng phải kiểm tra |
| `test` | Thư viện phục vụ test | Không tự đưa vào classpath production |
| `import` | Chỉ có ý nghĩa trong `dependencyManagement` khi import POM/BOM | Không phải một kiểu runtime dependency |
| `optional` (thuộc tính của dependency) | Cho phép người tiêu thụ quyết định có lấy dependency ấy hay không | Dependency optional không tự truyền qua downstream consumer như dependency bắt buộc |

Maven còn có các cơ chế hiếm hơn như `system`; không khuyến nghị dùng đường dẫn JAR cục bộ để thay cho repository/dependency management. Phạm vi bắc cầu Maven tính theo **kết hợp các scope qua từng cạnh**, nên đừng suy luận rằng mọi dependency `compile` của một thư viện sẽ được đưa nguyên xi vào tất cả cấu hình của ứng dụng.

### 7.2. Gradle configuration (mô hình Java plugin)

| Configuration khai báo | Vai trò |
| --- | --- |
| `implementation` | Dependency dùng cho code production; với Java plugin thông thường góp vào compile/runtime classpath của module |
| `api` | Khai báo API công khai khi dùng `java-library` plugin; cho phép consumer nhận dependency trên compile classpath theo hợp đồng API |
| `compileOnly` | Cần lúc compile nhưng không nằm trên runtime classpath của module qua cấu hình này |
| `runtimeOnly` | Chỉ cần runtime, không dùng để compile source của module |
| `testImplementation` | Dependency cho compile/chạy test, không biến thành runtime production dependency |
| `testRuntimeOnly` | Bổ sung dependency chỉ lúc chạy test |
| `annotationProcessor` | Processor cho compile; không mặc nhiên là runtime dependency của ứng dụng |

Các **resolvable configuration** như `compileClasspath`, `runtimeClasspath` và `testRuntimeClasspath` mới biểu hiện tập module cuối cùng sau resolution. Gradle có variant-aware dependency management, vì vậy graph có thể phụ thuộc configuration và attributes. Ví dụ `java-library` plugin phân biệt `api` với `implementation` để không rò rỉ chi tiết triển khai qua compile classpath của project khác.

**Tác động đến Spring Boot packaging:** task như `bootJar` sử dụng classpath runtime phù hợp do plugin/build cấu hình. Nếu bạn đặt JDBC driver cần thiết vào `compileOnly`, compile có thể xanh nhưng khi khởi chạy executable JAR sẽ thiếu driver. Nếu đặt thư viện test vào `implementation` thay vì `testImplementation`, bạn có thể làm artifact runtime lớn hơn cần thiết. Để khẳng định chắc chắn một dependency có được đóng gói, cần xem **runtimeClasspath và nội dung archive thực tế**, thay vì chỉ đọc dòng khai báo.

## 8. Khi có nhiều phiên bản cùng tọa độ: Maven và Gradle khác nhau

Một dependency graph có thể hình thành hình thoi:

~~~text
app
 ├── B
 │    └── D:1.0
 └── C
      └── D:2.0
~~~

Cả `D:1.0` và `D:2.0` là yêu cầu cho **cùng module D**, giả sử cùng groupId và artifactId. Runtime classpath thông thường không tùy tiện chất cả hai version của cùng module vào để “an toàn”; build tool phải áp dụng luật lựa chọn, và luật này phụ thuộc hệ thống build.

### 8.1. Maven: nearest definition

Maven mặc định ưu tiên phiên bản dependency được xác định **gần dự án nhất** trong cây dependency. Trong hình trên, hai đường dẫn tới D cùng độ sâu; nếu khai báo B trước C theo POM, quy tắc hòa thông thường là **dependency được khai báo trước thắng**. Khi app khai báo trực tiếp `D:3.0`, quan hệ app → D gần hơn hai đường đi bắc cầu, nên có ảnh hưởng trực tiếp tới mediation. `dependencyManagement` có thể áp đặt version đã quản lý khi thích hợp; cần xem effective POM để đánh giá chính xác.

Đừng diễn đạt quy tắc Maven thành “luôn lấy version mới nhất” hoặc “luôn lấy version của dependency có số cao hơn”. Cả hai kết luận đó đều có thể sai.

### 8.2. Gradle: conflict resolution theo yêu cầu và constraints

Gradle mặc định xem xét các phiên bản được yêu cầu cho cùng module trên graph và thường chọn **version cao nhất đáp ứng các ràng buộc**. Với hai yêu cầu `D:1.0` và `D:2.0` và không có quy tắc đặc biệt, kết quả thường là `D:2.0`. Nhưng `platform`, `enforcedPlatform`, `strictly`, version ranges, dependency constraints, component metadata và resolution rules có thể ảnh hưởng hoặc khiến resolution thất bại.

Do đó **cùng khai báo nhìn giống nhau trong Maven và Gradle không bảo đảm tạo ra cùng resolved dependency graph**. Đặc biệt khi Spring Boot BOM hiện diện, phải xác minh version đã chọn thay vì chỉ nhớ một khẩu quyết.

### 8.3. “Version khai báo” khác “version được sử dụng”

Giả sử trong bản in của Gradle có mũi tên:

~~~text
com.example:lib:1.0 -> 2.0
~~~

Cách đọc thông thường: có nơi yêu cầu `1.0` nhưng resolution quyết định dùng `2.0` cho module đó trong configuration được in. Để biết **vì sao** `2.0` được chọn, chạy `dependencyInsight` và đọc selection reason/các đường dẫn. Đừng chỉnh build file theo phỏng đoán chỉ vì nhìn thấy mũi tên.

Một dự án còn có thể bị **classpath conflict** khi **hai artifact có tọa độ khác nhau** lại chứa cùng class. Version mediation cho **cùng một module** không tự giải quyết mọi loại trùng class hoặc xung đột binary giữa các thư viện khác tên.

## 9. Công cụ điều tra dependency thật

### 9.1. Maven

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
mvn help:effective-pom
mvn dependency:analyze
~~~

- `dependency:tree` cho biết graph Maven sau khi xét metadata, scope và version mediation; đây là nơi bắt đầu tìm **đường nào kéo module lạ vào app**.
- `-Dincludes=...` tập trung tìm một tọa độ cụ thể; kết quả phụ thuộc plugin và graph có hiệu lực.
- `help:effective-pom` cho biết POM tổng hợp sau kế thừa và quản lý, hữu ích khi version được quản lý ở parent/BOM.
- `dependency:analyze` có thể chỉ ra dependency được dùng nhưng chưa khai báo hoặc khai báo dư; kết quả là gợi ý, có thể không nhận diện đúng việc sử dụng qua reflection, annotation processing hoặc runtime plugin, nên cần kiểm tra bằng hiểu biết ứng dụng.

Nếu dự án có Maven Wrapper thì thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trong Windows PowerShell. Không tự giả định mọi dự án đều có Wrapper.

### 9.2. Gradle

Với dự án có Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Trong Windows PowerShell dùng `.\gradlew.bat` thay vì `./gradlew`. Trên project multi-module, chỉ rõ project path, ví dụ `./gradlew :app:dependencies --configuration runtimeClasspath`.

- `dependencies` in graph theo configuration, có thể thấy version được chọn, constraints và nhánh lặp.
- `dependencyInsight` cho biết **selected module, selection reason và các đường dependency liên quan**. Khi có phiên bản không mong đợi, đây thường là công cụ đọc đầu tiên.
- Dấu `(*)` trong một số báo cáo Gradle đánh dấu nhánh đã được trình bày ở nơi khác để tránh lặp, không có nghĩa dependency bị bỏ.
- Không so sánh `compileClasspath` với `runtimeClasspath` rồi kết luận build lỗi chỉ vì hai graph khác nhau; `runtimeOnly` và `compileOnly` được tạo ra chính để chúng khác nhau.

### 9.3. Liên hệ với artifact được đóng gói

Khi dự án thật **đã có Spring Boot Gradle plugin và tạo executable JAR bằng `bootJar`**, có thể kiểm tra nội dung đã đóng gói bằng JDK `jar`:

~~~bash
jar tf build/libs/ten-artifact-thuc-te.jar
~~~

Đổi tên file thành **đúng tệp được tạo trên máy**, không chép tên giả trong ví dụ. Với executable Spring Boot JAR dạng thông thường, các thư viện runtime xuất hiện dưới `BOOT-INF/lib` và ứng dụng dưới `BOOT-INF/classes`. Với Maven Spring Boot repackage, xem file thực tế trong `target/` sau khi plugin được cấu hình/chạy.

Đọc archive cho biết **file nào thực sự được đưa vào artifact**, còn graph cho biết **vì sao và từ đường dependency nào**. Khi điều tra lỗi runtime, nên dùng cả hai. Nếu deploy qua OCI image hoặc dùng layered packaging, còn phải xác nhận image/layer thật, bởi một graph dependency hợp lệ chưa chứng minh image phân phối thành công.

## 10. Loại bỏ hoặc thay đổi một phụ thuộc bắc cầu

Một dependency bắc cầu có thể lỗi thời, không tương thích, dư thừa hoặc bị phát hiện lỗ hổng. Cách xử lý phụ thuộc nguyên nhân, **không nên vô hiệu hóa toàn bộ transitivity** chỉ để làm graph nhỏ.

### 10.1. Maven exclusion theo cạnh

Nếu app phụ thuộc trực tiếp `B`, mà `B` đưa theo `C` không mong muốn, có thể khai báo:

~~~xml
<dependency>
    <groupId>example.group</groupId>
    <artifactId>library-b</artifactId>
    <version>1.0</version>
    <exclusions>
        <exclusion>
            <groupId>example.group</groupId>
            <artifactId>library-c</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Đây là tọa độ **minh họa** (không cam kết artifact tồn tại trong repository). Exclusion loại bỏ quan hệ truyền theo **nhánh B → C** trong graph của app. Nếu một nhánh khác vẫn đưa C vào, C có thể tiếp tục hiện diện. Vì vậy cần kiểm tra lại dependency tree thay vì coi exclusion là “xóa toàn cục”.

### 10.2. Gradle exclusion theo dependency

~~~groovy
dependencies {
    implementation('example.group:library-b:1.0') {
        exclude group: 'example.group', module: 'library-c'
    }
}
~~~

Gradle có thể đưa C trở lại từ một đường khác. Hơn nữa, việc bỏ C có thể gây lỗi `ClassNotFoundException` / `NoClassDefFoundError` nếu B thật sự cần C khi chạy. Trước khi exclude, hãy xác minh tại sao C có mặt, thư viện nào dùng nó, và có phiên bản thay thế tương thích hay không.

### 10.3. Trường hợp cần override version

Nên ưu tiên bản cập nhật Spring Boot BOM / starter / thư viện cung cấp dependency khi có thể. Nếu phải override một module, cần hiểu:

- Maven `dependencyManagement` hoặc khai báo trực tiếp có version có thể tác động version được chọn.
- Gradle có `constraints`, `strictly`, `platform` và các quy tắc resolution; một dòng `implementation 'X:1.2'` không nhất thiết “cưỡng bức” version nếu graph có constraints khác.
- Dùng `enforcedPlatform` hoặc force toàn cục khi không hiểu hệ quả có thể làm thư viện khác mất tương thích binary.
- Sau thay đổi phải xem **resolved version**, chạy test cần thiết và xác nhận artifact runtime.

## 11. Các lỗi thường gặp và cách đặt câu hỏi đúng

| Hiện tượng | Nguyên nhân khả dĩ | Điều cần kiểm tra |
| --- | --- | --- |
| Java source import được thư viện nhưng `pom.xml`/`build.gradle` không khai báo nó | Thư viện đang là **transitive dependency** | Đọc dependency tree; nếu app dùng API trực tiếp, khai báo direct |
| Đã import BOM nhưng IDE báo thiếu class | BOM chỉ **quản lý version**, không tự thêm thư viện | Kiểm tra có khai báo dependency ở `dependencies` chưa và đúng configuration chưa |
| Maven và Gradle chọn hai version khác nhau | Khác luật mediation/constraints, parent/platform hoặc graph | So sánh `dependency:tree`, `effective-pom`, `dependencyInsight` |
| `Could not find ...` / lỗi resolve artifact | Sai tọa độ, version, repository, mạng hoặc quyền repository | Kiểm tra GAV, nguồn metadata, repository và lỗi tải thực tế |
| Compile xanh nhưng chạy báo `NoClassDefFoundError` | Runtime thiếu dependency, sai scope, exclude hoặc artifact chưa đóng gói đúng | Kiểm tra runtime classpath, `BOOT-INF/lib`, môi trường chạy |
| Runtime báo `NoSuchMethodError` sau thay đổi dependency | Có thể là binary incompatibility giữa version được compile và runtime | Xem selected version, duplicated classes, thư viện kéo phiên bản cũ/mới |
| Runtime có hai thư viện logging tranh chấp | Có thể gặp nhiều implementation/capability khác nhau | Xác định provider cần giữ, xem graph và dependency management rồi xử lý có chủ đích |
| Sửa version trực tiếp nhưng graph vẫn dùng bản khác | BOM/constraint/nearest-wins/conflict resolution đang ảnh hưởng | Xác minh resolved version và selection reason, không chỉ dòng khai báo |
| Dùng `transitive = false` làm mất nhiều class | Tắt toàn bộ phụ thuộc con của module trong Gradle | Chỉ dùng khi thực sự cung cấp đầy đủ dependency thay thế; ưu tiên exclusion chọn lọc |
| Dependency test xuất hiện trong package production | Khai báo nhầm scope/configuration hoặc packaging custom | Kiểm tra test vs runtime classpath, file archive và cấu hình task |
| App chạy trên IDE nhưng lỗi ở bản phát hành | IDE classpath khác classpath trong artifact hoặc môi trường | Đối chiếu runtimeClasspath, package contents, JDK và launch command |

**Lưu ý:** `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError` có thể có nguyên nhân khác; bảng trên đưa ra hướng điều tra dependency đầu tiên, không kết luận nguyên nhân duy nhất chỉ dựa vào tên exception.

## 12. Thực hành suy luận nhanh

**Tình huống A.** App chỉ khai báo `spring-boot-starter-web`, source gọi `ObjectMapper`. Hiện tại compile thành công. Điều gì có thể xảy ra nếu starter không còn mang Jackson theo cùng một nhánh?

**Trả lời:** compile của app có thể lỗi vì đã phụ thuộc vào API bắc cầu. Nếu app trực tiếp dùng Jackson, hãy khai báo `jackson-databind` trực tiếp và cho BOM phù hợp quản lý version; sau đó kiểm tra graph.

**Tình huống B.** App import Spring Boot BOM và không khai báo bất kỳ starter nào. Có tự xuất hiện `spring-webmvc` và Tomcat trên runtime classpath không?

**Trả lời:** Không, chỉ import BOM không kéo toàn bộ thư viện được quản lý. Phải khai báo dependency thực sự cần (ví dụ starter web), sau đó các cạnh transitive có hiệu lực mới được giải quyết.

**Tình huống C.** Hai đường nhánh yêu cầu cùng module ở `1.0` và `2.0`. Có thể kết luận ngay rằng `2.0` luôn được đóng gói không?

**Trả lời:** Không. Maven có nearest-wins; Gradle mặc định ưu tiên version cao nhất nhưng có thể bị constraints/strict versions/platform thay đổi. Cần kiểm tra resolution thực tế và classpath/task packaging.

**Tình huống D.** App đặt JDBC driver ở `compileOnly` trong Gradle, nhưng khi chạy artifact thì không kết nối được DB. Có thể do đâu?

**Trả lời:** Driver không xuất hiện trên runtime classpath chỉ vì khai báo `compileOnly`. Nếu ứng dụng chịu trách nhiệm cung cấp driver khi chạy, dùng configuration runtime phù hợp, thường là `runtimeOnly`, kiểm tra dependency graph và artifact thực tế.

**Tình huống E.** App exclude C khỏi B nhưng `dependencyInsight` vẫn hiển thị C. Exclusion có bị “hỏng” không?

**Trả lời:** Không nhất thiết. Một nhánh khác có thể vẫn yêu cầu C; exclusion trên cạnh B không xóa module toàn cục. Cần đọc tất cả đường dẫn đưa C vào graph.

## 13. Checklist khi thêm một thư viện vào Spring Boot

1. Xác định đúng `groupId` + `artifactId` theo tài liệu phát hành, không đoán theo tên package/import.
2. Xác định app **trực tiếp dùng API** đó hay chỉ dùng thư viện khác có dependency nội bộ.
3. Chọn Maven scope / Gradle configuration phản ánh đúng compile, runtime, test hoặc annotation processing.
4. Xác định có Spring Boot BOM/parent/platform đang quản lý version hay chưa; tránh ghi đè version không có lý do.
5. Resolve graph cho **configuration cần dùng**, đọc đường dẫn đến dependency và version cuối.
6. Khi gặp xung đột, so sánh luật Maven/Gradle và chọn phương án quản lý có lý do; không tự exclude hàng loạt.
7. Chạy compile/test cần thiết, kiểm tra runtime classpath và artifact thực tế khi sản phẩm được đóng gói/phát hành.
8. Ghi nhận các thư viện trực tiếp quan trọng để việc nâng cấp, kiểm tra giấy phép và xử lý lỗ hổng về sau có cơ sở rõ ràng.

### Ghi nhớ cốt lõi

**Tọa độ** nói “đây là module nào”; **dependency declaration** nói “dự án cần module nào và ở đâu”; **transitivity** giải thích “module nào đến từ module khác”; **BOM/constraints** điều phối “version nào nên được chọn”; **resolved graph** cho biết “build tool thực sự chọn gì”; còn **packaging** quyết định những file nào đi vào artifact phát hành. Tách bạch các lớp này giúp đọc đúng lỗi và tránh sửa nhầm phần không liên quan.

## 14. Tài liệu chính thống

- Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven Dependency Plugin — dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Gradle — Declaring Dependencies: https://docs.gradle.org/current/userguide/declaring_dependencies.html
- Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle — Dependency Constraints and Conflict Resolution: https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html
- Gradle — Platforms and Importing Maven BOMs: https://docs.gradle.org/current/userguide/platforms.html
- Spring Boot Gradle Plugin — Managing Dependencies: https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html
- Spring Boot Maven Plugin — Using Spring Boot Dependency Management: https://docs.spring.io/spring-boot/maven-plugin/using.html

Version được liệt kê trong ví dụ mang tính minh họa. Với dự án thực, hãy luôn đối chiếu phiên bản **Spring Boot, Gradle/Maven, JDK và BOM đang dùng** trước khi pin hoặc override dependency.