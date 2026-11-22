# Dùng spring-boot-properties-migrator khi nâng cấp thuộc tính do Boot quản lý

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Thiết kế và nâng cấp

## 1. Vấn đề: ứng dụng vẫn biên dịch, nhưng cấu hình đã đổi ý nghĩa

Nâng cấp một ứng dụng Spring Boot không chỉ là đổi phiên bản trong Maven hoặc Gradle. Một phiên bản Spring Boot mới có thể **đổi tên, deprecate, di chuyển hoặc loại bỏ một số configuration properties** mà phiên bản cũ từng chấp nhận.

Ví dụ, một project có file:

~~~properties
spring.kafka.retry.topic.delay=2s
~~~

Ở những phiên bản Spring Boot mới có thay đổi tương ứng được ghi trong danh sách deprecated application properties, tên key được khuyến nghị có thể chuyển thành:

~~~properties
spring.kafka.retry.topic.backoff.delay=2s
~~~

Hai đoạn trên minh họa một trường hợp đổi tên được tài liệu Spring Boot 4.2 liệt kê; không nên áp dụng thay thế đó cho mọi phiên bản Boot hoặc mọi ứng dụng nếu chưa đối chiếu dependency và tính năng đang dùng.

Một tình huống điển hình:

1. Ứng dụng chạy tốt ở phiên bản cũ.
2. Nhóm nâng cấp Spring Boot hoặc một starter liên quan.
3. Build vẫn thành công vì YAML/properties chỉ chứa dữ liệu text.
4. Một số key cũ không còn được consumer tương ứng nhận biết, hoặc vẫn được nhận nhưng đã deprecated.
5. Ứng dụng khởi động với **default khác**, bỏ qua cấu hình tưởng đã áp dụng, hoặc hành vi ở runtime đổi ngoài ý muốn.

Đây là kiểu lỗi nguy hiểm: **không nhất thiết có compile error**. Một tên key sai hoặc đã bị loại bỏ có thể nằm yên trong file application configuration mà không khiến lập trình viên chú ý.

Spring Boot cung cấp module **`spring-boot-properties-migrator`** để hỗ trợ quá trình nâng cấp. Khi được thêm tạm thời vào runtime classpath, module có thể:

- Phân tích những configuration properties có hiệu lực trong `Environment` lúc khởi động.
- Phát hiện một số property đã đổi tên, deprecated hoặc không còn được hỗ trợ theo metadata mà phiên bản Boot đang dùng biết tới.
- In thông tin chẩn đoán để người nâng cấp sửa nguồn cấu hình.
- **Tạm thời di chuyển một số property tại runtime** nhằm hỗ trợ ứng dụng chuyển tiếp trong quá trình sửa cấu hình.

Công cụ này là **cầu nối tạm thời**, không phải một lớp tương thích vĩnh viễn và không thể thay thế migration guide, release notes, kiểm thử chức năng hoặc việc chủ động cập nhật các cấu hình thật.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Giải thích được vì sao đổi phiên bản Boot có thể làm hỏng cấu hình mà không tạo lỗi biên dịch.
2. Phân biệt property **renamed**, **deprecated**, **removed** và thay đổi semantics.
3. Thêm `spring-boot-properties-migrator` đúng phạm vi dependency trong Maven/Gradle.
4. Khởi động ứng dụng với đúng profile và nguồn cấu hình để đọc diagnostics.
5. Chuyển cảnh báo thành danh sách việc cần sửa ở YAML, properties, environment variables, CLI và deployment manifests.
6. Hiểu giới hạn thời điểm xử lý của migrator, đặc biệt với `@PropertySource` được thêm muộn.
7. Giải quyết xung đột khi key cũ và key mới cùng tồn tại ở các nguồn có precedence khác nhau.
8. Biết cách kiểm tra behavior thực tế bằng tests thay vì tin rằng migrator “chạy thành công” là đủ.
9. Sử dụng tùy chọn fail theo phiên bản khi được hỗ trợ để phát hiện migration còn sót.
10. Gỡ module migrator khỏi dependency sau khi hoàn tất, và kiểm tra lại artifact không còn phụ thuộc vào migration tạm.

## 2. Bốn loại thay đổi cấu hình phải nhận diện

### 2.1. Renamed property — chỉ đổi tên hoặc nhóm key

Một key cũ được thay bằng key mới, đôi khi cấu trúc prefix cũng đổi:

~~~text
Tên cũ: spring.kafka.retry.topic.delay
Tên mới: spring.kafka.retry.topic.backoff.delay
~~~

Đây là một ví dụ có thể xác nhận trong deprecated properties appendix của Spring Boot 4.2. Khi nâng cấp đến một phiên bản tương ứng, phải kiểm tra xem key cũ còn được hỗ trợ tạm thời, có replacement metadata và migrator có đề xuất chuyển đổi hay không.

**Không chỉ sửa tên trong một file**: cùng key có thể xuất hiện trong ConfigMap, biến môi trường, lệnh khởi động, Helm values và file profile-specific.

### 2.2. Deprecated property — còn hiện diện nhưng không nên tiếp tục dùng

Một property có thể được đánh dấu không còn khuyến nghị. Nó có thể vẫn hoạt động trong phiên bản hiện tại nhưng dự kiến bị xóa trong phiên bản sau.

Điều đó **không** có nghĩa bạn được phép giữ lại mãi vì “vẫn chạy tốt”. Trong lần nâng cấp tiếp theo, compatibility có thể bị loại bỏ.

Ví dụ trong tài liệu Spring Boot hiện hành có những property được đánh dấu deprecated nhưng không phải cái nào cũng có replacement đơn giản. Phải đọc `reason`, `replacement` và migration guide thay vì sửa theo một quy tắc chung.

### 2.3. Removed property — không còn được hỗ trợ

Khi property bị xóa hẳn, không thể mặc định có một key mới tương đương. Có thể tính năng đã biến mất, cơ chế cấu hình được thiết kế lại hoặc cần thay code.

Ví dụ một công cụ báo “không còn được hỗ trợ” thay vì “đổi tên thành X”. Khi đó, tìm hiểu chức năng mới trong release notes hoặc API docs. Không tự phát minh một tên thay thế chỉ để tắt cảnh báo.

### 2.4. Behavior/semantics change — tên mới chưa đủ

Có những thay đổi từ một boolean thành enum hoặc một giá trị với semantics khác. Chẳng hạn danh sách deprecation của một số phiên bản Spring Boot mô tả việc thay property dạng **enabled** bằng property quyết định **mode**. Khi đó, copy nguyên giá trị `true` hay `false` vào key mới có thể sai kiểu hoặc sai ý nghĩa.

Ví dụ sơ đồ ý tưởng:

~~~text
old.feature.enabled=true
           |
           v
new.feature.mode=<giá trị enum phù hợp>
~~~

Các key `old.feature.*` và `new.feature.*` ở trên **là tên giả định để minh họa**, không phải thuộc tính Spring Boot thật. Chỉ có thể chọn giá trị mới sau khi hiểu hợp đồng cấu hình cụ thể.

Đối với những thay đổi semantics, migrator có thể giúp phát hiện nhưng **không thể thay bạn quyết định nghiệp vụ** hoặc sửa hoàn toàn Java code và dependency đã đổi.

## 3. spring-boot-properties-migrator là gì?

Tên Maven/Gradle artifact:

~~~text
org.springframework.boot:spring-boot-properties-migrator
~~~

Đây là một module chính thức do Spring Boot cung cấp để giúp nâng cấp configuration properties. Nó khác với:

- `spring-boot-configuration-processor`: sinh metadata cấu hình cho IDE và tooling lúc build.
- `spring-boot-starter-validation`: cung cấp Bean Validation để kiểm tra giá trị typed configuration.
- `@ConfigurationProperties`: bind property từ `Environment` thành Java object.
- `spring.config.import`: đưa Config Data bổ sung vào quá trình tạo `Environment`.
- Database migration tools như Flyway/Liquibase: thay đổi schema dữ liệu, **không** chuyển configuration property keys.

Migrator tập trung vào **configuration-property migration khi nâng cấp Spring Boot**.

### 3.1. Nó phát hiện vấn đề lúc nào?

Module phân tích `Environment` trong giai đoạn khởi động được Boot tích hợp. Những property sources đã được chuẩn bị đủ sớm có thể được phân tích. Nó ghi diagnostics lên log khởi động, và với những trường hợp metadata cho phép có thể tạm chuyển đổi property tại runtime.

Điểm quan trọng: **đây không phải một linter quét toàn bộ repository**. Nó không tự truy cập Git, Helm chart, mọi values file, tất cả manifests và mọi cấu hình chỉ dùng ở production. Nó quan sát **những property đang có mặt trong Environment của lần khởi động cụ thể**, theo cơ chế Boot hỗ trợ.

Nếu chạy chỉ với profile `dev`, không được kết luận mọi cấu hình của `prod` đã sạch.

### 3.2. Nó không thay đổi file nguồn

Ngay cả khi migrator thông báo một key đã được chuyển tạm thời, nội dung `application.yml`, `application.properties`, Kubernetes ConfigMap hoặc environment variable vẫn là giá trị bạn đã khai báo.

Không có phép màu sửa source code/config deployment cho bạn. Kỹ sư phải mở đúng nơi cấp key và thay thế có chủ đích.

### 3.3. Tại sao runtime migration chỉ là tạm thời?

Nếu dự án giữ lại module này mãi, bạn có thể gặp các vấn đề:

- Một lần nâng cấp tiếp theo xóa hỗ trợ tương thích hiện tại.
- Diagnostics bị bỏ qua vì ứng dụng vẫn “chạy được”.
- Dev và production dùng nguồn khác nhưng chỉ một môi trường được thử.
- Runtime phải duy trì đường xử lý ngoài hợp đồng cấu hình cuối cùng.
- Một thay đổi tên key thành công che lấp thay đổi semantics khác.

Tài liệu chính thức của Spring Boot yêu cầu **gỡ dependency sau khi migration kết thúc**.

## 4. Chuẩn bị trước khi bật migrator

Đừng bắt đầu bằng cách thêm dependency vào production mà chưa biết đang nâng cấp từ đâu đến đâu.

### 4.1. Chốt nguồn và đích nâng cấp

Ví dụ:

~~~text
From: Spring Boot 3.x
To:   Spring Boot 4.x
~~~

Đây chỉ là ví dụ. Nâng từ `3.3` lên `3.5`, từ `3.x` lên `4.x`, hoặc giữa các minor versions có danh sách property changes khác nhau.

Trước khi chạy:

1. Xác nhận phiên bản Spring Boot hiện hành.
2. Chọn phiên bản đích cụ thể.
3. Đọc release notes/migration guide của tất cả các bước cần qua.
4. Kiểm tra phiên bản JDK, Spring Framework và starters cần nâng.
5. Xác định các config sources theo từng môi trường.
6. Chuẩn bị test và rollback.

Không dùng một trang deprecated properties của phiên bản mới nhất để suy ra mọi hành vi của một ứng dụng đang chạy Boot cũ.

### 4.2. Liệt kê nơi có thể chứa key cũ

| Nguồn | Ví dụ | Cần sửa ở đâu? |
| --- | --- | --- |
| Default config trong JAR | `src/main/resources/application.yml` | Source project |
| Profile-specific file | `application-prod.yml` | Source/config repository |
| External config | `./config/application.properties` | Hạ tầng hoặc mounted file |
| Config Data import | `spring.config.import=...` | File được import và nguồn của nó |
| OS environment | `SPRING_KAFKA_RETRY_TOPIC_DELAY` theo quy tắc tên tương ứng | Deployment env / CI |
| Java system property | `-Dspring.kafka.retry.topic.delay=2s` | Startup script / JVM options |
| Command line | `--spring.kafka.retry.topic.delay=2s` | Args của process |
| Kubernetes ConfigMap | Các keys hoặc file contents | ConfigMap/Helm/GitOps |
| Test configuration | `@SpringBootTest(properties=...)` | Test code |
| Test resources | `application-test.yml` | Test configuration |
| Docker Compose/CI | `environment:` hoặc startup flags | Compose/pipeline |
| Third-party secret/config manager | Key/value theo môi trường | Store và sync configuration |

Tên biến môi trường cần được suy ra từ quy tắc relaxed binding áp dụng cho key **thật** và phiên bản Boot đang dùng. Không dựa vào bảng ví dụ này để tự suy ra mọi biến đã được hệ thống deploy cấp.

### 4.3. Không chỉnh đồng thời quá nhiều thứ

Một upgrade có thể kéo theo JDK, Boot, framework, Jackson, Servlet APIs, starters và configuration properties. Nếu cùng lúc đổi nhiều nguồn và nhiều hành vi nghiệp vụ, sẽ khó xác định nguyên nhân khi test fail.

Cách vận hành tốt là có **bản so sánh before/after**, chia thành các thay đổi có thể review và chạy regression tests theo từng giai đoạn.

## 5. Cài đặt migrator với Maven

Trong `pom.xml` của module Spring Boot application:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Nếu project sử dụng Spring Boot parent/BOM, phiên bản dependency thường được quản lý phù hợp. Nếu không dùng dependency management, cần chỉ định phiên bản tương thích với Spring Boot đích trong build config.

### 5.1. Vì sao dùng runtime scope?

Migrator hoạt động khi ứng dụng khởi động. Nó không phải API business code mà bạn cần import trong Java source. `runtime` giúp xác định đây là công cụ hỗ trợ khi chạy và không cần xuất hiện như một dependency compile-time thông thường.

### 5.2. Module nào phải thêm?

Với project nhiều module, hãy chú ý runtime classpath **của ứng dụng thực sự khởi động**. Nếu chỉ thêm dependency trong một module library không được đóng gói vào executable application, migrator có thể không có mặt khi JVM của service chạy.

Đừng thêm migrator bừa vào mọi shared library để phát hành vĩnh viễn. Thông thường nên thêm ở module app hoặc nơi quản lý runtime dependencies của artifact được nâng cấp.

### 5.3. Không nhầm với annotation processor

Cấu hình khác:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Processor sinh metadata hỗ trợ IDE; migrator dùng để chẩn đoán/migrate property trong quá trình chạy. Hai module có tên tương tự trong cùng group ID nhưng **không cùng mục đích**.

## 6. Cài đặt migrator với Gradle

Gradle Groovy DSL:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.boot:spring-boot-properties-migrator")
}
~~~

`runtimeOnly` nhấn mạnh rằng migrator không phải library để Java code gọi trong nghiệp vụ. Với plugin/dependency management của Spring Boot, không nhất thiết phải ghi phiên bản trong snippet, nhưng nếu project quản lý phiên bản thủ công thì cần khớp phiên bản target.

### 6.1. Đừng chỉ thêm testImplementation

Nếu đặt module trong test scope mà không có trên runtime classpath của ứng dụng khi chạy thử nâng cấp, bạn có thể thấy test setup khác runtime mong muốn.

Ngược lại, nếu chỉ định giữ migrator trong môi trường test/staging với packaging khác, phải xác định cách nó được đưa vào runtime classpath của **lần chạy được phân tích**. Mục tiêu là kiểm tra một instance thực sự khởi động với module có mặt.

### 6.2. Đừng commit thành dependency vĩnh viễn

Trong quá trình upgrade, một pull request có thể tạm thêm migrator để chẩn đoán. Sau khi mọi key đã được sửa, cần một commit/PR follow-up **gỡ dependency**, chạy tests và xác nhận artifact cuối cùng không còn chứa nó.

Một task migration chỉ được xem là hoàn tất khi không cần công cụ này để application giữ hành vi hợp lệ.

## 7. Quy trình cơ bản: thêm, chạy, đọc, sửa, chạy lại, gỡ

Sơ đồ:

~~~text
Chọn phiên bản Spring Boot đích
               |
               v
Thêm spring-boot-properties-migrator
               |
               v
Khởi động với config môi trường thử nghiệm
               |
               v
Đọc diagnostics từ startup log
               |
               v
Phân loại renamed / deprecated / removed
               |
               v
Sửa file, env, CLI, config import, manifests
               |
               v
Chạy lại với đúng profile và nguồn
               |
               v
Regression tests + kiểm tra behavior
               |
               v
Gỡ spring-boot-properties-migrator
               |
               v
Chạy startup & tests lại KHÔNG có migrator
               |
               v
Triển khai có quan sát và rollback
~~~

### 7.1. Lần chạy đầu phải đại diện cho cấu hình thật

Nếu service thường khởi động với:

~~~bash
java -jar catalog-service.jar \
  --spring.profiles.active=staging
~~~

hãy chạy một lần kiểm tra với profile `staging` và các nguồn mô phỏng điều kiện triển khai. Không cần phải dùng production secrets để kiểm tra property names; có thể dùng thông tin thử nghiệm hợp lệ và endpoints test.

Một lần khởi động không có profile nào có thể chỉ chạm vào default file và bỏ qua toàn bộ `application-prod.yml` hoặc imported config chỉ active trong production.

### 7.2. Xem toàn bộ logs chứ không chỉ dòng “Started”

Migrator đưa diagnostics vào quá trình startup. Một lần chạy có thể cuối cùng báo “Started ...” nhưng trước đó đã xuất hiện danh sách property cần sửa.

Đừng chỉ kiểm tra exit code bằng 0 rồi kết luận không còn technical debt cấu hình. Cần tìm các log về unsupported/renamed/deprecated property và ghi nhận chúng.

### 7.3. Sửa nguồn thật, không sửa giá trị hiệu lực tạm

Nếu migrator thêm một replacement ở runtime, việc `Environment` đọc được key mới không có nghĩa file đã được sửa. Cần cập nhật **đầu vào** thực tế và xác nhận nguồn nào sẽ cung cấp key trong lần chạy tiếp theo không có migrator.

## 8. Ví dụ thực hành với một property Boot có tên đổi

**Bối cảnh minh họa theo danh sách deprecation của Spring Boot 4.2**: một số thuộc tính Kafka retry-topic đã được chuyển vào nhóm `backoff`.

Trước khi sửa:

~~~properties
spring.kafka.retry.topic.delay=2s
spring.kafka.retry.topic.max-delay=20s
spring.kafka.retry.topic.multiplier=2
~~~

Các tên thay thế được liệt kê trong tài liệu tương ứng:

~~~properties
spring.kafka.retry.topic.backoff.delay=2s
spring.kafka.retry.topic.backoff.max-delay=20s
spring.kafka.retry.topic.backoff.multiplier=2
~~~

### 8.1. Vì sao dùng ví dụ có phiên bản đi kèm?

Không có một mapping chung cho mọi Boot release. Nếu đang nâng từ Boot 2.x sang Boot 3.x, danh sách đổi tên có thể khác. Luôn đọc appendix của **version target**, không copy ví dụ như một recipe universal.

### 8.2. Ứng dụng không dùng Kafka thì sao?

Nếu project không có tích hợp Kafka retry topics hoặc không bật tính năng liên quan, key ví dụ có thể không áp dụng. Đừng thêm các property này chỉ để “thử migrator” trên một dự án không sử dụng Kafka.

Khi cần demo, tạo một ứng dụng thử nghiệm ở đúng version/starter và kiểm tra property thực sự thuộc module đó.

### 8.3. Sửa YAML với cùng mapping

Trước:

~~~yaml
spring:
  kafka:
    retry:
      topic:
        delay: 2s
        max-delay: 20s
        multiplier: 2
~~~

Sau:

~~~yaml
spring:
  kafka:
    retry:
      topic:
        backoff:
          delay: 2s
          max-delay: 20s
          multiplier: 2
~~~

Đặc điểm của YAML là thay key prefix có thể cần đổi **cấu trúc object lồng nhau**, không chỉ tìm và thay một string có dấu chấm.

### 8.4. Xác nhận hành vi sau thay đổi

Đừng chỉ kiểm tra YAML có các tên mới. Cần chạy một test phù hợp xác nhận cấu hình retry/backoff đã được áp dụng cho hệ thống thực tế hoặc bean đang dùng, kể cả sau khi gỡ migrator.

Nếu là số hoặc Duration, kiểm tra conversion và đơn vị. Một typo như `max-deley` có thể khiến ứng dụng dùng default mà không rõ lỗi ngay.

## 9. Đọc diagnostics như một backlog có thể hành động

Một output chẩn đoán minh họa, **không phải bản sao chính xác của một phiên bản Spring Boot cụ thể**:

~~~text
Migration diagnostics
  Property: spring.kafka.retry.topic.delay
  Status: renamed/deprecated
  Suggested replacement:
    spring.kafka.retry.topic.backoff.delay
  Source: application.yml
~~~

Format/log level/thông tin source thực tế có thể khác theo phiên bản Boot, metadata và loại PropertySource. Đừng viết một script phụ thuộc chính xác vào dấu cách hoặc ngôn ngữ của ví dụ.

### 9.1. Bảng hành động từ diagnostics

| Trường cần ghi | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Property cũ | Key nào được báo? | `spring.kafka.retry.topic.delay` |
| Tình trạng | Rename, deprecated, removed? | Renamed |
| Replacement | Có property mới được chỉ rõ không? | `spring.kafka.retry.topic.backoff.delay` |
| Nguồn | Giá trị đến từ đâu? | `application-staging.yml` |
| Profile | File/document có active không? | `staging` |
| Value | Kiểu/đơn vị có cần chuyển đổi không? | `2s` |
| Owner | Team nào quản lý nguồn này? | Platform/Messaging |
| Test | Kiểm tra nào chứng minh behavior đúng? | Retry policy integration test |
| Trạng thái | Đã thay ở mọi môi trường chưa? | Staging xong, prod chưa |

### 9.2. Phân loại theo mức rủi ro

- **Rename thuần:** thường ưu tiên sửa key và chạy binding/functional test.
- **Rename kèm thay kiểu:** cần đọc chi tiết semantics trước khi đổi value.
- **Removed, không có replacement:** có thể phải thay kiến trúc hoặc bỏ một tính năng.
- **Không có diagnostics nhưng behavior sai:** vẫn phải kiểm tra migration guide, code và các key chưa được nạp.

Migrator là nguồn tín hiệu quan trọng, không phải bằng chứng đầy đủ rằng toàn bộ migration đã kết thúc.

## 10. Mối quan hệ với Spring Boot configuration metadata

Spring Boot có cấu trúc metadata JSON mô tả các configuration properties:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Một property có thể mang thông tin `deprecation` như `reason` hoặc `replacement` trong schema metadata.

Ví dụ cấu trúc minh họa:

~~~json
{
  "properties": [
    {
      "name": "example.old-timeout",
      "type": "java.time.Duration",
      "deprecation": {
        "level": "warning",
        "reason": "Tên thuộc tính cũ sẽ được loại bỏ.",
        "replacement": "example.client.timeout"
      }
    }
  ]
}
~~~

**`example.*` ở đây chỉ là key giả định để minh họa schema**, không phải key của Spring Boot. Không kết luận rằng chỉ cần tự thêm metadata này là migrator chắc chắn sẽ cung cấp tương thích runtime cho mọi property custom.

### 10.1. Deprecated metadata khác binding semantics

Metadata có thể giúp công cụ biết property cũ và replacement được khuyến nghị. Nhưng cấu hình ứng dụng vẫn cần consumer thực sự hỗ trợ key mới, và một number/string value cũ chưa chắc có ý nghĩa tương đương.

Không dùng một replacement string như bằng chứng về dữ liệu được chuyển đúng trong mọi tình huống.

### 10.2. Compiler không kiểm tra mọi property trong YAML

`application.yml` và `application.properties` thường được parse lúc runtime. Việc mã Java compile thành công không đảm bảo mọi key tồn tại, đúng version hoặc đã được starter liên quan hỗ trợ.

Đây là lý do migrator có giá trị thực tế khi upgrade: nó thu hẹp khoảng cách giữa **đổi dependency** và **đổi configuration contract**.

### 10.3. Migrator không phải configuration processor

`spring-boot-configuration-processor` tạo metadata từ `@ConfigurationProperties` classes, thường phục vụ IDE. `spring-boot-properties-migrator` chạy trong ứng dụng để kiểm tra và hỗ trợ chuyển tiếp config properties.

Không thêm annotation processor rồi kỳ vọng nó tự in runtime migration diagnostics.

## 11. Thứ tự ưu tiên nguồn cấu hình khi hai tên key cùng tồn tại

Giả sử có hai nguồn:

~~~yaml
# application.yml
spring:
  kafka:
    retry:
      topic:
        delay: 2s
~~~

Và một file externalized theo phiên bản mới:

~~~yaml
# ./config/application.yml
spring:
  kafka:
    retry:
      topic:
        backoff:
          delay: 5s
~~~

Ta đã có **key cũ** và **key mới** với hai giá trị khác nhau.

Câu hỏi “value cuối cùng là bao nhiêu?” không thể trả lời chỉ bằng việc “file ngoài JAR ưu tiên hơn file trong JAR”, vì còn cơ chế chuyển property cũ thành property mới và xử lý khi đồng thời có cả hai tên.

**Nguyên tắc migration an toàn:** tránh tồn tại đồng thời key cũ và key mới cho cùng một ý nghĩa trong các nguồn còn có hiệu lực. Hãy sửa tất cả source liên quan và kiểm tra giá trị cuối bằng test sau khi gỡ migrator.

### 11.1. PropertySource precedence vẫn là một phần của bài toán

Spring Boot có các lớp nguồn như:

- Config Data trong JAR.
- Config Data ở ngoài JAR.
- Imported Config Data.
- Profile-specific config.
- OS environment variables.
- Java system properties.
- `SPRING_APPLICATION_JSON`.
- Command-line arguments.
- Test property sources.

Một nguồn ưu tiên cao hơn có thể ghi đè giá trị cùng tên. Khi đổi **tên key**, còn có nguy cơ giá trị cũ và mới không cùng một tên trong những lần tra cứu ban đầu.

Nếu dùng migrator, phải xem diagnostics và đo actual binding. Đừng tự giả định luật “old always wins” hoặc “new always wins” cho mọi phiên bản và conflict scenario.

### 11.2. Cách tránh xung đột

1. Liệt kê mọi nguồn nơi key cũ xuất hiện.
2. Quyết định giá trị canonical sau nâng cấp.
3. Thay key cũ thành key mới ở tất cả nguồn do team quản lý.
4. Xóa các override đã lỗi thời, không chỉ bổ sung một override khác.
5. Chạy test với migrator để tìm phần còn sót.
6. Gỡ migrator và kiểm tra giá trị cuối trong environment triển khai tương đương.

### 11.3. Ví dụ CLI có thể ghi đè file đã sửa

File YAML đã đổi sang key mới:

~~~yaml
spring:
  kafka:
    retry:
      topic:
        backoff:
          delay: 5s
~~~

Nhưng script chạy vẫn truyền:

~~~bash
java -jar app.jar \
  --spring.kafka.retry.topic.delay=2s
~~~

Một lần migration chưa hoàn tất ở **startup arguments**. Cần sửa script hoặc CI/CD release job, không chỉ sửa YAML source.

## 12. Profile và multi-document: một lần chạy không quét hết mọi môi trường

File `application.yml` có nhiều document:

~~~yaml
app:
  deployment:
    label: "default"

---
spring:
  config:
    activate:
      on-profile: prod

app:
  deployment:
    label: "production"
~~~

Trong giai đoạn Config Data, Spring Boot quyết định document nào active dựa trên profile/conditions. Những key không nằm trong active documents có thể **không xuất hiện trong Environment** của lần chạy đó.

Nếu key cũ chỉ có ở `application-prod.yml`, một lần chạy với profile `dev` có thể không báo gì.

### 12.1. Ma trận kiểm tra profile

| Kịch bản | Mục tiêu |
| --- | --- |
| Không có profile tường minh | Kiểm tra default Config Data |
| `dev` | Kiểm tra tài liệu phát triển |
| `test` | Kiểm tra test-specific sources |
| `staging` | Kiểm tra manifest tương đương staging |
| `prod` trong môi trường thử nghiệm an toàn | Phát hiện key trong production config |
| Nhiều profiles cùng active | Kiểm tra thứ tự và override |
| Config import riêng cho môi trường | Kiểm tra key từ imported resources |

Không dùng production secret thật để chạy một ứng dụng thử chỉ nhằm tìm key cũ. Có thể tạo một cấu hình mô phỏng với placeholder hợp lệ, nhưng cần biết những khác biệt so với production.

### 12.2. Tài liệu chỉ active theo cloud platform

Một Config Data document có thể chỉ active dưới điều kiện cloud platform. Việc chạy app trên laptop với cùng `spring.profiles.active` chưa chắc nạp tài liệu Kubernetes-specific.

Do đó, migration inventory nên kết hợp **startup diagnostics** với **tìm kiếm tĩnh các file manifests/config repositories**; một công cụ không thay thế công cụ kia.

## 13. Hạn chế quan trọng: @PropertySource được thêm muộn

Tài liệu Spring Boot nêu rõ rằng những properties **được thêm muộn vào Environment**, ví dụ bằng `@PropertySource`, **không được migrator tính đến**.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy-boot-options.properties")
public class LegacyBootOptionsConfig {}
~~~

Tệp:

~~~properties
# Ví dụ key cũ ở một release mà team đang nâng cấp.
spring.kafka.retry.topic.delay=2s
~~~

Nếu `@PropertySource` chỉ được xử lý khi ApplicationContext refresh, migrator có thể đã chạy trước khi source này được thêm. Đừng xem việc log “không có cảnh báo” là bằng chứng tệp đó không chứa key cũ.

### 13.1. Vì sao thời điểm quan trọng?

Một mô hình đơn giản:

~~~text
SpringApplication starts
          |
          v
Build/prepare Environment
  - OS env
  - system properties
  - command-line
  - Config Data and imports
          |
          v
Properties migrator analyzes available sources
          |
          v
ApplicationContext refresh
          |
          v
@Configuration processing
  - @PropertySource might be added here
          |
          v
Beans initialized
~~~

Sơ đồ mang tính khái quát, không thay thế từng lifecycle hook chính xác ở mọi phiên bản. Điều quan trọng là **migrator không quét được các nguồn thêm sau thời điểm nó phân tích**.

### 13.2. Cách xử lý nguồn muộn

- Kiểm tra trực tiếp file `legacy-boot-options.properties`.
- Xác định có thật cần `@PropertySource` cho key do Boot quản lý không.
- Nếu file là cấu hình Boot chuẩn, cân nhắc đưa vào Config Data hoặc import tương ứng.
- Không đổi loader đột ngột chỉ để migrator thấy được mà chưa kiểm tra precedence và thời điểm nạp.
- Đối với configuration logic custom, viết test hoặc check tĩnh để phát hiện các key không còn được hỗ trợ.

### 13.3. Một số thuộc tính phải được cấp rất sớm

Các property như `logging.*`, `spring.main.*` và các key điều khiển Config Data locations được Spring Boot dùng ở những giai đoạn sớm. Đặt chúng trong `@PropertySource` có thể quá muộn cho hiệu ứng mong muốn, bất kể có migrator hay không.

Migrator không biến một source thêm muộn thành bootstrap property source.

## 14. Không nhầm phát hiện key cũ với kiểm thử behavior

Giả sử diagnositcs không còn warning. Ứng dụng vẫn có thể sai vì:

- Key mới có kiểu dữ liệu khác.
- Default đã đổi.
- Auto-configuration được thiết kế lại.
- Starter cũ được thay thế hoặc không còn trên classpath.
- Một tùy chọn previously enabled đã được chuyển thành policy.
- Key cũ chỉ tồn tại trong nguồn không active khi chạy test.
- Test cấu hình không có dependency tương ứng, nên property không được sử dụng như tưởng tượng.
- Bean client được tạo với cấu hình khác do một source ưu tiên cao hơn.

Do đó, cùng lúc cần kiểm tra:

1. **Configuration diagnostics**: còn key cũ không?
2. **Binding**: bean config cuối cùng nhận những giá trị nào?
3. **Behavior**: chức năng phụ thuộc vào config có hoạt động đúng?
4. **Deployment**: mọi instance/profile có dùng cùng contract mới?

## 15. Ví dụ kiểm thử typed configuration sau migration

Giả sử một ứng dụng có config riêng cho một client, và việc nâng Boot làm thay đổi cách client được tạo. Với key custom không liên quan trực tiếp đến migrator, vẫn có thể kiểm tra typed config:

~~~java
package com.example.catalog.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        Duration timeout,
        int maxAttempts
) {}
~~~

Test với `ApplicationContextRunner`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class CatalogConfigurationTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogClientProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsExpectedValues() {
        runner.withPropertyValues(
                "catalog.client.timeout=5s",
                "catalog.client.max-attempts=3"
        ).run(context -> {
            var config = context.getBean(
                    CatalogClientProperties.class);

            assertThat(config.timeout())
                    .isEqualTo(Duration.ofSeconds(5));
            assertThat(config.maxAttempts()).isEqualTo(3);
        });
    }
}
~~~

Ví dụ này **không trực tiếp kiểm thử migrator** vì `catalog.client.*` là key custom. Nó minh họa một loại regression test cần có khi nâng cấp application configuration: sau khi chọn property source, Binder phải tạo typed object như mong đợi.

### 15.1. Test auto-configuration mà Boot quản lý

Với một property do Spring Boot starter quản lý, regression test nên khởi tạo bean liên quan và kiểm tra rằng configuration có hiệu lực. Ví dụ nếu đổi HTTP client timeout property, một test tích hợp phải kiểm tra HTTP client được Boot tạo với timeout/chính sách đúng thay vì chỉ assert `Environment` có text value.

### 15.2. Test không có migrator

Trong khi còn dependency, ứng dụng có thể tiếp tục chạy vì runtime migration bridge. Một test pass **với migrator trên classpath** chưa chứng minh key cũ đã được thay hoàn toàn.

Sau khi sửa source, cần gỡ dependency và chạy ít nhất một test startup/functional test với đúng artifact cuối cùng. Đây là bước phát hiện phần cấu hình còn phụ thuộc vào bridge tạm.

## 16. Dùng tùy chọn fail khi migrator phát hiện vấn đề

Ở Spring Boot 4.2, tài liệu upgrading mô tả property:

~~~properties
spring.properties.migrator.fail=on-warning
~~~

Các lựa chọn được tài liệu phiên bản này nêu:

| Giá trị | Ý nghĩa |
| --- | --- |
| `never` | Không làm startup fail vì cảnh báo/lỗi migration; là mặc định được mô tả |
| `on-error` | Fail startup khi có property không còn được hỗ trợ |
| `on-warning` | Fail khi có property đã đổi tên hoặc không còn được hỗ trợ |

Diagnostics vẫn được ghi log bất kể cấu hình fail setting.

**Lưu ý phiên bản:** đây là thông tin được mô tả cho **Spring Boot 4.2**, không phải lời khẳng định `spring.properties.migrator.fail` tồn tại và có cùng behavior trong tất cả các bản 2.x, 3.x, 4.0 hoặc 4.1. Đối chiếu tài liệu của phiên bản **mà ứng dụng thật sự chạy** trước khi dùng.

### 16.1. Khi nào bật on-warning?

Đối với một migration gate trong CI hoặc staging, chế độ fail khi còn renamed/unsupported property có thể hữu ích nếu version target hỗ trợ:

~~~properties
# Ví dụ chỉ áp dụng cho phiên bản có hỗ trợ property này.
spring.properties.migrator.fail=on-warning
~~~

Khi đó, startup failure có thể trở thành tín hiệu tự động thay vì một warning dễ bị bỏ qua.

### 16.2. Không coi fail gate là trình quét mọi nguồn

Dù bật `on-warning`, migrator chỉ đánh giá được những property nó thực sự quan sát ở thời điểm xử lý. File của profile không active, source đến muộn và Helm values không được deploy vẫn có thể nằm ngoài phạm vi.

Vì vậy, fail gate là một lớp bảo vệ, không thay thế review các config sources.

### 16.3. Không mang fail setting vĩnh viễn mà quên mục đích

Sau khi xóa migrator khỏi runtime classpath, property dành riêng cho nó cũng không còn là công cụ kiểm tra migration. Nếu giữ cấu hình đó trong production sau khi gỡ module, nó có thể gây hiểu nhầm rằng hệ thống vẫn đang chặn deprecated keys.

Hãy xóa cả dependency và những cờ kiểm thử tạm sau khi đã xác nhận không cần chúng.

## 17. Maven/Gradle dependency management và artifact cuối

### 17.1. Maven dependency tree

Sau khi thêm migrator, có thể dùng trong môi trường build:

~~~bash
mvn dependency:tree
~~~

Để xem dependency hiện diện trong graph. Với Maven, có thể lọc theo artifact tùy plugin version, nhưng cú pháp filter cần phù hợp plugin.

### 17.2. Gradle runtimeClasspath

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra `spring-boot-properties-migrator` xuất hiện khi đang nâng cấp. Sau khi gỡ, chạy lại để xác nhận không còn dependency trên runtime classpath của artifact.

### 17.3. Kiểm tra JAR thực tế

Một executable JAR Spring Boot có thể đóng gói runtime dependencies bên trong. Nếu build pipeline phức tạp, cần chắc chắn artifact release cuối dùng đúng POM/Gradle configuration và không còn migrator thông qua dependency khác.

Không chỉ xóa một dòng rồi tin rằng artifact cũ trên môi trường deploy tự biến mất. Hãy rebuild artifact và xác nhận version/digest sẽ được triển khai.

### 17.4. Nhiều deployable modules

Nếu repository tạo nhiều services/JARs, mỗi service có thể có:

- Khác version target.
- Khác starters.
- Khác profiles/config sources.
- Khác release pipeline.

Không báo rằng “toàn monorepo đã migrate” chỉ vì một module đã chạy sạch diagnostics. Cần lập danh sách ứng dụng có sử dụng property do Boot quản lý để kiểm tra theo từng runtime.

## 18. CI/CD: biến migration thành công việc có bằng chứng

Một pipeline nâng cấp nên có các bước rõ ràng.

### Stage A — Build theo target version

Compile, chạy unit tests, kiểm tra dependency compatibility và đóng gói ứng dụng thử nghiệm.

### Stage B — Chạy startup diagnostics với migrator

Dùng môi trường thử nghiệm an toàn nhưng đại diện cho từng profile quan trọng. Thu thập logs đủ để thấy diagnostics. Không ghi secrets vào output.

### Stage C — Phân loại và sửa key

Lập danh sách property cũ, replacement, source, owner, test. Sửa YAML/properties, ConfigMap, Helm values, startup args và test resources.

### Stage D — Test sau khi sửa

Chạy lại với migrator. Nếu version hỗ trợ, cân nhắc dùng fail-on-warning trong migration gate. Đồng thời chạy integration tests chứng minh ứng dụng dùng behavior mong muốn.

### Stage E — Gỡ migrator

Xóa runtime dependency, rebuild, khởi động và chạy tests lại với đúng artifact cuối.

### Stage F — Deploy có giám sát

Rollout dần các instances mới, kiểm tra readiness, key metrics và lỗi chức năng. Giữ phương án rollback về bộ **image + config** đã biết hoạt động tốt.

### 18.1. Không chỉ tìm dòng “migrator” trong log

Tùy phiên bản và logging configuration, thông tin có thể xuất hiện bằng tên class/module hoặc các nhãn khác. Nếu build pipeline parse logs để enforce migration, phải kiểm soát version và test parser. Khi có fail policy chính thức ở phiên bản phù hợp, có thể dùng nó thay cho script grep mong manh.

### 18.2. Một lần khởi động thành công không bằng một bản upgrade an toàn

Service có thể khởi động nhưng một tính năng ít dùng không còn đúng semantics. Cần smoke tests và regression tests về đường nghiệp vụ, không chỉ startup health.

## 19. Cấu hình trong container, ConfigMap và Helm

Migrator chạy trong ứng dụng, còn giá trị có thể được cấp bởi deployment manifests. Đặc biệt chú ý khi key cũ được truyền qua env vars.

Ví dụ một Deployment giả định:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      containers:
        - name: app
          image: example/orders-service:upgrade-candidate
          env:
            - name: SPRING_KAFKA_RETRY_TOPIC_DELAY
              value: "2s"
~~~

Nếu target version có replacement theo `spring.kafka.retry.topic.backoff.delay`, cần cập nhật env name theo canonical property mới:

~~~yaml
env:
  - name: SPRING_KAFKA_RETRY_TOPIC_BACKOFF_DELAY
    value: "2s"
~~~

**Hai tên env ở đây là minh họa theo quy tắc relaxed binding phổ biến**; trong môi trường thực cần kiểm tra mapping của version và source đang dùng, nhất là khi tên có dấu gạch ngang, list index hoặc map key đặc biệt.

### 19.1. Sửa Helm values chưa chắc sửa manifest đang chạy

Một values file có thể được template thành env var hoặc ConfigMap file. Khi sửa, phải render/diff manifest thực tế hoặc kiểm tra resource sau deploy theo quy trình của tổ chức.

Không kết luận key đã sửa chỉ vì grep trong repo không còn tên cũ; key có thể được dựng bằng template hoặc inject từ secret/config store bên ngoài.

### 19.2. Rolling restart và cấu hình trong process

Nếu đổi ConfigMap/Secret sau khi Pod đã chạy:

- Environment variables của container hiện tại không tự được cập nhật.
- Volume mount có thể phản ánh file mới theo cơ chế eventual, nhưng `@ConfigurationProperties` đã bind không tự refresh.
- Pod mới thường cần được tạo để chắc chắn startup dùng config mới.

Đối với rollout nâng Boot, việc tạo deployment revision mới là cách rõ ràng để kết hợp **image mới** với **cấu hình đã migrate**.

### 19.3. Không dùng migrator để thay đổi bí mật

Nếu một property chứa password/token được đổi tên, phải sửa tên nguồn mà không tiết lộ giá trị. Migrator không phải secret manager. Không log raw Environment hoặc copy credentials vào báo cáo migration.

## 20. Phân biệt property Boot quản lý và property ứng dụng tự định nghĩa

Bài này tập trung vào những thuộc tính thuộc Spring Boot auto-configuration và các module mà Boot cung cấp metadata cho chúng.

Ví dụ property custom:

~~~java
@ConfigurationProperties(prefix = "example.payment")
public record PaymentProperties(
        String endpoint,
        Duration timeout
) {}
~~~

Nếu team tự đổi tên `example.payment.timeout` thành `example.payment.request-timeout`, đó là một migration **API cấu hình do team sở hữu**.

Không được mặc định rằng thêm `spring-boot-properties-migrator` sẽ tự nhận biết và chuyển mọi custom key chỉ vì class có `@ConfigurationProperties`.

### 20.1. Migration cho custom keys

Một chiến lược chuyển tiếp tự quản lý có thể gồm:

- Định nghĩa field/key mới.
- Ghi tài liệu deprecation cho key cũ.
- Trong một giai đoạn, code chấp nhận cả hai tên với precedence rõ.
- Log cảnh báo **không lộ secret** khi key cũ được sử dụng.
- Viết test cho old-only, new-only, both-present và invalid values.
- Đặt phiên bản/điểm cuối để bỏ hỗ trợ key cũ.

Đây là trách nhiệm của API config riêng hoặc thư viện sở hữu property đó, khác nhiệm vụ chính của Spring Boot properties migrator.

### 20.2. Thư viện bên thứ ba

Một starter ngoài Spring Boot có thể có property deprecation riêng hoặc tooling khác. Migrator có thể không tự xử lý tất cả, tùy metadata và cách thư viện tích hợp.

Luôn xem release notes của starter đó và runtime behavior, thay vì kỳ vọng một module Boot bao phủ mọi dependency trong classpath.

## 21. Những thay đổi cần migration guide ngoài cảnh báo property

Ví dụ Boot upgrade có thể yêu cầu:

- Chuyển package/import Java khi Spring Framework hoặc Jakarta APIs đổi.
- Đổi dependency starters hoặc cách auto-configuration được chia module.
- Thay cơ chế security filter chain.
- Điều chỉnh serialization/Jackson behavior.
- Thay đổi web server hoặc embedded Servlet API compatibility.
- Đổi cách tạo HTTP clients và timeout properties.
- Xem lại Actuator endpoints và management access policy.

Migrator chỉ tập trung vào thuộc tính cấu hình mà nó nhận biết. Nó không refactor code, sửa dependency hoặc bảo đảm behavior đúng khi các framework APIs thay đổi.

### 21.1. Không bỏ qua dữ liệu “removed without replacement”

Khi một tính năng bị bỏ hẳn, việc xóa key cũ có thể khiến startup sạch warnings nhưng ứng dụng mất khả năng trước đó. Cần xác định alternative implementation, có thể là code/config refactor, hoặc quyết định bỏ tính năng có chủ đích.

### 21.2. Đổi kiểu cần kiểm tra value

Một số key mới có thể nhận giá trị thuộc enum, Duration, DataSize hoặc danh sách. Với Boolean cũ, không copy `true` vào enum value nếu tài liệu không nói hỗ trợ. Tương tự, `500` có thể mang đơn vị khác khi key mới thay đổi semantics.

Kiểm thử nên assert **hiệu ứng** trên component, không chỉ assert raw text trong `Environment`.

## 22. Một ví dụ thứ hai: replacement có thể thay đổi ý nghĩa

Trong danh sách deprecated properties của Spring Boot hiện hành có ví dụ:

~~~text
spring.main.show-banner
    -> spring.main.banner-mode
~~~

Property cũ biểu đạt “hiển thị banner hay không” theo boolean, property mới biểu đạt “chế độ banner” theo cấu hình khác. Hai giá trị **không phải mapping string đơn giản**.

Ví dụ một lựa chọn theo API mới:

~~~properties
spring.main.banner-mode=off
~~~

Đây là ví dụ cho thấy **đừng copy value `false` từ key cũ sang key mới mà chưa kiểm tra hợp đồng mới**. Với các version/setting đã thay, phải đọc migration guide.

### 22.1. Lưu ý về thời điểm property

`spring.main.*` là nhóm property được dùng rất sớm trong SpringApplication startup. Khi thay những key thuộc bootstrap, việc dùng một nguồn cấu hình muộn như `@PropertySource` có thể không có hiệu lực như mong muốn.

Migrator không thể sửa một vấn đề về timing bằng cách chỉ map tên key.

### 22.2. Test trên hành vi hiển thị banner

Nếu migration nhằm tắt banner trong deploy, kiểm tra thực tế startup với file/CLI mới, không chỉ xem `Environment` cuối cùng chứa `spring.main.banner-mode=off`. Một property có thể đã được đọc ở giai đoạn sớm trước khi một nguồn khác được thêm.

## 23. Đừng đánh đồng cảnh báo deprecation với lỗi startup bắt buộc

Trong nhiều phiên bản, migrator có thể in diagnostics nhưng cho ứng dụng tiếp tục chạy. Điều này có chủ đích để hỗ trợ chuyển tiếp.

Tuy nhiên, một warning vẫn là việc cần giải quyết, vì:

- Một phiên bản tương lai có thể bỏ compatibility.
- Một số source không được quét.
- Runtime migration có thể ngừng hoạt động khi gỡ module.
- Tên cũ có thể gây khó hiểu cho người bảo trì.

Nếu dùng Spring Boot version có `spring.properties.migrator.fail`, có thể cấu hình gate trong CI/staging. Nếu không có tùy chọn đó ở target version, team vẫn cần kiểm tra log hoặc viết cơ chế riêng phù hợp, không dùng một property không tồn tại rồi kỳ vọng build sẽ fail.

### 23.1. Cảnh báo không đồng nghĩa mọi giá trị đều sai

Một property deprecated có thể được chuyển đúng và vẫn chạy. Nhưng mục tiêu migration là **không cần bridge và không dùng key cũ**, chứ không đơn thuần làm startup thành công.

### 23.2. Error có thể do giá trị không thể bind

Nếu property mới yêu cầu enum/kiểu khác, app có thể fail vì conversion ngay cả khi key đã đúng. Đọc stack trace và metadata, không quy mọi lỗi startup sau upgrade thành lỗi migrator.

## 24. Kiểm tra nguồn có hiệu lực mà không lộ secret

Khi diagnostics chưa đủ để xác định nơi cần sửa, có thể kiểm tra `PropertySources` cho một key **không nhạy cảm**.

Ví dụ:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
class PropertyOriginProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    PropertyOriginProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "spring.kafka.retry.topic.backoff.delay";

        System.out.println(
                "Effective value: " + environment.getProperty(key)
        );

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

Chỉ dùng snippet này trong một thử nghiệm có kiểm soát. Không dùng nó để dump toàn bộ `Environment`; credentials có thể nằm ở các nguồn config.

Một `PropertySource` có thể không cung cấp source origin chi tiết hoặc lưu key theo cách khác với relaxed binding. Việc `source.getProperty(key)` bằng null không chứng minh Binder chắc chắn không bind được giá trị tương ứng từ một tên OS environment khác. Khi nghi ngờ, kiểm tra bean đã bind và công cụ origin tracking tương ứng.

### 24.1. Actuator env/configprops

Nếu ứng dụng có Spring Boot Actuator, các endpoint như `env` hoặc `configprops` có thể giúp chẩn đoán. Phải cấu hình quyền, masking/redaction và truy cập an toàn; không công khai endpoint nhạy cảm trên Internet.

### 24.2. Ghi log tên key thay vì raw secret

Khi cần ghi nhận migration:

~~~text
Deprecated property detected: example.credential.old-name
Replacement property: example.credential.new-name
~~~

Đây là dạng thông tin được phép cân nhắc đưa vào log nếu chính sách nội bộ cho phép và không tiết lộ giá trị. Đừng log giá trị password/token chỉ để chứng minh key có mặt.

## 25. Nâng cấp nhiều lần hoặc nhảy qua nhiều phiên bản

Một project có thể từ Boot 2.x nhảy tới 4.x. Những deprecated properties có thể đã bị removed ở bước trung gian, và mapping mà migrator của version cuối còn biết không nhất thiết bao phủ tất cả lịch sử.

Chiến lược:

1. Đọc migration guides của các major/minor releases liên quan.
2. Kiểm tra deprecations của version trước khi nhảy.
3. Nếu có thể, nâng theo từng bước hợp lý và giữ regression suite chạy được.
4. Xác định những chức năng bị thay đổi behavior, không chỉ tên key.
5. Dùng migrator của mỗi target step khi phù hợp.
6. Không dựa vào “một lần chạy bản cuối không warning” để chứng minh mọi config cũ được nhận diện.

### 25.1. Lợi ích của việc kiểm tra trước khi major upgrade

Nếu đang ở Boot 3.x và chuẩn bị tới Boot 4.x, một bước chuẩn bị hợp lý là:

- Đọc danh sách deprecations của Boot 3.x.
- Sửa những key đã deprecated mà vẫn còn được hỗ trợ tại Boot 3.x.
- Chạy regression tests.
- Nâng Boot 4.x.
- Xử lý tiếp các key và behavior thay đổi theo migration guide Boot 4.x.

Điều này giảm số unknown khi sang major release.

### 25.2. Không có “rename all” an toàn cho mọi release

Một phép thay string hàng loạt có thể sửa cả comments, docs, source code không liên quan hoặc biến tên chứa substring tương tự. Với YAML, việc thay prefix còn có thể yêu cầu thay đổi cấu trúc nested object. Ưu tiên mapping được xác nhận và review diff.

## 26. Trường hợp property cũ nằm trong biến môi trường và System properties

Một đặc điểm của externalized configuration là cùng key có thể được truyền dưới nhiều hình thức.

Ví dụ key cũ:

~~~text
spring.kafka.retry.topic.delay
~~~

Có thể được cấp bằng JVM option:

~~~bash
java -Dspring.kafka.retry.topic.delay=2s -jar app.jar
~~~

Hoặc command-line argument:

~~~bash
java -jar app.jar \
  --spring.kafka.retry.topic.delay=2s
~~~

Hoặc env var theo quy tắc conversion tương ứng.

Nếu chỉ sửa `application.yml`, bạn vẫn có thể có một startup script hoặc ConfigMap đưa key cũ vào `Environment`. Migrator có thể thấy key khi source được nạp đủ sớm, nhưng mục tiêu cuối là **sửa nơi cấp**.

### 26.1. Đừng dùng System.setProperty để “sửa tạm” production

Một đoạn code:

~~~java
System.setProperty(
    "spring.kafka.retry.topic.backoff.delay", "2s");
~~~

nằm trong một bean được tạo muộn không nhất thiết có hiệu lực với auto-configuration đã chạy. Nó còn tạo side effects JVM-wide và làm khó theo dõi nguồn cấu hình.

Thay đổi key phải được thực hiện tại **nguồn externalized được Spring Boot đọc đúng thời điểm**.

### 26.2. Docker ENTRYPOINT và Kubernetes args

Kiểm tra command/args của container, Helm templates và scripts. Tên key cũ đôi khi nằm ở nơi không xuất hiện trong repository của application module.

## 27. Một ma trận migration để quản lý tiến độ

Một bảng theo dõi có thể gồm:

| ID | Old property | New property/action | Nguồn | Version | Test | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `spring.kafka.retry.topic.delay` | `spring.kafka.retry.topic.backoff.delay` | `application-staging.yml` | Theo target appendix | Retry policy test | Đang sửa |
| 2 | `spring.main.show-banner` | Xác định `banner-mode` phù hợp | CLI của service | Theo target appendix | Startup banner test | Cần kiểm tra semantics |
| 3 | Property đã removed, không replacement | Đọc migration guide và chỉnh thiết kế | Helm values | Target version | Integration test | Chưa xử lý |
| 4 | Custom `example.old-timeout` | Migration thuộc trách nhiệm ứng dụng | Shared library | Nội bộ | Unit + integration | Phân công owner |

Bảng này chỉ minh họa quản trị công việc; row 3 và 4 không đại diện cho một key Spring Boot thật.

### 27.1. Definition of Done

Một property chỉ được đánh dấu hoàn tất khi:

- Key cũ đã được loại bỏ khỏi **mọi nguồn thuộc phạm vi sở hữu**.
- Giá trị mới đúng kiểu và đúng semantics.
- Test phù hợp có bằng chứng pass.
- Startup ở profile tương ứng không cần migration tạm.
- Không còn conflict giữa key cũ và key mới.
- Người sở hữu deployment đã cập nhật manifest/script/import.
- Artifact cuối chạy không có migrator.

Nếu thiếu một điều kiện, nên giữ trong backlog migration thay vì tuyên bố toàn bộ upgrade đã hoàn tất.

## 28. Rollback: khôi phục cả artifact và cấu hình

Giả sử đã nâng service lên Boot mới và sửa các keys. Nếu rollout gặp vấn đề, nhóm có thể rollback image về phiên bản cũ. Tuy nhiên, **config mới có thể không được phiên bản cũ hiểu**, giống như config cũ có thể không được phiên bản mới hiểu.

Vì vậy cần quản lý:

~~~text
Release A = Image A + Config A
Release B = Image B + Config B
~~~

Rollback đúng đôi khi phải khôi phục cả hai thành phần cùng lúc. Nếu dùng Helm/GitOps, lưu revision và manifest snapshot đã được phê duyệt. Với secrets, quản lý phiên bản qua secret manager, không commit raw values vào Git.

### 28.1. Cửa sổ hai phiên bản cùng tồn tại

Trong rolling rollout, Pod cũ và Pod mới có thể hoạt động đồng thời. Nếu chúng dùng hai nhóm property khác nhau, config store cần có chiến lược cho cửa sổ chuyển tiếp, ví dụ separate ConfigMaps theo version hoặc một bộ values mà cả hai image đều hiểu.

Không trông chờ runtime migrator có mặt ở mọi image hay tự xử lý xung đột của hai release trên cùng môi trường.

### 28.2. Migrator không phải rollback mechanism

Khi migrator giúp một bản target chạy tạm với key cũ, đó là hỗ trợ chuyển tiếp cấu hình. Nó không tự khôi phục behavior của framework version trước, dependencies trước hoặc dữ liệu ngoài đã được migration.

## 29. Những lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Thêm migrator là project nâng cấp xong.” | Đây là bước chẩn đoán và chuyển tiếp; vẫn phải sửa source và test |
| “Migrator sửa luôn application.yml.” | Nó không tự rewrite file; có thể tạo mapping tạm ở runtime |
| “Không có warning nghĩa là toàn bộ repo sạch.” | Chỉ những nguồn được nạp/quan sát đủ sớm mới có cơ hội được phát hiện |
| “@PropertySource được quét như Config Data.” | Nguồn thêm muộn bằng @PropertySource không được tính đến |
| “Mọi deprecated key đều có replacement.” | Có thể removed hoặc không có thay thế |
| “Chỉ đổi property name, giữ nguyên value.” | Phải kiểm tra kiểu/semantics và policy mới |
| “Cứ giữ migrator ở production cho an toàn.” | Spring Boot yêu cầu gỡ sau migration |
| “Maven compile pass nghĩa là YAML đúng.” | Compile không kiểm tra mọi key runtime |
| “Chạy profile dev không warning thì prod ổn.” | Prod có sources và documents khác |
| “Key mới trong Environment là client đã dùng nó.” | Bean/client có lifecycle riêng, cần kiểm tra behavior |
| “Thêm TestPropertySource sẽ sửa environment variables.” | Test source không thay đổi OS process env |
| “Version mới sẽ nhận mọi key cũ.” | Removed compatibility có thể khiến key cũ không còn hiệu lực |
| “Gỡ migrator xong không cần test lại.” | Phải test artifact cuối không phụ thuộc bridge |
| “Fail option có trong mọi Spring Boot.” | Kiểm tra tài liệu version; tùy chọn fail đã được mô tả trong Boot 4.2 |
| “Rollback image là đủ.” | Config mới có thể không tương thích image cũ |

## 30. Quy trình gỡ migrator đúng cách

Sau khi đã sửa các nguồn cấu hình:

### Bước 1 — Xóa dependency

Maven: xóa block dependency `spring-boot-properties-migrator` khỏi `pom.xml`.

Gradle: xóa dòng `runtimeOnly(...)` khỏi build script.

### Bước 2 — Xóa cấu hình hỗ trợ tạm

Nếu đã dùng `spring.properties.migrator.fail` hoặc một script CI riêng chỉ phục vụ migration, xem xét loại bỏ theo kế hoạch. Đừng để lại một flag tưởng vẫn được Boot enforce khi module đã mất.

### Bước 3 — Rebuild artifact từ source sạch

Dùng build tool theo dự án, ví dụ:

~~~bash
mvn clean verify
~~~

Hoặc:

~~~bash
./gradlew clean test bootJar
~~~

Đây là ví dụ commands. Trong project thực, cần dùng các tasks, profiles và pipeline được team định nghĩa; không phải mọi Gradle project đều có `bootJar` task ở module đang chạy.

### Bước 4 — Xác nhận runtime classpath

Kiểm tra dependency graph và, nếu cần, executable JAR. Không chỉ kiểm tra source đã xóa dòng dependency, vì một dependency transitive bất ngờ hoặc artifact release cũ có thể còn chứa module.

### Bước 5 — Startup mà không có migrator

Khởi động đúng app với những nguồn cấu hình đã migrate. Kiểm tra bean/client behavior. Một service chỉ chạy khi có bridge migrator chưa được nâng cấp hoàn chỉnh.

### Bước 6 — Review diff và release

Một migration PR nên thể hiện rõ:

- Phiên bản Boot đã thay.
- Các key cũ và key mới.
- Các source config đã sửa.
- Test coverage và kết quả.
- Các hành vi đặc biệt cần xác nhận.
- Xác nhận gỡ migrator.
- Kế hoạch deployment và rollback.

## 31. Troubleshooting: migrator không báo hoặc báo không như mong đợi

### Tình huống A — Đã thêm dependency nhưng không thấy diagnostics

Khả năng:

- Không có key cần migrate trong nguồn đang active.
- Migrator không nằm trên runtime classpath của artifact đang chạy.
- App đang chạy một JAR/image cũ.
- Key cũ nằm trong `application-prod.yml` nhưng profile không active.
- Property source được thêm muộn bằng `@PropertySource`.
- Key thuộc starter bên thứ ba/custom không được module nhận diện như mong muốn.
- Logs bị lọc hoặc startup không tới giai đoạn cần thiết.

Hướng xử lý: xác nhận artifact/dependency, active profile, nguồn có hiệu lực và tài liệu deprecation của target version.

### Tình huống B — Đã sửa YAML nhưng warning vẫn xuất hiện

Khả năng:

- Key cũ còn ở CLI/env/config import/file externalized.
- Sửa nhầm file hoặc sai working directory.
- Source cũ ưu tiên cao hơn đang override.
- Một copy của file còn ở profile-specific location.
- Helm/ConfigMap chưa được cập nhật trong cluster.
- Pod/process chưa được tạo mới để nhận config mới.

Hướng xử lý: inventory mọi nguồn, inspect effective property sources trên môi trường an toàn, tạo lại instance khi nguồn process-level thay đổi.

### Tình huống C — App khởi động nhưng behavior vẫn sai

Khả năng:

- Value mới có semantics khác.
- Một setting đã removed và module không thể chuyển.
- Bean/client thực tế không dùng key đó.
- Có default thay đổi sau upgrade.
- Một source cao hơn đang override.
- Cấu hình đã bind nhưng resource client vẫn giữ parameter cũ.

Hướng xử lý: test behavior của component và xem migration guide, không chỉ log.

### Tình huống D — Build fail trước khi chạy migrator

Migrator chỉ hoạt động khi ứng dụng khởi động tới giai đoạn thích hợp. Nếu build lỗi do Java APIs, dependency version hoặc incompatibility classpath, cần sửa chúng trước. Module này không phải compiler refactoring tool.

### Tình huống E — Fail policy không có tác dụng

Kiểm tra phiên bản Spring Boot đang dùng có hỗ trợ `spring.properties.migrator.fail` hay chưa. Nếu không, bỏ property đó và dùng log review/test gate thích hợp, thay vì dựa vào một cờ không được phiên bản đó nhận biết.

### Tình huống F — Cùng key cũ và mới

Loại bỏ xung đột bằng cách cập nhật mọi source có hiệu lực, sau đó kiểm tra startup **không có migrator**. Không xây dựng quy tắc production dựa trên thứ tự một phép chuyển tạm của công cụ.

## 32. Bài tập thực hành

### Bài tập 1 — Đọc danh sách deprecated của version đích

Chọn một Spring Boot version mà bạn có thể thử nghiệm. Mở deprecated application properties appendix của version đó. Tìm ba loại entry: có replacement, không có replacement, có lý do thay đổi semantics. Đối chiếu với migration guide. Không tự giả định mapping của phiên bản khác.

### Bài tập 2 — Thêm migrator cho Maven

Tạo một project Spring Boot nhỏ với dependency management phù hợp. Thêm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Dùng một property deprecated thật của version target, khởi động app, quan sát diagnostics. Sau đó sửa key và kiểm tra lại.

### Bài tập 3 — Thêm migrator cho Gradle

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.boot:spring-boot-properties-migrator")
}
~~~

Build và khởi động đúng module ứng dụng. Xem runtime classpath rồi gỡ dependency sau khi đã migrate.

### Bài tập 4 — Sửa YAML nested key

Cho key cũ `spring.kafka.retry.topic.delay` và key mới `spring.kafka.retry.topic.backoff.delay` theo một target version có mapping này. Viết cấu hình YAML trước/sau, chú ý di chuyển nested value vào `backoff`. Test sau khi gỡ migrator.

### Bài tập 5 — Kiểm tra môi trường nhiều profile

Tạo `application.yml` và `application-staging.yml`; đặt key deprecated chỉ trong file staging. Chạy ứng dụng không có profile và với `--spring.profiles.active=staging`. So sánh diagnostics. Giải thích vì sao lần chạy đầu không chứng minh staging sạch.

### Bài tập 6 — Tệp được thêm bằng @PropertySource

Đặt một key deprecated trong một file chỉ được nạp bằng `@PropertySource`. Quan sát giới hạn phát hiện của migrator. Thiết kế cách kiểm tra bằng review/tìm kiếm tĩnh và quyết định có cần chuyển file sang Config Data không.

### Bài tập 7 — Precedence giữa old/new keys

Đặt key cũ trong file bên trong JAR và key mới trong external file. Thêm một CLI override. Dự đoán rủi ro conflict, sau đó thiết kế cách loại bỏ old key hoàn toàn thay vì phụ thuộc runtime migration.

### Bài tập 8 — Cảnh báo không đồng nghĩa failure

Trên một Spring Boot version có hỗ trợ fail policy, so sánh `never`, `on-error` và `on-warning` trong môi trường thử nghiệm. Ghi lại những loại key khiến startup fail. Không áp dụng cờ này cho version không hỗ trợ.

### Bài tập 9 — CI pipeline

Thiết kế pipeline: build target Boot → startup diagnostics có migrator → sửa source → regression tests → gỡ migrator → test artifact cuối → deploy canary. Xác định bằng chứng để kết thúc mỗi bước.

### Bài tập 10 — Rollback image và config

Một service dùng image cũ nhận key A, image mới nhận key B. Khi rollback image mới về cũ nhưng config vẫn là B, chuyện gì có thể xảy ra? Thiết kế một release bundle có revision của cả artifact và config.

## 33. Checklist nâng cấp cấu hình trước khi release

### Chuẩn bị

- [ ] Đã xác định chính xác Spring Boot version nguồn và đích.
- [ ] Đã đọc release notes, migration guide và deprecated properties appendix của target.
- [ ] Đã thống kê các profile và Config Data locations.
- [ ] Đã biết các nguồn outside JAR, env vars, JVM options, CLI và config imports.
- [ ] Đã phân biệt Boot-managed, third-party và custom properties.
- [ ] Đã thêm migrator tạm vào đúng runtime classpath.
- [ ] Đã có test environment không dùng production secrets.

### Phân tích và sửa

- [ ] Đã khởi động các profile quan trọng và lưu diagnostics.
- [ ] Đã phân loại rename, deprecated, removed và thay semantics.
- [ ] Đã xác nhận mapping trong tài liệu của version target.
- [ ] Đã sửa tên và value ở tất cả config sources có hiệu lực.
- [ ] Đã xử lý cấu trúc YAML nested và properties flat form.
- [ ] Đã kiểm tra những file chỉ được nạp qua `@PropertySource`.
- [ ] Đã loại bỏ xung đột key cũ và key mới.
- [ ] Không để lại key cũ trong manifests, startup arguments hoặc test resources.
- [ ] Đã test behavior của component thực, không chỉ đọc raw Environment.

### Đóng migration

- [ ] Đã chạy lại migrator với tất cả profile phù hợp.
- [ ] Đã dùng fail policy nếu version target hỗ trợ và workflow cần.
- [ ] Đã gỡ `spring-boot-properties-migrator` khỏi dependencies.
- [ ] Đã xóa migration-only flags và CI scripts không còn cần.
- [ ] Đã build artifact cuối từ source đã cập nhật.
- [ ] Đã xác nhận migrator không còn trên runtime classpath/artifact.
- [ ] Đã test startup và regression tests khi **không có migrator**.
- [ ] Đã có chiến lược rollout, readiness và rollback cả code lẫn config.
- [ ] Đã kiểm tra rằng secrets không bị in trong logs hoặc migration report.

## 34. Những ý chính cần nhớ

1. **`spring-boot-properties-migrator` là module hỗ trợ nâng cấp thuộc tính cấu hình do Spring Boot quản lý**, không phải công cụ sửa toàn bộ ứng dụng.
2. Nó có thể **phân tích `Environment`, in diagnostics lúc startup và tạm migrate một số properties ở runtime**. Không tự rewrite YAML/properties hay manifests.
3. Thêm tạm dependency `org.springframework.boot:spring-boot-properties-migrator` với `runtime` trong Maven hoặc `runtimeOnly` trong Gradle.
4. **Không phải mọi deprecated property đều có replacement**; những property đổi kiểu/semantics cần xử lý thủ công theo migration guide.
5. Một lần chạy chỉ có thể phát hiện những sources và profiles **được nạp và quan sát ở thời điểm phù hợp**.
6. Các property được đưa vào Environment quá muộn, ví dụ qua **`@PropertySource`**, không được migrator tính đến theo tài liệu Spring Boot.
7. Khi key cũ và mới cùng tồn tại, tránh phụ thuộc vào cơ chế chuyển tạm để giải quyết precedence. **Sửa mọi nguồn có hiệu lực** và kiểm tra value cuối.
8. Trên những phiên bản có hỗ trợ (ví dụ Spring Boot 4.2), `spring.properties.migrator.fail` có thể làm startup fail theo mức severity; không giả định có trên mọi phiên bản.
9. **Startup sạch warnings chưa đủ**: cần kiểm tra binding, runtime behavior, profiles, CI/CD manifests và dependency compatibility.
10. **Gỡ migrator sau khi sửa xong** rồi chạy lại tests trên artifact cuối không có bridge. Đây là bước bắt buộc để chứng minh migration độc lập.

## Tài liệu tham khảo chính thức

- [Spring Boot — Upgrading](https://docs.spring.io/spring-boot/upgrading.html): quy trình nâng cấp, `spring-boot-properties-migrator`, runtime diagnostics và giới hạn source thêm muộn.
- [Spring Boot 4.2 — Upgrading](https://docs.spring.io/spring-boot/4.2/upgrading.html): migration diagnostics và `spring.properties.migrator.fail` với các mức `never`, `on-error`, `on-warning` khi được hỗ trợ.
- [Spring Boot — Deprecated Application Properties](https://docs.spring.io/spring-boot/appendix/deprecated-application-properties/): danh sách key deprecated và replacement trong phiên bản đang hiển thị.
- [Spring Boot 4.2 — Deprecated Application Properties](https://docs.spring.io/spring-boot/4.2/appendix/deprecated-application-properties/index.html): ví dụ về `spring.kafka.retry.topic.*` đổi thành `spring.kafka.retry.topic.backoff.*`.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn config, precedence, profiles, imports và Config Data.
- [Spring Boot — Configuration Metadata Format](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html): metadata deprecation, reason và replacement.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): typed binding và validation.
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): ví dụ nâng cấp major release và lời khuyên dùng migrator.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): thay đổi version/metadata và các công việc nâng cấp lên Boot 4.
