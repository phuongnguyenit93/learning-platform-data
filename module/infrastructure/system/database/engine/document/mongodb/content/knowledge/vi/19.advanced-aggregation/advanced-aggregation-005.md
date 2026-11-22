# Tổng hợp nhiều nhánh bằng $facet và giới hạn bộ nhớ riêng trong MongoDB

## 1. Tại sao cần $facet?

Trong một trang danh sách sản phẩm, ứng dụng thường phải trả về **nhiều góc nhìn trên cùng tập dữ liệu**: vài sản phẩm đầu tiên, tổng số sản phẩm khớp, số lượng theo danh mục, khoảng giá, thương hiệu và thống kê tồn kho. Nếu chạy từng truy vấn độc lập, ứng dụng cần gửi nhiều lệnh tới MongoDB và phải lặp lại một phần logic lọc.

**`$facet`** là một **aggregation stage** cho phép chạy **nhiều sub-pipeline độc lập** trên **cùng tập document đầu vào**, sau đó trả về **một document** chứa kết quả của các nhánh dưới dạng những **mảng riêng biệt**.

Ví dụ về kết quả mong muốn:

~~~javascript
{
  products: [ /* các sản phẩm của trang hiện tại */ ],
  totalCount: [ { total: 11 } ],
  byCategory: [ /* số lượng theo danh mục */ ],
  byBrand: [ /* số lượng theo thương hiệu */ ],
  priceRanges: [ /* các khoảng giá */ ]
}
~~~

Với `$facet`, các nhánh nhìn thấy **cùng input sau các stage đứng trước `$facet`**, nhưng mỗi nhánh có thể lọc, nhóm, sắp xếp hoặc giới hạn theo cách khác nhau.

Bài này tập trung vào:

1. Mô hình dữ liệu đi qua `$facet` và cú pháp nhiều nhánh.
2. Phân biệt **lọc chung trước facet** với **lọc riêng trong từng nhánh**.
3. Thiết kế metadata, phân trang, thống kê, `$bucket` và `$sortByCount`.
4. **Giới hạn bộ nhớ riêng của `$facet`**: 100 MB cho document trung gian do stage tạo, không thể dùng `allowDiskUse` để spill; đầu ra cuối chịu giới hạn **16 MiB BSON**.
5. Những stage không được dùng bên trong facet và cách tận dụng index.
6. Cách quan sát bằng `explain()`, phát hiện kết quả rỗng, tối ưu bộ nhớ và chọn khi nào không nên dùng `$facet`.

## 2. Cú pháp và sơ đồ luồng dữ liệu

Cú pháp tổng quát:

~~~javascript
db.collection.aggregate([
  { $match: { /* điều kiện chung */ } },
  {
    $facet: {
      branchA: [
        { /* stage A1 */ },
        { /* stage A2 */ }
      ],
      branchB: [
        { /* stage B1 */ }
      ],
      branchC: [
        { /* stage C1 */ }
      ]
    }
  }
]);
~~~

Mỗi **tên nhánh** (`branchA`, `branchB`...) trở thành **một trường mảng** trong document đầu ra. Mỗi nhánh là một mảng các stage aggregation hợp lệ trong ngữ cảnh `$facet`.

~~~text
                      orders / products
                              |
                              v
                     $match (lọc CHUNG)
                              |
                              v
                    +---------+---------+
                    |       $facet      |
                    +---------+---------+
                       /      |       \
                      v       v        v
                  products  category   price
                    |         |         |
                  $sort     $group     $bucket
                    |         |         |
                  $limit    $sort     [buckets]
                    |         |         |
                    +---------+---------+
                              |
                              v
                 MỘT DOCUMENT KẾT QUẢ
        {
          products: [ ... ],
          category: [ ... ],
          price:    [ ... ]
        }
~~~

Các nhánh có ba tính chất quan trọng:

- **Cùng đầu vào:** tất cả nhận tập document được chuyển tới `$facet`.
- **Độc lập:** nhánh này không thay đổi input hoặc kết quả của nhánh khác. `$limit` trong nhánh `products` không giới hạn số document mà nhánh `category` được thấy.
- **Không truyền nối trực tiếp giữa các nhánh:** không viết một sub-pipeline giả định đọc kết quả của nhánh khác ngay trong cùng `$facet`. Muốn kết hợp mảng đã tạo, đặt **stage sau `$facet`**.

**Đừng nhầm** `$facet` với việc gọi nhiều aggregation độc lập trong ứng dụng. `$facet` chia sẻ luồng đầu vào, trả một document tổng hợp, nhưng cũng có ràng buộc bộ nhớ và khả năng index khác với nhiều truy vấn riêng.

## 3. Chuẩn bị dữ liệu mongosh

Mở `mongosh` kết nối MongoDB, tạo database riêng:

~~~javascript
const lab = db.getSiblingDB("facet_memory_lab");

// Chỉ xóa collection dành cho bài thực hành.
lab.products.drop();

lab.products.insertMany([
  {
    _id: 101,
    name: "Laptop Air",
    category: "laptop",
    brand: "Nova",
    price: 1200,
    rating: 4.7,
    stock: 6,
    status: "active",
    tags: ["portable", "sale"]
  },
  {
    _id: 102,
    name: "Laptop Pro",
    category: "laptop",
    brand: "Nova",
    price: 1900,
    rating: 4.9,
    stock: 2,
    status: "active",
    tags: ["premium"]
  },
  {
    _id: 103,
    name: "Laptop Lite",
    category: "laptop",
    brand: "Orion",
    price: 800,
    rating: 4.0,
    stock: 0,
    status: "active",
    tags: ["budget"]
  },
  {
    _id: 104,
    name: "Phone Mini",
    category: "phone",
    brand: "Nova",
    price: 450,
    rating: 4.3,
    stock: 11,
    status: "active",
    tags: ["portable", "budget"]
  },
  {
    _id: 105,
    name: "Phone Max",
    category: "phone",
    brand: "Orion",
    price: 950,
    rating: 4.8,
    stock: 3,
    status: "active",
    tags: ["premium", "sale"]
  },
  {
    _id: 106,
    name: "Phone Old",
    category: "phone",
    brand: "Nova",
    price: 300,
    rating: 3.8,
    stock: 0,
    status: "archived",
    tags: ["sale"]
  },
  {
    _id: 107,
    name: "Keyboard",
    category: "accessory",
    brand: "Orion",
    price: 100,
    rating: 4.4,
    stock: 18,
    status: "active",
    tags: ["office"]
  },
  {
    _id: 108,
    name: "Mouse",
    category: "accessory",
    brand: "Nova",
    price: 60,
    rating: 4.2,
    stock: 40,
    status: "active",
    tags: ["office", "sale"]
  },
  {
    _id: 109,
    name: "Headphones",
    category: "accessory",
    brand: "Sonic",
    price: 180,
    rating: 4.6,
    stock: 8,
    status: "active",
    tags: ["portable"]
  },
  {
    _id: 110,
    name: "Monitor",
    category: "accessory",
    brand: "Sonic",
    price: 350,
    rating: 4.7,
    stock: 5,
    status: "active",
    tags: ["office", "premium"]
  },
  {
    _id: 111,
    name: "Tablet",
    category: "tablet",
    brand: "Nova",
    price: 700,
    rating: 4.5,
    stock: 4,
    status: "active",
    tags: ["portable"]
  },
  {
    _id: 112,
    name: "MongoDB Book",
    category: "book",
    brand: "Paper",
    price: 40,
    rating: 4.9,
    stock: 25,
    status: "active",
    tags: ["learning"]
  }
]);

lab.products.find({}, {
  name: 1,
  category: 1,
  brand: 1,
  price: 1,
  stock: 1,
  status: 1
}).sort({ _id: 1 });
~~~

Tổng cộng có **12 sản phẩm**, gồm **11 active** và **1 archived** (`_id = 106`).

Để có kết quả đối chiếu, tập active có:

| Danh mục | Số sản phẩm active |
| --- | ---: |
| accessory | 4 |
| laptop | 3 |
| phone | 2 |
| book | 1 |
| tablet | 1 |
| **Tổng** | **11** |

Với cùng tập này, tổng tồn kho là **122** đơn vị, trong đó **10 sản phẩm còn hàng** và **1 sản phẩm stock = 0**. Các giá `price` là số đơn giản để minh họa nhóm giá; hệ thống tài chính thực tế cần cân nhắc `Decimal128` và cách làm tròn.

## 4. Facet đầu tiên: danh sách và số lượng trên cùng tập lọc

Trang sản phẩm cần hai thứ:

- Mảng `data`: ba sản phẩm đắt nhất hiện đang active.
- Mảng `metadata`: tổng số sản phẩm active, **không chỉ đếm ba sản phẩm của trang**.

~~~javascript
const firstFacet = [
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            name: 1,
            category: 1,
            price: 1
          }
        }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  }
];

lab.products.aggregate(firstFacet).toArray();
~~~

Kết quả dạng:

~~~javascript
[
  {
    data: [
      { _id: 102, name: "Laptop Pro",
        category: "laptop", price: 1900 },
      { _id: 101, name: "Laptop Air",
        category: "laptop", price: 1200 },
      { _id: 105, name: "Phone Max",
        category: "phone", price: 950 }
    ],
    metadata: [
      { total: 11 }
    ]
  }
]
~~~

Chú ý **hai cấp mảng** trong đoạn code:

1. `aggregate(...).toArray()` trả mảng kết quả của cursor; ở đây gồm **một document**.
2. Document đó chứa các **mảng `data` và `metadata`** do các nhánh facet tạo.

`$limit: 3` nằm **bên trong nhánh `data`**, vì vậy nhánh `metadata` vẫn đếm đủ 11 document active.

### 4.1. Lỗi logic nếu đặt $limit quá sớm

Ví dụ sau **không đáp ứng mục tiêu tổng sản phẩm active**:

~~~javascript
// SAI nếu metadata cần tổng tất cả sản phẩm active.
lab.products.aggregate([
  { $match: { status: "active" } },
  { $sort: { price: -1, _id: 1 } },
  { $limit: 3 },
  {
    $facet: {
      data: [{ $project: { name: 1, price: 1 } }],
      metadata: [{ $count: "total" }]
    }
  }
]);
~~~

`$limit: 3` **ở trước `$facet`** làm **cả hai nhánh** chỉ nhìn thấy ba sản phẩm. Metadata khi đó là `total: 3`, không phải 11.

Quy tắc: **bộ lọc chung** đặt trước facet khi mọi nhánh phải cùng áp dụng; **giới hạn riêng** đặt trong đúng nhánh.

## 5. Nhiều nhánh thống kê: category, brand, giá và tồn kho

Một dashboard có thể cần nhiều chiều phân tích trong cùng một response. Chạy pipeline:

~~~javascript
const dashboard = [
  {
    $match: {
      status: "active"
    }
  },
  {
    $facet: {
      products: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            name: 1,
            category: 1,
            brand: 1,
            price: 1
          }
        }
      ],

      totalCount: [
        { $count: "total" }
      ],

      byCategory: [
        { $sortByCount: "$category" },
        { $sort: { count: -1, _id: 1 } }
      ],

      byBrand: [
        {
          $group: {
            _id: "$brand",
            count: { $sum: 1 }
          }
        },
        { $sort: { count: -1, _id: 1 } }
      ],

      priceRanges: [
        {
          $bucket: {
            groupBy: "$price",
            boundaries: [0, 100, 500, 1000, 2000],
            default: "other",
            output: { count: { $sum: 1 } }
          }
        }
      ],

      stockStats: [
        {
          $group: {
            _id: null,
            totalStock: { $sum: "$stock" },
            inStockProducts: {
              $sum: {
                $cond: [
                  { $gt: ["$stock", 0] },
                  1,
                  0
                ]
              }
            }
          }
        },
        {
          $project: {
            _id: 0,
            totalStock: 1,
            inStockProducts: 1
          }
        }
      ]
    }
  }
];

const result = lab.products.aggregate(dashboard).toArray();

printjson(result[0]);
~~~

Tất cả **sáu nhánh** nhận tập đầu vào gồm 11 sản phẩm active. Mỗi nhánh biến đổi **đầu ra của chính mình** và không làm thay đổi input của nhánh khác.

### 5.1. Nhánh byCategory và $sortByCount

`$sortByCount: "$category"` tương đương về ý tưởng với `$group` theo category, đếm số document rồi sort count giảm dần. Dữ liệu ví dụ có:

~~~javascript
[
  { _id: "accessory", count: 4 },
  { _id: "laptop", count: 3 },
  { _id: "phone", count: 2 },
  { _id: "book", count: 1 },
  { _id: "tablet", count: 1 }
]
~~~

Stage `$sort: { count: -1, _id: 1 }` được thêm sau `$sortByCount` để có **thứ tự ổn định khi các nhóm có cùng count**. Nếu chỉ cần biểu đồ không phụ thuộc thứ tự nhóm bằng nhau, stage sort phụ này có thể không cần thiết.

### 5.2. Nhánh byBrand và $group

Kết quả mong đợi:

| Brand | Số sản phẩm active |
| --- | ---: |
| Nova | 5 |
| Orion | 3 |
| Sonic | 2 |
| Paper | 1 |
| **Tổng** | **11** |

`$group` phù hợp khi cần thêm các accumulator như `$avg`, `$sum`, `$min`, `$max` hoặc `$addToSet`. Đừng viết `$group` chỉ để “phân nhánh”: **`$facet` phân nhánh, `$group` gom nhóm trong một nhánh**.

### 5.3. Nhánh priceRanges và $bucket

Giá trị `boundaries` là các cận tăng dần. Mỗi bucket chứa khoảng **bao gồm cận dưới, không bao gồm cận trên**:

| Bucket | Khoảng giá | Số sản phẩm |
| --- | --- | ---: |
| `_id: 0` | [0, 100) | 2 |
| `_id: 100` | [100, 500) | 4 |
| `_id: 500` | [500, 1000) | 3 |
| `_id: 1000` | [1000, 2000) | 2 |
| `"other"` | Ngoài các khoảng được khai báo | 0 (không có bucket other xuất hiện trong dữ liệu mẫu) |

Với giá đúng `100`, sản phẩm thuộc bucket `[100,500)`, không phải `[0,100)`. Khi `default: "other"` được khai báo, những giá không thuộc các khoảng (hoặc giá không hợp lệ theo logic grouping) có thể được đưa vào bucket mặc định.

Không dùng `$bucketAuto` nếu nghiệp vụ đã định nghĩa **các khoảng giá cố định**. `$bucketAuto` chọn ranh giới dựa trên phân bố dữ liệu và có thể không phù hợp với nhãn giá cần ổn định giữa các lần chạy.

### 5.4. Nhánh stockStats

Kết quả:

~~~javascript
stockStats: [
  {
    totalStock: 122,
    inStockProducts: 10
  }
]
~~~

`stockStats` chỉ có **một object** trong mảng vì `$group: { _id: null }` gộp toàn bộ đầu vào thành một nhóm.

**Kiểm tra quan trọng:** trường `inStockProducts` đếm số document có `stock > 0`; nó **không phải** tổng số đơn vị stock. Cặp giá trị `10` và `122` đo hai đại lượng khác nhau.

## 6. Giới hạn phạm vi từng nhánh nhưng không làm sai thống kê

Giả sử bộ lọc chung là **status active** và người dùng chọn chỉ xem hàng của brand Nova. Có hai nghiệp vụ khác nhau:

**Nghiệp vụ A — mọi facet đều theo brand Nova:** đặt `brand: "Nova"` trong `$match` trước `$facet`. Khi đó total, byCategory, priceRanges đều chỉ phản ánh Nova.

**Nghiệp vụ B — danh sách theo Nova nhưng bộ lọc brand vẫn cần hiện số lượng của tất cả brand active:** đặt điều kiện brand **trong nhánh data**, để nhánh thống kê brand nhận toàn bộ sản phẩm active.

Ví dụ nghiệp vụ B:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $match: { brand: "Nova" } },
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        { $project: { name: 1, brand: 1, price: 1 } }
      ],
      allBrands: [
        { $sortByCount: "$brand" }
      ]
    }
  }
]).toArray();
~~~

Nhánh `data` trả ba sản phẩm Nova đắt nhất (Laptop Pro, Laptop Air, Tablet), trong khi `allBrands` vẫn có Nova/Orion/Sonic/Paper. **Hai kết quả không mâu thuẫn**: các nhánh sử dụng **filter khác nhau sau khi nhận cùng đầu vào**.

Thiết kế filter trước hoặc trong facet phải dựa trên **contract của màn hình tìm kiếm**, không phải chỉ dựa trên hiệu năng.

## 7. Một $facet tạo document đầu ra như thế nào?

`$facet` thường tạo **một document** chứa một trường mảng cho mỗi nhánh. Từng nhánh có thể tạo 0, 1 hoặc nhiều document; chúng được đặt vào mảng tương ứng.

Ví dụ:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      highPrice: [
        { $match: { price: { $gt: 10000 } } },
        { $project: { name: 1 } }
      ],
      allActive: [
        { $count: "n" }
      ]
    }
  }
]).toArray();
~~~

Kết quả:

~~~javascript
[
  {
    highPrice: [],
    allActive: [ { n: 11 } ]
  }
]
~~~

Một nhánh không có document khớp → mảng rỗng `[]`, **không làm mất toàn bộ document kết quả**.

### 7.1. $count trên tập rỗng

~~~javascript
lab.products.aggregate([
  { $match: { status: "does-not-exist" } },
  {
    $facet: {
      data: [{ $limit: 3 }],
      metadata: [{ $count: "total" }]
    }
  }
]).toArray();
~~~

Kết quả có dạng:

~~~javascript
[
  {
    data: [],
    metadata: []
  }
]
~~~

Khi không có đầu vào, `$count` **không trả một document có total = 0**, mà trả **không document nào**. Vì thế `metadata` là mảng rỗng. API nên chuẩn hóa về số 0 khi cần.

### 7.2. Chuẩn hóa output sau $facet

Đối với REST API, đôi khi ta muốn:

~~~javascript
{
  data: [ /* ... */ ],
  total: 11
}
~~~

thay vì:

~~~javascript
{
  data: [ /* ... */ ],
  metadata: [{ total: 11 }]
}
~~~

Có thể đặt `$project` **sau** facet:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        { $project: { name: 1, price: 1 } }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  },
  {
    $project: {
      _id: 0,
      data: 1,
      total: {
        $ifNull: [
          { $arrayElemAt: ["$metadata.total", 0] },
          0
        ]
      }
    }
  }
]).toArray();
~~~

`$arrayElemAt` lấy phần tử đầu trong mảng các giá trị `metadata.total`, `$ifNull` dùng 0 khi không có giá trị. Đây là cách ánh xạ từ output facet sang contract response.

**Cảnh báo:** `$project` sau `$facet` giúp đơn giản response và loại mảng metadata không cần gửi, nhưng **không thể giải quyết lỗi nếu chính `$facet` đã vượt giới hạn bộ nhớ 100 MB hoặc document BSON vượt ngưỡng cho phép trước khi kịp được thu gọn**. Vấn đề kích thước phải được xử lý từ **đầu vào hoặc trong các nhánh**.

## 8. Giới hạn bộ nhớ riêng của $facet

Đây là trọng tâm của bài học.

Theo MongoDB Manual, **khi các stage trong `$facet` chạy, document kết quả do facet xây dựng bị giới hạn ở 100 MB**. Nếu `$facet` xây dựng một document vượt giới hạn này, MongoDB báo lỗi kiểu **`ExceededMemoryLimit`**.

Đặc biệt:

- **`$facet` không thể spill ra đĩa** để vượt giới hạn 100 MB của chính stage.
- Tùy chọn **`allowDiskUse: true` không thay đổi giới hạn 100 MB của `$facet`**.
- Document kết quả cuối cùng mà aggregation trả về còn phải đáp ứng **giới hạn BSON 16 MiB**.
- Vì đầu ra facet chứa **nhiều mảng trong cùng một document**, tổng dung lượng các mảng dễ trở thành nút thắt khi số lượng kết quả lớn.

### 8.1. Hai ngưỡng không giống nhau

| Giới hạn | Áp dụng ở đâu? | Có thể dùng allowDiskUse để vượt? |
| --- | --- | --- |
| **100 MB** | Document trung gian do `$facet` xây dựng khi chạy | **Không**: `$facet` không spill |
| **16 MiB BSON** | Mỗi document kết quả cuối của aggregation | **Không** |
| **Giới hạn bộ nhớ của stage khác** | Ví dụ `$sort`, `$group`, `$bucket` tùy phiên bản | **Có thể**, nếu stage hỗ trợ spill và cấu hình cho phép |
| **Giới hạn RAM client** | Khi gọi `toArray()` hoặc giữ response lớn | Tùy ứng dụng; không được MongoDB tự loại bỏ |

**Không hiểu sai rằng mỗi nhánh có 100 MB riêng và có thể cộng hàng chục nhánh thành output không giới hạn.** Nhiều nhánh được **đóng gói vào cùng document của `$facet`**, vì vậy phải kiểm soát tổng kích thước của chúng.

**Không hiểu sai rằng 100 MB là kích thước document cuối cho phép trả về client.** MongoDB chỉ cho phép **16 MiB cho một BSON result document**; giá trị trung gian lớn hơn 16 MiB có thể tồn tại trong quá trình pipeline ở những trường hợp được hỗ trợ, nhưng phải được thu gọn hợp lệ trước đầu ra cuối và không vượt 100 MB ở facet.

### 8.2. Tại sao $facet dễ chạm giới hạn hơn các truy vấn nhiều dòng?

So sánh:

~~~text
Không dùng $facet:
  aggregate() -> doc1 -> doc2 -> doc3 -> ... -> cursor
  Mỗi result document có giới hạn BSON riêng.
  Cursor có thể đọc theo batch.

Dùng $facet:
  aggregate() -> {
    branchA: [doc1, doc2, doc3, ...],
    branchB: [x1, x2, x3, ...]
  }
  Toàn bộ các phần tử nằm trong MỘT BSON document.
~~~

Nếu nhánh `products` trả toàn bộ vài trăm nghìn sản phẩm gồm ảnh, mô tả dài và tags, còn nhánh `byCategory` chứa hàng nghìn nhóm, output facet có thể lớn hơn 16 MiB **dù client chỉ dùng `batchSize: 1`**.

Cursor batch size điều chỉnh **số document kết quả mỗi lần truyền**, **không chia nhỏ các mảng nằm bên trong một document facet**. `toArray()`, `batchSize`, hay `limit()` đặt **sau** facet không phải giải pháp cho một document facet quá lớn.

### 8.3. allowDiskUse khác gì?

Ở aggregation thông thường, các stage chặn như `$sort` hoặc `$group` có thể có ngưỡng bộ nhớ và, khi đủ điều kiện, cho phép ghi file tạm ra đĩa nếu `allowDiskUse` được bật. Từ MongoDB 6.0, cấu hình `allowDiskUseByDefault` ảnh hưởng hành vi mặc định của các stage hỗ trợ spill.

Ví dụ:

~~~javascript
lab.products.aggregate(
  [
    { $match: { status: "active" } },
    { $sort: { price: -1 } },
    { $group: { _id: "$category", count: { $sum: 1 } } }
  ],
  { allowDiskUse: true }
);
~~~

Một số stage trong pipeline **ngoài facet** có thể sử dụng bộ nhớ/đĩa theo quy tắc riêng. Nhưng lệnh:

~~~javascript
// KHÔNG biến $facet thành stage có thể spill.
lab.products.aggregate(
  [
    {
      $facet: {
        allDocuments: [
          { $project: { name: 1, category: 1, price: 1 } }
        ]
      }
    }
  ],
  { allowDiskUse: true }
);
~~~

**không có ngoại lệ** cho phép facet giữ một mảng document vượt giới hạn của nó. Nếu cần trả rất nhiều document, thiết kế **cursor truyền nhiều document** hoặc tách nhánh báo cáo khỏi nhánh danh sách thay vì gói tất cả vào một document.

### 8.4. Ngưỡng theo phiên bản và các giới hạn khác

Ngoài giới hạn riêng của facet, MongoDB còn có các giới hạn tổng quát về kích thước document, số lượng pipeline stage, bộ nhớ của từng stage và ở những phiên bản mới là **giới hạn bộ nhớ trên toàn operation**. Chẳng hạn MongoDB 9.0 có cơ chế giới hạn bộ nhớ theo operation được tài liệu mô tả.

**Không dùng một thông số server chung như `allowDiskUseByDefault` để suy ra rằng `$facet` được phép spill.** Cần đọc đúng tài liệu phiên bản đang chạy và phân biệt:

- Budget/bộ nhớ trung gian của chính `$facet`.
- Bộ nhớ của stage `$sort`/`$group` theo quy tắc riêng.
- Giới hạn một BSON result document.
- Bộ nhớ của client khi nhận kết quả.
- Các giới hạn operation và tài nguyên deployment.

## 9. Một ví dụ dễ thất bại vì bộ nhớ

Giả sử collection thật có 500.000 sản phẩm, mỗi document có mô tả dài, ảnh, thông số và metadata. Pipeline sau **gói toàn bộ document** vào một nhánh:

~~~javascript
// CHỐNG CHỈ ĐỊNH trên dữ liệu lớn: output facet có thể quá lớn.
db.bigProducts.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      allRows: [
        { $project: { _id: 1, name: 1, description: 1, images: 1 } }
      ],
      total: [
        { $count: "n" }
      ]
    }
  }
], { allowDiskUse: true });
~~~

Vấn đề:

1. Nhánh `allRows` tạo **mảng chứa mọi sản phẩm active**.
2. Document facet giữ `allRows` cộng `total`, cùng overhead của BSON.
3. Số phần tử và kích thước mỗi phần tử có thể đẩy document facet lên trên 16 MiB và/hoặc 100 MB.
4. `allowDiskUse: true` không làm `$facet` an toàn với việc giữ toàn bộ mảng.
5. Nếu máy chủ báo lỗi, giảm `batchSize` của cursor sẽ không làm document facet nhỏ hơn.

Thay đổi cần có ở **mô hình trả kết quả**, không phải chỉ bật thêm một option.

### 9.1. Giới hạn nhánh danh sách thật sự

~~~javascript
db.bigProducts.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      page: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $limit: 20 },
        {
          $project: {
            _id: 1,
            name: 1,
            category: 1,
            price: 1
          }
        }
      ],
      total: [
        { $count: "n" }
      ]
    }
  }
]);
~~~

Nhánh `page` chỉ giữ tối đa 20 document **nhỏ gọn**, còn nhánh `total` chỉ tạo một document đếm. Hai thay đổi này giảm đáng kể kích thước output facet.

Tuy nhiên, `$sort` nằm trong nhánh page có thể vẫn phải xử lý lượng input lớn và không tự dùng được index nằm trên collection nguồn từ bên trong facet. Muốn tối ưu sort, xem mục về index và đánh đổi giữa một facet chung với hai query riêng.

### 9.2. Nhánh thống kê chỉ giữ dữ liệu tổng hợp

Đừng viết:

~~~javascript
// DỄ PHÌNH TO: gộp nguyên document vào một mảng.
{
  $group: {
    _id: "$category",
    allProducts: { $push: "$$ROOT" }
  }
}
~~~

nếu chỉ cần số sản phẩm mỗi category. Thay bằng:

~~~javascript
{
  $group: {
    _id: "$category",
    count: { $sum: 1 }
  }
}
~~~

Nếu cần ví dụ sản phẩm tiêu biểu cho mỗi category, có thể giới hạn mẫu có ý nghĩa theo phiên bản và quy tắc sort, nhưng tránh `$push: "$$ROOT"` cho toàn bộ tài liệu. Một branch group trả rất ít document **vẫn có thể chứa mảng rất lớn bên trong mỗi document**.

## 10. Tối ưu theo thứ tự: giảm input, giảm field, giảm output

Có ba nơi cần giảm chi phí:

~~~text
Collection
   |
   v
[1] $match sớm và $project phù hợp
   |
   v
$facet
  |-- [2] branch A: $sort + $limit + $project
  |-- [2] branch B: $group -> chỉ count/sum/avg
  |-- [2] branch C: $bucket -> output ngắn
   |
   v
[3] $project/$set cuối -> response cần thiết
~~~

### 10.1. Lọc chung trước facet

~~~javascript
lab.products.aggregate([
  {
    $match: {
      status: "active",
      price: { $gte: 100 }
    }
  },
  {
    $facet: {
      byCategory: [{ $sortByCount: "$category" }],
      total: [{ $count: "n" }]
    }
  }
]);
~~~

Chỉ những sản phẩm active giá từ 100 mới vào facet. Việc này có thể làm giảm số document cần buffer/xử lý và tạo cơ hội dùng index cho filter.

Nếu một bộ lọc chỉ thuộc riêng một nhánh, đừng đưa nó ra ngoài một cách máy móc: như vậy sẽ làm sai các nhánh khác.

### 10.2. Project bỏ field nặng trước facet khi tất cả nhánh không cần

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $project: {
      name: 1,
      category: 1,
      brand: 1,
      price: 1,
      stock: 1
    }
  },
  {
    $facet: {
      byCategory: [{ $sortByCount: "$category" }],
      byBrand: [{ $sortByCount: "$brand" }],
      totalStock: [
        {
          $group: {
            _id: null,
            n: { $sum: "$stock" }
          }
        }
      ]
    }
  }
]);
~~~

Lúc này các nhánh không nhận `tags`, `description`, `images` hoặc thông tin không cần thiết. Nhưng **đừng loại `price` nếu nhánh khác còn cần tính giá**, và đừng giả định rằng đặt `$project` quá sớm luôn nhanh hơn vì MongoDB optimizer có thể tự giảm field khi thích hợp.

### 10.3. Giới hạn trong đúng nhánh

~~~javascript
{
  $facet: {
    topProducts: [
      { $sort: { price: -1, _id: 1 } },
      { $limit: 5 },
      { $project: { name: 1, price: 1 } }
    ],
    byCategory: [
      { $sortByCount: "$category" }
    ]
  }
}
~~~

Giới hạn trong `topProducts` không ảnh hưởng số lượng theo category.

Nếu sắp xếp theo **trường không có khóa phá hòa**, những sản phẩm có giá bằng nhau có thể đổi thứ tự giữa các lần chạy. Dùng `_id` như khóa phụ khi cần kết quả ổn định.

### 10.4. Sau facet chỉ giữ dữ liệu API cần

~~~javascript
{
  $project: {
    _id: 0,
    page: 1,
    total: {
      $ifNull: [
        { $arrayElemAt: ["$metadata.total", 0] },
        0
      ]
    }
  }
}
~~~

Đây là bước định dạng response, **không thay thế việc giới hạn mảng ngay trong facet**. Một branch đã vượt 100 MB thì stage sau không có cơ hội sửa lỗi.

## 11. $facet và index: vị trí stage rất quan trọng

Theo MongoDB Manual:

- Nếu **`$facet` là stage đầu tiên**, nó sẽ thực hiện **COLLSCAN** và không dùng index để chọn input.
- Nếu có các stage trước `$facet` đã dùng index (ví dụ `$match` hoặc `$sort`), `$facet` **không buộc server quét lại toàn bộ collection** từ đầu.
- **Các nhánh bên trong facet không tự lấy lại quyền truy cập collection/index như những query độc lập.** Chúng xử lý dòng document được chuyển vào facet.

### 11.1. Tạo index hỗ trợ filter chung

~~~javascript
lab.products.createIndex(
  { status: 1, price: -1, _id: 1 },
  { name: "ix_status_price_id" }
);
~~~

Một pipeline có thể sử dụng index:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  { $sort: { price: -1, _id: 1 } },
  {
    $facet: {
      page: [
        { $limit: 3 },
        { $project: { name: 1, price: 1 } }
      ],
      total: [
        { $count: "n" }
      ]
    }
  }
]);
~~~

Ưu điểm: `$match` và `$sort` đứng **trước `$facet`**, có cơ hội sử dụng compound index của collection. Nhược điểm: **toàn bộ input của mọi nhánh** phải đi qua stage `$sort`, kể cả `total` không quan tâm thứ tự. Nếu có hàng triệu document, cần đo chi phí, không mặc định một sort trước facet luôn tốt hơn.

### 11.2. Sort trong nhánh khác sort trước facet

So sánh:

~~~javascript
// A. Sort nằm trong nhánh:
[
  { $match: { status: "active" } },
  {
    $facet: {
      page: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 }
      ],
      total: [{ $count: "n" }]
    }
  }
]
~~~

với:

~~~javascript
// B. Sort đặt trước facet:
[
  { $match: { status: "active" } },
  { $sort: { price: -1, _id: 1 } },
  {
    $facet: {
      page: [{ $limit: 3 }],
      total: [{ $count: "n" }]
    }
  }
]
~~~

Hai pipeline cho cùng trang và tổng trong bộ dữ liệu mẫu, nhưng **kế hoạch thực thi và bộ nhớ có thể khác**. Với B, index có thể hỗ trợ sort ở ngoài; với A, sort nội bộ branch thường phải dựa trên input đã đến facet. Nếu chỉ nhánh page cần sort, A tránh áp sort ở pipeline chung, nhưng không tận dụng index theo cách tương tự. Phải dùng `explain()` và metric trên workload thật.

### 11.3. Xem explain

~~~javascript
lab.products.explain("executionStats").aggregate([
  { $match: { status: "active" } },
  { $sort: { price: -1, _id: 1 } },
  {
    $facet: {
      page: [{ $limit: 3 }],
      total: [{ $count: "n" }]
    }
  }
]);
~~~

Quan sát kế hoạch các stage trước facet, loại scan, `totalKeysExamined`, `totalDocsExamined` và dấu hiệu sort/bộ nhớ được báo tùy server version.

Dữ liệu lab chỉ 12 document, optimizer có thể chọn **COLLSCAN** thay vì index vì chi phí quét nhỏ. Đừng kết luận chỉ dựa trên một thử nghiệm tí hon. Việc `explain` hiển thị các stage được tối ưu hóa không nhất thiết trùng từng stage trong source pipeline.

## 12. Các stage bị cấm trong sub-pipeline của $facet

Không phải stage aggregation nào cũng có thể nằm bên trong một nhánh facet. Theo tài liệu MongoDB, các stage sau **không được** đặt bên trong `$facet`:

- `$collStats`
- `$facet`
- `$geoNear`
- `$indexStats`
- `$out`
- `$merge`
- `$planCacheStats`
- `$search`
- `$searchMeta`
- `$vectorSearch`

Đặc biệt:

1. **Không lồng một `$facet` thứ hai** trực tiếp bên trong một nhánh facet.
2. **Không ghi ra collection** bằng `$out` hoặc `$merge` trong sub-pipeline của facet.
3. **Không đặt `$search` hoặc `$vectorSearch` bên trong nhánh facet**. Nếu yêu cầu tìm kiếm, cần thiết kế bước truy vấn Search ở vị trí được hỗ trợ, sau đó facet trên đầu vào hoặc chia quy trình khác.
4. Các stage meta/thống kê server như `$indexStats` không phải sub-pipeline hợp lệ.

Ví dụ sai:

~~~javascript
// SAI: $facet lồng bên trong $facet.
lab.products.aggregate([
  {
    $facet: {
      nested: [
        {
          $facet: {
            categories: [
              { $sortByCount: "$category" }
            ]
          }
        }
      ]
    }
  }
]);
~~~

Nếu cần xử lý kết quả của nhiều nhánh, đặt stage **sau `$facet`**:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      byCategory: [
        { $sortByCount: "$category" }
      ],
      total: [
        { $count: "n" }
      ]
    }
  },
  {
    $set: {
      totalValue: {
        $ifNull: [
          { $arrayElemAt: ["$total.n", 0] },
          0
        ]
      }
    }
  },
  {
    $project: {
      byCategory: 1,
      totalValue: 1,
      _id: 0
    }
  }
]);
~~~

Đoạn này tính thêm `totalValue` từ mảng `total` **sau khi facet hoàn thành**, không cố tham chiếu mảng của nhánh khác khi nhánh đang chạy.

## 13. $bucket, $bucketAuto và $sortByCount trong facet

Những stage thường đi với `$facet` để xây giao diện lọc đa chiều:

| Stage trong nhánh | Mục đích | Ví dụ |
| --- | --- | --- |
| `$sortByCount` | Đếm tần suất giá trị | Số sản phẩm mỗi brand |
| `$bucket` | Nhóm theo những khoảng có ranh giới định sẵn | Giá 0–99, 100–499, 500–999 |
| `$bucketAuto` | Tạo các nhóm theo phân bố dữ liệu | Chia thành khoảng giá có kích thước nhóm gần nhau |
| `$group` | Thống kê tự do theo khóa | Tổng tồn, trung bình giá, đếm theo category |
| `$match` | Lọc riêng một nhánh | Chỉ hàng còn trong kho |
| `$project` | Làm nhỏ phần tử mảng kết quả | Chỉ giữ id, tên, giá |
| `$sort`/`$limit` | Lấy top N trong một nhánh | Top 10 brand hoặc sản phẩm |

### 13.1. Dùng $bucketAuto khi ranh giới không cố định

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      dynamicPrice: [
        {
          $bucketAuto: {
            groupBy: "$price",
            buckets: 3,
            output: {
              count: { $sum: 1 },
              minPrice: { $min: "$price" },
              maxPrice: { $max: "$price" }
            }
          }
        }
      ]
    }
  }
]);
~~~

`$bucketAuto` cố gắng chia dữ liệu thành số bucket yêu cầu, với ranh giới phụ thuộc dữ liệu và tính khả dụng của độ chi tiết. Số lượng bucket thực tế có thể ít hơn nếu không đủ giá trị phân biệt. **Không hardcode giá trị ranh giới** của `$bucketAuto` như một contract cho frontend nếu dữ liệu thay đổi thường xuyên.

### 13.2. Tìm kiếm đa chiều và số lượng theo bộ lọc

Giả sử frontend lọc chung `status: "active"` và `category: "accessory"`. Nếu đặt cả hai trước facet, kết quả byCategory chỉ còn accessory, không cho biết các category khác.

Khi xây sidebar lọc như thương mại điện tử, cần quyết định **self-excluding facets**: một facet category có thể đếm theo tất cả filter **trừ chính filter category**, trong khi facet brand có thể tính theo tất cả filter trừ filter brand. Tình huống này đòi hỏi **các nhánh có filter riêng** hoặc các truy vấn riêng, chứ không chỉ một `$match` chung.

Ví dụ:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      products: [
        { $match: { category: "accessory", brand: "Nova" } },
        { $sort: { price: -1, _id: 1 } },
        { $limit: 10 },
        { $project: { name: 1, category: 1, brand: 1, price: 1 } }
      ],
      categories: [
        // Có filter brand, nhưng không giới hạn category.
        { $match: { brand: "Nova" } },
        { $sortByCount: "$category" }
      ],
      brands: [
        // Có filter category, nhưng không giới hạn brand.
        { $match: { category: "accessory" } },
        { $sortByCount: "$brand" }
      ]
    }
  }
]);
~~~

Trong đoạn này:

- Nhánh `products` trả chỉ sản phẩm vừa accessory vừa Nova (Mouse).
- Nhánh `categories` đếm category của tất cả sản phẩm Nova active.
- Nhánh `brands` đếm brand của tất cả accessory active.

Các số không được kỳ vọng cộng lại thành một tổng chung duy nhất nếu **phạm vi filter khác nhau**. Đây là đặc điểm cố ý của thiết kế faceted search.

## 14. $facet cho phân trang: ưu điểm và rủi ro

Một mẫu phổ biến:

~~~javascript
const page = 2;
const pageSize = 3;
const skip = (page - 1) * pageSize;

lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $skip: skip },
        { $limit: pageSize },
        { $project: { name: 1, price: 1 } }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  }
]);
~~~

Với 11 sản phẩm active, trang 2 theo giá giảm dần là:

~~~text
_id 103: Laptop Lite   price 800
_id 111: Tablet        price 700
_id 104: Phone Mini    price 450
~~~

Tổng metadata vẫn là 11.

### 14.1. Không đánh đồng skip trong facet với index-based seek

`$skip` ở nhánh `data` chỉ bỏ qua các result document đã được đưa tới nhánh. Với offset rất sâu, nó không có lợi thế như keyset pagination dùng compound index ở nguồn.

Nếu dữ liệu rất lớn và người dùng cuộn qua hàng trăm trang, có thể tốt hơn khi:

- Dùng **keyset pagination** trên một truy vấn `find()` hoặc `aggregate()` đơn giản, với sort ổn định và compound index phù hợp.
- Tính tổng hoặc facets bằng truy vấn riêng, có thể cache.
- Chỉ dùng `$facet` khi mong muốn thật sự là **trả nhiều chiều thống kê từ cùng tập input** và kích thước output được khống chế.

Không phải vì một lệnh chứa cả `data` và `count` thì nó luôn nhanh hơn hai lệnh tách biệt; hiệu năng thực tế phụ thuộc dữ liệu, index, độ lớn trang và quy tắc cache.

### 14.2. Tránh sort thiếu khóa phụ

Nếu nhiều sản phẩm có cùng giá, `$sort: { price: -1 }` không bảo đảm thứ tự giữa những sản phẩm đồng giá. Khi dùng `$skip` và `$limit` trong phân trang, nên thêm khóa phụ có tính duy nhất:

~~~javascript
{ $sort: { price: -1, _id: 1 } }
~~~

Điều đó giúp kết quả có thứ tự xác định cho một tập dữ liệu không đổi. Tuy nhiên, việc chèn/xóa hoặc cập nhật giá giữa các request vẫn có thể khiến offset pagination lặp/bỏ sót sản phẩm.

## 15. Tính tổng và thống kê trên các nhánh mà không giữ bản ghi gốc

Những statistic branch thường chỉ cần một số giá trị tổng hợp. Ví dụ tổng giá niêm yết của các sản phẩm active:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      totals: [
        {
          $group: {
            _id: null,
            productCount: { $sum: 1 },
            totalListPrice: { $sum: "$price" },
            averagePrice: { $avg: "$price" }
          }
        },
        {
          $project: {
            _id: 0,
            productCount: 1,
            totalListPrice: 1,
            averagePrice: 1
          }
        }
      ],
      inStock: [
        { $match: { stock: { $gt: 0 } } },
        { $count: "n" }
      ]
    }
  }
]);
~~~

Từ bộ dữ liệu:

- `productCount = 11`.
- `totalListPrice = 6730`.
- `averagePrice` xấp xỉ **611,82**.
- `inStock = [{ n: 10 }]`.

Nhánh totals tạo một document nhỏ; nhánh inStock cũng tạo một document nhỏ. Đây là dạng `$facet` thích hợp cho dữ liệu lớn nếu lọc chung đủ chọn lọc và các phép tổng hợp nằm trong giới hạn tài nguyên.

**Phân biệt phép đo:** tổng giá niêm yết của một sản phẩm trong catalog **không phải doanh thu bán hàng**; bảng catalog không có thông tin đơn hàng đã thanh toán. Nếu muốn tính doanh thu, cần nguồn dữ liệu giao dịch và quy tắc xử lý hoàn tiền, thuế, đơn hủy...

## 16. Thiết kế nhiều bước sau $facet mà không làm phình document

Output `$facet` là một object có các mảng, nên có thể dùng aggregation expressions sau đó.

### 16.1. Lấy chỉ số đếm từ mảng metadata

~~~javascript
[
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        { $project: { name: 1, price: 1 } }
      ],
      metadata: [
        { $count: "n" }
      ]
    }
  },
  {
    $set: {
      total: {
        $ifNull: [
          { $arrayElemAt: ["$metadata.n", 0] },
          0
        ]
      }
    }
  },
  {
    $unset: "metadata"
  }
]
~~~

### 16.2. Kết hợp kết quả hai nhánh sau khi chúng đã tạo ra

Ví dụ chỉ tạo hai nhánh count và tính tỉ lệ có hàng:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      total: [{ $count: "n" }],
      available: [
        { $match: { stock: { $gt: 0 } } },
        { $count: "n" }
      ]
    }
  },
  {
    $set: {
      totalN: {
        $ifNull: [{ $arrayElemAt: ["$total.n", 0] }, 0]
      },
      availableN: {
        $ifNull: [{ $arrayElemAt: ["$available.n", 0] }, 0]
      }
    }
  },
  {
    $project: {
      _id: 0,
      totalN: 1,
      availableN: 1,
      availabilityRatio: {
        $cond: [
          { $gt: ["$totalN", 0] },
          { $divide: ["$availableN", "$totalN"] },
          null
        ]
      }
    }
  }
]);
~~~

Kết quả cho lab:

~~~javascript
{
  totalN: 11,
  availableN: 10,
  availabilityRatio: 0.9090909090909091
}
~~~

Trong trường hợp không có sản phẩm active, công thức đã tránh chia cho 0, trả `availabilityRatio: null` (hoặc giá trị khác theo contract nếu nghiệp vụ muốn).

### 16.3. Không coi stage sau facet là pipeline trên từng phần tử mảng

Sau `$facet`, một stage `$project` hoặc `$match` nhận **một document chứa mảng**, **không phải từng sản phẩm ban đầu**. Muốn xử lý từng phần tử trong `data`, cần dùng biểu thức mảng như `$map`/`$filter` hoặc `$unwind` khi thật sự cần đưa mảng trở lại dòng document.

Ví dụ đổi các item trong mảng `data` thành object ngắn:

~~~javascript
{
  $project: {
    _id: 0,
    names: {
      $map: {
        input: "$data",
        as: "product",
        in: "$$product.name"
      }
    }
  }
}
~~~

Đừng thêm `$unwind: "$data"` chỉ để hiển thị tên nếu có thể dùng `$map`: `$unwind` biến một document facet thành nhiều document, thay đổi contract của API và cần kiểm soát kích thước/giới hạn BSON.

## 17. Phân biệt giới hạn 100 MB với 16 MiB qua kịch bản

### Kịch bản A — Branch chỉ có nhóm count nhỏ

~~~javascript
{
  $facet: {
    byCategory: [{ $sortByCount: "$category" }],
    total: [{ $count: "n" }]
  }
}
~~~

Số category có giới hạn và output nhỏ. Đây là cách dùng điển hình, phù hợp.

### Kịch bản B — Branch giữ hàng trăm nghìn document

~~~javascript
{
  $facet: {
    allRows: [{ $project: { name: 1, description: 1 } }]
  }
}
~~~

Output là một mảng khổng lồ nằm trong một BSON document. Có nguy cơ vượt 16 MiB và 100 MB. Không cứu bằng `allowDiskUse` hay cursor batch size.

### Kịch bản C — Group tạo một mảng $push rất lớn

~~~javascript
{
  $facet: {
    grouped: [
      {
        $group: {
          _id: "$category",
          allIds: { $push: "$_id" }
        }
      }
    ]
  }
}
~~~

Mặc dù số nhóm ít, mỗi nhóm có thể mang một mảng `allIds` rất dài. `$push` và `$facet` đều có giới hạn bộ nhớ liên quan riêng; `allowDiskUse` không đảm bảo tránh lỗi với accumulator `$push` lớn. Nếu chỉ cần số lượng, thay `$push` bằng `$sum: 1`.

### Kịch bản D — Thêm $limit ở phía sau

~~~javascript
[
  {
    $facet: {
      allRows: [
        { $project: { name: 1, description: 1 } }
      ]
    }
  },
  { $limit: 1 }
]
~~~

`$limit: 1` ở cuối pipeline chỉ giới hạn **số document của luồng đầu ra**, không giảm kích thước mảng `allRows` bên trong document facet. Vì `$facet` vốn đã tạo một document, `$limit: 1` gần như không giúp gì cho kích thước.

**Giải pháp:** Đặt `$limit` **bên trong nhánh allRows**, đồng thời `$project` bỏ trường nặng không cần trả.

### Kịch bản E — Cắt bớt mảng ở stage sau

~~~javascript
[
  {
    $facet: {
      allRows: [
        { $project: { name: 1, description: 1 } }
      ]
    }
  },
  {
    $project: {
      allRows: { $slice: ["$allRows", 10] }
    }
  }
]
~~~

Nếu facet đã vượt giới hạn 100 MB trong lúc xây dựng, stage sau không thể cứu. **Đừng dựa vào việc cắt output sau facet để xử lý một luồng đầu vào quá lớn**. Giới hạn và rút gọn trong nhánh ngay từ đầu.

## 18. Đo kích thước BSON trước khi hệ thống chạm ngưỡng

Khi output nhỏ và hợp lệ, có thể dùng expression `$bsonSize` để đo xấp xỉ kích thước của document đang được tạo:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 3 },
        { $project: { name: 1, category: 1, price: 1 } }
      ],
      metadata: [{ $count: "total" }]
    }
  },
  {
    $project: {
      _id: 0,
      data: 1,
      metadata: 1,
      facetDocumentBytes: { $bsonSize: "$$ROOT" }
    }
  }
]);
~~~

`facetDocumentBytes` là kích thước BSON của document đầu vào cho stage `$project`, được tính **sau `$facet`**. Phép đo này hữu ích để quan sát độ tăng của response khi pageSize hoặc số bucket tăng.

Nhưng:

- Nó **không chạy được để “đo document lỗi”** nếu `$facet` đã thất bại vì 100 MB hoặc BSON quá lớn trước đó.
- Kích thước document output cuối có thể khác chút ít do field đo được thêm vào.
- Trong một phiên bản MongoDB cũ không hỗ trợ `$bsonSize`, cần cách đo khác hoặc đo size tại ứng dụng.
- Không lấy giới hạn 16 MiB làm mục tiêu thiết kế “đạt sát ngưỡng”; response lớn còn tăng latency, RAM và chi phí truyền.

**Khuyến nghị:** Đặt giới hạn pageSize, số lượng bucket và các field trả về từ API ở mức nhỏ có chủ đích.

## 19. Khi nào nên tách $facet thành nhiều truy vấn?

`$facet` giúp tổ chức nhiều phép tổng hợp trên cùng input, nhưng có những tình huống tách truy vấn mang lại lợi ích:

| Tình huống | Vì sao cần cân nhắc tách? |
| --- | --- |
| Danh sách sản phẩm phân trang rất sâu | Keyset/compound index ở query riêng có thể hiệu quả hơn sort trong facet |
| Facet có hàng nghìn hoặc hàng triệu bucket | Một output document rất lớn, rủi ro 16 MiB |
| Có nhánh cần `$search`/`$vectorSearch` đặc biệt | Những stage này không được đặt trong sub-pipeline `$facet` |
| Mỗi nhánh cần tập index khác nhau | Query riêng có thể tận dụng index theo filter/sort chuyên biệt |
| Counts ít thay đổi nhưng danh sách đổi liên tục | Cache counts/facets, chỉ đọc lại danh sách |
| Có nhánh xử lý lâu hoặc dùng nhiều bộ nhớ | Tách để kiểm soát timeout/tài nguyên và khả năng retry |
| Cần stream toàn bộ dữ liệu | Không nên gói thành một mảng của một document facet |
| Cần kết quả nhất quán tuyệt đối từ nhiều phép ghi/chuyển trạng thái | Cần thiết kế read concern/snapshot hoặc transaction, không chỉ chọn một API |

### 19.1. Ví dụ tách data và count

~~~javascript
const filter = {
  status: "active"
};

// Truy vấn trang dữ liệu, có thể tận dụng index sort.
const data = lab.products.find(
  filter,
  { name: 1, category: 1, brand: 1, price: 1 }
).sort({ price: -1, _id: 1 })
 .limit(3)
 .toArray();

// Truy vấn tổng đếm độc lập.
const total = lab.products.countDocuments(filter);

printjson({ data, total });
~~~

Đổi lại, dữ liệu có thể thay đổi giữa hai lệnh. Nếu yêu cầu tất cả phép đọc phải nhìn một snapshot nhất quán, cần đánh giá session/read concern/transaction theo phiên bản và topology, thay vì giả định hai lệnh luôn đồng thời nhất quán.

**Đừng mặc định `$facet` đồng nghĩa với “rẻ hơn vì quét nguồn một lần”.** Nó có thể giảm việc đọc input nhiều lần nhưng tạo nhánh sort/group lớn, không dùng index trong nhánh và bị giới hạn một BSON document. Benchmark theo workload thực mới cho kết luận.

## 20. Giới hạn khi cùng dữ liệu thay đổi và yêu cầu nhất quán

Một `$facet` sử dụng cùng tập input trong **một aggregation invocation**, giúp các nhánh dựa trên cùng luồng document được cung cấp tới stage. Nhưng điều này không phải tuyên bố rằng MongoDB tự cấp **snapshot isolation** cho mọi aggregation trong mọi cấu hình.

Nếu có client cập nhật/chèn/xóa đồng thời:

- Các thuộc tính nhất quán của một lần aggregate phụ thuộc read concern và topology.
- Hai lần chạy cùng một pipeline có thể cho kết quả khác nhau.
- Chạy một facet rồi một query khác ngay sau đó không đảm bảo hai kết quả nhìn cùng trạng thái dữ liệu.
- Nếu nghiệp vụ yêu cầu tính toán từ một thời điểm nhất định, cần thiết kế read concern/snapshot hoặc cơ chế lưu phiên bản dữ liệu theo mức bảo đảm mong muốn.

Với dashboard số liệu thay đổi nhanh, thường chấp nhận eventual consistency theo vài giây. Với báo cáo tài chính cần đối soát chính xác, nên có mô hình chốt kỳ và nguồn dữ liệu bất biến/được version hóa thay vì phụ thuộc vào một truy vấn `$facet` tức thời.

## 21. Chẩn đoán vấn đề bằng từng nhánh riêng

Khi output facet không đúng, có thể chạy **một nhánh dưới dạng aggregation độc lập** với cùng các stage lọc chung.

Ví dụ kiểm chứng byCategory:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  { $sortByCount: "$category" },
  { $sort: { count: -1, _id: 1 } }
]).toArray();
~~~

Kiểm chứng byBrand:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  { $group: { _id: "$brand", count: { $sum: 1 } } },
  { $sort: { count: -1, _id: 1 } }
]).toArray();
~~~

Kiểm chứng total:

~~~javascript
lab.products.countDocuments({ status: "active" });
// 11
~~~

Nếu các nhánh riêng đúng mà output facet thiếu một field, hãy xem:

1. Tên field của nhánh đã khai báo đúng chưa?
2. Có stage `$project` hoặc `$unset` sau facet xóa mảng đó không?
3. Có filter chung đưa ra ngoài facet làm giảm input không?
4. Có stage `$limit` đặt nhầm ở pipeline chung không?
5. Nhánh có tạo mảng rỗng vì không có document khớp không?
6. Có dùng `$group` nhưng hiểu nhầm rằng nó giữ thứ tự đầu ra không?
7. Có một nhánh giữ quá nhiều document làm facet vượt giới hạn bộ nhớ không?

**Cẩn trọng về chi phí:** chạy từng nhánh riêng nhiều lần có thể tốn scan và CPU hơn một facet. Đây là kỹ thuật chẩn đoán trên dữ liệu có kiểm soát, không nên chạy tự động hàng trăm lần trên cluster production.

### 21.1. Kiểm chứng tổng các bucket

Trong bộ dữ liệu active:

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [0, 100, 500, 1000, 2000],
      default: "other",
      output: { count: { $sum: 1 } }
    }
  }
]).toArray();
~~~

Kết quả có số lượng `2 + 4 + 3 + 2 = 11`. Nếu tổng bucket nhỏ hơn totalCount, có thể do ranh giới thiếu `default`, bộ lọc khác nhau hoặc dữ liệu thiếu/sai kiểu. Nếu tổng lớn hơn, cần kiểm tra xem đã nhân bản document trước bucket hay không.

## 22. Lưu ý vận hành: explain, profiler và giám sát

Dùng `explain` trên pipeline thực:

~~~javascript
lab.products.explain("executionStats").aggregate(dashboard);
~~~

Quan sát:

- Những stage trước facet có `IXSCAN`/`COLLSCAN` hay không.
- Các điều kiện `$match` đã được đẩy vào query planner như thế nào.
- Stage sort có cần xử lý trong bộ nhớ hay đã dùng index.
- Các thống kê nReturned, keys/docs examined, thời gian và memory/spill được báo tùy phiên bản.
- Dấu hiệu lỗi `ExceededMemoryLimit` và kích thước output khi tăng tập dữ liệu.

**Profiler/log `usedDisk`** chỉ báo những stage được phép sử dụng đĩa có thực sự spill hay không. Không thấy `usedDisk` không chứng minh `$facet` dùng rất ít RAM; `$facet` vốn không thể spill để vượt giới hạn riêng.

Khi có lỗi, cần xác định **stage bị giới hạn**:

- `$facet` document quá lớn → giảm số lượng/kích thước phần tử trong nhánh; tách query.
- `$sort` ngoài facet vượt RAM, có thể spill theo cấu hình → index hoặc `$sort` kết hợp `$limit`, cân nhắc `allowDiskUse`.
- `$group` với accumulator mảng lớn → không dùng `$push` vô hạn.
- Final BSON lớn hơn 16 MiB → không thể trả document đó, dù cursor batch size rất nhỏ.

Không nên tự ý thay tham số nội bộ MongoDB để tăng ngưỡng chỉ nhằm giữ nguyên pipeline sai mô hình dữ liệu. Ưu tiên thiết kế lại shape kết quả.

## 23. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `ExceededMemoryLimit` khi dùng facet | Document trung gian của `$facet` vượt giới hạn 100 MB | Giảm đầu vào, hạn chế nhánh, loại field nặng, chia query |
| Đã đặt `allowDiskUse: true` vẫn lỗi | `$facet` không spill | Không dựa vào allowDiskUse để nâng giới hạn facet |
| BSON document exceeds maximum size | Document kết quả cuối vượt 16 MiB | Giảm tổng mảng/field hoặc tách output thành nhiều document |
| `batchSize: 1` vẫn không giải quyết | Một document facet chứa các mảng rất lớn | Giới hạn dữ liệu **bên trong nhánh** |
| Metadata đếm bằng pageSize | `$limit` đặt trước `$facet` | Đưa limit vào nhánh `data` |
| Nhánh có ít kết quả bất thường | `$match` chung đặt quá chặt | Kiểm tra phạm vi filter chung và riêng |
| `metadata: []` khi không có dữ liệu | `$count` trên input rỗng không tạo document | Chuẩn hóa về 0 sau facet |
| Không thấy `_id`/tên trường mong muốn | `$project` trong hoặc sau facet xóa trường | Kiểm tra shape từng nhánh |
| Count theo brand không bằng count theo category | Hai nhánh dùng filter khác nhau hoặc dữ liệu missing | Xác định cùng phạm vi hoặc tính toán theo contract |
| `$search`/`$vectorSearch` trong facet bị từ chối | Stage không cho phép trong sub-pipeline | Đặt ở vị trí được hỗ trợ ngoài facet hoặc tách query |
| `$facet` đầu tiên gây COLLSCAN | Facet không tận dụng index khi đứng đầu | Lọc/sort ở stage trước facet theo workload |
| Có index nhưng sort trong nhánh vẫn nặng | Branch xử lý stream sau facet, không trực tiếp scan index | Cân nhắc sort trước facet hoặc truy vấn riêng |
| `$project` sau facet vẫn lỗi 100 MB | Facet đã vượt ngưỡng trước khi project | Project/limit bên trong nhánh và trước facet |
| `$sortByCount` nhóm đồng hạng đổi thứ tự | Không có khóa phụ phá hòa | Thêm `$sort` rõ ràng |
| Chỉ còn một document sau facet | Đây là hình dạng thiết kế của `$facet` | Đọc các mảng trong document |
| Truy vấn API chậm dù dùng một aggregate | Nhiều nhánh blocking, sort lớn, output phình | Benchmark tách query, cache metadata, tối ưu index |

## 24. Bài tập thực hành

Các bài sau dùng `lab.products` ở mục 3. Không cần sửa dữ liệu, trừ khi bạn tự tạo fixture mới trong collection dành cho thực hành.

### Bài 1 — Facet hai nhánh đầu tiên

Tạo pipeline chỉ lấy sản phẩm active:

- Nhánh `data`: hai sản phẩm có giá cao nhất, chỉ trả `name` và `price`.
- Nhánh `metadata`: tổng số sản phẩm active.

~~~javascript
lab.products.aggregate([
  { $match: { status: "active" } },
  {
    $facet: {
      data: [
        { $sort: { price: -1, _id: 1 } },
        { $limit: 2 },
        { $project: { _id: 0, name: 1, price: 1 } }
      ],
      metadata: [{ $count: "total" }]
    }
  }
]);
~~~

Kết quả data có Laptop Pro và Laptop Air; metadata có `total: 11`.

### Bài 2 — Dự đoán lỗi đặt $limit sai vị trí

Di chuyển `$limit: 2` ra **trước** `$facet`. Dự đoán metadata và giải thích vì sao nó không còn là tổng của toàn bộ tập active.

Trả lời: metadata chỉ đếm input đã bị limit còn 2; kết quả không phải tổng 11.

### Bài 3 — Đếm theo category và brand

Thêm hai nhánh:

~~~javascript
byCategory: [{ $sortByCount: "$category" }],
byBrand:    [{ $sortByCount: "$brand" }]
~~~

Đối chiếu:

~~~text
Categories: accessory=4, laptop=3, phone=2, book=1, tablet=1.
Brands:     Nova=5, Orion=3, Sonic=2, Paper=1.
~~~

Tại sao một nhánh `$limit: 2` trong `data` không làm các con số này giảm?

### Bài 4 — Nhóm giá cố định

Dùng `$bucket` với các cận `[0, 100, 500, 1000, 2000]`. Chọn `default: "other"`. Kiểm chứng số lượng từng khoảng bằng chính dữ liệu:

~~~text
[0,100)       -> 2
[100,500)     -> 4
[500,1000)    -> 3
[1000,2000)   -> 2
~~~

Giải thích vì sao sản phẩm giá 100 nằm ở nhóm thứ hai.

### Bài 5 — Nhóm giá tự động

Dùng `$bucketAuto` với `buckets: 3`. So sánh ranh giới với `$bucket` cố định, giải thích tình huống nên dùng mỗi cách.

### Bài 6 — Tính tồn kho

Tạo nhánh `stockStats` trả:

~~~javascript
{ totalStock: 122, inStockProducts: 10 }
~~~

Dùng `$group` và `$cond` như mục 5.4. Giải thích sự khác nhau giữa tổng đơn vị tồn và số sản phẩm còn hàng.

### Bài 7 — Kết quả rỗng và $count

Lọc `status: "unknown"` trước facet, với nhánh `data` và `total: [{ $count: "n" }]`. Dự đoán output của mỗi nhánh. Viết `$project` sau facet để trả `total: 0` khi mảng tổng đếm rỗng.

### Bài 8 — Giải thích giới hạn 100 MB và 16 MiB

Một facet tạo document trung gian 50 MB, sau đó `$project` giữ lại mảng 5 MB. Phân biệt giới hạn 100 MB và 16 MiB, và cho biết vì sao có thể thiết kế được theo quy tắc kích thước nhưng vẫn không nên dựa vào document trung gian quá lớn.

Đảo lại tình huống: facet cố tạo 120 MB rồi stage sau cắt xuống 1 MB. Tại sao `allowDiskUse: true` không cứu được?

### Bài 9 — Nhận biết stage không hợp lệ

Trong các sub-pipeline bên dưới, stage nào không được phép?

~~~javascript
{
  $facet: {
    a: [{ $match: { brand: "Nova" } }],
    b: [{ $group: { _id: "$category", n: { $sum: 1 } } }],
    c: [{ $search: { /* search definition */ } }],
    d: [{ $merge: "results" }],
    e: [{ $facet: { nested: [{ $count: "n" }] } }]
  }
}
~~~

Trả lời: nhánh c, d, e có stage bị cấm trong `$facet`; a và b là các nhánh phù hợp về loại stage.

### Bài 10 — Giới hạn branch thay vì pipeline chung

Thiết kế API phân trang sản phẩm active theo giá giảm dần, pageSize = 3, cần metadata total = 11. Viết `$sort`, `$skip`, `$limit` bên trong nhánh `data`. Đối chiếu trang 2 có Laptop Lite, Tablet và Phone Mini.

### Bài 11 — Chỉ số BSON của output

Thêm stage `$project` sau facet dùng `$bsonSize: "$$ROOT"`. Ghi lại kích thước document trong lab. Tăng pageSize từ 3 lên 8 và so sánh.

Đặt câu hỏi: nếu document facet đã vượt giới hạn 100 MB, stage đo kích thước phía sau có chạy được không? Vì sao?

### Bài 12 — Index trước facet

Tạo index:

~~~javascript
lab.products.createIndex({ status: 1, price: -1, _id: 1 });
~~~

So sánh explain hai pipeline: `$match + $facet (sort trong branch)` và `$match + $sort + $facet (limit trong branch)`. Vì sao kế hoạch và tài nguyên có thể khác nhau? Phân biệt điều kiện index của tập nguồn và khả năng xử lý của branch.

### Bài 13 — Chọn facet hay hai query

Một hệ thống có 5 triệu sản phẩm, người dùng cuộn từng trang 20 kết quả; số lượng theo thương hiệu chỉ thay đổi vài lần mỗi ngày. Thiết kế cách lấy page và metadata.

Đáp án định hướng: ưu tiên đánh giá keyset pagination bằng index cho trang dữ liệu, tính và cache thống kê theo filter phù hợp; chỉ dùng một facet chung khi benchmark và nhu cầu nhất quán/tần suất cập nhật cho thấy có lợi.

### Bài 14 — Self-excluding facets

Người dùng đang chọn `category = "accessory"` và `brand = "Nova"`. Thiết kế ba nhánh:

- `products`: áp dụng cả hai filter.
- `categories`: chỉ áp dụng filter brand.
- `brands`: chỉ áp dụng filter category.

Giải thích vì sao tổng count trong các nhánh không nhất thiết bằng nhau và đó là hành vi mong muốn của giao diện lọc.

## 25. Tổng kết

`$facet` là công cụ mạnh khi cần **tổng hợp nhiều chiều từ cùng tập input trong một aggregation**. Mỗi nhánh có pipeline riêng, cùng nhận document từ các stage trước facet, và trả kết quả vào một **mảng trong một document duy nhất**.

Các điểm phải ghi nhớ:

1. **`$facet` xử lý nhiều nhánh độc lập**; không chuyển trực tiếp output của nhánh này vào nhánh khác trong cùng stage.
2. **Filter trước facet áp dụng cho mọi nhánh**; filter và limit trong nhánh chỉ tác động lên nhánh đó.
3. **Output facet là một BSON document chứa nhiều mảng**: không giống cursor trả nhiều document nhỏ.
4. **Giới hạn 100 MB của document trung gian `$facet` là giới hạn riêng và không thể spill**, dù đặt `allowDiskUse: true`.
5. **Document cuối vẫn chịu giới hạn 16 MiB BSON**; batchSize hoặc `$limit` sau facet không làm một document khổng lồ nhỏ đi đúng lúc.
6. **Giới hạn output bên trong nhánh** bằng `$limit`, `$project`, `$group` chỉ giữ thống kê, không `$push: "$$ROOT"` vô hạn.
7. **`$facet` đứng đầu gây COLLSCAN**; dùng `$match`/`$sort` trước facet để tận dụng index khi đúng với contract dữ liệu.
8. **Không dùng `$facet` lồng nhau, `$merge`, `$out`, `$search`, `$vectorSearch` và các stage bị cấm khác** trong sub-pipeline.
9. **`$count` trên input rỗng tạo mảng rỗng**, cần chuẩn hóa total nếu API muốn số 0.
10. **Chọn facet hay các truy vấn riêng dựa trên dữ liệu và workload**; nhiều nhánh chung một scan không luôn tốt hơn truy vấn riêng có index/caching tối ưu.

### Tài liệu MongoDB chính thức

- [`$facet` (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/) — cú pháp, các nhánh độc lập, giới hạn 100 MB, 16 MiB, index và những stage bị cấm.
- [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — giới hạn kích thước, memory, `allowDiskUse` và khác biệt theo phiên bản.
- [`$bucket`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucket/) — nhóm theo ranh giới xác định.
- [`$bucketAuto`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucketAuto/) — tự chia bucket dựa trên phân bố.
- [`$sortByCount`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sortByCount/) — đếm tần suất và sắp xếp.
- [`$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — gom nhóm và accumulator.
- [`$count`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/count/) — đếm document trong pipeline.
- [`$bsonSize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonSize/) — đo kích thước document BSON.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/) — di chuyển lọc/sort, tối ưu pipeline và index.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — quan sát kế hoạch và execution stats.
