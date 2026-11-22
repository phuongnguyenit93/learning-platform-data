# Javadoc và liên kết tài liệu cho thư viện phụ thuộc trong Maven

## 1. Javadoc là gì và vì sao thư viện cần tài liệu liên kết?

Một thư viện Java phát hành ra Maven repository thường có **binary JAR**, POM và đôi khi có thêm sources/Javadoc JAR. Binary JAR giúp ứng dụng compile và chạy. POM cho biết groupId, artifactId, version và dependencies. **Javadoc** giải thích public API: kiểu dữ liệu, tham số, giá trị trả về, ngoại lệ, hợp đồng sử dụng, mức độ tương thích và phiên bản xuất hiện.

Công cụ `javadoc` nằm trong **JDK**. **Apache Maven Javadoc Plugin** dùng công cụ này để biến Java source/comments thành HTML, lấy classpath từ Maven dependencies, tạo external links và đóng gói API docs khi cần.

Ví dụ thư viện của ta dùng `org.apache.commons.lang3.StringUtils`. Khi tài liệu có `{@link StringUtils#isBlank(CharSequence)}`, người đọc muốn bấm vào đó để thấy **Javadoc của Commons Lang**, thay vì chỉ thấy chữ `StringUtils`.

Để điều này xảy ra phải có hai điều kiện:

1. **Symbol resolution:** Java source/Javadoc tool biết class `StringUtils` và method `isBlank(CharSequence)` qua dependency trên classpath.
2. **External documentation resolution:** Javadoc biết **gốc bộ API docs** của Commons Lang và đọc được metadata `package-list` hoặc `element-list`.

Có dependency trong POM **không tự tạo hyperlink Javadoc**. Có external docs URL cũng **không giúp compiler biết một class chưa có dependency**.

Bài học hướng dẫn Maven Javadoc Plugin **3.12.0**, cách dùng `links`/`offlineLinks`, Java 17 Javadoc, Maven Site, Javadoc JAR, cách publish và debug, cùng ví dụ Java 17/JUnit 5 có thể chạy được.

## 2. Phân biệt các đầu ra của Maven

| Đầu ra | Chứa gì | Công cụ/lệnh |
| --- | --- | --- |
| Binary JAR | Compiled `.class` và resources | `mvn package` với packaging jar |
| HTML Javadoc | Trang HTML mô tả API của project | `javadoc:javadoc` |
| Maven Site | Trang giới thiệu, reports và API docs | `mvn site` và `<reporting>` |
| Javadoc JAR | HTML API docs trong archive classifier `javadoc` | `javadoc:jar` |
| Sources JAR | Java source files | Maven Source Plugin, không phải Javadoc Plugin |

External links chỉ là các hyperlink từ HTML của bạn tới **HTML của dependency**. Maven Javadoc Plugin không tự nhúng toàn bộ Javadoc của Commons Lang vào Javadoc JAR chỉ vì đã khai báo link.

### Vai trò của Javadoc comments

Javadoc comment dùng cú pháp comment đặc biệt bắt đầu bằng `/**` trước một declaration. Bên trong có mô tả và tags:

| Tag | Tác dụng |
| --- | --- |
| `@param` | Giải thích tham số và ràng buộc |
| `@return` | Giải thích kết quả |
| `@throws` | Điều kiện ném exception |
| `@see` | Tham chiếu hiển thị ở mục “See Also” |
| `{@link Type}` | Hyperlink inline đến Java symbol |
| `{@link Type#method(Type)}` | Hyperlink tới method với signature |
| `{@code null}` | Code literal, không phải hyperlink |
| `@since` | Phiên bản API xuất hiện |
| `@deprecated` | Giải thích API cũ và hướng thay thế |
| `@apiNote` và `@implNote` | Ghi chú API/implementation khi cần |

Một comment tốt không chỉ “mô tả tên method” mà nêu rõ behavior, nullability, tính bất biến, exceptions và những điều người dùng API cần biết.

**Javadoc không tự coi mọi comment như Markdown README.** Standard Doclet hỗ trợ Javadoc tags và HTML hợp lệ, ví dụ `<p>` và `<ul><li>`. Java code có thể compile trong khi Javadoc tool báo lỗi vì unresolved link hoặc HTML không hợp lệ.

## 3. Internal link, external link và chữ ký method

Một số kiểu reference:

```text
{@link #label(String)}
{@link NameFormatter#labels(List)}
{@link org.apache.commons.lang3.StringUtils}
{@link org.apache.commons.lang3.StringUtils#isBlank(CharSequence)}
{@link java.util.List}
```

- `#label(String)`: method thuộc class đang được document, thường là **internal link**.
- `NameFormatter#labels(List)`: method của một type thuộc chính project.
- `StringUtils`: type **ngoài project**, thuộc Commons Lang dependency.
- `java.util.List`: JDK API, cũng nằm ngoài source project.

**Chữ ký trong member reference phải khớp declaration thật.** Ví dụ `StringUtils.isBlank` có tham số `CharSequence`, dù Java caller có thể truyền `String`. Viết `isBlank(String)` trong `@link` có thể khiến Javadoc không resolve method đó.

`@see StringUtils` là block tag; `{@link StringUtils}` tạo link ngay trong câu. `{@code StringUtils}` chỉ hiển thị chữ kiểu code, không tự mở trang tài liệu.

## 4. Vì sao external Javadoc URL cần package-list hoặc element-list?

Javadoc tool không thể suy chính xác URL HTML của một type nếu không biết bộ docs ngoài xuất bản packages/modules nào. Khi xử lý tùy chọn link, nó thường tìm metadata ở **gốc bộ Javadoc HTML**:

```text
https://docs-provider.example/api/package-list
https://docs-provider.example/api/element-list
```

Đây chỉ là URL mẫu. Bộ docs cũ thường có `package-list`; bộ docs cho Java modular APIs có thể có `element-list`. Công cụ Javadoc và plugin phải hỗ trợ định dạng liên quan.

**Không trỏ tới file một class** như `StringUtils.html`, URL trang chủ dự án hoặc binary `.jar`. Phải trỏ tới docs root chứa metadata và các trang class.

Hai docs roots sử dụng trong ví dụ:

- `https://docs.oracle.com/en/java/javase/17/docs/api/` — Java SE 17 API.
- `https://javadoc.io/doc/org.apache.commons/commons-lang3/3.14.0/` — Commons Lang Javadoc, phiên bản 3.14.0.

**Cần kiểm tra metadata thật trong môi trường build.** CDN, proxy, redirect hoặc HTTP 404 có thể làm một URL vốn mở được trong trình duyệt nhưng không cung cấp list cho Javadoc tool. Khi URL không còn tương thích, chọn root docs khác có metadata hợp lệ hoặc chuẩn bị offlineLinks.

## 5. Các cách cấu hình external Javadoc links

### 5.1. Khai báo links tường minh

```xml
<configuration>
    <links>
        <link>https://docs.oracle.com/en/java/javase/17/docs/api/</link>
        <link>https://javadoc.io/doc/org.apache.commons/commons-lang3/3.14.0/</link>
    </links>
</configuration>
```

Đây là **đoạn plugin configuration**, không phải POM độc lập. Nó tương ứng với khả năng `-link` của JDK Javadoc.

**Pin link version theo dependency binary version**: nếu project dùng `commons-lang3:3.14.0` nhưng docs trỏ `latest`, người đọc có thể xem một API method chỉ xuất hiện trong bản mới hơn.

### 5.2. detectLinks

```xml
<configuration>
    <detectLinks>true</detectLinks>
</configuration>
```

Maven Javadoc Plugin có thể suy ra docs URLs từ metadata/conventions của Maven dependencies. Tuy nhiên:
- Dependency POM `project.url` có thể trỏ homepage, không phải docs root.
- Một dự án có thể đổi hosting hoặc đường dẫn.
- Một URL dùng chung cho nhiều versions có thể luôn trả latest.
- Một số dependencies không publish API docs metadata.
- CI offline/proxy có thể chặn URL được suy ra.

Vì vậy **detectLinks không đảm bảo liên kết luôn đúng**. Ví dụ chính dùng links tường minh và `detectLinks=false`.

### 5.3. detectJavaApiLink

Plugin có thể tự nhận diện Java SE API docs theo source/compile configuration hoặc Javadoc executable. Nếu bạn đã thêm URL **Java SE 17** tường minh vào `links`, có thể đặt:

```xml
<detectJavaApiLink>false</detectJavaApiLink>
```

để kiểm soát URL JDK và tránh lặp links. Không vô tình gắn docs của JDK cao hơn lên thư viện cam kết tương thích Java 17.

### 5.4. detectOfflineLinks

Tham số này hướng tới **cross-links giữa các Maven modules**, khác với links tới thư viện ngoài reactor. Với Maven Javadoc Plugin 3.12.0, release notes ghi nhận default `detectOfflineLinks` đã thay đổi thành false cho **JAR goals**. Nếu cần cross-module docs, cấu hình và kiểm tra rõ từng goal/version thay vì dựa vào mặc định mơ hồ.

## 6. Bài thực hành Java 17 và JUnit 5 đầy đủ

Bài tạo library `name-format-docs`, dùng Commons Lang 3.14.0 và có cả source, Javadoc comment, unit tests.

### 6.1. Cấu trúc file

```text
name-format-docs/
├── pom.xml
└── src/
    ├── main/java/com/example/docs/
    │   ├── package-info.java
    │   ├── NameFormatter.java
    │   └── Demo.java
    └── test/java/com/example/docs/
        └── NameFormatterTest.java
```

Đường dẫn trong sơ đồ là cách viết rút gọn các folders dưới `src/main/java` và `src/test/java`. Package của các Java files là `com.example.docs`.

### 6.2. pom.xml hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.docs</groupId>
    <artifactId>name-format-docs</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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
                <artifactId>maven-site-plugin</artifactId>
                <version>3.22.0</version>
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
                    <show>public</show>
                    <linksource>true</linksource>
                    <failOnError>true</failOnError>
                    <detectLinks>false</detectLinks>
                    <detectJavaApiLink>false</detectJavaApiLink>
                    <detectOfflineLinks>false</detectOfflineLinks>
                    <links>
                        <link>https://docs.oracle.com/en/java/javase/17/docs/api/</link>
                        <link>https://javadoc.io/doc/org.apache.commons/commons-lang3/3.14.0/</link>
                    </links>
                </configuration>
            </plugin>
        </plugins>
    </build>

    <reporting>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.12.0</version>
                <configuration>
                    <release>17</release>
                    <show>public</show>
                    <linksource>true</linksource>
                    <detectLinks>false</detectLinks>
                    <detectJavaApiLink>false</detectJavaApiLink>
                    <detectOfflineLinks>false</detectOfflineLinks>
                    <links>
                        <link>https://docs.oracle.com/en/java/javase/17/docs/api/</link>
                        <link>https://javadoc.io/doc/org.apache.commons/commons-lang3/3.14.0/</link>
                    </links>
                </configuration>
            </plugin>
        </plugins>
    </reporting>
</project>
```

**Đây là một POM hoàn chỉnh**. Các lựa chọn chính:
1. Java release 17 phù hợp với code và phiên bản API JDK.
2. Commons Lang là compile dependency để source và Javadoc resolve `StringUtils`.
3. JUnit Jupiter chỉ có test scope.
4. Javadoc Plugin trong `<build><plugins>` áp dụng cho goals gọi trực tiếp.
5. Javadoc Plugin trong `<reporting><plugins>` áp dụng cho Maven Site report.
6. `show=public` hướng tài liệu vào API công khai.
7. `linksource=true` sinh HTML có liên kết tới source của **project**, không tự tải source dependency.
8. `detectLinks=false` và `detectJavaApiLink=false` giúp links tường minh là nguồn docs được kiểm soát.
9. `failOnError=true` khiến Javadoc goal báo lỗi khi generation bị lỗi.
10. **Chưa bind Javadoc goal vào build lifecycle**: `mvn package` chưa tự tạo Javadoc HTML/JAR.

Nếu Javadoc tool không thể fetch metadata docs ngoài ở hai links, cần xem phần offlineLinks thay vì kết luận Java source sai.

### 6.3. src/main/java/com/example/docs/package-info.java

```java
/**
 * API xử lý tên người dùng, có tham chiếu tới
 * {@link org.apache.commons.lang3.StringUtils} của Commons Lang.
 *
 * @since 1.0.0
 */
package com.example.docs;
```

`package-info.java` là nơi viết **package-level documentation**. Nó giúp tài liệu HTML có trang package summary.

### 6.4. src/main/java/com/example/docs/NameFormatter.java

```java
package com.example.docs;

import java.util.List;
import java.util.Objects;

import org.apache.commons.lang3.StringUtils;

/**
 * Các phương thức định dạng tên dùng trong Java applications.
 *
 * <p>{@link #label(String)} dùng
 * {@link StringUtils#isBlank(CharSequence)} và
 * {@link StringUtils#capitalize(String)} từ Commons Lang.
 *
 * <p>{@link #labels(List)} trả {@link java.util.List}.
 *
 * @see StringUtils
 * @since 1.0.0
 */
public final class NameFormatter {

    private NameFormatter() {
    }

    /**
     * Tạo tên hiển thị, hoặc dùng giá trị dự phòng nếu trống.
     *
     * @param input đầu vào, có thể là {@code null}
     * @return tên chuẩn hóa hoặc {@code "Anonymous"} nếu trống
     * @see StringUtils#isBlank(CharSequence)
     */
    public static String label(String input) {
        if (StringUtils.isBlank(input)) {
            return "Anonymous";
        }
        return StringUtils.capitalize(input.strip());
    }

    /**
     * Định dạng từng phần tử trong danh sách.
     *
     * <p>Mỗi phần tử được xử lý như {@link #label(String)}.
     * Kết quả từ {@link java.util.stream.Stream#toList()}
     * là một danh sách không cho phép thêm hoặc xóa phần tử.
     *
     * @param inputs danh sách đầu vào; không cho phép {@code null}
     * @return danh sách tên đã chuẩn hóa, unmodifiable
     * @throws NullPointerException nếu {@code inputs} là {@code null}
     * @see java.util.List
     */
    public static List<String> labels(List<String> inputs) {
        Objects.requireNonNull(inputs, "inputs");
        return inputs.stream().map(NameFormatter::label).toList();
    }
}
```

**Đây là Java 17 compilable.** Những liên kết quan trọng:
- `{@link #label(String)}` là internal member link.
- `{@link StringUtils#isBlank(CharSequence)}` là external member link tới Commons Lang.
- `{@link java.util.List}` là link tới Java SE API.

**Hành vi thật:**
- `label("  maven  ")` trả `"Maven"`.
- `label(null)` hoặc `label("   ")` trả `"Anonymous"`.
- `labels(List.of(" java ", "maven"))` tạo danh sách `[Java, Maven]`.
- `labels(null)` ném `NullPointerException`.
- `Stream.toList()` trên Java 17 trả danh sách unmodifiable.

### 6.5. src/main/java/com/example/docs/Demo.java

```java
package com.example.docs;

import java.util.List;

/**
 * Ví dụ cách dùng {@link NameFormatter}.
 *
 * @since 1.0.0
 */
public final class Demo {

    private Demo() {
    }

    /**
     * In các kết quả.
     *
     * @param args tham số dòng lệnh (không dùng)
     */
    public static void main(String[] args) {
        System.out.println(NameFormatter.label("  maven  "));
        System.out.println(NameFormatter.label("   "));
        System.out.println(NameFormatter.labels(List.of(" java ", "maven")));
    }
}
```

**Stdout chính xác của chương trình** khi runtime có dependency cần thiết:

```text
Maven
Anonymous
[Java, Maven]
```

### 6.6. src/test/java/com/example/docs/NameFormatterTest.java

```java
package com.example.docs;

import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class NameFormatterTest {

    @Test
    void capitalizesTrimmedName() {
        assertEquals("Maven", NameFormatter.label("  maven  "));
    }

    @Test
    void usesFallbackForNullAndBlank() {
        assertEquals("Anonymous", NameFormatter.label(null));
        assertEquals("Anonymous", NameFormatter.label("   "));
    }

    @Test
    void returnsUnmodifiableLabels() {
        List<String> result =
                NameFormatter.labels(List.of(" java ", "maven"));

        assertEquals(List.of("Java", "Maven"), result);
        assertThrows(UnsupportedOperationException.class,
                () -> result.add("Other"));
    }
}
```

Đây là **3 JUnit Jupiter test methods**. Maven Surefire nhận class có hậu tố `Test`. Javadoc goal main-source thông thường không sinh API docs cho test class này; muốn tài liệu test riêng dùng `javadoc:test-javadoc`.

## 7. Build, generate Javadoc, generate Site và chạy Java

### Bước 1: kiểm tra Maven/JDK

Từ root `name-format-docs`:

```bash
mvn -version
java -version
```

Cần JDK 17+ có công cụ `javadoc`, Maven tương thích plugin đã ghim và repository có plugins/dependencies. Một bản JRE tối giản có thể không chứa `javadoc`.

### Bước 2: build và tests

```bash
mvn -B -ntp clean verify
```

Project tạo binary JAR và chạy 3 tests. Report thường ở:

```text
target/surefire-reports/TEST-com.example.docs.NameFormatterTest.xml
```

**Không nhầm:** vì chưa bind Javadoc goal vào verify, `BUILD SUCCESS` ở bước này **chưa** có nghĩa Javadoc external links đã đạt.

### Bước 3: sinh Javadoc HTML riêng

```bash
mvn -B -ntp javadoc:javadoc
```

Với Javadoc Plugin 3.12.0 gọi trực tiếp, một vị trí output thường là:

```text
target/reports/apidocs/index.html
target/reports/apidocs/com/example/docs/NameFormatter.html
target/reports/apidocs/com/example/docs/package-summary.html
```

Nếu `reportOutputDirectory` đã tùy chỉnh hoặc goal chạy trong Site, output directory có thể khác. Kiểm tra Maven log và file thật.

Mở `NameFormatter.html`; tìm internal links, external links tới `StringUtils`/`List`, phần `@param`/`@return`, và HTML source khi `linksource=true`.

### Bước 4: sinh Maven Site

```bash
mvn -B -ntp site
```

Do POM có `<reporting>`, site thường ở:

```text
target/site/index.html
target/site/project-reports.html
target/site/apidocs/index.html
```

**`mvn site` chỉ sinh website local**, không tự deploy lên Internet.

### Bước 5: chạy demo với đầy đủ classpath

Trên Linux/macOS có Maven local repository mặc định:

```bash
java -cp "target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" com.example.docs.Demo
```

Trên Windows, Java classpath thường dùng `;` thay `:`. Nếu local repository tùy biến, thay đường dẫn thực tế.

Stdout:

```text
Maven
Anonymous
[Java, Maven]
```

Không dùng `java -jar target/name-format-docs-1.0.0.jar` rồi kỳ vọng demo chạy: POM không tạo executable manifest `Main-Class` và không nhúng Commons Lang vào library JAR.

## 8. Phân biệt `<links>` và `<offlineLinks>`

Khi Javadoc tool có Internet, `<links>` có thể lấy metadata từ docs root. Nhưng trong CI offline hoặc firewall hạn chế, Javadoc tool có thể không đọc được metadata đó.

Với `<offlineLinks>` cần hai dữ kiện:
- **`<url>`**: URL public được ghi vào hyperlink cuối cùng.
- **`<location>`**: folder/địa chỉ chứa metadata `package-list`/`element-list` mà tool đọc **khi generate**.

Ví dụ đã giải nén Javadoc HTML của Commons Lang 3.14.0:

```text
name-format-docs/
└── third-party-javadoc/
    └── commons-lang3-3.14.0/
        ├── index.html
        ├── element-list  (hoặc package-list)
        └── org/apache/commons/lang3/...
```

Phương án offline dùng **thay thế** phần `<links>` online của plugin:

```xml
<configuration>
    <detectLinks>false</detectLinks>
    <detectJavaApiLink>false</detectJavaApiLink>
    <offlineLinks>
        <offlineLink>
            <url>https://javadoc.io/doc/org.apache.commons/commons-lang3/3.14.0/</url>
            <location>${project.basedir}/third-party-javadoc/commons-lang3-3.14.0/</location>
        </offlineLink>
    </offlineLinks>
</configuration>
```

Đây là **fragment cấu hình**, không phải POM đầy đủ và không dùng để thêm một Javadoc Plugin thứ hai.

**Lưu ý:**
- `location` phải là nơi metadata nằm ngay dưới thư mục đó; file `.jar` chưa giải nén **không tương đương** một directory docs root.
- Muốn liên kết Java SE 17 offline, chuẩn bị thêm metadata JDK docs cục bộ và thêm `offlineLink` cho Java docs.
- Maven `-o` cũng cần các build plugins và dependencies đã cache. Offline links không tự làm Maven có Commons Lang binary JAR.
- Hyperlink HTML có thể vẫn trỏ ra website public, ngay cả khi quá trình generate chỉ đọc metadata local.
- Không để đồng thời online link và offline link **cho cùng docs root** mà không hiểu cấu hình/ưu tiên.

### Chuẩn bị dependency Javadoc archive khi online

Một dependency có thể publish artifact classifier `javadoc`. Có thể thử copy Javadoc JAR bằng Maven Dependency Plugin:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:copy -Dartifact=org.apache.commons:commons-lang3:3.14.0:jar:javadoc -DoutputDirectory=target/external-doc-archives
```

Sau đó giải nén vào thư mục đã chọn và kiểm tra metadata. Đây là bước **chuẩn bị có mạng**; không phải mọi third-party library đều publish Javadoc JAR.

## 9. `linksource` không phải nguồn của thư viện phụ thuộc

Cấu hình:

```xml
<linksource>true</linksource>
```

yêu cầu Javadoc tool tạo bản HTML có line numbers cho **source files đang được document của chính project**, rồi liên kết các trang API tới HTML source tương ứng.

Nó **không tự**:
- tải `commons-lang3-sources.jar`;
- tải toàn bộ Commons Lang Javadoc;
- tự mở Git repository của dependency;
- tạo Javadoc cho compiled dependencies mà không có source/docs riêng.

Khi publish tài liệu, hãy kiểm tra chính sách disclosure của project trước khi bật source links trên site public.

## 10. Javadoc JAR để phát hành thư viện

Sau build, có thể gọi:

```bash
mvn -B -ntp clean package javadoc:jar
```

Javadoc Plugin tạo HTML rồi đóng thành JAR classifier mặc định `javadoc`. Các output cần tìm:

```text
target/name-format-docs-1.0.0.jar
target/name-format-docs-1.0.0-javadoc.jar
```

Kiểm tra nội dung:

```bash
jar tf target/name-format-docs-1.0.0-javadoc.jar
```

Bạn cần thấy những HTML pages của `com.example.docs`; **không** phải toàn bộ HTML Commons Lang.

Muốn tự attach Javadoc JAR khi release build tới phase `package`, có thể đặt **fragment execution này vào Javadoc Plugin đang có trong `<build><plugins>`**:

```xml
<executions>
    <execution>
        <id>attach-javadoc</id>
        <phase>package</phase>
        <goals>
            <goal>jar</goal>
        </goals>
    </execution>
</executions>
```

Gọi `javadoc:jar` trực tiếp chỉ attach artifact **trong Maven session hiện tại**. Nếu muốn cài/phát hành cùng main JAR, cần chạy trong cùng invocation trước `install`/`deploy`, hoặc bind goal vào lifecycle.

- `mvn install`: cài artifacts/POM vào **local repository**.
- `mvn deploy`: publish Maven artifacts lên **remote repository** nếu có distributionManagement/credentials hợp lệ.
- `mvn site`: tạo website cục bộ.
- `site:deploy`: publish site theo cơ chế deployment website, khác artifact deploy.

Không gọi deploy trên repository sản phẩm chỉ để thực hành.

## 11. `<reporting>` và `<build><plugins>` khác nhau

Trong POM đầy đủ, Maven Javadoc Plugin xuất hiện ở hai vị trí:

- `<build><plugins>`: cấu hình goals được gọi trực tiếp, hoặc một execution được bind vào default lifecycle.
- `<reporting><plugins>`: cấu hình Javadoc **report** khi chạy Maven Site Plugin.

Chỉ khai báo plugin trong `<reporting>` **không khiến** `mvn package` tự tạo Javadoc JAR. Chỉ khai báo plugin ở `<build>` **không nên bị coi là** cấu hình report/menu Site đầy đủ.

Một Maven Site reporting fragment:

```xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.12.0</version>
            <configuration>
                <show>public</show>
                <links>
                    <link>https://docs.oracle.com/en/java/javase/17/docs/api/</link>
                    <link>https://javadoc.io/doc/org.apache.commons/commons-lang3/3.14.0/</link>
                </links>
            </configuration>
        </plugin>
    </plugins>
</reporting>
```

Đây là **fragment minh họa** đã có trong full POM, không cần copy để tạo khối `<reporting>` thứ hai. Nếu có parent POM, xem **effective configuration** và output thực tế vì build/report plugin configuration có inheritance/merge semantics khác nhau.

## 12. Multi-module Javadoc và aggregate reports

Giả sử một Maven reactor:

```text
root/pom.xml            (packaging=pom)
├── api/pom.xml
├── impl/pom.xml
└── cli/pom.xml
```

Có ba việc khác nhau:
1. Sinh Javadoc của từng module.
2. Sinh một bộ Javadoc **aggregate** cho nhiều modules trong reactor.
3. Tạo external hyperlinks tới dependencies ngoài reactor (Commons Lang, JDK).

Khi muốn aggregate:

```bash
mvn -B -ntp javadoc:aggregate
```

Dùng từ aggregator root hợp lệ, rồi kiểm tra output. `javadoc:aggregate` **không tự tải mọi Javadoc ngoài reactor**. Nếu muốn include dependency sources cần cơ chế và artifacts riêng.

Trong root `<reporting>` của multi-module project, có thể dùng reportSets:

```xml
<reportSets>
    <reportSet>
        <id>aggregate</id>
        <inherited>false</inherited>
        <reports>
            <report>aggregate</report>
        </reports>
    </reportSet>
    <reportSet>
        <id>default</id>
        <reports>
            <report>javadoc</report>
        </reports>
    </reportSet>
</reportSets>
```

Đây là **fragment cho multi-module root**, không phải phần bổ sung cần thiết vào POM demo đơn module. Javadoc Plugin từ 3.1.0 có behavior aggregate ở nhiều cấp, nên hãy kiểm soát inheritance/reportSets để tránh sinh báo cáo tổng hợp lặp không mong muốn.

`detectOfflineLinks` giúp một số goals tạo links **giữa modules** khi metadata/module URLs phù hợp; nó không thay `<links>` tới third-party documentation.

## 13. Version, doclint và tính tái lập

Khi thư viện target Java 17 nhưng link sang docs Java 25, người dùng có thể đọc API chưa có trong Java 17. Khi POM dùng Commons Lang 3.14.0 nhưng link docs `latest`, người dùng cũng có thể đọc method không tồn tại ở binary version của họ.

**Khi cập nhật dependency/version:**
1. Đổi version trong POM.
2. Đối chiếu source imports và member signatures.
3. Cập nhật docs URL đúng version.
4. Chạy compile/tests.
5. Chạy Javadoc generation.
6. Mở HTML, click vài external links đại diện và kiểm tra URL đích.

Javadoc có thể báo:
- Unresolved type/member reference;
- HTML markup không hợp lệ;
- Thiếu mô tả tag theo mức doclint đang bật;
- Encoding sai;
- External metadata không đọc được;
- JDK/toolchain quá cũ cho source release.

**Compiler success không bằng Javadoc success.** Hãy sửa Javadoc source/metadata trước khi nghĩ đến cách tắt toàn bộ `doclint` hoặc đặt `failOnError=false`.

### UTF-8 và tiếng Việt

Nên đặt:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
```

Đây là properties fragment, không phải full POM. Plugin có `encoding`, `docencoding`, `charset` nếu muốn xác định trực tiếp. Java source files phải thực sự được lưu UTF-8.

## 14. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Link StringUtils chỉ là text | Không có docs root metadata | Kiểm tra `<links>` và list files |
| `reference not found` | Type/member signature sai | Đối chiếu Java classpath và declaration |
| Link `isBlank(String)` fail | Signature thực là `isBlank(CharSequence)` | Sửa Javadoc reference |
| `package-list` HTTP 404 | URL trỏ class/landing thay docs root | Chọn docs root hợp lệ |
| Link dẫn bản Commons khác | URL `latest` không cố định | Pin docs theo dependency version |
| CI offline thiếu external links | Metadata không tải được | Chuẩn bị `<offlineLinks>` |
| `<location>` trỏ file `.jar` | Chưa giải nén Javadoc JAR | Giải nén và kiểm tra file list |
| JDK API link không đúng release | detectJavaApiLink/manual URL sai | Chọn Java 17 docs |
| Javadoc HTML lỗi tiếng Việt | Source/output charset khác | Chốt UTF-8 |
| `mvn test` xanh nhưng Javadoc fail | Test phase không chạy Javadoc | Gọi `javadoc:javadoc` |
| `mvn site` thiếu API docs | Reporting thiếu hoặc cấu hình sai | Kiểm tra `<reporting>`/Site output |
| `mvn package` không có javadoc JAR | Chưa gọi/bind `javadoc:jar` | Thêm execution hoặc gọi goal |
| Javadoc JAR không có Commons HTML | External docs chỉ được tham chiếu | Hành vi đúng |
| linksource không tải source dependency | Chỉ tạo HTML source của project | Phân biệt với Maven Source Plugin |
| Maven dùng JDK cũ | Javadoc tool không hỗ trợ release 17 | Kiểm tra `mvn -version`/toolchain |
| Javadoc source compile nhưng docs fail | Unresolved tag hoặc HTML doclint | Sửa Javadoc comments |
| Hosting local đúng nhưng deployed links sai | URL base/layout site khác | Test HTML sau publish |

### Quy trình debug

1. Kiểm tra Maven và JDK bằng `mvn -version`.
2. Chạy `mvn clean verify` để bảo đảm source/dependencies đúng.
3. Kiểm tra Javadoc Plugin version/configuration.
4. Chạy `mvn javadoc:javadoc`; đọc **lỗi đầu tiên**.
5. Kiểm tra FQCN, method signatures và Java imports.
6. Kiểm tra docs roots và metadata `package-list`/`element-list`.
7. Nếu offline, kiểm tra folder ở `<offlineLinks><location>`.
8. Mở HTML và click external links; kiểm tra version đích.
9. Với Site, kiểm tra `target/site/apidocs`.
10. Với Javadoc JAR, dùng `jar tf` để xem contents.

## 15. CI và quality gate tài liệu

Một CI job có thể làm hai bước:

```bash
mvn -B -ntp clean verify
mvn -B -ntp javadoc:javadoc
```

Lệnh đầu kiểm tra code/tests; lệnh sau kiểm tra Javadoc source và external links. Trong POM demo, **chỉ `mvn verify` chưa sinh Javadoc**, vì goal chưa bind vào phase đó.

Một workflow GitHub Actions minh họa:

```yaml
name: API documentation
on:
  pull_request:
  push:

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify Java
        run: mvn -B -ntp clean verify
      - name: Generate Javadoc
        run: mvn -B -ntp javadoc:javadoc
```

Đây là workflow **minh họa**, không tự thiết lập branch protection hoặc deploy site. Với CI offline, chuẩn bị Maven artifact cache và external metadata trước. Đừng xem lỗi kết nối website bên ngoài như một lỗi code mà tắt Javadoc checks vô thời hạn.

## 16. Bài tập tự kiểm tra

1. Tại sao Maven dependency và external Javadoc URL là hai cấu hình khác nhau?
2. `{@code StringUtils}` có tạo link như `{@link StringUtils}` không?
3. `@see` và `{@link}` xuất hiện ở đâu trong HTML?
4. Tại sao `isBlank(String)` có thể không resolve nhưng `isBlank(CharSequence)` resolve?
5. `<links>` trỏ docs root hay một class page?
6. `package-list` và `element-list` có tác dụng gì?
7. `detectLinks=true` có đảm bảo mọi dependency có docs đúng version không?
8. `detectJavaApiLink=false` hữu ích khi nào?
9. Tại sao `linksource` không tải source dependency?
10. `mvn javadoc:javadoc` và `mvn site` thường xuất HTML ở đâu?
11. Mục đích của Javadoc JAR classifier `javadoc` là gì?
12. Tại sao gọi `javadoc:jar` không mặc nhiên đồng nghĩa đã deploy?
13. `<offlineLinks><url>` và `<location>` khác nhau ra sao?
14. Vì sao phải giải nén Javadoc archive để dùng local metadata folder?
15. `javadoc:aggregate` khác external Javadoc links thế nào?
16. Ba dòng output của `Demo` là gì?
17. Khi nâng Commons Lang từ 3.14.0, ngoài POM cần đổi gì?
18. Vì sao nên bấm thử links thật trước khi publish?

## 17. Checklist phát hành

- [ ] Public API có mô tả Javadoc rõ, không mâu thuẫn implementation.
- [ ] `@param`, `@return`, `@throws` đầy đủ khi API yêu cầu.
- [ ] Symbol/member signatures trong `{@link}`/`@see` tồn tại.
- [ ] Java dependencies đầy đủ cho Javadoc tool resolve.
- [ ] Maven Javadoc Plugin và Maven Site Plugin được ghim version.
- [ ] Java release/Java SE docs URL tương thích nhau.
- [ ] External docs URLs có metadata list hợp lệ.
- [ ] Docs dependency version tương ứng binary dependency version.
- [ ] `detectLinks`/`detectJavaApiLink` được chọn có chủ đích.
- [ ] Offline metadata được chuẩn bị nếu CI không có mạng.
- [ ] `linksource` phù hợp chính sách public source.
- [ ] Source/HTML charset nhất quán UTF-8.
- [ ] `javadoc:javadoc` sinh HTML thật, các links đã được thử.
- [ ] Maven Site có Javadoc report nếu cần website docs.
- [ ] `javadoc:jar` được gọi/bind khi cần publish classifier.
- [ ] Không nhầm binary JAR, sources JAR, Javadoc JAR và Site HTML.
- [ ] Multi-module dùng aggregate goals khi thực sự cần.
- [ ] CI không che mọi lỗi docs bằng `failOnError=false`.
- [ ] Versioned docs được giữ lâu dài cho consumers.
- [ ] Không đưa secret vào public Javadoc hoặc POM.

**Kết luận:** Maven Javadoc Plugin sinh API documentation cho Java library. Để tham chiếu **tài liệu của thư viện phụ thuộc**, source phải resolve đúng class/member và Javadoc tool phải có URL docs root + metadata `package-list`/`element-list`. Dùng `<links>` khi có mạng, `<offlineLinks>` khi cần metadata local; `javadoc:javadoc` sinh HTML standalone, `mvn site` tích hợp Javadoc vào website, còn `javadoc:jar` tạo artifact classifier `javadoc` cho consumers. Ghim versions và kiểm tra HTML/links thật trước khi release là cách bảo đảm docs hữu ích và bền vững.

## Tài liệu tham khảo

- [Apache Maven Javadoc Plugin — Introduction](https://maven.apache.org/plugins/maven-javadoc-plugin/)
- [Apache Maven Javadoc Plugin — Usage](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html)
- [Apache Maven Javadoc Plugin — Links/OfflineLinks](https://maven.apache.org/plugins/maven-javadoc-plugin/examples/links-configuration.html)
- [Apache Maven Javadoc Plugin — javadoc:javadoc](https://maven.apache.org/plugins/maven-javadoc-plugin/javadoc-mojo.html)
- [Apache Maven Javadoc Plugin — javadoc:jar](https://maven.apache.org/plugins/maven-javadoc-plugin/jar-mojo.html)
- [Apache Maven Javadoc Plugin — Aggregation](https://maven.apache.org/plugins/maven-javadoc-plugin/examples/aggregate.html)
- [Apache Maven Javadoc Plugin — FAQ](https://maven.apache.org/plugins/maven-javadoc-plugin/faq.html)
- [Apache Maven Site Plugin](https://maven.apache.org/plugins/maven-site-plugin/)
- [Apache Maven — POM/Reporting](https://maven.apache.org/pom.html)
- [Java SE 17 API Reference](https://docs.oracle.com/en/java/javase/17/docs/api/)
- [Java Javadoc Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html)
- [Apache Commons Lang 3.14.0 API](https://javadoc.io/doc/org.apache.commons/commons-lang3/3.14.0/)