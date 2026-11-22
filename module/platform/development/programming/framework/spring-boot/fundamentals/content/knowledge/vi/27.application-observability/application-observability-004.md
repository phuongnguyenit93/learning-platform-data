# health, info và ý nghĩa dữ liệu được công bố

Một ứng dụng Spring Boot chạy được không nhất thiết đã **sẵn sàng phục vụ**, và một endpoint HTTP trả về `200 OK` cũng không tự chứng minh toàn bộ hệ thống đang khỏe mạnh. Trong thực tế, đội vận hành cần biết hai nhóm thông tin khác nhau:

- **Ứng dụng đang ở trạng thái nào?** Nó có thể hoạt động, có nên nhận request mới, hay đang gặp vấn đề với một phụ thuộc bắt buộc?
- **Ứng dụng này là bản triển khai nào?** Nó thuộc dịch vụ nào, đang chạy phiên bản nào, build từ bản mã nào, và có tài liệu vận hành ở đâu?

Spring Boot Actuator cung cấp hai endpoint thường được nhắc đến để giải quyết hai nhu cầu đó:

- **`health`** — báo cáo trạng thái sức khỏe của ứng dụng và các thành phần được cấu hình tham gia đánh giá.
- **`info`** — công bố metadata có chủ đích về ứng dụng, chẳng hạn tên dịch vụ, phiên bản build hoặc thông tin hỗ trợ vận hành.

Bài học thuộc **Spring Boot Fundamentals → Quan sát ứng dụng**, với trọng tâm không chỉ là bật endpoint mà còn hiểu **ý nghĩa của dữ liệu được công bố**, cách diễn giải nó trong giám sát, mức độ tin cậy của từng tín hiệu và ranh giới bảo mật khi đưa thông tin ra HTTP.

## 1. Health và info trả lời hai câu hỏi khác nhau

Giả sử một dịch vụ xử lý đơn hàng có hai phản hồi:

~~~http
GET /actuator/health

HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

Và:

~~~http
GET /actuator/info

HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{
  "app": {
    "name": "orders-api",
    "description": "Dịch vụ xử lý đơn hàng"
  },
  "build": {
    "version": "1.4.2"
  }
}
~~~

Hai response mang ý nghĩa hoàn toàn khác nhau:

| Câu hỏi | `health` | `info` |
|---|---|---|
| Có đang gặp tình trạng không sẵn sàng không? | Có thể cung cấp tín hiệu | Không phải mục đích chính |
| Nên điều hướng request mới vào instance này không? | Có thể dùng readiness health group | Không |
| Process có dấu hiệu lỗi nghiêm trọng cần restart không? | Có thể dùng liveness probe phù hợp | Không |
| Đây là phiên bản nào? | Không phải thông tin chính | Có thể trả metadata build |
| Có thể hiển thị tên hoặc mô tả dịch vụ không? | Không cần | Có |
| Có thể chứa thông tin nội bộ nhạy cảm không? | Có, nếu mở chi tiết không kiểm soát | Có, nếu công bố metadata quá rộng |
| HTTP 200 chứng minh toàn bộ nghiệp vụ thành công? | Không | Không |

Một `info` response hoàn chỉnh vẫn có thể được trả trong thời gian database ngừng hoạt động. Ngược lại, một response `health` là `UP` cũng không cho biết chính xác ứng dụng đang chạy commit nào nếu không có metadata tương ứng.

**Nguyên tắc:** dùng `health` để đánh giá tình trạng phục vụ theo những điều kiện được định nghĩa rõ; dùng `info` để **nhận diện và giải thích ứng dụng**, không phải làm hệ thống kiểm tra sống/chết.

## 2. Spring Boot Actuator là gì?

**Spring Boot Actuator** là tập hợp các khả năng hỗ trợ vận hành và quan sát ứng dụng, bao gồm các endpoint về health, info, metrics, loggers và nhiều loại thông tin khác tùy dependency và cấu hình.

Trong ứng dụng web dùng HTTP, endpoint thường có đường dẫn bắt đầu bằng:

~~~text
/actuator
~~~

Ví dụ:

~~~text
/actuator/health
/actuator/info
/actuator/health/liveness
/actuator/health/readiness
~~~

Những đường dẫn phụ thuộc vào phiên bản, endpoint được bật hay không, cấu hình exposure, health group và đường dẫn management được tùy chỉnh. Không được suy luận rằng tất cả endpoint trên luôn sẵn có sau khi thêm một dependency.

Một ứng dụng Spring Boot bình thường có thể chạy hoàn toàn không cần Actuator. Nhưng khi cần triển khai qua container orchestration, load balancer hoặc hệ thống quan sát tập trung, Actuator giúp cung cấp những tín hiệu vận hành có cấu trúc và nhất quán.

### Thêm dependency bằng Maven

Trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Ví dụ này giả định project đã dùng Spring Boot dependency management để chọn phiên bản starter phù hợp.

### Thêm dependency bằng Gradle

Groovy DSL trong `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Sau khi có starter và ứng dụng được cấu hình phù hợp, Spring Boot auto-configuration sẽ đăng ký các thành phần Actuator tương ứng.

**Actuator không tự biến mọi thông tin vận hành thành dữ liệu công khai.** Việc một endpoint tồn tại trong context khác với việc endpoint đó được expose qua HTTP và người gọi có quyền truy cập.

## 3. Ba lớp quyết định một endpoint có thể truy cập được hay không

Khi một người gọi `GET /actuator/info` và nhận 404 hoặc 403, chưa thể kết luận endpoint không được Spring Boot hỗ trợ. Cần phân biệt ba lớp:

1. **Endpoint enabled:** endpoint có được kích hoạt bởi ứng dụng không?
2. **Endpoint exposed:** endpoint có được đưa ra công nghệ truy cập đang dùng, chẳng hạn HTTP, không?
3. **Endpoint authorized:** request có vượt qua cơ chế xác thực/phân quyền không?

Sơ đồ:

~~~text
Actuator endpoint
      |
      v
Được bật (enabled)?
      | Không -> Không khả dụng
      v
Được expose qua HTTP?
      | Không -> Không tìm thấy từ HTTP
      v
Có quyền truy cập?
      | Không -> 401/403 hoặc hành vi do security quy định
      v
Endpoint xử lý request và trả dữ liệu
~~~

Ví dụ một cấu hình tường minh:

~~~properties
management.endpoints.web.exposure.include=health,info
~~~

Nó chỉ định hai endpoint được expose qua HTTP theo cấu hình Actuator. Dòng này **không tự thiết lập cơ chế xác thực/phân quyền**; khi cần bảo vệ `info` hoặc các endpoint quản trị khác, phải kết hợp cấu hình security phù hợp.

Trong nhiều cấu hình Spring Boot thông dụng, chỉ `health` được expose qua HTTP theo mặc định. Không nên giả định `info` hoặc những endpoint khác công khai nếu chưa cấu hình. Giá trị mặc định có thể thay đổi theo bản Spring Boot; luôn kiểm tra phiên bản và cấu hình dự án đang chạy.

### Đường dẫn quản trị mặc định

Một ví dụ đơn giản:

~~~properties
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,info
~~~

Nếu web server sử dụng cổng 8080 và không đổi context path, có thể thử:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/info
~~~

Nếu ứng dụng đổi `management.server.port`, servlet context path, web base path hoặc security rule, URL thực tế sẽ khác. Không nên cố định URL trong hệ thống giám sát mà không đối chiếu cấu hình triển khai.

## 4. Response cơ bản của health

Endpoint `health` cung cấp một trạng thái tổng hợp của những contributor tham gia kiểm tra.

Response tối giản thường có dạng:

~~~json
{
  "status": "UP"
}
~~~

Trạng thái này cho biết các tín hiệu mà **health endpoint đang đánh giá** được tổng hợp thành `UP`. Nó **không bảo đảm**:

- Mọi HTTP endpoint nghiệp vụ đều hoạt động.
- Tất cả database, cache, queue hoặc API ngoài đã được kiểm tra.
- Dữ liệu đã được đồng bộ mới nhất.
- Ứng dụng sẽ tiếp tục khỏe mạnh trong vài phút sau.
- Instance đó đang nhận traffic qua load balancer.
- Không có bug logic trong bất kỳ method Java nào.

**`UP` là kết quả của một bộ kiểm tra tại thời điểm request, theo cấu hình hiện tại.** Muốn diễn giải đúng phải biết những thành phần nào được đưa vào kết quả tổng hợp.

### Những trạng thái thường gặp

Spring Boot hỗ trợ các trạng thái health phổ biến:

| Trạng thái | Ý nghĩa khái quát |
|---|---|
| `UP` | Contributor được coi là đang hoạt động theo phép kiểm tra của nó |
| `DOWN` | Contributor hoặc điều kiện bị xem là không hoạt động |
| `OUT_OF_SERVICE` | Thành phần/ứng dụng được xác định chưa thể hoặc không nên phục vụ |
| `UNKNOWN` | Không có đủ thông tin để đưa ra kết luận rõ ràng |

Ứng dụng có thể định nghĩa trạng thái tùy chỉnh, nhưng nếu tạo thêm status mới, cần xem xét cả thứ tự tổng hợp và ánh xạ HTTP status để hệ thống giám sát hiểu đúng.

Không nên coi `UNKNOWN` là lỗi hay thành công chắc chắn; đó là tín hiệu cần được diễn giải theo chính sách của ứng dụng.

## 5. Health status và HTTP status là hai lớp thông tin

Ví dụ khi database bắt buộc không thể kết nối:

~~~http
GET /actuator/health

HTTP/1.1 503 Service Unavailable
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"DOWN"}
~~~

Trong cấu hình Spring Boot thông thường:

- `UP` thường được ánh xạ thành HTTP `200 OK`.
- `DOWN` và `OUT_OF_SERVICE` thường được ánh xạ thành HTTP `503 Service Unavailable`.
- Các trạng thái khác thường có ánh xạ mặc định, trừ khi người phát triển cấu hình lại.

Đây là lý do load balancer hoặc orchestrator có thể đọc tín hiệu HTTP của health endpoint mà không cần phân tích toàn bộ nội dung JSON.

Tuy nhiên, có thể **tùy chỉnh** ánh xạ status → HTTP code. Vì vậy, khi thiết kế probe, không nên dựa vào một phép thử duy nhất mà không kiểm tra hành vi endpoint thực tế.

### Vì sao response 503 lại hữu ích?

Trong bối cảnh readiness, HTTP 503 có thể là tín hiệu để bộ điều phối tạm ngừng gửi request mới đến instance. Điều này khác với việc JVM đã dừng; process có thể vẫn chạy để chờ một phụ thuộc phục hồi.

Trong bối cảnh liveness, lặp lại lỗi kéo dài có thể khiến orchestrator quyết định restart process. Hai mục đích khác nhau cần hai chính sách kiểm tra khác nhau.

**Không phải mọi lần health 503 đều có nghĩa phải restart.**

## 6. Health contributor và HealthIndicator

Spring Boot Actuator có thể thu thập tình trạng từ nhiều **health contributor**. Một contributor đơn giản thường được triển khai bằng interface `HealthIndicator`:

~~~java
package com.example.observation;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class SampleHealthIndicator implements HealthIndicator {

    @Override
    public Health health() {
        return Health.up().build();
    }
}
~~~

`health()` trả về một đối tượng `Health` có status và có thể kèm detail.

Ví dụ một contributor kiểm tra tình trạng sẵn sàng của một dịch vụ:

~~~java
@Override
public Health health() {
    boolean available = checkRequiredResource();

    if (available) {
        return Health.up().build();
    }

    return Health.down()
            .withDetail("reason", "required-resource-unavailable")
            .build();
}
~~~

`checkRequiredResource()` là phương thức minh họa do ứng dụng định nghĩa. Đoạn code mô tả cơ chế trả về Health, không tự cung cấp cách kiểm tra mạng, database hay business state.

### Health có thể tổng hợp nhiều thành phần

Nếu một ứng dụng có contributor cho disk space, database và catalog, trạng thái tổng hợp có thể như:

~~~text
Overall health
   |
   +-- diskSpace: UP
   |
   +-- db: UP
   |
   +-- catalog: DOWN
   |
   v
Overall status: DOWN
~~~

Cách tổng hợp phụ thuộc group, những contributor được đưa vào group và status aggregator được cấu hình. Một contributor không nên bị hiểu là “đại diện cho toàn bộ ứng dụng” nếu vẫn còn những điều kiện quan trọng khác chưa được đánh giá.

## 7. Các health indicator được Spring Boot cung cấp

Khi có dependency và cấu hình phù hợp, Spring Boot có thể tự đăng ký những health indicator thường gặp:

| Nhóm | Ví dụ khả năng kiểm tra | Điều cần hiểu |
|---|---|---|
| `diskSpace` | Dung lượng đĩa khả dụng | Không phản ánh dữ liệu trên đĩa có đúng nghiệp vụ hay không |
| `db` | Kết nối/khả năng phản hồi cơ bản của datasource | Không bảo đảm mọi query hay migration đúng |
| `redis` | Redis có phản hồi ở mức kiểm tra được cấu hình | Không bảo đảm cache đã nạp đủ |
| `mongo` | Tình trạng kết nối MongoDB | Không chứng minh mọi collection đang nhất quán |
| `rabbit` | Khả năng kiểm tra RabbitMQ | Không đồng nghĩa mọi queue đều tiêu thụ bình thường |
| `ping` | Một thành phần health cơ bản, nếu được bật | Không kiểm tra các nghiệp vụ của ứng dụng |
| `livenessState` | Liveness theo ApplicationAvailability | Chỉ phản ánh trạng thái vòng đời được Spring Boot công bố |
| `readinessState` | Readiness theo ApplicationAvailability | Không tự biết mọi tác vụ chuẩn bị bất đồng bộ |

Không phải mọi indicator trên đều xuất hiện trong mọi dự án. Danh sách thực tế phụ thuộc starter, thư viện trên classpath, beans, phiên bản và cấu hình.

**Kiểm tra “database có kết nối được không” khác với “dịch vụ thanh toán hoàn thành giao dịch được không”.** Mỗi health indicator chỉ có phạm vi bảo đảm đúng bằng logic mà nó thực hiện.

### Không nên đưa tất cả dependency vào mọi health group

Nếu một API vẫn có thể phục vụ request thông thường khi công cụ analytics hoặc hệ thống email phụ trợ bị mất kết nối, đánh dấu toàn bộ service `DOWN` chỉ vì dependency tùy chọn có thể gây gián đoạn không cần thiết.

Hãy xác định rõ dependency nào **thật sự bắt buộc** cho trạng thái được công bố, đặc biệt là readiness.

## 8. Readiness và liveness giải quyết hai bài toán vận hành khác nhau

Một trong những ứng dụng thực tế quan trọng nhất của `health` là cung cấp probe cho hệ thống điều phối như Kubernetes.

Hai thuật ngữ chính:

**Liveness:** ứng dụng có còn trong trạng thái có thể tiếp tục chạy hay không?

**Readiness:** instance hiện tại có nên nhận request mới hay không?

Ví dụ:

~~~text
Application instance
        |
        +-----------------------+
        |                       |
        v                       v
   Liveness probe          Readiness probe
        |                       |
        v                       v
Process còn vận hành?    Đã nên nhận traffic?
        |                       |
        v                       v
Có thể dùng cho       Có thể dùng cho
quyết định restart    quyết định routing
~~~

Một instance có thể **live nhưng chưa ready**:

- Web server vừa mở cổng, công việc chuẩn bị vẫn đang chạy.
- Cache bắt buộc chưa nạp xong.
- Một dependency thiết yếu chưa phục hồi, nhưng ứng dụng có thể retry mà không cần restart.
- Instance đang tạm từ chối traffic trong giai đoạn dừng có quản lý.

Ngược lại, nếu ứng dụng rơi vào trạng thái nội tại không thể phục hồi, liveness có thể là tín hiệu thích hợp cho việc restart theo chính sách hệ thống.

### Vì sao không nên đưa database vào liveness mặc định?

Giả sử toàn bộ database bị mất kết nối trong vài phút. Nếu liveness probe của mọi instance phụ thuộc trực tiếp vào database, orchestrator có thể liên tục restart hàng loạt instance chỉ vì database không sẵn sàng.

Điều đó làm sự cố rộng thêm:

~~~text
Database outage
     |
     v
Mọi app instance báo liveness DOWN
     |
     v
Orchestrator restart hàng loạt
     |
     v
Restart storm và tăng tải khi database phục hồi
~~~

Trong nhiều kiến trúc, database nên là điều kiện **readiness** nếu mọi request bắt buộc cần nó, thay vì là điều kiện liveness. Tuy nhiên, cả readiness cũng cần thiết kế thận trọng để tránh tạo hiệu ứng lan truyền hoặc loại bỏ toàn bộ capacity không cần thiết.

## 9. Bật liveness và readiness health groups

Trong Spring Boot, có thể cấu hình Actuator probes để truy cập những nhóm health theo trạng thái vòng đời:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Khi các nhóm được kích hoạt và web environment hỗ trợ, đường dẫn thường là:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Ví dụ:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Phản hồi thường ở dạng:

~~~json
{"status":"UP"}
~~~

hoặc:

~~~json
{"status":"DOWN"}
~~~

Việc có nhận được `UP` hay không phụ thuộc thời điểm startup/shutdown và trạng thái được công bố, không phải một bảo đảm cho mọi lần gọi.

Kubernetes environment có thể kích hoạt hỗ trợ probes tự động tùy phiên bản và môi trường. Cấu hình `management.endpoint.health.probes.enabled=true` làm chủ đích rõ ràng khi muốn tự thử nghiệm ngoài Kubernetes.

### Chỉ riêng readinessState đã đủ chưa?

Trong luồng startup bình thường, Spring Boot công bố các trạng thái availability như:

~~~text
Application bắt đầu khởi động
     |
     v
Readiness: REFUSING_TRAFFIC
     |
     v
Context refresh và chạy runners
     |
     v
ApplicationReadyEvent
     |
     v
Readiness: ACCEPTING_TRAFFIC
~~~

Nhưng nếu một `ApplicationRunner` chỉ **submit task nạp cache vào executor rồi trả về ngay**, Spring Boot có thể công bố `ACCEPTING_TRAFFIC` khi task vẫn đang chạy.

Vì vậy, một readiness group chỉ gồm `readinessState` có thể chưa đủ cho ứng dụng có điều kiện nghiệp vụ bất đồng bộ. Cần bổ sung health contributor riêng phản ánh đúng điều kiện đó.

## 10. Cấu hình health group theo nhu cầu ứng dụng

Actuator cho phép định nghĩa hoặc điều chỉnh nhóm health. Ví dụ đưa một indicator custom tên `catalog` vào readiness:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,catalog
~~~

Điều kiện logic cần đạt:

~~~text
Spring Boot readinessState
           AND
Catalog đã chuẩn bị hoàn tất
           |
           v
/actuator/health/readiness -> UP
~~~

Nếu catalog chưa sẵn sàng, readiness group có thể trả `DOWN` mặc dù Boot đã công bố `ReadinessState.ACCEPTING_TRAFFIC`.

Một health group cũng có thể dùng để phục vụ nhu cầu chuyên biệt, ví dụ nhóm cho một endpoint tích hợp nội bộ. Nhưng cần phân biệt:

- **Health tổng thể `/actuator/health`:** nhìn theo contributor/group mặc định.
- **Liveness group:** kiểm tra tình trạng sống còn nội tại.
- **Readiness group:** kiểm tra điều kiện nhận traffic.
- **Custom group:** một tập health contributor do ứng dụng định nghĩa.

Không nhất thiết mọi group có cùng thành phần và cùng status.

### Cấu hình liveness độc lập

Trong nhiều hệ thống, liveness group nên dựa chủ yếu vào `livenessState`:

~~~properties
management.endpoint.health.group.liveness.include=livenessState
~~~

Việc cố tình đưa network dependency vào liveness nên được đánh giá cẩn thận vì sự cố bên ngoài không nhất thiết được xử lý bằng cách restart app.

## 11. Viết HealthIndicator cho điều kiện chuẩn bị riêng

Giả sử API đơn hàng phải nạp catalog vào bộ nhớ trước khi nhận traffic. Ta muốn readiness báo chưa đạt trong thời gian nạp.

File `CatalogHealthIndicator.java`:

~~~java
package com.example.observation;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("catalogHealthIndicator")
public class CatalogHealthIndicator implements HealthIndicator {

    private final AtomicBoolean ready = new AtomicBoolean(false);

    public void markReady() {
        ready.set(true);
    }

    public void markNotReady() {
        ready.set(false);
    }

    @Override
    public Health health() {
        if (ready.get()) {
            return Health.up()
                    .withDetail("phase", "READY")
                    .build();
        }

        return Health.down()
                .withDetail("phase", "PREPARING")
                .build();
    }
}
~~~

Giải thích:

- Ban đầu `ready=false` nên indicator trả `DOWN`.
- Khi công việc chuẩn bị hoàn thành, gọi `markReady()`.
- Nếu có điều kiện khiến service không còn đủ năng lực phục vụ, có thể gọi `markNotReady()` theo chính sách ứng dụng.
- `AtomicBoolean` giúp trạng thái được cập nhật an toàn giữa thread chạy công việc và thread phục vụ health request.
- Tên bean `catalogHealthIndicator` thường được Actuator ánh xạ thành contributor name `catalog`.

Đây là một mô hình tối giản. Ở production có thể cần nhiều trạng thái hơn như `PREPARING`, `READY`, `FAILED` và metadata nội bộ cho debug. Không nên đưa thông tin nhạy cảm hoặc exception gốc trực tiếp vào public health details.

### Kết hợp với tác vụ startup đồng bộ

Một runner có thể chỉ đánh dấu ready sau khi công việc bắt buộc thành công:

~~~java
package com.example.observation;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogPreparationConfiguration {

    @Bean
    ApplicationRunner prepareCatalog(
            CatalogHealthIndicator indicator
    ) {
        return args -> {
            // Mô phỏng công việc chuẩn bị có thể kiểm tra được.
            // Trong ứng dụng thật, thay bằng nạp catalog thực tế.
            Thread.sleep(1500);

            indicator.markReady();
        };
    }
}
~~~

Với runner đồng bộ, Boot chờ lời gọi `run(...)` trả về trước mốc ready. `Thread.sleep` chỉ dùng để mô phỏng trong bài học, không phải đề xuất nạp dữ liệu production bằng cách sleep.

Nếu runner ném exception, startup có thể thất bại. Nếu công việc dùng `@Async` hoặc executor và runner trả về ngay, **phải giữ indicator `DOWN` cho đến khi công việc nền hoàn tất thật sự**, không chỉ đến lúc task được submit.

### Thêm indicator vào readiness

Trong `application.properties`:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,catalog
~~~

Với cấu hình trên, readiness có thể kết hợp trạng thái vòng đời của Boot và trạng thái catalog.

**Lưu ý:** nếu để contributor catalog tham gia health tổng thể mặc định, nó cũng có thể ảnh hưởng đến `/actuator/health`. Hãy quyết định rõ scope của contributor, health group nào cần nó và chính sách phản hồi của từng endpoint.

## 12. Khi nào không nên dùng HealthIndicator để thực hiện việc nặng?

Mỗi lần gọi health endpoint có thể kích hoạt logic kiểm tra. Nếu một implementation gọi query lớn, download file, đọc hàng triệu bản ghi hoặc đợi một hệ thống chậm mà không có timeout, chính endpoint quan sát có thể trở thành nguyên nhân tiêu tốn tài nguyên.

Ví dụ không nên:

~~~java
@Override
public Health health() {
    List<Order> allOrders = orderRepository.findAll();
    return allOrders.isEmpty() ? Health.down().build()
                               : Health.up().build();
}
~~~

Việc đọc toàn bộ database để trả lời “ứng dụng có đủ khả năng xử lý request không?” vừa tốn tài nguyên, vừa không chắc phản ánh đúng điều kiện.

Thay vào đó:

- Ưu tiên kiểm tra rẻ, có giới hạn thời gian.
- Nếu cần kết nối ngoài, dùng timeout và cơ chế điều khiển phù hợp.
- Không thực hiện side effect hoặc sửa dữ liệu trong probe.
- Cân nhắc health dựa trên trạng thái do tiến trình chính cập nhật.
- Phân biệt dependency bắt buộc với thành phần tùy chọn.
- Xem xét tần suất probe từ nhiều orchestrator, load balancer và monitoring service.

Trong ứng dụng reactive, nếu health check phải thực hiện I/O bất đồng bộ, có thể dùng `ReactiveHealthIndicator` và các cơ chế phù hợp với web stack. Không nên block event loop chỉ để thực hiện một health check.

## 13. Endpoint info dùng để làm gì?

`info` là nơi công bố **metadata không nhằm mô tả trạng thái sức khỏe tức thời**.

Những ví dụ thích hợp:

- Tên dịch vụ: `orders-api`.
- Mô tả ngắn: dịch vụ nhận và xử lý đơn hàng.
- Phiên bản ứng dụng: `1.4.2`.
- Thông tin build: group, artifact, version, thời gian build.
- Git commit ID hoặc branch khi được cấu hình và cho phép công bố.
- Tên đội phụ trách hoặc URL runbook nội bộ, nếu endpoint có phạm vi truy cập phù hợp.
- Mã phiên bản hợp đồng API không nhạy cảm.

Thông tin không phù hợp để công bố công khai:

- Password, access token, API key.
- Chuỗi kết nối có credential.
- Biến môi trường đầy đủ.
- Tên máy nội bộ, thông tin định danh hạ tầng hoặc topology mà tổ chức không muốn công bố.
- Đường dẫn file tuyệt đối đến secret hoặc private key.
- Cấu hình bảo mật chi tiết.
- Dữ liệu người dùng hoặc dữ liệu nghiệp vụ chưa được phép tiết lộ.

**Info là nơi cho người quan sát biết “đang chạy bản nào”, không phải nơi dump toàn bộ Environment.**

## 14. Cấu hình info.app qua application.properties

Có thể tạo metadata tường minh:

~~~properties
spring.application.name=orders-api

management.endpoints.web.exposure.include=health,info
management.info.env.enabled=true

info.app.name=orders-api
info.app.description=Dich vu xu ly don hang
info.app.version=1.4.2
~~~

Trong ví dụ:

- `info.app.*` là những property do ứng dụng đặt.
- `management.info.env.enabled=true` cho phép contributor môi trường đưa những property `info.*` phù hợp vào endpoint trong các cấu hình Spring Boot hỗ trợ cơ chế này.
- `management.endpoints.web.exposure.include=health,info` giúp endpoint có thể được truy cập qua HTTP nếu đã enabled và security cho phép.

Response minh họa:

~~~json
{
  "app": {
    "name": "orders-api",
    "description": "Dich vu xu ly don hang",
    "version": "1.4.2"
  }
}
~~~

**Không nên suy ra rằng chỉ thêm `info.app.name` là chắc chắn endpoint sẽ hiện giá trị trong mọi phiên bản.** Cần bảo đảm contributor tương ứng đã bật và endpoint được expose đúng.

### Vì sao info có thể trả {}?

Nếu `/actuator/info` trả:

~~~json
{}
~~~

điều đó thường không có nghĩa ứng dụng lỗi. Có thể:

- Chưa có `InfoContributor` nào cung cấp metadata.
- Contributor mong đợi chưa được bật.
- Chưa sinh build info/git info resource.
- Config `info.*` không được đọc từ source đang có hiệu lực.

Cần xem cấu hình thực tế, thay vì dùng response rỗng như một tín hiệu health failure.

## 15. Build information: tránh nhập tay version khi có pipeline build

Phiên bản ứng dụng nên đến từ **quy trình build**, thay vì chỉ hardcode trong nhiều file khác nhau.

Với Spring Boot, build-info metadata thường được sinh vào tài nguyên:

~~~text
META-INF/build-info.properties
~~~

Một nội dung minh họa:

~~~properties
build.artifact=orders-api
build.group=com.example
build.name=Orders API
build.version=1.4.2
build.time=2026-11-13T09:00:00Z
~~~

Khi contributor build info được bật và resource tương ứng tồn tại, `/actuator/info` có thể hiển thị dữ liệu theo nhóm `build`:

~~~json
{
  "build": {
    "artifact": "orders-api",
    "group": "com.example",
    "name": "Orders API",
    "version": "1.4.2",
    "time": "2026-11-13T09:00:00Z"
  }
}
~~~

Các giá trị chỉ là minh họa; phiên bản, group và timestamp thực tế do build tạo.

### Sinh build-info bằng Maven

Với `spring-boot-maven-plugin`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>build-info</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Nếu dự án đã có plugin với execution khác, hãy bổ sung mục tiêu `build-info` vào cấu hình phù hợp, không tạo hai cấu hình plugin mâu thuẫn.

### Sinh build-info bằng Gradle

Trong dự án dùng Spring Boot Gradle plugin, có thể cấu hình:

~~~groovy
springBoot {
    buildInfo()
}
~~~

Điểm cần nhớ: các đoạn cấu hình chỉ minh họa cách yêu cầu build tool sinh metadata; nó không thay thế việc chạy đúng build task hoặc xác minh resource tồn tại trong artifact.

### Ý nghĩa của build.time

Thời gian build giúp điều tra:

- Artifact có được tạo trong lần phát hành mong đợi không?
- Instance nào đang chạy một build cũ hơn?
- Có sự khác biệt giữa artifact vừa build và artifact đã được đưa lên production không?

Tuy nhiên, timestamp không đủ thay thế commit ID, version hoặc checksum. Hai artifact có thể cùng version nhưng khác nội dung nếu quy trình phát hành không kiểm soát tính bất biến.

## 16. Git information: xác định commit đang chạy

Nếu build sinh một resource như:

~~~text
git.properties
~~~

Spring Boot có thể dùng contributor tương ứng để đưa một số Git metadata vào endpoint `info`, tùy phiên bản và cấu hình.

Ví dụ thông tin có thể xuất hiện:

~~~json
{
  "git": {
    "branch": "main",
    "commit": {
      "id": "abc1234",
      "time": "2026-11-13T08:40:00Z"
    }
  }
}
~~~

Dữ liệu này giúp trả lời câu hỏi quan trọng trong incident:

> Instance đang chạy code từ commit nào?

Khi có nhiều instance sau rolling deployment, so sánh commit/version có thể giúp phát hiện một instance chưa được cập nhật hoặc đã rollback.

### Git metadata không tự có mặt trong mọi ứng dụng

Spring Boot không thể tự suy ra commit source chính xác chỉ bằng cách chạy JAR đã build nếu không có dữ liệu build tương ứng. Quy trình build thường phải dùng plugin hoặc task tạo `git.properties`.

Ví dụ các dự án Maven có thể sử dụng plugin sinh Git properties; Gradle có thể dùng plugin tương tự. Tên, cấu hình và hành vi plugin phụ thuộc hệ build nên cần đối chiếu dự án cụ thể.

Không nên tự tuyên bố một Git branch là nguồn của artifact chỉ vì server production đang đặt một biến `BRANCH=main`. Dữ liệu về code build cần gắn với artifact đã phát hành.

### Mức độ thông tin công bố

Một số cấu hình info Git có thể cho phép thông tin đầy đủ hơn. Càng chi tiết thì càng phải cân nhắc:

- Có lộ tên branch nội bộ không?
- Có lộ URL repository private hoặc thông tin người commit không?
- Có lộ tag/metadata nhạy cảm không?
- Có cần hiển thị cho client bên ngoài không, hay chỉ cho hệ thống vận hành?

Chỉ công bố trường cần thiết cho mục đích quan sát, với mức phân quyền phù hợp.

## 17. Tạo InfoContributor riêng

Nếu metadata không thể biểu diễn đầy đủ bằng `info.*` hoặc build/git contributor, có thể tạo một `InfoContributor` tùy chỉnh.

Ví dụ:

~~~java
package com.example.observation;

import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.stereotype.Component;

@Component
public class ServiceInfoContributor implements InfoContributor {

    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail(
                "service",
                Map.of(
                        "name", "orders-api",
                        "domain", "orders",
                        "runbook", "https://docs.example.org/runbooks/orders"
                )
        );
    }
}
~~~

Response minh họa:

~~~json
{
  "service": {
    "name": "orders-api",
    "domain": "orders",
    "runbook": "https://docs.example.org/runbooks/orders"
  }
}
~~~

URL trong ví dụ chỉ đại diện cho một đường dẫn tài liệu giả định; không yêu cầu người học truy cập hoặc coi đó là tài liệu thật.

### Những nguyên tắc khi thiết kế InfoContributor

1. Chỉ công bố metadata có ích cho người gọi endpoint.
2. Không đưa toàn bộ `Environment`, system properties hoặc object chứa secret vào `Info.Builder`.
3. Hạn chế thao tác I/O nặng khi có request đến endpoint.
4. Không dùng endpoint `info` thay cho dữ liệu thay đổi liên tục như tình trạng database.
5. Giữ các key ổn định để dashboard hoặc công cụ monitoring có thể đọc.
6. Nếu metadata chỉ dành cho nội bộ, phải áp dụng security hoặc mạng nội bộ phù hợp.

`InfoContributor` là cơ chế mở rộng rất hữu ích, nhưng không nên coi nó là nơi ghi nhận log, cập nhật trạng thái nghiệp vụ hoặc nạp dữ liệu mỗi lần được gọi.

## 18. Health và info có thể cung cấp dữ liệu ở mức độ chi tiết khác nhau

Health endpoint thường có cơ chế điều chỉnh mức chi tiết trả về:

~~~properties
management.endpoint.health.show-details=never
~~~

Một số lựa chọn thường gặp:

| Giá trị | Ý nghĩa |
|---|---|
| `never` | Không hiển thị health details cho client |
| `when_authorized` | Hiển thị khi request đáp ứng điều kiện authorization |
| `always` | Hiển thị details, nếu endpoint truy cập được |

Có thể cấu hình thêm việc hiển thị các component:

~~~properties
management.endpoint.health.show-components=never
~~~

Hoặc lựa chọn khác phù hợp với nhu cầu vận hành. Cần phân biệt **component names** và **details**: việc hiện tên contributor đôi khi đã tiết lộ kiến trúc hoặc công nghệ ứng dụng, ngay cả khi các detail bị ẩn.

### Response tối giản

~~~json
{
  "status": "UP"
}
~~~

### Response có chi tiết — chỉ minh họa

~~~json
{
  "status": "UP",
  "components": {
    "db": {
      "status": "UP",
      "details": {
        "database": "PostgreSQL"
      }
    },
    "diskSpace": {
      "status": "UP",
      "details": {
        "threshold": 10485760,
        "exists": true
      }
    }
  }
}
~~~

Response cụ thể phụ thuộc contributor và phiên bản Spring Boot. Nếu cấu hình chỉ hiện details cho người có quyền, client không đủ quyền sẽ nhìn thấy output rút gọn.

**Không bật `show-details=always` trên endpoint công khai chỉ để dễ debug.** Những detail như tên database, cấu trúc dependency, đường dẫn hoặc exception có thể cung cấp thông tin không nên hiển thị cho người dùng bên ngoài.

## 19. when_authorized cần có kiểm soát truy cập thực sự

Một cấu hình ví dụ:

~~~properties
management.endpoint.health.show-details=when_authorized
management.endpoint.health.roles=ACTUATOR_ADMIN
~~~

Chủ đích của cấu hình:

- Người gọi thông thường chỉ được thấy trạng thái tổng quát.
- Người có role phù hợp mới được thấy details theo cơ chế authorization.

Tuy nhiên, cần kiểm tra Spring Security và cấu hình authentication/authorization thực tế. **Không được giả định rằng chỉ có dòng `when_authorized` thì endpoint đã an toàn**, nhất là trong ứng dụng không có security hoặc có security chain tùy chỉnh.

Trong các cấu hình không có Spring Security phù hợp, hành vi đánh giá người gọi “authorized” có thể không như mong đợi. Vì vậy, nếu endpoint được public qua Internet, phương án an toàn thường là chỉ công bố trạng thái tối giản, đồng thời dùng endpoint nội bộ có phân quyền để xem details.

### Có cần tách endpoint health công khai và nội bộ?

Nhiều hệ thống dùng:

~~~text
Public / routed health:
  Chỉ UP/DOWN hoặc status tối giản

Internal diagnostics:
  Có quyền truy cập mới thấy component và details
~~~

Đây là cách phân tách trách nhiệm hợp lý. Health check phục vụ load balancer không nhất thiết cần biết tên datasource, disk threshold hay exception chi tiết.

## 20. Security của endpoint info

Không giống `health`, endpoint `info` thường chứa metadata không cần thiết cho client thông thường. Dù dữ liệu không phải password, nó vẫn có thể làm lộ:

- Version cụ thể của framework hoặc ứng dụng.
- Commit, branch, build timestamp.
- Tên nhóm phụ trách và đường dẫn runbook.
- Kiến trúc hoặc danh sách module nghiệp vụ.
- Đường dẫn repository hay thông tin công cụ build.

Những dữ liệu này có thể giúp điều tra lỗi, nhưng cũng có thể hỗ trợ kẻ tấn công xác định phiên bản hoặc mục tiêu.

**Hãy đặt câu hỏi: ai cần biết?**

| Người gọi | Thông tin có thể cần |
|---|---|
| Load balancer | Health status cơ bản |
| Kubernetes readiness probe | Readiness status |
| Hệ thống theo dõi bản phát hành | Version, commit, build ID |
| Nhân viên vận hành | Version, owner, runbook và metadata phù hợp |
| Người dùng bên ngoài | Thường không cần hầu hết build/internal metadata |

Vì vậy, cân nhắc giới hạn endpoint `info` trong mạng nội bộ, yêu cầu authentication/authorization, hoặc chỉ expose các trường không nhạy cảm. Nếu phải public một số metadata, nên thiết kế cố định những trường được phép xuất hiện thay vì dump nguyên một object cấu hình.

## 21. Enabled, exposed và protected: ví dụ thiết kế bảo vệ

Một cấu hình ứng dụng web có thể bắt đầu với:

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never
management.info.env.enabled=true
~~~

Đây chỉ là **cấu hình endpoint và dữ liệu**, không phải chính sách security hoàn chỉnh. Khi yêu cầu `/actuator/info` chỉ nhân viên vận hành truy cập được, ứng dụng cần một security rule tương ứng.

Ví dụ với Spring Security 6 và Spring Boot 3.x trong ứng dụng Servlet:

~~~java
package com.example.observation;

import org.springframework.boot.actuate.autoconfigure.security.servlet
        .EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders
        .HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .anyRequest().hasRole("ACTUATOR_ADMIN")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đoạn này minh họa **một SecurityFilterChain cho Actuator**, không phải cấu hình bảo mật đầy đủ của toàn bộ ứng dụng. Trong dự án thực tế cần thêm chain cho các URL nghiệp vụ và chính sách xác thực phù hợp. Không dùng thông tin đăng nhập mẫu hoặc Basic Auth công khai ngoài môi trường HTTPS đã được quản lý.

**Lưu ý:** `permitAll()` cho `health` thường cho phép cả health endpoint con/group nếu thuộc matcher tương ứng; nếu cần chỉ công khai một probe và bảo vệ các group khác, phải viết rule cụ thể hơn theo đường dẫn và kiểm thử chính sách thực tế.

Khi ứng dụng tự khai báo `SecurityFilterChain`, không nên mặc định auto-configuration của Spring Boot sẽ tiếp tục bảo vệ mọi endpoint theo mong muốn. Tổ chức phải chủ động quyết định những endpoint nào được public, yêu cầu role nào và được expose ở đâu.

## 22. Management port riêng và khác biệt giữa hai cổng

Spring Boot hỗ trợ cấu hình management server trên một port khác với application server trong những môi trường phù hợp.

Ví dụ:

~~~properties
server.port=8080
management.server.port=9090
management.endpoints.web.exposure.include=health,info
~~~

Lúc này, tùy cấu hình:

~~~text
Application API:
  http://localhost:8080/api/orders

Management:
  http://localhost:9090/actuator/health
  http://localhost:9090/actuator/info
~~~

Port riêng có thể thuận tiện để giới hạn truy cập quản trị qua network policy. Nhưng nó cũng tạo ra một tình huống:

**Management port vẫn trả health UP không chứng minh application port đang nhận request bình thường.**

Ví dụ, management server có thể hoạt động trong khi connector phục vụ ứng dụng hoặc một phần routing tại port chính gặp sự cố. Nếu orchestrator cần kiểm tra khả năng phục vụ traffic thực, cần xem xét probe trên **main server port** hoặc cơ chế kiểm tra end-to-end thích hợp.

### Additional probe paths

Spring Boot hỗ trợ tùy chọn liên quan probes:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

Trong cấu hình hỗ trợ, các probe có thể được cung cấp thêm trên main server port theo những đường dẫn như `/livez` và `/readyz`. Cần xác minh đường dẫn/cổng thực tế trên phiên bản và web stack đang dùng.

Mục đích là để probe kiểm tra đường đi gần hơn với cổng phục vụ request thật, thay vì chỉ xác nhận management context riêng vẫn hoạt động.

## 23. Mẫu cấu hình Kubernetes với readiness/liveness

Ví dụ manifest pod/container với web port 8080:

~~~yaml
containers:
  - name: orders-api
    image: example/orders-api:1.4.2
    ports:
      - containerPort: 8080
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
~~~

Ví dụ giả định Actuator probes đã được bật và hai URL này phục vụ qua cổng 8080. Nếu sử dụng management port riêng, cấu hình sẽ phải khác.

**Ý nghĩa của hai probe:**

- Readiness không đạt: instance thường không được nhận request mới từ những đường routing tôn trọng readiness.
- Liveness không đạt kéo dài theo ngưỡng: orchestrator có thể restart container.
- Một HTTP 503 từ readiness có thể xảy ra trong giai đoạn startup hoặc khi dependency bắt buộc không sẵn sàng mà không có nghĩa JVM chết.

Nếu ứng dụng khởi động chậm, có thể dùng `startupProbe` để cho phép thêm thời gian khởi động trước khi liveness bắt đầu gây restart. Startup probe không thay thế readiness: một ứng dụng khởi động xong hạ tầng vẫn có thể chưa đủ điều kiện nghiệp vụ để nhận traffic.

### Không copy thông số probe một cách máy móc

Các giá trị `periodSeconds`, `timeoutSeconds` và `failureThreshold` phải dựa trên:

- Thời gian startup dự kiến.
- Latency của health check.
- Tải hệ thống.
- Chính sách rollout.
- Thời gian cần để phát hiện và phản ứng với sự cố.

Đặt timeout quá ngắn có thể tạo false negative khi hệ thống cao tải. Đặt threshold quá dài có thể làm chậm việc loại một instance thật sự không sẵn sàng.

## 24. Health check không nên trở thành nguyên nhân gây sự cố

Giả sử mỗi health request lại gọi một query SQL phức tạp. Nếu có nhiều tầng giám sát, một instance có thể bị probe hàng chục hoặc hàng trăm lần mỗi phút.

~~~text
Load balancer probe
          |
Kubernetes probe
          |
Monitoring collector
          |
          v
  /actuator/health
          |
          v
  Expensive database query
          |
          v
     Tăng tải DB
~~~

Trong tình huống xấu, chính probe làm tăng tải lên dependency rồi khiến health DOWN, tạo vòng lặp phản ứng bất lợi.

Một health check phù hợp nên:

- Được thực hiện nhanh và có timeout.
- Không thay đổi trạng thái nghiệp vụ.
- Không giữ lock dài.
- Không tạo hàng loạt kết nối mới không cần thiết.
- Không phụ thuộc vào một danh sách dịch vụ quá rộng nếu không cần thiết.
- Có chính sách cache hoặc trạng thái cập nhật phù hợp với yêu cầu độ tươi của tín hiệu.

Một số thành phần quan trọng có thể cần kiểm tra trực tiếp. Nhưng điều kiện được kiểm tra phải tương xứng với ý nghĩa health và tần suất probe.

## 25. Info không nên chứa dữ liệu thay đổi từng giây

Một ví dụ lạm dụng `InfoContributor`:

~~~java
@Override
public void contribute(Info.Builder builder) {
    builder.withDetail("activeOrders",
            orderRepository.countAllActiveOrders());
}
~~~

Nếu mỗi request `/actuator/info` đều query database để lấy một số đếm, endpoint này đang làm công việc gần với metric hoặc dashboard động hơn là cung cấp metadata.

Thay vào đó:

- Dùng **metrics** để theo dõi số lượng đơn hàng đang xử lý, latency và tỷ lệ lỗi.
- Dùng **logs** cho bối cảnh của các sự kiện cụ thể.
- Dùng **tracing** để điều tra luồng gọi xuyên dịch vụ.
- Dùng **health** cho điều kiện vận hành có phạm vi rõ ràng.
- Dùng **info** cho dữ liệu nhận diện phiên bản, dịch vụ và thông tin liên hệ.

Những công cụ này bổ sung cho nhau. Không nên biến một endpoint đơn lẻ thành nơi chứa mọi dữ liệu quan sát vì nó tiện hiển thị qua JSON.

## 26. Health không phải API nghiệp vụ

Giả sử dịch vụ có API xử lý đơn hàng:

~~~text
POST /api/orders
GET  /api/orders/{id}
~~~

Một health indicator có thể xác nhận database kết nối được. Nhưng điều đó không kiểm tra:

- Thuế và giá được tính đúng hay không.
- Đơn hàng có bị lưu trùng không.
- Luồng thanh toán có phản hồi đúng điều kiện nghiệp vụ không.
- Dữ liệu trả về có tuân thủ quyền truy cập không.

Đó là việc của unit test, integration test, contract test, end-to-end test và monitoring nghiệp vụ.

**Health giúp vận hành ra quyết định nhanh; nó không chứng minh tính đúng đắn của sản phẩm.**

Vì vậy, khi một service báo `UP` nhưng người dùng vẫn nhận lỗi, cần điều tra request/metric/log/tracing và các điều kiện nghiệp vụ thay vì chỉ tin vào health response.

## 27. Ví dụ project nhỏ: health + info + readiness

Giả sử ứng dụng quản lý đơn hàng có:

~~~text
orders-api
  |
  +-- Spring Web
  |
  +-- Spring Boot Actuator
  |
  +-- CatalogHealthIndicator
  |
  +-- ServiceInfoContributor
  |
  +-- API /api/ping
~~~

### 27.1. Dependencies

Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

### 27.2. Main class

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

### 27.3. Endpoint API tối thiểu

~~~java
package com.example.orders;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }
}
~~~

### 27.4. Cấu hình Actuator

~~~properties
spring.application.name=orders-api

management.endpoints.web.exposure.include=health,info
management.endpoint.health.probes.enabled=true

management.endpoint.health.show-details=never
management.endpoint.health.show-components=never

management.info.env.enabled=true
info.app.name=orders-api
info.app.description=Order processing service
info.app.version=1.4.2
~~~

Nếu đã khai báo `CatalogHealthIndicator` ở phần trước và muốn nó tham gia readiness:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,catalog
~~~

### 27.5. Quan sát từ terminal

~~~bash
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/info
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Response `/api/ping` cho biết route ví dụ hoạt động, `/health` cho biết trạng thái health đã tổng hợp, `/info` cho biết metadata đã cấu hình, còn liveness/readiness cung cấp các tín hiệu vòng đời và điều kiện do nhóm kiểm tra.

Một request trả HTTP 404 có thể do endpoint chưa được expose hoặc URL không khớp. Một request 401/403 có thể do security. Một request 503 ở health lại có thể là tín hiệu status không đạt, **không nhất thiết là endpoint bị vô hiệu hóa**.

## 28. Đọc một health response có components

Trong môi trường có quyền truy cập, một response có thể chứa các contributor:

~~~json
{
  "status": "DOWN",
  "components": {
    "catalog": {
      "status": "DOWN",
      "details": {
        "phase": "PREPARING"
      }
    },
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    }
  }
}
~~~

Cách đọc đúng:

1. Overall status là `DOWN`.
2. Thành phần `catalog` được báo chưa sẵn sàng.
3. DiskSpace và Ping báo `UP` theo phép kiểm tra riêng.
4. **Không kết luận CPU, database, queue hoặc mọi API đều khỏe** nếu chúng không được thể hiện hoặc kiểm tra.
5. Response này chỉ nên đưa cho người có quyền phù hợp nếu component/detail mang thông tin nội bộ.

Một response `DOWN` cần có thêm bối cảnh từ logs và metrics để biết **vì sao** catalog chưa sẵn sàng, nó sẽ tự phục hồi hay cần can thiệp.

## 29. Health status tổng hợp có thể che sự khác nhau giữa các thành phần

Giả sử:

~~~text
diskSpace = UP
db        = DOWN
cache     = UP
~~~

Status tổng hợp có thể là `DOWN` vì database là điều kiện được đưa vào phép tổng hợp.

Nhưng một service khác có thể dùng cùng database theo cách không bắt buộc để phục vụ một số API. Đối với service đó, quyết định readiness khi database DOWN có thể khác.

Do đó:

- **Cùng status không có nghĩa cùng nguyên nhân.**
- **Cùng nguyên nhân không nhất thiết cho ra cùng chính sách routing.**
- **Một health group phù hợp ứng dụng A chưa chắc phù hợp ứng dụng B.**

Đừng viết orchestration policy chỉ dựa trên tên contributor mà không hiểu vai trò của nó trong service.

### Custom status và thứ tự ưu tiên

Spring Boot có cơ chế tổng hợp trạng thái của contributor và có thể cho phép tùy chỉnh thứ tự, ví dụ khi ứng dụng bổ sung trạng thái `DEGRADED`.

Nhưng khi tạo custom status, cần nhất quán:

- Status nào nghiêm trọng hơn?
- Status nào là readiness failure?
- HTTP status code tương ứng là gì?
- Monitoring hiểu status mới thế nào?
- Liveness có nên chịu ảnh hưởng của status ấy không?

Nếu không có nhu cầu rõ ràng, dùng các status có sẵn thường đơn giản và dễ tích hợp hơn.

## 30. Health của ứng dụng reactive

Trong ứng dụng Spring WebFlux hoặc môi trường reactive, blocking I/O trong health check có thể gây vấn đề nếu chạy trên thread xử lý không phù hợp.

Spring Boot có `ReactiveHealthIndicator` cho cách biểu diễn health bất đồng bộ:

~~~java
package com.example.observation;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveSampleHealthIndicator
        implements ReactiveHealthIndicator {

    @Override
    public Mono<Health> health() {
        return Mono.just(Health.up().build());
    }
}
~~~

Ví dụ chỉ mô tả interface; không có I/O thực tế.

Khi kiểm tra một dependency ngoài, một implementation reactive cần:

- Dùng client phù hợp với reactive stack.
- Có timeout rõ ràng.
- Xử lý lỗi thành trạng thái health hợp lý.
- Không chặn event loop bằng lệnh blocking không kiểm soát.
- Tránh thực hiện những thao tác mạng quá nặng cho mỗi probe.

Tùy stack, Spring Boot có thể thích ứng health contributor theo cách phù hợp. Nguyên tắc về ý nghĩa và phạm vi của health vẫn không thay đổi: phép kiểm tra chỉ nói lên điều nó thực sự đo.

## 31. InfoContributor cũng phải có dữ liệu ổn định và đáng tin cậy

Một số trường metadata rất hữu ích nhưng cần được quản lý cẩn thận.

| Metadata | Cách sử dụng có ý nghĩa | Rủi ro nếu công bố rộng |
|---|---|---|
| `app.name` | Nhận diện dịch vụ | Thường thấp nhưng vẫn cần chính sách tên gọi |
| `app.version` | Biết release được deploy | Có thể tiết lộ phiên bản có lỗ hổng |
| `build.time` | Điều tra artifact cũ/mới | Có thể tiết lộ lịch phát hành |
| `git.commit.id` | Truy về mã nguồn phát hành | Có thể giúp suy ra thông tin repository |
| `runbook` | Hỗ trợ xử lý sự cố | Link tài liệu nội bộ có thể không nên public |
| `team` | Xác định owner | Có thể lộ cơ cấu nội bộ |
| `region` | Phân biệt nơi triển khai | Có thể tiết lộ topology |
| `feature-flags` | Biết cấu hình tính năng | Không nên dump toàn bộ cờ hoặc chính sách |
| `environment variables` | Có ích khi debug một số giá trị | Rất dễ chứa secret và dữ liệu nhạy cảm |

Một ứng dụng có nhiều replica có thể dùng cùng một `app.version` hoặc `git.commit.id`, trong khi thời điểm start process và một số thông số môi trường khác nhau. Nếu đưa nhiều dữ liệu runtime vào `info`, cần xác định rõ đó có còn là metadata ổn định cần công bố hay không.

### Không xem thông tin do client tự truyền là nguồn tin cậy cho build

Ví dụ, nếu ứng dụng lấy giá trị `version` từ một HTTP request rồi trả lại trong `info`, dữ liệu đó không chứng minh được version code đang chạy. Metadata build đáng tin hơn khi được pipeline sinh và gắn vào artifact, với quá trình phát hành có kiểm soát.

## 32. Các tình huống triển khai thường gặp

### A. Load balancer chỉ cần biết instance còn tiếp nhận traffic

Dùng readiness health group hoặc một endpoint kiểm tra có phạm vi rõ. Không cần cung cấp `info` hoặc health details cho load balancer.

### B. On-call cần biết bản deploy nào đang lỗi

Sử dụng `info` có version/commit và kết hợp logs/metrics. Đặt quyền truy cập phù hợp để chỉ người vận hành xem được metadata cần thiết.

### C. Một phụ thuộc bắt buộc không hoạt động

Nếu ứng dụng không thể phục vụ request chính khi dependency này mất kết nối, có thể phản ánh trong readiness. Tránh đưa dependency này vào liveness nếu restart ứng dụng không thể sửa được sự cố.

### D. Một phụ thuộc phụ trợ thất bại

Nếu ứng dụng vẫn phục vụ được chức năng cốt lõi, có thể dùng metric và cảnh báo riêng thay vì làm toàn bộ readiness `DOWN`.

### E. Startup có bước nạp dữ liệu bất đồng bộ

Dùng trạng thái chuẩn bị riêng kết hợp readiness group; không báo ready chỉ vì `ApplicationReadyEvent` đã xảy ra.

### F. Cần kiểm tra instance từ bên ngoài

Nếu bắt buộc expose health, ưu tiên status tối giản, kiểm soát cổng, path và network access. Không tự động expose các endpoint Actuator khác chỉ vì muốn dùng health.

## 33. Các lỗi cấu hình thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `/actuator/health` trả 404 | Actuator thiếu, endpoint/path không đúng hoặc chưa expose | Dependency, base path, management port, config |
| `/actuator/info` trả 404 | Info chưa expose hoặc endpoint disabled | Exposure include, endpoint enablement |
| `/actuator/info` trả `{}` | Không có info contributor hoặc chưa bật | `management.info.env.enabled`, build/git resource |
| `/actuator/health` trả 503 | Có status tổng hợp DOWN/OUT_OF_SERVICE | Logs, contributors nội bộ, dependency bắt buộc |
| Health luôn UP dù API chính lỗi | Health chỉ kiểm tra một tập điều kiện giới hạn | Thiết kế lại điều kiện/metric và kiểm tra nghiệp vụ |
| Readiness UP trong lúc cache chưa nạp | Task async chưa tham gia readiness | Thêm indicator phản ánh hoàn thành thực tế |
| Liveness DOWN vì DB outage | Đưa DB vào liveness | Tách readiness và liveness |
| Health bị timeout | Indicator chậm hoặc phụ thuộc xa | Timeout, đo latency, giảm công việc probe |
| Không xem được health details | `show-details=never` hoặc thiếu quyền | Kiểm tra chính sách hiển thị và authorization |
| Info lộ dữ liệu nội bộ | Cấu hình expose và contributor quá rộng | Hạn chế fields và phân quyền |
| Management port health UP nhưng API port lỗi | Probe không đi qua cùng đường traffic | Xem additional probe paths hoặc smoke test ứng dụng |
| Build info không xuất hiện | Không sinh hoặc không đóng gói `build-info.properties` | Kiểm tra build plugin, archive và contributor |
| Git info sai/missing | Không sinh `git.properties` hoặc artifact trôi phiên bản | Xác minh CI pipeline và artifact |

Bảng trên là các hướng bắt đầu điều tra. Lỗi cụ thể cần được xác nhận từ stack trace, cấu hình và phản hồi thật của hệ thống.

## 34. Thực hành: quan sát health và info từng bước

Trong môi trường local hoặc staging an toàn, có thể làm các bước sau.

### Thí nghiệm 1 — Health tối giản

Thêm starter Actuator và cấu hình:

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
~~~

Chạy ứng dụng rồi gọi:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Ghi nhận HTTP status và body. Không suy luận thêm các dependency chưa được kiểm tra.

### Thí nghiệm 2 — Info từ environment

Thêm:

~~~properties
management.info.env.enabled=true
info.app.name=learning-service
info.app.version=0.1.0
~~~

Gọi:

~~~bash
curl -i http://localhost:8080/actuator/info
~~~

So sánh output trước và sau khi có cấu hình. Nếu output rỗng hoặc endpoint 404, xác định đúng nhóm nguyên nhân: metadata chưa có hay endpoint chưa expose.

### Thí nghiệm 3 — Custom HealthIndicator

Tạo `CatalogHealthIndicator` ở mục 11. Khi chưa gọi `markReady()`, indicator trả `DOWN`. Sau khi gọi `markReady()`, nó trả `UP`.

Thêm:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,catalog
~~~

Kiểm tra `/actuator/health/readiness` trong giai đoạn chuẩn bị và sau khi hoàn thành.

### Thí nghiệm 4 — Thử giới hạn dữ liệu công bố

Chuyển:

~~~properties
management.endpoint.health.show-details=never
~~~

sang một chính sách chỉ dành cho người có quyền, ví dụ `when_authorized` với role phù hợp. Kiểm tra bằng hai identity khác nhau nếu project có security đúng.

Không thử bật chi tiết rồi expose endpoint công khai ra Internet chỉ để quan sát cho tiện.

### Thí nghiệm 5 — Kiểm tra metadata build

Cấu hình build tool sinh `META-INF/build-info.properties`, đóng gói ứng dụng rồi chạy chính artifact. Gọi `/actuator/info` để xem thông tin build đã có chưa.

Một số trường có thể khác nhau tùy plugin và phiên bản; điều cần nhận ra là build metadata phải được sinh và có mặt trong runtime artifact.

## 35. Những nhầm lẫn cần tránh

**“Health UP nghĩa là tất cả API đều hoạt động.”** Sai. Nó chỉ tổng hợp những kiểm tra được cấu hình và có thể không bao phủ logic nghiệp vụ.

**“Info trả 200 nghĩa là hệ thống healthy.”** Sai. Info chủ yếu công bố metadata và không được thiết kế làm readiness hoặc liveness signal.

**“Chỉ cần thêm starter là mọi endpoint đã public.”** Sai. Enabled, exposure và security là các lớp khác nhau.

**“Khi health trả 503 phải restart mọi instance.”** Sai. Trong readiness, nó có thể là trạng thái chờ phục hồi; restart hay không phụ thuộc liveness và chính sách vận hành.

**“Liveness cứ kiểm tra tất cả dependency cho chắc.”** Có thể dẫn đến restart storm khi phụ thuộc ngoài gặp sự cố.

**“ApplicationReadyEvent chắc chắn nạp xong mọi dữ liệu.”** Không đúng với các công việc bất đồng bộ được khởi chạy và trả về sớm.

**“Info rỗng là lỗi.”** Không nhất thiết; có thể chưa cấu hình contributor.

**“show-details=always là cách duy nhất để giám sát tốt.”** Sai. Probe thường chỉ cần status; details nên có quyền truy cập và mục đích rõ.

**“Chỉ bật info endpoint thì mọi giá trị info.* sẽ tự xuất hiện.”** Còn phụ thuộc contributor và cấu hình trong phiên bản Boot đang dùng.

**“HealthIndicator càng nhiều phép thử càng đáng tin.”** Không hẳn. Probe chậm, nặng hoặc chứa phụ thuộc không cần thiết có thể làm hệ thống kém ổn định hơn.

**“Tách management port là đủ để endpoint an toàn.”** Không. Vẫn cần chính sách mạng, xác thực và phân quyền phù hợp.

**“Không trả secret trực tiếp thì mọi metadata đều public được.”** Version, commit, topology hoặc runbook cũng có thể là thông tin nội bộ có giá trị với kẻ tấn công.

## 36. Checklist thiết kế trước khi đưa health/info lên production

1. **Mục đích:** endpoint phục vụ load balancer, Kubernetes hay nhân viên vận hành?
2. **Phạm vi:** những tín hiệu nào thật sự ảnh hưởng liveness hoặc readiness?
3. **Độ tươi:** health check được cập nhật theo sự kiện hay mỗi lần gọi?
4. **Hiệu năng:** health contributor có nhanh, có timeout và không gây side effect?
5. **Kết quả:** status và HTTP code có phù hợp với probe/alerting không?
6. **Security:** endpoint nào public, endpoint nào cần authentication/authorization?
7. **Dữ liệu:** details có chứa credential, topology hoặc thông tin nội bộ không?
8. **Version:** info có phản ánh artifact thực tế, không chỉ giá trị nhập tay?
9. **Topology:** probe được gọi qua management port hay application port?
10. **Triển khai:** có kiểm tra startup, shutdown và hành vi khi dependency bắt buộc thất bại không?
11. **Giám sát bổ sung:** logs, metrics và tracing có đủ để điều tra khi health DOWN không?
12. **Khả năng phục hồi:** readiness DOWN có cơ chế phục hồi hay cảnh báo phù hợp, thay vì giữ hệ thống không phục vụ vô hạn?

Một cấu hình ban đầu cho một API có Actuator, muốn hiển thị health tối giản và info nội bộ, có thể là:

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never
management.endpoint.health.probes.enabled=true

management.info.env.enabled=true
info.app.name=orders-api
info.app.description=Order processing service
~~~

**Cần bổ sung security/network policy theo môi trường thực tế** trước khi coi cấu hình này phù hợp cho production. Nếu chỉ load balancer cần `health` và không cần `info`, có thể expose ít hơn.

## Kết luận

Spring Boot Actuator có hai endpoint mang vai trò khác nhau:

- **`health`** cung cấp trạng thái vận hành theo các health contributor và health group đã cấu hình. Nó có thể hỗ trợ readiness/liveness và phản hồi `UP`, `DOWN`, `OUT_OF_SERVICE` hoặc `UNKNOWN`, nhưng chỉ nói lên những điều kiện được đánh giá tại thời điểm gọi.
- **`info`** công bố metadata có chủ đích, như tên dịch vụ, build version, commit hoặc thông tin hỗ trợ. Nó phục vụ nhận diện bản triển khai và điều tra vận hành, **không phải phép đo tình trạng sức khỏe**.

Khi sử dụng, hãy tách rõ **endpoint được bật**, **được expose qua HTTP** và **được cho phép truy cập**. Không mở health details, thông tin build, repository hay môi trường rộng rãi chỉ để debug thuận tiện. Đối với hệ thống điều phối, phân biệt **liveness** với **readiness**, tránh đặt dependency không cần thiết vào liveness và bổ sung điều kiện nghiệp vụ nếu Spring Boot ready nhưng công việc bất đồng bộ vẫn chưa hoàn tất.

**Giá trị của dữ liệu quan sát không nằm ở việc công bố càng nhiều càng tốt, mà ở chỗ người nhận hiểu chính xác tín hiệu đang chứng minh điều gì — và không chứng minh điều gì.**
