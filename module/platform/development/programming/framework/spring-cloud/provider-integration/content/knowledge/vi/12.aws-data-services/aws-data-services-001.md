# Tích hợp DynamoDB bằng starter và DynamoDbTemplate khi phiên bản hỗ trợ

## 1. Bối cảnh và mục tiêu

Trong một ứng dụng Spring Boot, dữ liệu có thể được lưu trên dịch vụ managed của AWS thay vì vận hành một cụm cơ sở dữ liệu riêng. **Amazon DynamoDB** là cơ sở dữ liệu NoSQL dạng key–value/document do AWS quản lý, phù hợp với các luồng truy cập có khóa xác định, cần độ trễ thấp và có lưu lượng biến động. Bài này thuộc chương **Dữ liệu AWS**, tập trung vào tích hợp Spring Boot với DynamoDB qua **Spring Cloud AWS (AWSpring)**.

Sau bài học, bạn có thể:

- Chọn đúng thư viện và nhận diện trường hợp phiên bản Spring Cloud AWS cung cấp `DynamoDbTemplate`.
- Cấu hình region, danh tính IAM, quyền truy cập và endpoint cho môi trường AWS hoặc DynamoDB Local.
- Thiết kế bảng theo partition key/sort key, ánh xạ Java bean và thực hiện CRUD, `Query` bằng `DynamoDbTemplate`.
- Chuyển sang `DynamoDbEnhancedClient` của AWS SDK for Java v2 nếu starter/template chưa phù hợp.
- Kiểm thử tích hợp, xử lý lỗi phổ biến và đưa ra quyết định vận hành về bảo mật, chi phí, tính nhất quán và hiệu năng.

**Ví dụ xuyên suốt:** một ứng dụng quản lý đặt chỗ lưu `ReservationRecord` theo khóa `tenantId` (đơn vị thuê) và `reservationId` (mã đặt chỗ). Truy vấn chính là lấy một đặt chỗ hoặc danh sách đặt chỗ của một tenant.

> Phạm vi: DynamoDB là dịch vụ AWS; `DynamoDbTemplate` trong bài là abstraction của thư viện `io.awspring.cloud`, **không phải** `MongoTemplate`, `JdbcTemplate` hay Spring Data JPA. Starter cung cấp auto-configuration và các thao tác dữ liệu; không mặc nhiên sinh repository từ interface kiểu `JpaRepository`.

## 2. Chọn đúng cơ chế tích hợp và phiên bản

Có ba lớp API liên quan:

~~~mermaid
flowchart TD
    A["Spring MVC / Service"] --> B["ReservationRepository"]
    B --> C["DynamoDbTemplate / DynamoDbOperations<br/>(AWSpring, nếu bản đang dùng hỗ trợ)"]
    C --> D["DynamoDbEnhancedClient<br/>(AWS SDK v2)"]
    D --> E["DynamoDbClient<br/>(AWS SDK v2)"]
    E --> F[("Amazon DynamoDB")]
    B -. "Phương án thay thế" .-> D
~~~

| Cơ chế | Khi nên dùng | Trách nhiệm chính |
| --- | --- | --- |
| `spring-cloud-aws-starter-dynamodb` + `DynamoDbTemplate` | Dự án có phiên bản AWSpring tương thích, cần CRUD và truy vấn thông thường | Spring tự cấu hình bean client, template, table name/schema resolver |
| `DynamoDbEnhancedClient` | Muốn kiểm soát conditional writes, table API, hoặc phiên bản dự án không có template | Tạo `DynamoDbTable<T>`, ánh xạ schema và gọi API Enhanced Client |
| `DynamoDbClient` | Cần API mức thấp như tạo bảng, batch/transaction hoặc yêu cầu chưa có trong abstraction cao hơn | Xây request và xử lý response trực tiếp |

**Kiểm tra khả năng hỗ trợ trước khi viết code:**

1. Xem *dependency tree* để biết phiên bản `io.awspring.cloud` thực tế và Spring Boot đang dùng. Chọn BOM AWSpring tương thích với phiên bản Spring Boot của dự án; không ghép tùy tiện nhiều dòng major.
2. Trong tài liệu API của đúng phiên bản, xác nhận có `io.awspring.cloud.dynamodb.DynamoDbTemplate`, `DynamoDbOperations` và starter `spring-cloud-aws-starter-dynamodb`. Ví dụ, tài liệu Spring Cloud AWS **3.4.0/3.4.2** mô tả đầy đủ các thành phần này.
3. Xác nhận bean template được auto-configure; một dependency mang tên tương tự thuộc thư viện đời cũ `org.springframework.cloud:spring-cloud-starter-aws` không thay thế được `io.awspring.cloud`.
4. Nếu thiếu template hoặc API có khác biệt, dùng Enhanced Client của AWS SDK v2 (mục 8); không tự giả định method có sẵn.

**Lưu ý phiên bản:** mã Java dùng template bên dưới tham chiếu API dòng AWSpring 3.4.x. Với dòng 4.x hoặc các dòng khác, đối chiếu tài liệu của bản đã khóa trong BOM. Khi dùng API mới như conditional operations, luôn kiểm tra chữ ký method cụ thể.

## 3. Thiết kế bảng DynamoDB theo truy vấn

DynamoDB tổ chức dữ liệu theo **primary key**. Với bảng có composite primary key:

- **Partition key** `tenantId` (kiểu String): nhóm dữ liệu của mỗi tenant.
- **Sort key** `reservationId` (kiểu String): phân biệt các đặt chỗ trong một tenant.
- **Thuộc tính thông thường** `propertyId`, `state`, `createdAt`: không cần khai báo trong `create-table` nếu không tham gia key/index.

| Nhu cầu truy cập | Cách đáp ứng | Lưu ý |
| --- | --- | --- |
| Lấy đúng một đặt chỗ | `GetItem` với cả `tenantId` và `reservationId` | Chỉ biết `reservationId` thì chưa đủ để tìm theo primary key hiện tại |
| Liệt kê đặt chỗ của một tenant | `Query` theo partition key `tenantId` | Có thể phân trang và bổ sung điều kiện trên sort key |
| Tìm mọi đặt chỗ theo `propertyId` | Thiết kế Global Secondary Index phù hợp | Không dùng `Scan` toàn bảng làm giải pháp mặc định |
| Lọc theo trạng thái `state` | Chọn key/index tương ứng nếu đây là luồng truy vấn thường xuyên | `FilterExpression` vẫn đọc các item trước khi lọc, không thay thế index |

Việc chọn partition key còn ảnh hưởng phân phối tải: không dồn mọi lượt ghi vào một giá trị key nóng. Sort key là **chuỗi**, nên thứ tự sắp xếp theo chuỗi; nếu muốn duyệt theo thời gian, cân nhắc sort key dạng `createdAt#reservationId` với timestamp chuẩn UTC và đảm bảo mã không trùng. Trong ví dụ tối thiểu bên dưới, dùng `reservationId` để đơn giản hóa.

## 4. Thêm dependency cho Spring Boot

### Maven

Giả sử dự án đang chạy một dòng Spring Boot 3.x tương thích với AWSpring 3.4.2. Kiểm tra ma trận tương thích trước khi khóa phiên bản:

~~~xml
<properties>
    <!-- Chọn phiên bản phù hợp với Spring Boot của dự án -->
    <spring-cloud-aws.version>3.4.2</spring-cloud-aws.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-dynamodb</artifactId>
    </dependency>
</dependencies>
~~~

Trong ví dụ, BOM lấy phiên bản từ property Maven `spring-cloud-aws.version` để chỉ thay đổi một nơi khi nâng cấp. Spring Boot parent/BOM của ứng dụng vẫn cần được thiết lập như thông lệ.

### Gradle (Groovy DSL)

~~~groovy
dependencies {
    implementation platform('io.awspring.cloud:spring-cloud-aws-dependencies:3.4.2')
    implementation 'io.awspring.cloud:spring-cloud-aws-starter-dynamodb'
}
~~~

Không khai báo version riêng cho từng starter khi BOM đã quản lý. Nếu có lỗi `NoClassDefFoundError` hoặc `NoSuchMethodError` sau khi thêm dependency, kiểm tra các phiên bản AWS SDK v2 bị kéo vào hoặc bị ghi đè. Không trộn AWS SDK v1 và v2 theo cách tạo ra các client/cấu hình không tương thích.

## 5. Danh tính AWS, region và endpoint

### 5.1. Production: sử dụng IAM role

Trong AWS, nên cấp quyền cho **IAM role gắn với workload** (ví dụ role của ECS task, EC2 instance hoặc cơ chế danh tính dành cho EKS). AWS SDK và Spring Cloud AWS có thể lấy credentials từ provider chain; tránh đưa access key/secret key cố định vào `application.yml`, source code hoặc Git.

~~~yaml
# application.yml (môi trường AWS)
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        enabled: true
~~~

`spring.cloud.aws.region.static` là region mặc định dùng bởi các client được auto-configure. Nếu chỉ DynamoDB cần region riêng, xem property `spring.cloud.aws.dynamodb.region` của đúng bản đang dùng.

Ví dụ policy IAM minh họa cho ứng dụng chỉ đọc/ghi bảng chính:

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
      "Resource": "arn:aws:dynamodb:ap-southeast-1:123456789012:table/reservation_record"
    }
  ]
}
~~~

Thay region, account ID và tên bảng bằng tài nguyên thật; đây chỉ là policy mẫu. Nếu `Query` trên GSI, bổ sung đúng ARN của index (ví dụ `...:table/reservation_record/index/ten_index`) với quyền cần thiết. Chỉ cấp `Scan`, `BatchWriteItem`, `TransactWriteItems`, `DescribeTable` khi nghiệp vụ thật sự cần.

### 5.2. Local: DynamoDB Local

Có thể dùng container để thực hành mà không tạo dữ liệu trên tài khoản AWS:

~~~bash
docker run --rm --name dynamodb-local -p 8000:8000 amazon/dynamodb-local:latest
~~~

Tạo cấu hình dành riêng cho local:

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

Khởi chạy Spring Boot với profile `local`. DynamoDB Local thường dùng credentials giả để ký request; chỉ đặt credentials giả trong **môi trường local**, không lưu vào cấu hình production.

~~~bash
# Bash / shell dành cho phát triển local
export AWS_ACCESS_KEY_ID=local
export AWS_SECRET_ACCESS_KEY=local
~~~

Trên PowerShell có thể dùng `$env:AWS_ACCESS_KEY_ID="local"` và `$env:AWS_SECRET_ACCESS_KEY="local"` trong phiên terminal thử nghiệm. AWS CLI cũng cần credentials và region hợp lệ về mặt cú pháp dù endpoint đang là localhost.

## 6. Tạo bảng khớp với entity

Tạo bảng `reservation_record` với hai thuộc tính tham gia key:

~~~bash
aws dynamodb create-table --endpoint-url http://localhost:8000 --region ap-southeast-1 --table-name reservation_record --attribute-definitions AttributeName=tenantId,AttributeType=S AttributeName=reservationId,AttributeType=S --key-schema AttributeName=tenantId,KeyType=HASH AttributeName=reservationId,KeyType=RANGE --billing-mode PAY_PER_REQUEST
~~~

Xác nhận bảng tồn tại:

~~~bash
aws dynamodb describe-table --endpoint-url http://localhost:8000 --region ap-southeast-1 --table-name reservation_record
~~~

Với AWS thật, tạo bảng qua IaC như CloudFormation, CDK hoặc Terraform và dùng endpoint mặc định của AWS. **Starter không tự tạo bảng dựa trên entity** như Hibernate có thể làm với relational database.

### 6.1. Định nghĩa entity ánh xạ

~~~java
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbBean;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSortKey;

@DynamoDbBean
public class ReservationRecord {
    private String tenantId;
    private String reservationId;
    private String propertyId;
    private String state;
    private String createdAt;  // ISO-8601 UTC, ví dụ 2026-11-24T08:00:00Z

    public ReservationRecord() {
    }

    @DynamoDbPartitionKey
    public String getTenantId() {
        return tenantId;
    }

    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    @DynamoDbSortKey
    public String getReservationId() {
        return reservationId;
    }

    public void setReservationId(String reservationId) {
        this.reservationId = reservationId;
    }

    public String getPropertyId() {
        return propertyId;
    }

    public void setPropertyId(String propertyId) {
        this.propertyId = propertyId;
    }

    public String getState() {
        return state;
    }

    public void setState(String state) {
        this.state = state;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

Điểm cần nhớ:

- `@DynamoDbBean` thuộc **AWS SDK Enhanced Client**, không thuộc JPA. Bean có constructor không tham số và public getter/setter để mapper làm việc.
- Annotate **getter** bằng `@DynamoDbPartitionKey` / `@DynamoDbSortKey`. Kiểu và tên thuộc tính phải khớp schema thực tế của bảng (`tenantId`, `reservationId`).
- `DynamoDbTemplate` chọn tên bảng qua `DynamoDbTableNameResolver`. Mặc định tên class `ReservationRecord` được chuyển thành `reservation_record`. Có thể cấu hình `spring.cloud.aws.dynamodb.table-prefix`, `table-suffix` hoặc cung cấp resolver riêng; lúc đó tên bảng tạo bằng CLI/IaC phải thay đổi tương ứng.
- Dữ liệu thiếu khóa hoặc kiểu khóa khác bảng sẽ dẫn đến lỗi khi ghi/đọc. DynamoDB là schema linh hoạt với thuộc tính thường, nhưng **primary key và index vẫn có schema rõ ràng**.

## 7. CRUD và Query với DynamoDbTemplate

Với bản thư viện có bean `DynamoDbTemplate`, Spring tự cấu hình template dựa trên `DynamoDbEnhancedClient`, `DynamoDbTableNameResolver` và `DynamoDbTableSchemaResolver`. Có thể inject trực tiếp template vào repository do ứng dụng tự viết:

~~~java
import io.awspring.cloud.dynamodb.DynamoDbTemplate;
import java.util.List;
import java.util.Optional;
import java.util.stream.StreamSupport;
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;

@Repository
public class ReservationRepository {
    private final DynamoDbTemplate template;

    public ReservationRepository(DynamoDbTemplate template) {
        this.template = template;
    }

    public ReservationRecord save(ReservationRecord item) {
        return template.save(item);
    }

    public Optional<ReservationRecord> findById(
            String tenantId, String reservationId) {
        Key key = Key.builder()
                .partitionValue(tenantId)
                .sortValue(reservationId)
                .build();

        return Optional.ofNullable(
                template.load(key, ReservationRecord.class));
    }

    public List<ReservationRecord> first25ForTenant(String tenantId) {
        QueryEnhancedRequest request = QueryEnhancedRequest.builder()
                .queryConditional(QueryConditional.keyEqualTo(
                        Key.builder().partitionValue(tenantId).build()))
                .limit(25)
                .build();

        return StreamSupport.stream(
                        template.query(request, ReservationRecord.class)
                                .items()
                                .spliterator(),
                        false)
                .limit(25)
                .toList();
    }

    public void deleteById(String tenantId, String reservationId) {
        Key key = Key.builder()
                .partitionValue(tenantId)
                .sortValue(reservationId)
                .build();

        template.delete(key, ReservationRecord.class);
    }
}
~~~

Gọi thử từ tầng service:

~~~java
ReservationRecord booking = new ReservationRecord();
booking.setTenantId("tenant-a");
booking.setReservationId("res-1001");
booking.setPropertyId("house-99");
booking.setState("PENDING");
booking.setCreatedAt("2026-11-24T08:00:00Z");

repository.save(booking);

ReservationRecord loaded = repository
        .findById("tenant-a", "res-1001")
        .orElseThrow();

List<ReservationRecord> recent = repository.first25ForTenant("tenant-a");

repository.deleteById("tenant-a", "res-1001");
~~~

**Diễn giải đúng về thao tác:**

- `save(item)` ghi dữ liệu; **đừng hiểu là insert-only**. Đọc và ghi cùng key có thể thay thế/cập nhật item tùy semantics của operation. Muốn chống tạo trùng hoặc chống cập nhật đè, dùng **conditional write**.
- `load(key, clazz)` trả `null` khi item không tồn tại; wrapper `Optional.ofNullable` giúp service phân biệt “không tìm thấy”.
- `Query` cần điều kiện theo partition key. `first25ForTenant` có giới hạn item phục vụ minh họa; thuộc tính `limit(25)` trên request điều khiển số item DynamoDB đánh giá mỗi lần gọi, không bảo đảm bản thân truy vấn chỉ có tối đa 25 kết quả qua mọi trang. Giới hạn của Java stream ở ngoài mới quyết định số item trả về trong ví dụ.
- Mặc định DynamoDB có thể trả **eventually consistent reads**. Khi nghiệp vụ cần đọc dữ liệu mới ghi ngay, kiểm tra API hỗ trợ `consistentRead(true)` (chỉ áp dụng tại nơi DynamoDB cho phép, không áp dụng strong consistency cho GSI).
- Các trang kết quả có thể còn dữ liệu; với ứng dụng production, nên trả `nextToken` / cursor có kiểm soát, giới hạn tải và không âm thầm duyệt toàn bộ tập dữ liệu.

### 7.1. Query so với Scan

`Query` truy xuất theo key/index được thiết kế trước. `Scan` duyệt dữ liệu rộng, thường tiêu tốn nhiều read capacity, nhất là bảng lớn. `ScanEnhancedRequest` và `template.scan(...)` hữu ích cho tác vụ quản trị hay xử lý dữ liệu nhỏ, nhưng không thay thế một access pattern/secondary index phù hợp.

Nếu cần lọc `state = "CONFIRMED"` ở quy mô lớn, thiết kế index phản ánh truy vấn như `tenantId + state#createdAt` hoặc GSI khác tùy nhu cầu và phân bố tải. DynamoDB không tự hỗ trợ tìm tùy ý mọi trường như SQL; việc thiết kế key/index nên bắt đầu từ **câu hỏi nghiệp vụ**.

### 7.2. Khi nào cần Enhanced Client cho thao tác nâng cao?

Với yêu cầu tạo mới chỉ khi key chưa tồn tại, có thể dùng `DynamoDbEnhancedClient` và `PutItemEnhancedRequest` với biểu thức điều kiện `attribute_not_exists(tenantId)`. Khi hai request cùng ghi, DynamoDB đánh giá điều kiện theo cách atomic trên item; request không thỏa sẽ nhận `ConditionalCheckFailedException`. Cũng có thể dùng `@DynamoDbVersionAttribute` trên entity phù hợp để hỗ trợ optimistic locking thông qua Enhanced Client. Đối chiếu API cụ thể vì hỗ trợ conditional operations của template khác nhau giữa các phiên bản.

Đối với nhiều item phải thay đổi atomically, xem DynamoDB transactional APIs cùng giới hạn và chi phí; `template.save(...)` cho từng item **không tạo transaction đa item**.

## 8. Phương án khi không có DynamoDbTemplate: AWS SDK v2 Enhanced Client

Nếu phiên bản hiện tại không cung cấp `DynamoDbTemplate`, vẫn có thể dùng mô hình entity nói trên. Khi đã có bean `DynamoDbEnhancedClient`, viết repository như sau:

~~~java
import java.util.Optional;
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;

@Repository
public class ReservationEnhancedRepository {
    private final DynamoDbTable<ReservationRecord> table;

    public ReservationEnhancedRepository(DynamoDbEnhancedClient client) {
        this.table = client.table(
                "reservation_record",
                TableSchema.fromBean(ReservationRecord.class));
    }

    public void save(ReservationRecord item) {
        table.putItem(item);
    }

    public Optional<ReservationRecord> findById(
            String tenantId, String reservationId) {
        Key key = Key.builder()
                .partitionValue(tenantId)
                .sortValue(reservationId)
                .build();

        return Optional.ofNullable(table.getItem(key));
    }

    public void deleteById(String tenantId, String reservationId) {
        table.deleteItem(Key.builder()
                .partitionValue(tenantId)
                .sortValue(reservationId)
                .build());
    }
}
~~~

Nếu dự án **không dùng AWSpring starter**, khai báo AWS SDK v2 dependencies `software.amazon.awssdk:dynamodb`, `software.amazon.awssdk:dynamodb-enhanced` và cấu hình hai bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Configuration
class DynamoDbSdkConfiguration {
    @Bean
    DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(DefaultCredentialsProvider.create())
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

Đoạn cấu hình SDK thuần ở trên gọi endpoint AWS thật. Để chạy local, cần cấu hình `endpointOverride(URI.create("http://localhost:8000"))` và region/credentials local tương ứng; không tự áp dụng property `spring.cloud.aws.dynamodb.endpoint` nếu bỏ hoàn toàn AWSpring auto-configuration. **Không khai báo lại các bean client này** nếu starter đã tạo bean phù hợp, trừ khi chủ động thay cấu hình mặc định.

## 9. Kiểm thử tích hợp có thể lặp lại

Một unit test dùng mock repository chỉ kiểm tra logic service; để phát hiện lệch table name, khóa, mapper, cấu hình endpoint và bean, cần **integration test với DynamoDB Local hoặc LocalStack**.

Kịch bản đơn giản trên máy phát triển:

1. Chạy container DynamoDB Local và tạo bảng `reservation_record` như mục 5–6.
2. Thiết lập environment credentials giả trong terminal chạy test và profile `local`.
3. Chạy test Spring Boot để ghi một item bằng repository thực, đọc lại và xác nhận dữ liệu.
4. Chọn `tenantId` / `reservationId` ngẫu nhiên cho mỗi test hoặc xóa item trong cleanup để tránh phụ thuộc trạng thái cũ.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

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
    void saveThenLoadFromRealDynamoDbEndpoint() {
        String tenant = "it-" + UUID.randomUUID();

        ReservationRecord item = new ReservationRecord();
        item.setTenantId(tenant);
        item.setReservationId("res-1");
        item.setPropertyId("property-1");
        item.setState("CONFIRMED");

        repository.save(item);

        ReservationRecord loaded = repository
                .findById(tenant, "res-1")
                .orElseThrow();

        assertEquals("CONFIRMED", loaded.getState());
        assertEquals("property-1", loaded.getPropertyId());

        repository.deleteById(tenant, "res-1");
    }
}
~~~

Test trên giả định Spring Boot app và JUnit 5/test starter đã có, **DynamoDB Local đang chạy và bảng đã tạo**. Để CI độc lập với môi trường, tạo container bằng Testcontainers rồi cấu hình endpoint/region/credentials động và tạo bảng trong setup test. Một số phiên bản AWSpring hỗ trợ `spring-cloud-aws-testcontainers` với `@ServiceConnection` cho LocalStack; kiểm tra tài liệu đúng phiên bản trước khi dùng vì cú pháp phụ thuộc cả Spring Boot và Testcontainers.

Nên kiểm tra thêm các trường hợp: khóa không tồn tại, cả partition/sort key bị sai, nhiều item cùng tenant, bảng bị thiếu, credentials/region sai, policy không đủ quyền và ghi đồng thời có điều kiện. Một test thực tế chỉ nên được coi là PASS khi đã chạy trên endpoint thử nghiệm, không dựa vào việc mã ví dụ trông hợp lý.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: DynamoDbTemplate` | Starter/version không hỗ trợ, auto-config bị tắt, bean không được tạo | Kiểm tra BOM, dependency tree, `spring.cloud.aws.dynamodb.enabled` và điều kiện auto-configuration |
| `NoClassDefFoundError` / `NoSuchMethodError` | Xung đột AWS SDK v2/AWSpring hoặc sai phiên bản tương thích với Spring Boot | Dùng BOM phù hợp, thống nhất dependency versions; tránh ghi đè SDK tùy tiện |
| `Unable to load credentials` | Chưa có provider phù hợp hoặc ứng dụng chạy ngoài AWS | Kiểm tra AWS profile, env vars, IAM role, workload identity; với local dùng credentials giả |
| `ResourceNotFoundException` | Sai bảng, region, account hoặc endpoint | Kiểm tra `describe-table`, tên bảng do resolver sinh ra và region thực tế |
| `ValidationException` khi truy cập key | Thiếu sort key, dùng sai kiểu dữ liệu, tên thuộc tính không khớp | Đối chiếu `@DynamoDbPartitionKey`, `@DynamoDbSortKey` và `Key.builder()` với schema bảng |
| `AccessDeniedException` | IAM policy không cho phép action trên table/index | Kiểm tra role thực tế và ARN tài nguyên trong policy |
| `ConditionalCheckFailedException` | Điều kiện ghi cập nhật không còn đúng | Phân biệt xung đột nghiệp vụ với lỗi hệ thống; retry có kiểm soát nếu phù hợp |
| Đọc ngay sau ghi chưa thấy kết quả | Eventually consistent read hoặc đọc qua GSI | Dùng consistent read ở thao tác hỗ trợ khi cần; không giả định GSI strong consistent |
| Query chậm hoặc tốn chi phí | Scan/filter diện rộng, hot partition, phân trang không giới hạn | Thiết kế lại key/index, giới hạn dữ liệu trả về, theo dõi consumed capacity |

Có thể bật log AWS SDK/HTTP phục vụ chẩn đoán nhưng cần **ẩn dữ liệu nhạy cảm**, tránh ghi credentials, token, toàn bộ payload khách hàng hoặc thông tin định danh vào log.

## 11. Các quyết định cho môi trường production

### Quyền và bảo vệ secret

Dùng IAM role ngắn hạn với nguyên tắc least privilege; tách role môi trường dev/staging/prod. Nếu ứng dụng cần lưu secret ngoài phần cấu hình, cân nhắc AWS Secrets Manager hoặc Parameter Store cho đúng loại dữ liệu. DynamoDB đã mã hóa dữ liệu lưu trữ (at rest) nhưng vẫn cần TLS khi kết nối, chính sách truy cập, kiểm soát dữ liệu nhạy cảm ở tầng ứng dụng, và quy trình sao lưu/phục hồi.

### Chi phí, độ trễ và khả năng mở rộng

DynamoDB có các lựa chọn capacity như on-demand và provisioned. Cân nhắc lưu lượng đọc/ghi, kích thước item, index, TTL, backup, số request và vùng truy cập. `Query` theo key thường phù hợp hơn `Scan` trên bảng lớn; GSI tăng khả năng truy vấn nhưng đi kèm chi phí lưu trữ và ghi.

### Tính đúng đắn dữ liệu

- `save` không tự đảm bảo duy nhất theo logic nghiệp vụ; dùng conditional writes khi chống ghi trùng là bắt buộc.
- DynamoDB transaction không tương đương việc thêm `@Transactional` của JPA vào mọi phương thức repository; hãy dùng transaction API phù hợp nếu có nhiều thay đổi cần atomic.
- Retry `ThrottlingException` / lỗi mạng theo cơ chế backoff của SDK và thiết kế ghi idempotent; không retry mù với mọi lỗi, nhất là khi kết quả ghi trước đó chưa rõ.
- DynamoDB giới hạn kích thước một item; tài liệu/ảnh lớn nên lưu ở S3 và chỉ giữ metadata/tham chiếu trong bảng.
- Nếu cần đọc theo nhiều chiều thường xuyên, thiết kế thêm GSI trước khi triển khai; lưu ý dữ liệu index có thể cập nhật bất đồng bộ và việc truy vấn GSI không hỗ trợ strong consistency.

### Ranh giới giữa các cloud provider

Ví dụ này dành cho DynamoDB của AWS, không phải API chung cho Azure Cosmos DB hoặc Google Cloud Firestore. Khi xây ứng dụng đa cloud, nên đặt interface nghiệp vụ của repository ở tầng ứng dụng, để từng adapter cho AWS/Azure/GCP thực thi phù hợp với mô hình key/index, consistency, giao dịch và IAM của provider tương ứng.

## 12. Bài thực hành mở rộng

1. Thêm `GSI` để tra cứu đặt chỗ theo `propertyId` và thời gian; ghi rõ truy vấn nào dùng primary key, truy vấn nào dùng index và vì sao tránh `Scan`.
2. Thêm thao tác “chỉ tạo khi chưa tồn tại” bằng Enhanced Client conditional write; chạy hai request tạo cùng key và xử lý `ConditionalCheckFailedException`.
3. Tích hợp Testcontainers trong CI để container/bảng được tạo tự động; kiểm tra CRUD và quyền truy cập tại môi trường thử nghiệm.
4. Đo sự khác biệt giữa `Query` theo tenant và `Scan` toàn bảng khi số item tăng; quan sát số trang, consumed capacity và giới hạn trả kết quả.
5. So sánh khả năng ứng dụng khi chuyển từ DynamoDB sang Azure Cosmos DB hoặc Google Cloud Firestore: danh tính, khóa dữ liệu, SDK, mô hình truy vấn và chi phí.

## Tài liệu tham khảo

- [Spring Cloud AWS 3.4.2 – DynamoDb Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): starter, cấu hình credentials/region/endpoint, template và tên bảng.
- [DynamoDbTemplate API – Spring Cloud AWS 3.4.0](https://docs.awspring.io/spring-cloud-aws/docs/3.4.0/apidocs/io/awspring/cloud/dynamodb/DynamoDbTemplate.html): chữ ký `save`, `load`, `query`, `delete` và các thao tác khác.
- [Spring Cloud AWS 4.1.1 – Reference](https://docs.awspring.io/spring-cloud-aws/docs/4.1.1/reference/html/index.html): đối chiếu khi dùng dòng thư viện mới hơn.
- [AWS SDK for Java 2.x – DynamoDB Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html): table schema, entity mapper và thao tác nâng cao.
- [AWS DynamoDB Developer Guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html): key, query, index, consistency, IAM, capacity và giới hạn của dịch vụ.
