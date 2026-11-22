# Xử lý array với filter, map, reduce và tập hợp

> **Chương:** Aggregation nâng cao  
> **Module:** `SPRING_DATA_MONGODB`

Array là một trong những đặc trưng quan trọng của document MongoDB: một đơn hàng chứa nhiều dòng sản phẩm, một bài viết có nhiều nhãn, một thiết bị có nhiều lần đo hoặc một tài khoản có danh sách quyền. Khi cần tính toán ngay trên các mảng đó, ta không nhất thiết tải toàn bộ document vào Java và viết nhiều vòng `for`. **MongoDB Aggregation Framework** cung cấp các *array expressions* để lọc phần tử (`$filter`), biến đổi từng phần tử (`$map`), tích lũy kết quả (`$reduce`) và tính toán theo ngữ nghĩa tập hợp (`$setUnion`, `$setIntersection`, `$setDifference`, `$setEquals`, `$setIsSubset`).

Điểm khó không phải chỉ nhớ tên toán tử. Cần xác định chính xác **mỗi expression nhận array nào, trả về kiểu gì, có giữ thứ tự/giá trị lặp không, và xử lý mảng rỗng, `null` hay field thiếu ra sao**. Một pipeline trông hợp lý có thể đếm trùng phần tử, bỏ qua dữ liệu legacy hoặc làm sai tổng số tiền khi biến đổi sai thứ tự.

Bài thuộc module `SPRING_DATA_MONGODB`: kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu. Ta sẽ bắt đầu bằng MongoDB aggregation, sau đó hiện thực tương ứng ở Spring Data MongoDB.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt *aggregation stage* (`$match`, `$set`, `$project`, `$unwind`) với *array expression* (`$filter`, `$map`, `$reduce` và các set operators).
2. Dùng `$filter` để giữ phần tử phù hợp, `$map` để biến đổi phần tử, `$reduce` để tạo một kết quả tích lũy, kể cả array hoặc object.
3. Sử dụng `$$this`, `$$value` và biến tự đặt qua `as` đúng phạm vi.
4. Áp dụng `$setUnion`, `$setIntersection`, `$setDifference`, `$setEquals`, `$setIsSubset` mà không nhầm thứ tự và duplicate của array với tập hợp.
5. Xử lý array rỗng/`null`/missing/sai kiểu bằng `$isArray`, `$cond`, `$ifNull`, phân biệt filter theo phần tử với lọc document.
6. Tích hợp pipeline bằng `Aggregation`/`MongoTemplate` hoặc `@Aggregation` phù hợp, đối chiếu kiểu BSON và kiểm thử kết quả trên server MongoDB thật.

## 2. Bản đồ nhanh các toán tử

| Toán tử | Đầu vào chính | Đầu ra | Đặc điểm |
| --- | --- | --- | --- |
| `$filter` | Array + điều kiện `cond` | Array con | Giữ thứ tự tương đối của phần tử được chọn; không tự bỏ duplicate |
| `$map` | Array + biểu thức `in` | Array cùng số phần tử | Biến đổi từng phần tử theo thứ tự, không tự lọc |
| `$reduce` | Array + `initialValue` + biểu thức `in` | Một giá trị tùy ý | Duyệt từ trái qua phải; giá trị tích lũy có thể là số, string, object hoặc array |
| `$setUnion` | Các array | Tập hợp hợp | Bỏ trùng, không hứa giữ thứ tự |
| `$setIntersection` | Các array | Tập hợp giao | Chỉ giữ phần tử chung; bỏ trùng |
| `$setDifference` | Hai array | Hiệu tập hợp | Có hướng: A trừ B khác B trừ A |
| `$setEquals` | Các array | Boolean | So sánh theo tập hợp, không theo thứ tự/số lần xuất hiện |
| `$setIsSubset` | Hai array | Boolean | Kiểm tra mọi phần tử của tập thứ nhất có trong tập thứ hai |
| `$size` | Array | Số nguyên | Đếm **số phần tử array**, gồm cả giá trị lặp |
| `$concatArrays` | Các array | Array nối | Giữ phần tử lặp, phục vụ nối danh sách chứ không phải set union |
| `$arrayElemAt` | Array và index | Một phần tử | Lấy theo vị trí, không dùng ngữ nghĩa tập hợp |

Các expression này thường nằm **bên trong** `$set`/`$addFields`, `$project` hoặc `$group`, không phải là các stage cấp cao nhất. `$set` trong aggregation là stage tạo/ghi đè field của **document đang đi trong luồng**, không phải lệnh cập nhật dữ liệu gốc.

### 2.1. Mô hình luồng

```text
Collection orders (document có items[] và labels[])
            |
            v
[$match]  Chỉ document thuộc tenant được phép
            |
            v
[$set]    Chuẩn hóa input thành safeItems[], safeLabels[]
            |
            v
[$set]    eligibleItems[] = $filter(safeItems[])
          lineTotals[] = $map(safeItems[])
          allItemTags[] = $reduce(...$setUnion...)
          union/intersection/difference của labels[]
            |
            v
[$set]    totalMinor = $reduce(lineTotals[])
          eligibleSubtotal = $reduce(eligibleItems[])
            |
            v
[$project] Chỉ giữ output phục vụ API
            |
            v
Document kết quả; mỗi order vẫn là một document
```

Trong pipeline này, các expression xử lý array **mà không cần `$unwind`**. Do đó, mỗi order thường tiếp tục tương ứng một document đầu ra. `$unwind` là stage có thể **nhân số document** theo số phần tử, khác với `$map` hoặc `$filter` vốn giữ cấu trúc mảng ở bên trong mỗi document.

## 3. Bộ dữ liệu dùng xuyên suốt

Ta có collection `orders`. Mỗi đơn gồm `items` là array các dòng hàng, mỗi dòng có `sku`, `qty`, `unitPriceMinor`, `tags`; ngoài ra đơn có `labels` hiện tại và `incomingLabels` từ một nguồn đồng bộ.

**Chỉ chạy trên database MongoDB kiểm thử cô lập:**

```javascript
use shop

db.orders.insertMany([
  {
    _id: "A-101",
    tenantId: "TENANT-A",
    status: "PAID",
    items: [
      { sku: "SKU-A", qty: 2,
        unitPriceMinor: NumberLong(12000),
        tags: ["fragile", "promotion"] },
      { sku: "SKU-B", qty: 1,
        unitPriceMinor: NumberLong(5000),
        tags: ["gift"] },
      { sku: "SKU-C", qty: 3,
        unitPriceMinor: NumberLong(7000),
        tags: ["promotion", "priority"] }
    ],
    labels: ["web", "priority", "web"],
    incomingLabels: ["priority", "express", "priority"]
  },
  {
    _id: "A-102",
    tenantId: "TENANT-A",
    status: "NEW",
    items: [],
    labels: [],
    incomingLabels: ["web"]
  },
  {
    _id: "A-103",
    tenantId: "TENANT-A",
    status: "PAID",
    items: [
      { sku: "SKU-D", qty: 1,
        unitPriceMinor: NumberLong(9000),
        tags: ["express"] },
      { sku: "SKU-E", qty: 4,
        unitPriceMinor: NumberLong(2000),
        tags: ["priority", "express"] }
    ],
    labels: ["app", "express"],
    incomingLabels: ["express", "priority"]
  },
  {
    _id: "A-104",
    tenantId: "TENANT-A",
    status: "NEW",
    items: null,
    labels: null,
    incomingLabels: ["web"]
  },
  {
    _id: "B-201",
    tenantId: "TENANT-B",
    status: "PAID",
    items: [
      { sku: "SKU-Z", qty: 100,
        unitPriceMinor: NumberLong(100000),
        tags: ["private"] }
    ],
    labels: ["private"],
    incomingLabels: ["private", "priority"]
  }
])
```

`TENANT-B` được đưa vào để bắt lỗi thiếu điều kiện phân quyền. Không được cộng giá trị SKU-Z vào báo cáo tenant A. `A-102` và `A-104` giúp phân biệt **mảng rỗng** với **BSON null**; dữ liệu thực còn có thể thiếu hẳn field hoặc lưu sai kiểu.

### 3.1. Kỳ vọng tính toán

| Đơn | Dòng hàng và thành tiền | Tổng tất cả | Dòng đủ `qty >= 2` | Tổng dòng đủ điều kiện |
| --- | --- | ---: | --- | ---: |
| A-101 | 24.000 + 5.000 + 21.000 | 50.000 | SKU-A, SKU-C | 45.000 |
| A-102 | Không có dòng hàng | 0 | Không có | 0 |
| A-103 | 9.000 + 8.000 | 17.000 | SKU-E | 8.000 |
| A-104 | `items: null` | 0 theo quy tắc chuẩn hóa minh họa | Không có | 0 |
| B-201 | 100 × 100.000 | 10.000.000 | SKU-Z | 10.000.000 |

Giá trị A-104 bằng 0 là **quy tắc fallback được chọn cho ví dụ học tập**, không có nghĩa null trong dữ liệu thanh toán thực luôn tương đương số tiền bằng 0. Nếu schema yêu cầu `items` bắt buộc, cách đúng ở production có thể là từ chối document hoặc đưa vào hàng xử lý lỗi thay vì báo cáo 0.

## 4. $filter: lọc *phần tử* trong array

Yêu cầu: trên từng đơn tenant A, chỉ giữ các dòng có `qty >= 2`:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "TENANT-A", _id: "A-101" } },
  {
    $project: {
      _id: 1,
      eligibleItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: { $gte: ["$$item.qty", 2] }
        }
      }
    }
  }
])
```

Kết quả `eligibleItems` gồm **SKU-A** và **SKU-C**, theo thứ tự gốc; SKU-B bị bỏ do `qty=1`.

### 4.1. Giải nghĩa cú pháp

| Thành phần | Ý nghĩa |
| --- | --- |
| `input: "$items"` | Lấy giá trị array của document hiện tại |
| `as: "item"` | Đặt biến cục bộ cho từng phần tử (tên không có `$$`) |
| `cond: {...}` | Biểu thức điều kiện; phần tử được giữ khi điều kiện đúng |
| `"$$item.qty"` | Truy cập `qty` của biến phần tử `item`, không phải field `item.qty` của document gốc |
| `limit` (nếu dùng) | Giới hạn số phần tử thỏa điều kiện, theo hỗ trợ của phiên bản MongoDB |

Nếu không khai báo `as`, biến phần tử mặc định của `$filter` là `$$this`. Cú pháp tương đương:

```javascript
{
  $filter: {
    input: "$items",
    cond: { $gte: ["$$this.qty", 2] }
  }
}
```

**Không nhầm `$filter` với `$match`:** `$match` quyết định **document nào** đi qua pipeline; `$filter` quyết định **phần tử nào bên trong một array** được giữ. Với input là một array, `$filter` không tự nhân document thành nhiều bản ghi.

### 4.2. Kết hợp nhiều điều kiện

Giữ dòng vừa có `qty >= 2`, vừa có `unitPriceMinor >= 5000`:

```javascript
{
  $filter: {
    input: "$items",
    as: "i",
    cond: {
      $and: [
        { $gte: ["$$i.qty", 2] },
        { $gte: ["$$i.unitPriceMinor", NumberLong(5000)] }
      ]
    }
  }
}
```

Ở A-101, SKU-A (12.000, qty 2) và SKU-C (7.000, qty 3) đều khớp. Viết `$and` **bên trong `cond`** để buộc hai điều kiện đúng trên **cùng một phần tử**.

### 4.3. $filter.limit không giống $limit stage

Ví dụ lấy tối đa **một phần tử phù hợp** từ array:

```javascript
{
  $filter: {
    input: "$items",
    as: "i",
    cond: { $gte: ["$$i.qty", 2] },
    limit: 1
  }
}
```

`limit` ở đây giới hạn **phần tử trong array kết quả**, không phải số document toàn pipeline. Còn `{ $limit: 1 }` là stage giới hạn **một document** đi tiếp. Kiểm tra phiên bản MongoDB server đang dùng khi tận dụng các tùy chọn nâng cao của toán tử.

## 5. $map: biến đổi từng phần tử thành giá trị mới

Yêu cầu: từ mỗi dòng hàng, tạo một **thành tiền** `qty × unitPriceMinor`:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "TENANT-A", _id: "A-101" } },
  {
    $project: {
      _id: 1,
      lineTotals: {
        $map: {
          input: "$items",
          as: "i",
          in: { $multiply: ["$$i.qty", "$$i.unitPriceMinor"] }
        }
      }
    }
  }
])
// A-101: lineTotals = [24000, 5000, 21000]
```

`$map` trả array có **cùng số lượng phần tử và thứ tự** với array đầu vào, trừ trường hợp input null/missing (xem mục an toàn dữ liệu). Đây không phải phép lọc: mỗi phần tử sinh ra đúng một giá trị của expression `in`.

### 5.1. Map sang object thay vì number

```javascript
{
  $map: {
    input: "$items",
    as: "item",
    in: {
      sku: "$$item.sku",
      qty: "$$item.qty",
      subtotalMinor: {
        $multiply: [
          "$$item.qty",
          "$$item.unitPriceMinor"
        ]
      }
    }
  }
}
```

Với A-101, kết quả là ba object tương ứng SKU-A, SKU-B, SKU-C, mỗi object có `subtotalMinor`. Mục đích là tạo một **read model cho API** mà không cần sửa dữ liệu lưu trong collection.

### 5.2. Map sau filter và filter sau map

Nếu chỉ cần thành tiền của các dòng `qty >= 2`:

```javascript
{
  $map: {
    input: {
      $filter: {
        input: "$items",
        as: "item",
        cond: { $gte: ["$$item.qty", 2] }
      }
    },
    as: "selected",
    in: {
      $multiply: [
        "$$selected.qty",
        "$$selected.unitPriceMinor"
      ]
    }
  }
}
// A-101: [24000, 21000]
```

Thứ tự **filter rồi map** hữu ích vì phép nhân chỉ thực hiện cho các phần tử được chọn. Nếu **map trước** thành các con số, stage/expression lọc phía sau không còn `qty` để xét trừ khi map ra object vẫn giữ `qty`. Cần định nghĩa rõ schema trung gian khi kết hợp nhiều array expressions.

### 5.3. $map không cập nhật array gốc

```javascript
db.orders.aggregate([
  { $match: { _id: "A-101" } },
  {
    $project: {
      _id: 1,
      transformed: {
        $map: {
          input: "$items",
          as: "i",
          in: { sku: "$$i.sku" }
        }
      }
    }
  }
])
```

MongoDB chỉ trả array `transformed` trong **kết quả aggregation**. Collection vẫn có các dòng hàng gốc. Muốn thay đổi dữ liệu đã lưu phải dùng update API hoặc pipeline ghi đích có chủ đích như `$merge`/`$out`, không suy diễn rằng `$map` tự ghi.

## 6. $reduce: gộp một array thành một giá trị

`$reduce` thích hợp khi mỗi phần tử cần góp vào một **giá trị tích lũy** (*accumulator*), ví dụ tổng tiền, chuỗi mô tả, một object chứa nhiều số liệu hoặc tập hợp nhãn. Khác với `$map`, số phần tử đầu ra không còn phải tương ứng một-một với đầu vào: kết quả là **một giá trị**.

Cấu trúc:

```javascript
{
  $reduce: {
    input: <array-expression>,
    initialValue: <initial-expression>,
    in: <expression-using-$$value-and-$$this>
  }
}
```

Trong `in`:

- `$$value` là kết quả tích lũy trước khi xử lý phần tử hiện tại; lần đầu chính là `initialValue`.
- `$$this` là phần tử array **đang được xử lý**.
- Biểu thức `in` tính ra **giá trị tích lũy mới**, sẽ trở thành `$$value` cho vòng kế tiếp.
- MongoDB xử lý theo thứ tự từ trái sang phải. Nếu cần duyệt ngược, dùng `$reverseArray` cho `input` trước khi reduce.

### 6.1. Reduce tổng từ array lineTotals

Giả sử từ `$map` ta đã có:

```javascript
lineTotals: [NumberLong(24000), NumberLong(5000), NumberLong(21000)]
```

Expression:

```javascript
{
  $reduce: {
    input: "$lineTotals",
    initialValue: NumberLong(0),
    in: { $add: ["$$value", "$$this"] }
  }
}
```

Diễn tiến:

| Vòng | `$$value` trước vòng | `$$this` | `$$value` sau vòng |
| --- | ---: | ---: | ---: |
| Khởi tạo | — | — | 0 |
| 1 | 0 | 24.000 | 24.000 |
| 2 | 24.000 | 5.000 | 29.000 |
| 3 | 29.000 | 21.000 | 50.000 |

Tổng A-101 = **50.000**. Với array rỗng, `$reduce` trả **`initialValue`**, trong trường hợp này là số 0. Với input null/missing, `$reduce` trả null theo ngữ nghĩa toán tử; đừng nhầm hai trường hợp nếu dữ liệu đầu vào chưa được chuẩn hóa.

### 6.2. Reduce trực tiếp array object

Không bắt buộc `$map` trước khi tính tổng:

```javascript
{
  $reduce: {
    input: "$items",
    initialValue: NumberLong(0),
    in: {
      $add: [
        "$$value",
        {
          $multiply: [
            "$$this.qty",
            "$$this.unitPriceMinor"
          ]
        }
      ]
    }
  }
}
```

Ở đây `$$this` là **object dòng hàng**, nên có thể truy cập `$$this.qty` và `$$this.unitPriceMinor`. Cách này ngắn khi chỉ cần tổng; còn `$map` + `$reduce` tách hai bước sẽ dễ debug nếu cần đồng thời trả thành tiền từng dòng.

### 6.3. Reduce sau filter: tổng tiền các dòng đủ điều kiện

```javascript
{
  $reduce: {
    input: {
      $filter: {
        input: "$items",
        as: "i",
        cond: { $gte: ["$$i.qty", 2] }
      }
    },
    initialValue: NumberLong(0),
    in: {
      $add: [
        "$$value",
        { $multiply: ["$$this.qty", "$$this.unitPriceMinor"] }
      ]
    }
  }
}
```

A-101 nhận 45.000, A-103 nhận 8.000. Đây là phép giảm tổng **trên các dòng đã lọc**, không phải tổng tất cả dòng.

### 6.4. Reduce thành object chứa nhiều kết quả

`initialValue` có thể là object chứ không chỉ một số:

```javascript
{
  $reduce: {
    input: "$items",
    initialValue: {
      lineCount: 0,
      quantityTotal: 0,
      amountMinor: NumberLong(0)
    },
    in: {
      lineCount: { $add: ["$$value.lineCount", 1] },
      quantityTotal: {
        $add: ["$$value.quantityTotal", "$$this.qty"]
      },
      amountMinor: {
        $add: [
          "$$value.amountMinor",
          { $multiply: ["$$this.qty", "$$this.unitPriceMinor"] }
        ]
      }
    }
  }
}
```

Kết quả cho A-101:

```javascript
{
  lineCount: 3,
  quantityTotal: 6,
  amountMinor: NumberLong(50000)
}
```

Đây là một phép *fold*: mỗi dòng cập nhật cả ba field của object tích lũy. Khi thêm nhiều đại lượng, cần kiểm tra đơn vị, kiểu BSON và khả năng overflow; biểu thức đúng về cú pháp không đủ bảo đảm kết quả có ý nghĩa tài chính.

### 6.5. Reduce nối các phần tử theo thứ tự

```javascript
{
  $reduce: {
    input: ["A", "B", "C"],
    initialValue: "",
    in: { $concat: ["$$value", "$$this"] }
  }
}
// "ABC"
```

Phép nối có **thứ tự** khác hẳn toán tử tập hợp. `$setUnion` không dùng để giữ thứ tự chuỗi nếu đầu vào có thể có phần tử lặp.

## 7. Các phép tập hợp trên array: bỏ trùng và không dựa vào thứ tự

Array của MongoDB có **thứ tự và cho phép giá trị lặp**. Ngược lại, các biểu thức set thao tác theo **tập hợp phần tử**, nên thường không giữ thông tin về vị trí hoặc số lần xuất hiện.

Với A-101:

```javascript
labels         = ["web", "priority", "web"]
incomingLabels = ["priority", "express", "priority"]
```

### 7.1. $setUnion: hợp

```javascript
{
  $setUnion: ["$labels", "$incomingLabels"]
}
```

Tập kết quả chứa **web**, **priority**, **express** — mỗi giá trị một lần. Đừng kỳ vọng kết quả phải đúng thứ tự `["web","priority","express"]`: set operators **không cam kết thứ tự phần tử**.

Nếu cần array đầu ra có thứ tự cố định cho API, hãy thêm bước sort array khi MongoDB version hỗ trợ `$sortArray`, hoặc xử lý sắp xếp bằng pipeline/cách khác phù hợp.

### 7.2. $setIntersection: giao

```javascript
{
  $setIntersection: ["$labels", "$incomingLabels"]
}
```

Kết quả chứa duy nhất **priority**. Giá trị này xuất hiện ở cả hai array; việc lặp `priority` trong input không làm nó xuất hiện hai lần trong tập kết quả.

### 7.3. $setDifference: hiệu có hướng

```javascript
{
  $setDifference: ["$labels", "$incomingLabels"]
}
// Tập kết quả: { "web" }
```

Phần tử thuộc labels cũ nhưng không thuộc incomingLabels mới là `web`.

Đảo thứ tự hai đối số:

```javascript
{
  $setDifference: ["$incomingLabels", "$labels"]
}
// Tập kết quả: { "express" }
```

**`A \\ B` khác `B \\ A`**. Với đồng bộ nhãn, phải quyết định rõ đang muốn **bỏ khỏi danh sách cũ** hay **thêm mới từ nguồn đồng bộ**.

### 7.4. $setEquals: cùng tập phần tử?

```javascript
{
  $setEquals: [
    ["web", "priority", "web"],
    ["priority", "web"]
  ]
}
// true
```

Hai array khác thứ tự và số lần xuất hiện, nhưng đều biểu diễn tập `{web, priority}`, nên `$setEquals` trả true.

Nếu nghiệp vụ cần kiểm tra **array giống nhau từng vị trí**, không dùng `$setEquals`. Cần so sánh theo quy tắc array có thứ tự, ví dụ các expression phù hợp hoặc so sánh ở tầng ứng dụng.

### 7.5. $setIsSubset: kiểm tra tập con

```javascript
{
  $setIsSubset: [
    ["priority"],
    ["web", "priority"]
  ]
}
// true
```

Đảo đối số:

```javascript
{
  $setIsSubset: [
    ["web", "priority"],
    ["priority"]
  ]
}
// false
```

Đây là phép kiểm tra **tập con**, không kiểm tra subsequence theo thứ tự. Tập rỗng là tập con của mọi tập theo định nghĩa; nếu input rỗng có ý nghĩa nghiệp vụ “chưa được cấp quyền”, phải xử lý ở tầng xác thực thay vì tin rằng phép tập con chứng minh quyền hợp lệ.

### 7.6. $concatArrays không phải $setUnion

```javascript
{
  $concatArrays: ["$labels", "$incomingLabels"]
}
// ["web","priority","web","priority","express","priority"]
```

`$concatArrays` giữ lại số lần xuất hiện và thứ tự ghép các mảng. Nếu muốn một danh sách sự kiện/nhãn có thể lặp và thứ tự là quan trọng, dùng phép nối. Nếu muốn tập giá trị duy nhất không quan tâm thứ tự, dùng `$setUnion`.

### 7.7. Array lồng nhau không tự được “làm phẳng”

Ví dụ:

```javascript
{
  $setUnion: [
    [["A", "B"], "C"],
    [["A", "B"], "D"]
  ]
}
```

Mảng con `["A","B"]` được xem như **một phần tử** trong các toán tử set; chúng không tự đệ quy trải thành các phần tử `A` và `B`. Nếu đầu vào là array hai chiều hoặc array object, cần quyết định rõ **mức array** muốn hợp/giao và chuẩn hóa các phần tử trước khi áp phép tập hợp.

Giá trị bằng nhau cũng phụ thuộc quy tắc so sánh BSON/collation được áp dụng; với nhãn văn bản cần quy ước chữ hoa/thường, Unicode và cách so sánh thống nhất. Không mặc định một phép union sẽ tự chuyển `"Web"`, `"web"` và `"WEB"` thành cùng một nhãn nghiệp vụ.

## 8. $reduce kết hợp $setUnion: gom tag từ nhiều phần tử

Mỗi `items[]` chứa một array `tags[]` riêng. Yêu cầu: tạo một danh sách tag **duy nhất của toàn đơn hàng** mà không phải `$unwind` từng dòng.

```javascript
{
  $reduce: {
    input: "$items",
    initialValue: [],
    in: {
      $setUnion: [
        "$$value",
        { $ifNull: ["$$this.tags", []] }
      ]
    }
  }
}
```

Diễn tiến cho A-101:

| Lượt | Tags của dòng hiện tại | Tập đã tích lũy (không xét thứ tự) |
| --- | --- | --- |
| Khởi tạo | — | `{}` |
| SKU-A | fragile, promotion | `{fragile, promotion}` |
| SKU-B | gift | `{fragile, promotion, gift}` |
| SKU-C | promotion, priority | `{fragile, promotion, gift, priority}` |

Kết quả là một **array biểu diễn tập** gồm bốn nhãn duy nhất. Thứ tự JSON/BSON mà MongoDB trả ra **không thuộc hợp đồng**.

`$ifNull` ở đây gán mảng rỗng khi `tags` null/missing. Nhưng nếu `tags` là một String sai schema, `$ifNull` **không** chuyển String thành array; `$setUnion` có thể lỗi. Muốn bảo vệ cả sai kiểu, dùng `$isArray` cùng `$cond` (mục tiếp theo), hoặc chặn dữ liệu không hợp lệ theo chính sách ứng dụng.

### 8.1. Có thể dùng $map rồi $reduce không?

Có. Ví dụ `$map` trích array tags của từng item, sau đó `$reduce` hợp các mảng:

```javascript
{
  $reduce: {
    input: {
      $map: {
        input: "$items",
        as: "i",
        in: { $ifNull: ["$$i.tags", []] }
      }
    },
    initialValue: [],
    in: { $setUnion: ["$$value", "$$this"] }
  }
}
```

Cách này tách riêng **biến đổi** và **tích lũy**, hữu ích khi muốn inspect một stage trung gian. Cách reduce trực tiếp ở trên gọn hơn và thường dễ đọc nếu chỉ cần danh sách tags duy nhất.

### 8.2. Nếu cần giữ thứ tự xuất hiện và chỉ bỏ trùng?

Set operators không hứa giữ thứ tự. Nếu nghiệp vụ yêu cầu “lần đầu thấy nhãn nào thì giữ đúng vị trí đó”, hãy thiết kế một phép tích lũy có điều kiện, ví dụ `$reduce` với `$in` và `$concatArrays`:

```javascript
{
  $reduce: {
    input: ["web", "priority", "web", "express"],
    initialValue: [],
    in: {
      $cond: [
        { $in: ["$$this", "$$value"] },
        "$$value",
        { $concatArrays: ["$$value", ["$$this"]] }
      ]
    }
  }
}
// ["web", "priority", "express"]
```

Ví dụ này giữ thứ tự **xuất hiện đầu tiên**, với chi phí kiểm tra `$in` trong array đã tích lũy ở mỗi lượt. Với mảng lớn, cần xem xét hiệu năng và có thể chọn cấu trúc dữ liệu hoặc cách xử lý khác. Đây là hợp đồng khác với một phép hợp tập hợp đơn thuần.

## 9. Xử lý mảng rỗng, null, missing và sai kiểu

Một lỗi phổ biến khi xử lý dữ liệu legacy: người viết thử pipeline trên một document có `items: []`, thấy `$reduce` trả 0, rồi cho rằng document có `items: null` hoặc **không có field items** cũng trả 0. Điều này không đúng nếu không tự chuẩn hóa đầu vào.

### 9.1. Bảng hành vi cơ bản

| Input của expression | `$filter` | `$map` | `$reduce` |
| --- | --- | --- | --- |
| Array hợp lệ, có phần tử | Array con | Array đã biến đổi | Giá trị tích lũy |
| Array rỗng `[]` | `[]` | `[]` | `initialValue` |
| `null` hoặc field missing | `null` | `null` | `null` |
| Giá trị không phải array và không phải null/missing, như String | Lỗi | Lỗi | Lỗi |

Với các toán tử **set**, đầu vào cũng phải là array theo hợp đồng toán tử; không nên truyền String, number hoặc object rồi hy vọng MongoDB tự chuyển. Hành vi null/missing có thể khác giữa biểu thức set, accumulator của `$group` và các phiên bản; nên **chuẩn hóa input theo quy tắc ứng dụng** thay vì để nghiệp vụ phụ thuộc vào ngữ nghĩa null không được kiểm thử.

### 9.2. Chuẩn hóa chỉ null/missing bằng $ifNull

```javascript
{
  $filter: {
    input: { $ifNull: ["$items", []] },
    as: "item",
    cond: { $gte: ["$$item.qty", 2] }
  }
}
```

`$ifNull` gán `[]` nếu `items` là null/missing. Nhưng nếu `items` chứa String `"bad"`, `$ifNull` vẫn trả String đó; `$filter` tiếp tục bị lỗi vì đầu vào không phải array.

### 9.3. Chuẩn hóa kiểu dữ liệu bằng $isArray và $cond

```javascript
{
  $cond: [
    { $isArray: "$items" },
    "$items",
    []
  ]
}
```

Expression này chỉ giữ input khi nó là array; với null/missing/sai kiểu thì dùng array rỗng. Tạo field tạm `safeItems` ở stage đầu:

```javascript
{
  $set: {
    safeItems: {
      $cond: [
        { $isArray: "$items" },
        "$items",
        []
      ]
    }
  }
}
```

Sau đó mọi `$filter`, `$map` và `$reduce` dùng `"$safeItems"`, tránh lặp điều kiện trên toàn pipeline.

**Đánh đổi cần nêu rõ:** fallback `[]` giữ cho pipeline không lỗi, nhưng có thể **che mất chất lượng dữ liệu**. Với các dữ liệu tài chính, số lượng hàng hoặc quyền truy cập, hệ thống có thể cần gắn `invalidItems`, đếm record lỗi và đưa vào luồng xử lý riêng. Không coi `items: null` và `items: []` tương đương nếu hợp đồng nghiệp vụ cấm dữ liệu thiếu.

### 9.4. Chuẩn hóa cả array lồng trong phần tử

```javascript
{
  $reduce: {
    input: "$safeItems",
    initialValue: [],
    in: {
      $setUnion: [
        "$$value",
        {
          $cond: [
            { $isArray: "$$this.tags" },
            "$$this.tags",
            []
          ]
        }
      ]
    }
  }
}
```

Cách này xử lý cả trường hợp một dòng hàng có `tags` null/missing/sai kiểu. Tuy nhiên, các field `qty`/`unitPriceMinor` vẫn cần kiểm tra kiểu và ràng buộc riêng; bảo vệ array không tự bảo vệ phép nhân.

### 9.5. Không trộn undefined/missing với một phần tử có giá trị null

Ví dụ, `[null, "A"]` là **array chứa phần tử null**, khác với field `labels` mang giá trị `null`. Một số set operators có thể coi `null` nằm trong tập phần tử, và `$size` đếm nó là một phần tử. Quy tắc “bỏ null trong mảng nhãn” nếu cần phải được diễn đạt tường minh:

```javascript
{
  $filter: {
    input: "$safeLabels",
    as: "label",
    cond: { $ne: ["$$label", null] }
  }
}
```

Nếu mục tiêu là nhãn hợp lệ dạng String không rỗng, còn phải xét kiểu dữ liệu, khoảng trắng, chữ hoa/thường và quy chuẩn mã nhãn ở tầng dữ liệu.

## 10. Pipeline hoàn chỉnh: filter + map + reduce + tập hợp

Với dữ liệu ở mục 3, pipeline sau giữ mỗi order trong phạm vi tenant A, chuẩn hóa array, tính các array trung gian và tạo kết quả cho API:

```javascript
db.orders.aggregate([
  // 1. Giữ đúng tenant.
  {
    $match: {
      tenantId: "TENANT-A"
    }
  },

  // 2. Chuẩn hóa field thiếu/null/sai kiểu thành array rỗng.
  {
    $set: {
      safeItems: {
        $cond: [
          { $isArray: "$items" },
          "$items",
          []
        ]
      },
      safeLabels: {
        $cond: [
          { $isArray: "$labels" },
          "$labels",
          []
        ]
      },
      safeIncomingLabels: {
        $cond: [
          { $isArray: "$incomingLabels" },
          "$incomingLabels",
          []
        ]
      }
    }
  },

  // 3. Tạo các array và tập hợp trung gian.
  {
    $set: {
      eligibleItems: {
        $filter: {
          input: "$safeItems",
          as: "item",
          cond: { $gte: ["$$item.qty", 2] }
        }
      },
      lineTotals: {
        $map: {
          input: "$safeItems",
          as: "item",
          in: {
            $multiply: [
              "$$item.qty",
              "$$item.unitPriceMinor"
            ]
          }
        }
      },
      itemTags: {
        $reduce: {
          input: "$safeItems",
          initialValue: [],
          in: {
            $setUnion: [
              "$$value",
              {
                $cond: [
                  { $isArray: "$$this.tags" },
                  "$$this.tags",
                  []
                ]
              }
            ]
          }
        }
      },
      unionLabels: {
        $setUnion: ["$safeLabels", "$safeIncomingLabels"]
      },
      sharedLabels: {
        $setIntersection: ["$safeLabels", "$safeIncomingLabels"]
      },
      removedLabels: {
        $setDifference: ["$safeLabels", "$safeIncomingLabels"]
      },
      labelSetsEqual: {
        $setEquals: ["$safeLabels", "$safeIncomingLabels"]
      },
      labelsAllIncluded: {
        $setIsSubset: ["$safeLabels", "$safeIncomingLabels"]
      }
    }
  },

  // 4. Dùng các array vừa tạo để tính các tổng.
  {
    $set: {
      totalMinor: {
        $reduce: {
          input: "$lineTotals",
          initialValue: { $toLong: 0 },
          in: { $add: ["$$value", "$$this"] }
        }
      },
      eligibleSubtotalMinor: {
        $reduce: {
          input: "$eligibleItems",
          initialValue: { $toLong: 0 },
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.qty",
                  "$$this.unitPriceMinor"
                ]
              }
            ]
          }
        }
      }
    }
  },

  // 5. Chỉ trả các field phục vụ API.
  {
    $project: {
      _id: 1,
      status: 1,
      eligibleSkus: {
        $map: {
          input: "$eligibleItems",
          as: "i",
          in: "$$i.sku"
        }
      },
      lineTotals: 1,
      totalMinor: 1,
      eligibleSubtotalMinor: 1,
      itemTags: 1,
      unionLabels: 1,
      sharedLabels: 1,
      removedLabels: 1,
      labelSetsEqual: 1,
      labelsAllIncluded: 1
    }
  },
  { $sort: { _id: 1 } }
])
```

### 10.1. Kết quả kỳ vọng

Ở đây các array tạo bởi set operations được mô tả **như các tập không có thứ tự**:

| Document | `eligibleSkus` | `lineTotals` | `totalMinor` | `eligibleSubtotalMinor` |
| --- | --- | --- | ---: | ---: |
| A-101 | [SKU-A, SKU-C] | [24000, 5000, 21000] | 50000 | 45000 |
| A-102 | [] | [] | 0 | 0 |
| A-103 | [SKU-E] | [9000, 8000] | 17000 | 8000 |
| A-104 | [] | [] | 0 | 0 |

| Document | `itemTags` | `unionLabels` | `sharedLabels` | `removedLabels` |
| --- | --- | --- | --- | --- |
| A-101 | {fragile, promotion, gift, priority} | {web, priority, express} | {priority} | {web} |
| A-102 | {} | {web} | {} | {} |
| A-103 | {express, priority} | {app, express, priority} | {express} | {app} |
| A-104 | {} | {web} | {} | {} |

`labelSetsEqual` của bốn document đều là `false` theo seed hiện tại. `labelsAllIncluded` tương ứng: A-101=false (web không có trong incoming); A-102=true (tập rỗng); A-103=false (app không có trong incoming); A-104=true.

B-201 **không xuất hiện** trong kết quả vì `$match` ngay đầu pipeline. Đây là bất biến cần kiểm thử; việc tính set và reduce đúng nhưng bỏ filter tenant vẫn là một lỗi nghiêm trọng.

### 10.2. Theo dõi schema và số document

| Stage | Số document tenant A | Field quan trọng được tạo |
| --- | ---: | --- |
| Collection | 5 document tất cả tenants | `items`, `labels`, `incomingLabels` |
| `$match` | 4 | Schema nguồn, bỏ B-201 |
| `$set` chuẩn hóa | 4 | `safeItems`, `safeLabels`, `safeIncomingLabels` |
| `$set` array operators | 4 | `eligibleItems`, `lineTotals`, `itemTags`, các set labels |
| `$set` reduce tổng | 4 | `totalMinor`, `eligibleSubtotalMinor` |
| `$project`/`$sort` | 4 | DTO báo cáo; không thay đổi document nguồn |

Mỗi `$map`/`$filter` làm việc bên trong một document, nên **không làm số document tăng theo số item**. Nếu thay bằng `$unwind: "$items"`, A-101 có thể tạo ba document ở giai đoạn đó, A-103 tạo hai, còn A-102/A-104 cần xử lý đặc biệt khi array rỗng/null; khi group lại phải tránh đếm sai.

### 10.3. Vì sao stage thứ tư không được nhập tùy tiện vào stage thứ ba?

Trong ví dụ, `totalMinor` dùng `"$lineTotals"` và `eligibleSubtotalMinor` dùng `"$eligibleItems"` đã được tạo **ở stage thứ ba**. Không nên viết cùng một `$set` rồi giả định một field mới vừa tạo có thể được tham chiếu qua tên field trong chính stage đó như thể stage đã hoàn thành. Tách thành hai `$set` làm **phụ thuộc giữa các bước** tường minh, dễ debug và kiểm thử.

## 11. Triển khai trong Spring Data MongoDB

Spring Data MongoDB cung cấp `Aggregation` và các builder để biểu diễn nhiều stage, cùng các lớp `ArrayOperators`, `ConditionalOperators`, `ArithmeticOperators`... cho các expression. Tên method/overload của những builder có thể khác nhau giữa các phiên bản Spring Data. Khi pipeline dùng nhiều expression lồng nhau, một cách học rõ ràng là **giữ cấu trúc BSON gốc** trong các `AggregationOperation` tường minh, sau đó tối ưu thành DSL khi đã kiểm thử hợp đồng.

### 11.1. Entity nguồn

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String status,
    List<OrderItem> items,
    List<String> labels,
    List<String> incomingLabels
) {
    public record OrderItem(
        String sku,
        int qty,
        long unitPriceMinor,
        List<String> tags
    ) {}
}
```

Với `A-104` có `items: null`, record `items` có thể nhận null; bản thân việc Java khai báo `List<OrderItem>` **không làm MongoDB tự coi null là array rỗng**. Pipeline xử lý null bằng `$isArray`/`$cond` trước khi áp các biểu thức array.

### 11.2. MongoTemplate kết hợp typed match và BSON stages

File `OrderArrayAnalyticsService.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Service;

@Service
public class OrderArrayAnalyticsService {

    private final MongoTemplate template;

    public OrderArrayAnalyticsService(MongoTemplate template) {
        this.template = template;
    }

    // Chỉ dùng với JSON stage tĩnh và tin cậy do ứng dụng viết.
    private static AggregationOperation stage(String json) {
        return context -> Document.parse(json);
    }

    public List<Document> summaries(String permittedTenantId) {
        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant không hợp lệ");
        }

        Aggregation aggregation = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("tenantId").is(permittedTenantId)
            ),

            stage("""
                {
                  "$set": {
                    "safeItems": {
                      "$cond": [
                        { "$isArray": "$items" }, "$items", []
                      ]
                    },
                    "safeLabels": {
                      "$cond": [
                        { "$isArray": "$labels" }, "$labels", []
                      ]
                    },
                    "safeIncomingLabels": {
                      "$cond": [
                        { "$isArray": "$incomingLabels" },
                        "$incomingLabels", []
                      ]
                    }
                  }
                }
                """),

            stage("""
                {
                  "$set": {
                    "eligibleItems": {
                      "$filter": {
                        "input": "$safeItems",
                        "as": "i",
                        "cond": { "$gte": ["$$i.qty", 2] }
                      }
                    },
                    "lineTotals": {
                      "$map": {
                        "input": "$safeItems",
                        "as": "i",
                        "in": {
                          "$multiply": [
                            "$$i.qty", "$$i.unitPriceMinor"
                          ]
                        }
                      }
                    },
                    "itemTags": {
                      "$reduce": {
                        "input": "$safeItems",
                        "initialValue": [],
                        "in": {
                          "$setUnion": [
                            "$$value",
                            {
                              "$cond": [
                                { "$isArray": "$$this.tags" },
                                "$$this.tags", []
                              ]
                            }
                          ]
                        }
                      }
                    },
                    "unionLabels": {
                      "$setUnion": [
                        "$safeLabels", "$safeIncomingLabels"
                      ]
                    },
                    "sharedLabels": {
                      "$setIntersection": [
                        "$safeLabels", "$safeIncomingLabels"
                      ]
                    },
                    "removedLabels": {
                      "$setDifference": [
                        "$safeLabels", "$safeIncomingLabels"
                      ]
                    },
                    "labelSetsEqual": {
                      "$setEquals": [
                        "$safeLabels", "$safeIncomingLabels"
                      ]
                    },
                    "labelsAllIncluded": {
                      "$setIsSubset": [
                        "$safeLabels", "$safeIncomingLabels"
                      ]
                    }
                  }
                }
                """),

            stage("""
                {
                  "$set": {
                    "totalMinor": {
                      "$reduce": {
                        "input": "$lineTotals",
                        "initialValue": { "$toLong": 0 },
                        "in": { "$add": ["$$value", "$$this"] }
                      }
                    },
                    "eligibleSubtotalMinor": {
                      "$reduce": {
                        "input": "$eligibleItems",
                        "initialValue": { "$toLong": 0 },
                        "in": {
                          "$add": [
                            "$$value",
                            {
                              "$multiply": [
                                "$$this.qty",
                                "$$this.unitPriceMinor"
                              ]
                            }
                          ]
                        }
                      }
                    }
                  }
                }
                """),

            stage("""
                {
                  "$project": {
                    "_id": 1,
                    "status": 1,
                    "eligibleSkus": {
                      "$map": {
                        "input": "$eligibleItems",
                        "as": "i",
                        "in": "$$i.sku"
                      }
                    },
                    "lineTotals": 1,
                    "totalMinor": 1,
                    "eligibleSubtotalMinor": 1,
                    "itemTags": 1,
                    "unionLabels": 1,
                    "sharedLabels": 1,
                    "removedLabels": 1,
                    "labelSetsEqual": 1,
                    "labelsAllIncluded": 1
                  }
                }
                """),

            Aggregation.sort(Sort.by("_id"))
        );

        AggregationResults<Document> results = template.aggregate(
            aggregation, "orders", Document.class);

        return results.getMappedResults();
    }
}
```

Ví dụ dùng Java 17+ và Spring Data MongoDB có `AggregationOperation`/`MongoTemplate.aggregate(...)`. `Document.parse(...)` đọc **JSON hợp lệ** (không phải JavaScript shell với `NumberLong(...)`); đó là lý do initial value dùng expression `"$toLong": 0` thay cho cú pháp `NumberLong(0)` của `mongosh`.

**Giới hạn của cách dùng raw stage:**

- Các chuỗi stage là **hằng số do ứng dụng viết**, không ghép JSON/field name từ request. Giá trị `permittedTenantId` được đưa vào `Criteria` để binding, không nối chuỗi.
- `Document.parse` ở ví dụ trả nguyên tên **field BSON**. Nếu Java entity dùng `@Field("unit_price_minor")` hoặc converter đặc biệt, các chuỗi `"unitPriceMinor"` trong raw JSON **không tự biến đổi theo property Java**. Phải sửa đúng tên BSON hoặc chuyển sang DSL có metadata mapping thích hợp.
- Stage raw trong ví dụ không nhất thiết có được mọi hỗ trợ mapping/validation của các builder typed. Cần kiểm thử BSON pipeline thực tế trên server và khi nâng cấp Spring Data.
- `AggregationResults<Document>` là **read model của kết quả**, không phải `OrderDocument` dùng để gọi `save`. Sau `$project`, kết quả đã thiếu nhiều field entity và mang các field tính toán không có trong entity.

### 11.3. DTO output khi đã chốt hợp đồng

Có thể chuyển kết quả `Document` thành DTO:

```java
import java.util.List;
import org.bson.Document;

public record OrderArraySummary(
    String id,
    String status,
    List<String> eligibleSkus,
    long totalMinor,
    long eligibleSubtotalMinor,
    List<String> itemTags,
    List<String> unionLabels
) {
    public static OrderArraySummary from(Document doc) {
        return new OrderArraySummary(
            doc.getString("_id"),
            doc.getString("status"),
            doc.getList("eligibleSkus", String.class),
            ((Number) doc.get("totalMinor")).longValue(),
            ((Number) doc.get("eligibleSubtotalMinor")).longValue(),
            doc.getList("itemTags", String.class),
            doc.getList("unionLabels", String.class)
        );
    }
}
```

Đối với output tài chính, đây là chuyển đổi kiểu cơ bản phục vụ bài học; production cần validate field tồn tại, xử lý overflow và bảo đảm đơn vị tiền tệ/kiểu BSON chính xác. Nếu kết quả mong muốn có thứ tự nhãn ổn định, **sort mảng trước khi trả API** thay vì tin thứ tự của `$setUnion`.

### 11.4. Repository @Aggregation khi pipeline tĩnh

`@Aggregation` phù hợp cho pipeline JSON **cố định và ngắn hơn**, chẳng hạn trả các SKU đủ điều kiện theo tenant:

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0 } }",
        """
        {
          '$project': {
            '_id': 1,
            'eligibleSkus': {
              '$map': {
                'input': {
                  '$filter': {
                    'input': { '$ifNull': ['$items', []] },
                    'as': 'i',
                    'cond': { '$gte': ['$$i.qty', 2] }
                  }
                },
                'as': 'selected',
                'in': '$$selected.sku'
              }
            }
          }
        }
        """
    })
    List<Document> findEligibleSkus(String tenantId);
}
```

`?0` bind giá trị tenant theo tham số vị trí; `$$i`/`$$selected` là biến aggregation của MongoDB và **không** phải placeholder Java. `$ifNull` chỉ bảo vệ null/missing trong đoạn annotation này; nếu schema có thể lưu String thay cho array, cần dùng `$isArray` như pipeline chính.

**Phân biệt hai tên `Aggregation` trong Java:** `org.springframework.data.mongodb.repository.Aggregation` là annotation cho repository; `org.springframework.data.mongodb.core.aggregation.Aggregation` là class xây pipeline. Tránh import nhầm khi viết code.

### 11.5. Không phải mọi phép tính array đều cần aggregation

Nếu chỉ muốn tìm đơn **có ít nhất một item** thỏa điều kiện, filter thông thường với `Criteria.elemMatch(...)` có thể đơn giản hơn:

```java
Query query = Query.query(
    Criteria.where("tenantId").is(permittedTenantId)
        .and("items")
        .elemMatch(Criteria.where("qty").gte(2)));
```

Đây là truy vấn **chọn document**, không trả một array `eligibleItems` đã cắt bớt. `$filter` phù hợp khi muốn **giữ và trả phần tử được chọn trong kết quả**; `$elemMatch` phù hợp khi muốn **quyết định document có khớp không**. Hai cách không tự thay thế nhau.

## 12. Kiểm thử tích hợp trên BSON thực

Mock `MongoTemplate` không chứng minh MongoDB hiểu đúng `$$this`, `$reduce`, `$setUnion` hoặc xử lý null. Cần kiểm thử với một **MongoDB server riêng** và chèn dữ liệu BSON có array lồng nhau thực sự. `@DataMongoTest` và Testcontainers là một cách tổ chức phù hợp khi dự án đã cấu hình được test connection.

### 12.1. Tạo fixture có thứ tự, duplicate, null và tenant khác

File `OrderArrayAggregationTest.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class OrderArrayAggregationTest {

    @Autowired
    MongoTemplate template;

    private static Document item(
            String sku, int qty, long price, String... tags) {
        return new Document("sku", sku)
            .append("qty", qty)
            .append("unitPriceMinor", price)
            .append("tags", List.of(tags));
    }

    private static Document order(
            String id,
            String tenantId,
            Object items,
            Object labels,
            List<String> incomingLabels) {
        return new Document("_id", id)
            .append("tenantId", tenantId)
            .append("status", "PAID")
            .append("items", items)
            .append("labels", labels)
            .append("incomingLabels", incomingLabels);
    }

    private OrderArrayAnalyticsService service() {
        return new OrderArrayAnalyticsService(template);
    }

    private Document summary(String tenantId, String id) {
        return service().summaries(tenantId).stream()
            .filter(row -> id.equals(row.getString("_id")))
            .findFirst()
            .orElseThrow();
    }

    @BeforeEach
    void seed() {
        // TUYỆT ĐỐI chỉ chạy trên database test cô lập.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        collection.insertMany(List.of(
            order("A-101", "TENANT-A", List.of(
                    item("SKU-A", 2, 12000L,
                        "fragile", "promotion"),
                    item("SKU-B", 1, 5000L, "gift"),
                    item("SKU-C", 3, 7000L,
                        "promotion", "priority")),
                List.of("web", "priority", "web"),
                List.of("priority", "express", "priority")),

            order("A-102", "TENANT-A",
                List.of(), List.of(), List.of("web")),

            order("A-103", "TENANT-A", List.of(
                    item("SKU-D", 1, 9000L, "express"),
                    item("SKU-E", 4, 2000L,
                        "priority", "express")),
                List.of("app", "express"),
                List.of("express", "priority")),

            order("A-104", "TENANT-A",
                null, null, List.of("web")),

            order("B-201", "TENANT-B", List.of(
                    item("SKU-Z", 100, 100000L, "private")),
                List.of("private"),
                List.of("private", "priority"))
        ));
    }

    @Test
    void filterAndMapKeepOrderButRemoveIneligibleItems() {
        Document a = summary("TENANT-A", "A-101");

        assertThat(a.getList("eligibleSkus", String.class))
            .containsExactly("SKU-A", "SKU-C");

        List<Number> lineTotals =
            a.getList("lineTotals", Number.class);

        assertThat(lineTotals.stream()
                .mapToLong(Number::longValue)
                .toArray())
            .containsExactly(24000L, 5000L, 21000L);

        assertThat(a.get("totalMinor", Number.class)
                .longValue())
            .isEqualTo(50000L);
        assertThat(a.get("eligibleSubtotalMinor", Number.class)
                .longValue())
            .isEqualTo(45000L);
    }

    @Test
    void reduceWorksForAnotherOrder() {
        Document a = summary("TENANT-A", "A-103");

        assertThat(a.getList("eligibleSkus", String.class))
            .containsExactly("SKU-E");
        assertThat(a.get("totalMinor", Number.class)
                .longValue())
            .isEqualTo(17000L);
        assertThat(a.get("eligibleSubtotalMinor", Number.class)
                .longValue())
            .isEqualTo(8000L);
    }

    @Test
    void setOperatorsIgnoreDuplicatesAndNotPromiseOrder() {
        Document a = summary("TENANT-A", "A-101");

        assertThat(a.getList("itemTags", String.class))
            .containsExactlyInAnyOrder(
                "fragile", "promotion", "gift", "priority");
        assertThat(a.getList("unionLabels", String.class))
            .containsExactlyInAnyOrder(
                "web", "priority", "express");
        assertThat(a.getList("sharedLabels", String.class))
            .containsExactlyInAnyOrder("priority");
        assertThat(a.getList("removedLabels", String.class))
            .containsExactlyInAnyOrder("web");
        assertThat(a.getBoolean("labelSetsEqual")).isFalse();
        assertThat(a.getBoolean("labelsAllIncluded")).isFalse();
    }

    @Test
    void emptyAndNullInputAreNormalizedByContract() {
        for (String id : List.of("A-102", "A-104")) {
            Document row = summary("TENANT-A", id);

            assertThat(row.getList("eligibleSkus", String.class))
                .isEmpty();
            assertThat(row.getList("lineTotals", Number.class))
                .isEmpty();
            assertThat(row.getList("itemTags", String.class))
                .isEmpty();
            assertThat(row.get("totalMinor", Number.class)
                    .longValue())
                .isZero();
            assertThat(row.getBoolean("labelsAllIncluded")).isTrue();
        }
    }

    @Test
    void aggregationMustNotIncludeOtherTenant() {
        List<Document> a = service().summaries("TENANT-A");

        assertThat(a).hasSize(4);
        assertThat(a)
            .extracting(row -> row.getString("_id"))
            .containsExactly("A-101", "A-102", "A-103", "A-104");

        List<Document> b = service().summaries("TENANT-B");
        assertThat(b).hasSize(1);
        assertThat(b.get(0).getString("_id")).isEqualTo("B-201");
        assertThat(b.get(0).get("totalMinor", Number.class)
                .longValue())
            .isEqualTo(10000000L);
    }

    @Test
    void aggregationDoesNotModifyStoredOrder() {
        service().summaries("TENANT-A");

        Document stored = template.getCollection("orders")
            .find(new Document("_id", "A-101"))
            .first();

        assertThat(stored).isNotNull();
        assertThat(stored.getList("labels", String.class))
            .containsExactly("web", "priority", "web");
        assertThat(stored.containsKey("totalMinor")).isFalse();
        assertThat(stored.containsKey("eligibleItems")).isFalse();
    }
}
```

Các phép assert `containsExactly(...)` chỉ được dùng cho các array **có thứ tự theo hợp đồng** như `$filter` và `$map`. Với `$setUnion`, `$setIntersection`, `$setDifference`, test dùng `containsExactlyInAnyOrder(...)` vì MongoDB không cam kết thứ tự kết quả tập hợp.

**Cảnh báo thực thi:** `deleteMany(new Document())` sẽ xóa toàn bộ collection `orders` của database mà test kết nối. Phải cấu hình MongoDB **test cô lập**, không dùng production hoặc database chia sẻ. Ví dụ `@DataMongoTest` dùng package của dòng Spring Boot phổ biến; kiểm tra lại khi dự án đổi major version. Trong bước viết tài liệu này chưa chạy Gradle/test; đây là mã hướng dẫn cần được xác nhận trong môi trường dự án.

### 12.2. Kiểm thử trường hợp dữ liệu lỗi

Nên có thêm fixture:

```javascript
{
  _id: "A-BAD",
  tenantId: "TENANT-A",
  items: "not-an-array",
  labels: ["web", null, "web"],
  incomingLabels: ["app"]
}
```

Pipeline chính với `$isArray` sẽ biến `items` String thành `[]`. Nhưng nếu nghiệp vụ không cho phép một đơn không có items, test **không nên chỉ assert tổng = 0 rồi cho qua**: cần quy tắc đánh dấu invalid hoặc chủ động báo lỗi ở bước nhập dữ liệu.

Nếu một phần tử trong `items` chứa `qty: "2"` hoặc `unitPriceMinor: "12000"`, bảo vệ **kiểu array bên ngoài** vẫn không đảm bảo `$multiply` thành công. Cần test riêng kiểu phần tử, dùng schema validation, chuẩn hóa BSON hoặc biểu thức chuyển kiểu như `$convert` với `onError`/`onNull` theo chính sách.

### 12.3. Kiểm thử bổ sung theo ma trận

| Tình huống | Điều cần xác minh |
| --- | --- |
| Array có duplicate | `$filter`/`$map` giữ duplicate; set operators bỏ trùng |
| Array rỗng | `$reduce` trả `initialValue` |
| Field null/missing | `$isArray` + `$cond` tạo `[]` theo contract |
| Field không phải array | Pipeline có thể fail nếu không chuẩn hóa; không âm thầm nuốt lỗi nghiệp vụ |
| Các item thiếu tags | `itemTags` không lỗi khi đã kiểm tra `$isArray` |
| Các item thiếu giá/qty | Có validation/chính sách bỏ dòng hoặc báo lỗi, không tính doanh thu giả |
| Array lồng nhau | Set operators không tự làm phẳng nhiều cấp |
| Chữ hoa/chữ thường của tags | So sánh theo collation/quy chuẩn nhãn đã chọn |
| Phân quyền tenant | Không có B-201 khi truy vấn tenant A |
| API cần thứ tự tags | Không assert thứ tự của `$setUnion`; sort riêng |
| Dữ liệu lớn | Đo memory, docs examined, thời gian, kích thước output |
| Aggregation chỉ đọc | Không tạo field tạm trong BSON gốc |

## 13. $filter/$map/$reduce hay $unwind + $group?

Cùng một yêu cầu xử lý array đôi khi có nhiều cách triển khai. Không có một cách thắng cho mọi trường hợp:

| Nhu cầu | Array expressions thường phù hợp | `$unwind`/`$group` thường phù hợp |
| --- | --- | --- |
| Tính tổng tiền **trên từng document đơn hàng** | `$map` + `$reduce`, hoặc `$reduce` trực tiếp | Có thể làm nhưng phải group lại theo order |
| Lấy các item có qty lớn bên trong từng order | `$filter` | `$unwind` + `$match` + `$group` khi cần biến đổi phức tạp |
| Tạo danh sách tags không trùng của từng order | `$reduce` + `$setUnion` | `$unwind` nhiều cấp + group khi cần phân tích tags sâu |
| Đếm tổng số lần xuất hiện SKU trên **mọi đơn** | Có thể tính một phần mỗi order | `$unwind` + `$group` theo SKU thường dễ diễn đạt |
| Nhóm hàng theo thuộc tính item và tính doanh thu toàn tenant | Khó khi cần group xuyên nhiều order | `$unwind` → `$group` phù hợp |
| Muốn giữ nguyên mỗi order thành một document đầu ra | Dễ giữ cardinality | Phải group lại sau khi unwind |
| Dữ liệu có array cực lớn hoặc document kết quả quá rộng | Phải đánh giá memory/kích thước document | Có thể stream thành nhiều document hơn nhưng cần tính chi phí group/sort |

### 13.1. Ví dụ đối chiếu: tổng theo từng đơn bằng unwind

```javascript
db.orders.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$_id",
      totalMinor: {
        $sum: {
          $multiply: ["$items.qty", "$items.unitPriceMinor"]
        }
      }
    }
  }
])
```

Với cách viết này, A-101 và A-103 tạo tổng phù hợp; **A-102 (mảng rỗng) và A-104 (null)** có thể biến mất do `$unwind` mặc định không giữ chúng. Nếu hợp đồng cần cả những đơn không có item và tổng 0, phải dùng `preserveNullAndEmptyArrays` cùng xử lý null/số, hoặc chọn `$reduce` trên array đã được chuẩn hóa như pipeline chính.

### 13.2. Khi cần group trên từng item của nhiều đơn

Ví dụ thống kê số lượng bán theo SKU trên mọi đơn đã thanh toán:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: "PAID"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      quantitySold: { $sum: "$items.qty" },
      grossMinor: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPriceMinor"
          ]
        }
      }
    }
  },
  { $sort: { quantitySold: -1, _id: 1 } }
])
```

Đây là phân tích **xuyên document theo SKU**, khác với `$reduce` tính **từng document order**. Đừng nhầm hai bài toán rồi chọn API dựa trên tên operator.

### 13.3. $size và số phần tử sau filter

Muốn đếm số dòng đủ điều kiện mà vẫn trả một document trên mỗi order:

```javascript
{
  $size: {
    $filter: {
      input: "$safeItems",
      as: "item",
      cond: { $gte: ["$$item.qty", 2] }
    }
  }
}
```

A-101 có 2 dòng đủ điều kiện, A-103 có 1. `$size` đếm số **phần tử**, không cộng `qty`. Nếu cần tổng số đơn vị sản phẩm, dùng `$reduce` cộng `qty` của các dòng đã lọc.

## 14. Chẩn đoán hiệu năng và kế hoạch thực thi

Với các biểu thức array, MongoDB phải đánh giá trên các phần tử của **những document đã đi qua `$match`**. Một index có thể giúp chọn nhanh document phù hợp, nhưng không có nghĩa `$map`/`$reduce` tự có một index cho từng phần tử trung gian.

### 14.1. Filter sớm theo các field document

Index ứng viên cho truy vấn thường xuyên theo tenant và status:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_order_tenant_status" }
)
```

Nếu báo cáo chỉ tính đơn PAID, bắt đầu:

```javascript
{
  $match: {
    tenantId: "TENANT-A",
    status: "PAID"
  }
}
```

Điều đó giúp giảm số document phải xử lý array. Tuy nhiên, nếu nghiệp vụ cần cả NEW và PAID như ví dụ, không được thêm filter PAID chỉ để tối ưu rồi vô tình đổi kết quả.

### 14.2. $filter không tự thay cho $match có index

Pipeline này:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $project: {
      eligibleItems: {
        $filter: {
          input: "$items",
          as: "i",
          cond: { $gte: ["$$i.qty", 2] }
        }
      }
    }
  }
])
```

vẫn đưa các đơn A-102/A-104 qua pipeline rồi tạo array rỗng hoặc null tùy cách xử lý input. Nếu chỉ cần **những document có ít nhất một item đủ điều kiện**, có thể đưa predicate vào `$match` trước:

```javascript
{
  $match: {
    tenantId: "TENANT-A",
    items: { $elemMatch: { qty: { $gte: 2 } } }
  }
}
```

Sau đó vẫn có thể dùng `$filter` để trả **chỉ các item khớp**. Nếu có multikey index phù hợp trên `items.qty` cùng tenant, một phần filter có thể tận dụng index. Nhưng `$elemMatch` chọn **document**, còn `$filter` tạo **array con**; không đánh đồng.

### 14.3. Dùng explain trên pipeline thực tế

Ví dụ rút gọn để kiểm tra chi phí:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $project: {
      totalMinor: {
        $reduce: {
          input: {
            $cond: [
              { $isArray: "$items" },
              "$items",
              []
            ]
          },
          initialValue: { $toLong: 0 },
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.qty",
                  "$$this.unitPriceMinor"
                ]
              }
            ]
          }
        }
      }
    }
  }
])
```

Theo dõi số document/keys được xét, index scan/collection scan, thời gian thực thi, kích thước kết quả và mức tải server. `explain` có cách biểu diễn kế hoạch thay đổi giữa các phiên bản MongoDB; không suy luận “không thấy tên stage tường minh” là stage đã bị bỏ qua. Optimizer có thể kết hợp/đẩy các stage khi ngữ nghĩa cho phép.

### 14.4. Array lớn và chi phí lặp

- `$map`/`$filter` phải xử lý các phần tử trong array đầu vào cho từng document đã khớp.
- `$reduce` với accumulator là một array và `$concatArrays` liên tục có thể tạo nhiều bản sao trung gian; không phù hợp với array cực lớn nếu chưa đo.
- Pattern giữ thứ tự và loại trùng bằng `$in` trên array tích lũy có thể tốn nhiều phép so sánh khi danh sách lớn.
- `$setUnion` bỏ trùng nhưng có chi phí xử lý tập hợp; không nên tạo hàng trăm field trung gian rồi trả tất cả qua API nếu client chỉ cần hai số tổng.
- Nếu array/đầu ra quá lớn, phải xem giới hạn BSON document, bộ nhớ pipeline và khả năng phân tích theo nhiều document. Không bật `allowDiskUse` rồi mặc định mọi expression array sẽ trở nên rẻ.

### 14.5. Khi API cần kết quả có thứ tự từ set

Các phép tập hợp không bảo đảm thứ tự. Với MongoDB server hỗ trợ `$sortArray` (được giới thiệu ở MongoDB 5.2), có thể sắp xếp kết quả set:

```javascript
{
  $sortArray: {
    input: "$unionLabels",
    sortBy: 1
  }
}
```

Đoạn này phải đặt **sau stage đã tạo `unionLabels`**, ví dụ trong một `$set` mới. Nếu ứng dụng phải hỗ trợ server cũ chưa có `$sortArray`, cần một phương án sort khác hoặc chuẩn hóa ở Java. Đừng viết test khẳng định thứ tự ngẫu nhiên của set union là một hợp đồng có thể dựa vào.

## 15. Bảo mật, tính nhất quán và dữ liệu nhạy cảm

Array có thể mang **phân quyền, nhãn nhạy cảm hoặc khóa nghiệp vụ**. Các phép tập hợp rất hữu ích để tính giao/quyền chung, nhưng không thể thay thế kiểm tra an toàn:

### 15.1. Tập rỗng là tập con của mọi tập

```javascript
{
  $setIsSubset: [[], ["read", "write"]]
}
// true
```

Đây là kết quả đúng của lý thuyết tập hợp, nhưng nếu ứng dụng diễn giải “array yêu cầu quyền rỗng” là “người dùng hợp lệ”, nó có thể tạo sơ hở. **Phân quyền phải được thiết kế ở service/security layer**, không suy luận mọi kết quả true của set subset đều là một quyết định cho phép truy cập.

### 15.2. Thao tác với nhãn không được làm mất dữ liệu kiểm toán

`$setUnion` có thể bỏ trùng tags/labels, và `$setDifference` có thể chỉ ra tags bị loại. Nếu `labels` còn chứa thứ tự/số lần gắn nhãn dùng cho audit, không nên dùng kết quả set union rồi **ghi đè** lại array nguồn. Hãy tách read model báo cáo với update/migration theo hợp đồng dữ liệu.

### 15.3. Đọc aggregation không phải transaction snapshot xuyên nhiều lượt gọi

Pipeline đọc minh họa ở đây không cập nhật collection. Nhưng nếu thực hiện một pipeline khác rồi ghi ra collection bằng `$merge`/`$out`, đó là hành động ghi cần quyền và cơ chế consistency riêng. Nếu chạy nhiều truy vấn/aggregation tách biệt khi dữ liệu thay đổi đồng thời, đừng mặc định chúng phản ánh cùng một snapshot mà không có thiết kế read concern/transaction phù hợp.

### 15.4. Không ghép raw pipeline từ input

Trong Java service, chuỗi JSON stage là **hằng số nội bộ**, còn tenant được bind qua `Criteria`. Đừng cho client truyền tùy ý tên operator `$...`, một fragment JSON hoặc biểu thức aggregation rồi ghép vào `Document.parse(...)`. Nếu API cho lựa chọn field/điều kiện, hãy dùng **allowlist** tên field và các nhánh do ứng dụng kiểm soát.

## 16. Lỗi thường gặp khi xử lý array

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `$map` trả null thay vì [] | Input array là null/missing | Chuẩn hóa bằng `$ifNull` hoặc `$isArray` + `$cond` |
| Aggregation lỗi với `input must be an array` | Field chứa String/object thay vì array | Validate BSON hoặc chuẩn hóa rõ ràng |
| `$reduce` trả null cho đơn không có items | Input null/missing không phải array rỗng | Truyền `[]` theo contract hoặc xử lý record lỗi |
| Tổng tiền luôn 0 hoặc thấp bất thường | Field qty/price thiếu, sai kiểu hoặc filter trước đó loại nhầm | Kiểm tra `$type`, dữ liệu trung gian và từng bước |
| `$$item.qty` không có giá trị | Viết sai `as` hoặc dùng `"$item.qty"` thay cho biến `"$$item.qty"` | Phân biệt field path `$` và biến cục bộ `$$` |
| Một field mới không đọc được ngay trong stage tạo nó | Tham chiếu field đầu ra trong cùng `$set` | Tách các stage theo thứ tự phụ thuộc |
| `$filter` vẫn trả document không có phần tử khớp | `$filter` chỉ thay array, không lọc document | Dùng `$match`/`$elemMatch` nếu muốn loại document |
| `$map` có số phần tử khác kỳ vọng | Đã dùng `$filter` trước đó hoặc input thiếu | Theo dõi cardinality sau từng expression |
| `$unwind` làm báo cáo đếm trùng | Một document được nhân theo số phần tử array | Group lại đúng khóa hoặc dùng array expression |
| `$setUnion` trả thứ tự khác mỗi lần | Set operators không cam kết thứ tự | Sort kết quả riêng khi API cần thứ tự |
| `$concatArrays` vẫn có nhãn trùng | Phép nối mảng không loại duplicate | Dùng `$setUnion` nếu thật sự cần tập giá trị duy nhất |
| `$setDifference` trả chiều ngược | Nhầm thứ tự A/B | Định nghĩa rõ “removed” = current trừ incoming |
| `$setIsSubset` trả true cho input rỗng | Tập rỗng là tập con mọi tập | Không dùng làm quyết định phân quyền khi input chưa validate |
| Tags là array của arrays nhưng union không làm phẳng | Set operators coi nested array là một phần tử | Chuẩn hóa/flatten đúng cấp dữ liệu trước |
| Đọc report vào entity nguồn bị sai | `$project` đã đổi schema output | Dùng `Document`/DTO phù hợp, không lưu lại partial entity |
| Chạy đúng trong mongosh nhưng sai trong Java | Raw BSON stage dùng tên field khác `@Field` của entity | Kiểm tra mapped BSON và converter trên dữ liệu thật |
| Index có mà pipeline vẫn chậm | `$filter`/`$reduce` phải duyệt array lớn, hoặc filter ít chọn lọc | Đo `explain`, giảm đầu vào, xem xét schema/index |
| Dữ liệu tenant khác xuất hiện trong report | `$match` thiếu tenant hoặc OR sai phạm vi | Kiểm tra tenant ở đầu và integration test anti-leak |

## 17. Checklist thiết kế một pipeline xử lý array

1. **Document nguồn biểu diễn gì?** Order, line item, shipment, permission record? Kết quả mong muốn giữ một document đầu ra cho mỗi nguồn hay nhóm xuyên collection?
2. **Array đầu vào có thể null/missing/sai kiểu không?** Đặt schema validation hoặc fallback rõ ràng; đừng mặc định array rỗng và null cùng nghĩa nghiệp vụ.
3. **Đang lọc document hay lọc phần tử?** `$match`/`$elemMatch` chọn document; `$filter` chọn phần tử trong array của từng document.
4. **Có cần thứ tự hoặc số lần xuất hiện không?** `$map`/`$filter` thường giữ thứ tự tương đối; set operators bỏ trùng và không bảo đảm thứ tự.
5. **Dùng biến thế nào?** `"$items"` là field trên document; `"$$item.qty"` là field của biến cục bộ; `$$value`/`$$this` dành cho `$reduce`.
6. **Cần một giá trị hay một array?** `$map` tạo array, `$reduce` tạo một giá trị bất kỳ.
7. **Mỗi stage tạo field nào?** Tách các stage nếu stage sau phải đọc field mới được tạo.
8. **Các phần tử có kiểu ổn định không?** Đặc biệt qty, tiền, ngày giờ và tags lồng nhau; validate hoặc dùng chuyển kiểu có chính sách lỗi.
9. **Có phạm vi tenant/quyền bắt buộc không?** Đặt `$match` đã xác thực sớm, kiểm thử với tenant khác.
10. **Đầu ra là DTO nào?** Không trả partial aggregation như entity đầy đủ để cập nhật lại document.
11. **Đã kiểm thử array rỗng, null, duplicate, nested và set order chưa?**
12. **Đã đo với dữ liệu lớn chưa?** Index ở stage lọc, bộ nhớ/số phần tử array, kích thước document kết quả, giải thích kế hoạch bằng `explain`.

## 18. Bài tập vận dụng

Một hệ thống vận chuyển lưu document:

```javascript
{
  _id: "SHIP-001",
  tenantId: "TENANT-X",
  state: "READY",
  packages: [
    {
      code: "PK-A",
      weightGram: 1200,
      feePerKgMinor: NumberLong(15000),
      labels: ["fragile", "cold"]
    },
    {
      code: "PK-B",
      weightGram: 500,
      feePerKgMinor: NumberLong(20000),
      labels: ["cold", "priority"]
    },
    {
      code: "PK-C",
      weightGram: 2000,
      feePerKgMinor: NumberLong(10000),
      labels: ["fragile"]
    }
  ],
  currentLabels: ["cold", "priority", "cold"],
  desiredLabels: ["priority", "insured"]
}
```

Quy ước bài tập: với mỗi kiện, phí được tính bằng `weightGram / 1000 × feePerKgMinor`; bài tập dùng số nguyên gram và giả định kết quả phép chia/phép tính được xử lý theo quy tắc tiền tệ do hệ thống quy định. Trong production, cần quyết định rõ làm tròn và kiểu Decimal128 nếu có phần lẻ; không tự động dùng Double rồi đưa vào thanh toán.

Yêu cầu:

1. Dùng `$match` giới hạn `tenantId=TENANT-X` và `state=READY`.
2. Dùng `$filter` giữ kiện có `weightGram >= 1000`; dự đoán mã kiện sau lọc.
3. Dùng `$map` tạo array object gồm `code` và `feeMinor` của từng kiện.
4. Dùng `$reduce` cộng tổng `feeMinor`, xác định quy tắc làm tròn trước khi cộng.
5. Dùng `$reduce` kết hợp `$setUnion` lấy tập labels xuất hiện ở **bất kỳ kiện nào**.
6. Dùng `$setUnion`, `$setIntersection` và `$setDifference` so sánh currentLabels với desiredLabels; phân biệt “cần thêm” và “cần bỏ”.
7. Kiểm tra `$setIsSubset` để biết mọi currentLabel có nằm trong desiredLabels hay không. Giải thích vì sao array rỗng có thể trả true.
8. Xử lý một shipment không có `packages`, một shipment có `packages: []` và một shipment có `packages: "bad"`; xác định contract fallback hay lỗi.
9. Chuyển pipeline sang `MongoTemplate.aggregate(...)` hoặc repository `@Aggregation`, viết test gồm document của tenant khác.
10. Đo chi phí của pipeline khi một shipment có 50.000 phần tử và cân nhắc schema/processing strategy khác nếu output quá lớn.

### 18.1. Định hướng lời giải: chọn lọc và tính phí

Giữ kiện nặng ít nhất 1000 gram:

```javascript
{
  $filter: {
    input: {
      $cond: [
        { $isArray: "$packages" },
        "$packages",
        []
      ]
    },
    as: "p",
    cond: { $gte: ["$$p.weightGram", 1000] }
  }
}
// PK-A và PK-C
```

Tạo phí từng kiện với `$map`:

```javascript
{
  $map: {
    input: "$packages",
    as: "p",
    in: {
      code: "$$p.code",
      feeMinor: {
        $multiply: [
          { $divide: ["$$p.weightGram", 1000] },
          "$$p.feePerKgMinor"
        ]
      }
    }
  }
}
```

Trong dữ liệu ví dụ, phí tính theo công thức là **PK-A = 18.000**, **PK-B = 10.000**, **PK-C = 20.000**, tổng **48.000**. Đây là phép tính mô phỏng; dùng Decimal128/quy tắc làm tròn khi triển khai yêu cầu tiền thật. Nếu chuẩn hóa input thành `safePackages` ở stage trước, nên thay `"$packages"` bằng `"$safePackages"` cho cả map và reduce để không lỗi với dữ liệu legacy.

### 18.2. Định hướng lời giải: tập nhãn

- Hợp các nhãn ở mọi kiện: `{fragile, cold, priority}`.
- `currentLabels` hợp `desiredLabels`: `{cold, priority, insured}`.
- Giao current/desired: `{priority}`.
- Current trừ desired (cần bỏ): `{cold}`.
- Desired trừ current (cần thêm): `{insured}`.

Thứ tự các phần tử của kết quả tập hợp không được bảo đảm. Khi test, hãy so sánh theo tập hoặc sort tường minh.

## 19. Tài liệu tham khảo

- Spring Data MongoDB — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): pipeline và mapping trong Spring Data.
- Spring Data MongoDB — [Aggregation API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/Aggregation.html): xây các stage qua `MongoTemplate`.
- Spring Data MongoDB — [ArrayOperators API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/ArrayOperators.html): các builder array expressions của Spring Data.
- MongoDB Manual — [`$filter`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/), [`$map`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/), [`$reduce`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/reduce/): cú pháp, biến và hành vi với array.
- MongoDB Manual — [Set Expression Operators](https://www.mongodb.com/docs/manual/reference/operator/aggregation/set/): union, intersection, difference, equality, subset.
- MongoDB Manual — [`$isArray`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/isArray/), [`$cond`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/cond/): kiểm tra kiểu và chọn fallback.
- MongoDB Manual — [`$unwind`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/): chuyển phần tử array thành document tạm.
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/): kế hoạch và thứ tự stage.
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): thống kê truy vấn và hiệu năng.

## Ghi nhớ

**`$filter` giữ lại phần tử phù hợp; `$map` biến đổi từng phần tử; `$reduce` tích lũy thành một giá trị; các toán tử tập hợp hợp/giao/trừ/so sánh array theo ngữ nghĩa set, loại trùng nhưng không bảo đảm thứ tự.** Với document MongoDB thực tế, phải phân biệt `[]`, `null`, field thiếu, kiểu BSON sai và array lồng nhau. Khi chuyển sang Spring Data MongoDB, giữ đúng thứ tự các stage, kiểm tra biến `$$this`/`$$value`, dùng DTO cho output, bắt buộc giới hạn tenant, test trên BSON thật và đo hiệu năng trước khi đưa pipeline vào sản xuất.
