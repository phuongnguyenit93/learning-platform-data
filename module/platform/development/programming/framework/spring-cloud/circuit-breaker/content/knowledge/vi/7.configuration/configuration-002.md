# baseConfig và kế thừa cấu hình dùng chung

Trong một ứng dụng Spring Cloud CircuitBreaker sử dụng Resilience4j, nhiều dependency có thể cần những chính sách Circuit Breaker gần giống nhau. Nếu mỗi instance đều khai báo lại toàn bộ sliding window, ngưỡng lỗi, thời gian OPEN và số lời gọi thăm dò, cấu hình sẽ dài, khó đồng bộ và dễ sai lệch khi cần thay đổi.

Resilience4j hỗ trợ nhóm cấu hình dùng chung trong phần configs và cho phép từng instance tham chiếu nhóm đó bằng thuộc tính baseConfig. Instance kế thừa các giá trị chung, sau đó có thể khai báo những giá trị riêng để điều chỉnh hành vi cho dependency tương ứng.

Cơ chế này giúp chuẩn hóa cấu hình giữa các dịch vụ phụ thuộc, giảm lặp lại và vẫn giữ được khả năng tinh chỉnh theo đặc tính tải, độ trễ và mức độ quan trọng của từng dependency.

## 1. Phân biệt configs và instances

Trong cấu hình Resilience4j, hai phần có vai trò khác nhau:

- **configs** chứa các nhóm giá trị mẫu có thể được tái sử dụng. Một nhóm cấu hình chưa đại diện cho một Circuit Breaker đang chạy.
- **instances** khai báo các Circuit Breaker thực tế mà ứng dụng sử dụng. Mỗi instance có một ID và có thể tham chiếu một nhóm cấu hình trong configs bằng baseConfig.

Cấu trúc khái quát:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        failureRateThreshold: 50
    instances:
      inventory:
        baseConfig: default
      payment:
        baseConfig: default
        failureRateThreshold: 30
~~~

Trong ví dụ:

- default là tên một nhóm cấu hình dùng chung.
- inventory và payment là hai instance Circuit Breaker được ứng dụng sử dụng.
- inventory kế thừa các thuộc tính từ default.
- payment cũng kế thừa default nhưng thay failureRateThreshold thành 30.

Tên trong configs có thể được đặt theo mục đích hoặc đặc tính vận hành, chẳng hạn default, shared, highLatency hoặc criticalDependency. Tên instance nên thể hiện dependency hoặc luồng nghiệp vụ được bảo vệ, chẳng hạn inventory, payment hoặc customer-profile.

## 2. baseConfig hoạt động như thế nào?

Thuộc tính baseConfig đặt bên trong một instance và trỏ đến tên nhóm cấu hình trong configs của cùng loại Resilience4j. Khi tạo instance, các giá trị từ nhóm cơ sở được dùng làm cấu hình chung. Các thuộc tính khai báo trực tiếp trong instance sẽ ghi đè giá trị tương ứng được kế thừa.

Có thể hình dung thứ tự áp dụng:

~~~mermaid
flowchart TD
    A[Nhóm configs dùng chung] --> B[Instance khai báo baseConfig]
    C[Thuộc tính riêng của instance] --> D[Hợp nhất cấu hình]
    B --> D
    D --> E[Circuit Breaker có cấu hình hiệu lực]
~~~

Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      shared:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      inventory:
        baseConfig: shared
      payment:
        baseConfig: shared
        slidingWindowSize: 100
        failureRateThreshold: 30
        waitDurationInOpenState: 20s
~~~

Kết quả về mặt cấu hình:

| Thuộc tính | Nhóm shared | inventory | payment |
|---|---:|---:|---:|
| slidingWindowType | COUNT_BASED | COUNT_BASED | COUNT_BASED |
| slidingWindowSize | 50 | 50 | 100 |
| minimumNumberOfCalls | 10 | 10 | 10 |
| failureRateThreshold | 50 | 50 | 30 |
| slowCallDurationThreshold | 2s | 2s | 2s |
| slowCallRateThreshold | 50 | 50 | 50 |
| waitDurationInOpenState | 10s | 10s | 20s |
| permittedNumberOfCallsInHalfOpenState | 3 | 3 | 3 |

inventory sử dụng toàn bộ giá trị chung. payment chỉ ghi đè ba thuộc tính slidingWindowSize, failureRateThreshold và waitDurationInOpenState; các thuộc tính còn lại tiếp tục lấy từ shared.

Cần phân biệt giá trị được kế thừa với giá trị mặc định của thư viện. Nếu instance không tham chiếu baseConfig, nó không tự động kế thừa một nhóm tùy ý chỉ vì nhóm đó có tên shared. Hãy khai báo rõ baseConfig và bảo đảm tên được tham chiếu tồn tại trong configs tương ứng.

## 3. Khai báo nhóm cấu hình Circuit Breaker dùng chung

Một nhóm cấu hình chung nên chứa những thuộc tính có ý nghĩa nhất quán đối với các dependency cùng nhóm. Ví dụ, các dependency HTTP thông thường có thể dùng chung cửa sổ thống kê, ngưỡng lỗi và thời gian OPEN:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      inventory:
        baseConfig: default
      customer:
        baseConfig: default
      recommendation:
        baseConfig: default
~~~

Cấu hình trên giúp ba instance dùng chung một chính sách. Khi cần thay đổi kích thước cửa sổ hoặc thời gian OPEN cho cả nhóm, chỉ cần cập nhật nhóm default.

Tuy nhiên, không nên đưa mọi thuộc tính vào một nhóm chung nếu các dependency có đặc tính khác nhau. Ví dụ, dịch vụ thanh toán có thể cần ngưỡng lỗi chặt hơn, trong khi dịch vụ gợi ý sản phẩm có thể chấp nhận fallback hoặc suy giảm lâu hơn. Trong trường hợp đó, tạo các nhóm cấu hình riêng theo đặc tính vận hành.

## 4. Tạo nhiều nhóm cấu hình theo mục đích

Một ứng dụng có thể định nghĩa nhiều nhóm cấu hình trong cùng phần configs. Mỗi instance chọn nhóm phù hợp bằng baseConfig.

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      standard:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
      critical:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 20
        failureRateThreshold: 30
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 40
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 2
      bestEffort:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 20
        failureRateThreshold: 60
        waitDurationInOpenState: 5s
        permittedNumberOfCallsInHalfOpenState: 5
    instances:
      inventory:
        baseConfig: standard
      payment:
        baseConfig: critical
      recommendation:
        baseConfig: bestEffort
~~~

Có thể hiểu các nhóm như những chính sách vận hành:

| Nhóm | Ví dụ sử dụng | Đặc điểm |
|---|---|---|
| standard | Dependency thông thường | Ngưỡng và thời gian phục hồi cân bằng |
| critical | Dependency quan trọng như thanh toán | Phát hiện lỗi chặt hơn, thăm dò thận trọng |
| bestEffort | Gợi ý, nội dung bổ trợ | Cho phép mức lỗi cao hơn và thử phục hồi sớm hơn |

Các giá trị trên chỉ là ví dụ. Việc chọn ngưỡng cần dựa trên SLA, lưu lượng và hành vi thực tế của dependency. Không nên gán nhãn critical hoặc bestEffort chỉ dựa vào tên dịch vụ mà không xác định hậu quả nghiệp vụ khi dependency suy giảm.

## 5. Kế thừa cấu hình và ghi đè theo instance

Ghi đè theo instance giúp giữ chính sách chung mà không buộc mọi dependency phải có cùng hành vi. Một số trường hợp thường gặp:

- Dependency phản hồi chậm cần slowCallDurationThreshold cao hơn hoặc thấp hơn tùy SLA.
- Dependency có lưu lượng lớn có thể cần slidingWindowSize lớn hơn.
- Dependency quan trọng có thể dùng failureRateThreshold thấp hơn để mở mạch sớm.
- Dependency có khả năng phục hồi nhanh có thể dùng waitDurationInOpenState ngắn hơn, nếu việc thăm dò không tạo tải nguy hiểm.

Ví dụ, payment kế thừa nhóm critical nhưng điều chỉnh thời gian OPEN và số lời gọi thăm dò:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      critical:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 20
        failureRateThreshold: 30
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 2
    instances:
      payment:
        baseConfig: critical
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 1
~~~

payment nhận các giá trị chung từ critical. Hai thuộc tính được khai báo tại instance sẽ có hiệu lực riêng cho payment. Các instance khác tham chiếu critical vẫn giữ thời gian OPEN 20 giây và cho phép hai lời gọi thăm dò.

Khi ghi đè, cần chỉ khai báo những thuộc tính thực sự khác biệt. Việc sao chép toàn bộ cấu hình chung vào mỗi instance làm mất lợi ích tái sử dụng và khiến các thay đổi sau này khó kiểm soát.

## 6. Tách cấu hình dùng chung theo từng loại Resilience4j

Resilience4j có nhiều module như Circuit Breaker, Retry, TimeLimiter, Bulkhead và RateLimiter. Mỗi module có vùng configs và instances riêng. Một nhóm cấu hình trong circuitbreaker không tự động áp dụng cho retry hoặc bulkhead.

Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      shared:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
    instances:
      inventory:
        baseConfig: shared
      payment:
        baseConfig: shared
        failureRateThreshold: 30

  retry:
    configs:
      shared:
        maxAttempts: 2
        waitDuration: 200ms
    instances:
      inventory:
        baseConfig: shared
      payment:
        baseConfig: shared
        maxAttempts: 1

  timelimiter:
    configs:
      shared:
        timeoutDuration: 2s
        cancelRunningFuture: true
    instances:
      inventory:
        baseConfig: shared
      payment:
        baseConfig: shared
        timeoutDuration: 3s
~~~

Trong ví dụ:

- Circuit Breaker dùng shared để tái sử dụng cửa sổ và ngưỡng lỗi.
- Retry dùng shared để tái sử dụng số lần thử và thời gian chờ.
- TimeLimiter dùng shared để tái sử dụng giới hạn thời gian.
- Instance payment có thể ghi đè giá trị riêng trong từng module.

Tên shared được dùng ở ba vùng cấu hình độc lập. Mỗi baseConfig chỉ tham chiếu nhóm configs thuộc module tương ứng. Vì vậy, retry.instances.payment.baseConfig phải trỏ đến retry.configs, không phải circuitbreaker.configs.

Cách tổ chức này giúp các chính sách có cấu trúc nhất quán nhưng vẫn tách biệt trách nhiệm. Ví dụ, thời gian timeout của TimeLimiter không phải là thời gian OPEN của Circuit Breaker; số lần thử của Retry cũng không liên quan đến kích thước sliding window.

## 7. Liên kết tên instance với Spring Cloud CircuitBreaker

Khi sử dụng Spring Cloud CircuitBreaker với implementation Resilience4j, code tạo breaker theo ID. ID cần khớp với tên instance trong cấu hình Resilience4j.

Ví dụ:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryClient {

    private final CircuitBreaker inventoryBreaker;

    public InventoryClient(CircuitBreakerFactory<?, ?> factory) {
        this.inventoryBreaker = factory.create("inventory");
    }
}
~~~

Với reactive API:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class ReactiveInventoryClient {

    private final ReactiveCircuitBreaker inventoryBreaker;

    public ReactiveInventoryClient(
            ReactiveCircuitBreakerFactory<?, ?> factory) {
        this.inventoryBreaker = factory.create("inventory");
    }
}
~~~

Trong cả hai trường hợp, ID inventory được dùng để lựa chọn cấu hình instance inventory. Nếu instance đó khai báo baseConfig: shared, các giá trị chung của shared sẽ được áp dụng, sau đó các giá trị riêng của inventory sẽ ghi đè.

Factory là API của Spring Cloud CircuitBreaker; baseConfig là cơ chế tái sử dụng cấu hình của Resilience4j. Hai thành phần phối hợp qua ID instance, nhưng có vai trò khác nhau. Không nên nhầm baseConfig với phương thức cấu hình mặc định của factory trong Java hoặc với cấu hình mặc định của một implementation Circuit Breaker khác.

## 8. Tổ chức cấu hình theo môi trường

Các môi trường local, test, staging và production có thể cần các giá trị khác nhau. Có thể giữ cấu trúc nhóm dùng chung và instance ổn định, sau đó điều chỉnh một số giá trị theo Spring profile.

Ví dụ cấu hình cơ sở trong application.yml:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      shared:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
    instances:
      inventory:
        baseConfig: shared
      payment:
        baseConfig: shared
~~~

Ví dụ application-prod.yml ghi đè một số thuộc tính riêng:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 100
        failureRateThreshold: 40
      payment:
        waitDurationInOpenState: 30s
        failureRateThreshold: 25
~~~

Cần quản lý việc hợp nhất cấu hình giữa các profile theo cơ chế cấu hình Spring Boot của dự án. Khi một profile được kích hoạt, hãy kiểm tra giá trị hiệu lực của từng instance để bảo đảm không vô tình thay đổi chính sách chung. Tránh sao chép toàn bộ cấu hình shared vào file profile nếu chỉ cần điều chỉnh một vài thuộc tính.

Các profile nên được kiểm soát trong mã nguồn hoặc hệ thống quản lý cấu hình có kiểm soát phiên bản. Không nên thay đổi ngưỡng production tùy tiện mà không theo dõi tác động đến tỷ lệ lỗi, fallback và tải dependency.

## 9. Những lỗi thường gặp với baseConfig

- **Tham chiếu sai tên nhóm**: baseConfig trỏ đến tên không tồn tại trong configs của cùng module. Cần kiểm tra chính tả và vị trí khai báo.
- **Đặt baseConfig sai cấp YAML**: baseConfig phải nằm bên trong instance, cùng cấp với các thuộc tính được ghi đè.
- **Dùng nhầm nhóm giữa các module**: nhóm trong circuitbreaker không phải nhóm trong retry hoặc timelimiter.
- **Cho rằng nhóm shared tự động áp dụng cho mọi instance**: instance cần tham chiếu rõ ràng bằng baseConfig.
- **Sao chép toàn bộ cấu hình vào từng instance**: việc này tạo nhiều nguồn sự thật và làm các thay đổi khó đồng bộ.
- **Ghi đè quá nhiều thuộc tính**: instance có thể lệch khỏi chính sách chung mà không có lý do vận hành rõ ràng.
- **Đặt một nhóm dùng chung cho dependency không cùng đặc tính**: ngưỡng chung có thể quá nhạy với dịch vụ này nhưng lại quá chậm với dịch vụ khác.
- **Không kiểm tra cấu hình sau khi đổi profile**: giá trị cuối cùng có thể khác kỳ vọng do các lớp cấu hình được hợp nhất.
- **Nhầm baseConfig với fallback của request**: baseConfig kế thừa thuộc tính cấu hình; fallback là luồng xử lý khi lời gọi thất bại hoặc bị từ chối.

## 10. Quy trình xây dựng cấu hình dùng chung

Khi tổ chức baseConfig cho một ứng dụng Spring Cloud CircuitBreaker, có thể thực hiện theo trình tự:

1. Liệt kê các dependency và xác định đặc tính vận hành của từng dependency.
2. Nhóm các dependency có cùng yêu cầu về độ nhạy lỗi, thời gian phục hồi và lưu lượng.
3. Tạo các nhóm cấu hình trong configs của từng module Resilience4j.
4. Khai báo instance trong instances và tham chiếu nhóm phù hợp bằng baseConfig.
5. Chỉ ghi đè tại instance những thuộc tính thật sự cần khác biệt.
6. Bảo đảm ID truyền vào CircuitBreakerFactory hoặc ReactiveCircuitBreakerFactory khớp tên instance.
7. Tổ chức thay đổi theo Spring profile mà vẫn giữ cấu trúc nhóm chung rõ ràng.
8. Quan sát trạng thái Circuit Breaker, retry, timeout, bulkhead, rate limiter và fallback để điều chỉnh chính sách dựa trên dữ liệu.

baseConfig giúp các instance tái sử dụng một chính sách cấu hình thống nhất. Nhóm configs đóng vai trò mẫu dùng chung; instances đại diện cho các Circuit Breaker cụ thể; thuộc tính khai báo riêng tại instance ghi đè giá trị kế thừa. Khi phân nhóm theo đặc tính dependency và giữ ID nhất quán giữa code với YAML, cấu hình Resilience4j trong Spring Cloud dễ đọc, dễ bảo trì và ít sai lệch hơn khi hệ thống phát triển.
