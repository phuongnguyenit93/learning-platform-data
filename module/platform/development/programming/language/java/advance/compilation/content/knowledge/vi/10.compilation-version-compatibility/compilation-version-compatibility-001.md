# Phân biệt phiên bản JDK công cụ, ngôn ngữ nguồn và class đích khi biên dịch Java

## 1. Ba câu hỏi khác nhau trong một bản build

Một dự án Java thường nói “dùng Java 17”, nhưng câu này chưa đủ để biết build có tương thích với Java 17 hay không. Cần phân biệt **ba trục phiên bản**:

1. **JDK công cụ (*compiler/toolchain JDK*)**: bộ JDK thực sự cung cấp `javac` đang chạy, ví dụ JDK 24. Nó quyết định compiler hỗ trợ những mức source/target nào, có những tùy chọn và sửa lỗi nào.
2. **Ngôn ngữ nguồn (*source language level*)**: những cấu trúc cú pháp Java mà mã nguồn được phép dùng, ví dụ Java 17. Nó được điều khiển bằng `-source 17`, `--source 17` hoặc gián tiếp qua `--release 17`.
3. **Class đích (*target class-file level*)**: định dạng bytecode JVM được sinh ra, ví dụ class-file major version **61** cho Java 17. Nó được điều khiển bằng `-target 17`, `--target 17` hoặc `--release 17`.

Có **trục thứ tư phải kiểm tra** nếu muốn chạy thật: **nền tảng API của Java SE/JDK mà code được phép tham chiếu**. `-source` và `-target` **không tự giới hạn** API chuẩn hiện có trên JDK compiler. `--release` thường là cách đúng để đồng thời ràng buộc source language, target class file **và API nền tảng của release đích**.

| Điều cần xác định | Ví dụ | Tùy chọn/kiểm tra |
| --- | --- | --- |
| Compiler nào chạy? | `javac 24.0.2` | `javac -version`, cấu hình JDK toolchain |
| Cú pháp nguồn được phép dùng? | Java 17 | `-source 17`, `--release 17` |
| Class file đầu ra thuộc đời nào? | Major 61 = Java 17 | `-target 17`, `--release 17`, `javap -verbose` |
| API chuẩn nào được gọi? | Java SE 17 | `--release 17` giúp giới hạn API |
| Runtime thật là bản nào? | `java 17` hoặc `java 21` | `java -version`, launcher/container và CI |

Ví dụ **`javac` của JDK 24 biên dịch mã nguồn theo Java 17 và sinh bytecode Java 17** là hoàn toàn hợp lệ. Điều đó **không** có nghĩa máy dùng JDK 17 để biên dịch. Ngược lại, việc đang dùng JDK 24 cũng **không** buộc ứng dụng chỉ chạy trên Java 24.

## 2. Quan hệ giữa phiên bản tool, source, target và API

### 2.1. JDK công cụ: ai thực hiện quá trình compile?

`javac` là chương trình compiler thuộc JDK, không phải JVM runtime chạy ứng dụng sau khi build. JDK mới thường có thể biên dịch cho một số release cũ, nhưng **không hỗ trợ vô hạn tất cả release trước đây**. Hãy kiểm tra danh sách `Supported releases` trong:

~~~bash
javac -version
javac --help
~~~

Một máy có thể cài nhiều JDK; `javac -version` và `java -version` đôi khi trỏ tới **hai cài đặt khác nhau** do `PATH`, `JAVA_HOME`, IDE, Maven/Gradle toolchain hoặc container. Khi debug, phải xem compiler **thực sự** được build tool chọn, chứ không suy từ một terminal riêng.

Với thư viện được compile qua Maven/Gradle, version JDK chạy chính build tool cũng có thể khác với JDK mà task `JavaCompile` chọn qua toolchain. Trong CI, kiểm tra cả hai nếu có plugin phụ thuộc phiên bản JDK.

### 2.2. Source language level: ngôn ngữ nào hợp lệ?

`-source 17` bảo compiler kiểm tra các quy tắc ngôn ngữ Java 17. Nó quyết định source có dùng được cú pháp được giới thiệu trong các bản Java mới hay không. Ví dụ:
- `record` là tính năng chuẩn từ Java 16 nên hợp lệ với `-source 17`.
- Pattern matching cho `switch` được hoàn thiện thành tính năng chuẩn ở Java 21, nên không thể dùng như cú pháp chuẩn Java 17.
- Các tính năng *preview* chỉ được dùng theo quy tắc riêng; không tự mở chỉ bằng `-source`.

`-source` không phải tham số chọn compiler JDK. Một JDK 24 vẫn có thể chạy compiler với `-source 17`.

### 2.3. Target class-file level: định dạng bytecode nào được sinh?

`-target 17` yêu cầu output có class-file version dành cho Java 17. JVM quá cũ sẽ từ chối nạp class file có major version mới hơn mức nó hỗ trợ.

Các mốc phổ biến:

| Java release | Class-file major version |
| --- | ---: |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 18 | 62 |
| 19 | 63 |
| 20 | 64 |
| 21 | 65 |
| 22 | 66 |
| 23 | 67 |
| 24 | 68 |

Với Java 9 trở lên, major version tăng một đơn vị theo mỗi release: **major = release + 44**. Đây là cách nhớ cho các đời Java hiện đại, không thay cho việc kiểm tra `javap -verbose`.

Trên Java 17 class file bình thường thường có **major 61, minor 0**. Trong một số trường hợp class file sử dụng preview features có **minor 65535**; các class preview chịu quy tắc chạy riêng, không thể coi chúng giống class 61.0 thông thường.

### 2.4. API platform level: phần dễ bỏ sót nhất

Giả sử dùng JDK 24 để compile với:

~~~bash
javac -source 17 -target 17 ApiDemo.java
~~~

Hai tùy chọn này kiểm tra cú pháp Java 17 và tạo bytecode major 61. Nhưng nếu không giới hạn nền tảng, compiler có thể vẫn thấy API Java 24 trong module hệ thống của **JDK 24**.

Một lời gọi đến API mới có thể được biên dịch thành bytecode Java 17 mà **runtime Java 17 không có method/class tương ứng**. Kết quả có thể là `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi liên kết khác khi chạy trên Java 17, tùy API được dùng.

Đó là lý do **`--release 17` an toàn hơn `-source 17 -target 17`** cho đa số dự án cần chạy trên Java 17: nó còn dùng bộ API Java SE/JDK tương ứng với release 17 khi phân giải các API nền tảng được hỗ trợ.

## 3. Quy tắc của `javac`: chọn cấu hình nào?

| Lệnh | JDK compiler | Source syntax | Class target | Java SE/JDK API được kiểm soát theo target? |
| --- | --- | --- | --- | --- |
| `javac App.java` | JDK đang gọi | Mặc định của compiler | Mặc định của compiler | Theo JDK đang gọi |
| `javac -source 17 -target 17 App.java` | JDK đang gọi | Java 17 | Java 17 | **Không đảm bảo** |
| `javac --release 17 App.java` | JDK đang gọi, phải hỗ trợ release 17 | Java 17 | Java 17 | **Có**, với API nền tảng được `--release` kiểm soát |
| JDK 17 + `javac --release 17 App.java` | JDK 17 | Java 17 | Java 17 | Có |
| JDK 24 + `javac --release 17 App.java` | JDK 24 | Java 17 | Java 17 | Có |

**Giới hạn quan trọng:**
- `--release 17` không cài JDK 17 và cũng không đổi `javac` đang chạy thành phiên bản 17.
- `--release` **không dùng chung** với `-source` hoặc `-target` trong cùng invocation.
- Với `-source` / `-target`, **target không được thấp hơn source**. Ví dụ `-source 21 -target 17` bị `javac` từ chối: compiler không được hứa chuyển toàn bộ ngữ nghĩa/cú pháp Java 21 thành bytecode Java 17 theo cách đó.
- Compiler mới chỉ hỗ trợ một **tập hữu hạn** release cũ. Nếu yêu cầu không được `javac --help` liệt kê, cần chọn JDK/toolchain phù hợp.
- `--release` không tự xác minh **bên thứ ba**: nếu dependency được compile cho Java 21, cấu hình output Java 17 của ứng dụng không bảo đảm dependency đó chạy trên Java 17.
- `--release` còn áp dụng giới hạn với việc truy cập API nội bộ/non-exported của các module hệ thống. Tùy chọn `--add-exports` không thể được dùng để vượt rào các package hệ thống của release nền tảng đang target trong tình huống bị ràng buộc bởi `--release`.

Khi mục tiêu là **thực sự chạy trên Java 17**, cách bắt đầu tốt là:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/VersionDemo.java
~~~

Rồi kiểm tra trên **runtime Java 17 thực**, gồm cả dependencies, thay vì chỉ tin vào class-file version.

## 4. Thí nghiệm 1: JDK 24 biên dịch ra class Java 17

Tạo **`src/VersionDemo.java`** với nội dung đầy đủ:

~~~java
public class VersionDemo {
    public static void main(String[] args) {
        System.out.println("Hello " + "Java");
    }
}
~~~

Tại thư mục chứa `src`, dùng JDK hỗ trợ `--release 17`:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/VersionDemo.java
java -cp out VersionDemo
javap -verbose -classpath out VersionDemo
~~~

Trên Windows PowerShell có thể dùng `New-Item -ItemType Directory -Force out` thay lệnh tạo thư mục. Output ứng dụng:

~~~text
Hello Java
~~~

Trong kết quả `javap -verbose` của class này, tìm:

~~~text
minor version: 0
major version: 61
~~~

Dù compiler được kiểm chứng trong thí nghiệm là **`javac 24.0.2`**, output Java 17 vẫn có **major version 61**. Đó là bằng chứng cụ thể rằng **compiler JDK version** và **class target version** không đồng nhất.

Lệnh `java -cp out VersionDemo` chạy bằng `java` được shell chọn. Để kết luận ứng dụng thật sự chạy trên Java 17, phải chạy bằng **binary `java` của JDK/JRE 17** và xác nhận `java -version` cho đúng phiên bản đó.

## 5. Thí nghiệm 2: `-source/-target` vẫn có thể dùng API mới hơn

API `Thread.ofVirtual()` là API chuẩn có trong Java 21, **không có trong Java 17**. Dùng JDK 21 trở lên để tái hiện (ví dụ kết quả đã kiểm chứng bằng JDK 24).

Tạo **`src/ApiDemo.java`**:

~~~java
public class ApiDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread thread = Thread.ofVirtual().start(
                () -> System.out.println("virtual"));
        thread.join();
    }
}
~~~

Đây là một tệp Java độc lập. Mục tiêu thí nghiệm là minh họa **rào chắn API**; chương trình dùng API mới nên không được xem là chương trình tương thích Java 17.

### 5.1. Chỉ đặt source/target 17

~~~bash
mkdir -p out-legacy
javac -source 17 -target 17 -encoding UTF-8 -d out-legacy src/ApiDemo.java
~~~

Trên `javac 24.0.2`, lệnh này **biên dịch thành công (exit 0)** nhưng phát warning vì system modules của Java 17 chưa được cấu hình tương ứng:

~~~text
warning: [options] location of system modules is not set in conjunction with -source 17
  not setting the location of system modules may lead to class files that cannot run on JDK 17
    --release 17 is recommended instead of -source 17 -target 17 because it sets the location of system modules automatically
1 warning
~~~

`javap` vẫn cho **major 61**, nhưng bytecode có tham chiếu tới `Thread.ofVirtual()` mà Java 17 không cung cấp. Nếu thực thi đúng đường code đó trên JVM Java 17, có thể xảy ra lỗi liên kết **`NoSuchMethodError`**. Không có mâu thuẫn: định dạng class 61 là hợp lệ cho Java 17, nhưng **API tham chiếu không tương thích**.

Warning chính xác có thể thay đổi theo JDK; điểm kỹ thuật cần nắm là `-source`/`-target` không thay thế kiểm tra API nền tảng.

### 5.2. Dùng `--release 17`

~~~bash
mkdir -p out-release
javac --release 17 -encoding UTF-8 -d out-release src/ApiDemo.java
~~~

Trong thí nghiệm với `javac 24.0.2`, lệnh thất bại đúng dự kiến vì Java 17 không có method này:

~~~text
error: cannot find symbol
        Thread thread = Thread.ofVirtual().start(
                              ^
  symbol:   method ofVirtual()
  location: class Thread
1 error
~~~

Đường dẫn và số dòng trong diagnostic đã được lược bỏ để tập trung vào nội dung lỗi. Đây là **kết quả mong muốn**: cấu hình phát hiện API không tồn tại trên release đích ngay ở thời điểm biên dịch.

Nếu mục tiêu đúng là Java 21 hoặc mới hơn, có thể chọn `--release 21` và runtime Java 21+, với compiler đủ mới để hỗ trợ release đó. Không “sửa” bằng cách quay về `-source 17 -target 17` trong khi vẫn muốn chạy ở Java 17.

## 6. Thí nghiệm 3: cú pháp mới hơn target bị từ chối

Với source Java không sử dụng tính năng đặc biệt, vẫn có thể thử cố tình đưa vào hai mức không nhất quán:

~~~bash
javac -source 21 -target 17 src/VersionDemo.java
~~~

Trên `javac 24.0.2`, compiler trả diagnostic:

~~~text
error: specified target release 17 is too old for the specified source release 21
  --release 17 is recommended when compiling code to run on JDK 17
~~~

Lệnh này chủ ý **thất bại**; không có đầu ra class hợp lệ cần dùng. Compiler không hứa *backport* cấu trúc ngôn ngữ Java 21 sang runtime Java 17 bằng cách đặt target thấp tùy ý. Nếu cần cùng một codebase chạy trên Java 17, mã nguồn phải tuân thủ mức ngôn ngữ tương thích hoặc cần một quá trình chuyển đổi chuyên biệt có giới hạn rõ ràng.

## 7. Đọc class-file version và phân biệt với khả năng chạy

Khi class đã tồn tại, dùng:

~~~bash
javap -verbose -classpath out VersionDemo
~~~

Hoặc với JAR có class theo package:

~~~bash
javap -verbose -classpath application.jar com.example.Main
~~~

Tìm `major version` và `minor version`. Đây là dữ liệu **của file thật**, hữu ích hơn suy đoán từ `pom.xml` hoặc thông báo IDE.

Nếu runtime cũ hơn class-file major version, JVM có thể báo:

~~~text
java.lang.UnsupportedClassVersionError
~~~

Thông báo thường kèm hai con số class-file version mà class yêu cầu và runtime hỗ trợ tối đa. Giải pháp là sử dụng runtime đủ mới **hoặc** compile lại cho release được hỗ trợ, đồng thời sửa mọi API và dependency không tương thích.

**Tuy nhiên, major version phù hợp chỉ là điều kiện cần.** Bản build còn có thể không chạy vì:
- Gọi API Java SE/JDK mới hơn release target do chỉ dùng `-source/-target`.
- Dependency JAR có class-file major version mới hơn target.
- Phụ thuộc native library/JNI, module exports, thư viện bên thứ ba, service provider hoặc cấu hình runtime khác.
- Dùng preview feature với **minor 65535** cần runtime tương ứng cùng release và flags thích hợp; không được coi như bytecode ổn định cho JVM cũ.
- Chỉ kiểm tra một vài class; JAR còn class khác được biên dịch với target mới hơn.

Trong ứng dụng lớn, nên kiểm tra tất cả modules và dependencies cần thiết, không chỉ `Main.class`.

## 8. `--release` bảo đảm điều gì và không bảo đảm điều gì?

**Với API của Java SE/JDK:** `--release N` chọn quy tắc ngôn ngữ của release N, class-file target của N và các API nền tảng được hỗ trợ ở release N. Nó giúp bắt lỗi như `Thread.ofVirtual()` trong ví dụ Java 17 ngay lúc compile.

**Với thư viện bên thứ ba:** `--release N` không “hạ cấp” phiên bản bytecode hoặc API của JAR dependency. Một class của ứng dụng target 17 vẫn có thể gọi vào thư viện chỉ hoạt động trên Java 21 nếu build được cấu hình sai hoặc thiếu bước xác minh dependency. Cần dùng dependency version có tuyên bố hỗ trợ Java 17 và kiểm tra thực tế trên JDK 17.

**Với runtime behavior:** cùng một class 61 có thể chạy khác nhau giữa Java 17, 21 và 24 vì API implementations, defaults, môi trường, hệ điều hành hoặc thay đổi hành vi tương thích. Compatibility test vẫn cần thiết.

**Với preview features:** `--enable-preview` phải đi với mức source/release tương ứng **phiên bản JDK đang chạy compiler** theo quy tắc hỗ trợ của `javac`; không dùng JDK 24 để compile preview feature của Java 17 chỉ bằng `--release 17 --enable-preview`. Class chứa preview có ràng buộc runtime riêng. Nếu muốn phát hành thư viện rộng rãi, nên tránh phụ thuộc preview trừ khi yêu cầu của sản phẩm cho phép.

**Với API nội bộ:** `--release` được thiết kế để giới hạn API nền tảng công khai/hợp lệ theo release, không cho phép tùy tiện sử dụng API `jdk.internal.*` hoặc `com.sun.*` không được export. Những dự án dùng compiler internals cần tài liệu và build path riêng, không thể coi `--release` là công cụ hỗ trợ những API đó.

## 9. Cấu hình trong Maven

Với **Maven Compiler Plugin 3.6+** và JDK compiler hỗ trợ `--release`, trong `pom.xml` có thể khai báo:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đây là **một phần của POM đang có**, không phải POM độc lập. Thuộc tính `maven.compiler.release` yêu cầu plugin chuyển mức release cho compiler phù hợp. Nếu muốn đặt trực tiếp:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây cũng chỉ là **đoạn cấu hình bên trong `<project>`**, với version plugin được minh họa cụ thể; khi áp dụng, dùng version plugin đã được dự án kiểm định hoặc phiên bản phù hợp với build hiện tại.

Kiểm tra Maven chọn JDK nào:

~~~bash
mvn -version
mvn clean compile
~~~

`mvn -version` phản ánh JVM đang chạy Maven, còn Maven Toolchains Plugin/cấu hình compiler có thể chỉ định một JDK khác để gọi `javac`. Nếu dự án dùng toolchains, xem cấu hình toolchain và log compiler. Đừng tự kết luận JDK compiler chỉ từ `JAVA_HOME` nếu build có nhiều lớp chọn JDK.

Trong multi-module Maven, cần bảo đảm từng module phù hợp target của artifact cuối. Một module Java 17 dùng trực tiếp library module Java 21 sẽ không tự tương thích chỉ vì app đặt `maven.compiler.release=17`.

## 10. Cấu hình trong Gradle: toolchain và release là hai việc riêng

Trong Gradle, **Java toolchain** chọn JDK để compile; **`options.release`** quyết định Java release mà source/classes/API nền tảng được target. Có thể cấu hình **JDK 21 để compile nhưng target Java 17**.

Với Groovy DSL (`build.gradle`):

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

Với Kotlin DSL (`build.gradle.kts`):

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}
~~~

Hai đoạn là **cấu hình build độc lập cho dự án Gradle Java**, không phải mã Java. Điều kiện: Gradle và Java plugin phiên bản đang sử dụng hỗ trợ toolchain được chọn; JDK 21 phải có sẵn hoặc Gradle được cấu hình provisioning. Khi một processor/plugin cần JDK mới hơn, cần xét riêng khả năng chạy của các công cụ build.

Nếu chỉ viết:

~~~groovy
sourceCompatibility = '17'
targetCompatibility = '17'
~~~

thì chỉ thể hiện language/target compatibility theo cơ chế cũ, **không ràng buộc API** chặt như `options.release`; cũng không bảo đảm JDK compile là 17. Ưu tiên `options.release = 17` và toolchain tường minh khi cần cả tính tái lập và khả năng chạy trên bản Java đích.

Kiểm tra:

~~~bash
./gradlew --version
./gradlew clean compileJava
~~~

Trên Windows dùng `gradlew.bat`. `./gradlew --version` cho biết JVM của Gradle, không đủ xác minh compiler của task khi có toolchain; xem compile logs/config và class-file version thực tế.

## 11. Lựa chọn cấu hình theo mục tiêu

| Mục tiêu | Gợi ý | Vì sao |
| --- | --- | --- |
| Build bằng JDK 17, chạy trên Java 17 | JDK toolchain 17 + `--release 17` | Tái lập JDK compiler và kiểm soát syntax/class/API |
| Build bằng JDK 21, chạy Java 17 | Toolchain 21 + `--release 17` | Dùng compiler mới nhưng target nền tảng cũ |
| Build bằng JDK 24, chạy Java 21 | Toolchain 24 + `--release 21` | Source, bytecode, API theo Java 21 |
| Cần Java 21 language features | `--release 21` + runtime Java 21+ | Không thể dùng feature chuẩn Java 21 với target Java 17 |
| Dùng API Java 21 từ source kiểu Java 17 | **Không thể xem là Java 17 compatible** | Source syntax cũ không kéo API mới về release cũ |
| Dự án thư viện cần phân phối rộng | Chọn minimum runtime được hỗ trợ, compile `--release` tương ứng, test trên bản thấp nhất | Tránh đưa class/API mới vào artifact |

Toolchain JDK có thể cao hơn release đích, nhưng **không thể chọn `--release` cao hơn những release mà compiler hỗ trợ**. Chẳng hạn `javac 17` không biết các tính năng Java 21 và không thể `--release 21`; phải dùng compiler mới đủ khả năng.

## 12. Các lỗi thường gặp và cách nhận diện

### 12.1. `invalid source release` / `release version ... not supported`

Compiler JDK **quá cũ** hoặc release yêu cầu không được compiler hỗ trợ. Ví dụ gọi compiler JDK 17 với `--release 21` sẽ bị từ chối. Kiểm tra `javac -version`, `javac --help`, Maven/Gradle toolchain thực tế; nâng toolchain JDK phù hợp hoặc chọn release được hỗ trợ.

### 12.2. `UnsupportedClassVersionError`

JVM **quá cũ để nạp class file** (hoặc class preview có quy tắc đặc biệt). Kiểm tra major/minor bằng `javap -verbose`, runtime `java -version`, JAR trên runtime path và dependency nào thực sự được nạp.

### 12.3. `NoSuchMethodError` dù class target đúng

Ứng dụng hoặc library tham chiếu method không có trong runtime API/class thực tế. Nếu đã compile bằng `-source/-target` trên JDK mới, hãy kiểm tra việc **vô tình dùng API Java mới**. Ngoài ra, lỗi có thể do hai phiên bản thư viện bên thứ ba không nhất quán giữa compile và runtime classpaths; `--release` không sửa mismatch phiên bản thư viện.

### 12.4. Biên dịch được ở IDE nhưng CI không biên dịch

IDE và CI có thể chọn hai `javac`, hai Gradle/Maven JDK/toolchain hoặc hai `--release` khác nhau. Đọc log invocation và cấu hình build trong repository; chạy build sạch. Đừng chỉ sửa “Project language level” trong IDE mà bỏ mặc cấu hình build chính.

### 12.5. Preview feature dùng được lúc compile nhưng không chạy

Class preview có thể mang class-file minor 65535 và yêu cầu `--enable-preview` trên runtime cùng Java release tương ứng. Lệnh compile `--enable-preview` không biến preview thành API ổn định cho release cũ. Với build production có yêu cầu minimum runtime, quản lý preview như một phụ thuộc phiên bản rất chặt.

### 12.6. Class của thư viện quá mới

Artifact ứng dụng target Java 17 có thể kéo vào JAR từ thư viện compile Java 21. Khi runtime Java 17 nạp class của thư viện, nó có thể từ chối major 65. Kiểm tra yêu cầu minimum Java của từng dependency và class-file version; chọn bản library tương thích hoặc tăng minimum runtime.

## 13. Checklist xác minh build chạy thật trên Java đích

1. **Xác nhận compiler**: chạy `javac -version` hoặc xem compiler/toolchain trong log Maven/Gradle, tránh nhầm với runtime của build tool.
2. **Xác nhận cấu hình**: ưu tiên `--release N`; không trộn cùng `-source/-target`. Đặt `-encoding UTF-8` khi source lưu UTF-8.
3. **Compile từ trạng thái sạch**: tránh để class cũ biên dịch với target khác lọt vào artifact.
4. **Đọc bytecode**: `javap -verbose` trên class đại diện; kiểm tra các class quan trọng và dependency modules theo cần thiết.
5. **Xác nhận API**: kiểm tra compile không gọi API Java SE mới hơn release đích; xem cả library dependencies.
6. **Chạy bằng runtime đích thực**: ví dụ nếu hỗ trợ Java 17, phải có một test job chạy `java` 17, không chỉ chạy bằng JDK 24.
7. **Kiểm tra dependency/classpath/module path**: các JAR cần có phiên bản và minimum Java phù hợp; không chỉ class của module chính.
8. **Chạy integration tests**: serialization, reflection, service loading, network, security provider và native dependencies có thể phát lộ khác biệt runtime.
9. **Cố định CI và toolchains**: ghi JDK vendor/version, build plugin version, `--release` và môi trường test để các lần build có thể lặp lại.
10. **Kiểm tra artifact cuối**: class bên trong fat JAR, module JAR, distribution hoặc container image mới là thứ được triển khai; tránh nhầm với output trung gian.

## 14. Tự kiểm tra hiểu biết

**Câu 1.** Dùng `javac 24` với `--release 17` thì bytecode mang major nào?  
**Đáp án:** **61**, tương ứng class file Java 17; compiler vẫn là JDK 24.

**Câu 2.** Có thể `javac 17 --release 21` không?  
**Đáp án:** **Không.** Compiler JDK 17 không hỗ trợ release Java 21.

**Câu 3.** Vì sao `-source 17 -target 17` có thể tạo ứng dụng không chạy được trên JVM 17?  
**Đáp án:** Hai tùy chọn này không tự giới hạn API chuẩn của JDK đang compile; code có thể tham chiếu API mới hơn Java 17.

**Câu 4.** Cách ưu tiên để compiler mới kiểm tra syntax, bytecode và API Java 17 cùng lúc?  
**Đáp án:** `--release 17`, nếu compiler hỗ trợ release đó.

**Câu 5.** Dùng `javap` thấy `major version: 61` có đủ chứng minh ứng dụng hoàn toàn tương thích Java 17 không?  
**Đáp án:** **Chưa.** Cần xét API, dependencies, preview features và chạy test trên Java 17.

**Câu 6.** `source=21, target=17` có phải cách backport Java 21 thành Java 17?  
**Đáp án:** **Không.** `javac` từ chối target thấp hơn source.

**Câu 7.** Gradle toolchain JDK 21 và `options.release = 17` có mâu thuẫn không?  
**Đáp án:** **Không.** Toolchain chọn compiler; release chọn nền tảng ngôn ngữ/bytecode/API mục tiêu.

**Câu 8.** Ứng dụng class 61 nhưng dependency class 65, có thể triển khai nguyên bộ trên Java 17?  
**Đáp án:** **Không thể bảo đảm**; khi cần nạp class 65, JVM 17 không hỗ trợ định dạng đó. Chọn dependency phù hợp hoặc đổi minimum runtime.

## 15. Tài liệu chính thức

- [Oracle javac command — `--release`, `--source`, `--target`](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [JVMS 17, §4.1 — ClassFile structure và major version](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1)
- [Maven Compiler Plugin — Setting `--release`](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Gradle Java toolchains](https://docs.gradle.org/current/userguide/toolchains.html)

**Ghi nhớ:** **JDK công cụ** là compiler nào được chạy; **source level** là cú pháp nào được viết; **target level** là class file dành cho JVM đời nào. Muốn build thực sự cho Java N, hãy kiểm soát thêm **API nền tảng** bằng `--release N`, kiểm tra libraries và chạy test trên **runtime Java N thật**.
