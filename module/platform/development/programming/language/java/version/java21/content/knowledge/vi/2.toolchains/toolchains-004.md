# Cấu hình Java toolchain cho Maven và Gradle

Trong dự án Java 21, cấu hình toolchain giúp mọi máy phát triển và môi trường CI chọn đúng JDK cho các tác vụ biên dịch, kiểm thử và tạo tài liệu. Nhờ đó, kết quả build không phụ thuộc hoàn toàn vào JDK đang được đặt trong `JAVA_HOME` hoặc JDK mà IDE dùng để khởi chạy build tool.

Maven và Gradle đều hỗ trợ toolchain, nhưng cách khai báo khác nhau. Trước khi cấu hình, cần phân biệt ba phiên bản Java có thể xuất hiện trong cùng một lần build:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| JVM chạy build tool | JDK/JVM dùng để khởi chạy Maven hoặc Gradle daemon | Maven chạy trên JDK 17 |
| JDK toolchain | JDK cung cấp `javac`, `java` hoặc `javadoc` cho các tác vụ của dự án | Biên dịch và chạy test bằng JDK 21 |
| Java release mục tiêu | Phiên bản ngôn ngữ, API Java và định dạng bytecode mà mã nguồn được phép sử dụng | `--release 21` |

Ba giá trị này có liên quan nhưng không đồng nghĩa. Chẳng hạn, Maven có thể chạy trên JDK 17, dùng JDK 21 làm toolchain và biên dịch mã nguồn theo Java 21. Nếu cần tạo thư viện chạy được trên Java 17, vẫn có thể dùng JDK 21 làm compiler toolchain nhưng đặt release mục tiêu là 17.

## Vì sao cần toolchain?

Nếu không khai báo toolchain, compiler thường dùng JDK chạy build tool. Hai lập trình viên có `JAVA_HOME` khác nhau có thể vô tình biên dịch bằng các JDK khác nhau. Build trên máy cá nhân có thể thành công nhưng thất bại trên CI, hoặc sinh bytecode và sử dụng API không đúng với môi trường triển khai.

Toolchain giải quyết việc chọn JDK ở cấp dự án. Với Gradle, cấu hình Java toolchain được áp dụng cho các tác vụ biên dịch, kiểm thử và Javadoc có hỗ trợ toolchain. Với Maven, `maven-toolchains-plugin` đưa JDK đã chọn vào phiên build để các plugin có hỗ trợ toolchain sử dụng; vì vậy cần kiểm tra plugin nào thực sự hỗ trợ cơ chế này.

Toolchain không tự thay thế cấu hình release mục tiêu. Hãy dùng toolchain để chọn bộ công cụ và dùng `--release` để giới hạn ngôn ngữ, API Java cùng bytecode đầu ra. Với dự án Java 21, cấu hình thông thường là JDK toolchain 21 kết hợp `release` 21.

## Cấu hình Maven

### Chọn JDK 21 bằng cơ chế tự phát hiện

`maven-toolchains-plugin` từ phiên bản 3.2.0 có thể phát hiện các JDK đã cài ở những vị trí quen thuộc hoặc được khai báo qua biến môi trường. Phiên bản 3.3.0 cung cấp goal `select-jdk-toolchain` để chọn một JDK phù hợp mà không bắt buộc phải tự viết `toolchains.xml`.

Ví dụ sau yêu cầu một JDK thuộc nhánh Java 21 và đặt release biên dịch là 21. Các phiên bản plugin được ghim rõ ràng để hành vi build không thay đổi ngầm khi môi trường Maven thay đổi.

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <toolchain.jdk.version>[21,22)</toolchain.jdk.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.3.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>select-jdk-toolchain</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
        </plugin>
    </plugins>
</build>
```

Thuộc tính `[21,22)` là khoảng phiên bản Maven dùng để tìm JDK 21, bao gồm các bản cập nhật như 21.0.x và không bao gồm Java 22. Có thể bổ sung `toolchain.jdk.vendor` nếu tổ chức cần thống nhất nhà cung cấp JDK; giá trị phải khớp với thông tin plugin phát hiện được.

Trước khi build, kiểm tra các JDK mà plugin nhìn thấy:

```bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
```

Nếu không có JDK phù hợp trong kết quả, hãy cài JDK 21 hoặc cấu hình đường dẫn JDK qua biến môi trường mà plugin có thể phát hiện. Goal `select-jdk-toolchain` chỉ chọn trong số các JDK được phát hiện hoặc các toolchain đã khai báo; nó không bảo đảm tự tải JDK về máy.

### Khai báo đường dẫn JDK bằng `toolchains.xml`

Trong môi trường mà cơ chế tự phát hiện không tìm thấy JDK, hoặc khi muốn khai báo đường dẫn cài đặt một cách tường minh, có thể tạo file `toolchains.xml` tại `${user.home}/.m2/toolchains.xml` trên từng máy.

Ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/absolute/path/to/jdk-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Thay `/absolute/path/to/jdk-21` bằng thư mục JDK 21 thực tế trên máy. Đường dẫn này là cấu hình cục bộ, không nên commit vào `pom.xml` hoặc dùng chung nguyên trạng giữa Windows, Linux và macOS.

Khi dùng file này, cấu hình plugin trong `pom.xml` bằng goal `toolchain` và cùng tiêu chí version/vendor:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
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
                <version>[21,22)</version>
                <vendor>temurin</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

Maven đối chiếu các giá trị `version` và `vendor` trong POM với phần `provides` của `toolchains.xml`. Khoảng `[21,22)` hữu ích khi file cục bộ ghi phiên bản đầy đủ như `21.0.2`, thay vì chỉ ghi `21`. Nếu tiêu chí không khớp, Maven báo không tìm thấy toolchain phù hợp.

### Phạm vi tác dụng và kiểm tra Maven

Toolchain được chọn có thể được các plugin Maven có hỗ trợ sử dụng, ví dụ `maven-compiler-plugin`, Surefire, Failsafe và Javadoc ở các phiên bản có hỗ trợ tương ứng. Một plugin không hỗ trợ toolchain vẫn có thể tiếp tục dùng JVM hoặc công cụ mặc định của nó. Ngoài ra, tham số `jdkToolchain` cấu hình trực tiếp trong một plugin như Maven Compiler Plugin có thể ghi đè toolchain chung cho riêng plugin đó.

Các lệnh sau giúp phân biệt JDK chạy Maven với JDK được chọn cho dự án:

```bash
# Hiển thị Maven và JVM đang chạy Maven
mvn -v

# Liệt kê các JDK mà Maven Toolchains Plugin phát hiện
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains

# Chạy build và quan sát thông tin chọn toolchain trong log
mvn -X clean verify
```

`mvn -v` chỉ cho biết JVM chạy Maven. Muốn xác nhận JDK compiler sử dụng, hãy kiểm tra log của bước chọn toolchain và log của plugin biên dịch.

## Cấu hình Gradle

Gradle khai báo Java toolchain trực tiếp trong khối `java`. Cấu hình ở cấp dự án giúp các tác vụ Java như compile, test và Javadoc sử dụng cùng phiên bản toolchain.

### Groovy DSL — `build.gradle`

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

### Kotlin DSL — `build.gradle.kts`

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 21
}
```

`languageVersion = JavaLanguageVersion.of(21)` yêu cầu Gradle chọn JDK 21 làm toolchain. `options.release = 21` yêu cầu compiler tuân theo đặc tả Java 21, dùng API của Java 21 và tạo bytecode tương thích với Java 21.

Gradle tự phát hiện JDK đã cài. Nếu không tìm thấy JDK phù hợp, Gradle chỉ tự tải JDK khi build đã cấu hình một toolchain download repository thông qua resolver plugin; nếu chưa cấu hình cơ chế đó, cần cài JDK 21 trên máy hoặc CI. Không nên giả định chỉ khai báo `languageVersion` là Gradle sẽ luôn tải JDK về.

### Phân biệt JDK chạy Gradle và JDK toolchain

`java.toolchain` chọn JDK cho tác vụ của dự án. JVM chạy Gradle daemon được chọn riêng, thường chịu ảnh hưởng từ môi trường khởi chạy, IDE hoặc cấu hình daemon JVM. Hai JVM này có thể khác nhau.

Với Java 21, cần chú ý phiên bản Gradle Wrapper:

- Gradle 8.4 hỗ trợ dùng Java 21 qua toolchain để biên dịch, kiểm thử và chạy chương trình Java.
- Gradle 8.5 trở lên mới hỗ trợ chạy chính Gradle trên JVM Java 21.

Do đó, nếu CI hoặc IDE chạy Gradle bằng JDK 21, Wrapper phải từ 8.5 trở lên. Hãy kiểm tra phiên bản Gradle và JVM chạy Gradle bằng:

```bash
./gradlew --version
```

Trên Windows có thể dùng `gradlew.bat --version`. Lệnh này hiển thị JVM của Gradle; để xác nhận toolchain dự án, xem thông tin toolchain trong log build hoặc chạy tác vụ `javaToolchains` khi Java plugin được áp dụng:

```bash
./gradlew javaToolchains
```

## Chọn `--release` phù hợp với phiên bản triển khai

Toolchain và release có thể dùng hai phiên bản khác nhau. Ví dụ, một thư viện cần biên dịch bằng compiler JDK 21 nhưng phải chạy được trên Java 17:

**Maven:**

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <toolchain.jdk.version>[21,22)</toolchain.jdk.version>
</properties>
```

**Gradle Kotlin DSL:**

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
```

Compiler JDK 21 cung cấp compiler và công cụ của JDK 21; release 17 giới hạn cú pháp, API Java và định dạng class file theo Java 17. Máy chạy ứng dụng vẫn cần một JVM tương thích với bytecode đầu ra, trong ví dụ này là Java 17 trở lên.

## Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Đã đặt `maven.compiler.release=21` nhưng Maven vẫn báo compiler không hỗ trợ Java 21 | JDK thực tế mà compiler sử dụng thấp hơn 21 hoặc Maven chưa chọn toolchain | Kiểm tra `mvn -v`, danh sách JDK được phát hiện và log chọn toolchain |
| Maven báo không tìm thấy toolchain | JDK chưa được cài/phát hiện hoặc `version`/`vendor` không khớp | Kiểm tra output discovery; dùng khoảng `[21,22)`; xác minh `jdkHome` và metadata `provides` nếu dùng `toolchains.xml` |
| Gradle báo không tìm thấy Java 21 toolchain | Máy chưa có JDK 21 và chưa cấu hình resolver để tải JDK | Cài JDK 21 hoặc cấu hình toolchain download repository phù hợp |
| Gradle không khởi chạy khi `JAVA_HOME` trỏ tới JDK 21 | Gradle Wrapper quá cũ để chạy trên Java 21 | Dùng Wrapper 8.5 trở lên nếu chính Gradle chạy trên JDK 21 |
| Build chạy được trên máy cá nhân nhưng không chạy trên CI | JDK, vendor hoặc cấu hình toolchain giữa các môi trường khác nhau | Khai báo rõ phiên bản, thống nhất vendor khi cần, cài đặt JDK trên CI và commit Maven/Gradle Wrapper |

Không nên dùng `sourceCompatibility` và `targetCompatibility` làm cách chính để chọn JDK. Hai thuộc tính này chỉ đặt mức ngôn ngữ và bytecode, không buộc build dùng một JDK cụ thể và không bảo đảm API được giới hạn như `--release`. Với các dự án Java hiện đại, ưu tiên toolchain kết hợp `--release` khi cần xác định rõ cả JDK sử dụng lẫn nền tảng Java đích.

## Quy trình áp dụng cho dự án Java 21

1. Cài JDK 21 trên máy phát triển và môi trường CI, hoặc cấu hình resolver để build tool có thể cung cấp JDK phù hợp.
2. Chọn phiên bản Maven/Gradle Wrapper được hỗ trợ và commit các file Wrapper vào repository.
3. Khai báo JDK toolchain 21 trong POM hoặc Gradle build script.
4. Đặt release mục tiêu là 21 nếu sản phẩm yêu cầu chạy trên Java 21; chọn release thấp hơn nếu cần tương thích ngược.
5. Chạy build và kiểm tra log để xác nhận JDK được chọn. Kiểm tra thêm tác vụ test và Javadoc nếu dự án sử dụng chúng.
6. Đồng bộ cấu hình CI và IDE với yêu cầu của dự án, đồng thời giữ các đường dẫn cài JDK mang tính cá nhân trong cấu hình cục bộ.

## Tài liệu tham khảo chính thức

- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven — JDK Toolchain Discovery Mechanism](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html)
- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html)
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Oracle — The `javac` Command for JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
