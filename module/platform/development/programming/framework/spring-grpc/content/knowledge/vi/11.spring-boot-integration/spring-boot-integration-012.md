# Kiểm tra điều kiện auto-configuration trong Spring Boot gRPC

## 1. Vì sao cần kiểm tra auto-configuration?

Trong **SPRING_GRPC**, Spring Boot starter có thể tự đăng ký các bean phục vụ gRPC server hoặc client dựa trên dependency, cấu hình và những bean đã tồn tại trong `ApplicationContext`. Cơ chế này giúp ứng dụng không phải tự dựng mọi thành phần, nhưng cũng khiến một số lỗi khó thấy: starter có trong build nhưng cấu hình không chạy, client bean không xuất hiện, hoặc một cấu hình mặc định bị bỏ qua vì ứng dụng đã khai báo bean thay thế.

**Kiểm tra điều kiện auto-configuration** là xác định vì sao một cấu hình tự động được áp dụng hoặc bị bỏ qua, rồi đối chiếu kết quả với classpath, properties và bean thực tế.

Bài tập trung vào:

- Các nhóm điều kiện Spring Boot thường dùng: classpath, property, bean và resource.
- Cách starter gRPC được phát hiện và áp dụng các điều kiện.
- Cơ chế back-off khi ứng dụng tự cung cấp bean.
- Đọc Condition Evaluation Report và Actuator conditions endpoint.
- Viết test xác nhận điều kiện bằng `ApplicationContextRunner`.
- Phân biệt lỗi auto-configuration với lỗi service registration, channel hoặc kết nối mạng.

Ví dụ gRPC dùng các starter thuộc hệ **net.devh** để minh họa. Spring gRPC chính thức có cách đăng ký auto-configuration và cấu hình riêng theo phiên bản. Các property ví dụ tự định nghĩa trong bài không phải property mặc định của mọi gRPC starter.

## 2. Auto-configuration được quyết định bởi những điều kiện nào?

Một auto-configuration class thường được áp dụng khi nhiều điều kiện cùng thỏa mãn. Những điều kiện phổ biến:

| Điều kiện | Annotation | Câu hỏi cần trả lời |
| --- | --- | --- |
| Classpath | `@ConditionalOnClass` | Class/thư viện cần thiết có trên runtime classpath không? |
| Property | `@ConditionalOnProperty` | Property có tồn tại và có giá trị phù hợp không? |
| Bean đã tồn tại | `@ConditionalOnBean` | Context đã có bean phụ thuộc cần thiết chưa? |
| Bean chưa tồn tại | `@ConditionalOnMissingBean` | Ứng dụng đã tự khai báo bean thay thế chưa? |
| Resource | `@ConditionalOnResource` | File/resource được yêu cầu có tồn tại không? |
| Web application type | `@ConditionalOnWebApplication` | Ứng dụng có đúng loại web context không? |
| Profile | `@Profile` | Profile tương ứng có đang hoạt động không? |

Các điều kiện có thể kết hợp trên class hoặc từng `@Bean` method. Nếu một điều kiện không thỏa, phần cấu hình tương ứng sẽ không được áp dụng.

### 2.1. Điều kiện classpath

`@ConditionalOnClass` kiểm tra class có thể được nạp từ classpath hay không. Đây là cách starter tránh tạo cấu hình phụ thuộc vào thư viện chưa được cài.

Ví dụ, một cấu hình client gRPC có thể yêu cầu `io.grpc.ManagedChannel`. Nếu runtime chỉ có gRPC server artifact nhưng thiếu thư viện client cần thiết, một phần auto-configuration client có thể không được kích hoạt.

Cần kiểm tra **runtime classpath**, không chỉ nhìn danh sách dependency khai báo. Dependency có thể bị exclude, đánh dấu sai scope hoặc bị xung đột version khi resolve.

### 2.2. Điều kiện property

`@ConditionalOnProperty` kiểm tra property trong Spring `Environment`. Ví dụ, cấu hình tùy chọn chỉ hoạt động khi property `app.grpc.metrics.enabled=true`.

Điều kiện này thường được dùng để bật/tắt tính năng theo profile hoặc môi trường. Chú ý:

- `havingValue` xác định giá trị cần khớp.
- `matchIfMissing` quyết định hành vi khi property không tồn tại.
- Property có thể đến từ YAML, environment variable, command line hoặc test override.
- Tên property sai hoặc giá trị bị nguồn ưu tiên cao hơn ghi đè có thể làm điều kiện không khớp.

Không suy luận rằng property tồn tại chỉ vì đã viết nó trong một file YAML; cần kiểm tra file/profile đó thực sự được nạp.

### 2.3. Điều kiện bean và cơ chế back-off

`@ConditionalOnBean` chỉ áp dụng cấu hình khi một bean phù hợp đã được đăng ký. `@ConditionalOnMissingBean` thường dùng để tạo bean mặc định nếu ứng dụng chưa cung cấp bean tương ứng.

Ví dụ: starter có thể cung cấp một channel factory mặc định; nếu ứng dụng đăng ký một factory tùy chỉnh đúng kiểu, cấu hình mặc định có thể back-off. Đây là hành vi mở rộng có chủ đích, không nhất thiết là lỗi.

Cần phân biệt:

- Bean không có vì điều kiện không thỏa.
- Bean không có vì auto-configuration không được phát hiện.
- Bean mặc định không có vì đã có bean thay thế.
- Context thất bại vì có nhiều bean cùng kiểu hoặc dependency bắt buộc bị thiếu.

### 2.4. Điều kiện resource và web context

Một cấu hình có thể yêu cầu file resource như trust store hoặc một loại application context cụ thể. Nếu resource không tồn tại hoặc context không đúng loại, cấu hình tương ứng có thể bị bỏ qua.

Tuy nhiên, với TLS, không phải mọi starter đều kiểm tra sự tồn tại của file bằng cùng một conditional annotation; có thư viện chỉ đọc resource khi tạo server/channel. Vì vậy, lỗi certificate path có thể xuất hiện lúc bean được tạo hoặc lúc transport khởi động, dù condition report không có mục `@ConditionalOnResource` tương ứng.

## 3. Auto-configuration của gRPC starter được phát hiện ra sao?

Trong Spring Boot hiện đại, auto-configuration class thường được khai báo bằng `@AutoConfiguration` và được đăng ký qua resource:

`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Mỗi dòng trong file là tên đầy đủ của một auto-configuration class. Spring Boot đọc danh sách này rồi đánh giá các condition trên class và các bean method.

Một starter có thể chứa nhiều nhóm cấu hình, ví dụ:

- Cấu hình dùng chung cho gRPC Java.
- Cấu hình server khi server artifact có trên classpath.
- Cấu hình client khi client artifact có trên classpath.
- Cấu hình TLS, interceptor hoặc health integration nếu dependency/property tương ứng có mặt.

Đây là cách phân chia thường gặp, không phải cam kết tên class cụ thể của mọi starter. Với Spring Boot 2.7 trở lên, cơ chế `AutoConfiguration.imports` được dùng cho auto-configuration mới; các dự án cũ có thể còn sử dụng cơ chế đăng ký legacy như `spring.factories`.

### Thứ tự cấu hình cũng quan trọng

Auto-configuration có thể khai báo quan hệ trước/sau để các bean điều kiện được đăng ký đúng lúc. `@AutoConfiguration(after = ...)` hoặc `before = ...` giúp sắp xếp cấu hình; nó không tự bảo đảm một bean phụ thuộc sẽ tồn tại.

`@ConditionalOnMissingBean` đặc biệt nhạy với thứ tự: điều kiện được đánh giá dựa trên bean definitions đã biết tại thời điểm xử lý. Vì vậy, khi viết auto-configuration tùy chỉnh, dùng ordering contract của Spring Boot và tránh dựa vào thứ tự scan ngẫu nhiên.

## 4. Ví dụ một auto-configuration tùy chọn

Giả sử ứng dụng có tính năng ghi nhận metrics cho các cuộc gọi gRPC client. Tính năng này chỉ nên được đăng ký khi:

1. gRPC Java client API có trên classpath.
2. Ứng dụng bật property `app.grpc.observability.enabled=true`.
3. Ứng dụng chưa cung cấp implementation metrics riêng.

Ví dụ cấu hình tùy chỉnh:

```java
@AutoConfiguration
@ConditionalOnClass(name = "io.grpc.ManagedChannel")
@ConditionalOnProperty(
    prefix = "app.grpc.observability",
    name = "enabled",
    havingValue = "true"
)
public class GrpcClientObservabilityAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GrpcClientMetrics.class)
    GrpcClientMetrics grpcClientMetrics() {
        return new GrpcClientMetrics();
    }
}
```

`GrpcClientMetrics` là kiểu do ứng dụng định nghĩa trong ví dụ. Cấu hình này minh họa cơ chế condition; nó chưa tự instrument RPC. Muốn thu metrics thực tế, cần kết nối bean với interceptor hoặc instrumentation phù hợp.

Đăng ký class trong file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
dev.example.grpc.GrpcClientObservabilityAutoConfiguration
```

Và bật tính năng:

```yaml
app:
  grpc:
    observability:
      enabled: true
```

Ba tình huống:

| Classpath | Property | Bean tùy chỉnh đã có | Kết quả |
| --- | --- | --- | --- |
| Có `ManagedChannel` | `true` | Không | Auto-configuration tạo bean mặc định |
| Có `ManagedChannel` | Không bật/`false` | Không | Condition property không khớp, không tạo bean |
| Có `ManagedChannel` | `true` | Có | `@ConditionalOnMissingBean` back-off, dùng bean của ứng dụng |
| Thiếu `ManagedChannel` | `true` | Không | Condition classpath không khớp |

Nếu class auto-configuration không được đăng ký trong imports file, các condition bên trong không được đánh giá như một auto-configuration được phát hiện. Khi đó, bật property cũng không làm bean xuất hiện.

## 5. Đọc Condition Evaluation Report

Cách nhanh để xem vì sao cấu hình được áp dụng hoặc bỏ qua là bật debug report của Spring Boot:

```bash
java -jar app.jar --debug
```

Hoặc khi chạy ứng dụng từ IDE, thêm program argument `--debug`. Spring Boot sẽ in **Condition Evaluation Report**, thường gồm:

- **Positive matches:** cấu hình có các condition cần thiết được thỏa mãn.
- **Negative matches:** cấu hình bị loại và lý do condition không khớp.
- **Exclusions:** auto-configuration bị loại trừ rõ ràng.
- **Unconditional classes:** cấu hình không cần điều kiện thông thường.

Khi kiểm tra gRPC starter, tìm các auto-configuration liên quan đến server/client trong report. Nếu class xuất hiện ở negative matches, đọc phần lý do cụ thể thay vì chỉ nhìn kết luận “did not match”.

### Quy trình đọc report

1. Xác định auto-configuration class của server hoặc client.
2. Kiểm tra condition classpath: gRPC API cần thiết có được tìm thấy không?
3. Kiểm tra property condition: prefix, tên property và giá trị thực tế.
4. Kiểm tra bean condition: bean phụ thuộc đã được tạo chưa, có bean do ứng dụng thay thế không?
5. Kiểm tra exclusions và thứ tự cấu hình.
6. Đối chiếu kết quả với danh sách bean trong `ApplicationContext`.

`--debug` không tự sửa cấu hình. Nó chỉ cung cấp bằng chứng để tìm condition đầu tiên không thỏa hoặc cấu hình đã back-off.

## 6. Dùng Actuator conditions endpoint

Nếu ứng dụng có Spring Boot Actuator, endpoint `conditions` có thể trình bày kết quả đánh giá auto-configuration qua HTTP.

Ví dụ expose endpoint trong môi trường quản trị:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

Sau khi ứng dụng khởi động, endpoint thường có đường dẫn:

`/actuator/conditions`

Endpoint này hữu ích khi cần kiểm tra một ứng dụng đang chạy mà không đọc toàn bộ startup log. Cần bảo vệ endpoint bằng authentication, network policy và chỉ expose trên management interface phù hợp; thông tin điều kiện có thể tiết lộ cấu trúc thư viện và cấu hình nội bộ.

Actuator conditions cho biết kết quả condition evaluation. Nó không chứng minh remote gRPC server đang khỏe, channel đã kết nối hoặc RPC có thể hoàn tất. Những việc đó cần health check hoặc lời gọi RPC kiểm thử riêng.

## 7. Kiểm thử condition bằng ApplicationContextRunner

Không nên chỉ kiểm tra auto-configuration bằng cách khởi động toàn bộ ứng dụng. `ApplicationContextRunner` cho phép dựng một context nhỏ, áp dụng auto-configuration cụ thể, đặt properties và kiểm tra bean.

Ví dụ test cho cấu hình ở mục 4:

```java
class GrpcClientObservabilityAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    GrpcClientObservabilityAutoConfiguration.class
                )
            );

    @Test
    void createsMetricsBeanWhenEnabled() {
        contextRunner
            .withPropertyValues(
                "app.grpc.observability.enabled=true"
            )
            .run(context ->
                assertThat(context)
                    .hasSingleBean(GrpcClientMetrics.class)
            );
    }

    @Test
    void doesNotCreateMetricsBeanWhenDisabled() {
        contextRunner
            .withPropertyValues(
                "app.grpc.observability.enabled=false"
            )
            .run(context ->
                assertThat(context)
                    .doesNotHaveBean(GrpcClientMetrics.class)
            );
    }

    @Test
    void backsOffWhenApplicationProvidesBean() {
        contextRunner
            .withPropertyValues(
                "app.grpc.observability.enabled=true"
            )
            .withBean(
                GrpcClientMetrics.class,
                GrpcClientMetrics::new
            )
            .run(context ->
                assertThat(context)
                    .hasSingleBean(GrpcClientMetrics.class)
            );
    }
}
```

Test cần các dependency test phù hợp của Spring Boot (`spring-boot-test`, JUnit 5 và AssertJ; thường được cung cấp qua `spring-boot-starter-test`). Ví dụ kiểm tra ba hành vi: property bật, property tắt và back-off khi ứng dụng cung cấp bean riêng.

Để kiểm tra condition classpath, có thể dùng `FilteredClassLoader` trong `ApplicationContextRunner` để mô phỏng thiếu class cần thiết, rồi assert bean không được tạo. Cách này hữu ích hơn việc gỡ dependency thật khỏi build chỉ để kiểm thử một nhánh condition.

`ApplicationContextRunner` kiểm tra context/bean conditions. Nó không thay thế integration test gọi RPC qua channel và server thật.

## 8. Chẩn đoán khi gRPC auto-configuration không hoạt động

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Không có server bean | Thiếu server starter hoặc condition classpath không khớp | Runtime dependency tree và negative matches |
| Không có client/channel bean | Thiếu client starter, sai artifact hoặc property condition | Condition report và effective properties |
| Auto-configuration không xuất hiện trong report | Class chưa được import/discover hoặc bị exclude | Kiểm tra imports metadata và exclusions |
| Bean mặc định không được tạo | `@ConditionalOnMissingBean` đã back-off | Kiểm tra bean cùng kiểu trong context |
| Condition property không khớp | Sai prefix/name, giá trị khác hoặc profile chưa bật | Xem Environment và property sources |
| Context báo thiếu dependency | `@ConditionalOnBean` không thỏa hoặc bean nghiệp vụ chưa được scan | Kiểm tra bean definitions và component scan |
| Bean tồn tại nhưng RPC `UNAVAILABLE` | Condition đã qua nhưng target/network/server có vấn đề | Kiểm tra DNS, port, TLS và server readiness |
| RPC trả `UNIMPLEMENTED` | Service method chưa đăng ký hoặc contract lệch | Kiểm tra `BindableService`, service name và `.proto` |

### Phân biệt lỗi ở các tầng

Một auto-configuration được đánh dấu positive match chỉ có nghĩa các điều kiện để áp dụng cấu hình đã thỏa. Nó không bảo đảm mọi bean tạo sau đó đều khởi tạo thành công; bean creation vẫn có thể thất bại do constructor, resource hoặc dependency.

Tương tự, có `ManagedChannel` bean không có nghĩa channel đã đạt trạng thái `READY`. Có service bean không có nghĩa service đã được bind vào server nếu starter không nhận diện loại bean đó. Khi điều tra, đi lần lượt từ condition report, bean context, server lifecycle đến RPC thực tế.

## 9. Checklist kiểm tra trước khi sửa cấu hình

1. Xác nhận đúng server/client starter và version trên runtime classpath.
2. Xác định auto-configuration class liên quan có được phát hiện hay bị exclude.
3. Đọc positive/negative match và lý do cụ thể trong Condition Evaluation Report.
4. Kiểm tra property sau khi Spring hợp nhất YAML, profile, environment và command line.
5. Kiểm tra bean condition và back-off; tìm bean tùy chỉnh cùng kiểu.
6. Kiểm tra ordering khi auto-configuration phụ thuộc bean do cấu hình khác cung cấp.
7. Dùng `ApplicationContextRunner` để tái hiện condition tối thiểu.
8. Sau khi bean xuất hiện, tiếp tục kiểm tra service registration/channel/RPC riêng.
9. Tắt hoặc bảo vệ debug/Actuator endpoint phù hợp trước khi đưa ứng dụng vào production.

Với **SPRING_GRPC**, kiểm tra auto-configuration giúp xác định Spring Boot đã nhận diện đúng dependency và điều kiện để dựng các thành phần gRPC hay chưa. Condition report giải thích vì sao cấu hình được áp dụng hoặc back-off; kiểm tra bean và RPC tiếp tục xác minh những giai đoạn sau. Phân tách được các bước này giúp sửa đúng nguyên nhân thay vì thay dependency hoặc properties theo phỏng đoán.
