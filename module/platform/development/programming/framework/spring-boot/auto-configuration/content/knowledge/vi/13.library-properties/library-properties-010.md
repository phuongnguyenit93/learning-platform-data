# Kiểm tra quyền ưu tiên nguồn cấu hình trong phạm vi tính năng tự cấu hình

## 1. Bài toán: cùng một khóa, nhiều nguồn, auto-configuration nhận giá trị nào?

Một thư viện Spring Boot có thể cung cấp auto-configuration cho tính năng xuất dữ liệu. Thư viện muốn tính năng **tắt theo mặc định**, cho ứng dụng sử dụng thư viện **bật/tắt bằng cấu hình bên ngoài**, đồng thời cho phép thay định dạng xuất từ `csv` sang `json`.

Giả sử khóa tính năng là:

```properties
acme.export.enabled=true
acme.export.format=json
```

Trong một ứng dụng thực tế, cùng khóa `acme.export.enabled` có thể xuất hiện trong nhiều nơi: file cấu hình được đóng gói, file nằm ngoài JAR, cấu hình cho profile, biến môi trường, Java system properties, command-line argument hay thuộc tính dành riêng cho test.

**Câu hỏi không phải “nguồn nào được đọc đầu tiên?”, mà là “giá trị hiệu lực cuối cùng trong Spring `Environment` là gì tại lúc auto-configuration được đánh giá?”.** Với một khóa xuất hiện nhiều lần, nguồn có mức ưu tiên cao nhất phù hợp với ngữ cảnh sẽ quyết định kết quả. Spring Boot không lấy giá trị theo thứ tự nhìn thấy trong README, và thư viện không có quyền ưu tiên cao hơn ứng dụng chỉ vì thư viện đăng ký bean trước.

Sau bài này, bạn có thể:

1. Giải thích cơ chế ưu tiên giữa `PropertySource`, `ConfigData`, biến môi trường, system properties và command-line arguments trong Spring Boot 3.3.
2. Phân biệt giá trị được `@ConditionalOnProperty` dùng để **bật/tắt bean** và giá trị được `@ConfigurationProperties` **bind** vào object cấu hình.
3. Thiết kế mặc định và namespace của một thư viện để ứng dụng sử dụng thư viện vẫn kiểm soát tính năng.
4. Lập ma trận xung đột nguồn, dự đoán bean có được tạo và nội dung cấu hình được bind.
5. Kiểm chứng thứ tự bằng một bài thử Java 17+/Spring Boot 3.3 có input và kết quả rõ ràng.

## 2. PropertySource và phép chọn giá trị

Spring `Environment` đại diện cho cấu hình mà ứng dụng thấy. Mỗi `PropertySource` là một nguồn có thể cung cấp cặp khóa–giá trị. Một `ConfigurableEnvironment` có danh sách `MutablePropertySources` được **xếp thứ tự**.

Khi giải quyết khóa `acme.export.enabled`, Spring xem theo thứ tự ưu tiên hiện có và lấy giá trị từ nguồn phù hợp ưu tiên cao nhất có thể cung cấp khóa đó. Nếu một nguồn không có khóa, Spring xét nguồn tiếp theo. Ưu tiên áp dụng theo **từng khóa**, không có quy tắc rằng “một nguồn được chọn thì tất cả khóa của một object phải đến từ nguồn ấy”.

Ví dụ:

```text
Ưu tiên CAO
┌─────────────────────────────────────────────┐
│ override: acme.export.enabled = true        │
│           (không có acme.export.format)     │
├─────────────────────────────────────────────┤
│ base:     acme.export.enabled = false       │
│           acme.export.format  = csv         │
└─────────────────────────────────────────────┘
Ưu tiên THẤP
```

Giá trị hiệu lực:

```text
acme.export.enabled -> true   (từ override)
acme.export.format  -> csv    (từ base)
```

**Không có chuyện khóa `format` tự rỗng** chỉ vì nguồn ưu tiên cao không khai báo nó. Mặt khác, nếu nguồn cao có `enabled=false`, Spring không bỏ qua `false` để lấy `true` từ nguồn thấp: `false` là giá trị có thật.

### Phân biệt thứ tự khai báo và thứ tự ưu tiên

Cơ chế này khác hoàn toàn với:

- Thứ tự các lớp `@Configuration`/`@AutoConfiguration` được xử lý.
- Thứ tự các bean được tạo hoặc inject.
- Thứ tự tên trường trong `@ConfigurationProperties`.
- Thứ tự dòng trong một đoạn hướng dẫn triển khai.

Thứ tự áp dụng auto-configuration có thể ảnh hưởng điều kiện bean dựa trên các bean definition đã được xử lý; còn khi xét thuộc tính, nguồn cấu hình hiệu lực trong `Environment` mới là yếu tố quyết định.

## 3. Thứ tự ưu tiên chuẩn của Spring Boot 3.3

Theo tài liệu Spring Boot 3.3, bảng sau đi từ **ưu tiên thấp lên ưu tiên cao**. Nguồn ở dưới, nếu cùng cung cấp một khóa và các nguồn đều đang hoạt động, có thể ghi đè nguồn ở trên.

| Thứ tự | Nguồn cấu hình | Ý nghĩa thực tế |
|---:|---|---|
| 1 | Default properties do `SpringApplication.setDefaultProperties(...)` đặt | Giá trị dự phòng rất thấp |
| 2 | `@PropertySource` trên `@Configuration` | Nguồn bổ sung trong quá trình refresh context |
| 3 | **Config data**: `application.properties`/`application.yml`, các profile và import | Nơi khai báo cấu hình tệp thông thường |
| 4 | `RandomValuePropertySource` | Chủ yếu cho `random.*` |
| 5 | Biến môi trường của hệ điều hành | Dùng khi triển khai container/cloud |
| 6 | Java system properties (`-Dkey=value`) | Có thể ghi đè env var tương ứng |
| 7 | JNDI `java:comp/env` | Khi chạy trong môi trường có JNDI |
| 8 | ServletContext init parameters | Áp dụng cho môi trường servlet liên quan |
| 9 | ServletConfig init parameters | Áp dụng cho servlet cụ thể |
| 10 | `SPRING_APPLICATION_JSON` / `spring.application.json` | JSON cấu hình được đưa vào Environment |
| 11 | Command-line arguments `--key=value` | Mặc định thắng các nguồn file, env, system properties trong ứng dụng SpringApplication |
| 12–14 | Thuộc tính test qua `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@TestPropertySource` | Nguồn dành cho test, chỉ xét trong ngữ cảnh có chúng |
| 15 | Devtools global settings (khi devtools hoạt động) | Nguồn đặc biệt cho môi trường phát triển |

**Không có nghĩa mọi nguồn trên đều tồn tại trong mọi lần chạy.** Ứng dụng CLI không cần servlet sẽ không có ServletConfig init parameters; ứng dụng production thông thường không có nguồn test; khi devtools không hoạt động thì không có devtools global settings. Ngoài ra, code có thể thêm `PropertySource` tùy chỉnh bằng `addFirst`, `addLast`, `addBefore` hoặc `addAfter` và thay đổi thứ tự thực tế.

Với những nguồn vận hành phổ biến trong Spring Boot 3.3, có thể nhớ:

```text
command line: --acme.export.enabled=...
               ↑ ưu tiên cao
Java system property: -Dacme.export.enabled=...
               ↑
OS environment: ACME_EXPORT_ENABLED=...
               ↑
Config data: application-prod.yml / application.yml
               ↑
SpringApplication defaultProperties
               ↑ ưu tiên thấp
```

Mũi tên chỉ chiều tăng ưu tiên. Khi chạy với `SpringApplication` mặc định, command-line arguments bắt đầu bằng `--` được đưa vào Environment; có thể tắt hành vi này bằng `setAddCommandLineProperties(false)`. Vì vậy không được khẳng định command line luôn thắng nếu ứng dụng đã tùy chỉnh cơ chế mặc định.

### 3.1. Quy tắc riêng bên trong Config Data

“Config Data” không chỉ là một file duy nhất. Với Spring Boot 3.3 theo vị trí mặc định, các nhóm file có thứ tự ghi đè thông thường từ thấp đến cao:

1. `application.properties`/YAML được đóng gói **trong JAR**.
2. `application-{profile}.properties`/YAML **trong JAR**.
3. `application.properties`/YAML **bên ngoài JAR**.
4. `application-{profile}.properties`/YAML **bên ngoài JAR**.

Ví dụ: ứng dụng đóng gói `application.yml` có `acme.export.enabled=false`, file bên ngoài JAR `application-prod.yml` có `acme.export.enabled=true` và profile `prod` được kích hoạt; cấu hình bên ngoài cho profile có ưu tiên cao hơn. Nếu command line lại đặt `--acme.export.enabled=false`, giá trị hiệu lực cuối là `false`.

Các chi tiết có thể thay đổi kết quả:

- `spring.config.import`: nguồn được import có thể **ưu tiên hơn file đã kích hoạt import**, và nếu có nhiều import thì import sau có thể ưu tiên hơn import trước.
- `spring.config.location` thay thế các vị trí cấu hình mặc định; `spring.config.additional-location` bổ sung vị trí, thường cho phép file bổ sung ghi đè.
- Nhiều profile hoạt động cùng lúc: thứ tự và nhóm vị trí cấu hình ảnh hưởng quy tắc ghi đè; với profile đơn giản, file cho profile sau có thể ghi đè profile trước.
- Nếu cùng một vị trí chứa cả `application.properties` và `application.yml`, Spring Boot ưu tiên `.properties`; nên thống nhất một định dạng để tránh khó kiểm soát.
- File YAML có nhiều document: document xuất hiện sau có thể ghi đè document trước khi cùng áp dụng.

**Vì sao cần nêu những ngoại lệ này?** Một thư viện không nên suy luận “file ngoài JAR thắng” khi ứng dụng đã thiết lập custom location/import/profile. Quyết định đúng phải dựa trên **danh sách nguồn thực tế đang chạy**.

## 4. Từ giá trị hiệu lực đến auto-configuration

Xét auto-configuration sau (đây là ví dụ minh họa; các kiểu sẽ được định nghĩa đầy đủ ở mục 7):

```java
@AutoConfiguration
@EnableConfigurationProperties(ExportProperties.class)
public class ExportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.export",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @ConditionalOnMissingBean(ExportClient.class)
    ExportClient exportClient(ExportProperties properties) {
        return new ExportClient(properties.getFormat());
    }
}
```

Ba việc khác nhau xảy ra:

1. Spring Boot thu thập và chuẩn bị các PropertySource, tạo Environment hiệu lực.
2. Khi xét phương thức `@Bean`, `@ConditionalOnProperty` đọc giá trị hiệu lực của `acme.export.enabled`. Nếu thiếu khóa hoặc giá trị không bằng `true` (so sánh bỏ qua chữ hoa/chữ thường), điều kiện không khớp.
3. Nếu điều kiện thuộc tính khớp và không có bean `ExportClient` khác khiến `@ConditionalOnMissingBean` không khớp, Spring mới đăng ký bean mặc định; `@ConfigurationProperties` bind `acme.export.format` vào `ExportProperties` để tạo `ExportClient`.

**Thư viện không quyết định thứ tự ưu tiên bằng cách khai báo `@ConditionalOnProperty` trước `@EnableConfigurationProperties`.** Hai annotation đọc các khía cạnh của Environment theo vai trò của chúng; chúng không đặt quyền ưu tiên nguồn.

### 4.1. @ConditionalOnProperty và @ConfigurationProperties có vai trò khác nhau

| Đối tượng | Nhiệm vụ | Dựa vào đâu? |
|---|---|---|
| `@ConditionalOnProperty` | Có nên đăng ký configuration/bean này không? | Giá trị property có mặt và thỏa điều kiện tại lúc đánh giá |
| `@ConfigurationProperties` | Bind các khóa vào object typed configuration | Các giá trị hiệu lực qua Binder của Spring Boot |
| `@ConditionalOnMissingBean` | Có nên nhường quyền cho bean người dùng đã tạo? | Các bean definition/ứng viên hiện có |
| `@ConditionalOnClass` | Có class phụ thuộc cần thiết trên classpath không? | Classpath, không phải PropertySource |

Một trường `format = "csv"` khởi tạo sẵn bên trong lớp `ExportProperties` là **mặc định Java của object**, hữu ích khi không có khóa `acme.export.format`. Nó **không tự chèn** `acme.export.format=csv` vào Spring Environment để các annotation điều kiện khác nhìn thấy.

Tương tự, nếu đặt `private boolean enabled = true;` làm mặc định trong một `@ConfigurationProperties` object, nhưng điều kiện trên bean dùng `@ConditionalOnProperty(..., matchIfMissing=false)`, thì **khi thiếu khóa**, bean có điều kiện vẫn **không được tạo**. Đừng giả định mặc định Java của object khiến Environment có property đó.

### 4.2. Ưu tiên nguồn không đồng nghĩa xác nhận giá trị hợp lệ

`@ConditionalOnProperty(havingValue="true")` cần chuỗi `true`; giá trị `"yes"` hoặc `"1"` dù có thể được những hệ thống chuyển đổi Boolean khác chấp nhận cũng **không** khớp với `havingValue="true"`. Nếu nguồn ưu tiên cao có `acme.export.enabled=truue` trong khi nguồn thấp có `true`, Spring chọn **`truue`** làm giá trị hiệu lực; điều kiện không khớp. Nó không tự “thử lại” giá trị `true` thấp hơn.

Với `havingValue` bỏ trống, `@ConditionalOnProperty` mặc định khớp mọi giá trị có mặt **khác `false`**. Vì vậy tính năng cần bật rõ ràng nên sử dụng `havingValue="true", matchIfMissing=false`. Nếu cần từ chối cấu hình lỗi với thông báo cụ thể, hãy dùng validation/cơ chế kiểm tra cấu hình phù hợp; điều kiện trên tự nó không bảo đảm mọi typo đều gây lỗi lúc khởi động.

### 4.3. Đừng nhầm khởi tạo một lần với cờ bật/tắt động

`@ConditionalOnProperty` thường được đánh giá lúc tạo ApplicationContext. Việc thay đổi file trên đĩa hay biến môi trường **sau khi context đã khởi động** không khiến bean được thêm/xóa tự động. Nếu yêu cầu thay đổi tính năng không cần restart, đó là một bài toán runtime khác: cần quy trình reload/refresh và quản lý trạng thái nhất quán, không thể giải quyết chỉ bằng thứ tự PropertySource.

## 5. Hợp đồng cho thuộc tính của một thư viện

Thiết kế cụ thể cho thư viện xuất dữ liệu:

| Thuộc tính | Mục đích | Giá trị mẫu | Mặc định đề xuất |
|---|---|---|---|
| `acme.export.enabled` | Cho phép đăng ký `ExportClient` mặc định | `true`/`false` | **Tắt khi thiếu** (qua `matchIfMissing=false`) |
| `acme.export.format` | Định dạng xuất dữ liệu | `csv` hoặc `json` | `csv` trong `ExportProperties` |
| `acme.export.batch-size` | Số phần tử xử lý mỗi batch nếu sau này cần | Số nguyên dương, ví dụ `100` | Có thể có default hợp lý và validation |
| `acme.export.endpoint` | Đích gửi dữ liệu nếu tích hợp bên ngoài | URL phù hợp | Có thể bắt buộc chỉ khi tính năng được bật |

**Nguyên tắc thiết kế:** thư viện nên công bố **namespace ổn định**, key ở dạng kebab-case và default rõ ràng; ứng dụng triển khai nên là nơi quyết định giá trị cấu hình cho từng môi trường. Không nên dùng khóa quá chung như `enabled` hay `service.mode` vì dễ va chạm với ứng dụng và các starter khác.

Với thư viện tùy biến do bạn sở hữu, mô hình điển hình là:

- `@AutoConfiguration` để cung cấp cơ chế đăng ký bean.
- `@EnableConfigurationProperties(...)` hoặc cơ chế scan tương ứng để đăng ký typed properties.
- `@ConditionalOnProperty` kiểm soát đăng ký tính năng theo key cấu hình.
- `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp bean thay thế nếu thư viện thiết kế extension point này.
- Default giá trị thông thường được khai báo trong object properties; các cấu hình cấp ứng dụng/profile/triển khai có thể ghi đè những khóa được công bố.

### Không dùng file cấu hình của starter để tranh quyền với ứng dụng

Một starter có thể có tài nguyên properties/YAML, nhưng không nên ngầm dựa vào việc **một file `application.properties` đóng trong JAR starter** sẽ luôn là nguồn default duy nhất hoặc có thứ tự cố định trong mọi ứng dụng. Ứng dụng có thể có nhiều config data location, import, profile và `PropertySource` tùy chỉnh. Mặc định Java trong `@ConfigurationProperties` và default của condition dễ hiểu hơn cho những tùy chọn thuộc sở hữu thư viện.

Nếu thư viện cố đặt giá trị bằng `Environment.getPropertySources().addFirst(...)` trong startup hook, nó có thể **vô tình thắng** nguồn do ứng dụng/operator cung cấp. Cách như vậy chỉ phù hợp khi có yêu cầu rõ ràng và đã công khai chính sách ưu tiên; với feature flag thông thường, đó là thiết kế không thân thiện.

Thư viện nên ghi trong tài liệu: tên đầy đủ của key, kiểu mong đợi, default nếu thiếu, tác dụng lên bean nào, có cần restart không, điều kiện để bean nhường quyền cho user bean, và ví dụ override trong `application.yml`/env/command line. Những thông tin này quan trọng hơn việc liệt kê tất cả tên lớp cấu hình nội bộ.

## 6. Ma trận tình huống ưu tiên cần kiểm thử

Với `acme.export.enabled` và `acme.export.format`, quy ước trong bảng:

- **L** = một nguồn cấu hình ưu tiên thấp đang có mặt.
- **H** = một nguồn cấu hình ưu tiên cao đang có mặt.
- **∅** = khóa không được nguồn đó cung cấp.
- Điều kiện trên bean là `havingValue="true", matchIfMissing=false`.
- `ExportProperties.format` có default Java là `csv` nếu không có cấu hình cho key đó.
- Giả sử không có bean `ExportClient` khác và không có PropertySource thứ ba có cùng khóa.

| Tình huống | L: enabled / format | H: enabled / format | Giá trị hiệu lực | Có `ExportClient`? | Format được dùng |
|---|---|---|---|---|---|
| 1. Override bật và đổi format | `false / csv` | `true / json` | `true / json` | **Có** | `json` |
| 2. Override tắt | `true / csv` | `false / json` | `false / json` | **Không** | Bean không được tạo |
| 3. Nguồn cao không khai báo khóa | `true / csv` | `∅ / ∅` | `true / csv` | **Có** | `csv` |
| 4. Nguồn cao chỉ bật feature | `false / csv` | `true / ∅` | `true / csv` | **Có** | `csv` |
| 5. Thiếu hoàn toàn enabled | `∅ / csv` | `∅ / json` | `∅ / json` | **Không** | Bean không được tạo |
| 6. Giá trị bật ở nguồn cao bị gõ sai | `true / csv` | `truue / json` | `truue / json` | **Không** | Bean không được tạo |
| 7. Nguồn cao chỉ đổi format | `true / csv` | `∅ / json` | `true / json` | **Có** | `json` |

Trong tình huống 2 và 5, bean `ExportClient` không có, nhưng nếu auto-configuration vẫn được nạp và đăng ký `ExportProperties` thì properties object có thể vẫn được bind. Chỉ việc **không có client bean** không đồng nghĩa thư viện hay toàn bộ auto-configuration chưa từng được xét.

Một vài tình huống thêm khi chạy Spring Boot thông thường:

| Nguồn thấp | Nguồn cao | Giá trị cuối | Ý nghĩa |
|---|---|---|---|
| `application.yml: enabled=false` | `--acme.export.enabled=true` | `true` | CLI bật feature |
| `application.yml: enabled=true` | `ACME_EXPORT_ENABLED=false` | `false` | OS env tắt feature nếu không có nguồn cao hơn ghi đè |
| `ACME_EXPORT_ENABLED=true` | `-Dacme.export.enabled=false` | `false` | System property ưu tiên hơn env |
| `-Dacme.export.enabled=false` | `--acme.export.enabled=true` | `true` | CLI ưu tiên hơn system property |
| `application.yml: enabled=true` | `application-prod.yml: enabled=false` trong cùng vị trí, profile prod active | `false` | Profile-specific config ghi đè base config |
| `application.yml: enabled=false` | `spring.config.import=other.properties` mà file imported đặt enabled=true | `true` | Import được xử lý với ưu tiên theo quy tắc Config Data |

**Chú ý:** tên biến môi trường tương ứng với key nhiều dấu chấm là `ACME_EXPORT_ENABLED`. Với tên nhiều dấu gạch ngang, Spring Boot áp dụng quy tắc chuyển đổi tên biến môi trường riêng; kiểm tra tên chuẩn trong tài liệu để tránh đoán. Và nếu có nguồn khác ưu tiên hơn H, ma trận phải được điều chỉnh theo nguồn thực tế.

## 7. Ví dụ Java 17+, Spring Boot 3.3: kiểm thử quyền ưu tiên

Để có một kiểm thử **độc lập với môi trường máy người học**, ví dụ không bắt buộc bạn phải thật sự sửa biến môi trường OS hoặc command line. Ta mô phỏng hai `MapPropertySource` bằng API Spring: nguồn `simulatedDeployment` ưu tiên cao hơn nguồn `simulatedConfigFile`. Sau đó, `ApplicationContextRunner` khởi tạo một context mới cho từng kịch bản và kiểm tra bean do auto-configuration cung cấp.

Đây là **mô phỏng trực tiếp quy tắc thứ tự của PropertySource**, không tuyên bố tên `simulatedDeployment` là một nguồn tự động được Spring Boot tạo. Phần so sánh file, env và CLI thật nằm ở mục 6 và mục 8.

### 7.1. Tổ chức dự án

```text
property-priority-demo/
├── pom.xml
└── src/
    ├── main/java/demo/priority/
    │   ├── ExportClient.java
    │   ├── ExportProperties.java
    │   └── ExportAutoConfiguration.java
    └── test/java/demo/priority/
        └── PropertyPriorityTest.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>property-priority-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Maven parent của Spring Boot cấu hình compiler và test plugins phù hợp. Ví dụ dùng Maven vì dễ đưa vào một thư mục độc lập, dù cùng nguyên lý áp dụng trong dự án Gradle.

### 7.3. ExportClient.java

```java
package demo.priority;

public record ExportClient(String format) {
}
```

Java 17 hỗ trợ `record`. Object này ghi nhận format thực sự được tạo từ cấu hình.

### 7.4. ExportProperties.java

```java
package demo.priority;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.export")
public class ExportProperties {

    private String format = "csv";

    public String getFormat() {
        return format;
    }

    public void setFormat(String format) {
        this.format = format;
    }
}
```

`format = "csv"` là mặc định Java; nếu Environment có `acme.export.format`, Binder có thể ghi đè nó. Lớp này **không chứa trường enabled**, vì bài kiểm thử muốn `@ConditionalOnProperty` quyết định flag trực tiếp và không gây lỗi conversion do đặt chuỗi lỗi gõ vào một trường Boolean. Trong ứng dụng sản xuất, bạn có thể bổ sung validation cho flag/format theo hợp đồng yêu cầu.

### 7.5. ExportAutoConfiguration.java

```java
package demo.priority;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(ExportProperties.class)
public class ExportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.export",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @ConditionalOnMissingBean(ExportClient.class)
    ExportClient exportClient(ExportProperties properties) {
        return new ExportClient(properties.getFormat());
    }
}
```

Trong ví dụ test ta đưa class vào context bằng `AutoConfigurations.of(...)`. Nếu đóng gói thư viện thật để Spring Boot tự phát hiện, cần đưa tên đầy đủ `demo.priority.ExportAutoConfiguration` vào `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` của JAR tương ứng.

### 7.6. PropertyPriorityTest.java

```java
package demo.priority;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class PropertyPriorityTest {

    private static final String ENABLED = "acme.export.enabled";
    private static final String FORMAT = "acme.export.format";

    // Mô phỏng hai nguồn cùng cấp từ config/deployment,
    // với simulatedDeployment được ưu tiên cao hơn.
    private ApplicationContextRunner withSources(
            Map<String, Object> lower,
            Map<String, Object> higher) {

        return new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ExportAutoConfiguration.class))
                .withInitializer(context -> {
                    var sources = context.getEnvironment().getPropertySources();
                    sources.addLast(
                            new MapPropertySource("simulatedConfigFile", lower));
                    sources.addFirst(
                            new MapPropertySource("simulatedDeployment", higher));
                });
    }

    @Test
    void higherSourceEnablesAndOverridesFormat() {
        withSources(
                Map.<String, Object>of(ENABLED, "false", FORMAT, "csv"),
                Map.<String, Object>of(ENABLED, "true", FORMAT, "json"))
                .run(context -> {
                    assertThat(context).hasSingleBean(ExportClient.class);
                    assertThat(context.getBean(ExportClient.class).format())
                            .isEqualTo("json");
                    assertThat(context.getEnvironment().getProperty(ENABLED))
                            .isEqualTo("true");
                });
    }

    @Test
    void higherFalseDisablesLowerTrue() {
        withSources(
                Map.<String, Object>of(ENABLED, "true", FORMAT, "csv"),
                Map.<String, Object>of(ENABLED, "false", FORMAT, "json"))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ExportClient.class);
                    assertThat(context.getEnvironment().getProperty(ENABLED))
                            .isEqualTo("false");
                });
    }

    @Test
    void lowerValueIsUsedWhenHigherOmitsKey() {
        withSources(
                Map.<String, Object>of(ENABLED, "true", FORMAT, "csv"),
                Map.<String, Object>of())
                .run(context -> {
                    assertThat(context).hasSingleBean(ExportClient.class);
                    assertThat(context.getBean(ExportClient.class).format())
                            .isEqualTo("csv");
                });
    }

    @Test
    void higherOnlyEnablesWhileFormatComesFromLower() {
        withSources(
                Map.<String, Object>of(ENABLED, "false", FORMAT, "csv"),
                Map.<String, Object>of(ENABLED, "true"))
                .run(context -> {
                    assertThat(context).hasSingleBean(ExportClient.class);
                    assertThat(context.getBean(ExportClient.class).format())
                            .isEqualTo("csv");
                });
    }

    @Test
    void missingFlagKeepsFeatureDisabled() {
        withSources(
                Map.<String, Object>of(FORMAT, "csv"),
                Map.<String, Object>of(FORMAT, "json"))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ExportClient.class);
                    assertThat(context.getEnvironment().getProperty(ENABLED))
                            .isNull();
                });
    }

    @Test
    void invalidHighPriorityFlagDoesNotFallBackToTrue() {
        withSources(
                Map.<String, Object>of(ENABLED, "true", FORMAT, "csv"),
                Map.<String, Object>of(ENABLED, "truue", FORMAT, "json"))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ExportClient.class);
                    assertThat(context.getEnvironment().getProperty(ENABLED))
                            .isEqualTo("truue");
                });
    }

    @Test
    void higherOnlyOverridesFormatAndKeepsLowerEnabled() {
        withSources(
                Map.<String, Object>of(ENABLED, "true", FORMAT, "csv"),
                Map.<String, Object>of(FORMAT, "json"))
                .run(context -> {
                    assertThat(context).hasSingleBean(ExportClient.class);
                    assertThat(context.getBean(ExportClient.class).format())
                            .isEqualTo("json");
                    assertThat(context.getEnvironment().getProperty(ENABLED))
                            .isEqualTo("true");
                });
    }
}
```

Chạy trong thư mục `property-priority-demo` bằng JDK 17+ và Maven:

```bash
mvn test
```

Khi môi trường xây dựng có đủ dependency, kết quả kỳ vọng là **7 bài test PASS, 0 failures, 0 errors**. Nếu dự án chỉ có file test ở trên, Maven Surefire thường báo tổng cộng 7 test; log cụ thể phụ thuộc Maven và phiên bản plugin.

Cách đọc test:

1. `simulatedConfigFile` được thêm bằng `addLast`: mô phỏng nguồn thấp, không thắng giá trị ở đầu danh sách.
2. `simulatedDeployment` được thêm bằng `addFirst`: mô phỏng nguồn cao, thắng khi cùng chứa một key.
3. Mỗi lần `withSources(...).run(...)` tạo context độc lập. Không có việc test trước để lại bean cho test sau.
4. `AutoConfigurations.of(ExportAutoConfiguration.class)` đưa auto-config cần kiểm chứng vào runner; `@ConditionalOnProperty` đọc Environment chứa hai nguồn.
5. Với key `format`, `@ConfigurationProperties` dùng Binder đọc giá trị hiệu lực, vì vậy bean `ExportClient` mang `csv` hoặc `json` đúng kịch bản.
6. Test có cờ `truue` chứng minh rằng giá trị không hợp lệ ở nguồn cao vẫn **che** giá trị `true` ở nguồn thấp. Điều kiện không được “fallback” sang giá trị thấp.
7. Test chỉ đặt `format` ở nguồn cao trong khi `enabled` đến từ nguồn thấp chứng minh rằng ưu tiên được áp dụng **theo từng key**.

### 7.7. Tự thử một trường hợp khác

Đổi tình huống `higherFalseDisablesLowerTrue` thành:

```java
withSources(
    Map.<String, Object>of(
        "acme.export.enabled", "true",
        "acme.export.format", "csv"),
    Map.<String, Object>of(
        "acme.export.enabled", "TRUE"))
```

Kết quả dự đoán: bean được tạo và format bằng `csv`. `havingValue="true"` so sánh không phân biệt chữ hoa, còn `format` không có trong nguồn cao nên dùng từ nguồn thấp. Đây là **đoạn gợi ý thay input test**, không phải method Java độc lập.

## 8. Ví dụ cấu hình thực tế: ứng dụng ghi đè thư viện

Trong ứng dụng sử dụng thư viện, file chính có thể ghi:

**`src/main/resources/application.yml`:**

```yaml
acme:
  export:
    enabled: false
    format: csv
```

**`application-prod.yml`** (khi profile prod được kích hoạt và file tương ứng được nạp):

```yaml
acme:
  export:
    enabled: true
    format: json
```

Trong điều kiện thông thường với hai file cùng location và active profile `prod`, giá trị hiệu lực là `enabled=true` và `format=json`, nên auto-config có thể tạo `ExportClient("json")`.

Nếu người vận hành chạy:

```bash
java -jar app.jar --spring.profiles.active=prod --acme.export.enabled=false
```

thì thuộc tính command line `enabled=false` ưu tiên hơn config data, feature bị tắt; điều này vẫn đúng dù file `application-prod.yml` ghi `true`, với giả định ứng dụng dùng `SpringApplication` mặc định và không có nguồn tùy chỉnh ưu tiên cao hơn.

Hoặc dùng:

```bash
java -Dacme.export.format=csv -jar app.jar --spring.profiles.active=prod
```

thì system property `format=csv` ghi đè giá trị `json` trong profile file, trong khi `enabled=true` từ profile vẫn giữ; kết quả có thể là `ExportClient("csv")`.

Các ví dụ CLI trên là **tình huống triển khai** yêu cầu đã build `app.jar` của một Spring Boot application thực tế; chúng không phải lệnh chạy trực tiếp dự án test Maven ở mục 7. Đừng nhầm project thư viện auto-config đơn lẻ với executable Spring Boot app.

### 8.1. Mặc định Java khác với giá trị nguồn thấp trong Environment

Nếu bỏ toàn bộ khóa `acme.export.format` khỏi Environment, lớp `ExportProperties` của bài có `format="csv"` nên Binder giữ mặc định Java đó. Nhưng `Environment.getProperty("acme.export.format")` có thể trả `null` vì **mặc định của object không biến thành một PropertySource**.

Tương tự, khi `enabled` vắng mặt thì mặc dù một object properties khác có trường `enabled=true`, `@ConditionalOnProperty(matchIfMissing=false)` vẫn coi điều kiện thiếu khóa là không khớp. Nên kiểm thử sự nhất quán giữa **chính sách thiếu khóa** và **mặc định trong Java object** nếu thư viện khai báo cả hai.

### 8.2. @Value và tên khóa canonical

Khi phải dùng `@Value`, ưu tiên tham chiếu khóa ở dạng canonical lowercase kebab-case, ví dụ `acme.export.batch-size`. Dạng tên canonical giúp Spring Boot xử lý nhiều biến thể relaxed binding hơn trong property placeholders. Với nhiều thuộc tính cấu trúc, `@ConfigurationProperties` thường rõ nghĩa, hỗ trợ metadata và validation hơn.

Nếu dùng env var, nên kiểm tra quy tắc đặt tên: `acme.export.enabled` có thể được cung cấp bởi `ACME_EXPORT_ENABLED`. Khi thuộc tính gồm dấu gạch ngang, quy tắc chuyển sang env var thông thường là **bỏ dấu gạch ngang**, đổi dấu chấm thành gạch dưới và viết hoa. Không tự thêm gạch dưới vào mọi vị trí rồi giả định Spring luôn nhận.

## 9. Cách tìm nguồn nào đang thắng trong ứng dụng thật

Khi feature bất ngờ bật hoặc tắt, cần tìm **cả giá trị hiệu lực lẫn nguồn gây ra nó**.

### 9.1. Bước kiểm tra ban đầu

1. Xác định đầy đủ tên key, ví dụ `acme.export.enabled`, và giá trị mà auto-config mong đợi.
2. Kiểm tra `Environment.getProperty("acme.export.enabled")`: giá trị này mới là dữ kiện đầu vào quan trọng cho điều kiện.
3. Liệt kê các nguồn đang có mặt trong `ConfigurableEnvironment.getPropertySources()`, theo đúng thứ tự thực tế.
4. Kiểm tra có `--acme.export.enabled=...`, `-Dacme.export.enabled=...`, `ACME_EXPORT_ENABLED` hay file profile/config import ghi đè hay không.
5. Quan sát **Condition Evaluation Report** của Spring Boot bằng `--debug`; nếu có Spring Boot Actuator và endpoint được cho phép truy cập, `/actuator/conditions` giúp biết tại sao auto-config/bean condition khớp hoặc không khớp.
6. Nếu cần xem cấu hình đang bind, Actuator `/actuator/configprops` có thể hữu ích; `/actuator/env` có thể hiển thị nguồn và giá trị hiệu lực tùy quyền, cấu hình endpoint và cơ chế sanitization. Không đưa secret vào log.

### 9.2. Kiểm tra property sources bằng code

Một đoạn chẩn đoán có thể chạy trong ứng dụng đã có `ConfigurableEnvironment`:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public class PropertySourceInspector {

    public static void inspect(
            ConfigurableEnvironment environment, String key) {

        System.out.println("effective=" + environment.getProperty(key));
        for (PropertySource<?> source : environment.getPropertySources()) {
            if (source.containsProperty(key)) {
                System.out.println("source=" + source.getName());
            }
        }
    }
}
```

Đây là class Java chạy được khi được gọi từ ứng dụng có Spring `Environment`, **không phải một chương trình có `main` tự chạy riêng**. Nó chỉ in tên nguồn để giảm nguy cơ vô tình ghi log cấu hình nhạy cảm; với key ví dụ `enabled`, in giá trị hiệu lực thường không nhạy cảm. Các PropertySource tổng hợp do Spring Boot/Binder tạo có thể xuất hiện trong danh sách, nên cần hiểu tên nguồn, cấu trúc wrapper và nguồn gốc (origin) khi truy vết sâu hơn; đừng coi nguồn đầu tiên có property luôn tương đương với vị trí file trên đĩa.

Để xác định chính xác file/dòng gốc trong config data, ưu tiên cơ chế origin tracking của Spring Boot hoặc báo cáo từ endpoint phù hợp. Đối với thông tin bảo mật, giữ nguyên chính sách ẩn/sanitization của Actuator.

### 9.3. Cẩn thận với null, chuỗi rỗng và placeholder

- **Không khai báo khóa**: Environment có thể trả `null`; `@ConditionalOnProperty(matchIfMissing=false)` không khớp.
- **Khai báo giá trị rỗng**: là giá trị có mặt trong nhiều dạng PropertySource; với `havingValue="true"` không khớp.
- **Giá trị `false`**: là giá trị hợp lệ và che `true` ở nguồn thấp.
- **`SPRING_APPLICATION_JSON` chứa null**: Spring Boot 3.3 ghi nhận giá trị null theo cơ chế JSON nhưng resolver có thể xem null như giá trị vắng mặt, nên null **không** bảo đảm ghi đè nguồn thấp.
- **Placeholder**: nếu cấu hình dùng tham chiếu sang key khác, giá trị resolved có thể phụ thuộc các nguồn cấu hình còn lại; dùng key canonical để tránh mismatch.

Nên viết test cho những ca này khi thư viện cần hợp đồng cấu hình chặt chẽ.

## 10. Những lỗi thường gặp khi kiểm thử ưu tiên nguồn

| Triệu chứng | Giả định sai | Cách kiểm tra/sửa |
|---|---|---|
| File `application.yml` có `enabled=true` nhưng bean không được tạo | Cho rằng file là nguồn cuối cùng | Kiểm tra system property, env var, CLI, profile, import và condition khác |
| Nguồn ưu tiên cao có `false` mà vẫn mong fallback sang `true` | Cho rằng chỉ giá trị `true` mới “có hiệu lực” | Ưu tiên dựa trên **sự hiện diện của khóa**, không phải dựa trên điều kiện khớp |
| `format` từ file thấp không còn khi nguồn cao chỉ khai báo `enabled` | Cho rằng override theo cả object | Kiểm tra từng key riêng; `format` thường vẫn lấy từ nguồn thấp |
| Test pass trên laptop nhưng fail trong CI | Nguồn env/system property khác nhau giữa môi trường | Cô lập test bằng runner với PropertySource có thứ tự tường minh |
| Đổi `@AutoConfiguration(after=...)` để sửa giá trị property bị sai | Nhầm thứ tự auto-config với nguồn property | Kiểm tra `Environment.getProperty(...)` và `PropertySources` |
| Thêm default Java `enabled=true` và mong bean điều kiện có mặt khi thiếu key | Nhầm mặc định object với Environment | Đặt policy `matchIfMissing` rõ ràng hoặc cung cấp default qua nguồn phù hợp |
| Cờ `enabled=truue` nhưng kỳ vọng startup báo lỗi | Condition chỉ không khớp, không nhất thiết validate tất cả input | Bổ sung validation/condition riêng nếu sai cấu hình phải gây lỗi |
| CLI test có input nhưng không ảnh hưởng điều kiện | App tùy chỉnh bỏ CLI properties hoặc test dùng `ApplicationContextRunner` không parse CLI | Kiểm tra cách test cấp PropertySource và startup path thực tế |
| Một user bean tồn tại nên tưởng flag không có tác dụng | `@ConditionalOnMissingBean` có thể làm bean mặc định back off | Kiểm tra cả condition thuộc tính lẫn condition bean |
| Dùng một `@PropertySource` muộn để thay `spring.main.*` | Nguồn được thêm lúc refresh có thể quá trễ cho bootstrap property | Đặt bootstrap option qua nguồn được xử lý sớm |

Nếu một auto-configuration có nhiều điều kiện, chỉ việc xác nhận giá trị property đúng **chưa đủ** để bảo đảm bean xuất hiện. Phải kiểm tra classpath, bean đã có, thứ tự auto-config và khả năng khởi tạo dependency khi liên quan.

## 11. Các bài tập kiểm tra nhanh

### Bài tập 1: system property thắng môi trường

Giả sử `ACME_EXPORT_ENABLED=true` đã có trong OS, nhưng JVM được khởi động với `-Dacme.export.enabled=false`. Không có CLI hoặc nguồn ưu tiên cao hơn. `@ConditionalOnProperty(havingValue="true")` có khớp không?

**Đáp án:** Không. Trong Spring Boot 3.3 mặc định, system property ưu tiên hơn OS environment; giá trị hiệu lực của key là `false`.

### Bài tập 2: lấy giá trị theo từng khóa

Nguồn thấp có `enabled=true, format=csv`; nguồn cao chỉ có `format=json`. Bean được tạo không và dùng format gì?

**Đáp án:** Bean có thể được tạo vì key `enabled` lấy từ nguồn thấp vẫn là `true`. Format cuối cùng là `json` từ nguồn cao.

### Bài tập 3: giá trị sai ưu tiên cao

Nguồn thấp đặt `enabled=true`; nguồn cao đặt `enabled=treu`. Cần trả về bean không?

**Đáp án:** Với `havingValue="true"`, không khớp. Resolver không quay về `true` ở nguồn thấp chỉ vì giá trị ưu tiên cao bị gõ sai. Để báo lỗi rõ khi cấu hình không hợp lệ, cần cơ chế validation bổ sung.

### Bài tập 4: profile và command line

File `application-prod.yml` có `enabled=true`, profile prod đang bật, command line có `--acme.export.enabled=false`. Giá trị cuối?

**Đáp án:** `false` khi dùng SpringApplication mặc định vì CLI ưu tiên hơn config data.

### Bài tập 5: có bean người dùng nhưng feature flag bật

`@ConditionalOnProperty(... havingValue="true")` khớp; tuy nhiên application đã đăng ký một `ExportClient` phù hợp trước, và auto-config có `@ConditionalOnMissingBean(ExportClient.class)`. Bean mặc định của thư viện có tạo không?

**Đáp án:** Không. Flag cho phép tính năng, nhưng điều kiện missing-bean làm thư viện nhường quyền cho bean do ứng dụng cung cấp. Đây là **quy tắc bean**, không phải nguồn config có ưu tiên cao hơn.

### Bài tập 6: mặc định object

`ExportProperties.format` được khởi tạo `"csv"`; toàn bộ Environment thiếu `acme.export.format`. `Environment.getProperty("acme.export.format")` chắc chắn trả về `"csv"`?

**Đáp án:** Không. Giá trị Java default ở object không tự thêm một PropertySource. Binder có thể giữ `"csv"` trong object, trong khi Environment vẫn không có khóa tương ứng.

## 12. Tổng kết quy tắc thực hành

- **Nguồn cấu hình** quyết định giá trị hiệu lực của từng key; nguồn ưu tiên cao có key sẽ thắng nguồn thấp theo quy tắc đang áp dụng.
- Trong Spring Boot 3.3 thông thường, **command line** ưu tiên hơn system properties, OS environment và config data; **test property sources** và custom sources có thể thay đổi thứ tự trong phạm vi của chúng.
- Auto-configuration dùng **Environment đã được chuẩn bị** để kiểm tra `@ConditionalOnProperty`; `@ConfigurationProperties` bind từng key vào object, không tự cấp ưu tiên khác cho thư viện.
- Thiết kế starter với **namespace riêng, default rõ, flag bật tường minh**, đồng thời cho phép application/deployment override theo cơ chế Spring Boot.
- Kiểm thử cả **bean có hay không**, **giá trị bound cuối cùng**, **tình huống missing/typo**, **xung đột nguồn**, và **ứng dụng có bean thay thế**.
- Khi kết quả trái kỳ vọng, kiểm tra **PropertySources theo thứ tự thực tế**, `Environment.getProperty(...)` và Condition Evaluation Report; không suy đoán chỉ từ một file `application.yml`.

### Tài liệu chính thức

- [Spring Boot 3.3 — Externalized Configuration và PropertySource Order](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
