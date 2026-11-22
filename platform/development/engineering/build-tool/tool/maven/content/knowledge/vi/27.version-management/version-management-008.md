# Vai trò của Flatten Maven Plugin khi cần POM cho bên tiêu thụ

## 1. Vấn đề: build POM và consumer POM có nhu cầu khác nhau

Trong dự án Maven, file `pom.xml` thường chứa cả thông tin **để xây dựng artifact** và **để dự án khác sử dụng artifact**. Người phát triển cần parent POM, plugin, profiles, compiler settings, release process và các biến phiên bản như `${revision}`. Người sử dụng thư viện (consumer) thường cần `groupId:artifactId:version`, loại artifact, dependencies có version hợp lệ, scopes, exclusions và metadata phát hành.

Nếu publish nguyên một POM còn phụ thuộc vào parent nội bộ chưa được phát hành hoặc một biến version do CI cung cấp riêng, consumer có thể báo lỗi dù file JAR tải được. **Flatten Maven Plugin** của MojoHaus giúp tạo một **flattened POM** đã xử lý những chi tiết chỉ phục vụ build và chuẩn hóa thông tin thiết yếu cho consumer.

Plugin có hai mục tiêu cốt lõi:

- `flatten:flatten`: tạo file POM đã làm phẳng, mặc định tên `.flattened-pom.xml`, và tùy `updatePomFile` có thể chuyển tham chiếu POM của MavenProject sang file này.
- `flatten:clean`: dọn generated flattened POM.

Khi plugin được cấu hình đúng và chạy **trước** `install`/`deploy`, Maven có thể đưa flattened POM lên repository cùng binary artifact. Plugin không tự đổi bytecode, không gộp JAR, không xuất bản nếu không có `install`/`deploy`, không thay thế Maven Versions Plugin hoặc dependency scanner.

### Mục tiêu sau bài học

1. Phân biệt source/build POM, effective POM và POM thực tế trong artifact repository.
2. Hiểu Maven CI-friendly versions `${revision}`, `${sha1}`, `${changelist}` và lý do chúng liên quan đến publish POM.
3. Cấu hình `flatten-maven-plugin` trong lifecycle, `updatePomFile` và cleanup.
4. Biết chọn `flattenMode=defaults`, `oss`, `ossrh`, `bom`, `resolveCiFriendliesOnly`, `clean` hoặc `fatjar`.
5. Phân biệt `flattenDependencyMode=direct`, `inherited` và `all`.
6. Hiểu rủi ro khi xuất bản BOM hoặc parent POM bị loại mất thông tin.
7. Tạo library Java 17 dùng CI-friendly version, kiểm tra generated POM và installed POM.
8. Viết consumer Maven project riêng chỉ khai GAV thư viện, chạy Java và xác nhận transitive dependency.
9. Xác định lỗi repository POM, profile, GAV, parent, dependencyManagement và Maven 4 differences.
10. Biết bộ kiểm tra cần thực hiện trước một release.

## 2. Ba loại POM: đừng nhầm mục đích

### 2.1. Build POM (source pom.xml)

Đây là file developer commit lên Git và trực tiếp chỉnh sửa. Nó có thể chứa:

~~~xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>dev.example</groupId>
  <artifactId>greeting-lib</artifactId>
  <version>${revision}</version>
  <properties>
    <revision>1.4.2</revision>
    <commons.version>3.17.0</commons.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.commons</groupId>
      <artifactId>commons-lang3</artifactId>
      <version>${commons.version}</version>
    </dependency>
  </dependencies>
  <!-- build/plugins/profiles ... -->
</project>
~~~

Đây là **fragment minh họa**; POM đầy đủ runnable có ở mục 8. `${revision}` dùng cho CI-friendly project version, còn `${commons.version}` là interpolation Maven property thông thường. Khi producer đang build, Maven có thể giải cả hai. Nhưng nếu consumer đọc một POM đã phát hành mà các placeholders hoặc parent còn phụ thuộc môi trường build, artifact có thể không dùng được.

### 2.2. Effective POM

Maven kết hợp POM nguồn với parent, Super POM, active profiles, defaults, dependencyManagement và properties để xây **effective model** phục vụ phiên build hiện tại. Bạn có thể xuất:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Doutput=effective-pom.xml
~~~

Effective POM là công cụ debug build; nó **không mặc nhiên chính là POM được cài vào local/remote repository**. Nó có thể chứa nhiều plugin/build config mà consumer không cần.

### 2.3. Flattened/consumer POM

Generated POM có thể giống sơ đồ sau:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>dev.example</groupId>
  <artifactId>greeting-lib</artifactId>
  <version>1.4.2</version>
  <packaging>jar</packaging>
  <dependencies>
    <dependency>
      <groupId>org.apache.commons</groupId>
      <artifactId>commons-lang3</artifactId>
      <version>3.17.0</version>
    </dependency>
  </dependencies>
</project>
~~~

Đây chỉ là **minh họa các trường cần thiết**, không phải một file output được khẳng định byte-for-byte. Mode khác nhau sẽ giữ/bỏ những elements khác nhau, chẳng hạn licenses, SCM, repositories, properties và dependencyManagement.

Điểm quan trọng: `version` của artifact đã thành `1.4.2` và dependency version thành `3.17.0`, thay vì buộc consumer biết `revision` hoặc `commons.version` trong context của producer.

### 2.4. Sơ đồ pipeline

~~~text
source pom.xml
  |
  +--> Maven build/effective model --> compiler/test/package --> library.jar
  |
  +--> flatten:flatten  --> .flattened-pom.xml
                                  |
                        updatePomFile=true
                                  |
                                  v
                       MavenProject.file reference
                                  |
                             install/deploy
                                  |
                     repository .pom + .jar
                                  |
                                  v
                         consumer Maven build
~~~

`updatePomFile` cập nhật **MavenProject POM file reference** cho session, không mở và ghi đè nội dung `pom.xml` nguồn. Đây không phải plugin để chỉnh `<version>` của source POM.

## 3. Vì sao Maven cần POM phát hành riêng?

### 3.1. CI-friendly project version placeholders

Maven 3.5+ cho phép tên property đặc biệt trong `project.version` như:

~~~xml
<version>${revision}</version>
~~~

hoặc kết hợp `revision`, `sha1`, `changelist`. Với phiên bản được đặt qua:

~~~xml
<properties>
  <revision>1.4.2</revision>
</properties>
~~~

hay CLI:

~~~bash
mvn -B -ntp -Drevision=1.4.3-SNAPSHOT clean package
~~~

producer build có thể xác định version. Nhưng một POM được publish với `<version>${revision}</version>` mà consumer không có property cần thiết **không phải metadata an toàn cho phát hành**. Maven CI Friendly guide khuyến nghị dùng Flatten Plugin trong quy trình install/deploy cho các setup như vậy.

Không dùng một key tùy ý như `${myVersion}` ở project version rồi mặc định nó có semantics CI-friendly tương tự. Ngoài ra, inter-module dependencies có quy tắc riêng; với multi-module, Maven docs hướng dẫn dùng `${project.version}` ở những vị trí phù hợp.

### 3.2. Parent POM chỉ dành cho build và không có ở repository

Source project có thể dùng:

~~~xml
<parent>
  <groupId>dev.example.build</groupId>
  <artifactId>internal-parent</artifactId>
  <version>42</version>
</parent>
~~~

Nếu consumer POM còn parent GAV này mà repository bên tiêu thụ không truy cập được parent, Maven có thể báo `Non-resolvable parent POM`. Với ordinary library, flatten có thể loại parent sau khi giải các inherited values cần thiết. Nhưng với artifact mà **chính nó là một published parent POM**, xóa `build`/`properties`/`pluginManagement` có thể phá vỡ inheritance contract. Không chọn một mode flatten cho mọi loại POM.

### 3.3. Dependency version và metadata có thể thiếu

Nếu library nguồn dùng `dependencyManagement`, imported BOM, inherited dependencies hoặc version properties, POM dành cho consumer phải mô tả graph đúng. Nếu flatten làm mất một version hoặc bỏ dependency cần ở runtime, người dùng có thể gặp `Could not resolve dependencies` hoặc `NoClassDefFoundError` khi gọi code. Do đó **tên plugin không phải bằng chứng output đúng**; phải đọc generated/installed POM và thử một consumer ngoài reactor.

### 3.4. Build-only plugins không cần truyền cho người dùng thư viện

Maven Compiler Plugin, Surefire, Javadoc, Source Plugin, Jacoco, release profiles và code-format rules chủ yếu để phát triển artifact; chúng thường không cần có trong POM một ordinary library consumer. Tuy nhiên `licenses`, `developers`, `scm` và `description` có thể vẫn rất cần cho public repository policy. Đây là lý do `flattenMode` phải được chọn theo loại artifact và target repository.

## 4. Plugin và lifecycle

Tọa độ plugin:

~~~text
org.codehaus.mojo:flatten-maven-plugin
~~~

Bài dùng **1.8.0** để thống nhất với tài liệu chính thức đã kiểm tra. Version mới có thể xuất hiện; khi nâng hãy đọc release notes và đối chiếu generated POM. Không tự giả định default mọi phiên bản giống nhau.

POM fragment thường dùng:

~~~xml
<plugin>
  <groupId>org.codehaus.mojo</groupId>
  <artifactId>flatten-maven-plugin</artifactId>
  <version>1.8.0</version>
  <configuration>
    <flattenMode>defaults</flattenMode>
    <updatePomFile>true</updatePomFile>
  </configuration>
  <executions>
    <execution>
      <id>flatten</id>
      <phase>process-resources</phase>
      <goals><goal>flatten</goal></goals>
    </execution>
    <execution>
      <id>flatten-clean</id>
      <phase>clean</phase>
      <goals><goal>clean</goal></goals>
    </execution>
  </executions>
</plugin>
~~~

Vì sao:

- `process-resources` được chạy **trước install/deploy** trong default lifecycle, nên flattened POM sẵn sàng khi Maven phát hành.
- `updatePomFile=true` cho phép MavenProject dùng generated file cho publishing. Với `packaging=jar` đây thường là default, nhưng ghi rõ giúp dễ audit.
- `flatten:clean` dọn `.flattened-pom.xml` ở basedir. Clean Plugin bình thường chủ yếu dọn `target`.
- `.flattened-pom.xml` mặc định nằm cạnh source `pom.xml`; có thể đổi qua `flattenedPomFilename`/`outputDirectory`, nhưng cần đồng bộ clean và CI.

`mvn flatten:flatten` chỉ tạo POM, không tự install/deploy. Muốn consumer resolve qua Maven repository, chạy `mvn install` hoặc `mvn deploy` trong build được cấu hình đúng.

### 4.1. Source POM không bị thay thế trên disk

Ví dụ source tree:

~~~text
greeting-lib/
├── pom.xml                 (source-of-truth, giữ nguyên)
├── .flattened-pom.xml      (generated)
├── src/
└── target/
    └── greeting-lib-1.4.2.jar
~~~

`updatePomFile` không đồng nghĩa `mvn versions:set`. Có thể đặt `.flattened-pom.xml` vào `.gitignore` vì đây là generated file:

~~~gitignore
.flattened-pom.xml
~~~

Nếu tổ chức chủ động version-control generated POM thì phải có chính sách đối chiếu; không commit cả hai file rồi để lệch nhau sau một lần đổi version.

## 5. flattenMode: giữ và bỏ những elements nào?

| `flattenMode` | Ý nghĩa theo MojoHaus 1.8.0 | Khi cân nhắc |
| --- | --- | --- |
| `defaults` | Bỏ phần lớn optional elements, giữ repositories theo định nghĩa mode | Consumer POM đơn giản, thường dùng trong internal build |
| `clean` | Bỏ toàn bộ optional elements được mode kiểm soát | Cực tối giản, dễ mất release metadata |
| `oss` | Giữ optional elements hữu ích cho OSS, trừ repositories và pluginRepositories | Public libraries cần metadata dự án |
| `ossrh` | Giữ optional elements thường cần cho OSS repository hosting | Khi repository đòi licenses, SCM, developers |
| `bom` | Như ossrh, nhưng giữ dependencyManagement và properties | BOM packaging=pom được downstream import |
| `fatjar` | Bỏ optional elements và dependencies | Chỉ nếu artifact thật sự self-contained và consumer không cần dependencies |
| `resolveCiFriendliesOnly` | Chỉ xử lý revision/sha1/changelist, giữ phần còn lại | Cần sửa CI-friendly placeholders mà không flatten cấu trúc khác |

### 5.1. defaults và public publishing

Với `defaults`, POM có thể thiếu `licenses`, `scm`, `developers` hoặc `description`. Nhiều public repositories cần những trường này. Producer build xanh không chứng minh metadata đáp ứng release policy. Cân nhắc `oss` hoặc `ossrh`, rồi kiểm tra **published POM** và chính sách repository.

### 5.2. resolveCiFriendliesOnly

~~~xml
<configuration>
  <flattenMode>resolveCiFriendliesOnly</flattenMode>
  <updatePomFile>true</updatePomFile>
</configuration>
~~~

Mode này chủ yếu thay `${revision}`/`${sha1}`/`${changelist}` ở nơi tương ứng, giữ POM elements khác, gồm parent/build/dependencyManagement. Nó **không** bảo đảm xóa references tới một internal build parent. Dùng khi bạn cần đúng version nhưng vẫn muốn bảo toàn hợp đồng cấu hình build/parent.

### 5.3. fatjar không dành cho một library thông thường

Nếu library JAR còn gọi một external library nhưng `flattenMode=fatjar` làm consumer POM **không công bố dependency**, downstream có thể compile nhưng fail khi thực thi. Chỉ chọn khi binary thật sự đã chứa hoặc tự quản lý dependencies và bạn đã kiểm tra behavior ngoài reactor. Không dùng mode để “giảm kích thước POM” khi không hiểu graph.

## 6. flattenDependencyMode khác flattenMode

`flattenMode` quyết định **những phần tử POM nào còn lại**. `flattenDependencyMode` quyết định **độ sâu chuẩn hóa dependencies**.

| Mode | Ý nghĩa |
| --- | --- |
| `direct` | Chỉ xử lý direct dependencies, không kéo inherited dependencies từ parent thành direct |
| `inherited` | Xử lý direct + inherited dependencies; theo tài liệu 1.8.0 là default |
| `all` | Ngoài direct/inherited, kéo transitive dependencies thành direct với resolved versions |

Ví dụ:

~~~xml
<configuration>
  <flattenMode>defaults</flattenMode>
  <flattenDependencyMode>inherited</flattenDependencyMode>
</configuration>
~~~

`all` có thể hữu ích nếu library phụ thuộc dependencyManagement phức tạp, nhưng nó cũng thay đổi cách graph được thể hiện cho consumers. Đừng dùng `all` mặc định nếu không hiểu `optional`, scopes, exclusions và dependency mediation. Với một dependency `provided` hoặc `test`, cách nó được tiêu thụ khác với `compile`.

**Phân biệt:** `dependencyManagement` chỉ quản lý version/constraints; nó **không tự tạo dependency** trong graph. Một POM flattened phải thể hiện đúng các dependencies thật, không copy mọi managed entry như direct dependency khi không cần.

## 7. Lab đầy đủ: publish local library Java 17, consumer chạy độc lập

Mục tiêu: Producer có version `${revision}`, POM được flatten thành version `1.4.2` và dependency version resolved. Một **consumer project riêng** chỉ khai `dev.example:greeting-lib:1.4.2` rồi chạy được mà không phải khai trực tiếp Commons Lang.

### 7.1. Điều kiện và cấu trúc

Yêu cầu JDK 17+, Maven 3.9.x, Maven Central/mirror để tải dependencies/plugins. Không cần database, Docker, web server hoặc credentials.

~~~text
flatten-consumer-lab/
├── greeting-lib/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/example/greeting/Greeting.java
│       └── test/java/dev/example/greeting/GreetingTest.java
└── consumer-app/
    ├── pom.xml
    └── src/main/java/dev/consumer/ConsumerMain.java
~~~

**Không** khai `consumer-app` thành reactor module của producer ở lab; chúng phải trao đổi qua **local Maven repository** sau `mvn install` để thực sự kiểm chứng POM mà consumer nhận.

### 7.2. greeting-lib/pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>greeting-lib</artifactId>
    <version>${revision}</version>
    <packaging>jar</packaging>

    <properties>
        <revision>1.4.2</revision>
        <commons.version>3.17.0</commons.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>${commons.version}</version>
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
                <version>3.14.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>flatten-maven-plugin</artifactId>
                <version>1.8.0</version>
                <configuration>
                    <flattenMode>defaults</flattenMode>
                    <flattenDependencyMode>inherited</flattenDependencyMode>
                    <updatePomFile>true</updatePomFile>
                </configuration>
                <executions>
                    <execution>
                        <id>flatten</id>
                        <phase>process-resources</phase>
                        <goals>
                            <goal>flatten</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>flatten-clean</id>
                        <phase>clean</phase>
                        <goals>
                            <goal>clean</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Phân tích:** `revision=1.4.2` chọn phiên bản artifact; `commons.version` chọn dependency version; JUnit `scope=test` không truyền sang consumer runtime; Flatten Plugin chạy `process-resources` và sử dụng output cho install. `defaults` chỉ phù hợp bài demo nội bộ; khi publish public nên đánh giá `oss`/`ossrh` và metadata.

### 7.3. Greeting.java

`greeting-lib/src/main/java/dev/example/greeting/Greeting.java`:

~~~java
package dev.example.greeting;

import org.apache.commons.lang3.StringUtils;

public final class Greeting {
    private Greeting() {
    }

    public static String hello(String name) {
        String safe = StringUtils.isBlank(name)
                ? "world"
                : StringUtils.capitalize(name.trim());
        return "Hello, " + safe + "!";
    }
}
~~~

`StringUtils` đến từ Commons Lang, **không thuộc JDK**. `Greeting.hello(" maven ")` trả `Hello, Maven!`.

### 7.4. GreetingTest.java

`greeting-lib/src/test/java/dev/example/greeting/GreetingTest.java`:

~~~java
package dev.example.greeting;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingTest {

    @Test
    void formatsNames() {
        assertEquals("Hello, Maven!", Greeting.hello(" maven "));
        assertEquals("Hello, world!", Greeting.hello(null));
    }
}
~~~

Một test method có hai assertions. Nó kiểm tra library logic, **chưa kiểm tra downstream consumer POM**.

### 7.5. Producer: clean install

Trong thư mục `greeting-lib`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean install
~~~

Dấu hiệu Maven log dự kiến khi hoàn tất:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

File được sinh:

~~~text
greeting-lib/
├── pom.xml
├── .flattened-pom.xml
└── target/greeting-lib-1.4.2.jar
~~~

`.flattened-pom.xml` mặc định ở **project basedir**, không nằm dưới target. Kiểm tra generated POM:

~~~bash
cat .flattened-pom.xml
~~~

Trong Windows PowerShell:

~~~powershell
Get-Content .flattened-pom.xml
~~~

Tìm:
- `groupId=dev.example`, `artifactId=greeting-lib`, `version=1.4.2`.
- Dependency Commons Lang có version `3.17.0`, không còn `${commons.version}`.
- Nếu JUnit test dependency vẫn hiện, scope phải là `test`, không thành compile/runtime.
- Build plugins không cần thiết có thể bị loại theo `defaults`.

Không khẳng định XML phải giống một chuỗi mẫu hoàn toàn; mode/plugin version có thể thay cách sắp xếp hoặc giữ metadata khác.

### 7.6. Kiểm tra installed POM thật

Nếu dùng local repository mặc định:

~~~text
~/.m2/repository/dev/example/greeting-lib/1.4.2/
├── greeting-lib-1.4.2.jar
└── greeting-lib-1.4.2.pom
~~~

Linux/macOS:

~~~bash
cat "$HOME/.m2/repository/dev/example/greeting-lib/1.4.2/greeting-lib-1.4.2.pom"
~~~

PowerShell:

~~~powershell
Get-Content "$HOME\.m2\repository\dev\example\greeting-lib\1.4.2\greeting-lib-1.4.2.pom"
~~~

Đường dẫn thay đổi nếu `settings.xml` cấu hình `localRepository` riêng. Có thể hỏi Maven qua Help Plugin:

~~~bash
mvn -q -DforceStdout help:evaluate -Dexpression=settings.localRepository
~~~

**Installed POM là bằng chứng quan trọng**: nếu `.flattened-pom.xml` đúng nhưng repository POM vẫn còn `${revision}` hoặc build-only parent, kiểm tra `updatePomFile`, phase binding và `packaging` trước khi tuyên bố đã publish đúng.

### 7.7. Consumer pom.xml đầy đủ

`consumer-app/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.consumer</groupId>
    <artifactId>consumer-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>greeting-lib</artifactId>
            <version>1.4.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Consumer **không khai `commons-lang3` trực tiếp**. Nếu installed POM của `greeting-lib` có compile dependency đúng, Maven sẽ resolve Commons Lang **transitively**.

### 7.8. ConsumerMain.java

`consumer-app/src/main/java/dev/consumer/ConsumerMain.java`:

~~~java
package dev.consumer;

import dev.example.greeting.Greeting;

public final class ConsumerMain {
    private ConsumerMain() {
    }

    public static void main(String[] args) {
        System.out.println("CONSUMER OK: "
                + Greeting.hello(" maven "));
    }
}
~~~

Main class không import Commons Lang, nhưng producer code dùng `StringUtils` khi chạy. Điều đó khiến transitive dependency metadata của library trở nên có thể kiểm chứng.

### 7.9. Build và chạy consumer độc lập

Trong **thư mục `consumer-app`**, không phải `greeting-lib`:

~~~bash
mvn -B -ntp compile
mvn -B -ntp org.codehaus.mojo:exec-maven-plugin:3.6.4:java -Dexec.mainClass=dev.consumer.ConsumerMain
~~~

Exec Maven Plugin chạy class với classpath Maven dependencies của consumer. Maven có thể in nhiều INFO lines; **dòng stdout của ứng dụng** dự kiến chính xác:

~~~text
CONSUMER OK: Hello, Maven!
~~~

Nếu consumer chạy được, ta chứng minh thư viện `dev.example:greeting-lib:1.4.2` và dependency Commons Lang có thể được Maven dùng **qua installed POM**, chứ không cần source project producer trong cùng reactor.

### 7.10. Kiểm tra dependency graph của consumer

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Cấu trúc mong đợi:

~~~text
dev.consumer:consumer-app:jar:1.0.0
\- dev.example:greeting-lib:jar:1.4.2:compile
   \- org.apache.commons:commons-lang3:jar:3.17.0:compile
~~~

Đây là hình dung các dòng cốt lõi, Maven log thật có thể thêm INFO prefixes. Không mong JUnit Jupiter scope test của producer xuất hiện như runtime transitive dependency của consumer.

### 7.11. Tùy chọn chạy bằng java launcher

Sau `mvn compile` ở consumer, bạn có thể copy runtime dependencies:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/lib
~~~

POSIX:

~~~bash
java -cp 'target/classes:target/lib/*' dev.consumer.ConsumerMain
~~~

Windows PowerShell:

~~~powershell
java -cp "target\classes;target\lib\*" dev.consumer.ConsumerMain
~~~

Cả hai dự kiến in:

~~~text
CONSUMER OK: Hello, Maven!
~~~

Classpath separator là `:` trên Linux/macOS và `;` trên Windows. `lib/*` là Java launcher wildcard cho những JAR trực tiếp trong thư mục, không tự tìm vô hạn subdirectories.

### 7.12. Đổi version bằng CLI

Tại producer:

~~~bash
mvn -B -ntp clean install -Drevision=1.4.3-SNAPSHOT
~~~

GAV của artifact mới thành `dev.example:greeting-lib:1.4.3-SNAPSHOT`. Consumer POM đang khai `1.4.2` **không tự nâng cấp**; nếu muốn dùng bản mới, đổi dependency version ở consumer rồi build lại. Flatten Plugin không phải Maven Versions Plugin và không tự làm release management.

## 8. Các trường hợp packaging=pom: BOM và published parent

### 8.1. BOM là artifact có chức năng quản lý dependency version

Một BOM thường có `<packaging>pom</packaging>` và `dependencyManagement`:

~~~xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>dev.example</groupId>
  <artifactId>platform-bom</artifactId>
  <version>2.0.0</version>
  <packaging>pom</packaging>

  <properties>
    <commons.version>3.17.0</commons.version>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>${commons.version}</version>
      </dependency>
    </dependencies>
  </dependencyManagement>
</project>
~~~

Đây là **fragment mô tả BOM**, không phải một project runnable với release configuration. Nếu flatten BOM bằng mode làm mất `dependencyManagement`, consumer import BOM có thể không nhận được phiên bản nào.

Cấu hình cần cân nhắc:

~~~xml
<configuration>
  <flattenMode>bom</flattenMode>
  <updatePomFile>true</updatePomFile>
</configuration>
~~~

`bom` giữ `dependencyManagement` và `properties` theo tài liệu. Nó có thể giữ các entries như được khai, nên **không được giả định mọi imported BOM, inherited parent property hoặc placeholder khác đã resolve hoàn toàn**. Phải kiểm tra published BOM và thử consumer thực sự import:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>dev.example</groupId>
      <artifactId>platform-bom</artifactId>
      <version>2.0.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Sau đó consumer khai Commons Lang không version trong `dependencies`, chạy `dependency:tree` xem version `3.17.0` có được managed đúng không.

### 8.2. updatePomFile có default khác cho packaging pom

Theo tài liệu MojoHaus, default `updatePomFile` thường **chỉ tự thay POM reference khi packaging khác `pom`**. Với `packaging=pom`, phải bật `updatePomFile=true` nếu muốn publish generated POM, ngoại lệ `flattenMode=bom` có default true.

Điều đó có nghĩa **file `.flattened-pom.xml` tồn tại không chứng minh repository `.pom` là file ấy**. Với BOM/parent/aggregator, hãy inspect installed/deployed POM.

### 8.3. Parent POM có thể cần giữ cấu hình build

Nếu `platform-parent` là POM được các dự án khác kế thừa, nó có thể chứa `properties`, `pluginManagement`, `build/plugins`, `dependencyManagement`. Flatten bằng `defaults` hoặc `clean` rồi bỏ chúng sẽ làm downstream parent mất chức năng.

Phân biệt:

- **Build-only parent nội bộ**: có thể chỉ xuất hiện trong producer source/repo; flatten ordinary library để loại parent reference.
- **Published parent thực thụ**: downstream child phải tiếp tục kế thừa build configuration; cân nhắc `resolveCiFriendliesOnly`, không flatten hoặc cấu hình retention chuyên biệt.
- **BOM**: consumers import để lấy dependencyManagement; dùng `bom` và thử downstream import.
- **Aggregator**: chỉ chứa `modules` điều phối reactor; không nhất thiết cần publish cho consumer.

Không lấy sự thành công của `mvn install` của một POM packaging để kết luận contract với downstream child vẫn được giữ.

## 9. Multi-module, inherited dependencies và profiles

Dự án có thể gồm:

~~~text
workspace/
├── pom.xml
├── api/pom.xml
└── impl/pom.xml
~~~

Root `packaging=pom` có `version=${revision}`. Child `api`/`impl` là JARs và dùng shared version. Những rủi ro:

1. **Reactor build PASS không chứng minh published consumer POM đúng.** Reactor có thể resolve modules từ source tree mà remote consumer không có.
2. `impl` có thể phụ thuộc `api`; installed `impl.pom` phải ghi version `api` đã resolve và thuộc repository.
3. Mỗi module thường sinh `.flattened-pom.xml` ở **module basedir**; không dùng chung một file cho nhiều GAV.
4. Parent `packaging=pom` cần quyết định riêng: BOM, published parent hay build-only aggregator.
5. Đừng nhầm `<modules>` với `<parent>`; aggregation không tự tạo dependency/inheritance.
6. `pluginManagement` cung cấp configuration defaults, nhưng phải xác nhận plugin execution thực sự áp cho modules cần publish.
7. Với CI-friendly versions, Maven guide hướng dẫn dùng `${project.version}` cho những module dependencies trong trường hợp phù hợp, thay vì tùy tiện dùng `${revision}` ở mọi nơi.

### 9.1. Profiles có thể làm consumer graph khác đi

Producer có profiles theo JDK, OS, file, property, `-P`, Maven settings hoặc environment. Flatten Plugin có rules riêng về profile activation và tham số `embedBuildProfileDependencies`. Không có quy luật “flatten luôn xóa mọi profile”.

- Profile đang active khi producer build có thể thay effective dependencies.
- OS/JDK-driven profiles có thể được giữ để downstream chọn theo môi trường.
- Property/file activation có thể được nhúng dependencies theo option của plugin.
- Nếu CI và laptop kích hoạt profiles khác nhau, generated POM có thể khác nhau.

Không phát hành artifact với dependency graph vô tình phụ thuộc vào profile không ổn định. Kiểm tra generated POM và chạy consumer test ở các môi trường mục tiêu.

## 10. Install, deploy, signing và metadata phát hành

`flatten:flatten` chỉ tạo POM. `mvn install` cài artifact + POM vào local repository; `mvn deploy` xuất bản lên remote repository nếu `distributionManagement`, repository ID/credentials và permissions hợp lệ.

~~~bash
mvn -B -ntp clean install
mvn -B -ntp clean deploy
~~~

**Không chạy deploy nếu chưa cấu hình đích và quyền phù hợp.** Khi publish tới Nexus/Artifactory/Maven Central, cần quan tâm license/SCM/developers metadata, source/javadoc artifacts, checksums/signatures, SBOM và vulnerability scanning theo repository policy. `flattenMode=defaults` có thể bỏ những optional fields mà public repository muốn; khi đó chọn `oss`/`ossrh` hoặc cấu hình có kiểm chứng.

Nếu artifact được ký, đảm bảo POM được ký **chính là POM sẽ được deploy**. Không ký original POM rồi deploy một generated POM khác mà không kiểm tra plugin/goal order.

Một version release như `1.4.2` nên bất biến theo repository policy. Flatten không sửa version sau package. Không publish cùng một GAV với bytecode khác và mong consumer cache luôn phản ánh đúng.

## 11. Maven 4 và consumer POM tích hợp

MojoHaus Flatten Maven Plugin phổ biến trong **Maven 3.x**. **Maven 4** có cơ chế native phân biệt build POM/consumer POM và tùy chọn flattening riêng; semantics/default có thể khác và thay đổi theo release. Vì vậy:

- Đọc docs của Maven 4 version đang dùng, không sao chép một cách mù quáng `flattenMode` từ MojoHaus.
- Kiểm tra native flatten có bật hay không; consumer POM mặc định có thể giữ nhiều phần build/inheritance.
- Không thêm MojoHaus Flatten Plugin cùng native mechanism mà chưa kiểm tra artifact POM output thực.
- Chạy consumer từ repository với GAV đã publish, không chỉ trong source reactor.

Mục tiêu là **repository POM đúng**, không phải việc một plugin tên “flatten” đã chạy.

## 12. Lỗi thường gặp và cách điều tra

### 12.1. Consumer báo unresolved ${revision}

Kiểm tra source vs published POM, `flatten:flatten` có chạy trước install/deploy không, `updatePomFile` có đúng không, và `revision` đã được cấp qua properties/CLI chưa. Source POM còn `${revision}` **không nhất thiết sai**; lỗi là repository POM không consumable.

### 12.2. Đã có .flattened-pom.xml nhưng installed POM vẫn là original

Nguyên nhân có thể là `updatePomFile=false`, packaging `pom` dùng default không update, plugin chạy quá muộn hoặc build theo profile/module khác. Không sửa source `pom.xml` bằng tay để che dấu; sửa plugin/lifecycle, tạo bản build mới, inspect repository POM.

### 12.3. Non-resolvable parent POM

Source hoặc published POM còn trỏ tới parent chưa publish. `resolveCiFriendliesOnly` giữ parent reference; ordinary library có thể cần mode loại parent và resolve inherited values. Nếu published parent thực sự là hợp đồng build của consumer, phải publish parent có thể resolve được.

### 12.4. Consumer thiếu dependency hoặc version

`flattenMode=fatjar` có thể bỏ dependencies; `flattenDependencyMode`, `optional`, `exclusions`, imported BOM, scopes và dependencyManagement cũng ảnh hưởng. Đối chiếu source/flattened/installed POM và `dependency:tree` của consumer. Không dùng `all` như thuốc chữa mọi trường hợp.

### 12.5. BOM import được nhưng không quản lý version

Có thể mode đã loại `dependencyManagement` hoặc bỏ `properties` cần thiết. Dùng `bom`, kiểm tra consumer import BOM và downstream version thực.

### 12.6. Published parent mất compiler/pluginManagement settings

`defaults` tối giản không thích hợp nếu mục tiêu là child kế thừa build configuration. Cần giữ POM contract hoặc chọn chiến lược không flatten.

### 12.7. Public repository từ chối vì thiếu metadata

Mode đã bỏ licenses/SCM/developers hoặc file ký/source JAR chưa phù hợp. Dùng `oss`/`ossrh` và xác minh policy release; Maven build producer thành công không đủ.

### 12.8. mvn clean không xóa .flattened-pom.xml

`maven-clean-plugin` chủ yếu xóa `target`; generated POM ở project basedir. Bind `flatten:clean` vào lifecycle `clean` và cấu hình filename/outputDirectory đồng bộ.

### 12.9. Consumer trong IDE chạy nhưng CI không resolve

IDE có thể dùng cached artifacts hoặc Maven reactor/import configuration khác. Kiểm tra local/remote repository, POM thực tế, versions, settings/mirrors, permissions và clean consumer build. Không suy đoán plugin version chính xác là nguyên nhân khi chưa có logs.

### 12.10. Build với version khác nhưng consumer vẫn lấy bản cũ

`mvn -Drevision=...` thay producer version; consumer dependency version phải đổi tương ứng. Maven cache/snapshot metadata và repository policies cũng ảnh hưởng. Flatten không tự bump consumer dependency.

### 12.11. Public POM chứa private repository URLs

Mode `defaults` theo đặc tả giữ repositories; consumer có thể thấy private URL hoặc cần access. Với public artifacts, cân nhắc `oss` loại repositories/pluginRepositories, bảo đảm dependencies được publish ở những nơi consumer có quyền đọc.

### 12.12. Effective POM đẹp nhưng published POM lỗi

`help:effective-pom` phản ánh mô hình build, **không chứng minh installed POM**. Luôn kiểm tra `.flattened-pom.xml` và `artifact-version.pom` trong repository; cuối cùng chạy consumer build.

## 13. Quy trình kiểm chứng 8 bước cho release

1. Xác nhận Maven/JDK/plugin versions và định nghĩa artifact version.
2. `mvn clean verify` với profiles/CI properties sẽ dùng khi release.
3. Kiểm tra `.flattened-pom.xml` sau goal flatten: GAV, packaging, dependencies, scopes, optional/exclusions.
4. Xác nhận không còn CI placeholders chưa giải ở các trường consumer cần.
5. Dùng `mvn install` hoặc `mvn deploy` với đúng lifecycle, không chỉ `package`.
6. Đọc **installed/deployed POM**, không chỉ source POM/effective POM.
7. Tạo consumer **ngoài reactor**, dependency chỉ theo GAV; chạy `dependency:tree` và một use case runtime.
8. Với public release, rà license/SCM/developers, signature, artifact integrity và repository policy.

Khi làm nhiều modules, lặp lại bước 3–7 cho những module thực sự publish.

## 14. Bài tập và đáp án

**A.** `pom.xml` dùng `${revision}` và producer build PASS. Repository POM có cần resolve version không? — **Có**: bên tiêu thụ phải nhận GAV hợp lệ; kiểm tra published POM.

**B.** `flatten:flatten` tạo file rồi có tự upload Maven Central không? — **Không**: install/deploy và credentials/policy là quy trình riêng.

**C.** `updatePomFile=true` có sửa source pom.xml trên disk không? — **Không theo cơ chế chính**: nó thay MavenProject file reference để install/deploy dùng generated POM.

**D.** `packaging=pom` có cùng default updatePomFile với JAR không? — **Không**: cần chú ý mode `bom` hoặc set true tường minh.

**E.** BOM bị loại dependencyManagement vẫn là BOM có ích không? — **Không như mong muốn**: import không còn versions được quản lý; cân nhắc `flattenMode=bom`.

**F.** Parent POM cho downstream child có nên flatten `defaults` vô điều kiện không? — **Không**: dễ mất pluginManagement/properties/build config mà child cần.

**G.** `resolveCiFriendliesOnly` có giống `defaults` không? — **Không**: nó tập trung giải CI-friendly placeholders và giữ cấu trúc POM khác.

**H.** Library JAR cần Commons Lang nhưng POM flattened không có dependency đó; consumer sẽ ra sao? — **Có thể lỗi runtime**: cần giữ dependency metadata và kiểm tra consumer.

**I.** `flattenMode` và `flattenDependencyMode` có cùng chức năng không? — **Không**: một bên chọn POM elements; bên còn lại điều khiển dependency flattening depth.

**J.** `mvn clean package` có đưa artifact vào local repo để consumer dùng không? — **Không**: cần `install` hoặc remote `deploy`.

**K.** Multi-module reactor build PASS có chứng minh POM remote sẽ resolve được? — **Chưa**: phải kiểm tra artifact qua repository bằng consumer độc lập.

**L.** Maven 4 native consumer POM có luôn giống plugin MojoHaus không? — **Không**: behavior/version khác nhau, cần kiểm chứng.

## 15. Checklist cuối bài

- [ ] Phân biệt source POM, effective POM và consumer POM được publish.
- [ ] GAV của producer đã resolve đúng version.
- [ ] `revision`/`sha1`/`changelist` không còn unresolved ở published POM.
- [ ] Flatten Plugin bind trước install/deploy.
- [ ] `updatePomFile` đúng với loại packaging.
- [ ] Generated POM không bị commit vô tình; flatten clean được cấu hình.
- [ ] Mode phù hợp ordinary library, public release, BOM hoặc parent.
- [ ] Các direct/inherited/transitive dependencies được xử lý đúng.
- [ ] Scopes, optional, exclusions và version management không sai.
- [ ] Nếu bỏ build parent, consumer không còn parent reference không resolve.
- [ ] Nếu publish parent, properties/plugins quản lý cho child còn nguyên.
- [ ] Nếu publish BOM, dependencyManagement và properties import được.
- [ ] Profiles và CI properties không làm generated POM khác ngoài chủ ý.
- [ ] Đã kiểm tra installed/deployed `artifact-version.pom`.
- [ ] Consumer project ngoài reactor build và chạy bằng GAV từ repository.
- [ ] Nếu public release, licenses/SCM/developers/signatures đáp ứng policy.
- [ ] Maven 4 được đánh giá riêng với native consumer POM.

## 16. Tài liệu chính thức

1. [MojoHaus Flatten Maven Plugin — Introduction](https://www.mojohaus.org/flatten-maven-plugin/): vai trò consumer POM.
2. [Flatten Maven Plugin — Usage](https://www.mojohaus.org/flatten-maven-plugin/usage.html): bind process-resources/clean và updatePomFile.
3. [Flatten Plugin 1.8.0 — flatten:flatten](https://www.mojohaus.org/flatten-maven-plugin/flatten-mojo.html): flattenMode, flattenDependencyMode, updatePomFile, profile handling.
4. [Flatten Plugin — flatten:clean](https://www.mojohaus.org/flatten-maven-plugin/clean-mojo.html): xóa generated POM.
5. [Maven CI Friendly Versions](https://maven.apache.org/guides/mini/guide-maven-ci-friendly.html): revision, sha1, changelist và install/deploy.
6. [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): dependencies, scopes, BOM, optional, exclusions.
7. [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): process-resources, install, deploy.
8. [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): effective POM producer.
9. [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): consumer dependency graph.
10. [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html): consumer runtime test.
11. [Apache Maven 4 — What's New](https://maven.apache.org/whatsnewinmaven4.html): consumer POM và flattening tích hợp.
12. [Flatten Plugin — Multi-module Example](https://www.mojohaus.org/flatten-maven-plugin/examples/example-multiple-versions.html): central versions và modules.
