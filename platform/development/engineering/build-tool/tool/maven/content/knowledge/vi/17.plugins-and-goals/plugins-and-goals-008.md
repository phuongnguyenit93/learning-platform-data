# Phụ thuộc của plugin và vùng nạp lớp tách khỏi ứng dụng trong Maven

## 1. Mục tiêu và khái niệm nền tảng

Một project Maven có thể vừa dùng **thư viện Java của ứng dụng** (project dependencies), vừa dùng **các Maven plugin** (Compiler, Surefire, Resources, AntRun...) để build, test và đóng gói. Plugin cũng là mã Java, vì vậy nó có thể phụ thuộc các JAR khác. Nhưng Maven **không gom tất cả JAR vào một classpath toàn cục**.

Ý tưởng cần nhớ:

> **Dependency của plugin được giải quyết cho vùng nạp lớp của plugin** (*plugin class realm*), không tự được thêm vào compile/test/runtime classpath của mã ứng dụng. Ngược lại, dependency khai báo cho ứng dụng không tự chui vào plugin realm.

Vì vậy ba câu hỏi sau là hoàn toàn khác nhau:

1. `src/main/java` muốn dùng `org.apache.commons.lang3.StringUtils`? → Khai báo `commons-lang3` trong **`<project><dependencies>`** với scope phù hợp.
2. Một Maven goal cần một thư viện để **chính plugin** thực thi tác vụ? → Xem plugin đã tự cung cấp thư viện đó chưa; khi thật sự cần, bổ sung trong **`<build><plugins><plugin><dependencies>`**.
3. Unit test muốn gọi JUnit? → Khai báo JUnit trong **project dependencies scope test**, không phải nhờ JUnit mà Maven Surefire Plugin có thể sử dụng nội bộ.

Không nhầm plugin Java của Maven với plugin của IDE, Java annotation processor, servlet container hoặc một “plugin” được ứng dụng tự nạp qua SPI. Các cơ chế ấy có thể liên quan tới classloading nhưng không phải cùng một khái niệm.

**Phạm vi bài:** cách Maven dựng các class realms, đường đi của plugin dependencies, quan hệ với project classpath, pluginManagement, cách debug xung đột và ví dụ Java 17/Maven chạy được.

## 2. Phân biệt project dependencies và plugin dependencies

Hai đoạn XML nhìn giống nhau, nhưng vị trí khác nhau sẽ cho kết quả khác nhau.

**Project dependency**, phục vụ mã nguồn hoặc runtime của chính module:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.17.0</version>
    </dependency>
</dependencies>
~~~

Mảnh này phải nằm trực tiếp trong `<project>`. Với scope mặc định `compile`, Commons Lang tham gia project compile/runtime/test classpaths theo quy tắc Maven. Mã ứng dụng có thể import `StringUtils`.

**Plugin dependency**, chỉ bổ sung thư viện cho một plugin:

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

Đây là mảnh XML cần đặt trong POM hợp lệ. Ở đây, Ant-Contrib bổ sung Ant tasks cho **Maven AntRun Plugin**. Nó **không** trở thành project dependency chỉ vì có thể tìm thấy JAR của Ant-Contrib trong local Maven repository.

| Khía cạnh | Project `dependencies` | `plugin/dependencies` |
| --- | --- | --- |
| Chủ thể cần JAR | Source/test/runtime ứng dụng theo scope | Code của một Maven plugin |
| Vị trí khai báo | `project/dependencies` | `project/build/plugins/plugin/dependencies` |
| Classpath/class realm | Compile, test và runtime classpaths do plugin/build tool dựng | Plugin class realm của plugin tương ứng |
| `dependency:tree` bình thường | Hiển thị graph của project | **Không** trình bày đầy đủ graph nội bộ plugin |
| Có tự làm main Java code import được thư viện không? | Có, nếu scope và resolution phù hợp | **Không** |
| Có tự làm plugin load được thư viện không? | Không nhất thiết | Được cung cấp trong plugin resolution/realm phù hợp |
| Mức độ transitive | Theo dependency graph và scopes của project | Theo graph/resolution áp dụng cho plugin |
| Quản lý qua `project/dependencyManagement` | Có | **Không áp dụng để tự ép version các thư viện nội bộ của plugin** |

**Lưu ý:** plugin dependencies không được hiểu là thứ nên thêm vào mỗi khi có lỗi. Plugin đã có tập dependency được công bố và kiểm thử cùng phiên bản của nó. Việc thay version JAR nội bộ tùy tiện dễ phá tính tương thích.

## 3. Maven dùng classloader và “realm” như thế nào?

Maven sử dụng **Plexus Classworlds** để tạo đồ thị classloader. Trong mô hình này, *realm* là vùng nạp lớp với những JAR và quan hệ import cụ thể, giúp tránh để tất cả thành phần dùng chung một tập lớp không kiểm soát.

Sơ đồ khái niệm:

~~~text
Java runtime (platform classes)
                |
                v
System/bootstrap classloader
                |
                v
Maven Core / Maven API
                |
       +--------+------------------+
       |                           |
       v                           v
Project/build-extension context    Plugin realm: compiler
       |                             - maven-compiler-plugin.jar
       |                             - plugin's own dependencies
       |
       +--------------------------> Plugin realm: antrun
       |                             - maven-antrun-plugin.jar
       |                             - plugin's own Ant dependencies
       |                             - optional ant-contrib plugin dependency
       |
       +--------------------------> Plugin realm: surefire
                                     - maven-surefire-plugin.jar
                                     - plugin's own dependencies

Project compile/test/runtime classpaths:
  are obtained through MavenProject and passed to tools/JVMs;
  they are NOT automatically copied into each plugin realm.
~~~

Sơ đồ đơn giản hóa cách import classloaders và không trình bày đầy đủ mọi realm nội bộ của từng Maven version. Theo hướng dẫn chính thức *Guide to Maven Classloading*:

- Maven Core có các thư viện của chính Maven.
- Maven API realm cho plugin thấy các gói API được công bố, thay vì mặc nhiên mọi implementation detail của Core.
- Maven có project realm và các realm cho build extensions theo mô hình Classworlds.
- Một **plugin thông thường có classloader/plugin realm riêng**, import từ project realm theo cơ chế Maven.
- **Plugin realm không tự chứa project dependencies hay project build output**. Plugin có thể yêu cầu MavenProject cung cấp các classpaths ấy, rồi chủ động tạo classloader hoặc fork JVM để xử lý công việc.
- Khi Maven gọi một Maven plugin, *thread context classloader* có thể được đặt thành classloader của plugin trong thời gian goal thực thi.
- Một số plugin tự tạo **custom classloader** cho tool mà chúng chạy; custom loader này không tự nhập ngược mọi class vào plugin realm.

Điểm tinh tế: **“plugin realm cách ly” không có nghĩa plugin bị sandbox bảo mật.** Plugin chạy mã tùy ý, có thể truy cập filesystem/network/biến môi trường với quyền của tiến trình Maven. Classloader isolation là cơ chế phân tách **visibility và version** của Java classes, **không phải** cơ chế giới hạn quyền truy cập.

## 4. Vì sao Maven phải tách các vùng nạp lớp?

Nếu mọi plugin và mọi project cùng chia sẻ một classpath, rất dễ xảy ra những mâu thuẫn:

~~~text
Ứng dụng cần commons-lang3 3.x
Plugin A cần một version của plexus-utils
Plugin B cần version khác của plexus-utils
Maven Core cần API/implementation riêng để vận hành
~~~

Trong một classloader phẳng, class có cùng tên đầy đủ (*fully qualified class name*) thường chỉ được định nghĩa một lần bởi loader tương ứng. Nếu một thành phần nhận nhầm binary version, có thể xuất hiện lỗi:

~~~text
java.lang.NoSuchMethodError
java.lang.NoClassDefFoundError
java.lang.LinkageError
java.lang.ClassCastException
~~~

**Plugin realms giúp giảm nguy cơ xung đột** giữa dependency nội bộ của các plugin. Hai plugin có thể dùng các tập JAR riêng mà không cần ép project Java phải dùng chung version với cả hai.

Tuy nhiên, cách ly không phải tuyệt đối: plugin còn import Maven API/project realm, các plugin có thể nhận class từ các realm được công bố, và có thể tự tạo classloader riêng. Một số lỗi nạp lớp phụ thuộc vào **loại class nào được share** và loader nào đã định nghĩa class đó. Vì thế, không kết luận cứ thấy `ClassCastException` là “thiếu dependency”; cần xem stack trace và classloader thực tế.

Điều Maven **không** tự làm cho bạn:

- Không đảm bảo mọi plugin version luôn tương thích với Maven Core/JDK đang chạy.
- Không đảm bảo ghi đè một JAR trong plugin dependencies sẽ tương thích với plugin binary.
- Không tạo classpath chung cho mọi plugin.
- Không chặn plugin độc hại thao tác trên máy.
- Không thêm library của plugin vào JAR chính của app.

## 5. Ai quản lý dependency graph của plugin?

Mỗi Maven plugin là một artifact, thường có packaging `maven-plugin` và **POM phát hành riêng**. Maven giải quyết plugin artifact cùng các transitive dependencies theo plugin descriptor/POM và cấu hình hiệu lực. Nếu project **không khai báo `<plugin><dependencies>`**, plugin vẫn có thể cần và được tải các thư viện nội bộ của nó từ repository.

Luồng khái niệm:

~~~text
pom.xml declares maven-antrun-plugin:3.2.0
                   |
                   v
Maven Plugin Resolution
  - resolve plugin artifact/POM
  - read plugin dependencies, transitive dependencies
  - combine additional dependencies declared in project plugin config
                   |
                   v
Plexus Classworlds creates/reuses relevant plugin realm
                   |
                   v
Maven executes plugin goal (for example antrun:run)
                   |
          +--------+---------+
          |                  |
          v                  v
Plugin's own libraries     Maven APIs/project model
                            (as exposed/imported)
                   |
                   v
Goal may request project compile/test/runtime classpath
or create extra loaders/fork JVM as needed.
~~~

Ví dụ AntRun Plugin có dependency chính thức vào Ant. Nếu project thêm Ant-Contrib trong `<plugin><dependencies>`, Maven resolver bổ sung Ant-Contrib (và transitive dependencies phù hợp) để AntRun có thể nạp những task của thư viện đó. **Đây là thay đổi plugin resolution**, không phải thay đổi project compile classpath.

Ngược lại, nếu project khai báo Ant-Contrib trong `<project><dependencies>`, project graph có thể chứa Ant-Contrib, nhưng AntRun **không mặc định có quyền thấy class đó ngay trong chính plugin realm**. Nếu plugin cần custom task, hãy dùng cơ chế mà plugin tài liệu yêu cầu.

## 6. Goal, phase, plugin declaration và class realm: không phải một thứ

Một plugin dependency chỉ có ý nghĩa khi có **plugin được resolve/sử dụng**. Các khái niệm phải tách biệt:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Plugin | `org.apache.maven.plugins:maven-antrun-plugin:3.2.0` | Artifact Maven chứa code thực thi goal. |
| Goal | `antrun:run` | Một tác vụ cụ thể do plugin cung cấp. |
| Phase | `validate`, `compile`, `test` | Vị trí trong Maven lifecycle. |
| Plugin execution | `<execution><phase>validate</phase><goals><goal>run</goal>...` | Cấu hình gắn goal vào lifecycle. |
| Plugin dependency | `ant-contrib:ant-contrib:1.0b3` trong `plugin/dependencies` | Thêm JAR để plugin có thể nạp class. |
| Plugin class realm | Realm do Maven tạo cho plugin thực thi | Vùng classloading riêng của plugin. |
| Project dependency | JUnit Jupiter `scope=test` | Library nằm trong project test graph, không phải plugin realm. |

**Không phải cứ thêm plugin dependency là Maven tự chạy thêm goal.** Goal cần có lifecycle binding, plugin execution hoặc được gọi trực tiếp. Ngược lại, một plugin goal vẫn có thể chạy mà không có project dependency nào, nếu nó chỉ làm tác vụ build độc lập.

Chạy:

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-antrun-plugin:3.2.0 -Dgoal=run -Ddetail
~~~

để xem mô tả goal và các tham số plugin công bố. Lệnh này dùng **Maven Help Plugin** để mô tả AntRun, không chạy `antrun:run` và cũng không chứng minh Ant-Contrib đã nạp thành công. Muốn kiểm tra thực, phải chạy goal/binding tương ứng.

## 7. Ví dụ hoàn chỉnh Java 17: plugin dùng Ant-Contrib, ứng dụng không dùng Ant-Contrib

Ví dụ sau dùng:

- **Ứng dụng Java 17** chỉ gọi các class của JDK, không import Ant/Ant-Contrib.
- **JUnit Jupiter** là project test dependency `scope=test`.
- **Maven AntRun Plugin 3.2.0** chạy một Ant task ở phase `validate`.
- **Ant-Contrib 1.0b3** là **dependency của AntRun Plugin**, nạp task `if` từ `maven.plugin.classpath`.
- **Compiler Plugin và Surefire Plugin** được pin version để compile Java 17 và chạy JUnit.
- Mục tiêu: khi `mvn clean verify` thành công, Ant-Contrib hoạt động trong build nhưng **không trở thành project compile/runtime dependency**.

Ví dụ Ant-Contrib theo đúng cơ chế `taskdef resource=... classpathref="maven.plugin.classpath"` có trong tài liệu chính thức Maven AntRun Plugin. Ant-Contrib là library cổ, dùng ở đây để minh họa classloading; khi triển khai thật, review maintenance/security và ưu tiên tool hiện đại phù hợp.

Cấu trúc:

~~~text
plugin-realm-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/org/example/realm/App.java
    └── test/
        └── java/org/example/realm/AppTest.java
~~~

### 7.1. pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>plugin-realm-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <!-- Project test classpath only -->
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
                        <id>check-plugin-realm</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <!-- Load Ant-Contrib task definitions using
                                     the plugin's classpath, not app classes. -->
                                <taskdef
                                    resource="net/sf/antcontrib/antcontrib.properties"
                                    classpathref="maven.plugin.classpath"/>
                                <if>
                                    <equals arg1="ready" arg2="ready"/>
                                    <then>
                                        <echo message="plugin-task=OK"/>
                                    </then>
                                </if>
                            </target>
                        </configuration>
                    </execution>
                </executions>

                <dependencies>
                    <!-- Plugin dependency, NOT project dependency -->
                    <dependency>
                        <groupId>ant-contrib</groupId>
                        <artifactId>ant-contrib</artifactId>
                        <version>1.0b3</version>
                        <exclusions>
                            <!-- Ant-Contrib's old Ant dependency should not
                                 replace the Ant used by modern AntRun. -->
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

**Đây là POM độc lập đầy đủ.** Lưu ý những điểm quan trọng:

1. `ant-contrib` nằm **trong Maven AntRun Plugin `<dependencies>`**, không nằm ở `project/dependencies`.
2. `<taskdef>` dùng `classpathref="maven.plugin.classpath"`, một Ant path reference mà Maven AntRun Plugin cung cấp.
3. `<if>` là task của Ant-Contrib; khi `taskdef` nạp thành công, task mới khả dụng.
4. `<exclusions>` chỉ loại dependency Ant đời cũ ở nhánh plugin dependency Ant-Contrib, tránh làm nhiễu Ant hiện tại của AntRun. Nó **không làm JDK app khác đi**.
5. `<phase>validate</phase>` khiến task chạy trong lifecycle, kể cả trước compile. Thay đổi phase có thể làm task chạy ở thời điểm khác; không cần thiết cho bài học.
6. `junit-jupiter` là project test dependency, dành cho source test; không phải plugin dependency của Antrun.
7. `maven.compiler.release=17` yêu cầu compiler target Java 17, nhưng **không tự cài JDK 17** trên máy.

### 7.2. Source chính App.java

Đặt tệp tại `src/main/java/org/example/realm/App.java`:

~~~java
package org.example.realm;

public final class App {
    private App() {
    }

    public record Message(String text) {
    }

    public static String message() {
        return new Message("main-only").text();
    }

    public static void main(String[] args) {
        System.out.println("app=" + message());
    }
}
~~~

Mã dùng `record` được Java 17 hỗ trợ và chỉ dùng các class của JDK. Nó **không import Ant-Contrib**. Thậm chí trong project compile classpath không có Ant-Contrib, `App.java` vẫn biên dịch được.

### 7.3. Unit test AppTest.java

Tệp `src/test/java/org/example/realm/AppTest.java`:

~~~java
package org.example.realm;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void mainMessageWorksWithoutBuildPluginLibraries() {
        assertEquals("main-only", App.message());
    }
}
~~~

Test phụ thuộc JUnit test scope. Nó không có lý do để import Ant-Contrib. Surefire có thể chạy test với test execution classpath bao gồm `target/classes`, `target/test-classes` và các dependency test cần thiết; điều đó không làm thay đổi classpath compile của `App.java`.

### 7.4. Lệnh build và output

Yêu cầu: JDK 17+, Maven 3.9.x hoặc bản tương thích với plugin, khả năng tải dependencies/plugins từ repository tin cậy.

Ở thư mục `plugin-realm-demo`:

~~~bash
mvn -B -ntp clean verify
~~~

Trình tự quan trọng: Maven chạy phase `validate` với `antrun:run`, sau đó đi qua compile, test-compile, test, package và verify theo lifecycle `jar`. Nếu Ant-Contrib được resolve và nạp thành công, log AntRun chứa **thông điệp**:

~~~text
plugin-task=OK
~~~

*Đây là nội dung thông điệp do Ant `echo` tạo; log đầy đủ có thể có tiền tố như `[echo]`, timestamp hoặc mức INFO tùy Maven/Ant logger. Không coi dòng trên là stdout cố định của toàn lệnh `mvn`.*

Sau build, chạy ứng dụng:

~~~bash
java -cp target/classes org.example.realm.App
~~~

**Stdout chính xác của riêng lệnh Java:**

~~~text
app=main-only
~~~

Ứng dụng không cần thêm Ant-Contrib, AntRun hay JUnit vào runtime classpath vì mã chính chỉ dùng JDK. Đây là minh họa rõ nhất: **build dùng Ant-Contrib trong plugin realm, còn ứng dụng chạy độc lập mà không có JAR Ant-Contrib**.

Sau khi build thành công, các output thông thường:

~~~text
target/
├── classes/org/example/realm/App.class
├── classes/org/example/realm/App$Message.class
├── test-classes/org/example/realm/AppTest.class
├── surefire-reports/
│   ├── TEST-org.example.realm.AppTest.xml
│   └── org.example.realm.AppTest.txt
└── plugin-realm-demo-1.0.0.jar
~~~

Cây trên chỉ là các file trọng tâm; các plugin có thể tạo thêm metadata/thư mục. `App$Message.class` là nested record class. JAR chính thông thường chứa App và nested record, **không mặc nhiên đóng gói Ant-Contrib hoặc JUnit test JAR**.

### 7.5. Cách nhận biết Ant-Contrib không phải project dependency

Chạy:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Trong project dependency graph của POM mẫu, bạn sẽ thấy `junit-jupiter` scope test cùng dependencies bắc cầu phù hợp. **Ant-Contrib không nằm ở `project/dependencies`**, do đó bình thường không xuất hiện như project dependency trong cây này. Nhưng Maven vẫn phải resolve Ant-Contrib cho AntRun goal ở phase `validate`.

Đừng dùng sự vắng mặt trong `dependency:tree` để kết luận Ant-Contrib **không được tải ở đâu cả**. Nó được tải theo **plugin dependency graph**; plugin realm và project dependency graph là hai tập riêng.

## 8. Thí nghiệm lỗi có kiểm soát: khai báo sai vị trí dẫn đến điều gì?

Sau khi chạy thành công mẫu mục 7, hãy suy nghĩ về ba thay đổi **giả định** dưới đây. **Không áp dụng các thay đổi này vào POM mẫu khi muốn giữ ví dụ chạy được.**

### Trường hợp A: Chuyển Ant-Contrib sang project dependencies

Nếu xóa Ant-Contrib khỏi `<plugin><dependencies>` và thêm nó trực tiếp vào `<project><dependencies>`, mã ứng dụng có thể được cung cấp các lớp Ant-Contrib trên project classpath theo scope. Nhưng AntRun Plugin **không được bảo đảm nhìn thấy chúng** trong `maven.plugin.classpath`. `taskdef` của ví dụ có thể lỗi vì task library không nằm trong plugin classpath như yêu cầu.

Vấn đề cần sửa là **đặt dependency về đúng plugin**, không đưa cả Ant-Contrib vào production dependencies.

### Trường hợp B: Giữ plugin dependency nhưng import Ant-Contrib trong App.java

Ví dụ cố tình sai:

~~~java
import net.sf.antcontrib.logic.IfTask;
~~~

Dòng này **không thuộc App.java chạy được ở mục 7**. Mã main có thể báo `package ... does not exist` vì Ant-Contrib chỉ có trong plugin realm. Việc AntRun dùng task `if` thành công không nói gì về quyền thấy class của Java compiler khi biên dịch source ứng dụng.

Nếu mã ứng dụng **thật sự cần một API ngoài JDK**, phải khai báo **project dependency** thích hợp, xét license/version/scope/runtime. Không dùng một plugin dependency như đường tắt để cung cấp API cho source.

### Trường hợp C: Thêm dependency trực tiếp vào app nhưng lại mong plugin giải quyết được

Giả sử project có `org.apache.commons:commons-lang3` scope compile. Maven Compiler Plugin có thể biên dịch code dùng `StringUtils`, nhưng không có nghĩa Maven AntRun Plugin tự nạp class từ Commons Lang trong chính plugin realm. Nếu một Ant task thực sự cần Commons Lang qua plugin classloader, phải áp dụng cơ chế được AntRun hỗ trợ như `<plugin><dependencies>` hoặc task-specific classpath đã được cấu hình đúng.

**Mấu chốt:** Maven plugins được phép **tạo classloader bổ sung** từ project classpath khi goal thiết kế như vậy; đó là hành vi rõ ràng của goal, không phải Maven Core tự gom các JAR của project vào plugin realm.

## 9. Cách quan sát plugin classpath với Maven AntRun

AntRun có sẵn các Ant path references liên quan đến Maven:

~~~text
maven.compile.classpath    -> project compile classpath
maven.runtime.classpath    -> project runtime classpath
maven.test.classpath       -> project test classpath
maven.plugin.classpath     -> plugin classpath của AntRun
~~~

Đây là **các references do AntRun cung cấp**, không phải bốn thuộc tính Maven Core có thể sử dụng tùy ý trong mọi plugin.

Để quan sát, có thể **thêm các dòng** sau bên trong `<target>` của AntRun ở POM mẫu:

~~~xml
<property name="project_compile_cp" refid="maven.compile.classpath"/>
<property name="project_test_cp" refid="maven.test.classpath"/>
<property name="antrun_plugin_cp" refid="maven.plugin.classpath"/>
<echo message="compile-cp=${project_compile_cp}"/>
<echo message="test-cp=${project_test_cp}"/>
<echo message="plugin-cp=${antrun_plugin_cp}"/>
~~~

Đoạn trên là **mảnh Ant task XML**, không phải POM độc lập. Output là chuỗi đường dẫn cụ thể của máy; **không có một stdout cố định** để copy vào báo cáo cho mọi OS. Trong kịch bản mẫu:

- Project compile classpath không cần Ant-Contrib vì Java main chỉ dùng JDK.
- Test classpath có JUnit test dependencies.
- Plugin classpath của AntRun có AntRun/Ant và **Ant-Contrib** mà bạn khai báo ở `plugin/dependencies`.

Không dùng log in classpath vào public CI mà không xem dữ liệu chứa đường dẫn nội bộ, repository URLs, user-specific paths. Dùng kiểm tra cục bộ khi debug rồi bỏ logging nếu không cần.

Tài liệu chính thức của AntRun mô tả cụ thể `maven.plugin.classpath` và các project classpath references, vì vậy ví dụ này có cơ sở rõ ràng, thay vì đoán cấu trúc classloader từ một tên tùy ý.

## 10. Plugin realm khác test execution classpath của Surefire

Maven Surefire là ví dụ dễ gây nhầm:

~~~text
Maven invokes maven-surefire-plugin
          |
          v
Surefire plugin realm (plugin code and dependencies)
          |
          v
Goal builds test execution classpath
  target/test-classes
  target/classes
  project dependencies in test scopes
  additional configured test entries, if any
          |
          v
JUnit/TestNG provider and test execution
(optionally in a forked JVM)
~~~

JUnit được test source import cần có ở **project test dependencies**, hoặc ở cơ chế test execution được plugin hỗ trợ. Việc plugin Surefire có provider/runner internals **không làm JUnit API tự xuất hiện trong test compiler classpath nếu project không khai báo**.

Ngược lại, nếu test JVM chạy lỗi `ClassNotFoundException`, không được mặc định sửa plugin realm: lỗi có thể nằm ở test dependency graph, provider selection, fork configuration, Java module path hoặc custom classpath của Surefire.

Tương tự, Maven Compiler Plugin dùng **project compile classpath** để thực hiện compile. Nó có plugin realm phục vụ code/plugin dependencies của chính nó nhưng **không biến compiler realm thành classpath của `javac` một cách tự động**.

**Lưu ý với Java 9+:** Plugin có thể sử dụng **module path** (JPMS) thay vì classpath cho source modular tùy phiên bản/configuration. Việc `<dependency>` đã resolve chưa đủ để kết luận named module đọc được mọi package; cần xem `module-info.java`, `requires`, `exports`.

## 11. PluginManagement, inheritance và dependencies của plugin

Trong parent POM, `pluginManagement` cho phép quản lý version, cấu hình và một số thông số mặc định cho plugin mà child sẽ dùng:

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

Đây là mảnh cấu hình parent POM. Nếu child khai báo plugin AntRun trong `build/plugins`, plugin version có thể được lấy từ parent `pluginManagement`. Nhưng **chỉ liệt kê AntRun trong pluginManagement không tự làm goal `antrun:run` chạy**. Goal vẫn cần được gọi hoặc có execution/lifecycle binding phù hợp.

Một plugin trong `build/plugins` của parent có thể được kế thừa vào child (trừ cấu hình giới hạn như `<inherited>false</inherited>`) và có thể áp dụng execution cho nhiều module. Nếu bạn thêm **plugin dependency** vào một plugin ở parent, điều đó có thể tác động tới plugin realm trong nhiều child. Trước khi thay plugin-level libraries ở parent, cần kiểm tra các module thực sự thực thi plugin đó.

**`dependencyManagement` của project không phải `pluginManagement`.** Trong đó:

- `dependencyManagement` quản lý các dependency của project (và transitive resolution liên quan).
- `pluginManagement` quản lý Maven plugins và cấu hình của chúng.
- `plugin/dependencies` bổ sung JAR phục vụ chính plugin.
- Một entry trong project `dependencyManagement` **không tự ép version thư viện transitive của Maven plugin**.

Ví dụ khai báo `commons-lang3` version 3.17.0 trong `dependencyManagement` của app không mặc nhiên thay version Commons Lang mà một plugin đang dùng nội bộ. Muốn tác động tới plugin, phải xét plugin version và cơ chế plugin dependencies; cách ghi đè thư viện có thể không an toàn vì plugin có kỳ vọng binary API khác.

## 12. Tại sao plugin dependency có thể xung đột dù class realm tách riêng?

Cách ly class realm giảm xung đột **giữa các plugin và project**, nhưng không loại bỏ xung đột **bên trong một plugin realm**. Ví dụ:

~~~text
maven-antrun-plugin:3.2.0
    |
    +-- org.apache.ant:ant:1.10.x
    +-- plugin dependency ant-contrib:1.0b3
          |
          +-- transitive dependency ant:ant (old version)
~~~

Nếu để Ant-Contrib kéo vào một Ant rất cũ, graph có thể tạo version conflict với Ant mà AntRun hiện đại đang sử dụng. Chính vì vậy ví dụ tài liệu AntRun sử dụng:

~~~xml
<exclusions>
    <exclusion>
        <groupId>ant</groupId>
        <artifactId>ant</artifactId>
    </exclusion>
</exclusions>
~~~

Đây là **mảnh bên trong dependency Ant-Contrib của plugin**, không phải global exclusion cho toàn project. Nó ngăn nhánh legacy `ant:ant`, để AntRun sử dụng thư viện Ant phù hợp hơn với phiên bản plugin.

Dù có exclusion, **không cam kết mọi Ant-Contrib task đều hoạt động trên mọi phiên bản Ant/JDK**. Ví dụ học tập dùng `if`, nhưng ứng dụng production phải kiểm tra plugin compatibility, bảo trì thư viện và vulnerability status.

Một lỗi điển hình khác là cưỡng ép plugin dependency version mới hơn để chữa cảnh báo scanner; có thể plugin sẽ thiếu method mà version cũ cung cấp, hoặc Maven API/Guice/Plexus ABI thay đổi. Nên **ưu tiên nâng phiên bản plugin** đã tương thích với thư viện mới trước khi tự override nội bộ.

## 13. Vùng Maven Core, API, build extensions khác gì plugin realm?

Trong Maven 3, cần phân biệt thêm một số tầng:

| Vùng | Vai trò | Lưu ý |
| --- | --- | --- |
| Maven Core realm | Chứa các thư viện để Maven vận hành. | Không nên sửa tùy tiện thư mục cài Maven `lib`. |
| Maven API realm | Cho plugins/extensions thấy API được công bố. | Plugin import API từ Maven, không đồng nghĩa mọi lớp nội bộ Core đều public. |
| Project realm | Ngữ cảnh classloader gắn với một MavenProject và extension classes phù hợp. | Không tự chứa toàn bộ project compile dependencies. |
| Plugin realm | Dành cho plugin thông thường, plugin artifact và plugin dependencies. | Maven tạo/khai thác khi plugin được chạy. |
| Build extension realm | Dành cho build extensions hoặc plugin với `<extensions>true</extensions>`. | Có cơ chế đặc biệt, không giống plugin execution thông thường. |
| Custom loader do plugin tạo | Do riêng plugin dựng để chạy tool, test, code generator... | Có thể gồm project classpath, plugin classpath hoặc cả hai theo thiết kế plugin. |

Vì plugin realm không được phép tự “nhìn thấy mọi thứ”, nhiều plugin sử dụng API của MavenProject để lấy classpath theo scope. Maven Mojo có thể công bố nhu cầu dependency resolution ở descriptor/annotations (ví dụ một goal yêu cầu resolution `runtime` để biết runtime artifacts). **Đó là yêu cầu resolve project graph**, không phải thao tác chép toàn bộ JAR vào plugin realm.

**Build extensions là ngoại lệ đáng chú ý:** `<extensions>true</extensions>` trong plugin hoặc `build/extensions` ảnh hưởng đến Maven build architecture và classloading; không nên dùng tùy tiện chỉ để sửa `ClassNotFoundException`. Core extensions qua `.mvn/extensions.xml` còn được nạp rất sớm, có phạm vi/tác động khác; chúng cần quyền tin cậy và compatibility review riêng.

## 14. Annotation processors và code generators: một ranh giới khác

Một nhầm lẫn phổ biến là cho rằng **annotation processor** luôn thuộc Maven plugin realm. Thực tế, Java compiler có thể chạy annotation processors bằng một **processor path** hoặc cơ chế dependency riêng theo compiler plugin và JDK.

Ví dụ MapStruct/Lombok hoặc một processor tự viết:

- **Annotation API** mà mã source import có thể là project dependency.
- **Annotation processor implementation** cần được compiler phát hiện và nạp trong quá trình compile theo `annotationProcessorPaths`, processor dependency types hoặc cơ chế plugin/JDK tương ứng.
- **Maven Compiler Plugin** tự chạy trong plugin realm của Maven.
- **javac/annotation processor loader** có thể là classloader/module path riêng do compiler tạo, không đồng nhất với plugin realm.

Đừng đưa mọi annotation processor JAR vào `<plugin><dependencies>` của Compiler Plugin và cho rằng nó sẽ tự chạy. Kiểm tra đúng phiên bản Maven Compiler Plugin, JDK và tài liệu xử lý annotation. Từ JDK 23, các thay đổi mặc định về annotation processing khiến việc khai báo processor một cách rõ ràng càng quan trọng.

Tương tự, codegen plugin có thể tạo source trong `target/generated-sources` hoặc fork tiến trình; nhưng **class được tạo ra** vẫn phải được đưa vào project source roots/build output đúng cách. Nó không tự thành class trong plugin realm chỉ vì plugin sinh ra file.

## 15. Cách kiểm tra plugin nào đã chạy và nạp lớp gì

### 15.1. Xem cấu hình plugin hiệu lực

~~~bash
mvn help:effective-pom
~~~

Tìm `<build><plugins>`, `<pluginManagement>`, `<executions>` và `<plugin><dependencies>` của plugin gây vấn đề. Vì parent/profile có thể thêm hoặc override plugin, **đọc file `pom.xml` của module hiện tại thôi có thể chưa đủ**.

Trong reactor:

~~~bash
mvn -pl :your-module help:effective-pom
~~~

`your-module` là tên ví dụ; phải thay bằng artifactId module thực tế nếu muốn chạy. Không áp dụng nguyên lệnh ấy vào project mẫu một module ở mục 7.

### 15.2. Dùng debug log khi cần, nhưng bảo vệ dữ liệu

~~~bash
mvn -X validate
~~~

Debug log của Maven thường có thông tin về class realm cho một plugin, plugin artifact resolution và những goal được thực thi. Dùng nó để phân biệt:

- Lỗi resolve plugin artifact/JAR từ repository.
- Lỗi nạp dependency của plugin vào plugin realm.
- Lỗi nạp class trong JVM/loader của test hoặc ứng dụng.
- Lỗi Maven Core/API version compatibility.

**Không công bố nguyên log `-X`** khi log có repository URLs nội bộ, secrets trong user properties, file paths người dùng hoặc CI environment. Chỉ trích đoạn cần thiết sau khi loại bỏ thông tin nhạy cảm.

### 15.3. Dùng project dependency tree đúng mục đích

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Lệnh này hữu ích cho **project dependency graph**, nhưng không phải cách liệt kê plugin realm. Để kiểm tra plugin dependencies, hãy đọc POM plugin phát hành, plugin config và Maven debug log.

### 15.4. Chạy đúng goal

~~~bash
mvn -B -ntp validate
mvn -B -ntp clean verify
~~~

Ở dự án mẫu, AntRun đã được bind vào `validate`, nên cả hai lệnh đều có thể thực hiện Ant-Contrib task. Nhưng lệnh `validate` **chưa compile App.java**; muốn có `target/classes/App.class` và chạy ứng dụng, hãy chạy đến `compile` hoặc `verify`.

Không dùng `help:describe` như bằng chứng rằng goal đã chạy. Nó chỉ đọc metadata plugin; việc execution thành công phải xem log/output của lệnh thực thi.

## 16. Bảng lỗi: thiếu class thuộc vùng nào?

| Triệu chứng | Vùng đáng kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| Compiler báo `package org.apache.commons.lang3 does not exist` trong main source. | **Project compile classpath** | Thêm project dependency có scope phù hợp, kiểm tra tọa độ/version. |
| Test compiler báo thiếu `org.junit.jupiter.api.Test`. | **Project test compile classpath** | Khai báo JUnit ở project `scope=test`; không trông chờ Surefire tự cho source thấy API. |
| AntRun báo không tìm thấy Ant-Contrib `if` task hoặc `taskdef` resource. | **AntRun plugin/task classpath** | Kiểm tra `plugin/dependencies`, `maven.plugin.classpath`, exclusions và taskdef path. |
| `mvn dependency:tree` không thấy Ant-Contrib nhưng AntRun sử dụng được. | Không phải lỗi | Plugin dependency thuộc realm khác project tree. |
| Thêm Ant-Contrib vào project `dependencies` mà AntRun vẫn không load task. | **Plugin realm** | Đặt đúng vào plugin dependencies và taskdef classpath. |
| Java app chạy lỗi `NoClassDefFoundError` cho thư viện mà main code dùng. | **App runtime classpath** | Đưa compile/runtime JAR vào launcher/package phù hợp. |
| Surefire báo test `ClassNotFoundException`/provider error. | **Test execution classpath/provider/fork** | Xem Surefire logs, test dependencies, plugin version và JPMS settings. |
| Plugin goal ném `NoSuchMethodError` từ Plexus/Ant libraries. | **Plugin realm hoặc Maven API compatibility** | Kiểm tra phiên bản plugin và các plugin dependencies bị override. |
| Chạy được trên JDK này nhưng không chạy trên JDK khác. | **JDK + plugin compatibility** | So JDK, Maven, plugin release notes và bytecode target. |
| Compiler có plugin dependency X nhưng main source không import được X. | Hai classpaths bị nhầm | Chuyển/thêm dependency vào project đúng scope nếu mã main thật sự dùng X. |
| `<pluginManagement>` có plugin nhưng goal không chạy. | Lifecycle/execution | Kích hoạt plugin ở `build/plugins`, bind goal hoặc gọi goal trực tiếp. |
| Maven báo `PluginResolutionException` trước khi compile. | Plugin repository/resolution | Kiểm tra plugin coordinates, `pluginRepositories`, mirror, policy và network. |
| Custom task loaded nhưng runtime cast lỗi class cùng tên khác loader. | Classloader identity | Xem API nào cần chia sẻ, custom loader và plugin/library version. |
| Build extension gây lỗi nạp Maven API. | **Extension realm / Core API compatibility** | Xem phiên bản extension, Maven 3/4 support, không chữa bằng cách thêm library vào app. |

### Đường quyết định ngắn

~~~text
Lỗi ở bước compile main?
  -> project dependencies / compile scope.

Lỗi khi compile test?
  -> test scope, target/classes, test compiler setup.

Lỗi khi chạy unit/integration test?
  -> test execution classpath, Surefire/Failsafe, fork/module path.

Lỗi khi chạy "java" sau Maven build?
  -> application runtime classpath và packaging.

Lỗi trong stack trace code Maven plugin?
  -> plugin version, plugin realm, plugin dependencies, Maven API.

Lỗi ở build extension/core trước cả plugin goal?
  -> extension/Core realm, Maven version và configuration.
~~~

## 17. Plugin dependencies và tính tái lập, bảo mật

Do Maven plugin được thực thi **trong môi trường build có quyền truy cập cao**, chọn plugin và plugin dependencies phải được coi là một phần của **software supply chain**.

Những khuyến nghị chính:

1. **Pin plugin versions**, không dựa vào version mặc định thay đổi theo Maven lifecycle/plugin discovery.
2. **Chỉ thêm `<plugin><dependencies>` khi cần** và có tài liệu/test xác minh. Một dependency thêm vào plugin realm có thể làm thay đổi version mediation và hành vi plugin.
3. **Ưu tiên plugin hiện đại được bảo trì** thay vì thêm nhiều override để giữ một plugin quá cũ chạy trên JDK mới.
4. **Review transitive dependencies** của plugin khi có advisory, không chỉ review project dependency tree. Plugin graph cần kiểm tra riêng qua POM/artifact/scan thích hợp.
5. **Không tải plugin từ repository không tin cậy**. Maven plugin là executable code trên build machine; repository/mirror settings và artifact integrity rất quan trọng.
6. **Không lưu credentials trong POM**; dùng settings/secret manager của CI và nguyên tắc quyền tối thiểu.
7. **Pin JDK/Maven** hoặc dùng Maven Wrapper để giảm khác biệt giữa local và CI. Maven 4 và Maven 3 có thay đổi về API/build/tooling, không nên giả định một plugin cũ chạy tương đương.
8. **Không dùng scope=system** hoặc đường JAR hard-code trên máy để chữa plugin resolution; build sẽ khó tái lập giữa các runner.
9. **Ghi lại plugin version và nguyên nhân override** trong commit/README dự án, để người sau hiểu vì sao dependency nằm dưới plugin thay vì project.
10. **Test ít nhất một build sạch trên CI** sau khi thay plugin dependencies, vì cache local có thể che lỗi artifact resolution.
11. **Giới hạn debug logging**: nếu cần `-X`, bỏ secret và nội dung nội bộ trước khi chia sẻ.
12. **Quan sát output thật của plugin** thay vì giả định JAR tồn tại là goal đã chạy; điều kiện profile, phase và execution vẫn có thể vô hiệu hóa plugin.

Đối với ví dụ mục 7, Ant-Contrib `1.0b3` là một dependency cổ dùng minh họa. Trong dự án sản xuất không nên copy nguyên một plugin dependency cũ mà chưa đánh giá tình trạng bảo trì và rủi ro hiện tại.

## 18. Câu hỏi tự kiểm tra và checklist

### Câu hỏi

1. **Vì sao mã Java app không import được Ant-Contrib dù Maven AntRun chạy task `if` thành công?**  
   Vì Ant-Contrib nằm trong **plugin dependency**, được nạp cho AntRun; main compile classpath không tự nhận nó.

2. **Thêm Commons Lang vào `project/dependencies` có tự thêm cùng JAR vào mọi plugin realm không?**  
   Không. Plugin có classloading riêng và có thể tạo loader khác theo thiết kế, nhưng Maven Core không tự copy project deps vào từng plugin realm.

3. **`dependency:tree` có thể hiện đầy đủ graph của maven-antrun-plugin không?**  
   Không. Nó hiển thị project dependency graph; plugin realm cần xem plugin POM/config/log.

4. **JUnit được test source sử dụng thì đặt ở đâu?**  
   Trong `project/dependencies` với `scope=test` khi phù hợp; không nhầm với thư viện nội bộ của Surefire Plugin.

5. **Chỉ khai báo plugin trong `pluginManagement` thì Ant-Contrib task tự chạy?**  
   Không. Cần plugin thực sự được dùng và goal được bind hoặc gọi.

6. **Plugin class realm có phải một sandbox ngăn plugin ghi file hoặc truy cập mạng không?**  
   Không. Đó là cách ly classloading/version visibility, không phải security sandbox.

7. **Vì sao snippet AntRun dùng `classpathref="maven.plugin.classpath"`?**  
   Để Ant nạp Ant-Contrib task definitions từ classpath của **plugin** thay vì dùng project compile/test classpath.

8. **Nếu cùng tên class xuất hiện ở hai realm, chúng có luôn là cùng một Java Class không?**  
   Không. Java class identity còn phụ thuộc defining classloader; khác loader có thể tạo ra hai Class objects không cast qua lại được.

9. **Annotation processor có mặc định thuộc plugin realm của Compiler Plugin?**  
   Không. Processor có processor path/classloader/module path riêng tùy JDK/plugin configuration.

10. **Khi plugin ném `NoSuchMethodError`, bước đầu tiên nên làm gì?**  
    Xác định code/loader gây lỗi, plugin version và plugin dependencies, rồi so Maven API/JDK compatibility thay vì sửa project dependencies bừa bãi.

### Checklist áp dụng trong code review

- [ ] Dependency của **mã chính** nằm trong project `dependencies`, scope phù hợp.
- [ ] Dependency cho **test code** nằm trong project test graph.
- [ ] Dependency **chỉ cho plugin** nằm dưới đúng plugin, không gây ô nhiễm project classpath.
- [ ] Plugin goal được bind/called rõ ràng; không nhầm pluginManagement với execution.
- [ ] Plugin/dependency versions được pin hoặc có chiến lược quản lý tương thích.
- [ ] Không overwrite transitive plugin libs mà thiếu compatibility test.
- [ ] Đã kiểm tra output/log thật, không chỉ dependency tree hoặc effective POM.
- [ ] Nếu plugin tạo custom classloader/fork JVM, đã phân biệt classpath của nó với plugin realm.
- [ ] Đã cân nhắc extensions/JPMS/annotation processors khi classloader behavior bất thường.
- [ ] Đã kiểm tra build trên JDK/Maven của CI và review plugin supply-chain risk.

## 19. Tài liệu tham khảo chính thức

- [Apache Maven — Guide to Maven Classloading](https://maven.apache.org/guides/mini/guide-maven-classloading.html): core/API/project/plugin/build-extension realms và cơ chế plugin dependencies.
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): `build/plugins`, project dependencies và plugin management.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): cấu trúc `<plugins>`, `<plugin><dependencies>`, inheritance và dependency management.
- [Maven AntRun Plugin — Using tasks not included in Ant's default jar](https://maven.apache.org/plugins/maven-antrun-plugin/examples/customTasks): ví dụ Ant-Contrib plugin dependency, exclusion legacy Ant và `maven.plugin.classpath`.
- [Maven AntRun Plugin — Using the classpaths](https://maven.apache.org/plugins/maven-antrun-plugin/examples/classpaths.html): các path references compile/runtime/test/plugin do AntRun cung cấp.
- [Maven AntRun Plugin — antrun:run](https://maven.apache.org/plugins/maven-antrun-plugin/run-mojo.html): goal thực thi Ant target.
- [Maven Surefire Plugin — Configuring the Classpath](https://maven.apache.org/surefire/maven-surefire-plugin/examples/configuring-classpath.html): cách dựng test execution classpath.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): project dependency tree và giới hạn sử dụng trong chẩn đoán.
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): xem plugin configuration đã merge từ parent/profile.

**Kết luận:** Maven plugin có **dependency graph và plugin class realm riêng**, khác với compile/test/runtime classpaths của ứng dụng. `project/dependencies` phục vụ Java source và runtime; `plugin/dependencies` phục vụ code của một plugin. Một plugin có thể chủ động dùng project classpath hoặc tạo custom loader, nhưng Maven **không tự hợp nhất tất cả các vùng nạp lớp**. Khi gặp lỗi nạp class, xác định **goal nào đang chạy và loader nào thiếu class** trước khi thay dependency hoặc version.
