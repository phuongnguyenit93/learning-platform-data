# Giới hạn phép đếm, transaction và biến thể reactive

## 1. Vì sao truy vấn địa lý cần một cách đếm khác?

Một ứng dụng đặt lịch sử dụng **SPRING_DATA_MONGODB** để tìm các cửa hàng quanh một tọa độ: trả 20 địa điểm gần nhất, đồng thời hiển thị “có 137 cửa hàng trong bán kính 2 km”. Người lập trình dùng Spring Data MongoDB qua **MongoTemplate** hoặc repository và viết:

~~~java
Query nearby = Query.query(
    Criteria.where("location")
        .near(new GeoJsonPoint(106.7009, 10.7769))
        .maxDistance(2_000)
);

List<StoreDocument> results =
    mongoTemplate.find(nearby, StoreDocument.class);

long total = mongoTemplate.count(
    nearby, StoreDocument.class);
~~~

Phần **find** và **count** có thể không chạy cùng một hình thức truy vấn ở MongoDB Server. Các toán tử **$near/$nearSphere** vốn dành cho việc tìm và sắp kết quả theo khoảng cách; trong khi **countDocuments** dùng cơ chế đếm dựa trên aggregation và không cho phép dùng trực tiếp hai toán tử này trong bộ lọc đếm.

Spring Data MongoDB có cơ chế viết lại một số query geospatial cho phép đếm, nhưng việc đó cần được hiểu đúng:

- **Đếm số kết quả không giống sắp xếp theo khoảng cách.**
- **$near/$nearSphere không thể được chuyển thành $geoWithin mà không xét semantics.**
- **$minDistance** thường đòi thêm điều kiện loại trừ vòng tròn trong.
- **Số lượng đếm và danh sách trả ra có thể không cùng snapshot** nếu chạy thành hai lệnh độc lập.
- **Transaction** cần được đánh giá riêng về session, operator hỗ trợ và chi phí.
- **Reactive** hỗ trợ truy vấn địa lý, nhưng kết quả trả về là Publisher và không có mọi wrapper tổng hợp như API đồng bộ.

Bài **Giới hạn phép đếm, transaction và biến thể reactive** thuộc chương **Truy vấn không gian** của module **SPRING_DATA_MONGODB**. Module tập trung vào kết nối và ánh xạ document, thao tác MongoDB qua MongoTemplate/repository, thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

Sau bài này, bạn sẽ có thể xây một API tìm kiếm cửa hàng theo bán kính với tổng số kết quả có thể giải thích được, truy vấn reactive có giới hạn tài nguyên và kiểm thử đúng những ranh giới của MongoDB.

## 2. Ba câu hỏi khác nhau: gần nhất, trong vùng và bao nhiêu?

Giả sử có năm cửa hàng A, B, C, D, E tại các vị trí khác nhau:

~~~text
                     B
                .----------.
             .-'            '-.
            /      A           \
           |         X      C   |     E
            \         D         /
             '-.            .-'
                '----------'

X: vị trí khách hàng
Vòng tròn: bán kính tìm kiếm
~~~

Ba yêu cầu không tương đương:

| Câu hỏi | Operator/pipeline phù hợp | Kết quả |
| --- | --- | --- |
| Những điểm nào gần X nhất, có khoảng cách? | **$near/$nearSphere** hoặc **$geoNear** | Danh sách có thứ tự khoảng cách |
| Những điểm nào nằm trong một hình/bán kính? | **$geoWithin** | Tập document thỏa hình học, không tự có sort khoảng cách |
| Bao nhiêu điểm thỏa một bán kính? | **countDocuments** với **$geoWithin** hoặc aggregation count phù hợp | Một số lượng |

**Không nên dùng $near chỉ để đếm** khi API không yêu cầu sắp xếp khoảng cách.

### 2.1. Đếm trên toàn tập và đếm trên trang

Một API có thể trả:

~~~json
{
  "items": ["store-A", "store-C"],
  "pageSize": 2,
  "totalInRadius": 5
}
~~~

**items.length = 2** là số hàng của trang hiện tại, còn **totalInRadius = 5** là tổng số document phù hợp với phạm vi và các filter trước khi áp skip/limit. Không dùng số phần tử đã nhận làm tổng số toàn tập.

### 2.2. Đếm tài liệu, không phải đếm tọa độ

Nếu một document Store có nhiều điểm trong một mảng (nhiều chi nhánh), một phép countDocuments sẽ đếm **document khớp**, không nhất thiết đếm số tọa độ khớp. Nếu nghiệp vụ cần đếm **số chi nhánh**, nên mô hình mỗi chi nhánh một document hoặc dùng một aggregation riêng với các bước unwind/filter thích hợp.

### 2.3. Thứ tự trong GeoJSON

GeoJSON Point sử dụng:

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

Thứ tự bắt buộc là **[longitude, latitude]**, không phải [latitude, longitude]. Giá trị longitude nằm trong [-180,180], latitude trong [-90,90]. Một vị trí sai thứ tự có thể bị MongoDB từ chối hoặc được hiểu thành một điểm hoàn toàn khác.

## 3. Mô hình StoreDocument và 2dsphere index

Mẫu dữ liệu được sử dụng xuyên suốt:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  name: "Store A",
  active: true,
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
~~~

Java entity:

~~~java
package com.example.geosearch;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "stores")
public record StoreDocument(
    @Id ObjectId id,
    String tenantId,
    String name,
    boolean active,
    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    GeoJsonPoint location
) {}
~~~

**@GeoSpatialIndexed** mô tả metadata của index. Index thật phải tồn tại trong MongoDB; auto-index creation không được mặc định bật trong mọi dự án.

~~~javascript
db.stores.createIndex(
  { location: "2dsphere" },
  { name: "idx_stores_location_2dsphere" }
);
~~~

### 3.1. Compound index và tenant

Nếu hệ thống luôn lọc tenant/active, có thể đánh giá compound index:

~~~javascript
db.stores.createIndex(
  { tenantId: 1, active: 1, location: "2dsphere" },
  { name: "idx_stores_tenant_active_geo" }
);
~~~

Đây là **đề xuất cần benchmark**, không phải một index luôn vượt trội. Cách MongoDB sử dụng compound geospatial index phụ thuộc query shape, dữ liệu, cardinality và MongoDB Server version; chạy **explain("executionStats")** trước khi đưa vào production.

### 3.2. Dữ liệu không hợp lệ

Một GeoJSON Point cần có kiểu và tọa độ hợp lệ. Một **2dsphere index** có những yêu cầu đối với hình học được index. Cần validation cho dữ liệu người dùng, kiểm tra field có bị null/missing và kiểm soát schema migrations.

### 3.3. Không lẫn 2d và 2dsphere

| Index | Dữ liệu thường dùng | Mô hình |
| --- | --- | --- |
| 2d | Legacy coordinate pairs | Phẳng, cần chú ý đơn vị tọa độ |
| 2dsphere | GeoJSON và một số legacy coordinate formats | Hình học trên mặt cầu |

Với dữ liệu vị trí thực của cửa hàng trên Trái Đất, **GeoJSON Point + 2dsphere** thường là mô hình dễ diễn đạt hơn. Không tự coi phép tính trên bản đồ phẳng bằng bán kính tính theo “độ” là khoảng cách mét chính xác.

## 4. Những toán tử geospatial cần phân biệt

| Operator | Mục đích | Tự sort theo khoảng cách? | Cần chú ý khi count? |
| --- | --- | --- | --- |
| $near | Tìm lân cận một point | Có | Không được dùng trực tiếp trong countDocuments |
| $nearSphere | Tìm lân cận với hình học cầu | Có | Không được dùng trực tiếp trong countDocuments |
| $geoWithin | Lọc hình học nằm trong vùng | Không | Phù hợp cho countDocuments |
| $geoIntersects | Lọc hình học giao với một geometry | Không | Phù hợp khi yêu cầu là “giao nhau” |
| $geoNear | Aggregation stage tính distance và xếp gần–xa | Có | Không coi như $match; stage phải đứng đầu pipeline |

### 4.1. $near và GeoJSON

~~~javascript
db.stores.find({
  tenantId: "shop-a",
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 2000
    }
  }
});
~~~

Với **GeoJSON Point** được dùng trong điều kiện gần, khoảng cách tối đa tính bằng **meters**. $near trả những document phù hợp theo thứ tự gần trước; thêm một sort khác có thể làm thay đổi thứ tự khoảng cách và tăng chi phí.

### 4.2. $geoWithin với $centerSphere

~~~javascript
const EARTH_RADIUS_METERS = 6371008.8;
const radiusRadians = 2000 / EARTH_RADIUS_METERS;

db.stores.find({
  tenantId: "shop-a",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7009, 10.7769],
        radiusRadians
      ]
    }
  }
});
~~~

**$centerSphere nhận bán kính bằng radians**, do đó 2.000 mét phải được chuyển bằng tỉ số với bán kính Trái Đất tính theo mét. Dùng trực tiếp 2000 làm radius của $centerSphere là sai đơn vị.

### 4.3. $geoWithin không trả distance

Một document nằm trong bán kính 2 km sẽ được chọn, nhưng **không tự có distance field**. Nếu cần hiển thị “cách bạn 430 m” hoặc sắp gần nhất, cần $geoNear, hoặc một phép tính distance có đơn vị rõ theo yêu cầu.

### 4.4. Tại sao không thay $near bằng $geoWithin cho mọi mục đích?

Hai truy vấn có thể chọn một tập điểm tương tự trong trường hợp hình học được cấu hình tương đương, nhưng khác sort mặc định, distance metadata, cách biểu diễn vòng ngoài/vòng trong, index/operator constraints và các trường hợp ranh giới. Vì vậy, **thay khi muốn count** là một thiết kế có chủ ý.

## 5. countDocuments không hỗ trợ trực tiếp $near/$nearSphere

Theo MongoDB và tài liệu Spring Data MongoDB về **Counting Documents**, countDocuments và bước $match aggregation tương ứng không chấp nhận $near hoặc $nearSphere làm predicate đếm.

Đoạn mongosh sau không phải cách đếm được hỗ trợ:

~~~javascript
// Không dùng $near trực tiếp cho countDocuments:
db.stores.countDocuments({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 2000
    }
  }
});
~~~

Thay bằng một truy vấn containment:

~~~javascript
const radiusRadians = 2000 / 6371008.8;

const total = db.stores.countDocuments({
  tenantId: "shop-a",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7009, 10.7769],
        radiusRadians
      ]
    }
  }
});
~~~

**Điểm cốt lõi:** countDocuments cần một biểu thức lọc tập document, không cần tính thứ tự khoảng cách.

### 5.1. countDocuments khác count của kết quả đã phân trang

~~~javascript
const page = db.stores.find(withinQuery)
  .sort({ name: 1, _id: 1 })
  .skip(20)
  .limit(10)
  .toArray();

const total = db.stores.countDocuments(withinQuery);
~~~

page.length có thể là 10, còn total có thể là 1.000. Tổng không được suy từ một trang; khi count theo mongosh/API cụ thể, xác nhận skip/limit/options của count được sử dụng đúng.

### 5.2. Không thay bằng estimatedDocumentCount

estimatedDocumentCount() dùng metadata/thống kê collection cho một ước lượng tổng document, **không nhận filter geospatial theo tenant, active hay bán kính**. Nó không trả “tổng cửa hàng trong 2 km”.

### 5.3. Nếu không cần total?

Khi API chỉ cần hiển thị một trang và cờ hasNext, có thể lấy pageSize+1 kết quả rồi quyết định còn trang tiếp hay không. **Không bắt buộc chạy count** cho mọi endpoint nếu UX không yêu cầu tổng số.

## 6. Spring Data MongoDB viết lại near query khi count

Từ thế hệ Spring Data MongoDB 3.x, các lời gọi **count** qua MongoTemplate/ReactiveMongoTemplate sử dụng cơ chế dựa trên countDocuments thay vì dựa vào thống kê collection cho truy vấn đếm thông thường.

Do countDocuments không nhận $near/$nearSphere, Spring Data có logic chuyển điều kiện geospatial sang **$geoWithin** và một vùng **$center/$centerSphere** tương ứng cho đường đếm.

Ví dụ tài liệu Spring Data mô tả:

~~~javascript
// Ý định ban đầu: chọn những point gần vị trí, có maxDistance.
{
  location: {
    $near: [-73.99171, 40.738868],
    $maxDistance: 1.1
  }
}
~~~

được biểu diễn khi count thành một điều kiện containment tương đương loại hình:

~~~javascript
{
  location: {
    $geoWithin: {
      $center: [
        [-73.99171, 40.738868],
        1.1
      ]
    }
  }
}
~~~

**Lưu ý:** ví dụ trên dùng cặp tọa độ legacy và $center với đơn vị theo không gian tọa độ. Nó **không phải** ví dụ bán kính 1.1 mét. Với GeoJSON/2dsphere, dùng đúng hình học cầu và chuyển đổi đơn vị.

### 6.1. Có thể gọi MongoTemplate.count trực tiếp không?

~~~java
GeoJsonPoint origin =
    new GeoJsonPoint(106.7009, 10.7769);

Query nearQuery = Query.query(
    Criteria.where("location")
        .near(origin)
        .maxDistance(2_000)
);

long total = mongoTemplate.count(
    nearQuery, StoreDocument.class);
~~~

Ở phiên bản Spring Data hỗ trợ rewrite, API sẽ điều chỉnh query count theo cách nó biết. Tuy vậy:

- Không tự coi việc có rewrite là bằng chứng mọi ranh giới min/max và geometry được giữ chính xác như ý muốn.
- Không dùng logic rewrite như một API public riêng cho code khác.
- Khi cần semantics count được kiểm soát chặt, **định nghĩa một geoWithin query riêng** và viết integration tests.
- Khi cập nhật Spring Data version, kiểm thử lại hành vi rewrite.

### 6.2. Tại sao phải kiểm tra command thực?

Ở những bài toán khó, bật driver command monitoring/test integration để kiểm tra **filter thực gửi xuống MongoDB**. Đừng chỉ in Query.toString() rồi khẳng định nó bằng chính lệnh sau khi Spring Data chuyển đổi.

### 6.3. Viết lại query đếm không biến nó thành nearest-neighbor

Một count thành công không trả danh sách được sort, không có distance cho từng document và không trả average distance. Nó chỉ tính số document phù hợp với filter sau khi được biểu diễn hợp lệ.

## 7. minDistance + maxDistance: đếm theo vành khăn

Một tìm kiếm có thể yêu cầu **từ 500 m đến 2.000 m**, tức là loại các điểm quá gần:

~~~javascript
db.stores.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $minDistance: 500,
      $maxDistance: 2000
    }
  }
});
~~~

**$geoWithin** không có thuộc tính $minDistance trực tiếp. Để đếm theo một vành khăn, mô hình hóa:

~~~text
Tập được đếm = Các document trong vòng tròn bán kính 2.000 m
               trừ các document trong vòng tròn bán kính 500 m
~~~

Một biểu diễn MongoDB:

~~~javascript
const earthRadius = 6371008.8;
const outerRadius = 2000 / earthRadius;
const innerRadius = 500 / earthRadius;

db.stores.countDocuments({
  $and: [
    { tenantId: "shop-a", active: true },
    {
      location: {
        $geoWithin: {
          $centerSphere: [
            [106.7009, 10.7769],
            outerRadius
          ]
        }
      }
    },
    {
      $nor: [
        {
          location: {
            $geoWithin: {
              $centerSphere: [
                [106.7009, 10.7769],
                innerRadius
              ]
            }
          }
        }
      ]
    }
  ]
});
~~~

### 7.1. Ranh giới của vòng trong

Nếu vòng trong được xem là **bao gồm** các điểm tại đúng bán kính 500 m, thì $nor loại cả chúng. Trong khi đó, $minDistance của nearest query có semantics riêng về điểm nằm trên ranh giới.

Các vị trí đúng trên boundary, floating-point precision và hình học ở khu vực đặc biệt cần **integration test** khi yêu cầu đếm chính xác tới từng điểm biên.

### 7.2. Rewrite tự động trong Spring Data

Tài liệu Spring Data có mô tả trường hợp **minDistance** bằng cách kết hợp $geoWithin và $nor. Không đồng nhất việc viết lại ở một phiên bản cụ thể với việc luôn bảo toàn mọi semantics của toàn bộ truy vấn ban đầu; kiểm tra API/version và BSON được sinh.

### 7.3. Không dùng hai phép count rồi trừ nếu cần một snapshot

~~~javascript
const outer = db.stores.countDocuments(outerFilter);
const inner = db.stores.countDocuments(innerFilter);
const annulus = outer - inner;
~~~

Nếu giữa hai phép count có writer thêm/xóa/chuyển vị trí, số liệu có thể không nhất quán. Một **countDocuments với điều kiện vành khăn** hoặc một aggregation cùng operation phù hợp hơn khi cần một tập điều kiện được đánh giá trong một lần đếm.

## 8. Near vs within: bảng chọn cho API thật

| API requirement | Truy vấn ưu tiên | Cần count riêng? |
| --- | --- | --- |
| “20 cửa hàng gần nhất” | $near/$geoNear + limit | Không nếu không hiển thị total |
| “Tất cả cửa hàng trong 2 km” | $geoWithin + $centerSphere | Có thể count nếu cần total |
| “Trong 2 km, sort theo tên” | geoWithin + sort name/id | Có nếu UI muốn total |
| “Từ 500 m đến 2 km” | $geoNear min/max hoặc geoWithin outer + exclude inner | Có nếu muốn total |
| “Có bao nhiêu cửa hàng đang mở trong bán kính?” | countDocuments geoWithin + status filter | Không cần query nearest |
| “Liệt kê khoảng cách thực tới từng cửa hàng” | $geoNear | Count là operation khác |
| “Vùng đa giác giao với tuyến đường” | $geoIntersects tùy geometry | Count theo geometry/filter tương ứng |

**Chỉ dùng phép đếm đúng như một câu hỏi nghiệp vụ độc lập**, không gắn countDocuments vào mọi $near query một cách máy móc.

## 9. Xây hàm đếm bán kính bằng MongoTemplate

Để loại bỏ nhập nhằng, service nên cung cấp phương thức đếm riêng, nhận bán kính **meters** và dùng $geoWithin/$centerSphere.

~~~java
package com.example.geosearch;

import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class StoreRadiusCountService {

    private static final double EARTH_RADIUS_METERS = 6_371_008.8;
    private final MongoTemplate mongoTemplate;

    public StoreRadiusCountService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public long countWithin(
            String authenticatedTenantId,
            double longitude, double latitude,
            double radiusMeters) {

        validate(authenticatedTenantId,
            longitude, latitude, radiusMeters);

        Circle sphere = new Circle(
            new Point(longitude, latitude),
            radiusMeters / EARTH_RADIUS_METERS
        );

        Query query = Query.query(
            Criteria.where("tenantId")
                .is(authenticatedTenantId)
                .and("active").is(true)
                .and("location").withinSphere(sphere)
        );

        return mongoTemplate.count(query, StoreDocument.class);
    }

    private static void validate(
            String tenant,
            double longitude, double latitude,
            double radiusMeters) {

        if (tenant == null || tenant.isBlank()
                || !Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -90 || latitude > 90
                || !Double.isFinite(radiusMeters)
                || radiusMeters <= 0
                || radiusMeters > 50_000) {
            throw new IllegalArgumentException(
                "Invalid location or radius");
        }
    }
}
~~~

**Ý nghĩa:** tenant từ authentication context đáng tin cậy; latitude/longitude/radius được validate; bán kính chuyển sang **radians** cho withinSphere; toàn bộ filter tenant + active + location được dùng khi count.

### 9.1. Vì sao giới hạn 50 km?

Đó là **policy minh họa**, không phải giới hạn bắt buộc của MongoDB. Tùy yêu cầu, có thể chọn 5 km, 100 km hoặc vùng tùy ý; phải đo query plan, dữ liệu và SLA.

### 9.2. Một nguồn filter

API danh sách và API đếm phải sử dụng cùng center, radius, tenant, active, category và điều kiện khác. Nên có object **StoreSearchCriteria** hoặc helper tạo filter dùng chung để tránh một endpoint đổi điều kiện mà endpoint kia không đổi.

### 9.3. Đếm ngay sau update

Kết quả có thể phụ thuộc read preference, read concern, replication và trạng thái commit. Query đúng công thức không bảo đảm mọi replica đã nhận dữ liệu mới nhất tại đúng cùng thời điểm.

## 10. Đếm bằng aggregation $match + $count

MongoDB có aggregation pipeline:

~~~javascript
const r = 2000 / 6371008.8;

db.stores.aggregate([
  {
    $match: {
      tenantId: "shop-a",
      active: true,
      location: {
        $geoWithin: {
          $centerSphere: [
            [106.7009, 10.7769],
            r
          ]
        }
      }
    }
  },
  { $count: "total" }
]);
~~~

Đây là một cách đếm theo vùng **không có $near trong $match**.

### 10.1. Spring Data Aggregation

~~~java
import org.bson.Document;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

Circle radius = new Circle(
    new Point(106.7009, 10.7769),
    2000.0 / 6371008.8
);

Aggregation pipeline = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("tenantId").is("shop-a")
            .and("active").is(true)
            .and("location").withinSphere(radius)
    ),
    Aggregation.count().as("total")
);

AggregationResults<Document> results =
    mongoTemplate.aggregate(
        pipeline, StoreDocument.class, Document.class);

Document row = results.getUniqueMappedResult();
long total = row == null
    ? 0L
    : ((Number) row.get("total")).longValue();
~~~

Đoạn minh họa vai trò của Aggregation.match, Aggregation.count và kết quả rỗng. Service hoàn chỉnh cần validate input, không hardcode tenant, và áp authorization.

### 10.2. Không có document thì sao?

Khi $count không có input, pipeline có thể không phát ra document total=0 mà **không có bản ghi kết quả**. Mapping DTO phải chuyển output rỗng thành số 0.

### 10.3. Có nên tự viết aggregation cho mọi count?

Không. **mongoTemplate.count(query, type)** với $geoWithin thường ngắn và dễ duy trì hơn. Aggregation riêng hữu ích khi cần nhiều stage nhưng không tự nhanh hơn countDocuments.

## 11. Đếm có paging: tránh tổng của trang

Một API trả page=2, size=10 và total=97:

~~~text
Query danh sách: tenant + active + vùng + sort + skip 20 + limit 10
Query đếm:       tenant + active + vùng (không giới hạn theo trang)
~~~

Ví dụ:

~~~java
Query countFilter = Query.query(
    Criteria.where("tenantId").is(tenant)
        .and("active").is(true)
        .and("location").withinSphere(circle)
);

long total = mongoTemplate.count(
    countFilter, StoreDocument.class);

Query pageQuery = Query.query(
    Criteria.where("tenantId").is(tenant)
        .and("active").is(true)
        .and("location").withinSphere(circle)
);

pageQuery.with(
    org.springframework.data.domain.PageRequest.of(
        2, 10,
        org.springframework.data.domain.Sort.by("name")
            .ascending()
            .and(org.springframework.data.domain.Sort.by("_id"))
    )
);

List<StoreDocument> page =
    mongoTemplate.find(pageQuery, StoreDocument.class);
~~~

**Dùng một Query riêng cho đếm** giúp tránh suy đoán việc count API xử lý skip/limit ra sao trên các phiên bản/framework khác nhau.

### 11.1. Sort ổn định

Nếu nhiều cửa hàng có cùng name, chỉ sort theo name có thể không ổn định; thêm một tie-breaker duy nhất như **_id**. Nhưng dữ liệu thay đổi giữa các request vẫn có thể khiến offset paging bị lặp hoặc thiếu hàng.

### 11.2. Phân trang nearest khác gì?

Với $near/$geoNear, distance quyết định thứ tự tự nhiên. Những địa điểm bằng distance có thể cần tie-breaker phù hợp và thêm sort có thể tốn chi phí. Kiểm tra query plan khi dùng offset/skip lớn.

### 11.3. Khi không cần total

Lấy tối đa **pageSize+1** kết quả để quyết định hasNext, rồi trả pageSize phần tử đầu. Không phải gọi count cho mọi màn hình chỉ vì framework có Page type.

## 12. Transaction: không chỉ là thêm @Transactional

MongoDB transaction gắn với một **ClientSession** và yêu cầu deployment hỗ trợ, thường là replica set hoặc sharded cluster tương thích. Spring Data cung cấp MongoTransactionManager:

~~~java
package com.example.geosearch;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class MongoTxConfiguration {

    @Bean("mongoTransactionManager")
    MongoTransactionManager transactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

MongoTemplate dùng cùng MongoDatabaseFactory có thể tham gia transaction session do manager quản lý.

### 12.1. Tại sao count trong transaction có khác biệt lịch sử?

Lệnh count cũ dựa trên collection statistics không phản ánh đúng những thay đổi trong transaction. Spring Data từng chọn aggregation-based count khi transaction đang hoạt động. Từ **Spring Data MongoDB 3.x**, các lời gọi count thông thường dùng cơ chế dựa trên **countDocuments** kể cả khi không có transaction.

**Không dùng estimated collection statistics để quyết định nghiệp vụ đòi một snapshot transaction.**

### 12.2. Near operator và transaction

Tài liệu Spring Data về **Special behavior inside transactions** lưu ý các bộ lọc đếm dùng $near/$nearSphere phải dùng $geoWithin với $center/$centerSphere ở đường aggregation count.

Điều này **không đồng nghĩa mọi truy vấn geospatial bị cấm trong mọi transaction**. Phân biệt command, toán tử, stage, server version và transaction topology.

### 12.3. Không tạo geospatial index trong transaction nghiệp vụ

Tạo collection/index qua migration trước khi phục vụ request. Hỗ trợ DDL trong transaction có điều kiện theo MongoDB version và topology; không đặt lệnh tạo index vào read/write business transaction.

### 12.4. Read-only transaction cũng có chi phí

MongoTransactionManager có thể bắt đầu transaction khi method dùng **@Transactional(readOnly=true)**. Nó không tự làm query rẻ hơn hoặc bỏ qua các ràng buộc read concern/read preference.

## 13. Count và danh sách có thể khác nhau khi chạy hai lệnh

~~~text
T0: count theo bán kính -> total=10
T1: một cửa hàng trong bán kính bị chuyển ra ngoài
T2: find theo bán kính -> 9 cửa hàng
~~~

Đây có thể là kết quả bình thường nếu hai lệnh độc lập không dùng cùng một snapshot. **total=10** và **items khớp 9** không tự chứng minh geospatial filter sai.

| Yêu cầu | Hướng xử lý |
| --- | --- |
| UI tìm nơi gần, dữ liệu được phép thay đổi | Hai query độc lập có thể chấp nhận |
| API muốn count và items nhất quán trong một lần đọc | Một aggregation/snapshot phù hợp |
| Nghiệp vụ nhiều document writes cần cùng commit | Transaction ngắn, guards và retry phù hợp |

### 13.1. Transaction và read concern

**@Transactional** không bảo đảm vô điều kiện mọi kiểu đọc có một snapshot giống nhau trên mọi topology. Khi cần snapshot, cấu hình transaction read concern và test với deployment thực.

### 13.2. $facet

Nếu filter địa lý dùng $geoWithin trong $match, một pipeline **$facet** có thể trả nhánh items (sort/skip/limit) và nhánh totals ($count) từ cùng input. Tuy nhiên facet có giới hạn memory và BSON output size; không mặc định dùng cho mọi collection lớn.

### 13.3. Không quên authorization

Trong transaction hoặc facet, tenant filter vẫn bắt buộc. Nếu nhánh items lọc tenant nhưng nhánh total không lọc, số total có thể tiết lộ dữ liệu tenant khác.

## 14. $geoNear là một aggregation stage đặc biệt

MongoDB **$geoNear** tính khoảng cách tới các document và phát kết quả theo thứ tự gần đến xa:

~~~javascript
db.stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: {
        tenantId: "shop-a",
        active: true
      }
    }
  },
  { $limit: 20 },
  {
    $project: {
      name: 1,
      distanceMeters: 1
    }
  }
]);
~~~

Ba điểm quan trọng:

1. **$geoNear phải là stage đầu tiên** trong pipeline thông thường.
2. **key** chọn field có geospatial index (quan trọng nếu có nhiều geospatial indexes).
3. Filter tenant/active nằm trong **query** của $geoNear; không đặt $match trước $geoNear.

### 14.1. Vì sao không viết $match trước?

~~~javascript
// Sai cấu trúc: không đặt $match trước $geoNear.
[
  { $match: { tenantId: "shop-a" } },
  { $geoNear: { /* ... */ } }
]
~~~

MongoDB yêu cầu $geoNear đứng đầu. Đưa các điều kiện thường như tenant/active vào thuộc tính query của $geoNear để giới hạn candidate khi có thể.

### 14.2. $geoNear trong transaction?

Aggregation nói chung được MongoDB hỗ trợ trong transactions, nhưng có **danh sách stages không được phép** và điều kiện riêng theo server version. Không phát biểu tuyệt đối rằng $geoNear luôn bị cấm trong transaction hay luôn được phép trong mọi workload.

Kiểm chứng trên deployment thực:

- Geospatial index hợp lệ và $geoNear là stage đầu.
- Pipeline không chứa stage bị cấm trong transaction.
- Transaction read concern, read preference, cursor lifecycle phù hợp.
- Phiên bản MongoDB Server/driver/Spring Data hỗ trợ cách thực hiện.
- Integration test dùng replica set/sharded test deployment.

### 14.3. $near không phải $geoNear

$near/$nearSphere là **query match execution operators**, không được nhét trực tiếp vào $match của aggregation pipeline. Muốn aggregation nearest, sử dụng **$geoNear** stage.

## 15. $geoNear + $count: một lựa chọn khác

Khi cần dùng **chính semantics của geoNear** để lọc theo min/max distance, có thể để $geoNear phát kết quả rồi đếm:

~~~javascript
db.stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      key: "location",
      distanceField: "distanceMeters",
      minDistance: 500,
      maxDistance: 2000,
      spherical: true,
      query: {
        tenantId: "shop-a",
        active: true
      }
    }
  },
  { $count: "total" }
]);
~~~

Đây là một **aggregation** với $geoNear stage, không phải countDocuments nhận $near predicate. Nó có thể phải tính khoảng cách trên nhiều candidates trước khi count, nên cần benchmark so với $geoWithin count.

### 15.1. Khi nào hợp lý?

- Muốn count theo min/max distance nhất quán với geoNear semantics.
- Vùng sát boundary quan trọng và đã kiểm thử hình học.
- Index phù hợp và chi phí pipeline chấp nhận được.

### 15.2. Không giới hạn trước khi tính tổng

~~~javascript
[
  { $geoNear: { /* ... */ } },
  { $limit: 20 },
  { $count: "total" }
]
~~~

Pipeline này chỉ đếm **tối đa 20** phần tử do $limit trước $count, không phải total của toàn vùng.

### 15.3. Không dựa vào default limit cũ

MongoDB hiện hành không mặc định giới hạn $geoNear ở 100 như một số tài liệu cũ. Với API danh sách, **đặt $limit rõ**; với count toàn vùng, hiểu rõ chi phí thực thi.

## 16. Một pipeline $facet: items và total

Với filter $geoWithin, có thể dùng $facet trả trang và tổng trong một lần aggregation:

~~~javascript
const radius = 2000 / 6371008.8;

db.stores.aggregate([
  {
    $match: {
      tenantId: "shop-a",
      active: true,
      location: {
        $geoWithin: {
          $centerSphere: [
            [106.7009, 10.7769],
            radius
          ]
        }
      }
    }
  },
  {
    $facet: {
      items: [
        { $sort: { name: 1, _id: 1 } },
        { $skip: 20 },
        { $limit: 10 },
        { $project: { name: 1, location: 1 } }
      ],
      totals: [
        { $count: "total" }
      ]
    }
  }
]);
~~~

### 16.1. Filter trước $facet

Filter địa lý/tenant trước $facet giúp hai nhánh cùng nhìn tập đã giới hạn; nhánh items thêm sort/pagination, nhánh totals đếm toàn bộ tập.

### 16.2. Empty results

Nhánh totals có thể là **mảng rỗng**, không nhất thiết chứa total=0. DTO mapping phải xử lý empty totals.

### 16.3. Chi phí của $facet

$facet có giới hạn memory và BSON output, có thể xử lý nhiều candidates để tính total và đôi khi tăng latency. Không mặc định nó nhanh hơn hai query; cần đo với dữ liệu thực.

## 17. Khi nào geo query nên nằm trong transaction?

Một request chỉ đọc **mười cửa hàng gần nhất** thường **không cần multi-document transaction**. Transaction dành cho ranh giới nhất quán được xác định rõ.

Ví dụ luồng phân phối đơn hàng:

~~~text
1. Tìm các cửa hàng gần nhất.
2. Thử giữ hàng tại một cửa hàng.
3. Tạo reservation document.
4. Ghi movement và outbox event.
~~~

**Bước 2–4** có thể cần transaction để cùng commit/rollback. Nhưng việc cửa hàng đứng gần nhất không bảo đảm còn hàng hoặc được phép giữ tại thời điểm ghi.

### 17.1. Candidate query không thay conditional update

~~~javascript
db.stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      distanceField: "distanceMeters",
      maxDistance: 5000,
      key: "location",
      query: { tenantId: "shop-a", active: true }
    }
  },
  { $limit: 5 }
]);
~~~

Sau đó ở inventory service vẫn cần **conditional update stock>=quantity** cùng reservation transaction/state. Đừng trừ tồn bằng một số lượng dựa trên snapshot cũ mà thiếu điều kiện.

### 17.2. Transaction context

MongoTransactionManager dùng thread context trong imperative stack; ReactiveMongoTransactionManager dùng Reactor Context. Raw driver/session khác không tự tham gia một Spring transaction.

### 17.3. Tránh transaction kéo dài

Một geo search dài bên trong transaction có thể giữ snapshot, session và cursor. Đừng giữ transaction mở qua HTTP response streaming hoặc trong lúc chờ client nếu không có yêu cầu nhất quán rõ ràng.

### 17.4. Count không thay business guard

Điều kiện “count cửa hàng trong bán kính >=1” không bảo đảm một Store vẫn có đủ hàng/đang mở khi bước reserve chạy; ghi cần kiểm tra lại trạng thái/version tại thời điểm update.

## 18. ReactiveMongoTemplate: count trả Mono, find trả Flux

Reactive MongoDB access không bắt buộc tải toàn bộ kết quả vào List. Thay vào đó:

| Imperative API | Reactive API |
| --- | --- |
| MongoTemplate.count(query, class) → long | ReactiveMongoTemplate.count(query, class) → Mono<Long> |
| MongoTemplate.find(query, class) → List<T> | ReactiveMongoTemplate.find(query, class) → Flux<T> |
| MongoTemplate.geoNear(nearQuery, class) → GeoResults<T> | ReactiveMongoTemplate.geoNear(nearQuery, class) → Flux<GeoResult<T>> |
| MongoTemplate.aggregate(...) → AggregationResults<T> | ReactiveMongoTemplate.aggregate(...) → Flux<T> |

Đây là khác biệt về API contract và lifecycle, không phải MongoDB Server đổi toán tử geospatial.

### 18.1. Reactive service đếm trong bán kính

~~~java
package com.example.geosearch;

import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveStoreCountService {

    private static final double EARTH_RADIUS_METERS = 6_371_008.8;
    private final ReactiveMongoTemplate template;

    public ReactiveStoreCountService(
            ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Long> countWithin(
            String authenticatedTenantId,
            double longitude, double latitude,
            double radiusMeters) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || !Double.isFinite(longitude)
                || longitude < -180 || longitude > 180
                || !Double.isFinite(latitude)
                || latitude < -90 || latitude > 90
                || !Double.isFinite(radiusMeters)
                || radiusMeters <= 0 || radiusMeters > 50_000) {
            return Mono.error(
                new IllegalArgumentException("Invalid search"));
        }

        Circle circle = new Circle(
            new Point(longitude, latitude),
            radiusMeters / EARTH_RADIUS_METERS
        );

        Query query = Query.query(
            Criteria.where("tenantId")
                .is(authenticatedTenantId)
                .and("active").is(true)
                .and("location").withinSphere(circle)
        );

        return template.count(query, StoreDocument.class);
    }
}
~~~

**Mono<Long>** chỉ phát ra số lượng khi Publisher được subscribe và truy vấn hoàn tất. Nếu query lỗi, nó phát **error signal**, không tự chuyển thành Mono.just(0).

### 18.2. Không block trên WebFlux event loop

~~~java
// Không nên:
long total = reactiveStoreCountService
    .countWithin(tenant, lon, lat, meters)
    .block();
~~~

Blocking có thể làm nghẽn event loop hoặc gây lỗi tại thread không cho phép blocking. Trả Mono tới controller hoặc compose với map/flatMap/zip.

### 18.3. Không tự subscribe trong service

~~~java
// Không nên:
Mono<Long> total = template.count(query, StoreDocument.class);
total.subscribe(value -> log.info("Total: {}", value));
return total;
~~~

Đoạn trên có thể tạo **hai lần subscription và hai lệnh đếm**: một lần từ subscribe thủ công, một lần khi WebFlux subscribe vào Mono được trả ra. Để log trong cùng pipeline, dùng **doOnNext** mà không subscribe riêng.

### 18.4. Lỗi phải được giữ nguyên nghĩa

Không dùng:

~~~java
return template.count(query, StoreDocument.class)
    .onErrorReturn(0L);
~~~

để che mọi lỗi database thành “không có cửa hàng”. Một lỗi timeout/authorization/index khác hoàn toàn với tập kết quả rỗng. Nếu API cần fallback, phải có policy rõ, log/metrics và response không gây hiểu nhầm.

## 19. Reactive geoNear: Flux<GeoResult<T>>

Với Spring Data MongoDB ReactiveMongoTemplate:

~~~java
Flux<GeoResult<StoreDocument>> nearby =
    reactiveMongoTemplate.geoNear(
        nearQuery, StoreDocument.class);
~~~

Mỗi **GeoResult<T>** chứa content là entity đã ánh xạ, và Distance là khoảng cách tương ứng với metric của NearQuery.

### 19.1. Dùng NearQuery và units rõ ràng

~~~java
package com.example.geosearch;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class ReactiveNearestStoreService {

    private final ReactiveMongoTemplate template;

    public ReactiveNearestStoreService(
            ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<GeoResult<StoreDocument>> findNearby(
            double longitude, double latitude,
            double radiusKilometers) {

        if (!Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -90 || latitude > 90
                || !Double.isFinite(radiusKilometers)
                || radiusKilometers <= 0
                || radiusKilometers > 50) {
            return Flux.error(
                new IllegalArgumentException("Invalid search"));
        }

        GeoJsonPoint center =
            new GeoJsonPoint(longitude, latitude);

        NearQuery near = NearQuery.near(
                center, Metrics.KILOMETERS)
            .maxDistance(
                new Distance(radiusKilometers, Metrics.KILOMETERS))
            .limit(20);

        return template.geoNear(near, StoreDocument.class);
    }
}
~~~

**Ví dụ trên tập trung vào units/API**, chưa áp tenant/active filter. Với hệ thống nhiều tenant, bắt buộc thêm filter tenant vào NearQuery hoặc dùng aggregation $geoNear.query ở server. Không dùng kết quả unscoped này trong API cho người dùng thật.

### 19.2. Khoảng cách phụ thuộc kiểu Point

Javadoc NearQuery nhấn mạnh:

- **Point** legacy có thể dẫn tới semantics khoảng cách theo **radians** với cấu hình neutral.
- **GeoJsonPoint** dùng đơn vị **meters** ở biểu diễn MongoDB GeoJSON.
- Đặt **Metric** (ví dụ Metrics.KILOMETERS) giúp NearQuery tính/hiển thị khoảng cách với unit rõ ràng.

Không copy literal maxDistance giữa hai mẫu Point và GeoJsonPoint mà bỏ qua loại tọa độ và metric.

### 19.3. Đọc distance

~~~java
return reactiveTemplate.geoNear(
        near, StoreDocument.class)
    .map(geo -> new StoreDistanceView(
        geo.getContent().id(),
        geo.getContent().name(),
        geo.getDistance().getValue()
    ));
~~~

StoreDistanceView là DTO ứng dụng cần định nghĩa. Nếu NearQuery trả distance theo kilometers, property DTO nên đặt **distanceKilometers**, không để client tự đoán đơn vị.

### 19.4. Thêm tenant filter vào NearQuery

NearQuery có API query(Query) để thêm điều kiện thông thường:

~~~java
Query scopedFilter = Query.query(
    Criteria.where("tenantId").is(tenant)
        .and("active").is(true)
);

NearQuery scopedNear = NearQuery
    .near(new GeoJsonPoint(lon, lat), Metrics.KILOMETERS)
    .maxDistance(new Distance(2, Metrics.KILOMETERS))
    .query(scopedFilter)
    .limit(20);
~~~

Tenant phải do authentication/authorization xác định, không tin nguyên giá trị client tự khai.

## 20. Reactive repository methods cho geospatial

Spring Data MongoDB reactive repositories hỗ trợ derived geospatial queries, bao gồm các return types:

~~~java
package com.example.geosearch;

import org.bson.types.ObjectId;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveStoreRepository
        extends ReactiveMongoRepository<StoreDocument, ObjectId> {

    Flux<StoreDocument> findByLocationNear(
        Point point, Distance distance);

    Flux<GeoResult<StoreDocument>> findByLocationNear(
        Point point, Distance distance,
        org.springframework.data.domain.Pageable pageable);
}
~~~

Hai overload minh họa entity Flux và GeoResult Flux; kiểm tra method resolution, parameter order và tên field theo Spring Data version thực tế. Trong hệ thống nhiều tenant nên dùng method derived có **TenantId/Active** hoặc Template với filter đầy đủ.

### 20.1. Reactive không trả GeoPage/GeoResults

**GeoResults<T>** ở stack đồng bộ chứa tập GeoResult và có khả năng tính aggregate information như average distance. **GeoPage<T>** là wrapper theo kiểu eager pageable result.

Tài liệu Spring Data MongoDB nêu rõ reactive geospatial queries **không hỗ trợ GeoResults/GeoPage return types** vì không phù hợp với deferred streaming semantics. Reactive API vẫn hỗ trợ **Flux<GeoResult<T>>** và entity Flux.

### 20.2. Pageable vẫn được hỗ trợ

Không hỗ trợ GeoPage **không đồng nghĩa không phân trang**. Reactive derived query có thể nhận **Pageable** để truyền sort/skip/limit xuống database, nhưng return type vẫn là Flux.

### 20.3. Không có Mono<Page> cho repository reactive

Nếu API muốn totalPages, service phải lấy content và count riêng, hoặc một aggregation trả cả hai. Mono<Page<T>> không phải return type Spring Data reactive repository hỗ trợ tự động như Page ở blocking repository.

### 20.4. Không trộn GeoResult với GeoPage

GeoResult chỉ mô tả **một item + distance**. Muốn average distance trong một trang, có thể tính trên **tập hữu hạn** với giới hạn số bản ghi; muốn aggregate toàn vùng, thiết kế pipeline aggregation riêng phù hợp.

## 21. Reactive paging và total: compose Mono.zip

Với geoWithin, có thể chạy một Flux find và một Mono count:

~~~java
import java.util.List;
import org.springframework.data.geo.Circle;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Mono;

public record StorePageResponse(
    List<StoreDocument> items,
    long total,
    int page,
    int size
) {}

public Mono<StorePageResponse> searchPage(
        String tenant, Circle circle,
        int page, int size) {

    if (tenant == null || tenant.isBlank()
            || circle == null
            || page < 0 || size <= 0 || size > 100) {
        return Mono.error(
            new IllegalArgumentException("Invalid page"));
    }

    Query pageQuery = Query.query(
        Criteria.where("tenantId").is(tenant)
            .and("active").is(true)
            .and("location").withinSphere(circle)
    );

    pageQuery.with(PageRequest.of(
        page, size,
        Sort.by("name").ascending()
            .and(Sort.by("_id"))
    ));

    Query countQuery = Query.query(
        Criteria.where("tenantId").is(tenant)
            .and("active").is(true)
            .and("location").withinSphere(circle)
    );

    Mono<List<StoreDocument>> items =
        reactiveTemplate.find(
            pageQuery, StoreDocument.class)
            .collectList();

    Mono<Long> count = reactiveTemplate.count(
        countQuery, StoreDocument.class);

    return Mono.zip(items, count)
        .map(tuple -> new StorePageResponse(
            tuple.getT1(), tuple.getT2(),
            page, size
        ));
}
~~~

Đoạn này thuộc một service có field **ReactiveMongoTemplate reactiveTemplate** được inject; StorePageResponse là một public record nên cần nằm trong source file riêng.

### 21.1. collectList có giới hạn?

Có, bởi find được giới hạn **size<=100**. Không dùng collectList trên Flux trả toàn bộ cửa hàng của một quốc gia hoặc một change stream vô hạn.

### 21.2. Mono.zip và nhất quán

Mono.zip compose hai Publisher, nhưng **không tự tạo transaction hoặc snapshot**. Count và find có thể được gửi thành hai lệnh MongoDB độc lập; dữ liệu có thể thay đổi giữa chúng.

### 21.3. Nếu chỉ muốn hasNext

Lấy size+1 kết quả với upper bound phù hợp, trả tối đa size và cờ hasNext. Điều đó tránh count nhưng vẫn cần hiểu offset paging khi dữ liệu thay đổi.

### 21.4. Empty count

ReactiveMongoTemplate.count thường phát **Mono<Long>** với 0 khi không có document thỏa điều kiện; khác với custom $count aggregation có thể trả **Flux.empty()** khi input rỗng. Không áp một chính sách xử lý empty duy nhất cho mọi API.

## 22. Reactive transaction: dùng Reactor Context

Khi cần transaction reactive, dùng **ReactiveMongoTransactionManager**:

~~~java
package com.example.geosearch;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTxConfiguration {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager reactiveTxManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

Transaction context reactive đi theo Publisher/Subscriber context, khác với imperative session theo thread của MongoTransactionManager.

### 22.1. TransactionalOperator

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

TransactionalOperator operator =
    TransactionalOperator.create(
        reactiveMongoTransactionManager);

Mono<StorePageResponse> result =
    searchPage(tenant, circle, 0, 20)
        .as(operator::transactional);
~~~

Đây là cấu hình minh họa một transaction bao cả pipeline. Chỉ nên dùng khi yêu cầu consistency/transaction options được xác định; không bật transaction chỉ vì query là geospatial.

### 22.2. Không block hoặc subscribe tách nhánh

~~~java
// Sai về quản lý transaction reactive.
Mono<Long> count = reactiveTemplate.count(
    countQuery, StoreDocument.class);

count.subscribe();  // Subscription riêng, ngoài chain được trả về.

return reactiveTemplate.find(pageQuery, StoreDocument.class);
~~~

Những subscription riêng không mặc nhiên cùng reactive transaction context và có thể khiến count chạy ngoài lifecycle của request.

### 22.3. Không trộn MongoTemplate đồng bộ vào reactive transaction

Một lời gọi MongoTemplate từ boundedElastic hoặc thread khác không tự tham gia session được ReactiveMongoTransactionManager quản lý. Khi cần atomicity, dùng reactive operations trong **một chain** và đúng manager.

### 22.4. readOnly có nghĩa gì?

Spring Data có thể bắt đầu transaction ngay cả với @Transactional(readOnly=true) trong reactive stack. Không suy rằng readOnly tắt session hoặc mọi query sẽ chạy trên secondary.

## 23. Tốc độ không chỉ phụ thuộc Flux

Reactive I/O giúp không giữ một thread blocking cho mỗi request đang chờ mạng, nhưng **không biến phép tìm geospatial nặng thành rẻ**.

### 23.1. Những nguồn chi phí

- Số document khớp vùng rộng.
- Hiệu quả geospatial index/compound filter.
- Số lần round trip (items + total).
- Việc tính khoảng cách, sort và skip.
- Số lượng item mapper/projection phải convert.
- Kích thước trang, giới hạn concurrency.
- Transaction/session/snapshot overhead.
- MongoDB server saturation và network latency.

### 23.2. Backpressure không phải index

Flux có backpressure trong reactive processing, nhưng MongoDB vẫn cần chọn/truy xuất candidates bằng query plan. Backpressure không sửa một filter không dùng được index, và không đảm bảo database chỉ scan đúng số rows subscriber yêu cầu trong mọi truy vấn.

### 23.3. Bounded resources

Với API nearest:

~~~java
NearQuery near = NearQuery
    .near(new GeoJsonPoint(lon, lat), Metrics.KILOMETERS)
    .maxDistance(new Distance(3, Metrics.KILOMETERS))
    .limit(30);
~~~

Giới hạn radius **và** limit giúp kiểm soát data exposure và chi phí. Với API toàn bộ vùng theo geoWithin, thêm pagination và caps tương tự.

### 23.4. Cancellation không phải rollback dữ liệu

Client hủy subscription có thể làm pipeline ngừng xử lý, nhưng không được coi mọi server work trước đó đã được rollback, đặc biệt nếu cùng request có write side effects. Geo search chỉ đọc thường ít rủi ro hơn, nhưng deadline/cancellation vẫn cần monitoring.

## 24. Index, query plan và chi phí count geospatial

Đúng công thức count chưa đủ; hiệu năng phụ thuộc index, số documents được xem xét và cách server thực thi filter.

### 24.1. 2dsphere index phải tồn tại thật

~~~javascript
db.stores.getIndexes();
~~~

Nếu không có index địa lý tương thích, các query như $near/$geoNear có thể thất bại vì thiếu geospatial index. **@GeoSpatialIndexed** chỉ là metadata Java, không đảm bảo collection đã có index nếu cơ chế tạo index không được bật.

### 24.2. Đọc executionStats

~~~javascript
const withinQuery = {
  tenantId: "shop-a",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7009, 10.7769],
        2000 / 6371008.8
      ]
    }
  }
};

db.stores.find(withinQuery)
  .explain("executionStats");
~~~

Nhìn các thông tin như index được chọn, documents/keys examined, số document trả ra, thời gian và query plan. Nếu query scan nhiều document rồi lọc ở bộ nhớ, cần phân tích index/filter/geometry thay vì chỉ tăng threads.

### 24.3. Không dùng estimatedDocumentCount thay filter

estimatedDocumentCount có thể rẻ nhưng không lọc tenant, active và radius. Một con số nhanh nhưng **không cùng semantics** không phải tối ưu đúng.

### 24.4. Geospatial index không phải covered query thông thường

Geospatial index có hạn chế về covered queries. Không mặc định projection chỉ _id/name có thể luôn đọc hoàn toàn từ index; xác nhận bằng explain và server docs.

### 24.5. Sort và skip

Query $near vốn có thứ tự theo khoảng cách. Thêm sort khác có thể tăng sorting overhead; offset paging với skip lớn thường tốn chi phí. Đánh giá giới hạn số trang và một cursor/snapshot policy phù hợp.

### 24.6. Compound index không chữa mọi query

Một compound index có tenantId, active và location 2dsphere có thể phù hợp cho một dạng workload. Nhưng thứ tự field, phần geospatial và cardinality không tự tối ưu; đo trên dữ liệu thật trước khi giữ nhiều indexes khiến mỗi write phải cập nhật thêm.

### 24.7. Partial index

Nếu chỉ index Store active, query muốn sử dụng partial index phải có filter tương thích với predicate của index. Một count bao gồm mọi Store có thể có plan khác hoặc không dùng được partial index.

### 24.8. Sharding

MongoDB không dùng geospatial index làm shard key, nhưng có thể có geospatial index trên sharded collection với shard key khác. Thiết kế shard key theo workload và kiểm chứng chi phí geo query xuyên shard.

## 25. Hình học và đơn vị khoảng cách

| Dữ liệu/thao tác | Đơn vị/ý nghĩa |
| --- | --- |
| GeoJSON Point.coordinates | [longitude, latitude] tính theo độ |
| $near với GeoJSON + maxDistance | Meters |
| $geoNear với GeoJSON + min/maxDistance | Meters |
| $centerSphere radius | Radians |
| Distance(2, Metrics.KILOMETERS) | Hai km ở tầng Spring Data |
| Legacy Point với NearQuery neutral | Có thể dùng radians |
| 2dsphere index | Hình học cầu, dữ liệu hợp lệ |

### 25.1. Công thức đổi bán kính

Với bán kính xấp xỉ Trái Đất:

\[
\theta_{\mathrm{rad}}=\frac{d_{\mathrm{m}}}{R_{\mathrm{m}}}
\]

Trong đó **R khoảng 6.371.008,8 mét** là bán kính Trái Đất trung bình dùng trong ví dụ. Với d=2.000 m, góc theta khoảng 0,0003139 radians.

Đây là approximation hình học cầu. Nếu nghiệp vụ đòi đo đạc trắc địa rất chính xác, cần chọn phương pháp/hệ tọa độ phù hợp và hiểu giới hạn của hình học được dùng.

### 25.2. Điểm sát boundary

Với cửa hàng ở 1.999,999 m và 2.000,001 m, kết quả có thể chịu ảnh hưởng floating-point, radius conversion và hình học. Test fixture nên có các điểm **xa ranh giới đủ lớn**, sau đó thêm boundary tests theo chính sách nghiệp vụ.

### 25.3. Cực và kinh tuyến 180 độ

Polygon/vùng tròn gần cực hoặc cắt kinh tuyến ±180 độ cần spherical geometry đúng. Không đổi thành bounding box phẳng với longitude >= min AND <= max mà bỏ qua wrap-around.

### 25.4. Kiểu dữ liệu tọa độ

~~~json
{"coordinates":["106.7009","10.7769"]}
~~~

Đây là **chuỗi**, không phải các số GeoJSON Point mong đợi. Validate input và tránh để client formatting biến số thành chuỗi.

### 25.5. So sánh distance từ hai nguồn

NearQuery có thể trả Distance ở kilometers, còn $geoNear raw BSON với GeoJSON tính distanceMeters. Nếu gom kết quả từ hai đường query, phải chuẩn hóa đơn vị trước khi sort/hiển thị.

## 26. Quyền riêng tư và multi-tenant trong geo query

Tọa độ của người dùng hoặc địa điểm nhạy cảm có thể là dữ liệu cá nhân. Dù ví dụ là tìm cửa hàng, service cần:

- Chỉ thu thập tọa độ khi có mục đích và quyền hợp lệ.
- Validate range, radius, số lượng yêu cầu và kích thước response.
- Không lưu toàn bộ lịch sử vị trí người dùng vào logs nếu không cần.
- Trả tọa độ cửa hàng theo chính sách công bố của doanh nghiệp.
- Áp **tenant/authorization filter** cho cả count và items.
- Tránh cache response có dữ liệu tenant A cho tenant B.
- Có cơ chế rate-limit/abuse prevention cho truy vấn tọa độ quá chi tiết.

### 26.1. Chỉ trả một count vẫn có thể tiết lộ thông tin

Một API không hiển thị điểm nào, nhưng trả số địa điểm nhạy cảm trong bán kính 10 m theo nhiều tâm khác nhau, vẫn có thể cho phép suy ra vị trí từ nhiều phép đo. Cân nhắc bán kính tối thiểu, precision, ngưỡng công bố và giới hạn tần suất theo use case.

### 26.2. Tenant phải do server xác thực

~~~java
Criteria.where("tenantId").is(authenticatedTenantId)
    .and("active").is(true)
    .and("location").withinSphere(circle);
~~~

Không coi tenantId client gửi qua query parameter là bằng chứng có quyền đọc. Authorization và data-scoping là phần của security boundary.

### 26.3. Query telemetry không cần lịch sử vị trí chính xác

Có thể log requestId, loại truy vấn, band bán kính, duration, error code, số kết quả, và tenant được bảo vệ. Không mặc định lưu toàn bộ tọa độ của từng người dùng mãi mãi.

## 27. Chiến lược integration test

Tối thiểu cần kiểm tra:

| Test case | Kỳ vọng |
| --- | --- |
| Cửa hàng ở đúng center | Có trong bán kính dương |
| Cửa hàng cách center khoảng 100 m | Có trong 2 km |
| Cửa hàng cách center hơn 5 km | Không được đếm trong 2 km |
| Store khác tenant ngay cạnh center | Không được đếm |
| Store inactive ngay cạnh center | Không được đếm |
| Không có document phù hợp | Count = 0 |
| Longitude/latitude ngoài khoảng hợp lệ | Bị từ chối trước DB |
| Radius âm, NaN, vô hạn | Bị từ chối |
| $geoWithin count so với near search | Thống nhất với fixture xa boundary |
| minDistance + maxDistance | Đúng tập trong vành khăn |
| $geoNear | GeoResult có distance và sort gần–xa |
| Reactive count | Mono<Long> phát đúng số |
| Reactive geoNear | Flux<GeoResult<T>> phát đúng |
| Transaction count trên replica set | Không lỗi near-in-count và đúng dữ liệu theo policy |
| Query count và find giữa concurrent writes | Response phù hợp contract về consistency |
| Mất index | Test/migration phát hiện và sửa được |

### 27.1. Vì sao mock chưa đủ?

Unit test với MongoTemplate mock chỉ chứng minh service đã xây Criteria hoặc gọi count. Nó **không chứng minh** MongoDB thực thi 2dsphere, radius radians, query rewrite, cursor và transaction đúng.

### 27.2. Seed điểm đủ xa ranh giới

~~~text
Center: (106.7009, 10.7769)
Near:   (106.7019, 10.7769)  — cách khoảng một trăm mét
Far:    (106.7609, 10.7769)  — cách nhiều km
~~~

Các con số là fixture minh họa, không phải phép đo trắc địa chính xác đến mét. Test assert near nằm trong bán kính 2 km và far ngoài, tránh phụ thuộc floating-point tại boundary.

### 27.3. MongoDB dành cho test

Count/near integration tests cần MongoDB test instance và geospatial index. Multi-document transaction tests cần replica set hoặc deployment tương thích. Không chạy fixture tạo/xóa dữ liệu của bài trên production.

### 27.4. Chia test theo tầng

1. **Unit test:** validate radius/coordinates, conversion meters→radians.
2. **Integration:** index, find/count, raw MongoDB geometry.
3. **Transaction integration:** read/count trong MongoDB transaction session.
4. **Reactive integration:** Mono/Flux/StepVerifier, error/cancellation behavior.
5. **Performance test:** explain/stats với dữ liệu và workload gần production.

## 28. Integration test đồng bộ: count và near cùng filter

Một bài test trực tiếp MongoDB giúp phát hiện sai radius, sai tenant và index thiếu.

~~~java
package com.example.geosearch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(StoreRadiusCountService.class)
class StoreRadiusCountIntegrationTest {

    @Autowired MongoTemplate template;
    @Autowired StoreRadiusCountService countService;

    @BeforeEach
    void ensureGeoIndex() {
        template.getCollection("stores")
            .createIndex(new Document("location", "2dsphere"));
    }

    @Test
    void countsOnlyActiveStoresOfAuthenticatedTenant() {
        String tenant = "TEST-" + UUID.randomUUID();
        String otherTenant = "TEST-" + UUID.randomUUID();

        StoreDocument center = new StoreDocument(
            new ObjectId(), tenant, "CENTER", true,
            new GeoJsonPoint(106.7009, 10.7769));
        StoreDocument near = new StoreDocument(
            new ObjectId(), tenant, "NEAR", true,
            new GeoJsonPoint(106.7019, 10.7769));
        StoreDocument far = new StoreDocument(
            new ObjectId(), tenant, "FAR", true,
            new GeoJsonPoint(106.7609, 10.7769));
        StoreDocument wrongTenant = new StoreDocument(
            new ObjectId(), otherTenant, "OTHER", true,
            new GeoJsonPoint(106.7009, 10.7769));
        StoreDocument inactive = new StoreDocument(
            new ObjectId(), tenant, "INACTIVE", false,
            new GeoJsonPoint(106.7009, 10.7769));

        List<StoreDocument> fixtures = List.of(
            center, near, far, wrongTenant, inactive);
        List<ObjectId> ids = fixtures.stream()
            .map(StoreDocument::id)
            .toList();

        template.insertAll(fixtures);

        try {
            long total = countService.countWithin(
                tenant, 106.7009, 10.7769, 2_000);
            assertThat(total).isEqualTo(2L);

            Query nearQuery = Query.query(
                Criteria.where("tenantId").is(tenant)
                    .and("active").is(true)
                    .and("location")
                    .near(new GeoJsonPoint(106.7009, 10.7769))
                    .maxDistance(2_000)
            );

            List<StoreDocument> found = template.find(
                nearQuery, StoreDocument.class);

            assertThat(found)
                .extracting(StoreDocument::name)
                .containsExactlyInAnyOrder("CENTER", "NEAR");

            assertThat(countService.countWithin(
                tenant, 107.5, 11.5, 100))
                .isZero();

        } finally {
            template.remove(
                Query.query(Criteria.where("_id").in(ids)),
                StoreDocument.class);
        }
    }

    @Test
    void rejectsBadLocationWithoutSendingCount() {
        assertThatThrownBy(() ->
            countService.countWithin(
                "shop-a", 999, 10, 2_000))
            .isInstanceOf(IllegalArgumentException.class);

        assertThatThrownBy(() ->
            countService.countWithin(
                "shop-a", 106, 10, Double.NaN))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

### 28.1. Vì sao test cần index?

Các query geospatial cần index tương ứng, đặc biệt nearest search. Nếu test chỉ mock repository hoặc không tạo 2dsphere index, kết quả không phản ánh production. Hãy đảm bảo fixture/test database có index trước khi chạy query.

### 28.2. Vì sao compare count và near?

Các fixture không sát boundary nên hai cách chọn tập:

- $near trong phạm vi tối đa 2 km.
- $geoWithin vùng cầu 2 km.

đều phải chọn đúng **CENTER + NEAR** và loại FAR. Nếu count sai vì thiếu tenant, sai units hoặc dùng radius 2.000 radians, test dễ phát hiện.

### 28.3. Không đòi một thứ tự tuyệt đối khi distance bằng nhau

Trong test trên chỉ so sánh tập tên, vì mục tiêu là filter/count. Nếu muốn kiểm thử sort theo distance, thêm các điểm có khoảng cách khác rõ rệt, kiểm tra thứ tự được trả về và xem tie-breaker khi khoảng cách bằng nhau.

### 28.4. Cấu hình test

Test cần MongoDB test database, Spring Boot Data MongoDB test slice, JUnit 5 và AssertJ. Ví dụ không tự tạo container để tập trung vào nghiệp vụ; dự án có thể cấu hình kết nối tới MongoDB Testcontainers hoặc một server test khác.

**Không chạy bài test trên production**, không dùng ID/tenant của người dùng thật và phải dọn fixture đúng phạm vi.

## 29. Integration test transaction với replica set

Muốn chứng minh **count geospatial chạy trong MongoDB transaction**, hãy có một test riêng với replica set thật, ví dụ Testcontainers MongoDB.

### 29.1. Service transactional

~~~java
package com.example.geosearch;

import org.springframework.data.geo.Circle;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransactionalGeoCountService {

    private final MongoTemplate template;

    public TransactionalGeoCountService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager")
    public long insertAndCount(
            StoreDocument newStore, Circle searchArea) {

        template.insert(newStore);

        Query query = Query.query(
            Criteria.where("tenantId").is(newStore.tenantId())
                .and("active").is(true)
                .and("location").withinSphere(searchArea)
        );

        return template.count(query, StoreDocument.class);
    }
}
~~~

Vì service dùng **MongoTemplate cùng MongoDatabaseFactory** với transaction manager, thao tác insert và count cùng transaction khi service được gọi qua Spring proxy đúng cách.

### 29.2. Testcontainers replica set

~~~java
package com.example.geosearch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
@Import(MongoTxConfiguration.class)
class TransactionalGeoCountTest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl);
    }

    @Autowired MongoTemplate template;
    @Autowired TransactionalGeoCountService service;

    @Test
    void countInsideTransactionCanSeeOwnInsertedStore() {
        template.getCollection("stores")
            .createIndex(new Document("location", "2dsphere"));

        String tenant = "TEST-" + UUID.randomUUID();
        StoreDocument store = new StoreDocument(
            new ObjectId(),
            tenant,
            "TX-STORE",
            true,
            new GeoJsonPoint(106.7009, 10.7769)
        );

        Circle circle = new Circle(
            new Point(106.7009, 10.7769),
            2000.0 / 6371008.8
        );

        try {
            long inTransaction =
                service.insertAndCount(store, circle);

            assertThat(inTransaction).isEqualTo(1L);

            long afterCommit = template.count(
                Query.query(
                    Criteria.where("_id").is(store.id())
                ),
                StoreDocument.class
            );
            assertThat(afterCommit).isEqualTo(1L);
        } finally {
            template.remove(
                Query.query(
                    Criteria.where("_id").is(store.id())
                ),
                StoreDocument.class
            );
        }
    }
}
~~~

Mẫu này giả định ứng dụng có một Spring Boot application được component scanning bao phủ service cùng package, dependency Testcontainers MongoDB và Docker trong môi trường test. Kiểm tra các package/API Testcontainers theo version dùng trong dự án.

### 29.3. Vì sao tạo index bên ngoài transaction?

Không đưa createIndex vào method insertAndCount. Index/schema cần được tạo trước khi transaction bắt đầu, vừa tránh hạn chế về DDL vừa giúp test phân biệt lỗi index với lỗi count.

### 29.4. Test này chứng minh điều gì?

Service trong transaction:

1. Insert một Store.
2. Đếm bằng geoWithin trong cùng MongoDB transaction.
3. Trả số 1 theo fixture cô lập.
4. Commit.
5. Test bên ngoài thấy document đã được ghi.

**Nó chưa chứng minh tất cả những read concerns/snapshot choices**, cũng chưa kiểm thử transaction abort/retry hoặc nearest filter trong transaction. Bổ sung test có chủ đích theo yêu cầu của hệ thống.

### 29.5. Nếu muốn kiểm tra rollback

Tạo service method ném một RuntimeException **sau** insert+count, rồi assert document không xuất hiện bên ngoài sau khi transaction abort. Test phải đi qua Spring proxy, không tự gọi method @Transactional bằng self-invocation.

### 29.6. Không dùng @Transactional trên test method một cách vô thức

Một transaction được test framework mở bên ngoài có thể khiến service chỉ tham gia vào transaction của test, che mất ranh giới commit thực của service. Test service transaction nên chủ động xác định transaction nào chịu trách nhiệm commit.

## 30. Reactive integration test bằng StepVerifier

Để chứng minh reactive count và geoNear dùng đúng publisher, tạo fixture bằng **ReactiveMongoTemplate** và test với StepVerifier.

~~~java
package com.example.geosearch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@DataMongoTest
@Import(ReactiveStoreCountService.class)
class ReactiveGeospatialIntegrationTest {

    @Autowired ReactiveMongoTemplate template;
    @Autowired ReactiveStoreCountService countService;

    @Test
    void reactiveCountAndGeoNearUseSameTestPoints() {
        String tenant = "TEST-" + UUID.randomUUID();

        StoreDocument near = new StoreDocument(
            new ObjectId(), tenant, "NEAR", true,
            new GeoJsonPoint(106.7009, 10.7769));
        StoreDocument far = new StoreDocument(
            new ObjectId(), tenant, "FAR", true,
            new GeoJsonPoint(106.7609, 10.7769));

        Query cleanup = Query.query(
            Criteria.where("_id").in(
                List.of(near.id(), far.id()))
        );

        Mono<Long> scenario = Mono.from(
                template.getCollection("stores")
                    .createIndex(
                        new Document("location", "2dsphere")))
            .then(template.insert(near))
            .then(template.insert(far))
            .then(countService.countWithin(
                tenant, 106.7009, 10.7769, 2_000));

        try {
            StepVerifier.create(scenario)
                .expectNext(1L)
                .verifyComplete();

            NearQuery nearQuery = NearQuery.near(
                    new GeoJsonPoint(106.7009, 10.7769),
                    Metrics.KILOMETERS)
                .maxDistance(
                    new Distance(2, Metrics.KILOMETERS))
                .query(Query.query(
                    Criteria.where("tenantId").is(tenant)
                        .and("active").is(true)))
                .limit(10);

            StepVerifier.create(
                template.geoNear(
                    nearQuery, StoreDocument.class))
                .assertNext(result -> {
                    assertThat(result.getContent().name())
                        .isEqualTo("NEAR");
                    assertThat(result.getDistance().getValue())
                        .isGreaterThanOrEqualTo(0d);
                })
                .verifyComplete();
        } finally {
            StepVerifier.create(
                template.remove(cleanup, StoreDocument.class))
                .expectNextCount(1)
                .verifyComplete();
        }
    }
}
~~~

### 30.1. Vì sao dùng Mono.from(createIndex)?

Lời gọi createIndex trên **reactive MongoCollection** trả một Publisher. Bằng Mono.from(...).then(...), test đảm bảo thao tác index được subscribe và hoàn tất trước khi insert/query, thay vì tạo Publisher rồi bỏ đi.

### 30.2. Test Mono count khác test Flux geoNear

- **Mono<Long>**: expectNext(1L), verifyComplete.
- **Flux<GeoResult<T>>**: assert từng GeoResult, verifyComplete hoặc dùng expectNextCount với fixture phù hợp.

Nếu Flux hoàn thành rỗng, assertNext sẽ thất bại; test giúp phát hiện sai filter, sai đơn vị hoặc không có index.

### 30.3. Không block và subscribe hai lần

Test không gọi block() và không tự gọi subscribe() ngoài StepVerifier. Mỗi StepVerifier tạo một subscription chịu trách nhiệm cho query của nó.

### 30.4. Cleanup sau lỗi

Đoạn finally thực hiện cleanup trên test database bằng Publisher và StepVerifier. Nếu test gặp lỗi tạo index trước khi insert, remove vẫn được phép chạy với các IDs chưa tồn tại. Không thực hiện cleanup này trên dữ liệu production.

### 30.5. Version và test slice

Một dự án reactive-only cần starter/driver reactive và Boot test auto-configuration tương ứng. Đối chiếu @DataMongoTest và API ReactiveMongoTemplate.getCollection với phiên bản đang chạy; Testcontainers có thể được dùng để tạo MongoDB test instance cô lập.

## 31. Bảng chẩn đoán khi count, transaction hoặc reactive trả sai

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| countDocuments báo lỗi với $near | $near/$nearSphere không dùng trực tiếp trong countDocuments | Dùng geoWithin count hoặc Spring Data rewrite được kiểm chứng |
| Đếm rất lớn dù chỉ cần 2 km | Đưa 2000 vào $centerSphere như radians | Chuyển meters sang radians |
| Tìm cửa hàng ở sai khu vực | Nhầm [lat,lon] với [lon,lat] | Validate và kiểm tra raw GeoJSON |
| $near/$geoNear báo thiếu index | Chưa tạo 2dsphere index thật | Migration/ensureIndex trong test |
| Count=0 nhưng find có hàng | Filter khác nhau, unit khác, mapping khác | So sánh tenant/active/radius/query BSON |
| Count khác số của trang | Count trên toàn vùng, trang có limit | Phân biệt total và page length |
| total=20 dù vùng có 500 item | $limit trước $count | Chuyển count trước limit hoặc tách nhánh |
| total và items khác khi có concurrent writes | Hai lệnh đọc độc lập, không cùng snapshot | Chấp nhận eventual view hoặc dùng snapshot/aggregation |
| estimatedCount khác count geospatial | Thống kê collection không áp filter | Không dùng estimatedCount cho bán kính |
| Vành khăn min/max bị sai | Chưa trừ vòng trong, boundary/units khác | geoWithin outer + $nor inner, test boundary |
| Spring Data count ra khác mong đợi sau nâng cấp | Geo near rewrite behavior thay đổi | Kiểm tra docs version và integration test |
| $geoNear báo stage position | Đặt $match trước $geoNear | Đưa $geoNear lên đầu, filter trong query |
| $geoNear dùng sai geospatial field | Có nhiều geospatial indexes, thiếu key | Chỉ định key đúng |
| $geoNear không trả distance | Chỉ dùng geoWithin hoặc projection bỏ distance | Dùng $geoNear và distanceField |
| Geo query chậm | Vùng rộng, index không phù hợp, sort/skip lớn | explain, caps, index review |
| Transaction count không chạy trên local | Standalone mongod | Test bằng replica set |
| Transaction count báo near restriction | $near trong aggregation-count helper | geoWithin với sphere/circle phù hợp |
| Transaction mở lâu rồi timeout | Kéo dài geo search/snapshot, HTTP streaming | Rút ngắn transaction |
| Transaction làm kết quả read inconsistent | Read concern/session không đúng assumption | Kiểm chứng transaction options và test |
| GeoPage không được chấp nhận trong reactive | Reactive không hỗ trợ GeoPage/GeoResults wrappers | Flux<GeoResult<T>>, DTO |
| Mono<Page> từ reactive repository lỗi | Không có reactive Page return tự động | Flux + Mono count riêng |
| Reactive query không chạy | Publisher chưa subscribe | Trả Mono/Flux, dùng StepVerifier |
| Reactive count thực thi hai lần | subscribe thủ công rồi caller subscribe | Một subscription lifecycle |
| WebFlux bị chặn | Dùng block()/blocking repository | Compose reactive operators |
| Reactor trả 0 dù DB timeout | onErrorReturn(0L) che lỗi | Phân biệt error và empty result |
| collectList tăng RAM | Query không có limit | Giới hạn trang, không gom Flux vô hạn |
| Reactive transaction không bao hết lệnh | Tách subscriptions hoặc dùng manager sync | ReactiveMongoTransactionManager + một chain |
| Người dùng đọc được count tenant khác | Count filter thiếu authorization | Áp tenant cho count và items |
| Test chỉ pass bằng mock | Không chạy geospatial engine thật | MongoDB integration test với 2dsphere index |

### 31.1. Quy trình điều tra theo từng lớp

1. **Input:** longitude, latitude, radius và đơn vị có đúng không?
2. **Dữ liệu BSON:** location có đúng GeoJSON Point và tọa độ kiểu số?
3. **Index:** 2dsphere index đã tồn tại, query có sử dụng được?
4. **Filter:** tenant/active/category có giống nhau ở count và items?
5. **Command:** dùng $near, $geoWithin hay $geoNear; có đang đưa $near vào countDocuments không?
6. **Count rewrite:** phiên bản Spring Data xử lý near/count thế nào?
7. **Vùng:** nếu có minDistance, đã trừ vòng trong và xác định boundary semantics chưa?
8. **Page:** có count trước skip/limit không?
9. **Consistency:** count và items có chạy độc lập không, có transaction/read concern không?
10. **Reactive:** Publisher được compose/subscribed đúng lifecycle chưa?
11. **Transaction:** đúng manager/session/topology và không giữ transaction quá lâu chưa?
12. **Hiệu năng:** explain, command latency và pool wait cho workload thật.

## 32. Bài tập thực hành

### Bài tập 1: chọn operator đếm

Một API chỉ cần số cửa hàng active trong bán kính 2 km, không cần khoảng cách hoặc sort. Nên bắt đầu bằng $near hay $geoWithin?

**Đáp án:** **$geoWithin + $centerSphere** trong countDocuments, với filter tenant/active.

### Bài tập 2: GeoJSON đúng thứ tự

Tọa độ longitude=106.7009, latitude=10.7769. GeoJSON Point đúng là gì?

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

**Đáp án:** longitude đứng trước latitude.

### Bài tập 3: khoảng cách radians

Khi dùng $centerSphere, radius 2.000 mét phải được chuyển ra sao?

~~~java
double radians = 2_000.0 / 6_371_008.8;
~~~

**Đáp án:** Khoảng 0,0003139 radians. Không dùng trực tiếp 2.000 như radians.

### Bài tập 4: countDocuments với near

Một lập trình viên dùng $near trong db.stores.countDocuments. Có nên mặc định lệnh hợp lệ không?

**Đáp án:** Không. countDocuments không chấp nhận trực tiếp $near/$nearSphere; dùng geoWithin hoặc cơ chế khác được hỗ trợ.

### Bài tập 5: Spring Data rewrite

Tại sao MongoTemplate.count với Criteria.near có thể trả số dù countDocuments không hỗ trợ $near?

**Đáp án:** Spring Data có cơ chế **rewrite near predicate** thành geoWithin cho count. Vẫn phải kiểm chứng units/minDistance/boundary theo version và query thực.

### Bài tập 6: min/max distance

Cần đếm từ 500 m đến 2 km. $geoWithin có trực tiếp một thuộc tính minDistance không?

**Đáp án:** Không. Có thể dùng vòng ngoài $centerSphere 2 km **và** $nor loại vòng trong 500 m; kiểm thử boundary. Hoặc dùng $geoNear + $count theo semantics và hiệu năng phù hợp.

### Bài tập 7: count của page

Query trả 10 hàng từ tập 125 hàng. API muốn totalPages với size=10. Có thể dùng 10 làm total không?

**Đáp án:** Không. Cần total=125 của filter chưa limit; totalPages theo phép tính ceiling(125/10)=13.

### Bài tập 8: estimatedCount

estimatedDocumentCount có trả tổng trong bán kính 2 km theo tenantId không?

**Đáp án:** Không. Nó không áp dụng filter geospatial/tenant.

### Bài tập 9: transaction

Spring Data MongoDB gọi count trong một MongoTransactionManager transaction. Có nên dựa vào collection statistics để phản ánh các document mới insert chưa commit?

**Đáp án:** Không. Transaction count cần cách đếm phản ánh dữ liệu trong transaction; Spring Data hiện hành dùng countDocuments/aggregation-based count.

### Bài tập 10: $geoNear stage

MongoDB aggregation pipeline đặt $match trước $geoNear. Điều gì sai?

**Đáp án:** $geoNear phải đứng đầu pipeline; filter tenant/active có thể nằm trong $geoNear.query.

### Bài tập 11: đếm bằng $geoNear

~~~javascript
[
  { $geoNear: { /* filter near */ } },
  { $limit: 20 },
  { $count: "total" }
]
~~~

**Câu hỏi:** total là tổng vùng hay tổng đã giới hạn?

**Đáp án:** Tổng **sau $limit**, tối đa 20, không phải toàn vùng.

### Bài tập 12: hai query độc lập

Count=10 ở T0; một Store chuyển vị trí tại T1; find trả 9 ở T2. Có nhất thiết là bug?

**Đáp án:** Không. Nếu không có cùng snapshot, dữ liệu có thể thay đổi giữa hai lệnh. Phải xác định API contract.

### Bài tập 13: $facet

Muốn items và total từ cùng một input $geoWithin, có thể dùng stage nào?

**Đáp án:** **$facet** với hai nhánh items và totals sau $match. Cần kiểm soát memory/output size và không mặc định nó nhanh hơn hai query.

### Bài tập 14: Reactive count

ReactiveMongoTemplate.count trả kiểu nào?

**Đáp án:** **Mono<Long>**, không phải long và không phải Flux<Long> cho một phép đếm bình thường.

### Bài tập 15: Reactive geoNear

ReactiveMongoTemplate.geoNear trả kiểu dữ liệu nào?

**Đáp án:** **Flux<GeoResult<T>>**. Mỗi GeoResult mang entity và Distance.

### Bài tập 16: GeoPage

Vì sao reactive repository không trả GeoPage tự động giống blocking API?

**Đáp án:** GeoPage/GeoResults là kiểu tập kết quả eager/aggregated và không phù hợp với deferred reactive result contract. Trả Flux và xây DTO/count khi cần.

### Bài tập 17: Reactive Pageable

Không có GeoPage có nghĩa reactive không nhận Pageable không?

**Đáp án:** Không. Pageable vẫn có thể được dùng để áp limit/skip/sort trong derived query, nhưng kết quả là Flux.

### Bài tập 18: Mono.zip

Mono.zip(itemsMono, countMono) có tự mở MongoDB transaction không?

**Đáp án:** Không. Nó compose Publishers; cần ReactiveMongoTransactionManager/TransactionalOperator khi yêu cầu snapshot transaction thực.

### Bài tập 19: Block và subscribe

Một service reactive gọi .block() để lấy total rồi .subscribe() cho query tìm gần nhất. Có vấn đề gì?

**Đáp án:** Blocking làm nghẽn event loop; subscription tự tạo tách lifecycle và transaction context. Return/combine Mono/Flux đúng cách.

### Bài tập 20: tenant security

API count lọc tenant, nhưng API danh sách không lọc tenant. Có an toàn không?

**Đáp án:** Không. Count và items đều phải áp authorization/tenant filter, đồng thời phân loại dữ liệu vị trí nào được công bố.

### Bài tập 21: dữ liệu đa điểm

Một Store document chứa năm địa điểm trong array, hai điểm nằm trong vùng. countDocuments trả bao nhiêu Store document cho record này?

**Đáp án:** **Một document** nếu document khớp, không phải hai tọa độ. Đếm chi nhánh cần mô hình/pipeline riêng.

### Bài tập 22: kiểm thử đúng

Unit test mock MongoTemplate trả 2 cho count. Đã đủ chứng minh chuyển meters→radians chính xác và 2dsphere hoạt động chưa?

**Đáp án:** Không. Cần integration test MongoDB với fixture center/near/far, index thật và so sánh kết quả.

## 33. Checklist trước khi triển khai production

- **Schema:** Store location lưu GeoJSON Point đúng [longitude,latitude] chưa?
- **Giới hạn đầu vào:** longitude/latitude hợp lệ, radius dương và hữu hạn chưa?
- **Đơn vị:** GeoJSON near tính meters, centerSphere nhận radians và NearQuery metric rõ ràng chưa?
- **2dsphere:** index đã tạo/migrate thật trên collection chưa?
- **Compound index:** query plan được đo với tenant/active/location filters chưa?
- **Tenant:** authenticatedTenantId đến từ nguồn server đáng tin cậy chưa?
- **Privacy:** có hạn chế việc tiết lộ tọa độ hay count quá chi tiết không?
- **Count:** không dùng $near/$nearSphere trực tiếp trong countDocuments chưa?
- **Rewrite:** phiên bản Spring Data có behavior count rewrite đã được kiểm thử chưa?
- **Manual count:** geoWithin/$centerSphere có cùng vùng và filter với danh sách chưa?
- **MinDistance:** đã xử lý vòng trong/vành khăn theo semantics cần thiết chưa?
- **Boundary:** có test gần ranh giới nếu nghiệp vụ cần độ chính xác cao chưa?
- **Estimated count:** không dùng estimatedDocumentCount làm total geospatial chưa?
- **Paging:** query count không bị giới hạn bởi page skip/limit chưa?
- **Stable ordering:** có tie-breaker để kết quả sort ổn định chưa?
- **Nearby:** $near hoặc $geoNear có giới hạn radius/max results chưa?
- **Distance:** response công bố đơn vị, không trộn meters/kilometers chưa?
- **Aggregation:** $geoNear đứng đầu, có key nếu cần và query filter đúng chưa?
- **Pipeline count:** không đặt $limit trước $count nếu muốn total của cả vùng chưa?
- **$facet:** đã đo memory/latency và xử lý totals rỗng chưa?
- **Transaction topology:** replica set/sharded deployment và index đã sẵn sàng chưa?
- **Transaction scope:** chỉ mở khi cần consistency, giữ đủ ngắn chưa?
- **Read concern:** có hiểu snapshot/read preference cho count + items chưa?
- **Write guard:** nếu chọn Store rồi giữ hàng, vẫn có conditional stock update chưa?
- **Reactive count:** trả Mono<Long> và giữ error signals chưa?
- **Reactive nearest:** trả Flux<GeoResult<T>> thay vì GeoPage/GeoResults chưa?
- **Reactive paging:** dùng Flux + count Mono hoặc aggregation/hasNext rõ ràng chưa?
- **Reactive lifecycle:** không block hoặc tự subscribe nhiều lần chưa?
- **Reactive transaction:** dùng ReactiveMongoTransactionManager/Reactor Context khi cần chưa?
- **Backpressure:** không nhầm streaming với tự tối ưu index chưa?
- **Limits:** pageSize, radius và timeouts đều được giới hạn chưa?
- **Tests:** có MongoDB integration tests cho center/near/far/tenant/units chưa?
- **Test transaction:** có replica set test cho read/count khi cần chưa?
- **Test reactive:** có StepVerifier cho count, GeoResult và error/cancel chưa?
- **Operations:** có executionStats, command latency, pool metrics và alert phù hợp chưa?

## 34. Tổng kết

1. **$near/$nearSphere** được dùng cho tìm kiếm lân cận, có semantics sort theo khoảng cách; chúng **không được sử dụng trực tiếp trong countDocuments**.
2. **$geoWithin** với $centerSphere là cách tự nhiên để đếm các GeoJSON points trong một bán kính hình cầu, nhưng radius cần đổi từ **meters sang radians**.
3. **Spring Data MongoDB** có cơ chế viết lại near queries cho count ở các phiên bản hiện hành; cần hiểu behavior và đặc biệt các trường hợp minDistance.
4. **Vành khăn** giữa minDistance/maxDistance có thể được biểu diễn bằng vòng ngoài và điều kiện loại vòng trong với $nor, hoặc bằng $geoNear + $count khi phù hợp.
5. **estimatedDocumentCount** không thay thế filtered count vì không áp điều kiện tenant/radius.
6. **Tổng số toàn vùng** khác số item trong page; không áp $limit trước $count nếu muốn toàn bộ total.
7. **$geoNear** là aggregation stage, phải đứng đầu pipeline và có geospatial index; nên đưa các filter thông thường vào thuộc tính query.
8. **$facet** có thể trả items và total trong một pipeline nhưng phải xem chi phí bộ nhớ/latency và giới hạn output.
9. **MongoTransactionManager** cung cấp transaction imperative; count trong transaction cần phương thức phù hợp, không dựa trên collection statistics.
10. **Transaction không mặc định cần cho geo search đọc**, không tự làm query nhanh hơn và không thay business guards cho các lệnh ghi sau đó.
11. **Count và items trong hai lệnh độc lập** có thể quan sát dữ liệu khác nhau khi có concurrent writes; xác định consistency contract trước khi chọn snapshot/transaction.
12. **ReactiveMongoTemplate.count** trả Mono<Long>, còn **ReactiveMongoTemplate.geoNear** trả Flux<GeoResult<T>>.
13. **Reactive repositories** hỗ trợ geospatial query và Pageable nhưng không tự trả GeoPage/GeoResults hay Mono<Page>.
14. **Mono.zip** compose hai Publisher nhưng không tự mở transaction; ReactiveMongoTransactionManager quản lý transaction qua Reactor Context.
15. **Reactive streaming không thay index/query-plan tuning**; phải kiểm soát radius, số item, concurrency và tài nguyên.
16. **Bảo mật theo tenant áp cho count và items**; một count địa lý quá chi tiết cũng có thể tiết lộ thông tin.
17. **Integration tests MongoDB** phải xác nhận 2dsphere index, tọa độ, đơn vị, vùng và thực thi thật; test transactions phải dùng topology hỗ trợ.

Nắm được **giới hạn phép đếm, transaction và biến thể reactive** giúp dịch vụ **SPRING_DATA_MONGODB** trả số lượng địa điểm chính xác theo định nghĩa nghiệp vụ, truy vấn lân cận với đơn vị rõ ràng, giữ ranh giới nhất quán phù hợp và triển khai reactive geospatial APIs không làm mất các ràng buộc của MongoDB Server.

### Tài liệu tham khảo

- [Spring Data MongoDB — Counting Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-document-count.html) — countDocuments, estimatedCount, rewrite $near/$nearSphere và minDistance.
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — Criteria.near/withinSphere, $geoNear và NearQuery.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — count trong transaction, session, transaction manager và geospatial restrictions.
- [Spring Data MongoDB — Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — reactive GeoResult, Pageable, giới hạn GeoPage/GeoResults.
- [Spring Data MongoDB — NearQuery API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/NearQuery.html) — metric, GeoJsonPoint, max/min distance, limit và query filter.
- [Spring Data MongoDB — ReactiveMongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html) — count Mono, geoNear Flux và aggregate.
- [MongoDB Manual — countDocuments](https://www.mongodb.com/docs/manual/reference/method/db.collection.countDocuments/) — hạn chế query predicates trong countDocuments.
- [MongoDB Manual — $geoNear Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/) — stage đầu tiên, geospatial index, distance và query filter.
- [MongoDB Manual — $near](https://www.mongodb.com/docs/manual/reference/operator/query/near/) — nearest-neighbor filter và distance units.
- [MongoDB Manual — $geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/) — geometry containment và centerSphere.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — session, topology và giới hạn transaction.
