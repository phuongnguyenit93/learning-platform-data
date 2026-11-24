# Tổ chức resilience4j.circuitbreaker.configs và instances

Trong Spring Cloud CircuitBreaker sử dụng Resilience4j, cấu hình Circuit Breaker được tổ chức theo hai nhóm chính: `configs` và `instances`. `configs` chứa các bộ cấu hình dùng lại được; `instances` khai báo những Circuit Breaker thực tế mà ứng dụng tạo ra cho từng dịch vụ hoặc thao tác phụ thuộc. Cách tổ chức này giúp nhiều lời gọi chia sẻ chính sách bảo vệ chung nhưng vẫn có thể điều chỉnh ngưỡng riêng theo đặc tính của từng phụ thuộc.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, ta dùng Circuit Breaker để ngăn lỗi dây chuyền khi dịch vụ phụ thuộc chậm hoặc không khả dụng. Vì mỗi phụ thuộc có lưu lượng, độ trễ và mức độ quan trọng khác nhau, việc tổ chức cấu hình rõ ràng giúp kiểm soát trạng thái CLOSED, OPEN, HALF_OPEN, sliding window và phương án fallback một cách nhất quán.

## 1. Vai trò của configs và instances

Hai nhóm cấu hình có mục đích khác nhau:

| Nhóm | Vai trò | Ví dụ |
| --- | --- | --- |
| `resilience4j.circuitbreaker.configs` | Khai báo các bộ tham số có thể tái sử dụng, thường gồm cấu hình mặc định và cấu hình theo loại phụ thuộc | `default`, `read-service`, `payment-service` |
| `resilience4j.circuitbreaker.instances` | Khai báo từng Circuit Breaker có tên cụ thể mà ứng dụng sử dụng | `inventory`, `payment`, `customer-profile` |

Có thể hình dung `configs` như mẫu chính sách, còn `instances` là các Circuit Breaker được tạo theo chính sách đó. Một instance có thể tham chiếu một cấu hình cơ sở bằng thuộc tính `baseConfig`, rồi ghi đè một vài tham số nếu phụ thuộc đó cần hành vi riêng.

Ví dụ, nhiều dịch vụ có thể cùng dùng sliding window kích thước 20 và ngưỡng lỗi 50%. Tuy nhiên, dịch vụ thanh toán có thể cần thời gian OPEN dài hơn dịch vụ đọc danh mục. Ta đặt tham số chung trong một config, sau đó chỉ ghi đè thời gian chờ ở instance thanh toán.

## 2. Cấu trúc YAML cơ bản

Cấu hình thường được đặt trong `application.yml` của ứng dụng Spring Boot hoặc trong file cấu hình theo profile đang chạy:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
        automaticTransitionFromOpenToHalfOpenEnabled: true
    instances:
      inventory:
        baseConfig: default
      customer-profile:
        baseConfig: default
      payment:
        baseConfig: default
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Trong ví dụ:

- `configs.default` định nghĩa chính sách chung.
- `instances.inventory` và `instances.customer-profile` kế thừa các tham số từ `default`.
- `instances.payment` cũng kế thừa `default`, nhưng thay thời gian OPEN thành 30 giây và chỉ cho phép 2 lời gọi thử nghiệm trong HALF_OPEN.

Các instance cần được đặt tên theo định danh mà ứng dụng dùng khi tạo Circuit Breaker. Với Spring Cloud CircuitBreaker, nếu code gọi `circuitBreakerFactory.create("inventory")`, phần cấu hình tương ứng là `instances.inventory`. Tên phải khớp để cấu hình mong muốn được áp dụng cho đúng lời gọi.

## 3. Kế thừa và ghi đè bằng baseConfig

Thuộc tính `baseConfig` cho biết instance sử dụng bộ cấu hình nào làm nền. Những thuộc tính không khai báo lại ở instance sẽ lấy từ config cơ sở; thuộc tính được khai báo trực tiếp tại instance sẽ thay thế giá trị kế thừa tương ứng. Mỗi instance tham chiếu một config cụ thể; hãy khai báo đầy đủ chính sách cần dùng trong config đó thay vì giả định các config khác tự kế thừa lẫn nhau.

Ví dụ, có thể tách các chính sách theo nhóm thao tác:

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
        permittedNumberOfCallsInHalfOpenState: 5
      read-service:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
      critical-write:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 30
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 5
    instances:
      product-catalog:
        baseConfig: read-service
      inventory:
        baseConfig: read-service
        slidingWindowSize: 40
      order-write:
        baseConfig: critical-write
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Ở đây, `read-service` và `critical-write` là hai chính sách độc lập. `product-catalog` sử dụng chính sách đọc. `inventory` sử dụng cùng chính sách nhưng tăng kích thước cửa sổ. `order-write` sử dụng chính sách ghi quan trọng và giới hạn số lời gọi thử nghiệm ở HALF_OPEN.

Khi đọc cấu hình, hãy lần theo `instances.<name>.baseConfig` đến config được tham chiếu, sau đó xem các thuộc tính ghi đè tại instance. Tránh sao chép toàn bộ tham số chung vào mọi instance vì cách đó làm cấu hình dài và khó đồng bộ khi chính sách chung thay đổi. Các config đặt trong `configs` là những bộ chính sách được đặt tên; instance chọn một bộ thông qua `baseConfig`.

Tên config là tên do ứng dụng đặt để tham chiếu. Tên instance là định danh Circuit Breaker được sử dụng trong code. Hai tên này có thể giống hoặc khác nhau; điều quan trọng là `baseConfig` phải trỏ đến đúng config và tên instance phải khớp với tên được tạo trong ứng dụng.

## 4. Những tham số thường đặt trong config

Các tham số trong config mô tả cách Circuit Breaker quan sát kết quả và quyết định chuyển trạng thái:

| Thuộc tính | Ý nghĩa | Lưu ý khi chọn |
| --- | --- | --- |
| `slidingWindowType` | Chọn `COUNT_BASED` hoặc `TIME_BASED` | Chọn theo cách muốn quan sát số lời gọi hoặc khoảng thời gian |
| `slidingWindowSize` | Số lời gọi trong cửa sổ COUNT_BASED hoặc số giây trong cửa sổ TIME_BASED | Cửa sổ lớn ổn định hơn nhưng có thể phản ứng chậm |
| `minimumNumberOfCalls` | Số kết quả tối thiểu trước khi tính tỷ lệ | Tránh quyết định từ quá ít mẫu |
| `failureRateThreshold` | Ngưỡng phần trăm lời gọi thất bại để mở mạch | Cân bằng khả năng phát hiện lỗi và nhiễu ngẫu nhiên |
| `slowCallDurationThreshold` | Thời lượng từ đó lời gọi được xem là chậm | Nên dựa trên độ trễ bình thường của phụ thuộc |
| `slowCallRateThreshold` | Ngưỡng phần trăm lời gọi chậm | Phát hiện suy giảm hiệu năng ngay cả khi lời gọi vẫn thành công |
| `waitDurationInOpenState` | Thời gian duy trì OPEN trước khi thử phục hồi | Tránh thử lại quá sớm khi phụ thuộc chưa ổn định |
| `permittedNumberOfCallsInHalfOpenState` | Số lời gọi thử được phép trong HALF_OPEN | Giới hạn tải khi kiểm tra khả năng phục hồi |
| `automaticTransitionFromOpenToHalfOpenEnabled` | Cho phép tự chuyển từ OPEN sang HALF_OPEN sau thời gian chờ | Hữu ích khi muốn chuyển trạng thái mà không chờ một lời gọi mới |

Ví dụ, với `COUNT_BASED` và `slidingWindowSize: 20`, cửa sổ quan sát 20 lời gọi gần nhất. Với `TIME_BASED` và `slidingWindowSize: 10`, cửa sổ quan sát kết quả trong 10 giây gần nhất. `minimumNumberOfCalls` vẫn cần được đặt đủ hợp lý để tránh tính tỷ lệ khi dữ liệu trong cửa sổ còn quá ít.

Giá trị thời gian như `10s`, `1500ms` giúp YAML dễ đọc. Hãy dùng kiểu giá trị thời gian được Spring Boot và phiên bản Resilience4j đang sử dụng hỗ trợ.

## 5. Tạo cấu hình riêng cho từng phụ thuộc

Không phải dịch vụ nào cũng nên dùng cùng một ngưỡng. Dịch vụ đọc hồ sơ có thể chịu được vài giây chờ và có thể dùng cache. Dịch vụ thanh toán có thể yêu cầu phản hồi nhanh, đồng thời cần thận trọng khi thử lại vì thao tác có tác động tài chính.

Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
      fast-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 40
      payment-protection:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 30
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 1
    instances:
      customer-profile:
        baseConfig: fast-read
      inventory:
        baseConfig: default
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
      payment:
        baseConfig: payment-protection
~~~

Trong cấu hình này, các lời gọi đọc hồ sơ được xem là chậm khi vượt 800 ms; tồn kho có ngưỡng chậm 2 giây; thanh toán dùng ngưỡng lỗi thấp hơn, thời gian OPEN dài hơn và chỉ cho phép một lời gọi thử nghiệm. Đây là giá trị minh họa để thể hiện cách tổ chức, không phải khuyến nghị áp dụng nguyên xi cho mọi hệ thống.

Khi thiết kế config theo nhóm, nên gom các phụ thuộc có mục tiêu độ trễ và cách phục hồi tương tự. Không nên dùng chung một chính sách chỉ vì các dịch vụ cùng loại giao thức HTTP; một dịch vụ tìm kiếm và một dịch vụ thanh toán có thể có yêu cầu vận hành rất khác nhau.

## 6. Phân loại exception trong cấu hình

Resilience4j cho phép xác định exception nào được tính là lỗi và exception nào được bỏ qua. Việc này quan trọng vì không phải mọi lỗi đều cho thấy dịch vụ phụ thuộc đang hỏng. Ví dụ, sản phẩm không tồn tại có thể là kết quả nghiệp vụ hợp lệ, trong khi lỗi kết nối hoặc lỗi máy chủ thường phản ánh sự cố phụ thuộc.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        recordExceptions:
          - java.io.IOException
        ignoreExceptions:
          - com.example.inventory.ProductNotFoundException
    instances:
      inventory:
        baseConfig: default
~~~

Các tên exception trong danh sách cần là tên lớp đầy đủ đúng với ứng dụng thực tế. Trong ví dụ, lỗi I/O được ghi nhận là lỗi; lỗi không tìm thấy sản phẩm được bỏ qua khi tính tỷ lệ. Cần hiểu chính sách của Resilience4j: khi khai báo `recordExceptions`, các exception không khớp danh sách ghi nhận không mặc nhiên được xem như lỗi; `ignoreExceptions` được bỏ qua trong phép tính. Hãy phân loại exception theo ý nghĩa nghiệp vụ và loại lỗi thực tế của HTTP client hoặc thư viện truy cập dịch vụ.

Nếu mọi exception đều bị ghi nhận, các lỗi đầu vào hoặc nghiệp vụ có thể khiến Circuit Breaker mở sai. Ngược lại, nếu bỏ qua quá nhiều exception, mạch có thể không mở dù phụ thuộc đang thực sự lỗi.

## 7. Kết nối tên instance với code

Cấu hình chỉ có tác dụng với lời gọi sử dụng đúng định danh Circuit Breaker. Với Spring Cloud CircuitBreaker abstraction, code thường tạo instance theo tên:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResult getInventory(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> inventoryClient.get(sku),
                failure -> InventoryResult.unavailable(sku)
        );
    }
}
~~~

Vì code gọi `create("inventory")`, cấu hình cần có `resilience4j.circuitbreaker.instances.inventory`. Instance này có thể dùng `baseConfig: default`, `baseConfig: read-service` hoặc một config phù hợp khác.

Nếu tên trong code và tên trong YAML không khớp, ứng dụng có thể tạo Circuit Breaker với cấu hình mặc định thay vì bộ tham số mà người phát triển dự định. Vì vậy, khi thêm một lời gọi phụ thuộc mới, cần cập nhật đồng thời tên instance và cấu hình tương ứng.

## 8. Phân biệt cấu hình Circuit Breaker với các cơ chế khác

Prefix `resilience4j.circuitbreaker` dành cho chính sách Circuit Breaker. Timeout và bulkhead có nhóm cấu hình riêng; không đặt các thuộc tính của chúng vào bên trong `circuitbreaker.configs` hoặc `circuitbreaker.instances`.

| Cơ chế | Nhóm cấu hình thường dùng | Mục đích |
| --- | --- | --- |
| Circuit Breaker | `resilience4j.circuitbreaker` | Mở mạch khi tỷ lệ lỗi hoặc lời gọi chậm vượt ngưỡng |
| TimeLimiter | `resilience4j.timelimiter` | Giới hạn thời gian chờ cho thao tác phù hợp |
| Bulkhead | `resilience4j.bulkhead` hoặc `resilience4j.thread-pool-bulkhead` | Giới hạn số lời gọi hoặc tác vụ đồng thời |
| Retry | `resilience4j.retry` | Thử lại có giới hạn khi gặp lỗi được chọn |

Các cơ chế có thể phối hợp, nhưng mỗi cơ chế cần được cấu hình và theo dõi đúng vai trò. Ví dụ, `slowCallDurationThreshold` giúp Circuit Breaker nhận diện lời gọi chậm; nó không thay thế timeout để kết thúc một lời gọi đang chờ. Bulkhead giới hạn tài nguyên đồng thời; nó không tự quyết định phụ thuộc đã phục hồi hay chưa.

## 9. Những lỗi thường gặp khi tổ chức configs và instances

| Lỗi cấu hình | Hậu quả có thể gặp | Cách kiểm tra |
| --- | --- | --- |
| Đặt tham số trong `instances` nhưng code tạo tên khác | Instance dự kiến không được sử dụng | Đối chiếu `create("...")` với khóa dưới `instances` |
| `baseConfig` trỏ đến tên config không tồn tại | Không thể áp dụng bộ cấu hình kế thừa như mong muốn | Kiểm tra tên trong `configs` và `baseConfig` |
| Chép các giá trị chung vào mọi instance | Cấu hình trùng lặp, khó bảo trì | Chuyển giá trị dùng chung vào config cơ sở |
| Cửa sổ quá nhỏ hoặc `minimumNumberOfCalls` quá thấp | Mạch có thể mở do một vài lỗi ngẫu nhiên | Đối chiếu lưu lượng và số mẫu thực tế |
| Ngưỡng lời gọi chậm không sát độ trễ bình thường | Mạch mở quá sớm hoặc phát hiện quá muộn | Đo độ trễ thực tế trước khi đặt ngưỡng |
| Ghi nhận mọi lỗi nghiệp vụ như lỗi phụ thuộc | Circuit Breaker có thể mở dù dịch vụ vẫn khỏe | Xem lại `recordExceptions` và `ignoreExceptions` |
| Đặt timeout hoặc bulkhead trong nhầm prefix | Cấu hình không được binder của cơ chế tương ứng sử dụng | Đặt mỗi thuộc tính trong nhóm cấu hình đúng |
| YAML sai thụt lề hoặc sai kiểu giá trị | Spring Boot không bind được giá trị mong muốn | Kiểm tra cấu trúc YAML và log khởi động |

Khi chẩn đoán, nên xác minh theo thứ tự: file cấu hình đang được nạp, prefix và thụt lề, tên instance trong code, tên config được tham chiếu, sau đó mới kiểm tra từng tham số và số liệu runtime.

## 10. Quy trình thêm một Circuit Breaker mới

Khi bảo vệ một phụ thuộc mới, có thể thực hiện theo trình tự:

1. Xác định tên ổn định cho Circuit Breaker, ví dụ `inventory`.
2. Chọn config cơ sở dựa trên đặc tính lưu lượng và độ trễ của phụ thuộc.
3. Khai báo `instances.inventory` và trỏ `baseConfig` đến config đã chọn.
4. Chỉ ghi đè những thuộc tính thực sự khác với chính sách chung.
5. Dùng đúng tên `inventory` khi tạo Circuit Breaker trong code.
6. Kiểm tra hành vi ở CLOSED, OPEN và HALF_OPEN; quan sát tỷ lệ lỗi, tỷ lệ lời gọi chậm và số lần bị từ chối.
7. Điều chỉnh ngưỡng theo số liệu thực tế thay vì chỉ dựa trên giá trị minh họa.

Ví dụ, nếu dịch vụ Kho có độ trễ bình thường cao hơn dịch vụ hồ sơ, ta có thể tạo config riêng cho nhóm đọc kho với `slowCallDurationThreshold` phù hợp. Nếu dịch vụ thanh toán cần bảo vệ chặt hơn, instance thanh toán có thể kế thừa config chung rồi đặt `waitDurationInOpenState` dài hơn và giới hạn số lời gọi thử nghiệm.

## 11. Tình huống tổng hợp

Một hệ thống có ba phụ thuộc: dịch vụ Hồ sơ khách hàng, dịch vụ Kho và dịch vụ Thanh toán. Nhóm phát triển chọn một config chung để thống nhất sliding window và ngưỡng lỗi. Hồ sơ và Kho dùng chính sách đọc, trong khi Thanh toán dùng chính sách riêng với thời gian OPEN dài hơn.

Khi dịch vụ Kho chậm, instance `inventory` ghi nhận tỷ lệ lời gọi chậm. Nếu tỷ lệ đạt ngưỡng sau khi có đủ mẫu, mạch chuyển từ CLOSED sang OPEN. Sau thời gian chờ, mạch chuyển sang HALF_OPEN và chỉ cho phép số lời gọi thử nghiệm đã cấu hình. Trong khi đó, lỗi của Kho không làm thay đổi trạng thái Circuit Breaker của Thanh toán vì hai phụ thuộc dùng hai instance riêng.

Khi phân tích tình huống, hãy tự trả lời:

- Vì sao đặt chính sách chung trong `configs.default`?
- Khi nào nên tạo config riêng thay vì ghi đè nhiều thuộc tính ở từng instance?
- Tên `inventory` trong code liên hệ thế nào với `instances.inventory`?
- `baseConfig` và giá trị khai báo trực tiếp ở instance phối hợp ra sao?
- Vì sao timeout và bulkhead thuộc nhóm cấu hình khác Circuit Breaker?
- Cần quan sát chỉ số nào để biết ngưỡng đang bảo vệ hệ thống hiệu quả?

Tổ chức tốt `resilience4j.circuitbreaker.configs` và `instances` giúp chính sách bảo vệ có thể tái sử dụng, dễ đọc và điều chỉnh theo từng phụ thuộc. Khi kết hợp đúng tên instance, ngưỡng sliding window và số liệu vận hành, ứng dụng Spring Cloud có thể kiểm soát chuyển trạng thái Circuit Breaker và hạn chế lỗi dây chuyền một cách có chủ đích.
