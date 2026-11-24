# Thiết kế partition key, sort key và ánh xạ đối tượng DynamoDB

## 1. Mục tiêu và bối cảnh

Trong chương **Dữ liệu AWS** của module **Spring Cloud Provider Integration**, ứng dụng Spring Boot cần làm việc với dịch vụ dữ liệu managed của AWS bằng thư viện Spring Cloud AWS hoặc AWS SDK. Với **Amazon DynamoDB**, quyết định quan trọng nhất thường không phải chọn lớp repository nào mà là **thiết kế khóa theo những truy vấn ứng dụng phải phục vụ**.

DynamoDB là cơ sở dữ liệu NoSQL dạng key–value/document. Tên bảng và các thuộc tính khóa/index được khai báo trước; các thuộc tính thông thường có thể linh hoạt giữa các item. DynamoDB **không** suy luận quan hệ hoặc tự hỗ trợ truy vấn tùy ý như một cơ sở dữ liệu quan hệ. Do đó, mô hình khóa, secondary index và lớp Java ánh xạ dữ liệu phải được thiết kế cùng nhau.

Sau bài học, bạn có thể:

- Phân biệt **partition key**, **sort key**, primary key đơn và primary key kết hợp.
- Xuất phát từ access pattern để chọn khóa phân phối tải tốt, tránh hot key và dữ liệu phân vùng không cân bằng.
- Thiết kế sort key cho truy vấn theo thời gian, nhóm bản ghi và khoảng giá trị; hiểu tác động của thứ tự so sánh chuỗi.
- Thiết kế **GSI/LSI** khi truy vấn khác với primary key, cùng giới hạn nhất quán và chi phí.
- Ánh xạ bảng vào Java bằng `@DynamoDbBean`, `@DynamoDbPartitionKey`, `@DynamoDbSortKey` và secondary index annotations của **AWS SDK for Java v2 Enhanced Client**.
- Gọi CRUD/Query từ Spring Boot, kiểm thử với DynamoDB Local và đánh giá cách thích ứng khi triển khai lên AWS.

> **Phạm vi:** Đây là bài thiết kế dữ liệu và object mapping cho DynamoDB. Các khái niệm `@DynamoDbBean` và `DynamoDbEnhancedClient` thuộc AWS SDK v2; `DynamoDbTemplate` của AWSpring, nếu phiên bản đang sử dụng hỗ trợ, có thể tái sử dụng các khai báo ánh xạ này. Không nhầm các annotation với JPA (`@Entity`, `@Id`).

## 2. DynamoDB tổ chức dữ liệu bằng khóa như thế nào?

### 2.1. Primary key đơn và kết hợp

Mỗi item trong một bảng được định danh duy nhất bởi **primary key**:

| Kiểu primary key | Thành phần | Khi thích hợp | Hạn chế cần nhớ |
| --- | --- | --- | --- |
| **Simple primary key** | Một partition key, ví dụ `orderId` | Chỉ cần đọc/ghi theo ID và ID có độ phân tán tốt | Không truy vấn được mọi đơn theo một người dùng bằng key chính |
| **Composite primary key** | Partition key + sort key, ví dụ `customerId` + `createdAt#orderId` | Cần nhiều item cho một nhóm, hỗ trợ truy vấn theo khoảng hoặc tiền tố | Muốn đọc đúng item phải biết **cả hai** giá trị khóa |

Một bảng có composite key có thể chứa nhiều item cùng partition key, nhưng **mỗi cặp** (`partitionKey`, `sortKey`) phải duy nhất. DynamoDB dùng giá trị partition key để phân phối dữ liệu; trong một nhóm cùng partition key, item được sắp theo sort key.

Các thuộc tính tham gia primary key phải là **scalar** kiểu **String**, **Number** hoặc **Binary**; không được là List/Map/Boolean. Giá trị khóa không được null hoặc chuỗi rỗng. Giới hạn độ dài giá trị partition key tối đa **2.048 byte**, sort key tối đa **1.024 byte**; đơn vị là byte UTF-8 chứ không phải số ký tự Java. Một item có kích thước tối đa **400 KB**, tính cả tên và giá trị thuộc tính.

~~~text
Bảng: reservation_record

tenantId (PK)      sortKey (SK)                              propertyId   state
---------------------------------------------------------------------------------
tenant-a           RES#2026-11-24T08:00:00.000Z#res-1001    house-99     PENDING
tenant-a           RES#2026-11-24T08:45:00.000Z#res-1002    house-99     CONFIRMED
tenant-a           RES#2026-11-25T09:00:00.000Z#res-1003    house-88     CANCELLED
tenant-b           RES#2026-11-24T08:00:00.000Z#res-1001    house-01     CONFIRMED

=> Hai tenant có thể cùng reservationId; khóa thực sự là (tenantId, sortKey).
~~~

### 2.2. `Query` khác `GetItem` và `Scan`

- `GetItem` đọc một item theo toàn bộ primary key. Bảng có sort key thì chỉ cung cấp partition key là chưa đủ.
- `Query` **bắt buộc có điều kiện bằng (`=`) trên partition key** của bảng hoặc index. Có thể bổ sung điều kiện trên sort key như `=`, `<`, `>`, `BETWEEN` hoặc `begins_with` (trong giới hạn kiểu dữ liệu của khóa).
- `Scan` duyệt dữ liệu rộng trên bảng/index. `FilterExpression` lọc **sau khi đọc** dữ liệu, vì vậy không biến một access pattern thiếu index thành truy vấn hiệu quả.
- Một trang `Query`/`Scan` bị giới hạn theo kích thước dữ liệu đọc; với `Query`, một lần gọi xử lý tối đa **1 MB trước khi áp dụng filter/projection**. Phải xử lý phân trang khi trả về `LastEvaluatedKey`.

~~~mermaid
flowchart LR
    A["Access pattern của nghiệp vụ"] --> B{"Biết khóa nào?"}
    B -->|"Cả PK + SK"| C["GetItem"]
    B -->|"PK, tùy chọn khoảng/prefix SK"| D["Query bảng"]
    B -->|"Khóa tra cứu khác"| E["Query GSI hoặc LSI"]
    B -->|"Không có key/index phù hợp"| F["Xem lại mô hình dữ liệu<br/>Scan chỉ khi thực sự cần"]
~~~

## 3. Bắt đầu từ access pattern, không bắt đầu từ class Java

Ví dụ hệ thống đặt chỗ gồm tenant, bất động sản và các lượt đặt. Trước khi tạo bảng, hãy mô tả những truy vấn chính và tính chất tải.

| Access pattern | Dữ liệu đầu vào | Kết quả mong muốn | Phương án |
| --- | --- | --- | --- |
| Xem một lượt đặt đã biết | `tenantId` + timestamp/mã đã ghi trong `sortKey` | Một item | `GetItem` trên khóa chính |
| Liệt kê lượt đặt tháng 11 của tenant | `tenantId` + `2026-11` | Nhiều item theo thời gian | `Query` trên PK với `begins_with(sortKey, ...)` |
| Liệt kê các lượt đặt của một nhà | `tenantId` + `propertyId` | Nhiều item theo thời gian | GSI có partition key `propertyKey` và sort key `createdAt` |
| Tìm lượt đặt chỉ biết `reservationId` | `tenantId` + `reservationId` | Một item | Thêm access pattern riêng: đổi thiết kế sort key, lập lookup item hoặc thêm GSI phù hợp |
| Thống kê số lượt đặt theo trạng thái | Tenant + thời gian + trạng thái | Tổng hợp số liệu | Có thể duy trì aggregate hoặc mô hình index chuyên biệt; cân nhắc chi phí |

**Quyết định thiết kế trong ví dụ:**

- Bảng `reservation_record` có primary key: **`tenantId` (partition key)** và **`sortKey` (sort key)**.
- `sortKey` có dạng `RES#<createdAtUtc>#<reservationId>`. Ví dụ: `RES#2026-11-24T08:00:00.000Z#res-1001`.
- `createdAt` lưu dưới dạng chuỗi ISO-8601 ở **UTC, cố định độ chính xác millisecond**. Phần tiền tố `RES#` giúp phân nhóm; phần thời gian giúp lấy khoảng; phần `reservationId` giúp tránh trùng primary key nếu hai lượt đặt cùng millisecond.
- GSI `by-property` dùng `propertyKey = tenantId#propertyId` làm partition key và `createdAt` làm sort key.

**Đánh đổi có chủ ý:** cách thiết kế này hỗ trợ truy vấn theo thời gian, nhưng API “tìm bằng reservationId” cần biết `sortKey` hoặc một ánh xạ phụ từ ID sang sort key. Nếu truy vấn theo ID là nhu cầu phổ biến nhất, một thiết kế khác như `PK=tenantId`, `SK=RES#reservationId` kết hợp GSI cho truy vấn theo thời gian có thể phù hợp hơn. Không có một khóa “đúng cho tất cả” khi access pattern khác nhau.

## 4. Chọn partition key để phân phối tải

Partition key không chỉ là một trường dùng lọc: nó ảnh hưởng việc phân phối read/write vào các partition vật lý. Một khóa tốt cần cân bằng giữa **khả năng truy vấn** và **mức độ phân tán traffic thực tế**.

### 4.1. Trường hợp tốt và dễ phát sinh hot key

| Ứng viên partition key | Điểm mạnh | Rủi ro |
| --- | --- | --- |
| `reservationId` có độ ngẫu nhiên cao | Phân tán các truy cập theo ID | Khó liệt kê toàn bộ lượt đặt theo tenant nếu không có index |
| `tenantId` | Truy vấn tất cả bản ghi tenant thuận lợi | Một tenant lớn, ghi/đọc dồn dập có thể thành hot key |
| `tenantId#yyyyMM` | Giảm phạm vi dữ liệu và có thể phân phối theo kỳ | Query nhiều tháng cần nhiều lượt; tenant cực lớn vẫn có thể nóng trong một tháng |
| `tenantId#bucket` (sharding) | Phân phối tải của tenant rất lớn | Truy vấn toàn tenant phải fan-out qua nhiều bucket và gộp kết quả |

**Ví dụ:** tenant `tenant-a` tạo vài chục reservation mỗi ngày thì `tenantId` có thể hoàn toàn hợp lý. Nhưng nếu một tenant tạo hàng chục nghìn request/giây cùng một key, cần đo tải và xem xét chia bucket; DynamoDB có adaptive capacity nhưng không làm biến mất mọi giới hạn của hot item/key. Đừng chọn sharding chỉ vì “NoSQL phải shard”; trước hết kiểm tra số lượng item, request, kích thước, mô hình truy vấn và các chỉ số throttling.

Nếu thiết kế multi-tenant, đưa `tenantId` vào khóa giúp tổ chức dữ liệu nhưng **không tự động tạo ranh giới phân quyền**. Tầng API phải xác thực tenant từ danh tính người dùng và kiểm tra từng thao tác đọc/ghi; không tin `tenantId` tùy ý trong request.

### 4.2. Những vấn đề phải quyết định sớm

- **Cardinality:** có bao nhiêu giá trị partition key khác nhau và phân bố lưu lượng trên chúng?
- **Item collection:** bao nhiêu item thường nằm trong cùng một partition key?
- **Truy vấn chéo nhóm:** dữ liệu phải liệt kê toàn tenant, theo tháng, theo nhà hay theo một ID riêng?
- **Kích thước/chi phí:** key dài làm tăng kích thước item, index và chi phí lưu trữ/đọc/ghi.
- **Mở rộng:** nếu sau này phải đổi primary key, thường phải tạo bảng mới và di chuyển dữ liệu vì DynamoDB không cho sửa định nghĩa primary key của bảng hiện hữu tại chỗ.

## 5. Thiết kế sort key theo cấu trúc và thứ tự

Sort key là nơi thể hiện thứ tự hoặc phân cấp của các item trong cùng partition key.

### 5.1. Sort key ghép

~~~text
RES#2026-11-24T08:00:00.000Z#res-1001
|    |                         |
|    |                         +-- mã để tránh đụng key
|    +---------------------------- thời gian UTC chuẩn hóa
+-------------------------------- loại item
~~~

Với cùng `tenantId`:

- `begins_with(sortKey, "RES#")`: các item reservation.
- `begins_with(sortKey, "RES#2026-11")`: reservation trong tháng 11/2026.
- `BETWEEN` với hai biên sort key: khoảng ngày/giờ khi định dạng timestamp thống nhất.

**Lưu ý thứ tự:** DynamoDB so sánh String key theo byte UTF-8, không tự hiểu thời gian. Các chuỗi như `2026-11-24T08:00:00Z` và `2026-11-24T08:00:00.100Z` khác độ dài và có thể sắp không đúng kỳ vọng theo thời gian. Hãy chuẩn hóa UTC, timezone, precision và zero-padding ngay khi ghi dữ liệu; quy định format như một phần của contract.

Nếu cần sort key số, kiểu DynamoDB `Number` được sắp theo giá trị số; nhưng không thể dùng `begins_with` với Number key. Với khóa ghép phân cấp như `CUSTOMER#123#ORDER#456`, ký tự phân cách cần được quy ước/escape khi ID có thể chứa ký tự đó. Không ghép tùy tiện dữ liệu người dùng vào key mà không kiểm soát.

### 5.2. Có nên lưu nhiều loại entity trong một bảng?

Một bảng đơn có thể lưu nhiều loại item:

~~~text
PK=TENANT#alpha, SK=PROFILE
PK=TENANT#alpha, SK=RES#2026-11-24T08:00:00.000Z#res-1001
PK=TENANT#alpha, SK=RES#2026-11-24T08:45:00.000Z#res-1002
~~~

Đây là **single-table design**, giúp một số access pattern truy vấn liên quan được trên một bảng. Tuy nhiên, nó đòi hỏi quy ước key, kiểm soát schema khác nhau giữa item type và cách ánh xạ ứng dụng phức tạp hơn. Bài thực hành này dùng **một loại item** trong bảng để làm rõ partition key, sort key và Java mapper trước.

## 6. Secondary index cho access pattern còn lại

### 6.1. GSI và LSI khác nhau

| Tiêu chí | Global Secondary Index (GSI) | Local Secondary Index (LSI) |
| --- | --- | --- |
| Partition key | Có thể khác partition key của bảng | Phải cùng partition key với bảng |
| Sort key | Có thể khác khóa của bảng | Khác sort key của bảng |
| Thời điểm tạo | Có thể bổ sung cho bảng hiện hữu | Phải khai báo khi tạo bảng |
| Đọc nhất quán mạnh | Không, GSI chỉ có eventually consistent reads | Có thể yêu cầu strongly consistent reads |
| Giới hạn item collection | Không bị ràng buộc bởi giới hạn 10 GB của LSI theo cùng cơ chế | Bảng có LSI chịu giới hạn item collection 10 GB cho mỗi partition key |
| Chi phí | Lưu trữ và năng lực read/write của index | Cân nhắc projection, lưu trữ và RCU/WCU bảng |

Với truy vấn **các reservation của một nhà trong tenant**, dùng GSI:

~~~text
GSI: by-property
  partition key: propertyKey = "tenant-a#house-99"
  sort key:      createdAt  = "2026-11-24T08:00:00.000Z"
~~~

Khóa `propertyKey` có tenant để tránh truy vấn index trộn dữ liệu của nhiều tenant. Nếu identifier có thể chứa `#`, cần quy tắc escape hoặc cấu trúc khóa không nhập nhằng. Dù có tenant trong key, authorization vẫn phải thực hiện ở service.

**GSI không đảm bảo duy nhất**: nhiều item của bảng cơ sở có thể cùng `propertyKey` và `createdAt` trên GSI. Tính duy nhất của item do primary key của bảng quyết định. GSI được cập nhật **bất đồng bộ**, vì vậy dữ liệu mới ghi có thể chưa xuất hiện ngay khi query index. Lựa chọn `ProjectionType=ALL` dễ thực hành nhưng tốn thêm lưu trữ và write; production nên đánh giá `KEYS_ONLY` hoặc `INCLUDE` theo trường thật sự cần.

### 6.2. Tạo bảng và GSI trong DynamoDB Local

Chạy DynamoDB Local cho thử nghiệm:

~~~bash
docker run --rm -p 8000:8000 amazon/dynamodb-local:latest
~~~

Đặt thông tin xác thực giả trong **terminal local**, chẳng hạn `AWS_ACCESS_KEY_ID=local` và `AWS_SECRET_ACCESS_KEY=local`. Không sử dụng khóa giả/endpoint local cho production.

~~~bash
# Bash; ví dụ dành cho DynamoDB Local, nơi endpoint đã được khai báo.
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

Đối chiếu:

- Tên bảng là `reservation_record`.
- Base table dùng `tenantId` / `sortKey`; index `by-property` dùng `propertyKey` / `createdAt`.
- Chỉ khai báo trong `--attribute-definitions` các thuộc tính tham gia khóa của bảng/index. `reservationId`, `state` và các thuộc tính thường không cần khai báo.
- Với AWS thật, nên tạo bảng/index bằng IaC, dùng IAM role, chọn region phù hợp; **starter/mapper không tự tạo schema**.

Kiểm tra table/index đã tồn tại:

~~~bash
aws dynamodb describe-table \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record
~~~

## 7. Ánh xạ đối tượng bằng AWS SDK for Java v2

### 7.1. Thư viện và nguồn cấu hình

Spring Boot có thể dùng AWSpring DynamoDB starter (nếu tương thích với phiên bản Spring Boot/AWS SDK của ứng dụng) để auto-configure `DynamoDbEnhancedClient`, hoặc tự cấu hình AWS SDK v2.

Với Maven, dependency quan trọng của Enhanced Client:

~~~xml
<!-- Quản lý version đồng nhất bằng AWS SDK v2 BOM của dự án. -->
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb</artifactId>
</dependency>
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb-enhanced</artifactId>
</dependency>
~~~

Nếu dùng AWSpring, dependency thường là `io.awspring.cloud:spring-cloud-aws-starter-dynamodb`, quản lý bằng **AWSpring BOM** tương thích với Spring Boot. Kiểm tra documentation và API của phiên bản thực tế trước khi giả định có `DynamoDbTemplate`; AWSpring và AWS SDK v2 là hai lớp khác nhau.

### 7.2. Định nghĩa bean khớp schema

Trong AWS SDK Enhanced Client, `@DynamoDbBean` cho phép ánh xạ các thuộc tính qua getter/setter JavaBean. Annotation khóa cần đặt trên **getter**; lớp có constructor không tham số và getter/setter truy cập được.

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
}
~~~

Bốn annotation quan trọng:

| Annotation | Ý nghĩa | Trong ví dụ |
| --- | --- | --- |
| `@DynamoDbPartitionKey` | Thuộc tính partition key của bảng | Getter `getTenantId()` |
| `@DynamoDbSortKey` | Thuộc tính sort key của bảng | Getter `getSortKey()` |
| `@DynamoDbSecondaryPartitionKey(indexNames = "...")` | Thuộc tính partition key của GSI/LSI được chỉ định | Getter `getPropertyKey()` |
| `@DynamoDbSecondarySortKey(indexNames = "...")` | Thuộc tính sort key của index được chỉ định | Getter `getCreatedAt()` |

Tên thuộc tính mặc định lấy từ tên property JavaBean. Để đổi tên trường lưu, có thể thêm `@DynamoDbAttribute("storageName")` trên getter; khi đó tên khóa trong **bảng/index thực tế** cũng phải khớp tên mới. Nếu có getter chỉ để hiển thị/định dạng và không muốn ghi vào DynamoDB, dùng `@DynamoDbIgnore`.

Nếu cần immutable object, AWS SDK Enhanced Client hỗ trợ `@DynamoDbImmutable(builder = ...)` với builder đúng quy ước; không chỉ đặt `final` cho field của `@DynamoDbBean` rồi kỳ vọng mapper vẫn hoạt động. Các kiểu phức tạp có thể dùng Bean lồng nhau, Map/List, custom `AttributeConverter`/`@DynamoDbConvertedBy` khi mapping mặc định không đáp ứng yêu cầu. Phần dữ liệu nested phải nằm trong giới hạn item và độ sâu tài liệu DynamoDB.

### 7.3. Giá trị key do nghiệp vụ quyết định

Annotation mô tả **trường nào** là key; annotation không tự tạo `sortKey` hay `propertyKey` từ các field khác. Service cần lập các khóa theo một quy tắc duy nhất:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class ReservationKeys {
    private static final DateTimeFormatter UTC_MILLIS =
            DateTimeFormatter
                    .ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS'Z'")
                    .withZone(ZoneOffset.UTC);

    private ReservationKeys() { }

    public static ReservationItem newItem(
            String tenantId,
            String propertyId,
            String reservationId,
            Instant createdAt) {
        String timestamp = UTC_MILLIS.format(createdAt);

        ReservationItem item = new ReservationItem();
        item.setTenantId(tenantId);
        item.setReservationId(reservationId);
        item.setPropertyId(propertyId);
        item.setPropertyKey(tenantId + "#" + propertyId);
        item.setCreatedAt(timestamp);
        item.setSortKey("RES#" + timestamp + "#" + reservationId);
        item.setState("PENDING");
        return item;
    }
}
~~~

Trong code production, validate tenant/property/reservation ID, quy ước dấu `#`, timezone, giới hạn độ dài key và unique ID. Với mã `reservationId` đã tồn tại, không nên sinh timestamp mới để tìm item; phải lấy lại khóa đã lưu hoặc dùng một index/lookup phù hợp. Nếu cần đảm bảo tính nhất quán của nhiều bản ghi lookup, xem transaction/conditional writes.

## 8. Dùng Enhanced Client trong Spring Boot

### 8.1. Khởi tạo client

Nếu đang dùng AWSpring starter tương thích và bean `DynamoDbEnhancedClient` đã được auto-configure thì chỉ cần inject bean. Nếu **không dùng AWSpring**, có thể khai báo cấu hình SDK v2 thuần:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Configuration
public class DynamoDbConfiguration {
    @Bean
    DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                // Dùng default credentials provider chain của SDK.
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

Đoạn trên kết nối AWS thật bằng credentials provider chain mặc định. Để chạy với DynamoDB Local **khi tự cấu hình client**, bổ sung endpoint override tương ứng, chẳng hạn `.endpointOverride(URI.create("http://localhost:8000"))`, và credentials giả chỉ cho môi trường local. **Không tạo trùng bean** khi starter đã cung cấp client đúng cấu hình.

Ví dụ cấu hình local của AWSpring (kiểm tra property trong phiên bản được chọn):

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

### 8.2. Repository lấy bảng theo TableSchema

~~~java
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbIndex;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;

@Repository
public class ReservationRepository {
    private final DynamoDbTable<ReservationItem> table;

    public ReservationRepository(DynamoDbEnhancedClient client) {
        this.table = client.table(
                "reservation_record",
                TableSchema.fromBean(ReservationItem.class));
    }

    public void save(ReservationItem item) {
        table.putItem(item);
    }

    public ReservationItem findOne(String tenantId, String sortKey) {
        Key key = Key.builder()
                .partitionValue(tenantId)
                .sortValue(sortKey)
                .build();
        return table.getItem(key); // null nếu không có item
    }

    public void listReservationsInMonth(String tenantId, String yyyyMM) {
        String prefix = "RES#" + yyyyMM;
        var pages = table.query(request -> request
                .queryConditional(QueryConditional.sortBeginsWith(
                        Key.builder()
                                .partitionValue(tenantId)
                                .sortValue(prefix)
                                .build()))
                .limit(25));

        for (var page : pages) {
            for (ReservationItem item : page.items()) {
                System.out.println(item.getReservationId());
            }
        }
    }

    public void listReservationsForProperty(
            String tenantId, String propertyId) {
        DynamoDbIndex<ReservationItem> index = table.index("by-property");
        var pages = index.query(request -> request
                .queryConditional(QueryConditional.keyEqualTo(
                        Key.builder()
                                .partitionValue(tenantId + "#" + propertyId)
                                .build()))
                .limit(25));

        for (var page : pages) {
            for (ReservationItem item : page.items()) {
                System.out.println(item.getReservationId());
            }
        }
    }
}
~~~

**Điều cần hiểu về đoạn mã:**

1. `TableSchema.fromBean(...)` đọc annotation và tạo metadata ánh xạ, nhưng **không tạo bảng AWS**. Bảng/index phải tồn tại đúng tên và kiểu key.
2. `table.getItem(key)` cần cả `tenantId` và `sortKey`; trả `null` nếu không tìm thấy.
3. `table.query(...)` dùng primary key, còn `table.index("by-property").query(...)` dùng khóa của GSI đã khai báo. **Không thể** query bảng trực tiếp bằng `propertyId` vì đây chỉ là thuộc tính thường của bảng.
4. `limit(25)` giới hạn số item DynamoDB đánh giá **trong mỗi lượt xử lý trang**, không bảo đảm toàn bộ vòng lặp trả tối đa 25 item. API demo duyệt tất cả page; hệ thống thật nên hỗ trợ cursor và giới hạn kết quả ở tầng API.
5. Query GSI có eventual consistency. Query trên bảng có thể yêu cầu consistent read khi nghiệp vụ cần và API hỗ trợ; **không bật strongly consistent trên GSI**.
6. Không đưa `System.out.println` vào repository production; thay bằng logic trả DTO/page và log có kiểm soát.

### 8.3. Ghi mới an toàn khi có concurrent requests

`putItem(item)` có thể thay item đã tồn tại cùng primary key. Nếu cần **create-only** thì thêm condition:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Expression;
import software.amazon.awssdk.enhanced.dynamodb.model.PutItemEnhancedRequest;

var createOnly = PutItemEnhancedRequest
        .builder(ReservationItem.class)
        .item(item)
        .conditionExpression(Expression.builder()
                .expression("attribute_not_exists(tenantId)")
                .build())
        .build();

table.putItem(createOnly);
~~~

Đoạn trên minh họa **bên trong repository nơi có biến `table` và `item`**. Điều kiện được đánh giá atomically trên item có key tương ứng; thao tác sẽ ném `ConditionalCheckFailedException` nếu cùng primary key đã tồn tại. Không tự retry vô hạn hay coi xung đột này là lỗi kết nối. Với cập nhật có cạnh tranh, có thể cân nhắc `@DynamoDbVersionAttribute` và optimistic locking phù hợp.

### 8.4. Nếu dự án dùng `DynamoDbTemplate`

Với phiên bản Spring Cloud AWS thực sự có `DynamoDbTemplate`, entity `@DynamoDbBean` bên trên vẫn là nền tảng để mapping, còn template thường cung cấp các operation như `save`, `load` và `query`. Hãy kiểm tra API và cấu hình table name resolver theo **đúng phiên bản**. Trường hợp ví dụ chủ động dùng tên bảng `reservation_record` qua `client.table("reservation_record", ...)`; nếu chuyển sang template mà resolver đặt tên khác, thao tác có thể thất bại với `ResourceNotFoundException`. Không giả định AWSpring, SDK v2 Enhanced Client và JPA có cùng cơ chế đặt tên bảng, repository hoặc transaction.

## 9. Kiểm thử thiết kế key và ánh xạ

Một test mock repository có thể cho kết quả xanh dù bảng thật dùng sai tên khóa. Với mô hình DynamoDB, nên có **integration test trên DynamoDB Local hoặc LocalStack** với bảng/index giống production.

Kịch bản tối thiểu:

1. Tạo bảng `reservation_record` và GSI `by-property` như mục 6, bật endpoint local.
2. Lưu 3 item: hai item cùng tenant/nhà nhưng khác timestamp và một item thuộc tenant khác.
3. Đọc đúng item bằng cả `tenantId` và `sortKey`; kiểm tra key tenant khác không đọc nhầm dữ liệu.
4. Query theo `begins_with(sortKey, "RES#2026-11")` và xác nhận chỉ xuất hiện bản ghi đúng khoảng thời gian của tenant.
5. Query GSI `propertyKey = "tenant-a#house-99"` và kiểm tra index trả dữ liệu đúng nhà. Nếu vừa ghi, có thể cần polling ngắn có giới hạn vì GSI cập nhật bất đồng bộ.
6. Thực hiện hai lần create-only cùng key để kiểm chứng lần thứ hai phát sinh `ConditionalCheckFailedException`.
7. Dùng dữ liệu riêng cho mỗi test và cleanup theo primary key để tránh phụ thuộc trạng thái test trước.

Ví dụ test Java với JUnit 5 (giả định Spring Boot/test dependencies và DynamoDB Local + bảng đã được thiết lập):

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class ReservationRepositoryIT {

    @Autowired
    ReservationRepository repository;

    @Test
    void compositeKeyMapsAndReadsCorrectItem() {
        String tenant = "it-" + UUID.randomUUID();
        ReservationItem item = ReservationKeys.newItem(
                tenant, "house-99", "res-1",
                Instant.parse("2026-11-24T08:00:00Z"));

        repository.save(item);

        ReservationItem loaded =
                repository.findOne(tenant, item.getSortKey());

        assertNotNull(loaded);
        assertEquals(item.getSortKey(), loaded.getSortKey());
        assertEquals(tenant + "#house-99", loaded.getPropertyKey());
        assertEquals("PENDING", loaded.getState());
    }
}
~~~

Bài thực hành nâng cao nên dùng Testcontainers khởi động DynamoDB Local/LocalStack trong CI, tạo bảng/index trong setup, cấu hình endpoint động và tự dọn dữ liệu. Chỉ khi test **thực sự chạy với DynamoDB endpoint** mới xác nhận được mapping và schema, không xem đoạn code ví dụ là bằng chứng test đã PASS.

## 10. Lỗi thường gặp và hậu quả

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `ValidationException: key element does not match schema` | Bean annotation, loại dữ liệu hoặc `Key.builder()` không khớp key thực tế | Kiểm tra `describe-table`, `tenantId`/`sortKey` và dạng scalar S/N/B |
| Đọc item trả null dù vừa ghi | Sai tenant, sai sort key, query nhầm bảng/region, eventual read | Log key đã chuẩn hóa và vùng; cân nhắc consistent read trên bảng |
| `ResourceNotFoundException` | Sai tên bảng/index, region hoặc endpoint | Kiểm tra tên trong IaC và resolver, trạng thái bảng/index |
| Query theo `propertyId` thất bại | `propertyId` không phải partition key bảng/index | Dùng GSI `by-property` với `propertyKey` hoặc thay access pattern |
| Thứ tự thời gian không đúng | Timestamp không cùng UTC/precision, key dạng chuỗi không chuẩn | Chuẩn hóa định dạng và thêm test về thứ tự |
| `DynamoDbMappingException` / class map lỗi | Thiếu constructor, setter, annotation trên getter, kiểu không hỗ trợ | Kiểm tra quy ước JavaBean, `TableSchema.fromBean`, converter |
| GSI thiếu item sau khi ghi | Cập nhật index bất đồng bộ hoặc item thiếu giá trị index key | Đợi có giới hạn nếu cần; kiểm tra `propertyKey`/`createdAt` |
| Tenant lớn bị throttling | Khóa `tenantId` quá nóng, item quá lớn hoặc GSI bị giới hạn | Đo metric theo key, cân nhắc sharding/index/capacity phù hợp |
| Tạo trùng reservation vô tình ghi đè | `putItem` không có condition | Dùng conditional writes, định nghĩa idempotency key rõ ràng |
| Truy vấn trả quá nhiều dữ liệu | Không phân trang; hiểu nhầm `limit` của mỗi request | Trả cursor/page size, giới hạn ở cả service/API |

## 11. Các quyết định vận hành và đa cloud

- **Bảo mật:** Spring Boot chạy trên ECS/EKS/EC2 nên dùng danh tính/role phù hợp, quyền IAM tối thiểu cho `GetItem`, `PutItem`, `Query`, `DeleteItem` và **ARN của GSI** khi truy vấn index. Không đưa access key/secret key vào source control. Dùng AWS Secrets Manager/Parameter Store nếu ứng dụng cần quản lý secret riêng.
- **Hiệu năng/chi phí:** chọn capacity mode dựa trên traffic thực, theo dõi read/write capacity, throttling, latency và GSI write amplification. `Scan` trên bảng lớn thường đắt hơn `Query` theo key phù hợp; tăng số GSI không miễn phí.
- **Nhất quán:** một item được ghi atomically; việc ghi nhiều item cần cân nhắc transaction API nếu phải all-or-nothing. GSI có eventual consistency, không phù hợp cho kiểm tra điều kiện đồng thời đòi hỏi dữ liệu mới nhất.
- **TTL và dữ liệu nhạy cảm:** nếu cần xóa dữ liệu hết hạn, lưu thời điểm TTL dưới dạng **Unix epoch seconds (Number)** ở thuộc tính riêng và bật TTL trên bảng. TTL không bảo đảm xóa ngay tại thời điểm hết hạn; code vẫn cần kiểm tra hạn khi nghiệp vụ yêu cầu.
- **Bảo toàn schema khi triển khai:** dùng IaC quản lý table/index, test mapper với schema thật, có kế hoạch backfill và cutover khi đổi khóa. Chuyển primary key của bảng không phải một thao tác sửa annotation đơn giản.
- **So sánh với Azure/GCP:** Azure Cosmos DB và Google Cloud Firestore cũng yêu cầu suy nghĩ về phân vùng, đường dẫn document, index và quota, nhưng mô hình khóa, giới hạn và IAM khác DynamoDB. Giữ interface truy cập dữ liệu trong tầng domain/service, triển khai provider-specific adapter khi xây sản phẩm đa cloud.

## 12. Bài tập tự luyện

1. Từ bốn truy vấn “theo reservationId”, “theo tenant và tháng”, “theo property”, “theo state”, hãy thiết kế hai phương án primary key/GSI khác nhau và phân tích tradeoff.
2. Tạo 100 item cho một tenant, query bằng `begins_with` để lọc tháng; so sánh với `Scan` về số item đọc/trang và dữ liệu trả về.
3. Thay `propertyKey = tenantId#propertyId` bằng một bộ quy tắc encode an toàn trước dữ liệu có dấu `#`; kiểm thử không có hai cặp ID khác nhau sinh cùng một key.
4. Thêm thuộc tính `expiresAt` cho TTL và một trường nested `guestContact`; chọn cách map và bảo vệ dữ liệu cá nhân.
5. Viết test kiểm chứng cùng một `reservationId` ở hai tenant khác nhau không ghi đè nhau, đồng thời test create-only khi có hai request cạnh tranh.
6. Đánh giá yêu cầu “đọc reservation theo ID ngay sau khi tạo” khi ID không chứa timestamp: bổ sung lookup item, GSI hay thay schema chính? Nêu quyết định và hệ quả tính nhất quán.

## Tài liệu tham khảo

- [AWS — Core components of DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.CoreComponents.html): bảng, item, partition key, sort key và index.
- [AWS — Designing partition keys](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html): phân phối tải và hot key.
- [AWS — Best practices for sort keys](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-sort-keys.html): sort key có cấu trúc và truy vấn theo phân cấp.
- [AWS — Key condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.KeyConditionExpressions.html): điều kiện `Query` và phân trang.
- [AWS — Using global secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html): GSI, projection, consistency và chi phí.
- [AWS SDK for Java 2.x — Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html): `TableSchema`, `DynamoDbBean` và API truy xuất.
- [AWS SDK for Java 2.x — Use secondary indices](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/ddb-en-client-use-secindex.html): ánh xạ GSI/LSI với annotation.
- [AWS — DynamoDB constraints](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Constraints.html): giới hạn key, item và các biểu thức.
