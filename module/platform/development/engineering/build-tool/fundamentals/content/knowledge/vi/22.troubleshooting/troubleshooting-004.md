# Lỗi biên dịch do phiên bản Java hoặc đường dẫn phụ thuộc

Khi biên dịch một dự án Java, compiler phải đọc được mã nguồn, dùng đúng bộ quy tắc ngôn ngữ và tìm thấy các lớp mà mã nguồn tham chiếu. Nếu JDK được chọn không tương thích với cấu hình source/target, hoặc dependency không có trên classpath/module path, build có thể thất bại dù mã nguồn không có lỗi logic.

Những lỗi này thường xuất hiện dưới dạng `invalid source release`, `release version ... not supported`, `class file has wrong version`, `package ... does not exist`, `cannot find symbol` hoặc `module not found`. Các thông báo có vẻ giống nhau nhưng nguyên nhân khác nhau. Cần xác định compiler nào đang chạy, phiên bản Java mà dự án yêu cầu, cấu hình build đang áp dụng và đường dẫn nào được dùng để tìm dependency.

Bài học này trình bày cách chẩn đoán hai nhóm nguyên nhân chính: **không tương thích phiên bản Java** và **không phân giải được dependency trên compile path**. Ví dụ sử dụng Gradle và Maven, đồng thời phân biệt lỗi biên dịch với lỗi chỉ xuất hiện khi chạy ứng dụng.

## 1. Compiler cần những gì để biên dịch mã Java?

Để biên dịch một file Java, `javac` cần ít nhất:

- Mã nguồn có cú pháp hợp lệ.
- Một phiên bản compiler hiểu cú pháp và tính năng ngôn ngữ được sử dụng.
- Các lớp JDK/API nền tảng tương ứng với phiên bản Java mục tiêu.
- Các dependency cần thiết trên compile classpath hoặc module path.
- Các annotation processor và mã sinh ra nếu dự án sử dụng chúng.
- Các tùy chọn compiler phù hợp như encoding, source/release, lint và processor path.

Ví dụ:

```java
package com.example.order;

import com.fasterxml.jackson.databind.ObjectMapper;

public class OrderJsonReader {
    public Order read(String json) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        return mapper.readValue(json, Order.class);
    }
}
```

Để biên dịch lớp này, compiler phải nhìn thấy `ObjectMapper` từ Jackson trên compile classpath, nhìn thấy `Order` trong source output hoặc dependency phù hợp, và hiểu mọi cú pháp Java được dùng. Nếu Jackson chỉ xuất hiện trên runtime classpath mà không có compile classpath, import sẽ không được giải quyết.

Có thể hình dung:

```text
Java source
    |
    +---- JDK/compiler + source/release options
    |
    +---- Compile classpath / module path
    |
    +---- Annotation processors / generated sources
    |
    v
  javac
    |
    v
  .class files
```

Nếu một thành phần không phù hợp, compiler dừng trước khi tạo được bytecode đầy đủ.

## 2. Phân biệt JDK, JVM, javac và Java runtime

Các khái niệm thường bị gọi chung là “Java version”, nhưng chúng có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| JDK (Java Development Kit) | Bộ công cụ phát triển, bao gồm compiler và các công cụ JDK |
| `javac` | Java compiler, chuyển mã nguồn `.java` thành bytecode `.class` |
| JVM | Máy ảo thực thi bytecode |
| Java runtime | Môi trường chạy ứng dụng, bao gồm JVM và các thư viện runtime cần thiết |
| Java toolchain | Cấu hình build tool chọn JDK/compiler phù hợp cho task compile/test/javadoc |
| Java release target | Mức Java mà bytecode/API đầu ra phải tương thích theo cấu hình compiler |

Máy có thể cài nhiều JDK. `java` trên `PATH` có thể đến từ một JDK, trong khi Gradle daemon hoặc Maven lại chạy bằng một JDK khác. Gradle còn có thể dùng toolchain riêng để biên dịch. Vì vậy, chỉ chạy `java -version` chưa đủ để biết compiler thực tế mà task đang sử dụng.

Ví dụ:

```text
java -version       -> JDK 21
javac -version      -> JDK 21
Gradle daemon       -> JDK 17
Java compile toolchain -> JDK 21
```

Trong cấu hình như trên, Gradle daemon và compiler có thể chạy trên JDK khác nhau. Điều này không nhất thiết là lỗi nếu phiên bản Gradle hỗ trợ JVM chạy daemon đó và toolchain được cấu hình đúng.

## 3. Hiểu `source`, `target` và `--release`

Ba khái niệm này thường bị nhầm lẫn khi build thất bại do phiên bản Java.

### 3.1. `source`

`source` xác định phiên bản cú pháp/ngôn ngữ Java mà compiler chấp nhận. Ví dụ, source 17 cho phép compiler xử lý các tính năng ngôn ngữ thuộc Java 17 theo quy tắc tương ứng.

### 3.2. `target`

`target` xác định phiên bản định dạng bytecode mà compiler tạo ra. Ví dụ, target 17 tạo class file dành cho JVM tương thích với Java 17.

Chỉ đặt `source` và `target` không luôn bảo đảm mã nguồn chỉ sử dụng API có mặt trong Java mục tiêu. Nếu compiler mới biên dịch với source/target cũ nhưng vẫn nhìn thấy API mới của JDK hiện tại, mã có thể biên dịch rồi lỗi khi chạy trên runtime cũ.

### 3.3. `--release`

`--release` (có từ JDK 9) kết hợp việc chọn mức ngôn ngữ, bytecode và tập API Java SE phù hợp với release được chỉ định. Khi có thể, đây thường là lựa chọn rõ ràng hơn cho ứng dụng cần tương thích với một Java release cụ thể.

Ví dụ dùng JDK 21 nhưng tạo output nhắm tới Java 17:

```bash
javac --release 17 -d out src/main/java/com/example/App.java
```

Compiler kiểm tra rằng mã sử dụng cú pháp và API phù hợp với Java 17, rồi tạo bytecode có thể chạy trên runtime Java 17 tương thích. Điều này không có nghĩa mọi thư viện bên ngoài tự động tương thích Java 17; dependency cũng phải có bytecode/API phù hợp.

### 3.4. Bảng so sánh

| Tùy chọn | Kiểm soát | Giới hạn |
|---|---|---|
| `-source` | Cú pháp/ngôn ngữ Java | Không tự giới hạn toàn bộ API JDK nhìn thấy |
| `-target` | Phiên bản bytecode đầu ra | Không tự bảo đảm chỉ dùng API của release mục tiêu |
| `--release` | Ngôn ngữ, bytecode và API Java SE của release mục tiêu | Chỉ hỗ trợ release mà JDK compiler có thể nhắm tới; không kiểm soát API của dependency bên ngoài |

Không nên đặt `source` hoặc `target` cao hơn khả năng của JDK compiler đang chạy. Ví dụ compiler JDK 11 không thể tạo bytecode Java 17 chỉ vì build script đặt `targetCompatibility = 17`.

## 4. Nhận diện lỗi phiên bản Java qua thông báo compiler

### 4.1. `invalid source release: 17`

Thông báo này thường có nghĩa compiler đang được gọi không hỗ trợ source level 17. Một tình huống phổ biến là build dùng JDK 11 nhưng cấu hình yêu cầu source 17.

Kiểm tra:

```bash
java -version
javac -version
```

Sau đó kiểm tra JDK thực tế mà Gradle/Maven dùng. Nếu dự án yêu cầu Java 17, cần chọn compiler JDK đủ mới hoặc điều chỉnh mục tiêu về release phù hợp với yêu cầu dự án.

### 4.2. `release version 17 not supported`

Đây cũng thường là dấu hiệu compiler JDK không hỗ trợ release được yêu cầu. Ví dụ, cấu hình Maven `maven.compiler.release=17` nhưng Maven đang chạy bằng JDK 11.

Đừng nhầm thông báo này với việc ứng dụng chạy bằng Java 17 hay 21. Đây là lỗi ở bước compiler không thể thực hiện yêu cầu release đã cấu hình.

### 4.3. `Source option 5 is no longer supported` hoặc source mặc định quá cũ

Một số build cũ dùng phiên bản Maven Compiler Plugin cũ hoặc không cấu hình release/source. Plugin có thể truyền source level cũ không còn được JDK mới hỗ trợ.

Hướng xử lý thường là cập nhật và pin Maven Compiler Plugin phù hợp, sau đó cấu hình `maven.compiler.release` rõ ràng. Không nên chỉ hạ JDK để làm build cũ chạy nếu dự án cần compiler mới hoặc đã dùng API mới.

### 4.4. `class file has wrong version` hoặc `UnsupportedClassVersionError`

Hai thông báo này liên quan đến class file version nhưng thường xuất hiện ở những thời điểm khác nhau:

- `class file has wrong version` có thể xuất hiện khi compiler hoặc công cụ đọc một dependency `.class` được biên dịch bằng Java mới hơn mức nó hỗ trợ.
- `UnsupportedClassVersionError` thường xuất hiện lúc JVM nạp class có bytecode mới hơn JVM hiện tại có thể chạy.

Ví dụ một số class file major version phổ biến:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Nếu runtime Java 11 gặp class file major 61, dependency hoặc ứng dụng đó cần runtime Java 17 trở lên. Nếu compiler JDK 11 đọc một dependency được biên dịch bằng Java 17, có thể gặp lỗi phiên bản class file trong lúc compile.

Hãy xác định class nào có version không tương thích. Đó có thể là class của chính ứng dụng, dependency bên ngoài, annotation processor hoặc plugin chạy trong JVM build.

### 4.5. Compiler JDK và runtime JDK khác nhau

Có thể biên dịch thành công bằng JDK 21 nhưng chạy thất bại trên JDK 17 nếu build tạo bytecode/API yêu cầu Java 21. Ngược lại, có thể dùng JDK 21 để biên dịch với `--release 17`, rồi chạy trên Java 17 nếu toàn bộ dependency cũng tương thích.

Luôn phân biệt ba câu hỏi:

1. JDK nào chạy Gradle/Maven?
2. JDK nào chạy compiler/test task?
3. Java release thấp nhất mà artifact phải hỗ trợ là bao nhiêu?

## 5. Kiểm tra Java version thực tế trong môi trường build

### 5.1. Kiểm tra từ shell

Linux/macOS:

```bash
which java
which javac
java -version
javac -version
echo "$JAVA_HOME"
```

Windows PowerShell:

```powershell
Get-Command java
Get-Command javac
java -version
javac -version
$env:JAVA_HOME
```

Các lệnh trên cho biết executable được shell tìm thấy và biến môi trường hiện tại. Chúng chưa chứng minh build tool đang dùng đúng JDK đó.

### 5.2. Kiểm tra Gradle JVM

```bash
./gradlew --version
```

Output cho biết Gradle version và JVM đang chạy Gradle. Đây là JVM của Gradle process/daemon theo môi trường hiện tại. Nếu build cấu hình Java toolchain, compiler task có thể dùng JDK khác.

Các nơi có thể ảnh hưởng JVM chạy Gradle gồm:

- `JAVA_HOME` và `PATH`.
- `org.gradle.java.home` trong `gradle.properties`.
- Gradle JVM được chọn trong IDE.
- Wrapper/Gradle version và giới hạn JVM tương thích của chính Gradle.

IDE có thể dùng Gradle JVM riêng với terminal. Vì vậy, nếu build chạy được trong terminal nhưng lỗi trong IDE (hoặc ngược lại), hãy so sánh Gradle JVM được chọn ở cả hai nơi.

### 5.3. Kiểm tra Maven JVM

```bash
./mvnw --version
```

Maven hiển thị Java version và Java home mà Maven process sử dụng. Đây là thông tin quan trọng khi compiler plugin mặc định dùng compiler từ JDK chạy Maven.

Nếu Maven được cấu hình dùng toolchain hoặc fork compiler riêng, cần kiểm tra JDK được chọn bởi cơ chế đó nữa. `mvnw --version` không tự chứng minh mọi plugin fork đều dùng cùng JDK.

### 5.4. Kiểm tra Java toolchain

Gradle có thể chọn JDK theo cấu hình toolchain. Maven có thể dùng Maven Toolchains Plugin và file `toolchains.xml`. Vì vậy, cần đọc build configuration để xác định compiler thực tế thay vì chỉ nhìn `JAVA_HOME`.

## 6. Cấu hình Java toolchain trong Gradle

### 6.1. Chọn JDK cho project

Kotlin DSL:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Toolchain yêu cầu Gradle chọn JDK có version phù hợp cho các task Java được hỗ trợ. JDK có thể được tìm thấy trên máy hoặc được provision tự động nếu build đã cấu hình resolver phù hợp và chính sách môi trường cho phép.

### 6.2. Đặt release target rõ ràng

Nếu build dùng JDK 21 để compile nhưng cần hỗ trợ runtime Java 17, có thể cấu hình toolchain và release riêng:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Ở ví dụ này, toolchain chọn compiler JDK 21, còn `options.release` yêu cầu compiler tuân thủ Java 17 cho ngôn ngữ, bytecode và API Java SE. Dependency bên ngoài vẫn cần được kiểm tra compatibility với Java 17.

Nếu mục tiêu là compile và chạy trên Java 21, có thể đặt cả toolchain và release là 21 hoặc để cấu hình tương ứng theo chính sách build. Điều quan trọng là chọn có chủ đích, tránh để source/target mặc định không rõ ràng.

### 6.3. Gradle daemon JVM không phải luôn là compiler JDK

Toolchain giúp tách JDK chạy Gradle khỏi JDK dùng cho Java compilation. Ví dụ Gradle daemon có thể chạy trên JDK 17 trong khi JavaCompile dùng JDK 21. Tuy nhiên, Gradle version vẫn có yêu cầu riêng về JVM có thể chạy chính Gradle; toolchain không làm một Gradle version cũ tự chạy được trên mọi JDK mới.

Khi gặp lỗi tương thích, hãy kiểm tra cả:

- Gradle Wrapper version và JVM chạy Gradle.
- Toolchain JDK được chọn.
- `options.release`, `sourceCompatibility` và `targetCompatibility`.
- JDK mà test worker hoặc plugin fork process sử dụng nếu được cấu hình riêng.

### 6.4. Kiểm tra toolchain được phát hiện

Gradle có thể tự tìm JDK theo các installation path và cấu hình toolchain resolver. Nếu không tìm thấy JDK phù hợp, task có thể báo không tìm thấy toolchain.

Hướng xử lý:

1. Xác định project yêu cầu Java release nào.
2. Kiểm tra JDK tương ứng đã cài chưa.
3. Kiểm tra Gradle có nhận diện installation path không.
4. Kiểm tra cấu hình auto-download/resolver nếu dự án dùng provision toolchain.
5. Xác nhận môi trường CI có quyền tải hoặc đã cài JDK cần thiết.

Không nên đổi version Java của dự án chỉ để khớp JDK ngẫu nhiên có sẵn trên máy. Hãy đối chiếu yêu cầu runtime và chính sách hỗ trợ của dự án.

## 7. Cấu hình compiler trong Maven

### 7.1. Dùng `maven.compiler.release`

Ví dụ trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>${maven.compiler.release}</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

`release` yêu cầu compiler tạo bytecode và giới hạn API Java SE theo release mục tiêu. Cần dùng JDK compiler hỗ trợ release đó. Ví dụ muốn release 17 thì Maven phải dùng compiler JDK đủ mới để hỗ trợ `--release 17`.

### 7.2. Không chỉ đặt `source` và `target`

Cấu hình cũ thường có:

```xml
<maven.compiler.source>17</maven.compiler.source>
<maven.compiler.target>17</maven.compiler.target>
```

Hai thuộc tính này điều khiển source và target, nhưng không có đầy đủ bảo đảm API như `release`. Với JDK 9 trở lên, ưu tiên cấu hình release khi mục tiêu là tương thích với một Java release cụ thể.

### 7.3. Maven Toolchains

Nếu Maven process chạy bằng một JDK nhưng project cần compiler JDK khác, Maven Toolchains Plugin có thể chọn JDK phù hợp cho các plugin hỗ trợ toolchain.

File toolchains của người dùng thường được cấu hình tại `~/.m2/toolchains.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Ví dụ cấu hình plugin trong POM:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.2.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>toolchain</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <toolchains>
                    <jdk>
                        <version>17</version>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Toolchain selection cần khớp thông tin `provides` và đường dẫn JDK thực tế. Ví dụ trên minh họa cấu trúc; tên vendor và installation path phải được điều chỉnh theo máy/CI. Không commit đường dẫn JDK riêng của một lập trình viên vào POM dùng chung.

### 7.4. Maven JVM và compiler toolchain

`./mvnw --version` hiển thị JDK chạy Maven. Toolchains có thể chọn JDK khác cho compiler plugin nếu plugin hỗ trợ và cấu hình đúng. Nếu không dùng toolchain, compiler thường lấy từ JDK Maven đang chạy (trừ khi cấu hình fork/executable riêng).

Khi Maven compile sai version, kiểm tra `JAVA_HOME`, Maven Wrapper, toolchains.xml, compiler plugin version và cấu hình release. Không chỉ nhìn `java -version` trong một terminal khác.

## 8. Đường dẫn phụ thuộc: compile classpath và runtime classpath

Một lỗi biên dịch phổ biến xảy ra khi compiler không tìm thấy class hoặc package mà source import.

### 8.1. Compile classpath

Compile classpath chứa các lớp cần thiết để compiler kiểm tra mã nguồn. Ví dụ:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
```

Để biên dịch được, `slf4j-api` phải có trên compile classpath của source set tương ứng.

### 8.2. Runtime classpath

Runtime classpath chứa lớp cần thiết khi ứng dụng hoặc test chạy. Một dependency chỉ có trên runtime classpath không nhất thiết có thể được import trong mã nguồn.

Ví dụ Gradle:

```kotlin
dependencies {
    runtimeOnly("org.postgresql:postgresql:42.7.4")
}
```

Nếu mã nguồn trực tiếp import `org.postgresql.Driver`, khai báo `runtimeOnly` có thể không đủ cho compilation. Nếu chỉ JDBC API được dùng trong source và driver được nạp ở runtime, `runtimeOnly` có thể là lựa chọn phù hợp.

### 8.3. Các configuration Gradle thường gặp

| Configuration | Mục đích khái quát |
|---|---|
| `implementation` | Dependency cần cho compile/runtime của module nhưng không công bố như API compile cho consumer của Java Library |
| `api` | Dependency được công bố trên compile API của library consumer |
| `compileOnly` | Cần để biên dịch nhưng không tự đưa vào runtime của module |
| `runtimeOnly` | Cần khi chạy, không cần để biên dịch source trực tiếp |
| `testImplementation` | Dependency dùng để biên dịch và chạy test |
| `testRuntimeOnly` | Dependency chỉ cần khi thực thi test |
| `annotationProcessor` | Processor được dùng trong quá trình biên dịch source set chính |
| `testAnnotationProcessor` | Processor được dùng khi biên dịch test source set |

Tên configuration có thể khác khi project dùng plugin hoặc source set tùy chỉnh. Hãy kiểm tra configuration thực tế thay vì giả định mọi project có cùng cấu trúc.

### 8.4. Scope Maven thường gặp

| Scope | Compile của project | Runtime của project | Test |
|---|---|---|---|
| `compile` (mặc định) | Có | Có | Có |
| `provided` | Có | Không được cung cấp bởi runtime của ứng dụng theo scope này | Có |
| `runtime` | Không dùng để biên dịch source chính | Có | Có |
| `test` | Không | Không | Có |
| `system` | Có theo đường dẫn cục bộ cấu hình | Theo semantics của scope nhưng phụ thuộc file cục bộ | Có |

`system` thường không được khuyến khích vì tạo phụ thuộc vào file cục bộ và khó tái lập. Nên dùng repository và dependency metadata thông thường.

## 9. Chẩn đoán `package ... does not exist`

Thông báo ví dụ:

```text
error: package com.fasterxml.jackson.databind does not exist
import com.fasterxml.jackson.databind.ObjectMapper;
```

Compiler không tìm thấy package chứa `ObjectMapper`. Các nguyên nhân có thể gồm:

- Chưa khai báo dependency.
- Sai `groupId`, `artifactId` hoặc version.
- Dependency được khai báo ở configuration không nằm trên compile classpath.
- Dependency chỉ được khai báo trong một module khác nhưng module hiện tại không phụ thuộc vào module đó.
- Repository không có artifact hoặc không được cấu hình.
- Dependency bị exclude hoặc resolution rule thay thế.
- Build đang chạy offline và artifact chưa có trong cache.
- Source set hoặc module path được cấu hình khác với dự kiến.

Quy trình kiểm tra:

1. Tìm tên class/package được import và xác định artifact cung cấp nó.
2. Xác nhận dependency có trong build file của đúng module.
3. Kiểm tra configuration/scope có cung cấp compile visibility.
4. Xem dependency graph hoặc compile classpath.
5. Kiểm tra repository, credentials, network và cache.
6. Kiểm tra exclusion, constraint và dependency substitution nếu artifact vẫn không xuất hiện.

Đừng vội thêm cùng dependency vào mọi module. Chỉ khai báo tại module có source trực tiếp cần API đó, hoặc công bố nó qua API khi kiểu của dependency xuất hiện trong public API.

## 10. Chẩn đoán `cannot find symbol`

Ví dụ:

```text
error: cannot find symbol
    ObjectMapper mapper = new ObjectMapper();
    ^
  symbol:   class ObjectMapper
  location: class OrderJsonReader
```

Thông báo này có thể do dependency thiếu, nhưng cũng có thể do lỗi tên hoặc phạm vi mã nguồn. Kiểm tra:

- Class/method/field có tồn tại trong version dependency đang dùng không?
- Import có đúng package và đúng chữ hoa/thường không?
- Module hiện tại có compile dependency cần thiết không?
- Có dùng nhầm API chỉ xuất hiện ở version mới hơn không?
- Generated source có được tạo trước compile không?
- Source set có chứa file khai báo class đó không?
- Nếu class thuộc module khác, package có được export và module có `requires` đúng không?

Nếu dependency đã có nhưng class không tồn tại trong version đó, compiler vẫn báo không tìm thấy symbol. Khi đó cần xác định API được thêm từ version nào và chọn version tương thích, thay vì chỉ thêm một repository khác.

## 11. Kiểm tra dependency graph với Gradle

### 11.1. Xem compile classpath

```bash
./gradlew :application:dependencies --configuration compileClasspath
```

Lệnh này hiển thị dependency graph của compile classpath trong project `application`. Kiểm tra artifact có xuất hiện hay không và version nào được chọn.

Đối với test:

```bash
./gradlew :application:dependencies --configuration testCompileClasspath
```

Nếu lỗi chỉ xảy ra khi biên dịch test, hãy xem configuration test thay vì chỉ kiểm tra compile classpath của source chính.

### 11.2. Truy tìm một dependency cụ thể

```bash
./gradlew :application:dependencyInsight \
    --dependency jackson-databind \
    --configuration compileClasspath
```

`dependencyInsight` cho biết dependency được yêu cầu từ đâu, constraint nào tác động và vì sao Gradle chọn version đó. Đây là công cụ hữu ích khi dependency có mặt nhưng version được chọn không chứa API mà source cần.

### 11.3. Kiểm tra repository và offline mode

Nếu artifact không tải được, xem repository được cấu hình trong Settings/project, thông báo resolution và network. Build chạy với `--offline` chỉ sử dụng artifact/metadata đã có trong cache phù hợp. Nếu dependency chưa từng được tải, offline mode có thể làm resolution thất bại.

Không nên khắc phục lỗi resolution bằng cách xóa cache ngay lập tức. Trước tiên hãy đọc thông báo, xác nhận tọa độ, repository và trạng thái mạng. Xóa cache có thể làm mất bằng chứng và buộc tải lại toàn bộ dependency.

## 12. Kiểm tra dependency với Maven

### 12.1. Xem dependency tree

```bash
./mvnw -pl application dependency:tree
```

Dependency tree cho biết dependency trực tiếp và bắc cầu, version, scope và các nhánh bị loại do mediation/exclusion. Nếu lỗi compile, chú ý các dependency có scope `compile` và dependency được quản lý từ parent/BOM.

Có thể lọc theo artifact:

```bash
./mvnw -pl application dependency:tree \
    -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Nếu artifact không xuất hiện, kiểm tra POM của đúng module, parent, profile và dependency management.

### 12.2. Xem effective POM

```bash
./mvnw -pl application help:effective-pom
```

Effective POM giúp xem cấu hình sau khi Maven áp dụng parent, properties, profiles và plugin management. Điều này hữu ích khi source POM không khai báo trực tiếp compiler release hoặc dependency version mà build vẫn nhận một giá trị khác.

### 12.3. Phân biệt `dependencyManagement` và `dependencies`

`dependencyManagement` quản lý version/scope mặc định khi dependency được khai báo. Nó không tự đưa dependency vào compile classpath chỉ vì artifact được liệt kê trong phần quản lý.

Ví dụ parent quản lý Jackson:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Module muốn sử dụng vẫn phải khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Nếu chỉ có block `dependencyManagement`, compiler không tự nhìn thấy `ObjectMapper`.

## 13. Lỗi version dependency và xung đột API

### 13.1. Version được chọn không có API mà source sử dụng

Source có thể được viết dựa trên API của Jackson 2.17 nhưng dependency graph lại chọn version cũ hơn. Khi đó, compiler báo `cannot find symbol` cho method/class mới.

Kiểm tra version thực tế được chọn thay vì chỉ nhìn version khai báo ở một file. Gradle có thể chọn version khác do conflict resolution, constraint hoặc platform. Maven có thể chọn version theo dependency mediation và dependency management.

### 13.2. Dependency conflict không phải lúc nào cũng gây lỗi compile

Hai thư viện có thể yêu cầu các version khác nhau của cùng một module. Build tool chọn một version theo quy tắc resolution. Nếu API compile tương thích, build vẫn có thể biên dịch; nhưng runtime có thể gặp:

- `NoSuchMethodError`.
- `NoSuchFieldError`.
- `AbstractMethodError`.
- Hành vi sai do thay đổi semantics.

Đây là lý do cần kiểm tra cả compile classpath và runtime classpath. Một lỗi xuất hiện sau khi ứng dụng khởi chạy không nhất thiết là lỗi biên dịch, dù nguyên nhân gốc vẫn có thể là version dependency.

### 13.3. BOM và dependency constraints

Nếu nhiều module thuộc cùng một release train, dùng BOM/platform hoặc dependency constraints để căn chỉnh version. Tuy nhiên, phải kiểm tra BOM thực sự quản lý artifact cần thiết và project đã import/apply BOM trong configuration phù hợp.

Không nên tự ép version bằng cách ghi version lặp lại trong nhiều module. Cấu hình tập trung giúp giảm lệch version và làm nguyên nhân resolution dễ theo dõi hơn.

## 14. Lỗi classpath và module path trong JPMS

Java có hai cách tổ chức việc tìm lớp phổ biến:

- **Classpath:** các lớp được tìm theo thứ tự classpath; mô hình truyền thống không áp dụng đầy đủ ranh giới module của JPMS.
- **Module path:** các module được xác định theo tên, khai báo `requires`, `exports` và các quy tắc encapsulation.

Nếu dự án có `module-info.java`, lỗi có thể liên quan đến module path thay vì chỉ thiếu JAR trên classpath.

### 14.1. `module not found`

Ví dụ:

```text
error: module not found: com.fasterxml.jackson.databind
    requires com.fasterxml.jackson.databind;
```

Compiler không tìm thấy module có tên được yêu cầu trên module path. Kiểm tra:

- Dependency JAR có nằm trên module path không?
- Module name thực tế có đúng không?
- JAR có `module-info.class` hay được coi là automatic module?
- `requires` có dùng đúng module name không?
- Build tool có cấu hình module path thay vì classpath theo ý định không?

Tên artifact Maven/Gradle không nhất thiết giống tên module JPMS. Dùng `jar --describe-module --file path/to/library.jar` để xem module name mà JAR công bố hoặc tên automatic module được suy ra.

### 14.2. Package không được export

Một module có thể được tìm thấy nhưng package cần dùng không được export. Compiler có thể báo package không được nhìn thấy hoặc package không được export.

Ví dụ:

```java
module com.example.consumer {
    requires com.example.library;
}
```

Nếu `com.example.library` không export package `com.example.library.internal`, consumer không thể truy cập package đó như một API module thông thường. Cần dùng public API được export hoặc thay đổi thiết kế module nếu có lý do chính đáng.

### 14.3. Classpath và module path không thể thay thế tùy tiện

Một JAR chạy được trên classpath có thể cần điều chỉnh khi đưa lên module path do split package, module name, `requires` hoặc encapsulation. Nếu build báo lỗi liên quan đến module, đừng chỉ thêm JAR vào một danh sách classpath khác mà không xác định dự án đang chạy theo mô hình nào.

## 15. Annotation processor và generated source

Một số thư viện không chỉ cung cấp API mà còn sinh mã trong quá trình compile. Ví dụ Lombok, MapStruct hoặc processor tạo metamodel.

### 15.1. Dấu hiệu lỗi

Ví dụ:

```text
error: cannot find symbol
    return order.getCustomerName();
```

Nếu method được kỳ vọng sinh bởi annotation processor nhưng không xuất hiện, nguyên nhân có thể là processor chưa được cấu hình, không tương thích JDK hoặc không chạy ở source set hiện tại.

### 15.2. Gradle annotation processor configuration

Ví dụ:

```kotlin
dependencies {
    compileOnly("org.projectlombok:lombok:1.18.34")
    annotationProcessor("org.projectlombok:lombok:1.18.34")

    testCompileOnly("org.projectlombok:lombok:1.18.34")
    testAnnotationProcessor("org.projectlombok:lombok:1.18.34")
}
```

Dependency API và processor có vai trò khác nhau. Chỉ khai báo processor như `implementation` không nhất thiết đặt nó đúng annotation processor path mà compiler sử dụng.

### 15.3. Maven annotation processor

Maven Compiler Plugin hỗ trợ cấu hình annotation processor và processor path. Cấu hình cụ thể phụ thuộc plugin version và cách project quản lý processor. Nếu dùng `annotationProcessorPaths`, cần bảo đảm processor artifact và version có thể được phân giải.

### 15.4. Kiểm tra output sinh mã

Gradle và Maven có thư mục generated source riêng. Kiểm tra task/goal xử lý annotation, processor version và log compiler. Nếu mã sinh ra được commit vào repository, cần xác định quy ước rõ ràng để tránh vừa dùng generated source cũ vừa sinh source mới.

## 16. Lỗi encoding, tên file và package

Không phải mọi lỗi compiler đều do JDK hoặc dependency, nhưng chúng có thể bị nhầm với lỗi đường dẫn.

### 16.1. Encoding không thống nhất

Nếu file được lưu UTF-8 nhưng compiler dùng encoding khác, ký tự ngoài ASCII có thể bị đọc sai hoặc phát sinh lỗi. Nên chỉ định encoding rõ ràng.

Gradle:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

Maven:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

### 16.2. Tên file và public class

Một public top-level class thường phải nằm trong file có tên tương ứng. Ví dụ `public class OrderService` phải nằm trong `OrderService.java`. Nếu tên file, package hoặc cấu trúc source directory không đúng, compiler có thể báo lỗi dù dependency đầy đủ.

### 16.3. Package và source root

Build tool cần biết thư mục nào là source root. Nếu file `Order.java` khai báo `package com.example.order` nhưng đặt ngoài source directory hoặc sai cấu trúc package, compile task có thể không tìm thấy nó như mong muốn.

Kiểm tra source set/source directory trước khi thêm dependency hoặc sửa version Java.

## 17. Bảng tra cứu lỗi và hướng xử lý

| Thông báo | Nguyên nhân thường gặp | Nơi cần kiểm tra đầu tiên |
|---|---|---|
| `invalid source release: 17` | Compiler JDK quá cũ so với source level | JDK của compiler, toolchain, source/release |
| `release version 17 not supported` | JDK compiler không hỗ trợ `--release 17` | Maven/Gradle compiler JDK và plugin config |
| `Source option 5 is no longer supported` | Compiler plugin/config cũ hoặc source mặc định quá thấp | Maven Compiler Plugin và release property |
| `class file has wrong version` | Dependency/class được biên dịch bằng Java mới hơn compiler có thể đọc | Class file version, JDK compiler, dependency version |
| `UnsupportedClassVersionError` | Runtime JVM quá cũ so với bytecode | Java runtime trên môi trường chạy |
| `package ... does not exist` | Dependency không có trên compile path hoặc sai package | Dependency declaration, compileClasspath/scope, repository |
| `cannot find symbol` | Sai tên/API, dependency/version thiếu hoặc generated source chưa có | Source, dependency graph, annotation processor |
| `module not found` | Module không có trên module path hoặc sai module name | Module path, `requires`, `jar --describe-module` |
| `package ... is not visible` | Package không được export hoặc module encapsulation | `module-info.java`, `exports` |
| `NoSuchMethodError` | Runtime dùng version API không tương thích | Runtime dependency graph và version mediation |
| `Could not resolve ...` | Repository, tọa độ, credentials, network hoặc variant | Resolution log, repository, dependency metadata |
| Generated method/class không tồn tại | Annotation processor không chạy hoặc không tương thích | Processor path, plugin, generated source output |

Thông báo đầu tiên trong log thường có giá trị chẩn đoán cao hơn các lỗi kéo theo. Khi một dependency không được resolve, compiler có thể báo hàng chục symbol không tìm thấy. Hãy xử lý lỗi gốc trước rồi mới đọc các lỗi còn lại.

## 18. Quy trình chẩn đoán lỗi biên dịch theo thứ tự

Khi build báo lỗi, có thể làm theo các bước sau:

1. **Xác định task/phase thất bại.** `compileJava`, `compileTestJava`, Maven `compile`, `testCompile` hay một plugin goal khác?
2. **Đọc thông báo đầu tiên.** Xác định lỗi nói về source level, class file version, package, symbol, module hay processor.
3. **Ghi nhận JDK của build tool.** Chạy `./gradlew --version` hoặc `./mvnw --version`.
4. **Xác định compiler/toolchain thực tế.** Kiểm tra Gradle toolchain, Maven Toolchains, fork compiler và IDE settings.
5. **So sánh release mục tiêu.** Kiểm tra `options.release`, `sourceCompatibility`, `targetCompatibility` hoặc `maven.compiler.release`.
6. **Xác định artifact cung cấp class bị thiếu.** Tìm dependency và version đúng.
7. **Kiểm tra compile classpath/module path.** Xem configuration, scope, dependency graph, module name và export.
8. **Kiểm tra generated source/annotation processor.** Xác nhận processor có mặt, tương thích và được gọi.
9. **Kiểm tra repository và môi trường.** Xem network, offline mode, credentials, profile và cache.
10. **Sửa một nguyên nhân rồi build lại.** Tránh đổi JDK, dependency và plugin đồng thời vì sẽ khó biết yếu tố nào giải quyết lỗi.

Nếu lỗi chỉ xuất hiện trong IDE, so sánh IDE Project SDK, Gradle JVM/Maven importer JVM và terminal. Nếu chỉ xuất hiện trong CI, so sánh JDK/toolchain, Wrapper, profiles, biến môi trường và dependency cache của CI với local.

## 19. Ví dụ: Gradle dùng sai JDK compiler

Giả sử dự án cần Java 17, nhưng máy phát triển có JDK 11 trong `JAVA_HOME`. Build file cấu hình release 17:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Nếu Gradle không được cấu hình toolchain và đang dùng compiler JDK 11, task compile có thể báo release 17 không được hỗ trợ.

Các bước xử lý:

1. Chạy `./gradlew --version` để xác định JVM chạy Gradle.
2. Kiểm tra `JAVA_HOME` và `javac -version`.
3. Xác nhận dự án thực sự yêu cầu Java 17, không phải Java 11.
4. Cài JDK 17 hoặc cấu hình toolchain để Gradle tìm được JDK 17.
5. Giữ `options.release = 17` nếu artifact cần tương thích Java 17.
6. Chạy lại compile trong môi trường đúng và kiểm tra runtime target.

Nếu tổ chức muốn dùng JDK 21 để build nhưng hỗ trợ runtime Java 17, có thể đặt toolchain 21 và release 17. Cần xác nhận dependency và plugin cũng hỗ trợ target đó.

## 20. Ví dụ: dependency có trong runtime nhưng thiếu ở compile

Một module Gradle khai báo:

```kotlin
dependencies {
    runtimeOnly("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}
```

Nhưng source lại import:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
```

Compiler không nhìn thấy `ObjectMapper` trên compile classpath. Nếu mã nguồn trực tiếp sử dụng Jackson, dependency cần được khai báo bằng configuration có compile visibility, chẳng hạn:

```kotlin
dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}
```

Nếu chỉ cần một driver JDBC được nạp ở runtime và source chỉ sử dụng API `java.sql`, `runtimeOnly` cho driver có thể phù hợp. Hãy quyết định theo việc source có trực tiếp tham chiếu kiểu của dependency hay không.

Trong Maven, một tình huống tương tự là dependency được khai báo scope `runtime` nhưng source chính import class từ dependency đó. Đổi scope sang `compile` nếu source thực sự cần compile visibility và chính sách dependency cho phép.

## 21. Ví dụ: dependency version không chứa method được sử dụng

Giả sử mã nguồn gọi method mới được thêm trong Jackson version mới, nhưng Gradle resolve một version cũ hơn do constraint hoặc dependency bắc cầu.

```java
mapper.someNewMethod();
```

Compiler báo không tìm thấy method. Cần kiểm tra:

```bash
./gradlew :application:dependencyInsight \
    --dependency jackson-databind \
    --configuration compileClasspath
```

Hoặc Maven:

```bash
./mvnw -pl application dependency:tree \
    -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Nếu version được chọn thấp hơn version có API cần dùng, hãy cập nhật catalog/platform/parent dependency management theo chính sách tương thích. Nếu version đã đúng, kiểm tra import, tên method, artifact thực tế và source set.

Không nên chỉ thêm một bản JAR khác vào classpath bằng tay. Hai version cùng tồn tại có thể khiến compiler/runtime chọn khác nhau và tạo lỗi khó dự đoán.

## 22. IDE và terminal dùng cấu hình khác nhau

Một dự án có thể build thành công trong terminal nhưng IDE gạch đỏ, hoặc IDE biên dịch được nhưng command line thất bại. Nguyên nhân thường là hai môi trường đang dùng cấu hình khác nhau.

Kiểm tra trong IDE:

- Project SDK/Project JDK.
- Module SDK hoặc language level.
- Gradle JVM nếu project import bằng Gradle.
- Maven importer/runner JDK nếu project dùng Maven.
- Build và run configuration.
- Annotation processing setting nếu IDE thực hiện compile riêng.
- Module dependencies và source roots được IDE nhận diện.

Nếu build được ủy quyền cho Gradle/Maven, build tool configuration thường là nguồn quyết định compiler và dependency. Nếu IDE dùng compiler riêng cho thao tác build, có thể tồn tại khác biệt với command line. Nên đồng bộ IDE với Wrapper và toolchain của dự án để giảm sai lệch.

## 23. Không xử lý lỗi bằng cách xóa cache một cách mù quáng

Khi dependency resolution thất bại, việc xóa `.gradle`, `.m2` hoặc cache toàn cục không phải bước đầu tiên. Cache có thể chứa artifact hợp lệ và metadata giúp tái hiện lỗi.

Hãy kiểm tra trước:

- Tọa độ dependency có chính xác không?
- Repository có chứa artifact/version đó không?
- Credentials hoặc proxy có hợp lệ không?
- Build có đang chạy offline không?
- Dependency bị exclude hoặc bị thay thế không?
- Metadata của repository có lỗi hoặc thay đổi không?

Chỉ cân nhắc làm mới cache khi có bằng chứng cache bị hỏng hoặc metadata cũ không còn hợp lệ. Nếu cần làm mới, ưu tiên phạm vi nhỏ và ghi lại command đã dùng. Việc xóa cache có thể làm lần build tiếp theo tải lại nhiều artifact, nên thời gian đo sau đó sẽ khác.

## 24. Kiểm soát Java version và dependency trong CI

Lỗi chỉ xảy ra trong CI thường đến từ khác biệt môi trường. Một pipeline có thể kiểm soát tốt hơn bằng cách:

- Dùng Gradle Wrapper hoặc Maven Wrapper đã commit.
- Chọn JDK rõ ràng trong CI image/setup step.
- Cấu hình Java toolchain hoặc Maven Toolchains khi cần.
- Đặt release target rõ ràng.
- Pin version compiler plugin và các plugin quan trọng.
- Dùng Version Catalog, BOM/platform hoặc Maven dependency management.
- Dùng dependency locking/verification nếu dự án yêu cầu.
- In thông tin JDK và build tool version vào log.
- Giữ repository và credentials nhất quán giữa các runner.

Ví dụ, bước chẩn đoán có thể in:

```bash
java -version
javac -version
./gradlew --version
```

Hoặc với Maven:

```bash
java -version
javac -version
./mvnw --version
```

Đây là dữ liệu quan sát ban đầu. Nếu build dùng toolchain khác, cần kiểm tra toolchain configuration và log compiler tương ứng.

## 25. Bài tập vận dụng

Một module Gradle khai báo Java release 17. Trên máy A, `./gradlew compileJava` thành công; trên máy B, build báo `invalid source release: 17`. Cùng lúc, một module khác báo `package com.fasterxml.jackson.databind does not exist`.

Hãy xác định:

1. Vì sao `java -version` trên hai máy chưa đủ để kết luận compiler JDK giống nhau?
2. Cần chạy lệnh nào để xem JVM đang chạy Gradle?
3. Java toolchain giải quyết khác biệt giữa Gradle daemon JVM và compiler JDK như thế nào?
4. `source`, `target` và `--release` khác nhau ở điểm nào?
5. Nếu compiler JDK 11 nhận yêu cầu release 17, cần thay đổi điều gì?
6. Dependency Jackson phải nằm trên configuration nào nếu source chính import `ObjectMapper`?
7. Dùng Gradle command nào để xem `compileClasspath` và lý do version Jackson được chọn?
8. Nếu dùng Maven, scope `runtime` có đủ cho source chính import class đó không?
9. Nếu source import một module JPMS nhưng báo `module not found`, cần kiểm tra gì ngoài tọa độ artifact?
10. Nếu lỗi chỉ xảy ra trong CI, những thông tin môi trường nào cần được ghi lại?

Có thể tạo một project nhỏ với Java toolchain và một dependency. Thử đổi release target cao hơn compiler JDK để quan sát lỗi, sau đó chọn toolchain tương thích. Tiếp theo, chuyển dependency từ `implementation` sang `runtimeOnly` rồi chạy compile để thấy khác biệt giữa compile classpath và runtime classpath. Thực hành tương tự trong Maven bằng cách thay compiler release và dependency scope.

## 26. Nguyên tắc xử lý lỗi biên dịch

- Xác định task hoặc phase thất bại trước khi sửa cấu hình.
- Phân biệt JDK chạy build, JDK compiler/toolchain và Java runtime mục tiêu.
- Dùng `--release` hoặc cấu hình release tương ứng khi cần tương thích với một Java version cụ thể.
- Pin Wrapper và compiler plugin để build nhất quán.
- Kiểm tra compile classpath, runtime classpath và module path theo đúng lỗi.
- Khai báo dependency ở module thực sự sử dụng API; chọn scope/configuration phù hợp.
- Dùng dependency insight/tree để xác nhận version được chọn, không chỉ đọc version khai báo.
- Kiểm tra annotation processor và generated source khi symbol được kỳ vọng sinh ra.
- Xác định IDE và CI có đang dùng JDK/toolchain khác terminal hay không.
- Chỉ làm mới cache khi có bằng chứng cache là nguyên nhân.
- Thay đổi từng yếu tố và build lại để xác nhận nguyên nhân đã được giải quyết.

Lỗi biên dịch do Java version thường bắt nguồn từ compiler không hỗ trợ release mà dự án yêu cầu hoặc dependency được biên dịch bằng Java mới hơn. Lỗi do đường dẫn phụ thuộc thường bắt nguồn từ artifact thiếu, version không phù hợp hoặc dependency nằm sai classpath/module path. Đọc đúng thông báo, xác định công cụ thực tế và kiểm tra graph của đúng source set sẽ giúp xử lý nguyên nhân gốc thay vì thay đổi JDK hay dependency một cách phỏng đoán.
