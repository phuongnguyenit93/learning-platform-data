# Đối chiếu cấu hình mong muốn với instance đang tồn tại

Một file YAML đúng cú pháp chưa đảm bảo Circuit Breaker đang chạy với đúng chính sách. Ứng dụng có thể nạp profile khác, ghi đè thuộc tính từ biến môi trường, tạo instance bằng một tên khác hoặc đã khởi tạo instance trước khi cấu hình được thay đổi. Vì vậy, khi vận hành Resilience4j trong Spring Cloud, cần đối chiếu cấu hình mong muốn với cấu hình thực tế của instance đang tồn tại, đồng thời xem trạng thái và metrics để hiểu hành vi hiện tại.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, thao tác đối chiếu này giúp xác định vì sao một Circuit Breaker chuyển OPEN, vì sao ngưỡng không được áp dụng hoặc vì sao một lời gọi dùng cấu hình mặc định. Cần phân biệt ba lớp thông tin: cấu hình được khai báo, cấu hình cuối cùng gắn với instance runtime và trạng thái động do các lời gọi đã xảy ra tạo nên.

## 1. Ba lớp thông tin cần đối chiếu

| Lớp thông tin | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Cấu hình mong muốn | YAML khai báo window size 40 và failure threshold 45% | Chính sách mà nhóm phát triển dự định sử dụng |
| Cấu hình hiệu lực của instance | CircuitBreakerConfig gắn với instance inventory-read | Giá trị Resilience4j thực sự dùng sau khi cấu hình được bind, kế thừa và áp dụng |
| Trạng thái runtime | CLOSED, OPEN, HALF_OPEN; số lời gọi và failure rate | Kết quả vận hành tại thời điểm quan sát, thay đổi theo traffic |

Không nên kết luận cấu hình sai chỉ vì instance đang OPEN. Một instance có thể dùng đúng ngưỡng 45% nhưng đã ghi nhận đủ lỗi để mở mạch. Ngược lại, một instance đang CLOSED không chứng minh cấu hình đã được áp dụng đúng; nó có thể chưa nhận đủ số mẫu hoặc đang dùng ngưỡng mặc định.

Quy trình kiểm tra cần trả lời lần lượt:

1. Ứng dụng có nạp đúng cấu hình và profile không?
2. Tên instance trong code có khớp khóa trong resilience4j.circuitbreaker.instances không?
3. Instance hiện tại có những giá trị cấu hình nào?
4. State và metrics cho thấy điều gì đã xảy ra với các lời gọi?

## 2. Xác định chính xác tên instance

Resilience4j tra cứu cấu hình theo tên instance. Ví dụ, nếu code dùng:

~~~java
CircuitBreaker circuitBreaker =
        circuitBreakerRegistry.circuitBreaker("inventory-read");
~~~

thì cấu hình tương ứng phải nằm dưới:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 40
        minimumNumberOfCalls: 20
        failureRateThreshold: 45
~~~

Tên phải khớp chính xác với định danh mà ứng dụng sử dụng. Với Spring Cloud CircuitBreaker, tên được truyền vào factory như create("inventory-read") cần khớp instance mà implementation Resilience4j dùng. Với OpenFeign, tên có thể được sinh từ client và method thông qua naming resolver; cần xác minh ID runtime thay vì đoán từ tên service.

Một lỗi thường gặp là cấu hình instances.inventory trong khi code tạo inventory-read, hoặc một resolver tạo ID đã chuẩn hóa khác với khóa YAML. Khi đó, instance mong muốn có thể không được dùng và ứng dụng rơi về cấu hình mặc định.

## 3. Kiểm tra cấu hình hiệu lực từ Spring Environment

Spring Boot có thể nạp nhiều nguồn cấu hình: file mặc định, file theo profile, biến môi trường, tham số dòng lệnh và nguồn cấu hình bên ngoài. Giá trị hiệu lực có thể khác giá trị nhìn thấy trong một file YAML riêng lẻ.

Ví dụ, profile prod có thể ghi đè failureRateThreshold; biến môi trường cũng có thể ghi đè thuộc tính trong file. Hãy xác định profile đang hoạt động và giá trị cuối cùng mà Spring Environment cung cấp.

Có thể dùng Binder để đọc một thuộc tính theo quy tắc relaxed binding của Spring Boot:

~~~java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CircuitBreakerPropertyInspector {
    private final Environment environment;

    public CircuitBreakerPropertyInspector(Environment environment) {
        this.environment = environment;
    }

    public Integer configuredWindowSize() {
        return Binder.get(environment)
                .bind(
                        "resilience4j.circuitbreaker.instances.inventory-read.sliding-window-size",
                        Integer.class)
                .orElse(null);
    }
}
~~~

Giá trị trả về cho biết thuộc tính được bind từ các property source hiện hành. Nếu instance dùng baseConfig, thuộc tính có thể được kế thừa từ config chung chứ không xuất hiện trực tiếp dưới khóa instance. Vì vậy, đọc một property riêng lẻ từ Environment chưa đủ để xác nhận toàn bộ cấu hình cuối cùng.

Khi cần xem nguồn ghi đè, endpoint Actuator env có thể giúp kiểm tra property source và origin của thuộc tính nếu ứng dụng đã bật endpoint tương ứng. Endpoint này có thể tiết lộ thông tin cấu hình nhạy cảm; chỉ expose trong phạm vi được kiểm soát và bảo vệ bằng xác thực, phân quyền phù hợp. Không mở endpoint môi trường cấu hình công khai chỉ để tiện debug.

## 4. Đọc cấu hình gắn với instance runtime

Cách xác nhận trực tiếp hơn là lấy instance đang tồn tại từ CircuitBreakerRegistry, sau đó đọc CircuitBreakerConfig gắn với nó. Dùng find(name) khi muốn kiểm tra instance đã được tạo hay chưa; không gọi circuitBreaker(name) chỉ để dò tìm vì phương thức đó có thể tạo instance mới nếu chưa tồn tại.

Ví dụ:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class CircuitBreakerRuntimeInspector {
    private static final Logger log =
            LoggerFactory.getLogger(CircuitBreakerRuntimeInspector.class);
    private final CircuitBreakerRegistry registry;

    public CircuitBreakerRuntimeInspector(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    public void inspectInventory() {
        CircuitBreaker breaker = registry.find("inventory-read")
                .orElseThrow(() ->
                        new IllegalStateException(
                                "Circuit Breaker inventory-read chưa được tạo"));

        CircuitBreakerConfig config =
                breaker.getCircuitBreakerConfig();

        log.info(
                "CircuitBreaker name={}, state={}, windowType={}, windowSize={}, "
                        + "minimumCalls={}, failureThreshold={}, slowCallThreshold={}, "
                        + "slowCallRateThreshold={}, halfOpenPermits={}",
                breaker.getName(),
                breaker.getState(),
                config.getSlidingWindowType(),
                config.getSlidingWindowSize(),
                config.getMinimumNumberOfCalls(),
                config.getFailureRateThreshold(),
                config.getSlowCallDurationThreshold(),
                config.getSlowCallRateThreshold(),
                config.getPermittedNumberOfCallsInHalfOpenState()
        );
    }
}
~~~

Đoạn mã minh họa việc kiểm tra cấu hình và state của instance đã tồn tại. Các API getter cần được đối chiếu với phiên bản Resilience4j mà dự án đang dùng; nếu phiên bản có khác biệt về chữ ký, hãy dùng API tương ứng của phiên bản đó.

Nếu find("inventory-read") không tìm thấy instance, cần kiểm tra xem lời gọi đã được thực thi chưa, factory có tạo instance với ID khác không và registry được inject có phải registry mà integration đang sử dụng không. Đừng tự tạo một instance mới trong quá trình chẩn đoán rồi kết luận rằng cấu hình production đã được nạp.

## 5. Đối chiếu từng tham số quan trọng

Nên lập bảng kỳ vọng cho mỗi instance và so sánh với cấu hình runtime:

| Thuộc tính | Giá trị mong muốn ví dụ | Điều cần xác nhận |
| --- | --- | --- |
| Tên instance | inventory-read | Trùng ID được dùng khi tạo Circuit Breaker |
| slidingWindowType | COUNT_BASED | Đơn vị của cửa sổ là số lời gọi |
| slidingWindowSize | 40 | Kích thước cửa sổ là 40 kết quả gần nhất |
| minimumNumberOfCalls | 20 | Chưa đánh giá tỷ lệ trước khi đủ 20 mẫu |
| failureRateThreshold | 45 | Ngưỡng mở mạch là 45% |
| slowCallDurationThreshold | 1500ms | Lời gọi vượt 1,5 giây được xem là chậm |
| slowCallRateThreshold | 60 | Ngưỡng tỷ lệ lời gọi chậm là 60% |
| waitDurationInOpenState | 10s | Thời gian chờ trước giai đoạn thử phục hồi |
| permittedNumberOfCallsInHalfOpenState | 3 | Tối đa 3 lời gọi thử nghiệm được phép |

Không phải mọi thuộc tính đều có getter hiển thị cùng một kiểu ở tất cả phiên bản. Ví dụ, cách biểu diễn thời gian chờ OPEN có thể là duration hoặc interval function. Khi so sánh, hãy quy đổi về cùng đơn vị và kiểm tra ngữ nghĩa, không chỉ so sánh chuỗi hiển thị.

## 6. Đọc state và metrics riêng với cấu hình

Sau khi xác nhận cấu hình, đọc metrics để hiểu tại sao instance đang ở state hiện tại:

~~~java
CircuitBreaker breaker = registry.find("inventory-read")
        .orElseThrow();

CircuitBreaker.Metrics metrics = breaker.getMetrics();

log.info(
        "name={}, state={}, bufferedCalls={}, failedCalls={}, "
                + "successfulCalls={}, failureRate={}, slowCallRate={}, rejectedCalls={}",
        breaker.getName(),
        breaker.getState(),
        metrics.getNumberOfBufferedCalls(),
        metrics.getNumberOfFailedCalls(),
        metrics.getNumberOfSuccessfulCalls(),
        metrics.getFailureRate(),
        metrics.getSlowCallRate(),
        metrics.getNumberOfNotPermittedCalls()
);
~~~

Metrics là ảnh chụp thống kê tại thời điểm đọc. Tùy phiên bản và state, một số tỷ lệ có thể chưa có đủ mẫu và được biểu diễn bằng giá trị chưa xác định hoặc giá trị sentinel. Cần xử lý giá trị đó đúng cách trong dashboard và log, tránh diễn giải nó như tỷ lệ 0% nếu chưa có dữ liệu.

Phân biệt:

- state cho biết Circuit Breaker hiện ở CLOSED, OPEN hay HALF_OPEN.
- bufferedCalls cho biết số kết quả đang được giữ trong cửa sổ.
- failedCalls và successfulCalls giúp hiểu kết quả đã ghi nhận.
- failureRate và slowCallRate cho biết tỷ lệ thống kê.
- rejectedCalls cho biết số lời gọi bị từ chối khi mạch không cho phép đi qua.

Một instance OPEN với failure rate 70% và ngưỡng 45% có thể đang hoạt động đúng chính sách. Một instance CLOSED với 3 lời gọi lỗi nhưng minimum calls là 20 cũng có thể đúng, vì chưa đủ mẫu để đánh giá.

## 7. Kiểm tra qua Spring Boot Actuator

Nếu ứng dụng có dependency Actuator và Resilience4j Actuator integration phù hợp, các endpoint chuyên biệt có thể hỗ trợ vận hành:

- circuitbreakers: xem các Circuit Breaker instance và trạng thái hiện tại.
- circuitbreakerevents: xem các sự kiện như thành công, lỗi, từ chối và chuyển trạng thái.
- metrics: xem meter được Micrometer đăng ký.
- env: kiểm tra property source và giá trị cấu hình hiệu lực nếu endpoint được bật.

Ví dụ expose các endpoint cần thiết trong môi trường quản trị:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,circuitbreakers,circuitbreakerevents
~~~

Tên endpoint và nội dung trả về phụ thuộc dependency, phiên bản Spring Boot/Resilience4j và cấu hình exposure. Hãy kiểm tra danh sách endpoint thực tế của ứng dụng. Chỉ expose những endpoint cần dùng và bảo vệ chúng bằng mạng quản trị, xác thực và phân quyền.

Actuator giúp xem state, event và metrics; không phải endpoint nào cũng hiển thị toàn bộ cấu hình đã hợp nhất của instance. Khi cần xác nhận slidingWindowSize, minimumNumberOfCalls hoặc threshold runtime, có thể dùng registry inspector để đọc config gắn trực tiếp với instance.

## 8. Phân biệt instance chưa tồn tại với instance đang dùng cấu hình mặc định

Hai tình huống này dễ bị nhầm:

| Tình huống | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Instance chưa được tạo | registry.find(name) trả về empty | Kiểm tra đường gọi, tên factory và thời điểm instance được tạo |
| Instance được tạo dưới tên khác | Registry có instance gần giống nhưng không có đúng tên | Ghi log ID thực tế và đối chiếu resolver |
| Instance tồn tại nhưng dùng default | Runtime config khác YAML mong muốn | Kiểm tra property binding, baseConfig, profile và tên khóa |
| Instance dùng đúng config nhưng state OPEN | Config runtime khớp; metrics vượt ngưỡng | Điều tra lỗi/độ trễ phụ thuộc, không đổi config chỉ vì state OPEN |
| Instance cũ giữ cấu hình trước đó | File đã đổi nhưng config runtime không đổi | Kiểm tra cơ chế refresh và thời điểm instance được khởi tạo |

Không dùng registry.circuitBreaker(name) làm phép kiểm tra tồn tại. Phương thức đó có thể tạo instance mới và làm thay đổi đối tượng đang được quan sát. Dùng find(name) hoặc liệt kê getAllCircuitBreakers() để kiểm tra các instance đã đăng ký.

## 9. Hiểu ảnh hưởng của baseConfig và thứ tự nạp cấu hình

Một instance có thể kế thừa chính sách từ configs:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
      inventory-policy:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 40
        minimumNumberOfCalls: 20
        failureRateThreshold: 45
        waitDurationInOpenState: 10s
    instances:
      inventory-read:
        baseConfig: inventory-policy
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
~~~

Trong ví dụ, inventory-policy là một config được đặt tên với các giá trị đầy đủ cho nhóm thao tác đọc tồn kho; instance inventory-read tham chiếu config đó rồi bổ sung thuộc tính riêng. Khi đối chiếu, cần xem cấu hình cuối cùng sau khi baseConfig được áp dụng, không chỉ đọc một block YAML.

Profile hoặc nguồn cấu hình ngoài có thể ghi đè thuộc tính. Nếu giá trị runtime khác dự kiến, kiểm tra profile đang active, file cấu hình được nạp, biến môi trường và tham số triển khai. Đừng chỉnh threshold trước khi xác định nguồn nào đang cung cấp giá trị cuối.

## 10. Cấu hình thay đổi nhưng instance đang tồn tại

Việc sửa application.yml không nhất thiết thay đổi ngay một Circuit Breaker đã được tạo. Resilience4j instance giữ cấu hình được gắn vào nó khi khởi tạo; khả năng cập nhật nóng phụ thuộc cơ chế refresh, integration và phiên bản ứng dụng.

Khi thay đổi cấu hình, hãy xác minh:

1. File hoặc nguồn cấu hình mới đã được nạp.
2. Spring Environment trả về giá trị mong muốn.
3. Integration có hỗ trợ refresh instance đang tồn tại hay không.
4. Registry inspector cho thấy config gắn với instance đã thay đổi chưa.
5. State hiện tại có được giữ lại hay instance được tạo lại/reset theo cơ chế cập nhật.

Nếu không có cơ chế refresh được hỗ trợ và xác nhận, triển khai lại ứng dụng theo quy trình vận hành để instance được tạo từ cấu hình mới. Tránh xóa hoặc tạo lại instance tùy tiện trong production vì có thể làm mất lịch sử sliding window, event và state đang cần để điều tra.

## 11. Ví dụ kiểm tra cấu hình bằng test

Một test trong Spring context có thể xác nhận cấu hình đã được bind và instance runtime nhận đúng giá trị:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class InventoryCircuitBreakerConfigurationTest {
    @Autowired
    CircuitBreakerRegistry registry;

    @Test
    void inventoryInstanceUsesExpectedConfiguration() {
        CircuitBreaker breaker = registry.find("inventory-read")
                .orElseThrow();
        CircuitBreakerConfig config =
                breaker.getCircuitBreakerConfig();

        assertEquals(
                CircuitBreakerConfig.SlidingWindowType.COUNT_BASED,
                config.getSlidingWindowType());
        assertEquals(40, config.getSlidingWindowSize());
        assertEquals(20, config.getMinimumNumberOfCalls());
        assertEquals(45.0f, config.getFailureRateThreshold());
    }
}
~~~

Test này cần cấu hình test context có instance inventory-read và các giá trị mong muốn. Nó kiểm tra cấu hình runtime, không chỉ kiểm tra file YAML tồn tại. Nếu dự án dùng nhiều profile, hãy chạy test với profile tương ứng hoặc tạo test riêng cho từng profile quan trọng.

Khi kiểm thử state transition, nên dùng instance riêng cho test và không để test thay đổi state của registry dùng chung giữa các test. Việc xác nhận cấu hình nên tách khỏi việc kiểm tra Circuit Breaker mở mạch sau một chuỗi lỗi.

## 12. Quy trình xử lý khi cấu hình và runtime không khớp

Khi phát hiện khác biệt, thực hiện theo thứ tự:

1. Xác nhận đúng tên instance từ code hoặc naming resolver.
2. Dùng registry.find(name) để xác nhận instance đã tồn tại.
3. Đọc cấu hình runtime gắn với instance.
4. Đối chiếu với cấu hình mong muốn, bao gồm baseConfig và các giá trị ghi đè.
5. Kiểm tra profile, biến môi trường, tham số triển khai và nguồn cấu hình ngoài.
6. Kiểm tra thời điểm instance được tạo và khả năng refresh của integration.
7. Đọc state, sliding window metrics và event để hiểu hành vi hiện tại.
8. Chỉ thay đổi cấu hình sau khi đã xác định nguồn gây sai lệch; sau triển khai, đọc lại instance để xác nhận.

Một bảng đối chiếu vận hành nên lưu tên instance, profile, window type, window size, minimum calls, failure threshold, slow-call threshold, thời gian OPEN, state hiện tại và thời điểm quan sát. Bảng này giúp nhóm phát triển so sánh giữa môi trường dev, staging và production mà không nhầm state động với cấu hình tĩnh.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ đọc YAML mà không kiểm tra instance | Bỏ sót profile hoặc property source ghi đè | Đọc config gắn với instance runtime |
| Dùng sai tên instance | Lời gọi dùng cấu hình mặc định hoặc instance khác | Đối chiếu tên trong code, factory và YAML |
| Gọi circuitBreaker(name) để kiểm tra tồn tại | Vô tình tạo instance mới trong lúc chẩn đoán | Dùng find(name) hoặc liệt kê registry |
| Nhầm state OPEN với cấu hình sai | Thay đổi threshold không cần thiết | So sánh config trước, sau đó đọc metrics và events |
| Chỉ nhìn state CLOSED | Không phát hiện instance chưa đủ mẫu hoặc đang dùng default | Kiểm tra config và số mẫu đã ghi nhận |
| Giả định YAML thay đổi sẽ cập nhật instance ngay | Runtime tiếp tục dùng cấu hình cũ | Xác minh refresh hoặc triển khai lại theo quy trình |
| Expose Actuator env không bảo vệ | Có thể lộ thông tin cấu hình nhạy cảm | Giới hạn exposure, xác thực và quyền truy cập |
| So sánh duration khác đơn vị | Kết luận sai rằng giá trị runtime không khớp | Quy đổi về cùng đơn vị trước khi so sánh |

## 14. Ghi nhớ

Đối chiếu cấu hình mong muốn với instance đang tồn tại cần xem cả cấu hình hiệu lực và trạng thái runtime. Dùng tên instance chính xác, lấy instance đã tồn tại bằng find, đọc CircuitBreakerConfig và metrics, rồi kiểm tra profile cùng các nguồn ghi đè của Spring Boot. Khi phân biệt được cấu hình tĩnh với state động, nhóm vận hành có thể xác định liệu Circuit Breaker đang hoạt động đúng chính sách hay đang dùng sai instance/cấu hình, từ đó điều chỉnh an toàn và có bằng chứng.
