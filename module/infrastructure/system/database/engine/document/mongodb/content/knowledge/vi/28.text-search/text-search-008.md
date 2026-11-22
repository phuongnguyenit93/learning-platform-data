# Facet, highlight và phân trang kết quả tìm kiếm trong MongoDB

## 1. Bối cảnh: trang kết quả tìm kiếm cần nhiều hơn danh sách document

Giả sử một ứng dụng bán hàng có hàng trăm nghìn sản phẩm. Người dùng tìm từ khóa **wireless**. Nếu chỉ trả về một mảng sản phẩm khớp, họ còn phải tự dò xem sản phẩm nào phù hợp. Một trang tìm kiếm hoàn chỉnh thường cần ba chức năng:

- **Facet:** cung cấp các nhóm lọc và số lượng tương ứng, ví dụ danh mục `audio (3)`, thương hiệu `nova (2)`, giá `500.000–1.000.000 (2)`.
- **Highlight:** lấy đoạn trích có từ khớp để người dùng nhận ra vì sao document xuất hiện.
- **Pagination:** lấy một số lượng kết quả giới hạn mỗi lần, có chức năng Next/Previous, tránh tải toàn bộ tập kết quả.

Ví dụ về giao diện (số liệu minh họa):

```text
Từ khóa: [ wireless_________________ ] [Tìm]

Bộ lọc                          Kết quả trang 1
--------------------------------  --------------------------------
Danh mục                          Wireless Headphones Light
[ ] audio        (3)              "... lightweight WIRELESS headphones ..."
[ ] accessory    (1)              890.000 VND
[ ] computer     (1)
                                  Wireless Earbuds Pro
Giá                               "... compact WIRELESS earbuds ..."
[ ] 0–500k       (1)              950.000 VND
[ ] 500k–1tr     (3)
[ ] 1tr–2tr      (1)                [Trước]  [Tiếp]
```

Ba chức năng liên quan nhưng giải quyết **ba bài toán khác nhau**:

1. Facet diễn giải **tập document khớp truy vấn**.
2. Highlight diễn giải **một document cụ thể khớp ở đâu**.
3. Pagination diễn giải **thứ tự và vị trí** của document trong danh sách kết quả.

**Mục tiêu bài học:** biết cấu hình MongoDB Search index, dùng `$searchMeta` để tính facet, `$search` để trả highlights và score, dùng `$skip`/`$limit` hoặc `searchAfter`/`searchBefore` để phân trang; hiểu giới hạn tính nhất quán và có thể tổ chức một API tìm kiếm an toàn.

## 2. Phân biệt `$text` và MongoDB Search

MongoDB có hai cơ chế thường bị gọi chung là “full-text search”:

| Đặc điểm | MongoDB `$text` truyền thống | MongoDB Search |
|---|---|---|
| Index | `createIndex({ name: "text" })` | Search index với mappings/analyzers |
| Truy vấn | `$text: { $search: ... }` | Aggregation `$search` hoặc `$searchMeta` |
| Điểm số | `$meta: "textScore"` | `$meta: "searchScore"` |
| Facet | `$match` rồi `$facet`/`$group` | Search `facet` collector |
| Highlight native | Không có `searchHighlights` | Có `highlight` + `searchHighlights` |
| Trang theo Search token | Không có | `searchSequenceToken` + `searchAfter/searchBefore` |
| Analyzer và tính năng | Tương đối cơ bản | Tùy chỉnh analyzer, fuzzy, phrase, autocomplete, facets... |

**Trọng tâm ở đây là MongoDB Search.** Một text index thường không đủ để tạo trọn bộ trải nghiệm facet, highlight và Search pagination token. Phần cuối bài vẫn có ví dụ `$text` làm phương án cơ bản.

### 2.1. Điều kiện để chạy MongoDB Search

MongoDB Search được hỗ trợ trên **MongoDB Atlas** và các cấu hình tự quản trị phù hợp ở phiên bản MongoDB mới. Theo tài liệu hiện hành, MongoDB Community từ **8.2** và một số cấu hình Enterprise tương ứng có hỗ trợ Search khi triển khai đủ thành phần; điều đó **không** có nghĩa mọi standalone `mongod` đều sử dụng được `$search`.

Cần kiểm tra deployment, phiên bản MongoDB/mongosh/driver, quyền tài khoản, Search component và tình trạng Search index trước khi chạy. Tính năng phân trang Search bằng token có yêu cầu phiên bản riêng (tài liệu hướng dẫn từ MongoDB 7.0.5 trở lên ở cluster hỗ trợ).

### 2.2. Hai loại metadata không thay thế nhau

```text
Text index:
  $text -> textScore

MongoDB Search index:
  $search -> searchScore, searchHighlights, searchSequenceToken
  $searchMeta -> count, facet buckets
```

Không dùng `$meta: "searchScore"` trong pipeline chỉ có `$text`. Không chờ `$text` tự tạo `searchHighlights`.

## 3. Bộ dữ liệu thực hành

Ta dùng database `search_lab_307` và collection `products307`, không tác động dữ liệu production.

### 3.1. Document sản phẩm

```javascript
{
  _id: "P001",
  sku: "P001",
  name: "Wireless Headphones Light",
  description: "Lightweight wireless headphones with long battery life.",
  category: "audio",
  brand: "nova",
  price: 890000,
  publishedAt: ISODate("2026-01-10T00:00:00Z"),
  active: true
}
```

Các trường `name` và `description` dùng để search/highlight; `category`, `brand` để tạo facet chuỗi; `price` và `publishedAt` để tạo facet theo khoảng; `active` là filter; `sku` duy nhất dùng làm tie-breaker khi sort.

### 3.2. Tạo dữ liệu lab

```javascript
const lab = db.getSiblingDB("search_lab_307");
const products = lab.products307;

if (products.countDocuments({}) !== 0) {
  throw new Error("Collection da co du lieu: hay chon lab rong");
}

products.insertMany([
  {
    _id:"P001", sku:"P001",
    name:"Wireless Headphones Light",
    description:"Lightweight wireless headphones with long battery life.",
    category:"audio", brand:"nova", price:890000,
    publishedAt:ISODate("2026-01-10T00:00:00Z"), active:true
  },
  {
    _id:"P002", sku:"P002",
    name:"Wireless Earbuds Pro",
    description:"Compact wireless earbuds with noise isolation.",
    category:"audio", brand:"nova", price:950000,
    publishedAt:ISODate("2026-02-05T00:00:00Z"), active:true
  },
  {
    _id:"P003", sku:"P003",
    name:"Wireless Speaker Mini",
    description:"Portable wireless speaker for small rooms.",
    category:"audio", brand:"orion", price:1350000,
    publishedAt:ISODate("2026-03-01T00:00:00Z"), active:true
  },
  {
    _id:"P004", sku:"P004",
    name:"Wireless Charging Pad",
    description:"Wireless charging accessory for phones.",
    category:"accessory", brand:"orion", price:350000,
    publishedAt:ISODate("2026-04-11T00:00:00Z"), active:true
  },
  {
    _id:"P005", sku:"P005",
    name:"USB-C Data Cable",
    description:"Reliable cable for charging and data transfer.",
    category:"accessory", brand:"nova", price:120000,
    publishedAt:ISODate("2026-04-12T00:00:00Z"), active:true
  },
  {
    _id:"P006", sku:"P006",
    name:"Wireless Mouse Basic",
    description:"Silent wireless mouse for office work.",
    category:"computer", brand:"nova", price:490000,
    publishedAt:ISODate("2026-05-03T00:00:00Z"), active:false
  },
  {
    _id:"P007", sku:"P007",
    name:"Wireless Keyboard",
    description:"Slim wireless keyboard with compact layout.",
    category:"computer", brand:"orion", price:690000,
    publishedAt:ISODate("2026-06-15T00:00:00Z"), active:true
  }
]);

products.createIndex({ sku: 1 }, { unique: true });
```

Không dùng `drop()`/`deleteMany({})` trên dữ liệu thật để tái tạo lab. Nếu collection đã có dữ liệu, chọn namespace thử nghiệm mới.

### 3.3. Tập khớp mong đợi

Truy vấn `wireless` cùng `active: true` có thể tìm các sản phẩm P001, P002, P003, P004, P007. P006 có chữ `wireless` nhưng `active: false`; P005 không có từ đó.

Thứ tự theo **relevance** có thể khác thứ tự insert. Chỉ dùng các mã trên để hiểu tập dữ liệu; không khẳng định Search score cụ thể trước khi chạy.

## 4. Search index: field text khác field facet

### 4.1. Chọn đúng mapping

| Field | Search type | Mục đích |
|---|---|---|
| `name` | `string` | Search text và highlight |
| `description` | `string` | Search text và highlight |
| `category` | `token` | Facet chuỗi, exact filter |
| `brand` | `token` | Facet chuỗi, exact filter |
| `price` | `number` | Numeric facet/range/sort |
| `publishedAt` | `date` | Date facet/range/sort |
| `active` | `boolean` | Filter |
| `sku` | `token` | Sort tie-breaker |

Theo tài liệu Search hiện hành, **`token`** được khuyến nghị cho string facet. `stringFacet` là type cũ được các hướng dẫn legacy sử dụng. Nếu cần **cùng một field vừa tìm từ vừa facet**, có thể cần index field dưới **nhiều kiểu phù hợp**; không nhầm `string` và `token` là đồng nghĩa.

### 4.2. Tạo index

Chỉ chạy trên deployment hỗ trợ Search:

```javascript
products.createSearchIndex("catalog_search_307", {
  mappings: {
    dynamic: false,
    fields: {
      name: {
        type: "string",
        indexOptions: "offsets"
      },
      description: {
        type: "string",
        indexOptions: "offsets"
      },
      category: {
        type: "token",
        normalizer: "lowercase"
      },
      brand: {
        type: "token",
        normalizer: "lowercase"
      },
      price: { type: "number" },
      publishedAt: { type: "date" },
      active: { type: "boolean" },
      sku: { type: "token" }
    }
  }
});
```

Index tạo qua `createSearchIndex()` **khác** index thông thường tạo qua `createIndex()`. Một Search index có thể còn đang build sau khi lệnh tạo trả về.

### 4.3. Kiểm tra trạng thái

```javascript
products.aggregate([
  { $listSearchIndexes: {} }
]);
```

Đảm bảo index tên `catalog_search_307` đã sẵn sàng. Không kết luận `$search` sai cú pháp khi Search index chưa hoàn thành build.

### 4.4. Tại sao highlight cần offsets?

Search cần biết **vị trí các từ/đoạn khớp trong văn bản gốc** để trích highlight. Field phải được index dạng `string` và `indexOptions: "offsets"` (thông thường là giá trị mặc định phù hợp). Không dùng mapping chỉ hỗ trợ exact token rồi mong có highlight text như tên sản phẩm.

## 5. `$search`: lấy document và relevance score

```javascript
products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      text: {
        query: "wireless",
        path: ["name", "description"]
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      sku: 1,
      name: 1,
      price: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

`$search` phải là **stage đầu tiên** trong pipeline có sử dụng nó. Không đặt `$match` trước `$search`. Nếu muốn Search filter từ đầu, sử dụng operator phù hợp trong `$search.compound.filter`.

### 5.1. Lọc active không làm lệch score văn bản

```javascript
products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      compound: {
        must: [
          {
            text: {
              query: "wireless",
              path: ["name", "description"]
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "active",
              value: true
            }
          }
        ]
      }
    }
  },
  {
    $project: {
      sku: 1,
      name: 1,
      active: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

`compound.must` yêu cầu text khớp; `compound.filter` giới hạn tập document mà không đóng góp điểm như điều kiện text.

### 5.2. Score không phải tỷ lệ phần trăm

`searchScore = 8.4` không có nghĩa “84% đúng”. Score là thước đo mức liên quan theo operator, analyzer và tập dữ liệu; không nên so trực tiếp score giữa hai từ khóa khác nhau mà không có cơ sở.

## 6. Facet: nhóm theo tập kết quả tìm kiếm

Với năm sản phẩm active khớp `wireless`:

```text
P001 audio      890.000
P002 audio      950.000
P003 audio    1.350.000
P004 accessory  350.000
P007 computer   690.000

Category facet:
  audio       3
  accessory   1
  computer    1

Price facet:
  [0, 500k)      1
  [500k, 1tr)    3
  [1tr, 2tr)     1
```

**Facet nên tính trên tập khớp đầy đủ theo filter được chọn**, không phải chỉ 10–20 document đang hiển thị ở trang hiện tại.

### 6.1. Ba dạng facet

| Dạng | Ví dụ | Cơ chế |
|---|---|---|
| String | Danh mục, thương hiệu | Bucket theo giá trị chuỗi, cần mapping `token` |
| Number | Giá, rating | Bucket theo khoảng số |
| Date | Ngày đăng, ngày phát hành | Bucket theo khoảng thời gian |

Field có nhiều giá trị (như array tags) có thể đóng góp cho **nhiều bucket**, do đó tổng số đếm của bucket **không bắt buộc bằng số document duy nhất**.

## 7. `$searchMeta`: facet theo category

`$searchMeta` trả **metadata**, không trả danh sách sản phẩm đầy đủ.

```javascript
products.aggregate([
  {
    $searchMeta: {
      index: "catalog_search_307",
      facet: {
        operator: {
          compound: {
            must: [
              {
                text: {
                  query: "wireless",
                  path: ["name", "description"]
                }
              }
            ],
            filter: [
              { equals: { path: "active", value: true } }
            ]
          }
        },
        facets: {
          categories: {
            type: "string",
            path: "category",
            numBuckets: 10
          }
        }
      }
    }
  }
]);
```

### 7.1. Cấu trúc

- `facet.operator` định nghĩa **tập kết quả khớp**.
- `facets.categories` định nghĩa **cách nhóm** tập đó.
- `type: "string"` yêu cầu string facet.
- `path: "category"` trỏ field index `token`.
- `numBuckets` giới hạn số bucket trả về, **không** giới hạn số document được Search xem xét.

### 7.2. Kết quả minh họa

```javascript
[
  {
    count: { lowerBound: NumberLong("5") },
    facet: {
      categories: {
        buckets: [
          { _id: "audio", count: NumberLong("3") },
          { _id: "accessory", count: NumberLong("1") },
          { _id: "computer", count: NumberLong("1") }
        ]
      }
    }
  }
]
```

`_id` ở bucket là **giá trị category**, không phải ID sản phẩm. Tên trường và giá trị thực phụ thuộc query/deployment; đây là mẫu rút gọn.

### 7.3. Facet không chỉ xử lý top 10 hits

Nếu query thực tế khớp 100.000 sản phẩm, `numBuckets: 10` có nghĩa chỉ trả tối đa 10 nhóm phổ biến theo tiêu chí facet; điều đó **không** có nghĩa Search chỉ đọc 10 sản phẩm. Với field nhiều giá trị duy nhất, facet vẫn có thể dùng nhiều bộ nhớ và tài nguyên.

## 8. Numeric facet: nhóm theo khoảng giá

```javascript
products.aggregate([
  {
    $searchMeta: {
      index: "catalog_search_307",
      facet: {
        operator: {
          text: {
            query: "wireless",
            path: ["name", "description"]
          }
        },
        facets: {
          prices: {
            type: "number",
            path: "price",
            boundaries: [0, 500000, 1000000, 2000000],
            default: "other"
          }
        }
      }
    }
  }
]);
```

**Lưu ý về bài lab:** truy vấn này chưa filter `active: true`, nên nếu cần hiển thị facet cho **sản phẩm active**, hãy thêm cùng điều kiện active vào `facet.operator`.

Các khoảng được hiểu:

```text
[0, 500000)
[500000, 1000000)
[1000000, 2000000)
other
```

**Biên dưới được tính, biên trên không tính.** Giá 500.000 thuộc bucket thứ hai, không phải bucket đầu. Giá 2.000.000 thuộc `other` nếu được chỉ định như trên.

Không đưa chuỗi `"890000"` vào field numeric rồi kỳ vọng nó được xử lý giống số `890000`.

### 8.1. Ranh giới là quyết định nghiệp vụ

Ứng dụng bán tai nghe có thể nhóm 0–500k, 500k–1tr, 1tr–2tr; ứng dụng bán ô tô có cách chia khác. Không nhất thiết phân khoảng đều theo min–max nếu điều đó không giúp người dùng chọn sản phẩm.

## 9. Date facet: nhóm theo thời gian

```javascript
products.aggregate([
  {
    $searchMeta: {
      index: "catalog_search_307",
      facet: {
        operator: {
          text: {
            query: "wireless",
            path: ["name", "description"]
          }
        },
        facets: {
          publishDates: {
            type: "date",
            path: "publishedAt",
            boundaries: [
              ISODate("2026-01-01T00:00:00Z"),
              ISODate("2026-04-01T00:00:00Z"),
              ISODate("2026-07-01T00:00:00Z")
            ],
            default: "otherDate"
          }
        }
      }
    }
  }
]);
```

Date facet nhóm theo **BSON Date**, không nên chuyển ngày thành text token rồi mong numeric/date range hoạt động tự nhiên.

### 9.1. Timezone quan trọng

Một bucket từ `2026-04-01T00:00:00Z` không trùng chính xác ngày bắt đầu quý theo mọi timezone. Nếu UI nói “Quý 2 theo giờ Việt Nam”, cần tính đúng ranh giới ngày/giờ địa phương rồi chuyển sang thời điểm UTC trước khi tạo boundaries.

## 10. Nhiều facet trong một truy vấn

```javascript
const facetMetadata307 = products.aggregate([
  {
    $searchMeta: {
      index: "catalog_search_307",
      facet: {
        operator: {
          compound: {
            must: [
              {
                text: {
                  query: "wireless",
                  path: ["name", "description"]
                }
              }
            ],
            filter: [
              { equals: { path: "active", value: true } }
            ]
          }
        },
        facets: {
          categories: {
            type: "string",
            path: "category",
            numBuckets: 10
          },
          brands: {
            type: "string",
            path: "brand",
            numBuckets: 10
          },
          prices: {
            type: "number",
            path: "price",
            boundaries: [0, 500000, 1000000, 2000000],
            default: "other"
          }
        }
      }
    }
  }
]).toArray();

printjson(facetMetadata307);
```

Một kết quả metadata có thể chứa:

```javascript
{
  count: { lowerBound: NumberLong("5") },
  facet: {
    categories: { buckets: [/* ... */] },
    brands: { buckets: [/* ... */] },
    prices: { buckets: [/* ... */] }
  }
}
```

Mỗi facet phản ánh **một cách nhóm trên cùng tập match**. Không cộng `categories.count` với `brands.count` rồi xem đó là tổng hits.

## 11. Khi người dùng chọn bộ lọc: conjunctive và disjunctive

Giả sử người dùng chọn `category = "audio"`.

### 11.1. Conjunctive faceting

Facet category được tính **sau khi đã áp category=audio**:

```text
Tập match:
  text=wireless AND active=true AND category=audio

Facet category:
  audio (3)
```

Cách này chính xác nếu UI muốn diễn giải **tập đang được lọc hiện tại**.

### 11.2. Disjunctive faceting

UI có thể muốn giữ các lựa chọn cùng chiều:

```text
[x] audio       (3)
[ ] accessory   (1)
[ ] computer    (1)
```

Khi đó, để tính facet category, **bỏ riêng điều kiện category đang chọn**, nhưng giữ các điều kiện khác:

```text
Query lấy hits:
  wireless AND active=true AND category=audio

Query lấy category facet:
  wireless AND active=true
```

Nếu chọn thêm brand=nova và price trong một khoảng, những filter đó vẫn cần được áp dụng khi tính category facet theo chính sách disjunctive.

### 11.3. Thay đổi loại facet cần thay đổi filter nào?

| Facet đang tính | Bỏ filter nào để còn các lựa chọn cùng chiều? |
|---|---|
| Category | Bỏ category, giữ brand/price/active |
| Brand | Bỏ brand, giữ category/price/active |
| Price | Bỏ price, giữ category/brand/active |

Không có quy tắc facet duy nhất đúng cho mọi giao diện. **Backend và frontend phải thống nhất semantics của bucket counts.**

### 11.4. Multi-select dùng OR trong một chiều

Một yêu cầu:

```text
category = audio OR computer
brand = nova
active = true
```

có thể biểu diễn bằng Search `in` trên field category token:

```javascript
{
  compound: {
    must: [{
      text: {
        query: "wireless",
        path: ["name", "description"]
      }
    }],
    filter: [
      { equals: { path: "active", value: true } },
      { in: { path: "category", value: ["audio", "computer"] } },
      { equals: { path: "brand", value: "nova" } }
    ]
  }
}
```

Không cho browser gửi trực tiếp operator tùy ý; backend cần allowlist field, operator, số filter và quyền đọc dữ liệu.

## 12. Search facet collector khác aggregation `$facet`

### 12.1. Aggregation `$facet`

`$facet` là một **aggregation pipeline stage** có thể chạy nhiều nhánh trên cùng tập document:

```javascript
products.aggregate([
  { $match: { active: true } },
  {
    $facet: {
      hits: [
        { $sort: { price: 1, _id: 1 } },
        { $limit: 5 }
      ],
      categories: [
        { $group: { _id: "$category", count: { $sum: 1 } } },
        { $sort: { count: -1, _id: 1 } }
      ]
    }
  }
]);
```

Nó xử lý document do pipeline phía trước cung cấp. Đây **không** phải Search facet collector.

### 12.2. Search facet collector

Facet nằm bên trong `$searchMeta`/`$search`:

```javascript
{
  $searchMeta: {
    index: "catalog_search_307",
    facet: {
      operator: {
        text: { query: "wireless", path: "name" }
      },
      facets: {
        categories: { type: "string", path: "category" }
      }
    }
  }
}
```

Nó sử dụng Search index để tính metadata.

### 12.3. Sai: đặt `$search` bên trong nhánh `$facet`

```javascript
// KHÔNG HỢP LỆ:
[
  {
    $facet: {
      hits: [
        { $search: { text: { query: "wireless", path: "name" } } }
      ]
    }
  }
]
```

`$search` phải là stage đầu của pipeline và **không được đặt bên trong một nhánh `$facet`**. Có thể dùng `$facet` **sau** `$search` nếu thật sự cần:

```javascript
products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      text: {
        query: "wireless",
        path: ["name", "description"]
      }
    }
  },
  {
    $facet: {
      hits: [
        { $limit: 5 },
        { $project: { name: 1, category: 1 } }
      ],
      categories: [
        { $group: { _id: "$category", count: { $sum: 1 } } }
      ]
    }
  }
]);
```

Không đặt `$limit` **trước** `$facet` nếu muốn đếm toàn bộ tập match. Với dữ liệu lớn, Search facet collector thường là lựa chọn phù hợp hơn vì `$facet` aggregation có thể phải xử lý nhiều document sau Search.

## 13. Lấy hits và metadata trong một pipeline

Một lựa chọn thực tế là chạy **hai query**:

```text
Query A: $search -> hits + highlights + pagination tokens
Query B: $searchMeta -> facets + count
```

Như vậy có thể cache facets độc lập và **không tính lại facet khi chỉ nhấn Next**.

### 13.1. Sử dụng `$$SEARCH_META`

MongoDB Search cũng hỗ trợ facet collector trong `$search`; metadata được cung cấp qua biến `$$SEARCH_META`.

```javascript
products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      facet: {
        operator: {
          text: {
            query: "wireless",
            path: ["name", "description"]
          }
        },
        facets: {
          categories: {
            type: "string",
            path: "category",
            numBuckets: 10
          }
        }
      },
      highlight: {
        path: ["name", "description"]
      }
    }
  },
  { $limit: 10 },
  {
    $facet: {
      hits: [
        {
          $project: {
            name: 1,
            category: 1,
            score: { $meta: "searchScore" },
            highlights: { $meta: "searchHighlights" }
          }
        }
      ],
      metadata: [
        { $replaceWith: "$$SEARCH_META" },
        { $limit: 1 }
      ]
    }
  },
  {
    $set: {
      metadata: { $arrayElemAt: ["$metadata", 0] }
    }
  }
]);
```

Kết quả là một document chứa `hits` và `metadata`. Tuy nhiên, nhánh đọc `$$SEARCH_META` sau `$search` cần có document khớp để chạy; trong trường hợp zero hits, metadata có thể phải xử lý riêng bằng `$searchMeta`.

Một số stage như `$lookup`/`$unionWith` còn làm mất khả năng tham chiếu `$$SEARCH_META` ở các stage tiếp theo. Hãy lấy metadata trước những stage đó.

## 14. Highlight: từ khớp và văn cảnh

Highlight không chỉ là tìm chuỗi con bằng JavaScript rồi tô màu. Search có thể dùng analyzer để khớp biến thể từ, field và vị trí khác nhau.

Kết quả highlight được trả qua `$meta: "searchHighlights"`. Một ví dụ rút gọn:

```javascript
{
  path: "description",
  score: 2.35,
  texts: [
    { value: "Lightweight ", type: "text" },
    { value: "wireless", type: "hit" },
    { value: " headphones with long battery life.", type: "text" }
  ]
}
```

`texts.type`:

- `"hit"`: đoạn cần đánh dấu.
- `"text"`: ngữ cảnh xung quanh.

Điểm highlight của **đoạn trích** không phải score xếp hạng của cả document.

### 14.1. Cú pháp `highlight`

```javascript
products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      text: {
        query: "wireless",
        path: ["name", "description"]
      },
      highlight: {
        path: ["name", "description"],
        maxNumPassages: 2,
        maxCharsToExamine: 5000
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      sku: 1,
      name: 1,
      score: { $meta: "searchScore" },
      highlights: { $meta: "searchHighlights" }
    }
  }
]);
```

**Vị trí option:** `highlight` là child trực tiếp của `$search`, không phải trường nằm bên trong `text`.

### 14.2. Vì sao `$project` cần `searchHighlights`?

Highlight là **metadata**, không phải field được lưu sẵn trong document sản phẩm. Muốn trả về UI, cần:

```javascript
{ highlights: { $meta: "searchHighlights" } }
```

### 14.3. Những option quan trọng

| Option | Vai trò |
|---|---|
| `highlight.path` | Field/list fields muốn có đoạn trích |
| `maxNumPassages` | Số passage tối đa mỗi field |
| `maxCharsToExamine` | Số ký tự tối đa được xét khi tìm highlight trong một field |

Nếu keyword nằm sau ký tự 15.000 nhưng `maxCharsToExamine: 5000`, Search vẫn có thể trả **document khớp** trong khi highlight của field đó rỗng. **Highlight rỗng không tự chứng minh document không match.**

### 14.4. Highlight không phải post-processor mọi field

Nếu field không được mapping đúng dưới dạng Search string với offset, hoặc bị xử lý qua một analyzer không tương ứng, highlight có thể thiếu/sai kỳ vọng. Không tạo một field `token` chỉ cho faceting rồi đòi highlight từ trường đó như một văn bản nhiều từ.

## 15. Render highlight an toàn, tránh XSS

Giả sử description trong database chứa:

```text
Wireless <script>alert("x")</script> headphones
```

Nếu frontend ghép nguyên `segment.value` vào `innerHTML`, nội dung từ người dùng có thể bị thực thi như HTML. Metadata highlight **không phải một bước khử HTML độc hại**.

Một cách render an toàn trong trình duyệt:

```javascript
for (const segment of highlight.texts) {
  if (segment.type === "hit") {
    const mark = document.createElement("mark");
    mark.textContent = segment.value;
    container.appendChild(mark);
  } else {
    container.appendChild(
      document.createTextNode(segment.value)
    );
  }
}
```

`textContent` và `createTextNode` tạo văn bản an toàn thay vì diễn giải nội dung thành HTML. Với React/Vue, dùng cơ chế escaping mặc định thay vì innerHTML thô.

Ngoài XSS, cần kiểm soát quyền truy cập field highlight: **snippet có thể tiết lộ nội dung** mà user không được xem nếu index nhầm trường nội bộ.

## 16. Phân trang đơn giản: `$skip` + `$limit`

Với `pageSize=10`:

```text
Trang 1 -> skip 0,  limit 10
Trang 2 -> skip 10, limit 10
Trang 3 -> skip 20, limit 10
Trang N -> skip (N-1)*10, limit 10
```

Ví dụ:

```javascript
const page = 3;
const pageSize = 10;

products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      text: {
        query: "wireless",
        path: ["name", "description"]
      },
      sort: {
        score: { $meta: "searchScore" },
        sku: 1
      }
    }
  },
  { $skip: (page - 1) * pageSize },
  { $limit: pageSize },
  {
    $project: {
      name: 1,
      sku: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

### 16.1. Sort ổn định cần tie-breaker

Nếu nhiều sản phẩm cùng score, thứ tự có thể không ổn định giữa các truy vấn. Dùng một khóa duy nhất `sku` được index kiểu `token` để quyết định thứ tự trong trường hợp tie:

```javascript
sort: {
  score: { $meta: "searchScore" },
  sku: 1
}
```

Hoặc:

```javascript
sort: {
  publishedAt: -1,
  sku: 1
}
```

**Chỉ sort theo ngày không đủ** nếu nhiều document có cùng `publishedAt`.

### 16.2. Deep skip tốn tài nguyên

Trang 20.000, mỗi trang 20:

```text
skip = (20000 - 1) * 20 = 399980
```

Server phải vượt rất nhiều vị trí trước khi trả 20 kết quả. Offset tiện cho **vài trang đầu** hoặc nhảy trang, nhưng có thể kém hiệu quả khi người dùng duyệt rất sâu.

### 16.3. Sort không tạo snapshot

Giữa trang 1 và trang 2, một document mới có thể được chèn lên đầu danh sách. Offset của các document cũ dịch chuyển, làm trang 2 **lặp** một kết quả trang 1 hoặc **bỏ** một kết quả chưa thấy.

Tie-breaker giải quyết thứ tự **đồng điểm**, không đóng băng dữ liệu trước insert/update/delete.

## 17. `searchAfter`: phân trang từ điểm tham chiếu

MongoDB Search hỗ trợ `searchAfter`/`searchBefore` trên những cluster/version tương thích; tài liệu MongoDB mô tả sử dụng từ MongoDB **7.0.5+** trong môi trường hỗ trợ.

Khác với skip:

```text
skip:
  Bỏ N kết quả đầu tiên.

searchAfter:
  Bắt đầu SAU một kết quả tham chiếu của Search sort.
```

### 17.1. Sinh token trang 1

```javascript
const size = 2;
const page1 = products.aggregate([
  {
    $search: {
      index: "catalog_search_307",
      compound: {
        must: [{
          text: {
            query: "wireless",
            path: ["name", "description"]
          }
        }],
        filter: [
          { equals: { path: "active", value: true } }
        ]
      },
      sort: {
        score: { $meta: "searchScore" },
        sku: 1
      }
    }
  },
  { $limit: size },
  {
    $project: {
      sku: 1,
      name: 1,
      score: { $meta: "searchScore" },
      paginationToken: { $meta: "searchSequenceToken" }
    }
  }
]).toArray();

const lastToken = page1.length > 0
  ? page1[page1.length - 1].paginationToken
  : null;

printjson(page1);
```

`searchSequenceToken` là **Base64-encoded token** do MongoDB Search sinh cho từng hit. Nó **không phải** Change Stream resume token, MongoDB cursor ID hay document `_id`.

### 17.2. Dùng token cho trang tiếp theo

```javascript
const page2 = lastToken
  ? products.aggregate([
      {
        $search: {
          index: "catalog_search_307",
          compound: {
            must: [{
              text: {
                query: "wireless",
                path: ["name", "description"]
              }
            }],
            filter: [
              { equals: { path: "active", value: true } }
            ]
          },
          sort: {
            score: { $meta: "searchScore" },
            sku: 1
          },
          searchAfter: lastToken
        }
      },
      { $limit: size },
      {
        $project: {
          sku: 1,
          name: 1,
          paginationToken: { $meta: "searchSequenceToken" }
        }
      }
    ]).toArray()
  : [];

printjson(page2);
```

Điểm quan trọng là **operator, filters và sort phải giữ nguyên ngữ nghĩa** giữa các trang. Khi đổi từ khóa, category, brand, price, analyzer, index hoặc sort, **bỏ token cũ và bắt đầu lại từ trang đầu**.

### 17.3. Token cuối trang, không token tự tạo

Lấy token từ hit **cuối** trang để làm next cursor. Nếu trang rỗng, không tạo token giả từ `Date.now()`, `ObjectId` hoặc score.

## 18. `searchBefore` và nút Previous

Để đi ngược, lấy token của **hit đầu trang hiện tại**:

```javascript
const firstToken = page2.length > 0
  ? page2[0].paginationToken
  : null;
```

Rồi dùng **cùng query** nhưng thay `searchAfter` bằng `searchBefore`:

```javascript
function previousPageFrom(token) {
  return products.aggregate([
    {
      $search: {
        index: "catalog_search_307",
        compound: {
          must: [{
            text: {
              query: "wireless",
              path: ["name", "description"]
            }
          }],
          filter: [
            { equals: { path: "active", value: true } }
          ]
        },
        sort: {
          score: { $meta: "searchScore" },
          sku: 1
        },
        searchBefore: token
      }
    },
    { $limit: size },
    {
      $project: {
        sku: 1,
        name: 1,
        paginationToken: { $meta: "searchSequenceToken" }
      }
    }
  ]).toArray().reverse();
}

const previousPage = firstToken
  ? previousPageFrom(firstToken)
  : [];
```

MongoDB Search trả các kết quả trước điểm tham chiếu theo **thứ tự ngược**. `reverse()` đưa mảng về thứ tự UI gốc.

Không thay đổi `sort` thành một sort khác rồi mong token còn tương thích.

## 19. Giới hạn quan trọng: token không cố định snapshot

Tài liệu MongoDB nêu rõ **`searchSequenceToken` không gắn với một snapshot cố định của database**.

Ví dụ:

```text
T1:
  A(score=9), B(score=8), C(score=7), D(score=6)
  page 1 = [A, B], lưu token sau B

T2:
  C được cập nhật thành score=10
  Thứ tự mới = C, A, B, D
```

Khi lấy trang 2 theo token cũ, ứng dụng không nên cam kết người dùng sẽ **nhìn mọi document đúng một lần**, bởi kết quả Search đã thay đổi.

### 19.1. Search-after mang lại điều gì?

- Giúp duyệt kết quả theo thứ tự Search mà không phải bỏ qua toàn bộ các trang trước.
- Có thể giảm chi phí deep pagination.
- Cho API một điểm tham chiếu do Search engine sinh.

### 19.2. Search-after không mang lại điều gì?

- Không tạo snapshot isolation xuyên nhiều HTTP request.
- Không làm index đứng yên khi source document đổi.
- Không biến một danh sách relevance thành thứ tự vĩnh viễn.
- Không cho phép tái sử dụng token trên query/filter/sort khác.

Nếu nghiệp vụ yêu cầu export **đúng một lần, đầy đủ và ổn định**, cần cơ chế snapshot/dataset cố định khác, không lấy token của trang Search làm bằng chứng đầy đủ.

### 19.3. Vì sao sort trong `$search`?

Token liên hệ với **thứ tự Search**. Nếu UI muốn sort theo giá nhưng pipeline lại:

```javascript
[
  { $search: { /* sort theo score */ } },
  { $sort: { price: 1 } }
]
```

thì token và thứ tự UI có thể lệch semantics. Hãy đặt:

```javascript
sort: { price: 1, sku: 1 }
```

**bên trong `$search`**, với field đã được Search index phù hợp.

## 20. So sánh offset, search-after và keyset

| Tiêu chí | Offset `$skip` | Search-after token |
|---|---|---|
| Điểm bắt đầu | Số vị trí cần bỏ | Một hit tham chiếu |
| Input API | `page=5` | `nextToken=...` |
| Nhảy trang 100 | Diễn đạt dễ nhưng đắt | Cần token hoặc bước trung gian |
| Duyệt sâu tuần tự | Có thể rất tốn tài nguyên | Thường thuận lợi hơn |
| Đổi filter/sort | Tính offset mới | Phải bỏ token cũ |
| Dữ liệu live thay đổi | Có thể lặp/thiếu | Vẫn có thể lặp/thiếu |

MongoDB Search hỗ trợ kết hợp `searchAfter` với `$skip` cho việc nhảy một khoảng **ngắn** từ điểm tham chiếu đã biết. Nó không biến việc nhảy hàng triệu vị trí thành miễn phí.

**Keyset pagination thủ công** bằng điều kiện `price > lastPrice` + `_id` thích hợp với những query MongoDB thông thường có sort ổn định. Khi tìm theo **relevance score** phức tạp, không nên tự sáng chế predicate theo score rồi xem tương đương Search token.

## 21. Count: lower bound khác exact total

Một truy vấn `$searchMeta` có thể trả:

```javascript
{
  count: { lowerBound: NumberLong("1000") }
}
```

`lowerBound` nghĩa là **cận dưới**, không được dịch thành “chính xác 1.000 kết quả”.

Khi cần exact total, có thể yêu cầu:

```javascript
products.aggregate([
  {
    $searchMeta: {
      index: "catalog_search_307",
      text: {
        query: "wireless",
        path: ["name", "description"]
      },
      count: { type: "total" }
    }
  }
]);
```

Exact total có thể tốn thêm tài nguyên; nhiều UI hiển thị “Hơn 1.000 kết quả” là đủ. Không cộng top-N facet buckets để suy total hits: nhiều bucket có thể bị giới hạn, một document array có thể góp nhiều nhóm và disjunctive facets có thể dùng query khác hits.

## 22. Thiết kế API: kết quả, facet và token

### 22.1. Input có hợp đồng rõ

```json
{
  "q": "wireless",
  "filters": {
    "active": true,
    "categories": ["audio"],
    "priceMin": 0,
    "priceMax": 2000000
  },
  "sort": "relevance",
  "pageSize": 10,
  "after": null
}
```

Backend tự xây Search operator từ các field **được phép**, không thực thi aggregation JSON do client tùy ý gửi.

### 22.2. Output đề xuất

```json
{
  "items": [
    {
      "id": "P001",
      "name": "Wireless Headphones Light",
      "price": 890000,
      "score": 4.2,
      "highlights": [
        {
          "path": "name",
          "texts": [
            { "type": "hit", "value": "Wireless" },
            { "type": "text", "value": " Headphones Light" }
          ]
        }
      ]
    }
  ],
  "facets": {
    "categories": [
      { "value": "audio", "count": 3 },
      { "value": "accessory", "count": 1 }
    ]
  },
  "count": {
    "value": 5,
    "relation": "lowerBound"
  },
  "nextToken": "opaque-token-from-mongodb-search",
  "previousToken": "opaque-token-from-mongodb-search"
}
```

Đây là **contract minh họa của backend**, không phải output nguyên dạng MongoDB. Score và token trên là giả lập.

### 22.3. Reset phân trang khi query thay đổi

```text
Đang xem:
  q=wireless, category=audio, page=2
        |
        v
Chọn thêm brand=orion
        |
        v
Reset nextToken/previousToken
Quay lại page 1 của query mới
```

### 22.4. Bảo vệ token

Một API có thể gói token Search với:

```javascript
{
  version: 1,
  queryHash: "hash-of-canonical-query-and-sort",
  searchToken: "opaque-base64",
  direction: "next"
}
```

Nếu token đi tới client, nên xác thực integrity (HMAC hoặc cơ chế tương ứng) hoặc lưu server-side. **Base64 không phải mã hóa bảo mật hoặc chữ ký.**

Token không thay thế authentication/authorization; backend phải tái áp dụng tenant/security filter ở mọi trang.

### 22.5. Không cho page size vô hạn

```javascript
const requested = 10000;
const pageSize = Math.min(
  Math.max(requested, 1),
  50
);
```

Giới hạn thực tế nên dựa trên SLA, kích thước document và khả năng hạ tầng.

## 23. `$text` + aggregation `$facet` khi chưa dùng MongoDB Search

Trên deployment chỉ có tìm kiếm truyền thống, có thể tạo text index:

```javascript
products.createIndex({
  name: "text",
  description: "text"
});
```

### 23.1. Query `$text` và textScore

```javascript
products.find(
  {
    $text: { $search: "wireless" },
    active: true
  },
  {
    name: 1,
    category: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" },
  _id: 1
}).limit(10);
```

### 23.2. Một aggregation vừa lấy hits vừa đếm facet

```javascript
products.aggregate([
  {
    $match: {
      $text: { $search: "wireless" },
      active: true
    }
  },
  {
    $addFields: {
      score: { $meta: "textScore" }
    }
  },
  {
    $facet: {
      hits: [
        { $sort: { score: -1, _id: 1 } },
        { $limit: 10 },
        {
          $project: {
            name: 1,
            category: 1,
            price: 1,
            score: 1
          }
        }
      ],
      categories: [
        { $group: { _id: "$category", count: { $sum: 1 } } },
        { $sort: { count: -1, _id: 1 } }
      ],
      priceRanges: [
        {
          $bucket: {
            groupBy: "$price",
            boundaries: [0, 500000, 1000000, 2000000],
            default: "other",
            output: { count: { $sum: 1 } }
          }
        }
      ]
    }
  }
]);
```

`$match` chứa `$text` phải là stage đầu của aggregation. Các nhánh facets ở đây tính trên **tập khớp sau `$match`**, không phải 10 hits đã `$limit` trong nhánh khác.

**Giới hạn:** `$text` không có Search `highlight` native và không có `searchSequenceToken`. Tự highlight bằng regex có thể khác analyzer/stemming và tạo rủi ro XSS/ReDoS nếu xử lý input không an toàn.

## 24. Tìm kiếm tiếng Việt và analyzer

Một hệ thống cần hỗ trợ:

```text
"tai nghe"
"tai nghe bluetooth"
"tai nghe không dây"
"khong day"
```

Đây là các chuỗi có quan hệ về từ vựng/ngữ nghĩa, nhưng **không mặc định khớp nhau** trong mọi Search analyzer.

Nên xác định:

- Có cần không phân biệt hoa/thường?
- Có cần bỏ dấu tiếng Việt?
- Analyzer tách token như thế nào?
- Có từ đồng nghĩa nghiệp vụ như “BT” ↔ “Bluetooth” không?
- Có cần autocomplete/prefix search không?
- Highlight có phản ánh khớp do analyzer một cách người dùng hiểu được không?

Facet thường dùng **normalized token** cho mã category/brand, trong khi description thường dùng **full-text analyzer**. Đừng dùng một analyzer cho tất cả field chỉ để đơn giản hóa index.

## 25. Java Sync Driver: hits, highlight và token

MongoDB Java Sync Driver có thể xây aggregation bằng `Document`. Cú pháp `$search` vẫn giống server; mã chỉ chạy khi URI trỏ tới deployment có Search.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.ArrayList;
import java.util.List;

public class SearchPage307 {
    public static void main(String[] args) {
        // URI giả lập; thay bằng địa chỉ deployment hỗ trợ Search.
        String uri = "mongodb://localhost:27017";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> products = client
                .getDatabase("search_lab_307")
                .getCollection("products307");

            Document text = new Document("text",
                new Document("query", "wireless")
                    .append("path",
                        Arrays.asList("name", "description")));

            Document activeFilter = new Document("equals",
                new Document("path", "active").append("value", true));

            Document compound = new Document("must",
                Arrays.asList(text))
                .append("filter", Arrays.asList(activeFilter));

            Document search = new Document("index", "catalog_search_307")
                .append("compound", compound)
                .append("highlight", new Document(
                    "path", Arrays.asList("name", "description")))
                .append("sort", new Document("score",
                    new Document("$meta", "searchScore"))
                    .append("sku", 1));

            Document project = new Document("sku", 1)
                .append("name", 1)
                .append("price", 1)
                .append("score",
                    new Document("$meta", "searchScore"))
                .append("highlights",
                    new Document("$meta", "searchHighlights"))
                .append("paginationToken",
                    new Document("$meta", "searchSequenceToken"));

            List<Document> pipeline = Arrays.asList(
                new Document("$search", search),
                new Document("$limit", 10),
                new Document("$project", project)
            );

            List<Document> hits = products.aggregate(pipeline)
                .into(new ArrayList<>());

            for (Document hit : hits) {
                System.out.println(hit.toJson());
            }

            if (!hits.isEmpty()) {
                String nextToken = hits.get(hits.size() - 1)
                    .getString("paginationToken");
                System.out.println("Next token = " + nextToken);

                // Lượt request sau: cùng query/filter/sort,
                // thêm searchAfter: nextToken vào $search.
            }
        }
    }
}
```

### 25.1. Trang tiếp theo trong Java

Ở request tiếp theo, tạo `Document search` mới **với cùng semantics** và thêm:

```java
search.append("searchAfter", nextToken);
```

Không giữ token trong biến static dùng chung giữa nhiều user hoặc dùng một token sau khi thay filter.

### 25.2. Facet metadata từ Java

```java
Document facet = new Document("operator",
        new Document("compound", compound))
    .append("facets", new Document("categories",
        new Document("type", "string")
            .append("path", "category")
            .append("numBuckets", 10)));

Document searchMeta = new Document("index", "catalog_search_307")
    .append("facet", facet);

List<Document> meta = products.aggregate(
    Arrays.asList(new Document("$searchMeta", searchMeta))
).into(new ArrayList<>());
```

Snippet dùng lại các biến `products`/`compound` từ hàm Java phía trên. Với trường hợp disjunctive, phải xây **facet operator khác** có chủ đích, không máy móc dùng nguyên filter category đang chọn.

## 26. Hiệu năng và tính nhất quán

### 26.1. Facet có thể tốn bộ nhớ

Chi phí faceting phụ thuộc **cardinality** của field và số request đồng thời, không chỉ vào `numBuckets`. Một facet theo `sku` có hàng triệu giá trị khác nhau thường không phù hợp cho thanh bộ lọc của UI.

### 26.2. Highlight dài có thể đắt

Với description hàng trăm nghìn ký tự, tăng `maxCharsToExamine` và `maxNumPassages` quá lớn có thể tăng CPU, kích thước phản hồi và độ trễ. Chỉ trả những trường và đoạn trích cần thiết.

### 26.3. Search index không phải cơ chế read-after-write nghiêm ngặt

MongoDB Search index có thể cập nhật **bất đồng bộ** với các thao tác ghi nguồn. Ngay sau khi insert/update thành công, `$search` có thể chưa thấy thay đổi mới.

Nếu nghiệp vụ cần xác minh đơn hàng vừa được ghi, đọc document nguồn với chính sách nhất quán phù hợp, **không dùng kết quả Search như bằng chứng duy nhất rằng ghi chưa được thực hiện**.

### 26.4. Facet và hits có thể nhìn dữ liệu tại hai thời điểm

Khi backend chạy hai query:

```text
$search -> hits
$searchMeta -> facets
```

giữa chúng có thể có cập nhật. Vì vậy facet counts và hits có thể chênh nhỏ khi dữ liệu biến động. Đừng tuyên bố hai query tự là một snapshot.

### 26.5. Tối ưu thực tế

- Cache facet metadata theo `normalized query + filters + facet policy` khi hợp lý.
- Không tính lại facets chỉ vì user bấm Next.
- Limit page size và projection.
- Dùng token cho duyệt sâu, tránh skip quá lớn.
- Sort ổn định với tie-breaker.
- Không facet theo trường cardinality quá cao.
- Theo dõi latency riêng cho `$search` và `$searchMeta`.
- Tối ưu mappings/analyzers theo truy vấn thật.

## 27. Những lỗi thường gặp

| Dấu hiệu | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| `$search` không được nhận diện | Deployment thiếu Search | Kiểm tra compatibility/cấu hình Search |
| Search trả rỗng | Index chưa build, field/analyzer/filter sai | `$listSearchIndexes`, query tối giản |
| String facet lỗi | Field chưa index kiểu `token` | Kiểm tra mapping |
| Highlight rỗng | Field thiếu offsets, query match field khác, giới hạn chars | Kiểm tra mapping và `$project` |
| Category count nhỏ bất thường | Tính sau `$limit` hoặc filter category đang bật | Kiểm tra facet operator/policy |
| Facet trả quá ít nhóm | `numBuckets` nhỏ hoặc tập match ít | Kiểm tra phạm vi và cardinality |
| Trang 2 lặp sản phẩm | Sort ties, data thay đổi, offset dịch | Tie-breaker và page token |
| Search token bị từ chối | Đổi query/filter/sort hoặc token sai | Reset phân trang |
| Previous có thứ tự ngược | Chưa reverse kết quả `searchBefore` | Đảo mảng trước UI |
| Count không khớp hiển thị | `lowerBound`, top N bucket, disjunctive policy | Hiểu count relation |
| Query tăng latency | Deep skip, nhiều facets, highlight dài | Giảm chi phí, đo workload |

### 27.1. Không thử sửa bằng cách đổi dữ liệu production

Khi Search index không sẵn sàng hoặc query không trả như mong đợi, kiểm tra cấu hình và log trước. Không xóa/reinsert collection nghiệp vụ, không drop index production tùy ý và không đổi mappings trong giờ cao điểm mà chưa có kế hoạch rebuild.

## 28. Các ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| `$text` có sẵn `searchHighlights` | Highlight native thuộc MongoDB Search |
| Aggregation `$facet` giống Search `facet` | Khác tầng xử lý và nguồn dữ liệu |
| Đặt `$search` trong nhánh `$facet` là hợp lệ | `$search` không được đặt ở đó |
| Facet đếm 10 hits hiện tại là đủ | Thanh bộ lọc thường cần toàn tập match |
| `numBuckets: 10` giới hạn Search đọc 10 document | Chỉ giới hạn số bucket trả ra |
| Category mapping `string` luôn facet được | Hiện nay dùng `token` cho string facets |
| Tổng các bucket bằng total hits | Array/missing values/top N có thể làm sai |
| Chọn category rồi facet không thay đổi | Phụ thuộc conjunctive/disjunctive policy |
| Highlight tự chống XSS | UI vẫn phải escape text |
| Không có highlight nghĩa không match | Passage/offset giới hạn có thể gây rỗng |
| `searchScore` là phần trăm liên quan | Score là thước đo xếp hạng phụ thuộc query |
| Sort chỉ theo score luôn ổn định | Có ties; cần tie-breaker |
| `$skip` sâu luôn rẻ như trang 1 | Deep skip có thể tốn tài nguyên |
| `searchAfter` bảo đảm không lặp/thiếu khi dữ liệu đổi | Token không gắn snapshot |
| Search token là Change Stream resume token | Hai loại token hoàn toàn khác nhau |
| Dùng token sau khi đổi filter vẫn đúng | Phải bắt đầu trang mới |
| `searchBefore` trả ngay thứ tự UI | Thường phải reverse mảng |
| Facet lowerBound là exact total | Nó chỉ là cận dưới |
| Search luôn thấy ngay ghi vừa commit | Index có thể cập nhật bất đồng bộ |
| Token Base64 tự xác thực người dùng | Token không thay auth hay authorization |
| Facet không trả document nên không thể lộ dữ liệu | Bucket counts có thể lộ thông tin |

## 29. Bài tập thực hành

### Bài 1 — Chọn cơ chế tìm kiếm

Một website cần: tìm từ khóa, lọc theo category, highlight và Next/Previous bằng token. Chức năng nào làm được bằng `$text` + `$facet`, chức năng nào yêu cầu MongoDB Search? Phân biệt `textScore` và `searchScore`.

### Bài 2 — Thiết kế mapping

Cho fields `name`, `description`, `category`, `brand`, `price`, `publishedAt`, `active`, `sku`. Hãy chọn Search mapping type và giải thích tại sao `sku` hợp lý làm tie-breaker nhưng không hợp lý làm facet trên hàng triệu sản phẩm.

### Bài 3 — Facet counts

Với năm hit:

```text
audio, audio, audio, accessory, computer
```

Hãy viết `$searchMeta` string facet category. Nếu pageSize=2, category facet nên đếm 2 hay 5 document cho một giao diện tổng thể?

### Bài 4 — Numeric boundaries

Cho `[0, 500000, 1000000, 2000000]`, phân loại các giá 499999, 500000, 999999, 1000000, 2000000. Vì sao 500000 không thuộc bucket đầu?

### Bài 5 — Date facet

Viết `$searchMeta` facet theo các khoảng quý trên field `publishedAt`. Nếu UI theo ngày Việt Nam, boundaries UTC cần được tính thế nào?

### Bài 6 — Array facet

Ba document có:

```javascript
{ tags: ["wireless", "portable"] }
{ tags: ["wireless"] }
{ tags: ["portable"] }
```

Tổng số bucket counts có thể lớn hơn số document không? Vì sao?

### Bài 7 — Conjunctive và disjunctive

Người dùng chọn category=audio, brand=nova. Hãy nêu operator cần dùng để lấy hits và operator để tính **facet category hiển thị các category khác**. Vì sao không chỉ sao chép nguyên mọi filter?

### Bài 8 — Pipeline sai

```javascript
[
  {
    $facet: {
      hits: [
        { $search: { text: { query: "wireless", path: "name" } } }
      ]
    }
  }
]
```

Tại sao sai? Hãy sửa bằng `$search` ở đầu pipeline và `$facet` phía sau hoặc bằng Search facet collector.

### Bài 9 — Highlight

Cho description `"Lightweight wireless headphones"` và query `wireless`. Hãy viết mảng `texts` với `hit`/`text` rồi mô tả cách render HTML an toàn.

### Bài 10 — Highlight rỗng

Description dài 20.000 ký tự, từ khớp nằm tại ký tự 15.000, `maxCharsToExamine=5000`. Document có thể vẫn match nhưng không có highlight không? Có nên tăng giới hạn vô hạn không?

### Bài 11 — Offset

Với pageSize=25, hãy tính skip cho trang 1, 3 và 1.000. Phân tích chi phí deep skip và tác động của insert mới vào vị trí đầu kết quả.

### Bài 12 — Tie-breaker

Mười document có cùng `searchScore`. Nếu chỉ sort theo score, nguy cơ gì khi phân trang? Tại sao thêm `sku` duy nhất giúp thứ tự rõ hơn nhưng không khóa snapshot?

### Bài 13 — Search-after

Viết pipeline trang đầu lấy `searchSequenceToken`, sau đó lấy token của hit cuối để dùng `searchAfter`. Điều gì xảy ra nếu người dùng đổi category giữa hai trang?

### Bài 14 — Search-before

Từ token của hit đầu trang 3, hãy viết truy vấn lấy trang trước với `searchBefore`. Vì sao phải đảo thứ tự mảng trước khi hiển thị?

### Bài 15 — Count metadata

Một query trả `count: { lowerBound: 1000 }`. UI hiển thị “Chính xác 1.000 kết quả”. Đúng hay sai? Khi nào cần `count: { type: "total" }`?

### Bài 16 — Dữ liệu thay đổi

T1: thứ tự A(9), B(8), C(7), D(6); trang 1 gồm A,B. T2: C đổi score thành 10. Hãy giải thích vì sao token sau B không bảo đảm một lượt duyệt không lặp/thiếu document.

### Bài 17 — Security filter

Hits query có filter `tenantId`, nhưng facet query không có. Ngay cả khi không trả nội dung document, facet count có thể rò rỉ thông tin gì? Đề xuất cách tái sử dụng security filter ở cả hai query.

### Bài 18 — Tối ưu và monitoring

Ứng dụng có hàng triệu sản phẩm, 50.000 brand, và mỗi lần Next đều tính lại facet brand. Hãy nêu ít nhất năm cải tiến về cardinality, cache, index, paging, highlight limits và quan sát p95 latency.

## 30. Quy trình triển khai đáng tin cậy

1. **Xác nhận Search support** của deployment và trạng thái index.
2. **Định nghĩa câu hỏi nghiệp vụ:** text, category, brand, price, time, sort.
3. **Tạo mapping đúng:** `string` cho text/highlight; `token` cho facet/exact filter/sort chuỗi; `number`/`date` cho khoảng.
4. **Xây shared operator:** text conditions và security filters phải thống nhất giữa hits và facets.
5. **Chốt facet semantics:** conjunctive hay disjunctive; bucket counts đếm tập nào.
6. **Chọn phương án metadata:** `$searchMeta` riêng hoặc `$$SEARCH_META` khi kết hợp.
7. **Thiết lập highlight:** offsets, path và giới hạn passages; render escape.
8. **Chọn sort ổn định:** relevance/price/date kèm unique tie-breaker.
9. **Chọn pagination:** offset cho trang đầu, search-after cho duyệt sâu; search-before cho Previous.
10. **Giữ query identity:** khi từ khóa/filter/sort đổi, reset token.
11. **Hiểu consistency:** Search token không cố định snapshot; index có thể cập nhật bất đồng bộ.
12. **Giới hạn tài nguyên:** pageSize, facet fields, numBuckets, highlight length.
13. **Theo dõi:** latency của Search/metadata, lỗi index, no-result rate và hành vi sử dụng filter.
14. **Bảo mật:** tenant filter cho cả facets, highlight và hits; token không thay xác thực.

## 31. Tổng kết

**Facet** trả metadata nhóm từ **tập kết quả tìm kiếm**; **highlight** chỉ ra đoạn văn bản khớp ở **từng hit**; **pagination** điều hướng theo một thứ tự xác định mà không tải hết danh sách cùng lúc. Ba chức năng bổ sung lẫn nhau nhưng không thể thay thế.

**MongoDB Search cung cấp công cụ chuyên biệt:** `$search` để lấy hits và `searchScore`; `$searchMeta` với facet collector để lấy category/number/date buckets; `$meta: "searchHighlights"` để trả đoạn đánh dấu; `$meta: "searchSequenceToken"`, `searchAfter` và `searchBefore` để phân trang theo điểm tham chiếu. Aggregation `$facet` không phải Search facet collector, còn `$text` truyền thống không có native Search highlights.

**Tính đúng đắn phụ thuộc semantics:** facet đếm trước phân trang và theo đúng filter policy; highlight phải được escape khi render; sort cần tie-breaker; token chỉ tương thích cùng search query/filter/sort. `searchAfter` có thể giúp giảm chi phí deep pagination nhưng **không tạo snapshot**, đặc biệt khi sản phẩm được thêm, sửa, xóa trong lúc người dùng chuyển trang.

Khi xác định rõ những giới hạn này, có thể xây trang tìm kiếm MongoDB vừa **dễ lọc**, **giải thích được kết quả** và **duyệt hiệu quả** mà không đưa ra những bảo đảm sai về số lượng hoặc tính ổn định của dữ liệu.

## Tài liệu tham khảo

- [MongoDB Search — $search](https://www.mongodb.com/docs/search/query/aggregation-stages/search/): Search operator, sort, metadata và stage rules.
- [MongoDB Search — $searchMeta](https://www.mongodb.com/docs/search/query/aggregation-stages/searchmeta/): metadata-only queries.
- [MongoDB Search — Facet](https://www.mongodb.com/docs/search/query/operators-collectors/facet/): string/number/date facets và `$$SEARCH_META`.
- [MongoDB Search — Highlight Search Terms](https://www.mongodb.com/docs/search/query/highlighting/): offsets, `searchHighlights`, passages.
- [MongoDB Search — Paginate Results](https://www.mongodb.com/docs/search/query/paginate-results/): `searchAfter`, `searchBefore`, `searchSequenceToken`.
- [MongoDB Search — Token field type](https://www.mongodb.com/docs/search/indexes/field-types/token-type/): facet và sort chuỗi.
- [MongoDB — createSearchIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/): tạo index.
- [MongoDB — $text query](https://www.mongodb.com/docs/manual/reference/operator/query/text/): lựa chọn tìm kiếm văn bản truyền thống.
