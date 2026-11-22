# Phân biệt plugins với pluginManagement và cấu hình execution trong Maven (Spring Boot)

Trong dự án Spring Boot dùng Maven, ba khái niệm thường đứng gần nhau trong `pom.xml` nhưng có nhiệm vụ khác nhau:

- **`<build><plugins>`:** khai báo/cấu hình các build plugin mà project sử dụng. Những plugin goal có ràng buộc với lifecycle có thể chạy khi Maven đi tới phase tương ứng; plugin cũng có thể chạy khi gọi goal trực tiếp.
- **`<build><pluginManagement>`:** quản lý tập trung **version, cấu hình và execution mặc định** cho plugin. Với plugin chưa được kích hoạt hoặc chưa có goal gắn lifecycle, phần quản lý này **không tự tạo một công việc mới để chạy**.
- **`<executions>` của plugin:** định nghĩa **goal nào** chạy, **trong phase nào**, với **cấu hình nào**, và dùng **`id`** để định danh một lần thực thi (phục vụ cấu hình, kế thừa, ghi đè).

Với Spring Boot, điểm kiểm tra thực tế là **`spring-boot-maven-plugin:repackage`**: dự án có thể build ra JAR Java thông thường, hoặc build ra **executable Spring Boot JAR** có launcher và dependencies để chạy bằng `java -jar`. Muốn hiểu vì sao `repackage` có chạy hay không, phải xét đồng thời `plugins`, `pluginManagement`, `executions` và phần kế thừa từ parent POM.

## 1. Nắm trước mô hình Maven: plugin, goal, lifecycle, phase, execution

**Plugin** là một artifact triển khai các tác vụ cho Maven. Ví dụ:

| Plugin | Goal thường gặp | Vai trò |
| --- | --- | --- |
| `maven-compiler-plugin` | `compile`, `testCompile` | Biên dịch mã nguồn Java |
| `maven-surefire-plugin` | `test` | Chạy unit tests |
| `maven-jar-plugin` | `jar` | Tạo JAR thông thường |
| `maven-failsafe-plugin` | `integration-test`, `verify` | Chạy và xác nhận integration tests nếu được cấu hình |
| `spring-boot-maven-plugin` | `run`, `repackage` | Chạy ứng dụng Boot, đóng gói lại archive thành dạng thực thi |
| `maven-antrun-plugin` | `run` | Chạy tác vụ Ant tùy chọn trong lifecycle |

**Goal** là một công việc cụ thể do plugin cung cấp, ví dụ `compiler:compile` hoặc `spring-boot:repackage`. **Lifecycle** là quy trình build; **phase** là một mốc trong lifecycle, ví dụ `compile`, `test`, `package`, `verify`. **Execution** là một cấu hình sử dụng một hoặc nhiều goal, có thể gắn với phase cụ thể.

Dòng chảy khi gọi:

~~~bash
mvn clean package
~~~

~~~text
clean lifecycle
  └─ clean → dọn output của lần build trước

default lifecycle (chạy các phase cần thiết đến package)
  validate → ... → compile → ... → test → package
                          |           |         |
                    compiler goal  surefire   jar goal (với packaging=jar)
                                                 |
                                                 └─ spring-boot:repackage
                                                    nếu đã được binding đúng
~~~

Sơ đồ thể hiện các điểm chính, không phải danh sách đầy đủ tất cả phase. Với `<packaging>jar</packaging>` (hoặc mặc định không ghi packaging), Maven **đã có các goal mặc định được gắn với lifecycle**. Vì vậy bạn thường thấy Maven compile và tạo JAR dù trong `pom.xml` không tự khai báo `maven-compiler-plugin` và `maven-jar-plugin`. Điều đó không có nghĩa mọi plugin sẽ tự chạy: plugin bổ sung chỉ chạy nếu goal của nó đã được gắn vào lifecycle hoặc được gọi trực tiếp.

So sánh hai dạng lệnh:

~~~bash
mvn package
mvn spring-boot:run
~~~

- `mvn package` yêu cầu Maven đi qua các phase cho đến `package` và thực hiện **các goal đang được bind vào những phase đó**.
- `mvn spring-boot:run` gọi trực tiếp goal `run` của Spring Boot Maven plugin (cần resolve được plugin và đủ cấu hình ứng dụng), **không tương đương** với đóng gói một file JAR rồi chạy artifact đó.
- `mvn package spring-boot:repackage` yêu cầu build package trước rồi gọi thêm goal repackage. Nếu project đã có execution repackage được bind vào `package`, gọi thêm goal riêng có thể khiến repackage bị thực hiện hai lượt; không dùng lệnh này một cách máy móc.

Maven phân biệt rõ **phase** và **goal**: `package` là phase, còn `spring-boot:repackage` là một goal. Phần `<execution>` tạo cầu nối giữa hai loại này.

## 2. `<build><plugins>`: đưa plugin vào cấu hình build đang sử dụng

Một plugin khai báo ở cấp build thường có cấu trúc:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.3.5</version>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn trong `pom.xml`**, không phải POM độc lập. Dự án đã khai báo plugin Spring Boot, nhưng chỉ riêng ba trường `groupId`, `artifactId`, `version` không tạo ra **mọi** goal của plugin trong mọi phase. Maven cần có một binding, execution đã cấu hình, execution kế thừa hoặc lệnh gọi goal trực tiếp. Ví dụ `repackage` có thể được cấu hình từ parent Spring Boot hoặc từ `<executions>` của project.

Khác với `<dependencies>`, plugin không phải thư viện ứng dụng dùng trong code Java. `spring-boot-maven-plugin` chạy **trong quá trình build**, còn `spring-boot-starter`/`spring-boot-starter-web` là dependency hỗ trợ **ứng dụng**.

### Plugins đặt trong parent POM có thể được kế thừa

Nếu parent khai báo plugin ở `<build><plugins>`, các module con thường kế thừa cấu hình plugin đó (trừ khi cấu hình `<inherited>false</inherited>` hoặc quy tắc kế thừa riêng). Khi đó plugin **có thể trở thành plugin đang được dùng** ở module con mà không cần module con khai báo thêm. Điều này khác với quản lý plugin qua `pluginManagement`, nơi chỉ đặt quy tắc cho plugin được dùng.

Tác động thực tế: khi xây multi-module Maven, tránh đặt một plugin có execution chỉ dành riêng cho ứng dụng vào `<plugins>` của parent chung nếu bạn không muốn mọi module con được áp dụng execution đó. Có thể dùng `pluginManagement` để quản lý version/config rồi chọn module nào thực sự khai báo plugin.

## 3. `<pluginManagement>`: tập trung quản lý, không tự phát sinh một goal mới

Ví dụ parent POM quản lý Spring Boot Maven plugin:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.3.5</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đoạn trên đặt **phiên bản được quản lý** cho plugin. Nó không đồng nghĩa Maven tự thêm `spring-boot:repackage` vào phase `package`. Trong một child module muốn sử dụng plugin, có thể khai báo ngắn:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Lúc này phần quản lý từ parent có thể cung cấp `version=3.3.5` cho khai báo plugin ở child. **Nhưng** để `repackage` chạy trong `package`, vẫn phải có một execution/binding hợp lệ, chẳng hạn execution được quản lý/kế thừa với `repackage` goal.

### Ngoại lệ cần hiểu đúng: các plugin đã được Maven bind sẵn

Không nên diễn giải `pluginManagement` thành quy tắc tuyệt đối “nếu không thêm plugin trong `<plugins>` thì management hoàn toàn vô tác dụng”. Với `packaging=jar`, Maven đã mặc định sử dụng các goal của compiler, resources, surefire, jar... trong lifecycle. `pluginManagement` có thể ảnh hưởng version/configuration của **những plugin/goal đã được lifecycle mặc định sử dụng**, kể cả khi chúng không được khai báo tường minh trong `<plugins>` của module.

Phân biệt hai trường hợp:

1. **Đã có binding mặc định hoặc plugin đang hoạt động:** management có thể tùy chỉnh version và hành vi của plugin đó.
2. **Một plugin hoàn toàn mới chưa có binding/goal được gọi:** chỉ đặt nó vào management sẽ không tạo tác vụ thực thi.

Với `spring-boot-maven-plugin` và goal `repackage`, không nên dựa vào suy đoán từ tên plugin; hãy kiểm tra active plugin và execution thực tế trong effective POM.

### Đừng nhầm `pluginManagement` với `dependencyManagement`

| Thành phần | Đối tượng quản lý | Ví dụ |
| --- | --- | --- |
| `<dependencies>` | Thư viện ứng dụng dùng trực tiếp | `spring-boot-starter-web` |
| `<dependencyManagement>` | Version/quy tắc cho dependency của ứng dụng | `spring-boot-dependencies` BOM |
| `<build><plugins>` | Plugin thực hiện thao tác build | `spring-boot-maven-plugin` |
| `<build><pluginManagement>` | Version/config/execution của build plugin | Cố định version plugin Spring Boot hoặc Surefire |

**Import Spring Boot BOM qua `<dependencyManagement>` không tự mang toàn bộ plugin management của `spring-boot-starter-parent`.** Đó là lý do cấu hình Spring Boot Maven plugin khác nhau khi có và không dùng starter parent.

## 4. `<executions>`: điều khiển thời điểm và cách goal được chạy

Cấu trúc tổng quát:

~~~xml
<plugin>
    <groupId>...</groupId>
    <artifactId>...</artifactId>
    <version>...</version>
    <configuration>
        <!-- Cấu hình chung ở cấp plugin -->
    </configuration>
    <executions>
        <execution>
            <id>ten-execution-duy-nhat</id>
            <phase>ten-phase</phase>
            <goals>
                <goal>ten-goal</goal>
            </goals>
            <configuration>
                <!-- Cấu hình riêng cho execution này -->
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **sơ đồ XML**, không phải cấu hình có thể chạy: các dấu `...` là chỗ minh họa. Ý nghĩa từng thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `<id>` | Danh tính execution trong plugin; dùng để ghép/ghi đè cấu hình khi kế thừa POM và đọc log |
| `<phase>` | Phase nơi Maven thực hiện goal, ví dụ `validate`, `process-resources`, `package` |
| `<goals>` | Một hoặc nhiều goal thuộc **plugin hiện tại** |
| `<configuration>` ở cấp plugin | Cấu hình dùng chung cho các lời gọi goal phù hợp |
| `<configuration>` ở cấp execution | Cấu hình riêng của execution, có thể ghi đè cấu hình cùng tham số ở cấp plugin |
| `<inherited>` | Kiểm soát cấu hình/execution có được kế thừa từ parent hay không |

**`<phase>` có thể được bỏ qua khi goal có default phase trong plugin descriptor.** Ví dụ `spring-boot:repackage` có default phase `package`; nếu goal không có default phase và cũng không ghi `<phase>`, execution thường **không được chạy trong lifecycle**. Cần phân biệt việc khai báo goal trong `<executions>` với gọi goal trực tiếp bằng dòng lệnh.

### Ví dụ có thể dùng: gắn một goal vào `validate`

Bên trong `<build><plugins>` của POM, thêm:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <executions>
        <execution>
            <id>show-build-marker</id>
            <phase>validate</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="VALIDATE_PHASE_REACHED"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Chạy ở project Maven có POM hợp lệ:

~~~bash
mvn validate
~~~

Trong output của Maven sẽ có thông điệp **`VALIDATE_PHASE_REACHED`** do Ant echo in ra, bên cạnh các dòng build/plugin log khác; không coi toàn bộ stdout của Maven là cố định. Nếu gọi `mvn package`, phase `validate` cũng được đi qua trước `package`, nên execution này chạy trong quy trình build.

Thí nghiệm:

1. Đặt toàn bộ cấu hình plugin/`show-build-marker` ở `<build><pluginManagement><plugins>...`, bỏ khai báo plugin ở `<build><plugins>`: goal `antrun:run` không được kích hoạt chỉ từ management.
2. Thêm plugin `maven-antrun-plugin` vào `<build><plugins>`, có thể chỉ khai báo `groupId`/`artifactId`: nó nhận cấu hình quản lý và goal được bind vào `validate`.
3. Chạy lại `mvn validate` và quan sát marker xuất hiện.

Cơ chế này lý giải lý do parent thường quản lý nhiều plugin nhưng mỗi module con chỉ kích hoạt plugin cần cho nhiệm vụ của nó.

### Plugin-level configuration so với execution-level configuration

Giả sử một plugin có hai executions khác nhau: phần `<plugin><configuration>` chứa tham số chung, còn `<execution><configuration>` chứa tham số riêng cho một execution. Nếu cùng một tham số được cấu hình ở hai cấp, cấu hình cụ thể của execution thường có mức ưu tiên đối với invocation đó sau khi Maven merge cấu hình. Quy tắc merge XML còn chịu cấu hình kế thừa và các thuộc tính như `combine.self`/`combine.children` khi có; hãy xem effective POM cho trường hợp phức tạp.

Nếu một goal cũng được chạy trực tiếp từ CLI, **đừng mặc định** mọi cấu hình chỉ đặt trong một execution tùy ý sẽ tự áp dụng cho lời gọi CLI. CLI có cơ chế execution riêng (thường liên quan `default-cli`) và cấu hình cấp plugin; xem plugin descriptor và lệnh hiệu lực để quyết định đặt tham số ở đâu.

## 5. Spring Boot với `spring-boot-starter-parent`: vì sao `repackage` có thể chạy mà không cần tự viết execution?

Spring Boot starter parent cung cấp dependency management và các mặc định build/plugin, bao gồm execution `repackage` của `spring-boot-maven-plugin` với **execution id là `repackage`**. Vì vậy khi project con dùng starter parent, thông thường chỉ cần khai báo Spring Boot Maven plugin trong `<build><plugins>` để dùng execution đã được quản lý.

Ví dụ đầy đủ, ghép từ hai file:

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>packaging-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/com/example/demo/PackagingDemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PackagingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PackagingDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showMessage() {
        return args -> System.out.println("PACKAGING_OK");
    }
}
~~~

Mã Java hợp lệ với **Java 17+**. Phiên bản Boot `3.3.5` được cố định để ví dụ lặp lại được; nó không được giới thiệu là phiên bản mới nhất. Cần có Maven tương thích, JDK 17+ và kết nối repository dependency cho lần build đầu. Thực hiện tại thư mục chứa `pom.xml`:

~~~bash
mvn clean package
java -jar target/packaging-demo-1.0.0.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

Dấu `\` ở cuối dòng là cú pháp nối dòng **trên Linux/macOS**; trên Windows PowerShell có thể viết lệnh `java -jar target/packaging-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF` trên **một dòng**. Với cấu hình đã tắt banner/root logging và startup thành công, chương trình in dòng:

~~~text
PACKAGING_OK
~~~

Lúc `mvn clean package` chạy, Maven có thể in log thay đổi theo môi trường; không có stdout cố định cho phần build. Project sử dụng `spring-boot-starter` thay vì starter web, nên ví dụ không cố tạo HTTP server và ứng dụng kết thúc sau khi chạy `CommandLineRunner`.

**Phân tích vai trò:**

1. Maven chọn `jar` packaging mặc định, biên dịch Java và tạo JAR thường nhờ lifecycle bindings.
2. `spring-boot-starter-parent` cung cấp version/configuration và execution `repackage` cho Spring Boot Maven plugin.
3. `<build><plugins>` của project đưa Spring Boot Maven plugin vào danh sách plugin được dùng.
4. Execution `repackage` hoạt động ở phase `package`, sau khi Maven đã tạo archive để repackaging. Kết quả là executable JAR với Spring Boot launcher và runtime dependencies cần thiết.
5. Lệnh `java -jar` chạy chính artifact đã build. Maven và Spring Boot Maven plugin **không chạy trong tiến trình ứng dụng lúc triển khai**.

Ví dụ này **không cần viết lại `<executions>` cho `repackage`** bởi starter parent đã quản lý nó. Nhưng nếu bỏ hẳn plugin khỏi `<build><plugins>` của project mà không có cơ chế kích hoạt plugin nào khác, không nên mặc định Maven sẽ tự tạo executable Boot JAR chỉ vì có dependency `spring-boot-starter`.

## 6. Tùy chỉnh execution kế thừa: phải dùng đúng `id=repackage`

Khi dùng starter parent, để tùy chỉnh execution `repackage` đã có, khai báo cùng `id`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>repackage</id>
                    <configuration>
                        <classifier>exec</classifier>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Đây là đoạn đặt trong `<project>` của ví dụ có starter parent. Với cùng execution id, Maven merge/override cấu hình của execution kế thừa, **không cần khai báo lại `<goal>repackage</goal>`**. `classifier=exec` cho biết artifact đã repackage được tạo dưới dạng `packaging-demo-1.0.0-exec.jar` song song với artifact gốc trong cấu hình minh họa; có thể chạy:

~~~bash
java -jar target/packaging-demo-1.0.0-exec.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

**Lỗi thường gặp:** tạo một execution mới với `<id>custom-repackage</id>` rồi thêm `<goal>repackage</goal>` khi execution `repackage` của parent vẫn có hiệu lực. Maven xem đây là **hai executions** khác nhau; goal có thể chạy hai lượt trong cùng phase và gây output/thứ tự đóng gói khó hiểu. Nếu ý định chỉ là đổi cấu hình parent, giữ nguyên `id=repackage`.

Nguyên tắc id trong kế thừa:

| Tình huống | Kết quả |
| --- | --- |
| Child khai báo execution trùng id với parent cho cùng plugin | Cấu hình được merge/override theo quy tắc Maven |
| Child khai báo id mới | Thêm một execution riêng bên cạnh execution kế thừa |
| Child không ghi `<id>` | Maven dùng id mặc định cho execution đó; không tự hiểu là `repackage` |
| Cần tránh một execution kế thừa | Cân nhắc cấu hình `skip` được goal hỗ trợ, `inherited` ở đúng cấp parent, hoặc cấu trúc plugin của module; xác nhận bằng effective POM |

Không nên lặp toàn bộ execution có sẵn khi chỉ cần đổi một tham số. Xem version/goal/execution id trong effective POM trước khi thêm cấu hình.

## 7. Không dùng starter parent: import BOM khác cấu hình Maven plugin

Một dự án có thể kế thừa parent của doanh nghiệp nên không dùng `spring-boot-starter-parent`. Dự án vẫn có thể **import BOM** của Spring Boot để quản lý dependency version:

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

Đoạn này chỉ cung cấp **dependency management**. Không suy ra nó đã cấu hình `spring-boot-maven-plugin` hoặc `repackage` execution. Muốn Maven tạo executable Boot JAR, có thể cấu hình plugin version và goal tường minh:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.3.5</version>
            <executions>
                <execution>
                    <id>boot-repackage</id>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Đây là đoạn cấu hình trong `<project>`; ví dụ giả định project còn có `dependencies` phù hợp, `packaging=jar` và compiler tương thích. Goal `repackage` có default phase là `package` nên có thể bỏ `<phase>package</phase>`; nhưng ghi tường minh cũng hợp lệ khi muốn giúp người học nhìn thấy binding:

~~~xml
<execution>
    <id>boot-repackage</id>
    <phase>package</phase>
    <goals>
        <goal>repackage</goal>
    </goals>
</execution>
~~~

Hai ví dụ execution ở trên là **hai lựa chọn thay thế cho nhau**; **không đặt cả hai vào cùng plugin** nếu chỉ cần một lần repackaging.

Khi không có starter parent, hãy kiểm tra riêng phiên bản/cấu hình compiler plugin, Java release, surefire và các plugin khác cần thiết. BOM không mang nguyên bộ mặc định plugin của parent. Nếu có một company parent đang quản lý plugin, bạn có thể kế thừa version/config của nó; không nhất thiết viết trùng mọi thứ trong module.

### Tại sao `repackage` cần có JAR trước?

`spring-boot:repackage` đóng gói **lại** archive Java đã được tạo; goal này không thay `compiler:compile` hay `jar:jar`. Trên project `jar` tiêu chuẩn, phase `package` đã bind `jar:jar` và execution Boot được thực hiện sau goal đóng gói mặc định theo thứ tự lifecycle. Nếu bạn chỉ gọi:

~~~bash
mvn spring-boot:repackage
~~~

trên một project chưa có JAR đầu vào, việc đóng gói lại có thể thất bại. Cách thông dụng là bind `repackage` vào `package` rồi chạy `mvn package`. Lệnh thủ công `mvn package spring-boot:repackage` chỉ phù hợp khi thật sự muốn gọi repackage sau khi package và hiểu project có execution nào đã chạy trước đó.

## 8. Quản lý plugin trong dự án đa module

Một parent POM dùng `<packaging>pom</packaging>` có thể định nghĩa plugin management cho toàn tổ chức:

**Parent POM (đoạn trong `<project>`):**

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.3.5</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

**Application module (đoạn trong child `<project>`):**

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

**Library module:** không khai báo Boot plugin nếu library chỉ cần plain JAR.

Kết quả: application module có một execution `repackage` từ management; library không bị ép đóng gói thành executable Boot JAR chỉ vì chia sẻ parent quản lý version. Phương án này giúp module tạo ứng dụng và module thư viện có lifecycle tương ứng với mục đích riêng.

### Đặt `<plugins>` ở parent khi nào?

Đặt plugin ở parent `<build><plugins>` khi **mọi module con thực sự cần** plugin/execution đó (trừ những module được tắt kế thừa hoặc có cấu hình riêng). Ví dụ các plugin kiểm tra build áp dụng toàn bộ modules có thể phù hợp; plugin Boot repackage thường chỉ phù hợp các module ứng dụng. Không áp một quy tắc cứng nhắc cho mọi dự án: cần xem actual parent inheritance, packaging type, profile và execution id.

### `<inherited>false</inherited>` khác `<skip>true</skip>`

- `<inherited>false</inherited>` là phần Maven model kiểm soát có truyền plugin/execution xuống POM con hay không (đặt ở cấp hỗ trợ).
- `<skip>true</skip>` là một tham số của **goal cụ thể**, chỉ có ý nghĩa nếu goal đó hỗ trợ và được truyền cấu hình đúng. Với Spring Boot `repackage`, goal có tùy chọn skip.
- Cả hai khác việc không khai báo plugin. Sự tồn tại của inherited execution và việc goal thực sự chạy phải được xác minh qua effective POM/log.

## 9. Plugin-level configuration, execution-level configuration và precedence

Ví dụ một plugin có tham số chung, một execution có tham số riêng:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludeDevtools>true</excludeDevtools>
    </configuration>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là mảnh cấu hình **giả định dùng starter parent**, nên execution `repackage` và goal của nó đã được kế thừa. Cấu hình plugin-level `excludeDevtools` dùng chung khi phù hợp; cấu hình classifier chỉ cho execution `repackage`. Tên tham số phải khớp plugin goal và version. Không bê một tham số từ plugin khác rồi cho vào `<configuration>` chỉ vì đều là XML.

Trong một tổ hợp parent + child + profiles, cấu hình Maven được merge qua nhiều nguồn. Cách hiểu an toàn:

1. Xem plugin nào đã được khai báo trực tiếp/kế thừa hoặc đã có default lifecycle binding.
2. Xác định execution **bằng `id`**, phase và goals.
3. Xem config ở cấp plugin và cấp execution sau kế thừa.
4. Kiểm tra log khi thực thi phase, vì effective POM mô tả model nhưng log cho biết goal nào đã chạy.

Khi bạn đổi `<phase>package</phase>` sang `<phase>verify</phase>`, execution sẽ chạy lúc Maven đi đến `verify` (nếu plugin goal được bind đúng). `mvn package` không đi đến `verify`; lúc đó goal sẽ không chạy trong lời gọi này. Với Boot `repackage`, đổi phase tùy tiện còn có thể làm artifact tại `package` khác điều bạn dự kiến, nên chỉ đổi khi có yêu cầu build rõ ràng.

## 10. Chẩn đoán cấu hình từ effective POM và log Maven

Ba lệnh đọc cấu hình và thực thi thường hữu ích:

~~~bash
mvn help:effective-pom
mvn help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail
mvn package
~~~

- **`help:effective-pom`**: cho thấy mô hình POM sau khi áp dụng parent, plugin management, profiles và các cấu hình liên quan; tìm `spring-boot-maven-plugin` ở cả `pluginManagement` và `plugins`. Cẩn thận: thấy plugin ở `pluginManagement` không đủ kết luận goal đã được chạy.
- **`help:describe`**: mô tả goal, các tham số và default phase của plugin đã resolve; dùng để xác minh goal/parameter name khi cấu hình execution.
- **`mvn package`**: quan sát log dạng `plugin-prefix:goal (execution-id)` để biết execution nào thực sự chạy; đây là thông tin cuối cùng về build hiện hành.

Có thể xuất effective POM để dễ tìm cấu hình:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

Lệnh này ghi một file phân tích dưới `target/` trong project hiện hành; chỉ chạy khi muốn tạo file đó. Nếu Maven không tạo được đường dẫn đích trong cấu hình cụ thể, chọn vị trí ghi khác phù hợp với hệ thống file.

Khi cần thêm chi tiết về vì sao plugin chạy hoặc bị skip:

~~~bash
mvn -X package
~~~

`-X` in debug log rất dài, có thể chứa cấu hình và đường dẫn nhạy cảm. Chỉ dùng để chẩn đoán khi log thường chưa đủ; không cần bật debug cho mọi lần build.

### Kiểm tra sản phẩm đóng gói

Sau khi build, tùy cấu hình project, chạy:

~~~bash
jar tf target/packaging-demo-1.0.0.jar
java -jar target/packaging-demo-1.0.0.jar
~~~

Với một **executable Boot JAR** chuẩn, thường thấy cấu trúc `BOOT-INF/classes/`, `BOOT-INF/lib/` và launcher trong manifest. Với **plain JAR**, có thể không có launcher hoặc runtime dependencies để khởi chạy bằng `java -jar`. Tên/đường dẫn artifact và classifier phụ thuộc `artifactId`, `version`, `finalName` và cấu hình repackage; không coi mọi project đều sinh tên file như ví dụ.

Dấu hiệu build có thể chạy nhưng artifact khác mong đợi:

- `mvn package` thành công nhưng JAR không chạy trực tiếp: kiểm tra goal `repackage` có được bind và chạy không.
- Một version của plugin không được mong muốn: kiểm tra version trực tiếp, pluginManagement và parent.
- `repackage` xuất hiện hai lần trong log: kiểm tra execution ids bị khai báo trùng ý định, nhất là với starter parent.
- Thư viện ứng dụng thiếu ở runtime: kiểm tra `dependencies`/scope; `pluginManagement` không bổ sung dependency cho ứng dụng.

## 11. Bảng lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có khả năng | Cách kiểm tra/sửa |
| --- | --- | --- |
| Chỉ cấu hình ở `pluginManagement` mà custom goal không chạy | Chưa kích hoạt plugin hoặc chưa có lifecycle binding | Khai báo plugin ở `<build><plugins>` và execution goal/phase nếu cần |
| Đã khai báo plugin nhưng không thấy goal trong `mvn package` | Goal chưa được bind; phase khác `package`; profile không active | Xem effective POM, goal default phase, `executions` và Maven log |
| Có parent Spring Boot nhưng JAR vẫn là plain JAR | Spring Boot Maven plugin chưa được kích hoạt hoặc repackage bị skip/ghi đè | Kiểm tra `<build><plugins>`, execution `id=repackage`, log `repackage` |
| Dùng BOM nhưng thiếu version Spring Boot Maven plugin | Import BOM chỉ quản lý dependencies | Thêm plugin version hoặc kế thừa `pluginManagement` phù hợp |
| Repackage chạy hai lượt | Tạo execution mới thay vì sửa `id=repackage` kế thừa | Dùng cùng id nếu mục đích là tùy chỉnh execution cũ |
| `No goals have been specified for this build` | Lệnh không chọn phase/goal hợp lệ | Gọi `mvn package` hoặc một goal cụ thể |
| `No plugin found for prefix 'spring-boot'` | Plugin prefix chưa resolve được hoặc plugin repo/cấu hình có vấn đề | Kiểm tra `pom.xml`, plugin version, repositories, mạng; thử tọa độ plugin đầy đủ |
| `Plugin execution not covered by lifecycle configuration` trong IDE | IDE/m2e không biết xử lý một plugin execution | Phân biệt vấn đề tích hợp IDE và Maven CLI; kiểm tra `mvn package` trước |
| Lỗi thiếu source JAR khi `repackage` | Gọi goal trước khi tạo archive hoặc sai cấu hình packaging | Bind vào `package` sau bước tạo JAR/WAR; chạy `mvn package` |
| `no main manifest attribute` khi `java -jar` | Có thể chạy plain JAR thay cho executable Boot JAR | Kiểm tra manifest, file/classifier, execution `repackage` |
| `ClassNotFoundException` sau khi đóng gói | Dependency/scope/classpath sai hoặc archive không phù hợp | Kiểm tra dependency tree, nội dung JAR, launcher và log |
| Compiler/Surefire tự chạy dù không khai báo plugin | Maven mặc định bind goal theo `packaging` | Phân biệt default lifecycle plugin với custom plugin chưa bind |

Trong Spring Boot, **`spring-boot-maven-plugin` chỉ phụ trách phần build**. Nó không thay thế annotation `@SpringBootApplication`, dependency `spring-boot-starter`, JDK hay JVM runtime. Sửa lỗi phải bắt đầu từ bước nào thực sự thất bại: resolve plugin, compile, test, archive, repackage hay `java -jar`.

## 12. Quy trình lựa chọn trong project thực tế

Dùng checklist ngắn trước khi thay đổi `pom.xml`:

1. **Xác định cần công việc gì:** compile, test, đóng gói JAR/WAR, repackage Boot, generate source hay kiểm tra chất lượng.
2. **Xác định plugin cung cấp goal đó** và version được quản lý; tránh nhầm Maven plugin với dependency của ứng dụng.
3. **Kiểm tra plugin đã hoạt động qua default lifecycle/parent chưa.** Nếu là goal mới, thêm plugin vào `<build><plugins>`; nếu một goal đã bind sẵn, chỉ cần điều chỉnh đúng cấu hình.
4. **Đặt version/config dùng chung ở `<pluginManagement>`** khi nhiều module cùng sử dụng, giữ sự lựa chọn plugin ở module cần nó.
5. **Cấu hình execution rõ ràng:** `id` ổn định, `goal` chính xác, `phase` đúng hoặc default phase đã được xác nhận; cấu hình riêng tại execution khi cần.
6. **Khi kế thừa Spring Boot starter parent, xem `repackage` execution trước khi thêm mới.** Tùy chỉnh execution có sẵn bằng `id=repackage`.
7. **Khi chỉ import Spring Boot BOM, tự quản lý phần build plugin cần thiết.** BOM dependency management không thay cho plugin management.
8. **Kiểm tra effective POM và chạy đúng phase.** Quan sát goal thực sự chạy, tên artifact cuối cùng và thử `java -jar` trên artifact dùng để phân phối.

### Câu hỏi tự kiểm tra

**Câu 1:** Một parent POM chỉ khai báo `maven-antrun-plugin` với goal `run` trong `<pluginManagement>`, còn child không dùng plugin ở `<plugins>`. Goal tùy chỉnh có tự chạy khi `mvn package` không?

**Trả lời:** Không chỉ nhờ management. Child cần kích hoạt plugin (hoặc có binding phù hợp từ nguồn khác) để custom goal chạy.

**Câu 2:** Vì sao `maven-compiler-plugin` có thể chạy dù POM không tự liệt kê nó trong `<plugins>`?

**Trả lời:** Packaging `jar` có default lifecycle bindings, trong đó có `compiler:compile`. Cơ chế này khác việc management tự thêm một custom goal.

**Câu 3:** Parent Spring Boot đã quản lý `repackage` execution id `repackage`. Muốn đổi classifier sang `exec`, bạn nên tạo `id=make-exec` mới hay dùng id cũ?

**Trả lời:** Dùng **`id=repackage`** để tùy chỉnh execution kế thừa. Id mới có thể tạo một execution bổ sung và khiến goal chạy thêm lượt.

**Câu 4:** Một project chỉ import `spring-boot-dependencies` BOM và có `spring-boot-starter`. Có thể kết luận `mvn package` tạo executable JAR không?

**Trả lời:** Không. BOM quản lý version của dependencies; cần cấu hình Spring Boot Maven plugin và `repackage` execution/binding phù hợp.

**Câu 5:** Một execution không ghi `<phase>` vẫn chạy trong `package` được không?

**Trả lời:** Có, **nếu goal có default phase là `package`**, ví dụ `spring-boot:repackage`. Với goal không có default phase/binding khác, không ghi phase có thể khiến nó không chạy trong lifecycle.

**Câu 6:** Bỏ `<configuration>` của plugin và đặt cấu hình riêng trong execution có id khác nhau thì giúp gì?

**Trả lời:** Cho phép cùng plugin chạy nhiều execution với tham số khác nhau; cần kiểm soát id/phase để tránh chạy ngoài ý định.

## Tài liệu tham khảo chính thức

- Maven, [Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): cấu hình plugin, execution, phase và kế thừa.
- Maven, [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): default lifecycle bindings và thứ tự goal.
- Maven, [POM Reference](https://maven.apache.org/pom.html): cấu trúc `build`, `plugins`, `pluginManagement`, `executions`.
- Spring Boot, [Using the Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html): starter parent, BOM và cấu hình plugin.
- Spring Boot, [Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html): `repackage`, execution id và thứ tự đóng gói.

**Ghi nhớ:** **`plugins` xác định plugin đang được dùng; `pluginManagement` quản lý phiên bản/cấu hình của plugin; `execution` gắn goal vào phase và phân biệt các lần chạy bằng id.** Muốn biết điều gì thật sự xảy ra, xem **effective POM + lifecycle bindings + log Maven + artifact đầu ra**.
