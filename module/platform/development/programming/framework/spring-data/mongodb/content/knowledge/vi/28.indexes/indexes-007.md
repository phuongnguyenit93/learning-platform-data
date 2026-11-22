# Text, geospatial, hashed và wildcard index

## 1. Vì sao cần các loại index chuyên dụng?

Trong chương **Chỉ mục** của **Spring Data MongoDB**, các index thông thường như `{ tenantId: 1, createdAt: -1 }` rất hữu ích cho điều kiện bằng nhau, khoảng giá trị và sắp xếp. Tuy nhiên, nhiều yêu cầu không chỉ là so sánh giá trị của một trường:

- Tìm sản phẩm có nội dung mô tả chứa các **từ khóa**, có xét điểm liên quan.
- Tìm điểm nhận hàng **gần vị trí** người dùng hoặc **nằm trong một khu vực**.
- Phân phối dữ liệu đều hơn trên các shard khi khóa logic có số lượng giá trị đủ lớn.
- Truy vấn các thuộc tính sản phẩm có cấu trúc **động**, không thể dự đoán hết tên field.

MongoDB có các index chuyên dụng:

| Loại index | Key pattern điển hình | Công việc chính |
|---|---|---|
**Text index** | `{ name: "text", description: "text" }` | Tìm từ khóa qua `$text`; có thể tính `textScore` |
**Geospatial 2dsphere** | `{ pickupLocation: "2dsphere" }` | Truy vấn điểm/khu vực trên bề mặt Trái Đất bằng GeoJSON |
**Geospatial 2d** | `{ point: "2d" }` | Tọa độ phẳng/legacy, không thay thế 2dsphere cho mọi bài toán |
**Hashed index** | `{ customerId: "hashed" }` | Hỗ trợ equality trên khóa đã băm; thường liên quan chiến lược hashed sharding |
**Wildcard index** | `{ "attributes.$**": 1 }` | Index nhiều đường dẫn field không cố định trong một document/map |

**Không có loại nào là “index mạnh nhất”.** Mỗi loại hỗ trợ một họ truy vấn, có chi phí ghi và giới hạn riêng. Tạo cả bốn loại cho mọi collection có thể khiến hệ thống chậm hơn do tốn index storage, cache và thời gian cập nhật index.

### Mục tiêu của bài

1. Giải thích cơ chế và trường hợp sử dụng text, geospatial, hashed, wildcard index.
2. Viết truy vấn MongoDB tương ứng và nhận biết loại index nào thực sự hỗ trợ nó.
3. Tạo index qua MongoDB shell, Spring Data MongoDB metadata hoặc `MongoTemplate`/Java Driver khi thích hợp.
4. Phân biệt `$text` với substring/regex và các giải pháp tìm kiếm chuyên dụng.
5. Đọc đúng GeoJSON, thứ tự longitude–latitude, đơn vị khoảng cách và khác biệt `2d`/`2dsphere`.
6. Hiểu hashed equality, tính phân phối shard key, giới hạn range/unique/multikey.
7. Sử dụng wildcard cho thuộc tính động mà vẫn bảo vệ whitelist field, tenant và hiệu năng.
8. Kiểm chứng index bằng `getIndexes()`, `explain("executionStats")` và integration test với MongoDB thật.

> Các ví dụ dùng Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x. Một số đặc tính phụ thuộc MongoDB server: text/2dsphere đã có từ các thế hệ cũ, wildcard index được giới thiệu trong MongoDB 4.2 và compound wildcard index có phạm vi hỗ trợ mới hơn (MongoDB 7.0+). Luôn xác minh phiên bản server/driver, topology và hỗ trợ API đang triển khai; không coi một đoạn lệnh shell là cam kết tương thích với mọi môi trường.

## 2. Dữ liệu mẫu cho bốn loại index

Ta dùng hệ thống danh mục sản phẩm đa tenant. Sản phẩm có mô tả văn bản, vị trí nhận hàng, mã khách hàng/nguồn ngoài và thuộc tính mở rộng:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "customerId": "cust-100127",
  "name": "Steel water bottle",
  "description": "Insulated reusable water bottle for outdoor trips",
  "category": "DRINKWARE",
  "pickupLocation": {
    "type": "Point",
    "coordinates": [106.70098, 10.77689]
  },
  "attributes": {
    "material": "steel",
    "capacityMl": 500,
    "insulated": true
  }
}
~~~

Với schema này:

- `name`/`description` là ứng viên của **text index**.
- `pickupLocation` là ứng viên của **2dsphere index**.
- `customerId` có thể là ứng viên của **hashed index** nếu truy vấn equality và bài toán phân phối dữ liệu phù hợp.
- `attributes` chứa các property biến đổi theo danh mục sản phẩm; có thể là ứng viên của **wildcard index**.
- `tenantId` là điều kiện phân quyền quan trọng, **không phải tùy chọn** trong các truy vấn của tenant.

### 2.1. Entity Spring Data MongoDB

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.util.Map;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String customerId;
    private String name;
    private String description;
    private String category;

    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    private GeoJsonPoint pickupLocation;

    private Map<String, Object> attributes;

    protected CatalogProduct() {
        // Dành cho Spring Data materialization.
    }

    public CatalogProduct(
            String id, String tenantId, String customerId,
            String name, String description, String category,
            GeoJsonPoint pickupLocation,
            Map<String, Object> attributes) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.name = name;
        this.description = description;
        this.category = category;
        this.pickupLocation = pickupLocation;
        this.attributes = attributes;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getCustomerId() { return customerId; }
    public String getName() { return name; }
    public String getDescription() { return description; }
    public String getCategory() { return category; }
    public GeoJsonPoint getPickupLocation() {
        return pickupLocation;
    }
    public Map<String, Object> getAttributes() {
        return attributes;
    }
}
~~~

`@MongoId(FieldType.STRING)` giữ `_id` là BSON String. `GeoJsonPoint` chứa **longitude trước, latitude sau**; annotation `@GeoSpatialIndexed` mô tả index 2dsphere ở mức metadata, nhưng **index không nhất thiết được tạo tự động**: điều đó phụ thuộc cấu hình auto-index và quy trình triển khai.

Trong bài này, các ví dụ text, hashed và wildcard được tạo bằng lệnh tường minh để dễ quan sát; **không đồng thời bật một cơ chế tự tạo index trùng định nghĩa mà không kiểm soát**.

## 3. Text index: tìm kiếm theo từ, không phải mọi chuỗi con

Text index của MongoDB tạo các mục index cho những **term** rút ra từ field văn bản theo cơ chế tokenization/language processing của server.

~~~javascript
db.catalog_products.createIndex(
  {
    name: "text",
    description: "text"
  },
  {
    name: "idx_product_text",
    weights: {
      name: 5,
      description: 1
    },
    default_language: "english"
  }
);
~~~

Index này dùng hai field nhưng vẫn là **một text index**. MongoDB có ràng buộc **tối đa một text index trên một collection** theo loại text index truyền thống; có thể đưa nhiều field vào cùng định nghĩa text index đó. Không tạo text index riêng cho `name` rồi một text index khác cho `description` trên cùng collection.

### 3.1. Truy vấn bằng $text

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  $text: {
    $search: "water bottle"
  }
});
~~~

Với cách diễn giải text search thông thường, các term trong `$search` không tự động tạo một phép so khớp **substring** giống SQL `LIKE '%water bottle%'`. MongoDB hỗ trợ tìm theo term, các biến thể từ theo language và quy tắc search cụ thể.

Ví dụ các nhu cầu **khác nhau**:

| Yêu cầu | Cơ chế gợi ý |
|---|---|
Tìm các term `water` hoặc `bottle` trong nội dung | MongoDB `$text` |
Ưu tiên cụm từ `"water bottle"` | Text search với cú pháp phrase phù hợp |
Tìm tên chính xác `"Steel water bottle"` | Equality/collation hoặc index thường tùy contract |
Tìm chuỗi con `"ottl"` ở mọi vị trí | Không coi text index là substring index |
Autocomplete khi gõ từng ký tự | Tìm kiếm chuyên dụng (ví dụ MongoDB Search) hoặc thiết kế riêng |
Tìm typo/fuzzy, synonym, ranking phong phú | Search engine/search index chuyên dụng |

**Điểm quan trọng:** text index không thay thế toàn bộ yêu cầu search. Khi cần autocomplete, fuzzy matching, analyzers theo ngôn ngữ hay ranking nâng cao, nên đánh giá **MongoDB Search** (Atlas Search ở môi trường tương ứng) hoặc một search service thích hợp; đó là cơ chế index/search khác với `createIndex({ field: "text" })` thông thường.

### 3.2. Phrase, negation và token semantics

Ví dụ trong mongosh:

~~~javascript
// Tìm một cụm từ được đặt trong dấu nháy kép.
db.catalog_products.find({
  $text: { $search: "\"water bottle\"" }
});

// Tìm term water, loại các document có term plastic.
db.catalog_products.find({
  $text: { $search: "water -plastic" }
});
~~~

Cú pháp search string có quy tắc riêng cho dấu nháy, dấu trừ và term. Không nối trực tiếp một chuỗi truy vấn search phức tạp từ đầu vào không đáng tin rồi mặc nhiên coi đó là một literal từ khóa. Hãy định nghĩa chính sách xử lý quotation, negation, độ dài và ký tự đặc biệt cho API.

### 3.3. Tại sao index text có thể không dùng được cho regex?

~~~javascript
db.catalog_products.find({
  name: /bottle/i
});
~~~

Lệnh này là regex query, **không phải `$text`**. Một text index không được thiết kế để tối ưu mọi regex tùy ý, đặc biệt regex không anchored hoặc không tương thích collation. Truy vấn theo prefix bằng B-tree index với điều kiện thích hợp có đặc điểm khác so với `$text` hay regex quét chuỗi.

## 4. Text score, trọng số field và sắp xếp kết quả

Khi nhiều document khớp từ khóa, ứng dụng thường cần đưa kết quả liên quan hơn lên trước. MongoDB cung cấp `textScore` metadata:

~~~javascript
db.catalog_products.find(
  {
    tenantId: "tenant-a",
    $text: { $search: "water bottle" }
  },
  {
    name: 1,
    description: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
});
~~~

Trọng số `weights: { name: 5, description: 1 }` khiến term trong tên có thể đóng góp khác với term trong mô tả. Tuy nhiên **score không phải xác suất** và không có thang cố định kiểu “từ 0 tới 100”. Không đặt ngưỡng nghiệp vụ tùy tiện dựa trên score khi chưa đo/test dữ liệu thật.

### 4.1. Score không tự động xuất hiện ở mọi find

Kết quả `$text` không nhất thiết chứa một field `score` bình thường trong BSON document gốc. `score` được đưa ra từ metadata `$meta: "textScore"` ở projection/sort, không phải field ứng dụng bắt buộc ghi vào collection.

Nếu DTO cần điểm liên quan, có thể dùng `@TextScore` trong Spring Data MongoDB ở những đường mapping được hỗ trợ; phải kiểm tra thực tế cách query yêu cầu và materialize score.

### 4.2. Text search và sort theo ngày

Một endpoint có thể muốn:

- **Relevance-first:** sắp `textScore DESC`.
- **Newest-first:** chỉ lọc theo `$text` rồi sắp `createdAt DESC`.
- **Hybrid ranking:** cần chính sách rõ ràng về kết hợp relevance, freshness và chất lượng.

Đừng mặc nhiên dùng index text như một compound B-tree index có thể sort mọi field còn lại. Khi sort theo field khác, server có thể phải xử lý một bước sort riêng. Dùng `explain` để đo.

## 5. Language, stemming, stop words và tiếng Việt

MongoDB text index truyền thống có khái niệm **language** dùng cho stemming và stop words. Ngôn ngữ trong index ảnh hưởng các term được lưu; ngôn ngữ trong `$text` ảnh hưởng cách xử lý search.

Ví dụ:

~~~javascript
db.catalog_products.createIndex(
  { name: "text", description: "text" },
  {
    name: "idx_product_text_none",
    default_language: "none"
  }
);
~~~

Đây là **lựa chọn thay thế** cho index `idx_product_text` của mục 3, **không phải lời gọi thứ hai chạy thêm trên cùng collection khi đã có text index**. Muốn đổi default language/weights, phải lên kế hoạch thay thế định nghĩa index cũ theo quy trình quản trị.

Với `default_language: "none"`, MongoDB không áp dụng stemming/stop-word filtering theo một ngôn ngữ cụ thể. Nó có thể phù hợp cho dữ liệu đa ngôn ngữ hoặc khi không có bộ stemming mong muốn, nhưng **không tự cung cấp tách từ tiếng Việt chuyên sâu, xử lý dấu, chính tả hoặc synonym**.

### 5.1. Tiếng Việt cần kiểm thử riêng

Một nội dung như:

~~~text
"Bình giữ nhiệt bằng thép không gỉ"
~~~

không được bảo đảm sẽ có cùng hành vi tìm kiếm khi bỏ dấu, đảo thứ tự từ hoặc gõ thiếu ký tự như người dùng kỳ vọng. Đừng chọn `default_language: "english"` rồi cho rằng từ tiếng Việt sẽ được phân tích đúng.

Nếu ứng dụng yêu cầu:

- Tìm có/không dấu;
- Tách từ tiếng Việt;
- Autocomplete ở mỗi ký tự;
- Đồng nghĩa theo miền bán hàng;
- Sửa lỗi gõ hoặc fuzzy ranking;

hãy thử một giải pháp search có analyzer phù hợp. Phải xây bộ test truy vấn tiếng Việt thực tế để so sánh chất lượng kết quả trước khi quyết định kiến trúc.

### 5.2. Một số hạn chế vận hành

- Một collection chỉ có thể có một text index truyền thống, dù index đó gồm nhiều field.
- Text index được xây trên **text fields**, không tự tìm trên mọi dữ liệu số/object.
- Text index truyền thống có quy tắc riêng với **collation** (với collection có non-simple default collation, cần xem xét `{ locale: "simple" }` khi tạo text index).
- `$text` có quy tắc sử dụng riêng trong aggregation và không thể thay thế mọi phép truy vấn geospatial.
- Tài liệu release của MongoDB phải được kiểm tra khi áp dụng trên view, sharded collection hoặc kết hợp operator đặc biệt.

**Không nên coi text index là lựa chọn mặc định cho trường mã SKU.** Mã SKU có quy tắc tách term đặc biệt, thường cần equality/prefix search với index hoặc search schema riêng.

## 6. Text index trong Spring Data MongoDB

Spring Data MongoDB có `@TextIndexed` để đánh dấu field góp vào text index và `TextCriteria`/`TextQuery` để xây truy vấn `$text`.

### 6.1. Metadata @TextIndexed

Trong một **class entity** có field `name` và `description`:

~~~java
import org.springframework.data.mongodb.core.index.TextIndexed;

@TextIndexed(weight = 5)
private String name;

@TextIndexed
private String description;
~~~

Đây là **đoạn khai báo field minh họa**, không phải class Java độc lập. Khi dùng auto-index creation hoặc index resolver trong một bước migration được kiểm soát, Spring Data có thể dùng metadata text index này để xây định nghĩa index.

Nếu đã tạo một text index bằng MongoDB shell/driver, không để hệ thống vô tình tự tạo thêm text index khác trên cùng collection. **Một chiến lược quản lý index thống nhất** quan trọng hơn việc dùng annotation hay lệnh shell.

### 6.2. TextCriteria và TextQuery

**CatalogTextSearchService.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.TextCriteria;
import org.springframework.data.mongodb.core.query.TextQuery;
import org.springframework.stereotype.Service;

@Service
public class CatalogTextSearchService {
    private final MongoTemplate mongo;

    public CatalogTextSearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CatalogProduct> search(
            String authenticatedTenantId,
            String searchTerm,
            int limit) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || searchTerm == null || searchTerm.isBlank()
                || searchTerm.length() > 100
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Bộ lọc không hợp lệ");
        }

        TextCriteria criteria = TextCriteria
                .forDefaultLanguage()
                .matching(searchTerm);

        TextQuery query = TextQuery
                .queryText(criteria)
                .sortByScore();

        query.addCriteria(
                Criteria.where("tenantId").is(authenticatedTenantId));
        query.limit(limit);

        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

`TextQuery.sortByScore()` yêu cầu sắp xếp dựa trên độ liên quan text. Tùy API/phiên bản, có thể dùng `@TextScore` ở entity/DTO để lấy score. Ví dụ này chỉ trả entity, **không cam kết expose score** như một field bình thường.

**Lưu ý bảo mật:** `authenticatedTenantId` phải lấy từ xác thực phía server. `$text` là điều kiện tìm kiếm, không thay thế lọc tenant hoặc các điều kiện quyền xem sản phẩm.

### 6.3. Khi nào không nên dùng TextQuery?

`TextQuery` chỉ thể hiện cơ chế text search truyền thống của MongoDB. Với autocomplete, fuzzy search, highlight, analyzer theo ngôn ngữ và phức hợp rank/search chuyên dụng, cần kiểm tra giải pháp search khác. Đừng ép một DSL Querydsl/repository hoặc `TextQuery` diễn đạt những tính năng không được adapter/server hỗ trợ.

## 7. Geospatial: dữ liệu không gian và 2dsphere

Geospatial index hỗ trợ query theo **vị trí, khoảng cách và hình học**. Với tọa độ địa lý thực tế (longitude/latitude trên Trái Đất), loại thường dùng là `2dsphere`:

~~~javascript
db.catalog_products.createIndex(
  { pickupLocation: "2dsphere" },
  { name: "idx_product_pickup_2dsphere" }
);
~~~

Document GeoJSON Point:

~~~json
{
  "type": "Point",
  "coordinates": [106.70098, 10.77689]
}
~~~

Trong GeoJSON, `coordinates` theo thứ tự **[longitude, latitude]**; không phải [latitude, longitude]. Hãy ghi quy tắc này ở cả DTO, validation và integration test để tránh một lỗi rất khó phát hiện khi hai giá trị vẫn nằm trong miền hợp lệ.

### 7.1. Kiểm tra tọa độ

- Longitude thông thường trong khoảng **−180 tới +180** độ.
- Latitude trong khoảng **−90 tới +90** độ.
- Nguồn dữ liệu phải thống nhất hệ tọa độ; GeoJSON trên 2dsphere dùng hệ tọa độ địa lý tương ứng (WGS84).
- `0,0` không phải “chưa có vị trí”. Dùng field thiếu/null theo chính sách schema, không mặc định gán tọa độ 0.
- GeoJSON geometry phải đúng cấu trúc, loại `Point`/`Polygon`/v.v. và quy tắc vòng khép kín với polygon.

### 7.2. 2dsphere khác 2d

| Khía cạnh | `2dsphere` | `2d` |
|---|---|---|
Không gian | Trái Đất/hình học trên cầu | Mặt phẳng 2 chiều |
Dữ liệu điển hình | GeoJSON Point, LineString, Polygon | Legacy coordinate pairs/planar |
Index | `{ location: "2dsphere" }` | `{ point: "2d" }` |
Truy vấn phổ biến | `$near`/`$nearSphere` và `$geoWithin` theo geometry phù hợp | `$near`/`$geoWithin` theo tọa độ legacy/planar phù hợp |
Đơn vị khoảng cách | GeoJSON point gần trên bề mặt Trái Đất: thường **mét** | Phụ thuộc hệ tọa độ phẳng, không tự là mét địa lý |
Khi chọn | Vị trí cửa hàng, giao nhận theo longitude/latitude | Bản đồ phẳng hoặc dữ liệu legacy được thiết kế phù hợp |

Không thay `"2d"` bằng `"2dsphere"` một cách máy móc nếu dữ liệu hiện tại không đúng GeoJSON/coordinate system. Với bài toán vị trí địa lý mới, **GeoJSON + 2dsphere** thường rõ ràng hơn.

### 7.3. Field thiếu và index 2dsphere

`2dsphere` có quy tắc sparse-like: document không có giá trị vị trí phù hợp có thể không tạo entry trong index. Vì vậy query địa lý chỉ có thể thấy các document có geometry được index theo điều kiện đó.

Không coi việc một sản phẩm không xuất hiện trong geo query là chứng cứ nó không tồn tại: có thể sản phẩm tồn tại nhưng thiếu `pickupLocation`, tọa độ không hợp lệ hoặc đang nằm ngoài bán kính/khu vực.

## 8. Truy vấn gần vị trí bằng $near

Tìm sản phẩm trong một phạm vi quanh một GeoJSON Point:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  pickupLocation: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  }
});
~~~

Ở đây, với GeoJSON Point và index `2dsphere` phù hợp, `$maxDistance: 3000` nghĩa là **3.000 mét**. Query `$near` trả những document thỏa điều kiện địa lý theo khoảng cách gần trước; không cần thêm một lần sort theo tọa độ thô để tạo “gần nhất”.

### 8.1. Không so khoảng cách bằng độ longitude/latitude

Ví dụ tính:

~~~text
deltaLon = abs(106.72 - 106.70)
deltaLat = abs(10.79 - 10.77)
~~~

không phải phép đo khoảng cách mặt đất theo mét. Một độ kinh tuyến có chiều dài thay đổi theo vĩ độ; Trái Đất không phải mặt phẳng longitude–latitude đồng nhất. Dùng các toán tử geospatial phù hợp thay vì tự viết khoảng cách Euclid theo số độ.

### 8.2. Bán kính và số liệu distance

Khi dùng GeoJSON/2dsphere với `$near`, khoảng cách được hiểu theo **mét**. Với các toán tử dùng legacy coordinate pairs hoặc `$centerSphere`, đơn vị có thể là **radian** thay vì mét; đừng lấy cùng một số `3000` áp dụng vào mọi biểu thức địa lý.

Nếu yêu cầu API là “trong 2,5 km”, chuyển thành **2500 mét** khi dùng `$near` GeoJSON; kiểm tra thực tế bằng test khoảng cách cho điểm gần, điểm ngoài bán kính và điểm ngay ranh giới.

### 8.3. Truy vấn gần nhất không tự lọc tenant

`$near` chỉ xử lý quan hệ địa lý. Nếu quên `tenantId` hoặc trạng thái sản phẩm, endpoint có thể trả điểm nhận hàng không được phép. Truy vấn phải kết hợp địa lý với **tenant và authorization filter** ngay ở server.

## 9. $geoWithin, polygon và $geoNear

### 9.1. Tìm trong khu vực bằng $geoWithin

Ví dụ polygon GeoJSON (tọa độ minh họa, không phải ranh giới hành chính thật):

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  pickupLocation: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.69, 10.77],
          [106.72, 10.77],
          [106.72, 10.79],
          [106.69, 10.79],
          [106.69, 10.77]
        ]]
      }
    }
  }
});
~~~

Polygon có **vòng khép kín**: điểm đầu xuất hiện lại ở cuối. Với polygon phức tạp, cần quan tâm đến thứ tự/ring, self-intersection, biên quốc tế, diện tích lớn và semantics hình học của MongoDB; đừng coi mọi đa giác do client gửi là hợp lệ.

`$geoWithin` kiểm tra quan hệ **nằm trong vùng**, không đồng nghĩa trả kết quả theo khoảng cách gần nhất. Nếu UI cần thứ tự gần trước, phải thiết kế bước tính/sort khoảng cách tương ứng.

### 9.2. Aggregation $geoNear

`$geoNear` cho phép lấy **khoảng cách tính toán** vào một field output:

~~~javascript
db.catalog_products.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      key: "pickupLocation",
      query: {
        tenantId: "tenant-a",
        category: "DRINKWARE"
      }
    }
  },
  { $project: {
      _id: 1,
      name: 1,
      distanceMeters: 1
    }
  },
  { $limit: 20 }
]);
~~~

Với pipeline này:

- `$geoNear` phải nằm **đầu pipeline** theo quy tắc của stage.
- `distanceField` tạo giá trị khoảng cách phục vụ DTO/UI.
- `query` bên trong `$geoNear` giữ điều kiện tenant/category.
- `key` giúp chỉ rõ field địa lý khi collection có nhiều index geospatial.
- `maxDistance` được hiểu theo đơn vị tương ứng với GeoJSON/thiết lập; ở ví dụ là mét.

Đừng đưa `$match` vào trước `$geoNear` chỉ để lọc tenant: dùng `query` của `$geoNear` khi stage yêu cầu đứng đầu.

### 9.3. Giới hạn khi ghép text search và geoNear

Một pipeline không thể tùy tiện đặt cả `$geoNear` và một `$match` chứa `$text` đều ở vị trí mà mỗi toán tử yêu cầu là **đầu tiên**. Nếu nghiệp vụ cần kết hợp ranking text và khoảng cách, hãy xem xét thiết kế search thích hợp, nhiều bước truy vấn có kiểm soát hoặc MongoDB Search theo khả năng của môi trường.

Không coi `$text` + `$near` là một query tổng quát mà mọi version/index đều hỗ trợ. Phải kiểm tra các hạn chế operator và thống nhất semantics xếp hạng.

## 10. GeoJSON và Spring Data MongoDB

Spring Data hỗ trợ `GeoJsonPoint`, `GeoJsonPolygon`, `Criteria`, `NearQuery` và `MongoTemplate.geoNear(...)` ở các mức API tương ứng.

### 10.1. GeoJsonPoint và nearSphere

**CatalogGeoSearchService.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class CatalogGeoSearchService {
    private final MongoTemplate mongo;

    public CatalogGeoSearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CatalogProduct> nearby(
            String authenticatedTenantId,
            double longitude,
            double latitude,
            double radiusMeters,
            int limit) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || !Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -90 || latitude > 90
                || !Double.isFinite(radiusMeters)
                || radiusMeters <= 0 || radiusMeters > 10000
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Geo query không hợp lệ");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authenticatedTenantId)
                        .and("pickupLocation")
                        .nearSphere(new GeoJsonPoint(
                                longitude, latitude))
                        .maxDistance(radiusMeters));

        query.limit(limit);
        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

`nearSphere` trên `GeoJsonPoint` diễn đạt truy vấn gần vị trí. Với GeoJSON + 2dsphere, `radiusMeters` là giới hạn mét theo semantics query tương ứng; cần xác minh BSON sinh ra và test ranh giới khoảng cách trên phiên bản Spring Data được dùng.

**Quan trọng:** phương thức trên không nhận tùy ý tên field địa lý từ client; cố định `pickupLocation` và lấy tenant từ ngữ cảnh xác thực. Chỉ số `radiusMeters` đã được giới hạn để tránh một request quét phạm vi quá rộng.

### 10.2. Khi cần distance trong kết quả

`MongoTemplate.geoNear(...)` có thể trả `GeoResults<T>` chứa `GeoResult<T>`, trong đó có giá trị `Distance`:

~~~java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.aggregation.NearQuery;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

NearQuery near = NearQuery
        .near(new GeoJsonPoint(106.70098, 10.77689))
        .maxDistance(new Distance(3, Metrics.KILOMETERS))
        .spherical(true);

GeoResults<CatalogProduct> results =
        mongo.geoNear(near, CatalogProduct.class);
~~~

Đây là **đoạn minh họa đặt trong scope có `mongo` kiểu `MongoTemplate`**. Để sử dụng trong endpoint đa tenant, phải bổ sung điều kiện tenant vào query/filter của `NearQuery` theo API phiên bản, hoặc dùng `$geoNear.query` tường minh; không copy đoạn demo chưa có tenant filter vào production.

Khoảng cách là một giá trị **tính toán**, không phải field bắt buộc lưu trong entity. Khi đưa ra API, hãy chuyển đơn vị và làm tròn theo contract (mét/km) thay vì hiển thị một số không tên đơn vị.

## 11. Hashed index: tối ưu equality trên giá trị đã băm

Hashed index lưu hash của giá trị field trong cấu trúc index. Ví dụ:

~~~javascript
db.catalog_products.createIndex(
  { customerId: "hashed" },
  { name: "idx_product_customer_hashed" }
);
~~~

Truy vấn phù hợp:

~~~javascript
db.catalog_products.find({
  customerId: "cust-100127"
});
~~~

Hashed index có thể hỗ trợ **equality lookup**, nhưng nó không lưu thứ tự nguyên bản của ID để phục vụ range/sort theo field đó.

### 11.1. Trường hợp không nên dùng hashed

~~~javascript
// Range theo chuỗi customerId.
db.catalog_products.find({
  customerId: { $gte: "cust-100000" }
});

// Sort theo customerId tăng dần.
db.catalog_products.find({}).sort({
  customerId: 1
});
~~~

Những truy vấn này không tự được hỗ trợ tốt bởi hashed index theo thứ tự tự nhiên của `customerId`. Nếu API thường xuyên duyệt một khoảng key hoặc phân trang theo ID, index B-tree tăng/giảm có thể phù hợp hơn.

### 11.2. Hashed index không tự có uniqueness

MongoDB **không hỗ trợ unique hashed index** theo semantics của một unique B-tree index. Dù hash được thiết kế để phân tán, uniqueness nghiệp vụ không thể dựa vào hash.

Nếu `customerId` cần unique theo tenant, hãy thiết kế unique index thích hợp, ví dụ:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, customerId: 1 },
  { unique: true, name: "uq_tenant_customer" }
);
~~~

Đây là một index **khác** với hashed index; ứng dụng phải cân nhắc có thực sự cần cả hai hay không. Đừng gọi một lệnh `createIndex({ customerId: "hashed" }, { unique: true })` rồi kỳ vọng MongoDB thực thi uniqueness.

### 11.3. Hashed và array

Hashed index không phải một multikey index cho array chứa nhiều phần tử. Nếu field được index trở thành array, MongoDB có các giới hạn khiến index không chấp nhận kiểu dữ liệu đó trong nhiều tình huống. Vì vậy nên chọn **khóa scalar ổn định** (String, ObjectId, số phù hợp...) thay vì `List<String>` làm hashed key.

## 12. Hashed index và sharding: phải nhìn cardinality

Một trong các động cơ dùng hashed key là **phân phối dữ liệu và write traffic** khi collection được sharding. Chẳng hạn, event ID tăng tuần tự có thể tạo điểm nóng nếu shard theo range; dùng hashed shard key có thể phân phối các giá trị ID trên các miền hash.

Sơ đồ ý tưởng:

~~~mermaid
flowchart LR
    A["Event IDs tăng dần"] --> B["Hash shard key"]
    B --> C["Hash range A"]
    B --> D["Hash range B"]
    B --> E["Hash range C"]
    C --> F["Shard 1"]
    D --> G["Shard 2"]
    E --> H["Shard 3"]
~~~

Tuy nhiên:

1. **Tạo hashed index không tự bật sharding**. Quản trị viên cần cấu hình sharded collection và shard key phù hợp theo cơ chế MongoDB.
2. **Cardinality quan trọng**. Nếu chỉ có ba giá trị tenantId nhưng hàng triệu document mỗi tenant, băm `tenantId` vẫn chỉ có ba hash values; không thể kỳ vọng phân phối tốt cho mọi workload.
3. **Khóa equality giúp định tuyến** khi shard key được cung cấp đúng; query không mang thông tin shard key có thể phải truy vấn nhiều shard.
4. **Range locality đánh đổi với distribution**. Shard key hashed phù hợp truy cập theo ID hơn các bài toán quét dải ID theo thứ tự.
5. **Uniqueness và hashed shard key** có các ràng buộc riêng trên sharded collection; không suy rằng một unique index thường ngoài shard key luôn bảo đảm uniqueness toàn cụm.

### 12.1. Khi nào customerId là hashed key tốt?

Nếu `customerId` có hàng triệu giá trị khác nhau và mỗi khách hàng có số document tương đối vừa phải, hashed distribution có thể giúp giảm tình trạng khóa tăng tuần tự dồn vào một miền. Nhưng nếu một `customerId` duy nhất phát sinh 40% write traffic, **hash không chia một giá trị giống nhau thành nhiều hash**; hot key vẫn tồn tại.

Không chọn shard key chỉ từ một biểu đồ phân phối lý thuyết. Cần phân tích kích thước document, write pattern, read targeting, tenant isolation, transaction, migration và chiến lược resharding.

### 12.2. Compound hashed index

Trong các phiên bản MongoDB hỗ trợ, compound hashed index có thể kết hợp field thường và một hashed field, ví dụ:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, customerId: "hashed" },
  { name: "idx_tenant_customer_hashed" }
);
~~~

Không coi compound hashed index là index unique và không giả định mọi phiên bản server chấp nhận cùng key pattern. Khi thiết kế sharding, còn cần kiểm tra **thứ tự shard key**, tính đồng đều và khả năng định tuyến query.

## 13. Wildcard index: khi tên field thay đổi theo từng document

Giả sử các loại sản phẩm có thuộc tính riêng:

~~~json
{
  "_id": "p-bottle",
  "attributes": {
    "material": "steel",
    "capacityMl": 500,
    "insulated": true
  }
}
~~~

~~~json
{
  "_id": "p-shirt",
  "attributes": {
    "size": "M",
    "fabric": "cotton",
    "color": "blue"
  }
}
~~~

Không thể tạo thủ công một index tốt cho **mọi** tên field tùy biến khi hệ thống có hàng nghìn thuộc tính. Wildcard index cho phép index các đường dẫn dưới `attributes`:

~~~javascript
db.catalog_products.createIndex(
  { "attributes.$**": 1 },
  { name: "idx_product_attributes_wildcard" }
);
~~~

Những query có thể được xem xét để dùng index này:

~~~javascript
db.catalog_products.find({
  "attributes.material": "steel"
});

db.catalog_products.find({
  "attributes.capacityMl": { $gte: 500 }
});

db.catalog_products.find({
  "attributes.fabric": "cotton"
});
~~~

**Wildcard index là index trên các đường dẫn BSON**, không phải cơ chế full-text search cho mọi chuỗi hay thay thế `2dsphere` cho mọi field địa lý.

### 13.1. Cú pháp $** và attributes.$**

| Key pattern | Phạm vi |
|---|---|
`{ "$**": 1 }` | Wildcard trên nhiều đường dẫn của document (theo quy tắc index của MongoDB) |
`{ "attributes.$**": 1 }` | Tập trung vào các field con bên trong `attributes` |

Với sản phẩm, scoped wildcard `attributes.$**` thường dễ quản lý hơn: tránh lập index vô tình cho nhiều field ngoài miền thuộc tính động như description hoặc metadata nội bộ.

**Đừng tự coi wildcard index là một index B-tree compound lý tưởng cho mọi sort.** Nó có cấu trúc/giới hạn riêng và thường tối ưu nhất khi một thuộc tính động là filter quan trọng của query.

### 13.2. Wildcard index không tự giải quyết mọi phép AND

Một query:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  "attributes.material": "steel",
  "attributes.capacityMl": { $gte: 500 }
})
.sort({ createdAt: -1 });
~~~

không có nghĩa wildcard index sẽ vừa giới hạn chặt chẽ mọi điều kiện, vừa đáp ứng sort mà không cần thêm công việc. Cần xem explain để biết index bounds, residual filters và `SORT`. Với những thuộc tính được dùng thường xuyên, index cụ thể theo field hoặc mô hình dữ liệu khác có thể tốt hơn.

### 13.3. Compound wildcard index: kiểm tra phiên bản

Ở những MongoDB server hỗ trợ **compound wildcard index** (MongoDB 7.0+), có thể thiết kế index kết hợp prefix có cấu trúc và một wildcard field:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, "attributes.$**": 1 },
  { name: "idx_tenant_attributes_wildcard" }
);
~~~

Đây là **ví dụ phụ thuộc phiên bản**, không phải lệnh chắc chắn chạy trên MongoDB 4.2/5.0/6.0. Các ràng buộc về vị trí field, sort, multikey và wildcard paths phải được kiểm tra theo release. Nếu server chưa hỗ trợ, dùng wildcard index độc lập cùng index tenant phù hợp và chấp nhận/đo chi phí lọc bổ sung, hoặc thay thiết kế schema.

## 14. Wildcard index và giới hạn cần nắm

### 14.1. Cấu trúc động có giá

Wildcard index có thể tạo nhiều index entries cho những đường dẫn thực tế có trong document. Nếu mỗi sản phẩm có một map vài nghìn thuộc tính, index size và chi phí update có thể tăng đáng kể.

Nó hữu ích cho **field khó dự đoán**, nhưng không tự hiệu quả hơn index cố định khi workload có một vài field nóng. So sánh:

- Query 90% tập trung vào `attributes.material` → index cụ thể có thể đơn giản hơn.
- Query phân tán trên hàng trăm field tùy category → wildcard có giá trị hơn.
- Query luôn có tenant + sort by createdAt → có thể cần kết hợp kế hoạch index khác hoặc server phiên bản hỗ trợ compound wildcard với điều kiện phù hợp.

### 14.2. Mảng, document lồng và null

Các giá trị `attributes` có thể là scalar, array hoặc document lồng. Wildcard indexing trên nested arrays có các quy tắc cụ thể về **đường dẫn được index, bounds và khả năng hỗ trợ sort**. Không mặc định một query trên array of documents bảo đảm các điều kiện áp dụng cho **cùng phần tử**.

Ví dụ:

~~~json
{
  "attributes": {
    "variants": [
      { "color": "RED", "stock": 2 },
      { "color": "BLUE", "stock": 12 }
    ]
  }
}
~~~

Query dot path:

~~~javascript
{
  "attributes.variants.color": "RED",
  "attributes.variants.stock": { $gte: 10 }
}
~~~

có thể khớp **hai phần tử khác nhau**. Nếu cần một variant RED có stock ít nhất 10, dùng `$elemMatch`:

~~~javascript
db.catalog_products.find({
  "attributes.variants": {
    $elemMatch: {
      color: "RED",
      stock: { $gte: 10 }
    }
  }
});
~~~

Index, kể cả wildcard/multikey, **không thay thế việc viết predicate đúng**.

### 14.3. Không dùng wildcard để thay unique, text và geospatial

Wildcard index không được xem là một phép tạo **unique constraint cho tất cả các field động**. Cũng không nên kỳ vọng nó hỗ trợ `$text` ranking hay `$near` trên GeoJSON như index chuyên dụng.

Khi nghiệp vụ cần:

- Unique SKU → unique B-tree/compound index đúng business key.
- Full-text term matching → text index hoặc search index chuyên dụng.
- Distance/region → 2dsphere.
- Thuộc tính động thường chỉ lọc equality/range → wildcard là một ứng viên.

Không dùng `{ "$**": 1 }` làm “giải pháp tối ưu mọi truy vấn” chỉ vì nó bao phủ nhiều field.

## 15. Bảng quyết định: chọn index theo query shape

| Truy vấn phổ biến | Index ứng viên | Không nên ngộ nhận |
|---|---|---|
`$text: { $search: "bottle" }` | Text trên name/description | Không phải substring search tự do |
`$near` với GeoJSON Point | 2dsphere trên location | Không phải B-tree index trên longitude |
`$geoWithin` polygon | 2dsphere | Không mặc định trả thứ tự gần nhất |
`customerId = X`, key phân phối lớn | Hashed có thể phù hợp | Không hỗ trợ range/sort hay unique như B-tree |
`customerId >= X` rồi sort | B-tree index trên customerId | Hashed phá thứ tự giá trị gốc |
`attributes.material = "steel"` | Wildcard hoặc field index cụ thể | Không phải full-text search |
Truy vấn nhiều thuộc tính động trong tenant | Wildcard/compound wildcard tùy version | Không tự tối ưu mọi AND/sort |
`tenantId + sku` phải unique | Unique compound B-tree | Không thay bằng hashed unique |
Tìm sản phẩm mới nhất theo tenant/status | Compound B-tree với equality + sort | Text/geo/wildcard không phải index mặc định |

### Cây quyết định ngắn

~~~mermaid
flowchart TD
    A["Mục tiêu truy vấn"] --> B{"Theo vị trí/khoảng cách?"}
    B -->|"Có"| C["2dsphere / 2d đúng hệ tọa độ"]
    B -->|"Không"| D{"Theo term văn bản?"}
    D -->|"Có"| E["Text index hoặc Search chuyên dụng"]
    D -->|"Không"| F{"Theo field động khó dự đoán?"}
    F -->|"Có"| G["Wildcard / index chuyên biệt cho field nóng"]
    F -->|"Không"| H{"Equality trên khóa cần phân tán?"}
    H -->|"Có"| I["Cân nhắc hashed + phân tích sharding"]
    H -->|"Không"| J["B-tree single/compound"]
    C --> K["Explain và đo trên workload thật"]
    E --> K
    G --> K
    I --> K
    J --> K
~~~

Một workload có thể dùng **nhiều loại index** trên cùng collection, nhưng mỗi index phải có lý do và phải xét tổng chi phí vận hành.

## 16. Tạo và liệt kê index qua MongoTemplate và Java Driver

Với Spring Data MongoDB, `MongoTemplate.indexOps(...)` rất tiện cho index thường và các metadata được hỗ trợ. Với key pattern đặc biệt `"text"`, `"hashed"`, `"$**"`, đôi khi dùng MongoDB Java Driver bên dưới `MongoTemplate` giúp biểu diễn BSON chính xác và độc lập với biến thể builder theo phiên bản.

**CatalogSpecialIndexProvisioner.java**

~~~java
package com.example.catalog;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

@Component
public class CatalogSpecialIndexProvisioner {
    private final MongoTemplate mongo;

    public CatalogSpecialIndexProvisioner(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    // Hãy thực hiện qua migration/provisioning được quản lý,
    // không gọi trong mỗi HTTP request.
    public void ensureSpecialIndexes() {
        MongoCollection<Document> collection =
                mongo.getCollection("catalog_products");

        collection.createIndex(
                new Document("name", "text")
                        .append("description", "text"),
                new IndexOptions()
                        .name("idx_product_text")
                        .weights(new Document("name", 5)
                                .append("description", 1)));

        collection.createIndex(
                new Document("pickupLocation", "2dsphere"),
                new IndexOptions().name("idx_pickup_2dsphere"));

        collection.createIndex(
                new Document("customerId", "hashed"),
                new IndexOptions().name("idx_customer_hashed"));

        collection.createIndex(
                new Document("attributes.$**", 1),
                new IndexOptions().name("idx_attributes_wildcard"));
    }

    public List<Document> listRawIndexes() {
        MongoCollection<Document> collection =
                mongo.getCollection("catalog_products");
        List<Document> indexes = new ArrayList<>();
        collection.listIndexes().into(indexes);
        return indexes;
    }
}
~~~

Đây là code **provisioning minh họa**. Trong production, phải quyết định chiến lược quản lý index, quyền tạo index, kiểm tra thay đổi options, thời gian index build và khả năng rollback. Method `createIndex` có thể báo lỗi nếu tên index đã tồn tại nhưng định nghĩa khác, hoặc server không hỗ trợ một key pattern.

### 16.1. Không tự trộn mọi API index

Nếu entity đã có `@GeoSpatialIndexed` và ứng dụng bật auto-index creation, việc migration đồng thời tạo thêm index cùng field có thể sinh index trùng hoặc xung đột tên/options. Hãy **chọn một nguồn định nghĩa index chủ đạo**, ví dụ migration có kiểm soát.

Các annotation/DSL chuyên dụng của Spring Data như `@TextIndexed` và `@GeoSpatialIndexed` hữu ích cho metadata; khi một feature mới chỉ có ở bản server/driver nhất định, raw BSON phải được đánh giá trên phiên bản đang chạy.

### 16.2. Xem chính xác các index đã tạo

Trong mongosh:

~~~javascript
db.catalog_products.getIndexes();
~~~

Các field cần xem:

1. `name`: đúng tên index mong muốn.
2. `key`: chứa `"text"`, `"2dsphere"`, `"hashed"` hay `"attributes.$**"` theo định nghĩa thích hợp.
3. `weights`/`default_language` của text index.
4. `2dsphereIndexVersion` hoặc metadata chuyên dụng, nếu server trả về.
5. `unique`/`partialFilterExpression`/`collation` nếu dùng.

**Chú ý text index:** MongoDB có thể lưu `key` dạng nội bộ/đặc biệt, ví dụ liên quan `_fts` và `_ftsx` thay vì nguyên mẫu `{ name: "text", description: "text" }`. Vì vậy test nên đọc metadata `weights`/`name`/type phù hợp, không bắt buộc so khớp nguyên văn key pattern đầu vào trên mọi phiên bản.

## 17. Explain: kiểm tra index được dùng cho truy vấn nào

Tạo index chỉ là bước đầu. Một index có thể tồn tại nhưng planner chọn index khác hoặc COLLSCAN.

### 17.1. Text

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  $text: { $search: "water bottle" }
})
.explain("executionStats");
~~~

Kiểm tra plan text search, số documents examined và số kết quả. Plan có thể dùng stage tên riêng cho text search tùy MongoDB version; đừng chỉ grep `IXSCAN` rồi kết luận text index không hoạt động.

### 17.2. Geo

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  pickupLocation: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  }
})
.explain("executionStats");
~~~

Các stage geo có thể hiển thị thông tin như `GEO_NEAR` hoặc cấu trúc plan đặc biệt, tùy server. Cần kiểm tra index geospatial được chọn, số key/document xem xét và tổng thời gian; số lượng document ở ngoài bán kính ảnh hưởng hiệu năng.

### 17.3. Hashed

~~~javascript
db.catalog_products.find({
  customerId: "cust-100127"
})
.explain("executionStats");
~~~

So sánh với một B-tree index trên customerId nếu workload cũng cần range/sort. Dữ liệu ít hoặc field có tính chọn lọc thấp có thể khiến planner không ưu tiên hashed index.

### 17.4. Wildcard

~~~javascript
db.catalog_products.find({
  "attributes.material": "steel"
})
.explain("executionStats");
~~~

Quan sát index name, key bounds, `totalKeysExamined`, `totalDocsExamined`, `nReturned` và có hay không blocking sort. Query trên `attributes.capacityMl` có thể có plan khác dù dùng cùng wildcard index.

### 17.5. Đừng kết luận từ một con số

| Chỉ số/quan sát | Điều cần hiểu |
|---|---|
`nReturned` | Có bao nhiêu document output |
`totalKeysExamined` | Có bao nhiêu index keys được xem |
`totalDocsExamined` | Có bao nhiêu document được truy cập |
`executionTimeMillis` | Thời gian thực thi của lần explain, không phải p95 production |
`COLLSCAN` | Có thể hợp lý với collection rất nhỏ |
Blocking `SORT` | Có thể tốn memory/CPU khi nhiều document |
Index name đúng | Không đủ nếu số keys/docs scanned vẫn rất cao |
Index chưa được dùng | Có thể do query shape, stats, cache, collation hoặc dữ liệu nhỏ |

Đo trên dữ liệu đại diện, nhất là các tenant có số lượng sản phẩm chênh lệch. Không bật `hint` chỉ để ép index trông “đúng” nếu chưa đo toàn bộ trade-off.

## 18. Kiểm thử tích hợp với MongoDB thật

Mock `MongoTemplate` có thể xác nhận service được gọi, nhưng không thể chứng minh:

- Text index được tạo và `$text` thực sự tìm được term.
- GeoJSON lưu đúng thứ tự tọa độ và `2dsphere` phục vụ `$near`.
- Hashed index tồn tại đúng định nghĩa và không bị nhầm với unique index.
- Wildcard index chứa đúng key pattern.
- Các filter tenant được giữ trong query.

Nên dùng MongoDB test thực (ví dụ Testcontainers). `@DataMongoTest` của Spring Boot 3.x **không tự khởi động MongoDB server**.

### 18.1. Test seed ba sản phẩm và bốn index

**CatalogSpecialIndexesTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.IndexOptions;
import java.util.List;
import java.util.Map;
import org.bson.Document;
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
@Import({
        CatalogTextSearchService.class,
        CatalogGeoSearchService.class
})
class CatalogSpecialIndexesTest {
    @Autowired MongoTemplate mongo;
    @Autowired CatalogTextSearchService textSearch;
    @Autowired CatalogGeoSearchService geoSearch;

    @BeforeEach
    void prepare() {
        // Chỉ xóa collection trên database test cô lập.
        mongo.dropCollection(CatalogProduct.class);
        var collection = mongo.getCollection("catalog_products");

        // Quản lý index tường minh trong test: tránh duplicate
        // với auto-index-creation của entity.
        collection.createIndex(
                new Document("name", "text")
                        .append("description", "text"),
                new IndexOptions().name("idx_product_text"));
        collection.createIndex(
                new Document("pickupLocation", "2dsphere"),
                new IndexOptions().name("idx_pickup_2dsphere"));
        collection.createIndex(
                new Document("customerId", "hashed"),
                new IndexOptions().name("idx_customer_hashed"));
        collection.createIndex(
                new Document("attributes.$**", 1),
                new IndexOptions().name("idx_attributes_wildcard"));

        mongo.insert(List.of(
                new CatalogProduct(
                        "p-101", "tenant-a", "cust-101",
                        "Steel water bottle",
                        "Insulated reusable water bottle",
                        "DRINKWARE",
                        new GeoJsonPoint(106.70098, 10.77689),
                        Map.of("material", "steel", "capacityMl", 500)),
                new CatalogProduct(
                        "p-102", "tenant-a", "cust-102",
                        "Ceramic mug",
                        "Hot drink mug",
                        "DRINKWARE",
                        new GeoJsonPoint(106.72000, 10.79000),
                        Map.of("material", "ceramic", "capacityMl", 250)),
                new CatalogProduct(
                        "p-201", "tenant-b", "cust-201",
                        "Water bottle",
                        "Travel bottle",
                        "DRINKWARE",
                        new GeoJsonPoint(106.70100, 10.77690),
                        Map.of("material", "steel", "capacityMl", 750))
        ), CatalogProduct.class);
    }

    @Test
    void textSearchUsesTenantFilter() {
        List<CatalogProduct> result =
                textSearch.search("tenant-a", "water bottle", 10);

        assertThat(result).extracting(CatalogProduct::getId)
                .containsExactly("p-101");
    }

    @Test
    void geoQueryExcludesNearbyProductFromOtherTenant() {
        List<CatalogProduct> result =
                geoSearch.nearby(
                        "tenant-a",
                        106.70098, 10.77689,
                        5000, 20);

        assertThat(result).extracting(CatalogProduct::getId)
                .containsExactly("p-101", "p-102");
    }

    @Test
    void wildcardDynamicFieldQueryReturnsExpectedProduct() {
        Query query = Query.query(
                Criteria.where("tenantId").is("tenant-a")
                        .and("attributes.material").is("steel"));

        List<CatalogProduct> result =
                mongo.find(query, CatalogProduct.class);
        assertThat(result).extracting(CatalogProduct::getId)
                .containsExactly("p-101");
    }

    @Test
    void hashedFieldCanBeQueriedByEquality() {
        Query query = Query.query(
                Criteria.where("customerId").is("cust-102")
                        .and("tenantId").is("tenant-a"));

        List<CatalogProduct> result =
                mongo.find(query, CatalogProduct.class);
        assertThat(result).extracting(CatalogProduct::getId)
                .containsExactly("p-102");
    }

    @Test
    void specializedIndexDefinitionsExistOnServer() {
        List<Document> indexes =
                mongo.getCollection("catalog_products")
                        .listIndexes()
                        .into(new java.util.ArrayList<>());

        assertThat(indexes).extracting(
                document -> document.getString("name"))
                .contains(
                        "idx_product_text",
                        "idx_pickup_2dsphere",
                        "idx_customer_hashed",
                        "idx_attributes_wildcard");

        Document geo = indexes.stream()
                .filter(i -> "idx_pickup_2dsphere"
                        .equals(i.getString("name")))
                .findFirst().orElseThrow();
        assertThat(geo.get("key", Document.class)
                .getString("pickupLocation")).isEqualTo("2dsphere");

        Document hash = indexes.stream()
                .filter(i -> "idx_customer_hashed"
                        .equals(i.getString("name")))
                .findFirst().orElseThrow();
        assertThat(hash.get("key", Document.class)
                .getString("customerId")).isEqualTo("hashed");
    }
}
~~~

**Những điều test trên chứng minh được:**

- Text search tìm theo index đã tạo, nhưng không lộ kết quả tenant-b.
- Geospatial query tìm đúng hai điểm của tenant-a trong bán kính, gần nhất trước.
- Query vào field động `attributes.material` trả đúng document.
- Equality query trên khóa hashed hoạt động.
- Geo/hashed index tồn tại đúng key type.

**Những điều test không tự chứng minh:** với ba document, planner có thể chọn COLLSCAN cho một số query; test không là benchmark. Test cũng không chứng minh một cấu hình shard key phân phối tốt trong production. Phần text dùng term tiếng Anh để kiểm tra cơ chế cơ bản; chất lượng tìm kiếm tiếng Việt phải được test riêng.

### 18.2. Những trường hợp cần bổ sung

| Ca test | Kỳ vọng |
|---|---|
Text index chưa tồn tại | `$text` có thể lỗi; không được im lặng fallback sang regex |
Đổi weights hoặc default language | Phải qua migration index, không tạo hai text indexes cạnh tranh |
Hai document text có độ liên quan khác nhau | Kiểm tra score/ranking ở đúng version |
Tìm term tiếng Việt có và không dấu | Ghi nhận limitations/analyzer strategy |
Đảo longitude và latitude | Test phát hiện điểm sai hoặc validation lỗi |
Điểm ngoài `maxDistance` | Không được trả |
GeoJSON field thiếu/null/sai kiểu | Query/index và ingestion có policy rõ ràng |
`$geoWithin` polygon | Chỉ document trong polygon hợp lệ |
Hashed key là array | Kiểm tra giới hạn hashed/multikey và lỗi ghi |
Hashed index + range/sort | Không suy index hỗ trợ thứ tự gốc |
Hai tenant cùng mã business | Không trông đợi hashed unique |
Wildcard có field động chưa có trước đó | Query mới vẫn xét index nếu schema/index phù hợp |
Wildcard nested array | Kiểm tra `$elemMatch` cùng phần tử |
Thay đổi index options/định nghĩa cùng tên | Migration xử lý xung đột rõ ràng |
Nhiều test chạy song song | Phải cô lập database/collection |

## 19. Hiệu năng và chi phí duy trì bốn index

Index chuyên dụng vẫn tiêu tốn tài nguyên. Khi product được thêm hoặc sửa:

- **Text index:** thay `name`/`description` có thể khiến các term entries phải được cập nhật.
- **2dsphere:** thay vị trí/geometry khiến index entry địa lý thay đổi.
- **Hashed:** thay `customerId` buộc tính hash mới và cập nhật entry.
- **Wildcard:** thay `attributes` với nhiều nested field có thể cập nhật nhiều entries.

### 19.1. Benchmark nên đo gì?

| Chỉ số | Ý nghĩa |
|---|---|
Read p50/p95/p99 | Độ trễ thực tế theo từng query shape |
`totalKeysExamined` | Mức quét khóa index |
`totalDocsExamined` | Mức FETCH/đọc document |
`nReturned` | Số document thực trả |
Index disk/cache footprint | Tài nguyên index chiếm dụng |
Insert/update throughput | Giá phải trả khi duy trì index |
Build time | Chi phí migration trên collection lớn |
Text search relevance | Chất lượng kết quả ngoài tốc độ |
Geo distance correctness | Khoảng cách, tọa độ và radius chính xác |
Sharding distribution | Tỷ lệ dữ liệu/traffic trên từng shard |
Wildcard dynamic-field coverage | Tỷ lệ query dùng index và residual filters |

Không có công thức cố định rằng “wildcard luôn chậm hơn index thường X lần” hoặc “hashed luôn nhanh hơn B-tree”. Kết quả phụ thuộc cardinality, dữ liệu, workload và server topology.

### 19.2. Tránh tạo index thừa

Giả sử một collection đồng thời có:

~~~javascript
{ name: "text", description: "text" }
{ pickupLocation: "2dsphere" }
{ customerId: "hashed" }
{ "attributes.$**": 1 }
{ tenantId: 1, category: 1, createdAt: -1 }
~~~

Đây có thể là tổ hợp hợp lý nếu ứng dụng thực sự có năm loại query khác nhau, nhưng cũng có thể quá nhiều nếu phần lớn request chỉ lọc theo tenant/category.

Quy trình:

1. Thu thập query shape thật và tần suất.
2. Kiểm tra index hiện hữu, bao gồm index text/geo đã được annotation tạo.
3. Chọn ứng viên theo loại toán tử.
4. Benchmark read/write và index size.
5. Chỉ triển khai index có lợi ích rõ ràng.
6. Theo dõi `$indexStats` trong một cửa sổ hoạt động đại diện; không xóa chỉ vì thống kê ngắn hạn thấp.

## 20. Bảo mật và sự đúng đắn khi truy vấn đặc biệt

### 20.1. Tenant isolation áp dụng cho cả text và geo

Sai:

~~~javascript
db.catalog_products.find({
  $text: { $search: "water bottle" }
});
~~~

Đúng với dữ liệu đa tenant:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  $text: { $search: "water bottle" }
});
~~~

Điều kiện tương tự phải áp dụng cho `$near`, `$geoNear.query` và các filter dynamic attributes. **Index không phải cơ chế phân quyền**; một truy vấn có index tốt nhưng quên `tenantId` vẫn có thể rò dữ liệu.

### 20.2. Whitelist field dynamic

Không chấp nhận HTTP request như:

~~~json
{
  "fieldPath": "anything.from.client",
  "operator": "$regex",
  "value": ".*"
}
~~~

rồi đưa nguyên vào BSON query. Với wildcard index, ứng dụng càng dễ bị cám dỗ cho phép query field path tùy ý. Hãy kiểm soát:

- Những thuộc tính nào được phép tìm (`material`, `capacityMl`, `color`...).
- Những toán tử nào được phép dùng (`eq`, một số range có giới hạn...).
- Kiểu dữ liệu/miền giá trị của từng thuộc tính.
- Độ dài text search, bán kính geo, số kết quả và timeout.
- Tenant và các chính sách ủy quyền phía server.

Trong Java, có thể dùng enum/switch để map tên thuộc tính cho phép sang path cố định, thay vì ghép arbitrary path từ input:

~~~java
String fieldPath = switch (requestedAttribute) {
    case "material" -> "attributes.material";
    case "capacityMl" -> "attributes.capacityMl";
    case "color" -> "attributes.color";
    default -> throw new IllegalArgumentException(
            "Thuộc tính không được phép lọc");
};

Query query = Query.query(
        Criteria.where("tenantId").is(authenticatedTenantId)
                .and(fieldPath).is(validatedValue));
~~~

Đây là đoạn minh họa đặt trong service có các biến `requestedAttribute`, `authenticatedTenantId` và `validatedValue` đã được xác thực/validate, không phải file Java độc lập. Cần kiểm tra kiểu giá trị tương ứng trước khi đặt vào query.

### 20.3. Location và privacy

Vị trí có thể là dữ liệu nhạy cảm. Không log raw tọa độ cá nhân, địa chỉ hay query geo trong production nếu không được phép. Nếu app chỉ cần tìm cửa hàng, không nên thu/ghi lại vị trí chính xác của người dùng lâu hơn yêu cầu nghiệp vụ.

Không trả toàn bộ GeoJSON hoặc dữ liệu khách hàng trong API khi chỉ cần tên sản phẩm, khoảng cách và vài thuộc tính công khai. Thiết kế DTO/response whitelist phù hợp.

## 21. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
Cho rằng text index là substring index | Search không tìm như mong đợi | Phân biệt term, phrase, regex, autocomplete |
Tạo hai text indexes trên cùng collection | Index build thất bại | Gộp field vào một text index |
Không kiểm tra language của text | Tokenization/stemming không hợp dữ liệu | Chọn language, test tiếng Việt, cân nhắc Search |
Cho rằng `textScore` là xác suất | Ranking/threshold sai | Đo relevance, không xem score là % |
Quên `$meta: "textScore"` khi cần score | Không thấy điểm liên quan | Thêm projection/sort metadata phù hợp |
Dùng regex bất kỳ và kỳ vọng text index tăng tốc | COLLSCAN hoặc scan rộng | Thiết kế đúng query/search index |
Đảo longitude/latitude | Tìm vị trí sai | Quy ước `[longitude, latitude]` và test |
Nhầm mét với radian | Bán kính sai rất lớn | Kiểm tra GeoJSON vs legacy operator |
Cho rằng `$geoWithin` tự sắp gần nhất | UI thứ tự sai | Dùng geoNear hoặc tính/sort distance |
Quên `$geoNear` phải đứng đầu pipeline | Aggregation lỗi | Đặt stage đầu và filter trong `query` |
Tin 2d phù hợp mọi GeoJSON trên Trái Đất | Sai hệ tọa độ/hình học | Chọn 2dsphere |
Gọi hashed index là unique index | Duplicate business key | Unique B-tree/compound riêng |
Sử dụng hashed cho range/sort | Không dùng được thứ tự gốc | Index thường phù hợp hơn |
Băm một tenantId ít giá trị để phân tán nhiều shard | Hot key/hot shard vẫn tồn tại | Phân tích cardinality/shard key |
Nghĩ tạo hashed index là đã sharding | Không có dữ liệu phân tán | Sharding cần quản trị riêng |
Đưa array vào hashed key | Vi phạm giới hạn indexed type | Dùng scalar ổn định |
Dùng wildcard để thay text/2dsphere | Không có semantics toán tử cần thiết | Chọn index chuyên dụng |
Tạo wildcard toàn document vô tội vạ | Index lớn, ghi chậm | Scope `attributes.$**` và đo |
Tưởng compound wildcard hoạt động trên MongoDB cũ | Index command không được hỗ trợ | Kiểm tra version (7.0+) |
Cho rằng wildcard tự tối ưu mọi AND/sort | Residual filter/SORT tốn tài nguyên | Explain, index riêng cho field nóng |
Cho phép field path tùy ý từ client | Rủi ro bảo mật/truy vấn nặng | Whitelist field/operator |
Quên filter tenant trong text/geo query | Rò dữ liệu tenant khác | Đặt tenant từ auth context vào BSON |
Chỉ dùng mock test | Không biết index/geo/text chạy thật | Integration test trên MongoDB |
Chỉ nhìn index tồn tại mà kết luận hiệu năng | Planner có thể không chọn index | Explain và benchmark |

## 22. Bài tập thực hành

**Bài 1 — Text cơ bản.** Tạo một text index trên `name`/`description`, chạy `$text` tìm `water bottle`, đối chiếu kết quả với equality và regex. Giải thích vì sao ba phép tìm không tương đương.

**Bài 2 — Weights và score.** Đặt weight của `name` lớn hơn `description`. Seed document khớp ở tên, một document khớp ở mô tả; đọc `textScore` và kiểm tra thứ tự theo relevance. Không dùng số score như xác suất.

**Bài 3 — Tiếng Việt.** Tạo dữ liệu chứa `Bình giữ nhiệt`, `bình giữ nhiệt` và phiên bản không dấu. So sánh behavior với text index có language phù hợp/`none` trên database test, ghi hạn chế và đề xuất analyzer/search phù hợp.

**Bài 4 — GeoJSON Point.** Tạo hai điểm gần và một điểm xa. Viết `$near` với bán kính theo mét; cố tình đảo lon/lat trong test để phát hiện lỗi dữ liệu.

**Bài 5 — GeoWithin Polygon.** Tạo polygon đóng vòng, tìm điểm trong/ngoài khu vực. Thử polygon không hợp lệ và xác định chính sách validation cho API.

**Bài 6 — GeoNear distance.** Dùng `$geoNear` tính `distanceMeters`, filter tenant ngay trong `query`. So sánh thứ tự nearest-first với `$geoWithin` không sort.

**Bài 7 — Hashed equality.** Tạo index `{ customerId: "hashed" }`, thử equality, range và sort, xem explain. Giải thích vì sao không được dùng hashed index làm unique business constraint.

**Bài 8 — Shard key.** Mô phỏng 100.000 event ID tuần tự và hai lựa chọn shard key: range và hashed. Đánh giá phân phối key, targeting query và truy cập theo khoảng; không chỉ kết luận từ số shard.

**Bài 9 — Wildcard attributes.** Tạo các sản phẩm có những field động khác nhau. Index `attributes.$**` rồi truy vấn `material`, `capacityMl`, `fabric`. So sánh với index cụ thể trên field được tìm nhiều nhất.

**Bài 10 — Wildcard và array.** Thêm array `attributes.variants`, kiểm tra dot-path query và `$elemMatch`. Chứng minh index không tự sửa lỗi cross-element matching.

**Bài 11 — Compound wildcard.** Trên MongoDB 7.0+ trong test, tạo index `{ tenantId: 1, "attributes.$**": 1 }`, so sánh query có/không tenant. Nếu môi trường không hỗ trợ, ghi lại giới hạn phiên bản và dùng phương án khác.

**Bài 12 — Spring Data mapping.** Thêm `@GeoSpatialIndexed`, dùng `GeoJsonPoint` và `Criteria.nearSphere`; viết `TextQuery` với tenant filter. Kiểm tra raw BSON và kết quả trên MongoDB thật.

**Bài 13 — Index migration.** Cố tình tạo text index với language/weights khác, sau đó đổi metadata. Thiết kế quy trình migration không tạo hai text indexes, bảo đảm rollback và đo chi phí index build.

**Bài 14 — Benchmark.** Seed dữ liệu lớn có nhiều tenant và thuộc tính động. Đo p95 text/geo/hashed/wildcard, `keysExamined`/`docsExamined`, kích thước index và tốc độ insert/update trước/sau. Đưa ra quyết định giữ/bỏ từng index từ số đo thực.

## 23. Ghi nhớ

**Text index** phục vụ **tìm kiếm term** qua `$text` và có thể dùng `textScore`, nhưng không phải substring search, autocomplete hay fuzzy search tổng quát. Cần kiểm soát language, trọng số field và cân nhắc search chuyên dụng cho tiếng Việt hoặc ranking phức tạp.

**Geospatial index** đòi hỏi đúng hệ tọa độ và toán tử. Với vị trí địa lý, **GeoJSON + 2dsphere** hỗ trợ truy vấn khoảng cách/vùng; luôn ghi `[longitude, latitude]`, kiểm tra đơn vị mét/radian, giới hạn bán kính và lọc tenant ở database.

**Hashed index** phù hợp **equality** trên khóa có cardinality thích hợp và có thể hỗ trợ thiết kế hashed sharding; nó **không tự sharding**, không thay unique index và không phục vụ range/sort theo thứ tự gốc. **Wildcard index** hỗ trợ field động như `attributes.*`, nhưng không tối ưu mọi AND/sort, không thay text/geo và có thể tạo rất nhiều index entries.

Trong **Spring Data MongoDB**, dùng đúng công cụ cho từng yêu cầu: `TextCriteria`/`TextQuery`, `GeoJsonPoint`/`Criteria`, metadata `@TextIndexed`/`@GeoSpatialIndexed` và `MongoTemplate`/Java Driver để quản lý các index cần BSON đặc biệt. **Chỉ chấp nhận một thiết kế index sau khi đã xác minh index thực sự tồn tại, kết quả truy vấn đúng, security filter đủ và `explain("executionStats")`/benchmark cho workload đại diện.**
