# Vai trò của thông tin tên tham số khi biên dịch với -parameters

Trong endpoint Actuator tùy chỉnh, tên tham số có thể trở thành tên đầu vào mà công cụ vận hành phải gửi. Với phương thức `inspect(String cacheName, int limit)`, Actuator cần biết đầu vào nào là `cacheName`, đầu vào nào là `limit`, rồi mới chuyển đổi và truyền giá trị vào đúng vị trí.

Bài này giải thích vì sao mã Java biên dịch thành công vẫn có thể làm Actuator không khởi tạo được thao tác, cách bật `-parameters` và cách kiểm chứng trên tệp `.class` thực sự được chạy. Ví dụ dùng Java 17 trở lên; phần ứng dụng minh họa theo Spring Boot 3.3, với JDK 21.

## 1. Tên trong mã nguồn và tên có ở thời điểm chạy

Xét khai báo sau; đây là một phương thức minh họa, chưa phải chương trình độc lập:

```java
public String inspect(String cacheName, int limit) {
    return cacheName + ":" + limit;
}
```

Có ba thông tin khác nhau:

| Thông tin | Trong ví dụ | Mục đích |
| --- | --- | --- |
| Vị trí tham số | Thứ nhất, thứ hai | Xác định thứ tự truyền đối số |
| Kiểu tham số | `String`, `int` | Kiểm tra kiểu và chuyển đổi đầu vào |
| Tên tham số | `cacheName`, `limit` | Ghép đầu vào có tên với tham số tương ứng |

Một lời gọi Java trực tiếp như `inspect("inventory", 5)` truyền đối số theo vị trí. JVM không cần tên `cacheName` để thực hiện lời gọi đó. Vì vậy, biên dịch thành công và gọi trực tiếp thành công chưa chứng minh rằng framework đọc được tên tham số.

`-parameters` là tùy chọn của **trình biên dịch `javac`**. Nó yêu cầu lưu tên tham số hình thức của phương thức và constructor vào metadata của tệp `.class`, để Java Reflection đọc lại. Nó không phải tùy chọn cấu hình HTTP hay cờ bật endpoint. [Tài liệu javac của JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) mô tả mục đích của tùy chọn này.

Ở thời điểm chạy, các API cần chú ý là:

- `Method.getParameters()`: lấy các đối tượng mô tả tham số.
- `Parameter.getName()`: lấy tên đọc được từ class hoặc tên tổng hợp.
- `Parameter.isNamePresent()`: kiểm tra class có cung cấp tên thực hay không.

Khi không có tên thực, `getName()` vẫn có thể trả chuỗi như `arg0`, `arg1`. Vì thế, chỉ kiểm tra tên khác `null` là chưa đủ. Phải kiểm tra cả `isNamePresent()`. Theo [API Parameter của Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html), tên tổng hợp có dạng `argN`; việc có tên được xác định từ thuộc tính `MethodParameters`.

## 2. Vì sao Actuator cần thông tin này?

Endpoint có tham số là điểm nối giữa hai cách gọi: phía ngoài cung cấp dữ liệu có tên, còn phương thức Java nhận đối số theo thứ tự. Chẳng hạn, bài thực hành dưới đây nhận yêu cầu:

```http
GET /actuator/nameprobe?cacheName=inventory&limit=5
```

Đường đi cần hiểu là:

```text
Tên trong mã nguồn: cacheName, limit
        |
        | javac -parameters
        v
Metadata trong NameProbeEndpoint.class
        |
        | Actuator đọc mô tả phương thức
        v
Ghép cacheName -> tham số thứ nhất
Ghép limit     -> tham số thứ hai
        |
        | chuyển chuỗi "5" thành int
        v
inspect("inventory", 5)
```

Hai việc **tìm tên** và **chuyển đổi kiểu** có liên quan nhưng khác nhau. Biết tham số thứ hai có kiểu `int` chưa cho Actuator biết phải lấy giá trị từ khóa `limit`.

Với `@ReadOperation`, ví dụ sử dụng query parameter. Với `@WriteOperation`, các thuộc tính ở mức gốc của JSON cũng có thể được ánh xạ theo tên tham số. `@Selector` đánh dấu tham số thuộc đường dẫn, nhưng không thay thế yêu cầu giữ thông tin tên. Cơ chế nhận đầu vào này thuộc mô hình endpoint dùng chung cho HTTP/JMX; không nên áp nguyên cách khai báo tham số của Spring MVC controller vào đây. Xem [Receiving Input trong tài liệu Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.receiving-input).

**Khi thiếu metadata, không được suy luận rằng chỉ cần gửi `arg0` là được.** Trong Spring Boot 3.3, việc trích xuất tên cho thao tác Java có thể thất bại ngay khi phát hiện endpoint. Khi ấy ứng dụng có thể dừng khởi tạo trước khi phục vụ yêu cầu. Trường hợp này khác với một endpoint đã hoạt động nhưng người gọi quên gửi tham số.

## 3. Thí nghiệm Java độc lập: có cờ, không có cờ và chỉ có -g

Lưu chương trình sau vào đúng tệp `ParameterNamesDemo.java`. Chương trình không cần Spring hoặc thư viện ngoài:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNamesDemo {
    public static String inspect(String cacheName, int limit) {
        return cacheName + ":" + limit;
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterNamesDemo.class.getDeclaredMethod(
                "inspect", String.class, int.class);
        for (Parameter parameter : method.getParameters()) {
            System.out.printf("%s / present=%s%n",
                    parameter.getName(), parameter.isNamePresent());
        }
        System.out.println(inspect("inventory", 5));
    }
}
```

### 3.1. Biên dịch không có -parameters

Chạy từ thư mục chứa tệp nguồn:

```shell
javac -encoding UTF-8 -d out-without ParameterNamesDemo.java
java -cp out-without ParameterNamesDemo
```

Stdout:

```text
arg0 / present=false
arg1 / present=false
inventory:5
```

Dòng `inventory:5` chứng minh lời gọi Java trực tiếp vẫn chạy. Hai dòng đầu chứng minh Reflection không có tên nguồn của hai tham số trên phương thức `inspect`.

### 3.2. Biên dịch có -parameters

```shell
javac -encoding UTF-8 -parameters -d out-with ParameterNamesDemo.java
java -cp out-with ParameterNamesDemo
```

Stdout:

```text
cacheName / present=true
limit / present=true
inventory:5
```

Mã nguồn và kết quả nghiệp vụ không đổi. Phần thay đổi là metadata giúp thành phần khác hiểu tên tham số.

### 3.3. Chỉ bật thông tin gỡ lỗi bằng -g

```shell
javac -encoding UTF-8 -g -d out-debug ParameterNamesDemo.java
java -cp out-debug ParameterNamesDemo
```

Stdout của ví dụ:

```text
arg0 / present=false
arg1 / present=false
inventory:5
```

`-g` có thể tạo thông tin gỡ lỗi, bao gồm thông tin biến cục bộ. Điều đó không làm Java Reflection coi tên của hai tham số thông thường trong ví dụ là hiện diện theo `MethodParameters`.

Từ Spring Framework 6.1, `LocalVariableTableParameterNameDiscoverer` đã bị loại bỏ. Framework không còn dùng cơ chế đó để suy tên tham số từ bảng biến cục bộ. Vì vậy, với dòng Spring Boot 3.3 dùng Spring Framework 6.1, không nên trông chờ vào `-g` để thay thế `-parameters`. [Ghi chú phát hành Spring Framework 6.1](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes#parameter-name-retention) nêu rõ thay đổi này.

Các lệnh ghi kết quả vào thư mục khác nhau để tránh vô tình chạy lại một tệp `.class` cũ. Khi đổi cờ biên dịch trong dự án thật, cũng phải tái biên dịch đúng lớp cần kiểm tra.

## 4. Thực hành với một endpoint Actuator

### 4.1. Chuẩn bị ứng dụng mẫu

Đây là dự án thực hành độc lập. Ví dụ cố định Spring Boot `3.3.0` để tái hiện hành vi trong dòng 3.3; số phiên bản này không phải khẳng định về phiên bản mới nhất. Dùng JDK 21 và Gradle 8.x.

Tạo cấu trúc:

```text
parameter-endpoint-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── ParameterEndpointApplication.java
    │   └── NameProbeEndpoint.java
    └── resources/
        └── application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'parameter-endpoint-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Plugin Spring Boot khi phối hợp với plugin Java đã tự thêm `-parameters` cho các tác vụ `JavaCompile`; vì thế dự án mẫu không cần thêm cờ thủ công. Phần BOM trong ví dụ quản lý phiên bản dependency. [Tài liệu Gradle plugin 3.3](https://docs.spring.io/spring-boot/3.3/gradle-plugin/reacting.html#reacting-to-other-plugins.java) mô tả cấu hình biên dịch tự động này.

`src/main/java/demo/ParameterEndpointApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ParameterEndpointApplication {
    public static void main(String[] args) {
        SpringApplication.run(ParameterEndpointApplication.class, args);
    }

    @Bean
    NameProbeEndpoint nameProbeEndpoint() {
        return new NameProbeEndpoint();
    }
}
```

`src/main/java/demo/NameProbeEndpoint.java`:

```java
package demo;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;

@Endpoint(id = "nameprobe")
public class NameProbeEndpoint {
    @ReadOperation
    public Snapshot inspect(String cacheName, int limit) {
        return new Snapshot(cacheName, limit);
    }

    public record Snapshot(String cacheName, int limit) {
    }
}
```

Đối tượng endpoint được đăng ký bằng `@Bean`. `inspect` chỉ phản hồi lại đầu vào để quan sát việc ánh xạ; nó không truy cập một bộ nhớ đệm thật. `Snapshot` là kiểu trả về, không phải đối tượng được dùng để gom các tham số đầu vào.

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,nameprobe
```

Cấu hình này phục vụ thí nghiệm cục bộ. Ví dụ không thêm Spring Security; nếu áp dụng mã vào ứng dụng đã có bảo mật hoặc đổi cổng/đường dẫn quản trị, kết quả truy cập còn phụ thuộc cấu hình đó.

### 4.2. Chạy và gửi đầu vào

Tại thư mục gốc của dự án mẫu, có thể tạo Gradle Wrapper bằng Gradle 8.x đang cài:

```shell
gradle wrapper --gradle-version 8.5
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean bootRun
```

Trên Linux/macOS:

```shell
./gradlew clean bootRun
```

Sau khi ứng dụng khởi động, mở terminal khác. Trên Windows dùng `curl.exe`; trên Linux/macOS có thể dùng `curl`:

```shell
curl.exe -s "http://127.0.0.1:8080/actuator/nameprobe?cacheName=inventory&limit=5"
```

Phần thân phản hồi JSON:

```json
{"cacheName":"inventory","limit":5}
```

Ứng dụng trả HTTP 200. `limit` ở đầu vào HTTP là chuỗi ký tự; phương thức nhận được số nguyên `5`. Khi kiểm tra JSON, hãy so giá trị các trường, không phụ thuộc thứ tự trường.

Hai yêu cầu để kiểm tra lỗi đầu vào:

```shell
curl.exe -i "http://127.0.0.1:8080/actuator/nameprobe?cacheName=inventory"
curl.exe -i "http://127.0.0.1:8080/actuator/nameprobe?cacheName=inventory&limit=abc"
```

Với đúng ứng dụng mẫu:

| Yêu cầu | Kết quả |
| --- | --- |
| Có `cacheName=inventory&limit=5` | 200, phản hồi hai giá trị |
| Thiếu `limit` | 400, thiếu tham số bắt buộc |
| `limit=abc` | 400, không chuyển được sang `int` |

Cả hai tham số của `inspect` đều bắt buộc trong ví dụ này. Không cần dựa vào nội dung thân lỗi vì cách trình bày lỗi có thể khác giữa các cấu hình.

### 4.3. Tái hiện thiếu metadata một cách có kiểm soát

Chỉ trong dự án thí nghiệm, có thể thêm cấu hình sau vào cuối `build.gradle` để loại cờ mà plugin đã thêm:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.removeAll { it == '-parameters' }
}
```

Chạy lại `clean bootRun` để bảo đảm lớp endpoint được biên dịch lại. Khi phát hiện phương thức `inspect(String, int)`, Spring Boot 3.3 có thể báo `IllegalStateException` với thông điệp bắt đầu bằng:

```text
Failed to extract parameter names for
```

Thông điệp đầy đủ còn chứa mô tả phương thức; các exception bên ngoài có thể là lỗi tạo bean. Hãy đọc nguyên nhân sâu nhất thay vì chỉ nhìn dòng báo lỗi khởi động ở ngoài.

Sau thí nghiệm, bỏ cấu hình loại cờ và chạy lại bản build sạch. Việc thêm `?arg0=inventory&arg1=5` vào URL không giải quyết được một ứng dụng đã thất bại khi phát hiện thao tác.

## 5. Bật cờ ở đúng nơi biên dịch

### Gradle: ứng dụng và thư viện có thể khác nhau

Với dự án Java không được plugin Spring Boot cấu hình, thêm cờ vào tác vụ biên dịch của **dự án sở hữu lớp endpoint**:

```groovy
tasks.withType(JavaCompile).configureEach {
    if (!options.compilerArgs.contains('-parameters')) {
        options.compilerArgs.add('-parameters')
    }
}
```

Đoạn này thêm phần tử vào danh sách hiện có. Tránh gán lại toàn bộ `compilerArgs` chỉ để thêm một cờ, vì có thể vô tình xóa tùy chọn khác.

Trong dự án nhiều module, bật cờ ở ứng dụng tiêu thụ không tái biên dịch các lớp đã nằm trong JAR thư viện. Nếu `NameProbeEndpoint` được cung cấp bởi một module thư viện chỉ áp dụng `java-library`, phải cấu hình và phát hành lại module đó. Cũng cần kiểm tra khi công cụ thu gọn hoặc biến đổi bytecode nằm sau bước biên dịch.

### Maven: phân biệt parent và BOM

Khi kế thừa `spring-boot-starter-parent`, cấu hình biên dịch có sẵn `-parameters`. Chỉ import `spring-boot-dependencies` làm BOM không kế thừa các thiết lập plugin của parent. [Tài liệu Maven plugin 3.3](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html) phân biệt hai cách sử dụng này.

Nếu dự án tự quản lý `maven-compiler-plugin`, cấu hình tương ứng trong phần `build/plugins` là:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Đây là một đoạn cấu hình để ghép vào POM đang quản lý phiên bản plugin và mức Java phù hợp, không phải POM độc lập. Sau khi đổi cấu hình, chạy lại bước biên dịch sạch của dự án và kiểm tra class đầu ra.

### IDE và CI

IDE có thể dùng trình biên dịch/cấu hình riêng thay vì ủy quyền cho Gradle hoặc Maven. Do đó, “chạy được trong IDE” và “chạy được JAR của CI” là hai phép kiểm khác nhau. Cách xác nhận đáng tin là đọc metadata của lớp mà tiến trình thực tế nạp, không chỉ nhìn tùy chọn đang hiển thị trong IDE.

## 6. Kiểm chứng trên class và trên artifact

Với thí nghiệm Java độc lập ở phần 3, dùng công cụ `javap` của JDK:

```shell
javap -p -v -classpath out-with ParameterNamesDemo
javap -p -v -classpath out-without ParameterNamesDemo
```

Trong phần mô tả phương thức `inspect` của bản có cờ, tìm thuộc tính `MethodParameters` và các tên `cacheName`, `limit`. Với bản không có cờ, không có bảng tên tương ứng cho phương thức này.

Không chỉ tìm chuỗi `cacheName` ở bất kỳ đâu trong toàn bộ đầu ra: thông tin gỡ lỗi hoặc thành phần khác cũng có thể chứa một chuỗi giống tên cần tìm. Cũng không suy ra mọi phương thức trong class đều có tên đúng chỉ vì thấy một bảng `MethodParameters`; hãy kiểm tra đúng phương thức và đúng từng tham số.

Nếu nghi ngờ chạy nhầm class, có thể tạm kiểm tra nguồn nạp lớp trong mã chẩn đoán:

```java
System.out.println(
        NameProbeEndpoint.class.getProtectionDomain()
                .getCodeSource().getLocation());
```

Đoạn trên dành cho quá trình chẩn đoán, không phải một chương trình độc lập; vị trí in ra phụ thuộc cách đóng gói và môi trường. Nó giúp đối chiếu xem đang chạy bản trong thư mục build hay JAR thư viện khác.

Với executable JAR do Spring Boot đóng gói, lớp ứng dụng thường nằm dưới `BOOT-INF/classes`, còn thư viện dưới `BOOT-INF/lib`. Khi dùng `javap`, giải nén artifact vào thư mục tạm rồi trỏ classpath đến đúng thư mục hoặc JAR chứa lớp cần kiểm tra. Không giả định rằng `javap -classpath app.jar` sẽ tự đọc lớp ứng dụng trong cấu trúc JAR lồng nhau.

Thứ tự kiểm chứng hữu ích là:

```text
1. Xác định class endpoint do module nào tạo.
2. Biên dịch lại module đó với -parameters.
3. Kiểm tra đúng phương thức trong class đầu ra.
4. Kiểm tra class được đóng gói vào artifact triển khai.
5. Xác nhận tiến trình đang dùng artifact vừa tạo.
6. Thử yêu cầu hợp lệ và yêu cầu thiếu/sai kiểu tham số.
```

## 7. Phân biệt lỗi metadata với các lỗi endpoint khác

| Biểu hiện | Điều cần kiểm tra trước |
| --- | --- |
| Khởi tạo thất bại, nguyên nhân nói không trích xuất được tên tham số | Metadata của đúng phương thức, cờ biên dịch, JAR đang được nạp |
| Ứng dụng khởi động nhưng URL trả 404 | Endpoint đã được đăng ký/chấp nhận phơi bày, đường dẫn quản trị, cổng và thao tác tương ứng |
| Trả 401 hoặc 403 | Xác thực, phân quyền và các quy tắc bảo mật liên quan |
| Trả 400 khi thiếu `limit` hoặc gửi `limit=abc` | Đầu vào bắt buộc và chuyển đổi kiểu |
| Reflection vẫn thấy `arg0`, `isNamePresent()=false` sau khi sửa build | Class cũ, cấu hình áp dụng sai module hoặc metadata bị loại sau biên dịch |

Bảng là hướng điều tra, không phải quy tắc chẩn đoán chỉ từ mã HTTP. Ví dụ, tầng bảo mật hoặc proxy có thể trả phản hồi trước khi yêu cầu tới thao tác Actuator.

Thêm `-parameters` không tự đăng ký bean, không tự phơi bày endpoint và không cấp quyền truy cập. Ngược lại, mở exposure cũng không tạo lại metadata đã thiếu trong class.

## 8. Tên tham số là một phần hợp đồng đầu vào

Giả sử endpoint ban đầu nhận `cacheName`. Một công cụ vận hành đang gọi `?cacheName=inventory&limit=5`. Nếu đổi tên tham số Java thành `cache` rồi biên dịch lại với `-parameters`, tên đầu vào được suy ra cũng thay đổi.

Lời gọi Java trực tiếp vẫn có thể tiếp tục biên dịch vì kiểu và thứ tự tham số không đổi. Công cụ vận hành gửi tên cũ lại có thể bị báo thiếu đầu vào mới. Vì vậy:

- Đặt tên tham số rõ nghĩa trước khi công bố thao tác.
- Xem việc đổi tên là thay đổi có thể ảnh hưởng người gọi HTTP/JMX.
- Kiểm tra yêu cầu bằng tên công khai, không chỉ gọi phương thức Java trong bài kiểm thử.
- Đồng bộ ví dụ lệnh, tài liệu vận hành và bên gọi khi thay đổi hợp đồng.

Không coi `-parameters` là cơ chế kiểm tra tính hợp lệ nghiệp vụ. Ví dụ, `limit=-5` vẫn chuyển đổi được thành `int`; nếu giá trị đó không hợp lệ với bài toán thật, ứng dụng phải kiểm tra riêng. Cờ này cung cấp thông tin tên, không suy ra khoảng giá trị cho phép.

## 9. Tự kiểm tra

1. Vì sao `inspect("inventory", 5)` vẫn chạy khi Reflection chỉ thấy `arg0`, `arg1`?
2. Trong ví dụ, bật `-g` có làm `isNamePresent()` trả về `true` không?
3. Tại sao thêm cờ ở module ứng dụng không sửa được một lớp endpoint nằm trong JAR thư viện đã biên dịch?
4. Một yêu cầu thiếu `limit` trả 400 có đủ để kết luận dự án thiếu `-parameters` không?
5. Nếu đổi `cacheName` thành `cache`, cần kiểm tra thêm điều gì ngoài việc build Java thành công?

Đối chiếu câu trả lời:

1. Java truyền đối số theo vị trí và kiểu; lời gọi trực tiếp không cần tên tham số nguồn.
2. Không. Với phương thức thông thường trong thí nghiệm, cần `-parameters` để giữ tên cho Reflection.
3. Module ứng dụng không tái biên dịch bytecode đã có trong dependency; phải sửa nơi tạo class.
4. Không. Đó có thể là lỗi thiếu đầu vào ở một thao tác đã được phát hiện đúng.
5. Kiểm tra tên đầu vào mà công cụ vận hành đang gửi, thử lại HTTP/JMX và cập nhật tài liệu liên quan.

Sau bài này, hãy tự xác nhận ba bằng chứng trên cùng một bản build: tên tham số hiện diện trong class, thao tác được phát hiện thành công và yêu cầu có tên đúng được ánh xạ vào đúng tham số.
