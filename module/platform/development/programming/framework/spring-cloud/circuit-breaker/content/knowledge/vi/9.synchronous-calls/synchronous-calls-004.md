# Truyền tham số và ánh xạ kết quả mà không tạo ID theo từng yêu cầu

Khi bảo vệ lời gọi đồng bộ bằng Spring Cloud CircuitBreaker và Resilience4j, mỗi Circuit Breaker cần một ID ổn định đại diện cho dịch vụ phụ thuộc hoặc thao tác được bảo vệ. Tham số của từng yêu cầu như mã sản phẩm, mã kho, mã đơn hàng hay người dùng được truyền vào lời gọi dịch vụ bên trong supplier. Những giá trị thay đổi theo yêu cầu không nên được ghép vào ID Circuit Breaker.

Cách tổ chức này giữ cho các lời gọi cùng một dịch vụ chia sẻ chung trạng thái CLOSED, OPEN hoặc HALF_OPEN và cùng sliding window. Ứng dụng vẫn có thể truyền đầy đủ tham số, nhận response, ánh xạ response sang mô hình nghiệp vụ và xử lý fallback cho từng yêu cầu. Đây là kỹ thuật quan trọng khi triển khai Circuit Breaker đồng bộ để ngăn lỗi dây chuyền mà không làm phân mảnh số liệu quan sát.

## 1. Phân biệt ID Circuit Breaker với tham số yêu cầu

ID Circuit Breaker xác định nhóm lời gọi có chung chính sách bảo vệ. Ví dụ, ứng dụng đặt hàng có thể dùng các ID ổn định:

| ID Circuit Breaker | Phạm vi được bảo vệ |
|---|---|
| **inventory-read** | Đọc số lượng tồn kho từ dịch vụ Inventory |
| **inventory-reserve** | Gửi yêu cầu giữ hàng đến dịch vụ Inventory |
| **catalog-product** | Lấy thông tin sản phẩm từ dịch vụ Catalog |
| **payment-authorize** | Yêu cầu dịch vụ Payment cấp phép thanh toán |

Các tham số của từng yêu cầu là dữ liệu đầu vào cho thao tác đó, ví dụ:

- **sku:** mã sản phẩm cần tra cứu.
- **warehouseCode:** mã kho cần kiểm tra.
- **orderId:** mã đơn hàng đang xử lý.
- **quantity:** số lượng cần giữ.
- **traceId:** mã tương quan để tìm log của một yêu cầu qua nhiều dịch vụ.

Một lần gọi có thể dùng ID **inventory-read** nhưng truyền các cặp tham số khác nhau như (SKU-001, HN-01) hoặc (SKU-002, HCM-02). Cả hai lời gọi vẫn đi qua cùng một Circuit Breaker vì chúng phụ thuộc vào cùng thao tác đọc tồn kho và cần được bảo vệ bằng cùng chính sách.

Không nên tạo các ID như **inventory-read-SKU-001**, **inventory-read-SKU-002** hoặc **inventory-read-order-12345**. Nếu tạo một Circuit Breaker riêng cho từng mã sản phẩm hay đơn hàng, trạng thái và sliding window sẽ bị chia nhỏ. Mỗi instance chỉ nhận một phần rất nhỏ lưu lượng nên khó đạt số mẫu tối thiểu để đánh giá tỷ lệ lỗi; metric cũng tăng số lượng định danh theo dữ liệu nghiệp vụ.

## 2. Truyền tham số qua supplier của lời gọi đồng bộ

API blocking của Spring Cloud CircuitBreaker cho phép truyền một supplier chứa thao tác cần được bảo vệ. Supplier được thực thi khi Circuit Breaker cho phép lời gọi. Lambda có thể sử dụng các biến đầu vào của phương thức hiện tại:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryGateway {

    private static final String INVENTORY_READ = "inventory-read";

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    InventoryResponse getInventory(String sku, String warehouseCode) {
        return circuitBreakerFactory.create(INVENTORY_READ).run(
            () -> inventoryClient.getInventory(sku, warehouseCode),
            error -> InventoryResponse.unavailable(sku, warehouseCode)
        );
    }
}
~~~

Trong ví dụ:

1. **INVENTORY_READ** là ID cố định của Circuit Breaker.
2. **sku** và **warehouseCode** là tham số riêng của yêu cầu hiện tại.
3. Supplier gọi client với đúng các tham số đó.
4. Nếu Circuit Breaker đang OPEN, supplier không được thực thi và hàm fallback được gọi.
5. Response fallback có thể mang thông tin về SKU và kho để tầng gọi xử lý theo nghiệp vụ.

Mỗi lần gọi phương thức **getInventory** có thể tạo một lambda mới chứa giá trị SKU và kho khác nhau. Điều này không tạo Circuit Breaker mới. Factory nhận cùng ID **inventory-read**, vì vậy các lời gọi vẫn chia sẻ trạng thái và cấu hình của cùng bộ ngắt.

Nếu client có nhiều tham số, hãy truyền chúng theo chữ ký rõ ràng của client. Không cần nối chúng thành một chuỗi ID, cũng không cần lưu tham số trong một biến toàn cục để Circuit Breaker có thể truy cập. Supplier đã giữ các giá trị cần thiết cho lần thực thi đó.

## 3. Dùng ID ổn định để giữ chung sliding window

Circuit Breaker dựa trên kết quả của các lời gọi trước đó để quyết định chuyển trạng thái. Khi ID được giữ ổn định theo dependency hoặc operation, các lời gọi cùng loại sẽ đóng góp vào cùng cửa sổ đánh giá.

Giả sử **inventory-read** có cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Nếu mười lời gọi đọc tồn kho đầu tiên được thực hiện với nhiều SKU và nhiều kho khác nhau, chúng vẫn được ghi nhận trong cùng instance **inventory-read**. Khi đủ số mẫu tối thiểu, Circuit Breaker có thể đánh giá tỷ lệ lỗi trên tập kết quả chung. Nếu tỷ lệ lỗi đạt ngưỡng, các lời gọi đọc tồn kho tiếp theo sẽ bị từ chối trong thời gian OPEN, bất kể yêu cầu đang hỏi SKU nào.

Đây là hành vi mong muốn khi sự cố nằm ở dịch vụ Inventory hoặc đường kết nối chung. Nếu một mã SKU riêng lẻ gây lỗi nghiệp vụ do không tồn tại, cần xử lý nó như kết quả nghiệp vụ phù hợp thay vì mặc định xem đó là lỗi sức khỏe của toàn dịch vụ.

Nếu có hai thao tác phụ thuộc có đặc tính khác nhau, chẳng hạn đọc tồn kho và giữ hàng, hãy dùng hai ID ổn định riêng. Cả hai có thể gọi cùng một dịch vụ Inventory nhưng có endpoint, SLA, lưu lượng và ý nghĩa lỗi khác nhau. ID nên đại diện cho phạm vi mà ứng dụng muốn đo lường và bảo vệ.

## 4. Ánh xạ response sang mô hình nghiệp vụ

Dịch vụ phụ thuộc thường trả về một DTO hoặc response riêng. Tầng ứng dụng có thể ánh xạ response đó sang mô hình nghiệp vụ để các thành phần phía trên không phụ thuộc cấu trúc API bên ngoài.

Ví dụ, Inventory trả về **InventoryResponse**, còn nghiệp vụ đặt hàng sử dụng **StockAvailability**:

~~~java
record InventoryResponse(
    String sku,
    String warehouseCode,
    int availableQuantity,
    String sourceStatus
) {}

record StockAvailability(
    String productCode,
    String warehouse,
    int quantityAvailable,
    boolean available
) {}

class InventoryMapper {

    StockAvailability toDomain(InventoryResponse response) {
        return new StockAvailability(
            response.sku(),
            response.warehouseCode(),
            response.availableQuantity(),
            response.availableQuantity() > 0
        );
    }
}
~~~

Có hai vị trí thường dùng để thực hiện mapping. Việc chọn vị trí phụ thuộc vào việc lỗi mapping có nên được xem là lỗi của lời gọi được bảo vệ hay không.

### Mapping bên trong supplier

Nếu response không hợp lệ hoặc không thể ánh xạ được được xem là một thất bại của hợp đồng dịch vụ phụ thuộc, có thể thực hiện mapping ngay trong supplier:

~~~java
StockAvailability getAvailability(String sku, String warehouseCode) {
    return circuitBreakerFactory.create(INVENTORY_READ).run(
        () -> inventoryMapper.toDomain(
            inventoryClient.getInventory(sku, warehouseCode)
        ),
        error -> StockAvailabilityUnavailable.forItem(sku, warehouseCode)
    );
}
~~~

Trong trường hợp này, supplier chỉ hoàn tất thành công nếu cả lời gọi client và bước mapping đều thành công. Ngoại lệ phát sinh trong quá trình mapping cũng có thể được Circuit Breaker ghi nhận là lỗi của lần thực thi được bảo vệ. Cách làm phù hợp khi lỗi mapping cho thấy response từ dịch vụ phụ thuộc không đáp ứng hợp đồng mà ứng dụng yêu cầu.

### Mapping sau khi supplier hoàn tất

Nếu muốn Circuit Breaker chỉ đo lường kết quả của thao tác gọi dịch vụ phụ thuộc, hãy lấy response ra trước rồi mapping bên ngoài:

~~~java
StockAvailability getAvailability(String sku, String warehouseCode) {
    InventoryResponse response =
        circuitBreakerFactory.create(INVENTORY_READ).run(
            () -> inventoryClient.getInventory(sku, warehouseCode),
            error -> {
                throw new InventoryUnavailableException(
                    sku, warehouseCode, error
                );
            }
        );

    return inventoryMapper.toDomain(response);
}
~~~

Ở đây, Circuit Breaker bảo vệ lời gọi client. Nếu mapping thất bại sau khi client đã trả về thành công, ngoại lệ mapping không được tính vào kết quả của Circuit Breaker này. Cách làm phù hợp khi lỗi mapping là vấn đề cục bộ của ứng dụng, chẳng hạn mapper có lỗi hoặc một quy tắc chuyển đổi nội bộ không hợp lệ.

Nếu response sai cấu trúc là dấu hiệu dịch vụ phụ thuộc trả dữ liệu hỏng, mapping hoặc kiểm tra hợp đồng có thể được đặt bên trong supplier để lỗi đó được tính vào kết quả bảo vệ. Hãy quyết định rõ ranh giới cần đo lường thay vì đặt toàn bộ xử lý tùy tiện vào trong hoặc ngoài supplier.

## 5. Ánh xạ fallback về cùng kiểu kết quả

Với API đồng bộ, supplier và fallback phải trả về kiểu kết quả tương thích. Nếu supplier trả **InventoryResponse**, fallback cũng phải trả **InventoryResponse** hoặc ném ngoại lệ phù hợp. Nếu supplier trả **StockAvailability**, fallback phải trả **StockAvailability**.

Ví dụ dùng cache làm dữ liệu dự phòng:

~~~java
InventoryResponse getInventory(
        String sku,
        String warehouseCode) {

    return circuitBreakerFactory.create(INVENTORY_READ).run(
        () -> inventoryClient.getInventory(sku, warehouseCode),
        error -> inventoryCache.find(sku, warehouseCode)
            .orElseThrow(() ->
                new InventoryUnavailableException(
                    sku, warehouseCode, error
                )
            )
    );
}
~~~

Cache được truy vấn bằng đúng tham số của yêu cầu hiện tại. ID Circuit Breaker vẫn là **inventory-read**. Nếu cache có dữ liệu, response từ cache được trả về theo cùng kiểu với response từ client. Nếu không có dữ liệu, fallback ném ngoại lệ nghiệp vụ để tầng trên có thể chuyển thành phản hồi thích hợp.

Không nên trả về một DTO rỗng hoặc số lượng bằng 0 nếu điều đó có thể bị hiểu là kho thực sự không còn hàng. Dữ liệu fallback cần thể hiện được trạng thái không khả dụng, thời điểm dữ liệu cache hoặc nguồn dữ liệu nếu nghiệp vụ cần phân biệt. Ví dụ, **unavailable** khác với **availableQuantity = 0**: trường hợp đầu là không thể xác định tồn kho; trường hợp sau là đã xác định kho hiện không còn hàng.

Fallback nhận nguyên nhân lỗi qua tham số **error**. Có thể phân loại lỗi bị Circuit Breaker từ chối, timeout và lỗi client để ghi log hoặc chọn nguồn dự phòng phù hợp:

~~~java
error -> {
    if (error instanceof CallNotPermittedException) {
        log.warn("Inventory đang được bảo vệ bởi Circuit Breaker, sku={}", sku);
    } else {
        log.warn("Không lấy được tồn kho, sku={}", sku, error);
    }

    return inventoryCache.find(sku, warehouseCode)
        .orElseThrow(() ->
            new InventoryUnavailableException(sku, warehouseCode, error)
        );
}
~~~

Không nên coi mọi lỗi đều là trạng thái OPEN. **CallNotPermittedException** cho biết lời gọi bị bộ ngắt từ chối; timeout và lỗi từ client là các tình huống khác cần được phân biệt khi theo dõi.

## 6. Giữ correlation ID riêng với Circuit Breaker ID

Trong hệ thống phân tán, một yêu cầu thường đi qua nhiều dịch vụ. **traceId** hoặc **correlationId** giúp nối log của cùng một yêu cầu, còn ID Circuit Breaker giúp xác định nhóm lời gọi được bảo vệ. Hai loại định danh phục vụ hai mục đích khác nhau.

| Định danh | Vòng đời | Dùng cho |
|---|---|---|
| Circuit Breaker ID | Ổn định theo dependency hoặc operation | Trạng thái, sliding window, cấu hình và metric |
| traceId / correlationId | Thay đổi theo từng request hoặc trace | Truy vết log và luồng xử lý |
| orderId | Theo từng đơn hàng | Dữ liệu nghiệp vụ và tra cứu đơn |
| sku | Theo sản phẩm | Tham số truy vấn tồn kho hoặc Catalog |

Ví dụ, một request có **traceId = 7f3a...** gọi Inventory với **sku = SKU-001**. Log có thể ghi cả ba thông tin:

~~~java
log.info(
    "Gọi Circuit Breaker {}, traceId={}, sku={}",
    INVENTORY_READ,
    traceId,
    sku
);
~~~

Metric Circuit Breaker vẫn chỉ gắn với ID ổn định **inventory-read**. Không đưa traceId, orderId hay SKU thành tên instance hoặc tag metric. Nếu đưa giá trị thay đổi liên tục vào tag, hệ thống giám sát có thể tạo hàng loạt time series, tăng bộ nhớ và chi phí lưu trữ.

Trong ứng dụng dùng tracing hoặc logging context, traceId có thể được tự động đưa vào MDC hoặc trace span. Việc truy vết request nên dựa vào cơ chế đó, còn Circuit Breaker ID vẫn dùng để tổng hợp sức khỏe của dependency.

## 7. Kiểm tra đầu vào trước khi gọi dịch vụ

Các lỗi xác thực dữ liệu đầu vào thường không phản ánh tình trạng của dịch vụ phụ thuộc. Nếu SKU rỗng hoặc số lượng không hợp lệ, hãy kiểm tra trước khi gọi Circuit Breaker:

~~~java
StockAvailability reserveStock(
        String sku,
        String warehouseCode,
        int quantity) {

    if (sku == null || sku.isBlank()) {
        throw new IllegalArgumentException("sku không được để trống");
    }
    if (warehouseCode == null || warehouseCode.isBlank()) {
        throw new IllegalArgumentException(
            "warehouseCode không được để trống"
        );
    }
    if (quantity <= 0) {
        throw new IllegalArgumentException(
            "quantity phải lớn hơn 0"
        );
    }

    InventoryResponse response =
        circuitBreakerFactory.create("inventory-reserve").run(
            () -> inventoryClient.reserve(
                sku,
                warehouseCode,
                quantity
            ),
            error -> {
                throw new InventoryUnavailableException(
                    sku, warehouseCode, error
                );
            }
        );

    return inventoryMapper.toDomain(response);
}
~~~

Trong ví dụ, kiểm tra tham số xảy ra trước supplier. Vì vậy, dữ liệu đầu vào sai không tạo ra một lời gọi đến Inventory và không làm tăng tỷ lệ lỗi của Circuit Breaker. Khi đầu vào hợp lệ, supplier truyền các giá trị đó vào client.

Nếu dịch vụ phụ thuộc trả lỗi nghiệp vụ như “không đủ hàng”, cần phân loại theo hợp đồng API. Lỗi nghiệp vụ có thể được trả bằng response hợp lệ hoặc exception riêng. Không nên để một lỗi nghiệp vụ bình thường làm tăng failure rate nếu chính sách Circuit Breaker chỉ nhằm phản ánh lỗi hạ tầng hoặc khả năng phục vụ của dependency. Resilience4j cho phép cấu hình các loại exception được ghi nhận hoặc bỏ qua; cần thiết lập theo semantics của client.

## 8. Không tạo ID động trong vòng lặp hoặc theo từng bản ghi

Một lỗi dễ gặp là tạo Circuit Breaker bên trong vòng lặp bằng tên ghép từ dữ liệu:

~~~java
// Không nên: mỗi SKU tạo một định danh Circuit Breaker riêng.
for (String sku : skuList) {
    String breakerId = "inventory-" + sku;
    circuitBreakerFactory.create(breakerId).run(
        () -> inventoryClient.getInventory(sku),
        error -> InventoryResponse.unavailable(sku, "DEFAULT")
    );
}
~~~

Cách này làm số instance tăng theo số SKU. Nếu hệ thống có hàng trăm nghìn SKU, factory và registry có thể giữ một lượng lớn Circuit Breaker. Mỗi instance có sliding window riêng, nhưng lưu lượng của từng SKU có thể quá ít để đạt **minimumNumberOfCalls**. Kết quả là cơ chế bảo vệ không có đủ dữ liệu để đánh giá tình trạng chung của Inventory.

Cách phù hợp là giữ một ID cho thao tác đọc tồn kho:

~~~java
for (String sku : skuList) {
    circuitBreakerFactory.create(INVENTORY_READ).run(
        () -> inventoryClient.getInventory(sku),
        error -> InventoryResponse.unavailable(sku, "DEFAULT")
    );
}
~~~

Mỗi supplier vẫn giữ SKU riêng của lần gọi tương ứng, nhưng tất cả cùng dùng ID **inventory-read**. Nếu cần giới hạn tốc độ theo từng tenant hoặc sản phẩm, hãy dùng cơ chế rate limit hoặc quota có thiết kế phù hợp; không biến Circuit Breaker thành registry theo từng dữ liệu nghiệp vụ.

## 9. Chọn phạm vi ID theo dịch vụ và thao tác

Một ID ổn định không nhất thiết chỉ đại diện cho toàn bộ một máy chủ dịch vụ. Hãy chọn phạm vi theo đơn vị mà ứng dụng muốn theo dõi và bảo vệ.

Ví dụ, cùng dịch vụ Inventory có hai endpoint:

- Đọc tồn kho thường có lưu lượng lớn, yêu cầu phản hồi nhanh.
- Giữ hàng có thể thay đổi trạng thái dữ liệu, có SLA và chính sách retry khác.

Có thể đặt hai ID **inventory-read** và **inventory-reserve** để tách trạng thái và metric. Tuy nhiên, không nên tách đến mức mỗi SKU, warehouse, user hoặc order có một ID riêng.

Khi chọn ID, hãy tự trả lời:

1. Các lời gọi này có cùng dependency hoặc cùng operation không?
2. Chúng có nên chia sẻ cùng ngưỡng lỗi, timeout và sliding window không?
3. Khi một nhóm lời gọi gặp sự cố, có nên chặn nhóm còn lại không?
4. Số lượng ID có cố định và có thể quản lý được không?

Nếu hai operation cần chính sách bảo vệ khác nhau, tách ID ổn định. Nếu chúng chỉ khác tham số đầu vào nhưng cùng phụ thuộc và cùng hành vi, giữ chung ID.

## 10. Tình huống thực hành

Một dịch vụ đơn hàng nhận yêu cầu kiểm tra tồn kho với các trường **sku**, **warehouseCode** và **orderId**. Client đồng bộ gọi dịch vụ Inventory. Ứng dụng cần bảo vệ tất cả lời gọi đọc tồn kho bằng Circuit Breaker **inventory-read**.

Giả sử có ba request:

| Request | SKU | Kho | Order |
|---|---|---|---|
| A | SKU-001 | HN-01 | ORD-1001 |
| B | SKU-002 | HCM-02 | ORD-1002 |
| C | SKU-003 | HN-01 | ORD-1003 |

Cả ba request đều gọi:

~~~java
circuitBreakerFactory.create("inventory-read").run(
    () -> inventoryClient.getInventory(sku, warehouseCode),
    error -> inventoryCache.find(sku, warehouseCode)
        .orElseThrow(() ->
            new InventoryUnavailableException(sku, warehouseCode, error)
        )
);
~~~

Circuit Breaker chỉ có một ID **inventory-read**. Mỗi supplier giữ các giá trị SKU và kho của request tương ứng. **orderId** có thể được ghi trong log hoặc trace context để truy vết, nhưng không tham gia tạo tên Circuit Breaker.

Nếu request A thành công, request B thất bại do timeout và request C thành công, các kết quả được ghi nhận vào cùng instance theo chính sách cấu hình. Khi có đủ mẫu, Circuit Breaker đánh giá tỷ lệ lỗi trên toàn bộ lời gọi đọc tồn kho. Nếu chuyển sang OPEN, request tiếp theo bị từ chối trước khi client được gọi; fallback sẽ sử dụng cache hoặc trả lỗi nghiệp vụ theo chính sách.

Khi thực hành, hãy xác định được:

- ID nào là định danh ổn định của thao tác được bảo vệ.
- Những tham số nào được truyền vào supplier của từng request.
- Response nào được ánh xạ sang mô hình nghiệp vụ và mapping nằm trong hay ngoài supplier.
- Fallback trả về cùng kiểu dữ liệu hay ném ngoại lệ nào.
- traceId và orderId được ghi log ở đâu mà không làm tăng số lượng Circuit Breaker instance.
- Kết quả nào được ghi nhận vào sliding window chung.

## Kết luận

Với lời gọi đồng bộ, hãy dùng một ID Circuit Breaker ổn định cho mỗi dịch vụ phụ thuộc hoặc operation cần được bảo vệ. Truyền tham số thay đổi theo request bên trong supplier, giữ traceId và dữ liệu nghiệp vụ cho logging/tracing, rồi ánh xạ response ở vị trí phù hợp với phạm vi lỗi muốn đo lường. Cách làm này giúp các lời gọi cùng dependency chia sẻ sliding window và trạng thái, tránh tạo instance động theo từng yêu cầu, đồng thời vẫn giữ được dữ liệu đầu vào, fallback và mô hình nghiệp vụ riêng cho từng request.
