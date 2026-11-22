# Aggregation bằng Spring Data và ánh xạ kết quả trong MongoDB

MongoDB Aggregation Framework xử lý dữ liệu qua một **pipeline gồm nhiều stage**. Trong ứng dụng Spring Boot sử dụng Spring Data MongoDB, lập trình viên không nhất thiết phải viết toàn bộ pipeline dưới dạng BSON/JSON thủ công: có thể dùng **Aggregation API**, **Criteria**, **MongoTemplate**, các phép **project, group, sort, unwind, lookup** và ánh xạ kết quả thành **Java DTO/record**. Đây là cách hữu ích để xây dựng dashboard doanh thu, thống kê đơn hàng, báo cáo hoạt động, phân tích theo thời gian hoặc kết hợp thông tin giữa các collection.

Điểm dễ sai không chỉ ở cú pháp pipeline. Sau **group**, MongoDB thường đặt khóa nhóm vào **_id**; sau **project**, các field có thể bị đổi tên hoặc biến mất; kết quả phép tính có thể là **Decimal128**, **Long**, **Double**, **Date** hoặc **null**. Nếu Java DTO không khớp shape/type thực tế, Spring Data có thể ánh xạ thiếu field, lỗi chuyển kiểu hoặc tạo kết quả khác mong đợi. Ngoài ra, **@Field** trên entity ảnh hưởng cách Spring Data ánh xạ tên thuộc tính Java sang tên BSON trong một số kiểu aggregation.

Bài học thuộc chương **Spring Data MongoDB**, tập trung đồng thời vào **xây pipeline đúng**, **đọc kết quả đúng** và **kiểm soát hiệu năng, vòng đời, tính toàn vẹn dữ liệu**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích luồng dữ liệu qua các stage của MongoDB aggregation.
2. Dùng **Aggregation.newAggregation(...)** và **MongoTemplate.aggregate(...)**.
3. Phân biệt **Aggregation**, **TypedAggregation**, **AggregationOperation**, **AggregationResults**.
4. Tạo pipeline với **$match, $project, $group, $sort, $limit, $skip**.
5. Xử lý mảng bằng **$unwind**, join bằng **$lookup** và báo cáo đa nhánh bằng **$facet**.
6. Ánh xạ khóa nhóm **_id**, aliases, kiểu Number/Date và nested documents sang DTO hoặc Java record.
7. Hiểu vai trò của **@Document**, **@Id**, **@Field** trong input mapping và collection selection.
8. Biết khi nào dùng **Document**, custom stage hoặc **@Aggregation** trên repository.
9. Dùng **AggregationOptions**, stream và cursor đúng cách khi dữ liệu lớn.
10. Kiểm tra shape của kết quả, test trên tập dữ liệu nhỏ và đọc explain để tối ưu.

**Phạm vi:** ví dụ sử dụng Spring Data MongoDB với **MongoTemplate**, Java 17+ và MongoDB server hỗ trợ các stage được minh họa. APIs có thể khác nhau giữa các nhánh Spring Data/Spring Boot; khi chạy thực tế hãy dùng tài liệu/API reference đúng phiên bản dependency của dự án. Các ví dụ là bài học, không phải giao dịch/tính tiền production đã được kiểm toán.

## 2. Aggregation Framework xử lý dữ liệu thế nào?

Một pipeline là danh sách các stage chạy theo thứ tự:

~~~text
Collection orders
      |
      v
$match: chọn đơn hàng đúng tenant, PAID
      |
      v
$group: gộp theo region, đếm và cộng tiền
      |
      v
$project: đổi _id thành region, chọn field trả về
      |
      v
$sort: revenue giảm dần
      |
      v
Result documents
      |
      v
Spring Data converter -> Java DTO
~~~

Đầu ra của stage trước là đầu vào của stage sau. Vì vậy:

- **$match** trước **$group** lọc từng document nguồn.
- **$match** sau **$group** lọc **các nhóm** đã tổng hợp, không phải document gốc.
- **$project** có thể bỏ một field cần sử dụng ở stage sau.
- **$sort** trước **$limit** thường tạo top-N có ý nghĩa; limit trước sort có thể chỉ sắp xếp một subset tùy ý.
- **$unwind** có thể nhân số document, khiến các phép **count/sum** sau đó phải tính theo số dòng đã unwind.

### 2.1. Phân biệt find() và aggregate()

**find()** thích hợp với truy vấn thông thường: lọc, projection, sort, limit và đọc document.

**aggregate()** thích hợp khi muốn biến đổi dữ liệu, tính toán, gộp nhóm, join, phân nhánh hoặc tạo cấu trúc kết quả khác document đầu vào.

Ví dụ:

~~~javascript
db.orders.find({
  tenant_id: "TENANT-A",
  status: "PAID"
});
~~~

so với:

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $group: {
      _id: "$region",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$gross_amount" }
    }
  },
  { $project: { _id: 0, region: "$_id", orderCount: 1, revenue: 1 } },
  { $sort: { revenue: -1 } }
]);
~~~

Ví dụ thứ hai trả **một dòng cho mỗi region**, không còn một dòng cho mỗi order.

## 3. Chuẩn bị Spring Data MongoDB

### 3.1. Dependency

Với dự án Spring Boot, thường dùng starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Ví dụ Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
}
~~~

Nên để **Spring Boot BOM/dependency management** chọn các bản Spring Data MongoDB và Java Driver tương thích. Không ghép ngẫu nhiên Spring Data phiên bản mới với MongoDB driver phiên bản cũ mà chưa kiểm chứng.

### 3.2. Kết nối

Ví dụ file **application.yml**:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Biến môi trường **MONGODB_URI** chứa connection string do môi trường chạy cấp. Không để credentials thật trong source, bài học hoặc log. Một số phiên bản Spring Boot có thay đổi namespace thuộc tính cấu hình; hãy đối chiếu tài liệu đúng version.

Spring Boot thường cung cấp **MongoTemplate** dưới dạng bean khi auto-configuration thành công. Một service có thể inject:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final MongoTemplate mongoTemplate;

    public ReportService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }
}
~~~

Không tạo **MongoClient** mới mỗi khi cần chạy báo cáo. **MongoTemplate** và client được quản lý theo vòng đời ứng dụng.

### 3.3. Những import thường gặp

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.domain.Sort;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;
~~~

Static imports giúp code ngắn gọn:

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("status").is("PAID")),
        group("region").count().as("orderCount"),
        sort(Sort.Direction.DESC, "orderCount")
);
~~~

## 4. Bộ dữ liệu mẫu: đơn hàng nhiều tenant

Để các kết quả dự đoán được, dùng collection **spring_agg_lab.orders** trên một **database thử nghiệm**. Dữ liệu có field BSON name khác tên Java property để minh họa mapping.

### 4.1. Document mẫu

~~~javascript
use spring_agg_lab

db.orders.insertMany([
  {
    _id: "O-1001",
    tenant_id: "TENANT-A",
    status: "PAID",
    region: "NORTH",
    gross_amount: NumberDecimal("120.50"),
    placed_at: ISODate("2026-10-01T09:00:00Z"),
    customer_ref: "C-1",
    items: [
      { sku: "BOOK-1", quantity: 2 },
      { sku: "PEN-1", quantity: 3 }
    ]
  },
  {
    _id: "O-1002",
    tenant_id: "TENANT-A",
    status: "PAID",
    region: "SOUTH",
    gross_amount: NumberDecimal("75.00"),
    placed_at: ISODate("2026-10-02T12:00:00Z"),
    customer_ref: "C-2",
    items: [{ sku: "BOOK-1", quantity: 1 }]
  },
  {
    _id: "O-1003",
    tenant_id: "TENANT-A",
    status: "NEW",
    region: "NORTH",
    gross_amount: NumberDecimal("10.00"),
    placed_at: ISODate("2026-10-03T08:00:00Z"),
    customer_ref: "C-1",
    items: [{ sku: "PEN-1", quantity: 1 }]
  },
  {
    _id: "O-1004",
    tenant_id: "TENANT-A",
    status: "PAID",
    region: "NORTH",
    gross_amount: NumberDecimal("60.25"),
    placed_at: ISODate("2026-10-04T16:00:00Z"),
    customer_ref: "C-3",
    items: [{ sku: "BAG-1", quantity: 1 }]
  },
  {
    _id: "O-1005",
    tenant_id: "TENANT-B",
    status: "PAID",
    region: "NORTH",
    gross_amount: NumberDecimal("999.00"),
    placed_at: ISODate("2026-10-05T09:00:00Z"),
    customer_ref: "C-B",
    items: [{ sku: "BOOK-1", quantity: 100 }]
  },
  {
    _id: "O-1006",
    tenant_id: "TENANT-A",
    status: "CANCELLED",
    region: "SOUTH",
    gross_amount: NumberDecimal("30.00"),
    placed_at: ISODate("2026-10-06T15:00:00Z"),
    customer_ref: "C-2",
    items: [{ sku: "PEN-1", quantity: 5 }]
  },
  {
    _id: "O-1007",
    tenant_id: "TENANT-A",
    status: "PAID",
    region: "SOUTH",
    gross_amount: NumberDecimal("40.00"),
    placed_at: ISODate("2026-10-07T10:00:00Z"),
    customer_ref: "C-2",
    items: [{ sku: "PEN-1", quantity: 4 }]
  },
  {
    _id: "O-1008",
    tenant_id: "TENANT-A",
    status: "PAID",
    region: "NORTH",
    gross_amount: NumberDecimal("24.25"),
    placed_at: ISODate("2026-10-08T14:00:00Z"),
    customer_ref: "C-1",
    items: [{ sku: "BOOK-1", quantity: 1 }]
  }
]);
~~~

**Chú ý:** sử dụng **_id cố định**, nên insertMany lại trên cùng collection sẽ gặp duplicate key. Chạy một lần trong lab sạch hoặc sử dụng upsert có kiểm soát; **không xóa dữ liệu production** để chạy ví dụ.

### 4.2. Kết quả mong đợi

Chỉ xét **TENANT-A** và **PAID**, có **5 orders**:

| Region | Các order | orderCount | revenue |
|---|---|---:|---:|
| NORTH | O-1001, O-1004, O-1008 | 3 | 205.00 |
| SOUTH | O-1002, O-1007 | 2 | 115.00 |

Không được tính order **O-1005** của **TENANT-B** dù nó có doanh thu cao; không tính các order **NEW** hoặc **CANCELLED**. Đây cũng là một bài kiểm tra **tenant isolation**.

### 4.3. Tạo index theo query pattern

~~~javascript
db.orders.createIndex({
  tenant_id: 1,
  status: 1,
  placed_at: -1
});
~~~

Index này minh họa một truy vấn thực tế thường lọc theo tenant/status và khoảng thời gian. Việc index có được dùng, chi phí và hiệu quả với pipeline cụ thể phải xác minh bằng explain; không phải cứ tạo index là mọi stage group/sort sẽ nhanh.

## 5. Ánh xạ MongoDB document vào Java domain model

Spring Data MongoDB phân biệt **tên thuộc tính Java** và **tên field trong BSON**. Đây là phần quan trọng với TypedAggregation.

### 5.1. Entity cho orders

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("orders")
public class OrderEntity {
    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String status;
    private String region;

    @Field(value = "gross_amount", targetType = FieldType.DECIMAL128)
    private BigDecimal grossAmount;

    @Field("placed_at")
    private Instant placedAt;

    @Field("customer_ref")
    private String customerRef;

    private List<OrderLine> items;

    public OrderEntity() {
    }

    // Getters/setters hoặc constructor binding theo chuẩn dự án.
}

public class OrderLine {
    private String sku;
    private int quantity;

    public OrderLine() {
    }

    // Getters/setters.
}
~~~

Trong project Java thực tế, mỗi public top-level class nên ở **file riêng**; hai declarations trong code block trên để trình bày mapping liền mạch.

**Điều cần nhớ:**

- Property **tenantId** ánh xạ tới BSON field **tenant_id**.
- Property **grossAmount** ánh xạ tới **gross_amount**, dữ liệu mẫu là **Decimal128**.
- Property **placedAt** ánh xạ tới **placed_at**.
- **@Document("orders")** khai báo collection mặc định khi dùng domain type.
- **@Id** tương ứng với **_id**.

Trong aggregation có đầu vào typed, Spring Data có thể dùng metadata từ entity để chuyển field references Java sang tên BSON. Nếu tự viết raw JSON, bạn phải hiểu rõ khi nào mapping này được áp dụng.

## 6. Bốn khái niệm cốt lõi của Spring Data Aggregation API

| Thành phần | Vai trò |
|---|---|
| **AggregationOperation** | Mô tả một stage trong pipeline, ví dụ match/group/project |
| **Aggregation** | Chứa toàn bộ pipeline và options |
| **TypedAggregation<T>** | Aggregation có input domain class để ánh xạ field |
| **AggregationResults<R>** | Đóng gói danh sách các result objects đã map và raw response |

Tổng quan:

~~~text
Java domain / input collection
              |
              v
newAggregation(operation1, operation2, ...)
              |
              v
MongoTemplate.aggregate(...)
              |
              v
MongoDB executes BSON pipeline
              |
              v
AggregationResults<ResultDto>
              |
              +--> getMappedResults()
              +--> getUniqueMappedResult()
              +--> getRawResults()
~~~

**Aggregation object không tự chạy query**; nó mô tả query. **MongoTemplate.aggregate(...)** mới gửi command qua driver và thực thi.

### 6.1. Không có input class

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("status").is("PAID")),
        group("region").count().as("orderCount")
);

AggregationResults<Document> results =
        mongoTemplate.aggregate(agg, "orders", Document.class);
~~~

Trong biến thể này, cần truyền **tên collection "orders"** rõ ràng vì aggregation không có input type. Những tên field trong pipeline phải tương ứng với representation mà bạn đang sử dụng.

### 6.2. Có input class

~~~java
TypedAggregation<OrderEntity> agg = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A")),
        group("region").count().as("orderCount")
);

AggregationResults<Document> results =
        mongoTemplate.aggregate(agg, Document.class);
~~~

Ở đây Spring Data có đầu vào là **OrderEntity**, có thể suy ra collection **orders** và map **tenantId** sang **tenant_id**.

Từ Spring Data MongoDB 3.2, truy cập một field/property không tồn tại trong typed aggregation **không còn mặc định ném lỗi** như trước. Nếu muốn strict validation, xem **AggregationOptions.strictMapping()** của phiên bản được dùng.

## 7. Ví dụ hoàn chỉnh: tính doanh thu theo khu vực

### 7.1. MongoDB pipeline đích

Trước khi viết Java, xác định kết quả mong muốn bằng MongoDB aggregation thuần:

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $group: {
      _id: "$region",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$gross_amount" }
    }
  },
  {
    $project: {
      _id: 0,
      region: "$_id",
      orderCount: 1,
      revenue: 1
    }
  },
  { $sort: { revenue: -1 } }
]);
~~~

Output gần như:

~~~javascript
[
  { region: "NORTH", orderCount: 3, revenue: NumberDecimal("205.00") },
  { region: "SOUTH", orderCount: 2, revenue: NumberDecimal("115.00") }
]
~~~

**Điểm quan trọng:** $group tạo **_id** là giá trị của region. $project sau đó biến **_id thành region** để DTO có cấu trúc rõ ràng.

### 7.2. DTO bằng Java record

Với Java 17+ và Spring Data MongoDB hỗ trợ constructor/record mapping:

~~~java
import java.math.BigDecimal;

public record RegionRevenue(
        String region,
        long orderCount,
        BigDecimal revenue
) {
}
~~~

Đây là **output DTO**, không phải entity OrderEntity. Pipeline tạo document có **region**, **orderCount**, **revenue** nên record khai báo đúng những tên đó.

### 7.3. Repository báo cáo sử dụng TypedAggregation

~~~java
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Repository;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

@Repository
public class OrderAnalyticsRepository {
    private final MongoTemplate mongoTemplate;

    public OrderAnalyticsRepository(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<RegionRevenue> revenueByRegion(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }

        TypedAggregation<OrderEntity> aggregation = newAggregation(
                OrderEntity.class,
                match(Criteria.where("tenantId").is(tenantId)
                        .and("status").is("PAID")),
                group("region")
                        .count().as("orderCount")
                        .sum("grossAmount").as("revenue"),
                project("orderCount", "revenue")
                        .and("_id").as("region")
                        .andExclude("_id"),
                sort(Sort.Direction.DESC, "revenue")
        );

        AggregationResults<RegionRevenue> results =
                mongoTemplate.aggregate(
                        aggregation, RegionRevenue.class);

        return results.getMappedResults();
    }
}
~~~

**Giải thích từng thành phần:**

1. **newAggregation(OrderEntity.class, ...)** cho Spring Data biết tên field/domain đầu vào.
2. **Criteria.where("tenantId")** dùng property Java; typed mapping có thể chuyển thành BSON **tenant_id**.
3. **group("region")** gom theo region.
4. **count().as("orderCount")** đếm số orders trong mỗi nhóm.
5. **sum("grossAmount").as("revenue")** cộng BSON **gross_amount** đã được map.
6. **project(...).and("_id").as("region")** phẳng hóa khóa nhóm thành field khớp DTO.
7. **andExclude("_id")** loại trường _id khỏi output cuối.
8. **sort(DESC,"revenue")** sắp xếp theo alias đã tạo ở group, không theo field nguồn.
9. **getMappedResults()** trả danh sách Java records.

Trong service nhiều tenant, tenantId **phải đến từ authentication/authorization context**, không được cho caller tự khai tenantId của tổ chức khác mà service không kiểm tra.

### 7.4. Tại sao không chỉ map _id vào region?

Nếu bỏ bước project:

~~~javascript
{ _id: "NORTH", orderCount: 3, revenue: NumberDecimal("205.00") }
~~~

thì record **RegionRevenue(String region, ...)** không có field **region** để đọc trực tiếp. Có thể định nghĩa DTO theo **_id** và dùng annotation/constructor mapping phù hợp, nhưng biến **_id -> region** trong pipeline làm hợp đồng báo cáo rõ ràng, ổn định và ít lệ thuộc quy tắc mapping ngầm.

### 7.5. Không map group result vào OrderEntity

Sau group, output không còn id, tenantId, grossAmount, placedAt... theo schema OrderEntity. Nếu dùng:

~~~java
mongoTemplate.aggregate(aggregation, OrderEntity.class);
~~~

thì có thể tạo các entity với nhiều field **null/default**, mất revenue/orderCount, hoặc gặp mapping errors. Hãy dùng **DTO riêng cho output shape** hoặc **Document** khi đang khám phá schema.

## 8. AggregationResults và cách lấy kết quả

**AggregationResults<T>** chứa kết quả đã ánh xạ và raw response.

~~~java
AggregationResults<RegionRevenue> results =
        mongoTemplate.aggregate(
                aggregation, RegionRevenue.class);

List<RegionRevenue> rows = results.getMappedResults();
org.bson.Document raw = results.getRawResults();
~~~

Các phương thức quan trọng:

| Phương thức | Ý nghĩa |
|---|---|
| **getMappedResults()** | Danh sách các result DTO; rỗng nếu không có dòng |
| **getUniqueMappedResult()** | Một dòng hoặc null; ném IllegalArgumentException nếu có nhiều hơn một dòng |
| **getRawResults()** | BSON Document phản hồi aggregate cấp driver, hữu ích để chẩn đoán |
| **iterator()** | Duyệt các mapped objects trong AggregationResults |

### 8.1. Khi nào dùng getUniqueMappedResult()?

Một pipeline **không group theo region** mà tính tổng toàn tenant:

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("tenant_id").is("TENANT-A")
                .and("status").is("PAID")),
        group()
                .count().as("orderCount")
                .sum("gross_amount").as("revenue"),
        project("orderCount", "revenue").andExclude("_id")
);

AggregationResults<TotalRevenue> results =
        mongoTemplate.aggregate(agg, "orders", TotalRevenue.class);

TotalRevenue total = results.getUniqueMappedResult();
~~~

DTO:

~~~java
import java.math.BigDecimal;

public record TotalRevenue(
        long orderCount,
        BigDecimal revenue
) {}
~~~

Với dữ liệu mẫu, output mong đợi là:

~~~javascript
{ orderCount: 5, revenue: NumberDecimal("320.00") }
~~~

Ở đây **group()** tạo một nhóm tổng toàn bộ những documents đã qua $match; có thể trả một dòng hoặc không có dòng theo dữ liệu/stage. Không gọi getUniqueMappedResult() cho báo cáo **một dòng mỗi region**, vì nó có thể có nhiều kết quả.

### 8.2. Empty results khác 0

Nếu không có order nào phù hợp, kết quả của một pipeline **$group không có input** có thể là **không có document** chứ không phải một document có revenue = 0. Vì vậy API trả báo cáo cần quyết định:

- Trả danh sách rỗng.
- Trả DTO totals với 0 theo hợp đồng nghiệp vụ.
- Trả một cấu trúc báo cáo có trạng thái **NO_DATA**.

Đừng gọi **getUniqueMappedResult().revenue()** khi kết quả có thể là null.

### 8.3. RawResults dùng để chẩn đoán, không phải DTO công khai

Không trả nguyên **getRawResults()** ra HTTP client chỉ vì dễ serialise; nó có thể chứa metadata nội bộ, BSON types hoặc dữ liệu nhạy cảm. Ứng dụng nên trả DTO có các field được kiểm soát.

## 9. $match với Criteria: trước và sau group

### 9.1. Match đầu pipeline

~~~java
match(Criteria.where("tenantId").is(tenantId)
        .and("status").is("PAID"))
~~~

Trong **TypedAggregation<OrderEntity>**, property tenantId được map tới tenant_id, dựa vào **@Field**. Với **Aggregation** không typed và tên collection thuần, code có thể cần:

~~~java
match(Criteria.where("tenant_id").is(tenantId)
        .and("status").is("PAID"))
~~~

Đây là nguồn lỗi rất phổ biến: pipeline chạy mà **không match** vì dùng tên thuộc tính Java trong một pipeline BSON đang đòi tên field thực.

### 9.2. Match sau group là filter các nhóm

Ví dụ muốn chỉ region có doanh thu >= 150:

~~~java
TypedAggregation<OrderEntity> agg = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A")
                .and("status").is("PAID")),
        group("region")
                .sum("grossAmount").as("revenue")
                .count().as("orderCount"),
        match(Criteria.where("revenue").gte(
                new java.math.BigDecimal("150.00"))),
        project("revenue", "orderCount")
                .and("_id").as("region")
                .andExclude("_id")
);
~~~

Với dữ liệu mẫu, chỉ **NORTH** đạt >= 150. Điều kiện thứ hai dùng **revenue**, alias của group output, không phải tên property **grossAmount**.

### 9.3. Không đưa filter bảo mật ra sau $lookup hoặc cuối pipeline

Một pipeline có thể vẫn chỉ trả đúng tenant nhưng quét/join một lượng dữ liệu quá lớn trước khi lọc tenant. Với multi-tenant data, nên đưa **mandatory tenant filter** vào sớm khi semantics cho phép, và phải xét quyền của các collection join.

Không kết luận “đầu ra cuối có tenantId đúng” là đủ để mọi stage trung gian không bao giờ xử lý dữ liệu ngoài quyền. Thiết kế authorization trước khi thực thi.

## 10. $project và field aliases

**$project** chọn field, đổi tên và tạo expression fields. Field bị loại ở một stage thường không còn có thể tham chiếu ở stage sau.

### 10.1. Chọn trường và đổi tên

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("status").is("PAID")),
        project()
                .and("_id").as("orderId")
                .and("gross_amount").as("amount")
                .and("region").as("region")
                .andExclude("_id")
);
~~~

Với untyped pipeline này, output:

~~~javascript
{
  orderId: "O-1001",
  amount: NumberDecimal("120.50"),
  region: "NORTH"
}
~~~

### 10.2. Các field bị project loại bỏ

~~~text
Input:
  _id, tenant_id, region, status, gross_amount

$project:
  region, gross_amount

Next stage:
  status không còn tồn tại
~~~

Nếu cần lọc status, tốt hơn **$match trước $project** trong trường hợp có cùng semantics và có thể tận dụng index.

### 10.3. Tạo field bằng biểu thức

MongoDB aggregation có nhiều expression operators như **$add, $multiply, $cond, $ifNull, $dateToString**. Spring Data có các builder của **ArithmeticOperators**, **ConditionalOperators**, **DateOperators**, cùng API phép tính trong projection.

Ví dụ phép tính minh họa (không dùng để tính thuế/tiền thật):

~~~java
Aggregation agg = newAggregation(
        project("region")
                .and("gross_amount")
                .multiply(2)
                .as("doubleAmount")
);
~~~

Pipeline trên tạo **doubleAmount** từ field BSON gross_amount. Khi input typed, có thể tham chiếu property **grossAmount** thay cho BSON **gross_amount**.

**Cần chú ý numeric types**: hệ số integer, double hoặc Decimal128 có thể ảnh hưởng kiểu kết quả. Không trộn Double vào phép tính tiền production mà chưa có quy tắc làm tròn/scale.

### 10.4. previousOperation() và _id

Spring Data có cú pháp lấy giá trị khóa của thao tác group trước đó:

~~~java
Aggregation agg = newAggregation(
        group("region").count().as("n"),
        project("n").and("region").previousOperation()
);
~~~

Đây là mẫu theo tài liệu Spring Data để đưa giá trị khóa nhóm ra alias. Cách khác dùng **.and("_id").as("region")**, dễ liên hệ với raw MongoDB pipeline. Chọn một cách rõ ràng và kiểm tra output Document.

## 11. $group và kiểu dữ liệu tổng hợp

Những phép thường gặp:

| Spring Data GroupOperation | MongoDB accumulator | Ý nghĩa |
|---|---|---|
| **count().as("n")** | $sum: 1 | Đếm document trong nhóm |
| **sum("grossAmount").as("total")** | $sum | Tổng số |
| **avg("grossAmount").as("average")** | $avg | Trung bình |
| **min("grossAmount").as("minimum")** | $min | Giá trị nhỏ nhất |
| **max("grossAmount").as("maximum")** | $max | Giá trị lớn nhất |
| **first("field").as("firstValue")** | $first | Giá trị theo thứ tự input |
| **last("field").as("lastValue")** | $last | Giá trị theo thứ tự input |
| **push("field").as("values")** | $push | Thu thập giá trị vào array |
| **addToSet("field").as("uniqueValues")** | $addToSet | Thu thập tập giá trị không trùng theo semantics MongoDB |

### 11.1. Group nhiều trường

~~~javascript
{
  $group: {
    _id: { region: "$region", status: "$status" },
    n: { $sum: 1 }
  }
}
~~~

Với Spring Data có thể:

~~~java
group("region", "status")
        .count().as("n")
~~~

Output **_id là object**:

~~~javascript
{ _id: { region: "NORTH", status: "PAID" }, n: 3 }
~~~

Không map _id object này thẳng vào **String id**. Dùng nested DTO hoặc project ra các properties:

~~~javascript
{
  $project: {
    _id: 0,
    region: "$_id.region",
    status: "$_id.status",
    n: 1
  }
}
~~~

Nếu dùng Spring Data projection builder, cần tham chiếu paths của **_id** đúng shape từ group stage; khi alias mapping phức tạp, có thể dùng **Document** để quan sát output trước khi chọn DTO.

### 11.2. $first/$last cần thứ tự có ý nghĩa

Nếu muốn ngày đầu/cuối một order trong mỗi region, cần **$sort** trước **$group** khi semantics dựa vào thứ tự:

~~~javascript
[
  { $sort: { placed_at: 1, _id: 1 } },
  {
    $group: {
      _id: "$region",
      firstOrder: { $first: "$_id" },
      lastOrder: { $last: "$_id" }
    }
  }
]
~~~

Không cho rằng $first là “ngày sớm nhất” nếu chưa sort theo ngày hoặc không sử dụng accumulator thích hợp.

### 11.3. $sum không tự biến String thành số

Nếu dữ liệu cũ lưu gross_amount là **"120.50"** (String), kết quả $sum không phải tổng số học đáng tin như với Decimal128. Cần đồng nhất schema, validate type và migration thay vì thêm một cast tùy tiện mà không kiểm tra lỗi dữ liệu.

## 12. $unwind: biến từng phần tử mảng thành một dòng

Một order chứa:

~~~javascript
{
  _id: "O-1001",
  items: [
    { sku: "BOOK-1", quantity: 2 },
    { sku: "PEN-1", quantity: 3 }
  ]
}
~~~

**$unwind: "$items"** tạo hai document pipeline:

~~~javascript
{ _id: "O-1001", items: { sku: "BOOK-1", quantity: 2 } }
{ _id: "O-1001", items: { sku: "PEN-1", quantity: 3 } }
~~~

### 12.1. Đếm số lượng sản phẩm đã bán theo SKU

Raw MongoDB:

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      quantitySold: { $sum: "$items.quantity" }
    }
  },
  { $project: { _id: 0, sku: "$_id", quantitySold: 1 } },
  { $sort: { quantitySold: -1, sku: 1 } }
]);
~~~

Spring Data:

~~~java
TypedAggregation<OrderEntity> agg = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A")
                .and("status").is("PAID")),
        unwind("items"),
        group("items.sku")
                .sum("items.quantity").as("quantitySold"),
        project("quantitySold")
                .and("_id").as("sku")
                .andExclude("_id"),
        sort(Sort.by(
                Sort.Order.desc("quantitySold"),
                Sort.Order.asc("sku")))
);

List<SkuSales> rows = mongoTemplate
        .aggregate(agg, SkuSales.class)
        .getMappedResults();
~~~

DTO:

~~~java
public record SkuSales(String sku, long quantitySold) {}
~~~

Với dữ liệu mẫu:

| SKU | Quantity sold |
|---|---:|
| PEN-1 | 7 |
| BOOK-1 | 4 |
| BAG-1 | 1 |

Tính bằng các đơn **PAID thuộc TENANT-A**: PEN-1 = 3+4; BOOK-1 = 2+1+1; BAG-1 = 1.

### 12.2. Lỗi nhân đôi số đơn hàng khi unwind

Nếu đếm:

~~~javascript
[
  { $unwind: "$items" },
  { $group: { _id: "$region", orderCount: { $sum: 1 } } }
]
~~~

thì **orderCount** ở đây là **số dòng item** sau unwind, **không phải số order**. Nếu một order có năm items, nó đóng góp năm dòng. Muốn đếm orders, hãy group trước theo order ID, dùng addToSet(orderId) rồi tính độ lớn tập nếu phù hợp, hoặc tổ chức pipeline khác tránh đếm trùng.

### 12.3. preserveNullAndEmptyArrays

Với document không có items hoặc items = [], unwind mặc định có thể loại document ấy khỏi pipeline. Khi muốn giữ lại:

~~~java
unwind("items", true)
~~~

Trong các bản Spring Data hỗ trợ overload này, tham số **true** tương ứng với preserveNullAndEmptyArrays. Khi đó stage sau phải xử lý **items = null/missing**, tránh cộng giá trị không tồn tại như dữ liệu hợp lệ.

### 12.4. Include array index

MongoDB có tùy chọn **includeArrayIndex** để giữ vị trí phần tử trong mảng. Spring Data cũng có builder/overload cho UnwindOperation theo phiên bản. Chỉ sử dụng khi cần giữ **thứ tự và vị trí gốc**, không mặc định mọi phần tử mảng đều có index sau unwind.

## 13. $lookup: kết hợp dữ liệu nhiều collection

Tạo một collection customers nhỏ:

~~~javascript
db.customers.insertMany([
  {
    _id: "C-1",
    tenant_id: "TENANT-A",
    name: "An",
    tier: "GOLD"
  },
  {
    _id: "C-2",
    tenant_id: "TENANT-A",
    name: "Binh",
    tier: "STANDARD"
  },
  {
    _id: "C-3",
    tenant_id: "TENANT-A",
    name: "Chi",
    tier: "GOLD"
  },
  {
    _id: "C-B",
    tenant_id: "TENANT-B",
    name: "Other tenant",
    tier: "PRIVATE"
  }
]);
~~~

### 13.1. Lookup đơn giản

Mỗi order có **customer_ref**, trỏ tới **customers._id**.

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $lookup: {
      from: "customers",
      localField: "customer_ref",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      customerName: "$customer.name",
      region: 1
    }
  }
]);
~~~

Spring Data:

~~~java
TypedAggregation<OrderEntity> agg = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A")
                .and("status").is("PAID")),
        lookup("customers", "customerRef", "_id", "customer"),
        unwind("customer"),
        project("region")
                .and("_id").as("orderId")
                .and("customer.name").as("customerName")
                .andExclude("_id")
);
~~~

DTO:

~~~java
public record OrderCustomerRow(
        String orderId,
        String region,
        String customerName
) {}
~~~

**Lưu ý mapping:** khi dùng **TypedAggregation<OrderEntity>**, Spring Data có thể ánh xạ **customerRef** thành **customer_ref** từ @Field. Với raw/untyped pipeline, dùng chính tên BSON trong collection. Với output của $lookup, **customer** là alias stage, không phải một property đã có sẵn trong OrderEntity.

### 13.2. $lookup trả về array

Ngay cả khi chỉ join tới một customer theo _id, output của **$lookup** vẫn là **mảng**:

~~~javascript
{
  _id: "O-1001",
  customer: [
    { _id: "C-1", name: "An", tier: "GOLD" }
  ]
}
~~~

**$unwind("customer")** biến array một phần tử thành object, giúp DTO có **customerName** rõ ràng. Khi customer không tồn tại, unwind mặc định có thể loại order; nếu cần giữ order, dùng preserveNullAndEmptyArrays và DTO cho phép customerName null.

### 13.3. Tránh rò rỉ dữ liệu giữa tenant khi lookup

Trong ví dụ, customer IDs là duy nhất toàn hệ thống; điều đó giảm nguy cơ vô tình ghép sai. Nhưng production có thể dùng IDs chỉ duy nhất **trong tenant**, hoặc dữ liệu bị thay đổi.

Vì vậy, join cần đảm bảo:

- Order phải thuộc tenant đã xác thực.
- Customer join cũng phải thuộc đúng tenant hoặc ACL cho phép.
- Không cho client tự chọn collection name/join keys tùy ý.
- Projection chỉ lấy những field được phép trả cho user.
- Khi cần điều kiện join phức tạp, sử dụng **pipeline form của $lookup** và xác minh chỉ mục/tính đúng đắn.

Không cho rằng chỉ $match orders.tenantId là đủ để mọi record trong collection customers chắc chắn an toàn.

### 13.4. Hiệu năng lookup

Index trên **foreignField** của collection join rất quan trọng. Với **foreignField="_id"**, MongoDB thường đã có _id index. Nếu join bằng trường khác, cân nhắc index theo query pattern. Join cardinality lớn có thể phình pipeline/memory; không dùng lookup để ghép mọi document của hai collection mà không có filter và giới hạn.

## 14. $facet: nhiều báo cáo trong cùng pipeline

**$facet** cho nhiều subpipelines xử lý cùng một tập tài liệu đầu vào. Ví dụ dashboard vừa cần doanh thu theo region, vừa cần số order theo status.

### 14.1. Kết quả cấu trúc

~~~javascript
{
  revenueByRegion: [
    { region: "NORTH", revenue: NumberDecimal("205.00") },
    { region: "SOUTH", revenue: NumberDecimal("115.00") }
  ],
  statusCounts: [
    { status: "PAID", count: 5 },
    { status: "NEW", count: 1 },
    { status: "CANCELLED", count: 1 }
  ]
}
~~~

Lưu ý: nếu prefilter ban đầu chỉ lấy **PAID**, nhánh **statusCounts** sẽ **không thể đếm NEW/CANCELLED**. Muốn các trạng thái, prefilter trước facet chỉ lọc **tenant** và để mỗi branch tự lọc điều kiện riêng.

### 14.2. Facet bằng Spring Data

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("tenant_id").is("TENANT-A")),
        facet(
                match(Criteria.where("status").is("PAID")),
                group("region").sum("gross_amount").as("revenue"),
                project("revenue")
                        .and("_id").as("region")
                        .andExclude("_id")
        ).as("revenueByRegion")
         .and(
                group("status").count().as("count"),
                project("count")
                        .and("_id").as("status")
                        .andExclude("_id")
        ).as("statusCounts")
);

AggregationResults<Document> result =
        mongoTemplate.aggregate(agg, "orders", Document.class);

Document dashboard = result.getUniqueMappedResult();
~~~

Ở đây dùng **Document** để minh họa nested arrays; phía dưới sẽ thiết kế DTO cho nested output. Các nhánh facet có thể được chạy trên một tập input chung, nhưng không vì thế mà cho rằng một facet luôn nhanh hơn nhiều truy vấn riêng. Hãy kiểm tra chi phí và giới hạn memory của stage.

### 14.3. $facet có giới hạn khác $group

**$facet** trả một document chứa các mảng output. Cần chú ý giới hạn kích thước document BSON (16 MiB) và giới hạn bộ nhớ của stage. **allowDiskUse** không thể khắc phục mọi giới hạn nội bộ của $facet. Tránh nhét hàng trăm nghìn documents vào một facet array chỉ để gửi trực tiếp cho UI.

## 15. $bucket và $bucketAuto cho báo cáo phân phối

**$bucket** phân nhóm theo các ranh giới được chọn, ví dụ đơn hàng theo mức tiền. **$bucketAuto** yêu cầu MongoDB tự chia dữ liệu thành số buckets xấp xỉ dự kiến.

MongoDB raw:

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $bucket: {
      groupBy: "$gross_amount",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("50"),
        NumberDecimal("100"),
        NumberDecimal("200")
      ],
      default: "OTHER",
      output: {
        count: { $sum: 1 }
      }
    }
  }
]);
~~~

Spring Data có builders **bucket(...)**, **bucketAuto(...)**. Với boundaries cần cùng kiểu BSON phù hợp và phải xác định inclusivity/exclusivity theo MongoDB; những giá trị ngoài boundaries đi vào **default** nếu có. Một bucket result có thể có **_id là Number hoặc String** tùy bucket, vì vậy không tự map tất cả vào một trường Java Integer nếu có default = "OTHER".

### 15.1. Vì sao bucket hữu ích?

Một báo cáo phân phối cần số đơn trong các khoảng:

~~~text
[0, 50)
[50, 100)
[100, 200)
OTHER
~~~

Đây là khác biệt với $group theo gross_amount exact, nơi mỗi giá trị số có thể tạo một nhóm riêng. Nên chọn boundaries từ yêu cầu nghiệp vụ và phân tích dữ liệu, không chỉ dùng bucketAuto khi cần những khoảng giá cố định trong báo cáo tài chính.

## 16. Biểu thức điều kiện và xử lý null

Trong nhiều nguồn, **discount** có thể missing/null; nếu cộng/trừ trực tiếp, biểu thức có thể trả null hoặc lỗi phụ thuộc operator và type.

### 16.1. $ifNull trong MongoDB

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discountSafe: {
        $ifNull: ["$discount", NumberDecimal("0")]
      }
    }
  }
]);
~~~

Spring Data cung cấp **ConditionalOperators.IfNull** và các conditional builders. Tùy phiên bản, có thể dùng:

~~~java
import org.springframework.data.mongodb.core.aggregation.ConditionalOperators;

Aggregation agg = newAggregation(
        project()
                .and(ConditionalOperators.ifNull("discount")
                        .then(0))
                .as("discountSafe")
);
~~~

Khi tiền tệ yêu cầu Decimal128, biểu thức fallback **0** kiểu integer trong ví dụ chỉ là minh họa; cần dùng giá trị và conversion phù hợp để không làm sai type/precision của phép tính tiếp theo.

### 16.2. $cond và phân nhóm theo điều kiện

Ví dụ MongoDB raw:

~~~javascript
{
  $project: {
    label: {
      $cond: [
        { $gte: ["$gross_amount", NumberDecimal("100")] },
        "LARGE",
        "SMALL"
      ]
    }
  }
}
~~~

Spring Data có **ConditionalOperators.when(...).then(...).otherwise(...)**. Khi sử dụng builder, đảm bảo expression tham chiếu đúng field đã tồn tại tại stage đó, đặc biệt nếu trước đó đã project/rename field.

### 16.3. Null và missing trong DTO

Ví dụ projection:

~~~javascript
{ region: "NORTH", revenue: null }
~~~

Nếu DTO dùng **long revenue**, null không có giá trị tương ứng; lỗi mapping hoặc giá trị mặc định có thể che dữ liệu thiếu. Nên dùng nullable **Long/BigDecimal** khi output có thể missing/null, hoặc tính giá trị mặc định trong pipeline và kiểm thử.

Không coi null revenue bằng 0 về mặt nghiệp vụ nếu null nghĩa là **chưa có dữ liệu** hoặc **không tính được**.

## 17. Ánh xạ output DTO: đặt tên field khớp với pipeline

**Ánh xạ kết quả** là một chức năng riêng với **ánh xạ domain input**. Spring Data chuyển BSON documents mà aggregate trả về thành các đối tượng của **outputType**.

### 17.1. Nhìn vào shape trước khi tạo DTO

Ví dụ MongoDB output:

~~~javascript
{
  region: "NORTH",
  orderCount: NumberLong(3),
  revenue: NumberDecimal("205.00")
}
~~~

DTO phù hợp:

~~~java
public record RegionRevenue(
        String region,
        long orderCount,
        java.math.BigDecimal revenue
) {}
~~~

Không dùng:

~~~java
public record RegionRevenue(
        String area,
        int numberOfOrders,
        double totalPrice
) {}
~~~

trừ khi pipeline đã đổi alias đúng hoặc code có custom conversion. Với DTO thứ hai, names **area**, **numberOfOrders**, **totalPrice** không khớp field output; dùng **double** còn có rủi ro sai chính xác tiền tệ.

### 17.2. Record constructor mapping

Java **record** là đối tượng bất biến với canonical constructor. Spring Data MongoDB hỗ trợ ánh xạ constructor/record trong các phiên bản hiện đại, với điều kiện constructor parameter names và field mappings được nhận diện chính xác.

Ưu điểm:

- DTO gọn, ít boilerplate.
- Field output phải có ý nghĩa rõ.
- Phù hợp response/read model.

Nhưng **record không làm biến mất vấn đề null/type mismatch**. Nếu aggregation không sinh field **region** hoặc sinh **revenue** là String, việc mapping vẫn có thể thất bại hoặc tạo ra dữ liệu không mong đợi.

### 17.3. DTO dạng Java class

Nếu dự án chưa dùng record:

~~~java
import java.math.BigDecimal;

public class RegionRevenueDto {
    private String region;
    private long orderCount;
    private BigDecimal revenue;

    public RegionRevenueDto() {
    }

    public String getRegion() {
        return region;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public long getOrderCount() {
        return orderCount;
    }

    public void setOrderCount(long orderCount) {
        this.orderCount = orderCount;
    }

    public BigDecimal getRevenue() {
        return revenue;
    }

    public void setRevenue(BigDecimal revenue) {
        this.revenue = revenue;
    }
}
~~~

Đảm bảo class có constructor/property access phù hợp với **MappingMongoConverter** và convention của dự án.

### 17.4. Nested DTO cho $facet

Facet trả **một document chứa các arrays**:

~~~javascript
{
  revenueByRegion: [
    { region: "NORTH", revenue: NumberDecimal("205.00") },
    { region: "SOUTH", revenue: NumberDecimal("115.00") }
  ],
  statusCounts: [
    { status: "PAID", count: 5 },
    { status: "NEW", count: 1 },
    { status: "CANCELLED", count: 1 }
  ]
}
~~~

Có thể định nghĩa:

~~~java
import java.math.BigDecimal;
import java.util.List;

public record DashboardReport(
        List<RegionTotal> revenueByRegion,
        List<StatusCount> statusCounts
) {}

public record RegionTotal(
        String region,
        BigDecimal revenue
) {}

public record StatusCount(
        String status,
        long count
) {}
~~~

Trong ứng dụng thực, mỗi public record ở **file Java riêng**. Spring Data converter có thể ánh xạ nested arrays thành Lists nếu cấu trúc BSON đúng và phiên bản hỗ trợ record mapping.

~~~java
AggregationResults<DashboardReport> results =
        mongoTemplate.aggregate(
                agg, "orders", DashboardReport.class);

DashboardReport dashboard = results.getUniqueMappedResult();
~~~

Không map toàn bộ facet result thành **List<RegionRevenue>** vì **top-level document** không phải một region, mà chứa arrays nhiều nhóm.

### 17.5. DTO nested từ $lookup

Nếu không unwind/project:

~~~javascript
{
  _id: "O-1001",
  customer: [
    { _id: "C-1", name: "An", tier: "GOLD" }
  ]
}
~~~

thì DTO phải có collection:

~~~java
public record CustomerSummary(
        String id,
        String name,
        String tier
) {}

public record OrderJoinResult(
        String id,
        java.util.List<CustomerSummary> customer
) {}
~~~

Tuy nhiên, **_id** của joined customer và order cần được map sang **id** qua Spring Data conventions hoặc explicit projection/annotations. Để tránh phụ thuộc mapping ngầm, có thể project **orderId, customerId, customerName** rõ ràng.

## 18. Numeric mapping: Int32, Int64, Double, Decimal128

MongoDB có các kiểu số BSON khác nhau:

| MongoDB/BSON | Java driver thô | Java DTO thường dùng | Rủi ro |
|---|---|---|---|
| Int32 | Integer | int/Integer | Có thể overflow |
| Int64 | Long | long/Long | Primitive không nhận null |
| Double | Double | double/Double | Sai số nhị phân với tiền |
| Decimal128 | Decimal128 | BigDecimal qua Spring conversion | Cần tương thích converter, scale và rounding |

### 18.1. Vì sao dùng BigDecimal cho tiền?

Nếu dùng **double**:

~~~java
double amount = 0.1 + 0.2;
~~~

kết quả nhị phân có thể không bằng chính xác **0.3**. Với báo cáo tài chính, nên lưu Decimal128 hoặc integer minor units theo chuẩn nghiệp vụ, và ánh xạ thành **BigDecimal/long** thích hợp.

### 18.2. $sum có thể trả type khác input

Tùy toán tử và kiểu input:

- **$sum: 1** thường cho numeric count và có thể là int/long, thậm chí thay đổi khi vượt giới hạn.
- **$sum** trên Decimal128 có thể trả Decimal128.
- **$avg** trên số nguyên có thể cho Double; trên Decimal128 có thể giữ kết quả Decimal128.

Không ép mọi **count** vào Integer nếu số document có thể vượt giới hạn. Dùng **long/Long** để diễn đạt tổng đếm trong output DTO.

### 18.3. Kiểm tra outputType khi gặp conversion error

Nếu pipeline trả:

~~~javascript
{ revenue: NumberDecimal("205.00") }
~~~

nhưng DTO khai báo:

~~~java
public record RevenueDto(int revenue) {}
~~~

thì không thể coi conversion là đúng. Hãy thử tạm **Document.class**, kiểm tra BSON type, rồi chọn output DTO đúng thay vì ép lossily.

### 18.4. Thiếu field không được tự hiểu là 0

Record:

~~~java
public record Stats(long orderCount, BigDecimal revenue) {}
~~~

với result:

~~~javascript
{ orderCount: 3 }
~~~

thì revenue **không có**; tránh code gọi revenue.add(...) mà không xét null. Nếu hợp đồng API muốn giá trị 0, hãy chủ động tạo/normalize nó bằng pipeline hoặc mapper có kiểm tra.

## 19. Date, Instant và múi giờ

BSON Date biểu diễn thời điểm UTC. Java domain thường dùng **Instant**, **Date** hoặc kiểu thời gian phù hợp với converter của Spring Data.

### 19.1. Group theo ngày cần timezone rõ

Một order diễn ra tại:

~~~text
2026-10-01T23:30:00Z
~~~

Ở múi giờ **Asia/Ho_Chi_Minh (UTC+07:00)**, đó là ngày **2026-10-02**, khác ngày UTC.

Nếu báo cáo doanh thu theo **ngày kinh doanh tại Việt Nam**, group theo ngày UTC có thể đưa order sang bucket không mong muốn.

### 19.2. MongoDB $dateToString với timezone

~~~javascript
db.orders.aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $group: {
      _id: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$placed_at",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      revenue: { $sum: "$gross_amount" }
    }
  },
  {
    $project: {
      _id: 0,
      businessDate: "$_id",
      orderCount: 1,
      revenue: 1
    }
  },
  { $sort: { businessDate: 1 } }
]);
~~~

Spring Data có **DateOperators** và builder hỗ trợ date expressions/timezone theo phiên bản. Khi cần một expression chưa thuận tiện trong builder, có thể dùng một **AggregationOperation** custom với BSON stage đã được kiểm tra.

### 19.3. DTO ngày có thể là String hoặc Date

Ở pipeline trên, **$dateToString** tạo String ngày **"YYYY-MM-DD"**, nên DTO thích hợp có thể là:

~~~java
public record DailyRevenue(
        String businessDate,
        long orderCount,
        java.math.BigDecimal revenue
) {}
~~~

Đừng map String này trực tiếp sang **Instant** nếu chưa có custom conversion; một ngày không có giờ/múi giờ không đại diện duy nhất một thời điểm.

### 19.4. $dateTrunc và bucket theo thời gian

MongoDB các phiên bản hỗ trợ **$dateTrunc** cho phép nhóm theo day/hour/week với timezone và các tùy chọn liên quan. Nếu output vẫn là BSON Date, DTO có thể dùng **Instant** với converter phù hợp.

Không dùng phép cắt chuỗi ISO ngày nếu yêu cầu có DST, timezone lịch sử hoặc tuần bắt đầu ở thứ khác. Chọn operator/date semantics đúng nghiệp vụ.

## 20. Strict mapping và tên field từ @Field

Khi chạy **TypedAggregation<OrderEntity>**, các stage builders được đánh giá trong context có domain metadata. Nhưng cùng một chuỗi field có thể có hai ý nghĩa:

~~~text
OrderEntity Java property:
  grossAmount

MongoDB document field:
  gross_amount

Aggregation result alias:
  revenue
~~~

Không dùng ba tên này thay thế cho nhau.

### 20.1. Trường input và trường output

Trước **$group**, tham chiếu:

~~~java
sum("grossAmount").as("revenue")
~~~

Trong typed aggregation, **grossAmount** được map thành **gross_amount**.

Sau **$group**, stage sort tham chiếu:

~~~java
sort(Sort.Direction.DESC, "revenue")
~~~

**revenue** là field vừa được tạo, không phải Java domain property.

### 20.2. Field không tồn tại

Giả sử lập trình viên đánh máy nhầm:

~~~java
match(Criteria.where("tennatId").is("TENANT-A"))
~~~

Field **tennatId** không tồn tại. Từ Spring Data MongoDB 3.2, typed aggregation không mặc định raise error cho mọi field reference không tồn tại. Kết quả có thể rỗng vì pipeline dùng tên sai.

Đối với môi trường cần kiểm tra chặt, dùng **strictMapping** theo version:

~~~java
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;

AggregationOptions options = AggregationOptions.builder()
        .strictMapping()
        .build();

TypedAggregation<OrderEntity> aggregation = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A"))
).withOptions(options);
~~~

Tuy nhiên, strict mapping còn phải tính đến những fields được **tạo động bởi các stage trước** và custom raw stages. Không bật/tắt strict chỉ vì một pipeline mới bị lỗi; cần xác định chỗ sai của field reference và output aliases.

### 20.3. Raw JSON và custom stages

Một stage thủ công:

~~~javascript
{ $match: { tenant_id: "TENANT-A" } }
~~~

không nhất thiết được rewrite dựa vào **@Field** giống cách builder tham chiếu Java properties trong TypedAggregation. Nếu tự viết raw BSON, hãy dùng **tên BSON thật** và document stage đúng semantics.

### 20.4. Dùng Document khi chưa rõ mapping

Ví dụ:

~~~java
AggregationResults<org.bson.Document> raw =
        mongoTemplate.aggregate(
                aggregation, org.bson.Document.class);

for (org.bson.Document row : raw.getMappedResults()) {
    System.out.println(row.toJson());
}
~~~

Trong lab với dữ liệu giả, cách này giúp quan sát shape/type. **Không in toàn bộ document nhạy cảm** vào logs production. Sau khi biết output shape, chọn DTO và bổ sung tests cụ thể.

## 21. Khi nào dùng @Aggregation trong Spring Data Repository?

Spring Data MongoDB cho phép khai báo pipeline trên repository method bằng annotation **org.springframework.data.mongodb.repository.Aggregation**.

~~~java
import java.util.List;

import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderSpringRepository
        extends MongoRepository<OrderEntity, String> {

    @Aggregation(pipeline = {
            "{ '$match': { 'tenant_id': ?0, 'status': 'PAID' } }",
            "{ '$group': { '_id': '$region', " +
                    "'orderCount': { '$sum': 1 }, " +
                    "'revenue': { '$sum': '$gross_amount' } } }",
            "{ '$project': { '_id': 0, 'region': '$_id', " +
                    "'orderCount': 1, 'revenue': 1 } }",
            "{ '$sort': { 'revenue': -1 } }"
    })
    List<RegionRevenue> revenueByRegion(String tenantId);
}
~~~

**?0** là placeholder cho tham số đầu tiên. Pipeline trong annotation là JSON-like text do Spring Data xử lý; ví dụ dùng tên BSON của collection mẫu để tránh nhầm mapping. Không nối trực tiếp user input vào chuỗi JSON tạo pipeline, vì có thể gây operator injection hoặc làm sai semantics.

### 21.1. Trường hợp phù hợp

- Pipeline ngắn, ít nhánh và ổn định.
- Logic báo cáo gắn trực tiếp repository.
- Kết quả có DTO rõ ràng.
- Không cần thêm nhiều stages theo điều kiện runtime.

### 21.2. Khi nào MongoTemplate tốt hơn?

- Pipeline động, nhiều điều kiện tùy chọn.
- Dùng **$facet/$lookup/$unwind** phức tạp.
- Cần **AggregationOptions**, streaming hoặc custom operations.
- Muốn tách các stage builder thành hàm dùng lại.
- Cần quản lý schema/result mapping chặt chẽ.

Chọn API theo mức độ phức tạp và khả năng kiểm thử, không theo quan điểm tuyệt đối. Repository methods có thể hỗ trợ Sort/Pageable theo version, nhưng tổng số groups sau $group **không tự bằng số documents nguồn**.

Nếu API cần:

~~~text
items: top 20 region groups
totalGroups: 183
~~~

thì cần định nghĩa rõ cách tính **totalGroups** (sau những filter nào) và có thể cần một pipeline đếm riêng hoặc facet thích hợp.

## 22. Pipeline động với điều kiện tùy chọn

Một báo cáo có thể lọc theo **tenantId** bắt buộc, status và ngày có thể tùy chọn.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

public class DynamicRevenueReport {
    private final MongoTemplate template;

    public DynamicRevenueReport(MongoTemplate template) {
        this.template = template;
    }

    public List<RegionRevenue> run(
            String trustedTenantId,
            String optionalStatus,
            Instant fromInclusive,
            Instant toExclusive) {

        if (trustedTenantId == null || trustedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Authenticated tenant is required");
        }

        Criteria criteria =
                Criteria.where("tenantId").is(trustedTenantId);

        if (optionalStatus != null && !optionalStatus.isBlank()) {
            criteria = criteria.and("status").is(optionalStatus);
        }

        if (fromInclusive != null || toExclusive != null) {
            Criteria dates = criteria.and("placedAt");
            if (fromInclusive != null) {
                dates = dates.gte(fromInclusive);
            }
            if (toExclusive != null) {
                dates = dates.lt(toExclusive);
            }
        }

        List<AggregationOperation> stages = new ArrayList<>();
        stages.add(match(criteria));
        stages.add(group("region")
                .count().as("orderCount")
                .sum("grossAmount").as("revenue"));
        stages.add(project("orderCount", "revenue")
                .and("_id").as("region")
                .andExclude("_id"));
        stages.add(sort(Sort.Direction.DESC, "revenue"));

        TypedAggregation<OrderEntity> agg =
                newAggregation(OrderEntity.class, stages);

        return template.aggregate(agg, RegionRevenue.class)
                .getMappedResults();
    }
}
~~~

**Nguyên tắc:** điều kiện **tenantId** không bao giờ là optional. Các field và operators được chọn từ code, không nhận tùy ý cấu trúc query do client gửi lên. Với điều kiện boolean phức tạp, sử dụng **Criteria.andOperator/orOperator** một cách rõ ràng và tránh tạo các key BSON trùng nhau.

### 22.1. Kiểm soát sort/limit từ request

Không đưa bất kỳ chuỗi **userField** nào vào Sort mà không có allowlist. API chỉ nên cho sort theo những alias output như **revenue**, **orderCount**, **region**, và giới hạn số rows.

## 23. Custom AggregationOperation cho stage mới

MongoDB server có thể bổ sung stage trước khi Spring Data version của dự án có builder chuyên biệt. Có thể truyền raw BSON thông qua **AggregationOperation**.

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;

AggregationOperation rawMatch = context -> new Document(
        "$match",
        new Document("tenant_id", "TENANT-A")
                .append("status", "PAID")
);
~~~

Sử dụng:

~~~java
Aggregation agg = Aggregation.newAggregation(
        rawMatch,
        Aggregation.group("region")
                .count().as("orderCount")
);
~~~

### 23.1. Mapping context

**AggregationOperationContext** có phương thức **getMappedObject(Document)**:

~~~java
AggregationOperation mappedMatch = context -> {
    Document raw = new Document(
            "$match",
            new Document("tenantId", "TENANT-A")
    );
    return context.getMappedObject(raw);
};
~~~

Việc áp dụng domain mapping phụ thuộc typed context và các exposed fields; không mặc định mọi raw Document tự map như builders. Nếu dùng raw stages, phải kiểm soát **tên BSON thật, thứ tự stage, version MongoDB, query injection và các aliases**.

### 23.2. Custom stage không thay thế compatibility

Một MongoDB server chưa hỗ trợ stage sẽ không tự hỗ trợ vì Java code tạo được Document. Custom AggregationOperation chỉ tạo/đưa stage BSON tới server; đúng/sai vẫn do phiên bản database và dữ liệu quyết định.

## 24. AggregationOptions: thời gian, bộ nhớ, cách thực thi

Một pipeline báo cáo có thể tốn CPU, memory và I/O. **AggregationOptions** cho phép cấu hình các tùy chọn tương ứng.

~~~java
import java.time.Duration;
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;

AggregationOptions options =
        AggregationOptions.builder()
                .allowDiskUse(true)
                .maxTime(Duration.ofSeconds(10))
                .comment("region-revenue-report")
                .build();

Aggregation agg = newAggregation(
        match(Criteria.where("tenant_id").is("TENANT-A")),
        group("region")
                .sum("gross_amount").as("revenue")
).withOptions(options);
~~~

Theo phiên bản, builder còn hỗ trợ options như **cursorBatchSize, hint, collation, readPreference/readConcern, explain**.

### 24.1. allowDiskUse không phải tăng tốc miễn phí

**allowDiskUse(true)** cho phép một số stages sử dụng disk tạm trong tình huống được hỗ trợ thay vì chỉ RAM. Nhưng:

- Có thể tăng I/O và yêu cầu storage tạm.
- Không sửa query thiếu index hoặc filter kém.
- Không xóa giới hạn BSON document 16 MiB.
- Không cho phép mọi stage spill; chẳng hạn $facet có giới hạn riêng.
- Hành vi mặc định phụ thuộc MongoDB server version và cấu hình.

### 24.2. maxTime khác timeout ở tầng HTTP

**maxTime(Duration)** tác động tới thời gian xử lý command phía MongoDB theo semantics của lệnh, không nhất thiết bao phủ DNS, chờ connection pool, network latency, mapping nhiều results hoặc thời gian serialize HTTP response.

Nên thiết kế deadline end-to-end, giới hạn số rows và theo dõi latency.

### 24.3. Comment không chứa bí mật

Comment hữu ích để nhận diện workload:

~~~text
region-revenue-report
~~~

Không đưa email, mật khẩu, token, số định danh hoặc dữ liệu khách hàng nhạy cảm vào comment vì có thể hiện trong diagnostic/profiler/log.

### 24.4. Explain không phải kết quả báo cáo

Khi dùng tùy chọn **explain(true)**, mục tiêu là thu thập thông tin thực thi, không phải records dạng RegionRevenue. Không đưa explain mode vào đường API trả DTO cho người dùng rồi mong vẫn có revenue rows.

## 25. Stream kết quả thay vì đưa hết vào List

**MongoTemplate.aggregate(...)** trả AggregationResults và mapped results. Khi output có rất nhiều rows, thu toàn bộ vào List có thể tiêu thụ nhiều RAM. Spring Data hỗ trợ **aggregateStream(...)** với cursor-backed Stream.

~~~java
import java.util.stream.Stream;

Aggregation agg = newAggregation(
        match(Criteria.where("tenant_id").is("TENANT-A")),
        project()
                .and("_id").as("orderId")
                .and("region").as("region")
                .andExclude("_id")
);

try (Stream<RegionOrder> stream =
             mongoTemplate.aggregateStream(
                     agg, "orders", RegionOrder.class)) {
    stream.forEach(row -> {
        // Xử lý từng dòng; không giữ tất cả trong RAM.
        System.out.println(row.orderId());
    });
}
~~~

DTO:

~~~java
public record RegionOrder(String orderId, String region) {}
~~~

**Phải đóng Stream**, kể cả khi có exception hoặc kết thúc trước khi duyệt hết. Đừng giữ Stream làm field singleton hoặc trả Stream ra ngoài một scope đã đóng.

### 25.1. Khi nào streaming vẫn không phù hợp?

Streaming làm giảm memory do **không materialize hết kết quả**, nhưng có thể giữ cursor lâu và tăng thời gian tài nguyên được chiếm dụng. Nên:

- Bounded query và filter sớm.
- Chọn batchSize phù hợp.
- Xử lý cancellation/errors.
- Không gọi **stream.toList()** trên hàng triệu documents nếu mục tiêu là streaming.
- Không đưa Stream trực tiếp sang controller rồi quên đóng.

### 25.2. cursorBatchSize không phải limit

**cursorBatchSize** quyết định kích thước batches/network behavior trong những trường hợp hỗ trợ; **$limit** mới quyết định tổng số rows tối đa được trả. Đừng dùng cursorBatchSize(100) và hiểu rằng query chắc chắn trả không quá 100 rows.

### 25.3. Reactive stack

Nếu dùng **ReactiveMongoTemplate**, aggregation thường trả **Flux<DTO>**, với subscription/backpressure và reactive driver. **MongoTemplate** của sync stack là blocking. Không gọi trực tiếp MongoTemplate trên event-loop nonblocking với giả định nó tự trở thành reactive.

## 26. Hiệu năng: thứ tự stage và khả năng dùng index

Pipeline đúng về kết quả chưa chắc tối ưu.

### 26.1. Đặt $match và projection hợp lý

Thường nên lọc tenant/status/date sớm:

~~~javascript
[
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  { $group: { _id: "$region", revenue: { $sum: "$gross_amount" } } },
  { $sort: { revenue: -1 } }
]
~~~

Nếu group mọi tenant rồi match tenant ở cuối, stage group đã xử lý lượng dữ liệu lớn hơn và có thể không còn tenantId để lọc.

Một số $project có thể được query optimizer di chuyển hoặc tối ưu, nhưng **không** dùng điều này làm lý do viết pipeline mất an toàn hoặc áp dụng filter tenant sai stage.

### 26.2. Sort trước và sau group khác nhau

~~~text
$sort(placed_at desc) trước $group:
  sắp xếp documents nguồn

$sort(revenue desc) sau $group:
  sắp xếp summary rows
~~~

Một B-tree index có thể phục vụ sort đầu pipeline trong điều kiện phù hợp, nhưng không tự tạo index trên **revenue** là field chỉ được tính sau group. Sort sau group thường phải sắp xếp kết quả tổng hợp.

### 26.3. $match + $sort + $limit

Nếu truy vấn chỉ cần các orders mới nhất:

~~~javascript
[
  { $match: { tenant_id: "TENANT-A" } },
  { $sort: { placed_at: -1, _id: -1 } },
  { $limit: 20 }
]
~~~

index:

~~~javascript
db.orders.createIndex({
  tenant_id: 1,
  placed_at: -1,
  _id: -1
});
~~~

có thể hữu ích. Nhưng báo cáo group theo region lại có pattern khác. **Index phải phục vụ workload cụ thể**, không chỉ vì collection có nhiều pipeline.

### 26.4. Explain

Trong mongosh lab:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenant_id: "TENANT-A", status: "PAID" } },
  {
    $group: {
      _id: "$region",
      revenue: { $sum: "$gross_amount" }
    }
  }
]);
~~~

Tùy server version/explain format, hãy tìm:

- **COLLSCAN** hay **IXSCAN** ở input side.
- Số documents/keys được quét.
- Các stages phải sort/aggregate và sử dụng memory.
- Thời gian thực thi theo thống kê phù hợp.
- Có allowDiskUse hoặc disk spill không.

**explain của collection 8 documents không đại diện production.** Dữ liệu nhỏ thường khiến collection scan nhanh, không có nghĩa index sai hoặc không cần index cho dữ liệu lớn.

### 26.5. $lookup và N×M

Join dữ liệu không được index phù hợp có thể đọc rất nhiều rows. Với $lookup:

- Lọc parent documents sớm.
- Index khóa join bên foreign collection.
- Giới hạn fields và cardinality.
- Cẩn trọng với nested arrays và unwind làm số rows phình.
- Áp dụng quyền tenant ở cả phía parent/foreign nếu nghiệp vụ yêu cầu.

### 26.6. Không lạm dụng $facet

Facet tiện cho dashboard đa nhánh nhưng có thể tạo document rất lớn và chi phí xử lý cao. Những phần báo cáo độc lập, cập nhật theo cadence khác nhau có thể thích hợp với **nhiều truy vấn** hoặc **materialized summary** thay vì một pipeline facet khổng lồ.

## 27. Pagination của kết quả đã group

Một báo cáo có thể trả hàng nghìn region/category groups. Dùng:

~~~java
sort(Sort.Direction.DESC, "revenue"),
skip(20),
limit(20)
~~~

để lấy trang kế tiếp trên một tập kết quả đã group. Tuy nhiên:

- **skip** lớn có chi phí bỏ qua nhiều dòng.
- Sort phải có thứ tự ổn định; nên thêm tie-breaker như **region** khi revenue trùng.
- Tổng số groups phải tính theo **kết quả group**, không phải số orders.
- Khi dữ liệu thay đổi giữa hai pages, offset pagination có thể gây duplicate/missing rows.

### 27.1. Ví dụ sort ổn định

~~~java
sort(Sort.by(
        Sort.Order.desc("revenue"),
        Sort.Order.asc("region")
)),
skip(20),
limit(20)
~~~

Khi ứng dụng yêu cầu phân trang rất sâu hoặc dữ liệu thay đổi liên tục, cân nhắc keyset/seek pagination hoặc snapshot/reporting model phù hợp, nhưng **keyset trên computed group results** cần thiết kế điều kiện và stability riêng.

### 27.2. Không lấy số trang bằng count() của collection

Nếu collection có 1.000.000 orders nhưng chỉ 250 regions/categories, **totalGroups=250**, không phải 1.000.000. Cần một pipeline đếm số nhóm sau filter/group hoặc một facet trả metadata đếm đúng.

## 28. Kiểm thử aggregation trong Spring Data

Một pipeline có thể chạy được mà vẫn **cho số liệu sai** do:

- Đặt match sai stage.
- Dùng nhầm **tenantId** với **tenant_id**.
- Đếm items thay vì orders sau unwind.
- Làm tròn/convert tiền qua Double.
- Map _id sai field.
- Không phân biệt null/missing.
- Join nhầm customer do khóa trùng giữa tenant.
- Sort trước group hoặc limit sai vị trí.

Vì vậy, cần có **integration tests với MongoDB thực**, sử dụng dữ liệu kiểm thử nhỏ nhưng đủ các tình huống khác nhau.

### 28.1. Bài test tích hợp doanh thu

Ví dụ JUnit 5/Spring Boot, giả định test database đã được tạo và seed **bộ dữ liệu của mục 4**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderAnalyticsRepositoryIT {

    @Autowired
    private OrderAnalyticsRepository reports;

    @Test
    void reportsPaidRevenueOnlyForRequestedTenant() {
        List<RegionRevenue> rows =
                reports.revenueByRegion("TENANT-A");

        assertEquals(2, rows.size());

        RegionRevenue north = rows.stream()
                .filter(r -> "NORTH".equals(r.region()))
                .findFirst()
                .orElseThrow();

        assertEquals(3L, north.orderCount());
        assertEquals(0, north.revenue()
                .compareTo(new BigDecimal("205.00")));

        assertTrue(rows.stream().noneMatch(r ->
                r.revenue().compareTo(
                        new BigDecimal("999.00")) == 0));
    }
}
~~~

Đây chỉ là **mẫu test**. Không chạy trên production. Test thực tế nên dùng database riêng, có seed/cleanup độc lập và xác nhận kết quả **SOUTH=115.00** ngoài NORTH. Nếu test chạy lại mà seed bằng insertMany với _id cố định trên collection chưa dọn, sẽ gặp duplicate key.

### 28.2. Test output mapping độc lập

Một tập test nên bao phủ:

| Tình huống | Điều cần xác minh |
|---|---|
| Không có order phù hợp | Empty list hoặc null result theo hợp đồng |
| Chỉ một region | Một DTO có đúng aliases |
| Nhiều regions | Danh sách được sort đúng |
| Hai regions cùng revenue | Tie-breaker ổn định |
| Giá trị Decimal128 | Không mất chữ số thập phân |
| Nhiều items một order | Quantity sum đúng, không đếm order trùng |
| Customer missing khi lookup | Hành vi unwind giữ/bỏ document như yêu cầu |
| Tenant B nhiều doanh thu | Không bị tính vào Tenant A |
| Date gần ranh giới UTC | Nhóm vào ngày theo timezone được khai báo |
| Output field null/missing | DTO hoặc converter xử lý đúng |

### 28.3. Unit test builder chưa đủ

Một unit test chỉ xác nhận Aggregation object không null **không đảm bảo** MongoDB server hiểu stage hoặc output mapper trả đúng số liệu. Những lỗi về BSON field names, Decimal128, $lookup, index và server version thường chỉ bộc lộ ở integration test.

### 28.4. Testcontainers

Với Testcontainers, có thể khởi động MongoDB cho test và cấu hình **spring.data.mongodb.uri** trỏ tới container, theo cách tương thích với phiên bản Testcontainers/Spring Boot. Bài này không ép một API Testcontainers cụ thể vì package/module của MongoDBContainer và phương pháp kết nối có thể thay đổi theo release.

Các lưu ý:

- Không dùng credentials production.
- Không chạy init script xóa collection không thuộc phạm vi test.
- Khi có test song song, tránh dùng chung một collection với cùng _id.
- Nếu test $lookup/$setWindowFields/$dateTrunc, dùng MongoDB image/version hỗ trợ stage tương ứng.
- Bảo đảm test không phụ thuộc thời gian local timezone của máy chạy.

### 28.5. Snapshot pipeline hữu ích nhưng không đủ

Có thể kiểm tra pipeline render BSON theo context của Spring Data, nhưng cần phân biệt pipeline string đã format và pipeline thực sự MongoTemplate gửi. Với typed mappings, một test render không có đúng domain context có thể không phản ánh mapping của production.

Đừng chỉ so sánh một chuỗi JSON rồi bỏ qua kiểm tra số liệu từ MongoDB.

## 29. Bảo mật và tính đúng đắn trong multi-tenant analytics

### 29.1. Tenant filter là bắt buộc

Nếu cùng collection có dữ liệu nhiều tenant, mọi báo cáo có scope tenant phải có filter tương ứng. Nhưng:

~~~java
public List<RegionRevenue> report(String tenantId)
~~~

không tự đảm bảo tenantId đáng tin. Controller/service phải resolve tenantId từ **identity/token/session được xác thực**, không sử dụng tenant tùy ý từ query string.

### 29.2. Aggregation có thể làm lộ thông tin qua số liệu tổng hợp

Một API trả:

~~~javascript
{ department: "EXECUTIVE", totalPayroll: 9000000 }
~~~

có thể tiết lộ thông tin nhạy cảm ngay cả khi không trả từng nhân viên. Cần authorization cho **bản thân báo cáo**, không chỉ cho collection documents.

### 29.3. Quyền truy cập trong $lookup

Khi join foreign collection, phải xét tenantId/ACL ở cả hai phía. Nếu có nhiều tenants dùng cùng customerRef hoặc productRef, một lookup chỉ dựa trên một key có thể ghép nhầm nguồn.

Không đưa raw joined documents ra API; chỉ project fields được phép.

### 29.4. Không cho client gửi raw pipeline tùy ý

Một request như:

~~~json
{
  "pipeline": [
    { "$match": {} },
    { "$lookup": { "from": "privateCollection" } }
  ]
}
~~~

không nên được thi hành trực tiếp bởi backend với credentials có quyền cao. Cần allowlist report types, filters, sort fields và output schema; không cấp khả năng arbitrary collection access chỉ vì MongoDB cho phép linh hoạt.

### 29.5. Giới hạn tài nguyên báo cáo

Một user có thể yêu cầu báo cáo trên khoảng thời gian quá lớn và làm server quá tải. Nên giới hạn:

- Date range tối đa.
- Số group/result rows.
- Số stages hoặc branch types được phép.
- maxTime/cancellation và concurrency.
- Sort fields.
- Số request báo cáo theo user/tenant.

Không dùng **allowDiskUse(true)** làm cơ chế kiểm soát lạm dụng.

## 30. Lỗi thường gặp và hướng xử lý

### 30.1. Query trả rỗng dù mongosh có dữ liệu

**Khả năng:** pipeline dùng Java property **tenantId** trong chế độ untyped/Document trong khi collection lưu **tenant_id**.

**Hướng xử lý:** xác định typed hay untyped aggregation; kiểm tra @Field mapping và BSON pipeline. Đối chiếu raw mongosh query trên dữ liệu giả.

### 30.2. Revenue bị null sau group

**Khả năng:** đã group **grossAmount** nhưng untyped pipeline phải dùng **gross_amount**; hoặc dữ liệu lưu dưới String/null/không đồng nhất.

**Hướng xử lý:** xem field names, BSON types, stage order và raw output Document. Không tự ép null về 0 trước khi hiểu nguyên nhân.

### 30.3. DTO region null dù _id có NORTH

**Nguyên nhân:** group output là:

~~~javascript
{ _id: "NORTH", orderCount: 3 }
~~~

nhưng DTO đòi **region**. **Hướng xử lý:** project **region: "$_id"** rồi exclude _id, hoặc dùng mapping annotation/constructor phù hợp.

### 30.4. BigDecimal không đúng

**Nguyên nhân:** input có Double hoặc code dùng double trong tính toán, $avg tạo kiểu khác, hoặc dữ liệu cũ lưu String.

**Hướng xử lý:** kiểm tra BSON Decimal128, @Field targetType, numeric expression types, conversion và scale/rounding policy.

### 30.5. aggregateStream nhưng app giữ cursor quá lâu

**Nguyên nhân:** stream không được close, xử lý mỗi row mất nhiều thời gian, hoặc đưa stream ra ngoài method.

**Hướng xử lý:** try-with-resources, bounded batch, backpressure và cancellation.

### 30.6. $lookup trả array thay vì object

**Nguyên nhân:** lookup luôn trả array. **Hướng xử lý:** thiết kế DTO với List hoặc unwind/project để lấy object fields.

### 30.7. $unwind làm orderCount tăng

**Nguyên nhân:** group/count sau unwind đếm **item rows**, không phải orders. **Hướng xử lý:** đổi thứ tự pipeline hoặc deduplicate theo order ID.

### 30.8. getUniqueMappedResult() ném exception

**Nguyên nhân:** aggregation trả **hơn một document**, trong khi method này yêu cầu 0 hoặc 1 result. **Hướng xử lý:** dùng getMappedResults() cho nhiều groups; chỉ dùng unique khi có contract bảo đảm không quá một dòng.

### 30.9. NullPointerException trong controller

**Nguyên nhân:** group không có input hoặc result field missing, nhưng code dùng record primitive/field không null một cách ngầm định.

**Hướng xử lý:** thiết kế hành vi **no data** rõ, validate/normalize DTO và đừng gọi method trên giá trị null.

### 30.10. Sort không đúng

**Nguyên nhân:** sort theo field đã bị project bỏ, hoặc sort trước group trong khi muốn sort theo revenue đã tính.

**Hướng xử lý:** vẽ output shape từng stage, sort theo aliases hiện có, thêm tie-breaker khi cần pagination ổn định.

### 30.11. Performance kém dù có index

**Nguyên nhân:** $match đặt sau group/project, index không phục vụ filter, aggregation quét nhiều document, sort theo computed field, lookup thiếu index.

**Hướng xử lý:** explain executionStats, đo keys/docs examined, tối ưu pipeline/index theo workload.

### 30.12. Pipeline sử dụng stage mới báo unsupported

**Nguyên nhân:** MongoDB server version chưa hỗ trợ, hoặc Spring Data version không có builder. **Hướng xử lý:** phân biệt hai trường hợp: custom AggregationOperation chỉ giải quyết thiếu builder, không bổ sung feature phía server.

### 30.13. Report tính cả tenant khác

**Nguyên nhân:** bỏ tenant filter, nhận tenantId không đáng tin hoặc $lookup join nhầm nguồn. **Hướng xử lý:** coi là sự cố bảo mật, sửa authorization/data isolation và kiểm thử regression với tenant dữ liệu lớn dễ nhận thấy.

### 30.14. Báo cáo số lượng sản phẩm lẫn số đơn

**Nguyên nhân:** nhầm count documents, count items, sum quantities và count distinct orders. **Hướng xử lý:** đặt metric definition cụ thể, chọn stage grouping tương ứng.

### 30.15. $facet trả document quá lớn

**Nguyên nhân:** đưa quá nhiều rows vào arrays nhánh facet, vượt giới hạn BSON/memory. **Hướng xử lý:** chỉ xuất summary bounded, chia report, dùng pagination hoặc materialized view phù hợp.

### 30.16. Đếm sai số nhóm khi phân trang

**Nguyên nhân:** lấy MongoTemplate.count(Query...) của source collection thay cho số groups sau aggregation. **Hướng xử lý:** tính totalGroups từ pipeline group/filter hoặc facet riêng.

### 30.17. Timezone làm ngày báo cáo lệch

**Nguyên nhân:** dùng UTC trong khi nghiệp vụ cần Asia/Ho_Chi_Minh hoặc timezone khác. **Hướng xử lý:** khai báo timezone tại date operator và kiểm thử dữ liệu sát nửa đêm.

### 30.18. Báo cáo lấy quá nhiều RAM

**Nguyên nhân:** aggregation trả hàng triệu rows, getMappedResults() tạo List lớn; hoặc facet result quá lớn. **Hướng xử lý:** filter/projection/limit thích hợp, aggregateStream đúng scope, hoặc thiết kế report batch/materialized summary.

## 31. Quy trình xây một báo cáo aggregation từ đầu

### Bước 1 — Xác định metric

Ví dụ:

~~~text
Metric name: PAID revenue by region
Scope: authenticated tenant
Time filter: placedAt in [from, to)
Eligible status: PAID only
Currency: một currency thống nhất cho report
Output: region, orderCount, revenue
Sort: revenue descending, region ascending
~~~

Nếu hệ thống có nhiều currency, không cộng chung **100 USD + 100 VND** rồi gọi là revenue=200; phải nhóm theo currency hoặc quy đổi theo tỷ giá/chính sách phù hợp.

### Bước 2 — Xác định BSON data types và field names

~~~text
tenantId property -> tenant_id BSON String
status -> String
region -> String
grossAmount property -> gross_amount BSON Decimal128
placedAt property -> placed_at BSON Date
~~~

Đồng thời kiểm tra null/legacy data, currency và quyền tenant.

### Bước 3 — Viết pipeline MongoDB rõ ràng

~~~javascript
[
  { $match: { tenant_id: "<trusted>", status: "PAID" } },
  {
    $group: {
      _id: "$region",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$gross_amount" }
    }
  },
  { $project: { _id: 0, region: "$_id", orderCount: 1, revenue: 1 } },
  { $sort: { revenue: -1, region: 1 } }
]
~~~

### Bước 4 — Chuyển sang Spring Data builders

~~~java
newAggregation(
    OrderEntity.class,
    match(Criteria.where("tenantId").is(trustedTenantId)
        .and("status").is("PAID")),
    group("region")
        .count().as("orderCount")
        .sum("grossAmount").as("revenue"),
    project("orderCount", "revenue")
        .and("_id").as("region")
        .andExclude("_id"),
    sort(Sort.by(
        Sort.Order.desc("revenue"),
        Sort.Order.asc("region")))
);
~~~

### Bước 5 — Thiết kế DTO theo output, không theo input

~~~java
public record RegionRevenue(
        String region,
        long orderCount,
        BigDecimal revenue
) {}
~~~

### Bước 6 — Kiểm thử các edge cases

No data, một region, nhiều regions, equal revenue, multi-tenant, Decimal128, null, số liệu sát boundary date.

### Bước 7 — Explain và quan sát

Kiểm tra index, documents scanned, grouped cardinality, sort memory, latency, memory/response size. Không lấy benchmark trên tám dòng làm bằng chứng production nhanh.

### Bước 8 — Đưa vào service/API an toàn

Resolve tenant từ authentication, giới hạn date range, chỉ trả DTO đã được cấp quyền; có logging/metrics không chứa dữ liệu nhạy cảm.

## 32. Bài tập thực hành có hướng dẫn

Các bài tập dùng dữ liệu **spring_agg_lab.orders** và **spring_agg_lab.customers**. Bài tập chủ yếu viết/giải thích pipeline; các ví dụ chạy trực tiếp cần MongoDB và Spring Data môi trường thử nghiệm.

### Bài 1. Chuyển find thành aggregate

Truy vấn:

~~~javascript
db.orders.find({ tenant_id: "TENANT-A", status: "PAID" });
~~~

**Yêu cầu:** viết MongoTemplate Aggregation chỉ có $match và map ra Document.

**Định hướng:**

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("tenant_id").is("TENANT-A")
                .and("status").is("PAID"))
);

List<Document> documents = mongoTemplate
        .aggregate(agg, "orders", Document.class)
        .getMappedResults();
~~~

### Bài 2. Typed và untyped

Java property **tenantId** có @Field("tenant_id"). Hai câu:

~~~java
newAggregation(
        match(Criteria.where("tenantId").is("TENANT-A")));

newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is("TENANT-A")));
~~~

**Câu hỏi:** vì sao chúng có thể tạo query field khác nhau?

**Đáp án:** typed aggregation biết metadata @Field để ánh xạ tenantId sang tenant_id; untyped aggregation không có cùng input mapping context. Với untyped nên dùng tên BSON thật.

### Bài 3. Kết quả group vào _id

~~~javascript
{ $group: { _id: "$region", n: { $sum: 1 } } }
~~~

**Yêu cầu:** thiết kế DTO có field region, n.

**Định hướng:** thêm project stage alias **region: "$_id"**, loại _id, rồi map record **RegionCount(String region, long n)**.

### Bài 4. Tổng doanh thu theo region

**Yêu cầu:** lọc TENANT-A/PAID, group region và sum gross_amount. Kết quả mong đợi?

**Đáp án:** NORTH có 3 orders và revenue **205.00**, SOUTH có 2 orders và revenue **115.00**.

### Bài 5. Tenant isolation

Order của TENANT-B có revenue 999.00.

**Câu hỏi:** nếu chỉ lọc status PAID, số liệu sai thế nào?

**Đáp án:** báo cáo sẽ tính cả order TENANT-B, làm NORTH tăng thêm 999 và count thêm 1; đây là lỗi phân quyền/báo cáo, không chỉ lỗi số học.

### Bài 6. getUniqueMappedResult

Pipeline group theo **region** trả hai dòng.

**Câu hỏi:** dùng getUniqueMappedResult() có hợp lệ không?

**Đáp án:** không. Method giả định tối đa một kết quả và có thể ném IllegalArgumentException. Dùng getMappedResults().

### Bài 7. group() không có input

Không có order nào PAID cho một tenant mới.

**Câu hỏi:** có chắc getUniqueMappedResult() trả TotalRevenue(0,0) không?

**Đáp án:** không. Có thể không có output document, do đó method trả null. API phải thiết kế no-data behavior.

### Bài 8. Đếm sau unwind

Order O-1001 có hai items.

**Câu hỏi:** tại sao $unwind items rồi count document sẽ cho hai, không phải một?

**Đáp án:** một order đã thành hai intermediate documents. Metric đang đếm item rows, không phải distinct orders.

### Bài 9. Tổng số lượng SKU

**Yêu cầu:** tính quantitySold từ các order PAID của TENANT-A.

**Đáp án:** PEN-1 = **7**, BOOK-1 = **4**, BAG-1 = **1**.

### Bài 10. Lookup một customer

**Câu hỏi:** tại sao customer sau $lookup là array dù _id chỉ match một document?

**Đáp án:** $lookup luôn trả array. Dùng unwind nếu muốn object row và xác định behavior khi không có customer.

### Bài 11. Preserve null

Một order không có items.

**Câu hỏi:** unwind mặc định có thể làm điều gì? Làm sao giữ order?

**Đáp án:** có thể loại document khỏi pipeline. Sử dụng preserveNullAndEmptyArrays, rồi xử lý items null trong các stage sau.

### Bài 12. Facet dashboard

**Yêu cầu:** trả doanh thu theo region cho PAID và số orders theo status cho tất cả trạng thái của TENANT-A.

**Định hướng:** match tenant trước facet, nhánh revenueByRegion tự match PAID; nhánh statusCounts group theo status. Không match PAID trước facet vì sẽ làm statusCounts mất NEW/CANCELLED.

### Bài 13. Nested DTO

Facet trả:

~~~javascript
{ revenueByRegion: [...], statusCounts: [...] }
~~~

**Câu hỏi:** DTO top-level nên là List<RegionRevenue> hay DashboardReport có hai Lists?

**Đáp án:** DashboardReport có hai Lists, vì output là một document bao nhiều mảng.

### Bài 14. Decimal128

Pipeline trả revenue = NumberDecimal("205.00").

**Câu hỏi:** nên map sang Java double hay BigDecimal?

**Đáp án:** BigDecimal được ưu tiên cho tiền tệ. Cần dùng conversion tương thích Decimal128 và kiểm tra scale/rounding.

### Bài 15. Alias không tồn tại

Pipeline:

~~~text
$group as revenue
$project renames revenue -> total
$sort by revenue
~~~

**Câu hỏi:** vì sao sort sai?

**Đáp án:** sau project, field revenue không còn; phải sort theo total hoặc đổi thứ tự project/sort theo semantics.

### Bài 16. Sum String

Một order cũ lưu gross_amount = "120.50" thay vì NumberDecimal.

**Câu hỏi:** có thể tin $sum gross_amount trả tổng chính xác không?

**Đáp án:** không. Cần chuẩn hóa BSON types và xử lý dữ liệu legacy; không mặc định String được cộng như decimal.

### Bài 17. Hai group keys

~~~javascript
{ _id: { region: "$region", status: "$status" }, n: { $sum: 1 } }
~~~

**Câu hỏi:** _id có phải String không?

**Đáp án:** không, là object chứa region và status. Cần DTO nested hoặc project ra hai field phẳng.

### Bài 18. $first/$last

Muốn lấy order đầu tiên theo placed_at trong từng region.

**Câu hỏi:** nếu group().first("_id") mà không sort trước, có chắc là order cũ nhất không?

**Đáp án:** không. Phải sort đầu vào theo placed_at và tie-breaker trước group hoặc dùng accumulator phù hợp.

### Bài 19. Timezone báo cáo

Một order xảy ra lúc 23:30 UTC ngày 01/10/2026.

**Câu hỏi:** theo Asia/Ho_Chi_Minh nó thuộc ngày nào?

**Đáp án:** ngày **02/10/2026**. Cần khai báo timezone trong date grouping nếu business day theo giờ Việt Nam.

### Bài 20. Strict mapping

TypedAggregation dùng field **tennatId** bị gõ nhầm.

**Câu hỏi:** liệu mọi Spring Data version sẽ ném lỗi ngay?

**Đáp án:** không. Từ 3.2 typed aggregation mặc định không nhất thiết báo lỗi non-existent property; có thể dùng AggregationOptions.strictMapping() theo version và kiểm thử output.

### Bài 21. @Aggregation repository

Một báo cáo chỉ có một pipeline ổn định bốn stages và trả List<RegionRevenue>.

**Câu hỏi:** dùng @Aggregation có được không? Khi nào nên chọn MongoTemplate?

**Đáp án:** có thể dùng @Aggregation với placeholder tham số. MongoTemplate thuận tiện hơn khi pipeline động, nhiều facets/lookup hoặc cần options và streaming.

### Bài 22. maxTime và HTTP timeout

Application đặt maxTime 10 giây nhưng gateway timeout sau 2 giây.

**Câu hỏi:** maxTime có đảm bảo toàn bộ request kết thúc trước 2 giây không?

**Đáp án:** không. maxTime là tùy chọn command/server; cần phối hợp deadline HTTP/application, network, mapping và cancellation.

### Bài 23. allowDiskUse

Một báo cáo group/sort tiêu tốn nhiều memory.

**Câu hỏi:** chỉ bật allowDiskUse(true) đã đủ tối ưu chưa?

**Đáp án:** không. Nó có thể cho phép disk spill ở một số stages nhưng làm tăng I/O, không sửa pipeline thiếu index/filter, không vượt giới hạn BSON document/facet.

### Bài 24. Stream 1 triệu rows

Code lấy aggregateStream, sau đó gọi:

~~~java
List<RegionOrder> all = stream.toList();
~~~

**Câu hỏi:** có còn đạt mục tiêu giảm memory không?

**Đáp án:** không nếu vẫn thu toàn bộ rows vào List. Cần xử lý từng item/batch, giới hạn output và đóng stream.

### Bài 25. Kiểm soát input sort

API cho phép caller gửi arbitrary field name và biến thành Sort.by(fieldName).

**Câu hỏi:** có rủi ro gì?

**Đáp án:** field chưa được phép, không tồn tại, quá tốn tài nguyên hoặc làm lộ metadata. Nên allowlist các field output hợp lệ và giới hạn số rows/time range.

### Bài 26. Pagination sau group

Collection có một triệu orders nhưng report group thành 20 regions.

**Câu hỏi:** totalCount trả 1.000.000 có đúng cho pagination regions không?

**Đáp án:** không, totalGroups phải đếm **20** sau các filter/group tương ứng. Count collection là một metric khác.

### Bài 27. $lookup nhầm tenant

Một order và một customer thuộc hai tenants trùng customerRef. Pipeline join theo customerRef mà không kiểm tenant.

**Câu hỏi:** vì sao nguy hiểm?

**Đáp án:** có thể ghép nhầm và tiết lộ dữ liệu tenant khác. Cần predicate/keys/ACL đảm bảo tenant isolation ở cả hai collections.

### Bài 28. Shape mismatch

Pipeline trả:

~~~javascript
{ amount: NumberDecimal("120.50"), name: "Book" }
~~~

DTO:

~~~java
public record Result(String itemName, int revenue) {}
~~~

**Yêu cầu:** xác định hai vấn đề mapping.

**Đáp án:** field names **amount/name** khác **revenue/itemName**; numeric type Decimal128 không phù hợp int nếu cần giữ cents. Cần aliases đúng và BigDecimal.

### Bài 29. Dynamic reporting có bảo mật

Xây report nhận:

~~~text
Authenticated tenantId (required)
Optional status
Optional from/to
Sort: revenue / orderCount only
Limit: tối đa 100
~~~

**Yêu cầu:** nêu thứ tự stages, validation và DTO.

**Định hướng:** lấy tenantId từ auth, validate date range, build Criteria và match sớm, group/sum/count, project aliases, sort theo allowlist và limit bounded; trả RegionRevenue, không trả raw BSON.

### Bài 30. Thiết kế báo cáo end-to-end

Yêu cầu: Dashboard cho doanh nghiệp bán hàng với ba số liệu:

1. Doanh thu PAID theo region.
2. Số order theo status.
3. Số quantity bán theo sku.

Đồng thời phải tránh trộn tenant, xử lý Decimal128, hỗ trợ nhiều vùng thời gian, có khả năng chạy trên dữ liệu lớn.

**Định hướng giải pháp:**

- Thiết kế **common tenant match**.
- Chọn facet với mỗi branch phù hợp, hoặc nhiều pipelines nếu chi phí facet lớn.
- Revenue branch filter PAID rồi group region.
- Status branch group status không filter PAID.
- SKU branch filter PAID, unwind items, group items.sku sum quantity.
- Project aliases và tạo DashboardReport với ba nested lists.
- Validate BigDecimal/long, timezone nếu có daily breakdown.
- Phân quyền outputs, đặt giới hạn tài nguyên, kiểm tra index/explain.
- Integration test bằng dữ liệu hai tenants, nhiều statuses và multiple items.

## 33. Các stage nâng cao và những lưu ý tương thích

MongoDB Aggregation Framework có nhiều stages ngoài các ví dụ cơ bản. Spring Data MongoDB có thể hỗ trợ trực tiếp hoặc qua custom AggregationOperation tùy phiên bản.

| Stage | Công dụng | Điều cần lưu ý |
|---|---|---|
| **$addFields / $set** | Thêm field được tính | Field có thể ghi đè field cũ |
| **$unset** | Bỏ field | Stage sau không thể dựa vào field đã bỏ |
| **$replaceRoot / $replaceWith** | Thay shape root document | DTO phải khớp root mới |
| **$bucket / $bucketAuto** | Phân phối giá trị thành buckets | Kiểu _id và ranh giới buckets |
| **$sortByCount** | Đếm và sort theo nhóm | Output thường có _id và count |
| **$setWindowFields** | Window metrics, running totals | Sort/partition/window syntax, server version |
| **$unionWith** | Gộp dòng từ collection/pipeline khác | Output schema khác nhau cần normalize |
| **$graphLookup** | Truy vấn quan hệ đệ quy | Depth, cycle, memory và ACL |
| **$geoNear** | Geo distance | Vị trí stage, geospatial index |
| **$search / $vectorSearch** | Atlas Search/Vector Search | Deployment và vị trí stage, không thay bằng $match |
| **$out / $merge** | Ghi output sang collection | Side effects, quyền ghi và idempotency |

### 33.1. $merge và $out không giống report chỉ đọc

Nếu pipeline kết thúc bằng **$merge** hoặc **$out**, dữ liệu có thể được ghi vào collection khác. Trong Spring Data, chúng cần được dùng với API tương thích, quyền ghi, retry và lifecycle riêng.

Không gắn một pipeline ghi dữ liệu vào endpoint GET chỉ để làm “báo cáo tạm”, vì request lặp lại hoặc timeout có thể tạo side effects khó kiểm soát.

### 33.2. Materialized summary

Với báo cáo được đọc hàng nghìn lần nhưng cập nhật ít, có thể lưu một **materialized summary**:

~~~text
Orders collection
      |
      v
Scheduled aggregation (controlled batch)
      |
      v
summary_by_region collection
      |
      v
Read API -> small indexed query
~~~

Thiết kế này giảm tải aggregation lặp lại nhưng phải xử lý **freshness, incremental updates, backfill, idempotency và quyền tenant**. Không gọi summary table là hoàn toàn realtime nếu nó được làm mới theo lịch.

### 33.3. $search và $vectorSearch không phải stage tự do

Atlas Search và Vector Search có yêu cầu deployment, index và vị trí trong pipeline. Một custom stage Java có thể tạo BSON nhưng không bỏ qua những giới hạn server như yêu cầu stage đứng đầu hoặc không hỗ trợ trong một loại subpipeline nhất định.

### 33.4. AggregationUpdate khác Aggregate query

Spring Data có **AggregationUpdate** cho update pipeline trong những phiên bản phù hợp. Nó sử dụng các phép biến đổi để cập nhật documents, **khác** với đọc báo cáo qua **MongoTemplate.aggregate(...)**. Không dùng một pipeline đọc có $group/$facet trong update nếu MongoDB update pipeline không hỗ trợ những stages đó.

## 34. Checklist triển khai báo cáo Spring Data Aggregation

### 34.1. Data contract

- [ ] Đã xác định rõ metric và điều kiện filter.
- [ ] Có tenant/authorization scope bắt buộc.
- [ ] Đã phân biệt count orders, count line items và sum quantities.
- [ ] Đã biết BSON types và xử lý null/missing.
- [ ] Đã chốt currency, rounding và timezone.
- [ ] Có data sample bao gồm edge cases.

### 34.2. Pipeline

- [ ] $match lọc dữ liệu đầu vào đúng và sớm khi semantics cho phép.
- [ ] $group keys và accumulators đúng metric.
- [ ] $unwind không làm đếm trùng sai.
- [ ] $lookup bảo vệ join scope và chỉ lấy field cần.
- [ ] $facet có giới hạn output/memory hợp lý.
- [ ] $project tạo aliases khớp DTO, không bỏ field dùng sau.
- [ ] $sort có tie-breaker khi phân trang cần ổn định.
- [ ] Cấu hình index theo query pattern thực.

### 34.3. Spring Data mapping

- [ ] Typed/untyped aggregation dùng đúng tên Java/BSON.
- [ ] @Field trên domain entity được hiểu đúng.
- [ ] Output DTO đại diện cho shape sau stage cuối, không dùng input entity tùy tiện.
- [ ] _id sau group được project/ánh xạ có chủ đích.
- [ ] Decimal128/Int64/Date được map sang Java types phù hợp.
- [ ] getUniqueMappedResult chỉ dùng cho 0..1 dòng.
- [ ] Nested array/object map đúng cấu trúc DTO.

### 34.4. Vận hành

- [ ] Có maxTime và application deadline phù hợp.
- [ ] allowDiskUse được cân nhắc theo workload chứ không bật mặc định vì thiếu index.
- [ ] Có giới hạn date range/limit/concurrency cho report API.
- [ ] Với output lớn, có streaming/batch/materialized alternative.
- [ ] Có metrics latency/rows/failed aggregation và alerting.
- [ ] Explain/test trên dữ liệu đủ đại diện.
- [ ] Không log raw documents chứa thông tin bí mật.

## 35. Bảng ghi nhớ nhanh

| Muốn làm gì? | Spring Data API chính | MongoDB stage |
|---|---|---|
| Lọc documents | match(Criteria...) | $match |
| Chọn/đổi tên fields | project().and(...).as(...) | $project |
| Gộp theo field | group("field") | $group |
| Đếm trong group | count().as("n") | $sum: 1 |
| Cộng một numeric field | sum("amount").as("total") | $sum |
| Trung bình | avg("amount").as("avg") | $avg |
| Sort | sort(Sort.Direction...) | $sort |
| Giới hạn rows | limit(n) | $limit |
| Bỏ qua rows | skip(n) | $skip |
| Tách array thành rows | unwind("items") | $unwind |
| Join collection | lookup(...) | $lookup |
| Nhiều nhánh báo cáo | facet(...).as(...) | $facet |
| Đếm và sort theo field | sortByCount("field") | $sortByCount |
| Phân phối theo khoảng | bucket(...), bucketAuto(...) | $bucket, $bucketAuto |
| Chạy query | mongoTemplate.aggregate(...) | aggregate command |
| Stream rows | mongoTemplate.aggregateStream(...) | cursor-backed aggregate |
| Map kết quả | AggregationResults<DTO> | BSON result -> Java DTO |
| Input mapping | TypedAggregation<Entity> | @Field Java -> BSON |
| Options | AggregationOptions | maxTime/allowDiskUse/... |

### 35.1. Mẫu pipeline thường dùng

~~~java
TypedAggregation<OrderEntity> agg = newAggregation(
        OrderEntity.class,
        match(Criteria.where("tenantId").is(trustedTenantId)
                .and("status").is("PAID")),
        group("region")
                .count().as("orderCount")
                .sum("grossAmount").as("revenue"),
        project("orderCount", "revenue")
                .and("_id").as("region")
                .andExclude("_id"),
        sort(Sort.by(
                Sort.Order.desc("revenue"),
                Sort.Order.asc("region")))
);

List<RegionRevenue> result = mongoTemplate
        .aggregate(agg, RegionRevenue.class)
        .getMappedResults();
~~~

### 35.2. Những câu hỏi tự kiểm tra trước khi gọi aggregate

1. **Input field name** là Java property hay BSON field?
2. Stage trước có **giữ lại** field mà stage sau đang dùng không?
3. Khóa group đang nằm trong **_id** hay alias riêng?
4. Output có **bao nhiêu documents**, và DTO có khớp số lượng/type không?
5. Numeric output là Decimal128, Double, Int64 hay String?
6. Date grouping có timezone nghiệp vụ không?
7. Tenant và ACL có được áp dụng ở mọi nhánh/join không?
8. Output có đủ nhỏ và query có thể tận dụng index không?

## 36. Tài liệu tham khảo

Các khả năng và tên API có thể thay đổi theo Spring Data/MongoDB server version. Nên đối chiếu tài liệu chính thức:

- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [Spring Data MongoDB — Repository Query Methods và @Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html)
- [Spring Data MongoDB — MongoTemplate API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/MongoTemplate.html)
- [Spring Data MongoDB — Aggregation API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/aggregation/Aggregation.html)
- [Spring Data MongoDB — TypedAggregation API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/aggregation/TypedAggregation.html)
- [Spring Data MongoDB — AggregationResults API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/aggregation/AggregationResults.html)
- [Spring Data MongoDB — AggregationOptions API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/aggregation/AggregationOptions.html)
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Manual — Aggregation Stages](https://www.mongodb.com/docs/manual/reference/operator/aggregation-pipeline/)
- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)

Khi Spring Boot dependency management đã chọn một nhánh Spring Data cụ thể, dùng **API reference của cùng phiên bản** thay vì trộn cú pháp từ nhiều bản tài liệu.

## 37. Kết luận

Aggregation trong Spring Data MongoDB có hai lớp cần nắm vững:

~~~text
          JAVA / SPRING DATA LAYER

  Domain Entity + @Field metadata
                   |
                   v
  AggregationOperation / TypedAggregation
                   |
                   v
              MongoTemplate
                   |
                   v
          MONGODB SERVER LAYER

   $match -> $group -> $project -> $sort
                   |
                   v
            BSON result documents
                   |
                   v
          JAVA / SPRING DATA LAYER

         MappingMongoConverter
                   |
                   v
         AggregationResults<DTO>
                   |
                   v
            Service / REST API
~~~

**Những nguyên tắc quan trọng nhất:**

1. **Pipeline là một chuỗi biến đổi**; output stage trước quyết định field mà stage sau có thể sử dụng.
2. **TypedAggregation** giúp ánh xạ Java properties theo **@Field**, nhưng vẫn cần hiểu tên BSON và các alias được tạo trong pipeline.
3. **$group đặt khóa nhóm vào _id**; nếu DTO cần region, status, category... thì project alias minh bạch.
4. **DTO là hợp đồng output**; không tự dùng lại entity đầu vào sau khi group/project/lookup đã thay đổi schema.
5. **Numeric BSON type quyết định Java type**. Với tiền tệ, ưu tiên Decimal128/BigDecimal và quy tắc làm tròn rõ ràng.
6. **$unwind làm tăng số intermediate rows**; phân biệt đếm dòng item với đếm đơn hàng.
7. **$lookup trả array**, cần xử lý null và kiểm soát quyền join, nhất là trong multi-tenant data.
8. **$facet có ích cho dashboard** nhưng phải giới hạn kích thước output và memory.
9. **AggregationResults** có List/unique/raw methods khác nhau; **aggregateStream** phù hợp output lớn nhưng phải đóng cursor-backed stream.
10. **Tính đúng và hiệu năng đi cùng nhau**: tenant filtering, index/query plan, bounded result, timeout, integration tests và authorization đều cần được thiết kế chủ động.

Điểm cốt lõi là **viết pipeline theo đúng metric nghiệp vụ và ánh xạ theo đúng hình dạng BSON cuối cùng**. Khi phân biệt rõ input entity, intermediate stage fields, MongoDB aliases và Java output DTO, việc xây báo cáo trong Spring Data MongoDB trở nên dễ đọc, dễ kiểm thử và tránh được nhiều lỗi số liệu âm thầm.
