# Maven: Cấu hình phiên bản Java bằng `maven.compiler.release`

> **Build Tool Maven · Biên dịch và JDK**  
> Bài thực hành dành cho Maven 3.x, **JDK 17+**, và Maven Compiler Plugin **3.14.1**. Phần lưu ý về JDK 8 và Maven 4 được phân biệt rõ khi cần.

## 1. Mục tiêu của `maven.compiler.release`

Trong dự án Java dùng Maven, ta thường cần trả lời ba câu hỏi:

1. Mã nguồn được phép sử dụng **cú pháp Java phiên bản nào**?
2. File `.class` tạo ra có thể được **JVM phiên bản nào đọc**?
3. Mã được phép gọi **những API chuẩn Java SE có từ phiên bản nào**?

Cấu hình:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

giải quyết cả ba câu hỏi **ở bước biên dịch bằng `javac` có hỗ trợ `--release`**. Maven Compiler Plugin lấy giá trị của property `maven.compiler.release` để cấu hình tham số `--release 17` cho Java compiler. Khi đó:

- Ngôn ngữ Java bị giới hạn theo **source level 17**.
- Bytecode được tạo cho **class-file format của Java 17**.
- Các **API Java SE công khai** mà compiler cho phép tham chiếu được giới hạn theo Java 17 (không vô tình dùng API Java 21 khi target Java 17).

**Điểm cần phân biệt:** `maven.compiler.release=17` không có nghĩa Maven **tự cài hoặc tự chọn JDK 17**. Nếu máy dùng JDK 21 hỗ trợ target release 17, Maven có thể biên dịch cho Java 17 bằng JDK 21. Nếu trình biên dịch chỉ là JDK 11, nó không thể biên dịch cho một release **tương lai** như 17. Khi cần chọn chính xác JDK thực thi compiler, phải kiểm soát `JAVA_HOME`, CI image hoặc **Maven Toolchains**.

Lệnh kiểm tra đầu tiên trên mọi máy:

```bash
java -version
javac -version
mvn -version
```

Trong đó `mvn -version` thường báo JVM mà **Maven đang chạy**; nếu compiler được chọn bằng toolchain hoặc fork riêng, JDK thực sự dùng cho bước compile có thể **khác**.

### Kết quả cần đạt sau bài

- Viết được POM Java 17 hợp lệ với `maven.compiler.release`.
- Phân biệt `release` với `source`/`target` và version của Maven/JDK.
- Chạy được project mẫu và xác minh class file có `major version: 61` cho Java 17.
- Hiểu vì sao `--release 8` từ JDK 17 có thể từ chối `List.of`, dù `-source 8 -target 8` vẫn có thể biên dịch code đó.
- Xử lý các lỗi `release version ... not supported`, `UnsupportedClassVersionError`, thiếu API và IDE/CI dùng sai JDK.
- Biết cách đặt property ở parent multi-module và khi nào cần Toolchains.

## 2. Maven Compiler Plugin đứng ở đâu trong build?

Maven có **lifecycle phases** như `validate`, `compile`, `test-compile`, `test`, `package`, `verify`. Với project `packaging=jar`, Maven có default lifecycle bindings để gọi Compiler Plugin vào những phases biên dịch phù hợp:

- **`compiler:compile`**: biên dịch mã chính trong `src/main/java` sang `target/classes`.
- **`compiler:testCompile`**: biên dịch mã test trong `src/test/java` sang `target/test-classes` (với test classpath).

Khi chạy:

```bash
mvn clean compile
```

Maven chạy các phases tới `compile` của default lifecycle sau khi clean. Compiler Plugin nhận các tham số cấu hình. Property `maven.compiler.release` được ánh xạ tới tham số **`release`** của compiler goal; nó không phải property của Java runtime hay flag trực tiếp cho chương trình ứng dụng.

Một POM chuẩn nên **ghim phiên bản Maven Compiler Plugin**. Không nên chỉ dựa vào plugin version mặc định/ngẫu nhiên của Maven distribution hay parent POM để kỳ vọng mọi máy hiểu `release` giống nhau.

### 2.1. Đặt property gọn ở mức POM

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Đây là **fragment** đặt trong `<project>`. Nó chỉ phát huy tác dụng khi Maven Compiler Plugin được thực thi với version hỗ trợ property. Từ Maven Compiler Plugin **3.6**, tham số `release` và property `maven.compiler.release` được hỗ trợ; ở các version mới có thêm xử lý tương thích cho JDK 8.

### 2.2. Đặt trực tiếp trong plugin

Một cách tương đương về ý nghĩa:

```xml
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
```

Đây cũng là fragment POM, chưa phải file độc lập.

**Nên chọn cách nào?** Với dự án chỉ dùng một target Java chung, property `<maven.compiler.release>17</maven.compiler.release>` dễ đọc, dễ kế thừa ở parent và dễ điều chỉnh qua Maven user property. Với nhu cầu cấu hình phức tạp theo executions hoặc toolchain, block `<configuration>` có thể phù hợp.

**Tránh cấu hình mâu thuẫn:** đừng đặt property `maven.compiler.release=17` ở một nơi nhưng `<release>11</release>` hoặc `source`/`target` khác ở nơi khác rồi đoán kết quả. Khi plugin configuration chỉ định giá trị tường minh, Maven có các quy tắc property interpolation và parameter injection riêng; hãy xem effective POM và log compiler thay vì tự giả định một thứ tự override chung.

## 3. Vì sao `--release` tốt hơn chỉ `-source` và `-target`?

Trước Java 9, lập trình viên thường dùng hai cờ `javac`:

- `-source N`: giới hạn cú pháp/ngôn ngữ ở mức N.
- `-target N`: chọn **định dạng bytecode** thích hợp với phiên bản JVM mục tiêu.

Nhưng hai cờ này **không tự hạn chế tập API của JDK hiện tại**. Bạn có thể compile bằng JDK 17 với `-source 8 -target 8`, vô tình gọi một method chỉ mới xuất hiện ở Java 9+, rồi chạy trên JVM 8 bị lỗi liên kết method/class.

`javac --release N` (bắt đầu từ **JDK 9**) đồng thời đặt **ngôn ngữ, bytecode và tập Java SE platform APIs** theo release N. Nó thay thế cách phải tự cấu hình bootclasspath/system path để compile ngược về Java cũ trong nhiều trường hợp.

| Khía cạnh | `-source 8` | `-target 8` | `--release 8` khi dùng JDK mới hỗ trợ |
| --- | --- | --- | --- |
| Giới hạn cú pháp Java | Có | Không trực tiếp | **Có** |
| Tạo class file phù hợp Java 8 | Không phải vai trò chính | **Có** | **Có** |
| Ngăn sử dụng Java SE API chỉ có từ Java 9+ | **Không tự đảm bảo** | **Không** | **Có** |
| Có nghĩa là compiler đang chạy trên JDK 8 | Không | Không | **Không** |
| Có nghĩa third-party libraries tự động tương thích Java 8 | Không | Không | **Không** |

Với Maven Compiler Plugin, cấu hình legacy:

```xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
</properties>
```

không mang bảo đảm API như:

```xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
```

Trên JDK 9+ hỗ trợ release 8, cách thứ hai được khuyến nghị. Apache Maven Compiler Plugin cũng khuyến nghị dùng `maven.compiler.release` thay cho cấu hình chỉ có `source`/`target` với plugin version mới.

### 3.1. Thí nghiệm độc lập: Java 8 cú pháp, nhưng API Java 9

Tạo thư mục thử nghiệm **riêng** (không cần Maven) và file `ApiProbe.java`:

```java
import java.util.List;

public final class ApiProbe {
    private ApiProbe() {
    }

    public static void main(String[] args) {
        System.out.println(List.of("a", "b").size());
    }
}
```

Đây là Java source dùng cú pháp Java 8-compatible, nhưng gọi `List.of` — API **chỉ có từ Java 9**. Khi dùng **JDK 17**:

```bash
javac -source 8 -target 8 ApiProbe.java
java ApiProbe
```

Thông thường `javac` có thể biên dịch mã này (có thể có warning về bootstrap class path/system modules path), bởi vì bộ API được thấy vẫn là từ JDK 17. Chạy trên JDK 17, stdout:

```text
2
```

Nhưng class file của bản build `-target 8` chỉ có **định dạng** Java 8; nếu chạy trên JVM 8, `java.util.List` không có static method `of`, nên khi thực thi lời gọi đó sẽ gặp lỗi kiểu `NoSuchMethodError`. Kết quả trên JVM 17 **không chứng minh** ứng dụng chạy được trên JVM 8.

Bây giờ thử **độc lập**, vẫn dùng JDK 17:

```bash
javac --release 8 ApiProbe.java
```

Lần này compiler phải **từ chối sử dụng `List.of`** vì API đó không thuộc Java 8. Có thể gặp thông báo dạng:

```text
error: cannot find symbol
    symbol:   method of(java.lang.String,java.lang.String)
    location: interface java.util.List
```

Đây là **trích dạng thông báo** thay vì bản cam kết từng dấu/khoảng trắng của `javac`; cách trình bày khác nhau theo JDK. Thí nghiệm cho thấy `--release` phát hiện vấn đề **ngay lúc compile** thay vì để ứng dụng lỗi khi triển khai trên JVM cũ.

**Không nhầm với dependency từ Maven Central:** `--release` kiểm soát **Java SE platform API** và compiler target, không xác minh version bytecode/API của mọi thư viện bên thứ ba. Nếu dependency được compile cho Java 21 nhưng bạn đang dùng compiler/JDK 17, vẫn có thể gặp lỗi class-file version incompatibility khi đọc JAR đó.

## 4. Các con số release và class-file version

Một số mốc thông dụng:

| Java release | Cấu hình property | Class-file major version |
| --- | --- | --- |
| Java 8 | `<maven.compiler.release>8</maven.compiler.release>` | **52** |
| Java 11 | `<maven.compiler.release>11</maven.compiler.release>` | **55** |
| Java 17 | `<maven.compiler.release>17</maven.compiler.release>` | **61** |
| Java 21 | `<maven.compiler.release>21</maven.compiler.release>` | **65** |

**Release number** là con số `8`, `11`, `17`, `21`, **không** viết `1.17`. Định dạng version như `1.8` thường thấy ở cấu hình Java cũ không nên mang sang `--release 17` thành `1.17`.

**Không phải mọi bản `javac` đều hỗ trợ mọi release lịch sử.** Một compiler JDK mới chỉ hỗ trợ một tập target xác định và có thể bỏ các release quá cũ. Compiler JDK 11 không thể target 17; JDK 17 không thể target 21. Để kiểm tra target nào được hỗ trợ, tham khảo `javac --help` của JDK thực sự dùng:

```bash
javac --help
```

Dòng `--release` liệt kê các phiên bản khả dụng trong JDK. Nếu đang dùng Maven Toolchains, `javac` trên shell có thể **không phải** compiler mà plugin đã chọn; cần kiểm tra toolchain/configuration.

## 5. Ví dụ Maven + Java 17 hoàn chỉnh, chạy được

Mục tiêu thực hành:

- Tạo project `release-configuration-demo` dùng Java 17.
- Chỉ định `maven.compiler.release=17` trong POM, ghim Compiler Plugin `3.14.1`.
- Dùng **Java record** (ngôn ngữ chuẩn từ Java 16) và `String.isBlank()` (Java 11+) trong source. Hai tính năng đều hợp lệ với target Java 17.
- Build bằng Maven, chạy trực tiếp class (không cần third-party JAR), kiểm tra bytecode major version **61**.
- Cố tình thử target 11 để hiểu compile error khi source dùng record.

### 5.1. Cấu trúc thư mục

```text
release-configuration-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── Main.java
```

Cần JDK 17+ với compiler thích hợp, Maven 3.x, và quyền truy cập remote repository nếu máy chưa có plugin Maven trong cache. Không cần test dependencies.

### 5.2. POM đầy đủ

Tạo file `release-configuration-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>release-configuration-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Vì sao đủ?**

- `<modelVersion>4.0.0</modelVersion>` xác định mô hình Maven POM hiện hành.
- `<packaging>jar</packaging>` chọn lifecycle mặc định cho JAR.
- `<maven.compiler.release>17</maven.compiler.release>` yêu cầu compiler target Java 17.
- `<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>` giúp xử lý source text thống nhất, không thay thế tính năng `--release`.
- Compiler Plugin version `3.14.1` hỗ trợ property `maven.compiler.release`.
- Không cần chỉ định thêm `<maven.compiler.source>` hoặc `<maven.compiler.target>` trong bài mẫu; `release` đã cung cấp ba ràng buộc cần thiết.

### 5.3. Java class hoàn chỉnh

Tạo file `release-configuration-demo/src/main/java/org/example/Main.java`:

```java
package org.example;

public final class Main {
    private Main() {
    }

    private record BuildInfo(String tool, int javaRelease) {
    }

    public static void main(String[] args) {
        BuildInfo info = new BuildInfo("Maven", 17);
        String spaces = "   ";

        System.out.println(info.tool()
                + " targets Java " + info.javaRelease());
        System.out.println("blank=" + spaces.isBlank());
    }
}
```

Đây là mã **Java 17 hợp lệ**, dùng nested record `BuildInfo` và `String.isBlank`. Nested record được xem là nested static member, nên có thể sử dụng trực tiếp bên trong static `main`.

**Giải thích class:**

- Tên class `Main` khớp tên file `Main.java`.
- Package `org.example` khớp thư mục `org/example`.
- `BuildInfo` là một record có accessor `tool()` và `javaRelease()`.
- `String.isBlank()` trả `true` cho chuỗi chỉ chứa khoảng trắng.
- Không có `Math.random`, thời gian, locale hay I/O file ngoài, nên output có thể so sánh chính xác.

### 5.4. Biên dịch và chạy

Tại thư mục `release-configuration-demo`:

```bash
java -version
javac -version
mvn -version
mvn clean compile
java -cp target/classes org.example.Main
```

Stdout **chính xác của lệnh Java cuối cùng**:

```text
Maven targets Java 17
blank=true
```

Lệnh `mvn clean compile` có nhiều Maven log, không phải chỉ hai dòng trên. Hai dòng là output do chương trình Java viết ra, không tính Maven log.

**Vì sao có thể dùng `java -cp target/classes` ở đây?** `Main` chỉ phụ thuộc JDK classes và chính class nested record đã được compiler tạo trong `target/classes`; không có JAR bên thứ ba. Nếu project thật có external dependencies, phải bổ sung runtime classpath hoặc dùng Maven Exec Plugin/packaging phù hợp.

### 5.5. Kiểm tra class-file major version

Sau khi biên dịch:

```bash
javap -verbose -classpath target/classes org.example.Main
```

Tìm dòng:

```text
major version: 61
```

Đây là dấu hiệu bytecode của **Java 17**. `javap` là công cụ đi cùng JDK, không phải Maven plugin. Nó đọc class file đã tạo; kiểm tra này tốt hơn việc chỉ suy đoán từ POM, đặc biệt khi dự án có parent/profile/plugin configuration phức tạp.

Bạn cũng có thể kiểm tra nested record:

```bash
javap -verbose -classpath target/classes 'org.example.Main$BuildInfo'
```

Lệnh quote `'...'` ở trên phù hợp với nhiều shell Unix, nhưng cách quote tên class chứa `$` **khác trên Windows PowerShell/cmd**; dùng đường dẫn class file trong `target/classes` khi cần hoặc quote theo shell. Để tránh khác biệt, chỉ cần kiểm tra `org.example.Main` ở lệnh đầu tiên là đủ cho kết luận về target compiler của ví dụ.

**Lưu ý quan trọng:** bytecode major version **chỉ xác nhận format**. Nó không tự chứng minh API Java SE mới hơn chưa được gọi; chính `--release` giúp compiler kiểm soát API trong quá trình build. Ngoài ra, major version không chứng nhận các dependencies runtime có bytecode tương thích.

### 5.6. Đóng gói JAR

```bash
mvn clean package
jar tf target/release-configuration-demo-1.0.0.jar
```

JAR sẽ chứa `org/example/Main.class` và class file của `BuildInfo` cùng metadata manifest. Tuy nhiên, POM mẫu **không cấu hình `Main-Class`**, nên **không** hứa rằng:

```bash
java -jar target/release-configuration-demo-1.0.0.jar
```

sẽ chạy chương trình: `java -jar` cần manifest phù hợp. Dùng `java -cp target/classes org.example.Main` là cách đơn giản, chính xác cho bài này.

## 6. Thực nghiệm đổi release và quan sát lỗi

Từ project mẫu với Java record ở mục 5, thử **tạm override property** mà không sửa POM:

```bash
mvn clean compile -Dmaven.compiler.release=11
```

Với Compiler Plugin đọc user property này, compiler phải **từ chối source có `record`**, vì record là tính năng ngôn ngữ mới hơn Java 11. Lỗi có thể có dạng:

```text
records are not supported in -source 11
(use -source 16 or higher to enable records)
```

Block chỉ minh họa **thông điệp chính**; dòng lỗi, vị trí và cách format phụ thuộc JDK/plugin. Build thất bại **đúng ý đồ**. Sau đó khôi phục lệnh:

```bash
mvn clean compile
```

để target trở lại Java 17 theo POM.

### 6.1. Dùng release lớn hơn JDK compiler

Nếu **javac 17** đang được dùng, chạy:

```bash
mvn clean compile -Dmaven.compiler.release=21
```

sẽ không thể target Java 21 bằng compiler JDK 17. Một lỗi thường gặp:

```text
error: release version 21 not supported
```

Đây là lỗi về **năng lực compiler**, không phải lỗi code của `Main`. Muốn build Java 21, cần **compiler JDK 21+ hỗ trợ target 21**, sau đó thiết lập Maven/JDK toolchain tương ứng. Chỉ sửa POM `release=21` không cài compiler mới.

### 6.2. Chạy bytecode Java 17 trên JVM quá cũ

Nếu file `Main.class` có major version 61 nhưng chạy bằng JVM Java 11 (hỗ trợ tối đa major 55), quá trình nạp class sẽ thất bại với dạng lỗi:

```text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
```

Đây là **dạng lỗi điển hình**; đừng so từng chữ của stacktrace. Giải pháp không phải đổi `java -version` hiển thị trong IDE một cách hình thức. Hãy:

1. Xác định **JDK/JRE thật sự chạy ứng dụng**.
2. Quyết định runtime tối thiểu dự án cam kết hỗ trợ.
3. Dùng compiler với `maven.compiler.release` không lớn hơn runtime mục tiêu.
4. Nếu code dùng API/ngôn ngữ mới, sửa code hoặc nâng runtime; không ép compiler tạo bytecode thấp hơn bằng flag mâu thuẫn.

### 6.3. Release 17 có dùng được trên JDK 21?

Có, **nếu javac JDK 21 hỗ trợ `--release 17`**, nó có thể biên dịch Java source theo Java 17 platform API và tạo major 61. `mvn -version` có thể in JVM 21, trong khi output vẫn nhắm Java 17.

Điều này là ví dụ của **cross-compilation** (*biên dịch cho release khác với JDK đang chạy*), không phải Maven đã đổi JVM của process thành 17.

### 6.4. Cẩn trọng khi thử nghiệm override trên project thật

Trong demo, property nằm ở cấp POM và plugin không có `<release>` tường minh khác. Vì thế việc truyền `-Dmaven.compiler.release=11` hoặc `=21` giúp minh họa user property.

Với dự án thật có parent inheritance, profiles, plugin executions, system properties hoặc `<configuration><release>...</release></configuration>`, đừng tự tin rằng một flag CLI luôn thắng mọi cấu hình. Hãy đọc effective POM và kiểm tra class file thực tế sau `clean compile`.

## 7. `maven.compiler.release` không cài JDK và không đổi runtime

Một lỗi phổ biến là đặt:

```xml
<maven.compiler.release>17</maven.compiler.release>
```

rồi kết luận “mọi developer đều đang dùng JDK 17”. Điều đó **sai**. Property chỉ chọn target Java release **khi Maven Compiler Plugin được gọi**.

Bốn thực thể khác nhau:

| Thực thể | Quyết định bởi | Kiểm tra |
| --- | --- | --- |
| Java runtime chạy Maven | Thường là `JAVA_HOME`, PATH, launcher Maven | `mvn -version` |
| Java compiler dùng cho project | JDK chạy Maven, Toolchains, `fork`/`executable`, plugin config | Compiler/plugin log, toolchain selection |
| Java release của bytecode/API | `maven.compiler.release` / Compiler Plugin `<release>` | `javap -verbose`, kiểm tra compiler flags |
| Java runtime chạy ứng dụng/tests | Lệnh `java`, container, CI runner, Surefire/Failsafe JDK config | `java -version`, test runtime logs |

### 7.1. `JAVA_HOME` và `PATH`

Trên Linux/macOS, khi Maven cần Java từ một đường dẫn xác định, thường cấu hình `JAVA_HOME` là **thư mục gốc JDK**, không phải `.../bin/java`. Trên Windows, Maven script/IDE có thể chọn JDK từ biến môi trường hoặc cấu hình toolchain.

Để kiểm tra, dùng:

```bash
mvn -version
java -version
javac -version
```

Nếu ba lệnh báo phiên bản khác nhau, cần xem lại cách khởi chạy Maven/IDE và `JAVA_HOME`/PATH. Nhưng ngay cả khi cùng version, **Maven Toolchains** hoặc plugin compiler `executable` vẫn có thể chọn compiler khác.

### 7.2. Maven Wrapper không thay thế JDK setup

Maven Wrapper (`mvnw`) giúp nhóm chuẩn hóa **Maven distribution/version** được dùng. Nó **không mặc nhiên cài JDK 17** hoặc bảo đảm OS/CI đã cung cấp `javac` target phù hợp.

Một pipeline ổn định cần chỉ rõ:

- JDK distribution/version trong CI runner, hoặc Maven Toolchains.
- Maven version (Wrapper hoặc image chuẩn).
- Maven Compiler Plugin version.
- `maven.compiler.release` là hợp đồng target.
- Runtime version cho ứng dụng và tests.

### 7.3. IDE có thể biên dịch khác Maven

IDE thường có lựa chọn riêng cho **Project SDK**, **language level**, **bytecode target** và **Maven runner JDK**. Nếu IDE chạy được nhưng `mvn clean compile` lỗi, hoặc ngược lại, hãy xem Maven importer/runner JDK, `JAVA_HOME`, effective POM và compiler log.

**Lấy Maven CLI trên CI làm đường kiểm chứng cuối** cho artifact Maven, không chỉ dựa vào nút Run trong IDE.

## 8. Khi cần đúng JDK: Maven Toolchains

`maven.compiler.release` quy định **target**; Maven Toolchains có thể chọn **JDK compiler cụ thể** độc lập với JDK đang chạy Maven. Đây là giải pháp tốt cho dự án có chính sách “compile bằng JDK 17” ngay cả khi Maven được chạy trên một JDK khác.

### 8.1. Ý tưởng của Toolchains

Maven Toolchains kết hợp:

1. File **`toolchains.xml`** trên máy build để mô tả JDK installations có sẵn.
2. Maven Toolchains Plugin hoặc cấu hình compiler plugin để yêu cầu một JDK có properties phù hợp.
3. Các plugin **toolchain-aware** như Maven Compiler Plugin sẽ sử dụng JDK được chọn.

Một `toolchains.xml` **minh họa** (đường dẫn JDK phải tồn tại thật trên máy):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Thông thường file ở `~/.m2/toolchains.xml`. Trên Windows, `jdkHome` là đường dẫn native hợp lệ tới JDK, không phải `/opt/jdk-17`. Đường dẫn `/opt/jdk-17` trong ví dụ chỉ đúng **nếu đó là JDK17 thực tế** trên Linux/macOS; không copy nguyên vào môi trường khác.

### 8.2. Chọn toolchain trực tiếp trong Compiler Plugin

**Fragment** plugin để dùng với POM có `maven.compiler.release=17`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

Maven Compiler Plugin hỗ trợ `jdkToolchain` và sẽ tìm JDK đáp ứng khai báo từ toolchains. **Đừng dùng đoạn này nếu bạn chưa định nghĩa JDK thích hợp trên máy** — sẽ không tự tải hoặc cài JDK.

**Lưu ý matching version:** Toolchains có thể nhận diện version là `17`, `17.0.x` hoặc theo format khác; yêu cầu version exact `17` có thể **không** match entry lưu `17.0.12`. Tài liệu Maven khuyên dùng version range phù hợp khi cần chấp nhận cả patch releases, ví dụ `[17,18)` trong cấu hình yêu cầu.

### 8.3. Toolchains Plugin dùng chung cho nhiều plugin

Khi muốn compiler, Javadoc và một số goals tương thích cùng nhìn thấy selected JDK, có thể sử dụng `maven-toolchains-plugin` và profile/toolchain configuration của project. Dưới đây là **fragment ý tưởng** dùng một toolchain duy nhất:

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
                <version>[17,18)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

Trong Maven Toolchains Plugin, goal `toolchain` có default lifecycle binding ở `validate` phù hợp bản plugin được mô tả; Maven sau đó để các toolchain-aware plugins lấy toolchain từ session. Khi sử dụng, cần đối chiếu Maven Toolchains Plugin/version và file toolchains thực tế.

**Quan trọng:** Toolchains chỉ ảnh hưởng **những plugins hỗ trợ Toolchains**. Không phải mọi plugin hay lệnh Java shell tự động chuyển sang JDK17 vì một toolchain đã được chọn. Chạy unit tests/runtime trong CI trên phiên bản Java mong muốn là việc riêng.

## 9. Java 8 và Maven Compiler Plugin 3.13.0+ có một ngoại lệ quan trọng

`javac --release` chỉ xuất hiện từ **JDK 9**. JDK 8 **không hiểu** option `--release`. Nhưng Apache Maven Compiler Plugin từ **3.13.0** có xử lý đặc biệt:

- Khi chạy compiler `javac` trên **JDK 9+**, `maven.compiler.release=8` được truyền tương ứng với `--release 8` (nếu target 8 còn được hỗ trợ).
- Khi chạy compiler `javac` trên **JDK 8** với plugin version **3.13.0+**, plugin có thể **chuyển `release=8` thành `source=8`/`target=8`** để tương thích vì JDK 8 không hỗ trợ `--release`.
- Cách chuyển này **không phải** `javac 8` bỗng hỗ trợ `--release`. Nó không làm JDK8 compiler có thể biên dịch Java 17 hay truy cập API Java17.
- Với plugin **cũ hơn 3.13.0** hoặc compilerId khác `javac`, cần xử lý theo tài liệu/plugin version riêng, có thể dùng profile điều kiện theo JDK.

Điều này giải thích vì sao một POM dùng:

```xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
```

có thể biên dịch bằng **JDK 8 hoặc JDK 17** (với Maven Compiler Plugin 3.14.1 hỗ trợ). Trên JDK8, compiler dùng API JDK8 gốc và `source`/`target` tương ứng; trên JDK17, `--release 8` giới hạn Java SE API. **Hãy kiểm tra compiler version thật**, không chỉ đọc tên property.

### 9.1. Câu hỏi thường gặp: đặt release 17 khi Maven chạy JDK 8?

Không hợp lệ với compiler JDK8. Dù plugin mới có compatibility fallback, `javac 8` **không có khả năng biên dịch cú pháp/API/target 17**. Bạn cần một **JDK compiler 17+**. Plugin không tự tạo năng lực của compiler.

### 9.2. Target release quá cũ trên JDK quá mới

Nếu compiler mới không còn hỗ trợ Java release cổ điển, `--release N` có thể báo target N không được hỗ trợ. Hãy dùng compiler/toolchain phù hợp với phiên bản legacy, hoặc nâng mục tiêu runtime sau khi đánh giá tương thích. Không nên hack bootclasspath/classfile bytecode bằng script không kiểm soát để “ép” tương thích.

## 10. Parent POM và multi-module: một release chung, nhu cầu khác nhau

Trong một reactor nhiều module, parent POM có thể quy định target Java chung:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Đây là **fragment** đặt trong parent POM phù hợp, không phải file POM hoàn chỉnh. Khi child có quan hệ `<parent>` hợp lệ, properties và plugin management được kế thừa theo model Maven, còn Compiler Plugin được áp dụng qua lifecycle/plugin declaration hiệu lực.

**Không nhầm aggregation với inheritance:** POM root liệt kê `<modules>` không đủ để mọi module tự nhận property `maven.compiler.release=17`; mỗi module cần quan hệ parent/management hoặc cấu hình riêng phù hợp.

Nếu một module thực sự phải target Java 11 còn các module khác target 17, có thể override:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
```

trong POM child **có Java source/API tương thích 11**. Không copy một module chứa Java record 17 sang module target11 rồi mong Maven tự chuyển đổi ngôn ngữ.

### 10.1. Một release chung không đồng nghĩa compatibility giữa mọi module

Giả sử `api` target Java 17, `service` target Java 11 nhưng `service` phụ thuộc `api`. Khi compiler đọc API bytecode Java17 (major61), compiler JDK11 không thể đọc class đó; ngay cả khi dùng JDK17 compiler target11, runtime Java11 cũng không đọc được JAR Java17. Cần thiết kế **đồ thị phụ thuộc nhất quán với runtime tối thiểu**.

Nếu có mô-đun Java 11 cần dùng một API nội bộ, thư viện cung cấp API nên được compile cho Java 11 hoặc thấp hơn, trừ khi API được tách/đóng gói theo mô hình tương thích khác. `maven.compiler.release` chỉ kiểm soát đầu ra **của module đang compile**, không tự rewrite classes trong dependencies.

### 10.2. Profile khác nhau có thể thay release

Ví dụ một profile CI có thể đặt `maven.compiler.release` khác local. Nhưng với team lớn, thay compiler target ngầm theo OS/JDK/file activation có thể khiến cùng commit tạo artifact không tương thích. Nên thống nhất target release làm cấu hình rõ ràng, versioned cùng code, và kiểm tra effective POM trong pipeline.

Chỉ dùng profile khác release nếu thực sự xây dựng/kiểm thử một **ma trận compatibility** và code hỗ trợ những releases được chọn.

### 10.3. Khác biệt giữa Compiler Plugin main và test

Maven Compiler Plugin có tham số `testRelease`, ánh xạ qua property:

```xml
<maven.compiler.testRelease>17</maven.compiler.testRelease>
```

Đây là property cho **`compiler:testCompile`**. Thông thường giữ main/test Java target nhất quán để giảm bất ngờ, nhưng có dự án muốn test source dùng JDK mới hơn main artifact. Khi đó phải đảm bảo **test compiler và test runtime** hỗ trợ mức mới, và xác nhận compiler/plugin settings không gây mâu thuẫn. Không nghĩ `testRelease` tự nâng JDK chạy Surefire/Failsafe.

## 11. `release` và các phần khác của hệ build

### 11.1. `maven.compiler.release` không quản lý Maven version

Maven core có version riêng (ví dụ Maven 3.9.x). Compiler Plugin có version riêng (ví dụ 3.14.1). Java compiler/JDK cũng có version riêng. Một project có thể dùng Maven 3.9.x + Compiler Plugin 3.14.1 + JDK 21 để target Java 17. Không gọi cả ba là “Maven Java version”.

### 11.2. `release` không đặt dependency versions

Property này không chọn Java compatibility của third-party artifacts. Một JAR được phát hành với class file major 65 (Java 21) **không thể** được sử dụng trực tiếp bởi Java 17 runtime chỉ vì project của bạn có `<maven.compiler.release>17</...>`.

Với dependencies, kiểm tra tài liệu minimum supported Java, versions đã dùng và chạy tests trên runtime mục tiêu. Khi cần, có thể dùng Maven Enforcer hoặc build-time bytecode checks bổ sung theo chính sách tổ chức.

### 11.3. `release` không quyết định Java runtime của tests

`maven-surefire-plugin`, `maven-failsafe-plugin` và `exec-maven-plugin` có cơ chế riêng để chọn JVM/classpath. Nếu compile ra class Java17 nhưng test runner chạy JDK11, tests có thể fail trước cả khi tới assertions. Cần kiểm tra thực tế `java.version` trong test JVM hoặc cấu hình JDK/toolchain của test plugin.

### 11.4. `release` không bảo đảm build tái lập tuyệt đối

Hai compiler khác nhau hỗ trợ cùng `--release 17` có thể có khác biệt chi tiết trong classfile, diagnostics hoặc annotation processing; dependency versions, plugin versions, OS, locale và timestamps cũng có thể làm artifacts khác. Property này là **một phần của hợp đồng compatibility**, không phải toàn bộ cơ chế reproducible builds.

### 11.5. Module system, internal JDK APIs và `--release`

Khi dùng `--release`, compiler giới hạn **documented platform APIs** cho release mục tiêu. Nó không cho dùng tùy tiện internal APIs của JDK khác hoặc mở module bằng các flags phá encapsulation trái với ràng buộc `--release`. Nếu project cần internal API, nên thay bằng API chuẩn hoặc tái thiết kế; không khuyến khích vô hiệu hóa kiểm tra release.

## 12. Chẩn đoán sai cấu hình

### 12.1. `error: release version 17 not supported`

**Khả năng:** Compiler thực tế là JDK11 hoặc cũ hơn, hoặc compiler khác không hỗ trợ target17.

**Xử lý:**

1. Chạy `mvn -version` để xem Maven JVM.
2. Xem Compiler Plugin đang fork hay dùng `jdkToolchain`.
3. Kiểm tra `javac -version` của **đúng JDK** compiler.
4. Chọn compiler JDK17+ hoặc giảm release khi code/API thực sự hỗ trợ release thấp hơn.
5. Chạy `mvn clean compile` lại.

Đừng thay `maven.compiler.release=11` chỉ để build xanh khi code và runtime requirement là 17.

### 12.2. `invalid target release: 17`

Thường là phiên bản compiler/target không phù hợp. Nguyên nhân có thể là dự án dùng `-target` thay vì `--release`, plugin cũ, toolchain sai hoặc JDK thực tế cũ. Cách điều tra tương tự mục trên, nhưng cần xem **flags thực tế** chứ không suy luận theo tên lỗi.

### 12.3. `invalid flag: --release` trên JDK8

`javac 8` không biết `--release`. Với Compiler Plugin **3.13.0+** và default `javac` compilerId, `maven.compiler.release=8` được plugin chuyển tương thích sang `source`/`target` khi JDK8; plugin quá cũ hoặc compilerId khác có thể không có fallback.

Nếu project target17, **không có cách cấu hình nào khiến compiler JDK8 hiểu Java17**. Cần dùng JDK17+.

### 12.4. `records are not supported in -source 11`

Code đang dùng cú pháp từ Java phiên bản cao hơn target. Record được standardize ở Java 16, nên không có trong source level11. Phương án: giữ target17 nếu runtime cho phép; hoặc viết lại code bằng class thông thường/API tương thích 11 nếu cần hỗ trợ Java11.

### 12.5. `package ... does not exist` hoặc `cannot find symbol` khi target thấp

Có thể code dùng API Java SE mới mà release target chưa cung cấp (ví dụ `List.of` khi `release=8`). Đừng nhầm với lỗi dependency thiếu trên Maven Central. Kiểm tra package/class thuộc **JDK API hay third-party JAR** và lý do compiler không tìm thấy.

### 12.6. `UnsupportedClassVersionError` khi chạy

Class đã được compile cho Java mới hơn runtime. Dùng `javap -verbose` xem **major version** của class bị lỗi và đối chiếu JVM chạy thật. Có thể lỗi thuộc **dependency JAR**, không phải class của module bạn.

### 12.7. `NoSuchMethodError` trên runtime Java cũ

Nếu chỉ dùng `-source`/`-target` cũ nhưng compile với API JDK mới, class bytecode có thể có format cũ và vẫn gọi method không có trong runtime cũ. Thí nghiệm `List.of` ở phần 3 minh họa. Dùng `--release` phù hợp và kiểm thử trên runtime đích.

### 12.8. `--release` kết hợp `-source`/`-target` không hợp lệ

`javac` có giới hạn về việc kết hợp `--release` với `-source`/`-target` hoặc một số module/system options. Nếu POM có cả property `release` và những options thấp hơn, đừng mặc định compiler tự xử lý xung đột như mong muốn. Tốt nhất **chỉ dùng một chiến lược release rõ ràng**, bỏ cấu hình legacy trùng lặp, rồi xác minh output.

### 12.9. Maven CLI khác IntelliJ/Eclipse/VS Code

IDE có thể dùng JDK riêng để chạy Maven hoặc compiler nội bộ. Kiểm tra Maven runner JDK, project SDK, annotation processing, `JAVA_HOME`, PATH và bản POM effective. Chạy `mvn clean compile` bên ngoài IDE để cô lập nguyên nhân.

### 12.10. Test compile thành công nhưng chạy test lỗi

Có thể test source target thấp nhưng Surefire chạy trên JDK không tương thích, hoặc third-party test engine cần Java mới hơn. Cần kiểm tra runtime của process test, không chỉ `maven.compiler.testRelease`.

## 13. Quy trình debug có thể lặp lại

Chạy trong thư mục project:

```bash
mvn -version
java -version
javac -version
mvn help:effective-pom -Doutput=effective-pom.xml
mvn clean compile
javap -verbose -classpath target/classes org.example.Main
```

Nếu compile lỗi và cần thêm thông tin:

```bash
mvn -e clean compile
mvn -X clean compile
```

- `-e` hiển thị thông tin nguyên nhân/stacktrace sâu hơn.
- `-X` bật debug log Maven, có thể thấy thông tin compiler/plugin execution và toolchain. Log dài và có thể chứa thông tin nội bộ; **không chia sẻ công khai nếu chưa lọc dữ liệu nhạy cảm**.
- `effective-pom.xml` giúp tìm `<properties>`, compiler plugin version, `<configuration>` và inheritance sau profiles.
- `javap` kiểm tra kết quả bytecode **sau khi compile thành công**. Không đọc file từ build cũ: dùng `clean compile` để tránh artifact cache gây nhầm.

### 13.1. Đánh giá cấu hình trong CI

Một job CI tối thiểu nên cố định JDK và build phase:

```bash
mvn -B -V clean verify
```

`-B` bật batch mode; `-V` in Maven version trong log. Trước đó CI phải cung cấp đúng JDK; không có flag nào trong lệnh này tự cài Java17.

Ghi rõ trong cấu hình pipeline/README:

- Maven version (hoặc Maven Wrapper).
- Compiler Plugin version.
- `maven.compiler.release` hợp đồng runtime.
- JDK distribution/version trên CI.
- Maven Toolchain nếu dùng.
- Target runtime và các nhóm tests chạy bằng Java version nào.

### 13.2. Kiểm thử ma trận JDK

Nếu sản phẩm cần hỗ trợ runtime Java17, có thể xây/test bằng JDK17 và JDK21 **với cùng release17**, kết hợp một bước chạy test trên JDK17. Khi dùng JDK21 compiler target17, kết quả biên dịch nên được kiểm soát API Java17; nhưng tests chỉ chạy JDK21 không thay thế việc chạy trên JVM17.

Nếu sản phẩm cần hỗ trợ Java11, toàn bộ code/dependencies phải thực sự đáp ứng điều kiện đó. Không chỉ hạ `target=11` rồi tin bytecode/ API của third-party JAR cũng tự hạ theo.

## 14. Những ngộ nhận hay gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| `maven.compiler.release=17` tự cài JDK17 | Không, nó chỉ cấu hình target compiler |
| `mvn -version` báo Java21 thì không thể tạo Java17 class | Có thể dùng `--release 17` nếu compiler hỗ trợ |
| `java -version` trên terminal chắc chắn là compiler Maven dùng | Toolchains, fork hoặc IDE có thể chọn compiler khác |
| `source=8,target=8` luôn đảm bảo chạy được trên Java8 | Không, code có thể gọi API JDK9+ |
| `--release 8` chỉ thay tên của `-target 8` | Không, nó còn kiểm soát source level và Java SE API |
| `release=17` cho phép dùng API Java21 | Không trên compiler hỗ trợ `--release`; API public chỉ tới Java17 |
| `release=17` làm dependency Java21 chạy được trên Java17 | Không, third-party classfiles vẫn có mức riêng |
| Plugin version và Java version là một | Không, Maven, Compiler Plugin và JDK có version riêng |
| Ghim plugin version là đủ để chọn compiler JDK | Không, phải kiểm soát JAVA_HOME/Toolchains |
| `maven.compiler.release=17` luôn yêu cầu đúng JDK17 | Có thể compile với JDK mới hơn hỗ trợ `--release 17` |
| JDK11 có thể compile release17 nếu đổi POM | Không, compiler phải có khả năng target17 |
| JDK8 hiểu trực tiếp flag `--release 8` | Không; plugin mới có thể tự chuyển sang source/target |
| `maven.compiler.testRelease` tự chọn JVM chạy tests | Không, đó là tham số test compiler |
| JAR có bytecode major61 nghĩa chắc chắn dependencies runtime đều tương thích 17 | Không, kiểm tra dependencies và runtime |
| Đặt source, target và release trộn lẫn luôn an toàn | Có thể mâu thuẫn/không được javac chấp nhận |
| Root POM có modules là đủ để child kế thừa release | Child phải có inheritance/configuration phù hợp |
| IDE Build SUCCESS chứng minh Maven CI sử dụng cùng JDK | Không, runner JDK và compiler path có thể khác |
| Java11 runtime sẽ tự chạy class Java17 nếu code không dùng feature mới | Không, classfile major61 đã quá mới đối với JVM11 |
| Maven Wrapper đồng thời cố định Maven và Java | Wrapper chủ yếu cố định Maven distribution |
| `--release` làm artifact hoàn toàn reproducible | Chưa đủ: compiler, plugins, dependencies, timestamps... còn ảnh hưởng |

## 15. Tự kiểm tra kiến thức

**Câu 1.** Property nào của Maven Compiler Plugin đặt Java release?  
**Đáp án:** `maven.compiler.release`, ví dụ `<maven.compiler.release>17</maven.compiler.release>`.

**Câu 2.** `--release 17` bảo đảm ba điều gì khi compiler hỗ trợ?  
**Đáp án:** Ngôn ngữ ở mức Java17, class file target Java17 và chỉ sử dụng documented Java SE platform API của release17.

**Câu 3.** Đang dùng JDK21, đặt release17, classfile major version gì?  
**Đáp án:** **61**, nếu build thành công và compiler tuân theo target.

**Câu 4.** Tại sao `-source 8 -target 8` trên JDK17 có thể compile `List.of`?  
**Đáp án:** Source/target không tự giới hạn JDK APIs; `List.of` có trong JDK17 đang dùng để compile nhưng không có trong Java8 runtime.

**Câu 5.** Nếu chạy `javac --release 8 ApiProbe.java` có `List.of`, kỳ vọng gì?  
**Đáp án:** Lỗi compiler vì `List.of` không thuộc Java8 API.

**Câu 6.** Tại sao đổi `maven.compiler.release` thành 21 trên JDK17 compiler thất bại?  
**Đáp án:** JDK17 không hỗ trợ compile target release tương lai 21.

**Câu 7.** JDK8 có dùng `--release` không?  
**Đáp án:** `javac 8` không hỗ trợ. Compiler Plugin 3.13+ có thể chuyển `release=8` thành source/target khi dùng JDK8 mặc định.

**Câu 8.** Dùng `mvn -version` thấy Java21 thì có chắc `javac` thực thi là JDK21?  
**Đáp án:** Không nếu Toolchains/fork/executable chọn compiler khác.

**Câu 9.** Làm thế nào xác minh bytecode của ví dụ đúng Java17?  
**Đáp án:** `javap -verbose -classpath target/classes org.example.Main`, đọc `major version: 61`.

**Câu 10.** Root POM có `<modules>` nhưng child không có quan hệ parent. Child tự nhận `maven.compiler.release` không?  
**Đáp án:** Không do `<modules>` thuần; cần inheritance/configuration thực sự.

**Câu 11.** Main code target Java11, test code có thể biên dịch mức17 không?  
**Đáp án:** Có thể cấu hình `maven.compiler.testRelease` khi phù hợp, nhưng test compiler/runtime phải hỗ trợ17; không được hiểu là nâng runtime sản phẩm.

**Câu 12.** `release=17` có làm một dependency JAR compiled for Java21 chạy trên JVM17 không?  
**Đáp án:** Không. Dependency vẫn có classfile/API requirements riêng, cần chọn phiên bản tương thích.

**Câu 13.** Vì sao `UnsupportedClassVersionError` có thể đến từ thư viện ngoài dù module có `release=17`?  
**Đáp án:** Runtime còn phải nạp classes của dependencies; một JAR ngoài có major version cao hơn JVM.

**Câu 14.** Nếu Maven Compiler Plugin dùng cấu hình `<release>11</release>` riêng, nhưng parent property là17, có nên suy ra release cuối bằng cách đọc mỗi property?  
**Đáp án:** Không. Xem effective POM và compiler arguments; tránh mâu thuẫn trong thiết kế.

## 16. Checklist áp dụng vào dự án thật

- [ ] Biết runtime tối thiểu dự án cần hỗ trợ là Java bao nhiêu.
- [ ] Ghim Maven Compiler Plugin version tương thích.
- [ ] Chọn `<maven.compiler.release>N</maven.compiler.release>` khi dùng JDK/compiler hỗ trợ.
- [ ] Không giữ cấu hình `source`/`target` mâu thuẫn với `release`.
- [ ] Phân biệt JDK chạy Maven, JDK chạy compiler và JVM chạy ứng dụng/test.
- [ ] Dùng `mvn -version`, `javac -version` và toolchain/plugin log để xác định JDK thực.
- [ ] Compiler không cũ hơn target release, và phải hỗ trợ target đã chọn.
- [ ] Chạy `mvn clean compile`, sau đó dùng `javap` kiểm tra major version.
- [ ] Thử trên runtime mục tiêu, không chỉ runtime mới nhất đang cài.
- [ ] Biết `--release` ngăn gọi Java SE API mới hơn, nhưng không kiểm soát mọi third-party JAR.
- [ ] Nếu dùng multi-module, xác định property inheritance từ đúng parent.
- [ ] Nếu cần JDK cố định, cấu hình Maven Toolchains và JDK installations cho từng máy/CI.
- [ ] Đánh giá phiên bản main/test compiler khác nhau trước khi chỉnh `maven.compiler.testRelease`.
- [ ] Không coi Maven Wrapper là công cụ cài JDK.
- [ ] Cấu hình CI chạy `clean verify` và tests trên Java runtime được hỗ trợ.
- [ ] Khi thấy lỗi version, đọc đúng classfile/error/compiler JDK thay vì chỉ sửa số trong POM.
- [ ] Không tuyên bố artifact hoàn toàn reproducible chỉ vì có một thuộc tính `release`.

## 17. Nguồn chính thức

1. [Apache Maven Compiler Plugin — Setting the `--release` of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
2. [Apache Maven Compiler Plugin — Setting `-source` and `-target`](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-source-and-target.html)
3. [Apache Maven Compiler Plugin — `compiler:compile` parameters (`release` / `maven.compiler.release`)](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
4. [Apache Maven Compiler Plugin — `compiler:testCompile` parameters (`testRelease`)](https://maven.apache.org/plugins/maven-compiler-plugin/testCompile-mojo.html)
5. [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
6. [Apache Maven — Guide to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
7. [Oracle Java SE 17 — `javac` command documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
8. [Oracle Java SE 17 — `javap` command documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
9. [JEP 247 — Compile for Older Platform Versions (`--release`)](https://openjdk.org/jeps/247)
10. [Apache Maven — Introduction to the POM: Parent Inheritance](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)

**Thông điệp cuối bài:** `maven.compiler.release` là **hợp đồng phiên bản Java đầu ra** của Maven Compiler Plugin, không phải lệnh cài hoặc chuyển JDK. Với JDK 9+ thích hợp, `--release` mạnh hơn chỉ `source`/`target` vì kiểm soát **cú pháp, bytecode và Java SE platform API** cùng lúc. Hãy xác minh bằng `mvn -version`, biên dịch sạch và `javap`, rồi chạy tests trên đúng runtime mục tiêu.
