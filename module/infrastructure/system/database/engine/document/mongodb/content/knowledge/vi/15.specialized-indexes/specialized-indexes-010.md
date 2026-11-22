# Giới hạn index theo kiểu collection, phiên bản và mô hình triển khai trong MongoDB

MongoDB có nhiều loại index phục vụ những nhu cầu khác nhau: B-tree index thông thường, **TTL**, **text**, **geospatial (2d/2dsphere)**, **hashed**, **wildcard**, **multikey**, **partial**, **unique**, **clustered index**, cùng các hệ index tìm kiếm chuyên dụng như **MongoDB Search** và **MongoDB Vector Search**. Không phải mọi index đều có thể được tạo với cùng một cú pháp, trên mọi collection, ở mọi phiên bản hoặc trong mọi mô hình triển khai.

Ví dụ, một lệnh `createIndex({ location: "2dsphere" })` có thể hợp lệ cho collection thông thường, nhưng không có nghĩa nó được phép làm shard key. Một **standard view** có thể tận dụng index của collection nguồn, nhưng không có B-tree index riêng. **Time series collection** có cơ chế lưu theo bucket và hạn chế nhiều loại index. Một **unique index** hợp lệ trên collection đơn máy có thể không được chấp nhận khi collection được sharding. Còn **Search index** không thể đồng nhất với B-tree `text` index: cơ chế tạo, nơi triển khai và khả năng truy vấn khác nhau.

Bài học này cung cấp một cách ra quyết định có hệ thống theo **ba trục**:

1. **Kiểu collection:** normal, capped, time series, clustered, standard view hoặc collection kết quả materialized.
2. **Phiên bản và feature compatibility:** phiên bản binary của `mongod`, **featureCompatibilityVersion (FCV)**, phiên bản index và Stable API.
3. **Mô hình triển khai:** standalone, replica set, sharded cluster, Atlas, hay self-managed Community/Enterprise với các thành phần bổ sung.

> **Nguyên tắc thực hành:** Không suy luận “MongoDB hỗ trợ loại index X” thành “mọi MongoDB đều hỗ trợ X”. Trước khi dùng một tính năng chuyên biệt, phải xác nhận **version + FCV + collection type + topology + dịch vụ/tier có tính năng đó**. Các ví dụ có điều kiện được ghi rõ trong bài.

## 1. Ba tầng quyết định khả năng tạo index

Một index có thể bị giới hạn ở các bước khác nhau:

~~~text
Yêu cầu nghiệp vụ
      |
      v
1. Loại collection?
   normal / capped / time series / clustered / view
      |
      v
2. Phiên bản mongod, FCV, index version, Stable API?
      |
      v
3. Mô hình triển khai và dịch vụ?
   standalone / replica set / sharded / Atlas / self-managed
      |
      v
4. Kiểu dữ liệu và cấu hình index có hợp lệ?
   scalar / array / GeoJSON / Date / null / collation...
      |
      v
5. Có đủ quyền, tài nguyên và index build thành công?
      |
      v
6. Truy vấn có thực sự dùng được index?
   find()/aggregate() + explain()
~~~

**Tạo index thành công không đồng nghĩa truy vấn sẽ tự động dùng index.** Query planner còn dựa vào filter, sort, phân bố dữ liệu, tính đầy đủ của partial/sparse index, collation và chi phí thực thi. Vì vậy cần tách:

- **Hỗ trợ tính năng:** server cho phép định nghĩa index.
- **Khả năng xây dựng:** dữ liệu hiện có, quyền, dung lượng và quy tắc index cho phép build.
- **Khả năng sử dụng:** filter/sort/query tương thích index.
- **Lợi ích thực tế:** số key và document được xét giảm đủ để bù chi phí tạo, duy trì index.

## 2. Xác định môi trường trước khi viết lệnh createIndex()

### 2.1. Phiên bản server không phải phiên bản mongosh

Chạy trong `mongosh`:

~~~javascript
// Phiên bản server đang kết nối.
db.version();

// Thông tin build của server, nếu tài khoản được cấp quyền.
db.adminCommand({ buildInfo: 1 });

// Kiểm tra điểm kết nối là mongod hay mongos.
db.hello();
~~~

`db.version()` phản ánh server, còn phiên bản chương trình `mongosh` là chuyện khác. Một shell mới có thể kết nối server cũ, nhưng không khiến server cũ tự hỗ trợ tính năng index mới.

Kết quả `db.hello()` có thể giúp nhận diện topology. Khi kết nối `mongos` của sharded cluster, thường có `msg: "isdbgrid"`; kết nối `mongod` có những thông tin như `setName`/`isWritablePrimary` nếu thuộc replica set. Đừng suy luận một cluster chỉ từ tên máy hoặc chuỗi kết nối.

### 2.2. Feature Compatibility Version (FCV)

**FCV** kiểm soát việc sử dụng các tính năng và định dạng có thể không tương thích với phiên bản cũ khi upgrade/downgrade. Binary 8.x không đủ để đảm bảo tính năng gắn với FCV 8.x đã có hiệu lực.

Trên `mongod` khi có quyền:

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

**Lưu ý:** truy vấn FCV bằng `getParameter` phải thực hiện trên `mongod` phù hợp. Không áp dụng máy móc lệnh này trên `mongos` vì khả năng truy cập và cách quản trị khác. Trong cluster có sharding, cần kiểm tra kế hoạch FCV của toàn cluster qua quy trình vận hành phù hợp.

Không chủ động chạy `setFeatureCompatibilityVersion` chỉ để thử một index trong môi trường production. Đổi FCV là thao tác quản trị có tác động tới tính tương thích và rollback.

### 2.3. Nhận diện kiểu collection

~~~javascript
const labDb = db.getSiblingDB("index_limits_lab");

labDb.getCollectionInfos();
~~~

Các metadata cần quan sát:

| Metadata | Ý nghĩa |
| --- | --- |
| `type: "collection"` | Collection vật lý |
| `type: "view"` | Standard view tính từ aggregation pipeline |
| `options.capped` | Collection capped có giới hạn dung lượng |
| `options.timeseries` | Collection time series |
| `options.clusteredIndex` | Định nghĩa clustered index khi collection hỗ trợ |
| `options.viewOn` và `options.pipeline` | Nguồn và pipeline của view |

Cấu trúc chi tiết phụ thuộc phiên bản và loại collection. Không giả định mọi namespace được liệt kê đều có cùng lựa chọn tạo index.

Với collection thường:

~~~javascript
labDb.products.getIndexes();
~~~

`getIndexes()` cho biết **general indexes** của collection như `_id_`, B-tree, TTL hoặc geospatial. Nó **không phải** cách đáng tin để liệt kê toàn bộ MongoDB Search / Vector Search indexes; nhóm Search có API và trạng thái quản lý riêng.

## 3. Bảng so sánh khả năng index theo kiểu collection

| Kiểu đối tượng | General/B-tree index | Đặc điểm hoặc giới hạn quan trọng |
| --- | --- | --- |
| **Normal collection** | Hỗ trợ, gồm nhiều index chuyên biệt theo điều kiện riêng | Thường tạo `_id_` mặc định; kiểm tra data type/index options |
| **Capped collection** | Có thể sử dụng index thông thường phù hợp | Không được sharding; cơ chế giữ dữ liệu theo dung lượng khác TTL |
| **Standard view** | **Không tạo general index trực tiếp** | Dùng index của collection nguồn; pipeline quyết định hiệu quả |
| **Time series collection** | Hỗ trợ secondary indexes **có giới hạn** | Index trên bucket; các hạn chế text/unique, multikey/geo và version |
| **Clustered collection** | Có clustered index cùng khả năng thêm secondary indexes | Clustered index chỉ xác định khi tạo collection; khóa hiện hành là `{_id: 1}` |
| **Collection do materialized pipeline tạo** | Là collection vật lý nên có thể tạo general index | Dữ liệu kết quả không tự động refresh chỉ vì nguồn đổi |

Bảng là **bản đồ chọn hướng**, không phải ma trận bảo đảm mọi tổ hợp. Với time series và các phiên bản mới, phải đối chiếu tài liệu dành cho phiên bản thật đang dùng.

## 4. Normal collection: hỗ trợ rộng nhưng không phải vô hạn

Collection thông thường là nền tảng để học phần lớn index.

~~~javascript
const lab = db.getSiblingDB("index_limits_lab");

lab.catalog.drop();

lab.catalog.insertMany([
  {
    _id: 1,
    sku: "SKU-001",
    category: "electronics",
    title: "Wireless mouse",
    description: "Wireless mouse with quiet buttons",
    tags: ["office", "sale"],
    attributes: { color: "black", wireless: true },
    location: {
      type: "Point",
      coordinates: [106.7009, 10.7769]
    },
    createdAt: ISODate("2026-01-01T00:00:00Z"),
    expiresAt: ISODate("2027-01-01T00:00:00Z")
  },
  {
    _id: 2,
    sku: "SKU-002",
    category: "book",
    title: "MongoDB guide",
    description: "Document database index reference",
    tags: ["reading"],
    attributes: { language: "vi", edition: 2 },
    location: {
      type: "Point",
      coordinates: [105.8342, 21.0278]
    },
    createdAt: ISODate("2026-02-01T00:00:00Z"),
    expiresAt: ISODate("2027-02-01T00:00:00Z")
  }
]);
~~~

Bộ dữ liệu riêng này chỉ để quan sát cú pháp; `expiresAt` đặt trong tương lai để không bị TTL tự xóa ngay khi chạy ví dụ. Nếu ngày hệ thống đã qua mốc hết hạn, TTL sẽ xóa tài liệu theo chu kỳ; hãy dùng ngày xa hơn khi muốn giữ dữ liệu lab.

### 4.1. B-tree, compound và unique

~~~javascript
lab.catalog.createIndex(
  { category: 1, createdAt: -1 },
  { name: "ix_category_created" }
);

lab.catalog.createIndex(
  { sku: 1 },
  { name: "uq_sku", unique: true }
);
~~~

Các yêu cầu cơ bản vẫn áp dụng: không được có dữ liệu trùng ở `sku` trước khi tạo unique index; index ghép có thứ tự field quan trọng; không thể thêm vô hạn trường hoặc tạo vô hạn index.

Một **compound index thông thường** có tối đa **32 trường**. Ngoài giới hạn cấu trúc, hiệu năng còn phụ thuộc kích thước key, tỷ lệ đọc/ghi, cache và chi phí maintain. Index rộng không tự động tốt hơn.

### 4.2. Partial và sparse: vấn đề tính đầy đủ của kết quả

~~~javascript
lab.catalog.createIndex(
  { category: 1 },
  {
    name: "ix_electronics_only",
    partialFilterExpression: { category: "electronics" }
  }
);
~~~

Partial index chỉ chứa document đạt filter. Query muốn dùng index này một cách đầy đủ thường phải có điều kiện chứng minh rằng kết quả nằm trong phần được index. Không được dùng `hint()` ép index một phần để thay thế một truy vấn đáng lẽ phải đọc cả collection.

**Sparse index** cũng có thể bỏ qua những document thiếu field. Đây là thuộc tính về **những document nào được đưa vào index**, không chỉ là giảm dung lượng.

Với các nhu cầu lọc chủ động, partial index thường linh hoạt hơn sparse index. Tuy nhiên partial/sparse index có những giới hạn riêng tùy loại index và collection.

## 5. TTL index: tự động xóa theo thời gian, không phải general compound index

**TTL index** được thiết kế để tự động xóa document khi một trường ngày/giờ đến hạn hoặc đã qua khoảng thời gian nhất định.

~~~javascript
lab.catalog.createIndex(
  { expiresAt: 1 },
  {
    name: "ix_expiration",
    expireAfterSeconds: 0
  }
);
~~~

Trong ví dụ này, thời điểm hết hạn được lưu trực tiếp ở `expiresAt`. MongoDB dùng tiến trình TTL nền để xử lý document đủ điều kiện.

**Những giới hạn phải nhớ:**

1. TTL index là **single-field index**; đặt `expireAfterSeconds` vào compound index không biến compound index đó thành TTL.
2. Không tạo TTL index trên trường `_id`.
3. Trường TTL cần chứa BSON Date hoặc mảng có giá trị Date phù hợp; chuỗi ISO không tự biến thành Date trong index.
4. Xóa TTL là **asynchronous**; không đảm bảo document biến mất đúng từng mili-giây ngay khi hết hạn.
5. Không thay đổi thời hạn TTL của index đang có chỉ bằng cách gọi lại `createIndex()` với options mới. Dùng `collMod` theo đúng phiên bản.
6. Với **time series**, TTL có cơ chế theo bucket và hỗ trợ các biến thể phụ thuộc phiên bản; không áp dụng máy móc cú pháp normal collection.
7. Với **capped collection**, cơ chế tự động loại dữ liệu theo dung lượng khác cơ chế TTL. Trước khi thiết kế hãy đọc giới hạn của đúng phiên bản; tài liệu phiên bản 7.0 nêu không tạo TTL index trên capped collection.

Ví dụ xem index TTL sau khi tạo:

~~~javascript
lab.catalog.getIndexes().filter(
  idx => idx.name === "ix_expiration"
);
~~~

Nếu cần thay `expireAfterSeconds` trên một index hiện có, dùng `collMod` với key pattern hoặc tên index theo cú pháp MongoDB hỗ trợ; thao tác này có thể khiến lượng lớn dữ liệu ngay lập tức trở thành ứng viên xóa. Trước khi hạ TTL từ nhiều ngày xuống vài giây, cần ước lượng ảnh hưởng vận hành và có kế hoạch xóa từng đợt.

## 6. Text index, MongoDB Search và Vector Search là ba khái niệm khác nhau

### 6.1. B-tree text index trên self-managed MongoDB

Text index truyền thống được tạo bằng `createIndex()`:

~~~javascript
lab.catalog.createIndex(
  { title: "text", description: "text" },
  { name: "text_title_description" }
);

lab.catalog.find({
  $text: { $search: "MongoDB" }
});
~~~

**Giới hạn cơ bản của legacy text index:**

- **Tối đa một text index trên một collection**, dù index đó có thể bao gồm nhiều trường text.
- `$text` không cho phép chọn index bằng `hint()`.
- Text index không được dùng để tối ưu phép sort thông thường.
- Compound text index có quy tắc vị trí text keys; nếu có các khóa trước text key, query `$text` thường phải có điều kiện bằng trên các khóa tiền tố đó.
- Không kết hợp text key tùy ý với geospatial hoặc các special index type khác trong cùng compound text index.
- Text index chỉ hỗ trợ **binary collation**; khi collection có default collation khác, cần xem quy tắc khai báo index riêng.
- Không hỗ trợ text index trên **time series collection** theo tài liệu MongoDB.

Text index phục vụ bài toán full-text cơ bản, không tương đương Search engine chuyên dụng. Chẳng hạn nhu cầu autocomplete, fuzzy matching, ranking hoặc vector similarity cần xem hệ thống Search/Vector Search.

### 6.2. MongoDB Search và Vector Search indexes

MongoDB Search và MongoDB Vector Search dùng hệ **search indexes** riêng, không phải B-tree text index. Tạo và quản trị qua `createSearchIndex()`, các search index commands và `$listSearchIndexes`. Truy vấn thường dùng `$search` hoặc `$vectorSearch` theo tính năng triển khai.

**Khả dụng phụ thuộc môi trường và phiên bản:**

- **MongoDB Atlas:** có các hình thức MongoDB Search / Vector Search theo gói, tier và khả năng hỗ trợ của deployment.
- **Self-managed MongoDB Community từ 8.2 trở lên:** tài liệu hiện hành của `db.collection.createSearchIndex()` liệt kê môi trường này trong phạm vi tương thích; vẫn cần cấu hình các thành phần Search cần thiết.
- **Self-managed MongoDB Enterprise 8.2+ với Kubernetes Operator:** cũng được liệt kê là môi trường hỗ trợ theo điều kiện triển khai.
- Trên các **phiên bản self-managed cũ**, không được mặc định có Search index chỉ vì driver có phương thức `createSearchIndex()`.
- **Compatible views:** các Search/Vector Search index có thể được tạo trên view đủ điều kiện; không suy rộng thành cho phép B-tree index trực tiếp trên mọi standard view.
- **Time series:** tài liệu hiện hành liệt kê MongoDB Search không được hỗ trợ trên time series collection.

Ví dụ minh họa **chỉ chạy khi deployment hỗ trợ MongoDB Search**:

~~~javascript
// Chỉ thực hiện trên deployment có Search được cấu hình.
// Định nghĩa cụ thể phụ thuộc phiên bản/search engine.
db.catalog.createSearchIndex(
  "search_title",
  "search",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: { type: "string" }
      }
    }
  }
);

// Kiểm tra trạng thái: build không nhất thiết sẵn sàng ngay.
db.catalog.aggregate([{ $listSearchIndexes: {} }]);
~~~

Ví dụ này mang tính mô tả API, không phải phần bắt buộc của lab chạy trên mongod Community phiên bản cũ. **Đừng chỉ kiểm tra lệnh trả thành công rồi giả định index đã sẵn sàng**; search index build thường có vòng đời bất đồng bộ.

## 7. Hashed index: phân phối khóa khác với sort hoặc unique

Hashed index lưu giá trị **hash** của field để hỗ trợ một số dạng tìm kiếm bằng và sharding theo hashed key:

~~~javascript
lab.catalog.createIndex(
  { sku: "hashed" },
  { name: "ix_sku_hash" }
);
~~~

**Giới hạn cần ghi nhớ:**

- **Không đặt `unique: true` lên hashed index.** Nếu cần duy nhất, dùng thêm một B-tree unique index phù hợp.
- **Hashed index không phải multikey:** không index một field chứa mảng bằng hashed index. Trong compound index, không để các thành phần khiến index trở thành multikey.
- **Không phải lựa chọn cho sort/range theo giá trị gốc**, vì hash không duy trì thứ tự của giá trị nguồn.
- **Không hỗ trợ covered query** theo ràng buộc hashed index.
- Có các lưu ý về hash giá trị số lớn và số thực; không nên xem việc hash một giá trị số là bảo toàn chính xác mọi kiểu số một cách vô điều kiện.

Đặc biệt, **hashed shard key** có thể hỗ trợ phân phối dữ liệu giữa các shard, nhưng **không** đồng nghĩa với **unique constraint toàn cluster**. Các yêu cầu duy nhất trên sharded collection phải được thiết kế theo shard key và quy tắc unique index.

## 8. Wildcard index: chỉ mục cho field thay đổi, không phải index “biết mọi thứ”

Wildcard index giúp truy vấn những thuộc tính không cố định trong document:

~~~javascript
lab.catalog.createIndex(
  { "attributes.$**": 1 },
  { name: "ix_attributes_wildcard" }
);

lab.catalog.find({ "attributes.color": "black" });
~~~

Thích hợp khi `attributes` có các field khác nhau giữa document (màu sắc, chất liệu, công suất, kích cỡ...). Tuy nhiên wildcard index **không mặc nhiên nhanh bằng index chuyên biệt** nếu workload đã biết rõ field.

**Giới hạn đáng chú ý:**

1. Wildcard index không tự tạo entry cho mọi path vắng mặt. Đây là index có tính sparse.
2. Wildcard index **không phải** wildcard text index và không phục vụ `$text`.
3. Wildcard syntax không dùng để tạo trực tiếp 2d, 2dsphere, hashed, TTL, text hoặc unique index.
4. **Không thể dùng wildcard index làm shard-key index**.
5. **Compound wildcard index** chỉ có **một wildcard term** và các field còn lại phải thỏa điều kiện tương ứng; không thể ghép tùy ý hai wildcard terms.
6. Wildcard index không phục vụ tất cả kiểu truy vấn đối với document/mảng nguyên vẹn, ví dụ exact equality của một nested object có thể không được hỗ trợ theo cách index scalar path hoạt động.
7. Covered query bằng wildcard index có điều kiện chặt về **một field**, projection và tính chất không-mảng.
8. Mặc định `_id` được bỏ khỏi wildcard index; muốn index `_id` bằng wildcard cần cấu hình `wildcardProjection` đúng quy tắc.

**Theo phiên bản:** compound wildcard index có trong MongoDB **7.0+**. Khả năng chỉ định sort order tăng/giảm của wildcard term và các giới hạn liên quan cũng cần đối chiếu đúng phiên bản.

Ví dụ compound wildcard ở môi trường hỗ trợ:

~~~javascript
// Ví dụ chỉ dùng khi server/FCV cho phép compound wildcard.
lab.catalog.createIndex(
  {
    category: 1,
    "attributes.$**": 1
  },
  { name: "ix_category_attrs" }
);
~~~

Cách này phù hợp hơn khi ứng dụng thường có điều kiện category cố định kèm một thuộc tính động. Nhưng không dùng tùy ý nếu môi trường chưa hỗ trợ feature đó.

## 9. Geospatial: 2d, 2dsphere và giới hạn theo dữ liệu

MongoDB có hai loại index không gian chính:

- **`2d`**: phù hợp dữ liệu trên mặt phẳng.
- **`2dsphere`**: hỗ trợ hình học trên bề mặt hình cầu/GeoJSON, thường dùng vị trí địa lý.

Ví dụ 2dsphere:

~~~javascript
lab.catalog.createIndex(
  { location: "2dsphere" },
  { name: "ix_location_2dsphere" }
);

lab.catalog.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 5000
    }
  }
});
~~~

**Giới hạn quan trọng:**

- Không dùng **geospatial index làm shard-key index**. Có thể có geospatial index khác trên sharded collection, nhưng shard key phải được thiết kế riêng.
- **Geospatial index không hỗ trợ covered query** như B-tree scalar index.
- Indexed value phải tuân theo **định dạng hình học hợp lệ**; 2dsphere trên GeoJSON Point dùng tọa độ **[longitude, latitude]**. Dữ liệu không hợp lệ có thể làm lỗi index build hoặc ghi.
- `2d` không hỗ trợ custom collation; khi collection có collation không phải simple, cần khai báo collation simple cho 2d index.
- 2dsphere index có tính sparse: field vị trí vắng mặt/null/mảng rỗng không được index như một vị trí hợp lệ.
- Truy vấn `$geoNear` trên collection có nhiều geospatial index phải chỉ định **`key`** để chọn đúng index.
- **Time series** có các hạn chế truy vấn địa lý riêng, chẳng hạn không dùng `$near`/`$nearSphere` query operator theo tài liệu hiện hành; phải xem quy tắc về `$geoNear` và key.
- **2dsphereIndexVersion** thay đổi theo MongoDB release; phải xét khả năng downgrade.

### 9.1. Ví dụ thời điểm thay đổi 2dsphere index version

Từ **MongoDB 8.3**, tài liệu MongoDB giới thiệu **2dsphere index version 4** và chọn phiên bản này mặc định khi tạo mới. Nếu cần hạ FCV xuống dưới 8.3, phải xử lý các index version 4 không tương thích trước khi downgrade.

Đừng nhầm ba khái niệm:

| Tên | Ví dụ | Công dụng |
| --- | --- | --- |
| Binary server version | `8.3.x` | Mã máy chủ có khả năng thực thi tính năng |
| FCV | `8.0` / `8.3` | Giới hạn sử dụng tính năng không tương thích cũ |
| Index-specific version | `2dsphereIndexVersion: 3/4` | Định dạng và quy tắc index địa lý |

Chỉ override `2dsphereIndexVersion` khi có lý do tương thích rõ ràng; thông thường nên dùng bản mặc định phù hợp với server mục tiêu.

## 10. Multikey: giới hạn trên mảng tác động đến compound và sharding

Multikey không phải một “nút bật” độc lập trong mọi trường hợp; MongoDB thường chuyển index thành multikey khi một trường được index chứa **array**.

~~~javascript
lab.catalog.createIndex(
  { tags: 1 },
  { name: "ix_tags" }
);
~~~

Nếu muốn index ghép nhiều trường mảng, phải chú ý **giới hạn một array field trên mỗi document trong compound multikey index**; không thể tự do index đồng thời hai mảng độc lập gây nhiều tổ hợp phần tử.

Ví dụ cần cân nhắc:

~~~javascript
// Nếu tags và relatedSkus đều là mảng trong cùng một document,
// compound multikey index này không hợp lệ theo ràng buộc index.
db.catalog.createIndex({
  tags: 1,
  relatedSkus: 1
});
~~~

Các hệ quả:

- **Không dùng multikey index làm shard-key index**.
- Có thể tồn tại compound index dùng shard-key prefix scalar và một trường mảng ở phần suffix, theo quy tắc cụ thể.
- Multikey index **không thể cover** một query cần trả chính trường mảng.
- Query có `$elemMatch` có thêm giới hạn khi muốn covered query.
- Nếu index chứa hashed term, không được biến compound index thành multikey.
- Index mảng lớn làm nhiều index entries và tăng chi phí cập nhật.

Khi một document có nhiều field mảng cần truy vấn phối hợp, cân nhắc tách cấu trúc dữ liệu hoặc thiết kế index theo từng truy vấn thay vì cố tạo một index “ghép tất cả”.

## 11. Time series collection: bucket indexes và ngoại lệ theo phiên bản

Time series collection được thiết kế cho measurement liên tục như nhiệt độ, độ trễ, số liệu IoT. Dữ liệu có **`timeField`** và thường có **`metaField`** định danh nguồn đo.

Ví dụ (yêu cầu server hỗ trợ time series):

~~~javascript
lab.createCollection("sensorReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "sensor",
    granularity: "minutes"
  }
});

lab.sensorReadings.insertMany([
  {
    measuredAt: ISODate("2026-01-01T10:00:00Z"),
    sensor: { id: "S-01", zone: "A" },
    temperature: 29.5
  },
  {
    measuredAt: ISODate("2026-01-01T10:01:00Z"),
    sensor: { id: "S-01", zone: "A" },
    temperature: 29.8
  }
]);
~~~

Khác normal collection:

- Hệ thống tổ chức measurement vào **buckets**; nhiều secondary index phục vụ việc tìm bucket phù hợp thay vì lưu một entry thuần túy cho mỗi measurement như normal collection.
- MongoDB **không tạo `_id_` index mặc định** cho time series khi tạo collection. Đừng giả định `hint("_id_")` luôn hợp lệ.
- **Không hỗ trợ unique và text index** trên time series theo tài liệu chính thức.
- Multikey, 2d và sparse chỉ có hỗ trợ **giới hạn gắn với metaField** theo tài liệu limitations; cần đọc đúng phiên bản để biết cấu hình được phép.
- Không thể tạo **time series collection đồng thời là capped collection**.
- Không sử dụng các thiết kế index/geo từ normal collection một cách nguyên xi.

### 11.1. Những mốc phiên bản đáng nhớ

| Phiên bản | Thay đổi về time series index |
| --- | --- |
| **6.0+** | Mở rộng secondary index trên các field measurement bên cạnh timeField/metaField, với cơ chế index bucket |
| **6.3+** | Tài liệu MongoDB ghi nhận default compound index trên metaField và timeField theo quy tắc của phiên bản |
| **7.0+** | Hỗ trợ **partial TTL index** dùng timeField và `partialFilterExpression` chỉ xét metaField |
| **8.0+** | Shard key có chứa timeField bị **deprecated** cho time series |
| **8.3+** | Các quy định bổ sung về tên `_id_` index / hint trên time series; cần đối chiếu khi nâng cấp |

Khi chuyển giữa phiên bản, **FCV downgrade** có thể yêu cầu drop những secondary index time series không tương thích trước. Nếu tài liệu phiên bản bạn dùng có khác biệt ở từng nhóm sparse/geo, phải ưu tiên tài liệu **đúng nhánh phiên bản** của deployment, không chỉ dựa vào bảng ghi nhớ này.

### 11.2. TTL time series không tương đương TTL normal collection

Time series có thể dùng tùy chọn `expireAfterSeconds` ngay trên collection:

~~~javascript
// Ví dụ tạo một collection time series có retention 7 ngày.
lab.createCollection("sensorReadings7d", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "sensor"
  },
  expireAfterSeconds: 7 * 24 * 60 * 60
});
~~~

MongoDB xóa dữ liệu time series theo **bucket đủ điều kiện**, không bảo đảm từng measurement được xóa đúng ngay khi một timestamp vượt hạn. Khi cần retention khác nhau theo sensor, từ MongoDB 7.0 có thể dùng **partial TTL index dựa trên timeField, lọc theo metaField**, theo quy tắc phiên bản.

~~~javascript
// Chỉ dùng trên phiên bản hỗ trợ partial TTL cho time series.
// Bộ lọc partial chỉ sử dụng metaField.
lab.sensorReadings.createIndex(
  { measuredAt: 1 },
  {
    expireAfterSeconds: 3600,
    partialFilterExpression: {
      "sensor.zone": "A"
    }
  }
);
~~~

Ví dụ này minh họa chính sách riêng cho sensor zone A; thời điểm xóa thực tế phụ thuộc bucket, retention chung và TTL monitor. Nếu collection đã có TTL chung ngắn hơn, TTL index có thời hạn dài hơn không kéo dài được retention của dữ liệu.

### 11.3. Time series và sharding

MongoDB cho phép sharding time series trong những cấu hình được hỗ trợ, nhưng **shard key không tùy ý**:

- Dùng `metaField` hoặc các subfield của nó.
- Có những phiên bản cho phép thêm `timeField` ở cuối shard key, với điều kiện theo quy tắc; tuy nhiên từ 8.0 việc dùng timeField trong shard key đã bị deprecated.
- Không đưa một field measurement bất kỳ hoặc `_id` vào shard key của time series nếu nó không thuộc nhóm được hỗ trợ.
- Các thao tác resharding/zone sharding cũng có giới hạn riêng tùy phiên bản.

Với luồng IoT tăng liên tục theo thời gian, chỉ shard theo timeField đơn điệu có thể dồn ghi vào một vùng dữ liệu nóng. Ưu tiên thiết kế metaField/cardinality và shard key theo phân phối tải thực tế.

## 12. Clustered collection: index là một phần cách lưu dữ liệu

Clustered collection lưu document theo thứ tự **clustered index key**. Nó khác normal collection có B-tree `_id_` index tách riêng.

Theo MongoDB Manual:

- Clustered collections xuất hiện từ **MongoDB 5.3**.
- Khóa clustered index hiện được giới hạn ở **`{ _id: 1 }`**.
- Chỉ có **một clustered index** trên một collection.
- Clustered index được xác định **lúc tạo collection**, không thêm sau như secondary index.
- Có thể tạo **secondary indexes** trên clustered collection.
- Không thể chuyển trực tiếp normal collection thành clustered collection hoặc ngược lại bằng việc bật/tắt một option; cần migration dữ liệu.
- Clustered collection **không đồng thời là capped collection**.

Ví dụ (chỉ dùng trên server hỗ trợ):

~~~javascript
lab.createCollection("clusteredEvents", {
  clusteredIndex: {
    key: { _id: 1 },
    unique: true,
    name: "clustered_id"
  }
});
~~~

Trong MongoDB có tối ưu special cho query theo clustered key. Một số execution plan có thể dùng **bounded collection scan** thay vì hiển thị như quét B-tree secondary thông thường. Vì vậy không nên áp dụng máy móc tiêu chí “không thấy IXSCAN nghĩa là không dùng index” khi đang xem clustered collection.

**Không nhầm** clustered index với compound B-tree index có tên giống nhau, và không nhầm clustered collection với time series collection (dù time series có cơ chế cluster theo bucket time trong cách lưu trữ).

## 13. Standard view và materialized view: index thuộc về đâu?

### 13.1. Standard view không có general index riêng

~~~javascript
lab.createView(
  "electronicsView",
  "catalog",
  [
    { $match: { category: "electronics" } },
    { $project: { sku: 1, title: 1, category: 1 } }
  ]
);

lab.electronicsView.find();
~~~

MongoDB **không cho tạo/drop/rebuild general index trực tiếp** trên standard view. Để tăng hiệu năng:

1. Xem `viewOn` và pipeline định nghĩa view.
2. Tạo index trên **collection nguồn** (ở đây là `catalog`).
3. Dùng `explain()` để biết optimizer có thể tận dụng index nguồn ở điều kiện nào.
4. Nếu pipeline quá nặng và kết quả được đọc liên tục, cân nhắc materialized result.

Ví dụ:

~~~javascript
// Index tạo trên collection nguồn, không phải view.
lab.catalog.createIndex(
  { category: 1, title: 1 },
  { name: "ix_category_title" }
);
~~~

Trong các phiên bản Search có hỗ trợ, có ngoại lệ cho **Search/Vector Search indexes trên compatible views**. Đó là **search indexes**, không có nghĩa standard view bỗng hỗ trợ general B-tree index riêng.

### 13.2. On-demand materialized view thực chất dùng collection

Một aggregation có `$merge` hoặc `$out` có thể ghi kết quả vào **collection vật lý**:

~~~javascript
lab.catalog.aggregate([
  {
    $group: {
      _id: "$category",
      itemCount: { $sum: 1 }
    }
  },
  {
    $merge: {
      into: "catalogSummary",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);

lab.catalogSummary.createIndex(
  { itemCount: -1 },
  { name: "ix_summary_count" }
);
~~~

`catalogSummary` là collection vật lý và có thể tạo general indexes theo quy tắc của normal collection. Tuy nhiên dữ liệu của nó **không tự đồng bộ** mỗi khi `catalog` thay đổi. Phải có chiến lược refresh/loại bỏ bản ghi lỗi thời nếu muốn dùng cho báo cáo.

## 14. Capped collection: hiểu cơ chế vòng trước khi chọn index

Capped collection giữ dữ liệu trong phạm vi kích thước cố định và tự thay thế tài liệu cũ theo cơ chế lưu dữ liệu đặc thù:

~~~javascript
lab.createCollection("shortLogs", {
  capped: true,
  size: 1024 * 1024
});

lab.shortLogs.createIndex(
  { service: 1, createdAt: -1 },
  { name: "ix_service_time" }
);
~~~

Capped collection có thể có index cho truy vấn như ví dụ; nhưng cần nhớ:

- Capped collection **không được sharding**.
- Không thể coi đây là time series collection; capped và time series không thể kết hợp làm một.
- Cơ chế hết hạn do **giới hạn dung lượng** khác TTL dựa trên Date.
- Các hạn chế giao dịch và thao tác ghi đặc thù khiến capped không phải giải pháp thay thế normal collection + TTL trong mọi bài toán log.
- Trước khi kết hợp capped với bất kỳ special index nào (nhất là TTL), cần kiểm tra tài liệu phiên bản đang dùng; một số loại index/option không hợp lệ.

Với logs cần giữ trong một khoảng thời gian cố định thay vì dung lượng, **normal collection + TTL** thường dễ dự đoán nghiệp vụ hơn.

## 15. Giới hạn index trong sharded cluster

Sharding phân phối collection qua nhiều shard. Khi đó **truy vấn, index support, uniqueness và vận hành index build** phải được xét ở cấp cluster.

### 15.1. Shard key cần index hỗ trợ

Một sharded collection dùng shard key, ví dụ:

~~~javascript
{ tenantId: 1 }
~~~

Index hỗ trợ shard key có thể là chính key đó hoặc một compound index có shard key làm **prefix**:

~~~javascript
{ tenantId: 1 }
{ tenantId: 1, createdAt: -1 }
~~~

Trên collection đã có dữ liệu, cần có index hỗ trợ trước khi shard, theo phiên bản/quy trình tương ứng. Không được tùy tiện drop/hide **index duy nhất đang phục vụ shard key**.

### 15.2. Unique index phải có shard-key prefix

Ví dụ collection `accounts.users` đã sharded theo `regionId`. Nếu muốn `email` duy nhất **trong từng region**, dùng:

~~~javascript
// Ví dụ chỉ áp dụng sau khi đã shard theo regionId
// và xác nhận dữ liệu không có duplicate.
db.users.createIndex(
  { regionId: 1, email: 1 },
  { unique: true }
);
~~~

Index trên ràng buộc cặp `(regionId, email)`. Một index `{email: 1}` với `unique: true` **không có shard-key prefix** thường bị từ chối trên ranged sharded collection vì MongoDB không thể đảm bảo uniqueness toàn cluster theo cách đó.

**Điểm tinh tế:** Index `_id_` có quy tắc riêng. Khi `_id` **không phải shard key**, tính duy nhất của `_id` trong sharded collection có thể chỉ được bảo đảm ở phạm vi từng shard; ứng dụng phải có cách tạo giá trị `_id` đủ duy nhất toàn cục.

**Hashed shard key** không hỗ trợ unique constraint trên chính hashed index.

### 15.3. Special index không trở thành shard key chỉ vì đã tạo

Không dùng trực tiếp **geospatial**, **wildcard**, **text** hoặc **multikey** index như shard-key index theo các hạn chế tương ứng. Một sharded collection vẫn có thể chứa một số index chuyên biệt **khác với index hỗ trợ shard key**, nếu loại collection và cấu hình đáp ứng điều kiện.

Ví dụ một hệ thống địa điểm có thể sharding theo `regionId` và tạo 2dsphere index trên `location` để phục vụ tìm kiếm gần vị trí. Hai index đảm nhiệm hai công việc khác nhau.

### 15.4. Index builds trong replica set/sharded cluster

Tạo index trên cluster không chỉ là xử lý một máy:

- Có thể cần xây index trên nhiều member/shard chứa dữ liệu.
- Replica set sử dụng khái niệm **commit quorum** cho index build; lựa chọn quorum phụ thuộc phiên bản và trạng thái các thành viên bỏ phiếu.
- Nếu có node chậm, thiếu dung lượng hoặc mất kết nối, index build có thể bị ảnh hưởng.
- Một cluster có thể cần kiểm tra tính đồng nhất của index giữa các shard trong quá trình thay đổi topology/migration.
- Các thao tác DDL trên sharded cluster có quy tắc write concern/quản trị riêng.

Không ép `commitQuorum: 0` hoặc hủy index build chỉ vì cần hoàn tất triển khai gấp. Phải xem tác động đến availability và kế hoạch vận hành.

## 16. Standalone, replica set, sharded, Atlas, Community và Enterprise

Một số tính năng bị giới hạn bởi **topology**, số khác bởi **edition/service** hoặc **version**. Cần phân biệt các trục này.

| Môi trường | Nhận định đúng khi thiết kế index |
| --- | --- |
| **Standalone mongod** | Hỗ trợ nhiều general indexes trên collection thường, nhưng không có sharding; Search yêu cầu môi trường/version cấu hình phù hợp |
| **Replica set** | General index build/replication có thêm commit quorum và điều kiện đồng bộ member |
| **Sharded cluster** | Cần index hỗ trợ shard key, unique prefix và tuân thủ các quy tắc index trên shard |
| **MongoDB Atlas** | Có dịch vụ Search/Vector Search tùy tier/cấu hình, cùng giới hạn quản trị cluster |
| **Self-managed Community** | General indexes sẵn có; từ các phiên bản được hỗ trợ có thể cấu hình Search riêng, không mặc định bật |
| **Self-managed Enterprise** | Hỗ trợ general indexes và thêm các lựa chọn enterprise/deployment phù hợp; Search self-managed có điều kiện version/operator |
| **Serverless/free/managed tier** | Có thể giới hạn tài nguyên, cấu hình hoặc API; kiểm tra tính năng cụ thể của tier thay vì giả định mọi chức năng bằng dedicated cluster |

Không nên viết bảng cứng kiểu “Search chỉ có trên Atlas” cho mọi thời kỳ: tài liệu MongoDB hiện hành đã có hỗ trợ một số **self-managed deployments từ 8.2 trở lên**. Ngược lại, cũng không đúng nếu nói “mọi MongoDB 8.2 đều tạo Search index ngay” mà bỏ qua thành phần Search, môi trường triển khai và quyền.

## 17. Phiên bản, FCV, Stable API và nâng/hạ cấp

### 17.1. Các mốc phiên bản minh họa

| Mốc | Thay đổi liên quan đến index / collection |
| --- | --- |
| **5.0** | Có các hành vi mới về coexistence của unique sparse/non-sparse index cùng key pattern; xem docs đúng phiên bản |
| **5.1** | Hỗ trợ đổi non-TTL single-field index thành TTL index bằng `collMod` trong các điều kiện được mô tả |
| **5.3** | Ra đời clustered collections |
| **6.0** | Mở rộng secondary indexes trên time series |
| **6.3** | Default compound index cho time series meta/time được tài liệu ghi nhận |
| **7.0** | Compound wildcard index và partial TTL time series; quản lý Search index qua `mongosh`/database commands trên môi trường được hỗ trợ |
| **7.1** | Index build có cải thiện cách báo lỗi và khả năng kháng lỗi theo release notes |
| **8.2** | Các môi trường self-managed được liệt kê trong khả năng tạo MongoDB Search/Vector Search indexes |
| **8.3** | 2dsphere index version 4; một số thay đổi giới hạn index/time series |

Đây **không phải danh sách tính năng đầy đủ** và không thể dùng thay release notes cho từng patch. Các bản patch hoặc minor release có thể thay đổi tính năng, sửa lỗi hoặc bổ sung hạn chế.

### 17.2. Stable API là một lớp tương thích khác

**Stable API V1** quy định tập hành vi/command/option ổn định cho ứng dụng. Không phải mọi option của `createIndexes` đều thuộc Stable API V1; tài liệu MongoDB nêu những ngoại lệ như `sparse`, `storageEngine` và `background`. Legacy text indexes cũng có giới hạn khi dùng strict API V1.

Vì thế:

- **Binary server hỗ trợ** một index không đồng nghĩa lệnh đó thuộc Stable API V1.
- Driver có thể truyền `apiVersion: "1"` kèm `apiStrict: true` và từ chối option ngoài API.
- Kiểm tra đúng tài liệu Stable API và driver khi một lệnh chạy được trong `mongosh` thường nhưng lỗi từ ứng dụng.

### 17.3. FCV downgrade có thể bị index chặn

Trước một lần rollback phiên bản, cần kiểm tra **index format và tính năng** đã tạo sau upgrade. Ví dụ 2dsphere version 4 trên MongoDB 8.3 có thể cần được drop trước khi hạ FCV xuống mức cũ không hỗ trợ. Secondary indexes time series cũng có điều kiện tương tự nếu phiên bản đích không hỗ trợ.

Không được chỉ thay binary rồi kỳ vọng mọi index mới tự trở thành định dạng cũ. Một kế hoạch downgrade phải xét:

1. Phiên bản binary đích.
2. FCV hiện tại và FCV đích.
3. Các index được tạo bằng tính năng mới.
4. Các namespace đặc biệt (clustered/time series).
5. Khả năng tái tạo index và phương án backup/restore.
6. Cửa sổ downtime và độ trễ ghi.

## 18. Quan sát và chẩn đoán index theo đúng loại

### 18.1. Kiểm tra general indexes

~~~javascript
const d = db.getSiblingDB("index_limits_lab");

d.catalog.getIndexes();

d.catalog.find(
  { category: "electronics" },
  { _id: 0, category: 1, title: 1 }
).explain("executionStats");
~~~

Từ `explain`, quan sát:

- `winningPlan`: kế hoạch query planner chọn.
- `IXSCAN` và `COLLSCAN`: có dùng B-tree index hay collection scan không.
- `FETCH`: có cần đọc document nguồn sau index scan hay không.
- `totalKeysExamined`, `totalDocsExamined`, `nReturned`: khối lượng công việc thực tế.
- `SORT`: có cần sort riêng ngoài thứ tự index không.

Trên collection nhỏ, `COLLSCAN` đôi khi là lựa chọn hợp lý; không kết luận một index “vô dụng” chỉ vì explain trên vài tài liệu không chọn nó.

### 18.2. Kiểm tra Search index theo cơ chế riêng

Trên deployment hỗ trợ:

~~~javascript
// Không dùng getIndexes() như nguồn thông tin duy nhất về Search.
db.catalog.aggregate([
  { $listSearchIndexes: {} }
]);
~~~

Search index có thể đang ở trạng thái xây dựng/chưa sẵn sàng, ngay cả sau khi lệnh tạo được chấp nhận. Tương tự, Search query cần kiểm tra explain/metrics của hệ Search thay vì chỉ dựa vào `IXSCAN` của B-tree.

### 18.3. Khi index build báo lỗi

Một quy trình kiểm tra hợp lý:

1. **Namespace đúng chưa?** Collection thường, view, time series hay capped?
2. **Server version và FCV?** Tính năng mới có được bật và hỗ trợ bản patch đó?
3. **Index key pattern hợp lệ?** Một wildcard term, trường hash không là mảng, 2dsphere đúng kiểu?
4. **Options hợp lệ?** `unique`/`expireAfterSeconds`/`collation`/`partialFilterExpression` có áp dụng cho index này không?
5. **Dữ liệu đang tồn tại?** Có duplicate, geometry lỗi hoặc array vi phạm compound multikey?
6. **Topology?** Shard-key prefix, unique index và routing có phù hợp?
7. **Permissions và resources?** Quyền tạo index, dung lượng, commit quorum, trạng thái member?
8. **Query có thể dùng index không?** Đọc explain; phân biệt lỗi build với việc planner không chọn index.

Đừng hạ FCV, bật quyền rộng hoặc xóa index khác một cách vội vàng để “qua lỗi” khi chưa xác định điều kiện bị vi phạm.

## 19. Ví dụ đối chiếu: hợp lệ trên collection thường, không mặc định hợp lệ trên loại khác

### 19.1. Một text index trên collection thường

~~~javascript
const demo = db.getSiblingDB("index_limits_lab");

demo.articles.drop();
demo.articles.insertMany([
  { _id: 1, title: "MongoDB indexing", body: "Compound indexes" },
  { _id: 2, title: "MongoDB queries", body: "Text search" }
]);

demo.articles.createIndex(
  { title: "text", body: "text" },
  { name: "text_articles" }
);
~~~

Lệnh này tạo **một text index gồm hai field text**. Tạo text index thứ hai trên cùng collection sẽ vi phạm giới hạn legacy text index:

~~~javascript
// KHÔNG CHẠY như bước tạo thêm một index thông thường:
// một collection chỉ có tối đa một legacy text index.
demo.articles.createIndex({ body: "text" });
~~~

### 19.2. Hashed index không thể unique

~~~javascript
// KHÔNG HỢP LỆ:
demo.articles.createIndex(
  { title: "hashed" },
  { unique: true }
);

// Đúng nếu mục tiêu chỉ cần hash lookup, không unique.
demo.articles.createIndex(
  { title: "hashed" },
  { name: "ix_title_hashed" }
);
~~~

Nếu cần duy nhất, thêm một B-tree unique index **riêng**, sau khi xử lý duplicate và xét sharding:

~~~javascript
demo.articles.createIndex(
  { title: 1 },
  { unique: true, name: "uq_title" }
);
~~~

### 19.3. View không có general index riêng

~~~javascript
demo.createView(
  "articleTitles",
  "articles",
  [{ $project: { title: 1 } }]
);

// KHÔNG HỢP LỆ: general index không tạo trực tiếp trên view.
demo.articleTitles.createIndex({ title: 1 });

// ĐÚNG: tạo index trên collection nguồn nếu cần.
demo.articles.createIndex(
  { title: 1 },
  { name: "ix_article_title" }
);
~~~

Các lệnh gắn chú thích **KHÔNG HỢP LỆ** chỉ để minh họa và nên đọc riêng; khi chạy script thực hành tự động, không đưa chúng liên tiếp vào luồng không có xử lý lỗi.

### 19.4. Hạn chế trên time series

~~~javascript
// Phần này chỉ mô tả giới hạn, không gọi createIndex text/unique:
// demo.sensorReadings.createIndex({ temperature: "text" });
// demo.sensorReadings.createIndex({ "sensor.id": 1 }, { unique: true });
~~~

Muốn index measurement hay metaField, dùng tài liệu time series đúng phiên bản làm nguồn. Không thay thế collection type để “ép tạo index” khi nghiệp vụ đã cần dữ liệu time series.

## 20. Lựa chọn index theo nhu cầu triển khai

| Nhu cầu | Hướng thiết kế thường dùng | Điều cần xác nhận |
| --- | --- | --- |
| Tìm theo ID/mã duy nhất | B-tree unique/compound unique | Duplicate, shard-key prefix, collation |
| Tự xóa log/session theo ngày | TTL trên normal collection | BSON Date, single-field, thời hạn thực thi nền |
| Tìm tài liệu có từ khóa | Legacy text hoặc MongoDB Search | 1 text index/collection, Search availability |
| Autocomplete, ranking, fuzzy search | MongoDB Search | Deployment/edition/tier, search index build |
| Tìm embedding tương tự | MongoDB Vector Search | Phiên bản, cấu hình search index, hỗ trợ deployment |
| Tìm vị trí địa lý | 2dsphere / 2d | GeoJSON, tọa độ, không dùng làm shard key |
| Field động trong attributes | Wildcard | Giới hạn wildcard, version, sparse, query patterns |
| Shard theo giá trị phân phối đều | Hashed shard key | Không unique/multikey, range/sort limitations |
| Truy vấn measurement theo thời gian | Time series index trên meta/time/measurement | Bucket semantics, version/FCV, TTL, unsupported types |
| Dùng lại pipeline lọc dữ liệu | Standard view + index nguồn | Không general index trực tiếp trên view |
| Cần đọc báo cáo tổng hợp cực nhanh | Materialized collection + index | Cơ chế refresh và consistency |
| Quét khoảng theo định danh có thứ tự vật lý | Clustered collection | Khóa clustered, tạo lúc khởi tạo, version |

Một chỉ mục chuyên biệt tối ưu một loại truy vấn nhưng có thể làm tăng chi phí ghi, index build và khả năng tương thích. **Không tạo tất cả index** chỉ vì collection có nhiều trường.

## 21. Bài tập thực hành

### Bài 1 — Nhận diện môi trường

Chạy `db.version()`, `db.hello()` và khi có quyền `getParameter featureCompatibilityVersion`. Ghi lại:

1. Server đang dùng phiên bản nào?
2. Có đang kết nối tới `mongos` không?
3. Có replica set name không?
4. FCV có phù hợp với feature muốn sử dụng không?

Giải thích vì sao version của `mongosh` không phải câu trả lời cho các câu hỏi này.

### Bài 2 — Normal collection và giới hạn kiểu index

Dùng `lab.catalog` ở mục 4, tạo B-tree compound, TTL, hashed, wildcard và 2dsphere indexes theo các ví dụ. Liệt kê bằng `getIndexes()`, giải thích từng index phục vụ loại truy vấn nào.

### Bài 3 — Text index có nhiều field

Tạo một text index chứa `title` và `body` trên `articles`, chạy `$text`. Vì sao không tạo được **hai text indexes độc lập** trên cùng collection? Tại sao MongoDB Search không chịu cùng giới hạn đó?

### Bài 4 — TTL không phải timer chính xác

Tạo normal collection chứa các document có `expiresAt` khác nhau, tạo TTL index `expireAfterSeconds: 0`. Quan sát khi document được xóa. Giải thích vì sao TTL monitor không phải cơ chế hẹn giờ chính xác tuyệt đối và phải cân nhắc tải khi bật TTL trên dữ liệu lớn.

### Bài 5 — Time series và index mặc định

Tạo `sensorReadings` ở mục 11 trong một môi trường hỗ trợ time series. So sánh `getIndexes()` với normal collection mới tạo; giải thích vì sao không mặc định có index `_id_` như normal collection. Xác định phiên bản trước khi thử tạo secondary index đo lường.

### Bài 6 — Clustered collection

Nếu môi trường hỗ trợ, tạo một clustered collection có `clusteredIndex` trên `_id`. Tại sao không có hai clustered indexes? Tại sao phải xác định clustered index khi tạo collection thay vì thêm sau bằng `createIndex()`?

### Bài 7 — Sharding và unique index

Một collection `users` được shard theo `tenantId`. Bạn muốn email duy nhất **trong một tenant**. Hãy đề xuất unique index hợp lệ.

Lời giải định hướng:

~~~javascript
db.users.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true }
);
~~~

Giải thích vì sao `{email: 1}, unique: true` không đáp ứng shard-key prefix. Nếu nghiệp vụ yêu cầu email duy nhất **trên mọi tenant**, cần một mô hình đảm bảo uniqueness khác, không đơn giản bỏ tenantId khỏi index sharded.

### Bài 8 — Chọn Search thay cho text

Một ứng dụng cần fuzzy search và vector similarity. So sánh legacy text index với Search/Vector Search index; viết những câu hỏi cần trả lời trước khi triển khai trên Atlas hoặc self-managed, gồm **version, tier, search service, cách tạo index và query operator**.

### Bài 9 — Phân biệt index được hỗ trợ với index được sử dụng

Tạo `{category: 1, createdAt: -1}` và chạy `explain("executionStats")` cho query category. Sau đó chạy query khác chỉ lọc theo một field không có trong index. Vì sao không thể nói “đã tạo index là mọi truy vấn đều nhanh”?

### Bài 10 — Lập kế hoạch downgrade

Một hệ thống đang dùng MongoDB 8.3 và đã tạo 2dsphere index version 4, chuẩn bị hạ về FCV thấp hơn. Nêu các kiểm tra về index format, backup, feature flags và khả năng tái tạo index trước khi đổi FCV. Giải thích vì sao đổi binary mà không xử lý index version có thể thất bại.

## 22. Tổng kết

Giới hạn index MongoDB không thể được quyết định bằng duy nhất tên loại index. Một thiết kế đúng cần xem **kiểu collection**, **phiên bản binary và FCV**, **topology/edition/dịch vụ**, rồi đến **key pattern, data types, index options, khả năng build và query plan**.

Các điểm cốt lõi:

1. **Normal collection** hỗ trợ nhiều loại general index, nhưng từng loại có quy tắc về data type, uniqueness và cú pháp riêng.
2. **Standard view** không có general index trực tiếp; dùng index từ nguồn. **Materialized result** là collection vật lý có thể tạo index.
3. **Time series** tổ chức index theo bucket và giới hạn text, unique, một số multikey/geo, TTL và sharding theo phiên bản.
4. **Clustered collection** có clustered index gắn với định dạng lưu trữ, chỉ định khi tạo và không giống B-tree secondary index.
5. **Hashed index** không hỗ trợ unique, multikey hay covered query; **wildcard** không làm shard key; **geospatial** không làm shard key.
6. **Sharded cluster** đòi hỏi index phục vụ shard key, unique index thường có shard key làm prefix và kiểm soát index build trên nhiều shard.
7. **Search/Vector Search** là hệ index riêng; đừng đồng nhất với legacy text index hoặc giả định chỉ/luôn có trên một edition.
8. **Version và FCV** có thể chặn tạo hoặc downgrade index; phải xem đúng tài liệu version và định dạng index.
9. **Index build thành công chưa đủ**: dùng `explain()` và số liệu workload để xác định truy vấn có hưởng lợi thật không.

### Tài liệu MongoDB chính thức

- [Indexes](https://www.mongodb.com/docs/manual/indexes/) — các loại index và chi phí ghi/đọc.
- [Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) — giới hạn chung và khi sharding.
- [Wildcard Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-wildcard/reference/restrictions/) — loại index không tương thích, shard key, compound wildcard.
- [Text Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-restrictions/) — một text index/collection và giới hạn `$text`.
- [Hashed Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-hashed/) — unique, multikey, covered query.
- [Geospatial Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/restrictions/) — collation, shard key và kiểu dữ liệu hình học.
- [2dsphere Index Versions](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/2dsphere-index-versions/) — version 4 và tương thích FCV.
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — single-field, Date, TTL background.
- [Time Series Collection Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/) — giới hạn index và sharding time series.
- [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/) — bucket index, secondary index và version.
- [Clustered Collections](https://www.mongodb.com/docs/manual/core/clustered-collections/) — clustered index và giới hạn tạo.
- [Views](https://www.mongodb.com/docs/manual/core/views/) — view không có general index, compatible Search views.
- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — shard key prefix của unique index.
- [Shard Key Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key-indexes/) — index bắt buộc hỗ trợ shard key.
- [createSearchIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.createSearchIndex/) — môi trường hỗ trợ Search/Vector Search và lệnh quản trị.
- [createIndexes()](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndexes/) — options, Stable API, commit quorum và build.
- [setFeatureCompatibilityVersion](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/) — FCV và quản trị tương thích.
