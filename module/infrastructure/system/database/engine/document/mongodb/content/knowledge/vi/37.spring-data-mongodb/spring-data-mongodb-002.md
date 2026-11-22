# Ánh xạ @Document, @Id, @Field và cấu trúc document lồng nhau trong Spring Data MongoDB

## 1. Bài toán: từ Java object đến MongoDB document

Một dịch vụ quản lý tin đăng thuê nhà viết bằng **Java và Spring Boot** cần lưu thông tin như sau:

~~~text
Listing
  id
  tenantId
  title
  monthlyRent
  address
    cityCode
    district
    coordinates
      longitude
      latitude
  rooms[]
    type
    areaSqm
    amenities[]
  tags[]
  createdAt
~~~

Trong Java, developer muốn dùng tên thuộc tính theo quy ước **camelCase**: monthlyRent, cityCode, createdAt. Trong MongoDB, nhóm lưu trữ đã thống nhất các trường theo **snake_case** như monthly_rent, city_code và created_at. Trường nhận dạng chính phải nằm ở **_id**, còn address và rooms cần được giữ như **embedded documents**, không phải tạo collection mới cho từng đối tượng nhỏ.

Spring Data MongoDB cung cấp cơ chế **object-document mapping** để chuyển đổi hai biểu diễn:

~~~text
                 Java application
                       |
                       v
            ListingDocument (POJO)
              id: ObjectId
              tenantId: String
              address: Address
              rooms: List<Room>
                       |
                       v
        Spring Data MongoDB mapping layer
            MappingMongoConverter
                       |
                       v
                BSON document
              _id: ObjectId
              tenant_id: String
              address: { ... }
              rooms: [ { ... }, ... ]
                       |
                       v
                   MongoDB
              rental_listings_398
~~~

Ba annotation trọng tâm:

- **@Document:** khai báo một Java type được dùng làm MongoDB document root và cấu hình collection.
- **@Id:** khai báo property nhận dạng, ánh xạ tới trường **_id** của BSON.
- **@Field:** cấu hình tên field hoặc một số tùy chọn biểu diễn của property trong BSON, chẳng hạn target type.

Các object con, lists và maps thường được ánh xạ đệ quy thành **embedded documents/arrays** ngay cả khi class con không có annotation @Document.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích pipeline **Java object → MappingMongoConverter → BSON** và chiều ngược lại.
2. Dùng **@Document(collection = "...")** để xác định collection của document root.
3. Dùng **@Id** đúng với **_id**, phân biệt ObjectId, String ID và @MongoId.
4. Dùng **@Field** để đặt tên lưu trữ riêng, ví dụ monthlyRent → monthly_rent.
5. Ánh xạ **embedded object, nested object nhiều tầng, List và Map**.
6. Đọc BSON thực tế và nhận biết **_class**, BSON Date, Decimal128, arrays, null và missing fields.
7. Truy vấn nested properties bằng **MongoRepository** và **MongoTemplate**.
8. Thiết kế index dựa trên **tên field BSON** và đường dẫn lồng nhau.
9. Phân biệt **embedding**, **DBRef** và **DocumentReference** về cách lưu dữ liệu.
10. Xử lý schema evolution, đổi tên field và mối nguy mất dữ liệu khi save document cũ.
11. Kiểm thử mapping, tránh nhầm lẫn với validation hoặc authorization nghiệp vụ.
12. Triển khai một lab hoàn chỉnh với package, model classes, repository, service và mongosh verification.

> **Phạm vi phiên bản:** Ví dụ dùng cú pháp Java 17+ và Spring Boot 3.x/Spring Data MongoDB tương ứng làm nền để học. API/chức năng nhỏ và hành vi tự tạo index hoặc cấu hình driver có thể khác theo phiên bản; kiểm tra tài liệu chính thức cho version đang dùng. Các ví dụ chỉ sử dụng database lab **mongo_mapping_lab_398**, collection **rental_listings_398** và dữ liệu giả. Không kết nối hay sửa production để thực hành.

## 2. Spring Data MongoDB mapping có vai trò gì?

### 2.1. BSON không phải Java object

MongoDB lưu **BSON documents**. Một document có thể chứa:

~~~javascript
{
  _id: ObjectId("660000000000000000000398"),
  tenant_id: "tenant-001",
  title: "Studio gần công viên",
  monthly_rent: NumberDecimal("12500000.00"),
  address: {
    city_code: "HCM",
    district: "Binh Thanh",
    coordinates: {
      longitude: 106.71,
      latitude: 10.80
    }
  },
  rooms: [
    {
      type: "bedroom",
      area_sqm: 22,
      amenities: ["desk", "wifi"]
    }
  ],
  tags: ["near-park", "furnished"],
  created_at: ISODate("2026-01-15T09:30:00Z")
}
~~~

Java có classes, private fields, constructors, records, generics và enums. BSON có những kiểu lưu trữ như **ObjectId, Date, Decimal128, string, number, boolean, document, array, null**.

Mapping layer phải quyết định:

- Property Java nào tương ứng với tên field BSON nào?
- Kiểu Java nào tương ứng BSON type nào?
- Nested object có nhúng trong document cha không?
- Property nào là ID?
- Dùng constructor nào khi đọc BSON?
- Khi thiếu field, Java nhận null, primitive default hay giá trị theo constructor?
- Có cần converter tùy chỉnh không?

### 2.2. MappingMongoConverter

Trong Spring Data MongoDB, thành phần chính của mapping là **MappingMongoConverter**, sử dụng mapping metadata và các conversions để chuyển giữa đối tượng Java với BSON Document.

Sơ đồ:

~~~text
MongoRepository / MongoTemplate
              |
              v
       MappingMongoConverter
              |
       +------+------+
       |             |
  Mapping context   Custom conversions
       |             |
 @Document/@Id/    Converter Java <-> BSON
 @Field/metadata    khi được đăng ký
       |             |
       +------+------+
              |
              v
         MongoDB Driver
              |
              v
             BSON
~~~

Điều này khác với việc dùng Java driver thuần theo cách tự tạo Document:

~~~java
Document raw = new Document()
    .append("tenant_id", "tenant-001")
    .append("title", "Studio");
~~~

Với Spring Data, ta có thể lưu **ListingDocument** mà mapping layer tự chuyển tên field, nested types và ID.

### 2.3. Annotation hỗ trợ mapping, không phải validation

**@Document** và **@Field** không tự ép mọi document trong MongoDB theo một schema cố định. Một client mongosh hoặc service khác vẫn có thể ghi document thiếu trường nếu server không có validation phù hợp.

Để kiểm tra dữ liệu đầu vào, cần thêm:

- Java Bean Validation và kiểm tra ở API/service.
- Business invariant.
- MongoDB **$jsonSchema validation** nếu cần cưỡng chế tại database.
- Tests và migration khi schema thay đổi.

Không coi annotation mapping là một cơ chế database constraint tự động.

## 3. Chuẩn bị Spring Boot và MongoDB lab

### 3.1. Dependency

Một ứng dụng Spring Boot dùng starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Spring Boot quản lý phiên bản dependency qua dependency management tương ứng. Đừng ghép tùy tiện Spring Data MongoDB mới với một Spring Boot version không tương thích.

Nếu dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
}
~~~

Mã ví dụ dùng **Spring Data MongoRepository** và **MongoTemplate** đều có trong starter thông dụng.

### 3.2. application.yml của lab local

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://127.0.0.1:27017/mongo_mapping_lab_398"
~~~

Đây chỉ là URI cho MongoDB **lab local**. Production cần TLS, credentials theo secret manager, least-privilege database user và cấu hình network phù hợp. Không commit password thật vào application.yml.

Spring Boot còn cho phép cấu hình thông qua environment variables hoặc secret injection của runtime. Đừng hardcode credentials trong source.

### 3.3. Cấu trúc package minh họa

~~~text
src/main/java/com/example/mongo398/
  Mongo398Application.java
  domain/
    ListingDocument.java
    Address.java
    Coordinates.java
    Room.java
  repository/
    ListingRepository.java
  service/
    ListingService.java
~~~

Những tên file trong bài là **mô tả học tập**, không phải các file Worker tạo bên ngoài row398.md.

### 3.4. Kết nối và quyền

Một service CRUD cần đủ permissions cho các thao tác đọc/ghi tương ứng. Nếu triển khai chỉ có read, không nên dùng root. Nếu ứng dụng tạo index khi startup, cần tách quyền quản lý index cho migration job khi phù hợp.

Để hiểu vấn đề mapping, chúng ta dùng lab riêng thay vì bật chức năng tự tạo index trên cluster production.

## 4. @Document: Java type đại diện collection

### 4.1. Cú pháp cơ bản

~~~java
package com.example.mongo398.domain;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "rental_listings_398")
public class ListingDocument {

    @Id
    private ObjectId id;

    private String title;

    protected ListingDocument() {
        // Constructor cho mapping framework.
    }

    public ListingDocument(String title) {
        this.title = title;
    }

    public ObjectId getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

**@Document(collection = "rental_listings_398")** nói rằng root object này sẽ được lưu ở collection **rental_listings_398** khi dùng các API mapping mặc định với type đó.

Nếu không chỉ rõ collection, Spring Data có convention để suy ra collection name từ type; nhưng convention có thể không khớp schema hiện có. Chỉ định rõ tên thường giúp tránh thay đổi ngoài ý muốn khi refactor class.

### 4.2. @Document không tương đương SQL CREATE TABLE

MongoDB có thể tạo collection khi lần đầu ghi dữ liệu theo hành vi server; việc chỉ khai báo @Document **không đảm bảo collection đã được tạo**.

~~~text
@Document được đọc bởi mapping context
                 |
                 v
           Mapping metadata
                 |
            insert/save
                 |
                 v
          MongoDB collection
~~~

Nếu cần collection validator, collation, indexes hoặc tạo collection có kiểm soát, nên dùng migration/administration workflow phù hợp.

### 4.3. Một entity gắn với một collection mặc định

~~~java
@Document(collection = "tenant_listings")
public class TenantListing {
    @Id
    private String id;
}
~~~

Đây là mapping của entity type tới collection mặc định. Không có nghĩa một class chỉ được dùng trong duy nhất một collection trong mọi API: MongoTemplate có những overload cho phép chọn collection name khi thao tác.

Tuy nhiên, override collection động cần quản lý consistency, indexes, tenant authorization và migration. Đừng dùng tên collection tùy ý từ request người dùng.

### 4.4. @Document trên nested class có cần không?

Không. Một class **Address** có thể là value object được nhúng:

~~~java
public class Address {
    private String cityCode;
    private String district;
}
~~~

Khi Address là property của ListingDocument, Spring Data có thể ghi nó thành subdocument. Không cần thêm @Document cho Address chỉ để nhúng.

**@Document không tự biến mọi property tham chiếu tới class đó thành quan hệ giữa hai collections**. Quan hệ tham chiếu là một lựa chọn riêng, ví dụ @DBRef/@DocumentReference.

## 5. @Id: property nào trở thành BSON _id?

### 5.1. Trường _id của MongoDB

Trong một MongoDB collection, mỗi document có một trường **_id** làm định danh duy nhất trong collection. Spring Data dùng **@Id** để xác định Java property ánh xạ tới trường đó:

~~~java
@Id
private ObjectId id;
~~~

BSON:

~~~javascript
{
  _id: ObjectId("660000000000000000000398"),
  title: "Studio"
}
~~~

Không có field BSON riêng mang tên **id** ở document trên.

### 5.2. Tên Java không nhất thiết là id

~~~java
@Id
private ObjectId listingId;
~~~

Property Java tên **listingId** vẫn là **_id** khi được ghi ra BSON.

Vì vậy, trong Java:

~~~java
listing.getListingId()
~~~

và trong mongosh:

~~~javascript
db.rental_listings_398.findOne({
  _id: ObjectId("660000000000000000000398")
});
~~~

đang nói về cùng định danh.

### 5.3. ObjectId được tạo khi nào?

Khi insert object mới có ID kiểu **ObjectId** và giá trị chưa được gán, Spring Data/driver có thể tự tạo ID theo mapping/insertion path. Nếu cần hoàn toàn rõ ràng trong lab, ta có thể **chủ động cấp ObjectId**:

~~~java
ObjectId id = new ObjectId();
~~~

Không tự tạo ObjectId mới mỗi lần **save** một entity hiện có, vì như vậy có thể khiến lệnh ghi trở thành một document khác.

### 5.4. @Id String có conversion cần chú ý

~~~java
@Id
private String id;
~~~

Spring Data MongoDB có quy tắc chuyển đổi cho ID. Một chuỗi ID hợp lệ dưới dạng 24 ký tự hex có thể được chuyển thành **BSON ObjectId**, còn chuỗi khác có thể lưu dưới dạng **BSON String** tùy mapping path.

Ví dụ ý nghĩa:

~~~text
Java id: "660000000000000000000398"
  -> có thể lưu BSON ObjectId

Java id: "listing-398"
  -> lưu String
~~~

Không mặc định mọi @Id String đều được lưu BSON string. Việc khác BSON type có thể làm truy vấn driver thuần hoặc mongosh không khớp.

### 5.5. @MongoId để kiểm soát BSON type của ID

Nếu muốn ID lưu **đúng kiểu String** ngay cả khi trông giống ObjectId, Spring Data cung cấp **@MongoId**.

~~~java
import org.springframework.data.mongodb.core.mapping.MongoId;
import org.springframework.data.mongodb.core.mapping.FieldType;

public class ExternalListing {

    @MongoId(FieldType.STRING)
    private String id;

    public String getId() {
        return id;
    }
}
~~~

**@MongoId(FieldType.STRING)** giúp diễn đạt rõ ý định lưu ID ở dạng BSON string; **@MongoId(FieldType.OBJECT_ID)** diễn đạt ý định ObjectId phù hợp. Cú pháp và conversion behavior nên được kiểm thử với Spring Data version thật.

**Không khai báo đồng thời @Id và @MongoId trên cùng property** như hai nguồn sự thật. Chọn một chiến lược.

### 5.6. ObjectId vs UUID vs domain key

| ID strategy | Ưu điểm | Lưu ý |
| --- | --- | --- |
| **ObjectId** | Phổ biến, BSON native, thuận tiện tạo ID | DTO/REST thường cần chuyển sang chuỗi hex |
| **String có nghĩa nghiệp vụ** | Dễ tích hợp với hệ ngoài | Kiểu BSON và độ dài/index size cần kiểm soát |
| **UUID** | Tạo ID phân tán, ít phụ thuộc server | Cấu hình UUID representation/driver cần nhất quán |
| **Compound business identity** | Biểu diễn khóa miền nghiệp vụ | _id một field; có thể dùng embedded ID hoặc unique index tùy thiết kế |

Một _id không phải mặc định là **tenant authorization**. Khi đọc listing bằng ID, application vẫn cần kiểm tra tenant/owner:

~~~java
// Ý tưởng: phải có tenantId được xác thực.
// Chỉ query theo _id chưa đủ bảo vệ cross-tenant access.
~~~

### 5.7. Không đổi kiểu _id tùy tiện khi migration

Nếu collection đang có:

~~~javascript
{ _id: ObjectId("660000000000000000000398") }
~~~

thì query:

~~~javascript
{ _id: "660000000000000000000398" }
~~~

không tương đương hoàn toàn ở BSON vì String và ObjectId là hai kiểu khác nhau. Dữ liệu cũ và mới có thể không khớp nếu chuyển từ ObjectId sang String mà không migration đúng.

## 6. @Field: ánh xạ tên property thành tên BSON field

### 6.1. Ví dụ cơ bản

~~~java
@Field("tenant_id")
private String tenantId;

@Field("monthly_rent")
private BigDecimal monthlyRent;

@Field("created_at")
private Instant createdAt;
~~~

Java:

~~~text
tenantId
monthlyRent
createdAt
~~~

MongoDB:

~~~text
tenant_id
monthly_rent
created_at
~~~

**@Field không đổi tên biến Java**. Nó mô tả tên sử dụng khi persistence mapping.

### 6.2. Không gắn @Field khi tên giống nhau

Nếu tên property Java và BSON đều là **title**, có thể khai báo:

~~~java
private String title;
~~~

Spring Data dùng convention để ánh xạ. Có thể thêm @Field("title") để thể hiện contract rõ ràng nhưng không bắt buộc.

### 6.3. @Field và @Id khác nhiệm vụ

| Annotation | Mục đích | BSON kết quả |
| --- | --- | --- |
| @Document(collection = "rental_listings_398") | Xác định collection root | Collection name |
| @Id ObjectId id | Định danh document | _id |
| @Field("tenant_id") String tenantId | Tên field dữ liệu | tenant_id |
| @Field("monthly_rent") BigDecimal monthlyRent | Tên field và có thể thêm type config | monthly_rent |

**_id là trường đặc biệt.** Không cố dùng @Field("listingId") để thay thế semantics của @Id. Nếu một ID domain được lưu dưới tên khác, phải hiểu đó là **một field bình thường** hoặc thiết kế identity của MongoDB khác, không phải tự động đổi tên _id.

### 6.4. @Field targetType

Với dữ liệu tiền, **BigDecimal** là kiểu Java giúp biểu diễn số thập phân chính xác hơn floating point. MongoDB có kiểu **Decimal128**:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Field(
    value = "monthly_rent",
    targetType = FieldType.DECIMAL128
)
private BigDecimal monthlyRent;
~~~

Document MongoDB:

~~~javascript
{
  monthly_rent: NumberDecimal("12500000.00")
}
~~~

**Không giả định BigDecimal mặc định được lưu Decimal128 ở mọi cấu hình/converter.** Tùy annotation và conversions, cách biểu diễn có thể khác. Với số tiền, nên thống nhất domain policy về currency/scale/rounding, có tests và schema validation.

### 6.5. Thay @Field không tự đổi dữ liệu cũ

Nếu class cũ:

~~~java
private String postalCode;
~~~

lưu BSON field **postalCode**, rồi đổi thành:

~~~java
@Field("postal_code")
private String postalCode;
~~~

Spring Data bắt đầu tìm/ghi **postal_code** theo mapping mới. Những documents cũ chỉ có **postalCode** không tự được đổi tên trong MongoDB.

Hệ quả:

- Đọc record cũ có thể thấy property null.
- Query theo property mới có thể bỏ sót documents cũ.
- save toàn document có thể vô tình xóa/ghi đè field cũ theo hình dạng mới.

Cần migration có kế hoạch, không coi annotation là công cụ ALTER COLUMN trực tiếp.

## 7. Mô hình Java đầy đủ: root và các embedded value objects

### 7.1. Root document

File minh họa **ListingDocument.java**:

~~~java
package com.example.mongo398.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "rental_listings_398")
public class ListingDocument {

    @Id
    private ObjectId id;

    @Field("tenant_id")
    private String tenantId;

    @Field("title")
    private String title;

    @Field(
        value = "monthly_rent",
        targetType = FieldType.DECIMAL128
    )
    private BigDecimal monthlyRent;

    @Field("address")
    private Address address;

    @Field("rooms")
    private List<Room> rooms = new ArrayList<>();

    @Field("tags")
    private List<String> tags = new ArrayList<>();

    @Field("available")
    private boolean available;

    @Field("created_at")
    private Instant createdAt;

    @Transient
    private String displayLabel;

    protected ListingDocument() {
        // Dành cho Spring Data khi materialize object.
    }

    public ListingDocument(
            String tenantId,
            String title,
            BigDecimal monthlyRent,
            Address address,
            List<Room> rooms,
            List<String> tags,
            boolean available,
            Instant createdAt) {
        this.tenantId = tenantId;
        this.title = title;
        this.monthlyRent = monthlyRent;
        this.address = address;
        this.rooms = rooms == null
                ? new ArrayList<>() : new ArrayList<>(rooms);
        this.tags = tags == null
                ? new ArrayList<>() : new ArrayList<>(tags);
        this.available = available;
        this.createdAt = createdAt;
    }

    public ObjectId getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getTitle() {
        return title;
    }

    public BigDecimal getMonthlyRent() {
        return monthlyRent;
    }

    public Address getAddress() {
        return address;
    }

    public List<Room> getRooms() {
        return rooms;
    }

    public List<String> getTags() {
        return tags;
    }

    public boolean isAvailable() {
        return available;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getDisplayLabel() {
        return displayLabel;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public void setMonthlyRent(BigDecimal monthlyRent) {
        this.monthlyRent = monthlyRent;
    }

    public void setAvailable(boolean available) {
        this.available = available;
    }
}
~~~

**Giải thích mapping:**

1. **@Document** chọn collection.
2. **@Id** đặt ObjectId vào BSON **_id**.
3. **@Field("tenant_id")** đổi tên field.
4. **@Field(... targetType = DECIMAL128)** chỉ định biểu diễn tiền.
5. **address** là một embedded document.
6. **rooms** là BSON array chứa embedded documents.
7. **tags** là BSON array của strings.
8. **createdAt** là thời điểm, chuyển thành kiểu ngày phù hợp qua conversions.
9. **@Transient** khiến **displayLabel** không được persistence mapping như một field thông thường.

Đây là POJO mutable có no-arg constructor để dễ thấy quá trình mapping; trong dự án thật có thể dùng immutable classes/records, builder hoặc Lombok nhưng cần hiểu constructor binding và access rules.

### 7.2. Address — embedded object

File minh họa **Address.java**:

~~~java
package com.example.mongo398.domain;

import org.springframework.data.mongodb.core.mapping.Field;

public class Address {

    @Field("city_code")
    private String cityCode;

    @Field("district")
    private String district;

    @Field("coordinates")
    private Coordinates coordinates;

    protected Address() {
    }

    public Address(
            String cityCode,
            String district,
            Coordinates coordinates) {
        this.cityCode = cityCode;
        this.district = district;
        this.coordinates = coordinates;
    }

    public String getCityCode() {
        return cityCode;
    }

    public String getDistrict() {
        return district;
    }

    public Coordinates getCoordinates() {
        return coordinates;
    }
}
~~~

Kết quả lồng trong parent:

~~~javascript
{
  address: {
    city_code: "HCM",
    district: "Binh Thanh",
    coordinates: { /* nested document */ }
  }
}
~~~

Không tạo một collection **address** chỉ vì khai báo class Address. Spring Data ánh xạ theo quan hệ property của parent khi không có chỉ dẫn reference đặc biệt.

### 7.3. Coordinates — document lồng cấp thứ ba

File **Coordinates.java**:

~~~java
package com.example.mongo398.domain;

public class Coordinates {

    private double longitude;
    private double latitude;

    protected Coordinates() {
    }

    public Coordinates(double longitude, double latitude) {
        this.longitude = longitude;
        this.latitude = latitude;
    }

    public double getLongitude() {
        return longitude;
    }

    public double getLatitude() {
        return latitude;
    }
}
~~~

BSON:

~~~javascript
{
  address: {
    coordinates: {
      longitude: 106.71,
      latitude: 10.80
    }
  }
}
~~~

Đây chỉ là cặp tọa độ thông thường. Nếu muốn dùng **2dsphere geospatial index**, MongoDB thường mong đợi biểu diễn **GeoJSON** hoặc tọa độ theo định dạng hỗ trợ; không coi object có longitude/latitude ở bất kỳ cấu trúc nào là tự động sử dụng được $near.

### 7.4. Room — phần tử của array

File **Room.java**:

~~~java
package com.example.mongo398.domain;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Field;

public class Room {

    @Field("type")
    private String type;

    @Field("area_sqm")
    private int areaSqm;

    @Field("amenities")
    private List<String> amenities = new ArrayList<>();

    protected Room() {
    }

    public Room(
            String type,
            int areaSqm,
            List<String> amenities) {
        this.type = type;
        this.areaSqm = areaSqm;
        this.amenities = amenities == null
                ? new ArrayList<>() : new ArrayList<>(amenities);
    }

    public String getType() {
        return type;
    }

    public int getAreaSqm() {
        return areaSqm;
    }

    public List<String> getAmenities() {
        return amenities;
    }
}
~~~

Room không có @Id vì nó không phải root document được lưu ở collection riêng. Nếu ứng dụng cần nhận diện từng Room để update một phần tử array, có thể bổ sung **roomId** như field nghiệp vụ trong subdocument; đó không tự động trở thành MongoDB root _id.

### 7.5. Tổng hợp cây ánh xạ

~~~text
ListingDocument                       BSON
----------------------------------------------------------------
id: ObjectId                      -> _id: ObjectId(...)
tenantId: String                  -> tenant_id: "tenant-001"
title: String                     -> title: "Studio"
monthlyRent: BigDecimal           -> monthly_rent: Decimal128(...)
address: Address                  -> address: { ... }
  cityCode: String                ->   city_code: "HCM"
  district: String                ->   district: "Binh Thanh"
  coordinates: Coordinates        ->   coordinates: { ... }
    longitude: double             ->     longitude: 106.71
    latitude: double              ->     latitude: 10.80
rooms: List<Room>                 -> rooms: [ { ... }, ... ]
  areaSqm: int                    ->   area_sqm: 22
  amenities: List<String>         ->   amenities: ["desk","wifi"]
tags: List<String>                -> tags: ["near-park"]
createdAt: Instant                -> created_at: Date(...)
displayLabel: @Transient          -> không ghi field
~~~

## 8. MongoDB document sinh ra trông như thế nào?

### 8.1. Một BSON document minh họa

Nếu insert ListingDocument bằng converter mặc định, dạng BSON logic có thể là:

~~~javascript
{
  _id: ObjectId("660000000000000000000398"),
  tenant_id: "tenant-001",
  title: "Studio gần công viên",
  monthly_rent: NumberDecimal("12500000.00"),
  address: {
    city_code: "HCM",
    district: "Binh Thanh",
    coordinates: {
      longitude: 106.71,
      latitude: 10.80
    }
  },
  rooms: [
    {
      type: "bedroom",
      area_sqm: 22,
      amenities: ["desk", "wifi"]
    },
    {
      type: "kitchen",
      area_sqm: 8,
      amenities: ["stove"]
    }
  ],
  tags: ["near-park", "furnished"],
  available: true,
  created_at: ISODate("2026-01-15T09:30:00Z"),
  _class: "com.example.mongo398.domain.ListingDocument"
}
~~~

**_class** thường được MappingMongoConverter mặc định ghi làm type information, đặc biệt cho root documents và các tình huống đa hình. Các embedded values có thể có hoặc không có type metadata bổ sung tùy mapping/concrete type. Đây là mẫu minh họa, không phải cam kết từng byte của mọi cấu hình Spring Data.

### 8.2. Vì sao có _class?

Một document có thể được đọc về type tương ứng:

~~~text
_class:
  com.example.mongo398.domain.ListingDocument
~~~

Điều này giúp converter xác định type khi metadata cần thiết, nhất là khi Java property khai báo interface/base class nhưng dữ liệu chứa subclass.

Những hệ thống không muốn lưu FQCN có thể dùng **@TypeAlias** hoặc tùy chỉnh type mapper theo Spring Data. Nhưng thay đổi type metadata là **quyết định schema/compatibility**, không nên xóa _class trực tiếp trên production chỉ vì “nhìn thừa”.

### 8.3. Thực tế _class có thể khác

Nếu cấu hình converter thay đổi type mapping, _class có thể:

- Chứa alias ngắn.
- Không được ghi trong một số trường hợp.
- Sử dụng metadata khác theo custom type mapper.

Không viết integration test so nguyên văn document bao gồm _class mà không chủ động cố định configuration.

### 8.4. Extended JSON và BSON representation

MongoDB shell hiển thị ObjectId, ISODate, NumberDecimal thuận tiện cho người đọc. Khi export dạng **Extended JSON**, giá trị có thể xuất hiện:

~~~json
{
  "_id": { "$oid": "660000000000000000000398" },
  "monthly_rent": { "$numberDecimal": "12500000.00" },
  "created_at": { "$date": "2026-01-15T09:30:00Z" }
}
~~~

Đây là cách biểu diễn JSON của BSON types, không có nghĩa MongoDB thật lưu một document con **$oid** bên trong _id. Cần phân biệt **BSON native types** với **Extended JSON notation**.

## 9. Tạo một ListingDocument và lưu bằng MongoTemplate

### 9.1. Tạo object

~~~java
Address address = new Address(
    "HCM",
    "Binh Thanh",
    new Coordinates(106.71, 10.80)
);

List<Room> rooms = List.of(
    new Room("bedroom", 22, List.of("desk", "wifi")),
    new Room("kitchen", 8, List.of("stove"))
);

ListingDocument listing = new ListingDocument(
    "tenant-001",
    "Studio gần công viên",
    new BigDecimal("12500000.00"),
    address,
    rooms,
    List.of("near-park", "furnished"),
    true,
    Instant.parse("2026-01-15T09:30:00Z")
);
~~~

Trước khi insert, **listing.getId()** có thể là null. Khi lưu qua Spring Data, ID thường được cấp theo mapping strategy.

### 9.2. Insert

~~~java
ListingDocument saved = mongoTemplate.insert(listing);

System.out.println(saved.getId());
~~~

Nếu document mới, insert lưu vào collection từ @Document. **insert** có ý nghĩa tạo document mới và có thể bị duplicate key nếu _id đã tồn tại.

### 9.3. Save

~~~java
listing.setTitle("Studio gần công viên - đã cập nhật");
mongoTemplate.save(listing);
~~~

**save** thường có semantics chèn hoặc thay thế/upsert dựa vào ID theo mapping, khác với update một field đơn lẻ. Cần cẩn trọng với:

- Properties bị null hoặc default.
- Nested object chưa được load đầy đủ.
- Concurrent updates làm mất thay đổi của người khác.
- Dữ liệu cũ có fields không còn trong class mapping.

Khi chỉ cần sửa một field, **Update** có mục tiêu hẹp thường tốt hơn save toàn bộ document.

### 9.4. Find by ID

~~~java
ObjectId id = saved.getId();

ListingDocument loaded =
    mongoTemplate.findById(id, ListingDocument.class);

System.out.println(loaded.getTitle());
~~~

Đây là cách đọc lại object qua converter: BSON **_id** được ánh xạ về Java **id**.

### 9.5. Repository

Nếu dùng Spring Data repository:

~~~java
package com.example.mongo398.repository;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;
import com.example.mongo398.domain.ListingDocument;

public interface ListingRepository
        extends MongoRepository<ListingDocument, ObjectId> {
}
~~~

Các phương thức như **save**, **findById**, **findAll** và **deleteById** được cung cấp theo interface tương ứng. Không coi repository abstraction là một cách vượt qua MongoDB authorization hoặc transaction rules.

## 10. Query theo tên Java property hay tên BSON field?

### 10.1. MongoTemplate hiểu mapping metadata

Khi khai báo:

~~~java
@Field("tenant_id")
private String tenantId;
~~~

ta có thể dùng tên Java property trong **typed query**:

~~~java
Query query = new Query(
    Criteria.where("tenantId").is("tenant-001")
);

List<ListingDocument> result =
    mongoTemplate.find(query, ListingDocument.class);
~~~

Spring Data mapping layer có thể dịch **tenantId** thành BSON field **tenant_id** khi truy vấn được thực hiện với entity mapping context.

### 10.2. Không coi Criteria.where là raw mongosh query

Trong mongosh, phải dùng tên lưu trữ:

~~~javascript
db.rental_listings_398.find({
  tenant_id: "tenant-001"
});
~~~

MongoDB server **không biết Java property tenantId** nếu database chỉ có field tenant_id.

### 10.3. Nested property path

Với model:

~~~text
ListingDocument.address
Address.cityCode -> @Field("city_code")
~~~

Typed MongoTemplate query:

~~~java
Query query = new Query(
    Criteria.where("tenantId").is("tenant-001")
        .and("address.cityCode").is("HCM")
        .and("available").is(true)
);
~~~

BSON query tương ứng về logic:

~~~javascript
{
  tenant_id: "tenant-001",
  "address.city_code": "HCM",
  available: true
}
~~~

Ở đây, **address.cityCode** là property path của Java, còn **address.city_code** là dotted path của document lưu trữ.

### 10.4. Dotted path và tên field thật

MongoDB dùng dấu chấm để truy vấn nested field:

~~~javascript
{
  "address.coordinates.longitude": {
    $gte: 106.5
  }
}
~~~

Đây không phải trường có literal name **address.coordinates.longitude** được lưu trực tiếp trong document root theo mô hình của bài; nó là **đường dẫn tới nested value**.

Spring Data MongoDB có các chế độ/khả năng xử lý tên field chứa dấu chấm thật tùy phiên bản, nhưng đó là tình huống đặc biệt. Đừng tạo schema với field names có dấu chấm chỉ vì muốn “nhét” dotted path vào tên field.

## 11. MongoRepository: derived queries theo nested properties

### 11.1. Repository với query methods

~~~java
package com.example.mongo398.repository;

import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;
import com.example.mongo398.domain.ListingDocument;

public interface ListingRepository
        extends MongoRepository<ListingDocument, ObjectId> {

    List<ListingDocument> findByTenantIdAndAvailableTrue(
        String tenantId
    );

    List<ListingDocument> findByTenantIdAndAddress_CityCode(
        String tenantId,
        String cityCode
    );

    Page<ListingDocument> findByTenantIdAndAvailableTrue(
        String tenantId,
        Pageable pageable
    );
}
~~~

Tên method **Address_CityCode** sử dụng dấu gạch dưới làm điểm tách rõ đường dẫn property trong cú pháp derived query của Spring Data (không phải dấu gạch dưới của BSON field name). Nó biểu diễn đường dẫn Java **address.cityCode**.

**Lưu ý về overload:** Hai phương thức findByTenantIdAndAvailableTrue ở trên có danh sách tham số khác nhau nên là overload hợp lệ trong Java. Trong dự án thực, nên đặt tên/ngữ nghĩa rõ ràng, tránh tạo overload gây khó hiểu cho đội phát triển.

### 11.2. Query method không dùng tên field BSON

Nếu Java property là monthlyRent và BSON field là monthly_rent, method:

~~~java
List<ListingDocument> findByTenantIdAndMonthlyRentLessThanEqual(
    String tenantId,
    BigDecimal maxRent
);
~~~

dựa vào **Java property names**. Spring Data repository mapping giúp chuyển sang tên BSON tương ứng.

### 11.3. @Query với tên trường lưu trữ

Bạn cũng có thể viết JSON query:

~~~java
import org.springframework.data.mongodb.repository.Query;

@Query("{ 'tenant_id': ?0, 'address.city_code': ?1 }")
List<ListingDocument> findByStoredFields(
    String tenantId,
    String cityCode
);
~~~

Khi dùng **@Query**, cần biết bạn đang viết MongoDB JSON query string và convention field names được mapping xử lý theo phiên bản. Để tránh nhầm, trong tài liệu dự án hãy thống nhất dùng **stored names rõ ràng** nếu viết JSON trực tiếp, còn derived queries/typed Criteria thì ưu tiên **Java property paths**.

### 11.4. Pageable và sort

~~~java
Pageable pageable = PageRequest.of(
    0, 20, Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<ListingDocument> page =
    repository.findByTenantIdAndAvailableTrue(
        "tenant-001", pageable
    );
~~~

Khi dùng Spring Data repository, sort theo property **createdAt** được mapping sang **created_at**, và **id** sang **_id**. Nhớ import:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
~~~

Với dữ liệu lớn, offset pagination có thể kém hiệu quả ở những trang sâu; cân nhắc keyset pagination theo created_at + _id với index phù hợp và có kiểm thử.

## 12. Embedded documents: khi nào dùng và vì sao?

### 12.1. Một địa chỉ thuộc tin đăng

Một địa chỉ thường được đọc cùng tin đăng. Nhúng giúp lấy tất cả trong một document:

~~~javascript
{
  title: "Studio",
  address: {
    city_code: "HCM",
    district: "Binh Thanh"
  }
}
~~~

Thay vì:

~~~text
listings:
  listingId -> addressId

addresses:
  addressId -> cityCode, district
~~~

MongoDB embedded model phù hợp khi address có vòng đời phụ thuộc listing và thường được đọc cùng listing.

### 12.2. Ưu điểm

- Đọc một document chứa đầy đủ dữ liệu liên quan.
- Cập nhật nhiều field trong **cùng document** có atomicity theo semantics single-document của MongoDB.
- Giảm nhu cầu join/$lookup.
- Cấu trúc query rõ ràng theo nested path.

### 12.3. Giới hạn

- Document MongoDB có **giới hạn kích thước BSON** (thông thường 16 MiB cho một document).
- Arrays tăng liên tục có thể làm document lớn và gây contention.
- Một phần dữ liệu có vòng đời độc lập hoặc được nhiều parents tham chiếu có thể không phù hợp để nhúng.
- Khi update nested array phải xử lý đúng điều kiện phần tử.
- Data replication/transfer có thể tốn chi phí khi document lớn.

Không nhúng một lịch sử sự kiện tăng không giới hạn vào **ListingDocument.rooms** hoặc một array tương tự nếu không có chiến lược bounding.

### 12.4. One-to-few, one-to-many, unbounded

| Quan hệ | Thiết kế thường cân nhắc |
| --- | --- |
| Một tin có một địa chỉ | Embedded Address |
| Một căn hộ có 2–10 phòng | Embedded List<Room> |
| Một tin có vài chục tags | Embedded List<String> |
| Một tin có hàng triệu page views | Collection riêng cho events |
| Một owner có nhiều listings độc lập | Reference hoặc field ownerId; cân nhắc nhu cầu đọc |

Lựa chọn theo **query patterns, update frequency, growth, ownership/lifecycle**, không chỉ theo sơ đồ UML.

## 13. Nested arrays và truy vấn đúng phần tử

### 13.1. Array of embedded documents

Java:

~~~java
@Field("rooms")
private List<Room> rooms;
~~~

BSON:

~~~javascript
{
  rooms: [
    {
      type: "bedroom",
      area_sqm: 22,
      amenities: ["desk", "wifi"]
    },
    {
      type: "kitchen",
      area_sqm: 8,
      amenities: ["stove"]
    }
  ]
}
~~~

### 13.2. Query array có phần tử thỏa điều kiện

Mongosh:

~~~javascript
db.rental_listings_398.find({
  "rooms.amenities": "wifi"
});
~~~

Query này tìm document có **ít nhất một phần tử rooms** có amenities chứa wifi, theo semantics truy vấn array của MongoDB.

Typed MongoTemplate:

~~~java
Query q = new Query(
    Criteria.where("rooms.amenities").is("wifi")
);

List<ListingDocument> matches =
    mongoTemplate.find(q, ListingDocument.class);
~~~

### 13.3. Hai điều kiện phải thuộc cùng một room

Sai khi tưởng hai predicates luôn áp dụng trên cùng phần tử:

~~~javascript
{
  "rooms.type": "bedroom",
  "rooms.area_sqm": { $gte: 20 }
}
~~~

Một document có thể có **room A là bedroom** và **room B rộng 20 m²**; hai điều kiện dotted trên array có thể match khác phần tử.

Dùng **$elemMatch**:

~~~javascript
db.rental_listings_398.find({
  rooms: {
    $elemMatch: {
      type: "bedroom",
      area_sqm: { $gte: 20 }
    }
  }
});
~~~

Typed MongoTemplate:

~~~java
Query q = new Query(
    Criteria.where("rooms").elemMatch(
        Criteria.where("type").is("bedroom")
            .and("areaSqm").gte(20)
    )
);
~~~

Đường dẫn **areaSqm** bên trong type Room được mapping tương ứng sang BSON field **area_sqm** khi query dùng mapping context của ListingDocument. Khi dùng các dạng raw BSON update/aggregation, phải xem rõ mapping semantics của API đang dùng.

### 13.4. Cập nhật nested array

MongoDB hỗ trợ positional operators và arrayFilters trong update. Các thao tác này cần xác định:

- Phần tử nào được match.
- Có cập nhật một hay nhiều phần tử.
- Client version có map field aliases trong arrayFilters như mong muốn không.
- Concurrency và điều kiện nghiệp vụ.

Không dùng:

~~~javascript
{ $set: { rooms: [] } }
~~~

chỉ để cập nhật diện tích của một phòng: lệnh này thay cả array bằng rỗng.

Một update có điều kiện rõ ràng và được test trên lab tốt hơn việc load object rồi **save** toàn document khi nhiều user có thể sửa các rooms khác nhau.

## 14. Maps và dynamic attributes

### 14.1. Map trong Java

~~~java
@Field("attributes")
private Map<String, String> attributes;
~~~

BSON tương ứng:

~~~javascript
{
  attributes: {
    floor: "12",
    orientation: "east",
    furnishing: "full"
  }
}
~~~

Map phù hợp khi các key được kiểm soát nhưng có thể mở rộng.

### 14.2. Những điều cần chú ý

- Map keys trở thành field names trong BSON nested object.
- Không tùy tiện nhận keys trực tiếp từ client không tin cậy.
- Dấu chấm và ký tự **$** trong field names có ràng buộc/hành vi đặc biệt theo MongoDB version và API; nhiều query/update operators dùng dot notation.
- Không để map tăng không giới hạn trong một document.
- Nếu cần index và query ổn định trên thuộc tính quan trọng, một typed Java property có thể rõ hơn Map động.

### 14.3. Typed class vs Map

~~~java
public class Address {
    private String cityCode;
}
~~~

có lợi:

- Compiler nhận biết property.
- Dễ đặt @Field alias và validation.
- Derived repository queries an toàn hơn về refactor.

Map:

~~~java
Map<String, Object> address;
~~~

có lợi cho schema rất linh hoạt nhưng làm yếu type safety, validation và khả năng dự đoán query patterns.

## 15. Nested object khác reference

### 15.1. Embedded object mặc định

~~~java
private Address address;
~~~

Lưu:

~~~javascript
{ address: { city_code: "HCM" } }
~~~

### 15.2. Reference kiểu @DBRef

Spring Data có annotation **@DBRef**:

~~~java
@DBRef
private OwnerDocument owner;
~~~

Đây là một quan hệ tham chiếu tới document khác, **không nhúng toàn bộ OwnerDocument theo semantics mặc định của DBRef**. Đọc reference có thể đòi thêm database queries và cần quan tâm eager/lazy loading, hiệu năng và serialization.

### 15.3. @DocumentReference

Spring Data MongoDB cũng có **@DocumentReference** để biểu diễn tham chiếu linh hoạt theo mapping/lookup đã cấu hình. Nó khác @DBRef về cách lưu/resolve reference.

Không cần dùng @DBRef hay @DocumentReference cho **Address** nếu address không có vòng đời độc lập. Dùng reference chỉ khi access patterns và lifecycle biện minh.

### 15.4. Một-to-nhiều độc lập

Một owner có nhiều listings, các listings thay đổi độc lập. Thường cân nhắc lưu:

~~~javascript
{
  _id: ObjectId(...),
  owner_id: ObjectId("...")
}
~~~

và query/list theo owner_id, thay vì nhúng toàn bộ hàng nghìn listings vào một owner document. Quan hệ tham chiếu có thể được biểu diễn bằng field ID đơn giản hoặc annotation reference, tùy nhu cầu.

## 16. Các kiểu Java thường gặp và BSON tương ứng

| Java property | BSON thường gặp | Lưu ý |
| --- | --- | --- |
| String | String | Không phải mọi String ID đều được lưu String nếu @Id có conversion |
| ObjectId | ObjectId | Dùng cho _id hoặc trường BSON ObjectId |
| int/Integer | Int32 | Primitive nhận default 0 khi thiếu field |
| long/Long | Int64 | Khác Int32; kiểm tra kiểu khi schema evolution |
| double/Double | Double | Có sai số binary floating-point |
| BigDecimal | Có thể Decimal128 với @Field targetType | Thống nhất scale/rounding |
| boolean/Boolean | Boolean | boolean mặc định false; Boolean có thể null |
| Instant, Date | BSON Date | Kiểm soát timezone và precision |
| List<T> | Array | Nested elements được convert theo T |
| Map<String,T> | Embedded object/document | Key names cần policy |
| Enum | Thường String theo converter mặc định | Đổi enum names có thể phá dữ liệu cũ |
| POJO value object | Embedded document | Có thể có type metadata tùy trường hợp |

Chi tiết conversion có thể phụ thuộc converter registrations, custom conversions và driver; bảng là khái quát chứ không phải thay thế kiểm thử thực tế.

### 16.1. Instant và timezone

~~~java
@Field("created_at")
private Instant createdAt;
~~~

BSON Date lưu mốc thời gian, thường biểu diễn theo UTC epoch milliseconds. **Instant** có semantics một thời điểm rõ ràng; đối với lịch hẹn theo giờ địa phương, còn có thể cần **ZoneId** và business timezone.

Đừng dùng **LocalDateTime** rồi giả định nó chứa timezone. Nếu chuyển từ LocalDateTime sang Instant hoặc Date, hãy xác định zone và conversion policy.

### 16.2. Primitive và null

~~~java
private boolean available;
private int roomCount;
~~~

Nếu document BSON cũ không có field, object mới có thể dùng các giá trị default Java: false và 0.

~~~java
private Boolean available;
private Integer roomCount;
~~~

cho phép biểu diễn null trong Java. Nhưng **missing field** và **explicit BSON null** có thể cần được phân biệt ở migration/validation level; Java null một mình không luôn bảo tồn được sự khác biệt đó.

### 16.3. Enum

~~~java
enum ListingStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}
~~~

Thường lưu thành string tương ứng enum name theo converter mặc định:

~~~javascript
{ status: "ACTIVE" }
~~~

Đổi tên constant **ACTIVE** thành **PUBLISHED** mà không xử lý documents cũ có thể gây lỗi đọc hoặc lệch dữ liệu. Cân nhắc explicit stable codes và custom converters nếu cần schema lâu dài.

### 16.4. BigDecimal và tài chính

Với số tiền:

- Dùng BigDecimal hoặc biểu diễn **amountInMinorUnits** bằng long theo chính sách.
- Tránh dùng double để cộng trừ tiền nếu yêu cầu chính xác.
- Kiểm tra Decimal128 mapping thực lưu.
- Thêm currencyCode, scale và rounding policy.
- Không giả định chuỗi "12500000.00" và Decimal128 là tương đương về kiểu query.

## 17. Đọc object khi thiếu field hoặc thêm field mới

### 17.1. Schema-less không đồng nghĩa schema-free

MongoDB không bắt buộc mọi document trong cùng collection có đúng fields giống nhau, trừ khi có validation. Một collection có thể có:

~~~javascript
// Bản cũ
{
  _id: ObjectId(...),
  title: "Studio",
  tenant_id: "tenant-001"
}

// Bản mới
{
  _id: ObjectId(...),
  title: "Studio",
  tenant_id: "tenant-001",
  address: { city_code: "HCM" },
  available: true
}
~~~

Java class mới cần xử lý document cũ thiếu address:

~~~java
if (listing.getAddress() != null) {
    String city = listing.getAddress().getCityCode();
}
~~~

Nếu code mặc định gọi listing.getAddress().getCityCode() thì dễ gặp NullPointerException.

### 17.2. Constructor default không luôn là migration policy

Viết:

~~~java
private List<Room> rooms = new ArrayList<>();
~~~

giúp object mới có list rỗng trong một số đường tạo object. Nhưng trong immutable mapping, constructor binding và converter behavior có thể dẫn tới kết quả khác nếu input BSON thiếu/null.

Đừng dựa hoàn toàn vào field initializer để coi dữ liệu production cũ đã được backfill.

### 17.3. Đổi tên field

Từ:

~~~javascript
{ monthlyRent: NumberDecimal("12000000") }
~~~

sang:

~~~javascript
{ monthly_rent: NumberDecimal("12000000") }
~~~

Chỉ đổi @Field trong code không rewrite document cũ.

Trên **lab riêng**, một migration có thể dùng:

~~~javascript
db.rental_listings_398.updateMany(
  {
    labTag: "mongo398-v1",
    monthlyRent: { $exists: true },
    monthly_rent: { $exists: false }
  },
  {
    $rename: {
      monthlyRent: "monthly_rent"
    }
  }
);
~~~

Lệnh này **thay đổi dữ liệu** và không phải bước bắt buộc của bài học. Trên production cần đánh giá field conflicts, backup, index/query rollout, active writers và khả năng dual-read/dual-write phù hợp; không dùng một $rename hàng loạt khi đang có ứng dụng cũ vẫn ghi tên cũ mà chưa có kế hoạch.

### 17.4. Expand–migrate–contract

Một kế hoạch đổi field an toàn:

~~~text
Expand:
  Ứng dụng mới có thể đọc dữ liệu cũ và mới
         |
         v
Migrate:
  Backfill documents cũ theo batch có giới hạn
         |
         v
Verify:
  Đếm missing/new fields, check business values
         |
         v
Contract:
  Bỏ support field cũ sau khi writers/readers đã chuyển
~~~

**Đừng deploy mapping mới rồi ngay lập tức save toàn bộ collection** nếu dữ liệu cũ chưa được xử lý.

### 17.5. Unknown fields

Một document có thể chứa fields mà class Java không định nghĩa. Khi đọc qua converter, những fields ấy không tự trở thành properties trong Java object.

Nếu sau đó **save** object, cần cân nhắc nguy cơ làm mất unknown fields do replacement semantics. Khi chỉ cập nhật một field, dùng targeted Update có thể giảm rủi ro.

## 18. @Transient, static fields và computed properties

### 18.1. @Transient

~~~java
import org.springframework.data.annotation.Transient;

@Transient
private String displayLabel;
~~~

Property này không được persistence mapping thành BSON field. Phù hợp với:

- Giá trị được tính để hiển thị.
- Cache tạm trong object.
- Trạng thái không cần lưu.

Không dùng @Transient để “ẩn” thông tin nhạy cảm khỏi API JSON; **persistence mapping** khác **Jackson serialization**. Một property transient với MongoDB vẫn có thể được JSON serializer trả ra nếu có getter và không cấu hình API DTO.

### 18.2. @Transient có thể ảnh hưởng constructor binding

Nếu một immutable class có constructor parameter tương ứng một field @Transient, mapper có thể không có dữ liệu để bind theo cách bạn kỳ vọng. Cần thiết kế persistence constructor và derived fields cho rõ.

### 18.3. Computed values

Ví dụ:

~~~java
public String getDisplayTitle() {
    return title + " (" + tenantId + ")";
}
~~~

Nếu không có field mapping tương ứng, method này là logic Java. Không mặc định Spring Data sẽ lưu mọi getter dưới tên field mới; mapping thường dựa vào persistent properties/field access và metadata.

## 19. Constructor mapping, immutable classes và records

### 19.1. Mutable POJO

Mô hình trong mục 7 có:

- No-arg constructor.
- Fields được mapping layer truy cập.
- Getters cho application.
- Một số setters cho business updates.

Cách này dễ học và thường hoạt động ổn với Spring Data.

### 19.2. Immutable class

Một immutable model có final fields và constructor:

~~~java
public final class Money {

    private final BigDecimal amount;
    private final String currency;

    public Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

Spring Data có cơ chế constructor-based materialization; khi nhiều constructors/factory methods, có thể cần chỉ dẫn như **@PersistenceCreator** theo version và model.

### 19.3. Java record

Java 17:

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

public record AddressView(
    @Field("city_code") String cityCode,
    String district
) {}
~~~

Records thể hiện value objects bất biến và Spring Data có hỗ trợ record mapping trong các phiên bản tương ứng. Tuy nhiên, với root entity có ID được sinh tự động, records không có setter; cần hiểu cách mapping layer xử lý immutable properties, constructor binding và ID population.

Để tránh gây khó trong lab cơ bản, ví dụ chính dùng **mutable root POJO** và các embedded classes đơn giản.

### 19.4. @PersistenceCreator

Khi một class có nhiều constructors mà Spring Data cần biết constructor dùng để đọc persistence data, annotation **@PersistenceCreator** có thể được dùng theo API của Spring Data Commons.

~~~java
import org.springframework.data.annotation.PersistenceCreator;

public final class Label {
    private final String value;

    @PersistenceCreator
    public Label(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Không annotation bừa một constructor không chứa đủ required properties của immutable object. Cần kiểm thử BSON readback thực tế và tuân thủ rules về parameter names/type conversion.

## 20. Index theo nested fields và @Field alias

### 20.1. MongoDB index dùng tên BSON

Trong mongosh:

~~~javascript
db.rental_listings_398.createIndex(
  {
    tenant_id: 1,
    "address.city_code": 1,
    available: 1
  },
  { name: "ix_398_tenant_city_available" }
);
~~~

Index này giúp những query có điều kiện phù hợp trên tenant, city và available, tùy selectivity/sort và query plan.

Không dùng:

~~~javascript
{ tenantId: 1, "address.cityCode": 1 }
~~~

trong **mongosh raw** khi dữ liệu thật được lưu dưới tenant_id và city_code.

### 20.2. @CompoundIndex

Spring Data MongoDB có annotation hỗ trợ mô tả compound indexes:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;

@Document(collection = "rental_listings_398")
@CompoundIndex(
    name = "ix_398_tenant_city_available",
    def = "{ 'tenant_id': 1, 'address.city_code': 1, 'available': 1 }"
)
public class ListingDocument {
    // fields omitted
}
~~~

Đây là **mẫu annotation thêm vào model**, không phải một ListingDocument thứ hai trong cùng source code.

### 20.3. Annotation không đảm bảo index đã tồn tại

Spring Data MongoDB có cơ chế auto index creation/configuration, nhưng trong nhiều dự án và phiên bản, tự động tạo indexes **không được bật mặc định**. Ngoài ra, DB user runtime có thể không có quyền createIndex.

Do đó:

1. Định nghĩa index trong migration strategy.
2. Tạo index bằng identity có quyền phù hợp.
3. Xác nhận index build hoàn tất.
4. Kiểm tra bằng getIndexes/explain.
5. Đo tác động lên read và write.

Không dựa vào @Field hoặc @CompoundIndex như bằng chứng server chắc chắn đã có index.

### 20.4. Index cho array

~~~javascript
db.rental_listings_398.createIndex(
  { "rooms.amenities": 1 },
  { name: "ix_398_room_amenities" }
);
~~~

Vì rooms/amenities là arrays, index có thể là **multikey index**. Cần hiểu quy tắc index multikey và compound index khi có arrays; không ghép nhiều array fields vào compound index mà chưa kiểm tra giới hạn và chi phí.

### 20.5. Explain

~~~javascript
db.rental_listings_398.find({
  tenant_id: "tenant-001",
  "address.city_code": "HCM",
  available: true
}).explain("executionStats");
~~~

Quan sát:

- winningPlan.
- nReturned.
- totalKeysExamined.
- totalDocsExamined.
- executionTimeMillis.

Một index mới không tự bảo đảm plan được chọn hay request latency tốt hơn. Dataset, selectivity, sort và workload đồng thời đều quan trọng.

## 21. MongoTemplate: update field lồng nhau mà không replace cả document

### 21.1. Update một nested property

~~~java
Query query = new Query(
    Criteria.where("id").is(listingId)
        .and("tenantId").is(authorizedTenantId)
);

Update update = new Update()
    .set("address.cityCode", "HN");

mongoTemplate.updateFirst(
    query,
    update,
    ListingDocument.class
);
~~~

Với entity mapping context, Java property path **address.cityCode** được chuyển sang BSON **address.city_code**. Cách làm này nhắm một field thay vì save toàn object.

### 21.2. Tenant predicate là yêu cầu bảo mật

Không chỉ query:

~~~java
Criteria.where("id").is(listingId);
~~~

nếu dữ liệu thuộc nhiều tenant và application user không được đọc/sửa tenant khác. MongoDB RBAC thường giới hạn ở database/collection, **không tự thêm tenantId filter cho từng document**.

Phải lấy tenantId từ **security context đã xác minh** và đặt vào cả truy vấn đọc/ghi.

### 21.3. Update nested document nguyên khối

~~~java
Update update = new Update()
    .set("address", new Address(
        "HN",
        "Ba Dinh",
        new Coordinates(105.83, 21.03)
    ));
~~~

Thao tác set address có thể **thay toàn bộ embedded address**. Nếu address cũ có các fields mà new Address không biểu diễn, bạn có thể vô tình làm mất chúng. Chỉ dùng replacement khi business intent là thay tất cả address.

### 21.4. Optimistic locking

Spring Data có hỗ trợ **@Version** cho optimistic locking:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

Tính năng có thể giúp phát hiện một số concurrent updates khi save entity qua mapping APIs có hỗ trợ version. Nhưng:

- Cần version field trong document và migration policy cho dữ liệu cũ.
- Không tự áp dụng giống nhau cho mọi raw driver update.
- Phải xử lý conflict/retry ở service.
- Write concern và driver behavior có thể ảnh hưởng cách báo lỗi.

Không coi @Version là giải pháp thay thế tất cả concurrency controls hay business invariants.

## 22. DTO tách biệt persistence model

### 22.1. Không trả trực tiếp ListingDocument từ API

Persistence model có thể chứa:

- _id dạng ObjectId.
- tenantId nội bộ.
- Trường _class/metadata.
- Address chi tiết hoặc dữ liệu nhạy cảm.
- Các field mới chưa được phê duyệt cho API.

Nếu REST controller trả entity trực tiếp, JSON serialization có thể lộ fields hoặc tạo API contract bất ổn khi class thay đổi.

### 22.2. DTO trả về

~~~java
public record ListingResponse(
    String id,
    String title,
    String cityCode,
    String district,
    String monthlyRent
) {}
~~~

Mapper:

~~~java
public static ListingResponse toResponse(
        ListingDocument listing) {
    Address address = listing.getAddress();

    return new ListingResponse(
        listing.getId() == null
            ? null : listing.getId().toHexString(),
        listing.getTitle(),
        address == null ? null : address.getCityCode(),
        address == null ? null : address.getDistrict(),
        listing.getMonthlyRent() == null
            ? null : listing.getMonthlyRent().toPlainString()
    );
}
~~~

Chuyển BigDecimal thành string trong DTO ở đây nhằm giữ biểu diễn thập phân rõ ràng; API thực cần quy ước JSON money schema thống nhất, không chọn tùy tiện giữa string/number ở các endpoint.

### 22.3. DTO tạo mới

~~~java
public record CreateListingRequest(
    String title,
    String cityCode,
    String district,
    String monthlyRent
) {}
~~~

Khi tạo ListingDocument, **tenantId phải lấy từ session/token đã được server kiểm tra**, không tin trường do client tự gửi nếu user không được phép chọn tenant.

## 23. Kiểm thử mapping bằng MongoConverter

### 23.1. Vì sao cần test converter?

Khi thay @Field hoặc thay kiểu ID, chỉ nhìn Java class dễ bỏ sót:

- Field BSON được lưu sai tên.
- BigDecimal không lưu dưới BSON type mong muốn.
- Nested Address bị null.
- Array elements không được materialize.
- _class/type alias gây lỗi đọc.
- Document cũ thiếu fields.

Một test có thể kiểm tra cả **write conversion** và **read conversion**.

### 23.2. Mapping smoke check bằng converter

Trong test ứng dụng có MongoTemplate được cấu hình:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.convert.MongoConverter;

MongoConverter converter = mongoTemplate.getConverter();

ListingDocument source = new ListingDocument(
    "tenant-001",
    "Studio mapping smoke test",
    new BigDecimal("12500000.00"),
    new Address(
        "HCM",
        "Binh Thanh",
        new Coordinates(106.71, 10.80)
    ),
    List.of(new Room(
        "bedroom", 22, List.of("wifi")
    )),
    List.of("demo"),
    true,
    Instant.parse("2026-01-15T09:30:00Z")
);

Document raw = new Document();
converter.write(source, raw);

System.out.println(raw.toJson());

ListingDocument roundTrip =
    converter.read(ListingDocument.class, raw);

System.out.println(
    roundTrip.getAddress().getCityCode()
);
~~~

**Lưu ý:** converter.write với ObjectId id đang null có thể cho raw Document chưa có _id vì bước cấp ID thường nằm trong flow insert/save của MongoTemplate. Muốn test _id generation, phải test **insert** thực trên database lab. Không nhầm converter round-trip với full persistence flow.

### 23.3. Những assertions cần có

Trong một integration test:

~~~text
assert raw.containsKey("tenant_id")
assert !raw.containsKey("tenantId")
assert raw.get("address") là Document
assert nested.get("city_code") == "HCM"
assert raw.get("rooms") là List
assert rooms[0].get("area_sqm") == 22
assert Decimal128 representation phù hợp
assert roundTrip.getAddress().getCityCode() == "HCM"
~~~

Chúng là **gợi ý assertions**, không phải code JUnit hoàn chỉnh. Với Decimal128, dùng kiểu BSON/driver thực tế thay vì so text NumberDecimal của mongosh.

### 23.4. Kiểm thử schema evolution

Tạo dữ liệu cũ:

~~~javascript
{
  _id: ObjectId(...),
  tenant_id: "tenant-001",
  title: "Tin cũ",
  monthlyRent: NumberDecimal("8000000")
}
~~~

Sau đó đọc bằng mapping mới, xem monthlyRent property nhận giá trị gì, kiểm tra migration và không save lại nếu chưa có chiến lược bảo tồn dữ liệu.

### 23.5. Test với MongoDB thật

Converter-only test không kiểm tra:

- MongoDB index/unique constraint.
- Server-side JSON Schema validation.
- BSON size limit.
- Query planner/index.
- Repository method parsing và database query thật.
- Transaction/write concern.

Vì vậy, dự án nghiêm túc cần **integration tests với MongoDB instance/container thuộc version được triển khai** trong môi trường test. Không dùng production như database integration test.

## 24. Lab mongosh: đối chiếu Java mapping với BSON lưu thật

### 24.1. Mục đích

Nếu chưa dựng Spring Boot project, vẫn có thể tạo một BSON document tương ứng bằng mongosh rồi so với mapping table. Dùng database riêng:

~~~text
mongo_mapping_lab_398
  rental_listings_398
~~~

Chỉ ghi một document có _id cố định dành cho bài:

~~~text
ObjectId("660000000000000000000398")
~~~

### 24.2. Seed idempotent

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_mapping_lab_398");
  const listings = lab.getCollection("rental_listings_398");
  const id = ObjectId("660000000000000000000398");

  const sample = {
    _id: id,
    labTag: "mongo398-v1",
    tenant_id: "tenant-001",
    title: "Studio gần công viên",
    monthly_rent: NumberDecimal("12500000.00"),
    address: {
      city_code: "HCM",
      district: "Binh Thanh",
      coordinates: {
        longitude: 106.71,
        latitude: 10.80
      }
    },
    rooms: [
      {
        type: "bedroom",
        area_sqm: 22,
        amenities: ["desk", "wifi"]
      },
      {
        type: "kitchen",
        area_sqm: 8,
        amenities: ["stove"]
      }
    ],
    tags: ["near-park", "furnished"],
    available: true,
    created_at: ISODate("2026-01-15T09:30:00Z")
  };

  listings.replaceOne(
    {
      _id: id,
      labTag: "mongo398-v1"
    },
    sample,
    { upsert: true }
  );

  printjson(listings.findOne({ _id: id }));
})();
~~~

**Giới hạn an toàn:** Script chỉ nhắm _id cố định và labTag. Nếu đã có document trùng _id nhưng không thuộc bài, upsert sẽ gặp duplicate-key thay vì ghi đè theo filter. Không drop collection để giải quyết lỗi. Chỉ chạy trên database lab được phép viết.

**Khác biệt so với converter:** Document mongosh trên không có _class; mapping Java có thể vẫn đọc được khi type root đã được chỉ định qua **find(..., ListingDocument.class)**, nhưng không được giả định mọi tình huống đa hình đều hoạt động khi thiếu type metadata.

### 24.3. Xem field names

~~~javascript
const lab = db.getSiblingDB("mongo_mapping_lab_398");
const listings = lab.getCollection("rental_listings_398");

printjson(
  listings.findOne(
    {
      _id: ObjectId("660000000000000000000398")
    },
    {
      _id: 1,
      tenant_id: 1,
      monthly_rent: 1,
      "address.city_code": 1,
      rooms: 1
    }
  )
);
~~~

Lệnh projection đang sử dụng **stored BSON field names**, không phải Java property names.

### 24.4. Query nested city

~~~javascript
printjson(
  listings.find({
    labTag: "mongo398-v1",
    tenant_id: "tenant-001",
    "address.city_code": "HCM"
  }).toArray()
);
~~~

Kết quả mong đợi: document sample.

### 24.5. Query array với $elemMatch

~~~javascript
printjson(
  listings.find({
    labTag: "mongo398-v1",
    rooms: {
      $elemMatch: {
        type: "bedroom",
        area_sqm: { $gte: 20 }
      }
    }
  }, {
    _id: 1,
    title: 1,
    rooms: 1
  }).toArray()
);
~~~

Kết quả có sample vì cùng phần tử bedroom có area_sqm 22.

### 24.6. Trường absent vs null

~~~javascript
printjson({
  hasCity: listings.countDocuments({
    labTag: "mongo398-v1",
    "address.city_code": { $exists: true }
  }),
  explicitlyOrMissingNull: listings.countDocuments({
    labTag: "mongo398-v1",
    "address.city_code": null
  }),
  missingCity: listings.countDocuments({
    labTag: "mongo398-v1",
    "address.city_code": { $exists: false }
  })
});
~~~

Trong MongoDB, equality với null có thể match field null hoặc field không tồn tại; dùng **$exists** và **$type** khi muốn phân biệt trạng thái dữ liệu cụ thể.

### 24.7. Kiểm tra BSON type

~~~javascript
printjson(
  listings.aggregate([
    {
      $match: {
        _id: ObjectId("660000000000000000000398")
      }
    },
    {
      $project: {
        idType: { $type: "$_id" },
        rentType: { $type: "$monthly_rent" },
        addressType: { $type: "$address" },
        roomsType: { $type: "$rooms" },
        createdType: { $type: "$created_at" }
      }
    }
  ]).toArray()
);
~~~

Kết quả kỳ vọng về kiểu:

~~~text
idType      objectId
rentType    decimal
addressType object
roomsType   array
createdType date
~~~

### 24.8. Kiểm tra alias không có field cũ

~~~javascript
printjson(
  listings.findOne(
    {
      _id: ObjectId("660000000000000000000398")
    },
    {
      _id: 0,
      tenantId: 1,
      tenant_id: 1,
      monthlyRent: 1,
      monthly_rent: 1
    }
  )
);
~~~

Ở sample lab, stored fields là **tenant_id** và **monthly_rent**, không phải tenantId/monthlyRent.

### 24.9. Nested field update có kiểm soát

Nếu muốn minh họa update trên lab riêng:

~~~javascript
printjson(
  listings.updateOne(
    {
      _id: ObjectId("660000000000000000000398"),
      labTag: "mongo398-v1",
      tenant_id: "tenant-001"
    },
    {
      $set: {
        "address.district": "District 1"
      }
    }
  )
);
~~~

Điều kiện _id + labTag + tenant_id giới hạn phạm vi. Thao tác update này **có side effect**, chỉ chạy khi chủ động thực hành. Có thể chạy lại script seed để phục hồi document mẫu về giá trị ban đầu.

### 24.10. Thêm index cho query lab

~~~javascript
listings.createIndex(
  {
    tenant_id: 1,
    "address.city_code": 1,
    available: 1
  },
  { name: "ix_398_tenant_city_available" }
);
~~~

Không tạo index này ở production mà chưa đánh giá storage, write overhead và index build impact.

### 24.11. Explain query

~~~javascript
printjson(
  listings.find({
    tenant_id: "tenant-001",
    "address.city_code": "HCM",
    available: true
  }).explain("executionStats")
);
~~~

Với đúng một document lab, explain không mang nhiều ý nghĩa capacity. Nó chỉ giúp bạn xem field names và khái niệm index/query plan.

## 25. Những lỗi thường gặp khi mapping

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Đọc entity được nhưng id null | _id mapping/conversion không đúng; dữ liệu bất thường | Kiểm tra @Id, BSON _id và type |
| findBy... không trả kết quả | Nhầm Java property và BSON alias; ID type khác | Kiểm tra @Field, query mapped, BSON thật |
| Address bị null | Document cũ thiếu address hoặc constructor binding | Hỗ trợ null/migration |
| room areaSqm bằng 0 | BSON thiếu field hoặc tên lưu là area_sqm | Kiểm tra @Field và primitive defaults |
| Số tiền đọc sai | String/Double/Decimal128 khác nhau | Quy định Decimal128/conversion |
| Query @Id String không khớp | Chuỗi hex được lưu ObjectId | Kiểm tra BSON type, cân nhắc @MongoId |
| Document có _class | Default type metadata | Hiểu converter, không xóa tùy tiện |
| Document cũ mất field khi save | Replace toàn document sau mapping cũ/mới | Dùng targeted update/migration |
| Tưởng @Document tạo index | Annotation collection ≠ index creation | Migration index riêng |
| Tưởng @Field là validation | Mapping metadata không enforce schema | Bean Validation/$jsonSchema |
| Thiếu constructor phù hợp | Mapper không instantiate immutable/POJO | No-arg hoặc persistence constructor |
| Save embedded object ghi đè field khác | Thay toàn subdocument | Dùng dotted field update |
| Rooms query match sai phòng | Điều kiện array khác phần tử | $elemMatch |
| Truy vấn tenant chỉ bằng id | RBAC không tự lọc tenant | Server-side tenant filter |
| Lộ field nội bộ qua REST | Trả persistence entity trực tiếp | DTO rõ ràng |
| @Transient nhưng API vẫn trả | Mongo mapping ≠ Jackson serialization | DTO/JSON policy |
| Nested object bị tạo collection riêng ngoài ý muốn | Dùng repository riêng/reference sai nhu cầu | Phân biệt embedding/reference |
| Đổi @Field xong dữ liệu cũ không đổi | Annotation không migrate BSON | Expand–migrate–contract |
| Nhiều indexes tạo khi startup | Auto-index/job config chưa kiểm soát | Tách migration và least privilege |
| Null và missing bị hiểu một | MongoDB null query semantics | $exists/$type/schema validation |
| Map key từ user tạo dot path khó xử lý | Field naming và update semantics | Validate/whitelist keys |
| Dùng double cho tiền | Sai số floating point | BigDecimal/Decimal128 hoặc minor units |
| Record immutable không được set id | Constructor/id population khác POJO | Test version và chọn strategy |
| Test converter thành công nhưng DB insert lỗi | Chưa kiểm tra server indexes/constraints | Integration test MongoDB thật |

## 26. Quy trình thiết kế mapping cho một collection mới

### 26.1. Bước 1 — Bắt đầu từ access patterns

Hỏi:

- Một request thường đọc những fields nào?
- Address có luôn đi cùng listing không?
- Room count có giới hạn không?
- Các changes có cần atomic trong cùng document không?
- Document có tăng kích thước không?
- Dữ liệu có dùng chung giữa nhiều listings không?
- API cần tìm theo tenant/city/availability/price như thế nào?

Đây là những câu hỏi quan trọng hơn việc chọn annotation trước.

### 26.2. Bước 2 — Thiết kế BSON contract

Ví dụ:

~~~text
Collection: rental_listings_398
_id: ObjectId
tenant_id: String
title: String
monthly_rent: Decimal128
address.city_code: String
address.district: String
rooms[].type: String
rooms[].area_sqm: Int32
created_at: Date
~~~

Ghi lại kiểu dữ liệu và quy tắc missing/null. Từ đó annotation mới có contract rõ ràng.

### 26.3. Bước 3 — Viết Java model

1. @Document trên root.
2. @Id với ID strategy rõ.
3. @Field cho tên BSON khác Java.
4. Embedded classes cho nhóm fields có vòng đời phụ thuộc.
5. Arrays/Maps khi cần.
6. Constructor và accessors phù hợp.
7. @Transient cho property không cần persistence.

### 26.4. Bước 4 — Kiểm thử converter

- Java → BSON field names/types.
- BSON → Java nested structures.
- Missing fields.
- ID conversion.
- Decimal128/Date.
- _class/type alias.

### 26.5. Bước 5 — Kiểm thử truy vấn/index

- Repository derived query.
- Typed Criteria với nested path.
- BSON raw query.
- $elemMatch cho arrays.
- Indexes theo stored BSON names.
- Explain với dữ liệu đại diện.

### 26.6. Bước 6 — Kiểm soát compatibility

- Dữ liệu cũ có thể còn tên trường trước.
- Phải có migration/dual-read policy.
- Xem rename field và type changes.
- Chạy integration tests với fixture cũ/mới.
- Không save hàng loạt documents cũ nếu có nguy cơ mất unknown fields.

### 26.7. Bước 7 — Tách DTO và authorization

- API input được validate.
- tenantId đến từ trusted security context.
- Output chỉ có fields được phép.
- Không để client trực tiếp điều khiển collection/query raw tùy ý.
- MongoDB account chỉ có quyền collection/actions cần thiết.

## 27. Bài tập thực hành

### Bài 1 — Ba annotation chính

Giải thích mục đích khác nhau của @Document, @Id, @Field. Với mỗi annotation, nêu một thay đổi xảy ra ở collection/document khi persistence mapping.

### Bài 2 — @Document

Viết class ProductDocument được lưu ở collection catalog_products. Khi chỉ khai báo annotation mà chưa insert, có chắc collection đã tồn tại không?

### Bài 3 — @Id ObjectId

Một class có @Id ObjectId listingId. Field MongoDB lưu tên gì? Trong mongosh cần tìm theo listingId hay _id?

### Bài 4 — ID String

So @Id String id khi giá trị là "abc" và "660000000000000000000398". Có rủi ro gì về BSON type? Khi nào dùng @MongoId(FieldType.STRING)?

### Bài 5 — @Field alias

Ánh xạ Java tenantId, monthlyRent, createdAt sang BSON tenant_id, monthly_rent, created_at. Viết annotations tương ứng.

### Bài 6 — Decimal128

Tại sao double thường không thích hợp để biểu diễn tiền? Dùng annotation nào để thể hiện ý định lưu BigDecimal thành BSON Decimal128?

### Bài 7 — Embedded Address

Tạo Address gồm cityCode và district; đặt trong ListingDocument. Address có cần @Document không khi chỉ nhúng?

### Bài 8 — Nested nhiều tầng

Ánh xạ Address.coordinates.longitude và Address.coordinates.latitude. Viết BSON document lồng nhau tương ứng.

### Bài 9 — List<Room>

Ánh xạ một tin có hai rooms. Room type/areaSqm/amenities xuất hiện ở đâu trong BSON?

### Bài 10 — ObjectId vs Extended JSON

So BSON ObjectId thật với biểu diễn {"$oid":"..."} trong Extended JSON. Đâu là kiểu dữ liệu thực?

### Bài 11 — @Transient

Một property displayLabel chỉ dùng hiển thị. Dùng annotation nào để không lưu MongoDB? Điều đó có tự ngăn nó xuất hiện trong JSON response không?

### Bài 12 — _class

Vì sao document do Spring Data lưu có thể chứa _class? Trong tình huống nào alias/type mapper cần được thiết kế có kiểm soát?

### Bài 13 — Insert/save

So insert entity chưa có _id với save entity đã có _id. Vì sao save toàn document cần cẩn trọng trong hệ có concurrent updates?

### Bài 14 — Repository

Khai báo MongoRepository cho ListingDocument với ID ObjectId. Viết findByTenantIdAndAvailableTrue.

### Bài 15 — Nested derived query

Viết repository method tìm listings theo tenantId và address.cityCode. Giải thích dấu gạch dưới trong Address_CityCode của method name.

### Bài 16 — MongoTemplate

Viết Criteria theo Java property tenantId + address.cityCode + available. Dự đoán BSON query path thực lưu.

### Bài 17 — Mongosh

Viết mongosh find theo tenant_id và address.city_code. Nếu gõ tenantId và address.cityCode, chuyện gì có thể xảy ra với collection lab?

### Bài 18 — Array query

Viết query tìm listing có ít nhất một room có amenities chứa "wifi".

### Bài 19 — $elemMatch

Giải thích vì sao query "rooms.type":"bedroom" và "rooms.area_sqm":{$gte:20} không bắt buộc hai điều kiện nằm trên cùng room. Sửa bằng $elemMatch.

### Bài 20 — Maps

Ánh xạ Map<String,String> attributes vào embedded object. Nêu rủi ro nếu client được phép gửi key tùy ý chứa dấu chấm.

### Bài 21 — Embedded vs DBRef

Một owner có hàng nghìn listings thay đổi độc lập, nhưng mỗi listing chỉ có một address. Chọn embedding/reference cho từng quan hệ và giải thích theo access patterns.

### Bài 22 — 16 MiB document limit

Vì sao không nhúng một triệu pageViewEvents vào một ListingDocument? Thiết kế data model thay thế.

### Bài 23 — Missing field

Một document cũ không có address và available. Khi đọc vào Java POJO với Address reference và boolean available, ứng dụng cần xử lý tình huống nào?

### Bài 24 — Rename schema

Đổi @Field từ postalCode sang postal_code có tự cập nhật documents cũ không? Lập kế hoạch expand–migrate–contract.

### Bài 25 — Unknown fields

Một document cũ có legacy_notes không khai báo trong Java class. Vì sao read rồi save toàn document có thể gây mất dữ liệu?

### Bài 26 — Constructor

Một immutable class có hai constructors. Spring Data nên dùng constructor nào khi đọc BSON? Khi nào cân nhắc @PersistenceCreator?

### Bài 27 — Record

Viết record AddressView có @Field("city_code") String cityCode. So ưu/nhược với mutable POJO trong persistence mapping.

### Bài 28 — Index nested field

Viết index mongosh cho tenant_id + address.city_code + available. Vì sao dùng Java field alias names trực tiếp trong raw mongosh có thể sai?

### Bài 29 — Compound index

Thêm @CompoundIndex tương ứng. Có chắc MongoDB tự tạo index khi app chạy không? Ai nên chịu trách nhiệm migration index trong production?

### Bài 30 — Targeted Update

Viết MongoTemplate Update để sửa address.cityCode mà không replace toàn address. Tại sao cần tenantId trong Query filter?

### Bài 31 — DTO

Thiết kế ListingResponse trả id dưới dạng hex string, title, cityCode và monthlyRent. Vì sao không trả trực tiếp ListingDocument?

### Bài 32 — Converter round-trip

Lấy MongoTemplate.getConverter(), write ListingDocument ra Document rồi read trở lại. Những assertions nào chứng minh alias và nested objects đã được map đúng?

### Bài 33 — Mongosh lab

Chạy seed mục 24 trên database lab. Kiểm tra _id ObjectId, monthly_rent Decimal128, address object, rooms array, created_at date bằng $type.

### Bài 34 — Integration test

Tại sao converter-only test không thay thế integration test với MongoDB thật? Nêu các yếu tố index, validation, BSON size và authorization.

### Bài 35 — Tenant authorization

Một người dùng t001 đoán được _id của listing t002. Vì sao có @Id và @Document đúng vẫn không bảo vệ được truy cập xuyên tenant? Viết predicate bắt buộc trong service.

### Bài 36 — Thiết kế cuối bài

Hệ thống cần lưu listing có ObjectId, tenant ID, giá tiền, địa chỉ, tối đa 10 rooms, các tags và thời gian đăng. Hãy viết model annotations, một JSON/BSON mẫu, repository queries theo tenant/city, compound index, DTO, test schema cũ và kế hoạch migration an toàn.

## 28. Tài liệu tham khảo

- Spring Data MongoDB Reference — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html).
- Spring Data MongoDB Reference — [Mapping Configuration](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-config.html).
- Spring Data MongoDB Reference — [Mapping Usage](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html).
- Spring Data MongoDB Reference — [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html).
- Spring Data MongoDB Reference — [MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html).
- Spring Data MongoDB Reference — [MongoDB Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html).
- Spring Data MongoDB Reference — [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html).
- Spring Data MongoDB Reference — [Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html).
- Spring Data MongoDB Reference — [DBRef / Document References](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html).
- Spring Data MongoDB API — [@Document](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Document.html).
- Spring Data MongoDB API — [@Field](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Field.html).
- Spring Data MongoDB API — [@MongoId](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/MongoId.html).
- Spring Data Commons API — [@Id](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Id.html).
- MongoDB Manual — [Documents](https://www.mongodb.com/docs/manual/core/document/).
- MongoDB Manual — [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/).
- MongoDB Manual — [Query Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-embedded-documents/).
- MongoDB Manual — [Query Arrays of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/).
- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).

**Kết luận:** Trong Spring Data MongoDB, **@Document** chọn root collection, **@Id** ánh xạ định danh Java tới BSON **_id**, còn **@Field** định nghĩa tên field lưu trữ và một số tùy chọn kiểu BSON. **MappingMongoConverter** chuyển giữa Java objects và BSON, kể cả embedded objects nhiều tầng, arrays và maps; vì vậy một **Address** hoặc **Room** bình thường có thể được nhúng mà không cần collection riêng. Khi truy vấn, **Spring Data typed mapping dùng Java property paths**, trong khi **mongosh raw query dùng BSON stored field names**; nhầm hai lớp này dễ khiến query không trả dữ liệu. Các phần quan trọng đi kèm là **ObjectId/String ID conversion, Decimal128, _class, null/missing, index paths, constructor mapping và schema evolution**. Annotation không tự migrate dữ liệu cũ, không tự tạo mọi index, không cưỡng chế tenant authorization và không thay thế integration tests. Thiết kế bền vững cần **BSON contract rõ ràng, embedded model phù hợp access patterns, DTO riêng cho API, update có phạm vi và kiểm thử hai chiều Java ↔ BSON**.
