# JAR thư viện với executable JAR của ứng dụng

Khi học Spring Boot, bạn thường thấy hai file cùng có đuôi `.jar` nhưng được sử dụng rất khác nhau. Một file được thêm vào dependency để ứng dụng khác gọi các class bên trong; file còn lại có thể chạy bằng lệnh `java -jar app.jar`, tự khởi động Spring ApplicationContext và sử dụng các dependency đã được đóng gói.

Sự khác nhau này liên quan đến **mục đích của artifact**, **cấu trúc bên trong JAR**, **classpath**, **manifest** và **cơ chế launcher của Spring Boot**. Nếu không phân biệt, bạn dễ gặp những lỗi như “no main manifest attribute”, “ClassNotFoundException”, “Could not find or load main class”, hoặc một thư viện tưởng như đã được thêm vào project nhưng Spring không tìm thấy class.

Bài học thuộc chương **Chạy và đóng gói** của **Spring Boot Fundamentals**. Chúng ta sẽ lần lượt phân biệt JAR thư viện (library/plain JAR) với Spring Boot executable JAR, xem cách tạo bằng Gradle và Maven, tổ chức project nhiều module, quan sát nội dung artifact và xác định đúng loại JAR cần phát hành.

## 1. Trước hết: JAR là gì?

**JAR** (Java ARchive) là định dạng lưu trữ thường dùng để đóng gói các file `.class`, resource và metadata của ứng dụng Java. Về cơ bản, nó dựa trên cấu trúc ZIP và có thể chứa file:

```text
META-INF/MANIFEST.MF
com/example/demo/OrderService.class
com/example/demo/Order.class
application.properties
```

Cùng một định dạng `.jar` có thể phục vụ nhiều mục đích:

- Là thư viện được ứng dụng khác sử dụng trên classpath.
- Là artifact chứa một chương trình Java có phương thức `main`.
- Là executable JAR được Spring Boot đóng gói cùng các dependency cần thiết.
- Là artifact chứa hạ tầng hoặc annotation processor dùng trong quá trình build.
- Là một JAR được tạo theo chiến lược shading/assembly của công cụ khác.

Vì vậy, **đuôi `.jar` không đủ để kết luận file có thể chạy độc lập**. Cần xem cấu trúc, manifest, classpath và cách build.

### 1.1. Hai mục tiêu khác nhau

Một **JAR thư viện** thường trả lời câu hỏi:

> “Module khác có thể sử dụng những class, interface và resource nào?”

Một **executable JAR của Spring Boot** thường trả lời câu hỏi:

> “Làm sao chạy cả ứng dụng từ artifact này, với entry point và các dependency phù hợp?”

Sự khác nhau về mục tiêu dẫn tới cách đóng gói khác nhau.

## 2. JAR thư viện (plain/library JAR)

Giả sử bạn có một thư viện xử lý giá tiền:

```java
package com.example.pricing;

import java.math.BigDecimal;

public class PriceCalculator {

    public BigDecimal calculateTotal(
            BigDecimal unitPrice,
            int quantity
    ) {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

Sau khi compile và đóng gói thành `pricing-lib.jar`, cấu trúc phổ biến là:

```text
pricing-lib.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        └── pricing/
            └── PriceCalculator.class
```

Class `PriceCalculator` nằm trực tiếp dưới đường dẫn package tương ứng trong **root classpath của JAR**.

Ứng dụng khác có thể đưa JAR lên classpath và dùng:

```java
import com.example.pricing.PriceCalculator;
```

### 2.1. Thư viện không nhất thiết có main method

Một thư viện thường không có:

```java
public static void main(String[] args)
```

và manifest không cần khai báo entry point `Main-Class`.

Điều đó không phải lỗi. Thư viện được thiết kế để **được nạp bởi một ứng dụng khác**, không phải tự chạy như một process độc lập.

### 2.2. Dependency của thư viện có được đóng gói vào đó không?

Với tác vụ `jar` của Java/Gradle/Maven thông thường, artifact chủ yếu chứa những class và resource do module tạo ra, **không tự nhét toàn bộ dependency JAR vào bên trong**.

Ví dụ:

```text
pricing-lib.jar
  └── PriceCalculator.class

dependency-a.jar
dependency-b.jar
```

Nếu `PriceCalculator` cần class từ dependency A khi chạy, ứng dụng tiêu thụ phải có dependency A trên runtime classpath theo cơ chế build/dependency management phù hợp.

Một file `pom.xml` hoặc Gradle module metadata có thể mô tả dependency cho công cụ quản lý dependency. Bản thân JAR thông thường không tự biết cách tải những dependency chưa có ở runtime.

### 2.3. Có phải mọi JAR thư viện đều không chạy được?

Không. Một JAR bình thường có thể chứa `main` và được cấu hình manifest `Main-Class`. Khi đó lệnh `java -jar` có thể chạy entry point này.

Nhưng điều đó **không tự biến nó thành Spring Boot executable JAR**. Nếu ứng dụng cần thư viện bên ngoài, bạn vẫn phải bố trí runtime classpath hoặc đóng gói theo chiến lược phù hợp.

Cụm “JAR thư viện” ở đây mô tả **vai trò và cách tổ chức artifact**, không phải một ràng buộc tuyệt đối của định dạng JAR.

## 3. Spring Boot executable JAR là gì?

Spring Boot cung cấp cơ chế đóng gói ứng dụng thành một artifact có thể chạy trực tiếp:

```bash
java -jar orders-app.jar
```

Một executable JAR tiêu chuẩn do Spring Boot plugin tạo thường chứa:

- Các class/resource của ứng dụng.
- Những dependency JAR cần thiết ở runtime dưới dạng **nested JARs**.
- Các class của Spring Boot launcher/loader.
- Manifest khai báo launcher và application start class.
- Có thể có thêm metadata cho layers hoặc classpath index, tùy cấu hình và phiên bản.

Cấu trúc điển hình:

```text
orders-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/orders/OrdersApplication.class
│   │   ├── com/example/orders/OrderService.class
│   │   └── application.yml
│   ├── lib/
│   │   ├── spring-boot-*.jar
│   │   ├── spring-context-*.jar
│   │   ├── spring-core-*.jar
│   │   ├── logging-*.jar
│   │   └── pricing-lib-*.jar
│   └── layers.idx                 (có thể có)
└── org/springframework/boot/loader/
    └── ...                        (launcher/loader classes)
```

Các tên JAR và đường dẫn bổ sung phụ thuộc phiên bản Spring Boot cùng runtime dependencies thực tế.

### 3.1. Hai thư mục quan trọng nhất

**`BOOT-INF/classes/`** chứa class và resource của ứng dụng chính.

Ví dụ:

```text
BOOT-INF/classes/com/example/orders/OrdersApplication.class
BOOT-INF/classes/application.yml
```

**`BOOT-INF/lib/`** chứa runtime dependency JARs được đóng gói.

Ví dụ:

```text
BOOT-INF/lib/spring-context-*.jar
BOOT-INF/lib/jackson-databind-*.jar
BOOT-INF/lib/pricing-lib-1.0.0.jar
```

Không phải mọi executable JAR đều có đúng những dependency đó. Nếu ứng dụng không có HTTP server hoặc không dùng Jackson, các thư viện tương ứng có thể không xuất hiện.

### 3.2. Vì sao dependency lại nằm dưới dạng nested JAR?

Thay vì giải nén class của tất cả dependency rồi trộn vào một package tree khổng lồ, Spring Boot thường giữ từng dependency là một JAR riêng nằm bên trong executable JAR.

Ví dụ:

```text
orders-app.jar
  └── BOOT-INF/lib/pricing-lib-1.0.0.jar
        └── com/example/pricing/PriceCalculator.class
```

Kiểu tổ chức này có các lợi ích:

- Giữ cấu trúc mỗi thư viện tương đối độc lập.
- Giảm xung đột do giải nén và gộp file resource không đúng cách.
- Giúp xác định dependency nào được đóng gói.
- Hỗ trợ cơ chế Spring Boot launcher nạp dependency khi chạy.

Tuy nhiên, nested JARs **không được JVM classpath mặc định đọc như các JAR rời bên ngoài**. Spring Boot cần launcher riêng để thiết lập class loading phù hợp.

## 4. So sánh trực tiếp hai loại JAR

| Tiêu chí | JAR thư viện thông thường | Spring Boot executable JAR |
|---|---|---|
| Mục tiêu | Được project khác sử dụng | Khởi chạy ứng dụng |
| Class chính của module | Thường nằm tại root theo package | Nằm dưới `BOOT-INF/classes/` |
| Dependency | Thường không đóng gói trực tiếp | Thường nằm ở `BOOT-INF/lib/` |
| Entry point | Không bắt buộc | Có launcher và ứng dụng start class |
| `java -jar` | Không bảo đảm chạy được | Là cách chạy tiêu chuẩn |
| Dùng làm dependency | Phù hợp | Thường không phù hợp |
| Tạo với Gradle | `jar` | `bootJar` |
| Tạo với Maven | `maven-jar-plugin`/`package` | `spring-boot-maven-plugin:repackage` |
| Class loading | JVM và build-tool classpath thông thường | Spring Boot loader xử lý cấu trúc nested JAR |
| Nơi hay phát hành | Maven repository, thư viện dùng chung | CI artifact, server, container image |

Điểm dễ nhầm là **hai loại đều là file `.jar`**. Nếu chỉ nhìn tên file, bạn không biết nó thuộc cột nào.

## 5. java -cp và java -jar khác nhau ở đâu?

Hai cách chạy này không tương đương.

### 5.1. Chạy với -cp

```bash
java -cp "app-classes:pricing-lib.jar" com.example.Main
```

`-cp` (classpath) chỉ định những vị trí JVM cần tìm class và resource.

Ở Windows, dấu phân tách classpath thường là dấu chấm phẩy:

```powershell
java -cp "app-classes;pricing-lib.jar" com.example.Main
```

Ví dụ trên giả định `app-classes` chứa `com/example/Main.class` và `pricing-lib.jar` chứa những class được sử dụng.

Khi bạn thêm một library JAR vào classpath, JVM có thể tìm class theo package path nằm trong root JAR.

### 5.2. Chạy với -jar

```bash
java -jar orders-app.jar
```

JVM đọc thông tin entry point từ `META-INF/MANIFEST.MF` của JAR được chỉ định rồi chạy main class tương ứng.

Ở chế độ `-jar`, các thiết lập user classpath thông thường qua `-cp` hoặc biến `CLASSPATH` không được áp dụng theo cách bạn có thể kỳ vọng cho JAR đó. Những dependency cần thiết phải được bố trí theo cơ chế executable JAR hoặc manifest/classpath thiết kế phù hợp.

Đối với Spring Boot executable JAR, entry point là **Boot launcher**, và launcher này tiếp tục nạp ứng dụng.

### 5.3. Vì sao java -jar library.jar thường thất bại?

Nếu manifest của library JAR không có `Main-Class`, bạn có thể thấy:

```text
no main manifest attribute, in pricing-lib.jar
```

Không phải vì `PriceCalculator` sai hay thư viện không hợp lệ. Đơn giản là JAR không khai báo một chương trình để JVM khởi chạy.

Nếu library JAR có `Main-Class` nhưng thiếu runtime dependencies, nó vẫn có thể lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError` khi chạy.

### 5.4. Vì sao không dùng java -cp để chạy Boot JAR như thư viện?

Class ứng dụng bên trong Spring Boot executable JAR nằm ở:

```text
BOOT-INF/classes/com/example/orders/OrdersApplication.class
```

chứ không nằm ở root:

```text
com/example/orders/OrdersApplication.class
```

JVM classpath thông thường không xem `BOOT-INF/classes` như root classpath chỉ vì bạn thêm file executable JAR vào `-cp`.

Tương tự, `BOOT-INF/lib/*.jar` là nested JARs mà JVM classpath mặc định không tự mở để tìm các dependency.

Do đó, lệnh kiểu:

```bash
java -cp orders-app.jar com.example.orders.OrdersApplication
```

không phải cách chạy chuẩn của Spring Boot executable JAR và có thể thất bại vì không tìm thấy application class.

Hãy dùng:

```bash
java -jar orders-app.jar
```

hoặc chạy bằng Gradle/Maven plugin, IDE hay một classpath đã được dựng theo đúng định dạng thông thường.

## 6. Vai trò của META-INF/MANIFEST.MF

Manifest là file metadata có thể được dùng để mô tả entry point và một số thuộc tính của JAR.

Với JAR thư viện đơn giản, manifest có thể rất ít thông tin:

```text
Manifest-Version: 1.0
```

Với Spring Boot executable JAR, manifest có thể chứa nội dung tương tự:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.orders.OrdersApplication
Spring-Boot-Version: ...
Spring-Boot-Classes: BOOT-INF/classes/
Spring-Boot-Lib: BOOT-INF/lib/
```

Tên launcher trong `Main-Class` thay đổi theo phiên bản: những dòng Spring Boot cũ sử dụng đường dẫn như `org.springframework.boot.loader.JarLauncher`, còn các dòng mới hơn có thể sử dụng `org.springframework.boot.loader.launch.JarLauncher`. Không nên hard-code một tên launcher cụ thể mà không kiểm tra version.

### 6.1. Main-Class khác Start-Class

Với executable JAR của Spring Boot:

- `Main-Class` thường trỏ tới **Spring Boot launcher**.
- `Start-Class` trỏ tới **main class của ứng dụng**.

Ví dụ:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.orders.OrdersApplication
```

Khi dùng `java -jar`, JVM gọi main của launcher. Launcher thiết lập class loading theo cấu trúc Boot rồi gọi main của application class.

Đây là lý do manifest có thể không đặt `OrdersApplication` trực tiếp vào `Main-Class` như một plain executable JAR tự viết.

### 6.2. Luồng khởi động rút gọn

```text
java -jar orders-app.jar
          │
          ▼
JVM đọc META-INF/MANIFEST.MF
          │
          ▼
Spring Boot JarLauncher
          │
          ▼
Thiết lập classpath từ:
  BOOT-INF/classes/
  BOOT-INF/lib/*.jar
          │
          ▼
Nạp Start-Class của ứng dụng
          │
          ▼
OrdersApplication.main(args)
          │
          ▼
SpringApplication.run(...)
          │
          ▼
ApplicationContext khởi động
```

Sơ đồ này mô tả mục đích của từng bước, không phải toàn bộ chi tiết nội bộ class loader.

## 7. Kiểm tra cấu trúc JAR trên máy

Không cần đoán loại artifact. Bạn có thể xem các entry bên trong bằng JDK tool `jar`.

### 7.1. Liệt kê entry

```bash
jar tf pricing-lib.jar
```

Ví dụ output:

```text
META-INF/
META-INF/MANIFEST.MF
com/example/pricing/PriceCalculator.class
```

Với Boot JAR:

```bash
jar tf orders-app.jar
```

Có thể thấy:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/orders/OrdersApplication.class
BOOT-INF/lib/spring-core-...jar
BOOT-INF/lib/pricing-lib-...jar
org/springframework/boot/loader/...
```

Từ output, dấu hiệu nhận diện quan trọng nhất là `BOOT-INF/classes` và `BOOT-INF/lib`.

### 7.2. Lọc output trên Linux/macOS

```bash
jar tf orders-app.jar | grep "BOOT-INF/"
```

### 7.3. Lọc output trong PowerShell

```powershell
jar tf orders-app.jar | Select-String "BOOT-INF/"
```

Cách kiểm tra này hữu ích khi làm việc với Windows IDE, CI artifact hoặc một JAR do người khác cung cấp.

### 7.4. Đọc manifest

Có thể giải nén manifest vào một thư mục tạm:

```bash
mkdir inspect-jar
cd inspect-jar
jar xf ../orders-app.jar META-INF/MANIFEST.MF
```

Sau đó đọc:

```bash
cat META-INF/MANIFEST.MF
```

Trên PowerShell:

```powershell
Get-Content .\META-INF\MANIFEST.MF
```

Lưu ý lệnh `jar xf` ghi file ra thư mục hiện tại, nên hãy làm việc trong một thư mục tạm, không giải nén thẳng vào project root khi không cần thiết.

## 8. Gradle: jar và bootJar

Trong dự án dùng Gradle, hai task thường gặp là:

```text
jar
bootJar
```

### 8.1. Task jar

Task `jar` do Java plugin của Gradle cung cấp. Nó tạo JAR thông thường từ compiled classes và resources của module.

Ví dụ thư viện:

```groovy
plugins {
    id 'java-library'
}
```

Chạy:

```bash
./gradlew jar
```

Artifact thường nằm trong:

```text
build/libs/
```

Ví dụ:

```text
build/libs/pricing-lib-1.0.0.jar
```

Cấu trúc:

```text
com/example/pricing/PriceCalculator.class
META-INF/MANIFEST.MF
```

Task `jar` phù hợp với module thư viện.

### 8.2. Task bootJar

Khi Spring Boot Gradle plugin được áp dụng cho application module, task `bootJar` tạo executable JAR theo layout của Boot.

Chạy:

```bash
./gradlew bootJar
```

Artifact cũng thường nằm trong:

```text
build/libs/
```

Ví dụ:

```text
build/libs/orders-app-1.0.0.jar
```

Cấu trúc có `BOOT-INF/classes`, `BOOT-INF/lib` và launcher.

Chạy:

```bash
java -jar build/libs/orders-app-1.0.0.jar
```

### 8.3. Tên artifact có thể khác

Đừng giả định mỗi dự án luôn tạo ra chính xác:

```text
build/libs/app.jar
```

Tên file phụ thuộc vào:

- `project.name`.
- `version`.
- `archiveBaseName`.
- `archiveClassifier`.
- `archiveVersion`.
- Cách cấu hình Gradle task.
- Version của Spring Boot Gradle plugin.

Hãy xem `build/libs` để chọn đúng artifact.

### 8.4. Vì sao có file -plain.jar?

Trong nhiều phiên bản/cấu hình Spring Boot Gradle plugin, khi cả `jar` và `bootJar` được bật, plain JAR có thể nhận classifier `plain` để tránh trùng tên với executable JAR.

Ví dụ:

```text
build/libs/orders-app-1.0.0.jar
build/libs/orders-app-1.0.0-plain.jar
```

Thông thường:

- `orders-app-1.0.0.jar`: Boot executable JAR.
- `orders-app-1.0.0-plain.jar`: plain JAR.

Đây là quy ước phụ thuộc phiên bản/config của build, **không phải luật của JAR format**. Luôn kiểm tra bằng `jar tf` và manifest khi chưa chắc.

### 8.5. Cấu hình tên bootJar

Ví dụ Gradle Groovy DSL:

```groovy
tasks.named('bootJar') {
    archiveFileName = 'orders-app.jar'
}
```

Sau build, executable JAR được đặt tên cố định:

```text
build/libs/orders-app.jar
```

Cách đặt tên cố định có thể tiện cho script triển khai. Nhưng nếu bạn phát hành nhiều version song song, nên cân nhắc giữ version trong tên artifact để tránh ghi đè không chủ đích.

## 9. Gradle: module thư viện có cần Spring Boot plugin không?

Một module chỉ chứa domain models, utility, API contract hoặc reusable service implementation **không bắt buộc** phải áp dụng Spring Boot plugin.

Ví dụ module thư viện:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    // Khai báo thư viện cần thiết khi có.
}
```

Khi chạy:

```bash
./gradlew :pricing-lib:jar
```

bạn sẽ có artifact JAR thông thường.

### 9.1. Tại sao không bật bootJar cho mọi module?

Nếu mọi module đều tạo executable JAR, các module thư viện có thể:

- Không có application main class.
- Có layout `BOOT-INF/classes` không phù hợp với dependency classpath thông thường.
- Kéo dependency vào nested JAR không cần thiết.
- Khó được module khác sử dụng qua Gradle/Maven dependency.
- Khiến publication pipeline chọn nhầm artifact.

Do đó, nguyên tắc thông dụng trong multi-module project là:

> **Library module tạo plain JAR; application module tạo executable JAR.**

### 9.2. Nếu thư viện cũng dùng Spring annotations?

Một module có `@Service`, `@Configuration` hoặc `@ConfigurationProperties` vẫn có thể là JAR thư viện bình thường.

Ví dụ:

```java
package com.example.shared;

import org.springframework.stereotype.Service;

@Service
public class CurrencyConverter {
    // ...
}
```

Nó không cần trở thành executable JAR chỉ vì sử dụng annotation Spring. Module tiêu thụ phải đưa artifact lên classpath và đăng ký bean bằng component scan, `@Import`, auto-configuration hoặc cơ chế khác phù hợp.

### 9.3. Nếu module dùng Boot plugin nhưng chỉ muốn thư viện?

Một project có cấu hình build chung có thể áp dụng Boot plugin vào nhiều module. Khi module chỉ là thư viện, có thể vô hiệu hóa `bootJar` và bật `jar`:

```groovy
tasks.named('bootJar') {
    enabled = false
}

tasks.named('jar') {
    enabled = true
    archiveClassifier = ''
}
```

Đoạn này giả định task `bootJar` thực sự tồn tại vì Boot plugin đã được áp dụng. Cấu hình phù hợp phụ thuộc version/plugin và quy ước publication của project.

Nếu không có lý do để áp dụng Boot plugin ở thư viện, cách đơn giản hơn là dùng `java-library` và khai báo dependencies cần thiết.

## 10. Maven: JAR thông thường và spring-boot:repackage

Trong dự án Maven, `mvn package` thường kích hoạt packaging lifecycle. Với project `<packaging>jar</packaging>`, Maven JAR Plugin có thể tạo JAR thông thường từ compiled classes/resources.

Ví dụ:

```xml
<project>
    ...
    <packaging>jar</packaging>
    ...
</project>
```

Artifact thường nằm tại:

```text
target/pricing-lib-1.0.0.jar
```

### 10.1. Vai trò của Spring Boot Maven Plugin

Spring Boot Maven Plugin cung cấp goal:

```text
spring-boot:repackage
```

Goal này lấy một JAR/WAR đã được tạo và đóng gói lại theo executable layout của Spring Boot, với launcher và những dependency cần thiết.

Một cấu hình plugin phổ biến:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Version của plugin phải được quản lý bằng Spring Boot parent, dependency/plugin management hoặc khai báo version cụ thể theo project.

Sau:

```bash
mvn package
```

application artifact có thể trở thành executable JAR nếu `repackage` được liên kết và chạy thành công.

### 10.2. Maven parent không đủ để kết luận đã repackage

Một project dùng `spring-boot-starter-parent` và dependencies của Boot vẫn cần xem plugin executions thực tế. Tùy cấu hình parent, plugin được khai báo và lifecycle, `repackage` có thể hoặc không được chạy.

Không nên đoán chỉ từ việc source có `@SpringBootApplication`. Hãy kiểm tra:

- Effective POM/plugin configuration.
- Build log của `repackage`.
- Nội dung artifact trong `target`.
- Manifest và `BOOT-INF` entries.

### 10.3. Giữ cả plain JAR và executable JAR bằng classifier

Một số ứng dụng hoặc build pipeline cần cả:

- Plain JAR để sử dụng như artifact thông thường.
- Executable JAR để chạy.

Spring Boot Maven Plugin có thể dùng classifier cho bản được repackage:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Kết quả minh họa:

```text
target/orders-app-1.0.0.jar
target/orders-app-1.0.0-exec.jar
```

Artifact thứ hai là executable variant, còn artifact chính có thể tiếp tục là plain JAR theo cấu hình phù hợp.

Nếu sử dụng publishing, hãy xác nhận classifier và artifact nào được attach/deploy. Đừng để application executable JAR bị publish nhầm làm thư viện tiêu thụ.

## 11. Ví dụ nhiều module: thư viện dùng chung và ứng dụng Spring Boot

Ta xây dựng một project gồm:

- `greeting-lib`: thư viện Java thông thường.
- `greeting-app`: ứng dụng Spring Boot sử dụng thư viện.

### 11.1. Cấu trúc tổng thể

```text
greeting-project/
├── settings.gradle
├── build.gradle
├── greeting-lib/
│   ├── build.gradle
│   └── src/main/java/com/example/greeting/
│       └── GreetingFormatter.java
└── greeting-app/
    ├── build.gradle
    ├── src/main/java/com/example/app/
    │   └── GreetingApplication.java
    └── src/main/resources/
        └── application.yml
```

### 11.2. settings.gradle

```groovy
rootProject.name = 'greeting-project'

include 'greeting-lib'
include 'greeting-app'
```

### 11.3. Thư viện: greeting-lib/build.gradle

```groovy
plugins {
    id 'java-library'
}
```

Class trong thư viện:

```java
package com.example.greeting;

public class GreetingFormatter {

    public String format(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Module này không cần `@SpringBootApplication` hoặc phương thức `main`.

### 11.4. Ứng dụng: greeting-app/build.gradle

Ví dụ phần cấu hình của module ứng dụng:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':greeting-lib')
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Đoạn này giả định version Spring Boot plugin, repositories và dependency management đã được cấu hình tại root project hoặc theo build setup tương ứng. Nó thể hiện mối quan hệ giữa các module, không phải toàn bộ một file Gradle có thể chạy độc lập trong mọi project.

### 11.5. Ứng dụng sử dụng thư viện

```java
package com.example.app;

import com.example.greeting.GreetingFormatter;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class GreetingApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(GreetingApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }

    @Bean
    CommandLineRunner greetingRunner(
            GreetingFormatter formatter
    ) {
        return args -> System.out.println(
                formatter.format("Minh")
        );
    }
}
```

Tại đây, ứng dụng **đăng ký `GreetingFormatter` thành bean bằng `@Bean`**. Thư viện không bắt buộc phải biết gì về Spring Boot.

### 11.6. Build từng module

Build thư viện:

```bash
./gradlew :greeting-lib:jar
```

Build executable JAR của ứng dụng:

```bash
./gradlew :greeting-app:bootJar
```

Artifact minh họa:

```text
greeting-lib/build/libs/greeting-lib-1.0.0.jar
greeting-app/build/libs/greeting-app-1.0.0.jar
```

Tên file thực tế phụ thuộc cấu hình version/classifier.

### 11.7. Bên trong executable JAR

Khi xem `greeting-app` executable JAR, bạn sẽ gặp:

```text
BOOT-INF/classes/com/example/app/GreetingApplication.class
BOOT-INF/lib/greeting-lib-1.0.0.jar
BOOT-INF/lib/spring-boot-*.jar
BOOT-INF/lib/spring-context-*.jar
...
```

Điều đó minh họa quan hệ:

```text
greeting-lib.jar
      │
      │ dependency
      ▼
greeting-app
      │
      │ bootJar
      ▼
greeting-app-executable.jar
      ├── application classes
      └── nested greeting-lib.jar
```

### 11.8. Chạy ứng dụng

```bash
java -jar greeting-app/build/libs/greeting-app-1.0.0.jar
```

Phần output từ runner có thể là:

```text
Xin chào, Minh!
```

Bạn không chạy riêng `greeting-lib.jar`. Chính application executable JAR sử dụng library JAR được đóng gói ở runtime.

## 12. Vì sao không nên dùng Spring Boot executable JAR như dependency?

Đây là một quy tắc quan trọng khi thiết kế multi-module project.

Giả sử project A tạo:

```text
service-a-exec.jar
└── BOOT-INF/classes/com/example/a/MyService.class
```

Project B thêm file đó theo kiểu dependency thông thường, ví dụ đặt executable JAR trên classpath.

JVM và các build tools thường tìm:

```text
com/example/a/MyService.class
```

ngay từ root JAR. Nhưng class thực tế ở:

```text
BOOT-INF/classes/com/example/a/MyService.class
```

Vì vậy, công cụ tiêu thụ JAR như một library JAR thông thường có thể không thấy class.

### 12.1. Vấn đề không chỉ nằm ở main method

Ngay cả khi executable JAR có `Start-Class` đúng và chạy được, nó vẫn không phải một thư viện thuận tiện để project khác import class.

Sự khác biệt nằm ở **layout và cơ chế classpath**.

### 12.2. Nếu ứng dụng khác cần dùng chung logic thì sao?

Nên trích phần dùng chung vào một module tạo plain/library JAR:

```text
shared-domain.jar
      ▲                ▲
      │                │
  orders-app       billing-app
      │                │
      ▼                ▼
orders-exec.jar   billing-exec.jar
```

Hai ứng dụng cùng sử dụng library JAR, nhưng mỗi ứng dụng có executable JAR riêng với entry point và dependency phù hợp.

Đây là cách tách trách nhiệm rõ ràng và dễ phát hành hơn nhiều so với việc application A phải phụ thuộc executable JAR của application B.

### 12.3. Nếu cần chia sẻ API nhưng không muốn trùng code?

Có thể tạo các module:

- `shared-api`: interface, DTO, public contracts.
- `shared-core`: implementation dùng chung, nếu thích hợp.
- `orders-app`: ứng dụng/entry point thứ nhất.
- `billing-app`: ứng dụng/entry point thứ hai.

Các module shared tạo plain JAR; application modules tạo executable JAR. Chúng có thể được phát hành qua Maven repository nội bộ hoặc dùng Gradle project dependency trong mono-repo.

## 13. Spring Boot starter và auto-configuration thường là library JAR

Một starter/integration library có thể có các class Spring và metadata để Spring Boot tự khám phá cấu hình khi người dùng thêm dependency.

Ví dụ:

```text
acme-mail-autoconfigure.jar
├── META-INF/
│   └── spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── com/acme/mail/autoconfigure/
    └── MailAutoConfiguration.class
```

Đây vẫn có thể là **JAR thư viện thông thường**. Nó không cần `java -jar` hay một SpringApplication main class riêng.

### 13.1. Auto-configuration được khám phá như thế nào?

Khi ứng dụng Spring Boot thêm thư viện vào runtime classpath, Spring Boot có thể đọc resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

và tìm những auto-configuration class được liệt kê.

Ví dụ:

```text
com.acme.mail.autoconfigure.MailAutoConfiguration
```

Sau đó, Boot xét các conditions như `@ConditionalOnClass`, `@ConditionalOnProperty` và `@ConditionalOnMissingBean` để quyết định bean definitions có được đăng ký không.

**Auto-configuration trong library JAR không làm JAR đó trở thành executable JAR.** Nó chỉ cung cấp cấu hình có thể được ứng dụng khác nạp.

### 13.2. Phân biệt starter với executable app

| Artifact | Vai trò |
|---|---|
| `spring-boot-starter-web` | Tập hợp dependency phục vụ web stack; không phải ứng dụng web tự chạy |
| `acme-mail-autoconfigure.jar` | Cung cấp auto-configuration cho ứng dụng tiêu thụ |
| `acme-mail-starter.jar` | Thường kết hợp dependencies và auto-configuration |
| `orders-app.jar` đã chạy `bootJar` | Executable JAR để khởi chạy process ứng dụng |

Tên có “spring-boot” không chứng minh artifact là executable. Hãy nhìn nhiệm vụ của artifact.

## 14. Executable JAR của Boot khác shaded/uber JAR thế nào?

“Fat JAR”, “uber JAR” và “executable JAR” đôi khi bị dùng như từ đồng nghĩa, nhưng cách đóng gói có thể rất khác.

### 14.1. Spring Boot executable JAR giữ nested dependencies

```text
BOOT-INF/lib/library-a.jar
BOOT-INF/lib/library-b.jar
BOOT-INF/classes/...
```

Các dependency JAR vẫn là những archive riêng bên trong JAR chính.

### 14.2. Shaded/uber JAR có thể hợp nhất class

Công cụ như Maven Shade hoặc Gradle Shadow thường có thể giải nén nội dung dependency rồi gộp vào một archive:

```text
com/example/app/Application.class
org/example/liba/Helper.class
org/example/libb/Utility.class
META-INF/services/...
```

Ưu điểm của cách shading là có một classpath root thông thường và có thể hỗ trợ relocation để tránh một số xung đột package.

Nhưng việc gộp archive phải xử lý resource trùng tên, chữ ký JAR và service loader metadata đúng cách. Không được chỉ sao chép/ghi đè file tùy tiện.

### 14.3. Sự khác biệt chính

| Vấn đề | Spring Boot executable JAR | Shaded JAR thông thường |
|---|---|---|
| Dependency packaging | Nested JARs | Nhiều class/resources được hợp nhất |
| Class loading | Spring Boot loader | Thường dùng classpath JVM thông thường |
| Package layout | `BOOT-INF/classes` và `BOOT-INF/lib` | Class thường ở root theo package |
| Resource merge | Ít phải gộp trực tiếp nội dung từng dependency | Thường phải cấu hình transformer/merge |
| Entry point | Boot launcher và Start-Class | Tùy manifest/Main-Class được cấu hình |

Một shaded JAR cũng có thể chạy bằng `java -jar` nếu có main manifest hợp lệ. Nhưng nó không phải cùng layout với `bootJar`.

### 14.4. Không tự tạo Boot JAR bằng cách zip các file lại

Nếu bạn tự zip `BOOT-INF/classes` và `BOOT-INF/lib` nhưng không đưa launcher/manifest đúng, `java -jar` có thể thất bại.

Hãy dùng plugin `bootJar` hoặc `spring-boot:repackage` phù hợp. Chúng biết cách tạo layout và metadata tương thích với Spring Boot loader của phiên bản đang dùng.

## 15. Trong executable JAR có mọi dependency không?

Thông thường Spring Boot executable JAR chứa những dependencies thuộc runtime classpath mà build plugin lựa chọn. Tuy vậy, không nên khẳng định “mọi dependency trong project đều nằm trong JAR”.

Có nhiều phạm vi dependency:

- `implementation`: dùng khi compile, thường được đưa vào runtime classpath.
- `runtimeOnly`: chỉ cần lúc chạy.
- `compileOnly`: thường không được đưa vào runtime classpath mặc định.
- `testImplementation`: dành cho test, không nên được đóng gói vào production artifact.
- Maven `provided` hoặc các scope khác: cách đóng gói tùy plugin và packaging type.

Một số dependency hoặc configuration có quy tắc riêng của Spring Boot plugin. Hãy kiểm tra artifact cuối thay vì suy đoán chỉ từ tên scope.

### 15.1. Ví dụ driver database

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Ở ứng dụng JDBC sử dụng PostgreSQL, driver thuộc runtime dependency và thường cần có trong executable JAR.

Sau build, kiểm tra:

```text
BOOT-INF/lib/postgresql-*.jar
```

Nếu thiếu driver ở runtime, bạn có thể gặp lỗi không tìm thấy driver/class hoặc DataSource không khởi tạo được.

### 15.2. Dependency không đóng gói có thể vẫn cần ngoài ứng dụng

Executable JAR có dependencies cần thiết để chạy Java code, nhưng không có nghĩa mọi yếu tố môi trường đã nằm trong artifact.

Ứng dụng vẫn có thể cần:

- Java runtime/JDK tương thích.
- Database server đang hoạt động.
- Network access.
- Secrets và environment variables.
- External configuration.
- Quyền đọc/ghi file hoặc thư mục.
- Message broker, cache server hoặc API khác.

“Self-contained” trong ngữ cảnh Boot executable JAR chủ yếu là **đóng gói Java application code cùng dependencies**, không phải đóng gói cả hệ điều hành và mọi dịch vụ bên ngoài.

## 16. Khi Spring Boot tự tìm main class

Một application module thường có:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Build plugin có thể xác định start class từ các class có `main` hoặc từ cấu hình người dùng.

### 16.1. Khi project có nhiều main classes

Giả sử module có:

```text
com.example.orders.OrdersApplication
com.example.orders.AdminToolApplication
```

Việc tự xác định main class có thể mơ hồ.

Với Spring Boot Gradle plugin, có thể cấu hình:

```groovy
springBoot {
    mainClass = 'com.example.orders.OrdersApplication'
}
```

Hoặc cấu hình task cụ thể tùy nhu cầu:

```groovy
tasks.named('bootJar') {
    mainClass = 'com.example.orders.OrdersApplication'
}
```

Sau khi build, đọc manifest để xác nhận `Start-Class` thực tế.

### 16.2. Main class không nhất thiết phải có web controller

Một Spring Boot executable JAR có thể là:

- REST API.
- Reactive web app.
- Batch/CLI application.
- Message consumer.
- Scheduler.
- Background worker.

`@SpringBootApplication` cùng `SpringApplication.run(...)` không có nghĩa phải dùng embedded web server. Loại ứng dụng phụ thuộc classpath và `WebApplicationType`.

### 16.3. Nếu build thất bại vì không tìm được main class

Một module chỉ là library có thể không có `main`. Nếu bạn cố chạy `bootJar` trên module đó, plugin có thể báo không tìm thấy main class phù hợp.

Đây thường là dấu hiệu cần phân biệt lại vai trò module:

- Library: dùng `jar`.
- Application: cung cấp main class và dùng `bootJar`.

Đừng thêm main method giả chỉ để tạo executable JAR cho thư viện, nếu thư viện không thực sự là một chương trình cần chạy.

## 17. Resources được đóng gói ở đâu và đọc như thế nào?

Thư mục Gradle/Maven thông thường:

```text
src/main/resources/
```

có thể chứa:

```text
application.yml
templates/email.html
data/default-categories.json
META-INF/services/com.example.Plugin
```

Khi tạo plain JAR, những resource này thường được đặt theo classpath root trong JAR:

```text
application.yml
templates/email.html
data/default-categories.json
```

Khi tạo Boot executable JAR, các resource thuộc application module thường nằm dưới:

```text
BOOT-INF/classes/application.yml
BOOT-INF/classes/templates/email.html
BOOT-INF/classes/data/default-categories.json
```

### 17.1. Đọc bằng classpath, không dùng đường dẫn tương đối tới source

Trong Java:

```java
try (InputStream in =
        getClass().getResourceAsStream(
                "/data/default-categories.json"
        )) {
    if (in == null) {
        throw new IllegalStateException("Resource not found");
    }

    // Đọc dữ liệu từ in.
}
```

Cách dùng classpath resource thường hoạt động cả trong IDE và executable JAR, miễn là resource được đóng gói đúng.

Không nên viết:

```java
Files.readString(
        Path.of("src/main/resources/data/default-categories.json")
);
```

và kỳ vọng nó vẫn chạy khi deploy JAR từ thư mục khác. Đường dẫn `src/main/resources` là layout của source project; nó không phải đường dẫn file có thật bên ngoài JAR sau khi build.

### 17.2. Resource trong nested library JAR

Nếu `greeting-lib.jar` chứa resource:

```text
com/example/greeting/messages.properties
```

khi nó nằm ở `BOOT-INF/lib/greeting-lib.jar`, Spring Boot launcher có thể cho class loader tìm resource của thư viện.

Ứng dụng nên dùng API classpath như `ClassLoader#getResourceAsStream` hoặc Spring `ResourceLoader`, không tự ghép đường dẫn `BOOT-INF/lib/...` để mở như file thông thường.

### 17.3. Vì sao không chuyển URL resource thành File tùy tiện?

Resource trong executable JAR/nested JAR không nhất thiết biểu diễn được bằng một `java.io.File` trên filesystem.

Ví dụ sau có thể không phù hợp sau khi đóng gói:

```java
File file = new File(
        getClass().getResource("/data/default-categories.json").toURI()
);
```

Nếu resource ở trong archive, URI không phải `file:` path thông thường.

Tốt hơn là đọc qua `InputStream` hoặc dùng Spring `Resource`:

```java
Resource resource =
        resourceLoader.getResource(
                "classpath:data/default-categories.json"
        );

try (InputStream in = resource.getInputStream()) {
    // Xử lý nội dung.
}
```

## 18. Cấu hình bên ngoài executable JAR

Một executable JAR có thể chứa `application.yml` mặc định trong `BOOT-INF/classes`, nhưng Spring Boot hỗ trợ nhiều nguồn externalized configuration.

Ví dụ:

```text
deploy/
├── orders-app.jar
└── config/
    └── application-prod.yml
```

Bạn có thể chạy với profile:

```bash
java -jar orders-app.jar --spring.profiles.active=prod
```

Hoặc chỉ định nơi bổ sung config phù hợp:

```bash
java -jar orders-app.jar --spring.config.additional-location=optional:file:./config/
```

**Không cần mở JAR rồi sửa application.yml bên trong** mỗi khi chuyển môi trường.

### 18.1. Một artifact, nhiều môi trường

```text
orders-app.jar
       │
       ├── local + local config
       ├── staging + staging config
       └── production + production config
```

Cùng một application artifact có thể được triển khai ở nhiều nơi với:

- Environment variables.
- Java system properties.
- Command-line arguments.
- External config files.
- Profile-specific configuration.

Điều này giúp quy trình build/publish nhất quán: build một lần, deploy nhiều môi trường với cấu hình phù hợp.

### 18.2. Không đóng gói secrets vào JAR phát hành

Tránh lưu password, API token hoặc private key trực tiếp trong `src/main/resources/application.yml` rồi commit và đóng gói vào artifact phát hành.

Dùng cơ chế quản lý secret, environment variables hoặc external configuration an toàn theo nền tảng triển khai. JAR có thể được tải xuống, sao chép hoặc giải nén bởi nhiều người trong pipeline.

## 19. Spring Boot executable JAR và Docker/container

Executable JAR có thể được copy vào container image và chạy bằng Java runtime thích hợp.

Ví dụ Dockerfile đơn giản:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY orders-app.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Ví dụ giả định ứng dụng tương thích với Java 21 và artifact `orders-app.jar` đã được build trước khi tạo image. Chọn base image theo Java baseline và chính sách bảo mật của dự án.

### 19.1. Container image không thay thế executable JAR

Container image bao gồm runtime và môi trường đóng gói rộng hơn, trong khi executable JAR là artifact Java được chạy bên trong image.

Mối quan hệ:

```text
Container image
├── Java runtime
├── OS libraries cần thiết
└── /app/app.jar
    ├── BOOT-INF/classes
    └── BOOT-INF/lib
```

### 19.2. Layers và layers.idx

Spring Boot có thể ghi metadata về các layers của executable JAR:

```text
BOOT-INF/layers.idx
```

Layering giúp công cụ build container image phân tách application code, dependency thường xuyên thay đổi và dependency ít thay đổi. Điều này có thể cải thiện layer cache khi build image.

Tuy nhiên, `layers.idx` **không phải bằng chứng duy nhất để xác định executable JAR**, và không phải file mà ứng dụng cần đọc như business configuration.

Các công cụ như Spring Boot layertools/jarmode hoặc buildpacks có thể sử dụng metadata layering tùy phiên bản và cách build.

### 19.3. Cân nhắc image buildpacks

Ngoài viết Dockerfile và dùng `java -jar`, Spring Boot plugin còn hỗ trợ build OCI image qua integration với buildpacks, tùy cấu hình và môi trường.

Ví dụ Gradle task:

```bash
./gradlew bootBuildImage
```

Đây là một đường triển khai khác, không làm thay đổi sự phân biệt cơ bản giữa JAR thư viện và Spring Boot application artifact.

## 20. Fully executable JAR có phải mọi Boot JAR đều như vậy?

Một số phiên bản/cấu hình Spring Boot hỗ trợ **fully executable archive** với launch script được prepend vào file JAR.

Ví dụ trong Gradle có thể thấy cấu hình theo dòng plugin phù hợp:

```groovy
tasks.named('bootJar') {
    launchScript()
}
```

Ý tưởng là thêm một shell script để trên môi trường tương thích có thể chạy archive trực tiếp:

```bash
./orders-app.jar
```

Điều này khác với lệnh thông thường:

```bash
java -jar orders-app.jar
```

### 20.1. Không nhầm hai nghĩa của executable

Trong bài này, **Spring Boot executable JAR** chủ yếu nghĩa là **JAR có thể chạy qua `java -jar`** nhờ Boot launcher.

“Fully executable JAR” là biến thể có thêm launch script nhằm hỗ trợ chạy như một script/executable file trên một số hệ thống.

Không phải Boot JAR nào cũng có launch script; bạn không cần launch script để chạy `java -jar`.

### 20.2. Chú ý công cụ ZIP/JAR

Một số công cụ archive có thể xử lý khác nhau khi file JAR có phần shell script ở đầu. Do đó, nếu cần kiểm tra hoặc phân phối fully executable archive, hãy xác nhận toolchain hỗ trợ loại file này.

Trong môi trường container, cách `java -jar` thông thường thường đơn giản và dễ dự đoán hơn.

## 21. Executable WAR khác executable JAR thế nào?

Spring Boot có thể hỗ trợ đóng gói ứng dụng web thành WAR thay vì JAR.

### 21.1. WAR dùng cho servlet container

Một WAR truyền thống được thiết kế để triển khai vào servlet container như Tomcat ở môi trường tương ứng.

Cấu trúc WAR thường có:

```text
WEB-INF/classes/
WEB-INF/lib/
META-INF/
```

Spring Boot có thể tạo executable WAR có launcher để chạy bằng `java -jar` trong những cấu hình phù hợp, đồng thời phục vụ một số yêu cầu triển khai servlet container.

### 21.2. Không nhầm với JAR thư viện

Ba vai trò chính:

| Artifact | Mục tiêu |
|---|---|
| Library JAR | Để module khác dùng làm dependency |
| Boot executable JAR | Khởi chạy ứng dụng với embedded runtime/server khi phù hợp |
| WAR | Đóng gói web application cho servlet deployment hoặc Boot executable WAR tùy cấu hình |

Chỉ nên chọn WAR nếu có yêu cầu triển khai cụ thể. Với nhiều ứng dụng Spring Boot hiện đại, executable JAR là lựa chọn đơn giản để chạy trực tiếp.

## 22. Những lỗi thường gặp khi chạy hoặc dùng JAR

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
|---|---|---|
| `no main manifest attribute` | Plain/library JAR không có `Main-Class` | Dùng `bootJar`/`repackage` cho ứng dụng; không chạy library như app |
| `Could not find or load main class` | Classpath/entry point sai | Kiểm tra layout, manifest và lệnh chạy |
| `ClassNotFoundException` khi dùng Boot JAR làm dependency | Class ứng dụng nằm dưới `BOOT-INF/classes` | Tách thư viện thành plain JAR |
| `NoClassDefFoundError` lúc chạy | Thiếu dependency runtime hoặc version không tương thích | Kiểm tra `BOOT-INF/lib` hoặc dependency tree |
| Chạy JAR nhưng không tìm thấy file `src/main/resources/...` | Đang dùng filesystem path của source project | Dùng classpath resource |
| `bootJar` không tìm được main class | Module không có entry point hoặc có nhiều main classes | Chỉ dùng bootJar cho app, hoặc cấu hình `mainClass` |
| Có cả `-plain.jar` và JAR không classifier | Gradle tạo hai packaging variants | Kiểm tra file nào có `BOOT-INF` |
| App chạy được ở IDE nhưng thất bại với `java -jar` | Khác classpath, resources, profile hoặc build artifact | So sánh runtime dependencies và jar entries |
| `UnsupportedClassVersionError` | Java runtime thấp hơn bytecode target | Dùng runtime đúng Java version hoặc build target phù hợp |
| App JAR có dependencies nhưng không kết nối database | Dịch vụ ngoài/cấu hình không sẵn sàng | Kiểm tra config, network, credentials, DB availability |
| `java -cp app.jar Application` không thấy class | Boot JAR dùng layout nested và launcher | Chạy `java -jar app.jar` |
| Public library bị publish bằng executable JAR | Build/publish chọn nhầm artifact | Publish plain JAR, để executable JAR dành cho deployment |

### 22.1. Lỗi “no main manifest attribute”

Ví dụ:

```text
no main manifest attribute, in app-plain.jar
```

Khả năng cao bạn đang chạy plain JAR.

Kiểm tra `build/libs` hoặc `target` để xem đã tạo Boot executable JAR chưa. Nếu chưa, thực hiện task/goal đóng gói ứng dụng phù hợp.

### 22.2. Lỗi “ClassNotFoundException” với dependency

Nếu build phát hiện dependency nhưng lúc chạy không tìm thấy class, hãy phân biệt:

- Project đang dùng plain JAR và chưa đưa dependency vào classpath.
- Đã tạo executable JAR nhưng dependency cần thiết không có trong `BOOT-INF/lib`.
- Dependency bị exclude hoặc khai báo sai scope.
- Dependency/version bị conflict.
- Thư viện chứa class ở một package khác với import của code.

Không phải mọi `ClassNotFoundException` đều có nghĩa Spring Boot loader bị lỗi.

### 22.3. Lỗi Java version

Ví dụ:

```text
java.lang.UnsupportedClassVersionError
```

thường xuất hiện khi class được compile cho Java version mới hơn runtime đang dùng.

Kiểm tra:

```bash
java -version
```

và cấu hình Java toolchain/release của build. Spring Boot executable JAR không tự đóng gói một Java runtime tương thích bên trong theo mặc định.

## 23. Chạy từ IDE và chạy executable JAR khác nhau thế nào?

Khi bạn bấm Run trong IDE, IDE thường tạo classpath gồm:

```text
build/classes/java/main/
build/resources/main/
dependency-a.jar
dependency-b.jar
...
```

Sau đó IDE gọi:

```text
com.example.orders.OrdersApplication.main(...)
```

Nó không nhất thiết chạy Spring Boot JarLauncher.

Ngược lại:

```bash
java -jar orders-app.jar
```

sử dụng layout của executable JAR và launcher.

### 23.1. Vì sao IDE chạy được nhưng đóng gói lại lỗi?

Một số khả năng:

- Resource có trong IDE classpath nhưng bị loại khi build JAR.
- Dependency được IDE đưa vào nhưng không thuộc runtime classpath của artifact.
- Code dùng đường dẫn tuyệt đối hoặc đường dẫn relative tới project root.
- Main class/manifest được cấu hình sai.
- IDE chạy profile khác so với `java -jar`.
- Module build thiếu một thư viện cần thiết.
- Annotation processor/generated resource chưa được đưa vào artifact.

Đây là lý do cần kiểm tra **artifact cuối cùng**, không chỉ dựa vào việc Run thành công trong IDE.

### 23.2. bootRun là gì?

Spring Boot Gradle plugin thường có task:

```bash
./gradlew bootRun
```

`bootRun` khởi động ứng dụng bằng cơ chế chạy từ compiled classes/resources và runtime classpath, **không bắt buộc tạo executable JAR trước**.

So sánh:

| Cách chạy | Đặc điểm |
|---|---|
| Run main trong IDE | Classpath do IDE/Gradle/Maven integration chuẩn bị |
| `./gradlew bootRun` | Chạy từ project classpath qua Gradle task |
| `java -jar build/libs/app.jar` | Chạy artifact đã đóng gói bằng Boot launcher |
| `java -cp ... Main` | Chạy Java main với classpath tự chỉ định |

Với mục tiêu kiểm tra cách deploy thực tế, cần chạy đúng executable artifact cuối cùng, không chỉ bootRun.

## 24. Đóng gói đúng không đồng nghĩa ứng dụng chắc chắn khởi động được

Build thành công một Boot executable JAR chỉ xác nhận quá trình đóng gói đã tạo artifact theo cấu hình. Khi chạy, ứng dụng còn trải qua:

```text
JVM starts
    │
    ▼
Spring Boot launcher loads classes
    │
    ▼
SpringApplication.run
    │
    ▼
Environment and Config Data
    │
    ▼
Auto-configuration and bean registration
    │
    ▼
Instantiate/inject beans
    │
    ▼
Run startup callbacks and runners
    │
    ▼
Application ready (nếu thành công)
```

Có thể tồn tại JAR hoàn toàn hợp lệ nhưng ứng dụng lỗi vì:

- Database URL không hợp lệ.
- Thiếu password hoặc API key.
- Bean dependency bị thiếu.
- Port server đã được sử dụng.
- Configuration properties không bind/validate được.
- ApplicationRunner ném exception.
- Dịch vụ bên ngoài không sẵn sàng.

Đừng chữa một lỗi bean wiring bằng cách đổi `jar` sang `bootJar` khi artifact đã có launcher và dependencies đúng. Hãy xác định lỗi thuộc **packaging/classpath** hay **application startup**.

## 25. Publishing: artifact nào nên đưa lên Maven repository?

Một thư viện được phát hành để project khác dùng thường nên có:

- Plain JAR với các class/resource ở layout thông thường.
- Maven POM hoặc Gradle module metadata hợp lệ.
- Dependency declarations theo `api`/`implementation`/`runtime` phù hợp.
- Version ổn định.
- Có thể có sources JAR và Javadoc JAR khi cần.

Một executable JAR của ứng dụng thường được phát hành vào:

- CI/CD artifact storage.
- Container image repository (sau khi build image).
- Server hoặc deployment platform.
- Release package dành cho vận hành.

### 25.1. Vì sao publish nhầm executable JAR gây lỗi?

Một Maven consumer sẽ đặt artifact lên classpath như một thư viện. Nếu class của artifact nằm dưới `BOOT-INF/classes`, chúng không ở layout mà classpath resolver thông thường trông đợi.

Do đó, một artifact “dùng `java -jar` tốt” không tự đồng nghĩa “dùng làm dependency tốt”.

### 25.2. Có thể publish hai biến thể không?

Có, một project có thể xuất bản plain và executable artifacts với classifier khác nhau hoặc qua hai publication riêng.

Tuy nhiên, cần thống nhất:

- Artifact chính là gì?
- Consumer dependency sử dụng artifact nào?
- CI deployment lấy artifact nào?
- Tên/classifier có rõ ràng không?
- Có vô tình publish nested-dependency JAR như library chính không?

Nếu module đóng vai trò cả library lẫn application, việc tách thành hai module thường giúp quản lý dễ hơn và giảm ambiguity.

## 26. Phân biệt “chứa dependency” và “resolve dependency”

Một điểm nền tảng quan trọng khi sử dụng Java build tools:

### 26.1. Ở thời điểm build

Gradle hoặc Maven đọc dependency declarations để tải và chọn phiên bản thư viện:

```text
build.gradle / pom.xml
          │
          ▼
Dependency resolution
          │
          ▼
Compile classpath + runtime classpath
```

### 26.2. Khi tạo library JAR

```text
Compiled classes/resources
          │
          ▼
jar
          │
          ▼
library.jar
```

Metadata của publication có thể mô tả dependency để ứng dụng tiêu thụ tự resolve.

### 26.3. Khi tạo Boot executable JAR

```text
Application classes/resources
            +
Runtime dependencies
            │
            ▼
bootJar / repackage
            │
            ▼
Boot executable JAR
  BOOT-INF/classes/
  BOOT-INF/lib/
```

### 26.4. Khi chạy

Với library JAR, application launcher/build tool phải sắp xếp classpath có thư viện và các dependency cần thiết.

Với Boot executable JAR, Boot loader nạp runtime dependencies được đóng gói theo layout Boot.

Đó là lý do việc dependency resolution thành công ở build không bảo đảm bạn có thể dùng plain JAR bằng `java -jar` mà không chuẩn bị classpath khi chạy.

## 27. Quy trình kiểm tra artifact trước khi triển khai

Dù không thay thế các bài kiểm thử, một quy trình kỹ thuật hợp lý có thể gồm:

### Bước 1 — Xác nhận vai trò module

Module này là reusable library hay application entry point?

### Bước 2 — Chọn đúng task/goal

- Library: `jar` hoặc Maven JAR packaging.
- Application: `bootJar` hoặc `spring-boot:repackage`.

### Bước 3 — Xem tên artifact

Kiểm tra `build/libs` hoặc `target`, phân biệt `-plain`, `-exec` và các classifier khác.

### Bước 4 — Xem nội dung

```bash
jar tf artifact.jar
```

- Có class ở root package path? Thường là library/plain JAR.
- Có `BOOT-INF/classes` và `BOOT-INF/lib`? Thường là Boot executable JAR.

### Bước 5 — Xem manifest

Xác nhận `Main-Class` và `Start-Class` nếu cần executable JAR.

### Bước 6 — Xem dependencies

Với Boot JAR, xác nhận những runtime dependency quan trọng có trong `BOOT-INF/lib`.

### Bước 7 — Kiểm tra resource

Xác nhận `application.yml`, templates và các resources cần thiết được đóng gói vào đúng vị trí.

### Bước 8 — Chạy theo đúng mô hình triển khai

Ví dụ:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Không chỉ dựa vào IDE hoặc `bootRun` nếu production chạy `java -jar`.

### Bước 9 — Quan sát log khởi động

Phân biệt lỗi launcher/classpath, lỗi cấu hình và lỗi Spring ApplicationContext.

### Bước 10 — Đối chiếu Java runtime

Xác nhận Java version của môi trường chạy tương thích với bytecode và phiên bản Spring Boot.

## 28. Một số tình huống thực tế

### 28.1. “Tôi chỉ muốn viết thư viện dùng chung, có cần @SpringBootApplication không?”

Không. Một Java library có thể chỉ cần các class và interface thông thường. Nếu cần những Spring beans, module vẫn có thể cung cấp `@Configuration` hoặc auto-configuration, nhưng không cần có một main application class.

Hãy dùng plain JAR.

### 28.2. “Tôi muốn chạy ứng dụng Spring Boot chỉ có CommandLineRunner”

Bạn vẫn cần một application entry point. Có thể dùng `@SpringBootApplication`, `SpringApplication.run(...)` và `WebApplicationType.NONE`.

Sau đó tạo Boot executable JAR để chạy:

```bash
java -jar batch-app.jar
```

Không cần thêm web dependency chỉ để executable JAR chạy được.

### 28.3. “Tôi có một module repository, một module service và một module web”

Các module repository/service dùng chung thường là library JARs. Module web/application là entry point, tạo executable JAR chứa các module dependency.

```text
repository.jar
      │
      ▼
service.jar
      │
      ▼
web-app executable.jar
```

Tùy build graph, application executable JAR có thể chứa cả repository/service JAR dưới `BOOT-INF/lib`.

### 28.4. “Tôi cần nhập class từ app A sang app B”

Nếu các class là business logic dùng chung, nên tách chúng ra library module. Không nên thêm executable JAR của app A vào dependency của app B theo cách thông thường.

### 28.5. “Tôi có một Spring Boot starter, phải build bootJar không?”

Thông thường không. Starter/autoconfigure module thường được sử dụng dưới dạng library JAR, có thể đóng góp dependency metadata và auto-configuration resources.

Hãy tạo plain JAR; ứng dụng tiêu thụ mới tạo executable JAR.

### 28.6. “Tôi muốn một artifact chạy được trên server không cài Maven/Gradle”

Dùng Spring Boot executable JAR cùng Java runtime tương thích:

```bash
java -jar application.jar
```

Server không cần có source code hoặc Gradle/Maven để chạy artifact đã build. Nó vẫn cần runtime, permissions, cấu hình và những dịch vụ bên ngoài mà ứng dụng phụ thuộc.

### 28.7. “Tôi có thể giải nén JAR rồi chạy class thủ công không?”

Có thể làm ở mức thử nghiệm nhưng cần tạo lại classpath gồm application classes và dependencies. Cách này dễ sai và không cần thiết với Boot executable JAR.

Hãy ưu tiên cơ chế launcher được plugin cung cấp, trừ khi bạn có một yêu cầu triển khai đặc biệt.

## 29. Bài thực hành

### Bài 1 — Tạo plain library JAR

Tạo module `math-lib` chứa class `MathHelper` với method `square(int value)`. Dùng Gradle `java-library` plugin, chạy `jar` và kiểm tra class nằm ở root package path trong artifact.

### Bài 2 — Chạy thử library JAR với java -jar

Thử:

```bash
java -jar math-lib.jar
```

Quan sát lỗi entry point nếu manifest không có `Main-Class`. Giải thích tại sao đây không phải lỗi build thư viện.

### Bài 3 — Sử dụng library bằng classpath

Tạo một class `Main` ở module khác gọi `MathHelper.square(5)`. Build class và chạy với `-cp` có chứa library JAR, chú ý dấu phân tách classpath giữa Windows và Linux/macOS.

### Bài 4 — Tạo Boot executable JAR

Tạo Spring Boot application có `CommandLineRunner`. Dùng `bootJar` và chạy bằng:

```bash
java -jar app.jar
```

Quan sát runner và log startup.

### Bài 5 — So sánh hai artifact

Trong ứng dụng Boot, tạo cả plain JAR và executable JAR nếu build cho phép. Dùng `jar tf` kiểm tra class path, `BOOT-INF/classes`, `BOOT-INF/lib` và manifest.

### Bài 6 — Phân tích Main-Class và Start-Class

Mở `META-INF/MANIFEST.MF` của Boot executable JAR. Xác định tên launcher và application main class, rồi giải thích luồng `java -jar`.

### Bài 7 — Multi-module project

Tạo `shared-lib` và `main-app`. `main-app` phụ thuộc `shared-lib`, build `bootJar`. Kiểm tra `shared-lib.jar` nằm ở `BOOT-INF/lib` của app executable JAR.

### Bài 8 — Tái hiện lỗi dùng Boot JAR như library

Tạo một Boot executable JAR, rồi thử dùng nó như dependency classpath thông thường của project khác. Quan sát khác biệt so với plain JAR chứa class ở root, sau đó thiết kế lại theo library module.

### Bài 9 — Đọc resource từ JAR

Đưa `data/sample.txt` vào `src/main/resources`. Đọc bằng `getResourceAsStream` thay vì `Path.of("src/main/resources/...")`. So sánh hành vi trong IDE và sau khi chạy executable JAR.

### Bài 10 — Hai main classes

Tạo hai class có `public static void main` trong cùng module application. Cấu hình `springBoot.mainClass` hoặc `bootJar.mainClass` để chọn entry point. Kiểm tra `Start-Class` trong manifest.

### Bài 11 — Maven repackage

Tạo Maven Spring Boot application có `spring-boot-maven-plugin` và `repackage` execution. Dùng `mvn package` rồi quan sát artifact, phân biệt bản thường với bản repackage.

### Bài 12 — Runtime-only dependency

Tạo ứng dụng sử dụng một driver hoặc integration library ở runtime. Kiểm tra dependency có trong `BOOT-INF/lib` và phân biệt `implementation`, `runtimeOnly` với `testImplementation`.

### Bài 13 — External configuration

Build một executable JAR duy nhất, chạy lần lượt với hai profile/config khác nhau. Quan sát cấu hình hiệu lực thay đổi dù artifact không rebuild.

### Bài 14 — Java version mismatch

Biên dịch một ứng dụng cho Java release cao hơn Java runtime thử nghiệm (trong môi trường được phép). Quan sát lỗi version và giải thích vì sao việc đóng gói Boot JAR không tự mang theo JRE.

### Bài 15 — Docker deployment

Tạo container image chứa Java runtime và Boot executable JAR. Khởi chạy bằng `java -jar`, rồi giải thích vai trò của JAR so với image.

## 30. Tài liệu tham khảo chính thức

- [Spring Boot Reference — Executable Jars](https://docs.spring.io/spring-boot/reference/packaging/executable-jar/index.html): cấu trúc `BOOT-INF`, nested JARs và launcher.
- [Spring Boot Reference — Gradle Plugin](https://docs.spring.io/spring-boot/gradle-plugin/index.html): các task `bootJar`, `bootRun` và packaging.
- [Spring Boot Reference — Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/index.html): goal `repackage` và cấu hình artifact.
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): cách ứng dụng đọc cấu hình bên ngoài artifact.
- [Gradle Documentation — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): tạo library JAR và phân biệt dependencies API/implementation.
- [Apache Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): tạo JAR thông thường.
- [Oracle Java Documentation — The JAR File Format](https://docs.oracle.com/javase/8/docs/technotes/guides/jar/jar.html): cấu trúc JAR và manifest.

**Nguyên tắc cần nhớ:** JAR thư viện là artifact được nạp như dependency, thường đặt class trực tiếp theo package path ở root; Spring Boot executable JAR là artifact dùng để **chạy ứng dụng**, thường đặt class ở `BOOT-INF/classes`, dependency ở `BOOT-INF/lib` và dùng launcher trong manifest. Hãy chọn `jar` cho reusable library, `bootJar` hoặc `spring-boot:repackage` cho application entry point, và luôn kiểm tra nội dung artifact thực tế nếu gặp lỗi classpath hoặc startup. Một file có đuôi `.jar` chỉ cho biết định dạng archive — không cho biết nó đã được đóng gói đúng cho vai trò bạn cần hay chưa.
