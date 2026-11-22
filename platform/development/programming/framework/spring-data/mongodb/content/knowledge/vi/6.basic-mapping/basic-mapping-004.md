# Ánh xạ field, constructor và dữ liệu lồng nhau

## 1. Bài toán ánh xạ trong Spring Data MongoDB

Trong chương **Ánh xạ cơ bản** của **Spring Data MongoDB**, ta cần hiểu cách một đối tượng Java được biến thành document BSON trong MongoDB, rồi được khôi phục lại thành đối tượng Java khi đọc. Đây là nền tảng để thao tác dữ liệu qua `MongoTemplate` và `MongoRepository` mà vẫn giữ được mô hình miền rõ ràng.

Ví dụ ứng dụng quản lý khách hàng có lớp Java chứa `displayName`, `address` và `contacts`. Trong collection, đội phát triển muốn lưu tên khách hàng dưới khóa `display_name`, địa chỉ dưới một document con và danh sách liên hệ dưới một mảng document. Để làm đúng, cần trả lời ba câu hỏi:

1. **Field mapping:** tên property Java và tên trường BSON có tương ứng trực tiếp hay cần chỉ định bằng annotation?
2. **Constructor mapping:** Spring Data tạo lại đối tượng bằng constructor nào, đặc biệt với class bất biến hoặc Java record?
3. **Nested mapping:** object, danh sách và map được lưu như thế nào; khác gì với việc tham chiếu sang collection khác?

Spring Data sử dụng metadata ánh xạ của entity và `MappingMongoConverter` để giải quyết các câu hỏi này. Cơ chế mapping không thay thế việc thiết kế dữ liệu, index, truy vấn hay chính sách nhất quán; nó xác định **hình dạng dữ liệu trao đổi giữa Java và MongoDB**.

> Ví dụ tập trung vào Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x, với MongoDB Java Sync Driver ở tầng kết nối. Hãy kiểm tra API và cấu hình tương ứng nếu dự án dùng phiên bản major khác.

## 2. Các quy ước ánh xạ mặc định

Giả sử ta có một entity đơn giản:

~~~java
package com.example.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class SimpleCustomer {
    @Id
    private String id;
    private String displayName;
    private int loyaltyPoints;

    public SimpleCustomer() {}

    // Getter/setter hoặc cách truy cập property phù hợp được định nghĩa thêm.
}
~~~

Khi Spring Data ghi entity này, mặc định:

- `@Document(collection = "customers")` định danh collection để lưu entity. Annotation không tự đồng nghĩa với việc collection và index đã được tạo sẵn.
- Property có `@Id` được ánh xạ thành trường BSON `_id`. Với `String` ID, Spring Data có thể chuyển chuỗi biểu diễn ObjectId hợp lệ thành BSON `ObjectId`; không nên giả định mọi String ID đều lưu đúng kiểu String trong BSON.
- `displayName` và `loyaltyPoints` được lưu bằng tên property tương ứng, trừ khi có annotation hoặc cấu hình mapping thay đổi.
- Kiểu nguyên thủy và các kiểu thông dụng được chuyển đổi sang các kiểu BSON phù hợp; nếu có yêu cầu rõ ràng về kiểu BSON, phải xác định quy tắc chuyển đổi.
- Metadata kiểu `_class` có thể được lưu mặc định để hỗ trợ đọc lại kiểu đối tượng, đặc biệt trong đồ thị có nhiều kiểu. Các ví dụ document bên dưới có thể lược bỏ `_class` để tập trung vào field.

Những quy tắc này được thực thi khi thao tác **qua Spring Data mapping**, chẳng hạn `MongoTemplate.save(entity)` hay `MongoRepository.save(entity)`. Nếu làm việc trực tiếp với `MongoCollection<Document>` của driver, ứng dụng phải dùng đúng tên field BSON và tự xử lý chuyển đổi cần thiết.

### Các annotation cơ bản

| Annotation | Ý nghĩa | Lưu ý thực tế |
|---|---|---|
| `@Document(collection = "...")` | Khai báo entity gắn với collection | Có thể không cần cho object được nhúng; không tự tạo index |
| `@Id` | Đánh dấu property định danh, mapping đến `_id` | Với String ID cần chú ý việc chuyển sang BSON ObjectId |
| `@MongoId` | Điều khiển mapping ID theo kiểu BSON mong muốn | Dùng khi cần kiểm soát rõ kiểu `_id` thay cho hành vi chuyển đổi của `@Id` |
| `@Field(name = "...")` | Đặt tên field BSON khác tên property Java | Query dùng property Java qua mapping Spring Data có thể được chuyển sang tên lưu thực tế |
| `@Field(targetType = ...)` | Chỉ định kiểu BSON đích cho một property | Hữu ích cho kiểu như `BigDecimal` muốn lưu dạng Decimal128 |
| `@Transient` | Không lưu property vào document | Không dùng làm tham số bắt buộc của persistence constructor vì không có dữ liệu để khôi phục |
| `@PersistenceCreator` | Chỉ rõ constructor/factory dùng khi khôi phục entity | Hữu ích khi class có nhiều constructor; tên tham số phải được xác định đúng |

Trong Java, các annotation thường được đặt trên field hoặc thành phần record theo khả năng hỗ trợ của framework và phiên bản đang dùng. Với một entity, nên chọn cách khai báo nhất quán để người đọc hiểu property nào là nguồn ánh xạ.

## 3. Đổi tên field bằng @Field

Giả sử mô hình Java đặt tên theo camelCase nhưng collection được thống nhất đặt tên trường theo snake_case:

~~~java
package com.example.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "profiles")
public record Profile(
        @Id String id,
        @Field(name = "display_name") String displayName,
        @Field(name = "phone_number") String phoneNumber) {
}
~~~

Với `Profile("p-101", "Lan", "0900000000")`, dữ liệu BSON có thể có dạng (lược bỏ metadata `_class`):

~~~json
{
  "_id": "p-101",
  "display_name": "Lan",
  "phone_number": "0900000000"
}
~~~

Quan trọng:

- Khi viết mã Java và làm việc với entity, property vẫn là `displayName` và `phoneNumber`.
- Trong lệnh truy vấn MongoDB trực tiếp, tên field thực tế là `display_name` và `phone_number`.
- Không đổi tên property Java chỉ để làm khớp tên BSON nếu `@Field` đã diễn đạt quy ước lưu trữ.
- Đổi annotation từ `@Field("display_name")` sang `@Field("name")` **không tự đổi tên dữ liệu cũ**. Đây là thay đổi schema lưu trữ; cần kế hoạch migration/backfill và đánh giá code đang đọc field cũ.

Ví dụ truy vấn qua `MongoTemplate`, nơi Spring Data biết entity đích:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Profile findByDisplayName(MongoTemplate template, String displayName) {
    Query query = Query.query(Criteria.where("displayName").is(displayName));
    return template.findOne(query, Profile.class);
}
~~~

Với `Profile.class`, Spring Data ánh xạ tên property `displayName` sang trường BSON `display_name`. Đây là lý do nên ưu tiên đường truy cập entity-aware khi xây dựng truy vấn bằng `MongoTemplate`.

Ngược lại, lệnh MongoDB shell dùng tên BSON:

~~~javascript
db.profiles.find({ display_name: "Lan" });
~~~

Nếu dùng các API raw BSON hoặc aggregation stage cung cấp trực tiếp document không được framework mapping, phải kiểm tra cách Spring Data xử lý từng API; đừng mặc định tất cả chuỗi tên field đều được đổi tự động.

## 4. Ánh xạ dữ liệu lồng nhau: document, list và map

MongoDB lưu dữ liệu theo cấu trúc document, cho phép một field chứa object, mảng object hoặc map. Spring Data MongoDB thường ánh xạ trực tiếp các object value-type lồng nhau khi chúng là property của entity.

Ta xây dựng ví dụ đầy đủ gồm ba record Java trong package `com.example.mongo`.

**Address.java**

~~~java
package com.example.mongo;

import org.springframework.data.mongodb.core.mapping.Field;

public record Address(
        String street,
        String city,
        @Field(name = "postal_code") String postalCode) {
}
~~~

**ContactPoint.java**

~~~java
package com.example.mongo;

public record ContactPoint(
        String kind,
        String value) {
}
~~~

**Customer.java**

~~~java
package com.example.mongo;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "customers")
public record Customer(
        @Id String id,
        @Field(name = "display_name") String displayName,
        Address address,
        List<ContactPoint> contacts,
        Map<String, String> attributes,
        Instant createdAt) {
}
~~~

Một đối tượng ví dụ:

~~~java
Customer customer = new Customer(
        "c-101",
        "Lan",
        new Address("12 Đường Ví Dụ", "Hà Nội", "100000"),
        List.of(
                new ContactPoint("email", "lan@example.test"),
                new ContactPoint("phone", "0900000000")),
        Map.of("tier", "gold", "preferredLanguage", "vi"),
        Instant.parse("2026-11-20T08:00:00Z"));

mongoTemplate.save(customer);
~~~

Đoạn trên nằm trong lớp service có `MongoTemplate mongoTemplate` được inject; các record đã khai báo trong cùng package. Document lưu trữ có hình dạng gần như sau (thời gian biểu diễn bằng MongoDB Extended JSON; lược bỏ `_class`):

~~~json
{
  "_id": "c-101",
  "display_name": "Lan",
  "address": {
    "street": "12 Đường Ví Dụ",
    "city": "Hà Nội",
    "postal_code": "100000"
  },
  "contacts": [
    { "kind": "email", "value": "lan@example.test" },
    { "kind": "phone", "value": "0900000000" }
  ],
  "attributes": {
    "tier": "gold",
    "preferredLanguage": "vi"
  },
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

Vì `Address` và `ContactPoint` là **đối tượng lồng bên trong document khách hàng**, chúng không cần `@Document` riêng. Khi lưu `Customer`, Spring Data có thể tuần tự hóa cả đồ thị object này; khi đọc, nó khôi phục record lồng nhau qua constructor.

### 4.1. Nested object và đường dẫn field

Đường dẫn MongoDB `address.city` truy cập vào trường `city` của document con `address`; `address.postal_code` truy cập trường đã đổi tên bằng `@Field`.

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Customer> findByCity(MongoTemplate mongo, String city) {
    Query query = Query.query(Criteria.where("address.city").is(city));
    return mongo.find(query, Customer.class);
}

public List<Customer> findByPostalCode(MongoTemplate mongo, String postalCode) {
    Query query = Query.query(
            Criteria.where("address.postalCode").is(postalCode));
    return mongo.find(query, Customer.class);
}
~~~

Đường dẫn `address.postalCode` là **đường dẫn property Java**. Khi dùng thao tác typed `Customer.class`, Spring Data áp dụng mapping nested property để tạo truy vấn trên `address.postal_code`. Nếu truy vấn bằng raw `Document` qua driver, phải dùng `address.postal_code` trực tiếp.

### 4.2. List và array

`List<ContactPoint>` được lưu thành mảng BSON. Có thể tìm khách hàng có ít nhất một phần tử thỏa điều kiện:

~~~java
Query query = Query.query(
        Criteria.where("contacts")
                .elemMatch(Criteria.where("kind").is("email")));

List<Customer> customers = mongoTemplate.find(query, Customer.class);
~~~

Đối với nhiều điều kiện phải cùng khớp **một phần tử mảng**, dùng `$elemMatch` thay vì kết hợp tùy tiện nhiều đường dẫn; nếu không, các điều kiện có thể khớp với những phần tử khác nhau trong cùng một mảng.

Với mảng ngày càng dài hoặc có vòng đời độc lập, cân nhắc tách sang collection và lưu tham chiếu. Việc nhúng object giúp đọc cùng document, nhưng MongoDB có giới hạn kích thước BSON **16 MiB** cho một document; mảng tăng không giới hạn là tín hiệu cần xem lại thiết kế.

### 4.3. Map

`Map<String, String> attributes` được lưu như document với các khóa động, ví dụ `"tier"` và `"preferredLanguage"`. Mô hình này phù hợp tập thuộc tính có tên linh hoạt và phạm vi nhỏ.

Không sử dụng khóa map tùy ý từ dữ liệu người dùng làm đường dẫn cập nhật mà không kiểm tra: các ký tự đặc biệt như dấu chấm (`.`), ký hiệu `$` và quy tắc tên field có thể ảnh hưởng tới khả năng truy vấn, cập nhật, index hoặc import/export tùy phiên bản MongoDB và cách mapping. Với trường cần truy vấn thường xuyên, nên cân nhắc mô hình property cố định hoặc cấu trúc key/value rõ ràng.

### 4.4. Nhúng hay tham chiếu?

Một property kiểu `Address` ở ví dụ trên được lưu **nhúng**. Nó không tự biến thành tham chiếu chỉ vì type đó cũng có thể xuất hiện trong entity khác.

- **Nhúng:** object nằm trong document cha; phù hợp dữ liệu nhỏ, thường đọc cùng nhau và cùng vòng đời.
- **Tham chiếu ID:** document cha lưu khóa tới document trong collection khác; ứng dụng cần truy vấn riêng hoặc tổng hợp để lấy phần liên quan.
- **`@DBRef` hoặc `@DocumentReference`:** là cơ chế tham chiếu của Spring Data, có cách lưu và phân giải riêng; phải chủ động chọn và hiểu hành vi tải dữ liệu.

Hãy chọn mô hình theo truy vấn, kích thước document, tần suất cập nhật và yêu cầu nhất quán. Annotation mapping giúp chuyển đổi cấu trúc đã chọn, không tự quyết định cách thiết kế quan hệ dữ liệu.

## 5. Constructor mapping: Spring Data tạo object khi đọc như thế nào?

Khi document được đọc, `MappingMongoConverter` cần tạo đối tượng Java phù hợp rồi cung cấp giá trị cho các property. Với mutable class có constructor không tham số và setter/field access, quá trình này tương đối đơn giản. Với class bất biến hoặc record, **constructor trở thành điểm khôi phục trạng thái quan trọng**.

### 5.1. Java record: canonical constructor

Ví dụ `Customer` là record. Khi đọc, Spring Data có thể sử dụng **canonical constructor** của record với các tham số `id`, `displayName`, `address`, `contacts`, `attributes` và `createdAt`. Giá trị của `display_name` trong BSON được đưa vào tham số **`displayName`**, bởi metadata `@Field` liên kết tên lưu trữ với tên property Java.

Ưu điểm:

- Không cần setter cho entity được biểu diễn bằng record.
- Các thành phần record mô tả rõ trạng thái của document.
- Có thể đặt các kiểu lồng nhau bất biến trong record và khôi phục toàn bộ đồ thị.

Giới hạn:

- Nếu schema cũ thiếu field bắt buộc, constructor có thể nhận `null` hoặc không tạo được object khi có ràng buộc không cho phép null.
- Khi thay đổi kiểu dữ liệu hoặc đổi tên field mà chưa migration, việc khôi phục có thể thất bại.
- Record bất biến phải được thiết kế cẩn thận với ID do database sinh, các field được framework cập nhật và vòng đời save; cần kiểm tra cơ chế tạo bản sao/khởi tạo ID được hỗ trợ.

Để ví dụ đơn giản, ta **cung cấp ID cụ thể** (`c-101`), tránh phụ thuộc vào cách framework gắn ID tự sinh cho kiểu bất biến.

### 5.2. Class có nhiều constructor: @PersistenceCreator

Khi một class có nhiều constructor, có thể chỉ định constructor cần dùng lúc đọc bằng `@PersistenceCreator`:

~~~java
package com.example.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "catalog_items")
public final class CatalogItem {
    @Id
    private final String id;
    @Field(name = "display_title")
    private final String title;
    private final String category;

    @PersistenceCreator
    public CatalogItem(String id, String title, String category) {
        this.id = id;
        this.title = title;
        this.category = category;
    }

    // Constructor tiện ích cho trường hợp biết rõ ID và tên.
    public CatalogItem(String id, String title) {
        this(id, title, "general");
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getCategory() { return category; }
}
~~~

Giả sử document:

~~~json
{
  "_id": "item-101",
  "display_title": "Sổ tay",
  "category": "stationery"
}
~~~

Spring Data dùng constructor được đánh dấu, truyền giá trị tương ứng vào tham số `id`, `title`, `category`. **Tên tham số constructor khớp với tên property Java**, tức `title` chứ không phải `display_title`.

Lưu ý về constructor:

1. Khi chỉ có một constructor phù hợp, framework thường có thể tự xác định constructor cần dùng. Với nhiều constructor, `@PersistenceCreator` giúp tránh mơ hồ.
2. Spring Data cần biết tên tham số constructor, chẳng hạn qua metadata tên tham số khi biên dịch với cờ `-parameters`, hoặc cơ chế annotation/metadata được hỗ trợ. Nếu thiếu tên tham số ở class thông thường, mapping có thể thất bại.
3. Tham số constructor phải tương ứng với property có thể được materialize từ document. Không dùng property `@Transient` như giá trị bắt buộc từ persistence constructor.
4. Constructor có validation hoặc side effect phải cân nhắc dữ liệu lịch sử. Một rule mới nghiêm ngặt có thể khiến các document cũ không còn đọc được.

**Không nên khai báo một constructor chỉ để làm vừa cơ chế mapping rồi đặt logic nghiệp vụ nặng vào đó**. Constructor nên xây dựng object hợp lệ từ trạng thái dữ liệu; các side effect như gọi service, truy vấn mạng hoặc gửi sự kiện không thuộc trách nhiệm của nó.

### 5.3. Thiếu field, null và giá trị mặc định

Khi MongoDB có các document được tạo bởi nhiều phiên bản ứng dụng, một property có thể:

- **Không tồn tại** trong document cũ.
- **Tồn tại với BSON null**.
- **Tồn tại với kiểu dữ liệu khác** do schema đổi.

Các trường hợp này có thể ảnh hưởng khác nhau tới constructor, tùy kiểu property, converter và xử lý mặc định. Ví dụ một `Integer` tùy chọn có thể nhận `null`, còn `int` nguyên thủy không thể biểu diễn null. Constructor kiểm tra `Objects.requireNonNull` có thể ném lỗi khi đọc document cũ thiếu trường.

Chính sách an toàn là phân biệt:

- **Field bắt buộc mới:** viết migration/backfill trước hoặc đồng thời khi triển khai logic đọc bắt buộc.
- **Field tùy chọn:** dùng kiểu nullable và xử lý default tại lớp miền/adapter một cách tường minh.
- **Đổi tên field:** xác định giai đoạn tương thích đọc cả hai tên, di chuyển dữ liệu và thu hồi tên cũ có kế hoạch.
- **Đổi kiểu BSON:** kiểm tra dữ liệu thực tế và converter; không giả định framework có thể suy diễn mọi phép chuyển đổi.

Không nên dựa vào default của field Java như một cơ chế migration tự động, đặc biệt với entity bất biến được tạo bằng constructor.

## 6. Kiểm soát kiểu BSON và chuyển đổi

Tên field chỉ là một nửa của bài toán mapping. Kiểu dữ liệu thực tế trong MongoDB ảnh hưởng đến phép so sánh, index, aggregation và khả năng tương thích.

### 6.1. String ID và ObjectId

`@Id String id` có hành vi chuyển đổi đặc biệt với chuỗi có dạng ObjectId hợp lệ. Nếu ứng dụng thực sự cần `_id` là **BSON String** bất kể nội dung, có thể dùng `@MongoId(FieldType.STRING)` theo API hỗ trợ của Spring Data:

~~~java
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

public record ExternalKey(
        @MongoId(FieldType.STRING) String id,
        String label) {
}
~~~

Ví dụ record chỉ minh họa mapping ID; nếu cần dùng như aggregate root, hãy bổ sung `@Document` và collection tương ứng. Khi làm việc với lệnh driver BSON thô, luôn đối chiếu kiểu `_id` thực tế: truy vấn `eq("_id", "507f...")` với BSON String khác `eq("_id", new ObjectId("507f..."))`.

### 6.2. BigDecimal và Decimal128

Giá tiền đòi hỏi độ chính xác thập phân. Có thể chỉ định lưu `BigDecimal` ở định dạng BSON Decimal128:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public record Price(
        @Field(targetType = FieldType.DECIMAL128) BigDecimal amount,
        String currency) {
}
~~~

Ví dụ này biểu diễn **một đối tượng giá lồng trong document cha**. Nếu có quy tắc làm tròn, scale, tiền tệ hay giới hạn độ chính xác, cần xử lý rõ ở tầng nghiệp vụ. BSON Decimal128 có giới hạn biểu diễn riêng; không phải mọi `BigDecimal` tùy ý đều biểu diễn được nguyên vẹn.

### 6.3. Instant, enum và converter

- `Instant` thường được lưu qua BSON Date/UTC theo conversion được hỗ trợ. BSON Date có độ chính xác đến **mili giây**, vì vậy không nên trông đợi round-trip nanosecond nguyên vẹn.
- Enum thường được lưu bằng tên chuỗi theo mapping mặc định; đổi tên enum có thể làm dữ liệu cũ không đọc được nếu không có chính sách tương thích.
- Kiểu miền đặc thù có thể cần `@ReadingConverter`, `@WritingConverter` và đăng ký `MongoCustomConversions`. Converter phải thống nhất cả chiều ghi và đọc, đặc biệt khi có query và aggregation.

Những quyết định kiểu dữ liệu cần được xác minh trên **document BSON thực**, vì so sánh số và ngày trong MongoDB phụ thuộc kiểu được lưu.

## 7. Truy vấn và cập nhật nested field bằng MongoTemplate

Với entity `Customer` ở mục 4, cả truy vấn và cập nhật có thể dùng đường dẫn property Java:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class CustomerDataAccess {
    private final MongoTemplate mongo;

    public CustomerDataAccess(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<Customer> byPostalCode(String postalCode) {
        Query query = Query.query(
                Criteria.where("address.postalCode").is(postalCode));
        return mongo.find(query, Customer.class);
    }

    public boolean changeCity(String customerId, String newCity) {
        Query byId = Query.query(Criteria.where("id").is(customerId));
        Update update = new Update().set("address.city", newCity);
        return mongo.updateFirst(byId, update, Customer.class)
                .getModifiedCount() == 1;
    }
}
~~~

Điểm cần chú ý:

- `Criteria.where("id")` được mapping thành `_id` của entity đích.
- `address.postalCode` là tên property Java, được Spring Data chuyển thành field `address.postal_code` khi tạo truy vấn typed.
- `updateFirst` cập nhật **một document phù hợp** mà không cần tải lại toàn bộ object. Mã chỉ thay trường `address.city`.
- `getModifiedCount() == 0` có thể do không tìm thấy document, hoặc document đã có giá trị mong muốn; không nên tự kết luận nguyên nhân là “không tồn tại” chỉ từ con số đó.
- Với các cập nhật nhiều phần tử trong mảng, cần hiểu `$`, `$[]`, `$[identifier]` và array filters; không sử dụng cú pháp nested path đơn giản để thay thế nghiệp vụ cập nhật mảng phức tạp.

Nếu ứng dụng dùng **immutable record**, thao tác `MongoTemplate.updateFirst` vẫn thay đổi document trong database, nhưng **không sửa object record đã được tải sẵn trong bộ nhớ**. Muốn có snapshot mới, phải đọc lại hoặc làm việc với kết quả từ một thao tác phù hợp. Đây không phải một cơ chế identity map như một số ORM quan hệ.

## 8. Các lỗi mapping thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh hoặc sửa |
|---|---|---|
Field Java có giá trị nhưng BSON lưu dưới tên khác | `@Field`, naming strategy hoặc converter | Đọc raw BSON và đối chiếu metadata mapping |
Truy vấn raw BSON không tìm thấy dữ liệu | Dùng tên property Java thay cho tên BSON | Kiểm tra tên field vật lý, ví dụ `display_name` |
Đọc immutable class bị lỗi constructor | Nhiều constructor, thiếu `@PersistenceCreator` hoặc thiếu metadata tên tham số | Kiểm tra annotation, cờ biên dịch `-parameters` và log chuyển đổi |
Record cũ không đọc được sau khi thêm field bắt buộc | Field thiếu/null không qua được validation của constructor | Thiết kế compatibility hoặc migration/backfill |
`_id` tìm không khớp | Một bên dùng BSON String, bên kia dùng ObjectId | Đọc type thực tế, quyết định `@Id`/`@MongoId` nhất quán |
Dữ liệu lồng nhau bị đọc sai | Đường dẫn field hoặc kiểu class con đổi | Kiểm tra document lưu và mapping của nested property |
Lưu được nhưng chậm hoặc document rất lớn | Mảng/object lồng quá nhiều hoặc thiết kế index chưa phù hợp | Đo kích thước document, giải thích truy vấn và cân nhắc tách collection |
Giá trị tiền sai kiểu khi query/aggregation | `BigDecimal` và Decimal128/String không nhất quán | Chỉ định `targetType`, migration và test dữ liệu BSON |
Entity đổi nhưng document không đổi | Chỉ thay object Java trong bộ nhớ, chưa ghi | Gọi thao tác save/update phù hợp và kiểm tra kết quả |
Ghi bằng driver raw rồi không thấy callback/converter | Đường driver trực tiếp bỏ qua Spring Data mapping | Giữ đường truy cập thống nhất hoặc chuyển đổi rõ trong adapter |

## 9. Kiểm thử mapping bằng MongoDB thật

Các unit test chỉ kiểm tra constructor Java sẽ **không chứng minh** Spring Data ghi đúng tên field và BSON type. Nên có integration test sử dụng MongoDB thực, ví dụ Testcontainers hoặc môi trường MongoDB dành riêng cho test.

Với Spring Boot 3.x, `@DataMongoTest` tập trung vào hạ tầng Spring Data MongoDB. Đoạn test dưới đây dùng `MongoTemplate` và đọc lại **raw BSON** để thấy sự khác biệt giữa tên property và tên field lưu trữ.

~~~java
package com.example.mongo;

import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class CustomerMappingTest {
    @Autowired
    MongoTemplate mongo;

    @Test
    void mapsFieldNamesAndNestedRecords() {
        Customer expected = new Customer(
                "c-101",
                "Lan",
                new Address("12 Đường Ví Dụ", "Hà Nội", "100000"),
                List.of(new ContactPoint("email", "lan@example.test")),
                Map.of("tier", "gold"),
                Instant.parse("2026-11-20T08:00:00Z"));

        mongo.save(expected);

        Document bson = mongo.getCollection("customers")
                .find(eq("_id", "c-101"))
                .first();

        assertThat(bson).isNotNull();
        assertThat(bson.getString("display_name")).isEqualTo("Lan");
        assertThat(bson.get("displayName")).isNull();
        assertThat(bson.get("address", Document.class)
                .getString("postal_code")).isEqualTo("100000");

        Customer restored = mongo.findById("c-101", Customer.class);
        assertThat(restored).isEqualTo(expected);
    }
}
~~~

Test này cần database MongoDB sẵn sàng tại URI được cấu hình. `@DataMongoTest` **không tự chạy server MongoDB**. Testcontainers có thể cung cấp MongoDB tạm thời và URI động; cần cấu hình đúng với phiên bản Boot/Testcontainers đang sử dụng. Để tránh trùng ID giữa các test, nên dùng collection/database cô lập hoặc dọn dữ liệu test một cách có kiểm soát.

Các test bổ sung nên bao gồm:

1. **Tên field:** lưu, đọc, truy vấn và cập nhật `displayName`/`display_name` cùng `address.postalCode`/`postal_code`.
2. **Constructor:** khôi phục class có nhiều constructor và `@PersistenceCreator` từ document thực.
3. **Nested array:** kiểm tra `$elemMatch` khi hai phần tử mảng có thuộc tính khác nhau.
4. **Tương thích ngược:** đọc document thiếu trường, trường null hoặc kiểu BSON cũ; xác định lỗi dự kiến.
5. **Kiểu BSON:** xác minh `_id` kiểu String/ObjectId đúng thiết kế, Decimal128 và độ chính xác của timestamp.
6. **Thao tác cập nhật:** bảo đảm chỉ field mong muốn thay đổi và object đã đọc trước đó không tự cập nhật trong bộ nhớ.

## 10. Bài tập thực hành

**Bài 1 — Đổi tên trường.** Tạo `@Document(collection = "products")` với property `productName` và `listedPrice`, lưu trong BSON dưới `product_name` và `listed_price`. Viết một truy vấn `MongoTemplate` dùng tên property Java, sau đó kiểm tra raw BSON để chứng minh tên lưu vật lý.

**Bài 2 — Constructor bất biến.** Tạo class `PurchaseOrder` có hai constructor; đánh dấu một constructor bằng `@PersistenceCreator` và dùng ít nhất một `@Field(name = "...")`. Ghi document rồi đọc lại để xác nhận Spring Data khôi phục đúng object. Thử bỏ metadata tên tham số trong môi trường thử nghiệm để quan sát lỗi và giải thích nguyên nhân.

**Bài 3 — Document lồng.** Thiết kế `Delivery` chứa `recipient`, `address` và mảng `packages`. Truy vấn theo `address.postalCode`, tìm các document có package `weightGrams >= 1000` bằng `$elemMatch`, rồi cập nhật thành phố mà không thay toàn bộ document.

**Bài 4 — Dữ liệu lịch sử.** Thêm property mới vào record khi collection đã có dữ liệu cũ. Đề xuất cơ chế default/migration sao cho cả document cũ và mới đều đọc được, đồng thời giữ ràng buộc nghiệp vụ ở đúng lớp.

**Bài 5 — Kiểu dữ liệu.** Lưu hai document có `_id` dạng chuỗi 24 ký tự hexa, lần lượt dùng `@Id` và `@MongoId(FieldType.STRING)`. Kiểm tra raw BSON và giải thích tại sao truy vấn trực tiếp với `String` và `ObjectId` có thể cho kết quả khác nhau.

## 11. Ghi nhớ

Trong **Spring Data MongoDB**, mapping là hợp đồng giữa **property Java** và **field BSON**. `@Document` xác định entity/collection; `@Id` hoặc `@MongoId` xác định cách lưu khóa; `@Field` đổi tên hoặc chỉ định kiểu BSON; `@PersistenceCreator` và canonical constructor của record hỗ trợ khôi phục object bất biến.

Các object lồng nhau, list và map có thể được lưu trong cùng document khi mô hình dữ liệu phù hợp, còn tham chiếu cần được thiết kế riêng. Khi xây dựng query bằng `MongoTemplate` với entity type, ưu tiên dùng đường dẫn property Java để framework áp dụng mapping. Với lệnh MongoDB raw, sử dụng tên field BSON thực tế.

Hãy **đọc lại raw BSON trong integration test**, kiểm tra constructor với dữ liệu thiếu/null, chú ý kiểu `_id`, kiểu số và ngày, đồng thời có kế hoạch migration khi đổi tên hoặc kiểu field. Các bước đó giúp truy vấn, aggregation, index và thao tác repository ở những phần tiếp theo hoạt động trên dữ liệu có cấu trúc nhất quán.
