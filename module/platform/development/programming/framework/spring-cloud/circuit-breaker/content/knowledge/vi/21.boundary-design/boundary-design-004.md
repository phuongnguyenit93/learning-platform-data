# Quản lý tenant mà không tạo số instance không giới hạn

Trong ứng dụng đa tenant, nhiều khách hàng có thể cùng gọi một dịch vụ phụ thuộc như Catalog, Inventory hoặc Payment. Mỗi tenant có dữ liệu và quyền truy cập riêng, nhưng không phải lúc nào cũng cần một Circuit Breaker riêng. Nếu ghép tenant ID vào tên Circuit Breaker cho từng request, số instance có thể tăng theo số tenant và không có giới hạn rõ ràng. Hệ quả là registry, sliding window, metric và bộ nhớ tăng liên tục, trong khi mỗi instance lại có quá ít mẫu để đánh giá sức khỏe dependency.

Thiết kế phù hợp bắt đầu bằng việc phân biệt **tenant identity** với **Circuit Breaker ID**. Tenant identity xác định khách hàng và phạm vi dữ liệu; Circuit Breaker ID xác định dependency hoặc operation có chung failure domain và chính sách bảo vệ. Khi nhiều tenant dùng chung backend, một bộ ngắt ổn định theo operation thường phản ánh đúng sức khỏe của backend. Khi backend thực sự được chia thành các failure domain độc lập, có thể dùng một số lượng hữu hạn bộ ngắt theo shard hoặc vùng triển khai.

## 1. Tenant ID và Circuit Breaker ID phục vụ hai mục đích

Tenant ID thay đổi theo khách hàng hoặc tổ chức đang gửi request. Circuit Breaker ID nên ổn định theo dependency hoặc operation mà ứng dụng muốn bảo vệ.

| Định danh | Ví dụ | Mục đích |
|---|---|---|
| Tenant ID | **tenant-4821** | Xác định khách hàng, quyền truy cập và phạm vi dữ liệu |
| Circuit Breaker ID | **catalog-read** | Chia sẻ trạng thái và sliding window cho lời gọi đọc Catalog |
| Operation | **reserve-stock** | Mô tả thao tác được bảo vệ |
| Backend shard | **inventory-eu-1** | Xác định một failure domain độc lập nếu hạ tầng thực sự được phân vùng |
| Trace ID | Một mã duy nhất cho request hoặc trace | Nối log và span của một lần xử lý |

Một request đọc sản phẩm có thể mang tenant ID **tenant-4821**, SKU **SKU-001** và trace ID riêng. Nếu tất cả tenant đều gọi cùng cụm Catalog, lời gọi vẫn dùng Circuit Breaker ID **catalog-read**. Các tham số tenant và SKU đi vào supplier của lời gọi; chúng không cần được ghép vào tên bộ ngắt.

Không dùng các tên như **catalog-tenant-4821**, **catalog-tenant-4822** hoặc **inventory-order-90001** cho từng request. Mỗi tên mới có thể tạo thêm instance và cửa sổ thống kê. Cách đặt tên này làm phân mảnh kết quả, tăng cardinality của metric và có thể khiến registry giữ nhiều trạng thái không còn được sử dụng.

## 2. Vì sao không nên tạo một Circuit Breaker cho mỗi tenant?

Giả sử một nền tảng SaaS có 50.000 tenant cùng gọi một cụm Catalog. Nếu mỗi tenant có một Circuit Breaker riêng, ứng dụng có thể tạo đến 50.000 instance chỉ cho một operation.

Cách làm đó gây ra một số vấn đề:

- **Tăng bộ nhớ và chi phí quản lý:** mỗi instance có cấu hình, trạng thái, sliding window và các cấu trúc hỗ trợ riêng.
- **Phân mảnh mẫu:** một tenant ít request có thể không bao giờ đạt **minimumNumberOfCalls**, nên bộ ngắt không đủ dữ liệu để đánh giá.
- **Metric cardinality cao:** mỗi breaker name có thể trở thành một nhóm metric hoặc time series mới.
- **Khó vận hành:** dashboard và alert phải xử lý hàng chục nghìn trạng thái thay đổi liên tục.
- **Rủi ro lạm dụng:** nếu tên instance được tạo từ dữ liệu request, một lượng lớn tenant hoặc giá trị giả có thể buộc ứng dụng tạo thêm trạng thái.
- **Không phản ánh đúng lỗi backend chung:** nếu Catalog gặp sự cố cho tất cả tenant, các instance riêng có thể mở ở thời điểm khác nhau hoặc không mở vì mỗi instance có quá ít mẫu.

Circuit Breaker nhằm bảo vệ dependency khỏi các lời gọi khi dependency suy giảm. Nếu nhiều tenant cùng phụ thuộc một backend, việc quan sát kết quả chung thường giúp phát hiện lỗi sớm hơn và ngăn tải đồng loạt.

## 3. Dùng một Circuit Breaker ổn định khi backend được chia sẻ

Khi mọi tenant cùng gọi một dịch vụ hoặc cụm dịch vụ có failure domain chung, dùng một Circuit Breaker cho mỗi operation cần bảo vệ.

Ví dụ ứng dụng đọc Catalog cho nhiều tenant:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class CatalogGateway {

    private static final String CATALOG_READ = "catalog-read";

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;
    private final ProductCache productCache;

    CatalogGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient,
            ProductCache productCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
        this.productCache = productCache;
    }

    Product getProduct(
            TenantId tenantId,
            String sku) {
        return circuitBreakerFactory.create(CATALOG_READ).run(
            () -> catalogClient.getProduct(tenantId, sku),
            error -> productCache.find(tenantId, sku)
                .orElseThrow(() ->
                    new CatalogUnavailableException(tenantId, sku, error)
                )
        );
    }
}
~~~

Mọi tenant đều dùng tên cố định **catalog-read**. Supplier vẫn truyền tenant ID và SKU vào client để backend áp dụng phân quyền và truy vấn đúng dữ liệu. Fallback truy vấn cache theo cả tenant ID và SKU để tránh trả dữ liệu của khách hàng khác.

Nếu Catalog bị lỗi trên toàn cụm, các kết quả lỗi từ nhiều tenant cùng đóng góp vào sliding window của **catalog-read**. Khi đạt ngưỡng, bộ ngắt chuyển OPEN và chặn lời gọi mới đến dependency. Đây là hành vi phù hợp nếu sự cố thực sự ảnh hưởng chung đến backend.

Cần bảo đảm tenant ID được lấy từ ngữ cảnh xác thực đáng tin cậy, chẳng hạn principal hoặc security context đã được xác minh. Không dùng một header tùy ý do client gửi làm căn cứ truy cập dữ liệu tenant khác. Circuit Breaker không thay thế cơ chế xác thực, phân quyền hoặc cách ly dữ liệu.

## 4. Cấu hình một instance cho operation dùng chung

Tên instance trong Resilience4j phải khớp với ID truyền vào factory:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 30
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 5
~~~

Cấu hình này tạo một cửa sổ chung cho operation đọc Catalog. Giá trị trong ví dụ chỉ để minh họa; cần điều chỉnh theo lưu lượng, độ trễ bình thường và năng lực backend.

Nếu ứng dụng có nhiều operation khác nhau, có thể dùng một instance ổn định cho mỗi operation:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 30
        failureRateThreshold: 50
        waitDurationInOpenState: 15s

      catalog-search:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 60
        minimumNumberOfCalls: 20
        failureRateThreshold: 40
        waitDurationInOpenState: 20s

      inventory-reserve:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
~~~

Các ID trên là hữu hạn và có ý nghĩa theo operation. Chúng không tăng khi số tenant hoặc số request tăng. Đọc sản phẩm, tìm kiếm và giữ hàng có thể cần chính sách khác nhau vì SLA và semantics lỗi khác nhau; tách theo operation giúp giữ được phạm vi đánh giá có ý nghĩa.

Không tách Circuit Breaker chỉ vì muốn có một biểu đồ riêng cho từng tenant. Nếu cần đo tỷ lệ lỗi theo tenant, hãy dùng log, trace hoặc metric có cardinality được kiểm soát; không biến mỗi tenant thành một state machine độc lập khi backend vẫn là một failure domain chung.

## 5. Khi nào cần chia nhỏ theo shard hoặc vùng?

Có trường hợp nhiều tenant không dùng chung một backend. Ví dụ, nền tảng định tuyến tenant đến các cụm Inventory độc lập theo vùng hoặc shard. Nếu một shard gặp sự cố, các shard khác vẫn hoạt động bình thường. Khi đó, một Circuit Breaker chung cho toàn bộ Inventory có thể mở quá rộng và chặn cả những request đi đến backend khỏe mạnh.

Có thể tạo một số lượng hữu hạn instance theo failure domain thật sự:

| Backend failure domain | Circuit Breaker ID |
|---|---|
| Inventory shard EU-1 | **inventory-eu-1** |
| Inventory shard AP-1 | **inventory-ap-1** |
| Inventory shard US-1 | **inventory-us-1** |

Số lượng instance bị giới hạn bởi số shard đã triển khai, không phải số tenant. Một tenant được ánh xạ đến shard bằng router hoặc service discovery; sau đó ứng dụng chọn Circuit Breaker tương ứng.

Ví dụ dùng enum để giới hạn tập tên hợp lệ:

~~~java
enum InventoryShard {
    EU_1("inventory-eu-1"),
    AP_1("inventory-ap-1"),
    US_1("inventory-us-1");

    private final String breakerId;

    InventoryShard(String breakerId) {
        this.breakerId = breakerId;
    }

    String breakerId() {
        return breakerId;
    }
}
~~~

Service nhận shard đã được resolver xác định từ tenant routing:

~~~java
@Service
class ShardedInventoryGateway {

    private final CircuitBreakerFactory<?, ?> factory;
    private final InventoryRouter inventoryRouter;
    private final InventoryClient inventoryClient;

    ShardedInventoryGateway(
            CircuitBreakerFactory<?, ?> factory,
            InventoryRouter inventoryRouter,
            InventoryClient inventoryClient) {
        this.factory = factory;
        this.inventoryRouter = inventoryRouter;
        this.inventoryClient = inventoryClient;
    }

    Stock getStock(TenantId tenantId, String sku) {
        InventoryShard shard = inventoryRouter.resolve(tenantId);

        return factory.create(shard.breakerId()).run(
            () -> inventoryClient.getStock(shard, tenantId, sku),
            error -> Stock.unavailable(sku)
        );
    }
}
~~~

Trong ví dụ, **InventoryRouter** chỉ trả về một giá trị thuộc enum đã định nghĩa. Circuit Breaker ID không lấy trực tiếp từ chuỗi tenant ID. Khi thêm shard mới, nhóm phát triển thêm một giá trị định danh có kiểm soát và cấu hình tương ứng.

Chỉ nên tách theo shard khi các shard thực sự có khả năng lỗi độc lập. Nếu nhiều shard vẫn phụ thuộc vào cùng một database, DNS, network gateway hoặc dịch vụ chung, cần cân nhắc thêm một lớp bảo vệ cho dependency dùng chung. Nếu tách quá sâu, lỗi của thành phần chung có thể bị che khuất bởi các cửa sổ riêng lẻ.

## 6. Không dùng tenant tier làm failure domain nếu backend vẫn dùng chung

Một cách khác là chia tenant thành các nhóm như Free, Standard và Enterprise. Nhóm có thể muốn áp dụng quota hoặc giới hạn đồng thời khác nhau cho từng gói dịch vụ. Tuy nhiên, không nên mặc định tạo Circuit Breaker riêng cho từng tier.

Nếu mọi tier vẫn gọi cùng một cụm Catalog, lỗi của Catalog ảnh hưởng đến tất cả. Tách breaker theo tier có thể làm mỗi cửa sổ chỉ nhận một phần lưu lượng và khiến thời điểm mở mạch khác nhau. Một nhóm có thể tiếp tục gửi request đến backend đang lỗi chỉ vì breaker riêng của nhóm đó chưa đủ mẫu.

Nên phân chia trách nhiệm:

- Circuit Breaker dùng để theo dõi sức khỏe của dependency hoặc failure domain.
- Rate limiter hoặc quota kiểm soát mức sử dụng theo tenant hoặc gói dịch vụ.
- Bulkhead giới hạn tài nguyên đồng thời để một nhóm tải không chiếm hết năng lực xử lý.
- Authorization và tenant routing kiểm soát quyền truy cập và nơi dữ liệu được lưu.

Nếu các gói dịch vụ thực sự được phục vụ bởi cụm backend tách biệt, lúc đó có thể dùng breaker riêng theo cụm. Quyết định dựa trên kiến trúc triển khai và phạm vi lỗi, không dựa đơn thuần vào nhãn thương mại của tenant.

## 7. Kiểm soát tenant noisy neighbor bằng quota và Bulkhead

Một tenant có thể tạo lưu lượng lớn hoặc gửi nhiều request chậm, làm ảnh hưởng đến các tenant khác. Circuit Breaker chung giúp phát hiện backend suy giảm, nhưng không cung cấp công bằng tài nguyên theo tenant. Nếu cần giới hạn mức sử dụng của từng khách hàng, hãy dùng cơ chế quota hoặc rate limit riêng.

Bulkhead có thể giới hạn số tác vụ đồng thời đến một dependency hoặc một nhóm tài nguyên. Trong hệ thống đa tenant, có thể thiết kế các pool hoặc giới hạn hữu hạn theo lớp dịch vụ, shard hay workload. Không nên tạo một thread pool hoặc Bulkhead không giới hạn cho từng tenant.

Ví dụ về cách phân chia:

| Cơ chế | Phạm vi | Mục tiêu |
|---|---|---|
| Circuit Breaker **catalog-read** | Dependency Catalog dùng chung | Ngăn tiếp tục gọi backend đang lỗi |
| Rate limit | Tenant hoặc API key | Giới hạn tốc độ request của từng khách hàng |
| Bulkhead | Operation hoặc nhóm tài nguyên hữu hạn | Giới hạn số tác vụ đồng thời |
| Queue limit | Worker pool hoặc shard | Ngăn hàng đợi tăng vô hạn |
| Tenant authorization | Request và dữ liệu | Ngăn truy cập chéo tenant |

Rate limit theo tenant có thể cần lưu trạng thái riêng, nhưng cơ chế đó phải có giới hạn dung lượng, thời gian sống và chính sách dọn dẹp rõ ràng. Không tái sử dụng Circuit Breaker registry làm kho lưu quota theo tenant. Hai cơ chế có mục tiêu và vòng đời khác nhau.

## 8. Fallback và cache phải giữ ranh giới tenant

Dùng chung Circuit Breaker không có nghĩa dùng chung dữ liệu fallback. Khi Catalog không khả dụng, fallback vẫn phải truy vấn dữ liệu đúng tenant.

Ví dụ cache key cần bao gồm tenant ID:

~~~java
Optional<Product> find(TenantId tenantId, String sku) {
    return cache.get(
        tenantId.value() + ":product:" + sku,
        Product.class
    );
}
~~~

Nếu chỉ dùng SKU làm key trong khi mỗi tenant có danh mục, giá hoặc quyền hiển thị khác nhau, fallback có thể trả dữ liệu của tenant khác. Đây là lỗi cách ly dữ liệu nghiêm trọng.

Fallback cần giữ các quy tắc:

- Tenant ID được xác thực trước khi tra cache.
- Cache key chứa tenant ID hoặc namespace tenant tương đương.
- Dữ liệu fallback tuân theo quyền truy cập của tenant.
- Thời gian lưu cache phù hợp với nghiệp vụ và chính sách dữ liệu cũ.
- Nếu không có dữ liệu hợp lệ, trả lỗi không khả dụng thay vì giả lập kết quả nghiệp vụ.

Circuit Breaker bảo vệ đường gọi đến dependency; nó không tự đảm bảo cache, dữ liệu hoặc fallback tuân thủ cách ly tenant.

## 9. Giữ metric có cardinality hữu hạn

Metric là một lý do quan trọng để tránh tên Circuit Breaker động. Nhiều hệ thống giám sát tạo time series dựa trên tên instance và các tag. Nếu mỗi tenant ID trở thành breaker name hoặc tag, số chuỗi thời gian có thể tăng theo số tenant và số operation.

Nên dùng các chiều có số lượng giới hạn:

- Circuit Breaker name theo dependency hoặc operation.
- Shard hoặc region nếu số lượng shard hữu hạn.
- Kết quả lời gọi: success, failure, ignored, not permitted.
- Loại lỗi đã chuẩn hóa thành một tập giá trị hữu hạn.
- Môi trường hoặc phiên bản triển khai nếu cần so sánh.

Tenant ID có thể hữu ích trong log hoặc trace để điều tra request cụ thể. Tuy nhiên, không nên đưa tenant ID, user ID, order ID, SKU hoặc trace ID vào tag metric có cardinality cao. Nếu cần thống kê theo tenant, dùng hệ thống phân tích hoặc bảng tổng hợp có giới hạn, sampling và chính sách lưu trữ phù hợp.

Ví dụ log có thể giữ cả breaker ID và tenant ID:

~~~java
log.warn(
    "Circuit Breaker {} từ chối request của tenant={}, sku={}",
    "catalog-read",
    tenantId.value(),
    sku
);
~~~

Trong dashboard, metric vẫn nhóm theo **catalog-read**; log hoặc trace cho phép tìm tenant cụ thể khi có sự cố. Cách tách này giữ metric vận hành ổn định mà vẫn hỗ trợ điều tra.

## 10. Nếu thật sự cần Circuit Breaker riêng cho một số tenant

Một số hệ thống có khách hàng lớn được triển khai trên backend riêng hoặc có yêu cầu cô lập đặc biệt. Khi đó, breaker riêng có thể hợp lý, nhưng cần đáp ứng các điều kiện:

1. Số tenant được cấp breaker riêng là hữu hạn và được quản lý qua provisioning.
2. Mỗi tenant tương ứng với một failure domain độc lập hoặc có chính sách bảo vệ thực sự khác.
3. Instance name được tạo từ danh sách định danh được kiểm soát, không từ request tùy ý.
4. Có giới hạn tổng số instance và giám sát số lượng đang hoạt động.
5. Có quy trình vòng đời rõ ràng khi tenant ngừng hoạt động.
6. Có kế hoạch xử lý trạng thái khi instance bị loại bỏ và được tạo lại.
7. Metric và dashboard không tạo cardinality vượt khả năng lưu trữ.

Không nên thêm một cache không giới hạn để giữ Circuit Breaker theo tenant rồi coi đó là giải pháp an toàn. Nếu có cơ chế eviction, cần hiểu rằng loại bỏ một instance cũng có thể loại bỏ trạng thái OPEN và sliding window của nó. Khi instance được tạo lại, bộ ngắt có thể trở về trạng thái ban đầu và gửi request đến dependency đang lỗi. Việc eviction vì vậy là quyết định về semantics bảo vệ, không chỉ là tối ưu bộ nhớ.

Nếu buộc phải quản lý instance động, cần giới hạn số lượng, kiểm soát quyền tạo, xác định thời điểm hết hạn và cách xử lý khi xóa trạng thái. Nên ưu tiên provisioning trước cho tập tenant hữu hạn, thay vì tạo instance tự động cho mọi tenant xuất hiện trong traffic.

## 11. Kiểm thử thiết kế đa tenant

Bộ kiểm thử cần xác nhận cả cách ly dữ liệu và phạm vi chia sẻ trạng thái Circuit Breaker.

| Kiểm thử | Điều kiện | Kết quả cần xác nhận |
|---|---|---|
| Nhiều tenant dùng chung backend | Tenant A và B gọi Catalog | Cùng dùng ID **catalog-read** |
| Tenant ID thay đổi | Gửi request từ nhiều tenant khác nhau | Số Circuit Breaker instance không tăng theo tenant |
| Backend dùng chung gặp lỗi | Request của nhiều tenant đều nhận lỗi kỹ thuật | Cùng sliding window phản ánh sức khỏe backend |
| Circuit Breaker OPEN | Gọi từ tenant khác khi breaker chung OPEN | Không gửi thêm request đến backend |
| Fallback | Hai tenant có cùng SKU nhưng dữ liệu khác nhau | Cache trả dữ liệu đúng tenant |
| Shard độc lập | Tenant A ở shard EU, tenant B ở shard AP | Mỗi shard dùng breaker ID hữu hạn tương ứng |
| Tenant noisy neighbor | Một tenant vượt quota | Tenant đó bị giới hạn mà không tạo breaker mới |
| Metric | Tạo traffic cho nhiều tenant | Cardinality không tăng theo tenant ID |
| Tenant bị ngừng | Tenant không còn được phép truy cập | Authorization chặn request; không cần tạo hay giữ breaker mới |

Có thể dùng test tích hợp với Circuit Breaker thật để kiểm tra trạng thái và số lời gọi đến client. Mock factory chỉ đủ để xác nhận service truyền đúng ID và tham số; nó không chứng minh registry không tạo instance ngoài ý muốn hoặc trạng thái thực sự được chia sẻ.

Một test quan trọng là gửi nhiều request với tenant ID khác nhau nhưng cùng backend, sau đó xác minh tất cả đều dùng cùng breaker ID. Tiếp theo, tạo đủ lỗi để mở mạch và xác nhận request của tenant khác cũng bị từ chối nếu chúng cùng failure domain. Đây là hành vi chia sẻ có chủ ý, cần được ghi rõ trong hợp đồng vận hành.

## 12. Tình huống thực hành

Một nền tảng SaaS có 20.000 tenant. Tất cả tenant dùng chung Catalog cluster, trong khi Inventory được triển khai trên ba shard độc lập theo vùng.

Thiết kế được chọn:

- Catalog dùng một Circuit Breaker **catalog-read** cho tất cả tenant.
- Inventory dùng ba Circuit Breaker hữu hạn: **inventory-eu-1**, **inventory-ap-1** và **inventory-us-1**.
- Tenant ID được dùng để xác thực, định tuyến, cache key và truy vết.
- Quota được quản lý riêng theo tenant.
- Bulkhead giới hạn tải đồng thời của các operation.
- Metric Circuit Breaker chỉ dùng tên instance, shard và loại kết quả có cardinality hữu hạn.

Khi Catalog gặp sự cố, **catalog-read** ghi nhận lỗi từ traffic chung và chuyển OPEN theo ngưỡng. Request của mọi tenant đều được bảo vệ bởi cùng bộ ngắt. Khi Inventory shard EU-1 gặp sự cố, chỉ **inventory-eu-1** chuyển trạng thái; các tenant được định tuyến đến AP-1 hoặc US-1 tiếp tục sử dụng breaker của shard tương ứng.

Nếu một tenant tạo lưu lượng quá lớn, quota giới hạn tenant đó. Circuit Breaker vẫn phản ánh tình trạng backend, không phải mức sử dụng riêng của tenant. Fallback Catalog dùng cache key gồm tenant ID và SKU để giữ cách ly dữ liệu.

Sau khi triển khai, hãy kiểm tra:

1. Số instance Catalog vẫn là một dù traffic có nhiều tenant.
2. Số instance Inventory không vượt số shard được provision.
3. Circuit Breaker ID không chứa tenant ID hoặc request ID.
4. Cache và fallback luôn giữ namespace tenant.
5. Quota và Bulkhead kiểm soát noisy neighbor độc lập với Circuit Breaker.
6. Metric có cardinality hữu hạn và log/trace vẫn cho phép điều tra request theo tenant.

## Kết luận

Quản lý tenant an toàn cần tách tenant identity khỏi Circuit Breaker ID. Khi nhiều tenant dùng chung một backend, dùng Circuit Breaker ổn định theo dependency hoặc operation để chia sẻ trạng thái và sliding window. Chỉ tách breaker theo shard hoặc vùng khi đó là các failure domain độc lập và số lượng phân vùng hữu hạn. Dùng quota, rate limit và Bulkhead để kiểm soát tải theo tenant; giữ tenant ID trong xác thực, cache key và tracing, đồng thời tránh đưa nó vào tên instance hoặc metric tag có cardinality cao.
