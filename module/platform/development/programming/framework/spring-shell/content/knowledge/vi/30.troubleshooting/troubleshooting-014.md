# NoSuchMethodError hoặc ClassNotFoundException do xung đột phụ thuộc

Một ứng dụng Spring Shell có thể biên dịch và đóng gói thành công nhưng lỗi ngay khi khởi động hoặc khi gọi một command. Các thông báo như `NoSuchMethodError`, `ClassNotFoundException` và `NoClassDefFoundError` thường cho thấy classpath lúc chạy khác với classpath đã dùng khi biên dịch, một thư viện bị thiếu, hoặc nhiều phiên bản thư viện không tương thích cùng tham gia vào ứng dụng.

Không xử lý các lỗi này bằng cách thêm ngẫu nhiên một JAR hoặc nâng tất cả dependency lên phiên bản mới nhất. Trước hết cần xác định class/method nào bị lỗi, class đó được nạp từ JAR nào, và dependency graph đã chọn phiên bản nào. Với Spring Shell, bước quan trọng là giữ đúng thế hệ tương thích: Spring Shell 3.x thuộc hệ Spring Boot 3/Spring Framework 6; Spring Shell 4.x yêu cầu Spring Boot 4/Spring Framework 7.

## Phân biệt các lỗi thường gặp

Những exception/error này có tên gần nhau nhưng chỉ ra các tình huống khác nhau:

| Lỗi | Ý nghĩa | Nguyên nhân thường gặp |
|---|---|---|
| `NoSuchMethodError` | Bytecode đang chạy gọi một method mà class được JVM nạp không có method descriptor tương ứng | Compile với phiên bản API mới nhưng runtime nạp JAR cũ; hai module không cùng dòng version; class trùng tên đến từ JAR khác |
| `ClassNotFoundException` | Một thao tác nạp class theo tên như `Class.forName()` hoặc `ClassLoader.loadClass()` không tìm thấy class | Thiếu dependency runtime, sai tên class, classloader không nhìn thấy module hoặc driver/provider không có trên runtime classpath |
| `NoClassDefFoundError` | JVM cần định nghĩa class trong quá trình thực thi nhưng không tìm thấy định nghĩa đó | Dependency có lúc compile nhưng thiếu lúc runtime; JAR bị loại khỏi gói; hoặc class khởi tạo thất bại trước đó |
| `NoSuchMethodException` | API reflection không tìm thấy method theo tên/tham số được yêu cầu | Tên method, kiểu tham số hoặc cách tìm bằng reflection không đúng |
| `AbstractMethodError` | Code gọi method cần được implement nhưng class runtime không có implementation tương thích | Interface/abstract class và implementation được biên dịch với các phiên bản API khác nhau |
| `NoSuchFieldError` | Bytecode truy cập field không còn tồn tại trong class runtime | Compile/runtime dùng phiên bản class khác nhau |
| `UnsupportedClassVersionError` | JVM không hỗ trợ phiên bản bytecode của class file | Chạy artifact được biên dịch bằng JDK mới hơn runtime JVM |

`NoSuchMethodError`, `NoClassDefFoundError`, `AbstractMethodError` và `NoSuchFieldError` thuộc nhóm `LinkageError`. `ClassNotFoundException` là exception được ném khi yêu cầu nạp class theo tên không thành công. `NoSuchMethodException` là lỗi reflection dạng checked exception; không nhầm nó với `NoSuchMethodError` là lỗi linkage lúc runtime.

### NoSuchMethodError: method có lúc compile nhưng biến mất lúc runtime

Giả sử code được biên dịch với thư viện có API:

```java
package com.example.transport;

public class RequestClient {
    public void send(String endpoint, int timeoutSeconds) {
        // API ở phiên bản mới.
    }
}
```

Nhưng lúc chạy, classloader nạp phiên bản cũ chỉ có:

```java
package com.example.transport;

public class RequestClient {
    public void send(String endpoint) {
        // API cũ không có overload mới.
    }
}
```

Code gọi `send(String, int)` đã biên dịch thành công, nhưng JVM không tìm thấy method descriptor đó trong class thực tế được nạp và ném `NoSuchMethodError`. Trường hợp tương tự có thể xảy ra khi Spring Shell module, Spring Framework module hoặc JLine module không cùng bộ phiên bản.

Method descriptor bao gồm kiểu tham số và kiểu trả về. Chỉ nhìn tên method trong IDE chưa đủ; hãy so sánh đúng chữ ký của method ở phiên bản compile và runtime.

### ClassNotFoundException và NoClassDefFoundError

`ClassNotFoundException` thường xuất hiện khi code yêu cầu nạp class theo tên:

```java
Class<?> driverClass = Class.forName("com.example.Driver");
```

Nếu class không có trên classpath mà classloader đang sử dụng, `Class.forName()` có thể ném `ClassNotFoundException`. Kiểm tra tên class, dependency runtime và classloader đang thực hiện việc nạp.

`NoClassDefFoundError` thường xảy ra khi bytecode cần một class trong quá trình chạy nhưng JVM không thể tìm thấy định nghĩa. Ví dụ, ứng dụng compile với một thư viện nhưng dependency đó bị khai báo scope `provided`, `test`, `compileOnly`, bị exclude hoặc không được đóng gói vào executable JAR.

Một trường hợp khác: class từng thất bại trong static initializer. Lần đầu có thể thấy `ExceptionInInitializerError` với nguyên nhân gốc; những lần sử dụng tiếp theo có thể thấy `NoClassDefFoundError: Could not initialize class ...`. Khi gặp thông báo này, tìm exception đầu tiên trong log thay vì chỉ xử lý lần lỗi sau.

## Vì sao dependency conflict xảy ra?

Một thư viện Spring Shell kéo theo nhiều dependency như Spring Boot, Spring Framework, JLine, Jackson và SLF4J. Ứng dụng có thể thêm một thư viện khác kéo theo phiên bản khác của cùng artifact. Build tool phải giải quyết các yêu cầu đó để tạo classpath cuối cùng.

Ví dụ đồ thị phụ thuộc:

```text
customer-cli
├── spring-shell-starter:3.4.x
│   ├── spring-shell-core:3.4.x
│   ├── spring-context:6.2.x
│   └── jline-reader:3.x
└── legacy-admin-client
    ├── spring-context:5.3.x
    └── jline-reader:3.y
```

Sơ đồ chỉ minh họa hai nhánh yêu cầu version khác nhau. Phiên bản được chọn cuối cùng phụ thuộc quy tắc của Maven/Gradle, BOM, constraint và cấu hình dự án. Ngay cả khi build tool chọn được một phiên bản duy nhất cho từng artifact, phiên bản đó vẫn có thể không tương thích với code đã biên dịch từ nhánh còn lại.

Các nguyên nhân phổ biến:

- Khai báo version trực tiếp cho `spring-core`, `spring-context`, `spring-beans` hoặc `spring-boot` thay vì dùng bộ version do BOM quản lý.
- Dùng Spring Shell 3.x cùng dependency Spring Boot 4/Spring Framework 7, hoặc dùng Spring Shell 4.x cùng Spring Boot 3/Spring Framework 6.
- Một thư viện cũ kéo theo Spring/JLine/Jackson version cũ hơn.
- Exclude dependency chuyển tiếp nhưng quên khai báo dependency thay thế ở runtime.
- Dùng `compileOnly`, `provided` hoặc `test` cho dependency cần thiết khi chạy executable JAR.
- IDE chạy class cũ từ output directory trong khi command line chạy artifact mới, hoặc ngược lại.
- Gói phân phối chứa JAR cũ trong `lib/`, Docker image cũ hoặc một bản JAR bị copy thủ công.
- Hai JAR khác nhau chứa class cùng fully qualified name; classloader nạp bản không đúng với caller.
- Một plugin, application server hoặc custom classloader nạp phiên bản dependency khác với classloader của ứng dụng.

## Giữ đúng thế hệ Spring Shell và Spring Boot

Trước khi sửa dependency, xác định dòng phiên bản của toàn bộ stack:

| Stack | Nền tảng chính | Quy tắc |
|---|---|---|
| Spring Shell 3.3.x | Spring Boot 3.3.x, Spring Framework 6.1.x | Giữ các module Spring Shell ở cùng dòng 3.3.x và dùng bộ dependency tương ứng với Boot 3.3 |
| Spring Shell 3.4.x | Spring Boot 3.4.x, Spring Framework 6.2.x | Giữ các module Spring Shell ở cùng dòng 3.4.x và dùng bộ dependency tương ứng với Boot 3.4 |
| Spring Shell 4.0.x | Spring Boot 4.x, Spring Framework 7.x | Nâng đồng bộ nền tảng Boot/Framework và các module Spring Shell lên dòng 4.x |

Spring Shell 4 migration guide yêu cầu Spring Boot 4 trở lên và Spring Framework 7. Guide cũng khuyên nâng ứng dụng lên phiên bản Spring Shell 3.4.x mới nhất trước khi chuyển sang 4.x. Không coi việc đổi riêng version `spring-shell-starter` là một migration đầy đủ.

### Ví dụ Maven dùng một bộ version nhất quán

Với dự án Spring Shell 3.4.x dựa trên Spring Boot 3.4.x, để Spring Boot parent quản lý dependency của hệ Boot/Framework và đặt version Spring Shell rõ ràng:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.x</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-shell.version>3.4.x</spring-shell.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-starter</artifactId>
        <version>${spring-shell.version}</version>
    </dependency>
</dependencies>
```

`3.4.x` là placeholder chỉ dòng phiên bản; thay bằng patch release thực tế đã chọn và kiểm tra yêu cầu JDK của release đó. Không copy nguyên chuỗi `3.4.x` vào POM. Nếu dự án không dùng `spring-boot-starter-parent`, import `spring-boot-dependencies` BOM trong `dependencyManagement` và giữ cùng nguyên tắc quản lý version.

Không khai báo version riêng cho từng module `spring-core`, `spring-context`, `spring-beans`, `spring-expression` hoặc các module Spring Framework khác nếu không có lý do tương thích đã được kiểm chứng. Spring Boot BOM là danh sách dependency đã được kiểm thử cùng một bản Spring Boot; override version có thể phá bộ tương thích đó.

### Ví dụ Gradle dùng Spring Boot dependency management

Khi dùng Spring Boot Gradle plugin, plugin có thể import BOM tương ứng. Khai báo Spring Shell cùng một dòng version:

```kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.4.x"
}

extra["springShellVersion"] = "3.4.x"

dependencies {
    implementation("org.springframework.shell:spring-shell-starter:${property("springShellVersion")}")
}
```

Thay các placeholder bằng patch version thật. Nếu dùng Gradle native BOM thay cho dependency management plugin, import `spring-boot-dependencies` bằng `platform(...)` và để BOM quản lý các dependency mà nó sở hữu. Spring Shell version vẫn cần được khai báo theo hướng dẫn của Spring Shell nếu BOM Boot không quản lý artifact đó.

Không dùng `resolutionStrategy.force` để ép tất cả dependency về một version chỉ nhằm làm build hết cảnh báo. Một version cao hơn có thể không tương thích binary với thư viện đã gọi API cũ hoặc mới.

## Bước 1: đọc exception đầu tiên và xác định class/method

Khi gặp lỗi, lưu lại:

1. Exception/error đầu tiên, không chỉ dòng cuối cùng của stack trace.
2. Tên class hoặc method được nhắc trong thông báo.
3. Class gọi method ở frame đầu tiên thuộc code ứng dụng hoặc thư viện liên quan.
4. Lỗi xuất hiện lúc khởi động, khi tạo bean hay khi thực thi command cụ thể.
5. Khác biệt giữa môi trường chạy được và môi trường lỗi: JDK, command line, IDE, container và artifact.

Ví dụ:

```text
java.lang.NoSuchMethodError:
  'void org.springframework.core.SomeType.someMethod(java.lang.String)'
    at org.springframework.shell.SomeComponent.initialize(SomeComponent.java:42)
```

Đọc từ dưới lên trong stack trace để tìm chuỗi gọi liên quan, nhưng bắt đầu điều tra từ class/method được nêu trong error. Đừng chỉ nhìn class gọi method; class được nạp runtime mới là nơi cần xác minh.

Nếu log có `NoClassDefFoundError: Could not initialize class`, tìm lần xuất hiện đầu tiên của class đó trong log để xác định lỗi static initialization ban đầu.

## Bước 2: kiểm tra dependency graph với Maven

Chạy dependency tree ở đúng module tạo executable JAR:

```bash
./mvnw dependency:tree -Dverbose
```

Lọc các nhóm dependency liên quan Spring, Spring Boot, Spring Shell và JLine:

```bash
./mvnw dependency:tree -Dverbose \
  -Dincludes=org.springframework.shell:*,org.springframework.boot:*,org.springframework:*,org.jline:*
```

`-Dverbose` yêu cầu Maven Dependency Plugin hiển thị cả node bị omitted do dependency mediation. Nhìn vào cây để tìm:

- Hai version của cùng một artifact được yêu cầu qua các nhánh khác nhau.
- Artifact bị chọn version khác với version mà thư viện gọi nó được biên dịch cùng.
- Dependency bị omitted hoặc excluded.
- Module Spring Shell, Spring Framework hoặc JLine có version không cùng bộ.
- Scope của dependency không có mặt trong runtime classpath.

Xem effective POM để biết BOM/parent đã áp dụng version nào:

```bash
./mvnw help:effective-pom
```

Có thể tạo classpath runtime để đối chiếu với cách khởi chạy thực tế:

```bash
./mvnw dependency:build-classpath -Dmdep.outputFile=target/runtime-classpath.txt
```

Nếu build dùng nhiều Maven module, chạy các lệnh tại module tạo artifact bị lỗi và xác nhận dependency tree của module đó. Cây dependency ở module cha không nhất thiết giống runtime classpath của executable module.

### Bật kiểm tra dependency convergence

Maven Enforcer có rule `dependencyConvergence` để phát hiện cùng một artifact được yêu cầu ở nhiều version trong dependency tree:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <executions>
                <execution>
                    <id>enforce-dependency-convergence</id>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                    <configuration>
                        <rules>
                            <dependencyConvergence/>
                        </rules>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Rule này giúp phát hiện version divergence sớm trong build. Nó không chứng minh rằng hai artifact khác nhau có API tương thích, và cũng không thay thế kiểm thử runtime. Nếu có ngoại lệ có chủ đích, ghi rõ artifact/scope được loại trừ và lý do thay vì tắt rule cho toàn dự án.

## Bước 3: kiểm tra dependency graph với Gradle

In dependency tree của runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Xác định vì sao một artifact được chọn:

```bash
./gradlew dependencyInsight \
  --dependency spring-shell-core \
  --configuration runtimeClasspath
```

Kiểm tra thêm dependency Spring Framework hoặc JLine nếu stack trace liên quan:

```bash
./gradlew dependencyInsight \
  --dependency spring-context \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency jline-reader \
  --configuration runtimeClasspath
```

`dependencyInsight` cho biết dependency nào kéo artifact vào, version nào được yêu cầu, version nào được chọn và lý do lựa chọn. Gradle mặc định giải quyết version conflict bằng cách chọn version cao nhất trong các version được yêu cầu, trừ khi constraint, rule hoặc rich version thay đổi kết quả. Version cao nhất không có nghĩa là tương thích với mọi caller.

So sánh `compileClasspath` và `runtimeClasspath` nếu lỗi chỉ xảy ra sau khi đóng gói:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Nếu dependency có ở compile classpath nhưng thiếu ở runtime classpath, kiểm tra `compileOnly`, `runtimeOnly`, exclusion và cấu hình custom. Nếu version được chọn khác nhau giữa hai configuration, tìm dependency chỉ xuất hiện ở runtime.

Có thể cấu hình Gradle fail khi phát hiện version conflict trong lúc phát triển:

```kotlin
configurations.configureEach {
    resolutionStrategy {
        failOnVersionConflict()
    }
}
```

Chính sách này làm build dừng sớm để nhóm xử lý conflict. Không dùng nó thay cho BOM/constraints và không ép version một cách mù quáng.

## Bước 4: xác định JAR thực sự cung cấp class

Dependency tree cho biết build tool đã giải quyết graph như thế nào. JVM vẫn có thể nạp class từ một vị trí khác do launcher, executable archive, plugin hoặc custom classloader.

### Xem nguồn class bằng Java code

Có thể in classloader và `CodeSource` của một class nghi ngờ:

```java
import java.security.CodeSource;

static void printClassOrigin(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    CodeSource source = type.getProtectionDomain() == null
            ? null
            : type.getProtectionDomain().getCodeSource();

    String location = source == null
            ? "<không xác định>"
            : source.getLocation().toExternalForm();

    System.err.printf("class=%s loader=%s source=%s%n",
            type.getName(), loader, location);
}
```

Gọi hàm với class liên quan, ví dụ class của Spring Shell, Spring Framework hoặc thư viện đang gây lỗi. `CodeSource` có thể là `null` đối với một số classloader hoặc class được nạp theo cơ chế đặc biệt; khi đó dùng log class loading của JVM.

### Bật log class loading của JVM

Với JDK 9 trở lên:

```bash
java -Xlog:class+load=info -jar target/customer-cli.jar
```

Với JDK 8:

```bash
java -verbose:class -jar target/customer-cli.jar
```

Output có thể rất dài. Lọc theo tên class nghi ngờ bằng `grep`, `Select-String` hoặc công cụ log của môi trường. Xác nhận class được nạp từ JAR nào và classloader nào định nghĩa nó.

### Kiểm tra executable JAR của Spring Boot

Executable JAR của Spring Boot thường chứa dependency lồng trong `BOOT-INF/lib/`. Liệt kê các thư viện đã đóng gói:

```bash
jar tf target/customer-cli.jar | grep 'BOOT-INF/lib/'
```

Trong PowerShell:

```powershell
jar tf .\target\customer-cli.jar | Select-String 'BOOT-INF/lib/'
```

Tìm các JAR có tên/version đáng ngờ. Kiểm tra cả thư mục `lib/` của gói phát hành, Docker image và launcher script. Một executable JAR đúng không giúp ích nếu người dùng thực tế đang chạy một JAR cũ hoặc launcher trỏ tới thư mục khác.

### Kiểm tra method có trong JAR bằng javap

Khi `NoSuchMethodError` chỉ rõ class và method, dùng `javap` trên JAR nghi ngờ để xem chữ ký thực tế:

```bash
javap -classpath path/to/library.jar -p -s com.example.transport.RequestClient
```

`-p` hiển thị cả member không public; `-s` hiển thị JVM descriptor. So sánh descriptor với method mà caller đã biên dịch để xác định version API nào đang được nạp.

## Bước 5: sửa nguyên nhân thay vì ép version

Sau khi tìm ra nhánh dependency gây conflict, chọn một cách sửa phù hợp:

1. Dùng đúng Spring Boot BOM/parent cho thế hệ Spring Shell đang chạy.
2. Đặt một version Spring Shell nhất quán cho starter và các module liên quan.
3. Bỏ version override của Spring Framework/Spring Boot nếu không có yêu cầu đã kiểm chứng.
4. Nâng thư viện cũ đang kéo dependency không tương thích lên release tương thích.
5. Nếu cần exclusion, chỉ loại dependency chuyển tiếp đã xác định và khai báo replacement đúng scope/version.
6. Bảo đảm dependency cần ở runtime không bị đặt thành `provided`, `test` hoặc `compileOnly`.
7. Loại bỏ JAR copy thủ công, classpath cũ trong launcher và dependency trùng trong thư mục triển khai.
8. Build lại artifact từ cấu hình đã sửa và kiểm tra nội dung gói.

### Exclude dependency chỉ khi biết dependency thay thế

Ví dụ một thư viện cũ kéo theo module Spring không phù hợp. Có thể exclude dependency đó khỏi nhánh cũ, nhưng chỉ sau khi xác định một version tương thích khác sẽ được cung cấp ở runtime:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>2.1.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclusion chỉ bỏ một cạnh dependency trong graph; nó không tự thêm thư viện thay thế. Nếu không còn dependency nào cung cấp `spring-context` phù hợp, ứng dụng có thể chuyển từ `NoSuchMethodError` sang `ClassNotFoundException` hoặc `NoClassDefFoundError`.

### Không sửa bằng cách thêm JAR bất kỳ vào lib/

Chép thêm một JAR mới vào thư mục `lib/` hoặc `BOOT-INF/lib/` có thể làm classloader nạp một bản khác và che triệu chứng trên một máy. Nếu archive chứa hai JAR có cùng class, kết quả phụ thuộc thứ tự/classloader và khó tái hiện. Hãy sửa dependency graph, rebuild archive và xác minh chỉ có một định nghĩa class phù hợp trong runtime.

## Bước 6: làm sạch build và xác minh artifact thực tế

Sau khi thay đổi dependency:

```bash
./mvnw clean verify
java -jar target/customer-cli.jar version
```

Hoặc với Gradle:

```bash
./gradlew clean build
java -jar build/libs/customer-cli.jar version
```

Đường dẫn artifact phụ thuộc tên/version dự án. Dùng đúng JAR vừa được build, không chạy file cũ trong thư mục release hoặc cache IDE.

Kiểm tra thêm:

- Dependency tree không còn version divergence ngoài ngoại lệ đã được ghi nhận.
- Runtime classpath có đầy đủ dependency cần thiết.
- Executable JAR chứa đúng nested libraries.
- `CodeSource`/class loading log cho thấy class được nạp từ JAR mong muốn.
- Command khởi động, `help`, `version` và command gây lỗi đều chạy được.
- Test chạy với cùng runtime configuration như artifact phát hành.

Không xóa toàn bộ Maven/Gradle cache như bước đầu tiên. `clean` loại output build cũ của dự án; cache chỉ nên được xử lý khi có bằng chứng artifact cache bị hỏng hoặc repository cung cấp metadata sai.

## Các tình huống đặc biệt

### Chạy được trong IDE nhưng lỗi khi dùng java -jar

IDE có thể dùng classpath từ module compile/test khác với executable JAR. Kiểm tra dependency scope, `runtimeClasspath`, nested `BOOT-INF/lib` và đường dẫn artifact được launcher sử dụng. Đừng kết luận rằng IDE đã chứng minh runtime package đúng.

### Chạy được bằng java -jar nhưng lỗi trong container

Container có thể dùng image cũ, volume mount ghi đè thư mục `lib/`, hoặc command `ENTRYPOINT` trỏ tới artifact khác. Kiểm tra image digest, file JAR thực tế, Java runtime và class loading origin bên trong container.

### ClassCastException với cùng tên class ở hai phía

Thông báo như `com.example.Type cannot be cast to com.example.Type` thường chỉ ra hai định nghĩa class có cùng tên nhưng được định nghĩa bởi hai classloader khác nhau. Kiểm tra `Class.getClassLoader()` của cả hai object, loại bỏ JAR duplicate và xem lại ranh giới plugin/application server.

### NoClassDefFoundError: Could not initialize class

Tìm exception đầu tiên trong log. Một lỗi đọc cấu hình, thiếu native library, exception trong static initializer hoặc lỗi dependency khi khởi tạo có thể khiến class initialization thất bại. Sau đó JVM báo class không thể được khởi tạo; chỉ thêm dependency theo tên class trong thông báo cuối có thể không giải quyết được nguyên nhân ban đầu.

### Lỗi chỉ xuất hiện sau khi nâng Spring Shell 3 lên 4

Spring Shell 4 có thay đổi nền tảng và API lớn. Migration guide yêu cầu Boot 4+/Framework 7 và khuyên nâng lên Spring Shell 3.4.x mới nhất trước khi chuyển. Thực hiện migration theo giai đoạn, cập nhật starter/module, sửa package/API đã thay đổi, rồi chạy compile và runtime test. Không giữ một phần Spring Framework 6 trong khi phần khác đã lên Framework 7.

## Ma trận lỗi và hướng xử lý

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| `NoSuchMethodError` trong Spring Shell/Spring Framework | JAR thực sự cung cấp class và method descriptor | Đồng bộ Spring Shell/Boot/Framework; bỏ version override hoặc JAR cũ |
| `ClassNotFoundException` khi dùng `Class.forName()` | Tên class và classloader thực hiện load | Sửa tên/provider hoặc thêm dependency vào đúng runtime classpath |
| `NoClassDefFoundError` khi tạo bean | Dependency runtime và scope/exclusion | Thêm dependency cần thiết vào runtime; kiểm tra nested JAR |
| `NoClassDefFoundError: Could not initialize class` | Exception đầu tiên trong static initialization | Sửa nguyên nhân khởi tạo ban đầu và khởi động lại process sạch |
| `AbstractMethodError` | Interface và implementation được nạp từ version nào | Cập nhật implementation cùng API version |
| `NoSuchFieldError` | JAR runtime có field nào và caller cần field nào | Đồng bộ version chứa class và caller |
| `ClassCastException: X cannot be cast to X` | Classloader và CodeSource của hai class | Loại bỏ duplicate JAR hoặc sửa ranh giới classloader |
| `UnsupportedClassVersionError` | Java version dùng build và Java runtime | Nâng runtime hoặc build target phù hợp |
| Build pass nhưng executable JAR lỗi | `runtimeClasspath` và `BOOT-INF/lib` | Sửa scope, packaging và kiểm tra artifact sau build |
| Chỉ container lỗi | Image/JAR/volume/ENTRYPOINT thực tế | Rebuild image và xác nhận đúng artifact được khởi chạy |

## Checklist chẩn đoán

1. Ghi lại exception đầu tiên và class/method được nêu.
2. Xác định lỗi là `NoSuchMethodError`, `ClassNotFoundException`, `NoClassDefFoundError` hay một loại khác.
3. Xác nhận Spring Shell, Spring Boot, Spring Framework và JDK version thực tế.
4. Kiểm tra Maven `dependency:tree -Dverbose` hoặc Gradle `dependencies`/`dependencyInsight`.
5. So sánh compile classpath với runtime classpath.
6. Xác định JAR thực sự nạp class bằng `CodeSource` hoặc JVM class-loading log.
7. Kiểm tra nested JAR, thư mục `lib/`, launcher, Docker image và classpath tùy chỉnh.
8. Đồng bộ version qua BOM/constraints; bỏ override không cần thiết.
9. Chỉ exclude dependency khi đã cung cấp replacement đúng runtime scope.
10. Build sạch, kiểm tra executable artifact và chạy lại command gây lỗi.
11. Thêm dependency convergence/version conflict checks để phát hiện vấn đề sớm.
12. Ghi lại version matrix và lý do ngoại lệ nếu phải override dependency.

Khi gặp lỗi linkage, dependency graph cho biết build tool đã chọn gì; class-loading diagnostics cho biết JVM thực sự dùng gì. So sánh hai nguồn đó giúp xác định chính xác thư viện gây lỗi. Sau đó đồng bộ version theo BOM của nền tảng, sửa scope/exclusion hoặc loại bỏ JAR trùng, rồi xác minh lại executable artifact trên đúng môi trường triển khai.

## Tài liệu tham khảo

- [Spring Shell 3.3 — Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): nền tảng Spring Boot 3.3/Spring Framework 6 và dependency starter.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): yêu cầu Spring Boot 4+/Spring Framework 7 và thứ tự nâng cấp từ Spring Shell 3.4.x.
- [Spring Boot 3.4 — Build Systems](https://docs.spring.io/spring-boot/3.4/reference/using/build-systems.html): curated dependency list, BOM và cảnh báo override dependency versions.
- [Spring Boot 3.4 — Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/3.4/gradle-plugin/managing-dependencies.html): import BOM qua Gradle plugin hoặc native BOM support.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): hiển thị dependency graph, omitted nodes và các output format.
- [Apache Maven Enforcer — Dependency Convergence](https://maven.apache.org/components/enforcer/enforcer-rules/dependencyConvergence.html): phát hiện cùng artifact được yêu cầu ở nhiều version.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies` và `dependencyInsight` để xác định selected version và origin.
- [Gradle — Dependency Constraints and Conflict Resolution](https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html): cách Gradle giải quyết version/capability conflicts và constraints.
- [Java SE — NoSuchMethodError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NoSuchMethodError.html): method được gọi không còn tồn tại trong class runtime.
- [Java SE — ClassNotFoundException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassNotFoundException.html): class không tìm thấy khi nạp theo tên.
- [Java SE — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NoClassDefFoundError.html): JVM/classloader không tìm thấy định nghĩa class lúc runtime.
- [Java SE — LinkageError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LinkageError.html): nhóm lỗi khi dependency class thay đổi không tương thích sau khi caller được biên dịch.
