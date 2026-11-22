# Query, update và giới hạn ánh xạ trên thuộc tính unwrapped

Trong MongoDB, một object Java thường được lưu thành **document lồng nhau**. Tuy nhiên, Spring Data MongoDB hỗ trợ `@Unwrapped` để trải phẳng (*flatten*) các field của một value object vào **document cha**. Điều này ảnh hưởng trực tiếp tới đường dẫn truy vấn, toán tử cập nhật, tên field dùng trong index/aggregation và cách đọc lại dữ liệu thiếu trường.

Ví dụ, Java có `customer.billingAddress.city` nhưng BSON có thể lưu `billing_city` ngay ở cấp root, hoàn toàn **không tồn tại** document `billingAddress`. Vì vậy, câu lệnh `mongosh` và câu lệnh `MongoTemplate` mang metadata của entity có thể sử dụng **hai cách viết đường dẫn khác nhau** mà cùng truy cập một giá trị.

Bài thuộc chương **Đối tượng và nhúng**, tập trung vào cách truy vấn và cập nhật dữ liệu đã được `@Unwrapped`, những giới hạn quan trọng khi ánh xạ và cách kiểm chứng trên MongoDB. Kiến thức này dùng trực tiếp khi xây dựng ứng dụng Spring Data MongoDB bằng `MongoRepository`, `MongoTemplate`, aggregation và index.

Sau bài học, bạn có thể:

- Giải thích `@Unwrapped`, `prefix` và `onEmpty`; phân biệt với nhúng document thông thường.
- Viết truy vấn theo **đường dẫn thuộc tính Java** ở repository/`MongoTemplate` và theo **tên BSON trải phẳng** ở `mongosh`.
- Cập nhật một hoặc nhiều field đã trải phẳng, xử lý xóa field và xung đột ghi.
- Nhận diện các trường hợp không nên query/update **toàn bộ** unwrapped object.
- Thiết kế prefix, chỉ mục, projection, migration và kiểm thử để tránh xung đột tên trường hoặc sai kết quả mapping.

## 1. Nhúng bình thường và unwrapped khác nhau thế nào?

Giả sử một hồ sơ khách hàng có địa chỉ thanh toán:

```java
class Address {
    private String street;
    private String city;
    private String postalCode;
}

class CustomerProfile {
    private Address billingAddress;
}
```

Nếu `billingAddress` được ánh xạ **nhúng thông thường**, BSON có dạng:

```javascript
{
  customerNo: "CUS-001",
  billingAddress: {
    street: "12 Pho Mau",
    city: "Ha Noi",
    postalCode: "100000"
  }
}
```

Truy vấn raw MongoDB dùng dot notation:

```javascript
db.customer_profiles.find({ "billingAddress.city": "Ha Noi" });
```

Nếu gắn `@Unwrapped(prefix = "billing_")` trên thuộc tính `billingAddress`, BSON được trải phẳng:

```javascript
{
  customerNo: "CUS-001",
  billing_street: "12 Pho Mau",
  billing_city: "Ha Noi",
  billing_postal_code: "100000"
}
```

Với dữ liệu đã trải phẳng, truy vấn raw MongoDB phải dùng:

```javascript
db.customer_profiles.find({ billing_city: "Ha Noi" });
```

**Hệ quả then chốt:** `billingAddress.city` là **đường dẫn thuộc tính Java**; `billing_city` là **tên field BSON thực tế**. MongoDB server không hiểu annotation `@Unwrapped` của Spring Data. Chỉ các thao tác đi qua bộ ánh xạ Spring Data MongoDB và có đủ thông tin loại entity mới có thể chuyển đổi đường dẫn.

| Góc nhìn | Nhúng bình thường | `@Unwrapped(prefix = "billing_")` |
| --- | --- | --- |
| Java | `billingAddress.city` | `billingAddress.city` |
| BSON | `billingAddress: { city: ... }` | `billing_city: ...` |
| `mongosh` filter | `"billingAddress.city"` | `"billing_city"` |
| `MongoTemplate` với domain class | `"billingAddress.city"` | Thông thường vẫn viết `"billingAddress.city"` để mapper đổi sang `billing_city` |
| Đổi cả object bằng một field BSON | Có field `billingAddress` | Không có field `billingAddress` để thay trực tiếp |

## 2. Khai báo `@Unwrapped` trong Spring Data MongoDB

### 2.1. Một ví dụ hoàn chỉnh với prefix và `@Field`

```java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.Unwrapped;

@Document(collection = "customer_profiles")
public class CustomerProfile {
    @Id
    private ObjectId id;
    private String customerNo;
    private String displayName;

    @Unwrapped(
        prefix = "billing_",
        onEmpty = Unwrapped.OnEmpty.USE_NULL
    )
    private Address billingAddress;

    @Version
    private Long version;

    protected CustomerProfile() { }

    public CustomerProfile(
            String customerNo,
            String displayName,
            Address billingAddress) {
        this.customerNo = customerNo;
        this.displayName = displayName;
        this.billingAddress = billingAddress;
    }

    public ObjectId getId() { return id; }
    public String getCustomerNo() { return customerNo; }
    public String getDisplayName() { return displayName; }
    public Address getBillingAddress() { return billingAddress; }

    public static class Address {
        private String street;
        private String city;

        @Field("postal_code")
        private String postalCode;

        protected Address() { }

        public Address(String street, String city, String postalCode) {
            this.street = street;
            this.city = city;
            this.postalCode = postalCode;
        }

        public String getStreet() { return street; }
        public String getCity() { return city; }
        public String getPostalCode() { return postalCode; }
    }
}
```

Spring Data MongoDB ánh xạ ba thuộc tính `street`, `city` và `postalCode` của `Address` sang document cha. Prefix `billing_` được áp dụng lên **tên field lưu trữ**; vì `postalCode` có `@Field("postal_code")` nên field cuối cùng là `billing_postal_code`.

Ví dụ document lưu trữ, lược bỏ `_class` để dễ đọc:

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  customerNo: "CUS-001",
  displayName: "Khach hang vi du",
  billing_street: "12 Pho Mau",
  billing_city: "Ha Noi",
  billing_postal_code: "100000",
  version: NumberLong(0)
}
```

`_id` do chương trình/driver tạo, và loại BSON thực tế của `version` hoặc `_class` phụ thuộc cấu hình. Đoạn BSON trên là mẫu minh họa, **không phải kết quả cố định** của mọi phiên bản Spring Data MongoDB.

### 2.2. `@Unwrapped` không phải một entity độc lập

`Address` là **value object** thuộc `CustomerProfile`. Nó không có `@Id` riêng, không có repository riêng và không được ghi như một document độc lập trong collection `addresses`. Những thay đổi của địa chỉ phải được quản lý thông qua aggregate root `CustomerProfile`.

Không dùng `@Unwrapped` để mô phỏng liên kết giữa hai aggregate có vòng đời độc lập. Nếu `Address` cần danh tính riêng, lịch sử thay đổi độc lập hoặc được nhiều khách hàng chia sẻ như một đối tượng sống, hãy cân nhắc reference hoặc collection riêng.

### 2.3. Khi không khai báo prefix

```java
@Unwrapped
private Address billingAddress;
```

Với prefix mặc định rỗng, các field có thể xuất hiện ngay dưới tên `street`, `city`, `postal_code` ở document cha. Điều này ngắn gọn nhưng dễ xung đột nếu root cũng có `city` hoặc có nhiều địa chỉ.

Đặt prefix có ý nghĩa như `billing_`, `shipping_` hoặc `contact_` ngay từ đầu giúp schema dễ đọc và hạn chế va chạm. Thay prefix khi đã có dữ liệu là **thay đổi schema BSON**, cần kế hoạch migration.

## 3. Query qua `MongoRepository` và derived query

Khai báo repository với ID đúng kiểu Java:

```java
import java.util.List;
import java.util.Optional;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerProfileRepository
        extends MongoRepository<CustomerProfile, ObjectId> {

    Optional<CustomerProfile> findByCustomerNo(String customerNo);

    List<CustomerProfile> findByBillingAddressCity(String city);

    List<CustomerProfile>
        findByBillingAddressCityAndBillingAddressPostalCode(
            String city, String postalCode);
}
```

Spring Data phân tích method name theo property path của class Java, sau đó áp dụng metadata `@Unwrapped` khi tạo truy vấn MongoDB. `findByBillingAddressCity("Ha Noi")` nhằm tới field BSON `billing_city`, còn method thứ hai kết hợp `billing_city` và `billing_postal_code`.

**Không đặt tên method theo BSON field** như `findByBilling_city(...)` nếu class Java không có thuộc tính tương ứng. Derived query xây dựng từ tên thuộc tính Java; prefix là chi tiết ánh xạ của MongoDB. Khi tên thuộc tính dài hoặc có thể gây mơ hồ trong bộ phân tích method name, xem xét dùng `@Query` rõ ràng.

### 3.1. `@Query` và tên field lưu trữ

```java
import org.springframework.data.mongodb.repository.Query;

@Query("{ 'billing_city': ?0 }")
List<CustomerProfile> findByBillingCityRaw(String city);
```

Đây là ví dụ **method bổ sung trong interface repository** ở trên. Query JSON dùng trực tiếp tên field BSON `billing_city`, nên biểu đạt chính xác schema lưu trữ. Cú pháp/khả năng ánh xạ của query string còn phụ thuộc Spring Data, vì vậy khi dùng property path trong JSON query hoặc đổi prefix, cần có kiểm thử tích hợp xác nhận câu truy vấn thực sự được thực thi.

### 3.2. Không so khớp cả unwrapped object như một nested document

Câu truy vấn này **không phản ánh BSON thực tế**:

```javascript
// Sai với schema đang dùng @Unwrapped(prefix = "billing_").
db.customer_profiles.find({
  billingAddress: {
    city: "Ha Noi",
    postal_code: "100000"
  }
});
```

Vì không có field `billingAddress` trong document lưu trữ, query trên không tìm được document như mong muốn. Thay bằng lọc theo các field đã trải phẳng:

```javascript
db.customer_profiles.find({
  billing_city: "Ha Noi",
  billing_postal_code: "100000"
});
```

Tương tự, khi dùng API query Spring Data, ưu tiên **so khớp từng thuộc tính của value object**, thay vì `Criteria.where("billingAddress").is(address)`. Khả năng serialize toàn bộ value object thành một toán hạng query không tương đương với query nested BSON và không nên là cơ sở thiết kế.

## 4. Query qua `MongoTemplate`: phân biệt property path và raw BSON

Với `MongoTemplate`, cần có **entity class** để Spring Data biết metadata `@Unwrapped`:

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<CustomerProfile> findInCity(
        MongoTemplate template, String city) {

    Query query = Query.query(
        Criteria.where("billingAddress.city").is(city)
    );
    return template.find(query, CustomerProfile.class);
}
```

Đường dẫn `billingAddress.city` là đường dẫn **Java domain**; query mapper áp dụng `@Unwrapped(prefix = "billing_")` để tìm `billing_city`. Với nested annotation `@Field("postal_code")`, có thể truy vấn:

```java
Query query = Query.query(
    Criteria.where("billingAddress.postalCode").is("100000")
);
List<CustomerProfile> matches =
    template.find(query, CustomerProfile.class);
```

Trong trường hợp không có domain mapping, ví dụ dùng raw MongoDB Java Driver hoặc `mongosh`, dùng tên field BSON:

```javascript
db.customer_profiles.find({
  billing_postal_code: "100000"
});
```

Nếu truy cập một collection dưới dạng `org.bson.Document`/raw BSON qua driver, annotation trên `CustomerProfile` không được áp dụng cho chuỗi query tự viết. Tránh giả định một query raw sẽ tự chuyển `billingAddress.postalCode` thành `billing_postal_code`.

### 4.1. Lọc nhiều điều kiện và projection

Ví dụ tìm hồ sơ theo mã khách hàng và thành phố:

```java
Query query = Query.query(
    Criteria.where("customerNo").is("CUS-001")
        .and("billingAddress.city").is("Ha Noi")
);
query.fields().include("customerNo");
query.fields().include("displayName");
query.fields().include("billingAddress.city");

List<CustomerProfile> result =
    template.find(query, CustomerProfile.class);
```

**Lưu ý partial projection:** nếu chỉ lấy `billing_city` mà không lấy `billing_street` và `billing_postal_code`, object `Address` được dựng lại có thể **thiếu dữ liệu**. Với `onEmpty`, những trường hoàn toàn vắng mặt còn ảnh hưởng cách tạo `Address` hoặc gán `null`. Không nên lấy entity có projection không đầy đủ rồi `save` lại như thể đó là aggregate đầy đủ; thao tác thay thế document có thể làm mất những field bị bỏ qua khi đọc.

Nếu chỉ cần dữ liệu hiển thị, hãy dùng DTO/projection đọc riêng hoặc chỉ update các field cần sửa bằng câu lệnh có điều kiện, tránh ghi đè toàn document.

### 4.2. Kiểm tra truy vấn với `mongosh`

```javascript
db.customer_profiles.find(
  {
    customerNo: "CUS-001",
    billing_city: "Ha Noi"
  },
  {
    _id: 0,
    customerNo: 1,
    displayName: 1,
    billing_city: 1
  }
);
```

Khi chẩn đoán query sai kết quả, kiểm tra **tên field thật** trong BSON bằng `findOne` và so sánh với metadata entity: prefix, `@Field`, cách đọc/ghi của Spring Data hay driver trực tiếp.

## 5. Update từng field unwrapped bằng `MongoTemplate`

Một thao tác update trên MongoDB cập nhật **field BSON**, không cập nhật một Java object theo đường dẫn vật lý tưởng tượng. Cách an toàn khi dùng `@Unwrapped` là thay đổi **từng thuộc tính**.

### 5.1. Chuyển thành phố và mã bưu chính trong cùng một lệnh

```java
import org.bson.types.ObjectId;
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public UpdateResult changeBillingLocation(
        MongoTemplate template, ObjectId profileId,
        String city, String postalCode) {

    Query query = Query.query(
        Criteria.where("id").is(profileId)
    );
    Update update = new Update()
        .set("billingAddress.city", city)
        .set("billingAddress.postalCode", postalCode);

    return template.updateFirst(
        query, update, CustomerProfile.class
    );
}
```

Với `CustomerProfile.class`, bộ ánh xạ xác định:

| Đường dẫn trong `Update` | Field BSON cần cập nhật |
| --- | --- |
| `billingAddress.city` | `billing_city` |
| `billingAddress.postalCode` | `billing_postal_code` |
| `billingAddress.street` | `billing_street` |

Cùng một `updateFirst` thay đổi các field trên **một document** theo cách nguyên tử. Kiểm tra `getMatchedCount()` và `getModifiedCount()` của `UpdateResult`: matched bằng 0 nghĩa là bộ lọc không tìm thấy document; modified bằng 0 có thể do gán lại giá trị không thay đổi (hoặc chi tiết khác tùy update).

Trong phần lớn ứng dụng, trước khi update còn phải xác nhận người dùng có quyền sửa hồ sơ và giá trị `city`/`postalCode` đã vượt qua validation. `@Unwrapped` chỉ là metadata ánh xạ; nó không tự kiểm tra quy tắc nghiệp vụ.

### 5.2. Câu lệnh `mongosh` tương đương

```javascript
db.customer_profiles.updateOne(
  { customerNo: "CUS-001" },
  {
    $set: {
      billing_city: "Da Nang",
      billing_postal_code: "550000"
    }
  }
);
```

Viết trực tiếp `$set: { "billingAddress.city": "Da Nang" }` trên collection đã trải phẳng có thể tạo **document lồng nhau khác** trong BSON, thay vì thay đổi `billing_city` đang có. Đó là lỗi schema drift đặc biệt nguy hiểm khi có script vận hành bên ngoài Spring Data.

### 5.3. Không `$set` toàn bộ unwrapped object như một field

Đoạn sau không thể được hiểu là "cập nhật tất cả field trải phẳng" theo quy tắc MongoDB:

```javascript
// Không dùng với schema unwrapped: tạo/thay field billingAddress.
db.customer_profiles.updateOne(
  { customerNo: "CUS-001" },
  {
    $set: {
      billingAddress: {
        city: "Da Nang",
        postalCode: "550000"
      }
    }
  }
);
```

Nó nhắm đến một field `billingAddress` mới, trong khi dữ liệu đúng đang nằm ở `billing_city` và `billing_postal_code`. Ở tầng Spring Data, đừng dựa vào `new Update().set("billingAddress", address)` như một API thay thế nguyên khối unwrapped object: tùy khả năng ánh xạ và phiên bản, thao tác này có thể không được hỗ trợ hoặc không cho kết quả giống cập nhật từng field.

Nếu nghiệp vụ cần thay cả địa chỉ, giải pháp là **đặt tất cả field cấu thành vào cùng một update**. Khi cần bỏ một giá trị cũ, bổ sung `unset` cho field tương ứng, tránh để dữ liệu còn sót.

## 6. Xóa field, `null` và `onEmpty`

### 6.1. `USE_NULL` và `USE_EMPTY` khi đọc

`@Unwrapped` có tùy chọn `onEmpty` để quyết định cách Spring Data xử lý một value object khi **không có field có giá trị để dựng object**:

| Cấu hình | Hành vi mong đợi khi toàn bộ field unwrapped trống/không có |
| --- | --- |
| `Unwrapped.OnEmpty.USE_NULL` | Thuộc tính `billingAddress` của Java được đọc thành `null` |
| `Unwrapped.OnEmpty.USE_EMPTY` | Spring Data cố gắng dựng một instance `Address` rỗng theo cơ chế khởi tạo object |

Khi có ít nhất một field hữu ích, `Address` có thể được dựng với những field còn thiếu giữ giá trị `null`/default Java. Quy tắc cụ thể còn chịu ảnh hưởng constructor, conversion và các phiên bản Spring Data; hãy kiểm thử bằng dữ liệu thật, đặc biệt khi khác biệt giữa BSON Null và field thiếu có ý nghĩa.

Ví dụ thay cấu hình:

```java
@Unwrapped(
    prefix = "billing_",
    onEmpty = Unwrapped.OnEmpty.USE_EMPTY
)
private Address billingAddress;
```

**Quan trọng:** `onEmpty` là quy tắc **dựng object khi đọc**, không tự làm MongoDB lưu một document `billingAddress: {}`, cũng không phải validation rule bảo đảm địa chỉ luôn hợp lệ.

### 6.2. `$unset` từng field đã trải phẳng

Để xóa toàn bộ địa chỉ của hồ sơ trong ví dụ:

```javascript
db.customer_profiles.updateOne(
  { customerNo: "CUS-001" },
  {
    $unset: {
      billing_street: "",
      billing_city: "",
      billing_postal_code: ""
    }
  }
);
```

Sau update, ba field BSON trên **không tồn tại**. Với `USE_NULL`, đọc lại qua Spring Data thông thường thu được `billingAddress == null`. Với `USE_EMPTY`, có thể nhận một `Address` trống. Kết quả trực tiếp của `mongosh` không mang metadata này.

Trong `MongoTemplate`:

```java
Update clearAddress = new Update()
    .unset("billingAddress.street")
    .unset("billingAddress.city")
    .unset("billingAddress.postalCode");

template.updateFirst(
    Query.query(Criteria.where("id").is(profileId)),
    clearAddress,
    CustomerProfile.class
);
```

Không xem `$set: { billing_city: null }` là tương đương `$unset: { billing_city: "" }`. MongoDB phân biệt **BSON Null** và **field không tồn tại**; truy vấn `{ billing_city: null }` có thể khớp cả hai, còn `{ billing_city: { $exists: false } }` chỉ khớp field thiếu.

### 6.3. Kiểm tra dữ liệu rỗng

```javascript
// Địa chỉ không có field thành phố:
db.customer_profiles.find({
  billing_city: { $exists: false }
});

// Có field thành phố nhưng giá trị BSON Null:
db.customer_profiles.find({
  billing_city: { $type: "null" }
});

// Không có bất kỳ field địa chỉ nào:
db.customer_profiles.find({
  billing_street: { $exists: false },
  billing_city: { $exists: false },
  billing_postal_code: { $exists: false }
});
```

Những truy vấn này hữu ích để tìm document không đầy đủ trước khi thay đổi cấu hình `onEmpty` hoặc chạy migration.

## 7. Tránh lost update với `@Version` và compare-and-set

Với `@Version` trên root, `repository.save(profile)` có thể kiểm tra phiên bản khi ghi. Nếu hai request cùng đọc bản cũ rồi thay địa chỉ, request đến sau không được âm thầm ghi đè khi optimistic locking hoạt động và write concern được xác nhận.

Nhưng câu lệnh `MongoTemplate.updateFirst` **không tự biết phiên bản mà client đã đọc** nếu query chỉ lọc theo `id`. Một số API update Spring Data có thể tự tăng giá trị `version`, song **tăng version** khác với **so khớp expected version**.

Muốn kiểm tra phiên bản rõ ràng, đưa giá trị đó vào query:

```java
public boolean changeCityIfVersionMatches(
        MongoTemplate template,
        ObjectId profileId,
        long expectedVersion,
        String newCity) {

    Query query = Query.query(
        Criteria.where("id").is(profileId)
            .and("version").is(expectedVersion)
    );
    Update update = new Update()
        .set("billingAddress.city", newCity)
        .inc("version", 1);

    return template.updateFirst(
        query, update, CustomerProfile.class
    ).getModifiedCount() == 1;
}
```

Ví dụ coi `version` là giá trị Long đã có. Nếu không match, trả lỗi nghiệp vụ phù hợp, chẳng hạn HTTP 409 Conflict sau khi kiểm tra nguyên nhân, thay vì cứ retry vô hạn. Vì thao tác update chỉ tác động một document, phần cập nhật thành phố và tăng version diễn ra nguyên tử.

**Tránh kết hợp mù quáng** update tự quản lý version với những thao tác `save` hoặc callback khác cũng thay version. Mọi đường ghi cần áp dụng cùng hợp đồng optimistic locking, và phải kiểm tra `matchedCount`/`modifiedCount` sau khi ghi.

## 8. Index, aggregation và projection trên tên BSON phẳng

### 8.1. Index trên field thực tế

Ví dụ thường tìm khách hàng theo thành phố và mã bưu chính, có thể tạo index ghép:

```javascript
db.customer_profiles.createIndex(
  { billing_city: 1, billing_postal_code: 1 },
  { name: "idx_billing_city_postal" }
);

db.customer_profiles.getIndexes();
```

Trong index definition raw, dùng **tên field BSON**. Nếu viết index theo `"billingAddress.city"` sẽ tạo index cho **đường dẫn lồng nhau khác**, không giúp truy vấn vào `billing_city` như mong muốn.

Có thể khai báo metadata index trong Spring Data hoặc chủ động tạo qua `IndexOperations`/migration. Tính năng **tự động tạo index** từ annotation thường không bật mặc định trong các phiên bản Spring Data MongoDB hiện đại; hãy xác nhận index đã tồn tại trên MongoDB thay vì chỉ nhìn annotation.

Kiểm tra query plan:

```javascript
db.customer_profiles.find({
  billing_city: "Ha Noi",
  billing_postal_code: "100000"
}).explain("executionStats");
```

Đọc `winningPlan`, `totalKeysExamined`, `totalDocsExamined` và `nReturned`; số liệu còn tùy khối lượng dữ liệu và phiên bản MongoDB. Một tập dữ liệu nhỏ chưa đủ để kết luận index giúp giảm độ trễ trong production.

### 8.2. Aggregation raw sử dụng field BSON

Đếm hồ sơ theo thành phố thanh toán:

```javascript
db.customer_profiles.aggregate([
  { $match: { billing_city: { $exists: true } } },
  {
    $group: {
      _id: "$billing_city",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

`$group` dùng `"$billing_city"` chứ không phải `"$billingAddress.city"`, vì đây là pipeline raw chạy trên BSON tại MongoDB server.

Khi xây dựng aggregation dạng typed trong Spring Data, mapper có thể sử dụng metadata domain class để đổi property path. Tuy nhiên, các stage JSON/Document tự xây, field tính toán, projection alias và pipeline kết hợp nhiều collection có thể có ngữ cảnh mapping khác nhau. Hãy kiểm tra pipeline sinh ra hoặc chạy integration test, thay vì giả định mọi chuỗi field trong pipeline đều được ánh xạ giống `Query`.

### 8.3. Phân biệt index và schema validation

`@Unwrapped` **không bảo đảm** các field phẳng có kiểu đúng hay luôn xuất hiện. Nếu cần kiểm tra database-level, tạo MongoDB JSON Schema validator với các field BSON `billing_city`, `billing_postal_code`, không khai báo validator yêu cầu object `billingAddress` không tồn tại.

Ví dụ điều kiện schema cho địa chỉ có thể dùng:

```javascript
{
  bsonType: "object",
  properties: {
    billing_city: { bsonType: "string" },
    billing_postal_code: { bsonType: "string" }
  }
}
```

Đây là **mảnh schema minh họa**, cần đặt trong `$jsonSchema` khi cấu hình validator. Một index giúp truy vấn/unique constraint; validator dùng để áp đặt cấu trúc/kiểu. Chúng là hai cơ chế khác nhau.

## 9. Giới hạn và trường hợp không phù hợp của `@Unwrapped`

| Tình huống | Vấn đề | Hướng thiết kế |
| --- | --- | --- |
| Root và unwrapped object cùng có field `city` | Nếu không có prefix, hai thuộc tính tranh cùng một key BSON | Dùng prefix riêng; xem lại quyền sở hữu field |
| Hai địa chỉ `billingAddress` và `shippingAddress` | Trải phẳng cả hai không prefix khiến tên `street`/`city` va nhau | Dùng `billing_` và `shipping_` |
| Query toàn bộ `Address` | Không có field BSON `billingAddress` để so khớp object | Query từng field phẳng |
| `$set` nguyên object | MongoDB sẽ nhắm đến field `billingAddress` mới nếu dùng raw BSON | `$set` từng key `billing_*` trong một lệnh |
| Dùng collection/map động làm value object | Số lượng/tên field con không cố định, khó kiểm soát va chạm | Dùng nested document hoặc map đúng cấu trúc |
| Value object chứa ID/vòng đời riêng | Không phải thành phần thuộc một aggregate root | Tách thành aggregate/collection và tham chiếu phù hợp |
| Cần truy vấn mảng địa chỉ như các phần tử độc lập | Trải phẳng không giữ cấu trúc array của nhiều địa chỉ | Dùng nested array và `$elemMatch` khi phù hợp |
| Refactor đổi `prefix` hoặc tên `@Field` | Dữ liệu cũ vẫn giữ key BSON cũ | Lập migration có kiểm tra trước/sau |
| Chỉ đọc một phần field rồi `save` | Có thể thay thế document với object không đầy đủ | Dùng DTO/projection đọc riêng hoặc targeted update |
| Dữ liệu ghi bởi script và Spring Data | Raw script không có mapper; có thể tạo field nested ngoài ý muốn | Thống nhất hợp đồng tên BSON và kiểm thử tích hợp |

### 9.1. Va chạm tên field là lỗi schema

Giả sử class root có `private String city` và còn:

```java
@Unwrapped
private Address billingAddress;
```

Cả root `city` và `billingAddress.city` cùng muốn lưu tại BSON key `city`. Đây không phải hai vị trí độc lập trong document. Cần sửa cấu trúc hoặc cấu hình prefix:

```java
@Unwrapped(prefix = "billing_")
private Address billingAddress;
```

Tránh dựa vào thứ tự mapping để đoán field nào sẽ ghi đè field nào. Với các class phát triển về sau, ngay cả khi hôm nay không trùng, thêm một property mới vào value object có thể gây va chạm nếu không có prefix.

### 9.2. Không thay `@Unwrapped` cho object đa hình/tập động một cách tùy tiện

`@Unwrapped` phù hợp nhất với **value object có cấu trúc hữu hạn, ổn định**, thuộc về một aggregate. Nếu value object có nhiều subtype, các field con đổi liên tục hoặc một tập giá trị cần phân trang riêng, việc trải phẳng có thể làm mất ranh giới cấu trúc và tăng độ phức tạp khi deserialize.

Trước khi dùng với polymorphism, nested unwrapped, map hay collections, kiểm tra khả năng hỗ trợ ở đúng phiên bản Spring Data MongoDB và viết integration test. Với mô hình mà cấu trúc con cần duy trì như một đơn vị BSON, nhúng bình thường rõ nghĩa hơn.

### 9.3. Không trông chờ cascade hay transaction tự động

`@Unwrapped` là metadata mapping, **không phải** cơ chế liên kết khóa ngoại, cascade hoặc transaction. Sửa một hoặc nhiều field phẳng trong cùng document được MongoDB xử lý nguyên tử ở cấp document. Nếu yêu cầu cập nhật đồng thời một document khác (chẳng hạn customer profile và bảng thống kê địa chỉ ở collection khác), phải thiết kế transaction nhiều document hoặc quy trình nhất quán bất đồng bộ riêng.

## 10. Thực hành bằng `mongosh`: quan sát dữ liệu trải phẳng

Tạo dữ liệu thử nghiệm trong collection riêng, mỗi phiên dùng marker duy nhất để tránh sửa/xóa dữ liệu người khác:

```javascript
use spring_data_training

const lab = db.getCollection("unwrapped_lab");
const runId = "embedded-objects-008-" + new ObjectId().toHexString();

const insertion = lab.insertOne({
  runId: runId,
  customerNo: "CUS-LAB-001",
  displayName: "Khach thu nghiem",
  billing_street: "10 Pho Mau",
  billing_city: "Ha Noi",
  billing_postal_code: "100000"
});

printjson(insertion.insertedId);
printjson(lab.findOne({ _id: insertion.insertedId, runId: runId }));
```

`unwrapped_lab` là collection **khác** `customer_profiles` của entity Java ở ví dụ trước; nó chỉ dùng để quan sát cú pháp raw BSON. Nếu muốn đọc chính document này bằng entity `CustomerProfile`, phải ánh xạ entity tới collection tương ứng hoặc dùng thao tác đọc chỉ rõ collection.

### 10.1. Query đúng field

```javascript
lab.find({
  _id: insertion.insertedId,
  runId: runId,
  billing_city: "Ha Noi"
}).toArray();

// Không khớp vì raw BSON không có billingAddress.city:
lab.find({
  _id: insertion.insertedId,
  runId: runId,
  "billingAddress.city": "Ha Noi"
}).toArray();
```

### 10.2. Cập nhật nguyên tử hai field

```javascript
const updateResult = lab.updateOne(
  { _id: insertion.insertedId, runId: runId },
  {
    $set: {
      billing_city: "Da Nang",
      billing_postal_code: "550000"
    }
  }
);

printjson({
  matchedCount: updateResult.matchedCount,
  modifiedCount: updateResult.modifiedCount
});
```

Đọc lại:

```javascript
lab.findOne(
  { _id: insertion.insertedId, runId: runId },
  {
    _id: 0,
    billing_street: 1,
    billing_city: 1,
    billing_postal_code: 1,
    billingAddress: 1
  }
);
```

Kết quả có ba field `billing_*`; không có field `billingAddress`.

### 10.3. Thử xóa từng field

```javascript
lab.updateOne(
  { _id: insertion.insertedId, runId: runId },
  { $unset: { billing_street: "", billing_postal_code: "" } }
);

lab.findOne({
  _id: insertion.insertedId,
  runId: runId
});
```

`billing_city` vẫn tồn tại, nên một Java `Address` đọc lại có thể có `city` nhưng `street` và `postalCode` là `null`. Chỉ khi toàn bộ field cần dùng cho unwrapped object trống/thiếu thì `onEmpty` mới quyết định cách dựng object rỗng theo cấu hình.

### 10.4. Dọn dữ liệu thử nghiệm

```javascript
lab.deleteOne({
  _id: insertion.insertedId,
  runId: runId
});
```

Không dùng `deleteMany({})` hoặc `drop()` trên collection thật. Chỉ xóa document của phiên vừa tạo. Nếu muốn quan sát bằng MongoDB Compass, hãy dọn dữ liệu **sau khi** kiểm tra xong.

## 11. Kiểm thử tích hợp mapping và đường ghi

Vì `@Unwrapped` thay đổi tên field **trên BSON**, unit test chỉ kiểm tra object Java chưa đủ. Kiểm thử với MongoDB thật hoặc Testcontainers MongoDB cần xác minh cả hai phía:

1. Ghi `CustomerProfile` qua repository.
2. Đọc raw BSON trong `customer_profiles`, xác nhận **có** `billing_city` và **không có** field `billingAddress`.
3. Truy vấn bằng `findByBillingAddressCity` và `MongoTemplate` dùng property path.
4. Cập nhật bằng `Update.set("billingAddress.city", ...)`, kiểm tra raw field thực sự đổi.
5. Thử dữ liệu chỉ có một phần field, dữ liệu không có field, và cấu hình `USE_NULL` / `USE_EMPTY`.
6. Thử xung đột version hoặc hai thao tác update đồng thời khi nghiệp vụ yêu cầu.

Ví dụ khung kiểm thử cho hai bước đầu, với Spring Boot Test/JUnit 5 và repository/template được cấu hình trỏ đến MongoDB thử nghiệm:

```java
import static org.junit.jupiter.api.Assertions.*;
import static com.mongodb.client.model.Filters.eq;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class UnwrappedMappingTest {
    @Autowired CustomerProfileRepository repository;
    @Autowired MongoTemplate template;

    @Test
    void storesFlatFieldsInsteadOfNestedAddress() {
        var address = new CustomerProfile.Address(
            "10 Pho Mau", "Ha Noi", "100000"
        );
        var profile = repository.insert(
            new CustomerProfile("CUS-TEST-001", "Khach thu", address)
        );

        try {
            Document raw = template.getCollection("customer_profiles")
                .find(eq("_id", profile.getId()))
                .first();

            assertNotNull(raw);
            assertEquals("Ha Noi", raw.getString("billing_city"));
            assertEquals("100000",
                         raw.getString("billing_postal_code"));
            assertFalse(raw.containsKey("billingAddress"));

            assertFalse(
                repository.findByBillingAddressCity("Ha Noi").isEmpty()
            );
        } finally {
            repository.deleteById(profile.getId());
        }
    }
}
```

Tên mã khách hàng trong ví dụ chỉ mang tính minh họa; ở môi trường test dùng database/collection cách ly và tránh giả định tên cố định không thể trùng giữa các lượt chạy. Kiểm thử này cần MongoDB đang hoạt động và cấu hình Spring Boot test phù hợp. Theo quy trình bài học, code được cung cấp để bạn thực hành; nó chưa được chạy trong workspace khi soạn tài liệu.

### Kiểm tra khi sửa metadata

Nếu đổi `@Field("postal_code")` thành `@Field("zip")` hoặc đổi prefix từ `billing_` sang `invoice_`, document cũ **không tự được đổi tên field**. Trước khi release:

- Xác định các collection và field BSON đang có.
- Quy định schema cũ/mới và cách đọc trong giai đoạn chuyển đổi.
- Dùng migration có kiểm soát, cân nhắc thao tác `$rename` với tên field **thực tế** khi phù hợp.
- Cập nhật index, query raw, aggregation, validator và cả mã Java.
- Chạy integration test và kiểm tra dữ liệu trước/sau migration.

Ví dụ minh họa dạng lệnh rename BSON, **chỉ thực hiện trên dữ liệu thử nghiệm sau khi đánh giá rủi ro**:

```javascript
// Ví dụ đổi tên field phẳng cũ sang field phẳng mới.
db.customer_profiles.updateMany(
  { billing_postal_code: { $exists: true } },
  { $rename: { billing_postal_code: "invoice_postal_code" } }
);
```

Đây là thao tác sửa nhiều document, không phải migration transaction tự động. Trước khi áp dụng thực tế phải xử lý dữ liệu đã có field đích, kế hoạch rollback, update index và mọi đường ghi/đọc liên quan.

## 12. Bài tập tự luyện

**Bài 1 — Xác định BSON.** Một class `Employee` có `@Unwrapped(prefix = "contact_") ContactInfo contact`, trong `ContactInfo` có `email`, `phone` và `@Field("emergency_phone") emergencyPhone`. Viết document BSON dự kiến, sau đó viết bộ lọc `mongosh` tìm theo email.

**Bài 2 — Repository và template.** Viết `findByContactEmail(...)` trong repository, `Criteria.where("contact.email").is(...)` cho `MongoTemplate` và truy vấn raw tương đương. Giải thích khi nào prefix được mapper áp dụng.

**Bài 3 — Update đúng field.** Viết `Update` đổi email và số điện thoại của `ContactInfo` trong một lần ghi. Viết lệnh `mongosh` tương đương, giải thích nguy cơ khi sử dụng `$set: { contact: {...} }`.

**Bài 4 — Field thiếu và null.** Thử ba document: không có field `contact_*`, chỉ có `contact_email`, có `contact_email: null`. So sánh cách đọc khi `onEmpty = USE_NULL` và `onEmpty = USE_EMPTY`. Xác nhận bằng integration test.

**Bài 5 — Va chạm tên.** Một class có `@Unwrapped Address homeAddress` và `@Unwrapped Address officeAddress`, cả hai cùng có `city`. Đề xuất hai prefix, viết BSON và một index phù hợp cho truy vấn theo thành phố làm việc.

**Bài 6 — Projection và optimistic locking.** Một service chỉ đọc `contact_email` rồi lưu lại toàn bộ `Employee`. Hãy chỉ ra rủi ro mất field và đề xuất một update có điều kiện theo `id`, `version`. Xác định trạng thái ứng dụng trả về khi version không còn khớp.

**Bài 7 — Refactor schema.** Khi đổi prefix `contact_` thành `primary_contact_`, liệt kê những thứ cần cập nhật: dữ liệu cũ, query repository, raw Mongo query, pipeline, index, validator, test và đường ghi từ dịch vụ khác.

### Ghi nhớ

**`@Unwrapped` trải phẳng value object vào document cha.** Ở Java vẫn có property path như `billingAddress.city`, nhưng BSON lưu field như `billing_city`. Repository và `MongoTemplate` dùng metadata entity để ánh xạ query/update; `mongosh`, Compass, raw driver, index và aggregation raw phải sử dụng **tên BSON thực tế**. Ưu tiên truy vấn/cập nhật từng field đã trải phẳng, dùng prefix tránh va chạm, kiểm tra `onEmpty` khi field thiếu và đừng thay nguyên object hay lưu lại entity được projection không đầy đủ. Thử nghiệm trên MongoDB thật là cách xác nhận các đường ánh xạ hoạt động đúng.
