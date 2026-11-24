# Ghi có điều kiện, khóa lạc quan và lựa chọn tính nhất quán

## 1. Bối cảnh và mục tiêu

Trong chương **Dữ liệu AWS** của module **Spring Cloud Provider Integration**, Spring Boot kết nối đến các dịch vụ managed bằng Spring Cloud AWS (AWSpring) và AWS SDK. Khi làm việc với Amazon DynamoDB, một thao tác `PutItem` hoặc `UpdateItem` có thể thành công về mặt kỹ thuật nhưng **không đúng nghiệp vụ** nếu hai người dùng cập nhật đồng thời, một request bị gửi lại hoặc ứng dụng quyết định dựa trên dữ liệu đọc chưa mới nhất.

Ví dụ: dịch vụ đặt chỗ cho thuê bất động sản có bản ghi:

~~~text
tenantId   = "tenant-a"                                    (partition key)
sortKey    = "RES#2026-11-24T08:00:00.000Z#res-1001"       (sort key)
state      = "PENDING"
version    = 1
propertyKey = "tenant-a#house-99"
createdAt  = "2026-11-24T08:00:00.000Z"
~~~

Hai nhân viên có thể đồng thời xác nhận hoặc hủy lượt đặt. Một worker cũng có thể gửi lại request tạo reservation sau timeout. Nếu ứng dụng chỉ đọc item rồi ghi lại không có điều kiện, dữ liệu dễ bị ghi đè. Bài này tập trung vào ba cơ chế liên quan nhưng giải quyết **ba nhu cầu khác nhau**:

- **Conditional write:** DynamoDB chỉ ghi/xóa/cập nhật khi một điều kiện trên item hiện tại thỏa mãn, ví dụ "chỉ tạo nếu key chưa tồn tại" hoặc "chỉ xác nhận nếu state còn PENDING".
- **Optimistic locking:** phiên bản `version` của item được so sánh khi cập nhật để phát hiện có ai đã sửa từ lần đọc trước.
- **Read consistency:** ứng dụng chọn *eventually consistent* hay *strongly consistent* cho thao tác đọc ở nơi được hỗ trợ; lựa chọn này quyết định độ mới của dữ liệu được quan sát, nhưng **không thay thế điều kiện ghi để bảo vệ concurrency**.

Sau bài học, bạn sẽ:

1. Phân biệt ngữ nghĩa `PutItem`, `UpdateItem` và ghi có điều kiện.
2. Thiết kế điều kiện `attribute_not_exists`, `attribute_exists`, kiểm tra trạng thái và version trong cùng một yêu cầu.
3. Ánh xạ entity với `@DynamoDbVersionAttribute` của AWS SDK for Java v2 Enhanced Client; xử lý xung đột khi có hai request cùng cập nhật.
4. Chọn tính nhất quán khi đọc bảng chính, LSI và GSI; hiểu giới hạn của global tables và tính nhất quán xuyên nhiều trang.
5. Đưa logic vào Spring Boot, cấu hình IAM/credentials, kiểm thử DynamoDB Local và xác định khi nào cần DynamoDB transaction.
6. Đánh giá chi phí, retry, idempotency và khác biệt với các dịch vụ dữ liệu managed của Azure và Google Cloud.

> **Lưu ý phạm vi:** ví dụ dùng AWS SDK v2 Enhanced Client cùng DynamoDB. Các phiên bản AWSpring có thể cung cấp `DynamoDbTemplate` và auto-configuration tương ứng, nhưng hỗ trợ từng operation phụ thuộc phiên bản. `@Transactional` của JPA không mặc nhiên biến các write DynamoDB thành transaction, và các annotation của DynamoDB không phải annotation JPA.

## 2. Điều gì xảy ra nếu ghi không có điều kiện?

### 2.1. Ghi đè khi hai request đọc cùng trạng thái

Giả sử A và B cùng đọc item `state=PENDING, version=1`:

~~~mermaid
sequenceDiagram
    participant A as Nhân viên A
    participant B as Nhân viên B
    participant DB as DynamoDB
    A->>DB: GetItem → PENDING, version=1
    B->>DB: GetItem → PENDING, version=1
    A->>DB: PutItem/UpdateItem state=CONFIRMED
    DB-->>A: Thành công
    B->>DB: PutItem/UpdateItem state=CANCELLED
    DB-->>B: Thành công nếu không có condition
    Note over DB: B đã ghi đè quyết định của A
~~~

DynamoDB thực hiện mỗi write trên một item theo ngữ nghĩa atomic, nhưng atomic **không có nghĩa** ứng dụng tự động phát hiện quyết định stale được đưa ra từ lần đọc trước. Không có condition hoặc transaction phù hợp, thao tác ghi sau có thể thay đổi kết quả ghi trước.

### 2.2. Ba cơ chế giải quyết các rủi ro khác nhau

| Vấn đề | Cơ chế phù hợp | Điều kiện ví dụ |
| --- | --- | --- |
| Tạo trùng item vì request gửi lại | Conditional Put | `attribute_not_exists(tenantId)` trên item có cùng composite key |
| Xác nhận reservation đã bị hủy | Conditional Update | `#state = :pending` |
| Hai nhân viên cùng sửa những trường khác nhau từ một bản đọc | Optimistic locking | `#version = :expectedVersion`, rồi tăng version |
| Phải sửa hai item cùng thành công hoặc cùng thất bại | DynamoDB transaction | `TransactWriteItems` với điều kiện thích hợp |
| Phải thấy dữ liệu vừa ghi ngay trên bảng | Strongly consistent read tại nơi hỗ trợ | `ConsistentRead=true` trên table/LSI |
| Đọc qua GSI chưa thấy item mới | Thiết kế chấp nhận eventual consistency hoặc đọc theo base table | GSI không hỗ trợ strong read |

**Quy tắc trọng tâm:** kết hợp "đọc nhất quán mạnh" và "ghi không có điều kiện" **vẫn không bảo vệ** trường hợp hai request đọc cùng một giá trị rồi cùng ghi. Phần quyết định cuối cùng phải được kiểm tra trong **write request** (hoặc trong transaction có ngữ nghĩa phù hợp).

## 3. Chuẩn bị bảng và ứng dụng Spring Boot

### 3.1. Mô hình dữ liệu

Ví dụ dùng bảng `reservation_record`:

| Thuộc tính | Kiểu | Vai trò |
| --- | --- | --- |
| `tenantId` | String | Partition key của bảng |
| `sortKey` | String | Sort key của bảng, `RES#<UTC timestamp>#<reservationId>` |
| `reservationId` | String | Mã lượt đặt nghiệp vụ |
| `state` | String | `PENDING`, `CONFIRMED`, `CANCELLED` |
| `version` | Number | Phiên bản dùng cho optimistic locking |
| `propertyKey` | String | Partition key của GSI `by-property` |
| `createdAt` | String | Sort key của GSI `by-property`, chuỗi UTC cùng format |

Ví dụ này cố ý dùng composite key để làm rõ điều kiện tạo mới: **một item** được nhận diện bởi cặp (`tenantId`, `sortKey`), không phải chỉ một giá trị `tenantId`. Hai reservation khác nhau của cùng tenant có thể tồn tại đồng thời.

`createdAt` và phần timestamp trong `sortKey` phải được chuẩn hóa ở UTC, độ chính xác cố định, nếu muốn Query theo thứ tự thời gian bằng khóa String. `version` là số nguyên tăng dần; không dùng thời gian máy khách làm phiên bản vì đồng hồ không bảo đảm duy nhất và đồng bộ.

### 3.2. Dependency và cấu hình

Với AWSpring, dependency thường là:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-dynamodb</artifactId>
</dependency>
~~~

Dùng **AWSpring BOM phù hợp với phiên bản Spring Boot** để quản lý starter và AWS SDK liên quan. Ở dự án không dùng starter, khai báo AWS SDK v2 `dynamodb` và `dynamodb-enhanced` dưới AWS SDK BOM:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb</artifactId>
</dependency>
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb-enhanced</artifactId>
</dependency>
~~~

Các code Java trong bài dùng `DynamoDbClient` cho write expression cấp thấp và `DynamoDbEnhancedClient` cho ánh xạ bean. AWSpring phiên bản tương thích có thể auto-configure client; nếu tự tạo các bean, đừng tạo trùng với bean starter đã cung cấp.

Ví dụ cấu hình AWSpring khi triển khai trên AWS:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        enabled: true
~~~

Dùng IAM role/workload identity cho workload trên ECS, EKS hoặc EC2 và default credential provider chain. Không hardcode AWS access key, secret access key hoặc session token vào `application.yml`, source code hay Git.

### 3.3. Tạo DynamoDB Local để thực hành

~~~bash
docker run --rm --name dynamodb-local -p 8000:8000 amazon/dynamodb-local:latest
~~~

Với Bash, thiết lập credentials **giả** chỉ trong terminal thử nghiệm:

~~~bash
export AWS_ACCESS_KEY_ID=local
export AWS_SECRET_ACCESS_KEY=local
export AWS_DEFAULT_REGION=ap-southeast-1
~~~

Cấu hình profile local cho AWSpring ở phiên bản hỗ trợ:

~~~yaml
# application-local.yml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        endpoint: http://localhost:8000
~~~

Tạo bảng và GSI dùng cho các phần tiếp theo:

~~~bash
aws dynamodb create-table \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --attribute-definitions \
    AttributeName=tenantId,AttributeType=S \
    AttributeName=sortKey,AttributeType=S \
    AttributeName=propertyKey,AttributeType=S \
    AttributeName=createdAt,AttributeType=S \
  --key-schema \
    AttributeName=tenantId,KeyType=HASH \
    AttributeName=sortKey,KeyType=RANGE \
  --global-secondary-indexes \
    '[{"IndexName":"by-property","KeySchema":[{"AttributeName":"propertyKey","KeyType":"HASH"},{"AttributeName":"createdAt","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]' \
  --billing-mode PAY_PER_REQUEST
~~~

Chỉ các thuộc tính tham gia khóa của bảng/GSI nằm trong `--attribute-definitions`; `state` và `version` là thuộc tính thường. Bảng/index phải tồn tại trước khi chạy code. Trong production nên tạo qua IaC (CloudFormation, CDK, Terraform), gắn quyền IAM theo tài nguyên và đo năng lực truy cập.

## 4. Ghi có điều kiện với DynamoDB

### 4.1. `ConditionExpression` được đánh giá khi write

DynamoDB hỗ trợ điều kiện trên `PutItem`, `UpdateItem`, `DeleteItem` và `ConditionCheck` trong transaction. Điều kiện được đánh giá **atomically trên item đích cùng thao tác ghi**: nếu điều kiện sai, write không áp dụng và API trả lỗi như `ConditionalCheckFailedException`.

Một số biểu thức hữu ích:

| Biểu thức | Ý nghĩa | Trường hợp dùng |
| --- | --- | --- |
| `attribute_not_exists(tenantId)` | Thuộc tính key không tồn tại trên item đích | Chỉ tạo nếu item cùng primary key chưa tồn tại |
| `attribute_exists(tenantId)` | Item đích đã có thuộc tính key | Chặn cập nhật có thể tạo item mới |
| `#state = :pending` | Trạng thái hiện tại vẫn là PENDING | Chỉ xác nhận reservation chưa bị xử lý |
| `#version = :expected` | Phiên bản DB bằng phiên bản request đã đọc | Chống ghi từ bản đọc cũ |
| `#state = :pending AND #version = :expected` | Cả quy tắc nghiệp vụ và khóa lạc quan đều thỏa | Chuyển trạng thái an toàn với concurrency |

Trong condition expression, `#state` và `:pending` là placeholder được ánh xạ qua `ExpressionAttributeNames` và `ExpressionAttributeValues`. Dùng placeholder cho tên attribute giúp tránh các tên trùng reserved word, đồng thời không phải ghép trực tiếp giá trị do người dùng nhập vào expression.

**Chú ý composite key:** khi gọi `PutItem` cho khóa (`tenant-a`, `RES#...#res-2`), `attribute_not_exists(tenantId)` được kiểm tra trên **item có đủ khóa đó**. Item khác cùng `tenantId` nhưng sort key khác không làm điều kiện thất bại.

### 4.2. Chỉ tạo reservation khi key chưa tồn tại

Ví dụ dùng SDK v2 cấp thấp để thể hiện rõ condition và các attribute viết xuống bảng. Ta **chủ động gán `version = 1`** cho bản ghi mới; những update sau đó có thể đi qua Enhanced Client với `@DynamoDbVersionAttribute`.

~~~java
import java.util.Map;
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;

@Repository
public class ReservationConditionalWriter {
    private final DynamoDbClient client;

    public ReservationConditionalWriter(DynamoDbClient client) {
        this.client = client;
    }

    public void createOnly(
            String tenantId,
            String sortKey,
            String reservationId,
            String propertyKey,
            String createdAt) {
        client.putItem(PutItemRequest.builder()
                .tableName("reservation_record")
                .item(Map.of(
                        "tenantId", s(tenantId),
                        "sortKey", s(sortKey),
                        "reservationId", s(reservationId),
                        "propertyKey", s(propertyKey),
                        "createdAt", s(createdAt),
                        "state", s("PENDING"),
                        "version", n(1)))
                .conditionExpression("attribute_not_exists(#pk)")
                .expressionAttributeNames(Map.of("#pk", "tenantId"))
                .build());
    }

    private static AttributeValue s(String value) {
        return AttributeValue.builder().s(value).build();
    }

    private static AttributeValue n(long value) {
        return AttributeValue.builder()
                .n(Long.toString(value)).build();
    }
}
~~~

Nếu **cùng full key** đã tồn tại, DynamoDB trả `ConditionalCheckFailedException`; ứng dụng nên trả lỗi xung đột hoặc xử lý request lặp bằng idempotency key ổn định. Đây **không** phải lỗi kết nối cần retry mù.

Không nên sinh `sortKey` mới với timestamp hiện tại ở mỗi lần retry. Nếu request gốc đã ghi thành công nhưng response thất lạc, retry với key khác sẽ tạo bản ghi khác và vô hiệu hóa bảo vệ tạo trùng. Nghiệp vụ phải giữ một mã/idempotency key cố định, hoặc lưu mapping đủ để tái tạo cùng full key.

### 4.3. Conditional update theo trạng thái và version

Giả sử client đã đọc `state=PENDING, version=1`, cần đổi thành `CONFIRMED` chỉ khi **cả state và version vẫn như cũ**. API `UpdateItem` có thể cập nhật một trường mà không đưa toàn bộ item lên lại.

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ReturnValue;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemResponse;

// Phương thức bên trong class có field: DynamoDbClient client.
public UpdateItemResponse confirmIfPending(
        String tenantId, String sortKey, long expectedVersion) {

    return client.updateItem(UpdateItemRequest.builder()
            .tableName("reservation_record")
            .key(Map.of(
                    "tenantId", AttributeValue.builder()
                            .s(tenantId).build(),
                    "sortKey", AttributeValue.builder()
                            .s(sortKey).build()))
            .updateExpression(
                    "SET #state = :confirmed, #version = #version + :one")
            .conditionExpression(
                    "attribute_exists(tenantId) "
                    + "AND #state = :pending "
                    + "AND #version = :expected")
            .expressionAttributeNames(Map.of(
                    "#state", "state",
                    "#version", "version"))
            .expressionAttributeValues(Map.of(
                    ":confirmed", AttributeValue.builder()
                            .s("CONFIRMED").build(),
                    ":pending", AttributeValue.builder()
                            .s("PENDING").build(),
                    ":expected", AttributeValue.builder()
                            .n(Long.toString(expectedVersion)).build(),
                    ":one", AttributeValue.builder().n("1").build()))
            .returnValues(ReturnValue.ALL_NEW)
            .build());
}
~~~

Điều kiện và phép tăng version thuộc **cùng một write item atomic**, không có cửa sổ race giữa kiểm tra và ghi. Nếu item không tồn tại, đã bị hủy, hoặc version đã thay đổi, request sẽ thất bại. `ReturnValue.ALL_NEW` yêu cầu DynamoDB trả item sau khi cập nhật để caller lấy version mới; không cần một `GetItem` ngay sau mỗi write chỉ để biết giá trị đã ghi.

Với thao tác hủy, có thể dùng điều kiện tương tự nhưng `:next=CANCELLED` và trạng thái đích khác. Khi yêu cầu chuyển trạng thái không hợp lệ, trả lỗi nghiệp vụ rõ ràng; khi version stale, thông báo cần tải lại hoặc xử lý lại từ dữ liệu mới.

### 4.4. Conditional delete và khi nào cần soft delete

Tương tự Update, `DeleteItem` cũng hỗ trợ condition. Nếu yêu cầu “chỉ xóa khi version còn là 3”, đặt `#version = :expected`; item đã được sửa sẽ không bị xóa. Với hệ thống có audit trail, trạng thái `CANCELLED` thường phù hợp hơn xóa vật lý vì còn dữ liệu phục vụ kiểm toán, đối soát hoặc trả lời khách hàng.

Chọn cách xóa dựa vào thời hạn lưu, chính sách dữ liệu cá nhân, backup và yêu cầu khôi phục. DynamoDB TTL dùng epoch seconds và chạy xóa bất đồng bộ; TTL **không** thay thế việc kiểm tra hạn theo nghiệp vụ ở thời điểm xử lý request.

## 5. Khóa lạc quan với `@DynamoDbVersionAttribute`

### 5.1. Optimistic locking hoạt động ra sao?

**Optimistic locking** giả định phần lớn update không xảy ra xung đột. Thay vì giữ một khóa phân tán trong suốt thời gian người dùng đang chỉnh sửa, mỗi item mang một thuộc tính số `version`:

1. A và B cùng đọc item có `version=1`.
2. A gửi update điều kiện `version=1`; DynamoDB cho phép và chuyển version thành 2.
3. B gửi update cũng kỳ vọng `version=1`; điều kiện không thỏa, request thất bại.
4. B phải đọc lại dữ liệu và quyết định hợp nhất, yêu cầu người dùng xác nhận lại, hoặc bỏ thao tác.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as DynamoDB
    A->>DB: Đọc state=PENDING, version=1
    B->>DB: Đọc state=PENDING, version=1
    A->>DB: Update nếu version=1
    DB-->>A: OK; version mới=2
    B->>DB: Update nếu version=1
    DB-->>B: ConditionalCheckFailedException
    Note over B: Đọc lại và áp dụng logic nghiệp vụ
~~~

**Ưu điểm:** không giữ lock lâu trong DB; phát hiện lost update; phù hợp khi xung đột ít. **Giới hạn:** request nào dựa trên bản đọc cũ phải xử lý xung đột; cơ chế này không tự chọn bản cập nhật “đúng” về nghiệp vụ, không tự khóa bảng và không biến một chuỗi nhiều write thành transaction.

### 5.2. Ánh xạ entity dùng Enhanced Client

AWS SDK for Java v2 Enhanced Client hỗ trợ annotation `@DynamoDbVersionAttribute` với **`VersionedRecordExtension`**. Ví dụ entity:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbBean;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSortKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondaryPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondarySortKey;
import software.amazon.awssdk.enhanced.dynamodb.extensions.annotations.DynamoDbVersionAttribute;

@DynamoDbBean
public class ReservationItem {
    private String tenantId;
    private String sortKey;
    private String reservationId;
    private String propertyKey;
    private String createdAt;
    private String state;
    private Long version;

    public ReservationItem() {}

    @DynamoDbPartitionKey
    public String getTenantId() { return tenantId; }
    public void setTenantId(String value) { this.tenantId = value; }

    @DynamoDbSortKey
    public String getSortKey() { return sortKey; }
    public void setSortKey(String value) { this.sortKey = value; }

    public String getReservationId() { return reservationId; }
    public void setReservationId(String value) { this.reservationId = value; }

    @DynamoDbSecondaryPartitionKey(indexNames = "by-property")
    public String getPropertyKey() { return propertyKey; }
    public void setPropertyKey(String value) { this.propertyKey = value; }

    @DynamoDbSecondarySortKey(indexNames = "by-property")
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String value) { this.createdAt = value; }

    public String getState() { return state; }
    public void setState(String value) { this.state = value; }

    @DynamoDbVersionAttribute
    public Long getVersion() { return version; }
    public void setVersion(Long value) { this.version = value; }
}
~~~

**Kiểm tra import:** `@DynamoDbVersionAttribute` thuộc package `software.amazon.awssdk.enhanced.dynamodb.extensions.annotations`, còn các annotation khóa thuộc `software.amazon.awssdk.enhanced.dynamodb.mapper.annotations`. Cần dùng đúng version của SDK v2 vì một số IDE có thể tự import nhầm annotation tương tự từ thư viện khác.

Ở cấu hình Enhanced Client mặc định, `VersionedRecordExtension` thường được đăng ký sẵn để tự so sánh và tăng version trong write phù hợp. Nếu dự án dùng `DynamoDbEnhancedClient.builder().extensions(...)` để **tự đăng ký extension**, phải kiểm tra danh sách extension đang hoạt động và thêm `VersionedRecordExtension` khi cần; đừng giả định extension mặc định vẫn được giữ nếu đã thay danh sách bằng cấu hình tùy chỉnh.

### 5.3. Read–modify–write với kiểm tra version tự động

~~~java
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;
import software.amazon.awssdk.enhanced.dynamodb.model.GetItemEnhancedRequest;

@Repository
public class ReservationVersionedRepository {
    private final DynamoDbTable<ReservationItem> table;

    public ReservationVersionedRepository(DynamoDbEnhancedClient client) {
        this.table = client.table(
                "reservation_record",
                TableSchema.fromBean(ReservationItem.class));
    }

    public ReservationItem loadStrong(
            String tenantId, String sortKey) {
        return table.getItem(GetItemEnhancedRequest.builder()
                .key(Key.builder()
                        .partitionValue(tenantId)
                        .sortValue(sortKey)
                        .build())
                .consistentRead(true)
                .build());
    }

    public ReservationItem updateStateOptimistically(
            ReservationItem previouslyLoaded, String nextState) {
        previouslyLoaded.setState(nextState);
        return table.updateItem(previouslyLoaded);
    }
}
~~~

Ở ví dụ này, `previouslyLoaded` là **item đã được đọc đầy đủ** từ bảng, có `version` hiện tại. Enhanced Client áp dụng cơ chế version khi gọi `updateItem(...)`; nếu một write khác đã thay đổi version, DynamoDB trả `ConditionalCheckFailedException`. Đoạn code ở mục 4.3 là phương án **tường minh** khi cần kết hợp kiểm tra version và quy tắc chuyển trạng thái trong một expression.

Nếu dùng `table.updateItem(...)` với entity thiếu nhiều field, hành vi ánh xạ null có thể thay đổi hoặc xóa các thuộc tính không mong muốn tùy cấu hình/update semantics. Đối với partial update, chọn API/ignore-null mode thích hợp hoặc dùng `UpdateItemRequest` có expression rõ ràng. Không tạo một object chỉ chứa key + version + state rồi mặc nhiên coi việc update an toàn cho mọi field.

### 5.4. Khi nào version không đủ?

- **Điều kiện nghiệp vụ:** version vẫn mới nhưng nghiệp vụ không cho chuyển `CANCELLED → CONFIRMED`. Cần kiểm tra `state` hoặc thực hiện kiểm tra nghiệp vụ trước write với điều kiện atomic.
- **Dữ liệu thiếu version:** một item cũ không có attribute `version` có thể không tuân cùng hợp đồng optimistic locking. Cần chiến lược migration/backfill và condition tạo mới rõ ràng.
- **Ứng dụng khác bỏ qua version:** nếu một worker khác gọi raw `PutItem` mà không cập nhật `version`/condition, nó có thể ghi đè dữ liệu và phá vỡ giả định khóa lạc quan. Tất cả writer phải cùng tuân thủ quy tắc.
- **Nhiều item cùng thay đổi:** một version trên một item không bảo đảm invariant xuyên hai item; khi cần atomic đa item phải dùng transaction hoặc thiết kế lại invariant.
- **Xung đột cao:** nhiều request cùng cập nhật một item liên tục có thể gây tỷ lệ thất bại lớn, retry nhiều. Cân nhắc hàng đợi/serialization ở tầng nghiệp vụ hoặc thiết kế lại key.

**Phân biệt:** optimistic locking là kiểm tra *có ai sửa từ lúc tôi đọc không?*; conditional business write là kiểm tra *trạng thái hiện tại có cho phép hành động này không?*. Cả hai có thể được áp dụng cùng lúc.

## 6. Đọc nhất quán mạnh và nhất quán cuối cùng

### 6.1. Bảng lựa chọn

DynamoDB mặc định thường dùng **eventually consistent read** cho các thao tác đọc thông thường. Có thể yêu cầu **strongly consistent read** trên **base table** và **Local Secondary Index (LSI)** khi API hỗ trợ. **Global Secondary Index (GSI)** chỉ hỗ trợ eventually consistent read.

| Nguồn dữ liệu | Eventually consistent | Strongly consistent | Điều đáng lưu ý |
| --- | --- | --- | --- |
| Base table | Có; mặc định ở nhiều API read | Có, chọn `ConsistentRead=true` | Phù hợp khi cần thấy write đã thành công trong cùng Region |
| LSI | Có | Có | LSI dùng cùng partition key với bảng và phải tạo khi tạo bảng |
| GSI | **Có** | **Không** | GSI được cập nhật bất đồng bộ; có thể trễ so với bảng |
| DynamoDB Streams | Dữ liệu thay đổi xuất hiện bất đồng bộ | Không phải API strong-read bảng | Dùng cho event/CDC; không dùng thay GetItem cần dữ liệu mới nhất |
| Global tables nhiều Region | Tùy cơ chế sao chép/chế độ nhất quán | Phụ thuộc chế độ global table | Không suy từ strong read tại một Region ra việc đã thấy write tại Region khác |

**Strong consistency** cho một lần đọc bảng đảm bảo quan sát write đã hoàn tất trước đó theo ngữ nghĩa hỗ trợ của DynamoDB trong Region; không bảo đảm dữ liệu không thể thay đổi ngay sau khi đọc. **Eventual consistency** có thể trả bản dữ liệu cũ trong một khoảng thời gian ngắn sau write, nhưng thường tiết kiệm read capacity.

### 6.2. Đọc qua AWS SDK v2

Đọc item mạnh trên bảng:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.GetItemEnhancedRequest;

ReservationItem latest = table.getItem(
        GetItemEnhancedRequest.builder()
                .key(Key.builder()
                        .partitionValue("tenant-a")
                        .sortValue(
                                "RES#2026-11-24T08:00:00.000Z#res-1001")
                        .build())
                .consistentRead(true)
                .build());
~~~

Trong ví dụ trên, `table` là `DynamoDbTable<ReservationItem>` đã cấu hình tại mục 5.3. Nếu item không tồn tại thì `latest` là `null`. Strong read giúp giảm khả năng làm việc trên trạng thái cũ sau một write đã hoàn tất; **version condition khi update vẫn cần thiết**.

Query trên bảng có thể yêu cầu strong read:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;

QueryEnhancedRequest tableQuery = QueryEnhancedRequest.builder()
        .queryConditional(QueryConditional.keyEqualTo(
                Key.builder().partitionValue("tenant-a").build()))
        .consistentRead(true)
        .limit(20)
        .build();

var pages = table.query(tableQuery);
~~~

Trường hợp truy vấn **GSI**, không được đặt `consistentRead(true)`:

~~~java
var indexPages = table.index("by-property").query(
        QueryEnhancedRequest.builder()
                .queryConditional(QueryConditional.keyEqualTo(
                        Key.builder()
                                .partitionValue("tenant-a#house-99")
                                .build()))
                .limit(20)
                .build());
// GSI Query chỉ eventually consistent.
~~~

Nếu caller cần phản hồi chính xác ngay khi tạo một reservation, có thể trả trực tiếp bản ghi đã ghi thành công từ write response hoặc đọc lại qua **base table** với strong consistency. Đừng dùng GSI để xác nhận ngay lập tức một điều kiện quan trọng như không còn chỗ trống.

### 6.3. Chi phí và tác động thực tế

DynamoDB đo năng lực đọc theo đơn vị dữ liệu; với item tương đương và điều kiện khác như nhau, **eventually consistent reads thường tiêu thụ khoảng một nửa read capacity của strongly consistent reads**. Mốc 4 KB thường được dùng trong cách tính capacity cho đọc tiêu chuẩn; chi phí chính xác phụ thuộc mode, kích thước item, kiểu API và số lượng request.

Ví dụ mang tính quy tắc: đọc một item 4 KB với strong consistency tiêu thụ mức read capacity tương đương 1 read capacity unit; eventually consistent read tiêu thụ khoảng 0,5 trong mô hình tính capacity tiêu chuẩn. Không lấy số này làm mức phí tiền mặt cố định, vì giá phụ thuộc Region, mode on-demand/provisioned và các yếu tố khác.

Conditional write có thể tốn thêm read capacity cho việc đánh giá điều kiện khi thất bại, và có chi phí ghi khi thành công. Theo dõi `ConsumedCapacity`, throttling, độ trễ và tỷ lệ `ConditionalCheckFailedException` thay vì chỉ đo số request thành công.

## 7. Tại sao strong read vẫn không thay transaction?

### 7.1. Cửa sổ race sau lần đọc

~~~text
T0: A GetItem(ConsistentRead=true) -> state=PENDING
T1: B GetItem(ConsistentRead=true) -> state=PENDING
T2: A UpdateItem không có condition -> CONFIRMED
T3: B UpdateItem không có condition -> CANCELLED
~~~

Cả hai lần đọc đều có thể nhất quán mạnh và vẫn gặp **lost update**, vì dữ liệu đã đổi giữa lần đọc và lần ghi. Đặt điều kiện trong `UpdateItem` để DynamoDB đánh giá trạng thái/phiên bản **đúng tại thời điểm thực hiện write**.

### 7.2. Những việc cần nhiều item atomically

Giả sử xác nhận reservation phải đồng thời:

1. Chuyển `reservation.state` từ PENDING sang CONFIRMED.
2. Giảm `propertyInventory.available` đi một.
3. Không được giảm số chỗ xuống âm hoặc xác nhận reservation đã hủy.

Nếu làm hai `UpdateItem` riêng, bước 1 có thể thành công rồi bước 2 thất bại, khiến dữ liệu lệch. Với invariant cần atomically all-or-nothing, cân nhắc **`TransactWriteItems`** với update condition của từng item. Một transaction DynamoDB có quy tắc, giới hạn số item/kích thước và chi phí riêng; nó không tự xuất hiện khi gọi nhiều method repository dưới `@Transactional` của JPA.

~~~mermaid
flowchart LR
    A["Confirm reservation"] --> B{"Có invariant trên nhiều item?"}
    B -->|"Không"| C["Conditional UpdateItem / version check"]
    B -->|"Có"| D["TransactWriteItems<br/>Update reservation + inventory"]
    C --> E["Thành công hoặc conflict"]
    D --> E
~~~

Nếu luồng liên quan S3, SQS hoặc dịch vụ ngoài DynamoDB, transaction DynamoDB **không** bao trùm các dịch vụ đó. Khi có nhiều hệ thống tham gia, dùng outbox, idempotency key, saga/compensation và cơ chế retry có ranh giới, thay vì giả định một transaction xuyên cloud.

### 7.3. Scan/Query nhiều trang không tạo snapshot

`ConsistentRead=true` trên `Scan` (khi được hỗ trợ) có thể bảo đảm đọc nhất quán mạnh theo từng item, nhưng **không tạo snapshot nhất quán cho toàn bộ cuộc Scan**. Một `Query` nhiều trang cũng có thể nhìn thấy dữ liệu thay đổi giữa các request. Khi cần ảnh chụp dữ liệu bất biến cho báo cáo, cân nhắc export/backup hay quy trình snapshot thích hợp thay vì mặc nhiên gộp kết quả phân trang thành transaction.

## 8. Ghi an toàn dưới retry và lỗi mạng

### 8.1. Phân biệt conflict với lỗi hạ tầng

| Lỗi / dấu hiệu | Ý nghĩa thường gặp | Cách xử lý |
| --- | --- | --- |
| `ConditionalCheckFailedException` | Condition business/version không còn đúng hoặc item đã tồn tại | Trả conflict, đọc lại và đánh giá nghiệp vụ; không retry nguyên request vô hạn |
| `TransactionCanceledException` | Một thao tác trong transaction làm cả transaction bị hủy | Kiểm tra cancellation reasons, phân biệt condition vs throughput |
| `ProvisionedThroughputExceededException`, throttling | Bảng/GSI/partition nóng hoặc vượt capacity | SDK retry có backoff/jitter và giới hạn; xem metric/capacity |
| `ResourceNotFoundException` | Bảng/index sai tên, account, endpoint hoặc Region | Kiểm tra IaC, cấu hình và `DescribeTable` |
| `AccessDeniedException` | IAM role thiếu action hoặc ARN | Kiểm tra policy cho table và index |
| Timeout hoặc `SdkClientException` | Không biết chắc write đã đến server/chưa | Đánh giá tính idempotent, query/đối soát theo key cố định trước retry |

Với request tạo mới: **client có thể không nhận được response dù server đã ghi thành công**. Giải pháp là idempotency key ổn định và kiểm tra item theo key. Nếu retry cùng key bị `ConditionalCheckFailedException`, cần kiểm tra xem đó chính là yêu cầu đã hoàn tất hay một nghiệp vụ khác chiếm key; không tự coi tất cả conflict là thành công.

### 8.2. Chỉ retry khi có chiến lược

- **Optimistic conflict:** đọc lại item mới nhất, xác minh trạng thái và mục tiêu của người dùng, rồi mới quyết định có thử lại với version mới hay không. Retry mù có thể biến "hủy" thành "xác nhận" ngoài ý muốn.
- **Throttling/lỗi tạm thời:** dùng exponential backoff với jitter, giới hạn số lần, thời gian, độ trễ và chống request storm.
- **Write không idempotent:** các operation dạng tăng bộ đếm hoặc tạo ID mới ở mỗi lần thử cần cơ chế tránh áp dụng trùng khi response trước không rõ thành công hay thất bại.
- **Transaction:** dùng client request token được API hỗ trợ để giúp idempotency trong phạm vi và thời hạn của DynamoDB; vẫn phải thiết kế request ID lâu dài nếu nghiệp vụ cần.
- **Deadlines:** không giữ HTTP request chờ vô hạn; ghi nhận trạng thái cần xử lý tiếp hoặc trả lỗi rõ ràng.

### 8.3. HTTP error mapping

Một API quản lý reservation có thể quy ước:

| Tình huống | Phản hồi gợi ý |
| --- | --- |
| Create-only với reservation ID đã tồn tại | `409 Conflict` hoặc kết quả idempotent sau xác minh |
| Update với version cũ | `409 Conflict` kèm hướng dẫn reload; có thể dùng `412 Precondition Failed` nếu dùng HTTP precondition/ETag đúng quy ước |
| Không tìm thấy item | `404 Not Found` |
| Không được phép truy cập tenant | `403 Forbidden` hoặc che sự tồn tại theo chính sách API |
| DynamoDB bị throttling tạm thời | `429`/`503` tùy contract, cùng retry policy phù hợp |

Đừng trả stack trace, tên ARN bí mật hay thông tin key tenant khác trong response. Log correlation ID, request ID, trạng thái lỗi và metric; che dữ liệu cá nhân, credentials và payload nhạy cảm.

## 9. IAM và giới hạn truy cập đa tenant

Ví dụ policy tối thiểu cho API cần tạo, cập nhật, đọc một item và query GSI:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query"
      ],
      "Resource": [
        "arn:aws:dynamodb:ap-southeast-1:123456789012:table/reservation_record",
        "arn:aws:dynamodb:ap-southeast-1:123456789012:table/reservation_record/index/by-property"
      ]
    }
  ]
}
~~~

Thay Region, account ID và tên bảng/index bằng tài nguyên thật; tách quyền theo chức năng/role thay vì cấp tất cả cho mọi workload. Nếu dùng `TransactWriteItems` hoặc thao tác khác, bổ sung quyền cần thiết theo API/tài nguyên thực tế và nguyên tắc least privilege.

Trong hệ thống multi-tenant:

- Lấy `tenantId` từ danh tính đã xác thực hoặc ngữ cảnh ủy quyền, **không tin** tenant ID bất kỳ người dùng gửi trong body.
- Tính `propertyKey` từ tenant đã xác minh và mã property hợp lệ, không để client chọn partition key của người khác.
- Nếu dùng IAM condition như `dynamodb:LeadingKeys`, kiểm tra mô hình khóa và role phù hợp; điều kiện IAM không tự thay thế mọi authorization ở tầng business.
- Tách role dev/staging/prod; không để credentials giả của DynamoDB Local đi vào production.
- Bảo vệ thông tin cá nhân trong item, log, event và backup; DynamoDB encryption at rest không thay thế kiểm soát truy cập.

## 10. Kiểm thử tích hợp điều kiện ghi và khóa lạc quan

Unit test với mock repository hữu ích cho service, nhưng **không chứng minh** condition expression, version extension hoặc consistency behavior chạy đúng với schema DynamoDB. Cần test với DynamoDB Local/LocalStack, bảng/index giống môi trường đích và cả `DynamoDbClient` lẫn `DynamoDbEnhancedClient` đã cấu hình đúng endpoint.

### 10.1. Kịch bản nên bao phủ

1. **Create-only:** tạo item với key mới thành công; tạo lại cùng key nhận `ConditionalCheckFailedException`; item cùng `tenantId` nhưng `sortKey` khác vẫn tạo được.
2. **Transition condition:** từ PENDING xác nhận thành công, từ CANCELLED không được phép xác nhận, thiếu item không được phép upsert.
3. **Optimistic locking:** hai bản đọc cùng version; cập nhật A thành công; cập nhật B bằng bản cũ thất bại và không ghi đè A.
4. **Read consistency:** đọc bằng strong read trên bảng sau một write thành công; không yêu cầu strong consistency trên GSI. Với GSI, test dùng polling có giới hạn hoặc kiểm tra eventual behavior, không assert xuất hiện tức thì.
5. **Không cập nhật thiếu dữ liệu:** khi dùng Enhanced Client `updateItem`, xác nhận các attribute không liên quan vẫn giữ giá trị.
6. **Idempotent retry:** request create bị gửi lại cùng key sau giả lập timeout không sinh thêm item; phân biệt conflict thật với retry cùng request ID.
7. **Multi-tenant:** các item của tenant khác không bị ảnh hưởng, API không chấp nhận tenant do người dùng tự chọn.
8. **Rollback transaction:** nếu một điều kiện trong `TransactWriteItems` không thỏa, không item nào trong transaction bị áp dụng dở.

### 10.2. Test JUnit 5 cho optimistic locking

Ví dụ sau giả định class `ReservationVersionedRepository` ở mục 5.3 và `ReservationConditionalWriter` ở mục 4.2 đã được đăng ký thành bean, DynamoDB Local đang chạy với bảng `reservation_record`.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;

@SpringBootTest
@ActiveProfiles("local")
class ReservationOptimisticLockIT {
    @Autowired ReservationConditionalWriter writer;
    @Autowired ReservationVersionedRepository repository;

    @Test
    void staleUpdateMustNotOverwriteNewerState() {
        String tenantId = "it-" + UUID.randomUUID();
        String reservationId = "res-1";
        String createdAt = "2026-11-24T08:00:00.000Z";
        String sortKey = "RES#" + createdAt + "#" + reservationId;

        writer.createOnly(
                tenantId, sortKey, reservationId,
                tenantId + "#house-99", createdAt);

        ReservationItem first = repository.loadStrong(tenantId, sortKey);
        ReservationItem stale = repository.loadStrong(tenantId, sortKey);

        assertEquals(first.getVersion(), stale.getVersion());

        // Enhanced Client tự thực hiện version condition trong update.
        repository.updateStateOptimistically(first, "CONFIRMED");

        assertThrows(
                ConditionalCheckFailedException.class,
                () -> repository.updateStateOptimistically(
                        stale, "CANCELLED"));

        assertEquals(
                "CONFIRMED",
                repository.loadStrong(tenantId, sortKey).getState());
    }
}
~~~

Đây là **mẫu test cần chạy**, không phải kết quả test đã được thực thi. `updateStateOptimistically(...)` minh họa khóa lạc quan theo version; một service production còn phải kiểm tra chuyển trạng thái hợp lệ bằng condition expression như mục 4.3 nếu nghiệp vụ không cho phép mọi giá trị `nextState`. Assertion trọng tâm là **request thứ hai thất bại do version cũ** và item còn đúng trạng thái do request đầu ghi.

Để CI có thể tự chạy, dùng Testcontainers khởi động DynamoDB Local/LocalStack, tự tạo bảng trong setup và truyền endpoint/credentials vào Spring context. Đặt test data riêng mỗi lần chạy, cleanup theo key và tránh phụ thuộc dữ liệu từ test khác.

### 10.3. Test thực nghiệm mức nhất quán

Có thể mô tả các kiểm chứng:

~~~text
Bước 1: PutItem vào base table, response thành công
Bước 2: GetItem với ConsistentRead=true vào base table -> thấy item mới
Bước 3: Query GSI by-property -> có thể thấy hoặc chưa thấy ngay
Bước 4: Poll GSI có deadline; xác nhận cuối cùng index phản ánh item
Bước 5: Thử yêu cầu ConsistentRead=true trên GSI -> lỗi/không được hỗ trợ
~~~

DynamoDB Local có thể không mô phỏng chính xác độ trễ replication hoặc hành vi phân tán của DynamoDB thật. Vì vậy test local phù hợp để xác nhận API, schema và exception; bài đo latency/consistency thực tế cần môi trường thử nghiệm AWS có quota và ngân sách kiểm soát.

## 11. Những ngộ nhận thường gặp

| Phát biểu | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “Ghi một item của DynamoDB là atomic nên không có lost update.” | Sai | Hai write atomic vẫn có thể ghi đè nhau nếu thiếu condition/version |
| “Strong read là đủ để tránh hai người cùng sửa.” | Sai | Dữ liệu có thể đổi sau read, trước write |
| “PutItem mặc định chỉ insert nếu chưa tồn tại.” | Sai | Put có thể thay thế item cùng primary key |
| “`attribute_not_exists(tenantId)` khóa cả tenant.” | Sai | Điều kiện được đánh giá trên **item đích** đã xác định bởi full primary key |
| “`@DynamoDbVersionAttribute` tự bảo vệ các writer raw không kiểm tra version.” | Sai | Writer khác phải cùng tuân thủ version/condition |
| “GSI có thể bật strong consistency nếu bật ở Query request.” | Sai | GSI chỉ hỗ trợ eventual consistency |
| “Consistent Scan là snapshot của cả bảng.” | Sai | Strong read theo item không tạo snapshot xuyên toàn Scan |
| “Cứ gặp ConditionalCheckFailedException là retry.” | Sai | Thường là xung đột nghiệp vụ hoặc optimistic conflict |
| “`@Transactional` của Spring JPA bao trùm DynamoDB + S3 + SQS.” | Sai | Cần thiết kế giao dịch/điều phối theo từng hệ thống |
| “Khi response write timeout, chắc chắn DB chưa ghi.” | Sai | Kết quả có thể không rõ; phải có cơ chế idempotency/đối soát |

## 12. Bài tập thực hành nâng cao

1. Viết endpoint `POST /reservations` dùng create-only và idempotency key ổn định. Gửi cùng request hai lần, phân biệt request lặp với xung đột ID từ khách hàng khác.
2. Viết endpoint `PATCH /reservations/{id}/state` chuyển PENDING → CONFIRMED chỉ khi version và trạng thái còn đúng; trả `409 Conflict` khi version stale và có contract cho client reload.
3. Chạy hai thread cùng cập nhật một item với bản đọc version giống nhau. So sánh kết quả khi dùng write không điều kiện, write có state condition và Enhanced Client optimistic locking.
4. Thử đọc bảng bằng eventual và strong consistency; Query cùng item qua GSI; ghi lại đảm bảo lý thuyết và quan sát thực tế, tránh suy đoán từ một lần chạy.
5. Thiết kế transaction xác nhận reservation và giảm inventory cho một property; thêm condition chống số chỗ âm, thử case một phần điều kiện thất bại và xác minh không có cập nhật dở.
6. Mô phỏng timeout sau create-only thành công, gửi lại cùng request ID; xác minh không sinh reservation thứ hai và trạng thái trả về theo contract idempotent.
7. So sánh mô hình kiểm tra phiên bản và consistency khi chuyển workload từ DynamoDB sang Azure Cosmos DB hoặc Google Cloud Firestore. Xác định interface nghiệp vụ nào có thể giữ, và những semantics phải triển khai riêng theo provider.

**Tiêu chí hoàn thành:** người học giải thích được vì sao atomic write, optimistic locking, conditional business write và strong read phục vụ các bảo đảm khác nhau; triển khai được một tình huống concurrency thật trên DynamoDB; kiểm chứng conflict bằng test tích hợp; và chọn hợp lý giữa đọc bảng, GSI và transaction.

## Tài liệu tham khảo

- [Amazon DynamoDB — Condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html): conditional Put, Update và Delete.
- [Amazon DynamoDB — Read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html): eventual/strong consistency trên bảng, index và global tables.
- [Amazon DynamoDB — Working with transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html): transaction API, đặc điểm và giới hạn.
- [Amazon DynamoDB — Error handling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Programming.Errors.html): condition failures, throttling và retry.
- [Amazon DynamoDB — Global tables consistency modes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html): sao chép nhiều Region và ngữ nghĩa nhất quán theo chế độ.
- [AWS SDK for Java 2.x — DynamoDB Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html): ánh xạ bean và thao tác Enhanced Client.
- [AWS SDK for Java 2.x — Use extensions](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/ddb-en-client-extensions.html): `VersionedRecordExtension`, `@DynamoDbVersionAttribute` và custom extensions.
- [Spring Cloud AWS — Reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): dependency, AWS identity và auto-configuration tương ứng với phiên bản.
