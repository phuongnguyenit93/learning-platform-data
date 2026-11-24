# ThreadPoolBulkhead, kích thước thread pool và hàng đợi hữu hạn

Khi một dịch vụ gọi nhiều hệ thống phụ thuộc, một phụ thuộc chậm có thể chiếm hết luồng xử lý và làm các lời gọi khác bị đình trệ. **ThreadPoolBulkhead** cô lập nhóm lời gọi bằng một thread pool riêng và hàng đợi có giới hạn. Nhờ đó, số tác vụ chạy đồng thời và số tác vụ chờ đều có mức trần; khi năng lực đã dùng hết, lời gọi mới bị từ chối sớm thay vì tiếp tục chiếm tài nguyên không giới hạn.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, Bulkhead phối hợp với Circuit Breaker để hạn chế lỗi dây chuyền khi dịch vụ phụ thuộc chậm hoặc không khả dụng. Circuit Breaker quyết định có nên tiếp tục gọi một phụ thuộc dựa trên kết quả và tỷ lệ lỗi; ThreadPoolBulkhead giới hạn số tác vụ đồng thời và cách ly tài nguyên thực thi. Hai cơ chế giải quyết hai khía cạnh khác nhau của khả năng chịu lỗi.

## 1. ThreadPoolBulkhead giải quyết vấn đề gì?

Giả sử dịch vụ Đơn hàng gọi dịch vụ Kho. Khi Kho phản hồi trong 50 ms, các luồng xử lý được giải phóng nhanh. Khi Kho bị chậm và mỗi request mất 8 giây, nhiều luồng của dịch vụ Đơn hàng có thể bị giữ lại. Nếu tất cả lời gọi phụ thuộc dùng chung một executor không giới hạn, lượng tác vụ chờ tăng lên, bộ nhớ tăng và các phần chức năng khác có thể bị ảnh hưởng.

ThreadPoolBulkhead tạo một vùng thực thi riêng cho nhóm lời gọi. Nó giới hạn:

- Số luồng được phép chạy tác vụ của nhóm phụ thuộc.
- Số tác vụ có thể chờ trong hàng đợi.
- Thời gian sống của luồng nhàn rỗi vượt quá số luồng lõi, tùy cấu hình executor.
- Số tác vụ được chấp nhận trước khi hệ thống từ chối yêu cầu mới.

Sơ đồ luồng xử lý:

~~~mermaid
flowchart TD
    A[Yêu cầu đến] --> B[ThreadPoolBulkhead]
    B --> C{Còn chỗ trong pool hoặc queue?}
    C -->|Có| D[Chạy hoặc xếp hàng]
    C -->|Không| E[Từ chối nhanh]
    D --> F[Thread pool riêng]
    F --> G[Gọi dịch vụ phụ thuộc]
    G --> H[Kết quả hoặc lỗi]
    E --> I[BulkheadFullException]
~~~

Khi pool và queue đều đầy, ThreadPoolBulkhead từ chối tác vụ mới. Đây là hành vi bảo vệ có chủ đích: hệ thống báo rằng hiện tại không còn năng lực tiếp nhận công việc thay vì nhận thêm yêu cầu rồi để chúng chờ vô hạn.

## 2. Các tham số của thread pool và queue

Resilience4j ThreadPoolBulkhead có các tham số thường dùng:

| Thuộc tính | Ý nghĩa | Cách cân nhắc |
| --- | --- | --- |
| `coreThreadPoolSize` | Số luồng lõi của pool | Chọn theo số tác vụ đồng thời bình thường và tài nguyên CPU, bộ nhớ |
| `maxThreadPoolSize` | Số luồng tối đa mà pool có thể mở rộng đến | Đặt trần để một phụ thuộc không chiếm hết tài nguyên của ứng dụng |
| `queueCapacity` | Số tác vụ tối đa được phép chờ | Dùng hàng đợi hữu hạn để giới hạn bộ nhớ và thời gian chờ |
| `keepAliveDuration` | Thời gian luồng nhàn rỗi vượt quá số luồng lõi được giữ lại trước khi thu hồi | Chọn theo mức dao động tải và chi phí tạo luồng |

Ví dụ cấu hình:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    configs:
      default:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 20
        keepAliveDuration: 20ms
    instances:
      inventory:
        baseConfig: default
~~~

Trong ví dụ, pool duy trì 4 luồng lõi và có thể mở rộng tối đa 8 luồng. Khi các luồng đang bận, tối đa 20 tác vụ được chờ trong queue. Khi cả 8 luồng đều đang chạy và 20 vị trí chờ đã được sử dụng, tác vụ tiếp theo sẽ bị từ chối.

Với cấu hình minh họa này, số tác vụ được tiếp nhận đồng thời hoặc chờ trong bulkhead có giới hạn lý thuyết là 8 tác vụ đang chạy cộng 20 tác vụ chờ, tức 28 tác vụ. Đây là giới hạn tiếp nhận tại một thời điểm, không phải thông lượng mỗi giây. Thời gian hoàn tất vẫn phụ thuộc vào độ trễ của dịch vụ phụ thuộc và thời gian xử lý từng tác vụ.

## 3. Cách pool mở rộng và queue hoạt động

Với thread pool có số luồng lõi, số luồng tối đa và hàng đợi hữu hạn, hành vi thường diễn ra theo các bước:

1. Khi có tác vụ và số luồng đang chạy còn thấp hơn `coreThreadPoolSize`, executor tạo luồng để chạy tác vụ.
2. Khi các luồng lõi đã bận, tác vụ mới được đưa vào queue nếu queue còn chỗ.
3. Khi queue đầy, executor có thể tạo thêm luồng vượt số lõi, cho đến `maxThreadPoolSize`.
4. Khi pool đã đạt mức tối đa và queue cũng đầy, tác vụ mới bị từ chối.
5. Khi tải giảm, các luồng vượt số lõi có thể được thu hồi sau `keepAliveDuration`.

Ví dụ với 4 luồng lõi, tối đa 8 luồng và queue 20:

| Tình huống | Tác vụ đang chạy | Tác vụ chờ | Hành vi |
| --- | ---: | ---: | --- |
| Tải thấp | 2 | 0 | Hai luồng xử lý tác vụ |
| Đã dùng hết luồng lõi | 4 | 6 | Các tác vụ mới chờ trong queue |
| Queue đầy | 4 | 20 | Pool có thể mở rộng thêm luồng đến tối đa 8 |
| Pool và queue đầy | 8 | 20 | Tác vụ mới bị từ chối |
| Tải giảm | 3 | 0 | Các tác vụ hoàn tất; luồng vượt mức lõi có thể được thu hồi sau thời gian nhàn rỗi |

Queue càng lớn không đồng nghĩa hệ thống càng khỏe. Queue dài có thể giữ nhiều request trong bộ nhớ và làm thời gian phản hồi tăng lên. Nếu request đã chờ lâu đến mức kết quả không còn hữu ích, việc từ chối sớm có thể tốt hơn tiếp tục xếp hàng.

## 4. Vì sao hàng đợi phải hữu hạn?

Hàng đợi không giới hạn cho phép ứng dụng tiếp nhận nhiều công việc hơn khả năng xử lý. Khi phụ thuộc chậm, số tác vụ chờ có thể tăng liên tục. Hệ quả thường gặp:

- Bộ nhớ bị tiêu thụ bởi request, context và dữ liệu đang chờ.
- Thời gian chờ tăng, khiến client timeout trước khi tác vụ được chạy.
- Khi dịch vụ phụ thuộc phục hồi, một lượng lớn request tồn đọng có thể tạo đợt tải tăng đột ngột.
- Các request mới bị ảnh hưởng bởi công việc cũ đã hết hạn hoặc không còn giá trị.

Queue hữu hạn đặt giới hạn rõ ràng cho lượng công việc được chấp nhận. Khi hết chỗ, bulkhead từ chối nhanh và ứng dụng có thể trả lỗi tạm thời, dùng fallback hoặc để tầng gọi quyết định thử lại sau.

Không nên đặt `queueCapacity` thật lớn chỉ để giảm số lần từ chối. Hãy xác định ngân sách thời gian của request, tốc độ xử lý trung bình và lượng bộ nhớ có thể dành cho tác vụ chờ. Queue cần đủ nhỏ để thời gian chờ không vượt quá thời hạn hữu ích của request.

## 5. Dùng ThreadPoolBulkhead bằng Resilience4j

Có thể tạo ThreadPoolBulkhead trực tiếp qua registry và thực thi một supplier bất đồng bộ:

~~~java
import io.github.resilience4j.bulkhead.ThreadPoolBulkhead;
import io.github.resilience4j.bulkhead.ThreadPoolBulkheadConfig;
import io.github.resilience4j.bulkhead.ThreadPoolBulkheadRegistry;

import java.time.Duration;
import java.util.concurrent.CompletionStage;

public class InventoryWorker {
    private final InventoryClient inventoryClient;
    private final ThreadPoolBulkhead bulkhead;

    public InventoryWorker(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;

        ThreadPoolBulkheadConfig config =
                ThreadPoolBulkheadConfig.custom()
                        .coreThreadPoolSize(4)
                        .maxThreadPoolSize(8)
                        .queueCapacity(20)
                        .keepAliveDuration(Duration.ofMillis(20))
                        .build();

        ThreadPoolBulkheadRegistry registry =
                ThreadPoolBulkheadRegistry.of(config);
        this.bulkhead = registry.bulkhead("inventory");
    }

    public CompletionStage<Inventory> getInventory(String sku) {
        return bulkhead.executeSupplier(
                () -> inventoryClient.get(sku)
        );
    }
}
~~~

`executeSupplier` trả về `CompletionStage<T>`, vì tác vụ được thực thi trong thread pool riêng. Lời gọi đến `inventoryClient.get(sku)` diễn ra trong tác vụ được bulkhead điều phối, không chạy ngay trên luồng gọi phương thức `getInventory`.

Ví dụ dùng registry để minh họa API lập trình. Trong ứng dụng Spring Boot, có thể khai báo cấu hình qua YAML và inject registry hoặc dùng integration phù hợp của Spring Cloud CircuitBreaker. Không nên tạo một registry mới mỗi lần có request; registry và bulkhead cần được tạo một lần, quản lý như thành phần dùng chung của ứng dụng.

## 6. Xử lý khi pool và queue đã đầy

Khi không còn chỗ tiếp nhận, ThreadPoolBulkhead từ chối tác vụ, thường bằng `BulkheadFullException` được phát qua `CompletionStage`. Ứng dụng cần xử lý trường hợp này như một tình trạng quá tải có thể phục hồi, thay vì xem nó là lỗi lập trình không xác định.

Ví dụ:

~~~java
import io.github.resilience4j.bulkhead.BulkheadFullException;

public CompletionStage<InventoryResult> getInventoryResult(String sku) {
    return bulkhead.executeSupplier(() -> inventoryClient.get(sku))
            .thenApply(InventoryResult::available)
            .exceptionally(failure -> {
                Throwable cause = unwrap(failure);
                if (cause instanceof BulkheadFullException) {
                    return InventoryResult.temporarilyUnavailable(sku);
                }
                throw new IllegalStateException(
                        "Không thể lấy tồn kho", cause);
            });
}
~~~

Hàm `unwrap` trong ví dụ là helper của ứng dụng để lấy nguyên nhân gốc nếu lỗi được bọc trong `CompletionException` hoặc `ExecutionException`. Cần triển khai helper này theo cách dùng CompletionStage của dự án. Phần xử lý lỗi nên phân biệt bulkhead từ chối với lỗi HTTP hoặc lỗi nghiệp vụ từ dịch vụ Kho.

Không nên tự động gửi lại ngay khi nhận `BulkheadFullException`. Nếu pool và queue đã đầy, retry tức thì chỉ tạo thêm áp lực. Có thể trả lỗi 503 hoặc trạng thái quá tải để client điều tiết tốc độ, hoặc retry sau một khoảng chờ có giới hạn nếu hợp đồng API cho phép.

## 7. Kết hợp ThreadPoolBulkhead với Circuit Breaker

ThreadPoolBulkhead và Circuit Breaker có thể cùng bảo vệ một phụ thuộc:

| Cơ chế | Bảo vệ điều gì? | Tình huống kích hoạt |
| --- | --- | --- |
| ThreadPoolBulkhead | Tài nguyên thực thi và số tác vụ chờ | Pool và queue đã đạt giới hạn |
| Circuit Breaker | Tình trạng sức khỏe của phụ thuộc | Tỷ lệ lỗi hoặc lời gọi chậm vượt ngưỡng |

Bulkhead giới hạn số request có thể chạy đồng thời. Circuit Breaker theo dõi kết quả để ngừng gọi phụ thuộc khi nó liên tục lỗi hoặc chậm. Khi kết hợp, cần xác định rõ thứ tự áp dụng và loại exception nào được Circuit Breaker tính là lỗi.

Nếu bulkhead từ chối do quá tải nội bộ, cần cân nhắc liệu exception từ chối có nên làm tăng failure rate của Circuit Breaker hay không. Nếu tính mọi lần từ chối là lỗi của dịch vụ Kho, mạch có thể mở vì pool cục bộ đầy dù Kho vẫn khỏe. Ngược lại, nếu bỏ qua mọi lỗi từ chối mà không theo dõi riêng, ứng dụng có thể che giấu tình trạng thiếu năng lực xử lý. Hãy theo dõi riêng số lần bulkhead từ chối.

Một cấu hình Circuit Breaker riêng có thể đặt cùng tên instance với bulkhead nhưng thuộc prefix khác:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 20
        keepAliveDuration: 20ms
~~~

Hai cấu hình quản lý hai cơ chế riêng. Tên `inventory` giúp liên hệ với cùng phụ thuộc, nhưng các tham số Circuit Breaker không nằm trong nhóm ThreadPoolBulkhead và ngược lại.

## 8. Chọn kích thước pool và queue

Không có một bộ giá trị phù hợp cho mọi dịch vụ. Khi chọn cấu hình, hãy cân nhắc:

1. **Thời gian xử lý trung bình và phân vị cao.** Nếu mỗi tác vụ chờ dịch vụ Kho vài giây, số luồng lớn có thể làm tăng số kết nối đồng thời và tải lên Kho.
2. **Năng lực của dịch vụ phụ thuộc.** Giới hạn số lời gọi đồng thời theo khả năng mà phụ thuộc có thể phục vụ ổn định.
3. **Ngân sách tài nguyên của ứng dụng gọi.** Mỗi luồng có chi phí stack, context switching và tài nguyên liên quan. Không tạo nhiều pool lớn cho nhiều phụ thuộc mà không tính tổng số luồng.
4. **Ngân sách thời gian của request.** Queue không nên giữ tác vụ lâu hơn thời hạn mà kết quả còn hữu ích.
5. **Tính chất tác vụ.** Tác vụ chờ I/O có thể dùng pool khác với tác vụ CPU-bound; cần đo tải thực tế để chọn số luồng.
6. **Tỷ lệ từ chối chấp nhận được.** Một số request bị từ chối khi quá tải là dấu hiệu cơ chế đang giới hạn tải; tỷ lệ từ chối kéo dài cho thấy cần xem lại năng lực hoặc lưu lượng.

Một cách bắt đầu là chọn `coreThreadPoolSize` theo mức đồng thời bình thường, đặt `maxThreadPoolSize` cao hơn một mức có kiểm soát, rồi chọn queue nhỏ theo ngân sách chờ. Sau đó đo độ trễ, tỷ lệ queue đầy, số luồng hoạt động và số lần từ chối trong tải thử nghiệm có đại diện.

Tránh tăng cả pool lẫn queue chỉ để làm giảm số lỗi từ chối. Việc đó có thể chuyển một lỗi quá tải rõ ràng thành độ trễ cao và cạn tài nguyên khó phát hiện hơn.

## 9. Metrics và chẩn đoán

Nên quan sát các số liệu sau cho từng ThreadPoolBulkhead:

- Số luồng đang hoạt động và tổng số luồng trong pool.
- Số tác vụ đang chờ trong queue và dung lượng queue tối đa.
- Số tác vụ được hoàn tất và số tác vụ bị từ chối.
- Thời gian chờ trong queue và thời gian thực thi tác vụ.
- Tỷ lệ lỗi của lời gọi phụ thuộc sau khi tác vụ bắt đầu chạy.
- Trạng thái Circuit Breaker liên quan nếu hai cơ chế được kết hợp.

Khi số lần từ chối tăng, hãy phân biệt queue đầy do lưu lượng tăng đột biến với tác vụ kéo dài do dịch vụ phụ thuộc chậm. Nếu queue luôn đầy và thời gian chờ cao, tăng queue có thể chỉ làm request chờ lâu hơn. Nếu số luồng hoạt động luôn ở mức tối đa nhưng thời gian xử lý của phụ thuộc bình thường, có thể cần đánh giá giới hạn đồng thời hoặc năng lực của pool.

Resilience4j có thể xuất metrics qua Micrometer khi ứng dụng cấu hình tích hợp phù hợp. Có thể dùng Spring Boot Actuator và hệ thống giám sát để theo dõi queue, pool và số lần từ chối. Cần đặt cảnh báo cho tỷ lệ từ chối kéo dài, queue thường xuyên gần đầy và thời gian chờ vượt ngân sách.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng queue không giới hạn | Tác vụ chờ và bộ nhớ có thể tăng liên tục | Đặt `queueCapacity` hữu hạn |
| Đặt queue quá lớn | Request chờ lâu, có thể timeout trước khi được chạy | Chọn queue theo ngân sách thời gian |
| Đặt `maxThreadPoolSize` quá cao | Tạo quá nhiều luồng và tăng tải lên phụ thuộc | Giới hạn đồng thời theo năng lực thực tế |
| Tạo registry hoặc pool cho từng request | Tạo nhiều executor, tiêu thụ tài nguyên và khó quản lý | Dùng registry/bulkhead dùng chung |
| Retry ngay khi bulkhead đầy | Làm tăng áp lực đúng lúc hệ thống quá tải | Từ chối có kiểm soát hoặc retry có backoff |
| Xem BulkheadFullException là lỗi của dịch vụ phụ thuộc | Circuit Breaker có thể mở sai | Phân loại và theo dõi riêng lỗi từ chối |
| Chỉ theo dõi Circuit Breaker | Không thấy queue và pool đang cạn năng lực | Theo dõi metrics của cả Bulkhead |
| Chạy tác vụ blocking trên pool dùng chung toàn ứng dụng | Phụ thuộc chậm ảnh hưởng các công việc không liên quan | Cách ly executor cho nhóm tác vụ phù hợp |

## 11. Quy trình triển khai

Khi thêm ThreadPoolBulkhead cho một phụ thuộc, có thể thực hiện theo trình tự:

1. Xác định nhóm lời gọi cần cách ly và tên bulkhead ổn định.
2. Ước lượng số lời gọi đồng thời mà dịch vụ phụ thuộc và ứng dụng gọi có thể chịu được.
3. Cấu hình `coreThreadPoolSize`, `maxThreadPoolSize`, `queueCapacity` và `keepAliveDuration`.
4. Dùng registry hoặc Spring integration để tạo bulkhead dùng chung; không tạo pool theo từng request.
5. Xử lý trường hợp pool và queue đầy, phân biệt từ chối do bulkhead với lỗi HTTP từ phụ thuộc.
6. Kết hợp Circuit Breaker nếu cần theo dõi tỷ lệ lỗi và dừng lời gọi khi phụ thuộc suy giảm.
7. Kiểm tra dưới tải: xác nhận số luồng không vượt mức tối đa, queue không vượt dung lượng và tác vụ mới bị từ chối khi cả hai đã đầy.
8. Theo dõi metrics và điều chỉnh dựa trên độ trễ, thời gian chờ, tỷ lệ từ chối và tài nguyên thực tế.

ThreadPoolBulkhead với thread pool và hàng đợi hữu hạn tạo ra giới hạn rõ ràng cho công việc đang chạy và đang chờ. Khi đặt kích thước pool theo năng lực phụ thuộc, giữ queue trong ngân sách thời gian và xử lý từ chối có chủ đích, ứng dụng Spring Cloud có thể cô lập một dịch vụ chậm mà không để nó chiếm hết tài nguyên của các phần còn lại.
