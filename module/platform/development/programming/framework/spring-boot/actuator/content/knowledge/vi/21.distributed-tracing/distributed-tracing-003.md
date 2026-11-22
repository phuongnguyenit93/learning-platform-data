# Lựa chọn bridge OpenTelemetry hoặc Brave và exporter tương thích

## 1. Cần lựa chọn những thành phần nào?

Một dịch vụ có thể tạo observation nhưng chưa gửi được dữ liệu truy vết phân tán. Để lựa chọn đúng dependency, trước hết cần nhìn thấy đường đi của dữ liệu:

~~~text
Mã ứng dụng / framework
        |
        v
Micrometer Observation và Micrometer Tracing
        |
        v
Bridge: OpenTelemetry hoặc Brave
        |
        v
Bộ thực thi tracer tương ứng
        |
        v
Exporter / reporter và cơ chế gửi
        |
        v
Collector hoặc hệ thống lưu trữ, tìm kiếm trace
~~~

**Trace** là vết truy vết của một luồng xử lý có thể đi qua nhiều dịch vụ. **Span** biểu diễn một đơn vị công việc trong trace đó. **Tracer** tạo và quản lý span cùng ngữ cảnh truy vết.

**Bridge** là lớp thích ứng giữa API Micrometer Tracing và thư viện truy vết được chọn. **Exporter/reporter** phụ trách đưa các span đã ghi nhận ra ngoài theo định dạng và giao thức phù hợp. **Backend** là hệ thống lưu trữ và cho phép tìm kiếm dữ liệu; **Collector** có thể nhận, xử lý rồi chuyển tiếp dữ liệu tới backend.

Ví dụ:

~~~text
Micrometer → OpenTelemetry bridge → OpenTelemetry SDK → OTLP → Collector
Micrometer → Brave bridge         → Brave             → Zipkin API → Zipkin
Micrometer → OpenTelemetry bridge → OpenTelemetry SDK → Zipkin API → Zipkin
~~~

Dòng thứ ba cho thấy tên thư viện tracer không quyết định cứng backend phải dùng. OpenTelemetry có thể xuất sang Zipkin; không phải cứ thấy Zipkin là bắt buộc chọn Brave.

Bài tập trung vào tích hợp **Micrometer Tracing do Spring Boot 3.3 quản lý**. Đây là một cách tích hợp cụ thể; không trộn cấu hình của cách này với OpenTelemetry Java Agent hoặc một bộ starter OpenTelemetry khác rồi coi chúng là cùng một cơ chế.

## 2. Chọn đúng một bridge

Micrometer Tracing hỗ trợ hai bridge chính:

| Bộ thực thi tracer | Dependency bridge |
| --- | --- |
| OpenTelemetry | `io.micrometer:micrometer-tracing-bridge-otel` |
| OpenZipkin Brave | `io.micrometer:micrometer-tracing-bridge-brave` |

**Chỉ chọn một bridge trên runtime classpath.** Micrometer hướng dẫn không đặt cả hai bridge cùng lúc. [Micrometer Tracing: Supported Tracers](https://docs.micrometer.io/tracing/reference/tracers.html).

Lý do về thiết kế: ứng dụng cần một đường chuyển từ API truy vết chung sang bộ thực thi đã chọn. Thêm hai bridge không phải cơ chế dự phòng tự động, cũng không phải cách hợp lệ để “một phần dùng Brave, một phần dùng OpenTelemetry” trong cấu hình thông thường.

Khi lỡ có cả hai, hành vi cấu hình có thể phụ thuộc các bean, điều kiện tự cấu hình và dependency thực tế. Không dựa vào việc ứng dụng vẫn khởi động để kết luận rằng cả hai đã phối hợp đúng.

Tương tự, chỉ có bridge chưa chứng minh rằng dữ liệu đã được gửi tới một nơi lưu trữ. Cần kiểm tra cả exporter/reporter, endpoint, việc lấy mẫu và nơi nhận.

Nếu cần gửi dữ liệu đến nhiều đích, hãy thiết kế đường xuất có chủ đích, chẳng hạn chuyển tiếp qua Collector. Không thêm một bridge thứ hai để thay cho việc thiết kế nhiều đích nhận.

## 3. Các tổ hợp được Spring Boot 3.3 hỗ trợ

Mọi tổ hợp trong bảng dưới đây đều cần `org.springframework.boot:spring-boot-starter-actuator` bên cạnh các dependency được liệt kê.

| Tracer được chọn | Bridge | Exporter/reporter | Đường nhận dữ liệu |
| --- | --- | --- | --- |
| OpenTelemetry | `io.micrometer:micrometer-tracing-bridge-otel` | `io.opentelemetry:opentelemetry-exporter-otlp` | Collector/backend có cổng nhận OTLP phù hợp |
| OpenTelemetry | `io.micrometer:micrometer-tracing-bridge-otel` | `io.opentelemetry:opentelemetry-exporter-zipkin` | Zipkin API |
| OpenTelemetry | `io.micrometer:micrometer-tracing-bridge-otel` | `io.micrometer:micrometer-tracing-reporter-wavefront` | Wavefront |
| Brave | `io.micrometer:micrometer-tracing-bridge-brave` | `io.zipkin.reporter2:zipkin-reporter-brave` | Zipkin API |
| Brave | `io.micrometer:micrometer-tracing-bridge-brave` | `io.micrometer:micrometer-tracing-reporter-wavefront` | Wavefront |

Đây là các tổ hợp được tài liệu Spring Boot 3.3 mô tả, không phải bảng khẳng định mọi exporter Java có thể ghép với mọi tracer. [Spring Boot 3.3: Tracer Implementations](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.tracing.implementations).

### 3.1. Những tổ hợp dễ ghép nhầm

- `micrometer-tracing-bridge-brave` cùng `opentelemetry-exporter-otlp` không tạo đường xuất OTLP trực tiếp được Spring Boot 3.3 tự cấu hình.
- `micrometer-tracing-bridge-otel` cùng `zipkin-reporter-brave` không phải cặp thay thế cho OpenTelemetry Zipkin exporter.
- `opentelemetry-exporter-zipkin` và `opentelemetry-exporter-otlp` đều thuộc hệ OpenTelemetry, nhưng dùng định dạng/đường nhận khác nhau.
- Thêm một dependency chỉ có API không đảm bảo có đầy đủ bộ thực thi và cơ chế xuất.

Riêng OTLP, Spring Boot 3.3 chỉ tự cấu hình với OpenTelemetry. [Javadoc OtlpAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/tracing/otlp/OtlpAutoConfiguration.html).

### 3.2. Ghi chú về Wavefront trong bảng

Wavefront được giữ trong bảng để phản ánh phạm vi tích hợp của Spring Boot 3.3. Tài liệu Micrometer hiện đánh dấu Wavefront reporter là deprecated do thông báo kết thúc vòng đời dịch vụ. Vì vậy không xem sự có mặt trong bảng lịch sử phiên bản là khuyến nghị chọn mới một hệ thống đích. [Micrometer Tracing: Supported Reporters](https://docs.micrometer.io/tracing/reference/reporters.html).

## 4. Chọn theo yêu cầu tích hợp

| Yêu cầu thực tế | Lựa chọn có cơ sở |
| --- | --- |
| Hạ tầng tiếp nhận trace qua OTLP, muốn dùng cơ chế tự cấu hình của Boot 3.3 | OpenTelemetry bridge + OTLP exporter |
| Hệ thống đang dùng Brave, đã có Zipkin và các phần mở rộng Brave phù hợp | Brave bridge + Zipkin reporter |
| Muốn dùng OpenTelemetry nhưng nơi nhận hiện tại là Zipkin | OpenTelemetry bridge + Zipkin exporter |
| Dịch vụ cũ dùng Brave nhưng đường xử lý tập trung chuyển sang Collector | Cân nhắc gửi Zipkin tới receiver tương ứng của Collector, hoặc lập kế hoạch đổi tracer |
| Chỉ muốn bổ sung việc xuất trace, chưa có yêu cầu đặc thù | Xác định giao thức nhận và cách vận hành trước, rồi chọn một tổ hợp đầy đủ |

Bảng là cách suy luận từ yêu cầu tương thích, không phải kết luận rằng một tracer luôn nhanh hơn, nhẹ hơn hoặc tốt hơn tracer còn lại.

Những câu hỏi nên trả lời trước khi sửa dependency:

1. Nơi nhận chấp nhận OTLP, Zipkin hay một giao thức khác?
2. Với OTLP, nơi nhận dùng HTTP/protobuf hay gRPC?
3. Ứng dụng hiện đã phụ thuộc API hoặc phần mở rộng riêng của Brave/OpenTelemetry chưa?
4. Các dịch vụ giao tiếp với nhau dùng định dạng truyền ngữ cảnh nào?
5. Ai quản lý phiên bản SDK, cơ chế xuất và cấu hình runtime?

Nếu mã nghiệp vụ chỉ dùng API Micrometer, việc đổi bộ thực thi có thể ít ảnh hưởng hơn so với mã gọi trực tiếp các kiểu riêng của Brave hoặc OpenTelemetry. Tuy nhiên, vẫn cần kiểm tra hành vi truy vết, nhãn, lấy mẫu và truyền ngữ cảnh sau khi đổi.

### 4.1. Collector không làm mất yêu cầu tương thích ở từng chặng

Một đường chuyển tiếp có thể là:

~~~text
Ứng dụng Brave
    |
    | Zipkin API
    v
Zipkin receiver của Collector
    |
    | đường xuất do Collector cấu hình
    v
Backend đích
~~~

OpenTelemetry Collector có Zipkin receiver để nhận span theo định dạng Zipkin. [Collector Contrib: Zipkin Receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/zipkinreceiver).

Trong sơ đồ này, ứng dụng vẫn gửi Zipkin. Việc Collector có thể chuyển tiếp về sau không biến exporter phía ứng dụng thành OTLP exporter. Mỗi chặng cần đúng receiver, giao thức và cấu hình.

## 5. Hai cấu hình mẫu độc lập

Các đoạn dependency dưới đây áp dụng vào **ứng dụng Spring Boot 3.3 có sẵn**. Chúng giả định Gradle đã dùng cơ chế quản lý dependency của Spring Boot và starter ứng dụng cần thiết đã được cấu hình.

Không ghép hai khối dependency vào cùng một runtime. Hãy chọn một phương án, rồi dùng bộ thuộc tính tương ứng.

### 5.1. Phương án A: OpenTelemetry + OTLP qua HTTP/protobuf

Phần `dependencies` của Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Cấu hình `application.properties` cho môi trường thử nghiệm có Collector chạy trên máy JVM đang sử dụng:

~~~properties
spring.application.name=checkout-service
management.tracing.sampling.probability=1.0
management.otlp.tracing.endpoint=http://localhost:4318/v1/traces
~~~

Hoặc YAML tương đương:

~~~yaml
spring:
  application:
    name: checkout-service

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Các điểm phải khớp:

- Chọn `micrometer-tracing-bridge-otel`.
- Nơi nhận phải mở đường OTLP/HTTP phù hợp.
- Với đường nhận traces theo quy ước OTLP/HTTP, URL chứa `/v1/traces`.
- Giá trị `localhost` được hiểu từ nơi JVM chạy. Nếu JVM ở container, cần dùng địa chỉ truy cập được từ container đó.
- Endpoint, TLS và xác thực của môi trường thật phải theo cấu hình của nơi nhận.

**Không bỏ endpoint với giả định rằng Boot 3.3.0 luôn có sẵn địa chỉ mặc định.** Thí nghiệm ở phần 8 xác nhận `OtlpProperties` trong phiên bản này có endpoint mặc định là `null`.

`management.otlp.tracing` là nhóm thuộc tính xuất trace qua OTLP. [Javadoc OtlpProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/tracing/otlp/OtlpProperties.html).

### 5.2. Phương án B: Brave + Zipkin

Phần `dependencies`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
}
~~~

Cấu hình tương ứng:

~~~properties
spring.application.name=checkout-service
management.tracing.sampling.probability=1.0
management.zipkin.tracing.endpoint=http://localhost:9411/api/v2/spans
~~~

Hoặc YAML tương đương:

~~~yaml
spring:
  application:
    name: checkout-service

management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

Endpoint này là API nhận span của Zipkin. Không dùng URL của trang tìm kiếm trace trên giao diện làm endpoint gửi dữ liệu.

Nếu muốn dùng OpenTelemetry với cùng nơi nhận Zipkin, thay **cặp dependency** bằng:

~~~groovy
implementation 'io.micrometer:micrometer-tracing-bridge-otel'
implementation 'io.opentelemetry:opentelemetry-exporter-zipkin'
~~~

Giữ Actuator và dùng nhóm thuộc tính `management.zipkin.tracing.*`. Việc thay bridge không buộc backend phải đổi cùng lúc, nhưng phải dùng exporter tương thích với bridge mới.

### 5.3. Lấy mẫu 1.0 dùng cho kiểm chứng

Giá trị `management.tracing.sampling.probability=1.0` giúp kiểm chứng các trace thử nghiệm bằng cách lấy mẫu toàn bộ trace gốc mới theo chính sách xác suất cục bộ.

Nó không đảm bảo mọi dữ liệu đều xuất hiện ở backend: quyết định lấy mẫu được kế thừa từ ngữ cảnh cha, observation bị chặn, lỗi đường gửi hoặc việc lọc ở Collector/backend vẫn có thể ảnh hưởng kết quả.

Đừng dùng việc đã đặt 1.0 làm bằng chứng rằng bridge/exporter đã hoạt động. Cần quan sát span thực tế ở phía nhận.

## 6. OTLP không chỉ là một số cổng

### 6.1. HTTP/protobuf và gRPC là hai đường truyền khác nhau

| Đường truyền OTLP | Cổng thường dùng | Cách nhận dạng |
| --- | --- | --- |
| OTLP/HTTP | 4318 | HTTP endpoint, chẳng hạn `/v1/traces` |
| OTLP/gRPC | 4317 | Dịch vụ gRPC, không phải HTTP POST tới đường dẫn trên |

Các giá trị cổng là quy ước mặc định của OTLP, không phải điều kiện bắt buộc cho mọi triển khai. Nơi nhận có thể được cấu hình cổng khác. [OTLP Specification](https://opentelemetry.io/docs/specs/otlp/).

Trong tích hợp đang xét, Spring Boot 3.3 tự cấu hình OTLP qua **HTTP/protobuf**. Nếu muốn dùng gRPC, cần cấu hình exporter gRPC phù hợp và hiểu cơ chế tự cấu hình nhường quyền cho cấu hình tùy biến. [Javadoc OtlpAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/tracing/otlp/OtlpAutoConfiguration.html).

Vì vậy, đổi:

~~~properties
management.otlp.tracing.endpoint=http://localhost:4317
~~~

không tự biến HTTP exporter thành gRPC exporter. Cổng mở và máy chủ truy cập được vẫn chưa đủ nếu giao thức không khớp.

### 6.2. Đúng loại tín hiệu

Cũng cần phân biệt:

~~~text
/v1/traces   → trace
/v1/metrics  → metric
/v1/logs     → log
~~~

`management.otlp.metrics.export.*` cấu hình xuất metric, còn `management.otlp.tracing.*` cấu hình xuất trace trong Spring Boot 3.3. Cấu hình OTLP metrics không thay thế việc chọn tracing bridge và trace exporter. [Spring Boot 3.3: Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

Collector nhận được metric không phải bằng chứng rằng trace đã được cấu hình đúng.

## 7. Truyền ngữ cảnh giữa dịch vụ là quyết định riêng

Exporter trả lời câu hỏi: **Span được gửi tới đâu, bằng định dạng nào?**

Cơ chế truyền ngữ cảnh trả lời câu hỏi: **Dịch vụ tiếp theo biết nó đang tham gia trace nào bằng cách nào?**

~~~text
Dịch vụ A ── yêu cầu HTTP và header ngữ cảnh ──> Dịch vụ B
    |                                               |
    +── xuất span tới Collector/backend             +── xuất span
~~~

Hai dịch vụ có thể dùng cùng backend nhưng tạo hai trace tách rời nếu ngữ cảnh không được truyền/đọc đúng.

- W3C Trace Context quy định các header như `traceparent` và `tracestate`. [W3C Trace Context](https://www.w3.org/TR/trace-context/).
- B3 có định dạng một header và nhiều header; đây là định dạng truyền ngữ cảnh, không phải giao thức xuất span tới Zipkin. [OpenZipkin: B3 Propagation](https://github.com/openzipkin/b3-propagation).

Vì vậy, không suy luận “Brave thì chỉ truyền B3”, “OpenTelemetry thì chỉ truyền W3C” hoặc “cùng xuất Zipkin thì chắc chắn nối được trace”. Phải kiểm tra cấu hình truyền ngữ cảnh của từng dịch vụ.

### 7.1. Ví dụ cấu hình chuyển tiếp có chủ đích

Trong Spring Boot 3.3.0, có thể cấu hình riêng định dạng nhận và phát:

~~~properties
management.tracing.propagation.consume=W3C,B3,B3_MULTI
management.tracing.propagation.produce=W3C
~~~

Ví dụ này cho phép nhận các định dạng được liệt kê và phát W3C. Phần 8 kiểm chứng đây cũng là các giá trị mặc định của đối tượng cấu hình trong bản 3.3.0 được dùng.

`management.tracing.propagation.type` là thuộc tính cấu hình chung cho cả nhận và phát; khi đặt nó, nó ghi đè các cấu hình chi tiết tương ứng. Không đặt đồng thời nhiều thuộc tính rồi bỏ qua quan hệ ưu tiên này.

Cần kiểm tra cả cách khởi tạo HTTP client. Trong ứng dụng Boot, dùng các builder được tự cấu hình như `RestTemplateBuilder`, `RestClient.Builder` hoặc `WebClient.Builder` để nhận việc tích hợp truyền ngữ cảnh. [Spring Boot 3.3: Propagating Traces](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.tracing.propagating-traces).

### 7.2. Đổi bridge cần kiểm chứng toàn tuyến

Khi chuyển một dịch vụ từ Brave sang OpenTelemetry hoặc ngược lại:

1. Loại bridge cũ khỏi runtime classpath.
2. Chọn lại exporter/reporter cho bộ thực thi mới.
3. Giữ hoặc thay endpoint theo đúng giao thức nhận.
4. Kiểm tra các dịch vụ lân cận đọc được ngữ cảnh mới.
5. Đối chiếu trace ID, quan hệ cha–con, tên dịch vụ và dữ liệu quan trọng.
6. Kiểm tra các phần mở rộng hoặc mã sử dụng API riêng của tracer cũ.

Mục tiêu kiểm chứng là một yêu cầu có thể đi qua các dịch vụ và vẫn truy tìm được đường xử lý, không chỉ là ứng dụng khởi động mà không báo lỗi.

## 8. Thí nghiệm Java: kiểm tra thuộc tính của Spring Boot 3.3.0

Thí nghiệm này xác minh **việc liên kết thuộc tính cấu hình (binding)** và các giá trị mặc định. Nó không khởi tạo bridge, exporter hay kết nối tới Collector/Zipkin.

Mã đã được biên dịch với `javac --release 17` và chạy bằng JDK 21, dùng các lớp cấu hình của Spring Boot **3.3.0**. Việc ghi rõ phiên bản giúp tránh mang giá trị mặc định của một phiên bản khác vào phần giải thích.

### 8.1. Tệp dependency cho thí nghiệm độc lập

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>trace-configuration-probe</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Không thêm bridge vào POM thí nghiệm vì mục tiêu ở đây là đọc các đối tượng cấu hình. Các mẫu ứng dụng gửi trace thực tế ở phần 5 vẫn cần bridge và exporter/reporter tương ứng.

### 8.2. Chương trình đầy đủ

Lưu tệp `TraceConfigurationProbe.java` cạnh `pom.xml`:

~~~java
import java.util.Map;

import org.springframework.boot.actuate.autoconfigure.tracing.TracingProperties;
import org.springframework.boot.actuate.autoconfigure.tracing.otlp.OtlpProperties;
import org.springframework.boot.actuate.autoconfigure.tracing.zipkin.ZipkinProperties;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

public class TraceConfigurationProbe {
    public static void main(String[] args) {
        OtlpProperties otlp = bind("management.otlp.tracing", OtlpProperties.class,
                Map.of("management.otlp.tracing.endpoint",
                        "http://collector:4318/v1/traces"));
        ZipkinProperties zipkin = bind("management.zipkin.tracing", ZipkinProperties.class,
                Map.of("management.zipkin.tracing.endpoint",
                        "http://zipkin:9411/api/v2/spans"));
        TracingProperties tracing = bind("management.tracing", TracingProperties.class,
                Map.of("management.tracing.sampling.probability", "1.0"));

        System.out.println("OTLP_DEFAULT_ENDPOINT=" + new OtlpProperties().getEndpoint());
        System.out.println("OTLP_CONFIGURED_ENDPOINT=" + otlp.getEndpoint());
        System.out.println("ZIPKIN_DEFAULT_ENDPOINT=" + new ZipkinProperties().getEndpoint());
        System.out.println("ZIPKIN_CONFIGURED_ENDPOINT=" + zipkin.getEndpoint());
        System.out.println("SAMPLING_PROBABILITY=" + tracing.getSampling().getProbability());
        System.out.println("PROPAGATION_PRODUCE=" + tracing.getPropagation().getProduce());
        System.out.println("PROPAGATION_CONSUME=" + tracing.getPropagation().getConsume());
    }

    private static <T> T bind(String prefix, Class<T> type, Map<String, String> values) {
        Binder binder = new Binder(new MapConfigurationPropertySource(values));
        return binder.bind(prefix, Bindable.of(type))
                .orElseThrow(() -> new IllegalStateException("Cannot bind " + prefix));
    }
}
~~~

Ba lần `bind(...)` dùng ba nguồn thuộc tính riêng cho OTLP, Zipkin và chính sách tracing chung. Đây là các dữ liệu thử nghiệm của bộ liên kết thuộc tính; không phải cấu hình kích hoạt đồng thời hai đường gửi span.

### 8.3. Lệnh chạy

PowerShell/Windows:

~~~powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out TraceConfigurationProbe.java
java -cp "out;lib/*" TraceConfigurationProbe
~~~

Linux/macOS:

~~~shell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
mkdir -p out
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out TraceConfigurationProbe.java
java -cp "out:lib/*" TraceConfigurationProbe
~~~

Lần đầu cần tải dependency nếu máy chưa có sẵn.

### 8.4. Stdout đã kiểm chứng

~~~text
OTLP_DEFAULT_ENDPOINT=null
OTLP_CONFIGURED_ENDPOINT=http://collector:4318/v1/traces
ZIPKIN_DEFAULT_ENDPOINT=http://localhost:9411/api/v2/spans
ZIPKIN_CONFIGURED_ENDPOINT=http://zipkin:9411/api/v2/spans
SAMPLING_PROBABILITY=1.0
PROPAGATION_PRODUCE=[W3C]
PROPAGATION_CONSUME=[W3C, B3, B3_MULTI]
~~~

Đọc kết quả:

- `OTLP_DEFAULT_ENDPOINT=null`: không dựa vào một endpoint tự có trong đối tượng cấu hình của bản này.
- `OTLP_CONFIGURED_ENDPOINT` và `ZIPKIN_CONFIGURED_ENDPOINT`: đúng khóa đã được liên kết vào đúng nhóm thuộc tính.
- `ZIPKIN_DEFAULT_ENDPOINT`: có đầy đủ đường API `/api/v2/spans`.
- `SAMPLING_PROBABILITY=1.0`: cấu hình lấy mẫu đã được đọc.
- `PROPAGATION_PRODUCE` và `PROPAGATION_CONSUME`: minh họa rằng định dạng phát và nhận có thể khác tập giá trị.

Không có dòng nào trong stdout chứng minh một span đã tới backend. Để xác minh điều đó cần bước kiểm tra ứng dụng thực ở phần tiếp theo.

## 9. Kiểm chứng cấu hình gửi trace trong ứng dụng

### 9.1. Kiểm tra dependency thực tế

Với Gradle:

~~~shell
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-tracing-bridge --configuration runtimeClasspath
~~~

Trên Windows có thể dùng `gradlew.bat`. Với dự án nhiều module, chạy task ở đúng Gradle project của ứng dụng, chẳng hạn thêm đường dẫn project trước tên task.

Với Maven:

~~~shell
mvn dependency:tree
~~~

Các điều cần tìm:

- Đúng một trong hai artifact bridge.
- Exporter/reporter thuộc đúng hàng của bảng tương thích.
- Không có bridge cũ bị kéo vào từ dependency bắc cầu.
- Phiên bản được quản lý nhất quán theo Spring Boot BOM.

Không lấy việc đã xóa một dòng trong build file làm bằng chứng rằng dependency đã biến mất khỏi runtime classpath.

Spring Boot cung cấp danh sách phiên bản được quản lý; khai báo các artifact thuộc phạm vi đó không cần tự gắn phiên bản rời rạc. [Spring Boot 3.3: Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.3/appendix/dependency-versions/coordinates.html).

### 9.2. Kiểm tra chuỗi dữ liệu

Thực hiện với một yêu cầu hoặc một thao tác thử nghiệm có thể nhận diện:

~~~text
Thao tác có observation/span?
        |
        v
Tracer tương ứng đã được cấu hình?
        |
        v
Span được lấy mẫu và kết thúc?
        |
        v
Exporter/reporter gửi đúng endpoint và giao thức?
        |
        v
Collector/backend nhận được?
        |
        v
Tìm được theo dịch vụ, thời gian và trace ID?
~~~

Nên kiểm tra từng chặng:

1. Có điểm đo thực sự được thực thi; thao tác chưa kết thúc có thể chưa được gửi.
2. Chính sách lấy mẫu và ngữ cảnh cha không loại dữ liệu thử nghiệm.
3. Exporter/reporter đúng với tracer đang dùng.
4. Nơi nhận đang mở đúng receiver và đường API.
5. DNS, địa chỉ, cổng, TLS và xác thực phù hợp môi trường chạy JVM.
6. Đã tính tới việc gửi theo lô; kết thúc tiến trình đột ngột có thể làm dữ liệu chưa kịp gửi.
7. Bộ lọc thời gian/tên dịch vụ trên giao diện không che dữ liệu vừa nhận.

Khi thử nghiệm chuyển bridge, dùng cùng một kịch bản yêu cầu để đối chiếu trước và sau. Trace ID được sinh động, không có giá trị cố định để chép làm stdout chuẩn.

### 9.3. Phân biệt các mức bằng chứng

| Bằng chứng quan sát được | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| Dependency có trong runtime classpath | Thư viện sẵn có để cấu hình | Exporter đã hoạt động đúng |
| Bean tracer tồn tại | Có bộ thực thi được nối vào ứng dụng | Mọi thao tác đều có span hoặc span đã được gửi |
| Log có trace ID | Có ngữ cảnh truy vết tại thời điểm log | Backend đã lưu trace |
| Exporter gửi thành công tới Collector | Chặng ứng dụng → Collector có bằng chứng hoạt động | Mọi chặng sau Collector đều thành công |
| Tìm được span/trace ở backend | Đường xuất của dữ liệu thử nghiệm đã tới đích | Mọi dịch vụ và mọi tình huống lỗi đều đúng |

Cách phân biệt này giúp tránh đổi dependency liên tục trong khi lỗi thực tế nằm ở endpoint, receiver hoặc cách tìm dữ liệu.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng/cấu hình | Điểm cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Cả hai bridge cùng có mặt | Dependency trực tiếp và bắc cầu | Giữ một bridge; loại đường kéo bridge còn lại |
| Brave kèm OpenTelemetry OTLP exporter nhưng không có đường xuất như mong muốn | Ghép sai tracer và exporter | Chọn OpenTelemetry + OTLP, hoặc thiết kế chặng Zipkin qua Collector |
| OpenTelemetry kèm Brave Zipkin reporter | Ghép sai bộ thực thi | Dùng `opentelemetry-exporter-zipkin` cho nhánh OpenTelemetry |
| OTLP gửi tới cổng gRPC bằng cấu hình HTTP | Giao thức của receiver | Giữ HTTP/protobuf đúng endpoint hoặc cấu hình exporter gRPC riêng |
| Zipkin endpoint là URL giao diện | Đường API nhận span | Dùng endpoint tương ứng `/api/v2/spans` |
| Cấu hình OTLP metrics nhưng không có trace | Nhầm loại tín hiệu | Kiểm tra nhóm `management.otlp.tracing.*` và tracing dependencies |
| Có trace ID trong log nhưng không thấy trace | Gửi dữ liệu, lấy mẫu, bộ lọc tìm kiếm | Kiểm tra từng chặng thay vì coi log là xác nhận đã lưu |
| Hai dịch vụ tạo hai trace rời nhau | Header và HTTP client | Kiểm tra consume/produce và tích hợp truyền ngữ cảnh |
| Sửa một phiên bản SDK rồi gặp lỗi liên kết lớp | Xung đột phiên bản | Trở về bộ phiên bản tương thích do BOM quản lý, rồi kiểm tra dependency tree |
| Đổi bridge nhưng dữ liệu bị trùng | Cơ chế đo cũ, agent hoặc pipeline cũ vẫn hoạt động | Xác định nơi sở hữu điểm đo và đường xuất trước khi thêm cấu hình mới |

Không giả định các biến cấu hình của OpenTelemetry Agent tự điều khiển toàn bộ tích hợp Micrometer do Boot quản lý. Cần xác định thành phần nào khởi tạo tracer/SDK/exporter và thành phần đó đọc nguồn cấu hình nào.

## 11. Bài tập lựa chọn và kiểm chứng

1. Nơi nhận chỉ mở OTLP/HTTP ở `4318/v1/traces`. Chọn bridge, exporter và khóa cấu hình endpoint. Giải thích vì sao chọn Brave rồi thêm OTLP exporter không đáp ứng cơ chế tự cấu hình đang xét.
2. Ứng dụng đang gửi Brave tới Zipkin, muốn chuyển sang OpenTelemetry nhưng giữ Zipkin. Chỉ ra cặp dependency phải thay và nhóm endpoint có thể giữ.
3. Backend có tên “OpenTelemetry Collector” nhưng receiver chỉ mở Zipkin. Xác định giao thức mà ứng dụng phải gửi ở chặng đầu; không lựa chọn chỉ theo tên sản phẩm.
4. Collector chỉ mở OTLP/gRPC ở 4317. Giải thích vì sao đổi cổng trong cấu hình OTLP/HTTP chưa đủ.
5. Dịch vụ A phát W3C nhưng B chỉ đọc B3. Giải thích việc cùng xuất về một backend không tự nối hai trace.
6. Chạy chương trình kiểm tra thuộc tính, sau đó nêu rõ điều gì đã được xác minh và điều gì vẫn cần thử với backend thật.
7. Kiểm tra runtime classpath của một ứng dụng hiện có và ghi lại một đường hoàn chỉnh: API chung → bridge → tracer → exporter/reporter → giao thức → nơi nhận.

Một lựa chọn hoàn chỉnh phải khớp cả bộ thực thi, cơ chế xuất và giao thức nhận. Việc chỉ nhớ tên OpenTelemetry hoặc Brave chưa đủ để tạo một đường truy vết có thể kiểm chứng.
