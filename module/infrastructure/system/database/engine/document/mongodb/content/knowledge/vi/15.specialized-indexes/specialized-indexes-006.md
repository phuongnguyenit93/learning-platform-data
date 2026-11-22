# Wildcard index cho cấu trúc trường biến đổi trong MongoDB

Trong một catalog thương mại điện tử, sản phẩm laptop có `attributes.ramGB` và `attributes.cpu.cores`, máy ảnh có `attributes.sensor.megapixels`, còn ghế văn phòng có `attributes.maxLoadKg`. Những field này không xuất hiện đồng đều ở mọi document. Nếu mỗi khi phát sinh một thuộc tính mới, nhóm phát triển lại phải tạo một index riêng, số index sẽ tăng nhanh và trở nên khó quản trị. **Wildcard index** của MongoDB được thiết kế để hỗ trợ truy vấn theo nhiều đường dẫn field khác nhau, đặc biệt khi cấu trúc field biến đổi và không thể biết trước toàn bộ thuộc tính cần tra cứu.

Wildcard index không phải giải pháp “đánh index mọi thứ để mọi query đều nhanh”. Nó có thể tạo nhiều index key cho mỗi document, không có đầy đủ năng lực của một compound index được thiết kế cho filter/sort ổn định, và có những hạn chế với mảng, kiểu dữ liệu, sự kết hợp nhiều predicate. Bài học này giúp bạn hiểu **khi nào nên dùng `$**`, khi nào nên giới hạn phạm vi bằng `attributes.$**` hoặc `wildcardProjection`, và cách đánh giá hiệu quả bằng dữ liệu truy vấn thực tế.

Bài nằm trong chương **Index chuyên biệt** của module *Database Engine Document MongoDB*. Ví dụ dùng **mongosh** với database lab `wildcard_lab`. Một số tính năng, đặc biệt compound wildcard index, phụ thuộc phiên bản MongoDB; cần đối chiếu khả năng hỗ trợ của deployment khi triển khai. Không tạo/xóa index trên collection production chỉ để thử ví dụ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích bài toán **dynamic schema** và lý do wildcard index xuất hiện.
2. Phân biệt wildcard index toàn document `{"$**":1}`, wildcard index dưới một nhánh `{"attributes.$**":1}` và index trên field cụ thể.
3. Hiểu wildcard index tổ chức **đường dẫn field và giá trị**, không đơn thuần giống một B-tree trên một field đã biết.
4. Tạo, liệt kê và quản lý wildcard index với `createIndex()`, `getIndexes()`, `dropIndex()`.
5. Dùng `wildcardProjection` để chỉ bao phủ các nhánh cần thiết hoặc loại trừ dữ liệu không muốn lập index.
6. Phân tích các truy vấn equality, range, nested field, array và điều kiện nhiều field cùng lúc.
7. Nhận diện giới hạn về sort, covered query, thiếu field, field có cấu trúc phức tạp và index nhiều thuộc tính.
8. Hiểu compound wildcard index, đặc biệt use case có một số field ổn định và nhiều field động.
9. Đo query plan qua `explain("executionStats")`, quản lý footprint/index usage và chọn chiến lược khác khi wildcard không phù hợp.

## 2. Dynamic schema: vì sao index thông thường không đủ linh hoạt?

Giả sử collection `products` chứa ba nhóm document:

~~~javascript
// Laptop
{
  _id: "laptop-01",
  category: "laptop",
  attributes: {
    ramGB: 16,
    cpu: { cores: 8 },
    storage: { ssdGB: 512 }
  }
}

// Máy ảnh
{
  _id: "camera-01",
  category: "camera",
  attributes: {
    sensor: { megapixels: 24 },
    stabilization: true,
    lensMount: "E"
  }
}

// Ghế
{
  _id: "chair-01",
  category: "chair",
  attributes: {
    material: "mesh",
    maxLoadKg: 120,
    adjustableHeight: true
  }
}
~~~

Người dùng có thể tìm:

~~~javascript
db.products.find({ "attributes.ramGB": { $gte: 16 } })
db.products.find({ "attributes.sensor.megapixels": { $gte: 20 } })
db.products.find({ "attributes.maxLoadKg": { $gte: 100 } })
~~~

Nếu dùng index đơn thông thường cho từng đường dẫn:

~~~javascript
db.products.createIndex({ "attributes.ramGB": 1 })
db.products.createIndex({ "attributes.sensor.megapixels": 1 })
db.products.createIndex({ "attributes.maxLoadKg": 1 })
~~~

thì bạn phải dự đoán những field nào cần được truy vấn. Với hàng trăm category, hàng nghìn tên thuộc tính và thuộc tính mới liên tục được thêm bởi nhà bán hàng, chiến lược “mỗi field một index” có thể dẫn đến:

- Nhiều index có số lần dùng rất thấp.
- Dung lượng index lớn và chi phí ghi tăng.
- Nhiều migration index khi thêm thuộc tính.
- Index build gây ảnh hưởng tải và cần giám sát liên tục.
- Bài toán lựa chọn index và quản lý vòng đời ngày càng phức tạp.

**Wildcard index** cho phép khai báo một phạm vi đường dẫn có thể được index mà không cần liệt kê trước từng tên field.

### Phân biệt “field động” và “value động”

Một field ổn định có nhiều giá trị khác nhau không nhất thiết cần wildcard index:

~~~javascript
{
  category: "laptop",   // tên field cố định
  status: "ACTIVE",     // tên field cố định
  price: 25000000       // tên field cố định
}
~~~

Giá trị `category` thay đổi giữa laptop/camera/chair, nhưng **đường dẫn `category` không đổi**. Một index đơn/ghép thông thường có thể rất phù hợp.

Ngược lại, `attributes.ramGB`, `attributes.sensor.megapixels` và `attributes.maxLoadKg` là **các đường dẫn field khác nhau**. Đây là loại biến đổi mà wildcard index hướng tới.

## 3. Wildcard index hoạt động ở mức ý tưởng

Wildcard index dùng token `$**` để nói rằng MongoDB sẽ lập index cho các đường dẫn field trong phạm vi cho phép, thay vì chỉ một field được nêu tên. Trong cách giải thích logic, các index entry gắn **đường dẫn field** với **giá trị** tương ứng.

Ví dụ:

~~~javascript
{
  _id: "laptop-01",
  attributes: {
    ramGB: 16,
    cpu: { cores: 8 },
    color: "black"
  }
}
~~~

Một cách hình dung các cặp khóa:

~~~text
path = "attributes.ramGB"       value = 16
path = "attributes.cpu.cores"   value = 8
path = "attributes.color"       value = "black"
~~~

Đây là **mô hình giải thích**, không phải dump cấu trúc index trên disk. Engine còn xử lý BSON type, array, trùng key, metadata về đường dẫn và các trường hợp đặc biệt.

~~~mermaid
flowchart TD
    Product["Document sản phẩm"] --> Attr["Object attributes"]
    Attr --> A["attributes.ramGB = 16"]
    Attr --> B["attributes.cpu.cores = 8"]
    Attr --> C["attributes.color = black"]
    A --> WI["Wildcard index: đường dẫn + giá trị"]
    B --> WI
    C --> WI
    Query["Query trên attributes.cpu.cores"] --> WI
    WI --> Found["Ứng viên document phù hợp"]
~~~

**Một index có thể hỗ trợ nhiều đường dẫn:** query tìm `attributes.ramGB` và query tìm `attributes.cpu.cores` đều có khả năng sử dụng cùng một wildcard index. Tuy nhiên điều này **không có nghĩa một lần scan của wildcard index luôn tối ưu nhiều điều kiện khác đường dẫn**.

### 3.1. So với index đơn

| Tiêu chí | Index đơn `{"attributes.ramGB":1}` | Wildcard `{"attributes.$**":1}` |
|---|---|---|
| Đường dẫn được index | Cố định: `attributes.ramGB` | Nhiều đường dẫn bên dưới `attributes` |
| Tối ưu cho query nào? | Query lặp lại thường xuyên trên ramGB | Query động trên nhiều thuộc tính khác nhau |
| Thêm field mới | Cần cân nhắc thêm index riêng | Field mới trong scope có thể được index |
| Kích thước index | Thường tập trung vào một loại key | Có thể có nhiều key cho mỗi document |
| Filter + sort nhiều field | Có thể kết hợp qua compound index chuyên dụng | Nhiều hạn chế; cần kiểm tra query planner |
| Khi nào ưu tiên | Workload ổn định, field quan trọng | Workload field biến đổi, ít đoán trước |

## 4. Ba cách chỉ định phạm vi wildcard index

### 4.1. Wildcard toàn document

~~~javascript
db.flex_documents.createIndex(
  { "$**": 1 },
  { name: "idx_all_dynamic_paths" }
)
~~~

Pattern `{"$**":1}` hướng tới các đường dẫn field trên toàn document theo những quy tắc của wildcard index. Nó phù hợp khi **nhiều phần document** đều là dữ liệu động cần query.

Đánh đổi: field ổn định, thông tin log/debug, payload lớn hoặc metadata không bao giờ được filter cũng có thể làm index phình ra nếu không giới hạn. Vì vậy không nên chọn wildcard toàn document chỉ vì cú pháp ngắn.

### 4.2. Wildcard cho một nhánh document

~~~javascript
db.products.createIndex(
  { "attributes.$**": 1 },
  { name: "idx_product_attributes" }
)
~~~

Index tập trung vào các đường dẫn bên dưới `attributes`, ví dụ:

~~~text
attributes.ramGB
attributes.cpu.cores
attributes.sensor.megapixels
attributes.material
attributes.waterproof
~~~

Nó **không tự trở thành index** cho filter thuần `tenantId`, `status` hoặc `price` ở ngoài nhánh này.

Với catalog có các field lõi ổn định và object `attributes` biến đổi theo category, đây thường là điểm bắt đầu hợp lý hơn so với `{"$**":1}`.

### 4.3. Wildcard toàn document với `wildcardProjection`

Khi nhiều nhánh chứa field động nhưng có những nhánh không muốn index, có thể dùng `wildcardProjection`:

~~~javascript
db.flex_documents.createIndex(
  { "$**": 1 },
  {
    name: "idx_flex_without_large_payload",
    wildcardProjection: {
      rawPayload: 0,
      debugDetails: 0,
      description: 0
    }
  }
)
~~~

Ở đây projection loại trừ các nhánh được nêu tên khỏi phạm vi lập index. Một phương án khác là **chỉ bao gồm** những nhánh cần truy vấn:

~~~javascript
db.flex_documents.createIndex(
  { "$**": 1 },
  {
    name: "idx_flex_selected_branches",
    wildcardProjection: {
      attributes: 1,
      customFields: 1
    }
  }
)
~~~

Hai ví dụ trên là **hai lựa chọn thay thế**, không phải khuyến nghị tạo đồng thời cả hai index trên production. Trong cấu hình cụ thể, phải kiểm tra giới hạn inclusion/exclusion, cách xử lý `_id` và compatibility theo phiên bản MongoDB. `wildcardProjection` điều khiển **field được lập index**, không phải phép projection của kết quả `find()`.

### 4.4. Nên chọn phương án nào?

| Trường hợp | Phạm vi gợi ý | Lý do |
|---|---|---|
| Chỉ `attributes` biến đổi | `{"attributes.$**":1}` | Không tốn index cho field lõi ngoài attributes |
| Nhiều nhánh tùy biến | `{"$**":1}` kèm wildcardProjection bao gồm | Kiểm soát phạm vi cần index |
| Hầu hết field có thể cần tra cứu, trừ payload lớn | `{"$**":1}` với wildcardProjection loại trừ | Hạn chế các nhánh không hữu ích |
| Query gần như chỉ dùng một field ổn định | Index đơn/ghép chuyên dụng | Nhỏ gọn, tận dụng sort/range tốt hơn |
| Chỉ muốn index tài liệu theo nội dung ngôn ngữ tự nhiên | Text/search index theo nhu cầu | Wildcard B-tree không thay search engine |

## 5. Dữ liệu lab: catalog nhiều cấu trúc thuộc tính

Chọn database riêng:

~~~javascript
use wildcard_lab
~~~

Tạo dữ liệu thử. Mỗi nhóm sản phẩm có những field khác nhau trong `attributes`:

~~~javascript
db.products.insertMany([
  {
    _id: "p-101",
    tenantId: "t-01",
    category: "laptop",
    status: "ACTIVE",
    name: "Laptop Alpha",
    price: NumberDecimal("22000000"),
    attributes: {
      ramGB: 16,
      cpu: { cores: 8, family: "Core" },
      storage: { ssdGB: 512 },
      color: "gray",
      connectivity: ["wifi6", "bluetooth5"]
    }
  },
  {
    _id: "p-102",
    tenantId: "t-01",
    category: "laptop",
    status: "ACTIVE",
    name: "Laptop Beta",
    price: NumberDecimal("35000000"),
    attributes: {
      ramGB: 32,
      cpu: { cores: 16, family: "Ryzen" },
      storage: { ssdGB: 1024 },
      color: "black",
      connectivity: ["wifi7", "bluetooth5"]
    }
  },
  {
    _id: "p-201",
    tenantId: "t-01",
    category: "camera",
    status: "ACTIVE",
    name: "Camera Sigma",
    price: NumberDecimal("19500000"),
    attributes: {
      sensor: { megapixels: 24, format: "APS-C" },
      stabilization: true,
      lensMount: "E",
      iso: { max: 51200 }
    }
  },
  {
    _id: "p-202",
    tenantId: "t-02",
    category: "camera",
    status: "ACTIVE",
    name: "Camera Delta",
    price: NumberDecimal("12000000"),
    attributes: {
      sensor: { megapixels: 18, format: "Micro 4/3" },
      stabilization: false,
      lensMount: "MFT",
      iso: { max: 25600 }
    }
  },
  {
    _id: "p-301",
    tenantId: "t-01",
    category: "chair",
    status: "ACTIVE",
    name: "Chair Mesh",
    price: NumberDecimal("3200000"),
    attributes: {
      material: "mesh",
      maxLoadKg: 120,
      adjustableHeight: true,
      color: "black"
    }
  },
  {
    _id: "p-302",
    tenantId: "t-02",
    category: "chair",
    status: "INACTIVE",
    name: "Chair Oak",
    price: NumberDecimal("4600000"),
    attributes: {
      material: "wood",
      maxLoadKg: 80,
      adjustableHeight: false,
      color: "brown"
    }
  },
  {
    _id: "p-401",
    tenantId: "t-01",
    category: "shoes",
    status: "ACTIVE",
    name: "Shoes Trek",
    price: NumberDecimal("1900000"),
    attributes: {
      sizesEU: [40, 41, 42],
      upper: { material: "leather" },
      waterproof: true,
      colors: ["black", "brown"]
    }
  },
  {
    _id: "p-402",
    tenantId: "t-02",
    category: "shoes",
    status: "ACTIVE",
    name: "Shoes Run",
    price: NumberDecimal("1350000"),
    attributes: {
      sizesEU: [39, 40],
      upper: { material: "textile" },
      waterproof: false,
      colors: ["blue", "white"]
    }
  },
  {
    _id: "p-501",
    tenantId: "t-01",
    category: "phone",
    status: "ACTIVE",
    name: "Phone One",
    price: NumberDecimal("16000000"),
    attributes: {
      screen: { inches: 6.7 },
      battery: { mAh: 5000 },
      features: { eSIM: true },
      colors: ["black", "silver"]
    }
  },
  {
    _id: "p-502",
    tenantId: "t-02",
    category: "phone",
    status: "ACTIVE",
    name: "Phone Mini",
    price: NumberDecimal("9000000"),
    attributes: {
      screen: { inches: 6.1 },
      battery: { mAh: 4200 },
      features: { eSIM: false },
      colors: ["white", "green"]
    }
  }
])
~~~

Bộ dữ liệu trên để **hiểu ngữ nghĩa** chứ không để kết luận tốc độ. Chỉ chạy `insertMany()` một lần trên lab mới; lần tiếp theo với cùng `_id` sẽ báo duplicate key. Không xóa collection không phải dữ liệu thử nghiệm chỉ để chạy lại.

Kiểm tra:

~~~javascript
db.products.countDocuments({})

db.products.find(
  {},
  { _id: 1, tenantId: 1, category: 1, status: 1, name: 1 }
).sort({ _id: 1 })
~~~

### 5.1. Tạo wildcard index dưới `attributes`

~~~javascript
db.products.createIndex(
  { "attributes.$**": 1 },
  { name: "idx_attributes_wildcard" }
)
~~~

Xem metadata:

~~~javascript
db.products.getIndexes()
~~~

Lưu ý: index wildcard được khai báo theo một nhánh. Nếu ứng dụng thường tìm theo `tenantId`, `category`, `status` hoặc `price`, cần phân tích các index khác tương ứng; chỉ một wildcard index ở attributes chưa bảo đảm hiệu năng của toàn query.

## 6. Truy vấn equality trên field động

### 6.1. Laptop có RAM 16 GB

~~~javascript
db.products.find(
  { "attributes.ramGB": 16 },
  { _id: 1, name: 1, category: 1, "attributes.ramGB": 1 }
)
~~~

Trong dữ liệu mẫu, `p-101` khớp. MongoDB có thể xem wildcard index để tìm những key thuộc đường dẫn `attributes.ramGB` với giá trị 16.

### 6.2. Tìm vật liệu ghế

~~~javascript
db.products.find(
  {
    category: "chair",
    "attributes.material": "mesh"
  },
  { _id: 1, name: 1, "attributes.material": 1 }
)
~~~

`p-301` khớp. `category` là field lõi, còn `attributes.material` là field tùy biến. Wildcard index dưới attributes có thể hỗ trợ predicate thứ hai, nhưng không tự kết hợp cả hai field thành một thứ tự compound như index chuyên dụng.

### 6.3. Camera có lens mount E

~~~javascript
db.products.find({
  "attributes.lensMount": "E"
})
~~~

`p-201` khớp. Không cần tạo riêng index `{"attributes.lensMount":1}` chỉ để có một đường truy cập cho field này nếu wildcard index đáp ứng workload.

### 6.4. Laptop có tên CPU family

~~~javascript
db.products.find({
  "attributes.cpu.family": "Ryzen"
})
~~~

`p-102` khớp. Đường dẫn lồng sâu hơn vẫn thuộc nhánh `attributes`.

**Kết luận của các ví dụ:** một wildcard index có thể đóng vai trò ứng viên index cho nhiều **query riêng biệt trên nhiều path khác nhau**. Không nên suy ra nó được tối ưu đồng thời cho mọi tổ hợp các path trong cùng một query.

## 7. Truy vấn range trên thuộc tính động

Wildcard index không chỉ phục vụ equality. Với kiểu dữ liệu và query shape phù hợp, nó còn có thể hỗ trợ điều kiện range.

### 7.1. Máy ảnh có độ phân giải từ 20 MP

~~~javascript
db.products.find({
  "attributes.sensor.megapixels": { $gte: 20 }
})
~~~

Kết quả của bộ dữ liệu mẫu: `p-201` (24 MP); `p-202` chỉ có 18 MP.

### 7.2. Ghế chịu tải tối thiểu 100 kg

~~~javascript
db.products.find({
  "attributes.maxLoadKg": { $gte: 100 }
})
~~~

Kết quả: `p-301` (120 kg).

### 7.3. Laptop có RAM ít nhất 16 GB

~~~javascript
db.products.find({
  "attributes.ramGB": { $gte: 16 }
})
~~~

Kết quả: `p-101` và `p-102`.

### 7.4. Kiểu dữ liệu phải thống nhất

Nếu một nhà bán hàng ghi:

~~~javascript
{ attributes: { ramGB: "16" } }
~~~

thay vì:

~~~javascript
{ attributes: { ramGB: 16 } }
~~~

thì điều kiện số học có thể không nhận giá trị chuỗi theo cách bạn kỳ vọng. Index lưu giá trị BSON với type tương ứng; nó **không tự chuẩn hóa "16" thành 16**. Dynamic schema không đồng nghĩa được phép để mỗi nơi chọn một kiểu tùy ý.

Khuyến nghị: có **attribute dictionary** định nghĩa mỗi thuộc tính, kiểu dữ liệu, đơn vị, cho phép multiple values hay không, và cách canonicalize khi ghi.

## 8. Khi filter nhiều field động trong cùng một query

Một query phổ biến:

~~~javascript
db.products.find({
  category: "laptop",
  "attributes.ramGB": { $gte: 16 },
  "attributes.cpu.cores": { $gte: 8 }
})
~~~

Lúc này có ba predicate:

1. `category` ở field lõi.
2. `attributes.ramGB` ở đường dẫn động.
3. `attributes.cpu.cores` ở một đường dẫn động khác.

**Không thể coi một wildcard index giống index ghép** `{category:1,"attributes.ramGB":1,"attributes.cpu.cores":1}`. Wildcard index có cách tổ chức đường dẫn/giá trị riêng; trình tối ưu không mặc nhiên kết hợp tất cả điều kiện của nhiều path bằng một vùng scan hiệu quả.

MongoDB có thể:

- Dùng wildcard index cho một path động rồi FETCH document để kiểm tra predicate còn lại.
- Dùng một index khác nếu index đó chọn lọc hơn.
- Dùng kế hoạch phối hợp index trong những trường hợp hỗ trợ.
- Chọn collection scan khi dataset nhỏ hoặc index không đem lại lợi ích.

Những lựa chọn phụ thuộc query planner và phiên bản MongoDB. Khi query lặp lại thường xuyên, có thể nên tạo **compound index chuyên dụng**:

~~~javascript
db.products.createIndex(
  {
    category: 1,
    "attributes.ramGB": 1,
    "attributes.cpu.cores": 1
  },
  { name: "idx_laptop_ram_cpu" }
)
~~~

Chi phí là thêm một index riêng, đổi lại query rất phổ biến trên laptop có đường truy cập chuyên biệt.

### 8.1. Một query chỉ lọc một field động khác với query lọc cả chục field

Wildcard index thường hấp dẫn khi có **nhiều query biến đổi**, mỗi query hỏi một hoặc vài thuộc tính. Nếu giao diện faceted search thường kết hợp 5–10 điều kiện, sort theo giá và phân trang, cần đánh giá cả hệ thống search/query design chứ không kỳ vọng một wildcard index gánh hết.

### 8.2. Field ổn định vẫn đáng có index riêng

Ví dụ các query luôn có:

~~~javascript
{
  tenantId: "t-01",
  status: "ACTIVE"
}
~~~

thì một index:

~~~javascript
db.products.createIndex(
  { tenantId: 1, status: 1, price: 1 },
  { name: "idx_tenant_status_price" }
)
~~~

có thể phục vụ danh sách sản phẩm theo tenant, trạng thái và giá. Wildcard index thuộc attributes bổ trợ các filter tùy biến. Đây là kiến trúc **kết hợp index thường cho field lõi + wildcard cho thuộc tính động**.

## 9. Compound wildcard index

Trong các phiên bản MongoDB hỗ trợ **compound wildcard index** (được giới thiệu ở MongoDB 7.0), có thể kết hợp một đường dẫn wildcard với một hoặc nhiều field thông thường trong cùng một index. Ví dụ:

~~~javascript
// Chỉ thử trên deployment có hỗ trợ compound wildcard indexes.
db.products.createIndex(
  {
    tenantId: 1,
    "attributes.$**": 1
  },
  { name: "idx_tenant_dynamic_attributes" }
)
~~~

Ý tưởng: hệ thống multi-tenant luôn có `tenantId`, nhưng đường dẫn `attributes.*` biến đổi theo category. Index có thể hỗ trợ nhóm query dạng:

~~~javascript
db.products.find({
  tenantId: "t-01",
  "attributes.sensor.megapixels": { $gte: 20 }
})

db.products.find({
  tenantId: "t-01",
  "attributes.ramGB": { $gte: 16 }
})
~~~

**Cần lưu ý:**

- Phiên bản trước khi có hỗ trợ compound wildcard index sẽ không chấp nhận cú pháp hoặc khả năng này.
- Compound wildcard index vẫn **không tương đương** việc tạo compound index chuyên dụng cho mọi cặp thuộc tính động khác nhau.
- Chỉ một thành phần wildcard của index cần được hiểu theo quy tắc và giới hạn tính năng tương ứng.
- Các quy tắc sort, multikey, wildcard projection và query bounds có thể khác với compound B-tree thông thường.
- Thiết kế shard key, unique constraints và partial/sparse options phải được kiểm chứng riêng cho phiên bản/topology.

Đừng chỉ thấy có `tenantId` ở đầu rồi kết luận mọi query theo tenant + nhiều thuộc tính đều được phục vụ tối ưu. Đọc `explain()` và so với các index thay thế.

### 9.1. Có nên tạo cả index thuộc tính đơn và compound wildcard?

Hai index:

~~~javascript
{ "attributes.$**": 1 }
{ tenantId: 1, "attributes.$**": 1 }
~~~

có thể phục vụ các nhóm query khác nhau, nhưng cũng tốn chi phí duy trì cả hai. Nếu gần như mọi truy vấn đều có tenantId, hãy đánh giá index compound wildcard theo điều kiện phiên bản. Nếu còn truy vấn cross-tenant hợp lệ, cần xét use case đó. **Không tạo cả hai chỉ vì chúng đều có wildcard**.

## 10. Trường hợp mảng: multikey và giới hạn cần nhớ

Document sản phẩm có thể chứa:

~~~javascript
{
  _id: "p-401",
  attributes: {
    sizesEU: [40, 41, 42],
    colors: ["black", "brown"],
    upper: { material: "leather" }
  }
}
~~~

Truy vấn:

~~~javascript
db.products.find({
  "attributes.sizesEU": 41
})
~~~

`p-401` khớp vì mảng chứa 41. Wildcard index có cách xử lý array/multikey riêng; việc một document chứa nhiều phần tử có thể tạo nhiều index entry. Dữ liệu có mảng rất lớn hoặc object lồng nhiều lớp sẽ làm index nhiều key hơn và tăng chi phí.

### 10.1. So sánh một giá trị trong mảng

~~~javascript
db.products.find({
  "attributes.colors": "black"
})
~~~

Query có thể tìm những sản phẩm chứa màu đen trong mảng. Trong bộ dữ liệu mẫu, `p-401` và `p-501` có màu black; các sản phẩm khác lưu màu ở `attributes.color` là **đường dẫn khác**.

Điều này minh họa một vấn đề data modeling: `color` và `colors[]` không phải một đường dẫn logic duy nhất. Wildcard index không tự hợp nhất hai field có ý nghĩa gần nhau.

### 10.2. Các điều kiện phải thuộc cùng phần tử mảng object

Ví dụ:

~~~javascript
{
  attributes: {
    variants: [
      { color: "red", stock: 0 },
      { color: "blue", stock: 10 }
    ]
  }
}
~~~

Query:

~~~javascript
{
  "attributes.variants.color": "red",
  "attributes.variants.stock": { $gt: 0 }
}
~~~

có thể khớp document dù không có variant đỏ nào còn hàng, vì màu đỏ thuộc một phần tử và stock > 0 thuộc phần tử khác.

Truy vấn đúng:

~~~javascript
db.products.find({
  "attributes.variants": {
    $elemMatch: {
      color: "red",
      stock: { $gt: 0 }
    }
  }
})
~~~

`$elemMatch` bảo đảm cùng phần tử. **Một wildcard index không tự sửa sai ngữ nghĩa của hai predicate dotted field**. Đồng thời, không nên giả định wildcard index có đầy đủ khả năng kết hợp bounds của compound multikey index chuyên dụng cho cấu trúc mảng này; phải kiểm tra kế hoạch.

### 10.3. Mảng lồng nhau quá sâu

Array of arrays, nhiều cấp object và kiểu hỗn hợp có thể làm việc lập key và query bounds phức tạp. Tính năng index chính xác cho những mẫu như vậy phụ thuộc phiên bản và quy tắc multikey. Nếu một use case cần query cấu trúc quá sâu thường xuyên, cân nhắc **đơn giản hóa schema** hoặc tách thực thể con thành collection có field ổn định, thay vì dựa vào wildcard cho mọi tầng.

## 11. Những giới hạn cần phân biệt với index thường

Wildcard index phục vụ một mục tiêu đặc thù: **field path không dự đoán đầy đủ**. Một số kỳ vọng về B-tree compound index không nên được áp dụng máy móc.

| Kỳ vọng sai | Thực tế cần nhớ |
|---|---|
| Có wildcard là mọi query đều dùng index | Planner vẫn cân nhắc selectivity, field path, giá trị, sort và chi phí |
| Một wildcard scan tối ưu nhiều predicate thuộc các path khác nhau | Không mặc định; có thể chỉ dùng một path rồi FETCH kiểm tra phần còn lại |
| Wildcard thay compound index cho filter + sort ổn định | Không; compound index chuyên dụng thường có lợi thế rõ |
| Wildcard index tự xử lý tìm kiếm full-text | Không; text/search có cơ chế khác |
| Wildcard index tự phân biệt mọi kiểu schema theo nghiệp vụ | Không; field path/type vẫn cần được chuẩn hóa |
| Wildcard index luôn cung cấp covered query | Không nên giả định; coverage bị giới hạn, phải đo `explain()` |
| Wildcard chắc chắn giúp `sort` trên mọi field động | Không; cần kiểm tra query shape, sort stage và index hỗ trợ |
| Wildcard index bảo đảm field tồn tại hoặc duy nhất | Không; validation và unique business constraints cần thiết kế riêng |
| Có index trên field thiếu là query `$exists:false` sẽ nhanh | Field không có giá trị thường không có key index hữu ích; query cần kiểm tra khả năng sử dụng index |

### 11.1. Truy vấn một object nguyên khối khác truy vấn field con

Ví dụ:

~~~javascript
db.products.find({
  "attributes.cpu.cores": 8
})
~~~

chỉ định **đường dẫn scalar cụ thể**, phù hợp với mục tiêu wildcard. Nhưng:

~~~javascript
db.products.find({
  "attributes.cpu": { cores: 8, family: "Core" }
})
~~~

là phép so sánh object ở một path. Query equality trên object nguyên khối có ngữ nghĩa về cấu trúc/giá trị khác với so sánh từng field con và không mặc định được wildcard index tối ưu theo cùng cách. Trong thiết kế search, ưu tiên truy vấn các field con rõ ràng:

~~~javascript
db.products.find({
  "attributes.cpu.cores": 8,
  "attributes.cpu.family": "Core"
})
~~~

Rồi đo xem query planner dùng wildcard index hay nên tạo index thường nếu use case quá phổ biến.

### 11.2. Sort không tự được “tặng kèm”

Query:

~~~javascript
db.products.find({
  "attributes.ramGB": { $gte: 16 }
}).sort({
  price: 1
})
~~~

Index `{"attributes.$**":1}` nằm ở nhánh attributes, còn `price` là field khác. Không có cơ sở để giả định wildcard index tự cung cấp thứ tự giá; MongoDB có thể thêm stage SORT hoặc chọn đường truy cập khác.

Nếu query phổ biến, cân nhắc index:

~~~javascript
db.products.createIndex(
  {
    category: 1,
    "attributes.ramGB": 1,
    price: 1
  },
  { name: "idx_category_ram_price" }
)
~~~

Thứ tự key cần phân tích theo equality, range, sort; khi RAM là điều kiện range, index có thể không cung cấp sort toàn cục theo price như mong muốn. Đây là nơi áp dụng ESR và benchmark chứ không chọn index theo tên field.

### 11.3. Covered query cần kiểm chứng

Một query projection ít field:

~~~javascript
db.products.find(
  { "attributes.ramGB": 16 },
  { _id: 0, "attributes.ramGB": 1 }
)
~~~

không mặc định được phục vụ hoàn toàn từ wildcard index. Engine có thể cần FETCH document vì cách tổ chức wildcard index và điều kiện coverage. Đo `totalDocsExamined` và các stage thay vì chỉ nhìn projection ít field rồi kết luận covered.

### 11.4. Kiểu null và field thiếu

`attributes.ramGB` có thể không tồn tại ở camera/chair. Wildcard index là loại index có những quy tắc tương tự sparse đối với các đường dẫn field hiện hữu: không có đường dẫn thì không có key cho giá trị của path ấy theo cách đơn giản. Query như:

~~~javascript
db.products.find({
  "attributes.ramGB": { $exists: false }
})
~~~

không nên được kỳ vọng sẽ dùng wildcard index để duyệt “mọi document không có field”. Truy vấn về thiếu field cần lập kế hoạch riêng; có thể dùng schema chuẩn hơn hoặc cờ hiện diện nếu loại truy vấn này cực kỳ thường xuyên.

Truy vấn `{field:null}` trong MongoDB có ngữ nghĩa khác với `{field:{$exists:false}}` và có thể khớp cả field null hoặc vắng mặt trong các trường hợp phù hợp. Không suy diễn kết quả null/missing chỉ từ việc index có hay không có key.

### 11.5. Không dùng wildcard làm unique business constraint mặc định

Để đảm bảo SKU là duy nhất trong tenant:

~~~javascript
db.products.createIndex(
  { tenantId: 1, sku: 1 },
  {
    unique: true,
    name: "uq_tenant_sku"
  }
)
~~~

Đây là ràng buộc **cụ thể về nghiệp vụ**. Wildcard index không có nhiệm vụ xác định tất cả field động đều unique; unique constraints cần được thiết kế trên field/compound key rõ ràng. Khi schema linh hoạt, càng phải phân biệt **field động để tìm kiếm** với **khóa định danh bất biến**.

## 12. `wildcardProjection`: index đúng nhánh, tránh key vô ích

Giả sử một document chứa:

~~~javascript
{
  _id: "flex-001",
  type: "product",
  attributes: {
    material: "steel",
    weightKg: 2.5
  },
  customFields: {
    partnerCode: "P-100"
  },
  debugDetails: {
    internalNotes: "unindexed"
  },
  rawPayload: {
    // Payload import lớn, không cần query trực tiếp theo mọi field.
    source: "supplier-xyz"
  }
}
~~~

Nếu index toàn document `{"$**":1}`, phần `debugDetails` và `rawPayload` có thể tạo thêm những key ít giá trị. Có thể lập index chỉ cho `attributes` và `customFields`:

~~~javascript
db.flex_documents.createIndex(
  { "$**": 1 },
  {
    name: "idx_flex_selected",
    wildcardProjection: {
      attributes: 1,
      customFields: 1
    }
  }
)
~~~

Hoặc dùng exclusion:

~~~javascript
db.flex_documents.createIndex(
  { "$**": 1 },
  {
    name: "idx_flex_excluding_payload",
    wildcardProjection: {
      debugDetails: 0,
      rawPayload: 0
    }
  }
)
~~~

Đây là **các cấu hình minh họa thay thế**. Trước khi tạo trong môi trường thật:

- Thống kê query thực tế theo nhánh.
- Xác định field nào không bao giờ được dùng để filter.
- Đánh giá kích thước document và số key dự kiến.
- Kiểm tra cú pháp projection và giới hạn tương ứng với key pattern/phiên bản.
- Không nhầm `wildcardProjection` với projection của `find()` hoặc `$project` trong aggregation.

### 12.1. Vì sao không phải cứ exclusion càng nhiều càng tốt?

Loại trừ một nhánh sẽ giảm phần dữ liệu index, nhưng nếu sau này API cần query nhánh đó, wildcard index không hỗ trợ nữa. Cần quản lý catalog các loại filter được UI/API hỗ trợ, log truy vấn thực và migration khi phạm vi index thay đổi.

### 12.2. Tránh index payload bí mật không cần thiết

Một nhánh `customMetadata` có thể vô tình chứa token, ghi chú nội bộ hoặc PII. Index trên dữ liệu này làm tăng số bản sao vật lý/đường truy cập cần kiểm soát. Thiết kế nên tách thông tin nhạy cảm khỏi khu vực wildcard hoặc giới hạn projection. **Index không tự cấp quyền**, nhưng vẫn là một cấu trúc lưu dữ liệu và có chi phí bảo vệ, backup, mã hóa.

## 13. Đo query planner bằng `explain("executionStats")`

Đừng đánh giá wildcard index chỉ bằng cách `createIndex()` thành công. Hãy kiểm tra các query tiêu biểu:

~~~javascript
db.products.find({
  "attributes.sensor.megapixels": { $gte: 20 }
}).explain("executionStats")
~~~

Và:

~~~javascript
db.products.find({
  "attributes.ramGB": { $gte: 16 }
}).explain("executionStats")
~~~

### 13.1. Những chỉ số cần xem

| Thành phần | Cách hiểu |
|---|---|
| `queryPlanner.winningPlan` | Đường thực thi được chọn |
| `IXSCAN` | Stage quét index key |
| `COLLSCAN` | Stage quét collection |
| `FETCH` | Stage đọc document để trả field hoặc kiểm tra predicate bổ sung |
| `SORT` | Có bước sắp xếp riêng |
| `indexName` | Index mà kế hoạch đang sử dụng |
| `indexBounds` | Phạm vi key mà index scan xét |
| `totalKeysExamined` | Số index key được kiểm tra |
| `totalDocsExamined` | Số document được kiểm tra |
| `nReturned` | Số document trả về |
| `executionTimeMillis` | Thời gian thực thi được ghi nhận trong lần giải thích |

Wildcard index có thông tin về **path** trong cơ chế lập key/plan. Cách thể hiện chính xác của path và stage có thể khác theo phiên bản/execution engine; không nên viết công cụ giám sát phụ thuộc cứng vào một đường dẫn JSON duy nhất trong `explain()`.

### 13.2. Ba kế hoạch thường gặp

**A. `COLLSCAN`:** có thể query không phù hợp index, hoặc collection quá nhỏ khiến scan rẻ hơn. Bộ dữ liệu lab 10 document có thể gặp COLLSCAN dù đã tạo wildcard index.

**B. `IXSCAN` + `FETCH`:** index giúp tìm ứng viên theo một path, MongoDB đọc document để trả field khác hoặc kiểm tra điều kiện còn lại. Đây là tình huống bình thường.

**C. `IXSCAN` + `SORT`:** filter dùng index nhưng kết quả vẫn cần sắp xếp riêng. Nếu sort đắt và query thường xuyên, cần xem index chuyên dụng.

### 13.3. So wildcard với index chuyên dụng

Giả sử API laptop thường lọc RAM và sort giá:

~~~javascript
const query = {
  category: "laptop",
  "attributes.ramGB": { $gte: 16 }
}

db.products.find(query)
  .sort({ price: 1 })
  .limit(20)
  .explain("executionStats")
~~~

Sau đó tạo một index ứng viên trong lab:

~~~javascript
db.products.createIndex(
  {
    category: 1,
    "attributes.ramGB": 1,
    price: 1
  },
  { name: "idx_laptop_ram_price" }
)
~~~

Chạy lại cùng filter/sort/limit/projection rồi so `keysExamined`, `docsExamined`, stage SORT và độ trễ trên dữ liệu đủ lớn. **Không kết luận từ một lần chạy trên 10 sản phẩm**; thống kê bị chi phối bởi kích thước rất nhỏ và cache.

### 13.4. Dùng `hint()` có giới hạn

Khi cần thử một index cụ thể, có thể dùng hint theo tên:

~~~javascript
db.products.find({
  "attributes.ramGB": 16
}).hint("idx_attributes_wildcard")
  .explain("executionStats")
~~~

Khả năng hint wildcard index và cách index scan đáp ứng query cần phù hợp với phiên bản, query shape và index thực tồn tại. `hint` chỉ nên dùng trong phép đo có kiểm soát; không buộc API production dùng một index cố định khi chưa hiểu query planner và tác động khi index đổi.

## 14. Footprint và write amplification

Wildcard index có thể tạo key cho nhiều field thuộc nhánh được index. Với document có 5 field động khác nhau, chi phí index khác với document có 300 field động hoặc một mảng rất dài.

Ví dụ giả định:

~~~text
100.000 sản phẩm
50 thuộc tính scalar được index / sản phẩm

Số entry mức khái niệm có thể ở bậc:
100.000 × 50 = 5.000.000 giá trị/đường dẫn
~~~

Đây là phép tính hình dung quy mô, **không phải công thức chính xác** về số key/byte của WiredTiger: mảng, nested fields, type, deduplication, compression và cách lưu trữ ảnh hưởng đáng kể.

### 14.1. Các nguồn chi phí

| Nguồn | Tác động có thể xảy ra |
|---|---|
| Nhiều field động | Nhiều index key, disk/cache lớn hơn |
| Mảng dài | Multikey entry tăng, query/filter cần xét nhiều value |
| Cập nhật field động | Thêm/bỏ/sửa key tương ứng |
| Thêm một thuộc tính chưa từng có | Không cần định nghĩa index field mới, nhưng có thêm key phải duy trì |
| Index thêm cho mọi query khác | Tổng write amplification tăng |
| Query nhiều field động | Có thể FETCH/scan thêm nhiều document |
| Index build trên collection lớn | CPU, I/O, dung lượng tạm và thời gian vận hành |

### 14.2. Xem dung lượng index

~~~javascript
const stats = db.products.stats()

printjson({
  count: stats.count,
  size: stats.size,
  storageSize: stats.storageSize,
  totalIndexSize: stats.totalIndexSize,
  indexSizes: stats.indexSizes
})
~~~

`indexSizes` giúp nhìn footprint theo tên index. Số liệu storage không tương đương lượng RAM thực tế đang chiếm trong cache, và không phản ánh đầy đủ chi phí các replica, backup, journal hoặc shard.

### 14.3. Xem index được sử dụng thường xuyên không

~~~javascript
db.products.aggregate([
  { $indexStats: {} }
])
~~~

Metric `$indexStats` cho biết thông tin về lượt truy cập index trong phạm vi quan sát. Không kết luận index vô dụng chỉ vì ít lượt sử dụng trong vài giờ: một nhóm filter động chỉ xuất hiện theo mùa hoặc trong tác vụ quản trị vẫn có thể quan trọng.

### 14.4. Cân nhắc tỷ lệ read/write

Nếu hệ thống ghi 100.000 products/giờ nhưng truy vấn dynamic field rất hiếm, wildcard index có thể gây tốn chi phí không tương xứng. Ngược lại, nếu API cho phép lọc thuộc tính tùy biến trên hàng triệu sản phẩm và số lần truy vấn cao, một wildcard index có phạm vi hợp lý có thể giảm đáng kể gánh nặng phải quản lý vô số index chuyên dụng.

Không có ngưỡng “trên N field thì phải dùng wildcard”. Cần đo trên workload, schema shape và SLO.

## 15. Data modeling đi cùng wildcard index

Wildcard index chỉ hiệu quả khi **cách biểu diễn dữ liệu đủ nhất quán** để truy vấn đúng.

### 15.1. Chuẩn hóa đường dẫn field

Ví dụ ba nhóm nhà cung cấp cùng lưu RAM:

~~~javascript
{ attributes: { ramGB: 16 } }
{ attributes: { ram: "16GB" } }
{ attributes: { memory: { size: 16, unit: "GB" } } }
~~~

Đây là **ba đường dẫn/schema khác nhau**. Wildcard index có thể index các path tồn tại nhưng không tự hiểu chúng có cùng ý nghĩa “RAM 16 GB”. Khi API query một path, nó không tự lấy mọi biến thể ngữ nghĩa.

Nên có quy tắc canonicalize:

~~~javascript
{
  attributes: {
    ramGB: 16
  }
}
~~~

Ngoài field canonical, có thể giữ raw input bên ngoài phạm vi index để hỗ trợ audit/import nếu cần.

### 15.2. Data dictionary cho thuộc tính động

Một catalog attribute definition có thể lưu:

~~~javascript
{
  _id: "ramGB",
  categories: ["laptop", "desktop"],
  valueType: "number",
  unit: "GB",
  filterable: true,
  sortable: false,
  min: 1,
  max: 2048
}
~~~

Nó giúp:

- Validate kiểu/range và đơn vị trước khi ghi.
- Quy định field nào được tìm kiếm.
- Sinh UI filter theo category.
- Giới hạn tên path động hợp lệ.
- Lập kế hoạch index cho những thuộc tính có tải query cao.

Wildcard index là một **cơ chế truy cập**, không thay thế việc quản lý schema/metadata nghiệp vụ.

### 15.3. Field name chứa dấu chấm hoặc bắt đầu bằng `$`

MongoDB có quy tắc và API đặc biệt cho field name có dấu chấm hoặc ký tự `$`. Những tên field này không luôn được truy cập như dotted path thông thường. Với các phiên bản và expression đặc thù, có thể cần `$getField` hoặc phương thức khác; wildcard index không tự giải quyết mọi biểu thức truy vấn trên literal field name.

Trong hệ thống có attribute key do đối tác gửi, tốt nhất **chuẩn hóa hoặc ánh xạ sang key an toàn, ổn định**, thay vì coi mọi chuỗi được nhập là đường dẫn MongoDB có thể dùng trực tiếp.

### 15.4. Không biến tên field động thành biểu thức query không kiểm soát

Nếu API nhận:

~~~http
GET /products?attribute=ramGB&min=16
~~~

server có thể xây query:

~~~javascript
const attributeName = "ramGB" // Lấy sau khi kiểm tra whitelist/dictionary.
const path = "attributes." + attributeName

db.products.find({
  [path]: { $gte: 16 }
})
~~~

Trong production, `attributeName` cần được xác thực theo dictionary, giới hạn ký tự/độ dài, quyền truy vấn và kiểu giá trị. **Không nối trực tiếp path từ input không đáng tin** rồi cho phép người dùng điều khiển tùy ý field lõi hoặc toán tử truy vấn.

## 16. Wildcard index so với các mô hình thay thế

### 16.1. Một tập field ổn định, số lượng nhỏ

Nếu chỉ có 5–10 field quan trọng và query rất ổn định, index chuyên dụng thường rõ ràng hơn:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  category: 1,
  "attributes.ramGB": 1
})
~~~

Index này tập trung vào access pattern cụ thể. Wildcard có thể mang nhiều key không cần thiết nếu chỉ một field thực sự được hỏi.

### 16.2. Entity–Attribute–Value (EAV) trong collection riêng

Khi số thuộc tính thay đổi mạnh, có thể tách một document cho mỗi giá trị thuộc tính:

~~~javascript
// Collection product_attribute_values
{
  productId: "p-101",
  tenantId: "t-01",
  attribute: "ramGB",
  numericValue: 16
}

{
  productId: "p-101",
  tenantId: "t-01",
  attribute: "cpuCores",
  numericValue: 8
}
~~~

Index:

~~~javascript
db.product_attribute_values.createIndex({
  tenantId: 1,
  attribute: 1,
  numericValue: 1,
  productId: 1
})
~~~

Ưu điểm: path trở thành dữ liệu ở field `attribute` cố định; dễ index theo loại giá trị, có thể điều khiển số entry/partition. Nhược điểm: số document tăng, truy vấn nhiều thuộc tính cần join/intersection hoặc aggregation phức tạp, tăng round-trip và đồng bộ dữ liệu.

### 16.3. Materialized search document

Một chiến lược khác: collection nghiệp vụ giữ schema đủ chi tiết, còn collection tìm kiếm được chuẩn hóa thành cấu trúc riêng (ví dụ fields filterable đã chọn). Cần pipeline đồng bộ, version và reconciliation giữa dữ liệu gốc với read model.

### 16.4. Search engine hoặc faceted search

Nếu ứng dụng cần full-text relevance, typo tolerance, facet counts, ranking và nhiều điều kiện kết hợp phức tạp, có thể cần MongoDB Search hoặc một search engine chuyên dụng. Wildcard B-tree index phục vụ **truy cập predicate trên field**, không thay thế search index hay bộ máy ranking.

### 16.5. Chọn theo workload

| Mô hình | Điểm mạnh | Khi không lý tưởng |
|---|---|---|
| Index đơn/ghép | Query ổn định, filter/sort mạnh | Hàng nghìn field hiếm và biến đổi |
| Scoped wildcard index | Nhiều field tùy biến trong một nhánh | Query kết hợp nhiều field/sort phức tạp, write-heavy |
| Global wildcard + projection | Field động nằm ở nhiều nhánh, có thể giới hạn | Payload lớn/dữ liệu nhạy cảm, quá nhiều path |
| Compound wildcard | Field lõi ổn định + một path động, phiên bản hỗ trợ | Tổ hợp nhiều path/sort vượt năng lực |
| EAV | Kiểm soát index trên tên thuộc tính/value | Join nhiều thuộc tính, tăng số document |
| Search/read model | Facet, relevance, UI tìm kiếm chuyên biệt | Cần đồng bộ, chi phí vận hành thêm |

## 17. Mẫu kiến trúc thực tế: catalog sản phẩm đa ngành

Một hệ thống có:

- `tenantId`: cố định, dùng để cách ly tenant.
- `category`: cố định, lọc loại sản phẩm.
- `status`: cố định, trạng thái bán.
- `price`: cố định, sắp xếp theo giá.
- `attributes`: object động, mỗi category có trường riêng.

Sơ đồ:

~~~mermaid
flowchart TD
    API["API tìm kiếm sản phẩm"] --> Auth["Xác thực tenant + validate filter"]
    Auth --> Planner["Chọn query theo access pattern"]
    Planner --> Core["Compound index field lõi"]
    Planner --> Dynamic["Wildcard index nhánh attributes"]
    Planner --> Specialized["Index chuyên dụng cho filter rất phổ biến"]
    Core --> Data["products collection"]
    Dynamic --> Data
    Specialized --> Data
    Data --> Response["Trả danh sách sản phẩm"]
~~~

### 17.1. Không để client trực tiếp quyết định index

Backend nhận filter do người dùng yêu cầu, nhưng:

1. Xác thực tenant/role.
2. Kiểm tra thuộc tính có được công bố là filterable.
3. Chuẩn hóa kiểu, đơn vị và giá trị.
4. Giới hạn số predicate, sort key, page size.
5. Tạo query với path được phép.
6. Theo dõi query shape và hiệu năng.

Wildcard index giúp nhiều path có cơ hội được index, nhưng giới hạn đầu vào giúp tránh query đắt hoặc query vượt ranh giới quyền.

### 17.2. Những truy vấn quan trọng để định hướng index

| API | Query tiêu biểu | Chiến lược |
|---|---|---|
| Danh mục theo tenant/category/price | `tenantId,category,status` + sort `price` | Compound index field ổn định |
| Laptop RAM ≥ 16 | `attributes.ramGB` | Scoped wildcard, hoặc index chuyên dụng nếu rất thường |
| Camera sensor ≥ 20 MP | `attributes.sensor.megapixels` | Scoped wildcard |
| Shoes size chứa 41 | `attributes.sizesEU` | Wildcard/multikey, cần đo |
| Filter laptop cả RAM và CPU cores | Hai path trong attributes | Đo wildcard; cân nhắc compound chuyên dụng |
| Full-text tên/mô tả | Text/relevance query | Search index theo nhu cầu, không dùng wildcard thay thế |
| Báo cáo theo giá mọi tenant | `price` range + sort | Index/report model chuyên dụng |

## 18. Triển khai và quản trị index

### 18.1. Liệt kê cấu hình thật

~~~javascript
db.products.getIndexes()
~~~

Đọc key pattern và options để xác nhận tên/path wildcard đã tạo đúng. Đừng coi việc migration chạy không báo lỗi là đủ nếu môi trường có nhiều collection hoặc script có thể chạy vào database khác.

### 18.2. Tạo index trên dữ liệu lớn có chi phí

Trên collection lớn, xây dựng wildcard index có thể cần đọc nhiều document và tạo nhiều key. Trước rollout:

1. Ước lượng kích thước collection, số field động/document, độ sâu nesting và độ dài mảng.
2. Đánh giá disk trống, cache, CPU, I/O, replication và thời điểm triển khai.
3. Xác định query nào cần hưởng lợi, đo trước.
4. Triển khai vào staging với dữ liệu đại diện.
5. Theo dõi index build, latency của read/write và các sự cố.
6. Xác nhận metadata và đo lại query sau khi hoàn thành.

Đặc điểm tạo index trên replica set/sharded cluster và giới hạn build có thể khác giữa các phiên bản; kiểm tra theo deployment thực tế.

### 18.3. Ẩn index để đánh giá tác động

Nếu phiên bản hỗ trợ hidden indexes:

~~~javascript
db.products.hideIndex("idx_attributes_wildcard")

// Khi cần cho planner sử dụng lại:
db.products.unhideIndex("idx_attributes_wildcard")
~~~

Hidden index thường vẫn được duy trì khi ghi, vì vậy đây là công cụ quan sát tác động lên query planner chứ không phải cách giảm chi phí storage. Không ẩn index production nếu chưa kiểm tra những API quan trọng phụ thuộc nó.

### 18.4. Xóa index

~~~javascript
db.products.dropIndex("idx_attributes_wildcard")
~~~

Đây là thao tác thay đổi cấu trúc, không phải truy vấn đọc. Chỉ thực hiện trong lab hoặc change window có kế hoạch, sau khi xác minh index không còn phục vụ query quan trọng. Việc tạo lại trên collection lớn có thể tốn nhiều thời gian/tài nguyên.

### 18.5. Không lạm dụng wildcard index như “phương án dự phòng”

Nếu collection đã có index chuyên dụng cho phần lớn truy vấn, tạo thêm một global wildcard index để “phòng khi cần” có thể làm tăng footprint và write latency đáng kể. Khi muốn thử wildcard:

- Bắt đầu từ nhánh dynamic được xác định.
- Chọn những query không có index tốt hiện tại.
- So hiệu quả trên workload thật.
- Giữ index chỉ khi lợi ích bù chi phí của nó.

## 19. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Tạo `{"$**":1}` dù chỉ `attributes` động | Index cả field không cần tìm | Dùng `{"attributes.$**":1}` |
| Coi wildcard là compound index của mọi thuộc tính | Kỳ vọng nhiều predicate cùng dùng một index scan | Xem query plan, thêm index chuyên dụng cho nhóm query nóng |
| Dùng wildcard thay index phục vụ sort theo giá | Có thể phải sort nhiều dữ liệu | Index core fields/filter/sort thích hợp |
| Không giới hạn path động từ client | Truy vấn khó kiểm soát, rủi ro quyền và tài nguyên | Attribute dictionary + whitelist + auth |
| Để cùng một khái niệm có nhiều field name | Query thiếu sản phẩm hoặc phải OR phức tạp | Canonical schema/path |
| Lưu số dưới dạng chuỗi không thống nhất | Range filter sai kỳ vọng | Validate kiểu, chuẩn hóa đơn vị |
| Không đánh giá array/multikey | Index phình, query khó tối ưu | Giới hạn array, đo key footprint |
| Quên `$elemMatch` trên array object | Ghép điều kiện từ hai phần tử khác nhau | Ràng buộc same-element |
| Tưởng wildcard index tự bảo đảm unique | Duplicate business key | Unique index riêng |
| Dùng wildcard để full-text search | Không có relevance/fuzzy semantics | Text/search index |
| Đặt cùng wildcard ở nhiều phạm vi không rõ mục tiêu | Chi phí ghi/disk bị nhân lên | So workload trước khi giữ nhiều index |
| Cho rằng index càng nhiều thì write càng nhanh | Insert/update/delete tốn thêm công | Bộ index tối thiểu đáp ứng SLO |
| Kết luận benchmark từ 10 document | Query planner có thể COLLSCAN hợp lý | Dataset đủ lớn, workload đại diện |
| Dùng compound wildcard trên phiên bản không hỗ trợ | Lỗi createIndex | Xác nhận phiên bản/tính năng trước rollout |
| Xóa index khi chưa quan sát query hiếm | Làm chậm API ít chạy nhưng quan trọng | `$indexStats` + quan sát đủ chu kỳ + rollback |

## 20. Bài thực hành từ cơ bản đến nâng cao

Sử dụng collection `products` được tạo ở mục 5. Trước khi chạy mỗi query, hãy dự đoán những ID nào sẽ được trả về.

### Bài A — Tạo và hiểu phạm vi

1. Chạy `getIndexes()` để xác nhận index `_id_`.
2. Tạo `{"attributes.$**":1}` với tên `idx_attributes_wildcard`.
3. Chạy lại `getIndexes()`.
4. Giải thích vì sao index này không phải index `tenantId` hoặc `price`.
5. Phân biệt phạm vi với `{"$**":1}` trên toàn document.

### Bài B — Query equality theo path

1. Tìm laptop có `attributes.ramGB = 16`.
2. Tìm camera có `attributes.lensMount = "E"`.
3. Tìm chair có `attributes.material = "mesh"`.
4. Tìm phone có `attributes.features.eSIM = true`.
5. Tìm shoes có `attributes.waterproof = true`.

Chỉ ra những đường dẫn nào được index bởi cùng `idx_attributes_wildcard` và những document nào không có field đang hỏi.

### Bài C — Query range

1. Tìm camera có `attributes.sensor.megapixels >= 20`.
2. Tìm ghế có `attributes.maxLoadKg >= 100`.
3. Tìm laptop có `attributes.cpu.cores >= 8`.
4. Đổi cách lưu một document thành `ramGB: "16"` trong **bản sao lab** và dự đoán query numeric thay đổi thế nào.

### Bài D — Nhiều field động

Query:

~~~javascript
db.products.find({
  category: "laptop",
  "attributes.ramGB": { $gte: 16 },
  "attributes.cpu.cores": { $gte: 8 }
})
~~~

Viết dự đoán kế hoạch: wildcard index có thể hỗ trợ một path, các predicate còn lại có thể được kiểm tra khi FETCH. Sau đó tạo compound index chuyên dụng trong lab và so `explain`. Không giả định mọi predicate đều dùng chung một scan wildcard.

### Bài E — Array

1. Tìm sản phẩm có `attributes.sizesEU = 41`.
2. Tìm sản phẩm có `attributes.colors = "black"`.
3. Giải thích vì sao `attributes.color` (scalar) và `attributes.colors` (array) không phải cùng một path.
4. Với variants là mảng object, viết `$elemMatch` để tìm variant đỏ còn hàng.

### Bài F — Wildcard projection

Giả sử một collection dynamic khác có `attributes`, `customFields`, `rawPayload` và `debugDetails`. Viết:

- Index wildcard toàn document nhưng loại trừ rawPayload/debugDetails.
- Index wildcard chỉ bao gồm attributes/customFields.
- Giải thích vì sao hai phương án không nên được tạo đồng thời chỉ theo thói quen.

### Bài G — Multi-tenant

Nếu MongoDB hỗ trợ compound wildcard index, đề xuất:

~~~javascript
{ tenantId: 1, "attributes.$**": 1 }
~~~

So với chỉ `{"attributes.$**":1}` cho query có `tenantId`. Nêu yêu cầu kiểm tra phiên bản, index usage và tác động tới write throughput.

### Bài H — Lựa chọn kiến trúc

Cho ba workload:

1. **A:** Chỉ có ba field cố định `brand`, `price`, `status` và ít thay đổi.
2. **B:** Có 300 loại thuộc tính dynamic, UI filter mỗi lần chọn một thuộc tính.
3. **C:** Có hàng triệu sản phẩm, search cần facet đa thuộc tính, ranking text, sort giá, phân trang sâu.

Đề xuất index thường, wildcard hoặc search/read model cho từng loại. Giải thích đánh đổi truy vấn/chi phí ghi và vận hành.

### Bài I — Đo lường

Thực hiện:

~~~javascript
db.products.find({
  "attributes.ramGB": { $gte: 16 }
}).explain("executionStats")

db.products.aggregate([
  { $indexStats: {} }
])

db.products.stats().indexSizes
~~~

Ghi lại index được dùng, `nReturned`, `totalKeysExamined`, `totalDocsExamined` và footprint. Với dataset 10 document, không suy luận index nhanh hơn một cách đáng kể chỉ vì chênh lệch vài mili giây.

## 21. Gợi ý đáp án thực hành

**Bài B — Equality:**

~~~javascript
db.products.find({ "attributes.ramGB": 16 })
// p-101

db.products.find({ "attributes.lensMount": "E" })
// p-201

db.products.find({ "attributes.material": "mesh" })
// p-301

db.products.find({ "attributes.features.eSIM": true })
// p-501

db.products.find({ "attributes.waterproof": true })
// p-401
~~~

**Bài C — Range:**

~~~javascript
db.products.find({
  "attributes.sensor.megapixels": { $gte: 20 }
})
// p-201

db.products.find({
  "attributes.maxLoadKg": { $gte: 100 }
})
// p-301

db.products.find({
  "attributes.cpu.cores": { $gte: 8 }
})
// p-101, p-102
~~~

**Bài E — Array:**

~~~javascript
db.products.find({ "attributes.sizesEU": 41 })
// p-401

db.products.find({ "attributes.colors": "black" })
// p-401, p-501

db.products.find({
  "attributes.variants": {
    $elemMatch: {
      color: "red",
      stock: { $gt: 0 }
    }
  }
})
// Chỉ khớp document thực sự có một variant đỏ còn hàng.
~~~

**Bài H — Kiến trúc:** A nên ưu tiên index chuyên dụng theo filter/sort. B có thể hưởng lợi từ scoped wildcard, kết hợp dictionary và validation. C cần xét search/read model và bộ index dành cho facet/sort/filter phổ biến; wildcard đơn độc thường không giải quyết hết bài toán.

## 22. Câu hỏi ôn tập

**1. Wildcard index khác single-field index thế nào?**

Single-field index tổ chức key cho một đường dẫn field đã biết. Wildcard index tổ chức nhiều đường dẫn trong phạm vi wildcard, phù hợp khi tên field cần query biến đổi.

**2. `{"$**":1}` khác `{"attributes.$**":1}` ở đâu?**

Index đầu nhắm tới nhiều path toàn document theo quy tắc wildcard. Index sau chỉ nhắm các đường dẫn dưới `attributes`, giúp giới hạn phạm vi khi field lõi không cần wildcard.

**3. `wildcardProjection` dùng để làm gì?**

Chọn hoặc loại những nhánh được lập index trong phạm vi hỗ trợ, nhờ đó tránh index các field không cần truy vấn. Nó không điều khiển field được trả trong một lệnh `find()`.

**4. Wildcard index có giúp query trên field mới không cần tạo index riêng?**

Có thể, nếu field mới nằm trong phạm vi wildcard và loại dữ liệu/query được hỗ trợ. Nó vẫn làm phát sinh index key và chi phí ghi.

**5. Tại sao wildcard index không thay compound index cho mọi query?**

Wildcard tổ chức nhiều path/value, không có đầy đủ cấu trúc thứ tự của một compound index riêng cho tổ hợp filter/sort cố định. Query nhiều path có thể vẫn cần FETCH hoặc index khác.

**6. Wildcard index có tự tối ưu sort theo giá không?**

Không. Nếu `price` ngoài phạm vi wildcard và sort là phần quan trọng, cần đánh giá index thông thường phù hợp với filter và sort.

**7. Có thể dùng wildcard index để tìm giá trị trong array không?**

Có khả năng hỗ trợ một số query array/multikey, nhưng các quy tắc lập index, query bounds và chi phí cần kiểm chứng theo cấu trúc array/phiên bản. Không coi wildcard là giải pháp chung cho mọi dạng nested arrays.

**8. Vì sao `$elemMatch` vẫn quan trọng khi có wildcard index?**

Vì `$elemMatch` bảo đảm nhiều điều kiện cùng đúng trên một phần tử array object. Index không tự sửa truy vấn ghép điều kiện từ hai phần tử khác nhau.

**9. Wildcard index có cưỡng chế tên field và kiểu dữ liệu không?**

Không. Cần schema validation, attribute dictionary hoặc quy trình chuẩn hóa để bảo đảm kiểu/đơn vị/path.

**10. Compound wildcard index dùng khi nào?**

Khi có field lõi ổn định như `tenantId` và path động như `attributes.*`, trên phiên bản có hỗ trợ (từ MongoDB 7.0). Phải đánh giá khả năng query/sort và chi phí trên deployment thực.

**11. Nếu cùng RAM 16 GB được lưu thành `ramGB`, `ram` và `memory.size` thì wildcard tự hiểu là một field không?**

Không. Đó là ba path khác nhau. Cần canonicalization hoặc query logic biết rõ các biến thể.

**12. Một wildcard index có bảo đảm covered query không?**

Không được giả định. Cần `explain()` và kiểm tra plan/`totalDocsExamined`; một số kiểu truy vấn wildcard có hạn chế coverage.

**13. Tại sao không nên lập wildcard index toàn bộ trên document có raw payload lớn?**

Nó có thể tạo nhiều key không phục vụ truy vấn, tăng disk/cache và write amplification. Nên giới hạn nhánh hoặc wildcardProjection.

**14. MongoDB luôn dùng wildcard index sau khi tạo không?**

Không. Query planner có thể chọn index khác hoặc COLLSCAN, nhất là trên tập dữ liệu nhỏ hoặc khi filter/sort không phù hợp.

**15. Wildcard index có thay search engine cho full-text và facet không?**

Không. Nó phục vụ query trên đường dẫn field; relevance, phân tích ngôn ngữ, facet chuyên biệt và typo tolerance cần cơ chế search/read model thích hợp.

## 23. Bảng lệnh tham khảo nhanh

| Mục đích | Mẫu lệnh |
|---|---|
| Wildcard toàn document | `db.c.createIndex({"$**":1})` |
| Wildcard dưới attributes | `db.c.createIndex({"attributes.$**":1})` |
| Wildcard chỉ các nhánh được chọn | `db.c.createIndex({"$**":1},{wildcardProjection:{attributes:1,customFields:1}})` |
| Wildcard loại trừ payload | `db.c.createIndex({"$**":1},{wildcardProjection:{rawPayload:0,debugDetails:0}})` |
| Compound wildcard nếu phiên bản hỗ trợ | `db.c.createIndex({tenantId:1,"attributes.$**":1})` |
| Query equality path động | `db.c.find({"attributes.ramGB":16})` |
| Query range path động | `db.c.find({"attributes.sensor.megapixels":{$gte:20}})` |
| Query array scalar | `db.c.find({"attributes.sizesEU":41})` |
| Query array object same-element | `db.c.find({"attributes.variants":{$elemMatch:{color:"red",stock:{$gt:0}}}})` |
| Liệt kê index | `db.c.getIndexes()` |
| Phân tích plan | `db.c.find(filter).explain("executionStats")` |
| Xem footprint | `db.c.stats().indexSizes` |
| Quan sát truy cập index | `db.c.aggregate([{$indexStats:{}}])` |
| Ẩn index nếu hỗ trợ | `db.c.hideIndex("index_name")` |
| Hiện lại index | `db.c.unhideIndex("index_name")` |
| Xóa index | `db.c.dropIndex("index_name")` |

## 24. Checklist quyết định trước khi dùng wildcard index

- [ ] Cấu trúc field thật sự biến đổi, hay chỉ giá trị của field cố định biến đổi?
- [ ] Đã xác định rõ nhánh động như `attributes` chưa?
- [ ] Có dùng scoped wildcard thay cho global wildcard được không?
- [ ] Có nhánh payload/debug/PII cần loại khỏi index không?
- [ ] Các path và kiểu dữ liệu đã được canonicalize và validate chưa?
- [ ] Những query có nhiều predicate/path và sort quan trọng đã được tách thành nhóm workload chưa?
- [ ] Đã cân nhắc index đơn/ghép chuyên dụng cho filter nóng chưa?
- [ ] Có query về field thiếu/null hoặc array lồng sâu cần kiểm tra riêng không?
- [ ] Có cần compound wildcard và deployment đã hỗ trợ phiên bản/tính năng chưa?
- [ ] Đã đo `explain` trên dữ liệu đủ lớn, quan sát FETCH/SORT và key/doc examined chưa?
- [ ] Đã ước lượng index size, write amplification và tác động cache chưa?
- [ ] Có monitoring qua `getIndexes()`, `$indexStats` và `stats()` chưa?
- [ ] Có kế hoạch rollout/rollback thay đổi index trên replica set/sharded cluster chưa?
- [ ] API dynamic filter đã có whitelist, authentication, query limits và giới hạn tài nguyên chưa?

## 25. Kết luận

**Wildcard index** là công cụ quan trọng khi MongoDB chứa document có **đường dẫn field biến đổi**. Cú pháp `{"$**":1}` mở rộng phạm vi toàn document, còn `{"attributes.$**":1}` giúp tập trung vào nhánh thuộc tính động; `wildcardProjection` cho phép kiểm soát những nhánh được index. Chúng giúp nhiều query trên các thuộc tính khác nhau có một đường truy cập khả thi mà không phải tạo hàng trăm index riêng.

Tuy nhiên, wildcard index **không thay thế mọi compound index, không bảo đảm sort/coverage cho mọi query và không quản lý schema hoặc business uniqueness**. Chọn scoped wildcard khi field thực sự động, giữ index thông thường cho filter/sort ổn định, dùng validator và attribute dictionary để bảo vệ tính đúng đắn, rồi đo `explain("executionStats")`, footprint và tải ghi. Mục tiêu cuối cùng không phải “index mọi field” mà là **cho những truy vấn quan trọng một đường truy cập tốt với chi phí vận hành hợp lý**.
