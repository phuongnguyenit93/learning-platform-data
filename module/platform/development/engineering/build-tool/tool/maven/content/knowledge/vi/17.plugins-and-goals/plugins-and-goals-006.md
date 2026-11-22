# Cố định phiên bản Maven Plugin để kiểm soát thay đổi build

## 1. Tại sao phải cố định phiên bản plugin?

Trong Maven, **plugin** là thành phần thực thi các tác vụ của quá trình build: xóa output cũ, copy resources, biên dịch Java, chạy test, đóng gói JAR, tạo báo cáo, cài artifact vào local repository hoặc triển khai lên remote repository. Mỗi plugin có các **goal**; Maven gọi goal theo dòng lệnh trực tiếp hoặc thông qua **lifecycle phase**.

Ví dụ:

```bash
mvn clean verify
```

Một build Java kiểu `jar` thường liên quan đến nhiều plugin: Maven Clean Plugin, Resources Plugin, Compiler Plugin, Surefire Plugin, JAR Plugin... Nếu nhóm không chốt phiên bản plugin, cùng POM có thể sử dụng plugin version khác khi Maven runtime, metadata hoặc cấu hình phân giải thay đổi. Điều này có thể kéo theo thay đổi:

- Mặc định của một plugin: cách phát hiện unit test, các tham số compiler, kiểu xử lý resource, nội dung manifest hoặc báo cáo.
- Khả năng tương thích JDK/Maven: phiên bản plugin mới có thể yêu cầu runtime tối thiểu khác.
- Hành vi lỗi: bản plugin mới có thể kiểm tra chặt hơn, bỏ một tùy chọn đã deprecated hoặc thay đổi cách báo lỗi.
- Artifact đầu ra: cùng source code có thể tạo JAR hoặc báo cáo khác ở các máy/CI.
- An toàn vận hành: plugin có thể đọc file, chạy lệnh, tải artifact hoặc triển khai bản phát hành; không nên để phiên bản thay đổi ngoài quy trình review.

**Cố định phiên bản plugin (plugin version pinning)** nghĩa là dự án chọn **phiên bản cụ thể, có thể kiểm chứng** của những plugin mà build sử dụng, ghi nhận lựa chọn trong POM/parent POM và chỉ nâng cấp qua một thay đổi có chủ đích.

Theo hướng dẫn chính thức của Apache Maven, các plugin nên có `groupId`, `artifactId` và `version`; Maven khuyến nghị quản lý version build plugins trong `<build><pluginManagement>`, thường đặt tại parent POM.

Pinning **không tự bảo đảm kết quả build giống byte tuyệt đối**: còn cần kiểm soát Maven/JDK version, plugin configuration, dependency, profile, encoding, thời gian build, môi trường, nguồn repository và tính ổn định của plugin. Nhưng nó loại bỏ một biến quan trọng mà dự án hoàn toàn có thể quản lý.

## 2. Ba thành phần dễ nhầm: Maven, plugin và dependency

| Thành phần | Ví dụ | Chức năng | Cách kiểm soát |
| --- | --- | --- | --- |
| Maven runtime | Maven 3.9.x | Đọc POM, tạo project model, điều phối lifecycle/Reactor, chạy plugin | Dùng Maven Wrapper hoặc yêu cầu phiên bản Maven được duyệt |
| Build plugin | `maven-compiler-plugin:3.13.0` | Chạy goal `compile`/`testCompile` và các tác vụ liên quan | Pin `<version>` trong `<build><plugins>` hoặc `<pluginManagement>` |
| Project dependency | `junit-jupiter:5.10.2` | Cấp thư viện cho compile/runtime/test classpath | Pin `<dependencies>`/`<dependencyManagement>` |
| Plugin dependency | Artifact trong `<plugin><dependencies>` | Cấp thư viện cho chính plugin ở plugin realm | Kiểm tra cấu hình plugin và các version phụ thuộc liên quan |
| Reporting plugin | `maven-javadoc-plugin` khi dùng cho site report | Tạo báo cáo dự án | Pin version trong `<reporting><plugins>`; quản lý riêng nếu gọi như build plugin |

**Không nhầm hai kiểu version:**

- `<dependencies><dependency><version>...` quyết định **version thư viện của project**; nó không pin version của Maven Compiler Plugin.
- `<build><plugins><plugin><version>...` hoặc `<build><pluginManagement>` quyết định **version build plugin**; nó không tự nâng cấp JUnit/Jackson/Commons Lang trong classpath của ứng dụng.

Tương tự, Maven Wrapper chỉ chốt **bản phân phối Maven** khi chạy bằng script Wrapper; nó **không thay thế** việc pin version plugin được thực thi bởi Maven đó.

## 3. Plugin goal khác lifecycle phase

Maven cung cấp các phase như `validate`, `compile`, `test`, `package` và `verify`. Khi người dùng gọi phase, Maven sẽ chạy những goal đã được **gắn** (*bound*) vào các phase trong lifecycle của project, bao gồm các binding mặc định theo `packaging` và những execution do POM bổ sung.

```text
mvn verify              → chạy lifecycle tới phase verify
mvn compiler:compile    → gọi goal compile qua tiền tố plugin compiler
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile
                        → gọi đích danh goal compile với plugin version 3.13.0
```

Ba lệnh này **không tương đương**:

- `verify` chạy chuỗi phase và các goal tương ứng; có thể gồm resources, compile, test, package...
- `compiler:compile` trực tiếp gọi một goal; không tự bảo đảm đã chạy mọi phase cần thiết trước đó.
- Tọa độ đầy đủ nêu rõ version cho **lời gọi plugin cụ thể**. Các plugin khác trong build vẫn phải được quản lý bằng cách riêng.

Ví dụ khi module có `packaging=jar`, goal của Compiler Plugin và Surefire Plugin thường đã được Maven lifecycle gắn vào phase mặc định. Nếu parent POM quản lý version Compiler Plugin, Maven có thể dùng version đó cho goal compile được lifecycle gọi, dù con không cần tự thêm một execution mới.

**`pluginManagement` không tự kích hoạt một goal tùy ý.** Quản lý version của một plugin là một việc; bảo Maven chạy goal đó ở phase nào là một việc khác.

## 4. Pin plugin trong POM: hai vị trí dùng đúng mục đích

### 4.1. `<build><plugins>` — khai báo plugin được project sử dụng

Ví dụ một project khai báo trực tiếp Maven Compiler Plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn POM**, cần đặt trong `<project>` hợp lệ. Plugin có tọa độ `org.apache.maven.plugins:maven-compiler-plugin:3.13.0`. Module dùng cùng version khi Maven thực thi plugin trong các ngữ cảnh áp dụng.

Ưu điểm của `<build><plugins>` là dễ thấy plugin nào đang được project cấu hình và execution nào đang dùng. Hạn chế là nếu có nhiều module và mỗi module copy/paste một version, việc nâng cấp dễ bị lệch.

### 4.2. `<build><pluginManagement>` — quản lý version và cấu hình tập trung

Ví dụ parent POM:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Với module khai báo `<parent>` trỏ tới parent này, version/configuration được **quản lý** cho plugin tương ứng theo quy tắc Maven. Nếu module cần thêm cấu hình Surefire:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <failIfNoTests>true</failIfNoTests>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Module **không cần lặp lại `<version>3.2.5</version>`** nếu version đã được quản lý ở parent. Maven kết hợp khai báo với quản lý version/configuration theo mô hình hiệu lực.

Các điểm cần nhớ:

- Một mục trong `pluginManagement` là **chính sách cho plugin khi nó được sử dụng**, không tự ràng buộc mọi goal tùy ý vào build.
- Đối với plugin **đã được lifecycle mặc định gọi**, quản lý version có thể áp dụng mà module không cần khai báo lại plugin trong `<plugins>` chỉ để chạy goal mặc định.
- Đối với plugin **không có binding mặc định**, project muốn chạy một goal ở phase cụ thể cần khai báo `<build><plugins>` và `<executions>` phù hợp, hoặc gọi trực tiếp trên CLI.
- Parent POM chỉ cung cấp chính sách này cho những project **thật sự kế thừa** parent qua `<parent>`. Việc root liệt kê một module bằng `<modules>` không tự tạo quan hệ kế thừa.

### 4.3. Không đưa plugin version vào dependencyManagement

Đoạn sau **không phải** cách quản lý build plugin:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

`dependencyManagement` quản lý **dependency của project**, không phải version plugin mà Maven chọn để thực thi compile. Đặt GAV plugin ở đây không giải quyết mục tiêu pinning build plugin, lại dễ gây hiểu nhầm về project classpath.

## 5. Những plugin nào cần pin trong một build Java thông thường?

Với project `jar`, nên kiểm kê cả plugin **hiện rõ trong `<build><plugins>`** và plugin **được lifecycle mặc định gọi**. Ví dụ danh mục để review:

| Plugin | Goal/phase điển hình | Tại sao version thay đổi có thể đáng chú ý |
| --- | --- | --- |
| Maven Clean Plugin | `clean:clean` khi chạy `mvn clean` | Cách xóa output và một số tùy chọn xử lý file |
| Maven Resources Plugin | `resources:resources` ở `process-resources`; `testResources` | Encoding, filtering, copy tài nguyên |
| Maven Compiler Plugin | `compiler:compile`, `compiler:testCompile` | Java release, compiler options, incremental compilation |
| Maven Surefire Plugin | `surefire:test` ở `test` | Phát hiện/chạy test, JUnit Platform, fork và report |
| Maven JAR Plugin | `jar:jar` ở `package` cho `jar` | Manifest, metadata và cấu trúc JAR |
| Maven Install Plugin | `install:install` ở `install` | Cài artifact vào local repository |
| Maven Deploy Plugin | `deploy:deploy` ở `deploy` | Publish artifact lên remote repository |
| Maven Failsafe Plugin | `integration-test`/`verify` khi đã cấu hình | Phát hiện/chạy và kiểm tra kết quả integration test |
| Maven Dependency Plugin | `dependency:tree`, `copy-dependencies`... | Phân tích graph và thao tác artifact |
| Maven Shade Plugin / Assembly Plugin | Goal đóng gói khi dự án khai báo | Fat JAR, relocate, file layout |
| Maven Enforcer Plugin | `enforce` theo execution POM | Chính sách kiểm tra dependency/plugin/JDK |
| Reporting plugins | Goals sinh site/report | Định dạng và nội dung báo cáo |

Đây là **checklist theo nhu cầu**, không có nghĩa mọi project phải cài tất cả plugin. Ví dụ nếu project không bao giờ gọi `deploy` thì việc pin Maven Deploy Plugin chưa phải phần cốt lõi của bài demo `verify`; nhưng **trước khi đưa `deploy` vào CI**, cần chốt và kiểm chứng plugin version tương ứng.

Các version trong ví dụ dưới đây là **mốc đã được chọn để minh họa**, không tự nhận là bản mới nhất. Khi nâng cấp thực tế, phải đánh giá compatibility với JDK/Maven, security advisory và nhu cầu dự án.

## 6. Ví dụ hoàn chỉnh Java 17 + JUnit 5: parent POM quản lý plugin version

Ta xây một repository Maven hai cấp: root parent/aggregator và module `app`. Dự án **pin những plugin được dùng trong `clean verify`**, dùng JDK 17, JUnit Jupiter 5.10.2 và kiểm tra bằng lệnh Maven/Java.

Điều kiện: đã cài JDK 17+; Maven tương thích; được phép tải plugin/JUnit từ repository hợp lệ. Có thể thay `mvn` bằng Maven Wrapper tương ứng nếu project đã có Wrapper được kiểm chứng.

### 6.1. Cây thư mục

```text
pinned-plugin-demo/
├── pom.xml
└── app/
    ├── pom.xml
    └── src/
        ├── main/java/edu/demo/app/PinnedApp.java
        └── test/java/edu/demo/app/PinnedAppTest.java
```

### 6.2. Root pom.xml — nơi quản lý tập trung phiên bản plugin

Tệp `pinned-plugin-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>pinned-plugin-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.10.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-clean-plugin</artifactId>
                    <version>3.3.2</version>
                </plugin>
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
                    <version>3.2.5</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-dependency-plugin</artifactId>
                    <version>3.6.1</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Mục tiêu của POM này:

- `<modules>` cho Maven Reactor biết module `app` cần được thu thập khi chạy từ root.
- `<dependencyManagement>` quản lý version JUnit, **khác** khu vực quản lý plugin.
- `<pluginManagement>` pin version một số plugin lifecycle cho build `clean verify`, và pin Dependency Plugin để dùng khi phân tích.
- `maven.compiler.release=17` đặt ngôn ngữ/bytecode mục tiêu cho compiler plugin, không tự cài JDK 17.

Vì root `packaging=pom`, nó không tự biên dịch lớp Java thành JAR ứng dụng. Module `app` sẽ sử dụng POM cha để nhận chính sách version và được Maven xây thành JAR thông thường.

### 6.3. app/pom.xml — module kế thừa version nhưng chỉ kích hoạt plugin cần thiết

Tệp `pinned-plugin-demo/app/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>edu.demo</groupId>
        <artifactId>pinned-plugin-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`app` khai báo JUnit test dependency nhưng **không cần tự ghi version 5.10.2**, vì version lấy từ `dependencyManagement` của parent. `maven-surefire-plugin` được cấu hình `failIfNoTests=true` và cũng **không cần lặp version** vì `pluginManagement` của parent đã pin `3.2.5`.

Các plugin khác như Resources, Compiler và JAR Plugin được lifecycle của project `jar` gọi theo binding mặc định phù hợp. Parent quản lý version của chúng để tránh để version do Maven/Super POM hoặc metadata quyết định ngoài chủ đích.

**Quan trọng:** không suy ra việc khai báo Dependency Plugin ở `pluginManagement` tự chạy `dependency:tree` ở mỗi build. Nó chỉ được dùng khi goal được gọi hoặc gắn execution thông qua `plugins` ở đúng phase.

### 6.4. Mã Java 17 sản phẩm

Tệp `pinned-plugin-demo/app/src/main/java/edu/demo/app/PinnedApp.java`:

```java
package edu.demo.app;

public final class PinnedApp {
    private PinnedApp() {
    }

    public static String message(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is blank");
        }
        return "Build pinned: " + name.strip();
    }

    public static void main(String[] args) {
        System.out.println(message("Maven"));
    }
}
```

`String.isBlank()` và `String.strip()` có trong Java 11 trở lên, vì vậy mã hợp lệ với Java 17. Chương trình không dùng thư viện runtime bên ngoài, giúp kiểm tra việc Maven biên dịch và đóng gói mà không cần bổ sung classpath JAR cho `java` ở bước chạy.

### 6.5. Test JUnit Jupiter

Tệp `pinned-plugin-demo/app/src/test/java/edu/demo/app/PinnedAppTest.java`:

```java
package edu.demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PinnedAppTest {

    @Test
    void formatsMessage() {
        assertEquals("Build pinned: Maven", PinnedApp.message(" Maven "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                     () -> PinnedApp.message("   "));
    }
}
```

File này dùng JUnit Jupiter 5.10.2 (qua `dependencyManagement`) và Surefire Plugin 3.2.5 (qua `pluginManagement`). Nếu bỏ JUnit dependency nhưng chỉ để JUnit trong management, test không có JUnit trên test classpath và không thể compile.

### 6.6. Build toàn Reactor và kiểm tra kết quả

Tại thư mục `pinned-plugin-demo/`:

```bash
mvn -version
mvn -B clean verify
```

Nếu Maven/JDK/repository phù hợp:

1. Maven Clean Plugin phiên bản được quản lý xóa output ở `target` cho lượt build này.
2. Resources Plugin xử lý tài nguyên theo lifecycle; module không có resource riêng thì plugin có thể báo không có gì để copy.
3. Compiler Plugin biên dịch `PinnedApp.java` ở Java release 17.
4. Compiler Plugin biên dịch `PinnedAppTest.java` trong test sources.
5. Surefire Plugin chạy **2 test, 0 failures, 0 errors**, nếu không có cờ skip/profile thay đổi.
6. JAR Plugin tạo `app/target/app-1.0.0.jar` cho module.

Để xác minh test thực sự chạy, kiểm tra báo cáo:

```text
app/target/surefire-reports/
```

Không chỉ đọc dòng `BUILD SUCCESS`: nếu test bị bỏ qua, build có thể xanh nhưng mục tiêu kiểm thử không được chứng minh. Thuộc tính `failIfNoTests=true` trong app giúp phát hiện tình huống plugin không tìm thấy test; nó **không** thay thế việc xem report khi có cờ skip hoặc cấu hình khác.

Chạy chương trình trên Linux/macOS từ root:

```bash
java -cp app/target/classes edu.demo.app.PinnedApp
```

Với class được biên dịch như mã mẫu, **stdout của riêng lệnh Java này** là:

```text
Build pinned: Maven
```

Trên Windows PowerShell có thể gọi cùng classpath tương đối bằng:

```powershell
java -cp app\target\classes edu.demo.app.PinnedApp
```

JAR của app là **JAR thường**, chưa cấu hình manifest `Main-Class`, nên không mặc định chạy được với `java -jar app/target/app-1.0.0.jar`. Điều đó độc lập với việc plugin version đã được pin.

## 7. Kiểm tra phiên bản plugin thực sự được Maven chọn

### 7.1. Đọc output của build

Khi thực thi `mvn -B clean verify`, Maven thông thường in tên/plugin version ở đầu từng goal. Một số thông tin cần quan sát:

```text
maven-clean-plugin:3.3.2:clean
maven-resources-plugin:3.3.1:resources
maven-compiler-plugin:3.13.0:compile
maven-compiler-plugin:3.13.0:testCompile
maven-surefire-plugin:3.2.5:test
maven-jar-plugin:3.4.2:jar
```

Đây là **danh sách các plugin/goal và version kỳ vọng**, không phải log Maven được chép nguyên từng dòng. Output thật còn có execution id, artifactId, thứ tự lifecycle, project root và các goal khác. Nếu Maven in version khác, phải điều tra vì sao cấu hình quản lý version không được áp dụng cho project đang xét.

### 7.2. Xem effective POM

Maven Help Plugin có goal `effective-pom` để xem cấu hình sau khi kết hợp Super POM, parent, profile và POM con. Có thể gọi với version Help Plugin cụ thể:

```bash
mvn -B -pl :app org.apache.maven.plugins:maven-help-plugin:3.4.0:effective-pom -Doutput=target/effective-pom.xml
```

Với goal và output path tương đối, kiểm tra vị trí file **theo basedir của project app**. Mục đích là xem các mục `pluginManagement` được kế thừa, khai báo `plugins` hiệu lực và version plugin mà model công bố.

Khi cần đọc trực tiếp trên console:

```bash
mvn -B -pl :app org.apache.maven.plugins:maven-help-plugin:3.4.0:effective-pom
```

Chú ý: **effective POM không phải log thực thi mọi goal**. Nó cho biết cấu hình hiệu lực, còn bằng chứng goal nào **thực sự chạy** đến từ log build và báo cáo/test/artifact. Khi kiểm tra một plugin được gọi trực tiếp trên CLI bằng tọa độ đầy đủ, version trên CLI là một đầu vào riêng cần được ghi nhận.

### 7.3. Dùng plugin version cố định cho công cụ chẩn đoán

Trong ví dụ, muốn phân tích dependency graph một cách nhất quán:

```bash
mvn -B -pl :app org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Tọa độ đầy đủ `org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree` pin version cho **goal được gọi ở CLI**, không cần dựa vào prefix metadata để chọn version.

Nếu chỉ gọi:

```bash
mvn dependency:tree
```

Maven cần giải quyết prefix/plugin/version theo POM hiệu lực và cơ chế phân giải phù hợp. Khi parent quản lý Dependency Plugin, version quản lý thường là đầu vào cho việc chọn plugin nếu plugin được áp dụng đúng ngữ cảnh; nhưng **dùng tọa độ đầy đủ có version rõ ràng nhất trong script cần kiểm chứng độc lập**.

Không ghép nhiều giá trị vào một `<version>` theo kiểu `LATEST` hoặc `RELEASE` để “luôn mới nhất”. Cần dùng một release version cụ thể đã được review.

## 8. Parent POM và Reactor: quản lý tập trung không phụ thuộc vào vị trí module

Một cấu trúc nhiều module thường trông như:

```text
workspace/
├── pom.xml              parent + aggregator (có thể cùng file)
├── api/pom.xml
├── service/pom.xml
└── cli/pom.xml
```

Root có thể vừa là **parent** chứa `pluginManagement` vừa là **aggregator** chứa `modules`. Nhưng hai cơ chế độc lập:

- POM của `service` khai báo `<parent>...` mới nhận các version plugin quản lý từ parent.
- Root khai báo `<module>service</module>` chỉ đưa project vào Maven Reactor để build cùng lượt; không tự làm service kế thừa cấu hình.
- Nếu `cli` có parent khác, cần đặt/chia sẻ pluginManagement qua đúng chuỗi parent của `cli` hoặc pin riêng; chỉ vì cùng root aggregator không có nghĩa mọi module dùng cùng compiler plugin version.

Khi nâng plugin version tại parent, mọi module kế thừa và thực sự sử dụng plugin đó có thể bị ảnh hưởng. Hãy chạy test cho các module tương ứng, không chỉ chạy một module dễ nhất.

Một version trong parent `pluginManagement` có thể bị **ghi đè** bởi khai báo version cụ thể ở `<build><plugins>` của POM con, hoặc bị ảnh hưởng cấu hình/profile có hiệu lực. Vì vậy phải kiểm tra effective POM **từng module quan trọng** trước khi khẳng định toàn bộ Reactor dùng cùng version.

## 9. Pin version không tự kích hoạt plugin: một ví dụ goal tùy chỉnh

Giả sử một project muốn chạy Maven Dependency Plugin để sao chép runtime libraries vào thư mục phân phối. Parent chỉ có:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-dependency-plugin</artifactId>
            <version>3.6.1</version>
        </plugin>
    </plugins>
</pluginManagement>
```

Khai báo này **không tự làm `copy-dependencies` chạy ở mọi lần `mvn package`**. Module muốn goal đó tự chạy trong một phase phải khai báo execution:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-dependency-plugin</artifactId>
            <executions>
                <execution>
                    <id>copy-runtime-jars</id>
                    <phase>prepare-package</phase>
                    <goals>
                        <goal>copy-dependencies</goal>
                    </goals>
                    <configuration>
                        <includeScope>runtime</includeScope>
                        <outputDirectory>${project.build.directory}/lib</outputDirectory>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn POM bổ sung cho một module** có parent đang quản lý version Dependency Plugin 3.6.1. Execution được gắn vào `prepare-package`, nên Maven chạy goal đó khi lifecycle đi qua phase ấy.

Trong Maven Dependency Plugin, `includeScope=runtime` lọc các dependency phù hợp cho runtime, gồm những dependency có scope compile/runtime theo ngữ nghĩa goal. Nó **không** copy các dependency chỉ có scope test vào thư mục runtime này.

Phân biệt rõ ba câu hỏi:

1. **Plugin version nào?** Parent quản lý `3.6.1`.
2. **Goal nào chạy?** `copy-dependencies` trong execution.
3. **Khi nào chạy?** Phase `prepare-package` do `<phase>` quy định.

Đừng nhầm việc pin version với việc tự tạo execution. Đồng thời, plugin mặc định được lifecycle gắn sẽ hoạt động theo quy tắc riêng của packaging, không cần project tự tạo execution trùng lặp.

## 10. CLI đầy đủ và prefix: tránh version ngoài ý muốn trong script

Maven hỗ trợ gọi plugin bằng tiền tố ngắn:

```bash
mvn dependency:tree
mvn compiler:help -Ddetail
```

Trong nhiều trường hợp, Maven giải quyết group/artifact/version qua cấu hình project, plugin groups và metadata repository. Nếu phụ thuộc vào metadata chọn plugin version hoặc cấu hình trên từng máy, script có thể thiếu tính rõ ràng.

Cách gọi có version:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:help -Ddetail
```

**Pin version trên CLI** hữu ích cho một lần chạy công cụ chẩn đoán hoặc script đặc thù. Nhưng không nên thay thế hoàn toàn `pluginManagement` bằng việc viết hàng chục tọa độ plugin trong mọi job CI: lifecycle vẫn có nhiều goal được gắn tự động, và người dùng IDE có thể chạy `mvn verify` mà không truyền toàn bộ các version vào lệnh.

Thực tế nên kết hợp:

- **POM/parent:** pin version của mọi plugin thực sự tham gia lifecycle build và các plugin custom được sử dụng.
- **CLI:** dùng tọa độ đầy đủ có version khi gọi plugin trực tiếp độc lập với version của POM, nhất là khi chẩn đoán hay nâng cấp.
- **Maven Wrapper/JDK:** chốt môi trường công cụ theo tiêu chuẩn nhóm.
- **CI:** chạy những phase được duyệt và ghi nhận chính xác command/plugin versions trong log.

## 11. Phân biệt pin plugin version với reporting plugins

Maven có **build plugins** trong `<build>` và **reporting plugins** trong `<reporting>`, được dùng khi tạo site/báo cáo theo cơ chế phù hợp.

Ví dụ một report plugin:

```xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.7.0</version>
        </plugin>
    </plugins>
</reporting>
```

Đây là đoạn POM minh họa cho dự án có nhu cầu báo cáo Javadoc, không phải phần bắt buộc của ví dụ Java chạy được bên trên.

Theo Apache Maven, reporting plugin nên có version trong `<reporting><plugins>`; khi cùng plugin cũng được dùng như build plugin, quản lý version tương ứng trong `<build><pluginManagement>` là thực hành phù hợp. **Không giả định** pin một plugin trong `<reporting>` sẽ tự động pin mọi lần goal đó được gọi trực tiếp trong build lifecycle theo cách riêng.

Nếu CI chỉ chạy `mvn clean verify` mà không chạy site/reporting, đừng khẳng định report đã được tạo. Cần phân biệt tập plugin thực sự chạy với tập được khai báo để sử dụng về sau.

## 12. Thêm Maven Enforcer để ngăn plugin thiếu version

Để biến khuyến nghị thành một kiểm tra tự động, có thể dùng **Maven Enforcer Plugin** với rule `requirePluginVersions`. Rule này yêu cầu plugin có version được định nghĩa trong chính POM hoặc trong `pluginManagement` của POM/parent theo ngữ nghĩa rule, và có các lựa chọn cấm `LATEST`, `RELEASE` hoặc snapshot plugin.

Ví dụ **đoạn plugin** bổ sung vào `<build><plugins>` tại POM muốn kiểm tra:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.4.1</version>
    <executions>
        <execution>
            <id>check-plugin-versions</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requirePluginVersions>
                        <banLatest>true</banLatest>
                        <banRelease>true</banRelease>
                        <banSnapshots>true</banSnapshots>
                        <banMavenDefaults>true</banMavenDefaults>
                    </requirePluginVersions>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn cấu hình nâng cao**, không được gắn mặc định vào POM runnable ở phần 6. Với `banMavenDefaults=true`, rule có thể yêu cầu project kiểm soát thêm plugin version từ default lifecycle bindings, kể cả những plugin bạn chưa gọi tới trong `clean verify`. Vì vậy phải kiểm kê và pin đầy đủ theo policy trước khi bật chốt kiểm soát này trong CI.

Tài liệu rule nêu những tùy chọn quan trọng:

| Tham số | Ý nghĩa |
| --- | --- |
| `banLatest` | Chặn dùng version `LATEST` cho plugin |
| `banRelease` | Chặn dùng version `RELEASE` cho plugin |
| `banSnapshots` | Chặn snapshot plugin theo quy tắc của rule |
| `banMavenDefaults` | Khi true, không xem version từ Super POM/default lifecycle như thay thế cho khai báo version thuộc project/parent |
| `banTimestamps` | Kiểm soát timestamped snapshots trong các điều kiện được rule hỗ trợ |

Một phương án chuyển đổi là tạm để `banMavenDefaults=false` để chấp nhận một số version mặc định của Maven trong lúc rà soát; nhưng đây là **nới lỏng** chính sách, không đạt mức tự kiểm soát toàn bộ plugin version như `true`.

**Enforcer không thay thế test.** Rule có thể phát hiện plugin chưa pin hoặc version format vi phạm policy, nhưng không bảo đảm một plugin version đã pin là tương thích, an toàn hay tạo artifact đúng yêu cầu sản phẩm.

## 13. Không dùng các version động cho plugin quan trọng

Ví dụ cần tránh:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>LATEST</version>
</plugin>
```

Version động như `LATEST` hoặc `RELEASE` là lựa chọn không phù hợp cho build cần tái lập; một plugin version mới có thể được chọn ở lần chạy khác dù POM không thay đổi. Maven/Enforcer cũng có thể từ chối hoặc cảnh báo một số kiểu version không được khuyến khích này.

Tránh tiếp tục bằng:

```xml
<version>3.2-SNAPSHOT</version>
```

khi mục tiêu là release build ổn định. Snapshot plugin có thể thay đổi nội dung với cùng base version, phụ thuộc metadata và update policy; đây là điểm rủi ro tương tự dependency snapshot.

Một plugin version đã pin cũng cần được **phân giải từ repository được kiểm soát và đáng tin**. Nếu repository cho phép overwrite artifact đã release dưới cùng tọa độ, pin GAV một mình chưa chứng minh byte đã bất biến. Với yêu cầu audit cao, ghi nhận checksums, provenance, artifact manifest/SBOM và policy repository.

## 14. Nâng cấp plugin có kiểm soát thay vì giữ mãi một bản

Pinning không có nghĩa **không bao giờ nâng version**. Nó có nghĩa mọi lần nâng cấp là **thay đổi có review**, có thể rollback và xác minh hồi quy.

Một quy trình nâng cấp an toàn:

1. **Kiểm kê plugin đang dùng** từ root/parent và các module: cả lifecycle-bound plugins, custom executions, reporting plugins và plugin được gọi trực tiếp trong CI.
2. **Ghi baseline** Maven/JDK version, effective POM và log goal/version thực tế.
3. **Đọc changelog của phiên bản đích**: phiên bản Maven/JDK tối thiểu, tham số bị thay đổi, hành vi mặc định, lỗi đã sửa và cảnh báo tương thích.
4. **Thay version trong một nguồn quản lý chính** (thường parent `pluginManagement`), hạn chế phân tán version trùng lặp.
5. **Kiểm tra cấu hình plugin**: flag, parameter name, execution id, phase binding, default behavior, dependencies của plugin khi cần.
6. **Chạy build sạch** `mvn -B clean verify` và xem báo cáo test thật, không chỉ dòng `BUILD SUCCESS`.
7. **Kiểm tra artifact đầu ra**: class file target release, JAR manifest, resource filtering, Surefire/Failsafe reports, binary compatibility theo nhu cầu.
8. **Chạy trên CI môi trường chuẩn**: cùng Wrapper/JDK, không dựa vào plugin cached chỉ có trên laptop.
9. **Ghi kết quả trong PR**: plugin GAV trước/sau, lý do nâng, ảnh hưởng, test đã chạy và cách rollback.
10. **Sau khi merge**: theo dõi pipeline/phát hành để phát hiện lỗi chỉ xuất hiện ở packaging, deployment hoặc runtime.

Ví dụ sửa:

```xml
<!-- Before -->
<version>3.2.5</version>

<!-- After: release version mới đã được kiểm tra -->
<version>3.5.3</version>
```

Đây chỉ là **đoạn minh họa thay version của một plugin đã được xác định**; không phải chỉ dẫn thay mọi `<version>` trong POM bằng 3.5.3. Trước khi dùng bản mới, xem tài liệu của chính plugin và yêu cầu Maven/JDK của phiên bản đó.

Có thể dùng **Maven Versions Plugin** để hỗ trợ phát hiện bản cập nhật plugin, nhưng công cụ báo có bản mới **không tự chứng minh nên nâng ngay**. Bản nâng cần qua review và test; nếu gọi Versions Plugin trực tiếp trên CLI, nên chọn version của Versions Plugin rõ ràng thay vì dùng prefix không kiểm soát trong quy trình quan trọng.

## 15. Vì sao đã pin plugin nhưng build vẫn khác nhau?

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| Local dùng Surefire version đúng, CI dùng bản khác | CI chạy khác POM/parent, khác profile, version bị override ở module | Effective POM của module + log goal/version CI |
| `pluginManagement` có plugin nhưng goal không chạy | Plugin không có binding mặc định và chưa khai báo execution | Kiểm tra `<build><plugins><executions>` hoặc lệnh CLI |
| Parent pin version nhưng một module vẫn dùng bản khác | Module không kế thừa đúng parent hoặc có `<version>` ghi đè | `<parent>`, effective POM của module |
| Test chạy khác sau nâng Surefire | Thay đổi provider, fork, phát hiện test hoặc cấu hình | Surefire changelog, plugin version và report |
| Compiler pin rồi vẫn compile Java release khác | `JAVA_HOME`/Toolchains, `maven.compiler.release` hoặc profile khác | `mvn -version`, effective POM, target bytecode |
| CI dùng plugin mới dù POM không đổi | Maven/runtime khác, plugin invocation không có version, repository metadata thay đổi | Wrapper/version, CLI GAV, effective POM và log |
| Plugin download lỗi | Repository/mirror/proxy, pluginRepositories hoặc quyền credential | Effective settings, pluginRepositories, HTTP status |
| Build xanh nhưng không có test | Cờ skip, không tìm test, profile/Surefire config | Surefire reports, `failIfNoTests` |
| Dependency đúng version nhưng JAR khác | Plugin dùng packaging, shading/repackaging khác hoặc thời điểm build | Artifact manifest, checksums, plugin config và logs |
| Enforcer yêu cầu thêm plugin version | `banMavenDefaults=true` hoặc plugin lifecycle chưa được khai báo trong project | Danh sách plugin rule nêu, pin ở parent |
| Pin plugin đầy đủ mà build không tái lập byte | Timestamp, thứ tự entry, filesystem, encoding, nondeterminism | Cấu hình reproducible builds và so artifact/checksum |
| Chỉ lỗi khi `mvn site` hoặc `deploy` | Các plugin đó không nằm trong tập plugin `verify` đã review | Pin và test plugin reporting/deploy cho phase tương ứng |
| Maven Wrapper đổi nhưng plugin version không đổi | Maven runtime mới có khác biệt nội bộ; plugin API cần tương thích | Matrix Maven/Java/plugin và test trên CI |
| Plugin version được pin nhưng bị thay artifact ở repository | Release artifact bị overwrite hoặc kho không tin cậy | Checksum/provenance và policy bất biến repository |

### 15.1. Phân biệt lỗi dependency và lỗi plugin

Nếu log có `Plugin ... could not be resolved`, Maven không tải được **build plugin hoặc thành phần của plugin**. Cần xem `pluginRepositories`, mirror, credentials và version được khai báo.

Nếu log có `Could not resolve dependencies for project ...`, vấn đề thường thuộc **project dependency graph**. Nó có thể gián tiếp làm một goal plugin thất bại, nhưng không phải bằng chứng version plugin thiếu pin. Đọc nguyên nhân gốc thay vì thay plugin version tùy tiện.

### 15.2. Không dùng `-U` như chiến lược quản lý version

`mvn -U` yêu cầu Maven kiểm tra cập nhật snapshot/missing releases theo cơ chế phù hợp; nó không thay đổi `<version>` trong POM và không bảo đảm tự chọn plugin release mới nhất.

Ngược lại, nếu plugin không pin và được phân giải qua repository metadata, chính sách cập nhật/cache có thể ảnh hưởng lựa chọn phiên bản trên từng máy. Cách giải quyết chính là pin GAV và quản lý nguồn artifact, **không phải chỉ thêm `-U` hoặc xóa local repository mỗi khi CI khác kết quả**.

## 16. Checklist triển khai trên một dự án thật

- [ ] Đã liệt kê các plugin thực sự chạy ở `clean`, `compile`, `test`, `package`, `verify` và các phase `install`/`deploy`/`site` nếu có?
- [ ] Mỗi build plugin quan trọng có **version release cụ thể** được khai báo trong `plugins` hoặc `pluginManagement` từ project/parent?
- [ ] Các module kế thừa parent đúng và không override plugin version ngoài ý muốn?
- [ ] Đã phân biệt **pluginManagement quản lý version** với **plugins/executions kích hoạt goal**?
- [ ] Những plugin được gọi trực tiếp trong CI có tọa độ/version rõ ràng?
- [ ] Reporting plugins và plugin phục vụ các stage CI khác đã được pin riêng khi dùng?
- [ ] Maven Wrapper và JDK phù hợp đã được chốt, không giả định Wrapper pin luôn plugin?
- [ ] Có chính sách về `LATEST`, `RELEASE`, snapshot plugin và repository bất biến?
- [ ] Build sạch và unit/integration test liên quan được chạy thật, không bị skip?
- [ ] Effective POM và log build chứng minh plugin version đúng ở **từng module quan trọng**?
- [ ] Artifact đầu ra được kiểm tra sau nâng plugin (JAR, manifest, classpath, reports)?
- [ ] Có quy trình review, kiểm thử, rollback và theo dõi cập nhật bảo mật của plugin?

**Kết luận:** để kiểm soát thay đổi build trong Maven, hãy pin version plugin bằng tọa độ rõ ràng, ưu tiên quản lý tập trung ở `<build><pluginManagement>` của parent cho dự án nhiều module, khai báo execution khi cần chạy goal tùy chỉnh và kiểm tra hiệu lực qua **effective POM, log goal/version, test report và artifact đầu ra**. Pinning tạo nền tảng cho khả năng tái lập nhưng phải đi cùng Maven Wrapper, JDK, repository policy và quy trình nâng cấp có kiểm chứng.

### Tài liệu chính thức

- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to the POM, Plugin Management](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Enforcer Built-In Rules — requirePluginVersions](https://maven.apache.org/enforcer/enforcer-rules/requirePluginVersions.html)
- [Apache Maven Surefire Plugin — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
