# @ConditionalOnBean: yêu cầu bean phụ thuộc đã được đăng ký

## 1. Bài toán và ý nghĩa

Giả sử một thư viện Spring Boot cung cấp bean `GatewayReporter` để theo dõi trạng thái của `Gateway`. Không phải ứng dụng nào cũng khai báo `Gateway`. Nếu luôn đăng ký `GatewayReporter` và yêu cầu Spring tiêm `Gateway` qua constructor hoặc tham số phương thức `@Bean`, ứng dụng không có `Gateway` có thể khởi động thất bại vì thiếu dependency.

`@ConditionalOnBean` giải quyết bài toán *đăng ký bean theo điều kiện*: chỉ đăng ký một bean hoặc một nhóm cấu hình khi trong `BeanFactory` đã có bean đáp ứng yêu cầu được chỉ định.

~~~java
@Bean
@ConditionalOnBean(Gateway.class)
GatewayReporter gatewayReporter(Gateway gateway) {
    return new GatewayReporter(gateway);
}
~~~

Trong ví dụ này:
- Khi bean kiểu `Gateway` đã được đăng ký và được điều kiện nhìn thấy, Spring có thể đăng ký định nghĩa `gatewayReporter`.
- Khi chưa tìm được bean `Gateway`, định nghĩa `gatewayReporter` bị bỏ qua; không có đối tượng `GatewayReporter` do phương thức này tạo ra.
- Điều kiện **không tự tạo** `Gateway`, cũng không có nghĩa là bean phụ thuộc đã được khởi tạo, kết nối mạng thành công hay sẵn sàng phục vụ.

Đây là annotation của **Spring Boot**: `org.springframework.boot.autoconfigure.condition.ConditionalOnBean`, được xây dựng trên cơ chế `@Conditional` của Spring Framework.

## 2. Điều gì được kiểm tra và kiểm tra vào lúc nào?

Cần phân biệt ba sự kiện:

1. **Khai báo/đăng ký bean definition:** Spring đã xử lý `@Component`, `@Bean` hoặc cơ chế đăng ký khác và biết có bean nào, tên gì, kiểu gì.
2. **Đánh giá điều kiện:** Khi xử lý cấu hình có `@ConditionalOnBean`, Spring Boot xét các bean definition **đã được xử lý đến thời điểm đó** trong phạm vi tìm kiếm được cấu hình.
3. **Tạo instance và tiêm dependency:** Sau đó Spring mới khởi tạo các bean cần thiết và giải quyết quan hệ phụ thuộc theo lifecycle của container.

Do đó, “bean đã được đăng ký” khác với “bean đã khởi tạo xong”. Một `@Lazy` bean có thể đã được đăng ký và làm điều kiện khớp dù instance chưa được tạo. Ngược lại, một bean dự kiến được khai báo bởi auto-configuration khác nhưng **chưa được xử lý** khi điều kiện chạy có thể khiến điều kiện không khớp.

`@ConditionalOnBean` là quyết định trong quá trình xây dựng `ApplicationContext`, không phải cơ chế liên tục theo dõi container để tự bật/tắt bean khi ứng dụng đang chạy.

### Cách hiểu đúng yêu cầu nhiều bean

~~~java
@ConditionalOnBean({Gateway.class, AuditStore.class})
~~~

Phải tìm thấy **cả** kiểu `Gateway` **và** kiểu `AuditStore`. Chúng có thể là **hai bean khác nhau**; annotation không đòi một instance đồng thời là cả hai kiểu.

~~~java
@ConditionalOnBean(value = Gateway.class, name = "primaryAuditStore")
~~~

Phải tồn tại bean kiểu `Gateway` **và** bean tên `primaryAuditStore`; hai yêu cầu không nhất thiết phải do cùng một bean đáp ứng. Đây là phép kết hợp yêu cầu tồn tại, **không phải** quy tắc tự chọn đúng bean cho một tham số tiêm phụ thuộc.

## 3. Những thuộc tính cần biết

| Cách dùng | Kiểm tra |
| --- | --- |
| `@ConditionalOnBean(Gateway.class)` hoặc `value = ...` | Có bean mang kiểu được chỉ định. Với nhiều kiểu, phải có đủ mọi kiểu. |
| `@ConditionalOnBean(type = "com.example.Gateway")` | Có bean theo tên lớp dạng chuỗi; hữu ích khi không muốn tham chiếu trực tiếp kiểu trong annotation. |
| `@ConditionalOnBean(name = "gateway")` | Có bean với tên được chỉ định; nếu khai báo nhiều tên, tất cả phải tồn tại. |
| `@ConditionalOnBean(annotation = Marker.class)` | Có bean được đánh dấu bằng annotation yêu cầu; nhiều annotation là nhiều điều kiện cần thỏa. |
| `search = SearchStrategy.CURRENT` | Chỉ xét context hiện tại, bỏ qua context cha. Mặc định là `SearchStrategy.ALL`, có xét context cha. |
| `parameterizedContainer = ...` | Cho phép xét thêm các bean container có generic chứa kiểu cần tìm, ví dụ container riêng `Registration<Gateway>`. |

**Bẫy khi bỏ trống tham số:** Đặt `@ConditionalOnBean` không đối số trên một phương thức `@Bean` làm kiểu cần tìm mặc định là **kiểu trả về của chính phương thức đó**, chứ không tự suy ra các tham số dependency của phương thức. Nếu mục đích là “chỉ tạo reporter khi có gateway”, hãy viết rõ `@ConditionalOnBean(Gateway.class)`.

### Đặt ở class hay phương thức?

- Trên **phương thức `@Bean`**: điều kiện chi phối riêng việc đăng ký bean do phương thức ấy tạo.
- Trên **class `@Configuration` hoặc `@AutoConfiguration`**: điều kiện chi phối việc đăng ký class cấu hình đó và các bean của nó. Nếu không khớp, class cấu hình không được đăng ký như một bean.
- Có thể kết hợp điều kiện cấp class và cấp phương thức khi các bean có yêu cầu khác nhau. Mỗi mức phải thỏa điều kiện tương ứng.

## 4. Ví dụ có thể chạy: kiểm chứng đủ và thiếu bean

Ví dụ dưới đây là một **test Java 17+ hoàn chỉnh** dành cho dự án Spring Boot 3.3 có dependency `spring-boot-starter-test`. Tạo file:

`src/test/java/com/example/demo/OnBeanConditionTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class OnBeanConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ReporterAutoConfiguration.class));

    interface Gateway {
        String state();
    }

    static final class GatewayReporter {
        private final Gateway gateway;

        GatewayReporter(Gateway gateway) {
            this.gateway = gateway;
        }

        String report() {
            return "gateway=" + gateway.state();
        }
    }

    @AutoConfiguration
    static class ReporterAutoConfiguration {

        @Bean
        @ConditionalOnBean(Gateway.class)
        GatewayReporter gatewayReporter(Gateway gateway) {
            return new GatewayReporter(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGatewayConfiguration {

        @Bean
        Gateway gateway() {
            return () -> "ready";
        }
    }

    @Test
    void withoutGateway_reporterIsNotRegistered() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(Gateway.class);
            assertThat(context).doesNotHaveBean(GatewayReporter.class);
        });
    }

    @Test
    void withGateway_reporterIsRegistered() {
        runner.withUserConfiguration(UserGatewayConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Gateway.class);
                    assertThat(context).hasSingleBean(GatewayReporter.class);
                    assertThat(context.getBean(GatewayReporter.class).report())
                            .isEqualTo("gateway=ready");
                });
    }
}
~~~

Trong dự án Gradle đã cấu hình Spring Boot plugin và `spring-boot-starter-test`, chạy:

~~~bash
./gradlew test --tests "com.example.demo.OnBeanConditionTest"
~~~

Trên Windows có thể dùng `.\gradlew.bat test --tests "com.example.demo.OnBeanConditionTest"`. Đây là test dùng thư viện Spring, JUnit và AssertJ nên **không** thể biên dịch bằng `javac` đơn lẻ nếu không cung cấp classpath dependency đầy đủ.

**Kết quả mong đợi:** cả hai test PASS. Test đầu không khai báo `Gateway`, vì vậy không có bean `GatewayReporter`. Test sau bổ sung user configuration chứa bean `Gateway`; auto-configuration phát hiện nó và đăng ký reporter. Phần `report()` trả chuỗi chính xác `gateway=ready`, được kiểm chứng bằng assertion thay vì dựa vào stdout hay log build.

`ApplicationContextRunner` giúp chạy hai context độc lập và kiểm tra điều kiện thực tế mà không phải khởi động toàn bộ web server.

## 5. Thứ tự auto-configuration: lỗi tinh vi nhất

Nếu `Gateway` do **người dùng khai báo** trong cấu hình ứng dụng, Spring Boot thông thường xử lý bean definition người dùng trước auto-configuration. Vì vậy điều kiện trong auto-configuration thường nhìn thấy nó.

Nếu `Gateway` do **một auto-configuration khác tạo**, phải đảm bảo cấu hình tạo `Gateway` được xử lý **trước** cấu hình phụ thuộc. Ví dụ sau chỉ minh họa quan hệ giữa hai auto-configuration; giả định `Gateway` và `GatewayReporter` đã được định nghĩa như ở phần trước:

~~~java
@AutoConfiguration
class GatewayAutoConfiguration {
    @Bean
    Gateway gateway() {
        return () -> "ready";
    }
}

@AutoConfiguration(after = GatewayAutoConfiguration.class)
class ReporterAutoConfiguration {
    @Bean
    @ConditionalOnBean(Gateway.class)
    GatewayReporter gatewayReporter(Gateway gateway) {
        return new GatewayReporter(gateway);
    }
}
~~~

Ở đây, `after = GatewayAutoConfiguration.class` yêu cầu Spring Boot xử lý cấu hình tạo `Gateway` trước cấu hình tạo reporter. Tương đương có thể sử dụng `@AutoConfigureAfter(GatewayAutoConfiguration.class)`. Các auto-configuration dùng trong ứng dụng thực phải được Spring Boot phát hiện, chẳng hạn được liệt kê theo tên class đầy đủ trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` (đối với Spring Boot 3.x).

**Quan trọng:** `after` và `@AutoConfigureAfter` điều chỉnh **thứ tự đăng ký các bean definition**, không hứa thứ tự khởi tạo instance. Thứ tự khởi tạo do quan hệ tiêm dependency, lifecycle và có thể `@DependsOn` quyết định.

Đừng kỳ vọng `@DependsOn("gateway")` sửa được một `@ConditionalOnBean` đã bị đánh giá **không khớp** do thứ tự đăng ký: `@DependsOn` chỉ liên quan việc khởi tạo các bean đã được đăng ký.

## 6. So sánh với những cơ chế dễ nhầm

| Cơ chế | Câu hỏi mà cơ chế trả lời | Trường hợp phù hợp |
| --- | --- | --- |
| `@ConditionalOnBean` | Bean yêu cầu **đã được đăng ký và được nhìn thấy** chưa? | Chỉ đăng ký phần mở rộng khi có dependency bean. |
| `@ConditionalOnMissingBean` | Chưa tồn tại bean đáp ứng yêu cầu? | Cung cấp bean mặc định để người dùng có thể thay thế. |
| `@ConditionalOnClass` | Kiểu Java có trên classpath không? | Chỉ kích hoạt tích hợp khi thư viện tương ứng có mặt. |
| `@ConditionalOnProperty` | Cấu hình/giá trị property có thỏa điều kiện không? | Bật/tắt tính năng theo cấu hình. |
| `@ConditionalOnSingleCandidate` | Có một candidate thích hợp, chẳng hạn chỉ một bean phù hợp hoặc có primary rõ ràng? | Cần chọn dependency không mơ hồ khi nhiều bean cùng kiểu. |
| `@DependsOn` | Instance nào cần được khởi tạo trước instance khác? | Điều phối initialization cho các bean **đã được đăng ký**. |

Ví dụ: chỉ có thư viện chứa class `Gateway` trên classpath **chưa đủ** để `@ConditionalOnBean(Gateway.class)` khớp. Cần bean phù hợp trong `BeanFactory`. Ngược lại, có bean definition chưa chắc đã được khởi tạo, hoặc khởi tạo sẽ thành công.

## 7. Lỗi thường gặp và cách xử lý

1. **Bean phụ thuộc tồn tại trong mã nguồn nhưng điều kiện vẫn false.** Kiểm tra nó có thật sự được đăng ký vào context không: class có được component-scan không, `@Bean` có được import không, có điều kiện khác chặn nó không, hoặc auto-configuration tạo nó chạy sau hay không.
2. **Gắn `@ConditionalOnBean` vào cấu hình người dùng và dựa vào thứ tự scan.** Thứ tự xử lý bean definitions có thể khiến kết quả bất ngờ. Theo khuyến nghị của Spring Boot, nên ưu tiên dùng điều kiện bean trong auto-configuration, nơi các bean do người dùng khai báo đã được xử lý trước.
3. **Quên chỉ định kiểu dependency.** `@ConditionalOnBean` trống trên `@Bean Reporter reporter(...)` mặc định kiểm tra `Reporter`, không kiểm tra `Gateway`. Ghi rõ `@ConditionalOnBean(Gateway.class)`.
4. **Phương thức `@Bean` khai báo kiểu trả về quá chung như `Object`.** Điều kiện dựa vào metadata kiểu đã biết tại thời điểm đánh giá. Trả về kiểu cụ thể và giàu thông tin nhất có thể, thay vì giấu kiểu thực trong factory method.
5. **Điều kiện true nhưng tiêm bean vẫn lỗi.** Sự tồn tại của một bean theo kiểu hoặc tên không đảm bảo có đúng một bean phù hợp với `@Qualifier`, không có ambiguity hay circular dependency. Khi cần một candidate duy nhất, cân nhắc `@ConditionalOnSingleCandidate` hoặc làm rõ `@Qualifier`/`@Primary`.
6. **Bean tùy chọn bị bỏ qua nhưng consumer lại luôn bắt buộc tiêm nó.** Chỉ điều kiện hóa reporter mà để một bean khác constructor-inject `GatewayReporter` bắt buộc vẫn có thể làm context khởi động thất bại. Cần đồng bộ điều kiện cho consumer, thiết kế tích hợp tùy chọn hoặc cung cấp fallback thích hợp.
7. **Nhầm context cha/con.** Mặc định `search = ALL` có thể tìm thấy bean ở parent context. Nếu chỉ chấp nhận bean của context hiện tại, dùng `SearchStrategy.CURRENT`; phải xét đúng cấu trúc context khi debug.
8. **Tin rằng condition bảo đảm hạ tầng runtime khỏe mạnh.** Nó chỉ xét bean registration. Bean có thể khởi tạo lỗi hoặc kết nối dịch vụ bên ngoài thất bại sau khi condition đã khớp.

## 8. Chẩn đoán và kiểm thử

Khi một bean không xuất hiện:

1. Bật báo cáo điều kiện của Spring Boot bằng đối số `--debug` hoặc property `debug=true` trong môi trường phù hợp. Tìm tên auto-configuration và nguyên nhân `matched`/`did not match` liên quan `OnBeanCondition`.
2. Xác nhận bean prerequisite có mặt **trong đúng ApplicationContext** và kiểu hiển thị của bean definition khớp kiểu cần kiểm tra.
3. Nếu prerequisite do auto-configuration khác khai báo, kiểm tra `@AutoConfiguration(after = ...)` hoặc `@AutoConfigureAfter` và việc đăng ký auto-configuration ở file imports.
4. Viết test `ApplicationContextRunner` cho ít nhất hai nhánh **không có** và **có** prerequisite. Nếu có hai auto-configuration liên quan, thêm test chạy cả hai để kiểm chứng order. Khi cần, sử dụng `ConditionEvaluationReportLoggingListener` để xem lý do điều kiện trong test.
5. Nếu dự án có Actuator và chủ động bật/expose endpoint tương ứng, `/actuator/conditions` cũng có thể giúp xem condition evaluation; việc expose endpoint phụ thuộc cấu hình và chính sách truy cập.

### Câu hỏi tự kiểm tra

- Nếu bean `Gateway` chỉ tồn tại dưới dạng class trên classpath, `@ConditionalOnBean(Gateway.class)` có khớp không? **Không, nếu chưa có bean phù hợp được đăng ký.**
- Nếu có bean definition `Gateway` nhưng instance chưa được tạo vì `@Lazy`, điều kiện có thể khớp không? **Có**, nếu bean definition đã được xử lý và đủ thông tin kiểu.
- Nếu điều kiện yêu cầu `{Gateway.class, AuditStore.class}`, hai kiểu có phải cùng một instance không? **Không**; phải đáp ứng đủ các yêu cầu, có thể bằng nhiều bean.
- Vì sao cần `@AutoConfiguration(after = ...)`? **Để auto-configuration phụ thuộc được đánh giá sau khi bean definition từ auto-configuration cung cấp đã được xử lý.**
- `@DependsOn` có làm điều kiện false thành true không? **Không**; nó xử lý thứ tự khởi tạo, không hồi tố điều kiện đăng ký.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): bean conditions, thứ tự auto-configuration và `ApplicationContextRunner`.
- [Spring Boot 3.3 — JavaDoc `@ConditionalOnBean`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): semantics chính xác và các thuộc tính annotation.
