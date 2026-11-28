# Tách cấu hình preview và incubator khỏi cấu hình phát hành mặc định

Một dự án Java 25 có thể dùng đồng thời API ổn định, preview feature và incubator module. Ba nhóm này có vòng đời và cách bật khác nhau. Nếu đưa mọi cờ vào cấu hình build mặc định, artifact phát hành có thể vô tình phụ thuộc vào API chưa ổn định hoặc module thử nghiệm; nếu chỉ bật cờ lúc compile mà quên runtime, ứng dụng hoặc test sẽ không khởi chạy.

Bài này thuộc chương **Build và triển khai** của module **JAVA_VERSION_JAVA25**. Mục tiêu là tạo cấu hình phát hành mặc định chỉ dùng Java SE API ổn định, đồng thời cung cấp các cấu hình opt-in riêng cho preview và incubator khi nhóm phát triển chủ động thử nghiệm. Cấu hình compile, test, đóng gói và runtime phải nhất quán; artifact thử nghiệm phải được nhận diện rõ trước khi triển khai.

> **Phạm vi:** các ví dụ sử dụng JDK 25. Preview feature phải được biên dịch và chạy bằng JDK 25. Incubator module được bật riêng bằng module system. Khi chuyển sang JDK khác, hãy kiểm tra JEP và API của release đích, rồi biên dịch lại source bằng toolchain đích.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt API ổn định, preview feature, incubator module và experimental feature.
2. Nhận diện các preview feature và incubator module có trong JDK 25.
3. Giữ cấu hình phát hành mặc định không bật preview và không thêm incubator module.
4. Bật preview đúng ở cả compiler và runtime.
5. Bật incubator module đúng ở compile time và runtime.
6. Kết hợp preview và incubator mà không trộn lẫn ý nghĩa của hai loại cờ.
7. Tổ chức profile Maven và property Gradle cho cấu hình opt-in.
8. Tách source set, output directory, artifact và container image theo mục đích.
9. Đóng gói custom runtime bằng jlink/jpackage khi cần.
10. Thiết kế CI kiểm tra cấu hình mặc định và cấu hình thử nghiệm riêng.
11. Phát hiện class file preview bị đưa nhầm vào artifact phát hành.
12. Lập kế hoạch chuyển khỏi preview/incubator khi API thay đổi hoặc trở thành stable.

## 2. Bốn loại tính năng cần phân biệt

Không phải tính năng mới nào trong JDK cũng cần bật cùng một cờ.

| Loại | Ý nghĩa | Cách dùng | Mức ổn định |
|---|---|---|---|
| **Stable API/feature** | Đã được chuẩn hóa và đưa vào nền tảng Java SE | Dùng theo API bình thường; không cần preview flag | Permanent trong release |
| **Preview feature** | Đã có thiết kế và implementation nhưng còn có thể thay đổi hoặc bị loại bỏ | **--enable-preview** lúc compile và runtime | Gắn với một JDK release |
| **Incubator module** | API/module được đưa vào để thử nghiệm, thu thập phản hồi và có thể thay đổi hoặc bị loại bỏ | Chủ động thêm module, ví dụ **--add-modules** | Không phải API ổn định |
| **Experimental feature** | Tính năng thử nghiệm ở cấp triển khai/JVM, có cơ chế bật riêng theo tài liệu của tính năng | Dùng tùy chọn cụ thể được JEP/JDK mô tả | Không đồng nghĩa với preview hoặc incubator |

### 2.1. Preview không đồng nghĩa với incubator

Preview feature có thể là tính năng ngôn ngữ hoặc API preview thuộc Java SE. Trong JDK 25, ví dụ gồm Structured Concurrency và PEM Encodings of Cryptographic Objects.

Incubator module là một module riêng trong module graph. JDK 25 có **jdk.incubator.vector**. Việc thêm module này vào module graph không biến nó thành preview API, và **--enable-preview** không tự thêm module này vào ứng dụng.

### 2.2. Experimental là nhóm riêng

JDK 25 còn có JEP 509 — JFR CPU-Time Profiling (Experimental). Không phân loại JEP này thành preview feature hay incubator module. Nếu ứng dụng cần tính năng experimental, hãy đọc tùy chọn bật riêng của JEP và ghi nó trong inventory runtime; không tự suy ra rằng cần **--enable-preview** hoặc **--add-modules**.

## 3. Danh sách preview feature trong JDK 25

JDK 25 có bốn preview feature chính:

| JEP | Tên | Loại preview | Lưu ý khi build |
|---|---|---|---|
| **JEP 470** | PEM Encodings of Cryptographic Objects | Preview API | Các API **PEMEncoder**, **PEMDecoder**, **PEMRecord**, **DEREncodable** và một số method mã hóa khóa cần preview |
| **JEP 502** | Stable Values | Preview API | API **StableValue** của JDK 25 là preview; khi nhắm tới JDK mới hơn phải kiểm tra API thay thế |
| **JEP 505** | Structured Concurrency (Fifth Preview) | Preview API | **StructuredTaskScope** và các kiểu liên quan cần preview |
| **JEP 507** | Primitive Types in Patterns, instanceof, and switch (Third Preview) | Preview ngôn ngữ | Cú pháp pattern matching cho primitive cần preview |

Các tính năng trên là snapshot của JDK 25. Một preview feature có thể được preview lại với thay đổi, trở thành permanent hoặc bị loại bỏ ở release sau. Không mang class file preview của JDK 25 sang JDK khác và kỳ vọng nó vẫn chạy.

### 3.1. Kiểm tra preview API từ JDK

JDK 25 cung cấp Preview API List trong tài liệu Java SE API. Trang này liệt kê các kiểu và method được đánh dấu preview, ví dụ:

- **java.lang.StableValue**.
- **java.security.DEREncodable**, **PEMEncoder**, **PEMDecoder**, **PEMRecord**.
- **java.util.concurrent.StructuredTaskScope** và các kiểu lồng bên trong.
- Một số method preview trong **javax.crypto.EncryptedPrivateKeyInfo**.

Khi review source, kiểm tra cả import và lời gọi method preview. Không phải mọi preview feature đều xuất hiện dưới dạng một class có tên dễ nhận ra; JEP 507 là thay đổi ngôn ngữ.

### 3.2. Không bật preview cho tính năng đã final

JDK 25 cũng có nhiều tính năng đã trở thành permanent. Ví dụ:

| JEP | Tính năng | Cần preview flag? |
|---|---|---|
| JEP 506 | Scoped Values | Không |
| JEP 510 | Key Derivation Function API | Không |
| JEP 511 | Module Import Declarations | Không |
| JEP 512 | Compact Source Files and Instance Main Methods | Không |
| JEP 513 | Flexible Constructor Bodies | Không |
| JEP 514/515 | Ahead-of-Time Command-Line Ergonomics / Method Profiling | Không phải preview API |

Nếu source chỉ dùng các tính năng đã final này, cấu hình release mặc định vẫn biên dịch bằng **--release 25** mà không cần **--enable-preview**.

## 4. Incubator module trong JDK 25

JDK 25 cung cấp **Vector API (Tenth Incubator)** theo JEP 508 trong module:

```text
jdk.incubator.vector
```

Vector API biểu diễn phép tính trên các lane dữ liệu để runtime có thể biên dịch thành lệnh SIMD phù hợp với phần cứng, ví dụ AVX trên x64 hoặc NEON trên AArch64.

Các điểm cần hiểu:

- Đây là incubator module, không phải preview feature.
- Module có tên **jdk.incubator.vector**.
- API có thể thay đổi hoặc bị loại bỏ ở release tương lai.
- Hiệu năng phụ thuộc CPU, vector species, JIT compiler và workload.
- Có scalar fallback khi runtime không thể biên dịch phép toán thành vector instruction.
- Cần benchmark trên phần cứng triển khai; không giả định dùng Vector API luôn nhanh hơn code scalar.

Tài liệu JDK 25 ghi rõ module này là incubating feature và có thể bị loại bỏ trong một release tương lai. Vì vậy, hãy cô lập phần phụ thuộc Vector API và duy trì đường thực thi thay thế phù hợp.

## 5. Nguyên tắc cấu hình phát hành mặc định

Cấu hình mặc định phải phản ánh artifact mà nhóm muốn phát hành thường xuyên.

**Default release profile:**

- Compile với **--release 25**.
- Không truyền **--enable-preview**.
- Không thêm **jdk.incubator.vector** vào module graph nếu ứng dụng không dùng module đó.
- Không dùng source hoặc dependency phụ thuộc preview/incubator.
- Test và runtime chạy với cấu hình bình thường.
- Artifact được đóng gói trong output directory riêng của cấu hình release.

Cấu hình này vẫn sử dụng được các tính năng đã final của Java 25.

### 5.1. Vì sao phải tách output directory?

Nếu build preview ghi class file vào cùng thư mục với build release, file cũ có thể còn sót lại sau khi đổi profile. Artifact sau đó có thể chứa class preview dù lệnh build hiện tại không bật preview.

Dùng output directory riêng, ví dụ:

```text
build/
  release/
    classes/
    test-classes/
    app.jar
  preview-jdk25/
    classes/
    test-classes/
    app-preview.jar
  vector-jdk25/
    classes/
    test-classes/
    app-vector.jar
```

Với Maven, có thể dùng module hoặc profile/source layout riêng và luôn clean khi đổi chế độ build. Với Gradle, dùng source set/task/output riêng khi dự án có nhiều artifact. Không tái sử dụng output của một chế độ cho chế độ khác.

### 5.2. Đặt tên artifact thể hiện mức ổn định

Ví dụ:

| Artifact | Nội dung | Cách sử dụng |
|---|---|---|
| **orders-service.jar** | Chỉ API ổn định | Artifact phát hành mặc định |
| **orders-service-preview25.jar** | Có preview feature JDK 25 | Chỉ thử nghiệm trên JDK 25 có bật preview |
| **orders-service-vector25.jar** | Có phụ thuộc Vector API incubator | Chỉ chạy trên runtime có module Vector |
| **orders-service-preview-vector25.jar** | Có cả preview và incubator | Chỉ dùng cho test/benchmark có cấu hình rõ |

Tên chỉ là quy ước minh họa. Điều quan trọng là registry, image tag và deployment manifest thể hiện chính xác artifact phụ thuộc tính năng nào.

## 6. Cấu hình mặc định bằng javac và java

Với source chỉ dùng API ổn định:

```bash
javac --release 25 \
      -d build/release/classes \
      src/main/java/example/Main.java

java -cp build/release/classes example.Main
```

Không thêm **--enable-preview** hoặc **--add-modules jdk.incubator.vector** nếu source không cần chúng.

**--release 25** đặt ngôn ngữ, API Java SE và bytecode target theo Java 25. Nó không bật preview và cũng không tự thêm incubator module.

## 7. Cấu hình preview riêng cho JDK 25

Để biên dịch source sử dụng preview feature của JDK 25, phải dùng compiler JDK 25 và bật preview:

```bash
javac --enable-preview --release 25 -Xlint:preview \
      -d build/preview-jdk25/classes \
      src/preview25/java/example/PreviewMain.java
```

Chạy bằng runtime JDK 25 với cùng chế độ preview:

```bash
java --enable-preview \
     -cp build/preview-jdk25/classes \
     example.PreviewMain
```

### 7.1. Ý nghĩa từng tùy chọn

| Tùy chọn | Vai trò |
|---|---|
| **--enable-preview** | Bật hỗ trợ preview feature của release JDK đang dùng |
| **--release 25** | Giới hạn source/API/bytecode theo Java SE 25 |
| **-Xlint:preview** | Hiển thị chi tiết cảnh báo về việc dùng preview |
| **-d** | Đưa class file vào output directory riêng |

Preview phải được bật ở cả compiler và runtime. Nếu chỉ bật khi compile, JVM có thể từ chối class file phụ thuộc preview khi chạy.

### 7.2. Preview gắn với release

Dùng compiler JDK 25 để biên dịch preview của JDK 25. Không dùng compiler JDK 26 hoặc JDK mới hơn với **--enable-preview --release 25** để tái tạo preview của JDK 25. **--enable-preview** chỉ bật preview của chính release mà compiler hiện tại hỗ trợ.

Class file phụ thuộc preview có minor version **65535**. Theo JVM Specification, class file như vậy gắn với release đã định nghĩa preview đó và không được tải bởi một release khác, kể cả khi runtime mới hơn cũng bật preview.

### 7.3. Không bật preview toàn cục

Tránh đặt **--enable-preview** trong các biến môi trường toàn cục như **JDK_JAVA_OPTIONS** cho mọi tiến trình trên máy hoặc container. Cách này khiến test, tool quản trị và ứng dụng không liên quan đều nhận cấu hình preview.

Hãy truyền flag qua task/profile cụ thể để có thể audit và tắt dễ dàng.

## 8. Cấu hình incubator module riêng

Với ứng dụng dùng Vector API trên classpath hoặc unnamed module, thêm module khi compile:

```bash
javac --release 25 \
      --add-modules jdk.incubator.vector \
      -d build/vector-jdk25/classes \
      src/vector25/java/example/VectorMain.java
```

Khi chạy, cũng thêm module:

```bash
java --add-modules jdk.incubator.vector \
     -cp build/vector-jdk25/classes \
     example.VectorMain
```

**--add-modules** yêu cầu module system đưa module được chỉ định vào module graph. Compiler có thể cần tùy chọn này khi source không nằm trong một named module nhưng tham chiếu API của module bổ sung.

### 8.1. Với ứng dụng modular

Nếu ứng dụng có module descriptor, khai báo dependency trực tiếp:

```java
module com.example.vectorapp {
    requires jdk.incubator.vector;
}
```

Khi biên dịch named module, module descriptor thể hiện dependency. Khi chạy, module system giải quyết module theo quan hệ requires. Nếu source nằm trong classpath/unnamed module, dùng **--add-modules jdk.incubator.vector** như ví dụ trước.

Không thêm requires Vector API vào module mặc định nếu phần code phát hành không dùng Vector API.

### 8.2. Cảnh báo incubator

Compiler/runtime có thể thông báo đang sử dụng incubator module. Giữ cảnh báo này trong log build và test để reviewer nhận biết artifact có phụ thuộc thử nghiệm.

Không tắt warning một cách toàn cục chỉ để log sạch hơn. Nếu có suppression cần thiết, giới hạn đúng scope và vẫn ghi nhận module trong inventory.

## 9. Kết hợp preview và incubator khi thật sự cần

Một ứng dụng có thể vừa dùng preview API vừa dùng Vector API. Khi đó, bật cả hai cơ chế riêng biệt:

```bash
javac --enable-preview --release 25 \
      --add-modules jdk.incubator.vector \
      -Xlint:preview \
      -d build/preview-vector-jdk25/classes \
      src/preview-vector25/java/example/Main.java
```

Runtime:

```bash
java --enable-preview \
     --add-modules jdk.incubator.vector \
     -cp build/preview-vector-jdk25/classes \
     example.Main
```

Hai cờ có mục đích khác nhau:

| Cờ | Bật điều gì? | Không làm gì? |
|---|---|---|
| **--enable-preview** | Preview feature của JDK 25 | Không tự thêm Vector module |
| **--add-modules jdk.incubator.vector** | Đưa incubator module vào module graph | Không bật preview API |

Không dùng **--enable-preview** thay cho **--add-modules**, và cũng không dùng **--add-modules** thay cho preview flag.
## 10. Tách profile trong Maven

Maven nên có một cấu hình mặc định dùng API ổn định và các profile chỉ kích hoạt khi developer hoặc CI yêu cầu.

### 10.1. Cấu hình mặc định

Phần cấu hình cơ sở trong pom.xml:

```xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>25</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Không đặt **--enable-preview** hoặc **--add-modules jdk.incubator.vector** trong cấu hình cơ sở.

Ghim phiên bản tương thích của Maven Compiler Plugin, Surefire và Failsafe trong dự án thật; không phụ thuộc vào phiên bản plugin cũ được kế thừa ngầm từ super POM. Đồng thời xác nhận Maven đang chạy với JDK 25 hoặc compiler toolchain trỏ đúng JDK 25.

### 10.2. Profile preview

Thêm profile opt-in:

```xml
<profiles>
    <profile>
        <id>preview-jdk25</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <configuration>
                        <release>25</release>
                        <compilerArgs>
                            <arg>--enable-preview</arg>
                            <arg>-Xlint:preview</arg>
                        </compilerArgs>
                    </configuration>
                </plugin>

                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <configuration>
                        <argLine>--enable-preview</argLine>
                    </configuration>
                </plugin>

                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-failsafe-plugin</artifactId>
                    <configuration>
                        <argLine>--enable-preview</argLine>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

Kích hoạt có chủ đích:

```bash
mvn -Ppreview-jdk25 clean verify
```

Compiler và test JVM đều cần preview. Nếu dùng plugin khác để khởi chạy ứng dụng hoặc integration test, truyền **--enable-preview** cho JVM do plugin đó tạo ra.

### 10.3. Profile incubator Vector API

Profile riêng cho Vector API:

```xml
<profile>
    <id>vector-jdk25</id>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <release>25</release>
                    <compilerArgs>
                        <arg>--add-modules</arg>
                        <arg>jdk.incubator.vector</arg>
                    </compilerArgs>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <argLine>--add-modules=jdk.incubator.vector</argLine>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <configuration>
                    <argLine>--add-modules=jdk.incubator.vector</argLine>
                </configuration>
            </plugin>
        </plugins>
    </build>
</profile>
```

Kích hoạt:

```bash
mvn -Pvector-jdk25 clean verify
```

Nếu một build cần cả preview và Vector API, hãy tạo profile tổng hợp hoặc hợp nhất các compiler arguments và runtime arguments thành một cấu hình rõ ràng. Không để cấu hình của profile này ghi đè mất cờ cần thiết của profile kia. Kiểm tra effective POM và command line thực tế của test JVM.

### 10.4. Profile tổng hợp preview + incubator

Khi có use case cần cả hai, có thể khai báo profile riêng:

```xml
<profile>
    <id>preview-vector-jdk25</id>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <release>25</release>
                    <compilerArgs>
                        <arg>--enable-preview</arg>
                        <arg>-Xlint:preview</arg>
                        <arg>--add-modules</arg>
                        <arg>jdk.incubator.vector</arg>
                    </compilerArgs>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <argLine>--enable-preview --add-modules=jdk.incubator.vector</argLine>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <configuration>
                    <argLine>--enable-preview --add-modules=jdk.incubator.vector</argLine>
                </configuration>
            </plugin>
        </plugins>
    </build>
</profile>
```

Đây là profile thử nghiệm. Không kích hoạt nó trong pipeline release mặc định.

## 11. Tách cấu hình trong Gradle

Gradle có thể bật từng nhóm bằng project property. Cấu hình dưới đây dùng Kotlin DSL trong build.gradle.kts.

### 11.1. Cấu hình mặc định và opt-in properties

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
}

val useJdk25Preview =
    providers.gradleProperty("jdk25Preview").isPresent

val useJdk25Vector =
    providers.gradleProperty("jdk25Vector").isPresent

tasks.withType<JavaCompile>().configureEach {
    options.release.set(25)

    if (useJdk25Preview) {
        options.compilerArgs.add("--enable-preview")
        options.compilerArgs.add("-Xlint:preview")
    }

    if (useJdk25Vector) {
        options.compilerArgs.addAll(
            listOf("--add-modules", "jdk.incubator.vector")
        )
    }
}

tasks.withType<Test>().configureEach {
    if (useJdk25Preview) {
        jvmArgs("--enable-preview")
    }

    if (useJdk25Vector) {
        jvmArgs("--add-modules=jdk.incubator.vector")
    }
}

tasks.withType<JavaExec>().configureEach {
    if (useJdk25Preview) {
        jvmArgs("--enable-preview")
    }

    if (useJdk25Vector) {
        jvmArgs("--add-modules=jdk.incubator.vector")
    }
}
```

Không truyền property nào thì build dùng cấu hình release mặc định: chỉ **--release 25**.

### 11.2. Chạy từng chế độ

Build/test release mặc định:

```bash
./gradlew clean test
```

Build/test preview:

```bash
./gradlew clean test -Pjdk25Preview
```

Build/test Vector API:

```bash
./gradlew clean test -Pjdk25Vector
```

Build/test cả hai:

```bash
./gradlew clean test -Pjdk25Preview -Pjdk25Vector
```

Với Groovy DSL, dùng cùng nguyên tắc: đọc project property, thêm compiler args vào JavaCompile, thêm JVM args vào Test và JavaExec. Không đưa hai cờ thử nghiệm vào cấu hình global nếu không phải mọi task đều cần chúng.

### 11.3. Kiểm tra task do plugin tạo

Một số plugin tạo JVM riêng để chạy integration test, application, benchmark hoặc code generator. **Test** và **JavaExec** không bao phủ mọi launcher của plugin bên thứ ba. Kiểm tra task graph, command line và log để xác nhận JVM thực tế nhận đúng cờ.

## 12. Tách source set và module theo tính ổn định

Nếu dự án có nhiều loại code, tách source để cấu hình release không vô tình compile phần thử nghiệm.

Một cấu trúc minh họa:

```text
src/
  main/
    java/                 # API ổn định, artifact mặc định
  preview25/
    java/                 # Source dùng preview của JDK 25
  vector25/
    java/                 # Source dùng jdk.incubator.vector
  preview-vector25/
    java/                 # Source cần cả hai
```

Cách tổ chức này giúp:

- Reviewer nhận ra source phụ thuộc preview/incubator.
- CI build từng cấu hình riêng.
- Release artifact không compile nhầm source thử nghiệm.
- Có thể thay adapter Vector API hoặc preview API mà không đổi public API của ứng dụng.
- Dễ xóa source thử nghiệm khi tính năng final hoặc khi nhóm quyết định không tiếp tục.

Với dự án lớn, cân nhắc tách thành Maven/Gradle subproject riêng. Module thử nghiệm có thể phụ thuộc module lõi ổn định, còn module lõi không phụ thuộc ngược vào preview/incubator module.

### 12.1. Giữ API thử nghiệm sau adapter

Ví dụ phần xử lý số học có thể có interface ổn định:

```java
public interface DistanceCalculator {
    double distance(double[] left, double[] right);
}
```

Một implementation dùng scalar Java bình thường có thể nằm trong artifact mặc định. Implementation khác dùng Vector API nằm trong module thử nghiệm. Application chọn implementation qua wiring/configuration khi chạy benchmark.

Không để kiểu FloatVector, VectorSpecies hoặc StructuredTaskScope xuất hiện trong public API của module lõi nếu consumer không thể chấp nhận dependency thử nghiệm.

## 13. Đóng gói module incubator bằng jlink

Với modular application có module-info.java khai báo **requires jdk.incubator.vector**, jlink có thể tạo runtime image chứa module cần thiết.

Ví dụ:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.vectorapp \
  --output build/runtime-vector25
```

Vì module ứng dụng khai báo **requires jdk.incubator.vector**, module dependency được giải quyết trong graph và được đưa vào runtime image.

Nếu ứng dụng dùng classpath/unnamed module thay vì module descriptor, khai báo rõ module cần thêm vào root set của jlink:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,jdk.incubator.vector \
  --output build/runtime-vector25
```

Ví dụ thứ hai chỉ minh họa module set tối thiểu; ứng dụng thật còn cần các module JDK khác như java.logging, java.sql hoặc java.net.http nếu dùng chúng. Xác định module cần thiết bằng dependency analysis và test runtime image.

Không đưa jdk.incubator.vector vào runtime image phát hành mặc định nếu artifact đó không sử dụng module.

## 14. Đóng gói ứng dụng bằng jpackage

jpackage có thể tạo application image hoặc installer và sử dụng runtime image đã tạo.

Artifact mặc định:

```bash
jpackage \
  --type app-image \
  --name orders-release \
  --input target \
  --main-jar orders.jar \
  --runtime-image build/runtime-release
```

Artifact thử nghiệm có preview:

```bash
jpackage \
  --type app-image \
  --name orders-preview25 \
  --input target \
  --main-jar orders-preview25.jar \
  --runtime-image build/runtime-preview25 \
  --java-options "--enable-preview"
```

Artifact dùng Vector API:

```bash
jpackage \
  --type app-image \
  --name orders-vector25 \
  --input target \
  --main-jar orders-vector25.jar \
  --runtime-image build/runtime-vector25 \
  --java-options "--add-modules=jdk.incubator.vector"
```

Nếu ứng dụng cần cả hai, truyền cả **--enable-preview** và **--add-modules=jdk.incubator.vector** trong java options của launcher. Kiểm thử launcher được tạo ra trên đúng OS/architecture; installer hoặc app image không tự làm preview/incubator API trở nên stable.
## 15. Cấu hình runtime khi triển khai

Compile thành công không đảm bảo runtime được cấu hình đúng. Deployment manifest, service manager hoặc launcher phải giữ đúng cờ cho artifact tương ứng.

### 15.1. Default release

Ví dụ chạy artifact ổn định:

```bash
java -Xms512m -Xmx2g -jar orders.jar
```

Không có preview flag và không thêm incubator module.

### 15.2. Preview artifact

```bash
java --enable-preview \
     -Xms512m -Xmx2g \
     -jar orders-preview25.jar
```

Runtime phải thuộc JDK 25. Kiểm tra cờ trong process command line và startup log.

### 15.3. Vector artifact

```bash
java --add-modules=jdk.incubator.vector \
     -Xms512m -Xmx2g \
     -jar orders-vector25.jar
```

Đảm bảo runtime image có module **jdk.incubator.vector**. Nếu chạy từ custom runtime thiếu module, JVM sẽ không thể giải quyết module dependency.

### 15.4. Preview + Vector artifact

```bash
java --enable-preview \
     --add-modules=jdk.incubator.vector \
     -Xms512m -Xmx2g \
     -jar orders-preview-vector25.jar
```

Không gộp cờ thử nghiệm vào deployment manifest chung của mọi service. Mỗi workload chỉ nhận các cờ cần thiết cho artifact của nó.

## 16. Thiết kế CI pipeline theo ma trận

Một pipeline có thể tách thành các job sau:

| Job | Compiler | Compile args | Runtime args | Artifact |
|---|---|---|---|---|
| **release-default** | JDK 25 | **--release 25** | Không preview/incubator | **app.jar** |
| **preview-jdk25** | JDK 25 | **--enable-preview --release 25** | **--enable-preview** | **app-preview25.jar** |
| **vector-jdk25** | JDK 25 | **--release 25 --add-modules jdk.incubator.vector** | **--add-modules jdk.incubator.vector** | **app-vector25.jar** |
| **preview-vector-jdk25** | JDK 25 | Cả hai nhóm cờ | Cả hai nhóm cờ | **app-preview-vector25.jar** |

Job **release-default** phải là job bắt buộc trước khi publish artifact mặc định. Các job preview/incubator là opt-in hoặc chạy trong pipeline thử nghiệm riêng.

### 16.1. Những gì cần kiểm tra trong CI

- Ghi **java --version** và **javac --version**.
- Ghi compiler args và runtime args thực tế.
- Không dùng chung output directory giữa các job.
- Chạy unit test và integration test bằng đúng JDK 25.
- Kiểm tra warning preview/incubator.
- Kiểm tra artifact name, checksum và metadata.
- Kiểm tra deployment launcher/container có nhận đúng cờ.
- Giữ artifact thử nghiệm trong registry hoặc repository riêng nếu chính sách yêu cầu.
- Không publish preview/incubator artifact dưới tag stable mặc định.

### 16.2. Kiểm tra class file preview

Class file phụ thuộc preview có minor version **65535**. Có thể dùng **javap -verbose** để kiểm tra class đại diện trong artifact:

```bash
javap -verbose -classpath target/app.jar com.example.Main
```

Đọc phần **minor version**. Với class file release bình thường, minor version không phải **65535**. Nếu artifact mặc định chứa class preview, kiểm tra lại source set và output directory trước khi publish.

Không chỉ kiểm tra class main. Nếu class khác trong dependency graph được biên dịch bằng preview, ứng dụng vẫn có thể phụ thuộc preview.

### 16.3. Kiểm tra incubator dependency

Dùng **jdeps** để xem dependency module của artifact:

```bash
jdeps --multi-release 25 --list-deps --recursive target/app-vector25.jar
```

Nếu artifact mặc định không chủ ý dùng Vector API, kiểm tra để bảo đảm **jdk.incubator.vector** không xuất hiện trong module/dependency graph của nó.

Với classpath app hoặc artifact có dependency động, kết hợp dependency scan với integration test và runtime log.

## 17. Quy tắc khi nâng cấp sang JDK khác

Preview và incubator là các điểm phụ thuộc có thể thay đổi theo release.

### 17.1. Preview API

Khi chuyển từ JDK 25 sang release mới:

1. Kiểm tra JEP của preview feature trong release đích.
2. Xác định feature đã final, được preview lại, đổi API hay bị loại bỏ.
3. Sửa source theo API của release đích.
4. Biên dịch lại bằng compiler của release đích.
5. Chạy test bằng runtime của release đích.
6. Bỏ **--enable-preview** nếu feature đã final và source không dùng preview khác.

Không mang class file preview JDK 25 sang runtime JDK 26 hoặc JDK mới hơn.

### 17.2. Incubator module

Khi chuyển Vector API sang JDK mới:

- Đọc JEP mới nhất của Vector API.
- So sánh method, vector species và module name.
- Cập nhật code và benchmark.
- Kiểm tra CPU architecture được triển khai.
- Build lại custom runtime image.
- Kiểm tra scalar fallback và hiệu năng trên workload thật.
- Giữ adapter để có thể thay implementation khi API thay đổi.

Không giả định module incubator giữ nguyên signature hoặc tên package qua mọi release.

### 17.3. Xóa cấu hình thử nghiệm khi không còn cần

Khi preview API đã final hoặc module incubator không còn được dùng:

- Xóa profile không còn cần.
- Xóa runtime flag tương ứng.
- Xóa module khỏi module descriptor và custom runtime image.
- Xóa source set và artifact thử nghiệm đã hết vòng đời.
- Bổ sung test xác nhận artifact mặc định không còn phụ thuộc.
- Cập nhật tài liệu vận hành và CI.

## 18. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| javac báo preview feature disabled | Thiếu **--enable-preview** | Chỉ thêm flag trong profile preview |
| Compile được nhưng runtime từ chối class | Runtime thiếu **--enable-preview** | Bật preview cho đúng JVM khởi chạy |
| Preview class chạy trên JDK mới bị lỗi | Class file preview gắn với release cũ | Biên dịch lại và cập nhật API |
| package jdk.incubator.vector does not exist | Compiler chưa resolve incubator module | Thêm **--add-modules jdk.incubator.vector** hoặc khai báo **requires** |
| Runtime báo module vector không được tìm thấy | Runtime image thiếu module hoặc module graph chưa resolve | Thêm module vào jlink image và runtime graph |
| Chỉ test fail, compile pass | Surefire/Failsafe/Test JVM thiếu runtime args | Cấu hình JVM args cho test task |
| Local chạy nhưng CI fail | JDK compiler/runtime không cùng release | Ghim JDK toolchain và in version trong log |
| Release artifact chứa class preview | Dùng chung output directory hoặc source set | Tách output và clean build |
| Artifact stable phát warning incubator | Dependency thử nghiệm lọt vào graph | Rà soát source/dependency và module descriptor |
| Chỉ một service cần preview nhưng mọi service đều bật | Dùng cờ JVM toàn cục | Cấu hình theo process/artifact |
| Vector API không nhanh hơn scalar | CPU không hỗ trợ shape, workload quá nhỏ hoặc JIT không vectorize | Dùng preferred species và benchmark thực tế |
| Maven profile preview làm mất cờ vector | Plugin configuration bị merge/ghi đè | Dùng profile tổng hợp và kiểm tra effective POM |
| Gradle test pass nhưng JavaExec fail | Runtime task không nhận cờ | Cấu hình riêng **JavaExec** và task do plugin tạo |
| jpackage app khởi động lỗi preview | Launcher thiếu Java option | Thêm **--java-options "--enable-preview"** |

## 19. Ma trận nghiệm thu

| Mã | Kịch bản | Kết quả kỳ vọng |
|---|---|---|
| BUILD-FLAG-01 | Build mặc định bằng **--release 25** | Thành công mà không cần preview/incubator |
| BUILD-FLAG-02 | Kiểm tra compiler command của release | Không có **--enable-preview** |
| BUILD-FLAG-03 | Kiểm tra runtime command của release | Không có preview/incubator flag không cần thiết |
| BUILD-FLAG-04 | Compile source preview không có flag | Compiler từ chối preview usage |
| BUILD-FLAG-05 | Compile preview với JDK 25 và **--enable-preview** | Thành công |
| BUILD-FLAG-06 | Chạy preview class không bật preview | Runtime từ chối class phụ thuộc preview |
| BUILD-FLAG-07 | Chạy preview class với JDK 25 và preview flag | Thành công |
| BUILD-FLAG-08 | Compile Vector API không resolve module | Compiler không tìm thấy module/package |
| BUILD-FLAG-09 | Compile Vector API với **--add-modules** | Thành công và có incubator warning |
| BUILD-FLAG-10 | Chạy Vector API với module đã resolve | Runtime tìm thấy module |
| BUILD-FLAG-11 | Modular app khai báo **requires jdk.incubator.vector** | Dependency module được resolve |
| BUILD-FLAG-12 | Build có cả preview và Vector API | Có đủ hai nhóm cờ ở compile/runtime |
| BUILD-FLAG-13 | Maven default profile | Không bật preview/incubator |
| BUILD-FLAG-14 | Maven preview profile | Compiler và Surefire/Failsafe đều bật preview |
| BUILD-FLAG-15 | Maven vector profile | Compiler và test JVM resolve Vector module |
| BUILD-FLAG-16 | Gradle default task | Không thêm cờ thử nghiệm |
| BUILD-FLAG-17 | Gradle preview/vector properties | Chỉ task tương ứng nhận cờ |
| BUILD-FLAG-18 | jlink runtime image | Chỉ chứa module cần thiết |
| BUILD-FLAG-19 | jpackage preview launcher | Launcher có preview runtime option |
| BUILD-FLAG-20 | Kiểm tra class file trong release artifact | Không có class preview minor version **65535** |
| BUILD-FLAG-21 | Kiểm tra dependency module release artifact | Không có Vector module nếu không chủ ý dùng |
| BUILD-FLAG-22 | Chuyển JDK release | Preview/incubator source được đánh giá và build lại |

## 20. Bài thực hành tổng hợp

### Bài A — Tạo cấu hình release mặc định

1. Tạo một chương trình Java 25 chỉ dùng API ổn định.
2. Cấu hình Maven hoặc Gradle với **--release 25**.
3. Không bật preview và không thêm incubator module.
4. Build, test và đóng gói artifact.
5. Lưu compiler/runtime command line làm bằng chứng.

**Sản phẩm:** artifact release mặc định và build log.

### Bài B — Tạo profile preview

1. Tạo một source riêng dùng một preview feature của JDK 25.
2. Build không có preview flag và xác nhận compile thất bại.
3. Bật **--enable-preview** cho compiler.
4. Bật cùng flag cho test/runtime.
5. Kiểm tra class file preview và tên artifact.

**Sản phẩm:** artifact preview riêng, profile build và test report.

### Bài C — Tạo profile Vector API

1. Tạo một implementation dùng **jdk.incubator.vector**.
2. Thêm **--add-modules jdk.incubator.vector** khi compile và chạy.
3. Nếu dùng named module, khai báo **requires**.
4. So sánh kết quả với scalar implementation.
5. Benchmark trên CPU mục tiêu và lưu JDK/CPU metadata.

**Sản phẩm:** artifact vector riêng, benchmark và module graph.

### Bài D — Tạo profile kết hợp

1. Kết hợp source preview và Vector API.
2. Truyền cả hai nhóm cờ ở compile/test/runtime.
3. Xác nhận default release không nhận cờ thử nghiệm.
4. Dùng output directory riêng.
5. Đóng gói runtime image phù hợp.

**Sản phẩm:** artifact thử nghiệm kết hợp và deployment manifest.

### Bài E — Kiểm tra CI và rollback

1. Tạo job release-default, preview-jdk25 và vector-jdk25.
2. Chạy test độc lập.
3. Kiểm tra class file preview và module dependency.
4. Publish artifact theo tên/tag riêng.
5. Diễn tập rollback về artifact stable mặc định.
6. Ghi lại owner và điều kiện cho phép chạy artifact thử nghiệm.

**Sản phẩm:** CI pipeline, artifact inventory và quy trình rollback.

## 21. Câu hỏi tự đánh giá

1. Preview feature và incubator module khác nhau ở điểm nào?
2. JDK 25 có những preview feature nào?
3. Vector API trong JDK 25 thuộc module nào và có trạng thái gì?
4. Vì sao **--enable-preview** không tự resolve **jdk.incubator.vector**?
5. Vì sao **--add-modules** không làm incubator API trở thành stable?
6. **--release 25** có tự bật preview không?
7. Vì sao compiler và runtime đều cần preview flag?
8. Preview class file có minor version đặc biệt nào?
9. Vì sao preview class file gắn với release đã biên dịch?
10. Khi nào ứng dụng modular nên khai báo **requires jdk.incubator.vector**?
11. Vì sao phải tách output directory giữa release và preview build?
12. Maven Surefire/Failsafe cần cấu hình gì khi chạy preview code?
13. Gradle cần cấu hình những task runtime nào?
14. Khi nào cần một profile kết hợp preview và incubator?
15. jlink cần đưa module nào vào runtime image của ứng dụng dùng Vector API?
16. Vì sao artifact thử nghiệm phải có tên và tag riêng?
17. Làm thế nào kiểm tra release artifact không chứa preview class?
18. Khi JDK mới được phát hành, cần làm gì với preview/incubator source?

**Tiêu chí hoàn thành:** Bạn tạo được cấu hình phát hành mặc định chỉ dùng API ổn định, bật preview và incubator bằng profile riêng, cấu hình compile/test/runtime nhất quán, đóng gói đúng module và kiểm tra được artifact không mang dependency thử nghiệm ngoài chủ đích.

## 22. Nguồn tham khảo chính thức

- [Oracle Java SE 25 — Preview API List](https://docs.oracle.com/en/java/javase/25/docs/api/preview-list.html)
- [Oracle Java SE 25 — Preview Language and VM Features](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html)
- [Java Virtual Machine Specification, Java SE 25 — Preview Features and Class Files](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-1.html)
- [OpenJDK JEP 12 — Preview Features](https://openjdk.org/jeps/12)
- [OpenJDK JEP 470 — PEM Encodings of Cryptographic Objects (Preview)](https://openjdk.org/jeps/470)
- [OpenJDK JEP 502 — Stable Values (Preview)](https://openjdk.org/jeps/502)
- [OpenJDK JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505)
- [OpenJDK JEP 507 — Primitive Types in Patterns, instanceof, and switch (Third Preview)](https://openjdk.org/jeps/507)
- [OpenJDK JEP 508 — Vector API (Tenth Incubator)](https://openjdk.org/jeps/508)
- [Oracle Java SE 25 — jdk.incubator.vector Module](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/module-summary.html)
- [Oracle Java SE 25 — javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [Oracle Java SE 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Oracle Java SE 25 — jlink Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jlink.html)
- [Oracle Java SE 25 — jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html)
- [Oracle JDK 25 Migration Guide — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html)

**Điểm cần nhớ:** Cấu hình phát hành mặc định không nên bật preview hoặc thêm incubator module. Với JDK 25, preview cần **--enable-preview** ở cả compile và runtime; Vector API cần resolve **jdk.incubator.vector** bằng module system. Tách profile, source set, output directory, artifact và deployment option giúp nhóm thử nghiệm có chủ đích mà không làm thay đổi cấu hình phát hành ổn định.
