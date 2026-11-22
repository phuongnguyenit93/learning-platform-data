# Cấu hình trình biên dịch Java, mã hóa UTF-8 và tùy chọn -parameters trong Spring Boot

## 1. Ba quyết định khi biên dịch nguồn Java

Trong dự án Spring Boot, file Java trong `src/main/java` và `src/test/java` phải được **trình biên dịch Java (`javac`)** biến thành bytecode `.class` trước khi ứng dụng chạy. Cấu hình build quyết định JDK nào biên dịch, cách đọc ký tự nguồn và metadata nào được ghi vào `.class`. Ba mối quan tâm riêng biệt là:

1. **Phiên bản Java/compile target:** dùng JDK nào và ngôn ngữ/API Java nào được phép sử dụng (ví dụ Java 17). Maven dùng Maven Compiler Plugin; Gradle dùng task `JavaCompile` và Java toolchain.
2. **Mã hóa nguồn UTF-8:** trình biên dịch giải mã các byte của file `.java` thành ký tự theo charset nào. Cần thống nhất với cách editor lưu file.
3. **Tùy chọn `-parameters`:** yêu cầu `javac` ghi **tên tham số thật** của method/constructor vào class file để thư viện dùng Java reflection đọc tên đó lúc chạy.

Ba cấu hình không thay thế nhau: bật UTF-8 không làm tên tham số xuất hiện trong reflection; bật `-parameters` không quyết định JDK hay charset; chỉ chọn Java 17 cũng không luôn bảo đảm các build tool/máy có cùng hành vi.

| Cấu hình | Cờ/thuộc tính cốt lõi | Tác dụng | Nếu thiếu hoặc sai |
|---|---|---|---|
| Java compiler / target | `--release 17`, toolchain JDK 17, Maven `<release>` | Hạn chế cú pháp, bytecode và API theo Java release được chọn | Có thể compile bằng API không có trên runtime mục tiêu, hoặc compiler quá cũ báo lỗi |
| UTF-8 source | `javac -encoding UTF-8`; Maven `project.build.sourceEncoding` / `<encoding>`; Gradle `options.encoding` | Đọc đúng file Java chứa dấu tiếng Việt và ký tự Unicode | Lỗi unmappable character hoặc text bị biến dạng |
| Tên tham số runtime | `javac -parameters`; Maven `<parameters>true</parameters>`; Gradle compiler arg `-parameters` | Ghi tên tham số phương thức/constructor để reflection và Spring đọc | Reflection thường trả `arg0`, `arg1`; một số kiểu binding/injection theo tên thất bại |

**Chọn hướng cấu hình theo project thật:** Spring Boot có thể cung cấp mặc định hợp lý qua Maven parent hoặc Gradle plugin. Hãy xem thiết lập **đã có** trước khi thêm trùng lặp nhiều compiler flags.

## 2. Luồng từ nguồn đến class file

```text
IDE/Git lưu .java thành dãy byte (nên dùng UTF-8)
                       |
                       v
                Java compiler
  Chọn compiler JDK + --release + -encoding
                       |
                       +-- -parameters ?
                       |      Có  -> MethodParameters attribute
                       |      Không -> tên tham số có thể không có
                       v
              .class (bytecode)
                       |
                       v
     Spring Boot khởi động / Java reflection
      Java 17+ runtime hoặc runtime phù hợp
                       |
          Đọc method, tham số và annotation
```

Ví dụ file `UserController.java` có method `hello(String username)`:

- `-encoding UTF-8` ảnh hưởng việc compiler đọc ký tự Unicode trong file.
- `--release 17` (khi dùng javac hỗ trợ release này) giới hạn các API và đặc tính ngôn ngữ theo Java 17, và class file được sinh cho Java 17.
- `-parameters` làm tên `username` có thể được lấy từ `java.lang.reflect.Parameter.getName()` cùng `isNamePresent() == true`.

Lưu ý `-parameters` áp dụng cho **tên tham số của method và constructor** trong file `.class`; không phải tùy chọn đặt tên biến cục bộ, Java package, JSON field hay tên Spring bean.

## 3. Chọn JDK, source/target và --release cho Java 17+

Có hai khía cạnh hay bị nhầm:

- **Compiler đang chạy:** một tiến trình `javac` của JDK phiên bản nào, chẳng hạn JDK 17 hoặc JDK 21.
- **Release đích:** bytecode, cú pháp và API mà sản phẩm được phép sử dụng.

Với JDK từ Java 9, `javac --release 17` là cách phổ biến để giới hạn ngôn ngữ và Java platform API theo Java 17. Compiler phải đủ mới để hiểu release được yêu cầu. `--release` khác việc chỉ đặt `-source 17 -target 17`: source/target đặt mức ngôn ngữ và bytecode nhưng **không đảm bảo chặn dùng API JDK mới hơn** khi biên dịch bằng JDK mới.

Ví dụ dùng JDK 21 để tạo sản phẩm tương thích Java 17 về ngôn ngữ, bytecode và API chuẩn:

```bash
javac --release 17 -encoding UTF-8 -parameters Example.java
```

Đây là lệnh minh họa; `Example.java` phải tồn tại và chứa mã hợp lệ. Mặc dù `--release 17` giúp giữ tương thích API Java chuẩn, nó **không** tự bảo đảm rằng mọi dependency bên ngoài của ứng dụng cũng hỗ trợ Java 17; cần kiểm tra version dependency và runtime thật.

**Gradle Java toolchain** cho phép chọn compiler JDK chính xác:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Toolchain có thể chọn JDK 17 để biên dịch/test dù Gradle daemon được chạy bằng JDK khác, trong giới hạn tương thích của phiên bản Gradle/plugin. Không đồng nhất `java.toolchain` với `options.release`: toolchain chọn JDK công cụ, `release` đặt mục tiêu API/ngôn ngữ/bytecode cho task JavaCompile.

**Maven:** `maven.compiler.release` hoặc cấu hình `maven-compiler-plugin` điều khiển release đích. Nếu muốn Maven thực sự chọn **JDK compiler** cụ thể, cần kiểm soát `JAVA_HOME`/Maven runtime hoặc sử dụng Maven Toolchains Plugin theo yêu cầu dự án.

## 4. Tại sao mã hóa UTF-8 rất quan trọng?

UTF-8 là quy ước portable cho mã nguồn Java, cấu hình, tài liệu và dữ liệu có tiếng Việt. Ví dụ:

```java
public class VietnameseText {
    public static void main(String[] args) {
        System.out.println("Xin chào, thế giới!");
    }
}
```

Nếu `VietnameseText.java` được lưu **dưới dạng UTF-8**, biên dịch tường minh bằng:

```bash
javac -encoding UTF-8 VietnameseText.java
java VietnameseText
```

Stdout từ chương trình, khi terminal hiển thị Unicode đúng:

```text
Xin chào, thế giới!
```

**Hai điều phải cùng đúng:** editor/Git lưu đúng bytes UTF-8, và trình biên dịch đọc những bytes đó như UTF-8. Việc thêm `-encoding UTF-8` **không tự chuyển đổi** một file nguồn vốn đang lưu bằng một encoding cũ. Với JDK 17, không nên dựa vào default charset của từng máy; từ JDK 18, UTF-8 trở thành default charset của các Java API tiêu chuẩn trong nhiều ngữ cảnh, nhưng khai báo encoding rõ ở build vẫn giúp dự án đa môi trường và tránh hiểu nhầm.

**Phân biệt các loại encoding:**

| Khái niệm | Ví dụ | Có phải `-encoding UTF-8` của javac quản lý không? |
|---|---|---|
| Mã hóa nội dung file `.java` | `src/main/java/.../VietnameseText.java` | **Có**, khi javac đọc nguồn |
| Encoding tài nguyên được lọc (resource filtering) | `application.properties`, template | **Không trực tiếp**, do Maven Resources Plugin/Gradle copy filtering quản lý |
| Charset dữ liệu HTTP/JSON | Request/response của ứng dụng | **Không**; dùng HTTP media type và cấu hình thư viện |
| Charset JDBC/database | Kết nối và cột database | **Không**; phụ thuộc driver, DB và schema |
| Mã hóa stdout/terminal | Console Windows/Linux, log viewer | **Không**; terminal và JVM output cũng tham gia |
| Tên tham số trong `.class` | Reflection đọc `username` | **Không**; liên quan `-parameters` |

**Chú ý Spring Boot resources:** ở Maven, `project.build.sourceEncoding` thường được plugin compiler/resources dùng làm mặc định; ở Gradle, `options.encoding` chỉ áp dụng cho `JavaCompile`. Khi **lọc nội dung resources** (ví dụ dùng `expand`, `filter`), cần kiểm tra charset của task lọc riêng. Nếu chỉ copy binary/resource bytes bình thường, không nên ép “decode và encode lại” không cần thiết. Đặc biệt tránh lọc sai binary như ảnh/PDF.

## 5. -parameters làm gì trong class file?

Tùy chọn Java compiler `-parameters` yêu cầu ghi metadata tên tham số hình thức của các method/constructor vào **`MethodParameters` attribute** của bytecode. API reflection có:

- `Executable.getParameters()`: danh sách tham số của method/constructor.
- `Parameter.getName()`: tên tham số mà reflection biết.
- `Parameter.isNamePresent()`: `true` khi class file chứa tên thực theo `MethodParameters`.
- `Parameter.getType()` / `getParameterizedType()`: thông tin kiểu tham số, là khía cạnh khác tên.

Nếu biên dịch **không** có `-parameters`, tên tham số thường không được lưu; reflection tạo tên tổng hợp như `arg0`, `arg1` và trả `isNamePresent() == false`. Kiểu tham số, số lượng tham số và các annotation vẫn có thể có; không được hiểu rằng tắt `-parameters` xóa luôn signature của method.

**Đừng nhầm với `-g` hoặc debug symbols.** `javac -g` có thể ghi `LocalVariableTable` cùng thông tin phục vụ debugger. Đây không phải metadata tên tham số Java reflection sử dụng theo `Parameter.isNamePresent()`. Các phiên bản Spring Framework hiện đại, đặc biệt Spring 6.1+, yêu cầu `-parameters` ở những trường hợp cần suy luận tên qua reflection; việc có debug local-variable metadata không thay thế flag này.

## 6. Ví dụ Java 17 tự chạy: so sánh có và không có -parameters

Tạo **một file duy nhất** `ParameterProbe.java` (lưu UTF-8):

```java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public final class ParameterProbe {
    public static String greet(String guest, int repeat) {
        return "Xin chào, " + guest + " (" + repeat + ")";
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Method method = ParameterProbe.class.getDeclaredMethod(
                "greet", String.class, int.class);

        for (Parameter parameter : method.getParameters()) {
            System.out.println(parameter.getName()
                    + ": " + parameter.isNamePresent());
        }

        System.out.println(greet("Hà", 2));
    }
}
```

Mã độc lập, chỉ dùng Java Standard Library. Chạy bằng JDK 17+ và terminal hỗ trợ Unicode. Cách làm rõ ràng nhất là biên dịch vào **hai thư mục output khác nhau** để tránh chạy nhầm class cũ.

### 6.1. Biên dịch với -parameters

Trên Linux/macOS hoặc shell tương thích POSIX:

```bash
mkdir -p out-with out-without
javac --release 17 -encoding UTF-8 -parameters -d out-with ParameterProbe.java
java -cp out-with ParameterProbe
```

Stdout **của `java`** là:

```text
guest: true
repeat: true
Xin chào, Hà (2)
```

`javac` thường không in gì khi biên dịch thành công. `--release 17` là ví dụ đặt Java target; `-encoding UTF-8` đảm bảo đọc chuỗi tiếng Việt; `-parameters` cung cấp tên `guest` và `repeat` cho reflection.

### 6.2. Biên dịch không có -parameters

```bash
javac --release 17 -encoding UTF-8 -d out-without ParameterProbe.java
java -cp out-without ParameterProbe
```

Stdout **của `java`** là:

```text
arg0: false
arg1: false
Xin chào, Hà (2)
```

Phần chuỗi tiếng Việt **vẫn in đúng** vì đã dùng UTF-8; chỉ khác ở metadata tên tham số. Do cả hai thư mục chứa phiên bản class riêng, bạn có thể so sánh mà không đè file `.class`.

Trên Windows PowerShell, tạo thư mục bằng:

```powershell
New-Item -ItemType Directory -Force out-with, out-without | Out-Null
```

Sau đó dùng các lệnh `javac` và `java -cp` bên trên (không cần `./`). Nếu console Windows hiển thị tiếng Việt sai, kiểm tra thiết lập terminal/encoding đầu ra trước khi quy kết lỗi cho `-parameters`.

### 6.3. Kiểm tra MethodParameters bằng javap

`javap` đi kèm JDK cho phép xem bytecode metadata:

```bash
javap -v -p -classpath out-with ParameterProbe
javap -v -p -classpath out-without ParameterProbe
```

Tìm section `MethodParameters` của method `greet` trong bản `out-with`: nó ghi hai tên `guest` và `repeat`. Bản `out-without` không có metadata tham số tương ứng cho method `greet`. Output `javap -v` còn có nhiều constant-pool/attribute khác nên không cần ghi nhớ toàn bộ.

Đây là cách kiểm chứng cơ chế **thực tế**: nhìn class file thay vì chỉ thấy editor còn tên biến.

## 7. Spring Framework dùng tên tham số ở đâu?

Spring Boot chạy trên Spring Framework. Nhiều công việc dựa vào annotation chỉ cần biết kiểu, nhưng **một số cơ chế cần tên tham số** khi bạn không ghi tên tường minh trong annotation.

### 7.1. Spring MVC: @PathVariable và @RequestParam

Xét đoạn controller dưới đây, đặt trong project đã có `spring-boot-starter-web`:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/users/{username}")
    public String byPath(@PathVariable String username) {
        return "Xin chào, " + username;
    }

    @GetMapping("/greeting")
    public String byQuery(@RequestParam String name) {
        return "Xin chào, " + name;
    }
}
```

Với source đã được biên dịch có `-parameters`, framework có thể nhận diện tên `username` và `name` khi annotation không khai báo tên. Ví dụ HTTP request: `GET /users/ha` hoặc `GET /greeting?name=Ha`.

Khi tên tham số **không có trong class file** và annotation **không chỉ rõ tên**, Spring có thể không xác định được tên argument cần bind và báo lỗi, tùy phiên bản/framework path. Đây là tình huống thường gặp khi build bị đổi từ Maven parent hoặc Gradle Spring Boot plugin sang cấu hình javac tự viết.

Cách khai báo tường minh tránh phụ thuộc vào metadata tên cho trường hợp này:

```java
@GetMapping("/users/{username}")
public String byPath(@PathVariable("username") String username) {
    return "Xin chào, " + username;
}

@GetMapping("/greeting")
public String byQuery(@RequestParam("name") String name) {
    return "Xin chào, " + name;
}
```

Hai method ở đoạn sau là **phần thay thế** cho các method tương ứng trong controller, không được dán thêm nguyên vẹn vào cùng class với cùng đường dẫn. Chúng cần import `GetMapping`, `PathVariable`, `RequestParam` như ví dụ trước.

### 7.2. Constructor injection và chọn bean theo tên

Spring ưu tiên resolve dependency theo **kiểu**; tên tham số là một tín hiệu bổ sung khi nhiều bean cùng kiểu, không phải điều kiện bắt buộc cho mọi constructor injection. Ví dụ khi có hai bean `Formatter` và constructor nhận `Formatter orderFormatter`, Spring có thể dùng tên `orderFormatter` để phân biệt nếu không có qualifier/primary phù hợp.

Theo tài liệu Spring Framework, từ **Spring Framework 6.1**, fallback match theo tên tham số trong trường hợp autowiring yêu cầu flag `-parameters`. Vì vậy, trong project Spring Boot hiện đại, thiếu flag có thể làm một ca injection từng chạy được nay không xác định được bean.

Khi ý nghĩa bean thực sự cần rõ ràng, dùng `@Qualifier("orderFormatter")` hoặc cơ chế lựa chọn bean phù hợp; không phụ thuộc một cách không chủ đích vào cách đặt tên biến nguồn. `-parameters` vẫn được khuyến nghị để reflection hoạt động ổn định.

### 7.3. Những tình huống khác

Một số thư viện mapping, binding hoặc serialization sử dụng tên tham số constructor/method; mức độ ảnh hưởng tùy thư viện, annotation và cấu hình của nó. Không khẳng định tất cả API Spring/Jackson đều bắt buộc `-parameters`: annotation có tên tường minh, record metadata và các đường suy luận khác có thể đủ trong từng trường hợp.

**Lưu ý Kotlin:** mã Kotlin có cơ chế metadata riêng. Spring Boot Gradle plugin khi phối hợp Kotlin plugin có thể cấu hình `-java-parameters` cho `KotlinCompile`; không lấy tùy chọn `JavaCompile` của Java áp dụng máy móc cho một project Kotlin thuần.

## 8. Maven với spring-boot-starter-parent: những mặc định đã có

Với Maven project kế thừa **`org.springframework.boot:spring-boot-starter-parent`**, tài liệu Spring Boot 3.5 mô tả sẵn:

- Java 17 là mức mặc định nếu không override `java.version`.
- Source encoding UTF-8.
- Biên dịch với `-parameters`.
- Cấu hình Maven Compiler Plugin và các plugin khác có chủ đích.

Một `pom.xml` minh họa cho **project Spring Boot sẵn có**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>compiler-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Với source ứng dụng `@SpringBootApplication` và Java controller hợp lệ, đây là một POM dùng được cho Spring Boot 3.5.x. Để đóng gói thành executable JAR, project phải có entry point `main` thực sự. Ví dụ này **không cần khai báo thêm `<parameters>true</parameters>`** vì starter parent đã thiết lập.

`<java.version>17</java.version>` chọn target Java theo mô hình parent; `project.build.sourceEncoding` làm encoding tường minh, dù parent đã có giá trị mặc định tương ứng. **Đừng thêm cờ `-parameters` lặp đi lặp lại qua nhiều cấu hình nếu không có nhu cầu.**

Sau khi có Maven Wrapper do Spring Initializr sinh, dùng:

```bash
./mvnw clean compile
./mvnw test
```

Trên Windows: `mvnw.cmd clean compile` và `mvnw.cmd test`. Maven sẽ biên dịch nguồn và test theo phase, không có một stdout cố định cho mọi project. `compile` tạo class trong `target/classes`; `test` kiểm thử theo plugin và test có trong project.

## 9. Maven dùng corporate parent hoặc chỉ import BOM: cần tự cấu hình

Nếu project **không kế thừa `spring-boot-starter-parent`**, chẳng hạn dùng parent riêng rồi import BOM `spring-boot-dependencies`, bạn **không tự động nhận** compiler plugin configuration và các mặc định từ starter parent.

**BOM chỉ quản lý dependency versions**, không bảo đảm cấu hình Java compiler, `-parameters` hay resource filtering giống parent. Với trường hợp đó, cấu hình Maven Compiler Plugin tường minh trong `pom.xml`:

```xml
<!-- Thêm vào phần <build><plugins> của POM không dùng Boot parent. -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Đồng thời có thể đặt property ở cấp POM:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
```

**Chọn một nơi làm nguồn cấu hình chính:** dùng `<configuration>` của plugin hoặc các property tương ứng (plugin hỗ trợ), tránh rải nhiều giá trị khác nhau. `<parameters>true</parameters>` tương đương yêu cầu compiler ghi `MethodParameters`, không phải option runtime của `java -jar`. `<encoding>UTF-8</encoding>` chỉ định charset nguồn Java.

Không nên sao chép cùng lúc **cả hai snippet** với giá trị mâu thuẫn trong một POM; chúng chỉ minh họa hai cách biểu đạt. Phiên bản Maven Compiler Plugin cần được cố định bởi parent/plugin management của tổ chức hoặc khai báo cụ thể, và tương thích với Maven/JDK đang dùng.

Một số version compiler plugin có thể thay đổi default `source`/`target` hoặc version tối thiểu Maven/JDK theo thời gian; giữ `release` tường minh để tránh phụ thuộc default.

## 10. Gradle + Spring Boot plugin: cấu hình JavaCompile

Với Spring Boot Gradle Plugin **và** Java plugin, tài liệu Spring Boot 3.5 mô tả:

- Tự đặt `options.encoding = 'UTF-8'` trên các `JavaCompile` task **chưa có encoding** được cấu hình.
- Tự thêm compiler argument `-parameters` cho các `JavaCompile` task.
- Cung cấp các task như `bootJar`, `bootRun` và các cấu hình hỗ trợ Java.

Vì vậy project **đã áp dụng Spring Boot Gradle plugin** không cần tự thêm `-parameters` để có tên tham số, trừ khi có custom build logic đã thay đổi compiler args hoặc build có module Java thuần không áp dụng Boot plugin.

Ví dụ `build.gradle` Groovy DSL cho project Spring Boot Java 17:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

// Cấu hình tường minh encoding và target Java của các JavaCompile task.
// Spring Boot plugin đã cung cấp -parameters; không cần thêm lần nữa.
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong build ví dụ này, task `compileJava` và `compileTestJava` đều chịu rule `tasks.withType(JavaCompile)`. Các generated Java source được gắn vào JavaCompile task đúng cách cũng nhận options tương ứng. `options.release = 17` chọn target API/ngôn ngữ; toolchain yêu cầu JDK 17. Không cần đặt `sourceCompatibility`/`targetCompatibility` trùng lặp khi đã dùng mô hình rõ ràng.

Lệnh kiểm tra (với Gradle Wrapper và code hợp lệ trong project):

```bash
./gradlew --version
./gradlew clean compileJava --info
./gradlew test
```

Với Windows dùng `gradlew.bat`. Chỉ xem flag trong log `--info` chưa chắc đủ để biết bytecode thực tế; có thể xem class file bằng `javap` như ở mục 6.

### 10.1. Gradle Kotlin DSL tương đương

`build.gradle.kts` trong project có plugin tương ứng:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.test {
    useJUnitPlatform()
}
```

Đây là cú pháp Kotlin DSL, khác Groovy DSL ở `id("...")`, `implementation("...")`, `tasks.withType<JavaCompile>()` và `options.release.set(17)`. Với Java source và Boot plugin, `-parameters` vẫn được Boot plugin thiết lập.

### 10.2. Module Java không áp dụng Spring Boot plugin

Trong build nhiều module, một library module có thể chỉ áp dụng `java-library`, không áp dụng `org.springframework.boot`. Khi đó **đừng suy ra** flag compiler của Boot application module sẽ tự lan sang JavaCompile của library module.

Ở module đó, cấu hình rõ ràng:

```groovy
// build.gradle của module chỉ dùng plugin 'java-library'
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
    options.compilerArgs.add('-parameters')
}
```

Kotlin DSL trong `build.gradle.kts` của module Java thuần:

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
    options.compilerArgs.add("-parameters")
}
```

**Điểm cần nhớ:** đặt `options.compilerArgs.add("-parameters")` trong module chỉ dùng Java plugin là cách tường minh. Ở module Boot có plugin đã thêm flag, không cần lặp lại, nhất là nếu custom task/plugin xử lý flags theo cách riêng.

Trong multi-module build, để tránh quên cấu hình ở một module, cân nhắc **convention plugin** hoặc build logic chung được quản lý tập trung. Không mặc định mọi module đều dùng đúng một target Java; lựa chọn phụ thuộc API mà library muốn hỗ trợ.

## 11. Khi nào cần cấu hình resources encoding riêng?

Java compilation và resource processing là **hai bước khác nhau**:

```text
src/main/java/*.java  --javac encoding UTF-8--> target/classes hoặc build/classes
src/main/resources/** --copy/filter-----------> target/classes hoặc build/resources
```

- **Maven:** `maven-resources-plugin` đảm nhiệm xử lý file từ `src/main/resources`. Thuộc tính `project.build.sourceEncoding` thường là mặc định cho plugin khi lọc text, nhưng có tùy chọn `encoding` và cơ chế lọc riêng theo file. Với Spring Boot Maven parent, `application.properties`/`application.yml` còn có quy ước filter placeholder riêng để tránh va chạm với placeholder Spring.
- **Gradle:** task `processResources` thường copy resource; nếu khai báo `expand` hoặc filter để thay thế biến trong text, chú ý `filteringCharset`, ví dụ `'UTF-8'`, để bước biến đổi text đọc đúng dữ liệu. `options.encoding` của `JavaCompile` không tự đặt `filteringCharset` cho `processResources`.
- **Binary resources** (ảnh, font, file nén…) cần copy ở dạng bytes, tránh áp dụng text filter bừa.

Gradle Groovy DSL ví dụ khi **thực sự có resource filtering**:

```groovy
tasks.named('processResources', ProcessResources) {
    filteringCharset = 'UTF-8'
    filesMatching('build-info.txt') {
        expand(projectVersion: project.version)
    }
}
```

Đây là **snippet nâng cao**: giả định có file text `src/main/resources/build-info.txt` chứa placeholder Groovy template tương ứng và project đã áp dụng Java plugin. Nếu không dùng resource filtering, không cần thêm cấu hình này. Khi dùng Spring `application.properties`, cẩn thận các placeholder trong config để không bị build tool thay đổi ngoài ý muốn.

Tương tự, file `application.properties` có thể chứa ký tự Unicode; khi chạy, Spring đọc tài nguyên theo cơ chế của nó. Vấn đề đó nằm ngoài phạm vi `javac -encoding`, nên không chữa lỗi tài nguyên bằng cách chỉ đổi compiler flag.

## 12. Kiểm tra compiler thật sự đã dùng đúng options

### 12.1. Chẩn đoán Maven

Trong project Maven có wrapper:

```bash
./mvnw -version
./mvnw help:effective-pom
./mvnw clean compile
```

`help:effective-pom` cho biết cấu hình hiệu lực sau khi ghép parent/profile/plugin management, hữu ích khi kiểm tra `maven-compiler-plugin`. Output có thể rất dài; tìm phần `maven-compiler-plugin`, `release`, `encoding` và `parameters`. Cấu hình compiler từ property/parent đôi khi không hiện đúng ở vị trí bạn mong đợi trong một đoạn trích ngắn, nên xem plugin thực sự sử dụng trong build.

Nếu cần xem thông tin compiler chi tiết để chẩn đoán, có thể chạy `./mvnw -X compile`; log debug có thể chứa chi tiết môi trường, nên không đăng nguyên log lên kênh công khai khi chưa lọc thông tin nhạy cảm.

File Java biên dịch nằm ở `target/classes`, test class ở `target/test-classes`, trừ khi build đã thay đổi output path.

### 12.2. Chẩn đoán Gradle

```bash
./gradlew --version
./gradlew clean compileJava --info
./gradlew compileTestJava --info
```

Nếu task báo `UP-TO-DATE`, Gradle có thể đã dùng output hợp lệ từ lần trước. Khi thay đổi compiler args/encoding, input task thường thay đổi nên compile lại; tuy nhiên để xác nhận metadata với độ tin cậy cao, chạy clean compile có chủ đích và kiểm tra `.class`.

Output mặc định Gradle Java plugin thường ở `build/classes/java/main` và `build/classes/java/test`, với resource output riêng. Với build custom, đường dẫn có thể khác.

### 12.3. Dùng javap xem metadata của một class

Với class tự tạo trong package `com.example.demo`:

```bash
# Maven (tại root của module)
javap -v -p -classpath target/classes com.example.demo.GreetingController

# Gradle (tại root của module)
javap -v -p -classpath build/classes/java/main com.example.demo.GreetingController
```

Trong phần method có tham số, tìm `MethodParameters`. Nếu có tên tham số thật và `javap` thấy chúng thì compiler đã ghi metadata. Nếu không, kiểm tra class file đúng module/đúng lần build, plugin config, compiler args, toolchain và khả năng lớp đến từ dependency JAR khác.

Nếu build chạy bằng JDK khác với JDK đích, `javap`/`java` runtime để kiểm tra vẫn phải tương thích với class-file version được tạo. Kiểm tra `./gradlew --version`, `./mvnw -version` và `java -version` để tránh nhầm phiên bản.

### 12.4. Kiểm tra hành vi trong ứng dụng

Với controller `@GetMapping("/users/{username}")` đã được gắn vào Spring Boot application, gọi endpoint thực tế qua integration test hoặc HTTP request. Nếu xử lý lỗi do thiếu tên tham số, xem stacktrace và class metadata, rồi so sánh với trường hợp annotation ghi tường minh `@PathVariable("username")`.

**Quan sát có ý nghĩa hơn kết luận từ chữ ký nguồn.** Một phương thức nguồn có `String username` không có nghĩa file `.class` đang chạy đã lưu `username`. Nhiều lỗi đến từ build stale, JAR cũ, khác module hoặc class được biên dịch bởi pipeline khác.

## 13. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
|---|---|---|
| `unmappable character for encoding...` khi javac compile | File nguồn lưu charset khác charset compiler đang dùng | Kiểm tra bytes/editor encoding, chuyển file sang UTF-8 rồi đặt `-encoding UTF-8` |
| Log hoặc response hiển thị sai dấu tiếng Việt nhưng compile thành công | Console, resource, HTTP hoặc database charset khác | Xác định tầng gây lỗi; `options.encoding` không tự sửa runtime/terminal |
| Reflection trả `arg0`, `arg1` | Class thiếu `MethodParameters` từ `-parameters` | Bật flag ở task/plugin biên dịch đúng module, clean compile và xem `javap` |
| Spring MVC không suy ra tên argument cho `@PathVariable` / `@RequestParam` | Thiếu tên tường minh và class không giữ tên tham số | Bật `-parameters` hoặc ghi rõ annotation value; kiểm tra class đang chạy |
| Constructor injection không chọn đúng bean theo tên | Nhiều bean cùng kiểu, thiếu qualifier/primary hoặc metadata tên | Dùng `@Qualifier` hoặc `@Primary` khi phù hợp; đảm bảo `-parameters` nếu dựa vào tên tham số |
| Build Maven có BOM nhưng không có `-parameters` | BOM chỉ quản lý dependency, không đem theo compiler plugin defaults của parent | Cấu hình `maven-compiler-plugin` hoặc project properties tường minh |
| Gradle Boot module đúng nhưng library module khác thiếu metadata | Boot Gradle plugin chỉ áp dụng vào module đã cấu hình | Thiết lập `JavaCompile` ở library/convention plugin |
| Không tìm thấy JDK 17 toolchain | Gradle/Maven Toolchain chưa phát hiện JDK hoặc chưa cấu hình auto-provision | Kiểm tra cài đặt JDK và toolchain resolver, phiên bản wrapper |
| `invalid source release: 17` | Compiler JDK đang dùng cũ hơn Java 17 | Dùng JDK 17+ thích hợp; kiểm tra compiler/toolchain thực |
| Đặt `-Dfile.encoding=UTF-8` mà metadata vẫn mất | JVM runtime encoding không phải `javac -parameters` | Cấu hình compiler flag đúng chỗ |
| Biên dịch thành công nhưng runtime báo `UnsupportedClassVersionError` | Bytecode yêu cầu Java mới hơn runtime | Kiểm tra JDK chạy app và release target; đồng bộ môi trường |
| Biên dịch vẫn dùng API JDK mới dù target cũ | Chỉ đặt source/target, không kiểm soát API release | Dùng `--release` hoặc công cụ tương đương khi cần target chắc chắn |
| `javap` không thấy tên dù POM/build.gradle đã sửa | Class đang xem được sinh từ build cũ hoặc module khác | Xóa đúng output rồi compile lại, kiểm tra chính class trong artifact |

**Không nên khắc phục một lỗi encoding bằng cách thêm mọi option compiler có thể tìm được.** Xác định xem lỗi ở source decode, resource filtering, text output hay runtime trước. Tương tự, chỉ bật `-parameters` ở app module sẽ không sửa được class trong library JAR được biên dịch độc lập.

## 14. Quy trình cấu hình chuẩn cho một nhóm phát triển

1. **Thống nhất JDK và target Java.** Ví dụ Java 17 cho các dự án dùng Spring Boot 3.x; kiểm tra version Spring Boot thực tế, Gradle Wrapper/Maven Plugin và môi trường triển khai trước khi cố định.
2. **Thống nhất UTF-8 ở editor, Git và compiler.** Nên có chính sách code style/IDE và cấu hình build tường minh. Tránh để mỗi OS dùng default khác nhau.
3. **Chọn mô hình build.** Với Maven starter parent, tận dụng `java.version`, UTF-8 và `-parameters` đã có; với Maven corporate parent, định nghĩa rõ compiler plugin options. Với Gradle Boot module, plugin Boot tự thêm UTF-8 nếu chưa được cấu hình và `-parameters`; với Java library module, thêm flag tường minh.
4. **Áp dụng cho cả source chính và test khi cần.** `compileJava`, `compileTestJava` và các custom `JavaCompile` task phải dùng config nhất quán nếu framework/reflection đọc chúng.
5. **Dùng một chương trình reflection nhỏ để kiểm chứng.** So sánh `Parameter.isNamePresent()` với/không có flag; xem `MethodParameters` trong `javap` khi nghi ngờ.
6. **Kiểm thử binding thực tế.** Khi annotation dựa vào parameter name, có integration test để phát hiện ngay việc thiếu compiler metadata.
7. **Chỉ sửa đúng lớp cấu hình gây lỗi.** Maven parent, Gradle module, toolchain, resources hay console khác nhau; không dùng một runtime JVM property để bù cho compiler setting.
8. **Giữ CI tái lập được.** Commit build scripts và wrapper, chọn JDK chuẩn, chạy clean build theo yêu cầu pipeline và xác minh artifact thực tế.

### Tài liệu chính thức để đối chiếu

- [Java javac command — `-encoding`, `--release`, `-parameters`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [Java Reflection Parameter API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Parameter.html)
- [Spring Boot 3.5 Gradle Plugin — Reacting to Other Plugins](https://docs.spring.io/spring-boot/3.5/gradle-plugin/reacting.html)
- [Spring Boot 3.5 Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html)
- [Maven Compiler Plugin — compile goal parameters](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Gradle CompileOptions API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/compile/CompileOptions.html)
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Spring Framework — Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)

**Ghi nhớ:** Java compiler cần **đúng JDK/release**, **đúng encoding** để đọc source, và **`-parameters`** nếu ứng dụng cần tên tham số tại runtime. Trình biên dịch tạo ra bytecode; Spring chỉ đọc được metadata có trong bytecode mà process build thực sự đã sinh.
