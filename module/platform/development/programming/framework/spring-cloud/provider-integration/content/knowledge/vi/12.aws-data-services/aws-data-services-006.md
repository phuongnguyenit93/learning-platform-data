# Giới hạn giao dịch, dung lượng và xử lý throttling

## 1. Bối cảnh và mục tiêu

Trong chương **Dữ liệu AWS** của module **Spring Cloud Provider Integration**, ứng dụng Spring Boot cần tích hợp dịch vụ managed của AWS qua **Spring Cloud AWS (AWSpring)** hoặc **AWS SDK for Java v2**. Amazon DynamoDB giảm công việc vận hành cơ sở dữ liệu, nhưng không có nghĩa ứng dụng được ghi tùy ý số item, giữ item lớn bao nhiêu cũng được hoặc gửi không giới hạn request mà không bị từ chối.

Ba nhóm ràng buộc cần học cùng nhau:

- **Giới hạn dữ liệu:** kích thước một item, request batch, kết quả Query/Scan và giới hạn của index ảnh hưởng cấu trúc entity và đường truy cập.
- **Giới hạn giao dịch:** transaction DynamoDB có quy mô hữu hạn, hoạt động trong phạm vi một tài khoản và Region, có thể thất bại vì điều kiện nghiệp vụ, xung đột đồng thời hoặc thiếu capacity.
- **Throttling:** DynamoDB có thể giới hạn request khi tiêu thụ năng lực đọc/ghi vượt mức phù hợp với bảng/index/partition hoặc quota. Retry cần backoff, idempotency, giới hạn thời gian và theo dõi nguyên nhân.

Bài sử dụng một ví dụ xuyên suốt: dịch vụ đặt chỗ cho bất động sản. Khi xác nhận một lượt đặt, hệ thống phải **tạo bản ghi reservation** và **giảm số suất còn lại của bất động sản** như một đơn vị nghiệp vụ: nếu không còn suất, không được tạo reservation đã xác nhận. Cùng với đó, một đợt khuyến mại có thể tạo lượng ghi đột biến dẫn đến throttling.

Sau bài này, bạn có thể:

1. Nêu và áp dụng giới hạn cốt lõi của DynamoDB: **400 KB/item**, **100 hành động và 4 MB/transaction**, kích thước batch và **1 MB/trang Query/Scan**.
2. Phân biệt atomic item operation, batch operation và DynamoDB transaction; chọn transaction khi invariant trải qua nhiều item.
3. Xây `TransactWriteItems` có điều kiện để tạo reservation và giảm số chỗ còn lại, không để trạng thái cập nhật dở.
4. Đọc ý nghĩa của RCU/WCU và quyết định giữa on-demand, provisioned, index và access pattern phù hợp.
5. Xử lý throttling bằng retry có exponential backoff + jitter, giới hạn đồng thời và bảo đảm không tạo reservation trùng.
6. Cấu hình Spring Boot, IAM/role, endpoint DynamoDB Local và kiểm thử cả logic nghiệp vụ lẫn tình huống quá tải.

> **Phạm vi:** DynamoDB, RCU/WCU, transaction và throttling được trình bày theo semantics của AWS. Dịch vụ Azure Cosmos DB và Google Cloud Firestore cũng có quota, giao dịch và retry, nhưng giới hạn và cơ chế lập chỉ mục khác. Khi xây ứng dụng đa cloud, tránh áp dụng trực tiếp giới hạn DynamoDB lên adapter của provider khác.

## 2. Phân biệt item operation, batch và transaction

Từ góc nhìn application, **một write thành công** và **một nghiệp vụ nhiều write thành công hoàn toàn** không giống nhau.

| Cơ chế | Mục đích | Bảo đảm đáng chú ý | Không nên giả định |
| --- | --- | --- | --- |
| `PutItem`, `UpdateItem`, `DeleteItem` | Ghi/xóa một item theo key | Một thao tác item có tính atomic; hỗ trợ `ConditionExpression` | Nhiều thao tác riêng lẻ tự trở thành transaction |
| `BatchWriteItem` | Gửi nhiều Put/Delete hiệu quả hơn | Một request tối đa 25 thao tác Put/Delete | Không đảm bảo cả batch atomic; có thể trả `UnprocessedItems` |
| `BatchGetItem` | Đọc nhiều item theo key | Một request tối đa 100 item, có thể trả `UnprocessedKeys` | Không có giao dịch read snapshot; không phải Query tùy ý |
| `TransactWriteItems` | Put/Update/Delete/ConditionCheck nhiều item atomically | Hoặc tất cả hành động hợp lệ đều được áp dụng, hoặc không hành động nào được áp dụng | Không vượt giới hạn transaction; không bao trùm S3/SQS |
| `TransactGetItems` | Đọc tập item theo transactional read | Tập kết quả đọc theo ngữ nghĩa transaction trong cùng phạm vi hỗ trợ | Không phải giải pháp truy vấn tùy ý bằng filter/GSI |

Một giao dịch chỉ cần thiết nếu có **invariant**: ví dụ "tạo reservation được xác nhận thì số chỗ còn lại phải giảm đúng một". Đối với việc ghi log độc lập hoặc nhập dữ liệu số lượng lớn có thể retry từng item, batch thường phù hợp hơn, miễn ứng dụng xử lý thành công từng phần.

~~~mermaid
flowchart TD
    A["Nghiệp vụ ghi dữ liệu"] --> B{"Chỉ một item?"}
    B -->|"Có"| C["Put/Update/Delete<br/>+ ConditionExpression nếu cần"]
    B -->|"Không"| D{"Các item phải cùng thành công?"}
    D -->|"Có"| E["TransactWriteItems<br/>+ điều kiện nghiệp vụ"]
    D -->|"Không"| F["BatchWriteItem / queue worker<br/>+ xử lý UnprocessedItems"]
    E --> G["Đánh giá giới hạn 100 actions,<br/>4 MB và contention"]
    F --> H["Retry có backoff,<br/>checkpoint và idempotency"]
~~~

## 3. Giới hạn dữ liệu phải nhớ trước khi lập schema

### 3.1. Bảng giới hạn thực hành

| Hạng mục | Giới hạn/ràng buộc đáng nhớ | Hệ quả thiết kế |
| --- | --- | --- |
| Kích thước **một item** | Tối đa **400 KB**, bao gồm tên và giá trị thuộc tính theo cách DynamoDB tính kích thước | Không nhét ảnh, file, JSON lớn vô hạn vào item; lưu blob ở S3 |
| Giá trị partition key | Tối đa **2.048 byte** | Validate kích thước key; tính theo byte UTF-8 |
| Giá trị sort key | Tối đa **1.024 byte** | Tránh ghép chuỗi khóa quá dài hoặc dữ liệu người dùng không kiểm soát |
| `Query` / `Scan` | Một lần gọi xử lý tối đa **1 MB** dữ liệu trước filter/projection, hoặc dừng theo `Limit` | Dùng `LastEvaluatedKey` để phân trang |
| `BatchWriteItem` | Tối đa **25** Put/Delete và **16 MB** trong một request; từng item vẫn tối đa 400 KB | Chia lô và xử lý `UnprocessedItems` |
| `BatchGetItem` | Tối đa **100 item** hoặc **16 MB** mỗi request; một số key có thể chưa được xử lý | Chia nhóm và xử lý `UnprocessedKeys` |
| `TransactWriteItems` | Tối đa **100 hành động** trên **những item khác nhau**, tổng các item trong transaction không quá **4 MB** | Không gộp nguyên batch nhập liệu lớn thành một transaction |
| `TransactGetItems` | Tối đa **100 item**, tổng dữ liệu đọc không quá **4 MB** | Chỉ dùng cho tập key hữu hạn |
| Bảng có **LSI** | Item collection cho một partition key chịu giới hạn **10 GB** | Cẩn trọng khi cùng một partition key có rất nhiều item |
| GSI | Chỉ đọc **eventually consistent**; index tăng chi phí lưu trữ/ghi | Không lấy GSI làm nguồn kiểm tra điều kiện cấp phát suất còn lại tức thì |

Những con số trên là các ràng buộc API/data model cốt lõi thường gặp. Các **quota tài khoản, số lượng bảng/index, throughput, kích thước transaction, khả năng on-demand/provisioned và giới hạn theo Region** có thể được AWS cập nhật. Kiểm tra tài liệu quota mới nhất và **Service Quotas của chính tài khoản** trước khi đặt ngưỡng vận hành; đừng tự gán một con số throughput cố định cho mọi bảng và Region.

### 3.2. Item lớn gây tác động dây chuyền

Ví dụ một item reservation chứa:

~~~json
{
  "tenantId": "tenant-a",
  "reservationId": "res-1001",
  "state": "CONFIRMED",
  "guestCount": 4,
  "contractPdfBase64": "..."
}
~~~

Nếu nhúng cả hợp đồng PDF hoặc ảnh chụp dạng Base64:

- Item dễ tiến gần hoặc vượt giới hạn 400 KB.
- Mỗi read/write tiêu thụ thêm read/write capacity; index có projection rộng làm tăng dữ liệu nhân bản.
- Transaction 4 MB chứa được ít item hơn, tăng độ trễ và nguy cơ bị từ chối.
- Trả dữ liệu qua API tạo payload nặng và khó phân trang.

**Thiết kế thích hợp hơn:** lưu file/hợp đồng ở **Amazon S3** với quyền truy cập phù hợp, trong DynamoDB chỉ giữ `s3Key`, `contentType`, `checksum`, `fileSize` và metadata cần thiết. Đây là hai dịch vụ riêng: transaction DynamoDB không atomically commit object S3 cùng item; quy trình nghiệp vụ cần idempotency, trạng thái upload hoặc cơ chế dọn dữ liệu rác khi thất bại.

### 3.3. Giới hạn item collection với LSI

Nếu bảng có **Local Secondary Index**, tổng kích thước item collection cho một partition key bị giới hạn 10 GB theo quy tắc DynamoDB. Một `tenantId` cực lớn làm partition key chung cho hàng triệu bản ghi có thể khó phát triển, dù tổng bảng không có một ngưỡng dữ liệu nhỏ cố định. Phải xem lại access pattern, index và cách chia khóa nếu tenant có thể tăng rất lớn. Không chọn một khóa nóng rồi trông chờ thêm GSI sẽ tự giải quyết mọi giới hạn.

### 3.4. Khóa và kích thước byte

`String.length()` trong Java đếm UTF-16 code unit, không phải byte UTF-8. Một partition key chứa tiếng Việt có dấu hoặc emoji có thể dùng nhiều byte cho một ký tự hiển thị. Cần validate bằng `value.getBytes(StandardCharsets.UTF_8).length` nếu key lấy từ dữ liệu biến đổi; còn ID nghiệp vụ nên dùng định dạng ổn định và ngắn.

## 4. Giới hạn và tính chất của transaction

### 4.1. Transaction DynamoDB bảo đảm gì?

`TransactWriteItems` là một request ghi nhiều hành động `Put`, `Update`, `Delete` hoặc `ConditionCheck` với thuộc tính **all-or-nothing**. DynamoDB kiểm tra các điều kiện và chỉ commit khi toàn bộ transaction hợp lệ. `TransactGetItems` đọc nhiều item theo tập key dưới ngữ nghĩa transaction phù hợp.

Các ranh giới quan trọng:

1. Một transaction tối đa **100 hành động**, tối đa **4 MB dữ liệu item** theo quy tắc API.
2. Các item thuộc **cùng tài khoản AWS và cùng Region**; có thể nằm ở nhiều bảng khác nhau trong phạm vi này.
3. **Không đặt hai hành động trên cùng một item trong một `TransactWriteItems`**, ví dụ vừa `ConditionCheck` vừa `Update` đúng item đó. Thay bằng `ConditionExpression` ngay trong `Update`.
4. Transaction không trực tiếp sửa S3, SQS, RDS, Azure hay Google Cloud; nó bảo đảm atomicity trong phạm vi DynamoDB được hỗ trợ.
5. Transaction có thể thất bại vì condition sai, validation, item size, insufficient capacity, throttling hoặc **transaction conflict** khi các write cùng tranh chấp item.
6. **GSI và Streams được cập nhật bất đồng bộ** so với các write trên bảng. Transaction commit không có nghĩa mọi Query qua GSI ở thời điểm kế tiếp lập tức nhìn thấy toàn bộ thay đổi.

Đối với transaction nhiều bảng/item, **khóa chính của mỗi item phải xác định rõ**; không dùng `Scan` hoặc một GSI Query để chọn những item bất kỳ rồi giả định có thể khóa toàn bộ tập đó bằng một transaction không giới hạn.

### 4.2. Transaction và batch không thay thế nhau

Giả sử import 2.000 log item độc lập: tạo 20 transaction 100 item có thể tăng chi phí và rủi ro contention không cần thiết. Có thể dùng lô 25 item, xử lý `UnprocessedItems`, checkpoint theo message ID và retry. Ngược lại, nếu phải giảm inventory **và** tạo reservation cùng lúc, hai Put/Update riêng hoặc `BatchWriteItem` không bảo đảm invariant; transaction là lựa chọn thích hợp.

| Tình huống | Cơ chế phù hợp | Vì sao |
| --- | --- | --- |
| Nhập 5.000 sự kiện độc lập | Batch/worker | Có thể xử lý từng phần và retry |
| Tạo mới reservation không được trùng key | `PutItem` có `attribute_not_exists` | Một item, đủ atomic với condition |
| Tạo reservation và trừ số chỗ | `TransactWriteItems` | Invariant trên hai item |
| Kiểm tra tồn kho và cấp phát từ nhiều kho | Transaction nếu nằm trong giới hạn, hoặc thiết kế nghiệp vụ khác | Tránh số tồn kho âm |
| Cập nhật nhiều hệ thống gồm DynamoDB + S3 + SQS | Outbox/saga/idempotency | Transaction DynamoDB không phủ các hệ thống ngoài |

### 4.3. Chi phí transaction và contention

Transactional read/write thường tiêu thụ **nhiều capacity hơn** thao tác không transactional với cùng lượng dữ liệu: mô hình transactional hoạt động theo cơ chế chuẩn bị và commit, được tính tương ứng trong đơn vị đọc/ghi. Vì vậy không bật transaction cho mọi CRUD chỉ để “an toàn hơn”. Dùng transaction ở các invariant cần thiết, còn thao tác một item nên tận dụng conditional write.

Các transaction cạnh tranh ghi cùng một item `inventoryKey` sẽ tranh chấp. Khi xung đột xảy ra, một transaction có thể bị hủy; retry toàn bộ transaction chỉ phù hợp nếu **điều kiện nghiệp vụ vẫn đúng**, token/key đủ ổn định và có giới hạn thời gian. Nếu một điểm nóng tập trung quá nhiều request, tăng retry có thể làm tắc nghẽn nặng hơn.

## 5. Bài toán thực hành: tạo reservation và giảm inventory atomically

### 5.1. Thiết kế hai bảng

Ví dụ dùng hai bảng trong cùng AWS account/Region:

**`reservation_record`**

~~~text
tenantId (PK, String)  | sortKey (SK, String)                  | state      | reservationId
tenant-a               | RES#2026-11-24T08:00:00.000Z#res-1   | CONFIRMED  | res-1
~~~

**`property_inventory`**

~~~text
inventoryKey (PK, String)            | available (Number)
tenant-a#house-99#2026-11-24         | 3
~~~

Ta chọn inventory theo **một bất động sản và một ngày**, giả sử mỗi suất là một booking hợp lệ cùng ngày. Trong sản phẩm thật, reservation nhiều đêm phải có cơ chế cho từng ngày/khoảng tồn, transaction chạm nhiều inventory item và kiểm tra lại giới hạn 100 hành động, 4 MB. Không áp dụng ví dụ một ngày cho nghiệp vụ đặt nhiều đêm mà bỏ qua xung đột giữa các ngày.

### 5.2. Tạo bảng trong DynamoDB Local

DynamoDB Local phục vụ bài tập để không ghi dữ liệu vào tài khoản AWS:

~~~bash
docker run --rm --name dynamodb-local -p 8000:8000 amazon/dynamodb-local:latest
~~~

Trong terminal phát triển, đặt credentials **giả** và region:

~~~bash
export AWS_ACCESS_KEY_ID=local
export AWS_SECRET_ACCESS_KEY=local
export AWS_DEFAULT_REGION=ap-southeast-1
~~~

Tạo bảng reservation:

~~~bash
aws dynamodb create-table \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --attribute-definitions \
    AttributeName=tenantId,AttributeType=S \
    AttributeName=sortKey,AttributeType=S \
  --key-schema \
    AttributeName=tenantId,KeyType=HASH \
    AttributeName=sortKey,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
~~~

Tạo bảng inventory:

~~~bash
aws dynamodb create-table \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name property_inventory \
  --attribute-definitions AttributeName=inventoryKey,AttributeType=S \
  --key-schema AttributeName=inventoryKey,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
~~~

Seed tồn kho:

~~~bash
aws dynamodb put-item \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name property_inventory \
  --item '{
    "inventoryKey":{"S":"tenant-a#house-99#2026-11-24"},
    "available":{"N":"3"}
  }' \
  --condition-expression 'attribute_not_exists(inventoryKey)'
~~~

Chạy lệnh seed một lần; nếu item đã có thì condition sẽ từ chối, không tự ghi đè số chỗ của bài test trước. Khi làm CI nên dùng key độc nhất cho mỗi test hoặc tạo bảng riêng bằng Testcontainers và cleanup.

### 5.3. Transaction dùng AWS SDK v2

Trong ứng dụng Spring Boot, có thể inject `DynamoDbClient` do AWSpring starter tương thích auto-configure hoặc tự tạo bean AWS SDK v2. Ví dụ sau dùng API cấp thấp để biểu diễn **chính xác điều kiện ghi**:

~~~java
import java.util.Map;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.Put;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;
import software.amazon.awssdk.services.dynamodb.model.TransactWriteItem;
import software.amazon.awssdk.services.dynamodb.model.TransactWriteItemsRequest;
import software.amazon.awssdk.services.dynamodb.model.Update;

@Service
public class ReservationBookingService {
    private final DynamoDbClient client;

    public ReservationBookingService(DynamoDbClient client) {
        this.client = client;
    }

    public void bookOneSlot(
            String tenantId,
            String propertyId,
            String stayDate,
            String sortKey,
            String reservationId,
            String idempotencyToken) {

        String inventoryKey =
                tenantId + "#" + propertyId + "#" + stayDate;

        // 1. Chỉ tạo item nếu full primary key chưa có.
        TransactWriteItem createReservation =
                TransactWriteItem.builder()
                        .put(Put.builder()
                                .tableName("reservation_record")
                                .item(Map.of(
                                        "tenantId", s(tenantId),
                                        "sortKey", s(sortKey),
                                        "reservationId", s(reservationId),
                                        "state", s("CONFIRMED")))
                                .conditionExpression(
                                        "attribute_not_exists(#pk)")
                                .expressionAttributeNames(
                                        Map.of("#pk", "tenantId"))
                                .build())
                        .build();

        // 2. Chỉ trừ tồn khi item inventory đã có và còn suất.
        TransactWriteItem decrementInventory =
                TransactWriteItem.builder()
                        .update(Update.builder()
                                .tableName("property_inventory")
                                .key(Map.of(
                                        "inventoryKey", s(inventoryKey)))
                                .updateExpression(
                                        "SET #available = #available - :one")
                                .conditionExpression(
                                        "attribute_exists(inventoryKey) "
                                        + "AND #available >= :one")
                                .expressionAttributeNames(
                                        Map.of("#available", "available"))
                                .expressionAttributeValues(
                                        Map.of(":one", n(1)))
                                .build())
                        .build();

        client.transactWriteItems(
                TransactWriteItemsRequest.builder()
                        .transactItems(
                                createReservation, decrementInventory)
                        .clientRequestToken(idempotencyToken)
                        .returnConsumedCapacity(
                                ReturnConsumedCapacity.TOTAL)
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

**Cách transaction bảo vệ dữ liệu:**

- Nếu `reservation_record` đã có item **cùng đầy đủ `tenantId + sortKey`**, condition tạo mới sai: **không tạo reservation và không giảm inventory**.
- Nếu `available = 0`, điều kiện inventory sai: **không tạo reservation và không trừ tồn**.
- Nếu cả hai điều kiện đúng, reservation được tạo và inventory giảm một theo transaction.
- Nếu transaction bị hủy do xung đột/capacity, phải phân biệt nguyên nhân; không coi mọi lỗi transaction đều là “hết chỗ”.
- `sortKey` và `idempotencyToken` phải ổn định cho **cùng một ý định đặt chỗ**; không tạo timestamp mới ở mỗi lần thử.

**Điểm đặc biệt:** `idempotencyToken` là `ClientRequestToken` của transaction AWS, không phải ID bất kỳ dài vô hạn. Token phải đáp ứng điều kiện chiều dài/ký tự của API. DynamoDB hỗ trợ idempotency cho cùng request/token trong **cửa sổ 10 phút** tính từ lần request gốc hoàn tất. Nếu cùng token nhưng tham số request thay đổi trong cửa sổ đó, có thể nhận `IdempotentParameterMismatchException`. Sau cửa sổ, không được xem token là cơ chế chống lặp vĩnh viễn; hãy dùng một `reservationId`/full key ổn định và idempotency record theo nhu cầu nghiệp vụ.

### 5.4. Cấu hình Spring Boot và danh tính

Với phiên bản Spring Cloud AWS cung cấp starter DynamoDB và các property dưới đây:

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

~~~yaml
# application-local.yml - môi trường thử nghiệm
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        endpoint: http://localhost:8000
~~~

Dùng **AWSpring BOM phù hợp với Spring Boot** nếu tích hợp bằng `io.awspring.cloud:spring-cloud-aws-starter-dynamodb`. Khi cấu hình SDK v2 thuần, dùng `software.amazon.awssdk:dynamodb` và tự tạo `DynamoDbClient` với region, credential provider chain, `endpointOverride` cho local; property AWSpring không tự tác động lên client do ứng dụng tự khởi tạo.

Không đưa access key/secret key thật vào YAML. Với ECS/EKS/EC2, ưu tiên IAM role/workload identity và cấp quyền DynamoDB đúng bảng, action cho transaction. Cũng không đặt mật khẩu, token hoặc secret cấu hình trong bảng reservation; dùng Secrets Manager/Parameter Store hoặc giải pháp quản lý secret phù hợp.

### 5.5. Giao dịch nhiều đêm và vượt giới hạn

Với reservation 120 đêm, nếu phải cập nhật inventory của **từng ngày** cộng một item reservation, transaction đã vượt **100 hành động**. Không thể khắc phục bằng việc tăng số lượng item trong request. Các phương án cần phân tích:

- Giảm phạm vi invariant: chia lịch thành các bucket/sổ tồn phù hợp và kiểm chứng tính đúng đắn.
- Dùng workflow giữ chỗ `PENDING` / `CONFIRMING`, điều phối nhiều giao dịch nhỏ với compensation và idempotency.
- Thay cách biểu diễn tồn kho để số item chạm trong một transaction không vượt giới hạn.
- Nếu không thể bảo đảm toàn bộ booking atomically bằng thiết kế hiện tại, phải công khai tính chất eventual/process state ở tầng nghiệp vụ và tránh xác nhận sớm.

Chia một transaction 120 item thành hai transaction 60 item rồi gọi nối tiếp **không tự biến thành một transaction 120 item**: sau transaction thứ nhất, transaction thứ hai có thể thất bại và để lại trạng thái trung gian.

## 6. Capacity, RCU/WCU và vì sao vẫn bị throttling

### 6.1. Cách hình dung đơn vị đọc/ghi

DynamoDB dùng các đơn vị năng lực để đo phần việc phục vụ request:

- **Read Capacity Unit (RCU):** với mô hình tính tiêu chuẩn, một strong read của item đến 4 KB tương đương 1 RCU; eventual read cho cùng lượng dữ liệu tiêu thụ khoảng 0,5 RCU; transactional read tương đương khoảng 2 RCU.
- **Write Capacity Unit (WCU):** ghi tiêu chuẩn một item đến 1 KB tương đương 1 WCU; kích thước được làm tròn lên theo mỗi 1 KB. Transactional write có thể tính gấp đôi năng lực write tiêu chuẩn cho item cùng kích thước.
- **GSI:** ghi item có liên quan GSI có thể làm phát sinh chi phí và write capacity cho từng index; projection và cách cập nhật key/index ảnh hưởng tổng chi phí.
- **On-demand:** tính tiền theo request units tiêu thụ theo mô hình pricing hiện hành, không cần tự cấu hình throughput như provisioned nhưng vẫn chịu quota và giới hạn phân phối tải.
- **Provisioned:** cấu hình read/write capacity có thể điều chỉnh/auto scaling; vượt năng lực cấp phát có thể dẫn tới throttling.

Ví dụ minh họa **một item 5 KB** (bỏ qua index/network/overhead khác):

| Thao tác trên item 5 KB | Năng lực đọc/ghi tương đương trong mô hình tiêu chuẩn |
| --- | --- |
| Ghi tiêu chuẩn | `ceil(5 / 1) = 5` WCU |
| Ghi transactional | Khoảng `10` WCU |
| Strong read | `ceil(5 / 4) = 2` RCU |
| Eventual read | Khoảng `1` RCU |
| Transactional read | Khoảng `4` RCU |

Những con số trên giúp hiểu xu hướng, **không phải hóa đơn AWS**. Read/write pricing cụ thể còn phụ thuộc Region, loại bảng, chế độ capacity, index, backup, data transfer và các tùy chọn dịch vụ. Với transaction nhiều item, tính từng item và account for các index liên quan; đừng chỉ nhìn kích thước JSON response.

### 6.2. Throttling có thể xuất hiện từ đâu?

~~~mermaid
flowchart TD
    A["Request tăng đột biến"] --> B{"Nguyên nhân hạn chế?"}
    B --> C["Bảng hoặc GSI<br/>thiếu capacity / quota"]
    B --> D["Partition key quá nóng<br/>traffic dồn một vị trí"]
    B --> E["Transaction xung đột<br/>cùng item inventory"]
    B --> F["Account/Region quota<br/>hoặc vấn đề tạm thời"]
    C --> G["Đo metric và capacity"]
    D --> H["Điều chỉnh key / workload"]
    E --> I["Condition, contention control"]
    F --> J["Kiểm tra quota / retry"]
~~~

Các nguồn phổ biến:

1. **Provisioned capacity:** mức read/write được cấp thấp hơn nhu cầu thực, hoặc auto scaling chưa theo kịp một đợt tăng tải.
2. **On-demand hoặc account quota:** DynamoDB tự quản lý capacity, nhưng không có nghĩa request rate vô hạn; có thể chịu hạn mức của bảng/tài khoản hoặc thay đổi lưu lượng quá nhanh.
3. **Hot partition/hot item:** lượng request dồn vào một partition key hoặc một item inventory. Năng lực tổng của bảng chưa dùng hết vẫn có thể có giới hạn cục bộ.
4. **GSI throttling:** index có key nóng hoặc capacity không phù hợp; ghi bảng gốc làm cập nhật index, có thể bị ảnh hưởng bởi nghẽn index.
5. **Transaction conflict:** nhiều transaction cùng sửa một inventory item, dẫn đến tranh chấp; đây là vấn đề concurrency thường cần xử lý khác với throttling thuần.

**Nguyên tắc:** tăng provisioned throughput có thể hữu ích khi thiếu capacity toàn bảng, nhưng không tự khắc phục mọi hot item hay transaction conflict. Phải đọc **nguyên nhân cụ thể trong exception, thông tin throttling reason khi SDK/API có hỗ trợ và CloudWatch metrics** trước khi thay kiến trúc.

### 6.3. Chọn key, index và chia tải

Giả sử tất cả đặt chỗ của một bất động sản cùng update item:

~~~text
inventoryKey = "tenant-a#house-99#2026-11-24"
~~~

Khi có một đợt flash sale, mọi transaction đều tranh chấp item này. Các phương án phụ thuộc nghiệp vụ:

- Giới hạn số request đồng thời bằng queue/worker cho từng property/date, xác nhận theo thứ tự nghiệp vụ.
- Dùng reservation hold/ticket hoặc inventory shard/bucket, kèm cơ chế tổng hợp/đảm bảo không bán quá số lượng.
- Đảm bảo idempotency và condition để kết quả không âm; retry quá nhanh có thể làm tăng tranh chấp.
- Đo throughput trên đúng item/key và xem lại cách phân phối traffic; đừng shard tùy tiện khi còn ít dữ liệu hoặc khi cần exact consistency tức thì.
- Với API chỉ đọc, dùng Query theo key/index phù hợp và cache đúng mức; tránh Scan toàn bảng trong request có tần suất lớn.

## 7. Xử lý throttling có kiểm soát

### 7.1. Phân loại lỗi trước khi retry

| Lỗi / kết quả | Ý nghĩa thường gặp | Cách phản ứng |
| --- | --- | --- |
| `ProvisionedThroughputExceededException` | Vượt throughput cấp phát hoặc giới hạn tài nguyên liên quan | Backoff/jitter, điều chỉnh capacity/tải sau khi đo |
| `ThrottlingException` hoặc `RequestLimitExceeded` | Throttling/quota ở mức request hoặc tài khoản | Retry có giới hạn, xem quota và các throttling reasons |
| `TransactionCanceledException` | Một phần transaction không thỏa điều kiện, bị throttling hoặc xung đột | Xem cancellation reasons; **không** retry mù nếu là business conflict |
| `TransactionConflictException` hoặc cancellation reason conflict | Giao dịch cạnh tranh trên item | Backoff, serialization/giảm cạnh tranh, xác minh lại invariant |
| `ConditionalCheckFailedException` | Condition ghi một item sai | Xử lý nghiệp vụ, không tự retry vô hạn |
| `ValidationException` | Key, payload, quota/hình dạng request sai | Sửa request hoặc thiết kế; retry nguyên request không giúp |
| `ResourceNotFoundException` | Sai bảng/index, Region, endpoint hoặc chưa tạo tài nguyên | Sửa cấu hình, không xem như throttling |
| Timeout/`SdkClientException` | Có thể không rõ server đã nhận/commit write | Dựa vào idempotency và đối soát theo key, không đoán thất bại |

Không phải tất cả lỗi 4xx đều không nên retry: throttling thường có thể retry, còn validation/condition sai thường không. Ngược lại, không phải mọi timeout đều chứng minh write chưa chạy. **Một chính sách retry tốt gắn với semantics của operation và khả năng biết kết quả**, chứ không chỉ dựa trên tên exception.

### 7.2. Exponential backoff và jitter

Nếu request bị throttled, gửi lại ngay lập tức từ nhiều client làm tình hình xấu đi. Dùng exponential backoff có jitter và giới hạn nỗ lực.

Với base delay `b` và lần thử `k`, một cách tính *full jitter*:

\[
d_k \sim U\left(0,\;\min(d_{\max},\,b\cdot 2^k)\right)
\]

Ví dụ đặt `b = 100 ms`, `d_max = 5 s`, số lần thử bổ sung tối đa 4. Khoảng chờ thực tế được lấy ngẫu nhiên trong miền phù hợp; các số này chỉ là cấu hình minh họa, cần đo theo SLO và đặc điểm tải.

~~~text
Gọi lần đầu ────────────────────────────────┐
Throttling                                  │
Chờ ngẫu nhiên trong [0, 100 ms] ──────────┤ lần thử lại 1
Throttling                                  │
Chờ ngẫu nhiên trong [0, 200 ms] ──────────┤ lần thử lại 2
Throttling                                  │
Chờ ngẫu nhiên trong [0, 400 ms] ──────────┤ lần thử lại 3
... tối đa số lần/độ trễ đã cấu hình ...     │
                                           └── thành công hoặc trả lỗi
~~~

Trong AWS SDK for Java v2, SDK đã có **retry strategy**. Cấu hình ở client level là lựa chọn mặc định cho lỗi retryable; không thêm một vòng retry của service chồng lên SDK một cách vô ý. Kết hợp nhiều lớp retry có thể nhân số request khi hệ thống đang quá tải.

### 7.3. Ví dụ cấu hình retry ở AWS SDK v2

Ví dụ cấu hình bằng API `StandardRetryStrategy` có trong những phiên bản AWS SDK v2 hỗ trợ retry API này. Với phiên bản cũ hơn, kiểm tra API `RetryPolicy` tương ứng thay vì sao chép code không tương thích.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.retries.StandardRetryStrategy;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Configuration
class DynamoDbClientConfiguration {
    @Bean
    DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .overrideConfiguration(config -> config
                        .retryStrategy(StandardRetryStrategy.builder()
                                .maxAttempts(4)
                                .build()))
                .build();
    }
}
~~~

**Lưu ý API/phiên bản:** phương thức `retryStrategy` và `StandardRetryStrategy` thuộc API retry mới của AWS SDK v2; với phiên bản cũ hơn, cần đối chiếu `RetryPolicy` và nâng cấp có kế hoạch. `maxAttempts(4)` tính **cả lần gọi đầu tiên**, nghĩa là tối đa ba lần thử lại. Standard retry strategy đã triển khai backoff/jitter cho lỗi retryable. Khi dự án sử dụng AWSpring starter tự tạo client, ưu tiên cấu hình/customizer mà phiên bản AWSpring hỗ trợ; không khai báo trùng bean `DynamoDbClient` chỉ để đổi retry.

Nếu cần kiểm soát rõ backoff, có thể cấu hình `StandardRetryStrategy`/`AdaptiveRetryStrategy` theo SDK version, và đo lại. **Adaptive retry** có rate limiting phía client để đáp ứng throttling, phù hợp khi client được phân tách theo scope throttling; không mặc nhiên chia một client adaptive duy nhất cho nhiều bảng bị quota khác nhau.

### 7.4. Giảm tải upstream cùng với retry

Retry chỉ xử lý **tạm thời**; nếu tốc độ gửi vào lớn hơn năng lực phục vụ ổn định, hệ thống cần quản lý nguồn:

- Giới hạn **in-flight requests** bằng semaphore hoặc thread pool có kích thước hợp lý.
- Đưa công việc nhập liệu/đồng bộ sang **SQS** và worker với giới hạn đồng thời, visibility timeout, DLQ và idempotency.
- Chọn batch size và tần suất phù hợp, kiểm tra `UnprocessedItems`/`UnprocessedKeys`, retry chỉ phần chưa xử lý.
- Có **backpressure** từ API (HTTP `429`/`503` và `Retry-After` khi contract cho phép).
- Theo dõi queue lag và latency; tăng worker không đúng lúc có thể khuếch đại nghẽn.
- Phân biệt request tương tác cần phản hồi ngay và công việc batch có thể chờ lâu hơn.

Không đặt sleep kéo dài tùy tiện trong controller đang giữ kết nối; ưu tiên SDK retry có hạn mức và xử lý công việc bất đồng bộ khi phù hợp.

## 8. Idempotency và kết quả giao dịch không rõ ràng

### 8.1. Timeout không khẳng định write thất bại

~~~mermaid
sequenceDiagram
    participant API as Spring Boot
    participant DB as DynamoDB
    API->>DB: TransactWriteItems(token=K)
    DB->>DB: Commit thành công
    Note over API,DB: Response thất lạc / timeout phía API
    API->>DB: Retry cùng token K, cùng request
    DB-->>API: Kết quả idempotent trong cửa sổ API hỗ trợ
~~~

Nếu response bị mất sau commit, client không biết liệu inventory đã giảm hay chưa. Gửi **một transaction khác với reservation key hoặc token mới** có thể trừ kho thêm lần nữa. Vì vậy:

1. Gán một `reservationId` và `sortKey` ổn định cho **một yêu cầu nghiệp vụ**.
2. Tạo `ClientRequestToken` ổn định theo yêu cầu (thỏa length/charset API), không theo mỗi network attempt.
3. Dùng conditional Put cho reservation trong cùng transaction để chống tạo trùng.
4. Nếu retry vượt cửa sổ idempotency hoặc nhận conflict, đọc lại reservation bằng **full primary key** và đối soát kết quả, không tự trừ kho thêm.
5. Thiết kế lớp API phân biệt “đã hoàn tất”, “đang xử lý”, “xung đột” và “chưa rõ kết quả” khi cần.

`ClientRequestToken` hữu ích nhưng **không thay thế một sổ idempotency của nghiệp vụ tồn tại lâu dài** khi hệ thống cần chống lặp nhiều giờ/ngày.

### 8.2. Tránh lỗi retry không idempotent

Ví dụ thao tác raw `UpdateItem` chỉ có biểu thức `SET available = available - :one` mà không có condition/key bảo vệ nghiệp vụ. Nếu request đầu đã chạy nhưng response thất lạc, lặp lại request sẽ giảm tồn kho **hai lần**.

Transaction với conditional Put reservation sử dụng full key ổn định là một lớp bảo vệ: nếu reservation đã được tạo, lần transaction mới với cùng key không thể giảm thêm inventory vì condition Put thất bại và transaction bị hủy. Cần xác minh reservation thuộc **cùng** ý định nghiệp vụ trước khi trả kết quả idempotent; không xem mọi `TransactionCanceledException` là thành công.

### 8.3. Retry và xung đột đồng thời

Hai khách đặt suất cuối cùng:

~~~text
Inventory available = 1
Request A: transaction Put(res-A) + Update inventory if available >= 1
Request B: transaction Put(res-B) + Update inventory if available >= 1

Kết quả được chấp nhận về mặt nghiệp vụ:
  - A thành công, B bị từ chối; available = 0; chỉ res-A tồn tại
  - hoặc B thành công, A bị từ chối; available = 0; chỉ res-B tồn tại

Kết quả không được phép:
  - Cả A và B đều CONFIRMED khi available ban đầu là 1
  - available âm hoặc reservation tồn tại mà tồn kho không giảm
~~~

Ở mức transaction, một request có thể gặp **transaction conflict** trước khi condition được đánh giá lại. Nếu thử lại sau backoff, cần dùng chính reservation key/token cũ và vẫn giữ điều kiện `available >= 1`. Khi availability đã hết, trả thông báo hết suất; không retry liên tục cho đến khi “thắng”.

## 9. Quan sát hệ thống: biết vì sao bị throttling

### 9.1. Metric nên theo dõi

Các metric/biểu đồ CloudWatch cần xem xét theo bảng/index và luồng nghiệp vụ:

| Nhóm | Ví dụ quan sát | Câu hỏi được trả lời |
| --- | --- | --- |
| Năng lực đọc/ghi | `ConsumedReadCapacityUnits`, `ConsumedWriteCapacityUnits` | Nhu cầu thực tăng ở đâu? |
| Throttling | `ReadThrottleEvents`, `WriteThrottleEvents`, `ThrottledRequests` khi có dữ liệu/được hỗ trợ | Bảng hay GSI đang giới hạn request? |
| Độ trễ | `SuccessfulRequestLatency` và latency end-to-end của service | Chậm do DB, retry hay ứng dụng? |
| Lỗi | `SystemErrors`, `UserErrors`, loại exception | Lỗi hạ tầng hay lỗi request/nghiệp vụ? |
| Nghiệp vụ | `booking_conflict`, `inventory_empty`, `transaction_cancelled` | Đụng độ khi đặt suất cuối có tăng không? |
| Hàng đợi | queue depth, age of oldest message, DLQ | Retry/backlog có tăng theo đợt tải không? |

Phân tích **cùng lúc** throughput, retry count, transaction conflict, latency, consumed capacity và tỉ lệ thành công. Một spike throttling ngắn có thể hồi phục với SDK retry; throttling kéo dài cần điều tra capacity, access pattern hoặc workload.

### 9.2. Tránh nhầm symptom và root cause

- Transaction bị hủy vì `ConditionalCheckFailed`: thường là **xung đột nghiệp vụ**, không chữa bằng tăng WCU.
- Transaction bị hủy vì thiếu throughput: cần **capacity/backoff** và kiểm tra index/hot key.
- Nhiều client cùng update một item `inventoryKey`: có thể là **contention** cần serialization hoặc tái thiết kế inventory.
- GSI write throttling: có thể làm ảnh hưởng ghi bảng dù provisioned capacity bảng chưa hết.
- Ứng dụng tự retry nhiều lớp: làm tổng request vượt xa lượng request người dùng gửi; cần đo retry amplification.
- Scan toàn bảng trong giờ cao điểm: có thể tiêu thụ capacity và gây throttling cho workload online, dù Scan chỉ trả vài item sau filter.

### 9.3. Nhật ký an toàn

Nên log operation, correlation/request ID, bảng/index (trong phạm vi được phép), latency, số retry, loại lỗi, thông tin throttling reason và trạng thái nghiệp vụ. Tránh log AWS credentials, session token, toàn bộ DynamoDB item có dữ liệu cá nhân hoặc cursor mang key tenant. Hệ thống multi-tenant vẫn phải xác thực tenant ở tầng service; DynamoDB partition key **không tự thực thi quyền tenant**.

## 10. IAM, bảo mật và vận hành nhiều môi trường

### 10.1. Least privilege cho transaction

IAM role của Spring Boot chỉ nên có đúng những quyền DynamoDB cần dùng trên:

- Bảng `reservation_record` để `PutItem`/`GetItem` và các action transaction tương ứng khi cần.
- Bảng `property_inventory` để `UpdateItem`/`GetItem`, với điều kiện giới hạn tài nguyên/tài khoản phù hợp.
- Nếu Query GSI, bổ sung **ARN của index** và quyền `Query` tương ứng.
- Không cấp quyền `DeleteTable`, `UpdateTable`, `Scan` hoặc sửa policy khi service không cần.
- Tách role cho API trực tuyến, migration/batch, dev/staging/production.

Tên action IAM cần đối chiếu **IAM Service Authorization Reference** của DynamoDB và các resource/action dependency thực tế. Một transaction gồm Put, Update và ConditionCheck có thể yêu cầu nhiều quyền tương ứng; không giả định chỉ một action tên "transaction" đủ cho mọi resource.

### 10.2. Secrets và danh tính

Ưu tiên IAM role/workload identity trên ECS, EKS, EC2; hạn chế cấp credential dài hạn. Thông tin bí mật của dịch vụ ngoài DynamoDB nên được lưu trong Secrets Manager/Parameter Store hoặc giải pháp tương ứng. DynamoDB mã hóa dữ liệu at rest, nhưng vẫn cần TLS, quyền IAM, phân quyền theo tenant ở tầng service và quy trình backup/restore.

### 10.3. Backup và khôi phục

Nếu nghiệp vụ đặt chỗ là dữ liệu quan trọng, cân nhắc Point-in-Time Recovery (PITR), backup, thử khôi phục, cảnh báo dung lượng/chi phí và kế hoạch xử lý khi dữ liệu sai. Backup không thay cho transaction để tránh inventory âm trong lúc hệ thống đang hoạt động.

## 11. Kiểm thử tích hợp, failure injection và load test

### 11.1. Kiểm thử chức năng trên DynamoDB Local

DynamoDB Local giúp kiểm tra schema, transaction request, condition và các exception cơ bản. Kịch bản gợi ý:

1. **Transaction thành công:** seed inventory `available=3`; gọi `bookOneSlot` với key mới; kiểm tra reservation tồn tại và available=2.
2. **Hết chỗ:** seed inventory `available=0`; gọi transaction; xác nhận không có reservation mới và inventory vẫn bằng 0.
3. **Create-only:** tạo trước reservation với full key; gọi transaction trùng; xác nhận inventory không giảm thêm.
4. **Idempotency:** gửi lại cùng token và **cùng request** trong cửa sổ hỗ trợ; xác nhận không thực thi lần hai. Gửi cùng token nhưng thay tham số; xác nhận API từ chối.
5. **Concurrent last slot:** inventory=1, cho hai request có reservation khác nhau chạy đồng thời; chỉ một request có thể được xác nhận, inventory không âm.
6. **Ranh giới transaction:** thử request vượt 100 hành động, item >400 KB hoặc payload >4 MB trong môi trường thử nghiệm; ghi nhận lỗi validation thay vì chuyển thành retry.
7. **Quyền và endpoint:** cấu hình AWS profile sai, account/Region sai, bảng thiếu hoặc credential không hợp lệ; xác nhận ứng dụng có error mapping rõ.
8. **Cleanup:** dùng key riêng cho từng test và dọn dữ liệu sau test, tránh để các lượt chạy ảnh hưởng nhau.

Một ví dụ assertion ở tầng service (cần bổ sung bean, test starter, fixture và bảng thực trong môi trường CI):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;
import software.amazon.awssdk.services.dynamodb.model.TransactionCanceledException;

@SpringBootTest
@ActiveProfiles("local")
class ReservationBookingIT {
    @Autowired ReservationBookingService bookingService;
    @Autowired DynamoDbClient client;

    @Test
    void cannotBookWhenInventoryIsEmpty() {
        // Bảng phải tồn tại trong endpoint DynamoDB Local.
        String tenant = "it-" + UUID.randomUUID();
        String property = "it-property";
        String date = "2026-11-24";
        String reservationId = "res-empty";
        String sortKey = "RES#2026-11-24T08:00:00.000Z#res-empty";
        String inventoryKey = tenant + "#" + property + "#" + date;
        client.putItem(PutItemRequest.builder()
                .tableName("property_inventory")
                .item(Map.of(
                        "inventoryKey", AttributeValue.builder()
                                .s(inventoryKey).build(),
                        "available", AttributeValue.builder()
                                .n("0").build()))
                .build());

        assertThrows(TransactionCanceledException.class, () ->
                bookingService.bookOneSlot(
                        tenant, property, date, sortKey, reservationId,
                        UUID.randomUUID().toString()));

        var inventory = client.getItem(GetItemRequest.builder()
                .tableName("property_inventory")
                .key(Map.of("inventoryKey", AttributeValue.builder()
                        .s(inventoryKey).build()))
                .consistentRead(true)
                .build());
        assertEquals("0", inventory.item().get("available").n());

        var reservation = client.getItem(GetItemRequest.builder()
                .tableName("reservation_record")
                .key(Map.of(
                        "tenantId", AttributeValue.builder()
                                .s(tenant).build(),
                        "sortKey", AttributeValue.builder()
                                .s(sortKey).build()))
                .consistentRead(true)
                .build());
        assertTrue(reservation.item().isEmpty());
    }
}
~~~

Ví dụ trên tự seed inventory với khóa riêng của test, sau đó đọc lại **cả hai bảng** để xác minh transaction không cập nhật dở. Test vẫn cần hai bảng đã được tạo ở endpoint DynamoDB Local và Spring Boot/test dependencies đầy đủ. Có thể tự tạo bảng trong setup bằng Testcontainers để CI độc lập với máy cá nhân. Đây là mã mẫu cần thực thi; **chưa có kết quả PASS của một lần chạy thực tế**.

### 11.2. Throttling không được mô phỏng hoàn hảo ở local

DynamoDB Local thường **không mô phỏng đầy đủ phân phối partition, adaptive capacity, quota và throttling thực tế của AWS**. Vì vậy:

- Kiểm tra code retry/backoff bằng unit/contract test có stub trả exception retryable và non-retryable, đo số nỗ lực được phép.
- Với các giới hạn tải thật, thực hiện **load test có ngân sách và quota** trên tài khoản AWS thử nghiệm, không trên bảng production.
- Ghi CloudWatch metrics, latency, retry, conflict, consumed capacity, key distribution, GSI behavior.
- Tăng tải từng bước, đặt guardrail về request rate, duration và chi phí, bảo đảm có phương án dừng khi throttling kéo dài.

### 11.3. Bài tập phân tích

Cho hai workload:

- Workload A: nhập 20.000 event độc lập mỗi phút, item nhỏ, chấp nhận eventual processing.
- Workload B: 2.000 người cùng tranh một suất cuối ở cùng `inventoryKey`.

Hãy thiết kế riêng:

| Tiêu chí | A – nhập event | B – tranh một suất |
| --- | --- | --- |
| Cơ chế ghi | Batch/queue + retry từng phần | Transaction hoặc atomic conditional write |
| Mục tiêu | Throughput và không mất event | Không oversell, kết quả nhất quán |
| Rủi ro chính | UnprocessedItems, capacity, queue backlog | Hot item, transaction conflict |
| Idempotency | Event ID duy nhất, checkpoint | Reservation ID/token cố định, điều kiện tồn kho |
| Tối ưu | Batch size, worker concurrency, partition key | Serialization theo inventory key, bounded retry |
| Test | Tải theo đợt, retry/lag/DLQ | Đồng thời, chỉ một người thắng, tồn kho không âm |

Từ đó giải thích vì sao cùng là "hệ thống bị chậm", tăng số worker là quyết định có thể hữu ích cho A nhưng gây hại cho B.

## 12. Checklist khi đưa vào production

1. **Schema:** mọi item dưới 400 KB; khóa không vượt giới hạn byte; tránh payload lớn; bảng/GSI/LSI được IaC quản lý.
2. **Access pattern:** dùng `GetItem`/`Query` theo key/index hợp lý; không để Scan trực tuyến đọc toàn bảng.
3. **Transaction:** số hành động, item size và tổng 4 MB được kiểm tra; không tác động hai lần cùng item trong một request; invariant được ghi thành condition.
4. **Idempotency:** mã nghiệp vụ và transaction token ổn định; kế hoạch đối soát khi timeout/đã quá cửa sổ token.
5. **Retry:** phân loại lỗi; retry SDK có jitter và giới hạn, không retry business conflict vô hạn; có backpressure/queue khi cần.
6. **Capacity:** theo dõi RCU/WCU, GSI, hot partition, throttling và transaction conflict; kiểm tra quota thực của account/Region.
7. **IAM:** role workload có quyền tối thiểu, tách job và API, không lưu credentials vào mã nguồn.
8. **Kiểm thử:** integration test có real endpoint giả lập, test concurrency; load test AWS thật có giới hạn và chi phí kiểm soát.
9. **Vận hành:** metric, alarm, logging có che dữ liệu, DLQ, PITR/backup và kế hoạch khôi phục.
10. **Đa cloud:** tách adapter DynamoDB khỏi business interface; định nghĩa rõ transaction/consistency/retry contract của mỗi provider.

## 13. Câu hỏi tự luyện

1. Một reservation lưu ảnh hợp đồng Base64 kích thước 600 KB. Tại sao không thể ghi vào một item DynamoDB? Nên thiết kế lại object và workflow lưu file như thế nào?
2. Có 80 reservation item cần cập nhật và 30 inventory item phải giảm atomically. Tại sao không thể gửi toàn bộ trong một transaction? Việc chia thành hai transaction ảnh hưởng invariant ra sao?
3. Tại sao `BatchWriteItem` không thích hợp để vừa tạo reservation vừa trừ inventory? `UnprocessedItems` phải được xử lý thế nào?
4. Chọn capacity mode on-demand hay provisioned cho hệ thống có tải tăng đột biến mỗi ngày. Những chỉ số nào cần đo trước khi quyết định?
5. Một request `TransactWriteItems` timeout, trong khi DynamoDB đã commit. Hãy trình bày cách dùng `ClientRequestToken` và reservation key để không trừ kho hai lần.
6. Khi 500 khách cùng update một inventory item, CloudWatch cho thấy nhiều transaction conflict. Vì sao tăng WCU có thể chưa đủ? Đề xuất cơ chế giảm contention.
7. Một job Scan đêm dùng rất nhiều read capacity, khiến API online bị throttled. Hãy thiết kế lại lịch xử lý, giới hạn concurrency, checkpoint và alert.
8. Khi chuyển từ DynamoDB sang Azure Cosmos DB hoặc Google Cloud Firestore, những giới hạn/thao tác transaction nào cần xác minh lại thay vì dùng giả định của AWS?

## Tài liệu tham khảo

- [AWS DynamoDB — Quotas and constraints](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ServiceQuotas.html): giới hạn bảng, transaction, key và item.
- [AWS DynamoDB — Transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html): `TransactWriteItems`, atomicity, idempotency và tình huống bị hủy.
- [AWS DynamoDB — Transaction conflicts](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html): hành vi cạnh tranh khi truy cập item.
- [AWS DynamoDB — Batch operations](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-batch-operation.html): batch, kích thước request và unprocessed items.
- [AWS DynamoDB — Read/write capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadWriteCapacityMode.html): on-demand, provisioned và cách đánh giá.
- [AWS DynamoDB — Read/write capacity unit consumption](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/read-write-operations.html): kích thước item và RCU/WCU.
- [AWS DynamoDB — Throttling diagnostics](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/throttling-diagnosing-workflow.html): nguyên nhân, throttling reason và metric.
- [AWS DynamoDB — Error handling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Programming.Errors.html): lỗi, retry và backoff.
- [AWS SDK for Java 2.x — Retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html): retry mode, jitter và cấu hình SDK.
- [AWS SDK for Java 2.x — DynamoDB Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html): ánh xạ dữ liệu và API cấp cao.
- [Spring Cloud AWS — Reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): starter DynamoDB, cấu hình AWS identity, region và endpoint.
