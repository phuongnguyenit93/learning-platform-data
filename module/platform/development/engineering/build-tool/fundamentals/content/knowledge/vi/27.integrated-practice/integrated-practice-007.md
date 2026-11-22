# Tái hiện lỗi thiếu thư viện, lệch phiên bản và sai JDK

Một ứng dụng Java có thể biên dịch thành công nhưng vẫn thất bại khi chạy. Ba nguyên nhân thường gặp là thiếu thư viện trên classpath, compile và runtime dùng hai phiên bản API không tương thích, hoặc bytecode được tạo bởi JDK mới hơn JDK đang chạy ứng dụng. Cả ba đều có thể xuất hiện trong môi trường local, IDE, CI hoặc production, nhưng mỗi loại lỗi cần một cách tái hiện và chẩn đoán khác nhau.

Bài thực hành này xây dựng ba tình huống có chủ đích, quan sát thông báo lỗi, truy vết cấu hình và sửa nguyên nhân. Mục tiêu là hiểu mối liên hệ giữa dependency configuration, dependency graph, runtime classpath, compiler toolchain và JVM thực thi. Các bước tập trung vào Gradle để có thể quan sát rõ compile/runtime configurations; phần cuối có thêm cách kiểm tra tương đương trong Maven.

## 1. Mục tiêu và chuẩn bị

Sau bài thực hành, người học có thể:

- Tái hiện lỗi compile khi thư viện chỉ có trên runtime classpath.
- Tái hiện lỗi runtime khi thư viện chỉ có trên compile classpath.
- Phân biệt `ClassNotFoundException` với `NoClassDefFoundError` ở các tình huống phổ biến.
- Tạo hai version của cùng một thư viện và tái hiện `NoSuchMethodError`.
- So sánh compile classpath với runtime classpath bằng `dependencies` và `dependencyInsight`.
- Tái hiện `UnsupportedClassVersionError` khi compile bằng JDK 21 rồi chạy bằng JDK 17.
- Phân biệt JVM chạy Gradle, JDK dùng để compile và JDK dùng để chạy ứng dụng.
- Sửa từng lỗi và xác minh bằng đúng lệnh/tác vụ đã gây lỗi.

Chuẩn bị:

- Gradle Wrapper trong project mẫu hoặc có thể tạo một project Java mới bằng Gradle.
- Kết nối repository dependency nếu dùng ví dụ Apache Commons Text.
- Với bài JDK mismatch, cài JDK 17 và JDK 21 song song.
- Terminal PowerShell trên Windows hoặc shell tương đương trên Linux/macOS.
- Có thể chạy `java -version`, `javac -version` và `./gradlew --version`.

Không cần xóa Gradle User Home hay cache toàn máy để tái hiện các lỗi này. Hãy dùng một project lab riêng để tránh ảnh hưởng build khác.

## 2. Bản đồ ba nhóm lỗi

| Tình huống | Giai đoạn lỗi | Thông báo thường gặp | Điều cần kiểm tra |
|---|---|---|---|
| Dependency chỉ có trên runtime classpath nhưng source cần nó khi compile | Compile | `package ... does not exist`, `cannot find symbol` | `compileClasspath`, dependency configuration. |
| Dependency chỉ có trên compile classpath nhưng ứng dụng cần nó khi chạy | Runtime | `NoClassDefFoundError` hoặc `ClassNotFoundException` | `runtimeClasspath`, classloader và artifact đóng gói. |
| Compile bằng API version mới, runtime nạp API version cũ | Runtime linkage | `NoSuchMethodError`, đôi khi `NoSuchFieldError` | Version ở compile/runtime graph và JAR thực tế được nạp. |
| Compile tạo bytecode mới hơn khả năng của JVM runtime | Khi JVM đọc class | `UnsupportedClassVersionError` | Class file major version và JDK runtime thực tế. |

Ba nhóm lỗi có thể cùng xuất hiện sau một lần nâng cấp dependency/JDK. Vì vậy, hãy bắt đầu từ exception và giai đoạn lỗi, sau đó kiểm tra đúng classpath hoặc JDK liên quan.

## 3. Thực hành 1: thiếu thư viện trên compile classpath

Trong tình huống đầu tiên, source code dùng một class bên ngoài nhưng dependency được khai báo bằng `runtimeOnly`. Gradle chỉ đưa dependency đó vào runtime classpath, nên compiler không thể tìm thấy class.

### 3.1. Tạo project mẫu

Tạo một project Java với cấu trúc:

```text
missing-library-lab/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
```

`settings.gradle`:

```groovy
rootProject.name = 'missing-library-lab'
```

`src/main/java/demo/Main.java`:

```java
package demo;

import org.apache.commons.text.StringEscapeUtils;

public class Main {
    public static void main(String[] args) {
        String input = "<h1>Hello</h1>";
        System.out.println(StringEscapeUtils.escapeHtml4(input));
    }
}
```

Class `StringEscapeUtils` thuộc Apache Commons Text. Ứng dụng gọi method `escapeHtml4` để minh họa một API từ thư viện ngoài.

### 3.2. Cấu hình sai có chủ đích

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    runtimeOnly 'org.apache.commons:commons-text:1.12.0'
}

application {
    mainClass = 'demo.Main'
}
```

Chạy compile:

```bash
./gradlew compileJava
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat compileJava
```

Kết quả mong đợi là compile thất bại với lỗi tương tự:

```text
package org.apache.commons.text does not exist
cannot find symbol
  symbol:   variable StringEscapeUtils
```

Thông báo cụ thể có thể khác theo compiler và Gradle version. Nguyên nhân là `runtimeOnly` không cung cấp thư viện cho compile classpath của mã nguồn chính.

### 3.3. Xác nhận bằng dependency report

Xem compile classpath:

```bash
./gradlew dependencies --configuration compileClasspath
```

Xem runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Có thể tìm riêng dependency:

```bash
./gradlew dependencyInsight --dependency commons-text --configuration compileClasspath
./gradlew dependencyInsight --dependency commons-text --configuration runtimeClasspath
```

Kết quả mong đợi:

- `commons-text` không xuất hiện trong `compileClasspath`.
- `commons-text` xuất hiện trong `runtimeClasspath`.

Dependency đã được khai báo nhưng nằm sai configuration so với cách source sử dụng nó.

### 3.4. Sửa cấu hình

Đổi `runtimeOnly` thành `implementation`:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-text:1.12.0'
}
```

Chạy lại:

```bash
./gradlew clean run
```

Kết quả mong đợi là ứng dụng chạy và in nội dung HTML đã escape, ví dụ:

```text
&lt;h1&gt;Hello&lt;/h1&gt;
```

`implementation` đưa dependency vào compile classpath và runtime classpath của project. Đây là scope phù hợp khi mã nguồn chính trực tiếp gọi API của thư viện và ứng dụng cần thư viện đó khi chạy.

### 3.5. Biến thể: compile thành công nhưng runtime thiếu class

Để quan sát lỗi ngược lại, đổi dependency thành:

```groovy
dependencies {
    compileOnly 'org.apache.commons:commons-text:1.12.0'
}
```

Sau đó chạy:

```bash
./gradlew clean compileJava
./gradlew run
```

Compile có thể thành công vì `compileOnly` cung cấp API cho compiler. Nhưng `compileOnly` không đưa thư viện vào runtime classpath. Khi JVM cần nạp `StringEscapeUtils`, ứng dụng có thể ném:

```text
java.lang.NoClassDefFoundError: org/apache/commons/text/StringEscapeUtils
```

Trong trường hợp code gọi `Class.forName("org.apache.commons.text.StringEscapeUtils")`, thông báo có thể là `ClassNotFoundException` vì code đang yêu cầu classloader nạp class theo tên.

Sửa lại bằng `implementation` nếu thư viện cần cả compile và runtime. Chỉ dùng `compileOnly` khi môi trường chạy thực sự cung cấp dependency, ví dụ một API do application server hoặc container đảm nhiệm.

## 4. Thực hành 2: tái hiện `NoSuchMethodError` bằng hai version của cùng artifact

Tình huống này mô phỏng một ứng dụng được compile với thư viện version 2.0 nhưng runtime lại nạp version 1.0. Để không phụ thuộc vào một API bên thứ ba cụ thể, ta tự tạo hai version của một thư viện nhỏ và publish chúng vào Maven repository cục bộ của project.

### 4.1. Cấu trúc lab

```text
version-mismatch-lab/
├── settings.gradle
├── build.gradle
├── api-v1/
│   ├── build.gradle
│   └── src/main/java/com/acme/training/MessageApi.java
├── api-v2/
│   ├── build.gradle
│   └── src/main/java/com/acme/training/MessageApi.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/Main.java
```

`settings.gradle`:

```groovy
rootProject.name = 'version-mismatch-lab'
include 'api-v1', 'api-v2', 'app'
```

### 4.2. Khai báo publishing cho hai version

Root `build.gradle`:

```groovy
allprojects {
    group = 'com.acme.training'
}

tasks.register('publishTrainingApis') {
    dependsOn(
        ':api-v1:publishMavenJavaPublicationToTrainingRepository',
        ':api-v2:publishMavenJavaPublicationToTrainingRepository'
    )
}
```

`api-v1/build.gradle`:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

version = '1.0.0'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifactId = 'message-api'
        }
    }

    repositories {
        maven {
            name = 'training'
            url = rootProject.layout.buildDirectory.dir('repo').get().asFile.toURI()
        }
    }
}
```

`api-v2/build.gradle` có cùng cấu hình, chỉ thay:

```groovy
version = '2.0.0'
```

Hai project publish cùng tọa độ group/artifact nhưng khác version vào repository dưới `build/repo` của root project.

### 4.3. Tạo API version 1.0.0

`api-v1/src/main/java/com/acme/training/MessageApi.java`:

```java
package com.acme.training;

public class MessageApi {
    public String format(String value) {
        return value.trim();
    }
}
```

Version 1.0.0 chỉ cung cấp `format(String)`.

### 4.4. Tạo API version 2.0.0

`api-v2/src/main/java/com/acme/training/MessageApi.java`:

```java
package com.acme.training;

import java.util.Locale;

public class MessageApi {
    public String format(String value) {
        return value.trim();
    }

    public String format(String value, Locale locale) {
        return value.trim().toUpperCase(locale);
    }
}
```

Version 2.0.0 có thêm overload `format(String, Locale)`. Code cũ vẫn tồn tại, nhưng ứng dụng mới có thể gọi overload mới.

### 4.5. Cấu hình ứng dụng để cố ý lệch version

`app/build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    maven {
        name = 'training'
        url = rootProject.layout.buildDirectory.dir('repo').get().asFile.toURI()
    }
}

dependencies {
    compileOnly 'com.acme.training:message-api:2.0.0'
    runtimeOnly 'com.acme.training:message-api:1.0.0'
}

application {
    mainClass = 'demo.Main'
}
```

`app/src/main/java/demo/Main.java`:

```java
package demo;

import com.acme.training.MessageApi;
import java.util.Locale;

public class Main {
    public static void main(String[] args) {
        MessageApi api = new MessageApi();
        System.out.println(api.format("hello", Locale.US));
    }
}
```

Điểm cố ý trong cấu hình:

- `compileOnly` version `2.0.0` làm method overload mới hiển thị với compiler.
- `runtimeOnly` version `1.0.0` đưa bản cũ vào runtime classpath.
- Hai dependency nằm ở hai configuration khác nhau nên compile graph và runtime graph có thể chọn version khác nhau.

### 4.6. Publish hai version và chạy ứng dụng

Tại root project, chạy trước:

```bash
./gradlew publishTrainingApis
```

Sau khi hai artifact đã được publish, chạy:

```bash
./gradlew :app:run
```

Compile có thể thành công vì compiler nhìn thấy version 2.0.0. Khi chạy, JVM nạp class `MessageApi` từ version 1.0.0 và không tìm thấy descriptor của `format(String, Locale)`. Kết quả mong đợi:

```text
java.lang.NoSuchMethodError: 'java.lang.String com.acme.training.MessageApi.format(java.lang.String, java.util.Locale)'
    at demo.Main.main(Main.java:...)
```

Dòng số trong stack trace phụ thuộc file và compiler. Lỗi có thể chỉ xuất hiện khi gọi overload mới; nếu code chỉ gọi `format(String)`, runtime version 1.0.0 vẫn có method đó và chương trình có thể chạy.

### 4.7. Xác nhận compile graph và runtime graph

Chạy:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
```

Tìm riêng module:

```bash
./gradlew :app:dependencyInsight --dependency message-api --configuration compileClasspath
./gradlew :app:dependencyInsight --dependency message-api --configuration runtimeClasspath
```

Kết quả cần xác nhận:

| Configuration | Version được resolve |
|---|---|
| `compileClasspath` | `com.acme.training:message-api:2.0.0` |
| `runtimeClasspath` | `com.acme.training:message-api:1.0.0` |

Đây là bằng chứng trực tiếp cho thấy compiler và runtime dùng hai version khác nhau.

Có thể kiểm tra API trong từng JAR:

```bash
javap -classpath build/repo/com/acme/training/message-api/1.0.0/message-api-1.0.0.jar -p -s com.acme.training.MessageApi
javap -classpath build/repo/com/acme/training/message-api/2.0.0/message-api-2.0.0.jar -p -s com.acme.training.MessageApi
```

Version 1.0.0 không có descriptor nhận `String` và `Locale`; version 2.0.0 có descriptor đó. `javap` giúp xác minh API thực tế trong artifact thay vì chỉ suy luận từ tên version.

### 4.8. Sửa lệch version

Nếu ứng dụng cần overload mới, runtime phải dùng version có overload đó. Thay dependency declaration trong `app/build.gradle` bằng:

```groovy
dependencies {
    implementation 'com.acme.training:message-api:2.0.0'
}
```

Xóa hai khai báo `compileOnly` và `runtimeOnly` cũ để tránh giữ cấu hình mâu thuẫn. Chạy lại:

```bash
./gradlew :app:run
```

Kết quả mong đợi:

```text
HELLO
```

Nếu chưa thể nâng runtime lên 2.0.0, lựa chọn khác là sửa caller để chỉ dùng API mà version 1.0.0 cung cấp, hoặc nâng dependency consumer đang kéo API cũ. Không nên chỉ force version mới khi chưa xác nhận tất cả consumer tương thích.

## 5. Thực hành 3: tái hiện sai JDK và `UnsupportedClassVersionError`

Class file Java có version riêng. JVM chỉ đọc được class file có major version nằm trong phạm vi mà runtime hỗ trợ. Nếu compile bằng JDK mới nhưng chạy bằng JDK cũ, JVM có thể báo `UnsupportedClassVersionError`.

### 5.1. Quan hệ giữa JDK và class file version

Một số mốc thường gặp:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Ví dụ, JDK 21 tạo class file major version 65. JVM Java 17 chỉ hỗ trợ đến major version 61. Nếu chạy class version 65 bằng Java 17, JVM không thể đọc bytecode.

### 5.2. Tạo chương trình Java đơn giản

`src/Main.java`:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("Running on the selected Java runtime");
    }
}
```

Code không dùng API riêng của Java 21. Lỗi trong bài lab đến từ class file version, không phải từ việc source gọi API mới.

### 5.3. Compile bằng JDK 21, chạy bằng JDK 17

Trên Windows PowerShell, đặt hai đường dẫn JDK theo máy thực tế:

```powershell
$env:JAVA21_HOME = 'C:\Path\To\jdk-21'
$env:JAVA17_HOME = 'C:\Path\To\jdk-17'

New-Item -ItemType Directory -Force out | Out-Null
& "$env:JAVA21_HOME\bin\javac.exe" -d out src\Main.java
& "$env:JAVA17_HOME\bin\java.exe" -cp out Main
```

Trên Linux/macOS:

```bash
mkdir -p out
"$JAVA21_HOME/bin/javac" -d out src/Main.java
"$JAVA17_HOME/bin/java" -cp out Main
```

Thay `JAVA21_HOME` và `JAVA17_HOME` bằng đường dẫn JDK đã cài. Lệnh compile tạo bytecode theo mặc định của JDK 21. Lệnh chạy gọi rõ binary Java 17, tránh phụ thuộc `PATH` đang trỏ đến JDK nào.

Kết quả mong đợi tương tự:

```text
Exception in thread "main" java.lang.UnsupportedClassVersionError:
  Main has been compiled by a more recent version of the Java Runtime
  (class file version 65.0), this version of the Java Runtime only
  recognizes class file versions up to 61.0
```

### 5.4. Kiểm tra class file major version

Dùng `javap` từ JDK tương ứng:

```bash
javap -verbose -classpath out Main
```

Tìm dòng:

```text
major version: 65
```

Điều này xác nhận class được compile với target Java 21. Nếu dùng `javap` JDK 17, công cụ vẫn có thể hiển thị metadata của class file mới dù JVM 17 không chạy được class đó.

### 5.5. Sửa lỗi bằng cách chọn runtime phù hợp

Nếu ứng dụng yêu cầu Java 21, chạy bằng JDK 21:

```powershell
& "$env:JAVA21_HOME\bin\java.exe" -cp out Main
```

Hoặc trên Linux/macOS:

```bash
"$JAVA21_HOME/bin/java" -cp out Main
```

Kết quả mong đợi:

```text
Running on the selected Java runtime
```

Nếu sản phẩm phải chạy trên Java 17, cần compile với target tương thích Java 17 và tránh sử dụng API chỉ có từ Java 18 trở lên. Với `javac` 21:

```bash
"$JAVA21_HOME/bin/javac" --release 17 -d out src/Main.java
"$JAVA17_HOME/bin/java" -cp out Main
```

`--release 17` giới hạn source language, class file target và Java platform API ở mức Java 17. Chỉ đổi target bytecode mà không kiểm soát API có thể tạo artifact có class version 61 nhưng lại tham chiếu method chỉ có ở JDK mới hơn; khi chạy có thể gặp lỗi khác như `NoSuchMethodError`/`NoClassDefFoundError` trong API platform.

## 6. JDK chạy Gradle, JDK compile và JDK runtime là ba vai trò cần phân biệt

Một dự án có thể dùng nhiều JDK trong cùng quy trình:

| Vai trò | Dùng để làm gì? | Cách kiểm tra |
|---|---|---|
| Gradle JVM/daemon JVM | Chạy Gradle, load plugin và build logic. | `./gradlew --version`; kiểm tra `JAVA_HOME`/Gradle JVM trong IDE. |
| Compiler toolchain | Chạy `javac`/compiler được Gradle chọn để compile source. | `./gradlew -q javaToolchains`; xem `java.toolchain` và log compile. |
| Application runtime | Chạy chương trình, test fork hoặc service. | `java -version`, launch command, `JavaExec.javaLauncher` hoặc runtime/container config. |

`./gradlew --version` cho biết JVM chạy Gradle trong lần gọi đó. Nó không nhất thiết là JDK dùng để compile nếu project cấu hình Java Toolchains. Tương tự, JDK mà IDE dùng để chạy ứng dụng có thể khác với JDK trong terminal hoặc container production.

### 6.1. Khai báo Java Toolchain trong Gradle

Ví dụ `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'demo.Main'
}
```

Toolchain yêu cầu Gradle chọn JDK 21 cho các task Java được tích hợp với toolchain. Gradle có thể dùng một JVM khác để chạy daemon, miễn là phiên bản Gradle hỗ trợ JVM đó.

Xem các toolchain Gradle phát hiện:

```bash
./gradlew -q javaToolchains
```

Chạy:

```bash
./gradlew --version
java -version
javac -version
```

Ba lệnh cung cấp các góc nhìn khác nhau. Đừng suy ra compiler toolchain chỉ từ `java -version` trong terminal.

### 6.2. Cố ý cấu hình compile JDK 21 nhưng chạy JDK 17 trong Gradle

Nếu máy đã cài cả JDK 17 và 21, có thể cấu hình run task dùng launcher 17 để tái hiện lỗi:

```groovy
tasks.named('run', JavaExec) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Giữ toolchain compile ở Java 21 và target mặc định 21, sau đó chạy:

```bash
./gradlew clean run
```

Compile tạo class version 65, còn `run` dùng launcher Java 17 và có thể báo `UnsupportedClassVersionError`. Đây là lab cố ý tạo sai lệch; không dùng cấu hình này cho build phát hành.

Sửa bằng cách thống nhất runtime với Java 21, hoặc đặt `options.release = 17` nếu sản phẩm cần chạy trên Java 17:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Nếu `run` dùng JDK 17, compiler target 17 sẽ tạo bytecode tương thích Java 17, miễn là code và dependency không yêu cầu runtime mới hơn.

### 6.3. `sourceCompatibility`, `targetCompatibility` và `options.release`

Các thuộc tính này có ý nghĩa khác nhau:

- `sourceCompatibility` xác định mức cú pháp Java mà compiler chấp nhận.
- `targetCompatibility` xác định class file target trong cấu hình compiler truyền thống.
- `options.release` dùng tùy chọn `--release` của javac để đồng thời giới hạn language level, bytecode target và API Java platform.
- Java Toolchain xác định JDK/compiler được sử dụng; nó không tự quyết định ứng dụng production phải chạy JDK nào.

Với build mới, `options.release` thường là cách rõ ràng để đảm bảo compile không vô tình tham chiếu API JDK cao hơn runtime target. Toolchain giúp cố định JDK compiler. Cần kiểm tra cả dependency bên ngoài vì thư viện được resolve cũng có thể yêu cầu runtime Java cao hơn.

## 7. Kiểm tra JDK và bytecode trong dự án thực tế

Khi gặp lỗi JDK, thu thập các thông tin sau:

```bash
java -version
javac -version
./gradlew --version
./gradlew -q javaToolchains
```

Trên Windows, xác định executable đang được tìm thấy qua PATH:

```powershell
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac
```

Kiểm tra compiler task:

```bash
./gradlew compileJava --info
```

Kiểm tra bytecode:

```bash
javap -verbose -classpath build/classes/java/main demo.Main
```

Nếu lỗi xuất hiện trong Docker hoặc application server, chạy lệnh kiểm tra bên trong đúng image/container. JDK local không chứng minh runtime trên server dùng cùng version.

## 8. Maven: kiểm tra dependency graph và JDK tương ứng

Nếu project dùng Maven, có thể dùng các lệnh sau để xem dependency:

```bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dincludes=org.apache.commons:commons-text
```

Dependency `runtime` có thể không xuất hiện trong compile classpath. Dependency `provided` có thể có khi compile nhưng môi trường chạy phải cung cấp. Hãy đọc scope và dependency tree thay vì chỉ tìm tọa độ trong POM.

Để kiểm tra POM sau khi hợp nhất parent/profile:

```bash
mvn help:effective-pom
```

Maven compiler có thể cấu hình release target:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Nếu Maven Toolchains Plugin được dùng, JDK compiler có thể khác JVM đang chạy Maven. Kiểm tra `JAVA_HOME`, Maven toolchains configuration và JDK runtime/container. Đừng nhầm `mvn -version` (JVM chạy Maven) với compiler toolchain được plugin lựa chọn.

## 9. Phân biệt nguyên nhân qua thông báo lỗi

| Thông báo | Diễn giải ban đầu | Kiểm tra tiếp theo |
|---|---|---|
| `package ... does not exist` | Compiler không thấy package trên compile classpath hoặc source/module configuration sai. | `compileClasspath`, dependency scope, source set, module path. |
| `cannot find symbol` | Class/method/field không có trong compile API được compiler nhìn thấy. | Import, version compile, generated sources, compile classpath. |
| `ClassNotFoundException` | Code/framework yêu cầu classloader nạp class theo tên nhưng không tìm thấy. | Runtime classpath, classloader, reflection/service configuration. |
| `NoClassDefFoundError` | JVM cần class nhưng không thể nạp/định nghĩa; có thể do dependency thiếu hoặc class khởi tạo thất bại trước đó. | Runtime classpath và cause chain/static initializer. |
| `NoSuchMethodError` | Caller được compile với method descriptor mà class runtime không cung cấp. | Compile/runtime version, duplicate class, classloader source, `javap`. |
| `NoSuchFieldError` | Caller mong đợi field không có trong class runtime. | Version/API binary compatibility. |
| `UnsupportedClassVersionError` | JVM runtime quá cũ so với class file. | Major version, JDK runtime thật, compiler toolchain và release target. |
| `InaccessibleObjectException` | Reflection bị module encapsulation chặn. | JPMS module/package openness và framework version. |

Thông báo là manh mối, không phải kết luận đầy đủ. Luôn đọc stack trace và phần `Caused by`; `NoClassDefFoundError` có thể là hậu quả của một static initializer đã thất bại trước đó.

## 10. Quy trình chẩn đoán tổng hợp

Khi ứng dụng lỗi trên CI hoặc production, có thể đi theo trình tự sau:

### Bước 1: Tái hiện bằng đúng lệnh

Ghi lại task hoặc lệnh khởi chạy gây lỗi. Nếu lỗi chỉ xuất hiện trong CI, lấy đúng task request, profile, environment và artifact mà CI dùng. Chạy lại `test`, `run` hoặc lệnh deploy tương ứng; không thay đổi dependency ngay lập tức.

### Bước 2: Xác định giai đoạn lỗi

Lỗi ở compile, test runtime, application runtime, class loading hay JVM startup? Giai đoạn này quyết định xem cần kiểm tra `compileClasspath`, `testRuntimeClasspath`, `runtimeClasspath` hay JDK launcher.

### Bước 3: Đọc exception và caller

Ghi lại class/method bị thiếu, descriptor, class file version nếu có và frame đầu tiên thuộc code ứng dụng. Phân biệt lỗi thiếu class với lỗi thiếu method và lỗi không đọc được bytecode.

### Bước 4: Xem dependency graph đúng configuration

Gradle:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency <module> --configuration runtimeClasspath
```

Maven:

```bash
mvn dependency:tree -Dscope=runtime
```

Nếu lỗi xảy ra trong test, kiểm tra test runtime configuration/scope.

### Bước 5: Xác minh artifact và classloader

Dùng `jar tf` để xác nhận class có trong JAR; dùng `javap -p -s` để xác nhận method descriptor; dùng `CodeSource` hoặc class-loading logs để xác định JAR thực tế JVM nạp. Kiểm tra cả thư mục `lib`, fat JAR, container và shared library của server.

### Bước 6: Xác minh JDK từng giai đoạn

So sánh Gradle/Maven JVM, compiler toolchain và application runtime. Kiểm tra class file major version bằng `javap -verbose`. Nếu runtime target là Java 17, bảo đảm compiler release và các dependency tương thích Java 17.

### Bước 7: Sửa đúng tầng và chạy lại

- Thiếu compile dependency: dùng configuration cung cấp thư viện cho compiler.
- Thiếu runtime dependency: đưa dependency vào runtime hoặc xác nhận container cung cấp nó.
- Lệch API version: đồng bộ runtime version, nâng consumer hoặc dùng API tương thích.
- Sai JDK: chọn runtime đủ mới hoặc compile về release target được hỗ trợ.

Sau đó chạy lại đúng lệnh tái hiện lỗi, test liên quan và kiểm tra artifact cuối cùng.

## 11. Bài tập tổng hợp

Thực hiện lần lượt các bài tập sau và ghi lại bằng chứng trước/sau khi sửa.

### Bài tập A: sai dependency configuration

1. Đặt Apache Commons Text vào `runtimeOnly` trong khi source import `StringEscapeUtils`.
2. Chạy `compileJava` và lưu thông báo lỗi.
3. Chạy dependency report cho `compileClasspath` và `runtimeClasspath`.
4. Đổi thành `implementation`, chạy lại `clean run`.
5. Đổi thành `compileOnly`, quan sát compile pass nhưng runtime fail.
6. Trả lại `implementation` và ghi rõ lý do.

Kết quả cần giải thích: tại sao cùng một tọa độ dependency có thể được resolve nhưng vẫn không có ở classpath mà task cần?

### Bài tập B: compile/runtime version skew

1. Tạo `message-api` version 1.0.0 và 2.0.0 theo lab.
2. Publish hai version vào repository local trong project.
3. Cấu hình `compileOnly` 2.0.0 và `runtimeOnly` 1.0.0.
4. Chạy `:app:run` và ghi `NoSuchMethodError`.
5. Chạy `dependencyInsight` cho compile/runtime.
6. Dùng `javap` so sánh method descriptor của hai JAR.
7. Đổi thành `implementation` 2.0.0 và chạy lại.

Kết quả cần giải thích: vì sao compile thành công không chứng minh runtime API tương thích?

### Bài tập C: compiler và runtime JDK khác nhau

1. Compile `Main.java` bằng JDK 21.
2. Chạy class bằng JDK 17.
3. Ghi lại `UnsupportedClassVersionError` và major version.
4. Chạy bằng JDK 21 để xác nhận lỗi do runtime version.
5. Compile lại bằng `--release 17` rồi chạy JDK 17.
6. Kiểm tra `java -version`, `javac -version`, `gradlew --version` và Gradle toolchains.

Kết quả cần giải thích: compiler toolchain và JVM runtime khác nhau ở điểm nào, và `--release` kiểm soát điều gì?

## 12. Bảng ghi kết quả thực hành

| Lab | Cấu hình gây lỗi | Lỗi quan sát được | Bằng chứng cần lưu | Cách sửa |
|---|---|---|---|---|
| Thiếu compile dependency | `runtimeOnly` cho class được import | `package does not exist` / `cannot find symbol` | `compileClasspath` và `runtimeClasspath` | `implementation` hoặc configuration phù hợp. |
| Thiếu runtime dependency | `compileOnly` cho class cần lúc chạy | `NoClassDefFoundError` | Runtime graph, JAR contents, classloader | `implementation` hoặc runtime provider hợp lệ. |
| Lệch thư viện | Compile API 2.0, runtime API 1.0 | `NoSuchMethodError` | `dependencyInsight`, `javap`, `CodeSource` | Đồng bộ version/consumer/API. |
| Sai JDK | Compile bytecode 21, chạy JDK 17 | `UnsupportedClassVersionError` | JDK version, toolchain, major version | Chạy JDK 21 hoặc compile `--release 17`. |

## 13. Những lỗi thường gặp khi làm lab

- **Chỉ xem build file:** dependency có thể đến từ nhánh bắc cầu hoặc configuration khác. Hãy xem graph thực tế.
- **Chỉ xem `compileClasspath`:** lỗi runtime cần `runtimeClasspath` hoặc `testRuntimeClasspath`.
- **Cho rằng Gradle luôn chọn một version cho mọi configuration:** mỗi configuration được resolve độc lập; compile và runtime có thể có kết quả khác nhau.
- **Chỉ xem `java -version`:** lệnh này không chứng minh JDK compiler toolchain hoặc JDK trong container giống nhau.
- **Chỉ đổi `JAVA_HOME`:** IDE, service, daemon và container có thể dùng JDK đã cấu hình riêng.
- **Nhầm `sourceCompatibility` với runtime JDK:** target bytecode và JVM chạy artifact là hai cấu hình riêng.
- **Chỉ sửa version nhưng không kiểm tra artifact deploy:** server có thể vẫn chạy JAR cũ hoặc class từ shared library.
- **Dùng `clean` như cách sửa lỗi:** clean xóa output, không sửa dependency graph, API incompatibility hoặc JDK mismatch.
- **Bỏ qua lỗi trong test chưa đi qua đường code:** `NoSuchMethodError` có thể chỉ xuất hiện khi method mới được gọi.

## 14. Checklist trước khi kết luận đã sửa

- [ ] Đã tái hiện lỗi bằng lệnh xác định và lưu stack trace.
- [ ] Đã xác định lỗi ở compile, test runtime, application runtime hay JVM startup.
- [ ] Đã kiểm tra đúng configuration/classpath tương ứng.
- [ ] Đã xác nhận dependency được khai báo ở scope phù hợp.
- [ ] Đã so sánh version compile và runtime nếu có lỗi linkage.
- [ ] Đã kiểm tra JAR thực tế và method descriptor khi gặp `NoSuchMethodError`.
- [ ] Đã xác định JDK chạy Gradle/Maven, compiler toolchain và runtime.
- [ ] Đã kiểm tra class file major version khi gặp `UnsupportedClassVersionError`.
- [ ] Đã chạy lại đúng lệnh ban đầu sau khi sửa.
- [ ] Đã xác minh artifact cuối cùng và môi trường deploy dùng đúng dependency/JDK.

## 15. Nguyên tắc cần nhớ

Lỗi thiếu thư viện, lệch version và sai JDK đều có thể khiến ứng dụng compile hoặc khởi động không như mong đợi, nhưng chúng nằm ở những lớp khác nhau. Dependency configuration quyết định thư viện có mặt trên compile/runtime classpath; version resolution quyết định API nào được chọn trong từng configuration; compiler toolchain tạo bytecode; JVM runtime đọc và thực thi bytecode đó. Muốn xử lý chính xác, hãy tái hiện lỗi, xác định giai đoạn, xem đúng dependency graph, xác minh artifact thực tế và kiểm tra JDK của từng tiến trình. Khi sửa đúng lớp nguyên nhân và chạy lại đúng tình huống ban đầu, build sẽ đáng tin cậy hơn giữa máy developer, CI và production.
