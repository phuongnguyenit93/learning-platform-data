# Chẩn đoán lỗi task graph, Maven execution và cấu hình plugin bị ghi đè

## 1. Mục tiêu trong nhóm Chẩn đoán sự cố

Một lệnh Maven ngắn như `mvn clean verify` có thể kích hoạt nhiều lifecycle phases, plugin goals, executions kế thừa từ parent POM, executions trong profile và cấu hình lấy từ Maven settings. Khi build gặp lỗi, chỉ đọc `pom.xml` của module hiện tại thường chưa đủ để giải thích vì sao plugin chạy hai lần, không chạy, dùng sai version hoặc nhận giá trị khác với cấu hình vừa sửa.

Bài này tập trung vào ba nhóm sự cố:

1. **Task graph / execution plan:** Maven chạy những phase và plugin goals nào, theo thứ tự nào, goal nào được bind vào lifecycle và goal nào được gọi trực tiếp?
2. **Maven execution:** một goal chạy trong execution ID nào, được kích hoạt từ đâu, có chạy ở nhiều phase hay không, có bị gọi thêm do fork lifecycle không?
3. **Plugin configuration bị ghi đè hoặc merge:** cấu hình đến từ Super POM, parent POM, `pluginManagement`, `build/plugins`, profile, child POM hay command line; execution ID có khớp để override đúng execution hay tạo thêm execution mới?

Mục tiêu là xây quy trình chẩn đoán có thể lặp lại cho Spring Boot Maven Plugin, Maven Compiler, Surefire/Failsafe, JAR/WAR plugins và các plugin build khác.

### Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt Maven lifecycle, phase, plugin, goal, execution ID và execution plan.
- Đọc thứ tự thực thi của `clean`, `default` và `site` lifecycle.
- Xác định plugin goal được bind tự động theo packaging hay được thêm trong POM.
- Dùng `help:effective-pom`, `help:active-profiles`, `help:effective-settings` và `help:describe` để tìm cấu hình thật.
- Phân biệt `pluginManagement` với `build/plugins` và hiểu quy tắc merge execution theo ID.
- Phát hiện vì sao Spring Boot `repackage` chạy hai lần hoặc không chạy.
- Chọn đúng `build-image` và `build-image-no-fork`.
- Chẩn đoán profile, version, skip flags, reactor, plugin repositories và JDK mismatch.
- Tạo bản tái hiện tối thiểu, sửa đúng nguồn cấu hình và thêm quality gates cho CI.

**Phạm vi:** Maven 3.x/4.x và Spring Boot Maven Plugin **4.1.2**. Ví dụ tập trung vào Maven; khái niệm phase/goal/execution của Maven không nên bị nhầm với Gradle task graph.

## 2. Mô hình thực thi: lifecycle → phase → plugin goal → execution

Maven có ba built-in lifecycles:

| Lifecycle | Mục đích | Ví dụ phase |
| --- | --- | --- |
| `clean` | Xóa output của lần build trước | `pre-clean`, `clean`, `post-clean` |
| `default` | Validate, compile, test, package, verify, install, deploy | `validate`, `compile`, `package`, `verify`, `install`, `deploy` |
| `site` | Tạo và publish project documentation | `pre-site`, `site`, `post-site`, `site-deploy` |

Một **phase** là mốc trong lifecycle. Một **plugin goal** là tác vụ cụ thể thực hiện công việc. Một goal có thể được bind mặc định bởi packaging, được bind qua `<executions>` trong POM, có default phase do plugin khai báo hoặc chỉ chạy khi gọi trực tiếp.

Ví dụ với packaging `jar`, Maven có các binding phổ biến:

| Phase | Goal mặc định |
| --- | --- |
| `process-resources` | `resources:resources` |
| `compile` | `compiler:compile` |
| `process-test-resources` | `resources:testResources` |
| `test-compile` | `compiler:testCompile` |
| `test` | `surefire:test` |
| `package` | `jar:jar` |
| `install` | `install:install` |
| `deploy` | `deploy:deploy` |

Spring Boot Maven Plugin có thể thêm `spring-boot:repackage` vào `package` thông qua parent POM hoặc execution trong POM. Vì vậy phase `package` có thể chạy nhiều goal ở cùng một mốc.

### 2.1. Lệnh Maven được diễn giải thế nào?

~~~bash
mvn clean verify
~~~

Maven thực hiện clean lifecycle đến phase `clean`, sau đó chạy default lifecycle từ đầu đến phase `verify`, bao gồm các phase trước đó như validate, compile, test và package.

Lệnh sau có ý nghĩa khác:

~~~bash
mvn verify clean
~~~

Các phase được xử lý theo thứ tự xuất hiện trong command line: verify trước, sau đó clean. Kết quả cuối cùng có thể khiến bạn tưởng package không được tạo vì lệnh clean đã xóa output sau verify.

**Thói quen thông thường:** dùng `mvn clean verify` cho build sạch; dùng `mvn verify` cho vòng lặp nhanh khi không cần xóa output.

### 2.2. Phase không phải goal

~~~bash
mvn package
~~~

`package` là phase. Maven chạy tất cả phases trước đó của default lifecycle và các goals được bind tại những phases đó.

~~~bash
mvn spring-boot:repackage
~~~

`spring-boot:repackage` là plugin goal được gọi trực tiếp. Goal này cần archive nguồn đã được tạo bởi package phase. Nếu chạy riêng trong workspace sạch, nó có thể báo không tìm thấy JAR/WAR.

~~~bash
mvn package spring-boot:repackage
~~~

Lệnh này chạy package phase trước rồi gọi goal trực tiếp. Tuy nhiên, nếu parent POM đã bind `repackage` vào package phase, goal có thể chạy thêm lần nữa. Đừng dùng cách này như lệnh mặc định trước khi kiểm tra effective POM.

### 2.3. Vì sao một goal có thể chạy nhiều lần?

Một plugin có thể có nhiều executions: cùng goal ở nhiều phase; nhiều executions khác ID cùng bind vào một phase; execution kế thừa từ parent cộng với execution mới ở child; goal được bind lifecycle rồi gọi trực tiếp; hoặc goal fork lifecycle và gián tiếp kích hoạt goals khác.

Nhìn thấy hai dòng log cùng tên plugin không tự động có nghĩa Maven bị lỗi. Hãy đọc **execution ID, phase và nguồn cấu hình** của từng lần chạy.

## 3. Cách đọc execution plan và log Maven

Maven không dùng task graph kiểu Gradle. Để hiểu build đang chạy gì, kết hợp effective POM với debug log và thông tin plugin executions.

### 3.1. Chạy debug có kiểm soát

~~~bash
mvn -X -e -B -ntp clean verify
~~~

- `-X` bật debug logging, giúp xem Maven project/session, plugin resolution và mojo execution details.
- `-e` in exception stack trace.
- `-B` bật batch mode, phù hợp CI.
- `-ntp` tắt transfer progress để log dễ đọc hơn.

Trong debug output, tìm các dòng dạng:

~~~text
[DEBUG] Tasks:   [clean, verify]
[INFO] --- maven-clean-plugin:...:clean (...) @ catalog-service ---
[INFO] --- maven-resources-plugin:...:resources (...) @ catalog-service ---
[INFO] --- maven-compiler-plugin:...:compile (...) @ catalog-service ---
[INFO] --- spring-boot-maven-plugin:4.1.2:repackage (repackage) @ catalog-service ---
~~~

Đây là **ví dụ minh họa**; format và số dòng có thể khác theo Maven/plugin version. Dòng `--- groupId:artifactId:version:goal (execution-id) @ project ---` giúp xác định goal, execution ID và module đang được build.

Khi nghi goal chạy thiếu/thừa, ghi lại command line, Maven/Java version, project/module, phases, goals được bind, execution IDs, active profiles, goal trực tiếp/forked và lỗi đầu tiên. Đừng chỉ đọc 30 dòng cuối của log; lỗi gốc thường xuất hiện trước dòng `BUILD FAILURE`.

### 3.2. Bật log cho một module cụ thể

~~~bash
mvn -pl :catalog-service -am -X -e -B -ntp verify
~~~

`-pl :catalog-service` chọn module theo artifactId. `-am` yêu cầu build thêm các module mà module được chọn phụ thuộc vào trong reactor. Nếu bỏ `-am`, module có thể thất bại nếu dependency chưa được cài vào local repository.

### 3.3. Phân biệt các lần gọi plugin

Ví dụ log có:

~~~text
spring-boot-maven-plugin:4.1.2:repackage (repackage)
spring-boot-maven-plugin:4.1.2:build-image (default-cli)
~~~

Đây là hai goals khác nhau. Một lần đóng gói executable JAR và một lần tạo OCI image có thể là hành vi dự kiến. Hãy phân biệt goal, execution ID và phase trước khi kết luận duplicate execution.

## 4. Bốn lệnh Help Plugin quan trọng nhất

### 4.1. Xem effective POM

~~~bash
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom.xml
~~~

Effective POM là kết quả sau khi Maven xử lý Super POM, parent inheritance, property interpolation, plugin management/declarations, active profiles và cấu hình merge theo Maven model.

`-Dverbose` yêu cầu thêm comment về nguồn gốc của các phần tử khi được hỗ trợ. Mở `target/effective-pom.xml` và tìm plugin coordinates, version, executions, phase, goals, configuration và skip.

**Effective POM không phải execution log.** Nó cho thấy cấu hình Maven đã hợp nhất; muốn biết goal có thật sự chạy hay không, đối chiếu debug output.

### 4.2. Xem active profiles

~~~bash
mvn help:active-profiles
mvn help:all-profiles
~~~

Lệnh đầu cho biết profile nào đang active và nguồn kích hoạt như POM, user settings hoặc global settings. Lệnh sau liệt kê profile có thể dùng.

~~~bash
mvn -Pdev,container clean verify
~~~

Profile có thể được kích hoạt theo JDK, OS, property hoặc file tồn tại. Máy local và CI có thể active profile khác nhau dù command line giống nhau.

### 4.3. Xem effective settings

~~~bash
mvn help:effective-settings -Doutput=target/effective-settings.xml
~~~

Settings có thể ảnh hưởng local repository path, mirrors, repositories, plugin repositories, active settings profiles, proxy và server credentials.

**Bảo mật:** effective settings có thể chứa thông tin nhạy cảm. Không upload nguyên file lên ticket/chat công khai; redact server credentials, tokens, internal URLs và proxy secrets.

### 4.4. Xem goal và parameters của plugin

~~~bash
mvn help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin:4.1.2 -Dgoal=repackage -Ddetail
~~~

Dùng lệnh tương tự cho `build-image` hoặc plugin khác. Kết quả giúp xác nhận goal, parameter name/type/default và user property nếu goal hỗ trợ.

Đừng đoán tên property từ tên XML parameter. Một plugin có thể map `skip` sang user property `spring-boot.build-image.skip`; tên user property không nhất thiết giống XML node.

## 5. Nguồn cấu hình Maven: cái gì đang thắng?

Khi plugin nhận giá trị khác với mong đợi, kiểm tra các nguồn mà Maven đã merge:

~~~text
Super POM
   |
Parent POM chain
   |
pluginManagement + build/plugins
   |
Active profiles (POM / settings / global settings)
   |
Child module POM and its active profile effects
   |
Command-line properties and plugin-supported user properties
   |
Effective plugin configuration for this execution
~~~

Đây là sơ đồ khái quát, không phải thứ tự override tuyệt đối cho mọi parameter. Maven có quy tắc model merge và property interpolation; parameter cụ thể còn phụ thuộc plugin và user property mà mojo khai báo. **Effective POM + help:active-profiles + debug log** mới là căn cứ để xác định giá trị cuối cùng.

### 5.1. Parent POM

Parent có thể khai báo plugin version, configuration và executions. Nếu plugin/execution được kế thừa, module con có thể nhận hành vi mà không thấy toàn bộ cấu hình trong POM của module.

Kiểm tra parent coordinates/version, parent được resolve từ `relativePath` hay repository, corporate parent trung gian, execution ID và `inherited=false`.

### 5.2. pluginManagement và build/plugins

| Vị trí | Vai trò |
| --- | --- |
| `build/pluginManagement/plugins` | Quản lý version/default configuration cho plugin khi plugin được khai báo sử dụng |
| `build/plugins` | Khai báo plugin được dùng trong build; executions ở đây có thể bind goal vào lifecycle |

Ví dụ parent POM:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Child POM khai báo plugin để kích hoạt cấu hình đã quản lý:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Nếu chỉ có plugin trong `pluginManagement` mà không có plugin declaration ở `build/plugins` (hoặc cấu hình/packaging khác kích hoạt nó), đừng mặc định plugin sẽ được chạy như execution bổ sung.

### 5.3. Profile

Profile có thể được định nghĩa trong project POM, user settings `~/.m2/settings.xml` hoặc global Maven settings `${maven.home}/conf/settings.xml`. Profile có thể kích hoạt bằng explicit `-Pprofile-id`, JDK version, OS, system/CLI property, packaging hoặc file tồn tại/không tồn tại.

Profile definitions không được kế thừa như một khối nguyên vẹn xuống child POM; **các hiệu ứng của profile đang active**, ví dụ plugin/configuration được thêm vào effective model, có thể ảnh hưởng module con.

### 5.4. Command-line properties

~~~bash
mvn -Dspring-boot.build-image.skip=true verify
~~~

Lệnh này chỉ có ý nghĩa nếu goal/parameter thực sự khai báo user property tương ứng. Hãy dùng `help:describe` hoặc documentation của đúng plugin version.

Đừng giả định `mvn -Dskip=true verify` sẽ skip mọi plugin. Property `skip` có thể thuộc plugin này nhưng không tác động plugin khác; nhiều plugin dùng tên property riêng.

## 6. Quy tắc merge executions theo ID

Maven merge plugin executions theo ID:

- **Cùng execution ID** trong parent và child: cấu hình của child được merge/override theo quy tắc model merge cho execution đó.
- **Khác execution ID:** hai executions được giữ riêng và có thể cùng chạy.
- **Nhiều execution ID trong cùng POM:** có thể chạy nhiều lần, mỗi lần với phase/configuration riêng.
- Profile cũng có thể thêm hoặc thay đổi plugin executions.

Ví dụ parent có:

~~~xml
<plugin>
    <groupId>org.example</groupId>
    <artifactId>demo-plugin</artifactId>
    <version>1.0.0</version>
    <executions>
        <execution>
            <id>generate-report</id>
            <phase>prepare-package</phase>
            <goals><goal>report</goal></goals>
            <configuration><format>json</format></configuration>
        </execution>
    </executions>
</plugin>
~~~

Child muốn đổi format của đúng execution đó:

~~~xml
<plugin>
    <groupId>org.example</groupId>
    <artifactId>demo-plugin</artifactId>
    <executions>
        <execution>
            <id>generate-report</id>
            <configuration><format>xml</format></configuration>
        </execution>
    </executions>
</plugin>
~~~

Cùng ID `generate-report` giúp child sửa execution được kế thừa. Nếu child đặt ID khác, ví dụ `generate-report-xml`, Maven có thể giữ cả hai executions và chạy cả JSON lẫn XML.

### 6.1. Dùng sai ID tạo execution trùng

Giả sử parent có ID `repackage`, child thêm:

~~~xml
<execution>
    <id>custom-repackage</id>
    <goals><goal>repackage</goal></goals>
</execution>
~~~

Child vừa giữ execution `repackage` của parent, vừa thêm `custom-repackage`. Cả hai có thể chạy trong lifecycle, gây log repackage xuất hiện hai lần, artifact bị ghi đè/attach ngoài ý muốn hoặc classifier khác nhau.

### 6.2. Cùng ID không có nghĩa mọi XML node bị thay toàn bộ

Maven merge cấu hình XML theo model rules. Một số child elements có thể được merge với parent; cấu hình list/collection có thể cần điều khiển merge. Nếu thật sự muốn thay toàn bộ configuration tree, Maven có hỗ trợ attributes như `combine.self="override"` và `combine.children="append"` ở một số vị trí.

**Không dùng các attributes này để chữa đoán mò.** Trước hết xem effective POM; chỉ sử dụng khi hiểu cấu trúc cấu hình và muốn thay đổi cách merge đó.

### 6.3. Plugin-level config và execution-level config

~~~xml
<plugin>
    <groupId>org.example</groupId>
    <artifactId>demo-plugin</artifactId>
    <configuration><timeout>30</timeout></configuration>
    <executions>
        <execution>
            <id>fast-check</id>
            <phase>verify</phase>
            <goals><goal>check</goal></goals>
            <configuration><timeout>5</timeout></configuration>
        </execution>
    </executions>
</plugin>
~~~

Execution-level configuration có thể cung cấp giá trị riêng cho `fast-check`; plugin-level configuration cung cấp cấu hình dùng chung. Khi parameter khác mong đợi, kiểm tra cả hai cấp và kết quả merge.

## 7. Spring Boot Maven Plugin: lỗi repackage bị chạy hai lần

Spring Boot Maven Plugin **4.1.2** cung cấp goal `spring-boot:repackage` để biến JAR/WAR đã package thành executable archive có loader và dependencies phù hợp cho `java -jar`.

### 7.1. Khi dùng spring-boot-starter-parent

Spring Boot parent đã cấu hình execution ID **`repackage`**. Vì vậy, để thêm plugin vào project thường chỉ cần khai báo plugin:

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

Không thêm execution thứ hai nếu mục tiêu chỉ là bật cấu hình đã có trong parent.

### 7.2. Custom classifier đúng cách

Nếu muốn giữ original JAR và tạo executable JAR với classifier `exec`, hãy customize đúng execution ID mà parent đã khai báo:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration><classifier>exec</classifier></configuration>
        </execution>
    </executions>
</plugin>
~~~

**Không cần lặp lại goal hoặc phase** trong ví dụ này vì parent đã cung cấp execution `repackage` với goal tương ứng. Child chỉ thay configuration.

### 7.3. Lỗi: repackage chạy hai lần

Một cấu hình dễ gây lỗi:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>custom-repackage</id>
            <goals><goal>repackage</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Nếu parent đã có ID `repackage`, ID `custom-repackage` là execution khác. Maven có thể chạy cả hai.

**Cách chẩn đoán:**

~~~bash
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom.xml
mvn -X -B -ntp package
~~~

Tìm `spring-boot-maven-plugin`, các execution IDs và số lần goal `repackage` xuất hiện.

**Cách sửa:** nếu dùng starter parent, sửa execution có ID `repackage`; bỏ execution bổ sung nếu không có mục tiêu riêng. Nếu không dùng starter parent, tự khai báo một execution duy nhất cho goal này.

### 7.4. Không dùng starter parent

Nếu project chỉ import `spring-boot-dependencies` hoặc dùng corporate parent khác, cần khai báo plugin version và execution rõ ràng:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <executions>
        <execution>
            <id>repackage</id>
            <phase>package</phase>
            <goals><goal>repackage</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Không copy cả execution này vào project đang dùng Spring Boot starter parent mà không kiểm tra effective POM, vì parent có thể đã cung cấp một execution cùng chức năng.

### 7.5. Lỗi main class và manifest

Nếu executable JAR báo không tìm thấy main class:

- Kiểm tra application có `public static void main(String[] args)` không.
- Kiểm tra có nhiều main classes khiến plugin chọn sai không.
- Dùng `mainClass` của Spring Boot Maven Plugin để chỉ định entry point.
- Kiểm tra `Main-Class` và `Start-Class` trong manifest.
- Đừng sửa manifest của `maven-jar-plugin` rồi kỳ vọng Spring Boot repackage giữ nguyên; Spring Boot plugin quản lý các entry này.

Ví dụ cấu hình:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration><mainClass>com.example.catalog.CatalogApplication</mainClass></configuration>
</plugin>
~~~

Kiểm tra artifact:

~~~bash
jar tf target/catalog-service-1.0.0.jar
unzip -p target/catalog-service-1.0.0.jar META-INF/MANIFEST.MF
~~~

Trên Windows có thể dùng `jar` và PowerShell để đọc manifest. Nếu lệnh `unzip` không có, dùng công cụ archive tương ứng.

### 7.6. Lỗi classifier và module được dùng làm dependency

Executable Boot JAR đặt application classes trong `BOOT-INF/classes`. Một module khác không thể sử dụng archive này như JAR thư viện Java thông thường.

Nếu module vừa cần executable archive để chạy vừa cần artifact thường để module khác compile, hãy giữ original JAR, attach executable archive với classifier, đảm bảo consumer phụ thuộc đúng artifact/classifier và không để repackage thay thế artifact thư viện mà module khác cần đọc classes.

## 8. Spring Boot build-image: fork lifecycle và no-fork

Đây là lỗi execution thường gặp khi bind goal tạo OCI image vào Maven lifecycle.

### 8.1. Gọi trực tiếp trên command line

~~~bash
mvn spring-boot:build-image
~~~

`spring-boot:build-image` fork lifecycle để đảm bảo `package` đã chạy trước khi image được tạo. Đây là goal phù hợp cho command-line invocation.

### 8.2. Bind vào lifecycle trong POM

Nếu muốn image build tự động chạy khi đến phase `package`, dùng `build-image-no-fork`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <executions>
        <execution>
            <id>container-image</id>
            <phase>package</phase>
            <goals><goal>build-image-no-fork</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

`build-image-no-fork` không fork lifecycle. Nó phù hợp khi goal đã được gắn vào phase của build.

### 8.3. Vì sao dùng sai goal gây vòng lặp hoặc chạy lặp?

Nếu bind `build-image` vào `package`, goal lại fork lifecycle để chạy package. Lệnh package được gọi từ execution có thể kích hoạt lại execution image build. Đây là lý do Spring Boot cung cấp goal no-fork riêng.

| Cách gọi | Goal |
| --- | --- |
| Gọi trực tiếp từ terminal | `spring-boot:build-image` |
| Khai báo execution trong POM | `spring-boot:build-image-no-fork` |

Không dùng cả hai cách đồng thời nếu không có lý do rõ ràng, nếu không image có thể được build nhiều lần trong một lệnh.

### 8.4. Skip và image configuration

~~~bash
mvn -Dspring-boot.build-image.skip=true verify
~~~

Dùng để tạm bỏ image build khi plugin/goal hỗ trợ property này. Trong CI, tốt hơn nên tách profile/container-image riêng và chỉ bật ở job cần Docker daemon.

Ví dụ profile:

~~~xml
<profiles>
    <profile>
        <id>container-image</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <id>container-image</id>
                            <phase>package</phase>
                            <goals><goal>build-image-no-fork</goal></goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Kích hoạt:

~~~bash
mvn -Pcontainer-image clean package
~~~

Khi profile không active, execution image build không được thêm vào effective model. Kiểm tra bằng `help:active-profiles` và `help:effective-pom`.

## 9. Plugin version và plugin resolution

Một build có thể dùng plugin version khác mong đợi nếu POM không pin version hoặc parent/pluginManagement thay đổi.

### 9.1. Luôn pin plugin version

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
</plugin>
~~~

Đặt version ở `pluginManagement` của parent để các module dùng cùng version; module cần khai báo plugin trong `build/plugins` nếu cần kích hoạt cấu hình đó.

### 9.2. Plugin repository khác dependency repository

Maven có `repositories` để tải project dependencies và `pluginRepositories` để tải Maven plugins/plugin dependencies.

Nếu project dependency tải được nhưng plugin không resolve, kiểm tra `pluginRepositories`, mirror trong settings và network/proxy. Một mirror có thể áp dụng cho cả central và plugin repositories theo cấu hình `mirrorOf`.

### 9.3. Lỗi “No plugin found for prefix”

~~~text
No plugin found for prefix 'spring-boot' in the current project
~~~

Nguyên nhân thường gặp: plugin prefix chưa resolve, plugin chưa khai báo trong POM, version/coordinates sai, network/mirror không truy cập plugin metadata hoặc lệnh chạy từ thư mục không có POM mong muốn.

Thử gọi đầy đủ coordinates:

~~~bash
mvn org.springframework.boot:spring-boot-maven-plugin:4.1.2:help
~~~

Nếu full coordinates vẫn không resolve, kiểm tra repository/mirror và credentials. Không thêm plugin vào dependency `<dependencies>`; Maven build plugin phải được cấu hình dưới `<build><plugins>`.

### 9.4. Lỗi plugin dependency resolution

Nếu Maven báo không tải được plugin hoặc plugin dependency, xác định artifact/version trong log, kiểm tra `help:effective-settings`, `pluginRepositories`, proxy, certificate trust, credentials và compatibility của Maven/JDK.

Không xóa toàn bộ local repository ngay lập tức. Nếu nghi cache artifact hỏng, chỉ xóa đúng thư mục artifact/version liên quan sau khi xác định path và repository nguồn.

## 10. JDK, Maven runtime và compiler configuration

Một nguồn lỗi khác là Maven chạy bằng JDK khác với Java target mà project mong đợi.

~~~bash
mvn -version
java -version
~~~

`mvn -version` hiển thị Maven version, Java version và Java home mà Maven process đang dùng. `java -version` chỉ hiển thị executable java tìm thấy trong PATH; hai giá trị có thể khác nhau nếu `JAVA_HOME` và PATH không đồng bộ.

Ví dụ Spring Boot Java 17:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

Spring Boot parent thường cấu hình compiler release từ `java.version`. Nếu dùng corporate parent hoặc Maven Compiler Plugin tự cấu hình, kiểm tra effective POM để biết giá trị `source`, `target` hoặc `release` cuối cùng.

Nếu Maven chạy trên JDK 21 nhưng cần compile bằng JDK 17, Maven Toolchains Plugin có thể chọn compiler toolchain riêng. Khi đó `mvn -version` vẫn có thể báo Maven runtime JDK 21, trong khi compiler toolchain là JDK 17. Kiểm tra log toolchains và compiler plugin.

## 11. Skip flags: vì sao tests hoặc plugin vẫn chạy?

Nhiều plugin có skip property riêng. Một property chung không nhất thiết skip mọi plugin.

### 11.1. `-DskipTests`

~~~bash
mvn -DskipTests package
~~~

Với Maven Surefire, property này bỏ qua việc chạy test nhưng test sources vẫn được compile. Đây là lựa chọn tạm thời khi muốn build/package nhanh; không nên thay thế quality gates trong release.

### 11.2. `-Dmaven.test.skip=true`

~~~bash
mvn -Dmaven.test.skip=true package
~~~

Property này được các plugin Maven compiler/Surefire/Failsafe hỗ trợ để bỏ cả test compilation và test execution. Dùng thận trọng vì test code không được compile.

### 11.3. Integration tests và plugin skip riêng

Failsafe có property riêng như `skipITs`; kiểm tra đúng version plugin và config. Đừng giả định `-DskipTests` hoặc `-DskipITs` có cùng behavior trong mọi plugin.

Spring Boot build-image hỗ trợ user property:

~~~bash
mvn -Dspring-boot.build-image.skip=true verify
~~~

Nếu goal vẫn chạy, kiểm tra goal nào được bind, plugin version có hỗ trợ user property đó không, có nhiều executions hay profile khác thêm execution không, và effective POM có giá trị skip cuối cùng là gì.

## 12. Multi-module reactor và execution bị chạy ở sai module

Trong reactor, một plugin execution ở parent có thể được kế thừa bởi nhiều module. Khi build một module, Maven có thể chạy plugin ở module khác tùy packaging và cấu hình.

~~~bash
mvn -pl :catalog-service -am verify
mvn -pl :catalog-service -amd verify
mvn -N validate
mvn -rf :catalog-service verify
~~~

- `-pl` chọn project/module.
- `-am` build thêm các module mà project được chọn phụ thuộc.
- `-amd` build các module phụ thuộc vào project được chọn.
- `-N` tắt recursive build.
- `-rf` resume reactor từ project được chỉ định.

Với mỗi module bị lỗi, chạy `help:effective-pom -Dverbose`, `help:active-profiles` và `-X -e` riêng cho module đó. Đừng chỉ inspect root POM; child POM có thể override plugin version hoặc thêm execution/profile.

Parent aggregator thường có `<packaging>pom</packaging>`. Packaging `pom` không bind goals compile/package giống module `jar`. Tuy nhiên, executions khai báo trong parent `<build><plugins>` có thể được kế thừa và chạy trong child modules nếu được cấu hình kế thừa.

Nếu một plugin chỉ nên chạy ở một module, chuyển execution sang module đó, dùng profile phù hợp hoặc đặt `<inherited>false</inherited>` khi muốn ngăn execution/plugin config truyền xuống children.

## 13. Quy trình tìm nguồn cấu hình bị ghi đè

Khi parameter cuối cùng khác giá trị bạn đặt:

1. Chụp trạng thái: `mvn -version`, `mvn help:active-profiles` và `mvn help:effective-pom -Dverbose -Doutput=target/effective-pom.xml`.
2. Tìm plugin coordinates, version, execution ID, phase, goals, configuration và skip parameters.
3. Đọc verbose comments để xác định node đến từ parent, child hoặc profile.
4. Dùng `help:describe` để xác minh parameter, default và user property.
5. Sửa đúng nguồn: version ở parent/pluginManagement; ID execution; profile activation; parameter XML/user property; hoặc vị trí module.
6. Chạy lại `mvn clean verify`, xuất effective POM mới và so sánh debug log/artifact.

Không chỉnh nhiều nguồn cùng lúc; nếu thay parent, child, profile và command line trong một lượt, bạn sẽ khó biết sửa đổi nào thực sự giải quyết lỗi.

## 14. Ví dụ tái hiện: parent và child tạo hai execution

Parent POM có:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <goals><goal>repackage</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Child muốn thêm classifier nhưng khai báo sai ID:

~~~xml
<execution>
    <id>exec-archive</id>
    <goals><goal>repackage</goal></goals>
    <configuration><classifier>exec</classifier></configuration>
</execution>
~~~

Kết quả có thể là hai executions: `repackage` từ parent và `exec-archive` từ child. Sửa child bằng cách dùng ID `repackage` và chỉ cung cấp configuration cần thay đổi:

~~~xml
<execution>
    <id>repackage</id>
    <configuration><classifier>exec</classifier></configuration>
</execution>
~~~

Sau đó xem effective POM và debug log để xác nhận chỉ còn execution mong muốn.

## 15. Ví dụ tái hiện: build-image bị fork lặp

Cấu hình sai khi bind:

~~~xml
<execution>
    <id>image</id>
    <phase>package</phase>
    <goals><goal>build-image</goal></goals>
</execution>
~~~

`build-image` fork lifecycle để đảm bảo package phase đã chạy. Khi được bind vào package, nó có thể kích hoạt lại quá trình package và lặp execution.

Cấu hình đúng cho lifecycle binding:

~~~xml
<execution>
    <id>image</id>
    <phase>package</phase>
    <goals><goal>build-image-no-fork</goal></goals>
</execution>
~~~

Hoặc không bind vào lifecycle và chỉ chạy `mvn spring-boot:build-image`. Chọn một cách phù hợp với pipeline; không vừa bind goal vừa gọi trực tiếp goal đó trong cùng command nếu không muốn tạo image nhiều lần.

## 16. Bảng triệu chứng, nguyên nhân và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra và sửa |
| --- | --- | --- |
| Plugin goal không chạy ở `package` | Chỉ khai báo trong pluginManagement hoặc chưa có execution/binding | Xem effective POM; thêm plugin declaration/execution đúng nơi |
| Plugin chạy hai lần | Parent và child dùng execution IDs khác nhau; goal được gọi trực tiếp thêm lần nữa | Xem IDs trong debug log; merge cùng ID hoặc xóa execution dư |
| Plugin version khác mong đợi | Parent/pluginManagement/profile override | Xem effective POM verbose và plugin coordinates |
| Configuration trong child không có tác dụng | Execution ID không khớp hoặc parameter bị merge từ nguồn khác | Dùng cùng execution ID; inspect effective POM |
| Configuration bị nhân đôi | Executions khác ID được merge thành hai executions | Kiểm tra IDs parent/child/profile |
| `repackage` báo không tìm thấy archive | Goal chạy trước package hoặc source classifier sai | Chạy package trước; kiểm tra phase/order/classifier |
| `repackage` không chạy | Không dùng starter parent và chưa khai báo execution | Thêm execution goal repackage vào package |
| `repackage` chạy nhưng JAR không executable | Main class/manifest/layout/dependencies không đúng | Kiểm tra Start-Class, Main-Class và archive entries |
| `build-image` chạy lặp hoặc fork recursion | Bind build-image vào lifecycle thay vì no-fork | Dùng build-image-no-fork khi bind |
| `build-image` không chạy trên CI | Profile không active hoặc skip property bật | help:active-profiles, effective POM và skip config |
| `No plugin found for prefix` | Prefix/repository metadata không resolve | Dùng full coordinates, kiểm tra pluginRepositories/mirror |
| Plugin không resolve dependency | Proxy, credentials, plugin repository hoặc version không tồn tại | Kiểm tra effective settings và debug transfer logs |
| `Unknown lifecycle phase` | Gõ sai phase hoặc property bị parse thành goal/phase | Kiểm tra command line quoting và mvn -h |
| `BUILD SUCCESS` nhưng test không chạy | Skip property hoặc Surefire/Failsafe config | Kiểm tra test reports, skipTests/skipITs |
| Test compile vẫn chạy khi skipTests | skipTests chỉ skip execution, không bỏ test compilation | Dùng maven.test.skip nếu thật sự muốn skip compile và run |
| Local chạy, CI lỗi khác | Active profiles, JDK, settings, OS hoặc Maven version khác | So mvn -v, active profiles, effective POM/settings |
| Module A chạy plugin, module B không | Packaging/module POM/profile/inheritance khác nhau | Inspect effective POM từng module |
| Parent plugin chạy trong mọi child | Execution/plugin config được kế thừa | Đặt execution ở module cần dùng hoặc inherited=false |
| Maven dùng sai Java | JAVA_HOME/PATH/toolchains không đồng bộ | mvn -version, kiểm tra toolchains/compiler release |
| Build không tìm thấy plugin sau khi đổi mirror | Plugin repository chưa mirror hoặc credentials sai | Kiểm tra pluginRepositories và settings mirror |
| Build tạo JAR cũ sau sửa source | Package không chạy hoặc source/module không nằm trong reactor | clean package, xác minh module và output timestamp |
| `-Dskip=true` không skip plugin | Plugin không khai báo user property đó | Dùng help:describe và đúng property của goal |
| Debug log quá lớn hoặc lộ thông tin | Bật -X và chia sẻ log nguyên trạng | Redact secrets, URLs nội bộ, tokens và environment |

## 17. Bộ lệnh chẩn đoán nhanh

~~~bash
mvn -version
mvn help:active-profiles
mvn help:effective-pom -Dverbose -Doutput=target/effective-pom.xml
mvn help:effective-settings -Doutput=target/effective-settings.xml
mvn help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin:4.1.2 -Dgoal=repackage -Ddetail
mvn -X -e -B -ntp clean verify
~~~

Với multi-module:

~~~bash
mvn -pl :catalog-service -am -X -e -B -ntp verify
~~~

Khi debug xong, lưu command line chính xác và working directory, Maven version, Java runtime/toolchain, active profiles, effective POM đã redact, plugin coordinates/version/execution IDs, lỗi đầu tiên, artifact output thực tế và module pass/fail trong reactor.

**Không gửi effective settings hoặc debug log thô lên hệ thống công khai.** Những file này có thể chứa internal repository URLs, paths, system properties hoặc credential-related details.

## 18. Quy trình sửa lỗi an toàn trong CI

1. **Giữ nguyên lệnh build tái hiện lỗi.** Không thay nhiều flags cùng lúc.
2. **Ghi toolchain:** Maven, Java runtime, compiler toolchain và OS.
3. **Xác định module:** project root, `-pl`, `-am`, packaging và artifactId.
4. **Đọc active profiles:** xác nhận CI có bật profile khác local không.
5. **Xuất effective POM:** xem plugin versions, executions, phases, configuration và nguồn merge.
6. **Đọc debug log:** xác nhận goal thật sự chạy, execution ID và thứ tự.
7. **Xác định một nguyên nhân cụ thể:** binding thiếu, execution dư, version sai, skip, fork, module hoặc plugin resolution.
8. **Sửa một nguồn cấu hình:** parent, pluginManagement, child plugin, profile hoặc command line.
9. **Chạy lại clean verify:** kiểm tra cả tests và packaged artifact.
10. **So sánh output:** effective POM, execution count, archive manifest và image build result.
11. **Thêm regression check:** CI fail nếu execution ngoài ý muốn xuất hiện hoặc artifact không đúng.
12. **Lưu diagnostics đã redact:** để lần sau có thể so sánh giữa local và CI.

### Quality gates đề xuất

- [ ] Maven/Java versions được pin và ghi lại.
- [ ] Plugin versions quan trọng được quản lý tường minh.
- [ ] Active profiles được xác định trong CI.
- [ ] Effective POM có thể xuất để điều tra.
- [ ] Spring Boot repackage chỉ chạy đúng execution cần thiết.
- [ ] Build-image dùng goal phù hợp với cách gọi (fork trực tiếp, no-fork khi bind).
- [ ] Test reports chứng minh tests đã chạy.
- [ ] Executable JAR manifest/classifier được xác minh.
- [ ] Image build không bị lặp hoặc bị skip ngoài ý muốn.
- [ ] Reactor module list và build order đúng.
- [ ] Debug logs và settings được bảo vệ/redact.
- [ ] Build thành công từ clean workspace và không phụ thuộc output cũ.

## 19. Bài tập tự kiểm tra

**1. Phase và goal khác nhau thế nào?**

Đáp án: Phase là mốc trong lifecycle; goal là tác vụ của plugin được bind vào phase hoặc được gọi trực tiếp.

**2. Vì sao `mvn package` chạy nhiều plugin?**

Đáp án: Packaging mặc định bind nhiều plugin goals vào các phases trước và tại package; POM có thể bổ sung executions.

**3. `pluginManagement` có tự chạy plugin không?**

Đáp án: Nó quản lý cấu hình/version khi plugin được tham chiếu sử dụng; không nên xem nó như plugin execution được kích hoạt độc lập.

**4. Parent có execution ID `repackage`, child thêm ID `custom-repackage`. Điều gì xảy ra?**

Đáp án: Hai IDs khác nhau nên executions có thể cùng tồn tại và chạy cả hai. Dùng ID `repackage` nếu muốn customize execution đã kế thừa.

**5. `help:effective-pom -Dverbose` dùng để làm gì?**

Đáp án: Hiển thị POM sau inheritance, interpolation và active profiles, kèm comment nguồn gốc cấu hình khi có hỗ trợ.

**6. Vì sao `help:active-profiles` quan trọng?**

Đáp án: Profile có thể thêm plugin, execution hoặc thay property; local và CI có thể active profile khác nhau.

**7. Vì sao không bind `spring-boot:build-image` trực tiếp vào package phase?**

Đáp án: Goal này fork lifecycle để bảo đảm package đã chạy. Khi bind vào lifecycle, dùng `build-image-no-fork`.

**8. Khi nào dùng `spring-boot:repackage`?**

Đáp án: Sau khi JAR/WAR thường đã được tạo; với starter parent, execution repackage đã được cấu hình sẵn.

**9. `-DskipTests` khác `-Dmaven.test.skip=true` thế nào?**

Đáp án: skipTests bỏ việc chạy test nhưng vẫn compile test sources; maven.test.skip có thể bỏ cả compile và execution tests.

**10. Vì sao plugin không resolve dù project dependency resolve được?**

Đáp án: Plugin có thể cần pluginRepositories/mirror/credentials riêng hoặc plugin artifact chưa có trên repository hiện tại.

**11. Maven `-version` và `java -version` có thể khác nhau không?**

Đáp án: Có. Maven process dùng Java được xác định bởi JAVA_HOME/Maven launcher; executable java trong PATH có thể là bản khác. Compiler toolchain còn có thể chọn JDK riêng.

**12. Effective POM đã đúng nhưng goal vẫn chạy hai lần, kiểm tra gì tiếp?**

Đáp án: Debug log để tìm direct invocation, multiple executions, forked lifecycle, profile hoặc reactor module khác đang chạy cùng plugin.

## 20. Tài liệu tham khảo chính thức

1. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
2. [Apache Maven — Introduction to the POM and Inheritance](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
3. [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
4. [Apache Maven — Guide to Configuring Default Mojo Executions](https://maven.apache.org/guides/mini/guide-default-execution-ids.html)
5. [Apache Maven Help Plugin — Plugin Details](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html)
6. [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
7. [Apache Maven — Running Maven](https://maven.apache.org/run.html)
8. [Spring Boot 4.1.2 Maven Plugin — Goals](https://docs.spring.io/spring-boot/maven-plugin/goals.html)
9. [Spring Boot 4.1.2 — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
10. [Spring Boot 4.1.2 — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
11. [Spring Boot — Using the Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
12. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
