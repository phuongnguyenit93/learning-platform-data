# Javadoc trong CI: kiểm tra chất lượng và tạo tài liệu API

Javadoc trong CI biến tài liệu API thành một phần của chất lượng build. Mỗi pull request có thể được kiểm tra để phát hiện comment thiếu, sai `@param`/`@return`, liên kết không phân giải được, HTML không hợp lệ hoặc tài liệu không thể sinh bằng JDK mục tiêu. Khi kiểm tra thất bại, CI chặn merge giống như một compile task hoặc test task thất bại.

Javadoc là công cụ tạo HTML từ documentation comment trong source Java. DocLint kiểm tra nhiều lỗi thường gặp trong comment; tùy chọn `-Werror` biến warning thành lỗi. Maven, Gradle và Ant đều có thể gọi Javadoc trong build. Cần cấu hình task thành quality gate thực sự: nó phải được chạy trong lệnh CI bắt buộc, trả exit code khác 0 khi có lỗi và giữ lại output để người review kiểm tra.

Các lệnh và cấu hình dưới đây được kiểm tra với Zulu/OpenJDK 24.0.2, Maven 3.9.12, Maven Javadoc Plugin 3.12.0, Gradle 9.2.1 và Ant 1.10.15. Ví dụ source tương thích Java 17.

## 1. Javadoc có vai trò gì trong CI?

Javadoc giúp người dùng thư viện hiểu public API mà không cần đọc implementation. CI kiểm tra tài liệu ở đúng thời điểm API thay đổi, khi tác giả vẫn còn ngữ cảnh để sửa.

Một Javadoc gate thường đảm nhiệm bốn việc:

1. **Tạo tài liệu:** đọc source roots, phân giải type/reference và sinh HTML.
2. **Kiểm tra comment:** phát hiện lỗi cú pháp, HTML, reference, accessibility và mức độ thiếu documentation theo policy.
3. **Kiểm tra liên kết:** tạo liên kết tới API bên ngoài hoặc tài liệu của module phụ thuộc.
4. **Xuất artifact:** lưu HTML để review, hoặc đóng gói Javadoc JAR cùng binary và source JAR khi phát hành.

Javadoc task thường không thay thế compile, test hay kiểm tra HTML đầu ra. Một pipeline có thể tổ chức như sau:

~~~text
Checkout source
      |
      v
Select JDK / restore dependencies
      |
      v
Compile source -------------------+
      |                           |
      v                           v
Unit tests                 Generate Javadoc
      |                           |
      v                           v
Test quality gates         DocLint + -Werror
      |                           |
      +-------------+-------------+
                    |
                    v
               Verify / Check
                    |
          +---------+----------+
          |                    |
          v                    v
   Store HTML artifact    Package / Publish
                          Javadoc JAR
~~~

Với dự án chỉ có ứng dụng nội bộ, tài liệu có thể là artifact để nhóm phát triển tra cứu. Với thư viện hoặc SDK, Javadoc là một phần của hợp đồng API công khai và nên được kiểm tra nghiêm ngặt trước khi phát hành.

## 2. Phân biệt Javadoc comment với comment thông thường

Javadoc chỉ đọc documentation comment có dạng `/** ... */` gắn với declaration. Comment `//` và `/* ... */` thông thường không trở thành mô tả API.

Ví dụ:

~~~java
// This is a normal implementation comment.

/*
 * This is also a normal comment.
 */

/**
 * Calculates a price for the requested quantity.
 */
public final class PriceCalculator {
}
~~~

Javadoc dùng câu đầu tiên của comment làm phần tóm tắt trong bảng API, index và trang tổng quan. Vì vậy, câu đầu nên mô tả rõ hành vi, không mở đầu bằng những câu chung chung như “This class is a class”.

Có thể dùng `{@summary ...}` để chỉ định câu tóm tắt rõ ràng khi câu đầu tự nhiên không đủ phù hợp.

Comment nên giải thích:

- Hành vi mà caller có thể quan sát.
- Điều kiện đầu vào và giới hạn.
- Giá trị trả về, đơn vị đo và cách diễn giải.
- Exception có thể được ném.
- Side effect, thread-safety, lifecycle hoặc yêu cầu gọi theo thứ tự nếu có.
- Điểm khác biệt quan trọng giữa implementation hiện tại và hợp đồng API.

Không sao chép nguyên implementation vào Javadoc. Mục tiêu là mô tả cách dùng và bảo đảm của API.

## 3. Các tag thường dùng trong documentation comment

Ví dụ một method có documentation đầy đủ:

~~~java
/**
 * Calculates the total amount for a quantity and unit price.
 *
 * <p>The result uses the same minor currency unit as {@code unitPrice}.</p>
 *
 * @param quantity number of items; must be non-negative
 * @param unitPrice price of one item in minor currency units
 * @return the total amount in minor currency units
 * @throws IllegalArgumentException if an input is negative
 * @throws ArithmeticException if the result overflows a {@code long}
 * @since 1.0
 */
public long total(int quantity, long unitPrice) {
    // implementation
}
~~~

Các tag chính:

| Tag | Mục đích |
|---|---|
| `@param name` | Mô tả tham số method/constructor |
| `@param <T>` | Mô tả type parameter |
| `@return` | Mô tả kết quả của method trả giá trị |
| `@throws` / `@exception` | Mô tả exception và điều kiện phát sinh |
| `@since` | Phiên bản API được giới thiệu |
| `@deprecated` | Mô tả API cũ và hướng thay thế |
| `@see` | Tham chiếu tới API hoặc tài liệu liên quan |
| `@author` | Tác giả nếu dự án có chính sách hiển thị |
| `@version` | Phiên bản tài liệu nếu dự án sử dụng |

Các inline tag hữu ích:

- `{@code expression}` hiển thị code literal, tránh HTML xử lý dấu `<`, `>` hoặc `&`.
- `{@link Type#method}` tạo liên kết tới declaration.
- `{@linkplain Type#method}` tạo liên kết với text hiển thị thông thường.
- `{@literal text}` hiển thị nội dung literal.
- `{@inheritDoc}` kế thừa phần mô tả từ method cha/interface khi phù hợp.
- `{@value #CONSTANT}` hiển thị giá trị constant được hỗ trợ.

Với API generic, mô tả đúng type parameter:

~~~java
/**
 * Finds an item by its identifier.
 *
 * @param <T> type of the item
 * @param id identifier to find
 * @return the matching item, or {@code null} if absent
 */
public <T> T find(String id) {
    return null;
}
~~~

Không thêm `@return` cho method `void`, không mô tả tham số không tồn tại, và không ghi `@throws` cho một exception mà hợp đồng method không thể phát sinh. DocLint có thể phát hiện một số sai lệch này.

## 4. Document class, constructor, package và module

Javadoc không chỉ áp dụng cho method. Một public class nên mô tả mục đích, phạm vi sử dụng và các điều kiện quan trọng. Constructor công khai cũng là một declaration riêng; với strict missing-doc check, constructor mặc định được sinh ngầm có thể tạo warning.

Ví dụ:

~~~java
/**
 * Represents an amount in minor currency units.
 *
 * @since 1.0
 */
public final class Money {
    private final long minorUnits;

    /**
     * Creates a non-negative amount.
     *
     * @param minorUnits amount in the smallest currency unit
     * @throws IllegalArgumentException if the amount is negative
     */
    public Money(long minorUnits) {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("minorUnits must be non-negative");
        }
        this.minorUnits = minorUnits;
    }

    /**
     * Returns the amount in minor currency units.
     *
     * @return the amount in minor currency units
     */
    public long minorUnits() {
        return minorUnits;
    }
}
~~~

Dùng `package-info.java` để mô tả package, quy ước chung hoặc annotation ở cấp package:

~~~java
/**
 * Public API for monetary calculations.
 *
 * <p>All amounts in this package use minor currency units.</p>
 *
 * @since 1.0
 */
package com.example.api;
~~~

Với named module, `module-info.java` có thể chứa documentation comment để mô tả module, mục tiêu và API export. Khi tạo Javadoc cho nhiều module, dùng module path/module source path phù hợp với cấu trúc JPMS.

## 5. DocLint và các nhóm kiểm tra

DocLint là bộ kiểm tra tích hợp trong Javadoc. Trên JDK hiện đại, DocLint được bật mặc định cho các comment được đưa vào tài liệu; nên cấu hình rõ ràng trong CI để policy dễ đọc và không phụ thuộc giả định.

Các nhóm kiểm tra:

| Nhóm | Kiểm tra |
|---|---|
| `html` | HTML tag, cấu trúc và thuộc tính |
| `syntax` | Cú pháp comment, ký tự đặc biệt và tag không hợp lệ |
| `reference` | Liên kết và tham chiếu tới declaration |
| `accessibility` | Vấn đề accessibility như `alt` cho ảnh hoặc caption cho bảng |
| `missing` | Thiếu documentation cho declaration được đưa vào tài liệu |

Bật tất cả nhóm:

~~~text
-Xdoclint:all
~~~

Bật tất cả trừ kiểm tra thiếu comment:

~~~text
-Xdoclint:all,-missing
~~~

Cấu hình chuyển tiếp `all,-missing` hữu ích với codebase lớn đang bổ sung tài liệu dần. Có thể bật strict missing-doc gate cho package mới hoặc public API đã được chuẩn hóa, rồi mở rộng phạm vi sau khi xử lý backlog.

Để biến warning thành lỗi:

~~~text
-Werror
~~~

Khi có `-Werror`, một warning DocLint có thể làm Javadoc thoát với mã lỗi khác 0. CI sẽ nhận được build failure thay vì chỉ in warning rồi tiếp tục.

### 5.1. Nên bật strict policy như thế nào?

Với thư viện hoặc SDK công khai, dùng `-Xdoclint:all -Werror` để yêu cầu API được document đầy đủ. Với ứng dụng nội bộ có nhiều code cũ, bắt đầu bằng `-Xdoclint:all,-missing -Werror`, sau đó thiết lập lộ trình xử lý missing docs.

Không tắt toàn bộ DocLint chỉ vì một nhóm warning khó xử lý. Nếu một declaration có trường hợp ngoại lệ thực sự, có thể dùng `@SuppressWarnings("doclint")` hoặc nhóm cụ thể tại declaration đó, kèm lý do trong code review. Không đặt suppression ở package/root để che lỗi cho toàn bộ API.

DocLint phát hiện các lỗi phổ biến trong comment, nhưng không đánh giá tính đúng đắn của lời giải thích nghiệp vụ, không kiểm tra ngữ pháp và không thay thế một HTML conformance validator đầy đủ cho toàn bộ HTML được sinh.

## 6. Chạy Javadoc trực tiếp trong CI bằng CLI

Ví dụ project:

~~~text
src/
  main/
    java/
      com/example/api/
        package-info.java
        Money.java
        PriceCalculator.java
~~~

Lệnh strict gate cho Java 17:

~~~text
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -notimestamp -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
~~~

Ý nghĩa các option:

| Option | Ý nghĩa |
|---|---|
| `--release 17` | Dùng quy tắc source/API tương ứng Java 17 |
| `-encoding UTF-8` | Encoding của source files |
| `-docencoding UTF-8` | Encoding của HTML output |
| `-charset UTF-8` | Charset khai báo trong HTML |
| `-Xdoclint:all` | Bật mọi nhóm DocLint |
| `-Werror` | Làm build thất bại khi có warning |
| `-notimestamp` | Bỏ timestamp ẩn trong HTML để output ổn định hơn |
| `-d build/docs/javadoc` | Thư mục output |
| `-sourcepath` | Root chứa source package |
| `-subpackages` | Tạo tài liệu cho package và subpackage |

Javadoc mặc định tạo tài liệu cho public/protected API. Có thể dùng `-private` nếu cần document mọi declaration, nhưng không nên xuất private implementation docs thành API artifact nếu người dùng thư viện không cần chúng.

Thay `com.example` bằng package root thật. `-subpackages` giúp package mới được tự động đưa vào tài liệu khi source tree mở rộng.

Có thể truyền classpath khi source tham chiếu tới dependency:

~~~text
javadoc --release 17 -classpath "build/classes;lib/api.jar" -Xdoclint:all -Werror -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
~~~

Path separator của classpath là `;` trên Windows và `:` trên Linux/macOS. Với module, sử dụng `--module-path` và `--module-source-path` theo cấu trúc project.

## 7. Liên kết tới Javadoc bên ngoài

Khi comment tham chiếu tới class trong JDK hoặc thư viện khác, Javadoc có thể tạo liên kết tới tài liệu API bên ngoài.

Ví dụ liên kết Java SE 17:

~~~text
javadoc --release 17 -link https://docs.oracle.com/en/java/javase/17/docs/api/ -Xdoclint:all -Werror -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
~~~

Dùng full qualified name hoặc import hợp lệ trong `{@link ...}`. Một liên kết không phân giải được thường cho biết tên type/method sai, thiếu classpath hoặc tài liệu external API không có package list cần thiết.

`-link` có thể cần truy cập mạng để đọc metadata của tài liệu đích. Điều này làm build phụ thuộc mạng và dịch vụ bên ngoài. Với CI chạy offline hoặc cần tính ổn định cao, tải/cung cấp metadata Javadoc đã kiểm soát và dùng `-linkoffline <url> <local-doc-directory>`.

Một số JDK mới dùng `element-list` thay cho `package-list`; dùng file metadata phù hợp với phiên bản tài liệu được liên kết. Không tạo link tới URL không ổn định hoặc tài liệu chưa được publish.

## 8. Maven: đưa Javadoc vào `verify`

Maven Javadoc Plugin gọi Javadoc tool và hỗ trợ phần lớn option của tool. Cấu hình plugin trong `build/plugins` sẽ cho phép gọi goal trực tiếp; để biến nó thành CI gate, gắn goal vào lifecycle phase mà pipeline luôn chạy, ví dụ `verify`.

Ví dụ cấu hình trong `pom.xml`:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>

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

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-javadoc-plugin</artifactId>
      <version>3.12.0</version>
      <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
        <docencoding>UTF-8</docencoding>
        <charset>UTF-8</charset>
        <doclint>all</doclint>
        <failOnError>true</failOnError>
        <failOnWarnings>true</failOnWarnings>
        <notimestamp>true</notimestamp>
        <additionalOptions>
          <additionalOption>-Werror</additionalOption>
        </additionalOptions>
      </configuration>
      <executions>
        <execution>
          <id>javadoc-quality-gate</id>
          <phase>verify</phase>
          <goals>
            <goal>javadoc</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Chạy CI:

~~~text
./mvnw -B -ntp verify
~~~

- `doclint=all`: yêu cầu các nhóm DocLint.
- `failOnError=true`: lỗi khi Javadoc command thất bại.
- `failOnWarnings=true`: Maven plugin làm build fail khi Javadoc có warning.
- `additionalOptions/-Werror`: chuyển warning thành lỗi ngay trong Javadoc tool.
- `notimestamp=true`: bỏ timestamp trong HTML.
- `phase=verify`: đảm bảo `mvn verify` luôn gọi Javadoc gate.

Maven Javadoc Plugin có thể sinh tài liệu độc lập hoặc đóng gói Javadoc JAR. Chạy:

~~~text
./mvnw -B -ntp javadoc:javadoc
./mvnw -B -ntp javadoc:jar
~~~

Goal `javadoc:jar` tạo artifact có classifier `javadoc`, ví dụ:

~~~text
target/my-library-1.0-javadoc.jar
~~~

Trong release profile, có thể gắn goal `jar` để Javadoc JAR được publish cùng binary và source artifact. Chỉ publish artifact sau khi quality gate và các bước release khác thành công.

### 8.1. Multi-module Maven

Với Maven reactor, mỗi module có thể tạo Javadoc riêng. Nếu muốn một bộ tài liệu tổng hợp cho nhiều module, sử dụng goal `aggregate` hoặc `aggregate-jar` từ aggregator/parent phù hợp.

Đảm bảo dependency module và source được resolve trước khi aggregate. Nếu Javadoc goal được bind vào `verify` ở mọi module, cân nhắc cách tổ chức aggregate để tránh sinh cùng một bộ tài liệu nhiều lần hoặc publish artifact trùng.

## 9. Gradle: gắn `javadoc` vào `check`

Gradle Java Plugin tạo task `javadoc` kiểu `Javadoc` cho main source set. Task hỗ trợ option của Javadoc tool qua `StandardJavadocDocletOptions`.

Ví dụ `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withJavadocJar()
}

tasks.named('javadoc', Javadoc) {
    options.encoding = 'UTF-8'
    options.docEncoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.addBooleanOption('Xdoclint:all', true)
    options.addBooleanOption('Werror', true)
    options.addBooleanOption('notimestamp', true)
    options.links('https://docs.oracle.com/en/java/javase/17/docs/api/')
}

tasks.named('check') {
    dependsOn tasks.named('javadoc')
}
~~~

Chạy CI:

~~~text
./gradlew --no-daemon check
~~~

Task `javadoc` được gắn vào `check`, vì vậy `build` (phụ thuộc `check`) cũng chạy quality gate. Nếu chỉ chạy `compileJava` hoặc `test`, Javadoc task có thể không được thực thi; pipeline cần gọi `check` hoặc gọi rõ `javadoc`.

`withJavadocJar()` tạo task `javadocJar`, đóng gói output của `javadoc` với classifier `javadoc` và đăng ký documentation variant. Khi dùng `maven-publish` hoặc `ivy-publish`, variant này có thể được publish cùng component Java.

Chạy riêng:

~~~text
./gradlew --no-daemon javadoc
./gradlew --no-daemon javadocJar
~~~

Output HTML mặc định:

~~~text
build/docs/javadoc/index.html
~~~

Javadoc task của Java plugin xử lý source trong main source set. Nếu dự án có custom source set, test API hoặc nhiều subproject, cần cấu hình task riêng hoặc aggregate theo mục tiêu thực tế; không mặc định rằng task `javadoc` đã bao gồm mọi source set.

## 10. Apache Ant: `<javadoc>` task

Ant dùng `<javadoc>` để gọi Javadoc tool. Khác với `<javac>`, Javadoc task thường xử lý toàn bộ package được chọn mỗi lần chạy; nó không có cơ chế incremental theo từng file như compile task.

Ví dụ `build.xml`:

~~~xml
<project name="api-docs" default="javadoc">
  <target name="javadoc">
    <javadoc sourcepath="src/main/java"
             destdir="build/docs/javadoc"
             encoding="UTF-8"
             docencoding="UTF-8"
             charset="UTF-8"
             failonerror="true"
             failonwarning="true"
             useexternalfile="true">
      <package name="com.example.api"/>
      <arg value="-Xdoclint:all"/>
      <arg value="-Werror"/>
      <arg value="-notimestamp"/>
    </javadoc>
  </target>
</project>
~~~

Chạy:

~~~text
ant -noinput javadoc
~~~

- `failonerror=true`: fail khi Javadoc command trả lỗi.
- `failonwarning=true`: fail khi output có warning; thuộc tính này có từ Ant 1.9.4.
- `useexternalfile=true`: ghi command arguments vào file tạm, hữu ích khi command line quá dài.
- `<arg>`: truyền các option Javadoc không có thuộc tính tương ứng trong Ant task.

`-notimestamp` là option của Javadoc CLI, không phải thuộc tính của Ant `<javadoc>`. Truyền nó bằng nested `<arg>`. Ant Javadoc task luôn fork JVM vì Javadoc gọi `System.exit()`.

Nếu muốn đóng gói HTML thành JAR, chạy `<jar>` sau target Javadoc với `basedir="build/docs/javadoc"` và một `destfile` riêng. Kiểm tra output trước khi package để tránh phát hành JAR rỗng khi source package bị chọn sai.

## 11. CI workflow mẫu với GitHub Actions

Ví dụ workflow cho Maven, chạy trên pull request và push vào nhánh chính:

~~~yaml
name: Javadoc quality gate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  javadoc:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Compile, test and validate Javadoc
        run: ./mvnw -B -ntp verify

      - name: Store generated API documentation
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: api-javadoc
          path: target/reports/apidocs/
          if-no-files-found: error
~~~

Workflow này dùng cùng một JDK 17 cho compiler và Javadoc, cache Maven dependencies, và để `verify` làm gate bắt buộc. Nếu Javadoc thất bại, bước upload không chạy và job bị đánh dấu failed.

Với Gradle, dùng:

~~~yaml
- uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: '17'
    cache: gradle

- name: Run verification including Javadoc
  run: ./gradlew --no-daemon check

- name: Store generated API documentation
  if: success()
  uses: actions/upload-artifact@v4
  with:
    name: api-javadoc
    path: build/docs/javadoc/
    if-no-files-found: error
~~~

Trong CI thực tế:

- Chạy gate trên mọi pull request thay đổi source hoặc Javadoc comment.
- Để branch protection yêu cầu job này pass trước khi merge.
- Lưu HTML artifact để reviewer mở và kiểm tra liên kết/nội dung.
- Publish website hoặc Javadoc JAR từ nhánh được bảo vệ/tag release, không publish từ mọi pull request.
- Không đặt `continue-on-error` cho bước Javadoc quality gate.
- Giữ nguyên log warning/error trong job output để tác giả có thể sửa đúng file và dòng.

## 12. Quy định chất lượng tài liệu cho pull request

Một Javadoc gate hiệu quả cần có policy dễ hiểu:

**Mức API cần document**

- Public và protected type, constructor, field và method thuộc API công khai.
- Package/module overview nếu package/module có ý nghĩa với người dùng.
- API mới hoặc thay đổi hành vi phải cập nhật documentation tương ứng.
- Private implementation chỉ cần document nếu nhóm có yêu cầu riêng.

**Mức kiểm tra**

- DocLint `all` cho API đã đạt chuẩn.
- `all,-missing` trong giai đoạn chuyển đổi codebase cũ.
- `-Werror` để warning mới không bị bỏ qua.
- `@link` phải resolve được với source, classpath và external docs.
- HTML output phải được kiểm tra thêm nếu cần bảo đảm accessibility/conformance đầy đủ.

**Cách xử lý exception**

Nếu warning là false positive hoặc comment cố ý không áp dụng, suppression phải nằm gần declaration liên quan và có lý do. Reviewers nên xem suppression như một thay đổi policy, không phải cách làm CI xanh tạm thời.

Có thể dùng một rule riêng cho package mới: package đó bắt buộc `-Xdoclint:all`, trong khi package cũ được chuyển đổi dần. Khi backlog đã xử lý, nâng gate toàn module lên strict mode.

## 13. Giữ output ổn định và tái lập

Javadoc HTML có thể chứa timestamp, charset và nội dung phụ thuộc JDK/locale. Để build dễ so sánh giữa máy developer và CI:

- Pin JDK/toolchain và build-tool version.
- Pin Maven/Gradle plugin version.
- Dùng `--release` để đặt API/source release mục tiêu.
- Khai báo source encoding, HTML encoding và charset là UTF-8.
- Dùng `-notimestamp` hoặc `<notimestamp>true</notimestamp>`.
- Nếu đóng gói archive Maven, đặt `project.build.outputTimestamp` theo quy trình reproducible build.
- Dùng cùng external API documentation metadata trong mọi môi trường.
- Không phụ thuộc vào link website thay đổi không kiểm soát trong bước build offline.

Không cache output HTML như thể đó là source input nếu build tool không quản lý cache key tương ứng. Cache dependency/plugin download; để Javadoc task xác định khi nào output cần được tạo lại.

## 14. External links, dependency và mạng trong CI

Javadoc phải phân giải các type trong comment. Nếu API tham chiếu tới dependency, cần cung cấp compile classpath/module path tương ứng. Maven plugin thường lấy dependency từ project model; Gradle Javadoc task có classpath từ source set; Ant cần khai báo nested `<classpath>` khi cần.

Với external API docs:

- Dùng `-link` khi CI có quyền truy cập mạng ổn định.
- Dùng `-linkoffline` khi metadata được cung cấp trong cache hoặc workspace.
- Chọn tài liệu đúng phiên bản dependency/JDK.
- Tránh link tới URL không có `element-list`/`package-list` tương ứng.
- Nếu build bị chặn mạng, không tắt DocLint/reference checks; cung cấp metadata offline phù hợp.

Một lỗi `reference not found` có thể do tên class/method sai, thiếu import, dependency không có trong classpath, hoặc external documentation không resolve được. Kiểm tra từng nguyên nhân trước khi thêm suppression.

## 15. Generated sources, annotation processor và multi-module

Nếu project dùng annotation processor tạo API source, xác định rõ generated source directory và thứ tự task. Javadoc cần thấy source generated nếu các type đó là một phần API được phát hành. Đảm bảo task Javadoc chạy sau bước generate-sources và source path bao gồm output đó.

Với Maven, kiểm tra generated source được thêm vào project trước khi gọi `javadoc:javadoc`; nếu cần tổng hợp nhiều module, dùng `javadoc:aggregate` phù hợp.

Với Gradle, thêm generated source directory vào source set hoặc cấu hình Javadoc task cụ thể. Không document file sinh ra nếu đó chỉ là implementation detail.

Với JPMS, Javadoc có thể dùng module path và module source path. Kiểm tra module được export và package nào thuộc API công khai. Đừng đưa package nội bộ không export vào Javadoc public artifact nếu người dùng không thể truy cập chúng.

## 16. Javadoc JAR và artifact phát hành

HTML output hữu ích cho review và website; Javadoc JAR hữu ích cho IDE và Maven repository. Hai đầu ra có thể được tạo từ cùng một Javadoc task.

### Maven

~~~text
./mvnw -B -ntp javadoc:jar
~~~

Plugin tạo artifact classifier `javadoc`, ví dụ:

~~~text
target/my-library-1.0-javadoc.jar
~~~

Có thể bind goal `jar` vào release profile hoặc gọi trong release pipeline. `maven-javadoc-plugin` hỗ trợ goal `javadoc:jar` và `aggregate-jar`.

### Gradle

Trong Java plugin:

~~~groovy
java {
    withJavadocJar()
}
~~~

Task `javadocJar` đóng gói HTML và đăng ký documentation variant. Khi kết hợp `maven-publish`, variant Javadoc có thể được publish cùng Java component.

### Ant

Dùng `<jar>` sau khi target `<javadoc>` thành công:

~~~xml
<target name="javadoc-jar" depends="javadoc">
  <jar destfile="build/libs/api-javadoc.jar"
       basedir="build/docs/javadoc"/>
</target>
~~~

Không phát hành artifact nếu Javadoc gate fail hoặc output directory không có `index.html`.

## 17. Ví dụ Java 17+: source API để kiểm tra trong CI

Tạo `src/main/java/com/example/api/package-info.java`:

~~~java
/**
 * Public API for monetary calculations.
 *
 * <p>All amounts in this package use minor currency units.</p>
 *
 * @since 1.0
 */
package com.example.api;
~~~

Tạo `Money.java`:

~~~java
package com.example.api;

/**
 * Represents an amount in minor currency units.
 *
 * @since 1.0
 */
public final class Money {
    private final long minorUnits;

    /**
     * Creates a non-negative amount.
     *
     * @param minorUnits amount in the smallest currency unit
     * @throws IllegalArgumentException if the amount is negative
     */
    public Money(long minorUnits) {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("minorUnits must be non-negative");
        }
        this.minorUnits = minorUnits;
    }

    /**
     * Returns the amount in minor currency units.
     *
     * @return the amount in minor currency units
     */
    public long minorUnits() {
        return minorUnits;
    }
}
~~~

Tạo `PriceCalculator.java`:

~~~java
package com.example.api;

/**
 * Calculates totals for a quantity and unit price.
 *
 * <p>The result uses the same minor currency unit as {@code unitPrice}.</p>
 *
 * @see Money
 * @since 1.0
 */
public final class PriceCalculator {
    /**
     * Creates a calculator.
     */
    public PriceCalculator() {
    }

    /**
     * Calculates the total amount.
     *
     * @param quantity number of items; must be non-negative
     * @param unitPrice price of one item in minor currency units
     * @return the total amount in minor currency units
     * @throws IllegalArgumentException if an input is negative
     * @throws ArithmeticException if the result overflows a {@code long}
     * @see Math#multiplyExact(long, long)
     */
    public long total(int quantity, long unitPrice) {
        if (quantity < 0 || unitPrice < 0) {
            throw new IllegalArgumentException("inputs must be non-negative");
        }
        return Math.multiplyExact(quantity, unitPrice);
    }
}
~~~

Đây là source API dùng cho Javadoc task; nó không phải chương trình standalone có `main`. Maven compile task đã biên dịch ba source file với `--release 17`, sau đó Maven Javadoc Plugin sinh HTML trong verify phase. Gradle `check` và Ant `<javadoc>` cũng sinh tài liệu từ cùng API sample.

Kết quả đã xác minh:

~~~text
Maven:  target/reports/apidocs/index.html
Gradle: build/docs/javadoc/index.html
Ant:    ant-docs/index.html
~~~

Cả ba output đều có `index.html`. Maven `javadoc:jar` và Gradle `javadocJar` cũng tạo Javadoc JAR thành công.

## 18. Kiểm thử gate bằng một lỗi cố ý

Để xác nhận CI thật sự fail khi Javadoc sai, tạo một fixture có reference không tồn tại:

~~~java
/**
 * A class with an invalid reference.
 *
 * @see MissingMoneyType
 */
public final class BrokenApi {
}
~~~

Chạy:

~~~text
javadoc --release 17 -encoding UTF-8 -Xdoclint:all -Werror -d build/bad-docs -sourcepath src/main/java -subpackages com.example
~~~

Javadoc trả exit code khác 0 do reference không phân giải được. Trong CI, job phải giữ trạng thái failed. Sau khi xác minh gate, xóa fixture lỗi khỏi source thật và giữ test này ở sandbox riêng nếu muốn kiểm tra lại cấu hình.

Một gate chỉ chạy Javadoc nhưng không truyền `-Werror` hoặc không fail build khi warning xuất hiện có thể vẫn cho phép API documentation bị lỗi đi qua. Hãy kiểm tra cả trường hợp pass và trường hợp fail khi thiết lập pipeline.

## 19. Troubleshooting Javadoc trong CI

### `error: reference not found`

**Nguyên nhân:** `{@link}`/`@see` dùng tên sai, dependency thiếu trong classpath hoặc external Javadoc link không resolve.

**Cách xử lý:** kiểm tra full type/method signature, compile classpath/module path, URL external docs và `element-list`/`package-list`.

### `warning: no comment`

**Nguyên nhân:** public/protected declaration hoặc constructor không có documentation trong policy đang bật.

**Cách xử lý:** viết comment mô tả hành vi và tag tương ứng. Nếu đang chuyển đổi code cũ, có thể tạm dùng `-Xdoclint:all,-missing` với kế hoạch xử lý missing docs.

### `@param` hoặc `@return` không hợp lệ

**Nguyên nhân:** tên parameter không khớp source, type parameter thiếu dấu `<T>`, method `void` có `@return`, hoặc tag không đúng vị trí.

**Cách xử lý:** đối chiếu signature thực tế và chỉ dùng tag có ý nghĩa với declaration đó.

### HTML hoặc ký tự đặc biệt làm Javadoc fail

**Nguyên nhân:** dùng `<`, `>`, `&` như văn bản thường hoặc HTML tag chưa đóng/thiếu thuộc tính.

**Cách xử lý:** dùng `{@code ...}`/`{@literal ...}` cho text literal, kiểm tra HTML markup và accessibility attributes.

### `javadoc` không tìm thấy class từ dependency

**Nguyên nhân:** Javadoc classpath/module path không giống compile task.

**Cách xử lý:** kiểm tra Maven dependency, Gradle Javadoc classpath hoặc Ant nested `<classpath>`. Đảm bảo generated source và compile output đã sẵn sàng.

### Maven build thành công nhưng Javadoc không chạy

**Nguyên nhân:** plugin chỉ được khai báo trong `build/plugins` nhưng goal chưa được gọi hoặc chưa bind vào lifecycle.

**Cách xử lý:** bind `javadoc` vào `verify`, hoặc gọi `mvn javadoc:javadoc` tường minh. Kiểm tra pipeline thực sự chạy `mvn verify`.

### Maven `failOnWarnings` không làm CI fail

**Nguyên nhân:** cấu hình nằm trong `<reporting>` nhưng CI chỉ chạy build lifecycle, hoặc plugin config không áp dụng cho execution đang chạy.

**Cách xử lý:** đặt cấu hình đúng vị trí `<build><plugins>`, gắn execution vào `verify`, kiểm tra plugin version và xem command line Javadoc trong debug log.

### Gradle `javadoc` chạy khi gọi trực tiếp nhưng không chạy trong CI

**Nguyên nhân:** pipeline chỉ gọi `compileJava`/`test`, hoặc task `check` chưa phụ thuộc Javadoc.

**Cách xử lý:** nối `check.dependsOn(javadoc)` hoặc gọi `./gradlew check` với cấu hình task đã được xác nhận.

### Ant báo warning nhưng build vẫn xanh

**Nguyên nhân:** chưa bật `failonwarning`, chưa bật `-Werror`, hoặc Ant target không được gọi trong pipeline.

**Cách xử lý:** bật `failonerror` và `failonwarning`, truyền `-Xdoclint:all`/`-Werror` bằng nested `<arg>`, rồi chạy đúng target CI.

### Link ngoài lỗi trong môi trường không có mạng

**Nguyên nhân:** `-link` cần đọc metadata từ URL bên ngoài.

**Cách xử lý:** dùng `-linkoffline` với metadata được cache hoặc cung cấp qua workspace, và pin phiên bản tài liệu.

### HTML khác nhau giữa local và CI

**Nguyên nhân:** JDK/Javadoc version, locale, encoding, timestamp hoặc external link metadata khác nhau.

**Cách xử lý:** pin toolchain/plugin, đặt UTF-8, dùng `-notimestamp`, cố định locale và cùng nguồn metadata external links.

### Javadoc output trống hoặc thiếu package

**Nguyên nhân:** sourcepath/subpackages sai, source set không chứa file Java hoặc package bị exclude.

**Cách xử lý:** kiểm tra source root, package declaration, include/exclude và `index.html`. Với multi-module, xác định module nào đang được aggregate.

## 20. Checklist trước khi merge hoặc release

- [ ] JDK/Javadoc version được pin trong CI.
- [ ] Java release target trùng với baseline của thư viện.
- [ ] Source encoding, HTML encoding và charset là UTF-8.
- [ ] Public/protected API có class, constructor và method documentation phù hợp.
- [ ] `@param`, `@return`, `@throws`, `@since` và `@deprecated` chính xác.
- [ ] `{@link}` và `@see` phân giải được.
- [ ] `package-info.java`/`module-info.java` được document khi cần.
- [ ] DocLint được bật theo policy (`all` hoặc giai đoạn chuyển đổi có kiểm soát).
- [ ] `-Werror` hoặc `failOnWarnings` làm CI fail khi warning xuất hiện.
- [ ] Maven `verify`, Gradle `check` hoặc Ant target thực sự gọi Javadoc.
- [ ] External links có metadata ổn định hoặc hỗ trợ offline.
- [ ] Generated source và multi-module được đưa vào đúng phạm vi tài liệu.
- [ ] Output có `index.html` và được lưu thành CI artifact.
- [ ] Javadoc JAR được tạo khi phát hành thư viện.
- [ ] Pull request không publish tài liệu ra website production.
- [ ] Reproducibility được kiểm soát bằng toolchain, plugin, encoding và timestamp.
- [ ] Gate đã được thử với cả source hợp lệ và một lỗi Javadoc cố ý.

## 21. Tài liệu tham khảo

- Oracle JDK 24 — `javadoc` Command và DocLint: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html
- Oracle Java SE 24 — Javadoc Guide: https://docs.oracle.com/en/java/javase/24/javadoc/javadoc-guide.pdf
- Apache Maven Javadoc Plugin 3.12.0 — Introduction: https://maven.apache.org/plugins/maven-javadoc-plugin/
- Apache Maven Javadoc Plugin — Usage, goals `javadoc`, `javadoc:jar` và `aggregate`: https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html
- Apache Maven Javadoc Plugin — FAQ, `additionalOptions`, links và output encoding: https://maven.apache.org/plugins/maven-javadoc-plugin/faq.html
- Gradle — Building Java & JVM projects, Javadoc task: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — `CoreJavadocOptions` và `addBooleanOption`: https://docs.gradle.org/current/javadoc/org/gradle/external/javadoc/CoreJavadocOptions.html
- Gradle — `JavaPluginExtension.withJavadocJar()`: https://docs.gradle.org/current/dsl/org.gradle.api.plugins.JavaPluginExtension.html
- Apache Ant — Javadoc task, `failonwarning` và nested arguments: https://ant.apache.org/manual/Tasks/javadoc.html
- GitHub Actions — setup-java: https://github.com/actions/setup-java
- GitHub Actions — upload-artifact: https://github.com/actions/upload-artifact

Javadoc trong CI nên là một quality gate có thể tái lập: cùng JDK/toolchain, cùng release target, DocLint rõ ràng, warning làm build thất bại và output được giữ lại để review. Khi API thay đổi, người viết cập nhật documentation ngay trong pull request; khi phát hành thư viện, Javadoc JAR được tạo cùng binary để IDE và người dùng có thể tra cứu hợp đồng API.