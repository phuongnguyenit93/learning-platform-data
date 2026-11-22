# Vai trò của classpath.idx và thứ tự nạp thư viện trong Spring Boot Loader

## 1. Mục tiêu bài học

Một ứng dụng Spring Boot có thể chạy bình thường trong IDE hoặc bằng `mvn spring-boot:run` / `gradle bootRun` nhưng phát sinh lỗi sau khi được đóng gói và chạy bằng `java -jar`. Một nguyên nhân cần xem xét là **classpath khi phát triển** không nhất thiết giống **classpath do Spring Boot Loader tạo ra từ các thư viện JAR lồng nhau**.

Trong một executable Spring Boot JAR, các thành phần quan trọng thường nằm ở:

- `BOOT-INF/classes/`: class và resource của **ứng dụng**.
- `BOOT-INF/lib/`: các **dependency JAR** được đóng gói để sử dụng khi chạy.
- `META-INF/MANIFEST.MF`: xác định launcher và main class của ứng dụng.
- `org/springframework/boot/loader/...`: các class của Spring Boot Loader.
- `BOOT-INF/classpath.idx` (nếu có): chỉ mục **thứ tự đưa các nested JAR vào classpath**.
- `BOOT-INF/layers.idx` (nếu có): thông tin **chia lớp archive phục vụ Docker/OCI**, không phải thứ tự nạp thư viện.

**Điểm chính:** `classpath.idx` không phải một dependency declaration, không phải BOM hay file xác định phiên bản, và không phải nhật ký class nào **đã thực sự được JVM nạp**. Nó mô tả **thứ tự vị trí tìm kiếm** khi Boot Loader chuẩn bị classpath cho executable archive.

### Bảng phân biệt trước khi thực hành

| Câu hỏi | Đọc ở đâu? | Không kết luận sai |
|---|---|---|
| Thư viện nào được Maven/Gradle chọn, phiên bản nào? | `dependency:tree` hoặc `runtimeClasspath` | Không suy chỉ từ `classpath.idx` |
| JAR nào thật sự được đóng vào artifact? | `jar tf app.jar` tìm `BOOT-INF/lib/` | Không suy chỉ từ `pom.xml` |
| Thư viện lồng nhau được đưa vào classpath theo thứ tự nào? | `BOOT-INF/classpath.idx` | Không lấy thứ tự dòng `jar tf` làm thay thế |
| Class cụ thể đang đến từ JAR nào? | `CodeSource`, classloader, `-Xlog:class+load` | Không khẳng định chắc chỉ từ index |
| Khi nào một class được JVM nạp? | Theo nhu cầu của JVM và classloader thực tế | Không phải “toàn bộ JAR đứng trước được nạp trước” |
| Thư viện nằm trong Docker layer nào? | `BOOT-INF/layers.idx` | Layer order khác classpath order |

## 2. Vì sao Spring Boot cần loader cho nested JAR?

Java launcher chuẩn có thể chạy `java -jar app.jar` nếu manifest của JAR có entrypoint phù hợp. Nhưng Java launcher **không tự biến mỗi JAR bên trong một JAR thành một classpath entry**. Spring Boot cung cấp loader để giải quyết việc này, giúp phân phối một executable JAR giữ nguyên thư viện lồng nhau thay vì phải giải nén toàn bộ class thành một shaded JAR.

Sơ đồ một executable JAR **minh họa**:

```text
index-lab-0.0.1-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/
│   └── springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/indexlab/IndexLabApplication.class
    ├── lib/
    │   ├── spring-boot-3.5.16.jar
    │   ├── commons-lang3-3.17.0.jar
    │   └── ... (nhiều JAR khác)
    ├── classpath.idx
    └── layers.idx
```

Tên file và vị trí thành phần bổ sung của **archive thật** phụ thuộc plugin, version, dependency resolution và cấu hình. Không dùng sơ đồ như bằng chứng rằng một build cụ thể có chính xác những entry trên.

Trong Spring Boot 3.x, `META-INF/MANIFEST.MF` thường có:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.indexlab.IndexLabApplication
```

`Main-Class` chỉ bootstrap **JarLauncher**. `Start-Class` chỉ entrypoint ứng dụng. Spring Boot Loader thiết lập classpath phù hợp, sau đó gọi phương thức `main` của ứng dụng.

Các launcher thường gặp:

- **`JarLauncher`**: sử dụng `BOOT-INF/classes/` và các JAR trong `BOOT-INF/lib/`.
- **`WarLauncher`**: dành cho executable WAR, với `WEB-INF/classes/`, `WEB-INF/lib/` và `WEB-INF/lib-provided/` tùy packaging.
- **`PropertiesLauncher`**: cho phép cấu hình đường dẫn thêm như `loader.path` theo đặc tính riêng.

**Không áp dụng máy móc hành vi của JarLauncher lên mọi layout/launcher.** Nếu kiểm tra một WAR, một kiểu launcher tùy biến hoặc image đã giải nén lớp, hãy xác định manifest và cách ứng dụng thực sự được khởi chạy trước.

### Plain JAR khác executable JAR

| Plain Java JAR | Spring Boot executable JAR |
|---|---|
| Class của module thường ở root package, ví dụ `com/example/App.class` | Class ứng dụng ở `BOOT-INF/classes/com/example/App.class` |
| Không tự mang mọi dependency runtime | Thường mang nested JAR ở `BOOT-INF/lib/` |
| Thường được dùng như thư viện/classpath entry thông thường | Được thiết kế để Spring Boot Loader khởi chạy bằng `java -jar` |
| Không nhất thiết có classpath index | Có thể có `BOOT-INF/classpath.idx` |

Nếu Gradle tạo cả `myapp-plain.jar` và `myapp.jar`, hãy kiểm tra đúng **Boot executable artifact**. Trong Maven, `spring-boot-maven-plugin:repackage` thường thay thế JAR thường bằng bản executable khi cấu hình tương ứng.

## 3. classpath.idx là gì? Định dạng chuẩn

`classpath.idx` là một **danh sách đường dẫn các nested JAR kèm thứ tự**. File được đặt tại `BOOT-INF/classpath.idx` trong executable archive tương thích Spring Boot Loader. Theo tài liệu Spring Boot, cả executable JAR và executable WAR có thể cung cấp classpath index.

Ví dụ archive có hai thư viện:

```text
BOOT-INF/lib/dependency-a.jar
BOOT-INF/lib/dependency-b.jar
```

Index **có thể** ghi:

```text
- "BOOT-INF/lib/dependency-b.jar"
- "BOOT-INF/lib/dependency-a.jar"
```

Điều đó nói rằng khi file được loader sử dụng, `dependency-b.jar` được thêm vào classpath **trước** `dependency-a.jar`. Đây là ví dụ độc lập; **không** nói rằng thứ tự luôn ngược alphabet.

### Quy tắc viết một mục

1. Dòng bắt đầu với **dấu trừ rồi dấu cách**: `- `.
2. Đường dẫn nested JAR được bao bởi **dấu nháy kép**.
3. Tên là **entry path trong archive**, ví dụ `BOOT-INF/lib/example-1.0.jar`, không phải `C:\libs\example.jar` hay `group:artifact:version`.
4. Thứ tự các dòng là thứ tự JAR cần được đưa vào classpath.
5. Cú pháp chỉ **tương thích YAML**: Spring Boot **không dùng một YAML parser tổng quát** để đọc index. Không tùy ý bỏ dấu nháy, thay bằng YAML object, JSON hoặc thêm cấu trúc khác.

Ví dụ các dòng **không phải dạng chuẩn**:

```text
BOOT-INF/lib/alpha.jar
- BOOT-INF/lib/beta.jar
- "org.example:gamma:1.0"
```

Trong ví dụ sai: dòng 1 không có `- "..."`; dòng 2 thiếu dấu nháy; dòng 3 là Maven coordinates chứ không phải nested archive path.

**Index thường do Spring Boot Maven/Gradle build plugin tự tạo.** Khi phiên bản dependency thay đổi, file trong archive phải phản ánh tên JAR mới. Vì vậy không nên duy trì thủ công một index tĩnh bên ngoài quy trình build rồi chỉ “nhét lại” vào executable JAR cuối.

### Index không thay dependency resolver

Các công việc mà `classpath.idx` **không thực hiện**:

- Không tải thư viện từ Maven Central hoặc repository khác.
- Không thêm JAR thiếu vào `BOOT-INF/lib`.
- Không chọn giữa hai phiên bản dependency khi Maven/Gradle giải quyết đồ thị.
- Không tự loại thư viện thừa.
- Không thay scope `runtime`/`provided` hay Gradle configuration.
- Không biến JAR executable thành JAR thư viện bình thường.
- Không bảo đảm rằng class ở JAR trước sẽ được JVM khởi tạo trước.

## 4. Trong trường hợp nào Boot Loader đọc index?

**Giới hạn phạm vi quan trọng nhất** từ tài liệu Spring Boot: classpath index chỉ được dùng khi **executable archive được chạy bằng `java -jar`**. Nó không được dùng khi chạy trực tiếp trong IDE hay các lệnh development-run thông thường.

| Cách khởi chạy | Boot Loader sử dụng `classpath.idx` của executable archive? | Giải thích |
|---|---|---|
| `java -jar target/app.jar` | Có, nếu archive/index hợp lệ và launcher hỗ trợ | Chạy qua executable archive và Boot Loader |
| `java -jar build/libs/app.jar` | Có, với artifact `bootJar` được đóng gói phù hợp | Giống trên |
| `./mvnw spring-boot:run` | **Không** | Plugin Maven thiết lập classpath development |
| `./gradlew bootRun` | **Không** | Task Gradle dùng main source set và runtime classpath |
| Run main class trong IDE | **Không** | IDE quyết định classpath của project |
| `java -cp ... com.example.App` | **Không tự đọc index** | Launcher chuẩn theo `-cp`, không tự mở nested libraries của Boot archive |
| WAR triển khai tới servlet container truyền thống | **Không dùng cơ chế Boot `java -jar`** | Container có chính sách classloader riêng |

Vì vậy lỗi “IDE chạy được nhưng `java -jar` thất bại” **có thể** liên quan đến classpath index, nhưng cũng có thể do missing runtime dependency, resource không được package, cấu hình profile, khác phiên bản JDK, đường dẫn file hoặc classloader của container.

### Vì sao java -cp app.jar không tương đương java -jar app.jar?

Trong executable JAR, class ứng dụng nằm dưới `BOOT-INF/classes`, còn các thư viện dưới `BOOT-INF/lib`. Java launcher chuẩn với:

```bash
java -cp target/app.jar com.example.App
```

không tự coi `BOOT-INF/classes` và mọi JAR lồng nhau là các classpath entry. Cách khởi chạy thông thường cho executable Boot archive là:

```bash
java -jar target/app.jar
```

Chỉ đọc `classpath.idx` của archive không có ý nghĩa nếu ứng dụng thực tế chạy bằng `bootRun`, IDE hay một cơ chế tùy chỉnh không dùng chỉ mục đó.

## 5. Thứ tự classpath và thứ tự nạp class không giống nhau

Hãy xem hai thư viện:

```text
a-lib.jar  -> chứa com/example/Feature.class
b-lib.jar  -> cũng chứa com/example/Feature.class
```

Nếu cùng tên class xuất hiện trên cùng **classpath tuyến tính**, JAR được tìm trước thường cung cấp định nghĩa class. Đây là điểm mà thứ tự các nested JAR có thể quan trọng.

Tuy nhiên **thứ tự classpath là thứ tự tìm kiếm, không phải thời gian tải từng class**:

- JVM có thể chỉ tải class khi chúng thực sự được sử dụng.
- ClassLoader thường **delegate** cho parent loader theo quy tắc của nó; class từ JDK hoặc parent loader không bị chi phối đơn giản bởi vị trí một nested JAR.
- Một class đã được loader định nghĩa không tự đổi nguồn khi đường tìm kiếm được thay sau đó.
- Nhiều classloader khác nhau có thể định nghĩa class cùng tên thành hai kiểu khác nhau.
- Java module path, agents, ServiceLoader, container classloader hay devtools restart loader có thể thay đổi hành vi so với classpath phẳng.

Một cách nói đúng:

> “`classpath.idx` xác định thứ tự **nested JAR được thêm vào classpath** để Boot Loader tìm class/resource.”

Cách nói **sai**:

> “JVM sẽ nạp toàn bộ class trong JAR dòng thứ nhất, rồi mới đến JAR dòng thứ hai.”

### Tác động đến resources và SPI

Nhiều JAR có thể chứa cùng resource `config/default.properties`, cùng tên `META-INF/MANIFEST.MF`, hay nhiều descriptor `META-INF/services/<interface>`. Khi gọi `ClassLoader.getResource` hoặc `getResources`, thứ tự đường tìm kiếm **có thể** ảnh hưởng vị trí trả về. `ServiceLoader` có quy tắc nạp provider riêng; thứ tự classpath có thể tác động nhưng **không** thay thế metadata `META-INF/services`.

Một file tài nguyên không được tìm thấy khi packaged JAR chạy có thể đến từ:
- Resource không được đóng gói vào `BOOT-INF/classes` hoặc JAR dependency.
- Một JAR khác có resource cùng tên và được tìm thấy trước.
- API sử dụng context classloader khác với classloader bạn đang kiểm tra.
- Path resource sai chữ hoa/chữ thường hoặc cách load từ filesystem bị nhầm với classpath.

## 6. Ví dụ chạy được trên Java 17: đảo thứ tự hai JAR cùng chứa một class

Đây là **mô hình Java thuần**, không phải ứng dụng Spring Boot, để quan sát tác động của **thứ tự tìm class** một cách có thể xác minh độc lập.

Tạo các file:

```text
classpath-order-lab/
├── src/alpha/lib/Marker.java
├── src/beta/lib/Marker.java
└── src/app/lab/app/OrderProbe.java
```

Nội dung `src/alpha/lib/Marker.java`:

```java
package lib;

public final class Marker {
    private Marker() {}

    public static String origin() {
        return "alpha";
    }
}
```

Nội dung `src/beta/lib/Marker.java`:

```java
package lib;

public final class Marker {
    private Marker() {}

    public static String origin() {
        return "beta";
    }
}
```

Hai file này **cố ý định nghĩa cùng tên `lib.Marker`**, để làm thí nghiệm. **Không** giữ xung đột kiểu này trong ứng dụng production.

Nội dung `src/app/lab/app/OrderProbe.java`:

```java
package lab.app;

import lib.Marker;

public final class OrderProbe {
    public static void main(String[] args) {
        System.out.println(Marker.origin());
    }
}
```

Trên Linux/macOS, đứng ở root ví dụ và dùng JDK 17+:

```bash
mkdir -p out/alpha out/beta out/app

javac -d out/alpha src/alpha/lib/Marker.java
javac -d out/beta src/beta/lib/Marker.java

jar --create --file out/alpha.jar -C out/alpha .
jar --create --file out/beta.jar -C out/beta .

javac -cp out/alpha.jar -d out/app src/app/lab/app/OrderProbe.java

# alpha.jar trước beta.jar:
java -cp "out/app:out/alpha.jar:out/beta.jar" lab.app.OrderProbe

# beta.jar trước alpha.jar:
java -cp "out/app:out/beta.jar:out/alpha.jar" lab.app.OrderProbe
```

**Stdout chính xác** của lệnh `java` thứ nhất:

```text
alpha
```

**Stdout chính xác** của lệnh `java` thứ hai:

```text
beta
```

Class `OrderProbe` được biên dịch **một lần**, còn classpath khi chạy thay đổi. Cả hai bản `lib.Marker` có cùng method signature, nên không phát sinh lỗi linkage; giá trị trả về chứng minh JAR được chọn khác nhau.

Windows PowerShell dùng dấu chấm phẩy trong classpath:

```powershell
New-Item -ItemType Directory -Force out/alpha, out/beta, out/app | Out-Null
javac -d out/alpha src/alpha/lib/Marker.java
javac -d out/beta src/beta/lib/Marker.java
jar --create --file out/alpha.jar -C out/alpha .
jar --create --file out/beta.jar -C out/beta .
javac -cp out/alpha.jar -d out/app src/app/lab/app/OrderProbe.java

java -cp "out/app;out/alpha.jar;out/beta.jar" lab.app.OrderProbe
java -cp "out/app;out/beta.jar;out/alpha.jar" lab.app.OrderProbe
```

Hai lệnh cuối lần lượt in `alpha` và `beta`. **Bài học áp dụng cho Boot:** nếu hai nested JAR vô tình chứa cùng tên class/resource, thứ tự mà Boot Loader thiết lập có thể thay đổi nguồn được chọn. Tuy nhiên thí nghiệm JDK với `-cp` **không chứng minh** hành vi cụ thể của một Boot archive; cần nhìn chính `classpath.idx` và classloader runtime trong artifact đó.

## 7. Ví dụ Spring Boot Maven hoàn chỉnh: tạo executable archive và đọc index

Ví dụ pin Spring Boot **3.5.16**, Java **17+** để có kết quả tái lập theo phiên bản. Không mặc định đây là bản mới nhất ở mọi thời điểm. Cần Maven 3.6.3+ hoặc Maven Wrapper của dự án, JDK và quyền truy cập repository khi cache chưa đủ.

Cấu trúc:

```text
index-lab/
├── pom.xml
└── src/main/java/com/example/indexlab/IndexLabApplication.java
```

### 7.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>index-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
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

`spring-boot-starter-parent` quản lý dependencies/plugins và cấu hình `repackage` trong lifecycle. `spring-boot-starter` thực sự thêm các Spring dependencies; một BOM/parent **không tự thêm** chúng nếu không khai báo. `commons-lang3` được chọn với phiên bản cụ thể để có một nested JAR dễ nhận diện.

### 7.2. Java class hoàn chỉnh

`src/main/java/com/example/indexlab/IndexLabApplication.java`:

```java
package com.example.indexlab;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class IndexLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(IndexLabApplication.class, args);
    }

    @Bean
    CommandLineRunner probe() {
        return args -> {
            System.out.println("Loader demo ready");
            System.out.println("Capitalize = " + StringUtils.capitalize("spring"));
        };
    }
}
```

Ứng dụng dùng `spring-boot-starter` (không có web starter), nên chạy console và kết thúc sau khi các thành phần phù hợp hoàn tất. Chạy tại root ví dụ, với **một** trong hai kiểu build:

```bash
# Chỉ khi dự án đã có Maven Wrapper:
./mvnw clean package

# Nếu không có wrapper, dùng Maven đã cài:
mvn clean package

# Chạy archive đã được repackage:
java -jar target/index-lab-0.0.1-SNAPSHOT.jar
```

Hai dòng **do ứng dụng in ra** chính xác:

```text
Loader demo ready
Capitalize = Spring
```

Các log Spring Boot, Maven hay JVM khác có thể xuất hiện; không khẳng định toàn bộ stdout chỉ có hai dòng. Windows PowerShell dùng `.\mvnw.cmd clean package` nếu có wrapper, hoặc `mvn clean package`.

### 7.3. Liệt kê archive và đọc index bằng công cụ JDK

Linux/macOS:

```bash
# Quan sát BOOT-INF và các thư viện có thật:
jar tf target/index-lab-0.0.1-SNAPSHOT.jar
jar tf target/index-lab-0.0.1-SNAPSHOT.jar | grep -E '^(BOOT-INF/classpath.idx|BOOT-INF/lib/)'

# Trích duy nhất file index ra thư mục tạm, không sửa archive:
mkdir -p inspect
cd inspect
jar xf ../target/index-lab-0.0.1-SNAPSHOT.jar BOOT-INF/classpath.idx
cat BOOT-INF/classpath.idx
cd ..
```

PowerShell:

```powershell
jar tf target/index-lab-0.0.1-SNAPSHOT.jar | Select-String 'BOOT-INF/(classpath\.idx|lib/)'

New-Item -ItemType Directory -Force inspect | Out-Null
Push-Location inspect
jar xf ../target/index-lab-0.0.1-SNAPSHOT.jar BOOT-INF/classpath.idx
Get-Content BOOT-INF/classpath.idx
Pop-Location
```

`jar` đi kèm JDK; `jar xf <archive> <entry>` **trích file** vào thư mục đang đứng, không sửa artifact gốc. Khi archive không có file index, lệnh `Get-Content`/`cat` sẽ không tìm được file; lúc đó quay lại kiểm tra loại artifact, plugin và manifest chứ không đoán nội dung.

Những mục cần đối chiếu:

1. Có `BOOT-INF/classes/com/example/indexlab/IndexLabApplication.class` không?
2. Có `BOOT-INF/lib/commons-lang3-3.17.0.jar` không?
3. Có `BOOT-INF/classpath.idx` không? Nếu có, dòng chỉ tên thư viện với dạng `- "BOOT-INF/lib/...jar"` hay không?
4. Có những dependency bắc cầu nào do Spring Boot starter mang vào?
5. `META-INF/MANIFEST.MF` có `Main-Class` và `Start-Class` phù hợp không?
6. Khi `java -jar`, ứng dụng có thật sự chạy và in hai dòng expected không?

**Không khẳng định thứ tự tất cả thư viện của ví dụ từ trước khi chạy build.** Thứ tự phụ thuộc resolution, cách plugin tạo index và cấu hình reproducible build. Đối với một artifact cụ thể, nội dung index được trích ra là bằng chứng đúng nhất.

### 7.4. Đọc dependency graph song song

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
```

Dùng `mvn` thay `./mvnw` khi không có wrapper. `dependency:tree` nói **thư viện nào được chọn và đi vào qua đâu**; `jar tf` nói **thư viện nào có trong executable archive**; `classpath.idx` nói **thứ tự nested JAR trên classpath**. Không thể thay thế cả ba phép kiểm tra bằng một lệnh duy nhất.

## 8. Gradle: so bootRun với bootJar

Nếu dùng Gradle thay cho Maven, dùng **cùng class `IndexLabApplication.java`** ở trên với hai file Groovy DSL sau.

`settings.gradle`:

```groovy
rootProject.name = 'index-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Gradle `platform(...)` sử dụng BOM cho dependency constraints; Spring Boot plugin phối hợp với Java plugin tạo `bootJar`/`bootRun`. Khi dự án **đã có Gradle Wrapper**:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3

# Không dùng classpath.idx:
./gradlew bootRun

# Tạo executable archive:
./gradlew clean bootJar
jar tf build/libs/index-lab-0.0.1-SNAPSHOT.jar

# Có thể dùng index được đóng trong archive:
java -jar build/libs/index-lab-0.0.1-SNAPSHOT.jar
```

Windows dùng `.\gradlew.bat` thay `./gradlew`. Nếu chưa có wrapper cần tạo bằng một bản Gradle đã cài tương thích Spring Boot 3.5; file `gradlew` không tự xuất hiện chỉ bằng cách viết build script.

Để đọc classpath index của Gradle artifact, thay đường dẫn `target/index-lab-...jar` ở mục 7.3 bằng `build/libs/index-lab-...jar`. Đừng cho rằng thứ tự các dòng trong `build.gradle` hoặc output `dependencies` sẽ **luôn** là thứ tự trong `classpath.idx`; nhất là nếu build được cấu hình tái lập.

### Maven và Gradle: ba bước quan sát tương ứng

| Mục tiêu | Maven | Gradle |
|---|---|---|
| Chạy dev, không dùng index của archive | `./mvnw spring-boot:run` | `./gradlew bootRun` |
| Xem resolved dependency | `dependency:tree` | `dependencies --configuration runtimeClasspath` |
| Build executable archive | `./mvnw package` (repackage đã cấu hình) | `./gradlew bootJar` |
| Kiểm tra archive | `jar tf target/*.jar` (chọn đúng file) | `jar tf build/libs/*.jar` (chọn đúng file) |
| Chạy qua Boot Loader | `java -jar target/actual.jar` | `java -jar build/libs/actual.jar` |

Với dự án nhiều module, lệnh Gradle `:service-app:bootJar` hoặc Maven `-pl :service-app` chỉ đúng khi module thực sự tồn tại. Một root `build/libs` khác không có nghĩa test ở module con đã tạo executable JAR của module đó.

## 9. Reproducible builds: tại sao thứ tự có thể là alphabet?

Tài liệu Spring Boot xác nhận hai hành vi quan trọng:

1. Index do Maven/Gradle plugins tạo thường phản ánh classpath build tool dùng để chạy/test.
2. **Khi bật reproducible builds**, entry trong `classpath.idx` được **sắp theo alphabet**.

Hệ quả: **đừng** dùng thứ tự khai báo dependency trong build script như một hợp đồng cố định cho thứ tự runtime JAR ở mọi build. Cũng đừng nhầm **thứ tự entry trong ZIP** (lệnh `jar tf`) với **thứ tự classpath** (file index).

Index minh họa đã sắp xếp theo tên:

```text
- "BOOT-INF/lib/alpha-1.0.jar"
- "BOOT-INF/lib/beta-2.0.jar"
- "BOOT-INF/lib/omega-1.0.jar"
```

Đây là file ví dụ, **không phải nội dung chắc chắn** của một app bất kỳ. Dù sắp theo alphabet, nó vẫn chỉ quyết định thứ tự **tìm** class/resource khi cần, không “nạp hết alpha rồi beta rồi omega”.

Nếu một project chỉ chạy được khi `old-api.jar` đứng trước `new-api.jar`, đó là dấu hiệu cấu hình có xung đột và dễ vỡ. Cách sửa bền vững là quản lý phiên bản, loại transitive dependency không cần, không dựa vào thứ tự ngẫu nhiên của archive.

## 10. Xác nhận class thực sự được tải từ đâu

Khi nghi một class bị lấy từ JAR không mong muốn, có thể in **CodeSource**. Đoạn sau là mã chèn **bên trong một method Java**, không phải file độc lập:

```java
Class<?> type = org.apache.commons.lang3.StringUtils.class;
var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();

System.out.println(source == null
        ? "Unknown source"
        : source.getLocation());
```

Kết quả có thể là URL mô tả JAR lồng nhau, đường dẫn local hoặc không có code source, tùy JVM và classloader; **không** ghi một stdout cố định khi chưa chạy.

Với JDK 17, bật logging cho class loading:

```bash
java -Xlog:class+load=info -jar target/index-lab-0.0.1-SNAPSHOT.jar
```

Lưu ý `-Xlog:class+load=info` phải đứng **trước `-jar`** vì đây là JVM option; lệnh trên có thể in rất nhiều dòng. Lọc log theo một class cụ thể, ví dụ `org.apache.commons.lang3.StringUtils`, thay vì cố đọc toàn bộ.

Nếu nghi có **resource trùng tên**, trong method Java có thể dùng:

```java
var loader = Thread.currentThread().getContextClassLoader();
var urls = loader.getResources("META-INF/MANIFEST.MF");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

Đoạn này có thể ném `IOException` từ `getResources`; method chứa nó phải khai báo hoặc xử lý checked exception. `getResources` có thể trả nhiều URL, còn `getResource` trả một resource theo cơ chế của loader. Không nhầm chúng với file thông thường trên filesystem.

### Nếu có classloader khác

Spring Boot Devtools, các application server, test runner, IDE agent hoặc plugins có thể tạo **nhiều classloader**. Hai class cùng tên nhưng khác classloader có thể bị coi là **hai kiểu khác nhau**, dẫn đến `ClassCastException`. Khi đó cần in `SomeClass.class.getClassLoader()`, code source và classloader của object liên quan, không chỉ nhìn index. Parent delegation cũng có thể làm một class được tìm từ parent trước các nested JAR.

## 11. Phân biệt classpath.idx và layers.idx

Hai file có tên gần nhau và đôi khi cùng nằm trong `BOOT-INF/`:

| Đặc điểm | `classpath.idx` | `layers.idx` |
|---|---|---|
| Mục đích | Thứ tự nested JAR thêm vào classpath | Phân chia các thành phần archive thành Docker/OCI layers |
| Dữ liệu | Danh sách đường dẫn JAR | Tên layer và các file/thư mục thuộc layer |
| Kích hoạt có ý nghĩa | Khi Boot Loader khởi chạy bằng `java -jar` | Khi công cụ build/extract/container image xử lý layers |
| Hình thức | Mỗi dòng `- "BOOT-INF/lib/x.jar"` | Tên lớp rồi các đường dẫn con có thụt đầu dòng |
| Không làm gì | Không chọn version/không thêm JAR | Không điều khiển thứ tự JVM tìm class |

Ví dụ `layers.idx` **minh họa**:

```yaml
- "dependencies":
  - "BOOT-INF/lib/dependency-a.jar"
  - "BOOT-INF/lib/dependency-b.jar"
- "application":
  - "BOOT-INF/classes/"
  - "META-INF/"
```

Cấu trúc nội dung này phục vụ layer extraction/OCI caching. **Đổi thứ tự layer không phải cách chỉnh classpath order.** Docker layer order và Java classpath search order thuộc hai vấn đề độc lập.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Giả thuyết cần kiểm chứng | Thao tác phù hợp |
|---|---|---|
| Không tìm được `BOOT-INF/classpath.idx` | Đang mở plain JAR, plugin/layout không tạo index | Kiểm tra manifest, `BOOT-INF/lib`, plugin `repackage`/`bootJar`; index là tùy chọn |
| File có nhưng thiếu tên JAR cần thiết | Dependency không được package, bị exclude/scope sai | So index với `jar tf` và resolved dependency tree |
| IDE/`bootRun` ổn, `java -jar` lỗi | Classpath development khác runtime archive | Kiểm tra package, code source, index, runtime profiles |
| `ClassNotFoundException` | Class không có trên runtime classpath | Tìm đúng dependency, scope/configuration và JAR đóng gói |
| `NoClassDefFoundError` | Class thiếu hoặc lỗi khởi tạo/liên kết | Đọc `Caused by`, kiểm tra source JAR và initialization |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary conflict giữa version compile/run | Xác định JAR thực nạp, sửa dependency graph |
| Resource bị lấy từ JAR khác | Hai JAR có resource trùng tên | `getResources`, điều tra classloader và resource path |
| `ServiceConfigurationError` | Service provider thiếu/sai hoặc không tương thích | Kiểm tra `META-INF/services`, JAR, provider và classloader |
| `ClassCastException` với class tên giống nhau | Classloader khác nhau hoặc kiểu không tương thích | Xem classloader của hai phía và code source |
| Thay `classpath.idx` nhưng `spring-boot:run` không đổi | Chạy dev không đọc index | Chạy đúng executable JAR để kiểm thử |
| Đổi `layers.idx` không đổi runtime classpath | Layer index không phải classpath index | Dùng đúng khái niệm và giải quyết dependency |
| Thứ tự classpath khác với build script | Resolution/build config/reproducible sorting | Đọc index thật trong file archive cuối |
| Sửa JAR bằng tay rồi chạy lỗi | Zip metadata, nested JAR format, chữ ký/checksum hoặc index không hợp lệ | Trở về build từ nguồn và đóng gói lại bằng plugin |

**Đừng tự kết luận “classpath.idx gây lỗi” chỉ vì file tồn tại.** Rất nhiều lỗi sau đóng gói xuất phát từ dependency thiếu, profile khác, resource không được copy, Java version, hoặc cách container khởi chạy.

## 13. Quy trình chẩn đoán tối thiểu, có thể lặp lại

Khi một executable Spring Boot JAR chạy khác IDE, làm tuần tự:

1. **Xác nhận đúng artifact**: JAR nào được ứng dụng/container thực sự chạy? Có bị dùng nhầm `-plain.jar` hoặc bản cache không?
2. **Đọc manifest**: `Main-Class`, `Start-Class` và launcher có đúng loại archive không?
3. **Liệt kê archive**: dùng `jar tf`, kiểm tra `BOOT-INF/classes` và `BOOT-INF/lib`.
4. **Đọc classpath index**: trích `BOOT-INF/classpath.idx` nếu có; đối chiếu từng tên với file JAR thật.
5. **Đọc dependency graph**: kiểm tra Maven `dependency:tree`/Gradle `runtimeClasspath` và mọi exclusion/version override.
6. **So sánh đường khởi chạy**: `java -jar` khác IDE/`spring-boot:run`/`bootRun` về cách dựng classpath; không lấy kết quả một kiểu để suy kiểu khác.
7. **Định vị class/resource**: `CodeSource`, classloader và `-Xlog:class+load`, `getResources` khi cần.
8. **Phân loại lỗi**: missing class, binary incompatibility, duplicate class, wrong config hay launcher khác.
9. **Sửa trong build configuration**, không sửa index trực tiếp bên trong JAR đã phát hành; build lại từ nguồn.
10. **Kiểm thử artifact đóng gói thật** trên JDK/container mục tiêu, rồi chạy lại suite cần thiết.

### Checklist cuối bài

- [ ] Biết vì sao Spring Boot phải dùng Loader để đọc nested JAR.
- [ ] Phân biệt `Main-Class` = launcher và `Start-Class` = ứng dụng.
- [ ] Biết `BOOT-INF/classpath.idx` chứa **đường dẫn JAR theo thứ tự**, không chứa tên class.
- [ ] Biết `java -jar` là đường chạy liên quan index, còn IDE/`bootRun`/`spring-boot:run` không dùng index trong archive.
- [ ] Không nhầm thứ tự classpath với thứ tự thực thi/tải class theo thời gian.
- [ ] Biết reproducible builds có thể sắp xếp index theo alphabet.
- [ ] Không nhầm `classpath.idx` với `layers.idx`.
- [ ] Đã đối chiếu index, archive contents và dependency tree của **cùng artifact**.
- [ ] Đã xác minh code source/classloader khi nghi xung đột class/resource.
- [ ] Đã sửa dependency/packaging bền vững thay vì vá chỉ mục bằng tay.

**Kết luận:** `classpath.idx` là cơ chế giúp Spring Boot Loader giữ một thứ tự classpath cho **nested runtime JARs** của executable archive. Nó đặc biệt hữu ích khi cần giải thích sự khác nhau giữa `java -jar` và cách chạy development, hoặc truy các vấn đề trùng class/resource. Nhưng file index **không** quản lý dependency, không ép JVM nạp toàn bộ class theo thứ tự dòng và không thay thế xác minh nguồn class thực tế.

### Tài liệu chính thức

- [Spring Boot 3.5 — Nested JARs và Classpath Index](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.5 — Launching Executable Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html)
- [Spring Boot 3.5 — Maven Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Gradle Packaging](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Oracle JDK 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
