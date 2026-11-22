# Khai báo Maven plugin bằng groupId, artifactId và version

## 1. Plugin là gì và vì sao phải khai đúng ba tọa độ?

Maven không tự biết cách làm mọi công việc build. Maven điều phối các **lifecycle phase** như `compile`, `test`, `package`; các **plugin** cung cấp **goal** để thực hiện hành động cụ thể, chẳng hạn biên dịch Java, chạy JUnit, tạo JAR, sinh báo cáo hay chạy một công cụ bổ sung.

Mỗi plugin Maven là một artifact được nhận diện bằng bộ tọa độ:

~~~text
groupId:artifactId:version
~~~

Ví dụ:

~~~text
org.apache.maven.plugins:maven-compiler-plugin:3.14.1
~~~

Bộ tọa độ này nói rõ **plugin nào, của nhóm phát hành nào, ở phiên bản nào**. Khi Maven tải một plugin từ repository, nó không chỉ tìm một từ như “compiler”; Maven phải phân giải artifact plugin cùng các dependency cần để chạy plugin đó.

Khai báo đủ ba trường trong `pom.xml`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
</plugin>
~~~

Đây là **khai báo plugin**, không phải một khai báo dependency ứng dụng. Đặt nó trong `<build><plugins>` hoặc quản lý ở `<build><pluginManagement><plugins>` tùy mục đích.

### Mục tiêu sau bài học

Sau khi học xong, bạn có thể:

1. Giải thích đúng vai trò của `groupId`, `artifactId` và `version` trong một Maven plugin.
2. Viết POM hợp lệ khai plugin trong `build/plugins`, phân biệt với `dependencies` và `reporting/plugins`.
3. Hiểu khi nào có thể lược `groupId`, vì sao **không nên bỏ `version`** và hậu quả của việc dùng plugin version không được kiểm soát.
4. Phân biệt **plugin**, **goal**, **phase**, **execution**, **configuration** và **pluginManagement**.
5. Gọi goal bằng prefix hoặc bằng tọa độ đầy đủ, hiểu vì sao gọi goal trực tiếp không giống gọi lifecycle phase.
6. Tạo dự án **Maven 3.9.x + Java 17 + JUnit 5** chạy được; khai Compiler, Surefire, JAR và AntRun Plugin, kiểm tra log, file marker và stdout.
7. Đọc effective POM, kiểm tra plugin đã được chọn, xử lý lỗi `plugin not found`, sai version, không phân giải được prefix hoặc sai vị trí XML.
8. Áp dụng quy tắc quản lý phiên bản plugin trong parent POM để nhiều module build nhất quán.

Các phiên bản minh họa đã được ghim để bài học có đầu vào cụ thể, **không phải tuyên bố đó luôn là các bản mới nhất**. Khi nâng cấp plugin cho dự án thật, cần kiểm tra yêu cầu Maven/JDK và release notes của phiên bản muốn dùng.

## 2. Giải thích từng thành phần của tọa độ plugin

### 2.1. groupId: ai phát hành plugin?

`groupId` phân biệt nhóm dự án/tổ chức sở hữu artifact. Với plugin chính thức của Apache Maven, thường gặp:

~~~xml
<groupId>org.apache.maven.plugins</groupId>
~~~

Ví dụ các artifact cùng group:

~~~text
org.apache.maven.plugins:maven-compiler-plugin
org.apache.maven.plugins:maven-surefire-plugin
org.apache.maven.plugins:maven-jar-plugin
org.apache.maven.plugins:maven-resources-plugin
org.apache.maven.plugins:maven-dependency-plugin
~~~

Plugin cộng đồng hoặc plugin nội bộ có thể thuộc groupId khác, chẳng hạn `org.codehaus.mojo` hoặc một groupId do tổ chức sở hữu. **Không được giả định mọi plugin Maven đều mang groupId `org.apache.maven.plugins`.**

Điểm đặc biệt ở Maven 3: nếu khai plugin trong `build/plugins` hoặc `reporting/plugins` mà **bỏ `<groupId>`**, Maven dùng mặc định `org.apache.maven.plugins`. Ví dụ:

~~~xml
<plugin>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
</plugin>
~~~

Với Maven Compiler Plugin chính thức, khai báo rút gọn trên được hiểu như có `groupId=org.apache.maven.plugins`. Tuy nhiên, để dễ review và tránh nhầm với plugin bên thứ ba, bài này **ưu tiên khai đầy đủ `groupId`**.

Nếu một plugin thực sự thuộc `org.codehaus.mojo` hoặc `com.example.build`, lược `groupId` khiến Maven tìm ở **nhóm mặc định không đúng**; kết quả có thể là lỗi phân giải plugin hoặc chọn sai artifact khi tên trùng.

### 2.2. artifactId: tên artifact plugin

`artifactId` phân biệt plugin bên trong một group:

~~~xml
<artifactId>maven-compiler-plugin</artifactId>
~~~

Một số cặp tên dễ gặp:

| artifactId | Công việc tiêu biểu |
| --- | --- |
| `maven-compiler-plugin` | Biên dịch mã Java chính/test |
| `maven-surefire-plugin` | Chạy unit test |
| `maven-jar-plugin` | Đóng gói JAR |
| `maven-resources-plugin` | Sao chép/lọc resources |
| `maven-clean-plugin` | Dọn output build qua clean lifecycle |
| `maven-dependency-plugin` | Phân tích/copy dependencies |
| `maven-help-plugin` | Hiển thị thông tin plugin và effective POM |
| `maven-antrun-plugin` | Chạy Ant tasks khi được cấu hình |

Chú ý tên plugin là **`maven-compiler-plugin`**, còn trong CLI thường gọi ngắn là **`compiler`**. Tên `compiler` là **plugin prefix**, không phải artifactId và cũng không phải groupId.

Quy ước đặt tên của nhiều plugin chính thức là `maven-<prefix>-plugin`. Plugin bên thứ ba thường dùng `<prefix>-maven-plugin`, nhưng không phải tên nào cũng tuân thủ mẫu đó và prefix có thể do tác giả plugin cấu hình. Vì thế phải biết đúng **artifactId thật**, không tự ghép chuỗi từ tên goal rồi coi là một artifact được phát hành.

### 2.3. version: phiên bản plugin sẽ thực thi

~~~xml
<version>3.14.1</version>
~~~

Version của plugin ảnh hưởng đến **mã plugin, tham số, hành vi và yêu cầu Maven/JDK**. Một plugin version khác có thể thay đổi compiler defaults, phương thức chạy test, cách đóng JAR hoặc tên một goal.

Maven có thể cố phân giải version khi không khai `<version>` ở một số trường hợp (ví dụ qua management hoặc metadata của repository), nhưng **không nên dựa vào việc tự chọn version** cho build cần tái lập. Theo hướng dẫn Apache Maven, nên ghi rõ version của các plugin được sử dụng; với nhiều module, quản lý version tại `pluginManagement` của parent.

Không được nhầm:

- `<project><version>1.0.0</version>`: version **artifact ứng dụng**.
- `<dependency><version>5.11.4</version>`: version **thư viện của ứng dụng/test**.
- `<plugin><version>3.14.1</version>`: version **công cụ Maven build**.

Đổi version project không tự đổi version plugin; thêm dependency version cũng không tự kiểm soát plugin version.

### 2.4. Một tọa độ không đồng nghĩa một goal

~~~text
Plugin identity:  org.apache.maven.plugins:maven-compiler-plugin:3.14.1
Goal identity:    compiler:compile
Full CLI goal:    org.apache.maven.plugins:maven-compiler-plugin:3.14.1:compile
~~~

`groupId:artifactId:version` chọn **bản plugin**; tên goal `compile` chọn **hành động cụ thể bên trong plugin**. Một plugin có thể cung cấp nhiều goal, ví dụ Compiler Plugin có `compile` và `testCompile`. Không cần tạo một khai báo `<plugin>` mới cho từng goal của cùng plugin.

## 3. Cú pháp chính xác trong pom.xml

Cấu trúc tối thiểu ở một project Maven:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>plugin-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

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
~~~

Đây là **POM XML hoàn chỉnh về cấu trúc**, nhưng chưa kèm mã nguồn Java. Ví dụ thực hành đầy đủ có Java/JUnit tại mục 8.

Một đường dẫn cấu hình cần nhớ:

~~~text
project
└── build
    └── plugins
        └── plugin
            ├── groupId
            ├── artifactId
            ├── version
            ├── configuration (tùy chọn)
            └── executions (tùy chọn)
~~~

Nếu chỉ muốn khai plugin và để lifecycle binding chuẩn gọi goal, cấu hình có thể dừng ở ba trường tọa độ. Nếu muốn thay tham số plugin, thêm `<configuration>`. Nếu muốn gắn goal tùy chỉnh vào phase, dùng `<executions>`, `<execution>`, `<phase>` và `<goals>`.

**Không đặt plugin trong `<dependencies>` của ứng dụng** với suy nghĩ Maven sẽ chạy plugin. Cấu trúc `dependencies` giải quyết classpath của project; Maven build plugins được khai dưới `build/plugins` hoặc được quản lý qua `build/pluginManagement`.

## 4. Build plugin và reporting plugin khác nhau

Maven có hai nhóm plugin thường gặp:

| Nhóm | Vị trí chính | Công việc |
| --- | --- | --- |
| Build plugin | `<build><plugins>` | Biên dịch, test, đóng gói, kiểm tra, tạo mã, chuẩn bị artifact |
| Reporting plugin | `<reporting><plugins>` | Sinh báo cáo cho site/reporting trong quy trình tương ứng |

Ví dụ build plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>
    </plugins>
</build>
~~~

Ví dụ reporting plugin, chỉ minh họa vị trí (phải chọn plugin goal và version thực sự phù hợp với quy trình báo cáo đang dùng):

~~~xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-project-info-reports-plugin</artifactId>
            <version>3.7.0</version>
        </plugin>
    </plugins>
</reporting>
~~~

Một số plugin có thể tham gia cả build và reporting tùy mục tiêu, nhưng `reporting/plugins` không thay thế `build/plugins`. Muốn compiler tham gia default build lifecycle, hãy cấu hình đúng **build**. Bài học này chủ yếu tập trung **build plugins**.

**Lưu ý:** ví dụ reporting ở trên chỉ minh họa **đường dẫn XML**, không phải một dự án site đã cấu hình đầy đủ; ví dụ runnable ở mục 8 không dùng reporting.

## 5. Plugin, goal và lifecycle phase liên hệ thế nào?

Maven định nghĩa các phase, rồi gắn **goal của plugin** vào phase. Với packaging `jar` trong Maven 3, các binding phổ biến là:

| Phase | Plugin goal tiêu biểu được gắn mặc định |
| --- | --- |
| `process-resources` | `resources:resources` |
| `compile` | `compiler:compile` |
| `process-test-resources` | `resources:testResources` |
| `test-compile` | `compiler:testCompile` |
| `test` | `surefire:test` |
| `package` | `jar:jar` |
| `install` | `install:install` |
| `deploy` | `deploy:deploy` |

**Phase không phải plugin và goal không phải phase.** Với lệnh:

~~~bash
mvn package
~~~

Maven chạy các phase của default lifecycle **đến hết `package`**. Đối với project `jar`, trình tự này thường bao gồm xử lý resource, compile, test và đóng JAR.

Ngược lại:

~~~bash
mvn compiler:compile
~~~

là gọi **goal** của Compiler Plugin trực tiếp. Nó không đồng nghĩa `mvn compile`: lời gọi goal trực tiếp không mặc nhiên yêu cầu Maven chạy toàn bộ các phase đứng trước, dù một số goal cụ thể có thể có hành vi fork lifecycle riêng do plugin định nghĩa.

### 5.1. Vì sao chỉ thêm plugin chưa chắc tạo công việc mới?

Với packaging `jar`, `compiler:compile` và `jar:jar` **đã có lifecycle binding mặc định**. Khai chúng với version/cấu hình rõ là để kiểm soát plugin mà Maven sẽ chạy.

Nhưng đối với một plugin tùy chỉnh, chỉ có:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
</plugin>
~~~

**không tự khiến goal `antrun:run` chạy ở mọi lần `mvn package`**. Muốn một Ant target chạy trong lifecycle, phải khai execution gắn goal vào phase (xem mục 7 và ví dụ đầy đủ).

### 5.2. So sánh cú pháp gọi trên command line

~~~bash
mvn compile
mvn compiler:compile
mvn org.apache.maven.plugins:maven-compiler-plugin:3.14.1:compile
~~~

- `mvn compile`: gọi lifecycle **phase**; Maven đi qua các phase trước và tới `compile`.
- `mvn compiler:compile`: gọi plugin goal bằng **prefix**; Maven cần phân giải prefix thành plugin và xác định version.
- `mvn org.apache.maven.plugins:maven-compiler-plugin:3.14.1:compile`: gọi goal bằng **tọa độ plugin đầy đủ + goal**; xác định tường minh plugin và version cho lời gọi.

Cách đầy đủ hữu ích khi có prefix mơ hồ, settings khác nhau hoặc cần thử đúng một bản plugin. **Không dùng lời gọi goal trực tiếp thay cho toàn bộ pipeline build** nếu bạn cần chắc chắn resource/test/package đã chạy.

## 6. Prefix resolution và mối liên hệ với groupId

### 6.1. Prefix không phải artifactId

Người dùng có thể quen những lệnh:

~~~bash
mvn compiler:compile
mvn surefire:test
mvn jar:jar
mvn help:effective-pom
~~~

Tên `compiler`, `surefire`, `jar`, `help` là **prefix**, được Maven ánh xạ đến artifactId plugin dựa trên metadata plugin và nhóm tìm kiếm. Ví dụ `compiler` thường ánh xạ tới `maven-compiler-plugin`.

Với Maven 3, các plugin group mặc định phục vụ tra prefix bao gồm `org.apache.maven.plugins` và `org.codehaus.mojo`. Có thể thêm group khác vào `~/.m2/settings.xml` dưới `<pluginGroups>` khi cần gọi plugin bên thứ ba bằng prefix ngắn:

~~~xml
<pluginGroups>
    <pluginGroup>com.example.build</pluginGroup>
</pluginGroups>
~~~

**Đây chỉ là trích đoạn để đặt bên trong `<settings>`**, không phải `settings.xml` hoàn chỉnh. Group `com.example.build` là tên minh họa, không phải plugin đã được xác nhận tồn tại. Nếu bạn không có plugin của group ấy, thêm `pluginGroup` không sinh ra artifact hay goal nào.

### 6.2. Khi prefix không được tìm thấy

Một lỗi thường gặp:

~~~text
No plugin found for prefix 'example' in the current project and in the plugin groups
~~~

Hãy kiểm tra:

1. Prefix có đúng với metadata plugin thực tế không?
2. Plugin có được khai trong POM hoặc plugin group của settings có đúng không?
3. Repository có lưu plugin artifact và metadata mà Maven có quyền tải không?
4. Có bị proxy/mirror/credentials chặn việc giải quyết metadata không?
5. Có thể chạy bằng **tọa độ đầy đủ** thay cho prefix để loại bỏ sự mơ hồ không?

Đối với plugin bên thứ ba được phép dùng, prefer khai đủ `groupId`, `artifactId`, `version` trong POM. Nếu cần gọi trực tiếp, dùng tọa độ plugin đầy đủ và goal được tài liệu plugin công bố. **Không coi việc đoán prefix thành công là bằng chứng plugin đúng version**; xem log và effective POM.

### 6.3. Prefix resolution khác version resolution

Hai câu hỏi riêng:

- Prefix `compiler` tương ứng với **plugin artifact** nào?
- Plugin ấy sẽ chạy **version** nào?

Khai một `<version>` rõ ràng giải quyết câu hỏi thứ hai cho plugin được dùng theo POM; gọi CLI với `groupId:artifactId:version:goal` còn làm rõ cả hai. `<pluginGroups>` giúp tìm groupId khi dùng prefix, **không phải nơi chọn version cho mọi plugin**.

## 7. Khai configuration và executions đúng chỗ

### 7.1. Plugin-level configuration

Nếu muốn Compiler Plugin dùng Java 17:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
~~~

`<release>17</release>` là **tham số của Compiler Plugin**, không phải trường tọa độ plugin. Maven dùng các phần tử bên trong `configuration` để cấu hình goal theo plugin descriptor. Tên và kiểu tham số phải đúng tài liệu plugin.

Cấu hình trên không **cài đặt JDK 17**. JDK mà Maven thực sự sử dụng phải hỗ trợ `--release 17`. Kiểm tra bằng `mvn -version` và thiết lập JDK của terminal/IDE/CI.

Có thể đặt cùng yêu cầu ở property của POM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Trong ví dụ đầy đủ ở mục 8, property này được dùng để giảm lặp. Cả hai cách có thể được dùng tùy tiêu chuẩn dự án; tránh khai giá trị mâu thuẫn không cần thiết.

### 7.2. Execution gắn goal vào phase

Một execution hợp lệ thường có:

~~~xml
<execution>
    <id>write-marker</id>
    <phase>validate</phase>
    <goals>
        <goal>run</goal>
    </goals>
    <configuration>
        <target>
            <mkdir dir="${project.build.directory}"/>
            <echo file="${project.build.directory}/plugin-execution.marker">
                AntRun executed at validate
            </echo>
        </target>
    </configuration>
</execution>
~~~

Đây là **trích đoạn con của `maven-antrun-plugin`**; nó cần nằm trong `<plugin><executions>` của POM đầy đủ. Ý nghĩa:

- `id`: tên để nhận diện execution trong effective POM và log.
- `phase`: điểm Maven sẽ gọi goal trong lifecycle.
- `goals/goal`: goal `run` được cung cấp bởi AntRun Plugin.
- `configuration/target`: lệnh Ant cần thực thi.
- `mkdir`: bảo đảm `target` tồn tại trong lần build sạch trước khi `echo` ghi file.

Tại phase `validate`, goal `antrun:run` chạy, tạo file marker. **Maven không tự tạo marker này** nếu thiếu execution; nó chỉ là dấu hiệu quan sát việc plugin goal đã được kích hoạt.

### 7.3. Khác nhau giữa plugin-level và execution-level configuration

~~~xml
<plugin>
    ...
    <configuration>
        <!-- Tham số áp dụng ở mức plugin -->
    </configuration>
    <executions>
        <execution>
            <id>custom-execution</id>
            <configuration>
                <!-- Tham số áp dụng cho execution này -->
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Maven có cơ chế hợp nhất cấu hình, cho phép một số tham số chung ở plugin và một số tham số chuyên biệt ở từng execution. Nếu POM cha/con cùng khai plugin và execution id, cấu hình có thể được hợp nhất theo các quy tắc model. **Không giả định mọi execution đều nhận cùng parameter nếu có override riêng**; dùng `help:effective-pom` để xác minh.

## 8. Dự án thực hành đầy đủ: Java 17, JUnit 5, JAR và AntRun Plugin

Trong ví dụ này, ta **khai đủ groupId/artifactId/version** cho các plugin chính. Ba plugin Compiler, Surefire, JAR dùng lifecycle bindings chuẩn của packaging `jar`. AntRun là plugin bổ sung có execution rõ ràng ở phase `validate`.

### 8.1. Cấu trúc file

~~~text
plugin-coordinates-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/vn/example/plugins/App.java
    └── test/
        └── java/vn/example/plugins/AppTest.java
~~~

Yêu cầu: **Maven 3.9.x**, **JDK 17+**, repository có thể tải plugin/JUnit lần đầu. Nếu công ty dùng proxy/mirror, dùng `settings.xml` được phép thay vì sửa URL plugin tùy ý.

### 8.2. pom.xml hoàn chỉnh

File `plugin-coordinates-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>plugin-coordinates-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.plugins.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>write-plugin-marker</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}"/>
                                <echo file="${project.build.directory}/plugin-execution.marker"
                                      message="AntRun executed at validate"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích chính xác từng plugin:**

| Tọa độ plugin | Vai trò trong POM mẫu | Cách goal được kích hoạt |
| --- | --- | --- |
| `org.apache.maven.plugins:maven-compiler-plugin:3.14.1` | Biên dịch Java 17 | Packaging `jar` gắn `compiler:compile` và `compiler:testCompile` vào lifecycle |
| `org.apache.maven.plugins:maven-surefire-plugin:3.5.4` | Thực thi unit test JUnit | Packaging `jar` gắn `surefire:test` vào phase `test` |
| `org.apache.maven.plugins:maven-jar-plugin:3.4.2` | Đóng gói JAR, thêm Main-Class | Packaging `jar` gắn `jar:jar` vào `package` |
| `org.apache.maven.plugins:maven-antrun-plugin:3.1.0` | Ghi marker minh họa | **Execution do POM tự khai** gắn `antrun:run` vào `validate` |

`maven-jar-plugin` nhận `<archive><manifest><mainClass>` để thêm entry `Main-Class`, nhờ đó có thể dùng `java -jar` trong ví dụ không có external runtime dependency. **Main-Class là cấu hình plugin, không nằm trong ba trường tọa độ**.

**Vì sao không khai JUnit là plugin?** JUnit Jupiter là thư viện test trong `dependencies` với `scope=test`. Surefire là plugin build dùng JUnit để thực thi test. Hai artifact thuộc hai nhóm chức năng khác nhau.

**Vì sao AntRun có `executions`, còn ba plugin kia không cần?** Ba plugin kia đã được Maven gắn vào lifecycle `jar`. AntRun không phải goal mặc định cần chạy ở mọi project; ta thêm một execution rõ ràng để minh họa.

### 8.3. Java chính: App.java

File `src/main/java/vn/example/plugins/App.java`:

~~~java
package vn.example.plugins;

public final class App {
    private App() {
    }

    public static String greeting(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }

    public static void main(String[] args) {
        System.out.println(greeting("Maven"));
    }
}
~~~

Toàn bộ API trong `App.java` có sẵn trong JDK 17. Không cần runtime dependency ngoài JDK. Hàm `greeting` bỏ khoảng trắng hai đầu tên và không chấp nhận tên rỗng.

Stdout **chính xác** khi chạy chương trình:

~~~text
Hello, Maven!
~~~

Đây là stdout của **App.main**, không bao gồm log Maven. AntRun marker không thay đổi stdout Java.

### 8.4. JUnit test: AppTest.java

File `src/test/java/vn/example/plugins/AppTest.java`:

~~~java
package vn.example.plugins;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void formatsGreeting() {
        assertEquals("Hello, Lan!", App.greeting(" Lan "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> App.greeting("   "));
    }
}
~~~

JUnit Jupiter được khai trong `dependencies` với `scope=test`. Maven Surefire Plugin 3.5.4 thực thi test này khi build đến phase `test`; với đúng POM và mã nguồn, dự kiến **2 test PASS, 0 failure, 0 error**.

## 9. Chạy từng phase để nhận diện plugin goal

### 9.1. Kiểm tra môi trường

Từ thư mục `plugin-coordinates-demo`:

~~~bash
java -version
mvn -version
~~~

Maven phải chạy bằng JDK hỗ trợ Java 17. `mvn -version` cho biết Maven và Java runtime thực tế, không tự xác minh plugin tải được hay chưa.

### 9.2. Thử chỉ đến validate

~~~bash
mvn clean validate
~~~

Khi `clean` đã xóa output cũ, default lifecycle chạy tới `validate` và execution `write-plugin-marker` kích hoạt AntRun goal `run`. File xuất hiện:

~~~text
target/plugin-execution.marker
~~~

Nội dung:

~~~text
AntRun executed at validate
~~~

Ở lần build **`clean validate`**, `target/classes/vn/example/plugins/App.class` chưa được tạo, vì phase `compile` nằm sau `validate`. JAR ứng dụng cũng chưa được đóng gói.

Bạn có thể tìm trong log phần tương tự (định dạng hiển thị có thể thay đổi theo Maven):

~~~text
maven-antrun-plugin:3.1.0:run (write-plugin-marker)
~~~

Dòng đó là bằng chứng một goal **của plugin đã khai đúng tọa độ** đang được gọi trong execution tương ứng.

### 9.3. Thử compile

~~~bash
mvn clean compile
~~~

Maven đi qua `validate` (AntRun marker) và các phase đến `compile` (Compiler Plugin). File quan trọng sau build sạch:

~~~text
target/
├── plugin-execution.marker
└── classes/
    └── vn/example/plugins/App.class
~~~

Có thể chạy mã đã biên dịch trực tiếp mà không phải chờ JAR:

~~~bash
java -cp target/classes vn.example.plugins.App
~~~

Kết quả:

~~~text
Hello, Maven!
~~~

**`mvn compile` không tự chạy `App.main`.** Dòng stdout chỉ xuất hiện vì bạn gọi lệnh `java` riêng.

### 9.4. Thử package

~~~bash
mvn clean package
~~~

Với project `jar`, Maven chạy qua resource/compile/test rồi gọi JAR Plugin. Kiểm tra:

~~~text
target/
├── plugin-execution.marker
├── classes/vn/example/plugins/App.class
├── test-classes/vn/example/plugins/AppTest.class
├── surefire-reports/
└── plugin-coordinates-demo-1.0.0.jar
~~~

Trong log, mong đợi các goal sau được gọi trong lifecycle tương ứng:

~~~text
antrun:run
compiler:compile
compiler:testCompile
surefire:test
jar:jar
~~~

Đây là các **tên goal**, không phải tất cả các dòng log. Maven cũng có thể gọi Resources Plugin, Clean Plugin và các goal khác của lifecycle mà không khai tường minh trong POM mẫu.

Dùng JDK `jar` để kiểm tra manifest:

~~~bash
jar xf target/plugin-coordinates-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

Sau lệnh trên, file `META-INF/MANIFEST.MF` được giải nén vào thư mục hiện tại. Mở nó bằng editor; trong manifest phải có dòng:

~~~text
Main-Class: vn.example.plugins.App
~~~

**Lưu ý:** `jar xf` tạo thư mục `META-INF` trong working directory, không phải Maven sửa POM. Nếu chỉ muốn xem danh sách các file JAR, chạy `jar tf`. Không đọc thứ tự toàn bộ manifest như một chuẩn cố định vì metadata có thể khác giữa các phiên bản tool.

Chạy:

~~~bash
java -jar target/plugin-coordinates-demo-1.0.0.jar
~~~

Stdout:

~~~text
Hello, Maven!
~~~

Lý do `java -jar` hoạt động ở đây:

1. Compiler Plugin đã sinh bytecode `App.class`.
2. JAR Plugin đã đóng class vào JAR và ghi `Main-Class`.
3. `App` chỉ sử dụng API JDK, không cần thêm external runtime JAR.

Trong một dự án có dependencies ngoài, việc khai `Main-Class` **không tự tạo fat JAR**. Nếu ứng dụng cần thư viện ngoài, vẫn phải dùng distribution/classpath/launcher phù hợp.

### 9.5. Thử verify

~~~bash
mvn clean verify
~~~

Maven sẽ đi qua các phase trước `verify`, bao gồm `package`, nên các artifact và test tương ứng vẫn được tạo. `verify` không đồng nghĩa “Maven tự kiểm tra cấu hình mọi plugin theo ý bạn”; nó là một phase có thể gắn các goal kiểm tra bổ sung. Đối với bài này, `BUILD SUCCESS` cùng hai test PASS và việc chạy JAR là bằng chứng thực hành rõ ràng.

## 10. Kiểm tra Maven thực sự đang dùng phiên bản plugin nào

### 10.1. Log Maven

Khi chạy `mvn clean package`, tìm dòng có dạng:

~~~text
--- compiler:3.14.1:compile (...)
--- surefire:3.5.4:test (...)
--- jar:3.4.2:jar (...)
--- antrun:3.1.0:run (write-plugin-marker) ...
~~~

Các tiền tố và cách Maven hiển thị có thể khác. Mỗi dòng cho biết **plugin, version, goal và execution id** đã được Maven chọn.

### 10.2. Effective POM

~~~bash
mvn help:effective-pom
mvn help:effective-pom -Dverbose
~~~

Goal Help Plugin hiển thị **effective POM** sau khi Maven xử lý inheritance, pluginManagement, active profiles và các cấu hình khác. Trong bản kết quả của project thực hành, hãy tìm các plugin:

~~~text
maven-compiler-plugin = 3.14.1
maven-surefire-plugin = 3.5.4
maven-jar-plugin = 3.4.2
maven-antrun-plugin = 3.1.0
~~~

`-Dverbose` có thể thêm thông tin nguồn cấu hình. Nếu một module không sử dụng đúng version mong muốn, đọc **effective POM của chính module đó**, không chỉ POM cha.

### 10.3. Dùng Help Plugin mô tả goal và tham số

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.14.1 -Dgoal=compile -Ddetail=true
~~~

Tài liệu của Help Plugin cho phép `-Dplugin` bằng prefix, `groupId:artifactId` hoặc `groupId:artifactId:version`. Kết quả mô tả goal, tham số, các thuộc tính Maven cần thiết và các yêu cầu tương ứng. Điều này hữu ích khi không chắc tham số nên viết là `release`, `source` hay tên khác.

Cũng có thể kiểm tra AntRun:

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-antrun-plugin:3.1.0 -Dgoal=run -Ddetail=true
~~~

`help:describe` có thể cần tải chính Help Plugin lần đầu; nếu repository/proxy không truy cập được, lỗi tải plugin chưa phải lỗi trong `<configuration>` của compiler hoặc antrun.

### 10.4. Quan sát artifact từ local Maven repository

Plugin được giải quyết từ repository Maven và thường được cache ở `~/.m2/repository`, ví dụ một đường dẫn tương tự:

~~~text
~/.m2/repository/org/apache/maven/plugins/maven-compiler-plugin/3.14.1/
~~~

Chỉ có file JAR nằm trong cache **chưa chứng minh lần build hiện tại đã sử dụng plugin đó**: local repository có thể chứa nhiều version. Bằng chứng nên là **effective POM + log goal**, kết hợp output sau một lần build sạch.

## 11. Thực hành: phân biệt phase và lời gọi goal trực tiếp

Trong project mẫu, thử các lệnh sau ở những lần build riêng, không trộn lẫn kết quả của thư mục `target` khi chưa clean.

| Lệnh | Ý nghĩa | Có mặc định chạy AntRun ở validate? |
| --- | --- | --- |
| `mvn clean validate` | Chạy clean lifecycle rồi default lifecycle đến validate | Có |
| `mvn clean compile` | Chạy đến compile, gồm validate | Có |
| `mvn clean package` | Chạy đến package, gồm validate/test | Có |
| `mvn compiler:compile` | Gọi goal compiler trực tiếp | **Không bảo đảm**, vì không chạy cả lifecycle từ validate |
| `mvn org.apache.maven.plugins:maven-compiler-plugin:3.14.1:compile` | Gọi đúng plugin/version/goal trực tiếp | **Không bảo đảm** các phase trước |
| `mvn help:describe ...` | Mô tả plugin/goal | Không phải cách build app qua lifecycle |

Nếu bạn gọi `mvn compiler:compile` từ một workspace đã build trước, marker `target/plugin-execution.marker` có thể **vẫn còn từ lần trước**. Đừng lấy sự tồn tại của file cũ làm bằng chứng goal AntRun vừa chạy; dùng `mvn clean compile` hoặc đọc log goal của đúng lần chạy.

Một goal gọi trực tiếp có thể có riêng yêu cầu/lifecycle fork tùy plugin. Bài này dùng quy tắc tổng quát: **lệnh phase bảo đảm đi qua các phase tiền nhiệm của lifecycle**, còn gọi goal trực tiếp không tự trở thành một lệnh phase.

## 12. Quản lý phiên bản plugin tập trung với parent POM

Khi nhiều module đều dùng Compiler, Surefire, JAR Plugin, có thể quản lý version ở parent để tránh lặp:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đây là **đoạn đặt trong parent POM**, không phải một POM đầy đủ để chạy độc lập.

POM con có quan hệ:

~~~xml
<parent>
    <groupId>vn.example</groupId>
    <artifactId>company-build-parent</artifactId>
    <version>1.0.0</version>
</parent>
~~~

Maven nhận quản lý plugin khi quan hệ parent được thiết lập đúng. Đối với packaging `jar`, Compiler/Surefire có binding lifecycle nên version được quản lý có thể được sử dụng khi goal tương ứng chạy. Trong module muốn khai sử dụng plugin rõ ràng mà không lặp version, có thể viết:

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

Version `3.14.1` đến từ `pluginManagement` của parent, không phải Maven chọn tùy ý ở thời điểm build.

**Chú ý phân biệt:**

- `pluginManagement` **quản lý version/configuration/execution** cho plugin được sử dụng; với plugin không có lifecycle binding, chỉ quản lý nó **không tạo một goal mới tự chạy**.
- `build/plugins` là khai báo plugin để dùng trong build; một goal tùy chỉnh thường cần `executions` hoặc phải được gọi trực tiếp.
- `dependencyManagement` quản lý **dependency của ứng dụng**; không thay thế `pluginManagement`.
- `modules` ở aggregator không tự tạo quan hệ parent; module con phải khai `<parent>` phù hợp.

### 12.1. Một cách khai có nên đặt version ở cả parent và child?

Nếu parent đã quản lý `maven-compiler-plugin:3.14.1`, child chỉ khai plugin không cần lặp `<version>3.14.1</version>`. Nếu child đặt một version khác, nó có thể override quản lý chung và gây lệch version giữa module.

Một ngoại lệ có thể hợp lệ khi module đòi plugin version khác, nhưng nên có lý do kỹ thuật, test và đánh giá tương thích Maven/JDK. Khi toàn nhóm đồng ý nâng plugin, hãy sửa **nguồn quản lý tập trung**, rồi build/test toàn reactor.

### 12.2. Kế thừa execution có thể gây tác dụng ngoài ý muốn

Nếu parent đặt AntRun Plugin **trong `build/plugins`** cùng execution `write-plugin-marker`, các child POM thực sự kế thừa parent có thể nhận execution đó. Nếu chỉ muốn parent chạy một execution, Maven có thẻ `<inherited>false</inherited>` tại mức plugin hoặc execution để ngăn truyền theo phạm vi tương ứng.

Không đưa một execution tạo file tại root vào parent rồi giả định tất cả child sẽ bỏ qua. Với multi-module, kiểm tra **effective POM của từng module** và output path của plugin để tránh ghi đè chung thư mục.

## 13. Version plugin: những lỗi và rủi ro cần tránh

### 13.1. Không ghim plugin version

Một khai báo:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
</plugin>
~~~

nếu không có pluginManagement phù hợp có thể khiến Maven phải chọn version bằng quy tắc/metadata môi trường hoặc binding mặc định. Kết quả build giữa các Maven installation hoặc thời điểm có thể khó kiểm soát hơn.

**Cách làm tốt:** ghim `<version>` ở plugin được dùng, hoặc quản lý nó ở parent `pluginManagement`. Không chỉ ghim compiler mà quên test/packaging plugins quan trọng đối với sản phẩm.

### 13.2. Dùng version không tồn tại hoặc chưa được repository cho phép

Ví dụ:

~~~xml
<version>99.99.99</version>
~~~

là **phiên bản giả để minh họa lỗi**, không phải version nên thử tải trên hệ thống thật. Nếu Maven không tìm được plugin artifact theo đúng tọa độ, build có thể dừng ở bước resolution trước khi Java compiler chạy.

Đừng tự tạo số version từ suy đoán. Khi cập nhật, kiểm tra phiên bản thật được phát hành, yêu cầu Maven/JDK và mirror của tổ chức đã đồng bộ chưa.

### 13.3. Version plugin khác version dependency

Đây là cấu hình sai ý nghĩa:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
    </dependency>
</dependencies>
~~~

Đoạn XML trên sẽ khai **dependency của project** đến artifact plugin; nó **không phải cách cấu hình Compiler Plugin như build plugin** và không tự yêu cầu Maven chạy `compiler:compile` bằng version đó.

Muốn dùng Compiler Plugin đúng cách, đặt dưới `<build><plugins>` hoặc quản lý phiên bản trong `<build><pluginManagement>`. Với Maven plugin development riêng, plugin artifact có thể được dùng trong những bối cảnh đặc thù, nhưng không làm thay đổi nguyên tắc cho project ứng dụng.

### 13.4. Cài plugin vào nơi không phù hợp

Với Compiler Plugin trong một module `jar`, đặt ở `build/plugins` là vị trí chuẩn. Nếu bạn đặt nó chỉ ở `reporting/plugins` rồi gọi `mvn compile`, đó không phải cách xác định plugin build cần dùng.

Đối với `pom` packaging của parent aggregator, không tự suy ra mọi goal compile/test chạy ở parent như ở module `jar`. Default binding tùy **packaging**, còn plugin execution được gắn tùy POM.

### 13.5. Cấu hình goal không tồn tại

Ví dụ gọi:

~~~bash
mvn compiler:unknownGoal
~~~

Maven không có nghĩa vụ cung cấp goal tên `unknownGoal` trong Compiler Plugin. Lỗi kiểu `Could not find goal` cần được xử lý bằng cách đọc plugin goal documentation và `help:describe`; đừng thêm goal bất kỳ vào `<executions>` rồi kỳ vọng Maven tự hiểu.

### 13.6. Nâng version nhưng bỏ qua compatibility

Plugin version mới có thể yêu cầu Maven/JDK mới hơn, đổi default parameters hoặc hành vi đóng gói. Kể cả khi output Java compile pass, điều đó không tự chứng minh manifest, test reports hoặc packaging tương đương.

Để nâng plugin version an toàn:

1. Kiểm tra version phát hành và yêu cầu runtime Maven/JDK của plugin.
2. Đọc release notes/changelog và thay đổi tham số có ảnh hưởng.
3. Sửa đúng phiên bản ở POM hoặc parent pluginManagement.
4. Chạy `mvn clean verify` trên môi trường chuẩn hóa và kiểm tra test/log.
5. Kiểm tra artifact theo cách sản phẩm sẽ sử dụng.
6. Lưu commit, plugin version, JDK/Maven version và kết quả CI để truy vết.

## 14. Gỡ lỗi plugin resolution và goal execution

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `No plugin found for prefix` | Prefix chưa được ánh xạ, plugin group sai hoặc metadata không tải được | Dùng tọa độ đầy đủ, kiểm tra `pluginGroups` và repository |
| `PluginResolutionException` | Artifact plugin hoặc dependency của nó không phân giải được | Kiểm tra groupId/artifactId/version, mirror/proxy/credentials |
| `Could not find goal ...` | Goal không tồn tại trong plugin/version đã chọn | Dùng `help:describe` và plugin docs |
| Plugin chạy version khác trong POM đang xem | Version đến từ parent/pluginManagement/profile hoặc module khác | Xem effective POM đúng module + log |
| `mvn compile` thành công nhưng không tạo JAR | `compile` không phải `package` | Chạy `mvn package` khi cần JAR |
| `mvn package` nhưng AntRun marker không có | Chưa khai execution, sai phase hoặc goal không thực thi | Kiểm tra `<executions>` và log AntRun |
| Marker có nhưng build hiện tại không gọi AntRun | File cũ từ lần build trước | Dùng `mvn clean validate` và kiểm tra log |
| Maven báo XML không hợp lệ | Plugin đặt sai cấu trúc, đóng tag sai hoặc duplicate `build` | Kiểm tra `project/build/plugins/plugin` và cú pháp XML |
| `release version 17 not supported` | Maven dùng JDK cũ | `mvn -version`, `JAVA_HOME`, CI toolchain |
| Surefire chạy nhưng không thấy test | Test discovery, tên class, JUnit dependency hoặc skip options | Kiểm tra `AppTest.java`, `target/surefire-reports` |
| `java -jar` báo `no main manifest attribute` | JAR Plugin chưa thêm `Main-Class` | Xem `archive/manifest/mainClass` và manifest thật |
| `java -jar` báo thiếu class ngoài | JAR không nhúng runtime dependencies | Dùng distribution/classpath/packaging phù hợp |
| Plugin tải ở laptop nhưng lỗi trên CI | Mirror/proxy/offline/cache hoặc Maven/JDK khác | So sánh effective settings và build environment |
| Đã khai plugin trong pluginManagement nhưng goal tùy chỉnh không chạy | Management không tự kích hoạt goal mới | Khai plugin sử dụng/execution hoặc gọi goal rõ |
| Maven lỗi sau khi nâng plugin version | Thay đổi API/configuration hoặc yêu cầu runtime | Đối chiếu plugin docs/changelog, build/test với version mục tiêu |

### Quy trình gỡ lỗi ngắn

1. **Đọc tên plugin và version trong thông báo lỗi.** Đừng bắt đầu bằng việc sửa dependency ứng dụng nếu lỗi thuộc plugin resolution.
2. **Xem POM hiệu lực.** `mvn help:effective-pom` cho biết plugin management và cấu hình đã được hợp nhất.
3. **Tìm goal đúng trong tài liệu.** `help:describe` giúp liệt kê goal/parameter của plugin version xác định.
4. **Kiểm tra phase và execution id.** Mục tiêu là biết goal **có được gắn** và **đã đến phase hay chưa**.
5. **Đọc log build** bằng `mvn -e ...` hoặc `mvn -X ...` khi cần; cân nhắc redaction trước khi chia sẻ vì log có thể chứa thông tin nội bộ.
6. **Dùng build sạch để kiểm chứng output**. File còn lại sau lần build cũ không chứng minh goal vừa chạy.

Không xóa toàn bộ `~/.m2/repository` một cách tùy tiện. Cache plugin và dependency phục vụ nhiều project; trước tiên xác định đúng lỗi từ log và thông tin repository.

## 15. Plugin nào nên khai ở parent, plugin nào nên khai tại module?

Trong hệ thống multi-module, một parent thường quản lý:

- Version của `maven-compiler-plugin` cho mức Java chung.
- Version `maven-surefire-plugin` để test discovery và runtime test ổn định.
- Version `maven-jar-plugin`/WAR/shade plugin tùy packaging.
- Version của static analysis, checkstyle, code generation hoặc plugins dùng bởi nhiều module.

Tại mỗi module, bạn vẫn cần xác định **plugin nào thực sự nên hoạt động** và cấu hình riêng của module. Ví dụ, một module `pom` là aggregator không có mã Java chính; không nên áp đặt AntRun hay JAR-specific task cho tất cả project mà không xem packaging.

Bảng lựa chọn:

| Mục tiêu | Nơi thường phù hợp |
| --- | --- |
| Ghim version plugin chuẩn chung | Parent `build/pluginManagement` |
| Dùng plugin ở child và nhận version parent | Child `build/plugins` không lặp version |
| Chỉ sửa một tham số của plugin ở child | Child plugin `configuration` |
| Gắn goal riêng của plugin vào phase | `build/plugins/plugin/executions/execution` |
| Một plugin chỉ chạy tại root | Parent execution hoặc plugin có `inherited=false` khi phù hợp |
| Chỉ chạy một goal từ CLI | `mvn prefix:goal` hoặc tọa độ đầy đủ |
| Thống nhất library version | `dependencyManagement`, **không phải** `pluginManagement` |
| Sinh report tại site | `reporting/plugins` và site/reporting lifecycle tương ứng |

Khi có plugin nằm ở **cả parent và child**, Maven hợp nhất theo tọa độ plugin và các quy tắc POM model. Nếu hai executions có cùng id, phần cấu hình ở child có thể override phần parent; khác id có thể tạo thêm execution. Đọc effective POM thay vì suy luận chỉ từ XML ở một cấp.

## 16. Bài tập cuối bài

### Bài tập A — Nhận diện tọa độ

Từ:

~~~text
org.apache.maven.plugins:maven-surefire-plugin:3.5.4
~~~

chỉ ra `groupId`, `artifactId`, `version`. Giải thích vì sao `surefire:test` không phải một tọa độ plugin hoàn chỉnh và Maven cần phân giải prefix `surefire`.

### Bài tập B — Khai báo Compiler Plugin

Viết `<build><plugins>` khai Compiler Plugin đủ ba trường và cấu hình Java 17. Kiểm tra XML hợp lệ, rồi chạy `mvn -version` để xác nhận JDK có hỗ trợ mức release đó không.

### Bài tập C — Quan sát execution

Dựng project `plugin-coordinates-demo`, chạy `mvn clean validate`. Chứng minh file `target/plugin-execution.marker` có nội dung `AntRun executed at validate`, rồi giải thích id execution và goal `run` xuất hiện trong log.

### Bài tập D — Phân biệt compile/test/package

Chạy lần lượt `mvn clean compile`, `mvn clean test`, `mvn clean package`, đối chiếu `App.class`, Surefire reports và JAR. Mỗi lần đều bắt đầu bằng `clean` để tránh file cũ. Lệnh nào thực sự chạy `App.main`? **Không lệnh Maven nào trong ba lệnh tự gọi main**; chạy Java riêng để có stdout.

### Bài tập E — Cấu hình JAR Plugin

Với POM mẫu, dùng `jar xf` để xem manifest có `Main-Class` rồi chạy `java -jar ...`. Xóa tạm phần `<mainClass>`, build lại và dự đoán vì sao `java -jar` không còn tự tìm được main class. Khôi phục cấu hình sau thử nghiệm.

### Bài tập F — Gọi goal bằng tọa độ đầy đủ

So sánh:

~~~bash
mvn compiler:compile
mvn org.apache.maven.plugins:maven-compiler-plugin:3.14.1:compile
~~~

Xác định phần nào thuộc `groupId`, `artifactId`, `version` và `goal` trong lệnh thứ hai. Vì sao cả hai không nên được coi là thay thế hoàn chỉnh cho `mvn clean compile` khi cần chạy mọi phase tiền nhiệm?

### Bài tập G — Version pinning

Bỏ `<version>3.14.1</version>` của Compiler Plugin trong một bản sao POM **không có pluginManagement**, xem Maven chọn gì và có cảnh báo không. Khôi phục version rõ rồi dùng `help:effective-pom` để đối chiếu. Không dùng bài tập này để phát hành artifact không có version pinning.

### Bài tập H — Parent pluginManagement

Vẽ POM cha có `pluginManagement` quản lý Compiler/Surefire versions; POM con khai `<parent>` và sử dụng Compiler Plugin không ghi version. Giải thích vì sao con nhận version, và vì sao một AntRun Plugin chỉ nằm trong management không tự chạy goal tùy chỉnh.

### Bài tập I — Xử lý lỗi sai groupId

Trong bản sao project, thay groupId của AntRun Plugin thành `com.example.build` (chỉ là group ví dụ). Dự đoán lỗi resolution khi Maven không tìm được plugin thật ở tọa độ đó, rồi khôi phục `org.apache.maven.plugins`. Mục tiêu là thấy **artifactId giống nhau nhưng groupId khác không được coi là cùng plugin**.

### Bài tập J — Phân biệt plugin và library

Đọc POM mẫu, tìm JUnit Jupiter trong `dependencies` và Surefire trong `build/plugins`. Giải thích rõ bên nào cung cấp thư viện test, bên nào điều phối chạy test, và vì sao đặt Surefire vào project dependencies không phải cách chuẩn để điều khiển build.

## 17. Tự kiểm tra trước khi áp dụng vào dự án thật

Có thể dùng checklist:

- [ ] Plugin nằm đúng chỗ `project/build/plugins` hoặc `project/build/pluginManagement/plugins`.
- [ ] Có đúng `groupId`, `artifactId`, `version`; với plugin bên thứ ba không dựa vào groupId mặc định.
- [ ] Version được ghim rõ hoặc được quản lý tập trung có thể truy vết; không suy đoán plugin mới nhất.
- [ ] Nếu cần cấu hình goal, các tham số `configuration` có thật trong tài liệu đúng phiên bản plugin.
- [ ] Nếu cần chạy goal ở một phase, `execution/id/phase/goals` đã được khai hoặc có lifecycle binding chuẩn.
- [ ] Đã phân biệt prefix CLI với artifactId plugin và mục tiêu phase với mục tiêu goal.
- [ ] Đã kiểm tra effective POM và log của đúng module, đặc biệt khi có parent/profile/pluginManagement.
- [ ] Đã kiểm tra Maven/JDK version phù hợp với plugin version.
- [ ] Đã chạy build/test sạch và xác minh output của plugin; với ứng dụng Java, kiểm tra runtime theo cách sẽ triển khai.
- [ ] Khi chia sẻ POM/CI logs, đã không đưa secrets, credentials hoặc hostname nội bộ nhạy cảm vào tài liệu công khai.

Tóm lại: **`groupId` trả lời “plugin của ai?”, `artifactId` trả lời “plugin nào?”, `version` trả lời “bản nào?”, còn goal trả lời “thực hiện việc gì?”**. Khai đủ tọa độ và kiểm soát version giúp build dễ giải thích, tái lập và nâng cấp. Để plugin thực hiện một công việc, bạn vẫn cần **lifecycle binding, execution hoặc lệnh goal phù hợp**.

## 18. Tài liệu Apache Maven chính thức

- [Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): `groupId` mặc định, `artifactId`, `version`, configuration, execution và quy tắc ghim plugin version.
- [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase/goal, binding theo packaging và thứ tự thực thi.
- [Introduction to Plugin Prefix Resolution](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html): ánh xạ prefix, metadata plugin groups và `settings.xml`.
- [Apache Maven POM Reference](https://maven.apache.org/pom.html): `build/plugins`, `pluginManagement`, `reporting/plugins`, cấu trúc execution.
- [Apache Maven Compiler Plugin 3.14.1](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.1/plugin-info.html): Compiler Plugin và các goal biên dịch.
- [Apache Maven Surefire Plugin 3.5.4](https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/plugin-info.html): goal chạy unit test.
- [Apache Maven JAR Plugin 3.4.2](https://maven.apache.org/plugins-archives/maven-jar-plugin-3.4.2/plugin-info.html): goal `jar:jar` và yêu cầu phiên bản.
- [Maven Archiver — Make the JAR Executable](https://maven.apache.org/components/shared/maven-archiver/examples/classpath.html): cấu hình `archive/manifest/mainClass`.
- [Apache Maven AntRun Plugin 3.1.0](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/plugin-info.html): goal `antrun:run` và Ant `target`.
- [Apache Maven Help Plugin — help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html): xem plugin/goal/parameter theo tọa độ.
