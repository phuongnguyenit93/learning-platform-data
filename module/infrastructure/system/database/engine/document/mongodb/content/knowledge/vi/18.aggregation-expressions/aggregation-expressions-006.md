# Xử lý mảng bằng `$map`, `$filter`, `$reduce` và toán tử tập hợp trong MongoDB

## 1. Vì sao cần xử lý mảng ngay trong aggregation?

Trong mô hình document MongoDB, mảng thường được dùng để lưu dữ liệu có liên hệ chặt với document cha: các dòng hàng của đơn hàng, nhãn của bài viết, vai trò của người dùng, kết quả đo hoặc lịch sử sự kiện ngắn.

Ví dụ một đơn hàng:

```javascript
{
  _id: "O01",
  customerId: "C01",
  status: "PAID",
  tags: ["vip", "sale", "vip"],
  items: [
    { sku: "A", qty: 2, unitPrice: 100, active: true },
    { sku: "B", qty: 1, unitPrice: 200, active: false }
  ]
}
```

Từ document này, ứng dụng có thể cần:

- **Biến đổi từng dòng hàng** thành một object chứa `sku` và `lineTotal = qty × unitPrice`.
- **Lọc** chỉ những dòng hàng đang hoạt động (`active: true`).
- **Cộng dồn** thành tổng tiền hoặc đếm số dòng hàng ngay trong một document.
- **Loại giá trị trùng** trong `tags` hoặc so sánh các tag với một tập nhãn mục tiêu.
- **Kết hợp** nhiều mảng tag, tìm giao, hiệu, kiểm tra hai tập bằng nhau hoặc một tập là tập con.

MongoDB cung cấp các **aggregation expressions** đáp ứng những công việc đó:

| Nhóm | Toán tử | Vai trò |
|---|---|---|
| Biến đổi phần tử | `$map` | Ánh xạ mỗi phần tử sang một giá trị mới |
| Lựa chọn phần tử | `$filter` | Giữ phần tử thỏa điều kiện Boolean |
| Gộp/tích lũy | `$reduce` | Duyệt mảng từ trái sang phải, mang theo giá trị tích lũy |
| Phép toán tập hợp | `$setUnion`, `$setIntersection`, `$setDifference` | Hợp, giao, hiệu các mảng khi coi chúng là tập hợp |
| So sánh tập hợp | `$setEquals`, `$setIsSubset` | So sánh tập giá trị, bỏ qua thứ tự và phần tử trùng |
| Kiểm tra chân trị tập hợp | `$anyElementTrue`, `$allElementsTrue` | Kiểm tra có phần tử đúng hay tất cả phần tử đúng |

**Điểm quan trọng:** `$map`, `$filter`, `$reduce` và các toán tử tập hợp ở đây là **biểu thức tính giá trị**, không phải pipeline stage. Chúng thường được đặt trong `$project`, `$set` hoặc các nơi chấp nhận aggregation expressions.

```text
                  Một document chứa mảng items
                              |
            +-----------------+------------------+
            |                 |                  |
          $map              $filter           $reduce
            |                 |                  |
   mảng giá trị mới   mảng phần tử đã lọc   một giá trị tích lũy
            |                 |                  |
            +-----------------+------------------+
                              |
                    $project / $set
                              |
                    document kết quả

       tags[] + marketingTags[] --> $setUnion / $setIntersection / ...
```

Phần còn lại đi từ cú pháp đơn giản tới cách kết hợp nhiều toán tử và các lưu ý về tính đúng, hiệu năng, kiểu dữ liệu.

## 2. Chuẩn bị bộ dữ liệu thực hành

Các ví dụ sử dụng **mongosh** và collection thử nghiệm `aggArrayLesson`. Chỉ chèn một lần vào collection chưa có các `_id` bên dưới:

```javascript
db.aggArrayLesson.insertMany([
  {
    _id: "O01",
    customerId: "C01",
    status: "PAID",
    tags: ["vip", "sale", "vip"],
    coupons: ["WELCOME", "SALE"],
    points: [5, 7, 9],
    items: [
      { sku: "A", qty: 2, unitPrice: 100, active: true },
      { sku: "B", qty: 1, unitPrice: 200, active: false }
    ]
  },
  {
    _id: "O02",
    customerId: "C02",
    status: "PAID",
    tags: ["sale", "new"],
    coupons: ["SALE", "FREESHIP"],
    points: [10, 8],
    items: [
      { sku: "C", qty: 3, unitPrice: 50, active: true }
    ]
  },
  {
    _id: "O03",
    customerId: "C03",
    status: "PENDING",
    tags: [],
    coupons: [],
    points: [],
    items: []
  },
  {
    _id: "O04",
    customerId: "C04",
    status: "PAID",
    tags: ["vip", "new"],
    coupons: ["WELCOME"],
    points: [3],
    items: [
      { sku: "A", qty: 1, unitPrice: 100, active: true },
      { sku: "D", qty: 2, unitPrice: 80, active: true }
    ]
  },
  {
    _id: "O05",
    customerId: "C05",
    status: "PENDING",
    tags: null,
    items: null
    // coupons và points cố ý không tồn tại.
  },
  {
    _id: "O06",
    customerId: "C06",
    status: "PAID",
    coupons: ["SALE", "WELCOME", "SALE"],
    points: [2, 4],
    items: [
      { sku: "B", qty: 1, unitPrice: 200, active: false }
    ]
    // tags cố ý không tồn tại.
  }
]);
```

Các giá trị tiền được để dưới dạng **số nguyên nhỏ** cho dễ theo dõi phép tính. Với ứng dụng thương mại thật, cần quyết định cách biểu diễn tiền phù hợp, chẳng hạn số nguyên theo đơn vị nhỏ nhất hoặc BSON Decimal128 và cách làm tròn.

| Đơn | `tags` | Số dòng hàng | Tổng `qty × unitPrice` | Dòng hàng `active: true` |
|---|---|---:|---:|---:|
| O01 | vip, sale, vip | 2 | 400 | A |
| O02 | sale, new | 1 | 150 | C |
| O03 | mảng rỗng | 0 | 0 | Không có |
| O04 | vip, new | 2 | 260 | A, D |
| O05 | null | Không có mảng hợp lệ | Chưa xác định nếu không chuẩn hóa | Không có |
| O06 | Trường thiếu | 1 | 200 | Không có |

Với những ví dụ cần mảng hợp lệ, ta thường dùng `$ifNull` để xử lý null/missing thành `[]`. Nếu document chứa **String, Number hoặc Object thay vì Array**, `$ifNull` không sửa sai kiểu; phần 7 sẽ trình bày cách kiểm tra bằng `$isArray`.

## 3. `$map`: biến đổi từng phần tử và giữ cấu trúc mảng

`$map` áp dụng một biểu thức cho **từng phần tử** của mảng đầu vào và trả về **mảng kết quả** có các phần tử tương ứng.

### 3.1. Cú pháp

```javascript
{
  $map: {
    input: <arrayExpression>,
    as: "element",
    in: <expressionUsingElement>
  }
}
```

Ý nghĩa các trường:

- `input`: biểu thức trả về mảng cần duyệt.
- `as`: tên biến cho mỗi phần tử; là tùy chọn, nếu bỏ qua có thể dùng biến mặc định `$$this`.
- `in`: biểu thức tính **giá trị đầu ra cho từng phần tử**; tham chiếu biến bằng cú pháp `$$tenBien`.

Ví dụ một mảng số:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      _id: 1,
      doubledPoints: {
        $map: {
          input: "$points",
          as: "point",
          in: { $multiply: ["$$point", 2] }
        }
      }
    }
  }
]);
```

Kết quả:

```javascript
{
  _id: "O01",
  doubledPoints: [10, 14, 18]
}
```

`$map` không sửa mảng `points` đang lưu trong database; ở đây `$project` chỉ **tạo trường kết quả truy vấn**.

### 3.2. Biến đổi mảng embedded documents

Một trường hợp phổ biến hơn là tạo bản xem trước của từng dòng hàng:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      _id: 1,
      lines: {
        $map: {
          input: "$items",
          as: "item",
          in: {
            sku: "$$item.sku",
            quantity: "$$item.qty",
            lineTotal: {
              $multiply: [
                "$$item.qty",
                "$$item.unitPrice"
              ]
            }
          }
        }
      }
    }
  }
]);
```

Kết quả:

```javascript
{
  _id: "O01",
  lines: [
    { sku: "A", quantity: 2, lineTotal: 200 },
    { sku: "B", quantity: 1, lineTotal: 200 }
  ]
}
```

Khi dùng `as: "item"`, đường dẫn `"$$item.sku"` nghĩa là lấy trường `sku` của **phần tử hiện tại**. Nó khác với `"$item.sku"`, vốn tham chiếu một đường dẫn trường của document trong ngữ cảnh aggregation.

### 3.3. `$map` không tự loại phần tử

Nếu đầu vào có ba phần tử thì `$map` thường tạo ba phần tử đầu ra; nếu biểu thức `in` trả null cho một phần tử thì **null vẫn là một phần tử của mảng kết quả**. Muốn loại những phần tử không đạt điều kiện, dùng `$filter`.

```text
input  = [2, 3, 4]
map x*10
output = [20, 30, 40]

map không có nghĩa "lọc phần tử":
input  = [2, 3, 4]
map x%2 == 0 ? x : null
output = [2, null, 4]
```

### 3.4. Biến mặc định `$$this`

Nếu bỏ trường `as`, phần tử hiện tại có tên mặc định `this`:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O02" } },
  {
    $project: {
      plusOne: {
        $map: {
          input: "$points",
          in: { $add: ["$$this", 1] }
        }
      }
    }
  }
]);
```

`points` của O02 là `[10, 8]` nên `plusOne` bằng `[11, 9]`. Khi lồng nhiều biểu thức, đặt tên biến rõ ràng bằng `as` thường dễ đọc hơn dùng nhiều `$$this` ở các mức.

## 4. `$filter`: giữ các phần tử thỏa điều kiện

Nếu `$map` trả lời câu “**biến mỗi phần tử thành gì?**”, `$filter` trả lời câu “**giữ phần tử nào?**”.

### 4.1. Cú pháp

```javascript
{
  $filter: {
    input: <arrayExpression>,
    as: "element",
    cond: <booleanExpression>,
    limit: <optionalLimitExpression>
  }
}
```

Trong đó:

- `input`: mảng nguồn.
- `as`: tên biến cho phần tử.
- `cond`: biểu thức xác định phần tử có được giữ lại hay không.
- `limit`: tùy chọn giới hạn số phần tử **thỏa điều kiện** được trả về, ở những phiên bản MongoDB hỗ trợ modifier này; giá trị giới hạn hợp lệ phải từ 1 trở lên, hoặc null để không giới hạn.

`$filter` **giữ thứ tự tương đối** của những phần tử được chọn trong mảng gốc. Nó không tự sắp xếp.

### 4.2. Lọc những dòng hàng đang hoạt động

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      _id: 1,
      activeItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $eq: ["$$item.active", true]
          }
        }
      }
    }
  }
]);
```

Kết quả:

```javascript
{
  _id: "O01",
  activeItems: [
    { sku: "A", qty: 2, unitPrice: 100, active: true }
  ]
}
```

Dòng B bị loại vì `active: false`. Ngược lại, `$map` ở phần trước vẫn biến đổi **cả A và B** vì không có bộ lọc.

### 4.3. Nhiều điều kiện với `$and`

Tìm các dòng hàng vừa đang hoạt động vừa có số lượng từ 2:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      eligibleItems: {
        $filter: {
          input: { $ifNull: ["$items", []] },
          as: "item",
          cond: {
            $and: [
              { $eq: ["$$item.active", true] },
              { $gte: ["$$item.qty", 2] }
            ]
          }
        }
      }
    }
  }
]);
```

Với dữ liệu mẫu, O01 giữ dòng A, O02 giữ dòng C, O04 giữ dòng D; O03, O05, O06 trả mảng rỗng. Các điều kiện ở đây là **aggregation expressions** nhận giá trị và biến, không phải các filter document theo cú pháp `{ qty: { $gte: 2 } }`.

### 4.4. Sử dụng `limit` khi chỉ cần vài phần tử đầu tiên phù hợp

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O04" } },
  {
    $project: {
      firstActiveItem: {
        $filter: {
          input: "$items",
          as: "item",
          cond: { $eq: ["$$item.active", true] },
          limit: 1
        }
      }
    }
  }
]);
```

Mảng kết quả chỉ có **dòng A** vì A là phần tử hoạt động đầu tiên của O04. Kết quả vẫn là **mảng**, không tự trở thành một embedded document. Nếu cần giá trị đầu tiên, có thể dùng `$arrayElemAt` ở ngoài:

```javascript
{
  $arrayElemAt: [
    {
      $filter: {
        input: "$items",
        as: "item",
        cond: { $eq: ["$$item.active", true] },
        limit: 1
      }
    },
    0
  ]
}
```

Với các trường hợp không có phần tử phù hợp, cần quyết định rõ cách xử lý kết quả `null`/missing ở tầng tiêu thụ hoặc bọc thêm logic giá trị dự phòng.

### 4.5. `$filter` không phải `$match`

```javascript
// $match lọc cả DOCUMENT.
db.aggArrayLesson.aggregate([
  { $match: { "items.active": true } }
]);

// $filter giữ DOCUMENT, nhưng tạo mảng items đã lọc.
db.aggArrayLesson.aggregate([
  {
    $project: {
      activeItems: {
        $filter: {
          input: { $ifNull: ["$items", []] },
          as: "item",
          cond: { $eq: ["$$item.active", true] }
        }
      }
    }
  }
]);
```

`$match` đầu tiên chỉ giữ các đơn có ít nhất một phần tử active. Nó **không cắt bớt mảng items** trong document được giữ. `$filter` ở ví dụ thứ hai xử lý mảng **trong từng document**; mặc định tất cả document đi qua `$project` vẫn có mặt.

Đây là lý do khi trả dữ liệu cho giao diện, đôi khi cần **cả `$match` để chọn đơn, lẫn `$filter` để chọn những item hiển thị trong đơn**.

## 5. `$reduce`: tích lũy từ trái sang phải

`$reduce` đi qua từng phần tử của mảng và sử dụng một **giá trị tích lũy** để tạo kết quả cuối.

Nó trả lời câu hỏi:

> “Khi đã xử lý các phần tử trước, kết quả trung gian là gì và phải kết hợp nó với phần tử tiếp theo ra sao?”

### 5.1. Cú pháp

```javascript
{
  $reduce: {
    input: <arrayExpression>,
    initialValue: <initialExpression>,
    in: <expressionUsingValueAndThis>
  }
}
```

Hai biến đặc biệt bên trong `in`:

- **`$$value`:** giá trị tích lũy từ các lần xử lý trước; ban đầu bằng `initialValue`.
- **`$$this`:** phần tử mảng đang được xử lý.

Mặc định MongoDB duyệt `input` **từ trái sang phải**. Biểu thức `in` tạo giá trị mới thay cho `$$value` ở bước tiếp theo.

### 5.2. Cộng tổng số trong mảng

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      sumPoints: {
        $reduce: {
          input: "$points",
          initialValue: 0,
          in: { $add: ["$$value", "$$this"] }
        }
      }
    }
  }
]);
```

Mảng O01 là `[5, 7, 9]`. Các bước:

| Lượt | `$$this` | `$$value` trước lượt | Giá trị mới |
|---|---:|---:|---:|
| Ban đầu | — | 0 | 0 |
| 1 | 5 | 0 | 5 |
| 2 | 7 | 5 | 12 |
| 3 | 9 | 12 | 21 |

Kết quả: `{ _id: "O01", sumPoints: 21 }`.

Với phép cộng đơn giản, MongoDB còn có aggregation expression như `$sum` để tính trên mảng trong ngữ cảnh phù hợp. `$reduce` đặc biệt hữu ích khi **mỗi bước cần quy tắc gộp tùy chỉnh** chứ không chỉ cộng số.

### 5.3. Tính tổng tiền của các dòng hàng

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      orderTotal: {
        $reduce: {
          input: { $ifNull: ["$items", []] },
          initialValue: 0,
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.qty",
                  "$$this.unitPrice"
                ]
              }
            ]
          }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Kết quả theo dữ liệu mẫu:

| `_id` | `orderTotal` |
|---|---:|
| O01 | 400 |
| O02 | 150 |
| O03 | 0 |
| O04 | 260 |
| O05 | 0 |
| O06 | 200 |

`$ifNull` đưa `items: null` hoặc trường thiếu về `[]`. Khi `input` là mảng rỗng, `$reduce` trả **`initialValue`**, ở đây là 0.

Việc coi một đơn thiếu danh sách item là tổng 0 là **quyết định nghiệp vụ cho ví dụ**; trong hệ thống thật, dữ liệu thiếu bất thường có thể cần bị đánh dấu lỗi thay vì âm thầm coi như đơn rỗng.

### 5.4. Biến tích lũy có thể là document, không chỉ số

Một lần duyệt có thể tính đồng thời số dòng hàng và tổng tiền:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      statistics: {
        $reduce: {
          input: "$items",
          initialValue: {
            lineCount: 0,
            grossAmount: 0
          },
          in: {
            lineCount: {
              $add: ["$$value.lineCount", 1]
            },
            grossAmount: {
              $add: [
                "$$value.grossAmount",
                {
                  $multiply: [
                    "$$this.qty",
                    "$$this.unitPrice"
                  ]
                }
              ]
            }
          }
        }
      }
    }
  }
]);
```

Kết quả:

```javascript
{
  _id: "O01",
  statistics: {
    lineCount: 2,
    grossAmount: 400
  }
}
```

Ở mỗi vòng, `in` tạo **một document tích lũy mới** từ `$$value` cũ và phần tử `$$this`. Kiểu giá trị của `initialValue` nên phù hợp với cấu trúc mà `in` trả ra.

### 5.5. Thứ tự duyệt quan trọng với một số phép gộp

Với phép cộng thông thường, đổi thứ tự phần tử không làm thay đổi kết quả toán học. Nhưng với phép nối chuỗi, trừ liên tiếp hoặc một thuật toán phụ thuộc thứ tự, kết quả có thể khác.

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      skuList: {
        $reduce: {
          input: {
            $map: {
              input: "$items",
              as: "item",
              in: "$$item.sku"
            }
          },
          initialValue: "",
          in: {
            $cond: [
              { $eq: ["$$value", ""] },
              "$$this",
              { $concat: ["$$value", ",", "$$this"] }
            ]
          }
        }
      }
    }
  }
]);
```

Kết quả `skuList` của O01 là `"A,B"`. Nếu đảo mảng đầu vào, chuỗi sẽ là `"B,A"`.

Muốn xử lý từ phải sang trái, có thể đưa mảng đã `$reverseArray` vào `input` của `$reduce`. Không được giả định `$reduce` tự sắp xếp các phần tử.

### 5.6. Dùng `$reduce` để nối các mảng con

Giả sử document chứa mảng của nhiều nhóm tag:

```javascript
{
  _id: "GROUPS",
  tagGroups: [
    ["mongodb", "database"],
    ["java"],
    ["backend", "mongodb"]
  ]
}
```

Ta có thể tạo một mảng phẳng:

```javascript
db.tagGroupDemo.aggregate([
  {
    $project: {
      allTags: {
        $reduce: {
          input: "$tagGroups",
          initialValue: [],
          in: {
            $concatArrays: [
              "$$value",
              "$$this"
            ]
          }
        }
      }
    }
  }
]);
```

Ở đây giả định document `GROUPS` được lưu trong `tagGroupDemo` trước khi chạy pipeline. `$concatArrays` nối các mảng theo thứ tự, nên kết quả là:

```javascript
["mongodb", "database", "java", "backend", "mongodb"]
```

`$concatArrays` **giữ phần tử trùng**. Nếu muốn biến thành tập các tag duy nhất, dùng thêm `$setUnion`; hai ý định “nối danh sách” và “hợp tập hợp” không giống nhau.

## 6. Kết hợp `$filter`, `$map` và `$reduce`

Ba toán tử thường kết hợp thành một chuỗi:

```text
items ban đầu
      |
      v
$filter: chọn dòng hàng hợp lệ
      |
      v
$map: chuyển mỗi dòng sang số tiền
      |
      v
$reduce: cộng các số tiền
      |
      v
tổng tiền các dòng phù hợp
```

### 6.1. Ví dụ: tổng tiền các dòng hàng đang hoạt động

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      activeAmount: {
        $reduce: {
          input: {
            $map: {
              input: {
                $filter: {
                  input: { $ifNull: ["$items", []] },
                  as: "item",
                  cond: {
                    $eq: ["$$item.active", true]
                  }
                }
              },
              as: "selected",
              in: {
                $multiply: [
                  "$$selected.qty",
                  "$$selected.unitPrice"
                ]
              }
            }
          },
          initialValue: 0,
          in: { $add: ["$$value", "$$this"] }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Với dữ liệu mẫu:

| Đơn | Các dòng đang hoạt động | `activeAmount` |
|---|---|---:|
| O01 | A: 2 × 100 | 200 |
| O02 | C: 3 × 50 | 150 |
| O03 | Không có | 0 |
| O04 | A: 1 × 100, D: 2 × 80 | 260 |
| O05 | Không có mảng hợp lệ (được thay bằng []) | 0 |
| O06 | Không có (B inactive) | 0 |

Pipeline ở trên cố tình dùng **cả ba toán tử** để thể hiện từng bước. Trong bài toán chỉ cộng tiền, có thể tính trực tiếp trong `$reduce` trên mảng đã lọc để giảm một lớp `$map`; lựa chọn phụ thuộc mức dễ đọc và nhu cầu tái sử dụng dữ liệu trung gian.

### 6.2. Dùng `$let` để đặt tên biểu thức trung gian

Khi nhiều nhánh của biểu thức cần dùng lại một mảng đã lọc, `$let` giúp đặt tên biến trong phạm vi hiện tại:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O04" } },
  {
    $project: {
      summary: {
        $let: {
          vars: {
            selected: {
              $filter: {
                input: "$items",
                as: "item",
                cond: { $eq: ["$$item.active", true] }
              }
            }
          },
          in: {
            selectedCount: { $size: "$$selected" },
            selectedTotal: {
              $reduce: {
                input: "$$selected",
                initialValue: 0,
                in: {
                  $add: [
                    "$$value",
                    {
                      $multiply: [
                        "$$this.qty",
                        "$$this.unitPrice"
                      ]
                    }
                  ]
                }
              }
            }
          }
        }
      }
    }
  }
]);
```

Kết quả với O04 là `selectedCount: 2` và `selectedTotal: 260`.

`$let` tạo **biến expression** như `$$selected`, không thay đổi schema của document được lưu. Nó hữu ích khi một phép tính lớn có nhiều mức lồng nhau.

## 7. Null, missing, mảng rỗng và sai kiểu

Ba toán tử `$map`, `$filter` và `$reduce` có những quy tắc đầu vào quan trọng.

| Giá trị của `input` | `$map` | `$filter` | `$reduce` |
|---|---|---|---|
| Mảng có phần tử | Mảng các giá trị mới | Mảng phần tử thỏa điều kiện | Giá trị tích lũy |
| Mảng rỗng `[]` | `[]` | `[]` | `initialValue` |
| Null | `null` | `null` | `null` |
| Trường không tồn tại | `null` | `null` | `null` |
| Giá trị không phải mảng và không phải null | Lỗi kiểu đầu vào | Lỗi kiểu đầu vào | Lỗi kiểu đầu vào |

Ví dụ nếu dùng trực tiếp:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      itemsAsSku: {
        $map: {
          input: "$items",
          as: "item",
          in: "$$item.sku"
        }
      }
    }
  }
]);
```

Document O05 có `items: null` nên `itemsAsSku` của O05 là `null`, **không phải mảng rỗng**.

### 7.1. Chuẩn hóa null/missing thành mảng rỗng bằng `$ifNull`

```javascript
{
  $map: {
    input: { $ifNull: ["$items", []] },
    as: "item",
    in: "$$item.sku"
  }
}
```

Với O05, `$ifNull` thay null bằng `[]`, nên `$map` trả `[]`.

Đây là cách phù hợp khi nghiệp vụ quy định “không có mảng” được xử lý như danh sách rỗng. Nhưng nếu missing/null là **lỗi dữ liệu** cần được báo cáo, không nên tự động che giấu chúng bằng giá trị dự phòng.

### 7.2. `$ifNull` không sửa dữ liệu sai kiểu

Nếu:

```javascript
{
  _id: "BROKEN",
  items: "A,B,C"
}
```

thì `{ $ifNull: ["$items", []] }` vẫn trả về String `"A,B,C"`, và `$map`/`$filter`/`$reduce` nhận String sẽ lỗi.

Khi collection có schema lẫn lộn, có thể kiểm tra kiểu trước:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      safeSkus: {
        $map: {
          input: {
            $cond: [
              { $isArray: "$items" },
              "$items",
              []
            ]
          },
          as: "item",
          in: "$$item.sku"
        }
      }
    }
  }
]);
```

`$isArray` trả Boolean xác định một giá trị có là mảng hay không. Ví dụ này cố tình quy mọi giá trị không phải mảng thành `[]`; trong production, có thể thay bằng kiểm tra validation và quy trình xử lý lỗi để tránh im lặng mất dữ liệu.

### 7.3. Phân biệt mảng rỗng với trường thiếu

Để kiểm kê dữ liệu không đồng nhất, dùng `$type`:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      itemsType: { $type: "$items" },
      itemsIsArray: { $isArray: "$items" }
    }
  }
]);
```

Với O03, `itemsType` là `"array"`; với O05 là `"null"`. Khi trường không tồn tại, aggregation expression `$type` có thể trả `"missing"`.

Điều này hữu ích trước khi quyết định một phép tính nên trả 0, null hay báo dữ liệu không hợp lệ.

## 8. Danh sách khác tập hợp: vì sao cần các set operators?

Một **mảng** trong MongoDB giữ thứ tự và có thể chứa những phần tử giống hệt nhau:

```javascript
["vip", "sale", "vip"]
```

Một **tập hợp (set)** theo ý nghĩa toán học chỉ quan tâm một giá trị **có thuộc tập hay không**, không quan tâm vị trí và không đếm số lần xuất hiện.

Khi dùng các toán tử tập hợp, MongoDB coi mảng đầu vào như những tập giá trị:

```text
Mảng:   ["vip", "sale", "vip"]
Tập:    {"vip", "sale"}

Mảng:   ["sale", "vip"]
Tập:    {"vip", "sale"}

Hai mảng trên khác thứ tự/số lần lặp,
nhưng thể hiện cùng một tập giá trị.
```

Các toán tử tập hợp thường trả **mảng** biểu diễn tập kết quả, nhưng **không bảo đảm thứ tự phần tử trong mảng kết quả**. Nếu API cần sắp xếp, phải dùng bước sắp xếp phù hợp sau đó; không dựa vào thứ tự ví dụ để kiểm thử theo vị trí.

### 8.1. Set operator khác `$concatArrays`

```javascript
// Nối danh sách, giữ thứ tự và phần tử trùng:
{ $concatArrays: [["vip", "sale"], ["sale", "new"]] }

// Hợp tập hợp, loại giá trị trùng, thứ tự không xác định:
{ $setUnion: [["vip", "sale"], ["sale", "new"]] }
```

Kết quả về ý nghĩa:

```javascript
// $concatArrays
["vip", "sale", "sale", "new"]

// $setUnion: tập các giá trị, thứ tự có thể khác nhau
["vip", "sale", "new"]
```

**Không được dùng `$setUnion` để thay `$concatArrays`** nếu số lần lặp và thứ tự của phần tử có ý nghĩa nghiệp vụ, chẳng hạn lịch sử sự kiện hoặc các bước xử lý.

## 9. `$setUnion`: hợp nhiều tập hợp

`$setUnion` tạo tập chứa **mọi phần tử phân biệt** xuất hiện trong ít nhất một mảng đầu vào.

### 9.1. Cú pháp cơ bản

```javascript
{
  $setUnion: [
    <arrayExpression1>,
    <arrayExpression2>,
    ...
  ]
}
```

Ví dụ với O01:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      unifiedTags: {
        $setUnion: [
          "$tags",
          ["sale", "new"]
        ]
      }
    }
  }
]);
```

Vì `tags` của O01 là `["vip", "sale", "vip"]`, tập kết quả chứa **vip, sale và new**, mỗi giá trị chỉ một lần:

```javascript
{
  _id: "O01",
  unifiedTags: ["vip", "sale", "new"]
  // Thứ tự phần tử chỉ minh họa.
}
```

### 9.2. Loại trùng ngay trên một mảng

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      uniqueTags: {
        $setUnion: [
          { $ifNull: ["$tags", []] },
          []
        ]
      }
    }
  }
]);
```

Hợp một mảng với tập rỗng là cách viết ngắn để **lấy các giá trị duy nhất của mảng** theo ngữ nghĩa tập hợp. Với O01, `uniqueTags` có hai giá trị `vip` và `sale`, không giữ bản trùng vip.

Việc chuẩn hóa `tags` bằng `$ifNull` ở đây tránh coi null/missing như một mảng hợp lệ. Đừng nhầm với việc thay đổi dữ liệu lưu: `$project` chỉ tạo kết quả đọc.

### 9.3. Dùng với nhiều mảng

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O02" } },
  {
    $project: {
      allLabels: {
        $setUnion: [
          "$tags",
          "$coupons",
          ["new"]
        ]
      }
    }
  }
]);
```

O02 có tags `sale, new` và coupons `SALE, FREESHIP`. Theo so sánh String mặc định, `"sale"` và `"SALE"` là **hai giá trị khác nhau**; không mặc định gộp chữ hoa và chữ thường. Nếu nghiệp vụ xem chúng như nhau, cần chuẩn hóa dữ liệu hoặc dùng phép xử lý phù hợp trước khi đưa vào toán tử set.

## 10. `$setIntersection`: giao của các tập hợp

`$setIntersection` chỉ giữ những phần tử xuất hiện trong **tất cả mảng đầu vào**.

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      commonTags: {
        $setIntersection: [
          "$tags",
          ["sale", "new", "popular"]
        ]
      }
    }
  }
]);
```

Kết quả có một giá trị `"sale"` vì:

```text
tags của O01 = {vip, sale}
tags mục tiêu = {sale, new, popular}
giao         = {sale}
```

Một ví dụ truy vấn các đơn **có ít nhất một tag thuộc tập mục tiêu**:

```javascript
db.aggArrayLesson.aggregate([
  {
    $match: {
      $expr: {
        $gt: [
          {
            $size: {
              $setIntersection: [
                { $ifNull: ["$tags", []] },
                ["vip", "new"]
              ]
            }
          },
          0
        ]
      }
    }
  },
  { $project: { _id: 1, tags: 1 } }
]);
```

Các đơn có ít nhất một giá trị `vip` hoặc `new` là **O01, O02 và O04**. Đây là ví dụ sử dụng set expression trong `$expr` để lọc document.

Với nhu cầu chỉ kiểm tra một trường mảng có một giá trị thuộc danh sách, bộ lọc thông thường `{ tags: { $in: ["vip", "new"] } }` thường ngắn gọn hơn và có thể tận dụng multikey index phù hợp. Không cần dùng aggregation expression phức tạp cho mọi điều kiện trên array.

## 11. `$setDifference`: phần tử thuộc A nhưng không thuộc B

`$setDifference` thực hiện **hiệu tập hợp có hướng**: phần tử ở mảng thứ nhất nhưng **không có** trong mảng thứ hai.

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      tagsNotInCampaign: {
        $setDifference: [
          "$tags",
          ["sale", "new"]
        ]
      }
    }
  }
]);
```

Kết quả biểu diễn tập `{"vip"}`.

Nếu đảo hai mảng:

```javascript
{
  $setDifference: [
    ["sale", "new"],
    "$tags"
  ]
}
```

thì kết quả là tập `{"new"}`.

**Hiệu tập hợp không có tính giao hoán:** `A − B` khác `B − A`. Phân biệt rõ mục tiêu nghiệp vụ là “nhãn của đơn **chưa thuộc chiến dịch**” hay “nhãn chiến dịch **đơn chưa có**”.

### 11.1. Ví dụ gợi ý các nhãn cần bổ sung

Ứng dụng muốn thêm những tag mặc định `["sale", "new"]` còn thiếu ở O01:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      missingRecommendedTags: {
        $setDifference: [
          ["sale", "new"],
          { $ifNull: ["$tags", []] }
        ]
      }
    }
  }
]);
```

Kết quả chỉ gồm `"new"`. Đây là phép tính trên dữ liệu đọc; nếu muốn **ghi thêm** tag, ứng dụng cần một thao tác cập nhật riêng với ràng buộc nghiệp vụ phù hợp.

## 12. `$setEquals` và `$setIsSubset`: so sánh tập hợp

Hai toán tử này không trả mảng kết quả mà trả **Boolean**.

### 12.1. `$setEquals`: hai tập có cùng phần tử hay không?

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      tagsEquivalent: {
        $setEquals: [
          "$tags",
          ["sale", "vip"]
        ]
      }
    }
  }
]);
```

O01 có `["vip", "sale", "vip"]`; mảng so sánh là `["sale", "vip"]`. Kết quả `tagsEquivalent: true` vì hai mảng có cùng **tập giá trị**, dù khác số phần tử và thứ tự.

Đây là khác biệt quan trọng so với việc so sánh hai mảng như hai **danh sách có thứ tự**.

### 12.2. `$setIsSubset`: mọi phần tử của A có thuộc B không?

```javascript
db.aggArrayLesson.aggregate([
  { $match: { _id: "O01" } },
  {
    $project: {
      hasRequiredTags: {
        $setIsSubset: [
          ["vip"],
          "$tags"
        ]
      },
      allTagsAllowed: {
        $setIsSubset: [
          "$tags",
          ["vip", "sale", "new"]
        ]
      }
    }
  }
]);
```

Kết quả của hai điều kiện là `true`:

- `{"vip"} ⊆ {"vip", "sale"}`.
- `{"vip", "sale"} ⊆ {"vip", "sale", "new"}`.

**Thứ tự toán hạng rất quan trọng.** Muốn kiểm tra “đơn có **đầy đủ các tag bắt buộc**”, đặt mảng tag bắt buộc ở **vế trái**, tập tag hiện có ở **vế phải**.

### 12.3. Tập rỗng và tính bao hàm

Một số quy tắc toán học hữu ích:

- Tập rỗng là tập con của **mọi tập**.
- Hai tập rỗng bằng nhau.
- Giao với tập rỗng là tập rỗng.
- Hợp với tập rỗng giữ nguyên tập giá trị của toán hạng còn lại.

Vì vậy, `$setIsSubset: [[], "$tags"]` có thể trả true ngay cả khi `tags` không chứa nhãn nào (với điều kiện `tags` là mảng hợp lệ). Nếu nghiệp vụ yêu cầu **ít nhất một tag bắt buộc**, hãy kiểm tra mảng yêu cầu không rỗng trước khi suy ra ý nghĩa “đã đáp ứng yêu cầu”.

## 13. `$anyElementTrue` và `$allElementsTrue`

Đây là nhóm toán tử tập hợp để kiểm tra **chân trị** của các phần tử đầu vào. Chúng không tự hiểu nghiệp vụ của object hoặc các trường nested; vì thế thường dùng sau khi `$map` biến mảng thành các kết quả Boolean.

### 13.1. Có ít nhất một dòng hàng có số lượng lớn hơn 2?

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      hasLargeLine: {
        $anyElementTrue: [
          {
            $map: {
              input: { $ifNull: ["$items", []] },
              as: "item",
              in: { $gt: ["$$item.qty", 2] }
            }
          }
        ]
      }
    }
  }
]);
```

O02 có dòng C với `qty: 3`, nên `hasLargeLine` là true. Các đơn còn lại không có dòng hàng có `qty > 2` trong bộ mẫu.

`$anyElementTrue` nhận **một biểu thức mảng** (được bọc trong mảng đối số) và trả true nếu có phần tử được xét là đúng.

### 13.2. Tất cả dòng hàng có đang hoạt động?

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      allLinesActive: {
        $allElementsTrue: [
          {
            $map: {
              input: { $ifNull: ["$items", []] },
              as: "item",
              in: { $eq: ["$$item.active", true] }
            }
          }
        ]
      }
    }
  }
]);
```

O02 và O04 trả true vì mọi dòng hàng hiện có đều active. O01 và O06 trả false vì chứa dòng inactive.

**Bẫy quan trọng:** `$allElementsTrue` với mảng rỗng trả **true** (tính chất “mọi phần tử đều thỏa” trên tập rỗng). Vì vậy, O03 hoặc O05 có thể trả true sau khi chuẩn hóa sang `[]`, mặc dù **không có một dòng hàng active nào**.

Nếu nghiệp vụ muốn “**có ít nhất một dòng** và mọi dòng đều active”, phải kiểm tra thêm độ dài:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      hasItemsAndAllActive: {
        $let: {
          vars: {
            safeItems: { $ifNull: ["$items", []] }
          },
          in: {
            $and: [
              { $gt: [{ $size: "$$safeItems" }, 0] },
              {
                $allElementsTrue: [
                  {
                    $map: {
                      input: "$$safeItems",
                      as: "item",
                      in: {
                        $eq: ["$$item.active", true]
                      }
                    }
                  }
                ]
              }
            ]
          }
        }
      }
    }
  }
]);
```

Trong ví dụ, O02 và O04 là những đơn đáp ứng điều kiện mới.

### 13.3. Nested arrays được xem như phần tử, không tự duyệt đệ quy

Các toán tử tập hợp không mặc định “trải phẳng” mọi mảng lồng nhau. Một phần tử là mảng vẫn được xem như **một phần tử ở cấp hiện tại** khi xét những toán tử này. Vì thế, nếu ý định là kiểm tra Boolean trong nhiều tầng nested arrays, phải làm phẳng hoặc biến đổi dữ liệu có chủ đích trước.

Đừng dùng `$anyElementTrue` để thay một phép duyệt sâu mà không xác định rõ cấu trúc đầu vào.

## 14. Toán tử tập hợp coi mảng lồng nhau là phần tử nguyên vẹn

Với:

```javascript
const first = ["mongodb", ["java", "spring"]];
const second = [["java", "spring"], "backend"];
```

Theo cách các toán tử set xử lý mảng ở cấp hiện tại, mảng con `["java", "spring"]` được xem như **một phần tử của tập**, không tự biến thành hai phần tử `java` và `spring`.

Do đó, hợp tập chứa những giá trị có ý nghĩa:

```text
{
  "mongodb",
  ["java", "spring"],
  "backend"
}
```

Đây là lý do khi một document chứa **mảng của các mảng**, cần quyết định:

1. Muốn xem từng mảng con là **một đối tượng**?
2. Hay muốn thống kê và hợp nhất **các phần tử nằm bên trong**?

Ở trường hợp thứ hai, có thể dùng `$reduce + $concatArrays` để làm phẳng một cấp trước khi dùng `$setUnion`. Lưu ý làm phẳng một cấp **không phải** đệ quy vô hạn; nếu mảng có nhiều tầng lồng nhau, cần xác định độ sâu và cách xử lý phù hợp.

## 15. Dùng toán tử tập hợp trong một pipeline tổng hợp

Ví dụ ứng dụng muốn hiển thị danh sách tag duy nhất, những tag thuộc chương trình marketing và số lượng tag riêng biệt của từng đơn.

```javascript
db.aggArrayLesson.aggregate([
  {
    $set: {
      safeTags: {
        $ifNull: ["$tags", []]
      }
    }
  },
  {
    $project: {
      _id: 1,
      uniqueTags: {
        $setUnion: ["$safeTags", []]
      },
      campaignTags: {
        $setIntersection: [
          "$safeTags",
          ["vip", "sale"]
        ]
      },
      missingRecommendedTags: {
        $setDifference: [
          ["vip", "new"],
          "$safeTags"
        ]
      },
      distinctTagCount: {
        $size: {
          $setUnion: ["$safeTags", []]
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Ví dụ với O01:

```javascript
{
  _id: "O01",
  uniqueTags: ["vip", "sale"],
  campaignTags: ["vip", "sale"],
  missingRecommendedTags: ["new"],
  distinctTagCount: 2
}
```

**Thứ tự các phần tử trong mảng kết quả của set operators chỉ minh họa**, nhưng số lượng phần tử phân biệt là ổn định theo dữ liệu và quy tắc so sánh.

### 15.1. So sánh tổng phần tử với tổng giá trị phân biệt

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      tagCount: {
        $size: { $ifNull: ["$tags", []] }
      },
      distinctTagCount: {
        $size: {
          $setUnion: [
            { $ifNull: ["$tags", []] },
            []
          ]
        }
      }
    }
  }
]);
```

O01 có `tagCount = 3` nhưng `distinctTagCount = 2` vì `vip` bị lặp. Đây là hai đại lượng khác nhau:

- **`$size`:** số phần tử mảng, tính cả trùng.
- **`$size` của kết quả `$setUnion`:** số giá trị phân biệt trong mảng.

Không nên thay thế hai cách tính cho nhau nếu số lần xuất hiện là dữ liệu nghiệp vụ.

## 16. Cập nhật mảng: expression khác toán tử cập nhật

Các ví dụ trên chủ yếu dùng `aggregate()` để **đọc** và tính giá trị. MongoDB cũng hỗ trợ **update với aggregation pipeline**, nơi có thể sử dụng các expression để tạo trạng thái mảng mới.

### 16.1. `$addToSet` là update operator, khác `$setUnion`

```javascript
// Update truyền thống: thêm "new" nếu giá trị chưa tồn tại.
db.aggArrayLesson.updateOne(
  { _id: "O01" },
  {
    $addToSet: {
      tags: "new"
    }
  }
);
```

`$addToSet` giúp thêm một giá trị chưa có trong mảng, nhưng **không tự xóa những phần tử trùng đã tồn tại trước đó**. O01 vẫn có thể giữ hai bản `vip` cũ.

Ngược lại, dùng `$setUnion` trong **update pipeline**:

```javascript
db.aggArrayLesson.updateOne(
  { _id: "O01" },
  [
    {
      $set: {
        tags: {
          $setUnion: [
            { $ifNull: ["$tags", []] },
            ["new"]
          ]
        }
      }
    }
  ]
);
```

Ở đây `$setUnion` tạo **mảng mới đã loại trùng theo ngữ nghĩa set**, và `$set` là **aggregation stage** gán mảng đó trở lại trường `tags`. Thứ tự phần tử mới không được bảo đảm.

**Hai cách có ngữ nghĩa khác nhau**:

| Yêu cầu | Công cụ có thể phù hợp |
|---|---|
| Thêm một nhãn nếu chưa có, giữ thứ tự/cấu trúc mảng hiện tại ở mức có thể | Update `$addToSet` |
| Tạo một tập mới từ nhiều mảng, loại những giá trị trùng đã có | Aggregation expression `$setUnion` |
| Nối lịch sử và giữ những sự kiện lặp | `$concatArrays` hoặc update `$push` |
| Giữ tối đa N sự kiện mới nhất theo tiêu chí | Thiết kế preview với `$push` và các modifier thích hợp, hoặc pipeline tính lại |

### 16.2. `$filter` trong update pipeline làm thay đổi dữ liệu lưu

Ví dụ loại những dòng hàng không còn active:

```javascript
db.aggArrayLesson.updateOne(
  { _id: "O01" },
  [
    {
      $set: {
        items: {
          $filter: {
            input: { $ifNull: ["$items", []] },
            as: "item",
            cond: { $eq: ["$$item.active", true] }
          }
        }
      }
    }
  ]
);
```

Khác với `$project` ở truy vấn đọc, lệnh này **ghi đè mảng items đã lưu** bằng kết quả lọc. Dòng B của O01 sẽ bị xóa khỏi mảng lưu, không chỉ bị ẩn khỏi response. Chỉ làm vậy nếu đó thực sự là yêu cầu cập nhật nghiệp vụ.

Với các bài thực hành muốn giữ dataset ban đầu, **chạy ví dụ đọc trước ví dụ cập nhật**, hoặc dùng collection khác để thực nghiệm update pipeline.

## 17. So sánh `$map`, `$filter`, `$reduce`, `$unwind` và `$group`

Các tên này đều xuất hiện trong aggregation nhưng không cùng phạm vi:

| Công cụ | Loại | Đầu vào chính | Kết quả |
|---|---|---|---|
| `$map` | Expression | Một mảng | Một mảng đã biến đổi |
| `$filter` | Expression | Một mảng + điều kiện | Một mảng con |
| `$reduce` | Expression | Một mảng + tích lũy | Một giá trị |
| `$setUnion` | Expression | Hai hoặc nhiều mảng | Mảng phần tử phân biệt |
| `$unwind` | Pipeline stage | Luồng document có trường mảng | Có thể nhiều document cho từng phần tử |
| `$group` | Pipeline stage | Luồng nhiều document | Một document cho mỗi khóa nhóm |

### 17.1. Tính tổng bên trong một đơn bằng `$reduce`

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      total: {
        $reduce: {
          input: { $ifNull: ["$items", []] },
          initialValue: 0,
          in: {
            $add: [
              "$$value",
              { $multiply: ["$$this.qty", "$$this.unitPrice"] }
            ]
          }
        }
      }
    }
  }
]);
```

Mỗi document đơn hàng tạo một giá trị tổng từ **mảng items bên trong chính document đó**.

### 17.2. Tính tổng theo SKU trên toàn collection bằng `$unwind + $group`

```javascript
db.aggArrayLesson.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      lineCount: { $sum: 1 },
      units: { $sum: "$items.qty" },
      revenue: {
        $sum: {
          $multiply: [
            "$items.qty",
            "$items.unitPrice"
          ]
        }
      }
    }
  },
  { $sort: { units: -1, _id: 1 } }
]);
```

Kết quả trên dữ liệu mẫu (không lọc `active`):

| SKU | `lineCount` | `units` | `revenue` |
|---|---:|---:|---:|
| A | 2 | 3 | 300 |
| C | 1 | 3 | 150 |
| B | 2 | 2 | 400 |
| D | 1 | 2 | 160 |

`$unwind` làm phẳng mỗi dòng hàng thành một document trong luồng, sau đó `$group` gộp **giữa nhiều đơn**. `$reduce` thì thường được dùng để tính **trong một mảng của từng document**.

### 17.3. Vì sao không phải lúc nào cũng dùng `$unwind`?

Giả sử chỉ muốn trả danh sách các dòng hàng active **trong từng đơn**, giữ nguyên mỗi đơn là một document. Dùng `$filter` sẽ trực tiếp và thường dễ đọc hơn việc `$unwind` các dòng rồi `$match` và `$group` để ghép lại thành mảng.

Ngược lại, khi cần báo cáo doanh thu **theo SKU trên toàn collection**, `$unwind + $group` tự nhiên hơn nhiều `$reduce` riêng lẻ rồi cố kết hợp kết quả giữa các đơn.

Chọn công cụ theo **phạm vi biến đổi dữ liệu**: trong mảng của một document hay trên luồng nhiều document.

## 18. Toán tử tập hợp và truy vấn theo mảng: tránh làm quá phức tạp

Nếu chỉ muốn tìm đơn có tag `vip`, query filter thường đủ:

```javascript
db.aggArrayLesson.find({ tags: "vip" });
```

Nếu muốn tìm đơn có ít nhất một tag trong danh sách:

```javascript
db.aggArrayLesson.find({
  tags: { $in: ["vip", "new"] }
});
```

Nếu muốn tất cả tag bắt buộc cùng xuất hiện:

```javascript
db.aggArrayLesson.find({
  tags: { $all: ["vip", "sale"] }
});
```

Đây là **query operators** trong filter, không phải aggregation set expressions. Khi nhu cầu là lọc trực tiếp trên phần tử mảng, query operator có thể ngắn gọn và có cơ hội dùng **multikey index**.

Ngược lại, dùng set expressions khi cần:

- **Tính tập hợp mới** để trả trong response.
- **So sánh hai mảng động** thuộc cùng một document hoặc các nguồn biểu thức.
- **Tính số lượng phần tử phân biệt**.
- **Tạo mảng dẫn xuất** trong aggregation hoặc update pipeline.
- **Kiểm tra quan hệ tập con** giữa mảng bắt buộc và mảng hiện hành bằng phép tính.

Ví dụ hai mảng cùng nằm trong document:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      tagCouponOverlap: {
        $setIntersection: [
          { $ifNull: ["$tags", []] },
          { $ifNull: ["$coupons", []] }
        ]
      }
    }
  }
]);
```

Ở đây đang **tính giao của hai giá trị mảng có sẵn**, không chỉ kiểm tra một trường với danh sách hằng.

## 19. Những vấn đề về kiểu dữ liệu, thứ tự và so sánh

### 19.1. Set operators không tự sắp xếp đầu ra

Không viết kiểm thử phụ thuộc vào việc:

```javascript
{ $setUnion: [["b", "a"], ["c", "a"]] }
```

**bắt buộc** trả `["a", "b", "c"]` theo thứ tự chữ cái. Các toán tử tập hợp không bảo đảm thứ tự mảng đầu ra. Nếu giao diện hoặc API yêu cầu một thứ tự cụ thể, dùng phép sắp xếp mảng phù hợp với phiên bản và điều kiện triển khai, hoặc sắp xếp tại ứng dụng.

### 19.2. Kiểu BSON ảnh hưởng ý nghĩa bằng nhau

Trong dữ liệu thực tế, cùng ký tự hiển thị có thể mang kiểu khác nhau, chẳng hạn:

```javascript
"42"    // String
42      // Number
```

Không nên coi hai giá trị đó như một nhãn giống nhau rồi mong set operators tự chuẩn hóa. Tương tự, các giá trị viết hoa/thường có thể khác nhau theo quy tắc so sánh đang áp dụng. Nếu cần chuẩn hóa, làm rõ quy tắc ở **schema** hoặc biểu thức trước khi thực hiện phép tập hợp.

### 19.3. Null trong mảng khác với cả mảng null

```javascript
["a", null]    // Mảng hợp lệ, chứa một phần tử null.
null           // Giá trị null, không phải mảng.
```

Set operators có thể xem **phần tử null bên trong một mảng** như một giá trị thuộc tập. Ngược lại, nếu toàn bộ toán hạng là null hoặc thiếu, việc thực hiện một phép toán trên mảng cần được xử lý theo quy tắc toán tử và không nên giả định tương đương `[]`.

Một mẫu an toàn khi nghiệp vụ chấp nhận null/missing tương đương mảng rỗng:

```javascript
{
  $setIntersection: [
    { $ifNull: ["$tags", []] },
    ["vip", "sale"]
  ]
}
```

### 19.4. Embedded documents là giá trị phức hợp

Với:

```javascript
[
  { sku: "A", qty: 1 },
  { sku: "A", qty: 2 }
]
```

hai embedded documents có cùng `sku` nhưng **khác `qty`** không phải một giá trị hoàn toàn giống nhau. Set operators **không mặc định lấy riêng `sku` làm khóa duy nhất**.

Nếu muốn tập mã SKU riêng biệt, dùng `$map` để tạo **mảng scalar** trước, rồi mới `$setUnion`:

```javascript
db.aggArrayLesson.aggregate([
  {
    $project: {
      _id: 1,
      uniqueSkus: {
        $setUnion: [
          {
            $map: {
              input: { $ifNull: ["$items", []] },
              as: "item",
              in: "$$item.sku"
            }
          },
          []
        ]
      }
    }
  }
]);
```

Như vậy nghiệp vụ “duy nhất theo SKU” được diễn đạt rõ. Nếu chỉ hợp trực tiếp mảng `items`, quan hệ so sánh là trên **giá trị embedded document**, không phải trên một trường con được chọn ngầm.

## 20. Hiệu năng: xử lý mảng lớn có thể đắt

Các toán tử trong bài thường được tính **cho từng document** đi qua pipeline. Một document chứa mảng 10 phần tử khác với một document chứa mảng 100.000 phần tử.

### 20.1. Chi phí theo số phần tử

Ở mức trực giác:

- `$map`: cần xử lý các phần tử đầu vào để tạo mảng mới.
- `$filter`: cần đánh giá điều kiện cho các phần tử có liên quan.
- `$reduce`: cần duyệt các phần tử và cập nhật giá trị tích lũy.
- Các phép tập hợp: cần xem xét các giá trị để xác định phần tử trùng, giao, hiệu hoặc quan hệ bằng nhau.

Thời gian và bộ nhớ thực tế phụ thuộc độ dài mảng, kích thước phần tử, độ phức tạp của biểu thức lồng nhau, kế hoạch truy vấn và điều kiện thực thi. Không giả định việc gọi một expression luôn có chi phí hằng số.

### 20.2. Lọc document trước khi tính toán mảng

Nếu chỉ cần đơn `PAID`:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { status: "PAID" } },
  {
    $project: {
      _id: 1,
      activeItems: {
        $filter: {
          input: { $ifNull: ["$items", []] },
          as: "item",
          cond: { $eq: ["$$item.active", true] }
        }
      }
    }
  }
]);
```

`$match` thu hẹp số document cần tính expression. Khi có index trên `status` và dữ liệu đủ lớn, bước này có thể giúp giảm chi phí. Tuy nhiên, **index của query không tự làm `$map`/$filter` chạy trên từng phần tử mảng nhanh hơn**; nó chủ yếu hỗ trợ tìm các document cần xử lý.

### 20.3. Chỉ trả những trường cần thiết

Ví dụ nếu API chỉ cần `sku` và tổng giá của dòng, `$map` tạo ra object mới nhỏ hơn cả embedded document có thể giảm lượng dữ liệu gửi về:

```javascript
db.aggArrayLesson.aggregate([
  { $match: { status: "PAID" } },
  {
    $project: {
      _id: 1,
      lines: {
        $map: {
          input: { $ifNull: ["$items", []] },
          as: "item",
          in: {
            sku: "$$item.sku",
            total: {
              $multiply: [
                "$$item.qty",
                "$$item.unitPrice"
              ]
            }
          }
        }
      }
    }
  }
]);
```

`$project` làm rõ hợp đồng đầu ra, nhưng không nên mặc định mọi projection khiến database không phải đọc document gốc. Khả năng dùng index/covered query cần được quan sát từ kế hoạch thực thi.

### 20.4. Tránh mảng tăng không giới hạn

MongoDB có giới hạn **16 MiB cho một BSON document**. Nếu một đơn hàng hoặc người dùng chứa mảng lịch sử tăng mãi, cả việc lưu và tính toán các expression trên nó có thể trở nên không phù hợp.

Đối với dữ liệu có vòng đời độc lập hoặc số lượng cực lớn, cân nhắc tách sang collection riêng và dùng `$unwind`/`$group` hoặc truy vấn quan hệ thích hợp, thay vì buộc tất cả dữ liệu phải ở trong mảng của một document.

### 20.5. Khi nào cần lưu kết quả đã tính?

Nếu giao diện luôn hỏi tổng tiền đơn hoặc số tag riêng biệt, ứng dụng có thể cân nhắc lưu trường dẫn xuất như `totalAmount` hoặc `distinctTagCount` và duy trì nó cùng dữ liệu nguồn khi cập nhật.

Đổi lại, một trường dẫn xuất cần cơ chế nhất quán: thêm, xóa, sửa `items` hoặc `tags` phải cập nhật lại giá trị đúng. Chỉ làm vậy khi chi phí truy vấn thực tế và tần suất đọc/ghi biện minh cho rủi ro đồng bộ.

## 21. Những lỗi và hiểu nhầm thường gặp

| Cách nghĩ hoặc cách viết | Vấn đề | Hướng xử lý |
|---|---|---|
| `$map` tự loại phần tử không phù hợp | Nó biến đổi từng phần tử, thường giữ số lượng phần tử | Dùng `$filter` trước hoặc sau khi map |
| `$filter` lọc bỏ document gốc | Nó trả mảng con, không tự bỏ document trong pipeline | Dùng `$match` để chọn document |
| `$reduce` luôn trả mảng | Nó trả **giá trị tích lũy**, có thể số, chuỗi, object hay mảng | Chọn `initialValue` và `in` phù hợp |
| `$$value` là phần tử hiện tại | `$$value` là tích lũy; `$$this` là phần tử | Phân biệt vai trò biến |
| `"$item.sku"` và `"$$item.sku"` giống nhau | Một bên là đường dẫn document, bên kia là biến `as` | Dùng hai dấu `$` cho biến |
| Mảng rỗng và null luôn giống nhau | `$reduce` với [] trả initialValue; input null trả null | Quy định rõ chính sách chuẩn hóa |
| `$ifNull` sửa được mọi kiểu sai | String hay Number không phải null vẫn đi qua và gây lỗi | Kiểm tra `$isArray` hoặc validation |
| `$setUnion` nối danh sách và giữ trùng | Nó hợp tập, bỏ giá trị trùng, không hứa thứ tự | Dùng `$concatArrays` nếu cần danh sách |
| `$setDifference` có thể đảo thứ tự toán hạng | Hiệu tập hợp có hướng | Đặt đúng A − B |
| `$setEquals` so mảng theo vị trí | Nó so theo tập giá trị, không quan tâm thứ tự/trùng | Dùng cách so sánh mảng khi cần thứ tự |
| `$setIsSubset` luôn trả false nếu mảng yêu cầu rỗng | Tập rỗng là tập con của mọi tập | Kiểm tra điều kiện “phải có phần tử” riêng |
| `$allElementsTrue` trên [] trả false | Nó trả true với mảng rỗng | Kiểm tra `$size > 0` nếu cần |
| `$map` trên mảng object tự loại trùng theo `sku` | Object đầy đủ được so sánh theo giá trị | Map sang mảng `sku` rồi set-union |
| `$setUnion` luôn có kết quả theo bảng chữ cái | Không bảo đảm thứ tự phần tử kết quả | Sắp xếp tường minh |
| Toán tử tập hợp là một pipeline stage | Đây là expression dùng trong stage như `$project`/`$set` | Đặt đúng ngữ cảnh |
| `$reduce` trên một document thay thế `$group` trên toàn collection | Phạm vi khác nhau: mảng nội bộ vs nhiều document | Dùng `$unwind + $group` khi tổng hợp liên document |
| Mọi phép toán trên mảng đều dùng index | Biểu thức thường được tính sau khi tìm document | Dùng `$match` và kiểm tra `explain()` |

## 22. Bài tập thực hành

### Bài 1 — Biến đổi mảng số bằng `$map`

Cho document:

```javascript
{ _id: "X01", values: [2, 5, 8] }
```

Hãy viết `$project` với `$map` để tạo mảng:

```javascript
[4, 10, 16]
```

Sau đó tạo mảng Boolean cho biết mỗi số có lớn hơn 5 hay không. Giải thích vì sao `$map` vẫn trả đủ ba phần tử kể cả khi kết quả expression là `false`.

### Bài 2 — Lọc embedded documents

Với `items` ở O01, dùng `$filter` để chọn các dòng:

- `active: true`.
- `qty >= 2`.

Sau đó dùng `$map` để trả `sku` và `lineTotal`. Hãy dự đoán kết quả trước khi chạy và giải thích vai trò của `$$item`.

### Bài 3 — Cộng tiền bằng `$reduce`

Với mảng:

```javascript
[
  { sku: "A", qty: 2, unitPrice: 100 },
  { sku: "B", qty: 1, unitPrice: 200 }
]
```

Hãy viết `$reduce` trả tổng tiền bằng 400. Mô tả `$$value` và `$$this` ở mỗi vòng. Sau đó thử trên mảng rỗng và trên giá trị null: hai kết quả khác nhau như thế nào?

### Bài 4 — Tạo một tích lũy nhiều trường

Viết `$reduce` sao cho kết quả chứa:

```javascript
{
  lineCount: 2,
  totalUnits: 3,
  grossAmount: 400
}
```

cho hai dòng hàng của O01. Gợi ý: dùng `initialValue` là object có ba trường và biểu thức `in` tạo object mới, sử dụng `$$value.lineCount`, `$$value.totalUnits` và `$$value.grossAmount`.

### Bài 5 — Hợp, giao và hiệu

Cho:

```javascript
const A = ["mongodb", "java", "mongodb", "backend"];
const B = ["java", "cloud"];
```

Hãy dự đoán tập phần tử của:

- `$setUnion: [A, B]`.
- `$setIntersection: [A, B]`.
- `$setDifference: [A, B]`.
- `$setDifference: [B, A]`.

Vì sao không nên kiểm tra kết quả các toán tử set bằng cách đối chiếu thứ tự phần tử trong mảng?

### Bài 6 — Tập con và tập bằng nhau

Với tags `["vip", "sale", "vip"]`, hãy giải thích kết quả của:

```javascript
{ $setEquals: [
    ["vip", "sale", "vip"],
    ["sale", "vip"]
] }

{ $setIsSubset: [
    ["vip"],
    ["vip", "sale", "vip"]
] }

{ $setIsSubset: [
    [],
    ["vip", "sale"]
] }
```

Đặt thêm điều kiện gì nếu nghiệp vụ nói “tập nhãn bắt buộc phải **không rỗng**”?

### Bài 7 — Đếm số tag riêng biệt

Tạo hai trường từ mảng `tags` của mỗi đơn:

- `tagCount`: tổng số phần tử, tính cả trùng.
- `distinctTagCount`: số giá trị duy nhất.

Sử dụng `$size` và `$setUnion`. Với O01, hãy giải thích vì sao hai con số là **3 và 2**. Với O05 có null, hãy quyết định chính sách giá trị mặc định.

### Bài 8 — Kiểm tra tồn tại và tất cả

Với các dòng hàng trong `items`:

1. Kiểm tra có ít nhất một dòng có `qty > 2`.
2. Kiểm tra mọi dòng có `active: true`.
3. Kiểm tra đồng thời **có ít nhất một dòng** và **mọi dòng active**.

Sử dụng `$map`, `$anyElementTrue`, `$allElementsTrue`, `$size`. Hãy nêu kết quả cho O02 và O03, giải thích bẫy của mảng rỗng.

### Bài 9 — Phân biệt tập hợp và danh sách

Cho mảng các sự kiện:

```javascript
["LOGIN", "VIEW", "LOGIN"]
```

Vì sao `$setUnion` có thể làm mất thông tin về số lần LOGIN? Khi nào nên dùng `$concatArrays`, khi nào nên dùng `$setUnion`? Nếu cần đếm tần suất mỗi loại sự kiện trên toàn collection, có thể dùng `$unwind` rồi `$group` như thế nào?

### Bài 10 — Thiết kế API trả đơn hàng đã xử lý

Một endpoint cần:

- Chỉ trả các đơn `PAID`.
- Trong mỗi đơn, chỉ giữ các dòng hàng active.
- Mỗi dòng hiển thị `sku` và `lineTotal`.
- Trả thêm `totalActiveAmount`.
- Trả danh sách tag riêng biệt để hiển thị bộ lọc.

Hãy thiết kế aggregation pipeline có `$match`, `$project` hoặc `$set`, và các expression `$filter`, `$map`, `$reduce`, `$setUnion`. Giải thích những trường nào là dữ liệu gốc, trường nào chỉ là giá trị dẫn xuất của response.

### Bài 11 — Chọn cấu trúc lưu trữ

Một người dùng có lịch sử 2 triệu hoạt động. So sánh việc:

- Lưu tất cả hoạt động vào `user.events[]` và dùng `$filter + $reduce`.
- Lưu hoạt động thành các document riêng trong `events` và dùng `$match`, `$group`, `$sort`, `$limit`.

Đánh giá giới hạn BSON document, chi phí cập nhật mảng, khả năng truy vấn theo thời gian và xử lý từng batch. Vì sao các toán tử mảng tốt không có nghĩa một document nên chứa mọi sự kiện?

## 23. Tổng kết

**`$map` biến đổi từng phần tử**, **`$filter` chọn những phần tử thỏa điều kiện**, còn **`$reduce` gộp các phần tử vào một giá trị tích lũy**. Ba toán tử làm việc với mảng trong phạm vi một document và có thể kết hợp để xử lý những cấu trúc BSON lồng nhau mà không phải tải toàn bộ mảng về ứng dụng để tự tính.

**Các toán tử tập hợp xử lý mảng như những tập giá trị.** `$setUnion` lấy hợp, `$setIntersection` lấy giao, `$setDifference` lấy hiệu, `$setEquals` và `$setIsSubset` kiểm tra quan hệ tập hợp. Chúng bỏ qua thứ tự và phần tử trùng theo ngữ nghĩa set; không dùng chúng để thay thế phép nối danh sách khi thứ tự hoặc số lần lặp có ý nghĩa.

**Null, missing, mảng rỗng và dữ liệu sai kiểu không đồng nghĩa nhau.** `$map`, `$filter` và `$reduce` có hành vi riêng với mảng rỗng và null; `$ifNull` hoặc `$isArray` nên được dùng có chủ đích theo schema và bất biến nghiệp vụ.

**Chọn đúng phạm vi xử lý.** Expression trên mảng phù hợp để tạo kết quả trong một document; `$unwind` và `$group` phù hợp khi cần tổng hợp phần tử xuyên nhiều document. Khi dữ liệu có kích thước lớn hoặc cần khả năng truy vấn độc lập, mô hình collection và index vẫn quan trọng không kém cú pháp expression.
