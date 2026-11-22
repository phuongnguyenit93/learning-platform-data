# Kiểm tra deprecation trước nâng cấp

Trước khi nâng cấp Spring Kafka, Spring Boot hoặc Kafka Client, cần rà soát các API và cấu hình đã bị đánh dấu deprecated. Một API deprecated vẫn có thể chạy ở phiên bản hiện tại, nhưng nhà phát triển thư viện đã thông báo rằng ứng dụng nên chuyển sang cách dùng mới. Ở một bản phát hành sau, API đó có thể bị xóa hoặc thay đổi khiến ứng dụng không biên dịch, không khởi động hoặc xử lý message khác trước.

Kiểm tra deprecation trước nâng cấp giúp đội phát triển biết chính xác code nào cần thay, mức độ khẩn cấp ra sao và thay đổi có ảnh hưởng tới luồng messaging hay không. Với Spring Kafka, việc rà soát cần bao gồm API Java, cấu hình Spring Boot, Kafka Client, dependency bắc cầu, listener/error handler, serializer/deserializer và các công cụ vận hành.

## 1. Deprecation có ý nghĩa gì?

Một API được đánh dấu deprecated khi thư viện khuyến nghị không dùng nó cho code mới hoặc muốn người dùng chuyển sang API thay thế. Trong Java, annotation `@Deprecated` có thể cung cấp thêm thông tin:

| Thành phần | Ý nghĩa |
|---|---|
| `@Deprecated` | API đã deprecated |
| `since` | Phiên bản bắt đầu đánh dấu deprecated, nếu thư viện cung cấp |
| `forRemoval` | `true` cho biết API được dự kiến loại bỏ trong tương lai |
| Javadoc `@deprecated` | Giải thích lý do và thường chỉ ra API thay thế |

Ví dụ:

```java
/**
 * @deprecated Use the new listener configuration instead.
 */
@Deprecated(since = "2.8", forRemoval = true)
public void configureLegacyListener() {
    // Legacy behavior
}
```

`forRemoval = true` là tín hiệu cần ưu tiên xử lý vì API có thể bị xóa trong một bản phát hành tương lai. Tuy nhiên, `false` không có nghĩa API sẽ tồn tại mãi mãi; hãy đọc release notes và migration guide của thư viện.

Deprecation không đồng nghĩa API đã bị xóa hoặc lập tức không an toàn. Nó là cảnh báo về hướng phát triển. Ứng dụng vẫn có thể chạy bình thường hôm nay nhưng sẽ tích lũy công việc migration cho lần nâng cấp sau.

## 2. Phân biệt deprecated, removed và breaking change

Ba khái niệm này liên quan nhưng không giống nhau:

| Trạng thái | Điều xảy ra | Hành động |
|---|---|---|
| Deprecated | API vẫn còn nhưng không khuyến nghị dùng | Lập kế hoạch thay thế |
| Removed | API không còn trong phiên bản đích | Phải sửa code/config trước khi nâng cấp thành công |
| Breaking change | Hành vi hoặc contract thay đổi, có thể không liên quan deprecation | Đọc migration guide và kiểm thử hành vi |

Không phải mọi breaking change đều có giai đoạn deprecated. Một thay đổi có thể xuất hiện trong major release mà không có API cũ được đánh dấu trước đó. Ngược lại, một API deprecated có thể tiếp tục tồn tại qua nhiều phiên bản.

Vì vậy, chỉ tìm annotation `@Deprecated` là chưa đủ. Cần đọc release notes, migration guide, compatibility matrix và thay đổi hành vi của từng thành phần.

## 3. Phạm vi cần rà soát trong ứng dụng Spring Kafka

Trước khi nâng cấp, lập danh sách các lớp và cấu hình mà ứng dụng đang sử dụng:

| Phạm vi | Ví dụ cần kiểm tra |
|---|---|
| Spring Kafka API | `KafkaTemplate`, listener container, `@KafkaListener`, error handler, recoverer |
| Kafka Client API | `Producer`, `Consumer`, `Admin`, cấu hình producer/consumer |
| Spring Boot | Auto-configuration, property trong `application.yml`, dependency starter |
| Serialization | JSON, Avro, Protobuf, Schema Registry serializer/deserializer |
| Retry và DLT | `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, `@RetryableTopic` |
| Transaction | Kafka transaction manager, producer factory, listener transaction |
| Observability | Micrometer Observation, metrics, tracing và logging |
| Build và runtime | Java version, Maven/Gradle plugin, dependency bắc cầu và connector |

Hãy rà soát cả source code, test, cấu hình YAML/properties, file deployment, script CLI và cấu hình connector. Compiler chỉ phát hiện được một phần vấn đề; tên property trong YAML hoặc cấu hình được tạo từ environment variable có thể không tạo compiler warning.

## 4. Xác định phiên bản hiện tại và phiên bản đích

Deprecation chỉ có ý nghĩa khi biết API được đánh dấu từ phiên bản nào và ứng dụng định nâng cấp tới đâu. Ghi lại ít nhất:

- Java runtime và Java compiler release.
- Spring Boot version.
- Spring Framework version được Boot quản lý.
- Spring Kafka version.
- Kafka Client version (kafka-clients).
- Kafka broker version và phiên bản connector/Schema Registry nếu có.

Nếu ứng dụng dùng Spring Boot dependency management, ưu tiên để Boot BOM quản lý các dependency Spring và Kafka tương thích. Không override riêng spring-kafka hoặc kafka-clients chỉ để lấy một API mới khi chưa kiểm tra compatibility matrix.

Có thể xem dependency tree bằng Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.kafka:spring-kafka,org.apache.kafka:kafka-clients,org.springframework.boot:spring-boot
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Ghi rõ dependency nào là direct dependency và dependency nào được kéo vào transitively. Một thư viện khác có thể mang Kafka Client version khác với version mà ứng dụng dự định dùng.

## 5. Bật compiler warning để tìm call site deprecated

Java compiler có thể cảnh báo khi code gọi API deprecated. Bật chi tiết warning giúp tìm file và dòng code cần sửa.

Với Maven Compiler Plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <showWarnings>true</showWarnings>
        <compilerArgs>
            <arg>-Xlint:deprecation</arg>
            <arg>-Xlint:removal</arg>
        </compilerArgs>
    </configuration>
</plugin>
```

Với Gradle Groovy DSL:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Xlint:deprecation', '-Xlint:removal']
}
```

Với Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(listOf("-Xlint:deprecation", "-Xlint:removal"))
}
```

Sau khi bật warning, chạy compile trên source set chính và test. Đọc toàn bộ output thay vì chỉ đếm số warning; mỗi cảnh báo cần được gắn với dependency và phiên bản đích.

`-Xlint:deprecation` giúp hiển thị vị trí sử dụng API deprecated. `-Xlint:removal` tập trung vào API được đánh dấu để loại bỏ. Các tùy chọn này phụ thuộc JDK; hãy dùng JDK phù hợp với baseline mà ứng dụng hỗ trợ.

Không bật `-Werror` ngay trong lần rà soát đầu tiên nếu dự án đang có warning từ generated source hoặc dependency chưa thể xử lý. Sau khi dọn sạch warning có chủ đích, có thể cân nhắc biến warning mới thành lỗi trong CI để tránh nợ deprecation quay lại.

## 6. Tìm annotation trong source code

Tìm `@Deprecated` và Javadoc `@deprecated` giúp lập inventory những API do chính dự án khai báo:

```bash
rg -n --glob "*.java" "@Deprecated|@deprecated" src
```

Lệnh này tìm nơi khai báo API deprecated trong source. Nó không tìm đầy đủ mọi nơi đang gọi API deprecated từ thư viện bên ngoài. Để phát hiện call site, cần compiler warning, IDE inspection hoặc công cụ phân tích phù hợp.

Trong IDE, bật inspection cho deprecated API và dùng Find Usages trên symbol được đánh dấu. Kiểm tra cả:

- Code production và test.
- Cấu hình Java được tạo bằng reflection.
- Annotation hoặc class name được khai báo dưới dạng string.
- Generated source và code được sinh từ template.
- Module chưa được build trong pipeline chính.

Reflection, method handle hoặc tên class/property dạng chuỗi có thể không được compiler phát hiện. Những trường hợp này cần rà soát thủ công và kiểm thử khởi động.

## 7. Đọc Javadoc và tìm API thay thế

Khi gặp warning, mở Javadoc của đúng phiên bản dependency đang compile. Tìm:

1. Lý do API bị deprecated.
2. Phiên bản bắt đầu deprecated (since).
3. Có đánh dấu forRemoval hay không.
4. API thay thế được khuyến nghị.
5. Khác biệt về semantics, default value, thread-safety hoặc lifecycle.
6. Link migration guide hoặc issue giải thích thay đổi.

Không thay tên method một cách máy móc. API mới có thể thay đổi retry semantics, offset commit, transaction boundary, exception classification hoặc cách listener container quản lý thread.

Ví dụ lịch sử trong Spring Kafka: `SeekToCurrentErrorHandler` đã được deprecated để chuyển sang `DefaultErrorHandler`. Khi migration, cần đối chiếu cách cấu hình `BackOff`, recoverer, exception classification và hành vi seek/commit với phiên bản đích. Không chỉ đổi class name rồi cho rằng hành vi retry và DLT không đổi.

## 8. Đọc release notes và migration guide theo từng phiên bản

Với mỗi dependency quan trọng, đọc release notes của tất cả major/minor version nằm giữa phiên bản hiện tại và phiên bản đích. Đặc biệt tìm các mục:

- Deprecated APIs và APIs removed.
- Configuration property renamed, deprecated hoặc removed.
- Thay đổi default value.
- Thay đổi Java/Spring baseline.
- Kafka protocol hoặc broker compatibility.
- Thay đổi retry, error handling, transaction và offset behavior.
- Thay đổi serializer, header, metrics và tracing.

Không chỉ đọc ghi chú của phiên bản đích. Nếu nâng từ một phiên bản cũ qua nhiều major release, một thay đổi trung gian có thể yêu cầu migration trước khi tới đích.

Nguồn chính thức nên dùng:

- Spring Kafka change history: https://docs.spring.io/spring-kafka/reference/appendix/change-history.html
- Spring Kafka reference: https://docs.spring.io/spring-kafka/reference/
- Spring Boot release notes và migration guide: https://github.com/spring-projects/spring-boot/wiki
- Apache Kafka upgrade guide: https://kafka.apache.org/documentation/#upgrade
- JDK jdeprscan documentation: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html

Luôn mở tài liệu tương ứng với version đang dùng hoặc version đích. Trang `current` có thể mô tả API mới hơn baseline của dự án.

## 9. Kiểm tra deprecation trong cấu hình Spring Boot

Deprecation không chỉ xuất hiện trong Java code. Spring Boot có thể đánh dấu configuration property cũ và cung cấp property thay thế. Các property này thường nằm trong application.yml, application.properties, Helm values, environment variable hoặc secret/config map.

Tìm các property liên quan tới Kafka:

```bash
rg -n "spring[.]kafka|kafka[.]" src/main/resources deploy charts
```

Sau đó đối chiếu từng key với configuration metadata và release notes của Spring Boot đích. Kiểm tra:

- Property đã đổi tên hay chuyển namespace chưa.
- Kiểu dữ liệu, đơn vị thời gian và default value có thay đổi không.
- Property cũ còn được bind hay bị bỏ qua.
- Environment variable có còn ánh xạ đúng key mới không.
- Helm/Kubernetes manifest có đang ghi đè giá trị trong ứng dụng không.

Trong quá trình nâng cấp Spring Boot, có thể dùng dependency `spring-boot-properties-migrator` tạm thời để phát hiện và hỗ trợ migration một số property đã đổi tên. Thêm migrator đúng version Spring Boot đang dùng, chạy ứng dụng trong môi trường kiểm thử, đọc cảnh báo lúc startup rồi sửa cấu hình thật. Gỡ dependency migrator sau khi hoàn tất migration; không giữ nó như một phần runtime vĩnh viễn.

Ví dụ Maven dependency tạm thời:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
```

Property migrator không thay thế việc đọc release notes và không bảo đảm phát hiện mọi key tự định nghĩa, property của thư viện ngoài hoặc cấu hình được tạo động.

## 10. Dùng jdeprscan đúng phạm vi

JDK cung cấp công cụ `jdeprscan` để tìm việc sử dụng các API Java SE đã deprecated trong bytecode. Ví dụ:

```bash
jdeprscan --release 21 --for-removal target/classes
```

Có thể quét JAR đã build:

```bash
jdeprscan --release 21 --for-removal target/application.jar
```

`jdeprscan` hữu ích khi nâng JDK vì nó tìm các API Java SE deprecated, đặc biệt API được đánh dấu for removal. Nó không phải công cụ quét deprecation cho Spring Kafka, Spring Boot hoặc Kafka Client. Với các thư viện đó, hãy dùng compiler warnings, Javadoc, IDE và release notes của từng thư viện.

Đừng nhầm `jdeprscan` với `jdeps`. `jdeps` phân tích dependency và module/package dependency; nó không thay thế công việc rà soát API deprecated.

## 11. Phân tích thay đổi API của dependency

Khi nâng version một thư viện, có thể dùng công cụ so sánh API như Revapi hoặc japicmp để phát hiện thay đổi public API giữa hai artifact. Chúng hữu ích cho việc kiểm tra tương thích binary/source của thư viện, nhưng không tự chứng minh mọi call site trong ứng dụng đều an toàn.

Quy trình phù hợp:

1. So sánh artifact cũ và mới để tìm API bị xóa, đổi signature hoặc đổi visibility.
2. Đọc Javadoc/release notes để hiểu deprecation và replacement.
3. Compile ứng dụng với dependency version đích để phát hiện call site không còn hợp lệ.
4. Chạy integration test để phát hiện thay đổi behavior không thể hiện qua signature.

Với thư viện nội bộ do tổ chức phát triển, có thể đưa Revapi/japicmp vào CI để kiểm soát public API của chính thư viện đó. Với dependency bên ngoài, xem báo cáo như một nguồn tín hiệu bổ sung.

## 12. Phân loại mức độ ưu tiên

Không phải mọi warning cần sửa cùng lúc. Lập bảng inventory với mức độ ưu tiên:

| Mức | Điều kiện | Hành động |
|---|---|---|
| P0 - Blocker | API/property đã bị xóa trong version đích hoặc code không compile | Phải xử lý trước khi nâng cấp |
| P1 - High | forRemoval=true, API thay thế đã rõ hoặc behavior có rủi ro cao | Ưu tiên migration trong cùng đợt |
| P2 - Medium | Deprecated nhưng chưa có removal timeline rõ | Tạo ticket và kế hoạch thay thế |
| P3 - Low | Warning trong test/generated code hoặc API ít ảnh hưởng | Ghi nhận owner, xử lý theo kế hoạch |

Inventory nên có các cột:

| Field | Nội dung |
|---|---|
| Symbol/property | Tên API hoặc configuration key |
| Module/file | Nơi sử dụng |
| Dependency/version | Thư viện và phiên bản cung cấp API |
| Deprecated since | Phiên bản đánh dấu |
| For removal | Có hoặc không |
| Replacement | API/property thay thế |
| Behavior difference | Khác biệt cần kiểm thử |
| Owner/status | Người phụ trách và tiến độ |

Đừng bỏ qua warning vì nó xuất hiện trong test. Test thường là nơi chứa cách cấu hình cũ và có thể tiếp tục kéo API deprecated vào build.

## 13. Ví dụ migration error handler trong Spring Kafka

Giả sử ứng dụng cũ dùng `SeekToCurrentErrorHandler` và cần chuyển sang `DefaultErrorHandler`. Migration cần rà soát cả retry, backoff và dead-letter recoverer.

Ví dụ cấu hình theo hướng API mới:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler() {
        // Ví dụ: retry 2 lần, mỗi lần cách nhau 1 giây, sau đó recover.
        return new DefaultErrorHandler(
                (record, exception) -> {
                    // Publish to DLT or record recovery outcome.
                },
                new FixedBackOff(1_000L, 2L)
        );
    }
}
```

Đây là ví dụ minh họa cách khai báo error handler mới; recoverer thực tế cần được cấu hình để publish record sang DLT và xác nhận send thành công. Số lần retry, exception classification, batch listener behavior và offset commit phải được quyết định theo nghiệp vụ.

Khi thay error handler, kiểm thử:

- Exception retryable và non-retryable.
- Số lần delivery attempt và khoảng backoff.
- Record được recover có giữ original topic/partition/offset headers không.
- DLT publish thất bại thì offset nguồn được xử lý thế nào.
- Batch listener và record listener có hành vi phù hợp không.
- Transactional listener có rollback/recovery đúng không.

## 14. Không che warning bằng SuppressWarnings tùy tiện

`@SuppressWarnings("deprecation")` có thể cần thiết trong adapter tương thích hoặc code đang chờ migration, nhưng không nên dùng ở cấp package/class lớn để làm sạch log.

Nếu buộc phải giữ API deprecated:

1. Giới hạn suppression ở method hoặc statement nhỏ nhất.
2. Ghi lý do kỹ thuật và version dự kiến thay thế.
3. Tạo issue có owner và thời hạn.
4. Kiểm tra API chưa bị xóa trong version đích.
5. Bổ sung test bảo vệ behavior hiện tại.

Không suppress warning removal mà không có đánh giá rõ ràng. API đã được đánh dấu loại bỏ có thể biến thành compile error ngay khi dependency được nâng.

## 15. Nâng cấp theo từng lớp dependency

Spring Kafka chạy cùng Spring Framework, Spring Boot và Kafka Client. Nâng nhiều thành phần độc lập cùng lúc làm khó xác định nguyên nhân khi build hoặc runtime thất bại.

Một trình tự kiểm soát thường dùng:

1. Chọn Spring Boot version đích và kiểm tra Java baseline.
2. Dùng dependency management tương ứng để xác định Spring Framework, Spring Kafka và Kafka Client được hỗ trợ.
3. Đọc migration guide/release notes của từng major/minor release cần đi qua.
4. Xử lý API deprecated/removed và property cũ trong source/config.
5. Nâng dependency trong một nhánh riêng, compile và chạy test.
6. Kiểm thử integration với broker version mục tiêu và các serializer/connector đang dùng.
7. Triển khai staging, quan sát warning/log/metrics trước khi production.

Không ép Kafka Client version mới hơn mức Spring Kafka hoặc Spring Boot đang hỗ trợ nếu chưa xác minh tương thích. Broker có thể hỗ trợ nhiều client version, nhưng ứng dụng vẫn cần dependency set tương thích ở phía Java.

## 16. Kiểm thử sau khi thay API deprecated

Compile thành công chỉ chứng minh code phù hợp với signature mới. Với ứng dụng messaging, phải kiểm tra cả behavior:

| Khu vực | Kịch bản cần kiểm thử |
|---|---|
| Producer | Serialize, send success/failure, callback/future và retry |
| Consumer | Deserialize, listener invocation, concurrency và shutdown |
| Offset | AckMode, commit timing, redelivery sau lỗi |
| Error handler | Retry count, backoff, fatal exception và recoverer |
| DLT | Destination, headers, send failure và replay |
| Transaction | Commit/rollback và consume-transform-produce nếu có |
| Schema | Schema Registry, schema evolution và dữ liệu cũ |
| Configuration | Property binding, default value và environment override |
| Observability | Metrics, tracing, log correlation và alert |

Integration test nên dùng Kafka broker thực tế hoặc Testcontainers phù hợp với version mục tiêu. Nếu có Schema Registry, kiểm thử cả producer/consumer serializer thay vì chỉ mock KafkaTemplate.

## 17. Tạo báo cáo deprecation trước và sau nâng cấp

Lưu báo cáo vào ticket hoặc pull request để reviewer biết warning nào đã được xử lý:

| API/property | Trạng thái trước | Thay đổi | Trạng thái sau |
|---|---|---|---|
| Legacy error handler | Deprecated | Chuyển sang `DefaultErrorHandler` | Đã kiểm thử retry/DLT |
| Kafka property cũ | Deprecated/renamed | Dùng property mới | Startup binding PASS |
| JDK API for removal | Warning | Dùng API Java SE mới | `jdeprscan` sạch |
| API trong test | Deprecated | Cập nhật test fixture | Test compile PASS |

Sau khi nâng cấp:

- Chạy lại compiler warning với `-Xlint:deprecation` và `-Xlint:removal`.
- Quét JDK API bằng `jdeprscan` nếu nâng JDK.
- Xem startup log để phát hiện property deprecated hoặc unknown.
- So sánh dependency tree với bộ version đã duyệt.
- Ghi nhận warning còn lại, lý do và owner.

Mục tiêu không nhất thiết là zero warning ngay lập tức nếu có dependency ngoài chưa thể sửa, nhưng mọi warning phải được nhìn thấy, phân loại và có người chịu trách nhiệm.

## 18. Những nhầm lẫn thường gặp

1. **Cho rằng deprecated đồng nghĩa đã bị xóa.** Deprecated là cảnh báo; API có thể vẫn hoạt động ở version hiện tại.
2. **Chỉ tìm `@Deprecated` trong source.** Compiler warning mới tìm được nhiều call site trong dependency; cấu hình dạng chuỗi cần rà soát riêng.
3. **Bỏ qua `forRemoval=true`.** Đây là tín hiệu cần ưu tiên vì API có thể bị loại bỏ.
4. **Chỉ đọc release notes của version đích.** Migration qua nhiều major release có thể có bước trung gian bắt buộc.
5. **Đổi class/method nhưng không kiểm thử behavior.** Retry, offset, DLT hoặc transaction semantics có thể khác.
6. **Dùng `jdeprscan` để tìm deprecation của Spring Kafka.** Công cụ này tập trung vào Java SE APIs.
7. **Nhầm `jdeps` với deprecation scanner.** `jdeps` phân tích dependency/module, không thay thế compiler warnings.
8. **Override Kafka Client riêng lẻ.** Có thể tạo dependency set không được Spring Kafka/Spring Boot hỗ trợ.
9. **Suppress toàn bộ warning.** Làm mất tín hiệu về API sắp bị loại bỏ.
10. **Quên YAML, environment variable và deployment config.** Ứng dụng có thể compile nhưng bind property sai lúc startup.

Kiểm tra deprecation trước nâng cấp là bước quản lý rủi ro cho vòng đời ứng dụng Spring Kafka. Hãy kết hợp compiler warnings, IDE, Javadoc, release notes, migration guide, kiểm tra configuration và test trên đúng version đích. Khi mỗi API deprecated có replacement, owner và test tương ứng, việc nâng cấp sẽ dự đoán được hơn và giảm nguy cơ lỗi ẩn trong producer, consumer, retry, offset hoặc DLT.
