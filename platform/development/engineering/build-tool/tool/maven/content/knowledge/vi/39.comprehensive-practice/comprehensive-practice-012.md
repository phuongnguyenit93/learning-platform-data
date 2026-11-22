# Tự đọc một dự án Maven chưa quen bằng POM và các lệnh trợ giúp

## 1. Mục tiêu của bài thực hành tổng hợp

Bạn vừa nhận một repository Java/Maven không có người bàn giao. Trước khi sửa lỗi, nâng thư viện hoặc chạy CI, hãy trả lời: **project tạo artifact gì, bao nhiêu module, quan hệ phụ thuộc ra sao, parent và BOM quản lý điều gì, plugins nào thực sự chạy, profile nào active, Java/Maven nào cần thiết, và lệnh nào kiểm chứng được điều gì?**

Một repository có thể `BUILD SUCCESS` ở module A trong khi unit tests của module B chưa được chạy. Tương tự, không thấy version trong child `<dependency>` chưa chắc POM lỗi vì parent `dependencyManagement` có thể cung cấp version.

Bài học đi theo thứ tự **đọc cấu hình tĩnh → hiểu effective model → kiểm tra graph → chạy lifecycle trong môi trường an toàn → đối chiếu reports → viết báo cáo hiểu dự án**.

Sau khi hoàn thành, bạn có thể:
- Đọc root/child POM, phân biệt aggregator với parent, GAV và `packaging`.
- Đọc đúng `properties`, `dependencies`, `dependencyManagement`, `plugins`, `pluginManagement`, `profiles`, `repositories`, `pluginRepositories`, `distributionManagement`.
- Sử dụng Maven Help Plugin: `active-profiles`, `all-profiles`, `effective-pom`, `effective-settings`, `evaluate`, `describe`.
- Sử dụng Maven Dependency Plugin: `dependency:tree`, trực tiếp/bắc cầu, scopes và quản lý versions.
- Hiểu `-pl`, `-am`, `-amd`, `-f`, `-N` và build một phần.
- Xây project **Java 17** gồm **3 child modules/6 unit tests**, một application có stdout chính xác.
- Tạo hồ sơ dự án: **known from files / observed from Maven / not verified**.

### 1.1. Quy tắc an toàn khi nghiên cứu một repository chưa tin cậy

Không tự chạy `mvn install`, `mvn deploy`, `mvn verify` hoặc thậm chí `mvn validate` trước khi xem `pom.xml`, `.mvn/extensions.xml`, profiles và plugin executions. Một Maven goal có thể chạy mã plugin/extension, tải artifacts, ghi file, chạy shell, truy cập network hoặc service.

**Help Plugin cũng là code được thực thi**, có thể cần tải từ repository. Nếu chưa xác định trust:
1. Mở file bằng viewer, không chạy script.
2. Xem build plugins, extensions và CI shell commands.
3. Không cấp production tokens/SSH credentials.
4. Dùng sandbox/VM/container giới hạn quyền và network khi được phép.
5. Chỉ chạy Maven goals sau khi review đúng mức.
6. Không dùng `mvn deploy` để tìm remote repository; đọc `distributionManagement`.
7. Không public raw `settings.xml`, effective settings hoặc `mvn -X` logs có thể chứa secrets.

## 2. Quy trình khám phá một Maven project

```text
Repo mới
  |
  +--> [A] Đọc pom.xml, child POMs, .mvn/, CI YAML
  |         Xác định roles / plugins / extensions / trust
  |
  +--> [B] Đọc GAV, modules, properties, dependency management
  |         Vẽ reactor graph, build goals, profiles
  |
  +--> [C] Kiểm tra Maven/JDK/Wrapper
  |         Chỉ dùng binaries đã review
  |
  +--> [D] Help Plugin trong môi trường an toàn
  |         active-profiles, effective-pom, evaluate, describe
  |
  +--> [E] Dependency Plugin
  |         dependency:tree, scopes, mediation
  |
  +--> [F] Test/verify với đúng modules đã chọn
  |         Đọc test reports + Reactor Summary
  |
  +--> [G] Ghi findings, những phần không được chạy và risk
```

| Câu hỏi | Xem từ tĩnh | Đối chiếu bằng Maven |
| --- | --- | --- |
| Project chính là gì? | Root GAV, packaging | `help:evaluate` |
| Bao nhiêu modules? | `<modules>` | Reactor Build Order |
| Java version nào? | Compiler/Toolchains/Enforcer | `mvn -version` |
| Profile nào chạy? | Profiles trong POM/settings | `help:active-profiles` |
| Plugin nào chạy? | Executions và lifecycle bindings | Build log/plugin goal |
| Dependency version nào? | Parent/BOM/management | Effective POM, tree |
| Test nào chạy? | Surefire/Failsafe config | XML reports và test count |
| CI có chạy full không? | Workflow command, `-pl` | Reactor Summary |
| Repository ở đâu? | POM repositories, settings mirrors | Resolve logs |
| Chưa biết gì? | Kết quả đọc + assumptions | Ghi NOT VERIFIED |

**Không biến dữ liệu chỉ dự đoán từ POM thành “đã kiểm chứng”.** Một test chỉ PASS nếu nó thực sự được chạy, không phải vì thư mục test tồn tại.

## 3. Nhận diện root POM và cách tổ chức project

Dấu hiệu Maven thường gặp:

```text
repository/
├── pom.xml
├── .mvn/
│   ├── wrapper/maven-wrapper.properties
│   ├── maven.config
│   └── extensions.xml
├── mvnw
├── mvnw.cmd
├── src/                 (single-module, có thể có)
├── module-a/            (multi-module, có thể có)
└── .github/workflows/   (hoặc Jenkinsfile, .gitlab-ci.yml)
```

Các file không bắt buộc đều có. `pom.xml` là Maven project model. `.mvn/maven.config` có thể chứa args ảnh hưởng Maven command. `.mvn/extensions.xml` có thể nạp build extensions khi Maven khởi động. Maven Wrapper pin distribution nhưng không tự pin JDK/settings/plugins.

### 3.1. GAV và packaging

```xml
<groupId>dev.study</groupId>
<artifactId>unknown-project-lab</artifactId>
<version>1.0.0-SNAPSHOT</version>
<packaging>pom</packaging>
```

GAV = `dev.study:unknown-project-lab:1.0.0-SNAPSHOT`. Packaging `pom` thường cho parent/aggregator; packaging `jar` của child ràng buộc compiler, surefire và jar goals vào lifecycle. Nếu child không khai báo groupId/version, kiểm tra parent inheritance trước khi coi là lỗi.

### 3.2. Aggregator khác parent

- **Aggregator:** khai báo `<modules>` với relative paths để reactor thu thập projects.
- **Parent:** được child tham chiếu qua `<parent>`, cung cấp properties, management, plugins và các cấu hình kế thừa.
- Một root POM có thể làm cả hai vai trò, nhưng aggregation và inheritance **không đồng nghĩa**.
- Một child có thể kế thừa parent từ remote repository mà parent đó không nằm trong reactor; một module được aggregator liệt kê cũng có thể dùng parent khác.

### 3.3. Maven reactor sort

Maven reactor **collect → sort → build**. Sorting dùng dependency/parent/plugin/extension relationships thực tế, không mặc định theo thứ tự `<modules>`. Một entry chỉ nằm trong dependencyManagement **không tạo dependency edge**.

Ví dụ checkout-cli phụ thuộc catalog-core; catalog-core phải được build trước checkout-cli, kể cả khi root `<modules>` liệt kê checkout-cli trước.

## 4. Đọc 10 phần quan trọng trong POM

1. **Coordinates:** groupId, artifactId, version và packaging; xác định artifact identity.
2. **Parent:** GAV parent và `relativePath`; xác định inherited settings và location.
3. **Modules:** relative module paths trong aggregator, build scope của reactor.
4. **Properties:** Java target, encoding, plugin/dependency version aliases; properties có thể bị override.
5. **Dependencies:** direct dependencies, `scope`, `type`, `classifier`, `optional`, `exclusions`.
6. **DependencyManagement:** version/scope/config cho dependencies thực sự được khai báo; BOM import nằm ở đây.
7. **Build Plugins:** plugin goals/executions, phase bindings và side effects.
8. **PluginManagement:** pin versions/config **khi plugin được dùng**, không tự chạy mọi goal.
9. **Profiles:** activeByDefault, `-P`, JDK/OS/property/file activation và hiệu ứng lên model.
10. **Repositories/Distribution:** `<repositories>`, `<pluginRepositories>` nguồn tải artifacts; `<distributionManagement>` là đích publish, không phải lệnh để thử.

### 4.1. dependencyManagement không giống dependencies

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.study</groupId>
            <artifactId>catalog-core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây chỉ là **quản lý version**. Nếu child muốn dùng catalog-core phải có:

```xml
<dependencies>
    <dependency>
        <groupId>dev.study</groupId>
        <artifactId>catalog-core</artifactId>
    </dependency>
</dependencies>
```

Version bỏ trống ở child sẽ được quản lý. Nếu child **không có** dependency declaration thì catalog-core không được tự thêm vào classpath.

BOM `type=pom`/`scope=import` trong dependencyManagement cũng chỉ cung cấp version management, không tự thêm runtime JAR.

### 4.2. pluginManagement khác plugins

Trong `<build><pluginManagement>`, version/compiler config dùng khi plugin được invoked qua default lifecycle hoặc explicit declaration. Với jar packaging, Surefire test goal mặc định bind vào `test` nên version quản lý có thể áp dụng dù không thấy child khai báo plugin trực tiếp.

Khi đọc `<build><plugins>`, xem `<executions><execution><phase>` để biết Maven chạy goal ở phase nào. Một Exec/Antrun/custom goal bind `validate` là lý do `mvn validate` **không mặc nhiên read-only**.

### 4.3. Profiles và settings

Profiles trong POM hoặc settings có thể active qua `-Pci`, `<activeByDefault>`, JDK/OS, property hoặc file existence. User settings thường ở `~/.m2/settings.xml`; global settings đi kèm Maven installation.

`help:active-profiles` cho thấy profiles thật, còn `help:effective-pom` cho thấy tác động của chúng tới model. Đừng đoán từ tên “dev”/“ci”. Settings cũng có thể cung cấp mirrors, servers/proxy và local repository khác nhau giữa máy cá nhân, IDE và CI.

## 5. Bảng lệnh khám phá và rủi ro

| Lệnh | Trả lời câu hỏi | Rủi ro cần lưu ý |
| --- | --- | --- |
| `mvn -version` | Maven/JDK đang dùng | Dùng executable tin cậy |
| `java -version` | Java trong shell | Có thể khác Maven runtime |
| `help:active-profiles` | Profiles nào đang active | Maven plugin invocation |
| `help:all-profiles` | Profiles nào được khai báo | Có thể resolve plugin |
| `help:effective-pom` | Effective build model | Output lớn, có nội bộ |
| `help:effective-settings` | User/global settings merge | Có dữ liệu nhạy cảm |
| `help:evaluate` | Giá trị một expression | Không in secret properties |
| `help:describe` | Goal/params của plugin | Plugin resolution |
| `dependency:tree` | Resolved dependency graph | Resolution/network/cache |
| `mvn validate` | Model và bound validate goals | Có thể chạy custom plugins |
| `mvn test` | Unit tests | Chạy test code |
| `mvn verify` | Các phase/goals tới verify | Có thể chạy IT/quality gates |
| `mvn install` | Ghi artifacts vào local repo | Có side effects |
| `mvn deploy` | Publish remote | Cần authorization riêng |

CLI options hay gặp: `-B` batch mode, `-ntp` bỏ transfer progress, `-N` non-recursive, `-f` starting POM, `-Pci` profile, `-Dkey=value` property, `-s` user settings, `-pl` selected modules, `-am` upstream, `-amd` downstream, `-rf` resume theo reactor order.

## 6. Maven Help Plugin — câu hỏi nào dùng goal nào?

Các ví dụ dùng **maven-help-plugin 3.5.2** để ghim version. Chỉ thực thi khi repository/plugin source đã được review.

### 6.1. Active profiles

```bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp -Pci org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
```

Hai lệnh giúp so profiles mặc định và khi chọn `ci`. Đây là profiles thực sự áp dụng, khác với việc chỉ thấy profile block trong source POM.

### 6.2. All profiles

```bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:all-profiles
```

Liệt kê các profiles có sẵn và active/inactive. Không dùng output này để khẳng định mọi profile đều active.

### 6.3. Effective POM

```bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true
```

Effective POM bao gồm inheritance, interpolation, profiles và plugin/dependency management. `-Dverbose=true` thêm comments mô tả nguồn của từng phần XML.

Để xem riêng root:

```bash
mvn -B -ntp -N org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

**-N giới hạn root POM, không thay thế effective POM của child**. Ở multi-module project, output của goal có thể dài; phải xác định đúng project đang đọc.

### 6.4. Effective settings

```bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings
```

Dùng để xem user/global settings sau merge: mirror, proxies, server IDs, repositories và local repo. **Không bật `showPasswords=true`, không chia sẻ raw effective settings hoặc `mvn -X` logs**; có thể chứa endpoint và secret/property nội bộ dù một số fields được che.

### 6.5. Evaluate một expression

```bash
mvn -q -N org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=project.groupId -DforceStdout
mvn -q -N org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=project.artifactId -DforceStdout
mvn -q -N org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=project.version -DforceStdout
```

Đối với property mẫu của lab:

```bash
mvn -q -N org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=inspection.environment -DforceStdout
mvn -q -N -Pci org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=inspection.environment -DforceStdout
```

Dự kiến `dev` và `ci` nếu không bị settings/CLI khác can thiệp.

### 6.6. Describe plugin goal

```bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=org.apache.maven.plugins:maven-surefire-plugin:3.5.2 -Dgoal=test -Ddetail=true
```

Goal này hiển thị tên, mô tả, default phase và các parameters của Surefire `test`. **Nó không tự chạy unit tests**. Nếu POM/CI dùng một tham số plugin lạ, tra help:describe hoặc docs version-specific trước khi sửa.

## 7. Maven Dependency Plugin: đọc cây phụ thuộc đã resolve

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Có thể lọc theo nhóm:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=dev.study
```

Hoặc xuất JSON:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -DoutputType=json -DoutputFile=dependency-tree.json
```

Plugin 3.11.0 hỗ trợ output JSON. Không phải mọi version cũ hỗ trợ cùng flags.

Ví dụ **rút gọn mang tính khái niệm**, không phải raw tree hoàn chỉnh:

```text
dev.study:checkout-cli:jar:1.0.0-SNAPSHOT
+- dev.study:catalog-core:jar:1.0.0-SNAPSHOT:compile
\- org.junit.jupiter:junit-jupiter:jar:5.11.4:test
   ... JUnit transitive dependencies ...
```

- `compile` khác `test` trong classpath/scope.
- Tree thể hiện direct/transitive dependencies sau mediation.
- Version trong tree có thể đến từ parent/BOM.
- Tree không mô tả plugin execution hoặc cross-service HTTP/event contracts.
- Tree có thể cần tải artifacts. **Một invocation `verify` không tự `install` internal artifacts** xuống local repository; tree trong invocation mới có thể fail resolution nếu thiếu snapshots.

## 8. Dự án hoàn chỉnh Java 17 để học cách đọc

Tạo một thư mục mới. Ba child modules: catalog-core là provider, checkout-cli là consumer, report-tools độc lập.

```text
unknown-project-lab/
├── pom.xml
├── catalog-core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/study/catalog/PriceMath.java
│       └── test/java/dev/study/catalog/PriceMathTest.java
├── checkout-cli/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/study/checkout/CheckoutApp.java
│       └── test/java/dev/study/checkout/CheckoutAppTest.java
└── report-tools/
    ├── pom.xml
    └── src/
        ├── main/java/dev/study/report/ReportLabel.java
        └── test/java/dev/study/report/ReportLabelTest.java
```

Graph: **checkout-cli → catalog-core**; report-tools độc lập. Root là aggregator + parent.

### 8.1. Root pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.study</groupId>
    <artifactId>unknown-project-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <!-- Consumer đứng trước provider để minh họa reactor sort -->
    <modules>
        <module>checkout-cli</module>
        <module>report-tools</module>
        <module>catalog-core</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <inspection.environment>base</inspection.environment>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>dev.study</groupId>
                <artifactId>catalog-core</artifactId>
                <version>${project.version}</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                    <configuration>
                        <release>17</release>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                    <configuration>
                        <failIfNoTests>true</failIfNoTests>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>

    <profiles>
        <profile>
            <id>dev</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <properties>
                <inspection.environment>dev</inspection.environment>
            </properties>
        </profile>
        <profile>
            <id>ci</id>
            <properties>
                <inspection.environment>ci</inspection.environment>
            </properties>
        </profile>
    </profiles>
</project>
```

Đọc POM:
- `packaging=pom` và `<modules>`: aggregator.
- Child `<parent>` tới root: parent.
- dependencyManagement chỉ quản lý catalog-core/JUnit versions.
- pluginManagement quản lý Compiler/Surefire/JAR versions/config.
- `inspection.environment` dùng **chỉ để exercise Help Plugin**, không làm stdout ứng dụng đổi.
- dev activeByDefault; -Pci chọn ci.
- Không có Failsafe/JaCoCo/Checkstyle executions trong lab; không giả vờ verify chạy những gates đó.

### 8.2. catalog-core/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.study</groupId>
        <artifactId>unknown-project-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>catalog-core</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 8.3. checkout-cli/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.study</groupId>
        <artifactId>unknown-project-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>checkout-cli</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>dev.study</groupId>
            <artifactId>catalog-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

checkout-cli khai báo catalog-core **without version** vì parent đã quản lý. Scope không ghi nên mặc định **compile**.

### 8.4. report-tools/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.study</groupId>
        <artifactId>unknown-project-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>report-tools</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

report-tools cùng parent nhưng **không có internal dependency** vào hai modules còn lại.

## 9. Java 17 sources và sáu unit tests

### 9.1. PriceMath.java

Tệp `catalog-core/src/main/java/dev/study/catalog/PriceMath.java`:

```java
package dev.study.catalog;

public final class PriceMath {
    private PriceMath() {
    }

    public static int total(int unitPrice, int count) {
        if (unitPrice < 0 || count < 0) {
            throw new IllegalArgumentException(
                    "Price and count must be nonnegative");
        }
        return Math.multiplyExact(unitPrice, count);
    }
}
```

`Math.multiplyExact` ném ArithmeticException khi overflow, tránh tràn số nguyên âm thầm.

### 9.2. PriceMathTest.java

Tệp `catalog-core/src/test/java/dev/study/catalog/PriceMathTest.java`:

```java
package dev.study.catalog;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceMathTest {
    @Test
    void calculatesTotal() {
        assertEquals(45, PriceMath.total(15, 3));
    }

    @Test
    void rejectsNegativeCount() {
        assertThrows(IllegalArgumentException.class,
                () -> PriceMath.total(15, -1));
    }
}
```

**2 unit tests** cho provider module.

### 9.3. CheckoutApp.java

Tệp `checkout-cli/src/main/java/dev/study/checkout/CheckoutApp.java`:

```java
package dev.study.checkout;

import dev.study.catalog.PriceMath;

public final class CheckoutApp {
    private CheckoutApp() {
    }

    public static String summary() {
        return "CHECKOUT_TOTAL=" + PriceMath.total(15, 3);
    }

    public static void main(String[] args) {
        System.out.println(summary());
    }
}
```

Stdout chính xác:

```text
CHECKOUT_TOTAL=45
```

### 9.4. CheckoutAppTest.java

Tệp `checkout-cli/src/test/java/dev/study/checkout/CheckoutAppTest.java`:

```java
package dev.study.checkout;

import dev.study.catalog.PriceMath;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CheckoutAppTest {
    @Test
    void printsExpectedSummary() {
        assertEquals("CHECKOUT_TOTAL=45", CheckoutApp.summary());
    }

    @Test
    void supportsZeroCount() {
        assertEquals(0, PriceMath.total(15, 0));
    }
}
```

**2 unit tests** trong consumer module.

### 9.5. ReportLabel.java

Tệp `report-tools/src/main/java/dev/study/report/ReportLabel.java`:

```java
package dev.study.report;

import java.util.Locale;

public final class ReportLabel {
    private ReportLabel() {
    }

    public static String normalize(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Label cannot be blank");
        }
        return "REPORT:" + input.strip().toUpperCase(Locale.ROOT);
    }
}
```

report-tools độc lập với catalog-core.

### 9.6. ReportLabelTest.java

Tệp `report-tools/src/test/java/dev/study/report/ReportLabelTest.java`:

```java
package dev.study.report;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ReportLabelTest {
    @Test
    void normalizesInput() {
        assertEquals("REPORT:PAYMENT",
                ReportLabel.normalize(" payment "));
    }

    @Test
    void rejectsBlankLabel() {
        assertThrows(IllegalArgumentException.class,
                () -> ReportLabel.normalize("   "));
    }
}
```

**2 unit tests**. Tổng: **6 JUnit tests** trên cả 3 Java modules.

## 10. Tự đọc lab trước khi build: suy ra được gì?

| Thuộc tính | Kết luận từ POM/source |
| --- | --- |
| Root GAV | `dev.study:unknown-project-lab:1.0.0-SNAPSHOT` |
| Root packaging | pom |
| Root vai trò | aggregator + parent |
| Java modules | catalog-core, checkout-cli, report-tools |
| Internal dependency | checkout-cli → catalog-core |
| Java target | 17 |
| JUnit | Jupiter 5.11.4 từ dependencyManagement |
| Compiler Plugin | 3.14.1 |
| Surefire Plugin | 3.5.2 |
| JAR Plugin | 3.4.2 |
| Default profile | dev |
| Optional profile | ci |
| Số tests dự kiến | 6 |
| Stdout dự kiến | CHECKOUT_TOTAL=45 |
| Failsafe/JaCoCo | Chưa cấu hình |
| Publish target | Không khai báo distributionManagement |

Đây là **các kết luận đọc tĩnh**, không phải những phép đo đã chạy.

### 10.1. Hỏi Maven Help Plugin

Từ root trong môi trường được duyệt:

```bash
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true
```

Tìm version catalog-core của checkout-cli và JUnit 5.11.4, plugin versions và release 17. Lệnh effective-pom trên reactor có thể in nhiều projects; đừng lấy root effective POM thay cho child model.

### 10.2. Đọc property có profile

```bash
mvn -q -N org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=inspection.environment -DforceStdout
mvn -q -N -Pci org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=inspection.environment -DforceStdout
```

Khi không có settings/CLI override, giá trị dự kiến lần lượt là **dev** và **ci**. Java code không dùng property này, nên stdout ứng dụng không đổi giữa hai profile.

## 11. Build đầy đủ trong lab và xác minh

```bash
mvn -B -ntp clean verify
```

Dự kiến:
- catalog-core: **2 tests**.
- checkout-cli: **2 tests**.
- report-tools: **2 tests**.
- Tổng **6 tests**, 0 failures, Maven BUILD SUCCESS.

Log rút gọn minh họa (không phải toàn bộ output):

```text
catalog-core ... Tests run: 2, Failures: 0
checkout-cli ... Tests run: 2, Failures: 0
report-tools  ... Tests run: 2, Failures: 0
BUILD SUCCESS
```

Reports ở:
- `catalog-core/target/surefire-reports/`
- `checkout-cli/target/surefire-reports/`
- `report-tools/target/surefire-reports/`

Chỉ ghi “đã chạy” nếu file XML/log xác nhận tests thực sự chạy.

### 11.1. Chạy Java main

Linux/macOS:

```bash
java -cp "checkout-cli/target/classes:catalog-core/target/classes" dev.study.checkout.CheckoutApp
```

Windows PowerShell/cmd:

```powershell
java -cp "checkout-cli/target/classes;catalog-core/target/classes" dev.study.checkout.CheckoutApp
```

Stdout chính xác:

```text
CHECKOUT_TOTAL=45
```

Không mặc định dùng `java -jar checkout-cli/target/checkout-cli-1.0.0-SNAPSHOT.jar`, vì POM chưa cấu hình Main-Class và fat JAR. Chạy classpath giúp thấy rõ hai modules cần thiết.

## 12. Build một phần và lỗi ẩn

```bash
mvn -B -ntp -pl :checkout-cli -am clean verify
```

Maven chọn checkout-cli và upstream catalog-core; report-tools **NOT SELECTED**. Chỉ **4 tests** của hai modules được chạy.

### 12.1. Mutation test chứng minh partial green

Trong **lab**, sửa tạm một test ở `ReportLabelTest.java`:

Từ:

```java
assertEquals("REPORT:PAYMENT",
        ReportLabel.normalize(" payment "));
```

sang:

```java
assertEquals("REPORT:OTHER",
        ReportLabel.normalize(" payment "));
```

Giá trị thực vẫn REPORT:PAYMENT nên test của report-tools FAIL khi chạy. Nhưng `mvn -pl :checkout-cli -am clean verify` **có thể PASS** vì report-tools bị loại. Khi chạy full `mvn clean verify`, failure sẽ được phát hiện.

**Khôi phục expected REPORT:PAYMENT và full verify lại trước commit.** Bài này minh họa rằng một build partial SUCCESS không nói gì về modules chưa chạy.

### 12.2. Không có -am thì sao?

```bash
mvn -B -ntp -pl :checkout-cli clean verify
```

Nếu catalog-core chưa được install vào local repo, dependency resolution có thể FAIL. Nếu có bản SNAPSHOT cũ, Maven có thể dùng binary stale, không phản ánh source checkout hiện tại.

Với project nhiều modules, `-am` kéo upstream source projects trong reactor; không kéo các modules độc lập hoặc mọi downstream consumers.

## 13. Đọc dependency tree của lab

```bash
mvn -B -ntp -pl :checkout-cli -am org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Trong tree của checkout-cli, cần nhận diện:
- catalog-core 1.0.0-SNAPSHOT compile.
- JUnit Jupiter 5.11.4 test.
- JUnit transitive dependencies.
- Không có report-tools vì checkout-cli không phụ thuộc module đó.

**Chú ý resolution:** một lệnh `mvn verify` không tự install internal artifacts; invocation dependency:tree tách biệt có thể không resolve được catalog-core nếu local repo chưa có. Trong lab được tin cậy, có thể chạy `mvn install` sau khi xem goals để điền local repository; không tự thực hiện bước này trong repo chưa được review.

## 14. Chẩn đoán lỗi theo đúng layer

| Triệu chứng | Kiểm tra đầu tiên |
| --- | --- |
| Missing POM | Working dir và `-f` |
| Parent POM không resolve | Parent GAV, `relativePath`, settings |
| Dependency version missing | Parent/BOM dependencyManagement |
| Java 17 unsupported | Maven runtime JDK, Compiler/Toolchains |
| Plugin goal không chạy | Effective POM, packaging, executions |
| Surefire không tìm test | Naming, JUnit engine, skip flags |
| CI 401/403 | Mirror/server IDs và token scope, không in token |
| Plugin không tải | pluginRepositories, proxy, offline |
| Local PASS nhưng CI FAIL | Settings, profile, JDK, cache, CLI args |
| Report khác giữa modules | Reactor selection và phase dừng |
| Tree internal artifact unresolved | Local repo chưa có SNAPSHOT hoặc sai GAV |
| BUILD SUCCESS nhưng module khác FAIL | Partial build không chọn module |
| Test fail nhưng không có JUnit XML | Compile/lifecycle chưa tới tests hoặc fork crash |

Quy trình:
1. Ghi Maven/JDK version, command, starting POM.
2. Xem error gốc và module trong Reactor Summary.
3. Xác định plugin goal/phase lỗi.
4. So active profiles/effective POM.
5. Kiểm tra tree, settings/mirrors nếu lỗi dependency.
6. Xem reports của test thực sự được chạy.
7. Sửa nguyên nhân, rerun cùng scope, ghi bằng chứng.

**Đừng bật `mvn -X` và upload raw debug log làm bước đầu.** Nó có thể chứa private URLs/system properties/credentials.

## 15. IDE, CI và Maven CLI có thể khác nhau

IDE có thể dùng bundled Maven, importer JDK, runner JDK, user settings, active profiles hoặc native JUnit runner riêng. CI có thể dùng Maven Wrapper/runner image khác, `-s` settings, `-Pci`, `-DskipTests`, `-pl` hoặc credentials tạm.

Khi so:
- `mvn -version` và Maven Wrapper version.
- Java chạy Maven, compiler/toolchain target.
- Active profiles và effective POM.
- User/global settings và mirror/repository IDs.
- Exact Maven invocation/selected modules.
- Test reports, count, failures, skipped.
- Plugin versions và artifact outputs.

**Một IDE test run không tự chứng minh Failsafe/Checkstyle/JaCoCo goals đã chạy trong CI.** Đọc cấu hình từng môi trường.

## 16. Mẫu báo cáo bàn giao dự án

Dưới đây là **báo cáo kỳ vọng của lab**, không phải Maven auto-report. Khi dùng cho repo thật, chỉ đổi sang “observed” sau khi có logs/reports.

```text
Repo: unknown-project-lab
Git commit: ghi SHA thực tế nếu có
Root GAV: dev.study:unknown-project-lab:1.0.0-SNAPSHOT
Packaging: pom
Roles: aggregator + parent
Java target: 17
Modules: catalog-core, checkout-cli, report-tools

Internal edges:
  checkout-cli -> catalog-core
  report-tools -> none

Managed versions:
  catalog-core 1.0.0-SNAPSHOT
  JUnit Jupiter 5.11.4

Managed plugins:
  compiler 3.14.1
  surefire 3.5.2
  jar 3.4.2

Profiles:
  dev default / ci via -Pci

Expected full:
  mvn clean verify
  3 Java modules, 6 tests

Expected partial:
  mvn -pl :checkout-cli -am clean verify
  catalog-core + checkout-cli: 4 tests
  report-tools NOT SELECTED

Expected output:
  CHECKOUT_TOTAL=45

Not verified:
  deployment, private repository authorization,
  actual CI-specific plugins, cross-service contracts
```

Trong báo cáo sản xuất, có ba cột:
- **Known from source**: đã đọc POM/file, chưa chạy.
- **Observed from tools**: Maven/JDK versions, effective model, test reports, exit code.
- **Unknown / follow-up**: cần owner giải thích hoặc kiểm tra thêm.

Không để mật khẩu/token vào tài liệu. Nếu dùng links tới CI, chỉ chia sẻ trong phạm vi quyền.

## 17. Bài tập tự luyện

1. Phân biệt aggregator và parent Maven.
2. GAV là gì? Packaging ảnh hưởng default goals thế nào?
3. Vì sao một dependency thiếu version vẫn có thể đúng?
4. Vì sao dependencyManagement không tự thêm thư viện?
5. pluginManagement có tự chạy mọi plugin goal không?
6. `mvn validate` có luôn an toàn trong repo lạ không?
7. Cách biết profile nào active?
8. `help:all-profiles` khác `help:active-profiles` ra sao?
9. Khi nào cần `help:effective-pom -Dverbose=true`?
10. Tại sao không gửi raw effective-settings?
11. `help:evaluate` giải quyết vấn đề gì?
12. Dùng `help:describe` đọc Surefire parameters.
13. Tạo root POM và ba child POMs trong lab.
14. Xác nhận checkout-cli phụ thuộc catalog-core.
15. Dựng đầy đủ 6 Java files trong lab.
16. Chạy full reactor và xác nhận **6 tests**.
17. Chạy CheckoutApp và xác nhận `CHECKOUT_TOTAL=45`.
18. Chạy `-pl :checkout-cli -am verify`, lý giải vì sao có **4 tests**.
19. Vì sao report-tools bị bỏ qua?
20. Cố ý làm ReportLabelTest FAIL và so full/partial.
21. Khôi phục mutation và verify lại.
22. Nếu -pl không -am dùng SNAPSHOT cũ, rủi ro là gì?
23. `dependency:tree` khác POM declarations thế nào?
24. Tại sao tree có thể fail do thiếu internal artifacts?
25. Phân biệt test, verify, install, deploy.
26. Vì sao CLI và IDE có thể cho kết quả khác?
27. Khi CI lỗi 401/403, cách chẩn đoán không lộ token?
28. Khi Maven reports không tồn tại, có thể kết luận tests PASS không?
29. Viết bản đồ reactor và tài liệu known/observed/unknown cho repo thực.
30. Nêu các hành động cần phê duyệt trước khi chạy trong repo lạ.

## 18. Checklist kết thúc khám phá

- [ ] Root POM, GAV, packaging đã rõ.
- [ ] Aggregator/parent/module boundaries đã được xác nhận.
- [ ] Dependencies và management/BOM được phân biệt.
- [ ] Plugin bindings và build side effects đã được review.
- [ ] Maven/JDK/Wrapper versions đã được ghi rõ.
- [ ] Profiles đang active đã được kiểm tra.
- [ ] Effective POM/settings được xem trong môi trường an toàn.
- [ ] Dependency tree và cache limitations đã được hiểu.
- [ ] CI command/selected modules/skip flags đã được ghi nhận.
- [ ] Surefire/Failsafe/quality gates đã được phân biệt.
- [ ] Tests thật sự chạy có reports và số lượng đáng tin.
- [ ] Partial build không bị báo nhầm là full verification.
- [ ] Không chạy deploy/release trong giai đoạn khám phá.
- [ ] Không public credentials/settings/raw debug logs.
- [ ] Báo cáo có known/observed/unknown và next steps.

## 19. Kết luận

**Tự đọc một dự án Maven** là quá trình nối dữ liệu từ POM, effective model, dependency graph và evidence từ lifecycle execution.

- POM trả lời **khai báo gì**.
- Help Plugin trả lời **cấu hình nào có hiệu lực**.
- Dependency Plugin trả lời **dependency graph sau resolution**.
- Maven logs/test reports cho thấy **mô-đun nào và goal nào thực sự chạy**.
- Security/trust review quyết định **được phép thực thi gì**, không phải Maven tự bảo đảm an toàn.

Lab Java 17 minh họa **3 modules, 6 JUnit tests**, còn build checkout + upstream chỉ có **4 tests**. Java app in:

```text
CHECKOUT_TOTAL=45
```

Khi bạn tách rõ **cấu hình tĩnh, kết quả đã chạy và những điều chưa được kiểm chứng**, bạn đã đủ cơ sở để tiếp tục làm việc trên một Maven project chưa quen.

## 20. Nguồn Apache Maven chính thức

- [Maven POM Reference](https://maven.apache.org/pom.html)
- [Maven Multi-Module Reactor Guide](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Maven Settings](https://maven.apache.org/settings.html)
- [Maven Help Plugin Goals](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html)
- [Help effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Help active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Help all-profiles](https://maven.apache.org/plugins/maven-help-plugin/all-profiles-mojo.html)
- [Help evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html)
- [Help describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
- [Help effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Surefire](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Failsafe](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Maven Wrapper](https://maven.apache.org/tools/wrapper/)
