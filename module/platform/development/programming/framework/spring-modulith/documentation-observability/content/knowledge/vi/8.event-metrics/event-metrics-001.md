# Spring Modulith đăng ký metrics cho domain event

> **Chương:** Event metrics  
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.  
> **Trọng tâm:** Cơ chế đăng ký, nội dung, cách truy vấn và diễn giải đúng các counter đo **domain event publication** do Spring Modulith observability cung cấp.

## 1. Tại sao cần metrics cho domain event?

Trong một ứng dụng Spring Boot theo kiến trúc module, `order` có thể phát `OrderCompleted` để `inventory` cập nhật kho và `notification` gửi thông báo. Khi xử lý một đợt đặt hàng lớn, nhóm vận hành cần biết:

- Module nào đang phát event, và các loại event nào xuất hiện?
- Tần suất phát `OrderCompleted` có tăng đột biến hoặc giảm về 0?
- Số event được phát trong một khoảng thời gian có phù hợp với lưu lượng nghiệp vụ?
- Sau triển khai phiên bản mới, hệ thống còn phát loại event mà module khác phụ thuộc hay không?

Spring Modulith hỗ trợ đăng ký **Micrometer Counter** cho hoạt động công bố domain event. Counter giúp nhìn **lượng và xu hướng event được phát**, cả ở mức tổng hợp lẫn theo loại sự kiện. Đây là một lớp bằng chứng runtime bổ sung cho module graph và Actuator.

Tuy nhiên, counter publish **không phải** số lượng listener hoàn thành, số giao dịch commit, số message được broker nhận, hay số bản ghi nghiệp vụ cuối cùng đúng. Bài này luôn phân biệt những khái niệm đó trước khi diễn giải số liệu.

### Mục tiêu học tập

Sau khi học, bạn có thể:

1. Giải thích cơ chế Spring Modulith ghi nhận event publication bằng Micrometer.
2. Nhận diện đúng hai metric `module.events.published` và `module.events.published.<moduleIdentifier>.<simpleEventTypeName>`.
3. Hiểu tag `module.event.type`, `module.identifier`, `module.name` và lý do cần giới hạn cardinality.
4. Cấu hình dependency, Actuator, chạy một kịch bản phát event rồi đọc kết quả.
5. Tùy biến counter của một loại event bằng `ModulithEventMetricsCustomizer` mà không tạo tag không giới hạn.
6. Phân biệt event được phát với event được tiêu thụ hoặc hoàn tất, đồng thời đối chiếu metrics với trace, log và Event Publication Registry.

## 2. Domain event và phạm vi quan sát

### 2.1. Domain event là gì?

**Domain event** mô tả một sự kiện có ý nghĩa trong nghiệp vụ đã hoặc đang diễn ra: `OrderCompleted`, `InvoiceIssued`, `PaymentReceived`. Nó khác với thao tác kỹ thuật thông thường như một lời gọi nội bộ của framework, thay đổi trạng thái kết nối hay việc Spring tạo một bean.

Trong Spring Modulith, các module có thể cộng tác bằng cơ chế application event của Spring Framework:

~~~java
package com.acme.shop.order;

import java.util.UUID;

public record OrderCompleted(UUID orderId, Channel channel) {

    public enum Channel {
        WEB, MOBILE, PARTNER
    }
}
~~~

Kiểu `OrderCompleted` nằm ở API mà module tiêu thụ được phép tham chiếu, thay vì package nội bộ `order.internal`. Trường `orderId` giúp liên kết event với giao dịch nghiệp vụ; `channel` là enum có tập giá trị hữu hạn, sẽ dùng trong ví dụ tùy biến metric.

Một publisher đơn giản:

~~~java
package com.acme.shop.order;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class OrderManagement {

    private final ApplicationEventPublisher events;

    public OrderManagement(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void complete(UUID orderId, OrderCompleted.Channel channel) {
        // Trong ứng dụng thực: kiểm tra điều kiện và cập nhật order trong DB.
        events.publishEvent(new OrderCompleted(orderId, channel));
    }
}
~~~

Đoạn mã là **minh họa điểm publish**; một ứng dụng chạy thật cần persistence, xử lý giao dịch và kết nối các API nghiệp vụ tương ứng. `@Transactional` ở ví dụ không tự chứng minh đã có dữ liệu commit nếu phần ghi dữ liệu còn được lược bỏ.

### 2.2. Consumer có thể thuộc module khác

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.order.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderCompletedListener {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Thực hiện cập nhật kho dựa trên event.orderId().
    }
}
~~~

Một event có thể được nhiều listener xử lý. `@ApplicationModuleListener` của Spring Modulith hỗ trợ mô hình listener giao dịch và xử lý bất đồng bộ theo cơ chế của framework. Việc event được publish **không đồng nghĩa** mọi listener đã chạy hoặc chạy thành công.

### 2.3. Sự kiện nào được ghi nhận?

Tài liệu Spring Modulith mô tả việc đăng ký metrics cho các **domain event được phát trong ứng dụng** khi hỗ trợ observability đang hoạt động. Phạm vi thực tế còn tùy mô hình module, event được công cụ nhận diện và phiên bản đang dùng. Do đó:

- Không mặc định mọi Spring `ApplicationEvent` kỹ thuật đều là domain event cần có metric.
- Không mặc định một bản ghi mới xuất hiện ngay khi chỉ khai báo class event mà chưa phát event.
- Không mặc định mỗi lần HTTP request tạo đúng một event; nghiệp vụ có thể phát 0, 1 hoặc nhiều event.

Để kiểm tra phạm vi instrument của dự án, cần dùng một loại event nghiệp vụ có thật, phát qua luồng thực tế rồi kiểm tra meter phát sinh và các tag tương ứng.

## 3. Spring Modulith đăng ký những metric nào?

Theo tài liệu **Spring Modulith 2.2.0 – Production-ready Features**, hỗ trợ observability cung cấp **hai loại counter** cho domain event publication:

| Metric | Loại | Ý nghĩa | Nhãn phân loại |
|---|---|---|---|
| `module.events.published` | Counter | Ghi nhận các event publication được instrument; có thể tổng hợp hoặc lọc theo event/module | `module.event.type`, `module.identifier`, `module.name` |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter | Counter dành riêng cho một loại event trong module; có thể bổ sung tag nghiệp vụ | `module.identifier`, `module.name` và các tag custom có cấu hình |

Ví dụ nếu event `OrderCompleted` được nhận diện thuộc module `order`, tên counter chuyên biệt có thể là:

~~~text
module.events.published.order.OrderCompleted
~~~

Tên `order` là **module identifier** mà Spring Modulith đã xác định; nó không bắt buộc bằng tên class, tên thư mục trên filesystem hoặc tên bảng dữ liệu.

### 3.1. Counter tổng hợp `module.events.published`

Mục đích là biết **bao nhiêu lần phát event đã được công cụ ghi nhận**. Khi các label phân tách module và loại event, nhiều chuỗi thời gian có thể cùng thuộc một metric name.

Ví dụ minh họa:

| Module | Event type | Lượng publish quan sát được |
|---|---|---:|
| `order` | `OrderCompleted` | 12 |
| `order` | `OrderCancelled` | 3 |
| `payment` | `PaymentReceived` | 7 |
| **Tổng** | **Trong phạm vi quan sát** | **22** |

Số `22` chỉ là ví dụ cộng các lượt publish được quan sát. Nó **không** chứng minh 22 event đã được xử lý thành công hoặc 22 transaction đã commit.

**Chú ý:** Counter trong `MeterRegistry` là số tích lũy kể từ khi series được tạo trong một process/instance. Nó thường reset khi process khởi động lại. Muốn biết tốc độ 5 phút, dùng công cụ tính `rate` hoặc `increase` trên chuỗi thời gian theo cách backend hỗ trợ.

### 3.2. Counter riêng theo module và event type

Với `module.events.published.order.OrderCompleted`, dashboard có thể theo dõi trực tiếp event nghiệp vụ quan trọng. Vì mỗi event type có meter riêng, cũng có thể thêm các label **ít giá trị khác nhau** như kênh bán hàng khi thật sự cần thiết.

Counter này và counter tổng hợp là **hai cách biểu diễn cùng hoạt động publish ở hai mức phân loại**, không phải bằng chứng rằng sự kiện bị phát hai lần. **Không cộng trực tiếp hai counter đó để tính tổng số event**: một lượt publish được ghi vào cả hai loại metric theo cơ chế instrument.

## 4. Tag và ý nghĩa của chúng

### 4.1. Tag của counter tổng hợp

Theo tài liệu Spring Modulith:

| Tag | Ý nghĩa | Ví dụ diễn giải |
|---|---|---|
| `module.event.type` | Loại event được phát | Phân biệt `OrderCompleted` và `OrderCancelled` |
| `module.identifier` | Định danh application module | `order` |
| `module.name` | Tên hiển thị của module | `Order` |

Các tên trong bảng là **logical low-cardinality keys được tài liệu công bố**. Cách bộ exporter biểu diễn chúng thành nhãn, ví dụ khi xuất sang Prometheus, có thể bị chuẩn hóa theo quy ước backend.

Giá trị cụ thể của `module.event.type` phụ thuộc cách công cụ mô tả event trong phiên bản và mô hình thực tế; hãy xem `availableTags` trong Actuator hoặc series thực tế trước khi điền bộ lọc. Không tự giả định giá trị phải là tên Java đầy đủ hoặc simple class name.

### 4.2. Tag của counter riêng

Counter theo từng loại event có sẵn `module.identifier` và `module.name`. Tên meter đã mang phần nhận diện event type; customizer có thể bổ sung nhãn nghiệp vụ hữu hạn.

**Cần tránh high cardinality**: không đặt `orderId`, `customerId`, email, UUID, timestamp, trace ID hoặc giá trị văn bản tự do vào tag. Một giá trị mới có thể tạo một time series mới, gây tăng bộ nhớ, lưu trữ và chi phí truy vấn.

Ví dụ nên dùng:

- `channel=WEB|MOBILE|PARTNER`: enum hữu hạn.
- `region=APAC|EMEA|AMER`: nhóm vùng hữu hạn nếu phù hợp nghiệp vụ.
- `result=ACCEPTED|REJECTED`: nhóm trạng thái hữu hạn, chỉ khi metric có đúng ý nghĩa đó.

Ví dụ không nên dùng:

- `order.id=2574f1...` hoặc `customer.id=...`.
- `error.message=<nội dung lỗi tự do>`.
- `payment.amount=<giá trị liên tục>`.

Khi cần liên kết đến **một đơn hàng cụ thể**, hãy dùng log/trace có correlation và chính sách bảo vệ dữ liệu phù hợp.

## 5. Bật observability để metric được đăng ký

### 5.1. Thêm dependency

Trong ứng dụng Spring Boot đã dùng Spring Modulith và quản lý phiên bản tương thích bằng BOM, cách thuận tiện là dùng `spring-modulith-starter-insight`. Ví dụ Gradle:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Insight starter đưa vào các thành phần hỗ trợ Spring Modulith Actuator/observability và nền tảng Spring Boot Actuator của phiên bản tương ứng. Nếu muốn chỉ chọn phần quan sát, trong dòng Spring Modulith 2.2 có artifact chuyên biệt:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-observability-core'
    runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Ví dụ Maven với BOM đã quản lý phiên bản:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

**Hai cấu hình Gradle trên là các lựa chọn**, không phải chỉ dẫn phải khai báo đồng thời cả hai. Khi đã dùng Insight starter theo dependency tree phù hợp, không cần khai báo trùng `spring-modulith-observability-core`.

Nếu dự án dùng một dòng Spring Modulith 1.x/2.x khác, hãy kiểm tra artifact names, phiên bản Spring Boot và dependency tree thực tế. Đừng sao chép version cứng từ một bài viết khác vào dự án đang dùng BOM khác.

### 5.2. Cấu hình endpoint để kiểm tra

Ở môi trường thử nghiệm, cho phép truy cập endpoint metrics:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,modulith"
~~~

Khi ứng dụng Spring Boot web chạy trên `localhost:8080` và cấu hình access/security cho phép:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/modulith
~~~

Ba endpoint có nhiệm vụ khác nhau:

- `/actuator/health`: trạng thái health được các indicator đăng ký công bố.
- `/actuator/metrics`: liệt kê và xem meter Micrometer đã có trong registry.
- `/actuator/modulith`: metadata cấu trúc application modules của bản chạy; **không phải** nhật ký lượt phát event.

Spring Boot thường chỉ expose `health` qua HTTP theo mặc định; metric/modulith có thể yêu cầu explicit exposure. Với ứng dụng có Spring Security, management port, context path hoặc proxy, đường dẫn và kết quả HTTP phụ thuộc cấu hình hiện hành.

### 5.3. Kiểm tra trong runtime

Nếu application dùng Gradle, có thể kiểm tra sự hiện diện dependency trong `runtimeClasspath`:

~~~bash
# Trong repo Gradle, với ./gradlew tương ứng môi trường Unix.
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-modulith-observability-core \
  --configuration runtimeClasspath
~~~

Trên Windows, dùng `gradlew.bat` tương ứng. **Có artifact trong runtime classpath chỉ xác nhận điều kiện phụ thuộc**; không bảo đảm counter đã được đăng ký hoặc đã tăng. Muốn xác nhận, cần tạo event và đọc meter.

## 6. Quy trình thực hành: phát event và xem counter

### Bước 1 – Chọn kịch bản có thể tái lập

Chạy ứng dụng mẫu với một thao tác gọi `OrderManagement.complete(orderId, WEB)` có kiểm soát. Dùng dữ liệu thử và bảo đảm người dùng không đồng thời phát cùng loại event trên môi trường thử nghiệm.

Lưu ý: nếu thao tác bị retry hoặc app có nguồn publish khác, một request HTTP **có thể tương ứng nhiều publish**. Ghi log riêng để biết chính xác số lượt thực tế, không mặc định request = event.

### Bước 2 – Xem những meter hiện có

~~~bash
curl -s http://localhost:8080/actuator/metrics
~~~

Một payload kiểu minh họa:

~~~json
{
  "names": [
    "http.server.requests",
    "jvm.memory.used",
    "module.events.published",
    "module.events.published.order.OrderCompleted"
  ]
}
~~~

Danh sách thực tế dài/ngắn khác nhau theo ứng dụng, Micrometer registry và những event đã được instrument. Hai tên `module.events.published` chỉ xuất hiện khi cơ chế hỗ trợ đã thực sự ghi nhận chúng.

### Bước 3 – Xem counter tổng hợp

~~~bash
curl -s http://localhost:8080/actuator/metrics/module.events.published
~~~

Payload ví dụ:

~~~json
{
  "name": "module.events.published",
  "description": null,
  "baseUnit": null,
  "measurements": [
    { "statistic": "COUNT", "value": 4.0 }
  ],
  "availableTags": [
    { "tag": "module.identifier", "values": ["order"] },
    { "tag": "module.name", "values": ["Order"] },
    { "tag": "module.event.type", "values": ["order.OrderCompleted"] }
  ]
}
~~~

**Đây là dữ liệu minh họa, không phải response bắt buộc**. Trong thực tế, số `COUNT`, giá trị tag và metadata phụ thuộc số event ghi nhận, tên module và cơ chế xuất của phiên bản đang chạy.

### Bước 4 – Lọc theo tag được trả về

Ví dụ khi runtime trả `module.identifier=order`:

~~~bash
curl -G \
  --data-urlencode 'tag=module.identifier:order' \
  http://localhost:8080/actuator/metrics/module.events.published
~~~

Có thể thêm `tag=module.event.type:<giá trị-thực-tế>` sau khi quan sát `availableTags`. Dùng giá trị thực từ ứng dụng thay vì đoán định dạng event type.

Bộ lọc bằng tag giúp phân biệt event từ `order` và các module khác. **Số COUNT sau lọc là lượng phát được ghi nhận cho tổ hợp tag đó**, không phải số listener hoàn thành.

### Bước 5 – Xem counter dành riêng cho event

~~~bash
curl -s \
  http://localhost:8080/actuator/metrics/module.events.published.order.OrderCompleted
~~~

Tên đường dẫn trên là ví dụ với `moduleIdentifier=order` và `simpleEventTypeName=OrderCompleted`. Nếu tên khác, lấy chính xác tên từ kết quả `/actuator/metrics`.

Thử phát thêm một event cùng loại và so giá trị trước/sau. Nếu không có traffic đồng thời và không restart process, sự chênh lệch thường tương ứng số lượt event publication mà meter nhận được trong khoảng thử. **Counter tuyệt đối không phải số lượng đang chờ xử lý**.

## 7. Đếm đúng: publish, listener, commit, retry

Một domain event có thể được dùng theo luồng:

~~~mermaid
flowchart LR
    Order["order: phát OrderCompleted"]
    Count["Counter: module.events.published"]
    Registry["Event Publication Registry\n(nếu cấu hình)"]
    Inventory["inventory listener"]
    Notification["notification listener"]
    Outcome["Kết quả dữ liệu"]

    Order --> Count
    Order --> Registry
    Registry --> Inventory
    Registry --> Notification
    Inventory --> Outcome
~~~

Đây là sơ đồ **khái niệm**: registry chỉ tham gia khi được cấu hình và listener thuộc phạm vi theo dõi; event của ứng dụng cũng có thể đến listener bằng cơ chế khác. Các mũi tên không mô tả thứ tự transaction/commit chi tiết.

### 7.1. Một lượt publish có thể có nhiều listener

Ví dụ:

- `OrderCompleted` phát một lần.
- `inventory` có listener cập nhật tồn kho.
- `notification` có listener gửi email.
- `billing` có listener chuẩn bị hóa đơn.

Counter publish có thể tăng **một lần** cho event đó; số lượt gọi listener có thể là ba. Nếu một listener bị lỗi, counter vẫn phản ánh **publish**, không tự đổi thành “event failed”.

### 7.2. Publish chưa đồng nghĩa transaction commit

Khi publish nằm bên trong `@Transactional`, transaction có thể rollback sau khi lời gọi publish đã thực hiện. Tùy thời điểm instrumentation ghi nhận, counter có thể phản ánh lời gọi publish mà **không phải bằng chứng trạng thái cuối đã commit**.

Để kiểm tra một đơn hàng hoàn tất thật, cần xem transaction/data source, kết quả lưu dữ liệu, domain log và bằng chứng xử lý tương ứng.

### 7.3. Retry và duplicate publish là hai câu hỏi khác nhau

**Retry listener**: cùng event publication có thể được xử lý lại sau lỗi; counter **không mặc định tăng mỗi lần listener retry** nếu không có lần publish mới.

**Publish lại**: mã nghiệp vụ gọi `publishEvent(...)` thêm lần nữa (chẳng hạn retry toàn request), counter có thể tăng cho lần phát mới nếu được instrument.

**Nhiều instance**: mỗi instance có meter process riêng; backend tổng hợp đa instance cần xét label instance/pod, restart và khoảng thời gian đo. Đừng cộng các series đã được một recording rule tổng hợp sẵn rồi tính lại lần nữa.

### 7.4. Publication Registry bổ sung được gì?

Spring Modulith Event Publication Registry, nếu dùng backend như JDBC/JPA/MongoDB và cấu hình phù hợp, lưu thông tin publication gửi đến transactional listener được theo dõi. Tùy version, nó có thể phân biệt chờ xử lý, đang xử lý, hoàn tất, thất bại hoặc được resubmit.

| Câu hỏi | Nguồn chứng cứ phù hợp |
|---|---|
| Event được instrument phát ra bao nhiêu lần? | `module.events.published` và counter riêng |
| Event đã được giao đến transactional listener nào? | Registry khi đã cấu hình và listener thuộc phạm vi |
| Listener có chạy, lỗi hoặc hoàn tất không? | Registry lifecycle, log, trace/span listener |
| Giao dịch order có commit không? | Kết quả transaction và dữ liệu nghiệp vụ |
| Vì sao sự kiện có latency lớn? | Timer/span, log tương quan, thời gian publication/consume |
| Luồng chạy qua module nào? | Trace và module tags, đối chiếu module graph |

**Điểm nhấn:** Insight starter cho observability **không tự đồng nghĩa** backend Event Publication Registry bền vững đã được cấu hình. Cần kiểm tra dependency và trạng thái registry riêng.

## 8. Tùy biến metric theo loại domain event

Spring Modulith cung cấp SPI `ModulithEventMetricsCustomizer` để thêm tag hoặc thay đổi cách tạo **counter riêng theo event type**.

Theo Spring Modulith 2.2.0, nếu muốn sử dụng API tùy biến từ mã nguồn ứng dụng, cần thêm `spring-modulith-observability-api` vào compile classpath. Với Gradle và BOM có sẵn:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
}
~~~

Không khai báo `runtimeOnly` cho API mà mã Java cần import lúc biên dịch.

### 8.1. Ví dụ thêm tag có tập giá trị hữu hạn

Ở `OrderCompleted` đã định nghĩa `Channel` là enum gồm `WEB`, `MOBILE`, `PARTNER`. Ta có thể tách metric theo kênh:

~~~java
package com.acme.shop.config;

import com.acme.shop.order.OrderCompleted;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(
                OrderCompleted.class,
                (event, builder) -> builder.tags(
                        "channel",
                        event.channel().name().toLowerCase(java.util.Locale.ROOT)
                )
        );
    }
}
~~~

Ý nghĩa:

- Chỉ tùy biến counter dành cho `OrderCompleted`.
- Mỗi lần event được instrument, tag `channel` lấy từ enum có **ba giá trị**.
- Dashboard có thể so tốc độ event từ WEB, MOBILE và PARTNER, nếu backend đã xuất được các series.

**Không cần** thêm `orderId` vào tag để theo dõi một đơn hàng: điều đó tạo thêm rất nhiều series và có thể làm lộ dữ liệu không cần thiết. Nếu enum tăng không kiểm soát hoặc giá trị tag được lấy từ văn bản bên ngoài, vẫn phải đánh giá cardinality.

### 8.2. Customizer không phải callback “listener đã thành công”

`ModulithEventMetricsCustomizer` tham gia cấu hình counter cho event được ghi nhận. Nó **không** xác nhận:

- Có bao nhiêu listener đã xử lý xong.
- Có bao nhiêu retry thực sự xảy ra.
- Trạng thái kho/đơn hàng cuối cùng chính xác hay không.
- Event đã vào message broker hoặc được consumer bên ngoài ACK.

Nếu cần metric nghiệp vụ về completion hay SLA, hãy định nghĩa phép đo riêng tại điểm thật sự hoàn thành, hoặc sử dụng dữ liệu registry/lưu trữ và quy trình quan sát phù hợp. Không đổi tên counter `published` thành `processed` khi semantics vẫn là publish.

### 8.3. Tùy biến ObservationConvention khác gì?

Spring Modulith còn hỗ trợ `ModulithObservationConvention` để tùy biến observation ở cấp module interaction. Đây là **một extension point khác** với `ModulithEventMetricsCustomizer`.

| Extension point | Phạm vi |
|---|---|
| `ModulithEventMetricsCustomizer` | Counter riêng cho domain event publication |
| `ModulithObservationConvention` | Convention để mô tả observation của module entry, keys và tên trong phạm vi API tương ứng |
| Custom business counter của ứng dụng | Một sự kiện nghiệp vụ khác do nhóm tự định nghĩa; phải tự quy định nơi tăng |

Đừng thay đổi module-entry span convention chỉ để thêm một tag cho event counter nếu SPI chuyên biệt đã đáp ứng yêu cầu.

## 9. Đưa event metrics lên dashboard/alert

### 9.1. Từ Micrometer đến hệ thống lưu trữ

Một kiến trúc vận hành điển hình:

~~~mermaid
flowchart LR
    Publisher["Spring event publisher"]
      --> Modulith["Spring Modulith\nEvent instrumentation"]
    Modulith --> Registry["Micrometer MeterRegistry"]
    Registry --> Actuator["Actuator /metrics"]
    Registry --> Export["Prometheus/OpenTelemetry/monitoring export\n(nếu cấu hình)"]
    Export --> Dashboard["Grafana hoặc dashboard khác"]
    Export --> Alert["Cảnh báo theo rate/increase"]
~~~

`/actuator/metrics` là endpoint kiểm tra meter trong ứng dụng, **không phải** kho lưu trữ lịch sử nhiều tháng. Để quan sát xu hướng dài hạn, hệ thống cần cấu hình exporter/registry và backend lưu chuỗi thời gian.

Ví dụ cho Prometheus cần dependency `io.micrometer:micrometer-registry-prometheus`, cấu hình expose `prometheus` và hệ thống scrape phù hợp. Insight starter **không tự dựng Prometheus server**.

### 9.2. Query theo tốc độ thay vì chỉ giá trị tuyệt đối

Khi backend đã chuyển tên sang kiểu Prometheus (ví dụ `module_events_published_total`), có thể dùng mẫu query:

~~~promql
sum by (module_identifier) (
  rate(module_events_published_total[5m])
)
~~~

Đây là **mẫu minh họa**, không bảo đảm tên metric/label đúng tuyệt đối trong mọi exporter. Hãy xem output thật của `/actuator/prometheus` hoặc metric browser vì dấu chấm, dấu gạch, suffix `_total` và tag keys có thể được chuẩn hóa theo quy tắc backend.

- `rate(...[5m])`: ước lượng tốc độ tăng trung bình theo giây trong 5 phút, xử lý reset counter theo semantics Prometheus.
- `increase(...[15m])`: ước lượng số lượt tăng của counter trong 15 phút.
- `sum by (...)`: nhóm theo module sau khi đã xác nhận nhãn thực tế.

Lấy hiệu số đơn giản giữa hai mẫu counter liên tiếp có thể sai khi instance restart hoặc bị thay đổi tập pod; backend time series thường cung cấp hàm phù hợp.

### 9.3. Alert nào có ích?

Ví dụ tình huống có **kỳ vọng lưu lượng rõ ràng**:

- Tốc độ `OrderCompleted` giảm gần về 0 trong giờ hệ thống chắc chắn phải xử lý đơn.
- Số `PaymentReceived` tăng bất thường so với lượng giao dịch hợp lệ.
- Sau một lần deploy, dashboard chỉ còn event của module `order` mà mất event của `payment`.

Các alert phải được đối chiếu với **traffic nghiệp vụ**, cửa sổ thời gian, seasonality, batch job và thay đổi phiên bản. Một khoảng thời gian không có event có thể là trạng thái bình thường nếu không có đơn hàng nào hoàn tất.

Để cảnh báo consumer lỗi/tồn đọng, cần metric hoặc trạng thái **riêng cho listener/registry**; không chỉ dựa trên counter published.

## 10. Quan hệ với module graph, Actuator và tracing

### 10.1. Module graph nói về cấu trúc, metric nói về hoạt động

Giả sử module graph cho biết `inventory` tham chiếu `OrderCompleted` trong API của `order`:

~~~text
inventory --> order  (static dependency: uses OrderCompleted)
~~~

Khi chạy nghiệp vụ, luồng event lại có thể được kể theo hướng:

~~~text
order --publish OrderCompleted--> inventory (event flow)
~~~

Trong sơ đồ tĩnh, **consumer phụ thuộc vào kiểu event ở publisher**. Trong luồng runtime, **publisher phát event sang consumer**. Hai mũi tên khác chiều có thể đồng thời đúng vì khác ngữ nghĩa.

Counter `module.events.published` cung cấp bằng chứng rằng sự kiện được phát trong phạm vi quan sát, nhưng **không đủ để xác nhận cạnh runtime đã được thực thi đến consumer nào**.

### 10.2. Actuator `modulith` và `metrics` không cùng loại dữ liệu

| Nguồn | Câu hỏi trả lời | Giới hạn |
|---|---|---|
| `/actuator/modulith` | Bản deploy có module và dependency nào? | Không lưu lượt gọi/event |
| `/actuator/metrics` | Ứng dụng đã đăng ký meter gì và giá trị hiện tại? | Không cho trace của đơn hàng cụ thể |
| `/actuator/prometheus` | Metrics được xuất theo format scrape nào? | Cần registry và backend để có lịch sử |
| Trace/span | Trong một execution đã instrument, những bước nào chạy? | Sampling/instrumentation có thể khiến dữ liệu không đầy đủ |
| Event Publication Registry | Publication gửi tới listener trong phạm vi registry đã xử lý đến đâu? | Chỉ có nếu cơ chế registry phù hợp được bật |
| Dữ liệu nghiệp vụ | Order đã hoàn tất/tồn kho đã đổi đúng chưa? | Cần kiểm tra consistency và transaction |

### 10.3. Context propagation không phải event counter

Nếu listener chạy trên thread khác, trace có thể thiếu liên kết đến publisher khi `trace context` không được truyền theo executor. Counter publish **vẫn có thể tăng** dù trace thiếu span consumer.

Vì vậy khi phát hiện “metric có nhưng trace không có”, cần kiểm tra:

1. Event có thực sự đến listener không.
2. Tracing/exporter và sampling có hoạt động không.
3. Listener có nằm trong phạm vi instrument của Modulith không.
4. Context propagation qua thread hoặc executor đã được cấu hình chưa.
5. Mốc thời gian, build ID và correlation ID khi truy vấn có đúng không.

Không kết luận listener không chạy chỉ từ việc trace thiếu.

## 11. Tình huống thực hành: published tăng nhưng kho không đổi

Một hệ thống bán hàng nhận 100 lệnh hoàn tất đơn. Dashboard ghi nhận counter `module.events.published.order.OrderCompleted` tăng khoảng 100 trong khoảng thử. Tuy nhiên, tồn kho chỉ thay đổi cho 93 đơn.

**Câu hỏi điều tra:** 7 đơn còn lại bị mất event, listener lỗi, thao tác bị rollback, hay lỗi cập nhật dữ liệu?

| Bước | Kiểm tra | Có thể kết luận |
|---|---|---|
| 1 | Xác nhận 100 lệnh hoàn tất là 100 transaction commit thật, có order ID tương ứng | Tránh nhầm request với commit |
| 2 | Kiểm tra metric tag của module/event và sự khác biệt trước/sau | Có bao nhiêu lượt publish đã được instrument |
| 3 | Xem Event Publication Registry nếu đã bật | Publication đến từng transactional listener đang ở trạng thái nào |
| 4 | Xem trace/log có correlation và exception | Listener có được gọi, có retry hoặc lỗi ở bước nào |
| 5 | Kiểm tra hàng dữ liệu tồn kho và giao dịch cập nhật | Tác dụng nghiệp vụ thực sự có đúng không |
| 6 | Kiểm tra handling của duplicate event và idempotency | Có bỏ qua event hợp lệ hoặc xử lý lặp không |

**Ví dụ kết luận khác nhau:**

- **Registry có 7 publication thất bại:** nghi xử lý listener; tìm exception, recovery/retry và tính idempotent.
- **Registry báo hoàn tất cả 100 nhưng tồn kho chỉ đúng 93:** kiểm tra logic xử lý, transaction phụ, dữ liệu, tính nhất quán và những trường hợp bị bỏ qua.
- **Trên một instance metric tăng 100, nhưng request chạy nhiều pod:** cần truy vấn đủ instance và nhãn để tránh đọc lệch số lượng.
- **Traces chỉ thấy 60 event:** có thể do sampling hoặc propagation; không suy ra 40 event chưa phát.

**Không dùng phép tính `100 - 93 = 7` để tự động gắn nhãn “7 event bị mất”**. Hai con số đang mô tả **hai giai đoạn khác nhau** và có thể lệch vì nguyên nhân ngoài quá trình giao event.

## 12. Các lỗi cấu hình và đọc số liệu thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không có `module.events.published` khi vừa startup | Chưa có event được instrument hoặc hỗ trợ observability chưa hoạt động | Thực hiện publish thử, xem dependency/classpath và meter registry |
| Gọi `/actuator/metrics` trả 404 | Chưa expose endpoint, sai port/base path, chưa có Actuator | Kiểm tra `management.endpoints.web.exposure.include`, quyền access, Boot starter |
| Metric tồn tại nhưng giá trị thấp hơn số HTTP request | Không phải request nào cũng publish hoặc module/event khác nhau | Dùng log số lần publish và lọc đúng event type |
| Counter reset hoặc giảm sau deploy | Process/pod được khởi động lại, series mới | Dùng `rate`/`increase` và thông tin instance trong backend |
| Có metric tổng hợp nhưng thiếu counter event mong đợi | Khác module ID/tên event hoặc event chưa được instrument | Xem danh sách `/actuator/metrics`, dependency, module detection |
| Hai tên counter cùng tăng khi phát một event | Counter tổng hợp và counter riêng phản ánh hai mức đo | Không cộng cả hai thành số lượt event |
| Thêm tag `orderId` làm dashboard chậm | High cardinality tạo quá nhiều series | Loại tag định danh duy nhất, chuyển correlation sang log/trace |
| Counter published tăng nhưng listener lỗi | Metric publish không đo thành công consumer | Xem registry lifecycle, trace, log và dữ liệu cuối |
| Không có dữ liệu Prometheus dù Actuator có metric | Thiếu Prometheus registry/scrape config hoặc quyền truy cập | Kiểm tra `/actuator/prometheus` và backend |
| Metric có nhưng trace event thiếu | Tracing chưa cấu hình, sampling hoặc mất context | Kiểm tra tracer/exporter, async executor và context propagation |
| Số ở dashboard lệch Actuator của một JVM | Dashboard gộp nhiều instance hoặc khác thời gian/labels | Xác nhận query, instance, scrape interval và range |

## 13. Bài thực hành kiểm chứng

Dùng dự án Spring Boot có hai module `order` và `inventory`. Chuẩn bị một endpoint thử nghiệm gọi `OrderManagement.complete()` và một listener xử lý `OrderCompleted`. Chỉ chạy trong môi trường phát triển hoặc test:

1. Thêm Insight starter hoặc các dependency observability phù hợp và expose `metrics`.
2. Khởi động, ghi giá trị counter hiện tại sau khi có event; nếu meter chưa có, đó có thể là trạng thái bình thường trước lần publish đầu.
3. Phát lần lượt 3 event `OrderCompleted`, trong đó 2 event có `channel=WEB` và 1 event có `channel=MOBILE`.
4. Xem `module.events.published` với bộ lọc module/event đúng.
5. Xem counter riêng `module.events.published.order.OrderCompleted`.
6. Nếu đã cấu hình customizer, so các series theo `channel`. Không dùng `orderId` làm tag.
7. Cố ý cho một listener lỗi trong test, quan sát counter publish vẫn không tự là bằng chứng xử lý thành công.
8. Nếu có registry, đối chiếu publication state với metric; nếu có tracing, kiểm tra span listener và context propagation.
9. Khởi động lại ứng dụng, xác minh counter trong process mới có thể reset; dùng backend chuỗi thời gian nếu cần phân tích liên tục qua nhiều deploy.
10. Ghi kết quả kèm phiên bản Spring Modulith, build ID, số event phát, thời gian đo và phạm vi instance.

### Bảng ghi kết quả gợi ý

| Lần thử | Số publish dự kiến | Counter tổng hợp theo event | Counter riêng | Trạng thái listener |
|---|---:|---|---|---|
| Trước thử | 0 mới phát | Ghi baseline | Ghi baseline | Chưa thực thi kịch bản |
| Sau 2 event WEB | +2 | Đối chiếu độ tăng | Đối chiếu độ tăng | Xem log/registry |
| Sau 1 event MOBILE | +1 | Đối chiếu độ tăng | Đối chiếu độ tăng | Xem log/registry |
| Sau khi gây lỗi listener | +1 nếu có publish mới | Vẫn đo lượt publish | Vẫn đo lượt publish | Có thể failed hoặc cần retry |

Các ô trên là **kỳ vọng theo tình huống kiểm soát**, không phải giá trị tuyệt đối áp dụng cho mọi ứng dụng. Nếu instrument không nhận diện được event hoặc listener không thuộc registry, hãy ghi rõ kết quả và nguyên nhân thay vì kết luận hệ thống đã chạy đúng.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `module.events.published` tăng thêm 10. Có thể nói có 10 listener xử lý thành công không?

**Trả lời:** Không. Metric phản ánh các lượt công bố event được instrument. Một event có thể có nhiều listener, listener thất bại hoặc chưa được kích hoạt.

**Câu 2.** Hai counter `module.events.published` và `module.events.published.order.OrderCompleted` cùng tăng một đơn vị sau một event. Có phải event bị phát hai lần?

**Trả lời:** Không. Đây là hai counter ở hai mức phân loại khác nhau được ghi cho cùng hoạt động publish. Cần log/trace/registry để xác định publish có bị lặp thật hay không.

**Câu 3.** Có nên dùng `orderId` làm metric tag để dễ tìm một đơn hàng cụ thể?

**Trả lời:** Không nên. Đây là giá trị cardinality cao, sẽ tạo lượng series tăng theo đơn hàng. Dùng correlation trong log/trace cho việc theo dõi từng đơn.

**Câu 4.** `/actuator/modulith` và `/actuator/metrics` khác nhau ở đâu?

**Trả lời:** Modulith endpoint công bố metadata cấu trúc module; metrics endpoint cung cấp các meter runtime đã đăng ký. Graph tĩnh không chứng minh event đã được phát.

**Câu 5.** Listener retry một event cũ ba lần; counter publish có bắt buộc tăng ba lần không?

**Trả lời:** Không. Retry listener và publish mới là hai hoạt động khác nhau. Counter publish không bắt buộc tăng nếu không phát event mới.

**Câu 6.** Counter publish tăng, nhưng trace không có span listener. Kết luận listener chưa chạy có hợp lý không?

**Trả lời:** Chưa đủ căn cứ. Cần kiểm tra phạm vi instrument, tracing backend, sampling, async context propagation, log và registry.

**Câu 7.** Muốn thêm tag `channel` hữu hạn vào metric theo event type, nên dùng extension point nào?

**Trả lời:** `ModulithEventMetricsCustomizer`, với API artifact trong compile classpath của ứng dụng và giá trị tag được kiểm soát.

## 15. Ghi nhớ

- Spring Modulith đăng ký **hai nhóm counter** để đo domain event publication: `module.events.published` và counter theo `moduleIdentifier`/`simpleEventTypeName`.
- Counter tổng hợp có tag loại event, module identifier và module name; counter riêng có thể bổ sung tag nghiệp vụ bằng `ModulithEventMetricsCustomizer`.
- **Event được publish không đồng nghĩa event đã được xử lý thành công**, transaction đã commit hoặc dữ liệu cuối đã đúng.
- Không cộng counter tổng hợp với counter riêng để ra tổng lượt publish, và không dùng ID riêng lẻ làm metric label.
- Dùng Actuator để kiểm tra meter hiện có; cần backend/exporter phù hợp để xem lịch sử, tốc độ và alert.
- Đối chiếu **module graph/Actuator** với **metrics/tracing/registry** theo đúng build, môi trường, thời gian và mục tiêu điều tra.

## Tài liệu tham khảo

1. [Spring Modulith – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Hai counter domain event, low-cardinality keys và `ModulithEventMetricsCustomizer`.
2. [Spring Modulith – Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — Event publication, transactional listener và Event Publication Registry.
3. [Spring Modulith – Observability API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/package-summary.html) — SPI `ModulithEventMetricsCustomizer` và các lớp hỗ trợ.
4. [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Actuator metrics, Micrometer registry và export.
5. [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — Endpoint exposure/access.
6. [Spring Boot – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — Micrometer Observation và liên hệ metrics/tracing.
7. [Micrometer – Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html) — Counter, time series và tag cardinality.

