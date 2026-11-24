# Tag dùng chung theo dịch vụ, môi trường và vùng triển khai

Tag là các cặp khóa–giá trị gắn với meter để phân loại và truy vấn metrics. Với một hệ thống có nhiều ứng dụng, nhiều môi trường và nhiều vùng triển khai, ba thông tin **dịch vụ (service)**, **môi trường (environment)** và **vùng triển khai (region)** thường là những chiều phân loại nền tảng. Đưa chúng thành tag dùng chung giúp người vận hành lọc, so sánh và tổng hợp số liệu nhất quán giữa các dịch vụ.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, Micrometer cung cấp Counter, Gauge, Timer, Distribution Summary và registry để xuất metrics. Thiết kế tag cần giữ được ngữ cảnh vận hành mà không làm số lượng time series tăng mất kiểm soát. Bài này tập trung vào cách xác định ba tag nền tảng, cung cấp giá trị theo môi trường triển khai và áp dụng chúng đồng nhất trong ứng dụng Java/Spring Boot.

## 1. Vì sao cần tag dùng chung?

Tên metric cho biết đại lượng được đo; tag cho biết đại lượng đó thuộc về nhóm nào. Ví dụ, metric số request có thể được phân loại theo dịch vụ, môi trường và vùng:

~~~text
http.server.requests{
  service="checkout-service",
  environment="production",
  region="ap-southeast-1"
}
~~~

Khi các tag này xuất hiện nhất quán trên nhiều meter, người vận hành có thể:

- Lọc dashboard để chỉ xem một dịch vụ hoặc một môi trường.
- So sánh cùng một dịch vụ giữa staging và production.
- So sánh độ trễ hoặc tỷ lệ lỗi giữa các vùng triển khai.
- Tổng hợp số liệu của nhiều instance thuộc cùng một dịch vụ.
- Viết cảnh báo có phạm vi rõ ràng, chẳng hạn chỉ cảnh báo lỗi của checkout-service ở production.

Nếu mỗi nhóm phát triển tự đặt khóa và giá trị khác nhau, truy vấn trở nên khó tổng hợp. Ví dụ, một dịch vụ dùng app, dịch vụ khác dùng application, nơi khác lại dùng service_name; tương tự, prod, production và prd có thể cùng chỉ một môi trường. Một bộ tag nền tảng thống nhất giúp tránh những khác biệt không cần thiết.

## 2. Xác định ý nghĩa và quy ước cho từng tag

Nên thống nhất tên khóa, ý nghĩa, nguồn dữ liệu và tập giá trị hợp lệ trước khi áp dụng trên toàn hệ thống.

| Tag | Ý nghĩa | Ví dụ giá trị | Nguồn nên dùng |
|---|---|---|---|
| service | Tên logic của dịch vụ đang phát ra metric | checkout-service, catalog-service | Cấu hình ứng dụng hoặc metadata triển khai |
| environment | Môi trường mà dịch vụ đang chạy | development, staging, production | Cấu hình theo môi trường triển khai |
| region | Vùng hạ tầng nơi instance dịch vụ đang chạy | ap-southeast-1, us-east-1 | Cấu hình nền tảng, cloud metadata hoặc deployment |

**service** nên đại diện cho một ứng dụng hoặc dịch vụ logic ổn định. Nó không nên là tên class Java, tên pod, tên máy hay mã của từng instance. Ví dụ checkout-service có thể có nhiều replica nhưng tất cả replica đều mang cùng tag service.

**environment** mô tả nơi workload đang chạy, không phải trạng thái của một request. Dùng một tập giá trị có giới hạn và thống nhất chữ thường, ví dụ development, staging, production. Không trộn lẫn prod, production, live nếu chúng cùng mang một ý nghĩa.

**region** là vùng triển khai của chính instance phát metrics. Ví dụ, instance chạy ở ap-southeast-1 thì các metric của instance đó mang region="ap-southeast-1". Không lấy region từ request header, người dùng, tenant hoặc vùng của dịch vụ đích nếu điều đó không phản ánh vị trí triển khai của instance. Nếu cần đo vùng đích của một lời gọi liên vùng, có thể dùng một tag nghiệp vụ riêng như target_region, với tập giá trị được kiểm soát.

Tên service, environment, region trong ví dụ là một quy ước đơn giản. Nếu tổ chức đã có chuẩn chung, hãy dùng đúng chuẩn đó trên mọi dịch vụ và backend. Điều quan trọng là cùng một khóa phải giữ nguyên ý nghĩa, kiểu giá trị và cách chuẩn hóa trong toàn hệ thống.

Tên module OBSERVABILITY_INSTRUMENTATION_MICROMETER xác định phạm vi bài học. Khi instrument một ứng dụng thật, giá trị tag service phải là tên dịch vụ đang chạy, chẳng hạn checkout-service, chứ không phải tên module học tập.

## 3. Cung cấp giá trị tag từ cấu hình môi trường

Không nên hardcode production hoặc một region cụ thể trong mã nguồn dùng chung cho mọi môi trường. Hãy đưa giá trị vào cấu hình triển khai, sau đó để Spring Boot đưa chúng vào registry.

Ví dụ application.yml:

~~~yaml
spring:
  application:
    name: checkout-service

management:
  metrics:
    tags:
      service: ${spring.application.name}
      environment: ${APP_ENV:development}
      region: ${DEPLOYMENT_REGION:local}
~~~

Trong cấu hình trên:

- spring.application.name xác định tên logic của dịch vụ.
- APP_ENV được cung cấp từ môi trường chạy, ví dụ staging hoặc production.
- DEPLOYMENT_REGION được nền tảng triển khai cung cấp, ví dụ ap-southeast-1.
- Giá trị mặc định development và local giúp chạy local dễ dàng; production nên khai báo rõ hai biến này.

Ví dụ biến môi trường khi chạy ứng dụng:

~~~bash
APP_ENV=production
DEPLOYMENT_REGION=ap-southeast-1
~~~

Trong Docker Compose, Kubernetes hoặc hệ thống triển khai khác, khai báo hai biến theo cấu hình của từng deployment. Nếu region lấy từ cloud metadata hoặc nhãn node, nên chuyển nó thành một giá trị cấu hình ổn định tại lúc khởi động. Tránh gọi metadata service cho từng lần ghi metric hoặc đọc thông tin vị trí từ dữ liệu request.

Cần kiểm tra giá trị thực tế khi khởi động. Một biến bị thiếu có thể khiến tất cả instance mang cùng giá trị mặc định local, làm dashboard production phân loại sai. Có thể fail fast khi môi trường production không có region hợp lệ, thay vì âm thầm xuất dữ liệu với giá trị mặc định.

## 4. Spring Boot tự áp dụng common tags cho registry

Với Spring Boot Actuator và registry Micrometer trên classpath, thuộc tính management.metrics.tags.* được dùng để bổ sung các tag chung vào meter do registry quản lý. Cách này phù hợp khi giá trị tag đến từ cấu hình và không cần logic khởi tạo riêng.

Dependency cơ bản trong Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Sau khi ứng dụng khởi động, có thể xem endpoint /actuator/prometheus (khi endpoint được expose) để xác nhận các metric có chứa nhãn chung. Ví dụ một dòng exposition có thể trông như sau:

~~~text
checkout_orders_completed_total{
  service="checkout-service",
  environment="production",
  region="ap-southeast-1",
  channel="web"
} 42
~~~

Tên metric và cách biểu diễn có thể được chuẩn hóa theo registry; điều cần kiểm tra là ba label có đúng giá trị và xuất hiện nhất quán.

### Khi cần tùy biến bằng Java

Nếu giá trị được lấy từ một lớp cấu hình riêng hoặc cần logic kiểm tra/chuẩn hóa trước khi gắn vào registry, có thể dùng MeterRegistryCustomizer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsTagConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags(
            @Value("${spring.application.name}") String service,
            @Value("${app.environment}") String environment,
            @Value("${app.region}") String region) {

        return registry -> registry.config().commonTags(
                "service", service,
                "environment", environment,
                "region", region
        );
    }
}
~~~

Cấu hình tương ứng có thể đặt trong application.yml:

~~~yaml
spring:
  application:
    name: checkout-service

app:
  environment: ${APP_ENV:development}
  region: ${DEPLOYMENT_REGION:local}
~~~

MeterRegistryCustomizer cho phép tùy biến registry do Spring Boot quản lý trước khi meter được đăng ký. Nếu dùng cách này, không cần khai báo cùng ba tag lần nữa trong management.metrics.tags; hãy chọn một nơi làm nguồn cấu hình chính để tránh lặp và khó kiểm soát.

Với ứng dụng Java không dùng Spring Boot, có thể áp dụng common tags trực tiếp sau khi tạo registry và trước khi đăng ký meter:

~~~java
registry.config().commonTags(
        "service", serviceName,
        "environment", environment,
        "region", region
);
~~~

Thời điểm gọi rất quan trọng: hãy cấu hình common tags trước khi tạo các meter. Không nên tạo meter ở một registry rồi tạo registry khác với common tags và kỳ vọng những meter cũ tự chuyển sang registry mới.

## 5. Common tags khác với tag riêng của từng meter

Common tags mô tả ngữ cảnh áp dụng cho hầu hết hoặc toàn bộ metrics của một dịch vụ. Tag riêng của meter mô tả chiều phân loại chỉ có ý nghĩa đối với một loại số đo cụ thể.

Ví dụ, service, environment, region là tag chung; method, status, channel có thể là tag riêng:

~~~java
Counter completed = Counter.builder("checkout.orders.completed")
        .description("Number of completed checkout orders")
        .tag("channel", "web")
        .register(registry);

Timer requestDuration = Timer.builder("checkout.request.duration")
        .description("Checkout request duration")
        .tag("method", "POST")
        .tag("status", "success")
        .register(registry);
~~~

Khi xuất, các meter này nhận cả common tags lẫn tag riêng. Nhờ đó, truy vấn có thể lọc theo vùng hoặc môi trường trước, rồi tiếp tục phân tích theo channel, method hoặc status.

Không nên thêm các tag không liên quan vào tất cả meter chỉ để có cùng số lượng cột. Ví dụ, payment_type có ý nghĩa với metric thanh toán nhưng không nhất thiết có ý nghĩa với metric JVM heap. Hãy giữ bộ tag chung nhỏ và ổn định; chỉ thêm tag theo meter khi nó giúp trả lời một câu hỏi vận hành cụ thể.

## 6. Kiểm soát cardinality khi kết hợp tag

Mỗi tổ hợp tên metric và các giá trị tag tạo ra một time series riêng. Vì vậy, dù service, environment và region đều là các chiều có giá trị giới hạn, số lượng tổ hợp của chúng vẫn nhân lên theo số dịch vụ, môi trường và vùng.

Ví dụ, một hệ thống có:

- 8 dịch vụ.
- 3 môi trường.
- 4 vùng triển khai.

Chỉ riêng ba tag chung đã tạo tối đa 8 × 3 × 4 = 96 tổ hợp cho mỗi meter name nếu mọi dịch vụ chạy ở mọi môi trường và vùng. Với 40 meter name, đó là 3.840 chuỗi thời gian cơ sở trước khi tính thêm tag riêng, histogram bucket hoặc các dạng series bổ sung.

Đây là chi phí có chủ đích nếu các chiều đó cần thiết cho vận hành. Tuy nhiên, không nên mở rộng tập giá trị một cách tùy tiện. Các nguyên tắc sau giúp kiểm soát cardinality:

- Dùng tên dịch vụ từ danh mục dịch vụ ổn định; không đưa tên pod hoặc request vào service.
- Chuẩn hóa environment thành một tập giá trị hữu hạn; không dùng branch name, build number hoặc tên pull request.
- Dùng region theo danh mục vùng triển khai; không dùng tọa độ, tên thành phố tự do hoặc giá trị do client gửi.
- Tránh tag có giá trị gần như duy nhất như userId, orderId, sessionId, email, requestId và URL chứa ID.
- Chỉ thêm availability_zone, cluster hoặc namespace nếu thực sự cần truy vấn theo các chiều đó và đã đánh giá tác động số chuỗi thời gian.

Không dùng tag metric để lưu dữ liệu sự kiện chi tiết. Khi cần điều tra một request hoặc một người dùng cụ thể, log và trace phù hợp hơn vì chúng hỗ trợ dữ liệu có độ chi tiết cao mà không buộc backend metrics tạo một time series cho từng giá trị.

## 7. Phân biệt service, instance và vùng đích

Trong một dịch vụ có nhiều replica, nhiều instance có thể cùng mang:

~~~text
service="checkout-service"
environment="production"
region="ap-southeast-1"
~~~

Các tag này cho phép tổng hợp số liệu ở cấp dịch vụ hoặc vùng. Nếu cần phân biệt từng replica để điều tra một instance bất thường, dùng nhãn instance do cơ chế discovery/scrape hoặc nền tảng giám sát quản lý. Không đưa pod UID hoặc hostname thay đổi liên tục vào bộ common tags nếu backend đã có cơ chế định danh target.

Cũng cần phân biệt region với vùng mà request được gửi đến. Một instance ở Singapore có thể xử lý request hướng đến một vùng khác; region vẫn mô tả nơi instance đang chạy. Nếu việc định tuyến liên vùng là một chỉ số nghiệp vụ cần phân tích, dùng một chiều riêng như target_region và chỉ cho phép các giá trị vùng đã định nghĩa.

Với hệ thống đa vùng, hãy bảo đảm mọi vùng dùng cùng quy ước khóa và giá trị. Nếu một region xuất hiện dưới nhiều dạng như ap-southeast-1, singapore và sg, truy vấn tổng hợp có thể coi chúng là ba nhóm khác nhau.

## 8. Kiểm thử common tags

Có thể kiểm tra tag dùng chung ngay trong kiểm thử Spring Boot bằng cách đăng ký một meter và đọc ID của nó:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "spring.application.name=checkout-service",
        "management.metrics.tags.service=checkout-service",
        "management.metrics.tags.environment=staging",
        "management.metrics.tags.region=ap-southeast-1"
})
class MetricsTagConfigurationTest {

    @Autowired
    MeterRegistry registry;

    @Test
    void appliesServiceEnvironmentAndRegionTags() {
        Counter counter = registry.counter("checkout.test.counter");

        assertThat(counter.getId().getTag("service"))
                .isEqualTo("checkout-service");
        assertThat(counter.getId().getTag("environment"))
                .isEqualTo("staging");
        assertThat(counter.getId().getTag("region"))
                .isEqualTo("ap-southeast-1");
    }
}
~~~

Kiểm thử này xác nhận registry đã áp dụng ba tag và giá trị được cấu hình đúng. Có thể bổ sung kiểm thử cấu hình cho từng profile để bảo đảm staging và production không vô tình dùng chung giá trị.

Ngoài unit test, hãy kiểm tra endpoint metrics hoặc dữ liệu tại backend trong môi trường tích hợp. Xác nhận rằng:

1. Các metric nền và metric nghiệp vụ đều có ba tag chung.
2. Giá trị service, environment và region khớp với deployment đang chạy.
3. Nhiều replica của cùng dịch vụ có cùng ba giá trị khi chúng ở cùng môi trường và vùng.
4. Không xuất hiện biến thể chính tả hoặc chữ hoa/chữ thường ngoài quy ước.
5. Số lượng time series vẫn nằm trong ngân sách cardinality đã dự kiến.

## 9. Checklist thiết kế tag nền tảng

Trước khi áp dụng common tags cho một dịch vụ, hãy xác nhận:

- service đại diện cho tên logic ổn định của ứng dụng.
- environment lấy từ cấu hình triển khai và thuộc tập giá trị đã thống nhất.
- region mô tả nơi instance chạy và lấy từ nguồn cấu hình đáng tin cậy.
- Tên khóa, chữ hoa/chữ thường và cách viết giá trị thống nhất giữa các dịch vụ.
- Common tags được cấu hình trước khi meter được đăng ký.
- Chỉ có một nguồn cấu hình chính cho các tag dùng chung.
- Tag riêng của từng meter có mục đích truy vấn rõ ràng và cardinality hữu hạn.
- Đã kiểm thử tag trong ứng dụng và xác minh dữ liệu được xuất đến backend.

Khi ba tag nền tảng được thiết kế nhất quán, metrics từ nhiều dịch vụ và vùng triển khai có thể được lọc, so sánh và tổng hợp theo cùng một cách. Micrometer giúp áp dụng chúng ở tầng instrumentation; cấu hình triển khai cung cấp giá trị đúng cho từng môi trường; còn việc giới hạn tập giá trị giữ cho hệ thống metrics có chi phí và khả năng truy vấn ổn định.
