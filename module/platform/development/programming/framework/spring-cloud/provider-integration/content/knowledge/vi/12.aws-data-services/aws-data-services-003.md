# Đọc ghi dữ liệu, truy vấn chỉ mục và phân trang

## 1. Bối cảnh và mục tiêu

Trong chương **Dữ liệu AWS** của module **Spring Cloud Provider Integration**, ứng dụng Spring Boot cần truy cập dịch vụ dữ liệu managed của AWS một cách an toàn và có khả năng mở rộng. Với **Amazon DynamoDB**, thao tác đọc/ghi không chỉ gồm CRUD: người phát triển còn phải chọn đúng khóa, hiểu index, kiểm soát dung lượng mỗi lần đọc và xử lý phân trang.

Ví dụ xuyên suốt là dịch vụ đặt chỗ của một ứng dụng đa tenant:

- Bảng `reservation_record` chứa các lượt đặt chỗ.
- **Partition key** `tenantId` xác định tổ chức sở hữu bản ghi.
- **Sort key** `sortKey` có định dạng `RES#2026-11-24T08:30:00.000Z#res-1001`.
- **Global secondary index (GSI)** `by-property` giúp lấy các lượt đặt của một bất động sản theo thời gian: partition key `propertyKey` và sort key `createdAt`.
- Luồng chính: tạo lượt đặt, đọc một lượt đặt, sửa trạng thái, xóa, liệt kê theo tháng, liệt kê theo bất động sản và trả dữ liệu từng trang.

Sau bài học, bạn có thể:

1. Phân biệt `GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `Query` và `Scan` theo hành vi thực tế.
2. Ghi dữ liệu với **điều kiện** để tránh tạo trùng hoặc ghi đè ngoài ý muốn.
3. Truy vấn bảng và GSI theo partition key + điều kiện sort key, nhận biết eventual/strong consistency.
4. Phân trang có kiểm soát bằng `LastEvaluatedKey` và `ExclusiveStartKey`, không tải toàn bộ kết quả vào bộ nhớ.
5. Tổ chức repository Spring Boot qua **AWS SDK for Java v2 Enhanced Client** và hiểu khi nào dùng `DynamoDbTemplate` của **Spring Cloud AWS (AWSpring)**.
6. Kiểm thử với DynamoDB Local, cấu hình IAM/region/endpoint và đánh giá chi phí, quota, retry, cursor cho production.

> Bài này tập trung vào mô hình DynamoDB của AWS. Azure Cosmos DB và Google Cloud Firestore có cơ chế phân vùng, query/index, permission và continuation token riêng. Tầng nghiệp vụ nên có interface rõ ràng nếu cần tích hợp đa cloud, nhưng không giả định các SDK có cùng API hoặc guarantee.

## 2. Đọc và ghi trong DynamoDB khác SQL ở điểm nào?

### 2.1. Bảng quyết định thao tác

| Thao tác | Mục đích | Đầu vào quan trọng | Điều cần lưu ý |
| --- | --- | --- | --- |
| `GetItem` | Đọc **một** item | Toàn bộ primary key (PK, SK nếu có) | Không tìm trực tiếp theo thuộc tính thường |
| `PutItem` | Ghi toàn bộ item vào một key | Item có đầy đủ primary key | Có thể **thay thế item cùng key** nếu không có condition |
| `UpdateItem` | Thay đổi item/thuộc tính | Primary key, thay đổi, có thể kèm condition | Ngữ nghĩa null/update của Enhanced Client cần được kiểm tra |
| `DeleteItem` | Xóa item theo key | Toàn bộ primary key; condition nếu cần | Có thể xóa dữ liệu ngoài ý muốn nếu không kiểm soát quyền |
| `Query` | Đọc các item theo khóa bảng/index | Partition key bằng giá trị cụ thể; sort key tùy chọn | Có phân trang; thứ tự theo sort key trong một partition key |
| `Scan` | Duyệt dữ liệu của bảng/index | Có thể có filter và projection | Dễ tốn RCU; không dùng làm giải pháp mặc định cho màn hình lớn |
| `BatchGetItem`/`BatchWriteItem` | Thực hiện nhiều lượt đọc hoặc ghi/xóa | Nhiều key/item | Phải xử lý `UnprocessedKeys`/`UnprocessedItems`, không mặc nhiên atomic toàn bộ |
| `TransactWriteItems`/`TransactGetItems` | Nhóm thao tác có bảo đảm giao dịch | Danh sách thao tác thỏa giới hạn của DynamoDB | API/chi phí khác batch; không được thay bằng annotation JPA |

DynamoDB cho phép item có nhiều thuộc tính linh hoạt, nhưng **khóa chính và khóa của secondary index phải có tên và kiểu đúng** như bảng đã tạo. Với bảng có `tenantId` và `sortKey`, `GetItem` không thể chỉ nhận `reservationId` rồi tự tìm; ứng dụng phải biết toàn bộ key hoặc có một access pattern/index/lookup riêng.

### 2.2. Chọn thao tác theo access pattern

~~~mermaid
flowchart TD
    A["Ứng dụng cần dữ liệu"] --> B{"Biết toàn bộ PK + SK?"}
    B -->|"Có, đúng 1 item"| C["GetItem"]
    B -->|"Không, biết partition key"| D["Query bảng hoặc index"]
    B -->|"Không, chỉ biết thuộc tính thường"| E{"Có index phù hợp?"}
    E -->|"Có"| F["Query index"]
    E -->|"Chưa"| G["Thiết kế access pattern / index<br/>chỉ Scan khi có lý do rõ ràng"]
    D --> H["Kiểm soát phân trang"]
    F --> H
~~~

Cần phân biệt **lọc kết quả** và **định vị dữ liệu**. `KeyConditionExpression` chọn phạm vi trên khóa mà DynamoDB truy cập; `FilterExpression` loại bớt item **sau khi DynamoDB đã đọc chúng**. Vì thế, lọc `state = "CONFIRMED"` trên hàng triệu item bằng `Scan` có thể tốn nhiều read capacity dù response cuối cùng nhỏ.

## 3. Chuẩn bị bảng, index và thư viện

### 3.1. Mô hình dữ liệu minh họa

| Thuộc tính | Kiểu DynamoDB | Vai trò |
| --- | --- | --- |
| `tenantId` | String | Partition key của bảng |
| `sortKey` | String | Sort key của bảng: `RES#<UTC time>#<reservationId>` |
| `reservationId` | String | Mã nghiệp vụ |
| `propertyId` | String | Mã bất động sản |
| `propertyKey` | String | Partition key của GSI `by-property`: `tenantId#propertyId` |
| `createdAt` | String | Sort key của GSI, chuỗi UTC có định dạng thống nhất |
| `state` | String | `PENDING`, `CONFIRMED`, `CANCELLED` |
| `guestCount` | Number | Số khách |

Ví dụ:

~~~text
Primary key (bảng):          tenantId   + sortKey
GSI by-property:             propertyKey + createdAt

tenantId | sortKey                              | propertyKey      | createdAt                 | state
---------+--------------------------------------+------------------+---------------------------+----------
tenant-a | RES#2026-11-24T08:30:00.000Z#res-1   | tenant-a#house-1 | 2026-11-24T08:30:00.000Z  | PENDING
tenant-a | RES#2026-11-24T09:00:00.000Z#res-2   | tenant-a#house-2 | 2026-11-24T09:00:00.000Z  | CONFIRMED
tenant-b | RES#2026-11-24T08:30:00.000Z#res-1   | tenant-b#house-1 | 2026-11-24T08:30:00.000Z  | CONFIRMED
~~~

**Thiết kế có đánh đổi:** truy vấn “tất cả lượt đặt tháng 11 của tenant” dùng prefix của `sortKey` rất thuận tiện. Nhưng API “tìm theo reservationId mà không biết timestamp” không thể dùng `GetItem` với khóa này. Nếu đó là truy vấn chính, cân nhắc đổi sort key thành `RES#reservationId` và tạo GSI cho thời gian, hoặc duy trì một lookup item riêng. Không dùng `Scan` để bù cho access pattern chưa được thiết kế.

Thời gian lưu trong khóa String nên ở **UTC, cùng độ chính xác (millisecond), zero-padding đầy đủ**; nếu không, thứ tự chuỗi có thể khác thứ tự thời gian. Mã tạo khóa phải dùng quy tắc thống nhất, kiểm soát dấu phân cách để hai cặp ID không sinh cùng một chuỗi.

### 3.2. Maven với AWSpring hoặc SDK v2 thuần

Trong ứng dụng Spring Boot dùng Spring Cloud AWS, có thể khai báo starter (đặt version bằng BOM phù hợp với Spring Boot):

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-dynamodb</artifactId>
</dependency>
~~~

DynamoDB Enhanced Client có các dependency AWS SDK v2:

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

Khi dùng starter, kiểm tra dependency tree và BOM: không nhất thiết khai báo lại các artifact đã được starter kéo vào. **Không trộn bừa phiên bản AWSpring/Spring Boot/AWS SDK**; không mặc định có `DynamoDbTemplate` trong mọi phiên bản. Những ví dụ Java chính trong bài dùng Enhanced Client để thao tác index và ranh giới trang minh bạch.

### 3.3. Cấu hình danh tính, region và endpoint

Với AWSpring ở phiên bản hỗ trợ các property dưới đây:

~~~yaml
# application.yml - môi trường AWS
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        enabled: true
~~~

Ứng dụng production nên nhận credentials qua **IAM role/workload identity** và credential provider chain, không lưu access key/secret key cố định trong YAML hoặc mã nguồn.

Ví dụ profile local:

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

Với **AWS SDK v2 tự tạo client** (không dùng AWSpring auto-configuration), phải tự cấu hình region và `endpointOverride` tương ứng; property `spring.cloud.aws.dynamodb.endpoint` không tự tác động đến một bean client được tạo thủ công không đọc property đó.

Chạy DynamoDB Local:

~~~bash
docker run --rm --name dynamodb-local -p 8000:8000 amazon/dynamodb-local:latest
~~~

Trong terminal local, đặt AWS credentials **giả** (`AWS_ACCESS_KEY_ID=local` và `AWS_SECRET_ACCESS_KEY=local`) để AWS SDK/CLI có dữ liệu ký request. Chỉ dùng giá trị giả với endpoint local; khi triển khai AWS thật, dùng IAM role và endpoint mặc định.

### 3.4. Tạo bảng và GSI

Bash / AWS CLI với DynamoDB Local:

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

Tham số `--attribute-definitions` chỉ gồm những thuộc tính tham gia key của bảng/index, không liệt kê mọi trường dữ liệu. Index `ProjectionType=ALL` thuận tiện khi học, nhưng tăng storage/write cost; production có thể cân nhắc `KEYS_ONLY` hoặc `INCLUDE`.

Kiểm tra:

~~~bash
aws dynamodb describe-table \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record
~~~

Trên AWS thật, nên tạo bảng/index bằng **Infrastructure as Code**. Spring starter, `@DynamoDbBean` và `TableSchema.fromBean` **không tự tạo bảng**.

## 4. Định nghĩa entity và repository Spring Boot

### 4.1. Ánh xạ bằng `@DynamoDbBean`

~~~java
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbBean;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondaryPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondarySortKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSortKey;

@DynamoDbBean
public class ReservationItem {
    private String tenantId;
    private String sortKey;
    private String reservationId;
    private String propertyId;
    private String propertyKey;
    private String createdAt;
    private String state;
    private Integer guestCount;

    public ReservationItem() { }

    @DynamoDbPartitionKey
    public String getTenantId() { return tenantId; }
    public void setTenantId(String value) { this.tenantId = value; }

    @DynamoDbSortKey
    public String getSortKey() { return sortKey; }
    public void setSortKey(String value) { this.sortKey = value; }

    public String getReservationId() { return reservationId; }
    public void setReservationId(String value) { this.reservationId = value; }

    public String getPropertyId() { return propertyId; }
    public void setPropertyId(String value) { this.propertyId = value; }

    @DynamoDbSecondaryPartitionKey(indexNames = "by-property")
    public String getPropertyKey() { return propertyKey; }
    public void setPropertyKey(String value) { this.propertyKey = value; }

    @DynamoDbSecondarySortKey(indexNames = "by-property")
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String value) { this.createdAt = value; }

    public String getState() { return state; }
    public void setState(String value) { this.state = value; }

    public Integer getGuestCount() { return guestCount; }
    public void setGuestCount(Integer value) { this.guestCount = value; }
}
~~~

`@DynamoDbBean`, `@DynamoDbPartitionKey` và secondary key annotations thuộc AWS SDK v2 Enhanced Client, **không phải JPA**. Các annotation key đặt trên getter; class có constructor không tham số và public getter/setter. Mặc định tên attribute trùng tên JavaBean property, ví dụ `getCreatedAt()` ánh xạ thành `createdAt`. Nếu đổi tên bằng `@DynamoDbAttribute` thì schema bảng/index và code query phải dùng tên đã khai báo.

Service tạo giá trị `sortKey`, `propertyKey`, `createdAt`; annotation **không tự ghép khóa**. Ví dụ:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class ReservationFactory {
    private static final DateTimeFormatter UTC_MILLIS =
            DateTimeFormatter
                    .ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS'Z'")
                    .withZone(ZoneOffset.UTC);

    private ReservationFactory() { }

    public static ReservationItem create(
            String tenantId,
            String propertyId,
            String reservationId,
            Instant when,
            int guestCount) {
        String timestamp = UTC_MILLIS.format(when);

        ReservationItem item = new ReservationItem();
        item.setTenantId(tenantId);
        item.setPropertyId(propertyId);
        item.setReservationId(reservationId);
        item.setCreatedAt(timestamp);
        item.setSortKey("RES#" + timestamp + "#" + reservationId);
        item.setPropertyKey(tenantId + "#" + propertyId);
        item.setState("PENDING");
        item.setGuestCount(guestCount);
        return item;
    }
}
~~~

Trong production cần validate ID, chống chuỗi phân cách gây nhập nhằng và không cho người dùng tự ý chọn `tenantId` vượt khỏi phạm vi được cấp phép. Nếu có nguy cơ nhiều lượt đặt cùng timestamp, phần `reservationId` phải đủ duy nhất.

### 4.2. Kết nối Enhanced Client

Nếu starter đã tự cấu hình `DynamoDbEnhancedClient`, repository chỉ cần inject. Với SDK v2 thuần, các bean có thể như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Configuration
class DynamoDbClientConfig {
    @Bean
    DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }

    @Bean
    DynamoDbEnhancedClient dynamoDbEnhancedClient(DynamoDbClient client) {
        return DynamoDbEnhancedClient.builder()
                .dynamoDbClient(client)
                .build();
    }
}
~~~

Đây là cấu hình **AWS thật** dùng default credentials provider chain. Khi chạy local bằng SDK tự cấu hình, bổ sung `endpointOverride(URI.create("http://localhost:8000"))` và credentials local. **Không định nghĩa trùng bean client** khi AWSpring đã cung cấp cấu hình phù hợp.

Repository lấy tên bảng và schema:

~~~java
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;

@Repository
public class ReservationRepository {
    private final DynamoDbTable<ReservationItem> table;

    public ReservationRepository(DynamoDbEnhancedClient client) {
        this.table = client.table(
                "reservation_record",
                TableSchema.fromBean(ReservationItem.class));
    }

    // Các phương thức đọc/ghi và phân trang ở phần tiếp theo
}
~~~

Các ví dụ sau dùng biến `table` từ repository này, trừ khi nói khác.

## 5. Ghi, đọc, cập nhật và xóa

### 5.1. Ghi một item: `putItem` và điều kiện chống trùng

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Expression;
import software.amazon.awssdk.enhanced.dynamodb.model.PutItemEnhancedRequest;

public void createNew(ReservationItem item) {
    var condition = Expression.builder()
            .expression("attribute_not_exists(tenantId)")
            .build();

    table.putItem(PutItemEnhancedRequest
            .builder(ReservationItem.class)
            .item(item)
            .conditionExpression(condition)
            .build());
}
~~~

Không có condition, `table.putItem(item)` có thể **thay thế toàn bộ item** nếu một item cùng primary key đã tồn tại. Điều kiện `attribute_not_exists(tenantId)` được DynamoDB đánh giá atomically trên **item đích**; dù có hàng nghìn item khác cùng `tenantId` nhưng khác `sortKey`, thao tác tạo item mới vẫn hợp lệ. Nếu item cùng cặp (`tenantId`, `sortKey`) đã có, SDK trả `ConditionalCheckFailedException`: đây thường là xung đột nghiệp vụ, không phải lỗi mất mạng để retry vô hạn.

Để chống ghi trùng từ sự kiện hoặc request gửi lại, nên có **idempotency key** và quy tắc key ổn định. Tạo timestamp mới cho mỗi lần retry có thể vô tình tạo item khác dù là cùng hành động nghiệp vụ.

### 5.2. Đọc một item bằng `getItem`

~~~java
import java.util.Optional;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.GetItemEnhancedRequest;

public Optional<ReservationItem> findOne(
        String tenantId, String sortKey, boolean strongRead) {
    Key key = Key.builder()
            .partitionValue(tenantId)
            .sortValue(sortKey)
            .build();

    GetItemEnhancedRequest request = GetItemEnhancedRequest
            .builder()
            .key(key)
            .consistentRead(strongRead)
            .build();

    return Optional.ofNullable(table.getItem(request));
}
~~~

Nếu key không tồn tại, kết quả là `null`; `Optional` ở repository giúp service xử lý rõ trường hợp “không tìm thấy”. `consistentRead(true)` có thể được dùng trên **bảng** khi cần đọc dữ liệu mới ghi với strong consistency, đổi lại chi phí đọc/độ trễ có thể khác. Không áp dụng strong consistency cho GSI.

**Cảnh báo:** `sortKey` là `RES#timestamp#reservationId`, nên `reservationId` đơn lẻ **không đủ** để gọi `getItem`. Đừng lắp một timestamp mới rồi giả định tìm được item cũ.

### 5.3. Cập nhật một item

Enhanced Client hỗ trợ:

~~~java
// Chạy khi đã đọc đủ dữ liệu hiện có của item:
ReservationItem item = table.getItem(
        Key.builder()
                .partitionValue(tenantId)
                .sortValue(sortKey)
                .build());

if (item == null) {
    throw new IllegalArgumentException("Không tìm thấy reservation");
}

item.setState("CONFIRMED");
table.updateItem(item);
~~~

**Không dùng ví dụ trên như cách cập nhật đồng thời an toàn tuyệt đối.** Hai request cùng đọc rồi sửa có thể ghi đè thay đổi của nhau. Ngoài ra, `updateItem` và các cấu hình xử lý null có thể cập nhật/xóa các thuộc tính không được cung cấp trong bean; không xây một bean “chỉ có key + state” rồi gọi `updateItem` khi chưa biết semantics của phiên bản SDK.

Với hệ thống thực tế, có thể dùng:

- Conditional update, ví dụ chỉ đổi `PENDING → CONFIRMED` khi trạng thái hiện tại vẫn `PENDING`.
- Optimistic locking bằng thuộc tính version và `@DynamoDbVersionAttribute` của Enhanced Client, nếu entity và extension được cấu hình phù hợp.
- `UpdateItemEnhancedRequest` với cấu hình ignore-null tương thích phiên bản SDK khi chủ động cập nhật một phần.
- Transaction API khi nhiều item phải đổi trạng thái atomically.

Khi thay đổi `propertyKey` hoặc `createdAt`, cần nhớ GSI index cũng sẽ được cập nhật và có thể xuất hiện độ trễ khi đọc lại qua index.

### 5.4. Xóa item

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Key;

public void deleteOne(String tenantId, String sortKey) {
    table.deleteItem(Key.builder()
            .partitionValue(tenantId)
            .sortValue(sortKey)
            .build());
}
~~~

Xóa theo khóa thường không báo lỗi chỉ vì item đã không tồn tại. Nếu bắt buộc chỉ xóa khi state/version thỏa điều kiện, dùng conditional delete. Với nghiệp vụ cần truy vết, cân nhắc **soft delete** (`state = CANCELLED`) hoặc lưu audit event thay vì xóa vật lý.

### 5.5. Batch và transaction: các giới hạn hay bị hiểu nhầm

- `BatchGetItem` có thể đọc tối đa **100 item** mỗi request; DynamoDB có thể trả `UnprocessedKeys` khi bị giới hạn. Cần retry có backoff cho các key chưa xử lý.
- `BatchWriteItem` nhận tối đa **25 yêu cầu Put/Delete** trong một batch, không hỗ trợ Update hoặc condition trên từng thao tác như một transaction. Kiểm tra và retry `UnprocessedItems`.
- Batch không bảo đảm tất cả item cùng thành công hay cùng rollback. Với thay đổi có ràng buộc all-or-nothing, xem `TransactWriteItems`/`TransactGetItems` cùng quota và chi phí tương ứng.
- Với Enhanced Client, có API batch/transaction cấp cao, nhưng **không nên suy ra `@Transactional` của Spring Data JPA tự biến DynamoDB writes thành transaction**.

## 6. Truy vấn bảng bằng partition key và sort key

Đối với bảng `reservation_record`, lấy reservation của tenant trong tháng bằng prefix của sort key:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;

QueryEnhancedRequest request = QueryEnhancedRequest.builder()
        .queryConditional(QueryConditional.sortBeginsWith(
                Key.builder()
                        .partitionValue("tenant-a")
                        .sortValue("RES#2026-11")
                        .build()))
        .scanIndexForward(false)
        .limit(25)
        .build();

for (var page : table.query(request)) {
    for (ReservationItem item : page.items()) {
        System.out.println(item.getReservationId());
    }
}
~~~

Giải thích:

1. `QueryConditional.sortBeginsWith` thực hiện điều kiện trên partition key **và** sort key. DynamoDB không cho dùng `begins_with` trên partition key; partition key phải so sánh bằng giá trị cụ thể.
2. `scanIndexForward(false)` đảo chiều sort key (mới nhất lên trước khi timestamp key được chuẩn hóa); mặc định là `true`, tức tăng dần.
3. `limit(25)` giới hạn số item **được DynamoDB đánh giá trong mỗi lần gọi/trang**, không bảo đảm vòng lặp trên mọi page chỉ in 25 item. Nếu muốn 25 item toàn response, cần kiểm soát số trang và số item ở application.
4. `Query` có ranh giới **1 MB dữ liệu được xử lý mỗi request** (trước filter), nên ngay cả khi limit lớn cũng có thể có thêm trang.
5. Nếu không có item phù hợp, trang có thể rỗng. Nếu có filter, một trang rỗng **vẫn có thể có `LastEvaluatedKey`** báo còn dữ liệu để tìm tiếp.
6. Truy vấn sort key String theo thứ tự UTF-8, không tự diễn giải múi giờ. Mọi timestamp nằm trong key phải theo một định dạng cố định để thứ tự đúng.

### 6.1. `Query` với điều kiện khoảng

Khi đã biết tenant và hai mốc sort key, có thể dùng:

~~~java
QueryConditional range = QueryConditional.sortBetween(
        Key.builder()
                .partitionValue("tenant-a")
                .sortValue("RES#2026-11-01")
                .build(),
        Key.builder()
                .partitionValue("tenant-a")
                .sortValue("RES#2026-11-30T23:59:59.999Z#~")
                .build());
~~~

`BETWEEN` bao gồm **cả hai đầu**. Ví dụ trên minh họa điều kiện khoảng khi định dạng sort key đã được quy ước thống nhất; trong production hãy định nghĩa biên khoảng dựa trên format thực tế và test các trường hợp ranh giới/ID. Nếu muốn xem mọi reservation tháng 11, `begins_with(sortKey, "RES#2026-11")` thường dễ hiểu hơn, tránh các giả định về ký tự lớn nhất ở cuối key.

### 6.2. Vì sao `FilterExpression` không thay index?

Giả sử muốn “chỉ lấy reservation `CONFIRMED` của tenant” nhưng `state` không nằm trong khóa. Có thể dùng filter expression, song DynamoDB vẫn cần đọc các item phù hợp `KeyConditionExpression` trước khi loại bỏ item không có `state = CONFIRMED`. **Read capacity tính trên dữ liệu được đọc**, không tính riêng số item cuối cùng được gửi về.

Nếu truy vấn theo state là luồng tải lớn, cân nhắc thiết kế thêm GSI `tenantStateKey + createdAt` hoặc điều chỉnh access pattern. Càng nhiều GSI thì mỗi ghi có thể phát sinh thêm công việc index, làm tăng dung lượng và chi phí write.

### 6.3. `ProjectionExpression` và giới hạn đọc

Projection chỉ yêu cầu trả về một tập thuộc tính. Đây là cách giảm payload truyền qua mạng và giảm chi phí xử lý client; với `Query` trên bảng hoặc LSI, projection **không tự làm giảm lượng read capacity tính theo kích thước item được đọc**. Với GSI, dữ liệu có thể query chỉ gồm các thuộc tính được project lên index; không thể tự yêu cầu các thuộc tính mà index không chứa như trường hợp đọc bảng gốc. Chọn projection khi thiết kế index phù hợp.

## 7. Truy vấn Global Secondary Index (GSI)

GSI `by-property` có khóa:

~~~text
IndexName = by-property
PK        = propertyKey  ("tenant-a#house-99")
SK        = createdAt    ("2026-11-24T08:30:00.000Z")
~~~

Ví dụ truy vấn các reservation cho một bất động sản trong tháng:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbIndex;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;

DynamoDbIndex<ReservationItem> index = table.index("by-property");

QueryEnhancedRequest request = QueryEnhancedRequest.builder()
        .queryConditional(QueryConditional.sortBeginsWith(
                Key.builder()
                        .partitionValue("tenant-a#house-99")
                        .sortValue("2026-11")
                        .build()))
        .limit(20)
        .build();

for (var page : index.query(request)) {
    for (ReservationItem item : page.items()) {
        System.out.println(item.getReservationId());
    }
}
~~~

Khi query `table`, điều kiện dùng `tenantId + sortKey`; khi query `index`, điều kiện dùng **`propertyKey + createdAt`**. Index phải được định nghĩa trên bảng thực tế và ánh xạ trong entity. `table.index("by-property")` trỏ tới đúng index, không biến một thuộc tính thường thành index mới.

Các điểm cần nhớ:

- GSI có thể có partition key khác bảng; LSI phải dùng cùng partition key với bảng và phải tạo khi tạo bảng.
- GSI được duy trì **bất đồng bộ**, chỉ hỗ trợ **eventually consistent reads**; không đặt `consistentRead(true)` cho query GSI.
- Item có thể chưa xuất hiện ở GSI ngay sau khi `PutItem` thành công trên bảng. Nếu thuộc tính key của GSI vắng mặt, item không được index như mong đợi (sparse index).
- GSI có write/read capacity và storage riêng khi tính chi phí; nếu index bị throttling có thể ảnh hưởng đến ghi bảng nguồn.
- GSI không đảm bảo unique theo khóa index. DynamoDB đảm bảo unique theo khóa chính của **bảng gốc**.

**Khi cần luôn nhìn thấy dữ liệu vừa tạo:** nếu nghiệp vụ đòi read-after-write chặt chẽ, ưu tiên `GetItem`/`Query` trên bảng với strongly consistent read khi được hỗ trợ hoặc thiết kế quy trình đồng bộ khác. Không xây bảo đảm nhất quán mạnh dựa vào GSI eventual.

## 8. Phân trang đúng với `LastEvaluatedKey` và `ExclusiveStartKey`

### 8.1. Cơ chế phân trang của DynamoDB

Một `Query` có thể trả về một phần kết quả với `LastEvaluatedKey`:

~~~mermaid
sequenceDiagram
    participant UI as Client
    participant API as Spring Boot API
    participant DB as DynamoDB
    UI->>API: GET /reservations?month=2026-11&pageSize=20
    API->>DB: Query(KeyCondition, Limit=20)
    DB-->>API: Items + LastEvaluatedKey
    API-->>UI: Items + nextCursor
    UI->>API: GET /reservations?month=2026-11&cursor=...
    API->>DB: Query(cùng điều kiện, ExclusiveStartKey)
    DB-->>API: Items + LastEvaluatedKey hoặc null
    API-->>UI: Items + nextCursor hoặc null
~~~

Các khái niệm:

- `Limit`: số item tối đa được DynamoDB **đánh giá** ở một request; khi có filter, số item **trả về** có thể nhỏ hơn limit, thậm chí bằng 0.
- **1 MB cap:** DynamoDB có thể ngắt trang khi đạt ngưỡng kích thước dữ liệu đã xử lý, dù số lượng item chưa đạt limit.
- `LastEvaluatedKey`: khóa đánh dấu vị trí dừng của lần đọc. Không có key này (hoặc key rỗng) nghĩa là đã đến cuối cho access pattern hiện tại.
- `ExclusiveStartKey`: đặt bằng `LastEvaluatedKey` của response trước để đọc tiếp; vị trí bắt đầu là **sau** item đó.
- Khóa phân trang của GSI có thể chứa cả các thuộc tính khóa bảng gốc và khóa index. Không tự suy ra rằng chỉ cần `propertyKey`/`createdAt` là đủ; hãy giữ **nguyên vẹn map khóa** do SDK trả về.

DynamoDB không cung cấp pagination kiểu SQL `OFFSET 100000` hiệu quả. Không nên tải 100.000 item để bỏ 99.900 item chỉ nhằm đến “trang 1000”. Dùng **cursor/continuation token** và thống nhất thứ tự truy vấn.

### 8.2. Repository trả đúng **một trang**

Có thể định nghĩa một kết quả phân trang ở tầng repository:

~~~java
import java.util.List;
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

public record ReservationPage(
        List<ReservationItem> items,
        Map<String, AttributeValue> nextKey) {
}
~~~

Trong `ReservationRepository`, thêm phương thức truy vấn một trang theo tháng:

~~~java
import java.time.YearMonth;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.Page;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

public ReservationPage monthPage(
        String tenantId,
        String yyyyMM,
        int pageSize,
        Map<String, AttributeValue> startKey) {

    // Parse giúp từ chối chuỗi tháng không hợp lệ.
    YearMonth month = YearMonth.parse(yyyyMM);
    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("pageSize phải nằm trong 1..100");
    }

    QueryEnhancedRequest.Builder request = QueryEnhancedRequest.builder()
            .queryConditional(QueryConditional.sortBeginsWith(
                    Key.builder()
                            .partitionValue(tenantId)
                            .sortValue("RES#" + month)
                            .build()))
            .scanIndexForward(false)
            .limit(pageSize);

    if (startKey != null && !startKey.isEmpty()) {
        request.exclusiveStartKey(startKey);
    }

    Iterator<Page<ReservationItem>> iterator =
            table.query(request.build()).iterator();

    if (!iterator.hasNext()) {
        return new ReservationPage(List.of(), null);
    }

    Page<ReservationItem> page = iterator.next();
    return new ReservationPage(
            List.copyOf(page.items()),
            page.lastEvaluatedKey());
}
~~~

Giải thích vì sao mã này dùng **`iterator().next()` một lần**: Enhanced Client cung cấp đối tượng có thể duyệt nhiều page. Nếu gọi `for (var page : ...)` hoặc dùng convenience `items()` và duyệt hết, client sẽ tiếp tục gọi DynamoDB cho đến khi hết dữ liệu, làm mất ý nghĩa giới hạn một trang của API.

Vì `Limit` là số item được đánh giá, một request có filter có thể trả về ít hơn `pageSize` và vẫn có `nextKey`. API không nên tự tuyên bố “hết dữ liệu” chỉ vì `items.size() < pageSize`.

### 8.3. Phân trang GSI: giữ đúng ngữ cảnh

Một ví dụ phương thức dùng GSI `by-property`:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import software.amazon.awssdk.enhanced.dynamodb.model.Page;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

public ReservationPage propertyPage(
        String tenantId,
        String propertyId,
        int pageSize,
        Map<String, AttributeValue> startKey) {

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("pageSize phải nằm trong 1..100");
    }

    QueryEnhancedRequest.Builder request = QueryEnhancedRequest.builder()
            .queryConditional(QueryConditional.keyEqualTo(
                    Key.builder()
                            .partitionValue(tenantId + "#" + propertyId)
                            .build()))
            .scanIndexForward(false)
            .limit(pageSize);

    if (startKey != null && !startKey.isEmpty()) {
        request.exclusiveStartKey(startKey);
    }

    Iterator<Page<ReservationItem>> iterator =
            table.index("by-property")
                    .query(request.build())
                    .iterator();

    if (!iterator.hasNext()) {
        return new ReservationPage(List.of(), null);
    }

    Page<ReservationItem> page = iterator.next();
    return new ReservationPage(
            List.copyOf(page.items()),
            page.lastEvaluatedKey());
}
~~~

`startKey` phải được phát ra từ **truy vấn cùng index, partition key, chiều sắp xếp và điều kiện lọc tương ứng**. Không lấy `LastEvaluatedKey` của truy vấn bảng rồi dùng cho index, hoặc trộn cursor của tenant/property khác.

### 8.4. Cursor công khai cần có ranh giới bảo mật

`Map<String, AttributeValue>` là kiểu dữ liệu **nội bộ repository**; không nên trả nguyên object AWS SDK qua public REST API rồi tin dữ liệu client gửi lại.

API production nên dùng token mờ `nextCursor`:

1. Khi response có `LastEvaluatedKey`, tuần tự hóa **đúng các kiểu AttributeValue của key** (String/Number/Binary theo schema) cùng thông tin truy vấn: loại index, tenant, bộ lọc, thứ tự, page size/phiên bản và thời hạn.
2. Ký token bằng **HMAC** hoặc bảo vệ bằng cơ chế authenticated encryption. Base64 URL-safe chỉ là **mã hóa biểu diễn**, không bảo vệ chống chỉnh sửa hay giấu thông tin.
3. Khi nhận cursor, kiểm tra chữ ký, thời hạn, phiên bản, tài khoản/tenant đã xác thực, index và các tham số truy vấn. Từ chối token không khớp; không nhận tùy ý tên table/index hoặc tenant từ token.
4. Giải mã lại thành `Map<String, AttributeValue>` để truyền vào `exclusiveStartKey`; nếu là cursor từ nguồn GSI, giữ đầy đủ các key mà DynamoDB trả về.
5. Nếu cần không tiết lộ khóa hoặc thông tin định danh, dùng authenticated encryption hoặc lưu trạng thái token ở server. Hạn chế độ dài token và kích thước request để chống lạm dụng.

**Ví dụ contract HTTP:**

~~~json
{
  "items": [
    {
      "reservationId": "res-1001",
      "propertyId": "house-99",
      "state": "PENDING",
      "createdAt": "2026-11-24T08:30:00.000Z"
    }
  ],
  "nextCursor": "opaque-signed-token-generated-by-server"
}
~~~

Token trong mẫu chỉ minh họa contract, **không phải token thực**. Không dùng JSON/Base64 “tự chế” cho sản phẩm nếu chưa có cơ chế xác thực nội dung. Dùng SDK serialization/type-safe codec, test token có Number/Binary nếu schema hỗ trợ. Với ví dụ bài học này, tất cả key là String nhưng cách serialize `AttributeValue` thành JSON vẫn cần quản lý rõ ràng.

### 8.5. Những giới hạn của phân trang theo cursor

- Query nhiều lần **không phải ảnh chụp snapshot nhất quán** của toàn bộ bảng. Trong lúc client đi từ trang 1 sang trang 2, dữ liệu có thể được thêm, xóa hoặc đổi sort key/index; ứng dụng phải chấp nhận hoặc thiết kế cơ chế snapshot riêng.
- Cursor có thể không ổn định nếu truy vấn thay đổi index, lọc, chiều sort hoặc cấu trúc key giữa hai lần request.
- `LastEvaluatedKey` xuất hiện nghĩa là **có thể** còn dữ liệu cần đọc. Một request tiếp theo có thể trả trang rỗng, nhất là khi có filter hoặc dữ liệu thay đổi.
- Không dựa trên `items.size()` để suy ra còn/hết trang; kiểm tra `nextKey`.
- Nếu yêu cầu một trang **đủ N item sau filter**, cần lặp có giới hạn qua một số DynamoDB pages cho đến khi đủ N hoặc hết dữ liệu; phải đặt ngân sách read/latency và duy trì đúng cursor mới nhất, tránh vòng lặp không giới hạn.

## 9. Quyền IAM, lỗi thực tế và giới hạn chi phí

### 9.1. IAM cho thao tác đọc/ghi và index

Ví dụ policy giới hạn vào bảng/index đã nêu; thay account ID và region theo môi trường:

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
        "dynamodb:DeleteItem",
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

Không cấp `Scan`/`BatchWriteItem`/transaction actions nếu service chưa cần. Nếu hệ thống multi-tenant, còn cần authorization ở service: lọc `tenantId` theo danh tính người dùng và kiểm tra quyền thao tác trên property/reservation. IAM của workload đơn lẻ không tự động giới hạn người dùng cuối theo tenant.

### 9.2. Xử lý lỗi

| Lỗi/triệu chứng | Cách hiểu | Cách xử lý |
| --- | --- | --- |
| `ResourceNotFoundException` | Bảng/index không tồn tại ở account, region hoặc endpoint hiện tại | `describe-table` và kiểm tra IaC/cấu hình |
| `ValidationException` | Khóa thiếu/sai kiểu, key expression không phù hợp, cursor không hợp lệ | Đối chiếu schema PK/SK/index, định dạng key và request |
| `ConditionalCheckFailedException` | Tạo/cập nhật/xóa có condition nhưng điều kiện không còn đúng | Trả lỗi xung đột nghiệp vụ, không retry mù |
| `AccessDeniedException` | IAM role thiếu quyền trên table/index | Kiểm tra action/ARN của resource thật |
| `ProvisionedThroughputExceededException` / throttling | Đọc/ghi quá khả năng hoặc có hot key/index | Backoff với jitter, đo consumed capacity, điều chỉnh key/capacity |
| `SdkClientException` hoặc timeout | DNS, network, credentials, endpoint hoặc kết nối bị gián đoạn | Kiểm tra cấu hình, log SDK an toàn, retry idempotent |
| Query trả trống dù bảng có dữ liệu | Query nhầm index/key/tenant, sparse GSI, eventual consistency | Xem access pattern, schema, dữ liệu key của item |
| Trang chỉ có vài item dù limit lớn | Filter, 1 MB cap hoặc còn `LastEvaluatedKey` | Tiếp tục phân trang theo token, kiểm soát ngân sách |
| Ghi thành công nhưng GSI chưa thấy item | GSI chỉ eventually consistent | Thiết kế luồng nghiệp vụ chịu được độ trễ |

### 9.3. Tối ưu truy vấn và chi phí

- Query theo key/index phù hợp thay vì Scan diện rộng.
- Đo `ConsumedCapacity` (request có hỗ trợ `returnConsumedCapacity` ở mức SDK phù hợp), số request, item size, read/write latency và throttling.
- Projection có thể giảm dữ liệu truyền nhưng **không bảo đảm giảm RCU** khi chỉ giới hạn thuộc tính trả về của một query trên bảng.
- GSI có chi phí lưu trữ/write và có thể gây nghẽn ngược về bảng nếu key/index quá nóng; cân nhắc sparse index và projection.
- DynamoDB giới hạn kích thước item; tài liệu/ảnh lớn thường lưu S3, bảng chỉ giữ khóa và metadata.
- SDK có retry mặc định cho một số lỗi; điều chỉnh retry/backoff có giới hạn và bảo đảm thao tác tạo đặt chỗ có thể khôi phục sau timeout. Không gọi liên tục vô hạn khi client gửi cursor không hợp lệ.

## 10. Kiểm thử tích hợp và bài thực hành

Unit test mock repository không chứng minh mapping, index hay continuation key đúng. Để kiểm tra thực tế, chạy Spring Boot với DynamoDB Local/LocalStack và bảng/index giống production.

### 10.1. Kiểm thử thủ công bằng AWS CLI

Sau khi tạo bảng và cấu hình credentials giả, ghi một item:

~~~bash
aws dynamodb put-item \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --item '{
    "tenantId":{"S":"tenant-a"},
    "sortKey":{"S":"RES#2026-11-24T08:30:00.000Z#res-1001"},
    "reservationId":{"S":"res-1001"},
    "propertyId":{"S":"house-99"},
    "propertyKey":{"S":"tenant-a#house-99"},
    "createdAt":{"S":"2026-11-24T08:30:00.000Z"},
    "state":{"S":"PENDING"},
    "guestCount":{"N":"2"}
  }'
~~~

Đọc item theo đầy đủ primary key:

~~~bash
aws dynamodb get-item \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --key '{
    "tenantId":{"S":"tenant-a"},
    "sortKey":{"S":"RES#2026-11-24T08:30:00.000Z#res-1001"}
  }'
~~~

Query GSI:

~~~bash
aws dynamodb query \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --index-name by-property \
  --key-condition-expression 'propertyKey = :pk' \
  --expression-attribute-values '{":pk":{"S":"tenant-a#house-99"}}' \
  --limit 10
~~~

Nhớ rằng AWS CLI có thể tự phân trang theo mặc định. Khi học sự khác nhau giữa `Limit`, `LastEvaluatedKey` và `ExclusiveStartKey`, hãy xem raw service response hoặc dùng thao tác SDK ở mục 8. Dùng các tham số CLI `--no-paginate`/`--max-items`/`--starting-token` phải hiểu chúng là cơ chế phân trang của **CLI** và có thể khác cách truyền trực tiếp DynamoDB `ExclusiveStartKey`.

### 10.2. Kiểm thử repository có phân trang

Các kịch bản nên chạy với endpoint thật của môi trường test:

1. Tạo nhiều item cùng tenant, gồm cả timestamp khác ngày/tháng; kiểm tra `monthPage(...)` chỉ trả đúng các item có sort key prefix được yêu cầu.
2. Gọi `monthPage(tenant, month, 2, null)`, nhận `nextKey` rồi gọi tiếp với **cùng các tham số**; kiểm tra không bỏ sót/đọc trùng trong tập dữ liệu không thay đổi.
3. Tạo item thuộc tenant khác, xác nhận request tenant A không trả item tenant B.
4. Query `by-property` theo `propertyKey`, kiểm tra chỉ đúng bất động sản; nếu vừa ghi, dùng bounded polling vì GSI có eventual consistency.
5. Tạo hai item cùng composite key bằng create-only; lần thứ hai phải phát sinh `ConditionalCheckFailedException`.
6. Dùng một `LastEvaluatedKey` không phù hợp hoặc cursor đã hết hạn trong tầng API; xác nhận API từ chối rõ ràng, không phát sinh query sang tenant khác.
7. Khi lọc theo state, kiểm tra trang có thể ít item hơn limit nhưng vẫn có `nextKey`; không dừng chỉ vì `items.size() < pageSize`.
8. Giới hạn mỗi request, theo dõi response time, read capacity, số DynamoDB page được fetch và chi phí khi tăng dữ liệu.

Test có thể dùng JUnit 5, Spring Boot Test và Testcontainers tạo DynamoDB Local/LocalStack, cấu hình endpoint động và dựng bảng trước khi test. Đừng coi ví dụ trong bài là bằng chứng đã chạy test; **chỉ báo PASS khi test thực sự chạy với endpoint và schema tương ứng**.

## 11. Tổng kết kiến thức dưới dạng quyết định kỹ thuật

| Câu hỏi thiết kế | Hướng chọn |
| --- | --- |
| Cần một item theo PK + SK? | `GetItem`; cân nhắc consistent read nếu cần |
| Cần nhiều item theo tenant và thời gian? | `Query` bảng với `partitionValue` + `sortBeginsWith`/range |
| Cần nhiều item theo property? | `Query` trên GSI `by-property` |
| Chỉ biết thuộc tính thường, không có index? | Xem lại access pattern và thiết kế GSI/lookup |
| Không muốn tạo trùng? | `PutItem` với `conditionExpression`, key/idempotency ổn định |
| Muốn cập nhật mà không mất thay đổi đồng thời? | Conditional update hoặc optimistic locking |
| Muốn API phân trang? | `LastEvaluatedKey` → signed cursor → `ExclusiveStartKey` |
| Page dưới `limit` có chắc hết dữ liệu? | Không; nhìn `LastEvaluatedKey` |
| Phải đọc ngay sau ghi qua GSI? | GSI eventual, cân nhắc đọc theo bảng |
| Cần viết nhiều item atomically? | DynamoDB transaction API, không giả định JPA transaction |

### Bài tập nâng cao

- Thêm GSI cho truy vấn theo `state` và thời gian, phân tích chi phí duy trì index khi trạng thái thay đổi nhiều lần.
- Xây `GET /reservations` trả `items` + `nextCursor`, dùng HMAC để ký cursor; test sửa token, token tenant khác và token hết hạn.
- Viết optimistic locking cho cập nhật trạng thái; mô phỏng hai tác vụ cùng đổi `PENDING` sang trạng thái khác nhau.
- Thêm tiêu chí giới hạn số request/phân trang trong service và metric consumed capacity; so sánh tác động của filter so với truy vấn index.
- Thử đọc theo table với `consistentRead(true)` và query GSI sau ghi mới; giải thích các guarantee khác nhau.
- So sánh cursor DynamoDB với continuation token của Azure Cosmos DB và cơ chế cursor/query snapshot của Google Cloud Firestore, nhất là ranh giới xác thực/tenant.

## Tài liệu tham khảo

- [AWS DynamoDB — Read and write operations](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadWrite.html).
- [AWS DynamoDB — Query: Key condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.KeyConditionExpressions.html).
- [AWS DynamoDB — Query: Filter expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html).
- [AWS DynamoDB — Paginating query results](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html).
- [AWS DynamoDB — Global Secondary Indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html).
- [AWS DynamoDB — Condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html).
- [AWS DynamoDB — Batch operations and error handling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-query-scan.html).
- [AWS SDK for Java v2 — DynamoDB Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html).
- [AWS SDK for Java v2 — Secondary indexes with Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/ddb-en-client-use-secindex.html).
- [Spring Cloud AWS — Reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html).
