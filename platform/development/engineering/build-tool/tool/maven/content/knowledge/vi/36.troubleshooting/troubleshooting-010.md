# Xung đột classloader plugin so với classpath ứng dụng trong Maven

## 1. Tình huống: có dependency nhưng plugin vẫn báo thiếu class

Một ứng dụng Java compile thành công và có thư viện trên `mvn dependency:tree`. Tuy nhiên một Maven plugin lại fail:

~~~text
[ERROR] A required class was missing while executing ...
[ERROR] java.lang.NoClassDefFoundError: org/example/Helper
[ERROR] realm = plugin>org.example:sample-maven-plugin:1.0.0
~~~

Không có mâu thuẫn ở đây. **Maven plugin và ứng dụng không dùng chung một classpath mặc định.** Project khai dependency để biên dịch/chạy mã ứng dụng; plugin chạy mã của chính plugin trong một **class realm khác**. Mỗi nơi có dependency graph, version mediation và thời điểm tải lớp riêng.

Một triệu chứng khác là:

~~~text
java.lang.NoSuchMethodError: ...
~~~

Class thực sự có thể đã được nạp, nhưng phiên bản JAR trong **loader đang thực thi** không chứa method với binary signature mà code gọi. Đó là vấn đề tương thích nhị phân, không chỉ thiếu `.jar`.

Bài này thuộc nhóm **Chẩn đoán lỗi**. Ta sẽ tìm đúng nguyên nhân trước khi sửa `pom.xml`, tránh workaround như thêm cùng dependency vào mọi chỗ, sửa `$MAVEN_HOME/lib` hoặc xóa toàn bộ `~/.m2/repository`.

### Mục tiêu

Sau bài, bạn có thể:

1. Phân biệt **Maven core/API realm**, **plugin realm**, **build-extension realm** và **project compile/runtime/test classpath**.
2. Giải thích vì sao `<project><dependencies>` không tự cấp JAR cho plugin.
3. Giải thích vì sao `<plugin><dependencies>` không tự cấp JAR cho ứng dụng khi chạy ngoài Maven.
4. Nhận diện `NoClassDefFoundError`, `ClassNotFoundException`, `NoSuchMethodError`, `ClassCastException`, `ServiceConfigurationError` và `UnsupportedClassVersionError`.
5. Dùng `mvn -e -X`, `help:effective-pom`, `dependency:tree` và class origin để khoanh vùng.
6. Thực hành một project Maven Java17/JUnit5 có **hai phiên bản Commons Lang ở hai graph khác nhau**.
7. Chủ động tạo lỗi thiếu class rồi sửa bằng đúng cấu hình Exec Maven Plugin.
8. Phân biệt `exec:java` với `exec:exec` và `java -jar` của thin JAR.
9. Chứng minh **cùng tên class nhưng defining classloader khác** có thể tạo hai Java types khác nhau.
10. Biết khi nào sửa plugin dependency, project dependency, annotation processor path hoặc launcher/runtime packaging.
11. Thiết kế checklist CI để tái hiện lỗi, giữ exit code và bảo vệ debug logs.

Demo ghim **Maven 3.9.x**, **Java 17+**, Maven Compiler Plugin **3.14.1**, Surefire **3.5.4**, JAR Plugin **3.4.2**, Dependency Plugin **3.10.0**, Exec Maven Plugin **3.6.4**, Commons Lang **3.17.0** (project), **3.12.0** (plugin) và JUnit Jupiter **5.11.4**. Những versions này dùng cho việc học, không phải khuyến nghị bỏ qua bản vá bảo mật trong production.

---

## 2. Cách Maven tải class: các không gian khác nhau

~~~text
JVM chạy Maven
  |
  +-- Maven core / exported API realm
  |      Maven APIs, container và lifecycle infrastructure
  |
  +-- Build extensions (nếu được khai)
  |      Extension realm(s) và API packages được export
  |
  +-- Plugin realm: maven-compiler-plugin
  |      Compiler plugin + plugin dependencies
  |
  +-- Plugin realm: exec-maven-plugin
  |      Exec plugin + plugin dependencies
  |      KHÔNG tự có target/classes hoặc project dependency JARs
  |
  +-- Project classpaths được Maven xác định
         compile: classes + compile/provided dependencies
         runtime: classes + compile/runtime dependencies
         test: test-classes + classes + test dependencies
~~~

Maven dùng **Plexus Classworlds** để tổ chức các realms. Sơ đồ trên thể hiện ranh giới logic; parent/import rules có chi tiết tùy loại realm/Maven version. Maven **project classloader** hỗ trợ build extensions, không được nhầm với **project compile/runtime/test classpath**.

### 2.1. Maven core/API

Maven core cung cấp API và build infrastructure. Plugin sử dụng các Maven APIs được export vào realm theo cơ chế Maven. Thêm một JAR vào project không có nghĩa Maven core tự thay thư viện nội bộ của nó bằng version đó.

### 2.2. Plugin class realm

Plugin realm thường chứa:

- JAR của plugin được Maven resolve.
- Dependencies của plugin trong chính plugin POM.
- Dependencies bổ sung từ `<build><plugins><plugin><dependencies>`.
- Maven API exports được cho phép.

**Điểm chính thức trong Apache Maven Guide to Maven Classloading:** plugin realm **không chứa project dependencies hay compiled main/test classes theo mặc định**. Plugin nào thật sự cần project runtime classes phải truy xuất classpath từ MavenProject hoặc API phù hợp rồi **tạo/điều khiển loader hoặc process riêng**.

### 2.3. Compile/runtime/test classpaths của project

Project dependencies phục vụ code đang được compile, tests hoặc application runtime. Maven Compiler Plugin có thể nhận project compile classpath dù **Compiler Plugin realm** bản thân vẫn là một không gian riêng.

### 2.4. Một JVM có thể có nhiều loaders

Maven plugin chạy trong Maven process nhưng không có nghĩa mọi plugin nạp cùng một phiên bản class. `exec:java` còn tạo classloader để thực thi App ngay trong Maven JVM. `exec:exec` có thể khởi chạy Java process khác; `java -jar` từ terminal cũng là JVM riêng. Hãy xác định lệnh nào thực thi code đang fail.

---

## 3. Khai dependency ở đâu mới đúng?

### 3.1. Dependency của ứng dụng

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.17.0</version>
    </dependency>
</dependencies>
~~~

Thư viện Commons Lang được Maven chọn cho **project graph**. Java source của ứng dụng có thể import `org.apache.commons.lang3.StringUtils`.

### 3.2. Dependency của một plugin

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.codehaus.mojo</groupId>
            <artifactId>exec-maven-plugin</artifactId>
            <version>3.6.4</version>
            <dependencies>
                <dependency>
                    <groupId>org.apache.commons</groupId>
                    <artifactId>commons-lang3</artifactId>
                    <version>3.12.0</version>
                </dependency>
            </dependencies>
        </plugin>
    </plugins>
</build>
~~~

Đây là dependency thuộc **plugin graph**. Nó không tự xuất hiện trong compiled App JAR và không thay `commons-lang3:3.17.0` trên project compile classpath.

### 3.3. Hai versions ở hai realm không nhất thiết là lỗi

~~~text
Project:     commons-lang3:3.17.0
Exec plugin: commons-lang3:3.12.0
~~~

Lỗi chỉ xuất hiện khi **classloader đang chạy code** nhận version sai API, thiếu class hoặc có class identity crossing boundary không đúng.

### 3.4. dependencyManagement và pluginManagement

`dependencyManagement` quản lý dependency versions trong project model; nó không tự đưa mọi dependency được quản lý vào plugin realm.

`pluginManagement` giúp quản lý plugin versions/configuration, nhưng plugin chưa chắc chạy goal nếu chỉ được liệt kê ở đó. Khi debug, xem **effective POM của module hỏng**, không chỉ root POM. Child/module có thể override plugin dependencies hay configuration.

---

## 4. Đọc đúng loại lỗi

| Lỗi/triệu chứng | Hướng điều tra | Điều không được suy ra |
| --- | --- | --- |
| `ClassNotFoundException` | ClassLoader/reflection tìm tên class không được | Chưa kết luận dependency version sai |
| `NoClassDefFoundError` | JVM cần định nghĩa/liên kết class nhưng không resolve được | Có thể thiếu transitive JAR hoặc static init lỗi trước |
| `NoSuchMethodError` | Đã load class nhưng thiếu method descriptor | Thường là binary ABI/version mismatch |
| `NoSuchFieldError` | Runtime class thiếu field bytecode gọi tới | Không đơn thuần thiếu class file |
| `AbstractMethodError` | Interface/implementation không compatible | Có thể version skew |
| `IllegalAccessError` | Linkage bị chặn vì access flags | Không phải luôn JDK module opens |
| `ClassCastException` | Object không phải type đang được loader kỳ vọng | Có thể cùng FQCN nhưng defining loaders khác |
| `ServiceConfigurationError` | ServiceLoader/provider/resources/type không khớp | Cần kiểm TCCL và service descriptor |
| `UnsupportedClassVersionError` | Class file được compile cho Java version mới hơn JVM đang chạy | Không tự sửa bằng project release flag |
| `InaccessibleObjectException` | Reflection/module encapsulation | Khác với class không tồn tại |
| `PluginResolutionException` | Không tải/resolve được plugin artifact | Chưa phải lỗi Mojo classloading |
| `PluginContainerException` | Plugin/Mojo không khởi chạy do API/class issue | Đọc nguyên nhân gốc và realm |

### 4.1. Lỗi static initialization

~~~text
NoClassDefFoundError: Could not initialize class ...
~~~

có thể xuất hiện sau `ExceptionInInitializerError`. File class vẫn có, nhưng JVM đã đánh dấu lỗi khởi tạo. Tìm **nguyên nhân đầu tiên** trong logs.

### 4.2. Binary method signature

`NoSuchMethodError` có thể liên quan tên, danh sách tham số và return type trong JVM descriptor. Đừng chỉ tra source version hiện tại rồi kết luận runtime class chắc có method đó.

### 4.3. Không gộp lỗi plugin với lỗi ứng dụng

Một `NoClassDefFoundError` bên trong Mojo khởi chạy là vấn đề plugin realm/loader của plugin. Một `NoClassDefFoundError` từ Java `main` khi `java -jar` là vấn đề application runtime. Tên ngoại lệ giống nhau **không** nói lên nơi sửa đúng.

---

## 5. Quy trình chẩn đoán trước khi thay POM

1. **Ghi lệnh fail**: `mvn compile`, `mvn verify`, `mvn exec:java`, `java -jar` hay test fork?
2. **Xác định stacktrace**: phần `Caused by`, missing FQCN/method/field, tên Mojo/main/test class.
3. **Ghi Maven/JDK versions**: `mvn -version`, `java -version`.
4. **Đọc plugin realm**: `mvn -e -X` khi lỗi ở goal/plugin.
5. **Xem effective POM** của đúng module và dependency scopes.
6. **Tìm class source/loader** bằng `CodeSource`, `getClassLoader`, `jar tf` và `javap`.
7. **Sửa đúng graph** rồi rerun goal lỗi và full Maven verify/test suite.

### 5.1. Maven debug

~~~bash
mvn -e -X clean verify
~~~

Hoặc chính goal đang fail:

~~~bash
mvn -e -X exec:java
~~~

Log Maven có thể có dạng:

~~~text
[DEBUG] Created new class realm plugin>org.codehaus.mojo:exec-maven-plugin:3.6.4
[DEBUG] Populating class realm ...
[DEBUG] Included: org.apache.commons:commons-lang3:jar:3.12.0
~~~

**Dòng log là minh họa định dạng, không phải output chính xác của mọi Maven version.** Hãy đọc các JAR versions được nạp và realm identity thực.

`-e` bật stacktraces; `-X` bật debug logging. `-q` giảm log và không phù hợp để tìm lỗi tải lớp khó. Debug logs có thể chứa repository URLs/secret-bearing configuration, nên chỉ chia sẻ sau khi kiểm thông tin nhạy cảm.

### 5.2. Effective POM

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

Tìm **hai nhánh khác nhau**: top-level `dependencies` và `build/plugins/plugin/dependencies`. Xem cả plugin `version`, `configuration`, profiles và child overrides.

### 5.3. Dependency tree của project

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
~~~

Hoặc lọc:

~~~bash
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Lệnh này không in toàn bộ JARs của plugin realm; nó là **project dependency graph**.

### 5.4. Project classpath

~~~bash
mvn dependency:build-classpath -Dmdep.outputFile=target/project-classpath.txt
~~~

File chứa dependency classpath của project theo goal/options. Đừng dùng nó như bằng chứng chắc chắn plugin realm có cùng JARs.

### 5.5. Exec goal help

~~~bash
mvn org.codehaus.mojo:exec-maven-plugin:3.6.4:help -Ddetail=true -Dgoal=java
~~~

Cho phép kiểm parameters chính thức của plugin: `includeProjectDependencies`, `includePluginDependencies`, `classpathScope` và `addOutputToClasspath`.

---

## 6. Demo Maven Java17 chạy được với hai versions Commons Lang

Dự án một module, gồm đúng **3 file**:

~~~text
maven-realm-boundary-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/realm/App.java
    └── test/java/vn/example/realm/AppTest.java
~~~

Mục đích: project dùng Commons Lang **3.17.0**, Exec Plugin có dependency riêng Commons Lang **3.12.0**. Sau đó ta thay đổi classpath do `exec:java` tạo.

**Phân biệt cẩn thận:** `exec:java` có chức năng tạo loader để chạy App trong Maven JVM. Nó không chứng minh các plugins bình thường tự nạp project classes vào plugin realm; chúng vẫn tách biệt.

### 6.1. pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>maven-realm-boundary-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.includeProjectDependencies>true</demo.includeProjectDependencies>
        <demo.includePluginDependencies>false</demo.includePluginDependencies>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
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
                            <mainClass>vn.example.realm.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.10.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
                <configuration>
                    <mainClass>vn.example.realm.App</mainClass>
                    <classpathScope>runtime</classpathScope>
                    <includeProjectDependencies>${demo.includeProjectDependencies}</includeProjectDependencies>
                    <includePluginDependencies>${demo.includePluginDependencies}</includePluginDependencies>
                    <addOutputToClasspath>true</addOutputToClasspath>
                </configuration>
                <dependencies>
                    <dependency>
                        <groupId>org.apache.commons</groupId>
                        <artifactId>commons-lang3</artifactId>
                        <version>3.12.0</version>
                    </dependency>
                </dependencies>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- `commons-lang3:3.17.0` trong top-level `<dependencies>` phục vụ project compile/test/runtime.
- `commons-lang3:3.12.0` dưới Exec `<plugin><dependencies>` phục vụ plugin graph.
- `demo.includeProjectDependencies` / `demo.includePluginDependencies` được POM dùng để tạo effective goal config, nên có thể chuyển mode bằng CLI `-Ddemo...`.
- `addOutputToClasspath=true` cho phép `target/classes` được cấp cho application loader ngay cả khi tắt project **dependency JARs**.
- `classpathScope=runtime` dùng compile/runtime project dependencies khi bật.
- Có hai versions ở hai places là **thí nghiệm cố ý**, không phải đề nghị sao chép nguyên cho production.

### 6.2. App.java

File `src/main/java/vn/example/realm/App.java`:

~~~java
package vn.example.realm;

import java.net.URL;
import java.security.CodeSource;
import java.security.ProtectionDomain;
import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String normalize(String input) {
        return StringUtils.capitalize(StringUtils.trimToEmpty(input));
    }

    public static String libraryOrigin() {
        ProtectionDomain domain = StringUtils.class.getProtectionDomain();
        CodeSource source = domain == null ? null : domain.getCodeSource();
        URL url = source == null ? null : source.getLocation();
        return url == null ? "unknown" : url.toExternalForm();
    }

    public static void main(String[] args) {
        System.out.println("APP_RESULT=" + normalize("  maven  "));
        System.out.println("LANG_ORIGIN=" + libraryOrigin());
    }
}
~~~

Khi class Commons Lang phù hợp được loader cung cấp, **dòng output đầu tiên chính xác**:

~~~text
APP_RESULT=Maven
~~~

Dòng thứ hai có prefix `LANG_ORIGIN=` và một URL/path tùy máy, ví dụ tham khảo:

~~~text
LANG_ORIGIN=file:/.../commons-lang3/3.17.0/commons-lang3-3.17.0.jar
~~~

Đây **không phải** stdout tuyệt đối cố định. Nếu không có CodeSource, App in `LANG_ORIGIN=unknown`. CodeSource giúp đối chiếu JAR thực; không dùng path tuyệt đối làm giá trị assert cho unit tests.

### 6.3. AppTest.java

File `src/test/java/vn/example/realm/AppTest.java`:

~~~java
package vn.example.realm;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void normalizesInput() {
        assertEquals("Maven", App.normalize("  maven  "));
    }

    @Test
    void treatsNullAsEmpty() {
        assertEquals("", App.normalize(null));
    }
}
~~~

Có đúng **hai** JUnit5 tests. Chúng chạy bằng project test classpath và không dựa vào plugin-level version 3.12.0.

---

## 7. Chạy baseline và xem origin

Tại root project:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Nếu Maven/JDK, mạng/repositories và source phù hợp, kết quả dự kiến:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **kỳ vọng từ source/POM demo**, không phải khẳng định tác giả đã chạy Maven thực tế.

Sau build:

~~~bash
mvn -q exec:java
~~~

Kỳ vọng dòng đầu:

~~~text
APP_RESULT=Maven
~~~

Kiểm dòng `LANG_ORIGIN`. Thông thường nó chỉ project Commons Lang 3.17.0. Nếu khác, đọc effective POM, project classpath và loader configuration thực.

### 7.1. Lưu ý về goal độc lập

`mvn exec:java` không tự đảm bảo compile project trước mỗi lần gọi. Trên checkout sạch chưa có `target/classes`, có thể gặp lỗi không tìm main class. Dùng:

~~~bash
mvn -B -ntp compile exec:java
~~~

hoặc `clean verify` trước. Đây là **timing/build output issue**, không nên chữa bằng cách nhét `src/main/java` vào plugin realm.

---

## 8. Tạo lỗi thiếu class một cách có chủ đích

Sau `mvn clean verify`, chạy:

~~~bash
mvn -e \
  "-Ddemo.includeProjectDependencies=false" \
  "-Ddemo.includePluginDependencies=false" \
  exec:java
~~~

POM vẫn có `addOutputToClasspath=true` nên loader chạy App thấy `target/classes`. Nhưng nó không được cấp project hoặc plugin dependency JARs; khi gọi `StringUtils`, Maven goal dự kiến thất bại với nested cause tương tự:

~~~text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
~~~

Maven/Exec Plugin có thể wrap exception và thay đổi lời báo trên console, nên **không coi mẫu này là exact full log**.

### 8.1. Đây là lỗi loader nào?

**Application execution classloader do Exec Plugin tạo**, không phải chứng cứ Exec Mojo tự không tải được vào **plugin realm**. Cùng exception class có thể đến từ hai loaders khác nhau. Đây là lý do phải biết nơi code đang fail.

### 8.2. Tại sao thêm Commons Lang vào project không sửa?

Project đã có dependency. Nhưng config `includeProjectDependencies=false` cố ý loại project dependency JARs khỏi application execution loader. Tăng version hoặc xóa cache không thay ý nghĩa cờ false.

### 8.3. Phục hồi bằng đúng cờ

~~~bash
mvn -q \
  "-Ddemo.includeProjectDependencies=true" \
  "-Ddemo.includePluginDependencies=false" \
  exec:java
~~~

Dòng đầu trở lại:

~~~text
APP_RESULT=Maven
~~~

---

## 9. Chạy bằng plugin dependencies: xem ranh giới

Thử chỉ bật plugin dependencies:

~~~bash
mvn -q \
  "-Ddemo.includeProjectDependencies=false" \
  "-Ddemo.includePluginDependencies=true" \
  exec:java
~~~

Với plugin graph đã khai Commons Lang 3.12.0 và các API StringUtils của demo có trong version đó, ứng dụng có thể in:

~~~text
APP_RESULT=Maven
LANG_ORIGIN=file:/.../commons-lang3/3.12.0/commons-lang3-3.12.0.jar
~~~

Dòng `LANG_ORIGIN` chỉ là **đường dẫn minh họa**; bắt buộc xem output thật vì dependency mediation, loader/classpath ordering và repo paths có thể khác.

### 9.1. Vì sao không nên dùng plugin library làm runtime library?

Khi bạn chạy App bằng Java launcher ngoài Maven, dependency của Exec Plugin không tự xuất hiện. Một ứng dụng cần runtime library phải được khai và phân phối theo **project runtime dependencies**. Đừng giữ chế độ plugin-only làm “fix” production.

### 9.2. Bật cả hai có thể tạo duplicate classes

~~~bash
mvn -q \
  "-Ddemo.includeProjectDependencies=true" \
  "-Ddemo.includePluginDependencies=true" \
  exec:java
~~~

Giờ loader chạy App có thể có hai JAR versions chứa cùng class names. **Đừng đoán version nào thắng** từ thứ tự POM. Đọc origin thực, effective flags và classpath order, rồi cố gắng chỉ dùng một version tương thích trong một loader thực thi.

---

## 10. Thin JAR và lỗi java -jar không phải plugin realm

POM demo dùng Maven JAR Plugin tạo thin JAR, **không nhúng** Commons Lang classes. Lệnh:

~~~bash
java -jar target/maven-realm-boundary-demo-1.0.0.jar
~~~

có thể lỗi `NoClassDefFoundError` vì Java launcher không biết local Maven dependency repository.

Đây là **application runtime classpath issue**, không phải Maven Plugin Realm. `Main-Class` trong manifest giúp tìm entry point nhưng không mang theo transitively tất cả libraries.

Bash/Linux/macOS, nếu Maven repo ở mặc định:

~~~bash
java -cp \
  "target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.17.0/commons-lang3-3.17.0.jar" \
  vn.example.realm.App
~~~

Dòng đầu:

~~~text
APP_RESULT=Maven
~~~

Cần thay path nếu dùng custom Maven local repo. Windows dùng `;` thay `:`. Các hướng triển khai đúng gồm thin JAR + `lib` launcher, Shade/Assembly distribution, hoặc Spring Boot executable JAR khi dùng framework đó.

**Không copy toàn bộ Maven plugin dependencies vào application runtime** chỉ để chữa lỗi `java -jar`.

---

## 11. Đo defining loader và CodeSource

Snippet Java dùng gần vị trí lỗi:

~~~java
Class<?> type = org.apache.commons.lang3.StringUtils.class;
System.out.println("name=" + type.getName());
System.out.println("loader=" + type.getClassLoader());

java.security.ProtectionDomain domain = type.getProtectionDomain();
java.security.CodeSource source =
        domain == null ? null : domain.getCodeSource();
System.out.println("origin=" +
        (source == null ? "unknown" : source.getLocation()));
~~~

Đây là **snippet**, không phải file standalone: nó cần Commons Lang compile dependency. Đặt ở App nếu App lỗi, đặt ở plugin nếu Mojo lỗi. Log nguồn class ở App **không** tự chứng minh plugin realm dùng cùng JAR.

### 11.1. Loader và TCCL có thể khác

~~~java
Thread.currentThread().getContextClassLoader()
~~~

là **thread context classloader (TCCL)**. Frameworks như ServiceLoader có thể dựa vào TCCL. Defining loader của `SomeClass.class` có thể khác TCCL. Khi một plugin tạm đổi TCCL, phải lưu/restore trong `finally`, tránh ảnh hưởng các executions khác.

### 11.2. CodeSource không phải luôn có

`ProtectionDomain.CodeSource` có thể null với loader riêng; `App.libraryOrigin()` chủ động in `unknown` trong trường hợp ấy. Không cast mọi loader thành URLClassLoader: Maven Classworlds và Java 9+ có loader implementations khác.

### 11.3. Bootstrap loader

`String.class.getClassLoader()` có thể null vì class được bootstrap loader định nghĩa; không phải thiếu class.

---

## 12. Demo Java 17 thuần: cùng tên class, hai Java types

Tạo một thư mục riêng:

~~~text
loader-identity-demo/
└── src/vn/example/identity/
    ├── Token.java
    └── LoaderIdentityDemo.java
~~~

### 12.1. Token.java

~~~java
package vn.example.identity;

public final class Token {
    public Token() {
    }
}
~~~

### 12.2. LoaderIdentityDemo.java

~~~java
package vn.example.identity;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderIdentityDemo {
    private LoaderIdentityDemo() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Expected directory with compiled Token.class"
            );
        }

        Path path = Path.of(args[0]).toAbsolutePath();
        URL url = path.toUri().toURL();

        try (URLClassLoader first =
                     new URLClassLoader(new URL[] {url}, null);
             URLClassLoader second =
                     new URLClassLoader(new URL[] {url}, null)) {

            String name = "vn.example.identity.Token";
            Class<?> a = Class.forName(name, true, first);
            Class<?> b = Class.forName(name, true, second);
            Object valueA = a.getDeclaredConstructor().newInstance();

            System.out.println("sameName="
                    + a.getName().equals(b.getName()));
            System.out.println("sameClass=" + (a == b));
            System.out.println("compatible=" + b.isInstance(valueA));
        }
    }
}
~~~

### 12.3. javac và java

Đứng tại root `loader-identity-demo`:

~~~bash
javac -d isolated-classes src/vn/example/identity/Token.java
javac -d launch-classes src/vn/example/identity/LoaderIdentityDemo.java
java -cp launch-classes vn.example.identity.LoaderIdentityDemo isolated-classes
~~~

**Stdout chính xác:**

~~~text
sameName=true
sameClass=false
compatible=false
~~~

Hai URLClassLoaders có parent `null` và tự define Token từ cùng file bytecode. Vì vậy class names bằng nhau nhưng Java types khác. Nếu plugin/project loaders mỗi bên định nghĩa một shared API type riêng, truyền object qua boundary có thể dẫn tới `ClassCastException`.

**Lưu ý:** Maven có cơ chế imports/delegation; không mặc định mọi Maven plugin sẽ nhân đôi class này. Thí nghiệm chỉ chứng minh quy tắc **defining loader là một phần của type identity**.

---

## 13. Chẩn đoán NoSuchMethodError bằng class origin và javap

Khi plugin code được compile against library version mới nhưng realm thực tế dùng bản cũ, bytecode gọi method không tồn tại trong runtime class:

~~~text
java.lang.NoSuchMethodError: ...
~~~

Tìm đúng ba yếu tố:

1. **Ai gọi method?** Mojo, test, application hay processor?
2. **Class đang nạp từ đâu?** JAR URL/CodeSource, plugin `-X` realm.
3. **Binary descriptor có gì?** Dùng `javap` trên đúng JAR.

Commands minh họa:

~~~bash
jar tf path/to/library.jar
javap -classpath path/to/library.jar -public com.example.Library
javap -classpath path/to/library.jar -s com.example.Library
~~~

Thay placeholder paths/class bằng artifact thật. `javap -s` cho thấy descriptors để tìm overload/return types không khớp.

Nếu lỗi nằm trong **plugin realm**, có thể nâng plugin compatible hoặc thêm library dưới `<plugin><dependencies>` khi plugin hỗ trợ cách override. Nếu lỗi nằm trong **App runtime**, sửa project dependency/launcher. Đừng ép Maven core nạp version của project bằng cách sửa global CLASSPATH.

---

## 14. ServiceLoader và Java module/resource visibility

`java.util.ServiceLoader` và frameworks tương tự dùng `META-INF/services` để tìm providers. Một provider có mặt trong JAR nhưng không được loader đang tìm kiếm nhìn thấy, hoặc provider/interface bị định nghĩa ở hai loaders khác nhau, có thể gây:

~~~text
java.util.ServiceConfigurationError:
  java.some.Service: Provider vn.example.Provider not found
~~~

Khi gặp lỗi:

- Kiểm service interface loader.
- Kiểm provider class loader/CodeSource.
- Kiểm `META-INF/services/<service-interface>` nằm đúng JAR.
- Kiểm provider transitive dependencies.
- Kiểm TCCL và realm imports.
- Kiểm Shade Plugin có relocate class nhưng quên transform service resources không.

Không chuyển mọi libraries vào plugin realm chỉ để ServiceLoader tìm thấy. Thiết kế **shared API type boundary** và cấu hình loader/service discovery chính xác.

---

## 15. Annotation processor không giống application runtime

Maven Compiler Plugin có thể dùng **annotation processor path** riêng, ví dụ `annotationProcessorPaths`. Khi processor code thiếu helper class, sửa **processor dependencies/path** có thể cần thiết; thêm helper vào application runtime dependencies chưa chắc giúp.

Kiểm:

- Compiler plugin version/config và processor discovery.
- Processor artifact + transitive dependencies.
- JDK/compiler version.
- Processor path, generated sources và phase timing.

Cùng quy tắc áp dụng cho Surefire test provider classpath, Failsafe integration tests và những plugins có custom runtime loaders: **mỗi bên có scope/loader được thiết kế riêng**.

---

## 16. Viết Maven plugin riêng: requiresDependencyResolution

Một Mojo muốn đọc project runtime dependency graph có thể khai:

~~~java
@org.apache.maven.plugins.annotations.Mojo(
    name = "inspect",
    requiresDependencyResolution =
        org.apache.maven.plugins.annotations.ResolutionScope.RUNTIME
)
public final class InspectMojo
        extends org.apache.maven.plugin.AbstractMojo {

    @Override
    public void execute()
            throws org.apache.maven.plugin.MojoExecutionException {
        getLog().info("Inspect goal running");
    }
}
~~~

**Chỉ là snippet minh họa.** Để build một Maven plugin thực cần `packaging=maven-plugin`, Maven Plugin Plugin tạo descriptor và plugin API/annotations dependencies. Đoạn trên chưa tải project class nào.

`requiresDependencyResolution=RUNTIME` yêu cầu Maven resolve project runtime dependencies để Mojo có thể **truy cập project classpath** từ MavenProject/các API; nó không tự trộn các JAR đó vào plugin realm. Nếu cần chạy project classes, plugin author phải tạo controlled classloader hoặc process, khôi phục TCCL và đóng resources đúng lifecycle.

Không nạp và chạy static initializers của code không tin cậy nếu tác vụ chỉ cần inspect bytecode.

---

## 17. Shade/relocation và API boundary

Khi plugin cần implementation library riêng và có nguy cơ trùng class names với APIs dùng chung, plugin author có thể **shade/relocate** một phần implementation dependency sang namespace riêng:

~~~text
com.vendor.internal.Helper
    -> vn.example.plugin.shaded.com.vendor.internal.Helper
~~~

Điều này không phải cách chữa tất cả xung đột. ServiceLoader descriptors, reflection và resources có thể cần transformer. **Không relocate Maven core API hay shared interfaces bừa**, vì class identity mà framework mong đợi có thể bị phá.

Phân biệt:

- Plugin-level dependency: thêm thư viện để **Mojo** dùng.
- Project-level dependency: thêm thư viện để **App** compile/run.
- Annotation processor path: classpath cho processors.
- Custom loader/launcher: thực thi project code theo mục đích.
- Shade/relocate: thay package của implementation dependency trong một artifact có quản lý.

---

## 18. Maven local repository không phá ranh giới realm

Xóa `~/.m2/repository` không làm plugin tự có project dependencies. Nếu POM/config vẫn sai, Maven thường tải lại đúng plugin/JARs cũ và lỗi lặp lại.

Chỉ cân nhắc cache refresh khi có bằng chứng artifact corrupted, `.lastUpdated` do download fail, SNAPSHOT cũ, local `mvn install` artifact sai hoặc mirror metadata bất thường.

Thử repository sandbox:

~~~bash
mvn -B -ntp "-Dmaven.repo.local=.m2-diagnostic/repository" clean verify
~~~

Nếu fresh repository build pass, điều tra cache/origin; nếu cả hai fail cùng plugin classloading cause, sửa POM/plugin design.

`mvn -U` yêu cầu Maven kiểm updated snapshots/missing releases theo update policy, **không** tự sửa plugin realm.

---

## 19. Multi-module/CI/IDE: tránh chẩn đoán nhầm

Một reactor có thể gồm module custom plugin và module App. Nếu App gọi plugin chưa được resolve/không có plugin descriptor, lỗi có thể là `PluginResolutionException` hoặc `NoPluginFoundForPrefixException` — **khác** với `NoClassDefFoundError` khi Mojo đã chạy.

Khi nghi plugin prefix resolution:

~~~bash
mvn org.codehaus.mojo:exec-maven-plugin:3.6.4:java
~~~

Lệnh fully qualified chỉ định đúng plugin GAV/goal, không chữa mọi lỗi loader.

Maven Wrapper, IDE bundled Maven và CI runner có thể sử dụng JDK/Maven khác nhau. Plugin version không được pin, `settings.xml`/mirrors khác, active profiles hoặc module selection khác cũng làm kết quả lệch.

Thu thập:

~~~bash
mvn -version
java -version
mvn help:effective-pom
mvn dependency:tree
mvn -e -X exec:java
~~~

Đọc đúng **goal, Maven/JDK versions, module và profiles**. Đừng so IDE chỉ chạy compile với CI chạy verify + codegen rồi kết luận chúng đã test cùng classloader.

### 19.1. Không che exit code trong CI

Bash:

~~~bash
set -o pipefail
mvn -e -X exec:java | tee build-debug.log
status=$?
exit "$status"
~~~

Nếu bỏ `pipefail`, có thể nhận exit code của `tee` chứ không phải Maven. Đừng dùng `-fn` hoặc `|| true` làm release quality gate. Khi lưu debug logs, nhớ kiểm secrets/URLs/config.

---

## 20. Troubleshooting nhanh

| Hiện tượng | Nơi kiểm đầu tiên | Cách xử lý |
| --- | --- | --- |
| Mojo thiếu Helper | Plugin realm dump, plugin deps | Pin compatible plugin/dependency version |
| Project compiler thiếu StringUtils | Project compile deps | Add project dependency đúng scope |
| App thiếu StringUtils khi exec:java | Exec flags và runtime classpath | Include project deps, compile trước |
| App thiếu StringUtils khi java -jar | Thin JAR launcher | Package runtime libs/launcher |
| Plugin NoSuchMethodError | Version thực trong plugin realm | Inspect method signature, align plugin |
| Unit test CNFE | Surefire/JUnit test classpath | Test deps/provider/fork config |
| Annotation processor NCDFE | Processor path | Fix processor dependencies |
| Token không cast sang Token | Defining loaders khác | Shared API boundary/loader strategy |
| ServiceLoader provider not found | TCCL, service file, provider deps | Align resource/type visibility |
| UnsupportedClassVersionError | Java chạy Maven quá cũ | Compatible JDK/plugin |
| PluginResolutionException | Maven repo/plugin artifact | Fix coordinates/settings/credentials |
| IDE pass, CI fail | JDK/Maven/plugin/profile drift | Align environments and logs |
| Xóa cache vẫn lỗi | Class realm separation không đổi | Fix đúng dependency graph/config |

---

## 21. Bài tập

**Bài 1.** Tại sao project dependency Commons Lang 3.17.0 không làm Exec Plugin realm tự dùng version đó?

**Bài 2.** Tạo đúng ba file demo, chạy `mvn clean verify`, kiểm hai JUnit tests và `mvn -q exec:java`. Dòng output đầu tiên là gì?

**Bài 3.** Dựa trên `LANG_ORIGIN`, phân biệt nguồn class ở project-only mode với plugin-only mode.

**Bài 4.** Tắt cả `demo.includeProjectDependencies` và `demo.includePluginDependencies`. Vì sao App class có thể được tìm thấy nhưng `StringUtils` không?

**Bài 5.** Khôi phục project=true/plugin=false. Vì sao cách này tốt hơn việc nâng version hoặc xóa cache trong thí nghiệm?

**Bài 6.** Bật project=false/plugin=true. Tại sao App có thể dùng plugin dependency nhưng không nên triển khai production theo cách đó?

**Bài 7.** Bật cả hai true. Cần kiểm gì trước khi kết luận version nào của Commons Lang được nạp?

**Bài 8.** Chạy `java -jar` với thin JAR. Vì sao runtime không tự biết Maven local repository?

**Bài 9.** Dùng `mvn -e -X`, tìm plugin realm và kiểm realm dependencies. Tại sao `dependency:tree` project không thay được bước này?

**Bài 10.** Một plugin gọi method của Guava 32.x nhưng realm chứa bản cũ. Chẩn đoán và hướng sửa đúng ở đâu?

**Bài 11.** Chạy demo hai `URLClassLoader`. Giải thích `sameName=true` nhưng `sameClass=false`.

**Bài 12.** Một provider được ServiceLoader tìm thấy nhưng không cast được sang interface. Vai trò defining loaders và TCCL là gì?

**Bài 13.** Compiler annotation processor thiếu Helper; vì sao chỉ thêm application runtime dependency có thể không sửa được?

**Bài 14.** Plugin build bằng JDK21 chạy trong Maven JDK17. `maven.compiler.release=17` của ứng dụng có sửa `UnsupportedClassVersionError` không?

**Bài 15.** Một plugin Mojo cần project runtime classes. Vì sao `requiresDependencyResolution=RUNTIME` chưa tự đưa chúng vào realm, cần bước nào tiếp?

**Bài 16.** CI lỗi plugin, IDE không. Liệt kê Maven/JDK/plugin/settings/profile differences cần kiểm.

**Bài 17.** Một cache JAR bị hỏng, khi nào thử local repository sandbox hoặc targeted purge? Vì sao không nên xóa toàn bộ repository?

**Bài 18.** Thiết kế script CI giữ đúng exit code Maven và lưu debug logs đã redact secrets để chẩn đoán.

---

## 22. Checklist áp dụng

- [ ] Biết lỗi xảy ra trong Mojo, compiler, test JVM hay App runtime.
- [ ] Đọc được root cause và binary FQCN/method signature.
- [ ] Ghim Maven/JDK/plugin versions.
- [ ] Xem `-e/-X` và đúng plugin realm khi Mojo lỗi.
- [ ] Tách project dependencies và plugin dependencies trong effective POM.
- [ ] Không coi project dependency:tree là plugin realm dump.
- [ ] Đo class origin/defining loader khi có thể.
- [ ] Hiểu Exec goal include flags và `addOutputToClasspath`.
- [ ] Phân biệt `exec:java` với `exec:exec` và `java -jar`.
- [ ] Kiểm scopes và phase/`target/classes` trước khi chạy main.
- [ ] Nếu lỗi processor/test, sửa đúng processor/test path.
- [ ] Nếu class identity conflict, tìm shared API boundary.
- [ ] Không dùng global CLASSPATH hoặc sửa Maven home/lib làm workaround.
- [ ] Không xóa cả ~/.m2 nếu chưa có evidence cache hỏng.
- [ ] Không chia sẻ Maven -X logs có credentials.
- [ ] Rerun đúng goal và full `mvn verify` sau khi sửa.
- [ ] CI phải báo fail thật khi classpath/ABI conflict vẫn tồn tại.

**Kết luận:** **Plugin class realm và classpath ứng dụng là hai phạm vi tải lớp khác nhau**. Project dependency giúp App compile/run; plugin dependency phục vụ Mojo. `NoClassDefFoundError`, `NoSuchMethodError` hay `ClassCastException` phải được phân tích từ đúng process, loader, JAR nguồn và exception cause. Sửa **đúng graph/configuration** giúp giải quyết lỗi mà không làm hỏng Maven core hoặc đưa library thừa vào sản phẩm.

## 23. Nguồn tham khảo chính thức

- [Apache Maven — Guide to Maven Classloading](https://maven.apache.org/guides/mini/guide-maven-classloading.html): plugin realm, project classpath, classloader graph.
- [Apache Maven — Maven 3.x Class Loading](https://cwiki.apache.org/confluence/spaces/MAVEN/pages/3475335/Maven+3.x+Class+Loading): realms trong Maven 3.
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): plugin dependencies và versions.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scopes, mediation, transitive dependencies.
- [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html): includeProjectDependencies, includePluginDependencies, classpathScope, addOutputToClasspath.
- [MojoHaus Exec Maven Plugin — exec:exec](https://www.mojohaus.org/exec-maven-plugin/exec-mojo.html): external process execution.
- [MojoHaus Exec Maven Plugin — Plugin Info](https://www.mojohaus.org/exec-maven-plugin/plugin-info.html): requirements/goal versions.
- [Apache Maven Dependency Plugin — tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): resolved project graph.
- [Apache Maven Dependency Plugin — build-classpath](https://maven.apache.org/plugins/maven-dependency-plugin/build-classpath-mojo.html): project classpath.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): effective plugin config.
- [Apache Maven — Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development.html): Mojo.
- [Maven Surefire — Class Loading and Forking](https://maven.apache.org/surefire/maven-surefire-plugin/examples/class-loading.html): test classloader.
- [Java 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader/type identity.
- [Java 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): custom loader.
