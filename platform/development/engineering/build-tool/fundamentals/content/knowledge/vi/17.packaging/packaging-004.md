# JAR thư viện, JAR chạy được và các điều kiện thực thi

JAR (Java ARchive) là định dạng đóng gói dựa trên ZIP, thường chứa bytecode Java, tài nguyên và metadata. Cùng một định dạng JAR có thể được dùng cho hai mục đích khác nhau: cung cấp lớp và tài nguyên để project khác sử dụng, hoặc đóng gói một ứng dụng có thể khởi chạy trực tiếp bằng Java launcher.

Hai mục đích này không giống nhau. **JAR thư viện (library JAR)** chủ yếu cung cấp API cho mã nguồn khác. **JAR chạy được (executable JAR)** có một điểm vào (entry point) để Java launcher biết lớp nào cần khởi chạy. Một JAR có thể chứa các lớp Java và vẫn không chạy trực tiếp được nếu thiếu thông tin khởi chạy hoặc dependency cần thiết.

Ngoài việc tạo file JAR, build còn phải bảo đảm ứng dụng có đủ dependency, dùng đúng phiên bản Java, tìm được tài nguyên, truy cập được file và đáp ứng các điều kiện của môi trường chạy. Bài học này giải thích cấu trúc hai loại JAR, manifest, cách đóng gói bằng Gradle và Maven, cùng những điều cần kiểm tra trước khi phát hành.

## 1. JAR là gì?

JAR là một archive chứa các entry, mỗi entry có tên đường dẫn tương đối. Một JAR Java thông thường có thể chứa:

- Các file `.class` được compiler tạo ra.
- Tài nguyên như properties, JSON, template, ảnh và schema.
- Thư mục `META-INF` chứa manifest và metadata khác.
- Thông tin module như `module-info.class` nếu JAR được xây dựng theo JPMS.
- Metadata hoặc file bổ sung do framework và công cụ đóng gói tạo ra.

Ví dụ cấu trúc một JAR thư viện:

```text
order-domain-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       └── order/
│           ├── Order.class
│           └── OrderStatus.class
└── com/example/order/
    └── defaults.properties
```

JAR không chứa một thư mục gốc `classes` bắt buộc. Đường dẫn bên trong archive thường phản ánh package của lớp và vị trí tương đối của resource trên classpath. Ví dụ lớp `com.example.order.Order` thường nằm ở `com/example/order/Order.class`.

Có thể xem nội dung archive bằng JDK:

```bash
jar tf order-domain-1.0.0.jar
```

Lệnh `jar tf` chỉ liệt kê nội dung. Nó không chạy mã và cũng không xác nhận ứng dụng có đủ dependency để thực thi.

## 2. JAR thư viện (library JAR)

### 2.1. Mục đích

JAR thư viện được tạo để project khác sử dụng. Nó cung cấp các lớp, interface, enum, annotation và resource mà consumer có thể truy cập thông qua compile classpath hoặc module path.

Ví dụ một module `order-domain` cung cấp API:

```java
package com.example.order;

public class Order {
    private final String id;

    public Order(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
```

Sau khi biên dịch và đóng gói, project khác có thể khai báo JAR này như dependency. Consumer tạo đối tượng `Order` trong mã nguồn của mình; nó không cần gọi một `main` method của thư viện.

### 2.2. Library JAR không cần có main class

Một thư viện thường không có điểm vào ứng dụng. Nó được nạp khi chương trình consumer sử dụng các lớp của nó. Vì vậy, manifest của library JAR không bắt buộc phải có `Main-Class`.

Ví dụ manifest tối giản:

```text
Manifest-Version: 1.0
Implementation-Title: Order Domain
Implementation-Version: 1.0.0

```

Các thuộc tính `Implementation-Title` và `Implementation-Version` là metadata tùy chọn. Consumer hoặc công cụ có thể đọc manifest để nhận diện artifact, nhưng các thuộc tính này không làm JAR tự chạy.

### 2.3. Dependency của thư viện được quản lý ra sao?

Một library JAR thông thường không nhúng toàn bộ thư viện mà nó phụ thuộc. Thay vào đó, dependency được mô tả qua metadata phát hành, ví dụ POM Maven hoặc Gradle Module Metadata. Khi consumer khai báo dependency tới library, build tool có thể phân giải các dependency bắc cầu.

Ví dụ, `order-domain` có thể sử dụng SLF4J. Khi phát hành thư viện, metadata của nó công bố dependency tương ứng. Consumer khai báo `order-domain`; Gradle hoặc Maven sẽ phân giải SLF4J theo metadata và configuration/scope phù hợp.

Đây là điểm quan trọng khi phân biệt library JAR với fat JAR. Một JAR thư viện có thể không chứa `slf4j-api.jar` bên trong, nhưng build tool của consumer vẫn biết cần tải dependency đó khi đọc metadata của artifact.

### 2.4. Cách consumer sử dụng library JAR

Trong Gradle, nếu thư viện được phát hành lên repository:

```groovy
repositories {
    mavenCentral()
    maven {
        url = uri('https://repo.example.com/releases')
    }
}

dependencies {
    implementation 'com.example:order-domain:1.0.0'
}
```

Trong Maven:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>order-domain</artifactId>
    <version>1.0.0</version>
</dependency>
```

Build tool tải JAR và metadata cần thiết, sau đó đưa artifact vào classpath thích hợp. Nếu chỉ có một file JAR cục bộ mà không có metadata, consumer vẫn có thể thêm nó như file dependency, nhưng sẽ phải tự quản lý các dependency khác.

## 3. JAR chạy được (executable JAR)

### 3.1. Có điểm vào để Java launcher khởi chạy

Executable JAR là JAR được chuẩn bị để Java launcher có thể gọi một lớp điểm vào. Với JAR kiểu classpath truyền thống, manifest thường khai báo thuộc tính `Main-Class`:

```text
Manifest-Version: 1.0
Main-Class: com.example.order.OrderApplication

```

`Main-Class` phải chỉ đến tên đầy đủ (fully qualified name) của lớp chứa điểm vào mà phiên bản Java mục tiêu chấp nhận. Với ứng dụng Java truyền thống, điểm vào thường có dạng:

```java
package com.example.order;

public class OrderApplication {
    public static void main(String[] args) {
        System.out.println("Order service started");
    }
}
```

Manifest chỉ định lớp, không chỉ định tên file `.class` và cũng không dùng dấu `/` giữa package. Ví dụ đúng là `com.example.order.OrderApplication`.

### 3.2. Chạy bằng `java -jar`

Khi JAR có manifest `Main-Class` hợp lệ, có thể chạy:

```bash
java -jar order-application.jar
```

Java launcher đọc manifest, nạp lớp điểm vào và gọi phương thức khởi chạy. Nếu lớp không tồn tại, không có phương thức main hợp lệ theo quy tắc của Java runtime mục tiêu hoặc có lỗi khi khởi tạo lớp, ứng dụng sẽ không khởi động thành công.

`Main-Class` là điều kiện để launcher biết điểm vào; nó không tự đóng gói dependency. Một executable JAR có `Main-Class` vẫn có thể thất bại ngay khi chạy nếu các lớp mà ứng dụng cần không có trên runtime classpath hoặc module path.

### 3.3. Tạo manifest thủ công

Có thể tạo file `MANIFEST.MF`:

```text
Manifest-Version: 1.0
Main-Class: com.example.order.OrderApplication

```

Sau đó tạo JAR bằng lệnh `jar`:

```bash
jar --create \
    --file order-application.jar \
    --manifest MANIFEST.MF \
    -C build/classes/java/main . \
    -C build/resources/main .
```

Lệnh trên minh họa việc đóng gói bytecode và tài nguyên chính cùng manifest. Cần bảo đảm thư mục đầu vào tồn tại và không có xung đột entry giữa các thư mục được đưa vào archive.

JDK cũng hỗ trợ chỉ định main class trực tiếp khi tạo JAR:

```bash
jar --create \
    --file order-application.jar \
    --main-class com.example.order.OrderApplication \
    -C build/classes/java/main .
```

Tùy chọn `--main-class` ghi thông tin điểm vào vào manifest. Nó không biên dịch mã nguồn, không tự tìm dependency và không tạo runtime image.

## 4. Manifest và các thuộc tính quan trọng

Manifest là file metadata thường nằm tại `META-INF/MANIFEST.MF` trong JAR. Một số thuộc tính thường gặp:

| Thuộc tính | Mục đích |
|---|---|
| `Manifest-Version` | Phiên bản định dạng manifest; thường là `1.0` |
| `Main-Class` | Tên lớp điểm vào cho kiểu khởi chạy JAR truyền thống |
| `Class-Path` | Danh sách URL/đường dẫn bổ sung để tìm lớp và resource khi launcher xử lý manifest |
| `Implementation-Title` | Tên implementation/artifact |
| `Implementation-Version` | Version của implementation |
| `Specification-Title` | Tên specification mà thư viện triển khai |
| `Automatic-Module-Name` | Tên module ổn định khi JAR được dùng như automatic module trên module path |
| `Multi-Release` | Đánh dấu multi-release JAR khi giá trị là `true` |

Không phải JAR nào cũng cần tất cả thuộc tính. Library JAR thường không cần `Main-Class`; executable JAR thường cần điểm vào; `Class-Path` chỉ hữu ích khi dependency được cung cấp dưới dạng file ngoài và manifest được dùng để tìm chúng.

### 4.1. Quy tắc của `Main-Class`

`Main-Class` chứa tên lớp đầy đủ, ví dụ:

```text
Main-Class: com.example.order.OrderApplication
```

Lớp này phải có trong JAR hoặc có thể được tìm thấy từ classpath mà launcher thiết lập. Nếu viết sai package hoặc sai tên lớp, Java launcher có thể báo không tìm thấy hoặc không nạp được main class.

Không ghi `.class` ở cuối và không thay dấu chấm phân cách package bằng dấu gạch chéo. Ví dụ `com.example.order.OrderApplication` là tên phù hợp; `com/example/order/OrderApplication.class` là đường dẫn entry trong archive, không phải giá trị `Main-Class`.

### 4.2. Quy tắc của `Class-Path`

Nếu executable JAR không nhúng dependency, manifest có thể chỉ định các JAR ngoài:

```text
Manifest-Version: 1.0
Main-Class: com.example.order.OrderApplication
Class-Path: lib/slf4j-api.jar lib/jackson-databind.jar lib/jackson-core.jar

```

Các entry trong `Class-Path` là danh sách phân tách bằng khoảng trắng. Đường dẫn tương đối được diễn giải theo vị trí URL của JAR chứa manifest. Ví dụ nếu JAR nằm ở `/opt/order/app.jar`, entry `lib/slf4j-api.jar` trỏ đến thư mục `lib` tương ứng cạnh JAR theo quy tắc URL.

Điều này có nghĩa cấu trúc triển khai phải giữ đúng quan hệ đường dẫn:

```text
order-app/
├── app.jar
└── lib/
    ├── slf4j-api.jar
    ├── jackson-databind.jar
    └── jackson-core.jar
```

Nếu chuyển `app.jar` sang thư mục khác mà không chuyển thư mục `lib` tương ứng, dependency có thể không còn được tìm thấy. `Class-Path` trong manifest không tải dependency từ Maven Central; nó tham chiếu đến tài nguyên có thể truy cập theo URL.

### 4.3. Manifest không thay thế dependency metadata

`Class-Path` chủ yếu hỗ trợ launcher tìm file khi chạy một JAR. Nó không thay thế POM hoặc Gradle Module Metadata khi phát hành library cho project khác. Consumer build cần biết version, scope/variant và dependency graph; chỉ một chuỗi đường dẫn trong manifest không mô tả đầy đủ các thông tin đó.

Đối với thư viện được publish, hãy công bố dependency bằng metadata của hệ sinh thái build. Đối với ứng dụng triển khai cùng thư mục `lib`, manifest class path hoặc script khởi chạy có thể phù hợp.

## 5. Ba cách phân phối ứng dụng Java

Một ứng dụng có dependency bên ngoài có thể được phân phối theo nhiều hình thức.

### 5.1. Thin executable JAR

Thin JAR chứa lớp và tài nguyên của ứng dụng. Dependency được cung cấp bên ngoài, ví dụ trong thư mục `lib`, thông qua manifest `Class-Path` hoặc script khởi chạy.

```text
distribution/
├── order-app.jar
└── lib/
    ├── jackson-databind.jar
    ├── jackson-core.jar
    └── slf4j-api.jar
```

Ưu điểm:

- Các dependency vẫn là những JAR riêng, dễ nhận diện và thay thế theo quy trình quản lý version.
- Có thể chia sẻ thư viện giữa nhiều ứng dụng nếu chính sách triển khai cho phép.
- Phù hợp với cơ chế distribution có cấu trúc rõ ràng.

Điểm cần quản lý là thư mục dependency phải được phân phối đầy đủ và đúng vị trí. Nếu dùng `Class-Path`, các URL tương đối trong manifest phải khớp cấu trúc thư mục. Một script khởi chạy cũng có thể thiết lập classpath thay cho manifest.

### 5.2. Fat JAR hoặc uber JAR

Fat JAR (còn gọi là uber JAR) đóng gói lớp và tài nguyên của ứng dụng cùng nội dung của các dependency vào một archive lớn hơn. Người vận hành có thể triển khai một file thay vì một JAR cộng nhiều JAR phụ thuộc.

```text
order-app-all.jar
├── META-INF/
├── com/example/order/OrderApplication.class
├── com/fasterxml/jackson/.../*.class
└── org/slf4j/.../*.class
```

Lợi ích là việc phân phối đơn giản và ít phụ thuộc cấu trúc thư mục bên ngoài. Tuy nhiên, gộp nhiều archive có thể gây xung đột:

- Nhiều JAR chứa file cùng đường dẫn.
- Nhiều dependency có `META-INF/services/...` cần được hợp nhất đúng cách.
- Manifest của dependency có thể xung đột với manifest ứng dụng.
- Chữ ký số trong `META-INF` có thể không còn hợp lệ sau khi nội dung archive thay đổi.
- Dependency có thể chứa native library hoặc tài nguyên cần xử lý đặc biệt.
- Một số framework/module không tương thích với cách gộp phẳng.

Vì vậy, fat JAR cần plugin đóng gói hiểu cách xử lý service descriptor, file trùng và metadata. Chỉ giải nén tất cả JAR vào một thư mục rồi nén lại có thể tạo archive chạy sai.

### 5.3. Application distribution gồm JAR, dependency và script

Một lựa chọn khác là phát hành một thư mục hoặc file ZIP/TAR chứa:

- JAR chính của ứng dụng.
- Các dependency riêng trong thư mục `lib`.
- Script khởi chạy cho Windows và Unix.
- File cấu hình mặc định hoặc metadata cần thiết.

Ví dụ:

```text
order-app/
├── bin/
│   ├── order-app
│   └── order-app.bat
└── lib/
    ├── order-app-1.0.0.jar
    ├── jackson-databind.jar
    ├── jackson-core.jar
    └── slf4j-api.jar
```

Script khởi chạy thiết lập classpath và gọi Java với main class. Cách này phù hợp khi ứng dụng có nhiều dependency hoặc cần truyền JVM options, cấu hình logging, system properties và tham số ứng dụng.

## 6. Gradle: tạo JAR thư viện và executable JAR

### 6.1. Java plugin cung cấp task jar

Với Gradle Java plugin:

```groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'
```

Task `jar` đóng gói output của source set chính thành JAR. Với `java-library`, artifact này thường được dùng như thư viện và được publish cùng metadata phù hợp. Task không tự thêm tất cả dependency vào bên trong JAR.

Chạy:

```bash
./gradlew jar
```

Artifact thường nằm trong `build/libs/`. Tên file dựa trên project name, version và cấu hình archive.

### 6.2. Thêm Main-Class vào JAR

Với ứng dụng Java đơn giản, có thể cấu hình manifest của task `jar`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

tasks.named('jar') {
    manifest {
        attributes(
            'Main-Class': 'com.example.order.OrderApplication',
            'Implementation-Version': project.version
        )
    }
}
```

Sau khi chạy:

```bash
./gradlew jar
java -jar build/libs/<tên-jar>.jar
```

JAR có manifest điểm vào, nhưng vẫn chỉ chứa output mà task `jar` đóng gói theo cấu hình. Nếu ứng dụng dùng thư viện bên ngoài, cần cung cấp chúng bằng một chiến lược runtime dependency phù hợp.

Không nên kết luận rằng thêm `Main-Class` là đã tạo fat JAR. Thuộc tính này chỉ giúp launcher biết lớp cần chạy.

### 6.3. Dùng Application plugin

Gradle Application plugin phù hợp khi cần chạy và phân phối một ứng dụng Java cùng runtime dependency:

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.example.order.OrderApplication'
}
```

Application plugin áp dụng Java plugin và cung cấp các task tiện ích như:

| Task | Vai trò |
|---|---|
| `run` | Chạy ứng dụng bằng runtime classpath của project |
| `installDist` | Tạo distribution đã cài đặt trong thư mục build |
| `distZip` | Tạo distribution dạng ZIP |
| `distTar` | Tạo distribution dạng TAR |
| `startScripts` | Tạo script khởi chạy phù hợp hệ điều hành |

Chạy ứng dụng trong quá trình phát triển:

```bash
./gradlew run
```

Tạo distribution:

```bash
./gradlew installDist
./gradlew distZip
```

Distribution mặc định thường có script trong `bin/` và JAR cùng runtime dependency trong `lib/`. Script thiết lập classpath phù hợp rồi khởi chạy main class. Đây là một cách phân phối ứng dụng đầy đủ mà không cần gộp mọi dependency vào một JAR.

Application plugin không mặc định tạo fat JAR. Nếu yêu cầu một archive duy nhất chứa dependency, cần plugin đóng gói bổ sung hoặc cơ chế framework phù hợp.

### 6.4. Kiểm tra manifest và nội dung JAR

Sau khi build:

```bash
# Liệt kê nội dung
jar tf build/libs/order-app-1.0.0.jar

# Đọc manifest (có thể dùng unzip nếu có)
unzip -p build/libs/order-app-1.0.0.jar META-INF/MANIFEST.MF
```

Kiểm tra `Main-Class`, các resource cần thiết và tên lớp điểm vào. Sau đó chạy đúng cách phân phối dự kiến, không chỉ kiểm tra rằng file JAR đã được tạo.

## 7. Maven: tạo library JAR và executable JAR

### 7.1. Maven JAR Plugin

Maven project có packaging `jar` thường dùng Maven JAR Plugin để tạo artifact trong `target/`. Một library JAR không cần khai báo main class.

Để tạo executable JAR kiểu thin JAR, có thể cấu hình `Main-Class` trong manifest:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifest>
                        <mainClass>com.example.order.OrderApplication</mainClass>
                    </manifest>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Sau đó:

```bash
./mvnw package
java -jar target/order-app-1.0.0.jar
```

Manifest có main class nhưng JAR vẫn không tự chứa dependency ngoài. Nếu ứng dụng cần thư viện khác, cần thiết lập classpath hoặc đóng gói theo chiến lược khác.

### 7.2. Manifest Class-Path với dependency ngoài

Maven JAR Plugin có thể tạo manifest classpath tham chiếu đến thư mục dependency nếu cấu hình đúng. Tuy nhiên, chỉ tạo chuỗi `Class-Path` chưa đủ; quá trình phân phối phải sao chép các dependency đến vị trí tương ứng.

Một cách tiếp cận là dùng Maven Dependency Plugin để copy runtime dependencies vào thư mục `lib`, rồi cấu hình manifest classpath trỏ đến chúng. Khi triển khai, giữ cấu trúc thư mục nhất quán với đường dẫn tương đối trong manifest.

Với ứng dụng cần script và cấu hình phức tạp, nên dùng cơ chế assembly/distribution hoặc công cụ chuyên đóng gói thay vì tự ghép đường dẫn classpath ở nhiều nơi.

### 7.3. Fat JAR bằng Maven Shade Plugin

Maven Shade Plugin có thể gộp dependency vào một archive. Ví dụ cấu hình rút gọn:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-shade-plugin</artifactId>
            <version>3.6.0</version>
            <executions>
                <execution>
                    <phase>package</phase>
                    <goals>
                        <goal>shade</goal>
                    </goals>
                    <configuration>
                        <transformers>
                            <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                <mainClass>com.example.order.OrderApplication</mainClass>
                            </transformer>
                        </transformers>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Shade Plugin chạy ở phase `package`, gộp nội dung dependency và có thể tạo manifest với `Main-Class`. Với ứng dụng sử dụng `ServiceLoader`, cần transformer phù hợp để hợp nhất file service descriptor. Nếu dependency có resource trùng tên, cần xác định cách xử lý thay vì để một file bị ghi đè ngoài ý muốn.

Việc gộp JAR có thể làm chữ ký số của dependency không còn hợp lệ. Các file signature trong `META-INF` thường cần được loại bỏ hoặc xử lý theo hướng dẫn của plugin khi tạo archive mới. Nếu dùng relocation để đổi package, cần kiểm tra reflection, resource và tên lớp được lưu trong cấu hình.

## 8. JAR chạy được không đồng nghĩa với một file tự chứa mọi thứ

Một điểm dễ gây nhầm lẫn là từ “executable” chỉ mô tả khả năng khởi chạy theo cách đã cấu hình. Nó không tự cho biết dependency được phân phối như thế nào.

| Loại artifact | Có điểm vào? | Dependency bên ngoài | Cách chạy điển hình |
|---|---|---|---|
| Library JAR | Thường không | Consumer build tool phân giải | Được dùng trên classpath/module path của ứng dụng khác |
| Thin executable JAR | Có `Main-Class` | Cần `Class-Path`, script hoặc classpath được thiết lập | `java -jar` nếu manifest classpath đầy đủ |
| Fat/uber JAR | Có `Main-Class` | Phần lớn dependency được gộp vào archive | `java -jar` |
| Application distribution | Có main class trong cấu hình/script | Các dependency riêng trong `lib/` | Script trong `bin/` |
| Framework executable archive | Có entry point/launcher theo framework | Có thể chứa dependency lồng nhau theo định dạng riêng | `java -jar` theo quy ước framework |

Một JAR có thể được launcher mở nhưng ngay sau đó lỗi `NoClassDefFoundError` vì dependency chưa có. Khi kiểm tra khả năng chạy, phải xét cả manifest, classpath/runtime dependency và môi trường, không chỉ sự tồn tại của `Main-Class`.

## 9. Điều kiện để ứng dụng trong JAR thực thi thành công

Một ứng dụng được đóng gói cần đáp ứng nhiều điều kiện liên quan.

### 9.1. Có điểm vào hợp lệ

Với JAR classpath truyền thống chạy bằng `java -jar`, manifest phải chỉ ra lớp điểm vào. Lớp đó phải có phương thức main mà Java launcher của runtime mục tiêu chấp nhận. Dạng truyền thống được dùng rộng rãi là:

```java
public static void main(String[] args)
```

Lớp và method phải có đúng tên, chữ ký và khả năng truy cập theo quy tắc của phiên bản Java mục tiêu. Các phiên bản Java mới có thể mở rộng quy tắc launch của source-file/class mode; khi phát hành ứng dụng, nên xác định rõ phiên bản runtime mục tiêu và kiểm tra bằng chính launcher đó.

### 9.2. Runtime Java tương thích

Ứng dụng cần một JVM tương thích với bytecode và API mà nó sử dụng. Nếu ứng dụng được biên dịch với release mới hơn runtime đang cài, JVM có thể báo `UnsupportedClassVersionError`.

Cần phân biệt:

- JDK/JRE dùng để chạy ứng dụng.
- Phiên bản Java mà compiler nhắm tới (`--release`, toolchain hoặc compiler configuration).
- Phiên bản Java mà thư viện/framework yêu cầu.

Build thành công trên JDK mới không đảm bảo JAR chạy được trên một JRE cũ hơn. Hãy thử chạy bằng đúng phiên bản runtime mà môi trường triển khai sẽ dùng.

### 9.3. Đủ runtime dependency

Tất cả lớp cần thiết khi khởi động và chạy phải có trên classpath hoặc module path. Compile classpath có thể chứa thư viện mà runtime distribution không đóng gói. Vì vậy, compile thành công không chứng minh runtime classpath đầy đủ.

Thiếu lớp có thể dẫn đến:

- `ClassNotFoundException` khi ứng dụng chủ động tìm lớp theo tên.
- `NoClassDefFoundError` khi JVM cần nạp lớp nhưng không tìm thấy định nghĩa cần thiết.
- `NoSuchMethodError` hoặc `NoSuchFieldError` khi runtime có version API không tương thích với version lúc biên dịch.

Hãy kiểm tra runtime dependency graph, không chỉ compile dependency graph.

### 9.4. Có đủ resource và metadata

Ứng dụng có thể cần properties, template, service descriptor, logging configuration hoặc schema. Nếu resource không được đưa vào JAR hoặc classpath runtime, ứng dụng có thể khởi động thất bại hoặc chạy sai.

Các framework và thư viện có thể dựa vào `META-INF/services` để tìm implementation qua `ServiceLoader`. Khi gộp dependency vào fat JAR, các service descriptor cần được hợp nhất đúng cách để không làm mất provider.

### 9.5. Đúng filesystem, quyền truy cập và cấu hình ngoài

Ứng dụng có thể cần đọc file cấu hình, ghi log, tạo thư mục dữ liệu hoặc tải certificate. Những file bên ngoài JAR phải tồn tại ở vị trí mà ứng dụng mong đợi, và tài khoản chạy ứng dụng phải có quyền phù hợp.

Đường dẫn tương đối thường được phân giải theo working directory của tiến trình. Một lệnh chạy trong IDE có thể có working directory khác với service manager hoặc container. Với file quan trọng, nên truyền đường dẫn cấu hình rõ ràng hoặc dùng đường dẫn tuyệt đối theo môi trường triển khai.

Không nên đóng gói bí mật như mật khẩu database, token hoặc private key vào JAR. Artifact thường được lưu trữ và phân phối rộng hơn phạm vi một máy; bí mật nên được cấp qua secret store hoặc cơ chế cấu hình an toàn của môi trường.

### 9.6. Môi trường hệ điều hành và native dependency

Một số thư viện dùng native library hoặc gọi chương trình ngoài. Khi đó cần kiểm tra:

- Hệ điều hành và kiến trúc CPU.
- Native binary có sẵn và có thể nạp được không.
- Biến môi trường như `PATH` hoặc đường dẫn native library.
- Quyền thực thi và quyền truy cập file.
- Các chương trình hệ thống mà ứng dụng gọi có được cài đặt không.

Một JAR thuần Java thường có tính di động cao hơn, nhưng không thể giả định mọi ứng dụng Java đều không phụ thuộc môi trường hệ điều hành.

## 10. `java -jar` và `java -cp` khác nhau thế nào?

Có hai cách chạy phổ biến.

### 10.1. Dùng `java -jar`

```bash
java -jar order-app.jar
```

Launcher dùng JAR được chỉ định và thông tin manifest để tìm main class cùng classpath bổ sung. Khi dùng `-jar`, các thiết lập classpath bên ngoài như `-cp` hoặc `CLASSPATH` không được dùng theo cách chạy class thông thường; hãy cấu hình dependency trong manifest hoặc dùng cách chạy classpath riêng.

### 10.2. Dùng `java -cp`

Có thể chỉ định classpath rõ ràng và tên lớp điểm vào:

```bash
java -cp "order-app.jar:lib/*" com.example.order.OrderApplication
```

Trên Windows, dấu phân cách classpath là `;`:

```bat
java -cp "order-app.jar;lib/*" com.example.order.OrderApplication
```

Ở cách này, Java launcher nhận main class trực tiếp từ command line. JAR không bắt buộc phải có `Main-Class` trong manifest để lệnh chạy classpath hoạt động, dù manifest vẫn có thể chứa metadata khác.

### 10.3. Khi nào dùng cách nào?

| Tình huống | Cách phù hợp |
|---|---|
| Một JAR có manifest main class và dependency đã được đóng gói hoặc mô tả qua manifest | `java -jar` |
| Muốn kiểm soát classpath từ script hoặc command line | `java -cp` |
| Chạy một class trong thư mục output khi phát triển | `java -cp ... com.example.Main` |
| Ứng dụng được phát hành bằng Gradle Application distribution | Dùng script trong `bin/` để thiết lập classpath |
| Ứng dụng JPMS chạy trên module path | `java --module-path ... -m module[/main-class]` |

## 11. JAR và Java Platform Module System (JPMS)

Một JAR có thể chứa `module-info.class` để khai báo named module. Khi đó, cách tổ chức dependency và truy cập package có thể tuân theo module path thay vì chỉ classpath truyền thống.

Ví dụ `module-info.java`:

```java
module com.example.order {
    exports com.example.order.api;
    requires java.logging;
}
```

Sau khi biên dịch, `module-info.class` được đưa vào JAR. Có thể xem mô tả module:

```bash
jar --describe-module --file order-domain.jar
```

Để chạy named module, có thể dùng:

```bash
java --module-path mods -m com.example.order/com.example.order.OrderApplication
```

Ở đây, `com.example.order` đầu tiên là module name; phần sau dấu `/` là tên lớp main. Tên module và tên package/class là hai định danh khác nhau.

Nếu một thư viện không có `module-info.class` nhưng được đặt trên module path, JVM có thể xử lý nó như automatic module theo quy tắc đặt tên tương ứng. Manifest `Automatic-Module-Name` có thể cung cấp tên module ổn định cho trường hợp này.

Không nên mặc định mọi executable JAR là modular JAR hoặc mọi JAR đều chạy theo cùng quy tắc module path. Hãy xác định ứng dụng đang dùng classpath hay JPMS và cấu hình launcher phù hợp.

## 12. Framework executable JAR và dependency lồng nhau

Một số framework tạo executable JAR có cấu trúc riêng. Ví dụ, Spring Boot có thể đóng gói dependency vào các JAR lồng bên trong archive ứng dụng và dùng launcher riêng để nạp chúng.

Kiểu archive này vẫn có thể chạy bằng:

```bash
java -jar order-service.jar
```

Nhưng cơ chế nạp lớp không giống một JAR phẳng được tạo bằng cách giải nén mọi dependency vào gốc archive. Không nên tự chỉnh sửa cấu trúc hoặc dùng công cụ shade theo cách không tương thích với định dạng framework.

Khi dùng framework plugin, hãy theo cách đóng gói và launcher mà plugin/framework hỗ trợ. Kiểm tra tài liệu về resource, classloader, layered archive, native image hoặc cách triển khai nếu ứng dụng cần các tính năng đó.

## 13. Kiểm tra JAR trước khi phát hành

Một quy trình kiểm tra artifact nên xác minh nhiều khía cạnh.

### 13.1. Kiểm tra nội dung và manifest

```bash
# Liệt kê entry trong JAR
jar tf order-app.jar

# Kiểm tra manifest bằng unzip nếu công cụ có sẵn
unzip -p order-app.jar META-INF/MANIFEST.MF

# Kiểm tra mô tả module nếu JAR dùng JPMS
jar --describe-module --file order-app.jar
```

Xác nhận main class, resource, module descriptor và metadata cần thiết có mặt. Nếu JAR cần file cấu hình ngoài, xác nhận cách truyền đường dẫn đó trong môi trường chạy.

### 13.2. Chạy bằng đúng runtime mục tiêu

```bash
java -version
java -jar order-app.jar
```

Chạy trên phiên bản Java mà môi trường triển khai sẽ dùng. Nếu ứng dụng cần system property hoặc tham số, thử đúng command line hoặc script production dự kiến.

### 13.3. Kiểm tra dependency

Với Gradle, xem runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Với Maven:

```bash
./mvnw dependency:tree -Dscope=runtime
```

Nếu JAR là thin JAR, xác nhận tất cả runtime dependency được phân phối và đường dẫn manifest/script trỏ đúng. Nếu là fat JAR, xác nhận plugin đã xử lý dependency, service descriptor và resource trùng phù hợp.

### 13.4. Kiểm tra artifact trong môi trường sạch

Không nên chỉ chạy JAR từ thư mục build nơi mọi dependency và file nguồn đều có sẵn. Hãy thử với đúng distribution đã tạo, trong một thư mục triển khai sạch hoặc container tương tự môi trường thật.

Điều này giúp phát hiện những phụ thuộc vô tình vào:

- File chỉ tồn tại trong checkout source.
- JAR có sẵn trong thư mục cá nhân.
- Biến môi trường chỉ được IDE thiết lập.
- Working directory khác dự kiến.
- JDK mới hơn runtime production.
- File cấu hình hoặc certificate chưa được triển khai.

## 14. Lỗi thường gặp khi chạy JAR

| Lỗi hoặc hiện tượng | Nguyên nhân có thể có | Hướng xử lý |
|---|---|---|
| `no main manifest attribute` | Manifest không có `Main-Class` khi chạy JAR kiểu truyền thống | Cấu hình main class trong manifest hoặc chạy classpath với tên lớp |
| `Could not find or load main class` | Sai tên main class hoặc lớp không nằm trong classpath/JAR | Kiểm tra `Main-Class`, package và nội dung archive |
| `ClassNotFoundException` | Code tìm lớp theo tên nhưng runtime không có lớp đó | Kiểm tra runtime classpath/module path và dependency |
| `NoClassDefFoundError` | Thiếu định nghĩa lớp lúc JVM cần nạp hoặc lỗi khởi tạo lớp trước đó | Kiểm tra dependency, static initialization và exception trước đó |
| `NoSuchMethodError` | Version runtime của thư viện khác với API mà mã đã biên dịch dựa vào | Kiểm tra dependency graph và version được đóng gói |
| `UnsupportedClassVersionError` | Bytecode được biên dịch cho Java mới hơn runtime | Dùng runtime phù hợp hoặc biên dịch với release thấp hơn |
| Resource không tìm thấy | Resource chưa được đóng gói hoặc lookup sai đường dẫn | Kiểm tra JAR bằng `jar tf`, dùng resource API phù hợp |
| `Permission denied` | Tài khoản chạy thiếu quyền đọc, ghi hoặc thực thi | Kiểm tra owner, permission và volume mount |
| `UnsatisfiedLinkError` | Native library thiếu hoặc không tương thích OS/architecture | Kiểm tra native dependency và đường dẫn nạp thư viện |
| Service provider không được phát hiện trong fat JAR | File `META-INF/services` bị ghi đè hoặc không được hợp nhất | Cấu hình service resource transformer/merger phù hợp |

Thông báo đầu tiên thường chứa nguyên nhân quan trọng hơn dòng lỗi cuối. Ví dụ `NoClassDefFoundError` có thể là hệ quả của một exception trước đó trong static initializer. Hãy đọc toàn bộ stack trace và xác định thời điểm lớp được nạp.

## 15. Lựa chọn cách đóng gói theo nhu cầu

| Nhu cầu | Hình thức phù hợp | Lý do |
|---|---|---|
| Phát hành API cho project khác | Library JAR cùng metadata dependency | Consumer build tool quản lý version và dependency graph |
| Chạy một ứng dụng nhỏ, ít dependency | Thin executable JAR | Một file ứng dụng và manifest main class có thể đủ |
| Ứng dụng có dependency ngoài, muốn một file triển khai | Fat/uber JAR hoặc framework executable JAR | Gộp dependency theo quy tắc plugin/framework |
| Ứng dụng có nhiều dependency và cần JVM options/script | Application distribution | Tách JAR và dependency, cung cấp script khởi chạy |
| Ứng dụng dùng JPMS | Modular JAR và module path | Thể hiện module name, requires/exports/opens rõ ràng |
| Ứng dụng cần native runtime hoặc image tối ưu | Công cụ runtime image/native image phù hợp | Đáp ứng mục tiêu triển khai cụ thể ngoài JAR thuần |

Không có một định dạng duy nhất tốt nhất cho mọi dự án. Hãy chọn dựa trên cách consumer sử dụng thư viện, cách vận hành triển khai ứng dụng, yêu cầu bảo mật và khả năng kiểm soát runtime dependency.

## 16. Bài tập vận dụng

Một dự án có hai module `order-domain` và `order-app`. `order-domain` cung cấp class `Order` cho project khác. `order-app` có lớp `OrderApplication` chứa `main` và sử dụng Jackson cùng SLF4J.

Hãy xác định:

1. Artifact của `order-domain` nên được đóng gói như library JAR hay executable JAR? Vì sao?
2. Manifest của `order-app` cần thuộc tính nào để chạy bằng `java -jar`?
3. Thêm `Main-Class` có tự đưa Jackson và SLF4J vào JAR không?
4. Nếu dùng thin JAR, có những cách nào để cung cấp runtime dependency?
5. Nếu dùng Gradle Application plugin, task nào tạo distribution và script khởi chạy?
6. Nếu dùng Maven Shade Plugin, cần quan tâm điều gì với `META-INF/services` và chữ ký số của dependency?
7. Vì sao lệnh `java -jar app.jar` không sử dụng `-cp` theo cách chạy classpath thông thường?
8. Nếu build bằng Java 21 nhưng triển khai bằng Java 17, cần kiểm tra điều gì?
9. Nếu ứng dụng chạy trong IDE nhưng thiếu resource khi chạy JAR, cần kiểm tra archive và cách lookup nào?
10. Nếu JAR chứa `module-info.class`, nên kiểm tra và khởi chạy theo mô hình nào?

Có thể thực hành bằng cách tạo một library JAR và một ứng dụng nhỏ phụ thuộc vào nó. Tạo executable JAR với manifest main class, thử chạy khi thiếu dependency để quan sát lỗi, sau đó cung cấp dependency bằng classpath hoặc application distribution. Dùng `jar tf` và đọc manifest để xác nhận nội dung thực tế của từng artifact.

Khi chuẩn bị phát hành, hãy xác định JAR đang đóng vai trò thư viện hay ứng dụng, điểm vào nằm ở đâu, dependency được cung cấp bằng cách nào và runtime mục tiêu có đáp ứng yêu cầu hay không. Một file JAR được tạo thành công mới chỉ là kết quả đóng gói; khả năng thực thi cần được xác nhận bằng đúng classpath, runtime, resource và môi trường mà ứng dụng sẽ sử dụng.
