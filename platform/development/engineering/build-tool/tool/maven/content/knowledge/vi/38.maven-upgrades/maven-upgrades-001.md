# Lập danh mục phiên bản Maven, JDK, plugin và extension đang dùng

## 1. Tại sao cần kiểm kê trước khi nâng cấp Maven?

Trước khi thay Maven core hoặc JDK, đội phát triển cần biết **những phiên bản thật sự tham gia build**. Không thể chỉ đọc một dòng `<maven.compiler.release>17</maven.compiler.release>` rồi kết luận toàn hệ thống đang chạy JDK17, hoặc thấy một plugin trong `pluginManagement` rồi cho rằng goal của nó đã chạy ở CI.

Một build có thể phụ thuộc vào:

- Maven executable do `PATH` cung cấp hoặc Maven Wrapper trong repository.
- JVM/JDK thực tế dùng để chạy Maven core và plugins.
- JDK riêng được Maven Toolchains/Compiler Plugin lựa chọn để biên dịch.
- Maven plugin versions khai trong POM, kế thừa qua parent, profiles và pluginManagement.
- Lifecycle goals ngầm được bind theo packaging, không nhất thiết hiện rõ trong source POM.
- Plugin dependencies riêng với project dependencies.
- Core extensions tải từ `.mvn/extensions.xml` hoặc môi trường Maven launcher.
- Build extensions trong `build/extensions` hoặc plugin có `extensions=true`.
- Reporting plugins dùng ở `site`, khác plugins dùng ở `verify`.
- CI matrix, module selection, settings, active profiles và các yếu tố chỉ có lúc runtime.

**Mục tiêu:** lập bản kê có thể dùng làm baseline trước/sau migration Maven/JDK, mỗi dòng có scope, version, nguồn bằng chứng và trạng thái kiểm chứng. Bản kê là **inventory hiện trạng**, không phải danh sách đề xuất “latest versions”.

### Kết quả học tập

Bạn sẽ học cách:

1. Phân biệt declared, managed, effective, resolved và executed versions.
2. Thu Maven core version và Java runtime thật bằng `mvn -version` hoặc `./mvnw -version`.
3. Đọc Wrapper `distributionUrl`, version pin và checksum policy.
4. Phân biệt Maven JVM JDK, Java trên PATH, javac trên PATH, selected toolchain JDK và target `--release`.
5. Trích các plugins được khai, quản lý, effective và thực sự execute.
6. Dùng Maven Help Plugin, Dependency Plugin và Versions Maven Plugin đúng mục đích.
7. Xác định core/build extensions và ngoài-repo Maven extension injections.
8. Chạy dự án Maven3.9/Java17/JUnit5 với POM có Enforcer guards.
9. Viết script Python3 chuẩn để lấy metadata từ effective POM và extensions XML.
10. Tạo danh mục dạng CSV/Markdown, diff trước–sau và xử lý các trường còn unknown.
11. Xây CI workflow thu evidence mà không rò rỉ credentials hoặc nhầm cached output với current build.

Phiên bản cố định **dùng trong ví dụ**: Maven **3.9.12** (qua Wrapper khi được cài), JDK **17+**, Maven Compiler Plugin **3.14.1**, Surefire **3.5.4**, Jar **3.4.2**, Enforcer **3.6.3**, Help **3.5.2**, Dependency Plugin **3.11.0**, MojoHaus Versions Plugin **2.25.1**, JUnit Jupiter **5.11.4**. Đây chỉ là **fixture học tập**, phải đo dự án thật trước khi dùng số liệu để quyết định nâng cấp.

---

## 2. Năm lớp thông tin khác nhau

| Lớp | Nghĩa | Nguồn | Hạn chế |
| --- | --- | --- | --- |
| Declared | Version được khai trực tiếp | POM source, Wrapper properties, extension files | Có thể bị parent/profile/CLI thay đổi |
| Managed | Version do `pluginManagement` hoặc parent quản lý | Parent/effective POM | Không chứng minh plugin đã chạy |
| Effective | Model Maven tính sau inheritance và profile activation | `help:effective-pom` | Không thay actual execution trace |
| Resolved | Artifact Maven đã lấy từ repository | Resolver/plugin resolution logs | Download được không bằng đã thực thi |
| Executed | Plugin version+goal thật được Maven gọi | Build log, `-X` | Phụ thuộc CI invocation/phase/module |

Ví dụ khác nhau:

~~~text
Plugin declared: maven-surefire-plugin (không có version ở child)
Plugin managed: 3.5.4 trong parent
Plugin effective: 3.5.4 sau inheritance
Plugin executed: surefire:3.5.4:test ở lệnh clean verify
Candidate: 3.x khác mà Versions Plugin gợi ý
~~~

Candidate version là **lựa chọn nâng cấp**, không phải version đang dùng.

### 2.1. Đơn vị ghi một inventory record

~~~text
repo | commitSHA | module | profile | environment | command
kind | groupId | artifactId | version | role
evidenceLevel | evidenceFile | executedGoal
MavenVersion | MavenJDK | compilerToolchain | observedAt
status | owner | candidateVersion | migrationNotes
~~~

Thiếu bằng chứng thì ghi **unverified**. Không được tự điền version theo tài liệu mới nhất thay cho build thực tế.

### 2.2. Không có một inventory duy nhất cho mọi build

Một monorepo có JDK17 và JDK21 jobs, profiles `ci`/`release`, Maven CLI và Maven Wrapper, các child POM overrides sẽ có nhiều runtime configurations. Inventory phải giữ **ngữ cảnh đúng** để sau này so sánh đồng nhất.

---

## 3. Xác định Maven thực sự chạy

### 3.1. Maven từ PATH

~~~bash
mvn -version
~~~

Kết quả có thể có dạng:

~~~text
Apache Maven 3.9.12 (...)
Maven home: ...
Java version: 17..., vendor: ..., runtime: ...
Default locale: ..., platform encoding: ...
OS name: ..., arch: ...
~~~

**Đây là dạng output minh họa, không phải log đã đo trong dự án của bạn.** Ghi Maven version, Maven home, Java version/vendor/runtime, OS/arch và môi trường shell.

Nếu máy có nhiều Maven distributions, `mvn` trên PATH có thể khác Maven được team pin.

### 3.2. Maven Wrapper

Cấu trúc thường thấy:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
.mvn/wrapper/maven-wrapper.jar  (tùy wrapper distribution type)
~~~

Một dòng properties minh họa:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.12/apache-maven-3.9.12-bin.zip
~~~

Lệnh trên Linux/macOS:

~~~bash
./mvnw -version
~~~

Windows:

~~~text
mvnw.cmd -version
~~~

**Phân biệt** Wrapper configured version đọc từ file với version thực in bởi launcher. File properties đơn độc không đủ để chạy Wrapper nếu scripts chưa được cài vào repository.

### 3.3. Kiểm checksum

Maven Wrapper hỗ trợ `distributionSha256Sum` và theo phương thức wrapper `wrapperSha256Sum`. Nếu có, xác minh checksum dựa trên nguồn đáng tin; không tự tạo giá trị giả. Nếu chưa cấu hình thì ghi `checksum not pinned` để supply-chain review.

Không đưa credentials vào `distributionUrl` được commit trong source.

### 3.4. Không tự nâng plugin khi nâng Maven core

Maven core và Maven plugins có release cycles riêng. Việc dùng Maven3.9.12 không nói Compiler/Surefire/Enforcer đang ở bản 3.9.12. Khi thử Maven4 cần rà Maven plugin requirements, extensions và JDK compatibility, không chỉ thử `mvn -version`.

---

## 4. Kiểm kê Java/JDK đúng từng mục đích

### 4.1. Maven JVM

Lấy từ `mvn -version` hoặc `./mvnw -version` trong **đúng CI job**. Đây là JVM chạy Maven core, nhiều build plugins và core extensions.

### 4.2. Java trên PATH

~~~bash
java -version
~~~

Có thể khác Java runtime mà Maven dùng do `JAVA_HOME`, launcher hoặc IDE config.

### 4.3. Javac trên PATH

~~~bash
javac -version
~~~

Không chứng minh Compiler Plugin sử dụng nó, vì Maven Toolchains hoặc compilerExecutable có thể chọn JDK khác.

### 4.4. Compiler target

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Maven Compiler Plugin có thể truyền `--release 17` để tạo bytecode/API tương thích Java17. Điều này **không** biến Maven JVM thành JDK17.

### 4.5. Toolchains

Một project có thể chạy Maven trên JDK21 nhưng dùng toolchain JDK17 để compile; Surefire/Failsafe test JVM lại có thể dùng JDK khác theo config.

Snippet yêu cầu toolchain (không phải XML file đầy đủ):

~~~xml
<toolchains>
    <jdk>
        <version>17</version>
        <vendor>temurin</vendor>
    </jdk>
</toolchains>
~~~

Khi audit, ghi **requested toolchain criteria**, **selected JDK home/version** từ plugin logs và **Compiler release** riêng. Không public toàn bộ `~/.m2/toolchains.xml` nếu có machine-specific private paths.

| Dữ liệu | Nguồn | Không thể suy ra |
| --- | --- | --- |
| Maven JVM JDK | Maven launcher version output | Compiler toolchain giống |
| Shell Java | `java -version` | Maven JVM chắc chắn dùng |
| Shell javac | `javac -version` | Compiler Plugin chọn nó |
| Selected toolchain | Toolchain/plugin logs | Test JVM cũng dùng nó |
| Bytecode/API release | effective Compiler config | JDK runtime đang là 17 |

---

## 5. Plugin được khai, được quản lý và chạy ở đâu?

### 5.1. build/plugins

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
        </plugin>
    </plugins>
</build>
~~~

Đây là version khai trực tiếp.

### 5.2. pluginManagement

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Entry này quản lý version/config. **Không mặc nhiên có nghĩa goal chạy.** Với plugin được lifecycle bind, managed version có thể áp dụng khi goal chạy.

### 5.3. Reporting plugins

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

Reporting plugins có thể phục vụ `mvn site`, không nhất thiết chạy ở `mvn verify`. Ghi inventory role=reporting.

### 5.4. Parent POM và profiles

Version có thể được thừa kế, override tại child hoặc profile. Dùng Maven Help Plugin:

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom \
  -Dverbose=true \
  -Doutput=target/effective-pom.xml
~~~

Bản một dòng chạy được trên PowerShell/CMD:

~~~text
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=target/effective-pom.xml
~~~

`verbose=true` thêm comments chỉ nguồn origin cho các phần tử; giúp tìm plugin version đến từ parent/profile nào.

### 5.5. Default lifecycle

Với packaging `jar`, Maven bind một số plugin goals mặc định. Nếu không thấy mọi goal/plugin trong source POM, **đọc actual build log** và lifecycle mapping/Maven core version. Effective POM là thông tin model, không phải đầy đủ “plugins đã execute”.

---

## 6. Xác minh plugin versions thật sự được execute

~~~bash
mvn -B -ntp clean verify
~~~

Log thường có phần dạng:

~~~text
--- enforcer:3.6.3:enforce (...) @ maven-inventory-demo ---
--- compiler:3.14.1:compile (...) @ maven-inventory-demo ---
--- surefire:3.5.4:test (...) @ maven-inventory-demo ---
--- jar:3.4.2:jar (...) @ maven-inventory-demo ---
~~~

Các dòng trên là **minh họa format**, không phải log nguyên văn; thực tế có thể chứa resources/compiler:testCompile/clean và thứ tự khác.

- `effective plugin`: được Maven model xác định.
- `resolved plugin`: JAR/metadata đã lấy từ repository.
- `executed plugin goal`: có bằng chứng trong invocation log.

Không gắn nhãn executed cho Help/Versions chỉ vì POM khai versions của chúng. Chúng có thể không có goal nào trong `verify`.

Khi cần:

~~~bash
mvn -e -X clean verify
~~~

`-X` có thể cho plugin realm, resolution và configuration. Đừng chia sẻ raw logs nếu chứa private repositories/tokens.

---

## 7. Plugin dependencies và project dependencies khác nhau

Một plugin là mã Java chạy trong plugin class realm, có dependencies riêng. Project dependency tree không phải danh sách library của Maven plugins.

~~~xml
<plugin>
    <groupId>org.example</groupId>
    <artifactId>custom-maven-plugin</artifactId>
    <version>1.2.3</version>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>plugin-helper</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
</plugin>
~~~

Đoạn trên chỉ minh họa cú pháp, **không phải artifact có thật đã xác minh**.

Project tree:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Plugin dependencies resolution:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:resolve-plugins \
  -DoutputFile=target/resolved-plugins.txt
~~~

Goal `dependency:resolve-plugins` được Apache Maven mô tả là resolve project plugins/reporting plugins và dependencies của chúng. Nó có thể tải artifacts về local repository. **Resolved không chứng minh goal đã chạy**, và output không nhất thiết khám phá ngoài-repo core extensions hoặc plugin dynamic downloads.

---

## 8. Core extension khác build extension

### 8.1. Core extension ở .mvn/extensions.xml

Maven core extension có thể được nạp từ:

~~~text
.mvn/extensions.xml
~~~

Ví dụ **tùy chọn** (không nằm trong dự án Maven runnable phía dưới):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<extensions xmlns="http://maven.apache.org/EXTENSIONS/1.1.0">
    <extension>
        <groupId>org.apache.maven.extensions</groupId>
        <artifactId>maven-build-cache-extension</artifactId>
        <version>1.3.0</version>
    </extension>
</extensions>
~~~

Tài liệu Maven Build Cache Extension công bố version 1.3.0 và cơ chế khai. **Không bật extension chỉ để kiểm kê**: nó có thể thay caching/lifecycle behavior.

### 8.2. Core extension còn có thể inject từ environment

Tài liệu Maven Using Extensions đề cập:

- `.mvn/extensions.xml`.
- CLI `-Dmaven.ext.class.path=...`.
- Maven home `lib/ext` theo cơ chế/version.
- Các Maven launcher/IDE integrations.

Vì vậy kiểm file trong repo là cần nhưng **chưa đủ**. Ghi source file, Maven home, CLI/environment và startup debug evidence.

### 8.3. Build extensions

~~~xml
<build>
    <extensions>
        <extension>
            <groupId>org.example</groupId>
            <artifactId>build-support-extension</artifactId>
            <version>1.0.0</version>
        </extension>
    </extensions>
</build>
~~~

Đây là snippet giả để minh họa cấu trúc `build/extensions`.

### 8.4. Plugin với extensions=true

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.example</groupId>
            <artifactId>lifecycle-extension-plugin</artifactId>
            <version>1.0.0</version>
            <extensions>true</extensions>
        </plugin>
    </plugins>
</build>
~~~

Plugin này được đánh dấu mang extension, khác ordinary plugin chỉ chạy goal. Cần đọc docs/version compatibility của từng extension, đặc biệt nếu định nâng Maven3 lên Maven4: extensions dùng internal APIs/Resolver có nguy cơ break ngay lúc bootstrap.

---

## 9. Active profiles và effective settings

Maven Help Plugin có goal `help:active-profiles`:

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
~~~

Để xem profile release (chỉ khi repo có profile ấy):

~~~bash
mvn -Prelease org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
~~~

Effective POM cùng profile:

~~~bash
mvn -Prelease org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom \
  -Dverbose=true \
  -Doutput=target/effective-release-pom.xml
~~~

Không gọi một output mặc định là release inventory nếu `-Prelease` chưa được bật.

Settings ảnh hưởng mirror/repository/pluginRepositories/profiles:

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings
~~~

Cần tránh lưu raw settings ở kênh public; nó có thể mang private repository metadata hoặc credentials. Trong inventory, chỉ ghi các fields không nhạy cảm được tổ chức cho phép.

---

## 10. POM Maven3.9/Java17 runnable với Enforcer

Tạo ba file:

~~~text
maven-inventory-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/inventory/InventoryApp.java
    └── test/java/vn/example/inventory/InventoryAppTest.java
~~~

### 10.1. File pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>maven-inventory-demo</artifactId>
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
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.inventory.InventoryApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>verify-toolchain-baseline</id>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-help-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.11.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>versions-maven-plugin</artifactId>
                <version>2.25.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chú thích:

- Ba lifecycle plugins được quản lý version qua `pluginManagement` và khai usage dưới `plugins` không lặp version.
- Enforcer version3.6.3 với `requireMavenVersion` khóa baseline Maven3.9.x, không có nghĩa Maven4 bị lỗi với mọi dự án.
- `requireJavaVersion` kiểm Maven JVM 17+ theo rule, không tự xác minh mọi JDK/toolchain.
- JUnit Jupiter 5.11.4 là project test dependency, không phải plugin.
- Help/Dependency/Versions đã pin để dùng cho audit; riêng việc khai plugins **không tự chạy mọi báo cáo** ở `verify`.

### 10.2. File InventoryApp.java

~~~java
package vn.example.inventory;

import java.util.Locale;
import java.util.Objects;

public final class InventoryApp {
    private InventoryApp() {
    }

    public static String greeting(String name) {
        Objects.requireNonNull(name, "name");
        return "Hello, " + name.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println("MAVEN INVENTORY: " + greeting("java"));
    }
}
~~~

### 10.3. File InventoryAppTest.java

~~~java
package vn.example.inventory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class InventoryAppTest {
    @Test
    void formatsName() {
        assertEquals("Hello, JAVA", InventoryApp.greeting("java"));
    }

    @Test
    void rejectsNull() {
        assertThrows(
                NullPointerException.class,
                () -> InventoryApp.greeting(null)
        );
    }
}
~~~

Có **2 tests**. Java runtime main chỉ dùng standard library nên artifact JAR chạy được mà không cần thêm runtime JAR ngoài JDK.

### 10.4. Build và stdout

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
java -jar target/maven-inventory-demo-1.0.0.jar
~~~

Khi Maven3.9.x, JDK17+ và repositories có thể resolve plugin/dependency, dự kiến tests:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **mẫu kết quả kỳ vọng**, không phải kết quả thực thi được xác nhận. Stdout chính xác từ Java main:

~~~text
MAVEN INVENTORY: Hello, JAVA
~~~

---

## 11. Bản kê bằng các lệnh read-only/report

### 11.1. Maven runtime/JDK

~~~bash
mvn -version
java -version
javac -version
~~~

Ghi từng giá trị riêng. Maven version từ Wrapper nếu CI thực dùng Wrapper.

### 11.2. Active profile và effective POM

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom \
  -Dverbose=true -Doutput=target/effective-pom.xml
~~~

### 11.3. Project graph và plugin graph

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:resolve-plugins \
  -DoutputFile=target/resolved-plugins.txt
~~~

Phân biệt dependency tree của project với plugin dependencies. Goal resolve-plugins có thể tải artifacts dù không sửa source POM.

### 11.4. Candidate versions

MojoHaus Versions Plugin cung cấp read/report goals:

~~~bash
mvn org.codehaus.mojo:versions-maven-plugin:2.25.1:display-plugin-updates
mvn org.codehaus.mojo:versions-maven-plugin:2.25.1:display-extension-updates
mvn org.codehaus.mojo:versions-maven-plugin:2.25.1:display-parent-updates
mvn org.codehaus.mojo:versions-maven-plugin:2.25.1:display-property-updates
~~~

Lệnh `display-extension-updates` có tùy chọn `processBuildExtensions` và `processCoreExtensions`. Không xem report “không có update” là bằng chứng mọi extension ngoài-project đã được phát hiện.

**Quan trọng:** không chạy các goals thay POM như `versions:update-properties`, `versions:update-parent` hoặc `versions:use-latest-versions` nếu đang ở bước chỉ kiểm kê.

---

## 12. Script Python3 xuất CSV từ effective POM

Đây là file **tùy chọn bổ sung** để tự động hóa; không thuộc ba file bắt buộc của demo. Script đọc **một effective POM** và các file extensions/wrapper local nếu tồn tại. Nó dùng Python standard library; không tải dependency nào.

File `tools/inventory_versions.py`:

~~~python
#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET


def lname(tag):
    return tag.rsplit("}", 1)[-1]


def child(parent, name):
    if parent is None:
        return None
    return next(
        (item for item in parent if lname(item.tag) == name),
        None,
    )


def path(parent, *names):
    for name in names:
        parent = child(parent, name)
    return parent


def field(parent, name, fallback=""):
    node = child(parent, name)
    if node is None or node.text is None:
        return fallback
    return node.text.strip()


def elements(parent, name):
    if parent is None:
        return []
    return [x for x in parent if lname(x.tag) == name]


def plugin_rows(root, kind, *location):
    box = path(root, *location)
    for plugin in elements(box, "plugin"):
        yield [
            kind, "/".join(location),
            field(plugin, "groupId", "org.apache.maven.plugins"),
            field(plugin, "artifactId"),
            field(plugin, "version", "(implicit/unresolved)"),
            field(plugin, "extensions", "false"),
        ]


def extension_rows(root, kind, *location):
    box = path(root, *location)
    for ext in elements(box, "extension"):
        yield [
            kind, "/".join(location),
            field(ext, "groupId"),
            field(ext, "artifactId"),
            field(ext, "version", "(unresolved)"),
            "",
        ]


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python3 tools/inventory_versions.py "
            "target/effective-pom.xml"
        )

    root = ET.parse(sys.argv[1]).getroot()
    out = csv.writer(sys.stdout)
    out.writerow([
        "kind", "location", "groupId",
        "artifactId", "version", "extensionsFlag",
    ])

    for row in plugin_rows(root, "build-plugin",
                           "build", "plugins"):
        out.writerow(row)
    for row in plugin_rows(root, "managed-plugin",
                           "build", "pluginManagement", "plugins"):
        out.writerow(row)
    for row in plugin_rows(root, "reporting-plugin",
                           "reporting", "plugins"):
        out.writerow(row)
    for row in extension_rows(root, "build-extension",
                              "build", "extensions"):
        out.writerow(row)

    core = Path(".mvn/extensions.xml")
    if core.is_file():
        core_root = ET.parse(core).getroot()
        for ext in elements(core_root, "extension"):
            out.writerow([
                "core-extension", str(core),
                field(ext, "groupId"),
                field(ext, "artifactId"),
                field(ext, "version", "(unresolved)"), "",
            ])

    wrapper = Path(".mvn/wrapper/maven-wrapper.properties")
    if wrapper.is_file():
        for line in wrapper.read_text(
                encoding="utf-8").splitlines():
            if line.lstrip().startswith("distributionUrl="):
                url = line.partition("=")[2].strip()
                match = re.search(r"/apache-maven/([^/]+)/", url)
                version = match.group(1) if match else "(inspect URL)"
                out.writerow([
                    "wrapper-maven", str(wrapper), "",
                    "apache-maven", version, "",
                ])
                break


if __name__ == "__main__":
    main()
~~~

### 12.1. Chạy trên Bash

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom \
  -Dverbose=true \
  -Doutput=target/effective-pom.xml

python3 tools/inventory_versions.py target/effective-pom.xml \
  > target/version-inventory.csv
~~~

Windows PowerShell:

~~~powershell
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=target/effective-pom.xml
python tools/inventory_versions.py target/effective-pom.xml | Set-Content -Encoding UTF8 target/version-inventory.csv
~~~

Dữ liệu CSV có thể bao gồm:

~~~csv
kind,location,groupId,artifactId,version,extensionsFlag
managed-plugin,build/pluginManagement/plugins,org.apache.maven.plugins,maven-compiler-plugin,3.14.1,false
build-plugin,build/plugins,org.apache.maven.plugins,maven-enforcer-plugin,3.6.3,false
~~~

**Đây là hai dòng ví dụ, không phải toàn bộ output**. Effective POM có thể có entries kế thừa hoặc thứ tự khác.

### 12.2. Script kiểm được gì?

Nó trích:

- Plugin entries từ `build/plugins`.
- Plugin management từ `build/pluginManagement/plugins`.
- Reporting plugins.
- `build/extensions`.
- Core extension declarations trong `.mvn/extensions.xml`.
- Wrapper distribution version theo URL pattern (nếu file tồn tại).

### 12.3. Script không thể kết luận điều gì?

- Không tự biết Maven core/JDK runtime.
- Không biết JDK/toolchain được Maven Compiler thực chọn.
- Không xác định các plugin implicit lifecycle goals đã execute.
- Không resolve plugin dependencies/transitives.
- Không phát hiện Maven home/CLI/IDE injected extensions ngoài repo.
- Không biết file extension declaration có thực được load trong CI invocation khác hay không.
- Không kiểm kê toàn reactor nếu chỉ đưa một effective POM.
- Không tìm phiên bản mới nhất, không check security advisory.
- Không xác thực checksums/provenance của artifacts đã tải.

Đối với audit nghiêm túc, giữ **nhãn evidenceLevel=effective-model**, đồng thời thêm Maven -version, build goal logs và environment metadata riêng.

---

## 13. Multi-module: một repo có nhiều danh mục

Ví dụ:

~~~text
parent/pom.xml
  +-- common/pom.xml
  +-- api/pom.xml
  +-- worker/pom.xml
  +-- custom-extension/pom.xml
~~~

Parent có thể pin Surefire 3.5.4 nhưng `worker` override thành version khác. Nếu chỉ đọc root POM và ghi “Surefire toàn repo 3.5.4” thì sai.

### 13.1. Đúng module, đúng profile

Có thể chạy Help goal tại module directory hoặc từ reactor root theo `-pl`/`-am` phù hợp. `help:effective-pom` là aggregator goal nên xử lý/output nhiều projects có thể khác tùy cách gọi; kiểm đúng output file thuộc module cần audit.

### 13.2. CI matrix

Một CI matrix Java17/Linux và Java21/Windows là hai environments khác. Ghi job URL, OS, JDK, Maven launcher và goals để không gộp sai data.

### 13.3. Profiles

Profile có thể thêm plugins/extensions hoặc đổi versions. Phải thu effective POM với cùng `-P`/settings/profile activation của build thực.

### 13.4. Reactor subset

`-pl :api -am` có thể chỉ xây một phần reactor. Execution logs của subset không chứng minh plugins của mọi module khác. Ghi target modules và command chính xác.

---

## 14. CI workflow giữ evidence qua clean

Ví dụ GitHub Actions dùng Maven sẵn có trên runner; nếu repo có Wrapper, nên thay `mvn` bằng `./mvnw` **nhất quán**.

File `.github/workflows/version-inventory.yml`:

~~~yaml
name: Maven version baseline

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Setup Java 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Capture runtime
        run: |
          mkdir -p audit
          mvn -version | tee audit/maven-version.txt
          java -version 2>&1 | tee audit/java-version.txt
          javac -version 2>&1 | tee audit/javac-version.txt

      - name: Build and test
        run: mvn -B -ntp clean verify

      - name: Capture effective POM
        if: always()
        run: >
          mvn -B -ntp
          org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
          -Dverbose=true
          -Doutput=audit/effective-pom.xml

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: maven-version-evidence
          path: |
            audit/
            target/surefire-reports/
          if-no-files-found: warn
~~~

### 14.1. Tại sao xuất audit/?

Nếu xuất effective POM vào `target/effective-pom.xml` **trước** `mvn clean verify` thì phase clean có thể xóa file đó. Workflow trên dùng `audit/` nằm ngoài target và xuất **sau build**, tránh mất file do clean.

### 14.2. if: always() không che lỗi

Khi Maven build fail, CI vẫn cố gắng thu model và reports. Điều này không biến build fail thành pass, nhưng Help goal cũng có thể fail nếu repository/config lỗi. Cần giữ logs và xem artifact có thật hay không.

### 14.3. Những dữ liệu workflow chưa tự thu

- Actual executed plugin goal versions ở dạng CSV.
- Outside-project core extensions từ Maven home/CLI.
- Selected Toolchains JDK.
- Full reactor plugin versions khi chỉ build một module.

Bổ sung những nguồn trên khi phải audit sâu.

### 14.4. Không lộ bí mật

`settings.xml`, debug `-X` logs hoặc effective settings có thể chứa private repository URLs, server IDs và credentials tùy config/plugin. Không upload raw data công khai; dùng access control, sanitization và retention policy.

---

## 15. Enforcer là guardrail, không phải inventory

POM demo dùng:

~~~xml
<requireMavenVersion>
    <version>[3.9,4.0)</version>
</requireMavenVersion>
<requireJavaVersion>
    <version>[17,)</version>
</requireJavaVersion>
~~~

Maven Enforcer Plugin 3.6.3 `enforcer:enforce` khi được bind trong build sẽ fail nếu Maven/JDK ngoài range. Điều này hỗ trợ baseline migration nhưng **không tự kê plugin/core extension versions**.

Khi cần thử Maven4, đổi range ở nhánh kiểm chứng sau compatibility review; không tắt Enforcer trên release CI chỉ để tạo `BUILD SUCCESS`.

---

## 16. Quy trình nâng cấp từ inventory

1. **Đóng băng baseline:** commit, Maven wrapper, Maven JVM JDK, toolchain, profiles, plugin/extension GAV và executed goals.
2. **Kiểm current/target:** dùng Versions Plugin read reports và release notes.
3. **Rà core extensions:** ưu tiên các component tích hợp sâu với Resolver/lifecycle.
4. **Giữ các trục độc lập:** thử Maven core mới với plugin versions đang dùng trước; nếu fail tìm plugin incompatible.
5. **Kiểm JDK requirements:** một plugin mới có thể đòi JDK khác với `maven.compiler.release`.
6. **Chạy full suite:** compile/tests/package/integration/plugin custom goals theo profile thực.
7. **So inventory trước–sau:** cùng source/modules/profiles; nêu mọi thay đổi không chủ ý.
8. **Phê duyệt:** quyết định target version dựa trên compatibility/security/test evidence.

Bảng quản trị:

| Loại | Current | Candidate | Rủi ro cần kiểm |
| --- | --- | --- | --- |
| Maven core | Measured version | Target release | Plugin/Core API và Resolver |
| Maven Wrapper | distributionUrl | Pin bản mới | Download checksum/source |
| Maven JVM | Vendor/major/patch | Target JDK | Plugin min-JDK |
| Compiler Plugin | Effective/executed | Candidate | --release/toolchain |
| Surefire/Failsafe | Effective/executed | Candidate | JUnit provider/fork behavior |
| Core extension | GAV + origin | Supported extension | Bootstrap/runtime hooks |
| Build extension | GAV + role | Supported extension | Artifact handler/lifecycle |

---

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `mvn` khác `./mvnw` | PATH Maven khác Wrapper | Dùng đúng launcher CI |
| Maven JDK khác `java -version` | JAVA_HOME/launcher override | Tin `mvn -version` của job |
| Javac PATH khác compiler dùng | Toolchains | Log selected JDK |
| POM không có plugin version | Parent/pluginManagement/default mapping | Effective POM + execution log |
| Managed plugin không có trong logs | Chưa execute goal/phase | Ghi managed, không executed |
| dependency:tree không có plugin helper | Project graph khác plugin graph | resolve-plugins |
| Core extension không ở POM | .mvn/extensions.xml/CLI/Maven home | Startup evidence |
| Versions report không có updates | Offline/mirror/filter | Kiểm metadata/reachability |
| Plugin version mới nhưng không compatible | Maven/JDK requirements | Read changelog, thử matrix |
| Enforcer chặn Maven4 | Range baseline `[3.9,4.0)` | Migration branch policy |
| File effective POM bị mất | Xuất vào target trước clean | Xuất ngoài target/sau build |
| CI artifacts có private URL | Dump hiệu lực quá rộng | Redact/access control |
| Root inventory khác child | Overrides/profiles | Per-module collection |
| Cache hit nhưng versions khác | Stale/changed resolution/environment | Check logs/current job |
| Wrapper có properties nhưng không có mvnw | Wrapper chưa cài scripts | Cài wrapper đúng, không giả có lệnh |

---

## 18. Bài tập thực hành

### Bài 1 — Launcher

Chạy `mvn -version` và `./mvnw -version` (repo có Wrapper). Khi khác nhau, version nào là bằng chứng CI chạy Wrapper?

### Bài 2 — Java runtime

So Maven JVM Java version, `java -version` và `javac -version`. Chúng có bắt buộc trùng không?

### Bài 3 — Release target

Vì sao `maven.compiler.release=17` không chứng minh Maven JVM sử dụng JDK17?

### Bài 4 — Build mẫu

Tạo ba file demo, chạy `mvn -B -ntp clean verify`. Xác nhận 2 tests PASS và stdout `MAVEN INVENTORY: Hello, JAVA`.

### Bài 5 — Managed version

Trong demo, Compiler version ở `pluginManagement` nhưng usage ở `build/plugins`. Khi nào nó được execute?

### Bài 6 — Effective POM

Chạy `-Dverbose=true` và tìm nguồn plugin version; khi parent/child khác nhau, bản effective có ích thế nào?

### Bài 7 — Lifecycle

Một plugin không khai version trực tiếp nhưng log cho thấy goal chạy. Cần bằng chứng nào trước khi ghi version current?

### Bài 8 — Project vs plugin graphs

Chạy `dependency:tree` và `dependency:resolve-plugins`. Vì sao outputs khác nhau?

### Bài 9 — Core extension

Kiểm `.mvn/extensions.xml` và `maven.ext.class.path`. Vì sao inventory cần cả project config và environment?

### Bài 10 — Build extension

Plugin có `extensions=true` khác ordinary plugin thế nào khi nâng Maven?

### Bài 11 — Versions Plugin

Giải thích output `display-plugin-updates`/`display-extension-updates` là candidate, không phải executed version.

### Bài 12 — Python CSV

Chạy script `tools/inventory_versions.py`, tìm các records và liệt kê những thông tin script không thể tự xác định.

### Bài 13 — Multi-module

Một child module override Surefire. Vì sao không gộp về một row chung của toàn repository?

### Bài 14 — CI evidence

Vì sao không nên xuất `target/effective-pom.xml` trước `mvn clean verify` rồi mong file còn sau build?

### Bài 15 — Toolchain

Maven chạy JDK21, compile bằng Toolchains JDK17. Inventory phải ghi mấy version JDK riêng?

### Bài 16 — Enforcer

Vì sao Maven4 bị Enforcer chặn theo rule bài tập không chứng minh Maven4 không hỗ trợ project?

### Bài 17 — Confidentiality

Khi lưu effective settings/logs, cần che thông tin nào mà vẫn giữ được repository identity hữu ích?

### Bài 18 — Migration plan

Thiết kế baseline/current/candidate và CI matrix cho Maven/JDK/plugins/extensions, thử một trục một lượt.

---

## 19. Checklist kiểm kê xong

- [ ] Ghi repo, commit SHA, module, profile, environment, CI job.
- [ ] Ghi Maven launcher, Maven core version và Maven home.
- [ ] Ghi Wrapper configured version/checksum nếu có.
- [ ] Ghi JVM Maven JDK vendor/version/path.
- [ ] Không nhầm shell Java/Javac với Maven/toolchain.
- [ ] Ghi Compiler release target và selected toolchain evidence.
- [ ] Tách plugin build, pluginManagement, reporting.
- [ ] Thu effective POM đúng active profiles và source version.
- [ ] Thu actual executed plugin versions/goals từ build logs.
- [ ] Phân biệt project dependencies và plugin dependencies.
- [ ] Quét .mvn/extensions.xml và build/extensions.
- [ ] Kiểm plugin extensions flag và core extension injection ngoài POM.
- [ ] Ghi unknown/unverified fields rõ ràng.
- [ ] Không coi candidate versions là versions đang dùng.
- [ ] Không chạy update goals ở bước audit.
- [ ] Không upload secrets/credentials/debug logs vô kiểm soát.
- [ ] Lưu test counts/build result làm baseline.
- [ ] So sánh trước/sau migration trên cùng module/profile/goal.

**Kết luận:** Danh mục trước nâng cấp Maven phải chỉ rõ **Maven core/Wrapper, Maven JVM JDK và Toolchains, plugins được khai–quản lý–hiệu lực–thực thi, cùng core/build extensions**. `pom.xml` không đủ; phải kết hợp `mvn -version`, Help Plugin effective POM/active profiles, Dependency Plugin resolve-plugins, actual build logs và các nguồn extension ngoài project. Khi mỗi dòng có evidence và scope, bạn mới có thể nâng Maven/JDK có kiểm soát, tìm regression và chứng minh CI đúng phiên bản.

## 20. Tài liệu chính thức

- [Apache Maven 3.9.12 Release Notes](https://maven.apache.org/docs/3.9.12/release-notes.html): Maven core release độc lập plugin releases.
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/): scripts, distribution URL, checksum.
- [Apache Maven — Using Extensions](https://maven.apache.org/guides/mini/guide-using-extensions.html): core/build extensions.
- [Maven Build Cache Extension](https://maven.apache.org/extensions/maven-build-cache-extension/): ví dụ core extension.
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): model hiệu lực và origin.
- [Maven Help Plugin — active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html): profiles đang active.
- [Maven Dependency Plugin — resolve-plugins](https://maven.apache.org/plugins/maven-dependency-plugin/resolve-plugins-mojo.html): plugin resolution.
- [Maven Dependency Plugin — tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): project graph.
- [MojoHaus Versions Plugin — Plugin Info](https://www.mojohaus.org/versions/versions-maven-plugin/plugin-info.html): display update goals.
- [Apache Maven Enforcer — requireMavenVersion](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html): Maven baseline rule.
- [Apache Maven Enforcer — requireJavaVersion](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html): JDK baseline rule.
- [Apache Maven POM Reference](https://maven.apache.org/pom.html): parent/profiles/build/plugins/reporting.
- [Apache Maven — Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html): Maven runtime vs compiler toolchain.
