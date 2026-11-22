# Đặt ResourceBundle đúng đường dẫn khi đóng gói JAR trong Java

## 1. Vì sao ResourceBundle chạy trong IDE nhưng lỗi khi chạy JAR?

Một lỗi phổ biến trong ứng dụng Java đa ngôn ngữ:

- Khi chạy `Main` trong IDE, các thông điệp tiếng Việt tải bình thường.
- Sau khi chạy `mvn package` hoặc `gradle jar`, chương trình báo `MissingResourceException`.
- Kiểm tra JAR mới phát hiện tệp `Messages_vi_VN.properties` không được đưa vào, hoặc nó nằm dưới một thư mục không thuộc classpath root.

Ví dụ chương trình gọi:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"));
```

Đây là **snippet** yêu cầu import `java.util.ResourceBundle` và `java.util.Locale`. Java sẽ tra cứu bundle theo **base name**, **locale** và **classpath/module resources**. Với bundle `.properties` trên classpath truyền thống, một tài nguyên có thể được tìm tại đường dẫn:

```text
com/example/i18n/Messages_vi_VN.properties
```

**Phải hiểu rằng đây là đường dẫn tương đối tính từ classpath root hoặc từ gốc nội dung của JAR**, không phải đường dẫn đến file nguồn trong dự án. Khi đóng gói, chỉ cần một cấp thư mục dư như `src/main/resources/` ở bên trong JAR cũng có thể làm Java không tìm thấy tài nguyên.

Bài này hướng dẫn cách bố trí resource bundle, tổ chức Maven/Gradle và JAR thủ công, cách Java chọn file theo locale và cơ chế fallback, kiểm tra JAR thực tế, phân biệt classpath với filesystem và những điểm đặc biệt ở Java 9+/Java 17+, named modules và Spring Boot.

## 2. Ba khái niệm: base name, resource path và classpath root

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Base name** | `com.example.i18n.Messages` | Tên logic truyền cho `ResourceBundle.getBundle`, dùng dấu chấm, **không có** phần mở rộng `.properties` |
| **Tên bundle theo locale** | `Messages_vi_VN.properties` | Tên file sử dụng quy tắc `_<language>_<country>` khi tương ứng locale |
| **Resource path** | `com/example/i18n/Messages_vi_VN.properties` | Đường dẫn tương đối từ classpath/JAR root |
| **Classpath root** | `target/classes`, `build/resources/main` hoặc **gốc nội dung** một JAR | Vị trí Java dùng làm điểm xuất phát để tìm resource |
| **JAR entry** | `com/example/i18n/Messages_vi_VN.properties` | Tên entry cần xuất hiện trong file `.jar`, dùng dấu `/` |
| **Filesystem path trong repo** | `src/main/resources/com/example/i18n/Messages_vi_VN.properties` | Vị trí file nguồn; bước build phải chép vào classpath output |

Với base name `com.example.i18n.Messages`, Java xét các tên bundle như:

```text
com.example.i18n.Messages_vi_VN
com.example.i18n.Messages_vi
com.example.i18n.Messages
```

Khi tra cứu bundle dạng property trên classpath, dấu chấm của phần package được đổi thành dấu `/` và thêm `.properties`:

```text
com/example/i18n/Messages_vi_VN.properties
com/example/i18n/Messages_vi.properties
com/example/i18n/Messages.properties
```

Đó là lý do **cấu trúc thư mục** và **tên file** phải tương ứng base name. Nếu bạn truyền `"Messages"` thay vì `"com.example.i18n.Messages"`, Java sẽ tìm ở **gốc** classpath, không tự dò vào thư mục `com/example/i18n`.

### Thử tên đường dẫn bằng API Java

Trong ứng dụng classpath/unnamed module, `ResourceBundle.Control` có các phương thức dùng để quan sát phép biến đổi tên:

```java
import java.util.Locale;
import java.util.ResourceBundle;

ResourceBundle.Control control = ResourceBundle.Control.getControl(
        ResourceBundle.Control.FORMAT_DEFAULT);

Locale locale = Locale.forLanguageTag("vi-VN");
String bundleName = control.toBundleName(
        "com.example.i18n.Messages", locale);

String path = control.toResourceName(bundleName, "properties");
System.out.println(bundleName);
System.out.println(path);
```

Đây là **snippet đặt trong phương thức**, không phải một class độc lập. Kết quả đã xác minh:

```text
com.example.i18n.Messages_vi_VN
com/example/i18n/Messages_vi_VN.properties
```

**Lưu ý:** `ResourceBundle.Control` mô tả chi tiết đặc biệt của chiến lược classpath; một số overload `getBundle(..., Control)` **không hỗ trợ khi gọi trong named module**. Với ứng dụng JPMS cần tuân thủ API và quy tắc đóng gói module tương ứng; không sao chép nguyên cách xử lý classpath sang module path.

## 3. Cấu trúc dự án Maven/Gradle đúng chuẩn

Một dự án Java thông dụng:

```text
bundle-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── app/
        │               └── Main.java
        └── resources/
            └── com/
                └── example/
                    └── i18n/
                        ├── Messages.properties
                        ├── Messages_vi.properties
                        └── Messages_vi_VN.properties
```

Trong Maven, `src/main/resources` là thư mục mặc định cho tài nguyên runtime. Với Gradle Java plugin, `src/main/resources` cũng là resource source directory mặc định. Bước build đặt nội dung của thư mục ấy vào output resources hoặc sao chép vào JAR.

**Không** đặt các file này trong `src/main/java/com/example/i18n` và tin rằng mọi công cụ build mặc định sẽ đưa `.properties` ở source code tree vào JAR. Một số IDE có thể xử lý khác, nhưng bản build CLI không phải lúc nào cũng sao chép các non-`.java` resources ở source tree.

**Không** coi `src/main/resources` là một package cần hiện diện trong JAR. Đây là thư mục đầu vào của build tool, không phải thành phần của base name.

### Bên trong JAR chuẩn phải trông như thế nào?

Sau khi đóng gói JAR chạy theo classpath truyền thống, các entry quan trọng phải có cấu trúc:

```text
com/example/app/Main.class
com/example/i18n/Messages.properties
com/example/i18n/Messages_vi.properties
com/example/i18n/Messages_vi_VN.properties
```

Không nên có dạng:

```text
src/main/resources/com/example/i18n/Messages_vi_VN.properties
resources/com/example/i18n/Messages_vi_VN.properties
target/classes/com/example/i18n/Messages_vi_VN.properties
```

trừ khi runtime được cấu hình và base name được thiết kế đặc biệt để xử lý những layout đó. Với ví dụ base name chuẩn của bài, các tên entry có thêm tiền tố như trên là **sai vị trí**.

## 4. Ví dụ Java 17+: ResourceBundle hoạt động trước và sau khi đóng gói

Ví dụ này là một dự án Maven **không có thư viện runtime bên ngoài**, đủ để tạo một JAR đơn giản và chạy bằng `java -cp`.

### 4.1. Tạo các tệp thông điệp

**`src/main/resources/com/example/i18n/Messages.properties`**

```properties
greeting=Hello
app.title=Localization Demo
only.base=Base fallback
```

**`src/main/resources/com/example/i18n/Messages_vi.properties`**

```properties
greeting=Xin chào
app.title=Ứng dụng bản địa hóa
```

**`src/main/resources/com/example/i18n/Messages_vi_VN.properties`**

```properties
greeting=Xin chào từ Việt Nam
```

Tạo và lưu ba file ở **UTF-8**. Trong Java 9 trở lên, property resource bundles dùng UTF-8 theo mặc định (với cơ chế fallback ISO-8859-1 cho dữ liệu cũ trong trường hợp byte UTF-8 không hợp lệ). Java 17+ hỗ trợ các ký tự tiếng Việt trực tiếp như trong ví dụ.

Cả ba file dùng **cùng một base name `com.example.i18n.Messages`** nhưng khác phần hậu tố locale. File root `Messages.properties` có ý nghĩa dự phòng. File `Messages_vi.properties` cung cấp bản tiếng Việt chung; `Messages_vi_VN.properties` chứa các ghi đè riêng cho Việt Nam.

Tài nguyên `Messages_vi_VN.properties` **không cần lặp lại mọi key** từ cha; `ResourceBundle` cho phép tra key qua chuỗi parent bundle khi một key không có trong bundle con.

### 4.2. Chương trình Main.java đầy đủ

Tạo file **`src/main/java/com/example/app/Main.java`**:

```java
package com.example.app;

import java.net.URL;
import java.util.Locale;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) {
        String baseName = "com.example.i18n.Messages";
        Locale locale = Locale.forLanguageTag("vi-VN");

        ResourceBundle bundle =
                ResourceBundle.getBundle(baseName, locale);

        System.out.println("Bundle locale: "
                + bundle.getLocale().toLanguageTag());
        System.out.println("Greeting: "
                + bundle.getString("greeting"));
        System.out.println("Title: "
                + bundle.getString("app.title"));
        System.out.println("Base fallback: "
                + bundle.getString("only.base"));

        String resourcePath =
                "com/example/i18n/Messages_vi_VN.properties";
        ClassLoader loader = Main.class.getClassLoader();
        URL url = loader.getResource(resourcePath);

        System.out.println("Resource in classpath: "
                + (url != null));
    }
}
```

Đây là lớp Java 17+ độc lập về runtime (sử dụng Java SE), nhưng **muốn chạy thành công phải đóng gói/đặt các file `.properties` cùng classpath đúng như phần trên**.

Ý nghĩa:

1. `getBundle(baseName, locale)` dùng tên có dấu chấm, **không** cần chuỗi hậu tố `_vi_VN` vì Java tự chọn candidate bundles.
2. `bundle.getLocale()` cho biết locale của bundle được tải — ở đây là `vi-VN`.
3. `getString("greeting")` lấy giá trị từ `Messages_vi_VN.properties`.
4. `getString("app.title")` tìm đến parent `Messages_vi.properties` vì key không có trong `vi_VN`.
5. `getString("only.base")` tìm đến root `Messages.properties`.
6. `ClassLoader.getResource(path)` kiểm tra tài nguyên qua **classpath**, không dựa vào thư mục làm việc hiện tại.

Với các file được tạo đúng và dữ liệu locale Java 17+, stdout dự kiến:

```text
Bundle locale: vi-VN
Greeting: Xin chào từ Việt Nam
Title: Ứng dụng bản địa hóa
Base fallback: Base fallback
Resource in classpath: true
```

Nếu terminal không hỗ trợ Unicode, ký tự trên màn hình có thể hiển thị sai dù `ResourceBundle` đọc đúng. Để chẩn đoán, kiểm tra code point hoặc file output UTF-8 thay vì chỉ nhìn hình dạng glyph.

## 5. Đóng gói bằng Maven: resources phải được copy vào target/classes

### 5.1. pom.xml tối thiểu

Tạo **`pom.xml`** tại gốc dự án:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>bundle-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Cấu hình trên cho phép Maven compile source tương ứng Java 17. Khi dự án không tự định nghĩa `resources` khác, Maven coi `src/main/resources` là resource directory chuẩn. Bước `process-resources` sao chép các file sang `target/classes`, rồi mục tiêu `package` đưa chúng cùng class đã biên dịch vào JAR.

### 5.2. Build và kiểm tra

Chạy từ **gốc dự án**:

```bash
mvn -q clean package
jar tf target/bundle-demo-1.0.0.jar
```

`jar tf` hiển thị toàn bộ entry trong JAR. Tìm những entry sau (đây là **trích phần liên quan**, không phải toàn bộ kết quả của `jar tf`):

```text
com/example/app/Main.class
com/example/i18n/Messages.properties
com/example/i18n/Messages_vi.properties
com/example/i18n/Messages_vi_VN.properties
```

Nếu các tệp `.properties` không xuất hiện, **vấn đề nằm ở cấu hình build, đường dẫn resource, ignore/exclude/filter hoặc artifact được kiểm tra**. Nếu file có xuất hiện nhưng dưới `src/main/resources/...`, cấu trúc entry bên trong JAR vẫn không đúng với base name.

Chạy bằng classpath (cách này **không cần Main-Class trong manifest**):

```bash
java -cp target/bundle-demo-1.0.0.jar com.example.app.Main
```

Với ví dụ này, lệnh trên in năm dòng như mục 4.2. Java dùng JAR như một **classpath entry**: đường dẫn `com/example/i18n/Messages_vi_VN.properties` được tìm tính từ gốc của JAR.

**Không** chạy `java -jar target/bundle-demo-1.0.0.jar` và kỳ vọng thành công trong ví dụ `pom.xml` tối thiểu: JAR mặc định có thể **không có `Main-Class` trong manifest**. `java -cp <jar> <main-class>` là cách chạy đúng mà không cần manifest entry. Nếu muốn dùng `java -jar`, cấu hình plugin để tạo manifest có `Main-Class`; việc này tách biệt với việc đóng gói `.properties`.

### 5.3. Resource nằm ở đâu qua từng giai đoạn?

| Giai đoạn | Nơi tồn tại | Vì sao |
| --- | --- | --- |
| Trước build | `src/main/resources/com/example/i18n/*.properties` | File nguồn resource |
| Sau process-resources | `target/classes/com/example/i18n/*.properties` | Classpath output của Maven |
| Sau compile | `target/classes/com/example/app/Main.class` | Java bytecode |
| Sau package | Các entry `com/example/i18n/*.properties` trong JAR | Có thể tải được trên runtime classpath |
| Sau `java -cp ...` | Java tra trong classpath JAR | Không cần file vật lý tách rời cạnh JAR |

**Đừng** viết code đọc `src/main/resources/...` bằng `new File(...)`: khi ứng dụng được triển khai, source tree thường không tồn tại.

## 6. Đóng gói bằng Gradle Java plugin

Gradle Java plugin cũng có layout chuẩn:

```text
src/main/java/
src/main/resources/
src/test/java/
src/test/resources/
```

Với cấu hình mặc định, các tệp trong `src/main/resources` được xử lý thành runtime resources (thường tại `build/resources/main`) và được đưa vào JAR do tác vụ `jar` tạo. Ví dụ Gradle Kotlin DSL tối thiểu:

**`build.gradle.kts`**

```kotlin
plugins {
    java
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

Đây là file build Gradle; cấu trúc `src/main/java` và `src/main/resources` giữ nguyên như mục 3. Build bằng Gradle Wrapper của dự án nếu có:

```bash
./gradlew clean jar
```

Trên Windows có thể dùng `gradlew.bat clean jar`. JAR thường nằm dưới `build/libs/`, ví dụ `bundle-demo-1.0.0.jar` nếu tên project là `bundle-demo`. Sau đó kiểm tra:

```bash
jar tf build/libs/bundle-demo-1.0.0.jar
java -cp build/libs/bundle-demo-1.0.0.jar com.example.app.Main
```

Nếu tên project hoặc version khác, **thay tên file bằng artifact thực tế**; không mặc định mọi Gradle build tạo đúng tên này.

### Khi nào resources có thể biến mất khỏi Gradle JAR?

- `sourceSets.main.resources.srcDirs` đã được đổi sang thư mục khác.
- Task `processResources` có `exclude` hoặc bộ lọc không phù hợp.
- Task `jar` đã tùy biến `from` hoặc `duplicatesStrategy`.
- Ứng dụng chạy một artifact khác JAR vừa tạo.
- Bạn chỉ chạy `javac` ở ngoài Gradle nhưng quên đưa `src/main/resources` lên classpath.

Đối chiếu các file source resources, output `build/resources/main` và entry thực tế của JAR để phân biệt lỗi **không copy**, lỗi **copy sai đường dẫn** và lỗi **runtime classpath**.

## 7. Đóng gói JAR thủ công bằng javac và jar

Không dùng Maven hoặc Gradle vẫn có thể kiểm tra rõ các lớp:

```bash
javac -encoding UTF-8 -d out src/main/java/com/example/app/Main.java
jar --create --file bundle-demo.jar -C out . -C src/main/resources .
jar tf bundle-demo.jar
java -cp bundle-demo.jar com.example.app.Main
```

Đây là các lệnh của **JDK 17+** chạy từ gốc dự án. Chúng có ý nghĩa:

1. `javac -d out` tạo `out/com/example/app/Main.class`.
2. `-C out .` của `jar` đưa **nội dung bên trong** `out` vào gốc JAR.
3. `-C src/main/resources .` đưa **nội dung bên trong** thư mục resources vào gốc JAR.
4. `jar tf` xác nhận tên entry thực tế.
5. `java -cp bundle-demo.jar com.example.app.Main` chạy với artifact được tạo.

Lưu ý: những lệnh shell này là hướng dẫn, không phải code Java. Trên Windows, hãy dùng các công cụ `javac` và `jar` trong `PATH`; cú pháp option `-C` của công cụ `jar` là độc lập với ký tự phân cách classpath của hệ điều hành.

Nếu muốn chạy **không đóng JAR** từ hai thư mục riêng, cần đưa **cả class output lẫn resource root** vào runtime classpath:

Linux/macOS:

```bash
java -cp "out:src/main/resources" com.example.app.Main
```

Windows:

```powershell
java -cp "out;src/main/resources" com.example.app.Main
```

Dấu phân cách các thành phần classpath là `:` trên hệ điều hành kiểu Unix và `;` trên Windows. Đừng chỉ để `out` trên classpath rồi kỳ vọng `getBundle` đọc được resource nằm trong `src/main/resources` mà không có bước copy/đưa root vào classpath.

## 8. Vì sao không thể đọc resource trong JAR bằng new File?

Một lỗi khác:

```java
File file = new File("src/main/resources/com/example/i18n/Messages_vi_VN.properties");
```

Trong IDE, working directory có thể trùng gốc repo và file tồn tại. Nhưng trong bản deploy, runtime thường chỉ có `bundle-demo.jar`, không có thư mục `src/main/resources`.

Kể cả khi đã biết URL tới entry trong JAR:

```text
jar:file:/.../bundle-demo.jar!/com/example/i18n/Messages_vi_VN.properties
```

nó **không phải** một filesystem `Path` thông thường. Đừng lấy `getResource(...).getFile()` rồi mặc nhiên chuyển sang `new File(...)`; cách làm này có thể hỏng với các URL có dấu cách, dấu `!`, path được escape hoặc nested JAR.

### Đọc resource qua classloader

Khi cần trực tiếp đọc một resource (không dùng `ResourceBundle`):

```java
import java.io.InputStream;

try (InputStream in = Main.class.getClassLoader()
        .getResourceAsStream(
                "com/example/i18n/Messages_vi_VN.properties")) {

    if (in == null) {
        throw new IllegalStateException("Resource not found");
    }
    // Đọc từ InputStream với charset phù hợp.
}
```

Đây là **snippet đặt trong một method thuộc lớp Main**. `getResourceAsStream` trả một `InputStream` có thể truy cập nội dung của entry ngay trong JAR mà không cần giải nén. Phải đóng stream sau khi dùng.

Phân biệt hai API:

- `Main.class.getClassLoader().getResourceAsStream("com/example/...")` dùng đường dẫn **tính từ classpath root**, **không có dấu `/` ở đầu**.
- `Main.class.getResourceAsStream("/com/example/...")` dùng đường dẫn **tuyệt đối từ classpath root** do dấu `/` đầu tiên.
- `Main.class.getResourceAsStream("local.txt")` khi không có dấu `/` sẽ tìm **tương đối tới package `com/example/app`** của `Main`.

`ResourceBundle.getBundle` thực hiện logic tìm bundle/fallback, không chỉ đọc một file đơn lẻ. Vì vậy với thông điệp đa ngôn ngữ, ưu tiên `ResourceBundle` thay vì tự duyệt các path của `.properties`, trừ khi ứng dụng có định dạng resource tùy chỉnh.

## 9. Candidate locales, fallback và key kế thừa

Khi gọi:

```java
ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"));
```

với các file trong ví dụ, Java xét candidate bundle phù hợp; trong trường hợp `vi-VN` đơn giản:

```text
Messages_vi_VN.properties
Messages_vi.properties
Messages.properties
```

Với dữ liệu được chuẩn bị ở mục 4, các key được giải quyết:

| Key | File chứa giá trị được sử dụng | Giá trị |
| --- | --- | --- |
| `greeting` | `Messages_vi_VN.properties` | `Xin chào từ Việt Nam` |
| `app.title` | `Messages_vi.properties` | `Ứng dụng bản địa hóa` |
| `only.base` | `Messages.properties` | `Base fallback` |

Một chú ý về thuật toán mặc định: `ResourceBundle` có chiến lược **candidate locales và fallback tới default locale** nếu bundle cho locale yêu cầu không tìm được, tùy tình huống. Không nên giải thích cứng rằng “mọi yêu cầu đều thử locale → root rồi dừng” cho tất cả cấu hình. Ví dụ đặt `Locale.getDefault()` thành một vùng khác có thể thay đổi bundle nào được chọn khi candidate cho locale yêu cầu không có.

Nếu cần **không fallback qua default locale JVM** trên classpath, có thể dùng `ResourceBundle.Control.getNoFallbackControl(...)` — nhưng cần hiểu API này không sử dụng như cũ cho mọi named module.

Ví dụ kiểm soát rõ locale là tốt hơn việc chỉ gọi overload không truyền locale:

```java
ResourceBundle selected = ResourceBundle.getBundle(
        "com.example.i18n.Messages", Locale.forLanguageTag("vi-VN"));
```

Đừng gọi `ResourceBundle.getBundle(baseName)` trong server đa vùng rồi kỳ vọng mọi người dùng thấy đúng ngôn ngữ riêng: overload đó dựa trên locale mặc định của JVM, không phải locale của từng request.

### MissingResourceException có hai nguyên nhân khác nhau

- **Không tìm thấy bundle:** `ResourceBundle.getBundle(...)` ném `MissingResourceException` vì không thể tải bundle thích hợp từ classpath/module.
- **Có bundle nhưng thiếu key:** `bundle.getString("some.key")` cũng có thể ném `MissingResourceException` vì key không có trong bundle được chọn và các parent.

Cùng tên ngoại lệ **không đồng nghĩa cùng cách sửa**. Hãy kiểm tra **base name, classpath, JAR entries** khi lỗi xảy ra tại `getBundle`; kiểm tra **key names và parent hierarchy** khi lỗi ở `getString`.

## 10. Encoding: ResourceBundle .properties và Java 9+

Đối với Java 17+, file `.properties` của `PropertyResourceBundle` được đọc theo **UTF-8** theo mặc định (thay đổi từ Java 9, JEP 226). Nếu file không phải UTF-8 hợp lệ, implementation mặc định thử **ISO-8859-1** để tương thích một số tài nguyên cũ.

Có thể dùng thuộc tính hệ thống `java.util.PropertyResourceBundle.encoding` với giá trị `UTF-8` hoặc `ISO-8859-1` để cố định cách đọc. Thuộc tính này được xét khi `PropertyResourceBundle` khởi tạo; không thay giá trị runtime rồi kỳ vọng mọi bundle đã cache sẽ giải mã lại.

Điểm cần phân biệt:

| API | Quy tắc charset |
| --- | --- |
| `PropertyResourceBundle(InputStream)`, Java 9+ | UTF-8 trước, fallback ISO-8859-1 khi byte không hợp lệ, trừ cấu hình cố định |
| `Properties.load(InputStream)` | Theo đặc tả truyền thống, giải mã byte ISO-8859-1; **không** phải UTF-8 mặc định |
| `Properties.load(Reader)` | Dùng ký tự do Reader đã giải mã theo charset của nó |
| `ResourceBundle.getBundle(...)` tìm property bundles | Theo cơ chế `PropertyResourceBundle`/provider và môi trường classpath/module tương ứng |

**JDK 18 chuyển charset mặc định sang UTF-8 (JEP 400) không phải nguyên nhân của thay đổi JEP 226**: quy tắc property resource bundle UTF-8 đã có từ Java 9.

### Một số lỗi do công cụ build làm biến đổi resource

Không chỉ Java runtime, **bước build** cũng có thể ảnh hưởng byte:

- Plugin resource filtering thay các mẫu placeholder trong `.properties`.
- Công cụ build đọc file với charset không phù hợp rồi ghi lại, gây mojibake.
- File thực tế được lưu trong legacy encoding nhưng code/tài liệu nói UTF-8.
- Lỗi escape của `.properties`: ký tự `=`, `:`, `#`, `!`, `\\` và dòng nối có ý nghĩa cú pháp; không nên tự kết luận tệp resource là một file text “key=value” không cần escaping.

Với Java 17+, lưu source properties ở UTF-8 và khai báo encoding của build phù hợp. Chỉ bật Maven/Gradle resource filtering khi thật sự cần; **không** dùng filtering để tự động biến đổi nội dung dịch nếu có nguy cơ ảnh hưởng dấu, dấu nháy hoặc placeholder.

## 11. Named modules (JPMS) và resource bundles

Mô hình classpath thông thường đặt JAR trên `-cp` và lớp nằm trong **unnamed module**. Khi ứng dụng dùng `module-info.java` và chạy bằng `--module-path`, việc tìm resource phải tuân thủ thêm **module encapsulation**.

Các điều quan trọng:

1. Resource bundle nằm **cùng named module** với ứng dụng có thể được tải bởi code bên trong module thông qua `ResourceBundle.getBundle(baseName, locale)`.
2. Resource bundle trong **module khác** không mặc định mở cho mọi nơi đọc; khả năng truy cập còn phụ thuộc module exports/opens và cơ chế tìm qua module.
3. API Java 9+ hỗ trợ `ResourceBundle.getBundle(baseName, locale, module)` để tìm trên danh nghĩa một module cụ thể.
4. Resource bundle có thể được cung cấp qua **`ResourceBundleProvider` service** giữa các modules, với `uses`/`provides` phù hợp.
5. Một số overload `getBundle` nhận `ResourceBundle.Control` **không hỗ trợ trong named module**; dùng đúng quy tắc JPMS và APIs hiện đại.

Ví dụ một câu lệnh ở ngữ cảnh module có ý nghĩa:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"),
        Main.class.getModule());
```

Đây là **snippet**, yêu cầu resource nằm trong module được chỉ định/được module đó truy cập theo quy tắc đóng gói; không bảo đảm tự tìm resource bị ẩn ở module không liên quan.

**Đừng giải quyết lỗi bằng cách tự ý mở toàn bộ module ra bên ngoài.** Hãy kiểm tra bundle nằm cùng module hay module khác, module được cấp quyền gì và API nào đang gọi. Xem phần *Resource Bundles and Named Modules* của Javadoc chính thức.

## 12. Spring Boot executable JAR khác JAR classpath thông thường

Một executable JAR của Spring Boot thường có cấu trúc:

```text
BOOT-INF/classes/com/example/app/Main.class
BOOT-INF/classes/com/example/i18n/Messages_vi_VN.properties
BOOT-INF/lib/...
META-INF/MANIFEST.MF
```

Đây là **layout của Spring Boot executable JAR**, không phải tên entry root của một JAR chuẩn chạy trực tiếp bằng `java -cp`. Spring Boot loader tạo classpath runtime từ `BOOT-INF/classes` và các nested JAR phụ thuộc. Vì vậy:

- `jar tf app.jar` có thể cho thấy `BOOT-INF/classes/com/example/i18n/Messages_vi_VN.properties` và vẫn **đúng** đối với Spring Boot.
- Dùng lệnh run chuẩn của Spring Boot, ví dụ `java -jar app.jar` khi manifest/loader đã cấu hình đúng.
- Không áp quy tắc “entry bắt buộc ở gốc JAR” của mục 3 một cách máy móc cho các định dạng executable archive khác nhau.
- Nếu sử dụng **Spring MessageSource** với `spring.messages.basename`, tham số đó tuân theo cách tìm resource của Spring và cấu hình tương ứng, không nhất thiết giống mọi cách dùng `java.util.ResourceBundle`. Cần xem tài liệu và cấu hình Spring cụ thể.

Đường dẫn nguồn vẫn thường là `src/main/resources`. Khác biệt là **cách Boot đóng gói và load resource**. Khi debug, xác định **loại JAR** trước, rồi mới quyết định entry nào là đúng.

## 13. ClassLoader và bẫy đóng gói đa JAR

Trong hệ thống thực, bundle có thể nằm ở module phụ thuộc hoặc một JAR riêng. Khi đó:

- Cần đặt JAR chứa resources trên **runtime classpath** (hoặc module path với quy tắc phù hợp).
- Một resource có thể tồn tại ở nhiều JAR khác nhau với **cùng một path**. Thứ tự/chiến lược tra cứu của classloader có thể quyết định file nào được chọn; không nên dựa vào sự trùng path.
- Trong plugin systems, application servers, thread context class loaders có thể khác classloader của lớp ứng dụng. `ResourceBundle.getBundle(baseName, locale, loader)` hoặc overload module có thể hữu ích khi cần chỉ rõ môi trường tải.
- Trên Java 9+, cache bundle có thể gắn với classloader/module và locale. Thay đổi JAR ngoài đĩa không bắt buộc làm bundle đang sống trong JVM tự động reload.
- `ResourceBundle.clearCache()` tồn tại cho một số tình huống reload kiểm thử, nhưng không thay thế thiết kế cập nhật resource có quản lý classloader và lifetime phù hợp.

Một chương trình đơn giản không cần custom classloader. Chỉ dùng các overload nâng cao khi hệ thống thật sự có các loader hoặc module khác nhau. Đừng viết code để quét toàn bộ filesystem tìm file `Messages*.properties` nếu lỗi chủ yếu là sai classpath.

## 14. Quy trình chẩn đoán MissingResourceException có hệ thống

Khi lỗi xảy ra sau khi đóng gói:

### Bước 1. Xác định nơi ném lỗi

- `getBundle(base, locale)` lỗi → kiểm tra bundle/resource path và runtime loader.
- `getString(key)` lỗi → kiểm tra tên key, các file parent và bundle locale được chọn.

### Bước 2. Ghi chính xác base name và locale

```java
System.out.println("Bundle base: " + baseName);
System.out.println("Requested locale: " + locale.toLanguageTag());
```

Đây là snippet, với `baseName` và `locale` đã được tạo.

Chú ý viết hoa/thường ở tên thư mục, tên tệp và hậu tố locale, ví dụ `Messages_vi_VN.properties` khác `messages_vi_vn.properties` trên nhiều môi trường. Hãy tuân theo tên mà `ResourceBundle` sinh ra, không tự đổi `vi_VN` thành `vi-VN` trong tên file chỉ vì BCP 47 dùng dấu gạch nối.

### Bước 3. Kiểm tra classpath output và artifact

Với Maven:

```bash
mvn -q clean package
jar tf target/bundle-demo-1.0.0.jar
```

Với Gradle: kiểm tra `build/resources/main` rồi `jar tf build/libs/<actual-name>.jar`. Với Spring Boot: xem `BOOT-INF/classes`, không chỉ root entry.

### Bước 4. So sánh đường dẫn cần tìm với entry thực

```text
Expected: com/example/i18n/Messages_vi_VN.properties
Actual:   src/main/resources/com/example/i18n/Messages_vi_VN.properties
```

Trường hợp này là **file có trong JAR nhưng sai path**. Sửa build packaging/copy root, không sửa locale hay chuyển charset.

### Bước 5. Kiểm tra đúng JAR đang chạy

Đôi khi `jar tf` được chạy trên artifact mới nhất nhưng deployment lại chạy bản cũ hoặc một JAR khác tên. Xác nhận script, container image, `-cp`, `-jar`, module path và classloader thực tế.

### Bước 6. Kiểm tra runtime getResource

```java
String resourcePath =
        "com/example/i18n/Messages_vi_VN.properties";
boolean found = Main.class.getClassLoader()
        .getResource(resourcePath) != null;
System.out.println(found);
```

Đây là snippet. Nếu `false`, classloader đang dùng **không tìm thấy đúng path**. Nếu `true` nhưng `getBundle` vẫn lỗi, kiểm tra base name, candidate locale, format, module constraints, bundle class/property xung đột hoặc loader khác nhau.

### Bước 7. Tách lỗi encoding khỏi lỗi tìm resource

Nếu `getBundle` và `getString` **thành công** nhưng dấu tiếng Việt thành chuỗi sai, resource có thể đã được tải đúng path nhưng byte bị chuyển mã sai hoặc console hiển thị sai. Khi đó mới kiểm tra UTF-8, resource filtering và output encoding.

## 15. Bảng đối chiếu lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| IDE chạy, JAR không chạy | Resource chưa vào JAR | Đặt file trong `src/main/resources`; xem `jar tf` |
| JAR có file nhưng `MissingResourceException` | Entry bị thêm tiền tố `src/main/resources/` hoặc `resources/` | Đóng gói **nội dung** resource root vào root JAR |
| `getBundle("Messages", locale)` không tìm thấy | Base name thiếu package | Dùng `com.example.i18n.Messages` khi file ở package tương ứng |
| Truyền `Messages_vi_VN.properties` làm base name | Base name không phải file name | Bỏ extension và locale suffix; truyền base name |
| `.properties` nằm trong `src/main/java` | Build không copy non-code files ở source tree | Chuyển sang `src/main/resources` |
| Lỗi chỉ xảy ra trên Linux | File/package khác chữ hoa/thường | Kiểm tra case của path và suffix |
| `getString` thiếu key dù bundle tồn tại | Key không nằm trong bundle hoặc parent | Kiểm tra parent chain và tên key |
| Hiển thị ngôn ngữ khác mong đợi | Locale/default locale và fallback | Truyền locale tường minh; kiểm tra `getLocale()` |
| Đọc được nhưng chữ tiếng Việt lỗi | Encoding resource hoặc console | Xác nhận UTF-8, JEP 226, pipeline output |
| `getResourceAsStream` trả null | Classpath root sai, path có `/` đầu khi dùng ClassLoader | Dùng đúng path tương đối classpath root |
| `new File("src/main/resources/...")` lỗi khi deploy | Working directory khác, source tree không tồn tại | Dùng `getResourceAsStream`/`getBundle` |
| `java -jar` báo thiếu main manifest | JAR chưa có `Main-Class` | Cấu hình manifest hoặc chạy `java -cp jar Main` |
| `java -cp` trên Boot fat JAR không hoạt động | Nested `BOOT-INF` layout | Chạy qua Boot loader/`java -jar` đúng cách |
| Named module không thấy bundle | Module encapsulation hoặc loader không đúng | Xem JPMS ResourceBundle docs và cách mở package hợp lệ |
| Locale thay nhưng vẫn thấy nội dung cũ | Bundle cache/classloader sống lâu | Kiểm tra deployment, cache/reload strategy |
| Một bundle bị load nhầm từ dependency | Trùng resource path trong nhiều JAR | Đặt tên namespace riêng; kiểm tra classloader |
| Build filtering làm hỏng placeholder | Plugin xử lý resource text ngoài ý muốn | Cấu hình excludes/encoding/filtering đúng |
| Tên file `Messages_vi-VN.properties` | Sai convention underscore của bundle locale file | Dùng `Messages_vi_VN.properties` |
| Không có root file | Fallback không như dự kiến hoặc không có bundle phù hợp | Cân nhắc tạo `Messages.properties` làm root fallback |

## 16. Kiểm thử tự động sau khi package

Kiểm thử ở IDE chưa đủ, vì IDE có thể tự động đưa `src/main/resources` lên runtime classpath. Nên có **smoke test trực tiếp trên JAR thành phẩm**.

Với dự án Maven tối thiểu trong bài:

```bash
mvn -q clean package
jar tf target/bundle-demo-1.0.0.jar
java -cp target/bundle-demo-1.0.0.jar com.example.app.Main
```

Các kỳ vọng cần đạt:

1. JAR chứa đúng entry `com/example/i18n/Messages_vi_VN.properties`.
2. Output `Bundle locale: vi-VN`.
3. `Greeting: Xin chào từ Việt Nam`.
4. Key `app.title` kế thừa `vi` và `only.base` kế thừa root.
5. `Resource in classpath: true`.
6. Test **sau khi di chuyển JAR** sang một thư mục khác vẫn chạy bằng `java -cp /path/to/jar com.example.app.Main`, không cần source tree.
7. Nếu chạy trong container, đường dẫn resource được tìm từ **artifact/runtime classpath**, không phải từ current working directory.

### Bất biến hữu ích cho pipeline

- **Tất cả bundle variants cần thiết được đóng gói** vào đúng path.
- **Mỗi base name có root bundle** khi sản phẩm yêu cầu fallback ổn định.
- Các key bắt buộc được kiểm tra trong các locale sản phẩm hỗ trợ.
- Không có duplicate resource path ngoài chủ đích.
- Build artifact có checksum/version đúng với bản đang deploy.
- Không dựa vào file tồn tại trong source tree để đọc resource ở runtime.

Với hệ thống cần kiểm thử chặt, có thể viết integration test chạy `java -cp artifact.jar Main` sau build. Lỗi source-resource root thường chỉ được phát hiện ở bước này.

## 17. Bài tập thực hành và đáp án

**Câu 1.** Tệp `src/main/resources/com/acme/i18n/Labels_fr_CA.properties` tương ứng base name nào?

**Đáp án:** `com.acme.i18n.Labels`. Locale tương ứng `fr-CA`. JAR classpath thông thường phải chứa `com/acme/i18n/Labels_fr_CA.properties`.

**Câu 2.** Vì sao file `src/main/resources/Labels_vi.properties` không được tìm khi gọi `getBundle("com.acme.Labels", Locale.forLanguageTag("vi"))`?

**Đáp án:** Base name quy định package `com.acme`, nên Java tìm `com/acme/Labels_vi.properties` từ classpath root. File đặt ở gốc resources lại có path `Labels_vi.properties`, không khớp.

**Câu 3.** Tệp `Messages_vi_VN.properties` đã xuất hiện trong `jar tf` nhưng dưới `src/main/resources/com/example/i18n`. Có đủ không?

**Đáp án:** Không đối với base name trong ví dụ. Java tìm dưới `com/example/i18n` tính từ classpath root/JAR root, không phải dưới thư mục `src/main/resources` nằm bên trong JAR.

**Câu 4.** Nếu `Messages_vi_VN.properties` không có `app.title` mà `Messages_vi.properties` có, `getString("app.title")` trả gì?

**Đáp án:** Theo parent bundle chain, trả giá trị `Ứng dụng bản địa hóa` từ `Messages_vi.properties`.

**Câu 5.** Vì sao `java -cp bundle-demo.jar com.example.app.Main` chạy được nhưng `java -jar bundle-demo.jar` báo thiếu main manifest?

**Đáp án:** `-cp` chỉ định JAR trong classpath và tên lớp Main tường minh; `-jar` yêu cầu manifest/launcher phù hợp. Đây là hai khái niệm khác với việc resource đã được đóng gói.

**Câu 6.** Có thể sửa bằng `new File("src/main/resources/...")` trong production không?

**Đáp án:** Không nên. Khi đóng gói JAR, source tree không nhất thiết được triển khai. Dùng `ResourceBundle` hoặc `ClassLoader.getResourceAsStream` để đọc entry qua classpath.

**Câu 7.** Vì sao cùng một JAR chạy trong Spring Boot lại có `BOOT-INF/classes` và vẫn load resources được?

**Đáp án:** Spring Boot executable JAR dùng loader bố trí runtime classpath từ layout riêng của nó. Quy tắc root entry của JAR classpath thường không áp trực tiếp lên layout này.

**Câu 8.** Java 17 có đọc được thông điệp tiếng Việt trực tiếp trong `.properties` lưu UTF-8 không?

**Đáp án:** Có đối với property resource bundles chuẩn Java 9+, theo JEP 226. Đừng nhầm với `Properties.load(InputStream)` vốn có quy tắc ISO-8859-1.

**Câu 9.** `getBundle(...)` thành công nhưng `getString("missing.key")` thất bại. Cần sửa packaging trước tiên không?

**Đáp án:** Không nhất thiết. Hãy kiểm tra key ở bundle và các parent. `MissingResourceException` có thể là lỗi **thiếu key**, không phải lỗi thiếu file.

**Câu 10.** Muốn chắc JAR deploy không phụ thuộc IDE, test nào đáng tin?

**Đáp án:** Chạy `jar tf` kiểm tra entry, sau đó chạy trực tiếp JAR thành phẩm bằng runtime launcher/classpath phù hợp từ môi trường **không có source tree**.

## 18. Tổng kết

- **Base name** dùng dấu chấm, **resource path** dùng dấu `/`; với `com.example.i18n.Messages` và `vi-VN`, file cần có path `com/example/i18n/Messages_vi_VN.properties` từ classpath root.
- Trong Maven/Gradle chuẩn, để các file trong `src/main/resources` để build tool tự copy và đóng gói; không lồng thêm nguyên thư mục `src/main/resources` bên trong JAR.
- **Xác minh JAR thành phẩm bằng `jar tf`** và chạy thử artifact trực tiếp; chạy được trong IDE chưa chứng minh package đúng.
- `ResourceBundle.getBundle` thực hiện tìm variant theo locale và fallback key. `ClassLoader.getResourceAsStream` dùng để đọc resource cụ thể; `new File(...)` không phù hợp cho entry nằm trong JAR.
- Java 9+ có quy tắc UTF-8 cho property resource bundles. Lỗi resource path, thiếu key, encoding và lỗi manifest/launcher là các loại vấn đề **khác nhau**.
- Named modules và Spring Boot executable JAR có mô hình tìm resources/đóng gói riêng; kiểm tra đúng kiểu runtime trước khi sửa.

**Tài liệu chính thức và tham khảo:**

- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [OpenJDK JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226)
- [Maven Resources Plugin — Resource directories](https://maven.apache.org/plugins/maven-resources-plugin/examples/resource-directory.html)
- [Gradle Java Plugin — Project layout and resources](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Java SE 21 — jar tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
