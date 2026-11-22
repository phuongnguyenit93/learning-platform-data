# Cấu hình dependencies riêng cho plugin khi có nhu cầu trong Maven

## 1. Mục tiêu và nguyên tắc quan trọng nhất

Trong Maven, plugin là công cụ thực thi các **goal** của quá trình build, chẳng hạn biên dịch mã (`maven-compiler-plugin`), chạy kiểm thử (`maven-surefire-plugin`), xử lý resource (`maven-resources-plugin`) hay gọi Ant (`maven-antrun-plugin`). Mỗi plugin là một artifact có POM và các thư viện phụ thuộc riêng để thực hiện công việc.

Đôi khi plugin cần **một thư viện bổ sung mà POM phát hành mặc định của nó chưa mang theo**, ví dụ một Ant custom task. Maven cho phép cấu hình thư viện bổ sung ngay bên dưới plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.2.0</version>
            <dependencies>
                <dependency>
                    <groupId>ant-contrib</groupId>
                    <artifactId>ant-contrib</artifactId>
                    <version>1.0b3</version>
                    <exclusions>
                        <exclusion>
                            <groupId>ant</groupId>
                            <artifactId>ant</artifactId>
                        </exclusion>
                    </exclusions>
                </dependency>
            </dependencies>
        </plugin>
    </plugins>
</build>
~~~

Đây là **mảnh XML** đặt trong `<project>`; nó không phải `pom.xml` độc lập. Trong ví dụ, dependency `ant-contrib` được thêm cho **Maven AntRun Plugin**, **không** phải dependency của mã Java ứng dụng.

**Thông điệp cốt lõi:**

> **Chỉ thêm `<plugin><dependencies>` khi chính plugin cần JAR bổ sung để chạy goal. Nếu mã ứng dụng hoặc test trực tiếp dùng API của thư viện, hãy dùng `<project><dependencies>` với scope phù hợp.**

Đặt thư viện vào sai chỗ có thể khiến build vừa phình to, vừa tiếp tục báo `ClassNotFoundException`, trong khi ứng dụng tình cờ compile được trên một máy nhưng không chạy được trên CI.

Mục tiêu bài học: xác định **khi nào cần**, **cách cấu hình chính xác**, **ảnh hưởng tới plugin class realm**, **xử lý version/transitive conflicts**, **kiểm chứng**, và **những trường hợp không nên áp dụng**.

## 2. Phân biệt dependency của dự án với dependency riêng của plugin

Đọc hai cấu trúc XML sau.

**Dependency của project:**

~~~xml
<project>
    <!-- các phần tử bắt buộc khác của POM được lược bớt -->
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Mảnh này biểu diễn rằng **mã của project** cần Commons Lang. Khi scope mặc định `compile`, JAR có thể tham gia main compile, test và runtime classpath theo quy tắc Maven. Mã `src/main/java` có thể import `org.apache.commons.lang3.StringUtils`.

**Dependency của riêng plugin:**

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.2.0</version>
            <dependencies>
                <dependency>
                    <groupId>ant-contrib</groupId>
                    <artifactId>ant-contrib</artifactId>
                    <version>1.0b3</version>
                </dependency>
            </dependencies>
        </plugin>
    </plugins>
</build>
~~~

Mảnh này cung cấp Ant-Contrib cho **plugin AntRun**. Nó không tự làm `src/main/java` import được Ant-Contrib.

| Vấn đề | Project `dependencies` | Plugin `dependencies` |
| --- | --- | --- |
| Nơi khai báo | `project/dependencies` | `project/build/plugins/plugin/dependencies` |
| Ai cần JAR? | Mã chính, test hoặc runtime của project | Code của plugin khi thực thi goal |
| Tham gia classpath nào? | Compile/test/runtime theo scope và cách plugin dựng classpath | Plugin class realm và các custom classloader được plugin sử dụng |
| `mvn dependency:tree` mặc định | Hiển thị graph của project | **Không** hiển thị đầy đủ graph plugin |
| Có làm `src/main/java` import được API? | Có nếu artifact nằm trong compile classpath | Không mặc định |
| Có tự chạy thêm goal nào không? | Không | Cũng không |
| Quản lý phiên bản | Project `dependencyManagement` có thể áp dụng | Quản lý plugin version và các khai báo plugin dependencies riêng; không dựa vào project dependencyManagement để ép nội bộ |
| Rủi ro khi thêm thừa | Runtime hoặc transitive graph của project bị nhiễu | Plugin realm bị nhiễu, dễ phát sinh xung đột ABI |

`maven-compiler-plugin` là một **build plugin**, chứ không phải project dependency cần thêm vào `<dependencies>` để source compile. Ngược lại, `junit-jupiter` là project test dependency: việc Surefire có logic hỗ trợ JUnit không làm source test tự nhìn thấy JUnit API.

## 3. Cơ chế nạp lớp: vì sao hai loại dependency không trộn lẫn?

Maven 3 sử dụng **Plexus Classworlds** để tổ chức các classloader thành các **realm**, trong đó plugin thông thường được Maven tạo vùng nạp lớp riêng. Tập JAR plugin có thể gồm chính plugin, transitive dependencies trong POM plugin và dependency bổ sung mà project khai báo trong `plugin/dependencies`.

~~~text
Maven Core / Maven API
          |
          +--------> Maven Compiler Plugin realm
          |             + compiler plugin JAR
          |             + internal plugin dependencies
          |
          +--------> Maven AntRun Plugin realm
          |             + antrun plugin JAR
          |             + Ant library dependencies
          |             + ant-contrib (nếu khai báo cho plugin)
          |
          +--------> Maven Surefire Plugin realm
                        + surefire plugin JAR
                        + plugin-internal dependencies

Project compile/test/runtime dependencies:
    + commons-lang3 (nếu project dùng)
    + junit-jupiter (test scope)
    + ...
    (được các plugin tra cứu qua MavenProject rồi cung cấp
     cho compiler/JVM con theo mục đích; không tự chép
     vào mọi plugin realm)
~~~

Mỗi realm có những import quan hệ nhất định; sơ đồ trên chỉ mang tính khái niệm, không miêu tả tất cả classloaders nội bộ. Theo [Guide to Maven Classloading](https://maven.apache.org/guides/mini/guide-maven-classloading.html), **plugin classloader không tự chứa dependencies và build output của project**. Plugin có thể lấy project classpath thông qua MavenProject và chủ động tạo loader khác hoặc fork JVM khi goal cần.

Vì sao điều này quan trọng?

- Plugin A và plugin B có thể cần hai version khác nhau của một thư viện. Realm riêng giảm sự can thiệp lẫn nhau.
- Thêm `commons-lang3` ở project level **không** mặc định sửa lỗi thiếu Commons Lang trong code nội bộ của plugin.
- Thêm một JAR trong `plugin/dependencies` **không** mặc định sửa lỗi import của source ứng dụng.
- Một plugin có thể tạo custom loader kết hợp project classpath và plugin classpath; đó là **hành vi của plugin cụ thể**, không phải quy tắc gộp toàn cục của Maven.

**Classloader isolation không phải security sandbox.** Plugin chạy trong build process với quyền truy cập tài nguyên hệ thống tương ứng; chỉ tải plugin/dependency từ nguồn đáng tin cậy.

## 4. Khi nào thực sự nên thêm plugin dependency?

Không phải plugin nào cũng cần custom dependency. Hầu hết các project chỉ cần khai báo plugin + version + configuration; plugin POM của bản phát hành đã mang theo các library cần thiết.

Các tình huống có cơ sở để bổ sung dependency:

| Tình huống | Vì sao có thể cần? | Điều phải kiểm tra |
| --- | --- | --- |
| Một plugin hỗ trợ **extension/custom task** ngoài bộ mặc định | Plugin cần load JAR chứa task, ví dụ Ant-Contrib cho AntRun. | Hướng dẫn plugin về classpath và đúng coordinates. |
| Goal sử dụng **driver/provider** trong chính runtime của plugin | Provider class không có trong plugin realm mặc định. | Plugin docs có yêu cầu provider ở `plugin/dependencies` hay trong project dependencies? |
| Tích hợp **generator/formatter/transformer** chạy ngay trong plugin | Thư viện implementation của plugin là một tùy chọn. | Plugin có tham số riêng hoặc processor path thay vì plugin dependencies không? |
| Sửa lỗi thiếu library bên trong **plugin goal** đã xác minh | Classloader của plugin thiếu API/class cần thiết. | Stack trace, plugin docs, plugin POM, khả năng nâng plugin trước. |
| Sửa xung đột plugin transitive version đã hiểu rõ | Muốn kiểm soát một dependency của plugin. | Tương thích nhị phân, exclusions, kiểm thử build sạch. |

Các tình huống **thường không nên** thêm plugin dependencies:

- `src/main/java` thiếu một import → kiểm tra **project compile dependency**.
- `src/test/java` thiếu JUnit/Mockito → kiểm tra **project test dependency**.
- App chạy `java -cp ...` thiếu một thư viện → kiểm tra **runtime classpath**, đóng gói hoặc launcher.
- Annotation processor của `javac` chưa được kích hoạt → kiểm tra **processor path**/cấu hình compiler plugin tương ứng, không mặc định thêm processor vào realm.
- Chỉ muốn đổi tham số plugin như `release`, `skipTests` hoặc output directory → dùng **`<configuration>`**/user property được plugin công bố; không cần thêm JAR.
- Plugin rất cũ không chạy trên Maven/JDK mới → **ưu tiên nâng plugin** và xác nhận compatibility thay vì ghi đè hàng loạt JAR nội bộ.

**Quy tắc ra quyết định:** chỉ thêm khi biết **JAR cụ thể**, **goal cụ thể** và **lý do chính plugin cần nạp JAR đó**. Nếu chưa xác định được, xem tài liệu plugin và stack trace trước khi chỉnh POM.

## 5. Cú pháp chuẩn và ý nghĩa từng thành phần

Mẫu cơ bản:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.2.0</version>

            <configuration>
                <!-- Tham số cấu hình chung của goal, nếu có -->
            </configuration>

            <dependencies>
                <dependency>
                    <groupId>ant-contrib</groupId>
                    <artifactId>ant-contrib</artifactId>
                    <version>1.0b3</version>
                </dependency>
            </dependencies>
        </plugin>
    </plugins>
</build>
~~~

Các phần trên có mục đích độc lập:

- `<plugin><version>3.2.0</version>` chọn **phiên bản Maven AntRun Plugin**.
- `<plugin><dependencies>` khai báo **những artifact được thêm vào graph của plugin**.
- `<dependency><version>1.0b3</version>` chọn phiên bản Ant-Contrib; **không** thay version của AntRun Plugin.
- `<configuration>` gán **tham số của plugin goal**, ví dụ `target` của AntRun. Không phải mọi parameter đều mang tên property CLI giống tên XML.
- `<executions>` (không có trong mẫu tối giản trên) bind một hay nhiều goal với lifecycle phase; **khai báo dependency không tự tạo execution**.

Trong plugin dependencies, nên khai báo tọa độ rõ ràng `groupId/artifactId/version` và chỉ thêm `type`, `classifier` hoặc `exclusions` nếu có lý do. Không sao chép `<scope>test</scope>` từ project dependencies với kỳ vọng plugin chạy goal test mới nạp thư viện: **plugin dependency không có cùng ý nghĩa với project test classpath**. Hãy đọc POM schema/plugin docs và xác minh plugin resolution thực tế.

Nếu một plugin có nhiều dependency bổ sung, khai báo nhiều `<dependency>` trong đúng `<plugin><dependencies>`. Không khai báo một block `<build>` thứ hai ở cùng cấp POM để “thêm riêng”; nên tích hợp vào cấu trúc `build/plugins` hiện có.

## 6. Cấu hình một plugin dependency có transitive exclusion

Một custom task JAR có thể kéo theo những JAR đời cũ. Ví dụ chính thức của AntRun 3.2.0 dùng Ant-Contrib 1.0b3, có thể kéo dependency `ant:ant` cũ theo nhánh transitive. Để tránh làm nhiễu version Ant mà AntRun hiện đại đã sử dụng, có thể exclude dependency legacy của **riêng nhánh Ant-Contrib**:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.2.0</version>
    <dependencies>
        <dependency>
            <groupId>ant-contrib</groupId>
            <artifactId>ant-contrib</artifactId>
            <version>1.0b3</version>
            <exclusions>
                <exclusion>
                    <groupId>ant</groupId>
                    <artifactId>ant</artifactId>
                </exclusion>
            </exclusions>
        </dependency>
    </dependencies>
</plugin>
~~~

Đây là **mảnh XML trong `<build><plugins>`**, chưa phải POM đầy đủ.

Exclusion ở đây có phạm vi **đường dependency từ Ant-Contrib tới legacy Ant**, không phải “cấm mọi thư viện Ant của toàn dự án”. Nếu AntRun cần thư viện Ant khác để vận hành, exclusion trên một nhánh không loại mọi artifact có chữ “ant” trong groupId/artifactId.

Những điểm cần xác minh sau khi thêm exclusion:

1. Plugin có vẫn resolve và nạp được đúng custom task không?
2. Có bị thiếu class mà custom task dùng từ chính library bị loại không?
3. Có vô tình ép version không tương thích với API của plugin không?
4. Plugin behavior trên JDK/Maven hiện tại có được kiểm thử sạch chưa?
5. Nếu build chạy trong CI, repository của CI có đúng plugin và artifact không?

**Không xem exclusions là cách sửa mọi `NoSuchMethodError`**. Lỗi binary compatibility đôi khi nên giải quyết bằng nâng plugin hoặc đổi implementation chứ không cắt các nhánh tùy tiện.

## 7. Ví dụ hoàn chỉnh: AntRun dùng Ant-Contrib nhưng Java app chỉ dùng JDK

Ví dụ dưới đây có thể build với **Maven 3.9.x** và **JDK 17+**, nếu các plugin/dependency được resolve bình thường.

Mục đích:

1. Plugin AntRun chạy custom task `if` từ Ant-Contrib ở phase `validate`.
2. Ant-Contrib xuất hiện **chỉ trong plugin dependency**, không phải `project/dependencies`.
3. Project có một unit test JUnit Jupiter để minh họa **test dependency riêng**.
4. Mã Java chính sử dụng JDK chuẩn và chạy độc lập không cần Ant-Contrib.
5. Kết quả của `mvn dependency:tree` có thể so với log AntRun để chứng minh hai graph khác nhau.

Cấu trúc dự án:

~~~text
maven-plugin-deps-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/org/example/lesson/DemoApp.java
    └── test/
        └── java/org/example/lesson/DemoAppTest.java
~~~

### 7.1. pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.lesson</groupId>
    <artifactId>maven-plugin-deps-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- This is a PROJECT TEST dependency, not an AntRun library. -->
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
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.2.0</version>

                <executions>
                    <execution>
                        <id>run-custom-task</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <!-- The task is NOT inside Ant by default. -->
                                <taskdef
                                    resource="net/sf/antcontrib/antcontrib.properties"
                                    classpathref="maven.plugin.classpath"/>

                                <if>
                                    <equals arg1="plugin" arg2="plugin"/>
                                    <then>
                                        <echo message="custom-task=ACTIVE"/>
                                    </then>
                                </if>
                            </target>
                        </configuration>
                    </execution>
                </executions>

                <!-- These libraries are loaded for the AntRun plugin. -->
                <dependencies>
                    <dependency>
                        <groupId>ant-contrib</groupId>
                        <artifactId>ant-contrib</artifactId>
                        <version>1.0b3</version>
                        <exclusions>
                            <exclusion>
                                <groupId>ant</groupId>
                                <artifactId>ant</artifactId>
                            </exclusion>
                        </exclusions>
                    </dependency>
                </dependencies>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đây là POM đầy đủ**, không phải các mảnh XML rời ở mục trước. Các phiên bản cố định là ví dụ đào tạo, **không tự động là khuyến nghị phiên bản production mới nhất**. Trong project thật, kiểm tra compatibility, vulnerability và chính sách của nhóm trước khi chọn plugin/dependency versions.

Giải thích vị trí:

- `junit-jupiter` nằm ở **project dependencies** scope `test`, vì `src/test/java` import JUnit.
- `maven-compiler-plugin` ở `build/plugins` để biên dịch Java 17.
- `maven-surefire-plugin` ở `build/plugins` để chạy unit test.
- `maven-antrun-plugin` có execution `run` bind vào `validate`.
- `<target><taskdef .../>` khai báo task definitions từ JAR Ant-Contrib bằng **`maven.plugin.classpath`**.
- `<if>` là custom task của Ant-Contrib, chạy Ant `equals` và `echo` khi điều kiện đúng.
- `<plugin><dependencies>` chứa `ant-contrib`. Nếu chỉ thêm Ant-Contrib vào project dependencies, `taskdef` dùng plugin classpath **không bảo đảm** nhìn thấy nó.

### 7.2. Mã Java 17: DemoApp.java

Tạo tệp `src/main/java/org/example/lesson/DemoApp.java`:

~~~java
package org.example.lesson;

public final class DemoApp {
    private DemoApp() {
    }

    public record Label(String value) {
    }

    public static String greeting(String name) {
        Label label = new Label(name.strip());
        return "Hello, " + label.value() + "!";
    }

    public static void main(String[] args) {
        System.out.println(greeting(" Maven "));
    }
}
~~~

Tệp là một lớp Java hoàn chỉnh, dùng `record` (Java 17 hỗ trợ) và `String.strip()` của JDK. Mã **không import class Ant-Contrib, Ant hoặc JUnit**.

Với `name=" Maven "`, `strip()` trả `Maven` nên method `greeting` trả `Hello, Maven!`.

### 7.3. Test Java: DemoAppTest.java

Tạo tệp `src/test/java/org/example/lesson/DemoAppTest.java`:

~~~java
package org.example.lesson;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class DemoAppTest {
    @Test
    void createsGreeting() {
        assertEquals("Hello, Maven!", DemoApp.greeting(" Maven "));
    }
}
~~~

Test dùng JUnit từ **project test classpath** và gọi mã chính từ `target/classes`. Nó không cần biết Ant-Contrib đã làm gì trong plugin realm.

### 7.4. Build và chạy

Tại thư mục chứa `pom.xml`:

~~~bash
mvn -B -ntp clean verify
~~~

Maven thực hiện các phase chuẩn của lifecycle `jar`. Khi đến `validate`, AntRun goal thực thi custom task; nếu Ant-Contrib được tải/nạp đúng, log có thông điệp với **nội dung**:

~~~text
custom-task=ACTIVE
~~~

AntRun/Maven có thể thêm tiền tố logger, ví dụ `[echo]` hoặc `[INFO]`, nên đoạn trên **không phải toàn bộ stdout chính xác của lệnh Maven**. Chỉ kết luận goal thành công khi build report/log xác nhận phù hợp.

Sau `compile`, test compilation và test execution, một test method sẽ được chạy nếu plugin/runner hoạt động như POM mẫu. Để chạy ứng dụng:

~~~bash
java -cp target/classes org.example.lesson.DemoApp
~~~

**Stdout chính xác của riêng lệnh `java`:**

~~~text
Hello, Maven!
~~~

Lệnh `java` không cần truyền Ant-Contrib JAR vì `DemoApp` dùng duy nhất standard JDK API. Đây là kết quả mong muốn: **plugin có thêm library để build, nhưng app không phụ thuộc library đó**.

Các file output trọng tâm sau build:

~~~text
target/
├── classes/org/example/lesson/DemoApp.class
├── classes/org/example/lesson/DemoApp$Label.class
├── test-classes/org/example/lesson/DemoAppTest.class
├── surefire-reports/
│   ├── TEST-org.example.lesson.DemoAppTest.xml
│   └── org.example.lesson.DemoAppTest.txt
└── maven-plugin-deps-demo-1.0.0.jar
~~~

Đây là cây rút gọn; Maven có thể tạo thêm `maven-status`, metadata và báo cáo khác. Project POM không yêu cầu fat JAR và không đặt Ant-Contrib vào JAR ứng dụng.

## 8. Kiểm chứng thư viện đúng là plugin dependency

Có ba phép kiểm tra bổ sung cho nhau, không nên chỉ dựa vào một phép.

### 8.1. Chạy AntRun goal thực sự

~~~bash
mvn -B -ntp clean validate
~~~

Với POM mẫu, AntRun được bind tại `validate`; nếu goal thực thi thành công, log có thông điệp `custom-task=ACTIVE`. Lệnh `clean validate` **chưa chạy compiler/test**; đó là phép thử plugin gọn hơn `verify` khi chỉ muốn biết task Ant-Contrib có nạp được hay không.

Nếu lỗi do AntRun, xem `taskdef` resource/classpathref và thông điệp từ Ant, chứ không sửa ngay JUnit dependency.

### 8.2. Xem project dependency graph

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Ở POM mẫu, project graph sẽ tập trung vào JUnit Jupiter scope test và các transitive dependencies của JUnit. **Ant-Contrib không nằm trong project/dependencies**, nên không nên trông đợi Ant-Contrib xuất hiện trong cây project mặc định.

**Nhưng việc không có Ant-Contrib trong dependency:tree không chứng minh plugin chưa tải nó**: plugin dependencies được resolve riêng.

### 8.3. Xem plugin configuration cuối và class realm

~~~bash
mvn help:effective-pom
mvn -X validate
~~~

`help:effective-pom` cho thấy plugin, execution, version và `plugin/dependencies` sau khi Maven áp dụng parent/profile. `-X` có thể in chi tiết Maven tạo/điền plugin realm và những artifact plugin được resolve. Hình thức debug log phụ thuộc phiên bản Maven và plugin.

Cần chú ý:

- Không đồng nhất `dependency:tree` với plugin graph.
- Không đồng nhất `help:effective-pom` với bằng chứng goal đã chạy; goal vẫn cần bind/called.
- Không đồng nhất sự có mặt của JAR trong `~/.m2/repository` với việc nó được nạp vào classloader cụ thể.
- Chỉ chia sẻ debug log sau khi loại bí mật/đường dẫn riêng nếu đang ở môi trường tổ chức.

## 9. AntRun có sẵn các classpath references nào?

Maven AntRun Plugin cho Ant tasks truy cập các path references được tạo cho project/goal. Theo trang **Using the Classpaths** của AntRun 3.2.0:

~~~text
maven.compile.classpath
maven.runtime.classpath
maven.test.classpath
maven.plugin.classpath
~~~

Trong POM mẫu, `maven.plugin.classpath` là đường dẫn phù hợp cho Ant-Contrib task definitions. Nếu muốn quan sát trong AntRun target, có thể thêm mảnh:

~~~xml
<property name="plugin_cp" refid="maven.plugin.classpath"/>
<property name="compile_cp" refid="maven.compile.classpath"/>
<property name="test_cp" refid="maven.test.classpath"/>
<echo message="plugin-cp=${plugin_cp}"/>
<echo message="compile-cp=${compile_cp}"/>
<echo message="test-cp=${test_cp}"/>
~~~

Đây là **mảnh Ant target XML**, phải đặt **bên trong `<target>` của AntRun** nếu muốn dùng. Các dòng in ra có thể chứa đường dẫn máy/local Maven repository cụ thể, nên **không có một stdout chung chính xác cho mọi môi trường**.

Khi xem log:

- `plugin-cp` có thể chứa AntRun/Ant và Ant-Contrib cùng những dependency riêng của plugin.
- `compile-cp` phản ánh project compile classpath; ở ví dụ main dùng JDK nên không cần Ant-Contrib.
- `test-cp` có thêm JUnit test dependencies.
- Đây là các **Ant references của AntRun**, không phải user properties chung được Maven Core định nghĩa cho mọi goal.

Nếu không muốn log dài và lộ thư mục cá nhân, bỏ mảnh in classpath sau khi đã chẩn đoán xong. Trong CI, không in cả repository URLs/credentials hay những đường dẫn nhạy cảm.

## 10. Vì sao chỉ thêm `<dependencies>` chưa chắc đủ?

Một plugin cần library bổ sung **và** cần được chỉ dẫn cách dùng library đó. Những bước thường là:

1. **Khai báo plugin version** chính xác.
2. **Thêm plugin dependency** vào `<plugin><dependencies>`.
3. **Cấu hình goal** bằng `<configuration>` (ví dụ AntRun `taskdef` trỏ đúng resource).
4. **Gắn goal vào lifecycle** qua `<executions>` hoặc gọi goal trực tiếp.
5. **Chạy trong điều kiện đúng**: profile/module/JDK/repository phù hợp.
6. **Quan sát output thực** để biết custom task đã hoạt động.

Ví dụ thiếu `<taskdef>` trong AntRun có thể làm `<if>` không được nhận diện, dù Ant-Contrib JAR đã được tải. Ngược lại, có `<taskdef>` nhưng thiếu plugin dependency có thể gây lỗi không tìm được resource/class. Thêm dependency **không tự kích hoạt goal** và không tự sinh task definition.

Với plugin khác, tham số có thể tên `implementation`, `provider`, `task` hoặc `classpath`; **không đoán** tên. Hãy đọc tài liệu chính thức của **goal và version** đang dùng, vì có plugin hỗ trợ project dependencies hoặc custom loader theo cơ chế riêng thay vì `plugin/dependencies`.

## 11. Plugin dependencies, pluginManagement và parent POM

Với project nhiều module, parent POM thường quản lý plugins chung:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đây là **mảnh parent POM**. Nó quản lý plugin version/config mặc định khi plugin được sử dụng, nhưng **không tự bind `antrun:run` vào lifecycle** chỉ vì có trong `pluginManagement`.

Một module con thật sự muốn chạy task Ant-Contrib có thể khai báo plugin trong `<build><plugins>` và cấu hình execution/dependency tương ứng. Nếu parent đã quản lý version và plugin phù hợp, con có thể bỏ lặp lại `<version>` ở cấu hình plugin; tuy nhiên cần kiểm tra **effective POM**.

Các vấn đề kế thừa cần chú ý:

- `build/plugins` của parent có thể được kế thừa và ảnh hưởng đến các child; `<inherited>false</inherited>` có thể giới hạn kế thừa trong tình huống phù hợp.
- Nếu Ant-Contrib chỉ cần trong **một module**, đừng vội khai báo plugin dependency ở parent sao cho tất cả các module cùng nhận nó.
- `pluginManagement` là chỗ quản lý mặc định; không phải thứ buộc mọi module phải thực thi plugin.
- `project/dependencyManagement` **không tự điều khiển các transitive dependencies nội bộ của plugin**.
- Khi cần dependency khác nhau giữa modules, hãy đặt trong đúng plugin của module tương ứng và kiểm tra merge/inheritance; không ghi đè blind POM parent.

Một module có thể tự chọn project dependencies độc lập với plugin dependencies mà nó cần để build. Maven reactor aggregation (`<modules>`) cũng không đồng nghĩa mọi module có chung một plugin realm hoặc classpath Java ứng dụng.

## 12. Quy trình xác định version plugin và dependency tương thích

Khi thêm plugin dependency, cần pin và kiểm soát **hai loại phiên bản**:

- **Version của Maven plugin**: phiên bản định nghĩa goal, plugin implementation và những dependency mặc định của plugin.
- **Version của thư viện bổ sung**: phiên bản API/implementation mà plugin hoặc custom task cần load.

Ví dụ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.2.0</version>
    <dependencies>
        <dependency>
            <groupId>ant-contrib</groupId>
            <artifactId>ant-contrib</artifactId>
            <version>1.0b3</version>
        </dependency>
    </dependencies>
</plugin>
~~~

Mảnh này **chưa có exclusion** nên không phải mẫu đầy đủ được khuyến nghị cho bài Ant-Contrib. Nó chỉ minh họa hai version có vai trò khác nhau.

Vì sao cần kiểm tra kỹ?

- Plugin có thể được compile dựa trên một API version nhất định. Nếu thêm JAR mới làm phiên bản transitive khác được chọn, plugin có thể ném `NoSuchMethodError`, `AbstractMethodError` hoặc `LinkageError`.
- Dependency của plugin có thể kéo một thư viện mà Maven Core/API đã expose theo một cách riêng, dẫn tới classloader mismatch.
- Một library cũ có thể không chạy trên JDK mới; nâng bản library không phải lúc nào cũng tương thích binary với plugin cũ.
- Nếu version được lấy từ `SNAPSHOT` hoặc repository mutable, cùng POM có thể resolve nội dung khác nhau vào ngày khác.
- Nếu nhiều module sử dụng cùng một plugin, overrides khác nhau có thể dẫn đến hành vi build khó dự đoán.

Cách làm:

1. Xem **documentation và release notes** của plugin version hiện dùng.
2. Xác nhận dependency được plugin chấp nhận qua cách đó.
3. Chọn library version được plugin/task tương thích.
4. Kiểm tra transitive dependencies của library và xem có cần exclusion có cơ sở không.
5. Pin plugin version lẫn library version.
6. Chạy đúng goal và full build/test trong môi trường Maven/JDK của CI.
7. Ghi rõ lý do custom plugin dependency trong comment hoặc tài liệu dự án.

Ưu tiên sửa bằng **plugin release chính thức** nếu dependency nội bộ của plugin bị lỗi hoặc có CVE, thay vì tự ghi đè version khắp nơi mà không được kiểm chứng.

## 13. Xung đột phiên bản và exclusions trong plugin graph

Plugin dependencies cũng có graph bắc cầu. Giả sử:

~~~text
maven-antrun-plugin:3.2.0
  +-- Ant libraries compatible with plugin
  +-- plugin dependency ant-contrib:1.0b3
         +-- legacy ant:ant (transitive, older)
~~~

Một lớp có cùng qualified name đến từ hai JAR không tương thích trong **cùng realm** có thể khiến AntRun/custom task dùng nhầm API. Exclusion của chính ví dụ AntRun:

~~~xml
<exclusions>
    <exclusion>
        <groupId>ant</groupId>
        <artifactId>ant</artifactId>
    </exclusion>
</exclusions>
~~~

chặn **một nhánh** của graph plugin. Exclusion không tự loại tất cả thư viện Ant, cũng không điều chỉnh project dependencies của ứng dụng.

Không thêm mọi exclusion “cho sạch dependency tree”: nếu custom task cần API chỉ có ở thư viện bị loại, bạn sẽ tạo lỗi nạp lớp mới. Một số dependency có thể là optional/provider/runtime-only; xem POM/artifact thực tế trước khi quyết định.

**Phân biệt dependency conflict với classloader conflict:** Maven có thể hòa giải để chọn một version trong graph của một realm, nhưng nếu hai classloaders khác nhau cùng định nghĩa một class, Java có thể coi đó là hai kiểu khác nhau. `ClassCastException` hoặc lỗi linkage có thể đến từ class identity, không chỉ version string.

## 14. Annotation processor và các trường hợp đặc biệt

Một số công cụ cũng “chạy trong build”, nhưng **không phải tất cả đều nên cấu hình qua `plugin/dependencies`**.

### 14.1. Annotation processors

Với MapStruct, Lombok hoặc processor tự viết, các version mới của Maven Compiler Plugin có cơ chế `annotationProcessorPaths` hoặc processor dependencies/types phù hợp phiên bản. Processor được `javac` nạp qua processor path/module path tùy cấu hình, **không mặc định là plugin class realm**.

Ví dụ mảnh cấu hình Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <annotationProcessorPaths>
            <path>
                <groupId>org.mapstruct</groupId>
                <artifactId>mapstruct-processor</artifactId>
                <version>1.6.3</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

**Đây là mảnh minh họa cơ chế processor path**, không phải một plugin dependency chung và không được ghép tùy tiện vào POM bài thực hành. Nếu source import annotation MapStruct, cần thêm API annotation tương ứng trong project dependencies; processor path riêng phục vụ code generation. Khi nâng JDK/Compiler Plugin, phải xem release notes và yêu cầu xử lý annotation của phiên bản đó.

### 14.2. Test providers và Surefire

JUnit mà source test import cần project dependency `scope=test`. Maven Surefire Plugin có provider/runner logic và classpath test execution được thiết kế riêng. Đưa JUnit vào `<plugin><dependencies>` của Surefire không phải lựa chọn mặc định để giải quyết thiếu `org.junit.jupiter.api.Test` khi `testCompile`.

Nếu Surefire không tìm thấy test dù test source compile được, xem tên test, provider, Java version, fork/module path và cấu hình plugin thay vì chỉ thêm library vào plugin realm.

### 14.3. Build extensions

Plugin có `<extensions>true</extensions>` hoặc các build extensions trong `build/extensions` có cơ chế nạp lớp khác plugin goal thông thường. Core extensions trong `.mvn/extensions.xml` còn được nạp sớm hơn. **Không chuyển một Maven plugin thường thành extension chỉ để nó “nhìn thấy” thêm JAR**; đó là thay đổi kiến trúc build với tác động rộng.

### 14.4. Codegen plugin fork JVM

Một plugin sinh mã có thể dùng loader hoặc fork JVM riêng. JAR ở `plugin/dependencies` không nhất thiết được chuyển sang JVM con. Nếu thiếu thư viện trong process fork, xem tài liệu goal cho `classpath`, `javaagent`, `toolchain` hoặc provider path phù hợp; không suy rằng plugin realm và forked JVM dùng chung classpath.

## 15. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và xử lý |
| --- | --- | --- |
| `mvn dependency:tree` không thấy Ant-Contrib. | Ant-Contrib chỉ là plugin dependency. | Bình thường; xem `build/plugins` và AntRun goal/debug log. |
| AntRun không nhận task `if`. | Thiếu `taskdef` hoặc không thấy Ant-Contrib trên `maven.plugin.classpath`. | Xem resource path, plugin dependency và log `antrun:run`. |
| AntRun load được Ant-Contrib nhưng task ném `NoSuchMethodError`. | Xung đột phiên bản Ant hoặc dependency khác trong plugin realm. | Kiểm tra Ant-Contrib transitive graph, exclusion legacy Ant và plugin/JDK compatibility. |
| Java main không compile khi import Ant-Contrib. | Ant-Contrib chỉ nằm ở plugin realm. | Nếu source thật sự cần API, khai báo project dependency phù hợp; không dùng plugin dependency thay thế. |
| JUnit không compile dù Surefire chạy được. | Thiếu project test dependency. | Khai báo JUnit `scope=test`; test API không đến từ plugin realm. |
| Đã thêm plugin dependency nhưng goal không chạy. | Plugin chưa được bind/execution chưa phù hợp hoặc profile inactive. | Xem `<executions>`, phase và lệnh gọi goal. |
| Chạy `help:describe` nhưng custom task chưa xuất hiện. | Chỉ đọc plugin goal metadata, không chạy Ant target. | Chạy `validate`/execution thực tế rồi xem AntRun log. |
| `PluginResolutionException`. | Plugin/dependency tọa độ sai, thiếu repository, proxy, credentials hoặc offline. | Xác minh coordinates, `pluginRepositories`, mirror và quyền đọc. |
| Local chạy, CI báo thiếu plugin dependency. | Repository/mirror/policy khác, local cache che lỗi hoặc chưa pin version. | Chạy clean build trên CI và xem resolution log. |
| `project/dependencyManagement` có version nhưng plugin dùng version khác. | Management project không phải nơi quản lý plugin transitive deps. | Xem plugin POM, plugin-dependencies, version và cách resolver xử lý realm. |
| Lỗi `ClassNotFoundException` trong app sau package. | Runtime classpath của app thiếu thư viện. | Điều tra project runtime dependencies/packaging/launcher, không mặc định sửa plugin. |
| Lỗi trong Java annotation processor. | Processor path/annotation API hoặc JDK/Compiler Plugin config chưa đúng. | Kiểm tra processor-specific docs, không mặc định thêm plugin dependency. |
| Child nhận thêm plugin dependency không mong đợi. | Plugin config từ parent được kế thừa/merge. | Xem `help:effective-pom` đúng module; giới hạn inheritance nếu có lý do. |
| Plugin lỗi Java `UnsupportedClassVersionError`. | Plugin hoặc plugin dependency có bytecode quá mới với JDK đang chạy Maven. | Chọn JDK/plugin versions tương thích; `maven.compiler.release` không đổi JDK chạy Maven. |

**Quy trình ngắn:** xác định **goal nào lỗi** → class thiếu thuộc **plugin hay project/test/runtime** → plugin version và plugin dependency graph → cấu hình goal/execution → CI repository và JDK → sửa đúng chỗ, kiểm thử lại.

## 16. CI và bảo mật cho plugin dependencies

Maven plugin là **mã được thực thi trên máy build**, thường có quyền đọc/ghi workspace, repository, environment và có thể truy cập mạng. Vì vậy plugin dependency không chỉ là chuyện “compile được”.

Checklist:

- [ ] Chỉ thêm dependency khi biết rõ **goal cần JAR nào và vì sao**.
- [ ] Pin plugin version và dependency version thay vì dựa vào giá trị khó kiểm soát.
- [ ] Không dùng plugin/dependency từ repository không tin cậy.
- [ ] Review license, maintenance status, vulnerabilities của cả plugin và những JAR transitive.
- [ ] Nếu plugin cũ có CVE, cân nhắc nâng plugin thay vì chỉ override một JAR.
- [ ] Không hard-code credentials vào `pom.xml`, `settings.xml` được commit, hoặc tham số `-Dpassword` trong CI log.
- [ ] Không in `maven.plugin.classpath` hoặc toàn bộ `-X` log công khai nếu có đường dẫn/repository nội bộ và bí mật.
- [ ] Có test build sạch cho các environment chính (local, CI, JDK versions phù hợp).
- [ ] Ghi lý do exclusions, tránh gây khó hiểu cho người nâng phiên bản.
- [ ] Với parent POM, giới hạn plugin dependencies chỉ trong module/goal cần thiết.
- [ ] Không coi classloader isolation là sandbox giới hạn quyền plugin.
- [ ] Khi dùng Java 17 hoặc Java mới hơn, xác minh plugin/tool compatibility riêng với compiler release.

Một workflow CI mẫu cho repository có Maven Wrapper và JDK 17:

~~~yaml
name: Verify Maven plugin dependencies
on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Verify plugin and Java build
        run: ./mvnw -B -ntp clean verify
~~~

Đây là ví dụ dành cho repository **đã commit Maven Wrapper** và cấp quyền thực thi `mvnw`; project mẫu ở mục 7 **chưa tự tạo Maven Wrapper**. Nếu không có Wrapper, dùng `mvn` của runner được quản lý và pin version theo chính sách nhóm. `setup-java` chọn JDK; `maven.compiler.release` của POM không tự cài JDK.

## 17. Các bước áp dụng trong một dự án thực tế

Khi cần cấu hình dependencies riêng cho plugin, đi theo thứ tự dưới đây:

1. **Chỉ ra plugin và goal cụ thể.** Ghi groupId/artifactId/version và goal đang chạy, ví dụ `maven-antrun-plugin:3.2.0:run`.
2. **Đọc tài liệu plugin/goal.** Xác nhận plugin có hỗ trợ mở rộng bằng JAR tại `plugin/dependencies` và cơ chế load custom task/provider nếu cần.
3. **Xác định artifact bổ sung.** Tìm chính xác groupId/artifactId/version/type/classifier cần thiết, không đoán từ tên Java package.
4. **Kiểm tra liệu JAR thực sự đã ở plugin graph chưa.** Nếu plugin tự mang library và hoạt động tốt, không thêm trùng chỉ vì “an toàn”.
5. **Thêm `<dependency>` dưới đúng `<plugin><dependencies>`.** Không vô tình thêm vào `project/dependencies` hoặc plugin khác.
6. **Cấu hình goal tương ứng.** Với AntRun, thêm `taskdef classpathref=maven.plugin.classpath` và task mà bạn muốn chạy.
7. **Giới hạn transitive conflicts.** Chỉ thêm exclusion đã được giải thích và kiểm chứng, không xóa một nhánh ngẫu nhiên.
8. **Đảm bảo goal thực sự chạy.** Bind `<execution>` vào phase hoặc gọi plugin goal phù hợp.
9. **Chạy thử gọn rồi chạy full lifecycle.** Ví dụ `mvn clean validate` để kiểm tra AntRun; `mvn clean verify` để kiểm tra Java/JUnit.
10. **Kiểm tra project graph và plugin execution tách riêng.** Dùng `dependency:tree`, `help:effective-pom`, debug log có kiểm soát; không suy nội dung plugin realm từ project tree.
11. **Kiểm tra runtime của ứng dụng.** Không được tự nhận thêm thư viện chỉ dành cho plugin; JAR ứng dụng và dependencies phải hợp lý.
12. **Review và ghi chú.** Pin versions, ghi lý do custom dependency/exclusion, chạy CI sạch và theo dõi upgrade của plugin.

Đây là quy trình có thể áp dụng cho nhiều plugin, nhưng **cơ chế nạp thư viện bổ sung của từng plugin có thể khác**. Tài liệu goal cụ thể luôn được ưu tiên so với việc sao chép máy móc mẫu AntRun sang một plugin khác.

## 18. Tự kiểm tra kiến thức

1. **Thêm Ant-Contrib vào `project/dependencies` có chắc giúp AntRun nạp task `if` trong plugin classpath không?**  
   Không. Cần dùng cơ chế AntRun hỗ trợ, trong ví dụ là `plugin/dependencies` cùng `taskdef` trỏ tới `maven.plugin.classpath`.

2. **`<plugin><dependencies>` có tự làm mã Java chính import được thư viện đó không?**  
   Không. Project compile classpath là một tập riêng.

3. **Plugin được khai báo nhưng goal chưa chạy; chỉ thêm plugin dependency đã đủ không?**  
   Chưa. Cần gọi goal hoặc bind execution vào lifecycle.

4. **Tại sao Ant-Contrib 1.0b3 cần exclusion `ant:ant` trong mẫu?**  
   Để tránh legacy Ant bắc cầu xung đột với Ant hiện đại mà AntRun Plugin dùng; exclusion chỉ áp dụng trên nhánh dependency tương ứng.

5. **`mvn dependency:tree` không thấy Ant-Contrib có phải nó chưa được tải không?**  
   Không. Project dependency tree không trình bày đầy đủ plugin dependencies.

6. **Muốn thấy plugin version/configuration sau khi kế thừa parent thì dùng gì?**  
   `mvn help:effective-pom` trên đúng module, kết hợp log goal thực thi.

7. **Annotation processor phải luôn nằm dưới `plugin/dependencies` của Compiler Plugin?**  
   Không. Compiler/`javac` có processor path hoặc cơ chế khai báo processor riêng theo phiên bản.

8. **Một plugin realm tách biệt có ngăn plugin độc hại đọc file hoặc gọi network?**  
   Không. Realm tách classloading, không phải bảo mật sandbox.

9. **Nếu main code chỉ dùng JDK nhưng AntRun dùng Ant-Contrib, vì sao `java -cp target/classes ...` vẫn chạy được?**  
   App không cần Ant-Contrib ở runtime; library đó chỉ hỗ trợ plugin trong giai đoạn build.

10. **Có nên override plugin dependency để lấy version mới nhất bất kể plugin version?**  
    Không. Phải kiểm tra API/binary compatibility và thử nâng plugin chính thức trước nếu phù hợp.

## 19. Nguồn chính thức

- [Apache Maven — Guide to Maven Classloading](https://maven.apache.org/guides/mini/guide-maven-classloading.html) — giải thích plugin realms, Core/API/project realms, custom classloaders và plugin dependencies.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — cấu trúc `build/plugins/plugin/dependencies`, `dependencies`, `pluginManagement` và inheritance.
- [Apache Maven AntRun Plugin — Using tasks not included in Ant's default jar](https://maven.apache.org/plugins/maven-antrun-plugin/examples/customTasks) — ví dụ Ant-Contrib 1.0b3, exclusion legacy Ant, `taskdef` với `maven.plugin.classpath`.
- [Apache Maven AntRun Plugin 3.2.0 — Using the classpaths](https://maven.apache.org/components/plugins-archives/maven-antrun-plugin-3.2.0/examples/classpaths.html) — `maven.compile.classpath`, `maven.runtime.classpath`, `maven.test.classpath`, `maven.plugin.classpath`.
- [Apache Maven AntRun Plugin — antrun:run](https://maven.apache.org/plugins/maven-antrun-plugin/run-mojo.html) — goal và tham số Ant target.
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — scope, transitivity và dependency management của project.
- [Apache Maven Surefire Plugin — Configuring the Classpath](https://maven.apache.org/surefire/maven-surefire-plugin/examples/configuring-classpath.html) — test runtime classpath khác plugin realm.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html) — quan sát plugin config sau inheritance/profile.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — kiểm tra project dependencies, không thay thế plugin-graph analysis.

**Kết luận:** `<plugin><dependencies>` là cơ chế **bổ sung thư viện cho chính Maven plugin khi goal thật sự cần**, không phải nơi khai báo API dùng bởi ứng dụng/test. Chọn đúng plugin/version/goal, đặt dependency đúng chỗ, dùng configuration/Ant taskdef hoặc provider mechanism phù hợp, kiểm tra transitive conflicts và quan sát hành vi build thực tế. **Không thêm plugin dependency theo thói quen**, vì mỗi JAR bổ sung còn là một quyết định về compatibility và supply-chain security.
