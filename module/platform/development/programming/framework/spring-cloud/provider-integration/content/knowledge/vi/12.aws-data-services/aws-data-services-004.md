# Phân biệt Query và Scan khi thiết kế truy cập

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, Spring Boot kết nối các dịch vụ managed của AWS, Azure và Google Cloud thông qua SDK và thư viện Spring Cloud tương ứng. Ở chương **Dữ liệu AWS**, Amazon DynamoDB là cơ sở dữ liệu NoSQL quản lý bởi AWS. Chọn thao tác đọc phù hợp ảnh hưởng trực tiếp đến **độ trễ, số lần gọi dịch vụ, chi phí đọc, khả năng mở rộng và bảo vệ dữ liệu tenant**.

Hai thao tác dễ bị nhầm là **`Query`** và **`Scan`**:

- `Query` đọc tập item bằng **partition key** của bảng hoặc secondary index; có thể bổ sung điều kiện trên **sort key**.
- `Scan` duyệt các item của bảng hoặc index, không cần key condition; filter, nếu có, được áp dụng **sau khi dữ liệu đã được đọc**.

Sau bài học, bạn có thể:

1. Chọn `GetItem`, `Query` hay `Scan` từ một access pattern cụ thể.
2. Thiết kế partition key, sort key và GSI để tránh Scan trong API nghiệp vụ thường xuyên.
3. Giải thích chính xác `KeyConditionExpression`, `FilterExpression`, `ProjectionExpression`, `Limit`, `Count` và `ScannedCount`.
4. Ước lượng tác động chi phí/độ trễ của Query và Scan, kể cả khi filter chỉ trả vài item.
5. Thực hiện Query/Scan bằng AWS SDK for Java v2, tích hợp vào repository Spring Boot và nhận biết vai trò tùy phiên bản của Spring Cloud AWS.
6. Phân trang với `LastEvaluatedKey` / `ExclusiveStartKey`, kiểm soát Scan hợp lệ và kiểm thử bằng DynamoDB Local.

> **Phạm vi:** Các nguyên tắc này thuộc DynamoDB, không tự áp dụng nguyên trạng cho truy vấn của Azure Cosmos DB hoặc Google Cloud Firestore. Khi thiết kế hệ thống đa cloud, giữ interface nghiệp vụ ổn định nhưng triển khai adapter theo cơ chế partition/index của từng dịch vụ.

## 2. Bắt đầu từ access pattern

DynamoDB được thiết kế để tìm theo khóa và các truy vấn đã dự đoán trước. Vì vậy, thiết kế dữ liệu nên bắt đầu từ **người dùng cần lấy gì, biết giá trị nào khi gọi API, kết quả có thể lớn đến đâu và tần suất bao nhiêu**.

Giả sử dịch vụ quản lý lượt đặt chỗ cho nhiều công ty:

| Thuộc tính | Ví dụ | Vai trò |
| --- | --- | --- |
| `tenantId` | `tenant-a` | Partition key của bảng `reservation_record` |
| `sortKey` | `RES#2026-11-24T08:00:00.000Z#res-1001` | Sort key của bảng; hỗ trợ liệt kê theo thời gian |
| `reservationId` | `res-1001` | Mã đặt chỗ nghiệp vụ |
| `propertyId` | `house-99` | Bất động sản liên quan |
| `propertyKey` | `tenant-a#house-99` | Partition key của GSI `by-property` |
| `createdAt` | `2026-11-24T08:00:00.000Z` | Sort key của GSI `by-property` |
| `state` | `CONFIRMED` | Trạng thái đặt chỗ |

Bảng có **composite primary key** là `(tenantId, sortKey)`. GSI `by-property` có key là `(propertyKey, createdAt)`. Mọi timestamp trong khóa String được chuẩn hóa về **UTC, độ chính xác millisecond** để thứ tự so sánh theo chuỗi phù hợp thứ tự thời gian.

Bốn câu hỏi nghiệp vụ dẫn đến các lựa chọn khác nhau:

| Yêu cầu | Khóa người gọi đã biết | Cơ chế thích hợp | Vì sao |
| --- | --- | --- | --- |
| Lấy đúng lượt đặt đã biết | `tenantId` và toàn bộ `sortKey` | `GetItem` | Định vị duy nhất một item |
| Lấy lượt đặt tháng 11 của tenant | `tenantId`, tiền tố `RES#2026-11` | `Query` bảng | Partition key bằng giá trị cụ thể + prefix sort key |
| Lấy lượt đặt của một bất động sản | `tenantId`, `propertyId` | `Query` GSI `by-property` | Index có partition key `tenantId#propertyId` |
| Rà soát toàn bảng để phát hiện dữ liệu không hợp lệ theo kỳ | Không biết key cụ thể | `Scan` có giới hạn, chạy theo lô | Tác vụ quản trị có chủ ý phải duyệt nhiều item |

Truy vấn chỉ với `reservationId` mà không biết timestamp **không thể gọi trực tiếp `GetItem` theo mô hình trên**. Có thể thiết kế lại khóa, thêm lookup item hoặc GSI chuyên dụng. Không nên cố giải quyết bằng một Scan ở mỗi request.

~~~mermaid
flowchart TD
    A["Nhu cầu truy xuất"] --> B{"Biết đủ PK và SK?"}
    B -->|"Có, 1 item"| C["GetItem"]
    B -->|"Không"| D{"Biết PK của bảng hoặc index?"}
    D -->|"Có"| E["Query theo key<br/>+ điều kiện sort key nếu cần"]
    D -->|"Không"| F{"Có thể tạo index/lookup?"}
    F -->|"Có"| G["Thiết kế index/lookup<br/>rồi Query"]
    F -->|"Không, tác vụ duyệt toàn bộ có chủ đích"| H["Scan có giới hạn<br/>và giám sát"]
~~~

## 3. `Query` thực sự hoạt động như thế nào?

### 3.1. Key condition là bộ định vị dữ liệu

`Query` trên một bảng hoặc index yêu cầu **điều kiện bằng (`=`) trên đúng partition key của đối tượng đang Query**. Nếu có sort key, có thể thêm một điều kiện:

- `=`, `<`, `<=`, `>`, `>=`;
- `BETWEEN :from AND :to` (bao gồm hai đầu);
- `begins_with(sortKey, :prefix)` cho **sort key kiểu String hoặc Binary**, không áp dụng cho Number.

Ví dụ Query bảng:

~~~sql
tenantId = :tenant AND begins_with(sortKey, :monthPrefix)
-- :tenant      = "tenant-a"
-- :monthPrefix = "RES#2026-11"
~~~

Điều kiện trên có nghĩa “đọc tập item của `tenant-a` với sort key bắt đầu bằng `RES#2026-11`”. Nếu muốn truy vấn GSI `by-property` thì phải đổi sang khóa **của index**:

~~~sql
propertyKey = :property AND begins_with(createdAt, :monthPrefix)
-- :property    = "tenant-a#house-99"
-- :monthPrefix = "2026-11"
~~~

Không thể đặt `propertyId = :id` trong `KeyConditionExpression` nếu `propertyId` chỉ là thuộc tính thường. Tương tự, không thể gọi `Query` mà bỏ điều kiện partition key.

### 3.2. Thứ tự và kích thước kết quả

`Query` trả kết quả theo **sort key của bảng/index**. Với sort key Number, thứ tự theo giá trị số; với String, theo byte UTF-8. `ScanIndexForward=true` cho thứ tự tăng dần (mặc định), còn `false` đảo chiều. Thứ tự này chỉ có ý nghĩa **trong một partition key** đã được Query.

Một lần gọi `Query` xử lý tối đa **1 MB dữ liệu trước filter/projection**, hoặc dừng sớm khi đạt `Limit`. Nếu còn dữ liệu, response chứa `LastEvaluatedKey` để đọc tiếp. Vì vậy một `Query` theo tenant có hàng triệu item **vẫn có thể rất tốn kém** nếu ứng dụng duyệt hết trang.

**Nhớ:** `Query` thường hiệu quả hơn `Scan` cho một access pattern cụ thể, nhưng hiệu quả còn phụ thuộc tính chọn lọc của key condition, kích thước item, số trang cần đọc và mức độ tập trung lưu lượng trên partition key.

## 4. `Scan` thực sự hoạt động như thế nào?

### 4.1. Scan đọc dữ liệu rộng

`Scan` xem các item trong **toàn bảng hoặc toàn secondary index** theo từng trang. DynamoDB không dùng một `KeyConditionExpression` để thu hẹp Scan về một partition key.

Ví dụ yêu cầu:

~~~sql
-- Đây là filter của Scan, KHÔNG phải KeyConditionExpression:
state = :expected
-- :expected = "CONFIRMED"
~~~

DynamoDB phải **đọc các item thuộc phần Scan đang xử lý rồi mới áp dụng filter**. Nếu bảng có 500.000 item và chỉ 200 item `CONFIRMED`, filter không khiến DynamoDB định vị trực tiếp được 200 item đó.

Một lần Scan đọc tối đa **1 MB trước filter** hoặc số item được đánh giá theo `Limit`; muốn duyệt toàn bảng phải thực hiện nhiều request đến khi không còn `LastEvaluatedKey`. `Scan` không bảo đảm thứ tự tăng dần theo key trên toàn bảng như `Query` một partition key.

### 4.2. `Count` và `ScannedCount`

Trong response của Scan:

- `ScannedCount`: số item đã được DynamoDB **đánh giá** trong request, trước filter.
- `Count`: số item **còn lại sau filter** trong request.
- `Items`: các item trả về theo filter/projection.
- `LastEvaluatedKey`: vị trí để tiếp tục, nếu còn dữ liệu có thể được duyệt.

Ví dụ một trang đọc 100 item nhưng chỉ 3 item đúng điều kiện:

~~~text
ScannedCount = 100
Count        = 3
LastEvaluatedKey = { ... }    # Vẫn có thể còn dữ liệu
~~~

Tỷ lệ chọn lọc của filter trong trang này là `3 / 100 = 3%`. Đây là dấu hiệu đáng xem xét lại thiết kế access pattern khi Scan chạy thường xuyên. `Count` và `ScannedCount` chỉ phản ánh **trang hiện tại**; cộng nhiều trang nếu cần thống kê cả lượt quét.

### 4.3. Khi nào Scan có chỗ đứng?

Scan có thể hợp lý cho:

- Bài toán vận hành một lần: backfill, kiểm toán dữ liệu, migration, đối chiếu schema.
- Job định kỳ không thể mô hình bằng key/index và được chạy ngoài giờ cao điểm.
- Tập dữ liệu nhỏ, tải truy vấn rất thấp, đã đo chi phí/độ trễ.
- Công cụ quản trị/điều tra có quota, phạm vi quyền và giới hạn truy cập rõ ràng.

Không nên biến Scan thành đường mặc định cho màn hình danh sách có tần suất cao hoặc API tự phục vụ quy mô lớn. Nếu buộc Scan trên bảng lớn, ưu tiên job bất đồng bộ với checkpoint, giới hạn tốc độ, retry có backoff và metric; không duyệt hết bảng trong một request HTTP rồi giữ kết nối quá lâu.

## 5. So sánh Query và Scan theo quyết định kỹ thuật

| Tiêu chí | `Query` | `Scan` |
| --- | --- | --- |
| Điều kiện bắt buộc | `partitionKey = value` | Không cần key |
| Sort key | Có thể thêm range, prefix hoặc so sánh | Không dùng key condition để thu hẹp |
| Phạm vi đọc | Item thỏa key condition trên bảng/index | Duyệt toàn bảng/index qua nhiều trang nếu không dừng |
| `FilterExpression` | Áp dụng sau dữ liệu phù hợp key condition đã đọc | Áp dụng sau dữ liệu của trang Scan đã đọc |
| `ProjectionExpression` | Chọn thuộc tính trả về, không tự giảm RCU của đọc bảng | Chọn thuộc tính trả về, không tự giảm RCU của đọc bảng |
| Thứ tự | Theo sort key trong partition key Query | Không bảo đảm thứ tự toàn bảng hữu ích |
| Pagination | `LastEvaluatedKey` → `ExclusiveStartKey` | Cùng cơ chế; thường nhiều trang hơn |
| `Limit` | Số item tối đa được đánh giá trước filter mỗi request | Số item tối đa được đánh giá trước filter mỗi request |
| 1 MB/request | Có | Có |
| Consistency | Strong trên bảng/LSI nếu yêu cầu; GSI eventual | Strong trên bảng/LSI khi hỗ trợ, **không tạo snapshot toàn Scan**; GSI eventual |
| Parallel read | Có thể tách nhiều Query theo khóa ở tầng ứng dụng | Hỗ trợ **parallel Scan** bằng `Segment`/`TotalSegments` |
| Khi dùng | API nghiệp vụ đã thiết kế key/index | Backfill, audit, batch duyệt dữ liệu có chủ đích |

**Sai lầm phổ biến:** “Scan có filter thì chỉ tốn tài nguyên của vài item được trả về” và “Query luôn rẻ”. Cả hai đều sai. Chi phí đọc dựa trên **dữ liệu DynamoDB đã xử lý**, kiểu nhất quán, kích thước item/index và số lần truy xuất. Filter chỉ làm giảm số item được gửi tới client; Query thiếu chọn lọc cũng có thể đọc nhiều MB qua nhiều trang.

## 6. `KeyCondition`, `FilterExpression` và `ProjectionExpression`

### 6.1. Bộ ba có vai trò khác nhau

~~~mermaid
flowchart LR
    A["Bảng / Index"] --> B["Chọn phạm vi theo key<br/>Query: PK=... và SK...<br/>Scan: duyệt"]
    B --> C["Đọc trang dữ liệu<br/>tối đa 1 MB / Limit"]
    C --> D["Áp dụng FilterExpression"]
    D --> E["Chỉ gửi thuộc tính theo Projection"]
    E --> F["Items + LastEvaluatedKey"]
~~~

- **Key condition:** chỉ áp dụng cho `Query`, dùng partition key và tùy chọn sort key. Đây là phần **giảm phạm vi dữ liệu phải đọc**.
- **Filter expression:** có thể dùng với Query hoặc Scan, lọc sau khi các item đã được đọc. Query filter **không được đặt điều kiện trên primary key của bảng/index đang Query**; điều kiện khóa cần ở key condition.
- **Projection expression:** yêu cầu DynamoDB trả về những trường cụ thể. Có thể giảm bytes truyền qua mạng và memory ở client; **không mặc nhiên giảm read capacity** của truy vấn bảng, vì DynamoDB đã đọc các item liên quan.
- **GSI projection:** GSI chỉ chứa những thuộc tính được project (cùng khóa cần thiết); Query GSI thường đọc trên kích thước index item, có thể tiết kiệm khi index nhỏ hơn base table. GSI không tự fetch các trường không được project từ bảng nguồn.

### 6.2. “Filter chỉ có 2% kết quả” là vấn đề truy cập

Giả sử API `GET /reservations?state=CONFIRMED` mỗi giây được gọi hàng trăm lần, bảng có nhiều triệu item và `state` không phải khóa của bảng/index. Hai cách xử lý:

**Cách A — Scan + filter:**

~~~text
Scan reservation_record
FilterExpression: state = "CONFIRMED"
~~~

Mỗi lần API có thể phải duyệt nhiều trang và tiêu thụ nhiều read capacity. Thời gian phản hồi tăng theo dữ liệu, có thể làm chậm các tác vụ khác.

**Cách B — Thiết kế access pattern:**

~~~text
GSI by-tenant-state-time
  partition key: tenantStateKey = tenantId + "#STATE#" + state
  sort key:      createdAt
Query index với tenantStateKey = "tenant-a#STATE#CONFIRMED"
~~~

Query mới chỉ đọc item theo khóa của index và có thể sắp theo thời gian. Đánh đổi là tăng dung lượng index, số lần ghi index khi trạng thái thay đổi, và GSI chỉ có eventual consistency. Thiết kế tốt còn phải kiểm tra cardinality, hot key và quyền tenant.

**Không có thiết kế duy nhất đúng cho mọi hệ thống.** Nếu báo cáo trạng thái chỉ chạy một lần mỗi đêm, ít item, Scan có quota có thể đơn giản hơn duy trì index không cần thiết. Nếu truy vấn là tính năng chính của sản phẩm, index/aggregate/materialized view thường đáng cân nhắc.

## 7. Ước lượng chi phí và độ trễ một cách có cơ sở

### 7.1. Số item trả về không phản ánh toàn bộ công việc đọc

Xem tình huống giả định:

- Bảng chứa khoảng **200.000 reservation**, mỗi item khoảng 1 KB.
- Tenant `tenant-a` có 500 reservation trong tháng 11.
- Màn hình hiển thị **20 reservation gần nhất** theo tenant và tháng.
- Một số item có `state=CONFIRMED` nhưng trạng thái không nằm trong key/index.

| Phương án | Dữ liệu DynamoDB cần xem xét | Điều người dùng nhận |
| --- | --- | --- |
| `Query` PK=tenant-a + sort key prefix, đảo chiều, lấy trang đầu | Item trong đúng dải khóa của tenant/tháng | Tối đa số item thỏa điều kiện của một trang |
| `Query` rồi filter state | Cùng phạm vi key condition, filter áp dụng sau đọc | Có thể dưới 20 item; cần trang tiếp nếu còn key |
| `Scan` toàn bảng rồi filter tenant/tháng/state | Có thể nhiều trang trên lượng dữ liệu rất lớn | Có thể cũng chỉ 20 item dù đã đọc hàng nghìn item |

Không thể suy ra một mức RCU chính xác từ các con số trên nếu chưa biết kích thước dữ liệu thật, consistency, số page và cách truy vấn được thực thi. Có thể nêu quy tắc nền tảng: DynamoDB tính năng lực đọc theo khối **4 KB** và kiểu đọc; với một lượng dữ liệu tương đương, eventual consistency thường tiêu thụ khoảng **một nửa** năng lực đọc so với strong consistency. Scan 1 MB có thể tiêu tốn một lượng đáng kể read capacity trong một request. Hãy đo trên dữ liệu mẫu thay vì dùng số item trả về để ước lượng bill.

### 7.2. Chỉ số cần đo

Đối với từng loại request, ghi nhận:

- **Độ trễ end-to-end** và độ trễ request đến DynamoDB.
- **Consumed capacity** (`ReturnConsumedCapacity=TOTAL` hoặc `INDEXES` khi API hỗ trợ), read capacity theo bảng/index.
- **Số item đánh giá** `ScannedCount` so với **số trả về** `Count`; so sánh riêng từng trang rồi cộng cả lượt.
- **Số trang**, tổng bytes response và thời gian hoàn tất.
- **Throttling**, retry, timeout, số request bị lỗi.
- Độ phân tán key và lưu lượng trên partition/index nóng.

Một Query có `ScannedCount=10` và `Count=10` thường cho thấy filter không loại item, còn Scan có `ScannedCount=10000` và `Count=12` là tín hiệu phải xem xét lại. Nhưng các chỉ số này luôn cần đặt trong ngữ cảnh của access pattern, dữ liệu và tần suất request.

## 8. Mã ví dụ Spring Boot: ánh xạ entity và dùng Enhanced Client

### 8.1. Dependencies và auto-configuration

Ở Spring Boot, có thể chọn **Spring Cloud AWS (AWSpring)** với starter DynamoDB hoặc cấu hình **AWS SDK for Java v2** trực tiếp.

~~~xml
<!-- Khi sử dụng AWSpring: chọn BOM phù hợp với phiên bản Spring Boot -->
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-dynamodb</artifactId>
</dependency>
~~~

Nếu dùng SDK v2 thuần, thêm các dependency dưới sự quản lý của AWS SDK BOM:

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

`DynamoDbTemplate` là abstraction của những phiên bản Spring Cloud AWS hỗ trợ nó. API của template không nhất thiết giống Enhanced Client và không phải một Spring Data JPA repository. Ở đây dùng trực tiếp Enhanced Client để làm rõ Query/Scan, biểu thức, index và ranh giới trang. Nếu starter tự cung cấp bean `DynamoDbEnhancedClient`, inject bean đó; nếu dùng SDK thuần, cấu hình client riêng và dùng credential provider chain.

### 8.2. Entity khớp bảng và GSI

~~~java
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbBean;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSortKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondaryPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondarySortKey;

@DynamoDbBean
public class ReservationItem {
    private String tenantId;
    private String sortKey;
    private String reservationId;
    private String propertyKey;
    private String createdAt;
    private String state;

    public ReservationItem() {}

    @DynamoDbPartitionKey
    public String getTenantId() { return tenantId; }
    public void setTenantId(String value) { tenantId = value; }

    @DynamoDbSortKey
    public String getSortKey() { return sortKey; }
    public void setSortKey(String value) { sortKey = value; }

    public String getReservationId() { return reservationId; }
    public void setReservationId(String value) { reservationId = value; }

    @DynamoDbSecondaryPartitionKey(indexNames = "by-property")
    public String getPropertyKey() { return propertyKey; }
    public void setPropertyKey(String value) { propertyKey = value; }

    @DynamoDbSecondarySortKey(indexNames = "by-property")
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String value) { createdAt = value; }

    public String getState() { return state; }
    public void setState(String value) { state = value; }
}
~~~

Các getter có annotation thuộc **Enhanced Client**; cần public getter/setter và constructor không tham số. Annotation khai báo mapping, **không tự tạo bảng hoặc index**. `sortKey` và `propertyKey` cần được service tạo nhất quán lúc ghi item.

### 8.3. Repository Query bảng, Query GSI và Scan

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;

import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;
import software.amazon.awssdk.enhanced.dynamodb.model.Page;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;
import software.amazon.awssdk.enhanced.dynamodb.model.ScanEnhancedRequest;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

@Repository
public class ReservationReadRepository {
    private final DynamoDbTable<ReservationItem> table;

    public ReservationReadRepository(DynamoDbEnhancedClient client) {
        this.table = client.table(
                "reservation_record",
                TableSchema.fromBean(ReservationItem.class));
    }

    public record ReadPage(
            List<ReservationItem> items,
            Map<String, AttributeValue> nextKey) {}

    // Query đúng tenant và prefix tháng trên bảng.
    public ReadPage queryMonth(String tenantId, String yyyyMM,
            Map<String, AttributeValue> startKey) {
        QueryEnhancedRequest.Builder request =
                QueryEnhancedRequest.builder()
                        .queryConditional(QueryConditional.sortBeginsWith(
                                Key.builder()
                                        .partitionValue(tenantId)
                                        .sortValue("RES#" + yyyyMM)
                                        .build()))
                        .scanIndexForward(false)
                        .limit(20);
        if (startKey != null && !startKey.isEmpty()) {
            request.exclusiveStartKey(startKey);
        }
        Iterator<Page<ReservationItem>> pages =
                table.query(request.build()).iterator();
        return pages.hasNext()
                ? toPage(pages.next())
                : new ReadPage(List.of(), null);
    }

    // Query GSI bằng khóa của INDEX, không phải khóa của bảng.
    public ReadPage queryProperty(String propertyKey,
            Map<String, AttributeValue> startKey) {
        QueryEnhancedRequest.Builder request =
                QueryEnhancedRequest.builder()
                        .queryConditional(QueryConditional.keyEqualTo(
                                Key.builder()
                                        .partitionValue(propertyKey)
                                        .build()))
                        .limit(20);
        if (startKey != null && !startKey.isEmpty()) {
            request.exclusiveStartKey(startKey);
        }
        Iterator<Page<ReservationItem>> pages = table
                .index("by-property")
                .query(request.build())
                .iterator();
        return pages.hasNext()
                ? toPage(pages.next())
                : new ReadPage(List.of(), null);
    }

    // Chỉ dành cho job quản trị/batch đã được kiểm soát.
    public ReadPage scanOnePage(
            Map<String, AttributeValue> startKey) {
        ScanEnhancedRequest.Builder request =
                ScanEnhancedRequest.builder().limit(20);
        if (startKey != null && !startKey.isEmpty()) {
            request.exclusiveStartKey(startKey);
        }
        Iterator<Page<ReservationItem>> pages =
                table.scan(request.build()).iterator();
        return pages.hasNext()
                ? toPage(pages.next())
                : new ReadPage(List.of(), null);
    }

    private static ReadPage toPage(Page<ReservationItem> page) {
        return new ReadPage(
                List.copyOf(page.items()),
                page.lastEvaluatedKey());
    }
}
~~~

**Ý nghĩa của phương thức một trang:** đối tượng trả về từ `query(...)` hoặc `scan(...)` có thể lazy-load những trang tiếp theo. Lấy đúng `pages.next()` một lần giúp repository trả **một trang DynamoDB**, tránh vô tình duyệt toàn bộ kết quả trong HTTP request. `limit(20)` chỉ giới hạn số item **được đánh giá trong một request**, không bảo đảm một trang luôn trả đủ 20 item (đặc biệt khi dùng filter) hoặc rằng đó là tổng kích thước toàn bộ kết quả.

Trước khi gọi `queryMonth` cần xác thực `yyyyMM` ở tầng API, ví dụ `YearMonth.parse(value)`; nếu không, prefix có thể sai hoặc quá rộng. Trước khi gọi `queryProperty`, phải sinh `propertyKey` từ tenant đã xác thực và property ID đã validate, không nhận tự do từ client.

**Scan trong repository chỉ minh họa một trang**, không phải lời khuyên xây endpoint public `GET /all`. Nếu cần duyệt hết bảng, triển khai worker/job có kiểm soát, không đặt vòng lặp lấy mọi trang trong controller.

### 8.4. Khi cần kiểm tra `ScannedCount` và consumed capacity

AWS SDK v2 cấp thấp phơi bày rõ các trường này. Một ví dụ có kiểm soát để so sánh Filter với Scan:

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;
import software.amazon.awssdk.services.dynamodb.model.ScanRequest;
import software.amazon.awssdk.services.dynamodb.model.ScanResponse;

public class ScanDiagnostics {
    private final DynamoDbClient client;

    public ScanDiagnostics(DynamoDbClient client) {
        this.client = client;
    }

    public void inspectOnePage() {
        ScanRequest request = ScanRequest.builder()
                .tableName("reservation_record")
                .filterExpression("#status = :state")
                .expressionAttributeNames(Map.of("#status", "state"))
                .expressionAttributeValues(Map.of(
                        ":state", AttributeValue.builder()
                                .s("CONFIRMED").build()))
                .limit(50)
                .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL)
                .build();

        ScanResponse response = client.scan(request);
        System.out.println("ScannedCount = " + response.scannedCount());
        System.out.println("Count = " + response.count());
        System.out.println("ConsumedCapacity = "
                + response.consumedCapacity());
        System.out.println("HasMore = "
                + !response.lastEvaluatedKey().isEmpty());
    }
}
~~~

Đây là mã **chẩn đoán cho một trang**; nếu chỉ có 2 item `CONFIRMED` trong 50 item được đánh giá, `ScannedCount` vẫn là 50. Không để `System.out.println` và dữ liệu khách hàng trong logs production; sử dụng metrics/logging đã lọc thông tin nhạy cảm.

## 9. Phân trang: `Limit` không có nghĩa “chỉ đọc N kết quả thỏa điều kiện”

### 9.1. Quy trình hai thao tác giống nhau

Cả Query và Scan đều có thể trả `LastEvaluatedKey`. Request tiếp theo giữ nguyên những điều kiện/query context và đặt `ExclusiveStartKey` bằng map key vừa nhận.

~~~mermaid
sequenceDiagram
    participant UI as Client
    participant API as Spring Boot
    participant DB as DynamoDB
    UI->>API: GET /reservations?tenant=...&pageSize=20
    API->>DB: Query key condition + Limit=20
    DB-->>API: Items + LastEvaluatedKey
    API-->>UI: Items + nextCursor
    UI->>API: GET /reservations?cursor=...
    API->>DB: Query cùng điều kiện + ExclusiveStartKey
    DB-->>API: Items + LastEvaluatedKey hoặc rỗng
    API-->>UI: Items + nextCursor hoặc null
~~~

Nếu response **không có `LastEvaluatedKey`** (hoặc map rỗng), lượt đọc đã đến cuối tại thời điểm đó. Nếu có key, có thể còn dữ liệu. Một trang trả **0 item** vẫn có thể có next key sau khi filter; đừng xem `items.isEmpty()` hay `items.size() < limit` là dấu hiệu hết.

DynamoDB không bảo đảm snapshot nhất quán xuyên suốt nhiều request phân trang. Nếu dữ liệu được ghi/xóa/sửa key trong lúc client chuyển trang, kết quả có thể khác thời điểm trang đầu. Một Scan có `ConsistentRead=true` cũng không biến toàn bộ nhiều trang thành snapshot transaction.

### 9.2. Thiết kế cursor public

`ReadPage.nextKey` là map kỹ thuật của AWS SDK. API public nên trả `nextCursor` mờ và kiểm tra:

- Cursor thuộc đúng **tenant đã xác thực**, table/index, key condition, filter, hướng sort và page size.
- Token có phiên bản, thời hạn và **chữ ký HMAC** hoặc authenticated encryption; Base64 chỉ là biểu diễn, **không chống sửa**.
- Nếu query GSI, giữ **nguyên map khóa trả về**; đừng tự dựng cursor chỉ có partition key mà làm mất khóa bảng/index.
- Từ chối cursor lạ/hết hạn/đổi tham số, giới hạn kích thước token và tránh để thông tin nhạy cảm lộ trong log.
- Trả lỗi rõ ràng và yêu cầu client bắt đầu lại khi token không còn hợp lệ.

Ví dụ payload API (token chỉ là placeholder):

~~~json
{
  "items": [
    {"reservationId":"res-1001","state":"CONFIRMED"}
  ],
  "nextCursor": "opaque-signed-token-from-server"
}
~~~

Nếu nghiệp vụ yêu cầu trả **đủ 20 item sau Filter**, có thể phải gọi nhiều trang DynamoDB rồi gộp. Cần giới hạn **số request, read budget và thời gian**; không lặp vô hạn chỉ để lấp đầy trang. Cách tốt hơn cho truy vấn phổ biến là **thiết kế GSI đủ chọn lọc** để giảm số item phải đọc.

## 10. Parallel Scan: khi cần và điều cần tránh

DynamoDB hỗ trợ chia Scan thành các segment bằng `Segment` và `TotalSegments`, cho phép nhiều worker duyệt các segment khác nhau. Parallel Scan hữu ích trong job xử lý lượng lớn dữ liệu, nhưng:

- Có thể **tăng tốc độ tiêu thụ read capacity**, không làm giảm tổng lượng dữ liệu phải đọc.
- Có thể tăng contention/throttling cho các luồng nghiệp vụ cùng bảng hoặc GSI.
- Mỗi segment phải có checkpoint `LastEvaluatedKey` **riêng**; `ExclusiveStartKey` chỉ tiếp tục trong đúng segment.
- Không dùng để hỗ trợ API phân trang tùy ý cho người dùng hoặc để sắp xếp kết quả trên toàn bảng.
- Nếu thay đổi `TotalSegments` giữa chừng, phải có chiến lược chạy lại/chia lại công việc; không tự trộn cursor.
- Có thể cần giới hạn đồng thời, backoff với jitter, queue/batch window, metric và cơ chế tiếp tục sau lỗi.

Ví dụ SDK v2 cấp thấp cho **một trang segment**:

~~~java
import software.amazon.awssdk.services.dynamodb.model.ScanRequest;
import software.amazon.awssdk.services.dynamodb.model.ScanResponse;

int totalSegments = 4;
int segmentNumber = 0; // Mỗi worker nhận một giá trị 0..3.

ScanResponse page = client.scan(ScanRequest.builder()
        .tableName("reservation_record")
        .totalSegments(totalSegments)
        .segment(segmentNumber)
        .limit(100)
        .build());

// Chỉ worker segmentNumber được tái dùng page.lastEvaluatedKey().
~~~

`client` ở ví dụ trên là `DynamoDbClient`; ví dụ minh họa cấu hình segment chứ chưa tạo toàn bộ job, checkpoint hoặc retry. Chỉ cân nhắc parallel Scan sau khi đo và xác nhận cần duyệt bảng/index thật sự.

## 11. IAM, bảo mật tenant và môi trường triển khai

### 11.1. Chỉ cấp đúng quyền cần dùng

Với repository sử dụng Query trên bảng và GSI:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:Query", "dynamodb:GetItem"],
      "Resource": [
        "arn:aws:dynamodb:ap-southeast-1:123456789012:table/reservation_record",
        "arn:aws:dynamodb:ap-southeast-1:123456789012:table/reservation_record/index/by-property"
      ]
    }
  ]
}
~~~

Thay region/account/table/index bằng môi trường thật. Đối với job Scan, cấp thêm `dynamodb:Scan` **trên tài nguyên thực sự cần**, tốt nhất dùng role chuyên dụng. Không cấp cho API user-facing quyền Scan chỉ vì code dễ viết.

Application phải kiểm tra tenant ID từ token/danh tính đã xác thực; không tin `tenantId` hoặc `propertyKey` do client tự chọn. Có thể cân nhắc IAM condition như `dynamodb:LeadingKeys` khi mô hình danh tính/phân vùng cho phép, nhưng vẫn cần authorization theo nghiệp vụ. Không ghi credentials, dữ liệu nhạy cảm, cursor raw hoặc toàn bộ item khách hàng vào log.

### 11.2. Cấu hình region, credentials và local endpoint

Ở AWS, gắn IAM role vào workload (ECS task, EC2 instance, EKS pod identity/IRSA theo môi trường); AWS SDK và AWSpring có thể dùng credential provider chain. Ví dụ cấu hình AWSpring ở phiên bản hỗ trợ:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Chạy thử ở local bằng DynamoDB Local:

~~~bash
docker run --rm -p 8000:8000 amazon/dynamodb-local:latest
~~~

~~~yaml
# application-local.yml (AWSpring phiên bản hỗ trợ property này)
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        endpoint: http://localhost:8000
~~~

Cần set credentials giả (ví dụ `AWS_ACCESS_KEY_ID=local`, `AWS_SECRET_ACCESS_KEY=local`) trong terminal local để ký request; không sử dụng credentials giả ở AWS thật. Nếu tự cấu hình `DynamoDbClient` bằng SDK thuần, phải cấu hình `endpointOverride(URI.create("http://localhost:8000"))` tương ứng, vì property AWSpring không tự có tác dụng lên client do mình tạo.

## 12. Thực hành đối chiếu Query và Scan trên DynamoDB Local

### 12.1. Tạo bảng và dữ liệu mẫu

Tạo bảng với composite primary key và GSI:

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

Lưu một reservation:

~~~bash
aws dynamodb put-item \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --item '{
    "tenantId":{"S":"tenant-a"},
    "sortKey":{"S":"RES#2026-11-24T08:00:00.000Z#res-1001"},
    "reservationId":{"S":"res-1001"},
    "propertyKey":{"S":"tenant-a#house-99"},
    "createdAt":{"S":"2026-11-24T08:00:00.000Z"},
    "state":{"S":"CONFIRMED"}
  }'
~~~

Tạo thêm một số bản ghi khác tenant, khác tháng, khác `state` và `propertyKey` để thấy Query trả ít đúng key còn Scan phải đọc rộng hơn. Nếu chỉ có một bản ghi, so sánh chưa phản ánh khác biệt chi phí.

### 12.2. Truy vấn với CLI

**Query theo key của bảng:**

~~~bash
aws dynamodb query \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --key-condition-expression 'tenantId = :t AND begins_with(sortKey, :p)' \
  --expression-attribute-values '{
    ":t":{"S":"tenant-a"},
    ":p":{"S":"RES#2026-11"}
  }' \
  --limit 20 \
  --return-consumed-capacity TOTAL \
  --no-paginate
~~~

**Query GSI theo nhà:**

~~~bash
aws dynamodb query \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --index-name by-property \
  --key-condition-expression 'propertyKey = :p' \
  --expression-attribute-values '{
    ":p":{"S":"tenant-a#house-99"}
  }' \
  --limit 20 \
  --return-consumed-capacity TOTAL \
  --no-paginate
~~~

**Scan với filter:**

~~~bash
aws dynamodb scan \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --filter-expression '#s = :s' \
  --expression-attribute-names '{"#s":"state"}' \
  --expression-attribute-values '{":s":{"S":"CONFIRMED"}}' \
  --limit 20 \
  --return-consumed-capacity TOTAL \
  --no-paginate
~~~

Quan sát `Count`, `ScannedCount`, `ConsumedCapacity` và `LastEvaluatedKey`. Tùy số item và giới hạn request, có thể chưa thấy next key; tăng dữ liệu và dùng limit nhỏ hơn để thực hành pagination. AWS CLI có **cơ chế auto-pagination riêng**; ở ví dụ này dùng `--no-paginate` để dễ quan sát response của một lượt gọi. Đừng nhầm `--starting-token` của CLI với map DynamoDB `ExclusiveStartKey`.

### 12.3. Kịch bản kiểm thử tích hợp Spring Boot

Một bộ kiểm thử đáng có:

1. **Đúng key:** Query `tenant-a`, prefix tháng 11 chỉ trả item thuộc đúng tenant/tháng, không lẫn `tenant-b`.
2. **Đúng index:** Query `by-property` chỉ trả item có `propertyKey` tương ứng. Ngay sau ghi, GSI có thể cần bounded polling vì eventual consistency.
3. **Filter sau đọc:** Scan với filter chỉ trả vài item; kiểm tra `ScannedCount >= Count` và phản ánh sự khác biệt.
4. **Phân trang:** gọi một trang với limit nhỏ, lấy `LastEvaluatedKey` rồi dùng `ExclusiveStartKey` cho request cùng điều kiện; kiểm tra không bỏ/đọc trùng dữ liệu khi tập test đứng yên.
5. **Trang rỗng:** dùng filter không match và đủ dữ liệu để có next key; xác nhận API không kết thúc chỉ vì page rỗng.
6. **Tenant isolation:** API không nhận token/cursor tenant khác; xác minh scope được kiểm tra trước Query/Scan.
7. **Throttling/capacity:** với số lượng dữ liệu tăng, đo số trang, RCU, retry và latency; không chạy load test không giới hạn trên bảng production.

Test dùng JUnit 5/Spring Boot Test và DynamoDB Local hoặc LocalStack qua Testcontainers; cần thực sự chạy với bảng/index giống production. Các đoạn code trong bài là hướng dẫn thực hành, **không có nghĩa kiểm thử đã được thực thi**.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| Query bị `ValidationException` | Thiếu điều kiện `partitionKey = value` hoặc đặt thuộc tính thường vào key condition | Chọn đúng PK của bảng/index; dùng filter cho thuộc tính không thuộc key hoặc thiết kế index |
| Query không trả item | Sai tenant, sort prefix, region, endpoint hoặc item không nằm trong GSI | Đối chiếu schema và data, đặc biệt key của GSI |
| Scan trả ít item nhưng đọc nhiều | Filter có độ chọn lọc kém | Đánh giá GSI/lookup/aggregate, theo dõi `ScannedCount` |
| Scan ảnh hưởng latency của API khác | Đọc diện rộng gây tăng read capacity/throttling | Chuyển job offline, giảm tốc độ, phân đoạn có kiểm soát |
| GSI vừa ghi chưa trả kết quả | GSI cập nhật bất đồng bộ | Thiết kế lại luồng cần read-after-write, tránh giả định strong consistency trên GSI |
| Query trang 1 có ít item hơn limit | Filter hoặc giới hạn dữ liệu/trang | Kiểm tra `LastEvaluatedKey` trước khi kết luận hết |
| Cursor trang sau lỗi hoặc sai dữ liệu | Đổi index/key condition/sort khi dùng lại cursor | Ràng buộc token với toàn bộ ngữ cảnh truy vấn |
| Dùng `for (page : query)` làm API chậm | SDK lazy-fetch mọi trang nếu vòng lặp không dừng | Chỉ lấy một page hoặc chủ động đặt ngân sách |
| `ResourceNotFoundException` | Bảng hoặc GSI không tồn tại theo account/region/endpoint | Kiểm tra IaC, tên bảng/index và `describe-table` |
| `AccessDeniedException` | Role thiếu `Query`/`Scan` trên ARN phù hợp | Kiểm tra IAM least privilege, index ARN và role đang chạy |
| Thay đổi kiểu dữ liệu key | Schema mapping không khớp table/index | Đồng bộ Java mapping với schema AWS, migration có kế hoạch |

## 14. Câu hỏi thực hành và tiêu chí hoàn thành

1. Bảng lưu 1 triệu đơn hàng, màn hình hiển thị 20 đơn gần nhất của một khách hàng. Hãy chọn partition key/sort key, viết `KeyConditionExpression`, giải thích vì sao Scan + filter chưa hợp lý.
2. Dịch vụ phải lọc theo `state` 500 lần/giây nhưng `state` không nằm trong khóa. So sánh hai phương án: Scan + Filter so với GSI theo tenant-state-time, gồm chi phí ghi index, độ trễ, tính nhất quán.
3. Tạo bộ dữ liệu 100 item, đo riêng từng trang `Query` và `Scan` bằng `Count`, `ScannedCount`, `ConsumedCapacity`. Ghi lại kết quả thay vì đoán theo số item hiển thị.
4. Viết REST endpoint trả `items` + `nextCursor` đã ký, giới hạn 20 item mỗi request; bảo đảm cursor tenant A không thể dùng ở tenant B.
5. Tạo job Scan kiểm toán dữ liệu cũ, có giới hạn request/giây, checkpoint mỗi segment, retry với backoff và báo số item đã quét sau khi hoàn thành.
6. So sánh cách một chức năng “lọc theo mã nhà và thời gian” được triển khai với DynamoDB GSI, Azure Cosmos DB và Google Cloud Firestore. Xác định phần interface nghiệp vụ có thể dùng chung và phần phụ thuộc provider.

**Tiêu chí tự đánh giá:** người học giải thích được vì sao Query là thao tác theo khóa, Filter không làm giảm dữ liệu đã đọc, Scan cần chủ đích và quota, `Limit` không phải giới hạn item cuối cùng sau filter, và phân trang phải theo `LastEvaluatedKey` của đúng truy vấn.

## Tài liệu tham khảo

- [AWS — Key condition expressions for Query](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.KeyConditionExpressions.html): quy tắc partition/sort key.
- [AWS — Filter expressions for Query](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html): filter sau read và ảnh hưởng read capacity.
- [AWS — Scanning tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html): Scan, Count, ScannedCount, pagination, parallel Scan.
- [AWS — Best practices for querying and scanning](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-query-scan.html): hiệu năng, RCU, giới hạn tốc độ.
- [AWS — Paginating table query results](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html): `LastEvaluatedKey` và `ExclusiveStartKey`.
- [AWS — Global secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html): truy vấn/index projection/consistency.
- [AWS SDK for Java v2 — DynamoDB Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html): repository, Query/Scan và mapping.
- [Spring Cloud AWS — Reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): starter và cấu hình client theo phiên bản.
