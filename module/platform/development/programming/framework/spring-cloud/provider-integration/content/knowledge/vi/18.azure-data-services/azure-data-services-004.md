# ETag, optimistic locking và lựa chọn mức nhất quán

Một ứng dụng quản lý tồn kho bằng Azure Cosmos DB có thể có hai request cùng đọc số lượng là 10, rồi cùng trừ đi 3. Nếu cả hai ghi lại giá trị 7 mà không kiểm tra phiên bản, một cập nhật có thể ghi đè cập nhật còn lại: hệ thống vẫn hiển thị 7 thay vì 4. Đây là **lost update**. Cosmos DB cung cấp **ETag** và điều kiện HTTP `If-Match` để phát hiện thao tác đang dựa trên phiên bản cũ. Đồng thời, dịch vụ cho phép chọn **mức nhất quán (consistency level)** để quyết định một lần đọc có thể nhìn thấy dữ liệu mới đến đâu trong môi trường phân tán nhiều replica và nhiều region.

Hai cơ chế này giải quyết hai câu hỏi khác nhau: **ETag bảo vệ một lần ghi khỏi ghi đè phiên bản đã thay đổi**; **consistency level quyết định dữ liệu mà thao tác đọc được phép quan sát**. Dùng ETag không làm mọi lần đọc trở thành strong consistency, và chọn strong consistency cũng không thay thế quy tắc xử lý hai người cùng cập nhật một item.

Bài thuộc chương **Dữ liệu Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Bài này tập trung vào Azure Cosmos DB for NoSQL, Spring Data Cosmos và cách chọn mức nhất quán theo yêu cầu nghiệp vụ.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Giải thích ETag, `If-Match`, `If-None-Match` và lỗi HTTP 412.
- Nhận diện lost update/lost delete và triển khai optimistic concurrency control (OCC).
- Ánh xạ `_etag` vào entity Spring Data Cosmos bằng `@Version`.
- Xử lý conflict bằng cách đọc lại và áp dụng lại quy tắc nghiệp vụ thay vì retry payload cũ.
- Phân biệt ETag với session token, item ID, partition key và application version.
- Mô tả năm consistency level: Strong, Bounded Staleness, Session, Consistent Prefix và Eventual.
- Cấu hình consistency mặc định cho Spring Cloud Azure và hiểu session token trong ứng dụng nhiều instance.
- Đánh giá ảnh hưởng của multi-region writes, conflict resolution và giới hạn của ETag.
- Thiết kế kiểm thử concurrency, read-after-write, failover và các tình huống stale read.

## 2. Hai bài toán cần giải quyết riêng

### 2.1. Cập nhật đồng thời: ai được phép ghi phiên bản nào?

Giả sử item tồn kho có `availableQuantity = 10`. Hai worker cùng đọc item ở phiên bản ETag `E1`:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant DB as Cosmos DB
    A->>DB: Read item (quantity=10, ETag=E1)
    B->>DB: Read item (quantity=10, ETag=E1)
    A->>DB: Replace quantity=7, If-Match E1
    DB-->>A: Success, ETag=E2
    B->>DB: Replace quantity=7, If-Match E1
    DB-->>B: 412 Precondition Failed
    B->>DB: Read latest item (quantity=7, ETag=E2)
    B->>B: Re-evaluate business rule
    B->>DB: Replace quantity=4, If-Match E2
    DB-->>B: Success, ETag=E3
~~~

ETag cho phép server từ chối lần ghi thứ hai vì worker B đang dựa trên phiên bản cũ. Ứng dụng đọc lại giá trị mới, tính lại số lượng và thử ghi với ETag mới. Nếu không đủ tồn kho sau khi đọc lại, nghiệp vụ phải từ chối giao dịch thay vì cố ghi.

### 2.2. Đọc dữ liệu phân tán: replica nào được phép trả lời?

Trong account Cosmos DB có nhiều replica/region, một lần đọc có thể cần bảo đảm mạnh hơn hoặc yếu hơn về độ mới và thứ tự dữ liệu. Consistency level định nghĩa những bảo đảm này:

~~~mermaid
flowchart TD
    A[Application read] --> B{Consistency policy}
    B --> C[Strong: latest committed value]
    B --> D[Bounded staleness: lag <= K or T]
    B --> E[Session: read-your-writes in session]
    B --> F[Consistent prefix: ordered prefix]
    B --> G[Eventual: convergence over time]
    C --> H[Read result]
    D --> H
    E --> H
    F --> H
    G --> H
~~~

Một item có ETag mới không có nghĩa mọi region đã quan sát phiên bản đó ngay lập tức ở mọi consistency level. Ngược lại, một lần đọc strong trả về phiên bản mới nhất vẫn không ngăn hai request cùng cố ghi; muốn bảo vệ cập nhật phải dùng điều kiện phiên bản như ETag.

## 3. ETag là gì?

Mỗi item trong Azure Cosmos DB for NoSQL có thuộc tính hệ thống **`_etag`** do dịch vụ tạo. Khi item được cập nhật, ETag thay đổi. Giá trị này là **opaque token**: ứng dụng lưu và gửi lại nguyên vẹn, không phân tích thành thời gian, số thứ tự hoặc phép so sánh phiên bản.

Khi đọc item, response chứa ETag hiện tại. Khi muốn thay thế hoặc xóa item chỉ nếu nó chưa bị thay đổi, client gửi giá trị đó qua điều kiện **`If-Match`**:

- Nếu ETag gửi lên khớp với ETag hiện tại ở server, thao tác có thể được thực hiện.
- Nếu item đã thay đổi và ETag không còn khớp, server từ chối bằng **HTTP 412 Precondition Failed**.
- Ứng dụng đọc lại item, xem thay đổi mới và quyết định có thể áp dụng lại nghiệp vụ hay phải báo conflict.

~~~text
GET item
  <- item + ETag: E1

PUT/REPLACE item
  If-Match: E1
  -> ETag tại server vẫn là E1: cập nhật thành công, server phát E2
  -> ETag tại server đã là E2: trả 412, không ghi đè phiên bản mới
~~~

ETag giúp phát hiện **lost update** và **lost delete**. Nó không khóa item, không giữ transaction mở giữa lúc đọc và ghi, và không đảm bảo một lần đọc luôn mới nhất. Đây là **optimistic locking**: nhiều tiến trình có thể đọc cùng lúc; chỉ khi ghi mới kiểm tra xem phiên bản còn hợp lệ không.

## 4. If-Match và If-None-Match

| Header | Mục đích | Kết quả điển hình |
| --- | --- | --- |
| `If-Match: <etag>` | Chỉ cập nhật/xóa nếu tài nguyên vẫn ở phiên bản đã đọc | Khớp: thao tác tiếp tục; không khớp: 412 |
| `If-None-Match: <etag>` | Kiểm tra tài nguyên có thay đổi so với bản client đang giữ không | ETag vẫn khớp: có thể trả 304; khác: trả representation mới |

`If-Match` thường dùng cho **replace**, **upsert** khi thao tác thực sự là replace và **delete**. Với thao tác create, không có phiên bản hiện hữu để so khớp nên điều kiện này có thể bị bỏ qua theo API. Đối với upsert, phải hiểu rõ nhánh create/replace; không mặc định một điều kiện ETag có ý nghĩa giống nhau cho cả hai nhánh.

`If-None-Match` thường dùng cho cache validation hoặc kiểm tra item đã thay đổi chưa. Đây không phải cơ chế chống ghi đè. Với ứng dụng web, ETag HTTP của API có thể được dùng làm validator cho response, nhưng cần ánh xạ rõ tới phiên bản item và không để caller gửi ETag của tài nguyên khác.

**Không nhầm 409 và 412:** 409 thường là conflict như ID/unique key đã tồn tại; 412 là precondition không còn đúng, ví dụ ETag đã cũ. Ứng dụng có thể ánh xạ hai lỗi này thành các response khác nhau theo contract public API.

## 5. Optimistic locking trong Spring Data Cosmos bằng @Version

Spring Data Cosmos hỗ trợ optimistic locking cho những container/operation được hỗ trợ. Cách khai báo phổ biến là thêm field kiểu `String` tên `_etag` và đánh dấu bằng annotation `@Version`.

~~~java
import com.azure.spring.data.cosmos.core.mapping.Container;
import com.azure.spring.data.cosmos.core.mapping.PartitionKey;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;

@Container(
    containerName = "inventory",
    autoCreateContainer = false
)
public class InventoryDocument {
    @Id
    private String id;

    @PartitionKey
    private String warehouseId;

    private int availableQuantity;

    @Version
    private String _etag;

    public InventoryDocument() {
    }

    public String getId() { return id; }
    public String getWarehouseId() { return warehouseId; }
    public int getAvailableQuantity() { return availableQuantity; }
    public String getEtag() { return _etag; }

    public void setId(String id) { this.id = id; }
    public void setWarehouseId(String warehouseId) {
        this.warehouseId = warehouseId;
    }
    public void setAvailableQuantity(int quantity) {
        this.availableQuantity = quantity;
    }
}
~~~

Repository:

~~~java
import com.azure.spring.data.cosmos.repository.CosmosRepository;

public interface InventoryRepository
        extends CosmosRepository<InventoryDocument, String> {
}
~~~

Application service:

~~~java
import com.azure.cosmos.models.PartitionKey;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    public InventoryDocument reserve(
            String warehouseId, String itemId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        InventoryDocument item = inventory.findById(
            itemId, new PartitionKey(warehouseId))
            .orElseThrow(() -> new IllegalArgumentException("Item not found"));

        if (item.getAvailableQuantity() < quantity) {
            throw new InsufficientInventoryException();
        }

        item.setAvailableQuantity(item.getAvailableQuantity() - quantity);
        return inventory.save(item);
    }
}
~~~

Đây là ví dụ minh họa application flow; constructor, exception và package cần được tổ chức theo dự án. `@Version` cho phép Spring Data Cosmos đưa ETag hiện tại vào điều kiện ghi ở những thao tác được hỗ trợ. Khi một tiến trình khác đã cập nhật item, upsert/delete dựa trên ETag cũ sẽ thất bại thay vì âm thầm ghi đè.

**Không tự gán hoặc tính toán `_etag`.** Giá trị này do Cosmos DB quản lý và framework cập nhật sau khi ghi thành công. Không đưa `_etag` vào DTO cho người dùng chỉnh sửa, không đặt nó thành một timestamp hoặc tự tăng một con số.

### 5.1. @Version bảo vệ điều gì?

- Bảo vệ update/upsert/delete theo item ở những operation Spring Data Cosmos hỗ trợ.
- Phát hiện một tiến trình khác đã thay đổi item kể từ lần đọc.
- Giảm nguy cơ lost update/lost delete trong môi trường nhiều request/worker.
- Tạo điểm để application service xử lý conflict theo nghiệp vụ.

Nó **không** tự bảo vệ mọi query bulk hoặc thao tác SDK được gọi bên ngoài repository; cũng không tự tạo transaction xuyên nhiều item, container hoặc dịch vụ khác. Nếu một code path dùng SDK trực tiếp, phải truyền ETag/If-Match cho thao tác tương ứng.

### 5.2. Xử lý conflict đúng cách

Khi Spring Data phát hiện phiên bản không khớp, framework có thể ném exception thuộc nhóm optimistic locking/data access. Lớp application nên bắt tại boundary phù hợp và phân loại thành conflict nghiệp vụ. Không phụ thuộc vào một message text cụ thể; kiểm tra exception type và cause theo version Spring Data Cosmos đang dùng.

Luồng xử lý an toàn:

1. Đọc item và ETag hiện tại.
2. Tính thay đổi từ trạng thái đã đọc.
3. Gửi update có ETag.
4. Nếu thành công, trả kết quả.
5. Nếu conflict, đọc lại trạng thái mới và **đánh giá lại điều kiện nghiệp vụ**.
6. Chỉ thử lại số lần giới hạn nếu thao tác vẫn hợp lệ; nếu không, trả conflict cho caller.

Ví dụ reserve tồn kho: nếu hai người cùng đặt hàng, request thứ hai phải đọc lại lượng tồn kho. Nếu lượng còn lại không đủ, trả lỗi “không đủ hàng”; không được chỉ lấy payload cũ rồi ghi lại với ETag mới.

## 6. Dùng ETag trực tiếp với Azure Cosmos DB Java SDK

Khi cần thao tác SDK cấp thấp ngoài repository, có thể đặt ETag vào `CosmosItemRequestOptions`:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

public InventoryDocument updateWithEtag(
        CosmosContainer container,
        String itemId,
        String warehouseId,
        InventoryDocument itemReadEarlier,
        String etagReadEarlier) {

    itemReadEarlier.setAvailableQuantity(
        itemReadEarlier.getAvailableQuantity() - 1);

    CosmosItemRequestOptions options = new CosmosItemRequestOptions()
        .setIfMatchETag(etagReadEarlier);

    CosmosItemResponse<InventoryDocument> response =
        container.replaceItem(
            itemReadEarlier,
            itemId,
            new PartitionKey(warehouseId),
            options);

    return response.getItem();
}
~~~

Trong ví dụ, `etagReadEarlier` phải lấy từ response của lần đọc chính item đó, không lấy từ item khác hoặc một request khác. `replaceItem` cần đúng item ID và partition key; nếu ETag không còn hiện hành, SDK nhận lỗi precondition (412). Ví dụ chỉ minh họa conditional replace; code production cần xử lý exception, validate số lượng và tránh dùng lại object cũ sau conflict.

Nếu dùng Spring Data repository, ưu tiên `@Version` để framework quản lý ETag. Chỉ dùng `CosmosItemRequestOptions.setIfMatchETag` khi cần điều khiển SDK trực tiếp và đã có lý do rõ ràng.

## 7. ETag không phải session token hay application version

| Giá trị | Nguồn tạo | Mục đích | Có thể dùng thay ETag? |
| --- | --- | --- | --- |
| **ETag / `_etag`** | Cosmos DB server | Điều kiện ghi/xóa theo phiên bản item | Đây là token dùng cho If-Match |
| **Session token** | Cosmos DB response, được SDK lưu và gửi lại | Bảo đảm session consistency cho read/write flow | Không; nó không phải item version để conditional update |
| **Item ID** | Ứng dụng | Định danh item trong container | Không; ID không cho biết item đã thay đổi |
| **Partition key value** | Ứng dụng/container model | Định tuyến tới logical partition | Không; nó không phải version |
| **Application revision** | Ứng dụng | Phiên bản nghiệp vụ có thể hiển thị hoặc đồng bộ | Chỉ nếu có contract riêng; không thay ETag tự động |
| **Timestamp `_ts`** | Cosmos DB server | Thời điểm cập nhật dạng epoch seconds | Không; hai cập nhật có thể không được phân biệt đủ cho OCC |

ETag là giá trị opaque, chỉ nên so khớp bằng equality ở server. Không dùng chuỗi ETag để sắp xếp “bản nào mới hơn”, không parse nội dung và không chia sẻ ETag giữa các item. Nếu ứng dụng cần revision tăng đơn điệu để đồng bộ cache/event, tạo **application version** riêng và cập nhật nó bằng OCC.

## 8. Năm consistency level của Azure Cosmos DB for NoSQL

Cosmos DB cung cấp năm mức nhất quán, từ mạnh nhất đến yếu hơn:

| Mức | Bảo đảm chính | Khi cân nhắc |
| --- | --- | --- |
| **Strong** | Linearizability: đọc trả về phiên bản commit mới nhất | Nghiệp vụ cần mọi read thấy write mới nhất và chấp nhận trade-off latency/availability |
| **Bounded Staleness** | Độ trễ dữ liệu giữa các region bị chặn bởi K phiên bản hoặc T thời gian | Cần giới hạn stale read rõ ràng nhưng không cần Strong |
| **Session** | Read-your-writes, monotonic reads và write-follows-reads trong session phù hợp | Ứng dụng tương tác theo người dùng hoặc workflow |
| **Consistent Prefix** | Đọc thấy một prefix có thứ tự của các write, không thấy thứ tự bị đảo | Chấp nhận stale read nhưng cần giữ thứ tự write |
| **Eventual** | Các replica hội tụ cuối cùng; không đảm bảo read mới nhất hoặc thứ tự | Dữ liệu có thể stale tạm thời và ưu tiên độ sẵn sàng/độ trễ |

Consistency guarantee áp dụng cho một thao tác đọc trong phạm vi logical partition. Nó không tạo snapshot transaction xuyên nhiều partition hoặc nhiều container. Nếu use case cần nhiều thao tác đọc/ghi cùng nhất quán, phải xem xét transaction/batch trong cùng logical partition và giới hạn tương ứng.

### 8.1. Strong

Strong consistency cung cấp **linearizability**: một read luôn thấy phiên bản commit mới nhất, kể cả khi có các thao tác đồng thời. Với account nhiều region, write phải chờ bảo đảm replication mạnh giữa các region, nên latency có thể tăng đáng kể theo khoảng cách địa lý. Strong cũng có thể giảm khả năng phục vụ khi không thể đạt quorum cần thiết.

Strong không phải lựa chọn mặc định cho mọi ứng dụng. Hãy dùng khi yêu cầu nghiệp vụ thực sự cần đọc toàn cục giá trị mới nhất và đã đánh giá chi phí/latency. **Account cấu hình multi-region writes không hỗ trợ Strong consistency.**

Strong và Bounded Staleness dùng quorum read trên nhiều replica; với cùng mức RU, read throughput có thể thấp hơn các mức Session, Consistent Prefix và Eventual. Strong còn có thể làm write latency tăng khi account trải rộng nhiều region. Đánh giá bằng workload thực thay vì chỉ so tên consistency level.

### 8.2. Bounded Staleness

Bounded staleness giới hạn độ cũ tối đa của dữ liệu giữa các region bằng:

- **K:** số phiên bản/update tối đa mà một read có thể chậm.
- **T:** khoảng thời gian tối đa mà một read có thể chậm.

Read ở secondary region có thể không thấy write mới nhất tức thì, nhưng mức stale bị giới hạn theo K/T. Nếu replication lag vượt giới hạn, write trên partition liên quan có thể bị throttle cho tới khi độ trễ quay lại trong ngưỡng. Mức này hữu ích khi nghiệp vụ chấp nhận một khoảng trễ được định nghĩa, thay vì yêu cầu Strong.

### 8.3. Session

Session consistency thường là lựa chọn phù hợp cho ứng dụng tương tác. Trong một client session, Cosmos DB bảo đảm:

- **Read-your-writes:** sau khi ghi, đọc tiếp trong cùng session thấy write của session đó.
- **Monotonic reads:** không đọc phiên bản mới rồi quay lại phiên bản cũ hơn trong cùng session.
- **Write-follows-reads:** write tiếp theo tuân theo thứ tự đọc/ghi của session.

Bảo đảm read-your-writes cần một writer session duy nhất hoặc các writer chia sẻ session token. Session token được gắn với partition; SDK lưu token nhận từ response và tự gửi trong các lần đọc tiếp theo. Token không phải một snapshot version để quay về dữ liệu lịch sử; nó là minimum-version barrier.

Nếu ứng dụng có nhiều instance với nhiều CosmosClient, session token cache của mỗi client không tự chia sẻ. Request ghi có thể vào instance A, request đọc tiếp theo được load balancer đưa sang instance B; nếu B chưa có token của partition đó, nó có thể chưa nhìn thấy write vừa rồi trong một khoảng thời gian. Khi yêu cầu read-your-writes xuyên instance, cần session affinity hoặc truyền session token an toàn giữa các tầng rồi gắn vào request đọc tiếp theo. Không sửa nội dung token.

### 8.4. Consistent Prefix

Consistent Prefix bảo đảm các write được quan sát theo một prefix có thứ tự, không thấy write sau mà thiếu write trước trong thứ tự đó. Tuy nhiên, read có thể vẫn stale và không nhất thiết thấy write mới nhất. Mức này phù hợp khi thứ tự sự kiện quan trọng hơn độ mới tức thời, nhưng ứng dụng không cần read-your-writes theo từng session.

### 8.5. Eventual

Eventual consistency cho phép read từ replica chưa nhận đủ các write gần nhất. Khi không còn write mới, replica sẽ hội tụ về cùng trạng thái theo thời gian. Mức này có thể giảm độ trễ đọc và phù hợp với dữ liệu hiển thị phụ, dashboard hoặc workload chấp nhận stale data. Không dùng nó cho một quyết định như trừ tồn kho hoặc chấp nhận thanh toán nếu stale read có thể tạo sai kết quả nghiệp vụ.

## 9. Cấu hình consistency trong Spring Cloud Azure

Spring Cloud Azure cung cấp property `spring.cloud.azure.cosmos.consistency-level`. Ví dụ chọn Session:

~~~yaml
spring:
  cloud:
    azure:
      cosmos:
        endpoint: ${AZURE_COSMOS_ENDPOINT}
        database: orders-db
        consistency-level: SESSION
~~~

Tên property và các giá trị được hỗ trợ cần được xác minh theo phiên bản Spring Cloud Azure/Azure Spring Data Cosmos đang dùng. SDK Java cũng mặc định dùng **Session** nếu client không cấu hình mức khác.

Nếu tự tạo `CosmosClient` bằng Java SDK:

~~~java
import com.azure.cosmos.ConsistencyLevel;
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;

CosmosClient client = new CosmosClientBuilder()
    .endpoint(endpoint)
    .key(accountKey)
    .consistencyLevel(ConsistencyLevel.SESSION)
    .buildClient();
~~~

Đây là minh họa cách cấu hình client; trong production ưu tiên credential an toàn như Managed Identity thay vì đưa account key vào source code. Nếu starter đã tạo client, không tạo thêm client chỉ để đổi consistency; dùng property hoặc custom configuration đúng cách để tránh hai client có cấu hình khác nhau trong cùng ứng dụng.

### 9.1. Account default và client override

Consistency mặc định được cấu hình ở cấp account và áp dụng cho database/container bên dưới. Client/request có thể override theo giới hạn của API: với cơ chế `ConsistencyLevel` truyền thống, ứng dụng chỉ có thể **relax** xuống mức yếu hơn hoặc bằng account default; muốn tăng mức mạnh hơn thì phải cấu hình account tương ứng. SDK Java có API mới hơn cho read consistency strategy ở các phiên bản gần đây, nhưng khả năng này phụ thuộc phiên bản/feature support; không giả định mọi Spring Data Cosmos starter đều expose được.

Khi thay đổi consistency ở account, cần triển khai lại ứng dụng/client nếu cấu hình client đã được khởi tạo theo mức cũ. Hãy kiểm tra cả cấu hình account, client bean, preferred regions và request options; một YAML property không chứng minh tất cả instance đang chạy cùng cấu hình.

## 10. Session token trong ứng dụng nhiều instance

Với Session consistency, SDK thường tự quản lý session token trong cùng client instance. Chỉ cần quan tâm quản lý thủ công khi cần nối session qua nhiều client/process, ví dụ:

~~~mermaid
sequenceDiagram
    participant U as Browser / caller
    participant A as App instance A
    participant B as App instance B
    participant DB as Cosmos DB
    U->>A: POST update item
    A->>DB: Write
    DB-->>A: Success + session token T1
    A-->>U: Success + opaque session context (nếu cần)
    U->>B: GET item, kèm session context
    B->>DB: Read với token T1
    DB-->>B: Read theo minimum session version
    B-->>U: Latest value trong session
~~~

Không nhất thiết đưa raw session token cho browser. Có thể giữ token trong server-side session/cache hoặc đóng gói trong một context opaque đã được bảo vệ. Nếu truyền qua client, giới hạn kích thước, xác minh phạm vi/partition và tránh ghi log. Session token không phải credential và không cấp quyền đọc; identity/RBAC vẫn được kiểm tra độc lập.

Session token **partition-bound**. Không dùng token nhận từ partition A cho partition B. Nếu client instance được tạo lại, cache token trong memory của client mới cũng được tạo lại; cho đến khi có write/token mới, read trên partition chưa có token có thể mang hành vi gần Eventual.

## 11. Multi-region writes và conflict resolution

Account Cosmos DB có thể cấu hình nhiều write region để giảm latency ghi tại các vùng địa lý khác nhau và tăng khả năng phục hồi. Nhưng nhiều write region làm phát sinh khả năng hai region cập nhật cùng item gần như đồng thời.

Những điểm cần nhớ:

- **Strong consistency không hỗ trợ** cho account multi-region writes.
- ETag/OCC ở mỗi region không thay thế cơ chế giải quyết conflict xuyên region.
- Conflict có thể phát sinh khi insert cùng ID, replace cùng item hoặc delete ở một vùng đồng thời update ở vùng khác.
- Cosmos DB có conflict resolution policy; mặc định thường là **Last Write Wins (LWW)** theo timestamp `_ts`, hoặc có thể dùng một property số tùy chỉnh làm conflict resolution path.
- API for NoSQL cũng hỗ trợ custom conflict resolution bằng stored procedure merge theo cấu hình container.

Ví dụ hai region cùng đọc item với ETag cục bộ tương ứng rồi cùng ghi. Mỗi thao tác có thể được chấp nhận tại region của nó, sau đó xung đột được giải quyết khi các thay đổi hội tụ. Vì vậy, không xem ETag như một khóa phân tán toàn cầu ngăn mọi write đồng thời trên nhiều region.

Nếu nghiệp vụ cần quy tắc hợp nhất như “không được giảm số dư xuống âm” hoặc “chỉ một yêu cầu đặt chỗ được thắng”, LWW theo timestamp có thể không đủ. Có thể cần:

- Chuyển các thao tác ghi quan trọng về một write region/đầu mối điều phối.
- Thiết kế operation ID và idempotency để tránh tác dụng phụ trùng.
- Dùng custom conflict resolution phù hợp hoặc một workflow nghiệp vụ giải quyết conflict.
- Lưu các command/event bất biến rồi tính lại trạng thái thay vì ghi đè một aggregate ở nhiều region.

Không bật multi-region writes chỉ vì muốn giảm latency mà chưa xác định conflict semantics. Thử failover và concurrent write giữa region trong môi trường Azure thật trước khi đưa vào production.

## 12. Chọn consistency level theo use case

| Use case | Mức có thể bắt đầu đánh giá | Lý do và điều kiện |
| --- | --- | --- |
| Giỏ hàng hoặc hồ sơ theo phiên người dùng | **Session** | Thường cần đọc thấy thay đổi vừa ghi trong cùng user session |
| Inventory dùng một write region | **Session + ETag OCC** hoặc Strong khi yêu cầu toàn cục thực sự cần | ETag chống lost update; consistency quyết định freshness của read |
| Báo cáo dashboard chấp nhận dữ liệu trễ | **Eventual** hoặc Session tùy trải nghiệm | Tối ưu độ trễ/throughput khi stale data chấp nhận được |
| Hệ thống cần giới hạn stale read toàn vùng | **Bounded Staleness** | Có thể định nghĩa K/T để nghiệp vụ chấp nhận |
| Dữ liệu log/event cần giữ thứ tự prefix | **Consistent Prefix** | Không cần đọc phiên bản mới nhất ngay lập tức |
| Nghiệp vụ cần mọi region đọc latest commit | **Strong** nếu account topology hỗ trợ | Đánh giá latency/availability; không dùng với multi-region writes |

Đây là điểm khởi đầu, không phải cấu hình chung cho mọi hệ thống. Hãy mô tả yêu cầu bằng câu hỏi cụ thể:

1. Sau khi ghi, chính caller có phải đọc thấy ngay kết quả không?
2. Một request ở region khác có cần thấy write ngay không?
3. Chấp nhận dữ liệu cũ tối đa bao lâu hoặc bao nhiêu update?
4. Nếu hai người cập nhật cùng item, ai thắng và ứng dụng làm gì?
5. Có cho phép nhiều region cùng ghi không?
6. Độ trễ/availability nào quan trọng hơn trong tình huống region bị lỗi?

**Consistency level không thay thế transaction design.** Nếu thao tác cần thay đổi nhiều item trong cùng logical partition, dùng transactional batch hoặc stored procedure theo giới hạn Cosmos DB. Nếu cần cập nhật Cosmos DB và phát message/ghi Blob, dùng outbox/saga; Strong consistency của Cosmos DB không tạo distributed transaction với dịch vụ khác.

## 13. ETag và consistency phối hợp như thế nào?

Một luồng cập nhật item an toàn có thể dùng cả hai:

1. SDK đọc item theo Session consistency và nhận ETag `E1`.
2. Application kiểm tra nghiệp vụ và tạo thay đổi.
3. Spring Data Cosmos `save` item có `@Version`; server kiểm tra ETag.
4. Nếu item không thay đổi, write thành công và server phát ETag mới `E2`.
5. Nếu item đã được cập nhật, server trả 412; ứng dụng đọc lại và tính lại nghiệp vụ.
6. Read sau write trong cùng session dùng session token do SDK quản lý để quan sát phiên bản mới theo Session guarantee.

Ở đây:

- **ETag** ngăn một write dựa trên bản cũ ghi đè bản mới.
- **Session token** giúp read tiếp theo trong cùng session không quay về phiên bản cũ.
- **Consistency level** xác định mức bảo đảm read giữa replica/region.
- **Business rule** quyết định có thể áp dụng lại command sau conflict hay phải từ chối.

Nếu hai instance có client khác nhau, session token cache không tự chia sẻ; nếu đọc qua region khác hoặc multi-region writes, cần xét thêm topology, conflict resolution và session-token flow.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Không khai báo `@Version` nhưng nghĩ repository tự chống lost update | Update cũ có thể ghi đè update mới | Ánh xạ `_etag` bằng `@Version` hoặc dùng If-Match trong SDK |
| Tự tạo/đổi giá trị `_etag` | Conditional write không còn đúng | Để Cosmos DB quản lý; chỉ giữ nguyên token từ response |
| Retry ngay lỗi 412 với cùng payload | Lặp conflict hoặc ghi đè quyết định mới | Đọc lại, kiểm tra business invariant và tính lại |
| Coi ETag là timestamp/version number | So sánh thứ tự sai | Dùng như opaque token, chỉ so khớp |
| Nghĩ Strong consistency thay thế ETag | Vẫn có thể có concurrent writes | Dùng OCC cho thao tác cập nhật |
| Nghĩ ETag bảo vệ toàn cục trong multi-region writes | Xung đột xuyên region vẫn có thể xảy ra | Thiết kế conflict resolution và write topology |
| Dùng Eventual cho read-after-write của UI | Caller có thể thấy dữ liệu cũ | Session hoặc truyền session token khi qua nhiều client |
| Mỗi instance tự tạo CosmosClient và mong session tự chia sẻ | Token cache bị tách | Dùng client lifecycle hợp lý hoặc truyền token an toàn |
| Chọn Strong cho multi-region writes | Cấu hình không được hỗ trợ | Chọn topology/consistency tương thích |
| Coi 412 là lỗi transient và retry tự động vô hạn | Tăng tải nhưng không giải quyết conflict | Xử lý conflict ở application layer |
| Dùng `@Version` nhưng bỏ qua bulk/SDK path | Đường ghi khác không có OCC | Kiểm tra mọi write path, thêm If-Match cho SDK |

## 15. Kiểm thử optimistic locking và consistency

### 15.1. Kiểm thử hai writer cùng ETag

Kịch bản cần có:

1. Tạo item ban đầu.
2. Đọc item hai lần, giữ hai bản copy có cùng ETag.
3. Writer A cập nhật và ghi thành công.
4. Writer B ghi bản copy cũ.
5. Xác minh writer B nhận conflict/412 thay vì ghi đè.
6. Đọc lại item, áp dụng lại business rule và kiểm tra kết quả cuối.

Với Spring Data Cosmos, kiểm thử repository thật với entity có `@Version`. Mock repository chỉ chứng minh application service xử lý exception; nó không chứng minh framework gửi đúng ETag.

### 15.2. Kiểm thử consistency

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Write rồi read bằng cùng client/session | Session read-your-writes |
| Write ở instance A, read ở instance B | Hành vi khi session token không được chia sẻ |
| Đọc từ preferred region khác | Độ trễ replication và consistency đã chọn |
| Strong account với nhiều region | Read thấy latest committed theo guarantee; đo write latency |
| Bounded staleness | Staleness nằm trong giới hạn K/T theo cấu hình |
| Multi-region writes | Conflict policy, hub resolution và recovery sau failover |
| ETag conflict | 412 không bị nhầm với 429/5xx hoặc permission error |

Cosmos DB Emulator hữu ích cho CRUD và một số test concurrency cơ bản, nhưng không mô phỏng đầy đủ latency liên vùng, replication, Strong consistency toàn cầu, multi-region writes và failover. Các guarantee này phải được kiểm thử trên Azure test account có topology phù hợp.

### 15.3. Metrics và diagnostics

Theo dõi:

- Số lượng và tỷ lệ **412 Precondition Failed** theo container/operation.
- Số lần application re-read/retry sau conflict và tỷ lệ conflict cuối cùng trả về caller.
- p50/p95/p99 latency cho read/write theo region.
- RU charge, 429/throttling và retry-after.
- Replication latency, consistency/PBS metrics và trạng thái region.
- Số conflict phát sinh/được giải quyết trong multi-region writes.

Không ghi toàn bộ item hoặc session token vào log. Dùng activity ID, request diagnostics và operation ID để đối chiếu; bảo vệ thông tin tenant và dữ liệu nhạy cảm.

## 16. Bài tập thực hành

**Bài tập 1 — Lost update.** Hai request cùng đọc số dư tài khoản là 100. Request A trừ 30, request B trừ 20. Mô phỏng hai write không có ETag và có ETag. Xác định kết quả đúng phải là 50 hay 70 trong từng trường hợp và giải thích.

**Bài tập 2 — Spring Data @Version.** Tạo entity `InventoryDocument` với `_etag` và `@Version`. Viết repository/service để reserve hàng; chạy hai test đồng thời cùng đọc một item và xác minh một request phải đọc lại, tính lại.

**Bài tập 3 — Xử lý 412.** Viết application flow bắt lỗi optimistic locking, đọc item mới và áp dụng lại quy tắc “không cho tồn kho âm”. Nêu trường hợp nào được retry và trường hợp nào phải trả conflict/insufficient inventory.

**Bài tập 4 — Chọn consistency.** Một ứng dụng có user ở ba region. Sau khi user đổi địa chỉ, lần GET kế tiếp phải thấy địa chỉ mới; dashboard toàn cầu có thể trễ 30 giây. Đề xuất mức consistency và session-token strategy cho hai use case.

**Bài tập 5 — Multi-region writes.** Hai region cùng cập nhật một item tồn kho. Giải thích tại sao Strong không khả dụng, ETag cục bộ chưa đủ để giải quyết conflict toàn cục và vì sao LWW có thể sai với business invariant. Đề xuất một chiến lược ghi/merge.

**Bài tập 6 — Session qua nhiều instance.** Request POST đi vào instance A, GET tiếp theo vào instance B. Mô tả session token được SDK cache ở đâu, vì sao B có thể chưa có token và cách truyền token an toàn khi cần read-your-writes xuyên instance.

**Bài tập 7 — If-None-Match.** Thiết kế endpoint đọc item hỗ trợ cache validation bằng ETag. Phân biệt 304 Not Modified với 412 Precondition Failed và xác định header nào dùng cho GET, header nào dùng cho update.

**Bài tập 8 — Kiểm thử thực tế.** Lập test matrix cho ETag, Session, Strong, Bounded Staleness và multi-region writes. Chỉ ra test nào có thể chạy ở unit/emulator và test nào cần Azure test account.

## 17. Ghi nhớ

- **ETag/`_etag` là token phiên bản opaque do Cosmos DB tạo.** Dùng `If-Match` để bảo vệ replace/upsert/delete khỏi lost update; không tự parse hoặc thay đổi ETag.
- **HTTP 412** cho biết precondition không còn đúng. Đọc lại item, đánh giá lại business rule rồi mới retry; không gửi lại payload cũ một cách mù quáng.
- Spring Data Cosmos hỗ trợ optimistic locking bằng field String `_etag` gắn `@Version` cho các container/operation được hỗ trợ.
- **Consistency level là bảo đảm của read**, không phải khóa ghi. ETag và consistency giải quyết hai vấn đề khác nhau và thường được dùng cùng nhau.
- Năm mức là **Strong, Bounded Staleness, Session, Consistent Prefix và Eventual**. Chọn theo read-your-writes, độ stale chấp nhận được, thứ tự, latency và topology region.
- Session token được SDK tự quản lý trong client và **gắn với partition**. Nhiều instance/client cần chiến lược truyền token nếu phải chia sẻ cùng session.
- **Multi-region writes không hỗ trợ Strong** và có thể phát sinh conflict xuyên region. ETag không thay thế conflict resolution policy hoặc quy tắc nghiệp vụ.
- Kiểm thử cả concurrent writers, session qua nhiều instance, stale reads, failover và diagnostics trên Azure environment phù hợp; Emulator không chứng minh được mọi guarantee đa vùng.

## 18. Tài liệu tham khảo

- [Optimistic concurrency control và ETag trong Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/database-transactions-optimistic-concurrency)
- [Azure Spring Data Cosmos — Optimistic Locking với @Version](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-data-cosmos-readme?view=azure-java-stable)
- [Năm consistency level của Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/consistency-levels)
- [Quản lý consistency và session token](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-manage-consistency)
- [CosmosClientBuilder và consistencyLevel trong Java SDK](https://learn.microsoft.com/en-us/java/api/com.azure.cosmos.cosmosclientbuilder?view=azure-java-stable)
- [HTTP status codes: 412 Precondition Failed](https://learn.microsoft.com/en-us/rest/api/cosmos-db/http-status-codes-for-cosmosdb)
- [Conflict resolution policies cho multi-region writes](https://learn.microsoft.com/en-us/azure/cosmos-db/conflict-resolution-policies)
- [Reliability và multi-region writes của Cosmos DB for NoSQL](https://learn.microsoft.com/en-us/azure/reliability/reliability-cosmos-db-nosql)
