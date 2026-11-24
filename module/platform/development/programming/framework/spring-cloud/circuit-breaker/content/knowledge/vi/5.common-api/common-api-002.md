# Tạo bộ ngắt mạch bằng ID ổn định

Trong Spring Cloud CircuitBreaker, ứng dụng tạo một bộ ngắt mạch thông qua factory và truyền vào một định danh, thường là tên dịch vụ phụ thuộc hoặc thao tác gọi dịch vụ. Ví dụ, khi dịch vụ đặt hàng gọi dịch vụ tồn kho để đọc số lượng sản phẩm, ứng dụng có thể dùng ID inventory-read.

ID ổn định giúp ứng dụng luôn truy cập đúng bộ ngắt mạch cho cùng một luồng gọi. ID này còn là điểm nối giữa mã nguồn, cấu hình Resilience4j và số liệu giám sát. Khi tên thay đổi theo từng yêu cầu, ứng dụng có thể tạo ra nhiều bộ ngắt mạch với trạng thái và số liệu bị chia nhỏ, khiến cấu hình khó áp dụng và việc quan sát trở nên thiếu tin cậy.

## ID của circuit breaker dùng để làm gì?

Spring Cloud CircuitBreaker cung cấp CircuitBreakerFactory để tạo bộ ngắt mạch theo tên:

~~~java
CircuitBreaker circuitBreaker = circuitBreakerFactory.create("inventory-read");
~~~

Với backend Resilience4j, ID được dùng để xác định instance circuit breaker. ID này thường được đối chiếu với tên instance trong cấu hình, đồng thời xuất hiện trong số liệu giám sát như một nhãn nhận diện. Vì vậy, cùng một luồng gọi cần sử dụng cùng một ID qua các lần thực thi.

ID ổn định có ba vai trò:

- **Nhận diện luồng gọi:** cho biết bộ ngắt mạch đang bảo vệ lời gọi đến phụ thuộc hoặc thao tác nghiệp vụ nào.
- **Áp dụng cấu hình:** giúp instance nhận đúng các ngưỡng và thời gian đã khai báo trong application.yml.
- **Theo dõi vận hành:** giúp nhóm phát triển và vận hành lọc số liệu theo một tên nhất quán giữa các lần chạy và các bản sao ứng dụng.

ID không đại diện cho một yêu cầu HTTP cụ thể, một người dùng hay một đơn hàng. Nó đại diện cho một loại lời gọi mà ứng dụng muốn bảo vệ bằng cùng chính sách circuit breaker.

## Chọn phạm vi của một ID

Hãy chọn ID theo đặc tính lỗi và chính sách phục hồi của lời gọi. Nếu hai thao tác có cùng phụ thuộc, cùng đặc tính độ trễ và cùng cách fallback, chúng có thể dùng chung một bộ ngắt mạch. Nếu một thao tác đọc dữ liệu và một thao tác ghi dữ liệu có mức độ quan trọng, ngưỡng hoặc cách phục hồi khác nhau, nên tách thành hai ID.

Ví dụ với hệ thống đặt hàng:

| ID ổn định | Luồng được bảo vệ | Lý do |
|---|---|---|
| inventory-read | Đọc thông tin tồn kho | Có thể dùng cache gần nhất nếu nghiệp vụ cho phép. |
| inventory-reserve | Giữ chỗ số lượng tồn kho | Cần phản ánh chính xác kết quả ghi và không được giả định thao tác thành công. |
| payment-authorize | Yêu cầu cổng thanh toán cấp phép | Có chính sách timeout, lỗi và xử lý kết quả không xác định riêng. |

Nếu dùng chung một ID cho các luồng có hành vi khác nhau, kết quả của một luồng có thể làm bộ ngắt mạch mở và ảnh hưởng đến luồng còn lại. Chẳng hạn, lỗi từ thao tác giữ chỗ tồn kho có thể làm gián đoạn cả thao tác đọc tồn kho dù thao tác đọc vẫn hoạt động bình thường.

Ngược lại, không nên tách ID chỉ vì mỗi URL có một giá trị tham số khác nhau. Nếu các endpoint có cùng đặc tính vận hành và cùng chính sách bảo vệ, việc tạo ID riêng cho từng URL có thể làm phân tán số liệu và khiến mỗi bộ ngắt mạch có quá ít mẫu để đánh giá.

## Quy ước đặt tên ổn định

Một quy ước hữu ích là dùng tên dịch vụ phụ thuộc kết hợp với thao tác nghiệp vụ, viết thường và phân tách bằng dấu gạch ngang:

- Dễ đọc và mô tả được mục tiêu bảo vệ.
- Không chứa dữ liệu thay đổi theo yêu cầu.
- Giữ nguyên giữa các lần khởi động và các bản sao của cùng ứng dụng.
- Khớp chính xác với tên instance trong cấu hình khi dùng Resilience4j.

Có thể tập trung các tên vào một lớp hằng số:

~~~java
public final class CircuitBreakerIds {

    public static final String INVENTORY_READ = "inventory-read";
    public static final String INVENTORY_RESERVE = "inventory-reserve";
    public static final String PAYMENT_AUTHORIZE = "payment-authorize";

    private CircuitBreakerIds() {
    }
}
~~~

Lớp hằng số giúp tránh lỗi gõ sai tên và làm rõ những luồng gọi nào đang được bảo vệ. Khi đổi tên một ID, cần cập nhật đồng bộ các nơi sử dụng và cấu hình instance tương ứng.

Không đưa các giá trị sau vào ID:

| Không nên dùng | Ví dụ | Vấn đề |
|---|---|---|
| Mã đơn hàng | order-93821 | Mỗi đơn hàng có thể tạo một tên mới và chia nhỏ trạng thái. |
| Mã người dùng | customer-1042 | Tạo số lượng instance và nhãn metrics tăng theo người dùng. |
| UUID ngẫu nhiên | 9c1... | Không thể ánh xạ ổn định với cấu hình hoặc số liệu giữa các lần chạy. |
| Tham số URL | inventory-sku-ABC | Số lượng ID tăng theo dữ liệu đầu vào. |
| Tên có timestamp | inventory-2026-11-24T10:00 | Mỗi khoảng thời gian tạo ra một định danh khác. |

Nếu ID thay đổi theo từng yêu cầu, registry có thể tích lũy nhiều instance và hệ thống metrics có thể phát sinh cardinality cao. Mỗi instance cũng chỉ nhận được một phần lưu lượng, khiến cửa sổ trượt thiếu mẫu và ngưỡng lỗi hoặc lời gọi chậm khó phản ánh chính xác tình trạng phụ thuộc.

## Tạo và sử dụng bộ ngắt mạch trong lời gọi đồng bộ

Ví dụ sau bảo vệ thao tác đọc tồn kho. Bộ ngắt mạch được tạo từ factory với ID cố định và được lưu trong client để các lần gọi cùng sử dụng một định danh.

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {

    private final RestClient restClient;
    private final CircuitBreaker inventoryReadBreaker;

    public InventoryClient(
            RestClient.Builder builder,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restClient = builder
                .baseUrl("http://inventory-service")
                .build();

        this.inventoryReadBreaker =
                circuitBreakerFactory.create(CircuitBreakerIds.INVENTORY_READ);
    }

    public Inventory findInventory(String sku) {
        return inventoryReadBreaker.run(
                () -> restClient.get()
                        .uri("/inventory/{sku}", sku)
                        .retrieve()
                        .body(Inventory.class),
                error -> Inventory.unavailable(sku)
        );
    }
}
~~~

Inventory, phương thức Inventory.unavailable và CircuitBreakerIds là các thành phần minh họa của ứng dụng. Trong dự án thực tế, hãy thay chúng bằng mô hình dữ liệu và lớp hằng số của dự án.

Mỗi lần findInventory được gọi, cùng một bộ ngắt mạch inventory-read sẽ ghi nhận kết quả của lời gọi. Khi mạch đang CLOSED, lời gọi được chuyển đến dịch vụ tồn kho. Nếu tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng, mạch có thể chuyển sang OPEN. Những lần gọi tiếp theo bị từ chối nhanh và hàm fallback có thể trả dữ liệu dự phòng.

Fallback cần phản ánh đúng ý nghĩa nghiệp vụ. Nếu dữ liệu cache có thể chấp nhận cho màn hình tham khảo, ứng dụng có thể trả dữ liệu gần nhất và đánh dấu dữ liệu đã cũ. Nếu thao tác cần số lượng tồn kho chính xác để xác nhận đơn hàng, không được giả định rằng tồn kho vẫn đủ khi dịch vụ không phản hồi.

## Khớp ID với cấu hình Resilience4j

Khi sử dụng Spring Cloud CircuitBreaker với Resilience4j, tên instance trong application.yml cần khớp với ID truyền vào factory. Ví dụ, mã nguồn gọi create("inventory-read") thì cấu hình tương ứng nằm dưới instances.inventory-read:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
      inventory-reserve:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
        slowCallDurationThreshold: 500ms
        slowCallRateThreshold: 40
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Trong ví dụ, inventory-read và inventory-reserve có chính sách riêng. Thao tác giữ chỗ có thể cần ngưỡng thận trọng hơn vì ảnh hưởng trực tiếp đến dữ liệu nghiệp vụ. Các con số chỉ minh họa cách gắn cấu hình theo ID; cần điều chỉnh chúng theo độ trễ, lưu lượng và yêu cầu của từng hệ thống.

Nếu ID trong mã nguồn không khớp với tên instance cấu hình, bộ ngắt mạch có thể sử dụng cấu hình mặc định thay vì bộ ngưỡng mà nhóm phát triển mong đợi. Khi đổi tên ID, hãy tìm và cập nhật cả hằng số, vị trí gọi factory, cấu hình và các truy vấn dashboard hoặc cảnh báo đang lọc theo tên cũ.

## Dùng ID ổn định trong lời gọi reactive

Với WebClient và Reactor, dùng ReactiveCircuitBreakerFactory để tạo bộ ngắt mạch reactive. ID vẫn là tên ổn định của luồng gọi; không đưa mã SKU hay mã đơn hàng vào tên bộ ngắt mạch.

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class ReactiveInventoryClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker inventoryReadBreaker;

    public ReactiveInventoryClient(
            WebClient.Builder builder,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();

        this.inventoryReadBreaker =
                circuitBreakerFactory.create(CircuitBreakerIds.INVENTORY_READ);
    }

    public Mono<Inventory> findInventory(String sku) {
        Mono<Inventory> request = webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class);

        return inventoryReadBreaker.run(
                request,
                error -> Mono.just(Inventory.unavailable(sku))
        );
    }
}
~~~

Chuỗi reactive tiếp tục trả về Mono và không cần gọi block để chờ kết quả. Việc tạo bộ ngắt mạch bằng ID cố định giúp mọi yêu cầu đi qua cùng một chính sách bảo vệ. Nếu một thao tác reactive có đặc tính vận hành khác với thao tác đồng bộ, hãy cân nhắc dùng ID riêng để tách chính sách và số liệu; nếu chúng thực sự là cùng một luồng logic thì có thể dùng chung ID một cách có chủ đích.

## ID ổn định và số liệu giám sát

ID thường được dùng làm nhãn nhận diện bộ ngắt mạch trong số liệu Resilience4j và Micrometer. Nhờ tên ổn định, nhóm vận hành có thể so sánh trạng thái và tỷ lệ lỗi của cùng một luồng gọi qua nhiều khoảng thời gian.

Khi theo dõi, cần quan sát:

- Trạng thái CLOSED, OPEN và HALF_OPEN theo từng ID.
- Số lời gọi thành công, thất bại, chậm và bị từ chối.
- Failure rate, slow call rate và độ trễ.
- Số lần fallback được gọi.
- Số lần circuit breaker chuyển trạng thái.

Tên ID nhất quán giúp dashboard và cảnh báo có thể nhóm số liệu theo thao tác nghiệp vụ. Tránh thêm mã người dùng, mã đơn hàng hoặc giá trị đầu vào vào tên ID, vì điều đó làm tăng số lượng chuỗi nhãn và khiến metrics khó tổng hợp.

Cũng cần hiểu phạm vi trạng thái. ID ổn định giúp các lời gọi trong cùng một tiến trình ứng dụng sử dụng đúng instance theo tên. Nó không tự tạo ra một circuit breaker phân tán dùng chung trạng thái giữa mọi máy chủ. Nếu ứng dụng chạy nhiều replica, mỗi replica thường theo dõi trạng thái bộ ngắt mạch trong tiến trình của mình; cùng một ID trên các replica giúp cấu hình và cách đọc metrics nhất quán, nhưng không có nghĩa trạng thái OPEN của replica này tự động mở mạch ở replica khác.

## Những lỗi thường gặp khi chọn ID

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Tạo ID từ dữ liệu request | Nhiều instance, cửa sổ thiếu mẫu và metrics cardinality cao. | Dùng hằng số theo dịch vụ hoặc thao tác nghiệp vụ. |
| Mã nguồn và YAML dùng tên khác nhau | Cấu hình riêng của instance không được áp dụng như dự kiến. | Dùng một nguồn hằng số cho mã nguồn và kiểm tra tên cấu hình. |
| Dùng một ID cho các thao tác có chính sách khác nhau | Lỗi của thao tác này có thể làm mở mạch ảnh hưởng thao tác kia. | Tách ID khi đặc tính lỗi, timeout hoặc fallback khác nhau. |
| Tách ID cho mọi endpoint dù cùng chính sách | Lưu lượng và kết quả bị chia nhỏ, khó đủ mẫu. | Nhóm các lời gọi có cùng đặc tính bảo vệ. |
| Đổi tên ID nhưng quên dashboard hoặc cảnh báo | Biểu đồ và cảnh báo vẫn truy vấn tên cũ. | Cập nhật đồng bộ cấu hình giám sát khi đổi tên. |
| Nghĩ ID giống nhau chia sẻ trạng thái giữa các replica | Kỳ vọng sai về hành vi khi triển khai nhiều instance. | Theo dõi trạng thái theo từng replica và thiết kế cảnh báo phù hợp. |

## Kiểm tra thiết kế trước khi đưa vào vận hành

Trước khi triển khai, hãy rà soát từng ID theo các câu hỏi sau:

1. ID có mô tả rõ dịch vụ phụ thuộc và thao tác được bảo vệ không?
2. ID có giữ nguyên giữa các yêu cầu, lần khởi động và các replica không?
3. ID có khớp chính xác với tên instance trong cấu hình Resilience4j không?
4. Các lời gọi dùng chung ID có thực sự có cùng đặc tính lỗi, timeout và fallback không?
5. Có bất kỳ mã người dùng, mã đơn hàng, UUID hoặc tham số URL nào lọt vào ID không?
6. Dashboard và cảnh báo có thể nhận diện bộ ngắt mạch bằng tên này không?

Có thể kiểm tra hành vi bằng cách tạo tải cho một luồng gọi, mô phỏng lỗi hoặc độ trễ từ dịch vụ phụ thuộc, rồi quan sát đúng ID chuyển trạng thái. Sau đó gửi yêu cầu với nhiều SKU hoặc mã đơn hàng khác nhau và xác nhận chúng vẫn được ghi nhận dưới cùng ID ổn định. Nếu số lượng ID tăng theo dữ liệu yêu cầu, cần sửa cách đặt tên trước khi triển khai rộng.

ID ổn định là nền tảng để cấu hình, trạng thái và số liệu của circuit breaker cùng mô tả một luồng gọi. Hãy đặt tên theo phụ thuộc và thao tác nghiệp vụ, dùng nhất quán trong factory và application.yml, rồi chỉ tách ID khi có lý do vận hành rõ ràng. Cách làm này giúp Spring Cloud CircuitBreaker bảo vệ đúng phạm vi và giúp nhóm vận hành đọc được tín hiệu khi dịch vụ phụ thuộc gặp sự cố.

