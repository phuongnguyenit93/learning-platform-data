# Đối chiếu tài liệu đúng phiên bản và nhận diện hướng dẫn bootstrap cũ

## 1. Mục tiêu và phạm vi

Khi học **Spring Boot Externalized Configuration**, nhiều tài liệu trên Internet đều sử dụng các từ quen thuộc như `application.yml`, `bootstrap.yml`, `spring.profiles.active`, `spring.cloud.config.uri` và `spring.config.import`. Tuy nhiên, **cùng một hướng dẫn không nhất thiết đúng cho mọi phiên bản Spring Boot và Spring Cloud**.

Một đoạn hướng dẫn có thể từng hoạt động tốt trên Spring Boot 2.2/2.3 với Spring Cloud Hoxton, nhưng không còn là cách cấu hình mặc định khi ứng dụng chuyển sang Spring Boot 2.4+ và các thế hệ Spring Cloud tương ứng. Cũng có trường hợp một hướng dẫn nói về **Spring Cloud bootstrap context**, trong khi người đọc lại tưởng nó mô tả **bootstrap của Spring Boot** nói chung.

Bài học này giúp bạn:

1. Xác định **Spring Boot, Spring Framework, Java, Spring Cloud release train và module Config Client** mà dự án thực sự sử dụng.
2. Hiểu bước ngoặt của **Config Data** từ Spring Boot **2.4** và ý nghĩa của `spring.config.import`.
3. Phân biệt cơ chế **Spring Cloud bootstrap context / bootstrap.yml** với cơ chế Config Data chuẩn.
4. Nhận diện ví dụ **bootstrap cũ**, ví dụ **Config Data mới**, và trường hợp cố tình bật chế độ tương thích cũ.
5. Đọc đúng **tài liệu tham chiếu của phiên bản đang chạy**, không sao chép từ tài liệu mới nhất vào dự án cũ hoặc ngược lại.
6. Xây quy trình nâng cấp, kiểm tra profile, precedence, nguồn remote, xử lý lỗi startup và testing.
7. Biết khi nào nên **giữ bootstrap có chủ đích**, khi nào nên **chuyển sang Config Data**, và khi nào phải hoãn thay đổi cho tới khi xác minh đầy đủ dependency.

Phạm vi chính của bài là Spring Boot và Spring Cloud Config Client; các tích hợp Vault, Consul, Kubernetes, AWS hoặc nguồn cấu hình tùy biến có thể có quy tắc bổ sung theo thư viện và phiên bản của chúng.

**Nguyên tắc xuyên suốt: đọc phiên bản trước, chọn cơ chế sau, rồi thử nghiệm trên đúng artifact thực tế.**

---

## 2. Tình huống thường gặp: sao chép bootstrap.yml nhưng ứng dụng không nhận cấu hình

Một hướng dẫn cũ có thể viết:

```yaml
# bootstrap.yml
spring:
  application:
    name: order-service
  cloud:
    config:
      uri: http://localhost:8888
```

Người học sao chép file vào:

```text
src/main/resources/bootstrap.yml
```

rồi nâng cấp Spring Boot hoặc Spring Cloud và chạy:

```bash
java -jar order-service.jar
```

Kết quả có thể là:

- Ứng dụng không lấy được thuộc tính từ Config Server.
- Spring Cloud Config Client báo thiếu `spring.config.import`.
- Một số biến môi trường vẫn hoạt động, khiến người học tưởng file bootstrap đã được đọc.
- Một profile-specific setting không được áp dụng như ở bản cũ.
- Hoặc ứng dụng vẫn chạy được vì **legacy bootstrap đã được bật** thông qua một dependency khác.

Không có một kết luận duy nhất cho tất cả các trường hợp. Hãy phân loại:

| Câu hỏi | Điều phải xác minh |
| --- | --- |
| Dự án dùng Spring Boot bao nhiêu? | Chính xác major/minor/patch trong build và artifact |
| Dự án dùng Spring Cloud release train nào? | Spring Cloud BOM thực tế |
| Có Spring Cloud Config Client không? | Dependency runtime `spring-cloud-starter-config` hoặc module liên quan |
| Có bật legacy bootstrap không? | `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled` được cấp sớm |
| Có khai báo `spring.config.import` không? | Vị trí và giá trị property |
| Có Config Data resolver cho `configserver:` không? | Dependency, bootstrap mode và cấu hình phù hợp |
| Có profile/nguồn ưu tiên cao hơn không? | Active profiles, Config Data, CLI, environment |
| Log thể hiện điều gì? | Lỗi nạp, binding, conversion, validation hoặc networking |

Một README hướng dẫn đáng tin cậy phải nêu **điều kiện phiên bản và dependency**, chứ không chỉ đưa một file YAML thiếu bối cảnh.

## 3. Hai chữ “bootstrap” không phải lúc nào cũng chỉ cùng một thứ

Từ *bootstrap* xuất hiện trong nhiều ngữ cảnh:

### 3.1. Bootstrap theo nghĩa chung

Một ứng dụng Java cần khởi động JVM, tạo SpringApplication, chuẩn bị Environment, khởi tạo ApplicationContext, đăng ký bean và chạy lifecycle. Người ta có thể gọi toàn bộ quá trình này là *application bootstrap* theo nghĩa chung.

### 3.2. Spring Cloud legacy bootstrap context

Trong các thế hệ Spring Cloud cũ, **bootstrap context** là một giai đoạn/context đặc biệt hỗ trợ lấy cấu hình sớm, đặc biệt từ Spring Cloud Config Server.

Tệp `bootstrap.yml` hoặc `bootstrap.properties` thường được dùng trong hướng dẫn cho mô hình này.

### 3.3. Spring Boot bootstrap registry / bootstrap context API

Spring Boot có các API như `BootstrapRegistryInitializer` dùng để đăng ký đối tượng sớm cho quá trình startup/Config Data trong các phiên bản hỗ trợ. **Đây không đồng nghĩa với việc mọi file `bootstrap.yml` theo kiểu Spring Cloud cũ sẽ tự động được đọc.**

### 3.4. Spring Boot Config Data

Từ Spring Boot 2.4, cơ chế Config Data cho phép import dữ liệu cấu hình qua `spring.config.import`, profile activation và các location/resolver chuyên biệt.

Đây là cơ chế trọng tâm của các tài liệu tham khảo Boot hiện đại.

**Ghi nhớ:** thấy từ `bootstrap` trong tên một API, tài liệu hoặc log **chưa đủ để kết luận** dự án đang dùng kiểu nạp `bootstrap.yml` của Spring Cloud.

## 4. Mốc thời gian quan trọng: Spring Boot 2.4

Spring Boot **2.4** thay đổi đáng kể cách xử lý `application.properties`, `application.yml` và các nguồn cấu hình liên quan. Thay đổi này được giải thích trong **Spring Boot Config Data Migration Guide** và release notes chính thức.

Trước bước ngoặt đó, nhiều ứng dụng dựa vào những quy tắc cũ để xử lý profile, thứ tự document và các config location.

Từ Spring Boot 2.4, cơ chế **Config Data** được giới thiệu cùng property:

```properties
spring.config.import=optional:file:./local.properties
```

Cơ chế mới còn đặt ra những hạn chế rõ ràng đối với khai báo kích hoạt profile trong các tài liệu profile-specific hoặc đã có điều kiện.

Dòng thời gian khái quát:

```text
Spring Boot 2.3 và trước
   |
   | Cơ chế xử lý application.* cũ;
   | nhiều hướng dẫn Spring Cloud dùng bootstrap.yml
   v
Spring Boot 2.4
   |
   | Config Data processing được giới thiệu
   | spring.config.import
   | quy tắc profile/document mới
   v
Spring Boot 2.5 / 2.6 / 2.7
   |
   | tiếp tục dùng Config Data
   | cần Spring Cloud release train phù hợp
   v
Spring Boot 3.x
   |
   | tiếp tục mô hình Config Data;
   | thay đổi nền tảng Java/Jakarta và phiên bản framework
   v
Spring Boot 4.x
   |
   | cần đối chiếu tài liệu/compatibility của 4.x;
   | không tự suy ra mọi API, starter, phiên bản từ 3.x
```

Sơ đồ này chỉ nêu **các mốc khái niệm**, không phải bảng hỗ trợ vòng đời hay danh sách đủ mọi thay đổi nhỏ.

### 4.1. Đọc chính xác tài liệu lịch sử

Một nguồn lịch sử có giá trị là:

- Spring Boot Config Data Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-Config-Data-Migration-Guide
- Spring Boot 2.4 Release Notes: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.4-Release-Notes

Khi đọc một hướng dẫn dùng `bootstrap.yml` hoặc `spring.config.use-legacy-processing`, hãy xác định tác giả đang nói tới mốc trước/sau 2.4.

## 5. Version matrix: không ghép Spring Boot và Spring Cloud tùy ý

Spring Cloud có **release train** riêng, ví dụ Hoxton, 2020.0.x, 2021.0.x, 2023.0.x, 2024.0.x và 2025.x. Không thể chỉ nhìn “Spring Cloud version mới hơn” rồi giả định tương thích với mọi bản Boot.

Ví dụ quan hệ **theo bảng tương thích công bố trên trang dự án Spring Cloud**:

| Spring Cloud release train | Dòng Spring Boot liên quan |
| --- | --- |
| Hoxton | Boot 2.2.x / 2.3.x trong các service release được hỗ trợ |
| 2020.0.x | Boot 2.4.x / 2.5.x, với giới hạn bản vá cụ thể |
| 2021.0.x | Boot 2.6.x / 2.7.x, với giới hạn bản vá cụ thể |
| 2022.0.x | Boot 3.0.x / 3.1.x, với giới hạn bản vá cụ thể |
| 2023.0.x | Boot 3.2.x / 3.3.x, với giới hạn bản vá cụ thể |
| 2024.0.x | Boot 3.4.x |
| 2025.0.x | Boot 3.5.x |
| 2025.1.x | Boot 4.0.x; hỗ trợ Boot 4.1.x từ một bản 2025.1.x phù hợp |

**Đây là bảng định hướng theo nhóm phiên bản, không phải cam kết rằng mọi patch bất kỳ trong hai dòng tương thích.** Trang chính thức có ghi giới hạn service release bắt đầu hỗ trợ một minor, trạng thái kết thúc hỗ trợ (EOL) và thay đổi ở các bản phát hành tiếp theo.

Luôn kiểm tra lại:

https://spring.io/projects/spring-cloud/

và release notes của **đúng** Spring Cloud train trước khi nâng cấp.

### 5.1. Vì sao matrix quan trọng với bootstrap?

Một ví dụ `bootstrap.yml` viết khi tác giả dùng Boot 2.3 + Cloud Hoxton có thể thiếu `spring.config.import` vì bản Cloud ấy dùng mô hình bootstrap truyền thống.

Nếu bạn dùng Boot 3.5 + Cloud 2025.0.x, tài liệu Spring Cloud Config Client cho phép mô hình Config Data import; bạn không nên tự động sao chép toàn bộ cách khởi động của Hoxton.

Nếu bạn dùng Boot 4.x, lại cần kiểm tra train tương ứng và hướng dẫn của phiên bản 4.x, không chỉ đổi số version trong `pom.xml`.

## 6. Xác định phiên bản thực tế của dự án trước khi xem tài liệu

Không đoán phiên bản từ tên thư mục, tên artifact hoặc một câu trong README cũ.

### 6.1. Maven: kiểm tra parent/BOM

Ví dụ:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.x</version>
</parent>
```

Đây là **mẫu minh họa**; `3.5.x` là một dòng phiên bản, không phải chuỗi có thể chép nguyên để build.

Nếu dự án dùng BOM thay vì parent:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>...</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Cần kiểm tra cả cấu hình parent/BOM, những dependency bị override version và profile Maven đang kích hoạt.

### 6.2. Maven: xác định dependency cuối cùng

```bash
./mvnw help:effective-pom
./mvnw dependency:tree
```

Trong một dự án nhiều module, có thể cần chọn module cụ thể:

```bash
./mvnw -pl service-module dependency:tree
```

Hãy tìm:

```text
org.springframework.boot:*
org.springframework.cloud:*
spring-cloud-starter-config
spring-cloud-starter-bootstrap
spring-cloud-dependencies
```

Nếu dùng Maven system không có wrapper, thay `./mvnw` bằng `mvn`.

### 6.3. Gradle: kiểm tra plugin/BOM

```groovy
plugins {
    id 'org.springframework.boot' version '<version>'
}

dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:<train-version>"
    )
}
```

Đây là cấu trúc minh họa. Cách project quản lý phiên bản có thể dùng Spring dependency-management plugin, version catalog hoặc conventions plugin thay thế.

### 6.4. Gradle: xem dependency thực sự

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-cloud-config-client \
  --configuration runtimeClasspath
```

Nếu module không có task/configuration tương ứng, hãy chọn đúng Gradle project.

### 6.5. Phân biệt source với artifact đang chạy

Dù `build.gradle` đang khai báo Spring Boot 3.x, một container có thể vẫn chạy JAR được build từ 2.7. Cần xác định **artifact version/image digest/commit** của tiến trình thực, không chỉ file build mới trên laptop.

## 7. Chọn đúng loại tài liệu chính thức

Có ít nhất bốn loại tài liệu hữu ích, mỗi loại trả lời một câu hỏi khác nhau:

| Loại tài liệu | Dùng khi |
| --- | --- |
| Spring Boot reference của đúng version | Kiểm tra Externalized Configuration, Config Data, profile |
| Spring Boot migration guide/release notes | Hiểu hành vi đổi khi nâng cấp Boot |
| Spring Cloud Config Client reference của đúng version | Kiểm tra `configserver:`, legacy bootstrap, kết nối remote |
| Spring Cloud compatibility/release train | Chọn Cloud BOM phù hợp với Boot |

Ví dụ, tài liệu Boot hiện đại:

https://docs.spring.io/spring-boot/reference/features/external-config.html

Tài liệu Spring Cloud Config Client:

https://docs.spring.io/spring-cloud-config/reference/client.html

**Cần lưu ý:** đường dẫn tài liệu `/reference/...` thường thể hiện bản được site coi là hiện hành. Một dự án chạy version cũ cần xem **version selector** hoặc URL tài liệu lưu trữ theo version, không mặc định lấy “current” làm đáp án.

Đặc biệt:

- Hướng dẫn Spring Boot **không tự động mô tả toàn bộ tính năng Spring Cloud Config Client**.
- Hướng dẫn Spring Cloud **không tự thay thế quy tắc Config Data của Boot phiên bản đang dùng**.
- Một blog có thể là tư liệu lịch sử đúng đắn nhưng không phải hướng dẫn mới nhất.

## 8. Nhận diện tài liệu bootstrap cũ bằng các dấu hiệu

Một bài viết có thể thuộc thế hệ bootstrap truyền thống nếu thấy nhiều dấu hiệu sau:

1. Tạo file `src/main/resources/bootstrap.yml`.
2. Đặt `spring.cloud.config.uri` và `spring.application.name` trong file ấy.
3. Không hề nhắc tới `spring.config.import`.
4. Giải thích rằng bootstrap context đọc Config Server trước application context.
5. Dùng Boot 2.3 hoặc Spring Cloud Hoxton/những release train cũ.
6. Dùng mã `BootstrapConfiguration` hoặc cơ chế `spring.factories` đặc thù Spring Cloud cũ.
7. Khuyên đặt mọi thuộc tính remote-config vào `bootstrap.properties` mà không nói tới Config Data.

Ví dụ điển hình:

```yaml
# bootstrap.yml — ví dụ kiểu legacy Spring Cloud bootstrap
spring:
  application:
    name: invoice-service
  cloud:
    config:
      uri: http://localhost:8888
      fail-fast: true
```

Đây **không phải cấu hình mặc định phổ quát cho mọi ứng dụng Spring Boot hiện đại**.

### 8.1. Không phải cứ có bootstrap.yml là sai

Có những dự án cố tình bật legacy bootstrap vì yêu cầu tương thích hoặc một tích hợp Spring Cloud cụ thể. Trong trường hợp ấy, file `bootstrap.yml` có thể vẫn được sử dụng hợp lệ.

Vấn đề không phải “xóa mọi file bootstrap”, mà là **xác minh vì sao nó còn hoạt động và có phù hợp với thiết kế hiện tại hay không**.

## 9. Spring Boot Config Data với spring.config.import

Trong mô hình mới, một file ứng dụng có thể nạp nguồn bổ sung qua:

```yaml
# application.yml
spring:
  config:
    import: "optional:file:./local-overrides.yml"
```

Khi location tồn tại, giá trị từ tài liệu import có thể có ưu tiên cao hơn tài liệu khai báo import theo quy tắc Config Data.

Cơ chế này thuộc **Spring Boot**. Nó hỗ trợ các loại location chuẩn được Boot xử lý và các loại location mà module bên ngoài bổ sung resolver/loader.

Nếu import từ Spring Cloud Config Server, location dùng scheme đặc thù:

```text
configserver:
```

Scheme `configserver:` không phải cách biểu diễn một file cục bộ; nó yêu cầu thành phần Spring Cloud Config Client và version tương thích để xử lý.

## 10. Spring Cloud Config Client theo cách Config Data

Khi dùng Spring Cloud Config Client tương thích với Spring Boot 2.4+ và Config Data, một cấu hình phổ biến là:

```yaml
# application.yml
spring:
  application:
    name: invoice-service
  config:
    import: "optional:configserver:http://localhost:8888"
```

Điều kiện:

- Có dependency Spring Cloud Config Client phù hợp.
- Spring Boot và Spring Cloud release train tương thích.
- Config Server có thể truy cập ở endpoint đã khai báo.
- Ứng dụng cho phép nạp cấu hình remote theo chính sách của môi trường.

### 10.1. optional:configserver:

```properties
spring.config.import=optional:configserver:
```

Ví dụ tài liệu Spring Cloud Config Client dùng dạng này với Config Server ở vị trí mặc định khi không chỉ định URL khác.

`optional:` có ý nghĩa **không biến việc không thể kết nối nguồn này thành lỗi bắt buộc theo chính sách import tương ứng**.

Hãy kiểm tra yêu cầu thực tế:

- Nếu remote config chỉ bổ sung cờ tính năng, có thể muốn `optional:`.
- Nếu remote config chứa chính sách bắt buộc, chạy thiếu nó có thể nguy hiểm; khi đó cần cân nhắc import không optional, validation và cơ chế fail-fast phù hợp.

### 10.2. configserver: không optional

```properties
spring.config.import=configserver:http://localhost:8888
```

Cách này thể hiện rằng remote Config Server là một phụ thuộc bắt buộc của quá trình nạp cấu hình, theo semantics của Config Data/Config Client.

Không nên tự thêm `optional:` để “làm ứng dụng chạy cho qua” mà không đánh giá hậu quả. Ứng dụng có thể khởi động bằng các mặc định không đúng môi trường.

### 10.3. Địa chỉ Config Server

Tài liệu Spring Cloud Config Client cho phép đặt địa chỉ trong location:

```properties
spring.config.import=optional:configserver:http://localhost:8888
```

Hoặc dùng `spring.cloud.config.uri` cùng dạng import phù hợp. Khi cả hai cách cùng khai báo location, cần xem quy tắc ưu tiên được tài liệu **đúng phiên bản** mô tả; ở các phiên bản tham khảo hiện đại, địa chỉ trong `spring.config.import` có ưu tiên hơn `spring.cloud.config.uri`.

Không đưa username/password trực tiếp vào URL trong README công khai. Dùng secret manager hoặc environment phù hợp cho dữ liệu xác thực.

## 11. Một ví dụ so sánh trước và sau

### 11.1. Cách kiểu legacy bootstrap

```yaml
# bootstrap.yml
spring:
  application:
    name: billing-service
  cloud:
    config:
      uri: http://localhost:8888
```

Cách trên giả định **legacy bootstrap context đã được bật** và dependency tương ứng hiện diện.

### 11.2. Cách Config Data

```yaml
# application.yml
spring:
  application:
    name: billing-service
  config:
    import: "optional:configserver:http://localhost:8888"
```

Tùy nhu cầu, thêm các property Spring Cloud Config Client thích hợp.

### 11.3. Khác biệt bản chất

| Khía cạnh | Legacy bootstrap | Config Data import |
| --- | --- | --- |
| File chủ yếu được nhắc tới | `bootstrap.yml` | `application.yml` hoặc nguồn Config Data phù hợp |
| Điểm mở rộng chủ yếu | Spring Cloud bootstrap context | Spring Boot Config Data |
| Cấu hình kết nối remote | Thường `spring.cloud.config.uri` | `spring.config.import=configserver:...` |
| Kích hoạt | Legacy bootstrap được bật | Import và resolver/loader tương thích |
| Liên quan profile | Theo vòng đời bootstrap cũ | Config Data xử lý theo cơ chế Boot mới |
| Giữ tương thích cũ | Có thể có chủ đích | Mục tiêu phổ biến của dự án mới |

**Không nên viết cả hai bộ cấu hình một cách vô thức.** Nếu một dự án vừa bật bootstrap context, vừa import `configserver:`, có thể xuất hiện nhiều đường kết nối hoặc khó hiểu nguồn nào đang thắng. Cần kiểm tra docs và log của phiên bản thực tế.

## 12. Legacy bootstrap vẫn có thể bật có chủ đích

Theo tài liệu Spring Cloud Config Client, muốn dùng cách **Config First Bootstrap** cũ có thể bật bootstrap qua:

```text
spring.cloud.bootstrap.enabled=true
```

hoặc starter phù hợp:

```text
org.springframework.cloud:spring-cloud-starter-bootstrap
```

Với property `spring.cloud.bootstrap.enabled=true`, tài liệu yêu cầu cấp nó ở một nguồn đủ sớm, như **Java system property hoặc environment variable**.

Ví dụ:

```bash
java -Dspring.cloud.bootstrap.enabled=true \
     -jar app.jar
```

Hoặc:

```bash
SPRING_CLOUD_BOOTSTRAP_ENABLED=true java -jar app.jar
```

Khi bật chế độ ấy, cấu hình kiểu `bootstrap.yml` và `spring.cloud.config.uri` có thể có ý nghĩa theo đường đi legacy mà Spring Cloud cung cấp.

**Lưu ý:** việc bật thành công phụ thuộc vào module Cloud, release train tương thích và cơ chế khởi động của phiên bản đó. Không giả định chỉ cần tạo file `bootstrap.yml` là Boot thuần tự động kích hoạt Spring Cloud bootstrap context.

## 13. spring-cloud-starter-config khác spring-cloud-starter-bootstrap

Hai artifact có vai trò khác nhau:

```text
spring-cloud-starter-config
spring-cloud-starter-bootstrap
```

- `spring-cloud-starter-config` cung cấp những thành phần để ứng dụng dùng Spring Cloud Config Client.
- `spring-cloud-starter-bootstrap` hỗ trợ kích hoạt cơ chế bootstrap cũ trong những release train có chức năng tương ứng.

Nếu ứng dụng muốn dùng Config Data import từ Config Server, thông thường hãy bắt đầu từ **Config Client starter** và property `spring.config.import`.

Nếu ứng dụng đang áp dụng legacy bootstrap có chủ đích, kiểm tra starter/flag riêng.

Không nên “sửa” lỗi cấu hình bằng cách thêm `spring-cloud-starter-bootstrap` theo phản xạ mà không biết dự án đang dùng mode nào. Có thể giải quyết triệu chứng ban đầu nhưng làm phức tạp quá trình nâng cấp.

## 14. Lỗi “No spring.config.import property has been defined”

Trong những bộ dependency của Spring Cloud Config Client dùng cơ chế Config Data, khi thiếu cấu hình import thích hợp, ứng dụng có thể hiển thị một thông báo startup có ý nghĩa như:

```text
No spring.config.import property has been defined
```

Đây là dấu hiệu mạnh rằng bạn đang dùng **Config Client theo thế hệ yêu cầu cấu hình Config Data import**, nhưng chưa khai báo import hoặc chưa bật legacy bootstrap phù hợp.

### 14.1. Cách xử lý đúng

1. Xác nhận Spring Cloud Config Client có thật sự cần thiết.
2. Xác nhận Boot–Cloud release train tương thích.
3. Xác định muốn dùng **Config Data mode** hay **legacy bootstrap mode**.
4. Với Config Data, khai báo `spring.config.import=...` ở nguồn phù hợp.
5. Với legacy mode, chỉ bật bootstrap nếu dự án có nhu cầu và docs của phiên bản hỗ trợ.
6. Kiểm tra kết nối mạng, URI, ứng dụng/profile/label được Config Server cung cấp.
7. Khởi động lại và đọc log.

Một số hướng dẫn còn gợi ý tắt kiểm tra import bằng:

```properties
spring.cloud.config.import-check.enabled=false
```

Khi property này được phiên bản hỗ trợ, nó có thể **tắt một kiểm tra**, nhưng **không đồng nghĩa đã cấu hình thành công đường nạp remote**. Không dùng nó như phương pháp chính để thay thế việc hiểu `spring.config.import`.

## 15. spring.config.use-legacy-processing là gì?

Tài liệu migration của Spring Boot 2.4 ghi nhận lựa chọn:

```properties
spring.config.use-legacy-processing=true
```

để tạm thời sử dụng lại logic xử lý cấu hình kiểu Spring Boot 2.3 trong phạm vi các phiên bản chuyển tiếp hỗ trợ tùy chọn đó.

Đây là **cơ chế tương thích chuyển tiếp lịch sử**, không phải lựa chọn được bảo đảm tồn tại hoặc nên dùng lâu dài trong mọi phiên bản mới.

Đừng tự suy rằng một ứng dụng chạy Boot 3.x hoặc 4.x có thể bật nguyên `spring.config.use-legacy-processing=true` rồi nhận lại toàn bộ hành vi của Boot 2.3.

Đặc biệt:

- Tùy chọn này thuộc câu chuyện **Spring Boot Config Data migration**.
- Nó không phải synonym của `spring.cloud.bootstrap.enabled`.
- Bật một trong hai không có nghĩa tự động tái hiện tất cả behavior của cái còn lại.
- Khi nâng cấp, nên hướng tới hợp đồng cấu hình chính thức của phiên bản đích, không dựa mãi vào compatibility flag.

Nếu một blog khuyên giữ `spring.config.use-legacy-processing=true` “cho đơn giản”, hãy kiểm tra **ngày viết bài, version nguồn và version đích**.

## 16. Phân biệt hai loại legacy

| Vấn đề | Cơ chế | Ý nghĩa |
| --- | --- | --- |
| Muốn hành vi xử lý application.yml kiểu trước Boot 2.4 | `spring.config.use-legacy-processing` trong các version chuyển tiếp hỗ trợ | Spring Boot Config Data compatibility |
| Muốn Spring Cloud bootstrap context kiểu cũ | `spring.cloud.bootstrap.enabled` / bootstrap starter khi được hỗ trợ | Spring Cloud legacy bootstrap |
| Muốn import Config Server theo cơ chế hiện đại | `spring.config.import=configserver:...` | Spring Boot Config Data + Cloud Config Client |
| Muốn nạp file bổ sung | `spring.config.import=file:...` | Config Data thuần Spring Boot |
| Muốn đăng ký resource/đối tượng ở giai đoạn bootstrap của Boot | `BootstrapRegistryInitializer` | API khởi động, không tự đọc bootstrap.yml |

Đây là bảng quan trọng nhất khi một hướng dẫn có chữ “bootstrap” hoặc “legacy”.

## 17. Thay đổi profile documents từ Boot 2.4

Một phần lớn khó khăn khi nâng cấp từ Boot 2.3 liên quan tới YAML nhiều tài liệu và điều kiện profile.

Ví dụ kiểu cũ có thể thấy:

```yaml
spring:
  profiles: dev

app:
  message: "development"
```

Với Config Data, cách mô tả điều kiện document được dùng rộng rãi là:

```yaml
spring:
  config:
    activate:
      on-profile: dev

app:
  message: "development"
```

Ở đây `spring.config.activate.on-profile` là **điều kiện áp dụng document**, không phải lời yêu cầu tự kích hoạt profile.

Để bật profile:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Đây là thay đổi cần đối chiếu với migration guide khi gặp YAML cũ dùng `spring.profiles` như một điều kiện document.

## 18. Không đặt spring.profiles.active vào document đã kích hoạt theo profile

Một lỗi dễ gặp khi di chuyển dữ liệu từ bootstrap:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: prod

app:
  message: "production"
```

Đây không phải mô hình khai báo phù hợp của Config Data. Spring Boot hiện đại hạn chế các thuộc tính kích hoạt profile trong tài liệu profile-specific hoặc tài liệu đã được điều kiện hóa bằng `spring.config.activate.on-profile`.

Cách tách trách nhiệm:

**Ở nguồn được phép cung cấp profile lúc startup:**

```bash
java -jar app.jar --spring.profiles.active=prod
```

**Trong document chỉ dành cho prod:**

```yaml
spring:
  config:
    activate:
      on-profile: prod

app:
  message: "production"
```

Nếu lỗi startup nói về khai báo `spring.profiles.active` không hợp lệ, hãy tìm vị trí document chứa property, không chỉ cố bật lại legacy bootstrap.

## 19. spring.profiles.include và group khi nâng cấp

Một số tài liệu cũ dùng:

```yaml
spring:
  profiles:
    include: metrics
```

Spring Boot hiện đại vẫn có khái niệm include và profile groups, nhưng có **quy tắc nơi được phép khai báo**.

Ví dụ profile group trong một document không bị điều kiện hóa:

```yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmetrics
```

Kích hoạt `production` sẽ khiến các profile thành viên được xét theo cơ chế tương ứng.

Không đặt `spring.profiles.include` hoặc định nghĩa group một cách tùy ý bên trong một document đã có `on-profile` hoặc tệp riêng cho profile.

Khi đọc hướng dẫn cũ dùng include lồng vào mỗi file profile, hãy tra migration guide cho version đang chạy. Đừng giả định một YAML từng hợp lệ ở Boot 2.3 vẫn hợp lệ với Config Data.

## 20. spring.config.import không giống @PropertySource

Spring Framework hỗ trợ:

```java
@Configuration
@PropertySource("classpath:company.properties")
public class CompanyConfiguration {
}
```

Cơ chế này được xử lý trong quá trình xây dựng Spring context.

Trong khi đó:

```yaml
spring:
  config:
    import: "classpath:company.properties"
```

thuộc **giai đoạn Config Data** của Boot.

Hai cơ chế có thể khác về:

- thời điểm nạp;
- profile;
- vị trí trong thứ tự ưu tiên;
- cú pháp import;
- quy tắc missing-resource;
- tác động lên các thuộc tính startup sớm.

Một hướng dẫn cũ có thể khuyên thêm `@PropertySource` để đọc file ngoài. Điều đó không hẳn sai với một tệp Properties truyền thống, nhưng không thay thế toàn bộ Config Data, đặc biệt khi cần quyết định profile/import ở giai đoạn rất sớm.

Không coi `@PropertySource`, `bootstrap.yml` và `spring.config.import` là ba cách viết tương đương.

## 21. spring.config.location và additional-location

Các thuộc tính:

```text
spring.config.location
spring.config.additional-location
```

có ý nghĩa liên quan tới vị trí Config Data.

Khái quát:

- `spring.config.location` định nghĩa lại những vị trí tìm kiếm mặc định theo cơ chế Boot.
- `spring.config.additional-location` bổ sung vị trí bên ngoài danh sách mặc định.

Ví dụ:

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/opt/app/config/
```

Dấu `/` cuối biểu thị một thư mục; `optional:` thể hiện chính sách chấp nhận location vắng mặt trong tình huống phù hợp.

Một hướng dẫn cũ có thể đặt file ở `bootstrap.yml` để “nạp thật sớm”. Nếu yêu cầu ngày nay chỉ là **đọc file cấu hình ngoài JAR**, thông thường nên kiểm tra khả năng chuẩn của Config Data trước khi khôi phục Spring Cloud bootstrap context.

Chỉ đưa legacy bootstrap vào khi thật sự cần đặc tính thuộc Spring Cloud của cơ chế đó.

## 22. Không đồng nhất import file: với import configserver:

Hai ví dụ:

```properties
spring.config.import=optional:file:./local.yml
```

và:

```properties
spring.config.import=optional:configserver:http://localhost:8888
```

đều dùng property `spring.config.import` nhưng **loại location khác nhau**:

| Scheme | Ai xử lý thông thường |
| --- | --- |
| `file:`, `classpath:` | Config Data loader của Spring Boot cho các tài nguyên hỗ trợ |
| `configserver:` | Config Client extension của Spring Cloud khi có dependency thích hợp |
| Custom scheme | `ConfigDataLocationResolver` và `ConfigDataLoader` của một thư viện/ứng dụng |

Nếu ứng dụng báo không nhận diện location `configserver:`, hãy kiểm tra module Config Client và version trước khi sửa tên file YAML.

Một Boot application thuần không cần Spring Cloud để nạp một local `application.yml` hay một tệp `file:` được hỗ trợ.

## 23. Khi nào một import được nạp?

Trong Config Data, tài liệu khai báo:

```yaml
spring:
  config:
    import: "optional:file:./extra.yml"

app:
  timeout: 3s
```

có thể import dữ liệu từ file `extra.yml` nếu file tồn tại.

Tài liệu chính thức mô tả các import được xử lý khi gặp và có quan hệ ưu tiên đặc thù: giá trị từ import có thể ghi đè giá trị từ document đã khai báo import.

Ví dụ:

```yaml
# extra.yml
app:
  timeout: 5s
```

Với bố trí này, `app.timeout` từ import có thể là giá trị hiệu lực trong phạm vi Config Data tương ứng.

**Nhưng:** điều đó chưa xét CLI, environment variables, system properties, profile-specific documents hoặc nguồn khác. Một nguồn có ưu tiên cao hơn vẫn có thể thắng.

Không bê nguyên quy tắc precedence của “bootstrap config cũ” để suy đoán thứ tự import mới. Hãy dùng docs đúng version và kiểm thử.

## 24. Một Config Server có thể được gọi nhiều lần khi khởi động

Tài liệu Spring Cloud Config Client giải thích Config Data có thể hoạt động theo nhiều bước, ví dụ ban đầu nạp dữ liệu theo profile mặc định để xác định các profile được kích hoạt, sau đó nạp dữ liệu phù hợp với active profiles.

Vì vậy khi bật Config Data mode, bạn có thể thấy **nhiều request tới Config Server** trong một lần khởi động. Đây có thể là hệ quả bình thường của vòng đời xử lý profile/import, không nhất thiết là lỗi gọi trùng hoặc retry vô hạn.

Khi phân tích log hoặc metrics:

- Phân biệt request lấy cấu hình ở pha default với request theo active profile.
- Kiểm tra app name, profile, label và URI.
- Phân biệt nhiều request bình thường với retry do network failure.
- So sánh behavior với tài liệu Config Client của đúng version.

Nếu bạn chuyển từ bootstrap cũ sang Config Data mà số request tăng, không nên lập tức tắt profile processing để “quay lại một request”.

## 25. Fail-fast và optional là quyết định thiết kế

Một tài liệu có thể viết:

```properties
spring.config.import=optional:configserver:
```

để giúp developer chạy local ngay cả khi Config Server không sẵn sàng. Nhưng production có thể yêu cầu điều ngược lại.

Phân loại:

| Yêu cầu | Thiết kế nên cân nhắc |
| --- | --- |
| Config Server tùy chọn; có mặc định local an toàn | Có thể dùng `optional:` |
| Config Server bắt buộc để bảo đảm chính sách | Cân nhắc import không optional |
| Muốn thử kết nối lại khi server lỗi tạm thời | Cơ chế retry mà Config Client version hỗ trợ |
| Muốn tránh startup với cấu hình không đầy đủ | Validation và fail-fast thích hợp |
| Muốn developer offline vẫn chạy | Local fallback có ý nghĩa và tách profile rõ |

Trong legacy bootstrap, một số ví dụ dùng:

```properties
spring.cloud.config.fail-fast=true
```

Trong Config Data import, việc bỏ `optional:` có vai trò liên quan tới fail startup khi nguồn bắt buộc không truy cập được.

Không nên kết luận hai công tắc này hoàn toàn đồng nghĩa trong mọi ngữ cảnh. Kiểm tra tương tác với retry, import location và phiên bản Config Client.

## 26. Retry trong Config Data import có quy tắc riêng

Các tài liệu Config Client thường đề cập `spring.cloud.config.retry.*` và yêu cầu dependency phù hợp cho retry.

Ví dụ khái niệm:

```properties
spring.cloud.config.retry.max-attempts=10
spring.cloud.config.retry.initial-interval=1000
```

Một số trường hợp khi import Config Server được khai báo trong file theo profile cần chuyển tham số retry sang URL query parameter của location, theo hướng dẫn version tương ứng.

Ví dụ cấu trúc:

```properties
spring.config.import=configserver:http://config.example.invalid:8888?fail-fast=true&max-attempts=10
```

Đây là ví dụ về **cú pháp tham số** trong những version tài liệu có mô tả, không phải một cấu hình production đầy đủ.

Với một ứng dụng thật, cần xem:

- Lỗi mạng có được retry không?
- Việc mất auth hoặc nhận 4xx có nên retry không?
- Tổng thời gian startup có giới hạn không?
- Retry được áp dụng ở pha Config Data hay legacy bootstrap?
- Dependency retry/AOP có được cấu hình đúng không?

Đừng sao chép retry setting từ blog dùng legacy bootstrap sang Config Data mode mà không xác nhận cách xử lý.

## 27. spring.application.name, profile và label ở Config Server

Một Spring Cloud Config Client thường định danh cấu hình remote bằng các thành phần như:

```text
application
profile
label
```

Các giá trị thường liên hệ tới:

```text
spring.application.name
spring.profiles.active
spring.cloud.config.label
```

Ví dụ:

```yaml
spring:
  application:
    name: billing-service
  profiles:
    active: dev
  config:
    import: "optional:configserver:http://localhost:8888"
```

Trong ví dụ triển khai thật, nên cấp active profile từ lệnh khởi chạy hoặc environment theo chính sách phù hợp, không nhất thiết đặt cố định vào file chung.

Một lỗi có thể không liên quan tới bootstrap mode, mà do **ứng dụng hỏi Config Server bằng app name, profile hoặc label không như bạn nghĩ**.

Khi log cho thấy remote fetch thành công nhưng thiếu property, hãy xác nhận bộ ba định danh và repository của Config Server.

## 28. Không nhầm bootstrap.yml với application.yml

Đặt file tại:

```text
src/main/resources/bootstrap.yml
```

không tự tạo hiệu lực giống `application.yml` trong mọi Spring Boot application.

Trong Boot tiêu chuẩn, các tên config cơ sở liên quan tới `application`, trừ khi có cơ chế khác hoặc `spring.config.name` được cấu hình để đổi tên.

Tệp `bootstrap.yml` thường được liên kết với **Spring Cloud legacy bootstrap**.

Nếu dự án không có Spring Cloud bootstrap machinery hoặc không chủ động import file theo cơ chế phù hợp, đừng mặc định Boot sẽ tự nạp `bootstrap.yml` như một config chuẩn.

**Cách kiểm chứng đơn giản:**

1. Xác định đúng version và dependency.
2. Xem có cấu hình bật legacy bootstrap không.
3. Bật log Config Data phù hợp.
4. Liệt kê PropertySource names và đọc một khóa không nhạy cảm.
5. Kiểm tra ứng dụng thật sự đang dùng nguồn nào.

Không kết luận chỉ bằng việc file tồn tại trong repository.

## 29. Phân biệt tên file, thứ tự nạp và nơi cấp thuộc tính

Ba câu hỏi tách biệt:

**File có tồn tại không?**

```text
src/main/resources/application.yml
```

**File có được đóng gói/nạp không?**

Trong executable JAR thông thường, resource của module ứng dụng nằm dưới:

```text
BOOT-INF/classes/
```

**Giá trị của file có thắng không?**

Có thể không, vì:

- File/profile khác có mức ưu tiên cao hơn.
- Import đóng góp giá trị mới.
- Java system property ghi đè.
- Biến môi trường ghi đè.
- CLI ghi đè.
- Một PropertySource tùy chỉnh được thêm ở đầu.

Khi một hướng dẫn bootstrap cũ nói “cấu hình bootstrap được nạp trước, vì vậy luôn có độ ưu tiên cao”, cần đánh giá lại quy tắc ưu tiên hiện hành, cơ chế Spring Cloud property source và chính sách override cụ thể.

**Nạp sớm không tự động đồng nghĩa luôn thắng mọi nguồn.**

## 30. Cấu hình bootstrap legacy có thể điều chỉnh thứ tự nguồn remote

Trong những mô hình Spring Cloud bootstrap truyền thống, PropertySource từ Config Server có thể được đưa vào Spring Environment với độ ưu tiên và khả năng cho phép override theo những thiết lập Cloud cụ thể.

Một số hướng dẫn cũ nói tới nhóm property liên quan:

```text
spring.cloud.config.allow-override
spring.cloud.config.override-none
spring.cloud.config.override-system-properties
```

Không nên sao chép các công tắc ấy vào mọi ứng dụng Config Data và kỳ vọng chúng vẫn có cùng hiệu quả.

Khi gặp chúng trong tài liệu:

1. Xác minh đó là tài liệu của Spring Cloud Config/legacy bootstrap nào.
2. Kiểm tra property có còn được hỗ trợ ở phiên bản hiện tại không.
3. Xác minh phía server hay client có quyền đặt thuộc tính.
4. Kiểm thử giá trị hiệu lực giữa remote source, local Config Data, environment và CLI.
5. Không tạo kết luận về precedence chỉ từ tên property.

Thứ tự ưu tiên cấu hình là một phần của hợp đồng vận hành, có thể gây thay đổi behavior khi nâng cấp dù ứng dụng vẫn khởi động.

## 31. Nhận diện ví dụ có package/API từ đời cũ

Các bài viết kỹ thuật cũ có thể sử dụng:

```java
import javax.validation.constraints.NotBlank;
```

Trong Spring Boot 3.x, các ví dụ Jakarta Validation thường dùng:

```java
import jakarta.validation.constraints.NotBlank;
```

Đây là ví dụ về **khác biệt nền tảng** khi chuyển major Boot, không phải trực tiếp là thay đổi Config Data.

Điều này cho thấy hướng dẫn bootstrap phải được xem trong toàn cảnh:

- Java version được hỗ trợ.
- Spring Framework major.
- Boot starter và API.
- Jakarta/Javax namespace.
- Spring Cloud release train.
- Build plugin và dependency versions.

Nếu một bài viết vừa có `bootstrap.yml` kiểu cũ, vừa dùng các API `javax.*` của giai đoạn trước Boot 3, đó là dấu hiệu cần đối chiếu phiên bản kỹ lưỡng.

Không nên sửa riêng `javax` thành `jakarta` rồi cho rằng toàn bộ dự án đã tương thích với Boot 3.x.

## 32. Spring Boot 4.x cần thêm một vòng đối chiếu

Tại thời điểm viết tài liệu, Spring Boot và Spring Cloud đã có các thế hệ 4.x/2025.x. Một dự án Boot 4.x không nên áp dụng máy móc mọi dependency, starter hoặc constructor API từ các ví dụ Boot 2.x/3.x.

Hãy kiểm tra:

- Release notes của đúng Boot 4.x patch.
- Spring Cloud train hỗ trợ chính minor đó.
- Hướng dẫn Spring Cloud Config Client tương ứng.
- Những thay đổi dependency, auto-configuration hoặc starter trong major.
- API Config Data/Environment và các cơ chế khai báo extension mà thư viện đang dùng.
- Phiên bản Java, Gradle, Maven plugin được hỗ trợ.

Trong bảng compatibility trên trang Spring Cloud, dòng `2025.1.x` được gắn với Boot 4.0.x và hỗ trợ 4.1.x từ một service release thích hợp. **Không coi tên train đủ để khẳng định mọi patch đều tương thích**; hãy dùng bảng hỗ trợ và release notes được cập nhật chính thức.

## 33. Vì sao không nên copy một BOM version từ câu trả lời cũ?

Maven có thể khai báo:

```xml
<properties>
    <spring-cloud.version>...</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Trong ví dụ, dấu `...` là **placeholder cho version cụ thể được chọn từ compatibility table**, không phải bản build có thể chạy nguyên văn.

Nếu người học lấy một train từ blog cũ và bỏ vào Boot 4.x, hệ thống có thể gặp lỗi startup, API incompatibility hoặc check version.

Quy trình đúng:

1. Đọc Boot version trong project.
2. Tra compatibility table của Spring Cloud.
3. Chọn release train tương thích.
4. Chọn bản service release phù hợp, còn được hỗ trợ nếu có.
5. Import Cloud BOM.
6. Để dependency management quản lý những module Cloud trong cùng train.
7. Kiểm tra dependency tree và chạy thử startup.

Không nên gắn version riêng cho từng Cloud module một cách tùy tiện nếu đã dùng BOM, trừ khi có lý do đã được xác minh.

## 34. Gradle cũng cần quản lý version thống nhất

Một mẫu khái quát:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<boot-version>'
}

dependencies {
    implementation platform(
            'org.springframework.cloud:spring-cloud-dependencies:<cloud-train-version>')

    implementation 'org.springframework.cloud:spring-cloud-starter-config'
}
```

Tùy build convention, project có thể dùng dependency-management plugin hoặc version catalog.

Ý nghĩa của ví dụ không nằm ở cú pháp placeholder, mà ở **việc Boot plugin và Cloud train phải được chọn như một cặp tương thích**.

Khi nâng cấp:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

và kiểm tra các module đang dùng phiên bản nào, nhất là nếu nhiều module của dự án còn giữ những version trực tiếp từ thế hệ trước.

## 35. Không nhầm hai phương pháp đăng ký extension

Trong hệ sinh thái Spring có thể thấy:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

và các interface/class khác nhau:

```text
EnvironmentPostProcessor
BootstrapRegistryInitializer
PropertySourceLocator
ConfigDataLocationResolver
ConfigDataLoader
AutoConfiguration
```

Chúng phục vụ những vòng đời khác nhau.

Ví dụ:

- `EnvironmentPostProcessor` là điểm mở rộng chuẩn bị Environment.
- `ConfigDataLocationResolver` và `ConfigDataLoader` hỗ trợ loại location Config Data.
- `BootstrapRegistryInitializer` liên quan tới bootstrap registry của Boot.
- `PropertySourceLocator` có thể xuất hiện trong Spring Cloud bootstrap kiểu truyền thống.
- `AutoConfiguration.imports` liên quan tới công bố các lớp auto-configuration.

**Không suy rằng mọi thứ có tên `Bootstrap` sẽ đọc `bootstrap.yml`.**

Khi đọc một bài hướng dẫn extension, hãy tra đúng API và release notes của Spring Boot/Spring Cloud đang dùng. Ví dụ cũ có thể chứa cách đăng ký khác với bản hiện hành.

## 36. Chẩn đoán trước khi sửa file bootstrap

Một quy trình điều tra hiệu quả:

### Bước 1: xác nhận phiên bản

Kiểm tra build và dependency tree. Xác định Boot major/minor, Cloud train và Config Client.

### Bước 2: xác nhận mode

Tìm một trong các dấu hiệu:

```text
spring.config.import
spring.cloud.bootstrap.enabled
spring-cloud-starter-bootstrap
spring.config.use-legacy-processing
```

Lưu ý: chỉ tìm thấy một chuỗi trong repository không chứng minh nó có hiệu lực. Phải xác nhận nguồn được nạp và version hỗ trợ.

### Bước 3: xem startup log

Bật logger phù hợp khi cần:

```bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Với Spring Cloud Config Client, có thể cần thêm logger của các thành phần Cloud Config cụ thể theo phiên bản để thấy kết nối remote và lỗi HTTP.

### Bước 4: xem profile và Config Data

Xác nhận active profiles, default profile, import locations và nguồn được nạp.

### Bước 5: xem PropertySources

Liệt kê tên nguồn; đừng log tất cả giá trị, đặc biệt secret.

### Bước 6: xác nhận value và binding

Đọc một khóa không nhạy cảm từ Environment/bean `@ConfigurationProperties`. Phân biệt:

- Không tìm được file.
- File nạp nhưng profile không áp dụng.
- Giá trị bị ghi đè.
- Binder sai kiểu.
- Validation từ chối.

### Bước 7: sửa đúng tầng

Có thể phải sửa import, BOM, profile, working directory, server URL hoặc permission, chứ không nhất thiết cần một bootstrap file mới.

## 37. Lỗi khi dùng Spring Cloud Config: cách phân loại

| Triệu chứng | Nhóm nguyên nhân khả dĩ | Hướng điều tra |
| --- | --- | --- |
| Thông báo thiếu `spring.config.import` | Config Client Config Data mode chưa khai báo import | Thêm import đúng, hoặc kiểm tra legacy mode có chủ đích |
| `bootstrap.yml` không có tác dụng | Legacy bootstrap chưa bật | Kiểm tra starter/flag và phiên bản |
| Không nhận ra scheme `configserver:` | Config Client module không hiện diện/không tương thích | Xem dependency tree và BOM |
| Không kết nối được Config Server | URI, network, auth, TLS, server chưa chạy | Log client, connectivity và secrets |
| Kết nối thành công nhưng thiếu property | App name/profile/label, repository, precedence | Xem endpoint và các nguồn có hiệu lực |
| Nạp được remote nhưng bean vẫn lỗi | Conversion/validation thiếu giá trị | Xem `@ConfigurationProperties` và log |
| Startup có nhiều request config | Config Data profile processing/retry | Phân biệt pha và nguyên nhân |
| Sau nâng cấp profile thay đổi | Quy tắc Config Data khác legacy | Đọc migration guide, test profile |
| Boot–Cloud mismatch | Chọn release train sai | Compatibility table |
| Prod chạy nhưng dùng local default | Remote import optional hoặc cấu hình remote thiếu | Xem yêu cầu fail-fast/validation |

Không quy tất cả các triệu chứng về “Spring Boot không đọc bootstrap”. Một hệ thống có thể dùng hoàn toàn đúng Config Data nhưng gặp vấn đề khác ở phía remote.

## 38. Không nên để lỗi “optional” che thiếu cấu hình bắt buộc

Một cách “sửa nhanh” thường thấy:

```yaml
spring:
  config:
    import: "optional:configserver:"
```

Ứng dụng khởi động qua lỗi kết nối Config Server, nhưng sau đó có thể chạy với mặc định không an toàn nếu các khóa remote là bắt buộc.

Ví dụ:

```yaml
payment:
  endpoint: "https://fallback.example.invalid"
```

Nếu Config Server ở production phải cung cấp endpoint thật và chính sách giao dịch, việc dùng fallback có thể là lỗi vận hành nghiêm trọng.

Để giảm rủi ro:

1. Phân loại thuộc tính bắt buộc.
2. Không đặt mặc định giả cho dữ liệu có ý nghĩa an toàn.
3. Dùng validation khi tạo bean.
4. Chỉ dùng `optional:` cho nguồn thực sự tùy chọn.
5. Có integration test khi remote server không sẵn sàng.
6. Có telemetry/readiness để nhận diện thiếu cấu hình.

**Khởi động được không đồng nghĩa đã có cấu hình đúng.**

## 39. Kiểm tra thứ tự ưu tiên sau khi di chuyển mode

Một test thực tế nên có cùng khóa ở nhiều nguồn:

```yaml
# application.yml
client:
  timeout: 3s
```

Remote Config Server (ví dụ):

```properties
client.timeout=5s
```

Environment variable:

```text
CLIENT_TIMEOUT=7s
```

Command line:

```bash
java -jar app.jar --client.timeout=9s
```

Với những nguồn cùng xuất hiện, mục tiêu là xác định **giá trị được binder nhận trong phiên bản và mode cụ thể**.

Không nên viết test dựa trên niềm tin rằng “remote luôn thắng local” hoặc “biến môi trường luôn thắng mọi remote” nếu chưa xét cơ chế Cloud và các property override.

Bạn có thể dùng:

```java
Environment environment = ...;
String timeout = environment.getProperty("client.timeout");
```

và một bean:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(Duration timeout) {
}
```

Đối chiếu giá trị và danh sách PropertySource. Đừng chỉ dựa vào thứ tự in ra của một file YAML duy nhất.

## 40. Cách xác nhận Config Data đã nạp nguồn nào

Trong môi trường dev/test, bật TRACE:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Log có thể giúp thấy xử lý location, profile và import. Nội dung chính xác phụ thuộc phiên bản.

Để xem PropertySource names:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class PropertySourceNamePrinter implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public PropertySourceNamePrinter(
            ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (var source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
```

Ví dụ chỉ in tên nguồn, không in toàn bộ giá trị. Các tên nội bộ có thể thay đổi theo version, nên không viết mã nghiệp vụ phụ thuộc chúng.

Dòng log “Config Server đã trả dữ liệu” không có nghĩa giá trị của server chắc chắn thắng những nguồn cao hơn. Cần xác nhận giá trị hiệu lực.

## 41. Kiểm tra profile thực tế thay vì đọc một file

Ví dụ:

```java
import java.util.Arrays;

System.out.println(
        Arrays.toString(environment.getActiveProfiles()));
```

Khi không có active profile, mảng có thể rỗng dù Spring Boot vẫn nạp tài liệu cơ sở và xét default profile.

Nếu profile `prod` được khai báo trong CLI:

```bash
java -jar app.jar --spring.profiles.active=prod
```

nhưng trong log xuất hiện nhiều profile hơn, có thể do profile groups/includes, code bootstrap hoặc một nguồn ghi đè.

Đặc biệt, một tài liệu có:

```yaml
spring:
  config:
    activate:
      on-profile: prod
```

**không tự kích hoạt `prod`**. Nó chỉ đặt điều kiện áp dụng tài liệu.

## 42. Kiểm thử cấu hình theo mode trong dự án

Bộ kiểm thử nên bao gồm cả phần nhanh và phần tích hợp.

### 42.1. Unit test cho binding

Dùng `Binder` với `MapConfigurationPropertySource` nếu chỉ cần kiểm tra tên khóa/kiểu Java.

### 42.2. Context test cho đăng ký bean

Dùng `ApplicationContextRunner` với `@EnableConfigurationProperties` để xem binder và validation của bean.

### 42.3. Integration test cho Config Data

Khởi động context với profile phù hợp và những nguồn cấu hình thật trong test.

### 42.4. Integration test với Config Server

Dùng một server test hoặc môi trường tích hợp có kiểm soát; kiểm tra hành vi khi server khả dụng và không khả dụng.

### 42.5. Smoke test executable JAR

Chạy artifact đúng version với CLI/environment tương đương triển khai, rồi kiểm tra startup, profile, remote import, validation và readiness.

Không thể chứng minh một migration từ bootstrap sang Config Data thành công chỉ bằng việc unit test một `MapPropertySource`. Test ấy không thực hiện remote fetch hoặc Config Data lifecycle.

## 43. Một hợp đồng cấu hình minh họa để kiểm thử

Record:

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        @NotNull URI endpoint,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts) {
}
```

Ví dụ này áp dụng import `jakarta.validation.*` cho Spring Boot 3.x. Với Boot 2.x, namespace và dependency tương ứng có thể khác; với Boot 4.x, cần xem hướng dẫn của đúng phiên bản.

Một bài test context có thể xác minh giá trị hiệu lực hợp lệ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientPropertiesContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsValidValues() {
        runner.withPropertyValues(
                "client.endpoint=https://api.example.invalid",
                "client.timeout=3s",
                "client.max-attempts=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            ClientProperties properties =
                    context.getBean(ClientProperties.class);
            assertThat(properties.maxAttempts()).isEqualTo(4);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfiguration {
    }
}
```

Test này kiểm tra binding trong context nhỏ, **không tự kiểm tra đường nạp Config Server**. Với remote config, cần test riêng phần integration.

## 44. Kịch bản nâng cấp 1: Boot 2.3 + Cloud Hoxton lên Boot 2.7

Giả sử dự án lịch sử có:

```text
Spring Boot 2.3.x
Spring Cloud Hoxton
src/main/resources/bootstrap.yml
```

Mục tiêu:

```text
Spring Boot 2.7.x
Spring Cloud 2021.0.x tương thích
```

Một kế hoạch:

1. Xác nhận mã đang dựa vào bootstrap context ở những phần nào.
2. Đọc migration guide Boot 2.4 trước khi đổi Boot.
3. Cập nhật Boot version và chọn Cloud train tương thích.
4. Chuyển các tài liệu cấu hình từ quy tắc cũ sang Config Data khi phù hợp.
5. Quyết định có dùng `spring.config.import=configserver:` hay có lý do giữ legacy bootstrap.
6. Sửa YAML nhiều tài liệu sử dụng quy tắc profile cũ.
7. Kiểm tra CLI/system/env precedence.
8. Chạy test với profile dev/prod và một Config Server test.
9. Kiểm tra remote fetch, retries, fail-fast.
10. Đóng gói, smoke test và ghi nhận thay đổi trong README.

Không nên nhảy từ Hoxton sang một Cloud train mới nhất không tương thích Boot 2.7.

## 45. Kịch bản nâng cấp 2: Boot 2.7 lên Boot 3.x

Ở đây, ngoài Config Data đã có từ Boot 2.4, dự án còn đối mặt các thay đổi nền tảng Java/Jakarta/Spring Framework.

Danh sách:

- Chọn Java version theo yêu cầu Boot 3.x.
- Cập nhật Spring Cloud train theo compatibility table.
- Chuyển các API Javax/Jakarta liên quan.
- Kiểm tra dependency thay thế hoặc đã bỏ.
- Kiểm tra Cloud Config Client vẫn dùng mode mong muốn.
- Kiểm tra `@ConfigurationProperties` và validation.
- Kiểm tra actuator/management security.
- Test profile/import/config precedence.
- Xác nhận build JAR mới và không chạy nhầm artifact cũ.

Nếu gặp lỗi `ClassNotFoundException` hoặc `NoSuchMethodError` ngay khi startup, đó có thể là **dependency/API mismatch**, không phải chỉ vì file `bootstrap.yml` chưa nạp.

## 46. Kịch bản nâng cấp 3: Boot 3.x lên Boot 4.x

Không áp dụng đơn giản quy tắc “Boot 2.7 lên 3.x” cho toàn bộ migration tiếp theo.

Quy trình:

1. Chọn đúng target Boot 4.x minor/patch được hỗ trợ.
2. Tra Spring Cloud train tương ứng.
3. Xem release notes Boot 4.x và Cloud Config Client.
4. Kiểm tra Java/build tool/starter thay đổi.
5. Kiểm tra cơ chế Config Data import còn phù hợp.
6. Kiểm tra extension riêng dùng `EnvironmentPostProcessor`, `ConfigDataLocationResolver` hoặc `BootstrapRegistryInitializer`.
7. Xem các API/annotation đã được đổi hoặc bỏ.
8. Chạy thử startup, binding, validation và remote fetch trên artifact mới.
9. Kiểm tra log/metrics và bảo mật Actuator.
10. Ghi lại version pair được chứng minh bằng build/test.

Đặc biệt, nếu dự án có một thư viện nội bộ vẫn dùng Spring Cloud bootstrap extension đời cũ, cần nâng cấp thư viện ấy thay vì chỉ nâng Spring Boot app.

## 47. Một checklist migration có thể áp dụng cho nhóm

Trước khi thay đổi:

- Ghi lại Boot version, Cloud train, Config Client version.
- Chụp lại dependency tree của module ứng dụng.
- Liệt kê các file `application.*`, `bootstrap.*` và những nguồn ngoài JAR.
- Liệt kê các import, active profiles, include/groups.
- Ghi nhận giá trị hiệu lực của một số khóa **không nhạy cảm**.
- Xác định remote config bắt buộc hay tùy chọn.
- Xác định hệ thống đang bật legacy bootstrap bằng cách nào.

Khi thay đổi:

- Chọn cơ chế đích: Config Data hay legacy bootstrap có chủ đích.
- Cập nhật BOM tương thích.
- Di chuyển cấu hình cần thiết vào nguồn phù hợp.
- Chỉnh các khai báo profile/document theo quy tắc đích.
- Không dùng compatibility flag như giải pháp vĩnh viễn nếu không có căn cứ.
- Bảo vệ secret khỏi source code và log.
- Ghi rõ working directory/location trong deployment.

Sau khi thay đổi:

- Chạy test binder/validation.
- Chạy integration test Config Data/profile.
- Thử Config Server online/offline.
- Kiểm tra fail-fast/optional semantics.
- Kiểm tra precedence trên các nguồn trùng khóa.
- Smoke test đúng executable JAR/container.
- Cập nhật README với version và link docs chính xác.

## 48. Tạo bảng đối chiếu trước–sau cho riêng dự án

Một bảng như sau có thể đưa vào tài liệu nâng cấp:

| Nội dung | Trước | Sau | Cách kiểm chứng |
| --- | --- | --- | --- |
| Boot version | 2.3.x | 2.7.x | Effective build |
| Cloud train | Hoxton | 2021.0.x phù hợp | Dependency tree |
| Remote config | `bootstrap.yml` | `spring.config.import=configserver:` | Startup log + Config Server |
| Profile declaration | Quy tắc file cũ | Config Data profile activation | Profile integration test |
| Missing remote | Cơ chế fail-fast legacy | Import optional/bắt buộc có chủ đích | Server offline test |
| Client timeout | Giá trị từ nhiều nguồn | Kiểm tra precedence đích | Bean config assertion |
| Artifact | JAR build cũ | JAR build mới | Artifact ID/version |
| Rollback | Khởi động mode cũ | Phương án rollback đã thử | Smoke test |

Bảng chỉ là **mẫu quy trình**. Khi điền thực tế, hãy ghi chính xác version (không dùng `x`) và tên module.

Một cuộc migration tốt không chỉ là thay file; nó có **bằng chứng hành vi trước–sau**.

## 49. Lỗi thường gặp: copy ví dụ “current” vào dự án EOL

Giả sử một dự án đang chạy Boot 2.2 và Cloud Hoxton, nhưng người học đọc docs Spring Cloud hiện đại rồi thêm:

```properties
spring.config.import=configserver:http://localhost:8888
```

Một Boot 2.2 không có cơ chế Config Data `spring.config.import` được giới thiệu ở Boot 2.4.

Do đó, không nên giả định Spring Boot cũ sẽ tự hiểu property mới và gọi Config Server theo behavior hiện đại.

Giải pháp:

- Nếu chưa nâng cấp, đọc tài liệu lịch sử đúng version.
- Nếu muốn sử dụng Config Data, lập kế hoạch nâng cấp Boot và Cloud tương thích.
- Không cố vá một property mới vào runtime cũ rồi bỏ qua lỗi nếu nó không có tác dụng.

**Tài liệu mới không tự làm một runtime cũ hiểu tính năng chưa tồn tại.**

## 50. Lỗi thường gặp: dùng bootstrap.yml trong Boot thuần

Một ứng dụng chỉ có:

```groovy
implementation 'org.springframework.boot:spring-boot-starter'
```

không có Spring Cloud Config Client hoặc legacy bootstrap module.

Người học tạo:

```yaml
# bootstrap.yml
demo:
  message: "Hello"
```

rồi không thấy giá trị `demo.message`.

Trong trường hợp thông thường, Boot dùng `application.yml` làm tên file Config Data mặc định, không tự coi `bootstrap.yml` là file cấu hình chuẩn chỉ vì tên có chữ bootstrap.

Nếu đây chỉ là một cấu hình local, hãy dùng:

```yaml
# application.yml
demo:
  message: "Hello"
```

hoặc import một resource rõ ràng theo cơ chế hỗ trợ.

Đừng thêm Spring Cloud bootstrap starter chỉ để đọc một file mà bạn có thể đặt tên và import bình thường bằng Config Data.

## 51. Lỗi thường gặp: thiếu Config Client dependency

Một file có:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

nhưng project không có Config Client module hỗ trợ location đó.

Khi ấy, Spring Boot không nhất thiết có resolver cho scheme `configserver:` và có thể báo lỗi location.

Hướng xử lý đúng:

- Xác nhận thật sự cần Spring Cloud Config Server.
- Thêm `spring-cloud-starter-config` đúng train.
- Không thêm một version Cloud bất kỳ.
- Kiểm tra lại cấu hình import và startup.

Nếu không cần remote Config Server, bỏ scheme `configserver:` và dùng nguồn phù hợp thay vì thêm dependency thừa.

## 52. Lỗi thường gặp: thêm bootstrap starter rồi mất kiểm soát precedence

Một nhóm gặp lỗi Config Client import và thêm:

```text
spring-cloud-starter-bootstrap
```

để ứng dụng khởi động. Nhưng lúc này một số cấu hình được đọc theo đường bootstrap context, có thể khác expectation về thời điểm và precedence.

Hậu quả:

- Không rõ remote config được nạp bởi đường nào.
- Hai nhóm developer tài liệu hóa theo hai phương pháp khác nhau.
- Một số khóa bị ghi đè ngoài dự tính.
- Khi nâng cấp tiếp, lỗi lại xuất hiện.

Cần:

1. Xác định một mode có chủ đích.
2. Tài liệu hóa đường nạp nguồn.
3. Kiểm tra dependency tree.
4. Kiểm thử giá trị hiệu lực.
5. Chỉ giữ bootstrap starter khi đây là quyết định kỹ thuật có căn cứ.

## 53. Lỗi thường gặp: bỏ optional mà không thử khi server offline

Nếu đổi:

```properties
spring.config.import=optional:configserver:
```

thành:

```properties
spring.config.import=configserver:
```

bạn thay đổi hợp đồng startup: nguồn remote giờ được xem là bắt buộc theo semantics import.

Điều này có thể là thay đổi đúng cho production, nhưng cần kiểm thử:

- Khi server sẵn sàng.
- Khi server tạm ngừng.
- Khi DNS/network timeout.
- Khi credential bị từ chối.
- Khi một profile không có dữ liệu.
- Khi remote trả dữ liệu nhưng bean validation thất bại.

Không đánh giá chỉ bằng trường hợp happy path.

## 54. Lỗi thường gặp: tự tạo EnvironmentPostProcessor để “sửa bootstrap”

Một số hướng dẫn cũ dùng:

```java
EnvironmentPostProcessor
```

để thêm PropertySource tự tạo rất sớm.

Điểm mở rộng này có thể hợp lý cho một nhu cầu cụ thể, nhưng không nên dùng để mô phỏng toàn bộ Spring Cloud Config Client hoặc Config Data chỉ vì bootstrap cũ không hoạt động.

Nếu cần một loại Config Data mới, hãy xem:

```text
ConfigDataLocationResolver
ConfigDataLoader
```

và phiên bản API tương ứng.

Nếu chỉ cần một file `application.yml` ngoài JAR, dùng các location chuẩn khi phù hợp. Nếu cần Config Server, dùng module Config Client đúng train.

**Chọn extension theo bài toán**, không theo mẹo tương thích đã lỗi thời.

## 55. Khi tài liệu cũ và mới mâu thuẫn, nên ưu tiên gì?

Một quy tắc đánh giá tài liệu:

1. **Xác định version dự án.**
2. **Ưu tiên reference docs đúng version.**
3. **Đọc release notes/migration guide cho khoảng version nâng cấp.**
4. **Xem compatibility matrix khi dùng Spring Cloud.**
5. **Đọc issue/blog như bằng chứng bổ sung, không thay thế docs chuẩn.**
6. **Thử lại trong một project nhỏ hoặc test context với version thật.**
7. **Ghi lại kết quả và version của chính dự án.**

Ví dụ:

- Bài blog năm 2019 nói `bootstrap.yml` là cách chuẩn cho Config Server.
- Docs hiện đại nói `spring.config.import=configserver:`.
- Dự án của bạn dùng Boot 2.7 + Cloud 2021.0.x.

Không có nghĩa blog cũ “nói sai” trong lịch sử. Nó có thể đúng với bộ version được tác giả dùng. Nhưng áp dụng vào dự án 2.7 đòi hỏi đối chiếu với Config Data và quy tắc Cloud tương ứng.

## 56. Dấu hiệu một hướng dẫn không đủ thông tin

Hãy thận trọng khi tài liệu:

- Không nêu Spring Boot version.
- Không nêu Spring Cloud train.
- Không phân biệt Spring Cloud Config Client và Boot thuần.
- Yêu cầu tạo `bootstrap.yml` nhưng không nói có bật legacy bootstrap không.
- Khuyên dùng `spring.config.use-legacy-processing=true` cho “mọi bản Spring Boot mới”.
- Cung cấp dependency version rời rạc không có BOM.
- Không nhắc xử lý missing remote source.
- Không có hướng dẫn test profile/precedence.
- Chỉ dùng một bản screenshot IDE hoặc một đoạn console rất cũ.
- Không nêu lệnh khởi động hoặc cấu hình environment.
- Gọi một lỗi `BindException` là “Config Server không kết nối” mà không xem nguyên nhân.
- Khuyên in toàn bộ Environment/PropertySources để debug, kể cả secrets.

Cách khắc phục không phải bỏ qua mọi bài blog. Hãy bổ sung thiếu sót bằng cách tra docs đúng version và test.

## 57. Các bước thử tối thiểu trước khi di chuyển bootstrap

Dựng một sandbox nhỏ trên version mục tiêu:

1. Tạo ứng dụng tối giản và chọn BOM tương thích.
2. Thêm dependency Config Client nếu cần remote.
3. Tạo `application.yml` với `spring.application.name` và import.
4. Tạo một property không nhạy cảm tại Config Server, ví dụ `demo.source=remote`.
5. Chạy ứng dụng với profile dev.
6. Xác nhận `Environment#getProperty("demo.source")` và nguồn ứng dụng nhìn thấy.
7. Tắt Config Server và xem startup behavior.
8. Thử import optional và non-optional riêng biệt.
9. Thử có CLI ghi đè một property.
10. Ghi lại log/behavior.
11. Sau khi đã hiểu đường mới, chuyển dự án thật.

Không kiểm thử bằng secret production hay một Config Server nhạy cảm chỉ để chứng minh một thuộc tính demo.

## 58. Ví dụ runnable tối giản cho Config Data local (không cần Cloud)

Một ví dụ chỉ dùng Spring Boot, phù hợp để hiểu phần Config Data độc lập.

```text
src/main/resources/
├── application.yml
└── extra.yml
```

```yaml
# application.yml
spring:
  config:
    import: "classpath:extra.yml"

demo:
  message: "local"
```

```yaml
# extra.yml
demo:
  message: "from-import"
```

Record:

```java
package com.example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(String message) {
}
```

Ứng dụng:

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Chú ý `extra.yml` chứa cùng khóa `demo.message` để quan sát precedence giữa file import và file khai báo import.

Ví dụ này **không dùng Spring Cloud**, và có thể được kiểm thử trong một dự án Boot có hỗ trợ Config Data. Nó hữu ích để phân biệt lỗi Config Data nói chung với lỗi của `configserver:`.

## 59. Ví dụ cấu hình Config Client trên version tương thích

Với Spring Cloud Config Client được quản lý bằng BOM tương thích:

```yaml
# application.yml
spring:
  application:
    name: config-client-demo
  config:
    import: "optional:configserver:http://localhost:8888"

demo:
  message: "local-fallback"
```

Lúc Config Server khả dụng, nguồn remote có thể đóng góp:

```properties
demo.message=remote
```

Khi server không khả dụng, import optional có thể cho phép startup tùy chi tiết phiên bản và cấu hình retry/fail-fast, với local fallback phù hợp.

Test cần xác minh thực tế:

- Tên application/profile được hỏi ở server.
- Remote property có được nạp không.
- Giá trị cuối có phải remote hay một nguồn khác ghi đè không.
- Hành vi khi server offline.
- Các exception xuất hiện khi remote config có giá trị sai kiểu.

Không giả định cứ khai báo import là mọi giá trị phải đến từ server.

## 60. Phân biệt lỗi do file, do network và do bean

Ba luồng lỗi:

**A. File local bắt buộc không có**

```properties
spring.config.import=file:./required.yml
```

Có thể thất bại ở giai đoạn tìm/nạp Config Data.

**B. Config Server không truy cập được**

```properties
spring.config.import=configserver:http://localhost:8888
```

Có thể thất bại khi resolver/loader gọi remote, tùy cấu hình import và client.

**C. File hoặc server nạp được nhưng bean sai**

```properties
client.timeout=not-a-duration
```

Có thể thất bại ở bước conversion/binding.

Chúng khác nhau:

```text
Config Data location
       |
       v
Resolution / Loading ----> lỗi file/network
       |
       v
Spring Environment
       |
       v
Binder / Conversion -----> lỗi kiểu
       |
       v
Bean Validation ----------> lỗi ràng buộc
```

Không khắc phục lỗi conversion bằng cách bật legacy bootstrap, cũng không khắc phục lỗi network bằng cách bỏ `@Validated`.

## 61. Cách ghi lại tài liệu dự án để tránh lặp lỗi

Trong README nội bộ, nên có một đoạn cấu hình như sau:

```text
Spring Boot version:       <exact-version>
Spring Cloud train:        <exact-train>
Config Client:             Có/Không
Cơ chế remote config:      Config Data import / Legacy bootstrap
Config Server location:    lấy từ nguồn nào
Active profile:            cấp ở đâu
Fail-fast/optional:        chính sách
Retry:                     chính sách
Fallback:                  những giá trị nào được phép
Cách test:                 command + expected outcome
Tài liệu tham khảo:        URL đúng version
```

Các placeholder cần được thay bằng giá trị thật trước khi chia sẻ trong nhóm.

Một tài liệu có thể dùng bảng:

| Quyết định | Lý do |
| --- | --- |
| Dùng Config Data import | Phù hợp Boot/Cloud hiện tại |
| Không dùng bootstrap starter | Không có use case legacy |
| Remote config bắt buộc ở prod | Tránh startup với giá trị không phù hợp |
| Local fallback được phép ở dev | Phát triển offline |
| Bật validation trên bean | Phát hiện cấu hình sai sớm |

Việc tài liệu hóa quyết định quan trọng hơn việc chỉ ghi một snippet YAML.

## 62. Câu hỏi thường gặp: bootstrap.yml có còn “được hỗ trợ” không?

Câu trả lời đầy đủ là: **phụ thuộc vào module, version và bootstrap mode**.

- Với Boot thuần theo Config Data mặc định, `bootstrap.yml` không phải tên file ứng dụng tiêu chuẩn tự động nạp như `application.yml`.
- Với một Spring Cloud setup bật **legacy bootstrap context** phù hợp, `bootstrap.yml` có thể vẫn có chức năng theo tài liệu phiên bản đó.
- Với Config Client mode mới, `spring.config.import=configserver:` thường được dùng và không cần một `bootstrap.yml` để import Config Server.

Không trả lời theo kiểu “bootstrap.yml luôn bị xóa” hoặc “bootstrap.yml vẫn luôn bắt buộc”.

## 63. Câu hỏi thường gặp: có nên xóa bootstrap.yml ngay khi nâng Boot?

Không nên xóa chỉ dựa trên việc nâng một dependency.

Hãy kiểm tra:

1. File chứa những thuộc tính nào?
2. Những thuộc tính ấy có thuộc Spring Cloud Config, service discovery, security, profile, hoặc log startup không?
3. Mode hiện tại là gì?
4. Có extension nội bộ nào đọc bootstrap context không?
5. Dữ liệu sẽ được chuyển sang đâu?
6. Có test xác nhận remote config và precedence không?
7. Có kế hoạch rollback nếu startup thất bại không?

Sau khi chuyển đường nạp và test thành công, file bootstrap cũ có thể được bỏ nếu không còn nhu cầu. Không giữ lại hai bộ file với cùng property mà không có quy tắc ưu tiên rõ ràng.

## 64. Câu hỏi thường gặp: có thể chỉ đặt spring.config.import vào bootstrap.yml?

Trong Config Data mode, tài liệu khuyến nghị thường đặt import vào `application.yml` hoặc một nguồn cấu hình được nạp ở giai đoạn thích hợp.

Nếu không bật cơ chế legacy đọc `bootstrap.yml`, một `spring.config.import` nằm **chỉ trong bootstrap.yml chưa được nạp** sẽ không thể tự kích hoạt việc nạp chính file đó.

Đây là một lỗi vòng lặp logic rất hay gặp khi copy hướng dẫn:

```text
bootstrap.yml không được nạp
       |
       v
spring.config.import nằm trong bootstrap.yml
       |
       v
import không được nhìn thấy
```

Hãy đặt property tại một nguồn Spring Boot thực sự đọc được ở thời điểm Config Data processing.

## 65. Câu hỏi thường gặp: Config Client mới có luôn yêu cầu Config Server đang chạy?

Không phải mọi cấu hình đều giống nhau.

- Nếu import bắt buộc, việc không truy cập được server có thể làm startup thất bại.
- Nếu import optional, ứng dụng có thể tiếp tục với dữ liệu local trong những điều kiện phù hợp.
- Nếu có retry/fail-fast, thời gian và loại lỗi ảnh hưởng hành vi.
- Nếu ứng dụng còn có validation bắt buộc, việc thiếu property remote vẫn có thể khiến context thất bại dù import optional.

Vì vậy một hướng dẫn chỉ viết “Config Server không cần chạy nhờ optional” là chưa đầy đủ. Cần kiểm tra tác động tới **hợp đồng cấu hình cuối cùng** của ứng dụng.

## 66. Câu hỏi thường gặp: spring.config.use-legacy-processing có sửa mọi lỗi nâng cấp?

Không. Đó là cơ chế tương thích lịch sử của quá trình chuyển từ Boot 2.3 sang 2.4 trong những phiên bản có hỗ trợ.

Nó không thay thế việc:

- chọn đúng Spring Cloud train;
- cấu hình Config Client;
- sửa YAML profile không hợp lệ;
- kiểm tra Java/Jakarta API;
- kiểm tra dependency;
- thử network/remote config;
- xác nhận precedence;
- viết test migration.

Hướng tới cơ chế được docs của phiên bản đích hỗ trợ lâu dài.

## 67. Bài tập A: xác định kiểu hướng dẫn

Bạn đọc một ví dụ:

```yaml
# bootstrap.yml
spring:
  cloud:
    config:
      uri: http://localhost:8888
```

Bài viết không có `spring.config.import` và cho biết dự án dùng Boot 2.3.

**Câu hỏi:** đây nhiều khả năng là kiểu hướng dẫn nào?

**Đáp án:** hướng dẫn Spring Cloud **legacy bootstrap**. Nó có thể đúng với stack lịch sử, nhưng khi chuyển sang Boot 2.4+ và Cloud train tương ứng cần đối chiếu lại.

## 68. Bài tập B: một ứng dụng Boot thuần

Dự án chỉ có Boot starter. File:

```yaml
# bootstrap.yml
demo:
  mode: "safe"
```

Không bật Cloud bootstrap hoặc import gì khác.

**Câu hỏi:** có thể chắc chắn `demo.mode` được Spring Boot tự động nạp không?

**Đáp án:** không. `bootstrap.yml` không phải file Config Data mặc định của Boot thuần theo cách ứng dụng thông thường. Nên dùng `application.yml` hoặc import rõ ràng.

## 69. Bài tập C: chuyển Config Client

Dự án có Spring Cloud Config Client phù hợp với Boot 3.x, không có yêu cầu giữ legacy bootstrap.

**Yêu cầu:** đề xuất một cấu hình import để kết nối Config Server tại localhost:8888 và cho phép phát triển local khi server offline.

**Một đáp án:**

```yaml
spring:
  application:
    name: sample-service
  config:
    import: "optional:configserver:http://localhost:8888"
```

Cần test cả trường hợp server online/offline; `optional:` không thay thế validation của thuộc tính bắt buộc.

## 70. Bài tập D: phân biệt legacy flags

Hãy giải thích:

```text
spring.config.use-legacy-processing=true
spring.cloud.bootstrap.enabled=true
```

**Đáp án:**

- Property thứ nhất liên quan tới việc quay lại logic xử lý config trước Boot 2.4 trong giai đoạn chuyển tiếp được hỗ trợ.
- Property thứ hai liên quan tới việc bật **Spring Cloud legacy bootstrap** theo cơ chế và version tương ứng.

Chúng không phải hai cách viết cho cùng một chức năng.

## 71. Bài tập E: profile migration

Ví dụ cũ:

```yaml
spring:
  profiles: prod

app:
  mode: live
```

**Yêu cầu:** viết điều kiện document kiểu Config Data.

**Đáp án:**

```yaml
spring:
  config:
    activate:
      on-profile: prod

app:
  mode: live
```

Và kích hoạt profile từ nguồn phù hợp như CLI:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Không đặt `spring.profiles.active` trong chính document đã được điều kiện hóa.

## 72. Bài tập F: compatibility matrix

Một dự án dùng Boot 3.5 nhưng đang thêm Spring Cloud 2020.0.x từ một blog rất cũ.

**Câu hỏi:** vấn đề cần kiểm tra đầu tiên là gì?

**Đáp án:** Spring Cloud train không phù hợp với thế hệ Boot 3.5. Cần tra compatibility table hiện hành của Spring Cloud rồi chọn train được công bố phù hợp với Boot 3.5, thay vì trộn các module Cloud rời rạc.

## 73. Bài tập G: nhiều request Config Server

Sau khi chuyển sang Config Data import, log xuất hiện hai lượt request cấu hình trong một lần startup. Người phát triển khẳng định đây chắc chắn là bug.

**Đáp án:** chưa đủ căn cứ. Spring Cloud Config Client mô tả Config Data có thể cần xử lý profile theo nhiều bước, từ đó phát sinh thêm request. Cần xem profile và log; phân biệt vòng xử lý bình thường, retry do lỗi mạng và các request thực sự trùng lặp không mong muốn.

## 74. Bài tập H: file nạp được nhưng giá trị vẫn sai

Config Data TRACE cho thấy `application-prod.yml` đã được nạp. Nhưng bean nhận `client.timeout=9s` thay vì `5s` trong file.

**Câu hỏi:** có thể kết luận loader bị lỗi không?

**Đáp án:** không. Cần xem nguồn ưu tiên cao hơn, chẳng hạn CLI, environment variables, remote Config Server hoặc custom PropertySource; có thể file đã nạp đúng nhưng giá trị bị ghi đè.

## 75. Bài tập I: một tài liệu trên Internet không ghi version

Bạn thấy bài viết hướng dẫn Spring Cloud Config, nhưng:

- Không ghi Boot version.
- Không ghi Spring Cloud train.
- Dùng bootstrap.yml.
- Có Maven dependency ghi version tách rời.
- Không có test fail-fast/profile.

**Câu hỏi:** có nên copy nguyên vào production?

**Đáp án:** không. Hãy xác nhận version của dự án, tra docs và compatibility chính thức, kiểm tra cách bật bootstrap, lựa chọn mode và viết test startup với nguồn remote/đường dẫn thực tế.

## 76. Tài liệu tham khảo chính thức

Các liên kết dùng để xác minh và đối chiếu theo version:

1. **Spring Boot — Externalized Configuration**  
   https://docs.spring.io/spring-boot/reference/features/external-config.html

2. **Spring Boot — Config Data Migration Guide**  
   https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-Config-Data-Migration-Guide

3. **Spring Boot — 2.4 Release Notes**  
   https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.4-Release-Notes

4. **Spring Cloud Config — Config Client**  
   https://docs.spring.io/spring-cloud-config/reference/client.html

5. **Spring Cloud — Release Train / Spring Boot compatibility**  
   https://spring.io/projects/spring-cloud/

6. **Spring Cloud — Release Train Reference**  
   https://docs.spring.io/spring-cloud-release/reference/index.html

**Cách dùng:** những URL hiện hành có thể thay đổi nội dung khi version mới được phát hành. Nếu đang bảo trì Boot 2.7 hoặc một bản Cloud cụ thể, hãy chọn trang tài liệu lưu trữ/version selector tương ứng, rồi lưu **URL đúng version** vào README của dự án.

Bài học không yêu cầu người học phải luôn dùng phiên bản mới nhất; nó yêu cầu người học **không nhầm tài liệu của một thế hệ với runtime của thế hệ khác**.

## 77. Ghi nhớ

- **Spring Boot 2.4 là mốc quan trọng** khi cơ chế Config Data và `spring.config.import` được giới thiệu.
- **Spring Cloud legacy bootstrap context**, **Spring Boot bootstrap registry** và **Config Data** là những khái niệm khác nhau; chữ “bootstrap” không đủ để kết luận cơ chế nạp file.
- `bootstrap.yml` thuộc nhiều hướng dẫn Spring Cloud cũ; nó **không tự trở thành file cấu hình mặc định của mọi ứng dụng Spring Boot**.
- Với Spring Cloud Config Client tương thích Config Data, dùng `spring.config.import=configserver:...` hoặc `optional:configserver:...` theo chính sách, thay vì tự mặc định phải có bootstrap.yml.
- Legacy bootstrap vẫn có thể được bật có chủ đích thông qua cơ chế được version Cloud hỗ trợ, như `spring.cloud.bootstrap.enabled` hoặc `spring-cloud-starter-bootstrap`.
- `spring.config.use-legacy-processing` là câu chuyện compatibility của Spring Boot 2.4, **không đồng nghĩa** với Spring Cloud bootstrap và không phải giải pháp nâng cấp vĩnh viễn.
- Spring Boot và Spring Cloud **phải được ghép theo compatibility matrix**. Chỉ chọn số version dựa trên một blog là rủi ro.
- Khi nâng cấp Config Data, kiểm tra lại **profile activation**, document nhiều phần, `spring.config.import`, `optional:`, precedence và remote fetch.
- Một file được nạp đúng **chưa chắc giá trị của nó thắng**; giá trị runtime phụ thuộc toàn bộ PropertySource đang có hiệu lực.
- Một lỗi startup có thể thuộc **nạp location**, **network**, **binding/conversion**, **validation** hoặc **dependency incompatibility**; đừng đổ mọi lỗi vào bootstrap.
- Luôn đối chiếu **reference docs đúng phiên bản**, migration guide, release notes và kết quả test trên artifact thực tế.
- Mục tiêu của nâng cấp là một **hợp đồng cấu hình có thể giải thích, kiểm thử và triển khai lặp lại**, không phải chỉ đổi tên `bootstrap.yml` thành `application.yml`.
