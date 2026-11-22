# Danh mục sản phẩm: thuộc tính biến đổi và truy vấn bộ lọc trong MongoDB

Một danh mục thương mại điện tử hiếm khi có một cấu trúc dữ liệu cố định cho mọi sản phẩm. Laptop có **RAM, dung lượng SSD, kích thước màn hình, CPU**; điện thoại có **mạng di động, camera, dung lượng pin**; giày có **màu, kích cỡ, chất liệu**; thực phẩm có **khối lượng, hạn sử dụng, thành phần**. Trong khi đó, ứng dụng vẫn cần tìm kiếm, lọc nhiều điều kiện, phân trang, sắp xếp theo giá và hiển thị các **bộ lọc động (facets)** phù hợp với danh mục đang xem.

MongoDB hỗ trợ document linh hoạt nên phù hợp với những thuộc tính biến đổi theo loại sản phẩm. Nhưng **linh hoạt không có nghĩa lưu mọi thứ vào một object tùy ý rồi truy vấn tùy ý vẫn nhanh**. Cấu trúc field, cách biểu diễn giá trị, hệ thống quy định thuộc tính, loại index, vị trí lưu variants và cách xây truy vấn phải được thiết kế đồng bộ.

Ví dụ mục tiêu:

> Trong danh mục laptop, tìm những sản phẩm đang bán của thương hiệu Acer, RAM tối thiểu 16 GB, giá không quá 30 triệu đồng, sắp xếp theo giá tăng dần; đồng thời hiển thị số lượng sản phẩm tương ứng với các bộ lọc như thương hiệu, dung lượng RAM và ổ cứng.

Bài học thuộc chương **Thiết kế ứng dụng** và tập trung vào **mô hình danh mục sản phẩm có thuộc tính biến đổi và truy vấn bộ lọc** trong MongoDB. Những ví dụ dùng dữ liệu giả trong database thử nghiệm, không mặc định là cấu hình production.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **thuộc tính chung**, **thuộc tính theo danh mục**, **thuộc tính biến thể/SKU** và **thuộc tính phục vụ tìm kiếm**.
2. Thiết kế document MongoDB cho các sản phẩm thuộc nhiều loại mà không tạo một collection riêng cho mọi nhóm sản phẩm nhỏ.
3. So sánh mô hình **subdocument động**, **Attribute Pattern dạng mảng key–value** và **hybrid schema**.
4. Chuẩn hóa tên thuộc tính, kiểu giá trị, đơn vị đo, cách biểu diễn range và tập giá trị hợp lệ.
5. Viết bộ lọc bằng **equality, $in, range, $elemMatch, $all** mà không nhầm điều kiện giữa các phần tử mảng.
6. Thiết kế **multikey indexes**, index thông thường, wildcard indexes và index cho query thường dùng.
7. Xây dựng **faceted search** bằng aggregation, hiểu self-excluding facets và phân trang.
8. Tách **product** khỏi **variant/SKU** để lọc màu/kích cỡ/tồn kho đúng cặp thuộc tính.
9. Tạo query an toàn trong **Java MongoDB Sync Driver** và **Spring Data MongoDB**, tránh nhận operator/field tùy ý từ người dùng.
10. Kiểm thử dữ liệu, tối ưu explain/latency và triển khai mở rộng thuộc tính theo nhiều phiên bản ứng dụng.

## 2. Ngôn ngữ nghiệp vụ cần thống nhất

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Product** | Một sản phẩm logic để hiển thị | Laptop Acer A14 |
| **Category** | Nhóm phân loại sản phẩm | laptops, phones, shoes |
| **Attribute/Specification** | Thuộc tính mô tả | ramGB = 16 |
| **Facet** | Chiều có thể lọc và hiển thị số lượng | RAM: 8/16/32 GB |
| **Variant/SKU** | Biến thể có thể bán/đặt hàng riêng | Giày màu đen size 41 |
| **Inventory** | Số lượng có thể bán của một SKU/địa điểm | SKU-001 còn 5 chiếc |
| **Offer/Price** | Giá, tiền tệ, khuyến mãi/khả dụng theo kênh | 22.000.000 VND |
| **Search document** | Bản ghi tối ưu cho tìm kiếm/listing | Brand, category, search attributes |
| **Attribute definition** | Cấu hình định nghĩa kiểu và bộ lọc | ramGB: number, min/max |

Không nên nhầm:

- **Product ID** với **SKU ID**: một sản phẩm có thể có nhiều SKU.
- **Giá hiển thị** với **giá cuối cùng khi thanh toán**: giá thay đổi theo kênh/khuyến mãi/thời điểm.
- **Tồn kho tổng hợp** với **tồn kho biến thể cụ thể**: có size 40 màu đen không có nghĩa có size 41 màu đen.
- **Facet count** với **số hàng còn tồn kho**: một facet có thể đếm sản phẩm, SKU hoặc offers; phải định nghĩa đơn vị đo rõ.

## 3. Các câu hỏi cần trả lời trước khi thiết kế schema

Trước khi chọn document shape, hãy viết danh sách query thật:

~~~text
GET /products?category=laptops&brand=Acer&ramGBMin=16&maxPrice=30000000
GET /products?category=phones&storageGB=256
GET /products?category=shoes&color=black&sizeEU=41&inStock=true
GET /products?category=laptops&sort=price_asc&pageSize=24
GET /products/{id}
GET /categories/{id}/facets
~~~

Các quyết định quan trọng:

- Sản phẩm mới có bao nhiêu loại category? Mỗi category có những attributes nào?
- Field nào dùng **filter rất thường xuyên**, field nào chỉ hiển thị ở trang chi tiết?
- Người dùng chọn nhiều giá trị của cùng một facet là **OR** hay **AND**?
- Các thuộc tính có kiểu số, ngày, String, Boolean hay mảng?
- Giá và tồn kho nằm ở product, SKU, offer hay nhiều stores?
- Cần facets cập nhật theo kết quả đang lọc hay chỉ counts cố định cho category?
- Có nhiều tenants/sellers/countries/currencies không?
- Mục tiêu độ trễ, số sản phẩm, tần suất cập nhật và số kết quả có bao nhiêu?

**Schema cần xuất phát từ các truy vấn và quy tắc nghiệp vụ**, không chỉ từ việc MongoDB cho phép document lồng nhau.

## 4. Bộ dữ liệu mẫu xuyên suốt

Tạo database **catalog_lab** và collection **products** trên môi trường học tập. Ví dụ dưới dùng giá nguyên theo đơn vị **VND**, tránh dùng Double cho giá tiền.

~~~javascript
use catalog_lab

db.products.insertMany([
  {
    _id: "L-101",
    tenantId: "SHOP-A",
    categoryId: "laptops",
    brandId: "acer",
    title: "Acer Swift A14",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("22000000"),
    attributes: {
      ramGB: 16,
      storageGB: 512,
      screenInch: 14,
      color: "black"
    }
  },
  {
    _id: "L-102",
    tenantId: "SHOP-A",
    categoryId: "laptops",
    brandId: "lenovo",
    title: "Lenovo IdeaPad S",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("16000000"),
    attributes: {
      ramGB: 8,
      storageGB: 256,
      screenInch: 15.6,
      color: "gray"
    }
  },
  {
    _id: "L-103",
    tenantId: "SHOP-A",
    categoryId: "laptops",
    brandId: "dell",
    title: "Dell X Pro",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("33000000"),
    attributes: {
      ramGB: 16,
      storageGB: 1024,
      screenInch: 15.6,
      color: "silver"
    }
  },
  {
    _id: "L-104",
    tenantId: "SHOP-A",
    categoryId: "laptops",
    brandId: "acer",
    title: "Acer Creator 16",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("40000000"),
    attributes: {
      ramGB: 32,
      storageGB: 1024,
      screenInch: 16,
      color: "black"
    }
  },
  {
    _id: "P-101",
    tenantId: "SHOP-A",
    categoryId: "phones",
    brandId: "samsung",
    title: "Samsung Mobile 256",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("17000000"),
    attributes: {
      ramGB: 8,
      storageGB: 256,
      batteryMAh: 5000,
      color: "black"
    }
  },
  {
    _id: "S-101",
    tenantId: "SHOP-A",
    categoryId: "shoes",
    brandId: "puma",
    title: "Puma Runner",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("1800000"),
    attributes: {
      material: "mesh",
      gender: "unisex"
    }
  },
  {
    _id: "S-102",
    tenantId: "SHOP-A",
    categoryId: "shoes",
    brandId: "nike",
    title: "Nike Runner",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("2400000"),
    attributes: {
      material: "synthetic",
      gender: "unisex"
    }
  },
  {
    _id: "L-X",
    tenantId: "SHOP-B",
    categoryId: "laptops",
    brandId: "acer",
    title: "Other tenant laptop",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("10000000"),
    attributes: {
      ramGB: 64,
      storageGB: 2048,
      color: "black"
    }
  }
]);
~~~

**Lưu ý:** các ID cố định, nên chỉ insert một lần trên collection lab sạch. Không tự xóa collection production để chạy lại ví dụ.

### 4.1. Kết quả truy vấn minh họa

Chỉ tìm thuộc **SHOP-A**, category **laptops**, status ACTIVE, visibility PUBLIC:

| ID | Brand | RAM (GB) | Storage (GB) | Giá (VND) |
|---|---|---:|---:|---:|
| L-101 | acer | 16 | 512 | 22.000.000 |
| L-102 | lenovo | 8 | 256 | 16.000.000 |
| L-103 | dell | 16 | 1024 | 33.000.000 |
| L-104 | acer | 32 | 1024 | 40.000.000 |

Khi lọc **brand=acer**, **RAM ≥ 16 GB**, **price ≤ 30.000.000 VND**, chỉ còn **L-101**.

### 4.2. Tách scope tenant từ đầu

L-**X** là sản phẩm cùng category/brand nhưng thuộc **SHOP-B**. Đây là một bản ghi cố ý để kiểm thử: truy vấn chỉ dựa vào category/brand mà quên **tenantId** có thể vô tình trả sản phẩm của tenant khác.

Các giá trị tenantId cho user request phải được lấy từ **authentication/authorization context** đáng tin cậy, không cho client tự nhận quyền chỉ bằng query parameter.

## 5. Mô hình 1: subdocument attributes động

Document chính dùng:

~~~javascript
{
  _id: "L-101",
  categoryId: "laptops",
  attributes: {
    ramGB: 16,
    storageGB: 512,
    screenInch: 14,
    color: "black"
  }
}
~~~

Một chiếc giày có thể có:

~~~javascript
{
  _id: "S-101",
  categoryId: "shoes",
  attributes: {
    material: "mesh",
    gender: "unisex"
  }
}
~~~

Ưu điểm:

- Đọc rất dễ: **attributes.ramGB**, **attributes.storageGB**.
- Có thể tạo index cụ thể cho những field phổ biến.
- Thuộc tính số vẫn là số, dùng range queries đúng.
- Chỉ lưu những fields thực sự có trên sản phẩm, không cần hàng chục field null.
- Phù hợp khi số nhóm category và tập attributes đã được quản trị.

Hạn chế:

- Số keys có thể tăng nhanh theo ngành hàng.
- Query động với thuộc tính mới khó được index sẵn.
- Hai keys gần nghĩa như **ram**, **memoryGB**, **ramGB** dễ gây dữ liệu phân mảnh.
- Mỗi category cần quy tắc type/units; MongoDB mặc định không tự kiểm tra chúng nếu không cấu hình validator.
- Wildcard index có thể hữu ích cho field khó đoán nhưng không thay mọi compound index đặc thù.

### 5.1. Truy vấn bằng dotted paths

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC",
  brandId: "acer",
  "attributes.ramGB": { $gte: 16 },
  priceVnd: { $lte: NumberLong("30000000") }
}).sort({ priceVnd: 1, _id: 1 });
~~~

Kết quả mong đợi: **L-101**.

### 5.2. Chỉ định field tồn tại hoặc có kiểu hợp lệ

~~~javascript
db.products.find({
  categoryId: "laptops",
  "attributes.ramGB": { $type: "number" }
});
~~~

Kiểu **number** trong $type là alias chung cho các kiểu số BSON phù hợp. Không nên trộn **"16"** (String) và **16** (Number), vì filter range số có thể không hoạt động như mong đợi khi dữ liệu lưu sai kiểu.

### 5.3. Hạn chế của tên key động

Trong dạng object, keys là một phần cấu trúc BSON. Không nhận nguyên tên field hoặc biểu thức operator từ client rồi ghép trực tiếp vào query:

~~~text
User input: arbitrary path/operator
Application: string-concatenate into query
Result: query semantics vượt ngoài các facet được phép
~~~

Cần tra thuộc tính qua **attribute definition registry** có allowlist, validate type và chỉ dựng dotted path đã được đăng ký.

## 6. Mô hình 2: Attribute Pattern dạng mảng key–value

Một lựa chọn khác là biểu diễn thuộc tính thành các phần tử trong mảng:

~~~javascript
{
  _id: "L-101",
  categoryId: "laptops",
  attributes: [
    { key: "ramGB", valueNum: 16 },
    { key: "storageGB", valueNum: 512 },
    { key: "screenInch", valueNum: 14 },
    { key: "color", valueStr: "black" }
  ]
}
~~~

Đây là dạng **Attribute Pattern** thường dùng khi có nhiều loại metadata cần lọc theo tên thuộc tính và giá trị.

### 6.1. Vì sao tách valueNum và valueStr?

Trong thiết kế này, một phần tử có **giá trị đúng kiểu**:

~~~javascript
{ key: "ramGB", valueNum: 16 }
{ key: "color", valueStr: "black" }
{ key: "waterResistant", valueBool: true }
~~~

Nếu một field **value** vừa chứa String vừa Number, truy vấn range và indexing khó quản lý hơn. Phương án tách value fields giúp schema rõ nhưng vẫn cần registry quy định key nào có type gì, ngăn keys trùng và thống nhất unit.

### 6.2. Tìm một điều kiện bằng $elemMatch

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  attributes: {
    $elemMatch: {
      key: "ramGB",
      valueNum: { $gte: 16 }
    }
  }
});
~~~

**$elemMatch** đảm bảo **key=ramGB** và **valueNum≥16** thuộc **cùng một phần tử** của mảng attributes.

### 6.3. Vì sao hai điều kiện dotted notation có thể sai?

Document:

~~~javascript
{
  attributes: [
    { key: "ramGB", valueNum: 8 },
    { key: "storageGB", valueNum: 1024 }
  ]
}
~~~

Query dễ sai ngữ nghĩa:

~~~javascript
db.products.find({
  "attributes.key": "ramGB",
  "attributes.valueNum": { $gte: 16 }
});
~~~

MongoDB có thể match vì một phần tử có **key=ramGB**, trong khi phần tử khác có **valueNum≥16**. Đây là false positive.

Dùng:

~~~javascript
db.products.find({
  attributes: {
    $elemMatch: {
      key: "ramGB",
      valueNum: { $gte: 16 }
    }
  }
});
~~~

### 6.4. Tìm đồng thời hai thuộc tính khác nhau

Muốn **RAM≥16** và **storage≥512**, phải yêu cầu **hai phần tử** tương ứng:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  attributes: {
    $all: [
      {
        $elemMatch: {
          key: "ramGB",
          valueNum: { $gte: 16 }
        }
      },
      {
        $elemMatch: {
          key: "storageGB",
          valueNum: { $gte: 512 }
        }
      }
    ]
  }
});
~~~

**$all** kết hợp nhiều điều kiện **$elemMatch** cho cùng mảng; mỗi điều kiện có thể được thỏa bởi phần tử khác nhau. Đây là AND giữa các thuộc tính.

### 6.5. Nhiều giá trị một facet thường là OR

Ví dụ màu **black hoặc gray**:

~~~javascript
{
  attributes: {
    $elemMatch: {
      key: "color",
      valueStr: { $in: ["black", "gray"] }
    }
  }
}
~~~

| Ý định | Logic |
|---|---|
| RAM tối thiểu 16 và SSD tối thiểu 512 | AND hai thuộc tính |
| Màu đen hoặc xám | OR trong một facet |
| Brand Acer hoặc Dell | $in trên brandId |
| Có cả Wi-Fi và Bluetooth | AND nếu nghiệp vụ yêu cầu cả hai |
| Size 41 màu đen **cùng SKU** | AND trong một variant, không trên hai arrays riêng |

### 6.6. Ưu điểm và giới hạn

Ưu điểm:

- Có thể dùng compound multikey index cho key và typed value.
- Thuận tiện tạo dynamic facets bằng **$unwind + $group**.
- Có chỗ chứa metadata của từng attribute nếu thật sự cần.
- Không tạo một BSON path mới cho mỗi key.

Đánh đổi:

- Document lớn do lặp key.
- Query dễ sai nếu quên $elemMatch.
- Multi-attribute AND có thể không tận dụng index tối ưu cho tất cả điều kiện.
- Compound multikey indexes có giới hạn với nhiều array paths.
- Cần validate không xuất hiện nhiều phần tử trùng key ngoài chủ đích.

## 7. Mô hình 3: hybrid schema

Một giải pháp dễ vận hành là kết hợp **fields cố định** cho những truy vấn phổ biến, **searchable attributes** có kiểu rõ và **specs** linh hoạt ít dùng để lọc:

~~~javascript
{
  _id: "L-101",
  tenantId: "SHOP-A",
  categoryId: "laptops",
  brandId: "acer",
  status: "ACTIVE",
  visibility: "PUBLIC",
  priceVnd: NumberLong("22000000"),
  searchable: {
    ramGB: 16,
    storageGB: 512,
    color: "black"
  },
  specs: {
    cpuModel: "Intel Core example",
    panelType: "IPS",
    ports: ["USB-C", "HDMI"],
    keyboardLayout: "US"
  }
}
~~~

**searchable** là quy ước dữ liệu để phục vụ filter; MongoDB không tự động tạo search index cho field đó.

Hybrid thường phù hợp khi phần lớn requests chỉ lọc **category + brand + price + status**, còn mỗi ngành có vài facets quan trọng như RAM/SSD của laptop hay màu/kích cỡ của giày.

Cần xác định source-of-truth nếu một thông tin đồng thời có trong **searchable** và **specs**, tránh bản sao stale.

## 8. Chọn mô hình qua bảng so sánh

| Tiêu chí | attributes object | Attribute Pattern array | Hybrid |
|---|---|---|---|
| Dễ đọc document | Rất tốt | Trung bình | Tốt |
| Truy vấn exact/range theo field phổ biến | Dễ | Cần $elemMatch | Dễ |
| Thuộc tính khó biết trước | Có | Có | Có |
| Quản lý type/units | Cần registry | Cần registry | Cần registry |
| Index field thường dùng | Dễ tạo index riêng | Multikey có giới hạn | Dễ cho core fields |
| Dynamic facets theo key | Có thể dùng $objectToArray | $unwind thuận tiện | Tùy thiết kế |
| Dung lượng do lặp key | Tương đối thấp | Cao hơn | Phụ thuộc |
| Sai match giữa array elements | Ít với scalar fields | Cao nếu quên $elemMatch | Tùy thuộc cấu trúc |

Không có một đáp án cho mọi catalog. Hệ thống có ít loại sản phẩm ổn định không cần key–value array phức tạp; marketplace nhiều ngành hàng có thể cần registry mạnh và mô hình linh hoạt hơn.

## 9. Attribute definitions: từ điển thuộc tính theo category

MongoDB không tự biết **ramGB** có đơn vị GB, **screenInch** là một số dương hay **color** chỉ nhận những mã chuẩn. Nên tạo metadata registry, ví dụ collection **attributeDefinitions**:

~~~javascript
db.attributeDefinitions.insertMany([
  {
    _id: "laptops.ramGB",
    categoryId: "laptops",
    key: "ramGB",
    valueType: "number",
    unit: "GB",
    filterKind: "range",
    minAllowed: 4,
    maxAllowed: 256,
    visible: true,
    filterable: true
  },
  {
    _id: "laptops.storageGB",
    categoryId: "laptops",
    key: "storageGB",
    valueType: "number",
    unit: "GB",
    filterKind: "multi-select",
    allowedValues: [256, 512, 1024, 2048],
    visible: true,
    filterable: true
  },
  {
    _id: "laptops.color",
    categoryId: "laptops",
    key: "color",
    valueType: "string",
    filterKind: "multi-select",
    allowedValues: ["black", "gray", "silver"],
    visible: true,
    filterable: true
  },
  {
    _id: "shoes.material",
    categoryId: "shoes",
    key: "material",
    valueType: "string",
    filterKind: "multi-select",
    allowedValues: ["mesh", "leather", "synthetic"],
    visible: true,
    filterable: true
  }
]);
~~~

Registry này là **mô hình ứng dụng**, không tự động trở thành MongoDB validator. Cần logic nhập liệu, chuẩn hóa và có thể dùng **$jsonSchema** cho các ràng buộc ổn định.

### 9.1. Metadata hữu ích

| Thuộc tính registry | Lý do cần |
|---|---|
| categoryId + key | Key có nghĩa trong phạm vi ngành hàng |
| valueType | Không trộn String và Number |
| unit | Chuẩn hóa range và hiển thị |
| filterKind | exact, multi-select, numeric range, boolean |
| allowedValues | Chặn giá trị sai và dựng UI |
| filterable | Không mọi spec đều cần query |
| visible | Một số metadata không được công khai |
| multiValued | Có một hay nhiều giá trị |
| displayLabelByLocale | Hiển thị theo ngôn ngữ |
| order, group | Thứ tự và nhóm facet trên UI |
| deprecated | Ngăn writers mới dùng key cũ |

### 9.2. Không đổi key theo ngôn ngữ UI

~~~text
Canonical key: ramGB
Vietnamese label: Dung lượng RAM
English label: Memory capacity
~~~

Seller nhập “RAM”, “Bộ nhớ RAM” hoặc “Memory” cần được map về **ramGB** khi thật sự cùng ngữ nghĩa. Không lưu ba key rồi mong query một key trả mọi sản phẩm.

### 9.3. Chuẩn hóa đơn vị

Ví dụ hai nhà cung cấp nhập:

~~~text
SSD: 512 GB
SSD: 0.5 TB
~~~

Nếu filter dùng storageGB, cần quy tắc thống nhất **decimal GB/TB** và **binary GiB/TiB**. Không tùy tiện làm tròn vì một giá trị có thể đổi vị trí qua ngưỡng filter.

Các fields khác cũng cần chuẩn:

- Khối lượng có thể lưu integer grams.
- Kích thước có thể lưu millimeters.
- Giá lưu integer minor units hoặc Decimal128.
- Thời gian lưu BSON Date/Instant, xác định timezone khi hiển thị.
- Enum lưu mã chuẩn, không lưu nhãn đã dịch.

### 9.4. Missing, null, unknown và not applicable

Giày không có pin, điện thoại có pin nhưng chưa rõ dung lượng:

~~~text
missing          = không lưu field
null             = field có mặt, giá trị null
unknown          = có thuộc tính, chưa biết giá trị
not applicable   = không liên quan category
~~~

Đừng lưu **batteryMAh: 0** cho giày rồi hiểu là pin có dung lượng 0. Chọn một schema có semantics và query nhất quán.

### 9.5. Ngăn duplicates trong Attribute Pattern

Ví dụ dữ liệu xấu:

~~~javascript
{
  attributes: [
    { key: "ramGB", valueNum: 8 },
    { key: "ramGB", valueNum: 32 }
  ]
}
~~~

Nếu RAM là single-valued, hai entries cùng key làm filter >=16 match dù giá trị thực không rõ. Cần validation ở ingestion và update. Không giả định unique multikey index trên **attributes.key** tự bắt mọi trường hợp lặp phần tử trong cùng document; unique multikey index không đảm bảo uniqueness giữa các phần tử của một document theo cách nhiều người kỳ vọng.

## 10. Category hierarchy và filter kế thừa

Một taxonomy có thể là:

~~~text
Electronics
  +-- Computers
      +-- Laptops
      +-- Desktops
  +-- Phones
Fashion
  +-- Shoes
      +-- Running shoes
~~~

Product lưu leaf categoryId, còn collection categories quản lý ancestry:

~~~javascript
{
  _id: "laptops",
  parentId: "computers",
  ancestorIds: ["electronics", "computers"],
  slug: "laptops",
  enabled: true
}
~~~

### 10.1. Lọc cả danh mục cha

Nếu product materialize **categoryAncestorIds**:

~~~javascript
{
  _id: "L-101",
  categoryId: "laptops",
  categoryAncestorIds: ["electronics", "computers"]
}
~~~

thì tìm các sản phẩm thuộc Electronics:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  status: "ACTIVE",
  visibility: "PUBLIC",
  categoryAncestorIds: "electronics"
});
~~~

Giảm nhu cầu truy vấn đệ quy theo từng request, đổi lại phải cập nhật product search documents khi taxonomy đổi.

### 10.2. Facet definitions kế thừa

~~~text
Electronics: brand, price
Computers: processorFamily
Laptops: ramGB, storageGB, screenInch
~~~

Facets cho laptops có thể merge từ ancestors và leaf theo override policy. Cần định nghĩa key nào kế thừa và tác động khi chuyển parent category.

### 10.3. Không nhất thiết một collection cho mỗi category

Một marketplace với hàng nghìn categories mà tạo collections riêng cho tất cả sẽ phức tạp ở index, code, reporting và deployment. Collection chung với **categoryId** và polymorphic attributes thường dễ vận hành, chỉ tách khi có workload/retention/security/lifecycle khác biệt thực sự.

## 11. Thiết kế filter contract cho API

API nên nhận **tham số có kiểu và đã được định nghĩa**, không nhận raw MongoDB query:

~~~text
GET /catalog/search
  ?category=laptops
  &brand=acer
  &minRamGB=16
  &maxPriceVnd=30000000
  &sort=price_asc
  &limit=24
~~~

### 11.1. Chuẩn hóa thành FilterSpec

~~~javascript
{
  scope: {
    tenantId: "SHOP-A",
    status: "ACTIVE",
    visibility: "PUBLIC"
  },
  categoryId: "laptops",
  brandIds: ["acer"],
  numeric: { ramGB: { min: 16 } },
  priceVnd: { max: 30000000 },
  sort: "price_asc",
  limit: 24
}
~~~

**tenantId** do backend lấy từ authentication, không mặc nhiên tin giá trị do user tự khai.

### 11.2. AND giữa facets, OR trong cùng facet

~~~text
brand in [acer, dell]
AND ramGB >= 16
AND storageGB in [512, 1024]
AND price <= 30000000
~~~

MongoDB:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC",
  brandId: { $in: ["acer", "dell"] },
  "attributes.ramGB": { $gte: 16 },
  "attributes.storageGB": { $in: [512, 1024] },
  priceVnd: { $lte: NumberLong("30000000") }
});
~~~

Với bộ dữ liệu mẫu, truy vấn trả **L-101**.

### 11.3. Parse và validate dữ liệu

Query string HTTP **"16"** là String. Backend phải parse thành số và validate:

~~~text
?minRamGB=16   -> integer 16
?minRamGB=abc  -> validation error
?minRamGB=-100 -> validation error
~~~

Không đưa String “16” vào MongoDB rồi mong so sánh numeric đúng. Giá nên dùng long/Decimal128 tùy currency và quy ước kế toán, tránh Double khi cần chính xác tiền tệ.

### 11.4. Scalar range và array range khác nhau

Với scalar attributes.ramGB:

~~~javascript
db.products.find({
  "attributes.ramGB": { $gte: 8, $lte: 16 }
});
~~~

là khoảng [8,16]. Nếu field là mảng nhiều giá trị, hai điều kiện range có thể được thỏa bởi hai phần tử khác nhau; dùng **$elemMatch** khi yêu cầu một phần tử thỏa cả hai.

### 11.5. Semantics cần thống nhất

- Màu và size phải khớp **cùng SKU** nếu muốn mua một tổ hợp cụ thể.
- Features có thể là “có tất cả” ($all), không phải “có ít nhất một” ($in).
- Price cần phân biệt giá niêm yết và giá cuối cùng theo kênh/ưu đãi.
- Availability cần xác định theo toàn hệ thống hay location cụ thể.
- Category cha có thể bao gồm mọi descendants.

## 12. Bộ xử lý filter an toàn

Một pipeline ở tầng ứng dụng:

~~~text
HTTP request
    |
    v
Parse + validate input
    |
    v
Load category attribute definitions
    |
    v
Normalize values / types / units
    |
    v
Resolve tenant and catalog scope from authentication
    |
    v
Build MongoDB query from allowlisted fields
    |
    v
Query + sort + pagination + aggregation facets
    |
    v
Map listing DTO / facet DTO
    |
    v
HTTP response
~~~

### 12.1. Không nhận tùy ý MongoDB operator

Không an toàn:

~~~javascript
// Không dùng cho public API.
const filter = JSON.parse(userSuppliedJson);
db.products.find(filter);
~~~

User có thể đưa cấu trúc vượt khỏi bộ lọc được phép. Thay vào đó backend nhận một điều kiện kiểu:

~~~javascript
{ attribute: "ramGB", comparison: "gte", value: 16 }
~~~

rồi kiểm tra key có trong registry, type number, comparison hợp lệ, giá trị trong range và tổng số điều kiện được giới hạn. Sau đó mới dựng **Bson filter**.

### 12.2. Giới hạn độ phức tạp

Một request có thể gửi 1.000 brands, 100 điều kiện nested và limit một triệu. Dù BSON hợp lệ vẫn có thể làm quá tải.

Nên giới hạn số filters, values mỗi facet, page size, độ sâu category, kích thước payload và thời gian aggregation theo SLO.

### 12.3. Normalization cho String và text search

Brand ID ổn định **acer** tốt hơn các chuỗi hiển thị “Acer Inc.” hoặc “ACER”. Title text search, accent/case-insensitive search và autocomplete có yêu cầu riêng; không mặc định regex chứa user pattern trên title sẽ được index tốt:

~~~javascript
// Tránh đưa trực tiếp userText tùy ý vào regex lớn.
{ title: { $regex: userText, $options: "i" } }
~~~

Cần kiểm soát regex metacharacters, độ dài, sự hỗ trợ của index; có thể cân nhắc Search/autocomplete index chuyên dụng theo sản phẩm và deployment.

## 13. Product và variant/SKU là hai cấp dữ liệu

Một đôi giày **Puma Runner** có thể có:

~~~text
Puma Runner (product)
    |
    +-- black / size 40 / SKU-PUMA-BLK-40 / inStock
    +-- black / size 41 / SKU-PUMA-BLK-41 / outOfStock
    +-- white / size 41 / SKU-PUMA-WHT-41 / inStock
~~~

Nếu lưu sản phẩm với:

~~~javascript
{
  colors: ["black", "white"],
  sizesEU: [40, 41],
  inStock: true
}
~~~

thì câu hỏi **“có size 41 màu đen còn hàng không?”** không thể trả lời đúng chỉ từ ba giá trị độc lập. Black có thể chỉ còn size 40, size 41 còn hàng chỉ với White.

### 13.1. Embedding variants trong product

~~~javascript
{
  _id: "S-101",
  categoryId: "shoes",
  brandId: "puma",
  variants: [
    {
      sku: "PUMA-BLK-40",
      color: "black",
      sizeEU: 40,
      availableQty: 3
    },
    {
      sku: "PUMA-BLK-41",
      color: "black",
      sizeEU: 41,
      availableQty: 0
    },
    {
      sku: "PUMA-WHT-41",
      color: "white",
      sizeEU: 41,
      availableQty: 4
    }
  ]
}
~~~

Để lọc **cùng variant**:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "shoes",
  variants: {
    $elemMatch: {
      color: "black",
      sizeEU: 41,
      availableQty: { $gt: 0 }
    }
  }
});
~~~

Kết quả **không match S-101** vì black/size41 hết hàng.

### 13.2. Truy vấn sai khi không dùng $elemMatch

~~~javascript
db.products.find({
  "variants.color": "black",
  "variants.sizeEU": 41,
  "variants.availableQty": { $gt: 0 }
});
~~~

Có thể match S-101 dựa trên ba phần tử khác nhau. **$elemMatch** là điều kiện cần khi các predicates phải thỏa trong **cùng array element**.

### 13.3. Khi nào tách SKU thành collection riêng?

Embedding phù hợp khi:

- Số variants nhỏ và có giới hạn.
- Trang chi tiết thường đọc hầu hết variants.
- Ít cập nhật đồng thời.
- Document không tăng vô hạn.

Tách **productVariants** phù hợp khi:

- Số SKU lớn hoặc liên tục phát sinh.
- Giá/tồn kho cập nhật thường xuyên.
- Nhiều warehouses/sellers cập nhật đồng thời.
- Cần index/filter và lifecycle riêng.
- Muốn giảm contention cập nhật product document lớn.

~~~javascript
{
  _id: "SKU-PUMA-BLK-40",
  tenantId: "SHOP-A",
  productId: "S-101",
  color: "black",
  sizeEU: 40,
  availableQty: 3,
  active: true
}
~~~

Với model tách riêng, có thể tìm **productIds** có SKU đúng:

~~~javascript
db.productVariants.distinct("productId", {
  tenantId: "SHOP-A",
  active: true,
  color: "black",
  sizeEU: 40,
  availableQty: { $gt: 0 }
});
~~~

Trên catalog lớn, không nên lấy danh sách productIds rất dài rồi dùng **$in** vô hạn; có thể cần search projection đã materialize, aggregation $lookup có index hoặc kiến trúc tìm kiếm theo SKU.

### 13.4. Inventory không chỉ là boolean

Một SKU có thể có:

~~~text
onHand = 10
reserved = 4
damaged = 1
availableToSell = 5
~~~

availableToSell có thể là số tính toán hoặc snapshot, không hẳn là field gốc. Với filter inStock, phải xác định scope warehouse/location và nguồn dữ liệu có thẩm quyền.

Listing phục vụ trải nghiệm; **checkout phải kiểm tra lại giá/tồn kho và thực hiện concurrency control**, không dùng cached listing như cam kết giữ hàng.

### 13.5. Snapshot/search projection của variants

Một model có thể materialize:

~~~javascript
{
  _id: "S-101",
  searchableColors: ["black", "white"],
  searchableSizesEU: [40, 41],
  hasAvailableVariant: true
}
~~~

Các summary fields này hữu ích cho facet count cấp sản phẩm, nhưng **không thể chứng minh** tổ hợp color+size có SKU thật, càng không chứng minh SKU đó còn hàng. Cần thiết kế mapping cặp biến thể:

~~~javascript
{
  availableVariantOptions: [
    { color: "black", sizeEU: 40 },
    { color: "white", sizeEU: 41 }
  ]
}
~~~

Sau đó dùng **$elemMatch**. Summary/materialized search fields phải được cập nhật khi inventory đổi; cần đo độ trễ đồng bộ và nêu rõ tính eventual consistency nếu có.

### 13.6. Product count và SKU count

Ví dụ một sản phẩm giày có ba SKU. Bộ lọc size 41 có thể:

- Đếm **một sản phẩm** nếu có ít nhất một SKU size 41 thỏa.
- Đếm **hai SKU** nếu có hai size 41 khác màu.
- Đếm **một SKU còn hàng** nếu chỉ một size 41 available.

UI cần công bố **đơn vị facet count**; aggregation phải $group theo productId nếu đang xuất counts cấp product.

## 14. Giá và offer: tách dữ liệu biến động nhiều

Một product có thể được bán ở nhiều kênh:

~~~text
Base product: Laptop A
    |
    +-- Seller A, VND, 22,000,000
    +-- Seller B, VND, 22,500,000
    +-- Seller C, USD, 900.00
~~~

Lưu một field **priceVnd** ở product chỉ phù hợp khi đây là giá canonical của **một catalog và một currency**. Marketplace đa sellers/currencies thường cần offers/pricing model riêng:

~~~javascript
{
  _id: "OFFER-101",
  tenantId: "SHOP-A",
  productId: "L-101",
  skuId: "SKU-L-101-A",
  currency: "VND",
  priceMinor: NumberLong("22000000"),
  active: true,
  channel: "web"
}
~~~

**priceMinor** ở VND cần quy tắc nhất quán về đơn vị nhỏ nhất được ứng dụng sử dụng; với currency khác phải xử lý scale theo chuẩn currency, không mặc nhiên mọi đơn vị có hai chữ số thập phân.

### 14.1. Định nghĩa filter giá

Trước khi dùng **minPrice/maxPrice**, trả lời:

- Giá trước hay sau mã giảm giá?
- Giá của SKU rẻ nhất hay sản phẩm chính?
- Giá của seller nào?
- Currency nào và tỷ giá vào thời điểm nào?
- Có bao gồm thuế/phí vận chuyển không?

**Không cộng/trộn giá khác currency** vào cùng một numeric range nếu chưa quy đổi có policy rõ.

### 14.2. Khi nào materialize giá ở product?

Để listing nhanh, có thể lưu:

~~~javascript
{
  minActivePriceVnd: NumberLong("22000000"),
  maxActivePriceVnd: NumberLong("22500000"),
  priceUpdatedAt: ISODate("2026-10-01T00:00:00Z")
}
~~~

Đây là một **read model** có thể stale khi offers đổi. Checkout vẫn cần tính và chốt giá ở workflow đặt hàng; search document không phải hệ thống kế toán.

## 15. Chiến lược index cho truy vấn catalog

Một catalog có hàng trăm thuộc tính nhưng mỗi query chỉ dùng vài trường. **Không tạo một compound index cực dài cho mọi field**; index strategy nên xuất phát từ query patterns thực tế.

### 15.1. Index cho listing phổ biến

Giả sử query phần lớn là:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC"
}).sort({ priceVnd: 1, _id: 1 }).limit(24);
~~~

Một index tham khảo:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    status: 1,
    visibility: 1,
    priceVnd: 1,
    _id: 1
  },
  { name: "catalog_listing_price_asc" }
);
~~~

Các field equality đứng trước trường sort/range theo cấu trúc query này. **_id** là tie-breaker giúp thứ tự ổn định khi nhiều sản phẩm cùng giá.

### 15.2. Query có brand equality

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    status: 1,
    visibility: 1,
    brandId: 1,
    priceVnd: 1,
    _id: 1
  },
  { name: "catalog_brand_price" }
);
~~~

Index có brandId giúp query **brand exact + sort price** trong điều kiện phù hợp. Nhưng nếu query không lọc brand, trường brandId nằm trước price trong index có thể cản index phục vụ global price sort như mong muốn; vì thế không thể thay thế mọi listing index bằng một index có brand ở giữa.

### 15.3. Index cho RAM numeric range

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    status: 1,
    "attributes.ramGB": 1
  },
  { name: "catalog_laptop_ram" }
);
~~~

Nếu RAM là field category-specific ổn định, index này có thể hỗ trợ lọc theo RAM; tuy nhiên query đồng thời **RAM range + price sort** không mặc định dùng một index để tối ưu cả hai việc. Một range có thể khiến sort theo field sau trở nên khó tận dụng. Cần xem execution plan thay vì đoán.

### 15.4. Không tạo mọi tổ hợp index

Nếu có:

~~~text
12 facets
3 sort orders
2 availability modes
5 common query shapes
~~~

việc tạo index cho mọi permutation sẽ làm write amplification, storage và index maintenance rất lớn. Nên bắt đầu bằng một số query patterns có traffic/số document lớn, đo workload thật, rồi điều chỉnh.

### 15.5. Index cho Attribute Pattern

Với mảng **attributes: [{key, valueNum, valueStr}]**:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    "attributes.key": 1,
    "attributes.valueNum": 1
  },
  { name: "attr_numeric_key_value" }
);
~~~

Và tương tự cho String:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    "attributes.key": 1,
    "attributes.valueStr": 1
  },
  { name: "attr_string_key_value" }
);
~~~

Hai paths **attributes.key** và **attributes.valueNum** nằm trong cùng array of documents, nên query dùng **$elemMatch** giúp yêu cầu cả key/value match trong cùng phần tử, đồng thời có thể cho phép index bounds hiệu quả hơn theo đúng cấu trúc.

**Không suy ra** một index như vậy sẽ nhanh cho truy vấn AND của năm attributes khác nhau. MongoDB có giới hạn khi kết hợp nhiều array paths và có thể cần index scan/intersection, fetch/filter hoặc kế hoạch khác. Cần đo executionStats của những query nhiều attributes.

### 15.6. Compound multikey restrictions

Trong MongoDB, một compound multikey index không được phép chứa tùy ý **nhiều array fields độc lập** cho cùng document. Một index trên **colors** và **sizesEU** nếu cả hai là arrays có thể vi phạm giới hạn parallel arrays; ngay cả khi được xây trong dataset hiện tại, writes sau này có thể làm nó trở thành không hợp lệ.

Thiết kế đúng là:

- Dùng **một mảng variants** chứa các cặp thuộc tính cần gắn với nhau.
- Sử dụng **$elemMatch** trên mảng đó.
- Xem các quy tắc compound multikey của phiên bản MongoDB đang dùng.
- Không giả định tách color/size thành hai arrays rồi compound-index sẽ giải quyết quan hệ giữa chúng.

### 15.7. Index cho variants collection

Khi SKU lưu riêng và query bắt đầu từ size/color:

~~~javascript
db.productVariants.createIndex(
  {
    tenantId: 1,
    active: 1,
    color: 1,
    sizeEU: 1,
    productId: 1
  },
  { name: "variant_color_size_product" }
);
~~~

Nếu query thường bắt đầu từ productId để hiển thị tất cả SKU:

~~~javascript
db.productVariants.createIndex(
  {
    tenantId: 1,
    productId: 1
  },
  { name: "variant_by_product" }
);
~~~

Hai query patterns khác nhau có thể cần hai indexes. Cũng cần **unique SKU identity** và quy tắc uniqueness theo seller/tenant phù hợp, không chỉ dựa vào tùy ý một tên SKU string.

## 16. Wildcard index: khi field names thay đổi

Với object attributes động, MongoDB có **wildcard index** để index nhiều subpaths:

~~~javascript
db.products.createIndex(
  { "attributes.$**": 1 },
  { name: "attributes_wildcard" }
);
~~~

Truy vấn có thể là:

~~~javascript
db.products.find({
  "attributes.batteryMAh": { $gte: 4500 }
});
~~~

Wildcard index hữu ích khi chưa biết tất cả attribute names lúc tạo index, nhưng **không phải một index thần kỳ**:

- Không thay thế compound index tối ưu cho filter equality/category/price sort thường dùng.
- Hiệu quả phụ thuộc cấu trúc BSON, kiểu giá trị và loại truy vấn.
- Có các giới hạn đối với sort/covered query và các cách kết hợp predicate.
- Với array/nested structures, cần xem quy tắc wildcard/multikey cụ thể.
- Index có thể rất lớn khi hàng nghìn keys/values cùng được index.

### 16.1. Khi nào cân nhắc wildcard?

Phù hợp khi:

- Catalog có nhiều attributes mới khó đoán.
- Query trên một số paths động có tần suất vừa phải.
- Không hợp lý tạo index riêng cho mọi path.
- Đã kiểm nghiệm workload và storage overhead.

Không phù hợp để mặc định tối ưu:

~~~text
category + brand + RAM + SSD + price sort
~~~

trong mọi điều kiện. Với top facets có traffic cao, index đặc thù thường dễ điều khiển hơn.

### 16.2. Quy trình lựa chọn index

1. Liệt kê top query shapes theo traffic và chi phí.
2. Chọn index cụ thể cho các fields ổn định.
3. Đánh giá wildcard cho rare attributes nếu có nhu cầu.
4. Kiểm tra index size và write amplification.
5. Dùng explain("executionStats") so sánh keys/docs examined và thời gian.
6. Quan sát behavior khi dataset/index/data skew thay đổi.

## 17. Index partial và dữ liệu hiển thị

Một catalog có nhiều sản phẩm ARCHIVED/PRIVATE nhưng listing chỉ tìm ACTIVE/PUBLIC. Có thể cân nhắc partial index:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    priceVnd: 1,
    _id: 1
  },
  {
    name: "public_active_price",
    partialFilterExpression: {
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  }
);
~~~

Điều kiện query phải tương thích với **partialFilterExpression** để planner sử dụng index một cách đúng đắn. Query dành cho admin xem ARCHIVED/PRIVATE không thể mặc nhiên dùng partial index này.

### 17.1. Partial index không phải phân quyền

Nếu một ứng dụng quên filter visibility hoặc tenantId, **partial index không chặn** nó đọc dữ liệu riêng tư; index là công cụ hiệu năng và ràng buộc nhất định, không thay authorization.

### 17.2. TTL không phải trạng thái ngừng bán

Không dùng TTL để tự xóa sản phẩm chỉ vì nó hết hàng hoặc tạm ngừng bán. TTL thực sự xóa documents khi tới thời điểm đủ điều kiện theo TTL index. Catalog thường cần giữ product history, orders reference và audit; hãy dùng status/visibility và retention policy phù hợp.

## 18. Đọc execution plan để biết index có hữu ích không

Ví dụ:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC",
  brandId: "acer",
  "attributes.ramGB": { $gte: 16 },
  priceVnd: { $lte: NumberLong("30000000") }
}).sort({ priceVnd: 1, _id: 1 })
  .explain("executionStats");
~~~

Hãy quan sát:

| Dấu hiệu | Ý nghĩa |
|---|---|
| **winningPlan** | Kế hoạch được chọn |
| **IXSCAN** | Có sử dụng index scan |
| **COLLSCAN** | Quét collection |
| **FETCH** | Cần tải document để kiểm tra/trả field |
| **SORT** | Có thể có bước sort không được index phục vụ |
| **totalKeysExamined** | Số index entries đã xét |
| **totalDocsExamined** | Số documents đã đọc/kiểm tra |
| **nReturned** | Số documents trả về |
| **executionTimeMillis** | Thống kê thời gian thực thi tham khảo |

**Một IXSCAN không tự động đồng nghĩa query nhanh.** Nếu scan hàng triệu keys nhưng trả 24 products, cần xem selectivity/index order. Ngược lại, với tám records test, COLLSCAN có thể nhanh hơn IXSCAN và không chứng minh index production vô dụng.

### 18.1. Chọn dữ liệu benchmark đại diện

Trong production có thể:

- 70% sản phẩm ở 3 brands phổ biến.
- 90% products ACTIVE.
- Một category có 80% toàn bộ records.
- Một facet như color=black cực phổ biến.

Index được chọn tốt cho brand hiếm không nhất thiết tối ưu cho brand rất phổ biến. Benchmark cần đại diện distribution thực tế, đồng thời đo p50/p95/p99 latency, CPU/IO, query execution và index maintenance.

## 19. Faceted search: bộ lọc động có số lượng

Một trang catalog thường hiển thị:

~~~text
Danh mục: Laptop
Thương hiệu
  [ ] Acer (2)
  [ ] Dell (1)
  [ ] Lenovo (1)

RAM
  [ ] 8 GB (1)
  [ ] 16 GB (2)
  [ ] 32 GB (1)

Khoảng giá
  [ ] Dưới 20 triệu
  [ ] 20–30 triệu
  [ ] Trên 30 triệu
~~~

**Facet count** là số lượng sản phẩm trong một tập xác định, không phải số tổng số documents của toàn collection trong mọi trường hợp.

### 19.1. Facets cơ bản cho category

Đếm theo thương hiệu, chỉ sản phẩm thuộc SHOP-A, laptops và đang hiển thị:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  },
  {
    $group: {
      _id: "$brandId",
      productCount: { $sum: 1 }
    }
  },
  { $sort: { productCount: -1, _id: 1 } }
]);
~~~

Với data mẫu:

| Brand | Số sản phẩm |
|---|---:|
| acer | 2 |
| dell | 1 |
| lenovo | 1 |

Nếu quên **tenantId**, Acer tăng từ 2 thành 3 do sản phẩm của SHOP-B. Nếu đếm cả status DRAFT/ARCHIVED, số counts cũng có thể sai nghiệp vụ.

### 19.2. Facet cho numeric attribute

Đếm các giá trị RAM trong category laptop:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC",
      "attributes.ramGB": { $type: "number" }
    }
  },
  {
    $group: {
      _id: "$attributes.ramGB",
      productCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả:

~~~javascript
[
  { _id: 8, productCount: 1 },
  { _id: 16, productCount: 2 },
  { _id: 32, productCount: 1 }
]
~~~

### 19.3. Facet range bằng $bucket

Chia giá thành các ngưỡng xác định:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  },
  {
    $bucket: {
      groupBy: "$priceVnd",
      boundaries: [
        NumberLong("0"),
        NumberLong("20000000"),
        NumberLong("30000000"),
        NumberLong("50000000")
      ],
      default: "OTHER",
      output: {
        productCount: { $sum: 1 }
      }
    }
  }
]);
~~~

MongoDB **$bucket** dùng lower bound inclusive và upper bound exclusive theo các ranh giới; với các giá trị trong mẫu:

| Giá | Sản phẩm | Count |
|---|---|---:|
| [0, 20 triệu) | L-102 | 1 |
| [20, 30 triệu) | L-101 | 1 |
| [30, 50 triệu) | L-103, L-104 | 2 |

Nếu UI ghi “dưới hoặc bằng 20 triệu” nhưng $bucket dùng [0,20 triệu), hợp đồng bị lệch ở ranh giới. Cần thiết kế nhãn và query đúng inclusivity.

### 19.4. Đếm một sản phẩm hay một biến thể?

Một document sản phẩm có thể có nhiều variants cùng color hoặc size. Nếu unwind variants rồi group theo color, mỗi variant có thể làm tăng count; nếu UI muốn **số sản phẩm**, phải deduplicate **product ID + facet value** trước khi count.

Ví dụ với embedded variants:

~~~javascript
db.products.aggregate([
  { $match: { tenantId: "SHOP-A", categoryId: "shoes" } },
  { $unwind: "$variants" },
  { $match: { "variants.availableQty": { $gt: 0 } } },
  {
    $group: {
      _id: {
        productId: "$_id",
        color: "$variants.color"
      }
    }
  },
  {
    $group: {
      _id: "$_id.color",
      productCount: { $sum: 1 }
    }
  }
]);
~~~

Stage group thứ nhất loại trùng các variants **cùng sản phẩm cùng màu**, stage thứ hai đếm số sản phẩm theo màu.

## 20. Facet counts sau khi người dùng chọn filter

Giả sử người dùng chọn:

~~~text
brand = acer
ramGB >= 16
~~~

Trong sample, kết quả hiện tại là **L-101** và **L-104**, total=2.

Có hai mô hình counts:

1. **Conjunctive counts:** tính trên tập đã áp dụng mọi filter, nên brand khác không hiện nếu đã chọn Acer.
2. **Self-excluding / disjunctive counts:** khi tính facet Brand, bỏ filter Brand nhưng giữ RAM; khi tính facet RAM, bỏ RAM nhưng giữ Brand. UI sẽ thấy những lựa chọn thay thế còn khả dụng.

Không có một semantics đúng cho mọi sản phẩm; cần chọn một chính sách nhất quán.

### 20.1. Conjunctive counts

Nếu áp dụng tất cả điều kiện:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC",
      brandId: "acer",
      "attributes.ramGB": { $gte: 16 }
    }
  },
  { $group: { _id: "$brandId", count: { $sum: 1 } } }
]);
~~~

chỉ có **acer: 2**. Các lựa chọn Dell/Lenovo sẽ không có count vì đã lọc brand.

### 20.2. Self-excluding counts

Khi tính Brand, **bỏ điều kiện Brand** nhưng giữ RAM≥16:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC",
      "attributes.ramGB": { $gte: 16 }
    }
  },
  { $group: { _id: "$brandId", count: { $sum: 1 } } },
  { $sort: { count: -1, _id: 1 } }
]);
~~~

Kết quả:

~~~javascript
[
  { _id: "acer", count: 2 },
  { _id: "dell", count: 1 }
]
~~~

Lenovo RAM 8 nên không xuất hiện. Người dùng vẫn thấy Dell là một lựa chọn còn phù hợp nếu bỏ/chuyển brand filter.

Ngược lại, khi tính RAM, giữ brand=acer nhưng **bỏ điều kiện RAM**:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC",
      brandId: "acer"
    }
  },
  {
    $group: {
      _id: "$attributes.ramGB",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả **RAM 16: 1, RAM 32: 1**.

### 20.3. Nhiều giá trị cùng facet

Nếu user chọn **brand=acer,dell**, semantics OR trong Brand nên cho phép:

~~~javascript
brandId: { $in: ["acer", "dell"] }
~~~

Khi tính Brand facet theo kiểu self-excluding, bỏ **toàn bộ điều kiện Brand** chứ không chỉ một giá trị. Những UX khác (ví dụ drill-down facets) có thể chọn chính sách khác; backend và UI phải thống nhất.

### 20.4. Facets không nên luôn hiện đầy đủ mọi giá trị

Với thuộc tính modelNumber có 100.000 giá trị, việc trả hết làm JSON rất lớn. Nên:

- Chỉ hiện top N facet values theo count.
- Có tính năng search trong facet values nếu cần.
- Dùng metadata allowedValues cho bộ lọc hữu hạn.
- Tránh group toàn bộ String values một cách không giới hạn.
- Quy định hành vi cho facet values đã chọn nhưng hiện count=0.

## 21. $facet: gom nhiều kết quả vào một aggregation

**$facet** cho phép nhiều nhánh aggregation từ cùng một tập dữ liệu đầu vào. Một pipeline có thể trả **items**, **total count**, **brand counts** và **RAM counts** trong một document.

### 21.1. Ví dụ self-excluding với hai facets

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  },
  {
    $facet: {
      items: [
        {
          $match: {
            brandId: "acer",
            "attributes.ramGB": { $gte: 16 }
          }
        },
        { $sort: { priceVnd: 1, _id: 1 } },
        { $limit: 24 },
        {
          $project: {
            title: 1,
            brandId: 1,
            priceVnd: 1
          }
        }
      ],
      total: [
        {
          $match: {
            brandId: "acer",
            "attributes.ramGB": { $gte: 16 }
          }
        },
        { $count: "value" }
      ],
      brands: [
        { $match: { "attributes.ramGB": { $gte: 16 } } },
        { $group: { _id: "$brandId", count: { $sum: 1 } } },
        { $sort: { count: -1, _id: 1 } }
      ],
      ramValues: [
        { $match: { brandId: "acer" } },
        {
          $group: {
            _id: "$attributes.ramGB",
            count: { $sum: 1 }
          }
        },
        { $sort: { _id: 1 } }
      ]
    }
  }
]);
~~~

Kết quả có cấu trúc:

~~~javascript
{
  items: [ /* L-101, L-104 */ ],
  total: [ { value: 2 } ],
  brands: [
    { _id: "acer", count: 2 },
    { _id: "dell", count: 1 }
  ],
  ramValues: [
    { _id: 16, count: 1 },
    { _id: 32, count: 1 }
  ]
}
~~~

Lưu ý **total là array**, có thể rỗng nếu $count không nhận đầu vào. API mapper nên trả total=0 theo hợp đồng nếu array rỗng, không truy cập phần tử [0] một cách vô điều kiện.

### 21.2. Vì sao $match chung trước $facet?

**tenantId, status, visibility và category** áp dụng cho **mọi nhánh**, nên $match chung ở đầu:

- Đảm bảo scope chính xác.
- Có cơ hội tận dụng index ở đầu pipeline.
- Giảm số documents đi vào các facet branches.

Nếu $facet là stage đầu pipeline, nó thường không thể tận dụng index để giảm tập đầu vào như một $match có thể dùng trước đó.

### 21.3. $facet không phải miễn phí

- Mỗi branch xử lý một tập document đầu vào.
- Một kết quả facet top-level chứa nhiều arrays, có giới hạn BSON document size.
- Stage $facet có giới hạn bộ nhớ riêng; **allowDiskUse** không khắc phục mọi giới hạn đó.
- Sort/group trong nhiều branches có thể tốn CPU/memory.
- Một pipeline với 40 facet branches không tự nhanh hơn 40 queries đơn lẻ.

Đối với catalog rất lớn, có thể tách thành **items query**, **facet queries** và **materialized facet counts** với caching/refresh policy rõ.

## 22. Dynamic facets khi không biết trước key

Với attributes object, MongoDB có thể chuyển object thành mảng bằng **$objectToArray** để group theo tên key:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  },
  { $project: { entries: { $objectToArray: "$attributes" } } },
  { $unwind: "$entries" },
  {
    $group: {
      _id: {
        key: "$entries.k",
        value: "$entries.v"
      },
      productCount: { $sum: 1 }
    }
  },
  { $sort: { "_id.key": 1, productCount: -1 } }
]);
~~~

Ví dụ output:

~~~javascript
{ _id: { key: "ramGB", value: 16 }, productCount: 2 }
{ _id: { key: "ramGB", value: 8 }, productCount: 1 }
{ _id: { key: "color", value: "black" }, productCount: 2 }
~~~

### 22.1. Không cho mọi field thành facet

Attribute object có thể chứa serialNumber, manufacturingBatch hoặc internalNotes. Không tự động lộ mọi key/value sau $objectToArray. Chỉ giữ các keys được registry đánh dấu **filterable=true, visible=true** và có quyền hiển thị. Không chỉ trông chờ frontend ẩn một facet chứa dữ liệu nhạy cảm.

### 22.2. Array và nested values cần xử lý riêng

Nếu:

~~~javascript
{ ports: ["USB-C", "HDMI"] }
~~~

$objectToArray tạo một entry có **value là cả array**; nó không tự tạo hai port facets. Cần unwind/normalize theo giá trị. Nếu một product lặp cùng port, deduplicate **product+facet value** trước khi count.

Nested object:

~~~javascript
{ dimensions: { widthMm: 300, heightMm: 25 } }
~~~

không nên được group như một giá trị facet duy nhất. Nên đăng ký explicit paths như dimensions.widthMm nếu thực sự cần filter.

### 22.3. Attribute Pattern tạo facets bằng $unwind

Với array of key–value:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  },
  { $unwind: "$attributes" },
  { $match: { "attributes.key": { $in: ["color", "ramGB"] } } },
  {
    $group: {
      _id: {
        key: "$attributes.key",
        stringValue: "$attributes.valueStr",
        numberValue: "$attributes.valueNum"
      },
      count: { $sum: 1 }
    }
  }
]);
~~~

Đây là mẫu minh họa. Với dữ liệu typed khác nhau, nên tách numeric/string branches hoặc tạo representation group key chuẩn; các fields missing có thể tạo nhóm null. Cần validate không lặp key vô ý.

### 22.4. Tổng facet counts có thể vượt total products

Nếu một product có hai màu, nó có thể đóng góp 1 vào black và 1 vào white. Tổng counts của mọi màu lớn hơn total products không nhất thiết sai. Nhưng một product không được tính hai lần vào **cùng một giá trị màu** nếu UI đếm số sản phẩm.

## 23. Pagination và sort ổn định

### 23.1. Offset pagination

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC"
}).sort({ priceVnd: 1, _id: 1 })
  .skip(24)
  .limit(24);
~~~

Ưu điểm: đơn giản. Hạn chế: skip lớn tốn công bỏ qua rows; thay đổi dữ liệu giữa pages có thể làm trùng/bỏ sót.

### 23.2. Thêm _id làm tie-breaker

Sort chỉ theo giá:

~~~javascript
{ priceVnd: 1 }
~~~

không đảm bảo thứ tự xác định giữa sản phẩm cùng giá. Dùng:

~~~javascript
{ priceVnd: 1, _id: 1 }
~~~

để có thứ tự xác định trên trạng thái dữ liệu được quan sát.

### 23.3. Keyset pagination

Với sort tăng dần **(priceVnd, _id)** và cursor của item cuối:

~~~javascript
{ lastPriceVnd: NumberLong("22000000"), lastId: "L-101" }
~~~

trang kế tiếp:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC",
  $or: [
    { priceVnd: { $gt: NumberLong("22000000") } },
    {
      priceVnd: NumberLong("22000000"),
      _id: { $gt: "L-101" }
    }
  ]
}).sort({ priceVnd: 1, _id: 1 })
  .limit(24);
~~~

Backend cần ràng buộc cursor với tenant/filter/sort để tránh client thao túng scope. Cursor có thể được ký hoặc encode kèm filter hash và version.

### 23.4. Keyset không tạo snapshot bất biến

Nếu giá đổi giữa hai pages, sản phẩm có thể di chuyển vị trí. Keyset không tự đảm bảo snapshot isolation cho cả phiên duyệt; yêu cầu mạnh hơn cần thiết kế snapshot/search versioning.

### 23.5. Total và facet counts phải xét cả tập kết quả

**Counts thường tính trên toàn bộ tập match**, không chỉ trang 24 sản phẩm. Nếu tính facet sau $skip/$limit, UI chỉ thấy counts của một trang.

~~~text
authenticated scope + filters
              |
         +----+----+
         |         |
         v         v
     items page  facet counts
     sort/limit  trên toàn tập match
~~~

Exact total count có thể đắt. Nếu UI chấp nhận **hasMore** hoặc cached/estimated count, phải ghi rõ semantics thay vì hiển thị một số không được xác minh như exact.

## 24. Projection và kích thước payload

Listing nên trả fields cần thiết như _id/title/brand/price/thumbnail, không trả toàn bộ:

~~~text
longDescription
technicalSpecs
allImages
supplierInternalCost
allVariants
moderationHistory
~~~

~~~javascript
db.products.find(
  {
    tenantId: "SHOP-A",
    categoryId: "laptops",
    status: "ACTIVE",
    visibility: "PUBLIC"
  },
  {
    title: 1,
    brandId: 1,
    priceVnd: 1,
    thumbnailUrl: 1
  }
).sort({ priceVnd: 1, _id: 1 }).limit(24);
~~~

Projection giảm payload và có thể giảm I/O; nó không thay authorization. Backend không được trả supplierCost hoặc metadata riêng tư vì chúng cùng nằm trong document.

### 24.1. Denormalization cho listing

Brand label/thumbnailUrl có thể copy vào search document để tránh join, nhưng tạo trách nhiệm đồng bộ khi brand đổi tên, ảnh đổi hoặc locale thay đổi. Chỉ denormalize fields có lợi ích rõ và có quy trình cập nhật, không sao chép mọi dữ liệu liên quan.

## 25. Java MongoDB Sync Driver: tạo bộ lọc an toàn

Một service Java thường nhận filter options sau khi controller đã parse/validate. Không để repository nhận nguyên một JSON query hoặc field path chưa được kiểm tra.

### 25.1. Filter specification

~~~java
import java.util.List;

public record CatalogFilter(
        String categoryId,
        List<String> brandIds,
        Integer minRamGB,
        Long maxPriceVnd,
        int limit
) {
}
~~~

**tenantId không nằm trong CatalogFilter** vì scope này nên do service xác định từ identity đã xác thực, tránh cho request tự giả mạo tenant.

### 25.2. Repository dùng Filters/Sorts/Projections

~~~java
import java.util.ArrayList;
import java.util.List;

import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

public final class ProductSearchRepository {
    private final MongoCollection<Document> products;

    public ProductSearchRepository(
            MongoCollection<Document> products) {
        this.products = products;
    }

    public List<Document> findProducts(
            String trustedTenantId,
            CatalogFilter requested) {

        if (trustedTenantId == null || trustedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Authenticated tenant is required");
        }
        if (requested.categoryId() == null ||
                requested.categoryId().isBlank()) {
            throw new IllegalArgumentException("Category is required");
        }
        if (requested.limit() < 1 || requested.limit() > 48) {
            throw new IllegalArgumentException(
                    "Page size must be 1..48");
        }
        if (requested.maxPriceVnd() != null &&
                requested.maxPriceVnd() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        if (requested.minRamGB() != null &&
                (requested.minRamGB() < 1 ||
                 requested.minRamGB() > 256)) {
            throw new IllegalArgumentException("Invalid RAM filter");
        }

        List<Bson> clauses = new ArrayList<>();
        clauses.add(Filters.eq("tenantId", trustedTenantId));
        clauses.add(Filters.eq("categoryId", requested.categoryId()));
        clauses.add(Filters.eq("status", "ACTIVE"));
        clauses.add(Filters.eq("visibility", "PUBLIC"));

        if (requested.brandIds() != null &&
                !requested.brandIds().isEmpty()) {
            if (requested.brandIds().size() > 20) {
                throw new IllegalArgumentException("Too many brands");
            }
            clauses.add(Filters.in("brandId", requested.brandIds()));
        }
        if (requested.minRamGB() != null) {
            clauses.add(Filters.gte(
                    "attributes.ramGB", requested.minRamGB()));
        }
        if (requested.maxPriceVnd() != null) {
            clauses.add(Filters.lte(
                    "priceVnd", requested.maxPriceVnd()));
        }

        FindIterable<Document> query = products.find(
                Filters.and(clauses))
                .sort(Sorts.orderBy(
                        Sorts.ascending("priceVnd"),
                        Sorts.ascending("_id")))
                .projection(Projections.include(
                        "title", "brandId",
                        "priceVnd", "thumbnailUrl"))
                .limit(requested.limit());

        return query.into(new ArrayList<>());
    }
}
~~~

Đây là ví dụ cho **schema object attributes** và danh sách trả có giới hạn; một production API vẫn cần:

- Validate category cho phép lọc RAM (không cho áp RAM vào shoes).
- Map brand aliases sang brandIds chuẩn.
- Hỗ trợ min/max price cùng nhau.
- Xử lý sort allowlist và pagination cursor.
- Áp dụng timeout, logging/metrics an toàn.
- Giới hạn complexity và bảo vệ response DTO.

**Không tạo MongoClient trong mỗi lần findProducts()**. Inject MongoCollection từ MongoClient dùng chung theo vòng đời application.

### 25.3. Query Attribute Pattern bằng Filters.elemMatch

~~~java
import com.mongodb.client.model.Filters;
import org.bson.conversions.Bson;

Bson ramFilter = Filters.elemMatch(
        "attributes",
        Filters.and(
                Filters.eq("key", "ramGB"),
                Filters.gte("valueNum", 16)
        )
);

Bson storageFilter = Filters.elemMatch(
        "attributes",
        Filters.and(
                Filters.eq("key", "storageGB"),
                Filters.gte("valueNum", 512)
        )
);

Bson combined = Filters.and(
        Filters.eq("tenantId", "SHOP-A"),
        Filters.eq("categoryId", "laptops"),
        ramFilter,
        storageFilter
);
~~~

Hai **elemMatch** độc lập trên cùng mảng là cách biểu diễn **cần một entry ramGB thỏa** và **cần một entry storageGB thỏa**. Các operators đều được backend dựng từ registry; không chấp nhận key hoặc numeric type tùy ý.

### 25.4. Query variant trong cùng phần tử

~~~java
Bson inStockBlack41 = Filters.elemMatch(
        "variants",
        Filters.and(
                Filters.eq("color", "black"),
                Filters.eq("sizeEU", 41),
                Filters.gt("availableQty", 0)
        )
);
~~~

Đây là phép kiểm tra **có ít nhất một variant thỏa**; không có nghĩa mọi variants của product đều available.

### 25.5. Dynamic path chỉ sau allowlist

Ví dụ registry đã xác nhận một key:

~~~java
import java.util.Set;

Set<String> allowedNumericFilters =
        Set.of("ramGB", "storageGB", "screenInch");

String attributeKey = requestedAttributeKey;
if (!allowedNumericFilters.contains(attributeKey)) {
    throw new IllegalArgumentException(
            "Unsupported numeric filter");
}

Bson minFilter = Filters.gte(
        "attributes." + attributeKey, numericMinValue);
~~~

Mẫu này chỉ hợp lệ khi **requestedAttributeKey** được validate theo category và value number được parse chuẩn trước đó. Không chỉ kiểm tra chuỗi bắt đầu bằng "attributes." là đủ để chặn những field paths không mong muốn.

## 26. Java Driver: aggregation facet cơ bản

Java Sync Driver có builders cho aggregation stages. Ví dụ đếm theo brand:

~~~java
import java.util.ArrayList;
import java.util.List;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

public List<Document> countByBrand(
        MongoCollection<Document> products,
        String trustedTenantId) {

    List<Bson> pipeline = List.of(
            Aggregates.match(Filters.and(
                    Filters.eq("tenantId", trustedTenantId),
                    Filters.eq("categoryId", "laptops"),
                    Filters.eq("status", "ACTIVE"),
                    Filters.eq("visibility", "PUBLIC")
            )),
            Aggregates.group(
                    "$brandId",
                    Accumulators.sum("productCount", 1)
            ),
            Aggregates.sort(
                    Sorts.orderBy(
                            Sorts.descending("productCount"),
                            Sorts.ascending("_id")
                    ))
    );

    return products.aggregate(pipeline)
            .into(new ArrayList<>());
}
~~~

Đoạn code minh họa một method trong class service/repository. Result Document có **_id** là brandId và **productCount** là numeric type phù hợp. Trong API thực, map sang **BrandFacetDto** với tên field nhất quán, không trả raw BSON response cho bên ngoài.

### 26.1. Result count có thể rỗng

Nếu category không có sản phẩm, aggregation group trả list rỗng. Service cần trả:

~~~javascript
{ facets: [], total: 0 }
~~~

theo hợp đồng. Không mặc định mọi facet có item.

### 26.2. Cẩn thận khi materialize danh sách dài

**into(new ArrayList<>())** phù hợp với số nhóm facet đã giới hạn; không nên dùng để đọc hàng triệu sản phẩm vào RAM. Với datasets lớn, dùng cursor/batching và đảm bảo đóng resource theo vòng đời thích hợp.

## 27. Spring Data MongoDB: entity polymorphic

Với Spring Boot, có thể dùng **MongoTemplate** và một entity chứa core fields cùng attributes map.

~~~java
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("products")
public class ProductDocument {
    @Id
    private String id;

    private String tenantId;
    private String categoryId;
    private String brandId;
    private String title;
    private String status;
    private String visibility;
    private long priceVnd;
    private Map<String, Object> attributes;

    public ProductDocument() {
    }

    // Getters/setters hoặc constructor binding của dự án.
}
~~~

### 27.1. Vì sao dùng Map<String,Object> không giải quyết mọi thứ?

Map cho phép thuộc tính biến đổi, nhưng:

- Numeric có thể được convert thành Integer/Long/Double tùy BSON type.
- Giá trị null/missing khác nhau.
- Java compiler không biết ramGB luôn là số.
- Khi lấy attributes.get("ramGB"), phải validate type trước khi cast.
- Không đảm bảo category chỉ có keys hợp lệ.

Đối với nghiệp vụ phức tạp, có thể sử dụng **typed value objects**, các classes theo category hoặc custom converters. Map ở đây là minh họa cấu trúc linh hoạt, không phải lựa chọn bắt buộc cho mọi dự án.

### 27.2. Query bằng MongoTemplate

~~~java
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class ProductCatalogService {
    private final MongoTemplate mongoTemplate;

    public ProductCatalogService(
            MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<ProductDocument> searchLaptops(
            String trustedTenantId,
            int minRamGB,
            long maxPriceVnd) {

        if (minRamGB < 1 || maxPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid filter");
        }

        Query query = new Query(
                Criteria.where("tenantId").is(trustedTenantId)
                        .and("categoryId").is("laptops")
                        .and("status").is("ACTIVE")
                        .and("visibility").is("PUBLIC")
                        .and("attributes.ramGB").gte(minRamGB)
                        .and("priceVnd").lte(maxPriceVnd)
        );

        query.with(Sort.by(
                Sort.Order.asc("priceVnd"),
                Sort.Order.asc("_id")
        ));
        query.limit(24);

        return mongoTemplate.find(
                query, ProductDocument.class);
    }
}
~~~

Với **ProductDocument** ở trên, tên Java properties trùng BSON names. Nếu dùng **@Field("price_vnd")** hoặc các mappings khác, cần dùng đúng Spring Data mapping context; không sao chép untyped BSON query và kỳ vọng tên field được map giống nhau ở mọi overload.

### 27.3. Projection ra DTO thay vì entity đầy đủ

Ví dụ muốn tránh tải attributes lớn:

~~~java
Query query = new Query(
        Criteria.where("tenantId").is(trustedTenantId)
                .and("categoryId").is("laptops")
);

query.fields()
        .include("_id")
        .include("title")
        .include("brandId")
        .include("priceVnd");
~~~

Đây là **field projection**. Nếu map vào **ProductDocument** đầy đủ, những fields không được trả sẽ rỗng/default. API nên dùng **listing DTO** hoặc mapping riêng thay vì coi entity thiếu fields là entity hoàn chỉnh có thể save lại.

### 27.4. Query mảng variants bằng Criteria.elemMatch

~~~java
Criteria variantCriteria = Criteria.where("variants")
        .elemMatch(
                Criteria.where("color").is("black")
                        .and("sizeEU").is(41)
                        .and("availableQty").gt(0)
        );

Query query = new Query(
        new Criteria().andOperator(
                Criteria.where("tenantId").is(trustedTenantId),
                Criteria.where("categoryId").is("shoes"),
                variantCriteria
        )
);
~~~

**Criteria.elemMatch** diễn đạt đúng điều kiện cùng array element, không chỉ độc lập có color/size/stock ở những phần tử khác nhau.

### 27.5. Hai thuộc tính khác nhau trong Attribute Pattern

~~~java
Criteria hasRam = Criteria.where("attributes")
        .elemMatch(
                Criteria.where("key").is("ramGB")
                        .and("valueNum").gte(16)
        );

Criteria hasStorage = Criteria.where("attributes")
        .elemMatch(
                Criteria.where("key").is("storageGB")
                        .and("valueNum").gte(512)
        );

Query query = new Query(
        new Criteria().andOperator(
                Criteria.where("tenantId").is(trustedTenantId),
                Criteria.where("categoryId").is("laptops"),
                hasRam,
                hasStorage
        )
);
~~~

Lưu ý: đây là **phương án schema khác** với ProductDocument Map của mục 27. Để dùng dạng Attribute Pattern trong một entity thật, khai báo **List<AttributeValue>** hoặc sử dụng MongoTemplate với collection name/Document đúng model.

## 28. Spring Data Aggregation và facet DTO

Spring Data hỗ trợ Aggregation API để tạo facet counts; ví dụ đếm brands cho một category:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

Aggregation aggregation = newAggregation(
        match(Criteria.where("tenantId").is(trustedTenantId)
                .and("categoryId").is("laptops")
                .and("status").is("ACTIVE")
                .and("visibility").is("PUBLIC")),
        group("brandId").count().as("productCount"),
        project("productCount")
                .and("_id").as("brandId")
                .andExclude("_id")
);

AggregationResults<BrandFacet> results =
        mongoTemplate.aggregate(
                aggregation, "products", BrandFacet.class);

List<BrandFacet> brands = results.getMappedResults();
~~~

DTO:

~~~java
public record BrandFacet(String brandId, long productCount) {
}
~~~

MongoDB **$group** tạo khóa **_id**; ở đây **$project** biến _id thành brandId để khớp record. Nếu bỏ project và map vào record có brandId, field có thể null/thiếu do output shape không đúng.

### 28.1. Tạo nhiều facet branches

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("tenantId").is(trustedTenantId)
                .and("categoryId").is("laptops")
                .and("status").is("ACTIVE")
                .and("visibility").is("PUBLIC")),
        facet(
                group("brandId").count().as("count"),
                project("count")
                        .and("_id").as("brandId")
                        .andExclude("_id")
        ).as("brands")
         .and(
                group("attributes.ramGB").count().as("count"),
                project("count")
                        .and("_id").as("ramGB")
                        .andExclude("_id")
        ).as("ramValues")
);

AggregationResults<org.bson.Document> raw =
        mongoTemplate.aggregate(
                agg, "products", org.bson.Document.class);
~~~

Output top-level là **một document chứa hai arrays**. Nếu muốn map typed DTO:

~~~java
import java.util.List;

public record CatalogFacetResponse(
        List<BrandCount> brands,
        List<RamCount> ramValues
) {}

public record BrandCount(String brandId, long count) {}
public record RamCount(Integer ramGB, long count) {}
~~~

Trong Java thực tế, mỗi public top-level record phải ở file riêng. Nếu output không có group nào, các nhánh có thể trả arrays rỗng; cần quyết định defaults trong API response.

### 28.2. Self-excluding facets trong Spring Data

Các branches ở mục 21 áp dụng **các bộ lọc khác nhau**. Với Spring Data, hãy xây từng **AggregationOperation[]** có match conditions chính xác cho:

- Items: brand + RAM + những filters khác.
- Brands: RAM + các filters khác, **không có brand**.
- RAM: brand + các filters khác, **không có RAM**.

Đừng xây một **$match brand+RAM trước $facet** rồi hy vọng brand branch có thể bỏ lại điều kiện brand; dữ liệu đã bị loại ở stage trước thì branch không thể khôi phục.

### 28.3. Khi nào @Aggregation trên repository phù hợp?

Một pipeline cố định, ngắn, có output DTO rõ có thể dùng **@Aggregation** của Spring Data repository. Với search filters động, mỗi facet branch có logic loại trừ riêng, MongoTemplate hoặc Java Driver Aggregation builders thường dễ kiểm soát hơn so với nối chuỗi JSON annotations.

Không nhận raw pipeline JSON của user để gọi trực tiếp bằng quyền backend.

## 29. Validation: schema linh hoạt vẫn cần ràng buộc

Một catalog đa ngành có thể không yêu cầu tất cả products có **attributes.ramGB**, nhưng thường cần mọi product có các fields chung hợp lệ.

### 29.1. Validator cho core fields

Ví dụ **$jsonSchema** minh họa:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId", "categoryId", "title",
      "status", "visibility", "priceVnd"
    ],
    properties: {
      tenantId: { bsonType: "string" },
      categoryId: { bsonType: "string" },
      title: { bsonType: "string" },
      status: {
        enum: ["DRAFT", "ACTIVE", "ARCHIVED"]
      },
      visibility: {
        enum: ["PUBLIC", "PRIVATE"]
      },
      priceVnd: {
        bsonType: "long",
        minimum: 0
      },
      attributes: { bsonType: "object" }
    }
  }
}
~~~

Đây là **validator fragment**, không phải lệnh đã chạy. Trên collection có validator hiện tại, **collMod** phải kết hợp ràng buộc cũ; thay toàn bộ biểu thức có thể vô tình nới lỏng bảo vệ.

### 29.2. Quy tắc theo category

Laptop có thể cần:

~~~text
ramGB: positive number
storageGB: positive number
screenInch: positive number
~~~

Shoes có:

~~~text
material: enum
gender: enum
~~~

Không coi lưu chung collection là lý do bỏ validation. Có thể dùng app-level registry validation, schema validation với conditions, import-time checks và versioned definitions khi cần. Validator không tự giải quyết mọi business invariant; app validation không bảo vệ tất cả admin/ETL writers nếu họ ghi trực tiếp.

### 29.3. Cập nhật một thuộc tính

~~~javascript
db.products.updateOne(
  {
    _id: "L-101",
    tenantId: "SHOP-A",
    status: { $ne: "ARCHIVED" }
  },
  {
    $set: {
      "attributes.ramGB": 32,
      updatedAt: new Date()
    }
  }
);
~~~

Đây là atomic update của **một document**. Nếu thay RAM làm SKU/giá/search projection ở collection khác phải đổi, cần workflow đồng bộ; update một field không làm mọi bản sao tự cập nhật.

### 29.4. Không cho seller gửi arbitrary BSON path

API nhập thuộc tính phải map input về **canonical key** từ registry rồi mới tạo path. Không dùng key tùy ý làm dotted path, nhất là key chứa dấu chấm, dollar prefix hoặc mâu thuẫn với reserved fields.

### 29.5. Idempotent import

Feed nhà bán hàng có thể nhập cùng sản phẩm nhiều lần:

~~~javascript
{
  tenantId: "SHOP-A",
  source: "supplier-7",
  sourceProductId: "P-9001"
}
~~~

Nên dùng stable source identity, conditional upsert và unique index phù hợp; không insert document mới ở mọi lần feed. Khi feeds cập nhật đồng thời, cần sourceVersion/sequence hoặc optimistic revision để nguồn cũ không overwrite thông tin mới.

## 30. Tiến hóa attributes và schema migration

Catalog có thể đổi **storage** thành **storageGB**, hoặc thay **"16 GB"** (String) thành 16 (Number). Đây là thay đổi dữ liệu, không chỉ đổi label.

### 30.1. Không đổi field chỉ trong một release

Old document:

~~~javascript
{ "attributes.storage": "512 GB" }
~~~

New filter:

~~~javascript
{ "attributes.storageGB": 512 }
~~~

Documents cũ sẽ biến khỏi kết quả nếu chưa migrate. Nên triển khai:

~~~text
Expand readers: accept old/new
 -> Update writers: canonical new field
 -> Backfill: parse/convert old data
 -> Reconcile: verify types/counts
 -> Switch filters and indexes
 -> Contract: remove old field and index
~~~

### 30.2. $rename không đủ khi đổi kiểu/đơn vị

~~~javascript
db.products.updateMany(
  {},
  {
    $rename: {
      "attributes.storage": "attributes.storageGB"
    }
  }
);
~~~

Lệnh này chỉ đổi field name; **"512 GB"** vẫn là String. Cần parsing/mapping kiểu, validation và kế hoạch xử lý invalid data. Ngoài ra, $rename có thể overwrite target đã tồn tại, nên không chạy tràn lan trên mixed schema.

### 30.3. Mixed schema trong rolling deployment

- Readers có thể cần hỗ trợ hai keys.
- Writer phải xác định field canonical.
- Index mới cần sẵn sàng trước filter cutover.
- Facet counts không được đếm hai aliases như hai loại thuộc tính.
- Backfill cần idempotent và không overwrite field mới.

### 30.4. Registry versioning

Một attribute definition mới không tự thay dữ liệu đã lưu theo key cũ. Cần deprecation/aliases, data migration và kiểm thử query giữa các phiên bản API.

### 30.5. Backfill quy mô lớn

Với hàng triệu products, dùng bounded batches, guarded updates, checkpoint, retry, rate limiting và giám sát replication lag. Không dùng một transaction khổng lồ để “đổi schema toàn collection” nếu chiến lược backfill idempotent + reconciliation đáp ứng yêu cầu.

## 31. Tìm kiếm văn bản và structured filtering là hai yêu cầu khác nhau

Người dùng thường có hai mục tiêu:

1. **Search text:** tìm theo từ/cụm từ trong title, description, brand aliases.
2. **Structured filtering:** category, price, RAM, color, size, availability.

MongoDB **find + indexes** phù hợp với nhiều structured filters. Full-text relevance, autocomplete, fuzzy search, synonyms hoặc search facets lớn có thể cần **MongoDB Search/Atlas Search** hay một search service khác tùy deployment.

### 31.1. $text không phải mọi thứ

MongoDB text index và **$text** có khả năng riêng, nhưng không tự có autocomplete, semantic search hoặc arbitrary substring search tối ưu. Cần đánh giá ngôn ngữ, index và use case.

### 31.2. Search index và B-tree index khác nhau

**MongoDB Search** có search-index model và stages như **$search/$searchMeta** trên deployment hỗ trợ. Không nhầm chúng với index tạo bởi db.collection.createIndex. Search index có thể cập nhật **asynchronously**, do đó kết quả search có thể hơi trễ so với writes.

Không dùng search results làm nguồn có thẩm quyền cho giá cuối cùng hoặc tồn kho lúc checkout.

### 31.3. Tenant/visibility trong search

Search query phải bảo vệ scope:

~~~text
authenticated tenant
status ACTIVE
visibility PUBLIC
other ACL constraints
~~~

Không dựa vào frontend lọc dữ liệu riêng tư sau khi search backend đã trả về. Với Search, cần xem stage placement và filter/index semantics đúng phiên bản để bảo đảm quyền ngay trong truy vấn.

### 31.4. Kết hợp text và facets

Các hướng:

- Dùng search engine cho relevance, và filters/facets trong cùng hệ thống khi hỗ trợ.
- Với candidate set nhỏ có giới hạn, lấy IDs rồi query MongoDB để tải details.
- Dùng denormalized search projection được chuẩn hóa.

Không đẩy hàng trăm nghìn IDs qua một truy vấn **$in** vô hạn chỉ để nối hai engine; cần phân trang và consistency strategy.

## 32. Cache và materialized facet counts

Facet counts có thể được cache theo bộ lọc normalized:

~~~text
cache key:
  tenantId
  catalogVisibility
  categoryId
  canonicalFilterHash
  selfExcludingFacetId
  currency / market
  searchIndexVersion (if relevant)
~~~

### 32.1. Cache key phải có tenant scope

Nếu cache key chỉ là categoryId+brandId mà thiếu tenantId/visibility, count của SHOP-A có thể được trả cho SHOP-B. Đó là lỗi security/data isolation. Key và authorization policy phải phù hợp; không tin một request header tenant chưa xác thực.

### 32.2. Cache counts có thể stale

~~~text
Product activated
  -> MongoDB updated
  -> facet cache not invalidated yet
  -> UI displays old count
~~~

Cần quyết định chấp nhận độ trễ bao lâu, TTL/invalidation/refresh policy. Không gắn nhãn “realtime exact” cho cached counts chưa đảm bảo.

### 32.3. Materialized facet collection

~~~javascript
{
  _id: "SHOP-A|laptops|brand",
  tenantId: "SHOP-A",
  categoryId: "laptops",
  facetKey: "brandId",
  counts: [
    { value: "acer", count: 2 },
    { value: "dell", count: 1 },
    { value: "lenovo", count: 1 }
  ],
  computedAt: ISODate("2026-10-01T00:00:00Z")
}
~~~

Counts này chỉ đúng cho **scope không có các filter khác**. Nó không tự cho ra count chính xác sau khi người dùng chọn RAM≥16 và maxPrice≤30 triệu.

### 32.4. Không materialize mọi tổ hợp

Nếu có hàng chục facets và hàng trăm giá trị, lưu mọi tổ hợp count gây bùng nổ. Có thể cache top queries, dùng query engine cho long-tail và lựa chọn specialized search index khi workload phù hợp.

## 33. Đồng bộ search projection và giao dịch mua hàng

Hệ thống lớn thường có một sơ đồ:

~~~text
Product master + Category metadata
            |
            v
        Product events
            |
            v
Catalog search projection / MongoDB Search index
            |
            v
        Listing / Facets
            |
            v
     Product details API
            |
            v
Price + Inventory authority
            |
            v
       Checkout workflow
~~~

Search projection có thể chứa những fields được **denormalize** như brand label, availableVariantOptions, min price và category ancestry. Nó là **read model**, không phải nguồn sự thật duy nhất cho tồn kho và giá.

### 33.1. Sự kiện out-of-order

Ví dụ:

~~~text
T1: price set to 22M (revision=10)
T2: price set to 20M (revision=11)
Event revision=11 processed
Event revision=10 arrives late
~~~

Nếu consumer không kiểm revision, search projection có thể quay về 22M. Cần idempotent event handlers, version guards hoặc ordered partitioning đủ cho data model.

### 33.2. Change streams có những giới hạn

MongoDB change streams có thể hỗ trợ đồng bộ thay đổi trên replica set/sharded topology phù hợp, nhưng cần resume tokens, xử lý consumer lag và đủ retention window. Không coi change stream là “exactly once business side effects” tự động; consumer vẫn phải đảm bảo idempotency và hành vi khi replay/duplicate.

### 33.3. SKU stock thay đổi liên tục

Nếu availability là filter được đọc hàng nghìn lần, có thể cần compact search projection để tránh join inventory realtime cho mỗi listing. Nhưng UI cần chấp nhận độ trễ theo policy; checkout phải kiểm tra lại tồn kho với concurrency safeguards.

### 33.4. Khi product bị ngừng bán

Một product **status=ARCHIVED** phải biến khỏi public listing/search. Nếu read model cập nhật chậm, có thể xuất hiện tạm thời trong kết quả. Backend của API details và checkout vẫn phải kiểm tra status từ nguồn đáng tin cậy trước khi cho phép mua.

## 34. Phân quyền và chống lộ dữ liệu trong catalog

Public catalog không có nghĩa mọi field của product đều công khai.

### 34.1. Các nhóm dữ liệu

| Nhóm | Ví dụ | Thông thường |
|---|---|---|
| Public listing | title, thumbnail, public price | Có thể xuất |
| Public specs | RAM, storage, color | Theo category/approval |
| Seller private | supplierCost, margin | Không xuất public |
| Moderator metadata | reviewFlags, moderationNotes | Chỉ nội bộ |
| Tenant private | unpublished products | Không cho tenant khác đọc |
| Personalization | viewedBy, segments | Có thể là PII, có policy riêng |

Một object attributes linh hoạt không nên là nơi tiện tay lưu mọi loại thông tin nhạy cảm rồi trả toàn bộ nó ra response.

### 34.2. Authorization trước aggregation

Trong faceted search, **tenantId/status/visibility** phải được áp đúng từ đầu. Một aggregation group có thể rò rỉ thông tin qua counts ngay cả khi không trả product details. Không coi “chỉ trả số lượng” là miễn authorization.

### 34.3. Không dùng supplierCost làm facet công khai

Nếu backend lấy mọi attributes ra nhóm facets bằng **$objectToArray**, một field giá nhập có thể lộ dưới dạng count hoặc value. Registry phải phân biệt public filterable vs internal-only, và data flow cần review.

### 34.4. Giới hạn tài nguyên

User có thể gửi rất nhiều facet values hoặc lọc một category cực lớn. Áp dụng:

- Rate limits.
- Query complexity limits.
- Page size max.
- Timeouts/maxTime.
- Bounded aggregation output.
- Caching theo đúng tenant scope.

Lỗi quyền không được giải quyết bằng cách chỉ cho kết quả bị lọc ở frontend.

## 35. Kiểm thử catalog filtering trên dữ liệu đại diện

Các phép thử cần kiểm tra **logic kết quả**, **BSON types**, **tenant isolation**, **facet count** và **index performance**. Một query trả đúng trên bộ dữ liệu rất nhỏ không chứng minh nó chạy nhanh khi có hàng triệu sản phẩm.

### 35.1. Bảng kiểm thử với sample data

| Điều kiện | Kết quả mong đợi |
|---|---|
| SHOP-A, laptops, ACTIVE/PUBLIC | L-101, L-102, L-103, L-104 |
| SHOP-A, laptops, brand=acer | L-101, L-104 |
| SHOP-A, laptops, ramGB≥16 | L-101, L-103, L-104 |
| SHOP-A, laptops, priceVnd≤20M | L-102 |
| SHOP-A, laptops, brand=acer, ramGB≥16, price≤30M | L-101 |
| SHOP-A, laptops, storageGB=1024 | L-103, L-104 |
| SHOP-A, phones, storageGB=256 | P-101 |
| SHOP-A, shoes, brand=puma | S-101 |
| SHOP-A, laptops, brand=acer, ram≥64 | Không có kết quả |
| SHOP-B, laptops, brand=acer | L-X (không có records SHOP-A) |

Các ví dụ không có filter availability cho laptop vì sample products không chứa inventory. Đừng mặc định sản phẩm có status ACTIVE thì luôn còn hàng.

### 35.2. Test $elemMatch chống false positives

Tạo document biến thể:

~~~javascript
db.variantsLab.insertOne({
  _id: "V-CROSS",
  variants: [
    { color: "black", sizeEU: 40, availableQty: 2 },
    { color: "black", sizeEU: 41, availableQty: 0 },
    { color: "white", sizeEU: 41, availableQty: 3 }
  ]
});
~~~

Query:

~~~javascript
db.variantsLab.find({
  variants: {
    $elemMatch: {
      color: "black",
      sizeEU: 41,
      availableQty: { $gt: 0 }
    }
  }
});
~~~

phải **không trả V-CROSS**. Nếu truy vấn dotted paths độc lập lại trả V-CROSS, test đã phát hiện kiểu false positive cần phòng tránh.

### 35.3. Test Attribute Pattern key/value cùng phần tử

~~~javascript
db.attrLab.insertOne({
  _id: "A-CROSS",
  attributes: [
    { key: "ramGB", valueNum: 8 },
    { key: "storageGB", valueNum: 1024 }
  ]
});
~~~

Query **$elemMatch: {key:"ramGB", valueNum:{$gte:16}}** phải không match. Nhưng query dùng **attributes.key="ramGB"** và **attributes.valueNum≥16** độc lập có thể match sai.

### 35.4. Test OR vs AND

Với **brand in [acer,dell]** và **RAM≥16**, có **L-101, L-103, L-104** nếu chưa lọc giá.

Với **brand=acer AND brand=dell** trên field scalar, không có product nào có cả hai brand IDs. Một multi-select brand thông thường cần OR/$in, không phải ghép hai phép bằng AND.

### 35.5. Test facet counts

Không có filter ngoài category:

~~~text
brands: acer=2, dell=1, lenovo=1
RAM: 8=1, 16=2, 32=1
total=4
~~~

Chọn **brand=acer, RAM≥16**, self-excluding counts:

~~~text
items: L-101, L-104
total=2
brands (bỏ brand filter): acer=2, dell=1
RAM (bỏ RAM filter): 16=1, 32=1
~~~

Nếu UI muốn conjunctive counts, kết quả khác và test cần dựa vào contract đã chọn.

### 35.6. Test theo trạng thái và quyền

Nên bổ sung một product:

~~~javascript
{
  _id: "L-PRIVATE",
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "DRAFT",
  visibility: "PRIVATE",
  brandId: "acer",
  priceVnd: NumberLong("1000000"),
  attributes: { ramGB: 128 }
}
~~~

Public listing/brand facet/RAM facet phải **không tính sản phẩm này**. Một filter sai có thể làm lộ thông tin qua counts ngay cả khi items branch vô tình bỏ nó.

### 35.7. Test sorting và pagination

Tạo hai products cùng priceVnd và kiểm tra sort **priceVnd + _id** xác định. Duyệt qua các pages và xác minh không có duplicate IDs trong điều kiện dữ liệu đứng yên.

Khi cập nhật price giữa pages, cần có test cho hành vi đã chấp nhận (eventual consistency, cursor invalidation hoặc snapshot policy), không giả định offset luôn ổn định.

### 35.8. Test invalid input

- ramGBMin=abc: lỗi validation.
- ramGBMin=-1: lỗi validation.
- priceMax=NaN: lỗi validation.
- category không tồn tại: 404/empty theo API contract.
- facet key không được filterable: từ chối.
- tenantId do user tự gửi khác identity: không cấp quyền.
- limit quá lớn: từ chối/cap theo policy.
- sort field tùy ý ngoài allowlist: từ chối.
- multi-value list quá dài: từ chối.

### 35.9. Tích hợp Java/Spring Data

Nên test thực với MongoDB trong môi trường riêng (container/test cluster) cho:

- Native Driver **Filters.elemMatch**.
- Spring Data **Criteria.elemMatch**.
- Numeric serialization **Long/Decimal128/Integer**.
- Aggregation **$facet** và nested DTO.
- **$objectToArray** trên attributes object.
- Index planner trên dataset gần production hơn.

Một unit test chỉ mock repository không thể xác minh index performance hoặc BSON query semantics thực của MongoDB.

## 36. Runbook tối ưu một catalog filter chậm

### Bước 1 — Chốt query shape

Ghi:

~~~text
tenant scope:
category:
selected facets:
sort order:
page size:
schema model:
attribute type:
source of price/availability:
~~~

Không so sánh hai query khác category/selectivity rồi coi là cùng workload.

### Bước 2 — Xác nhận kết quả đúng

Một query có thể chạy rất nhanh vì nó đã **lọc sai**. Kiểm tra:

- Có tenantId/status/visibility không?
- Multi-select brand dùng OR hay AND đúng?
- Numeric range dùng đúng BSON type?
- SKU color/size/stock dùng cùng một element?
- Counts đếm product hay SKU?

### Bước 3 — Xem executionStats

Đo keys/docs examined, nReturned, sort, index, memory/spills và duration. Với Atlas Search cần xem Search-specific diagnostics phù hợp, không dùng B-tree explain để giải thích toàn bộ search-index execution.

### Bước 4 — Xem index phù hợp

Nếu query luôn có tenant/category/status và sort price, cân nhắc compound index theo equality/sort. Nếu query Attribute Pattern dùng $elemMatch, xem compound multikey index theo key/value. Nếu workload rất đa dạng, đánh giá wildcard với explain.

### Bước 5 — Đánh giá cardinality và data skew

Một category có một triệu documents, một brand chiếm 70%; query lọc brand đó vẫn lớn. Tăng index không tự giảm lượng data phải scan nếu filter kém chọn lọc. Có thể cần pagination tốt, cache hoặc search projection.

### Bước 6 — Cắt giảm dữ liệu output

Project những fields cần cho listing, giới hạn page, không $lookup toàn bộ variants/suppliers cho mỗi product.

### Bước 7 — Giới hạn facet branch costs

Nếu $facet có nhiều branches group/sort lớn, tách truy vấn, cache các counts ít biến động hoặc materialize một số dimensions phổ biến.

### Bước 8 — Đo lại dưới load

Theo dõi:

- p50/p95/p99 latency.
- CPU/IO/working set.
- MongoDB connections và pool wait time.
- Facet cache hit rate/freshness.
- Search index lag.
- Price/inventory projection freshness.
- Index size/write amplification.

Không dùng một explain trên 8 products làm cơ sở duy nhất cho thiết kế production.

## 37. Các lỗi thiết kế/truy vấn catalog thường gặp

### 37.1. Đổi thuộc tính trong giao diện nhưng data query vẫn dùng key cũ

**Triệu chứng:** người dùng chọn RAM, nhưng nhiều laptop không xuất hiện.

**Nguyên nhân:** một số documents dùng **memoryGB**, một số dùng **ramGB**.

**Cách xử lý:** registry canonical key, migration old/new keys theo pha và kiểm tra query coverage. Không chỉ thay label UI.

### 37.2. Lọc số bằng String

**Triệu chứng:** người dùng chọn RAM≥16 nhưng không match sản phẩm lưu ramGB="32".

**Nguyên nhân:** BSON String khác Numeric.

**Xử lý:** validate và normalize type tại ingestion; backfill dữ liệu cũ. Không chạy range comparison kiểu text cho numeric values.

### 37.3. Lọc hai thuộc tính từ hai array elements khác nhau

**Triệu chứng:** laptop RAM 8/SSD 1024 thỏa nhầm RAM≥16 trong Attribute Pattern.

**Nguyên nhân:** dùng dotted predicates độc lập thay vì $elemMatch.

**Xử lý:** dùng $elemMatch để ràng buộc key/value cùng phần tử.

### 37.4. Product match màu/size không tồn tại ở cùng SKU

**Triệu chứng:** UI báo “đen, size 41, còn hàng”, nhưng checkout không tìm được SKU.

**Nguyên nhân:** dựa trên colors[], sizes[] và hasStock[] độc lập.

**Xử lý:** query cùng variant bằng $elemMatch hoặc variant collection có compound filter; xác minh lại tồn kho lúc checkout.

### 37.5. Facet counts bị nhân số biến thể

**Nguyên nhân:** unwind variants rồi count tất cả rows, thay vì count distinct productId khi UI muốn số sản phẩm.

**Xử lý:** group theo (productId, facetValue), rồi group theo facetValue.

### 37.6. Facet count không đổi khi chọn filter

**Nguyên nhân:** app dùng cached counts theo category, không tính các filter động.

**Xử lý:** định nghĩa conjunctive/self-excluding behavior, tính counts theo scope và các filter tương ứng; nếu cache phải ghi rõ freshness/approximation.

### 37.7. Facet Brand chỉ còn một lựa chọn

**Nguyên nhân:** tính Brand facet sau khi áp brand=acer trong common $match.

**Xử lý:** nếu UI yêu cầu self-excluding facets, bỏ brand filter **chỉ ở branch Brand**, nhưng vẫn giữ các filter khác.

### 37.8. $facet trả document quá lớn

**Nguyên nhân:** mỗi branch trả hàng chục nghìn values hoặc items không có limit, vượt giới hạn memory/document.

**Xử lý:** top N, bounded arrays, pagination, split queries hoặc materialized counts. allowDiskUse không sửa tất cả giới hạn của $facet.

### 37.9. Wildcard index tồn tại nhưng query vẫn chậm

**Nguyên nhân:** compound filter/sort không phù hợp, index quá rộng, selectivity thấp hoặc cần fetch nhiều documents.

**Xử lý:** explain, so sánh compound index cho query phổ biến và giảm index bloat.

### 37.10. Tạo index cho mọi thuộc tính khiến ghi chậm

**Nguyên nhân:** quá nhiều indexes, tăng write amplification/storage.

**Xử lý:** đo query traffic, loại indexes không có giá trị theo quy trình, chỉ index top facets và xem wildcard cho long-tail khi phù hợp.

### 37.11. Cache trả dữ liệu tenant khác

**Nguyên nhân:** key thiếu tenantId/visibility, hoặc app nhận tenantId từ client chưa xác thực.

**Xử lý:** coi là security incident, sửa canonical cache key/scope và kiểm tra authorization end-to-end.

### 37.12. Public listing xuất supplierCost

**Nguyên nhân:** trả nguyên product Document, hoặc dynamic facets lấy mọi attribute values.

**Xử lý:** projection/DTO/attribute registry allowlist theo quyền; không expose nội bộ qua JSON response.

### 37.13. Product đã archived vẫn xuất hiện trong search

**Nguyên nhân:** cache hoặc search projection còn stale, hoặc quên status filter.

**Xử lý:** kiểm tra ingestion/events, freshness và quyền ở details/checkout. Không chỉ ẩn item ở frontend.

### 37.14. Giá hiển thị khác giá checkout

**Nguyên nhân:** materialized min price/offer cache chưa cập nhật, currency hoặc promotion conditions khác.

**Xử lý:** định nghĩa rõ listing price, đo freshness và chốt giá từ authoritative service khi đặt hàng.

### 37.15. Offset pagination trùng sản phẩm

**Nguyên nhân:** sản phẩm được thêm/xóa/đổi giá trong lúc duyệt hoặc sort không có tie-breaker.

**Xử lý:** sort price+_id, cân nhắc keyset/snapshot policy và chấp nhận eventual changes theo sản phẩm.

### 37.16. Index mới không dùng được để sort

**Nguyên nhân:** field index order không phù hợp query, brand nằm giữa equality prefix và price nhưng query thiếu brand, hoặc sort trên computed field.

**Xử lý:** kiểm tra compound index order và explain, không giả định có index là đủ.

### 37.17. Group cả sản phẩm không có attribute

**Triệu chứng:** RAM facet có một nhánh null rất lớn.

**Nguyên nhân:** group RAM trên category gồm nhiều products không có ramGB, hoặc có field wrong type.

**Xử lý:** match category và numeric type trước group; thiết kế unknown bucket nếu UI cần.

### 37.18. Brand ID và label bị trộn

**Triệu chứng:** facet hiển thị Acer, ACER, Acer Inc. như ba giá trị.

**Nguyên nhân:** không chuẩn hóa brand ID tại import.

**Xử lý:** dùng brandIds ổn định, lưu localized labels riêng và có mapping aliases.

### 37.19. Multi-select dùng AND ngoài ý định

**Triệu chứng:** chọn Acer và Dell cho ra 0 sản phẩm.

**Nguyên nhân:** backend ghép hai equality filters trên cùng field scalar bằng AND.

**Xử lý:** dùng $in theo chính sách OR trong một facet.

### 37.20. Query category cha không lấy descendant

**Nguyên nhân:** query categoryId="electronics" nhưng products chỉ lưu leaf "laptops"/"phones".

**Xử lý:** query categoryAncestorIds hoặc resolve descendant categories có index/caching và đồng bộ taxonomy.

### 37.21. Inventory filter chỉ kiểm tổng sản phẩm

**Nguyên nhân:** hasAvailableVariant=true nhưng variant có color/size đã chọn hết hàng.

**Xử lý:** query availability cùng variant, re-check at checkout.

### 37.22. Dữ liệu thuộc tính thay đổi nhưng facet counts không đổi

**Nguyên nhân:** cache invalidation/changelog consumer lag, hoặc materialized counts không được cập nhật.

**Xử lý:** quan sát event versions, consumer lag, cache freshness và đối soát định kỳ.

### 37.23. Seller nhập một thuộc tính hai lần

**Nguyên nhân:** Attribute Pattern không có validation single-valued keys; unique multikey index không bảo vệ điều kiện trong cùng document như mong đợi.

**Xử lý:** validate unique keys tại ingestion; có test và quy trình làm sạch duplicates.

### 37.24. Regex/autocomplete chậm

**Nguyên nhân:** arbitrary substring regex trên lượng dữ liệu lớn, index thông thường không tối ưu.

**Xử lý:** đặt yêu cầu search rõ, cân nhắc dedicated Search/autocomplete và query limits.

### 37.25. Dữ liệu filter sai sau đổi đơn vị

**Nguyên nhân:** storage=0.5TB được import sai thành storageGB=0.5; kết quả range bị sai.

**Xử lý:** migration có unit-aware conversion, version và validation; không chỉ đổi tên field.

## 38. Các quy tắc vận hành khi catalog tăng trưởng

### 38.1. Tách read và write responsibilities

Một workflow tham khảo:

~~~text
Seller input
   |
   v
Validate product/category/attribute registry
   |
   v
Canonical master data + variants/offers
   |
   v
Change events / outbox
   |
   v
Search projection + cached/materialized facets
   |
   v
Public catalog APIs
~~~

Ingestion phải bảo đảm types/units/identity. Search projection tối ưu read; checkout dùng authoritative stock/price.

### 38.2. Quan sát theo category

Nên đo latency và workload phân theo những category groups có cardinality phù hợp, nhưng tránh metrics labels chứa hàng nghìn product IDs. Một category có 99% queries và triệu sản phẩm cần index/compute khác category hiếm với 100 records.

### 38.3. Làm mới search data có kiểm soát

Khi hàng triệu attributes được migrate:

- Throttle writes để tránh overload.
- Xem replication/search index lag.
- Đảm bảo event consumers idempotent.
- Đối soát tài liệu bị bỏ sót.
- Bật filter mới sau khi dữ liệu/index đã sẵn sàng.

### 38.4. Giới hạn document growth

Một product có hàng chục nghìn variants, reviews, inventory history và media files không nên nhét tất cả trong một document. MongoDB có giới hạn kích thước BSON document; arrays tăng vô hạn làm cập nhật và đọc khó kiểm soát. Tách dữ liệu có lifecycle khác nhau thành collections phù hợp.

### 38.5. Định nghĩa SLO và freshness

Ví dụ các nhóm chỉ tiêu:

~~~text
Catalog listing p95 latency:
Facet count p95 latency:
Search index freshness:
Price projection freshness:
Stock projection freshness:
Maximum allowed page size:
Maximum active query time:
~~~

Cần điền số liệu dựa trên yêu cầu sản phẩm và benchmark thật, không coi các con số ví dụ là mặc định MongoDB.

## 39. Bài tập thực hành: thiết kế schema và query

Các bài tập dùng database **catalog_lab** và sample data ở mục 4, trừ khi đề bài cung cấp document riêng. Nên chạy trong database thử nghiệm với quyền phù hợp.

### Bài 1. Chọn field chung và field đặc thù

Một catalog có laptops, phones và shoes.

**Câu hỏi:** những fields nào nên thống nhất ở product và những fields nào tùy category?

**Định hướng:** tenantId, categoryId, brandId, title, status, visibility, price hoặc offer reference thường là core fields. ramGB/storageGB/batteryMAh/material có thể theo category. Cần tránh trộn mọi category-specific field vào top-level mà không có rule rõ.

### Bài 2. Lọc laptop Acer

**Yêu cầu:** tìm sản phẩm SHOP-A, ACTIVE/PUBLIC, laptops, brand=acer.

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  brandId: "acer",
  status: "ACTIVE",
  visibility: "PUBLIC"
});
~~~

**Đáp án:** L-101 và L-104.

### Bài 3. Lọc RAM và giá

**Yêu cầu:** RAM≥16, priceVnd≤30M, laptops của SHOP-A.

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  "attributes.ramGB": { $gte: 16 },
  priceVnd: { $lte: NumberLong("30000000") }
});
~~~

**Đáp án:** L-101. Với query public thực, thêm status ACTIVE và visibility PUBLIC.

### Bài 4. Lọc nhiều brands

**Câu hỏi:** nếu user chọn Acer hoặc Dell thì dùng gì?

**Đáp án:**

~~~javascript
{ brandId: { $in: ["acer", "dell"] } }
~~~

Đừng dùng AND hai equality predicates trên cùng brandId scalar.

### Bài 5. Storage trong nhiều lựa chọn

**Yêu cầu:** storageGB trong [256,1024] cho laptops SHOP-A.

**Đáp án:** L-102, L-103 và L-104. L-101 có 512 không nằm trong danh sách.

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  "attributes.storageGB": { $in: [256, 1024] }
});
~~~

### Bài 6. Lỗi String vs Number

Document:

~~~javascript
{ attributes: { ramGB: "16" } }
~~~

**Câu hỏi:** vì sao query ramGB≥16 dạng number không đáng tin?

**Đáp án:** BSON String không phải Numeric; cần chuẩn hóa dữ liệu thành số trước khi query range.

### Bài 7. Thuộc tính chỉ có một giá trị

Một Product Attribute Pattern chứa hai phần tử key=ramGB, valueNum=8 và 32.

**Câu hỏi:** có chắc ramGB≥16 phản ánh đúng sản phẩm không?

**Đáp án:** không. Single-valued key bị trùng, cần validate và sửa dữ liệu. Unique multikey index không thay logic kiểm trùng từng entry trong một document.

### Bài 8. $elemMatch với Attribute Pattern

~~~javascript
{
  attributes: [
    { key: "ramGB", valueNum: 8 },
    { key: "storageGB", valueNum: 1024 }
  ]
}
~~~

**Câu hỏi:** làm sao tránh match nhầm RAM≥16?

**Đáp án:**

~~~javascript
{
  attributes: {
    $elemMatch: {
      key: "ramGB",
      valueNum: { $gte: 16 }
    }
  }
}
~~~

### Bài 9. Hai attributes khác nhau

**Yêu cầu:** RAM≥16 và SSD≥512 trong Attribute Pattern.

**Định hướng:** dùng **$all** chứa hai **$elemMatch** hoặc **$and** của hai $elemMatch trên cùng array field; mỗi phần tử ràng buộc key với đúng value, không tạo điều kiện một phần tử phải có cả hai key.

### Bài 10. Match SKU cùng color, size và stock

Variants:

~~~javascript
[
  { color: "black", sizeEU: 41, availableQty: 0 },
  { color: "white", sizeEU: 41, availableQty: 3 }
]
~~~

**Câu hỏi:** product có đáp ứng black/size41/inStock=true không?

**Đáp án:** không. Dùng $elemMatch trên variants, cùng phần tử thỏa ba predicates.

### Bài 11. Phân biệt product count và SKU count

Một product có ba SKU đỏ, hai SKU còn hàng.

**Câu hỏi:** nếu UI facet “màu đỏ: số sản phẩm”, nên đếm 1 hay 2/3?

**Đáp án:** đếm **1 product** nếu có ít nhất một SKU đỏ đáp ứng các điều kiện hiện tại; đếm SKU là metric khác. Cần group/deduplicate theo productId.

### Bài 12. Tìm products thuộc category cha

Product chỉ lưu categoryId="laptops", categoryAncestorIds=["electronics","computers"].

**Câu hỏi:** filter categoryId="electronics" có match không? Làm sao tìm?

**Đáp án:** không; query categoryAncestorIds="electronics" hoặc resolve descendant categories theo taxonomy.

### Bài 13. Default 0 có đúng không?

Một đôi giày không có batteryMAh. Developer đặt batteryMAh=0 để không bị null.

**Câu hỏi:** có nên không?

**Đáp án:** không nếu battery không áp dụng; 0 là giá trị numeric khác unknown/not-applicable. Thiết kế missing/NA rõ.

### Bài 14. Facet counts cơ bản

**Câu hỏi:** với SHOP-A/laptops ACTIVE/PUBLIC, count theo brand là gì?

**Đáp án:** acer=2, dell=1, lenovo=1.

### Bài 15. Facet theo RAM

**Câu hỏi:** với 4 laptops SHOP-A, RAM facet là gì?

**Đáp án:** RAM 8=1, RAM 16=2, RAM 32=1.

### Bài 16. Self-excluding Brand

User chọn brand=acer và RAM≥16.

**Câu hỏi:** Brand facet self-excluding có những values nào?

**Đáp án:** acer=2, dell=1. Khi tính Brand, bỏ filter brand nhưng giữ RAM≥16, nên Lenovo RAM8 không match.

### Bài 17. Self-excluding RAM

Cùng điều kiện bài 16.

**Câu hỏi:** RAM facet self-excluding là gì?

**Đáp án:** 16=1 và 32=1. Khi tính RAM, bỏ RAM filter nhưng giữ brand=acer.

### Bài 18. Count sau phân trang

Query có 100 products phù hợp, trả page size 24.

**Câu hỏi:** totalCount nên là 100 hay 24?

**Đáp án:** 100 nếu UI yêu cầu exact total matching products. 24 chỉ là số dòng trang hiện tại.

### Bài 19. $facet và common match

**Câu hỏi:** vì sao không đưa match brand=acer trước $facet nếu muốn Brand self-excluding?

**Đáp án:** branch Brand không thể khôi phục các brands đã bị loại ở stage trước. Đưa tenant/category/status/visibility vào common match; các filter có thể loại trừ theo facet đặt trong branches phù hợp.

### Bài 20. Group array of values

Một product có ports=["USB-C","HDMI"].

**Câu hỏi:** $objectToArray rồi group theo value ports có tự đếm riêng từng port không?

**Đáp án:** không. Value còn là array; cần unwind/normalize rồi deduplicate product+port nếu đếm sản phẩm.

### Bài 21. Chọn index cho listing

Query thường gặp: tenantId + categoryId + status + visibility, sort priceVnd tăng và _id tăng.

**Đáp án định hướng:**

~~~javascript
db.products.createIndex({
  tenantId: 1,
  categoryId: 1,
  status: 1,
  visibility: 1,
  priceVnd: 1,
  _id: 1
});
~~~

Phải kiểm chứng explain dưới workload thực.

### Bài 22. Index có brandId

**Câu hỏi:** index tenant/category/status/visibility/brandId/priceVnd có luôn phục vụ price sort nếu không filter brand?

**Đáp án:** không. Field brandId đứng trước price có thể làm index không đáp ứng global price sort khi brand không bị ràng buộc equality.

### Bài 23. Compound multikey trên hai arrays

Product có colors[] và sizesEU[] độc lập. Developer muốn compound index trên cả hai.

**Đáp án:** MongoDB compound multikey hạn chế parallel arrays; hơn nữa hai arrays không bảo toàn quan hệ color-size. Nên dùng variants cùng phần tử hoặc collection SKU.

### Bài 24. Wildcard index

**Câu hỏi:** wildcard index attributes.$** có tự thay compound indexes category+brand+price+RAM không?

**Đáp án:** không. Wildcard hữu ích cho dynamic paths nhưng không tự tối ưu mọi compound predicates và sort.

### Bài 25. Partial index

Một partial index chỉ chứa status=ACTIVE và visibility=PUBLIC.

**Câu hỏi:** admin query ARCHIVED có dùng index này để trả đủ documents không?

**Đáp án:** không thể chỉ dựa vào partial index vì index không chứa documents ngoài filter.

### Bài 26. Facet counts và bảo mật

Public facet trả RAM=128:1 cho sản phẩm PRIVATE.

**Câu hỏi:** lỗi gì?

**Đáp án:** quyền/scope chưa được áp trong facet branch, làm lộ thông tin qua count. Cần common match tenant/status/visibility và authorization.

### Bài 27. Giá nhiều currency

**Câu hỏi:** có được so sánh trực tiếp 20.000.000 VND và 900 USD trong cùng priceMax mà không quy đổi không?

**Đáp án:** không. Cần currency và quy tắc chuyển đổi/scale nhất quán.

### Bài 28. Sort có giá trùng

Hai products cùng priceVnd. Query sort chỉ theo priceVnd.

**Câu hỏi:** vấn đề khi phân trang?

**Đáp án:** thứ tự items cùng giá không xác định; dùng priceVnd + _id làm tie-breaker.

### Bài 29. Keyset cursor

Cuối trang có (price=22M, _id="L-101"). Trang kế theo giá tăng cần:

~~~javascript
{
  $or: [
    { priceVnd: { $gt: NumberLong("22000000") } },
    {
      priceVnd: NumberLong("22000000"),
      _id: { $gt: "L-101" }
    }
  ]
}
~~~

Phải kết hợp tenant/category/status/visibility và sort tương ứng.

### Bài 30. Dynamic facets và dữ liệu riêng tư

Attribute object có internalCost và serialNumber.

**Câu hỏi:** có thể xuất mọi entries từ $objectToArray ra public facets không?

**Đáp án:** không. Chỉ keys được registry cho phép visible/filterable và đúng user permissions mới được xuất.

### Bài 31. Tồn kho ở listing khác checkout

Cached listing cho biết color=black,size41 còn hàng, nhưng inventory đã hết trước checkout.

**Câu hỏi:** có được xác nhận order dựa trên listing không?

**Đáp án:** không. Checkout phải xác nhận số lượng từ nguồn có thẩm quyền và xử lý concurrency/reservation.

### Bài 32. Cache thiếu tenant

Cache key chỉ có category=laptops,brand=acer, thiếu tenantId.

**Câu hỏi:** nguy cơ?

**Đáp án:** lộ hoặc trộn products/facet counts giữa tenants. Key phải ràng buộc authenticated tenant scope và visibility/market.

### Bài 33. Dữ liệu cũ đổi key

Old field attributes.storage="512 GB"; new field attributes.storageGB=512.

**Câu hỏi:** đổi nhãn UI là đủ chưa?

**Đáp án:** chưa. Cần expand readers/writers, parse/convert old data, backfill, reconcile, index switch và contract.

### Bài 34. Partial SKU match

Một product có:

~~~javascript
[
  { color: "black", sizeEU: 40, availableQty: 1 },
  { color: "white", sizeEU: 41, availableQty: 1 }
]
~~~

**Câu hỏi:** product có black size41 còn hàng không?

**Đáp án:** không. Màu và size không thuộc cùng variant.

### Bài 35. Thiết kế catalog đa ngành

Một marketplace có 300 categories và 4 triệu products:

~~~text
80% requests: category + brand + price sort
15% requests: category + one numeric facet
5% requests: long-tail spec filters
~~~

**Yêu cầu:** đề xuất schema/index.

**Định hướng:** core fields cho category/brand/status/price, hybrid hoặc object attributes với registry; compound indexes cho top patterns, indexes category-specific cho numeric facets cần thiết, cân nhắc wildcard cho long-tail sau khi đo. Không index mọi permutation.

### Bài 36. Validate FilterSpec

Backend nhận:

~~~javascript
{
  category: "laptops",
  attribute: "ramGB",
  min: "16",
  sort: "price_asc"
}
~~~

**Đáp án định hướng:** lấy tenant từ auth, validate category/attribute filterable, parse "16" thành Number, validate range, allowlist sort, giới hạn page size/query complexity và dựng BSON query từ các operators được code kiểm soát.

### Bài 37. IXSCAN nhưng vẫn chậm

Một query scan 600.000 index entries, trả 24 products.

**Câu hỏi:** thấy IXSCAN đã đủ kết luận query tốt chưa?

**Đáp án:** chưa. Cần keys/docs examined, selectivity, sort stage và distribution. Có thể cần index/query khác hoặc giới hạn workload.

### Bài 38. Thiết kế facet dashboard

Yêu cầu:

~~~text
Category laptops
Selected: Acer, RAM >= 16
Show items + total + Brand counts + RAM counts
Brand counts show alternative brands
RAM counts show alternative RAM values
~~~

**Định hướng:** common match tenant/category/status/visibility; items+total branches áp Acer+RAM; Brand branch chỉ áp RAM; RAM branch chỉ áp Acer. Không đặt cả hai filters trước $facet.

### Bài 39. Product có quá nhiều variants

Một sản phẩm có 50.000 SKUs, inventory cập nhật liên tục.

**Câu hỏi:** có nên embed mọi SKU và stock vào product document?

**Định hướng:** cân nhắc tách SKU/inventory collection để tránh document growth/contention, dùng bounded search projection cho listing, kiểm tra lại lúc checkout.

### Bài 40. Product count từ SKU rows

Có 1.000 products và 2.500 SKUs. User chọn color black, size41, stock>0 và UI ghi “42 sản phẩm”.

**Câu hỏi:** aggregation cần bảo đảm gì?

**Đáp án:** filter color+size+stock trên cùng variant, rồi deduplicate theo productId trước khi count, tránh trả 42 SKU rows nhưng gắn nhãn là 42 products.

## 40. Checklist thiết kế catalog trước khi triển khai

### 40.1. Mô hình dữ liệu

- [ ] Đã phân biệt product, variant/SKU, offer và inventory.
- [ ] Có core fields nhất quán cho tenant/category/brand/status/visibility.
- [ ] Có registry thuộc tính theo category, type, unit và filter semantics.
- [ ] Biết thuộc tính nào single-valued, multi-valued, variant-specific.
- [ ] Không lưu String tùy ý cho numeric filter.
- [ ] Có chiến lược missing/null/unknown/not-applicable.
- [ ] Có giới hạn array/document growth và lifecycle của dữ liệu biến động nhanh.

### 40.2. Truy vấn và facets

- [ ] AND giữa facets và OR trong một facet được định nghĩa rõ.
- [ ] $elemMatch được dùng khi predicates phải thỏa cùng array element.
- [ ] Đơn vị facet count là product hay SKU được công bố.
- [ ] Facet counts áp đúng tenant/status/visibility.
- [ ] Conjunctive hay self-excluding facet semantics được thống nhất với UI.
- [ ] Facets của array/multi-valued keys được deduplicate phù hợp.
- [ ] Có giới hạn số facets và values trả ra API.
- [ ] Pagination ổn định và total count semantics rõ.

### 40.3. Index và hiệu năng

- [ ] Compound indexes dựa vào top query shapes thực.
- [ ] Multikey indexes đáp ứng hạn chế array paths.
- [ ] Wildcard index chỉ dùng sau khi hiểu giới hạn và đo workload.
- [ ] Có explain executionStats trên dataset đại diện.
- [ ] Có giới hạn sort/page size/time/query complexity.
- [ ] Có chiến lược caching/materialized counts khi cần.
- [ ] Đã tính write amplification/storage của indexes.

### 40.4. Bảo mật và tích hợp

- [ ] Tenant đến từ authenticated context.
- [ ] Public response chỉ có fields được phép.
- [ ] Dynamic attribute queries được allowlist và validate.
- [ ] Private specs/supplier cost không xuất trong dynamic facets.
- [ ] Search projection có freshness policy và xử lý events trễ.
- [ ] Checkout kiểm tra giá/tồn kho authoritative.
- [ ] Có contract tests cho downstream consumers/feeds.
- [ ] Có migration plan khi category/attribute definitions thay đổi.

### 40.5. Vận hành

- [ ] Có metrics query/facet p95/p99, error rate, index usage và lag.
- [ ] Có integration tests cho false positives của $elemMatch.
- [ ] Có test tenant isolation trong items **và** facet branches.
- [ ] Có test numeric types, unit conversion, boundary conditions.
- [ ] Có test product count vs SKU count.
- [ ] Có kế hoạch khi Search/index/cache không đồng bộ.
- [ ] Có phương án rollback schema/index trước khi thay đổi lớn.

## 41. Hợp đồng API trả listing và facets

Một response nên thể hiện rõ **sản phẩm đang hiển thị**, **tổng số sản phẩm phù hợp** và **ngữ nghĩa các counts**:

~~~javascript
{
  categoryId: "laptops",
  items: [
    {
      productId: "L-101",
      title: "Acer Swift A14",
      brandId: "acer",
      price: {
        amountMinor: 22000000,
        currency: "VND"
      }
    },
    {
      productId: "L-104",
      title: "Acer Creator 16",
      brandId: "acer",
      price: {
        amountMinor: 40000000,
        currency: "VND"
      }
    }
  ],
  page: {
    size: 24,
    nextCursor: null,
    totalProducts: 2
  },
  facets: {
    semantics: "self-excluding",
    brand: [
      { value: "acer", productCount: 2 },
      { value: "dell", productCount: 1 }
    ],
    ramGB: [
      { value: 16, productCount: 1 },
      { value: 32, productCount: 1 }
    ]
  }
}
~~~

Ví dụ minh họa bộ lọc **SHOP-A/laptops/brand=acer/RAM≥16** mà chưa thêm giới hạn giá. Trong JSON qua HTTP, số nguyên tiền VND nên được biểu diễn theo hợp đồng chính xác; nếu giá trị có thể vượt giới hạn Number an toàn của JavaScript, cân nhắc String decimal hoặc API schema hỗ trợ big integer.

### 41.1. Các quyết định cần ghi trong API specification

- **totalProducts** là exact hay cached/estimated?
- **Facet productCount** tính trên selected filters nào?
- **Facets** có được phép không cập nhật tức thời theo inventory không?
- **nextCursor** có ràng buộc tenant/filter/sort không?
- **Price** là base, min offer, promotional hay final checkout price?
- **Unknown attribute values** có bucket riêng không?
- **Counts bằng 0** có hiện trong UI không?
- **Brand labels** lấy từ registry theo locale hay từ product snapshots?

Một API không có những định nghĩa này có thể trả dữ liệu MongoDB hoàn toàn hợp lệ nhưng tạo trải nghiệm filter khó hiểu.

## 42. Tài liệu tham khảo

Khi triển khai thực tế, chọn tài liệu phù hợp với **MongoDB server version**, **Java Driver version** và **Spring Data MongoDB version** của dự án:

- [MongoDB Manual — Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/)
- [MongoDB Manual — Query Arrays](https://www.mongodb.com/docs/manual/tutorial/query-arrays/)
- [MongoDB Manual — Query Arrays of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/)
- [MongoDB Manual — $elemMatch](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/)
- [MongoDB Manual — $all](https://www.mongodb.com/docs/manual/reference/operator/query/all/)
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual — Wildcard Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-wildcard/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Manual — $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB Manual — $bucket](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucket/)
- [MongoDB Manual — $objectToArray](https://www.mongodb.com/docs/manual/reference/operator/aggregation/objectToArray/)
- [MongoDB Manual — $unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [Spring Data MongoDB — Template Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
- [Spring Data MongoDB — Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [MongoDB Search — Facet Operator](https://www.mongodb.com/docs/atlas/atlas-search/facet/)

Các đường dẫn tài liệu có thể thay đổi theo phiên bản; nếu một trang được chuyển, mở nhóm chủ đề tương ứng trên tài liệu chính thức và chọn bản phù hợp. Không sao chép cú pháp của tính năng chưa được deployment hỗ trợ.

## 43. Kết luận

Một catalog sản phẩm có thuộc tính biến đổi không chỉ là collection có nhiều field tùy ý. Thiết kế đúng cần kết hợp **schema**, **query semantics**, **index**, **SKU/offer/inventory**, **facets**, **API contract** và **data lifecycle**:

~~~text
                CATEGORY DEFINITIONS
                  /             \
                 v               v
          Attribute registry   Taxonomy
                 |               |
                 +-------+-------+
                         |
                         v
               CANONICAL PRODUCT DATA
                /        |         \
               v         v          v
           Attributes  Variants    Offers
               |         |          |
               +---------+----------+
                         |
                         v
                 SEARCH PROJECTION
                         |
           +-------------+--------------+
           |             |              |
           v             v              v
       Filter query   Facet counts   Sorting/paging
           |             |              |
           +-------------+--------------+
                         |
                         v
                  PUBLIC CATALOG API
                         |
                         v
                  PRODUCT SELECTION
                         |
                         v
               AUTHORITATIVE CHECKOUT
           (price and inventory re-check)
~~~

**Các nguyên tắc trọng tâm:**

1. **Nhận diện core fields và category-specific attributes** trước khi chọn object, array Attribute Pattern hay hybrid.
2. **Giá trị phải có kiểu và đơn vị chuẩn**. Range numeric trên String/đơn vị sai gây lỗi logic dù MongoDB không báo syntax error.
3. **Attribute Pattern cần $elemMatch** để key và value thuộc cùng phần tử; nhiều attributes khác nhau cần tổ hợp điều kiện phù hợp.
4. **Product và SKU không giống nhau**. Lọc màu/size/stock phải match trong cùng variant và counts phải xác định đang đếm product hay SKU.
5. **Facets là truy vấn có ngữ nghĩa**, không chỉ group: cần định nghĩa AND/OR, self-excluding behavior, exact/cached counts và phạm vi tenant.
6. **Index phục vụ query patterns**, không phải tạo một wildcard index rồi coi mọi filter/sort đã tối ưu.
7. **Category registry là nguồn hợp đồng dữ liệu**, quản lý type, units, allowed values, visibility và mapping keys theo ngôn ngữ/UI.
8. **Search projection có thể stale**; checkout không dựa vào cached stock/price mà phải xác nhận lại từ nguồn có thẩm quyền.
9. **Phân trang cần thứ tự ổn định** và phải xác định consistency khi product/price thay đổi giữa các trang.
10. **Validation, authorization, migration, monitoring và integration tests** là một phần của thiết kế catalog, không phải việc bổ sung sau khi hệ thống đã quá lớn.

Khi quyết định thiết kế từ **những câu hỏi người dùng thực sự muốn lọc** và **đơn vị dữ liệu hệ thống cần trả lời**, MongoDB có thể lưu nhiều nhóm sản phẩm trong cùng một mô hình linh hoạt mà vẫn truy vấn đúng, mở rộng được và giữ các giới hạn nghiệp vụ rõ ràng. Mục tiêu không phải làm một document chứa mọi thứ, mà là **dữ liệu mô tả sản phẩm đúng, filter cho ra kết quả đúng và hệ thống có thể duy trì hiệu năng khi catalog phát triển**.
