# Kiểm tra yêu cầu Java và khả năng hỗ trợ record theo phiên bản

Khi dùng Jackson để chuyển đổi JSON thành đối tượng Java, chọn đúng phiên bản thư viện chỉ là một phần của bài toán. Môi trường chạy phải hiểu bytecode của ứng dụng, compiler phải hỗ trợ cú pháp Java đang dùng, cấu hình build phải cho phép đúng mức ngôn ngữ và phiên bản Jackson phải có khả năng ánh xạ kiểu dữ liệu đó.

Bài học này tập trung vào cách kiểm tra những điều kiện ấy, đặc biệt với **Java record**. Record là kiểu dữ liệu thường được dùng làm DTO bất biến; khi deserialize, Jackson cần nhận diện record component và gọi canonical constructor để tạo đối tượng.

## 1. Phân biệt yêu cầu Java và khả năng của Jackson

Có hai câu hỏi độc lập cần trả lời:

1. **Java có hỗ trợ cú pháp và bytecode của ứng dụng không?** Điều này phụ thuộc JDK dùng để biên dịch, cấu hình source/release và JRE/JDK dùng để chạy.
2. **Phiên bản Jackson có hỗ trợ ánh xạ kiểu dữ liệu đó không?** Điều này phụ thuộc phiên bản jackson-databind, các module đi kèm và cấu hình mapper.

Một dự án có thể chạy trên JDK mới nhưng vẫn dùng Jackson quá cũ để ánh xạ record. Ngược lại, Jackson có hỗ trợ record nhưng compiler của dự án vẫn đặt --release ở mức Java 11, nên source code khai báo record không thể biên dịch.

Có thể hình dung chuỗi tương thích như sau:

```text
Mã nguồn Java
    │
    ▼
JDK/compiler + source/release
    │
    ▼
Bytecode của ứng dụng
    │
    ▼
JRE/JDK thực tế khi chạy
    │
    ▼
Jackson databind + core + annotations + modules
    │
    ▼
Ánh xạ JSON ↔ Java record
```

Mỗi tầng có điều kiện riêng. Chỉ nhìn kết quả java -version là chưa đủ để kết luận toàn bộ dự án có hỗ trợ record.

## 2. Record được Java hỗ trợ từ phiên bản nào?

Record là một dạng class đặc biệt, phù hợp để biểu diễn dữ liệu có trạng thái cố định. Java tạo sẵn các thành phần theo record component, gồm accessor, equals, hashCode, toString và canonical constructor.

Ví dụ:

```java
public record UserDto(long id, String displayName) {}
```

Record có các mốc phiên bản quan trọng:

| Phiên bản Java | Trạng thái record | Ý nghĩa khi phát triển |
| --- | --- | --- |
| Java 8–13 | Chưa có record trong ngôn ngữ chuẩn | Không thể khai báo record bằng compiler Java thông thường |
| Java 14 | Preview lần thứ nhất | Phải bật preview khi biên dịch và chạy; không nên xem là nền tảng ổn định |
| Java 15 | Preview lần thứ hai | Vẫn phụ thuộc preview và đúng phiên bản JDK tương ứng |
| Java 16 trở lên | Chính thức (final) | Có thể dùng record mà không cần bật preview |

Record được giới thiệu dưới dạng preview ở Java 14 và Java 15, sau đó trở thành tính năng chính thức từ Java 16. Với dự án mới hoặc mã nguồn cần ổn định lâu dài, hãy dùng Java 16 trở lên; trong hệ thống thực tế, nên theo LTS mà dự án đã chọn, chẳng hạn Java 17 hoặc Java 21.

Không nên chọn Java 14/15 preview chỉ để thử record trong ứng dụng đang triển khai. Preview feature có thể thay đổi giữa các bản JDK và cần bật cờ tương ứng ở cả compile lẫn runtime. Nếu ứng dụng cần hỗ trợ nhiều môi trường, dùng record chính thức từ Java 16 trở lên sẽ dễ kiểm soát hơn.

### 2.1. Record khác class DTO thông thường như thế nào?

Một DTO class truyền thống có thể được khai báo như sau:

```java
public class UserDto {
    private final long id;
    private final String displayName;

    public UserDto(long id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Cùng dữ liệu đó, record ngắn gọn hơn:

```java
public record UserDto(long id, String displayName) {}
```

Record phù hợp khi dữ liệu được xem như một giá trị, không cần thay đổi trạng thái sau khi tạo. Các component của record là final và record không được kế thừa từ class khác. Record vẫn có thể triển khai interface, khai báo method bổ sung và kiểm tra dữ liệu trong compact constructor.

Jackson cần đọc được tên component và tạo record qua canonical constructor. Cách này khác với nhiều JavaBean mutable vốn thường được tạo bằng constructor rỗng rồi gán property qua setter.

## 3. Jackson hỗ trợ record từ phiên bản nào?

Khả năng hỗ trợ record tích hợp trong Jackson Databind được bổ sung từ **Jackson 2.12**. Với Jackson 2.12 trở lên và Java runtime có record chính thức (Java 16+), Jackson có thể nhận diện record component và deserialize qua canonical constructor mà không cần viết custom deserializer cho trường hợp thông thường.

Bảng định hướng:

| Jackson | Hỗ trợ record tích hợp | Cách hiểu |
| --- | --- | --- |
| Jackson trước 2.12 | Chưa có hỗ trợ record tích hợp như các bản mới | Không nên giả định ObjectMapper có thể bind record theo cách thông thường |
| Jackson 2.12 trở lên | Có hỗ trợ record | Dùng được với record khi môi trường Java và cấu hình tương thích |
| Jackson 3.x | Tiếp tục hỗ trợ record; yêu cầu Java tối thiểu cao hơn | Cần kiểm tra hướng dẫn nâng cấp và namespace API của major version mới |

**Điều kiện thực tế để dùng record an toàn:** mã nguồn dùng record được biên dịch bằng Java 16 trở lên, ứng dụng chạy trên Java 16 trở lên, và jackson-databind từ 2.12 trở lên. Nếu dự án chọn Jackson 3.x, cần đáp ứng baseline Java của dòng 3.x (Java 17 trở lên) và xử lý các thay đổi API/package khi nâng cấp.

Bảng này mô tả mốc tính năng record, không thay thế bảng tương thích đầy đủ của từng release. Mỗi phiên bản Jackson còn có yêu cầu JDK tối thiểu riêng, có thể thay đổi theo release line. Khi kiểm tra dự án cụ thể, hãy xem metadata của artifact và release notes đúng phiên bản đang định dùng.

### 3.1. Vì sao cần jackson-databind?

Jackson thường được chia thành ba artifact:

- **jackson-core**: parser và generator, làm việc ở mức token JSON.
- **jackson-annotations**: các annotation mô tả quy tắc mapping.
- **jackson-databind**: ánh xạ giữa JSON và Java object, bao gồm ObjectMapper và khả năng record binding.

Mốc hỗ trợ record tích hợp gắn với Databind. Chỉ nhìn thấy jackson-core trong dependency tree không chứng minh ứng dụng có record data binding. Cần xác định phiên bản jackson-databind thực tế trên runtime classpath.

Các artifact liên quan cần được quản lý phiên bản nhất quán. Không nên tùy tiện dùng jackson-databind của một minor release cùng jackson-core hoặc jackson-annotations của minor release khác.

### 3.2. Record không cần constructor rỗng

Với record:

```java
public record ProductDto(
    long id,
    String name,
    BigDecimal price
) {}
```

Jackson dùng canonical constructor tương ứng với danh sách component để tạo đối tượng. Đây là lý do record có thể deserialize dù không khai báo constructor rỗng, setter hoặc field mutable.

Thông thường, không cần thêm @JsonCreator chỉ để Jackson nhận diện canonical constructor của record. Chỉ bổ sung annotation khi cần mô tả mapping đặc biệt hoặc giải quyết một quy tắc cụ thể.

Tên component của record được Java cung cấp qua metadata record. Điều này khác với class thông thường có constructor nhiều tham số, nơi việc nhận diện tên tham số có thể phụ thuộc compiler flag, annotation hoặc module hỗ trợ parameter names. Không nên nhầm hỗ trợ record với ParameterNamesModule.

## 4. Ma trận kiểm tra nhanh Java và Jackson

Khi đọc một cấu hình dự án, có thể dùng bảng sau để định hướng:

| Điều kiện | Kết luận |
| --- | --- |
| Java 11 + Jackson 2.12+ | Jackson có tính năng record nhưng Java 11 không biên dịch/chạy record chính thức; chưa đủ điều kiện |
| Java 16+ + Jackson trước 2.12 | Java hiểu record nhưng Databind cũ chưa có hỗ trợ record tích hợp; cần nâng Jackson hoặc dùng cách mapping khác |
| Java 16+ + Jackson 2.12+ | Đủ điều kiện cơ bản cho record binding; vẫn phải kiểm tra dependency thực tế và cấu hình |
| Java 17+ + Jackson 3.x | Phù hợp baseline Java của Jackson 3.x; cần xử lý thay đổi major version |
| Compiler JDK 21 nhưng --release 11 | Không thể khai báo record trong source đang được biên dịch theo release 11 |
| Compile bằng Java 21, chạy bằng Java 11 | Có thể gặp UnsupportedClassVersionError nếu bytecode được tạo cho Java 16/17/21 |

Ma trận này chỉ đánh giá điều kiện chính. Một ứng dụng vẫn có thể lỗi nếu runtime classpath chứa nhiều phiên bản Jackson, module cần thiết chưa được đăng ký, hoặc Spring Boot cung cấp một mapper có cấu hình khác với mapper trong ví dụ độc lập.

## 5. Kiểm tra Java đang thực sự được sử dụng

Hãy kiểm tra riêng JDK của terminal, build tool và ứng dụng. Các lệnh sau có thể chạy từ thư mục dự án.

### 5.1. Kiểm tra Java và compiler

```bash
java -version
javac -version
```

- java -version cho biết Java runtime mà lệnh java trong PATH đang gọi.
- javac -version cho biết compiler mà lệnh javac trong PATH đang gọi.

Hai lệnh này có thể trả về phiên bản khác nhau nếu máy có nhiều JDK hoặc PATH được cấu hình không nhất quán. Nếu javac không tồn tại, terminal có thể chỉ đang trỏ tới JRE hoặc chưa cấu hình JDK đúng cách.

### 5.2. Kiểm tra JDK mà Gradle sử dụng

Với Gradle Wrapper trên Linux/macOS:

```bash
./gradlew -version
```

Với Windows PowerShell:

```powershell
.\gradlew.bat -version
```

Kết quả hiển thị phiên bản Gradle và JVM đang chạy Gradle. Đây là JVM của Gradle daemon, chưa chắc là compiler JDK nếu dự án cấu hình Java Toolchain riêng.

Nếu dự án dùng Java plugin, có thể kiểm tra các toolchain được Gradle phát hiện bằng task tương ứng:

```bash
./gradlew javaToolchains
```

Đọc thêm build.gradle, build.gradle.kts, convention plugin và cấu hình trong gradle.properties để biết dự án chọn toolchain nào. Đừng kết luận compiler dùng cùng JDK với Gradle chỉ từ gradlew -version.

### 5.3. Kiểm tra JDK mà Maven sử dụng

```bash
mvn -version
```

Kết quả cho biết Maven đang chạy bằng Java nào. Sau đó kiểm tra pom.xml, Maven Compiler Plugin, Maven Toolchains Plugin (nếu có) và cấu hình parent/BOM. Maven chạy trên một JDK không có nghĩa compiler đã được cấu hình đúng cho release mà dự án yêu cầu.

### 5.4. Phân biệt bốn mức phiên bản

| Mức | Câu hỏi cần trả lời |
| --- | --- |
| Build JVM | Gradle/Maven đang chạy bằng JDK nào? |
| Compiler/toolchain | JDK nào thực hiện biên dịch source? |
| Source/release | Source được phép dùng cú pháp Java đến phiên bản nào? |
| Runtime JVM | Môi trường triển khai dùng Java nào để chạy bytecode? |

Ví dụ, máy phát triển có JDK 21 nhưng Gradle toolchain chọn JDK 17 và options.release = 17. Kết quả là source chỉ được dùng API/cú pháp thuộc Java 17, bytecode tương thích với Java 17; việc terminal có JDK 21 không làm ứng dụng tự động trở thành Java 21.

## 6. Kiểm tra cấu hình Java trong Gradle

### 6.1. Java Toolchain

Cấu hình toolchain chọn compiler JDK:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Đoạn cấu hình này yêu cầu Gradle dùng toolchain Java 17 cho các tác vụ Java liên quan. Toolchain có thể được cài sẵn hoặc được Gradle provision theo cấu hình môi trường.

Toolchain trả lời câu hỏi **dùng JDK nào để biên dịch**. Nó không tự giải quyết mọi yêu cầu của runtime triển khai và không thay thế việc xác định bytecode target.

### 6.2. Cấu hình release

Có thể giới hạn ngôn ngữ, API chuẩn và bytecode bằng options.release:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Khi cần, kết hợp toolchain và release để có cấu hình rõ ràng:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Nếu dùng record chính thức, release phải từ Java 16 trở lên. Chọn Java 17 hoặc 21 tùy baseline của ứng dụng.

### 6.3. SourceCompatibility và targetCompatibility

Một số dự án cấu hình:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
```

Hai thuộc tính này mô tả mức source và mục tiêu bytecode trong cấu hình Gradle. Chúng không tự chọn compiler JDK. Ngoài ra, chỉ đặt source/target không có đầy đủ tác dụng giới hạn API nền tảng như --release; với JDK hiện đại, options.release thường diễn đạt mục tiêu tương thích rõ hơn.

Đọc cấu hình cuối cùng sau khi convention plugin áp dụng, vì module có thể kế thừa hoặc bị ghi đè bởi plugin dùng chung. Nếu nhiều file cấu hình cùng tồn tại, không chỉ đọc một dòng trong build.gradle của module rồi kết luận.

## 7. Kiểm tra cấu hình Java trong Maven

Maven thường khai báo mức Java qua property:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Property này được Maven Compiler Plugin sử dụng để biên dịch theo release 17. Dự án cũ có thể dùng maven.compiler.source và maven.compiler.target; hãy kiểm tra plugin version và cấu hình effective POM để biết giá trị cuối cùng.

Có thể xem cấu hình sau khi parent POM và profile được áp dụng:

```bash
mvn help:effective-pom
```

Nếu dự án sử dụng Maven Toolchains, hãy kiểm tra toolchains.xml và cấu hình plugin tương ứng. mvn -version chỉ cho biết JVM đang chạy Maven, còn toolchain có thể chọn JDK khác cho compiler.

## 8. Kiểm tra phiên bản Jackson thực tế

Không nên chỉ nhìn version được khai báo trực tiếp trong một file. Dependency có thể được kế thừa từ Spring Boot, Jackson BOM, convention plugin hoặc dependency bắc cầu của thư viện khác.

### 8.1. Gradle: xem dependency tree

Để xem dependency runtime:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để truy ra dependency nào đưa jackson-databind vào và phiên bản nào được chọn:

```bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Nếu cần kiểm tra module khác, chạy tương tự với tên dependency như jackson-core, jackson-annotations hoặc jackson-datatype-jsr310.

Đọc cả các thông tin sau:

- Phiên bản được yêu cầu trực tiếp.
- Phiên bản cuối cùng Gradle đã chọn.
- Dependency nào yêu cầu phiên bản khác.
- Có rule, constraint, platform/BOM hoặc resolution strategy nào thay đổi kết quả không.
- compileClasspath và runtimeClasspath có khác nhau không.

Đối với lỗi chỉ xuất hiện khi chạy ứng dụng, runtime classpath là dữ liệu đặc biệt quan trọng. Một compile classpath đúng không đảm bảo runtime classpath cũng đúng nếu có cấu hình riêng.

### 8.2. Maven: xem dependency tree

Dùng:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Có thể mở rộng bộ lọc cho các artifact Jackson khác hoặc xem toàn bộ dependency tree. Kiểm tra các dòng conflict/omitted để hiểu Maven đã chọn phiên bản nào.

Để xem cấu hình sau khi parent POM, profile và dependency management được hợp nhất, dùng effective POM:

```bash
mvn help:effective-pom
```

### 8.3. Spring Boot và BOM

Spring Boot thường quản lý phiên bản Jackson thông qua dependency management. Nếu ứng dụng đã dùng Spring Boot BOM, hãy ưu tiên để BOM quản lý các artifact liên quan thay vì đặt version riêng cho từng module.

Ví dụ, việc chỉ nâng jackson-databind mà giữ jackson-core hoặc jackson-annotations ở phiên bản cũ có thể gây lỗi tương thích ở runtime. Khi cần override, hãy dùng cơ chế quản lý phiên bản nhất quán và kiểm tra lại toàn bộ dependency tree.

Tên dependency khai báo trong build.gradle hoặc pom.xml không nhất thiết là phiên bản cuối cùng được nạp. **Phiên bản được resolve trên classpath mới là thứ ứng dụng thực sự sử dụng.**

## 9. Thử nghiệm record với Jackson

Sau khi xác nhận Java và Jackson đáp ứng điều kiện, hãy tạo một phép thử nhỏ để kiểm tra cả hai chiều serialize và deserialize.

### 9.1. Record mẫu

```java
import java.math.BigDecimal;

public record ProductDto(
    long id,
    String name,
    BigDecimal price
) {}
```

### 9.2. Kiểm tra round-trip

```java
ObjectMapper mapper = new ObjectMapper();

ProductDto original = new ProductDto(
    101L,
    "Keyboard",
    new BigDecimal("1250000.00")
);

String json = mapper.writeValueAsString(original);

ProductDto restored = mapper.readValue(json, ProductDto.class);

if (!original.equals(restored)) {
    throw new IllegalStateException("Record round-trip failed");
}
```

Phép thử này kiểm tra:

1. Compiler có chấp nhận cú pháp record không.
2. Runtime có thể nạp và khởi tạo record không.
3. Jackson có serialize record component thành JSON không.
4. Jackson có deserialize JSON qua canonical constructor không.
5. Kiểu dữ liệu như BigDecimal có được giữ phù hợp không.

Với record đơn giản, ObjectMapper đã được cấu hình đúng thường có thể thực hiện mapping mà không cần setter hoặc constructor rỗng.

### 9.3. Kiểm tra bằng JUnit

Có thể chuyển phép thử thành test tự động:

```java
class RecordMappingTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void shouldSerializeAndDeserializeRecord() throws Exception {
        ProductDto original = new ProductDto(
            101L,
            "Keyboard",
            new BigDecimal("1250000.00")
        );

        String json = mapper.writeValueAsString(original);
        ProductDto restored = mapper.readValue(json, ProductDto.class);

        assertEquals(original, restored);
    }
}
```

Trong ứng dụng Spring Boot, nên có thêm một test dùng đúng bean ObjectMapper được inject từ Spring context. Cách đó kiểm tra cấu hình thật của ứng dụng, bao gồm module, customizer và các tùy chọn do Spring Boot áp dụng.

### 9.4. Kiểm tra tên JSON khác tên component

Record vẫn có thể dùng annotation để biểu diễn hợp đồng JSON:

```java
public record UserRequest(
    long id,
    @JsonProperty("display_name") String displayName
) {}
```

JSON tương ứng:

```json
{
  "id": 42,
  "display_name": "An"
}
```

Nếu dùng tên JSON cũ trong giai đoạn chuyển đổi, có thể cân nhắc @JsonAlias để chấp nhận tên thay thế khi đọc. Hãy kiểm thử cả tên chuẩn và tên tương thích; đừng suy luận rằng serializer sẽ ghi ra mọi alias.

## 10. Lưu ý khi dùng record với các kiểu dữ liệu khác

### 10.1. Collection và generic

Record có thể chứa collection hoặc generic như class thông thường:

```java
public record OrderDto(
    long id,
    List<String> items,
    Map<String, String> attributes
) {}
```

Jackson vẫn cần thông tin kiểu generic chính xác. Khi đọc trực tiếp JSON thành collection generic độc lập, dùng TypeReference hoặc JavaType; record support không loại bỏ vấn đề type erasure.

### 10.2. Ngày giờ Java

Record có component thuộc java.time:

```java
public record EventDto(
    String name,
    LocalDate eventDate,
    Instant createdAt
) {}
```

Trong Jackson 2.x, module thường dùng cho Java Time là jackson-datatype-jsr310 với JavaTimeModule. Cần bảo đảm module được đăng ký trong mapper độc lập hoặc được cấu hình đúng trong Spring Boot.

```java
ObjectMapper mapper = new ObjectMapper()
    .registerModule(new JavaTimeModule());
```

Record binding và Java Time binding là hai khả năng khác nhau. Jackson nhận diện được canonical constructor không đồng nghĩa mọi component kiểu mở rộng đã có serializer/deserializer phù hợp.

### 10.3. Null và giá trị primitive

Record có thể có component primitive:

```java
public record AccountDto(long id, boolean active) {}
```

Primitive không thể chứa null. Nếu JSON gửi null hoặc thiếu property, kết quả phụ thuộc feature và cấu hình deserialization. Với dữ liệu đầu vào cần phân biệt thiếu, null và giá trị mặc định, hãy cân nhắc wrapper type như Long, Boolean, hoặc thiết kế request model rõ ràng.

Không dùng giá trị mặc định do Java tạo ra để thay cho validation. Sau khi Jackson tạo DTO, ứng dụng vẫn cần kiểm tra dữ liệu theo quy tắc nghiệp vụ.

## 11. Jackson 2.x và 3.x: lưu ý khi nâng cấp

Major version có thể thay đổi yêu cầu Java, package, API và cách tích hợp framework. Đừng xem việc đổi một số version trong dependency là nâng cấp hoàn chỉnh.

| Nội dung | Jackson 2.x | Jackson 3.x |
| --- | --- | --- |
| Java baseline | Phụ thuộc release cụ thể của dòng 2.x; nhiều ứng dụng dùng Java 8+ nhưng phải kiểm tra đúng artifact | Java 17 trở lên |
| Namespace phổ biến | com.fasterxml.jackson.* | tools.jackson.* |
| Record | Hỗ trợ tích hợp từ 2.12 | Tiếp tục hỗ trợ |
| Nâng cấp | Giữ hệ sinh thái 2.x và kiểm tra minor/patch alignment | Là major upgrade, cần kiểm tra migration guide và tương thích framework |

Khi nâng cấp từ 2.x lên 3.x:

1. Xác định Java runtime tối thiểu của ứng dụng và môi trường triển khai.
2. Kiểm tra phiên bản Spring Boot/framework có hỗ trợ dòng Jackson mới hay không.
3. Đọc migration guide chính thức của Jackson cho major version đích.
4. Rà soát package import, dependency coordinates, module và custom serializer/deserializer.
5. Kiểm tra API đã deprecated hoặc thay đổi hành vi.
6. Chạy test serialize/deserialize cho DTO, record, collection, ngày giờ, enum, polymorphism và payload cũ.
7. Kiểm tra runtime dependency tree để bảo đảm không trộn artifact 2.x và 3.x.

Không nên tự ý nâng riêng Jackson trong ứng dụng Spring Boot đang chạy ổn định mà chưa xác minh ma trận tương thích của Spring Boot. Framework có thể phụ thuộc vào API của một major version cụ thể.

## 12. Nhận biết lỗi do sai phiên bản hoặc sai môi trường

Một số dấu hiệu thường gặp:

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Compiler báo không nhận diện từ khóa record | JDK compiler cũ hoặc source/release quá thấp | Kiểm tra javac -version, toolchain và options.release/maven.compiler.release |
| UnsupportedClassVersionError | Runtime JVM thấp hơn mức bytecode cần | Kiểm tra Java chạy ứng dụng và major version của class |
| Jackson không tạo được record | Databind cũ, class không phải record ở runtime hoặc mapping/constructor không tương thích | Kiểm tra runtime jackson-databind, JDK và kiểu JSON |
| NoSuchMethodError trong package Jackson | Các artifact Jackson không đồng bộ hoặc thư viện kỳ vọng API khác | Xem dependency tree của core, annotations, databind và module |
| ClassNotFoundException hoặc NoClassDefFoundError | Thiếu artifact/module hoặc classpath khác môi trường build | Kiểm tra runtime classpath và dependency đóng gói |
| Lỗi với LocalDate/Instant | Chưa có hoặc chưa đăng ký Java Time module, định dạng không phù hợp | Kiểm tra jackson-datatype-jsr310 và cấu hình mapper |
| Test dùng mapper tự tạo chạy nhưng API Spring Boot lỗi | Mapper của test không giống bean runtime hoặc customizer của ứng dụng | Viết test qua Spring context và inject mapper thật |

Không nên chỉ dựa vào tên exception để kết luận nguyên nhân. Hãy đọc phần Caused by, class/package xuất hiện trong stack trace và phiên bản artifact thực tế được nạp.

### 12.1. Kiểm tra bytecode khi nghi ngờ runtime quá cũ

Có thể xem major version của class bằng javap:

```bash
javap -verbose -classpath build/classes/java/main com.example.UserDto
```

Một số major version thường gặp:

| Java | Class file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ, class file major version 61 cần runtime Java 17 trở lên. Nếu chạy trên Java 11, runtime không thể nạp class đó và có thể phát sinh UnsupportedClassVersionError.

Với record, việc kiểm tra bytecode hữu ích khi compiler mới tạo class nhưng môi trường triển khai vẫn dùng JDK cũ. Hãy kiểm tra đúng class của ứng dụng hoặc thư viện gây lỗi, không chỉ class mẫu trong test.

## 13. Quy trình xác minh trước khi chọn record

Khi bắt đầu một module hoặc nâng cấp dependency, thực hiện theo thứ tự:

### Bước 1 — Xác định runtime triển khai

Ghi lại JDK ở máy local, CI, container và môi trường chạy thật. Nếu các môi trường khác nhau, lấy môi trường thấp nhất làm giới hạn tương thích.

### Bước 2 — Xác định compiler và release

Đọc Gradle toolchain hoặc Maven toolchain, cùng options.release hay maven.compiler.release. Đảm bảo mức release đủ để biên dịch record chính thức.

### Bước 3 — Xác định phiên bản Jackson được resolve

Kiểm tra jackson-databind, jackson-core, jackson-annotations và module liên quan trên runtime classpath. Tìm nguồn version từ BOM, Spring Boot, dependency constraint hoặc override.

### Bước 4 — Đối chiếu mốc record

Nếu dùng record, cần Java 16+ và Jackson Databind 2.12+ (hoặc major version mới tương thích với baseline Java của nó). Với Jackson 3.x, xác nhận Java 17+ và hướng dẫn migration.

### Bước 5 — Viết test trên mapper thực tế

Test serialize/deserialize một record đơn giản. Nếu chạy trong Spring Boot, inject bean ObjectMapper thật. Thêm test cho generic, ngày giờ, null, tên JSON và payload cũ nếu ứng dụng có dùng các trường hợp đó.

### Bước 6 — Kiểm tra sau khi đóng gói

Xác minh Java runtime và dependency trong artifact/container giống cấu hình đã kiểm thử. Một build thành công trên máy phát triển chưa đủ chứng minh môi trường triển khai tương thích.

## 14. Checklist lựa chọn Java và Jackson

Trước khi quyết định dùng record, có thể tự trả lời:

- [ ] JDK chạy ứng dụng có phải Java 16 trở lên không?
- [ ] JDK compiler/toolchain có hỗ trợ record không?
- [ ] Source/release có được đặt từ Java 16 trở lên không?
- [ ] CI và môi trường triển khai có cùng đáp ứng mức Java đó không?
- [ ] Runtime classpath có jackson-databind từ 2.12 trở lên không?
- [ ] jackson-core, jackson-annotations và các Jackson module có được quản lý phiên bản nhất quán không?
- [ ] Nếu dùng Jackson 3.x, dự án đã đáp ứng Java 17+ và migration requirements chưa?
- [ ] Test dùng đúng ObjectMapper của ứng dụng có chạy thành công không?
- [ ] Các component kiểu ngày giờ, collection, generic, null và enum đã được kiểm tra chưa?

Nếu có một điều kiện chưa xác minh, hãy ghi nhận nó là điểm chưa chắc chắn thay vì kết luận dự án đã hỗ trợ record.

## 15. Bài thực hành

Giả sử một ứng dụng Spring Boot nhận JSON để tạo người dùng. Hãy thực hiện các bước sau:

1. Chạy java -version, javac -version và lệnh hiển thị JVM của Gradle/Maven.
2. Tìm cấu hình toolchain và release trong build file hoặc convention plugin.
3. Xem dependency tree để xác định phiên bản jackson-databind được resolve.
4. Tạo UserRequest dạng record gồm username, email và createdAt.
5. Serialize record thành JSON và deserialize JSON trở lại.
6. Đăng ký Java Time module nếu mapper không tự cấu hình module này.
7. Viết test qua Spring context để dùng mapper thật của ứng dụng.
8. Hạ release về Java 11 trong một nhánh thử nghiệm và quan sát compiler từ chối cú pháp record.
9. Dùng dependency tree để xác định liệu một thư viện khác có đang kéo phiên bản Jackson cũ vào hay không.
10. Viết kết luận nêu rõ JDK runtime, compiler release, Jackson Databind, module liên quan và kết quả test.

Bài thực hành hoàn thành khi có thể giải thích vì sao ứng dụng hỗ trợ hoặc chưa hỗ trợ record ở từng tầng, đồng thời chỉ ra bằng chứng từ cấu hình build và dependency tree.

## 16. Nguyên tắc ghi nhớ

- Record là tính năng Java preview ở Java 14/15 và chính thức từ Java 16.
- Jackson Databind có hỗ trợ record tích hợp từ phiên bản 2.12.
- Dùng record chính thức cần compiler và runtime Java 16 trở lên; Jackson 3.x yêu cầu Java 17 trở lên.
- JDK chạy Gradle/Maven, compiler toolchain, source/release và runtime triển khai là các giá trị có thể khác nhau.
- Phiên bản khai báo trong build file chưa chắc là phiên bản thực tế được resolve.
- Giữ các artifact Jackson cùng hệ phiên bản bằng BOM hoặc dependency management phù hợp.
- Với Spring Boot, kiểm tra mapper được framework cấu hình và phiên bản Jackson do BOM quản lý.
- Kiểm tra bằng test round-trip trên runtime classpath thực tế trước khi kết luận tính tương thích.

Khi xác minh khả năng hỗ trợ record, hãy đi từ JDK và cấu hình biên dịch đến Jackson Databind được resolve, rồi kết thúc bằng một test chạy trên đúng môi trường của ứng dụng.
